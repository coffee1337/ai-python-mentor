"""Server-only, opt-in Chat Completions adapter. No retries or vendor defaults."""
import json
import os
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, Field, ValidationError


class GatewayError(Exception):
    def __init__(self, status: int, detail: str):
        self.status, self.detail = status, detail


class ProviderMessage(BaseModel):
    role: str
    content: str = Field(min_length=1, max_length=12000)


class Choice(BaseModel):
    message: ProviderMessage
    finish_reason: str


class ProviderResponse(BaseModel):
    choices: list[Choice] = Field(min_length=1, max_length=1)
    usage: dict | None = None


@dataclass(frozen=True)
class GatewayConfig:
    url: str
    model: str
    key: str
    timeout: float


def configuration(*, model_override: str | None = None) -> GatewayConfig:
    url = os.getenv("AI_GATEWAY_URL", "").strip()
    model = os.getenv("AI_GATEWAY_MODEL", "").strip()
    key = os.getenv("AI_GATEWAY_API_KEY", "").strip()
    try:
        parts = urlsplit(url)
        timeout = float(os.getenv("AI_GATEWAY_TIMEOUT_SECONDS", "20"))
        model = model_override.strip() if model_override else model
        valid = (parts.scheme == "https" and parts.hostname and not parts.username
                 and not parts.password and not parts.query and not parts.fragment
                 and model and key and 1 <= timeout <= 60)
    except ValueError:
        valid = False
    if not valid:
        raise GatewayError(503, "AI mentor is not configured")
    return GatewayConfig(url, model, key, timeout)


def generate(config: GatewayConfig, messages: list[dict[str, str]]) -> str:
    content, _ = generate_with_usage(config, messages)
    return content


def generate_with_usage(
    config: GatewayConfig,
    messages: list[dict[str, str]],
    *,
    max_completion_tokens: int = 2200,
) -> tuple[str, dict | None]:
    """One HTTP call. Validate the envelope; never expose provider error bodies."""
    if not 1 <= max_completion_tokens <= 3000:
        raise ValueError("Invalid completion-token budget")
    try:
        with httpx.Client(timeout=config.timeout, follow_redirects=False, trust_env=False) as client:
            with client.stream(
                "POST", config.url,
                headers={"Authorization": f"Bearer {config.key}"},
                json={"model": config.model, "messages": messages, "max_completion_tokens": max_completion_tokens},
            ) as response:
                response.raise_for_status()
                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 65536:
                        raise ValueError("Response too large")
                parsed = ProviderResponse.model_validate(json.loads(raw))
        choice = parsed.choices[0]
        if choice.message.role != "assistant" or choice.finish_reason != "stop" or not choice.message.content.strip():
            raise ValueError("Incomplete response")
        return choice.message.content.strip(), parsed.usage
    except httpx.TimeoutException:
        raise GatewayError(504, "AI mentor timed out; retry later") from None
    except (httpx.HTTPError, ValidationError, ValueError, UnicodeError):
        raise GatewayError(502, "AI mentor is temporarily unavailable") from None
