"""
Restore-test workflow structural tests (B5 / finding 12-OPS-006).

Asserts that the restore-test CI workflow exists with a monthly schedule and
a restore-test job, and that the Makefile restore-test target includes the
migrate --plan --check step.

Follows the same pattern as test_docs_ci_parity.py and test_deploy_workflow.py:
string-level checks via Path.read_text(), no PyYAML dependency, repo-root
resolution by searching upward for pyproject.toml.

The 12-OPS-004 guards cover three classes of defect the existence checks cannot
see:

- readiness: the target waits for the DRILL DATABASE to answer a real query
  (``psql -tAc "SELECT 1"``), bounded; a ``pg_isready``-only loop is a liveness
  ping and is rejected (Restore Test run 42202769195, commit a6cc2b99);
- fail-on-empty: the target asserts ``django_migrations`` and ``ads_ad`` counts
  are ``> 0`` instead of echoing them;
- pg_restore strictness: ``--exit-on-error`` present, ``-1`` absent, and a
  ``pg_restore``-specific failure message rather than a catch-all diagnostic.
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


# --- Readiness gate: existence, not liveness (run 42202769195, a6cc2b99) ----
# The old gate was `until docker exec restore-db pg_isready ...`. `pg_isready` is
# a LIVENESS ping: the postgres entrypoint runs `CREATE DATABASE` against a
# temporary socket-only server, which reports "accepting connections" before
# `bazuna_restore` exists, and upstream does not require a wrong -U/-d to fail.
# The gate must therefore be a bounded loop whose condition runs a real query
# against the drill DB. The post-restore smoke step legitimately keeps
# `pg_isready`, so the checks below are scoped to the readiness loop — its
# `until` condition and its body up to `done`; the smoke step is never inspected.

# The `until` condition: everything after the `until` keyword up to the end of
# its physical line. The keyword is matched anywhere on the line because the
# recipe joins chain links with `;` (e.g. `_attempt=0; until …`).
_READINESS_CONDITION_RE = re.compile(r"\buntil\b(?P<condition>[^\n]*)")
# The rest of the loop body, from its `do` up to the terminating `done`. The
# terminator is a `done` followed only by `;`, `&&`, or the line ending, so an
# indented `done` (the recipe indents every physical line with a tab) matches.
_READINESS_BODY_RE = re.compile(r"\bdo\b(?P<body>.*?)\bdone\b[^\S\n]*(?:&&|;|$)", re.DOTALL)
# A real query: psql in tuple-only/unaligned mode, selected value `1`, against
# the drill DB named literally or via the `$$RESTORE_DB` shell variable (the
# Makefile reads the name once into `RESTORE_DB`, so either spelling is valid).
_READINESS_QUERY_RE = re.compile(r"\bpsql\b.*?\s-tAc\s+['\"]?SELECT 1\b", re.IGNORECASE)
_READINESS_TARGET_RE = re.compile(r"\s-d\s+['\"]?(?:\$\$RESTORE_DB\b|bazuna_restore\b)")
# A bounded retry: an attempt counter with a numeric ceiling, or a deadline.
_READINESS_BOUND_RES = (
    re.compile(r"-ge\s+[0-9]+"),
    re.compile(r"\bdeadline\b", re.IGNORECASE),
)


def _readiness_region(target_block: str) -> tuple[str, str]:
    """Split the readiness loop into ``(until condition, loop body)``.

    Both parts are empty when the block has no ``until … do … done`` loop, so
    every rule below reports a violation for a target without a bounded gate.
    """
    condition = _READINESS_CONDITION_RE.search(target_block)
    body = _READINESS_BODY_RE.search(target_block)
    return (
        condition.group("condition") if condition else "",
        body.group("body") if body else "",
    )


def _readiness_violations(target_block: str) -> list[str]:
    """Return readiness-gate violations for a ``restore-test`` target (empty ⇒ valid).

    Single source of truth for both the file guard and the RED proof. Rules:

    (a) the loop's ``until`` condition must not use ``pg_isready`` (a liveness
        ping that passes before ``CREATE DATABASE`` runs — run 42202769195);
    (b) it must run a real query: ``psql … -tAc … SELECT 1``;
    (c) the query must target the drill DB, named literally
        (``bazuna_restore``) or through the ``$$RESTORE_DB`` shell variable —
        accepted because the Makefile defines the name once and reuses the
        variable, so a renamed DB cannot leave a stale literal behind;
    (d) the loop must be bounded (an ``-ge <n>`` attempt ceiling or a
        ``deadline``) so a never-ready server fails the monthly drill instead
        of hanging it.

    The ``pg_isready`` in the post-restore smoke step is allowed: only the
    ``until`` condition is judged.
    """
    condition, body = _readiness_region(target_block)
    if not condition:
        return ["restore-test must wait for readiness in an `until … do … done` loop"]

    violations: list[str] = []
    if "pg_isready" in condition:
        violations.append(
            "restore-test readiness must not be pg_isready-only: it is a liveness "
            "ping that the entrypoint's temporary server answers before "
            "CREATE DATABASE runs (Restore Test run 42202769195, a6cc2b99)"
        )
    if not _READINESS_QUERY_RE.search(condition):
        violations.append(
            'restore-test readiness must run a real query: psql -tAc "SELECT 1" '
            "in the until condition, not a connectivity probe"
        )
    elif not _READINESS_TARGET_RE.search(condition):
        violations.append(
            "restore-test readiness query must target the drill DB "
            "(bazuna_restore or $$RESTORE_DB)"
        )
    if not any(bound.search(condition) or bound.search(body) for bound in _READINESS_BOUND_RES):
        violations.append(
            "restore-test readiness loop must be bounded (an `-ge <n>` attempt "
            "ceiling or a deadline) so a never-ready server cannot hang the drill"
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
    `docker pull` for a reason unrelated to backup integrity (12-OPS-004). An
    unauthenticated tag->manifest probe was additionally observed to be
    unreliable (401/404 under rate limiting), so the pin names the immutable
    digest directly. The pin must therefore be a recorded, digest-qualified
    reference at the canonical GHCR coordinate — never a `${{ github.sha }}`
    expression, never `:latest` — with its source commit SHA recorded next to it.
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

    The ``> 0`` assertion lives in the target's ``require_count`` helper, so the
    path is checked at both ends: each count step must invoke the helper with
    its exact query and must gate the chain on the helper's status, and the
    helper itself must validate the value is numeric and assert it is positive.
    (The single-line ``test "$$RESTORE_MIGRATIONS" -gt 0`` form was folded into
    that helper; asserting the literal alone would now pass only a dead string.)
    """
    block = _restore_test_target_block()
    assert "django_migrations" in block, (
        "restore-test must assert django_migrations is present in the restored "
        "database (12-OPS-004)"
    )
    for query, label in (
        ("SELECT count(*) FROM django_migrations;", "django_migrations rows"),
        ("SELECT count(*) FROM ads_ad;", "ads_ad rows"),
    ):
        invocation = f'require_count "{query}" "{label}"'
        assert invocation in block, (
            f"restore-test must assert {label} is non-empty through "
            f'{invocation!r}, not echo the count (12-OPS-004)'
        )
        step = block.split(invocation, 1)[1].split("\n", 1)[0]
        assert step.rstrip().endswith("|| exit 1; \\"), (
            f"the {label} count step must fail the target when the assertion "
            "fails, not record the count and continue"
        )
    helper = block.split("require_count() {", 1)[-1].split("};", 1)[0]
    assert 'test "$$_value" -gt 0' in helper, (
        "restore-test must fail when a count is zero (a positive-count "
        "assertion), not echo the count (12-OPS-004)"
    )
    assert "''|*[!0-9]*)" in helper, (
        "restore-test must reject a non-numeric count result so a failed query "
        "is never reported as 0 (12-OPS-004)"
    )
    assert "--exit-on-error" in block, (
        "restore-test pg_restore must carry --exit-on-error so a per-object error "
        "fails the drill instead of being silently skipped"
    )
    assert "--single-transaction" not in block, (
        "restore-test must NOT use --single-transaction: django_migrations is "
        "created before the data restore, so one transaction would abort before "
        "the smoke checks can inspect it"
    )
    assert re.search(r"(?<![\w-])-1(?![\w-])", block) is None, (
        "restore-test must NOT use the short form of --single-transaction (-1); "
        "the check is a bare-token match so `-ge 1` does not trip it"
    )
    assert "pg_restore failed" in block, (
        "a pg_restore failure must print a pg_restore-specific message; the "
        "'empty or partial dump' diagnostic must stay scoped to the table-count "
        "assertion, never act as the catch-all for an earlier failure"
    )


def test_restore_test_readiness_proves_the_database_exists() -> None:
    """Readiness must prove DB EXISTENCE, not liveness (run 42202769195).

    The target's readiness gate must be a real query against the drill database.
    A ``pg_isready``-only ``until`` loop let the drill reach ``pg_restore``
    before ``bazuna_restore`` existed, so the restore aborted with
    ``FATAL: database "bazuna_restore" does not exist`` (commit a6cc2b99).
    """
    block = _restore_test_target_block()
    violations = _readiness_violations(block)
    assert not violations, "\n".join(violations)


def test_readiness_predicate_rejects_liveness_only_and_accepts_the_real_file() -> None:
    """The readiness predicate rejects liveness gates (RED proof) and accepts the file.

    A guard that only passes today's file is not a guard. The same
    ``_readiness_violations`` predicate the file guard uses is driven over
    representative wrong gates — the exact OLD gate (which also carries the
    legitimate post-restore ``pg_isready`` smoke step: the gate is judged, not
    the smoke step), a loop with no query, a query against the wrong database,
    and an unbounded loop — plus the real-query form, which must pass.
    """
    old_gate = (
        "echo \"→ Smoke test 1/5: pg_isready (connectivity)\"; \\\n"
        "docker exec restore-db pg_isready -U restore_user -d bazuna_restore; \\\n"
        "_i=0; until docker exec restore-db pg_isready -U restore_user -d bazuna_restore; do\n"
        " sleep 1; _i=$$((_i + 1));\n"
        ' if [ $$_i -ge 30 ]; then echo "Error: postgres did not become ready in 30s"; exit 1; fi;\n'
        "done"
    )
    no_query = "_i=0; until docker exec restore-db true; do sleep 1; _i=$$((_i + 1)); done"
    wrong_db = (
        '_i=0; until docker exec restore-db psql -U restore_user -d postgres '
        '-tAc "SELECT 1" >/dev/null 2>&1; do\n sleep 1; _i=$$((_i + 1));\n'
        " if [ $$_i -ge 60 ]; then exit 1; fi;\ndone"
    )
    unbounded = (
        "until docker exec restore-db psql -U restore_user -d bazuna_restore "
        '-tAc "SELECT 1" >/dev/null 2>&1; do sleep 1; done'
    )
    real_gate = (
        "_attempt=0; until docker exec restore-db psql -U restore_user -d $$RESTORE_DB "
        "-tAc 'SELECT 1' 2>&1; do\n _attempt=$$((_attempt + 1));\n"
        " if [ $$_attempt -ge 60 ]; then return 1; fi;\n done"
    )
    wrong_gates = {
        "the old pg_isready-only gate": old_gate,
        "a loop without a real query": no_query,
        "a query against the wrong DB": wrong_db,
        "an unbounded readiness loop": unbounded,
    }
    for label, gate_text in wrong_gates.items():
        assert _readiness_violations(gate_text), (
            f"_readiness_violations must reject {label}: {gate_text!r}"
        )

    assert _readiness_violations(real_gate) == [], (
        "the real-query readiness gate must satisfy every rule"
    )
    assert _readiness_violations(_restore_test_target_block()) == [], (
        "the real Makefile readiness gate must satisfy every rule"
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
