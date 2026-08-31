# Audit Report — Commit `a96d10a` Search Patterns Verification

**Date:** 2026-08-31
**Commit:** `a96d10afae31b9c840743dccd61a49a696b32e3e`
**Plan under review:** `.ai/plans/01_search_patterns_test_verification_detailed_plan.md`
**Reviewer:** Kilo (architect)
**Status:** APPROVED — with mandatory follow-up items

---

## Methodology

Static verification only — no test execution:

1. **Git inspection:** committed diff vs. plan (T1–T8 / Block 1–8 mappings).
2. **Code inspection:** `grep`, `Read`, `ast-editor` symbol-level checks on 9 source files.
3. **Lint gate:** `uv run ruff check` on all 5 changed Python files.
4. **Documentation cross-check:** plan specification ↔ template tag usage ↔ test assertions.

**Constraint:** The project's `make test` / `pytest` requires Docker PostgreSQL (`mko-bazuna-test-db-*` on port 5433). Could not be invoked here, so the plan's "All 1134 fast-gate tests pass" claim is treated as **unverified but credible** (tests assert the fixed behavior, not stale; see §4.3).

---

## 1. Objective

Verify that commit `a96d10a` faithfully implements the 8 tasks (T1–T8) of `.ai/plans/01_search_patterns_test_verification_detailed_plan.md`, scoped to Spec 15 search-pattern correctness, and that the supporting test artifacts are consistent with the intended (not stale) behavior.

---

## 2. Findings

### 2.1 Approved — T1–T8 Implemented Correctly

| Task | Plan Spec | Verified Implementation | Location |
|------|-----------|------------------------|----------|
| **T1** | Remove `{% csrf_token %}` from GET search form | Tag removed; `getCsrf()` refactored to `{{ csrf_token|escapejs }}` | `header_catalog.html` |
| **T2** | Clear/search-again button | `data-search-clear` button calling `window.history.back()` added | `header_catalog.html` |
| **T3** | Preserve category/city on search | Hidden `category` + `city` `<input>` fields added to form | `header_catalog.html` |
| **T4** | Sort dropdown on empty query | `{% if not query %}` gate removed in `filter_form.html`; `AdSort` branches added to FTS queryset | `filter_form.html`, `search.py:182-202` |
| **T5** | Empty price fields | `{{ min_price|default:'' }}` / `{{ max_price|default:'' }}` | `filter_form.html` |
| **T6** | HTMX sync GET | `htmx.get` absent from all templates (fixed in prior `32687e3` via `htmx.ajax`) | All templates |
| **T7** | Preserve query string in pagination | `&lang={{ LANGUAGE_CODE }}` added to all 9 pagination URLs + chip/removal links | `ad_list.html` |
| **T8** | Seed popular searches | `seed.default.json` `popular_searches` now Cyrillic Russian terms | `seed.default.json` |

**Commit message** correctly states it is scoped to "T1–T8" — it does **not** claim Block 9–11 coverage. No discrepancy found.

### 2.2 Approved — Supporting Changes Valid

- **13 new test functions** (`test_autocomplete_template.py` ×4, `test_catalog_filters.py` ×9): all assert the **new** fixed behavior. No stale-behavior traps.
- **`conftest.py` — `--run-syncdb` migrate:** beneficial test-infrastructure improvement for table creation without explicit migrations. Correct and non-disruptive.
- **`header_catalog.html` language switcher reformatting:** pure whitespace; Block 9 V4 logic (`?lang=` replacing query string) unchanged and **out of scope**.

### 2.3 Approved — Lint Gate Clean

```
$ uv run ruff check src/backend/conftest.py \
  src/backend/templates/components/header_catalog.html \
  ...
All checks passed!
```
(Ruff runs on `.py` files; templates are HTML-only.)

---

## 3. Problems Requiring Attention

### 3.1 CRITICAL — `escapeHtml` Regex Bug (Not in Plan Scope)

**Severity:** HIGH — security/correctness
**File:** `src/backend/templates/components/header_catalog.html`, line ~229
**Diff:**
```
Before:  .replace(/>/g, '&gt;');
After:   .replace( />/g, '&gt;');
```
A space was inserted inside the regex literal `/`,>/` → `/ />/g`. The function sanitizes autocomplete suggestion data (`s.text`, `s.category_path`, `s.type`/`s.source`, `s.slug`) before DOM insertion as `<li><a href="#" data-suggestion-text="...">...</a></li>`.

- `>` is now **not** escaped unless preceded by a space.
- XSS exploitability is currently **mitigated** (`<`, `&`, `"` still escaped), but `escapeHtml` breaches its contract of escaping all four HTML-special characters.
- **Not documented** in plan D1–D8 nor the commit message.
- **Recommendation:** Revert to `.replace(/>/g, '&gt;')`.

### 3.2 MEDIUM — Stale HTMX Version Comments

**Paths:**
- `header_catalog.html:4` — "HTMX 1.9.12 has no hx-on"
- `favorites/favorite_heart.html:35` — "HTMX 1.9.12 does not support the inline event attribute"

CDN is HTMX 2.0.10. Templates use vanilla JS (IIFE), not `hx-on`. Comments are misleading but harmless.

### 3.3 LOW — Formatting-Only Churn Obscured Semantic Change

30 template files received **pure formatting** changes (re-indentation, attribute splitting) via "stash/pop reconciliation." Verified zero semantic change via `git diff --ignore-all-space --ignore-blank-lines`. This is the **exact mechanism that introduced Problem 3.1**.

**Recommendation:** Isolate formatting-only changes into a dedicated commit/PR.

### 3.4 LOW — Committed Build Artifacts Deleted

Commit deleted 6 `_step3_*.txt` profiling artifacts (mistakenly committed in `c73f54d`). Deletion is correct cleanup. Recommend adding `_step3_*.txt` to `.gitignore`.

---

## 4. Rollout Analysis

### 4.1 Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| `escapeHtml` regex (Problem 3.1) | HIGH | Fix before any autocomplete suggestion could contain `>` in user-visible text |
| Unverified test run | MEDIUM | `make test` in Docker should be run to confirm claims before release |
| Stale HTMX comments (3.2) | LOW | Update or remove to prevent future maintainer confusion |

### 4.2 Dependencies

- **Test execution:** Requires `docker compose --project-name mko-bazuna-test` with PostgreSQL 18 on port 5433. Cannot be validated in this static-only pass.
- **Deployment:** No DB migration required by this commit — all changes are template/HTML/Python logic.
- **Rollback:** Standard git revert of `a96d10a` restores prior behavior with no schema coupling.

### 4.3 Backward Compatibility

- **Full backward compatible.** No API, schema, or data-model changes.
- The only behavioral changes are: (a) HTMX GET sync fix (T6), (b) price-field empty-value handling (T5), (c) sort-on-empty-query (T4). These are bug fixes that align with existing user expectations.
- **Caveat (T1):** Removing `{% csrf_token %}` from a GET form has **no security impact** — GET requests are not CSRF-protected by design. Correct.

---

## 5. Execution Validation

| Check | Result |
|-------|--------|
| Commit message matches plan scope (T1–T8) | ✅ Pass |
| T1–T8 source diffs verified against plan spec | ✅ Pass |
| Plan D1–D8 deliverables present (templates, fixtures, tests) | ✅ Pass |
| 13 new tests assert fixed behavior (not stale) | ✅ Pass |
| `ruff check` clean on changed Python files | ✅ Pass |
| Plan Block 9–11 explicitly out of scope | ✅ N/A — correctly deferred |
| `escapeHtml` regex correctness | ⚠️ FAIL — space inside `/><` regex literal |
| Test suite execution | 🔶 Unverified — Docker PostgreSQL required |

---

## 6. Warnings

- **Test verification unconfirmed:** The plan's central claim "All 1134 fast-gate tests pass" could not be independently verified. Tests appear well-formed on static inspection (assert post-fix behavior), but runtime confirmation is required before considering this complete.
- **`escapeHtml` is the real blocker:** The stash/pop formatting reconciliation introduced a regex literal bug that breaks the sanitization contract. While not currently exploitable (other escapes remain), it is a latent correctness defect.
- **Out-of-scope items remain:** Block 3 V5 (AnalyticsEvent unit test), Block 8 V5 (search did-you-mean), and Block 5 V2 (chip-removal edge cases) are correctly left for follow-up — they are not part of T1–T8.

---

## 7. Required Fixes

| # | Fix | Priority | Effort |
|---|-----|----------|--------|
| R1 | Revert `.replace( />/g, '&gt;')` → `.replace(/>/g, '&gt;')` in `header_catalog.html` | **Mandatory** | Trivial |
| R2 | Add `_step3_*.txt` to `.gitignore` | Recommended | Trivial |
| R3 | Update or remove stale HTMX 1.9.12 comments (2 templates) | Recommended | Trivial |

---

## 8. Advisory Recommendations

- **ADVISORY:** Run `make test` in Docker to independently confirm 1134-test pass + new test assertions.
- **ADVISORY:** Separate formatting-only template changes into a dedicated PR to keep semantic diffs reviewable (would have caught the `escapeHtml` bug at review time).
- **ADVISORY (process):** Track follow-up for unaddressed plan items — Block 3 V5 (P0), Block 8 V5 (P0), Block 5 V2 (P1). These fall outside T1–T8 but should be scheduled.
- **ADVISORY:** The `test_header_search_form_has_no_csrf_token` test checks for absence of literal `csrfmiddlewaretoken` in source text. Consider strengthening to assert the `{% csrf_token %}` **tag** is not rendered (semantic, not textual). Out of scope for this commit.

---

## 9. Conclusion

**COMMIT `a96d10a` IS APPROVED** for its stated scope (T1–T8 Spec 15 search-pattern fixes). All 8 tasks verified as correctly implemented, 13 new tests confirmed to assert fixed behavior, and the lint gate passes.

The commit does **not** over-claim — it correctly scopes to T1–T8 and leaves Block 9–11 for follow-up.

**Mandatory action:** Fix the `escapeHtml` regex bug (Problem 3.1 / R1) before considering the search-patterns work fully production-ready. This defect was introduced by the stash/pop formatting reconciliation, not by the plan's logic.
