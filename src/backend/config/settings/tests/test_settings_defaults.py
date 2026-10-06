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

from apps.core.enums import LanguageLocale
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


# Probe the resolved ``NUMBER_GROUPING`` per locale. Django resolves each format
# attribute through ``FORMAT_MODULE_PATH`` before the bundled locale data, so
# the ``bs`` value comes from ``config.locale_formats`` while ``ru``/``en`` come
# from ``django.conf.locale.<lang>.formats``. ``django.setup()`` is required
# because ``get_format`` reads ``settings.FORMAT_MODULE_PATH``.
_NUMBER_GROUPING_PROBE_CODE = (
    "import django; django.setup(); "
    "from django.utils.formats import get_format; "
    "print('ru=' + repr(get_format('NUMBER_GROUPING', lang='ru'))); "
    "print('bs=' + repr(get_format('NUMBER_GROUPING', lang='bs'))); "
    "print('en=' + repr(get_format('NUMBER_GROUPING', lang='en')))"
)


def test_bs_number_grouping_override_matches_the_other_locales() -> None:
    """``FORMAT_MODULE_PATH`` gives ``bs`` the ``NUMBER_GROUPING`` it lacks (14-I18N-003).

    Django's bundled ``django.conf.locale.bs.formats`` leaves
    ``NUMBER_GROUPING`` undefined, and ``django.utils.numberformat`` gates
    thousands grouping on ``grouping != 0`` — the missing value defaults to 0, so
    ``bs`` prices were ungrouped even under ``force_grouping=True`` (the ``Q3``
    option (a) decision). ``base.py``'s ``FORMAT_MODULE_PATH`` supplies
    ``config.locale_formats.bs.formats`` with ``NUMBER_GROUPING = 3``.

    The subprocess imports ``base.py`` (through ``config.settings.prod``) and
    reads the **resolved** ``get_format`` value, so the test fails if the setting
    is dropped or the override package is unwired — not merely if a line is
    absent. ``ru`` and ``en`` must be unaffected: they take 3 from their bundled
    locale data, which this change must not disturb.
    """
    env = _prod_env_overrides()
    result = _run_in_subprocess(env, _NUMBER_GROUPING_PROBE_CODE)
    assert result.returncode == 0, result.stderr
    assert "ru=3" in result.stdout
    assert "bs=3" in result.stdout
    assert "en=3" in result.stdout


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


# The zone the Product Owner ruling of 2026-10-03 (Q4) fixed: hard-coded, not
# env-overridable. ``django.conf.global_settings`` defaults ``TIME_ZONE`` to
# "America/Chicago", so its absence from every settings module — not an explicit
# America/Chicago — is the defect (14-I18N-004).
_TIME_ZONE = "Europe/Podgorica"

# One known UTC instant used to prove the calendar day itself moves with the
# zone. Podgorica is UTC+1 in March (05:30 on the 16th); the America/Chicago
# default is UTC-5 (23:30 on the 15th), so the day-flip is observable.
_KNOWN_UTC_INSTANT = "2026-03-16T04:30:00+00:00"

# Locale format NAMES, never pattern strings: the display templates now pass
# these to the ``date`` filter, which resolves them through ``get_format``.
_DISPLAY_FORMAT_NAMES = ("DATE_FORMAT", "SHORT_DATE_FORMAT", "DATETIME_FORMAT")

# The two ISO ``<time datetime>`` attributes that are the machine-readable
# contract and must not be swept into the display-format change (constraint 8).
_ISO_DATETIME_TEMPLATES = (
    "src/backend/templates/ads/detail.html",
    "src/backend/templates/ads/partials/ad_list.html",
)

# Probe the resolved ``TIME_ZONE`` and localise the known instant with it, so the
# assertion observes the zone's effect on presentation rather than the setting
# name alone.
_TIME_ZONE_PROBE_CODE = (
    "import os; "
    "import django; django.setup(); "
    "import datetime; "
    "from django.conf import settings; "
    "from django.utils import timezone; "
    "print('time_zone=' + repr(settings.TIME_ZONE)); "
    "instant = datetime.datetime.fromisoformat(os.environ['PROBE_INSTANT']); "
    "print('local=' + timezone.localtime(instant).isoformat())"
)

# Render each display format name in each supported locale and, beside it, the
# same name resolved through ``get_format``. The pairs are compared in the test
# so a typo in a format name — which the ``date`` filter silently passes through
# as a literal instead of raising — fails the equality.
_LOCALE_DISPLAY_FORMAT_PROBE_CODE = (
    "import os; "
    "import django; django.setup(); "
    "import datetime; "
    "from django.utils import timezone, translation; "
    "from django.utils.formats import date_format; "
    "instant = datetime.datetime.fromisoformat(os.environ['PROBE_INSTANT']); "
    "local = timezone.localtime(instant); "
    "names = os.environ['PROBE_FORMAT_NAMES'].split(','); "
    "langs = os.environ['PROBE_LOCALES'].split(','); "
    "\nfor lang in langs:\n"
    "    translation.activate(lang)\n"
    "    for name in names:\n"
    "        expected = date_format(local, name)\n"
    "        print(f'{lang}.{name}|' + date_format(local, name))\n"
    "        print(f'{lang}.{name}.expected|' + expected)"
)


def _probe_time_zone(env_name: str) -> dict[str, str]:
    """Resolve ``TIME_ZONE`` and the localised known instant for an env.

    ``base`` is evaluated with production-like env vars so it imports cleanly;
    ``dev``/``test`` use the ambient env (they skip .env reading). The probe
    reads the resolved setting, so an ``env()``-sourced value would be observed.
    """
    if env_name == "base":
        env = _prod_env_overrides()
    else:
        env = {k: v for k, v in os.environ.items()}
        env["DJANGO_SECRET_KEY"] = TEST_SECRET_KEY
    module_path = f"config.settings.{env_name}"
    env["DJANGO_SETTINGS_MODULE"] = module_path
    env["PROBE_INSTANT"] = _KNOWN_UTC_INSTANT
    result = _run_in_subprocess(env, _TIME_ZONE_PROBE_CODE)
    assert result.returncode == 0, result.stderr
    resolved: dict[str, str] = {}
    for line in result.stdout.splitlines():
        key, _, value = line.partition("=")
        resolved[key] = value
    assert set(resolved) == {"time_zone", "local"}, (
        f"the time-zone probe did not report every value for {env_name}: "
        f"got {sorted(resolved)}"
    )
    return resolved


def test_time_zone_is_the_hardcoded_ruled_value() -> None:
    """``TIME_ZONE`` is the literal Europe/Podgorica under every module (14-I18N-004).

    The Q4 ruling (Product Owner, 2026-10-03) fixed the zone as a hard-coded
    value with no env surface. ``_prod_env_overrides`` starts from ``os.environ``,
    so if the setting were read through ``env("TIME_ZONE", ...)`` an ambient
    value would win — asserting the resolved setting catches that. ``dev`` and
    ``test`` are probed too, because a per-module override would reintroduce the
    drift the ruling closed.
    """
    for env_name in ("base", "dev", "test"):
        resolved = _probe_time_zone(env_name)
        assert resolved["time_zone"] == repr(_TIME_ZONE), resolved


def test_known_instant_renders_to_the_expected_local_wall_time() -> None:
    """A known UTC instant renders to the local wall time of Europe/Podgorica.

    Under Django's ``America/Chicago`` default the calendar day itself is wrong
    (2026-03-15), so this asserts the actual localised day, not merely that
    ``America/Chicago`` is absent. The rendered value is compared to a
    ``get_format``-derived expectation below, which is where the format
    resolution is checked.
    """
    resolved = _probe_time_zone("base")
    assert resolved["local"] == "2026-03-16T05:30:00+01:00", resolved


def test_display_format_names_drive_the_templates_per_locale() -> None:
    """The display templates' format names render as ``get_format`` dictates.

    The ``date`` filter resolves a locale format NAME through ``get_format``; an
    UNKNOWN name passes through as a literal and does NOT raise (the silent
    defect this guards). The probe therefore renders each of the three names in
    the four display templates under every ``LanguageLocale.values()`` member and
    compares it to the expectation derived from ``get_format`` for that locale —
    a typo in a name would leave the literal name in the output and fail here.
    Iterating ``LanguageLocale.values()`` (not bare ``("ru", "bs", "en")``)
    keeps this in step with the supported-locale set.
    """
    env = _prod_env_overrides()
    env["PROBE_INSTANT"] = _KNOWN_UTC_INSTANT
    env["PROBE_FORMAT_NAMES"] = ",".join(_DISPLAY_FORMAT_NAMES)
    env["PROBE_LOCALES"] = ",".join(LanguageLocale.values())
    result = _run_in_subprocess(
        env,
        _LOCALE_DISPLAY_FORMAT_PROBE_CODE,
    )
    assert result.returncode == 0, result.stderr
    rendered: dict[str, str] = {}
    expected: dict[str, str] = {}
    for line in result.stdout.splitlines():
        key, _, value = line.partition("|")
        if key.endswith(".expected"):
            expected[key.removesuffix(".expected")] = value
        else:
            rendered[key] = value
    expected_keys = {
        f"{lang}.{name}"
        for lang in LanguageLocale.values()
        for name in _DISPLAY_FORMAT_NAMES
    }
    assert set(rendered) == expected_keys, (
        f"the locale-format probe did not report every (locale, name) pair: "
        f"got {sorted(rendered)}"
    )
    for key in sorted(expected_keys):
        assert rendered[key] == expected[key], (
            f"{key}: rendered {rendered[key]!r} does not match the "
            f"get_format-derived expectation {expected[key]!r} — an unknown "
            "format name passes through as a literal instead of raising"
        )


def test_iso_datetime_attributes_are_byte_identical() -> None:
    """The two ``<time datetime>`` ISO attributes keep their ``'Y-m-d'`` pattern.

    Those attributes are the machine-readable contract (constraint 8), not
    display strings. This asserts the literal source text ``|date:'Y-m-d'`` in
    ``ads/detail.html`` and ``ads/partials/ad_list.html``, so a future sweep of
    the display patterns cannot quietly convert the machine-readable value to a
    locale format.
    """
    for rel_path in _ISO_DATETIME_TEMPLATES:
        html = (_ROOT / rel_path).read_text(encoding="utf-8")
        assert "datetime=\"{{ ad.published_at|date:'Y-m-d' }}\"" in html, (
            f"{rel_path}: the ISO <time datetime> attribute no longer carries "
            "the byte-identical 'Y-m-d' pattern"
        )
