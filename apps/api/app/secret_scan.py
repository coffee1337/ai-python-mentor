"""Secret scanning for anything the learner sends us.

A paste with a live key must not travel further: not into logs, not into an AI
request, not into a stored review. Detection is pattern-based and deliberately
conservative — a false positive costs a warning, a false negative leaks a key.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

REDACTED = "[REDACTED-SECRET]"

PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b")),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("telegram_bot_token", re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{30,}\b")),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("dotenv_secret", re.compile(r"(?im)^\s*[A-Z0-9_]*(?:PASSWORD|SECRET|TOKEN|API_KEY|PRIVATE_KEY)[A-Z0-9_]*\s*=\s*\S{8,}")),
    ("connection_string", re.compile(r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis)://[^\s:@]+:[^\s:@]{6,}@")),
)


@dataclass(frozen=True)
class Finding:
    kind: str
    line: int
    excerpt: str


@dataclass(frozen=True)
class ScanResult:
    findings: list[Finding]

    @property
    def clean(self) -> bool:
        return not self.findings

    def kinds(self) -> list[str]:
        return sorted({finding.kind for finding in self.findings})

    def guidance(self) -> str | None:
        if self.clean:
            return None
        names = ", ".join(self.kinds())
        return (
            f"В отправленном фрагменте похоже на секрет ({names}). "
            "Секрет не сохранён и не отправлен наставнику. Отзовите ключ у провайдера "
            "и выпустите новый; в коде держите только переменные окружения."
        )


def scan(text: str, *, max_findings: int = 5) -> ScanResult:
    """Find secret-shaped strings, with a short masked excerpt for each."""
    if not text:
        return ScanResult([])
    findings: list[Finding] = []
    for number, line in enumerate(text.splitlines(), start=1):
        for kind, pattern in PATTERNS:
            match = pattern.search(line)
            if match:
                findings.append(Finding(kind=kind, line=number, excerpt=_mask(match.group(0))))
                break
        if len(findings) >= max_findings:
            break
    return ScanResult(findings)


def _mask(value: str) -> str:
    if len(value) <= 8:
        return REDACTED
    return f"{value[:4]}…{value[-2:]}" if not value.startswith("-----") else "-----BEGIN PRIVATE KEY-----"


def redact(text: str) -> str:
    """Return the text with every detected secret replaced; keeps the rest intact."""
    if not text:
        return text
    result = text
    for _kind, pattern in PATTERNS:
        result = pattern.sub(REDACTED, result)
    return result
