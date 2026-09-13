"""Gunicorn configuration for the Mko Bazuna production runtime.

This file is auto-discovered by Gunicorn when the working directory is /app
(runtime container CWD). Only pure Python values are used so that
``preload_app`` can safely load the configuration before worker processes fork.
"""

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
