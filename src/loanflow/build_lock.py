"""Prevent two local pipeline writers from publishing inconsistent work artifacts."""
from contextlib import contextmanager
from datetime import datetime,timezone
import json
import os
from pathlib import Path


@contextmanager
def single_writer(root):
    path=Path(root)/'.build.lock'
    try:fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    except FileExistsError:raise RuntimeError('Another build is active, or a crashed build left .build.lock; verify no build is running before removing it') from None
    try:
        with os.fdopen(fd,'w') as out:json.dump({'pid':os.getpid(),'started_at':datetime.now(timezone.utc).isoformat()},out)
        yield
    finally:path.unlink(missing_ok=True)
