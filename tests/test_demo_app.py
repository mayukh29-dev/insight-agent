"""Public demo must run without credentials and must not expose Live Mode."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "demo_app.py"


def test_demo_question_is_offline(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not at.exception
    assert "Live Mode" not in [x.value for x in at.radio]
    at.button[0].click().run()
    assert not at.exception
    assert any("Electronics generated the most revenue" in x.value for x in at.markdown)


def test_dashboard_metrics_and_filters():
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    at.radio[0].set_value("Sales Dashboard").run()
    assert not at.exception
    assert [x.value for x in at.metric] == ["$12,951.00", "240", "717"]
    at.multiselect[0].set_value(["Home"]).run()
    assert at.metric[0].value == "$3,882.50"


def test_tableau_link_present():
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    at.radio[0].set_value("Tableau Intelligence").run()
    assert not at.exception
    assert any("embedded dashboard" in x.value for x in at.info)
