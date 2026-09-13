---
# Report metadata
phase: "03"
phase_name: "Database & Concurrency Consistency"
date: "2026-09-12"
auditor: "Executor (subagent)"
mode: "problems-only"
id_prefix: "DB"
report_status: "draft"
severity_taxonomy: ".kilo/commands/audit/phases/03-audit-db-concurrency.md#severity-taxonomy"
---

# Audit Findings — Database & Concurrency Consistency

## Executive Summary

Three transaction-atomicity gaps and one async/event-loop-blocking pattern were identified across the dual-process Django + aiogram system. One CRITICAL finding allows a bot-submitted ad to persist in a partial state if auto-moderation fails after the ad is committed. One HIGH finding exposes the aiogram event loop to blocking Redis I/O. Two MEDIUM findings cover non-atomic ban/audit-log writes and a split-transaction login flow.

## Scope & Methodology

**Scope:** Transaction boundaries around multi-row domain writes in `src/backend/apps/ads/services/submission.py`, `src/backend/apps/moderation/services/auto_moderation.py`, `src/backend/apps/moderation/admin_actions.py`, `src/telegram_bot/handlers/login.py`, `src/telegram_bot/handlers/ad_create.py`, `src/telegram_bot/handlers/contact.py`; advisory-lock discipline in `src/backend/apps/core/utils/advisory_lock.py`; sync-cache I/O in `src/telegram_bot/middlewares/update_id_dedup.py`.

### Runtime Verification

| R# | Check | Method | Result |
|----|-------|--------|--------|
| R-01 | Sweeps acquire transaction-scoped advisory locks | `grep -rn "advisory_lock" src/backend/apps/*/management/` | PASS — all 10+ production sweep commands verified |
| R-02 | `CONN_MAX_AGE=0` and `prepare_threshold: None` | `read src/backend/config/settings/base.py:191-193` | PASS — confirmed |
| R-03 | All ORM calls from bot async handlers wrapped in `sync_to_async` | `grep -rn "sync_to_async" src/telegram_bot/handlers/` | PASS — all ORM calls wrapped |
| R-04 | No bare sync cache calls in async context without `sync_to_async` | `grep -rn "check_upload_rate_limit\|check_contact_start_rate_limit\|cache\.add" src/telegram_bot/` | **FAIL** — 3 unguarded sync cache calls found |
| R-05 | `submit_ad` atomic scope includes `auto_moderate` | `read src/backend/apps/ads/services/submission.py:158-186` | **FAIL** — `auto_moderate` called outside `transaction.atomic()` |
| R-06 | Ban functions wrapped in `transaction.atomic()` | `read src/backend/apps/moderation/admin_actions.py:66-87,201-226` | **FAIL** — neither `ban_user_for_ad` nor `bulk_ban_users` use `transaction.atomic()` |
| R-07 | Login claim + user-create in single transaction | `read src/telegram_bot/handlers/login.py:184-192` | **FAIL** — two separate `transaction.atomic()` blocks |
| R-08 | Lint clean on all identified files | `ruff check` on 7 files | PASS |
| R-09 | Typecheck clean on all identified files | `basedpyright` on 7 files | PASS |
| R-10 | Structural lock tests pass | `docker compose ... run --rm -e PYTEST_OPTS="-k 'sweep_lock or admin_actions'" test` | PASS — 21 tests |

> PASS results prove thoroughness; FAIL results are findings below.

**Tools used:** `grep`, `read` (file inspection), `uv run ruff check`, `uv run basedpyright`, `docker compose --project-name mko-bazuna-test run --rm test`.

**Assumptions:** Production uses Redis-backed cache (network I/O); PostgreSQL 18; Django 5.2.16; bot runs under CPython; `submit_ad` bot path has no outer `transaction.atomic()` (confirmed in `ad_create.py:813`), while the web edit path does have an outer transaction (`edit.py:125`).

## Findings Summary

| ID | Title | Severity | Status | Category |
|----|-------|----------|--------|----------|
| DB-001 | `submit_ad` (bot path) commits ad + images before auto-moderation | CRITICAL | Open | Transaction atomicity |
| DB-002 | Sync Redis cache I/O blocks aiogram event loop in 3 async call sites | HIGH | Open | Async/sync bridge |
| DB-003 | `ban_user_for_ad` and `bulk_ban_users` write ban and audit log non-atomically | MEDIUM | Open | Transaction atomicity |
| DB-004 | Login handler splits token-claim and user-creation into two transactions | MEDIUM | Open | Cross-process consistency |

## Distribution

**Severity counts**

| CRITICAL | 1 |
|----------|---|
| HIGH | 1 |
| MEDIUM | 2 |
| LOW | 0 |

**Status counts**

| Status | Count |
|--------|-------|
| Open | 4 |

## Findings by Severity

### CRITICAL

#### DB-001: [CRITICAL] — `submit_ad` (bot path) commits ad + images before auto-moderation

| Field | Value |
|:---:|---|
| **ID** | DB-001 |
| **Title** | `submit_ad` (bot path) commits ad + images before auto-moderation |
| **Severity** | CRITICAL |
| **Category** | Transaction atomicity |
| **File(s)** | `src/backend/apps/ads/services/submission.py:158-186` |
| **Status** | Open |
| **Problem** | In the bot call path (`ad_create.py:813` calls `submit_ad` via `sync_to_async` with no enclosing `transaction.atomic()`), `submit_ad` commits the ad row, AdImage records, and `transition_to(ON_MODERATION)` at line 158-179 in one transaction, then calls `auto_moderate(ad)` at line 186 *outside* that transaction. `auto_moderate` internally opens its own `transaction.atomic()` in `_pass_moderation` (line 253) or `_fail_moderation` (line 236), creating a second, independent transaction with an intermediate commit. |
| **Impact** | If `auto_moderate` fails partway (e.g., `record_event` or `TrustCalculator().calculate_and_save` at line 268 raises), the ad is already committed in `ON_MODERATION` with images persisted, but the status transition to `PUBLISHED`/`ON_MODERATION_FAILED`, the `ModeratorActionLog`, and `AnalyticsEvent` records are lost. The ad is left in limbo — `ON_MODERATION` with no moderation outcome — requiring manual intervention. In the web edit path this is mitigated because `edit.py:125` wraps `submit_ad` in an outer `transaction.atomic()`, making `auto_moderate`'s inner block a SAVEPOINT. But the bot path has no such outer transaction. |
| **Root Cause** | `auto_moderate` is called after the `with transaction.atomic():` block closes (line 181-186), and `auto_moderate`'s internal `_pass_moderation`/`_fail_moderation` each open their own transaction rather than participating in the caller's transaction. |
| **Recommendation** | Move the `auto_moderate(ad)` call inside the `with transaction.atomic():` block in `submit_ad` (after `ad.transition_to(ON_MODERATION)`). Since `auto_moderation._pass_moderation`/`_fail_moderation` already use `transaction.atomic()`, they will become SAVEPOINTs nested in the outer transaction, ensuring the entire submission + moderation is a single unit of work. Verify the web edit path still works (the outer transaction in `edit.py` will create three levels of nesting, but Django handles SAVEPOINTs correctly). |
| **Effort** | S |
| **Priority** | P0 |

**Evidence — `submission.py:158-186`** *(supports: "auto_moderation called outside transaction.atomic block")*:
```python
# L157: comment — DB transaction: save + images + status transition
with transaction.atomic():  # L158
    ad.listing_condition_id = input.listing_condition_id
    ad.save()                                    # L160
    if input.feature_ids is not None:
        ad.features.set(input.feature_ids)       # L164
    for photo in input.photos:
        AdImageService.create_or_skip(...)       # L168-176
    ad.transition_to(AdStatus.ON_MODERATION)     # L179

# L181-186: auto_moderate called OUTSIDE the atomic block
from apps.moderation.services.auto_moderation import auto_moderate  # L184
passed = auto_moderate(ad)  # L186 — opens its OWN transaction in _pass_moderation/_fail_moderation
```

**Evidence — `ad_create.py:813`** *(supports: "bot path has no enclosing transaction.atomic")*:
```python
is_valid, errors = await sync_to_async(submit_ad)(  # no outer transaction.atomic()
    SubmitAdInput(...)
)
```

**Evidence — `edit.py:125`** *(supports: "web path IS wrapped, only bot path is vulnerable")*:
```python
with transaction.atomic():        # L125 — outer transaction
    ad = get_object_or_404(Ad.objects.select_for_update(), id=ad_id)  # L126
    ...
    passed, errors = submit_ad(SubmitAdInput(...))  # L178 — inside outer atomic
```

---

### HIGH

#### DB-002: [HIGH] — Sync Redis cache I/O blocks aiogram event loop in 3 async call sites

| Field | Value |
|:---:|---|
| **ID** | DB-002 |
| **Title** | Sync Redis cache I/O blocks aiogram event loop in 3 async call sites |
| **Severity** | HIGH |
| **Category** | Async/sync bridge |
| **File(s)** | `src/telegram_bot/handlers/ad_create.py:675`, `src/telegram_bot/handlers/contact.py:118`, `src/telegram_bot/middlewares/update_id_dedup.py:58` |
| **Status** | Open |
| **Problem** | Three synchronous cache operations are called directly from async context (bot handler / middleware `__call__`) without `sync_to_async` wrapping: (1) `check_upload_rate_limit(user_id)` at `ad_create.py:675` in an async handler; (2) `check_contact_start_rate_limit(message.from_user.id)` at `contact.py:118` in an async handler; (3) `cache.add(...)` at `update_id_dedup.py:58` in the async middleware `__call__`. In production, Django's cache backend is Redis (`django-redis`), so each call performs socket I/O to the Redis server. |
| **Impact** | Each cache call blocks the entire aiogram event loop — no other bot update (ad creation, moderation, login, or incoming message) can be processed during the Redis round-trip. Under burst load (e.g., many users uploading photos simultaneously), event-loop stalls compound, causing Telegram webhook timeouts and degraded/blocking bot responsiveness. The dedup middleware is particularly dangerous: it runs before every update and blocks all incoming traffic if Redis is slow. |
| **Root Cause** | `check_upload_rate_limit` and `check_contact_start_rate_limit` are defined as synchronous functions in `telegram_bot/services/rate_limit.py` using Django's sync `cache.add`/`cache.incr`/`cache.set` API. The bot handlers call them directly without wrapping in `sync_to_async`. The dedup middleware similarly calls `cache.add` directly in `async def __call__`. |
| **Recommendation** | Wrap all three cache calls in `sync_to_async`: (1) `await sync_to_async(check_upload_rate_limit)(user_id)` at `ad_create.py:675`; (2) `await sync_to_async(check_contact_start_rate_limit)(message.from_user.id)` at `contact.py:118`; (3) `added = await sync_to_async(cache.add)(...)` at `update_id_dedup.py:58`. Consider refactoring the rate-limit functions to `async def` using `django-asyncio` or `aioredis` directly for non-blocking I/O. |
| **Effort** | S |
| **Priority** | P0 |

**Evidence — `ad_create.py:673-677`** *(supports: "check_upload_rate_limit called synchronously in async handler without sync_to_async")*:
```python
    # Enforce per-seller upload burst limit (anti-abuse).
    user_id = data.get("user_id")
    if user_id is not None and not check_upload_rate_limit(user_id):  # L675 — sync call, no await + sync_to_async
        await message.answer("Uploading too fast, please wait a moment.")
        return
```

**Evidence — `contact.py:118`** *(supports: "check_contact_start_rate_limit called synchronously in async handler")*:
```python
    if not check_contact_start_rate_limit(message.from_user.id):  # L118 — sync call, no await + sync_to_async
        await message.answer(CONTACT_US_RATE_LIMITED_MESSAGE)
        return True
```

**Evidence — `update_id_dedup.py:57-58`** *(supports: "cache.add called synchronously in async middleware __call__")*:
```python
        try:
            added = cache.add(f"bot_update:{update_id}", 1, timeout=DEDUP_TTL_SECONDS)  # L58 — sync, no sync_to_async
        except (ConnectionInterrupted, redis.RedisError):
```

**Evidence — `rate_limit.py:52-56`** *(supports: "check_upload_rate_limit is a sync function using cache.add/cache.incr")*:
```python
    try:
        added = cache.add(key, 1, timeout=period)  # L52 — sync Redis I/O
        if added:
            current = 1
        else:
            current = cache.incr(key)  # L56 — sync Redis I/O
```

---

### MEDIUM

#### DB-003: [MEDIUM] — `ban_user_for_ad` and `bulk_ban_users` write ban and audit log non-atomically

| Field | Value |
|:---:|---|
| **ID** | DB-003 |
| **Title** | `ban_user_for_ad` and `bulk_ban_users` write ban and audit log non-atomically |
| **Severity** | MEDIUM |
| **Category** | Transaction atomicity |
| **File(s)** | `src/backend/apps/moderation/admin_actions.py:66-87`, `src/backend/apps/moderation/admin_actions.py:201-226` |
| **Status** | Open |
| **Problem** | `ban_user_for_ad` (line 66-87) calls `user.save(update_fields=["is_banned"])` at line 78 and then `log_ban_account(...)` at line 80-84 with no `transaction.atomic()` wrapper around the pair. `bulk_ban_users` (line 201-226) calls `log_ban_account(...)` in a loop at lines 218-222 and then `User.objects.filter(id__in=user_ids).update(is_banned=True)` at line 225, also without `transaction.atomic()`. |
| **Impact** | In `ban_user_for_ad`: if `log_ban_account` raises after `user.save()` commits, the user is banned but the audit log entry is lost — an irreproducible moderation action with no trace. In `bulk_ban_users`: if the `User.objects.filter().update()` at line 225 fails after the `log_ban_account` calls have already committed, audit logs exist for users who are not actually banned. Both functions are invoked from the synchronous web process but the `User` model is also touched by the bot (login flow), creating a cross-process consistency risk if a sweep or bot action reads a half-banned state. |
| **Root Cause** | Ban and audit-log writes are independent operations with no transactional demarcation. The sibling functions `approve_ad`, `reject_ad`, and `soft_delete_ad` correctly use `transaction.atomic()`, but `ban_user_for_ad` and `bulk_ban_users` were not aligned to the same pattern. |
| **Recommendation** | Wrap the `user.save()` + `log_ban_account()` pair in `ban_user_for_ad` with `with transaction.atomic():`. In `bulk_ban_users`, wrap the loop + final `User.objects.filter().update()` in `with transaction.atomic():`. Note: `test_bulk_ban_users_not_locked` (line 242) only asserts `select_for_update` is absent — it does not assert `transaction.atomic()` is absent, so this change is compatible with existing tests. |
| **Effort** | S |
| **Priority** | P1 |

**Evidence — `admin_actions.py:66-87`** *(supports: "ban_user_for_ad has no transaction.atomic around save + log")*:
```python
def ban_user_for_ad(ad: Ad, moderator_id: int, reason: str) -> None:
    user = ad.user
    if user and not user.is_banned:
        user.is_banned = True
        user.save(update_fields=["is_banned"])          # L78 — commits immediately
        log_ban_account(user_id=user.id, ...)           # L80-84 — separate implicit transaction
```

**Evidence — `admin_actions.py:201-226`** *(supports: "bulk_ban_users has no transaction.atomic around log calls + bulk update")*:
```python
    user_ids = set(queryset.values_list("user_id", flat=True))
    count = 0
    for user_id in user_ids:
        if user_id:
            log_ban_account(user_id=user_id, ...)      # L218-222 — N separate implicit transactions
            count += 1
    User.objects.filter(id__in=user_ids).update(is_banned=True)  # L225 — another implicit transaction
    return count                                                     # no transaction.atomic() anywhere
```

**Evidence — `admin_actions.py:242-245`** *(supports: "existing test only checks select_for_update is absent, not transaction.atomic")*:
```python
    def test_bulk_ban_users_not_locked() -> None:
        """bulk_ban_users must NOT gain select_for_update (out of DB-003 scope)."""
        src = inspect.getsource(bulk_ban_users)
        assert "select_for_update" not in src  # only checks select_for_update, not transaction.atomic
```

---

#### DB-004: [MEDIUM] — Login handler splits token-claim and user-creation into two transactions

| Field | Value |
|:---:|---|
| **ID** | DB-004 |
| **Title** | Login handler splits token-claim and user-creation into two transactions |
| **Severity** | MEDIUM |
| **Category** | Cross-process consistency |
| **File(s)** | `src/telegram_bot/handlers/login.py:184-192` |
| **Status** | Open |
| **Problem** | The `_handle` function (wrapped in `@sync_to_async` at line 177) opens `transaction.atomic()` at line 184 for `_claim_login_token` (an `UPDATE ... RETURNING` that consumes the token), commits that transaction at line 184's block close, then opens a *second* `transaction.atomic()` at line 192 for `User.objects.get_or_create`. |
| **Impact** | If `get_or_create` fails after the token has been claimed (e.g., concurrent insert race on `telegram_id` uniqueness constraint, or a transient DB error), the login token is permanently consumed — the user cannot complete login and must request a new token. The claim and creation should be a single atomic unit: either both succeed, or neither does. Login tokens are shared between bot and web (web middleware reads `User`), so a partially-consumed token creates cross-process inconsistency. |
| **Root Cause** | Two separate `transaction.atomic()` blocks were used instead of one, despite the function docstring at line 166 stating "Atomically claim a login token, then get or create the user." The `UPDATE ... RETURNING` claim is itself atomic (no TOCTOU), but the two-phase commit is not. |
| **Recommendation** | Merge the two `transaction.atomic()` blocks into one: wrap both `_claim_login_token` and `User.objects.get_or_create` in a single `with transaction.atomic():`. If `get_or_create` raises, the entire block rolls back, returning the token to an unclaimed state. Verify `_claim_login_token` (line 122) doesn't require its own savepoint semantics. |
| **Effort** | S |
| **Priority** | P1 |

**Evidence — `login.py:177-199`** *(supports: "two separate transaction.atomic blocks for claim and user-create")*:
```python
    @sync_to_async
    def _handle() -> tuple[LoginToken | None, User | None, bool]:
        now = timezone.now()
        with transaction.atomic():                      # L184 — FIRST transaction
            login_token = _claim_login_token(token_hash, telegram_id, now)  # L185
        if login_token is None:
            return None, None, False
        try:
            with transaction.atomic():                  # L192 — SECOND transaction (separate!)
                user, created = User.objects.get_or_create(...)  # L193-206
```

**Evidence — `login.py:166-172`** *(supports: "docstring claims atomicity but code is non-atomic")*:
```
Atomically claim a login token, then get or create the user.
Combines the claim and user operations in a single sync_to_async call
to reduce DB connection churn with CONN_MAX_AGE=0.
The claim uses UPDATE ... RETURNING to avoid a TOCTOU race between
the UPDATE and a subsequent SELECT.
```

## Cross-Finding Analysis

- **Merge candidates:** DB-001 and DB-003 both stem from transaction-scope-too-narrow patterns. They address different code paths (ad submission vs. user banning) and have different severities, so they remain separate findings.
- **Conflicting evidence:** None.
- **Dependency chains:** None. DB-002 (sync cache I/O) is structurally independent of the transaction findings. Fixing DB-001 first is recommended before addressing DB-003/DB-004 since `submit_ad` calls `auto_moderation` which calls `_pass_moderation` (which could call `ban_user_for_ad`) — but no current code path chain exists from `ban_user_for_ad` through `auto_moderate`.

## Remediation Roadmap

| Order | ID | Severity | Effort | Priority | Recommendation (summary) |
|-------|----|----------|--------|----------|--------------------------|
| 1 | DB-001 | CRITICAL | S | P0 | Move `auto_moderate(ad)` call inside `submit_ad`'s `transaction.atomic()` block |
| 2 | DB-002 | HIGH | S | P0 | Wrap 3 sync cache calls in `sync_to_async` |
| 3 | DB-003 | MEDIUM | S | P1 | Wrap ban + log_ban_account in `transaction.atomic()` for both functions |
| 4 | DB-004 | MEDIUM | S | P1 | Merge two `transaction.atomic()` blocks in login handler into one |

## Rollout Safety

| ID | Risk | Backward-compatible? | Test gap (must cover) |
|----|------|----------------------|-----------------------|
| DB-001 | High | Yes | No test asserts `auto_moderate` runs within `submit_ad`'s transaction boundary; add a test that fails `auto_moderate` mid-execution and asserts the ad is NOT committed |
| DB-002 | Low | Yes | No test exercises sync cache calls from async context; add a test that detects blocking cache I/O in async handlers (e.g., mock cache backend to record thread-blocking) |
| DB-003 | Low | Yes | `test_bulk_ban_users_not_locked` only asserts `select_for_update` absence; add assertion that `transaction.atomic` is present |
| DB-004 | Low | Yes | No test simulates `get_or_create` failure after token claim; add test that patches `get_or_create` to raise and asserts token is unclaimed |

## Appendices

### Appendix A — `ad_create.py:805-820` (bot path calls `submit_ad` without outer transaction)

```python
        # L808-812
        if not is_valid:
            ...
        is_valid, errors = await sync_to_async(submit_ad)(
            SubmitAdInput(
                ad_id=ad.id,
                photos=photos_final,
                ...
            )
        )
        if not is_valid:
            ...
```

*(supports the claim: "bot path at ad_create.py:813 calls submit_ad via sync_to_async with no enclosing transaction.atomic()")*

### Appendix B — Structural test results

```text
$ docker compose ... run --rm -e PYTEST_OPTS="-k 'sweep_lock or admin_actions'" test
4 passed, 1474 deselected in 30.60s  (sweep_lock)
17 passed, 1461 deselected in 30.47s  (admin_actions)
1 passed, 1477 deselected in 31.37s  (transition_concurrency)
```

*(supports: "all existing structural/concurrency tests pass — findings are not covered by current tests")*
