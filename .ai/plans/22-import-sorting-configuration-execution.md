---
id: import-sorting-configuration-execution
domain: plan
source_spec: .ai/problems/21_import-sorting-configuration_spec.md
auditor_report: .ai/plans/code-context-import-sorting.md
tags:
  - import-sorting
  - ruff
  - isort
  - CI-atomicity
  - bot-bootstrap-safety
  - T1-T2-atomic
  - Makefile
  - docs
related:
  - docs/99-agent/architecture.md
  - docs/99-agent/rules.md
  - .kilo/rules/commands.md
  - AGENTS.md
  - pyproject.toml
  - src/telegram_bot/main.py
  - Makefile
  - Makefile.ps1
  - .github/workflows/ci.yml
  - .github/workflows/ci-nightly.yml
---

# Import Sorting Configuration — Execution Plan (Phase 08)

**Plan ID:** `22-import-sorting-configuration-execution`  
**Source spec:** `.ai/problems/21_import-sorting-configuration_spec.md` (5 tasks T1–T5, PO decisions Q1–Q4 confirmed Choson=A, DoR all [x])  
**Auditor verification:** `.ai/plans/code-context-import-sorting.md` — 2 HIGH-severity discrepancies corrected  
**Generated:** 2026-09-10 — Planning only. No code modified.

---

## 1. Overview

Configure ruff's built-in isort to enforce import sorting project-wide, fix the dead `[tool.isort]` config, correct the `known-first-party` list, auto-fix all 178 existing I001 violations, and add a `format` make target for developer workflow. The work decomposes into **4 execution blocks** forming a dependency DAG.

---

## 2. Key Questions Answered

| # | Question | Answer | Rationale |
|---|----------|--------|-----------|
| 1 | T1+T2 one block or separate? | **One block (atomic commit)** | Removing `I001` from `ignore` (T1) without fixing the 178 violations (T2) would cause CI's `lint` job to fail on every push. Spec §7 constraint C6 and Risk R2 both confirm atomicity. |
| 2 | Makefile.ps1 also get `format`? | **Yes** | The spec §5 T4 only mentions Makefile, but the Auditor confirmed `Makefile.ps1` also lacks a `format` target. Windows is the primary dev path (AGENTS.md "Test Environment"). Both build systems must have parity. |
| 3 | Researcher agent needed? | **No** | Spec §4 research is comprehensive (ruff FAQ, isort comparison, config options). The bot-bootstrap safety finding is empirical (Auditor `--diff`), not a research question. No external docs needed. |
| 4 | Auditor re-check before implementation? | **No separate Auditor agent** | The Auditor already verified all findings. An inline `--diff` pre-check is recommended as the first Implementor step (to review `main.py` modifications), but does not require a separate agent. |
| 5 | T4 and T5 separate commits? | **Yes** | T4 is a code change (Makefile/Makefile.ps1 → Implementor). T5 is documentation (AGENTS.md/commands.md → Doc-specialist). Separate commits, same PR acceptable. |
| 6 | Bot bootstrap safety correction? | **Documented as acceptance criterion** | The spec's claim that `# noqa: E402` prevents isort reordering is **FALSE**. The reorder IS semantically safe — ruff isort never moves imports across code statements, so `django.setup()` is preserved as a barrier. Verify this post-fix in `main.py`. |

---

## 3. Discrepancy Corrections (vs. Source Spec)

The Auditor's empirical verification (code-context-import-sorting.md) identified **two spec claims as FALSE** that directly affect this plan:

### 3.1 Bot Bootstrap Safety — Spec §7.4/§8 R1/§11 DoR #5 is FALSE

**Spec claim:** `# noqa: E402` in `src/telegram_bot/main.py` prevents ruff's isort from reordering delayed imports.

**Auditor correction (FALSE):** `# noqa: E402` suppresses only the **E402** rule ("module level import not at top of file"), **not** the **I001** rule ("import block is un-sorted or un-formatted"). Ruff's `--diff` shows **2 I001 fixes** in `main.py`:
- **Module-level block (post-`django.setup()`):** moves `django.conf` ahead of `telegram_bot.*`, inserts a section-separator blank line, expands the long `telegram_bot.middlewares` import to parenthesized form (via `combine-as-imports = true`).
- **In-function block (inside `main()`):** alphabetizes the router imports in `from telegram_bot.handlers import (...)`.

**Semantic safety (confirmed):** Ruff's isort reorders imports *within* blocks only — it **never moves an import across a code statement**. The `django.setup()` call (line 11) is an unconditional statement; no import can cross it. Reordering is safe.

**Plan impact:** Block 1 (T1+T2) **WILL modify** `src/telegram_bot/main.py`. The spec's Risk R1 mitigation ("verify ruff's isort does NOT touch these") gives false comfort. Block 1's acceptance criteria explicitly require verifying the `django.setup()` boundary is preserved.

### 3.2 Assumption A6 (CI scope) — Spec §6 A6 is FALSE

**Spec claim:** `.github/` does not exist; CI is configured externally.

**Auditor correction (FALSE):** `.github/workflows/` exists with `ci.yml` and `ci-nightly.yml`. The CI `lint` job runs `uv run ruff check .` from `working-directory: src/backend` (ci.yml L121–137). CI uses config `select`/`ignore` (no `--select` flag), so `I001` in `ignore` currently suppresses all 178 violations in CI.

**Plan impact:** After T1 removes `I001` from `ignore`, CI will enforce I001 on `src/backend/` files. T2's auto-fix covers all of `src/` (including `src/backend/`), so CI will pass. **Pre-existing scope limitation:** CI lints `.` from `src/backend/` cwd — it does NOT cover `src/telegram_bot/`. This is out of scope for this spec; noted in §8.4.

---

## 4. Execution Graph (dependency-ordered)

```
┌─────────────────────────────────────────────────────────────────────┐
│  Block 1: T1+T2 — Config fix + auto-fix 178 I001 violations          │
│  (atomic commit, atomic by CI constraint)                            │
│  Files: pyproject.toml + all Python modules under src/               │
└──────────────────────┬──────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Block 2: T3 — Verify ruff clean + basedpyright clean + make test    │
│  (verification gate, no code change)                                 │
└──────────────────────┬──────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Block 3: T4 — Add `format` target to Makefile + Makefile.ps1        │
│  (independent files; parallel-safe with Block 2)                     │
└──────────────────────┬──────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Block 4: T5 — Update AGENTS.md + commands.md documentation          │
│  (documents the format target from Block 3)                          │
└─────────────────────────────────────────────────────────────────────┘
```

**Parallel-safe pairs:**
- Block 1 ∥ Block 3 — disjoint files (`pyproject.toml` + `src/*.py` vs `Makefile` + `Makefile.ps1`). Can execute concurrently.
- Block 2 ∥ Block 3 — Block 3 touches only Makefile/ps1; Block 2 runs verification. No shared files.

**NOT parallel-safe:**
- Block 1 → Block 2 — Block 2 verifies Block 1's output.
- Block 3 → Block 4 — Block 4 documents Block 3's `format` target.

---

## 5. Rollout & Commit Sequence

| Order | Block | Task | Agent | Commit | Parallel with |
|-------|-------|------|-------|--------|---------------|
| 1 | Block 1 | T1+T2 | Implementor | ✅ Commit 1 | Block 3 |
| 1 | Block 3 | T4 | Implementor | ✅ Commit 2 | Block 1, Block 2 |
| 2 | Block 2 | T3 | Validator | — (gate) | Block 3 |
| 3 | Block 4 | T5 | Doc-specialist | ✅ Commit 3 | — |

**Commit 1** (T1+T2): `chore(imports): fix ruff isort config and auto-fix all 178 I001 violations` — atomic.
**Commit 2** (T4): `feat(build): add format make target to Makefile and Makefile.ps1`.
**Commit 3** (T5): `docs: document format target and ruff check --fix vs ruff format distinction`.

> **Recommended:** Single PR with Commit 1 + Commit 2 + Commit 3 (or PR 1 = Commit 1; PR 2 = Commits 2+3). Block 2 (T3 verification) gates Commit 1 before Commits 2+3 should land.

---

## 6. Implementation Path Alternatives

### Block 1 (T1+T2)

| Path | Approach | When to use |
|------|----------|-------------|
| **A (Recommended)** | Staged pre-check: run `ruff check src/ --select I --diff` first, review (especially `main.py`), then apply `--fix`. T1 and T2 in one commit. | Default path — the `--diff` pre-check catches any unexpected reordering before it's applied. |
| **B** | Blind fix: edit config (T1), immediately run `--fix` (T2), commit. | Only if Implementor is highly confident about isort's safety guarantee and time-constrained. Skips the main.py review. |

### Block 3 (T4)

| Path | Approach | When to use |
|------|----------|-------------|
| **A (Recommended)** | Add `format` to both `Makefile` and `Makefile.ps1`. | Windows is the primary dev path; parity between build systems is required. |
| **B** | Makefile only (spec §5 T4 literal). | Rejected — the Auditor confirmed `Makefile.ps1` also lacks `format`, creating a Windows dev friction gap. |

---

## 7. Block 1 — T1+T2: Config Fix + Auto-Fix (Atomic Commit)

<!-- TASK_START: t1t2_import_sorting_config_and_autofix -->

```yaml
id: t1t2_import_sorting_config_and_autofix
title: "T1+T2: Fix ruff isort config in pyproject.toml + auto-fix all 178 I001 violations (atomic commit)"
priority: high
depends_on: []
classification: mandatory
risk: medium
status: pending
source_reference: .ai/problems/21_import-sorting-configuration_spec.md
source_section: "§5 T1+T2, §12, §7.4, §8 R1, §11 DoR #5; corrected by .ai/plans/code-context-import-sorting.md §4"
agent: Implementor
atomic_commit: true
ci_impact: "After T1 removes I001 from ignore, CI lint job (ruff check . from src/backend/) will fail until T2 applies --fix. Must be same commit."
```

### Description

Fix ruff's import-sorting configuration in `pyproject.toml` and auto-fix all 178 existing I001 violations in a single atomic commit. The config changes ensure ruff classifies imports correctly (first-party vs. third-party); the auto-fix then reorganizes every import block to `stdlib → third-party → first-party` with alphabetical sorting and correct blank-line separation.

**CORRECTION to spec §7.4/§8 R1:** `src/telegram_bot/main.py` **WILL be modified** by this block. The spec's claim that `# noqa: E402` prevents isort reordering is false (Auditor §4). The reordering is semantically safe — ruff isort never moves imports across code statements, so `django.setup()` at line 11 remains an immovable boundary.

### Implementation Scope

**Primary file (config):**
- `pyproject.toml` — TOML sections: `[tool.isort]`, `[tool.ruff]`, `[tool.ruff.lint]`, `[tool.ruff.lint.isort]`

**Auto-fix target (code):**
- All Python modules under `src/` containing import blocks (~170 files, 178 violations)
- **Specifically affected** (from spec §12 examples + Auditor): `src/telegram_bot/main.py` (module-level + in-function blocks), `src/backend/apps/ads/models.py`, `src/telegram_bot/handlers/ad_create.py`, `src/telegram_bot/handlers/login.py`, plus ~166 other modules under `src/backend/` and `src/telegram_bot/`.

### Changes

#### T1 — Config fixes in `pyproject.toml`

1. **Delete `[tool.isort]` section** — Remove the entire dead section (comment + header + 3 keys): `profile = "black"`, `known_first_party = [...]`, `combine_as_imports = true`. No tool consumes this; isort is not installed.

2. **Add `src` to `[tool.ruff]`** — After `fix = false`, add:
   ```toml
   src = ["src", "src/backend"]
   ```
   Matches `PYTHONPATH=/app/src:/app/src/backend` (Dockerfile) and `pythonpath = ["src", "src/backend"]` (pyproject.toml pytest config).

3. **Remove `I001` from `[tool.ruff.lint].ignore`** — Remove the `"I001"` entry and its comment. The `ignore` list should contain only `"E501"`.

4. **Fix `known-first-party` in `[tool.ruff.lint.isort]`** — Replace:
   ```toml
   known-first-party = ["mko_bazuna", "settings", "core"]
   ```
   With:
   ```toml
   known-first-party = ["apps", "config", "theme", "telegram_bot", "conftest"]
   ```
   These are the actual importable first-party packages (Auditor §2, verified).

5. **Preserve `combine-as-imports = true`** — Already correct in `[tool.ruff.lint.isort]`.

6. **Update stale comment on `"I"` line** — Change `# import-sorted checks (ruff checks imports)` to `# isort: import sorting (ruff built-in; replaces standalone isort tool)`.

#### T2 — Auto-fix all violations

```powershell
# Inline pre-check (review before applying):
uv run ruff check src/ --select I --diff

# Apply fixes:
uv run ruff check src/ --select I --fix
```

### Inline Pre-Check (safety gate for main.py)

Before applying `--fix`, the Implementor **must** run:
```powershell
uv run ruff check src/ --select I --diff
```
and specifically review `src/telegram_bot/main.py` output. Confirm:
- The `django.setup()` statement (line 11) is **not** moved — no import from lines 3–6 (`import logging`, `import os`, `import django`) appears after `django.setup()`.
- The post-setup block (lines 13–21: `aiogram`, `django.conf`, `telegram_bot.*`) may be reordered internally but remains after `django.setup()`.

### Acceptance Criteria

- `[tool.isort]` section deleted from `pyproject.toml`
- `I001` removed from `[tool.ruff.lint].ignore` (only `E501` remains)
- `known-first-party = ["apps", "config", "theme", "telegram_bot", "conftest"]` in `[tool.ruff.lint.isort]`
- `src = ["src", "src/backend"]` added under `[tool.ruff]`
- `combine-as-imports = true` preserved
- `"I"` comment updated to reflect ruff built-in isort
- `uv run ruff check src/ --select I` reports **0 errors** (178 violations fixed)
- `src/telegram_bot/main.py`: `django.setup()` still precedes all delayed imports (no import crosses the boundary)
- All import blocks under `src/` follow: stdlib → third-party → first-party, each alphabetically sorted with correct blank-line separation

### Verification

```powershell
# 1. Confirm 0 I001 violations (deterministic)
uv run ruff check src/ --select I --no-cache

# 2. Confirm no new violations introduced (full lint)
uv run ruff check src/ --no-cache
```

<!-- TASK_END: t1t2_import_sorting_config_and_autofix -->

---

## 8. Block 2 — T3: Verification Gate

<!-- TASK_START: t3_verify_import_sorting -->

```yaml
id: t3_verify_import_sorting
title: "T3: Verify ruff clean + basedpyright clean + make test passes"
type: verification
priority: high
depends_on:
  - t1t2_import_sorting_config_and_autofix
verifies:
  - t1t2_import_sorting_config_and_autofix
status: pending
agent: Validator
```

### Description

Verification gate for Block 1. Runs three checks in sequence: (1) ruff reports 0 I001 violations, (2) basedpyright passes with no new errors (the auto-fix is non-semantic — no type changes), (3) the full test suite passes via Docker Compose. No code changes in this block.

### Verification Steps

```powershell
# 1. Ruff import sorting clean
uv run ruff check src/ --select I --no-cache

# 2. Full lint clean (no new violations)
uv run ruff check src/ --no-cache

# 3. Basedpyright — non-semantic auto-fix should not introduce type errors
uv run basedpyright src/

# 4. Full test suite (Docker Compose, fast gate)
make test
```

### Pass Criteria

- `ruff check src/ --select I` → 0 errors
- `ruff check src/` → 0 errors (full lint, no new violations)
- `basedpyright src/` → 0 errors (no semantic change from isort reorder)
- `make test` → exits 0 (fast gate, skips nightly seed suite)

### Failure Action

Return Block 1 to Implementor. If basedpyright reports new errors, the auto-fix likely introduced a semantic issue (extremely unlikely for isort, but verify). If tests fail, review the specific test failure — likely an import-order-sensitive test that needs updating (rare; isort does not change import semantics).

### Rollback

If Block 2 fails and cannot be remediated:
```powershell
git reset HEAD~1 --soft   # uncommit, preserve working tree changes
git checkout -- src/      # restore all auto-fixed files to pre-fix state
git checkout -- pyproject.toml  # restore config
```
Re-investigate before retrying.

<!-- TASK_END: t3_verify_import_sorting -->

---

## 9. Block 3 — T4: Add `format` Target to Makefile + Makefile.ps1

<!-- TASK_START: t4_format_make_target -->

```yaml
id: t4_format_make_target
title: "T4: Add format target to Makefile and Makefile.ps1"
priority: medium
depends_on: []
classification: mandatory
risk: low
status: pending
source_reference: .ai/problems/21_import-sorting-configuration_spec.md
source_section: "§5 T4, §12.4"
agent: Implementor
```

### Description

Add a `format` make target that runs `uv run ruff check --fix src/` inside the `web` container, mirroring the existing `lint` target pattern. Add to both `Makefile` (GNU Make, Linux/macOS dev path) and `Makefile.ps1` (PowerShell, Windows primary dev path) for build-system parity.

**Design decision:** The `format` target runs `ruff check --fix` (not `ruff format`). Ruff's design separates linting (`ruff check`, including I001 import sorting) from formatting (`ruff format`, line wrapping/quotes only). The `format` target fixes lint issues including import sorting; `ruff format` is out of scope for this spec (spec §10 OQ1).

### Implementation Scope

**Files:**
- `Makefile` — `.PHONY` list, Code Quality help section, Code Quality targets section, dev Compose project variable assignment group
- `Makefile.ps1` — `Show-Help` function output, new `Invoke-Format` function (mirrors `Invoke-Lint`), `switch` dispatch block

### Changes

#### Makefile

| Location | Change |
|----------|--------|
| `.PHONY` list (line 3) | Add `format` after `lint` |
| Dev project var group (line 17) | Add `format` after `lint` (so `COMPOSE_PROJECT_NAME = mko-bazuna-dev` is exported) |
| `help` target → Code Quality section (line 48) | Add `@echo "  format         Auto-fix lint issues (including import sorting)"` after the `lint` line |
| Code Quality targets (after `lint:` target, line 109–110) | Add new target: |

```makefile
format:
	docker compose $(COMPOSE_FILES) run --rm web uv run ruff check --fix src/
```

#### Makefile.ps1

| Location | Change |
|----------|--------|
| `Show-Help` function (line 55) | Add `Write-Host "  format         Auto-fix lint issues (including import sorting) inside web container"` after the `lint` line |
| New function (after `Invoke-Typecheck`, line 176) | Add: |

```powershell
# Run linter with auto-fix inside web container
function Invoke-Format {
    $env:COMPOSE_PROJECT_NAME = $DevProject
    docker compose -f docker-compose.yml -f docker-compose.dev.override.yml run --rm web uv run ruff check --fix src/
}
```

| `switch` dispatch block (line 369) | Add `"format" { Invoke-Format }` after `"lint" { Invoke-Lint }` |

### Acceptance Criteria

- `make format` runs `ruff check --fix src/` inside the dev `web` container
- `.\Makefile.ps1 format` runs the equivalent command in the dev `web` container
- `format` added to `.PHONY` list (Makefile)
- `format` added to dev Compose project variable group (Makefile)
- `format` appears in `make help` output and `.\Makefile.ps1 help` output
- Both Makefile and Makefile.ps1 `format` targets follow the same pattern as `lint` (dev container, `COMPOSE_FILES` / `DevProject`, `--rm web`)

### Verification

```powershell
# Help text shows format target
make help | Select-String "format"
.\Makefile.ps1 help | Select-String "format"
```

### Commit

```yaml
type: feat
scope: build
description: "Add format make target to Makefile and Makefile.ps1 (runs ruff check --fix src/)"
files_to_stage:
  - Makefile
  - Makefile.ps1
```

<!-- TASK_END: t4_format_make_target -->

---

## 10. Block 4 — T5: Update Developer Documentation

<!-- TASK_START: t5_document_format_target -->

```yaml
id: t5_document_format_target
title: "T5: Update AGENTS.md and commands.md to document format target"
priority: medium
depends_on:
  - t4_format_make_target
classification: mandatory
risk: low
status: pending
source_reference: .ai/problems/21_import-sorting-configuration_spec.md
source_section: "§5 T5, §12.5"
agent: Doc-specialist
```

### Description

Update developer-facing documentation to record the new `format` make target and clarify the distinction between `ruff check --fix` (lint auto-fix, includes I001 import sorting) and `ruff format` (code formatter — line wrapping, quotes; does NOT sort imports).

### Implementation Scope

**Files:**
- `AGENTS.md` — Quick Reference section
- `.kilo/rules/commands.md` — Python (PowerShell) commands table

### Changes

#### AGENTS.md (Quick Reference, line 17)

Replace:
```
- **Lint:** `uv run ruff check <path>`
```
With:
```
- **Lint:** `uv run ruff check <path>` · **Auto-fix:** `uv run ruff check --fix <path>`
```

#### `.kilo/rules/commands.md` (Python commands table, lines 7–13)

The current table has `Format | uv run ruff format --check <path>` — the `--check` flag means "report only, modify nothing." Replace the entire table with the corrected version that adds an `Auto-fix` row and removes `--check` from the Format row:

| Lint | `uv run ruff check <path>` |
| Auto-fix | `uv run ruff check --fix <path>` |
| Format | `uv run ruff format <path>` |
| Typecheck | `uv run basedpyright <path>` |
| Add dep | `uv add <pkg>` / `uv add --dev <pkg>` |

Append a note below the table:
> `ruff check --fix` handles import sorting (I001) and other fixable lint rules. `ruff format` only formats code (line wrapping, quotes) — it does **NOT** sort imports. The `make format` target runs `ruff check --fix src/` (not `ruff format`).

### Acceptance Criteria

- `AGENTS.md` Quick Reference includes Auto-fix command
- `commands.md` Python table includes Auto-fix row and updated Format row
- `commands.md` includes a note clarifying `ruff check --fix` (imports + lint) vs `ruff format` (code formatting only)
- All user-visible strings wrapped in gettext (no new strings — documentation only, no user-facing text)

### Verification

```powershell
# Confirm changes are present
Select-String -Path AGENTS.md -Pattern "Auto-fix"
Select-String -Path .kilo/rules/commands.md -Pattern "Auto-fix"
Select-String -Path .kilo/rules/commands.md -Pattern "does NOT sort imports"
```

No tests needed — documentation-only changes.

### Commit

```yaml
type: docs
scope: docs
description: "Document format target and ruff check --fix vs ruff format distinction"
files_to_stage:
  - AGENTS.md
  - .kilo/rules/commands.md
```

<!-- TASK_END: t5_document_format_target -->

---

## 11. Verification Matrix

| Block | Agent | Verification command | Type | Pass criteria |
|-------|-------|---------------------|------|---------------|
| Block 1 (T1+T2) | Implementor | `uv run ruff check src/ --select I --no-cache` | Lint gate | 0 I001 errors |
| Block 1 (T1+T2) | Implementor | `uv run ruff check src/ --no-cache` | Lint gate | 0 errors (full) |
| Block 2 (T3) | Validator | `uv run basedpyright src/` | Typecheck | 0 errors |
| Block 2 (T3) | Validator | `make test` | Integration | Exits 0 (fast gate) |
| Block 3 (T4) | Implementor | `make help | Select-String "format"` | Smoke | `format` target listed |
| Block 3 (T4) | Implementor | `.\Makefile.ps1 help | Select-String "format"` | Smoke | `format` target listed |
| Block 4 (T5) | Doc-specialist | `Select-String -Path AGENTS.md -Pattern "Auto-fix"` | Doc check | Present |
| Block 4 (T5) | Doc-specialist | `Select-String -Path .kilo/rules/commands.md -Pattern "Auto-fix"` | Doc check | Present |

**Note on test environment:** All test commands must run via Docker Compose (`make test` or `$dc run --rm test`). The test DB is PostgreSQL 18 on port 5433, already running. Local `uv run pytest` fails (no DB on localhost:5432).

**Note on CI scope:** After Block 1, CI's `lint` job (`ruff check .` from `src/backend/` cwd in ci.yml) will enforce I001 on `src/backend/` files only — not `src/telegram_bot/` (pre-existing scope limitation, out of scope for this spec). T2 fixes all of `src/`, so CI passes.

---

## 12. Risk Assessment

| Risk | Block | Impact | Severity | Mitigation |
|------|-------|--------|----------|------------|
| **CI atomicity** — T1 committed without T2 | Block 1 | CI `lint` job fails with 178 errors | HIGH | T1+T2 in same atomic commit (enforced by plan structure). Inline pre-check in Block 1 catches config errors before `--fix`. |
| **Bot bootstrap reorder** — spec claim is false | Block 1 | `main.py` imports reordered despite `# noqa: E402` | LOW (post-correction) | The spec's claim is corrected in this plan. Ruff isort never moves imports across code statements — `django.setup()` (line 11) is an immovable barrier. Acceptance criterion explicitly requires verifying the boundary. Inline `--diff` pre-check lets Implementor review before applying. |
| **known-first-party misclassification** | Block 1 | Ruff misclassifies imports, causing 0 or wrong fixes | LOW | All 5 packages verified importable by Auditor (§2). Post-fix `ruff check --select I` = 0 errors confirms correct classification. |
| **Large diff (170 files)** | Block 1 | Reviewer difficulty — changes obscure logic | LOW | T2 is a standalone mechanical commit titled "chore: auto-fix import sorting" with no other changes. PR description notes it's a pure isort reformat. |
| **Makefile.ps1 parity** | Block 3 | Windows devs miss `format` target | LOW | Blocked 5 (question 2) resolves: both Makefile and Makefile.ps1 get the target. |
| **`ruff format` vs `ruff check --fix` confusion** | Block 3+4 | Devs run `ruff format` expecting import sorting | LOW | T5 documentation explicitly clarifies: `ruff format` = code formatter (no imports); `ruff check --fix` = lint auto-fix (includes I001). |
| **CI scope limitation** | (info) | CI doesn't lint `src/telegram_bot/` | LOW | Pre-existing (CI runs `ruff check .` from `src/backend/` cwd). T2 fixes all of `src/`, so `make lint` (which checks `src/`) is the authoritative local gate. Not changed by this spec. |

**No Auditor, Researcher, or Planner agent required for implementation.** The Auditor already verified all findings (code-context-import-sorting.md). The inline `--diff` pre-check in Block 1 replaces a separate Auditor review. The spec's §4 research is comprehensive. Implementation is deterministic (isort auto-fix is mechanical, non-semantic).

---

## 13. Agent Requirements

| Block | Primary agent | Secondary agent | When |
|-------|---------------|-----------------|------|
| Block 1 (T1+T2) | **Implementor** | — | Run config edits + `ruff check --select I --fix` + commit atomically |
| Block 2 (T3) | **Validator** | — | Run ruff + basedpyright + `make test` gate after Block 1 lands |
| Block 3 (T4) | **Implementor** | — | Add `format` target to Makefile + Makefile.ps1 |
| Block 4 (T5) | **Doc-specialist** | — | Update AGENTS.md + commands.md |

**No agent required for:** Auditor (already verified), Researcher (spec §4 is comprehensive), Planner (this document).

---

## 14. CI & Deployment Considerations

### 14.1 CI lint job (ci.yml L121–137)

- **Current state:** `lint` job runs `uv run ruff check .` from `working-directory: src/backend`. Since `I001` is in `ignore`, CI passes despite 178 violations.
- **After Block 1:** `ruff check .` from `src/backend/` will enforce I001 on all files under `src/backend/`. T2 fixes all violations in `src/` (including `src/backend/`), so CI will pass.
- **CI action:** No file changes needed. CI uses the config from `pyproject.toml` (committed in Block 1). The `lint` job runs check-only (`ruff check .` without `--fix`) — this is correct (CI detects, does not modify).
- **Pre-existing scope limitation:** CI lints `.` relative to `src/backend/`, so `src/telegram_bot/` is NOT covered by CI. This is out of scope. Local `make lint` (`ruff check src/`) is the authoritative lint gate covering both.

### 14.2 CI nightly (ci-nightly.yml)

- Runs only the `seed` test suite. No lint job. Unaffected by this spec.

### 14.3 Deployment impact

- **Zero deployment impact.** Import sorting is a pure lint/code-organization change. No schema migrations, no settings changes, no runtime behavior change. The `main.py` reordering preserves the `django.setup()` boundary, so bot bootstrap is unaffected. Both processes (web + bot) start identically.

### 14.4 i18n completeness gate

- Import sorting changes touch `.py` files only — no template or `.po`/`.mo` changes.
- `test_i18n_completeness.py` is unaffected (it scans templates and `.po` msgstrs, not Python import order).
- T3 verification does not need to run the i18n gate, but it runs as part of `make test` (fast gate includes `seed` exclusion but not i18n-specific exclusion — i18n tests are `@pytest.mark.unit`, included in fast gate).

---

## 15. Git Strategy

| Commit | Contents | Type | Reviewer notes |
|--------|----------|------|----------------|
| 1 | T1 (pyproject.toml config) + T2 (all `src/**/*.py` auto-fixes) | `chore(imports)` | Mechanical isort reformat. Review focus: config correctness. `src/telegram_bot/main.py` is the only file with a non-trivial rationale (django.setup() boundary preserved). |
| 2 | T4 (Makefile + Makefile.ps1 `format` target) | `feat(build)` | Code change to build workflow. |
| 3 | T5 (AGENTS.md + commands.md docs) | `docs` | Documentation only. |

**PR recommendation:** One PR containing all 3 commits. Block 2 (T3 verification) gates Commit 1 before Commits 2+3. Alternatively: PR 1 = Commit 1 only; PR 2 = Commits 2+3.

---

## 16. Artifacts

| Artifact | Status | Location |
|----------|--------|----------|
| Source spec (T1–T5, Q1–Q4, DoR) | ✅ Validated | `.ai/problems/21_import-sorting-configuration_spec.md` |
| Auditor verification (discrepancies) | ✅ Validated | `.ai/plans/code-context-import-sorting.md` |
| Existing task template (YAML) | ✅ Reference | `.ai/tasks/templates/task_template.yaml` |
| Verification task template (YAML) | ✅ Reference | `.ai/tasks/templates/task_template_verification.yaml` |
| This execution plan | ✅ Active | `.ai/plans/22-import-sorting-configuration-execution.md` |
| CI workflow (lint job) | ✅ Reference | `.github/workflows/ci.yml` (L121–137) |
| Bot bootstrap file (corrected) | ✅ Reference | `src/telegram_bot/main.py` |
| Makefile (format target source) | ✅ Reference | `Makefile` |
| Makefile.ps1 (format target source) | ✅ Reference | `Makefile.ps1` |
| AGENTS.md (doc target) | ✅ Reference | `AGENTS.md` (L17) |
| commands.md (doc target) | ✅ Reference | `.kilo/rules/commands.md` (L7–13) |

---

*This plan is execution-oriented. It decomposes the validated spec into 4 dependency-ordered blocks with semantic anchors (no line numbers in implementation scope), inline safety checks, and a clear CI-atomicity constraint. All 6 planner questions are answered in §2. Both HIGH-severity Auditor discrepancies (§3) are corrected in the plan structure and acceptance criteria.*

*Generated: 2026-09-10 — Planning only. No code modified.*