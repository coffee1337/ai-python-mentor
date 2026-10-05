"""Embeddings adapter, served by the same private gateway as chat.

The domain never learns a vendor name: it asks for a vector list and validates
the envelope, exactly as it does for Chat Completions. Requests are batched so
one learner turn costs one call, never one call per chunk.
"""
import json
import os
import hashlib
import math
import re
import struct
from dataclasses import dataclass
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, ValidationError

MAX_EMBEDDING_INPUTS = 24
MAX_EMBEDDING_INPUT_CHARS = 4000
MAX_EMBEDDING_DIMENSION = 4096


class EmbeddingError(Exception):
    def __init__(self, status: int, detail: str):
        self.status, self.detail = status, detail


class EmbeddingDatum(BaseModel):
    index: int = Field(ge=0)
    embedding: list[float]


class EmbeddingResponse(BaseModel):
    data: list[EmbeddingDatum] = Field(min_length=1)
    model: str = Field(min_length=1, max_length=120)


@dataclass(frozen=True)
class EmbeddingConfig:
    url: str
    model: str
    key: str
    timeout: float
    dimension: int


def embedding_configuration() -> EmbeddingConfig:
    """Return embeddings config, or raise ``GatewayError`` when unconfigured.

    Chat Completions may be configured while embeddings are not. Callers must
    treat that as a degraded retrieval, never as a failed request.
    """
    from app import ai_gateway

    base = ai_gateway.configuration()
    url = os.getenv("AI_GATEWAY_EMBEDDINGS_URL", "").strip()
    model = os.getenv("AI_GATEWAY_EMBEDDINGS_MODEL", "").strip()
    try:
        parts = urlsplit(url)
        dimension = int(os.getenv("AI_GATEWAY_EMBEDDINGS_DIMENSION", "0"))
    except (TypeError, ValueError):
        raise ai_gateway.GatewayError(503, "AI embeddings are not configured") from None
    valid = (
        parts.scheme == "https"
        and parts.hostname
        and not parts.username
        and not parts.password
        and not parts.query
        and not parts.fragment
        and model
        and 1 <= dimension <= MAX_EMBEDDING_DIMENSION
    )
    if not valid:
        raise ai_gateway.GatewayError(503, "AI embeddings are not configured")
    return EmbeddingConfig(url, model, base.key, base.timeout, dimension)


def embed(config: EmbeddingConfig, inputs: list[str]) -> list[list[float]]:
    """Embed 1..MAX_EMBEDDING_INPUTS short strings. Raises ``EmbeddingsUnavailable``."""
    if not 1 <= len(inputs) <= MAX_EMBEDDING_INPUTS:
        raise ValueError("Invalid embedding batch size")
    if any(not text.strip() or len(text) > MAX_EMBEDDING_INPUT_CHARS for text in inputs):
        raise ValueError("Invalid embedding input")
    try:
        import httpx

        with httpx.Client(timeout=config.timeout, follow_redirects=False, trust_env=False) as client:
            with client.stream(
                "POST",
                config.url,
                headers={"Authorization": f"Bearer {config.key}"},
                json={"model": config.model, "input": inputs},
            ) as response:
                response.raise_for_status()
                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 262144:
                        raise ValueError("Response too large")
            parsed = EmbeddingResponse.model_validate(json.loads(raw))
    except httpx.TimeoutException:
        raise EmbeddingError(504, "AI embeddings timed out") from None
    except (httpx.HTTPError, ValidationError, ValueError, UnicodeError, ImportError):
        # Never surface a provider body: it may echo the submitted text.
        raise EmbeddingError(502, "AI embeddings are temporarily unavailable") from None

    if len(parsed.data) != len(inputs):
        raise EmbeddingError(502, "AI embeddings are temporarily unavailable")
    by_index: dict[int, list[float]] = {}
    for datum in parsed.data:
        vector = [value for value in datum.embedding if isinstance(value, (int, float))]
        if len(vector) != len(datum.embedding) or not vector:
            raise EmbeddingError(502, "AI embeddings are temporarily unavailable")
        if any(not math.isfinite(value) for value in vector) or len(vector) != config.dimension:
            raise EmbeddingError(502, "AI embeddings are temporarily unavailable")
        if datum.index in by_index:
            raise EmbeddingError(502, "AI embeddings are temporarily unavailable")
        by_index[datum.index] = vector
    if sorted(by_index) != list(range(len(inputs))):
        raise EmbeddingError(502, "AI embeddings are temporarily unavailable")
    return [by_index[index] for index in range(len(inputs))]


def pack(vector: list[float]) -> bytes:
    return struct.pack(f"<{len(vector)}f", *vector)


def unpack(blob: bytes, dimension: int) -> list[float]:
    if len(blob) != dimension * 4:
        raise ValueError("Stored embedding does not match its dimension")
    return list(struct.unpack(f"<{dimension}f", blob))


LOCAL_EMBEDDING_MODEL = "local-hash-v1"
LOCAL_EMBEDDING_DIMENSION = 256


def local_embedding(text: str) -> list[float]:
    """Stable, private token hashing fallback; no provider call or paid usage."""
    vector = [0.0] * LOCAL_EMBEDDING_DIMENSION
    for token in re.findall(r"[\w]+", text.lower())[:4000]:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        vector[int.from_bytes(digest[:2], "big") % len(vector)] += 1.0
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector] if norm else vector
