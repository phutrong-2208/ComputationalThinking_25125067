"""Evaluation is independent of agent implementation; records include failure runs."""

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from .config import Settings
from .contracts import AgentMetadata, Completion
from .models import Evaluation, GenerationRequest, GenerationResponse, Status, TokenUsage

logger = logging.getLogger("exam_baseline.evaluation")


def fingerprint(value: Any) -> str:
    text = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


class Evaluator:
    def __init__(self, settings: Settings):
        self.settings = settings

    def summarize(
        self,
        *,
        run_id: str,
        request: GenerationRequest,
        status: Status,
        agent: AgentMetadata,
        completion: Completion | None,
        generation_latency_ms: float,
        total_latency_ms: float,
        satisfaction: float | None,
        validation_passed: bool | None,
        error_code: str | None,
    ) -> Evaluation:
        usage = completion.usage if completion else TokenUsage()
        cost = None
        input_price = self.settings.input_price_per_million
        output_price = self.settings.output_price_per_million
        if (
            input_price is not None
            and output_price is not None
            and usage.input_tokens is not None
            and usage.output_tokens is not None
        ):
            cost = (usage.input_tokens * input_price + usage.output_tokens * output_price) / 1e6
        return Evaluation(
            run_id=run_id,
            created_at=datetime.now(timezone.utc),
            status=status,
            provider=agent.provider,
            requested_model=agent.requested_model,
            model=completion.model if completion else agent.requested_model,
            prompt_version=agent.prompt_version,
            prompt_sha256=agent.prompt_sha256,
            request_sha256=fingerprint(request.model_dump(mode="json")),
            response_sha256=hashlib.sha256(completion.text.encode()).hexdigest()
            if completion
            else None,
            provider_response_id=completion.response_id if completion else None,
            generation_latency_ms=round(generation_latency_ms, 3),
            total_latency_ms=round(total_latency_ms, 3),
            usage=usage,
            estimated_cost_usd=cost,
            input_price_per_million=input_price,
            output_price_per_million=output_price,
            generation_parameters=agent.parameters,
            constraint_satisfaction_rate=satisfaction,
            validation_passed=validation_passed,
            error_code=error_code,
        )


class JsonEvaluationRecorder:
    """One process: thread-safe JSONL appends. No exam, prompt, or bank content persisted."""

    def __init__(self, path: Path | None = None):
        self.path = path
        self.lock = Lock()

    def record(self, response: GenerationResponse) -> None:
        validation = response.validation
        record = {
            "evaluation": response.evaluation.model_dump(mode="json"),
            "validation": None
            if validation is None
            else {
                "passed": validation.passed,
                "constraint_satisfaction_rate": validation.constraint_satisfaction_rate,
                # Check IDs and pass/fail suffice; actual/expected may contain question text.
                "checks": [{"code": c.code, "passed": c.passed} for c in validation.checks],
            },
        }
        line = json.dumps(record, ensure_ascii=False)
        logger.info(line)
        if self.path:
            with self.lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as stream:
                    stream.write(line + "\n")
