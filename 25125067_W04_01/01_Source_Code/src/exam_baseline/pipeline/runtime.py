"""Provider admission, bounded calls, deadlines, schema normalization and full traces."""

import asyncio
import json
import re
from pathlib import Path
from time import perf_counter

from ..contracts import Completion, CompletionRequest, LLMProvider, ProviderError
from ..mini import digest
from .contracts import CallTrace, PipelineResult, Role, WorkflowConfig


def normalize_json(text: str) -> tuple[str, bool]:
    match = re.fullmatch(r"\s*```(?:json)?\s*\n(.*?)\n```\s*", text, re.DOTALL)
    if match:
        # Only remove a wrapper around a complete valid JSON object, never guess content.
        try:
            if isinstance(json.loads(match[1]), dict):
                return match[1], True
        except ValueError:
            pass
    return text, False


class TracedProvider:
    def __init__(
        self,
        provider: LLMProvider,
        stage: Role,
        revision: int,
        config: WorkflowConfig,
        result: PipelineResult,
        response_directory: Path | None = None,
    ):
        self.provider, self.stage, self.revision = provider, stage, revision
        self.config, self.result = config, result
        self.response_directory = response_directory
        self.name, self.model = provider.name, provider.model
        self.parameters = provider.parameters
        self.supports_images = getattr(provider, "supports_images", False)

    async def complete(self, request: CompletionRequest) -> Completion:
        cfg, calls = self.config, self.result.calls
        if len(calls) >= cfg.max_provider_calls:
            raise self._failure("call_budget_exceeded", "Provider call budget exhausted.")
        used_tokens = sum((c.usage.input_tokens or 0) + (c.usage.output_tokens or 0) for c in calls)
        if used_tokens >= cfg.max_total_tokens:
            raise self._failure("token_budget_exceeded", "Known token budget exhausted.")
        if len(request.system) + len(request.user) > cfg.max_prompt_chars:
            raise self._failure("context_too_large", "Prompt exceeds configured character limit.")
        if request.images and not self.supports_images:
            raise self._failure("vision_required", "Actual images require a vision-capable stage.")
        trace = CallTrace(
            stage=self.stage,
            revision=self.revision,
            attempt=1 + sum(c.stage == self.stage and c.revision == self.revision for c in calls),
            provider=self.name,
            requested_model=self.model,
            prompt_sha256=digest((request.system + "\n" + request.user).encode()),
            image_sha256=[digest(i.data) for i in request.images],
        )
        calls.append(trace)
        start, completion = perf_counter(), None
        try:
            completion = await asyncio.wait_for(
                self.provider.complete(request), timeout=cfg.stage_timeout_seconds
            )
            if self.response_directory is not None:
                self.response_directory.mkdir(parents=True, exist_ok=True)
                name = f"{self.stage}_r{self.revision}_a{trace.attempt}.json"
                (self.response_directory / name).write_text(completion.text, encoding="utf-8")
            text, normalized = normalize_json(completion.text)
            trace.normalized_json_fence = normalized
            if (
                used_tokens
                + (completion.usage.input_tokens or 0)
                + (completion.usage.output_tokens or 0)
                > cfg.max_total_tokens
            ):
                raise self._failure("token_budget_exceeded", "Known token budget exceeded.")
            if self.stage == "composer":
                try:
                    parsed = json.loads(text)
                    too_many = len(parsed.get("visuals", [])) > cfg.max_figures
                except (ValueError, AttributeError, TypeError):
                    too_many = False  # Schema boundary reports malformed content.
                if too_many:
                    raise self._failure("figure_budget", "Too many visual specifications.")
            return Completion(
                text=text,
                model=completion.model,
                usage=completion.usage,
                response_id=completion.response_id,
            )
        except asyncio.TimeoutError as exc:
            trace.error_code = "stage_timeout"
            raise self._failure("stage_timeout", "Stage exceeded its deadline.") from exc
        except ProviderError as exc:
            trace.error_code, completion = exc.code, exc.completion or completion
            trace.http_status = exc.http_status
            exc.stage = self.stage
            raise
        except asyncio.CancelledError:
            trace.error_code = "run_timeout"
            raise
        finally:
            trace.latency_ms = (perf_counter() - start) * 1000
            if completion is not None:
                trace.model, trace.usage = completion.model, completion.usage
                trace.response_sha256 = digest(completion.text.encode())
                prices = getattr(cfg, self.stage)
                input_price = prices.input_price_per_million
                output_price = prices.output_price_per_million
                if input_price is None:
                    input_price = getattr(self.provider, "input_price_per_million", None)
                    output_price = getattr(self.provider, "output_price_per_million", None)
                if (
                    input_price is not None
                    and output_price is not None
                    and completion.usage.input_tokens is not None
                    and completion.usage.output_tokens is not None
                ):
                    trace.known_cost_usd = (
                        completion.usage.input_tokens * input_price
                        + completion.usage.output_tokens * output_price
                    ) / 1000000

    def _failure(self, code: str, message: str) -> ProviderError:
        error = ProviderError(code, message)
        error.stage = self.stage
        return error
