"""CLI behaviour, offline isolation, and artifact persistence without real provider calls."""

import json

import httpx
import pytest

from exam_baseline import cli
from exam_baseline.config import Settings
from exam_baseline.models import GenerationResponse


def load_result(output):
    return json.loads((output / "response.json").read_text(encoding="utf-8"))


def test_offline_cli_never_reads_local_configuration(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("EXAM_PROVIDER=invalid\nEXAM_TIMEOUT_SECONDS=invalid\n")
    monkeypatch.setenv("EXAM_PROVIDER", "invalid")
    monkeypatch.setenv("EXAM_MODEL", "should-not-be-used")
    monkeypatch.setenv("EXAM_TIMEOUT_SECONDS", "invalid")
    output = tmp_path / "result"
    assert Settings.for_offline().provider == "mock"
    assert cli.main(["--offline", "--output-dir", str(output)]) == 0
    response = GenerationResponse.model_validate(load_result(output))
    assert response.evaluation.provider == "mock"
    assert response.evaluation.model == "mock-fixture-v1"
    assert len(response.exam.questions) == 4
    assert response.validation.passed
    assert (output / "ket_qua.md").is_file()
    assert (output / "request.json").is_file()


def test_exported_request_is_valid_and_not_overwritten(tmp_path):
    example = tmp_path / "request.json"
    assert cli.main(["--export-example", str(example)]) == 0
    original = example.read_bytes()
    assert cli.main(["--export-example", str(example)]) == 2
    assert example.read_bytes() == original


def test_schema_error_is_saved_as_readable_report(payload, tmp_path):
    payload["matrix"]["question_count"] = 5
    request = tmp_path / "invalid.json"
    request.write_text(json.dumps(payload), encoding="utf-8")
    output = tmp_path / "result"
    assert cli.main(["--offline", "--request", str(request), "--output-dir", str(output)]) == 1
    assert load_result(output)["detail"]
    assert "422" in (output / "ket_qua.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("content", [None, "{malformed"])
def test_unreadable_request_returns_clear_failure(content, tmp_path):
    request = tmp_path / "request.json"
    if content is not None:
        request.write_text(content, encoding="utf-8")
    assert cli.main(["--request", str(request)]) == 2


def test_output_is_checked_before_generation(monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        raise AssertionError("generation must not happen")

    monkeypatch.setattr(cli, "_live", forbidden)
    sentinel = tmp_path / "response.json"
    sentinel.write_text("keep me", encoding="utf-8")
    assert cli.main(["--live", "--output-dir", str(tmp_path)]) == 2
    assert sentinel.read_text(encoding="utf-8") == "keep me"


def test_live_uses_local_api_and_preserves_response(monkeypatch, tmp_path, payload, exam_dict):
    def post(url, **kwargs):
        assert url == "http://127.0.0.1:9999/v1/exams/generate"
        assert kwargs["json"] == payload
        assert kwargs["trust_env"] is False
        return httpx.Response(200, json={"status": "success", "exam": exam_dict})

    monkeypatch.setattr(cli.httpx, "post", post)
    output = tmp_path / "result"
    assert (
        cli.main(["--live", "--base-url", "http://127.0.0.1:9999", "--output-dir", str(output)])
        == 0
    )
    assert load_result(output)["exam"] == exam_dict


@pytest.mark.parametrize("failure", [httpx.ConnectError, httpx.ReadTimeout])
def test_transport_failure_also_has_saved_report(monkeypatch, tmp_path, failure):
    def post(*args, **kwargs):
        raise failure("do not log upstream details")

    monkeypatch.setattr(cli.httpx, "post", post)
    output = tmp_path / "result"
    assert cli.main(["--live", "--output-dir", str(output)]) == 2
    assert load_result(output)["status"] == "client_failure"
    assert "do not log" not in (output / "ket_qua.md").read_text(encoding="utf-8")


def test_non_json_api_reply_is_recorded(monkeypatch, tmp_path):
    monkeypatch.setattr(cli.httpx, "post", lambda *a, **kw: httpx.Response(500, text="HTML"))
    output = tmp_path / "result"
    assert cli.main(["--live", "--output-dir", str(output)]) == 2
    assert load_result(output)["error"]["code"] == "invalid_api_response"


@pytest.mark.parametrize(
    "options",
    [
        ["--timeout", "nan"],
        ["--timeout", "0"],
        ["--timeout", "inf"],
        ["--base-url", "https://user:secret@localhost"],
        ["--base-url", "http://localhost/path"],
    ],
)
def test_invalid_options_do_not_start_generation(options):
    with pytest.raises(SystemExit) as exc:
        cli.main(options)
    assert exc.value.code == 2
