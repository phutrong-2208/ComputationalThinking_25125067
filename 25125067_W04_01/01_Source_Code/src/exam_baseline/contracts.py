"""Small interfaces for independent replacement, without an orchestration framework."""

from dataclasses import dataclass, field
from typing import Any, Protocol

from .models import GeneratedExam, GenerationRequest, GenerationResponse, TokenUsage


@dataclass(frozen=True)
class ImageInput:
    """Actual image bytes; paths and visual specifications are not vision inputs."""

    data: bytes
    mime: str = "image/png"


@dataclass(frozen=True)
class CompletionRequest:
    system: str
    user: str
    output_schema: dict[str, Any]
    images: tuple[ImageInput, ...] = ()


@dataclass(frozen=True)
class Completion:
    text: str
    model: str
    usage: TokenUsage = field(default_factory=TokenUsage)
    response_id: str | None = None


class ProviderError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        completion: Completion | None = None,
        *,
        http_status: int | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.completion = completion
        self.http_status = http_status


class LLMProvider(Protocol):
    name: str
    model: str
    parameters: dict[str, Any]

    async def complete(self, request: CompletionRequest) -> Completion: ...


@dataclass(frozen=True)
class AgentInput:
    request: GenerationRequest
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class AgentResult:
    exam: GeneratedExam
    completion: Completion
    generation_latency_ms: float


@dataclass(frozen=True)
class AgentMetadata:
    provider: str
    requested_model: str
    parameters: dict[str, Any]
    prompt_version: str
    prompt_sha256: str


class AgentFailure(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        completion: Completion | None = None,
        latency_ms: float = 0,
        details: list[dict[str, Any]] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.completion = completion
        self.latency_ms = latency_ms
        self.details = details or []


class GenerationAgent(Protocol):
    metadata: AgentMetadata

    async def generate(self, context: AgentInput) -> AgentResult: ...


class ContextLoader(Protocol):
    def prepare(self, request: GenerationRequest) -> AgentInput: ...


class EvaluationRecorder(Protocol):
    def record(self, response: GenerationResponse) -> None: ...
