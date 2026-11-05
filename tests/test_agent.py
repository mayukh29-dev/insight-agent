"""Offline integration tests with real SDK response objects and scripted clients."""

import copy
import json
from types import SimpleNamespace
from pathlib import Path

import pytest
from openai import APITimeoutError, OpenAI
from openai.types.responses import Response

from agent import AgentError, TOOL_SCHEMAS, run_agent, verify_report
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
                        response(text="Ready"), draft("Leading category: {{category_sales.0}}"))
    report = run_agent("Which category leads revenue?", sales, client)
    assert "Electronics revenue is USD 4196.50 with 184 units sold" in report
    assert "Total revenue is USD 12951.00" in report
    outputs = [item for item in client.requests[1]["input"] if isinstance(item, dict)
               and item.get("type") == "function_call_output"]
    assert [item["call_id"] for item in outputs] == ["call_a", "call_b"]
    assert json.loads(outputs[0]["output"])["rows"][0]["revenue"] == "4196.50"
    assert client.requests[0]["tools"] == TOOL_SCHEMAS
    assert "tools" not in client.requests[2]  # Separate report stage.


def test_sequential_rounds(sales):
    client = FakeClient(response(("monthly_revenue", "{}", "a")),
                        response(("top_products", "{}", "b")), response(text="Ready"),
                        draft("{{monthly_revenue.0}}; {{top_products.0}}"))
    result = run_agent("Summarize months and top products", sales, client)
    assert "2025-01 revenue is USD 2131.00" in result
    assert "Wireless Mouse revenue is USD 3152.50" in result


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
    assert "Total revenue is USD 12951.00" in run_agent("Revenue?", sales, client)
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
    assert case["fact"] in report


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

    replies = iter([response(("total_revenue", "{}", "a")), response(text="Ready"), draft()])
    requests = []

    def handle(request):
        requests.append(json.loads(request.content))
        return httpx2.Response(200, json=next(replies).model_dump(mode="json"))

    with OpenAI(api_key="unit-test-placeholder", max_retries=0,
                http_client=httpx2.Client(transport=httpx2.MockTransport(handle))) as client:
        assert "USD 12951.00" in run_agent("Revenue?", sales, client)
    assert requests[0]["store"] is False
    assert requests[2]["text"]["format"]["type"] == "json_object"


def test_cli_ask(sales, monkeypatch, capsys):
    import app

    monkeypatch.setattr("sys.argv", ["app.py", "--ask", "Revenue?"])
    client = FakeClient(response(("total_revenue", "{}", "a")), response(text="Ready"), draft())
    monkeypatch.setattr("agent.OpenAI", lambda **kwargs: client)
    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-placeholder")
    app.main()
    assert "USD 12951.00" in capsys.readouterr().out
