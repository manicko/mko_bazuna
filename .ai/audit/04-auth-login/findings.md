---
phase: "04"
phase_name: "Authentication & Login Token Security"
date: "2026-09-12"
auditor: "Executor (subagent)"
mode: "problems-only"
id_prefix: "AUT"
report_status: "draft"
severity_taxonomy: ".kilo/commands/audit/phases/04-audit-auth-login.md#severity-taxonomy"
---

# Audit Findings — Authentication & Login Token Security

## Executive Summary

Two deviations found in the login-token auth mechanism. One MEDIUM (bot FSM authentication state is ephemeral and lost on restart, violating the spec's persistence requirement) and one LOW (test suite lacks a permanent concurrent double-claim race test). The core token mechanism — hash-only storage, constant-time comparison, atomic two-phase claim, expiry enforcement, 192-bit CSPRNG entropy, rate limiting, secure cookies, and session-fixation prevention — is sound with no CRITICAL or HIGH findings.

## Scope & Methodology

**Scope:** The login-token auth mechanism spanning `src/backend/apps/users/views/consent.py` (token issuance + web consumption), `src/telegram_bot/handlers/login.py` (bot claim), `src/backend/apps/users/models.py` (LoginToken schema), `src/backend/apps/core/services/{contact,login}_rate_limit.py` (rate limiting), `src/telegram_bot/main.py` (FSM storage config), all bot handlers that gate on FSM `user_id` (`ad_create.py`, `ad_copy.py`, `alerts.py`, `language.py`), and the `cleanup_login_tokens` management command + scheduler wiring.

### Runtime Verification

| R# | Check | Method | Result |
|----|-------|--------|--------|
| R-01 | Raw token never stored/logged | `grep -rn "raw_token" src/backend/apps/users/views/consent.py`; `grep -rn "logger.*token" src/` | PASS |
| R-02 | Invalid/expired/consumed rejection | `pytest -k "login_status" --tb=short -v` | PASS (9 tests) |
| R-03 | Concurrent double-claim race | Temporary `asyncio.gather` concurrent claim test (2 users, same token) | PASS (1 winner confirmed) |
| R-04 | No `==` on secrets / constant-time used | `grep -rn '==.*token\|==.*hash\|==.*secret' src/backend/apps/users/ src/telegram_bot/handlers/login.py`; `grep -rn "compare_digest" src/` | PASS |
| R-05 | Token-leak scan (logs/URLs/errors) | `grep -rn "logger.*raw_token\|logger.*token" src/backend/apps/users/ src/telegram_bot/handlers/` | PASS |
| R-06 | Lint + typecheck + auth test-suite | `ruff check`, `basedpyright`, `pytest -k login` | PASS (60 tests, 0 lint, 0 typecheck errors) |

**Tools used:** `ruff` (lint), `basedpyright` (typecheck), `grep` (R4/R5 scans), `docker compose run --rm test` (pytest), code trace of claim/consumption/validation entrypoints.

**Assumptions:** Production uses Redis-backed cache (django-redis) for shared rate-limit counters. PostgreSQL 18 with READ COMMITTED isolation. Django 5.2.16. Bot runs CPython with aiogram 3.x. Two containers share the same host clock (NTP).

## Findings Summary

| ID | Title | Severity | Status | Category |
|----|-------|----------|--------|----------|
| AUT-001 | Bot FSM auth state lost on restart — not restored from shared ORM | MEDIUM | Open | Availability / Reliability |
| AUT-002 | No permanent concurrent double-claim race test (R3) | LOW | Open | Test Quality |

## Distribution

**Severity counts**

| MEDIUM | 1 |
| LOW | 1 |

**Status counts**

| Status | Count |
|--------|-------|
| Open | 2 |

## Findings by Severity

### MEDIUM

#### AUT-001: [MEDIUM] — Bot FSM auth state lost on restart; not restored from shared ORM

| Field | Value |
|---|---|
| **ID** | AUT-001 |
| **Title** | Bot FSM auth state lost on restart; not restored from shared ORM |
| **Severity** | MEDIUM |
| **Category** | Availability / Reliability |
| **File(s)** | `src/telegram_bot/main.py:49`; `src/telegram_bot/handlers/login.py:109`; `src/telegram_bot/handlers/ad_create.py:86`; `src/telegram_bot/handlers/ad_copy.py:34`; `src/telegram_bot/handlers/alerts.py:47`; `src/telegram_bot/handlers/language.py:38,68` |
| **Status** | Open |
| **Problem** | The bot uses `MemoryStorage()` for FSM (main.py:49). On login, `state.update_data(user_id=user.id)` (login.py:109) stores the authenticated user's ID in ephemeral in-memory FSM state. Four bot handlers gate authentication on this FSM key (`"user_id" not in data`): `/post` (ad_create.py:86), `/copy` (ad_copy.py:34), `/alerts` (alerts.py:47), `/language` (language.py:38). None of these handlers fall back to a DB lookup via `chat_id`. When the bot process restarts, ALL FSM state is wiped. |
| **Impact** | After any bot restart, every previously-authenticated user is treated as unauthenticated by the bot. Users tapping `/post` receive "Please login first" and must re-issue a login token and re-open the Telegram deep-link. The LoginToken claim and User record persist in the shared Django ORM, but the bot cannot recover the authentication reference from them. This creates a recurring availability degradation: every deployment, crash, or OOM restart logs out all active bot users. |
| **Root Cause** | Bot FSM uses aiogram's `MemoryStorage` (documented as ephemeral in main.py:44-48: "MemoryStorage is ephemeral — FSM state is cleared on bot restart. Future: switch to RedisStorage"). The `AccountStateMiddleware` already performs a DB lookup by `chat_id` on every message (permissions.py:177) but never backfills `user_id` into FSM state. Handler-level auth checks read FSM state exclusively instead of querying the ORM. |
| **Recommendation** | Two options: (A) Switch FSM storage to `RedisStorage` so state survives restarts (matches the code's own "Future" note). (B) Add a bot middleware that, after `AccountStateMiddleware` confirms the user exists in the DB (by stable `chat_id`), backfills `user_id` into FSM state from the ORM on each message — this makes the FSM state recoverable without changing the storage backend. Option (B) is recommended as it works with `MemoryStorage` and adds resilience against partial state loss. |
| **Effort** | M |
| **Priority** | P1 |
| **CWE** | CWE-613 (Insufficient Session Expiration) — auth state not persisted across process restart |
| **Likelihood** | MEDIUM |

**Evidence — `src/telegram_bot/main.py:49`** *(supports: "Bot uses MemoryStorage for FSM")*:
```python
storage = MemoryStorage()  # pyright: ignore[reportUnknownVariableType]
# NOTE: MemoryStorage is ephemeral — FSM state is cleared on bot restart.
# There is no cross-process broadcast: if the bot is restarted while a user
# is mid-FSM, the in-progress dialog is lost. The Ad.DRAFT row in the ORM
# survives, but the FSM state machine state does not.
# Future: switch to RedisStorage for persistent FSM across restarts.
```

**Evidence — `src/telegram_bot/handlers/login.py:109`** *(supports: "user_id auth state written to ephemeral FSM")*:
```python
await state.update_data(user_id=user.id)
```

**Evidence — `src/telegram_bot/handlers/ad_create.py:86`** *(supports: "handlers gate auth on FSM state, not DB")*:
```python
data = await state.get_data()
if "user_id" not in data:
    await message.answer("Please login first with /start login_<token>")
    return
```

**Evidence — `src/telegram_bot/middlewares/permissions.py:177`** *(supports: "middleware already does DB lookup by chat_id but doesn't backfill FSM")*:
```python
@sync_to_async
def _get_user(self, chat_id: int) -> User:
    return User.objects.get(chat_id=chat_id)
```

**Evidence — Runtime test (60 auth tests pass)** *(supports: "existing tests pass with current MemoryStorage; restart persistence is NOT tested")*:
```
src/telegram_bot/tests/test_login.py ......
src/backend/apps/users/tests/test_login.py ........................
================= 60 passed, 1418 deselected, 31 warnings in 43.79s ===============
```

---

### LOW

#### AUT-002: [LOW] — No permanent concurrent double-claim race test (R3 gap)

| Field | Value |
|---|---|
| **ID** | AUT-002 |
| **Title** | No permanent concurrent double-claim race test in test suite |
| **Severity** | LOW |
| **Category** | Test Quality |
| **File(s)** | `src/telegram_bot/tests/test_login.py:134` (test_reclaim_blocked — sequential only); `src/backend/apps/users/tests/test_login.py` (no concurrent test) |
| **Status** | Open |
| **Problem** | The bot's `test_reclaim_blocked` (test_login.py:134) tests sequential double-claim only — it calls `handle_login_orm` twice in sequence and asserts the second returns `None`. The phase R3 verification requires concurrent double-claim (two identities claiming the same token simultaneously). No permanent test exercises true concurrency. The spec's "Isolation / Test Note" explicitly states: "Simulate the concurrent claim race." |
| **Impact** | If a future refactor weakens the atomic `UPDATE ... RETURNING` claim (e.g., switching to a `get()` + `save()` pattern), the race-proof property would silently break without test failure. The existing sequential test would still pass. This masks a regression that could enable double-claim / account-takeover. |
| **Root Cause** | The `test_reclaim_blocked` test verifies idempotency under sequential execution but does not fire two claims concurrently. The `pytest.mark.concurrent` marker on bot tests means `transaction=True` (TRUNCATE per test), not concurrent execution within a test. No `threading.Thread` or `asyncio.gather` concurrency test exists. |
| **Recommendation** | Add a permanent test that uses `asyncio.gather` to fire two `handle_login_orm` calls with the same `token_hash` but different `telegram_id` values concurrently, asserting exactly one returns a non-`None` `LoginToken`. The temporary test created during this audit (which passed) can serve as the basis. |
| **Effort** | S |
| **Priority** | P2 |
| **CWE** | CWE-754 (Improper Check for Unusual or Exceptional Conditions) — missing concurrency regression test |
| **Likelihood** | LOW |

**Evidence — `src/telegram_bot/tests/test_login.py:148-159`** *(supports: "test_reclaim_blocked is sequential, not concurrent")*:
```python
# Act: first claim succeeds
first_claim, _, _ = await handle_login_orm(
    token_hash=token_hash, telegram_id=first_user,
    username="first_user", first_name="First", last_name="User",
)
assert first_claim is not None, "First claim should succeed"

# Act: second claim of the same hash by a different user
second_claim, _, _ = await handle_login_orm(
    token_hash=token_hash, telegram_id=second_user,
    username="second_user", first_name="Second", last_name="User",
)

# Assert
assert second_claim is None, "Re-claim of a claimed token must be blocked"
```

**Evidence — Runtime concurrent test (temporary, deleted after verification)** *(supports: "R3 verified correct at runtime via temporary concurrent test")*:
```python
result_a, result_b = await asyncio.gather(
    handle_login_orm(token_hash=token_hash, telegram_id=user_a, ...),
    handle_login_orm(token_hash=token_hash, telegram_id=user_b, ...),
)
winners = [r for r in (result_a, result_b) if r[0] is not None]
assert len(winners) == 1, f"Expected exactly 1 winner, got {len(winners)}"
```
```
collected 1479 items / 1478 deselected / 1 selected
src/telegram_bot/tests/test_concurrent_claim_tmp.py .
===================== 1 passed, 1478 deselected in 32.10s ======================
```

## Cross-Finding Analysis

- **Merge candidates:** None — findings address distinct concerns (runtime behavior vs test coverage).
- **Conflicting evidence:** None.
- **Dependency chains:** None — findings are independent.

## Remediation roadmap

| Order | ID | Severity | Effort | Priority | Recommendation (summary) |
|-------|----|----------|--------|----------|--------------------------|
| 1 | AUT-001 | MEDIUM | M | P1 | Backfill FSM `user_id` from DB via middleware, or migrate to RedisStorage |
| 2 | AUT-002 | LOW | S | P2 | Add permanent concurrent double-claim race test using asyncio.gather |

## Rollout Safety

| ID | Risk | Backward-compatible? | Test gap (must cover) |
|----|------|----------------------|-----------------------|
| AUT-001 | Low | Yes (auth check becomes more permissive post-restart, never less) | Test: restart bot mid-session, verify /post works without re-login |
| AUT-002 | Low | Yes (adds test, no prod change) | N/A |
