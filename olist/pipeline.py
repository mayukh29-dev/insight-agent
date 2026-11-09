"""Validate four local CSVs and build exact-cent weekly merchandise totals."""

from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
import hashlib

import pandas as pd


class ValidationError(ValueError):
    """Source data cannot safely be aggregated."""


FILES = {
    "orders": ("olist_orders_dataset.csv", ["order_id", "order_status", "order_purchase_timestamp"]),
    "items": ("olist_order_items_dataset.csv", ["order_id", "order_item_id", "product_id", "price", "freight_value"]),
    "products": ("olist_products_dataset.csv", ["product_id", "product_category_name"]),
    "translations": ("product_category_name_translation.csv", ["product_category_name", "product_category_name_english"]),
}
STATUSES = {"created", "approved", "invoiced", "processing", "shipped", "delivered", "canceled", "unavailable"}
DATES = ["order_purchase_timestamp", "order_approved_at", "order_delivered_carrier_date", "order_delivered_customer_date", "order_estimated_delivery_date"]


def require(condition, message):
    if not condition:
        raise ValidationError(message)


def key(frame, columns, name):
    require(not frame[columns].isna().any().any(), f"{name}: missing key")
    require(not frame.duplicated(columns).any(), f"{name}: duplicate key {columns}")


def cents(value):
    try:
        amount = Decimal(value)
        require(amount.is_finite() and amount >= 0, "money must be finite and nonnegative")
        require(amount * 100 == (amount * 100).to_integral_value(), "money must have at most two decimal places")
        return int(amount * 100)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError("invalid BRL amount") from exc


def ingest(source):
    """Return (weekly dataframe, quality report). Fail on ambiguous structural data.

    Missing purchase dates are excluded and counted; malformed dates fail. Missing
    categories remain in revenue under explicit fallback labels. No IDs are output.
    """
    tables, hashes = {}, {}
    for name, (filename, columns) in FILES.items():
        path = Path(source) / filename
        require(path.is_file(), f"missing source file: {filename}")
        frame = pd.read_csv(path, dtype="string", keep_default_na=False)
        frame = frame.apply(lambda col: col.str.strip()).replace("", pd.NA)
        require(set(columns) <= set(frame.columns), f"{filename}: required columns {columns}")
        tables[name] = frame
        hashes[filename] = hashlib.sha256(path.read_bytes()).hexdigest()
    orders, items, products, translations = (tables[n] for n in FILES)
    require(not orders.empty, "orders must not be empty")
    key(orders, ["order_id"], "orders")
    key(items, ["order_id", "order_item_id"], "items")
    key(products, ["product_id"], "products")
    key(translations, ["product_category_name"], "translations")
    require(items.product_id.notna().all(), "items: missing product_id")
    require(items.order_item_id.str.fullmatch(r"[1-9][0-9]*").all(), "items: invalid order_item_id")
    require(orders.order_status.isin(STATUSES).all(), "orders: unknown or missing status")
    require(translations.product_category_name_english.notna().all(), "translations: missing English category")
    require(items.order_id.isin(orders.order_id).all(), "items: orphan order_id")
    require(items.product_id.isin(products.product_id).all(), "items: orphan product_id")
    missing_dates = {}
    for column in DATES:
        if column not in orders:
            continue
        raw = orders[column]
        parsed = pd.to_datetime(raw, format="%Y-%m-%d %H:%M:%S", errors="coerce")
        require(not (raw.notna() & parsed.isna()).any(), f"orders: invalid {column}")
        require(parsed.dropna().between(pd.Timestamp("2016-01-01"), pd.Timestamp("2018-12-31 23:59:59")).all(), f"orders: {column} outside historical 2016–2018 window")
        missing_dates[column] = int(parsed.isna().sum())
        orders[column] = parsed
    purchase = orders.order_purchase_timestamp
    for column in DATES[1:]:
        if column in orders:
            require(not (orders[column] < purchase).any(), f"orders: {column} precedes purchase")
    if all(c in orders for c in DATES[2:4]):
        require(not (orders.order_delivered_customer_date < orders.order_delivered_carrier_date).any(), "orders: delivery precedes carrier handoff")
    for column in ["price", "freight_value"]:
        items[column + "_cents"] = items[column].map(cents)
    eligible = orders.order_status.eq("delivered") & purchase.notna()
    selected = orders.loc[eligible]
    require(selected.order_id.isin(items.order_id).all(), "delivered dated order has no items")
    dated = purchase.dropna()
    require(not dated.empty, "no purchase dates to define observation window")
    start, end = dated.min().normalize(), dated.max().normalize()
    # Many-to-one joins preserve exactly one row per item, regardless of order size.
    joined = items.merge(selected[["order_id", "order_purchase_timestamp"]], on="order_id", validate="many_to_one")
    joined = joined.merge(products[["product_id", "product_category_name"]], on="product_id", validate="many_to_one")
    joined = joined.merge(translations[["product_category_name", "product_category_name_english"]], on="product_category_name", how="left", validate="many_to_one")
    missing_category = joined.product_category_name.isna()
    unmapped = ~missing_category & joined.product_category_name_english.isna()
    joined["category"] = joined.product_category_name_english.fillna("unmapped")
    joined.loc[missing_category, "category"] = "unknown"
    joined["week_start"] = joined.order_purchase_timestamp.dt.to_period("W-SUN").dt.start_time
    weeks = pd.date_range(start.to_period("W-SUN").start_time, end.to_period("W-SUN").start_time, freq="7D")
    totals = joined.groupby("week_start").price_cents.agg(lambda values: sum(int(v) for v in values))
    weekly = pd.DataFrame({"week_start": weeks})
    weekly["revenue_brl_cents"] = [int(totals.get(w, 0)) for w in weeks]
    weekly["revenue_brl"] = weekly.revenue_brl_cents.map(lambda v: f"{v // 100}.{v % 100:02d}")
    weekly["partial_week"] = (weekly.week_start < start) | (weekly.week_start + pd.Timedelta(days=6) > end)
    report = {
        "source": "Olist public historical dataset (2016–2018)", "currency": "BRL",
        "revenue_definition": "delivered-order item prices by purchase timestamp; excludes freight; not net of refunds",
        "week_definition": "Monday through Sunday; naive source local timestamps; no timezone conversion",
        "observation_start": str(start.date()), "observation_end": str(end.date()),
        "input_rows": {n: len(f) for n, f in tables.items()},
        "status_counts": dict(sorted(Counter(orders.order_status).items())),
        "missing_dates": missing_dates, "excluded_orders": int((~eligible).sum()),
        "excluded_non_delivered_orders": int(orders.order_status.ne("delivered").sum()),
        "excluded_delivered_missing_purchase_date": int((orders.order_status.eq("delivered") & purchase.isna()).sum()),
        "included_orders": len(selected), "included_items": len(joined),
        "missing_category_items": int(missing_category.sum()), "unmapped_category_items": int(unmapped.sum()),
        "category_revenue_brl_cents": {str(k): int(v) for k, v in joined.groupby("category").price_cents.agg(lambda values: sum(int(v) for v in values)).items()},
        "source_sha256": hashes,
        "warnings": ["Observation bounds are observed purchase dates, not proof of complete source coverage.", "Zero weeks mean no eligible sales in supplied files; sparse weeks may reflect incomplete coverage.", "Boundary weeks may be partial. No forecasting or refunds ledger is available."],
    }
    return weekly, report
