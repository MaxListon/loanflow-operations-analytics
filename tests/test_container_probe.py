"""Regression for the actual Docker-forwarded connection-reset startup race."""
from pathlib import Path
import importlib.util
import pytest

PATH=Path(__file__).resolve().parents[1]/'scripts/smoke_container.py'
spec=importlib.util.spec_from_file_location('smoke_container',PATH)
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)


class Ready:
    status=200
    def __enter__(self):return self
    def __exit__(self,*args):return False


def test_connection_reset_is_retried_before_readiness():
    calls=[]
    def opener(url,timeout):
        calls.append(url)
        if len(calls)==1:raise ConnectionResetError('Docker port not ready')
        return Ready()
    probe.wait_for_ready('http://127.0.0.1:8000',attempts=2,interval=0,opener=opener)
    assert len(calls)==2


def test_persistent_startup_failure_does_not_pass():
    def opener(url,timeout):raise ConnectionRefusedError('Not running')
    with pytest.raises(RuntimeError,match='readiness'):
        probe.wait_for_ready('http://127.0.0.1:8000',attempts=2,interval=0,opener=opener)
