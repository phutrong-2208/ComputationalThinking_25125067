"""Validated boundaries, explicit policies and audit artifacts for the full pipeline."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from ..mini import MiniRequest
from ..models import Identifier, Model, Text, TokenUsage

Role = Literal["composer", "illustrator", "solver", "reviewer"]
Target = Literal["composer", "illustrator", "solver", "formatter"]
Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class StageConfig(Model):
    model: str | None = None
    supports_images: bool | None = None
    max_output_tokens: int | None = Field(default=None, gt=0, le=100000)
    input_price_per_million: float | None = Field(default=None, ge=0)
    output_price_per_million: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def price_pair(self):
        if (self.input_price_per_million is None) != (self.output_price_per_million is None):
            raise ValueError("configure both token prices, or neither")
        return self


class WorkflowConfig(Model):
    composer: StageConfig = Field(default_factory=StageConfig)
    illustrator: StageConfig = Field(default_factory=StageConfig)
    solver: StageConfig = Field(default_factory=StageConfig)
    reviewer: StageConfig = Field(default_factory=StageConfig)
    max_repair_rounds: Literal[1] = 1
    max_schema_repairs: int = Field(default=1, ge=0, le=1)
    max_provider_calls: int = Field(default=12, gt=0, le=30)
    stage_timeout_seconds: float = Field(default=120, gt=0, le=600)
    run_timeout_seconds: float = Field(default=600, gt=0, le=1800)
    max_total_tokens: int = Field(default=100000, gt=0)
    max_prompt_chars: int = Field(default=200000, gt=0)
    max_image_bytes: int = Field(default=5000000, gt=0, le=20000000)
    max_questions: int = Field(default=120, gt=0, le=500)
    max_figures: int = Field(default=12, ge=0, le=40)


class PipelineRequest(MiniRequest):
    workflow_version: Literal["cisr-v3"] = "cisr-v3"
    workflow: WorkflowConfig = Field(default_factory=WorkflowConfig)


class Drawing(Model):
    visual_id: Identifier
    question_id: Identifier
    spec_sha256: Hash
    latex: str = Field(min_length=1, max_length=30000)


class IllustrationBook(Model):
    exam_id: str
    draft_id: str
    revision: int = Field(ge=1)
    drawings: list[Drawing] = Field(default_factory=list, max_length=40)


class SolutionEntry(Model):
    question_id: Identifier
    solvability: Literal["solvable", "unsolvable", "ambiguous"]
    answer: Text | None = None
    explanation: Text

    @model_validator(mode="after")
    def answer_policy(self):
        if self.solvability == "solvable" and self.answer is None:
            raise ValueError("a solvable question requires an answer")
        if self.solvability != "solvable" and self.answer is not None:
            raise ValueError("do not invent an answer for ambiguous/unsolvable questions")
        return self


class SolutionBook(Model):
    exam_id: str
    draft_id: str
    revision: int = Field(ge=1)
    artifact_sha256: Hash
    entries: list[SolutionEntry] = Field(min_length=1, max_length=500)


class ReviewIssue(Model):
    code: Identifier
    severity: Literal["info", "minor", "major", "critical"]
    target: Target
    question_id: Identifier | None = None
    visual_id: Identifier | None = None
    evidence: Text
    message: Text
    suggested_action: Text

    @property
    def blocking(self) -> bool:
        return self.severity in {"major", "critical"}


class ReviewReport(Model):
    exam_id: str
    draft_id: str
    revision: int = Field(ge=1)
    artifact_sha256: Hash
    solution_sha256: Hash
    checked_question_ids: list[Identifier] = Field(min_length=1, max_length=500)
    decision: Literal["approved", "needs_revision", "rejected", "inconclusive"]
    issues: list[ReviewIssue] = Field(default_factory=list, max_length=500)

    @model_validator(mode="after")
    def consistent_decision(self):
        if self.decision == "approved" and any(issue.blocking for issue in self.issues):
            raise ValueError("approved reviews cannot contain blocking issues")
        if self.decision == "needs_revision" and not any(
            issue.severity != "info" for issue in self.issues
        ):
            raise ValueError("needs_revision requires an actionable issue")
        return self


class CallTrace(Model):
    stage: Role
    revision: int
    attempt: int
    provider: str
    requested_model: str
    model: str | None = None
    prompt_sha256: str
    response_sha256: str | None = None
    image_sha256: list[str] = Field(default_factory=list)
    latency_ms: float = 0
    usage: TokenUsage = Field(default_factory=TokenUsage)
    known_cost_usd: float | None = None
    error_code: str | None = None
    http_status: int | None = None
    normalized_json_fence: bool = False


class WorkflowEvent(Model):
    stage: str
    revision: int
    status: Literal["succeeded", "skipped", "failed", "repair"]
    detail: str


class PipelineError(Model):
    stage: str
    code: str
    message: str


class PipelineResult(Model):
    run_id: str
    workflow_version: Literal["cisr-v3"] = "cisr-v3"
    execution_status: Literal["completed", "failed"] = "failed"
    quality_decision: Literal[
        "approved",
        "needs_revision",
        "rejected",
        "inconclusive",
        "not_reviewed",
        "pending_human_review",
    ] = "not_reviewed"
    final_latex: str | None = None
    latex_sha256: str | None = None
    revision: int = 0
    repairs: int = 0
    reviewer_feedback_sent: bool = False
    human_review_required: bool = True
    review_covers_final_revision: bool = False
    machine_approved: bool = False
    inspection_scope: Literal["text_and_latex_source"] = "text_and_latex_source"
    deterministic_passed: bool = False
    latex_validation: Literal["not_checked", "static", "compiled"] = "not_checked"
    solutions: SolutionBook | None = None
    review: ReviewReport | None = None
    calls: list[CallTrace] = Field(default_factory=list)
    events: list[WorkflowEvent] = Field(default_factory=list)
    errors: list[PipelineError] = Field(default_factory=list)
    total_latency_ms: float = 0
