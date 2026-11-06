"""JSON-only context preparation; a retrieval-backed loader can replace this later."""

import unicodedata
from collections import Counter

from .contracts import AgentInput
from .models import GenerationRequest


def normalized_text(text: str) -> str:
    """Conservative lexical comparison, not semantic duplicate detection."""
    # Preserve operators: 'x+1' and 'x-1' must never collapse to the same stem.
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split()).rstrip(".?!")


class JsonContextLoader:
    def prepare(self, request: GenerationRequest) -> AgentInput:
        # Models already trim boundaries and reject invalid IDs/fields. Preserve mathematical
        # notation, case, and provenance; do not silently deduplicate or truncate the bank.
        counts = Counter(normalized_text(q.stem) for q in request.question_bank.questions)
        warnings = []
        if any(n > 1 for n in counts.values()):
            warnings.append(
                "Question bank contains lexically duplicate stems; all IDs are retained."
            )
        topics = {t.id for t in request.matrix.topics}
        if any(q.topic_id not in topics for q in request.question_bank.questions):
            warnings.append("Some bank questions are outside the matrix topics; do not reuse them.")
        return AgentInput(request=request.model_copy(deep=True), warnings=tuple(warnings))
