---
id: plan-verification-test-optimization-audit-plans
domain: audit
tags:
  - static-analysis
  - lint
  - typecheck
  - ci
  - verification
related:
  - pyproject.toml
  - .github/workflows/ci.yml
  - .github/workflows/ci-nightly.yml
  - src/backend/conftest.py
---

# Plan Verification: Code-Level Static Defects (CI lint/typecheck red)

> **RESOLVED** — finding **O-03** fixed. `ruff check .` and `basedpyright .` (run from
> `src/backend`, mirroring CI) now report **0 errors**. The 4 unused imports were removed,
> the 8 `basedpyright` errors were resolved (generator fixture annotations, context-manager
> typing at `builder.py:74`, `list[SlugField]`→`list[str]` coercion at
> `lookup_resolution.py:59,64`). Affected test suites pass (68 + 6 tests).

**Scope:** Static verification of code-level defects found while auditing the two "DONE" test-plans, at **git HEAD `ef26fc8`** (working directory clean except `uv.lock`). Docker/PostgreSQL unavailable → pytest *runs* not re-executed; only static evidence (`file:line`, `ruff`, `basedpyright`, `git ls-files`) cited.

**Heads-up:** `main` is **+93 commits ahead of `origin/main`** and `uv.lock` is modified locally, so tool *versions* may differ from CI; however `F401` and the `basedpyright` report-class errors below are genuine static defects in committed source.

---

## Verdict summary

| Plan claim §14 | Actual code (HEAD ef26fc8) | Status |
|---|---|---|
| Lint `ruff` all-pass ✅ | `ruff check .` (src/backend, as CI) → **4 F401** errors | FALSE (CI lint red) |
| Typecheck `basedpyright` 0 errors ✅ | `basedpyright .` (src/backend, as CI) → **8 errors** | FALSE (CI typecheck red) |

---

## Findings — code-level static gates (must fix in code)

### O-03 — §14 "lint/typecheck/0 failures" claims do not hold at current HEAD  `[MEDIUM / correctness / mandatory-adjacent]`

§14 records `ruff` clean, `basedpyright` "0 errors", and "0 failures across 4 test runs." Static checks rerun against the current tree (mirroring the CI jobs, which run from `src/backend` with `ruff check .` and `basedpyright .`):

- **`ruff check .`** → **4 errors**, all `F401` unused imports in CI scope:
  - `apps/ads/tests/test_dashboard_stats.py:12` — `unittest.mock.patch`
  - `apps/analytics/tests/test_trust_analytics.py:15` — `Ad`
  - `apps/analytics/tests/test_trust_analytics.py:23` — `Category`
  - `apps/analytics/tests/test_trust_analytics.py:25` — `City`
- **`basedpyright .`** → **8 errors** (0 warnings, 0 notes):
  - `apps/analytics/tests/test_views.py:111,126,277,288` — generator return-type annotations (`reportInvalidTypeForm`/`reportReturnType`).
  - `apps/categories/catalog/builder.py:74` — object not a valid context manager (`reportGeneralTypeIssues`, ×2).
  - `apps/categories/services/lookup_resolution.py:59,64` — `list[SlugField]` not assignable to `list[str]` (`reportReturnType`, ×2).

The repo-root `ruff check .` additionally flags 6 `E402` in `scripts/*.py` (`check_import.py`, `debug_graph.py`, `dump_graph.py`) — outside CI scope but real.

Because `main` is +93 commits unpushed ahead of `origin/main` and `uv.lock` is modified locally, tool *versions* may differ from CI; however `F401` and the `basedpyright` `reportReturnType`/`reportGeneralTypeIssues` findings are genuine static defects in committed source, so the CI `lint` and `typecheck` jobs would fail as-is.

**Evidence:**
- `pyproject.toml:160` (addopts, no `--cov`); `pyproject.toml:163-170` (6 markers, no `e2e`).
- `src/backend/apps/ads/tests/test_dashboard_stats.py:12`
- `src/backend/apps/analytics/tests/test_trust_analytics.py:15,23,25`
- `src/backend/apps/analytics/tests/test_views.py:111,126,277,288`
- `src/backend/apps/categories/catalog/builder.py:74`
- `src/backend/apps/categories/services/lookup_resolution.py:59,64`
- `.github/workflows/ci.yml` / `ci-nightly.yml` (lint + typecheck jobs run from `src/backend`).

**Recommendation (mandatory-adjacent, correctness — fix in code, not docs):**
1. Remove the 4 unused imports in `test_dashboard_stats.py:12` and `test_trust_analytics.py:15,23,25`.
2. Resolve the 8 `basedpyright` errors:
   - Fix generator return-type annotations in `test_views.py:111,126,277,288` (annotate or `yield` correctly; `reportInvalidTypeForm`/`reportReturnType`).
   - Audit the `contextlib`-style usage at `builder.py:74` (`reportGeneralTypeIssues` ×2) — ensure the object implements `__enter__`/`__exit__` or replace with a proper context manager.
   - Fix `list[SlugField]` → `list[str]` mismatch in `lookup_resolution.py:59,64` (`reportReturnType` ×2) — either widen the return type or cast/coerce to `list[str]`.
3. Optionally clear the 6 `E402` in `scripts/*.py` (out of CI scope but flagged by root `ruff check .`).

**Effort:** small (test-file imports + localized type fixes).
**Priority:** recommended — this is the concrete CI-red gap; without it the `lint`/`typecheck` jobs fail.

---

## Severity

| CRITICAL | HIGH | MEDIUM | LOW |
|----------|------|--------|-----|
| 0 | 0 | 1 (O-03) | 0 |

Per existing audit taxonomy, the single finding here is **code-level static-gate regressions** that block CI. No production runtime defect was found in this verification pass; the underlying test infra (seed-exclusion gate, `--reuse-db`, markers — confirmed committed in `6e6f1dc`) is correctly in place.

## Advisory recommendation (prioritized)

1. **[Mandatory-adjacent] Fix O-03 — restore green CI lint/typecheck.** Remove the 4 unused imports and resolve the 8 `basedpyright` errors (return-type annotations, context-manager typing at `builder.py:74`, `list[SlugField]`→`list[str]` at `lookup_resolution.py:59,64`). This is the only remaining code-level correctness gap. Effort: small.
