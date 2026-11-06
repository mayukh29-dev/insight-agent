"""Presentation keeps source claims intact and demo mode stays offline."""

import pytest

from generate_data import DATA_PATH
from presentation import SAMPLE_QUESTIONS, answer_question, build_demo_reports, parse_report
from tools import load_sales


def test_adapter_preserves_report_claims():
    text = ("Question\nRevenue?\n\nTools executed\ntotal_revenue, category_sales\n\nKey metrics\n"
            "- Total revenue is USD 12951.00\n\nBusiness insights\n- Review the category mix.\n\n"
            "Recommendations\n- Investigate availability.\n\nLimitations\n- Fictional data only.")
    report = parse_report(text, "Revenue?")
    assert report.tools == ["total_revenue", "category_sales"]
    assert report.metrics == ["Total revenue is USD 12951.00"]
    assert report.summary == "Review the category mix."
    assert report.recommendations == ["Investigate availability."]
    assert report.limitations == ["Fictional data only."]
    assert report.raw == text


def test_unsupported_report_and_unexpected_format():
    report = parse_report("Question\nProfit?\n\nTools executed\nNone\n\nLimitations\nInsufficient evidence.", "Profit?")
    assert not report.tools
    assert report.summary == "Insufficient evidence."
    raw = parse_report("Unexpected format", "Question")
    assert raw.raw == "Unexpected format"
    assert not raw.metrics


def test_demo_answers_use_calculations_and_never_call_live():
    sales = load_sales(DATA_PATH)
    reports = build_demo_reports(sales)

    def forbidden(*args):
        pytest.fail("Demo mode attempted a live request")

    report = answer_question(SAMPLE_QUESTIONS[0], sales, "Demo Mode", reports, forbidden)
    assert report.summary == "Electronics generated the most revenue at $4,196.50."
    assert report.tools == ["category_sales"]
    assert reports[SAMPLE_QUESTIONS[1]].summary == "2025-03 has the highest monthly revenue at $2,455.50."
    assert "$3,152.50" in reports[SAMPLE_QUESTIONS[2]].summary
    assert "$12,951.00" in reports[SAMPLE_QUESTIONS[3]].summary
    assert "No AI request" in report.limitations[0]
    unsupported = answer_question("Profit?", sales, "Demo Mode", reports, forbidden)
    assert not unsupported.metrics
    assert "no precomputed demo answer" in unsupported.summary


def test_demo_recalculates_when_evidence_changes():
    sales = load_sales(DATA_PATH).iloc[:1]
    report = build_demo_reports(sales)[SAMPLE_QUESTIONS[3]]
    assert report.metrics == [f"Total revenue: ${sales.iloc[0]['quantity'] * sales.iloc[0]['unit_price']:,.2f}"]


def test_live_routing_uses_full_dataframe():
    sales = load_sales(DATA_PATH)
    calls = []

    def live(question, data):
        calls.append((question, data))
        return "Question\nRevenue?\n\nTools executed\ntotal_revenue\n\nKey metrics\n- USD 12951.00"

    result = answer_question("Revenue?", sales, "Live Mode", {}, live)
    assert calls[0][1] is sales
    assert result.metrics == ["USD 12951.00"]


def test_empty_question_and_invalid_mode():
    with pytest.raises(ValueError, match="Enter a business question"):
        answer_question(" ", None, "Demo Mode", {})
    with pytest.raises(ValueError, match="Choose Demo Mode"):
        answer_question("Revenue?", None, "Unknown", {})
