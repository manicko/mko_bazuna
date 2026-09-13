# Validated Audit Findings — Authentication & Login Token Security

**Phase:** 04 — Authentication & Login Token Security
**Date:** 2026-09-12
**Auditor:** Executor (subagent)
**Validator:** Kilo (read-validation agent)
**Mode:** problems-only · validated: yes

---

## Validator's Notes

This validation was performed by reading the actual source code at every line number and file referenced in the findings, cross-referencing with the project specification, and verifying the claim chain end-to-end. Key methodology:

1. **Code verification** — Every file and line referenced in the findings was read and confirmed against the actual source.
2. **Spec cross-reference** — The Phase 04 audit instructions (`04-audit-auth-login.md`), the technical specification (`technical-specification.md` zone H), and `db-schema.md` were checked for explicit requirements.
3. **Test verification** — Grep was used to confirm the absence of any concurrent-claim test across all test files.
4. **Architecture verification** — Middleware registration patterns were compared (`dp.message.middleware` vs `dp.update.middleware`) against the aiogram 3.x middleware contract.

Two findings were **validated** (reclassified from the original severity-only taxonomy to the validation type taxonomy). One **new finding** (AUT-003) was discovered during validation that the original audit did not surface — a non-functional middleware that compounds the AUT-001 problem.

---

## Findings by Severity

### MEDIUM

#### AUT-001: [MEDIUM] — Bot FSM auth state lost on restart; not restored from shared ORM

| Field | Value |
|:---:|---|
| **ID** | AUT-001 |
| **Title** | Bot FSM auth state lost on restart; not restored from shared ORM |
| **Severity** | MEDIUM |
| **Category** | Availability / Reliability |
| **File(s)** | `src/telegram_bot/main.py:49`; `src/telegram_bot/handlers/login.py:109`; `src/telegram_bot/handlers/ad_create.py:86`; `src/telegram_bot/handlers/ad_copy.py:34`; `src/telegram_bot/handlers/alerts.py:47`; `src/telegram_bot/handlers/language.py:38,68` |
| **Status** | Open |

> **Validation Note:**
> - **Action:** reclassified
> - **Detail:** The finding is technically correct in its core claims but the root-cause analysis is incomplete. The spec (technical-specification.md, zone H, line 147) states: "FSM auth completeness — authentication must complete (or safely abort) and persist through bot restart via the shared ORM." The implementation fails this requirement. However, the root-cause analysis claims the `AccountStateMiddleware` "performs a DB lookup by `chat_id` on every message" — this is **not true** (see new finding AUT-003). The middleware's `__call__` short-circuits before any DB lookup because it checks `isinstance(event, Update)` while being registered on `dp.message` (which passes `Message` events). The `_get_user` method exists at permissions.py:177 but is never invoked through the middleware pipeline. The recommendation (Option B: middleware backfill) would work once the isinstance bug is fixed. Type changed from severity-only to SPEC-DEVIATION because the spec explicitly requires auth-state persistence through bot restart.
> - **See also:** AUT-003 (middleware isinstance bug), Phase 03 DB-004 (login handler split-transaction)

**Problem** *(validated — code state confirmed as of 2026-09-12)*: The bot uses `MemoryStorage()` for FSM (main.py:49). On login, `state.update_data(user_id=user.id)` (login.py:109) stores the authenticated user's DB primary key in ephemeral in-memory FSM state. Four bot handlers gate authentication on this FSM key without any DB fallback: `/post` (ad_create.py:86: `if "user_id" not in data`), `/copy` (ad_copy.py:33-34: `user_id = data.get("user_id")` / `if not user_id:`), `/alerts` (alerts.py:46-49), `/language` (language.py:36-38 and 65-67). None of these handlers query the `User` table by stable `chat_id` to recover auth state. When the bot process restarts, `MemoryStorage` is wiped — ALL FSM state is lost.

**Impact** *(validated)*: After any bot restart (deployment, crash, OOM), every previously-authenticated user is treated as unauthenticated. Users tapping `/post` receive "Please login first" and must re-issue a login token. The `LoginToken` claim and `User` record persist in the shared Django ORM, but the bot cannot recover the authentication reference. This creates recurring availability degradation across all restarts.

**Root Cause** *(partially corrected — see Validation Note above)*: Bot FSM uses aiogram's `MemoryStorage` (documented as ephemeral in main.py:44-48). The `AccountStateMiddleware` was designed to look up users by `chat_id` on every message but is non-functional (see AUT-003). Handler-level auth checks read FSM state exclusively with no DB fallback.

**Spec requirement:** Technical Specification, zone H (login behavior, "Cross-Cutting Concerns"): "FSM auth completeness — authentication must complete (or safely abort) and persist through bot restart via the shared ORM." (technical-specification.md line 147)

**Recommendation** *(validated — sound, aligned with project patterns)*: Two options: (A) Switch FSM storage to `RedisStorage`; (B) Fix `AccountStateMiddleware` (see AUT-003) and add backfill of `user_id` into FSM state from the ORM on each message via `chat_id` lookup. Option (B) is recommended as it works with `MemoryStorage` and adds resilience.

**Effort** | M
**Priority** | P1
**CWE** | CWE-613 (Insufficient Session Expiration)
**Likelihood** | MEDIUM

**Evidence — verified on disk (2026-09-12):**

`src/telegram_bot/main.py:44-50` — MemoryStorage confirmed:

```python
# Storage: MemoryStorage (FSM state in memory, Ad.DRAFT in ORM)
# NOTE: MemoryStorage is ephemeral — FSM state is cleared on bot restart.
# There is no cross-process broadcast: if the bot is restarted while a user
# is mid-FSM, the in-progress dialog is lost. The Ad.DRAFT row in the ORM
# survives, but the FSM state machine state does not.
# Future: switch to RedisStorage for persistent FSM across restarts.
storage = MemoryStorage()  # line 49 — confirmed
dp = Dispatcher(storage=storage)
```

`src/telegram_bot/handlers/login.py:109` — `user_id` written to FSM:

```python
await state.update_data(user_id=user.id)  # line 109 — confirmed
```

`src/telegram_bot/handlers/ad_create.py:84-89` — FSM-only auth gate:

```python
data = await state.get_data()
if "user_id" not in data:
    await message.answer("Please login first with /start login_<token>")
    return
```

`src/telegram_bot/handlers/ad_copy.py:32-36` — FSM-only auth gate:

```python
data = await state.get_data()
user_id = data.get("user_id")
if not user_id:
    await message.answer("Please login first with /start login_<token>")
    return
```

`src/telegram_bot/handlers/alerts.py:46-51` — FSM-only auth gate:

```python
data = await state.get_data()
user_id = data.get("user_id")
if not user_id:
    await message.answer("Please login first with /start login_<token>")
    return
```

`src/telegram_bot/handlers/language.py:36-40 and 65-69` — FSM-only auth gate (two endpoints: message + callback_query):

```python
# cmd_language (line 36-38):
data = await state.get_data()
user_id = data.get("user_id")
if not user_id:
    await message.answer(_("Please login first with /start login_<token>"))

# handle_language_callback (line 65-67):
data = await state.get_data()
user_id = data.get("user_id")
if not user_id:
    await callback.answer(_("Please login first."), show_alert=True)
```

`src/telegram_bot/middlewares/permissions.py:176-193` — `_get_user` exists but middleware `__call__` is non-functional (see AUT-003):

```python
# permissions.py:60 — this short-circuits for ALL Message events:
if not isinstance(event, Update):
    return await handler(event, data)

# permissions.py:176-193 — _get_user is defined but never reached via __call__:
@sync_to_async
def _get_user(self, chat_id: int) -> User:
    return User.objects.get(chat_id=chat_id)
```

`src/telegram_bot/main.py:53` — middleware registered on `dp.message` (not `dp.update`):

```python
dp.message.middleware(AccountStateMiddleware())
```

**Minor line-number discrepancy:** The finding references `language.py:38,68`. Line 38 is correct (`if not user_id:`), but line 68 is `await callback.answer(...)` — the actual auth check is at line 67. This off-by-one in the source does not affect finding validity.

---

#### AUT-003: [MEDIUM] — NEW FINDING — `AccountStateMiddleware` is non-functional: `isinstance(event, Update)` short-circuits all message events

| Field | Value |
|:---:|---|
| **ID** | AUT-003 |
| **Title** | `AccountStateMiddleware.__call__` checks `isinstance(event, Update)` but is registered on `dp.message`, receiving `Message` objects — middleware is a no-op |
| **Severity** | MEDIUM |
| **Category** | Correctness / Security |
| **File(s)** | `src/telegram_bot/middlewares/permissions.py:60`; `src/telegram_bot/main.py:53`; `src/telegram_bot/tests/conftest.py:64` |
| **Status** | Open |

**Problem:** `AccountStateMiddleware` is registered via `dp.message.middleware(AccountStateMiddleware())` (`main.py:53`). In aiogram 3.x, `dp.message.middleware()` dispatches `Message` events to the middleware's `__call__` — the `event` parameter is a `Message`, not an `Update`. The middleware checks `isinstance(event, Update)` at `permissions.py:60`:

```python
if not isinstance(event, Update):
    return await handler(event, data)
```

Since `Message` is NOT a subclass of `Update` (they are sibling subclasses of `TelegramObject`), `isinstance(event, Update)` is always `False`, `not isinstance(event, Update)` is always `True`, and the middleware always short-circuits to `return await handler(event, data)` — bypassing ALL account-state checks and ALL DB lookups (including `_get_user` at line 177).

The middleware's design (lines 64-72) accesses `event.message` and `event.callback_query`, which are `Update`-only attributes — confirming the code was written for `Update` events but was registered on the wrong dispatch level.

Compare with `UpdateIdDedupMiddleware` (`update_id_dedup.py:41-42`), which is registered on `dp.update.middleware()` and whose docstring explicitly states: "the event is always an `aiogram.types.Update` (verified at runtime)." This is the correct pattern for `Update`-type middleware.

**Impact:** Three critical consequences:
1. Banned, deleted, declined, and consent-withdrawn users are NOT blocked — the middleware's four account-state flags (`is_banned`, `is_deleted`, `is_declined`, `consent_revoked`) are never enforced for message events.
2. The `/post` publish restriction (`ads_auto_publish=False`) is never enforced.
3. The proposed fix for AUT-001 (middleware backfill of `user_id` from `chat_id` lookup) would not work even if implemented, because the middleware never runs.

**Root Cause:** Registration-level mismatch — the middleware was written for `Update`-level dispatch (`isinstance(event, Update)`, `event.message`, `event.callback_query`) but was attached to `dp.message` instead of `dp.update`.

**Recommendation:** Move registration from `dp.message.middleware(...)` to `dp.update.middleware(...)` in both `main.py:53` and `tests/conftest.py:64`. This causes the middleware to receive `Update` events, making the `isinstance(event, Update)` check pass and the account-state + backfill logic functional. The callback_query handling at lines 64-72 would then also work as intended.

**Effort** | S
**Priority** | P0 (security: banned/deleted users are not blocked)
**CWE** | CWE-862 (Missing Authorization) — account-state authorization check never executes

**Evidence — verified on disk (2026-09-12):**

Registration mismatch — `main.py:49-53`:

```python
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
dp.message.middleware(AccountStateMiddleware())  # ← registered on dp.message
```

The isinstance short-circuit — `permissions.py:59-61`:

```python
# Only process Update events
if not isinstance(event, Update):
    return await handler(event, data)
```

The middleware accesses `Update`-only attributes — `permissions.py:64-72`:

```python
message: Message | None = event.message       # Update.message — not on Message
if (
    event.callback_query is not None          # Update.callback_query — not on Message
    and event.callback_query.message is not None
):
    ...
```

Correct pattern (contrast) — `update_id_dedup.py:41-42`:

```python
Registered as an update-level middleware via ``dp.update.middleware(...)``,
the event is always an ``aiogram.types.Update`` (verified at runtime)
```

Test gap — `test_account_state_middleware.py`: All 8 tests call `middleware._check_user_state(chat_id)` or `middleware._check_publish_permission(chat_id)` directly. No test exercises `middleware.__call__()` through the aiogram `dp`/`Dispatcher` pipeline. There is zero coverage of the `isinstance(event, Update)` gate or the `event.message`/`event.callback_query` extraction.

---

### LOW

#### AUT-002: [LOW] — No permanent concurrent double-claim race test (R3 gap)

| Field | Value |
|:---:|---|
| **ID** | AUT-002 |
| **Title** | No permanent concurrent double-claim race test in test suite |
| **Severity** | LOW |
| **Category** | Test Quality |
| **File(s)** | `src/telegram_bot/tests/test_login.py:134` (test_reclaim_blocked — sequential only); `src/backend/apps/users/tests/test_login.py` (no concurrent test) |
| **Status** | Open |

> **Validation Note:**
> - **Action:** reclassified
> - **Detail:** The finding is technically correct but its classification as severity-only "LOW" understates the spec requirement. The Phase 04 audit instructions (line 171) explicitly state in the "Isolation / Test Note": "Simulate the concurrent claim race." This is a mandatory test requirement from the spec, not optional best-practice. The finding is reclassified as SPEC-DEVIATION (missing required test) rather than a mere best-practice improvement. All evidence claims were verified on disk.
> - **See also:** Phase 03 DB-004 (different test gap: `get_or_create` failure after claim — not the same concern)

**Problem** *(validated — code state confirmed as of 2026-09-12)*: The bot's `test_reclaim_blocked` (`test_login.py:134-172`) tests sequential double-claim only — it calls `handle_login_orm` twice in sequence (await call 1, then await call 2) and asserts the second returns `None`. No `asyncio.gather` or `threading.Thread` is used. The Phase 04 R3 verification requires concurrent double-claim (two identities claiming the same token simultaneously). No permanent test exercises true concurrency. The spec's "Isolation / Test Note" (Phase 04 instructions, line 171) explicitly states: "Simulate the concurrent claim race."

**Impact** *(validated)*: If a future refactor weakens the atomic `UPDATE ... RETURNING` claim (e.g., switching to a `get()` + `save()` pattern), the race-proof property would silently break without test failure. The existing sequential test would still pass. This masks a regression that could enable double-claim / account-takeover.

**Root Cause** *(validated)*: The `test_reclaim_blocked` test verifies idempotency under sequential execution but does not fire two claims concurrently. The `pytest.mark.concurrent` marker (`pyproject.toml:170`) only means `transaction=True` (TRUNCATE per test), NOT concurrent execution within a test. No `asyncio.gather` or `threading.Thread` concurrency test for double-claim exists anywhere in the codebase.

**Spec requirement:** Phase 04 audit instructions, "Isolation / Test Note" (line 171): "Simulate the concurrent claim race."

**Recommendation** *(validated)*: Add a permanent test using `asyncio.gather` to fire two `handle_login_orm` calls with the same `token_hash` but different `telegram_id` values concurrently, asserting exactly one returns a non-`None` `LoginToken`.

**Effort** | S
**Priority** | P2
**CWE** | CWE-754 (Improper Check for Unusual or Exceptional Conditions)
**Likelihood** | LOW

**Evidence — verified on disk (2026-09-12):**

`src/telegram_bot/tests/test_login.py:134-172` — sequential test confirmed (no concurrency):

```python
async def test_reclaim_blocked(
    self,
    login_token_factory: Callable[..., Awaitable[tuple[str, Any]]],
) -> None:
    # Act: first claim succeeds
    first_claim, _, _ = await handle_login_orm(...)  # sequential — await first
    assert first_claim is not None, "First claim should succeed"

    # Act: second claim of the same hash by a different user
    second_claim, _, _ = await handle_login_orm(...)  # sequential — await second

    # Assert
    assert second_claim is None, "Re-claim of a claimed token must be blocked"
```

The `pytest.mark.concurrent` marker is defined at `pyproject.toml:170`:

```toml
"concurrent: marks tests requiring transaction=True (TRUNCATE per test)",
```

This confirms the `concurrent` marker means TRUNCATE-isolation, NOT concurrent execution within a test.

Codebase-wide grep confirms: No `asyncio.gather` or `threading.Thread` usage in any login-related test file. The only `asyncio.gather` usages in the codebase are in `ad_create.py:1065` (translation) and `immediate_alerts.py:239` (alert delivery) — neither related to login claims. The only `threading.Thread` usages are in `test_edit_views_locking.py:152` and `test_transition_concurrency.py:88` — both test ad lifecycle locking, not login token claims.

The temporary test `test_concurrent_claim_tmp.py` (referenced in the finding) was confirmed deleted — no file matching `*concurrent*` exists in any `tests/` directory.

---

## Cross-Finding Analysis

### Same root cause → merge candidates

None originally, but one was introduced during validation:

- **AUT-001 ↔ AUT-003 (new):** While these are distinct bugs (FSM persistence gap vs. middleware no-op), they share a remediation path. AUT-001's recommended Option B (middleware backfills `user_id` from DB) is blocked until AUT-003 is fixed. The middleware must be moved to `dp.update` before it can perform the `chat_id` → `user_id` backfill. They should be addressed together: fix AUT-003 first (P0), then implement the backfill (AUT-001, P1).

- **AUT-001 ↔ Phase 03 DB-004:** DB-004 ("Login handler splits token-claim and user-creation into two transactions") addresses the transaction scope in the same file (`login.py:184-192`). DB-004 is about atomicity of claim + user creation; AUT-001 is about FSM auth state persistence. Different root causes, same file. Fixing DB-004 (merging the two `transaction.atomic()` blocks) would strengthen the claim path but doesn't address AUT-001 or AUT-003. No merge — but coordination recommended since both touch `login.py`.

- **AUT-002 ↔ Phase 03 DB-004:** AUT-002 is about the missing concurrent double-claim test; DB-004's rollout note mentions a different test gap ("No test simulates `get_or_create` failure after token claim"). These are complementary test gaps, not duplicates.

### Conflicting evidence

None. All findings are mutually consistent.

**Cross-phase consistency:** Phase 03 (DB-004) confirms the claim uses `UPDATE ... RETURNING` (atomic for the claim step itself). AUT-002's temporary concurrent test passed (1 winner). These are consistent: the claim is atomic, but the permanent test is missing. No conflict.

### Dependency chains

1. **AUT-003 → AUT-001 (Option B):** The middleware backfill fix for AUT-001 depends on AUT-003 being fixed first. Without fixing the `isinstance` bug, the middleware never runs and can never backfill.
2. **AUT-001 is independent of AUT-002:** Test additions don't depend on production code changes.
3. **Phase 03 DB-004 ↔ AUT-002:** If DB-004 (merge transactions) is implemented, the concurrent double-claim test (AUT-002) should still pass — the single `UPDATE ... RETURNING` claim remains atomic. The test should be added regardless of DB-004's status.

---

## Rollout Safety

| ID | Risk | Backward-compatible? | Test gap (must cover) |
|----|------|----------------------|-----------------------|
| AUT-001 | Low | Yes (auth check becomes more permissive post-restart, never less) | Test: restart bot mid-session, verify `/post` works without re-login |
| AUT-002 | Low | Yes (adds test, no prod change) | N/A |
| AUT-003 | **High** (security: banned/deleted users unblocked) | Requires careful testing — moving middleware from `dp.message` to `dp.update` changes the event type from `Message` to `Update`. Must verify all handlers still receive proper account-state enforcement. | Test: send `Message` and `CallbackQuery` updates through the full `dp` pipeline and verify banned/declined users are blocked |

### Rollout ordering

1. **AUT-003 (P0, security):** Fix the `isinstance` bug FIRST. Move `AccountStateMiddleware` registration from `dp.message` to `dp.update` in both `main.py` and `tests/conftest.py`. Add integration tests that exercise `__call__` through the `dp` pipeline (not just `_check_user_state` directly).
2. **AUT-001 (P1):** After AUT-003 is fixed, implement the `user_id` backfill in `AccountStateMiddleware.__call__` (access `data` to backfill FSM state, or use `data["state"]` to call `state.update_data(user_id=user.id)`).
3. **AUT-002 (P2):** Add the permanent concurrent double-claim test at any time (no dependency on production changes).

### Circular dependency check

None. AUT-003 is a prerequisite for AUT-001's Option B, not a circular dependency. AUT-002 is independent.

---

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 0 | — |
| Reclassified | 2 | AUT-001 (severity → SPEC-DEVIATION), AUT-002 (severity → SPEC-DEVIATION) |
| Merged | 0 | — |
| Rejected | 0 | — |
| New findings (from validation) | 1 | AUT-003 — `AccountStateMiddleware` isinstance bug |

### Reclassified Findings

| ID | Original Type | New Type | Rationale |
|----|---------------|----------|-----------|
| AUT-001 | Severity-only (MEDIUM) | SPEC-DEVIATION | Spec explicitly requires auth state to "persist through bot restart via the shared ORM" (technical-specification.md H). Implementation does not. |
| AUT-002 | Severity-only (LOW) | SPEC-DEVIATION | Spec "Isolation / Test Note" explicitly requires "Simulate the concurrent claim race" (Phase 04 instructions, line 171). No permanent test exists. |

### Rejected Findings

_None._

### Merged Findings

_None._ (AUT-001 and AUT-003 were kept separate — distinct root causes, distinct fixes — but a dependency chain exists: AUT-001's Option B requires AUT-003 to be fixed first.)

### New Findings (Discovered During Validation)

| ID | Severity | Type | Title |
|----|----------|------|-------|
| AUT-003 | MEDIUM | SPEC-DEVIATION | `AccountStateMiddleware` registered on `dp.message` but checks `isinstance(event, Update)` — middleware is a no-op (banned/deleted users never blocked) |

### Warnings

1. **Architectural risk — untested middleware:** The `AccountStateMiddleware.__call__` method has zero pipeline-level test coverage. All tests for this middleware (`test_account_state_middleware.py:64-238`) call `_check_user_state` or `_check_publish_permission` directly, bypassing the `isinstance` check entirely. This allowed a critical authorization bug to ship undetected. Any middleware registration change (AUT-003 fix) MUST be covered by integration tests that send `Update` events through the full `dp` pipeline.

2. **Maintainability risk — root cause inaccuracy in original finding:** The original AUT-001 root-cause analysis claims the middleware "performs a DB lookup by chat_id on every message." This is incorrect — the middleware never runs. The validation has corrected this, but any implementation work referencing the original finding's root cause must use the corrected analysis (AUT-003).

3. **Rollout risk — AUT-003 fix changes middleware dispatch level:** Moving `AccountStateMiddleware` from `dp.message` to `dp.update` changes the event type from `Message` to `Update`. The middleware code at permissions.py:64-72 accesses `event.message` and `event.callback_query`, which are valid `Update` attributes. However, the callback_query handling must be tested end-to-end — the research doc (alert-unsubscribe-research.md:74-76) claims "callback-query events ARE subject to account-state checks via this middleware," which is currently false. After the fix, callback_query events WILL be subject to the checks — verifying this doesn't break existing callback handlers (e.g., `/alerts`, `/language`, ad-creation step callbacks) is required.

4. **Spec gap — bot auth persistence not in main spec:** The spec-index.md describes the login token mechanism in zone H but the "persist through bot restart via the shared ORM" requirement appears only in the Phase 04 audit instructions (line 147), not in the main `technical-specification.md`. The technical specification's zone H (login behavior) describes the token claim and web session but does NOT mention bot-side auth state persistence. This spec gap should be noted for spec maintainers.

5. **Dependency risk — Phase 03 DB-004:** The login handler (`login.py:184-192`) uses two separate `transaction.atomic()` blocks for claim + user creation (Phase 03 DB-004). If a future refactor merges these into one transaction while implementing AUT-001/AUT-003 fixes, the concurrent double-claim test (AUT-002) should still pass — but the test should be added BEFORE any such refactor to catch regressions.
