"""
Tests for Django settings default values.

Verifies that REDIS_URL defaults to an empty string when the env var is absent
(finding 09-EXT-05), that the production static-files backend is the pinned
theme storage (CFG-007), and that config.settings.dev and config.settings.test
agree on the transport-security tuple (CFG-010). Settings are evaluated at
import time, so these tests use subprocess isolation with controlled
os.environ.
"""

import os
from pathlib import Path

import pytest

from config.settings.tests import TEST_SECRET_KEY
from config.settings.tests.test_prod_logging import (
    _prod_env_overrides,
    _run_in_subprocess,
)

pytestmark = [pytest.mark.unit, pytest.mark.settings]

_ROOT = Path(__file__).resolve().parent
while not (_ROOT / "pyproject.toml").exists():
    _ROOT = _ROOT.parent

# The static-files backend prod must resolve to. This is the real decision, and
# it is owned by base.py's STORAGES dict — not by a STATICFILES_STORAGE
# assignment, which Django removed in 5.1. Asserting the resolved setting (rather
# than the absence of the dead key) is what detects the backend silently
# reverting to Django's default: get_storage_class()/the STORAGES lookup would
# hand back StaticFilesStorage, not this.
_THEME_STATICFILES_BACKEND = "theme.storage.ThemeStaticFilesStorage"

# The seven transport-security settings dev and test must agree on. Named as a
# module-level constant (project rule 10), never inline literals, so the parity
# tuple is one edit away from gaining an eighth member. The seventh,
# LOGIN_BROWSER_ID_COOKIE_HOST_PREFIX, resolves BOTH the login-binding cookie's
# ``__Host-`` name and its Secure flag (see login_token.py): it belongs here
# rather than hardcoded in login_issue, so a dev stack on a non-localhost HTTP
# origin (Django published directly on :8000) is covered by the same machine
# check as sessionid/csrftoken.
_TRANSPORT_SETTINGS = (
    "SECURE_SSL_REDIRECT",
    "SESSION_COOKIE_SECURE",
    "CSRF_COOKIE_SECURE",
    "SECURE_HSTS_SECONDS",
    "SECURE_HSTS_INCLUDE_SUBDOMAINS",
    "SECURE_HSTS_PRELOAD",
    "LOGIN_BROWSER_ID_COOKIE_HOST_PREFIX",
)

# The production value of the login-binding transport setting. base.py's True is
# the entire sibling-subdomain bypass fix (it yields the ``__Host-`` name and its
# mandatory Secure flag together); dev/test carry False for plain HTTP. Pinned
# separately by test_login_binding_host_prefix_is_enabled_in_production, because
# the parity test above only compares dev against test and would stay green if a
# well-meaning edit flipped base.py to False on all three modules at once.
_LOGIN_BINDING_HOST_PREFIX_PROD = True
_LOGIN_BINDING_HOST_PREFIX_DEV = False
_LOGIN_BINDING_HOST_PREFIX_TEST = False

# Import both modules in one process and print `NAME=<repr>` per setting, so a
# mismatch is visible as two differing lines rather than a bare assertion.
_TRANSPORT_PROBE_CODE = (
    "import importlib; "
    "import os; "
    "settings_module = importlib.import_module("
    "os.environ['PROBE_SETTINGS_MODULE']); "
    "print('\\n'.join("
    "f'{name}={getattr(settings_module, name)!r}' "
    "for name in os.environ['PROBE_SETTINGS_NAMES'].split(',')))"
)


def _probe_transport_tuple(module_name: str) -> dict[str, str]:
    """Import ``module_name`` in a subprocess and return its transport tuple.

    Returns a ``{setting_name: repr}`` mapping. Uses ``config.settings.test``'s
    own module name so base.py skips .env reading; the probe reads module
    attributes directly, so no ``django.setup()`` is needed.
    """
    env = {k: v for k, v in os.environ.items()}
    env["DJANGO_SETTINGS_MODULE"] = module_name
    env["DJANGO_SECRET_KEY"] = TEST_SECRET_KEY
    env["PROBE_SETTINGS_MODULE"] = module_name
    env["PROBE_SETTINGS_NAMES"] = ",".join(_TRANSPORT_SETTINGS)
    result = _run_in_subprocess(env, _TRANSPORT_PROBE_CODE)
    assert result.returncode == 0, result.stderr
    resolved: dict[str, str] = {}
    for line in result.stdout.splitlines():
        name, _, value = line.partition("=")
        resolved[name] = value
    assert set(resolved) == set(_TRANSPORT_SETTINGS), (
        f"the probe did not report every transport setting for {module_name}: "
        f"got {sorted(resolved)}"
    )
    return resolved


def test_redis_url_defaults_empty() -> None:
    """REDIS_URL defaults to "" when the env var is absent (finding 09-EXT-05).

    Uses config.settings.test (which skips .env file reading when
    DJANGO_SETTINGS_MODULE contains 'test') with REDIS_URL filtered out
    of the subprocess environment. The base.py default should be "".
    """
    env = {k: v for k, v in os.environ.items() if k != "REDIS_URL"}
    env["DJANGO_SECRET_KEY"] = TEST_SECRET_KEY
    env["DJANGO_SETTINGS_MODULE"] = "config.settings.test"
    result = _run_in_subprocess(
        env,
        "from django.conf import settings; print(repr(settings.REDIS_URL))",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "''"


_CONSOLE_BACKEND = "django.core.mail.backends.console.EmailBackend"
_SMTP_BACKEND = "django.core.mail.backends.smtp.EmailBackend"


def test_prod_email_backend_env_override_is_ignored() -> None:
    """prod.py pins EMAIL_BACKEND, so the env override cannot route mail to stdout.

    base.py reads EMAIL_BACKEND from the environment with an SMTP default and no
    allow-list, so setting it to the console backend under a fully valid prod
    environment used to make Django write the message body to stdout — the JSONL
    log stream. prod.py now re-pins the SMTP backend, exactly as it pins DEBUG.
    This asserts the **resolved setting**, not the absence of a warning.
    """
    env = _prod_env_overrides(EMAIL_BACKEND=_CONSOLE_BACKEND)
    result = _run_in_subprocess(
        env,
        "import django; django.setup(); "
        "from django.conf import settings; "
        "print(f'email_backend={settings.EMAIL_BACKEND}')",
    )
    assert result.returncode == 0, result.stderr
    assert f"email_backend={_SMTP_BACKEND}" in result.stdout
    assert _CONSOLE_BACKEND not in result.stdout


def test_prod_staticfiles_backend_is_theme_storage() -> None:
    """prod settings resolve the static-files backend to the theme storage (CFG-007).

    The production decision is ``STORAGES["staticfiles"]["BACKEND"]`` in
    ``base.py``. ``prod.py`` used to redundantly assign
    ``STATICFILES_STORAGE``, which Django removed in 5.1 and which is therefore
    never read — deleting it changed nothing observable, and this test pins that
    observable behaviour.

    Asserting the **resolved** backend, not the absence of ``STATICFILES_STORAGE``,
    is the point: the absence test passes on a build where ``STORAGES`` silently
    reverted to Django's default (``StaticFilesStorage``), which would break the
    ``collectstatic`` manifest the Docker builder produces. If this test goes red,
    the fix is in ``base.py``'s ``STORAGES`` dict, not in a new ``prod.py`` line.
    """
    env = _prod_env_overrides()
    result = _run_in_subprocess(
        env,
        "import django; django.setup(); "
        "from django.conf import settings; "
        "print(f'static_backend={settings.STORAGES[\"staticfiles\"][\"BACKEND\"]}')",
    )
    assert result.returncode == 0, result.stderr
    assert f"static_backend={_THEME_STATICFILES_BACKEND}" in result.stdout


def test_dev_and_test_share_the_transport_tuple() -> None:
    """config.settings.dev and config.settings.test agree on all seven transport settings.

    ``test.py``'s comment claims it mirrors ``dev.py``. It resets
    ``SECURE_SSL_REDIRECT``, ``SESSION_COOKIE_SECURE`` and ``CSRF_COOKIE_SECURE``
    but used to inherit the HSTS triple from ``base.py`` (``3600`` / ``True`` /
    ``False``) while ``dev.py`` zeroes it — so the claim was aspirational. This
    test makes it machine-checked: a future edit to either module that moves a
    transport setting out of agreement fails here.

    ``test_migrations.py`` does ``from .test import *`` and therefore inherits
    every one of the seven values, which is intended (it is a test-mode module
    and must not emit HSTS any more than ``test`` does). Covering it would add a
    third subprocess import for a module whose only divergence is migration
    discovery and the test-database name, so it is deliberately left to inherit
    rather than pinned separately.
    """
    dev = _probe_transport_tuple("config.settings.dev")
    test = _probe_transport_tuple("config.settings.test")
    mismatches = {
        name: (dev[name], test[name])
        for name in _TRANSPORT_SETTINGS
        if dev[name] != test[name]
    }
    assert not mismatches, (
        "config.settings.dev and config.settings.test disagree on the transport "
        f"tuple (setting: (dev, test)): {mismatches}. test.py's comment asserts "
        "parity with dev.py; reset the setting in test.py, or correct the comment."
    )


# Import the settings module and the login-binding service in one subprocess and
# print the resolved name, flag, and settings value, so the pairing is observed
# exactly as the view will emit it (settings evaluated at import time, then the
# service's derivation applied). PROBE_MODULE is the full settings module path so
# the probe reads the same module the service resolves against.
_LOGIN_BINDING_PROBE_CODE = (
    "import os; "
    "os.environ['DJANGO_SETTINGS_MODULE'] = os.environ['PROBE_MODULE']; "
    "import django; "
    "django.setup(); "
    "from apps.users.services.login_token import ("
    "LOGIN_BROWSER_ID_COOKIE as name, "
    "LOGIN_BROWSER_ID_COOKIE_SECURE as secure, "
    "LOGIN_BROWSER_ID_COOKIE_HOST_PREFIX as prefix); "
    "print(f'prefix={prefix!r}'); "
    "print(f'name={name!r}'); "
    "print(f'secure={secure!r}')"
)


def _probe_login_binding(env_name: str) -> dict[str, str]:
    """Return the resolved login-binding ``{prefix, name, secure}`` for an env.

    ``env_name`` is the settings suffix (``base``/``dev``/``test``). ``base`` is
    evaluated with production-like env vars so it imports cleanly, mirroring the
    prod probe above; ``dev``/``test`` use the ambient env (they skip .env
    reading).
    """
    if env_name == "base":
        env = _prod_env_overrides()
    else:
        env = {k: v for k, v in os.environ.items()}
        env["DJANGO_SECRET_KEY"] = TEST_SECRET_KEY
    module_path = f"config.settings.{env_name}"
    env["DJANGO_SETTINGS_MODULE"] = module_path
    env["PROBE_MODULE"] = module_path
    result = _run_in_subprocess(env, _LOGIN_BINDING_PROBE_CODE)
    assert result.returncode == 0, result.stderr
    resolved: dict[str, str] = {}
    for line in result.stdout.splitlines():
        key, _, value = line.partition("=")
        resolved[key] = value
    assert set(resolved) == {"prefix", "name", "secure"}, (
        f"the login-binding probe did not report every value for {env_name}: "
        f"got {sorted(resolved)}"
    )
    return resolved


def test_login_binding_host_prefix_is_enabled_in_production() -> None:
    """base.py enables the ``__Host-`` login-binding control; dev/test disable it.

    ``test_dev_and_test_share_the_transport_tuple`` only compares ``dev`` against
    ``test``, so it stays green if a well-meaning edit flips ``base.py`` to
    ``False`` on all three modules at once — silently reopening the sibling-
    subdomain bypass in production. This pins the value that carries the entire
    fix, per module.
    """
    base = _probe_login_binding("base")
    dev = _probe_login_binding("dev")
    test = _probe_login_binding("test")
    assert base["prefix"] == repr(_LOGIN_BINDING_HOST_PREFIX_PROD), base
    assert dev["prefix"] == repr(_LOGIN_BINDING_HOST_PREFIX_DEV), dev
    assert test["prefix"] == repr(_LOGIN_BINDING_HOST_PREFIX_TEST), test


def test_login_binding_name_and_secure_flag_agree_per_module() -> None:
    """The resolved name and ``Secure`` flag agree under every settings module.

    The defect this guards is exactly a name/flag disagreement: a
    ``__Host-``-prefixed cookie emitted without ``Secure`` is rejected by every
    conformant user agent, so the cookie is discarded and each login becomes a
    ``410``. The invariant is stated as a rule — ``__Host-`` iff ``Secure`` — so
    it holds for any module and fails on either half of the original bug.
    """
    for env_name in ("base", "dev", "test"):
        resolved = _probe_login_binding(env_name)
        has_prefix = resolved["name"].startswith("'__Host-")
        is_secure = resolved["secure"] == "True"
        assert has_prefix == is_secure, (
            f"{env_name}: name {resolved['name']} and secure {resolved['secure']} "
            "disagree; a __Host- cookie without Secure is discarded by every "
            "conformant user agent"
        )
