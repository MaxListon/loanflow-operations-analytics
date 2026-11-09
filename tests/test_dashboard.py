"""Exercise database-backed views; raw records are not required in CI."""
from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest

ROOT=Path(__file__).resolve().parents[1]
pytestmark=pytest.mark.skipif(not (ROOT/'data/processed/loanflow.duckdb').exists(),reason='Build pipeline before dashboard integration tests')

@pytest.mark.parametrize('page',['Overview','Real journeys','Process & rework','Early warning','Validation audit','Improvement lab','Data explorer'])
def test_dashboard_views_render_without_exceptions(page):
    at=AppTest.from_file(str(ROOT/'dashboard/app.py'),default_timeout=30).run()
    if page!='Overview':at.sidebar.radio[0].set_value(page).run()
    assert not at.exception
