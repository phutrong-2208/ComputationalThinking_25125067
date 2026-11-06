"""Deterministic LaTeX exporter for a validated mini draft."""

import json
import re
from pathlib import Path

from .mini import ExamDraft, MiniRequest, private_artifact_path, verify_handoff
from .models import QuestionType

MARKER = "%% ASTRA_BODY %%"
DEFAULT_TEMPLATE = r"""\documentclass[12pt,a4paper]{article}
\usepackage{fontspec}
\usepackage{amsmath,amssymb,graphicx}
\setmainfont{Arial}
\begin{document}
%% ASTRA_BODY %%
\end{document}
"""
_MATH = re.compile(r"(\$[^$\n]+\$|\\\([^\n]*?\\\)|\\\[[\s\S]*?\\\])")
_ESCAPES = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def latex_text(value: str) -> str:
    """Escape prose while preserving explicit math spans."""
    parts = _MATH.split(value)
    return "".join(
        part if index % 2 else "".join(_ESCAPES.get(char, char) for char in part)
        for index, part in enumerate(parts)
    )


def _document(template: str, body: str) -> str:
    if template.count(MARKER) != 1:
        raise ValueError("LaTeX template must contain exactly one ASTRA_BODY marker")
    return template.replace(MARKER, body) + "\n"


def export_latex(draft: ExamDraft, payload: MiniRequest, root: Path) -> dict[str, Path]:
    """Write student exam, private key and answer sheet after handoff validation."""
    failures = verify_handoff(draft, root)
    if failures:
        raise ValueError("draft handoff is invalid: " + ", ".join(e.code for e in failures))
    template = payload.latex_template or DEFAULT_TEMPLATE
    private = json.loads(private_artifact_path(root, draft.draft_id).read_text(encoding="utf-8"))
    if any(private[q.id]["answer"] is None for q in draft.exam.questions):
        raise ValueError("answer key requires answers for every question")
    topic_names = {topic.id: topic.name for topic in payload.request.matrix.topics}
    passages = {passage.start_question: passage for passage in draft.exam.shared_passages}
    figures = {figure.visual_id: figure for figure in draft.figures}
    metadata = {question.id: question for question in draft.questions}
    student = [
        rf"\begin{{center}}\Large\textbf{{{latex_text(draft.exam.title)}}}\end{{center}}",
        rf"\noindent Thời gian: {draft.exam.duration_minutes} phút.\\",
        latex_text(draft.exam.instructions),
        "",
    ]
    key = [rf"\section*{{Đáp án: {latex_text(draft.exam.title)}}}"]
    sheet = [
        rf"\section*{{Phiếu trả lời: {latex_text(draft.exam.title)}}}",
        r"\noindent Họ tên: \dotfill\quad Số báo danh: \dotfill",
        "",
    ]
    current_topic = None
    for index, question in enumerate(draft.exam.questions, start=1):
        if question.topic_id != current_topic:
            current_topic = question.topic_id
            student.append(rf"\section*{{{latex_text(topic_names[current_topic])}}}")
        if index in passages:
            passage = passages[index]
            student.append(
                rf"\noindent\textit{{Dựa vào thông tin sau để trả lời câu "
                rf"{index}--{passage.end_question}:}}\par"
            )
            student.append(latex_text(passage.text) + r"\par")
        stem = (
            question.stem
            if metadata[question.id].stem_format == "latex"
            else latex_text(question.stem)
        )
        student.append(rf"\noindent\textbf{{Câu {index}.}} " + stem + r"\par")
        if question.question_type == QuestionType.MULTIPLE_CHOICE:
            for label in question.choices:
                student.append(
                    rf"\noindent\hspace*{{1em}}{label}. "
                    + latex_text(question.choices[label])
                    + r"\par"
                )
            sheet.append(
                rf"\noindent Câu {index}: "
                + r"\quad ".join(rf"$\bigcirc$ {label}" for label in question.choices)
                + r"\par"
            )
        else:
            sheet.append(rf"\noindent Câu {index}: \dotfill\par")
        for visual_id in metadata[question.id].figure_refs:
            figure = figures[visual_id]
            student.append(
                r"\begin{center}\includegraphics[width=.8\linewidth]{"
                + figure.path.replace("\\", "/")
                + r"}\end{center}"
            )
        answer = private[question.id]
        key.append(
            rf"\noindent\textbf{{Câu {index}: {latex_text(answer['answer'])}}}"
            + (" " + latex_text(answer["solution"]) if answer["solution"] else "")
            + r"\par"
        )
    paths = {
        "exam": root / "de_thi.tex",
        "answer_key": root / "dap_an.tex",
        "answer_sheet": root / "phieu_tra_loi.tex",
    }
    for name, body in (("exam", student), ("answer_key", key), ("answer_sheet", sheet)):
        paths[name].write_text(_document(template, "\n".join(body)), encoding="utf-8")
    return paths
