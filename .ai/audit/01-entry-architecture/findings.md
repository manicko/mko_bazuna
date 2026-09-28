---
# Report metadata — fill once per phase report.
phase: "01"
phase_name: "Entry Points & Process Architecture"
date: "2026-09-28"
auditor: "Executor (subagent)"
validator: ""  # Phase 99 only — omit/blank for raw phase findings
mode: "problems-only"
id_prefix: "ENT"
report_status: "draft"
severity_taxonomy: ".kilo/commands/audit/phases/01-audit-entry-architecture.md#severity-taxonomy"
---

# Audit Findings — Entry Points & Process Architecture

## Executive Summary

Fourteen problems were found in how the system's long-running processes start, stop and
coordinate. Five are HIGH: the web server can crash on every worker restart, the background
job runner ignores the standard "please stop" signal for up to an hour, the daily
notification job can send users duplicate messages after a restart, the entire Telegram bot
process is excluded from the automated code-quality gate, and the login handshake logic is
duplicated independently in two different processes. The broadest business impact is on
reliability of the two long-running services: routine restarts and redeployments currently
end in forced kills rather than clean shutdowns, and users can receive the same daily alert
digest twice. The migration "run exactly once" guarantee itself is sound and was verified
under concurrent start.

## Scope & Methodology

**Scope:** The process topology and entry layer of the N-process Django system: the web WSGI
entrypoint and its gunicorn configuration, the bot process entrypoint (`telegram_bot/main.py`,
lifecycle hooks, middlewares, handlers), the profile-gated scheduler loop
(`apps/core/utils/scheduler.py` + `docker/entrypoint-scheduler.sh`), the one-shot migration
gate (`bootstrap_reference_data` → `migrate_locked` → advisory lock 100), the shared ORM
settings module, the URL router, the three-layer compose topology (base / dev override /
test / prod override), and every Docker entrypoint script. Business-logic depth inside views
and handlers was assessed only to the extent it constitutes entry-layer leakage.

### Runtime Verification

| R# | Check | Method | Result |
|----|-------|--------|--------|
| R-01 | Both entry modules import in isolation with no import-time side effects | `docker run … python -c "import config.wsgi; import telegram_bot.main; import apps.core.utils.scheduler"` | PASS |
| R-02 | Same imports with an unreachable DB (`DATABASE_URL=…@127.0.0.1:1/none`) to prove no import-time DB/network access | same command + `DATABASE_URL` override | PASS |
| R-03 | Web process boots, reaches ready state, and health probes answer | `gunicorn config.wsgi:application` in container; `curl /health/live/`, `/health/ready/` | PASS |
| R-04 | Bot process fails fast with a clear error and non-zero exit on an invalid token | `python -m telegram_bot.main` with a syntactically valid fake token | PASS |
| R-05 | Scheduler process boots, validates all 11 command names, dispatches a cycle, honours the per-command timeout | `python -m apps.core.utils.scheduler` with `SCHEDULER_COMMAND_TIMEOUT=1` | PASS |
| R-06 | Migration gate serializes concurrent runs (advisory lock 100) | two near-simultaneous `bootstrap_reference_data` containers + a two-thread `lock_timeout=4s` contention probe | PASS |
| R-07 | Graceful shutdown of gunicorn on SIGTERM | `docker stop -t 40` on a booted web container | **FAIL** (arbiter traceback, exit 255) |
| R-08 | Graceful shutdown of gunicorn on worker recycle | `--max-requests 2`, two requests issued | **FAIL** (arbiter traceback, exit 255) |
| R-09 | Scheduler honours SIGTERM within `stop_grace_period` (30 s) | `docker stop -t 30` on the scheduler container | **FAIL** (exit 137 = SIGKILL) |
| R-10 | Linter (`ruff check src/`) | containerized ruff | PASS (exit 0) |
| R-11 | Type checker in CI scope (`basedpyright .` from `src/backend`) | containerized basedpyright | **FAIL** (12 errors, exit 1) |
| R-12 | Type checker across the whole tree (`basedpyright src/`) | containerized basedpyright | **FAIL** (16 errors, exit 1) |
| R-13 | Test suite (fast gate) | `.\Makefile.ps1 test` | PASS (2394 passed, 0 failed, 167 s) |
| R-14 | Shared state lives only in DB / media FS (no process-local state assumed across processes) | static read of `scheduler.run_scheduler` + `send_alerts` | **FAIL** (see ENT-003) |

> PASS results prove the audit was thorough; they are METHODOLOGY evidence, NOT findings.

**Tools used:** `docker run` / `docker compose run` (image `mko-bazuna-test-test`,
`mko-bazuna-test-web`), `docker logs`, `docker inspect`, `docker stop -t N`, `ruff`,
`basedpyright`, `pytest` (via `.\Makefile.ps1 test`), `psql` (via `docker exec`), AST-based
`python -c` scanners (reverse-import detection, blocking-IO detection, unwrapped-ORM
detection, module-size census), `ast`-introspection of the installed `aiogram` 3.30.0 source
(`MiddlewareManager.wrap_middlewares`, `Dispatcher.start_polling`) and of
`prometheus_client.multiprocess.mark_process_dead`.

**Assumptions:** "Production runs `docker-compose.yml` + `docker-compose.prod.yml` with
`config.settings.prod`"; "production Redis cache is `django-redis`, not LocMemCache";
"PostgreSQL 18"; "Django 5.2 LTS on CPython 3.14 (not PyPy)"; "the bot runs as a single
process (aiogram `run_polling`, no replica set)"; "`.\Makefile.ps1 test` is representative of
the CI test job for R-13".

## Findings Summary

| ID | Title | Severity | Status | Category |
|----|-------|----------|--------|----------|
| ENT-001 | Gunicorn arbiter dies on every worker exit when `PROMETHEUS_MULTIPROC_DIR` is unset | HIGH | Open | Reliability / Availability |
| ENT-002 | Scheduler ignores SIGTERM for up to one hour; production stop is always SIGKILL | HIGH | Open | Reliability / Operability |
| ENT-003 | Daily-job dedupe state is process-local; `send_alerts` re-sends duplicate digests after a restart | HIGH | Open | Correctness / Data integrity |
| ENT-004 | Entire bot process is outside the CI lint + typecheck scope, and the typecheck gate is red | HIGH | Open | Maintainability / Correctness |
| ENT-005 | Two-phase login-claim protocol implemented twice inside entry handlers with divergent persistence | HIGH | Open | Separation of concerns / Correctness |
| ENT-006 | Migration advisory lock has no acquisition timeout; documented "skip" semantics are wrong | MEDIUM | Open | Operability / Documentation |
| ENT-007 | Bot readiness marker is written only after four sequential Telegram API calls | MEDIUM | Open | Operability |
| ENT-008 | Test-container bootstrap creates a migration-less schema in the non-test database, fail-open | MEDIUM | Open | Correctness / Test infrastructure |
| ENT-009 | Cross-process media race: orphan sweep can delete freshly promoted, not-yet-referenced files | MEDIUM | Open | Data integrity |
| ENT-010 | Bot middleware stack performs 4–6 I/O round-trips and one DB handshake per inbound update | MEDIUM | Open | Performance / Resource management |
| ENT-011 | `bot` service has no `stop_grace_period` in the production override | LOW | Open | Operability |
| ENT-012 | Dev startup gating is asymmetric: `web` waits for `seed`, `bot` does not | LOW | Open | Operability |
| ENT-013 | Scheduler liveness marker cannot distinguish "loop alive" from "jobs succeeded" | LOW | Open | Observability |
| ENT-014 | `entrypoint-test.sh` header comment wrongly claims the base entrypoint runs migrations | LOW | Open | Documentation |

## Distribution

**Severity counts**

| CRITICAL | HIGH | MEDIUM | LOW |
|-----------|------|--------|-----|
| 0 | 5 | 5 | 4 |

**Status counts**

| Status | Count |
|--------|-------|
| Open | 14 |

## Findings by Severity

### HIGH

#### ENT-001: [HIGH] — Gunicorn arbiter dies on every worker exit when `PROMETHEUS_MULTIPROC_DIR` is unset

| Field | Value |
|---|---|
| **ID** | ENT-001 |
| **Title** | Gunicorn arbiter dies on every worker exit when `PROMETHEUS_MULTIPROC_DIR` is unset |
| **Severity** | HIGH |
| **Category** | Reliability / Availability |
| **File(s)** | `gunicorn.conf.py:43`, `docker-compose.prod.yml:14`, `docker-compose.yml:219`, `docker-compose.test.yml:124` |
| **Status** | Open |
| **Problem** | The gunicorn config registers a `child_exit` hook that calls `prometheus_client.multiprocess.mark_process_dead(worker.pid)` unconditionally. That function reads `PROMETHEUS_MULTIPROC_DIR` and, when the variable is unset, passes `None` into `os.path.join()` and raises `TypeError`. The exception propagates out of gunicorn's `Arbiter.stop() → reap_workers() → cfg.child_exit()`, so the **arbiter (master) process itself terminates** instead of reaping the worker and continuing. Only `docker-compose.prod.yml` sets `PROMETHEUS_MULTIPROC_DIR`; the base compose, the test override, and the Docker image `ENV` do not. |
| **Impact** | Any deployment that uses the shared `gunicorn.conf.py` without that single env var loses the whole web process — not just the worker — every time a worker exits. Because `max_requests = 1000` is set, that is a routine, load-driven event: the web container enters a crash loop, drops in-flight traffic, and (under `restart: unless-stopped`) restarts only to repeat. A normal `docker stop` also ends in exit code 255 rather than 0, which makes orchestrators treat an orderly shutdown as a crash. |
| **Root Cause** | The hook is written as if the multiproc directory always exists, but the requirement lives outside the config file (in a single Compose override) with no guard and no validation at gunicorn startup. |
| **Recommendation** | Make the hook conditional: `if os.environ.get("PROMETHEUS_MULTIPROC_DIR"): multiprocess.mark_process_dead(worker.pid)`. Additionally set `PROMETHEUS_MULTIPROC_DIR` (with the matching tmpfs mount) on the `web` service in the **base** compose so every environment that inherits `gunicorn.conf.py` has the same contract. |
| **Effort** | S (≈10 lines, 1 file) |
| **Priority** | P0 |

| Field | Value |
|---|---|
| **Related Findings** | ENT-011 (same class of "compose override is the only place the process contract is expressed") |

**Evidence — `gunicorn.conf.py:43`** *(supports: "the hook calls `mark_process_dead` unconditionally, with no guard on `PROMETHEUS_MULTIPROC_DIR`")*:
```python
def child_exit(server, worker):
    """Clean up multiprocess Prometheus metrics when a worker exits.
    ...
    """
    multiprocess.mark_process_dead(worker.pid)
```

**Evidence — `docker logs ent-web-boot` (SIGTERM path)** *(supports: "the arbiter, not just the worker, terminates — exit 255 on an ordinary shutdown")*:
```text
[2026-09-27 16:48:38 -0500] [7] [INFO] Handling signal: term
[2026-09-27 16:48:38 -0500] [19] [INFO] Worker exiting (pid: 19)
Traceback (most recent call last):
  ...
  File "/opt/venv/lib/python3.14/site-packages/gunicorn/arbiter.py", line 650, in reap_workers
    self.cfg.child_exit(self, worker)
  File "/app/gunicorn.conf.py", line 50, in child_exit
    multiprocess.mark_process_dead(worker.pid)
  File "/opt/venv/lib/python3.14/site-packages/prometheus_client/multiprocess.py", line 182, in mark_process_dead
    for f in glob.glob(os.path.join(path, f'gauge_{mode}_{pid}.db')):
TypeError: expected str, bytes or os.PathLike object, not NoneType
$ docker inspect ent-web-boot -> ExitCode 255   (docker stop -t 40)
```

**Evidence — `docker logs ent-web-recycle2` (`--max-requests 2`)** *(supports: "the crash is load-driven, not shutdown-specific — two HTTP requests were enough to kill the master")*:
```text
[2026-09-28 01:28:39 -0500] [14] [INFO] Autorestarting worker after current request.
[2026-09-28 01:28:39 -0500] [14] [INFO] Worker exiting (pid: 14)
[2026-09-28 01:28:39 -0500] [1] [ERROR] Unhandled exception in main loop
  File "/opt/venv/lib/python3.14/site-packages/gunicorn/arbiter.py", line 271, in handle_chld
    self.reap_workers()
  File "/app/gunicorn.conf.py", line 50, in child_exit
    multiprocess.mark_process_dead(worker.pid)
TypeError: expected str, bytes or os.PathLike object, not NoneType
$ docker inspect ent-web-recycle2 -> "Exited (255)"
```

---

#### ENT-002: [HIGH] — Scheduler ignores SIGTERM for up to one hour; production stop is always SIGKILL

| Field | Value |
|---|---|
| **ID** | ENT-002 |
| **Title** | Scheduler ignores SIGTERM for up to one hour; production stop is always SIGKILL |
| **Severity** | HIGH |
| **Category** | Reliability / Operability |
| **File(s)** | `src/backend/apps/core/utils/scheduler.py:293`, `src/backend/apps/core/utils/scheduler.py:305`, `docker/entrypoint-scheduler.sh:21`, `docker-compose.prod.yml:88` |
| **Status** | Open |
| **Problem** | `main()` installs a SIGTERM/SIGINT handler that only sets `threading.Event _stop_event`, and `run_scheduler()` checks that event **at the top of the loop** and then blocks in `sleep_func(interval_seconds)` = `time.sleep(3600)`. Under PEP 475 a signal delivered during `time.sleep` runs the handler and then **resumes the sleep for the remaining timeout**; the loop therefore does not observe the stop flag until the sleep finishes. The production stop grace period is 30 s, so Docker escalates to SIGKILL long before the loop can break. |
| **Impact** | Every stop, redeploy, `docker compose restart`, or host reboot of the scheduler ends in `exit 137` instead of a clean exit. The documented ENT-002 guarantee ("exits cleanly after the current cycle, closing Django DB connections in a `finally` teardown") is never delivered in production: `_shutdown()` never runs, no shutdown log line is emitted, and the exit code is indistinguishable from an OOM or a hard kill. Because the signal can also land while a sweep command is mid-flight, the scheduler is routinely terminated in the middle of `delete_sweep` / `consent_hard_delete` rather than at a cycle boundary. |
| **Root Cause** | The stop signal is modelled as a cooperative flag checked between iterations, but the loop's dominant state is a *blocking sleep*, not the work. Nothing makes the wait interruptible. |
| **Recommendation** | Replace the blocking sleep with an interruptible wait: make `_stop_event` the thing being waited on, e.g. default `sleep_func=lambda s: _stop_event.wait(s)` (or `threading.Event().wait`) and keep the injection point for tests. The signal handler then breaks the wait immediately, the loop exits, and `_shutdown()` closes DB connections. Add a test that sends a real `SIGTERM` to a live scheduler and asserts a zero exit within a few seconds (the existing tests inject a `lambda s: None` sleep, which is why they do not catch this). |
| **Effort** | S (≈5 lines + 1 integration test) |
| **Priority** | P0 |

| Field | Value |
|---|---|
| **Related Findings** | ENT-013 (the same loop's readiness signal), ENT-011 (stop-grace asymmetry) |

**Evidence — `src/backend/apps/core/utils/scheduler.py:293`** *(supports: "the stop flag is only observed at the top of the loop, and the loop then blocks in a 3600 s `time.sleep`")*:
```python
    while True:
        if _stop_event.is_set():
            logger.info("Stop flag set — exiting scheduler loop after completed cycle")
            break
        try:
            last_daily = run_one_cycle(...)
        except Exception:
            logger.exception("Scheduler cycle failed — continuing")
        sleep_func(interval_seconds)      # <-- time.sleep(3600); PEP 475 resumes after the signal
```

**Evidence — `docker stop -t 30 ent-sched` + `docker inspect`** *(supports: "the process did not exit on SIGTERM within the 30 s grace period and was SIGKILLed")*:
```text
$ docker run -d --name ent-sched … -e SCHEDULER_COMMAND_TIMEOUT=1 … python -m apps.core.utils.scheduler
Command archive_sweep timed out after 1 seconds
… (9 hourly commands dispatched, cycle completes) …
$ docker stop -t 30 ent-sched
ent-sched
$ docker inspect ent-sched --format 'ExitCode={{.State.ExitCode}}'
ExitCode=137            # 128 + SIGKILL(9) — never a clean exit
```

**Evidence — PEP 475 probe (`ent-sigprobe`)** *(supports: "a Python-level signal handler does not shorten the remaining `time.sleep`; the loop only notices the flag when the sleep completes")*:
```text
signal received at t=18.27
loop noticed stop flag at t=24.00      # ~5.7 s later == the remaining duration of time.sleep(6)
$ docker ps -a --filter name=ent-sigprobe -> "Exited (0)"
```

---

#### ENT-003: [HIGH] — Daily-job dedupe state is process-local; `send_alerts` re-sends duplicate digests after a restart

| Field | Value |
|---|---|
| **ID** | ENT-003 |
| **Title** | Daily-job dedupe state is process-local; `send_alerts` re-sends duplicate digests after a restart |
| **Severity** | HIGH |
| **Category** | Correctness / Data integrity |
| **File(s)** | `src/backend/apps/core/utils/scheduler.py:292`, `src/backend/apps/core/utils/scheduler.py:104`, `src/backend/apps/search/management/commands/send_alerts.py:64`, `src/backend/apps/search/management/commands/send_alerts.py:151` |
| **Status** | Open |
| **Problem** | The "run daily jobs once per calendar day" decision is made from a plain in-memory local, `last_daily: date \| None`, initialised to `None` on every process start. `should_run_daily()` returns `True` whenever `last_daily is None and now.hour >= DAILY_HOUR_UTC`. The daily set includes `send_alerts`, which is **not** idempotent: it bulk-creates `AnalyticsEvent(SEARCH_ALERT_MATCHED)` rows without `ignore_conflicts`, and it sends the actual Telegram digests **outside** the advisory lock and outside the transaction, with no per-day delivery marker. `rollup_daily_metrics` is idempotent (`update_or_create` keyed on `yesterday`), but `send_alerts` is not. |
| **Impact** | Any restart of the scheduler after 08:00 UTC (deploy, crash, `docker compose restart`, node reboot) causes `send_alerts` to run a second time **on the same calendar day**. Every buyer with an active saved search receives a duplicate alert digest, and the analytics table gains a second `SEARCH_ALERT_MATCHED` row per saved search, permanently inflating the `SEARCH_ALERT_MATCHED` metric that the daily rollup aggregates. `SavedSearchNotification` rows are protected by the `uq_saved_search_ad` unique constraint, but the *user-visible message* and the *analytics events* are not, so the damage is exactly on the two things that matter. This violates the phase invariant that shared state lives only in the DB / media FS, not in process memory. |
| **Root Cause** | The idempotency contract for scheduled jobs is split: the advisory lock provides *mutual exclusion* between concurrent runs but never *deduplication across runs*, and the only dedupe record (`last_daily`) is discarded on restart. Nothing in the DB records "today's alert digest has already been dispatched". |
| **Recommendation** | Make the daily marker durable rather than in-memory: persist the last-run date (DB row or a Redis key with a >24 h TTL, Redis being already a hard dependency of both long-lived processes) and have `run_one_cycle` read/update it. Independently, make `send_alerts` delivery idempotent by recording dispatch state in the DB (e.g. a `sent_at` on `SavedSearchNotification` plus a daily-dispatch marker) and by wrapping `AnalyticsEvent.objects.bulk_create(...)` in `ignore_conflicts=True`. Moving the digest send inside a durable "claim" step also removes the current gap where delivery happens after the advisory lock is released. |
| **Effort** | M (2–4 person-days: durable marker + idempotent delivery + tests) |
| **Priority** | P0 |

| Field | Value |
|---|---|
| **Related Findings** | ENT-002 (a restart is the trigger), ENT-013 (the liveness marker cannot reveal the duplicate run) |

**Evidence — `src/backend/apps/core/utils/scheduler.py:292`** *(supports: "the daily dedupe record is a process-local variable reset to `None` on every start")*:
```python
    logger.info("Scheduler started (interval=%s seconds)", interval_seconds)
    last_daily: date | None = None          # <- process-local; gone after any restart
    while True:
        ...
        new_last_daily = last_daily
        if should_run_daily(now, last_daily, DAILY_HOUR_UTC):
            for cmd in DAILY_COMMANDS:      # ["send_alerts", "rollup_daily_metrics"]
                _dispatch(cmd, run_command)
            new_last_daily = now.date()
```

**Evidence — `src/backend/apps/core/utils/scheduler.py:104`** *(supports: "a fresh process at or after 08:00 UTC always re-fires the daily set")*:
```python
    if last_daily is None or now.date() != last_daily:
        return now.hour >= daily_hour_utc
    return False
```

**Evidence — `src/backend/apps/search/management/commands/send_alerts.py:64`** *(supports: "delivery is neither de-duplicated nor protected by the lock, and analytics rows are inserted without `ignore_conflicts`")*:
```python
        with transaction.atomic():
            with advisory_lock(AdvisoryLockId.ALERT_DELIVERY_TASK):
                user_ads, notifications_to_create, analytics_events = self._collect_alerts()
                self._persist_alerts(notifications_to_create, analytics_events)

        # Send messages outside the transaction (network I/O)   <- lock already released
        asyncio.run(self._send_user_digests(settings.BOT_TOKEN, user_ads))
...
    def _persist_alerts(self, notifications_to_create, analytics_events) -> None:
        if notifications_to_create:
            SavedSearchNotification.objects.bulk_create(notifications_to_create, ignore_conflicts=True)
        if analytics_events:
            AnalyticsEvent.objects.bulk_create(analytics_events)   # no ignore_conflicts -> duplicates
```

---

#### ENT-004: [HIGH] — Entire bot process is outside the CI lint + typecheck scope, and the typecheck gate is red

| Field | Value |
|---|---|
| **ID** | ENT-004 |
| **Title** | Entire bot process is outside the CI lint + typecheck scope, and the typecheck gate is red |
| **Severity** | HIGH |
| **Category** | Maintainability / Correctness |
| **File(s)** | `.github/workflows/ci.yml:178`, `.github/workflows/ci.yml:200`, `src/telegram_bot/handlers/alerts.py:83`, `src/telegram_bot/handlers/contact.py:277`, `Makefile:128` |
| **Status** | Open |
| **Problem** | The CI `lint` job runs `uv run ruff check .` and the `typecheck` job runs `uv run basedpyright .`, both with `working-directory: src/backend`. `src/telegram_bot` — the whole asynchronous bot process, i.e. the highest-risk entry layer in the system (event loop, `sync_to_async` boundaries, raw SQL) — is never scanned by either job. The local `make lint` / `make typecheck` targets do use `src/` and therefore *do* see it, so local and CI disagree about the gate. Worse, the gate itself is currently failing: `basedpyright .` in CI's own scope returns exit 1 with 12 errors, and `basedpyright src/` returns exit 1 with 16 errors, two of which are in production bot handlers. |
| **Impact** | The one long-running process whose runtime is hardest to reproduce has no automated static gate: regressions in the async entry layer are only caught by the pytest suite, and only if a test happens to exercise the changed path. The already-red typecheck job additionally means either CI is blocking all merges or the job is being ignored — in both cases the type gate provides no protection today. Because `pyproject.toml` sets `reportMissingImports = "none"` and CI does not set `PYTHONPATH`, the two production errors only surface at all when `PYTHONPATH=/app/src:/app/src/backend` is present (the image `ENV`); in CI's own invocation environment they are invisible even if the scope were widened. |
| **Root Cause** | The CI jobs were written against the Django project root while the repository actually contains two top-level Python packages (`src/backend` and `src/telegram_bot`), and the container image — not the workflow — is what makes both importable. |
| **Recommendation** | Run the static gates from the repository root with explicit extra paths, e.g. `uv run basedpyright --pythonpath . src` and `uv run ruff check src` with `PYTHONPATH=src:src/backend`, and drop the `working-directory: src/backend` override. Then fix the 16 reported errors (all are either test-side `with transaction.atomic():` context-manager complaints or model-field inference noise) so the gate is green again; "production code is king" means the fix belongs in the tests, not in production behaviour. |
| **Effort** | S–M (workflow change + ≤16 error fixes) |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **Related Findings** | none (adjacent to the code-quality phase, but the scope gap is a property of the process/CI topology) |

**Evidence — `.github/workflows/ci.yml:178` and `:200`** *(supports: "both static gates are scoped to `src/backend` only")*:
```yaml
  lint:
      - name: Run ruff
        run: uv run ruff check .
        working-directory: src/backend
  typecheck:
      - name: Run basedpyright
        run: uv run basedpyright .
        working-directory: src/backend
```

**Evidence — typecheck runs** *(supports: "the CI-scope gate is red, and widening the scope to `src/` reveals 4 further errors, 2 of them in production bot handlers")*:
```text
$ basedpyright .            # workdir /app/src/backend  (CI scope)
12 errors, 0 warnings, 0 notes          -> exit 1
  .../apps/ads/tests/test_edit_views_locking.py:239 - error: Object of type "(...) -> object" cannot be used with "with"
  .../apps/moderation/tests/test_admin_actions.py:529 - error: ... __enter__ / __exit__

$ basedpyright src/         # workdir /app   (what `make typecheck` runs)
16 errors, 0 warnings, 0 notes          -> exit 1
  /app/src/telegram_bot/handlers/alerts.py:83   - error: "__getitem__" method not defined on type "TextField"
  /app/src/telegram_bot/handlers/contact.py:277 - error: Type "BigIntegerField | None" is not assignable to "int | None"
  /app/src/telegram_bot/tests/test_ad_create.py:358,373 - error: "write" is not a known attribute of "None"

$ PYTHONPATH= basedpyright src/telegram_bot      # CI-like import resolution
2 errors, 0 warnings, 0 notes                   -> the 2 production errors disappear
$ ruff check src/ && ruff check src/telegram_bot && ruff check src/theme
All checks passed! (exit 0 both)
```

---

#### ENT-005: [HIGH] — Two-phase login-claim protocol implemented twice inside entry handlers with divergent persistence

| Field | Value |
|---|---|
| **ID** | ENT-005 |
| **Title** | Two-phase login-claim protocol implemented twice inside entry handlers with divergent persistence |
| **Severity** | HIGH |
| **Category** | Separation of concerns / Correctness |
| **File(s)** | `src/backend/apps/users/views/consent.py:381`, `src/backend/apps/users/views/consent.py:298`, `src/telegram_bot/handlers/login.py:154`, `src/telegram_bot/handlers/login.py:190` |
| **Status** | Open |
| **Problem** | Login is a **cross-process** protocol (web issues a token → bot claims it with its `telegram_id` → web polls and consumes it → web establishes the session), but the protocol lives entirely in the two entry handlers with no shared service owning its invariants. `src/telegram_bot/handlers/login.py` implements phase 1 as hand-written `UPDATE login_tokens … RETURNING` SQL with the eligibility rules inlined in the `WHERE` clause. `src/backend/apps/users/views/consent.py` implements phase 2 with the ORM (`LoginToken.objects.filter(...).update(consumed_at=...)`) and re-derives the same expiry/consumed/telegram_id rules in Python. `login_issue` additionally mints the token, hashes it, applies two rate limits and writes the row directly in the view; `login_status` additionally performs the ban check, `auth_login`, and a two-query preferred-city reconciliation, all in a 470-line view module. |
| **Impact** | The same domain rule ("a token is claimable iff unclaimed, unconsumed and unexpired") is encoded twice, in two persistence styles (raw SQL vs ORM) in two processes. A change to the eligibility rules on one side silently breaks the other, and because the failure mode is "user is stuck in the login loop" it is only discovered in production. The rules also cannot be unit-tested independently of HTTP/Telegram, and the token lifecycle has no single owner, which is exactly the class of defect the project's separation-of-concerns rule exists to prevent. |
| **Root Cause** | There is no `apps.users.services` counterpart for the login handshake; the view and the handler each became the de-facto service. |
| **Recommendation** | Extract the handshake into `apps/users/services/login_token.py` with two explicit operations — `issue_token()`, `claim_token(token_hash, telegram_id, now)` and `consume_token(token_hash, expected_telegram_id)` — each one transaction, each owning the eligibility predicate, each using the ORM (or, if the `UPDATE … RETURNING` form is kept for the TOCTOU guarantee, in exactly one place with the web side calling the same function). Leave the handlers as parse → delegate → respond, and have the view delegate the ban check / session establishment order to the service rather than re-implementing it. |
| **Effort** | M (3–5 person-days including test migration) |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **Related Findings** | none |

**Evidence — `src/telegram_bot/handlers/login.py:169`** *(supports: "phase 1 encodes the token eligibility rules in raw SQL inside the bot handler")*:
```python
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE login_tokens
               SET telegram_id = %s
             WHERE token_hash = %s
               AND telegram_id IS NULL
               AND consumed_at IS NULL
               AND expires_at > %s
            RETURNING id, token_hash, telegram_id, created_at, expires_at, consumed_at
            """,
            [telegram_id, token_hash, now],
        )
```

**Evidence — `src/backend/apps/users/views/consent.py:404`** *(supports: "phase 2 re-derives the same rules with the ORM inside the HTTP view, then continues with ban check, session login and city reconciliation")*:
```python
    with transaction.atomic():
        try:
            token = LoginToken.objects.get(token_hash=token_hash)
        except LoginToken.DoesNotExist:
            return HttpResponse(status=410)
        if token.expires_at <= timezone.now() or token.consumed_at is not None:
            return HttpResponse(status=410)
        if token.telegram_id is None:
            return HttpResponse(status=204)
        updated = LoginToken.objects.filter(
            token_hash=token_hash, telegram_id=token.telegram_id,
            consumed_at__isnull=True, expires_at__gt=timezone.now(),
        ).update(consumed_at=timezone.now())
        ...
    user = User.objects.get(telegram_id=token.telegram_id)
    if not can_login(user): ...
    auth_login(request, user)
    _reconcile_preferred_city_on_login(request, user)   # 2 more queries, still in the view
```

**Evidence — module-size census** *(supports: "the largest view module in the system is the one that also owns the cross-process handshake")*:
```text
     470  backend/apps/users/views/consent.py
     413  backend/apps/search/views/search.py
     347  backend/apps/ads/views/edit.py
     306  telegram_bot/handlers/ad_create/category.py
     263  telegram_bot/handlers/login.py
```

---

### MEDIUM

#### ENT-006: [MEDIUM] — Migration advisory lock has no acquisition timeout; documented "skip" semantics are wrong

| Field | Value |
|---|---|
| **ID** | ENT-006 |
| **Title** | Migration advisory lock has no acquisition timeout; documented "skip" semantics are wrong |
| **Severity** | MEDIUM |
| **Category** | Operability / Documentation |
| **File(s)** | `src/backend/apps/core/utils/migrate_locked.py:5`, `src/backend/apps/core/utils/advisory_lock.py:74`, `src/backend/apps/core/utils/migrate_locked.py:85` |
| **Status** | Open |
| **Problem** | `migrate_locked.py`'s module docstring states "Idempotent: subsequent runs will find lock already held and **skip**." The implementation calls `SELECT pg_advisory_lock(100)`, which **blocks** until the holder releases — it never skips, and it is never bounded. `SCHEDULER_COMMAND_TIMEOUT` (default 1800 s) bounds each *child* `manage.py` invocation, not the wait for the lock itself, and no `lock_timeout` / `statement_timeout` is set on the holder connection. |
| **Impact** | If a `migrate` container wedges (a hung child command, an OOM-killed grandchild that leaves the parent alive, a paused node), every later migration attempt — `docker compose up`, `make migrate`, the test container's `bootstrap_reference_data` — blocks **indefinitely and silently**, with no log line, while `web` and `bot` sit waiting on `migrate: service_completed_successfully`. Operators see a hung `docker compose up` with no explanation. The migration-once guarantee itself is intact (verified, R-06) — this is about diagnosability and boundedness, not about duplicate migrations. |
| **Root Cause** | The lock is acquired with the blocking variant and no acquisition deadline, while the docstring describes a non-existent try-lock-and-skip behaviour. |
| **Recommendation** | Decide the intended semantics and implement it. Either (a) set `lock_timeout` before acquiring so a contending run fails fast with a clear message ("another migration run holds lock 100; retry after it completes"), or (b) keep blocking but emit a log line before acquisition and document the blocking behaviour. Update the docstring either way. |
| **Effort** | S (1 file + docstring) |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **Related Findings** | ENT-008 (same bootstrap path, different failure mode) |

**Evidence — `src/backend/apps/core/utils/migrate_locked.py:5`** *(supports: "the documented semantics are 'skip', which the implementation does not provide")*:
```python
"""
One-shot migration runner with advisory lock.
Session-scoped lock safe because migrate runs before PgBouncer is attached.
Idempotent: subsequent runs will find lock already held and skip.
"""
```

**Evidence — `src/backend/apps/core/utils/advisory_lock.py:74`** *(supports: "the blocking lock variant is used, with no timeout around acquisition")*:
```python
        if session:
            cursor.execute("SELECT pg_advisory_lock(%s)", [lock_id])
            logger.info("Acquired session advisory lock %s", lock_id)
            try:
                yield
            finally:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [lock_id])
```

**Evidence — lock-contention probe** *(supports: "a contending holder blocks rather than skipping; only PostgreSQL's own `lock_timeout` breaks the wait")*:
```text
A: ACQUIRED lock after 0.00s
B: BLOCKED OperationalError: canceling statement due to lock timeout   # only because the probe SET lock_timeout='4s'
A: RELEASED
RESULT: {'B': 'blocked', 'A': 'ok'}
```

---

#### ENT-007: [MEDIUM] — Bot readiness marker is written only after four sequential Telegram API calls

| Field | Value |
|---|---|
| **ID** | ENT-007 |
| **Title** | Bot readiness marker is written only after four sequential Telegram API calls |
| **Severity** | MEDIUM |
| **Category** | Operability |
| **File(s)** | `src/telegram_bot/lifecycle.py:106`, `src/telegram_bot/lifecycle.py:92`, `src/telegram_bot/lifecycle.py:124`, `docker-compose.yml:299` |
| **Status** | Open |
| **Problem** | `_on_startup` first awaits `_set_bot_commands(bot)`, which issues **four sequential** `set_my_commands` requests (ru, bs, en, then the no-language default), and only afterwards writes the file liveness marker and the Redis `bot:liveness` key. The loop is `for lang, commands in _COMMANDS.items(): await bot.set_my_commands(...)` with no overall deadline of its own, so worst-case readiness latency is roughly 4 × the aiohttp request timeout. The Compose healthcheck allows `start_period: 30s`, `interval: 30s`, `retries: 3` — i.e. the container is declared unhealthy after ≈120 s. |
| **Impact** | When Telegram's API is slow (or rate-limiting the bot at startup, which is a real scenario for a freshly deployed bot), a perfectly healthy bot is reported `unhealthy` for the whole registration window, and the web `/health/ready/` probe's Redis input (`bot:liveness`) is stale or absent for the same period. Because the healthcheck cannot restart a container, the result is a false alarm that masks a real outage — the alert signal becomes untrustworthy precisely when Telegram is misbehaving. The command-menu registration is also, by design, fail-open and non-critical, so it should not gate readiness. |
| **Root Cause** | Startup performs optional, best-effort work (command menu registration) *before* publishing the readiness signal, with no per-call or overall budget. |
| **Recommendation** | Write the file and Redis liveness markers **first**, then perform `set_my_commands` with a bounded budget (e.g. `asyncio.wait_for(..., timeout=10)` around the whole registration, or a single `default` call with the rest best-effort). Readiness then reflects "polling is about to start", not "Telegram answered four times". |
| **Effort** | S (reorder + one `wait_for`, ~15 lines) |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **Related Findings** | ENT-013 (readiness signalling in the sibling process) |

**Evidence — `src/telegram_bot/lifecycle.py:106`** *(supports: "readiness markers are published only after the four API calls complete")*:
```python
async def _on_startup(*args: Any, **kwargs: Any) -> None:
    bot = kwargs.get("bot")
    if bot is not None:
        try:
            await _set_bot_commands(bot)          # 4 sequential network round-trips
        except Exception:
            logger.warning("Failed to register bot commands at startup")
    path = _marker_path()
    if path:
        Path(path).touch()                        # readiness published only now
        logger.info("Bot liveness marker written: %s", path)
    await _write_redis_marker()
```

**Evidence — `src/telegram_bot/lifecycle.py:92`** *(supports: "the four calls are sequential and each is individually unbounded by the startup path")*:
```python
    for lang, commands in _COMMANDS.items():      # ru, bs, en
        try:
            await bot.set_my_commands(commands, language=lang)
        except Exception:
            logger.warning("Failed to set bot commands for language %s; continuing", lang)
            continue
    try:
        await bot.set_my_commands(_COMMANDS["en"])   # 4th, default scope
    except Exception:
        logger.warning("Failed to set default bot commands; continuing")
```

**Evidence — `docker logs ent-bot-boot`** *(supports: "all four calls are real network round-trips that gate the marker; a rejected token burns all four before failing")*:
```text
Failed to set bot commands for language ru; continuing
Failed to set bot commands for language bs; continuing
Failed to set bot commands for language en; continuing
Failed to set default bot commands; continuing
...
aiogram.exceptions.TelegramUnauthorizedError: Telegram server says - Unauthorized
$ docker ps -a --filter name=ent-bot-boot -> "Exited (1)"
```

---

#### ENT-008: [MEDIUM] — Test-container bootstrap creates a migration-less schema in the non-test database, fail-open

| Field | Value |
|---|---|
| **ID** | ENT-008 |
| **Title** | Test-container bootstrap creates a migration-less schema in the non-test database, fail-open |
| **Severity** | MEDIUM |
| **Category** | Correctness / Test infrastructure |
| **File(s)** | `docker/entrypoint-test.sh:25`, `src/backend/config/settings/test.py:28`, `src/backend/config/settings/test.py:96`, `src/backend/apps/core/management/commands/bootstrap_reference_data.py:20` |
| **Status** | Open |
| **Problem** | The test entrypoint runs `bootstrap_reference_data`, which delegates to `migrate_locked.main()` and dispatches `migrate --noinput --run-syncdb` as a **subprocess**. Because `test.py` pins `DATABASES["default"]["NAME"] = "mko_bazuna"` (not `test_mko_bazuna`) *and* sets `MIGRATION_MODULES = DisableMigrations()` for every app, that subprocess creates the entire schema by syncdb in the **non-test** `mko_bazuna` database with no migration records at all. The step is wrapped in `|| true`, so any DDL failure is silently swallowed. `bootstrap_reference_data`'s own docstring documents exactly this hazard and explains why `conftest.py` avoids this command — yet the test entrypoint still uses it. |
| **Impact** | Every `make test` run leaves behind a phantom 39-table database in the test PostgreSQL instance that no test uses, is invisible to the suite's own bootstrap path (which correctly uses `AdvisoryLockId.TEST_SCHEMA_SETUP` against `test_mko_bazuna`), and whose `django_migrations` table does not even exist. Any later tooling that connects to that database — `manage.py showmigrations`, `migrate --plan`, a developer's IDE, a `pg_restore` smoke test — sees "all migrations pending" against tables that already exist, and the fail-open `|| true` means the operator gets no signal that the bootstrap silently did nothing useful. |
| **Root Cause** | A bootstrap designed for a real, migration-managed database is reused in an environment where migrations are disabled and the database name is deliberately pinned, and the two facts are not reconciled at the call site. |
| **Recommendation** | Either point the test bootstrap at the test database and run it under `AdvisoryLockId.TEST_SCHEMA_SETUP` like `conftest.py` does, or drop the step from `entrypoint-test.sh` entirely and let `conftest.py`'s autouse fixture own the trigger/seed bootstrap (it already does). If the step is kept for any reason, remove `|| true` so a real DDL failure is visible. |
| **Effort** | S (edit `docker/entrypoint-test.sh`; verify the suite still passes) |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **Related Findings** | ENT-006 (same bootstrap path) |

**Evidence — `docker/entrypoint-test.sh:25`** *(supports: "the bootstrap runs in the test container and is fail-open")*:
```bash
# Fail-open (|| true) preserves the lenient test-entrypoint policy: a DDL or
# trigger error must not block the test suite from running.
uv run python src/backend/manage.py bootstrap_reference_data || true
```

**Evidence — bootstrap output from the real test run** *(supports: "every app is syncdb-synced and no migration is applied")*:
```text
Operations to perform:
  Synchronize unmigrated apps: admin, ads, analytics, auth, cabinet, categories,
  contenttypes, core, currencies, django_htmx, django_prometheus, locations,
  lookups, media, messages, moderation, mptt, search, seed, sessions, staticfiles,
  tailwind, theme, trust, users
  Apply all migrations: (none)
Synchronizing apps without migrations:
  Creating tables...
    Running deferred SQL...
Running migrations:
  No migrations to apply.
```

**Evidence — `psql` against the test instance** *(supports: "the non-test `mko_bazuna` database holds a full schema with no migration history")*:
```text
$ psql -U postgres -d mko_bazuna -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';"
 39
$ psql -U postgres -d mko_bazuna -c "SELECT count(*) FROM django_migrations;"
ERROR:  relation "django_migrations" does not exist
```

**Evidence — `src/backend/apps/core/management/commands/bootstrap_reference_data.py:20`** *(supports: "the hazard is already known and documented, and the test entrypoint still calls the command")*:
```python
``conftest.py`` deliberately does **not** use this command: it calls
``call_command`` in-process under ``AdvisoryLockId.TEST_SCHEMA_SETUP`` (111)
instead, because ``migrate_locked.main()`` spawns subprocesses that would
connect to the hardcoded ``mko_bazuna`` database rather than pytest-django's
``test_mko_bazuna`` test database
```

---

#### ENT-009: [MEDIUM] — Cross-process media race: orphan sweep can delete freshly promoted, not-yet-referenced files

| Field | Value |
|---|---|
| **ID** | ENT-009 |
| **Title** | Cross-process media race: orphan sweep can delete freshly promoted, not-yet-referenced files |
| **Severity** | MEDIUM |
| **Category** | Data integrity |
| **File(s)** | `src/backend/apps/ads/services/submission.py:166`, `src/backend/apps/media/services/filesystem.py:44`, `src/backend/apps/media/management/commands/sweep_orphaned_media.py:138` |
| **Status** | Open |
| **Problem** | `submit_ad` intentionally calls `move_staging_to_permanent()` **before** opening its `transaction.atomic()` block, so a DB rollback leaves the promoted files as reclaimable orphans. The trade-off is a window in which files exist at their permanent paths but no `AdImage` row references them yet. The orphan sweep — running hourly in a **separate scheduler process**, holding only `AdvisoryLockId.SWEEP_ORPHANED_MEDIA` (103) — computes `orphans = on_disk - referenced` and deletes every match. `submit_ad` never takes lock 103, so nothing serialises the two processes. The sweep's own comment ("no writes, so no advisory lock is strictly needed") only holds for the DB side; the *filesystem* side is written by another process. |
| **Impact** | If the sweep's walk lands inside that window, it deletes images for an ad that is about to commit successfully. The result is a published ad whose `AdImage` rows point at files that no longer exist — a broken listing that no later sweep will repair, because the sweep only deletes unreferenced files and will never recreate a missing one. The window is short (milliseconds) so the rate is low, but the failure is permanent and user-visible, and it recurs on every scheduler restart that happens to coincide with a submission. |
| **Root Cause** | The DB↔filesystem consistency strategy is "write files first, then rows, and let the sweeper clean up rollback leftovers", but the sweeper's definition of "unreferenced" is evaluated at a different instant than the writer's, in a different process, with no shared lock or grace marker for freshly promoted files. |
| **Recommendation** | Close the window with the mechanism already used for abandoned uploads: have `move_staging_to_permanent` leave a short-lived marker (e.g. a `.pending` sibling file, or a DB row in a "recently promoted" table) that the sweep treats as referenced, and have it expire only after the sweep interval. Alternatively, take `AdvisoryLockId.SWEEP_ORPHANED_MEDIA` in `submit_ad` around promotion + commit so the two operations are mutually exclusive. The marker approach avoids making ad submission depend on a scheduler lock. |
| **Effort** | M (2–3 person-days including a concurrency test) |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **Related Findings** | none (the media phase may cover the same code path from the storage side) |

**Evidence — `src/backend/apps/ads/services/submission.py:161`** *(supports: "files are promoted before the transaction opens, creating the unreferenced window")*:
```python
    # Promote staging files to permanent storage BEFORE the transaction.
    # ... On DB rollback the permanent files become unreferenced orphans
    # reclaimed by the normal orphan sweep.
    move_staging_to_permanent(input.photos)

    # DB transaction: save + images + status transition
    with transaction.atomic():
        ad = Ad.objects.select_for_update().get(id=input.ad_id)
        ...
```

**Evidence — `src/backend/apps/media/management/commands/sweep_orphaned_media.py:134`** *(supports: "the sweep deletes every on-disk file with no matching `AdImage` row, under a lock the submit path does not take")*:
```python
        # Snapshot referenced keys before deleting anything (the DB side is
        # read-only here — no writes, so no advisory lock is strictly needed,
        # but we take it to avoid two instances racing on filesystem cleanup).
        with transaction.atomic():
            with advisory_lock(AdvisoryLockId.SWEEP_ORPHANED_MEDIA):
                referenced = _collect_referenced_keys()   # AdImage rows only
                on_disk = set(_walk_media_files(media_root))
                orphans = on_disk - referenced
                ...
```

---

#### ENT-010: [MEDIUM] — Bot middleware stack performs 4–6 I/O round-trips and one DB handshake per inbound update

| Field | Value |
|---|---|
| **ID** | ENT-010 |
| **Title** | Bot middleware stack performs 4–6 I/O round-trips and one DB handshake per inbound update |
| **Severity** | MEDIUM |
| **Category** | Performance / Resource management |
| **File(s)** | `src/telegram_bot/middlewares/update_id_dedup.py:59`, `src/telegram_bot/middlewares/lifecycle.py:171`, `src/telegram_bot/middlewares/language.py:53`, `src/telegram_bot/middlewares/permissions.py:103`, `src/telegram_bot/middlewares/permissions.py:112`, `src/telegram_bot/middlewares/permissions.py:130`, `src/telegram_bot/middlewares/connection.py:49`, `src/backend/config/settings/base.py:261` |
| **Status** | Open |
| **Problem** | The verified execution order of the update middleware chain (aiogram 3.30.0 `MiddlewareManager.wrap_middlewares` wraps in `reversed()` order, so the last-registered is outermost-innermost reversed — i.e. `UpdateIdDedup → Liveness → Language → AccountState`) means **every** inbound Telegram update, before any handler runs, performs: 1 Redis `cache.add` (dedup), 1 Redis `cache.set` (liveness), 1 Redis read (`get_cached_anon_language`), 1 `User` query (language resolution), 1 `User` query (account state), and for `/post` 2 more `User` queries (publish permission + FSM backfill) — up to 6 round-trips, three of them to PostgreSQL. Each `_get_user` is a separate `@sync_to_async` hop onto the single thread-sensitive executor, and each is an independent `User.objects.get(chat_id=...)` with no request-level memoisation. On top of that, `DatabaseConnectionMiddleware` calls `close_old_connections()` after **each** update and `CONN_MAX_AGE` is 0, so the PostgreSQL connection is torn down and re-established (TCP + auth handshake) once per update rather than reused. |
| **Impact** | The bot process pays a fixed, non-amortised I/O tax on every update, including trivial ones (`/language`, `confirm`, a bare `/start`), and a `User` lookup that is repeated up to three times within a single update. Because all ORM work funnels through one `thread_sensitive=True` executor, this also caps update throughput at the serialised rate of that one thread plus one connection handshake per update. The pattern also makes the "entry layer is thin" rule hard to hold: the middleware chain is doing per-request data access rather than delegating. |
| **Root Cause** | Each middleware resolves the acting user independently instead of resolving it once per update and attaching the result to the aiogram `data` dict; the connection lifecycle was tuned for request-scoped correctness (`CONN_MAX_AGE=0` for PgBouncer compatibility) without considering the bot's polling loop. |
| **Recommendation** | Resolve the `User` row once per update in a single new/extended middleware and stash it in `data["account_user"]` (+ `data["account_state"]`), so `LanguageMiddleware` and `AccountStateMiddleware` become pure reads — that alone removes 2–3 of the 6 round-trips. For the connection lifecycle, raise `CONN_MAX_AGE` (the value was chosen for PgBouncer transaction pooling, which is opt-in via `--profile pgbouncer` and not used by any service today) or drop the per-update `close_old_connections()` in favour of asgiref's `close_old_connections` only on a timer. This overlaps the performance phase; the entry-layer part (duplicate per-update user lookups) is the piece to fix here. |
| **Effort** | M (2–3 person-days) |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **Related Findings** | none |

**Evidence — `MiddlewareManager.wrap_middlewares` (aiogram 3.30.0, installed)** *(supports: "the effective execution order is dedup → liveness → language → account-state, i.e. four I/O-performing middlewares run before the handler")*:
```python
        middleware = handler_wrapper
        for m in reversed(middlewares):
            middleware = functools.partial(m, middleware)
        return middleware
```

**Evidence — `src/telegram_bot/middlewares/permissions.py:161`, `:206`, `:230`** *(supports: "the same `User` row is fetched up to three separate times per update, each as its own `sync_to_async` hop")*:
```python
    async def _check_user_state(self, chat_id, is_contact_link=False):
        try:
            user = await self._get_user(chat_id)          # query #1
        except User.DoesNotExist:
            return (True, "")
        state = get_account_state(user)
    ...
    async def _check_publish_permission(self, chat_id):
        try:
            user = await self._get_user(chat_id)          # query #2 (only for /post)
    ...
        if "user_id" not in fsm_data:
            user = await self._get_user(chat_id)          # query #3 (FSM backfill)
    ...
    @sync_to_async
    def _get_user(self, chat_id: int) -> User:
        return User.objects.get(chat_id=chat_id)         # no memoisation
```

**Evidence — `src/telegram_bot/middlewares/connection.py:46` + `src/backend/config/settings/base.py:261`** *(supports: "the database connection is closed after every update and never reused")*:
```python
    async def __call__(self, handler, event, data):
        try:
            return await handler(event, data)
        finally:
            await sync_to_async(close_old_connections)()   # per-update close
```
```python
            # PgBouncer async safety (zone C5)
            "CONN_MAX_AGE": 0,                            # no persistent connections
```

---

### LOW

#### ENT-011: [LOW] — `bot` service has no `stop_grace_period` in the production override

| Field | Value |
|---|---|
| **ID** | ENT-011 |
| **Title** | `bot` service has no `stop_grace_period` in the production override |
| **Severity** | LOW |
| **Category** | Operability |
| **File(s)** | `docker-compose.prod.yml:22`, `docker-compose.prod.yml:10`, `docker-compose.prod.yml:87`, `docker-compose.yml:288` |
| **Status** | Open |
| **Problem** | The production override sets `stop_grace_period: 30s` on `web` and on `scheduler`, but the `bot` override sets only `restart: unless-stopped`. Docker's default stop grace period is 10 s, and Compose does **not** inherit `stop_grace_period` from the base file, so the bot container is killed after 10 s while its siblings get 30 s. |
| **Impact** | aiogram's own `SIGTERM` handling is correct (verified: `Dispatcher.start_polling` installs `loop.add_signal_handler` for `SIGTERM`/`SIGINT` and runs the shutdown hooks), but 10 s may not be enough for a dispatch that is inside a `sync_to_async` ORM call, a photo download, or the four-command-menu registration. The result is an abrupt kill rather than the intended graceful path. Impact is muted in practice because `BOT_HEALTH_CHECK_ENABLED` defaults to `False`, so the orphaned `bot:liveness` Redis key (120 s TTL) does not gate web readiness by default. |
| **Recommendation** | Add `stop_grace_period: 30s` to the `bot` override so all three long-lived services share one shutdown contract. |
| **Effort** | S (1 line) |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **Related Findings** | ENT-001, ENT-002 |

**Evidence — `docker-compose.prod.yml`** *(supports: "web and scheduler declare a grace period; bot does not")*:
```yaml
  web:
    restart: unless-stopped
    stop_grace_period: 30s
  bot:
    restart: unless-stopped          # <- no stop_grace_period
  scheduler:
    restart: unless-stopped
    stop_grace_period: 30s
```

**Evidence — aiogram `Dispatcher.start_polling` (installed 3.30.0)** *(supports: "the bot's graceful-shutdown path exists and is signal-driven, so only the grace period is at fault")*:
```python
            if handle_signals:
                    loop.add_signal_handler(signal.SIGTERM, self._signal_stop_polling, signal.SIGTERM)
                    loop.add_signal_handler(signal.SIGINT,  self._signal_stop_polling, signal.SIGINT)
```

---

#### ENT-012: [LOW] — Dev startup gating is asymmetric: `web` waits for `seed`, `bot` does not

| Field | Value |
|---|---|
| **ID** | ENT-012 |
| **Title** | Dev startup gating is asymmetric: `web` waits for `seed`, `bot` does not |
| **Severity** | LOW |
| **Category** | Operability |
| **File(s)** | `docker-compose.dev.override.yml:29`, `docker-compose.dev.override.yml:33`, `docker-compose.yml:267` |
| **Status** | Open |
| **Problem** | In the dev override, the `web` service adds `depends_on: seed: {condition: service_completed_successfully}` (correctly, so media/seed photos exist before the first request), but the `bot` service keeps only the base `depends_on` (`load_catalog` completed + `redis` healthy). The two long-lived processes in the same environment therefore start on different readiness contracts. |
| **Impact** | A developer running `.\Makefile.ps1 up` gets a bot that accepts updates while the seed job is still populating 600 demo ads, so `/start` greetings, search results and saved-search digests can briefly reflect a half-seeded database. It also means a `seed` failure keeps the site down but leaves the bot up, so the failure is only visible on one of the two surfaces. No production impact — the prod override does not gate `bot` on `seed` either, and `seed` is profile-gated there. |
| **Recommendation** | Either mirror the `seed` dependency on the dev `bot` service so both start together, or add a short comment in the dev override explaining why the bot deliberately does not wait (it is a reasonable choice — but it should be recorded, not accidental). |
| **Effort** | S (1 block, or 1 comment) |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **Related Findings** | ENT-013 |

**Evidence — `docker-compose.dev.override.yml`** *(supports: "only `web` gains the `seed` dependency; `bot` inherits only the base deps")*:
```yaml
  web:
    ...
    # In dev, web waits for seed to complete so media/seed/ photos are populated
    # before serving. Dev override merges with base depends_on (load_catalog, redis).
    depends_on:
      seed:
        condition: service_completed_successfully

  bot:
    environment:
      - DJANGO_SETTINGS_MODULE=config.settings.dev
      - REDIS_URL=
    ...
    # no depends_on: added -> inherits load_catalog + redis only
```

---

#### ENT-013: [LOW] — Scheduler liveness marker cannot distinguish "loop alive" from "jobs succeeded"

| Field | Value |
|---|---|
| **ID** | ENT-013 |
| **Title** | Scheduler liveness marker cannot distinguish "loop alive" from "jobs succeeded" |
| **Severity** | LOW |
| **Category** | Observability |
| **File(s)** | `src/backend/apps/core/utils/scheduler.py:233`, `src/backend/apps/core/utils/scheduler.py:297`, `docker/healthcheck-scheduler.sh:18`, `docker-compose.prod.yml:122` |
| **Status** | Open |
| **Problem** | `_write_liveness_marker()` is called unconditionally after the hourly loop and after the `try/except` that swallows per-cycle exceptions, so the marker is refreshed whether every command succeeded, every command failed, or the cycle itself raised. `healthcheck-scheduler.sh` only checks marker existence and (optionally) age, so it reports `healthy` for a scheduler whose jobs have been failing for weeks. The first marker also cannot appear until a full 9-command cycle completes, while the healthcheck allows only `start_period: 30s` + 3 × 30 s retries. |
| **Impact** | A scheduler that is up but doing nothing (renamed command, broken SQL, blocked advisory lock on every job) stays `healthy` indefinitely; the failure is only visible in log lines. On a fresh deploy, a legitimately slow first cycle (large `consent_hard_delete`, a `sweep_orphaned_media` over a large `MEDIA_ROOT`) can push the container to `unhealthy` for a minute or two with nothing actually wrong. |
| **Recommendation** | Write the marker only after a cycle in which no command returned a non-zero exit code (or record the last successful cycle timestamp separately and have the healthcheck read that), and raise the scheduler healthcheck `start_period` to cover one full cycle (e.g. 120 s). This also gives the duplicate-alert case in ENT-003 a detectable signal. |
| **Effort** | S (1 conditional + 1 compose value) |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **Related Findings** | ENT-002, ENT-003 |

**Evidence — `src/backend/apps/core/utils/scheduler.py:227`** *(supports: "the marker is refreshed unconditionally, and per-command failures never propagate")*:
```python
    for cmd in HOURLY_COMMANDS:
        _dispatch(cmd, run_command)          # _dispatch swallows exceptions, returns 1

    # Write liveness marker after hourly cycle completes (before daily section).
    _write_liveness_marker()                # <- unconditional; no exit-code check
    ...
        except Exception:
            logger.exception("Scheduler cycle failed — continuing")   # loop keeps going
```

**Evidence — `docker healthcheck-bot`/`healthcheck-scheduler.sh` contract** *(supports: "the check is presence + age only, so it cannot observe job success")*:
```bash
marker="${SCHEDULER_LIVENESS_FILE:-/tmp/mko_bazuna_scheduler_alive}"
if [ ! -f "$marker" ]; then echo "scheduler: liveness marker missing"; exit 1; fi
stale="${SCHEDULER_HEALTH_STALE_SECONDS:-0}"
if [ "$stale" -gt 0 ] 2>/dev/null; then ... fi
echo "scheduler: healthy (process + marker OK)"
```

---

#### ENT-014: [LOW] — `entrypoint-test.sh` header comment wrongly claims the base entrypoint runs migrations

| Field | Value |
|---|---|
| **ID** | ENT-014 |
| **Title** | `entrypoint-test.sh` header comment wrongly claims the base entrypoint runs migrations |
| **Severity** | LOW |
| **Category** | Documentation |
| **File(s)** | `docker/entrypoint-test.sh:3`, `docker/entrypoint.sh:102` |
| **Status** | Open |
| **Problem** | The header of the test entrypoint states: "The base ENTRYPOINT (entrypoint.sh) already waits for the DB, **runs migrations**, and compiles translations, so this script only syncs deps and launches the test suite." `entrypoint.sh` never runs migrations — its executed path is `check_env_file → fix_volume_permissions → wait_for_db → wait_for_redis → compile_messages → deploy_check → exec "$@"`. Migrations come from the explicit `bootstrap_reference_data` call further down in `entrypoint-test.sh` (which, per ENT-008, is itself the problem). |
| **Impact** | A maintainer debugging the test bootstrap path is told the migration step is inherited from the base entrypoint and will look in the wrong place, or (worse) conclude the explicit `bootstrap_reference_data` call is redundant and remove it — which would leave the test instance without the search triggers and exchange rates the suite depends on. The code is correct; only the comment is wrong, so the fix is documentation-only. |
| **Recommendation** | Correct the comment to state what the base entrypoint actually does (DB wait, Redis wait, `compilemessages`, `check --deploy`) and that this script additionally runs `bootstrap_reference_data` itself. |
| **Effort** | S (comment only) |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **Related Findings** | ENT-008 |

**Evidence — `docker/entrypoint-test.sh:1`** *(supports: "the comment attributes migration to the base entrypoint")*:
```bash
# Test entrypoint for Mko Bazuna
# Runs pytest. The base ENTRYPOINT (entrypoint.sh) already waits for the DB,
# runs migrations, and compiles translations, so this script only syncs deps and
# launches the test suite.
```

**Evidence — `docker/entrypoint.sh:102`** *(supports: "the base entrypoint's executed path contains no migration step")*:
```bash
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    check_env_file
    fix_volume_permissions
    wait_for_db
    wait_for_redis
    compile_messages
    deploy_check

    exec "$@"
fi
```

---

## Cross-Finding Analysis

- **Merge candidates:** ENT-002 and ENT-003 are one operational story — a scheduler restart
  (ENT-002's failure mode) is precisely what triggers ENT-003's duplicate digest dispatch —
  but they have different root causes (an uninterruptible sleep vs. a process-local dedupe
  marker) and different fixes, so they stay separate. ENT-001 and ENT-011 share the *pattern*
  "a process contract is expressed only in one Compose override" and could be fixed in a single
  pass over `docker-compose*.yml` + `gunicorn.conf.py`, but the defects are independent.
- **Conflicting evidence:** none. R-06 proved the migration-once guarantee holds (lock
  contention blocks rather than duplicates), while ENT-006 is about that same lock's
  *unbounded wait* — the two findings are consistent, not contradictory.
- **Dependency chains:**
  - ENT-002 → ENT-003: fix the SIGTERM handling first, otherwise the restart that triggers
    duplicate alert digests keeps happening.
  - ENT-004 gates confidence in all future entry-layer changes: while the async bot process is
    outside the static gate, the fixes for ENT-005 and ENT-010 land without automated
    verification beyond pytest.
  - ENT-008 should be fixed before or together with ENT-006, since both live in the
    `bootstrap_reference_data` call path and touching one will mean reading the other.
- **Out-of-scope observations deliberately not filed here** (owned by sibling phases):
  `/metrics` is registered at the site root with no authentication (external-API / production-ops
  phase); the local dev stack's crash-looping `web`/`bot` containers are caused by a placeholder
  `BOT_TOKEN` in `.env.dev` (config/secrets phase); the 12 type errors inside `src/backend/**/tests`
  are a code-quality concern; `apps/api/` is an empty, documented ("DEFERRED to post-MVP")
  scaffold and therefore not dead code.

## Remediation Roadmap

| Order | ID | Severity | Effort | Priority | Recommendation (summary) |
|-------|----|----------|--------|----------|--------------------------|
| 1 | ENT-001 | HIGH | S | P0 | Guard `child_exit` on `PROMETHEUS_MULTIPROC_DIR`; set it in the base compose |
| 2 | ENT-002 | HIGH | S | P0 | Make the scheduler wait interruptible (`_stop_event.wait`) so SIGTERM exits within the grace period |
| 3 | ENT-003 | HIGH | M | P0 | Persist the daily-run marker; make `send_alerts` delivery and analytics insertion idempotent |
| 4 | ENT-004 | HIGH | S–M | P1 | Run ruff/basedpyright from the repo root over `src/` with `PYTHONPATH`; fix the 16 errors |
| 5 | ENT-005 | HIGH | M | P1 | Extract the two-phase login claim into `apps/users/services/login_token.py` |
| 6 | ENT-006 | MEDIUM | S | P1 | Bound advisory-lock acquisition (`lock_timeout`) and correct the "skip" docstring |
| 7 | ENT-008 | MEDIUM | S | P1 | Point the test bootstrap at the test DB under lock 111, or drop it from `entrypoint-test.sh` |
| 8 | ENT-007 | MEDIUM | S | P1 | Publish bot readiness markers before the best-effort command-menu registration |
| 9 | ENT-014 | LOW | S | P2 | Fix the incorrect migration claim in the `entrypoint-test.sh` header comment |
| 10 | ENT-011 | LOW | S | P2 | Add `stop_grace_period: 30s` to the `bot` production override |
| 11 | ENT-013 | LOW | S | P2 | Write the scheduler liveness marker only after a clean cycle; raise `start_period` |
| 12 | ENT-012 | LOW | S | P2 | Align dev `bot` startup gating with `web`, or record why it differs |
| 13 | ENT-009 | MEDIUM | M | P2 | Add a promotion grace marker, or lock 103 in `submit_ad`, to close the media race |
| 14 | ENT-010 | MEDIUM | M | P2 | Resolve the `User` row once per update and reuse it across middlewares |

## Rollout Safety

| ID | Risk | Backward-compatible? | Test gap (must cover) |
|----|------|----------------------|-----------------------|
| ENT-001 | Low | Yes | No test exists for `child_exit`; add one that calls the hook with `PROMETHEUS_MULTIPROC_DIR` unset (must not raise) and set (must mark dead) |
| ENT-002 | Med | Yes | Existing scheduler tests inject a no-op `sleep_func`, so they cannot catch this; needs a real-signal integration test asserting exit 0 within seconds |
| ENT-003 | Med | Yes | Needs a test that runs the daily predicate with a fresh `last_daily=None` and asserts `send_alerts` does not re-dispatch; plus an idempotency test for `_persist_alerts` on a second run |
| ENT-004 | Low | Yes | Mechanical (workflow + 16 error fixes); CI itself is the test. Confirm the `test` job still passes after the `working-directory` change |
| ENT-005 | High | Yes | The login suite covers both sides of the handshake separately; the extraction must keep both passing unchanged, and ideally add a test that asserts both processes agree on the eligibility predicate |
| ENT-006 | Low | Yes | `test_migrate_locked.py` exists; extend it with a lock-contention case asserting the bounded-wait behaviour |
| ENT-007 | Low | Yes | `lifecycle` tests cover the hooks; add one asserting the marker exists even when `_set_bot_commands` hangs |
| ENT-008 | Med | Yes | Full suite is the test: run `.\Makefile.ps1 test` after removing the step and confirm the trigger/seed autouse fixtures still cover what the step provided |
| ENT-009 | Med | Yes | Needs a concurrency test: promote a file, start a sweep before the `AdImage` insert commits, assert the file survives |
| ENT-010 | Med | Yes | `test_account_state_middleware.py` and `test_db_connection_middleware.py` exist; add a query-count assertion per update so the fan-out cannot regress |
| ENT-011 | Low | Yes | No test needed (compose value) |
| ENT-012 | Low | Yes | No test needed (compose value) |
| ENT-013 | Low | Yes | Extend `test_scheduler_wiring.py` to assert the marker is not refreshed after a failed cycle |
| ENT-014 | Low | Yes | Documentation only |

## Appendices

### Appendix A — R6: migration-once guarantee under near-simultaneous start

Two `bootstrap_reference_data` containers were started back to back against the same
PostgreSQL instance. Container 2's `migrate` subprocess began only after container 1 had
finished `setup_search_triggers` and `load_exchange_rates`, and both exited 0.

```text
=== C1 (tail) ===
  Apply all migrations: (none)
Installed trigger ads_search_vector_update
Backfilled search vectors for 0 rows
Exchange rates loaded: 0 created, 3 updated
Bootstrap reference data completed successfully
$ docker ps -a --filter name=ent-migrate  ->  ent-migrate-1 :: Exited (0)   ent-migrate-2 :: Exited (0)
```

*(supports the claim: "concurrent migration runs are serialized by advisory lock 100 and
execute exactly once; no duplicate or parallel migration occurs")*

### Appendix B — R1: no import-time side effects in any entry module

```text
$ docker run … -e DJANGO_SETTINGS_MODULE=config.settings.test … python -c "…"
--- importing config.wsgi ---
wsgi OK
--- importing telegram_bot.main ---
bot OK
--- importing apps.core.utils.scheduler ---
scheduler OK
--- importing apps.core.utils.migrate_locked ---
migrate_locked OK

$ # same, with an unreachable database
-e DATABASE_URL=postgres://nobody:nothing@127.0.0.1:1/none
wsgi import OK with unreachable DB
bot import OK with unreachable DB
scheduler import OK with unreachable DB
```

*(supports the claim: "no entry module performs DB access, model queries or network I/O at
import time; `django.setup()` is called before any ORM import in the bot entrypoint; no
circular imports")*

### Appendix C — R5: no reverse imports from lower layers into the entry layer

AST scan of every non-test module under `src/` for imports of `telegram_bot.*`, `config.wsgi`,
`config.asgi` and `config.urls`:

```text
48 matches — all of them are telegram_bot importing telegram_bot
  telegram_bot/main.py                 -> telegram_bot.handlers / .lifecycle / .middlewares / .retry
  telegram_bot/handlers/ad_create/*    -> telegram_bot.handlers.ad_create / .services.ad_data / .schemas
  telegram_bot/middlewares/permissions.py -> telegram_bot.handlers.contact
  …
TOTAL_REVERSE_IMPORTS: 48        # 0 from apps.* or any other lower layer
```

*(supports the claim: "no `apps.*` service/core module imports the bot process, the WSGI/ASGI
entrypoints, or the URL router; the dependency direction is acyclic. The one intra-layer
coupling — the account-state middleware importing a helper from a handler module — is inside
the entry layer and is noted as a maintainability smell rather than a boundary violation")*

### Appendix D — Bot process boot with an invalid token (R4)

```text
Failed to set bot commands for language ru; continuing
Failed to set bot commands for language bs; continuing
Failed to set bot commands for language en; continuing
Failed to set default bot commands; continuing
Traceback (most recent call last):
  File "<frozen runpy>", line 204, in _run_module_as_main
  File "/app/src/telegram_bot/main.py", line 134, in <module>  main()
  File "/app/src/telegram_bot/main.py", line 130, in main    dp.run_polling(bot)
  File ".../aiogram/dispatcher/dispatcher.py", line 377, in _polling
    user: User = await bot.me()
aiogram.exceptions.TelegramUnauthorizedError: Telegram server says - Unauthorized
$ docker ps -a --filter name=ent-bot-boot -> "ent-bot-boot :: Exited (1)"
```

*(supports the claim: "a missing/invalid bot token fails fast at boot with a clear error and a
non-zero exit code, satisfying the edge-case requirement; it does not silently hang")*












