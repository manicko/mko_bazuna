# code_context — Spec Verification: `21_import-sorting-configuration_spec.md`

**Auditor:** Kilo (poolside/laguna-s-2.1:free) · **Date:** 2026-09-10 · **Mode:** read-only (no files modified)
**Toolchain:** `uv run ruff 0.16.0` (project-pinned)

---

## Verdict Summary

| # | Spec claim | Status | Evidence |
|---|-----------|--------|----------|
| pyproject.isort | `[tool.isort]` dead config (L89-93) | ✅ VERIFIED | isort absent from dev deps |
| pyproject.ignore | `I001` in `[tool.ruff.lint].ignore` (L131-135) | ✅ VERIFIED | `ignore = ["E501", "I001"]` |
| pyproject.kfp | `known-first-party = ["mko_bazuna","settings","core"]` (L140) | ✅ VERIFIED | Same wrong value in both dead `[tool.isort]` and `[tool.ruff.lint.isort]` |
| pyproject.select | `select` includes `"I"` (L126) | ✅ VERIFIED | `select = ["E","F","I","B","UP"]` |
| pyproject.combine | `combine-as-imports = true` (L141) | ✅ VERIFIED | Present |
| pyproject.src | No `src` under `[tool.ruff]` | ✅ VERIFIED | Only `line-length`, `fix`, `exclude` |
| first-party | Packages: apps, config, theme, telegram_bot, conftest | ✅ VERIFIED | All importable under `PYTHONPATH=src:src/backend` |
| violations | 178 I001 violations | ✅ VERIFIED | `uv run ruff check src/ --select I --no-cache --statistics` → 178 I001, 178 fixable; 170 distinct files |
| bot safety | isort won't reorder `# noqa: E402` imports in main.py | ❌ **FALSE** | `--diff` shows 2 I001 fixes in main.py (see §4) |
| CI exists | `.github/` does not exist (A6) | ❌ **FALSE** | `.github/workflows/ci.yml` + `ci-nightly.yml` exist |
| CI lint | `ruff check .` from `src/backend` cwd | ✅ VERIFIED | ci.yml L136-137 |
| Makefile format | No `format` target | ✅ VERIFIED | grep `^format:` → none |
| Makefile.ps1 format | No `format` target | ✅ VERIFIED | grep `format` → only `psql format()` |
| docs AGENTS.md | Lint-only Quick Reference (L17) | ✅ VERIFIED | No Auto-fix row |
| docs commands.md | Format=`ruff format --check` (formatter, L11) | ✅ VERIFIED | No Auto-fix row |

---

## First-party packages (actual)

| Package | Path | Evidence |
|---------|------|----------|
| `apps` | `src/backend/apps/` | Django app root |
| `config` | `src/backend/config/` | `config.settings.prod` referenced in main.py L10 |
| `theme` | `src/theme/` | pyproject `include = ["apps*","config*","theme*","telegram_bot*"]` (L67-70) |
| `telegram_bot` | `src/telegram_bot/` | importable |
| `conftest` | `src/backend/conftest.py` | imported 52× across test files |

**Spec's list is correct.** `tests` is NOT a package (no `__init__.py`, only `test_docs_ci_parity.py`). `mko_bazuna` not importable (only stale egg-info). `core` = `apps.core` sub-package, not top-level. `settings` = `config.settings`.

---

## Bot bootstrap safety — SPEC CLAIM IS FALSE

The spec asserts (constraint #4 / Risk R1 / DoR #5) that ruff's isort "will NOT reorder" the `# noqa: E402` delayed imports in `src/telegram_bot/main.py`. Empirically false:

- `# noqa: E402` suppresses **E402 only**, not **I001**.
- ruff reports **2 I001 violations** in `main.py` and `--diff` shows it reorders:
  - **Block 1 (L13-21):** moves `django.conf` ahead of `telegram_bot.*` (third-party before first-party), inserts section-separator blank line, expands long import to parenthesized form (`combine-as-imports = true`).
  - **Block 2 (L59-66, in-function):** alphabetizes router imports inside `from telegram_bot.handlers import (...)`.
- **Only 5 files** in the repo carry `# noqa: E402` (all in `main.py`). No other bot-bootstrap file is affected.
- **Semantic safety:** ruff isort does NOT move imports across the `django.setup()` statement (L11) — it reorders only within the post-setup block. `django.setup()` still precedes every delayed import. Reorder is safe.
- The spec's Risk R1 mitigation ("verify… ruff's isort does NOT touch these") gives false comfort. T1+T2 WILL modify `main.py`.

---

## CI workflow — A6 IS FALSE

`.github/workflows/` exists with `ci.yml` (name: CI) and `ci-nightly.yml`. The CI `lint` job runs `uv run ruff check .` from `working-directory: src/backend` (ci.yml L121-137). CI uses config `select`/`ignore` (no `--select` flag), so `I001` in `ignore` currently suppresses all 178 violations in CI. After T1 (remove `I001` from ignore), CI will fail on all 178 until T2 fixes them — T1+T2 must be atomic.

---

## Key constraints

1. `fix = false` in ruff config (L98) — `ruff check` does NOT auto-fix without `--fix`. The `format` make target must pass `--fix` explicitly.
2. CI `lint` runs `ruff check .` (no `--fix`) — enforcement only after T1 removes `I001` from `ignore`.
3. Test DB in Docker only — verification via `make test` (Docker Compose).
4. Import sorting changes are in `.py` files only — `test_i18n_completeness.py` unaffected.
5. CI lint runs from `src/backend/` cwd, checking `.` (not `src/`) — this is a pre-existing scope limitation (CI doesn't lint `src/telegram_bot/`). Not changed by this spec.
