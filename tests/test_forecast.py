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
            assert report["next_week_illustration"]["available"]
            assert report["next_week_illustration"]["selected_prediction_brl_cents"] == 0


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
    assert report["next_week_illustration"]["status"] == "unavailable"
    assert report["next_week_illustration"]["unavailable_reasons"] == ["known_partial_target_week"]
    assert report["next_week_illustration"]["predictions_brl_cents"] is None
    assert report["next_week_illustration"]["selected_prediction_brl_cents"] is None
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


@pytest.mark.parametrize("ending", [[0] * 4, [1] * 4, [2000, 2000, 0, 0]])
def test_trailing_coverage_signal_suppresses_only_illustration(inputs, ending):
    frame = pd.read_csv(inputs[0])
    frame["revenue_brl_cents"] = [2000] * 20 + ending
    frame["revenue_brl"] = frame.revenue_brl_cents.map(lambda v: f"{v / 100:.2f}")
    rewrite(inputs, frame, category_revenue_brl_cents={"fiction": int(frame.revenue_brl_cents.sum())})
    report = run(*inputs)
    assert report["coverage"]["recent_source_coverage"]["status"] == "suspected_unreliable"
    assert report["next_week_illustration"]["unavailable_reasons"] == ["recent_source_coverage_unreliable"]
    assert report["next_week_illustration"]["predictions_brl_cents"] is None
    assert report["next_week_illustration"]["selected_prediction_brl_cents"] is None
    assert len(report["backtest_predictions"]) == 12
    assert [r["actual_brl_cents"] for r in report["backtest_predictions"]][-4:] == ending
    for method in METHODS:
        expected = metrics([r["actual_brl_cents"] for r in report["backtest_predictions"]],
                           [r["predictions_brl_cents"][method] for r in report["backtest_predictions"]])
        assert report["scores"][method] == expected
    assert report["selection"] == select(report["scores"])


def test_reviewed_october_partial_target_and_zero_tail(inputs):
    # Fictional values/dates reproduce the reported endpoint shape, not Olist records.
    frame = pd.DataFrame({"week_start": pd.date_range("2018-04-30", periods=25, freq="7D").strftime("%Y-%m-%d"),
                          "revenue_brl_cents": [2000] * 20 + [0] * 5,
                          "revenue_brl": ["20.00"] * 20 + ["0.00"] * 5,
                          "partial_week": [False] * 24 + [True]})
    rewrite(inputs, frame, observation_start="2018-04-30", observation_end="2018-10-16",
            category_revenue_brl_cents={"fiction": 40000})
    report = run(*inputs)
    last = report["coverage"]["recent_source_coverage"]["last_4_complete_weeks"][-1]
    assert last["week_start"] == "2018-10-08"
    assert last["revenue_brl_cents"] == 0
    assert last["calendar_complete"] and last["source_completeness"] == "unverified"
    assert last["recorded_value_explanation"] == "zero_recorded_value_cause_unknown"
    illustration = report["next_week_illustration"]
    assert illustration["target_week"] == "2018-10-15"
    assert illustration["unavailable_reasons"] == ["known_partial_target_week", "recent_source_coverage_unreliable"]
    assert illustration["selected_prediction_brl_cents"] is None


@pytest.mark.parametrize("zero_positions", [[0, 1, 2], [18], [23]])
def test_isolated_and_early_zeros_remain_usable(inputs, zero_positions):
    frame = pd.read_csv(inputs[0])
    frame.loc[zero_positions, "revenue_brl_cents"] = 0
    frame["revenue_brl"] = frame.revenue_brl_cents.map(lambda v: f"{v / 100:.2f}")
    rewrite(inputs, frame, category_revenue_brl_cents={"fiction": int(frame.revenue_brl_cents.sum())})
    report = run(*inputs)
    assert report["next_week_illustration"]["available"]
    assert report["coverage"]["recent_source_coverage"]["status"] == "no_truncation_signal_detected"
    assert len(report["coverage"]["zero_weeks"]) == len(zero_positions)


def order_evidence(frame):
    return [{"week_start": row.week_start, "recorded_orders": 1, "eligible_delivered_orders": 1,
             "eligible_items": 1, "status_counts": {"delivered": 1}} for row in frame.itertuples(index=False)]


@pytest.mark.parametrize("cause", ["free_items", "canceled", "absent"])
def test_weekly_order_evidence_distinguishes_recorded_zero_causes(inputs, cause):
    frame = pd.read_csv(inputs[0])
    frame.loc[23, "revenue_brl_cents"] = 0
    frame.loc[23, "revenue_brl"] = 0.0
    evidence = order_evidence(frame)
    if cause != "free_items":
        evidence[-1].update(eligible_delivered_orders=0, eligible_items=0)
        evidence[-1]["status_counts"] = {"canceled": 1} if cause == "canceled" else {}
        evidence[-1]["recorded_orders"] = 1 if cause == "canceled" else 0
    rewrite(inputs, frame, weekly_order_coverage=evidence,
            category_revenue_brl_cents={"fiction": int(frame.revenue_brl_cents.sum())})
    report = run(*inputs)
    last = report["coverage"]["recent_source_coverage"]["last_4_complete_weeks"][-1]
    explanations = {"free_items": "zero_value_eligible_items_recorded", "canceled": "only_ineligible_order_statuses_recorded", "absent": "no_orders_recorded"}
    assert last["recorded_value_explanation"] == explanations[cause]
    assert report["next_week_illustration"]["available"] == (cause == "free_items")
    assert last["source_completeness"] == "unverified"
    assert report["backtest_predictions"][-1]["actual_brl_cents"] == 0


@pytest.mark.parametrize("invalid", ["dates", "negative", "status_sum", "items", "positive_without_orders"])
def test_invalid_coverage_evidence_fails(inputs, invalid):
    frame = pd.read_csv(inputs[0])
    evidence = order_evidence(frame)
    if invalid == "dates":
        evidence[-1]["week_start"] = "2017-01-02"
    elif invalid == "negative":
        evidence[-1]["recorded_orders"] = -1
    elif invalid == "status_sum":
        evidence[-1]["recorded_orders"] = 2
    elif invalid == "items":
        evidence[-1]["eligible_items"] = 0
    else:
        evidence[-1].update(eligible_delivered_orders=0, eligible_items=0, status_counts={"canceled": 1})
    rewrite(inputs, weekly_order_coverage=evidence)
    with pytest.raises(ValidationError):
        run(*inputs)


def test_endpoint_sensitivity_is_fixed_diagnostic_not_selection(inputs):
    report = run(*inputs)
    sensitivity = report["backtest_tail_sensitivity"]
    rows = report["backtest_predictions"]
    assert sensitivity["available"] and not sensitivity["used_for_selection"]
    assert sensitivity["weeks"] == 8
    assert sensitivity["excluded_target_weeks"] == [r["target_week"] for r in rows[-4:]]
    assert sensitivity["end"] == rows[-5]["target_week"]
    for name in METHODS:
        assert sensitivity["scores"][name] == metrics([r["actual_brl_cents"] for r in rows[:-4]],
                                                     [r["predictions_brl_cents"][name] for r in rows[:-4]])
    assert report["selection"] == select(report["scores"])


def test_unavailable_illustration_cli_serializes_null_preserves_files(inputs, tmp_path):
    frame = pd.read_csv(inputs[0])
    frame.loc[23, "partial_week"] = True
    rewrite(inputs, frame, observation_end="2017-06-13")
    originals = [p.read_bytes() for p in inputs]
    output = tmp_path / "guarded.json"
    result = subprocess.run([sys.executable, "-m", "olist.forecast", "--input", str(inputs[0]), "--quality", str(inputs[1]), "--output", str(output)], capture_output=True, check=True, text=True)
    report = json.loads(output.read_text())
    assert report["report_version"] == 2
    assert report["next_week_illustration"]["predictions_brl_cents"] is None
    assert json.loads(result.stdout)["next_week_illustration"]["status"] == "unavailable"
    assert [p.read_bytes() for p in inputs] == originals
