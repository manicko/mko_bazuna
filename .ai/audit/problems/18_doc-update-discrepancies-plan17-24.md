---
id: discrepancies-plan17-24
domain: audit
tags:
  - documentation
  - discrepancies
  - plans-17-24
related:
  - 17_doc-update-discrepancies-plan14-16
---

# Discrepancies: Plans 17–24 vs. Current Implementation

## Context

This report captures deviations between the development plans/specs
(`17_preferred-city`, `20_catalog-menu-breadcrumb-fix`, `21_consent-banner-compliance`,
`22_catalog-menu-breadcrumb-fixes`, `22_seed-category-coverage`, `23_preferred-city-reset`,
`24_catalog-header-auth-entry`) and the **actual implemented code**, identified during
the documentation-update task. Deviations are recorded where they change how the
implemented functionality must be documented.

---

## 1. Preferred-city cookie name is a module constant, not a StrEnum

- **Planned:** Plan 17 (D-P1) and the city-selection research report §12.4 note the
  cookie name "preferred_city" should be a `StrEnum` (project rule 10).
- **Implemented:** `PREFERRED_CITY_COOKIE_NAME` is a **module-level `str` constant** in
  `apps/core/middleware/preferred_city.py` (not a `StrEnum`). Plan 17 D-P1 deliberately
  kept it as a plain constant mirroring `LanguagePreMiddleware`.
- **Assessment:** Per-plan decision, not a defect. The research report's characterization
  ("hardcoded string") is inaccurate — it is a named shared constant, but still not a
  `StrEnum`.
- **Documentation impact:** Describe the cookie name as a shared module constant
  (`PREFERRED_CITY_COOKIE_NAME` in `apps/core/middleware/preferred_city.py`), not a
  `StrEnum` and not an inline hardcoded string.

## 2. `set_preferred_city` clear contract is broader than Plan 23

- **Planned:** Plan 23 T-01 specifies clearing via `POST {action: clear}` (Decision D-P1).
- **Implemented:** `set_preferred_city` (`apps/search/views/preferred_city.py`) accepts **both**
  `action=clear` **and** a present-but-empty `slug` (`{"slug": ""}`) as a clear signal.
  A *missing* `slug` key (no `action`) still returns `400 invalid_city`.
- **Assessment:** Backward-compatible extension; the header "Вся страна" item posts
  `action=clear` only.
- **Documentation impact:** Document both clear signals (explicit `action=clear` and an
  empty `slug`); note the missing-slug case remains `400`.

## 3. Preferred-city cookie write is consent-gated (added after Plan 17)

- **Planned:** Plan 17 makes no mention of consent-gating the `preferred_city` cookie.
- **Implemented:** `set_preferred_city` only calls `response.set_cookie(...)` for the
  cookie when `request.COOKIES.get("consent_preferences") == "true"`
  (`apps/search/views/preferred_city.py`). Authenticated users' DB preference (`User.preferred_city`)
  persists regardless of cookie consent.
- **Assessment:** A post-Plan-17 refinement that resolves the consent research report's
  §5/Missing-Components #4 recommendation via source-gating (not a blocking middleware).
- **Documentation impact:** Document that the `preferred_city` cookie is consent-gated
  (`consent_preferences` cookie required); the authenticated `User.preferred_city` FK is
  not gated.

## 4. `CookieCategory` StrEnum is defined but unused at runtime

- **Planned:** Plan 21 (D-ENUMS) adds `ConsentChoice` and `CookieCategory` `StrEnum`s to
  `apps/core/enums.py`, re-exported via `__all__`, with category cookies keyed by the enum.
- **Implemented:** Both enums exist in `apps/core/enums.py` (lines ~236, ~244) and are
  exported. However, `ConsentSubmission` (in `apps/users/schemas.py`) and
  `record_consent_action` (`apps/users/services/consent_record.py`) use **plain string
  keys** (`"analytics"`, `"preferences"`) for the category flags — the `CookieCategory`
  enum values are never referenced at runtime. `ConsentChoice` **is** used (passed to
  `record_consent_action`).
- **Assessment:** `CookieCategory` is effectively documentation-only; a minor code-level
  inconsistency, not a functional gap (the cookie/string values still match the enum values).
- **Documentation impact:** Document `ConsentChoice` as the enum backing the audit-log
  `choice` column; note `CookieCategory` exists in `enums.py` as the category vocabulary
  (essential/analytics/preferences) but is not currently referenced by runtime code.

## 5. Consent views are anonymous-accessible (Plan 21 T-05 ships with T-02)

- **Planned:** Plan 21 T-02 adds `@require_POST` to `consent_accept`/`consent_decline`
  (kept `@login_required`); T-05 removes `@login_required` so anonymous users can consent
  via cookies only. Both land together.
- **Implemented:** `consent_accept` and `consent_decline` have `@require_POST` and **no**
  `@login_required` (anonymous POST allowed, cookie-only). `consent_withdraw` retains both
  `@login_required` + `@require_POST` (withdrawal is account-level). Verified in
  `apps/users/views/consent.py` (lines ~163, ~211, ~263).
- **Assessment:** Matches plan (release gate D-2 satisfied).
- **Documentation impact:** None beyond recording that accept/decline are anonymous-accessible
  POST endpoints, withdrawal is authenticated.

## 6. Script gating leaves two non-essential assets ungated

- **Planned:** Plan 21 D7/T-06b gates Plausible and GLightbox scripts behind
  `consent_analytics`.
- **Implemented:** Plausible is gated via `{% if consent_analytics and PLAUSIBLE_HOST %}`
  in 11 templates; GLightbox **JS** + inline init are gated behind `{% if consent_analytics %}`
  in `ads/detail.html`. However, two **non-JS** assets remain ungated: the GLightbox
  **CSS `<link>`** in `detail.html` `<head>` (always loaded), and Plausible on
  `privacy.html` (line 12, no consent context).
- **Assessment:** Partial D7. CSS is non-executable and low-risk; the `privacy.html`
  omission is a public-info page. The significant control (script/behavior gating) is in place.
- **Documentation impact:** Document that Plausible + GLightbox **JS** are consent-gated;
  note the GLightbox CSS link and the privacy page Plausible snippet load unconditionally
  (low-risk, progressive-enhancement fallback).

## 7. Stale research reports contradict the implementation

- **Planned/Research:** `docs/07-design-researches/Design_03/city-selection-report.md`
  §11.4 (line ~468) directs readers to create the middleware at
  `src/backend/apps/search/middleware/preferred_city.py`.
- **Implemented:** the middleware lives at `apps/core/middleware/preferred_city.py`.
  The report's own "Implementation Status" block (lines ~33-39) correctly cites
  `apps/core/middleware/`, but §11.4 and Appendix F still reference the wrong path and a
  stale 30-day `max_age`.
- **`consent-banner-gdpr-research-report.md`** still lists every D1–D9 defect as open
  ("/privacy/ returns 404", "consent views accept GET", "dead `consent_given` cookie",
  "banner guard missing on 5 templates", etc.) even though Plan 21 implemented all of them.
  Only the `preferred_city` consent-gating note was added.
- **Assessment:** Documentation drift — the research artifacts describe the pre-implementation
  defect state and are misleading.
- **Documentation impact:** Correct the middleware path + `max_age` in the
  city-selection report; expand the consent research report's "Implementation Status"
  block to cover all D1–D9 defects resolved by Plan 21.

## 8. Doc/code mismatch: submenu loading mechanism in ui-patterns

- **Planned/Doc:** `docs/01-spec/ui-patterns.md` (line ~299) states submenus are
  "fetched via `GET /categories/<slug>/submenu/` ... injected via HTMX swap."
- **Implemented:** `header_catalog.html` (lines ~318-321) loads the submenu with a
  vanilla `fetch('/categories/<slug>/submenu/')` → `container.innerHTML = html`.
  HTMX is only used for the autocomplete search (`hx-get` on the search input), not the
  category accordion.
- **Assessment:** Pre-existing doc inaccuracy, unrelated to a specific plan, but it
  contradicts the documented catalog-header behavior.
- **Documentation impact:** Correct to "fetched on first expand via a GET to
  `/categories/<slug>/submenu/` and injected into the panel" (vanilla JS, not HTMX).

## 9. Stale template reference in ui-patterns (get_children_count)

- **Planned/Doc:** `docs/01-spec/ui-patterns.md` (line 263) documents
  `{% if cat.get_children_count %}` on root-category expand buttons.
- **Implemented:** Plans 20/22 replaced this with `{% if cat.get_children.exists %}`
  (`header_catalog.html:95,161`; `mega_submenu.html:16`) so expand buttons render.
- **Assessment:** Bug-fix-level correction; the doc contradicts the code.
- **Documentation impact:** Update the HTML example to `cat.get_children.exists`.

## 10. Dangling spec-file reference in ui-patterns

- **Doc:** `docs/01-spec/ui-patterns.md` (line 324) says "See
  `24_catalog-header-auth-entry_spec.md` for full requirements."
- **Implemented:** no such file exists under `docs/01-spec/` or `.ai/problems/`; the spec
  is `.ai/problems/24_catalog-header-auth-entry_spec.md` (verified present).
- **Assessment:** Dangling cross-reference.
- **Documentation impact:** Point to the authoritative spec location / drop the reference.
