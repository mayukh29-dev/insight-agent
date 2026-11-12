"""Opt-in analyst controls; no API request on page load or mode changes."""
import hashlib

import streamlit as st

from . import dashboard


def use_sample():
    st.session_state.olist_agent_question = st.session_state.olist_agent_sample


def show(directory):
    st.divider()
    st.subheader("AI Forecast Analyst")
    st.caption("Separate historical BRL analyst · read-only saved results · no model retraining")
    if not st.toggle("Enable Forecast Analyst", key="olist_agent_enabled"):
        st.session_state.pop("olist_agent_answer", None)
        st.caption("Off by default. Enable for a deterministic key-free demo or opt-in Live AI.")
        return
    from . import forecast_agent as agent
    mode = st.segmented_control("Forecast Analyst mode", ["Demo", "Live AI"], default="Demo", key="olist_agent_mode") or "Demo"
    if mode == "Live AI":
        st.info("Live AI uses GPT-5.4 mini and may incur charges when you press Ask. Only your question and bounded aggregate facts are sent. Credentials stay server-side. Do not include personal data or secrets.")
    else:
        st.info("Key-free Demo uses verified facts and deterministic explanation templates. No AI request is made.")
    st.selectbox("Suggested historical question", agent.SAMPLES, key="olist_agent_sample", on_change=use_sample)
    if "olist_agent_question" not in st.session_state:
        st.session_state.olist_agent_question = agent.SAMPLES[0]
    question = st.text_input("Ask about historical Olist results", max_chars=agent.MAX_QUESTION, key="olist_agent_question")
    st.caption("For a specific actual week, use 'What is recorded revenue for week YYYY-MM-DD?' with a covered Monday. Chart filters do not filter analyst evidence.")
    try:
        stamp = (hashlib.sha256(b"".join(dashboard.snapshot(directory))).hexdigest(), mode)
    except dashboard.DashboardError:
        st.session_state.pop("olist_agent_answer", None)
        st.info("Source files changed or became unavailable. Refresh the historical dashboard.")
        return
    if st.session_state.get("olist_agent_stamp") != stamp:
        st.session_state.pop("olist_agent_answer", None)
        st.session_state.olist_agent_stamp = stamp
    if st.button("Ask Forecast Analyst", key="olist_agent_ask"):
        st.session_state.pop("olist_agent_answer", None)
        try:
            with st.spinner("Checking historical evidence…"):
                answer = agent.answer_question(question, mode, directory)
            if answer["fingerprint"] != stamp[0]:
                raise agent.ForecastAgentError("Source files changed. Refresh and ask again.")
            st.session_state.olist_agent_answer = answer
        except (agent.ForecastAgentError, dashboard.DashboardError) as error:
            st.error(str(error))
        except Exception:
            st.error("Forecast Analyst could not complete. Use Demo or refresh the verified reports.")
    answer = st.session_state.get("olist_agent_answer")
    if not answer:
        return
    st.caption(answer["notice"])
    st.markdown("#### Verified source facts")
    for fact in answer["facts"].values():
        st.text(fact)
    for title, entries in (("Explanation", answer["explanations"]), ("Recommendations", answer["recommendations"]), ("Limitations", answer["limitations"])):
        st.markdown(f"#### {title}")
        for entry in entries:
            st.text(entry)
    if st.toggle("Show Forecast Analyst tool evidence", key="olist_agent_evidence"):
        st.json(answer["tools"])
    st.caption("AI selects tools and verified references; application templates render every displayed fact and explanation. Raw model text and reasoning are never displayed.")
