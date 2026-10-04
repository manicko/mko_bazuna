"""
One image coordinate and workflow concurrency (12-OPS-009).

Before this guard there were four live ``ghcr.io/<owner>/<repo>`` strings and the
build cache was silently split: ``ci.yml``'s ``cache-from`` named
``ghcr.io/manicko/mko_bazuna:buildcache`` while its ``cache-to`` named
``ghcr.io/manicko/mko-bazuna:buildcache`` (underscore vs hyphen). Neither
``ci.yml`` nor ``deploy.yml`` declared a ``concurrency`` group, so two pushes
raced the shared buildcache reference and two manual deploys interleaved pull
and ``up -d`` against one production host.

These are structural tests (string-level reads of the workflow files and the
compose/env templates), following the ``test_docs_ci_parity.py`` precedent: no
PyYAML dependency. They do **not** execute any workflow.
"""

from __future__ import annotations

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

# The canonical GHCR coordinate. Chosen because it is the shape GHCR guarantees
# for the repository owner (`mko-bazuna`), and the only namespace the CI job's
# `packages: write` token can push to. `manicko/mko_bazuna` is the GitHub
# repository path, not the container-registry namespace.
_CANONICAL_REPOSITORY = "mko-bazuna/mko_bazuna"
_CANONICAL_COORDINATE = f"ghcr.io/{_CANONICAL_REPOSITORY}"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# --- cache parity ----------------------------------------------------------


def test_build_cache_from_and_to_name_the_same_reference() -> None:
    """``cache-from`` and ``cache-to`` must name the same registry reference.

    A split cache reference degrades every CI build to a cold cache: the layer
    cache written under one name is never read back under the other.
    """
    text = _read(_CI_YML)
    from_ref: str | None = None
    to_ref: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("cache-from:"):
            from_ref = stripped.split("ref=", 1)[1].split(",", 1)[0]
        elif stripped.startswith("cache-to:"):
            to_ref = stripped.split("ref=", 1)[1].split(",", 1)[0]
    assert from_ref, "ci.yml must declare a cache-from registry reference"
    assert to_ref, "ci.yml must declare a cache-to registry reference"
    assert from_ref == to_ref, (
        "ci.yml cache-from and cache-to must name the same reference; "
        f"got cache-from={from_ref!r} cache-to={to_ref!r}"
    )


def test_cache_reference_uses_the_canonical_coordinate() -> None:
    """The shared cache reference must resolve to the canonical coordinate.

    ``ci.yml`` declares ``IMAGE_REPOSITORY`` once in the build job's ``env:``
    and consumes it for both cache refs, so the value lives in exactly one place.
    """
    text = _read(_CI_YML)
    assert f"IMAGE_REPOSITORY: {_CANONICAL_REPOSITORY}" in text, (
        "ci.yml must define IMAGE_REPOSITORY to the canonical coordinate"
    )
    assert "type=registry,ref=ghcr.io/${{ env.IMAGE_REPOSITORY }}:buildcache" in text, (
        "ci.yml build-cache reference must consume env.IMAGE_REPOSITORY"
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
                repo = token.split(":", 1)[0].split(",", 1)[0].strip().split()[0]
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
    assert "${REPOSITORY:-manicko/mko_bazuna}" not in text, (
        "docker-compose.prod.yml still defaults REPOSITORY to the "
        "non-canonical manicko/mko_bazuna namespace"
    )


def test_env_prod_example_repository_is_canonical() -> None:
    """.env.prod.example must ship the canonical ``REPOSITORY`` value."""
    text = _read(_ENV_PROD_EXAMPLE)
    assert f"REPOSITORY={_CANONICAL_REPOSITORY}" in text, (
        f".env.prod.example must ship REPOSITORY={_CANONICAL_REPOSITORY}"
    )
    assert "REPOSITORY=manicko/mko_bazuna" not in text, (
        ".env.prod.example still ships the non-canonical "
        "manicko/mko_bazuna REPOSITORY value"
    )


# --- workflow concurrency --------------------------------------------------


def _concurrency_block(text: str) -> str:
    """Return the top-level ``concurrency:`` block, or an empty string."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line == "concurrency:":
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
