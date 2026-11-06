"""One provider call, strict schema parsing, no repair or hidden retries."""

from copy import deepcopy
from time import perf_counter

from pydantic import ValidationError

from .contracts import (
    AgentFailure,
    AgentInput,
    AgentMetadata,
    AgentResult,
    LLMProvider,
    ProviderError,
)
from .models import GeneratedExam
from .prompting import PromptBuilder


class SingleExamAgent:
    def __init__(self, provider: LLMProvider, prompts: PromptBuilder, max_prompt_chars: int):
        self.provider = provider
        self.prompts = prompts
        self.max_prompt_chars = max_prompt_chars
        self.metadata = AgentMetadata(
            provider=provider.name,
            requested_model=provider.model,
            parameters=deepcopy(provider.parameters),
            prompt_version=prompts.version,
            prompt_sha256=prompts.sha256,
        )

    async def generate(self, context: AgentInput) -> AgentResult:
        prompt = self.prompts.build(context)
        if len(prompt.system) + len(prompt.user) > self.max_prompt_chars:
            raise AgentFailure("context_too_large", "Prompt exceeds EXAM_MAX_PROMPT_CHARS.")
        start = perf_counter()
        try:
            completion = await self.provider.complete(prompt)
        except ProviderError as exc:
            raise AgentFailure(
                exc.code,
                str(exc),
                completion=exc.completion,
                latency_ms=(perf_counter() - start) * 1000,
            ) from exc
        latency = (perf_counter() - start) * 1000
        try:
            exam = GeneratedExam.model_validate_json(completion.text)
        except ValidationError as exc:
            # Do not expose raw model output, validation inputs, or secrets in API errors.
            details = [
                {"location": list(e["loc"]), "type": e["type"]}
                for e in exc.errors(include_input=False, include_context=False, include_url=False)
            ]
            raise AgentFailure(
                "invalid_exam_schema",
                "LLM output is not valid exam JSON.",
                completion=completion,
                latency_ms=latency,
                details=details,
            ) from exc
        return AgentResult(exam=exam, completion=completion, generation_latency_ms=latency)
