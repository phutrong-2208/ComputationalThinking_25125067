"""Composition and resource ownership shared by REST and offline CLI execution."""

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

import httpx

from .agent import SingleExamAgent
from .config import Settings
from .context import JsonContextLoader
from .contracts import LLMProvider
from .evaluation import Evaluator, JsonEvaluationRecorder
from .prompting import PromptBuilder
from .providers.chat_completions import ChatCompletionsProvider
from .providers.mock import MockProvider
from .service import GenerationService
from .validation import ExamValidator


def build_service(settings: Settings, provider: LLMProvider) -> GenerationService:
    return GenerationService(
        agent=SingleExamAgent(
            provider, PromptBuilder(settings.prompt_version), settings.max_prompt_chars
        ),
        loader=JsonContextLoader(),
        validator=ExamValidator(),
        evaluator=Evaluator(settings),
        recorder=JsonEvaluationRecorder(settings.evaluation_jsonl),
    )


@asynccontextmanager
async def service_scope(
    settings: Settings,
    provider: LLMProvider | None = None,
) -> AsyncIterator[GenerationService]:
    async with AsyncExitStack() as resources:
        if provider is None:
            if settings.provider == "mock":
                provider = MockProvider(model=settings.model)
            else:
                client = await resources.enter_async_context(
                    httpx.AsyncClient(follow_redirects=False)
                )
                provider = ChatCompletionsProvider(settings, client)
        yield build_service(settings, provider)
