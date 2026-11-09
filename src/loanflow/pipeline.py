"""One-command reproducible build, with failure on data integrity violations."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import time
import duckdb
from .build_lock import single_writer
from .warehouse import connect_warehouse
from .ingest import acquire,extract,extract_cache_valid
from .quality import run_checks
from .analysis import analyze
from .model import train
from .presentation import build_demo,write_memo
from .robustness import run_robustness
from .decision_support import build_decision_support,sha256

ROOT=Path(__file__).resolve().parents[2]


def _run():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh-extract',action='store_true',help='Reparse source even when CSVs exist')
    args=parser.parse_args()
    os.chdir(ROOT)
    start=time.monotonic()
    for sub in ['data/raw','data/processed','reports']:(ROOT/sub).mkdir(parents=True,exist_ok=True)
    source=acquire(ROOT)
    print('Source checksum verified.',flush=True)
    if args.refresh_extract or not extract_cache_valid(source,ROOT/'data/processed'):
        print('Extracted:',extract(source,ROOT/'data/processed'),flush=True)
    con=connect_warehouse(ROOT/'data/processed/loanflow.duckdb')
    for path in sorted((ROOT/'sql').glob('*.sql')):
        con.execute(path.read_text());print('SQL:',path.name,flush=True)
    quality=run_checks(con,ROOT);print(f"Integrity: {len(quality['checks'])} checks passed.",flush=True)
    summary=analyze(con,ROOT);print('Business analysis complete.',flush=True)
    model=train(con,ROOT);print('Selected model:',model['selected_model'],flush=True)
    robustness=run_robustness(con,ROOT);print('Frozen-model robustness and November audit complete.',flush=True)
    evidence=build_decision_support(con,ROOT);print('Journey evidence, competing outcomes and source provenance complete.',flush=True)
    build_demo(con,ROOT,summary,model,quality)
    write_memo(ROOT,summary,model,quality)
    (ROOT/'reports/build_manifest.json').write_text(json.dumps({'built_at_utc':datetime.now(timezone.utc).isoformat(),'source_md5':'10b37a2f78e870d78406198403ff13d2','python':platform.python_version(),'duckdb':duckdb.__version__,'elapsed_seconds':round(time.monotonic()-start,2),'random_seed':42},indent=2))
    con.close()
    build_path=ROOT/'reports/build_manifest.json'
    build_info=json.loads(build_path.read_text());build_info['warehouse_sha256']=sha256(ROOT/'data/processed/loanflow.duckdb')
    build_path.write_text(json.dumps(build_info,indent=2))
    (ROOT/'reports/artifact_hashes.json').write_text(json.dumps({str(p.relative_to(ROOT)):sha256(p) for folder in ['sql','src/loanflow','reports'] for p in sorted((ROOT/folder).glob('*')) if p.is_file() and p.name not in ['artifact_hashes.json','validation_summary.json']},indent=2))
    print('Complete. Open dashboard/index.html or run streamlit run dashboard/app.py',flush=True)


def main():
    with single_writer(ROOT):
        _run()


if __name__=='__main__':main()
