---
id: 31_template-comment-validation
spec: .ai/problems/30_template-comment-validation_spec.md
domain: implementation-plan
spec_status: APPROVED
priority: High
status: DONE
date: 2026-08-23
stack: Python 3.14 · Django 5.2 LTS · PostgreSQL 18 · HTMX MPA · aiogram 3.x · Pydantic v2
completion_date: 2026-08-23
outcome: SUCCESS
---

# Plan 31 — Django Template Comment Validation (djlint H017 Detection) — DONE

## 0. Summary

Implemented djlint as a template linter in CI to detect multi-line `{# ... #}` Django
template comments, which silently render literal `{#` text to HTML output. The original
plan assumed djlint's H017 rule would handle this detection, but research during
implementation revealed that H017 was reassigned in djlint v1.44.x to "void tags should
be self closing" — the multi-line comment detection rule no longer exists.

**Key deviation:** A custom Python module rule (H901) was created to detect multi-line
`{# ... #}` comments. Pattern-based rules cannot work because djlint treats all
`{# ... #}` content as "ignored inline blocks" and skips pattern matches inside them.
The Python module `run()` interface bypasses this filter and directly returns errors.

## 1. Deviations from Original Plan

### T3 — Config format correction
- **Plan specified:** `extend = "django"` and `use_default_config = true`
- **Actual:** `profile = "django"` and `ignore = "D018,H019,H021,H023,H030"`
- **Reason:** `extend` and `use_default_config` are not valid djlint config keys
  in v1.44.2. The correct keys are `profile` (replaces `extend`) and `ignore`
  (replaces `extend-skip`). This was discovered by inspecting djlint's settings.py
  source: `_PROFILES` validates `profile`, and `ignore` splits on commas.

### T4 — CI job structure changes
- **Plan specified:** Path `src/backend/templates/` with `working-directory: src/backend`
- **Actual:** Path `templates/` (relative) with `working-directory: src/backend`
  and `env: PYTHONPATH: .`
- **Reason:** With `working-directory: src/backend`, the path `src/backend/templates/`
  would resolve to `src/backend/src/backend/templates/` (nonexistent). The path must
  be `templates/` (relative to `src/backend`). Additionally, the custom rule module
  `djlint_custom_rules.py` lives at `src/backend/djlint_custom_rules.py` and must be
  importable — `PYTHONPATH=.` adds `src/backend/` to the Python path so `importlib.import_module`
  (called by djlint's linter at `lint.py:90`) can find it.

### T3/T4 — H017 → H901 rule substitution
- **Plan specified:** Use djlint's built-in H017 rule
- **Actual:** Created custom rule H901 via Python module + `.djlint_rules.yaml`
- **Reason:** H017 was reassigned in v1.44.x. Additionally, djlint's pattern-based rule
  system (`patterns` key in `.djlint_rules.yaml`) cannot detect multi-line `{# #}`
  because `linter.py:113` calls `overlaps_ignored_block()` which skips any regex match
  inside `{# ... #}` (treated as "ignored inline blocks"). The Python module rule
  interface (`lint.py:89-104`) bypasses `overlaps_ignored_block` entirely — it calls
  `rule_module.run()` and directly extends the errors list.

## 2. Files Changed

| File | Change |
|------|--------|
| `src/backend/templates/ads/partials/filter_sort.html` | Converted 2 multi-line `{# ... #}` comments to `{% comment %}...{% endcomment %}` |
| `pyproject.toml` | Added `djlint>=1.44.2` to `[dependency-groups] dev`; added `[tool.djlint]` config with `profile="django"`, `ignore="D018,H019,H021,H023,H030"` |
| `uv.lock` | Updated by `uv add --dev djlint` (lockfile, not hand-edited) |
| `src/backend/djlint_custom_rules.py` | **NEW** — Custom H901 rule module with `run()` function detecting multi-line `{# ... #}` via regex |
| `.djlint_rules.yaml` | **NEW** — Custom rules file referencing `python_module: djlint_custom_rules` |
| `.github/workflows/ci.yml` | Added `lint-templates` job: checkout → setup-uv → uv sync → `uv run djlint templates/` with `working-directory: src/backend`, `env: PYTHONPATH: .` |
| `Makefile` | Added `lint-templates` to `.PHONY`, help text, target-specific var group, and recipe |
| `.ai/context/commands.md` | Djlint command row already present — verified |

## 3. Pre-existing Violations Suppressed

The `ignore` list suppresses pre-existing style violations so CI enforces only H901:

| Code | Rule | Reason for suppression |
|------|------|------------------------|
| D018 | Django internal links should use `{% url %}` | 37 project-wide; out of scope for this task |
| H019 | javascript: URLs present | In `ads/detail.html` |
| H021 | Inline styles | In admin/moderation/queue.html, components/header_catalog.html |
| H023 | Entity references | In ad_list.html, breadcrumb.html, etc. (~10 templates) |
| H030 | Missing meta description | On standalone HTML documents (base templates) |

## 4. Verification Results

| Check | Result |
|-------|--------|
| `PYTHONPATH=src/backend uv run --project src/backend djlint src/backend/templates/` | 38 files, 0 errors ✅ |
| H901 detects multi-line `{# #}` in test file | 1 error found ✅ |
| `filter_sort.html` passes (no multi-line comments) | 0 errors ✅ |
| CI job YAML structure validated | 5-step structure matches lint/typecheck pattern ✅ |
| Makefile target matches pattern | Uses `$(COMPOSE_FILES)` like lint/typecheck ✅ |
| `commands.md` djlint row present | Already documented ✅ |
| No existing CI/Makefile targets modified | Only additive changes ✅ |

## 5. Acceptance Criteria Walkthrough

| AC | Status | Evidence |
|----|--------|----------|
| AC-1: `filter_sort.html` has no multi-line `{# ... #}` | ✅ | Both comments converted to `{% comment %}...{% endcomment %}` (lines 1-10, 20-23) |
| AC-2: djlint in dev deps + `[tool.djlint]` config | ✅ | `pyproject.toml` has `djlint>=1.44.2` and `[tool.djlint]` with `profile="django"` |
| AC-3: CI `lint-templates` job runs `uv run djlint` | ✅ | Job added with correct working-directory and PYTHONPATH env var |
| AC-4: `make lint-templates` runs djlint in Docker | ✅ | Target added; Dockerfile `ENV PYTHONPATH=/app/src/backend` makes module importable |
| AC-5: No regressions to lint, typecheck, test | ✅ | Changes are additive; no existing targets/jobs modified |

## 6. Notes for Future Maintainers

- **Custom rule module:** `src/backend/djlint_custom_rules.py` uses `importlib` to import
  via the name `djlint_custom_rules`. This requires `src/backend/` on `PYTHONPATH`:
  - Make (Docker): `ENV PYTHONPATH=/app/src:/app/src/backend` in Dockerfile ✅
  - CI: `env: PYTHONPATH: .` with `working-directory: src/backend` ✅
  - Local: `PYTHONPATH=src/backend uv run --project src/backend djlint ...` ✅
- **Rule discovery:** `.djlint_rules.yaml` is discovered by djlint's `find_djlint_rules()`
  which searches the project root (found via `.git` directory).
- **H017 vs H901:** If djlint is upgraded to a version that restores H017, the custom
  H901 rule can be removed and `ignore` updated accordingly.
