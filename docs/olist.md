# Olist historical ingestion — Phase 1

This optional module uses **Brazilian E-Commerce Public Dataset by Olist**, an
anonymized public marketplace dataset covering 2016–2018, published by Olist on
[Kaggle](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce).
There is no affiliation, live connection, internal access, or claim about current
company performance. The original synthetic dataset and application stay separate.

## Download and run

1. Visit the Kaggle link above. Sign in or create a Kaggle account if requested.
2. Review the dataset page and its current terms before downloading. The publisher
   lists **CC BY-NC-SA 4.0**, checked November 9, 2026. See the
   [license](https://creativecommons.org/licenses/by-nc-sa/4.0/) for attribution,
   noncommercial use, and share-alike conditions. Public availability does not mean
   unrestricted commercial use. This repository does not redistribute the source.
3. Use Kaggle's Download button, unzip locally, and create `data/olist/raw/` in
   your repository checkout. Copy these four files directly into that folder:

   - `olist_orders_dataset.csv`
   - `olist_order_items_dataset.csv`
   - `olist_products_dataset.csv`
   - `product_category_name_translation.csv`

4. With the project's environment activated and requirements installed, run:

   ```sh
   python -m olist --source data/olist/raw --output data/olist/processed
   python -m pytest -q
   ```

No Kaggle API token or OpenAI key is needed. No additional dependency is introduced.
The command writes `weekly_revenue.csv` and `quality_report.json`. Use the default
paths: `data/olist/` and source filenames are ignored by Git. Keep archives and
other downloaded tables outside Git too. Never force-add raw files or identifiers.
Tests generate tiny fictional CSVs in temporary folders and require no download.

## What the pipeline does

`olist/pipeline.py` reads strings first, trims whitespace, checks required columns,
and validates keys before joining anything. Orders must have one row per order;
items must have one row per `(order_id, order_item_id)`; products and translations
must have unique keys. Missing keys, unknown statuses, orphan references, conflicting
translations, malformed dates, and invalid money stop processing with an error.
Errors do not echo source identifiers. Extra source columns are allowed.

The required columns are declared in `FILES` in the module. Optional order approval,
carrier, customer delivery and estimated delivery timestamps are validated when
present. All supplied dates must be valid source timestamps in 2016–2018.
Optional timestamps before purchase and customer delivery before carrier handoff
are counted in `timestamp_inconsistencies` in `quality_report.json`, with a warning
when any occur. Counts cover all input orders, including excluded statuses, and
can overlap; `orders_with_timestamp_inconsistencies` counts affected orders once.
Absent optional columns have no check entry; missing timestamps do not count as
ordering inconsistencies. These anomalies do not change source files, timestamps,
or purchase-based revenue eligibility. Malformed and out-of-range dates still fail.
Late deliveries
after the estimated date are allowed. Missing dates are counted per column.
Missing purchase dates exclude the order from revenue; optional missing milestones
are reported without silently removing otherwise eligible orders. Source timestamps
are treated as naive local timestamps, without guessing a timezone conversion.

Only **delivered** orders with a purchase timestamp contribute revenue. Canceled,
unavailable, created, approved, invoiced, processing and shipped orders are excluded.
The quality report gives status counts, included order/item counts and exclusions.
A delivered, dated order without any items is an error rather than zero revenue.

Each item row represents one sold item. Revenue is the sum of `price`, in Brazilian
reais (**BRL**), for eligible items. Freight is validated separately and excluded.
Payments and reviews are never joined. This avoids multiplying item rows when an
order has several items, payments, or reviews. Every join checks its many-to-one
relationship. This is merchandise value for delivered orders, **not profit, cash
collections, or audited net revenue**. Refunds/returns are not represented by these
four tables and no refund deduction is invented.

Money is converted to integer centavos with Decimal validation (no rounding of
sub-cent input), then summed using integers. `revenue_brl_cents` is the exact numeric
forecasting input; `revenue_brl` is its two-decimal display form. Negative, missing,
nonfinite, and sub-cent prices or freight fail validation.

Products are mapped from Portuguese categories to English using the translation
file. Missing product categories become `unknown`; categories lacking translations
become `unmapped`. Both stay in revenue and are counted explicitly. Category totals
in the report allow reconciliation to the overall weekly total; source IDs are not
exported. The report also records input row counts and SHA-256 file fingerprints
so another run can be compared to the same inputs.

`weekly_order_coverage` lists recorded order counts, eligible delivered-order counts,
eligible item counts and status counts for every purchase week. Multi-item orders
count once. It distinguishes empty weeks from weeks with only excluded statuses
and zero-priced eligible sales. A lack of records is not proof of genuine zero
marketplace sales, and calendar-complete weeks are not verified source-complete.
These are additional diagnostics; original CSVs and weekly revenue are unchanged.

## Weeks and future forecasting

Weeks run Monday through Sunday, labeled by Monday's date, using **purchase time**,
even if delivery occurred later. The observation window is the earliest through
latest valid purchase date across all orders, including excluded statuses. Every
week in that window is preserved, including weeks with zero eligible sales. If no
purchase date exists, the pipeline fails rather than inventing an observation window.
If no eligible sales exist but dated orders do, it produces an all-zero series.

`partial_week` flags weeks extending beyond the observed date bounds. These flags
describe bounds, not verified completeness: supplied files may omit transactions,
and sparse early/late history can contain incomplete weeks even inside those bounds.
Zero means no eligible sales in the supplied data, not proof that the marketplace
was inactive. Review source coverage, quality warnings, gaps and partial weeks
before choosing a Phase 2 training window. Do not extrapolate 2018 history to today's
Olist performance. No model, forecasts, agent tools or UI integration are added here.
