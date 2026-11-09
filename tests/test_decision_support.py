"""Independent statistical invariants and source-cache corruption checks."""
import gzip
import numpy as np
import pytest
from loanflow.decision_support import competing_incidence,sample_size_per_arm
from loanflow.robustness import week_block_bootstrap,capacity_curve,HISTORY_FEATURES
from loanflow.ingest import extract,extract_cache_valid


def test_competing_outcomes_conserve_probability_and_handle_tied_censoring():
    rows=competing_incidence([1.,1.,2.],['A_Pending','Unresolved at cutoff','A_Cancelled'])
    assert rows[1]['A_Pending']==pytest.approx(1/3)
    assert rows[-1]['A_Cancelled']==pytest.approx(2/3)
    for row in rows:
        assert sum(row[k] for k in ['unresolved','A_Pending','A_Cancelled','A_Denied'])==pytest.approx(1)


def test_competing_outcome_censor_only_preserves_unresolved_probability():
    rows=competing_incidence([1,2],['Unresolved at cutoff']*2)
    assert rows[-1]['unresolved']==1
    assert all(rows[-1][k]==0 for k in ['A_Pending','A_Cancelled','A_Denied'])


def test_sample_size_scales_with_effect_and_power():
    assert sample_size_per_arm(.5,.02)>sample_size_per_arm(.5,.05)
    assert sample_size_per_arm(.5,.05,power=.9)>sample_size_per_arm(.5,.05,power=.8)
    assert 1500<sample_size_per_arm(.5,.05)<1650


@pytest.mark.parametrize('baseline,effect',[(0,.1),(.95,.1),(.5,0),(.5,-.1)])
def test_sample_size_rejects_impossible_assumptions(baseline,effect):
    with pytest.raises(ValueError):sample_size_per_arm(baseline,effect)


def test_capacity_curve_uses_exact_capacity_and_preserves_rank():
    curve=capacity_curve([1,0,1,0,0],[.9,.8,.7,.2,.1],shares=[.2,.4,1])
    assert [r['review_count'] for r in curve]==[1,2,5]
    assert curve[0]['precision']==1
    assert curve[-1]['recall']==1


def test_week_block_bootstrap_is_deterministic_and_records_cluster_count():
    args=(np.array([0,1]*6),np.array([.2,.8]*6),np.array([.5]*12),np.repeat(['a','b','c'],4))
    a=week_block_bootstrap(*args,iterations=20)
    assert a==week_block_bootstrap(*args,iterations=20)
    assert a['clusters']==3
    assert a['roc_auc_95']==[1.,1.]


def test_week_block_rejects_single_calendar_cluster():
    with pytest.raises(ValueError,match='clusters'):
        week_block_bootstrap([0,1],[.2,.8],[.5,.5],['one','one'])


def test_history_only_feature_list_excludes_mutable_context():
    assert not set(HISTORY_FEATURES)&{'requested_amount','requested_amount_unknown','loan_goal','application_type'}


def test_extraction_cache_detects_changed_output_bytes(tmp_path):
    source=tmp_path/'tiny.gz'
    with gzip.open(source,'wt') as out:
        out.write('<log><trace><string key="concept:name" value="case1"/><event><string key="concept:name" value="A_Pending"/></event></trace></log>')
    processed=tmp_path/'processed';extract(source,processed)
    assert extract_cache_valid(source,processed)
    with (processed/'events.csv').open('a') as f:f.write('corrupted row\n')
    assert not extract_cache_valid(source,processed)


def test_warehouse_always_uses_utc_calendar():
    from loanflow.warehouse import connect_warehouse
    with connect_warehouse(':memory:') as con:
        assert con.execute("SELECT current_setting('TimeZone')").fetchone()[0]=='UTC'
        assert con.execute("SELECT (TIMESTAMPTZ '2016-11-01T00:01:00Z')::DATE::VARCHAR").fetchone()[0]=='2016-11-01'
