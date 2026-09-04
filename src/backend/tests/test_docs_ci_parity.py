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
    phony_line = text.split(".PHONY")[1].split("\n")[0]
    assert "test-clean-db" in phony_line


def test_makefile_test_recreate_depends_on_clean_db() -> None:
    """test-recreate must depend on test-clean-db (pre-flight cleanup)."""
    text = _MAKEFILE.read_text()
    assert "test-recreate: test-clean-db" in text
