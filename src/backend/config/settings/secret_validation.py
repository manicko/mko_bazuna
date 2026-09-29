"""Shared secret and bot-username validation for the settings modules.

Single home for the ``^<[^>]+>$`` placeholder pattern and for the bot-username
validity contract. Exists because the pattern was previously compiled in two
settings modules and each copy could drift from the other.

Import constraints (BC-1): this module must never import from another settings
module or from ``apps.*``. ``prod.py`` imports it, so a reverse import is a
cycle, and the app registry is not ready while settings are being imported.

Note on classification: ``BOT_USERNAME`` is a public Telegram handle, not a
secret. The defect is correctness, not disclosure. Settings modules validate it
inside their existing secret-validation block because that block is the
project's single "this variable must be real when we serve traffic" mechanism —
not because the value is confidential. Widening the block is therefore a
deliberate decision, not a convenience.

``BOT_USERNAME_PATTERN`` duplicates ``SiteConfig.bot_username``'s
``RegexValidator`` on purpose: settings cannot import the model. The two are
held together by
``config/settings/tests/test_bot_username_validation.py::
test_bot_username_helper_agrees_with_model_validator``.
"""

import re
from typing import Final

from django.core.exceptions import ImproperlyConfigured

# Byte-identical to SiteConfig.bot_username's RegexValidator (see module docstring).
BOT_USERNAME_PATTERN: Final[str] = r"^[A-Za-z0-9_]{3,32}$"

# Matches values shipped as templates in .env.*.example files, e.g.
# <generate-with-django-secret-key-generator>, <your-bot-token-from-botfather>
_PLACEHOLDER_RE: Final[re.Pattern[str]] = re.compile(r"^<[^>]+>$")

# A valid username contains no leading '@' and no whitespace; the pattern above
# is compiled once here so `is_valid_bot_username` and `validate_bot_username`
# share one compiled object rather than recompiling per call.
_USERNAME_RE: Final[re.Pattern[str]] = re.compile(BOT_USERNAME_PATTERN)


def is_placeholder(value: str) -> bool:
    """Return True when the value is a shipped ``<...>`` template placeholder."""
    return _PLACEHOLDER_RE.match(value) is not None


def is_valid_bot_username(value: str) -> bool:
    """Return True when the value is usable as a Telegram bot username.

    Rejects the empty string, a shipped placeholder, and anything outside
    ``BOT_USERNAME_PATTERN``. This is the predicate the settings guard and the
    repair command both use, so "what the guard accepts" and "what the model
    accepts" cannot diverge.
    """
    if not value:
        return False
    if is_placeholder(value):
        return False
    return _USERNAME_RE.match(value) is not None


def validate_bot_username(var_name: str, value: str) -> None:
    """Fail fast when a bot username is missing, a template, or malformed.

    Checks in the order that produces the most actionable message first, so an
    operator sees the empty case before the placeholder case and the placeholder
    case before the generic format case. Raises ``ImproperlyConfigured`` with a
    value-free message naming the variable and the remediation; never logs or
    echoes the value.
    """
    if not value:
        raise ImproperlyConfigured(
            f"{var_name} must be set and non-empty in production. "
            "Provide the real Telegram bot handle (without the @ prefix) via the "
            ".env.prod runtime file."
        )
    if is_placeholder(value):
        raise ImproperlyConfigured(
            f"{var_name} appears to be a placeholder value from a .env template. "
            "Replace it with the real value in .env.prod."
        )
    if _USERNAME_RE.match(value) is None:
        raise ImproperlyConfigured(
            f"{var_name} must be 3-32 characters, alphanumeric and underscore "
            "only, because it is persisted into SiteConfig.bot_username. Provide "
            "the real Telegram bot handle (without the @ prefix) in .env.prod."
        )
