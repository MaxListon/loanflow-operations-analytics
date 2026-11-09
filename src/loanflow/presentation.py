"""Build a self-contained recruiter demo, with no hosted service or CDN required."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from plotly.offline import get_plotlyjs


def records(frame):
    return json.loads(frame.to_json(orient='records',date_format='iso'))


def build_demo(con,root,summary,model,quality):
    bundles={}
    for key,condition in {'All 2016':'true','Q1 · Jan–Mar':"cohort_month<'2016-04-01'",'Q2 · Apr–Jun':"cohort_month>='2016-04-01' AND cohort_month<'2016-07-01'",'Q3 · Jul–Sep':"cohort_month>='2016-07-01' AND cohort_month<'2016-10-01'",'Q4 · Oct–Dec':"cohort_month>='2016-10-01'"}.items():
        apps=con.execute(f'SELECT * FROM application_mart WHERE {condition}').df()
        state=con.execute(f'''SELECT s.activity,count(*) n,median(s.days_in_state) median_days,sum(s.days_in_state) total_days
          FROM state_case_durations s JOIN application_mart m USING(application_id)
          WHERE m.resolved_at IS NOT NULL AND {condition} GROUP BY 1 ORDER BY total_days DESC''').df()
        state['share']=state.total_days/state.total_days.sum()
        outcomes=apps.outcome_label.value_counts()
        mature=apps[apps.created_at+pd.Timedelta(days=30)<=pd.Timestamp(summary['source_cutoff'])]
        bundles[key]={'n':len(apps),'events':int(apps.event_count.sum()),'median':float(apps.resolution_days.median()),'p90':float(apps.resolution_days.quantile(.9)),
          'rework':float((apps.incomplete_count>0).mean()),'censored':int(apps.resolved_at.isna().sum()),
          'resolved30':float((mature.resolved_at.notna() & (mature.resolution_days<=30)).mean()),
          'state':records(state),'outcomes':[{'name':name,'n':int(n)} for name,n in outcomes.items()]}
    scenario=con.execute('''SELECT m.resolution_days,coalesce(s.days_in_state,0) target_days
     FROM application_mart m LEFT JOIN state_case_durations s ON m.application_id=s.application_id AND s.activity='A_Complete'
     WHERE m.resolved_at IS NOT NULL''').df()
    payload={'summary':summary,'model':model,'quality':quality,'bundles':bundles,
             'cohorts':records(con.execute('SELECT * FROM monthly_cohorts').df()),
             'robustness':json.loads((root/'reports/robustness.json').read_text()),
             'monthly_audit':records(pd.read_csv(root/'reports/monthly_model_audit.csv')),
             'capacity_curve':records(pd.read_csv(root/'reports/review_capacity.csv')),
             'pilot':json.loads((root/'reports/pilot_plan.json').read_text()),
             'source':json.loads((root/'reports/source_provenance.json').read_text()),
             'examples':json.loads((root/'reports/example_journeys.json').read_text()),
             'variants':records(con.execute('SELECT * FROM journey_variants LIMIT 8').df()),
             'transitions':records(con.execute('SELECT * FROM transition_summary ORDER BY applications DESC LIMIT 15').df()),
             'competing':records(pd.read_csv(root/'reports/competing_outcomes.csv').iloc[::20]),
             'backlog':records(con.execute('SELECT * FROM daily_backlog').df()),
             'scenario':np.round(scenario[['resolution_days','target_days']].to_numpy(),6).tolist(),
             'rework_outcomes':records(con.execute("SELECT * FROM read_csv_auto('reports/rework_by_outcome.csv')").df()),
             'segments':records(con.execute('SELECT * FROM read_csv_auto(\'reports/segments.csv\')').df())}
    template=(root/'dashboard/template.html').read_text()
    html=template.replace('/*PLOTLY_LIBRARY*/',get_plotlyjs()).replace('/*REPORT_DATA*/',json.dumps(payload,default=str).replace('</','<\\/'))
    (root/'dashboard/index.html').write_text(html)
    return payload


def write_memo(root,summary,model,quality):
    s,m=summary,model['test'];top=s['top_state'];r=s['rework_comparison'];scenario=s['scenarios'][2]
    memo=f'''# LoanFlow — executive decision memo

**Decision:** Prioritize investigation of the A_Complete stage and a measured customer-follow-up pilot, subject to verifying state semantics, case mix and intervention cost.

This is a retrospective portfolio analysis of BPI Challenge 2017. No bank intervention was performed.

## What the data shows

- Scope: **{s['applications']:,} applications**, **{s['events']:,} events**, and **{s['offers']:,} offers**.
- Median time to the first operational endpoint: **{s['median_resolution_days']:.1f} calendar days**; 90th percentile: **{s['p90_resolution_days']:.1f} days**. These duration summaries include resolved applications only; **{s['censored']}** remain unresolved at the observation cutoff.
- The largest application-state time bucket is **{top['activity']}**, representing **{top['share_of_elapsed']:.1%}** of accumulated elapsed time among resolved cases. This measures elapsed state time, not employee effort.
- **{s['incomplete_rate']:.1%}** of applications have at least one incomplete-state event. In resolved January–October cohorts, their median duration differs from other resolved cases by **{r['difference_days']:.1f} days** (application bootstrap 95% interval **{r['ci95'][0]:.1f}–{r['ci95'][1]:.1f}**). The pooled incomplete-file group is faster, but the no-incomplete group contains many long cancellation journeys. Within the pending-endpoint group, incomplete cases have a longer median (16.9 vs. 11.2 days). Outcome mix and selection matter; neither comparison is causal.

## Early-warning model

Among applications still open on day seven, a validation-selected model predicts whether they remain unresolved at day 30. The final evaluation uses September–October applications, separate from training and July model selection.

- Test cases: **{m['n']:,}**; unresolved prevalence: **{m['prevalence']:.1%}**.
- ROC AUC: **{m['roc_auc']:.3f}**; average precision: **{m['average_precision']:.3f}**.
- Brier score: **{m['brier']:.3f}**, compared with **{model['baseline_test']['brier']:.3f}** for training-prevalence predictions and **{model['state_baseline_test']['brier']:.3f}** for the stronger state-only baseline. The gain over the logistic reference is small, so a simpler model may be preferable operationally.
- Reviewing the highest-risk 20% identifies a group with **{m['top20_precision']:.1%}** unresolved outcomes, a **{m['top20_lift']:.2f}×** concentration over the test population; it captures **{m['top20_recall']:.1%}** of unresolved outcomes.

Use risk scores to prioritize a support-policy experiment, not approve or deny credit. Retrospective risk identification does not establish that intervention will help.

## Size the opportunity without claiming savings

Mechanically compressing A_Complete intervals by 25%, while holding all other intervals and outcomes fixed, changes median time among historically resolved cases from **{s['median_resolution_days']:.1f}** to **{scenario['median_days']:.1f} days**. The total is **{scenario['application_days_removed']:,.0f} application-days**, not staff-days, money saved or a causal forecast. Unresolved cases and queue feedback are excluded.

## Recommended pilot

1. Enroll applications still open on day seven that are in the A_Complete state; freeze eligibility before assignment.
2. Randomize by application to existing service or a clear next-step summary plus targeted follow-up. Keep contact cadence, privacy and service policies consistent with the operating institution.
3. Primary outcome: resolved by day 30, evaluated by intention to treat. Report pending, cancellation and denial separately: faster cancellation is not automatically a better customer outcome.
4. Guardrails: support contacts, complaints, completion/acceptance outcomes, and treatment burden. Specify handling for repeat offers and multiple applications if linkage becomes available.
5. Estimate the target segment's baseline from the data; set a meaningful minimum effect and intervention cost with stakeholders before calculating sample size. Do not launch based on the scenario alone.

## Reliability and limits

**{len(quality['checks'])} integrity checks passed.** Source checksum matches the publisher. Missing/zero requested amounts are preserved in raw data and modeled as unknown. First terminal events define endpoints; some applications have later terminal events, retained in raw data. This historical dataset describes one Dutch institution, with follow-up through early 2017; it does not establish current performance or transferability to another bank.

Source: van Dongen (2017), [BPI Challenge 2017](https://doi.org/10.4121/uuid:5f3067df-f10b-45da-b98b-86ae4c7a310b). See `docs/METHODOLOGY.md`, `reports/data_quality.json` and `reports/model_metrics.json` for definitions and audit evidence.
'''
    robustness=json.loads((root/'reports/robustness.json').read_text())
    pilot=json.loads((root/'reports/pilot_plan.json').read_text())
    original=robustness['results']['september_october'];nov=robustness['results']['november_audit']
    five=next(r for r in pilot['scenarios'] if r['assumed_absolute_effect']==.05)
    memo+=f"""

## Additional validation and the operating recommendation

The frozen context model's AUC declines to **{nov['context_model']['roc_auc']:.3f}** on **{nov['context_model']['n']:,} November cases**. Removing uncertain trace-context fields yields history-only AUC **{original['history_only']['roc_auc']:.3f}** in September–October and **{nov['history_only']['roc_auc']:.3f}** in November. Its Brier score is slightly worse than the transparent state-only baseline in both periods. These diagnostics support a simple state-based support-policy experiment unless context-field immutability and the value of added complexity can be established. November operational aggregates had been inspected before this extension; it is not external validation or a claim of a wholly untouched dataset.

The pilot segment contains **{pilot['historical_baseline']['applications']:,}** observed A_Complete cases still open on day seven, with baseline 30-day resolution **{pilot['historical_baseline']['resolved_30d_rate']:.1%}**. An **assumed five-percentage-point absolute effect** requires approximately **{five['per_arm']:,} applications per arm** under a two-sided normal approximation (alpha=.05, power=.80, equal independent arms, no attrition/clustering adjustment). Historical recruitment volume implies **{five['historical_volume_recruitment_weeks']:.1f} weeks**, plus **23 days** after the final day-seven randomization to observe the day-30 horizon. This is planning arithmetic, not a measured treatment effect or future-volume forecast.

Raw data is real observational data; source hashes and original-case event matches are recorded in `reports/source_provenance.json` and the tests. A clean source rebuild reproduced the primary metrics in `reports/reproduction_check.json`. The interactive real-journey examples use original source application IDs and event ordinals.
"""
    (root/'reports/EXECUTIVE_MEMO.md').write_text(memo)
