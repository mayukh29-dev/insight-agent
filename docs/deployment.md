# Deploy the public InsightAgent demo

The public demo uses `demo_app.py`. It shows four **precomputed**, clearly labelled questions calculated using pandas, interactive Plotly sales charts, and a link/embed to the published Tableau Public workbook. It **does not** expose Live Mode or call OpenAI, and needs **no API credentials**.

The full local application still runs via `python -m streamlit run streamlit_app.py`.

## Publish with Streamlit Community Cloud

1. Sign in with GitHub at https://share.streamlit.io/.
2. Choose **Create app** → **Yup, I have an app**.
3. Select repository `mayukh29-dev/insight-agent`.
4. Choose branch `main` and entrypoint `demo_app.py`.
5. Choose a subdomain (e.g., `insightagent-retail-demo`) if available.
6. Leave **Secrets** empty. **Do not paste an OpenAI API key.**
7. Select **Deploy**. Once it opens, confirm the category demo, Plotly filters, and Tableau link work.
8. Copy the actual `https://....streamlit.app` address and add it to the repository About → Website and README.

The public demo requires internet for the Tableau embed, but the local pandas demo calculations do not.

### Test locally before deployment

```powershell
python -m pip install -r requirements.txt
python -m pytest -q
python -m streamlit run demo_app.py
```

Check that the public demo has **no Live Mode** option, uses no API calls, displays $12,951.00 / 240 / 717 in the unfiltered sales dashboard, and clearly labels the analysis as an offline example.

Do not deploy `streamlit_app.py` with an API key to an unprotected public app. The deployment intentionally uses a separate entrypoint so the original Live Mode remains available only locally.

Official deployment guide: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy
