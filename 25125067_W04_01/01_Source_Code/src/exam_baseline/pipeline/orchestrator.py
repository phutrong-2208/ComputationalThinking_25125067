"""Four-agent workflow with exactly one possible Reviewer-to-Composer callback."""

import asyncio
import json
import shutil
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from ..contracts import LLMProvider, ProviderError
from ..mini import ComposerOutput, MiniRequest, StageResult, digest, validate_output
from .agents import ComposerAgent, IllustratorAgent, ReviewerAgent, SolverAgent
from .contracts import PipelineError, PipelineRequest, PipelineResult, WorkflowEvent
from .latex import compile_document, format_errors, prose, render_document, validate_template
from .runtime import TracedProvider
from .stages import StageContractError, validate_review, validate_solutions
from .views import reviewer_view, student_view, validate_illustrations


class PipelineFailure(Exception):
    def __init__(self, stage: str, code: str, message: str):
        super().__init__(message)
        self.stage, self.code = stage, code


class Orchestrator:
    def __init__(self, providers: dict[str, LLMProvider]):
        self.providers = providers
        self.agents = {
            "composer": ComposerAgent(),
            "illustrator": IllustratorAgent(),
            "solver": SolverAgent(),
            "reviewer": ReviewerAgent(),
        }

    async def run(
        self, payload: PipelineRequest, output: Path, *, compile_latex: bool = False
    ) -> PipelineResult:
        payload = PipelineRequest.model_validate(payload.model_dump())
        if output.exists():
            raise ValueError("output directory already exists")
        validate_template(payload.latex_template)
        for text in (
            payload.request.matrix.title,
            payload.request.matrix.subject,
            *(topic.name for topic in payload.request.matrix.topics),
        ):
            prose(text)
        if payload.request.matrix.question_count > payload.workflow.max_questions:
            raise ValueError("question count exceeds workflow limit")
        if len(payload.required_visual_question_ids) > payload.workflow.max_figures:
            raise ValueError("required figures exceed workflow limit")
        if payload.require_evidence and not any(
            e.role == "content_support" for e in payload.evidence
        ):
            raise ValueError("content-support evidence is required")
        missing = set(self.agents) - self.providers.keys()
        if missing:
            raise ValueError("missing providers: " + ", ".join(sorted(missing)))
        output.mkdir(parents=True, exist_ok=False)
        internal = output / "_internal"
        internal.mkdir()
        (internal / "request.json").write_text(payload.model_dump_json(indent=2), encoding="utf-8")
        result, start = PipelineResult(run_id=str(uuid4())), perf_counter()
        try:
            await asyncio.wait_for(
                self._execute(payload, output, result, compile_latex),
                payload.workflow.run_timeout_seconds,
            )
        except asyncio.TimeoutError:
            self._error(result, "orchestrator", "run_timeout", "Workflow deadline exceeded.")
        except PipelineFailure as exc:
            self._error(result, exc.stage, exc.code, str(exc))
        except ProviderError as exc:
            self._error(result, getattr(exc, "stage", "orchestrator"), exc.code, str(exc))
        except StageContractError as exc:
            self._error(result, exc.stage, "stage_contract", str(exc))
        except (OSError, ValueError) as exc:
            self._error(result, "finalizer", "artifact_error", str(exc))
        result.total_latency_ms = (perf_counter() - start) * 1000
        self._write(internal / "pipeline_result.json", result)
        return result

    async def _execute(self, payload, output, result, compile_latex):
        mini = MiniRequest.model_validate(
            {name: getattr(payload, name) for name in MiniRequest.model_fields}
        )
        feedback = None
        # Two fixed passes, never an until-approved loop. Reviewer exists only in pass 1.
        for revision in (1, 2):
            result.revision = revision
            result.deterministic_passed = False
            root = output / "_internal" / "drafts" / f"r{revision}"
            draft = await self._compose(mini, payload, root, result, feedback)
            self._event(result, "composer", "succeeded", "Question draft generated.")
            book = await self.agents["illustrator"].run(
                draft,
                self._provider("illustrator", payload, result, root),
                payload.workflow.max_schema_repairs,
            )
            self._write(root / "illustrations.json", book)
            illustrator_calls = [
                c for c in result.calls if c.stage == "illustrator" and c.revision == revision
            ]
            draft.illustrator = StageResult(
                status="succeeded",
                calls=len(illustrator_calls),
                reason="Illustrator Agent generated native TikZ/PGFPlots code.",
                latency_ms=sum(c.latency_ms for c in illustrator_calls),
                usage=illustrator_calls[-1].usage,
            )
            self._write(root / "exam_draft.json", draft)
            self._event(result, "illustrator", "succeeded", "Native TikZ/PGFPlots code generated.")
            self._checks(draft, mini, book)
            source = render_document(
                draft,
                root,
                payload.latex_template,
                {t.id: t.name for t in mini.request.matrix.topics},
                book,
            )
            (root / "merged.tex").write_text(source, encoding="utf-8")
            self._event(result, "merger", "succeeded", "Composer text + Illustrator code merged.")
            student, _ = student_view(draft, root, book, source)
            result.deterministic_passed = True
            solver_packet = dict(student)
            if revision == 2:
                solver_packet["correction"] = {
                    "instruction": "Independently re-solve the revised student exam and verify "
                    "arithmetic, units and native drawing source. No prior key is supplied."
                }
            solutions = await self.agents["solver"].run(
                solver_packet,
                self._provider("solver", payload, result, root),
                payload.workflow.max_schema_repairs,
            )
            result.solutions = solutions
            self._write(root / "solution_book.json", solutions)
            self._event(
                result, "solver", "succeeded", "Independent source/math verification completed."
            )
            if revision == 1:
                review = await self.agents["reviewer"].run(
                    reviewer_view(student, solutions, payload),
                    self._provider("reviewer", payload, result, root),
                    student,
                    solutions,
                )
                result.review = review
                self._write(root / "review_report.json", review)
                self._event(result, "reviewer", "succeeded", review.decision)
                needs_feedback = review.decision != "approved" or any(
                    i.severity != "info" for i in review.issues
                )
                if needs_feedback:
                    result.repairs = 1
                    result.reviewer_feedback_sent = True
                    feedback = {
                        "review": review.model_dump(mode="json"),
                        "previous_output": {
                            "exam": draft.exam.model_dump(mode="json"),
                            "questions": [q.model_dump(mode="json") for q in draft.questions],
                            "visuals": [v.model_dump(mode="json") for v in draft.visuals],
                        },
                        "instruction": "This is the ONLY Reviewer feedback. Correct the "
                        "identified defects, preserve matrix and question IDs. "
                        "The user performs final visual inspection.",
                    }
                    self._event(result, "composer", "repair", "Reviewer feedback delivered once.")
                    continue
                result.machine_approved = True
                result.review_covers_final_revision = True
            # Revision 2 goes directly to human handoff: no second Reviewer call or feedback.
            self._checks(draft, mini, book)
            current, _ = student_view(draft, root, book, source)
            if current != student:
                raise PipelineFailure("finalizer", "stale_artifact", "Merged source changed.")
            validate_solutions(solutions, current)
            if result.review_covers_final_revision:
                validate_review(result.review, current, solutions)
            candidate = output / "_internal" / "de_thi.tex"
            candidate.write_text(source, encoding="utf-8")
            result.latex_validation = "static"
            if compile_latex:
                compile_document(candidate)
                result.latex_validation = "compiled"
            final = output / "de_thi.tex"
            shutil.copyfile(candidate, final)
            result.final_latex, result.latex_sha256 = str(final), digest(final.read_bytes())
            result.quality_decision = "pending_human_review"
            result.execution_status = "completed"
            note = (
                "# Cần người dùng kiểm tra bằng mắt\n\n"
                f"Đề hiện tại: revision {revision}. Reviewer kiểm tra revision 1 đúng một lượt.\n"
                f"Đã gửi phản hồi về Composer: {result.reviewer_feedback_sent}.\n"
                "Không có Reviewer lượt hai. Kiểm tra công thức, hình render, dữ kiện và đáp án "
                "trong solution_book trước khi sử dụng. Máy kiểm source LaTeX, chưa xác nhận "
                "bố cục PDF bằng vision.\n\n"
            )
            for issue in result.review.issues:
                note += f"- {issue.question_id or 'Toàn đề'}: {issue.message}\n"
            for entry in solutions.entries:
                if entry.solvability != "solvable":
                    note += f"- Solver: {entry.question_id}: {entry.solvability}.\n"
            (output / "_internal" / "human_review.md").write_text(note, encoding="utf-8")
            self._event(result, "human_handoff", "succeeded", "Awaiting user visual inspection.")
            return

    async def _compose(self, mini, payload, root, result, feedback):
        # An initial schema correction is permitted; the Reviewer callback itself gets
        # exactly ONE Composer call. Failure never triggers another feedback cycle.
        attempts = 1 if feedback is not None else payload.workflow.max_schema_repairs + 1
        for attempt in range(attempts):
            produced = await self.agents["composer"].run(
                mini,
                self._provider("composer", payload, result, root),
                root,
                result.revision,
                feedback,
            )
            errors = (
                [e.model_dump() for e in produced.errors]
                if isinstance(produced, StageResult)
                else format_errors(produced)
            )
            if not errors:
                return produced
            code = errors[0]["code"]
            if result.calls:
                result.calls[-1].error_code = code
            if (
                isinstance(produced, StageResult)
                and (
                    not produced.calls
                    or code.startswith("provider_")
                    or code
                    in {
                        "call_budget_exceeded",
                        "token_budget_exceeded",
                        "context_too_large",
                        "stage_timeout",
                        "figure_budget",
                        "fixture_exhausted",
                    }
                )
            ) or attempt == attempts - 1:
                raise PipelineFailure(
                    "composer", code, "Composer failed: " + errors[0].get("message", code)
                )
            feedback = {"contract_errors": errors}
            try:
                previous = json.loads(
                    (root / "composer_last_response.json").read_text(encoding="utf-8")
                )
                if isinstance(previous, dict) and "exam" in previous:
                    feedback["previous_output"] = previous
            except (OSError, ValueError):
                pass
            self._event(result, "composer", "repair", "Initial schema/format correction.")
        raise AssertionError("unreachable")

    def _provider(self, role, payload, result, root):
        return TracedProvider(
            self.providers[role],
            role,
            result.revision,
            payload.workflow,
            result,
            root / "responses",
        )

    @staticmethod
    def _checks(draft, mini, book):
        checks = mini.model_copy(deep=True)
        checks.request.include_answers = checks.request.include_solutions = False
        for q in checks.request.question_bank.questions:
            q.answer = q.solution = None
        errors = validate_output(
            ComposerOutput(exam=draft.exam, questions=draft.questions, visuals=draft.visuals),
            checks,
            draft.revision,
        )
        if errors or format_errors(draft):
            raise PipelineFailure("finalizer", "final_validation", "Draft failed final checks.")
        validate_illustrations(book, draft)

    @staticmethod
    def _event(result, stage, status, detail):
        result.events.append(
            WorkflowEvent(stage=stage, revision=result.revision, status=status, detail=detail)
        )

    @staticmethod
    def _error(result, stage, code, message):
        if code in {"final_validation", "stale_artifact", "artifact_error"}:
            result.deterministic_passed = False
        result.errors.append(PipelineError(stage=stage, code=code, message=message))
        Orchestrator._event(result, stage, "failed", code)

    @staticmethod
    def _write(path, model):
        path.write_text(model.model_dump_json(indent=2), encoding="utf-8")
