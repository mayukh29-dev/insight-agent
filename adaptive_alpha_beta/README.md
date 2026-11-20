# Adaptive Alpha — Streamlit research beta

This is a **standalone demo** of the Adaptive Alpha historical research project. It uses disclosed historical summary numbers, not actual local backtest CSV files. It does not validate a production investment strategy.

## Run locally
```bash
pip install -r adaptive_alpha_beta/requirements.txt
streamlit run adaptive_alpha_beta/app.py
```

## Deploy
Open https://share.streamlit.io and select:
- Repository: `mayukh29-dev/insight-agent`
- Branch: `adaptive-alpha-streamlit-beta`
- Main file: `adaptive_alpha_beta/app.py`

The app is on a dedicated branch so the original Insight Agent main branch stays unchanged.

## Research Agent
The free Snapshot facts mode answers limited stock questions using a live vendor snapshot via yfinance. Optional AI mode requires the *visitor's own* OpenAI API key, supplied for the request; do not commit keys. Public hosting has not been configured and no hosted URL is live yet.

## Disclaimer
Historic test is affected by survivorship and retrospective selection bias; price anomalies are still being audited. Research snapshots can be stale or incomplete. Not financial advice.
