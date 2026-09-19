"""JSON log formatter with sensitive-field redaction for production logging.

Outputs one JSON object per line (JSONL) for log aggregation compatibility.
Redacts values of keys whose names match sensitive patterns (password, token,
secret, api_key, authorization, credential, private_key) before emitting.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

_SENSITIVE_KEYWORDS: tuple[str, ...] = (
    "password",
    "token",
    "secret",
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "private_key",
    "access_key",
    "secret_key",
)

# Pattern for detecting sensitive key=value or key:value pairs in string values.
_REDACT_STRING_PATTERN = re.compile(
    r"(password|token|secret|api[_-]?key|authorization|key)\s*[:=]\s*\S+",
    re.IGNORECASE,
)

# Standard LogRecord attributes that should NOT be flattened into top-level keys.
_STANDARD_ATTRS: frozenset[str] = frozenset({
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "lineno", "funcName", "created", "msecs", "relativeCreated",
    "thread", "threadName", "processName", "process", "exc_info",
    "exc_text", "stack", "message", "taskName",
})


def is_sensitive_key(key: str) -> bool:
    """Check if a key name matches any sensitive keyword pattern."""
    lowered = key.lower()
    return any(kw in lowered for kw in _SENSITIVE_KEYWORDS)


def redact_value(value: Any) -> Any:
    """Recursively redact sensitive values in dicts, lists, and strings."""
    if isinstance(value, dict):
        return {
            k: ("REDACTED" if is_sensitive_key(k) else redact_value(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, str):
        return redact_string(value)
    return value


def redact_string(text: str) -> str:
    """Redact sensitive patterns in string values (e.g. 'password=secret123')."""
    return _REDACT_STRING_PATTERN.sub(r"\1=REDACTED", text)


class RedactingJsonFormatter(logging.Formatter):
    """JSON formatter that redacts sensitive field values in log records.

    Emits a single JSON object per log record with standard fields
    (timestamp, level, message, logger) plus any extra attributes passed
    via ``logger.info(..., extra={...})``.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Flatten non-standard attributes (e.g. from extra={...}) onto top level
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS:
                log_data[key] = value

        redacted = redact_value(log_data)
        return json.dumps(redacted, default=str)
