"""Business analysis: uncertainty, state time and transparent counterfactual scenarios."""
import json
import numpy as np
import pandas as pd


def bootstrap_median_difference(a,b,iterations=1000):
    rng=np.random.default_rng(42)
    differences=[float(np.median(rng.choice(a,len(a),replace=True))-np.median(rng.choice(b,len(b),replace=True))) for _ in range(iterations)]
    return {'difference_days':float(np.median(a)-np.median(b)), 'ci95':np.quantile(differences,[.025,.975]).tolist(),'iterations':iterations}


def kaplan_meier(durations,resolved):
    frame=pd.DataFrame({'time':durations,'resolved':resolved.astype(int)})
    grouped=frame.groupby('time').agg(events=('resolved','sum'),n=('resolved','size')).sort_index()
    remaining=len(frame);survival=1.0;rows=[{'day':0.0,'unresolved_probability':1.0,'at_risk':remaining}]
    for time,row in grouped.iterrows():
        if row.events:survival*=1-row.events/remaining
        if row.events:rows.append({'day':float(time),'unresolved_probability':survival,'at_risk':remaining})
        remaining-=row.n
    return rows


def analyze(con,root):
    apps=con.execute('SELECT * FROM application_mart').df()
    closed=apps[apps.resolved_at.notna()].copy()
    # Restrict descriptive comparisons to Jan-Oct cohorts for longer follow-up.
    mature=closed[closed.created_at<pd.Timestamp('2016-11-01',tz='UTC')]
    a=mature.loc[mature.incomplete_count>0,'resolution_days'].to_numpy()
    b=mature.loc[mature.incomplete_count==0,'resolution_days'].to_numpy()
    rework={'with_incomplete_n':len(a),'without_incomplete_n':len(b),'with_incomplete_median':float(np.median(a)),
            'without_incomplete_median':float(np.median(b)),**bootstrap_median_difference(a,b),
            'interpretation':'Observational difference among resolved Jan–Oct applications. Selection, case complexity and longer time at risk can explain the association; not an effect of rework.'}
    state=con.execute("""SELECT s.activity,count(*) AS applications,median(s.days_in_state) AS median_days,
        quantile_cont(s.days_in_state,0.9) AS p90_days,sum(s.days_in_state) AS total_days
        FROM state_case_durations s JOIN application_mart m USING(application_id)
        WHERE m.resolved_at IS NOT NULL GROUP BY s.activity ORDER BY total_days DESC""").df()
    state['share_of_elapsed']=state.total_days/state.total_days.sum()
    state.to_csv(root/'reports/state_bottlenecks.csv',index=False)
    intervals=con.execute("SELECT application_id,sum(days_in_state) AS target_days FROM state_case_durations WHERE activity='A_Complete' GROUP BY 1").df()
    scenario_base=closed.merge(intervals,on='application_id',how='left').fillna({'target_days':0})
    rows=[]
    for reduction in [0,.1,.25,.5]:
        after=np.maximum(0,scenario_base.resolution_days-scenario_base.target_days*reduction)
        rows.append({'reduction':reduction,'applications':len(after),'affected_applications':int((scenario_base.target_days>0).sum()),
            'median_days':float(np.median(after)),'p90_days':float(np.quantile(after,.9)),
            'application_days_removed':float(scenario_base.target_days.sum()*reduction),
            'mean_days_removed_per_application':float(scenario_base.target_days.mean()*reduction),
            'resolved_within_30d_share':float((after<=30).mean())})
    pd.DataFrame(rows).to_csv(root/'reports/improvement_scenarios.csv',index=False)
    by_outcome=con.execute("""SELECT outcome_label,(incomplete_count>0) has_incomplete,count(*) n,median(resolution_days) median_days FROM application_mart WHERE created_at<TIMESTAMPTZ '2016-11-01' AND resolved_at IS NOT NULL GROUP BY 1,2 ORDER BY 1,2""").df()
    by_outcome.to_csv(root/'reports/rework_by_outcome.csv',index=False)
    # Segment profiles retain denominators and sample size to avoid small-cell stories.
    segments=con.execute("""SELECT loan_goal,count(*) n,median(resolution_days) median_days,
     avg((incomplete_count>0)::INT) incomplete_rate,
     avg(coalesce((outcome='A_Pending'),false)::INT) pending_rate
     FROM application_mart GROUP BY loan_goal ORDER BY n DESC""").df()
    segments.to_csv(root/'reports/segments.csv',index=False)
    for table in ['monthly_cohorts','daily_backlog']:
        con.execute(f'SELECT * FROM {table}').df().to_csv(root/f'reports/{table}.csv',index=False)
    surv=kaplan_meier(apps.observed_days.to_numpy(),apps.resolved_at.notna().to_numpy())
    pd.DataFrame(surv).to_csv(root/'reports/resolution_survival.csv',index=False)
    summary={'applications':len(apps),'events':int(apps.event_count.sum()),'offers':int(apps.offer_count.sum()),
      'resolved':len(closed),'censored':len(apps)-len(closed),'median_resolution_days':float(closed.resolution_days.median()),
      'p90_resolution_days':float(closed.resolution_days.quantile(.9)),
      'incomplete_rate':float((apps.incomplete_count>0).mean()),
      'outcomes':apps.outcome_label.value_counts().astype(int).to_dict(),
      'source_cutoff':str(apps.observed_until.max()),'top_state':state.iloc[0].to_dict(),
      'rework_comparison':rework,'scenarios':rows,
      'scenario_caveat':'Mechanical compression of observed A_Complete intervals among resolved cases only; no capacity feedback, changed outcomes or staff time modeled. Not a causal forecast or realized saving.'}
    (root/'reports/analysis.json').write_text(json.dumps(summary,indent=2,default=str))
    return summary
