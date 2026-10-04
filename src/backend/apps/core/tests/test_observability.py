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
