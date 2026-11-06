"""Exercise the actual UI with Streamlit AppTest. All AI requests stay mocked."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "streamlit_app.py"


def test_demo_ui(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not at.exception
    at.selectbox(key="sample_question").select("Which category generated the most revenue?").run()
    at.button[0].click().run()
    assert not at.exception
    assert any("Electronics generated the most revenue" in item.value for item in at.markdown)
    assert "Demo Mode" in at.radio(key="analysis_mode").value


def test_dashboard_ui_filters_and_empty_state():
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    at.radio(key="workspace").set_value("Sales Dashboard").run()
    assert not at.exception
    assert [item.value for item in at.metric] == ["$12,951.00", "240", "717"]
    at.multiselect(key="categories").set_value(["Home"]).run()
    assert at.metric[0].value == "$3,882.50"
    at.multiselect(key="categories").set_value([]).run()
    assert not at.exception
    assert at.metric[0].value == "$0.00"
    assert any("No transactions" in item.value for item in at.info)


def test_live_ui_calls_existing_agent(monkeypatch):
    calls = []

    def live(question, sales):
        calls.append((question, len(sales)))
        return "Question\nRevenue?\n\nTools executed\ntotal_revenue\n\nKey metrics\n- USD 12951.00"

    monkeypatch.setattr("agent.run_agent", live)
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    at.radio(key="analysis_mode").set_value("Live Mode").run()
    at.text_area(key="question").set_value("Revenue?").run()
    at.button[0].click().run()
    assert not at.exception
    assert calls == [("Revenue?", 240)]


def test_tableau_ui_has_fallback_link():
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    at.radio(key="workspace").set_value("Tableau Intelligence").run()
    assert not at.exception
    assert any("embed stays blank" in item.value for item in at.info)


def test_tableau_embed_uses_fixed_public_view():
    from tableau import TABLEAU_URL, embed_html

    html = embed_html()
    assert TABLEAU_URL in html
    assert "tableau.embedding.3.latest.min.js" in html
    assert "VizLoadError" in html
    assert "Open full dashboard" in html
