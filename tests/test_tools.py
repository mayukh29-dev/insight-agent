"""Check sales metrics against small, hand-calculated examples."""

import pytest

from tools import category_sales, load_sales, monthly_revenue, top_products, total_revenue

HEADER = "date,order_id,product,category,quantity,unit_price\n"


@pytest.fixture
def sales(tmp_path):
    path = tmp_path / "sales.csv"
    path.write_text(
        HEADER
        + "2025-01-01,001,Mug,Kitchen,2,5.50\n"
        + "2025-01-02,002,Lamp,Home,1,20\n"
        + "2025-03-01,003,Mug,Kitchen,3,5.50\n"
        + "2025-03-02,004,Tray,Kitchen,1,4\n"
        + "2025-03-03,005,Clock,Home,1,10\n"
        + "2025-03-04,006,Pen,Office,1,4\n"
        + "2025-03-05,007,Pad,Office,1,3\n",
        encoding="utf-8",
    )
    return load_sales(path)


def test_load_sales_preserves_order_id(sales):
    assert sales.loc[0, "order_id"] == "001"


def test_total_revenue(sales):
    # 11 + 20 + 16.50 + 4 + 10 + 4 + 3
    assert total_revenue(sales) == 68.50


def test_category_sales(sales):
    assert list(category_sales(sales).itertuples(index=False, name=None)) == [
        ("Kitchen", 6, 31.50),
        ("Home", 2, 30),
        ("Office", 2, 7),
    ]


def test_monthly_revenue(sales):
    trend = monthly_revenue(sales)
    assert trend["month"].astype(str).tolist() == ["2025-01", "2025-02", "2025-03"]
    assert trend["revenue"].tolist() == [31, 0, 37.50]


def test_top_products(sales):
    assert list(top_products(sales).itertuples(index=False, name=None)) == [
        ("Mug", 27.50), ("Lamp", 20), ("Clock", 10), ("Pen", 4), ("Tray", 4),
    ]


@pytest.mark.parametrize(("date", "quantity", "price", "error"), [
    ("2025-02-30", "1", "2", "date"),
    ("", "1", "2", "date"),
    ("2025-01-01", "1", "-2", "unit_price"),
    ("2025-01-01", "1", "inf", "unit_price"),
    ("2025-01-01", "1", "", "unit_price"),
    ("2025-01-01", "0", "2", "quantity"),
    ("2025-01-01", "-1", "2", "quantity"),
    ("2025-01-01", "1.5", "2", "quantity"),
    ("2025-01-01", "two", "2", "quantity"),
    ("2025-01-01", "", "2", "quantity"),
])
def test_invalid_rows(tmp_path, date, quantity, price, error):
    path = tmp_path / "invalid.csv"
    path.write_text(HEADER + f"{date},001,Mug,Kitchen,{quantity},{price}\n", encoding="utf-8")
    with pytest.raises(ValueError, match=error):
        load_sales(path)


def test_missing_columns(tmp_path):
    path = tmp_path / "missing.csv"
    path.write_text("date,order_id\n2025-01-01,001\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Missing required columns: category, product, quantity, unit_price"):
        load_sales(path)
