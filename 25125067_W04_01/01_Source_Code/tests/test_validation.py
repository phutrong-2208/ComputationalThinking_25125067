import pytest

from exam_baseline.context import JsonContextLoader, normalized_text
from exam_baseline.models import GeneratedExam
from exam_baseline.validation import ExamValidator


def test_example_passes_but_requires_semantic_review(exam, request_model):
    report = ExamValidator().validate(exam, request_model)
    assert report.passed
    assert report.constraint_satisfaction_rate == 1
    assert len(report.semantic_review_required) >= 5


@pytest.mark.parametrize(
    "mutation,code",
    [
        (lambda e: e["questions"].pop(), "question_count"),
        (lambda e: e.update(title="Wrong title"), "title"),
        (lambda e: e.update(subject="Other"), "subject"),
        (lambda e: e.update(duration_minutes=60), "duration_minutes"),
        (lambda e: e.update(total_points=99), "declared_total_points"),
        (lambda e: e["questions"][0].update(points=9), "total_points"),
        (lambda e: e["questions"][0].update(points=9), "topic_points:algebra"),
        (lambda e: e["questions"][0].update(points=9), "type_points:multiple_choice"),
        (lambda e: e["questions"][1].update(topic_id="functions"), "topic_count:algebra"),
        (lambda e: e["questions"][0].update(difficulty="hard"), "difficulty_count:easy"),
        (lambda e: e["questions"][1].update(question_type="essay"), "type_count:essay"),
        (lambda e: e["questions"][1].update(id="q1"), "unique_question_ids"),
        (
            lambda e: e["questions"][1].update(stem=e["questions"][0]["stem"].upper()),
            "duplicate_stems",
        ),
        (lambda e: e["questions"][1].update(topic_id="invented"), "known_topics"),
        (lambda e: e["questions"][1].update(subtopic="invented"), "known_subtopics"),
        (
            lambda e: e["questions"][1].update(learning_objective_ids=["invented"]),
            "known_objectives",
        ),
        (
            lambda e: [q.update(subtopic=None) for q in e["questions"][:2]],
            "subtopic_coverage:algebra:linear_equations",
        ),
        (
            lambda e: [q.update(learning_objective_ids=[]) for q in e["questions"][:2]],
            "objective_coverage:solve_linear",
        ),
        (lambda e: e["questions"][0].update(answer=None), "answers_policy"),
        (lambda e: e["questions"][0].update(solution=None), "solutions_policy"),
        (lambda e: e["questions"][0].update(source_question_id="fake"), "valid_source_references"),
        (lambda e: e["questions"][0].update(stem="An altered question"), "faithful_source_reuse"),
        (lambda e: e["questions"][0].update(answer="A"), "faithful_source_reuse"),
        (lambda e: e["questions"][0].update(source_question_id=None), "bank_copy_has_reference"),
        (
            lambda e: e["questions"][1].update(source_question_id="bank-linear-001"),
            "unique_source_references",
        ),
    ],
)
def test_constraint_failures_are_reported(exam_dict, request_model, mutation, code):
    mutation(exam_dict)
    report = ExamValidator().validate(GeneratedExam.model_validate(exam_dict), request_model)
    failures = {check.code for check in report.checks if not check.passed}
    assert code in failures
    assert not report.passed
    assert 0 <= report.constraint_satisfaction_rate < 1


def test_unknown_topic_does_not_hide_invalid_objectives(exam, request_model):
    exam.questions[0].topic_id = "unknown"
    exam.questions[1].learning_objective_ids = ["wrong"]
    report = ExamValidator().validate(exam, request_model)
    check = next(c for c in report.checks if c.code == "known_objectives")
    assert set(check.actual) == {"q1", "q2"}


def test_float_sum_uses_tolerance(exam, request_model):
    exam.questions[0].points += 1e-9
    assert ExamValidator().validate(exam, request_model).passed


def test_normalization_preserves_math_and_detects_whitespace():
    assert normalized_text("  Same   Question? ") == normalized_text("same question")
    assert normalized_text("x+1") != normalized_text("x-1")


def test_loader_warns_without_dropping_bank_questions(request_model):
    copied = request_model.question_bank.questions[0].model_copy(deep=True)
    copied.id = "duplicate-content"
    copied.topic_id = "out-of-scope"
    request_model.question_bank.questions.append(copied)
    context = JsonContextLoader().prepare(request_model)
    assert len(context.warnings) == 2
    assert len(context.request.question_bank.questions) == 3
    assert context.request is not request_model
