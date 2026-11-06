"""Build ten synthetic text packets plus a visual replay, never call a live model.

Solver/Reviewer responses are scripted, not independent quality measurements.
"""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def packet(folder, request, composer):
    identity = {
        key: "__CURRENT__" for key in ("exam_id", "draft_id", "revision", "artifact_sha256")
    }
    write(folder / "input.json", request)
    write(folder / "composer_01.json", composer)
    drawings = []
    for spec in composer.get("visuals", []):
        if spec["kind"] != "line_graph":
            raise ValueError("This replay builder currently defines a line-graph fixture only")
        coordinates = " ".join(f"({x},{y})" for x, y in spec["points"])
        x0, x1 = spec["x_domain"]
        y0, y1 = spec["y_domain"]
        code = (
            r"\begin{tikzpicture}"
            + "\n"
            + r"\begin{axis}["
            + f"width=11cm,height=8cm,axis lines=left,xmin={x0},xmax={x1},"
            + f"ymin={y0},ymax={y1},xlabel={{$x$}},ylabel={{$y$}},"
            + "xtick={0,1,2,3,4},ytick={0,1,2,3,4,5,6,7,8,9},grid=major]"
            + "\n"
            + r"\addplot[blue,thick] coordinates {"
            + coordinates
            + "};\n"
            + r"\end{axis}"
            + "\n"
            + r"\end{tikzpicture}"
        )
        drawings.append(
            {
                "visual_id": spec["visual_id"],
                "question_id": spec["question_id"],
                "spec_sha256": "__CURRENT__",
                "latex": code,
            }
        )
    write(
        folder / "illustrator_01.json",
        {key: "__CURRENT__" for key in ("exam_id", "draft_id", "revision")}
        | {"drawings": drawings},
    )
    write(
        folder / "solver_01.json",
        {
            **identity,
            "entries": [
                {
                    "question_id": q["id"],
                    "solvability": "solvable",
                    "answer": q["answer"],
                    "explanation": q["solution"],
                }
                for q in composer["exam"]["questions"]
            ],
        },
    )
    write(
        folder / "reviewer_01.json",
        {
            **identity,
            "solution_sha256": "__CURRENT__",
            "checked_question_ids": [q["id"] for q in composer["exam"]["questions"]],
            "decision": "approved",
            "issues": [],
        },
    )


def main():
    root = ROOT / "examples/pipeline"
    cases = []
    reviewer_cases = []
    for number in range(1, 11):
        a, b = number + 2, number + 5
        questions = []
        specs = [
            (f"Tính ${a}+{b}$.", a + b, "multiple_choice", "easy", "A"),
            (f"Giải phương trình $2x+{b}={2 * a + b}$.", a, "short_answer", "medium", None),
            (f"Cho $f(x)={a}x+{b}$. Tính $f(2)$.", 2 * a + b, "multiple_choice", "easy", "B"),
            (
                f"Hình chữ nhật có chiều dài {a} cm và chiều rộng {b} cm. "
                "Diện tích bằng bao nhiêu cm vuông?",
                a * b,
                "short_answer",
                "medium",
                None,
            ),
        ]
        for index, (stem, answer, kind, difficulty, key) in enumerate(specs, 1):
            choices = {}
            if key:
                choices = {
                    "A": str(answer + 1),
                    "B": str(answer + 2),
                    "C": str(answer - 1),
                    "D": str(answer + 3),
                }
                choices[key] = str(answer)
            explanation = [
                f"Cộng hai số: {a}+{b}={a + b}.",
                f"Chuyển vế được 2x={2 * a}; x={a}.",
                f"Thay x=2: f(2)={a}*2+{b}={2 * a + b}.",
                f"Diện tích bằng chiều dài nhân chiều rộng: {a}*{b}={a * b}.",
            ][index - 1]
            questions.append(
                {
                    "id": f"q{index}",
                    "stem": stem,
                    "topic_id": "math",
                    "question_type": kind,
                    "difficulty": difficulty,
                    "points": 1.0,
                    "choices": choices,
                    "answer": key or str(answer),
                    "solution": explanation,
                }
            )
        title = f"Đề toán synthetic {number:02d}"
        request = {
            "request": {
                "matrix": {
                    "subject": "Toán",
                    "title": title,
                    "duration_minutes": 20,
                    "question_count": 4,
                    "total_points": 4.0,
                    "topics": [{"id": "math", "name": "Toán", "question_count": 4}],
                    "question_type_distribution": {"multiple_choice": 2, "short_answer": 2},
                    "difficulty_distribution": {"easy": 2, "medium": 2, "hard": 0},
                }
            }
        }
        composer = {
            "exam": {
                "title": title,
                "subject": "Toán",
                "duration_minutes": 20,
                "total_points": 4.0,
                "instructions": "Trả lời các câu hỏi.",
                "questions": questions,
            },
            "questions": [{"id": q["id"]} for q in questions],
            "visuals": [],
        }
        folder = root / f"text_{number:02d}"
        packet(folder, request, composer)
        for defective in (False, True):
            question = dict(questions[0])
            question.pop("answer")
            question.pop("solution")
            identity = {
                "exam_id": f"review-{number}-{int(defective)}",
                "draft_id": f"review-draft-{number}-{int(defective)}",
                "revision": 1,
                "artifact_sha256": hashlib.sha256(
                    json.dumps(question, sort_keys=True).encode()
                ).hexdigest(),
            }
            student = {
                **identity,
                "exam": {**composer["exam"], "questions": [question], "total_points": 1.0},
                "image_manifest": [],
            }
            book = {
                **identity,
                "entries": [
                    {
                        "question_id": "q1",
                        "solvability": "solvable",
                        "answer": "D" if defective else "A",
                        "explanation": questions[0]["solution"],
                    }
                ],
            }
            issue = {
                "code": "wrong_answer",
                "severity": "major",
                "target": "solver",
                "question_id": "q1",
                "evidence": f"{a}+{b}={a + b}; key A, not D.",
                "message": "The answer key does not match the arithmetic.",
                "suggested_action": "Re-solve the question and correct the key.",
            }
            reviewer_cases.append(
                {
                    "id": f"{'defect' if defective else 'clean'}_{number:02d}",
                    "student_view": student,
                    "solutions": book,
                    "matrix": {
                        **request["request"]["matrix"],
                        "question_count": 1,
                        "total_points": 1.0,
                        "topics": [{"id": "math", "name": "Toán", "question_count": 1}],
                        "question_type_distribution": {"multiple_choice": 1},
                        "difficulty_distribution": {"easy": 1},
                    },
                    "gold": [{"code": "wrong_answer", "question_id": "q1"}] if defective else [],
                    "replay": {
                        **identity,
                        "solution_sha256": "__CURRENT__",
                        "checked_question_ids": ["q1"],
                        "decision": "needs_revision" if defective else "approved",
                        "issues": [issue] if defective else [],
                    },
                }
            )
        cases.append(
            {
                "id": f"text_{number:02d}",
                "track": "text",
                "request": f"text_{number:02d}/input.json",
                "fixtures": f"text_{number:02d}",
            }
        )
    visual = ROOT / "examples/mini/02_graph"
    packet(
        root / "visual_graph",
        json.loads((visual / "input.json").read_text(encoding="utf-8")),
        json.loads((visual / "composer_fixture.json").read_text(encoding="utf-8")),
    )
    write(root / "pilot.json", {"repeats": 2, "cases": cases})
    write(
        root / "reviewer_suite.json",
        {"scope": "synthetic arithmetic answer-key errors only", "cases": reviewer_cases},
    )
    print("Built 10 text replay cases (2 repeats) and one visual packet; no model calls.")


if __name__ == "__main__":
    main()
