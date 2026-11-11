"""Fictional weekly history only; no Olist records or generated data in Git."""
import hashlib
import json
import subprocess
import sys

import pandas as pd
import pytest

from olist.forecast import METHODS, metrics, predict, run, select
from olist.pipeline import FILES, ValidationError, ingest


@pytest.fixture
def inputs(tmp_path):
    weeks = pd.date_range("2017-01-02", periods=24, freq="7D")
    values = [1000 + i * 100 + (i % 3) * 10 for i in range(24)]
    frame = pd.DataFrame({"week_start": weeks.strftime("%Y-%m-%d"), "revenue_brl_cents": values,
                          "revenue_brl": [f"{v / 100:.2f}" for v in values], "partial_week": False})
    quality = {"currency": "BRL", "source": "Olist public historical dataset (2016–2018)",
               "revenue_definition": "delivered-order item prices by purchase timestamp; excludes freight; not net of refunds",
               "week_definition": "Monday through Sunday; naive source local timestamps; no timezone conversion",
               "observation_start": "2017-01-02", "observation_end": "2017-06-18",
               "category_revenue_brl_cents": {"fiction": sum(values)},
               "source_sha256": {filename: "a" * 64 for filename, _ in FILES.values()}}
    paths = tmp_path / "weekly.csv", tmp_path / "quality.json"
    frame.to_csv(paths[0], index=False)
    paths[1].write_text(json.dumps(quality))
    return paths


def rewrite(inputs, frame=None, **changes):
    if frame is not None:
        frame.to_csv(inputs[0], index=False)
    quality = json.loads(inputs[1].read_text())
    quality.update(changes)
    inputs[1].write_text(json.dumps(quality))


def test_report_reconciliation_dates_baselines_and_reproducibility(inputs):
    report = run(*inputs)
    assert report == run(*inputs)
    assert report["reconciliation"]["passed"]
    assert report["evaluation"]["weeks"] == 12
    assert report["evaluation"]["start"] == "2017-03-27"
    assert report["evaluation"]["end"] == "2017-06-12"
    first = report["backtest_predictions"][0]
    assert first["predictions_brl_cents"]["last_week"] == 2120
    assert first["predictions_brl_cents"]["mean_4"] == round((1820 + 1900 + 2010 + 2120) / 4)
    assert all(row["trained_through"] < row["target_week"] for row in report["backtest_predictions"])
    assert report["next_week_illustration"]["target_week"] == "2017-06-19"
    assert report["model"]["final_fit"]["training_samples"] == 20
    json.dumps(report, allow_nan=False)


def test_predictions_do_not_use_target_or_future(inputs):
    before = run(*inputs)
    frame = pd.read_csv(inputs[0])
    # Perturb target and all later values; reconciliation changes, but this origin cannot.
    frame.loc[12:, "revenue_brl_cents"] = 999999
    frame["revenue_brl"] = frame.revenue_brl_cents.map(lambda v: f"{v / 100:.2f}")
    rewrite(inputs, frame, category_revenue_brl_cents={"fiction": int(frame.revenue_brl_cents.sum())})
    after = run(*inputs)
    assert before["backtest_predictions"][0]["predictions_brl_cents"] == after["backtest_predictions"][0]["predictions_brl_cents"]
    assert before["backtest_predictions"][1]["predictions_brl_cents"]["last_week"] != after["backtest_predictions"][1]["predictions_brl_cents"]["last_week"]


def test_metrics_zero_denominator_and_bias():
    assert metrics([100, 300], [200, 100]) == {
        "mae_brl": 1.5, "wape_percent": 75.0, "wape_undefined_reason": None,
        "bias_brl": -0.5, "absolute_error_sum_brl_cents": 300, "weeks": 2}
    zero = metrics([0, 0], [0, 10])
    assert zero["wape_percent"] is None
    assert zero["wape_undefined_reason"]
    with pytest.raises(ValidationError):
        metrics([], [])


def test_ridge_matches_analytic_linear_example():
    predictions, audit = predict([i * 100 for i in range(12)])
    # Eight centered training rows; five collinear standardized features.
    # y_mean=750; next centered contribution=5*8*450/(1+5*8).
    assert predictions["ridge"] == round(750 + 18000 / 41)
    assert predictions["last_week"] == 1100
    assert predictions["mean_4"] == 950
    assert audit["training_samples"] == 8


@pytest.mark.parametrize("errors, winner, verdict", [
    ([1, 2, 3], "last_week", "loses"), ([3, 2, 1], "ridge", "wins"),
    ([2, 1, 1], "mean_4", "ties"), ([0, 0, 0], "last_week", "ties"),
])
def test_selection_honestly_reports_candidate_loss_and_ties(errors, winner, verdict):
    selected = select({name: {"absolute_error_sum_brl_cents": error} for name, error in zip(METHODS, errors)})
    assert selected["method"] == winner
    assert selected["candidate_vs_best_baseline"] == verdict


def test_constant_and_zero_history(inputs):
    for value in [0, 1234]:
        frame = pd.read_csv(inputs[0])
        frame["revenue_brl_cents"] = value
        frame["revenue_brl"] = f"{value / 100:.2f}"
        rewrite(inputs, frame, category_revenue_brl_cents={"fiction": 24 * value})
        report = run(*inputs)
        assert all(score["mae_brl"] == 0 for score in report["scores"].values())
        assert report["selection"]["method"] == "last_week"
        if value == 0:
            assert all(score["wape_percent"] is None for score in report["scores"].values())


def test_sparse_and_outlier_weeks_are_retained(inputs):
    frame = pd.read_csv(inputs[0])
    frame["revenue_brl_cents"] = [0] * 15 + [100000] + [0] * 8
    frame["revenue_brl"] = frame.revenue_brl_cents.map(lambda v: f"{v / 100:.2f}")
    rewrite(inputs, frame, category_revenue_brl_cents={"fiction": 100000})
    report = run(*inputs)
    assert len(report["coverage"]["zero_weeks"]) == 23
    assert "2017-04-17" in report["coverage"]["outlier_weeks"]
    assert len(report["backtest_predictions"]) == 12
    assert report["backtest_predictions"][3]["actual_brl_cents"] == 100000


def test_partial_boundaries_excluded_transparently(inputs):
    frame = pd.read_csv(inputs[0])
    frame.loc[[0, 23], "partial_week"] = True
    rewrite(inputs, frame, observation_start="2017-01-03", observation_end="2017-06-13")
    report = run(*inputs)
    assert report["evaluation"]["weeks"] == 10
    assert report["evaluation"]["training_start"] == "2017-01-09"
    assert report["evaluation"]["end"] == "2017-06-05"
    assert report["next_week_illustration"]["target_week"] == "2017-06-12"
    assert report["next_week_illustration"]["overlaps_excluded_partial_week"]
    # Reconciliation uses even the excluded boundary values.
    assert report["reconciliation"]["weekly_total_brl_cents"] == int(frame.revenue_brl_cents.sum())


@pytest.mark.parametrize("column,value", [
    ("week_start", "bad"), ("week_start", "2017-01-03"),
    ("revenue_brl_cents", "-1"), ("revenue_brl_cents", "nan"),
    ("revenue_brl_cents", "1.2"), ("revenue_brl_cents", "9007199254740992"),
    ("revenue_brl", "NaN"), ("revenue_brl", "Infinity"),
    ("revenue_brl", "-1"), ("revenue_brl", "99.99"),
    ("partial_week", ""), ("partial_week", "unknown"), ("partial_week", "True"),
])
def test_invalid_weekly_fields_fail(inputs, column, value):
    frame = pd.read_csv(inputs[0], dtype=str)
    frame.loc[3, column] = value
    rewrite(inputs, frame)
    with pytest.raises(ValidationError):
        run(*inputs)


@pytest.mark.parametrize("kind", ["gap", "duplicate", "unsorted", "schema", "empty"])
def test_invalid_week_structure(inputs, kind):
    frame = pd.read_csv(inputs[0])
    if kind == "gap":
        frame = frame.drop(3)
    elif kind == "duplicate":
        frame.loc[3, "week_start"] = frame.loc[2, "week_start"]
    elif kind == "unsorted":
        frame = frame.iloc[::-1]
    elif kind == "schema":
        frame = frame.drop(columns="revenue_brl")
    else:
        frame = frame.iloc[:0]
    rewrite(inputs, frame)
    with pytest.raises(ValidationError):
        run(*inputs)


@pytest.mark.parametrize("changes", [
    {"currency": "USD"}, {"category_revenue_brl_cents": {"fiction": 1}},
    {"category_revenue_brl_cents": {"fiction": -1}}, {"category_revenue_brl_cents": {"fiction": True}},
    {"category_revenue_brl_cents": None}, {"source_sha256": {}},
    {"revenue_definition": "payments USD"}, {"week_definition": "Sunday"},
    {"observation_start": "2017-01-09"}, {"observation_end": "bad"},
])
def test_invalid_quality_and_reconciliation_fail(inputs, changes):
    rewrite(inputs, **changes)
    with pytest.raises(ValidationError):
        run(*inputs)


@pytest.mark.parametrize("text", ["{", "[]", "null"])
def test_malformed_quality_json(inputs, text):
    inputs[1].write_text(text)
    with pytest.raises(ValidationError):
        run(*inputs)


def test_insufficient_history(inputs):
    frame = pd.read_csv(inputs[0]).iloc[:15]
    rewrite(inputs, frame, observation_end="2017-04-16", category_revenue_brl_cents={"fiction": int(frame.revenue_brl_cents.sum())})
    with pytest.raises(ValidationError, match="16 complete weeks"):
        run(*inputs)
    with pytest.raises(ValidationError, match="insufficient"):
        predict([1] * 11)


def test_cli_and_provenance_do_not_mutate_inputs(inputs, tmp_path):
    original = [path.read_bytes() for path in inputs]
    output = tmp_path / "forecast_results.json"
    command = [sys.executable, "-m", "olist.forecast", "--input", str(inputs[0]), "--quality", str(inputs[1]), "--output", str(output)]
    subprocess.run(command, check=True, capture_output=True)
    report = json.loads(output.read_text())
    assert report["provenance"]["weekly_input_sha256"] == hashlib.sha256(original[0]).hexdigest()
    assert [path.read_bytes() for path in inputs] == original
    command[-1] = str(inputs[0])
    assert subprocess.run(command, capture_output=True).returncode != 0
    assert [path.read_bytes() for path in inputs] == original


def test_ingestion_to_forecast_contract(tmp_path):
    # Exercise actual Phase 1 output schema and quality report, not just hand-built metadata.
    weeks = pd.date_range("2017-01-02", periods=18, freq="7D")
    tables = {
        "orders": [[f"fiction-{i}", "delivered", str(w)] for i, w in enumerate(weeks)],
        "items": [[f"fiction-{i}", "1", "fiction-product", "10.00", "1.00"] for i in range(18)],
        "products": [["fiction-product", "fiction-category"]],
        "translations": [["fiction-category", "fiction-english"]],
    }
    for name, rows in tables.items():
        filename, columns = FILES[name]
        pd.DataFrame(rows, columns=columns).to_csv(tmp_path / filename, index=False)
    weekly, quality = ingest(tmp_path)
    input_path, quality_path = tmp_path / "weekly.csv", tmp_path / "quality.json"
    weekly.to_csv(input_path, index=False)
    quality_path.write_text(json.dumps(quality))
    result = run(input_path, quality_path)
    assert result["reconciliation"]["weekly_total_brl_cents"] == 18000
    assert result["evaluation"]["weeks"] == 5  # last observed Monday is partial
