"""
Structural tests for CI/CD security scanning and deploy-check hardening.

Covers security scanning tooling (pip-audit, trivy, gitleaks) and the
dedicated `deploy-check` CI job (Block B2 / finding 12-OPS-001) that runs
``manage.py check --deploy`` against production settings. These are
non-execution tests — they assert on the structure of config files,
not on running security tools.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from django.conf import settings

pytestmark = [pytest.mark.unit]
_PROJECT_ROOT = settings.BASE_DIR.parent


def _read(*parts: str) -> str:
    """Read a text file from the project root."""
    return (_PROJECT_ROOT / Path(*parts)).read_text(encoding="utf-8")


def test_ci_yml_has_security_scan_tools() -> None:
    """ci.yml references pip-audit, trivy, and gitleaks (>= 3 tools)."""
    content = _read(".github", "workflows", "ci.yml")
    tools = ["pip-audit", "trivy", "gitleaks"]
    found = sum(1 for t in tools if t in content)
    assert found >= 3, f"Only found {found}/3 security scanning tools in ci.yml"


def test_ci_yml_has_security_job() -> None:
    """ci.yml defines a 'security' job."""
    content = _read(".github", "workflows", "ci.yml")
    assert "  security:" in content


def test_security_steps_are_blocking() -> None:
    """Security scan steps in ci.yml are blocking (no continue-on-error; Trivy/gitleaks use exit-code: 1)."""
    content = _read(".github", "workflows", "ci.yml")
    assert "continue-on-error: true" not in content
    assert "exit-code: 1" in content
    assert "--exit-code 1" in content


def test_dependabot_config_exists() -> None:
    """.github/dependabot.yml exists with github-actions and uv ecosystems."""
    dependabot_path = _PROJECT_ROOT / ".github" / "dependabot.yml"
    assert dependabot_path.exists(), "dependabot.yml not found"
    content = dependabot_path.read_text(encoding="utf-8")
    assert "github-actions" in content
    assert "uv" in content


# ---------------------------------------------------------------------------
# Dependabot configuration — PR #7 / PR #8 prevention
# ---------------------------------------------------------------------------
# PR #7 proposed major-version GitHub Action upgrades (actions/checkout v4→v7,
# astral-sh/setup-uv v5→v10) as auto-filed Dependabot PRs. PR #8 proposed
# Django 5→6 and django-prometheus 2.5.0→2.6.0.dev22. The dependabot.yml must
# gate these behind manual review by restricting update types per ecosystem
# and entry.

def _find_dependabot_entry(ecosystem: str, group_name: str | None = None) -> dict | None:
    """Locate a dependabot update entry by ecosystem, optionally by group name.

    Returns the first entry dict whose ``package-ecosystem`` matches, or
    ``None`` if no entry matches. When ``group_name`` is given, only entries
    whose ``groups`` dict contains that key are considered.
    """
    from ruamel.yaml import YAML

    path = _PROJECT_ROOT / ".github" / "dependabot.yml"
    if not path.exists():
        return None
    document = YAML(typ="safe").load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        return None
    updates = document.get("updates")
    if not isinstance(updates, list):
        return None
    for entry in updates:
        if not isinstance(entry, dict):
            continue
        if entry.get("package-ecosystem") != ecosystem:
            continue
        if group_name is not None:
            groups = entry.get("groups")
            if isinstance(groups, dict) and group_name in groups:
                return entry
            continue
        return entry
    return None


def test_dependabot_uv_restricted_to_semver_minor_patch() -> None:
    """The uv ecosystem only allows semver-minor and semver-patch updates.

    Blocks major-version bumps (e.g., Django 5→6) and pre-release/dev versions
    (e.g., django-prometheus 2.5.0→2.6.0.dev22) from being auto-filed —
    the root cause of PR #8.
    """
    entry = _find_dependabot_entry("uv")
    assert entry is not None, "uv ecosystem entry not found in dependabot.yml"
    allow = entry.get("allow", [])
    assert allow, "uv ecosystem must specify an `allow` list"
    update_types = {item.get("update-type") for item in allow if isinstance(item, dict)}
    assert "version-update:semver-major" not in update_types, (
        "uv ecosystem must not allow major-version updates"
    )
    assert "version-update:semver-minor" in update_types, (
        "uv ecosystem must allow semver-minor updates"
    )
    assert "version-update:semver-patch" in update_types, (
        "uv ecosystem must allow semver-patch updates"
    )


def test_dependabot_django_prometheus_prerelease_ignored() -> None:
    """The uv ecosystem ignores pre-release updates for django-prometheus.

    Belt-and-suspenders alongside the `allow` restriction: even if a pre-release
    version type slips through the allow filter, this `ignore` entry blocks it.
    """
    entry = _find_dependabot_entry("uv")
    assert entry is not None
    ignore_list = entry.get("ignore", [])
    prometheus_ignores = [
        i
        for i in ignore_list
        if isinstance(i, dict) and i.get("dependency-name") == "django-prometheus"
    ]
    assert prometheus_ignores, "django-prometheus must appear in the uv ignore list"
    all_update_types: set[str] = set()
    for ign in prometheus_ignores:
        all_update_types.update(ign.get("update-types", []))
    assert "version-update:semver-prerelease" in all_update_types, (
        "django-prometheus must ignore pre-release updates"
    )


def test_dependabot_build_actions_restricted_to_minor_patch() -> None:
    """The build-actions entry only allows semver-minor and semver-patch.

    Major-version action upgrades (actions/checkout v4→v7, astral-sh/setup-uv
    v5→v10) require manual review (12-OPS-017) — root cause of PR #7.
    """
    entry = _find_dependabot_entry("github-actions", "build-actions")
    assert entry is not None, "build-actions github-actions entry not found"
    allow = entry.get("allow", [])
    assert allow, "build-actions entry must specify an `allow` list"
    update_types = {
        item.get("update-type", "any") for item in allow if isinstance(item, dict)
    }
    assert "version-update:semver-major" not in update_types, (
        "build-actions entry must not allow major-version updates"
    )
    assert "version-update:semver-minor" in update_types
    assert "version-update:semver-patch" in update_types


def test_dependabot_security_actions_allows_all_types() -> None:
    """The security-actions entry allows all update types (incl. majors).

    trivy-action and codeql upload-sarif need timely major-version upgrades
    for CVE coverage.
    """
    entry = _find_dependabot_entry("github-actions", "security-actions")
    assert entry is not None, "security-actions github-actions entry not found"
    allow = entry.get("allow", [])
    assert allow, "security-actions entry must specify an `allow` list"
    for item in allow:
        assert "update-type" not in item, (
            f"security-actions allow entry must not restrict update-type: {item}"
        )


def test_dockerfile_has_sbom_generation() -> None:
    """Dockerfile builder stage generates a CycloneDX SBOM (via syft)."""
    content = _read("docker", "Dockerfile")
    assert "sbom" in content.lower()
    assert "syft" in content.lower() or "cyclonedx" in content.lower()


def test_dockerfile_copies_sbom_to_runtime() -> None:
    """Builder-stage SBOM is copied into the runtime image."""
    content = _read("docker", "Dockerfile")
    assert "sbom.cyclonedx.json" in content


def test_build_job_has_trivy_image_scan() -> None:
    """Build job scans the Docker image with Trivy."""
    content = _read(".github", "workflows", "ci.yml")
    assert "Scan Docker image for vulnerabilities" in content
    assert "trivy" in content.lower()


def test_build_job_targets_runtime_stage() -> None:
    """Build job must build the production ``runtime`` stage, not test-runtime.

    The ``test-runtime`` stage (the Dockerfile's final stage) installs
    ``[tool.uv]`` dev dependencies — including ``basedpyright`` which bundles
    Node.js — whose transitive CVEs inflate the Trivy image scan. No CI job
    executes this image (all CI jobs run on the runner); production consumes the
    ``runtime`` stage. Local Compose testing explicitly targets ``test-runtime``
    via ``docker-compose.test.yml``.
    """
    content = _read(".github", "workflows", "ci.yml")
    assert any(
        line.strip() == "target: runtime" for line in content.splitlines()
    ), (
        "ci.yml build job must pass target: runtime to docker/build-push-action "
        "so the pushed image excludes dev dependencies (12-OPS-013)"
    )
    assert "target: test-runtime" not in content, (
        "ci.yml build job must not target test-runtime — only local Compose should (12-OPS-013)"
    )


def test_trivy_image_scan_ignores_unfixed() -> None:
    """The Trivy image scan must set ignore-unfixed: true.

    Mirrors the existing fs-mode Trivy scan in the security job (which already
    has ``ignore-unfixed: true``). Only vulnerabilities with known fixes are
    reported; CVEs without an upstream fix do not block CI.
    """
    content = _read(".github", "workflows", "ci.yml")
    # The image scan section starts at the "Scan Docker image" step header and
    # extends until the next step ("Upload Trivy SARIF artifact").
    start = content.index("Scan Docker image for vulnerabilities")
    end = content.index("Upload Trivy SARIF", start)
    image_scan_section = content[start:end]
    assert "ignore-unfixed: true" in image_scan_section, (
        "the Trivy image scan in the build job must set ignore-unfixed: true "
        "to match the fs-mode scan policy (12-OPS-013)"
    )


def test_dockerfile_runtime_upgrades_os_packages() -> None:
    """The runtime stage runs apt-get upgrade to patch OS-level CVEs.

    The base ``python:3.14-slim`` image may ship stale Debian packages; the
    runtime stage upgrades them to the latest available versions before cleanup
    (12-OPS-013).
    """
    content = _read("docker", "Dockerfile")
    assert "apt-get upgrade" in content, (
        "Dockerfile runtime stage must run apt-get upgrade to patch OS CVEs (12-OPS-013)"
    )


def test_dockerfile_removes_system_setuptools() -> None:
    """The runtime stage uninstalls system-level setuptools.

    ``python:3.14-slim`` ships ``setuptools`` 70.3.0 in system site-packages,
    which is vulnerable to CVE-2025-47273 (fixed in 78.1.1) and
    CVE-2026-59890 (fixed in 83.0.0). setuptools is not needed at runtime —
    the venv at ``/opt/venv`` is self-contained. Removing it eliminates the
    HIGH-severity findings from the Trivy image scan.
    """
    content = _read("docker", "Dockerfile")
    assert "setuptools" in content, (
        "Dockerfile must reference setuptools so the removal step is present"
    )
    assert "uninstall" in content, (
        "Dockerfile runtime stage must uninstall setuptools, not merely comment about it"
    )


def test_dockerfile_has_cache_bust_arg() -> None:
    """The builder stage has a CACHEBUST ARG to invalidate stale BuildKit cache.

    Without an explicit cache-busting mechanism, a stale registry cache can
    serve an ``uv sync`` layer that installed outdated package versions (e.g.
    ``msgpack`` 1.1.2 when the lockfile specifies 1.2.2). The CACHEBUST arg
    changes the cache key for all subsequent layers, forcing a fresh install
    when its value is incremented.
    """
    content = _read("docker", "Dockerfile")
    assert "ARG CACHEBUST" in content, (
        "Dockerfile must declare a CACHEBUST ARG so stale BuildKit registry "
        "cache can be invalidated by incrementing its value"
    )


def test_gitleaks_config_exists() -> None:
    """.gitleaks.toml exists for allowlist configuration."""
    gitleaks_path = _PROJECT_ROOT / ".gitleaks.toml"
    assert gitleaks_path.exists(), ".gitleaks.toml not found"
    content = gitleaks_path.read_text(encoding="utf-8")
    assert "allowlists" in content


def test_pip_audit_in_dev_deps() -> None:
    """pip-audit is listed in pyproject.toml dev dependencies."""
    content = _read("pyproject.toml")
    assert "pip-audit" in content


# ---------------------------------------------------------------------------
# Block B2 — CI deploy-check hardening (finding 12-OPS-001)
# ---------------------------------------------------------------------------
# The previous CI "Django deploy checks" step ran ``manage.py check --deploy``
# against ``config.settings.test``, producing 6 false-positive warnings. It is
# replaced by a dedicated, blocking ``deploy-check`` job that targets
# ``config.settings.prod`` with ``--fail-level WARNING`` and all required
# production env vars set to valid placeholders.


def _deploy_check_section() -> str:
    """Return the YAML block of the dedicated ``deploy-check`` CI job.

    The job is the last definition in ``ci.yml``, so slicing from its header to
    end-of-file isolates exactly its contents.
    """
    content = _read(".github", "workflows", "ci.yml")
    marker = "  deploy-check:"
    idx = content.index(marker)
    return content[idx:]


def test_ci_deploy_check_uses_prod_settings() -> None:
    """The deploy-check job runs check --deploy against config.settings.prod (not test)."""
    section = _deploy_check_section()
    assert "config.settings.prod" in section
    assert "config.settings.test" not in section


def test_ci_deploy_check_fails_on_warnings() -> None:
    """The deploy-check step uses --fail-level WARNING and is not continue-on-error."""
    section = _deploy_check_section()
    assert "check --deploy --fail-level WARNING" in section
    assert "continue-on-error" not in section


def test_ci_deploy_check_sets_valid_secret_key() -> None:
    """The deploy-check job sets DJANGO_SECRET_KEY to a 50+ char non-secret literal."""
    section = _deploy_check_section()
    secret_key_value: str | None = None
    for line in section.splitlines():
        stripped = line.strip()
        if stripped.startswith("DJANGO_SECRET_KEY:"):
            raw = stripped.split(":", 1)[1].strip()
            if (raw.startswith('"') and raw.endswith('"')) or (
                raw.startswith("'") and raw.endswith("'")
            ):
                raw = raw[1:-1]
            secret_key_value = raw
            break
    assert secret_key_value is not None, "DJANGO_SECRET_KEY not set in deploy-check job"
    assert len(secret_key_value) >= 50, (
        f"DJANGO_SECRET_KEY is {len(secret_key_value)} chars; deploy-check requires >=50"
    )


# ---------------------------------------------------------------------------
# SAST scanning (bandit) — finding 12-OPS-001
# ---------------------------------------------------------------------------
# The security job runs bandit SAST. The step previously ran with
# ``working-directory: src/backend`` and repo-relative scan roots, so bandit
# resolved ``src/backend/src/backend`` and ``src/backend/pyproject.toml`` — both
# absent — and aborted with exit 2, scanning zero files. The guard below is a
# contract, not a substring check: it parses the SAST step, proves the configured
# config path and scan roots exist from the step's working directory, and runs
# bandit to assert a non-zero scanned-file count. Test trees are excluded via
# the [tool.bandit] ``exclude_dirs`` config.

# The step's name in ci.yml, used to locate it in the parsed document.
_SAST_STEP_NAME = "Run SAST (bandit)"

# Minimum number of source files a correct scan must touch. The repository has
# ~357 production Python files; a path-relativity regression collapses this to
# zero, so any non-zero floor catches it. The floor is deliberately well below
# the real count so ordinary file churn never trips it.
_MIN_SCANNED_FILES = 250


def _sast_step() -> dict:
    """Return the parsed SAST step mapping from ci.yml, proving it was found."""
    from ruamel.yaml import YAML

    content = _read(".github", "workflows", "ci.yml")
    document = YAML(typ="safe").load(content)
    assert isinstance(document, dict), "ci.yml must parse to a mapping"
    jobs = document.get("jobs")
    assert isinstance(jobs, dict), "ci.yml 'jobs' must be a mapping"
    security = jobs.get("security")
    assert isinstance(security, dict), "ci.yml has no 'security' job"
    steps = security.get("steps")
    assert isinstance(steps, list), "ci.yml 'security.steps' must be a list"
    for step in steps:
        if isinstance(step, dict) and step.get("name") == _SAST_STEP_NAME:
            return step
    raise AssertionError(f"ci.yml security job has no step named {_SAST_STEP_NAME!r}")


def _scan_roots_and_config(run: str) -> tuple[list[str], str]:
    """Parse ``-r <roots> -c <config>`` out of a bandit ``run`` command."""
    tokens = run.split()
    assert "-r" in tokens, f"bandit run must pass -r; got: {run!r}"
    assert "-c" in tokens, f"bandit run must pass -c; got: {run!r}"
    r_idx = tokens.index("-r")
    c_idx = tokens.index("-c")
    roots = tokens[r_idx + 1 : c_idx]
    config = tokens[c_idx + 1]
    return roots, config


def test_ci_yml_has_sast_job() -> None:
    """ci.yml defines a bandit SAST step with resolvable roots and config.

    This replaced a bare ``assert "bandit" in content``, which could not tell a
    working step from one that scanned nothing (project rule 2: production code
    is king — the old assertion let a permanently-red, no-op gate ship).
    """
    step = _sast_step()
    run = str(step.get("run", ""))
    assert "bandit" in run, f"SAST step must invoke bandit; got: {run!r}"
    working_dir = str(step.get("working-directory", "."))
    roots, config = _scan_roots_and_config(run)

    base = _PROJECT_ROOT if working_dir in (".", "./") else _PROJECT_ROOT / working_dir
    # The config path must resolve from the step's working directory — this is
    # exactly what broke: src/backend/pyproject.toml does not exist.
    config_path = base / config
    assert config_path.is_file(), (
        f"bandit config {config!r} does not resolve to {config_path} from "
        f"working-directory {working_dir!r}; bandit aborts with exit 2"
    )
    # Every scan root must resolve from the step's working directory.
    for root in roots:
        root_path = base / root
        assert root_path.is_dir(), (
            f"bandit scan root {root!r} does not resolve to {root_path} from "
            f"working-directory {working_dir!r}; bandit aborts with exit 2"
        )


def test_sast_step_actually_scans_files() -> None:
    """Run bandit as configured and assert a non-zero scanned-file count.

    A guard that only checks paths can still pass a step that scans nothing. This
    executes the configured command and reads bandit's own file metric, so a
    future path-relativity regression (or an over-broad ``exclude_dirs``) fails
    here instead of silently passing.
    """
    import json
    import shutil
    import subprocess
    import tempfile

    step = _sast_step()
    run = str(step.get("run", ""))
    working_dir = str(step.get("working-directory", "."))
    roots, config = _scan_roots_and_config(run)
    base = _PROJECT_ROOT if working_dir in (".", "./") else _PROJECT_ROOT / working_dir

    bandit = shutil.which("bandit")
    if bandit is None:
        # `uv run bandit` is the CI form; resolve it through uv if present.
        uv = shutil.which("uv")
        assert uv is not None, (
            "neither bandit nor uv is on PATH; the SAST contract cannot be checked"
        )
        argv = [uv, "run", "bandit"]
    else:
        argv = [bandit]

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as fh:
        report_path = fh.name
    try:
        argv += ["-r", *roots, "-c", config, "-f", "json", "-o", report_path]
        result = subprocess.run(
            argv,
            cwd=base,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        assert result.returncode in (0, 1), (
            f"bandit must exit 0 (clean) or 1 (findings), never 2 (abort): "
            f"got {result.returncode}\n{result.stderr[-2000:]}"
        )
        with open(report_path, encoding="utf-8") as report:
            payload = json.load(report)
    finally:
        import os

        os.unlink(report_path)

    metrics = payload.get("metrics", {})
    scanned = len([key for key in metrics if key != "_totals"])
    assert scanned >= _MIN_SCANNED_FILES, (
        f"bandit scanned only {scanned} files (expected >= {_MIN_SCANNED_FILES}); "
        f"the scan roots or exclude_dirs no longer cover the repository"
    )


def test_bandit_in_dev_deps() -> None:
    """pyproject.toml lists a SAST tool (bandit or semgrep) in dev dependencies."""
    content = _read("pyproject.toml")
    assert "bandit" in content or "semgrep" in content


def test_bandit_has_config_section() -> None:
    """pyproject.toml contains a [tool.bandit] configuration section."""
    content = _read("pyproject.toml")
    assert "[tool.bandit]" in content


# ---------------------------------------------------------------------------
# Supply-chain pinning of every workflow action (12-OPS-017)
# ---------------------------------------------------------------------------
# A third-party `uses:` reference written as a tag (e.g. `actions/checkout@v4`)
# is a mutable pointer: the tag can be moved under the pipeline, and the step
# that receives the production SSH private key or runs in the job holding
# `security-events: write` and a GITHUB_TOKEN would move with it. The guard
# asserts every third-party action is pinned to a full 40-hex commit SHA and
# carries the version in a trailing comment (so Dependabot bumps stay auditable).

# Matches a `uses:` reference: `owner/repo(/path)@ref`. Local actions (`./...`)
# and container actions (`docker://...`) carry no remote trust boundary and are
# out of scope.
_USES_REFERENCE_RE = re.compile(
    r"(?m)^\s*(?:-\s*)?uses:\s*(?P<ref>[^\s#]+)(?P<comment>\s*#.*)?$"
)
_COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _unpinned_uses_refs(text: str) -> list[str]:
    """Return every third-party ``uses:`` reference not pinned to a full commit SHA.

    Given a workflow file's text, returns one entry per offending reference. A
    pinned reference is ``owner/repo@<40-hex> # vX.Y.Z``. Local (``./``) and
    container (``docker://``) references are skipped deliberately: they carry no
    remote trust boundary.
    """
    offenders: list[str] = []
    for match in _USES_REFERENCE_RE.finditer(text):
        ref = match.group("ref")
        comment = match.group("comment") or ""
        if ref.startswith("./") or ref.startswith("docker://"):
            continue
        repo, sep, pin = ref.partition("@")
        if not sep:
            offenders.append(f"{ref} (no ref)")
            continue
        if not _COMMIT_SHA_RE.match(pin):
            offenders.append(f"{ref} (mutable ref, not a 40-hex commit SHA)")
        elif not comment.strip():
            offenders.append(f"{ref} (pinned but no version comment)")
    return offenders


def test_every_workflow_action_is_pinned_to_a_commit_sha() -> None:
    """Every third-party `uses:` in every workflow is a pinned commit SHA.

    A tag or branch is a pointer that can be moved under the pipeline, so the
    trust boundary — including the step that receives the production SSH private
    key and the security job's SARIF uploads — is only immutable when pinned to
    the commit SHA with the version recorded in a trailing comment (12-OPS-017).
    """
    workflows_dir = _PROJECT_ROOT / ".github" / "workflows"
    workflow_files = sorted(workflows_dir.glob("*.yml"))
    assert workflow_files, f"no workflow files found under {workflows_dir}"

    offenders: list[str] = []
    for path in workflow_files:
        text = path.read_text(encoding="utf-8")
        for offender in _unpinned_uses_refs(text):
            offenders.append(f"{path.name}: {offender}")

    assert not offenders, (
        "every third-party action must be pinned to a full commit SHA with the "
        "version in a trailing comment (12-OPS-017):\n" + "\n".join(offenders)
    )


def test_unpinned_uses_guard_detects_a_mutable_tag() -> None:
    """The pin guard fails on a mutable tag and on a blank version comment.

    A guard that only passes today's file is not a guard. This exercises the
    detector on representative inputs so a newly added unpinned reference turns
    ``test_every_workflow_action_is_pinned_to_a_commit_sha`` red.
    """
    assert _unpinned_uses_refs("        uses: actions/checkout@v4\n")
    assert _unpinned_uses_refs("        uses: appleboy/ssh-action@main\n")
    assert _unpinned_uses_refs(
        "        uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262\n"
    )
    # A pinned reference with its version comment is clean.
    assert not _unpinned_uses_refs(
        "        uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4.4.0\n"
    )
    # Local and container references carry no remote trust boundary.
    assert not _unpinned_uses_refs("      - uses: ./.github/actions/local\n")
    assert not _unpinned_uses_refs("      - uses: docker://alpine:3.20\n")


def test_dockerfile_downloads_are_pinned() -> None:
    """The image build's toolchain downloads are pinned, not fetched from `latest`.

    ``syft`` was installed from the moving ``main`` branch of an install script
    and the Tailwind CLI from ``releases/latest`` — neither is a pin. The syft
    tarball is now pinned to a version and verified against its sha256; Tailwind
    is pinned to a released version (12-OPS-017).
    """
    content = _read("docker", "Dockerfile")
    assert "releases/latest/download" not in content, (
        "Dockerfile must not download from a mutable `latest` release path"
    )
    assert "raw.githubusercontent.com/anchore/syft/main" not in content, (
        "Dockerfile must not install syft from a branch of install.sh"
    )
    assert "syft_1.54.0_linux_amd64.tar.gz" in content, (
        "Dockerfile must install syft from a pinned release tarball"
    )
    assert "sha256sum -c -" in content, (
        "Dockerfile must verify the pinned syft tarball's checksum"
    )
    assert "tailwindcss/releases/download/v4.3.3/" in content, (
        "Dockerfile must pin the Tailwind CLI to a released version"
    )
