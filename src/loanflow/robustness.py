"""Frozen-model temporal audits, trace-attribute ablation and week-block uncertainty."""
import json
import math
import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder,StandardScaler
from sklearn.metrics import roc_auc_score,brier_score_loss
from .model import FEATURES,metrics

HISTORY_NUMERIC=['events_7d','incomplete_7d','validation_7d','offers_7d','resources_7d','days_since_event']
HISTORY_CATEGORICAL=['state_7d']
HISTORY_FEATURES=HISTORY_NUMERIC+HISTORY_CATEGORICAL


def week_block_bootstrap(y,p,baseline,weeks,iterations=500,seed=42):
    """Resample entire creation-week clusters, preserving within-week dependence."""
    y,p,baseline,weeks=map(np.asarray,(y,p,baseline,weeks))
    groups=[np.flatnonzero(weeks==week) for week in np.unique(weeks)]
    if len(groups)<2:raise ValueError('At least two creation-week clusters required')
    rng=np.random.default_rng(seed);aucs=[];gains=[]
    for _ in range(iterations):
        selected=rng.integers(0,len(groups),len(groups))
        ix=np.concatenate([groups[i] for i in selected])
        if np.unique(y[ix]).size<2:continue
        aucs.append(roc_auc_score(y[ix],p[ix]))
        gains.append(brier_score_loss(y[ix],baseline[ix])-brier_score_loss(y[ix],p[ix]))
    return {'clusters':len(groups),'replicates':len(aucs),'roc_auc_95':np.quantile(aucs,[.025,.975]).tolist(),
        'brier_gain_over_state_95':np.quantile(gains,[.025,.975]).tolist(),
        'limitation':'Few calendar clusters; percentile interval is a sensitivity diagnostic, not external validation.'}


def capacity_curve(y,p,shares=(.05,.1,.2,.3,.4,.5)):
    y,p=np.asarray(y),np.asarray(p);order=np.argsort(-p,kind='stable');rows=[]
    for share in shares:
        k=math.ceil(len(y)*share);selected=y[order[:k]];positive=float(selected.sum())
        rows.append({'capacity_share':share,'review_count':k,'precision':float(selected.mean()),
         'recall':positive/float(y.sum()),'lift':float(selected.mean()/y.mean()),'unresolved_captured':int(positive)})
    return rows


def run_robustness(con,root):
    data=con.execute('SELECT * FROM landmark_features ORDER BY application_id').df()
    tr=data[data.split=='train'].copy();test=data[data.split=='test'].copy()
    nov=data[(data.created_at>=pd.Timestamp('2016-11-01',tz='UTC'))&(data.created_at<pd.Timestamp('2016-12-01',tz='UTC'))].copy()
    reference=joblib.load(root/'data/processed/delay_model.joblib')
    transformer=ColumnTransformer([
      ('numeric',Pipeline([('impute',SimpleImputer(strategy='median')),('scale',StandardScaler())]),HISTORY_NUMERIC),
      ('categorical',OneHotEncoder(handle_unknown='ignore',sparse_output=False),HISTORY_CATEGORICAL)])
    history=Pipeline([('prepare',transformer),('classifier',HistGradientBoostingClassifier(max_leaf_nodes=7,max_iter=150,learning_rate=.05,l2_regularization=10,early_stopping=False,random_state=42))])
    history.fit(tr[HISTORY_FEATURES],tr.unresolved_30d)
    prevalence=float(tr.unresolved_30d.mean());state=tr.groupby('state_7d').unresolved_30d.agg(['sum','count'])
    rates=(state['sum']+20*prevalence)/(state['count']+20)
    results={};monthly=[];predictions=[]
    for period,part in [('september_october',test),('november_audit',nov)]:
        y=part.unresolved_30d.to_numpy();context_p=reference.predict_proba(part[FEATURES])[:,1]
        history_p=history.predict_proba(part[HISTORY_FEATURES])[:,1];state_p=part.state_7d.map(rates).fillna(prevalence).to_numpy()
        weeks=part.created_at.dt.strftime('%G-%V').to_numpy()
        results[period]={'context_model':metrics(y,context_p),'history_only':metrics(y,history_p),'state_only':metrics(y,state_p),
            'week_block_context':week_block_bootstrap(y,context_p,state_p,weeks),
            'week_block_history':week_block_bootstrap(y,history_p,state_p,weeks)}
        for month,positions in part.groupby(part.created_at.dt.strftime('%Y-%m')).indices.items():
            for name,p in [('Context model',context_p),('History only',history_p),('State only',state_p)]:
                met=metrics(y[positions],p[positions]);monthly.append({'month':month,'model':name,**met,'mean_predicted':float(p[positions].mean())})
        scored=part[['application_id','created_at','state_7d','unresolved_30d']].copy()
        scored['context_risk']=context_p;scored['history_risk']=history_p;scored['state_risk']=state_p;scored['evaluation_period']=period
        predictions.append(scored)
        if period=='september_october':
            rows=[]
            for name,p in [('Context model',context_p),('History only',history_p),('State only',state_p)]:
                rows.extend({'model':name,**r} for r in capacity_curve(y,p))
            pd.DataFrame(rows).to_csv(root/'reports/review_capacity.csv',index=False)
    scored=pd.concat(predictions,ignore_index=True)
    scored.to_csv(root/'reports/robustness_predictions.csv',index=False)
    con.register('audit_scores',scored);con.execute('CREATE OR REPLACE TABLE robustness_predictions AS SELECT * FROM audit_scores')
    pd.DataFrame(monthly).to_csv(root/'reports/monthly_model_audit.csv',index=False)
    # Compare feature distributions against training without significance fishing.
    drift=[]
    for column in HISTORY_NUMERIC:
        for name,part in [('Train',tr),('Sep–Oct',test),('November',nov)]:
            values=part[column].astype(float)
            drift.append({'feature':column,'period':name,'n':len(values),'median':float(values.median()),'p90':float(values.quantile(.9)),'missing_rate':float(values.isna().mean())})
    pd.DataFrame(drift).to_csv(root/'reports/feature_drift.csv',index=False)
    result={'protocol':'docs/UPGRADE_PROTOCOL.md','history_features':HISTORY_FEATURES,'fixed_settings':{'max_leaf_nodes':7,'max_iter':150,'learning_rate':.05,'l2_regularization':10},
      'selection_note':'Ablation and November audit are additional diagnostics. No model settings selected on these outcomes; November operational aggregates were previously inspected.',
      'results':results,'recommendation':'Use history-only inputs when creation-time immutability of trace context cannot be established. Predictive differences do not measure intervention effects.'}
    (root/'reports/robustness.json').write_text(json.dumps(result,indent=2))
    joblib.dump(history,root/'data/processed/history_only_model.joblib')
    return result
