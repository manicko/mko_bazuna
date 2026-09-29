"""Parity between the CI ``deploy-check`` env block and ``config.settings.prod``.

This is the durable half of CFG-002. BLOCK 1 (``071e5c7``) restored the gate by
adding the two missing variables; this module makes that restoration survive the
next change. It parses the ``deploy-check`` job's ``env:`` block out of
``.github/workflows/ci.yml`` and asserts that ``config.settings.prod`` imports in
a subprocess driven by **exactly that block**. A guard added to ``prod.py``
without a matching CI variable now fails the ``test`` job instead of silently
neutering ``deploy-check``.

``ci.yml`` is the single source of truth. There is deliberately no second
representation of the required-variable set: a hand-maintained constant is true
whenever both sides drift together, and it cannot see a *new guard* that adds a
name to neither side. Only importing the module answers "what does prod
require".

The subprocess environment is a scrubbed ``MINIMAL_BASE`` (``PATH``, ``HOME``)
merged with the parsed block — explicitly **not** ``os.environ``. Inheriting the
developer shell would let an exported ``DJANGO_BUILD`` or ``DJANGO_SECRET_KEY``
decide the outcome and would make the CI run and the local run differ.

Every assertion message is **value-free**: it names keys, layers and files,
never a value read from the parsed block. This keeps the CI log and gitleaks
clean, and it relies on ``prod.py``'s exception messages staying value-free — a
future change that starts echoing values into an ``ImproperlyConfigured`` message
would break that contract, and this docstring is the reviewer's pointer to it.

Two negative-control rows are shipped, one per masking channel, each chosen to be
valid in **both** environments this suite runs in:

``REDIS_URL``, present-but-empty
    In the Docker test container ``./.env.test`` is bind-mounted as ``src/.env``
    and, for a prod import, ``base.py``'s present-file branch runs
    (``"test"`` is not in the module name). ``read_env(overwrite=False)`` then
    back-fills any key **absent** from the subprocess environment. A *deleted*
    key is therefore silently restored — but an *empty* value is not, because the
    key is present. So the portable mutation here is present-but-empty. In the CI
    ``test`` runner there is no ``src/.env`` at all, so both forms are simply the
    process environment.

``CSRF_TRUSTED_ORIGINS``, absent
    ``.env.test`` does not define this key, so there is nothing for the back-fill
    channel to restore and deletion is portable to both environments.

``DJANGO_SECRET_KEY`` is never used as a control. In the CI ``test`` runner there
is no ``src/.env``, so emptying it takes ``base.py``'s missing-file branch and
``sys.exit(1)``s with a red-herring ".env file not found" message rather than
exercising ``prod.py``.

The two rows also assert different exception types on purpose: the prod import
has no single failure surface. Six guards raise ``ImproperlyConfigured``, two
(``ALLOWED_HOSTS``, ``CSRF_TRUSTED_ORIGINS``) raise a bare ``ValueError``, and an
unset ``DJANGO_SECRET_KEY`` fails from ``base.py`` with a different message
again.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from ruamel.yaml import YAML

from config.settings.tests.test_prod_logging import _run_in_subprocess

pytestmark = [pytest.mark.unit, pytest.mark.settings]

# Resolve the repository root by walking upward to pyproject.toml — the same
# convention as test_prod_logging.py, test_csrf_trusted_origins.py,
# test_compose_contract.py and test_docs_ci_parity.py.
_ROOT = Path(__file__).resolve().parent
while not (_ROOT / "pyproject.toml").exists():
    _ROOT = _ROOT.parent

_CI_YML = _ROOT / ".github" / "workflows" / "ci.yml"
_JOB_NAME = "deploy-check"
_PROD_MODULE = "config.settings.prod"

# Both flags suppress prod.py's guards: DJANGO_BUILD unconditionally, and
# DJANGO_ONESHOT against any module that is not a *.prod module. Either one in
# the deploy-check block would make the gate pass without checking anything.
_BYPASS_FLAGS = frozenset({"DJANGO_BUILD", "DJANGO_ONESHOT"})

# The scrubbed base. PYTHONPATH is deliberately absent: _run_in_subprocess
# overwrites it with the parent sys.path, which is what lets the subprocess
# import config.settings.prod at all.
_MINIMAL_BASE_KEYS = ("PATH", "HOME")

# Importing the settings module directly is the exact subject of the assertion
# and adds no app-population surface to the failure.
_IMPORT_CODE = "import config.settings.prod"


def _load_ci_document() -> dict:
    """Parse ci.yml with a stock safe loader.

    ci.yml carries no custom tags, unlike the compose files that need ``!reset``
    and ``!override`` registered. A ``YAMLError`` is not caught: a malformed
    workflow file must fail the test, not skip it.
    """
    with _CI_YML.open(encoding="utf-8") as fh:
        document = YAML(typ="safe").load(fh)
    assert isinstance(document, dict), (
        "ci.yml must parse to a mapping at the document root"
    )
    return document


def _deploy_check_env() -> dict[str, str]:
    """Return the deploy-check job's env block, proving it was found.

    The non-vacuity ladder: each rung fails closed with a message naming what is
    missing, so a failure says "the env block is not a mapping" rather than
    raising ``TypeError`` from a bare subscript.
    """
    document = _load_ci_document()
    assert "jobs" in document, "ci.yml has no 'jobs' key"
    jobs = document["jobs"]
    assert isinstance(jobs, dict), "ci.yml 'jobs' must be a mapping"
    assert _JOB_NAME in jobs, (
        f"ci.yml has no '{_JOB_NAME}' job; the test's subject does not exist"
    )
    job = jobs[_JOB_NAME]
    assert isinstance(job, dict), f"ci.yml job '{_JOB_NAME}' must be a mapping"
    assert "env" in job, f"ci.yml job '{_JOB_NAME}' has no 'env' key"
    env = job["env"]
    assert isinstance(env, dict), (
        f"ci.yml job '{_JOB_NAME}': env must be a YAML mapping, which is what this test reads"
    )
    assert len(env) > 0, f"ci.yml job '{_JOB_NAME}': env block is empty"
    return {str(key): str(value) for key, value in env.items()}


def _subprocess_env(env: dict[str, str]) -> dict[str, str]:
    """Scrubbed base plus the parsed block. Never seeded from os.environ."""
    base = {key: os.environ[key] for key in _MINIMAL_BASE_KEYS if key in os.environ}
    return {**base, **env}


def test_deploy_check_env_block_imports_prod_settings() -> None:
    """config.settings.prod imports with exactly the deploy-check env block."""
    env = _deploy_check_env()
    assert env["DJANGO_SETTINGS_MODULE"] == _PROD_MODULE, (
        f"ci.yml job '{_JOB_NAME}': DJANGO_SETTINGS_MODULE must be {_PROD_MODULE}"
    )
    empty = sorted(key for key, value in env.items() if not value)
    assert not empty, (
        f"ci.yml job '{_JOB_NAME}': these keys must carry a non-empty "
        f"placeholder value: {empty}"
    )
    templated = sorted(key for key, value in env.items() if "${{" in value)
    assert not templated, (
        f"ci.yml job '{_JOB_NAME}': these keys use a GitHub Actions expression, "
        f"so this test cannot reproduce the value CI uses: {templated}"
    )
    result = _run_in_subprocess(_subprocess_env(env), _IMPORT_CODE)
    assert result.returncode == 0, (
        f"config.settings.prod does not import with the env block from "
        f"ci.yml job '{_JOB_NAME}'. If prod.py recently gained a new required "
        f"variable, add it to jobs.deploy-check.env in .github/workflows/ci.yml "
        f"as a non-secret placeholder — that is this test and the deploy-check "
        f"job both working, not a regression.\n{result.stderr}"
    )


def test_deploy_check_env_block_declares_no_bypass_flag() -> None:
    """The deploy-check block sets neither guard-disabling flag.

    DJANGO_BUILD is the live hazard: prod.py honours it unconditionally, so its
    presence would suppress every guard and the job would pass for no reason at
    all. DJANGO_ONESHOT is inert against a *.prod settings module since BLOCK 3
    but would still suppress the guards against any other module.
    """
    env = _deploy_check_env()
    present = sorted(_BYPASS_FLAGS & env.keys())
    assert not present, (
        f"ci.yml job '{_JOB_NAME}' must not set {present}. "
        "DJANGO_BUILD suppresses every prod guard unconditionally; "
        "DJANGO_ONESHOT is inert under a *.prod settings module but still "
        "suppresses it against any other module. Either one here makes the "
        "gate pass for no reason."
    )


@pytest.mark.parametrize(
    ("name", "form", "expected_error"),
    [
        ("REDIS_URL", "empty", "ImproperlyConfigured"),
        ("CSRF_TRUSTED_ORIGINS", "absent", "ValueError"),
    ],
)
def test_deploy_check_env_block_rejects_missing_variable(
    name: str, form: str, expected_error: str
) -> None:
    """The harness can observe a failure, so its green result means something.

    Each row applies one mutation and asserts the prod import fails with its own
    exception surface. Without this, a green import test would be compatible with
    a harness that cannot fail at all.
    """
    env = _deploy_check_env()
    if form == "empty":
        # read_env(overwrite=False) will not restore a key that is present.
        env[name] = ""
    else:
        # .env.test does not define it, so nothing is back-filled.
        del env[name]
    result = _run_in_subprocess(_subprocess_env(env), _IMPORT_CODE)
    assert result.returncode != 0, (
        f"removing '{name}' did not break the prod import — this test's "
        f"harness cannot observe a failure, so the parity assertion is worthless"
    )
    assert expected_error in result.stderr
    assert name in result.stderr
