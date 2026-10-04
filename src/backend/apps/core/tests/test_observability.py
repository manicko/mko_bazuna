"""
Tests for Block B3 — Observability Wiring (finding 12-OPS-004).

Verifies that ``django-prometheus`` is properly wired into the application:
- ``django_prometheus`` is registered in ``INSTALLED_APPS``
- ``PrometheusBeforeMiddleware`` is the FIRST middleware entry
- ``PrometheusAfterMiddleware`` is the LAST middleware entry
- ``/metrics`` endpoint returns HTTP 200 with Prometheus exposition format
"""

from __future__ import annotations

import importlib.util
import re
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest
from django.conf import settings
from django.test import Client

pytestmark = [pytest.mark.unit]

_PROJECT_ROOT = settings.BASE_DIR.parent


# ---------------------------------------------------------------------------
# INSTALLED_APPS
# ---------------------------------------------------------------------------


def test_prometheus_in_installed_apps() -> None:
    """``django_prometheus`` is present in ``settings.INSTALLED_APPS``."""
    assert "django_prometheus" in settings.INSTALLED_APPS


# ---------------------------------------------------------------------------
# MIDDLEWARE ordering
# ---------------------------------------------------------------------------


def test_prometheus_middleware_ordering() -> None:
    """``PrometheusBeforeMiddleware`` is first and ``PrometheusAfterMiddleware`` is last.

    django-prometheus does not enforce ordering at runtime; the Before middleware
    must be index 0 and the After middleware must be the last entry so that
    latency histograms capture the full request lifecycle through all other
    middleware layers.
    """
    middleware = list(settings.MIDDLEWARE)
    assert middleware[0] == "django_prometheus.middleware.PrometheusBeforeMiddleware"
    assert middleware[-1] == "django_prometheus.middleware.PrometheusAfterMiddleware"


# ---------------------------------------------------------------------------
# /metrics endpoint
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_metrics_endpoint(client: Client) -> None:
    """``/metrics`` returns 200 with Prometheus exposition format markers."""
    response = client.get("/metrics")
    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "# HELP" in content or "# TYPE" in content


# ---------------------------------------------------------------------------
# SLO alert scrape contract (12-OPS-003)
# ---------------------------------------------------------------------------
# The alert file docs/ops/prometheus-slo-alerts.yaml names series in its `expr`
# selectors. Three of them previously named series the exposition never emits
# (`django_http_response_duration_seconds` with a `handler` label, and
# `redis_db_keyspace_hits_total` from an exporter that is not deployed), so the
# rules could never fire. This guard parses every `expr` in the file, extracts
# the series each one selects, and resolves them against a RENDERED `/metrics` —
# never against remembered library source (VAL-003). Adding a selector naming a
# series the exposition does not contain turns the test red.

_SLO_ALERTS_YAML = _PROJECT_ROOT / "docs" / "ops" / "prometheus-slo-alerts.yaml"

# A PromQL series selector is a metric name followed by an optional `{...}`.
# Metric names may carry `:` (recording rules) and `_`/digits.
_PROMQL_SERIES_RE = re.compile(r"\b([a-zA-Z_:][a-zA-Z0-9_:]*)\s*(?:\{[^}]*\})?")

# PromQL keywords and functions that look like identifiers but are not series.
_PROMQL_KEYWORDS = frozenset(
    {
        "rate",
        "sum",
        "by",
        "avg",
        "min",
        "max",
        "count",
        "histogram_quantile",
        "le",
        "instance",
        "job",
        "without",
        "on",
        "ignoring",
        "group_left",
        "group_right",
        "and",
        "or",
        "unless",
        "offset",
    }
)


def _exposed_series_names(exposition: str) -> set[str]:
    """Return the set of metric family names present in a `/metrics` exposition."""
    names: set[str] = set()
    for line in exposition.splitlines():
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)", line)
        if match:
            names.add(match.group(1))
    return names


def _alert_exprs(rules_text: str) -> list[str]:
    """Return every non-empty `expr:` value across all rules in the alert file.

    Parses the YAML structurally (ruamel) rather than slicing text, so a
    multi-line block scalar and an inline expression are both captured exactly.
    """
    from ruamel.yaml import YAML

    document = YAML(typ="safe").load(rules_text)
    exprs: list[str] = []
    for group in (document or {}).get("groups", []) or []:
        for rule in (group or {}).get("rules", []) or []:
            expr = (rule or {}).get("expr")
            if isinstance(expr, str) and expr.strip():
                exprs.append(expr)
    return exprs


def _series_in_expr(expr: str) -> set[str]:
    """Return the candidate metric names referenced by a PromQL expression.

    Label matchers inside `{...}` (names AND quoted values) are removed first,
    so only metric-name positions are scanned. PromQL function names and
    keywords are filtered out.
    """
    without_matchers = re.sub(r"\{[^}]*\}", "", expr)
    found: set[str] = set()
    for match in _PROMQL_SERIES_RE.finditer(without_matchers):
        name = match.group(1)
        if name in _PROMQL_KEYWORDS:
            continue
        found.add(name)
    return found


@pytest.mark.django_db
def test_slo_alert_selectors_resolve_against_rendered_metrics(
    client: Client,
) -> None:
    """Every series named by the SLO alert file exists in a rendered `/metrics`.

    The alert file is a contract (12-OPS-003): each `expr` must select a series
    the exporter actually exposes. This guard renders `/metrics` and fails if
    any alert names a series the exposition does not contain — which is exactly
    how the three dead rules shipped.
    """
    exposition = client.get("/metrics").content.decode("utf-8")
    exposed = _exposed_series_names(exposition)
    assert exposed, "the /metrics exposition contained no metric families"

    rules_text = _SLO_ALERTS_YAML.read_text(encoding="utf-8")
    exprs = _alert_exprs(rules_text)
    assert exprs, f"no `expr:` selectors found in {_SLO_ALERTS_YAML.name}"

    unknown: list[str] = []
    for expr in exprs:
        for series in _series_in_expr(expr):
            # A `_bucket`/`_count`/`_sum` selector resolves to its family base.
            base = series
            for suffix in ("_bucket", "_count", "_sum", "_created"):
                if base.endswith(suffix):
                    base = base[: -len(suffix)]
                    break
            if series in exposed or base in exposed:
                continue
            unknown.append(series)

    assert not unknown, (
        "the SLO alert file names series the /metrics exposition does not "
        "expose (12-OPS-003): " + ", ".join(sorted(set(unknown)))
    )


def test_scrape_contract_rejects_a_selector_naming_an_absent_series() -> None:
    """The scrape-contract detector fails on a selector naming an absent series.

    A guard that only passes today's three rules is not a contract. This feeds
    the detector a rule naming a series that does not exist and asserts it is
    reported — so adding such a selector turns
    ``test_slo_alert_selectors_resolve_against_rendered_metrics`` red.
    """
    exposed = {
        "django_http_requests_latency_including_middlewares_seconds_bucket",
        "django_http_requests_latency_including_middlewares_seconds_count",
    }
    bad_expr = (
        'rate(django_http_response_duration_seconds_bucket{le="2.000", '
        'handler="search:search"}[14.4m])'
    )
    unknown = set()
    for expr in [bad_expr]:
        for series in _series_in_expr(expr):
            base = series
            for suffix in ("_bucket", "_count", "_sum", "_created"):
                if base.endswith(suffix):
                    base = base[: -len(suffix)]
                    break
            if series not in exposed and base not in exposed:
                unknown.add(series)
    assert unknown, (
        "the detector must report a selector naming a series the exposition "
        "does not contain (12-OPS-003)"
    )
    # And it must NOT report a selector naming a real series.
    good_expr = (
        'rate(django_http_requests_latency_including_middlewares_seconds_bucket'
        '{le="2.5", view="search:search"}[14.4m])'
    )
    good_unknown = {
        s
        for s in _series_in_expr(good_expr)
        if s not in exposed and s.removesuffix("_bucket") not in exposed
    }
    assert not good_unknown, f"false positive on a valid selector: {good_unknown}"


def test_slo_alert_file_is_not_a_kubernetes_crd() -> None:
    """The alert file is a plain rules file, not a PrometheusRule CRD (12-OPS-003).

    The project runs Compose, not Kubernetes, and the previous CRD form
    (`apiVersion: monitoring.coreos.com/v1`, `kind: PrometheusRule`) was
    consumed by nothing. The file survives as a reviewable rules contract and is
    explicitly labelled "planned — not deployed".
    """
    text = _SLO_ALERTS_YAML.read_text(encoding="utf-8")
    assert "kind: PrometheusRule" not in text, (
        "the alert file must not be a Kubernetes PrometheusRule CRD (12-OPS-003)"
    )
    assert "monitoring.coreos.com" not in text, (
        "the alert file must not carry a Kubernetes apiVersion (12-OPS-003)"
    )
    assert "PLANNED" in text.upper(), (
        "the alert file must state that it is planned, not deployed (12-OPS-003)"
    )


def test_slo_alert_file_lints_as_loadable_rules() -> None:
    """A promtool-style lint: the file parses and every rule has the schema.

    `promtool` is not in the test image, so this is the pure-Python equivalent:
    it loads the YAML, checks each group has a `name` and a non-empty `rules`
    list, and that every rule carries `alert`, a non-empty `expr` and `labels`.
    A malformed rule turns it red — demonstrated by
    ``test_slo_alert_lint_detects_a_malformed_rule``.
    """
    from ruamel.yaml import YAML

    document = YAML(typ="safe").load(_SLO_ALERTS_YAML.read_text(encoding="utf-8"))
    _assert_rules_document_is_well_formed(document)


def _assert_rules_document_is_well_formed(document: object) -> None:
    """Assert a Prometheus rules document has the `promtool check rules` shape."""
    assert isinstance(document, dict), "rules file must parse to a mapping"
    groups = document.get("groups")
    assert isinstance(groups, list) and groups, "rules file must declare `groups`"
    seen_alerts: list[str] = []
    for group in groups:
        assert isinstance(group, dict), "each group must be a mapping"
        assert group.get("name"), "each rule group must declare a `name`"
        rules = group.get("rules")
        assert isinstance(rules, list) and rules, (
            "each rule group must declare a non-empty `rules` list"
        )
        for rule in rules:
            assert isinstance(rule, dict), "each rule must be a mapping"
            assert rule.get("alert"), "each rule must declare an `alert` name"
            expr = rule.get("expr")
            assert isinstance(expr, str) and expr.strip(), (
                "each rule must declare a non-empty `expr`"
            )
            assert isinstance(rule.get("labels"), dict), (
                "each rule must declare `labels`"
            )
            seen_alerts.append(rule["alert"])
    assert seen_alerts, "the rules file declared no alerts"


def test_slo_alert_lint_detects_a_malformed_rule() -> None:
    """The promtool-style lint fails on a malformed rule (12-OPS-003).

    A lint that has never been seen red is not a lint. This feeds the lint a
    document whose rule has no `expr` and asserts it raises.
    """
    malformed = {
        "groups": [
            {
                "name": "slo.broken",
                "rules": [{"alert": "broken_alert", "labels": {"severity": "page"}}],
            }
        ]
    }
    with pytest.raises(AssertionError):
        _assert_rules_document_is_well_formed(malformed)



@pytest.mark.django_db
def test_metrics_gate_rejects_non_loopback_remote_addr() -> None:
    """A ``/metrics`` request from a non-loopback peer is 403 (09-API-014).

    nginx carries ``allow 127.0.0.1; deny all;``, but that control does not
    cover a caller reaching the ``web`` container directly across the Docker
    bridge. The ``config/urls.py`` gate is the second control: a Docker-bridge
    source (``172.x``) is refused here. The test fails if the gate is removed —
    it is not a no-op.
    """
    response = Client(REMOTE_ADDR="172.18.0.4").get("/metrics")
    assert response.status_code == 403


@pytest.mark.django_db
def test_metrics_gate_allows_loopback() -> None:
    """A ``/metrics`` request from a loopback peer reaches the exporter."""
    response = Client(REMOTE_ADDR="127.0.0.1").get("/metrics")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Prometheus multiprocess mode (P1 — 12-OPS-011)
# ---------------------------------------------------------------------------


def test_prometheus_multiproc_dir_configured() -> None:
    """docker-compose.yml sets PROMETHEUS_MULTIPROC_DIR for the web service."""
    content = (_PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "PROMETHEUS_MULTIPROC_DIR" in content, (
        "docker-compose.yml must set PROMETHEUS_MULTIPROC_DIR for the web service"
    )


def test_gunicorn_has_child_exit_hook() -> None:
    """gunicorn.conf.py defines a child_exit hook for multiprocess cleanup."""
    content = (_PROJECT_ROOT / "gunicorn.conf.py").read_text(encoding="utf-8")
    assert "def child_exit" in content, (
        "gunicorn.conf.py must define a child_exit hook"
    )
    assert "mark_process_dead" in content, (
        "child_exit must call prometheus_client.multiprocess.mark_process_dead(worker.pid)"
    )


# ---------------------------------------------------------------------------
# gunicorn worker_exit hook — worker-side shutdown of the alert executor
# (09-API-013)
# ---------------------------------------------------------------------------


def test_gunicorn_has_worker_exit_hook_with_lazy_import() -> None:
    """gunicorn.conf.py defines a WORKER-side worker_exit that imports lazily.

    ``preload_app = True`` means an import-time (``atexit``/``ready()``) hook
    belongs to the master and is a no-op in the forked workers that own the
    in-flight sends. ``worker_exit`` runs inside the child's own exit path, so
    the hook must live there — and its import must be INSIDE the function body
    or the module becomes a Django import at config-parse time.
    """
    content = (_PROJECT_ROOT / "gunicorn.conf.py").read_text(encoding="utf-8")
    assert "def worker_exit" in content, (
        "gunicorn.conf.py must define a worker_exit hook"
    )
    assert "cancel_futures=True" in content, (
        "worker_exit must cancel queued work via shutdown(cancel_futures=True)"
    )
    # The exec of gunicorn.conf.py must not import Django: the import of
    # immediate_alerts appears only inside the worker_exit body, never at module
    # top level.
    assert "from apps.search.services import immediate_alerts" in content, (
        "worker_exit must import immediate_alerts to reach its executor"
    )
    module_level_imports = [
        line
        for line in content.splitlines()
        if line.startswith("from apps.") or line.startswith("import apps.")
    ]
    assert module_level_imports == [], (
        "gunicorn.conf.py must not import Django apps at module level: "
        f"{module_level_imports}"
    )


def test_worker_exit_shuts_down_alert_executor_without_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """worker_exit calls ``_executor.shutdown(wait=False, cancel_futures=True)``.

    The executor is monkeypatched with a Mock: executing the hook against the
    real module would shut down the session-wide global executor and silently
    break every later test that dispatches an alert. This mirrors
    ``_patch_mark_process_dead``.
    """
    from apps.search.services import immediate_alerts

    gunicorn_conf = _load_gunicorn_conf()

    shutdown = Mock()
    monkeypatch.setattr(immediate_alerts._executor, "shutdown", shutdown)

    gunicorn_conf.worker_exit(None, _worker())

    shutdown.assert_called_once_with(wait=False, cancel_futures=True)


def test_worker_exit_import_failure_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An import failure inside worker_exit is swallowed (guarded lazy import)."""
    gunicorn_conf = _load_gunicorn_conf()

    import builtins

    real_import = builtins.__import__

    def _boom(name: str, *args: object, **kwargs: object):
        if name == "apps.search.services":
            raise ImportError("simulated")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _boom)

    # Must not raise: the guard keeps the exit path safe in containers that
    # never import the alert module (migrate, seed, load_cities, ...).
    gunicorn_conf.worker_exit(None, _worker())


# ---------------------------------------------------------------------------
# gunicorn child_exit hook guard (ENT-001)
# ---------------------------------------------------------------------------


def _load_gunicorn_conf() -> ModuleType:
    """Load gunicorn.conf.py from the repository root by file path.

    The repository root is not on ``src/``'s import path (``pyproject.toml``
    sets ``pythonpath = ["src", "src/backend"]``), so the module is loaded with
    ``importlib`` against ``settings.BASE_DIR.parent / "gunicorn.conf.py"``.
    """
    module_path = _PROJECT_ROOT / "gunicorn.conf.py"
    spec = importlib.util.spec_from_file_location("gunicorn_conf", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _worker(pid: int = 4242) -> SimpleNamespace:
    """A minimal fake gunicorn worker exposing only ``pid``."""
    return SimpleNamespace(pid=pid)


def _patch_mark_process_dead(
    gunicorn_conf: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> Mock:
    """Patch the module under test's ``multiprocess.mark_process_dead`` binding.

    The config does ``from prometheus_client import multiprocess`` (a module
    object, not a name), so patching ``gunicorn_conf.multiprocess.mark_process_dead``
    intercepts the call made inside ``child_exit``.
    """
    mock = Mock()
    monkeypatch.setattr(gunicorn_conf.multiprocess, "mark_process_dead", mock)
    return mock


def test_child_exit_unset_dir_does_not_raise_or_mark(monkeypatch) -> None:
    """With the directory unset, child_exit neither raises nor marks."""
    gunicorn_conf = _load_gunicorn_conf()
    # Delete BOTH casings. On Windows os.environ is case-insensitive, so
    # deleting only the uppercase name also clears a lowercase one and the test
    # would then pass on the dev machine for the wrong reason, masking a
    # regression in the Linux container.
    monkeypatch.delenv("PROMETHEUS_MULTIPROC_DIR", raising=False)
    monkeypatch.delenv("prometheus_multiproc_dir", raising=False)
    mock = _patch_mark_process_dead(gunicorn_conf, monkeypatch)
    gunicorn_conf.child_exit(None, _worker())
    mock.assert_not_called()


def test_child_exit_uppercase_dir_calls_mark_with_pid(monkeypatch) -> None:
    """An uppercase PROMETHEUS_MULTIPROC_DIR makes child_exit mark the pid."""
    gunicorn_conf = _load_gunicorn_conf()
    monkeypatch.delenv("PROMETHEUS_MULTIPROC_DIR", raising=False)
    monkeypatch.delenv("prometheus_multiproc_dir", raising=False)
    monkeypatch.setenv("PROMETHEUS_MULTIPROC_DIR", "/tmp/prometheus_multiproc")
    mock = _patch_mark_process_dead(gunicorn_conf, monkeypatch)
    gunicorn_conf.child_exit(None, _worker(pid=9000))
    mock.assert_called_once_with(9000)


def test_child_exit_lowercase_dir_calls_mark_with_pid(monkeypatch) -> None:
    """A lowercase prometheus_multiproc_dir fallback also makes it mark."""
    gunicorn_conf = _load_gunicorn_conf()
    monkeypatch.delenv("PROMETHEUS_MULTIPROC_DIR", raising=False)
    monkeypatch.delenv("prometheus_multiproc_dir", raising=False)
    monkeypatch.setenv("prometheus_multiproc_dir", "/tmp/prometheus_multiproc")
    mock = _patch_mark_process_dead(gunicorn_conf, monkeypatch)
    gunicorn_conf.child_exit(None, _worker(pid=1234))
    mock.assert_called_once_with(1234)


def test_child_exit_empty_dir_does_not_raise_or_mark(monkeypatch) -> None:
    """An empty-string value is treated as unset (truthiness decision)."""
    gunicorn_conf = _load_gunicorn_conf()
    monkeypatch.delenv("PROMETHEUS_MULTIPROC_DIR", raising=False)
    monkeypatch.delenv("prometheus_multiproc_dir", raising=False)
    monkeypatch.setenv("PROMETHEUS_MULTIPROC_DIR", "")
    mock = _patch_mark_process_dead(gunicorn_conf, monkeypatch)
    gunicorn_conf.child_exit(None, _worker())
    mock.assert_not_called()
