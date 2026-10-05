"""Stable question presentation without changing immutable grading content."""
from hashlib import sha256
import hmac
from typing import Sequence


def ordered_choices(choices: Sequence[str], *, session_id: object, question_id: str) -> list[str]:
    """Sample by an opaque server session; GET retries retain the same order."""
    key = sha256(str(session_id).encode("utf-8")).digest()
    return [choice for _, choice in sorted(
        enumerate(choices),
        key=lambda pair: hmac.new(
            key, f"choices-v1:{question_id}:{pair[0]}".encode("utf-8"), sha256,
        ).digest(),
    )]
