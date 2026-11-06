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
import tomllib
from dataclasses import dataclass
from pathlib import Path

import pytest
from django.conf import settings

# BASE_DIR in settings points to src/ ; its parent is the repository root.
_PROJECT_ROOT = settings.BASE_DIR.parent


def _read(*parts: str) -> str:
    """Read a text file from the project root."""
    return (_PROJECT_ROOT / Path(*parts)).read_text(encoding="utf-8")


def _ci_document() -> dict:
    """Parse ``ci.yml`` as YAML and return the document mapping.

    Uses ``yaml.safe_load`` (PyYAML) rather than ``ruamel.yaml`` because
    ci.yml legitimately repeats ``runs-on: ubuntu-latest`` across job
    mappings; ruamel 0.19 ``typ="safe"`` rejects duplicate keys, while
    PyYAML silently lets the last value win (acceptable here — we only
    read specific keys, never the repeated ones).
    """
    import yaml

    document = yaml.safe_load(_read(".github", "workflows", "ci.yml"))
    assert isinstance(document, dict), "ci.yml must parse to a mapping"
    return document


def _job_steps(job_name: str) -> list:
    """Return the parsed ``steps`` list for ``jobs.<job_name>`` from ci.yml.

    Raises ``AssertionError`` if the job or its steps are missing or
    malformed, surfacing config drift as a test failure rather than a
    silent KeyError later.
    """
    document = _ci_document()
    jobs = document.get("jobs")
    assert isinstance(jobs, dict), "ci.yml 'jobs' must be a mapping"
    job = jobs.get(job_name)
    assert isinstance(job, dict), f"ci.yml has no '{job_name}' job"
    steps = job.get("steps")
    assert isinstance(steps, list), f"ci.yml '{job_name}.steps' must be a list"
    return steps


def _job_by_name(job_name: str) -> dict:
    """Return the parsed ``jobs.<job_name>`` mapping from ci.yml."""
    document = _ci_document()
    jobs = document.get("jobs")
    assert isinstance(jobs, dict), "ci.yml 'jobs' must be a mapping"
    job = jobs.get(job_name)
    assert isinstance(job, dict), f"ci.yml has no '{job_name}' job"
    return job


def _step_by_name(job_name: str, step_name: str) -> dict:
    """Return a parsed step by its display name from ``jobs.<job_name>``."""
    for step in _job_steps(job_name):
        if isinstance(step, dict) and step.get("name") == step_name:
            return step
    raise AssertionError(f"ci.yml {job_name} job has no step named {step_name!r}")


def _build_step(step_name: str) -> dict:
    """Return a parsed step by its display name from the ``build`` job."""
    return _step_by_name("build", step_name)


@pytest.mark.unit
def test_ci_yml_has_security_scan_tools() -> None:
    """ci.yml references pip-audit, trivy, and gitleaks (>= 3 tools)."""
    content = _read(".github", "workflows", "ci.yml")
    tools = ["pip-audit", "trivy", "gitleaks"]
    found = sum(1 for t in tools if t in content)
    assert found >= 3, f"Only found {found}/3 security scanning tools in ci.yml"


@pytest.mark.unit
def test_ci_yml_has_security_job() -> None:
    """ci.yml defines a 'security' job."""
    content = _read(".github", "workflows", "ci.yml")
    assert "  security:" in content


@pytest.mark.unit
def test_security_steps_are_blocking() -> None:
    """Security scan steps in ci.yml are blocking (no continue-on-error; Trivy/gitleaks use exit-code: 1)."""
    content = _read(".github", "workflows", "ci.yml")
    steps = _job_steps("security")
    for step in steps:
        if isinstance(step, dict):
            assert step.get("continue-on-error") is not True, (
                f"security step {step.get('name', '<unnamed>')} must not set "
                "continue-on-error: true (12-OPS-001)"
            )
    assert "exit-code: 1" in content
    assert "--exit-code 1" in content


@pytest.mark.unit
def test_dependabot_config_exists() -> None:
    """.github/dependabot.yml exists with github-actions and uv ecosystems."""
    dependabot_path = _PROJECT_ROOT / ".github" / "dependabot.yml"
    assert dependabot_path.exists(), "dependabot.yml not found"
    content = dependabot_path.read_text(encoding="utf-8")
    assert "github-actions" in content
    assert "uv" in content


# ---------------------------------------------------------------------------
# Dependabot configuration — PR #7 / PR #8 / PR #16 prevention
# ---------------------------------------------------------------------------
# PR #7 proposed major-version GitHub Action upgrades (actions/checkout v4->v7,
# astral-sh/setup-uv v5->v10) as auto-filed Dependabot PRs. PR #8 proposed
# Django 5->6 and django-prometheus 2.5.0->2.6.0.dev22; PR #16 proposed
# django 5.2.17->6.1.2 against the declared ``django<6.0``.
#
# The dependabot.yml must gate these behind manual review. The schema key is
# ``update-types`` (plural, a list); the former singular ``update-type`` is not
# part of the schema and — because an ``allow`` rule without ``update-types``
# permits EVERY update type — it left the restriction inert.
#
# ``update-types`` never applies to security updates, so the binding guarantee
# that the locked dependency set stays inside the pyproject.toml bounds is a
# test over ``uv.lock`` (see section "Declared dependency bounds" below). It
# runs in the CI ``test`` job, so no extra ci.yml step is needed.

# Valid Dependabot ``update-types`` values used by this repository.
_UPDATE_TYPE_MINOR = "version-update:semver-minor"
_UPDATE_TYPE_PATCH = "version-update:semver-patch"
_UPDATE_TYPE_MAJOR = "version-update:semver-major"

# PEP 503: collapse runs of ``-``, ``_`` and ``.`` into a single ``-``.
_DISTRIBUTION_NAME_SEPARATOR_RE = re.compile(r"[-_.]+")

# A PEP 440-ish version token as it appears in uv.lock (``5.2.17``, ``1.0``).
_RELEASE_SEGMENT_RE = re.compile(r"^\d+(?:\.\d+)*$")


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


def _flatten_update_types(rule_entries: list) -> set[str]:
    """Return every value in the ``update-types`` lists of Dependabot rule entries."""
    flattened: set[str] = set()
    for item in rule_entries:
        if isinstance(item, dict):
            flattened.update(item.get("update-types", []))
    return flattened


def _assert_no_singular_update_type_key(
    rule_entries: list, *, where: str
) -> None:
    """Fail if any rule entry uses the invalid singular ``update-type`` key.

    Dependabot's schema key is ``update-types`` (plural, a list). A singular key
    is silently ignored, and because an ``allow`` rule that omits ``update-types``
    permits ALL update types, a restriction written that way is inert — a major
    bump is then auto-filed (PR #16). The comment on the whitelist covers a
    whole-file scan, which reports every offending ``dependency-name``.
    """
    singular = [item for item in rule_entries if isinstance(item, dict) and "update-type" in item]
    assert not singular, (
        f"{where} uses the invalid singular `update-type` key. Dependabot's schema "
        "key is `update-types` (a list); when `update-types` is omitted from an "
        "`allow` rule Dependabot allows ALL update types, so this restriction "
        f"is inert. Offending entries: {singular}"  # noqa: E501
    )


def _assert_allow_is_minor_patch_only(entry: dict, *, where: str) -> None:
    """Assert an entry's ``allow`` rules flatten to minor+patch and never major."""
    allow = entry.get("allow", [])
    assert allow, f"{where} must specify an `allow` list"
    _assert_no_singular_update_type_key(allow, where=f"{where} `allow`")
    update_types = _flatten_update_types(allow)
    assert _UPDATE_TYPE_MAJOR not in update_types, (
        f"{where} must not allow major-version updates"
    )
    assert _UPDATE_TYPE_MINOR in update_types, (
        f"{where} must allow semver-minor updates"
    )
    assert _UPDATE_TYPE_PATCH in update_types, (
        f"{where} must allow semver-patch updates"
    )


def _find_ignore_entry(entry: dict, dependency_name: str) -> list[dict]:
    """Return the ``ignore`` rules of a Dependabot entry for one dependency."""
    ignore_list = entry.get("ignore", [])
    assert isinstance(ignore_list, list), "Dependabot `ignore` must be a list"
    return [
        item
        for item in ignore_list
        if isinstance(item, dict) and item.get("dependency-name") == dependency_name
    ]


@pytest.mark.unit
def test_dependabot_uses_plural_update_types_everywhere() -> None:
    """No dependabot.yml rule uses the invalid singular ``update-type`` key."""
    from ruamel.yaml import YAML

    text = _read(".github", "dependabot.yml")
    document = YAML(typ="safe").load(text)
    violations: list[str] = []
    for index, entry in enumerate(document.get("updates", [])):
        if not isinstance(entry, dict):
            continue
        label = f"updates[{index}] ({entry.get('package-ecosystem')})"
        for section in ("allow", "ignore"):
            rules = entry.get(section, [])
            if not isinstance(rules, list):
                continue
            for rule in rules:
                if isinstance(rule, dict) and "update-type" in rule:
                    violations.append(f"{label}.{section}: {rule}")
    assert not violations, (
        "`update-type` is not a Dependabot schema key — use `update-types` (a "
        "list). An `allow` rule without `update-types` allows all update types, "
        "so the restriction is inert and majors get auto-filed:\n"
        + "\n".join(violations)
    )
    # Load-bearing for the comment above: the scan would pass vacuously.
    broken = {"updates": [{"allow": [{"dependency-name": "x", "update-type": "y"}]}]}
    assert any("update-type" in rule for rule in broken["updates"][0]["allow"])


@pytest.mark.unit
def test_dependabot_uv_restricted_to_semver_minor_patch() -> None:
    """The uv ecosystem only allows semver-minor and semver-patch updates.

    Blocks major-version bumps (e.g., Django 5->6) from being auto-filed — the
    root cause of PR #8 and PR #16. Security updates are not subject to
    ``update-types``; their bound is enforced by the uv.lock guard below.
    """
    entry = _find_dependabot_entry("uv")
    assert entry is not None, "uv ecosystem entry not found in dependabot.yml"
    _assert_allow_is_minor_patch_only(entry, where="uv ecosystem")


@pytest.mark.unit
def test_dependabot_django_prometheus_prerelease_ignored() -> None:
    """The uv ecosystem ignores pre-release updates for django-prometheus.

    Even if a pre-release version type slips through the (security-update
    exempt) allow filter, this `ignore` entry blocks it.
    """
    entry = _find_dependabot_entry("uv")
    assert entry is not None
    prometheus_ignores = _find_ignore_entry(entry, "django-prometheus")
    assert prometheus_ignores, "django-prometheus must appear in the uv ignore list"
    all_update_types = _flatten_update_types(prometheus_ignores)
    assert "version-update:semver-prerelease" in all_update_types, (
        "django-prometheus must ignore pre-release updates"
    )


@pytest.mark.unit
def test_dependabot_build_actions_restricted_to_minor_patch() -> None:
    """The build-actions entry only allows semver-minor and semver-patch.

    Major-version action upgrades (actions/checkout v4->v7, astral-sh/setup-uv
    v5->v10) require manual review (12-OPS-017) — root cause of PR #7.
    """
    entry = _find_dependabot_entry("github-actions", "build-actions")
    assert entry is not None, "build-actions github-actions entry not found"
    _assert_allow_is_minor_patch_only(entry, where="build-actions entry")


# ---------------------------------------------------------------------------
# Declared dependency bounds (DEP-003) — defence in depth for Dependabot
# ---------------------------------------------------------------------------
# Dependabot documents that ``update-types`` never applies to security updates,
# so dependabot.yml cannot guarantee that a proposed bump stays inside the
# pyproject.toml upper bound. Two guards below close that gap:
#   * every bounded dependency has an explicit major pin in the uv `ignore` list
#     (so the dependabot.yml intent is visible per dependency), and
#   * the resolved uv.lock stays inside every declared bound (the enforceable
#     guarantee — this is what PR #16's lock violated).


def _normalise_distribution_name(name: str) -> str:
    """Normalise a requirement name to its PEP 503 form (extras stripped)."""
    base = name.partition("[")[0]
    return _DISTRIBUTION_NAME_SEPARATOR_RE.sub("-", base).lower().strip("-")


def _lower_bound(requirement: str) -> str | None:
    """Return the version of the first ``>=`` clause in a requirement."""
    match = re.search(r">=\s*([0-9][0-9.]*)", requirement)
    return match.group(1) if match else None


def _upper_bound(requirement: str) -> str | None:
    """Return the version of the first ``<`` clause in a requirement."""
    match = re.search(r"<\s*([0-9][0-9.]*)", requirement)
    return match.group(1) if match else None


def _is_next_major_bound(requirement: str) -> bool:
    """Return ``True`` when ``<N.0`` excludes the next major above ``>=M``.

    ``>=5.2.16,<6.0`` is the typical next-major convention, and so is the
    ``>=10.4.0,<14.0`` form whose lower bound starts several majors below the
    ceiling (majors 10-13 are inside; 14 is excluded). ``<0.20`` / ``<0.19``
    only exclude a 0.x line, never a major.
    """
    upper = _upper_bound(requirement)
    if upper is None:
        return False
    parts = [int(part) for part in upper.split(".")]
    if len(parts) != 2 or parts[1] != 0 or parts[0] < 1:
        return False
    lower = _lower_bound(requirement)
    lower_release = _release_segments(lower) if lower is not None else None
    if lower_release is None:
        return parts[0] >= 2
    return lower_release[0] <= parts[0] - 1


@dataclass(frozen=True)
class _BoundedDependency:
    """A direct dependency bound by a PEP 440 upper (``<``) bound."""

    name: str
    requirement: str

    @property
    def pins_major(self) -> bool:
        """Return ``True`` when the upper bound excludes a major version."""
        return _is_next_major_bound(self.requirement)


def _pyproject_document() -> dict:
    """Parse pyproject.toml from the repository root."""
    document = tomllib.loads(_read("pyproject.toml"))
    assert isinstance(document, dict), "pyproject.toml must parse to a mapping"
    return document


def _declared_requirements() -> list[str]:
    """Return ``[project].dependencies`` + ``[dependency-groups].dev`` strings."""
    document = _pyproject_document()
    project_requirements = list(document.get("project", {}).get("dependencies", []))
    dev_requirements = list(
        document.get("dependency-groups", {}).get("dev", [])
    )
    return project_requirements + dev_requirements


def _split_requirement(requirement: str) -> tuple[str, str]:
    """Split a PEP 508 requirement into ``(normalised name, specifier text)``."""
    match = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*(?:\[[^\]]*\])?)\s*(.*)$", requirement)
    assert match is not None, f"unparseable requirement: {requirement!r}"
    return _normalise_distribution_name(match.group(1)), match.group(2)


def _bounded_dependencies() -> dict[str, _BoundedDependency]:
    """Return every declared dependency that carries an upper bound, by name."""
    bounded: dict[str, _BoundedDependency] = {}
    for requirement in _declared_requirements():
        name, specifier = _split_requirement(requirement)
        if _upper_bound(specifier) is not None:
            bounded[name] = _BoundedDependency(name=name, requirement=requirement)
    return bounded


def _lock_versions(lock_text: str) -> dict[str, str]:
    """Return ``{normalised name: version}`` for every package in uv.lock."""
    lock = tomllib.loads(lock_text)
    versions: dict[str, str] = {}
    for package in lock.get("package", []):
        if isinstance(package, dict) and "name" in package and "version" in package:
            versions[_normalise_distribution_name(package["name"])] = package["version"]
    return versions


def _release_segments(version: str) -> tuple[int, ...] | None:
    """Return the numeric release tuple of a version, or ``None`` if not numeric.

    uv.lock pins registry releases, so pre-release suffixes are unexpected; a
    non-numeric version makes the bound check inconclusive rather than wrong.
    """
    match = re.match(r"^([0-9]+(?:\.[0-9]+)*)", version)
    if match is None:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def _bound_violation(name: str, version: str, requirement: str) -> str | None:
    """Return a description of the first violated bound, or ``None`` if compliant."""
    release = _release_segments(version)
    if release is None:
        return None
    lower = _lower_bound(requirement)
    if lower is not None:
        lower_release = _release_segments(lower)
        assert lower_release is not None, f"unparseable lower bound in {requirement!r}"
        if release < lower_release:
            return f"{version} is below the declared >= {lower} bound"
    upper = _upper_bound(requirement)
    if upper is not None:
        upper_release = _release_segments(upper)
        assert upper_release is not None, f"unparseable upper bound in {requirement!r}"
        if not release < upper_release:
            return f"{version} is outside the declared < {upper} bound"
    return None


def _lock_bound_violations(
    lock_text: str, bounded: dict[str, _BoundedDependency]
) -> list[str]:
    """Return one message per bounded dependency the lock resolves out of bounds.

    Dependencies absent from the lock are skipped: this guard covers the
    resolved set only, and a missing declaration is a `uv lock` error already.
    """
    versions = _lock_versions(lock_text)
    violations: list[str] = []
    for name, dependency in sorted(bounded.items()):
        version = versions.get(name)
        if version is None:
            continue
        violation = _bound_violation(name, version, dependency.requirement)
        if violation is not None:
            violations.append(
                f"{name}: {violation} (pyproject.toml: {dependency.requirement})"
            )
    return violations


@pytest.mark.unit
def test_dependabot_uv_pins_major_for_bounded_dependencies() -> None:
    """Every dependency bounded below a major in pyproject.toml is major-pinned.

    Derived from ``[project].dependencies`` + ``[dependency-groups].dev``: each
    requirement with a ``<N.0`` upper bound (``django>=5.2.16,<6.0``) and each
    dependency whose bound spans the current major (``pillow>=10.4.0,<14.0``)
    must appear in the uv entry's ``ignore`` list with ``semver-major``.
    Removing the ignore entry for a bounded dependency turns this red.
    """
    entry = _find_dependabot_entry("uv")
    assert entry is not None, "uv ecosystem entry not found in dependabot.yml"
    ignore_list = entry.get("ignore", [])
    assert isinstance(ignore_list, list), "uv `ignore` must be a list"
    _assert_no_singular_update_type_key(ignore_list, where="uv `ignore`")

    major_bounded = {
        name: dependency
        for name, dependency in _bounded_dependencies().items()
        if dependency.pins_major
    }
    assert major_bounded, "pyproject.toml declares no next-major upper bounds"

    pinned_names = {
        _normalise_distribution_name(item["dependency-name"])
        for item in ignore_list
        if isinstance(item, dict) and "dependency-name" in item
    }
    unpinned = sorted(name for name in major_bounded if name not in pinned_names)
    assert not unpinned, (
        "these pyproject.toml dependencies declare a next-major upper bound but "
        "have no pin in the uv `ignore` list (Dependabot's `allow`/`update-types` "
        "does not apply to security updates, so the pin is the defence-in-depth "
        f"layer): {unpinned}"
    )

    # Every derived pin enforces semver-major.
    missing_major: list[str] = []
    for name in major_bounded:
        rules = _find_ignore_entry(entry, name)
        if _UPDATE_TYPE_MAJOR not in _flatten_update_types(rules):
            missing_major.append(name)
    assert not missing_major, (
        "these next-major-bounded dependencies have an `ignore` entry without "
        f"`{_UPDATE_TYPE_MAJOR}`: {missing_major}"
    )


@pytest.mark.unit
def test_major_bound_derivation_contract() -> None:
    """Pin the derivation contract behind the per-dependency major pins.

    ``>=10.4.0,<14.0`` spans majors 10-13, so major 14 is excluded (pin it).
    ``>=5.2.16,<6.0`` is the plain next-major case. ``<0.20`` excludes a 0.x
    line, not a major; a requirement without an upper bound is not bounded.
    """
    assert _BoundedDependency("pillow", "pillow>=10.4.0,<14.0").pins_major
    assert _BoundedDependency("django", "django>=5.2.16,<6.0").pins_major
    assert not _BoundedDependency("ruamel-yaml", "ruamel.yaml>=0.19.1,<0.20").pins_major
    assert not _BoundedDependency("ruff", "ruff>=0.16.10").pins_major

    bounded = _bounded_dependencies()
    assert "pillow" in bounded, "pillow must be derived as a bounded dependency"
    assert "django" in bounded
    assert "psycopg" in bounded, "psycopg[binary] must normalise to psycopg"
    assert "bandit" in bounded, "dev-group bounds must be derived too"
    # Unbounded dev tools must not be derived (they keep receiving majors via
    # the corrected global `allow`; no per-dependency pin is expected).
    for unbounded in ("ruff", "pytest", "basedpyright", "djlint", "pip-audit"):
        assert unbounded not in bounded, f"{unbounded} must not be derived as bounded"


@pytest.mark.unit
def test_dependency_bounds_are_respected_by_uv_lock() -> None:
    """Every declared upper bound is satisfied by the resolved uv.lock.

    This is the enforceable "never ship Django 6 while declaring ``django<6.0``"
    guarantee: it runs in the CI ``test`` job on every PR, so a Dependabot
    update (security or version) that resolves outside a bound fails the run.
    ``uv lock --check`` alone only proves the lock is up to date with the
    requirements; it does not re-assert the bound on a Dependabot-authored lock.
    """
    violations = _lock_bound_violations(_read("uv.lock"), _bounded_dependencies())
    assert not violations, (
        "uv.lock resolves outside the pyproject.toml upper bounds — the lock "
        "violates the dependency policy that blocked PR #16:\n"
        + "\n".join(violations)
    )


@pytest.mark.unit
def test_lock_bound_guard_detects_an_out_of_policy_lock() -> None:
    """The lock-bound predicate fails on a lock that resolves inside another major.

    A guard that only passes today's lock is not a guard. This feeds the same
    predicate the PR #16 shape (``django 6.1.2`` against ``django>=5.2.16,<6.0``)
    so the documented failure mode is proven detectable.
    """
    bounded = _bounded_dependencies()
    pr_16_lock = (
        '[[package]]\nname = "django"\nversion = "6.1.2"\n'
        '[[package]]\nname = "django-mptt"\nversion = "0.18.0"\n'
    )
    violations = _lock_bound_violations(pr_16_lock, bounded)
    assert any(v.startswith("django: ") for v in violations), violations
    assert not any(v.startswith("django-mptt: ") for v in violations), violations
    assert any("< 6.0" in v for v in violations), violations

    lower_violations = _lock_bound_violations(
        '[[package]]\nname = "django"\nversion = "5.1.0"\n', bounded
    )
    assert any(">= 5.2.16" in v for v in lower_violations), lower_violations

    compliant = '[[package]]\nname = "django"\nversion = "5.2.17"\n'
    assert not _lock_bound_violations(compliant, bounded)


@pytest.mark.unit
def test_dependabot_security_actions_allows_all_types() -> None:
    """The security-actions entry allows all update types (incl. majors).

    trivy-action and codeql upload-sarif need timely major-version upgrades for
    CVE coverage. Its ``allow`` entries carry only ``dependency-name``: no
    ``update-types`` (plural) and no invalid singular ``update-type``, which
    means every update type is allowed.
    """
    entry = _find_dependabot_entry("github-actions", "security-actions")
    assert entry is not None, "security-actions github-actions entry not found"
    allow = entry.get("allow", [])
    assert allow, "security-actions entry must specify an `allow` list"
    _assert_no_singular_update_type_key(allow, where="security-actions `allow`")
    for item in allow:
        assert "update-types" not in item, (
            f"security-actions allow entry must not restrict update types: {item}"
        )


@pytest.mark.unit
def test_dockerfile_has_sbom_generation() -> None:
    """Dockerfile builder stage generates a CycloneDX SBOM (via syft)."""
    content = _read("docker", "Dockerfile")
    assert "sbom" in content.lower()
    assert "syft" in content.lower() or "cyclonedx" in content.lower()


@pytest.mark.unit
def test_dockerfile_copies_sbom_to_runtime() -> None:
    """Builder-stage SBOM is copied into the runtime image."""
    content = _read("docker", "Dockerfile")
    assert "sbom.cyclonedx.json" in content


@pytest.mark.unit
def test_build_job_has_trivy_image_scan() -> None:
    """Build job scans the Docker image with Trivy."""
    content = _read(".github", "workflows", "ci.yml")
    assert "Scan Docker image for vulnerabilities" in content
    assert "trivy" in content.lower()


@pytest.mark.unit
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


@pytest.mark.unit
def test_trivy_image_scan_ignores_unfixed() -> None:
    """The Trivy image scan must set ignore-unfixed: true.

    Mirrors the existing fs-mode Trivy scan in the security job (which already
    has ``ignore-unfixed: true``). Only vulnerabilities with known fixes are
    reported; CVEs without an upstream fix do not block CI.
    """
    step = _build_step("Scan Docker image for vulnerabilities")
    config = step.get("with", {})
    assert config.get("ignore-unfixed") is True, (
        "the Trivy image scan in the build job must set ignore-unfixed: true "
        "to match the fs-mode scan policy (12-OPS-013)"
    )


# ---------------------------------------------------------------------------
# Trivy SARIF severity gate (12-OPS-013)
# ---------------------------------------------------------------------------
# `aquasecurity/trivy-action` unsets TRIVY_SEVERITY when `format: sarif` unless
# `limit-severities-for-sarif: true` is also set, so the `severity:
# CRITICAL,HIGH` argument is silently inert on both SARIF steps: the gate failed
# on *any* severity with a fix while the job log recorded no CVE. The flag makes
# the CRITICAL/HIGH filter effective (a relaxation for LOW/MEDIUM findings) and
# keeps `exit-code: 1` as the blocker.


def _sarif_severity_gate_violations(step: dict) -> list[str]:
    """Return a list of policy violations for one Trivy SARIF step's ``with:``.

    An empty list means the step is compliant. Split out from the guard so the
    negative-control test can prove the predicate detects a missing
    ``limit-severities-for-sarif`` instead of only passing today's ci.yml.
    """
    config = step.get("with", {})
    violations: list[str] = []
    if config.get("format") != "sarif":
        violations.append(f"format must be 'sarif', got {config.get('format')!r}")
    if config.get("limit-severities-for-sarif") is not True:
        violations.append(
            "limit-severities-for-sarif must be true so `severity` is honoured "
            f"in SARIF mode, got {config.get('limit-severities-for-sarif')!r}"
        )
    if config.get("exit-code") != 1:
        violations.append(f"exit-code must be 1, got {config.get('exit-code')!r}")
    if step.get("continue-on-error") is True:
        violations.append("continue-on-error must not be true")
    return violations


@pytest.mark.unit
def test_trivy_sarif_steps_limit_severities_and_stay_blocking() -> None:
    """Both Trivy SARIF steps honour CRITICAL/HIGH and remain blocking.

    The security job's loop in ``test_security_steps_are_blocking`` only guards
    ``continue-on-error``; the build job's image scan is otherwise unguarded, so
    the per-step policy is asserted here by explicit step name (12-OPS-013).
    """
    targets = (
        ("build", "Scan Docker image for vulnerabilities"),
        ("security", "Run Trivy vulnerability scanner in fs mode"),
    )
    for job_name, step_name in targets:
        violations = _sarif_severity_gate_violations(_step_by_name(job_name, step_name))
        assert not violations, (
            f"ci.yml {job_name}/{step_name} violates the Trivy SARIF gate policy "
            f"(12-OPS-013): " + "; ".join(violations)
        )


@pytest.mark.unit
def test_trivy_sarif_gate_guard_detects_a_missing_flag() -> None:
    """The SARIF gate predicate fails when ``limit-severities-for-sarif`` is absent.

    A guard that only passes today's file is not a guard. This feeds the same
    predicate a representative-but-broken step mapping and asserts every
    violation class is detected, so removing the flag (or the blocking
    ``exit-code: 1``) from either named step turns the guard red.
    """
    config = {
        "format": "sarif",
        "output": "trivy-image-results.sarif",
        "exit-code": 1,
    }
    violations = _sarif_severity_gate_violations({"name": "synthetic", "with": config})
    assert any("limit-severities-for-sarif" in v for v in violations), (
        "the predicate must detect a missing limit-severities-for-sarif flag"
    )

    relaxed = {**config, "limit-severities-for-sarif": False, "format": "table"}
    assert _sarif_severity_gate_violations({"with": relaxed})
    assert _sarif_severity_gate_violations(
        {"continue-on-error": True, "with": {**config, "limit-severities-for-sarif": True}}
    )

    # The compliant mapping is clean — the predicate is not vacuously true.
    assert not _sarif_severity_gate_violations(
        {"with": {**config, "limit-severities-for-sarif": True}}
    )


# ---------------------------------------------------------------------------
# Trivy image-scan reachability (12-OPS-013)
# ---------------------------------------------------------------------------
# The image scan ran under `if: always()` against the mutable `:ci` tag. When
# the build failed, the step scanned a *previously pushed* `:ci` image and
# reported a CRITICAL/HIGH verdict for CVEs that did not belong to the run — the
# incident signature in CI run 42190885870. The scan must run only after a
# successful build, and must scan the digest this run pushed (the immutable
# identity of the built image), never the mutable `:ci` tag.

# `:<tag>` suffix on a registry reference (outside an `@sha256:` digest), e.g.
# `ghcr.io/o/r:ci`. Only the final path segment can carry a tag.
_REGISTRY_TAG_SUFFIX_RE = re.compile(r":[A-Za-z0-9_][A-Za-z0-9_.-]*$")


def _image_scan_reachability_violations(scan_step: dict, build_step: dict) -> list[str]:
    """Return policy violations for the build job's Trivy image scan step.

    An empty list means the scan is reachable only after a successful build and
    addresses the digest that build pushed. Split out from the guard so the
    negative-control tests can prove the predicate detects an ``always()`` gate
    and a mutable ``:ci`` reference instead of only passing today's ci.yml.
    """
    violations: list[str] = []

    condition = scan_step.get("if")
    if condition is not None:
        gate = str(condition).strip()
        if "always()" in gate or "!cancelled()" in gate or gate.startswith("!"):
            violations.append(
                f"the scan must not run when the build did not succeed; got if: {gate!r}"
            )
    if scan_step.get("continue-on-error") is True:
        violations.append("continue-on-error must not be true")

    build_id = build_step.get("id")
    image_ref = str(scan_step.get("with", {}).get("image-ref", ""))
    if not build_id:
        violations.append("the build step must declare an id to expose its digest")
    elif f"steps.{build_id}.outputs.digest" not in image_ref:
        violations.append(
            "image-ref must address steps.<build id>.outputs.digest so the scan "
            f"sees the image this run built; got {image_ref!r}"
        )

    if "@" not in image_ref:
        violations.append(
            f"image-ref must be pinned to a digest (@sha256:...), got {image_ref!r}"
        )
    if _REGISTRY_TAG_SUFFIX_RE.search(image_ref.split("@", 1)[0]):
        violations.append(
            f"image-ref must not carry a mutable tag suffix, got {image_ref!r}"
        )
    return violations


@pytest.mark.unit
def test_trivy_image_scan_runs_only_after_a_successful_build() -> None:
    """The image scan is gated on a successful build and scans the pushed digest.

    Under the default ``success()`` gate a failed build has no digest, so the
    step is skipped instead of scanning a stale ``:ci`` image (12-OPS-013).
    """
    scan_step = _build_step("Scan Docker image for vulnerabilities")
    build_step = _build_step("Build and push Docker image")
    violations = _image_scan_reachability_violations(scan_step, build_step)
    assert not violations, (
        "ci.yml build job image scan violates the reachability policy "
        "(12-OPS-013): " + "; ".join(violations)
    )


@pytest.mark.unit
def test_image_scan_reachability_guard_detects_an_always_gated_step() -> None:
    """The guard fails on an ``always()`` gate over a mutable ``:ci`` reference."""
    violations = _image_scan_reachability_violations(
        {
            "name": "synthetic",
            "if": "always()",
            "with": {"image-ref": "ghcr.io/x/y:ci"},
        },
        {"id": "build_image"},
    )
    assert any("did not succeed" in v for v in violations), violations
    assert any(":ci" in v for v in violations), violations


@pytest.mark.unit
def test_image_scan_reachability_guard_detects_a_mutable_tag_ref() -> None:
    """The guard fails a correct gate that scans the mutable ``:ci`` tag."""
    violations = _image_scan_reachability_violations(
        {"name": "synthetic", "with": {"image-ref": "ghcr.io/x/y:ci"}},
        {"id": "build_image"},
    )
    assert violations
    assert any("digest" in v for v in violations), violations
    assert any("tag suffix" in v for v in violations), violations


@pytest.mark.unit
def test_build_job_summarises_trivy_findings_after_upload() -> None:
    """A read-only step pretty-prints the SARIF right after it is uploaded.

    Without it a failing image scan reports only ``Process completed with exit
    code 1`` with no finding lines, so the job is not self-diagnosing
    (12-OPS-013). The summary must (a) follow ``Upload Docker image scan
    results``, (b) never fail the job itself, and (c) not re-scan, which would
    duplicate the upload-artifact name and 409 on ``overwrite: false``.
    """
    names = [
        step.get("name") for step in _job_steps("build") if isinstance(step, dict)
    ]
    assert "Upload Docker image scan results" in names, (
        "the build job must still upload trivy-image-results SARIF"
    )
    assert "Summarise Trivy image findings" in names, (
        "the build job must summarise the Trivy SARIF into the job log (12-OPS-013)"
    )
    assert names.index("Summarise Trivy image findings") == (
        names.index("Upload Docker image scan results") + 1
    ), "the summary must run immediately after the SARIF upload"
    summary = _step_by_name("build", "Summarise Trivy image findings")
    assert "uses" not in summary, (
        "the summary must not invoke an action or a second Trivy scan"
    )
    assert summary.get("continue-on-error") is not True
    assert "trivy-image-results.sarif" in summary.get("run", "")


@pytest.mark.unit
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


@pytest.mark.unit
def test_dockerfile_removes_system_setuptools() -> None:
    """The runtime stage removes system-level setuptools via filesystem deletion.

    ``python:3.14-slim`` ships ``setuptools`` 70.3.0 in system site-packages,
    which is vulnerable to CVE-2025-47273 (fixed in 78.1.1) and
    CVE-2026-59890 (fixed in 83.0.0). setuptools is not needed at runtime —
    the venv at ``/opt/venv`` is self-contained. Removing it eliminates the
    HIGH-severity findings from the Trivy image scan.

    Uses ``rm -rf`` against the site-packages directory rather than
    ``pip uninstall`` because pip's metadata does not track the base image's
    system-level installation, making ``pip uninstall`` a silent no-op.
    """
    content = _read("docker", "Dockerfile")
    assert "setuptools" in content, (
        "Dockerfile must reference setuptools so the removal step is present"
    )
    assert "rm -rf" in content, (
        "Dockerfile runtime stage must remove setuptools via filesystem deletion (rm -rf), "
        "not pip uninstall (which is a no-op for system-level packages)"
    )
    assert "pip uninstall" not in content, (
        "Dockerfile must not use pip uninstall for setuptools removal — "
        "it is a no-op for the base image's system-level installation"
    )


@pytest.mark.unit
def test_dockerfile_has_no_dead_cache_bust_arg() -> None:
    """The builder stage has no dead CACHEBUST ARG.

    A previous revision declared ``ARG CACHEBUST=1`` but never referenced it
    in a subsequent ``COPY``: a dead cache-bust argument has no effect on cache
    invalidation, and must not be reintroduced. BuildKit's content-addressed
    layer cache needs no manual cache-bust argument at all — correct input
    hashing invalidates the affected layers automatically. See
    ``test_ci_image_coordinate.py`` for the build-cache backend policy.
    """
    content = _read("docker", "Dockerfile")
    assert "ARG CACHEBUST" not in content, (
        "Dockerfile must not declare a dead CACHEBUST ARG — BuildKit's "
        "content-addressed layer cache needs no manual cache-bust argument"
    )


@pytest.mark.unit
def test_gitleaks_config_exists() -> None:
    """.gitleaks.toml exists for allowlist configuration."""
    gitleaks_path = _PROJECT_ROOT / ".gitleaks.toml"
    assert gitleaks_path.exists(), ".gitleaks.toml not found"
    content = gitleaks_path.read_text(encoding="utf-8")
    assert "allowlists" in content


@pytest.mark.unit
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


def _deploy_check_job() -> dict:
    """Return the parsed ``deploy-check`` job mapping from ci.yml.

    Replaces the previous ``content.index`` slicing that assumed the job was
    the last definition in the file — a fragile assumption on text ordering.
    Structural parsing instead navigates ``jobs.deploy-check`` directly.
    """
    return _job_by_name("deploy-check")


@pytest.mark.unit
def test_ci_deploy_check_uses_prod_settings() -> None:
    """The deploy-check job runs check --deploy against config.settings.prod (not test)."""
    job = _deploy_check_job()
    env = job.get("env", {})
    assert isinstance(env, dict), "deploy-check job must declare an env block"
    settings_module = env.get("DJANGO_SETTINGS_MODULE")
    assert settings_module == "config.settings.prod", (
        f"deploy-check job must set DJANGO_SETTINGS_MODULE to "
        f"config.settings.prod, got {settings_module!r} (12-OPS-001)"
    )
    assert settings_module != "config.settings.test", (
        "deploy-check job must not use config.settings.test (12-OPS-001)"
    )


@pytest.mark.unit
def test_ci_deploy_check_fails_on_warnings() -> None:
    """The deploy-check step uses --fail-level WARNING and is not continue-on-error."""
    job = _deploy_check_job()
    steps = job.get("steps", [])
    assert isinstance(steps, list), "deploy-check job must declare steps"
    for step in steps:
        if isinstance(step, dict):
            assert step.get("continue-on-error") is not True, (
                f"deploy-check step {step.get('name', '<unnamed>')} must not set "
                "continue-on-error: true (12-OPS-001)"
            )
    deploy_check_run = next(
        (
            step.get("run", "")
            for step in steps
            if isinstance(step, dict)
            and "check --deploy" in str(step.get("run", ""))
        ),
        None,
    )
    assert deploy_check_run is not None, (
        "deploy-check job must have a step running check --deploy"
    )
    assert "--fail-level WARNING" in deploy_check_run, (
        "deploy-check step must use --fail-level WARNING"
    )


@pytest.mark.unit
def test_ci_deploy_check_sets_valid_secret_key() -> None:
    """The deploy-check job sets DJANGO_SECRET_KEY to a 50+ char non-secret literal."""
    job = _deploy_check_job()
    env = job.get("env", {})
    assert isinstance(env, dict), "deploy-check job must declare an env block"
    secret_key_value = env.get("DJANGO_SECRET_KEY")
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
    for step in _job_steps("security"):
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


@pytest.mark.unit
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


@pytest.mark.integration
@pytest.mark.slow
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


@pytest.mark.unit
def test_bandit_in_dev_deps() -> None:
    """pyproject.toml lists a SAST tool (bandit or semgrep) in dev dependencies."""
    content = _read("pyproject.toml")
    assert "bandit" in content or "semgrep" in content


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
def test_build_job_has_security_events_permission() -> None:
    """The build job grants security-events: write for upload-sarif.

    The build job uploads Trivy SARIF results via
    github/codeql-action/upload-sarif, which requires the ``security-events: write``
    permission. Without it, the ``Upload Docker image scan results`` step fails
    with a 403 Forbidden. ``actions: read`` is also required for
    actions/upload-artifact and workflow run metadata.
    """
    build = _job_by_name("build")
    permissions = build.get("permissions", {})
    assert isinstance(permissions, dict), (
        "build job must declare a permissions block (12-OPS-013)"
    )
    assert permissions.get("security-events") == "write", (
        "build job must grant security-events: write for upload-sarif (12-OPS-013)"
    )
    assert permissions.get("actions") == "read", (
        "build job must grant actions: read (required by upload-artifact and "
        "workflow metadata)"
    )


@pytest.mark.unit
def test_build_job_trivy_action_disables_cache() -> None:
    """The Trivy image scan step sets cache: false.

    The ``aquasecurity/trivy-action`` defaults its ``cache`` input to ``true``,
    which restores a date-keyed cache from a prior run. A stale cache serves
    outdated SARIF results (e.g. msgpack 1.1.2 when lockfile says 1.2.2) instead
    of scanning the freshly-built image. Setting ``cache: false`` forces a fresh
    scan on every run.
    """
    step = _build_step("Scan Docker image for vulnerabilities")
    config = step.get("with", {})
    assert config.get("cache") is False, (
        "the Trivy image scan step must set cache: false to prevent stale cache"
        " restoration from prior runs (12-OPS-013)"
    )
