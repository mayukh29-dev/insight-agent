# InsightAgent · Five-minute technical walkthrough

## 0:00–0:45 · Boundaries and data

Start with the architecture diagram in the README. The CSV is the local source of
truth for the CLI, Streamlit charts, and analyst. `load_sales()` validates required
columns, dates, positive whole quantities, finite nonnegative prices, duplicate order
IDs, and empty data. The generator uses a fixed random seed and stable CSV formatting.

The Tableau view is a separate published portfolio artifact. It is embedded through
Tableau's v3 web component. The application does not copy its workbook or claim that
its filters are synchronized with the Python workspace.

## 0:45–1:40 · Planning and controlled function calling

In Live Mode, `presentation.answer_question()` calls the existing `run_agent()`.
The planner receives the user's question and four function schemas. The model chooses
whether it needs total revenue, category sales, monthly revenue, or top products.
These are actual model-selected function calls that execute locally.

Each schema accepts an empty object. The application checks that the tool name is in
an explicit allowlist and rejects arguments that request additional inputs. The model
cannot choose a file path, execute Python, or invoke a shell through this interface.
The trusted dataframe is supplied by the application.

The pandas functions return deterministic results. The adapter converts periods and
numeric values into JSON-compatible results with monetary values formatted to cents.
Responses API continuation preserves model output items and sends each calculation
back as a `function_call_output` associated with the original call ID. The loop permits
four rounds and then stops if further tool execution is requested.

## 1:40–2:35 · Writing and reflection

A separate model request writes insights, recommendations, and limitations using
strict Structured Outputs. Both the first report and the optional revision use the
same JSON schema. The report schema controls shape, while the verifier checks content.

The calculation layer creates fact references that bind labels to values and units.
For example, a category fact contains the category name, its revenue, and its units
sold. A report can cite that complete fact without typing an unverified number.
The deterministic verifier rejects unknown references and explicit unsupported
quantities. It allows at most one revision, then removes and flags remaining
unverified statements. This is conservative verification, and human review is still
needed for natural-language interpretations.

Show the existing CLI to demonstrate that `python app.py` still works independently
of the UI. `--ask` continues to use the same agent. The web layer parses the returned
sections into a small `Report` object without rewriting the claims.

## 2:35–3:35 · Dashboard and UI architecture

`streamlit_app.py` handles navigation, session state, controls, and presentation.
`dashboard.py` contains pure filtering, KPI, and chart functions. Category and inclusive
date filters produce one dataframe that feeds every visible KPI and all three Plotly
charts. No matching rows produces zero KPIs and an explicit empty state. Partial months
are labeled in the definitions, and month gaps use the existing pandas tool behavior.

The analyst deliberately uses the complete dataset. Each question is independent.
Session history keeps the latest five analyses for review, with a mode label attached
to each result. If the CSV contents change, the UI clears previous answers and
revalidates the data. Credentials and exceptions containing provider details are never
displayed in the interface.

Demo Mode precomputes the curated answers from the validated dataframe. It uses the
same deterministic tools with prepared explanations. Unsupported demo questions receive
a clear limitation, and the code path does not create an OpenAI client.

## 3:35–4:35 · Verification

Run `python -m pytest -q`. Original analysis and agent tests remain in the suite.
Dashboard tests compare totals and filtered chart values with manually calculated
transactions. Presentation tests preserve claims and check the offline/live routing.
Streamlit AppTest exercises navigation, demo analysis, live dispatch with a mocked
agent, category filtering, empty states, and the Tableau fallback message.

The agent suite uses scripted clients and mocked SDK HTTP transport. No default test
spends API credits. These tests verify integration contracts and expected calculations,
but live model selection requires separate evaluation. Browser rendering, Plotly hover
behavior, and the third-party Tableau view also need browser-level checks.

## 4:35–5:00 · Limits and next questions

Explain the boundary between observation and inference. This dataset supports revenue
and units, but lacks costs, customer records, stock levels, and causal evidence.
Live requests incur token charges and may time out. Tableau availability depends on
its external service and browser policy. The application is intended for a local
portfolio demonstration and has no authentication or hosted multiuser controls.
