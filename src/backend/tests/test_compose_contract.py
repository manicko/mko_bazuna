"""
Compose environment contract tests (ENT-001, ENT-011, ENT-012).

Asserts that the process contract is expressed in the base ``docker-compose.yml``
and that no override contradicts it, plus the ``stop_grace_period`` and dev
``bot``/``seed`` asymmetry decisions. Follows the real-YAML parsing precedent of
``apps/core/tests/test_health_contract.py`` but parses each file independently —
``ruamel.yaml`` performs no Compose merge, so the contract is asserted per file
("the base declares it"; "no override contradicts it") rather than via a merged
``docker compose config`` view.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from ruamel.yaml import YAML

pytestmark = [pytest.mark.unit]

# Resolve the repository root by walking upward to pyproject.toml (it exists
# only at the repo root; this module lives at src/backend/tests/). Kept
# CWD-independent and free of any Django settings dependency.
_ROOT = Path(__file__).resolve().parent
while not (_ROOT / "pyproject.toml").exists():
    _ROOT = _ROOT.parent

_COMPOSE = _ROOT / "docker-compose.yml"
_PROD_COMPOSE = _ROOT / "docker-compose.prod.yml"
_DEV_OVERRIDE_COMPOSE = _ROOT / "docker-compose.dev.override.yml"
_TEST_COMPOSE = _ROOT / "docker-compose.test.yml"


def _load_yaml(path: Path) -> dict:
    """Parse a single compose file with ruamel.

    A stock ``YAML(typ="safe")`` cannot parse ``docker-compose.dev.override.yml``
    (uses the ``!reset`` tag) or ``docker-compose.test.yml`` (uses the
    ``!override`` tag) — it raises ``ConstructorError``. Both tags are registered
    as pass-through so the file parses. The tag is invisible after this: e.g.
    ``dev.services.seed.profiles`` parses as ``[]``, indistinguishable from a
    genuinely empty list. Do not attempt to verify the reset/override merge
    semantics — ruamel performs no merging.
    """
    yaml = YAML(typ="safe")
    for tag in ("!reset", "!override"):
        yaml.constructor.add_constructor(tag, lambda scn, node: node.value)
    with open(path, encoding="utf-8") as fh:
        data = yaml.load(fh)
    assert data is not None, f"{path.name} must parse to a mapping"
    return data


def _env_map(env: object) -> dict[str, str]:
    """Normalise a compose ``environment`` section to a dict of key -> value.

    Compose allows either a mapping (``KEY: value``) or a sequence of
    ``"KEY=value"`` strings. The base ``web`` service uses the sequence form;
    the base ``db`` service uses the mapping form. The form is asserted
    explicitly so a future base-file switch from sequence to mapping fails
    loudly rather than silently changing behaviour.
    """
    result: dict[str, str] = {}
    if isinstance(env, dict):
        for key, value in env.items():
            result[str(key)] = "" if value is None else str(value)
    elif isinstance(env, list):
        for item in env:
            key, sep, value = str(item).partition("=")
            result[key] = value if sep else ""
    else:
        raise AssertionError(f"unexpected environment form: {type(env)!r}")
    return result


# ---------------------------------------------------------------------------
# Prometheus multiprocess contract (ENT-001)
# ---------------------------------------------------------------------------


def test_base_web_declares_prometheus_contract_as_pair() -> None:
    """The base web service declares the variable AND its tmpfs as a pair.

    Asserting the variable alone would pass while leaving the service broken,
    since prometheus_client never creates the directory itself (see the tmpfs
    comment in docker-compose.yml).
    """
    data = _load_yaml(_COMPOSE)
    web = data["services"]["web"]
    env = _env_map(web["environment"])
    assert env.get("PROMETHEUS_MULTIPROC_DIR") == "/tmp/prometheus_multiproc", (
        "base web must set PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus_multiproc"
    )
    tmpfs = web.get("tmpfs", [])
    assert "/tmp/prometheus_multiproc:rw" in tmpfs, (
        "base web must mount tmpfs /tmp/prometheus_multiproc:rw"
    )


def test_base_web_environment_uses_sequence_form() -> None:
    """The base web environment is a sequence of ``K=V`` strings, not a mapping.

    Locks the sequence form so a future switch to the mapping form is a
    deliberate, reviewed change rather than a silent one.
    """
    data = _load_yaml(_COMPOSE)
    web = data["services"]["web"]
    assert isinstance(web["environment"], list), (
        "base web environment must use the sequence (list) form"
    )


def test_no_override_contradicts_prometheus_contract() -> None:
    """No override sets a competing value or tmpfs under the contract path."""
    for path in (_PROD_COMPOSE, _DEV_OVERRIDE_COMPOSE, _TEST_COMPOSE):
        data = _load_yaml(path)
        web = data.get("services", {}).get("web", {})
        env = _env_map(web.get("environment", {}))
        assert "PROMETHEUS_MULTIPROC_DIR" not in env, (
            f"{path.name} web must not set PROMETHEUS_MULTIPROC_DIR"
        )
        for mount in web.get("tmpfs", []):
            assert not str(mount).startswith("/tmp/prometheus_multiproc"), (
                f"{path.name} web must not declare a tmpfs under /tmp/prometheus_multiproc"
            )


def test_dockerfile_declares_no_prometheus_dir() -> None:
    """The Dockerfile must not declare a competing PROMETHEUS_MULTIPROC_DIR."""
    content = (_ROOT / "docker" / "Dockerfile").read_text(encoding="utf-8")
    assert "PROMETHEUS_MULTIPROC_DIR" not in content
    assert "prometheus_multiproc_dir" not in content


def test_base_web_runs_gunicorn_and_dev_replaces_with_runserver() -> None:
    """The base web command runs gunicorn; only dev replaces it with runserver.

    This is what makes the Prometheus contract meaningful: any environment
    whose web runs gunicorn inherits the contract from the base.
    """
    base_command = _load_yaml(_COMPOSE)["services"]["web"]["command"]
    assert isinstance(base_command, str) and "gunicorn" in base_command, (
        "base web command must run gunicorn"
    )
    dev_command = _load_yaml(_DEV_OVERRIDE_COMPOSE)["services"]["web"]["command"]
    assert isinstance(dev_command, str) and "runserver" in dev_command, (
        "dev override web command must replace gunicorn with runserver"
    )


# ---------------------------------------------------------------------------
# stop_grace_period contract (ENT-011)
# ---------------------------------------------------------------------------


def test_prod_long_lived_services_have_30s_stop_grace() -> None:
    """web, bot and scheduler in prod each carry stop_grace_period: 30s."""
    data = _load_yaml(_PROD_COMPOSE)
    for service in ("web", "bot", "scheduler"):
        svc = data["services"][service]
        assert svc.get("stop_grace_period") == "30s", (
            f"prod {service} must set stop_grace_period: 30s"
        )


def test_base_does_not_set_stop_grace_period() -> None:
    """The base long-lived services do not set stop_grace_period.

    So the prod value cannot be ambiguously inherited-and-overridden.
    """
    data = _load_yaml(_COMPOSE)
    for service in ("web", "bot"):
        assert "stop_grace_period" not in data["services"][service], (
            f"base {service} must not set stop_grace_period"
        )


# ---------------------------------------------------------------------------
# dev bot / seed asymmetry decision (ENT-012)
# ---------------------------------------------------------------------------


def test_dev_bot_has_no_depends_on_and_dev_web_depends_on_seed() -> None:
    """The asymmetry: dev web waits on seed, dev bot deliberately does not."""
    data = _load_yaml(_DEV_OVERRIDE_COMPOSE)
    bot = data["services"]["bot"]
    assert "depends_on" not in bot, (
        "dev bot must NOT depend on seed; the asymmetry is deliberate"
    )
    web = data["services"]["web"]
    assert "depends_on" in web and "seed" in web["depends_on"], (
        "dev web must depend on seed"
    )


def test_dev_bot_asymmetry_comment_present() -> None:
    """The recorded decision is stated in a comment on the dev bot block."""
    content = _DEV_OVERRIDE_COMPOSE.read_text(encoding="utf-8")
    assert "deliberately does NOT depend on seed" in content, (
        "dev bot block must carry the deliberate-asymmetry comment"
    )


# ---------------------------------------------------------------------------
# healthcheck start_period contract (12-OPS-019)
# ---------------------------------------------------------------------------

# Compose duration grammar: one or more `<number><unit>` groups (e.g. `30s`,
# `1m30s`, `1h`). Bare numbers (nanoseconds) are deliberately rejected — a probe
# window written as a bare integer is not the reviewed form.
_DURATION_GROUPS_RE = re.compile(r"^(?:\d+(?:\.\d+)?(?:ns|us|ms|s|m|h))+$")
_DURATION_TOKEN_RE = re.compile(r"\d+(?:\.\d+)?(?:ns|us|ms|s|m|h)")


def _is_parseable_duration(value: object) -> bool:
    """Whether *value* is a Compose duration string like ``30s`` or ``1m30s``.

    Guards a parseable duration, not the presence of the key: ``start_period:
    banana`` must fail. A bare integer (nanoseconds) is also rejected — the
    reviewed form is an explicit unit.
    """
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text or _DURATION_GROUPS_RE.match(text) is None:
        return False
    # Every character must be consumed by a duration token, so a trailing
    # garbage suffix cannot slip through.
    return "".join(_DURATION_TOKEN_RE.findall(text)) == text


def test_every_healthcheck_declares_a_parseable_start_period() -> None:
    """Every declared healthcheck carries a parseable ``start_period``.

    Each compose file is parsed independently (never merged with its override),
    so the contract is asserted per file. A missing key or a non-duration value
    (``start_period: banana``) fails, naming the ``(file, service)`` pair
    (12-OPS-019).
    """
    offenders: list[str] = []
    for path in (_COMPOSE, _TEST_COMPOSE, _PROD_COMPOSE):
        data = _load_yaml(path)
        services = data.get("services", {}) or {}
        for name, service in services.items():
            healthcheck = (service or {}).get("healthcheck")
            if healthcheck is None:
                continue
            value = healthcheck.get("start_period")
            if not _is_parseable_duration(value):
                offenders.append(f"{path.name}: {name} -> start_period={value!r}")

    assert not offenders, (
        "every healthcheck must declare a parseable start_period (12-OPS-019); "
        "missing or malformed:\n" + "\n".join(offenders)
    )


def test_is_parseable_duration_rejects_non_durations() -> None:
    """The duration guard fails on a non-duration value, not just a missing key.

    This is the ``start_period: banana`` case: the guard asserts a parseable
    duration, not the presence of the key string (12-OPS-019). Docker's own
    config parser rejects a bad value before it can ship, but this unit check
    keeps the guard's malformed branch covered independently of that.
    """
    for good in ("5s", "30s", "600s", "1m30s", "1h"):
        assert _is_parseable_duration(good), f"{good!r} must parse"
    for bad in ("banana", "", "15", "5sec", "5 s", None, 30):
        assert not _is_parseable_duration(bad), f"{bad!r} must not parse"


def test_start_period_does_not_alter_probe_cadence() -> None:
    """The four amended healthchecks keep interval/timeout/retries byte-identical.
    This block adds ``start_period`` and nothing else; changing ``retries``
    alters cold-start recovery semantics and is a different decision.
    """
    expected = {
        (_COMPOSE, "db"): ("5s", "5s", 5),
        (_COMPOSE, "redis"): ("5s", "3s", 5),
        (_TEST_COMPOSE, "db"): ("5s", "5s", 5),
        (_PROD_COMPOSE, "pgbouncer"): ("5s", "5s", 5),
    }
    for (path, service), (interval, timeout, retries) in expected.items():
        healthcheck = _load_yaml(path)["services"][service]["healthcheck"]
        assert healthcheck["interval"] == interval, f"{path.name} {service} interval"
        assert healthcheck["timeout"] == timeout, f"{path.name} {service} timeout"
        assert healthcheck["retries"] == retries, f"{path.name} {service} retries"
