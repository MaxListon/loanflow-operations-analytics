"""Start the actual local API, replay a real source case, and record smoke evidence.

Requires a built pipeline, verified release, and the [api] extra. Credentials are
created in memory for this run and are neither printed nor saved.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import os
import secrets
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import numpy as np
from loanflow.warehouse import connect_warehouse

ROOT=Path(__file__).resolve().parents[1]


def build_real_payload():
    with connect_warehouse(ROOT/'data/processed/loanflow.duckdb',read_only=True) as con:
        case=con.execute("SELECT application_id,created_at,landmark_at,state_7d FROM landmark_features WHERE split='test' ORDER BY application_id LIMIT 1").df().iloc[0]
        events=con.execute('''SELECT source_sequence,event_time,activity FROM events
          WHERE application_id=? AND event_time<? ORDER BY event_time,source_sequence''',[case.application_id,case.landmark_at.to_pydatetime()]).df()
    payload={'created_at':case.created_at.isoformat(),'as_of':case.landmark_at.isoformat(),
      'events':[{'sequence':int(r.source_sequence),'timestamp':r.event_time.isoformat(),'activity':r.activity} for r in events.itertuples()]}
    return str(case.application_id),str(case.state_7d),payload


def main():
    case_id,state,payload=build_real_payload()
    secret=secrets.token_urlsafe(48)
    # Reserve a local ephemeral address, then let Uvicorn bind that selected port.
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    address=f'http://127.0.0.1:{port}'
    env=dict(os.environ,LOANFLOW_API_KEY=secret,LOANFLOW_RELEASES=str(ROOT/'releases'))
    process=subprocess.Popen([sys.executable,'-m','uvicorn','loanflow.service:app','--host','127.0.0.1','--port',str(port),'--no-access-log'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    def request(path,body=None,auth=True):
        headers={'Content-Type':'application/json'}
        if auth:headers['Authorization']='Bearer '+secret
        req=urllib.request.Request(address+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
        try:
            with urllib.request.urlopen(req,timeout=10) as response:return response.status,response.read()
        except urllib.error.HTTPError as exc:return exc.code,exc.read()
    try:
        for _ in range(100):
            if process.poll() is not None:raise RuntimeError('Service process failed to start')
            try:
                if request('/readyz',auth=False)[0]==200:break
            except urllib.error.URLError:pass
            time.sleep(.1)
        else:raise RuntimeError('Service not ready within ten seconds')
        status,response=request('/v1/score',payload);prediction=json.loads(response)
        assert status==200 and prediction['state_at_day7']==state
        assert request('/v1/score',payload,auth=False)[0]==401
        def measure(_):
            start=time.perf_counter();code,_=request('/v1/score',payload);return code,(time.perf_counter()-start)*1000
        with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(measure,range(64)))
        assert all(code==200 for code,_ in results)
        bad=dict(payload,as_of=payload['created_at']);assert request('/v1/score',bad)[0]==422
        assert request('/metrics')[0]==200
        monitor=json.loads(request('/v1/monitor')[1])
        (ROOT/'reports/real_replay_request.json').write_text(json.dumps(payload,indent=2))
        latencies=[r[1] for r in results]
        report={'passed':True,'transport':'Actual Uvicorn process over loopback HTTP','release_id':prediction['release_id'],
          'real_source_application_id':case_id,'event_count':len(payload['events']),'state_at_day7':state,
          'probability':prediction['unresolved_by_day30_probability'],'checks':['ready','authenticated real-case replay','unauthenticated rejection','invalid horizon rejection','protected metrics','aggregate monitor'],
          'local_concurrency_probe':{'requests':64,'workers':8,'successful':sum(code==200 for code,_ in results),'p50_ms':float(np.median(latencies)),'p95_ms':float(np.quantile(latencies,.95))},
          'limitations':'Local smoke/concurrency probe only, not a sustained load test, hosted benchmark or uptime SLO. No public API deployed.'}
        (ROOT/'reports/service_smoke.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2))
    finally:
        process.terminate()
        try:process.wait(timeout=10)
        except subprocess.TimeoutExpired:process.kill();process.wait()


if __name__=='__main__':main()
