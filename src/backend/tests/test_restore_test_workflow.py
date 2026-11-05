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
    target_block = _restore_test_target_block()
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
# print a count and assert nothing, nor an image pin that is a placeholder or a
# moving expression on a `schedule` trigger. The guards below assert the
# observable properties the drill depends on: a RECORDED, IMMUTABLE digest of a
# published image (not `${{ github.sha }}`, not a bare tag), a fail-loud
# preflight that runs before any restore work, and a Makefile target that FAILS
# on an empty or partial restore instead of echoing a count. The behavioural
# proof that an empty restore fails is a RED demonstration of the target itself,
# recorded in the commit body — a text guard cannot execute `docker run`.

_MAKEFILE_RESTORE_TARGET_RE = re.compile(r"^restore-test:\s*", re.MULTILINE)
_GITHUB_SHA_EXPR = "${{ github.sha }}"

# The pinned image must be digest-qualified and live in the canonical GHCR
# coordinate. The regex is deliberately owner-AGNOSTIC (it matches any
# `ghcr.io/<owner>/<repo>`); the canonical-owner rule below is what rejects a
# digest-qualified reference under the wrong owner (12-OPS-009).
_CANONICAL_COORDINATE = "ghcr.io/manicko/mko_bazuna"
_DIGEST_REFERENCE_RE = re.compile(r"^(ghcr\.io/[a-z0-9_-]+/[a-z0-9_-]+)@sha256:[0-9a-f]{64}$")
_PIN_DECLARATION_RE = re.compile(r"^\s*RESTORE_APP_IMAGE:\s*(.+?)\s*$", re.MULTILINE)
_SOURCE_COMMIT_SHA = "57966ea0e6f8c5f41c3bdf20a98ba3e31a9204a8"


def _declared_pin(text: str) -> str:
    """Return the declared ``RESTORE_APP_IMAGE`` value, quote-stripped.

    One matching leading/trailing quote is stripped, so a YAML-quoted value such
    as ``"ghcr.io/...@sha256:..."`` is not falsely rejected. An empty string is
    returned when no declaration is found.
    """
    match = _PIN_DECLARATION_RE.search(text)
    if not match:
        return ""
    value = match.group(1).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1].strip()
    return value


def _pin_violations(text: str) -> list[str]:
    """Return human-readable violations of the pinned-image rules (empty ⇒ valid).

    Single source of truth for both the file guard and the RED proof. Rules:

    (a) the declared value must not be a ``${{ ... }}`` expression;
    (b) it must not be an empty value, ``:latest`` or a bare ``:tag`` — a bare
        tag is rejected because the value is not digest-qualified;
    (c) it must be digest-qualified:
        ``^(ghcr\\.io/[a-z0-9_-]+/[a-z0-9_-]+)@sha256:[0-9a-f]{64}$``;
    (d) the repository part must be the canonical coordinate
        ``ghcr.io/manicko/mko_bazuna``.

    Rule (d) is load-bearing and **not** implied by (c): the regex in (c) is
    owner-agnostic, so a digest-qualified reference under a non-canonical owner
    (e.g. ``ghcr.io/mko-bazuna/mko_bazuna@sha256:...``) passes (c) but must be
    rejected by (d) — GHCR has no namespace for such an owner (12-OPS-009).
    """
    value = _declared_pin(text)
    if not value:
        return ["restore-test.yml must declare RESTORE_APP_IMAGE (12-OPS-004)"]

    violations: list[str] = []
    if "${{" in value or "}}" in value:
        violations.append(
            f"RESTORE_APP_IMAGE must be a recorded identity, not an expression; got {value!r}"
        )
    if not value or value.endswith(":latest") or "@sha256:" not in value:
        violations.append(
            "RESTORE_APP_IMAGE must be digest-qualified (repo@sha256:<64 hex>), "
            f"not a bare tag or :latest; got {value!r} (12-OPS-008)"
        )
    match = _DIGEST_REFERENCE_RE.fullmatch(value)
    if not match:
        violations.append(
            "RESTORE_APP_IMAGE must match "
            "^(ghcr\\.io/[a-z0-9_-]+/[a-z0-9_-]+)@sha256:[0-9a-f]{64}$; "
            f"got {value!r}"
        )
    else:
        coordinate = match.group(1)
        if coordinate != _CANONICAL_COORDINATE:
            violations.append(
                f"RESTORE_APP_IMAGE must live at the canonical coordinate "
                f"{_CANONICAL_COORDINATE}; got {coordinate!r} (12-OPS-009)"
            )
    return violations


def _restore_test_target_block() -> str:
    """Return the Makefile's ``restore-test`` target body, bounded to the target.

    The block starts at the ``restore-test:`` line and extends until the next
    column-0 non-comment line (a sibling target), so checks scope only this
    target rather than everything below it in the Makefile.
    """
    text = _MAKEFILE.read_text(encoding="utf-8")
    match = _MAKEFILE_RESTORE_TARGET_RE.search(text)
    assert match, "Makefile must define a restore-test target"
    lines = text.split("\n")
    start_idx = next(i for i, line_text in enumerate(lines) if line_text.startswith("restore-test:"))
    block: list[str] = []
    for line in lines[start_idx:]:
        # Stop at the next column-0 non-comment line (a sibling target header).
        if block and line and not line.startswith((" ", "\t")) and not line.startswith("#"):
            break
        block.append(line)
    return "\n".join(block)


def test_restore_test_pins_a_digest_of_a_published_image() -> None:
    """restore-test.yml must pin an immutable digest at the canonical coordinate.

    A tag is a mutable label, not an identity (12-OPS-008), and the previous pin
    was a placeholder that never resolved, so the monthly drill failed at
    `docker pull` for a reason unrelated to backup integrity (12-OPS-004). The
    pin must therefore be a recorded, digest-qualified reference at the canonical
    GHCR coordinate — never a `${{ github.sha }}` expression, never `:latest` —
    with its source commit SHA recorded next to it.
    """
    text = _RESTORE_YML.read_text()
    assert _GITHUB_SHA_EXPR not in text, (
        "restore-test.yml must not pin the application image to "
        "${{ github.sha }} on a schedule trigger (12-OPS-004)"
    )
    violations = _pin_violations(text)
    assert not violations, (
        "restore-test.yml must pin an immutable, canonical digest "
        "(12-OPS-004 / 12-OPS-008 / 12-OPS-009):\n" + "\n".join(violations)
    )
    assert f"source-commit: {_SOURCE_COMMIT_SHA}" in text, (
        "the pin line must record its source commit "
        f"{_SOURCE_COMMIT_SHA} so a sha256 pin stays auditable"
    )


def test_restore_test_uses_the_pinned_image_for_migrate_plan() -> None:
    """The drill must consume the pin, behind a preflight that fails loudly.

    ``APP_IMAGE`` must resolve from ``env.RESTORE_APP_IMAGE`` (not a moving
    expression), and the ``Verify pinned app image resolves`` step must exist and
    run BEFORE both the ``docker pull`` step and the ``make restore-test`` step,
    so a stale pin fails before any restore work (12-OPS-004).
    """
    text = _RESTORE_YML.read_text()
    match = re.search(r"APP_IMAGE=(.+)", text)
    assert match, (
        "restore-test.yml must pass APP_IMAGE to `make restore-test` (12-OPS-004)"
    )
    app_image = match.group(1)
    assert "env.RESTORE_APP_IMAGE" in app_image, (
        "the drill's APP_IMAGE must reference the pinned RESTORE_APP_IMAGE, "
        f"not a moving expression; got {app_image!r} (12-OPS-004)"
    )
    assert "github.sha" not in app_image, (
        "the drill's APP_IMAGE must not resolve from github.sha (12-OPS-004)"
    )

    preflight_name = "Verify pinned app image resolves"
    assert preflight_name in text, (
        "restore-test.yml must verify the pinned image resolves before using it "
        "(12-OPS-004)"
    )
    preflight_idx = text.index(preflight_name)
    pull_idx = text.index("name: Pull recorded known-good app image")
    restore_idx = text.index("make restore-test BACKUP_FILE=")
    assert preflight_idx < pull_idx, (
        "the pinned-image preflight must run BEFORE the docker pull step "
        "(12-OPS-004)"
    )
    assert preflight_idx < restore_idx, (
        "the pinned-image preflight must run BEFORE the `make restore-test` step "
        "(12-OPS-004)"
    )

    preflight_body = text[preflight_idx:pull_idx]
    for token in ("docker manifest inspect", "::error::", "exit 1"):
        assert token in preflight_body, (
            f"the pinned-image preflight must contain {token!r} so a stale pin "
            "fails loudly and actionably (12-OPS-004)"
        )


def test_pin_predicate_rejects_wrong_pins_and_accepts_the_real_file() -> None:
    """The pin predicate rejects wrong pins (RED proof) and accepts the real file.

    A guard that only passes today's file is not a guard. This drives the same
    ``_pin_violations`` predicate the file guard uses over representative wrong
    inputs: the old placeholder value, a bare tag, ``:latest``, a
    ``${{ github.sha }}`` expression, a non-canonical coordinate, and — the
    load-bearing case — a digest-qualified reference under a NON-canonical owner,
    which the owner-agnostic digest regex alone would accept.
    """
    digest_tail = "@sha256:87cf5756a2e3ca57127d2f5ecaaa9fb02ab389a413fbb3ab9a9c04543a05fa70"
    wrong_pins = {
        "old placeholder value": 'RESTORE_APP_IMAGE: "2026.10.03"',
        "bare tag": 'RESTORE_APP_IMAGE: "ghcr.io/manicko/mko_bazuna:2026.10.03"',
        "latest tag": 'RESTORE_APP_IMAGE: "ghcr.io/manicko/mko_bazuna:latest"',
        "sha expression": 'RESTORE_APP_IMAGE: "${{ github.sha }}"',
        "non-canonical coordinate": f'RESTORE_APP_IMAGE: "ghcr.io/other/mko_bazuna{digest_tail}"',
        "non-canonical digest coordinate": f'RESTORE_APP_IMAGE: "ghcr.io/mko-bazuna/mko_bazuna{digest_tail}"',
    }
    for label, pin_text in wrong_pins.items():
        assert _pin_violations(pin_text), (
            f"_pin_violations must reject the {label} pin: {pin_text!r}"
        )

    assert _pin_violations(_RESTORE_YML.read_text()) == [], (
        "the real restore-test.yml pin must satisfy every rule"
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
