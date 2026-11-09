"""Observed journey evidence, competing outcomes, provenance and pilot planning."""
import hashlib
import json
import math
import platform
from datetime import datetime,timezone
import numpy as np
import pandas as pd
from scipy.stats import norm


def competing_incidence(durations,outcomes):
    """Aalen–Johansen for mutually exclusive first endpoints, with tied censoring.

    All risk sets are evaluated immediately before the observed time. Censoring
    at a tied time leaves the risk set only after endpoint increments are added.
    """
    kinds=['A_Pending','A_Cancelled','A_Denied']
    data=pd.DataFrame({'days':durations,'outcome':outcomes})
    remaining=len(data);survival=1.;incidence={k:0. for k in kinds}
    rows=[{'day':0.,'unresolved':1.,**incidence,'at_risk':remaining}]
    for day,group in data.groupby('days',sort=True):
        counts=group.outcome.value_counts();events=sum(int(counts.get(k,0)) for k in kinds)
        before=survival
        if events:
            for kind in kinds:incidence[kind]+=before*int(counts.get(kind,0))/remaining
            survival=before*(1-events/remaining)
            rows.append({'day':float(day),'unresolved':float(survival),**incidence,'at_risk':remaining})
        remaining-=len(group)
    return rows


def sample_size_per_arm(p0,absolute_effect,alpha=.05,power=.8):
    """Normal-approximation two-sided difference-in-proportions planning.

    Equal independent arms; no continuity correction, clustering or attrition.
    The effect is an assumption, not an estimate from the observational log.
    """
    p1=p0+absolute_effect
    if not(0<p0<1 and 0<p1<1 and absolute_effect>0 and 0<alpha<1 and .5<power<1):
        raise ValueError('Rates must be inside (0,1), effect positive, and alpha/power valid')
    pooled=(p0+p1)/2
    n=((norm.ppf(1-alpha/2)*math.sqrt(2*pooled*(1-pooled))+norm.ppf(power)*math.sqrt(p0*(1-p0)+p1*(1-p1)))**2)/(absolute_effect**2)
    return math.ceil(n)


def sha256(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        while block:=stream.read(1024*1024):digest.update(block)
    return digest.hexdigest()


def build_decision_support(con,root):
    apps=con.execute('SELECT * FROM application_mart ORDER BY application_id').df()
    cumulative=pd.DataFrame(competing_incidence(apps.observed_days.to_numpy(),apps.outcome_label.to_numpy()))
    cumulative.to_csv(root/'reports/competing_outcomes.csv',index=False)
    for name in ['transition_summary','journey_variants','pilot_baseline']:
        con.execute(f'SELECT * FROM {name}').df().to_csv(root/f'reports/{name}.csv',index=False)
    chosen=[]
    for label,query in [
        ('Pending endpoint',"outcome='A_Pending'"),('Cancelled endpoint',"outcome='A_Cancelled'"),
        ('Denied endpoint',"outcome='A_Denied'"),('Unresolved at cutoff','resolved_at IS NULL'),
        ('Repeated incomplete-state visits',"incomplete_count>=3 AND outcome='A_Pending'"),
        ('Multiple offers',"offer_count>=3 AND outcome='A_Pending'")]:
        row=con.execute(f'SELECT application_id FROM application_mart WHERE {query} ORDER BY application_id LIMIT 1').fetchone()
        if not row:continue
        aid=row[0];app=apps[apps.application_id==aid].iloc[0]
        events=con.execute('''SELECT e.source_sequence,e.activity,e.event_time,e.origin,e.lifecycle,
         epoch(e.event_time-m.created_at)/86400.0 AS elapsed_days
         FROM events e JOIN application_mart m USING(application_id)
         WHERE e.application_id=? AND e.origin='Application' AND e.event_time<=m.observed_until
         ORDER BY e.event_time,e.source_sequence''',[aid]).df()
        chosen.append({'label':label,'application_id':aid,'outcome':app.outcome_label,'observed_days':float(app.observed_days),
            'source_event_count':int(app.event_count),'offer_count':int(app.offer_count),'incomplete_count':int(app.incomplete_count),
            'events':json.loads(events.to_json(orient='records',date_format='iso'))})
    (root/'reports/example_journeys.json').write_text(json.dumps(chosen,indent=2))
    baseline=con.execute("SELECT * FROM pilot_baseline WHERE state_7d='A_Complete'").df().iloc[0].to_dict()
    weekly=float(baseline['applications'])/(366/7)
    plan={'population':'Applications still open in A_Complete at day seven, with full observed 30-day follow-up',
        'historical_baseline':baseline,'historical_eligible_per_week':weekly,
        'baseline_note':'Rates measured from mature 2016 applications; future recruitment and performance may differ.',
        'primary_outcome':'Any first operational endpoint by day 30; report pending, cancelled and denied separately and set customer-outcome guardrails.',
        'design':'Two-sided alpha .05, power .80, equal independent arms; normal approximation without continuity correction.',
        'effect_note':'Assumed absolute percentage-point improvements, not measured treatment effects.',
        'scenarios':[]}
    for effect in [.02,.03,.05,.08,.1]:
        if baseline['resolved_30d_rate']+effect>=1:continue
        per_arm=sample_size_per_arm(baseline['resolved_30d_rate'],effect)
        plan['scenarios'].append({'assumed_absolute_effect':effect,'per_arm':per_arm,'total_sample':per_arm*2,
           'historical_volume_recruitment_weeks':per_arm*2/weekly,'additional_followup_days':23})
    (root/'reports/pilot_plan.json').write_text(json.dumps(plan,indent=2,default=str))
    # Source provenance: hashes computed from the actual downloaded bytes.
    source=root/'data/raw/bpi2017.xes.gz';metadata=json.loads((root/'data/raw/source_metadata.json').read_text())
    actual_md5=hashlib.md5(source.read_bytes()).hexdigest()
    expected=next(f['computed_md5'] for f in metadata['files'] if f['id']==24044117)
    provenance={'is_real_observational_data':True,'synthetic_source_records':0,'title':metadata['title'],
      'citation':metadata['citation'],'doi':metadata['doi'],'publisher_metadata_url':'https://api.figshare.com/v2/articles/12696884',
      'publisher_md5':expected,'actual_md5':actual_md5,'checksum_matches':actual_md5==expected,
      'source_sha256':sha256(source),'source_size_bytes':source.stat().st_size,
      'verified_utc':datetime.now(timezone.utc).isoformat(),'license':metadata['license'],
      'record_counts':{'applications':len(apps),'events':int(apps.event_count.sum()),'offers':int(apps.offer_count.sum())},
      'distinction':'Source records, summaries and retrospective predictions use real events. Scenario reductions and treatment effects in pilot planning are explicit assumptions. Synthetic fixtures exist only in tests.'}
    (root/'reports/source_provenance.json').write_text(json.dumps(provenance,indent=2))
    return {'pilot':plan,'provenance':provenance,'examples':chosen}
