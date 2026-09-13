---
phase: "09"
phase_name: "External Integrations & API"
date: "2026-09-12"
auditor: "Executor (subagent)"
validator: "Kilo (validator agent)"
mode: "problems-only"
report_status: "validated"
id_prefix: "EXT"
severity_taxonomy: ".kilo/commands/audit/phases/09-audit-external-api.md#severity-taxonomy"
---

# Audit Findings — External Integrations & API — Validated Report

> **Self-contained validated report.** All decisions are applied inline to the copied findings. Evidence has been re-verified against the current codebase as of 2026-09-12.

## Executive Summary

Seven findings were submitted for validation. **Four are VALIDATED**, **two are MERGED** into prior phase 08 findings (cross-phase duplicates, already resolved), and **one is RECLASSIFIED**. The runtime verification claims (R-01 through R-15) were spot-checked against actual file contents — all hold.

**Corrected type distribution:**

| Type | Count | Details |
|------|-------|---------|
| SPEC-DEVIATION | 2 | EXT-002, EXT-003 |
| BEST-PRACTICE | 3 | EXT-005, EXT-006, EXT-007 |
| DOC-UPDATE | 1 | EXT-001 (reclassified; merged into SRH-001) |
| Merged (cross-phase) | 2 | EXT-001 → SRH-001, EXT-004 → SRH-002 |

**Key validation findings:**
- **EXT-001 is a cross-phase duplicate of SRH-001 (phase 08):** Both identify the same stale `consent.py` docstring. Phase 08 already validated SRH-001 as DOC-UPDATE (code correct, docstring stale). EXT-001 is merged into SRH-001 — no new action needed.
- **EXT-004 is a cross-phase duplicate of SRH-002 (phase 08):** Both identify the same dead `translate_cached` function. Phase 08 already validated SRH-002 as BEST-PRACTICE with a disclosed hidden dependency on `test_multi_lang_translation.py:21,53`. EXT-004 is merged into SRH-002.
- **EXT-003 is a semantic precision issue, not a security failure:** The moderation API returns 400 (a valid HTTP client-error) for schema validation failures where the audit rubric prefers 422. The critical constraint ("not 500") is already satisfied. Five existing tests deliberately assert 400, encoding this as the project's intentional convention.
- **EXT-002 is a genuine resilience gap:** `send_alerts.py` lacks the transient-error handling (retry/backoff, `return_exceptions=True`) that the parallel `immediate_alerts.py` path implements, and has no outer `try/except` around `asyncio.run()`.

## Scope & Methodology

Same as the original phase. Each finding was re-verified against:
- Actual source file contents (not just cited line numbers)
- `grep` for all references to `translate_cached`, `translate_cached_generic` across `src/`
- `git ls-files` for `.tmp/` tracking status
- `.gitignore` for coverage gaps
- Phase rubric (`.kilo/commands/audit/phases/09-audit-external-api.md` §4, §5)
- Project specification (`docs/01-spec/technical-specification.md`, `spec-index.md`, `db-schema.md`)
- Existing test assertions (`moderation/tests/test_priority_service.py`, `telegram_bot/tests/test_multi_lang_translation.py`)
- Bot middleware registration (`telegram_bot/main.py`, `telegram_bot/middlewares/permissions.py`)

## Findings Summary

| ID | Title | Severity | Type | Status | Action |
|----|-------|----------|------|--------|--------|
| EXT-001 | Stale consent.py docstring claims search queries sent to Google Translate | MEDIUM | DOC-UPDATE | Validated | Reclassified + Merged into SRH-001 (phase 08) |
| EXT-002 | send_alerts daily digest crashes on transient Telegram API errors | MEDIUM | SPEC-DEVIATION | Validated | Validated (unchanged) |
| EXT-003 | Moderation API returns 400 for schema validation instead of 422 | LOW | SPEC-DEVIATION | Validated | Validated (unchanged) |
| EXT-004 | Dead code: translate_cached (bs→ru) unused in production | LOW | BEST-PRACTICE | Validated | Reclassified + Merged into SRH-002 (phase 08) |
| EXT-005 | Redundant hmac.compare_digest in login_status is a no-op | LOW | BEST-PRACTICE | Validated | Validated (unchanged) |
| EXT-006 | Test certificate private keys committed to repository | LOW | BEST-PRACTICE | Validated | Validated (unchanged) |
| EXT-007 | Bot-side login deep-link handler lacks rate limiting | LOW | BEST-PRACTICE | Validated | Validated (unchanged) |

## Findings by Severity

### MEDIUM

#### EXT-001: ~~[MEDIUM] Stale consent.py docstring falsely claims search queries are sent to Google Translate~~ [RECLASSIFIED → DOC-UPDATE, MERGED into SRH-001]

> **Validation Note:**
> - **Action:** merged
> - **Detail:** This is a cross-phase duplicate of SRH-001 from phase 08 (Search & FTS audit). Phase 08 already validated the identical finding at `consent.py:8-13` as DOC-UPDATE: the code is correct (no query-time translation occurs), only the docstring is stale. The same evidence applies here verbatim. No additional action is needed — the phase 08 validation already covered this finding comprehensively.
> - **Evidence verified:** `consent.py:8-13` matches exactly. `translation.py:8-11` confirms search/query translation was removed. `technical-specification.md:121` states "No search queries are sent to any translation service." `spec-index.md:47,73` confirms per-language FTS with no query-time translation. Per the type-specific rule ("If code is better than docs → reclassify as DOC-UPDATE"), this is a documentation defect, not a spec deviation.
> - **See also:** SRH-001 (Phase 08 — same finding, already validated as DOC-UPDATE)

| Field | Value |
|---|---|
| **ID** | EXT-001 |
| **Title** | ~~Stale consent.py docstring falsely claims search queries are sent to Google Translate~~ |
| **Severity** | MEDIUM |
| **Type** | DOC-UPDATE (reclassified from implicit SPEC-DEVIATION) |
| **Category** | ~~Documentation / Data-flow accuracy~~ |
| **Merged into** | SRH-001 (Phase 08 — Search & FTS) |
| **Status** | Validated → Merged |
| **Problem** | ~~The module docstring for `consent.py` states: "Ad title/description (on creation) and search queries (on lookup) are sent to Google Translate..." In reality, search-query-to-translator egress was removed.~~ See SRH-001 (Phase 08) for full detail. |
| **Impact** | ~~Misrepresents data egress to a third party in a privacy/consent disclosure.~~ See SRH-001 (Phase 08). |
| **Root Cause** | ~~Docstring written when search-query translation existed; not updated when FTS replaced it.~~ See SRH-001 (Phase 08). |
| **Recommendation** | ~~Update the `consent.py` docstring to remove "search queries (on lookup)".~~ See SRH-001 (Phase 08) for the validated recommendation. |
| **Effort** | S |
| **Priority** | P1 |

---

#### EXT-002: [MEDIUM] — send_alerts daily digest command crashes on transient Telegram API errors

| Field | Value |
|---|---|
| **ID** | EXT-002 |
| **Title** | send_alerts daily digest command crashes on transient Telegram API errors |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Category** | Resilience / Error handling |
| **File(s)** | `src/backend/apps/search/management/commands/send_alerts.py:13,60,167-174` |
| **Status** | Validated |
| **Problem** | The daily `send_alerts` management command's `_send_user_digests` coroutine (line 167) only catches `TelegramBadRequest` and `TelegramForbiddenError` (permanent failures). It does NOT catch `TelegramRetryAfter` (HTTP 429), `TelegramServerError` (HTTP 5xx), or `TelegramNetworkError` (connection issues). A single transient error propagates out of the for-loop, past the `finally` block (which closes the bot session at line 183), and crashes the entire management command via `asyncio.run(self._send_user_digests(...))` at line 60 — which has no outer try/except. |
| **Impact** | When the Telegram API returns a transient error for any single user during the daily digest batch, the entire command aborts. All remaining users miss their daily alert digest for that cycle. Since notifications are already persisted before the send phase, re-running would re-send to users who already received their digest (duplicates) while users after the failure still miss theirs. |
| **Root Cause** | The immediate-alerts path (`immediate_alerts.py:207-237`) was hardened with comprehensive exception handling (permanent failures dead-lettered, transient failures retried once with capped backoff, all wrapped in a try/except for `AiogramError` at `_run_send` line 184). The `send_alerts.py` daily command was written first and was not updated to match the same resilient pattern. |
| **Recommendation** | Align `_send_user_digests` with the `immediate_alerts.py` exception handling pattern: (1) catch `TelegramRetryAfter`, `TelegramServerError`, and `TelegramNetworkError` as transient — retry once with backoff (respect `retry_after` for 429), then dead-letter on persistent failure; (2) keep `TelegramBadRequest`/`TelegramForbiddenError` as permanent dead-letter; (3) wrap the `asyncio.run()` call in `handle()` with a try/except for `AiogramError` so a single user's transient error never aborts the entire batch. Import `AiogramError`, `TelegramNetworkError`, `TelegramRetryAfter`, `TelegramServerError` from `aiogram.exceptions`. |
| **Effort** | S |
| **Priority** | P1 |
| **CWE** | CWE-754 (Improper Check for Unusual or Exceptional Conditions) |

**Evidence verified:**

- `send_alerts.py:13` — imports only `TelegramBadRequest, TelegramForbiddenError`:
```python
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
```

- `send_alerts.py:60` — `asyncio.run()` with no outer try/except:
```python
asyncio.run(self._send_user_digests(settings.BOT_TOKEN, user_ads))
```

- `send_alerts.py:167-174` — inner try/except catches only permanent failures:
```python
try:
    await bot.send_message(...)
except (TelegramBadRequest, TelegramForbiddenError) as e:
    logger.warning("Failed to send alert to user %d: %s", user_id, e)
```

- `immediate_alerts.py:22-29` — full exception import set:
```python
from aiogram.exceptions import (
    AiogramError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
```

- `immediate_alerts.py:184` — outer try/except for AiogramError:
```python
try:
    asyncio.run(_send_payloads(settings.BOT_TOKEN, payloads))
except AiogramError as exc:
    logger.error("Immediate alert send failed: %s", exc)
```

- `immediate_alerts.py:207-237` — comprehensive exception handling in `_send` (permanent dead-letter + transient retry+backoff).

- `immediate_alerts.py:239-242` — `return_exceptions=True` on `asyncio.gather`, preventing any single task from aborting the batch.

**Validation assessment:** The finding is **technically correct**. The send_alerts command lacks the transient error handling and outer safety net that the phase rubric §5(h) ("Graceful degradation") and §4.8 ("Graceful degradation — kill translation/bot dependency → assert core browse still works; search returns degraded results, not 500s") require for external integration boundaries. The immediate_alerts.py path demonstrates the project's own standard. **Spec-deviation validated.**

---

### LOW

#### EXT-003: [LOW] — Moderation API returns 400 for schema validation instead of 422

| Field | Value |
|---|---|
| **ID** | EXT-003 |
| **Title** | Moderation API returns 400 for schema validation instead of 422 |
| **Severity** | LOW |
| **Type** | SPEC-DEVIATION |
| **Category** | API validation |
| **File(s)** | `src/backend/apps/moderation/views/api_bulk.py:42-46` |
| **Status** | Validated |
| **Problem** | The moderation bulk-action API endpoint catches `pydantic.ValidationError` and returns HTTP 400 ("Invalid request body"). The audit phase rubric (§4.5: "malformed input → 422 (not 500)", §5(e): "bad input→422") expects semantically invalid input to return 422 (Unprocessable Entity). While 400 is a valid HTTP client-error code per RFC 9110, 422 is the semantically correct status for schema validation failures (the request was well-formed HTTP but contained semantically invalid data). |
| **Impact** | API clients cannot distinguish between malformed syntax (400) and schema validation failures (422), reducing error-handling precision. Low direct risk — the endpoint is staff-only, behind nginx rate limiting, and 400 already satisfies the critical constraint (not 500). |
| **Root Cause** | The Pydantic `ValidationError` is caught in the same handler as the `MAX_BULK_ACTIONS` rejection (line 58, also returns 400), returning 400 for both cases. No separate status code for semantic validation failure. |
| **Recommendation** | Return 422 (with `pydantic.ValidationError.errors()` as the JSON body) for Pydantic schema validation failures in `bulk_moderation_action`, retain 400 for the `MAX_BULK_ACTIONS` count rejection (or also return 422 for consistency). **Note:** This change requires updating 5 existing test assertions that currently expect 400: `test_unknown_action_returns_400`, `test_malformed_json_body_returns_400`, `test_empty_body_returns_400`, `test_extra_key_returns_400`, `test_selected_items_type_mismatch_returns_400` (all in `test_priority_service.py:611-708`). |
| **Effort** | T |
| **Priority** | P2 |
| **CWE** | CWE-693 (Protection Mechanism Failure) |

**Evidence verified:**

- `api_bulk.py:42-46` — catches `ValidationError`, returns status=400:
```python
try:
    payload = BulkModerationRequest.model_validate_json(request.body)
except ValidationError:
    logger.warning("Invalid bulk moderation request body")
    return JsonResponse({"error": "Invalid request body"}, status=400)
```

- `api_bulk.py:58-61` — MAX_BULK_ACTIONS rejection also returns 400 (same code path, different trigger):
```python
return JsonResponse(
    {"error": f"selected_items exceeds maximum of {MAX_BULK_ACTIONS}"},
    status=400,
)
```

- `schemas.py:24` — `extra="forbid"` rejects unknown keys (triggers ValidationError → currently 400):
```python
model_config = ConfigDict(extra="forbid")
```

- `test_priority_service.py` — 5 tests assert 400 for ValidationError cases:
  - `test_unknown_action_returns_400` (line 611) — `{"action": "unknown", ...}` → 400
  - `test_malformed_json_body_returns_400` (line 642) — `data="not-json"` → 400
  - `test_empty_body_returns_400` (line 656) — `data=""` → 400
  - `test_extra_key_returns_400` (line 670) — `{"rogue": "x", ...}` → 400 (extra="forbid")
  - `test_selected_items_type_mismatch_returns_400` (line 690) — `"selected_items": "not-a-list"` → 400

- `test_priority_service.py:736` — `test_bulk_exceeds_max_actions_returns_400` asserts 400 for MAX_BULK_ACTIONS rejection (separate from ValidationError).

- Phase rubric `.kilo/commands/audit/phases/09-audit-external-api.md:46` — §4.5: "malformed input → 422 (not 500)".

- Phase rubric §5(e) — "API surface security: unauth→401, bad input→422, injection safe, rate-limit→429."

**Validation assessment:** The finding is **technically correct** — the code returns 400 for schema validation failures where the audit phase rubric expects 422. However, the deviation is **LOW priority** because: (1) the critical constraint ("not 500") is already satisfied — 400 is not 500; (2) HTTP 400 is a semantically valid status for malformed input per RFC 9110 §15.5.1; (3) the project's test suite deliberately and consistently encodes 400 as the intended convention across 5 test cases; (4) the endpoint is staff-only with nginx rate limiting. The fix requires coordinated code + test updates. **Spec-deviation validated with LOW priority.**

---

#### EXT-004: ~~[LOW] Dead code: translate_cached (bs→ru specific function) unused in production~~ [RECLASSIFIED → BEST-PRACTICE, MERGED into SRH-002]

> **Validation Note:**
> - **Action:** merged
> - **Detail:** This is a cross-phase duplicate of SRH-002 from phase 08 (Search & FTS audit). Phase 08 already validated the identical dead-code finding at `translation.py:107-121` as BEST-PRACTICE. The grep evidence, hidden test dependency, and rollout safety concerns were fully disclosed in that validation. No additional action is needed — the phase 08 validation covers this comprehensively.
> - **Evidence verified:** `grep` for `translate_cached` (word boundary) across the entire `src/` tree confirms zero production callers. The only references are: (1) the definition (`translation.py:108`), (2) the import (`test_multi_lang_translation.py:21`), and (3) the `.cache_clear()` call in the `_reset_translation_state` test fixture (`test_multi_lang_translation.py:53`). The live translation path is `translate_text()` → `translate_cached_generic()` (called at `translation.py:192-193`).
> - **Hidden dependency (carried from SRH-002):** Removing `translate_cached` (lines 107–121) would break `test_multi_lang_translation.py:21` (ImportError) and `:53` (AttributeError on `.cache_clear()`). The test fixture must be updated atomically.
> - **Spec cross-reference:** Checked `spec-index.md`, `technical-specification.md`, and `db-schema.md` — `translate_cached` is not referenced as a required component. Mentioned only in `docs/96-researches/i18n-translation-egress.md:97` as a cache element (research doc, not a requirement).
> - **See also:** SRH-002 (Phase 08 — same finding, already validated as BEST-PRACTICE with rollout safety warnings)

| Field | Value |
|---|---|
| **ID** | EXT-004 |
| **Title** | ~~Dead code: translate_cached (bs→ru specific function) unused in production~~ |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE (confirmed — dead code removal) |
| **Category** | ~~Code quality / Maintenance~~ |
| **Merged into** | SRH-002 (Phase 08 — Search & FTS) |
| **Status** | Validated → Merged |
| **Problem** | ~~The function `translate_cached(query: str)` at line 108 is a bs→ru-specific wrapper. No production code calls this function.~~ See SRH-002 (Phase 08) for full detail. |
| **Impact** | ~~Confusing dead code with operational risk (live API key + lru_cache; accidental invocation incurs real Google Cloud costs).~~ See SRH-002 (Phase 08). |
| **Root Cause** | ~~Original bs→ru query-translation implementation, not removed when search refactored to per-language FTS.~~ See SRH-002 (Phase 08). |
| **Recommendation** | ~~Remove `translate_cached` and update test fixture.~~ See SRH-002 (Phase 08) for the validated recommendation and **critical rollout ordering**: update `test_multi_lang_translation.py:21,53` atomically before/alongside removing the function from `translation.py:107-121`. |
| **Effort** | S |
| **Priority** | P2 |

---

#### EXT-005: [LOW] — Redundant hmac.compare_digest in login_status is a no-op

| Field | Value |
|---|---|
| **ID** | EXT-005 |
| **Title** | Redundant hmac.compare_digest in login_status is a no-op |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Category** | Security correctness |
| **File(s)** | `src/backend/apps/users/views/consent.py:384-392` |
| **Status** | Validated |
| **Problem** | In `login_status`, the token is retrieved via `LoginToken.objects.get(token_hash=token_hash)` (line 386) — an ORM exact-match lookup on the unique-indexed `token_hash` field. If the lookup succeeds, `token.token_hash` is by definition equal to `token_hash` (they are the same value: the lookup key). The subsequent `hmac.compare_digest(token.token_hash, token_hash)` at line 391 therefore always returns `True`, making it a no-op. The comment (line 390) claims "Constant-time comparison (spec: spec-index.md:75, db-schema.md:86)" but the `compare_digest` is applied AFTER the comparison that already occurred in the DB lookup — it does not protect against timing attacks. |
| **Impact** | The `compare_digest` provides illusion of constant-time token verification without achieving it. The practical risk is negligible because the token has 192 bits of entropy (`secrets.token_urlsafe(24)`), making brute-force infeasible, and the actual claim uses an atomic `UPDATE ... RETURNING` with a `WHERE consumed_at IS NULL` filter. The misleading comment may cause future maintainers to believe the timing-attack protection is effective when it is not. |
| **Root Cause** | The spec (`spec-index.md:75`, `db-schema.md:93`) calls for `hmac.compare_digest`, and the developer applied it, but placed it after the ORM `get()` instead of using it in a way that would be meaningful. The spec did not specify the exact placement. |
| **Recommendation** | Option (a — preferred, per finding): Remove the redundant `compare_digest` call and its misleading comment, acknowledging that the SHA-256 hash + 192-bit entropy + atomic `UPDATE ... RETURNING` claim is the actual protection. Option (b): Restructure so the hash is compared in Python (not via DB `get`) with `compare_digest` before the DB write — more invasive, marginal benefit given the entropy. Option (a) is simpler and sufficient. |
| **Effort** | T |
| **Priority** | P2 |
| **CWE** | CWE-208 (Observable Timing Discrepancy / ineffective control) |

**Evidence verified:**

- `consent.py:384-392` — `get()` on unique-indexed field, then `compare_digest` on the same value:
```python
with transaction.atomic():
    try:
        token = LoginToken.objects.get(token_hash=token_hash)
    except LoginToken.DoesNotExist:
        return HttpResponse(status=410)

    # Constant-time comparison (spec: spec-index.md:75, db-schema.md:86)
    if not hmac.compare_digest(token.token_hash, token_hash):
        return HttpResponse(status=410)
```

- `models.py:162-167` — `token_hash` is `unique=True, db_index=True`, confirming `get()` does an exact match:
```python
token_hash = models.CharField(
    max_length=64,
    unique=True,
    db_index=True,
    help_text="SHA-256 of raw 32-char URL-safe token; raw token NEVER stored",
)
```

- `db-schema.md:93` — spec reference confirms `hmac.compare_digest` was intended:
```text
Both check `expires_at > now()`; token compare via `hmac.compare_digest` (constant time).
```

- `spec-index.md:75` — spec reference:
```text
- **Login (H):** QR deep-link login_<token> (32-char URL-safe token (~192-bit CSPRNG, rate-limited 5-min TTL),
  LoginToken two-phase atomic claim, hmac.compare_digest; consumption via POST body + CSRF (not URL query).
```

- `consent.py:303` — confirms token entropy: `raw_token = secrets.token_urlsafe(24)` (32 URL-safe chars, ~192-bit).

- `login.py:137-148` — the bot-side atomic claim uses `UPDATE ... RETURNING` with `WHERE token_hash = %s AND telegram_id IS NULL AND consumed_at IS NULL AND expires_at > %s` — zero-TOCTOU, only first valid claimer wins.

**Validation assessment:** The finding is **technically correct**. `LoginToken.objects.get(token_hash=token_hash)` on a unique-indexed field performs an exact SQL match (`token_hash = %s`). If the `get()` succeeds, `token.token_hash` IS `token_hash` — the values are identical. `hmac.compare_digest(token.token_hash, token_hash)` on identical strings always returns `True`. The security is not weakened by removing this no-op because: (1) the 192-bit token entropy makes brute-force infeasible; (2) the raw token is never stored (only its SHA-256 hash); (3) the actual two-phase claim uses an atomic `UPDATE ... RETURNING` with appropriate `WHERE` filters. **Best-practice finding validated — removing misleading code improves maintainability without compromising security.**

---

#### EXT-006: [LOW] — Test certificate private keys committed to repository

| Field | Value |
|---|---|
| **ID** | EXT-006 |
| **Title** | Test certificate private keys committed to repository |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Category** | Secrets hygiene |
| **File(s)** | `.tmp/nginx-test-certs/fullchain.pem`, `.tmp/nginx-test-certs/privkey.pem` (tracked via `git ls-files`) |
| **Status** | Validated |
| **Problem** | The files `.tmp/nginx-test-certs/fullchain.pem` and `.tmp/nginx-test-certs/privkey.pem` are tracked in the Git repository (confirmed via `git ls-files -- '.tmp/'`). These are mkcert-generated local development certificates. The `.gitignore` only excludes `docker/nginx/certs/*.pem` (line 221), not the `.tmp/nginx-test-certs/` path, so the private key (`privkey.pem`) was committed alongside the certificate. Note: `.env.docker` IS properly gitignored (line 148), and production nginx certs (`docker/nginx/certs/*.pem`) are gitignored (line 221) — the gap is specific to the `.tmp/` path. |
| **Impact** | While these are localhost development certificates (not production TLS certs), committing private keys to version control violates security hygiene. If the mkcert root CA or the private key is ever reused outside the original dev environment, it could enable MITM attacks. The `.gitignore` gap also means any future test certs in `.tmp/` would silently be committed. |
| **Root Cause** | The `.gitignore` pattern `docker/nginx/certs/*.pem` was written for the production cert mount path but does not cover the `.tmp/nginx-test-certs/` path used for local HTTPS testing. No `.tmp/` exclusion exists. |
| **Recommendation** | Add `.tmp/` to `.gitignore` (or at minimum `.tmp/nginx-test-certs/`), and remove the tracked `privkey.pem` and `fullchain.pem` from Git via `git rm --cached`. Verify no other `.tmp/` test artifacts are tracked. |
| **Effort** | T |
| **Priority** | P2 |
| **CWE** | CWE-312 (Cleartext Storage of Sensitive Information) |

**Evidence verified:**

- `git ls-files -- '.tmp/'` output — both files are tracked:
```text
.tmp/nginx-test-certs/fullchain.pem
.tmp/nginx-test-certs/privkey.pem
```

- `privkey.pem` contents confirm it is a real PEM private key:
```text
-----BEGIN PRIVATE KEY-----
... (26 lines of base64) ...
-----END PRIVATE KEY-----
```

- `.gitignore:220-222` — only covers production cert path:
```text
# mkcert development certificates (never commit private keys)
docker/nginx/certs/*.pem
!docker/nginx/certs/.gitkeep
```

- `.gitignore:148` — `.env.docker` IS gitignored (production secrets properly excluded):
```text
.env.docker
```

- No `.tmp/` exclusion exists anywhere in `.gitignore` (253 lines, verified).

**Validation assessment:** The finding is **technically correct**. `git ls-files` confirms both `.pem` files are tracked in the repository. The `.gitignore` does not exclude the `.tmp/` path, creating a gap. The risk is LOW (these are mkcert-generated localhost development certificates, not production TLS certs), but the practice violates basic secrets hygiene: committing private keys to version control creates risk of CA reuse and MITM attacks if the certificates are ever used outside the original dev environment. **Best-practice finding validated.**

---

#### EXT-007: [LOW] — Bot-side login deep-link handler lacks rate limiting

| Field | Value |
|---|---|
| **ID** | EXT-007 |
| **Title** | Bot-side login deep-link handler lacks rate limiting |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Category** | Defense-in-depth |
| **File(s)** | `src/telegram_bot/handlers/login.py:34-119` |
| **Status** | Validated |
| **Problem** | The `handle_login_deep_link` handler (responding to `/start login_<token>`) performs no rate limiting before executing the token claim. The web side rate-limits token ISSUANCE (`login_rate_limit_check` — 10/min per IP, `check_deep_link_render_rate_limit` — 60/10min), but the bot side — which actually claims the token via `UPDATE ... RETURNING` — has no per-chat or per-token rate limiting. Other bot endpoints (file uploads, contact-start) are rate-limited via `telegram_bot/services/rate_limit.py`, but login is not. |
| **Impact** | An attacker who knows or guesses a valid `login_<token>` deep-link format could spam `/start login_<token>` messages to the bot, causing a stream of DB UPDATE queries on the `login_tokens` table. The 192-bit token entropy makes brute-force guessing infeasible, and the atomic claim (`UPDATE ... RETURNING` with `consumed_at IS NULL` filter) ensures only the first valid claim succeeds — but a flood of login deep-links still consumes bot event-loop time and DB connections. |
| **Root Cause** | The login handler was implemented as part of the two-phase auth flow without applying the same `check_upload_rate_limit` / `check_contact_start_rate_limit` pattern from `telegram_bot.services.rate_limit` used by `ad_create` and `contact` handlers. The web-side rate limits were assumed sufficient as a proxy for bot-side protection. |
| **Recommendation** | Add a lightweight per-chat rate limit to `handle_login_deep_link` (e.g., 10 login claims per minute per Telegram `chat_id`) using the existing `telegram_bot.services.rate_limit` pattern (`check_upload_rate_limit` idiom with `cache.add` + `cache.incr`). If rate-limited, respond with a cooldown message and return early. |
| **Effort** | S |
| **Priority** | P2 |
| **CWE** | CWE-770 (Allocation of Resources Without Limits) |

**Evidence verified:**

- `login.py:34-101` — `handle_login_deep_link` has no rate-limiting call before `handle_login_orm`:
```python
@router.message(Command("start"))
async def handle_login_deep_link(message, bot, state) -> None:
    ...
    raw_token = match.group(1)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    login_token, user, created = await handle_login_orm(
        token_hash=token_hash, ...
    )
```
No `check_*_rate_limit(...)` call precedes the DB claim.

- `main.py:52-62` — bot middleware stack has no rate-limiting middleware:
```python
dp.message.middleware(AccountStateMiddleware())          # account state checks (banned/deleted/etc.)
dp.update.middleware(UpdateIdDedupMiddleware())          # Telegram update-ID dedup
dp.update.middleware(LivenessMiddleware())               # liveness marker
dp.update.outer_middleware(DatabaseConnectionMiddleware()) # DB connection lifecycle
```
`AccountStateMiddleware` checks account state flags (is_banned, is_deleted, is_declined, consent_revoked) but does NOT rate-limit (verified in `permissions.py:42-97`).

- `rate_limit.py:20-24,70-75` — existing per-chat rate-limit patterns:
```python
RATE_LIMIT_REQUESTS: Final[int] = 10      # uploads: 10/60s per user
RATE_LIMIT_PERIOD: Final[int] = 60
CONTACT_RATE_LIMIT_REQUESTS: Final[int] = 5  # contact-start: 5/600s per user
CONTACT_RATE_LIMIT_PERIOD: Final[int] = 600
```
No `check_login_rate_limit` function exists — login deep-link claims are unthrottled at the bot layer.

- `login_rate_limit.py:18-19,47-55` — web-side issuance rate limit exists:
```python
RATE_LIMIT_REQUESTS: Final[int] = 10
RATE_LIMIT_PERIOD: Final[int] = 60
def login_rate_limit_check(request: HttpRequest) -> bool: ...
```
This limiter guards `login_issue` (token ISSUANCE at `consent.py:299`); no equivalent guards the bot-side CLAIM in `handlers/login.py`.

- `login.py:137-148` — the actual claim is an atomic `UPDATE ... RETURNING` with `WHERE token_hash = %s AND telegram_id IS NULL AND consumed_at IS NULL AND expires_at > %s` — only the first valid claimer wins (verified correct).

**Validation assessment:** The finding is **technically correct**. The bot-side login handler has no rate limiting, while the web-side token issuance does (10/min per IP). The existing `telegram_bot.services.rate_limit` pattern (`cache.add` + `cache.incr` idiom) is available and used by `ad_create` and `contact` handlers but not by `login`. The core security properties (192-bit entropy, atomic claim, 5-min expiry, replay rejection, `consumed_at IS NULL` filter) are already sound — the missing rate limit is a defense-in-depth gap for resource-exhaustion protection. **Best-practice finding validated.**

---

## Cross-Finding Analysis

### Cross-Phase Duplicates (Merge Candidates)

| Original ID | Merged Into | Phase | Rationale |
|-------------|-------------|-------|-----------|
| EXT-001 | SRH-001 | 08 | Identical finding: stale `consent.py:8-13` docstring claiming search queries are sent to Google Translate. Phase 08 already validated as DOC-UPDATE (code correct, docstring stale). The evidence, root cause, and recommendation are identical. |
| EXT-004 | SRH-002 | 08 | Identical finding: dead `translate_cached` function at `translation.py:107-121`. Phase 08 already validated as BEST-PRACTICE with full hidden-dependency disclosure on `test_multi_lang_translation.py:21,53`. |

Both cross-phase duplicates were already comprehensively validated in phase 08. EXT-001 and EXT-004 add no new information and are merged into their phase 08 counterparts.

### Within-Phase Analysis

- **Merge candidates (same phase):** None — all 7 findings have distinct root causes within phase 09.
- **Conflicting evidence:** None.
- **Dependency chains:**
  - **EXT-004 → `test_multi_lang_translation.py:21,53`** (carried from SRH-002): Removing `translate_cached` requires atomically updating the test fixture's import and `.cache_clear()` call. Must be done in a single commit.
  - **EXT-003 → 5 test cases:** Changing 400→422 for `ValidationError` in the moderation API requires updating 5 existing test assertions (`test_unknown_action_returns_400`, `test_malformed_json_body_returns_400`, `test_empty_body_returns_400`, `test_extra_key_returns_400`, `test_selected_items_type_mismatch_returns_400`). These tests currently encode 400 as the intended behavior.
  - All other findings are independent.

## Rollout Safety

| ID | Risk | Backward-compatible? | Test gap (must cover) | Corrected dependency |
|----|------|----------------------|-----------------------|---------------------|
| EXT-001 | Low | Yes | N/A (doc change only) — merged into SRH-001 | None — already validated in phase 08 |
| EXT-002 | Med | Yes | Test: transient Telegram errors in `_send_user_digests` do not abort entire batch; test: retry+backoff engages for `TelegramRetryAfter`/`TelegramServerError`/`TelegramNetworkError`; test: `AiogramError` caught in `handle()` | None |
| EXT-003 | Low | Yes (with test updates) | Test: 422 returned for invalid JSON body / schema violation; UPDATE 5 existing tests that assert 400 to assert 422 (or 400 for MAX_BULK_ACTIONS only) | Must update 5 test assertions atomically with the code change |
| EXT-004 | Low | Yes | N/A (merged into SRH-002) — see phase 08 | **MUST** update `test_multi_lang_translation.py:21,53` atomically before/alongside removal |
| EXT-005 | Low | Yes | Test: `login_status` still returns 410 for invalid/expired tokens | None |
| EXT-006 | Low | Yes | Test: CI verifies no `.tmp/` files are tracked in git | None |
| EXT-007 | Low | Yes | Test: per-chat login rate limit returns appropriate response after threshold; test: legitimate single claim not blocked | None |

### Rollout Safety Warnings

1. **EXT-003 test churn:** Five existing tests in `test_priority_service.py` deliberately assert HTTP 400 for Pydantic `ValidationError` cases. If the API is changed to return 422, ALL five tests must be updated in the same commit. Failure to update any one test will cause a test failure. Per the project rule "Production Code is King — fix or remove tests that conflict with architecture," if the 422 convention is adopted as the architectural standard, the tests should be updated to match. If 400 is retained as the project convention, EXT-003 should be rejected (see Validation Summary).

2. **EXT-004 coordinated removal:** Removing `translate_cached` from `translation.py:107-121` without updating `test_multi_lang_translation.py:21,53` will cause an `ImportError` in the test suite. The test fixture's `_reset_translation_state` function calls both `translate_cached.cache_clear()` and `translate_cached_generic.cache_clear()`. Removing the function requires removing the import and the `.cache_clear()` call atomically. **This dependency was fully disclosed in the phase 08 validation of SRH-002.**

3. **EXT-002 batch idempotency:** The send_alerts command persists notifications BEFORE sending messages. If the command crashes mid-batch (current behavior on transient error), re-running will re-send to users who already received their digest. The fix must ensure that either (a) the retry+backoff pattern in `_send_user_digests` prevents mid-batch crashes, or (b) the notification persistence tracks send status per-user to avoid duplicates on retry. The immediate_alerts.py pattern uses `return_exceptions=True` to prevent any single failure from aborting the batch — send_alerts.py should adopt the same approach.

## Execution Validation

| Finding | Current state | Execution readiness |
|---------|--------------|-------------------|
| EXT-001 | Docstring at `consent.py:8-13` is stale; code is correct (no query-time translation) | Ready — doc-only change. **Merged into SRH-001 (phase 08), already validated.** |
| EXT-002 | `send_alerts.py:13` imports only `TelegramBadRequest, TelegramForbiddenError`; line 60 calls `asyncio.run()` with no outer try/except; immediate_alerts.py has the full pattern | Ready — align imports and exception handling with `immediate_alerts.py:22-29,184,239` |
| EXT-003 | `api_bulk.py:42-46` returns 400 for `ValidationError`; 5 tests assert 400 | Ready with test updates — change `status=400` to `status=422` + `ValidationError.errors()` in body; update 5 test assertions; retain 400 for `MAX_BULK_ACTIONS` |
| EXT-004 | Dead function at `translation.py:107-121`, no production callers; test fixture at `test_multi_lang_translation.py:21,53` imports it | Ready — **merged into SRH-002 (phase 08).** Update test fixture atomically with function removal. |
| EXT-005 | No-op `compare_digest` at `consent.py:391` after `get()` at line 386 | Ready — remove lines 390-392 (comment + compare_digest call) |
| EXT-006 | `.tmp/nginx-test-certs/*.pem` tracked in git; `.gitignore` doesn't cover `.tmp/` | Ready — add `.tmp/` to `.gitignore`, `git rm --cached` the two files |
| EXT-007 | `login.py:34-119` has no rate-limiting call; `rate_limit.py` has reusable patterns | Ready — add `check_login_rate_limit` function to `rate_limit.py` using the `check_upload_rate_limit` idiom; call it at the top of `handle_login_deep_link` |

All targets still exist in the codebase. All referenced code paths match the described behavior. No targets have drifted.

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 4 | EXT-002 (SPEC-DEVIATION), EXT-005 (BEST-PRACTICE), EXT-006 (BEST-PRACTICE), EXT-007 (BEST-PRACTICE) |
| Reclassified | 1 | EXT-004 (→ BEST-PRACTICE, was implicit) |
| Reclassified | 1 | EXT-001 (→ DOC-UPDATE, was implicit SPEC-DEVIATION) |
| Merged (cross-phase) | 2 | EXT-001 → SRH-001 (phase 08), EXT-004 → SRH-002 (phase 08) |
| Rejected | 0 | — |

### Rejected Findings

| ID | Title | — |
|----|-------|-----|
| *(none)* | | |

### Merged Findings

| Original ID | Merged Into | Phase | Rationale |
|-------------|-------------|-------|-----------|
| EXT-001 | SRH-001 | 08 | Same stale `consent.py:8-13` docstring. Phase 08 already validated as DOC-UPDATE. The code is correct (no query-time translation per `translation.py:8-11`, `technical-specification.md:121`, `spec-index.md:73`). Only the docstring is stale. |
| EXT-004 | SRH-002 | 08 | Same dead `translate_cached` function at `translation.py:107-121`. Phase 08 already validated as BEST-PRACTICE with full hidden-dependency disclosure on `test_multi_lang_translation.py:21,53`. |

### Reclassified Findings

| ID | Original Type (implicit) | New Type | Rationale |
|----|--------------------------|----------|-----------|
| EXT-001 | SPEC-DEVIATION (MEDIUM) | DOC-UPDATE | Code already implements correct behavior (no query-time translation per `translation.py:8-11` and `technical-specification.md:121`). Only the `consent.py` docstring is stale. Per type-specific rule: "If code is better than docs → reclassify as DOC-UPDATE." |
| EXT-004 | (implicit DOC-UPDATE via "dead code") | BEST-PRACTICE | Removing dead code is a maintainability improvement (BEST-PRACTICE), not a spec deviation. The code does not violate any requirement by having an unused function — it's a code-quality issue. Phase 08 already validated this classification. |

### Evidence Corrections

| Finding | Issue in Original Evidence | Correction |
|---------|---------------------------|-----------|
| EXT-001 | Original evidence is accurate | `consent.py:8-13`, `translation.py:8-11`, `technical-specification.md:119` all match exactly. No correction needed. |
| EXT-002 | Original evidence is accurate | `send_alerts.py:13,60,167-174` and `immediate_alerts.py:22-29,207-237,239` all match. No correction needed. |
| EXT-003 | Original evidence is accurate | `api_bulk.py:42-46` matches. However, the original finding did not enumerate the 5 existing test assertions that encode 400 — this is a hidden dependency not disclosed. |
| EXT-004 | Original evidence cites `test_multi_lang_translation.py:53` as the only test reference | Corrected (from phase 08): there are TWO references — import at line 21 AND `.cache_clear()` at line 53. Both must be updated. |
| EXT-005 | Original evidence is accurate | `consent.py:384-392` and `LoginToken` model match exactly. |
| EXT-006 | Original evidence is accurate | `git ls-files -- '.tmp/'` confirms tracking; `.gitignore:220-222` doesn't cover `.tmp/`. |
| EXT-007 | Original evidence is accurate | `login.py:34-101`, `main.py:52-62`, `rate_limit.py:20-24,70-75`, `login_rate_limit.py:18-19` all match. |

### Warnings

- **Cross-phase duplication (EXT-001, EXT-004):** Both findings are identical to phase 08 findings (SRH-001, SRH-002) already comprehensively validated. The phase 09 auditor rediscovered known issues. While this doesn't invalidate the phase 09 findings, it suggests the phase 09 audit scope should exclude areas already fully covered by prior phases to avoid redundant effort.

- **EXT-003 test-code tension:** Five existing tests deliberately assert HTTP 400 for Pydantic `ValidationError` cases. Changing to 422 requires coordinated test updates. Per the project rule "Production Code is King — fix or remove tests that conflict with architecture or business logic," the tests encode the project's own convention. If the audit rubric's 422 preference is adopted as the architectural standard, the tests are "correcting" the code; if 400 is retained, the finding should be rejected as non-compliant in practice.

- **EXT-002 operational gap:** The `send_alerts` management command runs via cron (daily). If it crashes mid-batch due to a transient Telegram API error, the cron operator may not notice — the command exits non-zero but the notification records are already persisted, so re-running creates duplicates. The fix should include monitoring/alerting on command exit status, or a `--resume` flag that skips users already notified.

- **EXT-006 git history:** Removing the tracked private keys via `git rm --cached` removes them from the working tree but NOT from git history. The private keys will remain in all prior commits. For full remediation, consider `git filter-repo` or BFG Repo-Cleaner to purge them from history, if the repository is public or was ever public.

- **EXT-005 spec alignment:** The spec (`spec-index.md:75`, `db-schema.md:93`) mandates `hmac.compare_digest` for constant-time token comparison. Removing the no-op call (option a) means the code no longer uses `compare_digest` at all, which diverges from the spec's letter. If full spec compliance is required, option (b) (restructure to make `compare_digest` meaningful) should be pursued instead. The validator recommends option (a) for simplicity given the 192-bit entropy, but this creates a spec divergence that should be documented.

### Required Fixes

1. **EXT-001 / SRH-001 (merged):** Update `consent.py:8-13` docstring to remove "search queries (on lookup)" from the Google Translate egress description. Align with `technical-specification.md:121` ("No search queries are sent to any translation service"). [DOC-UPDATE, already validated in phase 08]
2. **EXT-002:** Add `AiogramError`, `TelegramNetworkError`, `TelegramRetryAfter`, `TelegramServerError` imports to `send_alerts.py`. Catch transient exceptions in the per-user send loop with retry-once + capped backoff. Wrap `asyncio.run()` in `handle()` with try/except for `AiogramError`. [SPEC-DEVIATION, code fix]
3. **EXT-003 (optional):** Change `status=400` to `status=422` + `ValidationError.errors()` in `api_bulk.py:44-46`. Update 5 test assertions in `test_priority_service.py`. [SPEC-DEVIATION, code + test fix]
4. **EXT-004 / SRH-002 (merged):** Remove `translate_cached` (lines 107-121) from `translation.py`. Update `test_multi_lang_translation.py:21,53` to remove the import and `.cache_clear()` call. [BEST-PRACTICE, already validated in phase 08]
5. **EXT-005:** Remove the redundant `hmac.compare_digest` call and misleading comment at `consent.py:390-392`. [BEST-PRACTICE, code fix]
6. **EXT-006:** Add `.tmp/` (or `.tmp/nginx-test-certs/`) to `.gitignore:220`. Run `git rm --cached .tmp/nginx-test-certs/fullchain.pem .tmp/nginx-test-certs/privkey.pem`. [BEST-PRACTICE, repo hygiene]
7. **EXT-007:** Add `check_login_rate_limit` function to `rate_limit.py` (using the `check_upload_rate_limit` idiom: 10 claims/min per chat_id). Call it at the top of `handle_login_deep_link` in `login.py`, returning early with a cooldown message if rate-limited. [BEST-PACTICE, code fix]

### Advisory Recommendations

- **EXT-002 monitoring:** Add a cron-level wrapper that checks the exit code of `send_alerts` and alerts on non-zero exit, since the command is critical for user engagement and currently provides no observability on crash.
- **EXT-006 history purge:** Consider using `git filter-repo` to purge the committed private keys from git history if the repository was ever public or may become public.
- **EXT-005 spec update:** If the no-op `compare_digest` is removed (option a), update `spec-index.md:75` and `db-schema.md:93` to reflect that the actual protection is SHA-256 hash + 192-bit entropy + atomic `UPDATE ... RETURNING`, not `hmac.compare_digest`. Alternatively, implement option (b) to maintain spec compliance.

---

*This report was generated by the validator agent on 2026-09-12. All evidence was re-verified against the current codebase. Decisions are final and self-contained.*