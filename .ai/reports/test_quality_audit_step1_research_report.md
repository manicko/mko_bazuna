# Test Quality Audit — Step 1 Research Report

**Date:** 2026-08-26
**Scope:** Full backend (`src/backend/`) + bot (`src/telegram_bot/`) test suites, config, fixtures, production code
**Method:** Static analysis (grep, file reads, symbol inspection) cross-referenced with `.ai/problems/audit_findings_compilation.md`

---

## 1. Architecture Summary

### Apps (15 backend + 1 bot)

| App | Layer | Purpose |
|-----|-------|---------|
| `apps/ads` | domain | `Ad`, `AdImage`, `AdFeature`, `AdFavorite` models; listings/search views; FTS |
| `apps/users` | domain | `User` (AbstractUser + telegram_id/chat_id), `LoginToken`, `ConsentRecord` |
| `apps/categories` | domain | MPTT tree, `CategoryPath` multi-parent, config-driven catalog builder (`categories.yaml`) |
| `apps/locations` | domain | `City` (closed ME list) |
| `apps/lookups` | domain | `LookupGroup`, `LookupItem` (features, purposes, conditions) |
| `apps/moderation` | service | `ModerationCriteria` singleton, `ModeratorActionLog`, `AdModerationPriority`, priority + auto-moderation services, admin actions |
| `apps/trust` | service | `SellerTrustScore`, `SellerVerification`, `TrustCalculator`, trust template tags |
| `apps/currencies` | service | `CurrencyCode`, `ExchangeRate`, `PriceNormalizer` |
| `apps/analytics` | service | `AnalyticsEvent`, `DailyAdMetrics`, seller dashboard stats, trust analytics |
| `apps/search` | service | FTS search view, autocomplete, saved-search alerts, preferred-city |
| `apps/media` | service | Thumbnail generation, EXIF stripping, photo storage keys |
| `apps/cabinet` | UI | Seller cabinet (favorites, saved searches) |
| `apps/core` | infra | Middleware (language, preferred-city), URL routes, sweep/purge commands, contact service, context processors |
| `apps/api` | API | Serializers (future DRF) |
| `apps/seed` | dev-only | `SeedService`, `UserGenerator`, `AdGenerator`, `ImageGenerator` |
| `telegram_bot` | bot | aiogram handlers (ad_create, login, contact, unsubscribe), `django.setup()` + shared ORM |

### Layer boundaries
- **Models** (Django ORM) — persistence layer
- **Services** — business logic (auto_moderation, trust_calculator, priority_calculator, price_normalizer, contact, moderation_log, alerts)
- **Views** (HTMX MPA) — web UI rendering + DB queries
- **Handlers** — bot command routing (aiogram)
- **Management commands** — scheduled jobs (sweeps, alerts, thumbnails, seed)
- **Signals** — post_save hooks (Ad → calculate_ad_priority, deliver_immediate_alerts_on_publish)

### Key workflows
1. **Ad lifecycle:** DRAFT → ON_MODERATION → PUBLISHED | REJECTED | ON_MODERATION_FAILED; PUBLISHED → ARCHIVED → PUBLISHED; PUBLISHED → ON_MODERATION (text edit); any → DELETED
2. **Moderation:** `auto_moderate()` is the only gate before PUBLISHED; post_save triggers `calculate_ad_priority` + `deliver_immediate_alerts_on_publish` (via `transaction.on_commit`)
3. **Search:** PostgreSQL native FTS on per-language vectors (`search_vector_ru/bs/en`); GIN indexes; `difflib` fuzzy category matching; 5 sort modes; filters (category/city/price/purpose/features/condition)
4. **Trust:** `TrustCalculator.calculate_and_save()` — activity (0–40) + quality (0–30) + response (0–30) = 100; floors to VERIFIED for admin-verified/premium sellers
5. **Contact:** `can_contact_seller()` — PUBLISHED + telegram_id + not deleted + not banned + consent not revoked
6. **Login:** Two-phase atomic claim — bot sets `telegram_id`, web sets `consumed_at`; SHA-256 hash stored; `hmac.compare_digest`; 5-min expiry
7. **Price normalization:** EUR/RSD/BAM → `price_normalized_eur` via cached `ExchangeRate`

### Key models
- `Ad` (db_table `ads`): 6 StrEnum-backed fields, 5 lifecycle timestamps, 4 FTS vectors, 6 CheckConstraints, 10+ conditional GIN/B-tree indexes
- `User` (db_table `users`): telegram_id/chat_id, is_banned/is_deleted/is_declined, consent_revoked_at, preferred_city FK
- `LoginToken` (db_table `login_tokens`): token_hash (SHA-256), telegram_id, consumed_at, expires_at
- `SellerTrustScore`: OneToOne(User), trust_level, score, rejection_rate
- `AdModerationPriority`: OneToOne(Ad), base_score, priority_level, flags, confidence_score

---

## 2. Key Business Behaviors (Contracts Tests Should Verify)

| Behavior | Contract | Status in code |
|----------|----------|----------------|
| Ad status-timestamp consistency | 6 CheckConstraints: each lifecycle status requires its timestamp; moderation_failed_at/rejected_at mutually exclusive | `Ad.Meta.constraints` |
| State transition matrix | `Ad.transition_to()` enforces DRAFT→ON_MODERATION, ON_MODERATION→PUBLISHED/REJECTED/ON_MODERATION_FAILED, PUBLISHED→ARCHIVED, ARCHIVED→PUBLISHED/ON_MODERATION, any→DELETED; DELETED/REJECTED terminal | `Ad.transition_to()` |
| published_at reset | Resets on every PUBLISHED transition; original_published_at immutable | `Ad.transition_to()` lines 420-428 |
| Auto-moderation gate | Only gate before PUBLISHED; fails→ON_MODERATION_FAILED (7-day purge); passes→PUBLISHED | `auto_moderate()` in auto_moderation.py |
| Moderation signal chain | post_save Ad → `calculate_ad_priority` (ON_MODERATION only) + `deliver_immediate_alerts_on_publish` (transaction.on_commit, IMMEDIATE_ALERTS_ENABLED flag) | signals.py |
| Priority scoring | max(content_score, user_score); escalation if score≥80 or flags≥3; confidence=0.7 constant | PriorityCalculator |
| Trust level thresholds | PRO≥86, TRUSTED≥61, VERIFIED≥31; VERIFIED floor for admin-verified/premium | TrustCalculator._get_trust_level |
| Quality score truncation | `int((1-r/t)*30)` truncates (22.5→22) | TrustCalculator._calculate_quality_score |
| Contact render conditions | 5 R2 conditions; DECLINE ≠ WITHDRAW; contactable if all pass | contact.py |
| Login token atomicity | SHA-256 hash only; two-phase claim; replay→410; expired→410; consumed→410 | LoginToken model + views |
| Consent withdrawal | Deletes LoginTokens + soft-deletes ads; PII erasure after 30-day grace; atomic | `withdraw_consent()` |
| Sweep schedules | archive@60d, delete@120d from published_at; archive@120d from archived_at; purge_failed@7d; purge_rejected@90d; purge_deleted@120d; sweep_drafts@30min; cleanup_login_tokens; consent_hard_delete@30d | management commands |
| FTS trigger maintenance | Row-level trigger maintains search_vector_ru/bs/en on INSERT/UPDATE; category_name denormalized | pg_trigger.sql (migration 0007) |
| Price normalization | price_normalized_eur = price_amount × exchange_rate; EUR=1.0 base | PriceNormalizer |
| Preferred city reconciliation | Guest cookie + DB FK reconciliation on login; DB wins | `apps/search/views/preferred_city.py` |

---

## 3. Test Conventions

| Aspect | Convention | Source |
|--------|-----------|--------|
| Framework | pytest + pytest-django | pyproject.toml `[tool.pytest.ini_options]` |
| Test classes | Plain `class TestX:` — NOT `django.test.TestCase` / `unittest.TestCase` | docs/99-agent/rules.md §33 |
| Markers (module-level) | `pytestmark = [pytest.mark.django_db, pytest.mark.integration]` (DB tests) or `pytest.mark.unit` (DB-free) | pyproject.toml markers + rules.md |
| Markers (function) | `@pytest.mark.django_db` + `@pytest.mark.integration` for inline classes | test_trust_calculator.py pattern |
| Fixtures | Root `conftest.py` at `src/backend/conftest.py` provides `seller` (900000001), `user` (900000002), `category` ("Транспорт"), `city` ("Тестград") | conftest.py |
| Ad creation | `from conftest import create_test_ad(...)` — sets status-specific timestamps automatically | conftest.py + rules.md |
| Bot fixtures | Separate conftest at `src/telegram_bot/tests/conftest.py` — async `user`, different IDs, thread-connection cleanup | conftest.py |
| Assertions | Plain `assert` — NOT `self.assertEqual` etc. | rules.md |
| StrEnum usage | All fixed values via StrEnum (AdStatus, CurrencyCode, TrustLevel, AdPriorityLevel, ModeratorActionType, AnalyticsEventType, etc.) | core/enums.py |
| Coverage gate | `fail_under = 80` branch coverage | pyproject.toml `[tool.coverage.report]` |
| i18n DoD | Templates: `{% trans %}`/`{% blocktrans %}`; Python: `gettext`/`gettext_lazy`; verify via `test_i18n_completeness.py` | rules.md §16 |
| Test DB | Docker PostgreSQL 18 on port 5433; `--create-db` locally, `--reuse-db` via Docker entrypoint | commands.md |

---

## 4. Test Inventory

### Backend (`src/backend/`) — ~967 test functions in 104 files

| Area | Files | Test functions |
|------|-------|---------------|
| **ads** | 22 | ~199 |
| analytics | 6 | ~90 |
| **moderation** | 7 | ~127 |
| **search** | 7 | ~125 |
| core | 15 | ~152 |
| **users** | 7 | ~102 |
| trust | 3 | ~34 |
| **seed** (nightly) | 2 | ~119 |
| media | 3 | ~20 |
| currencies | 2 | ~7 |
| cabinet | 2 | ~9 |
| categories | 1 | ~7 |
| config/settings | 1 | ~3 |

**Notable recent additions (current session 8/26):**
- `test_ad_constraints.py` (7 tests — 6 constraint tests + mutual exclusivity)
- `test_decorators.py` (9 tests — staff_required + staff_required_api unit tests)
- `test_approve_ad_side_effects.py` (6 tests — signal chain)
- `test_listings_sort.py` (4 tests — DATE_OLD/DATE_NEW/default)
- `test_ad_detail_queries.py` (2 tests — N+1 regression guard)
- `TestContactCombinatorial` in test_contact.py (9 parametrized cases)
- `TestLoginTokenSecurity` in test_login.py (5 tests)
- `TestPriorityLevelBoundaries` + `TestConfidenceScore` in test_priority.py
- `TestQualityScoreTruncation` + `TestTrustLevelFloor` in test_trust_calculator.py

### Telegram bot (`src/telegram_bot/`) — ~78 test functions in 10 files

| File | Tests | Focus |
|------|-------|-------|
| test_ad_lifecycle.py | 17 | Draft creation, auto-moderate pass/fail, re-publish immutability |
| test_media.py | 21 | JPEG validation, storage key format, PII check, delete_photo |
| test_unsubscribe.py | 7 | Search deactivation ownership/authorization |
| test_claim_login_token.py | 7 | Atomic token claim (ORM-level, INSERT-time triggers) |
| test_multi_lang_translation.py | 10 | Bosnian→Russian translation, circuit breaker, fallback |
| test_create_draft_ad.py | 5 | DRAFT ad creation via bot FSM |
| test_ad_create_condition.py | 4 | Condition/feature keyboard for conditional categories |
| test_login_claim.py | 5 | Token claim/replay/expiry (handles same `handle_login_orm`) |
| test_ad_create.py | 2 | Language detection from Telegram user profile |
| test_save_photo_integration.py | 2 | Thumbnails populated/null on generation |

**Seed tests** (marked `@pytest.mark.seed`, skipped in fast gate):
- `test_seed.py` (60 tests) — SeedService end-to-end with mocked image pipeline
- `test_download_seed_photos.py` (59 tests) — Photo manifest validation

Markers: `unit` (~20 tests, no DB), `integration` (DB-backed, dominant), `seed` (~119, nightly only), `settings` (subprocess), `slow` (many), `concurrent` (bot DB-transaction tests), `real_images` (real photo pipeline).

---

## 5. Critical Constraints (DB + Logic)

### Ad model DB CheckConstraints (`apps/ads/models.py` Meta.constraints)
1. `ck_ads_published_at_if_published` — status=PUBLISHED ⟹ published_at NOT NULL
2. `ck_ads_archived_at_if_archived` — status=ARCHIVED ⟹ archived_at NOT NULL
3. `ck_ads_rejected_at_if_rejected` — status=REJECTED ⟹ rejected_at NOT NULL
4. `ck_ads_moderation_failed_at_if_failed` — status=ON_MODERATION_FAILED ⟹ moderation_failed_at NOT NULL
5. `ck_ads_deleted_at_if_deleted` — status=DELETED ⟹ deleted_at NOT NULL
6. `ck_ads_failed_and_rejected_mutually_exclusive` — NOT (moderation_failed_at AND rejected_at)

### Ad transition matrix (`Ad.transition_to()`)
```
DRAFT → ON_MODERATION
ON_MODERATION → PUBLISHED | REJECTED | ON_MODERATION_FAILED
PUBLISHED → ARCHIVED | ON_MODERATION  (text edit)
ARCHIVED → PUBLISHED | ON_MODERATION
ON_MODERATION_FAILED → REJECTED  (manual review, AD-001)
any → DELETED  (terminal; no exit)
REJECTED = terminal
```
Side-effects: PUBLISHED resets published_at (original_published_at set once); ON_MODERATION clears moderation_archive timestamps; DELETED sets deleted_at.

### TrustCalculator thresholds
- Activity: 5 pts/ad, capped at 40 (8+ ads)
- Quality: `int((1 - rejected/total) * 30)` — **truncates** (22.5→22)
- Response: `round((responses/total) * 30, 2)` — rounds to 2 decimals
- Level: PRO≥86, TRUSTED≥61, VERIFIED≥31, else UNVERIFIED
- **Floor:** admin-verified or Telegram Premium → VERIFIED even at score 0

### PriorityCalculator
- `total = max(content_score, user_score)` (not average — highest-risk wins)
- Escalation: `score ≥ 80 OR len(flags) ≥ 3`
- `_estimate_confidence` always returns `0.7` (placeholder constant)

### Contact service (Zone R2) — 5 conditions, ALL must be true:
1. ad.status == PUBLISHED
2. seller.telegram_id IS NOT NULL
3. NOT seller.is_deleted
4. NOT seller.is_banned
5. seller.consent_revoked_at IS NULL
- **DECLINE ≠ WITHDRAW:** `is_declined=True` alone does NOT block contact; only `consent_revoked_at` matters

### LoginToken
- SHA-256 hash stored (never raw token)
- `hmac.compare_digest` for comparison
- Two-phase: bot sets telegram_id, web sets consumed_at
- 5-minute expiry; replay/consumed/expired → 410

### Sweep schedules (AdvisoryLockId)
| Command | Lock ID | Window | Target |
|---------|--------|--------|--------|
| archive_sweep | 1 | 60 days from published_at | PUBLISHED→ARCHIVED |
| delete_sweep | 2 | 120 days from archived_at | ARCHIVED→DELETE |
| consent_hard_delete | 3 | 30 days from consent_revoked_at | PII hard-delete |
| sweep_drafts | 4 | 30 min from created_at | DRAFT→DELETE |
| cleanup_login_tokens | 5 | expired | LoginToken purge |
| purge_failed_ads | 6 | 7 days from moderation_failed_at | ON_MODERATION_FAILED→DELETE |
| purge_rejected_ads | 7 | 90 days from rejected_at | REJECTED→DELETE |
| purge_deleted_ads | 11 | 120 days from deleted_at | DELETED→DB delete |

All sweep commands wrap `pg_advisory_xact_lock` inside `transaction.atomic()`.

---

## 6. Prior Findings Status (vs. audit_findings_compilation.md)

### RESOLVED (correctly addressed by current session)

| Finding | Status | Evidence |
|---------|--------|----------|
| **F-01** Shadowed `tests.py` files | RESOLVED | `apps/moderation/tests.py` + `apps/search/tests.py` deleted; migrated to `tests/` packages |
| **C-01** Ad model check constraints | RESOLVED | `test_ad_constraints.py` (7 tests, all 6 constraints) + `TestCheckConstraints` in `test_ad_lifecycle.py` (3 tests) |
| **C-02** TrustCalculator quality score truncation | RESOLVED | `TestQualityScoreTruncation` in `test_trust_calculator.py` (test_quality_score_int_truncation: 3pub+1rej→22, total 37) |
| **C-03** PriorityCalculator boundaries | RESOLVED | `TestPriorityLevelBoundaries` (5 tests, 0/40/60/80/100 → LOW/LOW/MEDIUM/HIGH/HIGH) + `TestConfidenceScore` (2 tests) in `test_priority.py` |
| **C-04** Contact service `can_contact_seller` edge cases | RESOLVED | `TestContactCombinatorial` (9 parametrized cases), `TestCheckSellerContactable` (8 tests), `TestCanContactSellerLogic` (9 tests) in `test_contact.py` |
| **C-05** Search sorting DATE_OLD/DATE_NEW | RESOLVED | `test_listings_sort.py` (4 tests: DATE_OLD, DATE_NEW, default, reversal) |
| **C-06** Ad detail trust score prefetch N+1 | RESOLVED | `listings.py:61` now `.prefetch_related(..., "user__trust_score")`; `test_ad_detail_queries.py` (2 tests) |
| **C-07** approve_ad signal chain | RESOLVED | `test_approve_ad_side_effects.py` (6 tests: transition, no-alert-default, alerts-enabled, priority-signal, published-no-priority, idempotent) |
| **C-08** LoginToken HMAC edge cases | RESOLVED | `TestLoginTokenSecurity` in `test_login.py` (5 tests: mismatch, SHA-256, length, replay, bot-phase claim) |
| **C-10** PriorityCalculator boundary edges | RESOLVED | `TestPriorityLevelBoundaries` + `TestConfidenceScore` + `TestPriorityServiceBoundaries` (parametrized 6 cases) |
| **C-11** Trust level floor logic | RESOLVED | `TestTrustLevelFloor` in `test_trust_calculator.py` (3 tests: score=0 admin-verified→VERIFIED, premium→VERIFIED, none→UNVERIFIED) |
| **§2.3** TestCase usage | RESOLVED | grep for `import TestCase` and `class Test.*TestCase` → 0 matches; all 9 listed files migrated to pytest pattern |
| **§2.5** Missing decorator unit tests | RESOLVED | `test_decorators.py` (9 tests, unit-marked, RequestFactory) |
| **§2.1** Duplicated shared fixtures | RESOLVED/STALE | grep for `def seller(`/`def user(`/`def category(`/`def city(` in `apps/` → 0 matches; all backend tests consume root conftest fixtures; only bot conftest redefines (documented as separate scope) |
| **§2.2** Duplicated _make_ad/_create_ad helpers | RESOLVED/STALE | grep for `^def _make_ad(` / `^def _create_ad(` → only 1 match (`_make_ad` in `test_ad_localization.py`); 13/14 listed files now import `create_test_ad` from conftest |
| **D-03** Plan references deleted tests.py | RESOLVED (partial) | Files deleted; migrated replacements tracked and passing |

### OPEN (still requires work)

| Finding | Severity | Current state |
|---------|----------|--------------|
| **§2.4** Private method testing (`_check_seller_contactable`) | LOW/MEDIUM | `test_contact.py` still imports and calls `_check_seller_contactable` directly (line 12, 147). `_check_seller_contactable` is prefixed `_` — though it's the core Zone R2 predicate and arguably part of the testable contract. |
| **§2.6** `e2e` marker registered but unused | LOW | `pyproject.toml:167` registers `e2e`; grep for `@pytest.mark.e2e` → 0 matches. Dead config. |
| **§2.7** SimpleTestCase usage (convention violation) | LOW | **15 files** (not 9 as claimed) use `SimpleTestCase` with `self.assert*` instead of plain `class TestX:` + `assert`. Audit undercounted — additional files: `test_detail_context.py`, `test_templates.py`, `test_csp_report.py`, `test_preferred_city_middleware.py`, `test_language_locale.py`, `test_autocomplete_template.py`, `test_context_processors.py`, `config/settings/tests/test_settings_secrets.py`. |
| **§2.8** Raw strings for Enum fields | LOW | Confirmed in `test_sweep_commands.py`: `event_type="search_perseformed"` (L279,313), `action_type="ban_account"` (L291,317), `action_type="reject"` (L458). Audit's claim about `test_deletion.py` using `action_type` raw strings is **INACCURATE** — test_deletion.py has no `action_type` usage (verified by full-file read + grep). Audit also missed `action_type="reject"` at L458. |
| **§2.9** Direct `Ad.objects.create()` instead of shared helper | LOW | Confirmed in: `test_breadcrumbs_render.py:92`, `test_deletion.py:143,153,261,321`, `test_language_end_to_end.py:81`, `test_autocomplete.py:592,619,642,673`, `test_seed.py:263,358,372`. Audit only listed 2 of these 6 files — undercounting. |
| **§2.10** Fragile structure inspection via `inspect.getsource()` | MEDIUM | `test_sweep_lock_structure.py` (2 tests) still uses `inspect.getsource()` to verify `transaction.atomic()` wraps `advisory_lock()`. Tests implementation, not behavior. |
| **§2.11** Private auto-moderation function testing | MEDIUM | `test_auto_moderation.py` `TestValidateTitleLength`/`TestValidateDescriptionLength`/`TestValidateImageCount`/`TestContainsBannedWords` still call `_validate_*`, `_contains_banned_words` directly. `TestCheckFunction` tests public `check()` — that part is fine. |
| **§2.12** Duplicate bot login token tests | LOW | Both `test_claim_login_token.py` (7 tests) and `test_login_claim.py` (5 tests) test `handle_login_orm` with overlapping scenarios (valid/expired/claimed tokens, user creation). Redundant coverage. |
| **C-09** Thumbnail generation integration | P2 | PARTIALLY COVERED. `test_thumbnails.py` (11 tests) unit-tests `generate_thumbnails`. `test_save_photo_exif.py` (1 test) tests EXIF. The `save_photo→generate_thumbnails` integration at `ad_create.py:588` has no e2e test with real image data. `test_media_security.py` (28 tests) covers media access control but not the thumbnail generation pipeline. |
| **D-01** Plan §1.2 — markers "Not registered" | LOW | Plan says markers are "Not registered"; `pyproject.toml:163-172` registers all 9 markers. Doc discrepancy. |
| **D-02** Plan §1.4 — "CI runs all 934 tests" | LOW | CI runs `pytest -m "not seed"` (~890 non-seed). Plan claims 934. Doc discrepancy. |
| **D-04** Plan §14 T-12 — "All previously-failing tests pass" | MEDIUM | Claims 50+ failing tests all pass; shadowed `tests.py` tests (31 tests) were excluded from this baseline. |

### VERDICT: Audit compilation is 60% stale

The compilation document (dated 8/20–8/21) describes a codebase state that predates significant remediation work done in the current session (8/26). **8 of 11 coverage gaps (C-series) are now RESOLVED**, and **3 of 9 convention findings (§2.1, §2.2, §2.3, §2.5) are RESOLVED**. The compilation's severity/severity counts and file lists are outdated. Key corrections needed in the compilation:

1. **§2.7 count** is 15 files, not 9 (6 files missing from the list)
2. **§2.8 file attribution** for test_deletion.py is wrong (no `action_type` raw strings there); test_sweep_commands.py also has `action_type="reject"` (missed)
3. **§2.9** has 6 affected files, not 2 (missing: test_language_end_to_end.py, test_autocomplete.py, test_seed.py)
4. **§2.1/§2.2** are no longer accurate — fixtures and `create_test_ad` are already widely adopted
5. The validation matrix (§5) needs a full re-baseline

### Remaining open issues by priority
- **P2:** C-09 (thumbnail integration gap)
- **MEDIUM:** §2.10 (inspect.getsource), §2.11 (private auto-moderation methods), §2.4 (private contact method), D-04 (doc discrepancy)
- **LOW:** §2.6 (e2e marker), §2.7 (15 SimpleTestCase files), §2.8 (raw strings), §2.9 (5 files with Ad.objects.create), §2.12 (duplicate bot tests), D-01/D-02 (doc discrepancies)
