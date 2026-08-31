# Search Patterns Test Verification — Detailed Implementation Plan

> **Purpose:** Decomposes the 11 test blocks from `01_search_patterns_test_verification_top_plan.md` into implementation-ready plan sections, each grounded in verified source-code evidence. This document is the canonical execution artifact — it consolidates per-block findings, priorities, dependencies, and a consolidated implementation roadmap.

**Generated from:**
- Top plan: `.ai/problems/01_search_patterns_test_verification_top_plan.md`
- Live verification report: `.ai/problems/01_search_patterns_verification.md` (bugs B1–B7)
- Research docs: `.ai/research/search-journeys-{our-architecture,spec,validation}.md`
- Spec: `.ai/problems/15_search_patterns_spec.md`

**Process:** Each block was researched by a Researcher agent (R) → findings fed to this Planner pass. Per-block section files in `.ai/plans/_blocks/` contain the detailed findings tables. This document assembles the consolidated roadmap.

**Note:** No test code was written. This plan specifies *what* to test and *where*; test implementation is downstream work.

---

## Journey → Block Mapping (from top plan)

| Journey Group | Journey Group Name | Covered Block(s) |
|---|---|---|
| G1 | Search Entry Points & Landing States | Block 1 |
| G2 | Autocomplete Suggestions | Block 2 |
| G3 | Header Search Submission (q-only, context drop) | Block 3 |
| G4 | FTS Results, Relevance Ordering & Side Effects | Block 3, Block 4 |
| G5 | Category Browsing & Context Scoping | Block 4 |
| G6 | Filter Application | Block 5 |
| G7 | Sorting & Price Ordering | Block 6 |
| G8 | Filter Chips & Removal | Block 5 |
| G9 | Clear All Filters | Block 5 |
| G10 | URL State, Pagination & Back/Forward | Block 7 |
| G11 | Preferred City & Did-You-Mean | Block 8 |
| G12 | Language Switching & Per-Language FTS | Block 9 |
| G13 | Search History | Block 10 |
| G14 | Saved Search Modal & Alerts | Block 11 |

---

## Verified Bugs (from live verification report)

| Bug | Severity | Description | Location | Block(s) affected |
|---|---|---|---|---|
| B1 | Medium | CSRF token leaks into URL on GET search form submit | `header_catalog.html:115` | 1, 3 |
| B2 | Medium | No explicit clear button — native clear-X does nothing | `header_catalog.html:117-130` | — (open PO-1 decision) |
| B3 | Medium | Header search form drops category/city/filter context | `header_catalog.html:114-132` | 1, 3, 4 |
| B4 | Medium | Sort dropdown hidden when `q` present; `sort=` ignored on FTS | `filter_form.html:103`; `search.py:155-182` | 3, 6 |
| B5 | Low | `value="None"` on min/max price inputs | `filter_form.html:50-51,56-57` | 1, 5 |
| B6 | Medium → RESOLVED by explicit code fix (NOT by migration) | `htmx.get` is not a real HTMX API in any version; requires `htmx.get` → `htmx.ajax('GET', ...)` at `header_catalog.html:536` | `header_catalog.html:536`; runtime `list.html:16` | 1 (stale-line correction) |
| B7 | Low | `lang=ru` dropped from URL on HTMX pagination | `ad_list.html:64-65,71-72,142-169` | 7, 9 |

---

## Consolidated Roadmap Table

| Priority | Block | Variations | Key Tasks | Dependencies | Owner |
|---|---|---|---|---|---|
| **P0** | **3** | V5 (AnalyticsEvent gap) | Add test asserting `AnalyticsEvent(SEARCH_PERFORMED)` created after `GET /search/?q=…` | Blocks 2, 4 | Test Engineer |
| **P0** | **8** | V5 (did-you-mean on search) | Fix `search.py:81` — replace echo with `_suggest_city()` call; add test for `/search/?city=<invalid>` → fuzzy suggestion + corrected banner link | 3, 7 | Implementor + Test Engineer |
| **P1** | **1** | B1 (CSRF leak) | Remove `{% csrf_token %}` from GET header search form (`header_catalog.html:115`); assert AJAX `X-CSRFToken` header path intact (`list.html:19`, `detail.html:23`) | — | Implementor |
| **P1** | **6** | V1 (FTS-hidden-sort B4) | Test: `/search/?q=term&sort=price_asc` → rank-ordered not price-ordered; sort dropdown absent | 3, 5, 7 | Test Engineer |
| **P1** | **5** | V2 (chip removal bugs) | Fix purpose chip (drop condition collateral) + condition chip (no-op re-add) at `ad_list.html:41-42,53-54`; add URL-composition tests | 3, 4, 6, 7 | Implementor + Test Engineer |
| **P2** | **2** | V5b/V18 (keyboard nav) | Playwright infra prerequisite; test ArrowDown/Enter/Escape on autocomplete dropdown | 1, 10 | Test Engineer (blocked on Playwright) |
| **P2** | **10** | V5a (no prefix filter) | Add `prefix` param to `get_user_search_history`; filter user_history by typed prefix; test both auth + anon paths | 2, 3 | Implementor + Test Engineer |
| **P2** | **4** | V1 (subtree filter) + V2 (constrained option sets) | Test `/category/<slug>/` scope + resolver ancestor-walk; catalog fixture coordination | 3, 5 | Test Engineer |
| **P2** | **5** | V5 (EUR price `int()` rejects decimals) | Decision gate: `Decimal` parsing vs. `step="1"`; add test for silent decimal rejection | — | Product + Implementor |
| **P2** | **6** | V2 (price sort direction) | Test `price_asc`=lowest-first, `price_desc`=highest-first on `/` and `/search/` | 3, 5, 7 | Test Engineer |
| **P2** | **9** | V4 (toggle drops params) | Fix `language_switcher.html:40` — append `&lang=` to current search instead of replacing; test param preservation | 7 | Implementor + Test Engineer |
| **P3** | **1** | B5, B6, G3, G4 | Fix `value="None"` (filter_form.html); Implementor must explicitly fix `htmx.get` → `htmx.ajax('GET', ...)` at `header_catalog.html:536` — NOT automatic via CDN bump; add back-link + telegram-href tests | — | Implementor + Test Engineer |
| **P3** | **2** | V2 (locale-aware entity filtering) | Document as known gap OR fix `entity_suggestions.py` to filter locale-appropriate names; test non-RU prefix matching | 9 | Product decision |
| **P3** | **5** | V1, V6, B1, B5 | Add URL-composition tests for clear-all; fix `value="None"`; template-source CSRF guard test | 3, 4, 6, 7 | Test Engineer |
| **P3** | **8** | V3 (consent-revoke cookie clear) | Add test: `POST /consent/withdraw/` clears `preferred_city` cookie | — | Test Engineer |
| **P3** | **8** | V4 (listings did-you-mean) | Assert banner behavior + difflib limitation (transposition misses at 0.6 cutoff) | — | Test Engineer |
| **P3** | **9** | V3 (SameSite gap + consent gate gap) | Decision: set `samesite="Lax"` explicitly + consent-gate session write | — | Product decision |
| **P3** | **10** | V1, V3, V4, V6 + T1–T7 | Test coverage completion: empty-query no-op, normalization, no-merge-on-login, 50-cap, history page ordering/cap/href, clear-history 405/login/isolation | 3 | Test Engineer |
| **P3** | **11** | V1, V2, V4, V5, V6 | Modal visibility + pre-fill tests; cross-user edit 404; chat_id=None skip test; dry-run-with-existing-notifications dedup test; frequency decision gate | 3, 5, 10 | Test Engineer |
| **P4** | **7** | B7 (lang in pagination URLs) | Add `{% if LANGUAGE_CODE %}&lang={{ LANGUAGE_CODE }}{% endif %}` to 9 links in `ad_list.html`; test lang preserved in pagination URLs | — | Implementor + Test Engineer |
| **P4** | **7** | V4 (listings page-param), V8 (URL-content), V9 (deep-linking), V10 (Playwright Back/Fwd) | Page validation on listings; param-preservation assertion; deep-link rendering; Back/Forward Playwright | 5, 6 | Test Engineer |
| **P4** | **9** | V1 (per-language FTS) | Test `/search/?lang=bs&q=<bs-term>` → `search_vector_bs` results; `/search/?lang=en` → `search_vector_en` | 3 | Test Engineer |
| **P4** | **11** | V6 (frequency cadence) | Decision gate: weekly option? + assert `last_notified_at` is write-only (daily command ignores it); dedup via notification table | — | Product decision |

---

## Per-Block Summary

Detailed findings, test-engineer tasks, existing-test citations, and validator recommendations are in the per-block section files:

| Block | Section File | Priority | Status |
|---|---|---|---|
| 1 — Entry Points & Landing States | `.ai/plans/_blocks/block_01.md` | Low–Medium | ✅ Planned |
| 2 — Autocomplete Suggestions | `.ai/plans/_blocks/block_02.md` | High | ✅ Planned |
| 3 — Search Submission & FTS Results | `.ai/plans/_blocks/block_03.md` | High | ✅ Planned |
| 4 — Category Browsing & Context Scoping | `.ai/plans/_blocks/block_04.md` | Medium | ✅ Planned |
| 5 — Filter Controls, Chips & Management | `.ai/plans/_blocks/block_05.md` | Medium | ✅ Planned |
| 6 — Sorting & Price Ordering | `.ai/plans/_blocks/block_06.md` | Medium | ✅ Planned |
| 7 — URL State, Pagination & Navigation | `.ai/plans/_blocks/block_07.md` | Medium | ✅ Planned |
| 8 — Preferred City & Did-You-Mean | `.ai/plans/_blocks/block_08.md` | High | ✅ Planned |
| 9 — Language Switching & Per-Language FTS | `.ai/plans/_blocks/block_09.md` | Medium | ✅ Planned |
| 10 — Search History | `.ai/plans/_blocks/block_10.md` | Medium | ✅ Planned |
| 11 — Saved Search Modal & Alerts | `.ai/plans/_blocks/block_11.md` | Medium | ✅ Planned |

---

## Key Deviations from Top Plan (Researcher-confirmed)

| # | Deviation | Corrected Fact | Block |
|---|---|---|---|
| D1 | Plan says per-language FTS at `/?lang=bs&q=` | FTS lives at `/search/?q=` (not homepage `/`); homepage is a category/city-filtered listings view with no FTS | 9 |
| D2 | Plan claims "email per user preference" for alert delivery | Exhaustive source search finds ZERO email/SMTP — all delivery is Telegram-only via `chat_id` (`immediate_alerts.py:180-184`, `send_alerts.py:164-168`) | 11 |
| D3 | B6 line references cite 1062-1070 | Stale — file refactored to 549 lines; actual `htmx.get` at `header_catalog.html:536` | 1 |
| D4 | Live report claims `/city/budava/` → 301 redirect | Stale — current source renders 200 banner via `listings.py:292-299`; no redirect exists; spec + tests agree with banner | 8 |
| D5 | Plan: "each suggestion has `text`, `source`, `type`" | `type` field absent on `user_history` (`autocomplete.py:66-69`) and `popular_search` (`popular_search.py:73-79`); only category/city carry it | 2 |
| D6 | `features` slugs without `|urlencode` in pagination links | `ad_list.html:64-65,142-169` emit raw `{{ fslug }}`; low risk (ASCII slugs) but inconsistent with `{{ query|urlencode }}` | 7 |
| D7 | Plan: "daily/weekly cadence per saved search" | No `frequency` field exists; no weekly option; `last_notified_at` never read for gating; dedup via notification table only | 11 |
| D8 | HTMX 2.0 migration assumed to resolve B6 | FALSE — `htmx.get()` is not a real HTMX API in 1.9.12 *or* 2.0.x (audit `full_htmx_report.md` §D1: 0 matches in the public API object of either version, absent from `htmx.org/api/`). The `header_catalog.html:536` `TypeError` is a pre-existing latent bug, not a 2.x break; a CDN bump to 2.0.x alone leaves it broken and requires an explicit `htmx.get` → `htmx.ajax('GET', …)` code fix. Conversely, `htmx.ajax()` IS preserved in 2.0.x (`htmx.ajax = ajaxHelper` at `cabinet/favorites.html:47` — no change needed) and `addEventListener('htmx:afterRequest'/'htmx:afterSwap')` fires both camelCase and kebab-case in 2.0 (no listener changes needed). Stale comments claiming "HTMX 1.9.12 has no hx-on" (`header_catalog.html:4`, `favorite_heart.html:29-30`, `test_favorites.py:95`) are also factually wrong — `hx-on` is handled in 1.9.12. | 1 |

> **HTMX 2.0 migration correction (B6):** Per the audit report (`.ai/audit/problems/full_htmx_report.md`) and the migration findings (`.ai/plans/_blocks/_htmx2_migration_findings.md`), the HTMX 2.0 upgrade is a straightforward CDN tag bump across 5 templates, but it does **not** auto-resolve B6. `htmx.get()` was never a real HTMX API in any version; the implementor must apply the one-line call-site fix at `header_catalog.html:536` regardless of the version bump. `htmx.ajax()` is preserved in 2.0.x and the `addEventListener` event-name references need no changes.

---

## Open Product Decisions (affect test scope)

1. **Sort on FTS results** (B4) — Currently hidden/ignored. Tests assert *current* behavior (sort ignored when `q` present). Awaiting decision: should FTS results support sorting?
2. **Clear-X button** (B2) — Native clear-X does nothing. Awaiting decision: `history.back()` vs `/`.
3. **Header-search context preservation** (B3) — Currently drops category/city/filters. Tests assert *drop* behavior. Awaiting decision: should header search preserve context?
4. **Autocomplete popular gate** — `min_hit_count=10` makes popular empty on low-traffic instances. Tests assert the gate rule as-is.
5. **Entity locale-aware filtering (Block 2 V9)** — `name__istartswith` filters Russian `name` only; non-RU prefixes match nothing. Awaiting decision: document as gap vs. fix to filter locale-appropriate names.
6. **Language toggle param preservation (Block 9 V4)** — Currently replaces entire query string. Awaiting decision: preserve `q`/filters when switching language.
7. **Price input parsing (Block 5 V5)** — `int()` rejects decimals despite `step="0.01"`. Awaiting decision: `Decimal` parsing vs. `step="1"`.
8. **Cookie consent gating (Block 9 V3 Gap B)** — Server writes session `django_language` unconditionally on `?lang=`, ignoring `consent_preferences`. Awaiting decision: consent-gate the session write.
9. **Alert frequency (Block 11 V6)** — Plan claims daily/weekly cadence; no `frequency` field exists. Awaiting decision: implement frequency field or correct the spec.

---

## Definitions of Done

- **Researcher pass:** Each block verified against source code (`file:line` citations); bugs confirmed or corrected; gaps mapped. ✅ Complete for all 11 blocks.
- **Planner pass:** Each block section file written to `.ai/plans/_blocks/block_0N.md` with findings table, priority, dependencies, and validator recommendations. ✅ Complete for all 11 blocks.
- **Consolidated plan:** This document assembles the roadmap + deviations. ✅ Complete (this file).
- **Implementation:** Test code NOT yet written — this plan specifies *what* to test and *where*; actual test implementation is the downstream Test-Engineer task per block.

---

## Next Steps

1. Assign blocks to Test Engineers per the roadmap (P0 items first: Block 3 V5, Block 8 V5).
2. P0 bug fixes (B1, B4, Block 5 V2 chip bugs, Block 8 V5 did-you-mean) require Implementor intervention — these should land before or alongside their tests.
3. Coordinate on shared surfaces: `header_catalog.html` (B1, B6), `ad_list.html` 9-link invariant (B7, Block 5 V2, Block 6 V4, Block 7 V5/V8), `search.py` side-effects (Block 3 V5, Block 10 V1).
4. Establish Playwright infrastructure (Block 2 V5b/V18, Block 7 V10) as a cross-cutting prerequisite before client-side interaction tests.
5. Resolve open product decisions — tests for B2, B3, B4, Block 2 V9, Block 9 V4, Block 9 V3 Gap B, Block 11 V6 must assert either current behavior or the decided behavior.
