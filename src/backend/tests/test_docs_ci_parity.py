"""
CI configuration parity tests (Prevention — guards against D-01/D-02/D-04 / §8-rec-4 drift).

Asserts that live CI configuration matches the documented contract, converting
doc drift into a CI gate:

1. ci.yml:91 uses `--dist loadgroup` + `-m "not seed"` + `--reuse-db` (not loadscope).
2. ci-nightly.yml:73 uses `-m "seed"` with NO xdist (serial run).
3. pyproject.toml: no `e2e` marker; `xdist_group` registered; `addopts` has no `--cov`.
4. entrypoint-test.sh:41 default PYTEST_OPTS includes `--reuse-db` + `--dist loadgroup`.
5. Makefile: `test-clean-db` target exists, is in `.PHONY`, and `test-recreate`
   depends on it (requires T4/§8-rec-4 to be implemented first).

Uses stdlib only: tomllib for TOML; Path.read_text() for YAML (string-level checks).
No PyYAML dependency — the asserted values are command-line substrings in `run:` lines.
Follows the test_i18n_completeness.py precedent (doc-DoD enforcement, no third-party deps).
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

# Resolve repository root by searching upward for pyproject.toml.
# Robust to varying CWD in Docker (WORKDIR=/app or /app/src/backend) and
# local development (from repo root). pyproject.toml exists only at repo root.
_ROOT = Path(__file__).resolve().parent
while not (_ROOT / "pyproject.toml").exists():
    _ROOT = _ROOT.parent

_CI_YML = _ROOT / ".github" / "workflows" / "ci.yml"
_CI_NIGHTLY_YML = _ROOT / ".github" / "workflows" / "ci-nightly.yml"
_PYPROJECT = _ROOT / "pyproject.toml"
_ENTRYPOINT = _ROOT / "docker" / "entrypoint-test.sh"
_MAKEFILE = _ROOT / "Makefile"
_MAKEFILE_PS1 = _ROOT / "Makefile.ps1"


# --- ci.yml parity -------------------------------------------------------


def test_ci_uses_loadgroup() -> None:
    """ci.yml:91 must use --dist loadgroup (not loadscope)."""
    text = _CI_YML.read_text()
    assert "--dist loadgroup" in text, "ci.yml:91 must use --dist loadgroup"


def test_ci_excludes_seed() -> None:
    """ci.yml:91 must exclude seed tests with -m 'not seed'."""
    text = _CI_YML.read_text()
    assert '-m "not seed"' in text, "ci.yml:91 must use -m 'not seed'"


def test_ci_uses_reuse_db() -> None:
    """ci.yml:91 must use --reuse-db."""
    text = _CI_YML.read_text()
    assert "--reuse-db" in text, "ci.yml:91 must use --reuse-db"


def test_ci_does_not_use_loadscope() -> None:
    """ci.yml must never reference loadscope."""
    text = _CI_YML.read_text()
    assert "--dist loadscope" not in text, "ci.yml must not use --dist loadscope"


def test_ci_command_subset() -> None:
    """ci.yml:91 must contain the full expected command token set."""
    text = _CI_YML.read_text()
    expected = (
        '-m "not seed"',
        "-n auto",
        "--dist loadgroup",
        "--reuse-db",
        "--cov",
        "--cov-report=xml",
    )
    missing = [token for token in expected if token not in text]
    assert not missing, f"ci.yml missing expected tokens: {missing}"


# --- ci-nightly.yml parity -----------------------------------------------


def test_nightly_runs_seed() -> None:
    """ci-nightly.yml:73 must run -m 'seed'."""
    text = _CI_NIGHTLY_YML.read_text()
    assert '-m "seed"' in text, "ci-nightly.yml:73 must use -m 'seed'"


def test_nightly_is_serial() -> None:
    """ci-nightly.yml must NOT use xdist (no -n, no --dist)."""
    text = _CI_NIGHTLY_YML.read_text()
    assert "-n auto" not in text, "ci-nightly.yml must not use -n auto (serial run)"
    assert "--dist" not in text, "ci-nightly.yml must not use --dist (serial run)"


# --- pyproject.toml parity -----------------------------------------------


def _load_pyproject() -> dict:
    with _PYPROJECT.open("rb") as f:
        return tomllib.load(f)


def _marker_names() -> list[str]:
    markers: list[str] = _load_pyproject()["tool"]["pytest"]["ini_options"]["markers"]
    return [m.split(":")[0] for m in markers]


def test_no_e2e_marker() -> None:
    """e2e must not be a registered marker (removed per rules.md:51)."""
    assert "e2e" not in _marker_names(), "e2e marker must not be registered"


def test_xdist_group_marker_registered() -> None:
    """xdist_group must be in the markers list (pytest-xdist built-in)."""
    assert "xdist_group" in _marker_names()


def test_xdist_group_not_double_registered() -> None:
    """xdist_group must appear exactly once in markers (not double-registered)."""
    names = _marker_names()
    assert names.count("xdist_group") == 1, "xdist_group must appear exactly once"


def test_addopts_has_no_cov() -> None:
    """--cov must not be in addopts (CI-only, passed on command line)."""
    addopts: list[str] = _load_pyproject()["tool"]["pytest"]["ini_options"]["addopts"]
    assert "--cov" not in addopts, "--cov must be CI-only"


def test_addopts_uses_importlib() -> None:
    """addopts must use --import-mode=importlib."""
    addopts: list[str] = _load_pyproject()["tool"]["pytest"]["ini_options"]["addopts"]
    assert "--import-mode=importlib" in addopts


def test_pyproject_has_testpaths() -> None:
    """pyproject.toml must define testpaths to restrict collection scope.

    Prevents pytest from walking the entire rootdir (docs/, scripts/, etc.)
    during xdist collection — a known cause of transient ENOMEM on local
    Docker (see Problem_07).
    """
    ini_options = _load_pyproject()["tool"]["pytest"]["ini_options"]
    assert "testpaths" in ini_options, "testpaths must be set in pyproject.toml"


def test_testpaths_includes_backend_and_bot() -> None:
    """testpaths must cover both the backend and Telegram bot test suites."""
    ini_options = _load_pyproject()["tool"]["pytest"]["ini_options"]
    paths: list[str] = ini_options["testpaths"]
    assert "src/backend" in paths, "testpaths must include src/backend"
    assert "src/telegram_bot" in paths, "testpaths must include src/telegram_bot"


# --- entrypoint-test.sh parity -------------------------------------------


def test_entrypoint_defaults_reuse_db() -> None:
    """entrypoint-test.sh:41 default PYTEST_OPTS must include --reuse-db."""
    text = _ENTRYPOINT.read_text()
    assert "--reuse-db" in text


def test_entrypoint_defaults_loadgroup() -> None:
    """entrypoint-test.sh:41 default PYTEST_OPTS must include --dist loadgroup."""
    text = _ENTRYPOINT.read_text()
    assert "--dist loadgroup" in text


def test_entrypoint_caps_maxprocesses() -> None:
    """entrypoint-test.sh default PYTEST_OPTS must cap --maxprocesses to avoid
    transient ENOMEM from -n auto forking too many workers on local Docker
    (see Problem_07). CI runners have sufficient headroom and are unaffected.
    """
    text = _ENTRYPOINT.read_text()
    assert "--maxprocesses" in text, "entrypoint must cap --maxprocesses"


# --- Makefile parity (requires T4 / §8-rec-4 implemented) ----------------


def test_makefile_has_test_clean_db() -> None:
    """Makefile must define a test-clean-db target."""
    text = _MAKEFILE.read_text()
    assert "test-clean-db:" in text


def test_makefile_phony_includes_test_clean_db() -> None:
    """test-clean-db must be declared in .PHONY."""
    text = _MAKEFILE.read_text()
    # Collect all .PHONY lines (robust to content after the tag changing)
    # rather than relying on a brittle positional split(".PHONY")[1].
    phony_lines = [line for line in text.splitlines() if ".PHONY" in line]
    assert phony_lines, ".PHONY declaration must exist in Makefile"
    phony_content = "\n".join(phony_lines)
    assert "test-clean-db" in phony_content, (
        "test-clean-db must be declared as a .PHONY target"
    )


def test_makefile_test_recreate_depends_on_clean_db() -> None:
    """test-recreate must depend on test-clean-db (pre-flight cleanup)."""
    text = _MAKEFILE.read_text()
    assert "test-recreate: test-clean-db" in text


def test_makefile_test_recreate_opts_match() -> None:
    """test-recreate's PYTEST_OPTS must be byte-identical across Makefile and
    Makefile.ps1, and neither may use --no-reuse-db (pytest-django 4.x has no
    such option; it was a usage error that failed the fresh-schema gate)."""
    make_opts = _MAKEFILE.read_text()
    ps1_opts = _MAKEFILE_PS1.read_text()

    make_flag = "--create-db --tb=short -n auto --maxprocesses=4 --dist loadgroup"
    ps1_flag = "--create-db --tb=short -n auto --maxprocesses=4 --dist loadgroup"

    assert make_flag in make_opts, "Makefile must use the canonical test-recreate PYTEST_OPTS"
    assert ps1_flag in ps1_opts, "Makefile.ps1 must use the canonical test-recreate PYTEST_OPTS"
    assert make_flag == ps1_flag, "test-recreate PYTEST_OPTS must be identical in Makefile and Makefile.ps1"

    assert "--no-reuse-db" not in make_opts, "Makefile must not use the nonexistent --no-reuse-db flag"
    assert "--no-reuse-db" not in ps1_opts, "Makefile.ps1 must not use the nonexistent --no-reuse-db flag"


# --- DR runbook executability (12-OPS-006) ---------------------------------
# The restore runbook is opened when the database is already lost. docker
# compose aborts during config rendering without --env-file (docker-compose.yml
# and docker-compose.prod.yml use mandatory interpolation), so a production
# invocation that omits it — or omits -f docker-compose.prod.yml and silently
# runs the dev config — cannot be followed. This guard asserts the invariant the
# runbook now depends on. Scope: docs/ops/restore.md, the DR runbook the finding
# names. rollback.md's manual production invocations already carry the flags and
# its automated-rollback excerpt mirrors deploy.yml's sourced-.env.prod script,
# so it is deliberately out of scope here.

_DOCS_OPS = _ROOT / "docs" / "ops"
_RESTORE_RUNBOOK = _DOCS_OPS / "restore.md"
_PROD_OVERRIDE = "-f docker-compose.prod.yml"
_PROD_ENV_FILE = "--env-file .env.prod"


def _production_compose_invocations(text: str) -> list[str]:
    """Return the `docker compose` lines that target the production stack."""
    return [
        line.strip()
        for line in text.split("\n")
        if line.strip().startswith("docker compose")
        and _PROD_OVERRIDE in line
    ]


def test_restore_runbook_production_invocations_are_executable() -> None:
    """Every production `docker compose` line in restore.md carries both -f files.

    A missing `--env-file .env.prod` aborts during config rendering; a missing
    `-f docker-compose.prod.yml` silently runs the dev configuration. Both are
    demonstrated failures (12-OPS-006).
    """
    text = _RESTORE_RUNBOOK.read_text(encoding="utf-8")
    invocations = _production_compose_invocations(text)
    assert invocations, (
        "restore.md must contain at least one production docker compose "
        "invocation for the guard to check"
    )
    for line in invocations:
        assert _PROD_ENV_FILE in line, (
            f"production invocation must carry {_PROD_ENV_FILE!r} (12-OPS-006): {line}"
        )
        assert "-f docker-compose.yml" in line, (
            f"production invocation must carry the base -f file (12-OPS-006): {line}"
        )


