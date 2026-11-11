"""Historical one-week-ahead backtesting. No API calls or current-business forecasts."""

import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import platform
import re

import numpy as np
import pandas as pd

from .pipeline import FILES, ValidationError, require

METHODS = ("last_week", "mean_4", "ridge")
LAGS = 4
MIN_HISTORY = 12
MIN_EVALUATION = 4
ALPHA = 1.0
MAX_CENTS = 2**53 - 1


def nonnegative_int(value, label):
    require(type(value) is int and 0 <= value <= MAX_CENTS, f"{label}: expected nonnegative safe integer cents")
    return value


def date(value, label):
    require(isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is not None, f"{label}: expected ISO date")
    try:
        result = pd.Timestamp(value)
    except ValueError as exc:
        raise ValidationError(f"{label}: invalid date") from exc
    require(pd.Timestamp("2016-01-01") <= result <= pd.Timestamp("2018-12-31"), f"{label}: outside historical 2016–2018 window")
    return result


def load_inputs(input_path, quality_path):
    """Validate/reconcile the entire observation window before removing boundaries."""
    raw = pd.read_csv(input_path, dtype=str, keep_default_na=False)
    require(list(raw.columns) == ["week_start", "revenue_brl_cents", "revenue_brl", "partial_week"], "weekly schema mismatch")
    require(not raw.empty, "weekly input is empty")
    try:
        quality = json.loads(Path(quality_path).read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise ValidationError("invalid quality JSON") from exc
    require(isinstance(quality, dict), "quality report must be an object")
    require(quality.get("currency") == "BRL", "quality currency must be BRL")
    require(quality.get("source") == "Olist public historical dataset (2016–2018)", "unexpected historical source")
    require(quality.get("revenue_definition") == "delivered-order item prices by purchase timestamp; excludes freight; not net of refunds", "revenue definition mismatch")
    require(quality.get("week_definition") == "Monday through Sunday; naive source local timestamps; no timezone conversion", "week definition mismatch")
    start = date(quality.get("observation_start"), "observation_start")
    end = date(quality.get("observation_end"), "observation_end")
    require(start <= end, "reversed observation bounds")
    hashes = quality.get("source_sha256")
    require(isinstance(hashes, dict) and set(hashes) == {v[0] for v in FILES.values()}, "source fingerprints missing")
    require(all(isinstance(v, str) and re.fullmatch(r"[0-9a-f]{64}", v) for v in hashes.values()), "invalid source fingerprints")
    categories = quality.get("category_revenue_brl_cents")
    require(isinstance(categories, dict), "category totals missing")
    category_total = sum(nonnegative_int(v, "category total") for v in categories.values())
    weeks = [date(v, "week_start") for v in raw.week_start]
    require(all(w.day_of_week == 0 for w in weeks), "weeks must start on Monday")
    require(all(b - a == pd.Timedelta(days=7) for a, b in zip(weeks, weeks[1:])), "weeks must be sorted, unique and contiguous")
    require(weeks[0] == start.to_period("W-SUN").start_time and weeks[-1] == end.to_period("W-SUN").start_time, "weekly coverage disagrees with quality bounds")
    values, partial = [], []
    for row, week in zip(raw.itertuples(index=False), weeks):
        require(re.fullmatch(r"0|[1-9][0-9]*", row.revenue_brl_cents) is not None, "invalid integer cents")
        value = nonnegative_int(int(row.revenue_brl_cents), "weekly revenue")
        try:
            display = Decimal(row.revenue_brl)
            require(display.is_finite() and display >= 0 and display * 100 == value, "BRL display and cents disagree")
        except InvalidOperation as exc:
            raise ValidationError("invalid BRL display") from exc
        require(row.partial_week in ("True", "False"), "unknown partial_week flag")
        flag = row.partial_week == "True"
        expected = week < start or week + pd.Timedelta(days=6) > end
        require(flag == expected, "partial_week disagrees with observation bounds")
        values.append(value)
        partial.append(flag)
    weekly_total = sum(values)
    require(weekly_total <= MAX_CENTS, "total exceeds safe modeling range")
    require(weekly_total == category_total, "weekly/category revenue reconciliation failed")
    frame = pd.DataFrame({"week_start": weeks, "revenue_brl_cents": values, "partial_week": partial})
    return frame, quality, {"passed": True, "weekly_total_brl_cents": weekly_total, "category_total_brl_cents": category_total}


def features(history):
    """Only earlier observations: lags 1–4 and their trailing mean."""
    require(len(history) >= LAGS, "four lag observations required")
    recent = np.asarray(history[-LAGS:][::-1], dtype=float)
    return np.append(recent, recent.mean())


def predict(history):
    """Refit ridge on the expanding past; standardization never sees the target."""
    require(len(history) >= MIN_HISTORY, "insufficient training history")
    x = np.asarray([features(history[:i]) for i in range(LAGS, len(history))])
    y = np.asarray(history[LAGS:], dtype=float)
    mean, scale = x.mean(axis=0), x.std(axis=0)
    scale[scale == 0] = 1.0
    z = (x - mean) / scale
    y_mean = y.mean()
    coefficients = np.linalg.solve(z.T @ z + ALPHA * np.eye(z.shape[1]), z.T @ (y - y_mean))
    model_value = y_mean + ((features(history) - mean) / scale) @ coefficients
    candidates = {"last_week": history[-1], "mean_4": sum(history[-4:]) / 4, "ridge": float(model_value)}
    require(all(np.isfinite(v) for v in candidates.values()), "nonfinite prediction")
    # Fixed policy, applied to every method: clip negatives and round to centavos.
    predictions = {name: max(0, int(round(value))) for name, value in candidates.items()}
    require(all(value <= MAX_CENTS for value in predictions.values()), "prediction exceeds safe modeling range")
    audit = {"intercept_center_brl_cents": float(y_mean), "feature_means": mean.tolist(),
             "feature_scales": scale.tolist(), "coefficients": coefficients.tolist(), "training_samples": len(y)}
    return predictions, audit


def metrics(actual, predicted):
    require(len(actual) == len(predicted) and len(actual) > 0, "metrics require matching nonempty series")
    errors = [p - a for a, p in zip(actual, predicted)]
    absolute = sum(abs(e) for e in errors)
    denominator = sum(actual)
    return {"mae_brl": absolute / len(actual) / 100,
            "wape_percent": 100 * absolute / denominator if denominator else None,
            "wape_undefined_reason": None if denominator else "all actual revenue is zero",
            "bias_brl": sum(errors) / len(actual) / 100,
            "absolute_error_sum_brl_cents": absolute, "weeks": len(actual)}


def select(scores):
    # Same actual targets => ranking by absolute error sum also ranks MAE and WAPE.
    winner = min(METHODS, key=lambda name: (scores[name]["absolute_error_sum_brl_cents"], METHODS.index(name)))
    baseline = min(METHODS[:2], key=lambda name: (scores[name]["absolute_error_sum_brl_cents"], METHODS.index(name)))
    delta = scores["ridge"]["absolute_error_sum_brl_cents"] - scores[baseline]["absolute_error_sum_brl_cents"]
    return {"method": winner, "best_baseline": baseline,
            "candidate_vs_best_baseline": "loses" if delta > 0 else "wins" if delta < 0 else "ties",
            "rule": "lowest total absolute backtest error (equivalent to MAE); ties prefer last_week, then mean_4, then ridge",
            "caution": "Selection uses these backtests; selected score is not an independent estimate of future winner performance."}


def coverage(frame):
    """Descriptive diagnostics only; no removal or model fitting uses these flags."""
    values = frame.revenue_brl_cents.tolist()
    outliers = []
    for i in range(8, len(values)):
        q1, q3 = np.quantile(values[:i], [0.25, 0.75])
        width = q3 - q1
        if values[i] < q1 - 3 * width or values[i] > q3 + 3 * width:
            outliers.append(frame.week_start.iloc[i].date().isoformat())
    return {"zero_weeks": [w.date().isoformat() for w, v in zip(frame.week_start, values) if v == 0],
            "partial_weeks": frame.loc[frame.partial_week, "week_start"].dt.strftime("%Y-%m-%d").tolist(),
            "early_12_weeks": [{"week_start": w.date().isoformat(), "revenue_brl_cents": int(v)} for w, v in zip(frame.week_start[:12], values[:12])],
            "outlier_weeks": outliers, "outlier_rule": "after 8 observations: outside prior-history Q1−3*IQR to Q3+3*IQR; IQR=0 flags any departure; retain all",
            "sparse_period_policy": "first 12 complete weeks are fixed training warm-up; retain zero, sparse and outlier weeks thereafter; no automatic ramp-up trimming"}


def run(input_path, quality_path):
    frame, quality, reconciliation = load_inputs(input_path, quality_path)
    complete = frame.loc[~frame.partial_week].reset_index(drop=True)
    require(len(complete) >= MIN_HISTORY + MIN_EVALUATION, "need at least 16 complete weeks (12 training + 4 evaluation)")
    values = complete.revenue_brl_cents.tolist()
    rows = []
    for i in range(MIN_HISTORY, len(complete)):
        predictions, _ = predict(values[:i])
        rows.append({"target_week": complete.week_start.iloc[i].date().isoformat(),
                     "trained_through": complete.week_start.iloc[i - 1].date().isoformat(),
                     "history_weeks": i, "actual_brl_cents": values[i], "predictions_brl_cents": predictions})
    scores = {name: metrics([r["actual_brl_cents"] for r in rows], [r["predictions_brl_cents"][name] for r in rows]) for name in METHODS}
    selection = select(scores)
    future, audit = predict(values)
    next_week = complete.week_start.iloc[-1] + pd.Timedelta(days=7)
    sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return {
        "report_version": 1, "currency": "BRL", "horizon_weeks": 1,
        "source_timeframe": {"start": quality["observation_start"], "end": quality["observation_end"]},
        "revenue_definition": quality["revenue_definition"], "reconciliation": reconciliation,
        "source_quality_summary": {key: quality[key] for key in (
            "input_rows", "status_counts", "missing_dates", "timestamp_inconsistencies",
            "orders_with_timestamp_inconsistencies", "excluded_orders", "included_orders",
            "included_items", "missing_category_items", "unmapped_category_items", "warnings"
        ) if key in quality},
        "provenance": {"weekly_input_sha256": sha(input_path), "quality_input_sha256": sha(quality_path),
                       "source_sha256": quality["source_sha256"], "forecast_code_sha256": sha(__file__),
                       "python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__},
        "coverage": coverage(frame),
        "evaluation": {"start": rows[0]["target_week"], "end": rows[-1]["target_week"], "weeks": len(rows),
                       "rule": "expanding origin; every complete week after first 12; boundary partial weeks excluded from both training and scoring",
                       "reason": "fixed minimum supplies 8 supervised samples with four lags; at least 4 evaluation weeks; no tuning to observed errors",
                       "training_start": complete.week_start.iloc[0].date().isoformat()},
        "model": {"name": "ridge", "alpha": ALPHA, "features": ["lag_1", "lag_2", "lag_3", "lag_4", "trailing_mean_4"],
                  "objective": "sum squared errors + alpha * sum squared standardized-feature coefficients; unpenalized centered intercept",
                  "fit_policy": "refit and standardize using earlier training samples only; fixed hyperparameters, no search or random split",
                  "rounding": "nearest integer cent, ties to even; negative predictions clipped to zero", "final_fit": audit},
        "backtest_predictions": rows, "scores": scores, "selection": selection,
        "next_week_illustration": {"target_week": next_week.date().isoformat(),
                                   "trained_through": complete.week_start.iloc[-1].date().isoformat(),
                                   "kind": "prediction, not actual revenue or a current Olist business forecast",
                                   "overlaps_excluded_partial_week": bool((frame.week_start.eq(next_week) & frame.partial_week).any()),
                                   "predictions_brl_cents": future, "selected_method": selection["method"],
                                   "selected_prediction_brl_cents": future[selection["method"]]},
        "limitations": ["Historical 2016–2018 public data; not a forecast of 2026 Olist operations.",
                        "No prediction intervals: too little evidence for a calibrated uncertainty claim.",
                        "Source coverage is not guaranteed; zero weeks and outliers are retained. Review Phase 1 quality warnings.",
                        "Final partial week, if present, is ignored; illustration targets the week immediately after the last complete week, possibly that excluded partial week.",
                        "Scores select among three fixed methods on the same backtests; no independent post-selection holdout.",
                        "Late-delivery status is known from the historical extract; backtest simulates availability of weekly totals, not real-time status reporting."]}


def main():
    parser = argparse.ArgumentParser(description="Backtest historical weekly Olist BRL revenue")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--quality", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(args.output.resolve() not in {args.input.resolve(), args.quality.resolve()}, "output must not overwrite input")
    report = run(args.input, args.quality)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "scores": report["scores"], "selection": report["selection"]}, indent=2))


if __name__ == "__main__":
    main()
