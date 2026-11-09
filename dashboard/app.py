"""Analyst workspace backed by the DuckDB reporting layer.
Run from project root: streamlit run dashboard/app.py
"""
from pathlib import Path
import json
import duckdb
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from loanflow.warehouse import connect_warehouse

ROOT=Path(__file__).resolve().parents[1]
st.set_page_config(page_title='LoanFlow | Analyst workspace',page_icon='◈',layout='wide')
st.markdown('''<style>.stApp{background:#f4f6fa}h1{letter-spacing:-1px}div[data-testid="stMetric"]{background:white;padding:16px;border:1px solid #dde4ed;border-radius:10px}</style>''',unsafe_allow_html=True)
if not (ROOT/'data/processed/loanflow.duckdb').exists():
    st.error('Build the project first: python -m loanflow.pipeline');st.stop()

@st.cache_data
def read_table(name):
    # Names originate exclusively in the hard-coded calls below.
    with connect_warehouse(ROOT/'data/processed/loanflow.duckdb',read_only=True) as con:
        return con.execute(f'SELECT * FROM {name}').df()

@st.cache_data
def report(name):
    return json.loads((ROOT/'reports'/name).read_text())

apps=read_table('application_mart')
st.sidebar.title('LoanFlow.')
st.sidebar.caption('Loan operations intelligence')
page=st.sidebar.radio('Workspace',['Overview','Real journeys','Process & rework','Early warning','Validation audit','Improvement lab','Data explorer'])
st.sidebar.divider()
st.sidebar.caption('Independent portfolio analysis · BPI Challenge 2017 · Historical data, not a live banking system.')
st.title(page)
st.caption('Reproducible Python + DuckDB SQL | Real event data | Calendar days, UTC')
if page in ['Overview','Process & rework','Data explorer']:
    c1,c2,c3=st.columns(3)
    quarter=c1.selectbox('Creation quarter',['All',1,2,3,4])
    goals=c2.multiselect('Loan purpose',sorted(apps.loan_goal.unique()))
    bands=c3.multiselect('Requested amount',['Unknown','<10k','10–25k','25k+'])
    filtered=apps.copy()
    if quarter!='All':filtered=filtered[filtered.created_at.dt.quarter==quarter]
    if goals:filtered=filtered[filtered.loan_goal.isin(goals)]
    if bands:filtered=filtered[filtered.amount_band.isin(bands)]
    if filtered.empty:st.info('No applications match these filters.');st.stop()
    ids=set(filtered.application_id)

if page=='Overview':
    cols=st.columns(4)
    for col,label,value in zip(cols,['Applications','Median resolution','90th percentile','Incomplete files'],[f'{len(filtered):,}',f'{filtered.resolution_days.median():.1f}d',f'{filtered.resolution_days.quantile(.9):.1f}d',f'{(filtered.incomplete_count>0).mean():.1%}']):col.metric(label,value)
    st.caption('Duration summaries use resolved applications only; incomplete files means at least one A_Incomplete event.')
    a,b=st.columns([1.4,1])
    cohort=filtered.groupby('cohort_month').resolution_days.agg(median='median',p90=lambda x:x.quantile(.9)).reset_index()
    a.plotly_chart(px.line(cohort,x='cohort_month',y=['median','p90'],title='Resolution speed by creation cohort',labels={'value':'Calendar days','cohort_month':'Creation month'}),width='stretch')
    outcomes=filtered.outcome_label.value_counts().reset_index()
    b.plotly_chart(px.pie(outcomes,names='outcome_label',values='count',hole=.65,title='First operational endpoints'),width='stretch')
    st.info('A_Pending is an operational endpoint, not proof of disbursement. Faster resolution is not automatically better if it increases cancellations or denials.')
    backlog=read_table('daily_backlog')
    st.plotly_chart(px.line(backlog,x='report_date',y=['open_applications','aged_14d'],title='Historical end-of-day backlog · all applications'),width='stretch')
    st.caption('The backlog chart uses all applications; cohort and segment filters apply to the top charts and cards.')

elif page=='Real journeys':
    examples=report('example_journeys.json')
    chosen=st.selectbox('Observed source application',range(len(examples)),format_func=lambda i:examples[i]['label'])
    case=examples[chosen];events=pd.DataFrame(case['events'])
    st.info(f"{case['application_id']} · {case['outcome']} · {case['source_event_count']} original lifecycle events. Deterministically selected example, not a representative sample.")
    timeline=go.Figure(go.Scatter(x=events.elapsed_days,y=list(range(len(events))),mode='lines+markers',text=events.activity,hovertemplate='%{text}<br>Day %{x:.4f}<extra></extra>'))
    timeline.update_layout(title='Original application-state sequence',xaxis_title='Calendar days from creation',yaxis={'tickvals':list(range(len(events))),'ticktext':events.activity.tolist(),'autorange':'reversed'},height=500)
    st.plotly_chart(timeline,width='stretch')
    st.dataframe(events,width='stretch',hide_index=True)
    st.subheader('Competing first endpoints with censoring')
    cumulative=pd.read_csv(ROOT/'reports/competing_outcomes.csv')
    st.plotly_chart(px.line(cumulative,x='day',y=['A_Pending','A_Cancelled','A_Denied'],line_shape='hv',range_x=[0,60],labels={'value':'Cumulative probability','day':'Calendar days'}),width='stretch')
    st.caption('All applications; first 60 days shown. Pending does not prove funding. Cancellations and denials are separate competing endpoints.')
    st.subheader('Common application-state transitions')
    st.dataframe(read_table('transition_summary').sort_values('applications',ascending=False),width='stretch',hide_index=True)
    st.subheader('Most common state sequences')
    st.dataframe(read_table('journey_variants').head(20),width='stretch',hide_index=True)

elif page=='Process & rework':
    states=read_table('state_case_durations');states=states[states.application_id.isin(ids & set(apps.loc[apps.resolved_at.notna(),'application_id']))]
    score=states.groupby('activity').agg(applications=('application_id','size'),median_days=('days_in_state','median'),total_days=('days_in_state','sum')).reset_index().sort_values('total_days',ascending=False)
    if score.empty:st.info('No resolved cases in this segment.');st.stop()
    score['elapsed_share']=score.total_days/score.total_days.sum()
    st.plotly_chart(px.bar(score,x='elapsed_share',y='activity',orientation='h',title='Accumulated elapsed application-state time'),width='stretch')
    st.dataframe(score,width='stretch',hide_index=True)
    st.download_button('Download state scorecard',score.to_csv(index=False),'state_scorecard.csv','text/csv')
    st.warning('State duration includes waiting and customer response time. It is not measured labor effort. Associations between incomplete files and duration are not causal effects.')
    rework=pd.read_csv(ROOT/'reports/rework_by_outcome.csv')
    st.subheader('Check the outcome mix · Jan–Oct, all segments')
    st.dataframe(rework,width='stretch',hide_index=True)
    survival=pd.read_csv(ROOT/'reports/resolution_survival.csv')
    st.plotly_chart(px.line(survival,x='day',y='unresolved_probability',title='Kaplan–Meier unresolved probability · all applications',line_shape='hv'),width='stretch')
    st.caption('Censors unresolved cases at the observation cutoff. Administrative censoring may still differ by cohort; curve is descriptive.')

elif page=='Early warning':
    m=report('model_metrics.json');test=m['test']
    st.info(f"Selected on July validation log loss: {m['selected_model']}. Test: September–October applications still open on day seven.")
    cols=st.columns(4)
    for col,label,value in zip(cols,['Test cases','ROC AUC','Top 20% lift','Brier score'],[f"{test['n']:,}",f"{test['roc_auc']:.3f}",f"{test['top20_lift']:.2f}×",f"{test['brier']:.3f}"]):col.metric(label,value)
    comparison=pd.DataFrame({'Constant baseline':m['baseline_test'],'State-only baseline':m['state_baseline_test'],'Logistic reference':m['logistic_test'],'Selected model':test})
    st.dataframe(comparison.loc[['roc_auc','average_precision','brier','log_loss','top20_precision','top20_recall']],width='stretch')
    calibration=pd.DataFrame(m['calibration'])
    figure=px.line(calibration,x='predicted',y='observed',markers=True,title='Out-of-time probability calibration',range_x=[0,1],range_y=[0,1])
    figure.add_trace(go.Scatter(x=[0,1],y=[0,1],name='Ideal',line={'dash':'dot','color':'gray'}))
    st.plotly_chart(figure,width='stretch')
    st.subheader('Capacity-limited review queue · retrospective test set')
    capacity=st.slider('Share of eligible applications reviewed (%)',5,50,20,5)
    scores=read_table('test_predictions').sort_values(['risk','application_id'],ascending=[False,True],kind='stable')
    count=int(np.ceil(len(scores)*capacity/100));queue=scores.head(count)
    st.write(f"Reviewing {count:,} cases concentrates unresolved outcomes to {queue.unresolved_30d.mean():.1%}, capturing {queue.unresolved_30d.sum()/scores.unresolved_30d.sum():.1%} of all unresolved cases.")
    st.dataframe(queue.drop(columns='unresolved_30d').head(100),width='stretch',hide_index=True)
    st.download_button('Export retrospective queue',queue.to_csv(index=False),'review_queue.csv','text/csv')
    st.caption('Outcome labels in the export are for retrospective evaluation only. This queue is not live. Risk scores are not treatment-effect estimates or credit decisions.')
    st.subheader('Validation trials')
    st.dataframe(pd.DataFrame(m['trials']),width='stretch',hide_index=True)
    st.subheader('Segment calibration checks')
    st.dataframe(pd.read_csv(ROOT/'reports/model_slice_metrics.csv'),width='stretch',hide_index=True)

elif page=='Validation audit':
    audit=report('robustness.json')
    st.info('Model settings frozen before this extension. History-only removes trace-level context. November operational aggregates had been inspected previously; this is additional temporal validation, not wholly untouched data.')
    rows=[]
    for period,result in audit['results'].items():
        for name in ['context_model','history_only','state_only']:
            rows.append({'evaluation':period,'model':name,**result[name]})
    st.dataframe(pd.DataFrame(rows),width='stretch',hide_index=True)
    monthly=pd.read_csv(ROOT/'reports/monthly_model_audit.csv')
    st.plotly_chart(px.line(monthly,x='month',y='roc_auc',color='model',markers=True,title='Performance by creation month'),width='stretch')
    capacity=pd.read_csv(ROOT/'reports/review_capacity.csv')
    st.plotly_chart(px.line(capacity,x='capacity_share',y='recall',color='model',markers=True,title='Review capacity versus unresolved cases captured'),width='stretch')
    st.subheader('Creation-week block uncertainty')
    st.json(audit['results']['september_october']['week_block_context'])
    st.subheader('Observed feature distributions')
    st.dataframe(pd.read_csv(ROOT/'reports/feature_drift.csv'),width='stretch',hide_index=True)
    st.caption('Predictive utility is not intervention benefit. Few week clusters limit the uncertainty estimates.')

elif page=='Improvement lab':
    st.warning('Mechanical scenario, not a forecast. Resolved cases only; no altered outcomes, queue feedback or employee cost modeled.')
    states=read_table('state_case_durations')
    stage=st.selectbox('Application state to shorten',sorted(states.activity.unique()),index=sorted(states.activity.unique()).index('A_Complete'))
    reduction=st.slider('Assumed reduction in state time (%)',0,50,25,5)/100
    baseline=apps[apps.resolved_at.notna()][['application_id','resolution_days']].merge(states[states.activity==stage][['application_id','days_in_state']],on='application_id',how='left').fillna({'days_in_state':0})
    baseline['scenario_days']=np.maximum(0,baseline.resolution_days-baseline.days_in_state*reduction)
    c1,c2,c3=st.columns(3)
    c1.metric('Observed median',f'{baseline.resolution_days.median():.1f}d')
    c2.metric('Scenario median',f'{baseline.scenario_days.median():.1f}d')
    c3.metric('Application-days removed',f'{(baseline.days_in_state*reduction).sum():,.0f}')
    comparison=pd.DataFrame({'Metric':['Median','90th percentile'],'Observed':[baseline.resolution_days.median(),baseline.resolution_days.quantile(.9)],'Scenario':[baseline.scenario_days.median(),baseline.scenario_days.quantile(.9)]})
    st.plotly_chart(px.bar(comparison,x='Metric',y=['Observed','Scenario'],barmode='group',title='How much could timing change under the assumption?'),width='stretch')
    st.subheader('Randomized pilot sample-size planning')
    from loanflow.decision_support import sample_size_per_arm
    plan=report('pilot_plan.json');p0=plan['historical_baseline']['resolved_30d_rate']
    st.caption(f"Measured baseline: {p0:.1%} resolved by day 30 among mature A_Complete cases still open at day seven.")
    effect=st.slider('Assumed absolute improvement (percentage points)',1,10,5)/100
    n=sample_size_per_arm(p0,effect)
    st.write(f"Normal approximation: {n:,} per arm; {2*n:,} total. At historical volume, approximately {2*n/plan['historical_eligible_per_week']:.1f} recruitment weeks plus 23 days of follow-up after day-seven randomization.")
    st.warning('Effect is hypothetical. Equal independent arms, two-sided alpha=.05, power=.80; no attrition or clustering adjustment. Monitor pending, cancelled and denied outcomes separately.')
    with st.expander('Executive recommendation'):
        st.markdown((ROOT/'reports/EXECUTIVE_MEMO.md').read_text())

elif page=='Data explorer':
    st.subheader('Application-level reporting mart')
    cols=['application_id','created_at','loan_goal','application_type','requested_amount','amount_band','outcome_label','resolution_days','incomplete_count','offer_count']
    st.dataframe(filtered[cols],width='stretch',hide_index=True)
    st.download_button('Export selected applications',filtered[cols].to_csv(index=False),'applications.csv','text/csv')
    q=report('data_quality.json');st.success(f"{len(q['checks'])} integrity checks passed")
    st.dataframe(pd.DataFrame(q['checks']),width='stretch',hide_index=True)
    st.json(q['observations'])
    with st.expander('Verified real-data provenance'):
        st.json(report('source_provenance.json'))
    with st.expander('SQL reporting layer'):
        for file in sorted((ROOT/'sql').glob('*.sql')):
            st.subheader(file.name);st.code(file.read_text(),language='sql')
