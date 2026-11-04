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
Day 1 provides a terminal report for a fictional retail dataset.

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
