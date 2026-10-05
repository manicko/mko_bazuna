"""
Deployment workflow structural tests (B4 / finding 12-OPS-005).

Asserts that the deploy workflow exists and contains the required
deploy-safety mechanisms: SSH-based deployment, pre-deploy backup,
health-check gating on /health/ready/, automated rollback on health-check
failure (12-OPS-010), rollback documentation reference, and the
connection-draining stop_grace_period on the production web service.

Follows the same pattern as test_compose_hardening.py and
test_docs_ci_parity.py: string-level checks via Path.read_text(),
no PyYAML dependency, repo-root resolution by searching upward
for pyproject.toml.
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

_DEPLOY_YML = _ROOT / ".github" / "workflows" / "deploy.yml"
_CI_YML = _ROOT / ".github" / "workflows" / "ci.yml"
_ENV_PROD_EXAMPLE = _ROOT / ".env.prod.example"
_PROD_COMPOSE = _ROOT / "docker-compose.prod.yml"


def _service_block(compose_path: Path, service_name: str) -> str:
    """Extract a service's YAML block from a compose file.

    Services are 2-space-indented keys under ``services:``.  The block
    extends until the next 2-space service definition or a 0-indent
    top-level key (e.g. ``volumes:``).
    """
    text = compose_path.read_text()
    pattern = rf"^  {re.escape(service_name)}:\s*$"
    lines = text.split("\n")
    start = None
    for i, line in enumerate(lines):
        if re.match(pattern, line):
            start = i
            break
    if start is None:
        return ""
    block: list[str] = [lines[start]]
    for line in lines[start + 1 :]:
        # Stop at a 0-indented top-level key (not a comment or empty line).
        if line and not line.startswith(" "):
            break
        # Stop at the next sibling service (exactly 2-space indent).
        if re.match(r"^  [A-Za-z_][A-Za-z0-9_]*:\s*$", line):
            break
        block.append(line)
    return "\n".join(block)


# --- deploy.yml structural tests -------------------------------------------


def test_deploy_workflow_exists() -> None:
    """deploy.yml must exist at .github/workflows/deploy.yml."""
    assert _DEPLOY_YML.exists(), (
        "deploy.yml must exist at .github/workflows/deploy.yml (B4 / 12-OPS-005)"
    )


def test_deploy_workflow_uses_ssh_action() -> None:
    """deploy.yml must use appleboy/ssh-action for remote deployment."""
    text = _DEPLOY_YML.read_text()
    assert "appleboy/ssh-action" in text, (
        "deploy.yml must use appleboy/ssh-action@v1.2.0 for SSH-based deployment"
    )


def test_deploy_workflow_has_health_check() -> None:
    """deploy.yml must gate deployment on /health/ready/ (readiness endpoint)."""
    text = _DEPLOY_YML.read_text()
    assert "/health/ready/" in text, (
        "deploy.yml must reference /health/ready/ in the health-check gate"
    )
    # Verify it's in a health-check context (not just a stray comment).
    assert re.search(r"health.?check", text, re.IGNORECASE), (
        "deploy.yml must contain a health-check step that uses /health/ready/"
    )


def test_deploy_workflow_has_backup_step() -> None:
    """deploy.yml must create a pre-deploy database backup via pg_dump."""
    text = _DEPLOY_YML.read_text()
    assert "pg_dump" in text, (
        "deploy.yml must run pg_dump for a pre-deploy database backup"
    )
    assert "backup" in text.lower(), (
        "deploy.yml must reference backup in a backup step"
    )


def test_deploy_workflow_has_rollback_reference() -> None:
    """deploy.yml must reference the rollback runbook (docs/ops/rollback.md)."""
    text = _DEPLOY_YML.read_text()
    assert "rollback" in text.lower(), (
        "deploy.yml must reference rollback on failure"
    )
    assert "rollback.md" in text, (
        "deploy.yml must reference docs/ops/rollback.md on failure"
    )


def test_deploy_workflow_captures_previous_image_tag() -> None:
    """deploy.yml must capture PREVIOUS_IMAGE_TAG before pulling/recreating (12-OPS-010)."""
    text = _DEPLOY_YML.read_text()
    assert "PREVIOUS_IMAGE_TAG" in text, (
        "deploy.yml must capture PREVIOUS_IMAGE_TAG before pull for rollback"
    )


def test_deploy_workflow_has_automated_rollback_step() -> None:
    """deploy.yml must perform automated rollback on health-check failure (12-OPS-010).

    Asserts the rollback mechanism: revert image tag, force-recreate services,
    and re-poll /health/ready/ with a 30-second timeout to validate rollback.
    """
    text = _DEPLOY_YML.read_text()
    assert "--force-recreate" in text, (
        "deploy.yml automated rollback must use --force-recreate when reverting"
    )
    assert "PREVIOUS_IMAGE_TAG" in text, (
        "deploy.yml rollback must revert to the captured PREVIOUS_IMAGE_TAG"
    )
    assert "timeout 30" in text, (
        "deploy.yml rollback must re-poll /health/ready/ with a 30-second timeout"
    )


# --- deploy provenance: a green build, an identity rollback (12-OPS-002, 12-OPS-008)
# ---------------------------------------------------------------------------
# `deploy.yml` is triggered by workflow_dispatch with a free-text image_tag and
# has no dependency on the CI workflow, so any SHA can be typed in and deployed.
# Q11 (Product Owner, 2026-10-03) chose option (a): assert IN-WORKFLOW that the
# dispatched SHA is on `main` with a green CI run, before the SSH step; the
# manual environment approval is RETAINED. Separately, an automated rollback that
# targets a mutable tag is not a rollback to an identity (12-OPS-008), so the
# previous running image is captured by digest.


def test_ci_declares_pull_request_trigger() -> None:
    """ci.yml declares a `pull_request` trigger so changes are gated pre-merge.

    Without it, `push: branches: [main, develop]` makes every CI check a
    post-merge one: an ungated PR can merge and only then show red — and the
    deploy gate's "green CI run for the SHA" contract has no PR-side run
    (12-OPS-002).
    """
    from ruamel.yaml import YAML

    document = YAML(typ="safe").load(_CI_YML.read_text(encoding="utf-8"))
    triggers = document.get("on")
    assert isinstance(triggers, dict), "ci.yml must declare an `on:` mapping"
    assert "pull_request" in triggers, (
        "ci.yml must declare a pull_request trigger (12-OPS-002)"
    )


def test_deploy_asserts_dispatched_sha_is_a_gated_build() -> None:
    """deploy.yml asserts the dispatched SHA is on main with a green CI run.

    The assertion is option (a) of the 2026-10-03 Q11 ruling (12-OPS-002). It
    must run BEFORE the SSH step (so an ungated SHA never reaches the host) and
    must fail closed. The assertion reads workflow runs and commit status, so it
    needs `actions: read` and `statuses: read`; those permissions are asserted.
    """
    text = _DEPLOY_YML.read_text(encoding="utf-8")
    assert "Assert dispatched SHA is on main with a green CI run" in text, (
        "deploy.yml must carry the deploy-provenance assertion (12-OPS-002)"
    )
    # The assertion must precede the SSH deploy — an ungated SHA must not reach
    # the production host.
    assertion_idx = text.index("Assert dispatched SHA is on main with a green CI run")
    ssh_idx = text.index("appleboy/ssh-action")
    assert assertion_idx < ssh_idx, (
        "the deploy-provenance assertion must run before the SSH step (12-OPS-002)"
    )
    # Token scope: the assertion reads workflow runs and commit statuses.
    assert "actions: read" in text, (
        "deploy.yml must grant `actions: read` for the provenance assertion (12-OPS-002)"
    )
    assert "statuses: read" in text, (
        "deploy.yml must grant `statuses: read` for the provenance assertion (12-OPS-002)"
    )
    # It fails closed rather than open.
    assert "exit 1" in text, (
        "the provenance assertion must fail closed when it cannot verify (12-OPS-002)"
    )


def test_deploy_retains_manual_environment_approval() -> None:
    """The manual production approval is retained (12-OPS-002, Q11 option (a)).

    Option (b) (a `workflow_run` chain, which removes the human approval) was
    DECLINED on 2026-10-03. `environment: production` must stay, and no
    `workflow_run` trigger may appear.
    """
    text = _DEPLOY_YML.read_text(encoding="utf-8")
    assert "environment: production" in text, (
        "the manual environment approval must be retained (12-OPS-002)"
    )
    # The declined `workflow_run` chain must not appear as a *trigger*. It may
    # only appear as prose recording that it was declined, so the check is
    # scoped to the trigger block, not the whole file.
    from ruamel.yaml import YAML

    document = YAML(typ="safe").load(text)
    triggers = document.get("on")
    assert isinstance(triggers, dict), "deploy.yml must declare an `on:` mapping"
    assert "workflow_run" not in triggers, (
        "the declined workflow_run chain must not be a deploy.yml trigger (12-OPS-002)"
    )


def test_deploy_captures_previous_image_digest_before_pull() -> None:
    """The previous image is captured by digest, before pull/up (12-OPS-008).

    A tag is a mutable label, so a rollback targeting the previous tag can
    reproduce a different image. The running image's digest is captured with
    `docker inspect --format='{{index .Image}}'` while the old containers still
    run — before `pull` and before `up` — so it is the last-known-good identity.
    """
    text = _DEPLOY_YML.read_text(encoding="utf-8")
    assert "PREVIOUS_IMAGE_DIGEST" in text, (
        "deploy.yml must capture PREVIOUS_IMAGE_DIGEST (12-OPS-008)"
    )
    assert "{{index .Image}}" in text, (
        "the capture must read the running image's id via `docker inspect` (12-OPS-008)"
    )
    digest_idx = text.index("PREVIOUS_IMAGE_DIGEST=")
    pull_idx = text.index("pull\n")
    assert digest_idx < pull_idx, (
        "the digest must be captured before the image pull (12-OPS-008)"
    )


def test_deploy_rollback_branches_have_distinct_messages() -> None:
    """No-digest and digest-absent branches each have their own message.

    A generic failure cannot tell an operator "there was never a rollback
    target" from "the rollback target is no longer in the registry". Both
    branches must be present and distinct (12-OPS-008).
    """
    text = _DEPLOY_YML.read_text(encoding="utf-8")
    assert "No previous image digest available for rollback" in text, (
        "deploy.yml must have a distinct no-previous-digest message (12-OPS-008)"
    )
    assert "absent from the registry and could not be pulled" in text, (
        "deploy.yml must have a distinct digest-absent-from-registry message (12-OPS-008)"
    )


def test_deploy_does_not_build() -> None:
    """deploy.yml must never build an image — it deploys a verified artefact.

    This is the invariant (12-OPS-002 / OPS-008): the deploy path consumes an
    image produced by `ci.yml`, so neither `docker build` nor `docker compose …
    build` may appear anywhere in the workflow.
    """
    text = _DEPLOY_YML.read_text(encoding="utf-8")
    assert "docker build" not in text, (
        "deploy.yml must not build images; it deploys a CI-built artefact"
    )
    for line in text.splitlines():
        if "docker compose" in line and " build" in line:
            raise AssertionError(
                f"deploy.yml must not run `docker compose build`: {line.strip()!r}"
            )


def test_env_prod_example_forbids_latest_image_tag() -> None:
    """`.env.prod.example` must not ship `IMAGE_TAG=latest` (12-OPS-008).

    `latest` is a mutable label, not an identity: two hosts reading the same
    file with `latest` can run different code, and a rollback to `latest`
    reproduces whatever the tag points at now. The example carries a concrete
    pinned value instead.
    """
    text = _ENV_PROD_EXAMPLE.read_text(encoding="utf-8")
    image_tag_lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith("IMAGE_TAG=")
    ]
    assert image_tag_lines, ".env.prod.example must declare IMAGE_TAG"
    for line in image_tag_lines:
        assert line != "IMAGE_TAG=latest", (
            ".env.prod.example must not ship IMAGE_TAG=latest (12-OPS-008)"
        )


# --- docker-compose.prod.yml structural test -------------------------------


def test_deploy_health_check_uses_docker_exec() -> None:
    """deploy.yml health-check must use ``docker compose exec`` not bare ``curl localhost:8000``.

    Port 8000 is NOT published in production (docker-compose.yml:262 comment;
    docker-compose.prod.yml web service has no ``ports:`` section). The SSH
    script runs on the host, so ``curl http://localhost:8000`` would hit the
    host's port 8000 (Connection refused). The health-check must run curl inside
    the web container via ``docker compose exec -T web curl ...``.
    """
    text = _DEPLOY_YML.read_text()
    assert "docker compose exec" in text, (
        "deploy.yml health-check must use `docker compose exec` to reach the web "
        "container (port 8000 is not published on the host in production)"
    )
    assert "docker compose exec -T web curl" in text, (
        "deploy.yml health-check must use `docker compose exec -T web curl` "
        "(the -T flag disables pseudo-TTY allocation, required for piped output in scripts)"
    )
    # Ensure the broken pattern (bare curl without docker compose exec prefix) is NOT present.
    # The fixed line is: `while ! docker compose exec -T web curl -sf http://...`
    # so checking for the standalone `while ! curl -sf http://localhost:8000` catches the
    # old broken form without false-matching the corrected one.
    assert "while ! curl -sf http://localhost:8000" not in text, (
        "deploy.yml must NOT use bare `curl http://localhost:8000` — port 8000 is "
        "unpublished in production; use `docker compose exec -T web curl ...` instead"
    )


def test_web_service_has_stop_grace_period() -> None:
    """prod web service must have stop_grace_period >= 30s for gunicorn graceful shutdown.

    gunicorn.conf.py sets graceful_timeout = 30 and timeout = 60. Docker's
    default stop_grace_period is 10s, which truncates the graceful shutdown.
    """
    block = _service_block(_PROD_COMPOSE, "web")
    assert "stop_grace_period:" in block, (
        "web service in docker-compose.prod.yml must define stop_grace_period"
    )
    # Extract the value and verify it is >= 30s
    match = re.search(r"stop_grace_period:\s*(\d+)(s|m)?", block)
    assert match, "stop_grace_period must have a numeric value with optional s/m unit"
    value = int(match.group(1))
    unit = match.group(2) or "s"
    if unit == "m":
        value_seconds = value * 60
    else:
        value_seconds = value
    assert value_seconds >= 30, (
        f"stop_grace_period must be >= 30s to avoid truncating gunicorn graceful_timeout (30s), "
        f"got {value}{unit}"
    )


# --- production long-lived service set, declared once (12-OPS-007) ----------
# The production service set is declared by docker-compose.prod.yml itself: a
# long-lived service is one that carries `restart:`. This guard DERIVES that set
# from the manifest rather than restating it, so adding a restart:-carrying
# service without naming it on the deploy path turns the guard red — the drift
# that left the scheduler on a stale image and the daily backup job never
# started (12-OPS-005 / 12-OPS-007).


def _restart_carrying_prod_services() -> set[str]:
    """Return the service names in docker-compose.prod.yml that set ``restart:``.

    Parses the prod manifest with ruamel so the set is the manifest's own
    declaration, never a hand-maintained list.
    """
    from ruamel.yaml import YAML

    data = YAML(typ="safe").load(_PROD_COMPOSE.read_text(encoding="utf-8")) or {}
    services = data.get("services", {}) or {}
    return {name for name, svc in services.items() if "restart" in (svc or {})}


def _manifest_profiles() -> set[str]:
    """Return every compose profile named by a service in the prod manifest.

    Derived from ``docker-compose.prod.yml`` so the required deploy profile set
    is the manifest's declaration, never a hand-maintained list. A profile-gated
    service added to the manifest is therefore covered by the guard with no
    edit here (12-OPS-007).
    """
    from ruamel.yaml import YAML

    data = YAML(typ="safe").load(_PROD_COMPOSE.read_text(encoding="utf-8")) or {}
    services = data.get("services", {}) or {}
    return {profile for svc in services.values() for profile in (svc or {}).get("profiles", [])}


# Profiles that must stay OFF the deploy path, and the DOCUMENTED BLOCKED status
# that justifies each — the reason, not a bare literal. The deploy guard compares
# this set against ``_manifest_profiles()``, so a profile-gated service absent
# from ``deploy.yml``'s COMPOSE_PROFILES fails UNLESS it appears here with a real
# reason (12-OPS-007).
_BLOCKED_PROFILE_JUSTIFICATIONS: dict[str, str] = {
    "pgbouncer": "this profile is BLOCKED until it is in place",
}


def _blocked_profile_exclusions() -> dict[str, str]:
    """Return the profiles the deploy path must NOT activate, with their reason.

    An exclusion is only valid when the manifest still documents the profile as
    BLOCKED. Removing the BLOCKED note without removing the exclusion (or vice
    versa) therefore fails: the exclusion must never outlive or precede its
    justification. A reason that is empty, or that is not present verbatim in
    ``docker-compose.prod.yml``, is rejected — the cited warning
    ``"this profile is BLOCKED until it is in place"`` lives on the manifest's
    ``pgbouncer`` service (12-OPS-007). The operator-facing counterpart,
    ``"BLOCKED — do not enable the pgbouncer profile yet"``, is in
    ``docs/ops/docker-deployment.md``.
    """
    manifest_text = _PROD_COMPOSE.read_text(encoding="utf-8")
    for profile, reason in _BLOCKED_PROFILE_JUSTIFICATIONS.items():
        assert reason.strip(), (
            f"blocked profile {profile!r} needs a documented reason, not a bare "
            "literal (12-OPS-007)"
        )
        assert reason in manifest_text, (
            f"blocked profile {profile!r} cites {reason!r}, which is not in "
            "docker-compose.prod.yml — remove the exclusion or restore the "
            "documented BLOCKED note (12-OPS-007)"
        )
    return dict(_BLOCKED_PROFILE_JUSTIFICATIONS)


def _deploy_recreate_service_filters() -> list[set[str]]:
    """Return the service-name filters on the deploy `up -d` commands.

    The deploy workflow consumes the manifest rather than restating the service
    set, so its recreate commands must carry no service filter. Any bare
    (non-flag, non-path) token after `--remove-orphans` on an `up -d` line is a
    filter; a filter that omits a long-lived service is the defect (12-OPS-007).
    """
    text = _DEPLOY_YML.read_text(encoding="utf-8")
    filters: list[set[str]] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("#") or "up -d" not in stripped:
            continue
        tail = stripped.split("--remove-orphans", 1)
        if len(tail) != 2:
            continue
        names = {
            token
            for token in tail[1].split()
            if not token.startswith("-") and not token.startswith("${")
        }
        filters.append(names)
    return filters


def test_deploy_recreate_does_not_filter_out_a_long_lived_service() -> None:
    """The deploy path consumes the manifest set; it never filters a service out.

    The set is derived from ``docker-compose.prod.yml`` (the single declaration).
    If a deploy `up -d` command carries a service filter, every restart:-carrying
    service must be in it — otherwise a new long-lived service (or `scheduler`,
    or `backup`) would be left on a stale image and the daily backup job never
    started (12-OPS-005 / 12-OPS-007).
    """
    required = _restart_carrying_prod_services()
    assert required, "docker-compose.prod.yml declares no restart:-carrying service"
    for names in _deploy_recreate_service_filters():
        if not names:
            # No service filter: `up -d --remove-orphans` plus the active
            # profiles starts every service the manifest declares.
            continue
        missing = required - names
        assert not missing, (
            "a deploy `up -d` service filter omits a long-lived production "
            "service (12-OPS-007): " + ", ".join(sorted(missing))
        )


def test_deploy_invocations_activate_every_profile_gated_service() -> None:
    """Every deploy compose invocation carries the explicit profile flags.

    `up -d` with no profile flags does not activate a profile-gated service —
    that is the whole defect. The guard DERIVES the required profile set from
    ``docker-compose.prod.yml`` (the manifest's own declaration) rather than
    restating a hand-maintained list, so a profile-gated service added to the
    manifest without a matching flag on the deploy path turns this red
    (12-OPS-007).

    The ``pgbouncer`` profile is deliberately EXCLUDED: its image tag does not
    resolve and the service is documented BLOCKED/unusable, so activating it
    aborts ``docker compose pull`` and, under ``set -e``, the whole deploy. The
    exclusion is tied to the documented BLOCKED note (see
    ``_blocked_profile_exclusions``), so removing the note without removing the
    exclusion — or vice versa — fails this guard (12-OPS-007).
    """
    text = _DEPLOY_YML.read_text(encoding="utf-8")
    match = re.search(r'COMPOSE_PROFILES="([^"]*)"', text)
    assert match, "deploy.yml must declare COMPOSE_PROFILES (12-OPS-007)"
    profiles = match.group(1)

    blocked = _blocked_profile_exclusions()
    required = _manifest_profiles() - set(blocked)

    for profile in sorted(required):
        assert f"--profile {profile}" in profiles, (
            f"deploy COMPOSE_PROFILES must include the manifest profile "
            f"{profile!r} (12-OPS-007); got {profiles!r}"
        )
    # The pgbouncer profile must stay OFF the deploy path: activating it aborts
    # `docker compose pull` on an unresolvable image tag (12-OPS-007).
    for profile in sorted(blocked):
        assert f"--profile {profile}" not in profiles, (
            f"deploy COMPOSE_PROFILES must NOT activate the blocked profile "
            f"{profile!r} (12-OPS-007)"
        )

    # Every state-changing service-lifecycle invocation (`pull`, `up -d`, and
    # the pre-deploy `exec -T db pg_dump`) must consume it. Read-only probes
    # (`images`, the `exec -T web curl` health check) and comment/echo lines
    # need no profile flags.
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("echo "):
            continue
        if "docker compose" not in stripped:
            continue
        state_changing = (
            "up -d" in stripped
            or " pull" in stripped
            or "exec -T db pg_dump" in stripped
        )
        if not state_changing:
            continue
        assert "${COMPOSE_PROFILES}" in stripped, (
            f"deploy compose invocation must consume ${{COMPOSE_PROFILES}}: {stripped}"
        )
