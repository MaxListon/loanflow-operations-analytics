"""Verify a cold source rebuild using the existing Python environment."""
from pathlib import Path
import shutil,subprocess,os,json,sys,math,tempfile
root=Path(__file__).resolve().parents[1]
target=Path(tempfile.mkdtemp(prefix='loanflow-reproduction-'))
def ignore(path,names):
 p=Path(path)
 skip={n for n in names if n in ['__pycache__','.pytest_cache','.git'] or n.endswith('.egg-info')}
 if p==root/'data':skip.add('processed')
 if p==root:skip.update(['reports','releases'])
 if p==root/'data/raw':skip.update(n for n in names if n.endswith('.gz'))
 return skip
shutil.copytree(root,target,ignore=ignore,dirs_exist_ok=True)
(target/'reports').mkdir()
shutil.copy2(root/'data/raw/bpi2017.xes.gz',target/'data/raw/bpi2017.xes.gz')
env=dict(os.environ,PYTHONPATH=str(target/'src'),LOKY_MAX_CPU_COUNT='2',OMP_NUM_THREADS='2')
subprocess.run([sys.executable,'-m','loanflow.pipeline'],cwd=target,env=env,check=True)
checks=[]
for name in ['model_metrics.json','robustness.json']:
 original=json.loads((root/'reports'/name).read_text());reproduced=json.loads((target/'reports'/name).read_text())
 def compare(a,b,path=''):
  if isinstance(a,dict):
   assert a.keys()==b.keys(),path
   for key in a:compare(a[key],b[key],path+'/'+key)
  elif isinstance(a,list):
   assert len(a)==len(b),path
   for i,(x,y) in enumerate(zip(a,b)):compare(x,y,path+f'/{i}')
  elif isinstance(a,float):assert math.isclose(a,b,rel_tol=1e-9,abs_tol=1e-10),(path,a,b)
  else:assert a==b,(path,a,b)
 compare(original,reproduced);checks.append(name)
for name in ['state_bottlenecks.csv','improvement_scenarios.csv','pilot_baseline.csv']:
 import pandas as pd
 pd.testing.assert_frame_equal(pd.read_csv(root/'reports'/name),pd.read_csv(target/'reports'/name),rtol=1e-9,atol=1e-10)
 checks.append(name)
report={'passed':True,'method':'Fresh sanitized source directory, no extracted CSVs, no database, no fitted model; rebuilt from checksum-verified original gzip. Existing Python environment reused.','matching_artifacts':checks,'tolerance':{'relative':1e-9,'absolute':1e-10},'fresh_environment_tested':False}
(root/'reports/reproduction_check.json').write_text(json.dumps(report,indent=2))
shutil.rmtree(target)
print('CLEAN REBUILD MATCHES:',checks)
