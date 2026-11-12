"""A local retail analytics workspace over the existing CLI and agent."""

import streamlit as st
import streamlit.components.v1 as components

from dashboard import dashboard_charts, dashboard_metrics, filter_sales
from generate_data import DATA_PATH
from presentation import SAMPLE_QUESTIONS, answer_question, build_demo_reports
from tableau import TABLEAU_URL, embed_html
from tools import load_sales

st.set_page_config(page_title="InsightAgent | Retail intelligence", page_icon="◈", layout="wide")


@st.cache_data
def read_data(contents):
    """Invalidate cached validation when the local CSV contents change."""
    from io import BytesIO

    return load_sales(BytesIO(contents))


@st.cache_data
def demo_answers(sales):
    return build_demo_reports(sales)


def show_metrics(sales):
    metrics = dashboard_metrics(sales)
    columns = st.columns(3)
    columns[0].metric("Revenue · USD", f"${metrics['revenue']:,.2f}")
    columns[1].metric("Transactions", f"{metrics['transactions']:,}")
    columns[2].metric("Units sold", f"{metrics['units']:,}")


def show_report(report):
    st.subheader("Answer summary")
    st.write(report.summary)
    if report.metrics:
        with st.expander("Calculated metrics", expanded=True):
            for metric in report.metrics:
                st.write(metric)
    for heading, entries in (("Business insights", report.additional_insights),
                             ("Recommendations", report.recommendations)):
        if entries:
            st.markdown(f"#### {heading}")
            for entry in entries:
                st.write(entry)
    with st.expander("Limitations & evidence", expanded=True):
        for limitation in report.limitations:
            st.write(limitation)
        st.caption("Evidence is the complete validated local CSV. Revenue is quantity × unit price, in USD.")
    with st.expander("Underlying tools used"):
        if report.tools:
            st.code("\n".join(report.tools), language="text")
        else:
            st.write("No calculation tools executed for this question.")
        if report.raw:
            st.text(report.raw)


def use_sample():
    if st.session_state.sample_question:
        st.session_state.question = st.session_state.sample_question


def analyst_page(sales):
    st.caption("ASK • CALCULATE • VERIFY")
    st.title("Your retail analyst, on demand")
    st.write("Ask a business question and explore the calculations behind the answer.")
    mode = st.radio("Analysis mode", ["Demo Mode", "Live Mode"], horizontal=True, key="analysis_mode")
    if mode == "Demo Mode":
        st.info("Offline demo · Precomputed answers from validated sales data. Choose a suggested question.")
    else:
        st.info("Live AI · Each analysis calls OpenAI and may incur API charges. Credentials stay on the server.")
    st.caption("AI answers use the full dataset. Sales Dashboard filters apply only to that page. Each question is independent.")
    with st.expander("Dataset context"):
        show_metrics(sales)
    st.selectbox("Suggested question", SAMPLE_QUESTIONS, index=None,
                 placeholder="Choose a question to try", key="sample_question", on_change=use_sample)
    st.text_area("Your business question", key="question", height=90,
                 placeholder="Which category generated the most revenue?")
    if st.button("Run Analysis", type="primary"):
        question = st.session_state.question.strip()
        try:
            with st.spinner("Preparing your analysis…"):
                report = answer_question(question, sales, mode, demo_answers(sales))
            history = st.session_state.get("analysis_history", [])
            st.session_state.analysis_history = (history + [(mode, report)])[-5:]
        except ValueError as error:
            # AgentError inherits ValueError and contains a safe user-facing message.
            st.error(str(error))
        except Exception:
            st.error("Analysis could not complete. Please try again or switch to Demo Mode.")
    history = st.session_state.get("analysis_history", [])
    if history:
        answer_mode, report = history[-1]
        st.divider()
        with st.chat_message("user"):
            st.write(report.question)
        with st.chat_message("assistant"):
            st.caption(f"{answer_mode} · Complete dataset")
            show_report(report)
        if len(history) > 1:
            with st.expander("Earlier analyses in this session"):
                for earlier_mode, earlier_report in reversed(history[:-1]):
                    st.caption(earlier_mode)
                    st.write(earlier_report.question)
                    st.write(earlier_report.summary)
        if st.button("Clear analysis history"):
            st.session_state.analysis_history = []
            st.rerun()
    else:
        st.divider()
        st.subheader("Start with a question")
        st.write("Compare category revenue, explore monthly patterns, or find the leading products.")


def dashboard_page(sales):
    st.caption("EXPLORE • COMPARE • UNDERSTAND")
    st.title("The sales picture")
    st.write("Explore fictional retail performance with calculations you can inspect.")
    with st.container(border=True):
        categories = st.multiselect("Categories", sorted(sales["category"].unique()),
                                    default=sorted(sales["category"].unique()), key="categories")
        dates = st.date_input("Date range", value=(sales["date"].min().date(), sales["date"].max().date()),
                              min_value=sales["date"].min().date(), max_value=sales["date"].max().date(), key="date_range")
        st.caption("These filters affect every KPI and chart below. AI Analyst uses the full dataset.")
    if len(dates) != 2:
        st.info("Select both a start and end date to explore sales.")
        return
    try:
        filtered = filter_sales(sales, categories, *dates)
    except ValueError as error:
        st.warning(str(error))
        return
    st.caption(f"{dates[0]:%b %d, %Y} — {dates[1]:%b %d, %Y} · {len(categories)} categories selected")
    show_metrics(filtered)
    if filtered.empty:
        st.info("No transactions match these filters. Select another category or date range.")
        return
    charts = dashboard_charts(filtered)
    left, right = st.columns([1.5, 1])
    for container, title in ((left, "Monthly revenue"), (right, "Revenue by category")):
        with container:
            with st.container(border=True):
                st.subheader(title)
                st.plotly_chart(charts[title], width="stretch", config={"displaylogo": False})
    with st.container(border=True):
        st.subheader("Top five products by revenue")
        st.plotly_chart(charts["Top five products"], width="stretch", config={"displaylogo": False})
    with st.expander("Source transactions & definitions"):
        st.caption("One row is one transaction. Revenue is quantity × unit price. Dates are inclusive.")
        st.caption("Monthly gaps between the first and last matching transaction display zero revenue. Partial months remain partial.")
        st.dataframe(filtered, hide_index=True, width="stretch",
                     column_config={"unit_price": st.column_config.NumberColumn("Unit price · USD", format="$%.2f")})


def tableau_page():
    st.caption("INDEPENDENT PORTFOLIO VIEW")
    st.title("Tableau Intelligence")
    st.write("Explore the published Retail Sales Intelligence Dashboard in Tableau Public.")
    st.caption("This independent dashboard has its own data and controls. Local filters and AI questions do not modify it.")
    st.link_button("Open full Tableau dashboard ↗", TABLEAU_URL, type="primary")
    st.info("If the embed stays blank or your browser blocks it, use the full-dashboard link above. Tableau requires internet access.")
    components.html(embed_html(), height=830, scrolling=True)


def main():
    st.html("""<style>
      .stApp { background: #f6f8f8; }
      .block-container { padding-top: 2.5rem; padding-bottom: 3rem; max-width: 1320px; }
      h1, h2, h3 { letter-spacing: -0.035em; }
      [data-testid="stMetric"] { background: white; border: 1px solid #dee7e6;
        border-radius: 12px; padding: 16px; margin-bottom: 16px; }
      [data-testid="stSidebar"] { background: #eaf1f0; }
    </style>""")
    with st.sidebar:
        st.title("◈ InsightAgent")
        st.caption("RETAIL INTELLIGENCE WORKSPACE")
        st.divider()
        page = st.radio("Workspace", ["AI Analyst", "Sales Dashboard", "Tableau Intelligence", "Olist historical forecasts"],
                        label_visibility="collapsed", key="workspace")
        st.divider()
        st.caption("Portfolio project · Fictional USD demo / historical Olist BRL")
        st.caption("Python calculations. Evidence you can inspect.")
    if page == "Olist historical forecasts":
        # This page never loads or aggregates the fictional USD sales data.
        try:
            from olist.dashboard_page import show
        except ImportError:
            st.info("Historical dashboard dependencies are unavailable. Install requirements.txt and requirements-forecast.txt. Other workspaces remain available.")
            return
        show()
        return
    if page == "Tableau Intelligence":
        tableau_page()
        return
    try:
        contents = DATA_PATH.read_bytes()
        # Clear previous answers when the underlying evidence changes.
        if st.session_state.get("data_contents") != contents:
            st.session_state.analysis_history = []
            st.session_state.data_contents = contents
        sales = read_data(contents)
    except (OSError, ValueError):
        st.error("Sales data could not be loaded or validated. Check data/sales.csv or regenerate it with python generate_data.py.")
        return
    if page == "Sales Dashboard":
        dashboard_page(sales)
    else:
        analyst_page(sales)


if __name__ == "__main__":
    main()
