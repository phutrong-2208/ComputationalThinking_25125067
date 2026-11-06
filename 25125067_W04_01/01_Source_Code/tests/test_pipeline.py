import asyncio
import copy
import json
import shutil
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from exam_baseline.api import create_app
from exam_baseline.config import Settings
from exam_baseline.contracts import Completion, CompletionRequest, ImageInput, ProviderError
from exam_baseline.mini import Evidence
from exam_baseline.models import BankQuestion, TokenUsage
from exam_baseline.pipeline.bootstrap import ReplayProvider, replay_providers, stage_settings
from exam_baseline.pipeline.contracts import PipelineRequest, StageConfig
from exam_baseline.pipeline.latex import (
    compile_document,
    prose,
    validate_drawing_code,
)
from exam_baseline.pipeline.orchestrator import Orchestrator
from exam_baseline.providers.chat_completions import ChatCompletionsProvider

ROOT = Path(__file__).resolve().parents[1]
TEXT = ROOT / "examples/pipeline/text_01"
VISUAL = ROOT / "examples/pipeline/visual_graph"


def payload(folder=TEXT):
    return PipelineRequest.model_validate_json((folder / "input.json").read_text(encoding="utf-8"))


class Scripted:
    name = "test"
    model = "test-only"
    parameters = {}
    supports_images = True

    def __init__(self, fn):
        self.fn, self.requests = fn, []

    async def complete(self, request):
        self.requests.append(request)
        text = self.fn(request, len(self.requests))
        return Completion(
            text=text, model=self.model, usage=TokenUsage(input_tokens=10, output_tokens=20)
        )


def response(role, request, decision="approved", issues=None, wrong=False):
    data = json.loads((TEXT / f"{role}_01.json").read_text(encoding="utf-8"))
    view = json.loads(request.user)["input"]
    if role == "reviewer":
        data["solution_sha256"] = view["solution_sha256"]
        view = view["student_view"]
        data.update(decision=decision, issues=issues or [])
    for key in ("exam_id", "draft_id", "revision", "artifact_sha256"):
        data[key] = view[key]
    if wrong:
        data["entries"][0]["answer"] = "D"
    return json.dumps(data, ensure_ascii=False)


def issue(target="composer"):
    return {
        "code": "wrong_content",
        "severity": "major",
        "target": target,
        "question_id": "q1",
        "evidence": "Specific arithmetic inconsistency at q1.",
        "message": "Recalculate the question.",
        "suggested_action": "Correct the arithmetic.",
    }


def repeated_providers():
    return {
        role: ReplayProvider([(TEXT / f"{role}_01.json").read_text(encoding="utf-8")] * 2)
        for role in ("composer", "illustrator", "solver", "reviewer")
    }


def test_four_agents_merge_native_latex_then_handoff(tmp_path):
    result = asyncio.run(Orchestrator(replay_providers(TEXT)).run(payload(), tmp_path / "run"))
    assert result.execution_status == "completed"
    assert result.quality_decision == "pending_human_review" and result.human_review_required
    assert result.machine_approved and result.review_covers_final_revision
    assert [c.stage for c in result.calls] == ["composer", "illustrator", "solver", "reviewer"]
    assert result.deterministic_passed and not result.reviewer_feedback_sent
    output = Path(result.final_latex)
    assert sorted(p.name for p in output.parent.iterdir()) == ["_internal", "de_thi.tex"]
    text = output.read_text(encoding="utf-8")
    assert "Câu 4." in text
    for q in json.loads((TEXT / "composer_01.json").read_text(encoding="utf-8"))["exam"][
        "questions"
    ]:
        assert q["solution"] not in text
    assert (output.parent / "_internal/human_review.md").is_file()


def test_solver_receives_merged_latex_not_bank_or_composer_key(tmp_path):
    request = payload()
    request.request.context.course_materials = ["SECRET_CONTEXT"]
    request.request.question_bank.questions.append(
        BankQuestion(
            id="bank-secret",
            stem="Câu ngân hàng chưa dùng.",
            topic_id="math",
            question_type="short_answer",
            difficulty="easy",
            answer="SECRET_BANK_KEY",
        )
    )
    request.evidence = [Evidence(id="e1", text="SECRET_EVIDENCE", role="content_support")]
    providers = replay_providers(TEXT)
    solver = Scripted(lambda req, _: response("solver", req))
    providers["solver"] = solver
    result = asyncio.run(Orchestrator(providers).run(request, tmp_path / "run"))
    assert result.final_latex and "SECRET_" not in solver.requests[0].user
    packet = json.loads(solver.requests[0].user)["input"]
    assert packet["latex_source"] == Path(result.final_latex).read_text(encoding="utf-8")
    assert not solver.requests[0].images
    assert all("answer" not in q and "solution" not in q for q in packet["exam"]["questions"])


def test_illustrator_empty_spec_has_no_unrelated_questions_and_zero_drawing_schema(tmp_path):
    providers = replay_providers(TEXT)

    def draw(req, _):
        data = json.loads(req.user)["input"]
        assert data["visual_specs"] == data["questions"] == []
        schema = req.output_schema["properties"]["drawings"]
        assert schema["minItems"] == schema["maxItems"] == 0
        return json.dumps({"drawings": []})

    providers["illustrator"] = Scripted(draw)
    result = asyncio.run(Orchestrator(providers).run(payload(), tmp_path / "run"))
    assert result.final_latex and len(result.calls) == 4


def test_composer_count_feedback_contains_expected_actual_and_previous_output(tmp_path):
    providers = replay_providers(TEXT)
    good = json.loads((TEXT / "composer_01.json").read_text(encoding="utf-8"))

    def compose(req, count):
        body = copy.deepcopy(good)
        if count == 1:
            body["exam"]["questions"][0].update(question_type="short_answer", choices={})
        else:
            feedback = json.loads(req.user)["repair_feedback"]
            error = next(
                e for e in feedback["contract_errors"] if e["code"] == "type_count:multiple_choice"
            )
            assert "expected 2, received 1" in error["message"]
            assert feedback["previous_output"]["exam"]["questions"][0]["id"] == "q1"
        return json.dumps(body, ensure_ascii=False)

    providers["composer"] = Scripted(compose)
    result = asyncio.run(Orchestrator(providers).run(payload(), tmp_path / "run"))
    assert result.final_latex and not result.reviewer_feedback_sent
    assert len(result.calls) == 5


def test_illustrator_is_separate_agent_produces_editable_native_code(tmp_path):
    providers = replay_providers(VISUAL)
    for provider in providers.values():
        provider.supports_images = False
    result = asyncio.run(Orchestrator(providers).run(payload(VISUAL), tmp_path / "run"))
    assert result.final_latex and len(result.calls) == 4
    source = Path(result.final_latex).read_text(encoding="utf-8")
    assert r"\begin{tikzpicture}" in source and r"\addplot" in source
    assert r"\directlua" not in source and "includegraphics" not in source
    assert ".png" not in source and "local h =" not in source
    assert all(not call.image_sha256 for call in result.calls)
    assert result.inspection_scope == "text_and_latex_source"


@pytest.mark.parametrize(
    "decision,target",
    [("needs_revision", "solver"), ("rejected", "composer"), ("inconclusive", "illustrator")],
)
def test_reviewer_feedback_goes_to_composer_once_then_stops(tmp_path, decision, target):
    providers = repeated_providers()
    original = (TEXT / "composer_01.json").read_text(encoding="utf-8")
    composer = Scripted(lambda req, _: original)
    reviewer = Scripted(
        lambda req, _: response("reviewer", req, decision=decision, issues=[issue(target)])
    )
    providers.update(composer=composer, reviewer=reviewer)
    result = asyncio.run(Orchestrator(providers).run(payload(), tmp_path / "run"))
    assert result.final_latex and result.execution_status == "completed"
    assert result.reviewer_feedback_sent and result.repairs == 1 and result.revision == 2
    assert result.quality_decision == "pending_human_review" and result.human_review_required
    assert not result.machine_approved and not result.review_covers_final_revision
    assert result.review.revision == 1 and result.solutions.revision == 2
    assert len(reviewer.requests) == 1 and len(composer.requests) == 2
    assert [c.stage for c in result.calls] == [
        "composer",
        "illustrator",
        "solver",
        "reviewer",
        "composer",
        "illustrator",
        "solver",
    ]
    feedback = json.loads(composer.requests[1].user)["repair_feedback"]
    assert feedback["review"]["issues"][0]["target"] == target
    assert sum(e.status == "repair" and "feedback" in e.detail for e in result.events) == 1


def test_callback_composer_schema_failure_is_not_retried(tmp_path):
    providers = repeated_providers()
    valid = (TEXT / "composer_01.json").read_text(encoding="utf-8")
    composer = Scripted(lambda req, count: valid if count == 1 else "not JSON")
    providers["composer"] = composer
    providers["reviewer"] = Scripted(
        lambda req, _: response("reviewer", req, decision="needs_revision", issues=[issue()])
    )
    result = asyncio.run(Orchestrator(providers).run(payload(), tmp_path / "run"))
    assert not result.final_latex and result.reviewer_feedback_sent
    assert len(composer.requests) == 2 and result.calls[-1].stage == "composer"


def test_minor_format_issue_can_request_the_single_composer_feedback(tmp_path):
    providers = repeated_providers()
    minor = {**issue("formatter"), "severity": "minor"}
    providers["reviewer"] = Scripted(
        lambda req, _: response("reviewer", req, decision="needs_revision", issues=[minor])
    )
    result = asyncio.run(Orchestrator(providers).run(payload(), tmp_path / "run"))
    assert result.final_latex and result.reviewer_feedback_sent
    assert result.repairs == 1 and result.revision == 2
    assert sum(c.stage == "reviewer" for c in result.calls) == 1


def test_broken_reviewer_schema_gets_no_second_reviewer_call(tmp_path):
    providers = replay_providers(TEXT)
    reviewer = Scripted(lambda req, _: "not JSON")
    providers["reviewer"] = reviewer
    result = asyncio.run(Orchestrator(providers).run(payload(), tmp_path / "run"))
    assert not result.final_latex and result.errors[0].stage == "reviewer"
    assert len(reviewer.requests) == 1


def test_cannot_configure_a_second_quality_feedback_cycle():
    from pydantic import ValidationError

    for limit in (0, 2, 5):
        data = payload().model_dump()
        data["workflow"]["max_repair_rounds"] = limit
        with pytest.raises(ValidationError):
            PipelineRequest.model_validate(data)


def test_unsafe_illustrator_code_is_rejected_before_merge(tmp_path):
    providers = replay_providers(VISUAL)
    native = json.loads((VISUAL / "illustrator_01.json").read_text(encoding="utf-8"))
    native["drawings"][0]["latex"] = r"\begin{tikzpicture}\input{secret}\end{tikzpicture}"
    providers["illustrator"] = ReplayProvider([json.dumps(native)] * 2)
    result = asyncio.run(Orchestrator(providers).run(payload(VISUAL), tmp_path / "run"))
    assert not result.final_latex and result.errors[0].stage == "illustrator"
    assert [c.stage for c in result.calls] == ["composer", "illustrator", "illustrator"]


def test_illustrator_must_cover_all_figures_and_bind_spec_hash(tmp_path):
    providers = replay_providers(VISUAL)
    native = json.loads((VISUAL / "illustrator_01.json").read_text(encoding="utf-8"))
    native["drawings"][0]["spec_sha256"] = "a" * 64
    providers["illustrator"] = ReplayProvider([json.dumps(native)] * 2)
    result = asyncio.run(Orchestrator(providers).run(payload(VISUAL), tmp_path / "run"))
    assert not result.final_latex and result.errors[0].code == "stage_contract"


def test_initial_composer_latex_error_is_corrected_before_other_agents(tmp_path):
    providers = replay_providers(TEXT)
    original = json.loads((TEXT / "composer_01.json").read_text(encoding="utf-8"))

    def compose(req, count):
        data = copy.deepcopy(original)
        if count == 1:
            data["exam"]["questions"][0]["stem"] = "Tính $3+6."
        return json.dumps(data, ensure_ascii=False)

    providers["composer"] = Scripted(compose)
    result = asyncio.run(Orchestrator(providers).run(payload(), tmp_path / "run"))
    assert result.final_latex and not result.reviewer_feedback_sent
    assert [c.stage for c in result.calls][:3] == ["composer", "composer", "illustrator"]


def test_fenced_json_normalization_does_not_add_agent_call(tmp_path):
    providers = replay_providers(TEXT)
    text = (TEXT / "composer_01.json").read_text(encoding="utf-8")
    providers["composer"] = Scripted(lambda req, _: "```json\n" + text + "\n```")
    result = asyncio.run(Orchestrator(providers).run(payload(), tmp_path / "run"))
    assert result.final_latex and len(result.calls) == 4
    assert result.calls[0].normalized_json_fence


def test_call_budget_stops_before_reviewer(tmp_path):
    request = payload()
    request.workflow.max_provider_calls = 3
    result = asyncio.run(Orchestrator(replay_providers(TEXT)).run(request, tmp_path / "run"))
    assert not result.final_latex and len(result.calls) == 3
    assert result.errors[0].code == "call_budget_exceeded"
    assert result.errors[0].stage == "reviewer"


def test_token_budget_retains_failed_call_usage_and_cost(tmp_path):
    request = payload()
    request.workflow.max_total_tokens = 29
    request.workflow.composer.input_price_per_million = 1
    request.workflow.composer.output_price_per_million = 2
    providers = replay_providers(TEXT)
    providers["composer"] = Scripted(
        lambda req, _: (TEXT / "composer_01.json").read_text(encoding="utf-8")
    )
    result = asyncio.run(Orchestrator(providers).run(request, tmp_path / "run"))
    assert not result.final_latex and result.errors[0].code == "token_budget_exceeded"
    assert result.calls[0].usage.input_tokens == 10
    assert result.calls[0].known_cost_usd == pytest.approx(0.00005)


def test_reviewer_cannot_approve_stale_solution_book(tmp_path):
    providers = replay_providers(TEXT)

    def stale(req, _):
        data = json.loads(response("reviewer", req))
        data["solution_sha256"] = "a" * 64
        return json.dumps(data)

    providers["reviewer"] = Scripted(stale)
    result = asyncio.run(Orchestrator(providers).run(payload(), tmp_path / "run"))
    assert not result.final_latex and len(result.calls) == 4


def test_agents_return_content_while_code_binds_identity_and_hashes(tmp_path):
    providers = replay_providers(TEXT)
    fields = {"exam_id", "draft_id", "revision", "artifact_sha256", "solution_sha256"}
    providers["illustrator"] = Scripted(lambda req, _: json.dumps({"drawings": []}))

    def content(role, req):
        assert not (fields & req.output_schema["properties"].keys())
        body = json.loads(response(role, req))
        return json.dumps({k: v for k, v in body.items() if k not in fields})

    providers["solver"] = Scripted(lambda req, _: content("solver", req))
    providers["reviewer"] = Scripted(lambda req, _: content("reviewer", req))
    result = asyncio.run(Orchestrator(providers).run(payload(), tmp_path / "run"))
    assert result.final_latex and len(result.calls) == 4
    assert result.solutions.artifact_sha256 == result.review.artifact_sha256
    assert result.solutions.revision == result.review.revision == 1


def test_illustrator_spec_hash_is_bound_without_model_copying_it(tmp_path):
    providers = replay_providers(VISUAL)
    body = json.loads((VISUAL / "illustrator_01.json").read_text(encoding="utf-8"))
    for name in ("exam_id", "draft_id", "revision"):
        body.pop(name)
    body["drawings"][0].pop("spec_sha256")
    providers["illustrator"] = Scripted(lambda req, _: json.dumps(body))
    result = asyncio.run(Orchestrator(providers).run(payload(VISUAL), tmp_path / "run"))
    assert result.final_latex and len(result.calls) == 4


def test_finalizer_detects_source_tampering(tmp_path):
    providers = replay_providers(TEXT)

    def tamper(req, _):
        (tmp_path / "run/_internal/drafts/r1/merged.tex").write_text("changed", encoding="utf-8")
        return response("reviewer", req)

    providers["reviewer"] = Scripted(tamper)
    result = asyncio.run(Orchestrator(providers).run(payload(), tmp_path / "run"))
    assert not result.final_latex and result.errors[0].code == "artifact_error"


def test_compile_failure_does_not_publish_uncompiled_file(tmp_path, monkeypatch):
    def broken(path):
        raise ValueError("compiler_not_installed")

    monkeypatch.setattr("exam_baseline.pipeline.orchestrator.compile_document", broken)
    result = asyncio.run(
        Orchestrator(replay_providers(TEXT)).run(payload(), tmp_path / "run", compile_latex=True)
    )
    assert not result.final_latex and result.errors


def test_timeout_does_not_trigger_retry(tmp_path):
    class Slow(Scripted):
        async def complete(self, request):
            await asyncio.sleep(0.2)

    providers = replay_providers(TEXT)
    providers["solver"] = Slow(None)
    request = payload()
    request.workflow.stage_timeout_seconds = 0.01
    result = asyncio.run(Orchestrator(providers).run(request, tmp_path / "run"))
    assert len(result.calls) == 3 and result.errors[0].code == "stage_timeout"


def test_composer_http_status_reaches_report_and_does_not_retry(tmp_path):
    class Unavailable(ReplayProvider):
        async def complete(self, request):
            raise ProviderError(
                "provider_unavailable",
                "HTTP 503: Provider temporarily unavailable.",
                http_status=503,
            )

    providers = replay_providers(TEXT)
    providers["composer"] = Unavailable([])
    result = asyncio.run(Orchestrator(providers).run(payload(), tmp_path / "run"))
    assert len(result.calls) == 1 and result.calls[0].http_status == 503
    assert "HTTP 503" in result.errors[0].message
    assert not result.reviewer_feedback_sent


def test_v2_api_returns_latex_with_explicit_human_handoff(tmp_path):
    app = create_app(
        Settings.for_offline(),
        pipeline_providers=replay_providers(TEXT),
        pipeline_output_root=tmp_path,
    )
    with TestClient(app) as client:
        result = client.post("/v2/exams/generate", json=payload().model_dump(mode="json"))
        assert result.status_code == 200
        assert result.headers["content-type"].startswith("application/x-tex")
        assert result.headers["x-human-review-required"] == "true"
        assert result.headers["x-reviewer-feedback-sent"] == "false"
        assert "/v1/exams/generate" in client.get("/openapi.json").json()["paths"]


def test_input_rejected_before_any_call(tmp_path):
    request = payload()
    request.latex_template = r"\begin{document}%% ASTRA_BODY %%\input{secret}\end{document}"
    with pytest.raises(ValueError, match="unsupported_command"):
        asyncio.run(Orchestrator(replay_providers(TEXT)).run(request, tmp_path / "run"))
    with pytest.raises(ValueError, match="already exists"):
        asyncio.run(Orchestrator(replay_providers(TEXT)).run(payload(), tmp_path))


def test_native_code_validation_and_math_escaping():
    assert prose(r"50% & $x_1$") == r"50\% \& $x_1$"
    for code in (
        r"\begin{tikzpicture}\directlua{bad}\end{tikzpicture}",
        r"\begin{tikzpicture}\addplot table {secret};\end{tikzpicture}",
        r"\begin{tikzpicture}\draw (0,0)--(1,1);",
    ):
        with pytest.raises(ValueError):
            validate_drawing_code(code)
    with pytest.raises(ValueError):
        prose("$x+1")


def test_role_configuration_supports_an_independent_illustrator_model():
    base = Settings(
        _env_file=None, provider="chat_completions", model="composer", api_key="test-key"
    )
    native = stage_settings(base, StageConfig(model="illustrator"))
    assert native.model == "illustrator" and base.model == "composer"


def test_provider_sends_actual_image_content_and_blocks_text_only_adapter():
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}]}
        )

    async def run():
        settings = Settings(
            _env_file=None,
            provider="chat_completions",
            model="test-model",
            api_key="test-key",
            supports_images=True,
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = ChatCompletionsProvider(settings, client)
            request = CompletionRequest("system", "question", {}, (ImageInput(b"actual-bytes"),))
            await provider.complete(request)
            provider.supports_images = False
            with pytest.raises(ProviderError, match="not configured"):
                await provider.complete(request)

    asyncio.run(run())
    assert len(seen) == 1
    assert seen[0]["messages"][1]["content"][1]["image_url"]["url"] == (
        "data:image/png;base64,YWN0dWFsLWJ5dGVz"
    )


@pytest.mark.skipif(
    not (shutil.which("xelatex") or shutil.which("lualatex")),
    reason="No terminal TeX compiler installed; editor compilation tested separately",
)
def test_native_tex_compiles_when_terminal_compiler_available(tmp_path):
    result = asyncio.run(
        Orchestrator(replay_providers(VISUAL)).run(
            payload(VISUAL), tmp_path / "run", compile_latex=True
        )
    )
    assert result.final_latex and result.latex_validation == "compiled"
    compile_document(Path(result.final_latex))
