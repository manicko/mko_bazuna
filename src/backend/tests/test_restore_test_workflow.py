"""
Restore-test workflow structural tests (B5 / finding 12-OPS-006).

Asserts that the restore-test CI workflow exists with a monthly schedule and
a restore-test job, and that the Makefile restore-test target includes the
migrate --plan --check step.

Follows the same pattern as test_docs_ci_parity.py and test_deploy_workflow.py:
string-level checks via Path.read_text(), no PyYAML dependency, repo-root
resolution by searching upward for pyproject.toml.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

# Resolve repository root by searching upward for pyproject.toml.
# Robust to varying CWD in Docker (WORKDIR=/app or /app/src/backend) and
# local development (from repo root).
_ROOT = Path(__file__).resolve().parent
while not (_ROOT / "pyproject.toml").exists():
    _ROOT = _ROOT.parent

_RESTORE_YML = _ROOT / ".github" / "workflows" / "restore-test.yml"
_MAKEFILE = _ROOT / "Makefile"


# --- restore-test.yml structural tests --------------------------------------


def test_restore_test_scheduled_in_ci() -> None:
    """restore-test.yml must exist, define a schedule trigger, and contain a restore-test job."""
    assert _RESTORE_YML.exists(), (
        "restore-test.yml must exist at .github/workflows/restore-test.yml (B5 / 12-OPS-006)"
    )
    text = _RESTORE_YML.read_text()
    assert "schedule:" in text, "restore-test.yml must have a schedule trigger"
    assert "workflow_dispatch:" in text, "restore-test.yml must support manual dispatch"
    assert "restore-test:" in text, "restore-test.yml must define a restore-test job"


def test_restore_test_has_migrate_plan() -> None:
    """Makefile restore-test target must reference migrate --plan --check."""
    text = _MAKEFILE.read_text()
    target_match = re.search(r"^restore-test:\s*$", text, re.MULTILINE)
    assert target_match, "Makefile must define a restore-test target"
    target_block = text[target_match.start():]
    assert "migrate --plan --check" in target_block, (
        "Makefile restore-test target must run migrate --plan --check (B5 / 12-OPS-006)"
    )


def test_restore_test_schedule_is_monthly() -> None:
    """restore-test.yml must schedule monthly on the first Monday (cron 1-7 * 1)."""
    text = _RESTORE_YML.read_text()
    match = re.search(r'cron:\s*"([^"]+)"', text)
    assert match, "restore-test.yml must define a cron schedule"
    cron = match.group(1)
    parts = cron.split()
    assert len(parts) == 5, f"cron must have 5 fields, got {len(parts)}"
    # Day-of-month 1-7 (first week) + day-of-week 1 (Monday) = first Monday of month.
    assert parts[2] == "1-7", (
        f"day-of-month must be 1-7 for first-week cadence, got {parts[2]}"
    )
    assert parts[4] == "1", (
        f"day-of-week must be 1 (Monday), got {parts[4]}"
    )


# --- 12-OPS-004: the drill must prove a real restore ------------------------
# The string guards above assert the workflow EXISTS. They are the same class
# that let 12-OPS-004 through: they cannot detect a drill whose smoke steps
# print a count and assert nothing, nor an image pin that is a moving
# expression on a `schedule` trigger. The guards below assert the observable
# properties the drill depends on: a RECORDED known-good image tag (not
# `${{ github.sha }}`), and a Makefile target that FAILS on an empty or partial
# restore instead of echoing a count. The behavioural proof that an empty
# restore fails is a RED demonstration of the target itself, recorded in the
# commit body — a text guard cannot execute `docker run`.

_MAKEFILE_RESTORE_TARGET_RE = re.compile(r"^restore-test:\s*$", re.MULTILINE)
_GITHUB_SHA_EXPR = "${{ github.sha }}"


def _restore_test_target_block() -> str:
    """Return the Makefile's ``restore-test`` target body (to end of file)."""
    text = _MAKEFILE.read_text(encoding="utf-8")
    match = _MAKEFILE_RESTORE_TARGET_RE.search(text)
    assert match, "Makefile must define a restore-test target"
    return text[match.start():]


def test_restore_test_pins_a_recorded_app_image() -> None:
    """restore-test.yml must pin a recorded known-good tag, never github.sha.

    On a `schedule` trigger `github.sha` is the default-branch tip at fire time,
    which may have no pushed image, so the drill could fail at `docker pull` for
    a reason unrelated to backup integrity (12-OPS-004). The pinned value must be
    a concrete, non-expression tag.
    """
    text = _RESTORE_YML.read_text()
    assert _GITHUB_SHA_EXPR not in text, (
        "restore-test.yml must not pin the application image to "
        "${{ github.sha }} on a schedule trigger (12-OPS-004)"
    )
    match = re.search(r"RESTORE_APP_IMAGE_TAG:\s*\"?([^\"\n]+)\"?", text)
    assert match, (
        "restore-test.yml must declare a recorded RESTORE_APP_IMAGE_TAG "
        "(12-OPS-004)"
    )
    tag = match.group(1).strip()
    assert tag and "${{" not in tag, (
        f"RESTORE_APP_IMAGE_TAG must be a concrete recorded tag, got {tag!r} "
        "(12-OPS-004)"
    )


def test_restore_test_uses_the_pinned_tag_for_migrate_plan() -> None:
    """The `make restore-test APP_IMAGE=...` line must use the pinned tag."""
    text = _RESTORE_YML.read_text()
    match = re.search(r"APP_IMAGE=(.+)", text)
    assert match, (
        "restore-test.yml must pass APP_IMAGE to `make restore-test` (12-OPS-004)"
    )
    app_image = match.group(1)
    assert "env.RESTORE_APP_IMAGE_TAG" in app_image, (
        "the drill's APP_IMAGE must reference the recorded RESTORE_APP_IMAGE_TAG, "
        f"not a moving expression; got {app_image!r} (12-OPS-004)"
    )
    assert "github.sha" not in app_image, (
        "the drill's APP_IMAGE must not resolve from github.sha (12-OPS-004)"
    )


def test_restore_target_fails_on_an_empty_restore() -> None:
    """The Makefile restore-test target must assert non-empty content, not echo.

    An empty or partial restore must FAIL the target. Two properties are
    asserted: the target queries ``django_migrations`` (a migrated database,
    not a bare restore), and it asserts a count is greater than zero rather
    than only printing it. Echoing a count is the exact defect 12-OPS-004 names.
    """
    block = _restore_test_target_block()
    assert "django_migrations" in block, (
        "restore-test must assert django_migrations is present in the restored "
        "database (12-OPS-004)"
    )
    assert 'test "$$RESTORE_MIGRATIONS" -gt 0' in block, (
        "restore-test must fail when django_migrations is empty, not echo the "
        "count (12-OPS-004)"
    )
    assert 'test "$$RESTORE_ADS" -gt 0' in block, (
        "restore-test must fail when ads_ad has no rows, not echo the count "
        "(12-OPS-004)"
    )


def test_restore_test_keeps_the_self_generated_dump_labelled_additional() -> None:
    """The self-generated dump stays, labelled as an ADDITIONAL smoke test.

    The coordinator ruling of 2026-10-04 keeps this path so the round trip is
    checked at all, but requires it to be labelled honestly rather than passed
    off as a real artifact (12-OPS-004).
    """
    text = _RESTORE_YML.read_text()
    assert "test_backup.dump" in text, (
        "the self-generated dump path must remain (12-OPS-004)"
    )
    assert "ADDITIONAL" in text, (
        "the self-generated dump must be labelled an ADDITIONAL smoke test, not "
        "a real artifact (12-OPS-004)"
    )


def test_restore_test_records_the_off_host_half_as_an_open_named_task() -> None:
    """The off-host half must be recorded as an OPEN named task, not claimed.

    The off-host real-artifact half is not implementable from this repository
    (no object-storage client in the `backup` image, no storage SDK, a new
    credential surface). The workflow must record it as an open named task with
    that finding, so the drill stops being a false promise (12-OPS-004).
    """
    text = _RESTORE_YML.read_text()
    assert "OPEN NAMED TASK" in text, (
        "restore-test.yml must record the off-host half as an OPEN NAMED TASK "
        "(12-OPS-004)"
    )
    assert "object-storage client binary" in text, (
        "the open task must carry the implementability finding (12-OPS-004)"
    )
