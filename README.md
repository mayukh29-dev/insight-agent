# InsightAgent

An agentic AI retail sales analyst built as a three-day portfolio project using Python, pandas, Streamlit, and LLM tool use.

## Goal
Analyze a reproducible retail sales dataset, compute accurate business metrics, and ultimately generate grounded business insights using an agent workflow.

## Three-day scope
- **Day 1:** Generate sample sales data, implement deterministic pandas analysis tools, add CLI and pytest tests.
- **Day 2:** Add LLM planning, controlled tool execution, report writing, and one reflection pass.
- **Day 3:** Add a Streamlit UI, evaluations, documentation, and a demo.

## Project principles
- Calculations come from tested Python functions, not model guesses.
- LLM tool selection uses an explicit allowlist, never arbitrary code execution.
- Keep the implementation simple and auditable.
- Do not commit API keys or `.env` files.

## Status
Days 1 and 2 provide deterministic sales analysis and an optional CLI agent.

## Day 1 setup

From the repository root, create and activate a virtual environment with Python 3.11 or newer.

```sh
python -m venv .venv
```

In PowerShell, run `.\.venv\Scripts\Activate.ps1`. On macOS or Linux, run `source .venv/bin/activate`.

```sh
python -m pip install -r requirements.txt
python app.py
python -m pytest -q
```

## Data and metrics

The bundled `data/sales.csv` contains 240 fictional orders from January through June 2025. Run `python generate_data.py` to recreate the same CSV using the fixed seed.

The loader requires `date`, `order_id`, `product`, `category`, `quantity`, and `unit_price`. It rejects missing fields, invalid calendar dates, quantities that are not positive whole numbers, and prices that are negative or nonfinite.

Revenue is quantity times unit price in US dollars. Category sales include units sold and revenue. The monthly report fills any gaps between the first and last sale with zero revenue. The top five products are ranked by revenue, with ties sorted alphabetically.

## Day 2 architecture

`app.py --ask` loads validated data and calls `run_agent(question, sales, client=None)`.
The planner chooses real function calls using strict empty-object JSON schemas.
An explicit allowlist dispatches only the four existing pandas functions, operating
on the supplied in-memory dataframe. Tool results return as JSON strings through
`function_call_output` with matching call IDs. The full response output, including
reasoning items, is preserved for continuation. No raw CSV or credentials enter prompts.

Planning permits four tool rounds, with up to four calls per round, followed by a
completion request. Invalid names, nonempty/malformed arguments, duplicate IDs,
incomplete responses, or excess rounds stop with a safe error. The caller should
supply a dataframe returned by `load_sales`.

A separate LLM call writes JSON insights, recommendations, and limitations.
Numbers are inserted through complete fact references binding labels, values, and
units. Deterministic verification rejects unknown references and explicit numerical
claims outside those references. One revision is allowed, then unverified statements
are removed and flagged. All executed metrics are printed with USD values to two
decimal places. Qualitative statements still need human review. The verifier is
conservative and cannot prove arbitrary natural-language claims or catch every
spelled-out quantity or misleading interpretation.

## Agent environment and usage

Install the updated requirements in the virtual environment described above.
Copy `.env.example` to `.env`, then set `OPENAI_API_KEY` locally.
Alternatively set it in your shell environment. Never commit credentials.
The example file contains empty variable assignments only. Both `.env` and its
variants are ignored, with an explicit exception for the empty example.

Set `OPENAI_MODEL` to override the default `gpt-5.4-mini`. An empty value uses the
default. This cost-conscious model supports Responses, function calling, and
structured outputs. Account access and quota are required.

```sh
python app.py
python app.py --ask "Which category generated the most revenue?"
python app.py --ask "Show monthly revenue trends."
python app.py --ask "What are the top five products by revenue?"
python -m pytest -q
```

The original report runs without credentials. Agent requests use a 30-second
timeout and no automatic SDK retries. Authentication, rate-limit, connection,
and timeout failures produce safe messages without provider bodies or keys.

## Evaluation and limitations

`evaluations.json` contains twelve questions with expected tools and answer facts.
Default pytest uses scripted clients and real SDK response objects, so it incurs
no API charges. These cases check tool dispatch, output facts, and report contracts.
They do not measure a live model's tool-selection accuracy. To evaluate the live
planner, run each question with `--ask` and compare the tools and answer against
the JSON case. Live API testing remains pending because the development environment
has no API key.

Additional tests cover continuation, parallel and sequential calls, bad arguments,
unknown tools, malformed/empty responses, iteration limits, reflection, missing
credentials, duplicate orders, empty CSV data, and byte-identical regeneration.

Tools summarize the complete fictional dataset. Filtered questions, profit,
customer behavior, causes, and forecasts lack supporting tools/data. Unsupported
questions should produce an insufficient-evidence response. The model decides
whether the question is supported, so this classification requires live evaluation.
Reports may omit narrative statements that fail conservative verification.
Revenue uses existing pandas arithmetic and is formatted to cents for display.

Each supported question usually makes three API requests (plan, completion, report)
and can make up to seven with four tool rounds and one revision. Token caps bound
each response, while repeated conversation inputs also incur charges. Aggregated
tool results and the question are sent to OpenAI. Review current pricing before
running live evaluations. As verified on November 5, 2026, the model page lists
USD 0.75 per million input tokens and USD 4.50 per million output tokens.

Implementation follows the official
[Responses function-calling guide](https://developers.openai.com/api/docs/guides/function-calling)
and [GPT-5.4 mini model documentation](https://developers.openai.com/api/docs/models/gpt-5.4-mini).
