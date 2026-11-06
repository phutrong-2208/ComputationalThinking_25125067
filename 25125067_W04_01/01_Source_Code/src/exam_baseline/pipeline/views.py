"""Explicit data views: Solver cannot access request banks, evidence or teacher keys."""

from pathlib import Path

from ..mini import ExamDraft, digest
from .contracts import IllustrationBook, PipelineRequest, SolutionBook


def illustration_view(draft: ExamDraft) -> dict:
    visual_questions = {spec.question_id for spec in draft.visuals}
    return {
        "exam_id": draft.exam_id,
        "draft_id": draft.draft_id,
        "revision": draft.revision,
        "visual_specs": [
            {**spec.model_dump(mode="json"), "spec_sha256": digest(spec.model_dump_json().encode())}
            for spec in draft.visuals
        ],
        "questions": [
            {"id": q.id, "stem": q.stem, "choices": q.choices}
            for q in draft.exam.questions
            if q.id in visual_questions
        ],
    }


def validate_illustrations(book: IllustrationBook, draft: ExamDraft) -> None:
    from .latex import validate_drawing_code

    for field in ("exam_id", "draft_id", "revision"):
        if getattr(book, field) != getattr(draft, field):
            raise ValueError("illustrations must match the current draft identity")
    specs = {spec.visual_id: spec for spec in draft.visuals}
    if len(book.drawings) != len(specs) or {d.visual_id for d in book.drawings} != set(specs):
        raise ValueError("illustrations must cover each visual exactly once")
    for drawing in book.drawings:
        spec = specs[drawing.visual_id]
        if drawing.question_id != spec.question_id or drawing.spec_sha256 != digest(
            spec.model_dump_json().encode()
        ):
            raise ValueError("illustration is bound to an incorrect question or spec")
        validate_drawing_code(drawing.latex)


def student_view(
    draft: ExamDraft, root: Path, illustrations: IllustrationBook, latex_source: str
) -> tuple[dict, tuple]:
    validate_illustrations(illustrations, draft)
    saved = IllustrationBook.model_validate_json(
        (root / "illustrations.json").read_text(encoding="utf-8")
    )
    if saved != illustrations or (root / "merged.tex").read_text(encoding="utf-8") != latex_source:
        raise ValueError("handoff source changed")
    if any(q.answer is not None or q.solution is not None for q in draft.exam.questions):
        raise ValueError("student answer fields must be empty")
    exam = draft.exam.model_dump(mode="json", exclude_none=True)
    fields = {"id", "stem", "question_type", "choices", "points"}
    exam["questions"] = [{k: v for k, v in q.items() if k in fields} for q in exam["questions"]]
    return {
        "exam_id": draft.exam_id,
        "draft_id": draft.draft_id,
        "revision": draft.revision,
        "artifact_sha256": digest(latex_source.encode()),
        "exam": exam,
        "latex_source": latex_source,
        "drawing_source": [
            {"visual_id": d.visual_id, "question_id": d.question_id, "latex": d.latex}
            for d in illustrations.drawings
        ],
        "image_manifest": [],
        "inspection_scope": "text_and_latex_source",
    }, ()


def reviewer_view(student: dict, solutions: SolutionBook, payload: PipelineRequest) -> dict:
    # Only requested constraints, never raw bank/context/evidence with answer-bearing data.
    return {
        "student_view": student,
        "solutions": solutions.model_dump(mode="json"),
        "solution_sha256": solution_hash(solutions),
        "matrix": payload.request.matrix.model_dump(mode="json"),
        "format_profile": payload.request.format_profile,
        "required_visual_question_ids": payload.required_visual_question_ids,
    }


def solution_hash(book: SolutionBook) -> str:
    return digest(book.model_dump_json().encode())
