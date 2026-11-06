"""Environment configuration. Secrets never enter evaluation records."""

from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="EXAM_",
        env_file=".env",
        extra="ignore",
        hide_input_in_errors=True,
    )

    provider: Literal["mock", "chat_completions"] = "mock"
    model: str = Field(default="mock-fixture-v1", min_length=1)
    prompt_version: Literal["v1"] = "v1"
    api_key: SecretStr | None = None
    base_url: str = "https://api.openai.com/v1"
    timeout_seconds: float = Field(default=90, gt=0, allow_inf_nan=False)
    max_output_tokens: int = Field(default=8192, gt=0)
    token_limit_field: Literal["max_completion_tokens", "max_tokens"] = "max_completion_tokens"
    response_format: Literal["json_object", "text"] = "json_object"
    temperature: float | None = Field(default=None, ge=0, le=2, allow_inf_nan=False)
    seed: int | None = None
    max_prompt_chars: int = Field(default=200000, gt=0)
    supports_images: bool = False
    input_price_per_million: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    output_price_per_million: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    evaluation_jsonl: Path | None = None

    @classmethod
    def for_offline(cls) -> "Settings":
        """Validate defaults explicitly, ignoring .env and EXAM_* environment overrides."""
        defaults = {name: field.get_default() for name, field in cls.model_fields.items()}
        return cls(_env_file=None, **defaults)

    @model_validator(mode="after")
    def complete_configuration(self):
        if self.provider == "chat_completions":
            if not self.api_key or not self.api_key.get_secret_value().strip():
                raise ValueError("EXAM_API_KEY is required for chat_completions")
            if self.model == "mock-fixture-v1":
                raise ValueError("set EXAM_MODEL for the real provider")
            url = urlsplit(self.base_url)
            if url.scheme not in {"http", "https"} or not url.hostname:
                raise ValueError("EXAM_BASE_URL must be an HTTP(S) URL")
            if url.username or url.password or url.query or url.fragment:
                raise ValueError("EXAM_BASE_URL must not contain credentials, query, or fragment")
        if (self.input_price_per_million is None) != (self.output_price_per_million is None):
            raise ValueError("configure both input and output token prices, or neither")
        return self
