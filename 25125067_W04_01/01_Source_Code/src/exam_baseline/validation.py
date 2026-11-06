"""Deterministic label/structure checks. Passing never certifies semantic correctness."""

from collections import Counter
from collections.abc import Iterable
from typing import Any

from .context import normalized_text
from .format_profiles import HCM_DE11_PASSAGES, HCM_DE11_SECTIONS
from .models import (
    EPSILON,
    BankQuestion,
    ConstraintCheck,
    Difficulty,
    GeneratedExam,
    GenerationRequest,
    Question,
    QuestionType,
    ValidationReport,
)


def _faithful_reuse(question: Question, original: BankQuestion, request: GenerationRequest) -> bool:
    fields = ("topic_id", "subtopic", "question_type", "difficulty", "choices")
    if any(getattr(question, field) != getattr(original, field) for field in fields):
        return False
    if normalized_text(question.stem) != normalized_text(original.stem):
        return False
    if set(question.learning_objective_ids) != set(original.learning_objective_ids):
        return False
    if (
        request.include_answers
        and original.answer is not None
        and question.answer != original.answer
    ):
        return False
    return not (
        request.include_solutions
        and original.solution is not None
        and question.solution != original.solution
    )


class ExamValidator:
    def validate(self, exam: GeneratedExam, request: GenerationRequest) -> ValidationReport:
        matrix, questions = request.matrix, exam.questions
        checks: list[ConstraintCheck] = []

        def check(code: str, expected: Any, actual: Any, *, numeric: bool = False) -> None:
            passed = abs(expected - actual) <= EPSILON if numeric else expected == actual
            checks.append(
                ConstraintCheck(
                    code=code,
                    passed=passed,
                    expected=expected,
                    actual=actual,
                    message="Satisfied." if passed else "Constraint not satisfied.",
                )
            )

        def unique(code: str, values: Iterable[str]) -> None:
            duplicates = sorted(v for v, n in Counter(values).items() if n > 1)
            check(code, [], duplicates)

        check("schema_valid", True, True)
        check("title", matrix.title, exam.title)
        check("subject", matrix.subject, exam.subject)
        check("duration_minutes", matrix.duration_minutes, exam.duration_minutes)
        check("question_count", matrix.question_count, len(questions))
        check("declared_total_points", matrix.total_points, exam.total_points, numeric=True)
        check("total_points", matrix.total_points, sum(q.points for q in questions), numeric=True)
        unique("unique_question_ids", [q.id for q in questions])
        unique("duplicate_stems", [normalized_text(q.stem) for q in questions])

        if request.format_profile == "hcm_dgnl_de11":
            check(
                "profile_question_ids", [f"q{i}" for i in range(1, 121)], [q.id for q in questions]
            )
            expected_topics = [
                topic_id
                for start, end, topic_id, _ in HCM_DE11_SECTIONS
                for _ in range(start, end + 1)
            ]
            check("profile_section_order", expected_topics, [q.topic_id for q in questions])
            check(
                "profile_choice_keys",
                [],
                [q.id for q in questions if set(q.choices) != {"A", "B", "C", "D"}],
            )
            expected_ranges = list(HCM_DE11_PASSAGES)
            actual_ranges = [(p.start_question, p.end_question) for p in exam.shared_passages]
            check("profile_passage_ranges", expected_ranges, actual_ranges)
            check(
                "profile_passage_content",
                [],
                [
                    f"{p.start_question}-{p.end_question}"
                    for p in exam.shared_passages
                    if len(p.text.split()) < 15
                ],
            )
            check(
                "profile_passage_duplicates",
                [],
                sorted(
                    text
                    for text, count in Counter(
                        normalized_text(p.text) for p in exam.shared_passages
                    ).items()
                    if count > 1
                ),
            )

        topic_map = {t.id: t for t in matrix.topics}
        check("known_topics", [], sorted({q.topic_id for q in questions} - set(topic_map)))
        for topic in matrix.topics:
            group = [q for q in questions if q.topic_id == topic.id]
            check(f"topic_count:{topic.id}", topic.question_count, len(group))
            if topic.points is not None:
                check(
                    f"topic_points:{topic.id}",
                    topic.points,
                    sum(q.points for q in group),
                    numeric=True,
                )
            for subtopic in topic.subtopics:
                check(
                    f"subtopic_coverage:{topic.id}:{subtopic}",
                    True,
                    any(q.subtopic == subtopic for q in group),
                )
            for objective in topic.learning_objectives:
                check(
                    f"objective_coverage:{objective.id}",
                    True,
                    any(objective.id in q.learning_objective_ids for q in group),
                )
        bad_subtopics = [
            q.id
            for q in questions
            if q.subtopic is not None
            and (q.topic_id not in topic_map or q.subtopic not in topic_map[q.topic_id].subtopics)
        ]
        check("known_subtopics", [], bad_subtopics)
        bad_objectives = [
            q.id
            for q in questions
            if q.learning_objective_ids
            and (
                q.topic_id not in topic_map
                or set(q.learning_objective_ids)
                - {o.id for o in topic_map[q.topic_id].learning_objectives}
            )
        ]
        check("known_objectives", [], bad_objectives)
        for kind in QuestionType:
            check(
                f"type_count:{kind.value}",
                matrix.question_type_distribution.get(kind, 0),
                sum(q.question_type == kind for q in questions),
            )
        for difficulty in Difficulty:
            check(
                f"difficulty_count:{difficulty.value}",
                matrix.difficulty_distribution.get(difficulty, 0),
                sum(q.difficulty == difficulty for q in questions),
            )
        if matrix.points_by_type is not None:
            for kind, points in matrix.points_by_type.items():
                check(
                    f"type_points:{kind.value}",
                    points,
                    sum(q.points for q in questions if q.question_type == kind),
                    numeric=True,
                )

        check(
            "answers_policy",
            [],
            [q.id for q in questions if (q.answer is not None) != request.include_answers],
        )
        check(
            "solutions_policy",
            [],
            [q.id for q in questions if (q.solution is not None) != request.include_solutions],
        )
        bank = {q.id: q for q in request.question_bank.questions}
        bank_stems = {normalized_text(q.stem) for q in bank.values()}
        invalid_sources, changed_sources, missing_sources = [], [], []
        for question in questions:
            source = question.source_question_id
            if source is None:
                if normalized_text(question.stem) in bank_stems:
                    missing_sources.append(question.id)
                continue
            if source not in bank:
                invalid_sources.append(question.id)
                continue
            if not _faithful_reuse(question, bank[source], request):
                changed_sources.append(question.id)
        check("valid_source_references", [], invalid_sources)
        check("faithful_source_reuse", [], changed_sources)
        check("bank_copy_has_reference", [], missing_sources)
        unique(
            "unique_source_references",
            [q.source_question_id for q in questions if q.source_question_id is not None],
        )
        semantic = [
            "Answer and solution correctness; clarity and ambiguity; curriculum appropriateness.",
            "Topic/objective alignment and difficulty calibration; only labels were checked.",
            "Semantic duplicate detection and realistic completion time (metadata only checked).",
        ]
        if request.format_profile == "hcm_dgnl_de11":
            semantic.append(
                "Review whether each grouped question is answerable from its passage, "
                "and whether visual data and subject content match the intended exam style."
            )
        semantic.extend(f"Matrix constraint: {c}" for c in matrix.additional_constraints)
        semantic.extend(f"Context instruction: {c}" for c in request.context.instructions)
        semantic.extend(f"Custom requirement: {c}" for c in request.context.custom_requirements)
        return ValidationReport(
            passed=all(c.passed for c in checks),
            checks=checks,
            constraint_satisfaction_rate=sum(c.passed for c in checks) / len(checks),
            semantic_review_required=semantic,
        )
