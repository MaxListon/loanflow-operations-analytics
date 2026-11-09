"""Exercise the non-root container against a release trained from real data.

The key is generated in memory and inherited through the environment, never
printed, passed as a literal command argument, or written to disk.
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


def wait_for_ready(address,attempts=100,interval=.1,opener=None):
    """Docker's port can reset connections before Uvicorn is ready to accept."""
    opener=opener or urllib.request.urlopen
    for _ in range(attempts):
        try:
            with opener(address+'/readyz',timeout=1) as response:
                if response.status==200:return
        except (urllib.error.URLError,OSError):
            pass
        time.sleep(interval)
    raise RuntimeError('Non-root container failed readiness')


def main():
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
        try:wait_for_ready(address)
        except RuntimeError:
            subprocess.run(['docker','logs',name],check=False)
            raise
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


if __name__=='__main__':main()
