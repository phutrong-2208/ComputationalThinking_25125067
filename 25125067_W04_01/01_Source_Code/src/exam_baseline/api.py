"""REST routes and dependency wiring. No external requests during import or app creation."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import Body, Depends, FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import ValidationError

from . import __version__
from .bootstrap import service_scope
from .config import Settings
from .contracts import LLMProvider
from .http_status import response_status
from .models import GenerationRequest, GenerationResponse
from .pipeline.bootstrap import provider_scope
from .pipeline.contracts import PipelineRequest
from .pipeline.orchestrator import Orchestrator, PipelineFailure
from .samples import sample_request
from .service import GenerationService


def get_service(request: Request) -> GenerationService:
    return request.app.state.service


def create_app(
    settings: Settings | None = None,
    *,
    provider: LLMProvider | None = None,
    service: GenerationService | None = None,
    pipeline_providers: dict[str, LLMProvider] | None = None,
    pipeline_output_root: Path | None = None,
) -> FastAPI:
    settings = settings if settings is not None else Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if service is not None:
            app.state.service = service
            yield
        else:
            async with service_scope(settings, provider) as current:
                app.state.service = current
                yield

    app = FastAPI(
        title="ASTRA Exam Generation",
        version=__version__,
        lifespan=lifespan,
        description="V1: JSON baseline. V2: four agents, one feedback, human visual review.",
    )
    example = {
        "algebra": {
            "summary": "Valid four-question algebra example",
            "value": sample_request().model_dump(mode="json"),
        }
    }

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse("/docs")

    @app.get("/health")
    def health(current: Annotated[GenerationService, Depends(get_service)]) -> dict[str, str]:
        metadata = current.agent.metadata
        return {"status": "ok", "provider": metadata.provider, "model": metadata.requested_model}

    @app.post(
        "/v1/exams/generate",
        response_model=GenerationResponse,
        responses={code: {"model": GenerationResponse} for code in (413, 502, 503, 504)},
    )
    async def generate(
        payload: Annotated[GenerationRequest, Body(openapi_examples=example)],
        current: Annotated[GenerationService, Depends(get_service)],
    ) -> JSONResponse:
        result = await current.generate(payload)
        return JSONResponse(
            status_code=response_status(result),
            content=result.model_dump(mode="json"),
        )

    @app.post(
        "/v2/exams/generate",
        response_class=Response,
        responses={
            200: {
                "content": {"application/x-tex": {}},
                "description": "Native LaTeX exam awaiting user visual inspection",
            }
        },
    )
    async def generate_pipeline(
        payload: Annotated[
            PipelineRequest,
            Body(
                openapi_examples={
                    "algebra": {
                        "summary": "Four agents and one feedback before human review",
                        "value": {"request": sample_request().model_dump(mode="json")},
                    }
                }
            ),
        ],
    ) -> Response:
        output = (pipeline_output_root or Path("runs/pipeline")) / str(uuid4())
        try:
            if pipeline_providers is not None:
                result = await Orchestrator(pipeline_providers).run(payload, output)
            else:
                async with provider_scope(payload, settings) as providers:
                    result = await Orchestrator(providers).run(payload, output)
        except ValidationError:
            return JSONResponse(status_code=422, content={"error": "invalid_configuration"})
        except (ValueError, PipelineFailure) as exc:
            return JSONResponse(status_code=422, content={"error": str(exc)})
        if result.final_latex:
            return Response(
                Path(result.final_latex).read_bytes(),
                media_type="application/x-tex",
                headers={
                    "Content-Disposition": 'attachment; filename="de_thi.tex"',
                    "X-Run-ID": result.run_id,
                    "X-LaTeX-Validation": result.latex_validation,
                    "X-Human-Review-Required": "true",
                    "X-Reviewer-Feedback-Sent": str(result.reviewer_feedback_sent).lower(),
                },
            )
        code = (
            504
            if any("timeout" in e.code for e in result.errors)
            else 502
            if result.execution_status == "failed"
            else 409
        )
        return JSONResponse(status_code=code, content=result.model_dump(mode="json"))

    return app


def configure_logging() -> None:
    logger = logging.getLogger("exam_baseline.evaluation")
    if not logger.handlers:
        logger.addHandler(logging.StreamHandler())
    logger.setLevel(logging.INFO)
    logger.propagate = False
