"""Synthetic edge cases verify the analytical contracts, not just code paths."""
from pathlib import Path
import gzip
import csv
import duckdb
import numpy as np
import pytest
from loanflow.analysis import kaplan_meier
from loanflow.ingest import extract,verify
from loanflow.model import metrics

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture
def con():
    c=duckdb.connect(':memory:');c.execute("SET TimeZone='UTC'")
    c.execute('CREATE TABLE applications(application_id VARCHAR,requested_amount DOUBLE,application_type VARCHAR,loan_goal VARCHAR)')
    c.executemany("INSERT INTO applications VALUES (?,?,'New credit','Test')",[('A',10000),('B',0),('C',20000),('D',5000)])
    c.execute('CREATE TABLE events(application_id VARCHAR,source_sequence INTEGER,event_id VARCHAR,activity VARCHAR,lifecycle VARCHAR,event_time TIMESTAMPTZ,origin VARCHAR,resource VARCHAR,offer_id VARCHAR)')
    rows=[]
    specs={'A':[('2016-01-01','A_Create Application'),('2016-01-02','A_Complete'),('2016-01-04','O_Create Offer'),('2016-01-05','O_Create Offer'),('2016-01-08','A_Incomplete'),('2016-01-11','A_Pending'),('2016-02-05','A_Denied')],
           'B':[('2016-01-02','A_Create Application'),('2016-01-03','A_Complete'),('2016-02-15','W_Call after offers')],
           'C':[('2016-01-03','A_Create Application'),('2016-01-04','A_Complete'),('2016-02-08','A_Cancelled')],
           'D':[('2016-01-04','A_Create Application'),('2016-01-05','A_Complete'),('2016-01-10','A_Pending')]}
    for aid,events in specs.items():
        for seq,(date,activity) in enumerate(events):
            origin='Application' if activity.startswith('A_') else 'Offer' if activity.startswith('O_') else 'Workflow'
            rows.append((aid,seq,f'{aid}-{seq}',activity,'complete',date,origin,'User1',None))
    c.executemany('INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?)',rows)
    c.execute("CREATE TABLE offers AS SELECT 'o1' offer_id,'A' application_id UNION ALL SELECT 'o2','A'")
    for file in ['02_marts.sql','03_landmark.sql']:c.execute((ROOT/'sql'/file).read_text())
    yield c
    c.close()


def test_multiple_offers_do_not_duplicate_applications(con):
    assert con.execute('SELECT count(*) FROM application_mart').fetchone()[0]==4
    assert con.execute("SELECT offer_count FROM application_mart WHERE application_id='A'").fetchone()[0]==2


def test_first_endpoint_wins_over_later_conflicting_terminal(con):
    assert con.execute("SELECT outcome,resolution_days FROM application_mart WHERE application_id='A'").fetchone()==('A_Pending',10.)


def test_censored_case_retained_and_not_given_a_fake_resolution(con):
    assert con.execute("SELECT resolution_days IS NULL, observed_days FROM application_mart WHERE application_id='B'").fetchone()==(True,44.)


def test_state_time_conserves_observed_duration(con):
    bad=con.execute('''SELECT count(*) FROM (SELECT m.application_id,m.observed_days,sum(s.interval_days) total
    FROM application_mart m JOIN state_intervals s USING(application_id) GROUP BY 1,2 HAVING abs(total-observed_days)>1e-9)''').fetchone()[0]
    assert bad==0


def test_events_at_landmark_are_excluded(con):
    assert con.execute("SELECT incomplete_7d FROM landmark_features WHERE application_id='A'").fetchone()[0]==0


def test_future_event_does_not_change_historical_features(con):
    before=con.execute("SELECT events_7d,state_7d FROM landmark_features WHERE application_id='A'").fetchone()
    con.execute("INSERT INTO events VALUES ('A',99,'future','A_Validating','complete','2016-01-09','Application','User2',NULL)")
    con.execute((ROOT/'sql/03_landmark.sql').read_text())
    assert con.execute("SELECT events_7d,state_7d FROM landmark_features WHERE application_id='A'").fetchone()==before


def test_day7_population_and_day30_labels(con):
    rows=dict(con.execute('SELECT application_id,unresolved_30d FROM landmark_features').fetchall())
    assert rows=={'A':0,'B':1,'C':1}


def test_unknown_amount_does_not_become_zero_spending(con):
    assert con.execute("SELECT requested_amount IS NULL,amount_band FROM application_mart WHERE application_id='B'").fetchone()==(True,'Unknown')


def test_backlog_uses_snapshot_not_future_endpoint(con):
    assert con.execute("SELECT open_applications FROM daily_backlog WHERE report_date='2016-01-09'").fetchone()[0]==4
    assert con.execute("SELECT open_applications FROM daily_backlog WHERE report_date='2016-01-10'").fetchone()[0]==3


def test_survival_handles_censoring_and_tied_events():
    rows=kaplan_meier(np.array([1.,1.,2.]),np.array([True,False,True]))
    assert rows[1]['unresolved_probability']==pytest.approx(2/3)
    assert rows[-1]['unresolved_probability']==0


def test_capacity_ranking_is_exact_and_ties_stable():
    m=metrics([1,0,0,0,1],np.array([.5]*5))
    assert m['review_count']==1
    assert m['top20_precision']==1
    assert m['top20_recall']==.5


def test_source_checksum_rejects_changed_bytes(tmp_path):
    p=tmp_path/'bad.gz';p.write_bytes(b'not the official source')
    with pytest.raises(ValueError,match='checksum'):verify(p)


def test_parser_preserves_sequence_and_resolves_offer_creation_id(tmp_path):
    p=tmp_path/'mini.gz'
    with gzip.open(p,'wt') as f:f.write('''<log><trace><string key="concept:name" value="case1"/><float key="RequestedAmount" value="100"/><event><string key="concept:name" value="O_Create Offer"/><string key="EventID" value="offer1"/></event><event><string key="concept:name" value="A_Pending"/></event></trace></log>''')
    out=tmp_path/'processed';counts=extract(p,out)
    rows=list(csv.DictReader((out/'events.csv').open()))
    assert counts=={'applications':1,'events':2}
    assert rows[0]['offer_id']=='offer1'
    assert [r['source_sequence'] for r in rows]==['0','1']
