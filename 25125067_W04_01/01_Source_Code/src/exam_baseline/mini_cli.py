"""Create an unreviewed ASTRA mini draft from a request and provider or fixture."""

import argparse
import asyncio
import json
from pathlib import Path

import httpx

from .config import Settings
from .contracts import Completion
from .latex_export import export_latex
from .mini import Evidence, MiniRequest, StageResult, create_draft, private_artifact_path
from .models import QuestionBank
from .providers.chat_completions import ChatCompletionsProvider


class FixtureProvider:
    """Replay a Composer response; never describe this as a live generation."""

    name = "fixture"
    model = "fixture"
    parameters = {}

    def __init__(self, path: Path):
        self.path = path

    async def complete(self, request):
        return Completion(text=self.path.read_text(encoding="utf-8"), model=self.model)


async def run(args) -> int:
    payload = MiniRequest.model_validate_json(args.request.read_text(encoding="utf-8"))
    if args.template:
        payload.latex_template = args.template.read_text(encoding="utf-8-sig")
    if args.prompt:
        payload.user_prompt = args.prompt
    if args.bank:
        payload.request.question_bank = QuestionBank.model_validate_json(
            args.bank.read_text(encoding="utf-8-sig")
        )
    for index, path in enumerate(args.material, start=1):
        payload.evidence.append(
            Evidence(
                id=f"raw-material-{index}",
                text=path.read_text(encoding="utf-8-sig"),
                role="content_support",
                locator=str(path),
            )
        )
    payload = MiniRequest.model_validate(payload.model_dump())
    if args.fixture:
        result = await create_draft(payload, FixtureProvider(args.fixture), args.output)
    else:
        settings = Settings()
        if settings.provider != "chat_completions":
            raise ValueError("Live draft requires EXAM_PROVIDER=chat_completions")
        async with httpx.AsyncClient(follow_redirects=False) as client:
            result = await create_draft(
                payload, ChatCompletionsProvider(settings, client), args.output
            )
    if isinstance(result, StageResult):
        print(result.model_dump_json(indent=2))
        return 1
    latex = export_latex(result, payload, args.output)
    print(
        json.dumps(
            {
                "draft": str(args.output / "exam_draft.json"),
                "student": str(args.output / "student_view.json"),
                "teacher_private": str(private_artifact_path(args.output, result.draft_id)),
                "composer": result.composer.status,
                "illustrator": result.illustrator.status,
                "latex": {name: str(path) for name, path in latex.items()},
            },
            ensure_ascii=False,
        )
    )
    return 0 if result.illustrator.status != "failed" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, help="Replay a Composer JSON fixture")
    parser.add_argument("--template", type=Path, help="LaTeX template with %% ASTRA_BODY %%")
    parser.add_argument(
        "--material",
        type=Path,
        action="append",
        default=[],
        help="Raw UTF-8 RAG/bank material; may be repeated",
    )
    parser.add_argument("--bank", type=Path, help="Normalized QuestionBank JSON")
    parser.add_argument("--prompt", help="Optional user modification prompt")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output directory already exists")
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
