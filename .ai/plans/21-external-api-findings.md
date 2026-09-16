---
id: external-api-findings
domain: plan
status: 5 findings actionable (5 code) · 2 findings already resolved (EXT-001, EXT-004) · 5 implemented + 1 doc update committed (all complete)
source: .ai/audit/99-validation/09-external-api-validated-findings.md
verification: .ai/audit/99-validation/09-external-api-validated-findings-verification.md
tags:
  - external-api
  - telegram-errors
  - moderation-api
  - consent
  - rate-limiting
  - gitignore
  - audit-fix
  - resilience
related:
  - .ai/audit/99-validation/09-external-api-validated-findings.md
  - src/backend/apps/search/management/commands/send_alerts.py
  - src/backend/apps/search/services/immediate_alerts.py
  - src/backend/apps/search/tests/test_immediate_alerts.py
  - src/backend/apps/moderation/views/api_bulk.py
  - src/backend/apps/moderation/schemas.py
  - src/backend/apps/moderation/tests/test_priority_service.py
  - src/backend/apps/users/views/consent.py
  - src/backend/apps/users/tests/test_consent.py
  - src/telegram_bot/services/rate_limit.py
  - src/telegram_bot/handlers/login.py
  - src/telegram_bot/tests/test_login.py
  - .gitignore
---

# Execution Plan 21 — External API Findings (EXT-002–EXT-007)

> **Source (validated):** `.ai/audit/99-validation/09-external-api-validated-findings.md`
> **Validated on:** 2026-09-16 (findings re-verified against current codebase)
> **Status:** 5 actionable findings · 2 already resolved (EXT-001, EXT-004) · 0 committed

---

## 0. Resolution Status & Scope

Seven findings were submitted for validation. **Two are already resolved** and require no action:

| Finding | Status | Resolution evidence |
|---|---|---|
| EXT-001 (DOC-UPDATE) | ✅ ALREADY DONE | Commit `140f21a` updated `consent.py` module docstring (lines 8–14) to state "Buyer search queries are NOT sent to any translation service". Code already correct — docstring only. |
| EXT-004 (BEST-PRACTICE) | ✅ ALREADY DONE | Commit `2b018a9` removed the dead `translate_cached` function from `translation.py` and removed it from `test_multi_lang_translation.py:21,52`. `grep -rn '\btranslate_cached\b' src/` returns zero matches. |

The remaining **five findings** are actionable and form the scope of this plan:

| Block | ID | Severity | Priority | Type | Scope (semantic targets) | Status | Agent(s) |
|---|---|---|---|---|---|---|---|
| B1 | EXT-002 | MEDIUM | P1 | SPEC-DEVIATION | `send_alerts.py` `_send_user_digests`, `handle` + imports; mirror from `immediate_alerts.py` | OPEN | Implementor ✓, Test Engineer, Validator |
| B2 | EXT-003 | LOW | P2 | SPEC-DEVIATION | `api_bulk.py` `bulk_moderation_action`; 5 test assertions in `test_priority_service.py` | OPEN | Implementor ✓, Test Engineer, Validator |
| B3 | EXT-005 | LOW | P2 | BEST-PRACTICE | `consent.py` `login_status` — remove no-op `hmac.compare_digest` + comment + import | OPEN | Implementor ✓, Validator |
| B4 | EXT-006 | LOW | P2 | BEST-PRACTICE | `.gitignore` — add `.tmp/` exclusion | OPEN | Implementor ✓, Validator |
| B5 | EXT-007 | LOW | P2 | BEST-PRACTICE | `rate_limit.py` add `check_login_rate_limit`; `login.py` call it in `handle_login_deep_link` | OPEN | Implementor ✓, Test Engineer, Validator |

### Already-resolved findings (no action)

EXT-001 — The module docstring at `consent.py` lines 8–14 already accurately reflects
the architecture: ad title/description are translated at publication time, but buyer
search queries are NOT sent to any translation service. Verified by reading the current
docstring. No edit needed.

EXT-004 — `grep -rn '\btranslate_cached\b' src/` returns **zero matches**. The dead
function and its `@lru_cache` decorator were already removed by commit `2b018a9`. The
test fixture at `test_multi_lang_translation.py:21,52` already imports
`translate_cached_generic` (the live function), not `translate_cached`.

### EXT-006 note — files vs. gitignore gap

The validated findings note that commit `2b018a9` removed `.tmp/` certs from git
(`git rm --cached`). However, the `.gitignore` file has no `.tmp/` exclusion — this
gap remains and is the actionable part of EXT-006 (Block B4). The `git rm --cached`
step is assumed already done; this plan only covers adding the `.gitignore` exclusion.

---

## 1. Dependency DAG & Rollout Order

### 1.1 Inter-block dependency analysis

```
All 5 blocks are INDEPENDENT — no shared files, no cross-dependencies.

B1 (EXT-002) — send_alerts.py           ──► independent file set
B2 (EXT-003) — api_bulk.py + test       ──► independent file set
B3 (EXT-005) — consent.py               ──► independent file set
B4 (EXT-006) — .gitignore               ──► independent file set (repo config)
B5 (EXT-007) — rate_limit.py + login.py ──► independent file set (bot layer)
```

**No semantic targets are shared between any two blocks.** The blocks touch:
- B1: `send_alerts.py` (backend/search, management command)
- B2: `api_bulk.py` + `test_priority_service.py` (backend/moderation)
- B3: `consent.py` (backend/users)
- B4: `.gitignore` (repo root config)
- B5: `rate_limit.py` + `login.py` (telegram_bot/services, telegram_bot/handlers)

**Sequential constraint: only one Implementor at a time** ⟹ B1 → B2 → B3 → B4 → B5
(not a true dependency ordering — a resource constraint). The blocks can be
reordered by the Tech Lead based on priority. B1 (P1) should go first.

### 1.2 Rollout sequence (recommended by priority)

```
B1  (EXT-002, P1)  ──►  Implementor + Test Engineer + Validator
B2  (EXT-003, P2)  ──►  Implementor + Test Engineer + Validator  
B3  (EXT-005, P2)  ──►  Implementor + Validator
B4  (EXT-006, P2)  ──►  Implementor + Validator
B5  (EXT-007, P2)  ──►  Implementor + Test Engineer + Validator
```

**Rationale:**
1. B1 first — P1 priority; resilience gap in the daily alert command.
2. B2 second — P2 but spec-deviation; API contract change with test churn.
3. B3 third — P2 best-practice; trivial removal, no functional change.
4. B4 fourth — P2 best-practice; repo-config change, zero code impact.
5. B5 last — P2 best-practice; bot-side rate limiting, new logic.

---

## 2. Block Specifications

---

## Block B1 — EXT-002: Transient Telegram error handling in `send_alerts`

**Finding:** EXT-002 (MEDIUM, P1, SPEC-DEVIATION)
**CWE:** CWE-754 (Improper Check for Unusual or Exceptional Conditions)

### Description

The daily `send_alerts` management command (`send_alerts.py` → `Command.handle` →
`_send_user_digests`) catches only `TelegramBadRequest` and `TelegramForbiddenError`
(permanent failures). It does NOT catch `TelegramRetryAfter` (HTTP 429),
`TelegramServerError` (HTTP 5xx), or `TelegramNetworkError` (connection issues).
A single transient error propagates out of the per-user `for` loop, past the
`finally` block (which closes the bot session), and crashes the entire management
command via `asyncio.run(self._send_user_digests(...))` in `handle()` — which has
no outer `try/except`.

The parallel `immediate_alerts.py` path was hardened with comprehensive exception
handling: permanent failures are dead-lettered, transient failures retry once with
capped backoff, and `asyncio.gather(return_exceptions=True)` prevents any single
task from aborting the batch. The `asyncio.run()` call in `_run_send` is wrapped
in a `try/except AiogramError`.

### Semantic targets

| File | Symbol | Current state | Change |
|---|---|---|---|
| `src/backend/apps/search/management/commands/send_alerts.py` | Module imports (line 13) | `from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError` | Add `AiogramError, TelegramNetworkError, TelegramRetryAfter, TelegramServerError` |
| `src/backend/apps/search/management/commands/send_alerts.py` | `Command.handle` (line 61) | `asyncio.run(self._send_user_digests(settings.BOT_TOKEN, user_ads))` — no try/except | Wrap in `try/except AiogramError` logging error |
| `src/backend/apps/search/management/commands/send_alerts.py` | Module-level constants | No backoff constant defined | Add `_BACKOFF_BASE: Final[float] = 0.5` (mirror `immediate_alerts.py`) |
| `src/backend/apps/search/management/commands/send_alerts.py` | `Command._send_user_digests` (line 169–176) | Inner `try/except (TelegramBadRequest, TelegramForbiddenError)` only | Add `except (TelegramRetryAfter, TelegramServerError, TelegramNetworkError)` with retry-once + backoff, then dead-letter on persistent failure |

### Changes (YAML task spec)

```yaml
task_id: EXT-002-send-alerts-transient-errors
title: Add transient Telegram error handling to send_alerts command
priority: high
depends_on: []
description: >
  Align _send_user_digests with the immediate_alerts.py exception-handling pattern:
  catch transient Telegram exceptions (429/network/5xx), retry once with capped
  backoff, dead-letter on persistent failure; wrap asyncio.run() in handle() with
  try/except AiogramError.

goals:
  - transient errors do not abort the entire daily digest batch
  - retry-once with backoff for 429/network/5xx errors
  - permanent failures (BadRequest, Forbidden) dead-lettered as before
  - outer AiogramError safety net in handle()
  - backward-compatible: no behavior change for permanent failures

files:
  - path: src/backend/apps/search/management/commands/send_alerts.py
    targets:
      - type: class
        name: Command
      - type: method
        name: handle
      - type: method
        name: _send_user_digests
    changes:
      - action: edit_imports
        description: >
          Expand the aiogram.exceptions import to include AiogramError,
          TelegramNetworkError, TelegramRetryAfter, TelegramServerError.
          Mirror immediate_alerts.py:22-29 exactly.

      - action: add_code
        description: >
          Add _BACKOFF_BASE module constant after logger definition.
        code_hint: |
          from typing import Final
          _BACKOFF_BASE: Final[float] = 0.5

      - action: modify
        description: >
          Wrap asyncio.run(self._send_user_digests(...)) in handle() with
          try/except AiogramError, logging at error level.
        code_hint: |
          try:
              asyncio.run(self._send_user_digests(settings.BOT_TOKEN, user_ads))
          except AiogramError as exc:
              logger.error("Daily alert send failed: %s", exc)

      - action: modify
        description: >
          In _send_user_digests, extend the inner try/except around bot.send_message:
          - keep (TelegramBadRequest, TelegramForbiddenError) as permanent dead-letter
          - add (TelegramRetryAfter, TelegramServerError, TelegramNetworkError) as
            transient: retry once with backoff (respect retry_after for 429), catch
            AiogramError on retry for dead-lettering.
        code_hint: |
          try:
              await bot.send_message(...)
          except (TelegramBadRequest, TelegramForbiddenError) as e:
              logger.warning("Failed to send alert to user %d: %s", user_id, e)
          except (TelegramRetryAfter, TelegramServerError, TelegramNetworkError) as e:
              # Transient — retry once with capped backoff
              if isinstance(e, TelegramRetryAfter) and e.retry_after:
                  backoff: float = float(e.retry_after)
              else:
                  backoff = _BACKOFF_BASE
              await asyncio.sleep(backoff)
              try:
                  await bot.send_message(...)
              except AiogramError as retry_exc:
                  logger.warning("Alert retry failed to user %d: %s", user_id, retry_exc)

acceptance_criteria:
  - _send_user_digests catches all 5 aiogram exception types (BadRequest, Forbidden, RetryAfter, ServerError, NetworkError)
  - transient errors (429/network/5xx) trigger retry-once with backoff
  - 429 TelegramRetryAfter respects retry_after for backoff duration
  - permanent failures (BadRequest, Forbidden) dead-letter without retry
  - retry failure (second exception) is caught by AiogramError and logged, never propagates
  - handle() wraps asyncio.run() in try/except AiogramError
  - bot.session.close() still called exactly once in finally
  - session close survives even when send raises
```

### Required tests

Create `src/backend/apps/search/tests/test_send_alerts.py` — mirror the structure
and assertion style of `test_immediate_alerts.py` (already in the same directory):

| Test | What it verifies |
|---|---|
| `TestTransientErrorHandling.test_429_retry_after_honored` | `TelegramRetryAfter` with `retry_after` → sleep honors it → retry attempted |
| `TestTransientErrorHandling.test_server_error_uses_capped_backoff` | `TelegramServerError` → backoff = `_BACKOFF_BASE` → retry attempted |
| `TestTransientErrorHandling.test_network_error_retries_and_deadletters` | `TelegramNetworkError` → retry attempted; if retry also fails, logged and swallowed |
| `TestTransientErrorHandling.test_permanent_failure_deadletters` | `TelegramForbiddenError` → no retry, logged once |
| `TestBotSafety.test_session_closed_on_transient_error` | `bot.session.close` called exactly once even when transient errors occur |
| `TestHandleSafety.test_handle_swallows_aiogram_error` | `handle()` with `--dry-run` bypassed and `_send_user_digests` raising `AiogramError` → `handle()` does not raise |
| `TestGatherIsolation.test_transient_error_does_not_cancel_siblings` | If refactored to use `asyncio.gather`, transient errors on one user don't block others |

**Test markers:** `pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]`
(no DB writes needed for the error-handling tests — can use `@pytest.mark.unit`
for pure mock tests, and `django_db` for any DB-touching tests). Follow the pattern
in `test_immediate_alerts.py` which uses `pytestmark = [pytest.mark.unit]`.

### Implementation sequence

1. Expand imports in `send_alerts.py` (add 4 names from `aiogram.exceptions`)
2. Add `_BACKOFF_BASE: Final[float] = 0.5` constant + `from typing import Final`
3. Refactor `_send_user_digests` inner `try/except` — add transient exception handling
   with retry-once + backoff
4. Wrap `asyncio.run()` in `handle()` with `try/except AiogramError`
5. Create `test_send_alerts.py` mirroring `test_immediate_alerts.py` structure
6. Run tests via Docker: `$dc run --rm -e PYTEST_OPTS="-k send_alerts test"`

### Architectural constraints

- Mirror the `immediate_alerts.py` pattern exactly (same exception names, same backoff constant)
- The `for` loop in `_send_user_digests` is sequential (not `asyncio.gather` — it sends one
  user's digest at a time, not concurrent). Do NOT introduce `asyncio.gather` unless the
  Implementor also adds `return_exceptions=True` — keep the change minimal and aligned with
  the existing sequential structure.
- `_BACKOFF_BASE` must match `immediate_alerts.py:_BACKOFF_BASE` value (0.5) for consistency
- The `finally: await bot.session.close()` block must remain intact
- No DB migration needed — this is pure error-handling logic
- `handle()` returns `None` (no exit code manipulation) — the `try/except` is purely
  to prevent crash propagation

### Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Transient error handling changes retry semantics | Behavioral: retry may delay delivery by up to `retry_after` seconds | Backoff is capped (0.5s for non-429); 429 backoff is server-mandated |
| `asyncio.run()` exception swallowing hides crashes | Operational: cron failures may go unnoticed | `logger.error` at ERROR level; recommend EXT-002 advisory monitoring (see §5) |
| `Final` import not present | Lint: `ruff` will flag missing import | Check existing imports; `typing.Final` may already be imported |

### Agents

**Implementor** (code changes to `send_alerts.py`) — primary
**Test Engineer** (create `test_send_alerts.py`) — co-equal
**Validator** (review alignment with `immediate_alerts.py` pattern, run tests)

### Verification commands

- `$dc run --rm -e PYTEST_OPTS="-k send_alerts" test`
- `uv run ruff check src/backend/apps/search/management/commands/send_alerts.py`
- `uv run basedpyright src/backend/apps/search/management/commands/send_alerts.py`
- `$dc run --rm --env PYTEST_SKIP_MARKERS=seed test` (fast gate after changes)

---

## Block B2 — EXT-003: Moderation API 400→422 for Pydantic ValidationError (optional)

**Finding:** EXT-003 (LOW, P2, SPEC-DEVIATION)
**CWE:** CWE-693 (Protection Mechanism Failure)
**Status:** OPTIONAL — project convention conflict

### Description

The moderation bulk-action API endpoint (`api_bulk.py` → `bulk_moderation_action`)
catches `pydantic.ValidationError` and returns HTTP 400. The audit phase rubric
expects 422 (Unprocessable Entity) for schema validation failures — the request
was well-formed HTTP but contained semantically invalid data.

**Critical context from validation:** HTTP 400 is a semantically valid status
per RFC 9110, the endpoint is staff-only behind nginx rate limiting, and **five
existing tests deliberately encode 400 as the project's intended convention**.
Per the project rule "Production Code is King — fix or remove tests that conflict
with architecture," if the audit rubric's 422 preference is adopted as the
architectural standard, the tests are correct to be updated; if 400 is retained
as the convention, EXT-003 should be rejected (no action).

This plan assumes the **422 convention is adopted** (per the finding's
recommendation). The MAX_BULK_ACTIONS count rejection retains 400 (it is not a
schema validation failure — it is a business-rule limit).

### Decision point

Before implementation, the Tech Lead must decide: adopt 422 for
`ValidationError` (this block), or retain 400 (reject EXT-003). This plan
documents the 422 path.

### Semantic targets

| File | Symbol | Current state | Change |
|---|---|---|---|
| `src/backend/apps/moderation/views/api_bulk.py` | `bulk_moderation_action` function (ValidationError except block, ~line 44) | `except ValidationError: return JsonResponse({"error": "Invalid request body"}, status=400)` | Change `status=400` → `status=422`; add `"errors": exc.errors()` to JSON body |
| `src/backend/apps/moderation/views/api_bulk.py` | `bulk_moderation_action` function (MAX_BULK_ACTIONS block, ~line 58) | `status=400` | Retain 400 (business-rule, not schema validation) |
| `src/backend/apps/moderation/tests/test_priority_service.py` | `TestBulkModerationActionView.test_unknown_action_returns_400` | Asserts `response.status_code == 400` | Change to 422; rename test to `test_unknown_action_returns_422` |
| `src/backend/apps/moderation/tests/test_priority_service.py` | `TestBulkModerationActionView.test_malformed_json_body_returns_400` | Asserts 400 | Change to 422; rename |
| `src/backend/apps/moderation/tests/test_priority_service.py` | `TestBulkModerationActionView.test_empty_body_returns_400` | Asserts 400 | Change to 422; rename |
| `src/backend/apps/moderation/tests/test_priority_service.py` | `TestBulkModerationActionView.test_extra_key_returns_400` | Asserts 400 | Change to 422; rename |
| `src/backend/apps/moderation/tests/test_priority_service.py` | `TestBulkModerationActionView.test_selected_items_type_mismatch_returns_400` | Asserts 400 | Change to 422; rename |
| `src/backend/apps/moderation/tests/test_priority_service.py` | `TestBulkModerationActionView.test_bulk_exceeds_max_actions_returns_400` | Asserts 400 | **Unchanged** — MAX_BULK_ACTIONS retains 400 |

### Changes (YAML task spec)

```yaml
task_id: EXT-003-moderation-400-to-422
title: Return 422 for Pydantic ValidationError in bulk moderation API
priority: low  # P2 — optional per validation report
depends_on: []
description: >
  Change the ValidationError exception handler in bulk_moderation_action to
  return HTTP 422 (Unprocessable Entity) instead of 400, including
  ValidationError.errors() in the JSON body. Retain 400 for the MAX_BULK_ACTIONS
  business-rule rejection. Update 5 existing test assertions.

goals:
  - ValidationError → 422 with structured error body
  - MAX_BULK_ACTIONS → 400 (business rule, not schema)
  - all 5 test assertions updated to 422
  - backward-compatible for MAX_BULK_ACTIONS path

files:
  - path: src/backend/apps/moderation/views/api_bulk.py
    targets:
      - type: function
        name: bulk_moderation_action
    changes:
      - action: modify
        description: >
          In the ValidationError except block, change status=400 to status=422
          and include ValidationError.errors() in the JSON body.
        code_hint: |
          except ValidationError as exc:
              logger.warning("Invalid bulk moderation request body")
              return JsonResponse(
                  {"error": "Invalid request body", "errors": exc.errors()},
                  status=422,
              )
      - action: no_change
        description: >
          The MAX_BULK_ACTIONS rejection block retains status=400 (line 58).
          This is a business-rule limit, not a schema validation failure.

  - path: src/backend/apps/moderation/tests/test_priority_service.py
    targets:
      - type: class
        name: TestBulkModerationActionView
    changes:
      - action: modify
        description: >
          Update 5 test methods: change response.status_code assertion from 400
          to 422 and update test names to *_returns_422. Keep
          test_bulk_exceeds_max_actions_returns_400 unchanged (still asserts 400).
        affected_tests:
          - test_unknown_action_returns_400 → test_unknown_action_returns_422
          - test_malformed_json_body_returns_400 → test_malformed_json_body_returns_422
          - test_empty_body_returns_400 → test_empty_body_returns_422
          - test_extra_key_returns_400 → test_extra_key_returns_422
          - test_selected_items_type_mismatch_returns_400 → test_selected_items_type_mismatch_returns_422

acceptance_criteria:
  - ValidationError returns 422 with {"error": ..., "errors": [...]} body
  - MAX_BULK_ACTIONS rejection still returns 400
  - all 5 renamed tests pass asserting 422
  - test_bulk_exceeds_max_actions_returns_400 still passes asserting 400
  - test_error_messages_sanitized still passes (uses valid payload → 200)
  - test_bulk_at_max_actions_accepted still passes (valid edge case)
```

### Required tests

**Existing tests to update** (in `TestBulkModerationActionView`):

| Test (current name → new name) | Change |
|---|---|
| `test_unknown_action_returns_400` → `test_unknown_action_returns_422` | Assert 422 instead of 400 |
| `test_malformed_json_body_returns_400` → `test_malformed_json_body_returns_422` | Assert 422 |
| `test_empty_body_returns_400` → `test_empty_body_returns_422` | Assert 422 |
| `test_extra_key_returns_400` → `test_extra_key_returns_422` | Assert 422 |
| `test_selected_items_type_mismatch_returns_400` → `test_selected_items_type_mismatch_returns_422` | Assert 422 |
| `test_bulk_exceeds_max_actions_returns_400` | **Unchanged** — still 400 |

**New test to add:**
- `test_validation_error_includes_error_details` — verify the 422 response body
  includes `exc.errors()` (structured Pydantic error list with `type`, `loc`, `msg`)

**Test file marker:** `pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]`
(already set at module level in `test_priority_service.py`)

### Implementation sequence

1. Modify `api_bulk.py` `ValidationError` handler: `status=400` → `status=422`, add `errors` field
2. Update 5 test assertions in `test_priority_service.py` (code + rename)
3. Add new test `test_validation_error_includes_error_details`
4. Run: `$dc run --rm -e PYTEST_OPTS="-k TestBulkModerationActionView" test`

### Architectural constraints

- `BulkModerationRequest` model in `schemas.py` already uses Pydantic v2 with
  `extra="forbid"` — the `ValidationError.errors()` call is available on v2
  `ValidationError` objects
- The endpoint is staff-only (`@staff_required_api` decorator) — no public API
  consumer impact
- The 5 tests are the ONLY consumers of the 400 status in test code — changing to
  422 requires no other test updates
- `exc.errors()` returns a list of dicts with `type`, `loc`, `msg`, `input`, `url`
  (Pydantic v2) — safe to serialize as JSON

### Risks

| Risk | Impact | Mitigation |
|---|---|---|
| API contract change (400→422) for staff-only endpoint | Behavioral: any internal caller expecting 400 must handle 422 | Endpoint is staff-only, no public API consumers; audit found none |
| Test name churn (5 renames) | Low: git history loses test name continuity | Rename preserves test logic; git tracks renames if done in same commit |
| `exc.errors()` serialization failure | Low: Pydantic v2 `errors()` returns JSON-serializable dicts | Covered by new test `test_validation_error_includes_error_details` |

### Agents

**Implementor** (code change in `api_bulk.py`) — primary
**Test Engineer** (update 5 tests + add new test) — co-equal
**Validator** (review 400/422 boundary, run full test class)

### Verification commands

- `$dc run --rm -e PYTEST_OPTS="-k TestBulkModerationActionView" test`
- `uv run ruff check src/backend/apps/moderation/views/api_bulk.py src/backend/apps/moderation/tests/test_priority_service.py`
- `uv run basedpyright src/backend/apps/moderation/views/api_bulk.py`

---

## Block B3 — EXT-005: Remove redundant `hmac.compare_digest` no-op in `login_status`

**Finding:** EXT-005 (LOW, P2, BEST-PRACTICE)
**CWE:** CWE-208 (Observable Timing Discrepancy / ineffective control)

### Description

In `consent.py` → `login_status`, the token is retrieved via
`LoginToken.objects.get(token_hash=token_hash)` — an ORM exact-match lookup on
the `unique=True, db_index=True` `token_hash` field. If the lookup succeeds,
`token.token_hash` is by definition equal to `token_hash` (they are the same value:
the lookup key). The subsequent `hmac.compare_digest(token.token_hash, token_hash)`
always returns `True`, making it a no-op. The comment claims "Constant-time
comparison" but the comparison already occurred in the DB `get()` — the
`compare_digest` does not provide timing-attack protection.

**Security is not weakened** by removal because:
1. The 192-bit token entropy (`secrets.token_urlsafe(24)`) makes brute-force infeasible
2. The raw token is never stored (only its SHA-256 hash)
3. The actual two-phase claim uses an atomic `UPDATE ... RETURNING` with
   `WHERE consumed_at IS NULL` filter (zero-TOCTOU)

Per the finding's Option (a — preferred): remove the no-op call and its misleading
comment. The `hmac` import becomes unused and must be removed too (verified:
`hmac` is used only at this one call site in `consent.py`).

**Spec divergence warning:** The spec (`spec-index.md:75`, `db-schema.md:93`)
mandates `hmac.compare_digest`. Removing it creates a spec divergence. The
finding recommends documenting this divergence as an advisory (see §5).

### Semantic targets

| File | Symbol | Current state | Change |
|---|---|---|---|
| `src/backend/apps/users/views/consent.py` | Module imports (line 18) | `import hmac` (used only at line 392) | Remove `import hmac` |
| `src/backend/apps/users/views/consent.py` | `login_status` function (lines 391–393) | `# Constant-time comparison (spec: spec-index.md:75, db-schema.md:86)` + `if not hmac.compare_digest(...): return HttpResponse(status=410)` | Remove comment + dead `if` block |

### Changes (YAML task spec)

```yaml
task_id: EXT-005-remove-redundant-hmac
title: Remove no-op hmac.compare_digest from login_status
priority: low
depends_on: []
description: >
  Remove the redundant hmac.compare_digest call and its misleading comment
  from login_status. The ORM get(token_hash=...) already performed exact
  match on a unique-indexed field; compare_digest on the same value is
  always True. Remove the now-unused hmac import.

goals:
  - remove no-op compare_digest call
  - remove misleading "Constant-time comparison" comment
  - remove unused hmac import
  - login_status behavior unchanged (410 for invalid/expired/consumed)

files:
  - path: src/backend/apps/users/views/consent.py
    targets:
      - type: function
        name: login_status
    changes:
      - action: remove_code
        description: >
          Remove the 3-line block: the comment line, the if statement,
          and its return. The LoginToken.objects.get() already guaranteed
          the hash matches (unique-indexed field, exact match).
        code_hint_before: |
          # Constant-time comparison (spec: spec-index.md:75, db-schema.md:86)
          if not hmac.compare_digest(token.token_hash, token_hash):
              return HttpResponse(status=410)
        code_hint_after: ""

      - action: remove_import
        description: >
          Remove `import hmac` from module imports (only used by the
          compare_digest call being removed).
        import_text: "import hmac"

acceptance_criteria:
  - hmac.compare_digest call removed from login_status
  - misleading comment removed
  - import hmac removed (no unused import)
  - login_status still returns 410 for: nonexistent token, expired token,
    already-consumed token, invalid/expired hash
  - login_status still returns 204 when bot hasn't claimed (telegram_id is None)
  - login_status still returns 200 on successful consumption
  - ruff: no "unused import" warning for hmac
```

### Required tests

The existing `TestLoginStatusNoPii` class in `test_consent.py` covers the
`login_status` view. These tests must continue to pass unchanged:

- `test_login_consume_no_raw_telegram_id` — 200 response, PII masking (the
  primary behavioral test of `login_status`)

**New test to add** (in `test_consent.py`, `TestLoginStatusNoPii` or a new class):

- `test_invalid_token_returns_410` — random 64-char hash with no matching row
  → 410 (verifies the `DoesNotExist` branch still works without compare_digest)

No new DB migrations needed. No i18n impact (no user-visible strings changed).

### Implementation sequence

1. Remove the 3-line block (comment + `if not hmac.compare_digest(...)` + return)
   from `login_status`
2. Remove `import hmac` from module-level imports
3. Run existing `test_consent.py` tests: `$dc run --rm -e PYTEST_OPTS="-k test_consent" test`
4. Add `test_invalid_token_returns_410` test

### Architectural constraints

- `LoginToken.token_hash` is `unique=True, db_index=True` — ORM `get()` performs
  `SELECT ... WHERE token_hash = %s` (exact match). If it returns a row,
  `token.token_hash` IS `token_hash` — identical strings.
- The actual security boundary is the atomic `UPDATE ... RETURNING` at lines 406–411
  (filters: `token_hash`, `telegram_id`, `consumed_at__isnull=True`,
  `expires_at__gt=now`) — not the `compare_digest`
- `hmac` is imported only for this one call site (verified via grep: 2 matches —
  the import and the call)
- The `import hashlib` (used for `sha256`) remains — it is still needed

### Spec divergence note (advisory)

The spec (`spec-index.md:75`, `db-schema.md:93`) states token comparison uses
`hmac.compare_digest`. After this change, the code no longer uses `compare_digest`
at all. The actual protection is: SHA-256 hash (only hash stored) + 192-bit entropy
+ atomic `UPDATE ... RETURNING` with `WHERE consumed_at IS NULL`. See §5
(Advisory Recommendations) for the spec doc update task.

### Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Spec divergence (removed compare_digest) | Maintainability: future maintainers may expect compare_digest per spec | Advisory doc-update task in §5; actual security is not weakened (192-bit entropy + atomic claim) |
| Removing `import hmac` breaks something | Build: `ruff` may flag unused import if missed | grep confirms `hmac` used only at line 392; removal of both is atomic |
| Behavioral regression in login_status | Security: invalid tokens may not return 410 | Existing `TestLoginStatusNoPii` test covers the 200 path; new test covers the 410 path |

### Agents

**Implementor** (remove code + import, add test) — primary
**Validator** (verify no other `hmac` usage, run tests)

### Verification commands

- `$dc run --rm -e PYTEST_OPTS="-k test_consent" test`
- `uv run ruff check src/backend/apps/users/views/consent.py src/backend/apps/users/tests/test_consent.py`
- `uv run basedpyright src/backend/apps/users/views/consent.py`
- grep: `rg hmac src/backend/apps/users/views/consent.py` → zero matches

---

## Block B4 — EXT-006: Add `.tmp/` exclusion to `.gitignore`

**Finding:** EXT-006 (LOW, P2, BEST-PRACTICE)
**CWE:** CWE-312 (Cleartext Storage of Sensitive Information)

### Description

Commit `2b018a9` removed `.tmp/nginx-test-certs/*.pem` from git via `git rm --cached`.
However, the `.gitignore` file has no `.tmp/` exclusion — the gap that allowed the
private keys to be committed in the first place remains. Any future test artifacts
placed in `.tmp/` would silently be committed again.

The fix is a one-line addition to `.gitignore`: exclude the entire `.tmp/` directory.

### Semantic targets

| File | Symbol | Current state | Change |
|---|---|---|---|
| `.gitignore` | `docker/nginx/certs/*.pem` exclusion (lines 219–221) | `# mkcert development certificates (never commit private keys)` + `docker/nginx/certs/*.pem` + `!docker/nginx/certs/.gitkeep` | Add `.tmp/` exclusion after this block |

### Changes (YAML task spec)

```yaml
task_id: EXT-006-gitignore-tmp-exclusion
title: Add .tmp/ exclusion to .gitignore
priority: low
depends_on: []
description: >
  Add .tmp/ to .gitignore to prevent future test certificate artifacts
  (and any other temp files) from being committed. The tracked files were
  already removed by commit 2b018a9 via git rm --cached; this closes the
  gitignore gap that allowed their initial commit.

goals:
  - prevent .tmp/ from being committed again
  - close the gitignore gap for test certificates
  - no production code impact

files:
  - path: .gitignore
    targets:
      - type: block
        name: mkcert development certificates section
    changes:
      - action: add_line
        description: >
          Add .tmp/ exclusion after the existing mkcert certs section
          (after line 221, the !docker/nginx/certs/.gitkeep line).
        code_hint: |
          # Local test artifacts (mkcert dev certs, etc.) — never commit private keys
          .tmp/

acceptance_criteria:
  - .tmp/ is present in .gitignore
  - git ls-files -- '.tmp/' returns zero tracked files
  - no other .tmp/ artifacts are tracked in git
  - .gitignore remains valid (no syntax errors)
```

### Required tests

| Test / Check | Command |
|---|---|
| Verify no `.tmp/` files tracked | `git ls-files -- '.tmp/'` → must return empty |
| Verify `.gitignore` syntax | Read `.gitignore` — `.tmp/` pattern present |
| Verify `.tmp/` directory still usable | `.tmp/` directory can still exist locally (gitignore only affects git tracking) |

### Implementation sequence

1. Add `.tmp/` exclusion to `.gitignore` after the mkcert certs section
2. Verify `git ls-files -- '.tmp/'` returns empty (files already removed by `2b018a9`)
3. (If any `.tmp/` files are still tracked) run `git rm --cached .tmp/nginx-test-certs/fullchain.pem .tmp/nginx-test-certs/privkey.pem`
4. Commit `.gitignore` change

### Architectural constraints

- The `.gitignore` is a repo-root config file — no code, no schema, no i18n impact
- `.tmp/` is a temporary directory — excluding it entirely is safe (it contains
  only dev/test artifacts, no source files)
- The existing `docker/nginx/certs/*.pem` exclusion (line 221) is more specific
  (production cert mount path) and remains for clarity
- `.tmp/` may contain other dev artifacts (build outputs, etc.) — excluding the
  whole directory is the safest approach per the finding's recommendation

### Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Accidentally ignoring needed `.tmp/` files | None — `.tmp/` is purely temporary by convention | Documented in the plan; `.tmp/` is not referenced by any build or test script as a source path |
| `git rm --cached` needed if files still tracked | None — commit `2b018a9` already removed them | Verify with `git ls-files` before implementing |

### Agents

**Implementor** (edit `.gitignore`, verify via `git ls-files`) — primary
**Validator** (verify no `.tmp/` files tracked, review `.gitignore` syntax)

### Verification commands

- `git ls-files -- '.tmp/'` → empty
- `git check-ignore .tmp/nginx-test-certs/privkey.pem` → should output the path (confirming ignore)
- Read `.gitignore` to confirm `.tmp/` line present

---

## Block B5 — EXT-007: Add `check_login_rate_limit` to bot rate limiter

**Finding:** EXT-007 (LOW, P2, BEST-PRACTICE)
**CWE:** CWE-770 (Allocation of Resources Without Limits)

### Description

The `handle_login_deep_link` handler in `src/telegram_bot/handlers/login.py`
responds to `/start login_<token>` deep-links and performs no rate limiting before
executing the token claim (`UPDATE ... RETURNING`). The web side rate-limits token
ISSUANCE (`login_rate_limit.py`), but the bot side — which actually claims the token
— has no per-chat or per-user rate limiting. Other bot endpoints (file uploads,
contact-start) are rate-limited via `telegram_bot/services/rate_limit.py`, but login
is not.

The fix: add a `check_login_rate_limit` function to `rate_limit.py` (mirroring the
`check_upload_rate_limit` idiom: `cache.add` + `cache.incr`), then call it at the
top of `handle_login_deep_link`, returning early with a cooldown message if
rate-limited.

### Semantic targets

| File | Symbol | Current state | Change |
|---|---|---|---|
| `src/telegram_bot/services/rate_limit.py` | Module-level constants + `check_upload_rate_limit` + `check_contact_start_rate_limit` | Two rate limiters (upload, contact) | Add `LOGIN_RATE_LIMIT_REQUESTS` / `LOGIN_RATE_LIMIT_PERIOD` constants + `_LOGIN_RATE_LIMIT_KEY_PATTERN` + `check_login_rate_limit` function |
| `src/telegram_bot/handlers/login.py` | Module imports (line 21–26) | Imports from `apps.core.enums`, `apps.core.services`, `apps.users.models`, `aiogram`, `django` | Add import of `check_login_rate_limit` from `telegram_bot.services.rate_limit` |
| `src/telegram_bot/handlers/login.py` | `handle_login_deep_link` function (lines 34–136) | No rate-limiting call before `handle_login_orm` | Add rate-limit check at the top (after deep-link pattern match, before ORM claim) |

### Design decisions

1. **Rate limit key:** Use `message.from_user.id` (Telegram user ID) as the key.
   The finding says "per chat_id" but `from_user.id` is the stable Telegram
   identity — matches the `check_contact_start_rate_limit` pattern which uses
   `message.from_user.id`.

2. **Rate limit threshold:** 10 login claims per 60 seconds per user (mirror
   `RATE_LIMIT_REQUESTS: Final[int] = 10` / `RATE_LIMIT_PERIOD: Final[int] = 60`).
   This matches the upload limiter's threshold — login is less frequent than
   uploads, so 10/60s is a generous ceiling that only catches abuse.

3. **Placement:** The rate check goes AFTER the deep-link pattern match (inside the
   `LOGIN_PATTERN.match` branch, before `handle_login_orm`), so that non-login
   `/start` messages (greeting, contact_us, unsubscribe) are not counted against
   the login budget. This mirrors how `check_contact_start_rate_limit` is called
   only inside the `CONTACT_US_PATTERN` branch.

### Changes (YAML task spec)

```yaml
task_id: EXT-007-bot-login-rate-limit
title: Add check_login_rate_limit to bot rate limiter and call in login handler
priority: low
depends_on: []
description: >
  Add a per-user rate limit to handle_login_deep_link (10 login claims per
  60 seconds per Telegram user_id) using the existing cache.add + cache.incr
  idiom from rate_limit.py. If rate-limited, respond with a cooldown message
  and return early before the DB claim.

goals:
  - per-user login claim rate limit (10/60s)
  - transient abuse (DB UPDATE flood) blocked at bot layer
  - legitimate single login claim not blocked
  - cooldown message in user's locale (gettext)
  - no change to existing rate limiters (upload, contact)

files:
  - path: src/telegram_bot/services/rate_limit.py
    targets:
      - type: function
        name: check_login_rate_limit
    changes:
      - action: add_code
        description: >
          Add LOGIN_RATE_LIMIT_REQUESTS / LOGIN_RATE_LIMIT_PERIOD constants
          (10 / 60), _LOGIN_RATE_LIMIT_KEY_PATTERN, and check_login_rate_limit
          function mirroring check_upload_rate_limit (sync_to_async + cache.add/incr).
        code_hint: |
          LOGIN_RATE_LIMIT_REQUESTS: Final[int] = 10
          LOGIN_RATE_LIMIT_PERIOD: Final[int] = 60
          _LOGIN_RATE_LIMIT_KEY_PATTERN: Final[str] = "bot_login_rl:{user_id}"

          @sync_to_async
          def check_login_rate_limit(
              user_id: int,
              limit: int = LOGIN_RATE_LIMIT_REQUESTS,
              period: int = LOGIN_RATE_LIMIT_PERIOD,
          ) -> bool:
              key = _LOGIN_RATE_LIMIT_KEY_PATTERN.format(user_id=user_id)
              try:
                  added = cache.add(key, 1, timeout=period)
                  if added:
                      current = 1
                  else:
                      current = cache.incr(key)
                  return current <= limit
              except ValueError:
                  cache.set(key, 1, timeout=period)
                  return True

  - path: src/telegram_bot/handlers/login.py
    targets:
      - type: function
        name: handle_login_deep_link
    changes:
      - action: add_import
        description: >
          Add import of check_login_rate_limit from telegram_bot.services.rate_limit.
        import_text: "from telegram_bot.services.rate_limit import check_login_rate_limit"

      - action: add_code
        description: >
          After LOGIN_PATTERN.match succeeds, before handle_login_orm call,
          check the rate limit. If exceeded, send a cooldown message via
          message.answer and return early.
        code_hint: |
          if not await check_login_rate_limit(message.from_user.id):
              logger.warning(
                  "Login rate limit exceeded for telegram_id=%s",
                  message.from_user.id,
              )
              await message.answer(
                  _("Too many login attempts. Please wait a minute and try again.")
              )
              return
        placement: >
          Insert after `match = LOGIN_PATTERN.match(deep_link)` /
          `if not match:` block returns, and before
          `raw_token = match.group(1)`.

acceptance_criteria:
  - check_login_rate_limit added to rate_limit.py (mirrors check_upload_rate_limit)
  - 10 login claims / 60s per user_id threshold
  - handle_login_deep_link calls check_login_rate_limit before handle_login_orm
  - rate-limited → message.answer with gettext cooldown message, return early
  - rate not exceeded → normal flow proceeds (claim + user creation)
  - existing upload and contact rate limiters unchanged
```

### Required tests

**Existing tests to verify still pass** (in `test_login.py`):

- `TestClaimLoginToken.test_claim_valid_token` — single login claim succeeds
- `TestConsentAtStart.test_new_user_gets_consent_prompt` — login flow with consent
- `TestConsentAtStart.test_existing_user_with_consent_gets_success` — login flow success

**New tests to add** (in `test_login.py` or a new `test_login_rate_limit.py`):

| Test | What it verifies |
|---|---|
| `test_login_rate_limit_allows_single_claim` | Single `handle_login_deep_link` call proceeds normally (not blocked) |
| `test_login_rate_limit_blocks_after_threshold` | 11th login claim within 60s → receives cooldown message, no DB claim |
| `test_login_rate_limit_does_not_block_non_login_start` | `/start` without `login_` pattern → not counted against rate limit |
| `test_login_rate_limit_key_is_per_user` | Two different user_ids each get their own budget (not shared) |

**Unit test** (no DB) for `check_login_rate_limit` itself:

| Test | What it verifies |
|---|---|
| `test_check_login_rate_limit_allows_under_threshold` | 1st–10th call → True |
| `test_check_login_rate_limit_blocks_over_threshold` | 11th call → False |
| `test_check_login_rate_limit_resets_after_window` | After cache expiry → True again |

### Implementation sequence

1. Add `check_login_rate_limit` function + constants to `rate_limit.py`
2. Add import to `login.py`
3. Add rate-limit check call in `handle_login_deep_link` (after pattern match, before ORM claim)
4. Add tests for rate limiting behavior
5. Run: `$dc run --rm -e PYTEST_OPTS="-k login or -k rate_limit" test`

### Architectural constraints

- Must mirror `check_upload_rate_limit` exactly (same `@sync_to_async` decorator,
  same `cache.add` + `cache.incr` idiom with `ValueError` fallback)
- `Final` is already imported in `rate_limit.py` (line 14: `from typing import Final`)
- `logger` is already defined in `rate_limit.py` (line 19) and `login.py` (line 26)
- The cooldown message must use `gettext` (`_`) for i18n compliance (rule #16)
- `message.from_user.id` is the stable Telegram identity (matches
  `check_contact_start_rate_limit` parameter naming)
- The rate check goes AFTER the `LOGIN_PATTERN.match` check, so non-login deep-links
  (contact_us, unsubscribe) are NOT counted against the login budget
- The `@sync_to_async` decorator is needed because `cache` operations are
  synchronous Django cache API calls

### Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Rate limit blocks legitimate user during normal use | Usability: user can't login if they spam /start | 10/60s is generous; single login is well within budget |
| Rate limit check adds latency | Performance: `sync_to_async` + cache round-trip | Cache is in-memory (LocMemCache in dev, Redis in prod) — sub-millisecond |
| Cache miss / Redis down → `ValueError` fallback returns True | Security: rate limit silently bypassed | `ValueError` fallback returns `True` (allow) — same as existing limiters; documented behavior |
| Rate limit check placement blocks non-login /start | UX: user can't get greeting or contact deep-link | Check is placed AFTER `LOGIN_PATTERN.match`, not before — only login deep-links are counted |

### Agents

**Implementor** (add function to `rate_limit.py`, call in `login.py`) — primary
**Test Engineer** (unit + integration tests for rate limiting) — co-equal
**Validator** (verify mirror of `check_upload_rate_limit`, run bot test suite)

### Verification commands

- `$dc run --rm -e PYTEST_OPTS="-k login" test`
- `$dc run --rm -e PYTEST_OPTS="-k rate_limit" test`
- `uv run ruff check src/telegram_bot/services/rate_limit.py src/telegram_bot/handlers/login.py`
- `uv run basedpyright src/telegram_bot/services/rate_limit.py`
- Full bot test suite: `$dc run --rm -e PYTEST_OPTS="-k test_login or -k test_contact" test`

---

## 3. Rollout Safety Summary

| Block | Backward-compatible? | Risk | Test gap (must cover) | Atomicity |
|---|---|---|---|---|
| B1 (EXT-002) | Yes — only adds resilience | Medium (behavioral: retry on transient) | Transient errors don't abort batch; retry+backoff engages; AiogramError caught in handle() | No — additive changes only |
| B2 (EXT-003) | Yes (with test updates) | Low — staff-only endpoint | 422 returned for ValidationError; 5 tests updated atomically; MAX_BULK still 400 | Yes — code + 5 tests must be same commit |
| B3 (EXT-005) | Yes — removes dead code | Low | login_status still returns 410 for invalid tokens | No — code + import removal is naturally atomic |
| B4 (EXT-006) | Yes — config only | None | No .tmp/ files tracked in git | No — single .gitignore line |
| B5 (EXT-007) | Yes — adds rate limit | Low | Per-user login rate limit blocks after threshold; legitimate single claim not blocked | No — additive, non-breaking |

### Cross-block safety notes

1. **B1 and B5** both touch error handling / rate limiting patterns but in different
   codebases (backend/search vs telegram_bot). No file overlap. Parallel-safe.

2. **B2 and B3** both touch authentication-adjacent code (moderation API and login)
   but in completely different modules (`moderation/views/api_bulk.py` vs
   `users/views/consent.py`). No shared dependencies.

3. **B4** is a `.gitignore` change with zero code impact — can be done in parallel
   or independently at any time.

4. **B1 test pattern:** The existing `test_immediate_alerts.py` provides the exact
   template for `test_send_alerts.py` — same mock patterns, same exception
   assertion style. The Implementor should mirror it closely.

5. **B5 rate_limit.py:** The new `check_login_rate_limit` function follows the
   exact same `@sync_to_async` + `cache.add`/`cache.incr` idiom as the two existing
   functions. No new patterns introduced.

6. **B3 spec divergence:** Removing `hmac.compare_digest` creates a divergence
   from `spec-index.md:75` and `db-schema.md:93` which mandate `compare_digest`.
   The finding recommends documenting this (see §5, Advisory Recommendation AR-1).

---

## 4. Implementation Checklist

### Block B1 — EXT-002 (send_alerts transient errors)

- [ ] Expand `aiogram.exceptions` import in `send_alerts.py` (add 4 names)
- [ ] Add `from typing import Final` if not already imported
- [ ] Add `_BACKOFF_BASE: Final[float] = 0.5` constant
- [ ] Refactor `_send_user_digests` inner try/except: add transient exception handling
- [ ] Wrap `asyncio.run()` in `handle()` with try/except AiogramError
- [ ] Create `test_send_alerts.py` mirroring `test_immediate_alerts.py`
- [ ] Run: `$dc run --rm -e PYTEST_OPTS="-k send_alerts" test`
- [ ] Lint: `uv run ruff check src/backend/apps/search/management/commands/send_alerts.py`
- [ ] Typecheck: `uv run basedpyright src/backend/apps/search/management/commands/send_alerts.py`

### Block B2 — EXT-003 (moderation API 400→422)

- [ ] Change `api_bulk.py` ValidationError handler: status=400 → 422, add `errors` field
- [ ] Verify MAX_BULK_ACTIONS block retains status=400
- [ ] Update 5 test assertions in `test_priority_service.py` (400 → 422)
- [ ] Rename 5 test methods (*_returns_400 → *_returns_422)
- [ ] Add `test_validation_error_includes_error_details` test
- [ ] Verify `test_bulk_exceeds_max_actions_returns_400` unchanged
- [ ] Run: `$dc run --rm -e PYTEST_OPTS="-k TestBulkModerationActionView" test`
- [ ] Lint: `uv run ruff check src/backend/apps/moderation/`

### Block B3 — EXT-005 (remove redundant hmac.compare_digest)

- [ ] Remove comment + `if not hmac.compare_digest(...)` block from `login_status`
- [ ] Remove `import hmac` from `consent.py` module imports
- [ ] Add `test_invalid_token_returns_410` test to `test_consent.py`
- [ ] Run: `$dc run --rm -e PYTEST_OPTS="-k test_consent" test`
- [ ] Lint: `uv run ruff check src/backend/apps/users/views/consent.py`
- [ ] Verify: `rg hmac src/backend/apps/users/views/consent.py` → zero matches

### Block B4 — EXT-006 (gitignore .tmp/ exclusion)

- [ ] Add `.tmp/` exclusion to `.gitignore` after the mkcert certs section
- [ ] Verify: `git ls-files -- '.tmp/'` → empty
- [ ] Verify: `git check-ignore .tmp/nginx-test-certs/privkey.pem` → outputs path

### Block B5 — EXT-007 (bot login rate limit)

- [ ] Add `check_login_rate_limit` function to `rate_limit.py` (mirror `check_upload_rate_limit`)
- [ ] Add `LOGIN_RATE_LIMIT_REQUESTS` / `LOGIN_RATE_LIMIT_PERIOD` constants
- [ ] Add `_LOGIN_RATE_LIMIT_KEY_PATTERN` constant
- [ ] Add import to `login.py`
- [ ] Add rate-limit check in `handle_login_deep_link` (after pattern match, before ORM claim)
- [ ] Add unit tests for `check_login_rate_limit`
- [ ] Add integration tests for rate-limited login in `test_login.py`
- [ ] Run: `$dc run --rm -e PYTEST_OPTS="-k login" test`
- [ ] Lint: `uv run ruff check src/telegram_bot/services/rate_limit.py src/telegram_bot/handlers/login.py`

---

## 5. Advisory Recommendations

### AR-1 — EXT-005 spec alignment (doc-only)

After removing `hmac.compare_digest` from `login_status` (B3), update the spec
references that mandate `hmac.compare_digest`:

| File | Location | Stale content | Correction |
|---|---|---|---|
| `docs/01-spec/spec-index.md` | line 75 | "...LoginToken two-phase atomic claim, hmac.compare_digest..." | Replace with: "...LoginToken two-phase atomic claim via UPDATE ... RETURNING with WHERE consumed_at IS NULL; raw token SHA-256 hashed, 192-bit entropy..." |
| `docs/02-database/db-schema.md` | line 93 | "Both check `expires_at > now()`; token compare via `hmac.compare_digest` (constant time)." | Replace with: "Token validation: SHA-256 hash stored (raw token never persisted). Claim via atomic `UPDATE ... RETURNING` with `WHERE token_hash = %s AND telegram_id IS NULL AND consumed_at IS NULL AND expires_at > %s` — only first valid claimer wins (zero-TOCTOU). 192-bit token entropy makes brute-force infeasible." |

### AR-2 — EXT-002 monitoring (operational)

The `send_alerts` command runs via cron (daily). If it crashes mid-batch (even
after the transient-error fix, e.g. due to a non-Aiogram `RuntimeError`), the cron
operator may not notice. Recommend:

- Add a cron-level wrapper that checks exit code and alerts on non-zero
- OR add a `--resume` flag to `send_alerts` that skips users already notified
  (the `SavedSearchNotification` records are persisted before the send phase)

This is out of scope for the code fix but should be tracked as a follow-up.

### AR-3 — EXT-006 git history purge (security, optional)

`git rm --cached` (already done by `2b018a9`) removes files from the working tree
but NOT from git history. The private keys remain in all prior commits. If the
repository is public or was ever public, consider:

- `git filter-repo --path .tmp/nginx-test-certs/privkey.pem --invert-paths`
- BFG Repo-Cleaner equivalent
- Rotating the mkcert CA if the cert was ever reused

This is purely historical cleanup and does not affect the `.gitignore` fix.

---

## 6. Verification Strategy

### 6.1 Test infrastructure

All tests run via Docker Compose (local `uv run pytest` fails — no DB on localhost):

```powershell
$dc='docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml'
```

| Purpose | Command |
|---|---|
| Start test DB | `$dc up -d db` |
| Fast gate (skips seed suite) | `$dc run --rm --env PYTEST_SKIP_MARKERS=seed test` |
| Single test / keyword filter | `$dc run --rm -e PYTEST_OPTS="-k test_name" test` |
| Fresh schema (after migration changes) | `$dc run --rm --env PYTEST_OPTS="--create-db --tb=short -n auto --maxprocesses=4 --dist loadgroup" test` |
| Lint | `uv run ruff check <path>` |
| Typecheck | `uv run basedpyright <path>` |

### 6.2 Test coverage matrix

| Block | Test file | Test(s) | Docker command |
|---|---|---|---|
| B1 | `src/backend/apps/search/tests/test_send_alerts.py` (new) | Transient error retry, backoff, session close, handle() safety | `$dc run --rm -e PYTEST_OPTS="-k send_alerts" test` |
| B2 | `src/backend/apps/moderation/tests/test_priority_service.py` (existing, updated) | 5 renamed tests assert 422; MAX_BULK still 400; new error-details test | `$dc run --rm -e PYTEST_OPTS="-k TestBulkModerationActionView" test` |
| B3 | `src/backend/apps/users/tests/test_consent.py` (existing + 1 new) | `TestLoginStatusNoPii` passes; new `test_invalid_token_returns_410` | `$dc run --rm -e PYTEST_OPTS="-k test_consent" test` |
| B4 | (git-only, no pytest) | `git ls-files -- '.tmp/'` → empty | `git ls-files -- '.tmp/'` |
| B5 | `src/telegram_bot/tests/test_login.py` (existing + new) | Existing login tests pass; new rate-limit tests | `$dc run --rm -e PYTEST_OPTS="-k login or -k rate_limit" test` |

### 6.3 Post-implementation regression gate

After all blocks complete:
```powershell
$dc run --rm --env PYTEST_SKIP_MARKERS=seed test
```

This runs the fast gate (skips the ~300s seed suite). Must pass fully.

### 6.4 Lint + typecheck targets

| Block | Lint target | Typecheck target |
|---|---|---|
| B1 | `send_alerts.py` | `send_alerts.py` |
| B2 | `api_bulk.py`, `test_priority_service.py` | `api_bulk.py` |
| B3 | `consent.py`, `test_consent.py` | `consent.py` |
| B4 | (none — .gitignore is not Python) | (none) |
| B5 | `rate_limit.py`, `login.py` | `rate_limit.py`, `login.py` |

---

## 7. Agent Requirements Summary

| Block | Primary Agent | Supporting Agents | Review Gate |
|---|---|---|---|
| B1 (EXT-002) | Implementor | Test Engineer (new test file), Validator | Validator verifies alignment with `immediate_alerts.py` pattern |
| B2 (EXT-003) | Implementor | Test Engineer (5 test updates + 1 new), Validator | Validator verifies 400/422 boundary, runs full test class |
| B3 (EXT-005) | Implementor | Validator | Validator verifies zero `hmac` references remaining |
| B4 (EXT-006) | Implementor | Validator | Validator verifies `git ls-files` clean |
| B5 (EXT-007) | Implementor | Test Engineer (unit + integration tests), Validator | Validator verifies mirror of `check_upload_rate_limit` idiom |

### Key decision points

1. **B1:** Should `_send_user_digests` be refactored to use `asyncio.gather` (like
   `immediate_alerts.py`)? **Recommendation: No** — the current sequential `for` loop
   is intentional (sends one digest at a time, not concurrent). Keep the change minimal:
   add transient exception handling to the existing per-user `try/except`.

2. **B2:** Adopt 422 for `ValidationError` or retain 400? **This plan assumes 422.**
   If the Tech Lead decides to retain 400, EXT-003 is rejected — no implementation.

3. **B5:** Rate limit threshold — 10/60s per user (mirroring upload limiter).
   Could be tighter (e.g., 5/60s) since login claims are rarer than uploads.
   **Recommendation: 10/60s** for consistency with the existing upload limiter
   and to avoid blocking legitimate users during testing.

---

## 8. File Manifest

### Files to be created

| File | Block | Purpose |
|---|---|---|
| `src/backend/apps/search/tests/test_send_alerts.py` | B1 | Tests for transient error handling in `send_alerts` |

### Files to be modified

| File | Block | Change |
|---|---|---|
| `src/backend/apps/search/management/commands/send_alerts.py` | B1 | Imports + transient exception handling + AiogramError safety net |
| `src/backend/apps/moderation/views/api_bulk.py` | B2 | ValidationError → 422 with `errors()` body |
| `src/backend/apps/moderation/tests/test_priority_service.py` | B2 | 5 test assertions + renames; 1 new test |
| `src/backend/apps/users/views/consent.py` | B3 | Remove `import hmac` + no-op `compare_digest` block |
| `src/backend/apps/users/tests/test_consent.py` | B3 | Add `test_invalid_token_returns_410` |
| `.gitignore` | B4 | Add `.tmp/` exclusion |
| `src/telegram_bot/services/rate_limit.py` | B5 | Add `check_login_rate_limit` + constants |
| `src/telegram_bot/handlers/login.py` | B5 | Import + call `check_login_rate_limit` in `handle_login_deep_link` |
| `src/telegram_bot/tests/test_login.py` | B5 | Add rate-limit tests |

### Files already resolved (no action)

| File | Finding | Resolution |
|---|---|---|
| `src/backend/apps/users/views/consent.py` (docstring) | EXT-001 | Commit `140f21a` — docstring already correct |
| `src/backend/apps/core/services/translation.py` | EXT-004 | Commit `2b018a9` — `translate_cached` already removed |
| `src/telegram_bot/tests/test_multi_lang_translation.py` | EXT-004 | Commit `2b018a9` — fixture already updated |
| `.tmp/nginx-test-certs/*.pem` | EXT-006 (files) | Commit `2b018a9` — `git rm --cached` already done |

---

## 9. Audit Trail

| # | Finding | Validation status | Plan action |
|---|---|---|---|
| 1 | EXT-001 — Stale consent.py docstring | Already resolved (commit 140f21a) | No action |
| 2 | EXT-002 — send_alerts crashes on transient Telegram errors | Validated | Block B1 |
| 3 | EXT-003 — Moderation API returns 400 instead of 422 for ValidationError | Validated (optional) | Block B2 |
| 4 | EXT-004 — Dead code: translate_cached | Already resolved (commit 2b018a9) | No action |
| 5 | EXT-005 — Redundant hmac.compare_digest no-op | Validated | Block B3 |
| 6 | EXT-006 — Test cert private keys committed + .gitignore gap | Files removed (2b018a9); gitignore gap remains | Block B4 (.gitignore only) |
| 7 | EXT-007 — Bot login deep-link handler lacks rate limiting | Validated | Block B5 |
