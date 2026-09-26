"""
Tests for the ALLOWED_ENV_VARS env-var allowlist (Gate E, Option A).

Verifies that:
  - Every KEY= in each .env.*.example template is allowlisted, so a correctly
    configured environment never triggers a spurious warning.
  - Key Python-consumed vars are present.
  - _warn_unknown_env_vars logs a warning for unknown keys and stays silent
    for known keys.

These tests run in-process against config.settings.base (read_env is skipped
under test settings, so importing the module is side-effect free).
"""

from pathlib import Path

import pytest

from config.settings.base import ALLOWED_ENV_VARS, _warn_unknown_env_vars

pytestmark = [pytest.mark.unit, pytest.mark.settings]

_ROOT = Path(__file__).resolve().parent
while not (_ROOT / "pyproject.toml").exists():
    _ROOT = _ROOT.parent


def _example_keys(filename: str) -> set[str]:
    """Extract `KEY=` names (skipping comments/blank lines) from an example file."""
    keys = set()
    # The example files may contain non-UTF-8 bytes (e.g. em-dashes stored as
    # Windows-1252 0x97). Keys are pure ASCII, so ignore undecodable bytes.
    text = (_ROOT / filename).read_text(encoding="utf-8", errors="ignore")
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key:
                keys.add(key)
    return keys


@pytest.mark.parametrize(
    "filename",
    [".env.example", ".env.dev.example", ".env.prod.example", ".env.test.example"],
)
def test_example_keys_in_allowlist(filename: str) -> None:
    """Every KEY= in a tracked .env.*.example template is allowlisted."""
    missing = _example_keys(filename) - ALLOWED_ENV_VARS
    assert not missing, (
        f"{filename} keys not in ALLOWED_ENV_VARS: {sorted(missing)}"
    )


def test_python_consumed_vars_in_allowlist() -> None:
    """Key Python-consumed env vars are present in the allowlist."""
    expected = {
        "DATABASE_URL",
        "POSTGRES_PORT",
        "DJANGO_BUILD",
        "DJANGO_ONESHOT",
        "DJANGO_SETTINGS_MODULE",
        "EMAIL_BACKEND",
        "BOT_HEALTH_STALE_SECONDS",
        "SCHEDULER_COMMAND_TIMEOUT",
    }
    missing = expected - ALLOWED_ENV_VARS
    assert not missing, f"Python-consumed vars not in ALLOWED_ENV_VARS: {sorted(missing)}"


def test_scheduler_health_stale_seconds_allowlisted() -> None:
    """SCHEDULER_HEALTH_STALE_SECONDS stays allowlisted even though the Python
    setting was removed (CC-5); it is still a known compose/shell var."""
    assert "SCHEDULER_HEALTH_STALE_SECONDS" in ALLOWED_ENV_VARS


def test_unknown_env_var_logs_warning(caplog: pytest.LogCaptureFixture) -> None:
    """Unknown keys trigger a WARNING mentioning each key."""
    with caplog.at_level("WARNING", logger="config.settings.base"):
        _warn_unknown_env_vars({"BOT_T0KEN", "DJANGO_SECRETKEY"})
    warnings = [r.message for r in caplog.records if r.levelname == "WARNING"]
    assert any("BOT_T0KEN" in w for w in warnings)
    assert any("DJANGO_SECRETKEY" in w for w in warnings)


def test_known_env_vars_no_warning(caplog: pytest.LogCaptureFixture) -> None:
    """Known keys produce no WARNING."""
    with caplog.at_level("WARNING", logger="config.settings.base"):
        _warn_unknown_env_vars(
            {"DJANGO_SECRET_KEY", "BOT_TOKEN", "POSTGRES_PORT", "SITE_URL"}
        )
    assert not [r for r in caplog.records if r.levelname == "WARNING"]
