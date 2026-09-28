---
phase: "01"
phase_name: "Entry Points & Process Architecture"
source_report: ".ai/audit/01-entry-architecture/findings.md"
date: "2026-09-28"
auditor: "Executor (subagent)"
validator: "Kilo (validator subagent)"
mode: "problems-only"
id_prefix: "ENT"
report_status: "validated"
findings_in_scope: 14
verdict_tally: "Confirmed 10 · Adjusted 4 · Rejected 0"
anchor_commit: "9e96b84"
---

# Validated Findings — Entry Points & Process Architecture (Phase 01)

This report is self-contained. Every claim was re-derived independently from the
source tree at commit `9e96b84` (working tree source-clean; only `.ai/**` is
untracked), and four findings were additionally reproduced at runtime. No code was
modified. The reader needs neither the original findings file nor any source file to
act on this document.

## Verdicts at a glance

| ID | Title (abbrev.) | Auditor sev. | **Verdict** | **Final sev.** | One-line justification |
|----|-----------------|--------------|-------------|----------------|------------------------|
| ENT-001 | Gunicorn arbiter dies on worker exit when `PROMETHEUS_MULTIPROC_DIR` unset | HIGH | **ADJUSTED** | **MEDIUM** | Mechanism reproduced byte-for-byte (exit 255), but the only shipped gunicorn deployment — the prod override — *does* set the variable; the finding is a latent landmine, not a live outage. |
| ENT-002 | Scheduler ignores SIGTERM for up to an hour | HIGH | **CONFIRMED** | HIGH | Reproduced against the real module: stop flag set at t≈1.5 s, loop still running at t=2.5 s, exits only at t=20 s when `time.sleep(20)` returns. |
| ENT-003 | Daily dedupe is process-local → duplicate alert digests | HIGH | **CONFIRMED** | HIGH | Every link verified: in-memory `last_daily`, unguarded `AnalyticsEvent.bulk_create` on a table with no unique constraint, and delivery outside the lock. |
| ENT-004 | Bot process outside CI lint/typecheck; typecheck gate red | HIGH | **CONFIRMED** | HIGH | CI scope confirmed at `ci.yml:178-180,200-202`; gate confirmed red (12 errors, exit 1). One evidence figure (16 errors, 2 in production) is **not reproducible** — see VAL-001. |
| ENT-005 | Two-phase login claim implemented twice in entry handlers | HIGH | **ADJUSTED** | **MEDIUM** | Root cause is factually wrong (`apps/users/services/` exists, 13/13 apps have one) and "the same rule twice" mischaracterises two *distinct* protocol operations; the real content is a missing service owner + a 470-line view. |
| ENT-006 | Migration lock has no acquisition timeout; docstring says "skip" | MEDIUM | **CONFIRMED** | MEDIUM | Docstring, blocking `pg_advisory_lock`, absent `lock_timeout`, and "log only after acquire" all verified; the wait is genuinely unbounded and silent. |
| ENT-007 | Bot readiness marker written after 4 sequential Telegram calls | MEDIUM | **CONFIRMED** | MEDIUM | Order verified; worst case 4 × 30 s (aiogram default) = 120 s, exactly the `start_period 30 s + 3 × 30 s` unhealthy window. Arithmetic checks out. |
| ENT-008 | Test bootstrap builds a migration-less schema in the non-test DB, fail-open | MEDIUM | **ADJUSTED** | **LOW** | Fully reproduced live (39 tables, `django_migrations` absent), but the damage is contained to a throwaway database in the test project that no test and no documented command reads. |
| ENT-009 | Orphan sweep can delete freshly promoted, not-yet-referenced media | MEDIUM | **CONFIRMED** | MEDIUM | Cross-process window verified; taxonomy lists "uncoordinated media writes" at MEDIUM. Window is one DB transaction, not "milliseconds" — restate. |
| ENT-010 | Bot middleware does 4–6 I/O round-trips + 1 DB handshake per update | MEDIUM | **ADJUSTED** | **LOW** | Duplicate `User` lookups are real and worth fixing; the `CONN_MAX_AGE=0` / per-update close half is a *documented intentional* design and must not be filed as a defect. |
| ENT-011 | `bot` service has no `stop_grace_period` in the prod override | LOW | **CONFIRMED** | LOW | Verified in both prod and base compose; `BOT_HEALTH_CHECK_ENABLED` default is `False`, which correctly mutes the impact as the finding itself states. |
| ENT-012 | Dev startup gating asymmetric: `web` waits for `seed`, `bot` does not | LOW | **CONFIRMED** | LOW | Verified in the dev override; production does not gate `bot` on `seed` either. |
| ENT-013 | Scheduler liveness marker cannot distinguish "alive" from "succeeded" | LOW | **CONFIRMED** | LOW | Marker refresh is unconditional and per-command failures never propagate; the 7200 s staleness check catches a *stuck* loop, not a *failing* one. |
| ENT-014 | `entrypoint-test.sh` header wrongly claims base entrypoint runs migrations | LOW | **CONFIRMED** | LOW | Comment vs. `entrypoint.sh:102-110` executed path verified; documentation-only fix. |

**Severity movement:** 0 CRITICAL, 5 HIGH, 5 MEDIUM, 4 LOW → **0 CRITICAL, 4 HIGH,
4 MEDIUM, 6 LOW.**

**Type note.** The phase-01 handbook defines a *severity* taxonomy but no `Type`
vocabulary. The generic `SPEC-DEVIATION` / `BEST-PRACTICE` / `DOC-UPDATE` set does not
fit a runtime crash, so this report uses `RUNTIME-DEFECT` for the process-topology
failures and reserves the generic three for the findings that genuinely are one:
`DOC-UPDATE` (ENT-014), `SPEC-DEVIATION` (ENT-004, ENT-012 — the documented local gate
disagrees with the CI gate), `BEST-PRACTICE` (ENT-005, ENT-010).

---

## Checkpoint 1 — Auditor analysis

- **Stage:** Auditor analysis
- **Findings in scope:** 14 (CRITICAL 0, HIGH 5, MEDIUM 5, LOW 4); prefix `ENT-`
- **Evidence anchor:** `.ai/audit/01-entry-architecture/findings.md` (1033 lines, 14 runtime checks R-01…R-14, 4 appendices)
- **Dependencies / blockers:** dev `web`/`bot` crash-loop on a placeholder `BOT_TOKEN` in `.env.dev` (independently reported as CFG-006), so no live dev-stack evidence was available. Validation therefore used (a) source-level derivation, (b) the `mko-bazuna-test` image for isolated process reproductions, (c) the running test PostgreSQL instance for schema assertions, (d) local `uv run basedpyright` / `uv run ruff` (no DB required).
- **Checkpoint status:** closed

## Checkpoint 2 — Researcher verification

- **Stage:** Researcher verification
- **Cross-phase conflicts:** **0.** The one apparent collision is not a conflict: ENT-001 ("web crash-loops") and CFG-006 ("dev stack crash-loops") describe different containers with different causes (missing Prometheus env var vs. a bot-only credential breaking the shared dev settings module). They are complementary.
- **Merge candidates:** 0 hard merges. 2 soft relationships recorded — VAL-002 (ENT-005 ↔ AUT-007) and VAL-003 (ENT-001/ENT-011 ↔ CFG-002). All pairs have different root causes and different fixes, so they are retained and cross-referenced rather than merged.
- **Dependency chains confirmed:** ENT-002 → ENT-003 (a scheduler restart is the duplicate-digest trigger); ENT-004 → ENT-005/ENT-010 (bring the async entry layer inside the static gate before refactoring it); ENT-006/ENT-008/ENT-014 share the `bootstrap_reference_data` call path.
- **Audit-input defects found:** 4 (VAL-001…VAL-004), including one unreproducible evidence figure and one still-open dependency on the in-flight phase 03.
- **Checkpoint status:** closed

## Checkpoint 3 — Per-finding validation

- **Stage:** Per-finding validation
- **Decisions:** Validated unchanged **10** (ENT-002, ENT-003, ENT-004, ENT-006, ENT-007, ENT-009, ENT-011, ENT-012, ENT-013, ENT-014) · Adjusted **4** (ENT-001 HIGH→MEDIUM; ENT-005 HIGH→MEDIUM + BEST-PRACTICE; ENT-008 MEDIUM→LOW; ENT-010 MEDIUM→LOW + BEST-PRACTICE) · Merged 0 · Rejected 0
- **Runtime reproductions performed by the validator:** 4 (ENT-001 gunicorn crash; ENT-002 SIGTERM/sleep; ENT-008 phantom schema via `psql`; ENT-004 typecheck + lint exit codes)
- **Evidence anchor:** this document; every line reference verified against the working tree at `9e96b84`
- **Checkpoint status:** closed

## Checkpoint 4 — Rollout safety

- **Stage:** Final audit
- **Circular dependencies:** none among ENT-001…ENT-014
- **Unsafe ordering detected:** 1 (ENT-003 — see Rollout Safety below)
- **Fragile insertion points:** 1 (ENT-008 — removing the bootstrap step can silently break the suite)
- **Checkpoint status:** closed

---

## Findings

### ENT-001 — [MEDIUM] — Gunicorn arbiter dies on every worker exit when `PROMETHEUS_MULTIPROC_DIR` is unset

**Verdict: ADJUSTED — HIGH → MEDIUM.** Type: `RUNTIME-DEFECT`.

**Verified (reproduced).** `gunicorn.conf.py:43-50` registers a `child_exit` hook that
calls `multiprocess.mark_process_dead(worker.pid)` with no guard.
`prometheus_client/multiprocess.py:177-183` falls back to
`os.environ.get("PROMETHEUS_MULTIPROC_DIR", os.environ.get("prometheus_multiproc_dir"))`,
which yields `None` when unset, and then calls
`glob.glob(os.path.join(path, ...))` → `TypeError: expected str, bytes or os.PathLike
object, not NoneType`.

The exception is not swallowed: `gunicorn/arbiter.py` `reap_workers()` catches only
`OSError`, and `run()`'s `except Exception:` handler logs *"Unhandled exception in main
loop"*, calls `stop(False)` and `sys.exit(-1)` → **exit 255**.

**Runtime reproduction (validator, this pass).** Booted gunicorn in the shipped
`mko-bazuna-test-web` image with the project's own `gunicorn.conf.py` and
`--max-requests 2 --max-requests-jitter 0`, `PROMETHEUS_MULTIPROC_DIR` unset:

```text
$ docker run -d --name ent-val-1 -p 5999:5999 -v <probe>:/tmp/probe/app.py:ro \
    -e PYTHONPATH=/tmp/probe -w /app --entrypoint "" mko-bazuna-test-web:latest \
    gunicorn --config /app/gunicorn.conf.py --workers 1 --max-requests 2 \
             --max-requests-jitter 0 --bind 0.0.0.0:5999 app:application
$ curl x3
200 / 200 / <connection reset>
$ docker inspect ent-val-1 --format "ExitCode={{.State.ExitCode}}"
ExitCode=255
$ docker logs ent-val-1
[..] [1] [INFO] Autorestarting worker after current request.
[..] [1] [ERROR] Unhandled exception in main loop
  File ".../gunicorn/arbiter.py", line 246, in run      ->  handler()
  File ".../gunicorn/arbiter.py", line 271, in handle_chld -> self.reap_workers()
  File ".../gunicorn/arbiter.py", line 650, in reap_workers -> self.cfg.child_exit(self, worker)
  File "/app/gunicorn.conf.py", line 50, in child_exit   -> multiprocess.mark_process_dead(worker.pid)
  File ".../prometheus_client/multiprocess.py", line 182, in mark_process_dead
TypeError: expected str, bytes or os.PathLike object, not NoneType
```

The crash is load-driven, not shutdown-specific: **two HTTP requests were enough.**

**Why the severity drops to MEDIUM.** The finding's own impact text is conditional
("*any* deployment that uses the shared `gunicorn.conf.py` without that single env
var"), and that condition is not met by any deployment the project actually ships or
documents:

| Deployment path | Runs gunicorn? | Sets `PROMETHEUS_MULTIPROC_DIR`? | Started by a documented command? |
|---|---|---|---|
| `docker-compose.yml` + `docker-compose.prod.yml` | yes (`web`) | **yes** (`prod.yml:14`, with matching `tmpfs` at `:15-16`) | yes — this is production |
| `docker-compose.yml` + `docker-compose.dev.override.yml` | **no** — the dev override replaces the command with `manage.py runserver` (`dev.override.yml:7-9`) | n/a | yes — `.\Makefile.ps1 up` |
| `docker-compose.yml` + `docker-compose.test.yml` | yes (inherits base `command`) | no | **no** — `make test` / `make test-db` start only `db` and the one-shot `test` service |
| image `CMD ["gunicorn", "config.wsgi:application"]` (`docker/Dockerfile:180`) | yes | no — the image `ENV` does not set it | only via a bare `docker run` on the published image |

So this is a **latent, config-dependent landmine**, not an active production outage.
The two-line guard is still mandatory — a single missing env var silently taking down
the entire web tier is exactly the failure mode the guard exists to prevent — but
"the web container enters a crash loop" is not true of the topology as deployed.

**Required fix (unchanged from the auditor).** Guard the hook:
`if os.environ.get("PROMETHEUS_MULTIPROC_DIR"): multiprocess.mark_process_dead(worker.pid)`.
Additionally set `PROMETHEUS_MULTIPROC_DIR` (with the matching tmpfs) on `web` in the
**base** compose so every environment inheriting `gunicorn.conf.py` shares one
contract.

**Test gap.** No test exists for `child_exit`. Add one that calls the hook with the
variable unset (must not raise) and set (must mark dead).

---

### ENT-002 — [HIGH] — Scheduler ignores SIGTERM for up to one hour; production stop is always SIGKILL

**Verdict: CONFIRMED — HIGH (unchanged).** Type: `RUNTIME-DEFECT`. Phase-01 taxonomy
lists *"no graceful shutdown"* at HIGH.

**Verified (reproduced).** `scheduler.py:340-341` installs
`_handle_shutdown_signal`, which only sets `_stop_event` (`:45-52`).
`run_scheduler` checks that flag at the **top** of the loop (`:294-296`), runs the
cycle, then calls `sleep_func(interval_seconds)` (`:305`) where the default is
`time.sleep` (`:261`) and the production interval is `SCHEDULE_INTERVAL_SECONDS = 3600.0`
(`:80`). Under PEP 475 a `time.sleep` interrupted by a signal whose handler returns
normally **resumes for the remaining timeout**.

**Runtime reproduction (validator, this pass)** — the real module, real handler, real
default `sleep_func`, with `interval_seconds` shortened to 20 s to keep the test short
and `run_command_fn` stubbed so the cycle is instant:

```text
[t=  0.00s] run_scheduler() entered; production default sleep_func=time.sleep
[t=  1.50s] SIGTERM sent -> loop is already blocked in time.sleep(20)
[  3501ms ] Received signal 15; requesting graceful scheduler shutdown
[t=  2.50s] 1.0s after SIGTERM: loop has NOT exited (stop flag only set)
[t= 20.00s] LOOP EXITED
```

The stop flag was set at t≈1.5 s; the loop did not observe it for another **18.5
seconds** — exactly the remaining duration of the sleep. Scaled to production
(`time.sleep(3600)` vs. `stop_grace_period: 30s` at `docker-compose.prod.yml:87`),
Docker escalates to SIGKILL at 30 s → **exit 137**, `_shutdown()` (`:308-320`) never
runs, and the exit code is indistinguishable from an OOM.

**One correction to the report.** The original frames the delay as "the remaining
sleep". It is slightly worse than that: `sleep_func(...)` at `:305` is called
*unconditionally* after the cycle, so a SIGTERM delivered **during** a cycle is not
observed until the *next* top-of-loop check — i.e. the maximum delay is
`interval + cycle duration`, not just the remaining sleep. This does not change the
verdict; it widens the window.

**Required fix (unchanged).** Make the wait interruptible while keeping the injection
point for tests: default `sleep_func=lambda s: _stop_event.wait(s)`. The handler then
breaks the wait immediately, the loop exits, and `_shutdown()` closes DB connections.

**Test gap.** Existing scheduler tests inject a no-op `sleep_func`, so they cannot
catch this. Needs a real-signal integration test asserting exit 0 within seconds.

---

### ENT-003 — [HIGH] — Daily-job dedupe state is process-local; `send_alerts` re-sends duplicate digests after a restart

**Verdict: CONFIRMED — HIGH (unchanged).** Type: `RUNTIME-DEFECT` (dimension (e),
*"no process-local state assumed"*).

**Verified.** Every link in the chain checks out:

1. **Dedupe record is in-memory.** `scheduler.py:292` — `last_daily: date | None = None`,
   re-initialised on every process start.
2. **A fresh process after the threshold always re-fires.** `scheduler.py:104-106` —
   `if last_daily is None or now.date() != last_daily: return now.hour >= daily_hour_utc`,
   with `DAILY_HOUR_UTC = 8` (`:77`).
3. **`send_alerts` is in the daily set.** `scheduler.py:70-73` —
   `DAILY_COMMANDS = ["send_alerts", "rollup_daily_metrics"]`.
4. **Analytics rows are inserted without conflict handling.** `send_alerts.py:152-153` —
   `AnalyticsEvent.objects.bulk_create(analytics_events)` (no `ignore_conflicts`),
   while the *notifications* on the line above correctly pass `ignore_conflicts=True`.
5. **Nothing can reject the duplicate.** `analytics/models.py:56-63` — `AnalyticsEvent.Meta`
   declares only an index, **no unique constraint**. So the second run inserts a second
   `SEARCH_ALERT_MATCHED` row per saved search.
6. **Delivery is outside the lock and outside the transaction.**
   `send_alerts.py:64-74` — the lock scope ends at `:70`; the digest send at `:74`
   happens after the advisory lock is released, and `_collect_alerts` (`:100-136`)
   re-collects matching ads without filtering out already-notified ones, so the second
   run re-sends the *same* digest text.
7. **`rollup_daily_metrics` is not the concern.** The original report correctly notes
   it is idempotent (`update_or_create` keyed on yesterday), so the damage is confined
   to `send_alerts`.

**Impact is accurately stated.** `SavedSearchNotification` rows survive duplication via
`uq_saved_search_ad` + `ignore_conflicts=True`; the *user-visible message* and the
*analytics rows* do not. Any scheduler restart after 08:00 UTC (deploy, crash, node
reboot) re-runs the daily set on the same calendar day.

**Required fix (unchanged, with an ordering constraint — see Rollout Safety).** Make the
daily marker durable (DB row, or a Redis key with a >24 h TTL — Redis is already a hard
dependency of both long-lived processes) and make `send_alerts` delivery idempotent:
`ignore_conflicts=True` on the analytics bulk-create, plus recorded dispatch state.

---

### ENT-004 — [HIGH] — Entire bot process is outside the CI lint + typecheck scope, and the typecheck gate is red

**Verdict: CONFIRMED — HIGH (unchanged).** Type: `SPEC-DEVIATION` (the documented local
gate and the CI gate disagree about what "green" means, and CI is not currently green).

**Verified.** `.github/workflows/ci.yml`:

```yaml
lint:                                      # :160
  - run: uv run ruff check .               # :179
    working-directory: src/backend         # :180
typecheck:                                 # :182
  - run: uv run basedpyright .             # :201
    working-directory: src/backend         # :202
```

`src/telegram_bot` is a *sibling* of `src/backend`, so neither job can see it. The
local targets do see it — `Makefile:123` `ruff check src/`, `Makefile:129`
`basedpyright src/`, mirrored in `Makefile.ps1:172,178` — so local and CI genuinely
disagree.

**Runtime verification (validator, this pass), CI scope exactly as CI invokes it:**

```text
$ cd src/backend && uv run basedpyright .
12 errors, 0 warnings, 0 notes                    -> exit 1
  apps/ads/tests/test_edit_views_locking.py:239,247,292,300  (x2 each: __enter__/__exit__)
  apps/moderation/tests/test_admin_actions.py:529,538          (x2 each)
   -- all 12 are untyped `advisory_lock` context-manager complaints in TEST files

$ cd src/backend && uv run ruff check .
All checks passed!                                -> exit 0
```

The `typecheck` job has no `continue-on-error`, so **CI is red today**. All 12 errors
are the "django-stubs is not installed, `Atomic.__enter__/__exit__` untyped" class that
`pyproject.toml:201-206` explicitly documents as the reason affected call sites carry
an inline `# pyright: ignore[reportGeneralTypeIssues]` — the two offending test files
simply lack that comment. Per "production code is king", the fix belongs in the tests,
not in production behaviour.

**Evidence correction (see VAL-001).** The original report states `basedpyright src/`
yields **16** errors, two of them in production bot handlers
(`telegram_bot/handlers/alerts.py:83`, `contact.py:277`). Measured today in the working
tree, `basedpyright src/` yields **14** errors and **none** in production code:

```text
$ uv run basedpyright src/
14 errors, 0 warnings, 0 notes                    -> exit 1
  ... the same 12 test errors ...
  src/telegram_bot/tests/test_ad_create.py:358,373  ("write" is not a known attribute of "None")

$ uv run ruff check src/     -> All checks passed!  (exit 0)
```

The "2 production errors" figure is not reproducible and must be removed from the
evidence. It does not affect the finding: the scope gap is real, and the gate is
demonstrably red at 12 errors.

**Required fix (unchanged, count corrected).** Run the static gates from the repository
root over the whole tree with `PYTHONPATH=src:src/backend`, drop
`working-directory: src/backend`, and fix the **14** reported errors (12 in
`src/backend` tests, 2 in `telegram_bot` tests) so the gate is green. A green gate that
covers both processes is worth more than a red gate that covers one.

---

### ENT-005 — [MEDIUM] — Two-phase login-claim protocol implemented twice inside entry handlers

**Verdict: ADJUSTED — HIGH → MEDIUM, reclassified `BEST-PRACTICE`.** The structural
observation is real; the stated root cause is factually wrong and the stated defect
overlaps phase 04.

**Correction 1 — the root cause does not hold.** The report says *"There is no
`apps.users.services` counterpart for the login handshake."* In fact
`src/backend/apps/users/services/` **exists** and already hosts four modules:
`account_state.py` (with `can_login`, the predicate `login_status` calls),
`consent_record.py`, `deletion.py`, and `login_rate_limit.py` — the last of which is
the exact precedent for extracting `login_issue`'s logic out of the view. **All 13
apps** in `src/backend/apps/` have a `services/` package. What is missing is one
module (`login_token.py`), not the service layer. This *strengthens* the
recommendation — the extraction follows an established project pattern rather than
inventing one.

**Correction 2 — "the same rule twice" mischaracterises the code.** The two
implementations are not one predicate written twice; they are the two distinct
operations of a two-phase protocol, and their predicates legitimately differ:

| | Bot (`telegram_bot/handlers/login.py:169-187`) | Web (`apps/users/views/consent.py:404-430`) |
|---|---|---|
| Operation | **claim** — set `telegram_id` | **consume** — set `consumed_at` |
| Predicate | `telegram_id IS NULL AND consumed_at IS NULL AND expires_at > now` | `telegram_id = <observed> AND consumed_at IS NULL AND expires_at > now` |
| Mechanism | `UPDATE … RETURNING` (row lock ⇒ zero TOCTOU) | conditional `.filter(…).update(…)` (row count ⇒ zero TOCTOU) |
| Must it read first? | no | **yes** — it needs `token.telegram_id` to log the right user in |

The only genuinely shared invariant is *"the token is still live"* (`consumed_at IS
NULL AND expires_at > now`). Phase 04's independent audit rated the two-phase claim
zero-TOCTOU and sound. There is no demonstrated defect here today, which is why HIGH
("Correctness") is an inflation — the finding's own impact text is speculative
("*can* silently break the other").

**What survives, and is worth doing.**

1. The `LoginToken` lifecycle has **no single owner**: minting/hashing/rate-limiting
   sit in the view, claiming sits in the handler, and the token object is touched from
   a third place (`users/services/deletion.py:125` deletes outstanding tokens on
   consent withdrawal). The same class of defect is what AUT-007 reports concretely
   (`login_issue` never invalidates the browser's previous outstanding token).
2. `consent.py` is a **470-line view module** that mints the token, applies two rate
   limits, hashes it, consumes it, ban-checks, calls `auth_login`, *and* runs a
   two-query preferred-city reconciliation — business logic in the transport layer,
   which phase-01 dimension (c) explicitly forbids. Per the 99 handbook, splitting
   oversized modules is **high ROI** and must not be rejected as overengineering.
3. The claim/consume predicates are **not independently unit-testable** without HTTP
   and Telegram.

**Required fix (unchanged, now better-founded).** Extract
`apps/users/services/login_token.py` with `issue_token()`, `claim_token(token_hash,
telegram_id, now)` and `consume_token(token_hash, expected_telegram_id)` — one
transaction each, each owning its predicate, each using the ORM. Leave the handlers as
parse → delegate → respond, and slim `consent.py`.

**Cross-phase:** see VAL-002 (shares a root cause with AUT-007).

---

### ENT-006 — [MEDIUM] — Migration advisory lock has no acquisition timeout; documented "skip" semantics are wrong

**Verdict: CONFIRMED — MEDIUM (unchanged).** Type: `RUNTIME-DEFECT`.

**Verified.** `apps/core/utils/migrate_locked.py:5` — the module docstring states
*"Idempotent: subsequent runs will find lock already held and **skip**."* The
implementation (`migrate_locked.py:86`) calls
`advisory_lock(AdvisoryLockId.MIGRATE, session=True)`, which at
`apps/core/utils/advisory_lock.py:74` issues `SELECT pg_advisory_lock(%s)` — the
**blocking** variant. It never skips, and it is never bounded: no `lock_timeout` and no
`statement_timeout` is set anywhere in `advisory_lock.py`.

Two aggravating details the original report does not call out and which make the
diagnosis materially harder than described:

- The only log line, `logger.info("Acquired session advisory lock %s", lock_id)`
  (`advisory_lock.py:75`), fires **after** acquisition. A blocked run therefore emits
  **nothing at all** — the operator sees a silent hang, not even a "waiting" message.
- `SCHEDULER_COMMAND_TIMEOUT` (default `1800`, `config/settings/base.py:340`) bounds
  each child `manage.py` invocation (`migrate_locked.py:85,93`), **not** the wait for
  the lock itself.

The migration-once guarantee itself is intact and remains so; this is diagnosability
and boundedness only.

**Required fix (unchanged).** Decide the intended semantics and implement it: either
set `lock_timeout` before acquiring so a contending run fails fast with a clear
message, or keep blocking but log *before* acquisition and document it. Correct the
docstring either way.

---

### ENT-007 — [MEDIUM] — Bot readiness marker is written only after four sequential Telegram API calls

**Verdict: CONFIRMED — MEDIUM (unchanged).** Type: `RUNTIME-DEFECT`.

**Verified.** `telegram_bot/lifecycle.py:106-128` (`_on_startup`) awaits
`_set_bot_commands(bot)` at `:121` *before* `Path(path).touch()` at `:126` and
`await _write_redis_marker()` at `:128`. `_set_bot_commands` (`:84-103`) issues
`set_my_commands` once per language (`ru`, `bs`, `en`) plus a fourth default-scope
call — four sequential round-trips, each individually wrapped in a bare
`try/except Exception: continue`, with **no `asyncio.wait_for` and no overall budget**.

The arithmetic in the original report checks out: aiogram's default per-request
timeout is **30 s** (`aiogram/client/session/aiohttp.py:189`), so worst case is
≈120 s — exactly the unhealthy window declared by the bot healthcheck
(`docker-compose.yml:297-302`: `start_period: 30s`, `interval: 30s`, `retries: 3`).
Command-menu registration is fail-open and non-critical by design, so it should not
gate readiness.

**Required fix (unchanged).** Write the file and Redis liveness markers **first**, then
perform `set_my_commands` under a bounded budget (`asyncio.wait_for(..., timeout=10)`
around the whole registration). Readiness then means "polling is about to start", not
"Telegram answered four times".

---

### ENT-008 — [LOW] — Test-container bootstrap creates a migration-less schema in the non-test database, fail-open

**Verdict: ADJUSTED — MEDIUM → LOW.** Type: `RUNTIME-DEFECT` (test infrastructure).

**Verified (source + live schema).** The chain is exactly as described:

- `config/settings/test.py:28` pins `DATABASES["default"]["NAME"] = "mko_bazuna"` (not `test_mko_bazuna`).
- `config/settings/test.py:89-97` sets `MIGRATION_MODULES = DisableMigrations()` for every app, including Django built-ins.
- `docker/entrypoint-test.sh:25` runs `bootstrap_reference_data || true`.
- `bootstrap_reference_data.py:33,67` delegates to `migrate_locked.main()`, which spawns `manage.py migrate --noinput --run-syncdb` as a **subprocess** (`migrate_locked.py:53,90-93`) — and a subprocess inherits the same settings module, so it targets `mko_bazuna` with migrations disabled, i.e. pure syncdb.
- The command's own docstring (`bootstrap_reference_data.py:21-26`) documents precisely this hazard and explains why `conftest.py` avoids the command.

**Live confirmation (validator, this pass)** against the running test instance:

```text
$ docker exec mko-bazuna-test-db-1 psql -U postgres -d mko_bazuna \
    -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';"
39
$ docker exec mko-bazuna-test-db-1 psql -U postgres -d mko_bazuna \
    -tAc "SELECT to_regclass('public.django_migrations');"
                                    (empty — table does not exist)
```

A 39-table schema with no `django_migrations` history is sitting in the non-test
database. Confirmed.

**Why the severity drops to LOW.** The damage is *contained*. `mko_bazuna` inside the
`mko-bazuna-test` compose project is a throwaway database on a throwaway container:
pytest uses `test_mko_bazuna`, whose triggers and currency rows `conftest.py`
bootstraps itself under `AdvisoryLockId.TEST_SCHEMA_SETUP`; and no documented command
(`make test`, `make test-db`, `make test-recreate`) starts any service that reads
`mko_bazuna`. The real costs are (a) wasted container time on every test run and
(b) a `|| true` that would mask a genuine bootstrap failure if one ever occurred. Both
are worth fixing; neither is MEDIUM-severity.

**Required fix (unchanged, with the second half prioritised).** Point the test
bootstrap at the test database under lock 111, or drop the step from
`entrypoint-test.sh` and let `conftest.py`'s autouse fixture own the bootstrap (it
already does). **If the step is kept for any reason, remove `|| true`** so a real DDL
failure is visible. Note the rollout constraint below.

---

### ENT-009 — [MEDIUM] — Cross-process media race: orphan sweep can delete freshly promoted, not-yet-referenced files

**Verdict: CONFIRMED — MEDIUM (unchanged).** Type: `RUNTIME-DEFECT`. Phase-01 taxonomy
lists *"uncoordinated media writes"* at MEDIUM — an exact match.

**Verified.** `apps/ads/services/submission.py:161-166` promotes staging files to
permanent storage **before** opening `transaction.atomic()` at `:169`, and
`move_staging_to_permanent` (`apps/media/services/filesystem.py:44-84`) does an atomic
`os.replace` per key field. The comment states the intent explicitly: *"On DB rollback
the permanent files become unreferenced orphans reclaimed by the normal orphan sweep."*
`submit_ad` never takes `AdvisoryLockId.SWEEP_ORPHANED_MEDIA` (103).

The sweep (`apps/media/management/commands/sweep_orphaned_media.py:137-165`) takes
lock 103 (transaction-scoped), snapshots referenced keys from **`AdImage` rows only**
(`:41-50`), walks `MEDIA_ROOT` excluding `seed/` and `staging/` (`:53-73`), and
deletes `on_disk - referenced`. It runs in a **different process** — the scheduler's
`manage.py` subprocess — so nothing serialises the two.

The sweep's own comment (`:134-136`) — *"the DB side is read-only here — no writes, so
no advisory lock is strictly needed"* — is correct about the DB and blind to the
filesystem, which is the other process's write surface. That asymmetry is the defect.

**One correction.** The report describes the window as "milliseconds". It is actually
the **entire `transaction.atomic()` body** (`:169` → commit), which includes
`select_for_update()`, all field writes, normalisation, and the `AdImage` bulk insert.
Still short, but it is one DB transaction, not an unmeasured instant — restate it that
way when this finding is actioned.

**Cross-phase:** see VAL-004 (phase 07 media, and phase 05 AD-006, both touch
orphan-photo handling).

**Required fix (unchanged).** Close the window the way the project already closes
abandoned uploads: have `move_staging_to_permanent` leave a short-lived marker that the
sweep treats as referenced, expiring after one sweep interval. The marker approach is
preferable to taking lock 103 in `submit_ad`, which would make ad submission depend on
a scheduler lock.

---

### ENT-010 — [LOW] — Bot middleware stack performs 4–6 I/O round-trips and one DB handshake per inbound update

**Verdict: ADJUSTED — MEDIUM → LOW, split in two.** Type: `BEST-PRACTICE`.

**Half A — confirmed, keep it.** The middleware order is exactly as described. With
`main.py:49-58` registering `UpdateIdDedup → Liveness → Language → AccountState` as
update middlewares and `DatabaseConnectionMiddleware` as the outer middleware, every
inbound update performs, before any handler runs:

1. `cache.add` — `middlewares/update_id_dedup.py:59`
2. `os.utime` + `cache.set` — `telegram_bot/lifecycle.py:163-171`
3. `User.objects.filter(telegram_id=…).values_list(…).first()` — `middlewares/language.py:82-86`, plus a cache read at `:89`
4. `User.objects.get(chat_id=…)` — `middlewares/permissions.py:161` (every update)
5. `User.objects.get(chat_id=…)` — `permissions.py:206` (`/post` only)
6. `User.objects.get(chat_id=…)` — `permissions.py:130` (FSM `user_id` backfill only)

`_get_user` is a bare `@sync_to_async` (`permissions.py:222-239`) with **no
memoisation**, and none of the four lookups share a result — note they do not even use
the same column (`telegram_id` in `language.py` vs. `chat_id` in `permissions.py`).
Memoising the resolved user once per update and stashing it in the aiogram `data` dict
is a clean, low-risk refactor that removes 2–3 of the round-trips.

**Half B — rejected as a defect.** The connection-lifecycle part of this finding
describes **pre-existing, intentional** design and must not be filed as a problem:

- `CONN_MAX_AGE: 0` carries the comment *"PgBouncer async safety (zone C5)"*
  (`config/settings/base.py:260-261`).
- `DatabaseConnectionMiddleware`'s module docstring (`middlewares/connection.py:1-16`)
  explains in detail that it deliberately mirrors the HTTP `request_finished` hook and
  that the call *must* go through `sync_to_async` to land on the thread-local
  connection-owning thread.

The auditor's own recommendation (raise `CONN_MAX_AGE`) therefore contradicts a
documented decision, and the report notes PgBouncer is opt-in via
`--profile pgbouncer` and used by no service. If the connection cost is worth
revisiting, that is a **phase 13 (performance) question about a deliberate design
trade-off**, not a phase-01 entry-layer defect.

**Severity.** MEDIUM is inflated. Four indexed single-row selects plus two or three
Redis operations per update, serialised on a single `thread_sensitive` worker, is not
a demonstrated bottleneck at this project's scale, and the original report itself
concedes the work overlaps the performance phase. The architectural observation
("the entry layer is doing per-request data access rather than delegating") is real
and is the part worth acting on.

---

### ENT-011 — [LOW] — `bot` service has no `stop_grace_period` in the production override

**Verdict: CONFIRMED — LOW (unchanged).** Type: `SPEC-DEVIATION` (prod and the other
two long-lived services express a different shutdown contract).

**Verified.** `docker-compose.prod.yml`:

```yaml
web:        restart: unless-stopped; stop_grace_period: 30s   # :9-10
bot:        restart: unless-stopped                            # :22-23  <- no grace period
scheduler:  restart: unless-stopped; stop_grace_period: 30s   # :86-87
```

The base `bot` service (`docker-compose.yml:262-302`) declares no `stop_grace_period`
either, and Compose does not inherit one, so Docker's 10 s default applies to the bot
while its siblings get 30 s.

The impact is correctly self-muted: `BOT_HEALTH_CHECK_ENABLED` defaults to `False`
(`config/settings/base.py:329`), so the orphaned `bot:liveness` Redis key does not gate
web readiness by default. aiogram's own SIGTERM handling is sound
(`Dispatcher.start_polling` installs loop signal handlers and runs the shutdown hooks),
so only the grace period is at fault.

**Required fix (unchanged).** Add `stop_grace_period: 30s` to the `bot` override so all
three long-lived services share one shutdown contract. One line.

---

### ENT-012 — [LOW] — Dev startup gating is asymmetric: `web` waits for `seed`, `bot` does not

**Verdict: CONFIRMED — LOW (unchanged).** Type: `SPEC-DEVIATION` (the two long-lived
processes in the same environment start on different readiness contracts).

**Verified.** `docker-compose.dev.override.yml:27-31` adds
`depends_on: seed: {condition: service_completed_successfully}` to `web`; the `bot`
block at `:33-43` adds no `depends_on` and therefore inherits only the base
`load_catalog` + `redis` dependencies. In production the situation is the same
asymmetry by design — the prod override does not gate `bot` on `seed`, and `seed` is
`profiles: ["seed"]`-gated.

**Required fix (unchanged).** Either mirror the `seed` dependency on the dev `bot`
service, or record the deliberate difference with a comment. The second option is the
higher-ROI one: the asymmetry is defensible, it is only *accidental* right now.

---

### ENT-013 — [LOW] — Scheduler liveness marker cannot distinguish "loop alive" from "jobs succeeded"

**Verdict: CONFIRMED — LOW (unchanged).** Type: `RUNTIME-DEFECT` (observability).

**Verified.** `_write_liveness_marker()` is called unconditionally at
`scheduler.py:233`, after the nine-command hourly loop and before the daily section.
Per-command failures never propagate — `_dispatch` (`scheduler.py:165-181`) returns `1`
on exception — and cycle-level exceptions are swallowed at `scheduler.py:303-304`
(*"Scheduler cycle failed — continuing"*). `healthcheck-scheduler.sh:17-34` checks
marker presence plus, optionally, mtime age.

Production sets `SCHEDULER_HEALTH_STALE_SECONDS=7200`
(`docker-compose.prod.yml:98`), so a *stuck* loop is caught after two hours — but a
loop that keeps running and keeps refreshing the marker while every job fails stays
`healthy` indefinitely. That distinction is exactly the finding.

The second half is also correct: the first marker cannot appear until a full
nine-command cycle completes, while the healthcheck allows only
`start_period: 30s + 3 × 30s` retries — so a legitimately slow first cycle (a large
`consent_hard_delete`, a `sweep_orphaned_media` over a large `MEDIA_ROOT`) can mark a
healthy container `unhealthy` for a minute or two.

**Minor correction.** The report's evidence block attributes the marker call to the
`run_scheduler` loop at `:227`; the call site is inside `run_one_cycle` (`:233`). The
`File(s)` line is correct.

**Required fix (unchanged).** Write the marker only after a cycle in which no command
returned a non-zero code (or record the last successful cycle separately and read that),
and raise the scheduler healthcheck `start_period` to cover one full cycle. This also
gives ENT-003's duplicate run a detectable signal.

---

### ENT-014 — [LOW] — `entrypoint-test.sh` header comment wrongly claims the base entrypoint runs migrations

**Verdict: CONFIRMED — LOW (unchanged).** Type: `DOC-UPDATE`.

**Verified.** `docker/entrypoint-test.sh:3-5`:

```bash
# The base ENTRYPOINT (entrypoint.sh) already waits for the DB,
# runs migrations, and compiles translations, so this script only syncs deps ...
```

`docker/entrypoint.sh:102-110` — the executed path is:

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

No migration step. Migrations come from the explicit `bootstrap_reference_data` call at
`entrypoint-test.sh:25`. **The code is correct; only the comment is wrong**, so this is
a documentation-only fix — per the 99 handbook, code-is-better-than-docs reclassifies to
`DOC-UPDATE`, which it already effectively is.

**Impact.** A maintainer debugging the test bootstrap is sent to the wrong file, and
may conclude the explicit call is redundant and remove it — which would cost the suite
the search triggers and exchange rates.

**Required fix (unchanged).** Correct the comment to list what the base entrypoint
actually does and state that this script runs `bootstrap_reference_data` itself.

---

## Merged Findings

No findings were merged. Two soft relationships were identified; both pairs have
different root causes and different fixes, so both are retained and cross-referenced.

## Cross-Finding Analysis

- **Merge candidates:** 0 hard merges. Soft relationships: VAL-002 (ENT-005 ↔ AUT-007)
  and VAL-003 (ENT-001 + ENT-011 ↔ CFG-002). The original report's own pairing of
  ENT-002 and ENT-003 is also correct — a scheduler restart is the duplicate-digest
  trigger, but the fixes (interruptible wait vs. durable dedupe marker) are independent,
  so they stay separate.
- **Conflicting evidence:** **0 cross-phase conflicts.** The one apparent collision
  (ENT-001 "web crash-loops" vs. CFG-006 "dev stack crash-loops") is complementary:
  different containers, different causes (missing Prometheus env var vs. a bot-only
  credential breaking the shared dev settings module). ENT-001 and CFG-002 are also
  compatible — CFG-002 shows the prod-config gate is dead, ENT-001 shows the lint/type
  scope is too narrow; both mean "CI is not currently protecting the web process".
- **Dependency chains:**
  - ENT-002 → ENT-003: fix the SIGTERM handling first, otherwise the restarts that
    trigger duplicate digests keep happening.
  - ENT-004 → ENT-005 / ENT-010: bring the async entry layer inside the static gate
    before refactoring it.
  - ENT-006, ENT-008, ENT-014 all live on the `bootstrap_reference_data` call path and
    should be read together.
- **Deliberately not filed here (owned by sibling phases):** unauthenticated `/metrics`
  at the site root (phases 09/12); the dev-stack crash loop (phase 02, CFG-006); the 12
  type errors inside test files as a *code-quality* concern (phase 10 — note ENT-004
  still owns the CI-scope and red-gate half); `apps/api/` as an empty documented
  scaffold, which is not dead code.

---

## Rollout Safety

| ID | Risk | Backward-compatible? | Ordering constraint / test gap |
|----|------|----------------------|---------------------------------|
| ENT-001 | Low | Yes | No test exists for `child_exit`; add one that calls the hook with `PROMETHEUS_MULTIPROC_DIR` unset (must not raise) and set (must mark dead). |
| ENT-002 | Med | Yes | Existing scheduler tests inject a no-op `sleep_func`, so they cannot catch this; needs a real-signal integration test asserting exit 0 within seconds. |
| ENT-003 | Med | Yes | **Ordering constraint:** the durable marker and the idempotent `send_alerts` change must land together. Recording the marker first would only persist a run whose delivery is still duplicated. Any durable marker needs a migration (project rule: all schema changes via migrations). |
| ENT-004 | Low | Yes | Confirm the `test` job still passes after removing `working-directory: src/backend` — `pyproject.toml` `pythonpath` and the `test` job's own working directory interact. |
| ENT-005 | Med | Yes | The login suite covers both sides of the handshake separately; the extraction must keep both passing unchanged, and should add a test asserting both operations agree on their (deliberately different) predicates. |
| ENT-006 | Low | Yes | `test_migrate_locked.py` exists; extend with a contention case asserting the bounded wait. |
| ENT-007 | Low | Yes | Lifecycle tests cover the hooks; add one asserting the marker exists even when `_set_bot_commands` hangs. |
| ENT-008 | Med | Yes | **Fragile insertion point.** Removing the bootstrap step is the change most likely to break the suite silently. `.\Makefile.ps1 test` is the gate: confirm the trigger/seed autouse fixtures still cover what the step provided. Removing `|| true` first is the safe, reversible half. |
| ENT-009 | Med | Yes | Needs a concurrency test: promote a file, start a sweep before the `AdImage` insert commits, assert the file survives. |
| ENT-010 | Low | Yes | Apply **Half A only** (memoise the resolved user per update). Assert with a query-count test per update so the fan-out cannot regress. Do **not** change `CONN_MAX_AGE` or the per-update close under this finding. |
| ENT-011 | Low | Yes | No test needed (compose value). |
| ENT-012 | Low | Yes | No test needed (compose value). |
| ENT-013 | Low | Yes | Extend `test_scheduler_wiring.py` to assert the marker is not refreshed after a failed cycle. |
| ENT-014 | Low | Yes | Documentation only. |

**No circular dependencies** were detected among ENT-001…ENT-014.

---

## Audit-Input Defects (VAL-)

### VAL-001 — [HIGH] — ENT-004's typecheck evidence is not reproducible

> - **Action:** flagged; evidence must be corrected before the finding is actioned.
> - **Detail:** The report states `basedpyright src/` yields **16** errors including two
>   in production bot handlers (`telegram_bot/handlers/alerts.py:83`,
>   `contact.py:277`). Re-measured in the working tree at `9e96b84`,
>   `uv run basedpyright src/` yields **14** errors and **none** in production code.
>   The two cited "production errors" are environment-dependent (they depended on the
>   container's import resolution, not on the code) and must be struck from the
>   evidence. The remediation count must read **14** (12 in `src/backend` tests, 2 in
>   `telegram_bot` tests), not 16. The finding's *substance* — the CI scope gap and the
>   red gate — is independently confirmed and stands.
> - **See also:** ENT-004.

### VAL-002 — [MEDIUM] — ENT-005 and AUT-007 share one root cause: no service owns the `LoginToken` lifecycle

> - **Action:** retained as two findings, cross-referenced; **not merged** (different
>   fixes — structural extraction vs. token invalidation).
> - **Detail:** ENT-005 files the missing owner; AUT-007 files a concrete instance of
>   the same gap (`login_issue` never invalidates the browser's previous outstanding
>   token, because there is no lifecycle service that could). Phase 04 explicitly
>   scoped the token *mechanism* out as sound, so this is not a contradiction — but the
>   two findings must not be fixed by two separate ad-hoc patches.
> - **See also:** ENT-005, AUT-007.

### VAL-003 — [LOW] — Recurring anti-pattern across phases: a process contract is expressed in exactly one place and nothing checks that it is expressed everywhere

> - **Action:** advisory; not a merge.
> - **Detail:** ENT-001 (`PROMETHEUS_MULTIPROC_DIR` set only in the prod override),
> ENT-011 (`stop_grace_period` set only on `web` and `scheduler`), ENT-012 (the dev
> `bot` inherits a different `depends_on` than the dev `web`), and CFG-002 (the CI
> prod-config gate silently dead) are four instances of the same structural weakness:
> environment contracts live in single Compose files and CI does not assert that every
> environment satisfies them. A single compose-contract assertion (or moving the
> shared contract into the base file plus a CI check) would close all four at once,
> which is a materially better ROI than four independent one-line fixes.
> - **See also:** ENT-001, ENT-011, ENT-012, CFG-002.

### VAL-004 — [MEDIUM] — Cross-phase coverage could not be completed for ENT-006 and ENT-009

> - **Action:** open dependency.
> - **Detail:** Phase 03 (db/concurrency) was still executing and phase 07 (media) has
>   not run at validation time. ENT-006 (advisory-lock acquisition semantics) and
>   ENT-009 (lock 103 vs. `submit_ad`) are both lock-interaction findings and could
> duplicate or contradict a phase-03 result. ENT-009 additionally overlaps phase 05's
> AD-006 (seller-scoped photo dedup orphaning files) and is likely to be re-covered
> from the storage side by phase 07. These two must be re-checked for merge once
> phases 03 and 07 land.
> - **See also:** ENT-006, ENT-009, AD-006.

---

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 10 | ENT-002, ENT-003, ENT-004, ENT-006, ENT-007, ENT-009, ENT-011, ENT-012, ENT-013, ENT-014 |
| Reclassified | 4 | ENT-005 → `BEST-PRACTICE` (root cause corrected), ENT-010 → `BEST-PRACTICE` (split; Half B rejected as intentional design), ENT-004 → `SPEC-DEVIATION`, ENT-012 → `SPEC-DEVIATION` |
| Severity-adjusted | 4 | ENT-001 HIGH→MEDIUM, ENT-005 HIGH→MEDIUM, ENT-008 MEDIUM→LOW, ENT-010 MEDIUM→LOW |
| Merged | 0 | — |
| Rejected | 0 | No finding was stale, already-implemented, or a duplicate. |
| VAL- (cross-phase / rollout) | 4 | VAL-001 (HIGH), VAL-002, VAL-004 (MEDIUM), VAL-003 (LOW) |

### Rejected Findings

None. Every finding survived independent verification; four needed correction or
down-scoping rather than removal.

### Merged Findings

None. See VAL-002 and VAL-003 for the retained cross-phase relationships.

### Reclassified Findings

| ID | Original | New | Rationale |
|----|----------|-----|-----------|
| ENT-005 | untyped (implied `SPEC-DEVIATION`) | `BEST-PRACTICE` + MEDIUM | No defect exists today; phase 04 rated the two-phase claim zero-TOCTOU and sound. The value is a missing service owner and an oversized view module. |
| ENT-010 | untyped (implied `SPEC-DEVIATION`) | `BEST-PRACTICE` + LOW | The duplicate-lookup half is a clean-up; the connection-lifecycle half is documented intentional design and is rejected as a defect. |
| ENT-004 | untyped | `SPEC-DEVIATION` | The documented local gate (`make lint`/`make typecheck` over `src/`) and the CI gate (over `src/backend` only) disagree about the project's own contract. |
| ENT-012 | untyped | `SPEC-DEVIATION` | The two long-lived processes in one environment start on different readiness contracts with no recorded rationale. |
| ENT-014 | untyped | `DOC-UPDATE` | Code is correct; only the comment is wrong. |

### Severity-adjusted Findings

| ID | From | To | Rationale |
|----|------|-----|-----------|
| ENT-001 | HIGH | MEDIUM | Mechanism fully reproduced, but the only shipped gunicorn deployment sets the variable; latent landmine, not a live outage. |
| ENT-005 | HIGH | MEDIUM | Structural/clean-up concern with no demonstrated defect. |
| ENT-008 | MEDIUM | LOW | Real phantom schema, but contained to a throwaway test database no test or documented command reads. |
| ENT-010 | MEDIUM | LOW | No measured bottleneck at this scale; the connection half is intentional design. |

### Required Fixes (mandatory)

1. **ENT-002** — make the scheduler's wait interruptible (`_stop_event.wait`); without
   this, every stop/redeploy is a SIGKILL and ENT-003's trigger keeps firing.
2. **ENT-001** — guard `child_exit` on `PROMETHEUS_MULTIPROC_DIR` and move the variable
   into the base compose.
3. **ENT-003** — land the durable daily marker **and** the idempotent `send_alerts`
   delivery together, with a migration for the marker.
4. **ENT-004** — move CI's ruff and basedpyright to the repository root over the whole
   tree, and clear all **14** errors so the gate is green again (fix the tests, not
   production code).
5. **ENT-006** — bound advisory-lock acquisition (or log before acquiring) and correct
   the "skip" docstring.
6. **ENT-014** — correct the `entrypoint-test.sh` header comment (documentation only).

### Advisory Recommendations

- **ENT-007** — publish bot readiness markers *before* the best-effort command-menu
  registration, under an `asyncio.wait_for` budget.
- **ENT-005** — extract `apps/users/services/login_token.py`; `login_rate_limit.py` is
  the precedent, and slimming the 470-line `consent.py` is the higher-ROI half.
- **ENT-010 (Half A only)** — resolve the user once per update and stash it in the aiogram
  `data` dict; leave `CONN_MAX_AGE` and the per-update `close_old_connections` alone.
- **ENT-008** — remove `|| true` first (safe and reversible), then decide whether to drop
  the step entirely; `.\Makefile.ps1 test` is the gate.
- **ENT-009** — add a promotion grace marker rather than making ad submission depend on
  lock 103; re-check against phase 07 when it lands.
- **ENT-013** — write the scheduler liveness marker only after a clean cycle and raise
  the healthcheck `start_period` to cover one full cycle.
- **ENT-011 / ENT-012** — one-line compose changes; or, better, address the whole class
  at once per VAL-003.
