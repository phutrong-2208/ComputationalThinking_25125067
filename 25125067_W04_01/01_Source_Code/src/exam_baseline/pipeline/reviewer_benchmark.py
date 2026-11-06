"""Isolated 10-clean/10-seeded Reviewer suite; gold never enters the stage packet."""

import argparse
import asyncio
import json
from pathlib import Path

from ..contracts import ProviderError
from .bootstrap import ReplayProvider, provider_scope
from .contracts import PipelineRequest, PipelineResult, ReviewReport, SolutionBook
from .runtime import TracedProvider
from .stages import StageContractError, structured_stage, validate_review
from .views import solution_hash


async def evaluate_case(case: dict, provider, config) -> dict:
    student = case["student_view"]
    book = SolutionBook.model_validate(case["solutions"])
    # Explicit allowlist: case.gold and case.replay are evaluator-only, never prompt data.
    packet = {
        "student_view": student,
        "solutions": book.model_dump(mode="json"),
        "solution_sha256": solution_hash(book),
        "matrix": case["matrix"],
        "required_visual_question_ids": [],
        "format_profile": None,
    }
    result = PipelineResult(run_id=case["id"])
    traced = TracedProvider(provider, "reviewer", 1, config, result)
    try:
        report = await structured_stage(
            traced,
            "reviewer",
            packet,
            ReviewReport,
            (),
            0,
            lambda review: validate_review(review, student, book),
        )
        return {
            "case_id": case["id"],
            "review": report.model_dump(mode="json"),
            "calls": [c.model_dump(mode="json") for c in result.calls],
            "error": None,
        }
    except (ProviderError, StageContractError) as exc:
        return {
            "case_id": case["id"],
            "review": None,
            "calls": [c.model_dump(mode="json") for c in result.calls],
            "error": str(exc),
        }


def score(cases: list[dict], attempts: list[dict]) -> dict:
    tp = fp = fn = clean = alarms = retained = errors = 0
    for case, attempt in zip(cases, attempts, strict=True):
        gold = {(i["code"], i["question_id"]) for i in case["gold"]}
        review = attempt["review"]
        predicted = (
            {
                (i["code"], i["question_id"])
                for i in review["issues"]
                if i["severity"] in {"major", "critical"}
            }
            if review
            else set()
        )
        tp += len(gold & predicted)
        fp += len(predicted - gold)
        fn += len(gold - predicted)
        errors += review is None
        if not gold:
            clean += 1
            alarms += bool(review and review["decision"] in {"needs_revision", "rejected"})
            retained += bool(review and review["decision"] == "approved")
    return {
        "attempts": len(attempts),
        "errors": errors,
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "recall": tp / (tp + fn) if tp + fn else None,
        "precision": tp / (tp + fp) if tp + fp else None,
        "clean_false_alarm_rate": alarms / clean if clean else None,
        "clean_retention": retained / clean if clean else None,
    }


async def run(dataset_path: Path, output: Path, mode: str):
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    if output.exists():
        raise ValueError("output directory already exists")
    output.mkdir(parents=True)
    attempts = []
    for case in dataset["cases"]:
        payload = PipelineRequest.model_validate({"request": {"matrix": case["matrix"]}})
        if mode == "replay":
            provider = ReplayProvider([json.dumps(case["replay"], ensure_ascii=False)])
            attempts.append(await evaluate_case(case, provider, payload.workflow))
        else:
            async with provider_scope(payload) as providers:
                attempts.append(await evaluate_case(case, providers["reviewer"], payload.workflow))
    report = {
        "mode": mode,
        "scope": dataset["scope"],
        "metrics": score(dataset["cases"], attempts),
        "note": "Replay verifies scoring only; live scores cover synthetic key errors, "
        "not general defect quality or human-grounded evidence precision.",
    }
    (output / "attempts.json").write_text(
        json.dumps(attempts, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output / "metrics.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset", type=Path, default=Path("examples/pipeline/reviewer_suite.json")
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("replay", "live"), default="replay")
    args = parser.parse_args()
    print(
        json.dumps(
            asyncio.run(run(args.dataset, args.output, args.mode)), ensure_ascii=False, indent=2
        )
    )


if __name__ == "__main__":
    main()
