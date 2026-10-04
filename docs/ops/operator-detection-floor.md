# Operator detection floor

**Finding:** `12-OPS-011` (reduced scope — Q10 option (b), Product Owner, 2026-10-03).

This document states, plainly, **what an operator actually receives today** when
a production container goes unhealthy or a backup job stops succeeding. It is the
"detection floor": the signals that exist, how to read them, and the gap that
remains open.

## The floor, stated honestly

**There is no paging path.** No management command, service, signal, webhook or
host-side job inspects container health, dump freshness, deploy outcome or the
SLO rules. A container stuck `unhealthy` and a backup job that died a week ago
are discovered by a human looking, or by users filing complaints.

Per the 2026-10-03 decision (Q10 option (b)), the operator-notification floor is
a **machine-readable signal**, not a Telegram command. The Telegram
`manage.py notify_operator` command was **DECLINED**; no recipient configuration
key exists; `ALLOWED_ENV_VARS` and the four `.env.*.example` files are untouched.

## The signals, and how to read them

Both signals are machine-readable **at the Docker layer**. Neither is a
Prometheus metric, because the monitoring stack is deferred (Q5 option (c)) and
the `web` container does not mount the host backup directory.

### 1. Container health

Docker records a health status for every service that declares a `healthcheck:`,
and `web`, `bot`, `scheduler`, `backup` and `pgbouncer` all do.

```
docker inspect --format '{{.Name}} {{.State.Health.Status}}' $(docker compose -f docker-compose.yml -f docker-compose.prod.yml ps -q)
```

A non-zero count of `unhealthy` entries is the signal.

### 2. Backup dump freshness

The `backup` service's healthcheck (`docker/healthcheck-backup.sh`) is a
**freshness** probe, not a liveness one. It fails when the newest
`dump_*.dump` is older than `BACKUP_HEALTH_STALE_SECONDS` (48 h — two 24 h
cycles), so a backup job that has stopped succeeding turns the container
`unhealthy` instead of failing silently:

```
docker inspect --format '{{.State.Health.Status}}' "$(docker compose -f docker-compose.yml -f docker-compose.prod.yml ps -q backup)"
```

A dump-age signal equivalent to the healthcheck is reachable directly on the
host:

```
newest=$(ls -1t /backups/dump_*.dump 2>/dev/null | head -n 1)
echo "newest dump age (s): $(( $(date +%s) - $(stat -c %Y "$newest") ))"
```

## The residual gap — named, not closed

The signals above are produced and machine-readable, but **nothing alerts on
them**. Q5 deferred the monitoring stack, so during this programme there is no
consumer: the signals are not exposed on `/metrics`, are not scraped, and do not
page anyone. **Detection is unchanged, and `12-OPS-011` is not closed.**

The SLO artefacts (`prometheus-slo-alerts.yaml`, `grafana-slo-dashboard.json`)
are labelled **"planned — not deployed"** for the same reason and are not active
controls.

## What would close it

A deployed scraper that:
1. reads the Docker health status (or a metric that mirrors it), and
2. reads the newest-dump age (or the backup healthcheck's verdict),

and routes a page when either is bad. That is the deferred stack; it is not
delivered here and this document must not be read as claiming it is.
