"""Optional API-key-free historical page, loaded only when selected."""
from pathlib import Path

import streamlit as st

from . import dashboard as data

PREPARE = r"""& .\.venv\Scripts\python.exe -m pip install -r requirements-forecast.txt
& .\.venv\Scripts\python.exe -m olist --source .\data\olist\raw --output .\data\olist\processed
& .\.venv\Scripts\python.exe -m olist.forecast --input .\data\olist\processed\weekly_revenue.csv --quality .\data\olist\processed\quality_report.json --output .\data\olist\processed\forecast_results.json"""


@st.cache_data(max_entries=4, show_spinner=False)
def validated(directory, contents):
    # Byte contents (including producer code) invalidate the cache, not mtimes.
    return data.validate_dashboard(Path(directory), contents)


def show():
    st.caption("HISTORICAL OLIST · 2016–2018 · BRL · NO API KEY")
    st.title("How well did past weeks predict the next?")
    st.write("Explore recorded merchandise value and one-week-ahead historical predictions. This is not a forecast of today's Olist business.")
    try:
        directory = data.DEFAULT_DIRECTORY
        frame, quality, report = validated(str(directory), data.snapshot(directory))
    except data.DashboardError as error:
        st.info(str(error), title="Historical dashboard is not ready")
        st.write("Download the four source files manually using docs/olist.md, then run these commands from your repository in PowerShell. Existing demo pages remain available.")
        st.code(PREPARE, language="powershell")
        st.caption("See docs/historical_dashboard.md for setup and freshness checks. No licensed data is bundled.")
        return
    source, evaluation, choice = report["source_timeframe"], report["evaluation"], report["selection"]
    st.caption(f"Observed {source['start']} — {source['end']} · Evaluation {evaluation['start']} — {evaluation['end']} · BRL only")
    with st.container(horizontal=True):
        st.metric("Recorded weeks", str(len(frame)), border=True)
        st.metric("Backtest weeks", str(evaluation["weeks"]), border=True)
        st.metric("Lowest-error method", data.LABELS[choice["method"]], border=True)
        st.metric("Winner MAE · BRL", f"R${report['scores'][choice['method']]['mae_brl']:,.2f}", border=True)
    st.warning("Calendar completeness does not prove source coverage. Zeros remain recorded values; sparse weeks can distort errors. These are historical backtests, not current company results.")
    illustration = report["next_week_illustration"]
    st.subheader("Next-week historical illustration")
    if not illustration["available"]:
        st.warning(f"Unavailable for {illustration['target_week']}. No point prediction is shown.")
        for reason in illustration["unavailable_reasons"]:
            st.write({"known_partial_target_week": "The target overlaps an incomplete boundary week.",
                      "recent_source_coverage_unreliable": "Recent coverage looks unreliable; a zero or declining tail is not proof of genuine zero sales."}[reason])
    else:
        st.metric(f"Illustrative prediction · {illustration['target_week']} · BRL", f"R${illustration['selected_prediction_brl_cents'] / 100:,.2f}")
        st.caption("Prediction only, not actual revenue. No truncation signal was detected; completeness is still unverified. No uncertainty interval is established.")
    st.subheader("Historical prediction errors")
    st.write(f"Ridge {choice['candidate_vs_best_baseline']} against the best baseline ({data.LABELS[choice['best_baseline']]}). Lower error is better; a more complex model need not win.")
    st.caption("MAE is average absolute error in BRL. WAPE is an error percentage, not 100% minus accuracy. Positive bias means overprediction. All scores use the full, unchanged backtest window; selection is not an independent holdout test.")
    scores = data.score_table(report)
    if scores["WAPE · %"].isna().any():
        st.caption("WAPE is unavailable for an all-zero actual series. Empty WAPE cells do not mean zero error.")
    st.dataframe(scores, hide_index=True, width="stretch", alt="Historical method ranking with MAE, WAPE and bias",
        column_config={"MAE · BRL": st.column_config.NumberColumn(format="R$ %.2f"),
                       "WAPE · %": st.column_config.NumberColumn(format="%.2f%%"),
                       "Bias · BRL": st.column_config.NumberColumn(format="R$ %.2f")})
    metric = st.segmented_control("Compare errors", ["MAE · BRL", "WAPE · %"], default="MAE · BRL", key="olist_error_metric")
    if metric:
        bars = scores.loc[scores[metric].notna()]
        if bars.empty:
            st.info("WAPE is unavailable because all evaluated actual revenue is zero; it is not displayed as 0% accuracy.")
        else:
            st.bar_chart(bars, x="Method", y=metric, alt=f"Historical method comparison by {metric}; lower is better")
    st.subheader("Recorded revenue and rolling predictions")
    st.caption("Solid actuals and dashed backtest predictions align to target Mondays. Faded actuals mark initial training; squares mark excluded partial actuals. The next-week illustration is never mixed into this chart.")
    with st.container(border=True):
        dates = st.date_input("Chart date range", (frame.week_start.min().date(), frame.week_start.max().date()),
            min_value=frame.week_start.min().date(), max_value=frame.week_start.max().date(), key="olist_dates")
        defaults = list(dict.fromkeys([choice["best_baseline"], "ridge", choice["method"]]))
        methods = st.multiselect("Backtest methods", list(data.LABELS), default=defaults, format_func=lambda name: data.LABELS[name], key="olist_methods")
        training = st.toggle("Include initial training weeks", value=True, key="olist_training")
        st.caption("These controls affect this chart and its evidence table only. Global model scores, winner and safeguards never change with a chart filter.")
    if len(dates) != 2:
        st.info("Select both chart dates.")
    else:
        chart_data = data.series_data(frame, report, methods, *dates, include_training=training)
        if chart_data.empty:
            st.info("No weeks match these chart filters.")
        else:
            st.altair_chart(data.revenue_chart(chart_data), width="stretch", alt="Recorded weekly BRL revenue versus historical target-aligned predictions")
            if st.toggle("Show chart evidence", key="olist_chart_evidence"):
                st.dataframe(chart_data, hide_index=True, alt="Values plotted for actuals and historical predictions")
    st.subheader("Data quality and interpretation")
    coverage = report["coverage"]
    st.success(f"Revenue reconciliation passed: weekly and category totals both equal R${report['reconciliation']['weekly_total_brl_cents'] / 100:,.2f}.")
    st.write(f"{len(coverage['partial_weeks'])} partial boundary weeks · {len(coverage['zero_weeks'])} zero-value weeks · {len(coverage['outlier_weeks'])} outlier flags. All recorded zeros and outliers stay in the primary backtest.")
    st.write("Business reading: use the simplest method supported by the historical errors. Investigate coverage and order-status evidence before interpreting a low or zero revenue week. The figures do not establish profit, causes of changes, or present-day sales.")
    for warning in quality.get("warnings", []):
        st.warning(warning)
    if st.toggle("Inspect quality and provenance", key="olist_quality"):
        st.write("Partial boundaries: " + ", ".join(coverage["partial_weeks"]))
        st.write("Zero-value weeks: " + ", ".join(coverage["zero_weeks"]))
        st.write("Outlier weeks: " + ", ".join(coverage["outlier_weeks"]))
        st.json(coverage["recent_source_coverage"])
        st.json(report["backtest_tail_sensitivity"])
        st.caption("Endpoint sensitivity is a separate diagnostic, not the primary scoring window or winner.")
        st.json(report["provenance"])
    st.caption("Item prices for delivered orders by purchase week; excludes freight, not net of refunds. Charts never train models or call AI. The optional Forecast Analyst below calls AI only after explicit Live AI submission.")
    from .forecast_analyst_page import show as show_analyst
    show_analyst(directory)
