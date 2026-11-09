"""Integration checks on built real-data artifacts; skip before first build."""
from pathlib import Path
import json
import duckdb
import pytest
from loanflow.warehouse import connect_warehouse

ROOT=Path(__file__).resolve().parents[1]
DB=ROOT/'data/processed/loanflow.duckdb'
pytestmark=pytest.mark.skipif(not DB.exists(),reason='Build the real-data pipeline first')


def test_recorded_integrity_checks():
    quality=json.loads((ROOT/'reports/data_quality.json').read_text())
    assert quality['passed'] and len(quality['checks'])>=19
    assert all(c['violations']==0 for c in quality['checks'])


def test_test_predictions_match_eligible_population():
    with connect_warehouse(DB,read_only=True) as c:
        assert c.execute("SELECT count(*) FROM test_predictions").fetchone()[0]==c.execute("SELECT count(*) FROM landmark_features WHERE split='test'").fetchone()[0]
        assert c.execute('SELECT count(*) FROM test_predictions WHERE risk<0 OR risk>1 OR risk IS NULL').fetchone()[0]==0
        assert c.execute('SELECT count(*)-count(DISTINCT application_id) FROM test_predictions').fetchone()[0]==0


def test_exported_scenario_zero_reproduces_baseline():
    summary=json.loads((ROOT/'reports/analysis.json').read_text())
    assert summary['scenarios'][0]['median_days']==pytest.approx(summary['median_resolution_days'])
    assert summary['scenarios'][0]['application_days_removed']==0
    assert summary['scenarios'][-1]['median_days']<=summary['scenarios'][0]['median_days']


def test_real_source_provenance_and_cache_match():
    from loanflow.ingest import extract_cache_valid
    proof=json.loads((ROOT/'reports/source_provenance.json').read_text())
    assert proof['is_real_observational_data'] and proof['synthetic_source_records']==0
    assert proof['actual_md5']==proof['publisher_md5']=='10b37a2f78e870d78406198403ff13d2'
    assert extract_cache_valid(ROOT/'data/raw/bpi2017.xes.gz',ROOT/'data/processed')


def test_journey_variants_and_transition_contracts():
    with connect_warehouse(DB,read_only=True) as c:
        assert c.execute('SELECT sum(applications) FROM journey_variants').fetchone()[0]==31509
        assert c.execute('SELECT count(*) FROM application_transitions WHERE elapsed_days<0').fetchone()[0]==0
        assert c.execute("SELECT count(*) FROM application_transitions WHERE from_state IN ('A_Pending','A_Denied','A_Cancelled')").fetchone()[0]==0


def test_frozen_november_audit_has_no_training_applications():
    with connect_warehouse(DB,read_only=True) as c:
        assert c.execute("SELECT count(*) FROM robustness_predictions p JOIN landmark_features f USING(application_id) WHERE p.evaluation_period='november_audit' AND f.split!='unused'").fetchone()[0]==0
        assert c.execute("SELECT min(created_at)>=TIMESTAMPTZ '2016-11-01' AND max(created_at)<TIMESTAMPTZ '2016-12-01' FROM robustness_predictions WHERE evaluation_period='november_audit'").fetchone()[0]


def test_pilot_guardrail_outcomes_reconcile_to_total():
    plan=json.loads((ROOT/'reports/pilot_plan.json').read_text());b=plan['historical_baseline']
    assert b['pending_30d_rate']+b['cancelled_30d_rate']+b['denied_30d_rate']==pytest.approx(b['resolved_30d_rate'])


def test_every_published_journey_event_matches_original_event_table():
    examples=json.loads((ROOT/'reports/example_journeys.json').read_text())
    with connect_warehouse(DB,read_only=True) as c:
        for case in examples:
            for event in case['events']:
                row=c.execute('SELECT activity,origin FROM events WHERE application_id=? AND source_sequence=?',[case['application_id'],event['source_sequence']]).fetchone()
                assert row==(event['activity'],'Application')


def test_real_data_competing_outcomes_conserve_probability():
    import numpy as np
    import pandas as pd
    frame=pd.read_csv(ROOT/'reports/competing_outcomes.csv')
    total=frame[['unresolved','A_Pending','A_Cancelled','A_Denied']].sum(axis=1)
    assert np.allclose(total,1,atol=1e-10)
    assert (frame[['A_Pending','A_Cancelled','A_Denied']].diff().iloc[1:]>=-1e-12).all().all()


def test_release_builder_uses_verified_real_database(tmp_path):
    from loanflow.release import create_release,load_active
    release_id=create_release(ROOT,tmp_path/'releases')
    manifest,model=load_active(tmp_path/'releases')
    assert manifest['release_id']==release_id
    assert model['model']=='smoothed-state-baseline' and model['training_cases']==10452
    assert sum(model['training_state_distribution'].values())==pytest.approx(1)


def test_real_api_request_replays_the_same_sql_state_probability():
    import pandas as pd
    from fastapi.testclient import TestClient
    from loanflow.service import Settings,create_app
    if not (ROOT/'releases/CURRENT').exists():pytest.skip('Build a service release first')
    payload=json.loads((ROOT/'reports/real_replay_request.json').read_text())
    key='integration-test-only-key-01234567890123456789'
    with TestClient(create_app(Settings(ROOT/'releases',key))) as client:
        result=client.post('/v1/score',json=payload,headers={'Authorization':'Bearer '+key})
    assert result.status_code==200
    with connect_warehouse(DB,read_only=True) as con:
        training=con.execute("SELECT state_7d,sum(unresolved_30d) positive,count(*) n FROM landmark_features WHERE split='train' GROUP BY 1").df()
    prevalence=training.positive.sum()/training.n.sum()
    row=training[training.state_7d==result.json()['state_at_day7']].iloc[0]
    expected=(row.positive+20*prevalence)/(row.n+20)
    assert result.json()['unresolved_by_day30_probability']==pytest.approx(expected)
