"""Gunicorn configuration for the Mko Bazuna production runtime.

This file is auto-discovered by Gunicorn when the working directory is /app
(runtime container CWD). Only pure Python values are used so that
``preload_app`` can safely load the configuration before worker processes fork.
``os`` is a standard-library module with no Django dependency, so importing it
keeps that promise intact.
"""

import os

from prometheus_client import multiprocess

# Socket: bind to all interfaces on the HTTP port exposed by the container.
bind = "0.0.0.0:8000"

# Worker processes: 2 * CPU + 1 is the common heuristic; pinned at 3 for the
# container's expected allocation.
workers = 3

# Graceful request timeout (seconds) before a worker is killed and restarted.
timeout = 60

# Recycle each worker after this many requests to bound memory growth from
# gradual leaks. A jitter is added to spread restarts across workers.
max_requests = 1000
max_requests_jitter = 100

# Grace period (seconds) given to workers to finish in-flight requests on
# shutdown (SIGTERM) before the master force-kills them.
graceful_timeout = 30

# Log level for Gunicorn's own error/access logs.
loglevel = "info"

# Stream access and error logs to stdout/stderr so the container runtime
# captures them.
accesslog = "-"
errorlog = "-"

# Structured access log with named fields instead of a raw request line
# (12-OPS-012). The atoms are gunicorn's own (`%(h)s` remote address, `%(r)s`
# request line, `%(s)s` status, ...); the record is rendered by the redacting
# formatter configured below, so a sensitive-looking parameter in a request path
# (`?token=...`) comes back redacted instead of in the clear.
access_log_format = (
    '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(L)s'
)

# Route gunicorn's own loggers through the application's redacting JSON
# formatter (12-OPS-012). Gunicorn emits its access/error records through its OWN
# handlers, which never pass through Django's `LOGGING` tree, so the redactor had
# no effect on the highest-volume record type. `RedactingJsonFormatter` is a
# pure-stdlib class (no Django import), so a `dictConfig` factory reference
# resolves it here without `django.setup()`; this keeps `preload_app`'s
# config-parse-time promise intact. Gunicorn merges this dict over its own
# defaults with a SHALLOW update, so every sub-dict (`formatters`, `handlers`,
# `loggers`) is supplied whole. `accesslog`/`errorlog` above stay SET: if this
# config ever failed to load, a diagnostic plaintext line is far better than
# silence. A malformed config crashes the arbiter before the bind, so this dict
# is verified in a throwaway container (12-OPS-012).
logconfig_dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "apps.core.utils.json_logging.RedactingJsonFormatter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "stream": "ext://sys.stdout",
        },
        "error_console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "stream": "ext://sys.stderr",
        },
    },
    "loggers": {
        "gunicorn.error": {
            "level": "INFO",
            "handlers": ["error_console"],
            "propagate": False,
        },
        "gunicorn.access": {
            "level": "INFO",
            "handlers": ["console"],
            "propagate": False,
        },
    },
}

# Load the Django application in the master process before forking workers.
# Safe here because this module contains only pure Python values and performs
# no Django imports at parse time.
preload_app = True


def child_exit(server, worker):
    """Clean up multiprocess Prometheus metrics when a worker exits.

    Called by Gunicorn in the master process when a worker process exits.
    Removes the exiting worker's stale gauge files from PROMETHEUS_MULTIPROC_DIR
    so that the next /metrics scrape does not include dead-worker metrics.

    The call is guarded: ``prometheus_client.multiprocess`` resolves the
    directory from ``PROMETHEUS_MULTIPROC_DIR`` with a lowercase
    ``prometheus_multiproc_dir`` fallback. When neither is set the path is
    ``None`` and ``mark_process_dead`` raises ``TypeError`` inside
    ``os.path.join``; Gunicorn's arbiter only catches ``OSError`` around this
    hook, so the exception escapes to the loop-level handler, which stops the
    arbiter and exits 255. The truthiness check also treats an empty-string
    value as unset, matching ``django_prometheus``'s own presence check, so the
    hook and the /metrics export stay consistent.
    """
    path = os.environ.get("PROMETHEUS_MULTIPROC_DIR") or os.environ.get(
        "prometheus_multiproc_dir"
    )
    if path:
        multiprocess.mark_process_dead(worker.pid)


def worker_exit(server, worker):
    """Cancel the immediate-alert executor's queued work as a worker exits.

    ``preload_app = True`` means ``django.setup()`` runs in the master before
    workers fork, so the app (and the module-level ``ThreadPoolExecutor``) is
    constructed in the master. Worker-side-ness of the pool therefore depends
    on the *import* of ``immediate_alerts`` happening post-fork, which it does:
    ``apps/moderation/signals.py`` imports it lazily inside ``transaction.on_commit``.
    An ``atexit``/``ready()`` hook would belong to the master and would be a
    no-op for the forked children that hold the in-flight sends.

    ``worker_exit`` is the worker-side registration point: Gunicorn invokes it
    inside the child's own ``finally`` after ``worker.init_process()``, on the
    normal exit path. (``on_exit`` and ``worker_int`` are master-side.)
    ``concurrent.futures`` threads are non-daemon on Python 3.9+, so without
    this hook the interpreter joins them at exit and a worker can outlast the
    30 s ``graceful_timeout``; ``shutdown(wait=False, cancel_futures=True)``
    cancels queued work without blocking the exit.

    Both the import and the shutdown are guarded by a broad ``except Exception``:
    the one-shot containers (``migrate``, ``seed``, ``load_cities``,
    ``load_catalog``, ``create_admin``) never import the module, and an
    exception escaping this hook during Gunicorn's exit path is expensive — an
    unguarded ``TypeError`` from ``child_exit`` once escaped to the loop-level
    handler and stopped the arbiter with exit 255. The lazy import keeps this
    import-time module free of Django imports, preserving the ``preload_app``
    promise stated above.
    """
    try:
        from apps.search.services import immediate_alerts

        immediate_alerts._executor.shutdown(wait=False, cancel_futures=True)
    except Exception:
        # Best-effort cleanup on the exit path; never let this hook raise.
        pass
