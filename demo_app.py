"""Public, API-key-free InsightAgent portfolio demonstration.

This entry point deliberately does not import or expose the live AI agent.
The full local application remains available in streamlit_app.py.
"""
from datetime import date

import streamlit as st
import streamlit.components.v1 as components

from dashboard import dashboard_charts, dashboard_metrics, filter_sales
from generate_data import DATA_PATH
from presentation import SAMPLE_QUESTIONS, build_demo_reports
from tableau import TABLEAU_URL, embed_html
from tools import load_sales

st.set_page_config(page_title="InsightAgent | Interactive Demo", page_icon="📊", layout="wide")


@st.cache_data
def get_sales():
    return load_sales(DATA_PATH)


def show_kpis(sales):
    totals = dashboard_metrics(sales)
    a, b, c = st.columns(3)
    a.metric("Revenue (USD)", f"${totals['revenue']:,.2f}")
    b.metric("Transactions", f"{totals['transactions']:,}")
    c.metric("Units sold", f"{totals['units']:,}")


def analyst_view(sales):
    st.title("Ask InsightAgent")
    st.caption("OFFLINE DEMO · Four precomputed business questions backed by actual pandas calculations")
    st.info("This public demonstration does not call an AI model and requires no API key. "
            "The GitHub repository includes a separate, locally runnable Live Mode.")
    question = st.selectbox("Choose a business question", SAMPLE_QUESTIONS, key="demo_question")
    if st.button("Run Analysis", type="primary"):
        st.session_state.demo_selected = question
    selected = st.session_state.get("demo_selected")
    if not selected:
        st.write("Choose a question, then click **Run Analysis**.")
        return
    report = build_demo_reports(sales)[selected]
    st.subheader("Answer")
    st.write(report.summary)
    if report.metrics:
        with st.expander("Verified calculations", expanded=True):
            for metric in report.metrics:
                st.write(metric)
    if report.recommendations:
        st.subheader("Suggested next steps")
        for suggestion in report.recommendations:
            st.write(f"• {suggestion}")
    with st.expander("Limitations and transparency", expanded=True):
        for limitation in report.limitations:
            st.write(f"• {limitation}")
        st.caption("Calculation tools: " + ", ".join(report.tools))


def dashboard_view(sales):
    st.title("Explore retail sales")
    st.caption("Synthetic transactions · January–June 2025 · Interactive Plotly charts")
    categories = st.multiselect(
        "Product categories",
        sorted(sales["category"].unique()),
        default=sorted(sales["category"].unique()),
    )
    date_range = st.date_input(
        "Date range",
        value=(sales["date"].min().date(), sales["date"].max().date()),
        min_value=sales["date"].min().date(),
        max_value=sales["date"].max().date(),
    )
    if not isinstance(date_range, (tuple, list)) or len(date_range) != 2:
        st.info("Select both a start and an end date.")
        return
    try:
        filtered = filter_sales(sales, categories, date_range[0], date_range[1])
    except ValueError as exc:
        st.warning(str(exc))
        return
    show_kpis(filtered)
    if filtered.empty:
        st.info("No transactions match these filters.")
        return
    charts = dashboard_charts(filtered)
    left, right = st.columns(2)
    with left:
        st.subheader("Monthly revenue")
        st.plotly_chart(charts["Monthly revenue"], width="stretch")
    with right:
        st.subheader("Revenue by category")
        st.plotly_chart(charts["Revenue by category"], width="stretch")
    st.subheader("Top five products")
    st.plotly_chart(charts["Top five products"], width="stretch")
    with st.expander("Inspect selected transactions"):
        st.dataframe(filtered, hide_index=True)


def tableau_view():
    st.title("Tableau Intelligence")
    st.write("Explore the independently published Tableau Public dashboard.")
    st.caption("Its filters operate independently of the local Plotly charts.")
    st.link_button("Open dashboard on Tableau Public", TABLEAU_URL)
    st.info("If the embedded dashboard doesn't load, use the direct Tableau Public link.")
    components.html(embed_html(), height=830, scrolling=True)


def main():
    st.sidebar.title("InsightAgent")
    st.sidebar.caption("PUBLIC PORTFOLIO DEMO")
    page = st.sidebar.radio(
        "Explore",
        ("AI Analyst Demo", "Sales Dashboard", "Tableau Intelligence"),
    )
    st.sidebar.divider()
    st.sidebar.caption("Fictional retail data · No API requests or credentials")
    st.sidebar.link_button("View source on GitHub", "https://github.com/mayukh29-dev/insight-agent")
    try:
        sales = get_sales()
    except (OSError, ValueError):
        st.error("Unable to load the bundled synthetic sales data.")
        return
    if page == "AI Analyst Demo":
        analyst_view(sales)
    elif page == "Sales Dashboard":
        dashboard_view(sales)
    else:
        tableau_view()


if __name__ == "__main__":
    main()
