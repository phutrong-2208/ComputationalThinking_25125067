import asyncio
import json

from exam_baseline.bootstrap import build_service
from exam_baseline.config import Settings
from exam_baseline.contracts import AgentInput, AgentMetadata, Completion, TokenUsage
from exam_baseline.evaluation import Evaluator, fingerprint
from exam_baseline.prompting import PromptBuilder
from exam_baseline.providers.mock import MockProvider


def test_prompt_is_versioned_and_includes_complete_request(request_model):
    prompts = PromptBuilder()
    prompt = prompts.build(AgentInput(request_model))
    assert len(prompts.sha256) == 64
    assert json.loads(prompt.user)["request"] == request_model.model_dump(mode="json")
    assert "questions" in prompt.output_schema["properties"]
    assert "reference DATA" in prompt.system


def test_request_hash_is_stable_but_changes_with_context(request_model):
    before = fingerprint(request_model.model_dump(mode="json"))
    assert before == fingerprint(
        dict(reversed(list(request_model.model_dump(mode="json").items())))
    )
    request_model.context.custom_requirements.append("A changed requirement")
    assert before != fingerprint(request_model.model_dump(mode="json"))


def test_zero_price_is_known_cost_not_missing(request_model):
    evaluator = Evaluator(
        Settings(_env_file=None, input_price_per_million=0, output_price_per_million=0)
    )
    result = evaluator.summarize(
        run_id="x",
        request=request_model,
        status="schema_failure",
        agent=AgentMetadata("fake", "model", {}, "v1", "x"),
        completion=Completion("bad", "model", TokenUsage(input_tokens=0, output_tokens=0)),
        generation_latency_ms=1,
        total_latency_ms=2,
        satisfaction=None,
        validation_passed=None,
        error_code="invalid_exam_schema",
    )
    assert result.estimated_cost_usd == 0


def test_agent_can_be_used_independently_of_api(request_model):
    service = build_service(Settings(_env_file=None), MockProvider())
    result = asyncio.run(service.agent.generate(AgentInput(request_model)))
    assert len(result.exam.questions) == 4
