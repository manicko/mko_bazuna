"""
CI configuration parity tests (Prevention — guards against D-01/D-02/D-04 / §8-rec-4 drift).

Asserts that live CI configuration matches the documented contract, converting
doc drift into a CI gate:

1. ci.yml:91 uses `--dist loadgroup` + `-m "not seed"` + `--reuse-db` (not loadscope).
2. ci-seed.yml uses `-m "seed"` with NO xdist (serial run), triggered once per push (no nightly cron).
3. pyproject.toml: no `e2e` marker; `xdist_group` registered; `addopts` has no `--cov`.
4. entrypoint-test.sh:41 default PYTEST_OPTS includes `--reuse-db` + `--dist loadgroup`.
5. Makefile: `test-clean-db` target exists, is in `.PHONY`, and `test-recreate`
   depends on it (requires T4/§8-rec-4 to be implemented first).
6. docs/ops: every production `docker compose` invocation — embedded in a longer
   command, prefixed by a variable assignment, or split across shell
   backslash-continuations — carries its flags, and every canonical `ghcr.io`
   coordinate matches the manifest's own default. Both checks are per-file: each
   file the selector matches must still contain at least one conforming
   invocation, so a deleted invocation is flagged rather than absorbed
   (12-VAL-003).

Uses stdlib only: tomllib for TOML; Path.read_text() for YAML (string-level checks).
No PyYAML dependency — the asserted values are command-line substrings in `run:` lines.
Follows the test_i18n_completeness.py precedent (doc-DoD enforcement, no third-party deps).

Behavioural vs structural guards (12-VAL-003)
---------------------------------------------
This repository uses two distinct guard classes, and the distinction is the
convention `12-VAL-003` exists to make explicit:

* A **structural** guard inspects configuration text or symbols and asserts a
  *token* is present or absent. It is cheap, hermetic and CWD-independent, and it
  is the correct tool when the artefact under test genuinely has no runtime
  behaviour to observe (a workflow `run:` line, a Makefile target, a compose
  key). Most assertions in this module are structural, and that is appropriate.
* A **behavioural** guard exercises the real code path and asserts an
  *observable outcome* — a rendered response body, a resolved metric series, a
  subprocess exit status. It is the tool for anything that can silently become
  inert while its token survives. The repository's model is
  `apps/core/tests/test_observability.py::test_metrics_endpoint`, which renders
  `/metrics` and asserts the exposition rather than the route's presence.

The inconsistency this convention resolves: a structural guard placed over a
*control* passes while the control is dead — the shared root cause of
`12-OPS-001` (a SAST step that scanned zero files), `12-OPS-003` (an alert
selector naming a series that does not exist) and `12-OPS-004` (a restore drill
that echoed a count and asserted nothing). Where a control's outcome is
observable, the guard must be behavioural; where it is not,
`VAL-003`'s rule is to name that explicitly in the guard's docstring instead of
letting a structural assertion stand in for an unobservable property.

The `docs/ops` parity guard below is deliberately **structural**: the property it
polices — that a document quotes the same flags and coordinate the live files
declare — is static text, so a rendered record is neither available nor
meaningful. It asserts in the **documentation → live file** direction only, so a
new compose service never forces an unrelated doc edit.
"""

from __future__ import annotations

import re
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
_CI_SEED_YML = _ROOT / ".github" / "workflows" / "ci-seed.yml"
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


# --- ci-seed.yml parity ---------------------------------------------------


def test_seed_workflow_runs_seed() -> None:
    """ci-seed.yml must run -m 'seed'."""
    text = _CI_SEED_YML.read_text()
    assert '-m "seed"' in text, "ci-seed.yml must use -m 'seed'"


def test_seed_workflow_is_serial() -> None:
    """ci-seed.yml must NOT use xdist (no -n, no --dist)."""
    text = _CI_SEED_YML.read_text()
    assert "-n auto" not in text, "ci-seed.yml must not use -n auto (serial run)"
    assert "--dist" not in text, "ci-seed.yml must not use --dist (serial run)"


def test_seed_workflow_runs_on_push() -> None:
    """ci-seed.yml is push-triggered; the nightly cron is gone for good."""
    text = _CI_SEED_YML.read_text()
    assert "push:" in text, "ci-seed.yml must be triggered by push"
    assert "schedule:" not in text, "ci-seed.yml must not carry a nightly schedule"
    assert "cron:" not in text, "ci-seed.yml must not carry a cron schedule"


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


# --- docs/ops parity (12-VAL-003) ------------------------------------------
# `a89f0cd` (12-OPS-018) already derives the base manifest's own `image:` pins
# and asserts docs/ops/docker-deployment.md's production TABLE quotes them
# (equality, so a dropped row fails too). That guard is bounded to one file's
# table. The guard below does NOT restate it: it polices the two further
# documented claims `12-VAL-003` names — a `docker compose` invocation's FLAGS
# and a canonical registry COORDINATE quoted in prose — against the live files.
# It runs over every `docs/ops/*.md`, but it does not require them to *contain*
# the token: the documentation -> live-file direction means "where a doc makes
# the claim, the claim must match", and a doc that makes no such claim is left
# alone. What it does require, per file, is that a claim which exists today is
# not silently deleted afterwards.
#
# Direction: documentation -> live file. A newly added compose service or a new
# workflow step must never force a doc sentence unless the doc itself makes the
# claim. Structural by design (see the module docstring): the property policed is
# static text, so no rendered outcome is available to assert.

# The prod compose override, split so `-f docker-compose.prod.yml` matches only
# as a whole flag and not as a prefix of another file name.
_PROD_COMPOSE_FILE = "docker-compose.prod.yml"
_BASE_COMPOSE_FILE = "docker-compose.yml"
_CANONICAL_COORDINATE_RE = re.compile(r"ghcr\.io/[A-Za-z0-9_.\-/]+")


def _docs_ops_markdown() -> list[Path]:
    """Return every Markdown file under docs/ops, deterministically ordered."""
    return sorted(_DOCS_OPS.glob("*.md"))


def _normalise_continuations(text: str) -> list[str]:
    """Join shell ``\\``-continuations so a split invocation is one logical line.

    A production invocation written across several physical lines with a trailing
    backslash stops matching a per-physical-line selector, so the guard cannot
    see it to check it. This folds each ``... \\`` plus its indented continuation
    into a single space-separated line before any matching happens (12-VAL-003).
    """
    logical: list[str] = []
    pending: str | None = None
    for raw in text.split("\n"):
        stripped = raw.strip()
        if pending is None:
            pending = stripped
        else:
            pending = f"{pending} {stripped}"
        if pending.endswith("\\"):
            pending = pending[:-1].rstrip()
        else:
            logical.append(pending)
            pending = None
    if pending is not None:
        logical.append(pending)
    return logical


def _compose_invocations_targeting_prod(text: str) -> list[str]:
    """Return every logical line invoking production via ``docker compose``.

    The line is matched on *containment*, not ``startswith``: a production
    invocation may be embedded in a longer command (e.g. ``docker inspect …
    $(docker compose …)``) or prefixed by a per-command variable assignment
    (``IMAGE_TAG=… docker compose …``). Requiring ``startswith("docker compose")``
    silently skips those, which is exactly the vacuous-coverage defect this guard
    exists to remove. ``\\``-continuations are folded first so a split invocation
    is seen as one logical line (12-VAL-003).
    """
    return [
        line
        for line in _normalise_continuations(text)
        if "docker compose" in line and _PROD_COMPOSE_FILE in line
    ]


def _manifest_registry_coordinate() -> str:
    """Derive the canonical `ghcr.io/<owner>/<repo>` coordinate from the manifest.

    `docker-compose.prod.yml` is the single source of truth: it declares
    ``image: ${REGISTRY:-<registry>}/${REPOSITORY:-<repo>}:...``. The default for
    each variable is read from the manifest itself, so a doc that restates a
    different owner or repository fails — the coordinate is never hard-coded
    here. The guard's RED proof is exactly that: changing the manifest default
    moves the expected value and a stale doc stops matching.
    """
    text = (_ROOT / _PROD_COMPOSE_FILE).read_text(encoding="utf-8")
    registry_match = re.search(r"\$\{REGISTRY:-([^}]+)\}", text)
    repository_match = re.search(r"\$\{REPOSITORY:-([^}]+)\}", text)
    assert registry_match, (
        f"{_PROD_COMPOSE_FILE} must default $REGISTRY (12-VAL-003)"
    )
    assert repository_match, (
        f"{_PROD_COMPOSE_FILE} must default $REPOSITORY (12-VAL-003)"
    )
    return f"{registry_match.group(1)}/{repository_match.group(1)}"


# Files that today document at least one production `docker compose`
# invocation and therefore MUST keep at least one invocation carrying the
# required flags. A static manifest — not a derivation — is the deletion guard:
# if the derivation and this set ever disagree, the guard fails, so removing
# every invocation from a listed file (or adding a new one to an unlisted file)
# is a loud failure rather than a silent shrink of coverage. Regenerate the
# set deliberately when a runbook legitimately starts or stops documenting a
# production command (12-VAL-003).
_DOCS_OPS_FILES_WITH_PRODUCTION_INVOCATIONS = frozenset(
    {
        "docker-deployment.md",
        "operator-detection-floor.md",
        "restore.md",
        "rollback.md",
    }
)

# Files that today quote a canonical `ghcr.io` registry coordinate. Same
# deletion-guard reasoning as above (12-VAL-003).
_DOCS_OPS_FILES_WITH_REGISTRY_COORDINATES = frozenset(
    {
        "docker-deployment.md",
        "rollback.md",
    }
)


def _docs_ops_files_with_production_invocations() -> dict[str, str]:
    """Return ``filename -> text`` for files with a production compose invocation."""
    found: dict[str, str] = {}
    for path in _docs_ops_markdown():
        text = path.read_text(encoding="utf-8")
        if _compose_invocations_targeting_prod(text):
            found[path.name] = text
    return found


def test_docs_ops_production_compose_invocations_carry_env_file() -> None:
    """Every production `docker compose` invocation in docs/ops carries the flags.

    A production invocation that omits ``--env-file .env.prod`` aborts during
    config rendering, and one that omits the base ``-f`` file silently runs the
    dev configuration. A documented invocation that cannot be executed is the
    exact class of drift `12-VAL-003` names (12-OPS-006 recorded it for
    restore.md).

    **Per-file, not a global floor.** The previous form counted matches across
    all of docs/ops and asserted merely ``checked > 0``, so deleting one file's
    every invocation (or all but one invocation anywhere) left the guard green.
    Coverage is now anchored to ``_DOCS_OPS_FILES_WITH_PRODUCTION_INVOCATIONS``:
    the set the selector derives must equal that manifest (so a deleted
    invocation is flagged, not absorbed) and each listed file's invocation must
    carry both flags.
    """
    found = _docs_ops_files_with_production_invocations()
    missing = sorted(_DOCS_OPS_FILES_WITH_PRODUCTION_INVOCATIONS - set(found))
    unexpected = sorted(set(found) - _DOCS_OPS_FILES_WITH_PRODUCTION_INVOCATIONS)
    assert not missing, (
        "these docs/ops files no longer contain the production docker compose "
        f"invocation they document (12-VAL-003): {missing}"
    )
    assert not unexpected, (
        "these docs/ops files newly document a production docker compose "
        f"invocation; add them to the manifest above (12-VAL-003): {unexpected}"
    )
    for name, text in sorted(found.items()):
        offenders = [
            line
            for line in _compose_invocations_targeting_prod(text)
            if _PROD_ENV_FILE not in line or f"-f {_BASE_COMPOSE_FILE}" not in line
        ]
        assert not offenders, (
            f"{name}: production invocation must carry {_PROD_ENV_FILE!r} and "
            f"'-f {_BASE_COMPOSE_FILE}' (12-VAL-003): {offenders}"
        )


def test_docs_ops_registry_coordinate_matches_the_manifest() -> None:
    """Every `ghcr.io` coordinate quoted in docs/ops matches the manifest default.

    The canonical coordinate is ``ghcr.io/manicko/mko_bazuna``; the manifest
    derives it from ``${REGISTRY:-...}`` / ``${REPOSITORY:-...}``. A doc that
    quotes a stale owner or repository sends an operator to an image the stack
    does not pull. The expected value is derived from the manifest, so this
    cannot decay into a second copy of the string; trailing sentence punctuation
    is stripped before comparison (12-VAL-003).

    **Per-file, not a global floor.** As with the compose guard above, the set of
    files quoting a coordinate is anchored to
    ``_DOCS_OPS_FILES_WITH_REGISTRY_COORDINATES`` so a deleted coordinate in a
    named file is flagged rather than absorbed.
    """
    expected = _manifest_registry_coordinate()
    quoted_by_file: dict[str, list[str]] = {}
    for path in _docs_ops_markdown():
        text = path.read_text(encoding="utf-8")
        matches = _CANONICAL_COORDINATE_RE.findall(text)
        if matches:
            quoted_by_file[path.name] = [match.rstrip(".") for match in matches]

    missing = sorted(_DOCS_OPS_FILES_WITH_REGISTRY_COORDINATES - set(quoted_by_file))
    unexpected = sorted(
        set(quoted_by_file) - _DOCS_OPS_FILES_WITH_REGISTRY_COORDINATES
    )
    assert not missing, (
        "these docs/ops files no longer quote the registry coordinate they "
        f"document (12-VAL-003): {missing}"
    )
    assert not unexpected, (
        "these docs/ops files newly quote a registry coordinate; add them to "
        f"the manifest above (12-VAL-003): {unexpected}"
    )
    mismatched = [
        (name, coordinate)
        for name, coordinates in sorted(quoted_by_file.items())
        for coordinate in coordinates
        if coordinate != expected
    ]
    assert not mismatched, (
        f"docs/ops quote a registry coordinate that is not the manifest's "
        f"{expected!r} (12-VAL-003): {mismatched}"
    )

