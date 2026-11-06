import pytest
from pydantic import ValidationError

from exam_baseline.config import Settings
from exam_baseline.models import GeneratedExam, GenerationRequest


@pytest.mark.parametrize(
    "field,value",
    [
        ("question_count", 5),
        ("total_points", 11),
        ("duration_minutes", 0),
        ("question_type_distribution", {"essay": 3}),
        ("difficulty_distribution", {"easy": 4, "extreme": 0}),
        ("question_count", True),
        ("total_points", True),
        ("total_points", float("nan")),
    ],
)
def test_rejects_invalid_matrix(payload, field, value):
    payload["matrix"][field] = value
    with pytest.raises(ValidationError):
        GenerationRequest.model_validate(payload)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p["matrix"]["topics"][1].update(id="algebra"),
        lambda p: p["matrix"]["topics"][1]["learning_objectives"][0].update(id="solve_linear"),
        lambda p: p["matrix"]["topics"][0].update(subtopics=["same", "same"]),
        lambda p: p["matrix"]["topics"][0].update(subtopics=["a", "b", "c"]),
        lambda p: p["matrix"]["topics"][0].update(points=0),
        lambda p: p["matrix"].update(points_by_type={"multiple_choice": 10}),
        lambda p: p["question_bank"]["questions"][1].update(id="bank-linear-001"),
        lambda p: p.update(include_answers="false"),
        lambda p: p.update(unexpected=True),
    ],
)
def test_rejects_inconsistent_input(payload, mutation):
    mutation(payload)
    with pytest.raises(ValidationError):
        GenerationRequest.model_validate(payload)


def test_empty_bank_and_optional_context_are_supported(payload):
    request = GenerationRequest(matrix=payload["matrix"])
    assert request.question_bank.questions == []
    assert request.context.course_materials == []


@pytest.mark.parametrize(
    "change",
    [
        {"choices": {"A": "only one"}},
        {"answer": "missing-key"},
        {"choices": {"A": "same", "B": "SAME"}},
        {"stem": "   "},
        {"points": 0},
        {"learning_objective_ids": ["duplicate", "duplicate"]},
    ],
)
def test_structural_output_validation(exam_dict, change):
    exam_dict["questions"][0].update(change)
    with pytest.raises(ValidationError):
        GeneratedExam.model_validate(exam_dict)


def test_true_false_answer_is_not_arbitrary_text(exam_dict):
    exam_dict["questions"][2]["answer"] = "maybe"
    with pytest.raises(ValidationError):
        GeneratedExam.model_validate(exam_dict)


def test_partial_topic_budgets_must_leave_positive_points(payload):
    payload["matrix"]["topics"][0]["points"] = 10
    payload["matrix"]["topics"][1]["points"] = None
    with pytest.raises(ValidationError):
        GenerationRequest.model_validate(payload)


def test_configuration_requires_complete_prices_and_real_model():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, input_price_per_million=1)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, provider="chat_completions", api_key="secret")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, provider="chat_completions", model="test")


@pytest.mark.parametrize(
    "url", ["not-a-url", "https://user:pass@example.com/v1", "https://x?key=a"]
)
def test_invalid_provider_urls_are_rejected(url):
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None, provider="chat_completions", model="test", api_key="x", base_url=url
        )
