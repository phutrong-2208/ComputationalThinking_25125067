"""HTTP status translation shared by REST and offline CLI reports."""

from .models import GenerationResponse


def response_status(response: GenerationResponse) -> int:
    if response.status == "provider_failure":
        return 504 if response.error and response.error.code == "provider_timeout" else 503
    return {"schema_failure": 502, "context_failure": 413}.get(response.status, 200)
