"""Offline integration tests with real SDK response objects and scripted clients."""

import copy
import json
from types import SimpleNamespace
from pathlib import Path

import pytest
from openai import APITimeoutError, OpenAI
from openai.types.responses import Response

from agent import AgentError, TOOL_SCHEMAS, build_facts, execute_tool, run_agent, verify_report
from generate_data import DATA_PATH, generate_sales
from tools import load_sales


def response(*calls, text="", status="completed"):
    output = [{"type": "function_call", "name": name, "arguments": arguments,
               "call_id": call_id} for name, arguments, call_id in calls]
    if text:
        output.append({"type": "message", "role": "assistant", "status": "completed",
                       "id": "msg_test", "content": [{"type": "output_text", "text": text,
                                                       "annotations": []}]})
    return Response.model_validate({"id": "resp_test", "created_at": 0, "model": "test",
                                    "object": "response", "output": output, "status": status,
                                    "parallel_tool_calls": True, "tool_choice": "auto", "tools": []})


def draft(insight="{{total_revenue}}"):
    return response(text=json.dumps({"insights": [insight], "recommendations": [],
                                     "limitations": ["Fictional dataset only."]}))


class FakeClient:
    def __init__(self, *replies):
        self.replies = iter(replies)
        self.requests = []
        self.responses = SimpleNamespace(create=self.create)

    def create(self, **kwargs):
        self.requests.append(copy.deepcopy(kwargs))
        reply = next(self.replies)
        if isinstance(reply, Exception):
            raise reply
        return reply


@pytest.fixture
def sales():
    return load_sales(DATA_PATH)


def test_selection_execution_and_continuation(sales):
    client = FakeClient(response(("category_sales", "{}", "call_a"),
                                 ("total_revenue", "{}", "call_b")),
                        response(text="Ready"), draft("{{category_sales.0}}"))
    report = run_agent("Which category leads revenue?", sales, client)
    assert "Electronics generated $4,196.50 in revenue from 184 units sold." in report
    assert "Total revenue was $12,951.00." in report
    outputs = [item for item in client.requests[1]["input"] if isinstance(item, dict)
               and item.get("type") == "function_call_output"]
    assert [item["call_id"] for item in outputs] == ["call_a", "call_b"]
    assert json.loads(outputs[0]["output"])["rows"][0]["revenue"] == "4196.50"
    assert client.requests[0]["tools"] == TOOL_SCHEMAS
    assert "tools" not in client.requests[2]  # Separate report stage.


def test_sequential_rounds(sales):
    client = FakeClient(response(("monthly_revenue", "{}", "a")),
                        response(("top_products", "{}", "b")), response(text="Ready"),
                        response(text=json.dumps({"insights": ["{{monthly_revenue.0}}", "{{top_products.0}}"],
                                                  "recommendations": [], "limitations": []})))
    result = run_agent("Summarize months and top products", sales, client)
    assert "Revenue in 2025-01 was $2,131.00." in result
    assert "Wireless Mouse generated $3,152.50 in revenue." in result


@pytest.mark.parametrize(("name", "arguments"), [
    ("shell", "{}"), ("total_revenue", ""), ("total_revenue", "null"),
    ("total_revenue", "[]"), ("total_revenue", '{"path":"secret"}'),
])
def test_invalid_calls(sales, name, arguments):
    with pytest.raises(AgentError):
        run_agent("Revenue?", sales, FakeClient(response((name, arguments, "a"))))


@pytest.mark.parametrize("call_id", ["", "a"])
def test_missing_or_duplicate_ids(sales, call_id):
    client = FakeClient(response(("total_revenue", "{}", "a"),
                                 ("total_revenue", "{}", call_id)))
    with pytest.raises(AgentError, match="call ID"):
        run_agent("Revenue?", sales, client)


def test_bound(sales):
    client = FakeClient(*(response(("total_revenue", "{}", str(i))) for i in range(5)))
    with pytest.raises(AgentError, match="iteration limit"):
        run_agent("Revenue?", sales, client)


def test_unsupported_question(sales):
    client = FakeClient(response(text="Profit data unavailable"))
    assert "Insufficient evidence" in run_agent("What is profit?", sales, client)
    assert len(client.requests) == 1


def test_empty_response(sales):
    with pytest.raises(AgentError, match="no tool calls"):
        run_agent("Revenue?", sales, FakeClient(response()))


def test_incomplete_response(sales):
    with pytest.raises(AgentError, match="incomplete"):
        run_agent("Revenue?", sales, FakeClient(response(status="incomplete")))


def test_reflection_revises_once_and_removes_bad_claim(sales):
    client = FakeClient(response(("total_revenue", "{}", "a")), response(text="Ready"),
                        draft("Revenue is $999"), draft("Revenue is $888"))
    report = run_agent("Revenue?", sales, client)
    assert "$999" not in report and "$888" not in report
    assert "Verification flagged" in report
    assert len(client.requests) == 4


def test_reflection_success(sales):
    client = FakeClient(response(("total_revenue", "{}", "a")), response(text="Ready"),
                        draft("Revenue is $999"), draft())
    assert "Total revenue was $12,951.00." in run_agent("Revenue?", sales, client)
    assert len(client.requests) == 4


def test_verifier_checks_references_and_limits():
    report, issues = verify_report(json.dumps({"insights": ["{{missing}}", "Grew by ten percent"],
                                               "recommendations": ["Investigate."] * 4,
                                               "limitations": []}), {})
    assert not report["insights"]
    assert len(report["recommendations"]) == 3
    assert issues


def test_credentials_missing(sales, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("agent.load_dotenv", lambda *args: None)
    with pytest.raises(AgentError, match="Set OPENAI_API_KEY"):
        run_agent("Revenue?", sales)


def test_timeout(sales):
    import httpx2
    error = APITimeoutError(request=httpx2.Request("POST", "https://api.openai.com"))
    with pytest.raises(AgentError, match="timed out"):
        run_agent("Revenue?", sales, FakeClient(error))


def test_regeneration(tmp_path):
    path = tmp_path / "sales.csv"
    generate_sales(path)
    assert path.read_bytes() == DATA_PATH.read_bytes()


@pytest.mark.parametrize("contents", [
    "date,order_id,product,category,quantity,unit_price\n",
    "date,order_id,product,category,quantity,unit_price\n"
    "2025-01-01,001,Mug,Kitchen,1,5\n2025-01-02, 001 ,Mug,Kitchen,1,5\n",
])
def test_empty_and_duplicate_data(tmp_path, contents):
    path = tmp_path / "invalid.csv"
    path.write_text(contents, encoding="utf-8")
    with pytest.raises(ValueError, match="empty|Duplicate"):
        load_sales(path)


CASES = json.loads((Path(__file__).resolve().parents[1] / "evaluations.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=[case["question"] for case in CASES])
def test_evaluation_contract(sales, case):
    # Script expected plans to verify execution/facts offline, not model quality.
    calls = [(name, "{}", str(i)) for i, name in enumerate(case["tools"])]
    replies = [response(*calls), response(text="Ready"), draft("See the returned metrics.")]
    if not calls:
        replies = [response(text="Unsupported")]
    report = run_agent(case["question"], sales, FakeClient(*replies))
    # Expected amount facts stay numeric in the evaluation fixture.
    assert case["fact"] in report.replace(",", "")


@pytest.mark.parametrize(("status", "message"), [
    (401, "authentication"), (429, "rate limit"), (500, "API request failed"),
])
def test_sdk_api_failures(sales, status, message):
    import httpx2

    transport = httpx2.MockTransport(lambda request: httpx2.Response(
        status, json={"error": {"message": "sensitive provider body", "type": "api_error"}}))
    with OpenAI(api_key="unit-test-placeholder", max_retries=0,
                http_client=httpx2.Client(transport=transport)) as client:
        with pytest.raises(AgentError, match=message) as failure:
            run_agent("Revenue?", sales, client)
    assert "sensitive" not in str(failure.value)


def test_real_sdk_transport_offline(sales):
    import httpx2

    replies = iter([response(("total_revenue", "{}", "a")), response(text="Ready"),
                    draft("Revenue is $999"), draft()])
    requests = []

    def handle(request):
        requests.append(json.loads(request.content))
        return httpx2.Response(200, json=next(replies).model_dump(mode="json"))

    with OpenAI(api_key="unit-test-placeholder", max_retries=0,
                http_client=httpx2.Client(transport=httpx2.MockTransport(handle))) as client:
        assert "Total revenue was $12,951.00." in run_agent("Revenue?", sales, client)
    assert requests[0]["store"] is False
    # Check the actual serialized SDK requests for both writing and revision.
    expected_format = {
        "type": "json_schema", "name": "sales_report", "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "insights": {"type": "array", "items": {"type": "string"}},
                "recommendations": {"type": "array", "items": {"type": "string"}},
                "limitations": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["insights", "recommendations", "limitations"],
            "additionalProperties": False,
        },
    }
    assert len(requests) == 4
    assert requests[2]["text"]["format"] == expected_format
    assert requests[3]["text"]["format"] == expected_format
    assert "verification_issues" in json.loads(requests[3]["input"])
    assert "text" not in requests[0] and "text" not in requests[1]


def test_cli_ask(sales, monkeypatch, capsys):
    import app

    monkeypatch.setattr("sys.argv", ["app.py", "--ask", "Revenue?"])
    client = FakeClient(response(("total_revenue", "{}", "a")), response(text="Ready"), draft())
    monkeypatch.setattr("agent.OpenAI", lambda **kwargs: client)
    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-placeholder")
    app.main()
    assert "Total revenue was $12,951.00." in capsys.readouterr().out


def test_verified_fact_sentences_keep_values_labels_and_units(sales):
    results = {name: execute_tool(name, "{}", sales) for name in (
        "category_sales", "monthly_revenue", "top_products", "total_revenue"
    )}
    facts = build_facts(results)
    assert facts["category_sales.0"] == "Electronics generated $4,196.50 in revenue from 184 units sold."
    assert facts["monthly_revenue.0"] == "Revenue in 2025-01 was $2,131.00."
    assert facts["top_products.0"] == "Wireless Mouse generated $3,152.50 in revenue."
    assert facts["total_revenue"] == "Total revenue was $12,951.00."
    report, issues = verify_report(json.dumps({
        "insights": ["{{category_sales.0}}"], "recommendations": [], "limitations": []
    }), facts)
    assert not issues
    assert report["insights"] == [facts["category_sales.0"]]
    assert results["category_sales"]["rows"][0]["revenue"] == "4196.50"


@pytest.mark.parametrize(("section", "entry"), [
    ("insights", "Review the product mix for {{category_sales.0}}"),
    ("insights", "Leading category: {{category_sales.0}}"),
    ("insights", "{{category_sales.0}} and {{total_revenue}}"),
    ("recommendations", "Review pricing for {{category_sales.0}}"),
    ("recommendations", "{{category_sales.0}}"),
    ("limitations", "{{category_sales.0}}"),
    ("insights", "{{unknown}}"),
    ("insights", "Electronics generated $4,196.50 in revenue from 184 units sold."),
    ("insights", "Home generated $4,196.50 in revenue."),
    ("insights", "Revenue doubled because of promotions."),
    ("insights", "Forecast profit is ten percent higher."),
])
def test_verifier_rejects_inline_facts_and_unsupported_claims(sales, section, entry):
    facts = build_facts({"category_sales": execute_tool("category_sales", "{}", sales)})
    payload = {"insights": [], "recommendations": [], "limitations": []}
    payload[section] = [entry]
    report, issues = verify_report(json.dumps(payload), facts)
    assert issues
    assert report[section] == []


def test_inline_metric_triggers_one_revision(sales):
    client = FakeClient(response(("category_sales", "{}", "a")), response(text="Ready"),
                        draft("Review the product mix for {{category_sales.0}}"),
                        response(text=json.dumps({
                            "insights": ["{{category_sales.0}}", "{{category_sales.0}}"],
                            "recommendations": ["Review the Electronics product mix before making decisions."],
                            "limitations": ["Additional evidence is needed to explain the category mix."],
                        })))
    text = run_agent("Which category generated the most revenue?", sales, client)
    insights = text.split("\n\nBusiness insights\n")[1].split("\n\nRecommendations\n")[0]
    assert insights == "- Electronics generated $4,196.50 in revenue from 184 units sold."
    assert "Review the product mix for Electronics generated" not in text
    assert "All monetary amounts are in USD." in text
    assert "Qualitative interpretations require human review." in text
    assert len(client.requests) == 4
    assert "standalone" in client.requests[3]["input"]
