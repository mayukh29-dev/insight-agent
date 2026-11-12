"""All records below are fictional; no downloaded Olist identifiers."""
import json
import subprocess
import sys

import pandas as pd
import pytest

from olist.pipeline import FILES, ValidationError, ingest


@pytest.fixture
def source(tmp_path):
    rows = {
        "orders": [
            ["fiction-a", "delivered", "2017-01-04 10:00:00"],
            ["fiction-b", "delivered", "2017-01-23 10:00:00"],
            ["fiction-c", "canceled", "2017-01-10 10:00:00"],
            ["fiction-d", "delivered", ""],
            ["fiction-e", "unavailable", "2017-01-12 10:00:00"],
        ],
        "items": [
            ["fiction-a", "1", "toy-p", "10.10", "2.00"],
            ["fiction-a", "2", "toy-q", "20.20", "3.00"],
            ["fiction-b", "1", "toy-r", "5.05", "1.00"],
            ["fiction-c", "1", "toy-p", "999.00", "0.00"],
            ["fiction-d", "1", "toy-p", "999.00", "0.00"],
        ],
        "products": [["toy-p", "brinquedos"], ["toy-q", ""], ["toy-r", "fiction-unmapped"]],
        "translations": [["brinquedos", "toys"]],
    }
    for name, data in rows.items():
        filename, columns = FILES[name]
        pd.DataFrame(data, columns=columns).to_csv(tmp_path / filename, index=False)
    return tmp_path


def mutate(source, table, column, value):
    path = source / FILES[table][0]
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    frame.loc[0, column] = value
    frame.to_csv(path, index=False)


def test_exact_totals_gaps_categories_and_exclusions(source):
    weekly, report = ingest(source)
    assert weekly.revenue_brl_cents.tolist() == [3030, 0, 0, 505]
    assert weekly.revenue_brl.tolist() == ["30.30", "0.00", "0.00", "5.05"]
    assert weekly.week_start.dt.strftime("%Y-%m-%d").tolist() == ["2017-01-02", "2017-01-09", "2017-01-16", "2017-01-23"]
    assert weekly.partial_week.tolist() == [True, False, False, True]
    assert report["included_orders"] == 2
    assert report["included_items"] == 3
    assert report["excluded_orders"] == 3
    assert report["missing_dates"]["order_purchase_timestamp"] == 1
    assert report["category_revenue_brl_cents"] == {"toys": 1010, "unknown": 2020, "unmapped": 505}
    assert report["missing_category_items"] == report["unmapped_category_items"] == 1
    again, report_again = ingest(source)
    pd.testing.assert_frame_equal(weekly, again)
    assert report == report_again


@pytest.mark.parametrize("table,column,value", [
    ("orders", "order_status", "mystery"),
    ("orders", "order_status", ""),
    ("orders", "order_purchase_timestamp", "not-a-date"),
    ("orders", "order_purchase_timestamp", "2025-01-01 00:00:00"),
    ("orders", "order_id", ""),
    ("items", "order_id", "orphan"),
    ("items", "product_id", "orphan"),
    ("items", "order_item_id", "0"),
    ("items", "price", "NaN"),
    ("items", "price", "Infinity"),
    ("items", "price", "-1"),
    ("items", "price", "0.001"),
    ("items", "price", ""),
    ("items", "freight_value", "bad"),
    ("translations", "product_category_name_english", ""),
    ("orders", "order_delivered_carrier_date", "not-a-date"),
    ("orders", "order_delivered_customer_date", "not-a-date"),
    ("orders", "order_delivered_customer_date", "2025-01-01 00:00:00"),
])
def test_bad_values_fail(source, table, column, value):
    mutate(source, table, column, value)
    with pytest.raises(ValidationError):
        ingest(source)


@pytest.mark.parametrize("table", list(FILES))
def test_duplicate_keys_fail(source, table):
    path = source / FILES[table][0]
    frame = pd.read_csv(path)
    pd.concat([frame, frame.iloc[:1]]).to_csv(path, index=False)
    with pytest.raises(ValidationError, match="duplicate key"):
        ingest(source)


def test_schema_and_missing_file(source):
    path = source / FILES["items"][0]
    path.write_text("wrong\nvalue\n")
    with pytest.raises(ValidationError, match="required columns"):
        ingest(source)
    path.unlink()
    with pytest.raises(ValidationError, match="missing source file"):
        ingest(source)


def test_empty_eligible_sales_preserve_window(source):
    path = source / FILES["orders"][0]
    frame = pd.read_csv(path)
    frame["order_status"] = "canceled"
    frame.to_csv(path, index=False)
    weekly, report = ingest(source)
    assert weekly.revenue_brl_cents.tolist() == [0, 0, 0, 0]
    assert report["included_items"] == 0


def test_cli_writes_only_aggregates(source):
    output = source / "output"
    subprocess.run([sys.executable, "-m", "olist", "--source", str(source), "--output", str(output)], check=True)
    assert json.loads((output / "quality_report.json").read_text())["currency"] == "BRL"
    assert "fiction-a" not in (output / "weekly_revenue.csv").read_text()


def test_delivered_order_without_items_fails(source):
    path = source / FILES["items"][0]
    frame = pd.read_csv(path)
    frame.loc[frame.order_id.ne("fiction-b")].to_csv(path, index=False)
    with pytest.raises(ValidationError, match="no items"):
        ingest(source)


def test_no_dated_observation_window_fails(source):
    path = source / FILES["orders"][0]
    frame = pd.read_csv(path)
    frame["order_purchase_timestamp"] = ""
    frame.to_csv(path, index=False)
    with pytest.raises(ValidationError, match="no purchase dates"):
        ingest(source)


def test_optional_dates_and_late_delivery(source):
    path = source / FILES["orders"][0]
    frame = pd.read_csv(path)
    frame["order_delivered_carrier_date"] = ""
    frame["order_delivered_customer_date"] = ""
    frame["order_estimated_delivery_date"] = ""
    frame.loc[0, "order_delivered_carrier_date"] = "2017-01-05 10:00:00"
    frame.loc[0, "order_estimated_delivery_date"] = "2017-01-06 10:00:00"
    frame.loc[0, "order_delivered_customer_date"] = "2017-01-07 10:00:00"
    frame.to_csv(path, index=False)
    assert ingest(source)[1]["missing_dates"]["order_delivered_customer_date"] == 4
    frame.loc[0, "order_delivered_customer_date"] = "2017-01-04 11:00:00"
    frame.to_csv(path, index=False)
    weekly, report = ingest(source)
    assert report["timestamp_inconsistencies"]["customer_delivery_precedes_carrier_handoff"] == 1
    assert report["orders_with_timestamp_inconsistencies"] == 1
    assert weekly.revenue_brl_cents.tolist() == [3030, 0, 0, 505]


def test_timestamp_anomalies_reported_without_changing_sources_or_revenue(source):
    baseline, _ = ingest(source)
    path = source / FILES["orders"][0]
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    for column in ["order_approved_at", "order_delivered_carrier_date", "order_delivered_customer_date", "order_estimated_delivery_date"]:
        frame[column] = ""
        frame.loc[0, column] = "2017-01-03 10:00:00"
    frame.loc[0, "order_delivered_customer_date"] = "2017-01-02 10:00:00"
    # Count an anomaly in an excluded order too, once per order rather than item.
    frame.loc[2, "order_delivered_carrier_date"] = "2017-01-09 10:00:00"
    # Missing purchase date is not an ordering anomaly.
    frame.loc[3, "order_delivered_carrier_date"] = "2017-01-01 10:00:00"
    frame.to_csv(path, index=False)
    original_bytes = {filename: (source / filename).read_bytes() for filename, _ in FILES.values()}
    output = source / "output"
    subprocess.run([sys.executable, "-m", "olist", "--source", str(source), "--output", str(output)], check=True)
    report = json.loads((output / "quality_report.json").read_text())
    assert report["timestamp_inconsistencies"] == {
        "order_approved_at_precedes_purchase": 1,
        "order_delivered_carrier_date_precedes_purchase": 2,
        "order_delivered_customer_date_precedes_purchase": 1,
        "order_estimated_delivery_date_precedes_purchase": 1,
        "customer_delivery_precedes_carrier_handoff": 1,
    }
    assert report["orders_with_timestamp_inconsistencies"] == 2
    assert any("ordering inconsistencies" in warning for warning in report["warnings"])
    pd.testing.assert_frame_equal(baseline, ingest(source)[0])
    assert {filename: (source / filename).read_bytes() for filename in original_bytes} == original_bytes


def test_no_timestamp_anomalies_with_absent_or_missing_optional_dates(source):
    assert ingest(source)[1]["timestamp_inconsistencies"] == {}
    mutate(source, "orders", "order_delivered_carrier_date", "")
    report = ingest(source)[1]
    assert report["timestamp_inconsistencies"] == {"order_delivered_carrier_date_precedes_purchase": 0}
    assert report["orders_with_timestamp_inconsistencies"] == 0
    assert not any("ordering inconsistencies" in warning for warning in report["warnings"])


def test_weekly_order_coverage_explains_gaps_and_exclusions_without_item_duplication(source):
    _, report = ingest(source)
    rows = report["weekly_order_coverage"]
    assert [r["recorded_orders"] for r in rows] == [1, 2, 0, 1]
    assert [r["eligible_delivered_orders"] for r in rows] == [1, 0, 0, 1]
    assert [r["eligible_items"] for r in rows] == [2, 0, 0, 1]
    assert rows[1]["status_counts"]["canceled"] == 1
    assert rows[1]["status_counts"]["unavailable"] == 1
    assert sum(r["recorded_orders"] for r in rows) == 4  # missing purchase date separately excluded
    assert "fiction-a" not in json.dumps(rows)


def test_zero_priced_items_are_recorded_as_eligible_sales(source):
    path = source / FILES["items"][0]
    frame = pd.read_csv(path)
    frame.loc[frame.order_id.eq("fiction-a"), "price"] = 0
    frame.to_csv(path, index=False)
    original = path.read_bytes()
    weekly, report = ingest(source)
    assert weekly.revenue_brl_cents.iloc[0] == 0
    assert report["weekly_order_coverage"][0]["eligible_delivered_orders"] == 1
    assert report["weekly_order_coverage"][0]["eligible_items"] == 2
    assert path.read_bytes() == original
