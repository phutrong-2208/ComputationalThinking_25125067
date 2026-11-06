"""Provider-independent contracts. Counts are exact; every question has one primary topic."""

from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import __version__

Text = Annotated[str, Field(min_length=1, max_length=30000)]
Identifier = Annotated[str, Field(min_length=1, max_length=100)]
Count = Annotated[int, Field(ge=0, strict=True)]
PositiveCount = Annotated[int, Field(gt=0, strict=True)]
Points = Annotated[float, Field(gt=0, strict=True, allow_inf_nan=False)]
Budget = Annotated[float, Field(ge=0, strict=True, allow_inf_nan=False)]
EPSILON = 1e-6


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class QuestionType(str, Enum):
    MULTIPLE_CHOICE = "multiple_choice"
    SHORT_ANSWER = "short_answer"
    ESSAY = "essay"
    TRUE_FALSE = "true_false"


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class LearningObjective(Model):
    id: Identifier
    description: Text


class Topic(Model):
    id: Identifier
    name: Text
    subtopics: list[Identifier] = Field(default_factory=list, max_length=100)
    learning_objectives: list[LearningObjective] = Field(default_factory=list, max_length=100)
    question_count: Count
    points: Budget | None = None

    @model_validator(mode="after")
    def consistent_topic(self):
        if len(self.subtopics) != len(set(self.subtopics)):
            raise ValueError("subtopics must be unique within a topic")
        if self.question_count == 0 and (self.subtopics or self.learning_objectives):
            raise ValueError("a zero-question topic cannot require subtopics or objectives")
        if len(self.subtopics) > self.question_count:
            raise ValueError("each listed subtopic needs at least one question")
        if self.points is not None and ((self.question_count == 0) != (self.points == 0)):
            raise ValueError(
                "topic points must be positive exactly when question_count is positive"
            )
        return self


class ExamMatrix(Model):
    subject: Text
    title: Text
    topics: list[Topic] = Field(min_length=1, max_length=200)
    question_count: Annotated[int, Field(gt=0, le=500, strict=True)]
    question_type_distribution: dict[QuestionType, Count]
    difficulty_distribution: dict[Difficulty, Count]
    total_points: Points
    points_by_type: dict[QuestionType, Budget] | None = None
    duration_minutes: Annotated[int, Field(gt=0, le=1440, strict=True)]
    additional_constraints: list[Text] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def consistent_blueprint(self):
        if len({t.id for t in self.topics}) != len(self.topics):
            raise ValueError("topic IDs must be unique")
        objectives = [o.id for t in self.topics for o in t.learning_objectives]
        if len(objectives) != len(set(objectives)):
            raise ValueError("learning objective IDs must be globally unique")
        for label, counts in (
            ("topic", [t.question_count for t in self.topics]),
            ("question type", self.question_type_distribution.values()),
            ("difficulty", self.difficulty_distribution.values()),
        ):
            if sum(counts) != self.question_count:
                raise ValueError(f"{label} counts must sum to question_count")
        budgets = [t.points for t in self.topics if t.points is not None]
        if len(budgets) == len(self.topics):
            if abs(sum(budgets) - self.total_points) > EPSILON:
                raise ValueError("topic points must sum to total_points")
        elif budgets:
            unbudgeted_questions = any(
                t.points is None and t.question_count > 0 for t in self.topics
            )
            if unbudgeted_questions and sum(budgets) >= self.total_points:
                raise ValueError("partial topic budgets leave no points for other questions")
            if sum(budgets) > self.total_points + EPSILON:
                raise ValueError("topic points exceed total_points")
            if not unbudgeted_questions and abs(sum(budgets) - self.total_points) > EPSILON:
                raise ValueError("topic points must sum to total_points")
        if self.points_by_type is not None:
            if set(self.points_by_type) != set(self.question_type_distribution):
                raise ValueError("points_by_type must use the same keys as type distribution")
            if abs(sum(self.points_by_type.values()) - self.total_points) > EPSILON:
                raise ValueError("points_by_type must sum to total_points")
            for kind, count in self.question_type_distribution.items():
                if (count == 0) != (self.points_by_type[kind] == 0):
                    raise ValueError("type points must be positive exactly when count is positive")
        return self


class QuestionContent(Model):
    stem: Text
    topic_id: Identifier
    subtopic: Identifier | None = None
    learning_objective_ids: list[Identifier] = Field(default_factory=list, max_length=100)
    question_type: QuestionType
    difficulty: Difficulty
    choices: dict[Identifier, Text] = Field(default_factory=dict, max_length=10)
    answer: Text | None = None
    solution: Text | None = None

    @model_validator(mode="after")
    def valid_question_shape(self):
        if len(self.learning_objective_ids) != len(set(self.learning_objective_ids)):
            raise ValueError("learning_objective_ids must be unique")
        if self.question_type == QuestionType.MULTIPLE_CHOICE:
            if len(self.choices) < 2:
                raise ValueError("multiple_choice requires at least two choices")
            if len({v.casefold() for v in self.choices.values()}) != len(self.choices):
                raise ValueError("multiple_choice choice texts must be distinct")
            if self.answer is not None and self.answer not in self.choices:
                raise ValueError("multiple_choice answer must be a choice key")
        elif self.choices:
            raise ValueError("choices are only allowed for multiple_choice questions")
        if self.question_type == QuestionType.TRUE_FALSE and self.answer is not None:
            if self.answer.casefold() not in {"true", "false"}:
                raise ValueError("true_false answer must be true or false")
        return self


class BankQuestion(QuestionContent):
    id: Identifier
    points: Points | None = None
    metadata: dict[Identifier, Text] = Field(default_factory=dict)


class QuestionBank(Model):
    questions: list[BankQuestion] = Field(default_factory=list, max_length=2000)

    @model_validator(mode="after")
    def unique_ids(self):
        if len({q.id for q in self.questions}) != len(self.questions):
            raise ValueError("question bank IDs must be unique")
        return self


class Question(QuestionContent):
    id: Identifier
    points: Points
    source_question_id: Identifier | None = None


class GeneratedExam(Model):
    title: Text
    subject: Text
    duration_minutes: PositiveCount
    total_points: Points
    instructions: Text
    questions: list[Question] = Field(min_length=1, max_length=500)
    shared_passages: list["SharedPassage"] = Field(default_factory=list)


class SharedPassage(Model):
    start_question: Annotated[int, Field(gt=0, strict=True)]
    end_question: Annotated[int, Field(gt=0, strict=True)]
    text: Text

    @model_validator(mode="after")
    def valid_range(self):
        if self.end_question < self.start_question:
            raise ValueError("passage end must follow start")
        return self


class AdditionalContext(Model):
    course_materials: list[Text] = Field(default_factory=list, max_length=100)
    instructions: list[Text] = Field(default_factory=list, max_length=100)
    custom_requirements: list[Text] = Field(default_factory=list, max_length=100)


class GenerationRequest(Model):
    matrix: ExamMatrix
    question_bank: QuestionBank = Field(default_factory=QuestionBank)
    context: AdditionalContext = Field(default_factory=AdditionalContext)
    include_answers: Annotated[bool, Field(strict=True)] = True
    include_solutions: Annotated[bool, Field(strict=True)] = True
    format_profile: Literal["hcm_dgnl_de11"] | None = None

    @model_validator(mode="after")
    def profile_matches_matrix(self):
        if self.format_profile == "hcm_dgnl_de11":
            from .format_profiles import HCM_DE11_SECTIONS

            expected = {topic_id: end - start + 1 for start, end, topic_id, _ in HCM_DE11_SECTIONS}
            actual = {topic.id: topic.question_count for topic in self.matrix.topics}
            if actual != expected or self.matrix.question_count != 120:
                raise ValueError("hcm_dgnl_de11 requires the five fixed section counts")
            if self.matrix.question_type_distribution != {QuestionType.MULTIPLE_CHOICE: 120}:
                raise ValueError("hcm_dgnl_de11 requires 120 multiple-choice questions")
        return self


class ConstraintCheck(Model):
    code: str
    passed: bool
    expected: Any = None
    actual: Any = None
    message: str


class ValidationReport(Model):
    passed: bool
    checks: list[ConstraintCheck]
    constraint_satisfaction_rate: float
    semantic_review_required: list[str]
    warnings: list[str] = Field(default_factory=list)


class TokenUsage(Model):
    input_tokens: Count | None = None
    output_tokens: Count | None = None


Status = Literal[
    "success", "constraint_failure", "schema_failure", "provider_failure", "context_failure"
]


class Evaluation(Model):
    implementation_version: str = __version__
    run_id: str
    created_at: datetime
    status: Status
    provider: str
    requested_model: str
    model: str
    prompt_version: str
    prompt_sha256: str
    request_sha256: str
    response_sha256: str | None = None
    provider_response_id: str | None = None
    generation_latency_ms: float
    total_latency_ms: float
    usage: TokenUsage
    estimated_cost_usd: float | None = None
    input_price_per_million: float | None = None
    output_price_per_million: float | None = None
    generation_parameters: dict[str, Any]
    constraint_satisfaction_rate: float | None = None
    validation_passed: bool | None = None
    error_code: str | None = None


class GenerationError(Model):
    code: str
    message: str
    details: list[dict[str, Any]] = Field(default_factory=list)


class GenerationResponse(Model):
    status: Status
    exam: GeneratedExam | None = None
    validation: ValidationReport | None = None
    evaluation: Evaluation
    error: GenerationError | None = None
    warnings: list[str] = Field(default_factory=list)
