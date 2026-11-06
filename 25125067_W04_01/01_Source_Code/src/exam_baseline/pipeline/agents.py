"""Four explicit agent roles. Only Orchestrator controls communication and repetition."""

from ..mini import create_draft
from .contracts import IllustrationBook, ReviewReport, SolutionBook
from .stages import structured_stage, validate_review, validate_solutions
from .views import illustration_view, validate_illustrations


class ComposerAgent:
    async def run(self, payload, provider, root, revision, feedback=None):
        return await create_draft(
            payload,
            provider,
            root,
            revision=revision,
            repair_feedback=feedback,
            render_figures=False,
        )


class IllustratorAgent:
    async def run(self, draft, provider, schema_repairs=1):
        return await structured_stage(
            provider,
            "illustrator",
            illustration_view(draft),
            IllustrationBook,
            (),
            schema_repairs,
            lambda book: validate_illustrations(book, draft),
        )


class SolverAgent:
    async def run(self, student, provider, schema_repairs=1):
        return await structured_stage(
            provider,
            "solver",
            student,
            SolutionBook,
            (),
            schema_repairs,
            lambda book: validate_solutions(book, student),
        )


class ReviewerAgent:
    async def run(self, packet, provider, student, book):
        # Physical call count is one, including malformed responses: no Reviewer retry.
        return await structured_stage(
            provider,
            "reviewer",
            packet,
            ReviewReport,
            (),
            0,
            lambda report: validate_review(report, student, book),
        )
