---
id: discrepancies-plan17-24-split
source: .ai/audit/problems/18_doc-update-discrepancies-plan17-24.md
domain: audit
tags:
  - documentation
  - code-quality
  - discrepancies
  - plans-17-24
related:
  - 18_doc-update-discrepancies-plan17-24.md
---

# Discrepancies Plans 17–24 — Split: Code Work vs. Documentation Work

## Purpose

Re-classification of the 10 discrepancies recorded in
`18_doc-update-discrepancies-plan17-24.md` into two mutually exclusive,
implementation-track action sets:

1. **Code improvements** — changes to source code required to bring the
   implementation into compliance with current project rules.
2. **Documentation improvements** — changes to docs/research artifacts
   required to make the written record match the implemented behavior.

The split is **verified against the current repository HEAD** (sources under
`src/backend/`, docs under `docs/`). Each item carries a status marker so
neither track re-does already-resolved work.

### Path note

The source audit uses the logical shorthand `apps/...` for the Python package
tree. The actual on-disk locations are under
`src/backend/apps/...`; both are given below. Doc paths are verbatim under
`docs/` and templates under `src/backend/templates/`.

### Status legend

| Marker | Meaning |
|---|---|
| **OPEN** | Verified in source/docs: the required change is still outstanding. |
| **ALREADY RESOLVED** | Verified in current repo: the prescribed doc/code state already exists; no action expected on this track (noted so the work is not duplicated). |
| **OPEN (code-level, assessed low-risk)** | Outstanding but judged a backward-compatible / non-functional refinement. |

---

## Quick mapping

| # | Finding (summary) | Track | Status | Anchor |
|---|---|---|---|---|
| 1 | Preferred-city cookie name is a `str` constant, not a `StrEnum` | **Code** | **OPEN** | `core/middleware/preferred_city.py:29` |
| 2 | `set_preferred_city` clear contract accepts both `action=clear` and empty `slug` | **Docs** | ALREADY RESOLVED | `ui-patterns.md:332` |
| 3 | Preferred-city cookie write is consent-gated | **Docs** | ALREADY RESOLVED | `ui-patterns.md:336`; `search/views/preferred_city.py:78` |
| 4 | `CookieCategory` StrEnum exists but is unused at runtime (plain string keys) | **Code** | **OPEN** | `core/enums.py:244`; `users/schemas.py:24-25`; `users/views/consent.py:155,203,242`; `users/services/consent_record.py:34` |
| 5 | Consent accept/decline are anonymous-accessible; withdraw is authenticated | **Docs** | ALREADY RESOLVED | consent research report:8-34; `users/views/consent.py:109,163,211` |
| 6 | Two non-JS assets load unconditionally (GLightbox CSS, privacy-page Plausible) | **Docs** | ALREADY RESOLVED (as documented) | `ads/detail.html:15`; `privacy.html:12` |
| 7a | Stale research reports contradict implementation | **Docs** | **OPEN** (city-selection §13.2) | `city-selection-report.md:472` |
| 7b | `consent-banner-gdpr-research-report.md` still lists D1–D9 as open | **Docs** | ALREADY RESOLVED | `consent-banner-gdpr-research-report.md:8-34,264-273` |
| 8 | ui-patterns says submenu loads via HTMX; code uses vanilla `fetch` | **Docs** | ALREADY RESOLVED | `ui-patterns.md:340-343`; `components/header_catalog.html:318` |
| 9 | ui-patterns documents `cat.get_children_count`; code uses `cat.get_children.exists` | **Docs** | ALREADY RESOLVED | `ui-patterns.md:295,342`; `components/header_catalog.html:95,161` |
| 10 | ui-patterns references a non-existent `24_catalog-header-auth-entry_spec.md` path | **Docs** | ALREADY RESOLVED | `components/header_catalog.html` (canonical template named at `ui-patterns.md:373`) |

---

## BLOCK 1 — Code improvements (coder)

Two findings require source changes. Both are direct consequences of
**project rule 10** ("All fixed values must use `Enum` or `StrEnum` instead of
dicts and lists… No inline string literals for constants anywhere in the
codebase" — see `src/backend/apps/core/enums.py:4-6`).

### 1. Preferred-city cookie name is a `str` constant, not a `StrEnum` — OPEN

- **Rule violated:** Rule 10 (StrEnum for fixed values). The module docstring of
  `core/enums.py` itself states "No inline string literals for constants
  anywhere in the codebase."
- **Current code** (`src/backend/apps/core/middleware/preferred_city.py:29`):
  ```python
  PREFERRED_CITY_COOKIE_NAME = "preferred_city"
  PREFERRED_CITY_COOKIE_MAX_AGE = 365 * 24 * 60 * 60  # 1 year
  ```
  `PREFERRED_CITY_COOKIE_MAX_AGE` is an `int` constant (not a fixed-value
  vocabulary — acceptable). The cookie **name** is the fixed-value vocabulary
  that rule 10 targets.
- **Assessment:** The audit marks this "per-plan decision, not a defect" (Plan
  17 D-P1 deliberately mirrored `LanguagePreMiddleware`). This is a
  **rule-compliance gap**, not a behavioral bug — but rule 10 is unconditional,
  so it belongs on the code track. Note city-selection report §13.2 line 478
  independently lists "Extract cookie name into a StrEnum constant (project
  rule compliance)" as a required implementation step — confirming this is a
  known, outstanding code task.
- **Required change (what):** Introduce a `StrEnum` for preferred-city cookie
  identifiers in `apps/core/enums.py` (e.g. a `PreferredCityCookie(StrEnum)`
  with a `NAME` member equal to `"preferred_city"`), and migrate all four
  reference sites to it, removing the plain `str` constant:
  - `core/middleware/preferred_city.py` (definition site; lines 29, 64, 78)
  - `search/views/preferred_city.py` (import + use; lines 17-18, 52, 80)
  - `users/views/consent.py` (login reconciliation; lines 34, 331)
  - `core/tests/test_preferred_city_middleware.py` (test fixtures; lines 26, 56, 72, 88, 108, 117, 126-127, 133, 141, 147, 164)
- **Acceptance:** `consent_preferences == "true"` cookie-gating behavior (finding #3) is unaffected; cookie read/write/delete paths resolve to the same string value `"preferred_city"`.

### 4. `CookieCategory` StrEnum is defined but unused at runtime — OPEN

- **Rule violated:** Rule 10 + the DTO/validation rule (rule 11). An enum
  exists and is exported in `__all__` but the runtime code writes plain
  `str` keys.
- **Current code:**
  - `apps/core/enums.py:244-249` defines `CookieCategory`
    (`ESSENTIAL`/`ANALYTICS`/`PREFERENCES`, values `"essential"`,
    `"analytics"`, `"preferences"`) and exports it (`enums.py:269`).
  - `apps/users/schemas.py:24-25` (`ConsentSubmission`) models categories as
    two bare `bool` fields:
    ```python
    analytics: bool = False
    preferences: bool = False
    ```
  - `apps/users/views/consent.py` builds the category map with **literal string
    keys** at all three call-sites:
    ```python
    categories={"analytics": analytics, "preferences": preferences},   # lines 155, 203
    categories={"analytics": False, "preferences": False},            # line 242
    ```
  - `apps/users/services/consent_record.py:34` types the parameter as
    `categories: dict[str, bool]` and stores it verbatim.
  - Tests assert the **string-keyed shape**
    (`users/tests/test_consent_records.py:42,52,62`).
- **Assessment:** "Minor code-level inconsistency, not a functional gap" per
  the audit: the string values happen to equal the enum values, so stored data
  is consistent. It is still a rule-10/11 violation: the enum is documentation
  only and the string keys are duplicated literals.
- **Required change (what):** Make `CookieCategory` the single source of truth
  at the system boundary and service layer:
  - Bind `ConsentSubmission` category fields to the `CookieCategory` vocabulary
    (typed keys/values) so the DTO validates against the enum rather than
    free-form string keys.
  - Pass `categories` keyed by `CookieCategory` members in the three
    `consent_accept` / `consent_decline` / `consent_withdraw` call-sites
    (`users/views/consent.py`).
  - Update `record_consent_action` (`users/services/consent_record.py`) to
    accept the enum-typed mapping.
  - **Data-shape constraint (must NOT change):** the persisted JSONB/
    `dict` keys stored on `ConsentRecord.categories` must remain the string
    values `"essential"`, `"analytics"`, `"preferences"` (i.e. `member.value`),
    so downstream consumers (context processor `consent_state` reads
    `consent_analytics`/`consent_preferences`, `consent-banner-gdpr-research-report.md:211`
    table) and existing tests keep working without a migration.
- **Acceptance:** `ConsentChoice` is already used correctly at runtime (audit
  confirms) — it stays as the audit-log `choice` column vocabulary; only
  `CookieCategory` needs to be wired into the runtime path.

> Both code items are rule-compliance refactors. Neither changes observable
> behavior; neither blocks release. They should be paired with the existing
> test suite (`core/tests/test_preferred_city_middleware.py`,
> `users/tests/test_consent_records.py`, `ads/tests/test_script_gating.py`,
> `ads/tests/test_gallery_markup.py`).

---

## BLOCK 2 — Documentation improvements (writer)

Documentation-track items. All are documented-state corrections in `docs/`
research/spec artifacts or template prose. **Six of eight are already present
in the current repo** (the doc-update task, or later edits, already applied
them); only the city-selection research report §13.2 remains open.

### 2. Document the dual `set_preferred_city` clear contract — ALREADY RESOLVED

- **What was to be done:** Document that clearing is signaled by **both**
  `action=clear` **and** a present-but-empty `slug` (`{"slug": ""}`), and that a
  *missing* `slug` with no `action` still returns `400 invalid_city`.
- **Current state:** `docs/01-spec/ui-patterns.md:332` already reads:
  > "Вся страна" clears the preference (`POST search:preferred_city` with
  > `action=clear`, or an empty `slug`).
- **Status:** Resolved. The implementation (`search/views/preferred_city.py:46-59`)
  matches and the doc reflects it.

### 3. Document consent-gating of the preferred-city cookie — ALREADY RESOLVED

- **What was to be done:** Document that the `preferred_city` cookie is
  consent-gated (`consent_preferences` cookie required); the authenticated
  `User.preferred_city` FK is not gated.
- **Current state:** `ui-patterns.md:336` reads: "The cookie is consent-gated
  (`consent_preferences` required)"; implementation is at
  `search/views/preferred_city.py:78` (`if request.COOKIES.get("consent_preferences") == "true"`);
  authenticated persistence at `preferred_city.py:66-70`.
- **Status:** Resolved.

### 5. Consent accept/decline are anonymous-accessible; withdraw is authenticated — ALREADY RESOLVED

- **What was to be done:** Record that `consent_accept`/`consent_decline` are
  `@require_POST` and anonymous-accessible (no `@login_required`), while
  `consent_withdraw` retains both `@login_required` and `@require_POST`.
- **Current state:** Decorators verified in `users/views/consent.py` —
  `consent_accept` `@require_POST` (line 109), `consent_decline` `@require_POST`
  (line 163), `consent_withdraw` `@login_required` + `@require_POST` (lines
  211-212). The consent research report already records this at
  `consent-banner-gdpr-research-report.md:17-18` and the Risk Matrix at line 267.
- **Status:** Resolved.

### 6. Partial D7 — two non-JS assets load unconditionally — ALREADY RESOLVED (as documented)

- **What was to be done:** Document that Plausible + GLightbox **JS** are
  consent-gated, and note the GLightbox CSS `<link>` and the `/privacy/`
  Plausible snippet load unconditionally (low-risk progressive-enhancement
  fallback).
- **Current state:**
  - GLightbox JS + inline init gated behind `{% if consent_analytics %}` —
    `ads/detail.html:112-117`.
  - Plausible JS gated behind `{% if consent_analytics and PLAUSIBLE_HOST %}`
    in the 11 site templates (cabinet/settings, cabinet/search_history,
    cabinet/saved_search_edit, admin/moderation/review, analytics/moderation_dashboard,
    analytics/seller_dashboard, ads/dashboard, ads/detail, ads/list, +2 others).
  - **Still ungated (by design, low-risk):** GLightbox CSS at
    `ads/detail.html:15`; Plausible on `privacy.html:12` (`{% if PLAUSIBLE_HOST %`).
- **Status:** Resolved as documentation. The consent research report already
  captures the partial state at `consent-banner-gdpr-research-report.md:24-26`
  and `271`. (If a future decision gates the CSS too, that is a new consent
  task, not part of this discrepancy set.)

### 7a. City-selection research report §13.2 Implementation steps — **OPEN**

- **What was to be done:** Correct stale prescriptive content in the
  city-selection research report that contradicts the implemented layout.
- **Current state:**
  - §1.3 "Implementation Status" (lines 33-38) **already corrected**: cites the
    right path `apps/core/middleware/preferred_city.py`, notes 1-year max-age,
    and notes consent-gating.
  - §11.2 (lines 36-38) **already corrected**: "The original §11.2 value of 30
    days and the '30-day cookie' plan text were superseded."
  - **`§13.2 "Implementation steps"` (line 472) STILL STALE** — prescribes:
    > "1. Create `src/backend/apps/search/middleware/preferred_city.py` with
    > PreferredCityMiddleware…"
    (wrong path; actual is `src/backend/apps/core/middleware/preferred_city.py`),
    and line 478 still lists "Extract cookie name into a StrEnum constant (project
    rule compliance)" as an open step (this is code item #1).
  - Appendix F (line 533) is already correct (`src/backend/apps/search/views/...`
    with max_age=31536000 / 1 year).
- **Required doc action:** Update §13.2 line 472 to the correct middleware path
  (`apps/core/middleware/preferred_city.py`) and mark the StrEnum step (line
  478) as resolved **iff/when code item #1 is completed**; otherwise leave it as
  a tracked dependency on the code track.

### 7b. Consent research report defect list — ALREADY RESOLVED

- **What was to be done:** Expand the consent research report's "Implementation
  Status" to cover all D1–D9 defects resolved by Plan 21.
- **Current state:** The report now contains a top-level "Implementation Status
  (Plan 21 …)" block (`consent-banner-gdpr-research-report.md:8-34`) covering
  D-ENUMS, D-audit, D-views (T-05, D2), D-cookies, D4, D7 (partial), D9, and
  re-prompt; plus a "Compliance Risk Matrix" (lines 264-273) marking each prior
  defect Resolved/Partial; plus Missing Components #4 marked RESOLVED
  (lines 279, 312).
- **Status:** Resolved. No further doc action on the consent report.

### 8. Submenu loading mechanism — HTMX vs vanilla fetch — ALREADY RESOLVED

- **What was to be done:** Correct ui-patterns from "injected via HTMX swap" to
  vanilla `fetch` + `innerHTML`.
- **Current state:** `ui-patterns.md:340-343` already reads:
  > "fetched on first expand via `GET /categories/<slug>/submenu/` and injected
  > into the panel with vanilla JS (`container.innerHTML = html`) … HTMX is used
  > only for the autocomplete search, not the category accordion."
  Implementation confirmed in
  `components/header_catalog.html:318` (`fetch('/categories/' + … + '/submenu/')`).
- **Status:** Resolved.

### 9. Stale template helper reference (`get_children_count` → `get_children.exists`) — ALREADY RESOLVED

- **What was to be done:** Update the ui-patterns example from
  `{% if cat.get_children_count %}` to `{% if cat.get_children.exists %}`.
- **Current state:** `ui-patterns.md:295` (template snippet) and `:342` (prose)
  already use `cat.get_children.exists`; implementation confirmed at
  `components/header_catalog.html:95,161` and `mega_submenu.html:16`.
- **Status:** Resolved.

### 10. Dangling spec-file cross-reference — ALREADY RESOLVED

- **What was to be done:** Point the ui-patterns cross-reference to the
  authoritative spec or drop it.
- **Current state:** The current `ui-patterns.md` no longer contains the
  dangling `24_catalog-header-auth-entry_spec.md` reference. The Auth-Entry
  requirement is instead stated as "Auth Entry in Catalog Header (R-06,
  Spec 24)" (`ui-patterns.md:354`) with the canonical template named at
  `ui-patterns.md:373` (`components/header_catalog.html`). The authoritative
  spec lives at `.ai/problems/24_catalog-header-auth-entry_spec.md`.
- **Status:** Resolved.

---

## Notes for implementation planning

- The two **Code** items (#1, #4) are the only items that touch source and are
  the only ones blocking a "rule-10 clean" state. Both are zero-behavior-change
  refactors and can be scheduled independently of release. They share a test
  burden: `core/tests/test_preferred_city_middleware.py` (#1) and
  `users/tests/test_consent_records.py` (#4 must keep the persisted
  string-keyed shape).
- Of the **Docs** items, only **#7a** (city-selection §13.2 path + StrEnum step)
  remains OPEN; it is also the bridge to code item #1 (line 478's "Extract cookie
  name into a StrEnum constant" becomes a done check-box once #1 ships).
- Findings #2, #3, #5, #6, #7b, #8, #9, #10 are recorded as
  **ALREADY RESOLVED** purely so the doc track does not chase ghosts — their
  prescribed content already exists in the current `docs/` tree.

---

## Developer Scope Guidance (filtered)

> **Principle:** Do not change code merely to satisfy outdated documentation.
> Touch code only where an identified discrepancy reflects genuine
> architectural debt, duplicated logic, or a breach of the unified
> consent/security contract.

### 🔴 In-scope: Mandatory code work

1. **#6 — Consent / analytics gating (high)**
   Close the behavioral gap across all pages:
   - `privacy.html` must gate Plausible behind `consent_analytics` like every
     other page.
   - Audit the full chain: consent backend → template context → analytics
     scripts → third-party resource loads.
   - Decision point for GLightbox CSS: CSS is not analytics; either gate it
     uniformly under `consent_preferences` or document the deliberate exception.

2. **#3 — Preferred-city consent lifecycle (high)**
   Verify the complete state machine, not just the happy-path write:
   - Anonymous vs. authenticated user.
   - Grant → revoke → re-grant consent transitions.
   - Stale `preferred_city` cookie surviving a consent revocation.
   - City change / clearing edge cases under each consent state.

### 🟠 In-scope: Architectural hygiene

3. **#4 — Wire `CookieCategory` into runtime (medium)**
   Replace string literals (`"analytics"`, `"preferences"`, `"essential"`)
   with `CookieCategory` values in: `ConsentSubmission`,
   `record_consent_action`, schemas, services, audit log, serialization.
   Preserve the persisted string-keyed shape (no migration needed).

4. **#2 — Collapse duplicate clear contract (medium)**
   Investigate who emits `{"slug": ""}` vs. `{"action": "clear"}`.
   If no live client sends `slug=""`, remove it as the deprecated duplicate.
   If consumers exist, mark it as legacy/compat explicitly.

### 🟡 Verification-only (no required change)

5. **#1 — `PREFERRED_CITY_COOKIE_NAME` vs. StrEnum (low)**
   Assess project-wide convention: where do module-level constants live vs.
   `StrEnum`? Decide on one style; apply consistently. Do NOT change purely
   for rule-10 optics if the constant approach is the established pattern.

6. **#7 — Legacy research-report verification (check)**
   Do NOT edit the reports. Validate the stated D1–D9 against current code and
   tests; confirm they are genuinely closed.

### 🟢 Out of scope (docs only)

- #8 — HTMX submenu: `fetch()` is acceptable. Update docs only.
- #9 — `get_children.exists`: code already correct. Update docs only.
- #10 — Dangling spec cross-reference: fix the doc link, no code change.

### Summary for the developer

**Mandatory:** #6 → #3.
**Improve:** #4 → #2.
**Verify:** #1, D1–D9 from #7.
**Do not touch code for:** #8, #9, #10 (documentation track only).
