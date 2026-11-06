"""Generate offline or through a running API, then save JSON and a readable report."""

import argparse
import asyncio
import json
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from pydantic import ValidationError

from .bootstrap import build_service
from .config import Settings
from .http_status import response_status
from .models import GenerationRequest
from .providers.mock import MockProvider
from .reporting import render_readable_report
from .samples import sample_request


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--offline", dest="mode", action="store_const", const="offline")
    mode.add_argument("--live", dest="mode", action="store_const", const="live")
    parser.set_defaults(mode="offline")
    parser.add_argument("--request", type=Path, help="JSON input; defaults to the packaged example")
    parser.add_argument("--output-dir", type=Path, help="New directory; existing paths are refused")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=180, help="Client timeout in seconds")
    parser.add_argument("--export-example", type=Path, help="Write example JSON and exit")
    return parser


async def _offline(payload: Any) -> tuple[int, dict[str, Any]]:
    try:
        request = GenerationRequest.model_validate(payload)
    except ValidationError as exc:
        return 422, {
            "detail": exc.errors(
                include_input=False,
                include_context=False,
                include_url=False,
            )
        }
    service = build_service(Settings.for_offline(), MockProvider())
    response = await service.generate(request)
    return response_status(response), response.model_dump(mode="json")


def _live(payload: Any, base_url: str, timeout: float) -> tuple[int, dict[str, Any]]:
    try:
        response = httpx.post(
            base_url.rstrip("/") + "/v1/exams/generate",
            json=payload,
            timeout=timeout,
            trust_env=False,
        )
    except httpx.TransportError as exc:
        return 0, {
            "status": "client_failure",
            "error": {
                "code": "local_api_timeout"
                if isinstance(exc, httpx.TimeoutException)
                else "local_api_unreachable",
                "message": "Check that the local server is running. A timed-out generation may "
                "still finish; check the server before submitting again.",
            },
        }
    try:
        result = response.json()
        if not isinstance(result, dict):
            raise ValueError("response must be an object")
    except ValueError:
        result = {
            "status": "client_failure",
            "error": {
                "code": "invalid_api_response",
                "message": "API did not return a JSON object.",
            },
        }
    return response.status_code, result


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.export_example:
        if args.request or args.mode == "live" or args.output_dir:
            parser.error("--export-example cannot be combined with generation options")
        try:
            args.export_example.parent.mkdir(parents=True, exist_ok=True)
            # Never overwrite local inputs or a secret file by accident.
            with args.export_example.open("x", encoding="utf-8") as stream:
                stream.write(sample_request().model_dump_json(indent=2) + "\n")
        except OSError as exc:
            print(f"Cannot export example ({type(exc).__name__}); use a new file path.")
            return 2
        print(f"Example saved: {args.export_example.resolve()}")
        return 0

    url = urlsplit(args.base_url)
    if (
        url.scheme not in {"http", "https"}
        or not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
        or url.path not in {"", "/"}
    ):
        parser.error("--base-url must be an HTTP(S) origin without credentials or path")
    if not 0 < args.timeout < float("inf"):
        parser.error("--timeout must be a finite positive number")
    try:
        payload = (
            json.loads(args.request.read_text(encoding="utf-8-sig"))
            if args.request
            else (sample_request().model_dump(mode="json"))
        )
    except (OSError, ValueError) as exc:
        print(f"Cannot read request JSON ({type(exc).__name__}).")
        return 2

    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    output = (args.output_dir or Path("runs") / args.mode / f"{stamp}-{uuid4().hex[:8]}").resolve()
    try:
        # Fail before generation if an existing run would be overwritten.
        output.mkdir(parents=True, exist_ok=False)
        _write_json(output / "request.json", payload)
    except OSError as exc:
        print(f"Cannot create output ({type(exc).__name__}); use a new directory.")
        return 2
    status, result = (
        asyncio.run(_offline(payload))
        if args.mode == "offline"
        else _live(
            payload,
            args.base_url,
            args.timeout,
        )
    )
    try:
        _write_json(output / "response.json", result)
        (output / "ket_qua.md").write_text(render_readable_report(result, status), encoding="utf-8")
    except OSError as exc:
        print(f"Cannot save result ({type(exc).__name__}). Generation was already attempted.")
        return 2
    print(f"Mode: {args.mode}; HTTP: {status}; status: {result.get('status', 'request_failure')}")
    print(f"Readable report: {output / 'ket_qua.md'}")
    print(f"Full JSON: {output / 'response.json'}")
    if result.get("status") == "client_failure":
        return 2
    return 0 if 200 <= status < 300 and result.get("status") == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
