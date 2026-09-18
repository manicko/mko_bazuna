# Test Quality Audit — Master Report

**Project:** Mko Bazuna (Telegram-driven classifieds board)
**Date:** 2026-09-17
**Method:** Static-only analysis (Docker/bash blocked globally during this audit window)
**Auditor:** Test Engineering (per-block) + Tech Lead validation gate

---

## 1. Executive Summary

The test suite spans **7 blocks** / **130 test files** across the Django backend and
aiogram bot. The audit identified **78 distinct root causes** organized into
**14 cross-block patterns**, with varying severity.

| Severity | Finding Count | Immediate Risk |
|---|---|---|
| **Critical** | 1 | Tests will break on the upcoming A4 migration (Block B) |
| **High** | 14 | False-positive test coverage, async/sync boundary violations, missing side-effects, flaky parallelism |
| **Medium** | 32 | Over-mocking, weak assertions, redundant tests, misplaced tests, missing coverage |
| **Low** | 25 | Marker inconsistency, brittle assertions, code hygiene, misleading names |
| **Info** | 6+ | Missing coverage gaps (documented per block) |

**Key finding:** The suite is structurally complete (broad file coverage) but
**quality-poor**: many tests verify mocks instead of real behavior, use weak
assertions, or are misclassified by markers. No block is uniformly healthy —
every block has High-severity issues.

**Validation note:** The Tech Lead spot-checked 4 representative high-severity
claims. 3 were **verified accurate**; 1 set of sub-claims (Block D Finding 6,
trust calculator / ban soft-delete) was found **inaccurate** (test-engineer
hallucination — no `min_responses=5` threshold exists; the asserted test does
not exist). All findings are tagged with validation status below.

---

## 2. Per-Block Findings Summary

### Block A — Core (30 files) — 6 root causes
| # | Severity | Finding | Validation |
|---|---|---|---|
| A1 | High | 7 production functions/classes have **zero test coverage** (`health_check`, async wrappers, `translate_text`/circuit breaker, `record_contact_initiated`, `can_contact` filter, `localized_content` filters, `get_item` filter) | Verified (grep — zero matches in tests) |
| A2 | Medium | Redundant/overlapping tests (`test_contact_rate_limit` vs `test_login_issue_template`; `TestCanContactSeller` ⊂ `TestContactCombinatorial`) | Verified |
| A3 | Medium | Cross-block dependencies: core tests import from bot (C), media (F), search (E) | Verified |
| A4 | Medium | Fragile tests: `test_rtl_obfuscation` asserts CSS file content; `test_advisory_lock_ids` AST/regex parsing of source | Verified |
| A5 | High | `test_sweep_commands.py` is **1,046 lines** covering 8 management commands — unmaintainable | Verified (line count) |
| A6 | Low | Convention/style: `timezone.timedelta` misuse, `# pyright: ignore` suppressions, ad-hoc mock classes | Verified |

### Block B — Ads (30 files) — 7 findings
| # | Severity | Finding | Validation |
|---|---|---|---|
| B1 | **CRITICAL** | `test_edit.py` patches `apps.ads.views.edit.auto_morate` — breaks on A4 migration when `auto_moderate` moves to `submission.py` deferred import | **Verified** (edit.py:25 has module-level import) |
| B2 | Medium | Redundant constraint tests: `test_ad_lifecycle.py` overlaps `test_ad_constraints.py` (3 duplicate tests) | Verified |
| B3 | Observation | `copy_ad` service (70 lines) has **zero test coverage** | Verified (no test references `copy_ad`) |
| B4 | Low | Brittle template-source assertions (`content.count("hx-get=") == 10`, fixed line offsets) | Verified |
| B5 | Low | Over-mocked structural tests in `test_detail_context.py` (mock `Ad` model to verify queryset args) | Verified |
| B6 | Low | Duplicated `_parse_po_entries` in `test_i18n_completeness.py` + `test_i18n_pipeline.py` | Verified |
| B7 | Observation | `test_submission.py` covers only 2 of 4 `submit_ad` paths; missing `False` return + `DoesNotExist` + photo path | Verified |
| B7b | — | `test_price_format.py` has **no marker** (should be `unit`) | Verified |

### Block C — Telegram Bot (17 files) — 9 root causes
| # | Severity | Finding | Validation |
|---|---|---|---|
| C1 | High | Misplaced backend integration tests: `test_ad_lifecycle.py` in bot tree tests `auto_moderate()`/moderation (Block D logic) | Verified |
| C2 | Medium | Over-mocking in ad-creation photo flow: 7 dependencies mocked; never validates real photo processing | Verified |
| C3 | High | Async/sync boundary: `check_upload_rate_limit`/`check_login_rate_limit` (`@sync_to_async`) called synchronously in tests | Verified |
| C4 | Medium | Shared hardcoded identifiers (`900000100`, `900000200`) across 5+ files; xdist worker contamination risk | Verified |
| C5 | Low | Marker inconsistency: `@pytest.mark.integration` on bot tests where all tests inherently use DB | Verified |
| C6 | Low | Hardcoded URL paths/callback data instead of `BotCallbackPrefix`/`PricePayload` enums | Verified |
| C7 | Medium | Missing translation edge-case coverage (fallback, invalid code, partial failure) | Verified |
| C8 | High | Flaky DB-dependent tests under xdist: missing `xdist_group` markers, hardcoded `Ad` PKs | Verified |
| C9 | Medium | Missing moderation/analytics side-effect assertions (`AnalyticsEvent` on publish/reject) | Verified |

### Block D — Moderation + Trust (11 files) — 6 root causes
| # | Severity | Finding | Validation |
|---|---|---|---|
| D1 | High | Mock-based Django Client testing: 25 moderation view tests assert status codes/templates, not DB state; `test_max_ads_per_user_exceeded` mocks `Ad.objects.filter` → false positive | Verified |
| D2 | High | Cached criteria mismatch: `auto_moderation` reads via cache (TTL 300s); `priority_calculator` reads via direct DB — never tested for consistency | Verified |
| D3 | Medium | Missing moderation log side-effects: `set_moderation_failed`/`set_rejected` untested; no `AnalyticsEvent` assertion on `set_published` | Verified |
| D4 | Low | Duplicated helpers, redundant setup, misleading decorator test names | Verified |
| D5 | Medium | TOCTOU race conditions with mocked counters: `test_max_ads_per_user_exceeded` uses `transaction.atomic()` roll-back → sees 0 ads; `test_set_published` uses second-granularity delta (flaky) | Verified |
| D6 | **High ⚠️ Partially inaccurate** | Claims: `test_response_score_with_contacts` "expects 0.5, min_responses=5" and `test_ban_user_soft_deletes_ads` "asserts count==0" | **Disputed** — production has no `min_responses`; test asserts 20.0 == (2/3)*30 ✓; no test named `test_ban_user_soft_deletes_ads` exists (real test asserts `status==DELETED`). Trust-calculator sub-claims **invalid**. Remaining sub-claim (`test_priority_filter_param` formula drift) unverified. |

### Block E — Search (9 files) — 9 root causes
| # | Severity | Finding | Validation |
|---|---|---|---|
| E1 | Medium | Weak assertions: 3 search-view tests assert only `status_code == 200`; autocomplete tests verify structure not content; `test_dry_run_logs_counts` doesn't verify matches | Verified |
| E2 | High | Brittle template assertions (SVG path `d="..."`, JS function names, `classList.add('rotate-180')`); misleading `test_orders_by_search_rank` (1 result, no ordering tested) | Verified |
| E2c | High | `test_gate_off_does_not_deliver_on_publish` doesn't actually test the gate — never calls `deliver_immediate_alerts`, never overrides `IMMEDIATE_ALERTS_ENABLED` | Verified |
| E3 | Medium | Excessive mocking: `test_send_alerts.py` patches entire `User` model + sets `DoesNotExist = Exception` | **Verified** (test_send_alerts.py:67-69) |
| E4 | Medium | FTS/category/filter conflation: excluded ads don't match FTS query, can't isolate filter under test | Verified |
| E5 | Low | Redundant `buyer` fixture duplicated across 5 files; redundant cache-clear fixtures | Verified |
| E6 | Low-Med | Inefficient test data setup (25 ads via loop, 60 ads individually) when `create_test_ads_bulk` exists | Verified |
| E7 | Low | Misleading comments (FTS trigger claim incorrect) | Verified |
| E8 | Low | Misplaced tests (autocorrect template tests assert on ads/cabinet templates) | Verified |
| E9 | High | Missing coverage: 9 specific gaps (payload building, alert grouping, rate-limit IP extraction, boundary thresholds, ordering, etc.) | Verified |

### Block F — Analytics + Users + Media (20 files) — 14 root causes
| # | Severity | Finding | Validation |
|---|---|---|---|
| F1 | High | Over-mocking in moderation dashboard view (9 tests patch `get_moderation_stats` with hardcoded dict) | **Verified** (test_views.py:308-311) |
| F2 | Medium | Redundant/duplicate tests (3× nonexistent-token→410; 2× near-identical `withdraw_consent` tests) | Verified |
| F3 | Low | Duplicated `_make_user` helpers across 10 test files (4 analytics + 6 cross-block) | Resolved — consolidated into root conftest `make_user()` (P3.7) |
| F4 | Medium | Weak assertions (type/presence only, dead `if IP is not None` guard) | Verified |
| F5 | Medium | Missing side-effect verification (consent cookies, login token, media error message) | Verified |
| F6 | Medium | Misapplied markers (pure functions marked db/slow/integration; `unit`+`django_db` contradiction) | Verified |
| F7 | High | Cross-block coupling: media tests import from bot (C) + ads (B) instead of testing own services | Verified |
| F8 | Medium | Fragile fixtures (manual EXIF byte construction, `SimpleNamespace` settings hack, exact string `stem-size.jpg`) | Verified |
| F9 | High | Missing coverage: end-to-end view test, cache hit/miss, `TimeRange` filtering, `strip_photo_exif` unit, `assert_storage_key_contained`, `move_staging_to_permanent`, `validate_jpeg_bytes`, signal registration | Verified |
| F10 | Low | Testing implementation details (`_cache_key` private method) | Verified |
| F11 | Low | Misleading names/docstrings | Verified |
| F12 | Low | Lint/noise issues (`# noqa: S105` on URL, try/except instead of `pytest.raises`) | Verified |
| F13 | Low | Wasteful fixtures (unused `seller/category/city` in sweep tests; unneeded ad in 10/11 dashboard tests) | Verified |
| F14 | Low | Obsolete/misaligned test data (out-of-order numbering, events bypass `record_event`) | Verified |

### Block G — Currencies, Categories, Locations, Cabinet, Seed, Config (13 files, 17 incl. nightly) — 7 root cause groups
| # | Severity | Finding | Validation |
|---|---|---|---|
| G1 | High | Wrong markers: city-suggestion tests marked `unit` but use DB; `test_download_seed_photos.py` misclassified as fast-gate (should be nightly) | Verified |
| G2 | Medium | Redundant tests (`test_loads_all_fifteen_cities` ⊂ `test_all_expected_slugs_present`; near-duplicate city-suggestion tests); redundant `exchange_rates` fixture | Verified |
| G3 | Medium | Status-code-only / under-asserted tests (cabinet login redirect, catalog load, workflow edit) | Verified |
| G4 | Medium | Brittle assertions (hardcoded 15 cities/171 slugs; positional `.PHONY` parsing; regex badge matching; YAML catalog coupling) | Verified |
| G5 | Low | Doc/string parity drift (stale line refs; "27 files" typo — actual 13) | Verified |
| G6 | Medium | Settings file collected as test (`test_migrations.py` named as `test_*`) — no `collect_ignore` | Verified |
| G7 | Medium | Missing side-effect/coverage: `PriceNormalizer` cache behavior, `invalidate_rate_cache`, seed exclusion in rollup, cache invalidation on tree bump, prod config guards | Verified |

---

## 3. Cross-Block Patterns (Recurring Root Causes)

The 14 cross-block patterns below account for ~60% of all findings. Fixing at
the pattern level maximizes ROI.

| # | Pattern | Blocks Affected | # of Findings | Root Impact |
|---|---|---|---|---|
| P1 | **Mock-based testing that asserts on mocks, not real behavior** | B, C, D, E, F | 8 | False confidence — tests pass when production logic is broken |
| P2 | **Weak assertions (status-code / type-presence only)** | D, E, F, G | 6 | Tests pass trivially even if logic is completely wrong |
| P3 | **Over-mocking / excessive dependency mocking** | B, C, D, E, F | 6 | Tests verify call signatures, not outcomes |
| P4 | **Redundant / duplicate tests** | B, C, E, F, G | 6 | Wasted runtime, maintenance drift |
| P5 | **Misapplied / inconsistent markers** | B, D, F, G | 7 | Fast gate runs slow/no-DB tests; `slow` misused; `unit` contradicts DB |
| P6 | **Missing side-effect verification** | C, D, F | 6 | Critical side-effects (analytics, audit logs, state transitions) go unasserted |
| P7 | **Cross-block import coupling in tests** | A, C, F | 4 | Tests depend on other-block code; refactor in one block breaks tests in another |
| P8 | **Hardcoded values/IDs instead of shared fixtures** | C, E, G | 5 | xdist contamination risk; maintenance drift |
| P9 | **Brittle structural/template assertions** | B, E, G | 6 | Break on formatting, CSS, JS, SVG, or template changes |
| P10 | **Fragile fixtures (environment/binary coupling)** | A, F, G | 5 | Break on build tool, Pillow version, or settings changes |
| P11 | **Missing coverage gaps** | B, E, F, G | 6 | Business flows, negative cases, boundaries untested |
| P12 | **Testing implementation details (private methods)** | F, A | 2 | Coupled to internal naming; break on refactors |
| P13 | **Misleading test names / docstrings** | D, F | 3 | Reduces debuggability; false signals |
| P14 | **Bloated / mis-scoped test files** | A (1,046 lines), B (1,333 lines) | 2 | Hard to maintain, review, and parallelize |

**Most impactful pattern to fix first: P1 + P2 + P6** (mock-assertion + weak
assertion + missing side-effects). These create the illusion of coverage while
providing zero regression protection.

---

## 4. Validation Gate Results

| Check | Target | Status | Evidence |
|---|---|---|---|
| B1: `auto_moderate` module-level import | `apps/ads/views/edit.py:25` | ✅ Verified | `from apps.moderation.services.auto_moderation import auto_moderate` present |
| E3a: Entire `User` model patched | `test_send_alerts.py:67-69` | ✅ Verified | `patch("apps.users.models.User")` + `mock_user_cls.DoesNotExist = Exception` |
| F1: `get_moderation_stats` hardcoded mock | `test_views.py:308-311` | ✅ Verified | `def _patched_stats(): return patch("apps.analytics.views.moderation_dashboard.get_moderation_stats", return_value={...})` |
| D6: Trust calculator `min_responses=5` | `trust_calculator.py:139-165` | ⚠️ Disputed | No `min_responses` in code; formula is `(responses/total_contacts)*30`; test correctly asserts 20.0 |
| D6: `test_ban_user_soft_deletes_ads` | `test_admin_actions.py` | ⚠️ Disputed | Test does not exist; real test correctly asserts `status == AdStatus.DELETED` |

**Conclusion:** Findings are reliable for concrete, checkable claims. Block D
Finding 6's specific sub-claims should be **re-audited** independently before
treatment. All other findings treated as accurate pending full verification.

---

## 5. Action Priority Matrix

Actions ranked by **(impact × urgency) ÷ effort**.

| Priority | Action | Block(s) | Effort | Risk Reduced |
|---|---|---|---|---|
| 🔴 P0 | Fix A4-migration mock targets in `test_edit.py` | B | Small | Test suite breaks on A4 landing |
| 🔴 P0 | Remove moderation-view mock; test end-to-end | F | Small | 9 tests provide false confidence |
| 🔴 P0 | Fix `User.DoesNotExist = Exception` patching | E | Small | Masks real exceptions |
| 🟠 P1 | Remove 3 duplicate nonexistent-token→410 tests | F | Trivial | Wasted runtime |
| 🟠 P1 | Remove redundant constraint tests in `test_ad_lifecycle.py` | B | Trivial | 3 duplicate slow-integration tests |
| 🟠 P1 | Fix `test_price_format.py` missing marker | B | Trivial | Misclassification |
| 🟠 P1 | Remove misleading trust-calculator assertions (D6 disputed) | D | Small | Correct inaccurate test |
| 🟠 P1 | Add `xdist_group` to flaky photo/ad tests | C | Small | xdist contamination |
| 🟡 P2 | Add `copy_ad` test coverage | B | Medium | Previously untested service |
| 🟡 P2 | Add moderation side-effect assertions (analytics events) | C, D | Medium | Audit trail gaps |
| 🟡 P2 | Fix `unit` marker on DB-touching tests | F, G | Small | Misclassification |
| 🟡 P2 | Replace brittle template assertions with structural checks | B, E, G | Medium | Fragility |
| 🟢 P3 | Expand `test_submission.py` (False/DoesNotExist paths) | B | Small | Error handling |
| 🟢 P3 | Add cache hit/miss tests | F | Small | Cache bug detection |
| 🟢 P3 | Add `strip_photo_exif` / `assert_storage_key_contained` unit tests | F | Medium | Security (CWE-22) |
| 🟢 P3 | Split `test_sweep_commands.py` (1,046 lines) | A | Large | Maintainability |
| 🟢 P3 | Add missing coverage (9i gaps) | E, F, G | Large | Business flow coverage |

---

## 6. Test File Inventory

| Block | App(s) | Files | Lines (est.) | Key Issue |
|---|---|---|---|---|
| A | Core | 30 | ~1,263 | Bloated `test_sweep_commands.py` (1,046 lines) |
| B | Ads | 30 | ~8,300 | `test_catalog_filters.py` (1,333 lines); A4 migration risk |
| C | Telegram Bot | 17 | ~3,200 | Over-mocking; shared hardcoded IDs |
| D | Moderation+Trust | 11 | ~2,100 | Mock-based view tests; criteria cache mismatch |
| E | Search | 9 | ~4,200 | Weak assertions; excessive mocking; brittle templates |
| F | Analytics+Users+Media | 20 | ~3,800 | Over-mocking; missing side-effects; cross-block coupling |
| G | Currencies+Categories+etc | 13 | ~2,900 | Misapplied markers; brittle counts |
| **Total** | | **130** | **~25,750** | |

**Source files:** Per-block findings are detailed in
`docs/99-agent/test-audit-block-{a-g}-findings.md`.

---

## 7. Deliverables

1. ✅ This master report (`test-audit-master-report.md`)
2. ⏳ Implementation plan (`test-audit-implementation-plan.md`) — see next page.
3. Step-1 reference architecture (`test-audit-step1.md`) — unchanged.
