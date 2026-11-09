"""Read-only authenticated historical replay API. No applicant eligibility decisions."""
from collections import Counter,deque
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime,timedelta,timezone
import hmac
import json
import logging
import os
from pathlib import Path
import threading
import time
import uuid
from typing import Annotated
from fastapi import Depends,FastAPI,HTTPException,Request,Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials,HTTPBearer
from pydantic import AwareDatetime,BaseModel,ConfigDict,Field,model_validator
from .release import load_active

LOG=logging.getLogger('loanflow.service')
TERMINALS={'A_Pending','A_Cancelled','A_Denied'}


@dataclass(frozen=True)
class Settings:
    releases:Path
    api_key:str
    requests_per_minute:int=120
    max_body_bytes:int=262144

    def __post_init__(self):
        if len(self.api_key)<32:raise ValueError('LOANFLOW_API_KEY must contain at least 32 characters')
        if self.requests_per_minute<1 or self.max_body_bytes<1024:raise ValueError('Invalid service limits')

    @classmethod
    def from_env(cls):
        root=Path(__file__).resolve().parents[2]
        return cls(Path(os.environ.get('LOANFLOW_RELEASES',root/'releases')),os.environ.get('LOANFLOW_API_KEY',''))


class ObservedEvent(BaseModel):
    model_config=ConfigDict(extra='forbid')
    sequence:Annotated[int,Field(strict=True,ge=0)]
    timestamp:AwareDatetime
    activity:Annotated[str,Field(strict=True,min_length=1,max_length=80)]


class ScoreRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    created_at:AwareDatetime
    as_of:AwareDatetime
    events:list[ObservedEvent]=Field(min_length=1,max_length=1000)

    @model_validator(mode='after')
    def temporal_contract(self):
        if self.as_of!=self.created_at+timedelta(days=7):raise ValueError('Scoring is supported exactly at the day-seven landmark')
        if len({e.sequence for e in self.events})!=len(self.events):raise ValueError('Duplicate source sequences')
        if any(not self.created_at<=e.timestamp<self.as_of for e in self.events):raise ValueError('Events must be on/after creation and strictly before day seven')
        if any(e.activity in TERMINALS for e in self.events):raise ValueError('Application already has an operational endpoint')
        if min(e.timestamp for e in self.events)!=self.created_at:raise ValueError('History must include the creation timestamp')
        return self


class ScoreResponse(BaseModel):
    release_id:str
    model:str
    unresolved_by_day30_probability:float=Field(ge=0,le=1)
    state_at_day7:str
    fallback_used:bool
    scoring_time:datetime
    intended_use:str


class Runtime:
    def __init__(self,settings):
        self.settings=settings;self.manifest,self.model=load_active(settings.releases)
        self.window=deque();self.lock=threading.Lock();self.counts=Counter();self.states=Counter();self.latencies=deque(maxlen=10000)

    def admit(self):
        now=time.monotonic()
        with self.lock:
            while self.window and self.window[0]<=now-60:self.window.popleft()
            if len(self.window)>=self.settings.requests_per_minute:return False
            self.window.append(now);return True

    def observe(self,status,elapsed):
        with self.lock:self.counts[status]+=1;self.latencies.append(elapsed)


def create_app(settings=None):
    @asynccontextmanager
    async def lifespan(app):
        # Startup fails closed for missing credentials, corrupt releases or bad config.
        app.state.runtime=Runtime(settings or Settings.from_env())
        yield

    app=FastAPI(title='LoanFlow replay API',version='2.0.0',lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)
    bearer=HTTPBearer(auto_error=False)

    async def authorized(request:Request,credential:Annotated[HTTPAuthorizationCredentials|None,Depends(bearer)]):
        runtime=request.app.state.runtime
        if credential is None or credential.scheme.lower()!='bearer' or not hmac.compare_digest(credential.credentials.encode("utf-8"),runtime.settings.api_key.encode("utf-8")):
            raise HTTPException(401,'Authentication required',headers={'WWW-Authenticate':'Bearer'})
        if not runtime.admit():raise HTTPException(429,'Request limit reached',headers={'Retry-After':'60'})
        return runtime

    @app.middleware('http')
    async def request_envelope(request,call_next):
        started=time.perf_counter();request_id=uuid.uuid4().hex;runtime=getattr(app.state,'runtime',None)
        length=request.headers.get('content-length')
        if length is not None:
            try:too_large=int(length)>runtime.settings.max_body_bytes or int(length)<0
            except ValueError:too_large=True
            if too_large:return JSONResponse({'detail':'Invalid or oversized request'},status_code=413,headers={'X-Request-ID':request_id})
        # Enforce a byte limit for chunked bodies too, before JSON validation.
        if request.method in {'POST','PUT','PATCH'}:
            body=bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body)>runtime.settings.max_body_bytes:return JSONResponse({'detail':'Request too large'},status_code=413,headers={'X-Request-ID':request_id})
            request._body=bytes(body)
        try:response=await call_next(request)
        except Exception:
            # Do not log exception text, request bodies, IDs or credentials.
            LOG.error(json.dumps({'event':'request_failed','request_id':request_id}))
            response=JSONResponse({'detail':'Internal service error'},status_code=500)
        elapsed=time.perf_counter()-started
        if runtime:runtime.observe(response.status_code,elapsed)
        response.headers['X-Request-ID']=request_id;response.headers['Cache-Control']='no-store';response.headers['X-Content-Type-Options']='nosniff'
        route=request.scope.get('route');route_name=getattr(route,'path','unmatched')
        LOG.info(json.dumps({'event':'http_request','request_id':request_id,'route':route_name,'method':request.method,'status':response.status_code,'duration_ms':round(elapsed*1000,3)}))
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request,exc):
        # Default validation errors can echo raw input. Return only field locations.
        return JSONResponse({'detail':'Invalid request','fields':[list(e['loc']) for e in exc.errors()]},status_code=422)

    @app.get('/healthz')
    def health():return {'status':'alive'}

    @app.get('/readyz')
    def ready(request:Request):
        runtime=getattr(request.app.state,'runtime',None)
        if runtime is None:raise HTTPException(503,'Not ready')
        return {'status':'ready','release_id':runtime.manifest['release_id']}

    @app.post('/v1/score',response_model=ScoreResponse)
    def score(payload:ScoreRequest,runtime:Annotated[Runtime,Depends(authorized)]):
        policy=runtime.manifest['policy'];model=runtime.model
        if not datetime.fromisoformat(policy['creation_start'])<=payload.created_at<datetime.fromisoformat(policy['creation_end_exclusive']):
            raise HTTPException(422,'Creation date is outside this historical release scope; train and validate a new release before use on new cohorts')
        if any(e.activity not in model['activities'] for e in payload.events):raise HTTPException(422,'Unknown event activity; review the source contract')
        states=[e for e in payload.events if e.activity.startswith('A_')]
        if not states:raise HTTPException(422,'Application-state history required')
        state=max(states,key=lambda e:(e.timestamp,e.sequence)).activity
        fallback=state not in model['state_rates']
        probability=model['state_rates'].get(state,model['fallback'])
        with runtime.lock:
            runtime.states[state]+=1
            if fallback:runtime.counts['fallback']+=1
        return ScoreResponse(release_id=runtime.manifest['release_id'],model=model['model'],unresolved_by_day30_probability=probability,state_at_day7=state,fallback_used=fallback,scoring_time=payload.as_of,intended_use=policy['intended_use'])

    @app.get('/v1/model')
    def model(runtime:Annotated[Runtime,Depends(authorized)]):
        return {'release_id':runtime.manifest['release_id'],'policy':runtime.manifest['policy'],'model':runtime.model['model'],'training_cases':runtime.model['training_cases']}

    @app.get('/v1/monitor')
    def monitor(runtime:Annotated[Runtime,Depends(authorized)]):
        with runtime.lock:states=dict(runtime.states);fallback=runtime.counts.get('fallback',0)
        n=sum(states.values());expected=runtime.model.get('training_state_distribution',{})
        tvd=.5*sum(abs(states.get(k,0)/n-expected.get(k,0)) for k in set(states)|set(expected)) if n and expected else None
        return {'release_id':runtime.manifest['release_id'],'scored_requests':n,'fallback_count':fallback,
           'state_distribution_total_variation':tvd,'sufficient_demo_volume':n>=100,
           'note':'In-memory, per-process descriptive input monitor. No outcome labels: accuracy and treatment benefit cannot be monitored from requests alone.'}

    @app.get('/metrics',response_class=Response)
    def metrics(runtime:Annotated[Runtime,Depends(authorized)]):
        with runtime.lock:counts=dict(runtime.counts);latencies=list(runtime.latencies)
        lines=['# TYPE loanflow_http_requests_total counter']
        for code,value in sorted((k,v) for k,v in counts.items() if isinstance(k,int)):
            lines.append(f'loanflow_http_requests_total{{status="{code}"}} {value}')
        lines.append(f'loanflow_score_fallback_total {counts.get("fallback",0)}')
        lines.append(f'loanflow_observed_latency_window_count {len(latencies)}')
        if latencies:
            ordered=sorted(latencies);lines.append(f'loanflow_observed_latency_window_p95_seconds {ordered[int((len(ordered)-1)*.95)]}')
        return Response('\n'.join(lines)+'\n',media_type='text/plain; version=0.0.4')

    return app


app=create_app()
