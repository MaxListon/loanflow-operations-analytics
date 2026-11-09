"""Immutable, checksummed JSON model releases with atomic activation/rollback."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from .warehouse import connect_warehouse
from .ingest import extract_cache_valid

VERSION_PATTERN=re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}$')


def hash_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def verify_release(directory):
    directory=Path(directory)
    manifest=json.loads((directory/'manifest.json').read_text())
    if manifest.get('schema_version')!=1:raise ValueError('Unsupported release schema')
    if not VERSION_PATTERN.fullmatch(manifest.get('release_id','')):raise ValueError('Invalid release identity')
    if set(manifest.get('files',{}))!={'state_model.json','metrics.json','source.json'}:raise ValueError('Unexpected release file set')
    for name,digest in manifest['files'].items():
        target=directory/name
        if target.is_symlink() or not target.is_file() or hash_file(target)!=digest:raise ValueError('Release integrity mismatch')
    identity=canonical_hash({'files':manifest['files'],'policy':manifest['policy']})[:20]
    if manifest['release_id']!='lf-'+identity:raise ValueError('Release identity mismatch')
    state=json.loads((directory/'state_model.json').read_text())
    rates=[state['fallback'],*state['state_rates'].values()]
    if not all(isinstance(r,(int,float)) and 0<=r<=1 for r in rates):raise ValueError('Invalid model probabilities')
    if set(state['state_rates'])-set(state['activities']):raise ValueError('Model state missing from vocabulary')
    return manifest,state


def activate(releases,release_id):
    releases=Path(releases)
    if not VERSION_PATTERN.fullmatch(release_id):raise ValueError('Invalid release identity')
    directory=releases/release_id
    if directory.is_symlink():raise ValueError('Release symlinks are not permitted')
    verify_release(directory)
    # Each writer gets a unique temp path; os.replace exposes an entire pointer.
    fd,temp=tempfile.mkstemp(prefix='.current-',dir=releases)
    try:
        with os.fdopen(fd,'w') as out:out.write(release_id+'\n');out.flush();os.fsync(out.fileno())
        os.replace(temp,releases/'CURRENT')
    finally:
        if Path(temp).exists():Path(temp).unlink()
    return release_id


def load_active(releases):
    releases=Path(releases);release_id=(releases/'CURRENT').read_text().strip()
    if not VERSION_PATTERN.fullmatch(release_id):raise ValueError('Invalid active release identity')
    directory=releases/release_id
    if directory.is_symlink():raise ValueError('Release symlinks are not permitted')
    manifest,state=verify_release(directory)
    if manifest['release_id']!=release_id:raise ValueError('Active pointer mismatch')
    return manifest,state


def create_release(root,releases=None):
    root=Path(root);releases=Path(releases or root/'releases');releases.mkdir(parents=True,exist_ok=True)
    checks=json.loads((root/'reports/data_quality.json').read_text())
    if not checks.get('passed') or any(r['violations'] for r in checks['checks']):raise ValueError('Cannot release failed analytical checks')
    if not extract_cache_valid(root/'data/raw/bpi2017.xes.gz',root/'data/processed'):raise ValueError('Source extraction integrity failed')
    source=json.loads((root/'reports/source_provenance.json').read_text())
    actual_md5=hashlib.md5((root/'data/raw/bpi2017.xes.gz').read_bytes()).hexdigest()
    if not source['checksum_matches'] or source['actual_md5']!=actual_md5 or actual_md5!=source['publisher_md5']:raise ValueError('Source provenance does not match actual input')
    with connect_warehouse(root/'data/processed/loanflow.duckdb',read_only=True) as con:
        built=json.loads((root/'reports/build_manifest.json').read_text())
        if built.get('warehouse_sha256')!=hash_file(root/'data/processed/loanflow.duckdb'):raise ValueError('Warehouse differs from the verified build')
        table=con.execute("SELECT state_7d,sum(unresolved_30d) unresolved,count(*) n FROM landmark_features WHERE split='train' GROUP BY state_7d").fetchall()
        prevalence=sum(r[1] for r in table)/sum(r[2] for r in table)
        activities=[r[0] for r in con.execute('SELECT DISTINCT activity FROM events ORDER BY activity').fetchall()]
    state={'schema_version':1,'model':'smoothed-state-baseline','fallback':prevalence,
       'state_rates':{r[0]:(r[1]+20*prevalence)/(r[2]+20) for r in table},'training_state_distribution':{r[0]:r[2]/sum(x[2] for x in table) for r in table},'smoothing_pseudo_count':20,
       'training_cases':sum(r[2] for r in table),'activities':activities}
    policy={'landmark_days':7,'horizon_days':30,'creation_start':'2016-01-01T00:00:00+00:00',
       'creation_end_exclusive':'2017-01-01T00:00:00+00:00','intended_use':'historical operational-support replay; not credit eligibility',
       'selection_reason':'State-only probabilities avoid uncertain mutable trace context; history-only boosting did not improve Brier score consistently.'}
    with tempfile.TemporaryDirectory(prefix='.release-',dir=releases) as temp:
        stage=Path(temp)
        for name,value in [('state_model.json',state),('metrics.json',json.loads((root/'reports/model_metrics.json').read_text())['state_baseline_test']),('source.json',source)]:
            (stage/name).write_text(json.dumps(value,indent=2,sort_keys=True))
        hashes={name:hash_file(stage/name) for name in ['state_model.json','metrics.json','source.json']}
        release_id='lf-'+canonical_hash({'files':hashes,'policy':policy})[:20]
        manifest={'schema_version':1,'release_id':release_id,'files':hashes,'policy':policy,
           'created_at_utc':datetime.now(timezone.utc).isoformat()}
        (stage/'manifest.json').write_text(json.dumps(manifest,indent=2))
        verify_release(stage)
        destination=releases/release_id
        if destination.exists():verify_release(destination)
        else:os.replace(stage,destination)
    activate(releases,release_id)
    return release_id


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[2])
    parser.add_argument('--activate',help='Activate an existing verified release (rollback); restart API afterward')
    args=parser.parse_args()
    result=activate(args.root/'releases',args.activate) if args.activate else create_release(args.root)
    print(result)


if __name__=='__main__':main()
