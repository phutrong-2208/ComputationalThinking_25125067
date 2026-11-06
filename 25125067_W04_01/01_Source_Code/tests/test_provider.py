import asyncio
import json

import httpx
import pytest

from exam_baseline.config import Settings
from exam_baseline.contracts import CompletionRequest, ProviderError
from exam_baseline.providers.chat_completions import ChatCompletionsProvider


def settings(**kwargs):
    return Settings(
        _env_file=None,
        provider="chat_completions",
        model="any-model",
        api_key="do-not-leak-this",
        **kwargs,
    )


def invoke(handler, config=None):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = ChatCompletionsProvider(config or settings(), client)
            return await provider.complete(CompletionRequest("system JSON", "user JSON", {}))

    return asyncio.run(run())


def envelope(**kwargs):
    return {
        "id": "remote-id",
        "model": "resolved-model",
        "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 7},
        **kwargs,
    }


def test_adapter_request_and_usage_mapping():
    def handler(request):
        assert request.url == "https://api.openai.com/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer do-not-leak-this"
        data = json.loads(request.content)
        assert data["model"] == "any-model"
        assert data["response_format"] == {"type": "json_object"}
        assert data["max_completion_tokens"] == 8192
        assert "temperature" not in data and "seed" not in data
        return httpx.Response(200, json=envelope())

    result = invoke(handler)
    assert result.model == "resolved-model"
    assert result.usage.input_tokens == 12 and result.usage.output_tokens == 7
    assert result.response_id == "remote-id"


def test_compatible_provider_options():
    def handler(request):
        assert str(request.url) == "http://localhost:9000/v1/chat/completions"
        data = json.loads(request.content)
        assert data["max_tokens"] == 900
        assert data["temperature"] == 0 and data["seed"] == 5
        assert data["response_format"] == {"type": "text"}
        return httpx.Response(200, json=envelope(usage=None))

    result = invoke(
        handler,
        settings(
            base_url="http://localhost:9000/v1/",
            max_output_tokens=900,
            token_limit_field="max_tokens",
            temperature=0,
            seed=5,
            response_format="text",
        ),
    )
    assert result.usage.input_tokens is None


@pytest.mark.parametrize(
    "status,code",
    [
        (400, "provider_bad_request"),
        (401, "provider_auth_error"),
        (403, "provider_access_denied"),
        (404, "provider_not_found"),
        (429, "provider_rate_limited"),
        (500, "provider_internal_error"),
        (502, "provider_bad_gateway"),
        (503, "provider_unavailable"),
        (504, "provider_gateway_timeout"),
        (418, "provider_http_error"),
    ],
)
def test_http_errors_are_sanitized_without_retry(status, code):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, text="sensitive upstream body do-not-leak-this")

    with pytest.raises(ProviderError) as caught:
        invoke(handler)
    assert caught.value.code == code
    assert "do-not-leak" not in str(caught.value)
    assert caught.value.http_status == status
    assert f"HTTP {status}" in str(caught.value)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "exception,code",
    [
        (httpx.ReadTimeout, "provider_timeout"),
        (httpx.ConnectError, "provider_unreachable"),
    ],
)
def test_transport_errors(exception, code):
    def handler(request):
        raise exception("upstream details", request=request)

    with pytest.raises(ProviderError) as caught:
        invoke(handler)
    assert caught.value.code == code


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"choices": []},
        {"choices": [None]},
        envelope(choices=[{"message": {"content": None}, "finish_reason": "stop"}]),
        envelope(usage={"prompt_tokens": -1}),
        envelope(model=23),
    ],
)
def test_bad_envelopes(body):
    with pytest.raises(ProviderError) as caught:
        invoke(lambda r: httpx.Response(200, json=body))
    assert caught.value.code == "provider_protocol_error"


@pytest.mark.parametrize(
    "finish,message,code",
    [
        ("length", {"content": "{partial"}, "provider_incomplete"),
        ("stop", {"refusal": "cannot", "content": None}, "provider_refusal"),
        ("content_filter", {"content": None}, "provider_refusal"),
    ],
)
def test_incomplete_or_refused_response_preserves_usage(finish, message, code):
    body = envelope(choices=[{"message": message, "finish_reason": finish}])
    with pytest.raises(ProviderError) as caught:
        invoke(lambda r: httpx.Response(200, json=body))
    assert caught.value.code == code
    assert caught.value.completion.usage.input_tokens == 12


def test_invalid_outer_json():
    with pytest.raises(ProviderError) as caught:
        invoke(lambda r: httpx.Response(200, text="<html>bad gateway</html>"))
    assert caught.value.code == "provider_protocol_error"


def test_missing_content_preserves_available_usage():
    body = envelope(choices=[{"message": {"content": None}, "finish_reason": "stop"}])
    with pytest.raises(ProviderError) as caught:
        invoke(lambda r: httpx.Response(200, json=body))
    assert caught.value.code == "provider_protocol_error"
    assert caught.value.completion.usage.input_tokens == 12
