"""Dashboard contracts over tiny fictional derived files; no raw Olist data."""
import json
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from test_forecast import inputs
from olist import dashboard as view
from olist.forecast import run

APP = Path(__file__).resolve().parents[1] / "streamlit_app.py"


@pytest.fixture
def bundle(inputs):
    directory = inputs[0].parent
    inputs[0].rename(directory / "weekly_revenue.csv")
    inputs[1].rename(directory / "quality_report.json")
    generate(directory)
    return directory


def generate(directory):
    report = run(directory / "weekly_revenue.csv", directory / "quality_report.json")
    (directory / "forecast_results.json").write_text(json.dumps(report), encoding="utf-8")
    return report


def load(directory):
    return view.validate_dashboard(directory, view.snapshot(directory))


def edit_report(directory, mutate):
    path = directory / "forecast_results.json"
    report = json.loads(path.read_text())
    mutate(report)
    path.write_text(json.dumps(report))


def partial_bundle(directory):
    path = directory / "weekly_revenue.csv"
    frame = pd.read_csv(path)
    frame.loc[23, "partial_week"] = True
    frame.to_csv(path, index=False)
    quality_path = directory / "quality_report.json"
    quality = json.loads(quality_path.read_text())
    quality["observation_end"] = "2017-06-13"
    quality_path.write_text(json.dumps(quality))
    return generate(directory)


def ui(monkeypatch, directory):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(view, "DEFAULT_DIRECTORY", directory)
    at = AppTest.from_file(str(APP), default_timeout=30)
    at.session_state["workspace"] = "Olist historical forecasts"
    return at.run()


def test_load_no_training_and_target_alignment_brl(bundle, monkeypatch):
    monkeypatch.setattr("olist.forecast.predict", lambda *_args: pytest.fail("Dashboard must not train"))
    frame, _, report = load(bundle)
    series = view.series_data(frame, report, ["last_week", "ridge"], "2017-01-02", "2017-06-12")
    predictions = series.loc[series.Kind.eq("Prediction")]
    first = report["backtest_predictions"][0]
    first_week = predictions.loc[predictions.Week.eq(pd.Timestamp(first["target_week"]))]
    assert first_week["Revenue · BRL"].tolist() == [first["predictions_brl_cents"][m] / 100 for m in ["last_week", "ridge"]]
    assert len(predictions) == 24
    assert set(predictions.Phase) == {"Rolling backtest"}
    assert len(series.loc[series.Phase.eq("Initial training")]) == 12
    assert not series.Week.eq(pd.Timestamp(report["next_week_illustration"]["target_week"])).any()
    chart = view.revenue_chart(series).to_dict()
    assert chart["layer"][0]["encoding"]["x"]["field"] == "Week"
    assert "BRL" in chart["layer"][0]["encoding"]["y"]["title"]


def test_filtering_ranking_and_partial_actuals(bundle):
    partial_bundle(bundle)
    frame, _, report = load(bundle)
    table = view.score_table(report)
    assert table.iloc[0]["Method"] == view.LABELS[report["selection"]["method"]]
    series = view.series_data(frame, report, [], "2017-06-12", "2017-06-12", include_training=False)
    assert len(series) == 1
    assert series.iloc[0].Phase == "Excluded partial week"
    assert series.iloc[0].Series == "Recorded actual"
    assert report["next_week_illustration"]["predictions_brl_cents"] is None
    assert view.series_data(frame, report, [], "2018-01-01", "2018-02-01").empty


@pytest.mark.parametrize("name", view.FILENAMES)
def test_missing_and_corrupt_files_fail_cleanly(bundle, name):
    path = bundle / name
    path.write_text("broken file")
    with pytest.raises(view.DashboardError):
        load(bundle)
    path.unlink()
    with pytest.raises(view.DashboardError):
        view.snapshot(bundle)


@pytest.mark.parametrize("change", [
    lambda r: r.update(report_version=1),
    lambda r: r.update(currency="USD"),
    lambda r: r["provenance"].update(forecast_code_sha256="0" * 64),
    lambda r: r["provenance"].update(weekly_input_sha256="0" * 64),
    lambda r: r["provenance"].update(quality_input_sha256="0" * 64),
    lambda r: r["reconciliation"].update(passed=False),
    lambda r: r["backtest_predictions"][0].update(target_week="2017-03-20"),
    lambda r: r["backtest_predictions"][0].update(trained_through="2017-03-27"),
    lambda r: r["backtest_predictions"][0].update(actual_brl_cents=0),
    lambda r: r["backtest_predictions"][0]["predictions_brl_cents"].update(ridge=-1),
    lambda r: r["scores"]["ridge"].update(mae_brl=0),
    lambda r: r["selection"].update(method="invented"),
    lambda r: r["evaluation"].update(weeks=100),
    lambda r: r["coverage"].update(zero_weeks=["2017-01-02"]),
    lambda r: r["next_week_illustration"].update(selected_prediction_brl_cents=float("nan")),
])
def test_outdated_inconsistent_and_unsafe_reports_rejected(bundle, change):
    edit_report(bundle, change)
    with pytest.raises(view.DashboardError):
        load(bundle)


def test_cannot_reenable_suppressed_forecast(bundle):
    report = partial_bundle(bundle)
    for forged in [
        {"available": True, "status": "illustrative_only", "unavailable_reasons": []},
        {"predictions_brl_cents": {n: 0 for n in view.LABELS}, "selected_prediction_brl_cents": 0},
    ]:
        edit_report(bundle, lambda r: r["next_week_illustration"].update(forged))
        with pytest.raises(view.DashboardError):
            load(bundle)
        (bundle / "forecast_results.json").write_text(json.dumps(report))


def test_files_change_invalidates_snapshot(bundle):
    contents = view.snapshot(bundle)
    path = bundle / "quality_report.json"
    path.write_text(path.read_text() + " ")
    with pytest.raises(view.DashboardError):
        view.validate_dashboard(bundle, contents)


def test_optional_dependencies_error_is_safe(bundle, monkeypatch):
    def unavailable():
        raise ImportError("optional module")
    monkeypatch.setattr(view, "producer", unavailable)
    with pytest.raises(view.DashboardError, match="dependencies"):
        load(bundle)


def test_historical_ui_key_free_filters_and_usd_separation(bundle, monkeypatch):
    # Independent of synthetic CSV: selecting this page must never read sales data.
    monkeypatch.setattr("tools.load_sales", lambda *_args: pytest.fail("USD loader called"))
    at = ui(monkeypatch, bundle)
    assert not at.exception
    assert at.title[0].value == "How well did past weeks predict the next?"
    assert at.metric[0].value == "24"
    assert at.metric[1].value == "12"
    assert at.dataframe[0].value.iloc[0]["Rank"] == 1
    assert not any("USD" in m.label for m in at.metric)
    assert any("Illustrative prediction" in m.label for m in at.metric)
    scores_before = at.dataframe[0].value.copy()
    at.multiselect(key="olist_methods").set_value([]).run()
    at.toggle(key="olist_training").set_value(False).run()
    at.toggle(key="olist_chart_evidence").set_value(True).run()
    assert not at.exception
    pd.testing.assert_frame_equal(scores_before, at.dataframe[0].value)
    assert set(at.dataframe[1].value.Series) == {"Recorded actual"}
    assert "Initial training" not in set(at.dataframe[1].value.Phase)


def test_unavailable_ui_has_no_forecast_amount(bundle, monkeypatch):
    partial_bundle(bundle)
    at = ui(monkeypatch, bundle)
    assert not at.exception
    assert any("Unavailable for 2017-06-12" in w.value for w in at.warning)
    assert not any("Illustrative prediction" in m.label for m in at.metric)
    assert any("incomplete boundary" in m.value for m in at.markdown)


def test_unreliable_tail_ui_blocks_illustration_without_partial_target(bundle, monkeypatch):
    path = bundle / "weekly_revenue.csv"
    frame = pd.read_csv(path)
    frame.loc[20:, ["revenue_brl_cents", "revenue_brl"]] = 0
    frame.to_csv(path, index=False)
    quality_path = bundle / "quality_report.json"
    quality = json.loads(quality_path.read_text())
    quality["category_revenue_brl_cents"] = {"fiction": int(frame.revenue_brl_cents.sum())}
    quality_path.write_text(json.dumps(quality))
    report = generate(bundle)
    assert not report["next_week_illustration"]["overlaps_excluded_partial_week"]
    at = ui(monkeypatch, bundle)
    assert not at.exception
    assert any("Unavailable for" in w.value for w in at.warning)
    assert any("Recent coverage looks unreliable" in m.value for m in at.markdown)
    assert not any("Illustrative prediction" in m.label for m in at.metric)
    assert at.metric[1].value == "12"  # no silent removal of troublesome backtest weeks


def test_missing_data_ui_and_recovery_on_refresh(bundle, monkeypatch):
    forecast = bundle / "forecast_results.json"
    contents = forecast.read_bytes()
    forecast.unlink()
    at = ui(monkeypatch, bundle)
    assert not at.exception and at.info
    assert "olist.forecast" in at.code[0].value
    assert not at.metric
    forecast.write_bytes(contents)
    at.run()
    assert not at.exception and at.metric
    forecast.write_text("corrupt")
    at.run()
    assert not at.exception and at.info and not at.metric


def test_zero_wape_ui_and_optional_dependency_fallback(bundle, monkeypatch):
    path = bundle / "weekly_revenue.csv"
    frame = pd.read_csv(path)
    frame["revenue_brl_cents"] = 0
    frame["revenue_brl"] = "0.00"
    frame.to_csv(path, index=False)
    quality_path = bundle / "quality_report.json"
    quality = json.loads(quality_path.read_text())
    quality["category_revenue_brl_cents"] = {"fiction": 0}
    quality_path.write_text(json.dumps(quality))
    generate(bundle)
    at = ui(monkeypatch, bundle)
    at.segmented_control(key="olist_error_metric").set_value("WAPE · %").run()
    assert not at.exception
    assert any("WAPE is unavailable" in i.value for i in at.info)
    def unavailable():
        raise ImportError("test dependency missing")
    monkeypatch.setattr(view, "producer", unavailable)
    # Different file bytes force content-based validation rather than a cached result.
    quality_path.write_text(quality_path.read_text() + " ")
    at.run()
    assert not at.exception
    assert any("dependencies" in i.value for i in at.info)


def test_optional_feature_failure_leaves_original_demo_working(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    def unavailable():
        raise ImportError("optional feature")
    monkeypatch.setattr(view, "producer", unavailable)
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    at.radio(key="workspace").set_value("Sales Dashboard").run()
    assert not at.exception
    assert [m.value for m in at.metric] == ["$12,951.00", "240", "717"]
