"""API/release contracts use explicit synthetic fixtures; never analytical inputs."""
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from loanflow.release import activate,canonical_hash,hash_file,load_active,verify_release
from loanflow.service import create_app,Settings

KEY='unit-test-only-key-12345678901234567890'


def release_fixture(releases,rate=.4):
    staging=releases/'staging';staging.mkdir(parents=True)
    values={
      'state_model.json':{'schema_version':1,'model':'smoothed-state-baseline','fallback':.3,'state_rates':{'A_Complete':rate},'training_cases':100,
        'activities':['A_Create Application','A_Concept','A_Complete','O_Create Offer','A_Pending','A_Denied','A_Cancelled']},
      'metrics.json':{'brier':.2},'source.json':{'synthetic_test_fixture_only':True}}
    for name,value in values.items():(staging/name).write_text(json.dumps(value))
    hashes={name:hash_file(staging/name) for name in values}
    policy={'landmark_days':7,'horizon_days':30,'creation_start':'2016-01-01T00:00:00+00:00','creation_end_exclusive':'2017-01-01T00:00:00+00:00','intended_use':'synthetic fixture in tests only'}
    rid='lf-'+canonical_hash({'files':hashes,'policy':policy})[:20]
    (staging/'manifest.json').write_text(json.dumps({'schema_version':1,'release_id':rid,'files':hashes,'policy':policy}))
    staging.rename(releases/rid);activate(releases,rid);return rid


@pytest.fixture
def releases(tmp_path):
    path=tmp_path/'releases';release_fixture(path);return path


@pytest.fixture
def payload():
    return {'created_at':'2016-01-01T00:00:00Z','as_of':'2016-01-08T00:00:00Z','events':[
      {'sequence':0,'timestamp':'2016-01-01T00:00:00Z','activity':'A_Create Application'},
      {'sequence':1,'timestamp':'2016-01-02T00:00:00Z','activity':'A_Complete'}]}


@pytest.fixture
def client(releases):
    with TestClient(create_app(Settings(releases,KEY))) as c:yield c


def test_authenticated_score_has_probability_release_and_scope(client,payload):
    r=client.post('/v1/score',json=payload,headers={'Authorization':f'Bearer {KEY}'})
    assert r.status_code==200 and r.json()['unresolved_by_day30_probability']==.4
    assert r.json()['model']=='smoothed-state-baseline'
    assert r.headers['X-Request-ID'] and r.headers['Cache-Control']=='no-store'


@pytest.mark.parametrize('path,method',[('/v1/score','post'),('/v1/model','get'),('/metrics','get')])
def test_protected_endpoints_require_credentials(client,payload,path,method):
    r=client.request(method,path,json=payload if method=='post' else None)
    assert r.status_code==401


def test_wrong_key_is_rejected(client,payload):
    assert client.post('/v1/score',json=payload,headers={'Authorization':'Bearer wrong'}).status_code==401


def test_health_and_readiness_are_available_without_key(client):
    assert client.get('/healthz').json()=={'status':'alive'}
    assert client.get('/readyz').json()['status']=='ready'


def test_no_public_documentation_or_openapi(client):
    for path in ['/docs','/openapi.json','/redoc']:assert client.get(path).status_code==404


@pytest.mark.parametrize('change',[
    'naive_timestamp','future_event','exact_landmark_event','duplicate_sequence','terminal_event',
    'wrong_landmark','unknown_field','string_sequence','bool_sequence','outside_release','unknown_activity','missing_creation'])
def test_scoring_rejects_invalid_temporal_or_data_contract(client,payload,change):
    if change=='naive_timestamp':payload['created_at']='2016-01-01T00:00:00'
    if change=='future_event':payload['events'][-1]['timestamp']='2016-01-09T00:00:00Z'
    if change=='exact_landmark_event':payload['events'][-1]['timestamp']=payload['as_of']
    if change=='duplicate_sequence':payload['events'][-1]['sequence']=0
    if change=='terminal_event':payload['events'][-1]['activity']='A_Pending'
    if change=='wrong_landmark':payload['as_of']='2016-01-09T00:00:00Z'
    if change=='unknown_field':payload['eventual_outcome']='secret-test-value'
    if change=='string_sequence':payload['events'][-1]['sequence']='1'
    if change=='bool_sequence':payload['events'][-1]['sequence']=True
    if change=='outside_release':
        payload['created_at']='2026-01-01T00:00:00Z';payload['as_of']='2026-01-08T00:00:00Z'
        for e in payload['events']:e['timestamp']=e['timestamp'].replace('2016','2026')
    if change=='unknown_activity':payload['events'][-1]['activity']='A_Made up'
    if change=='missing_creation':payload['events']=payload['events'][1:]
    r=client.post('/v1/score',json=payload,headers={'Authorization':f'Bearer {KEY}'})
    assert r.status_code==422
    assert 'secret-test-value' not in r.text


def test_unseen_but_known_state_uses_documented_fallback(client,payload):
    payload['events'][-1]['activity']='A_Concept'
    r=client.post('/v1/score',json=payload,headers={'Authorization':f'Bearer {KEY}'})
    assert r.json()['fallback_used'] and r.json()['unresolved_by_day30_probability']==.3


def test_timezone_equivalent_request_is_accepted(client,payload):
    payload['created_at']='2015-12-31T16:00:00-08:00';payload['as_of']='2016-01-07T16:00:00-08:00'
    assert client.post('/v1/score',json=payload,headers={'Authorization':f'Bearer {KEY}'}).status_code==200


def test_request_rate_limit_is_bounded(releases,payload):
    with TestClient(create_app(Settings(releases,KEY,requests_per_minute=1))) as c:
        assert c.post('/v1/score',json=payload,headers={'Authorization':f'Bearer {KEY}'}).status_code==200
        assert c.post('/v1/score',json=payload,headers={'Authorization':f'Bearer {KEY}'}).status_code==429


def test_oversized_request_is_rejected(client):
    r=client.post('/v1/score',content=b'x'*300000,headers={'Authorization':f'Bearer {KEY}','Content-Type':'application/json'})
    assert r.status_code==413


def test_chunked_request_limit_is_enforced(client):
    r=client.post('/v1/score',content=iter([b'x'*140000,b'y'*140000]),headers={'Authorization':f'Bearer {KEY}','Content-Type':'application/json'})
    assert r.status_code==413


def test_logs_do_not_include_input_or_credentials(client,payload,caplog):
    import logging
    with caplog.at_level(logging.INFO,logger='loanflow.service'):
        client.post('/v1/score',json=payload,headers={'Authorization':f'Bearer {KEY}'})
    assert KEY not in caplog.text and 'A_Create Application' not in caplog.text
    assert 'http_request' in caplog.text


def test_metrics_are_observable_and_authenticated(client,payload):
    client.post('/v1/score',json=payload,headers={'Authorization':f'Bearer {KEY}'})
    result=client.get('/metrics',headers={'Authorization':f'Bearer {KEY}'})
    assert result.status_code==200 and 'loanflow_http_requests_total' in result.text


def test_weak_secret_fails_closed(releases):
    with pytest.raises(ValueError,match='32'):Settings(releases,'weak')


def test_missing_release_fails_startup(tmp_path):
    with pytest.raises(FileNotFoundError):
        with TestClient(create_app(Settings(tmp_path,KEY))):pass


def test_corrupt_release_fails_verification_and_does_not_replace_active(releases):
    active=(releases/'CURRENT').read_text().strip()
    other=release_fixture(releases,rate=.7)
    (releases/active/'state_model.json').write_text('{}')
    with pytest.raises(ValueError,match='integrity'):activate(releases,active)
    assert (releases/'CURRENT').read_text().strip()==other


def test_rollback_only_affects_new_processes(releases,payload):
    original=(releases/'CURRENT').read_text().strip()
    with TestClient(create_app(Settings(releases,KEY))) as old:
        newer=release_fixture(releases,rate=.7)
        # Running service is pinned; activation cannot mix model files mid-request.
        assert old.post('/v1/score',json=payload,headers={'Authorization':f'Bearer {KEY}'}).json()['release_id']==original
        with TestClient(create_app(Settings(releases,KEY))) as new:
            assert new.post('/v1/score',json=payload,headers={'Authorization':f'Bearer {KEY}'}).json()['release_id']==newer
        activate(releases,original)
    assert load_active(releases)[0]['release_id']==original


@pytest.mark.parametrize('invalid',['../escape','/tmp/file','', 'a'*81])
def test_release_pointer_rejects_path_traversal(releases,invalid):
    with pytest.raises(ValueError):activate(releases,invalid)


def test_descriptive_monitor_counts_scores_without_retaining_payload(client,payload):
    for _ in range(3):client.post('/v1/score',json=payload,headers={'Authorization':f'Bearer {KEY}'})
    result=client.get('/v1/monitor',headers={'Authorization':f'Bearer {KEY}'}).json()
    assert result['scored_requests']==3 and not result['sufficient_demo_volume']
    assert 'events' not in result and 'application_id' not in result


def test_bad_current_pointer_fails_closed(releases):
    (releases/'CURRENT').write_text('../outside')
    with pytest.raises(ValueError):load_active(releases)


def test_manifest_identity_cannot_be_silently_changed(releases):
    rid=(releases/'CURRENT').read_text().strip();path=releases/rid/'manifest.json'
    manifest=json.loads(path.read_text());manifest['policy']['landmark_days']=8;path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='identity'):verify_release(releases/rid)


def test_concurrent_pipeline_writers_are_rejected(tmp_path):
    from loanflow.build_lock import single_writer
    with single_writer(tmp_path):
        with pytest.raises(RuntimeError,match='build'): 
            with single_writer(tmp_path):pass
    assert not (tmp_path/'.build.lock').exists()


def test_build_lock_is_released_on_failure(tmp_path):
    from loanflow.build_lock import single_writer
    with pytest.raises(RuntimeError):
        with single_writer(tmp_path):raise RuntimeError('test failure')
    assert not (tmp_path/'.build.lock').exists()


def test_release_builder_rejects_failed_data_checks(tmp_path):
    from loanflow.release import create_release
    (tmp_path/'reports').mkdir();(tmp_path/'reports/data_quality.json').write_text(json.dumps({'passed':False,'checks':[]}))
    with pytest.raises(ValueError,match='failed'):create_release(tmp_path)


def test_release_builder_rejects_missing_extraction_manifest(tmp_path):
    from loanflow.release import create_release
    (tmp_path/'reports').mkdir();(tmp_path/'reports/data_quality.json').write_text(json.dumps({'passed':True,'checks':[]}))
    with pytest.raises(ValueError,match='extraction'):create_release(tmp_path)
