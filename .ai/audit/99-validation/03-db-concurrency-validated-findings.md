---
phase: "03"
phase_name: "Database & Concurrency Consistency"
report_type: "validated-findings"
source_report: ".ai/audit/03-db-concurrency/findings.md"
date: "2026-09-28"
validator: "Kilo (validator subagent)"
mode: "problems-only"
id_prefix: "DB"
report_status: "validated"
evidence_anchor: "9e96b84"
severity_taxonomy: ".kilo/commands/audit/phases/03-audit-db-concurrency.md#severity-taxonomy"
---

# Validated Findings — Database & Concurrency Consistency

Self-contained. Every claim below was re-derived from the source tree at
`9e96b84` or reproduced at runtime against PostgreSQL 18.6 / Django 5.2.17.
The reader needs neither the auditor's original report nor any source file.

## Verdict Summary

| ID | Title (abridged) | Auditor severity | **Validated severity** | Verdict |
|----|-------------------|-------------------|------------------------|---------|
| DB-001 | `create_draft_ad` race backstop never recovers | CRITICAL | **MEDIUM** | ADJUSTED |
| DB-002 | `record_event` aborts the caller's transaction | CRITICAL | **HIGH** | ADJUSTED |
| DB-003 | `sweep_drafts` reaps an in-progress draft | HIGH | **HIGH** | ADJUSTED → SPEC-DEVIATION |
| DB-004 | Unbounded row-lock wait stalls the bot | HIGH | **HIGH** | CONFIRMED (+ENT-006 merged) |
| DB-005 | Orphan media sweep deletes committing photos | MEDIUM | **MEDIUM** | CONFIRMED (+ENT-009 merged) |
| DB-006 | Delete sweeps undo a concurrent reactivation | MEDIUM | — | **REJECTED** |
| DB-007 | Two alert writers, no shared lock | MEDIUM | **MEDIUM** | CONFIRMED |
| DB-008 | Sweeps hold row locks for the whole sweep | MEDIUM | **MEDIUM** | CONFIRMED (evidence corrected) |
| DB-009 | `copy_ad` 500s when the bot holds the draft | MEDIUM | **LOW** | ADJUSTED |
| DB-010 | Lock "released" log never fires on rollback | LOW | **LOW** | CONFIRMED |
| DB-011 | Six sweeps pre-collect media keys for a log count | LOW | **LOW** | CONFIRMED |

**After validation: 0 CRITICAL · 3 HIGH (DB-002, DB-003, DB-004) · 3 MEDIUM
(DB-005, DB-007, DB-008) · 3 LOW (DB-009, DB-010, DB-011).** 1 rejected.

### Findings that genuinely require an architectural or structural change

| ID | Change class | What has to change |
|----|--------------|--------------------|
| DB-005 | **Architectural** | Media storage contract: a new file must not be visible in the swept `MEDIA_ROOT` until its `AdImage` row commits. Touches `apps.media` (directory policy), `apps.ads.services.submission` (promotion point) and the sweep's exclusion set. |
| DB-003 | **Architectural** | Bot↔DB write contract: the FSM must heartbeat `Ad.updated_at` on every step that changes an ad input, and the sweep predicate must switch from `created_at` to `updated_at`. |
| DB-004 | Structural | Connection/session-level timeout policy **plus** a shared bounded-retry error boundary that both processes must handle. |
| DB-008 | Structural | Per-batch commit with the advisory lock held once across all batches, in two commands. |
| DB-002 | Structural (small) | One function, but the fix requires a non-obvious constraint-mode step; see the finding. |
| DB-001, DB-007, DB-009, DB-010, DB-011 | Local | Single function, single module, or single product decision. |

---

## CRITICAL

*(none — both CRITICAL findings were downgraded; reasoning below)*

---

## HIGH

### DB-002: [HIGH] — `record_event` swallows database errors inside the caller's transaction, aborting the whole domain write

> **Validation Note:**
> - **Action:** reclassified (severity CRITICAL → HIGH; the "policy/contract change across call sites" framing is rejected)
> - **Detail:** The *mechanism* is real and independently reproduced, and the deferred-FK premise is **valid** — Django's PostgreSQL backend emits every FK as `DEFERRABLE INITIALLY DEFERRED`, so the check runs at the outermost COMMIT, not at savepoint release. But (a) **the auditor's primary recommendation is wrong**: a plain nested `transaction.atomic()` savepoint does **not** fix it (proven below), and (b) a local one-function guard **does** work, via `SET CONSTRAINTS ALL IMMEDIATE` inside the savepoint. So this is *not* a cross-call-site contract change. Severity is HIGH rather than CRITICAL because no reachable trigger exists in the current call graph: all 12 call sites pass a real `user.id`/`ad.id` or `None`, and no `AnalyticsEventType` value (longest `registration_created`, 20 chars) can overflow `varchar(30)` nor any `AdSource` value `varchar(20)`.
> - **See also:** DB-004 (landing it first converts a slow analytics INSERT into a new abort trigger), VAL-002

| Field | Value |
|---|---|
| **ID** | DB-002 |
| **Severity** | HIGH (was CRITICAL) |
| **Type** | SPEC-DEVIATION (contract stated in code is not honoured) |
| **Category** | Correctness / transaction integrity |
| **File(s)** | `src/backend/apps/core/services/analytics.py:7-8,45-60`; call sites `src/backend/apps/moderation/services/auto_moderation.py:248-255,265-278`; `src/telegram_bot/handlers/login.py:216,243-247` |
| **Status** | Open |

**Problem (confirmed).** `record_event` is documented "never raising" and catches bare
`Exception`, returning `None`. Its module docstring states it "performs NO
`transaction.atomic()` so it remains transparent to the caller's transaction
boundary" — but it *does* execute inside callers' transactions. `_fail_moderation`
and `_pass_moderation` wrap it in their own `atomic()`, themselves nested inside
`submit_ad`'s `atomic()`, so Django creates no savepoint around the INSERT. When
that INSERT fails at the database level, PostgreSQL has already aborted the
transaction, the exception is swallowed, and the caller keeps issuing statements
against a dead transaction — or, for a deferred constraint, sees success all the
way to COMMIT and loses the entire business write.

**Impact (confirmed, with the reachability caveat).** A best-effort analytics row
becomes a transaction-aborting failure of the operation it was only observing. In
`auto_moderate`, that discards the whole ad publish (`set_published` +
`transition_to(PUBLISHED)` + the moderator action log); in
`login.handle_login_orm` it discards the token claim and the `get_or_create`
user. The user-visible effect is a failed publish or a failed login blamed on a
write that was promised never to fail. **Reachability today is narrow**: the
deferred-FK trigger needs a concurrently hard-deleted user (`consent_hard_delete`,
hourly, lock 3) racing a publish; the immediate-error trigger needs a value that
no production path can produce (verified against every call site and the enum
widths). The defect becomes materially more likely the moment DB-004 lands, since
`statement_timeout` produces exactly this class of error on exactly this kind of
INSERT.

**Root Cause (confirmed).** `except Exception` around a database call that
participates in a transaction the function does not own, with no savepoint — while
the same file's sibling pattern (`TrustCalculator` at `auto_moderation.py:280-288`)
already does the right thing with a nested `atomic()`.

**Recommendation (corrected — the auditor's option (a) does not work).**
1. Preferred, and cheapest: wrap the INSERT in a nested `transaction.atomic()`
   **and issue `SET CONSTRAINTS ALL IMMEDIATE` inside that savepoint** before it.
   The `SET` is what forces the deferred check to run at the savepoint instead of
   at COMMIT; the savepoint rollback then removes the offending row and leaves the
   caller's transaction usable. `SET CONSTRAINTS` is itself transactional, so the
   mode reverts when the savepoint is released.
2. Equivalent and simpler to reason about: move the write out of the caller's
   transaction entirely — `transaction.on_commit(lambda: record_event(...))`, or
   call `record_event` after the `atomic()` block exits. This is the honest
   expression of "analytics is an observer, not a participant", and it costs three
   call-site edits.
3. Reject the bare-savepoint variant. It is the auditor's recommendation and it
   does not work (see evidence D).

Whichever is chosen, add a regression test that provokes a **real server-side**
error (not a mocked `RuntimeError`, which leaves the transaction usable) and
asserts the caller's transaction still commits. The existing
`src/backend/apps/core/tests/test_analytics_service.py:75-100` cannot reach this
mode and will keep passing either way.

**Effort:** S (1 person-day) · **Priority:** P0 (must land before DB-004)

**Evidence — independent reproduction** *(scratch DB, PostgreSQL 18.6, Django 5.2.17;
scratch database dropped after the run)*:

```text
=== A. the deferred-FK premise, checked against the live schema ===
 analytics_events_user_id_b21e3686_fk_users_id | t | t |
   FOREIGN KEY (user_id) REFERENCES users(id) DEFERRABLE INITIALLY DEFERRED

=== B. deferred-FK failure inside the caller's transaction ===
 record_event         : IntegrityError: insert or update on table
                        "analytics_events" violates foreign key constraint
 caller s write survived: False
 >>> the analytics write destroyed the caller s business write.

=== C. the auditor's recommended fix: plain nested savepoint ===
 savepoint-guarded tx : IntegrityError: ... violates foreign key constraint
 caller s write survived: False
 >>> local guard insufficient.

=== D. savepoint + SET CONSTRAINTS ALL IMMEDIATE ===
 guarded transaction   : COMMIT succeeded
 caller s write survived: True
```

Evidence D is the decisive correction: the fix is one function, and the
`SET CONSTRAINTS` step is mandatory.

---

### DB-003: [HIGH] — `sweep_drafts` reaps an ad the seller is still typing, destroying the whole listing

> **Validation Note:**
> - **Action:** reclassified (Type BEST-PRACTICE → SPEC-DEVIATION; severity HIGH held)
> - **Detail:** Confirmed and strengthened — this is a code-vs-spec deviation, not a design choice. The specification already requires an **idle** timeout ("Abandoned draft auto-deleted on idle timeout (e.g. 30 min)", `docs/01-spec/technical-specification.md:151`, and "Abandoned drafts auto-deleted on idle timeout (~30 min)", `docs/04-user-stories/seller-stories.md:39`), while the code measures **age since row creation** from `created_at` with no heartbeat. The spec-conformant fix is also the cheaper one. The auditor's alternative option (b) "extend the window to a value that cannot be exceeded by a human conversation" is **rejected**: `docs/02-database/db-retention.md:112` documents that retention values are deliberately hardcoded with no env var or CLI override, so making the window arbitrary contradicts a documented design decision.
> - **See also:** DB-001 (creates the draft that is later reaped), `sweep_orphaned_media.py:36-38` (the 2-hour staging TTL is derived from the 30-minute figure and must move with it)

| Field | Value |
|---|---|
| **ID** | DB-003 |
| **Severity** | HIGH (held) |
| **Type** | SPEC-DEVIATION |
| **Category** | Cross-process consistency |
| **File(s)** | `src/backend/apps/core/management/commands/sweep_drafts.py:44-69`; `src/backend/apps/ads/models.py:182-183`; `src/telegram_bot/handlers/ad_create/entry.py:53`; `src/telegram_bot/services/ad_data/orm.py:38-67`; `src/backend/apps/ads/services/submission.py:169-173`; `docs/01-spec/technical-specification.md:151` |
| **Status** | Open |

**Problem (confirmed, and a deviation from the spec).** The hourly `sweep_drafts`
deletes every `DRAFT` whose `created_at` is older than 30 minutes. `created_at` is
`auto_now_add`, so it is stamped the instant the seller sends `/post` — the start
of the conversation. The bot writes nothing back to the `Ad` row for the rest of
the dialog: title, description, price, category, city and photos all live in aiogram
FSM state and in `staging/` files, and the row is touched again only at
`submit_ad`. The advisory lock serialises *sweeps against each other*; nothing
coordinates the sweep with an in-flight dialog, and no row lock is taken.
`Ad.updated_at` (`auto_now`) exists and is the natural activity signal, but nothing
writes it before submission — so the spec's "idle timeout" is implemented as
"timeout since the seller opened the window".

**Impact (confirmed).** A seller who takes longer than 30 minutes between `/post`
and publish — reading moderation rules, choosing a city, re-uploading photos, or
simply walking away — returns to a bot that cannot submit: `submit_ad` does
`Ad.objects.select_for_update().get(id=input.ad_id)`, hits `Ad.DoesNotExist` and
returns `(False, ["Ad not found"])`. Everything typed is lost with no draft to
resume, and the already-downloaded `staging/` photos are reclaimed later by
`_reclaim_stale_staging`. Business effect: a seller abandons the platform after
losing typed work.

**Root Cause (confirmed).** Retention is measured from creation rather than from
last activity, and the bot issues no heartbeat while the FSM is populated — a
direct deviation from the specified idle-timeout semantics.

**Recommendation.**
1. Have the bot touch `Ad.updated_at` on every FSM step that changes the ad's
   inputs, and switch `sweep_drafts` to filter on `updated_at` (keep the 30-minute
   value — the spec sanctions it; the index `IX_ads_draft_sweep(status, created_at)`
   must become `(status, updated_at)`, which is a migration).
2. Make `submit_ad`'s "Ad not found" seller-recoverable ("your draft expired, start
   again") instead of a generic failure, per the i18n DoD.
3. Re-derive the 2-hour staging TTL in
   `src/backend/apps/media/management/commands/sweep_orphaned_media.py:36-38` so it
   stays a safe margin over the new inactivity window.

**Effort:** M (2-3 person-days) · **Priority:** P1

**Evidence — the spec says idle, the code says age:**

```text
docs/01-spec/technical-specification.md:151
  "- Abandoned draft auto-deleted on idle timeout (e.g. 30 min). No partial ads saved."
docs/04-user-stories/seller-stories.md:39
  "Abandoned drafts auto-deleted on idle timeout (~30 min); no partial ads saved."
docs/02-database/db-retention.md:32
  "| `DRAFT` | 30 minutes | `sweep_drafts` (advisory lock 4) | `IX_ads_draft_sweep` |"

src/backend/apps/core/management/commands/sweep_drafts.py:44-49
  cutoff_date = timezone.now() - timedelta(minutes=30)
  queryset = Ad.objects.filter(
      status=AdStatus.DRAFT,
      created_at__lt=cutoff_date,      # <-- dialog START, not last activity
  )
```

The auditor's §J harness is accepted as correct: a draft whose `updated_at` was
30 seconds old and whose `created_at` was 31 minutes old was destroyed, and the
submit-time re-fetch then raised `Ad.DoesNotExist`.

---

### DB-004: [HIGH] — A single blocked row lock stalls every database operation in the bot, with no lock timeout anywhere

> **Validation Note:**
> - **Action:** validated unchanged (severity HIGH held) + **ENT-006 (Phase 01) partially merged in** + mechanism wording corrected
> - **Detail:** The core claim is independently confirmed: a repo-wide search for `lock_timeout|statement_timeout|idle_in_transaction_session_timeout` returns **zero hits in `src/` and `docker/`**, and at runtime both `SHOW lock_timeout` and `SHOW statement_timeout` return `0`. **ENT-006 (Phase 01) is superseded on its timeout element** — do not ship that half twice — but ENT-006 carries two residual elements DB-004 does not cover, now folded in as a scoped addendum (see below). **Mechanism correction:** what stalls is the single asgiref `thread_sensitive` database-worker thread, **not the asyncio event loop** — the handler awaits, so the loop keeps running. The phase handbook lists "blocking ORM call freezing the async loop" as a CRITICAL condition; this finding does not meet it, and it was not claimed as CRITICAL, so HIGH is correct.
> - **See also:** DB-008 (the long holds that make the wait long), DB-010 (a different, unfixed log line), VAL-002 (rollout ordering)

| Field | Value |
|---|---|
| **ID** | DB-004 |
| **Severity** | HIGH (held) |
| **Type** | BEST-PRACTICE |
| **Category** | Availability / async dispatch |
| **File(s)** | `src/telegram_bot/middlewares/connection.py:8-16`; `src/backend/apps/ads/services/submission.py:171`; `src/backend/apps/ads/views/edit.py:117,284,322`; `src/backend/config/settings/base.py:245-266`; `src/backend/apps/core/utils/advisory_lock.py:72-87`; `src/backend/apps/core/utils/migrate_locked.py:5,86` |
| **Status** | Open |

**Problem (confirmed).** Every ORM call in the bot is dispatched with
`sync_to_async` at its default `thread_sensitive=True`, so all of them serialise
onto **one** asgiref worker thread owning one thread-local connection — exactly as
`DatabaseConnectionMiddleware` documents. Any statement that waits on a row lock
(`submit_ad`, `handle_login_orm`, `ad_edit`, `ad_archive`, `ad_reactivate`)
therefore blocks *every other* database operation in the whole bot, not just its
own handler. Nothing bounds the wait: `CONN_MAX_AGE=0` and `CONN_HEALTH_CHECKS`
are configured, but there is no `lock_timeout`, no `statement_timeout`, and no
`OperationalError`/`DatabaseError` retry anywhere in `src/` or `docker/`, and the
bot has no request-level timeout of its own.

**Impact (confirmed, mechanism restated).** During the wait the bot appears dead
to every seller — no `/post`, no photo upload, no login, no `/alerts` — because
all database work queues behind the one blocked dispatch. The wait is bounded only
by the holder, so a long sweep makes the outage last as long as the sweep. The
asyncio event loop itself is **not** blocked. In the web tier the same wait is
bounded only by gunicorn's `timeout = 60`, at which point the worker is SIGKILLed
mid-request, leaving the client with a 502 and the transaction to PostgreSQL's
rollback.

**Root Cause (confirmed).** The architecture assumes lock waits are short and rare,
but a single `thread_sensitive` worker converts one long wait into a process-wide
database stall, and no timeout was configured at either the PostgreSQL or the
application layer to turn a pathological wait into a fast, retryable failure.

**Recommendation (unchanged, and it does require a structural change).**
1. Set a per-statement lock/statement timeout on the bot's connection
   (`OPTIONS: {"lock_timeout": ..., "statement_timeout": ...}`, or `SET LOCAL` at
   the top of each `atomic()` that takes `select_for_update()`) and handle the
   resulting `OperationalError` with a bounded retry plus a seller-facing message.
2. Shorten the hold times that make the wait long (see DB-008).
3. Do **not** "fix" this by raising asgiref's worker count — `thread_sensitive`
   exists so a transaction and its connection stay on one thread, and relaxing it
   would break the single-dispatch-per-transaction guarantee the project documents.

**Merged addendum — ENT-006 (Phase 01), the two residual elements:**
- (a) **Doc-vs-impl.** `migrate_locked.py:5` claims a contender will "skip";
  `:86` uses the blocking `pg_advisory_lock` via `advisory_lock.py:74`. Decide the
  intended semantics and make the docstring match. This is a DOC-UPDATE riding on
  the same fix.
- (b) **Silent wait.** The only acquisition log line fires *after* the lock is
  granted (`advisory_lock.py:74-75`), so a blocked run emits nothing at all. Emit a
  line *before* acquisition. This is **not** DB-010: DB-010 is the **release** line
  registered on `on_commit` (`:84-86`), which never fires on rollback. Two
  different log lines at two different points — one work item, two changes.

**Effort:** M (2-3 person-days) · **Priority:** P1 (after DB-002)

**Evidence — independent reproduction:**

```text
row lock held 3.0s; waiter blocked 3.01s; exception raised: none
>>> the wait is bounded only by the holder, not by any configured timeout: True
lock_timeout setting  : 0 (0 = disabled)
statement_timeout     : 0 (0 = disabled)
```

And the absence, repo-wide:

```text
search for lock_timeout|statement_timeout|idle_in_transaction_session_timeout
  → 0 matches under src/ or docker/  (only .ai/audit/**.md prose matches)
```

Note on the auditor's §L transcript: the line "unrelated bot ORM read took 0.00s
(blocked 14.66s wall)" is easy to misread. 0.00 s is the read's own duration; the
14.66 s is queueing time on the shared worker thread. The substance (a single
contended row delays unrelated sellers) is correct.

---

## MEDIUM

### DB-005: [MEDIUM] — `sweep_orphaned_media` deletes media belonging to `AdImage` rows that are still committing

> **Validation Note:**
> - **Action:** validated unchanged (severity MEDIUM held) + **ENT-009 (Phase 01) fully merged in**
> - **Detail:** Re-verified end to end in source: promotion precedes the transaction, the sweep snapshots then walks then unlinks with no re-check, and nothing takes lock 103 on the write side. This is the **same defect and the same fix** as Phase 01's ENT-009 — do not ship it twice. **AD-003 (Phase 05) must NOT be merged in**: it shares the symptom ("a DB row and a file can disagree") but has a different root cause (no refcount on shared storage keys — `copy_ad` reuses keys while `pre_delete` deletes unconditionally) and a different fix. Classed **architectural** because the durable remedy changes the media storage contract, not one function.
> - **See also:** ENT-009 (Phase 01, absorbed), AD-003 (Phase 05, distinct root cause — do not merge)

| Field | Value |
|---|---|
| **ID** | DB-005 (absorbs ENT-009) |
| **Severity** | MEDIUM (held) |
| **Type** | SPEC-DEVIATION |
| **Category** | Cross-process consistency |
| **File(s)** | `src/backend/apps/ads/services/submission.py:161-169,217-227`; `src/backend/apps/media/management/commands/sweep_orphaned_media.py:41-50,128-181`; `src/backend/apps/media/services/filesystem.py` (`move_staging_to_permanent`) |
| **Status** | Open |

**Problem (confirmed).** `submit_ad` promotes staged files to permanent
`MEDIA_ROOT` **before** opening its `transaction.atomic()`, and only then inserts
the `AdImage` rows inside that transaction. It never takes
`AdvisoryLockId.SWEEP_ORPHANED_MEDIA` (103), so the write side and the sweep are
never serialised. The hourly sweep takes a *point-in-time snapshot* of referenced
keys, walks the whole `MEDIA_ROOT`, and deletes `on_disk - referenced` with no
re-check at delete time. Any `AdImage` row created after the snapshot whose file is
already promoted is classified as an orphan and unlinked.

**Impact (confirmed).** The committed `AdImage` row points at a file that no longer
exists: a published listing permanently loses one or all of its photos, with no
error in the submit path and no repair short of the seller re-uploading. The
exposure window is not a millisecond race — it spans the entire `os.walk` of
`MEDIA_ROOT`, minutes on a real media volume. The command also holds both the
transaction and the sweep lock for the whole filesystem traversal.

**Root Cause (confirmed).** Orphan detection is a stale snapshot with no
re-validation at delete time, and the promote-then-insert ordering puts a
permanently visible file in `MEDIA_ROOT` for a window in which no row references it.

**Recommendation.**
1. *Removes the window* (preferred, architectural): keep new files under a
   directory the sweep excludes — mirroring the existing `staging/` exclusion at
   `sweep_orphaned_media.py:64-69` — until the owning `AdImage` row commits, then
   move them. This requires a decision about where the final move happens relative
   to the transaction boundary in `submit_ad`.
2. *Narrows the window* (cheaper, defence in depth): re-check each candidate
   orphan inside a short transaction immediately before unlinking, and skip the
   file if a row now references it (deferring it to the next hourly run).

**Effort:** M (2-3 person-days) · **Priority:** P1

---

### DB-007: [MEDIUM] — Immediate-alert and daily-alert writers share no lock and both select the same `(saved_search, ad)` pair

> **Validation Note:**
> - **Action:** validated unchanged (severity MEDIUM held)
> - **Detail:** Both halves re-verified in source: `deliver_immediate_alerts` takes no advisory lock anywhere in its module and records the notification *before* dispatching the send, while the daily `send_alerts` holds `ALERT_DELIVERY_TASK` (9) across collect+persist. The correct rating and the correct decision to defer it to the `IMMEDIATE_ALERTS_ENABLED` rollout are both endorsed. One scoping note: the "recorded before sent" half is a *delivery-contract* question rather than a concurrency one, but the concurrency half stands on its own, so the finding is retained whole.
> - **See also:** PII-104 (Phase 06 — alert audience ignores consent/account state; same feature, different defect, do not merge)

| Field | Value |
|---|---|
| **ID** | DB-007 |
| **Severity** | MEDIUM (held) |
| **Type** | SPEC-DEVIATION |
| **Category** | Cross-process consistency |
| **File(s)** | `src/backend/apps/search/services/immediate_alerts.py:67-112`; `src/backend/apps/search/management/commands/send_alerts.py:54-76`; `src/backend/apps/search/services/alert_query.py:27-132`; `src/backend/apps/moderation/signals.py:56-77` |
| **Status** | Open |

**Problem (confirmed).** Two independent writers can decide to alert the same
`(saved_search, ad)` pair. The daily `send_alerts` serialises collect+persist under
`AdvisoryLockId.ALERT_DELIVERY_TASK` (9). `deliver_immediate_alerts` — fired from
the `Ad.post_save` signal via `transaction.on_commit`, so from whichever process
published the ad — takes **no** advisory lock and runs in autocommit, one
`bulk_create` per saved search. Deduplication rests entirely on the
`SavedSearchNotification` row, and `find_matching_ads` excludes previously notified
ads with a `NOT EXISTS` subquery evaluated at read time. Between the daily
command's read and its insert, the immediate path can select the same ad; the
immediate path's `ignore_conflicts=True` insert then becomes a no-op and both
writers send. The ordering is the second half: the immediate path records the
notification *before* handing off to `_executor.submit(_run_send, ...)`, so a
failed send leaves a notification row that permanently suppresses the daily
backfill the docstrings promise.

**Impact (confirmed, currently latent).** With `IMMEDIATE_ALERTS_ENABLED` on, a
subscriber can receive the same listing twice — once per-ad, once in the daily
digest — which both `alert_query.py:34-35` and `immediate_alerts.py:97` claim is
impossible. Any transient Telegram failure during an immediate send silently drops
that alert forever. Today the feature ships **off** (`IMMEDIATE_ALERTS_ENABLED`
default `False`; `false` in `.env.test:45`), so the double-send path is latent
rather than live.

**Root Cause (confirmed).** Two delivery mechanisms for the same job without a
shared serialisation primitive, plus "recorded" being used as a proxy for
"delivered" when it only means "selected".

**Recommendation.** Take `AdvisoryLockId.ALERT_DELIVERY_TASK` around the
immediate path's match+record step so the two writers serialise, and split
"selected" from "delivered" — record the notification only after a successful send
(or add an explicit delivery-state column) so a failed send is retried by the daily
backfill. Schedule with the `IMMEDIATE_ALERTS_ENABLED` rollout rather than
blocking it.

**Effort:** M (2-3 person-days) · **Priority:** P2

---

### DB-008: [MEDIUM] — Hourly and full-table sweeps hold `select_for_update()` row locks for their entire duration

> **Validation Note:**
> - **Action:** validated unchanged (severity MEDIUM held); one evidence item corrected
> - **Detail:** Both commands re-verified in source. **Correction:** the finding cites `scheduler.py:55-65` as evidence that "the hourly sweep" holds locks for its duration — that list contains `archive_sweep` only. `recompute_normalized_prices` appears in neither `HOURLY_COMMANDS` nor `DAILY_COMMANDS` (`scheduler.py:55-73`), so it is an on-demand/admin command and its blast radius is operator-triggered, not hourly. The defect and the fix are unaffected. **Confirmed as a genuine transaction-contract change**, and the risk of relaxing all-or-nothing is stated explicitly below.
> - **See also:** DB-004 (bounding the wait is only half the fix; the other half is shortening the hold)

| Field | Value |
|---|---|
| **ID** | DB-008 |
| **Severity** | MEDIUM (held) |
| **Type** | BEST-PRACTICE |
| **Category** | Contention / isolation |
| **File(s)** | `src/backend/apps/core/management/commands/archive_sweep.py:41-91`; `src/backend/apps/currencies/management/commands/recompute_normalized_prices.py:51-53,85-98,113-117`; `src/backend/apps/core/utils/scheduler.py:55-73` |
| **Status** | Open |

**Problem (confirmed).** `archive_sweep` runs hourly and wraps its *entire* sweep in
one `transaction.atomic()`, iterating every eligible ad inside it and calling
`transition_to()` per row — a `refresh_from_db()` plus a `save()` plus the
`post_save` search-cache invalidation, so the row lock is held for two round-trips
plus signals, for as long as the whole population takes.
`recompute_normalized_prices` is worse in shape: it walks the entire non-draft ad
table in 500-row batches, taking `select_for_update()` on each batch, but all
inside the one outer transaction — so the locks **accumulate** rather than release.

**Impact (confirmed).** No live *reader* is starved (READ COMMITTED + MVCC;
`isolation_level = read committed` verified at runtime), but any live *writer*
touching a locked ad blocks: the bot's `submit_ad`, the web's `ad_edit` /
`ad_archive` / `ad_reactivate`, and moderation's approve/reject all open
`select_for_update()` on the same row. Per DB-004 that wait lands on the bot's
single shared worker thread, so the blast radius is the whole Telegram bot for the
duration of the sweep, and web requests hitting the same row are killed by
gunicorn's 60 s timeout. The long transaction also pins dead row versions for its
whole life, feeding autovacuum lag on the hottest table in the system.

**Root Cause (confirmed).** All-or-nothing atomicity was applied to the whole sweep
for simplicity, without noticing that the atomicity that matters is per-batch. The
same codebase already has the correct "short transaction + lock only for the
count-to-mutate sequence" split in `backfill_thumbnails`.

**Risk of relaxing the all-or-nothing guarantee (explicitly required).** A
per-batch commit means a mid-sweep failure leaves earlier batches applied and the
sweep re-runs on the next tick. Re-running is *safe* for both commands — their
predicates are time-based and re-derived, `archive_sweep`'s `transition_to` is
idempotent per row, and `recompute_normalized_prices` already skips rows whose
normalised value is unchanged. What is genuinely lost is the *meaning of the
command's outcome*: "Archived N ads" becomes a per-batch count, and a non-zero
exit no longer implies the whole population was processed. Two invariants must
therefore be preserved explicitly, or the relaxation is a net loss:
1. the advisory lock is still taken **once and held across every batch** — moving
   the commit inside the loop while the lock is released per batch would let two
   invocations interleave, which is strictly worse than the current behaviour;
2. the queryset is **re-derived at the start of each batch** rather than iterated
   from a single long-lived cursor, so a batch cannot act on rows another batch
   already changed.

**Recommendation.** Take the advisory lock once at the outer level; commit every
batch (100-500 rows); re-derive the queryset per batch; accumulate and log a
per-batch count plus a total. Add a `lock_timeout` (DB-004) so a contended batch
fails fast instead of queueing behind the sweep. Add a regression test that fails
in batch *N* and asserts batches 1..*N*-1 are committed — i.e. the *opposite* of
what `test_sweep_archive.py` currently implies.

**Effort:** M (2-3 person-days) · **Priority:** P2

---

## LOW

### DB-009: [LOW] — `copy_ad` has no handling for the single-DRAFT invariant

> **Validation Note:**
> - **Action:** reclassified (severity MEDIUM → LOW); the stated impact is **factually wrong on both counts**
> - **Detail:** The service-level gap is real, but (a) **there is no web route for `copy_ad`** — zero matches in `src/backend/apps/ads/views/` and in `src/backend/templates/` — so "a 500 on the web route" is unsupported; and (b) the bot handler does **not** leak an unhandled exception: `ad_copy.py:53-62` wraps the call in `try/except PermissionError` / `except Exception`, logs, and answers the user. What actually remains is that the seller receives `"Failed to copy ad: {error}"` with the raw psycopg `IntegrityError` text (including the constraint name) interpolated into a user-facing message, for a scenario the bot FSM makes possible. The auditor's own §O evidence — that the rollback is correct and no partial copy survives — is accepted.
> - **See also:** DB-001 (the sibling creator of the same invariant)

| Field | Value |
|---|---|
| **ID** | DB-009 |
| **Severity** | LOW (was MEDIUM) |
| **Type** | BEST-PRACTICE |
| **Category** | Cross-process consistency / error surface |
| **File(s)** | `src/backend/apps/ads/services/copy_service.py:28-68`; `src/backend/apps/ads/models.py:353-357`; `src/telegram_bot/handlers/ad_copy.py:53-62` |
| **Status** | Open |

**Problem (confirmed, impact reduced).** `copy_ad` creates a second `DRAFT` row
while the partial unique constraint `uq_ads_single_draft_per_user` guarantees at
most one. It does not delete or reuse the existing draft (unlike
`create_draft_ad`, which deliberately does delete-then-recreate) and does not catch
the resulting `IntegrityError`. The transaction itself is correct: the failed insert
is rolled back and no partial copy survives.

**Impact (corrected).** The single production caller — the bot's `/copy` handler —
catches the error, so there is no crash. The real user-visible effect is a generic
failure message containing internal database text, instead of a message that tells
the seller what to do next.

**Root Cause (confirmed).** The single-draft invariant is enforced solely by a
database constraint with no shared service-level policy for "what happens when a
second draft is requested", and only one of the two creators implements a policy.

**Recommendation.** Decide the product rule once and apply it in both creators:
either "a new draft replaces the current one" (copy deletes the existing DRAFT and
its images inside the same transaction, matching the documented Option D pattern in
`orm.py:51-54`), or "a second draft is rejected with a message" (catch the
`IntegrityError` at a savepoint and raise a domain error the handler renders). The
handler message must then be translated and must not interpolate a raw exception —
per the i18n DoD. Add a test seeding an in-flight DRAFT and asserting the chosen
rule.

**Effort:** S (1 person-day) · **Priority:** P2

---

### DB-010: [LOW] — The transaction-scoped lock's "released" log fires only on commit, never on the rollback operators need

> **Validation Note:**
> - **Action:** validated unchanged (severity LOW held)
> - **Detail:** Re-verified at `advisory_lock.py:81-87`: the release message is registered with `transaction.on_commit`, which runs only on commit, while PostgreSQL releases `pg_advisory_xact_lock` on both paths. The lock's *behaviour* is correct and must not change. Distinct from DB-004's merged addendum item (b), which concerns the *acquisition* log firing only after the lock is granted — two different log lines at two different points; treat them as one work item with two edits, not as one finding.
> - **See also:** DB-004 (addendum b — the acquisition-side log)

| Field | Value |
|---|---|
| **ID** | DB-010 |
| **Severity** | LOW (held) |
| **Type** | BEST-PRACTICE |
| **Category** | Observability |
| **File(s)** | `src/backend/apps/core/utils/advisory_lock.py:81-87` |
| **Status** | Open |

**Problem (confirmed).** The transaction-scoped branch registers its
"Released transaction advisory lock N" message with `transaction.on_commit(...)`.
An `on_commit` callback runs only on commit, so the release log line is emitted
exactly when nothing went wrong and omitted precisely when the sweep failed. The
message that reads "released" is a proxy for "the sweep succeeded", not for "the
lock is free".

**Impact (confirmed, diagnostic only).** When a scheduled sweep aborts, the
operator sees the "Acquired transaction advisory lock N" line with no matching
release and cannot tell from the log whether the lock is still held (it is not) or
whether the process died holding it (it cannot — that is the point of the
xact-scoped variant). Lock behaviour is verified correct at runtime and is not at
issue.

**Recommendation.** Wrap the body in `try/finally` and log the release from the
`finally`. The behaviour of the lock itself must not change; the runtime check that
the lock is gone after a rollback must continue to pass.

**Effort:** S (< 1 person-day) · **Priority:** P2

---

### DB-011: [LOW] — Six delete/purge sweeps pre-collect media keys inside the lock-held transaction only to log a count

> **Validation Note:**
> - **Action:** validated unchanged (severity LOW held); the count corrected from five to six commands
> - **Detail:** Re-verified in all six commands. The auditor's own title says "Five" while its body, impact, recommendation and `File(s)` row all say six; six is correct. High ROI under project rule 15 (small, focused code) and a pure simplification with no behaviour change.
> - **See also:** none

| Field | Value |
|---|---|
| **ID** | DB-011 |
| **Severity** | LOW (held) |
| **Type** | BEST-PRACTICE |
| **Category** | Maintainability |
| **File(s)** | `src/backend/apps/core/management/commands/delete_sweep.py:62-66,80`; `sweep_drafts.py:60-66,77`; `purge_failed_ads.py:61-65,79`; `purge_rejected_ads.py:62-66,81`; `purge_deleted_ads.py:62-66,80`; `consent_hard_delete.py:69-73,97` |
| **Status** | Open |

**Problem (confirmed).** Each of these six commands builds `storage_keys` — a full
scan of `AdImage` rows for every doomed ad, expanding every thumbnail variant —
inside the `transaction.atomic()` + advisory-lock block, immediately before the
cascade delete. The files themselves are deleted by the `AdImage` `pre_delete`
signal via `transaction.on_commit()`. The only consumer of `storage_keys` is
`len(storage_keys)` inside the closing `logger.info(...)`.

**Impact (confirmed).** One redundant `AdImage` scan per sweep executed while the
sweep's advisory lock and transaction are held, whose sole purpose is a log number,
plus a comment ("Collect storage keys for physical media cleanup before ORM
cascade") that tells a future maintainer the loop performs the deletion when it does
not. On the `consent_hard_delete` path the scan covers every image of every
hard-deleted user — the largest of the six.

**Root Cause (confirmed).** The pre-collection predates the `pre_delete` +
`on_commit` mechanism and was never removed when the mechanism was added; the
explanatory comment was added at the deletion site but not at the collection site.

**Recommendation.** Delete the `storage_keys` collection from all six commands and
drop `len(storage_keys)` from their log lines, or keep the number by counting
`AdImage` rows in the same statement the delete already needs. Pure simplification:
no behaviour change, no test change.

**Effort:** S (< 1 person-day) · **Priority:** P2

---

## Rejected Findings

### DB-006: ~~[MEDIUM] — Delete and purge sweeps delete without a row lock, silently undoing a concurrent reactivation~~ [REJECTED]

> **Rejection reason:** the stated mechanism is factually wrong, and the
> reproduction is not reproducible against the production code path. The finding
> asserts that "Django's `QuerySet.delete()` issues its `DELETE` filtered on primary
> key only — not on the status/timestamp predicate it selected with." That is not
> how Django works on PostgreSQL. `Ad` is not fast-deletable
> (`Collector.can_fast_delete` → `False`, because of the `AdImage`/M2M cascades),
> so `QuerySet.delete()` routes through the collector, and the collector **evaluates
> the queryset inside `delete()`** — `deletion.py:281` → `add()` →
> `QuerySet.__bool__` → `_fetch_all()` — immediately before issuing the DELETE. The
> status/timestamp predicate is therefore re-applied at delete time, by the same
> statement. A concurrent write that makes the row ineligible wins.
>
> Reproduced directly, using the exact production code path
> (`Ad.objects.filter(status=ARCHIVED, archived_at__lt=cutoff).delete()`, with the
> reactivation committed from a genuinely separate session between the sweep's
> `count()` and its `delete()`): the DELETE reported `n = 0` and the row finished as
> `on_moderation`. The auditor's §K transcript claims `final row -> GONE`; that
> outcome cannot be produced by `delete_sweep.py` as written.
>
> `archive_sweep` does still need `select_for_update()` — for a different reason
> (it mutates rows per-row and can interleave with a concurrent status change
> between the SELECT and each `transition_to`, which its `refresh_from_db()` guard
> already handles), but that is not this finding and the five other sweeps have no
> equivalent lost-update exposure. The only real residue is cosmetic — the logged
> count can disagree with the number actually deleted, and the pre-delete
> `values_list` scan is redundant — and that residue is already covered by DB-011.

```text
=== delete_sweep (no row lock) vs a real concurrent reactivation ===
seeded ARCHIVED ad: 8
sweep SELECT found  : 1 ids: [8]
reactivation committed from other session: status=ON_MODERATION
sweep DELETE reported n = 0
FINAL STATE          : on_moderation
>>> reactivation SURVIVED — the DELETE re-evaluated the filter.
```

---

## Adjusted Findings — Detailed Rationale

### DB-001: ~~[CRITICAL]~~ → **[MEDIUM]** — `create_draft_ad`'s race backstop always fails instead of recovering

> **Validation Note:**
> - **Action:** reclassified (severity CRITICAL → MEDIUM)
> - **Detail:** The *mechanism* is confirmed and independently reproduced, but every
>   part of the claimed consequence is wrong, and the trigger is unreachable in the
>   shipped topology.
>
> **Confirmed:** the recovery branch is genuinely dead. Because Django creates no
> savepoint for the outermost `atomic()`, the `except IntegrityError` handler's
> first statement runs against an aborted transaction.
>
> **Wrong — the exception class.** The finding and its §B evidence both report
> `TransactionManagementError`. Production gets **`django.db.utils.InternalError`**.
> `TransactionManagementError` is only raised when `connection.needs_rollback` is
> set, and that flag is set by Django's atomic machinery when an exception passes
> *through* the block — which, here, it does not, because the `IntegrityError` is
> caught inside it. The next statement therefore reaches the server and PostgreSQL
> returns "current transaction is aborted".
>
> **Wrong — "the seller's ad is destroyed."** The report's Impact states the
> pre-existing DRAFT "is *not* deleted either" but the Executive Summary claims the
> seller's ad is destroyed. Neither is true in the damaging sense: the rollback
> **preserves** the pre-existing DRAFT row, and no `pre_delete`/`on_commit` file
> deletion fires. Reproduced: the DRAFT the seller already had was still present
> afterwards, with the same primary key.
>
> **Wrong — "unrecoverable."** A sequential retry — which is what any user or a
> subsequent update does — succeeds. Reproduced: delete-then-recreate left exactly
> one DRAFT.
>
> **Unreachable in the shipped topology.** `create_draft_ad` has exactly one
> production caller: `ad_create/entry.py:53` (the `/post` handler). The web process
> never calls it — the symbol is imported only from `src/telegram_bot`. The
> auditor's own §H proves that one bot process serialises concurrent calls on the
> single asgiref `thread_sensitive` worker, so the unique index cannot fire within
> a single bot process. §H2's "5 of 6 failed" comes from six *OS threads* calling
> the function body directly, which is not a topology the deployment has. A trigger
> requires a second bot process.
>
> **Taxonomy.** None of the phase handbook's CRITICAL conditions apply — this is
> not a non-atomic write leaving partial data (the rollback is complete) and not a
> lost update. It is a dead safety net: a genuine correctness bug, cheap to fix,
> currently unreachable.
>
> The fix is unchanged and remains a local one: wrap the `Ad.objects.create(...)`
> in a nested `transaction.atomic()` so the `except IntegrityError` branch runs
> against a usable transaction, mirroring `login.handle_login_orm:226-240` in the
> same codebase. Keep the existing cleanup-then-retry. Add a regression test that
> forces `uq_ads_single_draft_per_user` to fire and asserts a draft is returned.

```text
=== create_draft_ad recovery branch, against the real constraint ===
pre-existing DRAFT id: 9
outcome              : InternalError: current transaction is aborted, commands
                       ignored until end of transaction block
DRAFTs for user      : [9] | pre-existing id still present: True
>>> rollback PRESERVED the seller s draft; nothing was destroyed.
sequential retry     : OK, new draft 11 | DRAFT count: 1
```

---

## Cross-Phase Merge Decisions

| Incoming | From | Decision | Detail |
|----------|------|----------|--------|
| **ENT-006** | Phase 01 | **Superseded on its timeout element; residual folded into DB-004** | ENT-006's premise is confirmed and independently re-verified, and DB-004 covers "no `lock_timeout`/`statement_timeout` anywhere" — do not ship that half twice. ENT-006's two residual elements are *not* covered by DB-004 or DB-010 and are carried in DB-004 as a scoped addendum: (a) `migrate_locked.py:5` docstring says a contender "skips" while `:86` blocks on `pg_advisory_lock`; (b) the acquisition log fires only *after* the lock is granted (`advisory_lock.py:74-75`), so a blocked run emits nothing. |
| **ENT-009** | Phase 01 | **Fully absorbed by DB-005** | Identical defect and identical fix. ENT-009's chain re-verified end to end. Do not ship separately. |
| **AD-005** | Phase 05 | **Duplicate of DB-001 — one fix, and severities must agree** | Both describe the same `except IntegrityError` retry inside the outermost `atomic()` in `create_draft_ad`. DB-001 is now MEDIUM; AD-005 is filed HIGH. They must be re-rated consistently or the final report will present a CRITICAL/HIGH pair for a defect with no data loss. Raised as VAL-003. |
| **AD-003** | Phase 05 | **Do NOT merge** | Shares the symptom "a DB row and a file can disagree" with DB-005, but the root cause differs (no refcount on shared storage keys) and so does the fix. |
| **PII-104** | Phase 06 | **Do NOT merge** | Same feature (`apps/search` alerts) but a different defect (recipients selected by `is_active` alone, ignoring consent/account state). |
| **AUT-006** | Phase 04 | **Do NOT merge** | Unrelated (`SESSION_COOKION_AGE`); already de-duplicated by the phase-04 validator's VAL note. |

## Cross-Phase Conflicts

**VAL-003 — severity disagreement on the same defect (CRITICAL, must resolve before
the final report ships).** `AD-005` (Phase 05, HIGH) and `DB-001` (Phase 03) are the
same defect. Independently reproduced, it destroys no data and is self-healing, so
both must be rated MEDIUM. A tracker keyed on either ID must point at one work item.

**VAL-004 — audit-input evidence quality.** Two of the auditor's reproductions do
not hold against the production code path and must not be cited in the final report
without the correction attached: §K (DB-006 — see the rejection above) and §B's
exception class (DB-001 reports `TransactionManagementError`; production raises
`InternalError`). Minor internal inconsistency also noted: the R-01 row in the
source report says "3 total connections" while the retained
`verification-output.txt` §I says "2" — the same run cannot produce both.

---

## Rollout Safety

| Order | ID | Risk of the change | Backward-compatible? | Test gap that must be closed |
|-------|----|--------------------|----------------------|------------------------------|
| 1 | DB-002 | **High — the documented fix does not work.** A bare savepoint leaves the caller just as broken. Shipping it would close the ticket without fixing the defect. | Yes | `test_analytics_service.py` only mocks a Python-level `RuntimeError`, which structurally cannot reach the failure mode. Add a case with a **real server-side** error asserting the caller's transaction still commits. |
| 2 | DB-004 | Med — a timeout converts hangs into errors; every `select_for_update()` caller gains a new `OperationalError` path that must be handled or it surfaces as a 500. | Yes | No test asserts a bounded wait. Add one that holds a row lock and asserts the bot-side call fails fast rather than hanging. |
| 3 | DB-003 | High — changes retention semantics. A wrong `updated_at` choice either reaps live drafts or keeps junk forever; the `IX_ads_draft_sweep` index must change with it. | Yes | No test exercises a long dialog across the sweep boundary. Add one that back-dates `updated_at` and asserts the draft survives. |
| 4 | DB-005 | Med — re-checking before unlink can skip a file a racing insert just claimed, deferring it to the next hourly run. The architectural variant changes the media directory contract. | Yes | No test covers "orphan file whose `AdImage` row appears during the sweep". Add one. |
| 5 | DB-008 | Med — batching changes the all-or-nothing guarantee: a mid-sweep failure now leaves earlier batches applied, and the command's exit code no longer implies the whole population was processed. The advisory lock must still be held once across all batches. | Yes | `test_sweep_archive.py` asserts the lock structure, not batch boundaries. Add a failure-in-batch-*N* assertion that batches 1..*N*-1 **are** committed. |
| 6 | DB-001 | Low — the retry path is currently unreachable, so nothing depends on its broken behaviour; but it is a hot bot path. | Yes | No test forces `uq_ads_single_draft_per_user` to fire in `create_draft_ad`. Add one asserting a draft is returned. |
| 7 | DB-007 | Low — taking the shared lock serialises the two alert writers; must not deadlock with `send_alerts`, which holds it across network-free work only. | Yes | `test_alert_query.py` covers single-writer idempotency. Add a two-writer case. |
| 8 | DB-009 | Low — a product decision (replace vs reject) may change what sellers see. | Depends on the chosen rule | `test_copy_ad.py` documents the constraint but never seeds a pre-existing DRAFT. |
| 9 | DB-010 | Low — log-only; must not alter lock acquisition or release. | Yes | `test_advisory_lock_release_log.py` asserts the `on_commit` registration and **must be updated** to assert the `finally` path. |
| 10 | DB-011 | Low — removal only; the log line loses a number. | Yes | `test_sweep_delete.py` asserts the deletion path, not the key collection. No new test needed. |

**Mandatory ordering constraint (VAL-002): DB-002 must land before DB-004.** Adding
`statement_timeout` produces `OperationalError` on exactly the kind of INSERT
`record_event` issues, and `record_event` currently swallows it — so landing DB-004
first would convert a latent defect into a live one and, in the deferred-constraint
case, still lose the caller's write. The auditor's roadmap already orders them
correctly (DB-002 at #2, DB-004 at #4); this constraint is now explicit because it
is load-bearing rather than incidental.

**Rollout-safety blocker found by this validation (VAL-001): ID namespace
collision.** `DB-001`, `DB-002`, `DB-007` and `DB-010` are **already-used IDs
hard-coded in shipped source and tests for entirely different defects**:

| Location | Existing text | Refers to |
|----------|---------------|-----------|
| `src/backend/apps/core/utils/advisory_lock.py:34` | "…to prevent the autocommit-release bug (DB-001)." | a previous cycle's autocommit bug |
| `src/backend/apps/core/utils/advisory_lock.py:61-62` | "ID 10 is intentionally unused/reserved; it was formerly QUEUE_PROCESSING and was removed in DB-007." | a previous cycle's `QUEUE_PROCESSING` removal |
| `src/backend/apps/core/management/commands/archive_sweep.py:47` | "DB-010: acquire row-level lock via select_for_update()…" | a previous cycle's row-lock hardening |
| `src/telegram_bot/tests/test_create_draft_ad.py:112` | "Verifies DB-001 and DB-002 fixes…" | a previous cycle's atomicity fixes |

Any tracker, grep, or code comment keyed on `DB-00N` will therefore collide with
shipped source. This cycle's tracker must be keyed on a cycle-scoped prefix.

---

## VAL- Findings (validation-level)

### VAL-001 — `DB-00N` IDs collide with IDs already hard-coded in shipped source and tests

- **Severity:** HIGH (tracker integrity — this is what a rollout blocker looks like)
- **Type:** BEST-PRACTICE
- **Evidence:** the four locations tabulated above, all verified at `9e96b84`.
- **Detail:** the audit pipeline reuses the `DB-` prefix for a new cycle while
  production code and tests already cite `DB-001`, `DB-002`, `DB-007` and `DB-010`
  meaning *previous* defects. Phase 04's validator raised the identical class of
  problem (VAL-002 there, IDs `AUT-001`/`AUT-002` hard-coded in
  `permissions.py:117` and `consent.py:256`), so this is a systemic pipeline issue,
  not a one-off.
- **Recommendation:** key this cycle's tracker on a cycle-scoped prefix (e.g.
  `03-DB-00N`) and adopt the same convention for the `VAL-` prefix, whose IDs are
  also being reused across phases (phase 01 already used VAL-001…VAL-005).

### VAL-002 — Mandatory ordering: DB-002 before DB-004

- **Severity:** MEDIUM (rollout-ordering constraint)
- **Type:** BEST-PRACTICE
- **Detail:** `statement_timeout`/`lock_timeout` produce a server-side error on the
  same INSERT `record_event` swallows. Because `record_event`'s swallow is what
  turns a failed analytics write into a failed business transaction, landing DB-004
  first activates DB-002's blast radius. Both must land; the order is not
  cosmetic.

### VAL-003 — `AD-005` (Phase 05) and `DB-001` (Phase 03) are one defect filed twice, with disagreeing severities

- **Severity:** CRITICAL (cross-phase conflict — must resolve before the final
  consistency audit)
- **Type:** SPEC-DEVIATION (of the audit process)
- **Detail:** both describe the same dead `except IntegrityError` retry in
  `create_draft_ad`. Phase 05's auditor filed it HIGH; phase 03 filed it CRITICAL;
  independent reproduction shows neither is right — MEDIUM. The duplicate must be
  collapsed to one work item and one severity, or the final report will state a
  CRITICAL and a HIGH for a defect that destroys no data.

### VAL-004 — Two of the retained runtime reproductions do not survive contact with the production code path

- **Severity:** MEDIUM
- **Type:** SPEC-DEVIATION (of the audit input)
- **Detail:** §K asserts a concurrent reactivation is deleted; against
  `delete_sweep.py` as written the reactivation survives and the DELETE reports
  `n = 0` (basis for the DB-006 rejection). §B reports
  `TransactionManagementError`; production raises `InternalError`. Additionally the
  R-01 row reports "3 total connections" while the retained
  `verification-output.txt` §I reports "2" for the same run. These must not be
  cited in the final report without the correction attached.

---

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 6 | DB-004 and DB-005 carry merge addenda (ENT-006 / ENT-009); DB-008 carries an evidence correction; DB-007, DB-010, DB-011 are unchanged |
| Reclassified | 4 | DB-001 (CRITICAL→MEDIUM), DB-002 (CRITICAL→HIGH), DB-003 (→SPEC-DEVIATION, HIGH held), DB-009 (MEDIUM→LOW) |
| Merged | 2 | ENT-006 → DB-004 (partial), ENT-009 → DB-005 (full) |
| Rejected | 1 | DB-006 |
| VAL- (cross-phase / rollout) | 4 | VAL-001, VAL-002, VAL-003, VAL-004 |

### Rejected Findings

| ID | Title | Reason |
|----|-------|--------|
| DB-006 | Delete and purge sweeps delete without a row lock, silently undoing a concurrent reactivation | The stated mechanism is false: `QuerySet.delete()` re-evaluates the filter inside `delete()` (`deletion.py:281 → add → QuerySet.__bool__ → _fetch_all`), so the DELETE re-asserts `status`/`archived_at`. Reproduced against the production path: reactivation survived, `n = 0`. §K is not reproducible. |

### Merged Findings

| Original ID | Merged Into | Rationale |
|-------------|-------------|-----------|
| ENT-006 (Phase 01) | DB-004 (partial) | Identical root cause for the timeout element. Two residual elements (blocking-vs-"skip" docstring; acquisition log fires only after grant) are carried in DB-004 as a scoped addendum because neither DB-004 nor DB-010 covers them. |
| ENT-009 (Phase 01) | DB-005 (full) | Identical defect and identical fix: promote-before-transaction in `submission.py:166` vs snapshot→walk→unlink in `sweep_orphaned_media.py:137-165`, with nothing serialising them. |
| AD-005 (Phase 05) | DB-001 (duplicate — not yet collapsed) | Same defect. Logged as VAL-003; collapse pending. |

### Reclassified Findings

| ID | Original Type | New Type | Rationale |
|----|---------------|----------|-----------|
| DB-001 | BEST-PRACTICE | SPEC-DEVIATION | A documented backstop (`uq_ads_single_draft_per_user` retry) is dead code in practice. Severity CRITICAL→MEDIUM: no data loss, self-healing, and unreachable without a second bot process. |
| DB-002 | BEST-PRACTICE | SPEC-DEVIATION | The module docstring states a guarantee ("never raising", "transparent to the caller's transaction boundary") that the implementation cannot honour. Severity CRITICAL→HIGH. |
| DB-003 | BEST-PRACTICE | SPEC-DEVIATION | The spec mandates an *idle* timeout; the code implements age-since-creation. Severity HIGH held. |
| DB-009 | BEST-PRACTICE | SPEC-DEVIATION (contract) | No shared service-level policy for the single-draft invariant, and a raw driver error reaches a user-facing message. Severity MEDIUM→LOW; the claimed 500/unhandled-exception impact is not reproducible. |

### Severity movement

| | CRITICAL | HIGH | MEDIUM | LOW | Total open |
|---|---|---|---|---|---|
| Auditor | 2 | 2 | 5 | 2 | 11 |
| **Validated** | **0** | **3** | **3** | **3** | **9** |

---

## Validation Evidence

Re-derived independently of the auditor's harness. Method: source reading at
`9e96b84`; a read-only schema introspection over psycopg; and a purpose-built probe
run in the `mko-bazuna-test` compose project against PostgreSQL 18.6 / Django
5.2.17 on a scratch database, which was **dropped** afterwards. No production file
was modified; no test suite was mutated.

| ID | Check | Result |
|----|-------|--------|
| V-01 | `analytics_events` FKs are `DEFERRABLE INITIALLY DEFERRED` (justifying DB-002's deferred-constraint premise) | **TRUE** — confirmed in `pg_constraint`; Django's PostgreSQL backend emits every FK this way. |
| V-02 | Does `create_draft_ad`'s recovery branch execute? | **NO** — `InternalError: current transaction is aborted`, not `TransactionManagementError`. |
| V-03 | Does the failed `create_draft_ad` destroy the seller's DRAFT? | **NO** — the pre-existing DRAFT survives the rollback, same primary key. |
| V-04 | Is `create_draft_ad` self-healing on a sequential retry? | **YES** — exactly one DRAFT after delete-then-recreate. |
| V-05 | Does a plain nested savepoint fix DB-002? | **NO** — COMMIT still fails; the caller's business write is still lost. |
| V-06 | Does `SET CONSTRAINTS ALL IMMEDIATE` inside a savepoint fix DB-002? | **YES** — COMMIT succeeds; the caller's write survives. |
| V-07 | Does `QuerySet.delete()` re-assert the sweep filter at DELETE time? | **YES** — a reactivation committed between the sweep's SELECT and DELETE survives; the DELETE reports `n = 0`. Basis for the DB-006 rejection. |
| V-08 | Is any lock/statement timeout configured? | **NO** — zero hits in `src/` and `docker/`; `SHOW lock_timeout` and `SHOW statement_timeout` both return `0`. |
| V-09 | Is a blocked `select_for_update()` wait bounded? | **NO** — a 3 s hold blocks the waiter 3.01 s with no exception raised. |
| V-10 | Is `CONN_MAX_AGE=0` a defect? | **NO** — deliberate documented design (`base.py:260` "PgBouncer async safety"; `connection.py:1-16` explains the `sync_to_async` requirement). Correctly filed as PASS (R-02), not a finding. Phase 01's ENT-010 half B was rejected on the same grounds. |
| V-11 | Do the DB-004 / DB-002 / DB-003 / DB-008 findings need a cross-cutting contract change? | DB-002 **no** (one function, but the `SET CONSTRAINTS` step is mandatory); DB-003 **yes** (bot↔DB heartbeat contract); DB-004 **yes** (timeout policy + a shared retry boundary); DB-008 **yes** (per-batch commit with the lock held once — risk of relaxing all-or-nothing stated in the finding). |

**Cleanup performed:** scratch database `audit03v_probe` dropped (verified absent);
both probe scripts deleted; the phantom `mko_bazuna` database left untouched
(39 tables, no `django_migrations`).

---

## Checkpoint 1 — Auditor analysis

- **Stage:** Auditor analysis
- **Findings in scope:** 11 (CRITICAL 2, HIGH 2, MEDIUM 5, LOW 2)
- **Evidence anchor:** `.ai/audit/03-db-concurrency/findings.md`; runtime harness `verify_db.py` + retained `verification-output.txt`; code anchor `9e96b84`
- **Dependencies / blockers:** none — the source report was ingestible and self-describing
- **Checkpoint status:** closed

## Checkpoint 2 — Researcher verification

- **Stage:** Researcher verification
- **Findings in scope:** 11 · cross-phase conflicts: 1 (VAL-003) · merge candidates: 4 (ENT-006, ENT-009, AD-005, AD-003) · duplicates rejected: 1 (AD-003 does not merge)
- **Evidence anchor:** phase-01 validated report (VAL-004 open dependency), phase-05 result (AD-005/AD-003), phase-06 result (PII-104)
- **Dependencies / blockers:** ENT-006 and ENT-009 merge decisions resolved; AD-005/DB-001 duplicate remains open as VAL-003
- **Checkpoint status:** closed

## Checkpoint 3 — Per-finding validation

- **Stage:** Per-finding validation
- **Findings in scope:** 11 — Validated 6 (DB-004, DB-005, DB-007, DB-008, DB-010, DB-011), Reclassified 4 (DB-001, DB-002, DB-003, DB-009), Rejected 1 (DB-006)
- **Evidence anchor:** 11 independent checks (V-01…V-11) above; scratch-DB probe output quoted inline per finding
- **Dependencies / blockers:** DB-002 must precede DB-004 (VAL-002); tracker must use a cycle-scoped ID prefix (VAL-001)
- **Checkpoint status:** closed

## Checkpoint 4 — Final consistency audit

- **Stage:** Final audit
- **Findings in scope:** 9 open (0 CRITICAL, 3 HIGH, 3 MEDIUM, 3 LOW) + 1 rejected + 4 VAL
- **Evidence anchor:** this report, self-contained
- **Dependencies / blockers:** VAL-001 and VAL-003 must be resolved by the coordinator before the final report is assembled — they are the only items that would otherwise cause the shipped report to contradict itself or its own codebase
- **Checkpoint status:** closed
