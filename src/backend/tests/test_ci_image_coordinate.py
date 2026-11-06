"""
One image coordinate, the build cache backend and workflow concurrency
(12-OPS-009).

Invariant now guarded: the build cache is the GitHub Actions backend
(``type=gha``) with **one** stable ``scope`` shared by ``cache-from`` and
``cache-to``, and no branch-derived string may reach a Docker reference. A
``type=registry`` cache ref interpolated ``github.ref_name`` — for a
``pull_request`` event that is ``<pr_number>/merge``, and ``/`` is not a legal
Docker tag character, so every PR build aborted with ``invalid reference
format``.

Historical context (short): before this guard there were four live
``ghcr.io/<owner>/<repo>`` strings and the registry build cache was silently
split (``cache-from`` named one repo, ``cache-to`` another). The coordinate was
then briefly unified to ``mko-bazuna/mko_bazuna`` — a namespace no GitHub
account owns, so GHCR rejected every push with ``denied: not_found: owner not
found``. The canonical coordinate is ``ghcr.io/manicko/mko_bazuna``: GHCR has
no container-registry namespace distinct from the GitHub owner.

These are structural tests over the workflow files and the compose/env
templates, following the ``test_docs_ci_parity.py`` precedent. The build-cache
guards parse ``ci.yml`` with ``yaml.safe_load`` (PyYAML is an application
dependency) so they read the real job config rather than substring-matching
the file; the coordinate and concurrency guards stay string-level. They do
**not** execute any workflow.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

# Resolve repository root by searching upward for pyproject.toml. pyproject.toml
# exists only at the repo root, so this is robust to the Docker test CWD.
_ROOT = Path(__file__).resolve().parent
while not (_ROOT / "pyproject.toml").exists():
    _ROOT = _ROOT.parent

_CI_YML = _ROOT / ".github" / "workflows" / "ci.yml"
_DEPLOY_YML = _ROOT / ".github" / "workflows" / "deploy.yml"
_RESTORE_TEST_YML = _ROOT / ".github" / "workflows" / "restore-test.yml"
_PROD_COMPOSE = _ROOT / "docker-compose.prod.yml"
_ENV_PROD_EXAMPLE = _ROOT / ".env.prod.example"

# The canonical GHCR coordinate. GHCR namespaces packages by the owning GitHub
# account; the repository is `manicko/mko_bazuna`, so the only valid coordinate
# is `ghcr.io/manicko/mko_bazuna`. A prior revision of this guard unified the
# coordinate to `mko-bazuna/mko_bazuna`, but no GitHub account named
# `mko-bazuna` exists — GHCR rejects every push with
# `denied: not_found: owner not found`. `manicko/mko_bazuna` is both the GitHub
# repository path and the container-registry namespace; they are one and the same.
_CANONICAL_REPOSITORY = "manicko/mko_bazuna"
_CANONICAL_COORDINATE = f"ghcr.io/{_CANONICAL_REPOSITORY}"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# --- cache parity ----------------------------------------------------------
# The guards below are pure predicates over the build job's parsed ``with:``
# mapping, in the style of ``apps/core/tests/test_ci_security.py``. A predicate
# plus negative controls can go red; a literal pin on today's cache string can
# only fail when someone edits the file, and cannot tell a safe alternative from
# a broken one.

# Tokens that make a build-cache spec branch-derived. Interpolated into a Docker
# reference they produce `<pr_number>/merge` for a pull request, which is not a
# legal tag, so the exporter aborts. Flagged anywhere in either spec.
_BRANCH_DERIVED_TOKENS = ("github.ref_name", "github.head_ref", "buildcache-")


def _parse_cache_spec(spec: str) -> dict[str, str]:
    """Parse a buildx cache spec like ``type=gha,scope=x,mode=max`` into a dict.

    Keys and values are stripped; empty segments are skipped. A segment without
    ``=`` is recorded under its own (stripped) text as the key, so garbage input
    cannot silently parse into an empty-or-compliant dict — the predicate sees
    the unknown key and flags it.
    """
    parsed: dict[str, str] = {}
    for segment in spec.split(","):
        segment = segment.strip()
        if not segment:
            continue
        key, sep, value = segment.partition("=")
        if not sep:
            parsed[key] = ""
            continue
        parsed[key.strip()] = value.strip()
    return parsed


def _build_cache_violations(cache_from: str | None, cache_to: str | None) -> list[str]:
    """Return policy violations for the build job's cache pair; ``[]`` means compliant.

    Flagged: a missing/empty side; a backend other than ``gha`` (which is what
    keeps the ``type=registry`` + ``github.ref_name`` hazard out); a missing or
    empty ``scope`` on either side; differing scopes (a split cache is
    permanently cold); ``cache-to`` without ``mode=max`` (silent speed
    regression); and any branch-derived token in either spec.
    """
    violations: list[str] = []
    for label, spec in (("cache-from", cache_from), ("cache-to", cache_to)):
        if not spec or not spec.strip():
            violations.append(f"{label} must be set")
        else:
            for token in _BRANCH_DERIVED_TOKENS:
                if token in spec:
                    violations.append(
                        f"{label} is branch-derived ({token!r} is not legal in a "
                        "Docker reference)"
                    )

    if not cache_from or not cache_to:
        return violations

    from_parsed = _parse_cache_spec(cache_from)
    to_parsed = _parse_cache_spec(cache_to)

    for label, parsed in (("cache-from", from_parsed), ("cache-to", to_parsed)):
        if parsed.get("type") != "gha":
            violations.append(
                f"{label} must use type=gha, got {parsed.get('type')!r}"
            )
        if not parsed.get("scope"):
            violations.append(f"{label} must declare a non-empty scope")

    from_scope = from_parsed.get("scope")
    to_scope = to_parsed.get("scope")
    if from_scope and to_scope and from_scope != to_scope:
        violations.append(
            f"cache-from and cache-to must share one scope; got "
            f"{from_scope!r} vs {to_scope!r} (a split cache is permanently cold)"
        )

    if "max" not in to_parsed.get("mode", "").split(";"):
        violations.append(
            f"cache-to must set mode=max, got {to_parsed.get('mode')!r}"
        )

    return violations


def _build_job() -> dict:
    """Return the parsed ``jobs.build`` mapping from ci.yml."""
    import yaml

    document = yaml.safe_load(_read(_CI_YML))
    assert isinstance(document, dict), "ci.yml must parse to a mapping"
    jobs = document.get("jobs")
    assert isinstance(jobs, dict), "ci.yml 'jobs' must be a mapping"
    job = jobs.get("build")
    assert isinstance(job, dict), "ci.yml has no 'build' job"
    return job


def _build_cache_specs() -> tuple[str | None, str | None]:
    """Return the build job's ``(cache-from, cache-to)`` values as written."""
    job = _build_job()
    steps = job.get("steps")
    assert isinstance(steps, list), "ci.yml 'build.steps' must be a list"
    for step in steps:
        if isinstance(step, dict) and step.get("name") == "Build and push Docker image":
            config = step.get("with")
            assert isinstance(config, dict), (
                "the 'Build and push Docker image' step must declare a with: mapping"
            )
            return config.get("cache-from"), config.get("cache-to")
    raise AssertionError("ci.yml build job has no 'Build and push Docker image' step")


def _step_by_name(step_name: str) -> dict:
    """Return the build job's step mapping by display name."""
    steps = _build_job().get("steps", [])
    for step in steps:
        if isinstance(step, dict) and step.get("name") == step_name:
            return step
    raise AssertionError(f"ci.yml build job has no step named {step_name!r}")


def test_parse_cache_spec_reads_keys_and_values() -> None:
    """``_parse_cache_spec`` yields the mapping the predicates rely on."""
    assert _parse_cache_spec("type=gha,scope=mko-bazuna") == {
        "type": "gha",
        "scope": "mko-bazuna",
    }
    assert _parse_cache_spec("type=gha,scope=x,mode=max") == {
        "type": "gha",
        "scope": "x",
        "mode": "max",
    }
    # Garbage never silently becomes a compliant dict.
    garbage = "not a cache spec"
    assert _parse_cache_spec(garbage) == {garbage: ""}
    assert _build_cache_violations(garbage, garbage)


def test_build_cache_uses_the_gha_backend_with_one_scope() -> None:
    """The build job's cache pair is the GHA backend with one stable scope."""
    cache_from, cache_to = _build_cache_specs()
    violations = _build_cache_violations(cache_from, cache_to)
    assert not violations, (
        "ci.yml build cache violates the cache policy (12-OPS-009): "
        + "; ".join(violations)
    )


def test_build_cache_guard_detects_a_branch_derived_registry_ref() -> None:
    """The guard fails on the old ``type=registry`` + ``github.ref_name`` form.

    That is the shape that broke CI: ``github.ref_name`` is ``<pr>/merge`` for a
    pull request, and ``/`` is not a legal Docker tag character.
    """
    violations = _build_cache_violations(
        "type=registry,ref=ghcr.io/x/y:buildcache-${{ github.ref_name }}",
        "type=registry,ref=ghcr.io/x/y:buildcache-${{ github.ref_name }},mode=max",
    )
    assert violations
    assert any("type=gha" in v for v in violations), violations
    assert any("github.ref_name" in v for v in violations), violations


def test_build_cache_guard_detects_a_split_scope() -> None:
    """The guard fails when cache-from and cache-to use different scopes."""
    violations = _build_cache_violations(
        "type=gha,scope=a",
        "type=gha,scope=b,mode=max",
    )
    assert any("scope" in v for v in violations), violations


def test_build_cache_guard_detects_a_missing_max_mode() -> None:
    """The guard fails when cache-to drops ``mode=max``."""
    violations = _build_cache_violations(
        "type=gha,scope=x,mode=max",
        "type=gha,scope=x",
    )
    assert any("mode=max" in v for v in violations), violations


def test_build_cache_never_derives_a_ref_from_a_branch_name() -> None:
    """The canonical coordinate is defined once and the cache refs are branch-free.

    ``ci.yml`` declares ``IMAGE_REPOSITORY`` once in the build job's ``env:``, so
    the coordinate lives in exactly one place; the build cache must not
    reintroduce a branch-derived Docker reference.
    """
    text = _read(_CI_YML)
    assert f"IMAGE_REPOSITORY: {_CANONICAL_REPOSITORY}" in text, (
        "ci.yml must define IMAGE_REPOSITORY to the canonical coordinate"
    )
    cache_from, cache_to = _build_cache_specs()
    assert cache_from and cache_to, "ci.yml build job must declare both cache refs"
    for spec in (cache_from, cache_to):
        for token in ("github.ref_name", "github.head_ref", "buildcache-"):
            assert token not in spec, (
                f"ci.yml build-cache spec must not be branch-derived: {spec!r}"
            )


# --- one coordinate across the workflow files ------------------------------


def test_no_non_canonical_ghcr_coordinate_anywhere() -> None:
    """Every ``ghcr.io/...`` literal in the CI/deploy files matches the coordinate.

    The build output, the deploy echo, the restore-test pull and the cache refs
    must all resolve to the same registry namespace. ``${{ env.IMAGE_REPOSITORY }}``
    indirection is allowed because the env value is asserted canonical above.
    """
    offenders: list[str] = []
    for path in (_CI_YML, _DEPLOY_YML, _RESTORE_TEST_YML):
        for line_no, line in enumerate(_read(path).splitlines(), start=1):
            if "ghcr.io/" not in line:
                continue
            for token in line.split("ghcr.io/")[1:]:
                parts = token.split(":", 1)[0].split(",", 1)[0].strip()
                if not parts:
                    continue
                repo = parts.split()[0]
                # A digest-qualified reference (`repo@sha256:<hex>`) names the
                # same repository; strip the qualifier before comparing.
                repo = repo.split("@", 1)[0]
                if repo == "${{":
                    continue  # env.IMAGE_REPOSITORY indirection, asserted above
                if repo != _CANONICAL_REPOSITORY:
                    offenders.append(f"{path.name}:{line_no}: ghcr.io/{repo}")
    assert not offenders, (
        "every ghcr.io coordinate must resolve to "
        f"{_CANONICAL_COORDINATE} (12-OPS-009); found:\n" + "\n".join(offenders)
    )


def test_prod_compose_repository_default_is_canonical() -> None:
    """docker-compose.prod.yml must default ``REPOSITORY`` to the canonical namespace."""
    text = _read(_PROD_COMPOSE)
    assert f"${{REPOSITORY:-{_CANONICAL_REPOSITORY}}}" in text, (
        "docker-compose.prod.yml must default REPOSITORY to "
        f"{_CANONICAL_REPOSITORY}"
    )
    assert "${REPOSITORY:-mko-bazuna/mko_bazuna}" not in text, (
        "docker-compose.prod.yml still defaults REPOSITORY to the "
        "non-canonical mko-bazuna/mko_bazuna namespace — GHCR rejects it with "
        "not_found: owner not found"
    )


def test_env_prod_example_repository_is_canonical() -> None:
    """.env.prod.example must ship the canonical ``REPOSITORY`` value."""
    text = _read(_ENV_PROD_EXAMPLE)
    assert f"REPOSITORY={_CANONICAL_REPOSITORY}" in text, (
        f".env.prod.example must ship REPOSITORY={_CANONICAL_REPOSITORY}"
    )
    assert "REPOSITORY=mko-bazuna/mko_bazuna" not in text, (
        ".env.prod.example still ships the non-canonical "
        "mko-bazuna/mko_bazuna REPOSITORY value — GHCR rejects it with "
        "not_found: owner not found"
    )


# --- workflow concurrency --------------------------------------------------


def _concurrency_block(text: str) -> str:
    """Return the top-level ``concurrency:`` block, or an empty string."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if re.match(r"concurrency\s*:\s*$", line):
            block = [line]
            for follow in lines[i + 1 :]:
                if follow and not follow.startswith(" "):
                    break
                block.append(follow)
            return "\n".join(block)
    return ""


def test_ci_yml_declares_top_level_concurrency() -> None:
    """ci.yml must declare a top-level ``concurrency:`` group.

    Two pushes otherwise race the shared buildcache reference and interleave
    against the same cache target.
    """
    block = _concurrency_block(_read(_CI_YML))
    assert block, "ci.yml must declare a top-level concurrency: block"
    assert "group:" in block, "ci.yml concurrency must name a group"
    assert "cancel-in-progress:" in block, (
        "ci.yml concurrency must set cancel-in-progress explicitly"
    )


def test_deploy_yml_declares_top_level_concurrency() -> None:
    """deploy.yml must declare a top-level ``concurrency:`` group.

    Two manual dispatches otherwise interleave pull and ``up -d`` against one
    production host, and a half-applied mix of images can report green.
    """
    block = _concurrency_block(_read(_DEPLOY_YML))
    assert block, "deploy.yml must declare a top-level concurrency: block"
    assert "group:" in block, "deploy.yml concurrency must name a group"


def test_deploy_concurrency_never_cancels_in_progress() -> None:
    """A deploy must never be cancelled mid-flight (12-OPS-009)."""
    block = _concurrency_block(_read(_DEPLOY_YML))
    assert "cancel-in-progress: false" in block, (
        "deploy.yml must set cancel-in-progress: false — cancelling a deploy "
        "mid-flight can leave a half-applied mix of images reporting green"
    )
    assert "cancel-in-progress: true" not in block, (
        "deploy.yml must never cancel an in-flight deploy"
    )


def test_ci_concurrency_does_not_cancel_in_progress() -> None:
    """ci.yml's concurrency must not cancel in progress (branch-protection-adjacent).

    A cancelled run reports ``cancelled``, never ``success``, so it can never be
    mistaken for a green gate — but cancelling a run that a required status check
    depends on would turn a push into a permanently pending check. The value is
    ``false`` for that reason.
    """
    block = _concurrency_block(_read(_CI_YML))
    assert "cancel-in-progress: false" in block, (
        "ci.yml concurrency must set cancel-in-progress: false"
    )


# --- the corrected citation ------------------------------------------------


def test_deploy_check_comment_cites_the_current_phase() -> None:
    """The deploy-check rationale must cite ``12-OPS-`` never a bare ``OPS-``.

    The header read ``OPS-001`` — in this phase that identifier is the bandit
    finding, not the deploy-check gate.
    """
    text = _read(_CI_YML)
    marker = "  deploy-check:"
    idx = text.index(marker)
    header = text[:idx].splitlines()
    # The contiguous comment block directly above the job header.
    comment_lines: list[str] = []
    for line in reversed(header):
        if line.strip().startswith("#"):
            comment_lines.append(line)
        elif line.strip() == "":
            if comment_lines:
                break
        else:
            break
    comment = "\n".join(reversed(comment_lines))
    assert "12-OPS-" in comment, (
        "the deploy-check rationale must cite a cycle-scoped 12-OPS identifier"
    )
    # A bare `OPS-001` (not preceded by `12-`) must be gone.
    assert "(OPS-001)" not in comment, (
        "the deploy-check rationale still cites the bare `OPS-001`"
    )
