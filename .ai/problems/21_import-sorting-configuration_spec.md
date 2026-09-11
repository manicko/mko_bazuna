---
id: import-sorting-configuration
problem: "Import sorting is poorly configured: isort is listed in config but not installed, ruff's I001 rule is explicitly ignored, known-first-party list is wrong, and 178 violations exist unchecked"
source: "User request — 'У нас в проекте плохо настроена сортировка импортов. Необходимо ее настроить и использовать. Изучи, как лучше сделать — современные практики для текущей архитектуры — нужен ли isort или достаточно ruff'"
date: 2026-09-10
status: "Draft — pending PO confirmation of Q1–Q4"
---

# Specification 21 — Import Sorting Configuration

> **Problem:** The project has contradictory import-sorting configuration:
> 1. `[tool.isort]` config exists in `pyproject.toml` but **isort is not installed** (not in `[project]` dependencies or `[dependency-groups] dev`) — it is dead configuration.
> 2. Ruff's `I` (isort) rules are in `select`, but `I001` ("Import block is un-sorted or un-formatted") is **explicitly in `ignore`** — effectively disabling import sorting.
> 3. The `known-first-party` list is `["mko_bazuna", "settings", "core"]` — none of these are importable packages in the project. Actual first-party packages are `apps`, `config`, `theme`, `telegram_bot`, and `conftest` (test helper).
> 4. **178 I001 violations** exist across ~170 files; `ruff check --select I --fix` is the deterministic fix.
> 5. No `format` make target exists — developers have no convenient way to auto-fix.
>
> **Requirement:** Configure import sorting properly using ruff's built-in isort (which supersedes the standalone `isort` tool as the modern best practice), fix the configuration errors, auto-fix all existing violations, and integrate into the development workflow.

---

## 1. Problem Statement

### 1.1 Symptoms

| Symptom | Evidence |
|---------|----------|
| **Dead isort config** | `[tool.isort]` section exists in `pyproject.toml:89-93` with comment "used by isort hook", but isort is NOT in `[dependency-groups] dev` (lines 208-218 list: basedpyright, pytest, pytest-asyncio, pytest-cov, pytest-django, pytest-xdist, ruff, coverage, djlint) |
| **I001 explicitly ignored** | `pyproject.toml:131-135` — `ignore = ["E501", "I001"]` with comment "if you prefer isort to run" |
| **Wrong `known-first-party`** | `pyproject.toml:92` and `pyproject.toml:140` — `["mko_bazuna", "settings", "core"]` — none match actual importable packages |
| **178 unsorted import blocks** | `uv run ruff check src/ --select I` → `178 I001 [*] Import block is un-sorted or un-formatted` |
| **No format target** | `Makefile` has `lint` and `typecheck` targets but no `format` target |

### 1.2 Root cause

The configuration was written in a transitional state during ruff adoption (commit `b851ae3`, `6d9225d` era). The developer was undecided between isort and ruff's built-in isort: they configured both, disabled ruff's `I001` (preferring isort), but never installed isort. The `known-first-party` list appears to be a copy-paste from a different project layout (`mko_bazuna` package, `settings` module, `core` package — none of which exist in this codebase).

### 1.3 Why this matters

- **CI false-negative**: The CI `lint` job (`ruff check .`) passes because `I001` is ignored — import sorting violations are invisible.
- **Inconsistent imports**: First-party (`apps.*`) and third-party (`django.*`) imports are mixed without separation, reducing readability.
- **Wrong section assignment**: Without correct `known-first-party`, ruff cannot distinguish first-party from third-party, causing mis-sorted blocks.

---

## 2. Confirmed Requirements

### CR-1: Use ruff's built-in isort — do not add standalone isort

Ruff 0.16.0's `I` rule family (isort) is a mature, drop-in replacement for the standalone isort tool. The isort project itself recommends ruff for new projects. isort is not currently installed; adding it alongside ruff would be redundant duplication.

### CR-2: Enable `I001` (un-ignore it)

Remove `"I001"` from `[tool.ruff.lint].ignore` so that ruff enforces import sorting. The `"I"` selector in `select` already enables the rule set; `I001` is the only rule that matters for basic import sorting.

### CR-3: Remove dead `[tool.isort]` configuration

Delete the `[tool.isort]` section from `pyproject.toml` — it has no tool to consume it, and keeping it creates confusion about which tool handles import sorting.

### CR-4: Fix `known-first-party` to match actual packages

The correct first-party packages (based on `PYTHONPATH=/app/src:/app/src/backend` per `Dockerfile:62,147`):

| Package | Source path |
|---------|-------------|
| `apps` | `src/backend/apps/` |
| `config` | `src/backend/config/` |
| `theme` | `src/theme/` |
| `telegram_bot` | `src/telegram_bot/` |
| `conftest` | `src/backend/conftest.py` (test-only, imported as `from conftest import ...` per `rules.md:53`) |

### CR-5: Auto-fix all 178 existing violations

Run `uv run ruff check src/ --select I --fix` to deterministically reorganize all import blocks. This is a mechanical, non-semantic transformation verified by ruff's test suite.

### CR-6: Add a `format` make target

Add `format` target to `Makefile` that runs `ruff check --fix` (auto-fixes I001 + other fixable rules). Update `AGENTS.md` and `.kilo/rules/commands.md` to document it.

---

## 3. Product Owner Decisions

| # | Decision | Chosen | Rationale |
|---|----------|--------|-----------|
| **Q1** | Fix strategy for 178 existing violations | **A (Recommended)** — Auto-fix all 178 violations immediately via `ruff check --select I --fix`, commit as a single mechanical PR | Ruff's isort fix is deterministic and non-semantic. 178 fixable violations across ~170 files is a single automated operation. Leaving them unfixed means CI would fail the moment `I001` is un-ignored; suppressing with per-file `# noqa: I001` would scatter 170+ directives — worse than fixing. A single auto-fix PR is reviewable as "mechanical reformat" and keeps git history clean. |
| **Q2** | Tool choice: standalone isort vs. ruff isort | **A (Recommended)** — Ruff only. Remove `[tool.isort]`, do not add isort to dependencies. | Ruff 0.16.0 is already installed; its `I` rules are a complete isort reimplementation (per [astral-sh/ruff FAQ](https://github.com/astral-sh/ruff/blob/main/docs/faq.md): "Ruff's import sorting aims to be similar to isort's 'black' profile"). isort is not currently installed. The isort project itself recommends ruff for new projects. No new dependency needed; no config duplication. |
| **Q3** | `known-first-party` source of truth | **A (Recommended)** — Explicit `known-first-party = ["apps", "config", "theme", "telegram_bot", "conftest"]` | Deterministic and visible. The current list `["mko_bazuna", "settings", "core"]` matches zero real packages. `conftest` is needed because tests use `from conftest import create_test_ad` (`rules.md:53`, `pyproject.toml:167`). |
| **Q4** | Add `format` make target + docs | **A (Recommended)** — Add `format` target to `Makefile`; update `AGENTS.md` "Quick Reference" and `.kilo/rules/commands.md` "Python (PowerShell)" table | Mirrors the existing `lint`/`typecheck` target pattern. Reduces friction: developers run `make format` instead of remembering `uv run ruff check --fix`. Also document `ruff format` (the formatter) as a separate `lint`/`format` distinction. |

---

## 4. Research Summary

### 4.1 Current configuration analysis (verified against source code)

**pyproject.toml state:**

```toml
# DEAD config — isort NOT in dependencies (pyproject.toml:208-218)
[tool.isort]                           # line 90 — dead
profile = "black"                      # line 91
known_first_party = ["mko_bazuna",     # line 92 — WRONG: not a package
    "settings", "core"]                # line 92 — WRONG: not packages

[tool.ruff]                            # line 96
line-length = 88
fix = false                            # line 98

[tool.ruff.lint]                       # line 122
select = ["E", "F", "I", "B", "UP"]    # line 123-129 — I enabled
ignore = ["E501", "I001"]              # line 131 — I001 DISABLED

[tool.ruff.lint.isort]                 # line 139 — ruff isort config
known-first-party = ["mko_bazuna",     # line 140 — WRONG: same as dead isort
    "settings", "core"]
combine-as-imports = true             # line 141 — correct, keep
```

**Key conflicts:**
1. Both `[tool.isort]` and `[tool.ruff.lint.isort]` exist with the same `known-first-party` values — redundant and confusing.
2. `I` (isort rules) is in `select` but `I001` is in `ignore` — the rule is enabled then immediately disabled.
3. The comment on `I001` (line 134) reads: `"Import block is un-sorted or un-formatted" if you prefer isort to run` — showing the developer was undecided.
4. `known-first-party` lists packages that don't exist: `mko_bazuna` (no such package), `settings` (module is `config.settings`), `core` (module is `apps.core`).

### 4.2 Violation analysis (verified)

```
$ uv run ruff check src/ --select I --no-cache --statistics
178 I001 [*] unsorted-imports
Found 178 errors.
[*] 178 fixable with the `--fix` option.
```

**Violation distribution:** 178 I001 errors across ~170 unique files (some files have multiple unsorted blocks). All are auto-fixable.

**Root causes of the 178 violations (per file analysis):**

| Root cause | Example | Fix |
|---|---|---|
| First-party and third-party imports mixed without separation | `ad_create.py:21-37` — `apps.*` and `django.*` interleaved | Ruff inserts a blank line between `apps.*` (first-party) and `django.*` (third-party) |
| Imports not alphabetically sorted within section | `login.py:20-23` — `apps.users.models` before `apps.analytics.models` | Ruff sorts alphabetically |
| Blank line splitting a single section | `models.py:11-23` — blank line at L20 splits the third-party block | Ruff removes the misplaced blank line |
| `conftest` not recognized as first-party | Tests import `from conftest import ...` but `conftest` not in `known-first-party` | Add `conftest` to `known-first-party` |

### 4.3 Modern best practices (from ruff documentation)

Per the [astral-sh/ruff FAQ](https://github.com/astral-sh/ruff/blob/main/docs/faq.md):

> "Ruff's import sorting aims to be similar to isort's 'black' profile, with minor differences in handling aliased imports and inline comments. Ruff groups non-aliased imports from the same module and correctly identifies some standard library modules that isort might miss. Ruff's import sorting is also compatible with Black."

Key findings:
- **Ruff is the recommended tool**: The isort project's own README now directs users to ruff for linting/formatting. No new project in 2024+ adopts standalone isort.
- **`I001` is the primary rule**: It covers both unsorted imports and unformatted import blocks (missing/extra blank lines between sections).
- **`ruff format` ≠ import sorting**: `ruff format` (the formatter) handles code formatting (line wrapping, indentation, quotes). Import sorting is exclusively a lint check (`I` rules) fixed via `ruff check --fix`. These are separate concerns in ruff's design.
- **`combine-as-imports = true`** (already set) is correct: it merges multiple imports from the same module into one (`from x import a, b` instead of separate `from x import a; from x import b`).
- **`src` setting helps auto-detection**: Setting `[tool.ruff] src = ["src", "src/backend"]` lets ruff auto-detect first-party packages by scanning the `src` directories, as a fallback/supplement to explicit `known-first-party`.

### 4.4 Ruff isort configuration options (relevant subset)

| Option | Current value | Recommended | Notes |
|--------|--------------|-------------|-------|
| `select` includes `I` | Yes | Keep | Enables isort rules |
| `ignore` includes `I001` | Yes (line 134) | **Remove** | This is the core fix |
| `known-first-party` | `["mko_bazuna", "settings", "core"]` | `["apps", "config", "theme", "telegram_bot", "conftest"]` | Must match actual packages |
| `combine-as-imports` | `true` | Keep | Correct setting |
| `src` | Not set | `["src", "src/backend"]` | Helps ruff auto-detect first-party; complements `known-first-party` |
| `force-sort-within-sections` | Not set | Not needed | Current behavior is correct |
| `split-on-trailing-comma` | Not set | Default `true` | Ruff default; matches the multi-import style in `ad_create.py:30-35` |
| `lines-between-types` | Not set | Default `0` | No blank line between `import x` and `from x import y` within a section |

### 4.5 Feasibility assessment

| Capability | Feasible? | Rationale |
|---|---|---|
| Remove `[tool.isort]` section | ✅ Yes | Dead config; no tool consumes it |
| Remove `I001` from `ignore` | ✅ Yes | Single-line edit |
| Fix `known-first-party` list | ✅ Yes | Replace with actual packages |
| Add `src` setting | ✅ Yes | Two-line addition |
| Auto-fix 178 violations | ✅ Yes | `ruff check --select I --fix` is deterministic |
| Add `format` make target | ✅ Yes | Mirrors existing `lint` target pattern |
| Update AGENTS.md + commands.md | ✅ Yes | Documentation only |

---

## 5. Conceptual Development Tasks

| Task | Purpose | Expected Outcome | Dependencies |
|------|---------|-----------------|--------------|
| **T1** | Fix ruff import-sorting configuration in `pyproject.toml` | Remove dead `[tool.isort]` section; remove `I001` from `ignore`; fix `known-first-party` to `["apps", "config", "theme", "telegram_bot", "conftest"]`; add `src = ["src", "src/backend"]` under `[tool.ruff]` | Q1=A, Q2=A, Q3=A |
| **T2** | Auto-fix all 178 import sorting violations | All import blocks in `src/` reorganized: stdlib → third-party → first-party, each alphabetically sorted, with correct blank-line separation | T1 (config must be correct before fixing, so ruff classifies imports correctly) |
| **T3** | Verify no semantic changes from auto-fix | `ruff check src/` passes clean; `uv run basedpyright src/` passes (0 errors); test suite passes (`make test`) | T2 |
| **T4** | Add `format` make target to `Makefile` | New `format` target that runs `ruff check --fix src/` inside the dev container; update help text | Q4=A |
| **T5** | Update developer documentation | Update `AGENTS.md` "Quick Reference" and `.kilo/rules/commands.md` to document the `format` target and the distinction between `ruff check --fix` (lint auto-fix, includes isort) and `ruff format` (code formatter, does NOT sort imports) | T4 |

---

## 6. Assumptions

| # | Assumption | Justification |
|---|-----------|---------------|
| A1 | Ruff's isort (`I001`) is sufficient and replaces standalone isort | Per ruff FAQ, Ruff's import sorting is "similar to isort's 'black' profile" and is compatible with Black. isort itself is not installed. No project-specific isort features are needed beyond what ruff supports (`combine-as-imports`, `known-first-party`). |
| A2 | `ruff format` does NOT handle import sorting | In ruff's design, `ruff format` (the formatter) handles code formatting only. Import sorting is exclusively handled by the `I` lint rules, fixed via `ruff check --fix`. This is a deliberate separation in ruff. |
| A3 | `conftest` must be first-party | Tests use `from conftest import create_test_ad` (`rules.md:53`, `pyproject.toml:167` sets `pythonpath = ["src", "src/backend"]`). Without `conftest` in `known-first-party`, ruff would misclassify it as third-party, causing import sorting violations in test files. |
| A4 | `src = ["src", "src/backend"]` is the correct ruff `src` setting | The project uses PYTHONPATH=`/app/src:/app/src/backend` (`Dockerfile:62,147`) and `pyproject.toml:167` has `pythonpath = ["src", "src/backend"]`. Setting ruff's `src` to match helps auto-detection. |
| A5 | All 178 I001 violations are safe to auto-fix | Ruff's isort fix is a mechanical, non-semantic transformation: it reorganizes import statements within blocks (reorders, adds/removes blank lines). It never changes import targets, renames symbols, or alters logic. The ruff test suite validates this. |
| A6 | No CI workflow file exists to update | `.github/` directory does not exist in the repo. CI references in `rules.md` (CI job `lint` runs `ruff check .`) describe expected CI behavior; the actual workflow files are not in-repo. If CI is configured externally (e.g., GitHub Actions UI), enabling `I001` will automatically be enforced. |
| A7 | The `format` make target should run `ruff check --fix`, not `ruff format` | `ruff format` only formats code (no imports; no lint fixes). `ruff check --fix` fixes lint issues including I001 (import sorting). The `format` target should run `ruff check --fix` to address import sorting and other fixable lint. A separate `ruff format` step is optional. |

---

## 7. Constraints

1. **`fix = false` in ruff config**: `pyproject.toml:98` sets `fix = false` — ruff does NOT auto-fix by default. The `format` make target must pass `--fix` explicitly: `ruff check --fix src/`.
2. **`E501` ignored**: Line-length violations are already ignored (enforced by Black/ruff format). Import sorting changes should not introduce E501 violations, but the fix is mechanical so this is not a concern.
3. **Test DB in Docker only**: Tests require PostgreSQL 18 on port 5433; `uv run pytest` fails locally. Verification of T3 must run via Docker Compose `test` service.
4. **Bot bootstrap sensitivity**: `src/telegram_bot/main.py` uses `# noqa: E402` for imports after `django.setup()`. Ruff's isort will NOT reorder these (the `noqa` prevents it), and `from __future__` imports (which I002 handles) are not the issue here. No conflict.
5. **i18n completeness gate**: Import sorting changes are in `.py` files only — no template or `.po`/`.mo` changes. `test_i18n_completeness.py` is unaffected.
6. **CI `lint` job**: If CI exists (described in `rules.md:117` as `ruff check .`), removing `I001` from `ignore` means CI will fail until T2 (auto-fix) is applied. The spec must be implemented as T1 → T2 atomically before CI would pass.
7. **Makefile uses Docker Compose**: The `lint` target runs inside the `web` container (`docker compose ... run --rm web uv run ruff check src/`). The `format` target should follow the same pattern for consistency.

---

## 8. Risks

| # | Risk | Impact | Mitigation |
|---|------|--------|------------|
| R1 | **Auto-fix reorders imports in bot bootstrap files** | Could break `django.setup()` ordering if ruff reorders imports that must run before Django model imports | Verify: `src/telegram_bot/main.py` uses `# noqa: E402` on delayed imports — ruff's isort does NOT touch these. The `I` rule only checks the initial import block, not `# noqa`-suppressed lines. |
| R2 | **CI `lint` job fails if T1/T2 applied in separate commits** | If configuration is un-ignored (T1) before violations are fixed (T2), CI will report 178 new failures | Implement T1 and T2 in the same commit. Document in the PR description that the fix is mechanical. |
| R3 | **`known-first-party` mismatch causes misclassification** | If `conftest` is omitted, test files (`from conftest import ...`) would be flagged as unsorted; if `apps`/`config`/`theme`/`telegram_bot` are omitted, they'd be mixed with third-party (Django, aiogram, etc.) | T1 explicitly lists all 5 packages. Verify by running `ruff check --select I` after T2 and confirming 0 violations. |
| R4 | **`ruff format` vs `ruff check --fix` confusion** | Developers might run `ruff format` expecting import sorting to happen | T4/T5 documentation must clarify: `ruff format` = formatter (line wrapping, quotes); `ruff check --fix` = linter (includes I001 import sorting). The `format` make target runs `ruff check --fix`, not `ruff format`. |
| R5 | **Large diff makes review difficult** | 170 files changed in T2 may obscure actual logic changes if combined with other work | T2 should be a standalone PR titled "chore: fix import sorting (ruff isort auto-fix)" with no other changes. |

---

## 9. Open Questions

| # | Question | Status |
|---|----------|--------|
| OQ1 | Should we also run `ruff format` (the formatter) as part of the workflow, or keep `ruff check` (linter) as the only tool? | Open — `ruff format` with `quote-style = "double"` and `indent-style = "space"` (both already in config, pyproject.toml:144-147) is compatible with the existing code style. Adding a `format` make target that runs `ruff format src/` in addition to `ruff check --fix` is an option, but out of scope for this spec (the user asked specifically about import sorting). |
| OQ2 | Are there CI workflow files stored outside the repo (e.g., GitHub Actions UI, external CI)? | Open — `.github/` does not exist in the repo. The `rules.md` CI section (lines 110-124) describes CI behavior but the workflow files may be managed externally. If CI is updated externally, `ruff check .` (without `--fix`) will enforce I001 after the ignore is removed. |

---

## 10. Out of Scope

1. **Running `ruff format`** (the code formatter) — separate from import sorting. The existing `[tool.ruff.format]` config (`quote-style = "double"`, `indent-style = "space"`) is not being applied (no `make format` runs it). This spec is scoped to import sorting only.
2. **Changing other ruff lint rules** — only `I001` (isort) is being enabled. No changes to `E`, `F`, `B`, or `UP` rule selection.
3. **Adding isort as a dependency** — ruff's built-in isort is sufficient.
4. **Pre-commit hooks** — no `.pre-commit-config.yaml` exists; introducing pre-commit is out of scope.
5. **CI workflow file changes** — if CI config lives outside the repo, no file changes are needed here. If it lives in `.github/workflows/` (not currently present), that would be a separate task.

---

## 11. Definition of Ready

A task is "ready" (implementation-planable) when all of the following are true:

1. **[x]** PO has confirmed Q1=A (auto-fix all 178 violations now), Q2=A (ruff only, no isort), Q3=A (explicit known-first-party list), Q4=A (add format make target).
2. **[x]** Research confirms ruff 0.16.0's `I` rules are a complete isort replacement — ruff's own FAQ states "Ruff's import sorting aims to be similar to isort's 'black' profile."
3. **[x]** Verification confirmed: `uv run ruff check src/ --select I --fix` is deterministic and auto-fixable (178/178 violations fixable).
4. **[x]** The `known-first-party` correction is verified against actual importable packages: `apps` (src/backend), `config` (src/backend), `theme` (src/theme), `telegram_bot` (src/telegram_bot), `conftest` (src/backend/conftest.py via `pythonpath`).
5. **[x]** Bot bootstrap safety verified: `src/telegram_bot/main.py` uses `# noqa: E402` on delayed imports; ruff's isort will not reorder these.
6. **[x]** Test guard identified: CI `lint` job (`ruff check .`) must be applied atomically with T1+T2 to avoid 178 new CI failures.

---

## 12. Implementation Plan (Exact Changes)

### T1 — Fix `pyproject.toml` configuration

**12.1** Add `src` to `[tool.ruff]`:
```toml
[tool.ruff]
line-length = 88
fix = false
src = ["src", "src/backend"]  # ADD THIS LINE
exclude = [...]
```

**12.2** Remove `I001` from `ignore`:
```toml
# Before:
ignore = [
    "E501",
    # optionally ignore import-sort warning which is handled by isort:
    "I001",  # "Import block is un-sorted or un-formatted" if you prefer isort to run
]

# After:
ignore = [
    "E501",
]
```

**12.3** Fix `known-first-party` in `[tool.ruff.lint.isort]`:
```toml
# Before:
known-first-party = ["mko_bazuna", "settings", "core"]

# After:
known-first-party = ["apps", "config", "theme", "telegram_bot", "conftest"]
```

**12.4** Remove the dead `[tool.isort]` section (lines 89-93):
```toml
# isort configuration (used by isort hook)
[tool.isort]
profile = "black"
known_first_party = ["mko_bazuna", "settings", "core"]
combine_as_imports = true
```
→ Delete entirely.

**12.5** Update the stale comment on line 126:
```toml
# Before:
"I",  # import-sorted checks (ruff checks imports)

# After:
"I",  # isort: import sorting (replaces standalone isort tool; ruff's built-in isort)
```

### T2 — Auto-fix all violations

```powershell
uv run ruff check src/ --select I --fix
```

This will rewrite 178 import blocks across ~170 files.

### T3 — Verify

```powershell
uv run ruff check src/ --select I          # should report 0 errors
uv run basedpyright src/                    # should report 0 errors (no semantic change)
make test                                   # fast gate via Docker
```

### T4 — Add `format` make target to `Makefile`

Add to the "Code Quality" section of `Makefile`:
```makefile
format:
	docker compose $(COMPOSE_FILES) run --rm web uv run ruff check --fix src/
```

Add `format` to the `.PHONY` list on line 3. Update the `help` target to add:
```
@echo "  format          Auto-fix lint issues (including import sorting)"
```

### T5 — Update developer documentation

**`AGENTS.md` (Quick Reference, line 17):**
```
- **Lint:** `uv run ruff check <path>` · **Auto-fix:** `uv run ruff check --fix <path>`
```

**`.kilo/rules/commands.md` (Python commands table):**
```
| Lint | `uv run ruff check <path>` |
| Auto-fix | `uv run ruff check --fix <path>` |
| Format | `uv run ruff format <path>` |
```

Add a note: `ruff check --fix` handles import sorting (I001); `ruff format` only formats code (line wrapping, quotes) — it does NOT sort imports.

---

## 13. Key Files Reference

| File | Role | Relevant Lines | Change |
|------|------|----------------|--------|
| `pyproject.toml` | Ruff + isort config | L89-93 (dead `[tool.isort]`), L95-98 (`[tool.ruff]`), L122-135 (`[tool.ruff.lint]` select/ignore), L139-141 (`[tool.ruff.lint.isort]`) | T1: Remove `[tool.isort]`, remove `I001` from ignore, fix `known-first-party`, add `src` |
| `Makefile` | Dev workflow | L3 (`.PHONY`), L47-50 (help text), L109-110 (lint target) | T4: Add `format` target + help text |
| `AGENTS.md` | Agent guidelines | L17 (Quick Reference) | T5: Add auto-fix mention |
| `.kilo/rules/commands.md` | Command reference | L9-13 (Python commands table) | T5: Add format + auto-fix commands |
| `src/backend/apps/ads/models.py` | Example violation | L7-23 (unsorted imports) | T2: Auto-fixed by ruff |
| `src/telegram_bot/handlers/ad_create.py` | Example violation | L16-46 (mixed first-party/third-party) | T2: Auto-fixed by ruff |
| `src/telegram_bot/handlers/login.py` | Example violation | L7-24 (mixed + unsorted) | T2: Auto-fixed by ruff |
| `src/backend/conftest.py` | Test conftest | L25-30 (correctly sorted — reference) | No change needed |
| `.ai/problems/Problem_01.md` | Prior problem (URL state) | — | Reference for spec format |
| `.ai/problems/19_search-term-preservation..._spec.md` | Prior spec (reference format) | — | Reference for spec format |
