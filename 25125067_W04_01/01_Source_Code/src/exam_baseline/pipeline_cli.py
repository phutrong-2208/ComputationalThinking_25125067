"""Four-agent LaTeX generation, one Reviewer feedback, then user visual inspection."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from .mini import Evidence
from .models import QuestionBank
from .pipeline.bootstrap import provider_scope, replay_providers
from .pipeline.contracts import PipelineRequest
from .pipeline.orchestrator import Orchestrator, PipelineFailure


def load_request(args) -> PipelineRequest:
    payload = PipelineRequest.model_validate_json(args.request.read_text(encoding="utf-8-sig"))
    if args.template:
        payload.latex_template = args.template.read_text(encoding="utf-8-sig")
    if args.prompt:
        payload.user_prompt = args.prompt
    if args.bank:
        payload.request.question_bank = QuestionBank.model_validate_json(
            args.bank.read_text(encoding="utf-8-sig")
        )
    for index, path in enumerate(args.material, 1):
        payload.evidence.append(
            Evidence(
                id=f"raw-material-{index}",
                role="content_support",
                text=path.read_text(encoding="utf-8-sig"),
                locator=str(path),
            )
        )
    return PipelineRequest.model_validate(payload.model_dump())


async def run(args) -> int:
    payload = load_request(args)
    if args.fixture_dir:
        result = await Orchestrator(replay_providers(args.fixture_dir)).run(
            payload, args.output, compile_latex=args.compile
        )
    else:
        async with provider_scope(payload) as providers:
            result = await Orchestrator(providers).run(
                payload, args.output, compile_latex=args.compile
            )
    print(
        json.dumps(
            {
                "execution_status": result.execution_status,
                "quality_decision": result.quality_decision,
                "latex": result.final_latex,
                "latex_validation": result.latex_validation,
                "calls": len(result.calls),
                "repairs": result.repairs,
                "reviewer_feedback_sent": result.reviewer_feedback_sent,
                "human_review_required": result.human_review_required,
                "human_review": (
                    str(args.output / "_internal/human_review.md")
                    if (args.output / "_internal/human_review.md").is_file()
                    else None
                ),
                "report": str(args.output / "_internal/pipeline_result.json"),
                "errors": [e.model_dump() for e in result.errors],
            },
            ensure_ascii=False,
        )
    )
    return 0 if result.final_latex else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fixture-dir", type=Path, help="Replay only; no live model calls")
    parser.add_argument("--template", type=Path)
    parser.add_argument("--bank", type=Path)
    parser.add_argument("--material", type=Path, action="append", default=[])
    parser.add_argument("--prompt")
    parser.add_argument(
        "--compile", action="store_true", help="Require XeLaTeX/LuaLaTeX compilation"
    )
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output directory already exists")
    try:
        return asyncio.run(run(args))
    except ValidationError as exc:
        # Never echo raw input/configuration (which can include credentials).
        print(
            json.dumps(
                {
                    "error": "invalid_input",
                    "fields": [
                        {"location": list(e["loc"]), "type": e["type"]}
                        for e in exc.errors(include_input=False, include_url=False)
                    ],
                }
            ),
            file=sys.stderr,
        )
    except (OSError, ValueError, PipelineFailure) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
