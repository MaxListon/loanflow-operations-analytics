"""Exercise the built non-root container against a release trained from real data.

A temporary random key is inherited from this Python process, never passed as a
literal command argument or saved to a file. Intended for Docker-enabled CI.
"""
from pathlib import Path
import json
import os
import secrets
import subprocess
import time
import urllib.request
import urllib.error

ROOT=Path(__file__).resolve().parents[1]
secret=secrets.token_urlsafe(48)
env=dict(os.environ,LOANFLOW_API_KEY=secret)
name='loanflow-ci-'+secrets.token_hex(4)
command=['docker','run','--rm','-d','--name',name,'--read-only','--cap-drop=ALL','--security-opt=no-new-privileges',
 '--tmpfs','/tmp:size=16m,noexec,nosuid','-p','127.0.0.1::8000','-e','LOANFLOW_API_KEY',
 '-v',str(ROOT/'releases')+':/releases:ro','loanflow-api:ci']
subprocess.run(command,env=env,check=True,stdout=subprocess.DEVNULL)
try:
    port=subprocess.check_output(['docker','port',name,'8000/tcp'],text=True).strip().rsplit(':',1)[1]
    address='http://127.0.0.1:'+port
    for _ in range(100):
        try:
            with urllib.request.urlopen(address+'/readyz',timeout=1) as r:
                if r.status==200:break
        except (urllib.error.URLError,TimeoutError):pass
        time.sleep(.1)
    else:
        subprocess.run(['docker','logs',name],check=False)
        raise RuntimeError('Non-root container failed readiness')
    payload=(ROOT/'reports/real_replay_request.json').read_bytes()
    request=urllib.request.Request(address+'/v1/score',data=payload,headers={'Authorization':'Bearer '+secret,'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=5) as response:
        result=json.load(response)
        assert response.status==200 and 0<=result['unresolved_by_day30_probability']<=1
    user=subprocess.check_output(['docker','inspect','--format','{{.Config.User}}',name],text=True).strip()
    assert user=='10001:10001'
    print('PASS: non-root, read-only Docker container ready and real-data replay succeeds; release '+result['release_id'])
finally:
    subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
