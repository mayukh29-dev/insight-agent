"""Load retail transactions and calculate deterministic sales metrics."""

import pandas as pd

REQUIRED_COLUMNS = ("date", "order_id", "product", "category", "quantity", "unit_price")


def load_sales(path):
    """Read a CSV and raise ValueError when required transaction data is invalid."""
    sales = pd.read_csv(path, dtype="string", keep_default_na=False)
    missing = sorted(set(REQUIRED_COLUMNS) - set(sales.columns))
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    dates = pd.to_datetime(sales["date"], format="%Y-%m-%d", errors="coerce")
    if dates.isna().any():
        raise ValueError("Invalid date. Use YYYY-MM-DD calendar dates.")

    quantity = pd.to_numeric(sales["quantity"], errors="coerce")
    if not (quantity.notna() & quantity.gt(0) & quantity.mod(1).eq(0)).all():
        raise ValueError("Invalid quantity. Use positive whole numbers.")

    price = pd.to_numeric(sales["unit_price"], errors="coerce")
    if not (price.notna() & price.ge(0) & price.lt(float("inf"))).all():
        raise ValueError("Invalid unit_price. Use finite, nonnegative numbers.")

    for column in ("order_id", "product", "category"):
        sales[column] = sales[column].str.strip()
        if sales[column].eq("").any():
            raise ValueError(f"Missing value in {column}.")

    return sales.assign(date=dates, quantity=quantity, unit_price=price)


def _with_revenue(sales):
    """Return a copy with revenue for each transaction."""
    return sales.assign(revenue=sales["quantity"] * sales["unit_price"])


def total_revenue(sales):
    """Sum transaction revenue across all rows."""
    return _with_revenue(sales)["revenue"].sum()


def category_sales(sales):
    """Return units sold and revenue per category, highest revenue first."""
    return (
        _with_revenue(sales)
        .groupby("category", as_index=False)
        .agg(units_sold=("quantity", "sum"), revenue=("revenue", "sum"))
        .sort_values(["revenue", "category"], ascending=[False, True], ignore_index=True)
    )


def monthly_revenue(sales):
    """Return revenue for each calendar month in chronological order."""
    months = sales["date"].dt.to_period("M")
    revenue = _with_revenue(sales).groupby(months)["revenue"].sum()
    if not revenue.empty:
        all_months = pd.period_range(revenue.index.min(), revenue.index.max(), freq="M")
        revenue = revenue.reindex(all_months, fill_value=0)
    return revenue.rename_axis("month").reset_index()


def top_products(sales):
    """Return up to five products by revenue, breaking ties alphabetically."""
    return (
        _with_revenue(sales)
        .groupby("product", as_index=False)["revenue"].sum()
        .sort_values(["revenue", "product"], ascending=[False, True], ignore_index=True)
        .head(5)
    )
