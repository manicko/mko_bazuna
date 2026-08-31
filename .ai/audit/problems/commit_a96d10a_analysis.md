# Audit: Commit `a96d10a` — "fix(search): implement Spec 15 T1-T8 search pattern fixes"

**Date:** 2026-08-31  
**Analyst:** Architecture Audit  
**Commit:** a96d10afae31b9c840743dccd61a49a696b32e3e  
**Plan reference:** `.ai/plans/01_search_patterns_test_verification_detailed_plan.md`  

---

## 1. Summary

The commit implements all eight Spec 15 tasks (T1–T8) from the search-patterns plan.
All 14 Python test additions and all T1–T8 semantic code changes are within scope
of the plan. However, a **stash/pop reconciliation** pass (acknowledged in the commit
message) introduced 28 additional files of **pure formatting** changes (re-indentation,
attribute splitting), plus one **unintended semantic bug** in the `escapeHtml`
sanitizer that breaks `>` escaping in the autocomplete dropdown.

**Overall verdict:** The T1–T8 implementation is correct and improves the codebase.
The formatting changes are neutral. The `escapeHtml` regex bug is the one item that
**degrades** architecture (a latent XSS / correctness regression).

---

## 2. Files Changed — Classification

### 2.1 Semantic code changes (within T1–T8 plan scope) — 6 files

| File | Spec task | Change | Plan section |
|---|---|---|---|
| `templates/components/header_catalog.html` | T1 | Removed `{% csrf_token %}` from GET search form | P1, Block 1, B1 |
| `templates/components/header_catalog.html` | T2 | Added clear-search button (`data-search-clear`, `onclick="window.history.back()"`) | P1, Block 1, B2 |
| `templates/components/header_catalog.html` | T3 | Added hidden `<input name="category">` and `<input name="city">` to search form | P1, Block 1, B3 |
| `templates/ads/partials/filter_form.html` | T4 | Removed `{% if not query %}` gate around sort `<select>` | P1, Block 6, B4 |
| `templates/ads/partials/filter_form.html` | T5 | Price inputs: `value="{{ min_price }}"` → `value="{{ min_price|default:'' }}"` | P3, Block 1, B5 |
| `templates/ads/partials/ad_list.html` | T7 | Added `{% if LANGUAGE_CODE %}&lang={{ LANGUAGE_CODE }}{% endif %}` to all 9 pagination/chip-removal URLs | P4, Block 7, B7 |
| `apps/search/views/search.py` | T4 | Replaced hardcoded `order_by("-rank",...)` with `AdSort`-branched ordering for FTS results, preserving `-rank` as secondary tiebreaker | P1, Block 6, B4 |
| `apps/seed/config/seed.default.json` | T8 | `popular_searches` values changed from English to Russian (айфон, автомобиль, квартира, диван, велосипед) | T8 |

All match the plan's roadmap table exactly.

### 2.2 New test additions (within plan test scope) — 2 files

| File | Tests added | Plan block |
|---|---|---|
| `apps/ads/tests/test_catalog_filters.py` | `TestFtsSortOrder` (4 tests), `TestSortOnSearchResults` (1 test), 4 template-source assertions (lang param, sort dropdown, price default, lang in rendered output) | Block 6, Block 7, Block 5, Block 1 |
| `apps/search/tests/test_autocomplete_template.py` | `test_header_search_form_has_no_csrf_token`, `test_search_clear_button_is_wired_to_history_back`, `test_header_search_form_preserves_category_context`, `test_header_search_form_preserves_city_context` | Block 1, B1/B2/B3 |

Tests assert the **new** (fixed) behavior, not the old buggy behavior. Consistent with the plan's intent.

### 2.3 Supporting infrastructure change — 1 file (NOT in plan)

| File | Change | Assessment |
|---|---|---|
| `src/backend/conftest.py` | Added `call_command("migrate", "--run-syncdb")` before `load_exchange_rates` in `_restore_test_schema_post_db_setup` | **Low risk / beneficial.** Ensures tables for unmigrated apps (e.g., currencies) exist when using `--reuse-db`. Idempotent. Supports the new FTS sort tests that depend on `price_normalized_eur` (which requires exchange rate data). Not documented in the plan but is a correct test-infrastructure improvement. |

### 2.4 Build artifact cleanup — 7 deleted files (NOT in plan, NOT code)

| Files deleted | Assessment |
|---|---|
| `src/backend/_step3_conc.txt`, `_step3_done.txt`, `_step3_fg.txt`, `_step3_overhead.txt`, `_step3_seed.txt`, `_step3_sett.txt`, `_step3_unit.txt` | **Test-run profiling output** (pytest output captured to .txt files). These are generated artifacts that were erroneously committed in an earlier commit (c73f54d). Their deletion is cleanup — they are not source code, not configuration, and have zero impact on application operation. |

### 2.5 Pure formatting changes — 30 files

All 30 remaining template files were reformatted (re-indented, attributes split to
one-per-line, blank lines removed). Verified via `git diff --ignore-all-space
--ignore-blank-lines`: **no semantic changes** remain in any of these files. These
are the "formatting changes from stash/pop reconciliation" mentioned in the commit
message.

Files: `list.html`, `detail.html`, `edit.html`, `dashboard.html`, `favorites.html`,
`hub.html`, `saved_search_edit.html`, `saved_searches.html`, `search_history.html`,
`settings.html`, `login_issue.html`, `consent_banner.html`, `feature_tag.html`,
`header.html`, `header_auth_entry.html`, `header_favorites_badge.html`,
`language_switcher.html`, `login_prompt.html`, `breadcrumb.html`, `cabinet_nav.html`,
`footer.html`, `mega_submenu.html`, `pro_badge.html`, `trusted_badge.html`,
`verified_badge.html`, `save_search_modal.html`, `save_search_success.html`,
`queue.html`, `review.html`, `moderation_dashboard.html`, `seller_dashboard.html`.

---

## 3. CRITICAL Finding: `escapeHtml` regex bug (not in plan, degrades architecture)

**Severity: HIGH** (latent XSS / correctness regression)

**Location:** `src/backend/templates/components/header_catalog.html`, line 229

**Before (HEAD~1):**
```javascript
function escapeHtml(str) {
    return String(str == null ? '' : str)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
```

**After (HEAD):**
```javascript
function escapeHtml(str) {
    return String(str == null ? '' : str)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;') .replace( />/g, '&gt;').replace(/"/g, '&quot;');
}
```

**Root cause:** The two-line `.replace()` chain was joined into one line during
stash/pop reconciliation. A space was inserted inside the regex literal for `>`:
- Old regex: `/>/` — matches `>` (correct)
- New regex: `/ />/g` — matches ` />` (space + `>`, incorrect)

**Impact:**
- The `>` character is no longer escaped unless preceded by a space.
- `escapeHtml` is used to sanitize **autocomplete suggestion data** (`s.text`,
  `s.category_path`, `s.type/s.source`, `s.slug`) before inserting into
  `innerHTML` as `<li><a href="#" data-suggestion-text="...">...</a></li>`.
- Direct XSS exploitability is **mitigated** in the current code paths because
  `<` and `&` and `"` are still escaped — so neither tag injection nor attribute
  breakout is possible from `>` alone.
- **However**, this is a correctness regression: the function fails to escape
  one of the four HTML-special characters (`>`), breaking its own contract.
  Any future code that relies on `escapeHtml` for sanitization is at risk.
- The plan's Deviations section (D1–D8) does **not** mention this change.
  The commit message does not mention it. It is an unintended side effect.

**Recommendation:** Revert the regex to `/>/` (no leading space):
```javascript
.replace(/>/g, '&gt;')
```
Effort: trivial. Priority: recommended (correctness/security).

---

## 4. Side-effect changes in `header_catalog.html` (consequences of T1, correctly handled)

| Change | Plan reference | Assessment |
|---|---|---|
| `getCsrf()`: DOM query → `{{ csrf_token\|escapejs }}` | T1 / B1 | **Correct.** Removing `{% csrf_token %}` from the GET form (T1) also removed the `<input name="csrfmiddlewaretoken">` element the old DOM query looked for. Inlining the token from the template context is the proper fix. |
| `cityGetCsrf()`: same DOM query → `{{ csrf_token\|escapejs }}` | T1 / B1 | **Correct.** Same rationale. Used for city-selection AJAX POST. |
| SVG `transform="translate(0, 2)"` → `transform="translate(0, 2) "` (space before `/>`) | T6 / formatting | **Harmless.** Inside a JS string literal. Whitespace before `/>` in SVG markup is semantically irrelevant. |

---

## 5. Stale documentation comments (identified by plan D8, NOT fixed in this commit)

The plan's Deviation D8 identifies two stale comments:

| File:line | Comment | Status |
|---|---|---|
| `header_catalog.html:4` | "HTMX 1.9.12 has no hx-on" | **NOT fixed** — CDN is now 2.0.10 but comment still references 1.9.12. `hx-on` has never been used in this template (vanilla JS IIFE). Comment is misleading but harmless. |
| `favorite_heart.html:35` | "HTMX 1.9.12 does not support the inline event attribute" | **NOT fixed** — same stale reference. |

These are documentation inaccuracies, not functional bugs. The plan D8 recommends
correcting them. They remain uncorrected in this commit.

---

## 6. Deviations from the plan — Assessment

| Item | In plan? | Assessment |
|---|---|---|
| `conftest.py` `migrate --run-syncdb` | Not mentioned | **Beneficial.** Test infrastructure improvement, idempotent, prevents stale-schema failures. |
| Deleted `_step3_*.txt` files | Not mentioned | **Cleanup.** Generated test artifacts, not source code. No impact. |
| `escapeHtml` regex bug | Not mentioned | **DEGRADATION.** Unintended bug in autocomplete HTML sanitizer. Must be reverted. |
| Stale HTMX 1.9.12 comments | Identified in D8, not fixed | **Documentation gap.** Remains as known issue. |

**No architectural degradation occurred in the T1–T8 implementation itself.**
All eight Spec 15 tasks were implemented correctly, matching the plan's specification.
The only degradation is the `escapeHtml` regex bug, introduced by the unacknowledged
"formatting changes from stash/pop reconciliation."

---

## 7. Recommendations

1. **[BEST-PRACTICE] CRITICAL — Fix `escapeHtml` regex**  
   `header_catalog.html:229`: change `.replace( />/g, '&gt;')` back to `.replace(/>/g, '&gt;')`.  
   *Why:* Restores the function's security contract; prevents latent XSS risk in any future usage.  
   *Effort:* trivial. *Priority:* recommended (mandatory for correctness).

2. **[DOC-UPDATE] Correct stale HTMX version comments**  
   `header_catalog.html:4` and `favorite_heart.html:35`: update "HTMX 1.9.12" references to "HTMX 2.0.10" or remove the version-specific claims.  
   *Why:* Prevents confusion for future maintainers.  
   *Effort:* trivial. *Priority:* recommended.

3. **[BEST-PRACTICE] Avoid blanket "formatting changes" in feature commits**  
   The stash/pop reconciliation touched 30 template files with pure formatting. This obscures the review of the 8 actual semantic changes.  
   *Why:* Makes code review harder; increases merge conflict surface; the `escapeHtml` bug was introduced this way.  
   *Effort:* process-level. *Priority:* recommended.

4. **[DOC-UPDATE] Track `_step3_*.txt` cleanup**  
   These test-profiling artifacts should be in `.gitignore` to prevent re-commitment.  
   *Effort:* trivial. *Priority:* low.
