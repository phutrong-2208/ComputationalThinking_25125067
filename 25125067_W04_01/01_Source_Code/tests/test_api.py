import json

import httpx
import pytest
from fastapi.testclient import TestClient

from exam_baseline.api import create_app
from exam_baseline.bootstrap import build_service
from exam_baseline.config import Settings
from exam_baseline.contracts import Completion, ProviderError
from exam_baseline.models import TokenUsage


class FakeProvider:
    name = "fake"
    model = "fake-requested"
    parameters = {"temperature": 0}

    def __init__(self, text="", error=None):
        self.text, self.error, self.calls = text, error, 0

    async def complete(self, request):
        self.calls += 1
        assert "output_schema" in request.user
        if self.error:
            raise self.error
        return Completion(
            self.text, "fake-resolved", TokenUsage(input_tokens=100, output_tokens=50)
        )


def make_client(provider=None, **kwargs):
    settings = Settings(_env_file=None, **kwargs)
    return TestClient(create_app(settings, provider=provider))


def test_offline_api_and_openapi(payload):
    with make_client() as client:
        assert client.get("/health").json()["status"] == "ok"
        assert "/v1/exams/generate" in client.get("/openapi.json").json()["paths"]
        response = client.post("/v1/exams/generate", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["validation"]["passed"]
    assert body["evaluation"]["usage"]["input_tokens"] is None
    assert body["evaluation"]["estimated_cost_usd"] is None


def test_real_workflow_calls_one_agent_provider_once(payload, exam_dict):
    provider = FakeProvider(json.dumps(exam_dict))
    with make_client(provider, input_price_per_million=2, output_price_per_million=4) as client:
        response = client.post("/v1/exams/generate", json=payload)
    body = response.json()
    assert body["status"] == "success"
    assert provider.calls == 1
    metrics = body["evaluation"]
    assert metrics["estimated_cost_usd"] == pytest.approx(0.0004)
    assert metrics["requested_model"] == "fake-requested"
    assert metrics["model"] == "fake-resolved"
    assert metrics["generation_latency_ms"] >= 0
    assert metrics["total_latency_ms"] >= metrics["generation_latency_ms"]
    assert len(metrics["prompt_sha256"]) == 64
    assert len(metrics["request_sha256"]) == 64
    assert len(metrics["response_sha256"]) == 64


@pytest.mark.parametrize("text", ["not JSON", "```json\n{}\n```", "{}", "[]"])
def test_malformed_output_is_explicit_and_keeps_usage(payload, text):
    provider = FakeProvider(text)
    with make_client(provider) as client:
        response = client.post("/v1/exams/generate", json=payload)
    assert response.status_code == 502
    body = response.json()
    assert body["status"] == "schema_failure"
    assert body["exam"] is None and body["validation"] is None
    assert body["error"]["code"] == "invalid_exam_schema"
    assert body["evaluation"]["usage"]["input_tokens"] == 100
    assert body["evaluation"]["constraint_satisfaction_rate"] is None
    assert "input" not in json.dumps(body["error"]["details"])
    assert provider.calls == 1


@pytest.mark.parametrize(
    "code,status",
    [
        ("provider_timeout", 504),
        ("provider_http_error", 503),
        ("provider_rate_limited", 503),
        ("provider_refusal", 503),
    ],
)
def test_provider_failure_contract(payload, code, status):
    provider = FakeProvider(error=ProviderError(code, "Safe provider error."))
    with make_client(provider) as client:
        response = client.post("/v1/exams/generate", json=payload)
    assert response.status_code == status
    assert response.json()["status"] == "provider_failure"
    assert response.json()["evaluation"]["error_code"] == code
    assert provider.calls == 1


def test_structurally_valid_but_noncompliant_exam_is_returned(payload, exam_dict):
    exam_dict["questions"].pop()
    with make_client(FakeProvider(json.dumps(exam_dict))) as client:
        response = client.post("/v1/exams/generate", json=payload)
    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "constraint_failure"
    assert body["exam"] and not body["validation"]["passed"]
    assert body["evaluation"]["status"] == "constraint_failure"


def test_answers_suppressed_even_when_provider_disobeys(payload, exam_dict):
    payload.update(include_answers=False, include_solutions=False)
    with make_client(FakeProvider(json.dumps(exam_dict))) as client:
        response = client.post("/v1/exams/generate", json=payload)
    body = response.json()
    assert body["status"] == "constraint_failure"
    for q in body["exam"]["questions"]:
        assert q["answer"] is None and q["solution"] is None
    assert "x = 11" not in json.dumps(body["validation"])


def test_mock_supports_student_only_output(payload):
    payload.update(include_answers=False, include_solutions=False)
    with make_client() as client:
        body = client.post("/v1/exams/generate", json=payload).json()
    assert body["status"] == "success"
    assert all(q["answer"] is None for q in body["exam"]["questions"])


def test_invalid_request_does_not_invoke_provider(payload):
    provider = FakeProvider()
    payload["matrix"]["question_count"] = 99
    with make_client(provider) as client:
        response = client.post("/v1/exams/generate", json=payload)
    assert response.status_code == 422
    assert provider.calls == 0


def test_prompt_guard_does_not_call_provider(payload):
    provider = FakeProvider()
    with make_client(provider, max_prompt_chars=10) as client:
        response = client.post("/v1/exams/generate", json=payload)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "context_too_large"
    assert provider.calls == 0


def test_jsonl_records_success_and_failure_without_exam_text(payload, exam_dict, tmp_path):
    path = tmp_path / "runs" / "evaluations.jsonl"
    provider = FakeProvider(json.dumps(exam_dict))
    with make_client(provider, evaluation_jsonl=path) as client:
        client.post("/v1/exams/generate", json=payload)
        provider.text = "bad"
        client.post("/v1/exams/generate", json=payload)
    text = path.read_text(encoding="utf-8")
    records = [json.loads(line) for line in text.splitlines()]
    assert [r["evaluation"]["status"] for r in records] == ["success", "schema_failure"]
    assert records[0]["validation"]["passed"]
    assert "Solve 2x" not in text


def test_persistence_failure_does_not_lose_exam(payload, tmp_path):
    # A directory cannot be opened as an append-only file.
    with make_client(evaluation_jsonl=tmp_path) as client:
        body = client.post("/v1/exams/generate", json=payload).json()
    assert body["status"] == "success"
    assert any("persistence failed" in warning for warning in body["warnings"])


def test_root_redirects_to_docs_and_swagger_example_passes():
    with make_client() as client:
        redirect = client.get("/", follow_redirects=False)
        assert redirect.status_code == 307
        assert redirect.headers["location"] == "/docs"
        schema = client.get("/openapi.json").json()
        media = schema["paths"]["/v1/exams/generate"]["post"]["requestBody"]["content"]
        example = media["application/json"]["examples"]["algebra"]["value"]
        response = client.post("/v1/exams/generate", json=example)
        assert response.json()["status"] == "success"


def test_injected_service_is_used_without_creating_provider(monkeypatch):
    service = build_service(Settings.for_offline(), FakeProvider())

    def forbidden(*args, **kwargs):
        raise AssertionError("service injection must not create resources")

    monkeypatch.setattr("exam_baseline.api.service_scope", forbidden)
    with TestClient(create_app(Settings.for_offline(), service=service)) as client:
        health = client.get("/health").json()
    assert health["provider"] == "fake" and health["model"] == "fake-requested"


def test_real_provider_composition_owns_and_closes_its_client(monkeypatch, payload, exam_dict):
    original = httpx.AsyncClient
    clients = []

    def handler(request):
        assert str(request.url) == "https://provider.invalid/v1/chat/completions"
        return httpx.Response(
            200,
            json={
                "model": "resolved-model",
                "choices": [
                    {"message": {"content": json.dumps(exam_dict)}, "finish_reason": "stop"}
                ],
            },
        )

    def client_factory(**kwargs):
        client = original(**kwargs, transport=httpx.MockTransport(handler))
        clients.append(client)
        return client

    monkeypatch.setattr("exam_baseline.bootstrap.httpx.AsyncClient", client_factory)
    settings = Settings(
        _env_file=None,
        provider="chat_completions",
        model="requested-model",
        api_key="test-placeholder",
        base_url="https://provider.invalid/v1",
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").json()["model"] == "requested-model"
        response = client.post("/v1/exams/generate", json=payload).json()
        assert response["status"] == "success"
        assert response["evaluation"]["model"] == "resolved-model"
        assert len(clients) == 1 and not clients[0].is_closed
    assert clients[0].is_closed
