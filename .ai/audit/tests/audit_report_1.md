# Test Quality Audit — Report 1

**Project:** Mko Bazuna (Telegram-driven classifieds board)
**Date:** 2026-11-01
**Method:** 20 parallel per-block static audits (Docker available; targeted runs only) + Tech Lead synthesis
**Environment:** PASS — test DB healthy, 0 collection errors
**Scale audited:** 295 test files · ~3,718 test functions (4,027 collected incl. parametrization)
**Validation:** ⚠️ **Step 3 (independent validation) was deferred at the owner's request.** Every row below carries the per-block auditor's *preliminary* classification only. Treat all items as **unvalidated**.

---

## 1. Executive Summary

The suite is **broad but uneven**. Structurally it covers every app, but quality is concentrated in a minority of files. Across 20 blocks the auditors raised **~110 distinct root causes**. They collapse into a small set of recurring patterns:

| # | Pattern | Blocks | Weight |
|---|---|---|---|
| P1 | Mock-call / status-code verification stands in for business behavior | 3, 5, 6, 9, 13, 15, 17, 19, 20 | Largest single pattern; includes two *critical* instances (real publish path stubbed; no end-to-end bot FSM walk) |
| P2 | Assertions on source text (template/CSS/JS/YAML/shell/AST) instead of behavior | 1, 2, 4, 6, 7, 8, 9, 11, 12, 19 | Large; mostly medium severity, high churn cost |
| P3 | Missing boundary coverage (±1s retention cutoffs, 2 MB cap, TTLs, token expiry) | 4, 8, 10, 15, 16, 19, 20 | High — these are where regressions hide |
| P4 | Duplicated canonical homes | 4, 6, 8, 13, 16, 20 | Moderate; inflates runtime, creates drift |
| P5 | Seam predicates (consent/account-state) asserted via effects, not the predicate | 5, 11, 15, 20 | High — the single declaration can silently diverge |
| P6 | Marker/tier misclassification | 13, 17, 18, 19 | Moderate; fast gate loses or gains the wrong tests |
| P7 | Stale inventory, docstrings and inventory entries | 1, 3, 4, 6, 8, 9, 13, 18, 20 | Low individually; erodes trust |

**Five findings may indicate production defects rather than test defects** (auditors were read-only; no production code was touched). They are flagged `[PROD?]` and are *not* test problems until an owner decides:

1. **`apps/core/services/support.py:35`** reads the support-contact cache outside its `try` while the docstring promises fail-open on cache outage (Block 3, RC-1).
2. **Free-ad sort order** — code sorts price `0` first; spec says Free sorts last (Block 7, RC-1).
3. **`city_fuzzy` Tier-2** passes a non-casefolded query while Tier-1 casefolds (Block 16, RC-14).
4. **`recompute_normalized_prices`** lost-update guard is asserted nowhere — the only "lock" test never invokes the command (Block 17, RC-1) — so nobody has evidence the lock exists.
5. **Bot ad-create flow** — no test proves the FSM step keys match the keys `submit_ad` reads; the contract is unverified, not known broken (Block 19, RC-2).

**Prior audit status:** the 2026-09-17 report is now substantially stale. Roughly 40 of its items are resolved; ~12 remain open (notably B-series/E-series source-text patterns, F1 dashboard over-mocking, F6 `unit`+`django_db`, D2 criteria-cache divergence, and the G7 seed production guard). Prior item **D6 was confirmed to be an auditor hallucination** — `min_responses` does not exist.

---

## 2. Findings

Type legend: `[TEST-DELETE]` · `[TEST-REWRITE]` · `[TEST-UPDATE]` · `[BEST-PRACTICE]` · `[DOC-UPDATE]` · `[PROD?]` (possible production defect surfaced by the audit).

### 2.1 Group A — Real business flows proven only against stubs *(critical)*

| FilePath | TestName | Type | Problem | Recommendation |
|---|---|---|---|---|
| `src/backend/apps/ads/tests/test_submission.py` | `test_submit_ad_commit_when_auto_moderate_passes` (L107-131) | TEST-REWRITE | Patches `auto_moderate` to `True` and asserts `ON_MODERATION` for a "successful submit"; the real path sets `PUBLISHED`, `published_at`, `original_published_at`, writes `ModeratorActionLog` + `AD_PUBLISHED`/`MODERATION_APPROVED`. The docstring admits the mock bypasses `_pass_moderation`. | Add one un-patched success test asserting the full side-effect set; keep mocks only for rollback/branch cases. |
| `src/telegram_bot/tests/` (new file) | *(missing)* | BEST-PRACTICE | No end-to-end FSM walk (entry→category→city→text→price→photos→preview→confirm) produces a persisted ad. The step-key ↔ `submit.py:126-157` read-key contract is asserted nowhere. | Add `test_ad_create_flow_e2e.py` (`transaction=True`) driving `cmd_post` → … → confirm against the real ORM; assert persisted `title`/`description`/`price_amount`/`category_id`/`city_id`/`status`. |
| `src/backend/apps/currencies/tests/test_recompute_command.py` | `TestRecomputeRowLockConcurrency::test_recompute_row_lock_blocks_concurrent_price_edit` (L338-432) | TEST-REWRITE | Neither thread calls `call_command`; the main thread hand-opens `select_for_update()`. Deleting the lock from production leaves the test green. | Drive the real command from the main thread while a background thread performs the blocking edit. |
| `src/telegram_bot/tests/test_ad_copy.py` | `test_copy_success` (L48-79) | TEST-REWRITE | Patches `copy_ad` with a `MagicMock`; asserts a mocked method ran. Real ownership/DRAFT/field-copy path never exercised from the handler. | Use the real `copy_ad` and assert the copied draft row. |
| `src/backend/apps/ads/tests/test_edit_views_locking.py` | `TestEditViewsRowLockConcurrency::test_select_for_update_blocks_concurrent_delete_during` (L171-245) | TEST-REWRITE | Parametrizes three views but the helper does its own `select_for_update`; the `view` param is used only in prose. | Drive the real view POST in a thread holding the lock; assert it blocks. |
| `src/backend/apps/moderation/tests/test_approve_ad_side_effects.py` | `test_approve_ad_fires_alerts_after_commit` and siblings (L63, L82, L116) | TEST-REWRITE | `patch.object(transaction, "on_commit", side_effect=lambda fn: fn())` erases the commit-gating contract the test claims to verify. | Use `django_capture_on_commit_callbacks`. |
| `src/backend/apps/search/tests/test_search_api.py` | `test_over_budget_returns_rate_limited_problem` (L299-312) | TEST-REWRITE | Monkeypatches `rate_limit_check` to `False`, then asserts 429 — proves the mock returned `False`. | Exhaust the real counter, or assert the real counter behaviour. |

### 2.2 Group B — Predicate / gate seams asserted via effects instead of the declaration *(high)*

| FilePath | TestName | Type | Problem | Recommendation |
|---|---|---|---|---|
| `src/backend/apps/users/tests/test_account_state.py` | `TestPredicateConjunctIsLoadBearing` (L303-374) | TEST-REWRITE | Hand-writes one case per conjunct; `account_state_q` is never proven equivalent to `get_account_state` over the flag space. Adding a 7th flag turns nothing red (`is_active` already had to be patched once). | Parametrized truth table over the flag space + new-flag tripwire; assert the instance predicate equals the QS predicate per combination (with the documented `ads_auto_publish` exception). |
| `src/backend/apps/users/tests/test_account_state.py` | *(missing)* `TestCanStorePersonalData` | TEST-UPDATE | `can_store_personal_data` is referenced only in comments; its deliberate `is_active` omission and `consent_given_at` term are unreachable via `can_create_ad`. | Add a direct matrix incl. `is_active=False` + consented (the plan-19 support carve-out). |
| `src/backend/apps/users/tests/test_deletion.py` | `test_withdraw_soft_deletes_user_sets_pii_nulls` (L271-283) | TEST-UPDATE | Asserts 5 fields; `pii_inventory.py` declares `preferred_city` (NULL) and `password` (CLEAR). No test derives the expected set from `PII_ERASURE_ENTRIES`. A newly declared PII column is never caught. | Derive the expected null/clear set from `pii_inventory` and assert parity. |
| `src/backend/apps/ads/tests/test_ad_consent_gate.py` | *(missing)* `can_create_ad` truth table | TEST-UPDATE | The composition `can_publish_ad AND can_store_personal_data` is never pinned; dropping a conjunct passes. | Add the truth table; assert the refusal reason is `CONSENT_REQUIRED`. |
| `src/backend/apps/moderation/tests/test_moderation_side_effects.py` | `TestCriteriaCacheInvalidation` (L164-184) | BEST-PRACTICE | Prior D2 still open: `auto_moderation` reads 300 s cached criteria, `priority_calculator` reads the DB directly; no test asserts agreement after a mid-TTL edit. | Add a mid-TTL edit test asserting both readers agree. |
| `src/telegram_bot/tests/test_login.py` | *(missing)* | BEST-PRACTICE | No negative-account-state coverage at the login deep-link handler. | Add banned/deleted/deactivated refusal cases at the handler. |

### 2.3 Group C — Boundary coverage gaps *(high)*

| FilePath | TestName | Type | Problem | Recommendation |
|---|---|---|---|---|
| `src/backend/apps/core/tests/test_sweep_{delete,purge_deleted,purge_failed,purge_rejected,consent,login_tokens}.py`, `test_sweep_drafts.py` | retention tests (e.g. `test_deletes_archived_older_than_60_days`) | TEST-UPDATE | Boundaries tested only at wide margins (-200d vs -30d around 60d). Production uses strict `__lt`. A row exactly at the cutoff must survive; nothing asserts it. | Add a parametrized per-sweep test: row at `cutoff−1s` deleted, `cutoff+1s` kept, with a frozen `timezone.now()`. |
| `src/backend/apps/media/tests/test_filesystem.py` | `TestValidatePhoto` (L107) | TEST-UPDATE | Only `2MB+1` → reject tested. No "exactly 2 MB → accept". Production is strict `>`. | Add the accept half; build a decodable JPEG rather than a magic-byte blob. |
| `src/backend/apps/media/tests/test_filesystem.py` | `TestAssertStorageKeyContained` (L454-504) | TEST-UPDATE | Missing Windows backslash, URL-encoded `%2e%2e`, empty string, bare `".."`, in-root symlink. | Add the adversarial key set; assert containment on the resolved path. |
| `src/backend/apps/users/tests/test_login_token.py` | *(missing)* | TEST-UPDATE | `TOKEN_TTL_SECONDS=300` ±1s expiry boundary untested; concurrency only simulated by monkeypatching `.update → 0`. | Add a ±1s boundary test (freezegun) and a real threaded consume race. |
| `src/backend/apps/search/tests/test_autocomplete.py` | `test_autocomplete_rate_limit` (L157-174) | TEST-UPDATE | Asserts against `RateLimitBudget.SEARCH_PAGE.requests` in an autocomplete test; both are 30 today so the wrong constant is masked. | Use `AUTOCOMPLETE.requests`; add per-IP key isolation. |
| `src/telegram_bot/tests/test_update_id_dedup.py` | whole file | TEST-REWRITE | Monkeypatches the cache; real idempotency (same `update_id` twice → one effect) and the TTL boundary are never demonstrated; `86400` duplicates `DEDUP_TTL_SECONDS`. | Drive the middleware twice against LocMemCache; assert one effect; assert TTL via the constant. |
| `src/telegram_bot/tests/test_ad_create.py` | `TestProcessPhotos` | TEST-UPDATE | `file_size == MAX_PHOTO_BYTES` boundary (`==` vs `>`) and 1-photo/6-photo count boundaries untested. | Add the boundary cases. |
| `src/backend/apps/currencies/tests/test_price_normalizer.py` | *(missing)* | TEST-UPDATE | No zero, negative, >4dp rounding, or HALF_UP tie cases. | Add the boundary matrix. |
| `src/backend/apps/ads/tests/test_price_sort.py` | `TestPriceSort` (L17-83) | TEST-REWRITE | EUR-only data; `nulls_last=True` for NULL `price_normalized_eur` has zero coverage; mixed-currency normalization untested. | Add a mixed-currency pair and a NULL-priced ad. |

### 2.4 Group D — Source-text assertions standing in for behavior *(medium, high churn)*

| FilePath | TestName | Type | Problem | Recommendation |
|---|---|---|---|---|
| `src/backend/apps/search/tests/test_autocomplete_template.py` | ~30 assertions (L55-347) | TEST-REWRITE / TEST-DELETE | Greps SVG path `d="M5 9l7 7 7-7"`, JS `classList.add('rotate-180')`, Tailwind classes, an SRI hash, and *other apps'* templates (`ads/list.html`, `cabinet/*`). Prior E2/E8 unresolved. | Keep `hx-get`/`hx-target`/dropdown id; delete the rest; relocate cross-app assertions. |
| `src/backend/apps/ads/tests/test_gallery_markup.py` | `test_main_image_and_link_structure` (L106-131), `:142-148` | TEST-REWRITE | Pins IDs/classes; `assert "aspect-" in content` (L124) is vacuous. | Assert `data-full-url` anchor count/order instead. |
| `src/backend/apps/ads/tests/test_filter_url_reset.py` | L577-693, `:176-217`, `:238-265` | TEST-REWRITE | Asserts raw template-tag strings and CSS classes; the documented preservation rule (pagination carries lang/purpose/condition/features) is never asserted. Note `:238-252` ≡ `:254-265`. | Assert composed URLs contain each active filter key; delete pure source guards and the duplicate. |
| `src/backend/apps/core/tests/test_rtl_obfuscation.py` | `:211-216,219-232,240-280` | TEST-REWRITE | CSS/CSS-output and `privacy.html` text assertions incl. exact `rtl_count == 1`. Prior A4 still open. | Keep behavioral render tests; drop source checks. |
| `src/backend/apps/core/tests/test_templates.py` | `test_consent_banner_guard_in_all_templates` (L46) | TEST-REWRITE | Hardcoded 7-template list; `privacy.html:167-169` already carries the guard and is unprotected by the test — a live PII-009 safety gap. | Derive the set by globbing for the include. |
| `src/backend/apps/moderation/tests/test_priority_service.py` | `TestModerationQueueView` (L373-379, L510-522) | TEST-REWRITE | Asserts Russian literals (`"Нет объявлений в очереди модерации"`) duplicated by structured parity tests. | Assert `response.context` keys. |
| `src/backend/apps/core/tests/test_scheduler_wiring.py` | `test_entrypoint_invokes_scheduler_module` (L30-45) | TEST-UPDATE | `"exec" in content` is satisfied by a comment. | Assert the exact launch line. |
| `src/backend/apps/api/tests/test_urls.py` | `test_mount_unknown_paths_return_404` (L36-38) | TEST-UPDATE | Hand-copied route list; no route-inventory assertion. | Enumerate the live resolver. |

### 2.5 Group E — Duplicated canonical homes *(medium)*

| FilePath | TestName | Type | Problem | Recommendation |
|---|---|---|---|---|
| `src/backend/apps/ads/tests/test_media_security.py` | `TestExifStripping` (L360-421), `TestPhysicalDeletion` (L423-484) | TEST-DELETE | Weaker duplicates of `apps/media/tests/test_filesystem.py::TestStripPhotoExif` / `TestDeletePhoto` (media versions stronger). | Delete from the ads tree. |
| `src/backend/apps/ads/tests/test_adimage_storage_keys.py` | `test_key_columns_match_model_fields` (L96-113) | TEST-DELETE | Duplicate of `apps/media/tests/test_references.py::TestKeyColumnsAntiDrift`. | Delete; keep the ads-side behavioural keys tests. |
| `src/backend/apps/core/tests/test_delete_photo_single_call.py` vs five per-sweep copies | `test_collects_thumbnail_keys_for_media_cleanup` | TEST-DELETE | Per-sweep copies assert set equality (misses double-call); the parametrized test asserts exactly-once. | Delete the five per-sweep copies. |
| `src/backend/apps/core/tests/test_scheduler.py` | `TestDispatchIsolation` (L762-799) | TEST-DELETE | Weaker duplicate of `test_scheduler_error_handling.py:256-315` (same class name). | Delete from `test_scheduler.py`. |
| `src/backend/apps/lookups/tests/test_cache_key_convention.py` | whole file | TEST-DELETE (partial) | Weaker subset of `src/backend/tests/test_cache_key_convention.py`; only 2 unique assertions. | Keep the 2 unique assertions; delete the rest. |
| `src/backend/apps/ads/tests/test_favorites.py` | `test_excludes_non_published_and_blocked_sellers` (L296-310) | TEST-REWRITE | **Self-defeating**: all three ads belong to the seller that is then banned, so the two clauses cannot be distinguished. Duplicates the stronger `apps/cabinet/tests/test_favorites_visibility.py`. | Split into two independent fixtures, or defer to the cabinet test. |
| `src/backend/apps/ads/tests/test_dashboard_stats.py` | `test_html_contains_stats_card` (L242-250), `test_html_contains_time_range_selector` (L252-269) | TEST-REWRITE / TEST-DELETE | Tailwind class strings + Russian literals (`"За всё время"`, `"1 контакт"`) with no behavioral value; behaviour already covered by `TestDashboardTimeRange`. | Delete the translation/class assertions; assert context values. |
| `src/backend/apps/ads/tests/test_detail_context.py` | `test_detail_prefetch_includes_trust_score` (L73-107) | TEST-DELETE | Duplicate of `test_ad_detail_queries.py:71-94`. | Keep one home. |
| `src/backend/apps/core/tests/test_json_logging.py` | *(file)* | DOC-UPDATE | **File does not exist.** The block inventory listed a ghost. | Remove from inventories/docs. |
| `src/backend/apps/seed/tests/test_measure_nginx_rate_limit_keys.py` | whole file | TEST-DELETE (relocate) | Ops-script tool test misfiled under `apps/seed`; pins an attribution rule known broken since `cb798afa`. | Relocate to `scripts/tests/`; mark stale cases xfail. |
| `src/backend/apps/seed/tests/test_download_seed_photos.py` | whole file | TEST-DELETE (relocate) | Ops-script tool test misfiled; also has ~6 Unsplash/Pexels near-duplicate pairs and untested backoff. | Relocate, then parametrize over both clients. |

### 2.6 Group F — Marker / tier misclassification *(medium)*

| FilePath | TestName | Type | Problem | Recommendation |
|---|---|---|---|---|
| `src/backend/apps/seed/tests/test_seed.py` | `TestSeedEnums`, `TestUserGenerator`, `TestAdGenerator`, `TestAdGeneratorMultiLang` | TEST-UPDATE | Module-level `pytestmark=[django_db, integration]` blanket-excludes ~14 DB-free generator/enum tests from the fast gate. | Split into `test_seed_generators_unit.py` (the existing pattern); marker `seed` only the true seeders. |
| `src/backend/apps/seed/tests/test_seed.py` | `TestCityFixtures` (L1599) | TEST-UPDATE | Runs real DB city seeding but carries no `seed` marker → executes in the fast gate; inconsistent with the seed-marked `TestLeafCategoryFiltering`. | Harmonize the rule for SeedService fixture-loader tests. |
| `src/backend/apps/analytics/tests/test_analytics_models.py` | `pytestmark = [django_db, unit]` (L30) | BEST-PRACTICE | Prior F6 still present: `unit` + `django_db` contradiction. | Change to `integration`. |
| `src/backend/apps/search/tests/test_search_slo.py` | `TestSearchLatency` (L89-146) | BEST-PRACTICE | Wall-clock median assertion in the shared-Docker fast gate; failure mode is host load. | Move to `slow`/nightly. |
| `src/telegram_bot/tests/*` (11 files) | module-level `pytestmark` | TEST-UPDATE | Blanket `transaction=True` + `concurrent` + one `xdist_group("bot_concurrent")` on DB-free mock tests; serializes the whole ad-create block onto one worker. | Drop `transaction=True` where no DB is touched; split the xdist group. |
| `src/backend/apps/media/tests/test_purge_media_deletion_errors.py` | whole file | BEST-PRACTICE | `django_db` without `integration`/`unit`. | Add `integration`. |

### 2.7 Group G — Ad lifecycle & moderation rule coverage *(medium–high)*

| FilePath | TestName | Type | Problem | Recommendation |
|---|---|---|---|---|
| `src/backend/apps/ads/tests/test_ad_lifecycle.py` | `test_module_constant_matches_shipped_matrix` (L32-50) | TEST-REWRITE | Hand-copied snapshot; `any → DELETED` is a universal sink *not* in the dict and is untested as a matrix row. 7/13 allowed pairs sampled. | Parametrize from `ALLOWED_TRANSITIONS` + the DELETED sink. |
| `src/backend/apps/moderation/tests/test_auto_moderation.py` | *(missing)* | TEST-UPDATE | `price_required` and `duplicate_title` criteria have **zero** boundary tests; the outer `except Exception → ON_MODERATION_FAILED` safety net is untested. | Add both rules + the safety-net test. |
| `src/backend/apps/ads/tests/test_delete.py` | `test_delete_owner_transitions_to_deleted` (L43-60) | TEST-UPDATE | Asserts only status/redirect; US-S6's user-visible guarantee (hidden from listings/search/detail) and soft-delete image retention unasserted. | Assert absence from `ListingsQuery` + detail 404 + image rows retained. |
| `src/backend/apps/ads/tests/test_edit.py` | `TestBannedSellerRelistNowRefused` (L1376-1397) | BEST-PRACTICE | Banned owner refused on archive/reactivate, but `ad_edit` GET+POST is untested. | Add the banned-owner edit case. |
| `src/backend/apps/ads/tests/test_edit.py` | `TestApplyPriceChangeDelegation` (L704-723) | TEST-DELETE | Patches `normalize_price_to_eur` and asserts a call; the DRY invariant is behavioural and already covered. | Delete. |
| `src/backend/apps/ads/tests/test_edit_views_locking.py` | nine "sentinel" tests (L39-141) | TEST-DELETE | Reduce to `assert callable(edit.ad_edit)`; assert nothing about locking. | Delete. |
| `src/backend/apps/ads/tests/test_copy_ad.py` | `test_copy_ad_replaces_existing_draft` (L82-111) + `test_copy_ad_features_m2m_copied` (L208-219) | TEST-UPDATE / TEST-DELETE | Replacement-cascade, shared-key protection and savepoint retry untested; the features test duplicates `L165-168`. | Add the three branch tests; delete the duplicate. |
| `src/backend/apps/currencies/tests/test_price_normalizer.py`, `apps/ads/tests/test_price_sort.py` | — | — | *(folded into Group C)* | — |

### 2.8 Group H — API parity & inventory completeness *(medium)*

| FilePath | TestName | Type | Problem | Recommendation |
|---|---|---|---|---|
| `src/backend/apps/api/tests/test_import_rule.py` | `test_pairing_table_rows_satisfy_import_rule` | TEST-UPDATE | Enforces the import-subset rule only for rows present in `PAIRING_TABLE`; an unregistered `/api/v1/` module is silently unguarded. Nothing reconciles the live resolver against the table. | Add a resolver ↔ `PAIRING_TABLE` equality test. |
| `src/backend/apps/api/tests/test_import_rule.py` | `ALLOWLIST` | BEST-PRACTICE | 7 justified entries, but additive per endpoint with no cap/review trigger; two entries weaken the subset invariant. | Add a review rule / cap; document the rationale per entry in one place. |
| `src/backend/tests/test_docs_ci_parity.py` | whole file | TEST-UPDATE | No coverage of `.github/workflows/ci-nightly.yml` (the suite's only serial backstop) or `ci.yml`'s `test-full` marker set. | Add `_CI_NIGHTLY_YML` structural checks (no marker exclusion, `-p no:xdist`, `cancel-in-progress`). |
| `src/backend/apps/core/tests/test_sweep_drafts.py` | `test_draft_sweep_index_leads_on_updated_at` (L~195) | TEST-UPDATE | Reads `pg_indexes` against a syncdb schema; the migration that should create the index is never replayed. | Add a nightly migration-replay assertion or lower the docstring claim. |
| `src/backend/apps/categories/tests/test_load_catalog.py` | `test_load_catalog_succeeds...` (L62), `test_load_catalog_populates_lookup_items` (L83) | TEST-UPDATE | Assert non-emptiness only; a truncated catalog passes. Idempotency / `new_slug` rename / `--no-rewrite` rewrite untested (contrast `test_load_cities.py:72`). | Derive expected slugs + counts from `categories.yaml`; add re-run and rename tests. |
| `src/backend/apps/search/tests/test_alert_query.py` | `test_ignore_conflicts_skips_duplicates` (L512) | TEST-REWRITE | Asserts `count == 1` where `record_notifications` returns `len(ads)` unconditionally; `uq_saved_search_ad` is never asserted via `IntegrityError`. | Add the constraint test; assert rows, not the return value. |

### 2.9 Group I — Low-value / tautological / vacuous tests *(low–medium)*

| FilePath | TestName | Type | Problem | Recommendation |
|---|---|---|---|---|
| `src/backend/apps/core/tests/test_seedable_ad_statuses.py` | whole file | TEST-DELETE | Duplicates the `enums.py:162-164` frozenset; catches only an accidental enum edit. | Delete. |
| `src/backend/apps/core/tests/test_support_admin.py` | metadata tests (L53-177) | BEST-PRACTICE | Exact-list equality on `list_display` etc.; non-PII ones are pure introspection. Keep the PII-motivated ones. | Assert membership for the non-PII lists. |
| `src/backend/apps/ads/tests/test_ad_localization.py` | `:64`≡`:69`≡`:119` (+duplicates) | TEST-DELETE | `None` and `""` are identical under the truthiness guard. | Collapse into one parametrized truthiness test per field. |
| `src/backend/apps/search/tests/test_search_fuzzy.py` | `test_service_and_view_agree_on_fuzzy_match` (L77-99) | BEST-PRACTICE | Re-derives `difflib.get_close_matches` with the same cutoff — passes by construction. | Pin fixed expected slugs. |
| `src/backend/apps/core/tests/test_context_processors.py` | `_call_header_context` (L63-72) | TEST-UPDATE | `unit`-marked tests trigger a real DB read via `get_bot_username` and survive only via the fail-open fallback; dead `mock_city` return value. | Patch `get_bot_username`; return the context dict. |
| `src/backend/apps/core/tests/test_sanitize.py` | `test_empty_key_never_leaks_raw_value` (L84-91) | TEST-REWRITE | Docstring claims "warns once"; unasserted. Module-global warning state not reset → order-dependent. | Assert via `caplog`; reset globals in a fixture. |
| `src/backend/apps/seed/tests/test_seed_generators_unit.py` | `TestImageGeneratorManifest::test_manifest_loading` (L108-134) | TEST-REWRITE | Asserts the test's own dict assignment; dead `setup_method`/`teardown_method`/`temp_dir`. | Test the real `_load_manifest`; delete dead scaffolding. |
| `src/backend/apps/trust/tests/test_trust_calculator.py` | boundary/pro tests | TEST-UPDATE | Expected totals reproduced from the implementation's own arithmetic; global `CONTACT_INITIATED` denominator coupled; duplicate `make_user(990023001)` at `:291,318`. | Hand-compute a few anchors independently; dedupe ids. |
| `src/telegram_bot/tests/test_ad_create_submit_outcome.py` | `test_moderation_failed_clears_state` (L298) | TEST-UPDATE | `ad_id=1` with `submit_ad` patched — meaningless sentinel. | Use a real row or document the sentinel. |

### 2.10 Group J — Documentation & inventory drift *(low)*

| FilePath | TestName | Type | Problem | Recommendation |
|---|---|---|---|---|
| `src/backend/apps/core/tests/test_scheduler.py` | comments (L327, L637-638) | DOC-UPDATE | Say "9 hourly / 2 daily"; production ships 10 hourly / 3 daily. | Update. |
| `src/backend/apps/core/tests/test_footer_contact_link.py` | module docstring (L4-20) | DOC-UPDATE | Describes the removed `js_verified` gate. | Update. |
| `src/backend/apps/ads/tests/test_i18n_completeness.py` | `test_plural_forms_runtime` (L857-862) | TEST-REWRITE | Claims to prove CLDR form selection; bs `msgstr[1]`/`[2]` are textually identical, so only the interpolated counter differs. | Assert the form index; scope the claim to `ru`. |
| `src/backend/apps/ads/tests/test_i18n_category_city.py` | `test_detail_defaults_to_en` (L104-124) | TEST-UPDATE | Pins a *test-settings* artifact (`LANGUAGE_CODE="en"`); production default is `"ru"`. | Assert `LanguageLocale(settings.LANGUAGE_CODE)`. |
| `src/backend/apps/core/tests/test_context_processors.py` / `docs/01-spec/architecture-structure.md:191` | — | DOC-UPDATE | Doc says `bot_username` is NOT injected; production injects it. | Fix the doc; assert `bot_username` + `catalog_js_labels`. |
| `src/backend/apps/ads/tests/test_detail_context.py` | module docstring (L1-13) | DOC-UPDATE | Describes mocking that no longer exists. | Update. |
| `src/backend/apps/media/tests/test_helpers.py` | module | BEST-PRACTICE | Live helper module collected because it matches `test_*.py`. | Rename to `media_test_helpers.py`. |
| `src/backend/apps/search/tests/test_autocomplete.py` | comment (L737-739) | DOC-UPDATE | Claims "no search_vector trigger" — false. | Delete the comment. |
| `src/backend/apps/seed/tests/test_seed.py` | `TestSeedPopularSearchKeys` docstring | DOC-UPDATE | Claims `_clean` ran; it did not (direct service call). | Correct. |
| `src/backend/apps/ads/tests/test_media_security.py` | L147, L559 | DOC-UPDATE | Orphaned string literals acting as class docstrings. | Delete. |
| `docs/01-spec/contact-us.md:140` | — | DOC-UPDATE | Spec says 5 renders/10 min; code uses 60/600 s. | Owner reconciliation, then align the test. |
| `docs/01-spec/search-patterns.md:183-185,223-224` | — | DOC-UPDATE | Spec says Free ads sort last; code sorts them first. | Owner reconciliation (see `[PROD?]` #2). |
| `src/backend/apps/categories/tests/test_categories.py` / `docs/02-database/db-categories.md` | — | DOC-UPDATE | Multi-parent `CategoryPath` behaviour has no doc-linked test and no self-loop coverage. | Add both. |

### 2.11 Group K — Potential production defects surfaced *(do not "fix" by changing tests)*

| Production path | Where first seen | Finding | Required decision |
|---|---|---|---|
| `src/backend/apps/core/services/support.py:35` + `apps/core/utils/cache.py:290` | Block 3 RC-1 | Cache read sits outside the `try`; the docstring's "fails open on cache outage" is **false**. A Redis blip 5xx's any support-contacts render. | Route through `cache_get_or_none`, or downgrade the docstring. Either way add a cache-outage test. |
| `src/backend/apps/ads/services/listings_query.py:297-306` + `apps/search/services/fts.py:99-108` | Block 7 RC-1 | Free (0) sorts first ascending; spec says last. `nulls_last=True` handles NULL but not 0. | Owner decides spec-vs-code; then align test + doc together. |
| `src/backend/apps/locations/services/city_fuzzy.py:42-46` | Block 16 RC-14 | Tier-2 passes the raw query/candidates while Tier-1 casefolds; `categories/fuzzy.py:44-45` has the fix, cities did not get it. | Confirm and fix; add a discriminating test. |
| `src/backend/apps/currencies/management/commands/recompute_normalized_prices.py:117-127` | Block 17 RC-1 | No test has ever exercised the row lock. Evidence that the lock exists in production is currently absent. | Rewrite the test to drive the command; if it then fails, the lock is missing. |
| `src/telegram_bot/handlers/ad_create/*` ↔ `submit.py:126-157` | Block 19 RC-2 | Step-key ↔ submit-key contract unverified. | Add the e2e walk; if it fails, a key drifted. |
| `src/backend/apps/search/services/immediate_alerts.py:190-197` | Block 14 RC-3 | In-flight counter leak on `submit` failure untested. | Add the test. |

---

## 3. Prior-audit reconciliation

| Prior item | Status | Notes |
|---|---|---|
| A1 (zero-coverage core services) | ✅ Resolved | `test_core_tags.py`, `test_translation.py`, async wrappers, `record_contact_initiated` |
| A2 (contact-rate-limit vs login-template conflation) | ◐ Partial | Still: `TestContactSeller`/combinatorial/integration triple |
| A3 (cross-block imports) | ✅ Resolved | — |
| A4 (AST/source parsing) | ◐ Partial | Lock IDs scoped; template/CSS source guards remain (Groups D, G) |
| A5 (`test_sweep_commands.py` bloat) | ✅ Resolved | Split into 9 files |
| B2 (redundant constraints) | ✅ Resolved | — |
| B3 (`copy_ad` coverage) | ✅ Resolved | Added, then see Group G for remaining branches |
| B4/P9 (brittle template assertions) | ❌ Open | Group D |
| B5 (detail over-mocking) | ✅ Resolved | — |
| B6 (duplicate `_parse_po_entries`) | ✅ Resolved | — |
| B7b (`test_price_format` marker) | ✅ Resolved | — |
| C1 (backend tests in bot tree) | ❌ Open | `test_ad_lifecycle.py`, `test_lock_timeout_boundary.py` |
| C2 (bot photo integration) | ◐ Partial | Real JPEG staging exists; handler→submit seam still mocked |
| C3 (async/sync boundary) | ✅ Resolved | — |
| C4 (shared hardcoded ids) | ◐ Partial | Bot-local `_TEST_SELLER_ID` duplicates remain |
| C5 (marker loosening) | ◐ Partial | Blanket `transaction=True` |
| C6 (enums vs literals) | ✅ Resolved | — |
| C7 (translation edge cases) | ✅ Resolved | — |
| C8 (xdist flake) | ✅ Resolved | — |
| C9 (moderation side effects) | ◐ Partial | In the wrong tree; full-set assertion still missing |
| D1 (mock `Ad.objects.filter`) | ✅ Resolved | — |
| D2 (criteria cache divergence) | ❌ Open | Group B |
| D3 (moderation side effects) | ◐ Partial | Folded into Group G |
| D4 (helper duplication / names) | ◐ Partial | — |
| D5 (TOCTOU mocked counters) | ✅ Resolved | Residual `flaky` marker |
| D6 (trust/min_responses) | ✅ Confirmed invalid | Prior auditor hallucination; no `min_responses` exists |
| E1 (status-only assertions) | ◐ Partial | Remaining in autocomplete structure tests |
| E2 (brittle template assertions) | ❌ Open | Group D |
| E3 (`User.DoesNotExist = Exception`) | ✅ Resolved | — |
| E4 (FTS/category conflation) | ✅ Resolved | — |
| E5 (redundant fixtures) | ◐ Partial | Three `cache.clear()` fixtures |
| E6 (inefficient per-ad loops) | ❌ Open | `test_search_view.py` still loops |
| E7 (stale comments) | ◐ Partial | One remains |
| E8 (misplaced tests) | ❌ Open | Group D |
| E9 (search coverage gaps) | ◐ Partial | Group H |
| F1 (moderation dashboard over-mocking) | ❌ Open | `test_views.py:388-391` |
| F2 (duplicate 410 tests) | ✅ Resolved | — |
| F3 (duplicated `_make_user`) | ✅ Resolved | — |
| F4 (weak assertions) | ◐ Partial | `test_consent_records.py:140` `if IP is not None` |
| F5 (media-error side effect) | ✅ Resolved | — |
| F6 (`unit` + `django_db`) | ❌ Open | Group F |
| F7 (cross-block coupling) | ✅ Mostly Resolved | — |
| F8 (EXIF/settings hacks) | ✅ Resolved | — |
| F9 (missing media/analytics coverage) | ◐ Partial | Media units resolved; analytics e2e still missing |
| F10 (private `_cache_key`) | ◐ Partial | LocMem internals remain (Blocks 13, 16) |
| G1/G2/G4/G7 (markers, cities, config) | ✅ Mostly Resolved | G7 exception: seed production guard |
| G6 (`test_migrations.py` naming) | ◐ Observation | Not a defect |
| "3.1 slow marker abuse" (analytics) | ◐ Partial | `test_search_slo.py` wall-clock remains |
| "3.4 fragile fixtures" | ◐ Partial | `TestSeedFilterCoverage` xdist-dependent |
| "3.7 consolidate helpers" | ◐ Partial | `_SyncExecutor` cross-file import; `_prod_env` |

---

## 4. Missing Coverage Register (consolidated)

Highest-value additions, in rough order of risk:

1. **Bot FSM end-to-end walk** → persisted fully-populated ad (Bot, Block 19).
2. **Real submit → PUBLISHED** full side-effect set (Ads, Block 5).
3. **`account_state_q` ≡ `get_account_state`** truth table + **`can_store_personal_data`** matrix (Users, Block 15).
4. **PII erasure ↔ inventory parity** (Users, Block 15).
5. **Retention cutoff ±1s** for all six sweeps (Core, Block 4).
6. **Media boundaries**: 2 MB accept, traversal key set (Media, Block 10).
7. **`recompute_normalized_prices` real row lock** (Currencies, Block 17).
8. **API route ↔ `PAIRING_TABLE`** completeness (Api, Block 17).
9. **`update_id` real idempotency + TTL** (Bot, Block 20).
10. **Middleware order** (Bot Block 20 + Core Block 2).
11. **`ALLOWED_TRANSITIONS` exhaustive + `any → DELETED`** (Ads, Block 5).
12. **`price_required` / `duplicate_title` / outer moderation safety net** (Moderation, Block 11).
13. **`uq_saved_search_ad` IntegrityError**; counter-leak on submit failure (Search, Block 14).
14. **Catalog load idempotency + `CategoryPath` self-loop + multi-parent** (Categories, Block 16).
15. **Dedup `AD_PUBLISHED` on re-publish + real rollup** (Analytics, Block 17).
16. **LoginToken ±1s expiry + real threaded consume race** (Users, Block 15).
17. **Seed production guard** + seed data invariants (Seed, Block 18).
18. **Search relevance ordering** (order, not membership) (Search, Block 13).
19. **`ci-nightly.yml` / `test-full` tier parity** (Config, Block 12).
20. **Support cache fail-open / alert callback keyboard content / ticket status** (Core+Bot, Blocks 3, 20).

---

## 5. Statistics

| Metric | Value |
|---|---|
| Blocks audited | 20 |
| Root causes raised | ~110 |
| Critical | 4 (2 of them Group A flow-stub tests, 1 bot FSM walk, 1 recompute lock) |
| High | 22 |
| Medium | 41 |
| Low / BEST-PRACTICE / DOC-UPDATE | ~43 |
| Files recommended for deletion or relocation | 8 |
| Individual tests recommended for deletion | ~40 |
| Missing-coverage items proposed | ~95 |
| Ghost inventory entries | 1 (`apps/core/tests/test_json_logging.py`) |
| Potential production defects surfaced | 6 (`[PROD?]`) |

Per-block detail (evidence line numbers, per-file tables) is preserved in the raw findings:
`.ai/tmp/test-audit-raw-findings.md`.

---

## 6. Scope notes

- No production code, test file, or configuration was modified.
- Validation step skipped: no item here has been independently re-verified against production.
  Several items are **claims about what the code does**, not observed test failures.
- Every block reported its files exist and contain tests except the single ghost entry noted.
- Auditors ran with Docker available; only targeted runs were performed, no full suite.
- Prior block reports referenced timing noise from concurrent agents; no timing claim is used here.
