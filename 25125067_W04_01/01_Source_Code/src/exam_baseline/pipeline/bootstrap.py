"""Composition root: replace a role's model/provider without changing orchestration."""

import json
from contextlib import asynccontextmanager
from pathlib import Path

import httpx

from ..config import Settings
from ..contracts import Completion, ProviderError
from ..providers.chat_completions import ChatCompletionsProvider
from .contracts import PipelineRequest, StageConfig


class ReplayProvider:
    """Sequential, frozen stage responses for reproducible offline integration tests."""

    name = "replay"
    model = "fixture-not-a-live-model"
    parameters = {}
    supports_images = True

    def __init__(self, responses: list[str]):
        self.responses = iter(responses)

    async def complete(self, request):
        try:
            text = next(self.responses)
        except StopIteration as exc:
            raise ProviderError(
                "fixture_exhausted", "No replay response remains for this role."
            ) from exc
        data = json.loads(text)
        # Fixture-only identity binding accommodates platform-dependent PNG hashes.
        if isinstance(data, dict) and any(value == "__CURRENT__" for value in data.values()):
            view = json.loads(request.user)["input"]
            if data.get("solution_sha256") == "__CURRENT__":
                data["solution_sha256"] = view["solution_sha256"]
            view = view.get("student_view", view)
            for key in ("exam_id", "draft_id", "revision", "artifact_sha256"):
                if data.get(key) == "__CURRENT__":
                    data[key] = view[key]
            for drawing in data.get("drawings", []):
                if drawing.get("spec_sha256") == "__CURRENT__":
                    drawing["spec_sha256"] = next(
                        spec["spec_sha256"]
                        for spec in view["visual_specs"]
                        if spec["visual_id"] == drawing["visual_id"]
                    )
            text = json.dumps(data, ensure_ascii=False)
        return Completion(text=text, model=self.model)


def replay_providers(folder: Path) -> dict:
    providers = {}
    for role in ("composer", "illustrator", "solver", "reviewer"):
        files = sorted(folder.glob(f"{role}_*.json"))
        if not files:
            raise ValueError(f"missing {role}_NN.json fixtures in {folder}")
        # Confirm files are JSON, but preserve exact text for trace fingerprints.
        responses = [path.read_text(encoding="utf-8") for path in files]
        for response in responses:
            json.loads(response)
        providers[role] = ReplayProvider(responses)
    return providers


@asynccontextmanager
async def provider_scope(payload: PipelineRequest, settings: Settings | None = None):
    settings = settings if settings is not None else Settings()
    if settings.provider != "chat_completions":
        raise ValueError("pipeline live mode requires EXAM_PROVIDER=chat_completions")
    async with httpx.AsyncClient(follow_redirects=False) as client:
        providers = {}
        for role in ("composer", "illustrator", "solver", "reviewer"):
            configured = stage_settings(settings, getattr(payload.workflow, role))
            providers[role] = ChatCompletionsProvider(configured, client)
        yield providers


def stage_settings(settings: Settings, options: StageConfig) -> Settings:
    values = settings.model_dump()
    for name in (
        "model",
        "supports_images",
        "max_output_tokens",
        "input_price_per_million",
        "output_price_per_million",
    ):
        value = getattr(options, name)
        if value is not None:
            values[name] = value
    return Settings(_env_file=None, **values)
