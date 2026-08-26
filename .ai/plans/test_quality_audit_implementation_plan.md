# Test Quality Audit — Implementation Plan (Corrected & Supplemented)

**Source:** Step 2 audit report + Step 1 research report + Step 1 current-state + findings compilation
**Last updated:** 2026-08-26
**Scope:** Test-quality improvements only. No production source / config / schema changes introduced by the work below.

---

## 0. Resolved findings (do not re-implement)

These findings were confirmed RESOLVED by the Step 2 runtime audit. They are listed here to prevent re-work.

| Finding | Severity | Verified by | Evidence |
|---|---|---|---|
| F-01 — Shadowed `tests.py` files | CRITICAL | Runtime + git history | `apps/moderation/tests.py` + `apps/search/tests.py` deleted; migrated to `tests/` packages with fixed timestamp helpers |
| §2.1 — Duplicated shared fixtures | MEDIUM | Static grep | 0 `def seller`/`def user`/`def category`/`def city` redefinitions in `apps/`; only bot conftest redefines (documented separate scope) |
| §2.2 — Duplicated `_make_ad`/`_create_ad` helpers | MEDIUM | Static grep | 13/14 listed files migrated to `create_test_ad`; 1 residual remains (`test_ad_localization.py:19`) — see §2.2 residual task |
| §2.3 — `django.test.TestCase` usage | LOW | Static grep | 0 `import TestCase` / `class Test.*TestCase` matches across `src/` |
| §2.5 — Missing decorator unit tests | LOW | Runtime | `test_decorators.py` (9 tests) passes |
| §2.6 — `e2e` marker registered but unused | LOW | Static grep | `e2e` marker absent from `pyproject.toml`; 0 `@pytest.mark.e2e` usages — already removed |
| C-01 — Ad check constraints | P0 | Runtime | `test_ad_constraints.py` + `TestCheckConstraints` pass |
| C-02 — TrustCalculator quality truncation | P0 | Runtime | `TestQualityScoreTruncation` passes |
| C-03 — PriorityCalculator boundaries | P0 | Runtime | `TestPriorityLevelBoundaries` + `TestConfidenceScore` pass |
| C-04 — Contact edge cases | P1 | Runtime | `TestContactCombinatorial` + `TestCheckSellerContactable` pass |
| C-05 — Search DATE_OLD/DATE_NEW sorting | P1 | Runtime | `test_listings_sort.py` passes |
| C-06 — Ad detail trust-score prefetch N+1 | P1 | Runtime | `listings.py` prefetch added; `test_ad_detail_queries.py` passes |
| C-07 — approve_ad signal chain | P1 | Runtime | `test_approve_ad_side_effects.py` (6 tests) passes |
| C-08 — LoginToken HMAC edge cases | P2 | Runtime | `TestLoginTokenSecurity` in `test_login.py` (5 tests) passes |
| C-10 — Moderation priority boundary edges | P2 | Runtime | `TestPriorityLevelBoundaries` + `TestConfidenceScore` in `test_priority.py` passes |
| C-11 — Trust level floor logic | P2 | Runtime | `TestTrustLevelFloor` in `test_trust_calculator.py` (3 tests) passes |
| D-03 — Plan §1.1 references deleted `tests.py` | LOW | Git history | Files deleted; migrated replacements tracked |

---

## 1. Grounded facts (verified)

Public APIs to prefer over internals:
- **Auto-moderation** — `apps/moderation/services/auto_moderation.py`
  - `auto_moderate(ad: Ad) -> bool` (L92) — runs all validations, transitions `Ad` to `ON_MODERATION_FAILED` or `PUBLISHED`
  - `check(ad: Ad) -> tuple[bool, str | None]` (L264) — read-only pre-submission validation
  - ⚠️ There is **no** `moderate()` function/method — `AutoModerator` is not a class. (Decision gate D-01 resolves the §2.11 ambiguity.)
- **Sweep commands** — management commands invoked via `call_command()`. No standalone `sweep_moderation_queue()` or `run_sweep()` function exists. Each command is `apps/<app>/management/commands/<name>.py::Command.handle`, wrapping `with transaction.atomic(): with advisory_lock(AdvisoryLockId.<ID>):`. (Corrects the T210 spec which previously cited a non-existent function.)
- **Ad contact** — `apps/core/services/contact.py`
  - `can_contact_seller(ad: Ad) -> bool` (L48)
  - `get_seller_for_contact(ad_id: int) -> tuple[bool, User | None]` (L71)
  - `_check_seller_contactable(ad, seller) -> bool` (L27, **private**) — core Zone R2 predicate

Canonical enums (use members, never raw strings — rule 10):
- `apps/core/enums.py` — `AdStatus` (DRAFT/ON_MODERATION/PUBLISHED/REJECTED/ON_MODERATION_FAILED/ARCHIVED/DELETED); `ModeratorActionType` (REJECT/BAN_ACCOUNT/SOFT_DELETE/CRITERIA_CHANGE/OTHER); `AnalyticsEventType` (SEARCH_PERFORMED, AD_PUBLISHED, CONTACT_INITIATED, MODERATION_APPROVED, …); `LanguageLocale` (RUSSIAN=`"ru"`, …); `ThumbnailSizeStrEnum` (SMALL/MEDIUM/LARGE); `AdSource` (SEED/WEB/BOT, …)
- `apps/currencies/enums.py` — `CurrencyCode` (EUR/RSD/BAM)
- `apps/moderation/enums.py` — `BulkModerationAction` StrEnum (APPROVE/REJECT/FLAG)

Models / fixtures:
- `ExchangeRate` (`apps/currencies/models.py`) — `currency` (CharField, unique), `rate_to_eur`, `effective_date`, `source`, `is_current=True`. Seeded by `currencies/migrations/0001_initial.py::seed_initial_rates` (EUR=1.0, BAM=0.512, RSD=0.0105).
- `save_photo` — `telegram_bot/handlers/ad_create.py:961` (`async def save_photo(storage_key: str, photo_bytes: bytes) -> str` — takes raw bytes, no Bot fetch); `ThumbnailService.generate_thumbnails` — `apps/media/services/thumbnails.py:40`; photo→thumbnail chain — `ad_create.py:1162-1201`.
- `ThumbnailSizeStrEnum` defined in `apps/core/enums.py` (L85), not in `apps/media/`. `thumbnail_small/medium/large` CharFields live on `AdImage` (`apps/ads/models.py` L534-551).

Environment / conventions:
- `python_files = ["tests.py", "test_*.py"]`; markers live in `[tool.pytest.ini_options]` of `pyproject.toml` (all 8 now registered: `unit`, `integration`, `seed`, `settings`, `concurrent`, `slow`, `real_images`, `xdist_group`; `e2e` was removed).
- `make test` = fast gate (skips `seed` marker). `make test-all` = full ~35 min. `make test-recreate` = fresh schema.
- Bot tests live under `src/telegram_bot/tests/` with their **own** `conftest.py`; they **cannot** resolve backend root conftest fixtures (`create_test_ad`, `seller`, …) — bot tests must construct their own rows / use async style.
- Root test DB is the Docker `mko-bazuna-test-db` (port 5433). Run tests via the `test` Compose service, not `uv run pytest` locally.
- This plan is **not** the old perf/strategy audit `.ai/plans/done/25_test-optimization-plan_done.md` — D-01/D-02/D-04 correct that stale document, not this plan.

---

## 2. Priority groupings

Priority = (1) correctness / regression risk → (2) business importance → (3) test-quality impact → (4) effort.

### P0 — Core logic, high regression / business risk
| ID | Task | Root cause |
|----|------|-----------|
| §2.10 | Rewrite `test_sweep_lock_structure.py` away from `inspect.getsource()` | Brittle introspection; tests locking/transaction behavior (core sweep infrastructure). |
| §2.11 | Rewrite `test_auto_moderation.py` to call public `check()`/`auto_moderate()` | Internals-coupled tests; moderation is buyer/seller-facing business logic. |

### P1 — Correctness, fixture consistency, wide blast radius
| ID | Task | Root cause |
|----|------|-----------|
| §2.9 | Replace direct `Ad.objects.create()` with `create_test_ad(...)` in 5 files | Inconsistent ad fixtures; bypasses auto timestamping/status invariants. |
| §2.8 | Replace raw enum strings with `StrEnum` members in 5 files | Violates project rule 10; fragile stringly-typed assertions. |
| §2.4 | Rewrite `TestCheckSellerContactable` to validate through public API | Tests private `_check_seller_contactable`; convention violation. |
| §2.12 + NEW-2 | Consolidate bot login tests (overlap removal) + verify xdist-free pass | Duplicate coverage across 2 files; static `token_hash` fixture (NEW-6) causes isolation failure without xdist. |
| NEW-6 | Fix fixed `token_hash` fixture (unique per test) | Static `hashlib.sha256("a"*32)` fixture causes duplicate-key deadlocks when cleanup fails. |
| NEW-1 | Add `ExchangeRate` fixtures for currency tests | Currency tests rely on migration-seeded rows; fragile under `--reuse-db`. |

### P2 — Test quality / best-practice / docs, low risk
| ID | Task | Root cause |
|----|------|-----------|
| §2.7 | Convert 15 `SimpleTestCase` files → plain pytest classes + `assert` | Inconsistent base-class mix; `unittest` assert style in a pytest project. |
| NEW-4 | Fix `MagicMock` cache-key leaks in 2 files | Mocked cache hides key-construction; tests don't assert cache keys. |
| NEW-5 | Widen `_load_catalog` fixture scope (function → class) | Re-parses category YAML for every test (~3.6s setup each). |
| C-09 | Add `save_photo → ThumbnailService.generate_thumbnails` integration test | Test gap: photo→thumbnail chain unverified end-to-end. |
| §2.2 res | Assess `_make_ad` in `test_ad_localization.py` | 1 of 14 files not migrated to `create_test_ad`; in-memory helper may be intentional. |
| D-01 | Fix doc §1.2: markers "Not registered" → registered | Stale doc in `25_test-optimization-plan_done.md`. |
| D-02 | Fix doc §1.4: "CI runs all 934 tests" → runs `-m "not seed"` | Stale CI command in old plan doc. |
| D-04 | Fix doc §14 T-12: clarify shadowed `tests.py` exclusion | Old plan claims 50+ previously-failing tests pass; shadowed tests were excluded from baseline. |
| NEW-7 | Fix `test_media_security.py` doc path (`apps/ads/tests/` vs `apps/media/tests/`) | Stale doc references in compilation + audit report. |

---

## 3. Per-finding task specs

### T210 — §2.10 Rewrite `test_sweep_lock_structure.py`
- **Target:** `apps/core/tests/test_sweep_lock_structure.py`
- **Current approach:** 2 tests use `inspect.getsource(Command.handle)` to assert `"transaction.atomic"` appears before `"advisory_lock"` in source text for 11 command modules.
- **Rewrite:** Remove all `import inspect` / `getsource` usage. Test via `call_command()`:
  - **Positive-path (parametrized):** create an `Ad` past the archive threshold (PUBLISHED + `published_at` 61 days ago), run `call_command("archive_sweep")`, assert `Ad.status == ARCHIVED`.
  - **Lock/spy:** use a spy/mock on `apps.core.utils.advisory_lock.advisory_lock` to verify it is called inside `transaction.atomic()` — instead of inspecting source text. Assert the lock function is invoked with the correct `AdvisoryLockId` enum member.
  - **Scope guard:** keep one parametrized positive-path (covers all 11 sweep commands via table-driven parametrization) + one lock-ordering spy test.
- **Modules under test:** `archive_sweep`, `delete_sweep`, `consent_hard_delete`, `cleanup_login_tokens`, `sweep_drafts`, `purge_failed_ads`, `purge_rejected_ads`, `purge_deleted_ads`, `rollup_daily_metrics`, `backfill_thumbnails`, `send_alerts`.
- **Risk:** low — tests only. **Validation:** `pytest apps/core/tests/test_sweep_lock_structure.py` in isolation.

### T211 — §2.11 Rewrite `test_auto_moderation.py` (D-01)
- **Target:** `apps/moderation/tests/test_auto_moderation.py`
- **Decision gate D-01 (resolved):** the public API is `auto_moderate(ad) -> bool` and `check(ad) -> tuple[bool, str | None]`. Substitute `moderate()`→`auto_moderate()` everywhere in the spec.
- **Rewrite goal:** 
  - `TestCheckFunction` tests `check()` (public) — keep, strengthen assertions on the `(bool, str|None)` return tuple.
  - `TestValidateTitleLength` / `TestValidateDescriptionLength` / `TestValidateImageCount` / `TestContainsBannedWords` — rewrite to feed crafted `Ad` rows through `check()` / `auto_moderate()` and assert on the return value or resulting `Ad.status` (`ON_MODERATION_FAILED`). Drop direct calls to `_validate_*` / `_contains_banned_words`.
  - `TestCheckFunction.test_failed_ad_not_counted_in_active_limit` — calls `_validate_max_ads_per_user` directly; rewrite to drive `check()` with an over-limit user and assert `False` return.
- **Side effects to assert:** `Ad.status` transitions, `AnalyticsEvent` rows (MODERATION_REJECTED / AD_PUBLISHED / MODERATION_APPROVED).
- **Risk:** medium (moderation correctness). **Validation:** `pytest apps/moderation/tests/test_auto_moderation.py`.

### T29 — §2.9 `create_test_ad` adoption (5 files)
- **Files:** `apps/ads/tests/test_breadcrumbs_render.py`, `apps/users/tests/test_deletion.py`, `apps/core/tests/test_language_end_to_end.py`, `apps/seed/tests/test_seed.py`, `apps/search/tests/test_autocomplete.py`.
- **Action:** replace every `Ad.objects.create(...)` with `create_test_ad(..., status=AdStatus.*)` (from `src/backend/conftest.py`), passing the appropriate `AdStatus` enum member; let the helper set status-specific timestamps via `_set_status_timestamp`.
- **Price currency:** `create_test_ad` should accept and propagate `price_currency=CurrencyCode.*` (verify the helper supports it or extend it).
- **Exceptions to document:**
  - `test_deletion.py` — may intentionally construct rows with deliberate timestamp states; preserve raw `Ad.objects.create()` only where the test explicitly tests invariant bypassing; annotate each exception with a comment.
  - `test_seed.py` — `_setup_class` helpers create ads with raw `published_at="2024-01-01..."`; migrate to `create_test_ad` and let it set timestamps.
- **Risk:** medium. **Validation:** `pytest` each file in the fast gate subset.

### T28 — §2.8 Enum-string replacement (5 files)
- **Files + mappings:**

  | File | Location | Raw string | Replacement enum |
  |------|----------|-----------|------------------|
  | `apps/core/tests/test_sweep_commands.py` | L279, L313 | `"search_performed"` | `AnalyticsEventType.SEARCH_PERFORMED` |
  | `apps/core/tests/test_sweep_commands.py` | L292, L317 | `"ban_account"` | `ModeratorActionType.BAN_ACCOUNT` |
  | `apps/core/tests/test_sweep_commands.py` | L458 | `"reject"` | `ModeratorActionType.REJECT` |
  | `apps/seed/tests/test_seed.py` | L275, L370, L384 | `"EUR"` | `CurrencyCode.EUR` |
  | `apps/seed/tests/test_seed.py` | L1252, L1310 | `ad.price_currency == "EUR"` | `CurrencyCode.EUR` |
  | `apps/seed/tests/test_seed.py` | L838, L854 | `"ru"` | `LanguageLocale.RUSSIAN` |
  | `apps/ads/tests/test_breadcrumbs_render.py` | L97 | `"EUR"` | `CurrencyCode.EUR` |
  | `apps/core/tests/test_language_end_to_end.py` | L93 | `"EUR"` | `CurrencyCode.EUR` |
  | `apps/ads/tests/test_price_format.py` | L42 | `"BAM"` | `CurrencyCode.BAM` |

- **Sequencing:** T29 should run first for `test_seed.py`, `test_breadcrumbs_render.py`, `test_language_end_to_end.py` — since T29 replaces `Ad.objects.create(...)` with `create_test_ad(...)`, the embedded `price_currency="EUR"` strings are consumed by the refactor. T28 then only handles: `test_sweep_commands.py` (all 5 raw strings), `test_price_format.py` (1 raw string), and `test_seed.py` L1252/L1310/L838/L854 (assertion comparisons + LanguageLocale strings outside any `Ad.objects.create`).
- **Risk:** very low (values identical). **Validation:** `pytest` touched modules after both T28 + T29.

### T24 — §2.4 Rewrite `TestCheckSellerContactable` to validate through public API
- **Target:** `apps/core/tests/test_contact.py`
- **Current:** `TestCheckSellerContactable` (8 tests) calls the private `_check_seller_contactable(ad, seller)` directly; imports it at module level (L12).
- **Rewrite:** Replace direct calls to `_check_seller_contactable` with the public `can_contact_seller(ad)` and `get_seller_for_contact(ad.id)`. Each of the 8 branch scenarios should be driven through the public API and assert on its `bool` return (or `(bool, User|None)` tuple for `get_seller_for_contact`). Remove the `_check_seller_contactable` import.
- **Decision gate D-03:** Before removing private-method tests, confirm the public API (`can_contact_seller`, `get_seller_for_contact`) retains coverage of the same 8 branches via `TestContactCombinatorial` (9 parametrized cases) + the rewritten `TestCheckSellerContactable`. If any branch is lost, add an equivalent public-API assertion.
- **Risk:** low. **Validation:** `pytest apps/core/tests/test_contact.py`.

### T_NEW6 — NEW-6 Fix fixed `token_hash` fixture in `test_login_claim.py`
- **Target:** `src/telegram_bot/tests/test_login_claim.py` (L27-30) + `src/telegram_bot/tests/conftest.py` (`login_token_factory` fixture at L117).
- **Current:** `test_login_claim.py` defines `token_hash = hashlib.sha256("a" * 32).hexdigest()` — a single fixed hash reused across all 5 tests. When DB cleanup deadlocks (NEW-2), the fixed hash causes `IntegrityError: duplicate key` on the next test.
- **Fix:** Replace the fixed `token_hash` fixture with a per-test unique raw token (via `secrets.token_urlsafe(32)` or parametrized), re-deriving the SHA-256 hash each test. Pattern already exists in `conftest.py`'s `login_token_factory` (uses `secrets.token_urlsafe()`). Unify on the factory pattern; remove the fixed `token_hash` fixture.
- **Dependency:** Prerequisite for T_BOT (§2.12) — must fix isolation before consolidating.
- **Risk:** low. **Validation:** `pytest src/telegram_bot/tests/test_login_claim.py -p no:xdist` (must pass without xdist after fix).

### T_BOT — §2.12 + NEW-2 Consolidate bot login tests
- **Targets:** `src/telegram_bot/tests/test_claim_login_token.py`, `src/telegram_bot/tests/test_login_claim.py`, `src/telegram_bot/tests/conftest.py`.
- **Decision gate D-05:** Confirm overlap between the two files. The Step 2 report found 3 overlapping scenarios (token claim, expired rejection, consumed/claim replay). Merge the overlapping cases into a single file; keep distinct concerns (ISSUANCE via `test_claim_login_token.py`, CLAIM LIFECYCLE via `test_login_claim.py`) separate. Remove exact-duplicate test functions.
- **Constraint:** Bot tests have their **own** conftest and cannot import backend root fixtures — do not move shared fixtures to the backend root.
- **Risk:** low–medium. **Validation:** `pytest` over bot login test files with and without xdist (`pytest -p no:xdist`).

### T_ER — NEW-1 ExchangeRate fixtures for currency tests
- **Targets:** `apps/currencies/tests/test_recompute_command.py`, `apps/currencies/tests/test_price_normalizer.py`.
- **Action:** Create `apps/currencies/tests/conftest.py` with an `exchange_rates` fixture (autouse or explicit) that seeds `ExchangeRate.objects.create(currency=CurrencyCode.EUR, rate_to_eur=Decimal("1.0"), is_current=True)`, `CurrencyCode.BAM` (rate 0.512), `CurrencyCode.RSD` (rate 0.0105). Price-normalizer tests use this fixture instead of relying on migration seed data.
- **Risk:** low. **Validation:** `pytest apps/currencies/tests/` with both `--reuse-db` and `--create-db`.

### T27 — §2.7 SimpleTestCase → pytest (15 files)
- **Files:**
  1. `config/settings/tests/test_settings_secrets.py`
  2. `apps/ads/tests/test_adimage_thumbnail_urls.py`
  3. `apps/ads/tests/test_ad_localization.py`
  4. `apps/ads/tests/test_detail_context.py` ← also touched by NEW-4
  5. `apps/ads/tests/test_i18n_pipeline.py`
  6. `apps/ads/tests/test_i18n_completeness.py`
  7. `apps/ads/tests/test_listings_context.py` ← also touched by NEW-4
  8. `apps/trust/tests/test_trust_prefetch.py`
  9. `apps/core/tests/test_context_processors.py`
  10. `apps/core/tests/test_language_locale.py`
  11. `apps/core/tests/test_csp_report.py`
  12. `apps/core/tests/test_language_middleware.py`
  13. `apps/core/tests/test_preferred_city_middleware.py`
  14. `apps/core/tests/test_templates.py`
  15. `apps/search/tests/test_autocomplete_template.py`
- **Mechanical step per file:** drop `SimpleTestCase` import + base class, use plain `class TestX:`; replace `self.assertEqual`/`assertTrue`/`assertIn`/`assertSetEqual`/`assertNumQueries` with `assert`; convert `setUp`/`tearDown` to fixtures if they touch shared state. Add `pytestmark = [pytest.mark.unit]` if the file has no DB access and lacks any marker.
- **Order vs NEW-4:** T_NEW4 first for files #4 and #7 so the cache-mock fix lands before the class-conversion rewrite.
- **Risk:** low (style only). **Validation:** `make test` fast gate over `apps/ads`, `apps/core`, `apps/trust`, `apps/search`, `config/settings`.

### T_NEW4 — NEW-4 MagicMock cache-key leak fix
- **Targets:** `apps/ads/tests/test_listings_context.py`, `apps/ads/tests/test_detail_context.py`.
- **Root cause:** `test_listings_context.py` patches `apps.ads.views.listings.Category` with a `MagicMock`; `test_detail_context.py` passes `MagicMock` ad objects (L72, L111, L122). The mock's `repr`/`str` leaks into cache keys produced by view code that caches by object identity.
- **Fix:** Replace `MagicMock` cache backends with a real `locmem` cache via `override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})`, and assert the produced cache-key shape (prefix + identifier) via `assert cache.get(key)` or a thin recording spy. Where a `MagicMock` was standing in for a model, replace with a real model instance via `create_test_ad`.
- **Dependency:** Must precede the §2.7 conversion of these two files (T27).
- **Risk:** low. **Validation:** `pytest apps/ads/tests/test_listings_context.py apps/ads/tests/test_detail_context.py -W error::DeprecationWarning` (catch regressions on warnings).

### T_LOAD — NEW-5 `_load_catalog` fixture scope
- **Target:** `apps/ads/tests/test_breadcrumbs_render.py:45` (`@pytest.fixture(autouse=True) def _load_catalog()`).
- **Current:** function scope — calls `load_catalog()` + `City.objects.create()` for every test (~3.6s each, 4 of top 7 slowest setups).
- **Action:** set `scope="class"`. **Decision gate D-04:** session scope is not attempted — `City.objects.create()` is called inside the fixture body and would leak rows across test classes; `scope="class"` keeps teardown per-class and is safe.
- **Note:** `test_breadcrumbs_render.py` is NOT in the §2.7 list — no conversion conflict.
- **Risk:** low. **Validation:** `pytest apps/ads/tests/test_breadcrumbs_render.py --durations=10` (setup time should drop from ~3.6s to <0.1s per test).

### T_C09 — C-09 `save_photo → ThumbnailService.generate_thumbnails` integration test
- **Targets:** `telegram_bot/handlers/ad_create.py:961` (`save_photo`), `apps/media/services/thumbnails.py:40` (`ThumbnailService.generate_thumbnails`), chain in `ad_create.py:1162-1201`; assert `AdImage.thumbnail_small/medium/large` populated for every `ThumbnailSizeStrEnum` member.
- **Placement:** `apps/media/tests/test_thumbnail_integration.py` (new file). `save_photo` is `async def` taking `photo_bytes` directly (no Bot fetch needed). Use a real test JPEG (with EXIF) written to a `tmp_path` or `MEDIA_ROOT` override.
- **Test flow:**
  1. Build a small JPEG with EXIF via Pillow (in-memory `BytesIO`).
  2. `await save_photo(storage_key, jpeg_bytes)` → assert file exists on disk at `MEDIA_ROOT/storage_key`, EXIF stripped.
  3. `ThumbnailService(settings.MEDIA_ROOT).generate_thumbnails(jpeg_bytes, storage_key)` → assert 3 thumbnail files exist (`-small.jpg`, `-medium.jpg`, `-large.jpg`).
  4. Create `AdImage` via `AdImage.objects.create(storage_key=storage_key, thumbnail_small=..., ...)`.
  5. Assert `AdImage.thumbnail_small_url` etc. resolve to correct URLs.
- **Dependency:** `ThumbnailService`, `ThumbnailSizeStrEnum`, `AdImage` model.
- **Risk:** low (new test only). **Validation:** `pytest apps/media/tests/test_thumbnail_integration.py`.

### T_RESIDUAL_22 — §2.2 residual: assess `_make_ad` in `test_ad_localization.py`
- **Target:** `apps/ads/tests/test_ad_localization.py:19` (`def _make_ad(**kwargs) -> Ad`).
- **Context:** §2.2 is 93% resolved (13/14 files migrated to `create_test_ad`). This 1 residual uses `_make_ad` to create **in-memory** `Ad` instances via `Ad.__new__(Ad)` — no DB save. `create_test_ad` is DB-backed (`Ad.objects.create`).
- **Decision gate D-06:** Since these are pure-unit tests of `Ad.get_title(locale)` / `Ad.get_description(locale)` (no DB access, `pytestmark = [pytest.mark.unit]`), `create_test_ad` is not a drop-in replacement. Decision: simplify `_make_ad` to `Ad(**fields)` (equivalent, more idiomatic) OR keep `Ad.__new__` pattern with a docstring explaining the in-memory rationale. Do NOT introduce DB access.
- **Risk:** very low. **Validation:** `pytest apps/ads/tests/test_ad_localization.py`.

### T_DOC_MARKERS — D-01 Fix stale doc §1.2 (markers "Not registered")
- **Target:** `.ai/plans/done/25_test-optimization-plan_done.md` §1.2 (lines 40-44).
- **Current:** claims `unit`, `e2e`, `seed`, `settings`, `concurrent` are "Not registered."
  - **Fix:** Update §1.2 marker table to reflect current `pyproject.toml` — all 8 custom markers are now registered (`unit`, `integration`, `seed`, `settings`, `concurrent`, `slow`, `real_images`, `xdist_group`); `e2e` was removed. The old doc's claim of "Not registered" for `unit`/`seed`/`settings`/`concurrent` is stale; `e2e` should be removed from the table entirely. Cross-reference actual marker count (8, not the 5 "Not registered" in the old doc).
- **Risk:** none (doc-only). **No test run required.**

### T_DOC_CI — D-02 Fix stale doc §1.4 ("CI runs all 934 tests")
- **Target:** `.ai/plans/done/25_test-optimization-plan_done.md` §1.4 (lines 65-80, esp. L70 and L75).
- **Current:** claims CI test job runs all 934 tests sequentially.
- **Fix:** Update to reflect CI uses `-m "not seed"` (excludes ~8 seed-marked tests; ~890 non-seed tests collected) with `-n auto --dist loadgroup + --cov`. Note `25_test-optimization-plan_done.md` is in `.ai/plans/done/` — update the stale count.
- **Risk:** none (doc-only). **No test run required.**

### T_DOC_T12 — D-04 Fix stale doc §14 T-12 ("All previously-failing tests pass")
- **Target:** `.ai/plans/done/25_test-optimization-plan_done.md` §14 T-12 (lines 704-715).
- **Current:** claims "934 tests collected, 0 failures" and "Previously-failing tests (50+) — All now pass ✅."
- **Fix:** Add a note clarifying that the baseline excluded the 31 shadowed `tests.py` tests (deleted in F-01); the 1 real pre-existing failure (`test_reject_failed_moderation_ad`) was a test-helper bug (missing timestamp for non-PUBLISHED statuses), not a production-code bug. Update the count to reflect current test inventory (~1091 total, ~890 non-seed).
- **Risk:** none (doc-only). **No test run required.**

### T_DOC_PATH — NEW-7 Fix `test_media_security.py` doc path
- **Targets:** `.ai/problems/audit_findings_compilation.md:153`, `.ai/audit/tests/audit_report_1.md:69`.
- **Fix:** `apps/media/tests/test_media_security.py` → actual location is `apps/ads/tests/test_media_security.py`. Sync both doc refs.
- **Risk:** none (doc-only). **No test run required.**

---

## 4. Implementation order (dependency DAG)

```
Phase 1 (P0) — parallel, independent, no shared files
  ├─ T210  §2.10    (sweep_lock rewrite)
  └─ T211  §2.11    (auto_moderation rewrite)          [D-01 resolved]
  Gate G-P0: run moderation test subset (see §5)

Phase 2 (P1) — parallel, independent files
  ├─ T29   §2.9     (create_test_ad adoption)           ─┐
  ├─ T28   §2.8     (enum-string replacement)            │  T28 waits on T29 for shared files
  ├─ T24   §2.4     (rewrite to public API)              │  (price_currency strings consumed by T29)
  ├─ T_NEW6 NEW-6   (fix token_hash fixture)            ─┘→ T_BOT
  ├─ T_BOT  §2.12   (bot login consolidation)            ↗   [D-05]
  └─ T_ER   NEW-1   (ExchangeRate fixtures)
  Gate G-P1: targeted runs per finding

Phase 3 (P2) — order matters for shared files
  ├─ T_NEW4  NEW-4  (cache-mock fix) ─┐ blocks §2.7 on files #4/#7
  ├─ T27     §2.7   (SimpleTestCase x15) ┘
  ├─ T_LOAD  NEW-5  (_load_catalog scope)
  ├─ T_C09   C-09   (thumbnails integration test)
  ├─ T_RESIDUAL_22 §2.2-res (assess _make_ad)
  └─ T_DOC_PATH, T_DOC_MARKERS, T_DOC_CI, T_DOC_T12 (doc-only, no run)
  Gate G-P2: full `make test` fast gate
```

Detailed dependencies:

| Task | Blocked by | Blocks | Notes |
|------|-----------|--------|-------|
| T210 | — | G-P0 | No DB needed (currently `unit`-marked) |
| T211 | D-01 | G-P0 | D-01 resolved: use `auto_moderate()` + `check()` |
| T29 | — | T28 (shared files) | Replaces `Ad.objects.create` → `create_test_ad`, consuming embedded `price_currency` raw strings |
| T28 | T29 (for shared files) | G-P1 | Runs on all 5 files, but shared files' `Ad.objects.create` edits should be sequenced after T29 |
| T24 | D-03 | G-P1 | D-03 gate: verify public API coverage retained before removing private tests |
| T_NEW6 | — | T_BOT | Must fix fixture isolation before consolidation |
| T_BOT | T_NEW6, D-05 | G-P1 | D-05 gate: confirm overlap before merging |
| T_ER | — | G-P1 | Create `conftest.py` + fixture; tests use it |
| T_NEW4 | — | T27 (files #4/#7) | Fix cache-mocks before class-conversion for those 2 files |
| T27 | T_NEW4 (files #4/#7) | G-P2 | 13 of 15 files independent; 2 blocked by T_NEW4 |
| T_LOAD | — | — | Independent; `test_breadcrumbs_render.py` not in §2.7 list |
| T_C09 | — | G-P2 | New test file; depends on ThumbnailService + AdImage model (already in repo) |
| T_RESIDUAL_22 | D-06 | — | D-06 gate: assess in-memory vs DB-backed helper |
| T_DOC_* | — | — | Doc-only; no dependencies, no test run |

Cross-phase notes:
- **T28 vs T29 overlap:** 3 files (`test_seed.py`, `test_breadcrumbs_render.py`, `test_language_end_to_end.py`) contain both raw `price_currency` strings (§2.8) and `Ad.objects.create()` calls (§2.9). T29 subsumes the `price_currency` fix in those `create` calls. T28 still handles: `test_sweep_commands.py` (all 5 raw strings), `test_price_format.py` (1 raw string), and `test_seed.py` assertion comparisons (L1252/L1310) + `LanguageLocale` strings (L838/L854). Recommend: run T29 first on shared files, then T28.
- **§2.7 file #3 (`test_ad_localization.py`):** also touched by T_RESIDUAL_22 (assess `_make_ad`). These are independent concerns (class base vs helper function) — can be done in parallel; T_RESIDUAL_22 only decides whether to keep or simplify `_make_ad`.
- **T_LOAD vs T27:** `test_breadcrumbs_render.py` is NOT in the §2.7 list (15 files). T_LOAD touches this file independently. No conversion conflict.
- **Bot tests (T_BOT, T_NEW6):** cannot consume backend root fixtures — keep fixtures local to `src/telegram_bot/tests/conftest.py`.

---

## 5. Validation gates

- **G-P0** (after T210 + T211):
   ```
   pytest apps/moderation/tests/test_auto_moderation.py apps/core/tests/test_sweep_lock_structure.py -p no:cacheprovider
   ```
  Must not import `inspect` / `getsource`. Must use `call_command()` + spy on `advisory_lock`.

- **G-P1** (after T28, T29, T24, T_NEW6, T_BOT, T_ER):
  - `pytest apps/core/tests/test_contact.py` (T24/D-03)
  - `pytest apps/ads/tests/test_breadcrumbs_render.py apps/search/tests/test_autocomplete.py apps/core/tests/test_language_end_to_end.py` (T29)
  - `pytest apps/seed/tests/test_seed.py` (T29 + T28, seed marker subset)
  - `pytest src/telegram_bot/tests/test_claim_login_token.py src/telegram_bot/tests/test_login_claim.py -p no:xdist` (T_BOT + T_NEW6 — must pass without xdist)
  - `pytest apps/currencies/tests/ --reuse-db` AND `pytest apps/currencies/tests/ --create-db` (T_ER — both must pass)
  - Grep: 0 `@pytest.mark.e2e` (§2.6 confirmed resolved), 0 `def seller(`/`def user(`/`def category(`/`def city(` in `apps/` (§2.1 confirmed)

- **G-P2** (after T_NEW4, T27, T_LOAD, T_C09):
  ```
  make test
  ```
  Full fast gate (skips `seed`). Must pass with 0 failures. `--durations=10` must show `test_breadcrumbs_render.py` setup under 0.1s (was ~3.6s).
  Doc-only tasks (T_DOC_*, T_DOC_PATH) need no test run — verify by file grep only.

- **Regression back-stop (optional):** After P2, if any P1 change touched seeding or price normalisation, run `make test-all` once (~35 min).

---

## 6. Decision gates summary

| Gate | When | Resolution |
|------|------|-----------|
| D-01 | §2.11 rewrite | Use `auto_moderate(ad)` + `check(ad)`; `moderate()` does **not** exist; `AutoModerator` is not a class. |
| D-02 | §2.12 consolidation | (Replaced by D-05.) Confirm file overlap before merging; fix `token_hash` fixture regardless. |
| D-03 | §2.4 rewrite | Verify public `can_contact_seller`/`get_seller_for_contact` retain coverage of the 8 private-method branches before removing `TestCheckSellerContactable`. |
| D-04 | NEW-5 scope | Default to `scope="class"`; do **not** escalate to `session` (City row would leak across classes). |
| D-05 | §2.12 + NEW-2 | Confirm overlap percentage of the two bot login files. If >50% overlap, merge into one file; keep distinct concerns separate. Fix `token_hash` fixture (T_NEW6) regardless. |
| D-06 | §2.2 residual | Since `test_ad_localization.py` is a pure-unit test (no DB), `create_test_ad` is not applicable. Decide: simplify `_make_ad` to `Ad(**fields)` or keep `Ad.__new__` with explanatory docstring. Do NOT introduce DB access. |

---

## 7. Summary table

| # | Finding | Priority | Task | Target file(s) | Risk | Validation |
|---|---------|----------|------|----------------|------|------------|
| 1 | §2.10 | P0 | Rewrite `inspect.getsource` tests → `call_command()` + spy | `apps/core/tests/test_sweep_lock_structure.py` | low | isolated `pytest` |
| 2 | §2.11 | P0 | Rewrite to public `auto_moderate`/`check` | `apps/moderation/tests/test_auto_moderation.py` | medium | moderation `pytest` |
| 3 | §2.9 | P1 | `Ad.objects.create`→`create_test_ad` (5 files) | `test_breadcrumbs_render`, `test_deletion`, `test_language_end_to_end`, `test_seed`, `test_autocomplete` | medium | module subset |
| 4 | §2.8 | P1 | Enum strings→members (5 files, 15 raw strings) | `test_sweep_commands.py` + 4 others | very low | module `pytest` |
| 5 | §2.4 | P1 | Rewrite private-method test → public API | `apps/core/tests/test_contact.py` | low | isolated `pytest` |
| 6 | NEW-6 | P1 | Fix fixed `token_hash` fixture | `bot/tests/test_login_claim.py`, `conftest.py` | low | `pytest -p no:xdist` |
| 7 | §2.12+NEW-2 | P1 | Consolidate bot login tests | `test_claim_login_token.py`, `test_login_claim.py` | low–med | bot `pytest` (±xdist) |
| 8 | NEW-1 | P1 | ExchangeRate fixtures | `apps/currencies/tests/...`, new `conftest.py` | low | currencies `pytest` |
| 9 | §2.7 | P2 | SimpleTestCase→pytest (15 files) | list §3/T27 | low | `make test` gate |
| 10 | NEW-4 | P2 | Fix MagicMock cache-key leaks | `test_listings_context.py`, `test_detail_context.py` | low | those 2 files |
| 11 | NEW-5 | P2 | Widen `_load_catalog` scope | `apps/ads/tests/test_breadcrumbs_render.py` | low | `--durations=10` |
| 12 | C-09 | P2 | Add photo→thumbnail integration test | `apps/media/tests/test_thumbnail_integration.py` (new) | low | media `pytest` |
| 13 | §2.2 res | P2 | Assess `_make_ad` in `test_ad_localization.py` | `apps/ads/tests/test_ad_localization.py` | very low | isolated `pytest` |
| 14 | D-01 | P2 | Fix doc §1.2 markers "Not registered" | `25_test-optimization-plan_done.md` §1.2 | none | doc-only |
| 15 | D-02 | P2 | Fix doc §1.4 "CI runs all 934 tests" | `25_test-optimization-plan_done.md` §1.4 | none | doc-only |
| 16 | D-04 | P2 | Fix doc §14 T-12 claims | `25_test-optimization-plan_done.md` §14 | none | doc-only |
| 17 | NEW-7 | P2 | Fix `test_media_security.py` doc path | `audit_findings_compilation.md:153`, `audit_report_1.md:69` | none | doc-only |

**Rollout:** P0 → G-P0 → P1 (parallel, T_NEW6 before T_BOT; T29 before T28 on shared files) → G-P1 → P2 (T_NEW4 before §2.7 on shared files) → G-P2. Doc-only tasks (D-01/D-02/D-04/NEW-7) can run in parallel with any phase. No circular dependencies. Each task is independently reviewable.
