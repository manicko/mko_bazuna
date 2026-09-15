# Execution Plan — pytest-9 Plugin Registration Fix (ISO-4 Verification)

Decomposition of the remaining work from `.ai/research/24-pytest9-plugin-registration-findings.md`
into dependency-aware, independently reviewable execution blocks.

> **Not an implementation.** Specifies *what* to change and *in what order*, with
> semantic targets and verification gates. The Implementor executes; the Validator confirms.

---

## Overview

The ISO-4 code change (inner `transaction.atomic()` savepoint + `try/except Exception`
around `TrustCalculator().calculate_and_save()` in `_pass_moderation`) is **already
committed** at `c789933`. The plugin-registration fix needs **correction**: the root
`conftest.py` approach causes a module shadowing conflict (55 test files import
`from conftest import create_test_ad`), so it must be replaced with `-p testing.moderation_fixtures`
in `addopts`. Three items remain:

1. **Correct plugin registration** — delete root `conftest.py`; add `-p testing.moderation_fixtures` to `addopts` (Defect A); keep lazy imports (Defect B). Verify the 18 previously-broken tests now pass.
2. **Add** `strict_config = true` to `pyproject.toml` (defense-in-depth).
3. **Add** the ISO-4 invariant test (mock `TrustCalculator` to raise → ad stays `PUBLISHED`).

A final commit-scoping block ensures only plan-relevant files are committed, given
many unrelated uncommitted changes exist in the working tree.

---

## Verified Current State

| Item | Status | Git state | Evidence |
|---|---|---|---|
| ISO-4 code change (`_pass_moderation` inner savepoint) | ✅ Committed | `c789933` is HEAD; `auto_moderation.py` not in `git status` | `git log` confirms `c789933` |
| Defect A — `pytest_plugins` removed from `[tool.pytest.ini_options]` | ✅ In WT | `pyproject.toml` modified (M) | `git diff HEAD -- pyproject.toml` shows 1-line deletion |
| Defect A — root `conftest.py` created | ⚠️ INCORRECT — causes shadowing | `conftest.py` untracked (??) | 55 test files use `from conftest import create_test_ad`; root conftest shadows `src/backend/conftest.py` → `ImportError` |
| Defect A (corrected) — `-p testing.moderation_fixtures` in addopts | ❌ Not done | absent from `pyproject.toml` | Must REPLACE root conftest.py approach (see Block A) |
| Defect B — lazy `ModerationCriteria` import in both fixtures | ✅ In WT | `moderation_fixtures.py` modified (M) | `git diff HEAD` shows import moved inside fixture functions (lines 53, 78) |
| `strict_config = true` | ❌ Not done | absent from `pyproject.toml` | findings §6.3 / §9.3 |
| ISO-4 invariant test | ❌ Not done | no test mocks `TrustCalculator` to raise | findings §2.2, §9.4 |
| Plan/research docs committed | ❌ Not done | untracked | `.ai/research/24-*.md`, `.ai/plans/26-*.md` |

### Plugin loading mechanism (verified)

- Root `conftest.py` declares `pytest_plugins = ["testing.moderation_fixtures"]` as a
  **module-level variable** — the only mechanism pytest recognizes (findings §3.1).
- `pythonpath = ["src", "src/backend"]` in `pyproject.toml` makes the `testing`
  package importable from the project root (rootdir).
- `rootdir` = project root (where `pyproject.toml` lives); `testpaths` =
  `["src/backend", "src/telegram_bot"]` are sub-paths, so root `conftest.py` is
  discovered before both trees (findings §6.2 Option A).
- `moderation_fixtures.py` already defers `from apps.moderation.models import
  ModerationCriteria` to inside fixture bodies (Defect B applied).

### ISO-4 code path under test (verified)

- `_pass_moderation` calls `TrustCalculator().calculate_and_save(ad.user)` (line 273)
  inside an **inner** `transaction.atomic()` savepoint, wrapped in `try/except Exception`
  that logs a warning (lines 271-279).
- The **outer** `auto_moderate()` wraps `_pass_moderation(ad)` in its own
  `try/except Exception` (lines 165-172). If the TrustCalculator exception escaped
  the inner guard, it would be caught here → `_fail_moderation` → ad set to
  `ON_MODERATION_FAILED`, `auto_moderate` returns `False`.
- **Invariant:** a TrustCalculator failure must NOT propagate past the inner guard →
  ad stays `PUBLISHED`, `auto_moderate()` returns `True`.
- `TrustCalculator` is imported at module level in `auto_moderation.py`
  (`from apps.trust.services.trust_calculator import TrustCalculator`, line 24),
  so it can be patched via `apps.moderation.services.auto_moderation.TrustCalculator`.

### Test context (verified)

- `test_auto_moderation.py` is **self-contained** — defines its own `moderation_criteria`
  fixture (DB-backed singleton, lines 32-48), does NOT use the `permissive_criteria`
  plugin fixture. 29 tests pass independently (findings §2.2).
- `pytestmark = [pytest.mark.django_db, pytest.mark.integration]` at module level.
- `TestAutoModerateFunction._setup` (autouse) provides `moderation_criteria`, `user`,
  `category`, `city`.
- `_create_valid_ad(self.user, self.category, self.city)` creates a passing ad with
  2 images.
- Already imports `from unittest.mock import patch` (line 10).
- `create_test_ad` imported via `from conftest import create_test_ad` (pythonpath import).

---

## Dependencies & Execution Order

```
task_correct_plugin_registration ──► task_add_strict_config ──┐
                                                                  ├─► task_commit_scoping
task_iso4_invariant_test ──────────────────────────────────────────┘
```

- **`task_add_strict_config` BLOCKED on `task_correct_plugin_registration`** — `strict_config = true`
  turns "Unknown config option" into a **hard error** (exit code 2). Must confirm no
  unknown ini warnings remain after the `pytest_plugins` removal before enabling it.
- **`task_iso4_invariant_test` is INDEPENDENT** — uses local `moderation_criteria`
  fixture, not the `permissive_criteria` plugin fixture. Can be developed and run
  in isolation.
- **`task_commit_scoping` BLOCKED on all three** — commits only after verification signs off.

---

## Execution Blocks

### Block A — task_correct_plugin_registration

**IMPORTANT CORRECTION:** The root `conftest.py` registered via `pytest_plugins`
(Auditor-discovered) causes a **module shadowing conflict**: 55 test files across
both trees import `from conftest import create_test_ad`, which now resolves to the
root `/app/conftest.py` instead of `src/backend/conftest.py`, producing
`ImportError: cannot import name 'create_test_ad' from 'conftest'`. The plan's
recommended "Option A" is **not viable** for this codebase.

**Corrected approach — Option B from findings §6.2:** Remove the root `conftest.py`
and register the plugin via `-p testing.moderation_fixtures` in `addopts`. This
works because Defect B (lazy imports) is already applied — the module is
import-safe at the early `-p` loading phase (before `django.setup()`).

<details>
<summary>Task spec (YAML)</summary>

```yaml
id: task_correct_plugin_registration

title: FIX — correct plugin registration from root conftest to -p in addopts

type: implementation

priority: high

depends_on: []

description: >
  Removes the root conftest.py that causes `from conftest import create_test_ad`
  to resolve to the wrong module (55 affected test files). Instead, registers
  the moderation_fixtures plugin via `-p testing.moderation_fixtures` in addopts,
  leveraging the already-applied lazy-import fix (Defect B) that makes the module
  import-safe at pytest's early plugin-loading phase.

files:
  - path: conftest.py                     # DELETE (root, untracked — causes shadowing)
  - path: pyproject.toml
    targets:
      - type: toml_table
        name: tool.pytest.ini_options
    changes:
      - action: replace_value
        description: "Add `-p testing.moderation_fixtures` to addopts array"
        new_value: '["--import-mode=importlib", "-ra", "-q", "-p", "testing.moderation_fixtures"]'

acceptance_criteria:
  - 18 previously-broken tests pass (permissive_criteria/banning_criteria resolved)
  - no "Unknown config option" warning
  - `from conftest import create_test_ad` resolves to src/backend/conftest.py (55 files)
  - ruff check passes on moderation_fixtures.py
  - basedpyright passes on moderation_fixtures.py

verification_steps:
  - "docker ps --filter name=mko-bazuna-test-db-  # must be running"
  - "Run the 3 affected files: test_edit.py, test_ad_lifecycle.py, test_ad_create.py"
  - "Run test_auto_moderation.py (29 self-contained tests) to confirm no regression"
```

</details>

**Run commands:**

```powershell
# 0. Alias (if not already set)
$dc='docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml'

# 1. Ensure test DB is running
$dc up -d db

# 2. Targeted: the 18 affected tests across 3 files
$dc run --rm --env-file .env.test -e PYTEST_OPTS="-v --reuse-db src/backend/apps/ads/tests/test_edit.py src/telegram_bot/tests/test_ad_lifecycle.py src/telegram_bot/tests/test_ad_create.py" test

# 3. Self-contained module regression
$dc run --rm --env-file .env.test -e PYTEST_OPTS="-v --reuse-db src/backend/apps/moderation/tests/test_auto_moderation.py" test

# 4. Full fast-gate regression (seed excluded)
$dc run --rm --env-file .env.test --env PYTEST_SKIP_MARKERS=seed test
```

**Notes:**
- `PYTEST_OPTS` *replaces* the default entrypoint flags. Include `-n auto` for parallelism in the full fast gate.
- `addopts` in pyproject.toml now includes `-p testing.moderation_fixtures`, so PYTEST_OPTS does not need to restate it.
- `pythonpath = ["src", "src/backend"]` makes the `testing` package importable, so `-p testing.moderation_fixtures` resolves correctly.
---

### Block B — task_add_strict_config

Add `strict_config = true` to `pyproject.toml` `[tool.pytest.ini_options]`. This converts
the "Unknown config option" warning (which silently swallowed the original Defect A)
into a hard startup error, preventing recurrence.

<details>
<summary>Task spec (YAML)</summary>

```yaml
id: task_add_strict_config

title: IMPLEMENT — add strict_config = true to pyproject.toml

type: implementation

priority: medium

depends_on:
  - task_correct_plugin_registration   # BLOCKED — must confirm no unknown ini warnings

description: >
  Adds strict_config = true to [tool.pytest.ini_options] in pyproject.toml.
  This turns "Unknown config option" warnings into errors (exit code 2),
  ensuring future ini-level misconfigurations (like the pytest_plugins
  mistake that caused this defect) fail CI immediately instead of being
  silently ignored. Available since pytest 8.0; project pins minversion 8.4
  and pytest>=9.1.1, so it is supported.

files:
  - path: pyproject.toml
    targets:
      - type: toml_table
        name: tool.pytest.ini_options
    changes:
      - action: add_key
        description: >
          Add `strict_config = true` as the first key inside
          [tool.pytest.ini_options], immediately after the table header,
          before `minversion`.

acceptance_criteria:
  - strict_config = true present in [tool.pytest.ini_options]
  - pytest collects without "Unknown config option" error (exit code 0)
  - fast gate still passes (no behavioral change to test execution)
```

</details>

**Edit target (semantic):**

```toml
# pyproject.toml — [tool.pytest.ini_options] section (around line 156)
# INSERT as first key after the table header:
strict_config = true
minversion = "8.4"
```

**Verification command:**

```powershell
# Confirm pytest starts cleanly with strict_config enabled
$dc run --rm -e PYTEST_OPTS="--collect-only -q 2>&1 | tail -5" test
# Expect: no "Unknown config option" error, exit code 0
```

---

### Block C — task_iso4_invariant_test

Add a dedicated test that forces `TrustCalculator.calculate_and_save` to raise and
asserts the ad stays `PUBLISHED` (the core ISO-4 invariant). This test lives in
`test_auto_moderation.py` and uses the self-contained `moderation_criteria` fixture —
**it does not depend on the `permissive_criteria` plugin fixture**, so it verifies
ISO-4 independently of the plugin-registration fix.

<details>
<summary>Task spec (YAML)</summary>

```yaml
id: task_iso4_invariant_test

title: IMPLEMENT — add ISO-4 invariant test (TrustCalculator failure → ad stays PUBLISHED)

type: implementation

priority: high

depends_on: []

description: >
  Adds a test to the TestAutoModerateFunction class in test_auto_moderation.py
  that patches TrustCalculator (imported at module level in auto_moderation.py)
  so calculate_and_save raises, then calls auto_moderate(ad) and asserts:
    (a) auto_moderate returns True (inner try/except swallowed the exception)
    (b) ad.status remains AdStatus.PUBLISHED
    (c) ad.published_at is not None
  This verifies the savepoint isolation: a TrustCalculator failure inside the
  inner transaction.atomic() must not roll back the PUBLISHED transition in the
  outer savepoint. The test uses the local moderation_criteria fixture (DB-backed
  singleton) and does not depend on permissive_criteria/banning_criteria plugin
  fixtures.

files:
  - path: src/backend/apps/moderation/tests/test_auto_moderation.py
    targets:
      - type: class
        name: TestAutoModerateFunction
    semantic_anchors:
      insert_after:
        type: method
        name: test_auto_moderate_pass_sets_published_and_analytics
    changes:
      - action: add_method
        description: >
          Insert new test method `test_pass_moderation_survives_trust_calculator_failure`
          after `test_auto_moderate_pass_sets_published_and_analytics`. Uses
          `unittest.mock.patch` to patch
          `apps.moderation.services.auto_moderation.TrustCalculator` with a
          MagicMock whose `return_value.calculate_and_save.side_effect` raises
          a RuntimeError. Calls `auto_moderate(ad)`, then asserts result is True,
          ad.refresh_from_db().status == AdStatus.PUBLISHED, published_at is not None.

acceptance_criteria:
  - new test passes (ad stays PUBLISHED despite TrustCalculator raising)
  - test uses only local moderation_criteria fixture (no permissive_criteria dependency)
  - ruff check passes on the modified test file
  - basedpyright passes on the modified test file
```

</details>

**Implementation details:**

- **Patch target:** `apps.moderation.services.auto_moderation.TrustCalculator` — this is the
  module-level import alias (line 24 of `auto_moderation.py`). Patching it replaces the
  class reference that `_pass_moderation` instantiates on line 273.
- **Existing import:** `patch` is already imported in the test module (`from unittest.mock import patch`, line 10).
- **Fixture context:** The test goes inside `TestAutoModerateFunction` which has the
  `_setup` autouse fixture providing `moderation_criteria` (local), `user`, `category`,
  `city`. The `moderation_criteria` fixture creates a real DB singleton with
  `banned_words = []`, `min_images = 1`, etc., so `_create_valid_ad` produces a passing ad
  that reaches `_pass_moderation`.
- **Insertion point:** semantically "after `test_auto_moderate_pass_sets_published_and_analytics`
  method in class `TestAutoModerateFunction`." This method ends at its `assert` on
  `AnalyticsEventType.MODERATION_APPROVED`.

**Verification command:**

```powershell
# Run ONLY the new test (fast, isolated)
$dc run --rm -e PYTEST_OPTS="-k test_pass_moderation_survives_trust_calculator_failure -v --no-header" test
```

---

### Block D — task_commit_scoping

Scope commits to **only** plan-relevant files. The working tree contains 18+
unrelated uncommitted changes (templates, middleware, i18n tests). Each commit
must use explicit `git add <specific files>` — never `git add .` / `git add -A`.

<details>
<summary>Task spec (YAML)</summary>

```yaml
id: task_commit_scoping

title: COMMIT — scope commits to plan-relevant files only

type: commit

priority: high

depends_on:
  - task_correct_plugin_registration
  - task_add_strict_config
  - task_iso4_invariant_test

description: >
  Three logically-separate commits. Each uses explicit file paths in git add
  to avoid pulling in unrelated working-tree changes (18 template files, language
  middleware, i18n tests, etc.).
  Commit 1: Plugin registration fix (Defects A+B) — delete root conftest.py,
  add `-p` to addopts, keep lazy imports in moderation_fixtures.py.
  Commit 2: strict_config + ISO-4 invariant test.
  Commit 3: Research + plan documentation.

commits:
  - id: commit_plugin_fix
    message: "test(fix): register moderation fixtures via -p addopts, defer Django imports (ISO-4)"
    files:
      - pyproject.toml                    # pytest_plugins ini key removed; -p added to addopts
      - src/backend/testing/moderation_fixtures.py  # lazy ModerationCriteria import

  - id: commit_strict_config_and_test
    message: "test(iso): add strict_config + TrustCalculator-failure invariant test"
    files:
      - pyproject.toml                    # strict_config = true added
      - src/backend/apps/moderation/tests/test_auto_moderation.py  # new test method

  - id: commit_docs
    message: "docs: add pytest-9 plugin registration findings + execution plan"
    files:
      - .ai/research/24-pytest9-plugin-registration-findings.md
      - .ai/plans/26-pytest9-plugin-registration-fix.md

acceptance_criteria:
  - each commit touches only the files listed above
  - git diff --name-only c789933 HEAD shows no unrelated files
  - ISO-4 code change (c789933) is NOT re-committed (already in history)
```

</details>

**Commit order and rationale:**

| # | Commit | Files | Rationale |
|---|---|---|---|
| 1 | `test(fix): register moderation fixtures via -p addopts, defer Django imports (ISO-4)` | `pyproject.toml` (pytest_plugins removal + `-p` addopts), `moderation_fixtures.py` (lazy imports). **Delete** root `conftest.py`. | Atomic fix for Defects A+B. Restores 18 broken tests. |
| 2 | `test(iso): add strict_config + TrustCalculator-failure invariant test` | `pyproject.toml` (strict_config), `test_auto_moderation.py` (new test) | Defense-in-depth + ISO-4 verification. Both are test-infra hardening. |
| 3 | `docs: add pytest-9 plugin registration findings + execution plan` | `.ai/research/24-*.md`, `.ai/plans/26-*.md` | Research + plan artifacts. Docs-only, no code. |

**Critical scoping commands:**

```powershell
# Pre-step: delete the broken root conftest.py (untracked, causes shadowing)
Remove-Item conftest.py

# Commit 1 — explicit file list, no -A
git add pyproject.toml src/backend/testing/moderation_fixtures.py
git commit -m "test(fix): register moderation fixtures via -p addopts, defer Django imports (ISO-4)"

# Commit 2 — pyproject.toml already committed in step 1; only strict_config diff + test file
git add pyproject.toml src/backend/apps/moderation/tests/test_auto_moderation.py
git commit -m "test(iso): add strict_config + TrustCalculator-failure invariant test"

# Commit 3 — docs only
git add .ai/research/24-pytest9-plugin-registration-findings.md .ai/plans/26-pytest9-plugin-registration-fix.md
git commit -m "docs: add pytest-9 plugin registration findings + execution plan"

# Safety check — ensure no unrelated files leaked in
git diff --name-only c789933 HEAD
```

> **Note on `pyproject.toml` appearing in two commits:** Commit 1 stages the
> `pytest_plugins` removal + addopts `-p` addition; Commit 2 stages the `strict_config`
> line. Because Commit 1 lands first, `git add pyproject.toml` in Commit 2 stages only the
> *new* diff (the `strict_config` line). This is the correct Git behavior.

---

## Required Agents

| Agent | Triggered by | Role |
|---|---|---|
| **Implementor** | Block A, Block B, Block C, Block D | Deletes root conftest.py; edits `pyproject.toml` (addopts `-p` + strict_config); writes ISO-4 test in `test_auto_moderation.py`; stages and commits with explicit file paths; runs tests for local validation. |
| **Auditor** | Not required | Root cause and fix already validated in `.ai/research/24-*.md` and by Block A verification. |
| **Researcher** | Not required | No further discovery needed; plugin mechanisms verified against pytest 9.1.1 source + docs. |
| **Validator** | Post-implementation | Final review of plan completeness, commit scoping, and no regressions. |
| **Doc-specialist** | Post-implementation | Update `.ai/research/24-pytest9-plugin-registration-findings.md` section references if needed. |

---

## Risk Assessment

| Block | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| A (Correct) | Root `conftest.py` shadowing breaks 55 test files importing `from conftest import create_test_ad` | Discovered | High | Switch to `-p testing.moderation_fixtures` in addopts; delete root conftest.py. The `-p` mechanism loads the plugin at early phase but the module has lazy imports (Defect B fix), making it import-safe. |
| A (Correct) | `-p testing.moderation_fixtures` not resolvable from addopts | Low | High | `pythonpath = ["src", "src/backend"]` makes `testing` package importable; `testing/__init__.py` exists. |
| B (strict_config) | Other unknown ini options exist → exit code 2 | Low (only `pytest_plugins` was unknown, now removed) | Medium | Block B depends on Block A; run `--collect-only` before and after to confirm no warnings. |
| C (ISO-4 test) | Test does not actually exercise the isolation (mock target wrong) | Low | Medium | Patch target verified: `TrustCalculator` imported at module-level in `auto_moderation.py` line 24; patching `apps.moderation.services.auto_moderation.TrustCalculator` affects line 273 call site. |
| C (ISO-4 test) | Test depends on `permissive_criteria` and fails without plugin fix | Low | Low | Test placed in `TestAutoModerateFunction` which uses local `moderation_criteria` fixture, not the plugin. Can run in isolation with `-k`. |
| D (Commit) | Unrelated uncommitted changes included in commit | Medium (18+ unrelated files in WT) | Low | Explicit `git add <files>` only; `git diff --name-only c789933 HEAD` post-commit check. |
| D (Commit) | ISO-4 code change (c789933) accidentally re-committed | Low | Low | `git status` shows `auto_moderation.py` clean (already committed); exclude from future `git add` calls. |

**Overall implementation risk: LOW.** All code changes are either already applied (Defects A+B)
or are a single config line + one isolated mock-based test. The dominant risk is
process safety (commit scoping), mitigated by explicit file-level staging and
post-commit verification.

---

## Rollout Safety Notes

1. **ISO-4 code is already committed** (c789933). This plan does NOT re-implement the
   savepoint isolation — it verifies it and adds test coverage.
2. **No production code changes** in this plan. `auto_moderation.py` is untouched.
   `pyproject.toml` changes are test-infra only (`strict_config`, `pytest_plugins` removal).
3. **The 18 broken tests** were functional before commit `87d83ce` — they used inline
   `permissive_criteria`/`banning_criteria` fixtures. The fix restores that behavior
   via a shared plugin (`-p testing.moderation_fixtures` in addopts + lazy imports),
   not by reverting.
4. **`strict_config` is backward-compatible** with all currently-known ini keys
   (`asyncio_mode`, `python_files`, `pythonpath`, `testpaths`, `addopts`,
   `console_output_style`, `markers`). None are unregistered.
5. **The ISO-4 invariant test** is self-contained: it can be run in isolation
   (`-k test_pass_moderation_survives_trust_calculator_failure`) without the plugin
   fix, because it uses `test_auto_moderation.py`'s local `moderation_criteria` fixture.

---

## Out of Scope

- Re-implementing the ISO-4 savepoint isolation (already committed at c789933).
- Any production source changes (`auto_moderation.py`, `trust_calculator.py`,
  `moderation_log.py`, etc.).
- Database migrations.
- Changes to `addopts` beyond adding `-p testing.moderation_fixtures` (necessary for plugin registration).
- Unrelated working-tree changes (18 template files, language middleware, i18n tests).
