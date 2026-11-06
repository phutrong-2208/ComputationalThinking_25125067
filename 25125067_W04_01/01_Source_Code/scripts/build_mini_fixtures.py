"""Build five synthetic, replayable Composer/Illustrator handoff packages."""

import asyncio
import json
from pathlib import Path

from exam_baseline.contracts import Completion
from exam_baseline.mini import MiniRequest, create_draft, verify_handoff


class FixtureProvider:
    name = "fixture"
    model = "fixture"
    parameters = {}

    def __init__(self, output):
        self.output = output

    async def complete(self, request):
        return Completion(text=json.dumps(self.output, ensure_ascii=False), model=self.model)


def question(identifier, stem, answer, solution, points, difficulty="easy"):
    return dict(
        id=identifier,
        stem=stem,
        topic_id="math",
        subtopic=None,
        learning_objective_ids=[],
        question_type="short_answer",
        difficulty=difficulty,
        points=points,
        choices={},
        answer=answer,
        solution=solution,
        source_question_id=None,
    )


def case(name, title, questions, visuals):
    count = len(questions)
    total = sum(q["points"] for q in questions)
    difficulty = {
        label: sum(q["difficulty"] == label for q in questions)
        for label in ("easy", "medium", "hard")
    }
    matrix = dict(
        subject="Toán",
        title=title,
        topics=[dict(id="math", name="Toán", question_count=count, points=total)],
        question_count=count,
        question_type_distribution={"short_answer": count},
        difficulty_distribution=difficulty,
        total_points=total,
        duration_minutes=20,
    )
    evidence = [
        dict(
            id=f"source-{q['id']}",
            text=f"Fixture synthetic for {name}: {q['stem']}",
            role="content_support",
            locator=f"fixture:{name}:{q['id']}",
        )
        for q in questions
    ]
    request = dict(
        request=dict(matrix=matrix, include_answers=True, include_solutions=True),
        evidence=evidence,
        require_evidence=True,
        required_visual_question_ids=[v["question_id"] for v in visuals],
    )
    output = dict(
        exam=dict(
            title=title,
            subject="Toán",
            duration_minutes=20,
            total_points=total,
            instructions="Trả lời các câu hỏi.",
            questions=questions,
        ),
        questions=[
            dict(
                id=q["id"],
                source_refs=[dict(evidence_id=f"source-{q['id']}", role="content_support")],
                figure_refs=[v["visual_id"] for v in visuals if v["question_id"] == q["id"]],
            )
            for q in questions
        ],
        visuals=visuals,
    )
    return request, output


CASES = {
    "01_text": case(
        "01_text",
        "Phương trình bậc nhất",
        [question("q1", "Giải 2x + 3 = 7.", "x = 2", "2x = 4 nên x = 2.", 2)],
        [],
    ),
    "02_graph": case(
        "02_graph",
        "Đọc đồ thị hàm số",
        [
            question(
                "q1",
                "Theo đồ thị y = 2x + 1, y bằng bao nhiêu khi x = 3?",
                "7",
                "Thay x = 3: y = 7.",
                2,
            )
        ],
        [
            dict(
                visual_id="graph_q1",
                question_id="q1",
                revision=1,
                required=True,
                purpose="Đồ thị y=2x+1",
                kind="line_graph",
                points=[[0, 1], [1, 3], [2, 5], [3, 7]],
                x_domain=[0, 4],
                y_domain=[0, 9],
                x_label="x",
                y_label="y",
            )
        ],
    ),
    "03_geometry": case(
        "03_geometry",
        "Tam giác vuông",
        [
            question(
                "q1",
                "Tam giác ABC vuông tại A, AB = 3 cm và AC = 4 cm. Tính BC.",
                "5 cm",
                "Áp dụng Pythagoras: BC = 5 cm.",
                3,
                "medium",
            )
        ],
        [
            dict(
                visual_id="triangle_q1",
                question_id="q1",
                revision=1,
                required=True,
                purpose="Sơ đồ tam giác ABC",
                kind="geometry_segments",
                points=[[0, 0], [3, 0], [0, 4]],
                labels=["A", "B", "C"],
                segments=[[0, 1], [1, 2], [2, 0]],
                units="cm",
                scaling="equal",
            )
        ],
    ),
    "04_chart": case(
        "04_chart",
        "Đọc biểu đồ cột",
        [
            question(
                "q1",
                "Số sách của ba lớp A, B, C lần lượt như biểu đồ. Tổng là bao nhiêu?",
                "12",
                "3 + 5 + 4 = 12.",
                2,
            )
        ],
        [
            dict(
                visual_id="books_q1",
                question_id="q1",
                revision=1,
                required=True,
                purpose="Số sách từng lớp",
                kind="bar_chart",
                labels=["A", "B", "C"],
                values=[3, 5, 4],
                units="quyển",
                x_label="Lớp",
                y_label="Số sách (quyển)",
            )
        ],
    ),
    "05_mixed": case(
        "05_mixed",
        "Bài tập hỗn hợp",
        [
            question("q1", "Giải x + 5 = 9.", "x = 4", "Trừ 5 hai vế.", 2),
            question(
                "q2",
                "Theo đồ thị y = x + 2, y bằng bao nhiêu khi x = 3?",
                "5",
                "Thay x = 3: y = 5.",
                3,
                "medium",
            ),
        ],
        [
            dict(
                visual_id="graph_q2",
                question_id="q2",
                revision=1,
                required=True,
                purpose="Đồ thị y=x+2",
                kind="line_graph",
                points=[[0, 2], [1, 3], [2, 4], [3, 5]],
                x_domain=[0, 4],
                y_domain=[0, 6],
                x_label="x",
                y_label="y",
            )
        ],
    ),
}


async def build(root):
    for name, (request, output) in CASES.items():
        folder = root / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "input.json").write_text(
            json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (folder / "composer_fixture.json").write_text(
            json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        draft = await create_draft(
            MiniRequest.model_validate(request), FixtureProvider(output), folder / "handoff"
        )
        assert draft.composer.status == "succeeded" and draft.illustrator.status != "failed"
        assert not verify_handoff(draft, folder / "handoff")
        print(name, draft.composer.status, draft.illustrator.status)


if __name__ == "__main__":
    asyncio.run(build(Path("examples/mini")))
