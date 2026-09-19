"""Unit tests for the RedactingJsonFormatter and redaction helpers.

Pure unit tests — no database or Django settings required.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest

from apps.core.utils.json_logging import (
    RedactingJsonFormatter,
    is_sensitive_key,
    redact_string,
    redact_value,
)

pytestmark = [pytest.mark.unit]
class TestIsSensitiveKey:
    """Tests for is_sensitive_key()."""

    @pytest.mark.parametrize(
        "key",
        [
            "password",
            "PASSWORD",
            "Password",
            "api_key",
            "API_KEY",
            "apikey",
            "authorization",
            "Authorization",
            "secret",
            "token",
            "credential",
            "private_key",
            "access_key",
            "secret_key",
            "user_password",
            "bot_token",
            "api_key_id",
            "my_secret_field",
        ],
    )
    def test_sensitive_keys_detected(self, key: str) -> None:
        assert is_sensitive_key(key) is True

    @pytest.mark.parametrize(
        "key",
        [
            "username",
            "email",
            "name",
            "message",
            "level",
            "timestamp",
            "logger",
            "user_id",
            "phone_number",
        ],
    )
    def test_non_sensitive_keys_not_detected(self, key: str) -> None:
        assert is_sensitive_key(key) is False

    def test_empty_string_is_not_sensitive(self) -> None:
        assert is_sensitive_key("") is False


class TestRedactValue:
    """Tests for redact_value()."""

    def test_redacts_dict_with_sensitive_key(self) -> None:
        result = redact_value({"password": "secret123", "name": "alice"})
        assert result == {"password": "REDACTED", "name": "alice"}

    def test_redacts_nested_dict(self) -> None:
        result = redact_value(
            {"user": {"password": "secret123", "token": "abc"}, "name": "bob"}
        )
        assert result == {
            "user": {"password": "REDACTED", "token": "REDACTED"},
            "name": "bob",
        }

    def test_redacts_list_of_dicts(self) -> None:
        result = redact_value(
            [{"api_key": "key1"}, {"name": "item2"}, "plain_string"]
        )
        assert result == [{"api_key": "REDACTED"}, {"name": "item2"}, "plain_string"]

    def test_non_sensitive_string_passes_through(self) -> None:
        result = redact_value("hello world")
        assert result == "hello world"

    def test_numeric_values_preserved(self) -> None:
        result = redact_value({"count": 42, "price": 3.14, "flag": True})
        assert result == {"count": 42, "price": 3.14, "flag": True}

    def test_none_value_preserved(self) -> None:
        result = redact_value({"value": None})
        assert result == {"value": None}

    def test_deeply_nested_structure(self) -> None:
        result = redact_value(
            {"data": [{"inner": {"secret_key": "hidden", "visible": "ok"}}]}
        )
        assert result == {"data": [{"inner": {"secret_key": "REDACTED", "visible": "ok"}}]}


class TestRedactString:
    """Tests for redact_string()."""

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("password=secret123", "password=REDACTED"),
            ("password: secret123", "password=REDACTED"),
            ("api_key=abc123xyz", "api_key=REDACTED"),
            ("authorization: Bearer token123", "authorization=REDACTED token123"),
            ("token=abc.def.ghi", "token=REDACTED"),
            ("key=abc123xyz", "key=REDACTED"),
            ("User password=secret123 logged in", "User password=REDACTED logged in"),
        ],
    )
    def test_redacts_key_value_patterns(self, text: str, expected: str) -> None:
        assert redact_string(text) == expected

    def test_no_sensitive_pattern_unchanged(self) -> None:
        assert redact_string("just a normal log message") == "just a normal log message"

    def test_empty_string(self) -> None:
        assert redact_string("") == ""


class TestRedactingJsonFormatter:
    """Tests for RedactingJsonFormatter.format()."""

    def _make_record(
        self,
        msg: str = "test message",
        extra: dict[str, Any] | None = None,
        exc_info: tuple[type[BaseException], BaseException, Any] | None = None,
    ) -> logging.LogRecord:
        """Create a LogRecord suitable for the formatter.

        LogRecord.__init__ does not accept an ``extra`` kwarg (that is
        handled by Logger._log). We set extra attributes manually, mirroring
        what the logging framework does.
        """
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg=msg,
            args=None,
            exc_info=exc_info,
        )
        if extra:
            for key, value in extra.items():
                setattr(record, key, value)
        return record

    def test_output_is_valid_json(self) -> None:
        formatter = RedactingJsonFormatter()
        record = self._make_record("hello world")
        output = formatter.format(record)
        parsed = json.loads(output)
        assert isinstance(parsed, dict)

    def test_output_contains_standard_fields(self) -> None:
        formatter = RedactingJsonFormatter(datefmt="%Y-%m-%dT%H:%M:%S")
        record = self._make_record("hello world")
        parsed = json.loads(formatter.format(record))
        assert parsed["message"] == "hello world"
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "test.logger"
        assert "timestamp" in parsed

    def test_extra_fields_flattened_to_top_level(self) -> None:
        formatter = RedactingJsonFormatter()
        record = self._make_record(
            "user logged in", extra={"user_id": 12345, "action": "login"}
        )
        parsed = json.loads(formatter.format(record))
        assert parsed["user_id"] == 12345
        assert parsed["action"] == "login"

    def test_sensitive_extra_fields_redacted(self) -> None:
        formatter = RedactingJsonFormatter()
        record = self._make_record(
            "connecting",
            extra={
                "password": "supersecret",
                "api_key": "key123",
                "token": "tok456",
                "safe_field": "visible",
            },
        )
        parsed = json.loads(formatter.format(record))
        assert parsed["password"] == "REDACTED"
        assert parsed["api_key"] == "REDACTED"
        assert parsed["token"] == "REDACTED"
        assert parsed["safe_field"] == "visible"

    def test_exception_info_included(self) -> None:
        formatter = RedactingJsonFormatter()
        try:
            raise ValueError("something broke")
        except ValueError:
            import sys

            record = self._make_record(
                "error occurred",
                exc_info=sys.exc_info(),  # type: ignore[arg-type]
            )
        parsed = json.loads(formatter.format(record))
        assert "exception" in parsed
        assert "ValueError" in parsed["exception"]
        assert "something broke" in parsed["exception"]

    def test_non_serializable_extra_converted(self) -> None:
        """Non-serializable extra values are stringified via default=str."""
        formatter = RedactingJsonFormatter()

        class CustomObj:
            def __str__(self) -> str:
                return "custom-object-str"

        record = self._make_record(
            "processing", extra={"custom": CustomObj()}
        )
        parsed = json.loads(formatter.format(record))
        assert parsed["custom"] == "custom-object-str"

    def test_one_json_object_per_line(self) -> None:
        """Each format() call returns a single-line JSON string (JSONL)."""
        formatter = RedactingJsonFormatter()
        record = self._make_record("line one")
        output = formatter.format(record)
        assert "\n" not in output

    def test_logger_field_uses_record_name(self) -> None:
        formatter = RedactingJsonFormatter()
        record = logging.LogRecord(
            name="my.app.module",
            level=logging.WARNING,
            pathname=__file__,
            lineno=1,
            msg="warn message",
            args=None,
            exc_info=None,
        )
        parsed = json.loads(formatter.format(record))
        assert parsed["logger"] == "my.app.module"
        assert parsed["level"] == "WARNING"
