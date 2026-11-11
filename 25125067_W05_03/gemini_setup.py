"""Shared Gemini credentials for the course notebooks and LangGraph entrypoints."""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent


def load_environment(*, require_api_key: bool = False) -> None:
    """Load local settings without replacing credentials already in the process.

    GEMINI_ENV_FILE can point to an existing .env outside this submission. The
    original langchain-academy .env is a fallback for the current course setup.
    No credentials are copied into notebooks or printed.
    """
    explicit_path = os.getenv("GEMINI_ENV_FILE")
    if explicit_path:
        env_path = Path(explicit_path).expanduser()
        if not env_path.is_file():
            raise FileNotFoundError(f"GEMINI_ENV_FILE does not exist: {env_path}")
        load_dotenv(env_path, override=False)

    cwd = Path.cwd().resolve()
    for directory in (cwd, *cwd.parents):
        if directory == PROJECT_ROOT or PROJECT_ROOT in directory.parents:
            load_dotenv(directory / ".env", override=False)
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    load_dotenv(Path.home() / "langchain-academy" / ".env", override=False)

    if not os.getenv("GOOGLE_API_KEY") and os.getenv("GEMINI_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "false")

    # Tracing is optional; a Gemini key is sufficient for the model examples.
    if not (os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY")):
        os.environ["LANGSMITH_TRACING"] = "false"
        os.environ["LANGSMITH_TRACING_V2"] = "false"
        os.environ["LANGCHAIN_TRACING_V2"] = "false"

    if require_api_key and not os.getenv("GOOGLE_API_KEY"):
        raise RuntimeError(
            "Set GOOGLE_API_KEY (or GEMINI_API_KEY) in .env, or set "
            "GEMINI_ENV_FILE to your existing .env before running the notebook."
        )
