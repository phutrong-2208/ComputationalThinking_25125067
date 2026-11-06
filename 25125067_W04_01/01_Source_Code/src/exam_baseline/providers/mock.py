import json
from importlib.resources import files
from typing import Any

from ..contracts import Completion, CompletionRequest
from ..models import GeneratedExam


class MockProvider:
    """Static fixture, deliberately NOT a second exam-generation algorithm."""

    name = "mock"

    def __init__(self, model: str = "mock-fixture-v1"):
        self.model = model
        self.parameters: dict[str, Any] = {"fixture": "algebra-v1"}
        self._exam = GeneratedExam.model_validate_json(
            files("exam_baseline.fixtures").joinpath("mock_exam.json").read_text("utf-8")
        )

    async def complete(self, request: CompletionRequest) -> Completion:
        # Honor output visibility so offline demos also exercise the student-only path.
        exam = self._exam.model_copy(deep=True)
        preferences = json.loads(request.user)["request"]
        for question in exam.questions:
            if not preferences["include_answers"]:
                question.answer = None
            if not preferences["include_solutions"]:
                question.solution = None
        return Completion(
            text=exam.model_dump_json(),
            model=self.model,
            response_id="offline-fixture",
        )
