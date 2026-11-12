"""Read-only dashboard adapter. Never fit models or silently repair derived files."""
import hashlib
import importlib
import json
from pathlib import Path
from typing import cast

import pandas as pd

DEFAULT_DIRECTORY = Path(__file__).resolve().parents[1] / "data" / "olist" / "processed"
FILENAMES = ("weekly_revenue.csv", "quality_report.json", "forecast_results.json")
LABELS = {"last_week": "Last week", "mean_4": "Four-week mean", "ridge": "Ridge regression"}


class DashboardError(ValueError):
    """Derived files or optional dependencies are not ready for display."""


def producer():
    return importlib.import_module("olist.forecast")


def snapshot(directory):
    try:
        return tuple((Path(directory) / name).read_bytes() for name in FILENAMES) + (
            Path(__file__).with_name("forecast.py").read_bytes(),)
    except OSError as exc:
        raise DashboardError("The three local derived files are missing or unreadable.") from exc


def validate_dashboard(directory, contents):
    """Check provenance, target alignment, scores and guards without retraining."""
    try:
        f = producer()  # Lazy import: optional forecasting never affects 1.0 pages.
        directory = Path(directory)
        frame, quality, reconciliation = f.load_inputs(directory / FILENAMES[0], directory / FILENAMES[1])
        def reject_constant(_value):
            raise ValueError("Nonfinite JSON value")
        report = json.loads(contents[2], parse_constant=reject_constant)
        check = f.require
        check(report["report_version"] == 2 and report["currency"] == "BRL" and report["horizon_weeks"] == 1, "Unsupported report schema or currency")
        sha = lambda value: hashlib.sha256(value).hexdigest()
        provenance = report["provenance"]
        check(provenance["weekly_input_sha256"] == sha(contents[0]) and provenance["quality_input_sha256"] == sha(contents[1]), "Report belongs to different input files; regenerate it")
        check(provenance["forecast_code_sha256"] == sha(contents[3]), "Report uses outdated forecasting code; regenerate it")
        check(provenance["source_sha256"] == quality["source_sha256"], "Source fingerprints disagree")
        check(report["reconciliation"] == reconciliation, "Reconciliation disagrees")
        check(report["source_timeframe"] == {"start": quality["observation_start"], "end": quality["observation_end"]}, "Historical dates disagree")
        check(report["revenue_definition"] == quality["revenue_definition"], "Revenue definition disagrees")
        complete = frame.loc[~frame.partial_week].reset_index(drop=True)
        check(len(complete) >= f.MIN_HISTORY + f.MIN_EVALUATION, "Insufficient history")
        rows = report["backtest_predictions"]
        check(isinstance(rows, list) and len(rows) == len(complete) - f.MIN_HISTORY, "Backtest length disagrees")
        for i, row in enumerate(rows, f.MIN_HISTORY):
            check(row["target_week"] == complete.week_start.iloc[i].date().isoformat(), "Prediction target weeks are misaligned")
            check(row["trained_through"] == complete.week_start.iloc[i - 1].date().isoformat() and row["history_weeks"] == i, "Training dates disagree")
            check(type(row["actual_brl_cents"]) is int and row["actual_brl_cents"] == int(complete.revenue_brl_cents.iloc[i]), "Backtest actuals disagree")
            check(set(row["predictions_brl_cents"]) == set(f.METHODS), "Missing prediction methods")
            for value in row["predictions_brl_cents"].values():
                f.nonnegative_int(value, "Prediction")
        scores = {name: f.metrics([r["actual_brl_cents"] for r in rows], [r["predictions_brl_cents"][name] for r in rows]) for name in f.METHODS}
        check(report["scores"] == scores, "Reported errors disagree with predictions")
        check(report["selection"] == f.select(scores), "Model selection disagrees with errors")
        evaluation = report["evaluation"]
        check(evaluation["weeks"] == len(rows) and evaluation["start"] == rows[0]["target_week"] and evaluation["end"] == rows[-1]["target_week"], "Evaluation window disagrees")
        check(evaluation["training_start"] == complete.week_start.iloc[0].date().isoformat(), "Training window disagrees")
        recent = f.recent_coverage(complete, quality)
        check(report["coverage"] == {**f.coverage(frame), "recent_source_coverage": recent}, "Coverage diagnostics disagree")
        check(report["backtest_tail_sensitivity"] == f.tail_sensitivity(rows), "Sensitivity diagnostics disagree")
        illustration = report["next_week_illustration"]
        target = complete.week_start.iloc[-1] + pd.Timedelta(days=7)
        overlap = bool((frame.week_start.eq(target) & frame.partial_week).any())
        reasons = (["known_partial_target_week"] if overlap else [])
        if recent["status"] == "suspected_unreliable":
            reasons.append("recent_source_coverage_unreliable")
        check(illustration["target_week"] == target.date().isoformat() and illustration["trained_through"] == complete.week_start.iloc[-1].date().isoformat(), "Illustrative dates disagree")
        check(illustration["overlaps_excluded_partial_week"] is overlap, "Partial-target safeguard disagrees")
        check(illustration["available"] is (not reasons) and illustration["unavailable_reasons"] == reasons, "Availability safeguards disagree")
        check(illustration["selected_method"] == report["selection"]["method"], "Illustration method disagrees")
        if reasons:
            check(illustration["status"] == "unavailable" and illustration["predictions_brl_cents"] is None and illustration["selected_prediction_brl_cents"] is None, "Unavailable predictions must be null")
        else:
            check(illustration["status"] == "illustrative_only", "Unknown illustration status")
            check(set(illustration["predictions_brl_cents"]) == set(f.METHODS), "Missing illustration methods")
            for value in illustration["predictions_brl_cents"].values():
                f.nonnegative_int(value, "Illustration")
            f.nonnegative_int(illustration["selected_prediction_brl_cents"], "Selected illustration")
            check(illustration["selected_prediction_brl_cents"] == illustration["predictions_brl_cents"][illustration["selected_method"]], "Selected illustration disagrees")
        warnings = quality.get("warnings", [])
        check(isinstance(warnings, list) and all(isinstance(w, str) for w in warnings), "Invalid quality warnings")
        check(snapshot(directory) == contents, "Input files changed during loading; reload")
        return frame, quality, report
    except ImportError as exc:
        raise DashboardError("Optional forecasting dependencies are unavailable. Install requirements-forecast.txt.") from exc
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as exc:
        raise DashboardError("Derived files are invalid, outdated or inconsistent. Regenerate ingestion and forecasting together.") from exc


def series_data(frame, report, methods, start, end, include_training=True):
    """Actuals and predictions share target dates. Never append future illustrations."""
    evaluation_start = pd.Timestamp(report["evaluation"]["start"])
    rows = []
    for row in frame.itertuples(index=False):
        phase = "Excluded partial week" if row.partial_week else "Initial training" if row.week_start < evaluation_start else "Rolling backtest"
        rows.append({"Week": row.week_start, "Revenue · BRL": row.revenue_brl_cents / 100,
                     "Series": "Recorded actual", "Phase": phase, "Kind": "Actual"})
    for row in report["backtest_predictions"]:
        for method in methods:
            rows.append({"Week": pd.Timestamp(row["target_week"]), "Revenue · BRL": row["predictions_brl_cents"][method] / 100,
                         "Series": LABELS[method], "Phase": "Rolling backtest", "Kind": "Prediction"})
    data = pd.DataFrame(rows)
    selected = data.Week.between(pd.Timestamp(start), pd.Timestamp(end))
    if not include_training:
        selected &= data.Phase.ne("Initial training")
    return data.loc[selected].reset_index(drop=True)


def score_table(report):
    names = sorted(LABELS, key=lambda n: (report["scores"][n]["absolute_error_sum_brl_cents"], list(LABELS).index(n)))
    return pd.DataFrame([{"Rank": rank, "Method": LABELS[n], "MAE · BRL": report["scores"][n]["mae_brl"],
                          "WAPE · %": report["scores"][n]["wape_percent"], "Bias · BRL": report["scores"][n]["bias_brl"],
                          "Weeks": report["scores"][n]["weeks"]} for rank, n in enumerate(names, 1)])


def revenue_chart(data):
    import altair as alt
    base = alt.Chart(data).encode(x=alt.X("Week:T", title="Target / observed week (Monday)"),
        y=alt.Y("Revenue · BRL:Q", title="Weekly item-price revenue · BRL", scale=alt.Scale(zero=True)),
        color=alt.Color("Series:N"), tooltip=[alt.Tooltip("Week:T", format="%Y-%m-%d"), "Series:N", "Phase:N", alt.Tooltip("Revenue · BRL:Q", format=",.2f")])
    # Altair's fluent mark method has a generic return in its type declarations.
    lines = cast(alt.Chart, base.transform_filter(alt.datum.Phase != "Excluded partial week").mark_line(point=True)).encode(
        strokeDash=alt.StrokeDash("Kind:N", scale=alt.Scale(domain=["Actual", "Prediction"], range=[[1, 0], [6, 3]])),
        opacity=alt.Opacity("Phase:N", scale=alt.Scale(domain=["Initial training", "Rolling backtest"], range=[0.45, 1])), detail="Phase:N")
    partials = cast(alt.Chart, base.transform_filter(alt.datum.Phase == "Excluded partial week").mark_point(shape="square", size=85))
    return (lines + partials).properties(height=360).interactive()
