"""Coordinates ordinary Python components around exactly one generation agent."""

import logging
from time import perf_counter
from uuid import uuid4

from .contracts import (
    AgentFailure,
    ContextLoader,
    EvaluationRecorder,
    GenerationAgent,
)
from .evaluation import Evaluator
from .models import GenerationError, GenerationRequest, GenerationResponse, Status
from .validation import ExamValidator

logger = logging.getLogger(__name__)


def failure_status(code: str) -> Status:
    if code == "invalid_exam_schema":
        return "schema_failure"
    if code == "context_too_large":
        return "context_failure"
    return "provider_failure"


class GenerationService:
    def __init__(
        self,
        *,
        agent: GenerationAgent,
        loader: ContextLoader,
        validator: ExamValidator,
        evaluator: Evaluator,
        recorder: EvaluationRecorder,
    ):
        self.agent, self.loader = agent, loader
        self.validator, self.evaluator, self.recorder = validator, evaluator, recorder

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        start = perf_counter()
        run_id = str(uuid4())
        context = self.loader.prepare(request)
        exam, report, error, completion = None, None, None, None
        generation_latency_ms = 0.0
        try:
            result = await self.agent.generate(context)
            exam, completion = result.exam, result.completion
            generation_latency_ms = result.generation_latency_ms
            report = self.validator.validate(exam, context.request)
            status = "success" if report.passed else "constraint_failure"
            # Validate the original output, then enforce answer visibility even on failure.
            exam = exam.model_copy(deep=True)
            for question in exam.questions:
                if not request.include_answers:
                    question.answer = None
                if not request.include_solutions:
                    question.solution = None
        except AgentFailure as exc:
            completion, generation_latency_ms = exc.completion, exc.latency_ms
            status = failure_status(exc.code)
            error = GenerationError(code=exc.code, message=str(exc), details=exc.details)
        evaluation = self.evaluator.summarize(
            run_id=run_id,
            request=request,
            status=status,
            agent=self.agent.metadata,
            completion=completion,
            generation_latency_ms=generation_latency_ms,
            total_latency_ms=(perf_counter() - start) * 1000,
            satisfaction=report.constraint_satisfaction_rate if report else None,
            validation_passed=report.passed if report else None,
            error_code=error.code if error else None,
        )
        response = GenerationResponse(
            status=status,
            exam=exam,
            validation=report,
            evaluation=evaluation,
            error=error,
            warnings=list(context.warnings),
        )
        try:
            self.recorder.record(response)
        except OSError:
            logger.warning("Evaluation persistence failed for run %s", run_id)
            response.warnings.append(
                "Evaluation persistence failed; keep this response for the run."
            )
        return response
