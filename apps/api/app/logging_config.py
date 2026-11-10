"""One JSON object per log record on stdout.

Log aggregation (Loki, CloudWatch, journald) needs machine-readable lines, and
the pipeline needs a guarantee that prompts, keys and learner text never reach
them: callers log only identifiers and counters.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
        }
        message = record.getMessage()
        if message.startswith("{") and message.endswith("}"):
            try:
                payload.update(json.loads(message))
            except ValueError:
                payload["message"] = message
        else:
            payload["message"] = message
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def configure_logging() -> None:
    level_name = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    level = getattr(logging, level_name, logging.INFO)
    if not isinstance(level, int):
        level = logging.INFO
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "_apm_json", False):
            return
    handler = logging.StreamHandler(sys.stdout)
    handler._apm_json = True  # type: ignore[attr-defined]
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(level)
    # Uvicorn installs its own handlers; keep them but stop them from also
    # emitting unformatted copies through the root logger.
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).propagate = False
    logging.getLogger("uvicorn.access").propagate = False
