# Phase 11 Audit Findings — Test Coverage (Validated)

**Executor:** audit-executor
**Template:** .kilo/commands/audit/phases/11-audit-test-coverage.md
**Validated:** yes

---

## Findings

### TST-001: Login-token atomic claim (replay/expiry/already-used) is UNTESTED

| Field | Value |
|-------|-------|
| **ID** | TST-001 |
| **Severity** | CRITICAL |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/telegram_bot/handlers/login.py` (`claim_login_token`, `handle_login_deep_link`); `src/backend/apps/users/models.py` (`LoginToken`) |
| **Classification** | mandatory |

**Description:** The phase lists "login-token two-phase claim/expiry/replay" as a security-critical path. The only security control that actually *enforces* single-use is `claim_login_token` (login.py:100-126): an atomic `UPDATE ... WHERE token_hash=X AND telegram_id__isnull=True AND consumed_at__isnull=True AND expires_at__gt=now`. The existing `cleanup_login_tokens` command test (`test_sweep_commands.py:254-304`) only verifies the *sweep* deletion windows (expired / consumed>24h). It never exercises the claim itself: that an already-claimed token (telegram_id set) is rejected, that an expired token is rejected, or that concurrent claims cannot both succeed. The two-phase contract (bot sets telegram_id, web sets consumed_at) and replay protection are therefore unguarded by tests.

**Evidence:**
- `src/telegram_bot/handlers/login.py:100-126` — atomic claim; never imported by any test.
- `grep "claim_login_token"` returns only bot source + `main.py`; no test reference.
- `test_sweep_commands.py:TestCleanupLoginTokens` tests deletion windows only, not the claim.

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Verified that `claim_login_token` exists in login.py lines 100-126 and performs atomic UPDATE with conditions `telegram_id__isnull=True, consumed_at__isnull=True, expires_at__gt=now`. No test imports this function. Test count confirms 68 tests total, none referencing login token claim logic. Security-critical function with zero coverage is accurately identified.

**Recommendation:** Add backend tests that drive `claim_login_token` (or a call_command/login handler exercising it) against the real shared ORM: (1) fresh unclaimed+unexpired token → claimed; (2) re-claim of same token → returns None (replay blocked); (3) expired token → None; (4) already-consumed/claimed token → None. This is the highest-value security test currently missing. Effort: small. Priority: recommended.

---

### TST-002: Core ad-lifecycle transitions (DRAFT → PUBLISHED / ON_MODERATION_FAILED) are UNTESTED

| Field | Value |
|-------|-------|
| **ID** | TST-002 |
| **Severity** | CRITICAL |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/telegram_bot/handlers/ad_create.py` (`create_draft_ad`, `update_ad_and_moderate`); `src/backend/apps/ads/models.py` (`Ad` status docstring) |
| **Classification** | mandatory |

**Description:** The phase requires the "ad-lifecycle state machine" to be meaningfully tested. The lifecycle documentation (ads/models.py:20-29) lists transitions but there is **no centralized `transition_to` enforcement and no test asserting any transition**, including forbidden ones. The primary lifecycle driver is bot-side: `create_draft_ad` (ad_create.py:361-369) creates a DRAFT, and `update_ad_and_moderate` (ad_create.py:485-568) moves DRAFT → PUBLISHED or DRAFT → ON_MODERATION_FAILED. None of this is tested. Only the *scheduled sweeps* (archive/delete/purge) that act on already-PERSISTED statuses are covered. The actual publish/moderation-fail logic — which sets `published_at`, `original_published_at` immutability, title/description/photo/price validation, and moderation-fail branching — has zero coverage.

**Evidence:**
- `src/telegram_bot/handlers/ad_create.py:361-369` and `:485-568` — lifecycle write paths; no test imports them.
- `grep "transition_to|def transition"` → no such function exists; transitions are implicit in bot code only.
- `test_sweep_commands.py` only asserts post-transition states produced by sweeps, never the transition origin.

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Verified `create_draft_ad` (lines 361-369) and `update_ad_and_moderate` (lines 485-568) exist in ad_create.py. The latter contains lifecycle logic including setting `published_at`, `original_published_at`, and `status=AdStatus.ON_MODERATION_FAILED`. No test references these functions. The grep confirms no `transition_to` function exists. This is a valid finding.

**Recommendation:** Extract the lifecycle transition into a shared, testable service (per docs `rules` and the `T004_ad_transition_centralization` research present in `.ai/researches/`) and cover: DRAFT→PUBLISHED sets `published_at` + immutable `original_published_at`; DRAFT→ON_MODERATION_FAILED on validation failure; and at minimum one forbidden-transition guard. Until centralized, add backend tests invoking `update_ad_and_moderate` against the real ORM. Effort: medium. Priority: recommended.

---

### TST-003: Entire `telegram_bot` package has ZERO tests and is not even collected by pytest

| Field | Value |
|-------|-------|
| **ID** | TST-003 |
| **Severity** | CRITICAL |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/telegram_bot/**` (handlers, states, services, middlewares, main) |
| **Classification** | mandatory |

**Description:** The phase explicitly requires "Bot FSM tested against the REAL shared ORM (DRAFT persistence); web+bot consistency covered." The whole `telegram_bot/` package — the second of the two documented processes — has no test files anywhere (only 4 test files exist, all under `src/backend/apps/`). pytest's `python_files` is `["tests.py","test_*.py"]` with no `testpaths`, and there are no `test_*.py` files under `telegram_bot/`, so the bot is not collected at all. This is exactly the "fake-ORM / not-tested-against-shared-ORM" false-confidence scenario the phase warns against: the two-process model is asserted in docs/docs but unverified.

**Evidence:**
- Glob `**/test_*.py` → only 4 files, all in `src/backend/apps/{ads,core,moderation}`.
- `pytest --co` collects 68 tests, 0 from `telegram_bot`.
- `src/telegram_bot/` contains handlers (login, ad_create, contact), `states.py`, `services/media.py`, `middlewares/permissions.py`, `main.py` — none covered.

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Verified by glob and pytest collection. Exactly 4 test files under `src/backend/apps/` (test_contact.py, test_sweep_commands.py, test_search_triggers.py, test_auto_moderation.py). Zero test files under `src/telegram_bot/`. pytest collects 68 tests total, all from backend apps. The two-process architecture claim is unverified by tests.

**Recommendation:** Add a dedicated test package for the bot that boots Django + aiogram with `pytest-asyncio` (already a dev dependency) and drives FSM/handlers against the real PostgreSQL ORM. Start with `create_draft_ad`→DRAFT persistence and `claim_login_token` (TST-001/002). Ensure bot tests share the same migration/DB fixture as web tests to prove the two-process contract. Effort: medium. Priority: recommended.

---

### TST-004: No web-view (request/response) tests for search, contact-gating, consent, or moderation

| Field | Value |
|-------|-------|
| **ID** | TST-004 |
| **Severity** | HIGH |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/backend/apps/{ads,search,users,moderation}/views/**`; `src/backend/apps/core/services/contact.py` (`get_seller_for_contact`) |
| **Classification** | advisory |

**Description:** The phase requires "Web-View-Test: Request/response, search visibility, contact gating." `grep` for `tests.py|Client()|APIClient` finds nothing — no Django test client usage anywhere. Consequences:
- FTS visibility is only asserted at the ORM/trigger level (`test_search_triggers.py`), not via the actual `search` view's `status=PUBLISHED` filter (search.py:40) — a regression in the view's filter would pass tests.
- Contact-gating is tested only for `can_contact_seller` (the template helper). The bot-facing `get_seller_for_contact` (contact.py:65-104) — which is the real delivery gate — is untested, and there is no integration test proving the web contact button and bot contact deep-link agree.
- `users/views/consent.py`, `moderation/views/review.py`, `ads/views/*` (dashboard/delete/edit/listings) have no tests.

**Evidence:**
- `grep "tests.py|Client\(|APIClient"` → `No files found`.
- `src/backend/apps/search/views/search.py:40` status filter untested at view layer.
- `contact.py:65-104` `get_seller_for_contact` not referenced by any test.

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Verified `get_seller_for_contact` exists in contact.py lines 65-104 with zone R2 conditions. No test imports this function. The search view uses `status=AdStatus.PUBLISHED` filter. No Django test client usage found in any test file. The `can_contact_seller` function is tested but that's a template helper, not the bot-facing delivery gate.

**Recommendation:** Add `tests.py` per app using Django's test `Client` (no network). Cover: search view returns only PUBLISHED ads; anonymous contact gate; consent revoke/withdraw view; moderation review action. Effort: medium. Priority: recommended.

---

### TST-005: No migration reproducibility / idempotency test

| Field | Value |
|-------|-------|
| **ID** | TST-005 |
| **Severity** | HIGH |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/backend/apps/**/migrations/*`; `src/backend/apps/core/migrations/0001_verify_lifecycle_indexes.py` |
| **Classification** | advisory |

**Description:** The phase requires a test verifying migrations apply cleanly and are idempotent, and flags "Migration test missing → schema drift undetected" as a HIGH risk. There is no test that runs `makemigrations --check`/no-missing-migrations, nor one that re-applies migrations to assert no drift. `grep "makemigrations|assertNoMigration|MigrationAutodetector"` returns no test references. The custom `0001_verify_lifecycle_indexes.py` (manual `CREATE INDEX IF NOT EXISTS`) is never asserted to be a no-op on re-run.

**Evidence:**
- `grep "def migrate|idempot|makemigrations|assertNoMigration"` → matches only command docstrings and `migrate_locked.py`, no test.
- No `tests.py` in any `migrations/` directory.

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Verified the `0001_verify_lifecycle_indexes.py` migration uses `CREATE INDEX IF NOT EXISTS` for idempotency. No tests reference migrations. Confirmed `migrate_locked.py` exists but has no tests asserting migration idempotency or drift detection.

**Recommendation:** Add a CI-step/test that asserts `makemigrations --check --dry-run` produces no new migrations (catches drift) and re-runs migrations to confirm idempotency. Effort: small. Priority: recommended.

---

### TST-006: Translation fallback (`translate_query_bs_to_ru`) untested; naive test would hit network

| Field | Value |
|-------|-------|
| **ID** | TST-006 |
| **Severity** | HIGH |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/backend/apps/search/services/query_translator.py`; `src/backend/apps/search/views/search.py` (caller) |
| **Classification** | advisory |

**Description:** The phase lists "translation fallback" as a critical behavior and warns against "E2E test hitting the real translator (cost/flaky)." `translate_query_bs_to_ru` (query_translator.py:21-49) has no test. Importantly, its happy path calls `GoogleTranslator(...).translate(...)` over the network; a test that does not mock `deep_translator` would make real outbound calls (cost + CI flakiness, and the cached `translate_cached` uses `lru_cache` so order/interactions matter). The fallback (return original query on `TimeoutError`/`RequestException`) — the exact behavior the phase wants guarded — is completely unverified.

**Evidence:**
- `src/backend/apps/search/services/query_translator.py:21-67` — no test file references it.
- No `monkeypatch`/`mock` of `deep_translator` anywhere in tests.

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Verified `translate_query_bs_to_ru` exists in query_translator.py, uses `ThreadPoolExecutor` with timeout, and calls `GoogleTranslator.translate()` on line 66. No tests reference this module. The fallback on `TimeoutError`/`RequestException` is correct but untested.

**Recommendation:** Add a unit test mocking `deep_translator.GoogleTranslator.translate`: (1) success returns translated string; (2) exception/timeout returns original query (fallback); (3) empty/whitespace query short-circuits. Mock at the network boundary so CI never calls Google. Effort: trivial. Priority: recommended.

---

### TST-007: Media validation / storage-key generation untested

| Field | Value |
|-------|-------|
| **ID** | TST-007 |
| **Severity** | HIGH |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/telegram_bot/services/media.py` (`validate_photo`, `validate_jpeg_bytes`, `generate_storage_key`, `save_photo`) |
| **Classification** | advisory |

**Description:** The phase lists "media sweep (file+row atomicity)" and bot photo handling as critical. The media *service* (`validate_photo` JPEG magic-byte + dimension + size checks, `generate_storage_key`) is pure, easily unit-testable logic with zero tests. A regression (e.g., wrong magic-byte check, wrong size bound) would ship untested. `save_photo` writes to `MEDIA_ROOT` and should be asserted to use an isolated temp media root (fixture hygiene, phase (h)).

**Evidence:**
- `src/telegram_bot/services/media.py:20-73` — no test references it.
- Glob confirms no `test_media*` file exists.

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Verified all 4 media functions exist: `validate_jpeg_bytes` (line 20), `validate_photo` (line 27), `generate_storage_key` (line 71), `save_photo` (line 431 in ad_create.py). No tests exist for this module. The functions handle photo validation (JPEG magic bytes, size, dimensions) and storage key generation (UUID v4 + .jpg).

**Recommendation:** Add unit tests for `validate_jpeg_bytes` (valid/invalid), `validate_photo` (oversize, oversize-dimensions, non-JPEG), and `generate_storage_key` (UUID v4 + `.jpg`, no PII). Use a temp `MEDIA_ROOT` override for any file-write path. Effort: small. Priority: recommended.

---

### TST-008: CI runs pytest with no coverage reporting or threshold

| Field | Value |
|-------|-------|
| **ID** | TST-008 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `.github/workflows/ci.yml` (test job); `pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Classification** | advisory |

**Description:** The phase (i) requires "coverage reporting + threshold configured (or flag absence)." CI runs `uv run pytest --tb=short` with no `--cov` and no fail-under threshold. `pytest-cov` is a dev dependency but unused. Without coverage gates, the gaps in TST-001…007 are invisible to CI — the suite can stay green while security-critical modules (bot, login claim, views) sit at 0%.

**Evidence:**
- `.github/workflows/ci.yml:62-68` — `uv run pytest --tb=short`, no coverage flags.
- `pyproject.toml:137-146` — no `addopts` coverage; `pytest-cov` listed at line 162 but never invoked.

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Verified CI runs pytest without coverage flags (line 67). The `slow` marker is defined in pyproject.toml (line 145) but `pytest-cov` is never invoked. The 19 dev dependencies include pytest-cov at line 162 but it remains unused in CI.

**Recommendation:** Add `--cov=apps --cov-report=xml --cov-report=term` and a `fail_under` threshold (start conservatively, e.g. 70%, raise over time). Surface the coverage artifact in CI. Effort: trivial. Priority: recommended.

---

### TST-009: Auto-moderation `check()` test mocks the function's own internal helpers (implementation-coupled)

| Field | Value |
|-------|-------|
| **ID** | TST-009 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/backend/apps/moderation/tests/test_auto_moderation.py` (`TestCheckFunction`); `src/backend/apps/moderation/services/auto_moderation.py` (`check`) |
| **Classification** | advisory |

**Description:** The phase (c) flags tests "coupled to private internals that break on refactor without behavior change." `TestCheckFunction` monkeypatches four private functions of the unit under test (`_get_cached_criteria`, `_validate_max_ads_per_user`, `_is_duplicate_title`, `_fail_moderation`) (test_auto_moderation.py:170-231). This tests `check()` in a heavily stubbed bubble: if those helpers are renamed/refactored (likely, per the `T004` centralization effort), the test breaks even though behavior is unchanged. Additionally the test's assertion on the seller-safe error message (lines 238-241) is brittle string-checking.

**Evidence:**
- `test_auto_moderation.py:152-241` — 4 `monkeypatch.setattr` on `auto_moderation._*` internals.
- The helpers are private (`_`-prefixed); refactoring them is expected.

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Verified in test_auto_moderation.py that `TestCheckFunction` monkeypatches `_get_cached_criteria` (lines 173-176), `_validate_max_ads_per_user` (lines 178-181), `_is_duplicate_title` (lines 183-186), and `_fail_moderation` (lines 228-231). The error message assertion checks for "does not meet our requirements" (line 238) and ensures "too short" and "title" are not exposed (lines 238-241). Tests are coupled to private implementation details.

**Recommendation:** Replace internal monkeypatching with a real fixture: a `ModerationCriteria` singleton row + a persisted Ad/User, so `check()` runs end-to-end against the ORM. Assert on the returned `(passed, error)` contract, not on private call counts. Effort: small. Priority: recommended.

---

### TST-010: Account-state gating and deletion/PII services untested

| Field | Value |
|-------|-------|
| **ID** | TST-010 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/backend/apps/users/services/account_state.py` (`can_publish_ad`, `can_login`); `src/backend/apps/users/services/deletion.py`; `src/backend/apps/users/views/consent.py` |
| **Classification** | advisory |

**Description:** The PII/consent sweep is partially covered (`consent_hard_delete` command tested in test_sweep_commands.py), but the surrounding account-state *gating* that decides publish/login eligibility — `can_publish_ad` / `can_login` (account_state.py:48-99), which encode ban vs delete vs publish-restriction — has no tests. A bug here (e.g. deleted-but-not-banned user allowed to publish) is a correctness/security gap with no safety net. `deletion.py` and the consent view are also untested.

**Evidence:**
- `src/backend/apps/users/services/account_state.py:48-99` — not referenced by any test.
- `src/backend/apps/users/services/deletion.py` — no test reference.

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Verified `can_publish_ad` (lines 48-77) and `can_login` (lines 80-99) exist in account_state.py. Both functions check `is_banned`, `is_deleted`, `ads_auto_publish`, and `consent_revoked_at` flags. No tests reference these functions. The `consent_hard_delete` command is tested but the gating logic and deletion service are not.

**Recommendation:** Add unit tests for `can_publish_ad`/`can_login` across the flag matrix (banned, deleted, ads_auto_publish=False, combinations). Add a consent-withdrawal view test. Effort: small. Priority: recommended.

---

### TST-011: Contact deep-link regex duplicated between test and bot handler (coupling/DRY)

| Field | Value |
|-------|-------|
| **ID** | TST-011 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/backend/apps/core/tests/test_contact.py:149` (`CONTACT_PATTERN`); `src/telegram_bot/handlers/contact.py` (production pattern) |
| **Classification** | advisory |

**Description:** The test re-declares the contact deep-link regex inline (`re.compile(r"^contact_(\d+)$")`, test_contact.py:149) rather than importing the source-of-truth pattern from the bot handler. If the handler's pattern changes, the test keeps asserting the old one — a false pass. This is minor but classic test/impl drift.

**Evidence:**
- `test_contact.py:148-149` comment "Deep-link pattern from telegram_bot/handlers/contact.py" then re-declares it locally.

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Verified both files have identical `CONTACT_PATTERN = re.compile(r"^contact_(\d+)$")` (contact.py line 17, test_contact.py line 149). The test comment explicitly acknowledges the source but doesn't import it. This is an accurate DRY violation finding.

**Recommendation:** Import the regex constant from the bot handler module in the test instead of re-declaring. Effort: trivial. Priority: recommended.

---

### TST-012: `slow` marker defined but unused; no integration markers

| Field | Value |
|-------|-------|
| **ID** | TST-012 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `pyproject.toml:144-146` (markers); all test files |
| **Classification** | advisory |

**Description:** The phase (LOW) notes "No test markers for slow/integration." `pyproject.toml` registers a `slow` marker but no test uses it, and there is no `integration` marker to separate DB-backed two-process tests (which need full Postgres + bot bootstrap) from fast unit tests. As the suite grows (bot tests per TST-003), a marker strategy avoids running the heavy subset on every quick check.

**Evidence:**
- `pyproject.toml:144-146` — `markers = [ "slow: ..." ]`.
- Grep shows `pytest.mark.slow` used 0 times.

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Verified `slow` marker is defined in pyproject.toml (line 145) but no test uses `pytest.mark.slow`. No `integration` marker exists. This is accurate - the marker infrastructure is in place but unused.

**Recommendation:** Tag DB-backed/integration tests with `slow`/`integration` markers; allow `pytest -m "not slow"` for fast local runs. Effort: trivial. Priority: recommended.

---

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 12 | All findings verified as accurate |
| Reclassified | 0 | — |
| Merged | 0 | — |
| Rejected | 0 | — |

### Rejected Findings

None. All findings are accurate and represent real coverage gaps.

### Merged Findings

None. Each finding addresses distinct coverage gaps.

### Reclassified Findings

None. All findings correctly classified as BEST-PRACTICE.

## Rollout Analysis

The findings reveal a critical architectural risk: the two-process system (web + bot) has zero tests for the bot process, leaving the shared ORM contract completely unverified. This creates a false sense of security where:

1. **TST-001 + TST-002 + TST-003** are interrelated and form a priority chain. The bot process (telegram_bot) is untested, and these security-critical functions are embedded in bot handlers.
2. **TST-004** requires view-layer tests which should be added alongside bot tests to ensure web+bot consistency.
3. **TST-008** (coverage reporting) should be enabled first to make the current gaps visible in CI.

## Execution Validation

All findings are currently applicable. The recommendations can be implemented incrementally:

1. **High Priority:** TST-001, TST-002, TST-003 (security-critical, two-process model unverified)
2. **Medium Priority:** TST-004, TST-005, TST-006, TST-007, TST-008, TST-009, TST-010
3. **Low Priority:** TST-011, TST-012 (quick DRY fixes)

## Warnings

- **Architectural Risk:** The two-process model claims in documentation (docs/01-spec, docs/99-agent/architecture.md) describe untested behavior. Consider adding a testing-section note that bot-process and login-claim paths lack coverage until TST-001/002/003 are addressed.
- **Security Risk:** Login token claim replay protection (TST-001) is untested. A regression in the atomic UPDATE conditions could allow token reuse.
- **Operational Risk:** No migration idempotency test means schema drift could go undetected.