"""Pure dataframe calculations and Plotly figures for the sales workspace."""

import pandas as pd
import plotly.express as px

from tools import category_sales, monthly_revenue, top_products, total_revenue


def filter_sales(sales, categories, start_date, end_date):
    """Return a copy with inclusive calendar dates and the selected categories."""
    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize()
    if start > end:
        raise ValueError("Start date must be on or before end date.")
    dates = sales["date"].dt.normalize()
    return sales.loc[
        sales["category"].isin(categories) & dates.between(start, end)
    ].copy()


def dashboard_metrics(sales):
    """Calculate every KPI from the same dataframe as the charts."""
    return {
        "revenue": float(total_revenue(sales)),
        "transactions": len(sales),
        "units": int(sales["quantity"].sum()),
    }


def dashboard_charts(sales):
    """Use existing deterministic tools for all plotted values."""
    categories = category_sales(sales)
    months = monthly_revenue(sales)
    months["month"] = months["month"].astype(str)
    products = top_products(sales).sort_values("revenue")
    figures = {
        "Revenue by category": px.bar(
            categories, x="category", y="revenue", color_discrete_sequence=["#168579"],
            labels={"category": "Category", "revenue": "Revenue (USD)"},
        ),
        "Monthly revenue": px.line(
            months, x="month", y="revenue", markers=True,
            color_discrete_sequence=["#168579"],
            labels={"month": "Month", "revenue": "Revenue (USD)"},
        ),
        "Top five products": px.bar(
            products, x="revenue", y="product", orientation="h",
            color_discrete_sequence=["#4965a6"],
            labels={"product": "Product", "revenue": "Revenue (USD)"},
        ),
    }
    for title, figure in figures.items():
        figure.update_layout(
            template="plotly_white", height=350, showlegend=False,
            margin=dict(l=10, r=20, t=20, b=10),
            font=dict(family="Arial, sans-serif", color="#243c44", size=13),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        )
        if title == "Top five products":
            figure.update_xaxes(tickprefix="$", tickformat=",.2f")
            figure.update_traces(hovertemplate="%{y}<br>Revenue: $%{x:,.2f}<extra></extra>")
        else:
            figure.update_yaxes(tickprefix="$", tickformat=",.2f")
            figure.update_traces(hovertemplate="%{x}<br>Revenue: $%{y:,.2f}<extra></extra>")
    return figures
