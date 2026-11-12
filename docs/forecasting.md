# Phase 2: honest weekly revenue forecasting

This optional module learns from Olist's **historical 2016–2018 public dataset**.
It does not forecast current Olist operations, connect to a company system, or make
OpenAI calls. The synthetic demo, application CLI, Live Mode, Streamlit UI, Tableau,
and Phase 1 ingestion are unchanged. UI and agent tools belong to a later phase.

## Run on your downloaded files in PowerShell

Open PowerShell in your local `insight-agent` repository checkout. These commands
assume Python 3.11+ is available through the Windows `py` launcher. After this PR is
merged, use `main`; before merging, check out the review branch as shown:

```powershell
git fetch origin
git switch feat/olist-weekly-forecasting
py -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-forecast.txt
New-Item -ItemType Directory -Force .\data\olist\raw | Out-Null
```

Manually download and unzip the dataset from the publisher's
[Kaggle page](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce), respecting
its CC BY-NC-SA 4.0 terms. See [Phase 1 instructions](olist.md) for provenance,
license and definitions. Copy these four files into `data\olist\raw`:

- `olist_orders_dataset.csv`
- `olist_order_items_dataset.csv`
- `olist_products_dataset.csv`
- `product_category_name_translation.csv`

Then run (each command below occupies one line):

```powershell
& .\.venv\Scripts\python.exe -m olist --source .\data\olist\raw --output .\data\olist\processed
& .\.venv\Scripts\python.exe -m olist.forecast --input .\data\olist\processed\weekly_revenue.csv --quality .\data\olist\processed\quality_report.json --output .\data\olist\processed\forecast_results.json
& .\.venv\Scripts\python.exe -m pytest -q
& .\.venv\Scripts\python.exe -m pip check
$report = Get-Content .\data\olist\processed\forecast_results.json -Raw | ConvertFrom-Json
$report.reconciliation
$report.evaluation
$report.scores | ConvertTo-Json -Depth 5
$report.selection
$report.next_week_illustration | ConvertTo-Json -Depth 5
$report.coverage.recent_source_coverage | ConvertTo-Json -Depth 8
$quality = Get-Content .\data\olist\processed\quality_report.json -Raw | ConvertFrom-Json
$quality.weekly_order_coverage | Select-Object -Last 12 | ConvertTo-Json -Depth 5
$report.backtest_tail_sensitivity | ConvertTo-Json -Depth 6
```

No API key is needed. NumPy is the only explicitly added optional dependency;
it is already a pandas dependency, and is used directly for the small ridge model.
No scikit-learn installation is necessary. Keep `data/olist/` local: Git ignores raw
files, processed history and generated forecasts. Do not force-add generated data,
downloaded archives, source identifiers, or fitted models to Git. Only fictional
fixtures constructed inside tests are tracked. The forecast command validates
everything before writing and refuses to overwrite either input file.

## First check the money and dates

`olist/forecast.py` checks the exact four-column weekly schema and the Phase 1
quality report's currency, source, revenue definition, week definition, source-file
fingerprints and observation bounds. Weeks must be unique, sorted Mondays without
gaps. Monetary cent values must be nonnegative integers, within the exact float
integer range used for modeling; the two-decimal BRL column must agree with cents.
Unknown partial flags, negative/nonfinite money and malformed dates fail.

Before excluding any boundary weeks, the module adds **every weekly integer-cent
value** and compares it with the category-revenue cent totals in the quality report.
A mismatch stops the run. `reconciliation` records both totals and a passing flag.
This checks internal agreement, not independent correctness against a payment or
refund ledger. Phase 1 defines this measure as delivered-order item prices assigned
to purchase time, excluding freight, not net of refunds and not profit.

The report includes source-quality counts/warnings, input SHA-256 fingerprints,
source CSV fingerprints, code fingerprint and Python/pandas/NumPy versions. These
help reproduce a run without exporting identifiers. Preserve your original quality
report alongside the forecast report. Matching hashes establish file identity,
not external authenticity or guaranteed complete coverage.

## A fixed chronological experiment

We remove only partial boundary weeks from **both training and scoring**, using
flags checked against observation dates. They still count in reconciliation and
appear in coverage diagnostics. Missing or inconsistent flags fail rather than
being guessed. A flag of false means inside observed bounds, not verified source
completeness.

The first **12 complete weeks** are the fixed training warm-up. Each later complete
week is a target, and every method predicts that same week using only earlier
complete weeks. After scoring, that week's actual becomes available for the next
origin. This is expanding-window, one-week-ahead backtesting. At least **16 complete
weeks** are required: 12 initial training weeks and at least 4 scoring weeks.

This rule supplies eight initial supervised training examples after building four
lags. It is a deliberately modest minimum, not evidence that eight examples suffice
for reliable business forecasts. The window rule is fixed before inspecting scores;
there is no data-driven start-date search. The report states actual evaluation
dates and counts for your files.

Early ramp-up, zeros and spikes are **not silently removed**. The first 12 observed
weeks and their values are listed to help inspect sparse history. All zero weeks
are listed. After eight observations, an outlier flag compares the target with the
prior-history interquartile range: below Q1−3×IQR or above Q3+3×IQR. With IQR zero,
any departure is flagged. These diagnostic flags never remove observations, alter
features or change the evaluation window. In particular, the whole-series coverage
summary is not a model input. Review it alongside source-quality warnings.

## Three methods on identical target weeks

| Method | How it predicts next week |
| --- | --- |
| `last_week` | Repeats the last complete week's revenue. |
| `mean_4` | Averages the last four complete weeks. |
| `ridge` | Learns a regularized linear relationship between past weekly values and the following week's revenue. |

Ridge is a real fitted machine-learning model, implemented with NumPy's small
linear-system solver. Its features are lags 1, 2, 3 and 4 plus the mean of those
four lags. For each training row, all five features come from earlier weeks. The
model standardizes features using **only that origin's training rows**, centers
training targets, and fits squared error plus a fixed ridge penalty `alpha=1`.
The intercept is not penalized. Constant features use scale one. It refits from
scratch at each origin; no random split, random seed, parameter search, future
targets or future rolling averages are involved. The final fit's coefficients,
means, scales and training sample count are recorded for inspection.

Predictions are clipped at zero and rounded to the nearest cent (ties to even),
with the same rounding policy applied to all methods. Keep runtime versions fixed
to reproduce numerical results; numerical libraries/platform changes can affect
floating-point calculations near a rounding boundary. No 52-week seasonal baseline
is added: the required baselines permit comparison even on short history.

## Reading the results honestly

`forecast_results.json` separates `actual_brl_cents` from each method's
`predictions_brl_cents` for every historical target. It also records training-end
dates and history lengths. Divide cent values by 100 for BRL.

- **MAE in BRL:** average absolute prediction error. Lower is better.
- **WAPE percent:** 100 × sum of absolute errors ÷ sum of actual revenue. When all
  actuals are zero, it is JSON `null` with an explanation, even for perfect zeros.
- **Bias in BRL:** average (prediction minus actual); positive means overprediction.

All methods share the same evaluation dates and denominators. Selection chooses
the lowest total absolute error (equivalent to lowest MAE here). Ties favor
`last_week`, then `mean_4`, then `ridge`. The report explicitly says whether ridge
`wins`, `ties` or `loses` against the best simple baseline. A machine-learning model
is not presumed better. Selection and reported scores use the same backtests, so
the winner's score is **not an independent post-selection test**. There is no claim
that the winner will remain best outside this experiment.

The final selected method is refit on all calendar-complete history. Its one-week-ahead
illustration targets the next week, but **no point predictions are published** if that
target overlaps a known partial boundary week or recent coverage looks unreliable.
`next_week_illustration.available` is false, `status` is `unavailable`, both
prediction fields are JSON `null`, and `unavailable_reasons` explains why. Null
means unavailable, never R$0.00. The CLI prints this status as well. With no warning
signal, the status is `illustrative_only`, not a certification of source completeness.
These are historical predictions, not actual revenue and not 2026 company forecasts.
No prediction intervals are offered: no calibrated uncertainty has been established.

## Calendar bounds, missing coverage and real zero values

Phase 1 fills calendar weeks between the earliest and latest valid purchases
**across all order statuses**. Revenue includes only delivered-order items. Thus a
week ending within those bounds can be calendar-complete but have no recorded
orders, only canceled/unavailable/other excluded orders, or delivered items totaling
zero. A calendar flag cannot establish that the extract covers all eligible sales.
An empty sum is recorded as zero; it does not prove that true marketplace sales
were zero. Neither a declining series nor zero revenue alone proves missing data.

The regenerated Phase 1 quality report now includes `weekly_order_coverage`:
counts of recorded orders, eligible delivered orders, eligible items and order
statuses, grouped by purchase week. Orders are counted before item joins, so
multi-item orders are counted once. Missing purchase dates remain separately
reported. Source CSVs and all weekly revenue values are unchanged.

The forecast report validates these optional counts when supplied and explains
the last four calendar-complete weeks as one of:

- Positive recorded item value.
- Eligible zero-value item sales recorded (e.g. all item prices are zero).
- Only ineligible order statuses recorded.
- No orders recorded in the files.
- Zero recorded value with unknown cause (older quality report without counts).

These labels describe the files, **not verified real-world demand or completeness**.
Regenerate ingestion using the commands above to get the order-count evidence;
old valid quality reports still work, with unknown causes explicitly marked.
`source_completeness` remains `unverified` in each case. Full completeness requires
independent source knowledge, which this public extract does not provide.

The availability guard uses fixed conservative rules, without changing any data:

1. Suppress a next-week illustration for any known partial target.
2. Mark recent source coverage suspicious when the last four calendar-complete
   weeks average at most 10% of the preceding eight-week average, provided the
   preceding average is positive.
3. Also flag at least two trailing zero weeks following any positive history, or
   a latest week with no eligible orders in the supplied count evidence after
   positive revenue in the preceding eleven weeks.

Any suspicious recent-coverage signal suppresses all three next-week point
predictions, including nonzero model outputs. The reasons, exact recent values,
last positive week, zero-run length and available status evidence are reported.
These rules can also flag a genuine closure or downturn: they express caution,
not a diagnosis of missing data. Stable all-zero history, isolated zeros without
additional suspicious evidence, and early sparse weeks are not automatically
rejected. Recorded zeros always remain in reconciliation, training and the
original backtest. There is no zero imputation, file repair, retargeting to an
earlier convenient date, or change to the winning-method rule.

`backtest_tail_sensitivity` rescoring removes exactly the final four target weeks
from the **already computed** predictions, without refitting. It requires at least
four remaining targets and reports its own dates/count and scores. This diagnostic
never determines the primary winner. It shows how endpoint values affect reported
errors; it is not a coverage-corrected evaluation or proof of better performance.
The unchanged primary scores still include early sparse and suspicious trailing
weeks. Both sets can be compromised by incomplete source coverage; WAPE is an
error measure, not an accuracy percentage.

## Verification and results available in this PR

Real Olist CSVs remain unavailable in this development checkout. The following
results were supplied in the [PR #9 review](https://github.com/mayukh29-dev/insight-agent/pull/9#pullrequestreview-5853992724),
not independently rerun here. They cover **98 targets, 2016-11-28 to 2018-10-08**:

| Method | Reported MAE (BRL) | Reported WAPE |
| --- | ---: | ---: |
| last_week | 23,592.7231 | 17.5410% |
| mean_4 | 30,778.9887 | 22.8839% |
| ridge | 27,666.5027 | 20.5698% |

The primary winner is last_week; **ridge loses**. These reported errors are not
improved or replaced by this coverage fix. For the same weekly files, the primary
backtest calculations/window remain unchanged. The review reported four trailing
weeks averaging zero, a zero in the last calendar-complete week (2018-10-08), and
partial boundaries 2016-08-29 and 2018-10-15. Last-week repeated that zero into the
partial target 2018-10-15. The new guard suppresses that illustration for **both**
known partial overlap and suspected recent coverage. No independent claim is made
about the exact missing/excluded raw order counts: regenerate ingestion and inspect
the new weekly counts to distinguish absent records from excluded statuses and
zero-priced eligible items. The fixed sensitivity view will rescore 94 targets
for that 98-target run, without changing selection. Its real numerical scores
remain to be computed locally using the commands above.

Deterministic tests cover hand-calculated baselines/metrics, reconciliation failures,
future-data perturbations, reproducibility, constant/zero/sparse series, retained
outliers, partial weeks, minimum history, malformed inputs, model ranking/losses,
CLI output, input preservation and the actual ingestion-to-forecast file contract.
Existing application tests are run alongside these tests. The historical extract's
final delivered statuses may not have been known in real time, so backtesting assumes
weekly aggregates are available after each week; it does not simulate reporting delays.

Original Phase 2 verification: **163 tests passed**, including 45 forecasting cases;
`pip check` found no broken requirements. The run used Python 3.15.2, pandas 3.1.1
and NumPy 2.5.4 on Windows. These are verification versions, not a guarantee of
identical floating-point results across all library/platform combinations.

Coverage-fix verification: **182 tests passed**, including 62 forecasting cases
and 33 ingestion cases; `pip check` and `git diff --check` passed. Regressions
cover the October 8/15 endpoint shape, partial-target suppression, trailing zero
and nonzero collapses, legitimate zero-valued sales, old quality reports without
order evidence, count validation, fixed endpoint sensitivity and JSON null output.
