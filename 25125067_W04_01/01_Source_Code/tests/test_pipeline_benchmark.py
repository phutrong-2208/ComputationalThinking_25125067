import asyncio
import json
from pathlib import Path

import pytest

from exam_baseline.pipeline.benchmark import HumanLabel, run, summarize
from exam_baseline.pipeline.bootstrap import ReplayProvider
from exam_baseline.pipeline.contracts import WorkflowConfig
from exam_baseline.pipeline.reviewer_benchmark import evaluate_case, score


def attempt(name, *, passed=False, artifact=False):
    return {
        "attempt_id": name,
        "system": "pipeline",
        "track": "text",
        "requested_questions": 4,
        "status": "completed" if passed else "failed",
        "deterministic_passed": passed,
        "accepted": passed,
        "artifact_returned": artifact,
        "latency_ms": 100 if passed else 300,
        "calls": 3 if passed else 1,
        "known_cost_calls": 0,
        "known_cost_usd": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
        "usage_unknown_calls": 3 if passed else 1,
    }


def test_benchmark_keeps_failed_attempts_and_unknown_quality_cost():
    metrics = summarize([attempt("good", passed=True, artifact=True), attempt("bad")], {})[
        "pipeline/text"
    ]
    assert metrics["matrix_full_pass_rate"] == 0.5
    assert metrics["correct_question_yield"] is None
    assert metrics["useful_figure_rate"] is None
    assert metrics["total_cost_usd"] is None and metrics["cost_coverage"] == 0
    assert metrics["latency_median_ms"] == 200 and metrics["latency_max_ms"] == 300


def test_human_yield_uses_requested_questions_and_failed_attempts_get_zero():
    labels = {
        name: HumanLabel(requested_questions=4, correct_questions=4) for name in ("good", "bad")
    }
    metrics = summarize([attempt("good", passed=True, artifact=True), attempt("bad")], labels)[
        "pipeline/text"
    ]
    assert metrics["correct_question_yield"] == 0.5 and metrics["human_audit_coverage"] == 1


def test_reviewer_metrics_do_not_reward_reject_all():
    labels = {
        "defect": HumanLabel(
            requested_questions=4,
            correct_questions=3,
            gold_defects=1,
            true_positive_defects=1,
            predicted_defects=4,
        ),
        "clean": HumanLabel(
            requested_questions=4,
            correct_questions=4,
            predicted_defects=3,
            clean_case=True,
            false_alarm=True,
        ),
    }
    metrics = summarize(
        [attempt("defect", artifact=True), attempt("clean", artifact=True)], labels
    )["pipeline/text"]
    assert metrics["reviewer_defect_recall"] == 1
    assert metrics["reviewer_issue_precision"] == pytest.approx(1 / 7)
    assert metrics["reviewer_clean_false_alarm_rate"] == 1


def test_bad_annotation_denominator_is_rejected():
    with pytest.raises(ValueError, match="denominator"):
        summarize([attempt("one")], {"one": HumanLabel(requested_questions=3, correct_questions=2)})


def test_ten_case_two_repeat_replay_pilot_runs_both_systems(tmp_path):
    manifest = Path(__file__).parents[1] / "examples/pipeline/pilot.json"
    report = asyncio.run(run(manifest, tmp_path / "pilot", "replay", None))
    assert report["mode"] == "replay" and not report["quality_measured"]
    baseline, pipeline = report["metrics"]["baseline/text"], report["metrics"]["pipeline/text"]
    assert baseline["scheduled_attempts"] == pipeline["scheduled_attempts"] == 20
    assert baseline["matrix_full_pass_rate"] == pipeline["matrix_full_pass_rate"] == 1
    assert baseline["provider_calls"] == 20 and pipeline["provider_calls"] == 80
    assert baseline["correct_question_yield"] is pipeline["correct_question_yield"] is None
    rows = (tmp_path / "pilot/attempts.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 40 and all("attempt_id" in json.loads(row) for row in rows)
    assert (tmp_path / "pilot/manifest.json").is_file()


def test_pre_call_context_failures_have_zero_calls_and_unknown_usage(tmp_path):
    source = Path(__file__).parents[1] / "examples/pipeline/text_01"
    request = json.loads((source / "input.json").read_text(encoding="utf-8"))
    request["request"]["context"] = {"course_materials": ["a" * 30000] * 8}
    (tmp_path / "request.json").write_text(json.dumps(request), encoding="utf-8")
    manifest = {
        "repeats": 1,
        "cases": [
            {"id": "oversized", "track": "text", "request": "request.json", "fixtures": str(source)}
        ],
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    report = asyncio.run(run(tmp_path / "manifest.json", tmp_path / "output", "replay", None))
    for metrics in report["metrics"].values():
        assert metrics["provider_calls"] == metrics["usage_unknown_calls"] == 0
        assert metrics["failures"] == 1


def test_isolated_reviewer_suite_has_ten_clean_and_ten_defects_and_hides_gold():
    path = Path(__file__).parents[1] / "examples/pipeline/reviewer_suite.json"
    dataset = json.loads(path.read_text(encoding="utf-8"))
    assert len(dataset["cases"]) == 20
    assert sum(not case["gold"] for case in dataset["cases"]) == 10

    async def exercise():
        attempts = []
        for case in dataset["cases"]:

            class Inspect(ReplayProvider):
                async def complete(self, request):
                    packet = json.loads(request.user)["input"]
                    assert "gold" not in packet and "replay" not in packet
                    return await super().complete(request)

            provider = Inspect([json.dumps(case["replay"])])
            attempts.append(await evaluate_case(case, provider, WorkflowConfig()))
        return attempts

    metrics = score(dataset["cases"], asyncio.run(exercise()))
    assert metrics["recall"] == metrics["precision"] == metrics["clean_retention"] == 1
    assert metrics["clean_false_alarm_rate"] == 0 and metrics["errors"] == 0


def test_isolated_reviewer_error_is_not_counted_as_success():
    cases = [{"gold": [{"code": "wrong_answer", "question_id": "q1"}]}, {"gold": []}]
    metrics = score(cases, [{"review": None}, {"review": None}])
    assert metrics["recall"] == metrics["clean_retention"] == 0
    assert metrics["errors"] == 2 and metrics["precision"] is None
