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
