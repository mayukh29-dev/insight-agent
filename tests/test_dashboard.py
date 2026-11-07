"""Check plotted values and filtering against hand-calculated transactions."""

from datetime import date
from io import StringIO

import pytest

from dashboard import dashboard_charts, dashboard_metrics, filter_sales
from generate_data import DATA_PATH
from tools import load_sales


@pytest.fixture
def sales():
    return load_sales(StringIO(
        "date,order_id,product,category,quantity,unit_price\n"
        "2025-01-01,1,Mug,Kitchen,2,5.50\n"
        "2025-01-02,2,Lamp,Home,1,20\n"
        "2025-03-01,3,Mug,Kitchen,3,5.50\n"
    ))


def test_bundled_metrics():
    assert dashboard_metrics(load_sales(DATA_PATH)) == {
        "revenue": 12951.00, "transactions": 240, "units": 717,
    }


def test_filters_are_inclusive_and_do_not_mutate(sales):
    result = filter_sales(sales, ["Kitchen"], date(2025, 1, 1), date(2025, 1, 1))
    assert dashboard_metrics(result) == {"revenue": 11, "transactions": 1, "units": 2}
    result.loc[:, "quantity"] = 99
    assert sales["quantity"].tolist() == [2, 1, 3]


def test_combined_filter_totals(sales):
    result = filter_sales(sales, ["Home", "Kitchen"], date(2025, 1, 1), date(2025, 1, 31))
    assert dashboard_metrics(result) == {"revenue": 31, "transactions": 2, "units": 3}


def test_empty_filter(sales):
    result = filter_sales(sales, [], date(2025, 1, 1), date(2025, 3, 1))
    assert result.empty
    assert dashboard_metrics(result) == {"revenue": 0, "transactions": 0, "units": 0}


def test_reversed_dates(sales):
    with pytest.raises(ValueError, match="Start date"):
        filter_sales(sales, ["Home"], date(2025, 3, 1), date(2025, 1, 1))


def test_chart_values_and_month_gap(sales):
    figures = dashboard_charts(sales)
    assert list(figures["Monthly revenue"].data[0].x) == ["2025-01", "2025-02", "2025-03"]
    assert list(figures["Monthly revenue"].data[0].y) == [31, 0, 16.5]
    assert list(figures["Revenue by category"].data[0].y) == [27.5, 20]
    assert list(figures["Top five products"].data[0].x) == [20, 27.5]


def test_filtered_charts_match_kpis(sales):
    filtered = filter_sales(sales, ["Kitchen"], date(2025, 1, 1), date(2025, 3, 1))
    figures = dashboard_charts(filtered)
    assert sum(figures["Revenue by category"].data[0].y) == 27.5
    assert dashboard_metrics(filtered)["revenue"] == 27.5
