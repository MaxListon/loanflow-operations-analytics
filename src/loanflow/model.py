"""Auditable landmark prediction with chronological model selection."""
import json
import math
import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss, log_loss
from sklearn.calibration import calibration_curve

NUMERIC=['requested_amount','requested_amount_unknown','events_7d','incomplete_7d','validation_7d','offers_7d','resources_7d','days_since_event']
CATEGORICAL=['application_type','loan_goal','state_7d']
FEATURES=NUMERIC+CATEGORICAL


def metrics(y,p):
    y,p=np.asarray(y),np.asarray(p)
    k=max(1,math.ceil(len(y)*.2))
    top=np.argsort(-p,kind='stable')[:k]
    precision=float(y[top].mean())
    return {'n':len(y),'prevalence':float(y.mean()),'roc_auc':float(roc_auc_score(y,p)),
        'average_precision':float(average_precision_score(y,p)),'brier':float(brier_score_loss(y,p)),
        'log_loss':float(log_loss(y,p)),'top20_precision':precision,
        'top20_recall':float(y[top].sum()/y.sum()),'top20_lift':float(precision/y.mean()),'review_count':k}


def prepare():
    return ColumnTransformer([
        ('numeric',Pipeline([('impute',SimpleImputer(strategy='median')),('scale',StandardScaler())]),NUMERIC),
        ('categorical',Pipeline([('impute',SimpleImputer(strategy='most_frequent')),('onehot',OneHotEncoder(handle_unknown='ignore',sparse_output=False))]),CATEGORICAL)
    ])


def train(con,root):
    data=con.execute('SELECT * FROM landmark_features ORDER BY application_id').df()
    subsets={s:data[data.split==s].copy() for s in ['train','validation','test']}
    tr,va,te=[subsets[s] for s in ['train','validation','test']]
    candidates={f'Logistic regression · C={c}':LogisticRegression(C=c,max_iter=2000,random_state=42) for c in [.1,1.,10.]}
    # Small, predeclared challenger grid. Early stopping disabled so no random inner split.
    candidates.update({f'Gradient boosting · leaves={n}':HistGradientBoostingClassifier(max_leaf_nodes=n,max_iter=150,learning_rate=.05,l2_regularization=10,early_stopping=False,random_state=42) for n in [7,15]})
    trials=[];fitted={};best=None;best_name=None;best_loss=float('inf')
    for name,estimator in candidates.items():
        candidate=Pipeline([('prepare',prepare()),('classifier',estimator)])
        candidate.fit(tr[FEATURES],tr.unresolved_30d)
        val=candidate.predict_proba(va[FEATURES])[:,1]
        loss=float(log_loss(va.unresolved_30d,val))
        trials.append({'model':name,'validation_log_loss':loss,'validation_auc':float(roc_auc_score(va.unresolved_30d,val))})
        fitted[name]=candidate
        if loss<best_loss:best,best_name,best_loss=candidate,name,loss
    pred=best.predict_proba(te[FEATURES])[:,1];y=te.unresolved_30d.to_numpy()
    prevalence=float(tr.unresolved_30d.mean());baseline=np.repeat(prevalence,len(te))
    # Smoothed state-only baseline isolates how much value comes from current stage.
    state=tr.groupby('state_7d').unresolved_30d.agg(['sum','count'])
    rates=(state['sum']+20*prevalence)/(state['count']+20)
    state_pred=te.state_7d.map(rates).fillna(prevalence).to_numpy()
    logistic_name=min((t for t in trials if t['model'].startswith('Logistic')),key=lambda t:t['validation_log_loss'])['model']
    logistic=fitted[logistic_name]
    result={'definition':'Unresolved by day 30 among applications still open on day 7','selected_model':best_name,
        'features':FEATURES,'trials':trials,'selection':'Lowest validation log loss; final pipeline kept as fit on training only',
        'splits':{s:{'n':len(d),'created_min':str(d.created_at.min()),'created_max':str(d.created_at.max()),'prevalence':float(d.unresolved_30d.mean())} for s,d in subsets.items()},
        'test':metrics(y,pred),'baseline_test':metrics(y,baseline),'state_baseline_test':metrics(y,state_pred),
        'logistic_test':metrics(y,logistic.predict_proba(te[FEATURES])[:,1])}
    rng=np.random.default_rng(42);auc=[];brier_gain=[]
    for _ in range(500):
        ix=rng.integers(0,len(y),len(y))
        if len(np.unique(y[ix]))<2:continue
        auc.append(roc_auc_score(y[ix],pred[ix]))
        brier_gain.append(np.mean((state_pred[ix]-y[ix])**2)-np.mean((pred[ix]-y[ix])**2))
    result['bootstrap_95']={'roc_auc':np.quantile(auc,[.025,.975]).tolist(),'brier_improvement_over_state_baseline':np.quantile(brier_gain,[.025,.975]).tolist(),'replicates':500,'unit':'application; does not capture calendar-level dependence'}
    observed,expected=calibration_curve(y,pred,n_bins=8,strategy='quantile')
    result['calibration']=[{'predicted':float(p),'observed':float(o)} for p,o in zip(expected,observed)]
    scores=te[['application_id','created_at','landmark_at','state_7d','loan_goal','requested_amount','unresolved_30d']].copy();scores['risk']=pred
    scores.to_csv(root/'reports/test_predictions.csv',index=False)
    con.register('scores',scores);con.execute('CREATE OR REPLACE TABLE test_predictions AS SELECT * FROM scores')
    # Logistic coefficients are explanatory reference, not boosted-model attribution.
    names=logistic.named_steps['prepare'].get_feature_names_out()
    coef=pd.DataFrame({'feature':names,'standardized_log_odds':logistic.named_steps['classifier'].coef_[0]})
    coef.reindex(coef.standardized_log_odds.abs().sort_values(ascending=False).index).to_csv(root/'reports/logistic_coefficients.csv',index=False)
    slices=[]
    for column in ['state_7d','application_type']:
        for key,part in scores.merge(te[['application_id','application_type']],on='application_id',validate='one_to_one').groupby(column):
            if len(part)<100:continue
            slices.append({'dimension':column,'segment':key,'n':len(part),'prevalence':float(part.unresolved_30d.mean()),
                'mean_predicted':float(part.risk.mean()),'brier':float(brier_score_loss(part.unresolved_30d,part.risk))})
    pd.DataFrame(slices).to_csv(root/'reports/model_slice_metrics.csv',index=False)
    result['model_note']='Predictive associations, not creditworthiness or causal effects. Logistic coefficients belong to the logistic reference model only.'
    (root/'reports/model_metrics.json').write_text(json.dumps(result,indent=2))
    joblib.dump(best,root/'data/processed/delay_model.joblib')
    return result
