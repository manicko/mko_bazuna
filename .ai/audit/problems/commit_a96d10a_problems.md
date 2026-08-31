# Problems & Errors Report — Commit `a96d10a`

**Date:** 2026-08-31
**Commit:** a96d10afae31b9c840743dccd61a49a696b32e3e
**Scope:** Audit of commit "fix(search): implement Spec 15 T1-T8 search pattern fixes"

---

## Problem List

### 1. CRITICAL — `escapeHtml` regex bug
- **Severity:** HIGH
- **Path:** `src/backend/templates/components/header_catalog.html`, line 229
- **Code:**
  - Before: `.replace(/>/g, '&gt;')` — correct regex matching `>`
  - After: `.replace( />/g, '&gt;')` — broken regex matching ` />` (space + `>`)
- **Root cause:** Two-line `.replace()` chain was merged into one line during stash/pop reconciliation. A space was inserted inside the regex literal `/>`.
- **Impact:**
  - `>` is no longer escaped unless preceded by a space.
  - `escapeHtml` sanitizes autocomplete suggestion data (`s.text`, `s.category_path`, `s.type/s.source`, `s.slug`) before inserting into `innerHTML` as `<li><a href="#" data-suggestion-text="...">...</a></li>`.
  - Direct XSS exploitability is mitigated (because `<`, `&`, and `"` are still escaped), but the function breaches its own contract of escaping all four HTML-special characters. Any future code relying on `escapeHtml` is at risk.
  - Not documented in the plan (D1–D8) nor mentioned in the commit message.
- **Recommendation:** Revert to `/>/`
- **Effort:** trivial
- **Priority:** mandatory (correctness/security)

### 2. MEDIUM — Stale HTMX version comments (plan D8, not fixed)
- **Severity:** MEDIUM (documentation inaccuracy / misleads future maintainers)
- **Paths:**
  - `src/backend/templates/components/header_catalog.html`, line 4 — "HTMX 1.9.12 has no hx-on"
  - `src/backend/templates/ads/partials/favorites/favorite_heart.html`, line 35 — "HTMX 1.9.12 does not support the inline event attribute"
- **Status:** The CDN is at HTMX 2.0.10, but the comments still reference 1.9.12. Neither template uses `hx-on` or inline event attributes — a vanilla JS IIFE handles behavior. The comments are misleading but harmless.
- **Recommendation:** Update to 2.0.10 or remove version-specific claims.
- **Effort:** trivial
- **Priority:** recommended (documentation)

### 3. LOW — Committed build/test artifacts (`_step3_*.txt`)
- **Severity:** LOW (no runtime impact; generated artifacts)
- **Path:** `src/backend/`
- **Files deleted in commit:**
  - `_step3_conc.txt`
  - `_step3_done.txt`
  - `_step3_fg.txt`
  - `_step3_overhead.txt`
  - `_step3_seed.txt`
  - `_step3_sett.txt`
  - `_step3_unit.txt`
- **Assessment:** Generated test profiling output (pytest captured to .txt). Committed by mistake in an earlier commit (c73f54d). Deletion is cleanup with zero impact on application operation.
- **Recommendation:** Add `_step3_*.txt` to `.gitignore` to prevent re-entry.
- **Effort:** trivial
- **Priority:** low

### 4. LOW — Process — blanket formatting changes in feature commit
- **Severity:** LOW (process/operational)
- **Context:** The "formatting changes from stash/pop reconciliation" (acknowledged in commit message) touched 30 template files with re-indentation and attribute splitting.
- **Assessment:** 30 files had **pure formatting** changes — verified zero semantic changes via `git diff --ignore-all-space --ignore-blank-lines`. However, this broad churn obscured the 8 actual semantic changes, expanding the review surface. **This is the exact mechanism that introduced Problem 1** (the `escapeHtml` regex bug).
- **Recommendation:** Separate formatting-only changes into a dedicated commit or PR.
- **Effort:** process-level
- **Priority:** recommended

---

## Items Verified — No Problems Found

| Item | Assessment |
|---|---|
| T1–T8 Spec 15 tasks | All implemented correctly, matching the plan's specification |
| New Python tests (20 tests across 2 files) | All assert the **new** fixed behavior, not stale behavior. Consistent with plan intent. |
| `conftest.py` — `migrate --run-syncdb` | Beneficial test-infrastructure improvement (not in plan, but correct) |
| `header_catalog.html` — `getCsrf()` / `cityGetCsrf()` refactor | Correct — inlining `{{ csrf_token|escapejs }}` is the proper fix after removing `{% csrf_token %}` from the GET form (T1) |
| SVG `transform="translate(0, 2) "` trailing space | Harmless — inside a JS string literal; whitespace before `/>` is semantically irrelevant |
