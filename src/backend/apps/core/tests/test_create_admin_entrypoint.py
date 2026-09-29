"""Entrypoint contract test for ``docker/entrypoint-create-admin.sh``.

This module asserts the create_admin entrypoint's two contracts:

1. The **empty-password skip**: a container that is not given an admin password
   logs, exits 0, and creates no user. This is the only load-bearing behaviour
   the command-contract change touches, and it has no coverage anywhere else in
   the tree.
2. The **absence of the secret from the command line**: the script no longer
   passes ``--password``, so the credential is not *forced* through ``argv``.

**VAL-002 caveat, plainly: this is command-contract hygiene and it does not
reduce the credential's exposure.** The real exposure comes from the
``env_file`` channel: the ``create_admin`` service receives the password through
``env_file: .env.prod`` in ``docker-compose.prod.yml`` (and
``ADMIN_PASSWORD=${ADMIN_PASSWORD:-}`` in ``docker-compose.yml``), so the
plaintext is already in the container's ``Config.Env`` and ``docker inspect``
already returns it. Moving the value out of ``argv`` crosses no additional
privilege boundary and reduces the exposure by exactly zero. Nothing here may be
read as claiming otherwise.

**Why the split between a behavioural and a static test.** The skip branch runs
*before* any Python, so it is executable for real against a stubbed
``entrypoint.sh`` placed beside a copy of the script. The invocation, by
contrast, needs a database, Redis and ``/opt/venv/bin/python``, so it cannot be
executed in the test container; a static read of the script text is the honest
form there, not a compromise.

**Why the child environment is scrubbed.** ``_run_script`` passes only ``PATH``,
``HOME`` and (where the test sets it) ``ADMIN_PASSWORD``. Inheriting
``os.environ`` would let a developer's ambient ``ADMIN_PASSWORD``,
``DJANGO_BUILD`` or ``DJANGO_SETTINGS_MODULE`` decide the outcome, and the CI
run and the local run would differ.
"""

from __future__ import annotations

import os
import subprocess

import pytest
from django.conf import settings

pytestmark = [pytest.mark.unit]

# The script lives at <project-root>/docker/entrypoint-create-admin.sh. BASE_DIR
# in settings points to src/ (the inner source dir); its parent is the project
# root. Same resolution as test_scheduler_wiring.py.
_SCRIPT = settings.BASE_DIR.parent / "docker" / "entrypoint-create-admin.sh"

# Copied next to the script under test; the script sources entrypoint.sh from its
# own SCRIPT_DIR, so this is the only way to run the real skip branch without a
# database, Redis and /opt/venv/bin/python.
_STUB_ENTRYPOINT = """#!/bin/bash
set -e
check_env_file() { :; }
fix_volume_permissions() { :; }
wait_for_db() { :; }
wait_for_redis() { :; }
"""


def _run_script(tmp_path, admin_password):
    """Run the real script with a stubbed entrypoint.sh under a scrubbed env.

    The child sees ``PATH`` and ``HOME`` only, plus ``ADMIN_PASSWORD`` when the
    test supplies it -- never ``os.environ``. See the module docstring.
    """
    env = {"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", "/root")}
    if admin_password is not None:
        env["ADMIN_PASSWORD"] = admin_password
    (tmp_path / "entrypoint.sh").write_text(_STUB_ENTRYPOINT, encoding="utf-8")
    script = tmp_path / "entrypoint-create-admin.sh"
    script.write_text(_SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
    script.chmod(0o755)
    return subprocess.run(
        ["bash", str(script)],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_script_exits_zero_when_admin_password_is_empty(tmp_path):
    """ADMIN_PASSWORD set-but-empty: log, exit 0, no admin created.

    Note the script runs ``set -euo pipefail``, so an *unset* ADMIN_PASSWORD is
    an unbound-variable error, not a skip. Compose always defines the variable
    (``ADMIN_PASSWORD=${ADMIN_PASSWORD:-}``), so the empty case is the real one.
    """
    result = _run_script(tmp_path, admin_password="")
    assert result.returncode == 0, result.stderr
    assert "ADMIN_PASSWORD not set, skipping admin user creation" in result.stdout
    assert "create_admin_user" not in result.stdout


def test_script_does_not_pass_the_password_on_the_command_line():
    """The secret is not placed on argv (CFG-003).

    This is command-contract hygiene only. It does not reduce the credential's
    exposure, which comes from the ``env_file`` channel and is unchanged
    (VAL-002).
    """
    content = _SCRIPT.read_text(encoding="utf-8")
    assert "--password" not in content
    assert "exec " in content


def test_script_still_passes_username_and_telegram_id():
    """The non-secret arguments and the skip branch survive unchanged."""
    content = _SCRIPT.read_text(encoding="utf-8")
    assert '--username "${ADMIN_USERNAME:-admin}"' in content
    assert '--telegram-id "${ADMIN_TELEGRAM_ID:--1}"' in content
    assert 'if [ -z "${ADMIN_PASSWORD}" ]; then' in content
    assert "exit 0" in content
