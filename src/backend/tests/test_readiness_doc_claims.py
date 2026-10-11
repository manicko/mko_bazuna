"""Readiness claim vs assertion contract (12-OPS-010, Q6 ruling).

The Product Owner ruling of 2026-10-03 (Q6) keeps ``BOT_HEALTH_CHECK_ENABLED``
DISABLED in production and removes every shipped documentation claim that the
bot staleness window gates readiness. ``/health/ready/`` is the deploy gate and
the documented rollback validation target, so a doc claiming otherwise describes
a control that does not run.

These guards assert what the probe actually does and that the operator-facing
documentation matches it:

- in production the probe reports ``checks["bot"] == "disabled"`` because the
  flag is set nowhere;
- the rollback runbook no longer asserts a bot liveness marker is part of the
  readiness criterion, and instead documents readiness as database + cache only.

The behavioural half (both ``BOT_HEALTH_CHECK_ENABLED`` branches are reachable)
stays in ``apps/core/tests/test_health_contract.py``, which is unchanged.
"""

from __future__ import annotations

import pytest
from django.conf import settings

pytestmark = [pytest.mark.unit]

_PROJECT_ROOT = settings.BASE_DIR.parent
_ROLLBACK = _PROJECT_ROOT / "docs" / "ops" / "rollback.md"
_DOCKER_DEPLOYMENT = _PROJECT_ROOT / "docs" / "ops" / "docker-deployment.md"


def test_bot_health_flag_is_off_and_set_nowhere_in_production() -> None:
    """``BOT_HEALTH_CHECK_ENABLED`` defaults False and is set in no compose file.

    The flag is a shipped setting that is simply off in production. Its absence
    from every compose file and every ``.env.*.example`` is what makes the probe
    report ``"bot": "disabled"`` and keeps bot health from gating deploys
    (12-OPS-010, Q6 ruling 2026-10-03).
    """
    assert settings.BOT_HEALTH_CHECK_ENABLED is False, (
        "BOT_HEALTH_CHECK_ENABLED must default False (12-OPS-010)"
    )
    compose_files = sorted(_PROJECT_ROOT.glob("docker-compose*.yml"))
    env_examples = sorted(_PROJECT_ROOT.glob(".env*.example"))
    assert compose_files and env_examples
    for path in [*compose_files, *env_examples]:
        text = path.read_text(encoding="utf-8")
        assert "BOT_HEALTH_CHECK_ENABLED" not in text, (
            f"{path.name} must not set BOT_HEALTH_CHECK_ENABLED — the flag stays "
            f"disabled in production (12-OPS-010)"
        )


def test_rollback_runbook_does_not_claim_bot_gates_readiness() -> None:
    """The rollback runbook no longer asserts bot liveness as a readiness check.

    ``checks.bot`` is always ``"disabled"`` in production, so a validation
    criterion expecting ``"ok"`` describes a control that does not run
    (12-OPS-010).
    """
    text = _ROLLBACK.read_text(encoding="utf-8")
    assert 'checks.bot == "ok"' not in text, (
        "rollback.md must not assert checks.bot == \"ok\" as a readiness "
        "criterion (12-OPS-010)"
    )
    assert '"bot": "ok"|"stale"|"disabled"' not in text, (
        "rollback.md must not present bot liveness as part of the readiness "
        "response contract (12-OPS-010)"
    )


def test_rollback_runbook_describes_readiness_as_database_and_cache() -> None:
    """Readiness is documented (in rollback.md) as database + cache only.

    A correction states what is true now, not merely that the old text was
    wrong: the runbook must say the probe checks database and cache, and that a
    bot fault does not fail it (12-OPS-010).
    """
    text = _ROLLBACK.read_text(encoding="utf-8")
    assert "database and cache only" in text.lower() or (
        "database + cache only" in text.lower()
    ), "rollback.md must describe readiness as database and cache only (12-OPS-010)"
    assert '"bot": "disabled"' in text, (
        "rollback.md must state the probe reports bot as \"disabled\" in "
        "production (12-OPS-010)"
    )


def test_docker_deployment_describes_the_flag_as_off() -> None:
    """``docker-deployment.md`` states the bot check is off and does not gate.

    This passage was already accurate; the guard keeps it from drifting into a
    claim that the staleness window gates web readiness (12-OPS-010).
    """
    text = _DOCKER_DEPLOYMENT.read_text(encoding="utf-8")
    assert "does not gate web readiness" in text or "does not gate readiness" in text, (
        "docker-deployment.md must state the bot check does not gate readiness "
        "(12-OPS-010)"
    )
