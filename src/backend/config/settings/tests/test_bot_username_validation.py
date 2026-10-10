"""Tests for the prod.py BOT_USERNAME guard and the shared validation helper (CFG-005).

G4's decision is **required-non-empty**: an unset or empty ``BOT_USERNAME`` is a
hard ``ImproperlyConfigured`` in production, like the other seven guards. The
rejected alternative — validate-if-present — would let ``BOT_USERNAME=`` ship a
bot called ``bazuna_bot``; because the database wins over the environment and
``get_bot_username()``'s own fallback is that same literal, nothing downstream
could distinguish it from a correct deployment. ``test_bot_username_rejects_empty_in_production``
is the assertion that pins that decision.

Environment discipline (D7-1): ``_prod_env`` calls ``_prod_env_overrides()`` for
its **values**, then keeps only the keys in ``_PROD_ENV_ALLOWLIST`` and sets
``BOT_USERNAME`` from an explicit parameter. ``BOT_USERNAME`` is deliberately
absent from the allowlist, so no ambient value — from ``.env.test``, from
``os.environ``, or from a developer's shell — can reach the subprocess. That is
what makes this module green in both the Docker test container and the CI test
job by construction rather than by luck.

Because ``validate_bot_username`` checks empty, then placeholder, then format,
the three rejection modes produce three different, differently-actionable
messages; the tests below assert each branch's own message so a future reorder
of the checks is caught.
"""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError

from apps.core.models import SiteConfig
from config.settings.secret_validation import (
    BOT_USERNAME_PATTERN,
    is_placeholder,
    is_valid_bot_username,
)
from config.settings.tests.test_prod_logging import (
    _prod_env_overrides,
    _run_in_subprocess,
)

pytestmark = [pytest.mark.unit, pytest.mark.settings]

_PROD_MODULE = "config.settings.prod"
_ONESHOT_MODULE = "config.settings.oneshot"
_DEFAULT_BOT_USERNAME = "test_bot_for_testing_only"
_IMPORT_CODE = "import django; django.setup()"

# The only keys a subprocess is allowed to inherit. BOT_USERNAME is deliberately
# ABSENT: it is always set from an explicit parameter, so no value from .env.test,
# os.environ or a developer's shell can reach the assertion. This is what makes the
# module behave identically in the Docker test container and in the CI test job.
_PROD_ENV_ALLOWLIST = frozenset(
    {
        "DJANGO_SETTINGS_MODULE",
        "DEBUG",
        "DJANGO_SECRET_KEY",
        "BOT_TOKEN",
        "GOOGLE_TRANSLATE_API_KEY",
        "SITE_URL",
        "ALLOWED_HOSTS",
        "CSRF_TRUSTED_ORIGINS",
        "REDIS_URL",
        "LOG_MASK_KEY",
        "EMAIL_HOST",
        "EMAIL_PORT",
        "EMAIL_HOST_USER",
        "EMAIL_HOST_PASSWORD",
        "EMAIL_TIMEOUT",
        "EMAIL_BACKEND",
        "DEFAULT_FROM_EMAIL",
        "SUPPORT_NOTIFICATION_RECIPIENTS",
        "SENTRY_DSN",
        "DATABASE_URL",
        "PATH",
        "HOME",
    }
)

# Values that are not ``<...>`` placeholders but violate the model regex. Both the
# helper's placeholder branch and the model's validator reject none of them for the
# placeholder reason, so they exercise the format branch exclusively.
_MODEL_REGEX_VIOLATIONS = [
    "ab",  # 2 chars: too short
    "bot name",  # contains a space
    "my-bot",  # contains a hyphen
    "@my_bot",  # leading @
    "a" * 33,  # 33 chars: too long
]


def _prod_env(*, bot_username: str = _DEFAULT_BOT_USERNAME) -> dict[str, str]:
    """A production environment with an explicit BOT_USERNAME and nothing inherited.

    Values come from ``_prod_env_overrides()`` (the shared source of truth for what
    a valid production environment looks like); the *base* does not. The result is
    filtered to ``_PROD_ENV_ALLOWLIST``, so an ambient ``DJANGO_BUILD`` or
    ``DJANGO_ONESHOT`` or a developer's shell cannot decide the outcome. This is a
    different contract from ``_prod_env_overrides``, not a copy of it.
    """
    env = {
        key: value
        for key, value in _prod_env_overrides().items()
        if key in _PROD_ENV_ALLOWLIST
    }
    env["BOT_USERNAME"] = bot_username
    return env


# ---------------------------------------------------------------------------
# The helper itself (CFG-011's own regression guard)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("<your-bot-username>", True),
        ("<generate-with-django-secret-key-generator>", True),
        ("<placeholder>", True),
        ("x", False),
        ("", False),
        ("real_bot", False),
    ],
)
def test_secret_validation_placeholder_detector(value: str, expected: bool) -> None:
    """is_placeholder detects exactly the shipped ``<...>`` template form."""
    assert is_placeholder(value) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("<your-bot-username>", False),
        ("", False),
        ("ab", False),
        ("my-bot", False),
        ("test_bot", True),
    ],
)
def test_secret_validation_predicate(value: str, expected: bool) -> None:
    """is_valid_bot_username agrees with the placeholder and regex rules."""
    assert is_valid_bot_username(value) is expected


def test_bot_username_helper_agrees_with_model_validator() -> None:
    """The helper's pattern is byte-identical to the live model's RegexValidator.

    D6: the duplication between a settings-time pattern and the model field's is
    structural — settings cannot import ``apps.core.models`` — so this test is the
    only thing holding the two copies together.
    """
    validators = SiteConfig._meta.get_field("bot_username").validators
    patterns = [
        validator.regex.pattern
        for validator in validators
        if hasattr(validator, "regex")
    ]
    assert BOT_USERNAME_PATTERN in patterns

    for value in _MODEL_REGEX_VIOLATIONS + ["test_bot", "<your-bot-username>", ""]:
        model_ok = True
        for validator in validators:
            try:
                validator(value)
            except ValidationError:
                model_ok = False
                break
        assert is_valid_bot_username(value) is model_ok, value


# ---------------------------------------------------------------------------
# The prod guard
# ---------------------------------------------------------------------------


def test_bot_username_placeholder_rejected_in_production() -> None:
    """The shipped ``<your-bot-username>`` template is refused at prod import."""
    env = _prod_env(bot_username="<your-bot-username>")
    result = _run_in_subprocess(env, _IMPORT_CODE)
    assert result.returncode != 0, result.stderr
    assert "ImproperlyConfigured" in result.stderr
    assert "BOT_USERNAME" in result.stderr
    assert ".env.prod" in result.stderr
    # Value-free message contract (BC-4): the value never appears in the output.
    assert "<your-bot-username>" not in result.stderr


def test_bot_username_rejects_empty_in_production() -> None:
    """A present-but-empty BOT_USERNAME is a hard production failure (G4).

    This is the assertion that distinguishes required-non-empty from
    validate-if-present. The value is set present-but-empty rather than deleted,
    so ``read_env(overwrite=False)`` cannot back-fill it from a bind-mounted
    ``.env`` — the assertion is portable across both environments.
    """
    env = _prod_env(bot_username="")
    result = _run_in_subprocess(env, _IMPORT_CODE)
    assert result.returncode != 0, result.stderr
    assert "ImproperlyConfigured" in result.stderr
    assert "BOT_USERNAME" in result.stderr
    assert "non-empty" in result.stderr


@pytest.mark.parametrize("value", _MODEL_REGEX_VIOLATIONS)
def test_bot_username_rejects_value_failing_model_regex_in_production(
    value: str,
) -> None:
    """A non-placeholder value outside ^[A-Za-z0-9_]{3,32}$ is refused in production.

    This distinguishes a validator from a placeholder detector: ``^<[^>]+>$``
    accepts every one of these, so a helper that only detected the shipped
    template would let them all through.
    """
    env = _prod_env(bot_username=value)
    result = _run_in_subprocess(env, _IMPORT_CODE)
    assert result.returncode != 0, result.stderr
    assert "ImproperlyConfigured" in result.stderr
    assert "BOT_USERNAME" in result.stderr
    # None of these is a placeholder, so the placeholder branch cannot be what
    # fired: the message is the format-branch one and says so.
    assert "placeholder" not in result.stderr.lower()


def test_bot_username_valid_value_accepted_in_production() -> None:
    """A real-format BOT_USERNAME imports prod cleanly and reads back unchanged."""
    env = _prod_env()
    code = (
        "import django; django.setup(); "
        "from django.conf import settings; print(settings.BOT_USERNAME)"
    )
    result = _run_in_subprocess(env, code)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == _DEFAULT_BOT_USERNAME


# ---------------------------------------------------------------------------
# The two bypass directions the guard must keep working
# ---------------------------------------------------------------------------


def test_bot_username_guard_skipped_during_build() -> None:
    """DJANGO_BUILD=1 with a placeholder BOT_USERNAME imports with exit 0 (D2).

    An ungated guard would break the Docker builder stage, which runs
    ``collectstatic`` under config.settings.prod with ``DJANGO_BUILD=1`` and no
    ``.env`` at all, and would break
    ``test_django_build_flag_bypasses_all_prod_guards`` by construction.
    """
    env = _prod_env(bot_username="<your-bot-username>")
    env["DJANGO_BUILD"] = "1"
    result = _run_in_subprocess(env, _IMPORT_CODE)
    assert result.returncode == 0, result.stderr
    assert "ImproperlyConfigured" not in result.stderr
    assert "ValueError" not in result.stderr


def test_bot_username_guard_skipped_for_oneshot_bootstrap() -> None:
    """The placeholder passes under the bootstrap module, deliberately (D3).

    The dev bootstrap one-shots load config.settings.oneshot, where
    ``_SKIP_SECRET_VALIDATION`` is True, so this guard is inert there. The
    database is protected in that path by migration 0003's ``full_clean()``, not
    by a settings guard. This test exists so a future editor does not "close the
    gap" by adding an ungated guard to oneshot.py.
    """
    env = _prod_env(bot_username="<your-bot-username>")
    env["DJANGO_SETTINGS_MODULE"] = _ONESHOT_MODULE
    env["DJANGO_ONESHOT"] = "1"
    result = _run_in_subprocess(env, _IMPORT_CODE)
    assert result.returncode == 0, result.stderr
    assert "ImproperlyConfigured" not in result.stderr
    assert "ValueError" not in result.stderr
