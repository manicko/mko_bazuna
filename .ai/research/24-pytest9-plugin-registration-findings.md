# Research Findings — ISO-4 pytest-9 Plugin Registration Incompatibility

| Field | Value |
|---|---|
| **Researcher** | Analysis of ISO-4 agent session `ses_f5bbc9f5affeM6FqtUys0QCBvg` |
| **Date** | 2026-09-15 |
| **Status** | Complete |
| **Related session** | ISO-4: Isolate TrustCalculator from publish savepoint (`@implementor` subagent) |
| **Related plan** | `.ai/plans/23-test-isolation-flakiness.md` (Block D — ISO-4) |
| **Gate-0 findings** | `.ai/research/23-gate0-findings.md` |

---

## 1. Executive Summary

The ISO-4 implementor successfully applied the code change (inner savepoint +
`try/except` around `TrustCalculator().calculate_and_save()` in
`auto_moderation.py:271`), and lint + typecheck pass. However, **Verify step 4**
— running the specific flaky integration test
`test_edit_published_text_edit_passes_auto_moderation` — is **blocked by a
pre-existing test-infrastructure defect**: the shared moderation fixtures
(`permissive_criteria`, `banning_criteria`) are registered via an **invalid
ini-level `pytest_plugins`** key in `pyproject.toml`, which pytest 9.1.1
ignores, and the `-p` CLI workaround crashes with `AppRegistryNotReady` because
the plugin module performs top-level Django imports before `django.setup()`.

This defect was introduced by commit `87d83ce` ("test(iso): consolidate
permissive_criteria/banning_criteria into shared plugin") and affects **18 tests**
across two files in both the backend and bot test trees.

---

## 2. ISO-4 Change Status

### 2.1 The change (already applied, uncommitted)

**File:** `src/backend/apps/moderation/services/auto_moderation.py`

The change wraps `TrustCalculator().calculate_and_save(ad.user)` in an inner
`transaction.atomic()` savepoint with a `try/except Exception` guard:

```python
# _pass_moderation (auto_moderation.py:249-279, after ISO-4)
def _pass_moderation(ad: Ad) -> None:
    from apps.moderation.services.moderation_log import set_published

    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - ...
        set_published(ad)

        record_event(
            event_type=AnalyticsEventType.AD_PUBLISHED,
            user_id=ad.user_id,
            ad_id=ad.id,
        )

        record_event(
            event_type=AnalyticsEventType.MODERATION_APPROVED,
            user_id=ad.user_id,
            ad_id=ad.id,
        )

        try:
            with transaction.atomic():  # inner savepoint — isolates TrustCalculator
                TrustCalculator().calculate_and_save(ad.user)
        except Exception:
            logger.warning(
                "Trust score calculation failed for user %s; ad still PUBLISHED",
                ad.user_id,
                exc_info=True,
            )
```

```bash
$ git status --short src/backend/apps/moderation/services/auto_moderation.py
 M src/backend/apps/moderation/services/auto_moderation.py
```

The change is **uncommitted** in the working tree. The most recent commit on
this file is `acb406a` ("refactor(qlt-003): migrate auto_moderation.py events to
record_event") — the ISO-4 wrapper is not in git history.

### 2.2 Verification status

| Step | Status | Detail |
|---|---|---|
| `ruff check` | ✅ Pass | No issues |
| `basedpyright` | ✅ Pass | Inner `transaction.atomic()` has matching `# pyright: ignore` |
| `test_auto_moderation.py` (29 tests) | ✅ Pass | 29 passed in 11.67s — self-contained module uses its own local `moderation_criteria` fixture (not the broken plugin) |
| Flaky test via Docker | ❌ Blocked | `fixture 'permissive_criteria' not found` (plugin not loaded) |

---

## 3. The Problem: Two Independent Defects

### 3.1 Defect A — Invalid ini-level `pytest_plugins` registration

**Location:** `pyproject.toml:164`

```toml
[tool.pytest.ini_options]
...
pytest_plugins = ["testing.moderation_fixtures"]
```

**Problem:** `pytest_plugins` is **not a valid ini configuration option**.
Pytest's `_validate_config_options()` (in `_pytest/config/__init__.py`) compares
every key in `[tool.pytest.ini_options]` against its registered ini options and
emits `PytestConfigWarning: Unknown config option: pytest_plugins` for
unrecognized keys. The key is then silently ignored — the plugin module is
**never imported**, and any fixtures it defines are **never registered**.

**Root cause (verified from pytest source 4.6 through 9.1.1):**
`pytest_plugins` is only processed as a **module-level Python variable** in
`conftest.py` files, not as an ini-file setting. The pytest source confirms:

```python
# _pytest/config/__init__.py — consider_module (pytest 7.1 source):
def consider_module(self, mod):
    self._import_plugin_specs(getattr(mod, "pytest_plugins", []))
```

Pytest reads `pytest_plugins` via `getattr(mod, "pytest_plugins", [])` from
loaded modules — **never** from the ini configuration dict. There is no
`parser.addini("pytest_plugins", ...)` registration anywhere in pytest's
source. The official documentation confirms the supported mechanisms:

> "You can require plugins in a test module or a conftest file using
> pytest_plugins: `pytest_plugins = ("myapp.testsupport.myplugin",)`"
> (Source: docs.pytest.org — [How to install and use plugins](https://docs.pytest.org/en/stable/how-to/plugins.html))

Supported plugin registration mechanisms (verified from pytest 9.1 docs):

| Mechanism | Example | Timing | Django-safe? |
|---|---|---|---|
| `conftest.py`-level variable | `pytest_plugins = "mod"` in root `conftest.py` | **After** `pytest_load_initial_conftests` | ✅ Yes (Django already set up) |
| `-p` CLI flag | `pytest -p testing.moderation_fixtures` | **Before** `pytest_load_initial_conftests` | ⚠️ Only if module has no top-level Django imports |
| `PYTEST_PLUGINS` env var | `PYTEST_PLUGINS=testing.moderation_fixtures pytest` | **Before** `pytest_load_initial_conftests` | ⚠️ Only if module has no top-level Django imports |
| `pytest11` entry point | `[project.entry-points.pytest11]` in pyproject.toml | **Before** `pytest_load_initial_conftests` | ⚠️ Only if module has no top-level Django imports |
| **ini-level `pytest_plugins`** | `pytest_plugins = [...]` in `[tool.pytest.ini_options]` | **Never** (not recognized) | ❌ No — silently ignored |

> **Note:** This is **not** specifically a pytest-9 regression. The
> `_validate_config_options` / `_get_unknown_ini_keys` mechanism that emits
> "Unknown config option" has existed since at least pytest 4.6. Commit
> `87d83ce` (Sep 15, 2026) was authored against `pytest>=9.1.1` (pinned at
> `pyproject.toml:204`) and introduced the invalid ini-level registration. The
> characterisation in the ISO-4 session as a "pytest-9 incompatibility" is
> approximately correct: it manifests under pytest 9.1.1, but the root cause is
> a configuration error, not a version-specific regression.

### 3.2 Defect B — Top-level Django import in plugin module (import-timing hazard)

**Location:** `src/backend/testing/moderation_fixtures.py:12`

```python
from apps.moderation.models import ModerationCriteria  # top-level import
```

**Problem:** When the plugin is loaded via `-p` (command-line) or
`PYTEST_PLUGINS` (environment variable), pytest imports the module during the
**early plugin loading phase** — specifically inside
`PytestPluginManager.consider_pluginarg()` / `consider_env()`, which runs
**before** the `pytest_load_initial_conftests` hooks fire.

pytest-django registers its `pytest_load_initial_conftests` hook with
`tryfirst=True`, and it is inside that hook that `django.setup()` is called:

> "pytest-django calls `django.setup()` automatically. If you want to do
> anything before this, you have to create a pytest plugin and use the
> `pytest_load_initial_conftests()` hook, with `tryfirst=True`."
> (Source: pytest-django docs — [Configuring Django settings](https://pytest-django.readthedocs.io/en/latest/configuring_django.html))

> "Support for [.pytest 2.4] `pytest_load_initial_conftests` [...] makes it
> possible to import Django models in project `conftest.py` files, since
> pytest-django will be initialized before the conftest.py is loaded."
> (Source: pytest-django changelog — v2.4.0)

**Plugin loading sequence (pytest-django 4.12 + pytest 9.1.1):**

```
1. Built-in plugins registered
2. Entry-point plugins loaded (pytest11) — includes pytest-django
3. PYTEST_PLUGINS env-var plugins loaded     ← -p plugins loaded HERE
4. -p CLI plugins loaded                      ← testing.moderation_fixtures imported HERE
   │                                          (top-level `from apps.moderation.models import ...` → AppRegistryNotReady)
5. pytest_load_initial_conftests (tryfirst)   ← pytest-django calls django.setup() HERE
6. Initial conftest.py loaded                 ← root conftest.py with pytest_plugins would import the module HERE (safe)
7. Additional conftest.py files collected
8. pytest_configure hooks
9. Test collection
```

At step 4, `django.setup()` has not yet run (step 5). Any module that imports
Django models at top level will raise `django.core.exceptions.AppRegistryNotReady`.

---

## 4. How ISO-4 Was Verified Despite the Fixture Problem

The ISO-4 implementor correctly identified that `test_auto_moderation.py` is
**self-contained** — it defines its own local `moderation_criteria` fixture
(line 32-48) that creates a real `ModerationCriteria` singleton in the DB, and
does **not** depend on the broken `permissive_criteria` plugin fixture. The key
pass-path test is:

```python
# test_auto_moderation.py:455
def test_auto_moderate_pass_sets_published_and_analytics(self):
    ad = _create_valid_ad(self.user, self.category, self.city)
    result = auto_moderate(ad)          # → _pass_moderation() → TrustCalculator().calculate_and_save()
    assert result is True
    ad.refresh_from_db()
    assert ad.status == AdStatus.PUBLISHED
    assert ad.published_at is not None
```

This test exercises the ISO-4 modified code path and confirms the inner-savepoint
wrapper preserves the publish success path (PUBLISHED commits through the outer
savepoint) with no regression in the fail / MaxAds paths.

**Result:** `29 passed` for the entire `test_auto_moderation.py` module.

However, the **isolation-path** (TrustCalculator raises → ad stays PUBLISHED)
has **no dedicated test**. The ISO-4 change's primary purpose — isolating
trust-score failures from the publish savepoint — is not directly verified by the
existing test suite.

---

## 5. Affected Tests

Commit `87d83ce` removed the inline `permissive_criteria`/`banning_criteria`
fixtures from 3 test files and moved them to `testing/moderation_fixtures.py`,
registered via the broken ini-level `pytest_plugins`. **18 tests** across **2
files** now have unresolved fixture references:

### Backend tree (`src/backend/apps/ads/tests/test_edit.py`)

| Line | Test | Fixture |
|---|---|---|
| 135 | `test_edit_reactivation_passes_auto_moderate` | `permissive_criteria` |
| 212 | `test_edit_reactivation_currency_keep_current` | `permissive_criteria` |
| 251 | `test_edit_reactivation_price_normalized_recomputed` | `permissive_criteria` |
| 293 | `test_edit_reactivation_text_updated` | `permissive_criteria` |
| **502** | **`test_edit_published_text_edit_passes_auto_moderation`** | **`permissive_criteria`** |

### Bot tree (`src/telegram_bot/tests/test_ad_create.py`)

| Line | Test | Fixture |
|---|---|---|
| 99 | `test_original_language_detected_from_user` | `permissive_criteria` |
| 133 | `test_original_language_falls_back_to_bosnian` | `permissive_criteria` |

### Bot tree (`src/telegram_bot/tests/test_ad_lifecycle.py`)

| Line | Test | Fixture |
|---|---|---|
| 77 | `test_auto_moderate_publishes_valid_ad` | `permissive_criteria` |
| 95 | `test_auto_moderate_sets_published_at` | `permissive_criteria` |
| 108 | `test_auto_moderate_sets_original_published_at_first_publish` | `permissive_criteria` |
| 127 | `test_auto_moderate_fails_banned_word` | `banning_criteria` |
| 141 | `test_auto_moderate_fail_sets_moderation_failed_at` | `banning_criteria` |
| 154 | `test_auto_moderate_fail_does_not_set_publish_timestamps` | `banning_criteria` |
| 172 | `test_original_published_at_immutable_on_re_publish` | `permissive_criteria` |
| 199 | `test_original_published_at_immutable_on_second_moderation_cycle` | `permissive_criteria` |
| 231 | `test_published_at_updates_on_re_publish` | `permissive_criteria` |
| 293 | `test_auto_moderate_with_images_passes` | `permissive_criteria` |
| 309 | `test_auto_moderate_creates_analytics_event` | `permissive_criteria` |
| 326 | `test_auto_moderate_fail_creates_moderation_log` | `banning_criteria` |

> **CI impact:** All 18 tests are marked `integration` (and most `slow`). The
> CI pipeline (`.github/workflows/ci.yml:111`) runs
> `uv run pytest -m "not seed"`, which **includes** `slow` and `integration`
> tests. These 18 tests will produce `fixture 'permissive_criteria' not found`
> (or `banning_criteria`) errors in CI as well.

---

## 6. Modern Best Practices & Recommended Solutions

### 6.1 Core principle: Defer Django imports in pytest plugin modules

**Never import Django models at module top-level in a pytest plugin that may
be loaded via `-p` or `PYTEST_PLUGINS`.** These mechanisms load plugins
**before** pytest-django calls `django.setup()`. The standard fix is to move
Django imports inside fixture functions or hook implementations:

```python
# ✅ CORRECT — lazy import inside fixture
import pytest

@pytest.fixture
def permissive_criteria(monkeypatch):
    from apps.moderation.models import ModerationCriteria  # deferred
    _mock_criteria = MagicMock(spec=ModerationCriteria)
    ...
```

This makes the module import-safe at any point in pytest's startup sequence.

### 6.2 Correct plugin registration mechanisms (in priority order)

#### Option A — Root `conftest.py` with module-level `pytest_plugins` (RECOMMENDED)

Create a root-level `conftest.py` at the project root:

```python
# conftest.py (project root — discovered by both src/backend and src/telegram_bot)
pytest_plugins = ("testing.moderation_fixtures",)
```

**Why this works:** Conftest.py files are loaded at step 6 in the loading
sequence (after `pytest_load_initial_conftests` at step 5, where pytest-django
runs `django.setup()`). Top-level Django imports in the plugin module are safe.

**Cross-tree coverage:** The rootdir is the project root (where `pyproject.toml`
lives). Both `testpaths` (`src/backend`, `src/telegram_bot`) are sub-paths, so
the root conftest.py is discovered before both trees.

**Caveat (MODULE SHADOWING):** A root-level `conftest.py` creates a Python module
named `conftest` in `sys.modules`. Any test file that does
`from conftest import create_test_ad` (55 files in this codebase) will resolve
to the root conftest, not `src/backend/conftest.py`, producing
`ImportError: cannot import name 'create_test_ad'`.

**Shadowing-safe implementation:** Instead of a root conftest, add
`pytest_plugins = ("testing.moderation_fixtures",)` to the **existing** conftest
files that are already discovered by each test tree:
- `src/backend/conftest.py` (discovered by all `src/backend` tests)
- `src/telegram_bot/tests/conftest.py` (discovered by all bot tests)

This avoids creating a new `conftest` module in `sys.modules` while still using
the correct `pytest_plugins` registration mechanism (module-level variable in
a conftest file, processed at step 6 — after `django.setup()`).

#### Option B — `-p` in `addopts` + lazy imports (ALTERNATIVE)

> **NOTE (post-commit verification):** Option B was implemented in commit `2d9e599`
> (added `-p testing.moderation_fixtures` to `addopts` + lazy imports in
> `moderation_fixtures.py`). However, the post-fix fast gate run
> (1459 passed, 2 failed, 37 errors) shows this approach **does not work** under
> the project's xdist configuration (`-n auto --dist loadgroup`).
>
> **Root cause of failure:** While the lazy imports correctly prevent `AppRegistryNotReady`
> at the early plugin-loading phase, and `PYTHONPATH=/app/src:/app/src/backend` in the
> Docker image makes the `testing` package importable, the `-p` plugin loading mechanism
> does not reliably propagate fixture definitions to xdist worker processes under
> `--dist loadgroup`. The plugin module imports successfully in the controller process,
> but fixtures from controller-loaded `-p` plugins may not be broadcast to workers,
> resulting in "fixture not found" errors during test collection.
>
> **Updated recommendation:** Use **Option A** (conftest-level `pytest_plugins`) instead.
> See §6.2 Option A (revised) below for the shadowing-safe implementation.

```toml
# pyproject.toml [tool.pytest.ini_options]
addopts = ["--import-mode=importlib", "-ra", "-q", "-p", "testing.moderation_fixtures"]
```

Combined with deferred Django imports in the plugin module, this works because
the module is import-safe at the early plugin-loading phase.

**Trade-off:** Less idiomatic than conftest.py-level `pytest_plugins`; mixes
plugin registration with runtime flags in `addopts`.

#### Option C — `PYTEST_PLUGINS` env var (CI/container-only)

Set `PYTEST_PLUGINS=testing.moderation_fixtures` in the Docker compose env and
CI env. Requires lazy imports in the plugin module. Less discoverable than
in-repo configuration.

### 6.3 pytest 9+ configuration modernization (future-proofing)

| Topic | Recommendation | Rationale |
|---|---|---|
| `strict_config = true` | Add to `[tool.pytest.ini_options]` | Turns "Unknown config option" into an **error** (exit code 2), catching misconfigurations like this one at pytest startup instead of silently ignoring them. Available since pytest 8.0. |
| `[tool.pytest]` vs `[tool.pytest.ini_options]` | Consider migrating to native `[tool.pytest]` table (pytest 9.0+) | pytest 9.0 introduces native TOML config (`[tool.pytest]`) with rich types. `ini_options` is maintained as a bridge for backward compat. |
| `pytest_plugins` as ini option | **Remove** | Never valid. Replace with conftest.py variable or `-p`. |

### 6.4 Recommended fix (minimal, targeted)

**Step 1** — Remove the invalid ini-level registration:
```toml
# pyproject.toml — REMOVE this line:
pytest_plugins = ["testing.moderation_fixtures"]
```

**Step 2** — Make `moderation_fixtures.py` import-safe (defer Django import):
```python
# src/backend/testing/moderation_fixtures.py
from unittest.mock import MagicMock  # keep
import pytest  # keep
# REMOVE: from apps.moderation.models import ModerationCriteria

@pytest.fixture
def permissive_criteria(monkeypatch):
    from apps.moderation.models import ModerationCriteria  # deferred import
    ...
```

**Step 3** — Register via conftest-level `pytest_plugins` (shadowing-safe):
```python
# src/backend/conftest.py — add at module level:
pytest_plugins = ("testing.moderation_fixtures",)

# src/telegram_bot/tests/conftest.py — add at module level:
pytest_plugins = ("testing.moderation_fixtures",)
```

**Why not a root `conftest.py`:** 55 test files use `from conftest import create_test_ad`,
which would resolve to the root conftest instead of `src/backend/conftest.py`, causing
`ImportError` (see §6.2 Option A caveat above).

This combination fixes both defects:
- Defect A resolved: `pytest_plugins` is in the correct location (conftest.py module-level, not ini)
- Defect B resolved: lazy imports make the module import-safe at any phase
- xdist-safe: conftest-level `pytest_plugins` is discovered per-worker, unlike `-p` which
  has propagation issues under `--dist loadgroup`
- Shadowing-safe: both conftest files already exist; no new `conftest` module is created

---

## 7. Verification of Root Cause (Evidence Chain)

1. **`pyproject.toml:164`**: `pytest_plugins = ["testing.moderation_fixtures"]` in `[tool.pytest.ini_options]`
   - `pytest_plugins` is NOT a registered ini option (no `addini("pytest_plugins")` in pytest source)
   - Verified from pytest 4.6, 7.1, and 9.1.1 source: `_validate_config_options()` flags it as unknown

2. **`uv run python -c "import pytest; print(pytest.__version__)"`**: outputs `9.1.1`
   - `pyproject.toml:204`: `pytest>=9.1.1` (pinned since before commit `87d83ce`)

3. **`moderation_fixtures.py:12`**: `from apps.moderation.models import ModerationCriteria`
   - Top-level Django model import — crashes with `AppRegistryNotReady` if module is imported before `django.setup()`

4. **`src/backend/conftest.py`**: No `pytest_plugins` variable (only fixtures)
5. **No root `conftest.py`** exists at the project root
6. **`testing/__init__.py`** exists — the `testing` package is importable from `src/backend` (via `pythonpath = ["src", "src/backend"]`)

7. **Commit `87d83ce`** removed inline `permissive_criteria`/`banning_criteria` definitions from:
   - `src/backend/apps/ads/tests/test_edit.py` (5 usages)
   - `src/telegram_bot/tests/test_ad_create.py` (2 usages)
   - `src/telegram_bot/tests/test_ad_lifecycle.py` (11 usages)

8. **`test_auto_moderation.py`** defines its own local `moderation_criteria` fixture (line 32-48) using the real DB path (`ModerationCriteria.get_singleton()`), confirming it does NOT depend on the broken plugin — which is why it passes.

---

## 8. Summary of Facts vs. Inferences

| Statement | Type | Confidence | Evidence |
|---|---|---|---|
| `pytest_plugins` in `[tool.pytest.ini_options]` is not a valid ini option | **Fact** | HIGH | pytest source: no `addini("pytest_plugins")`; `_validate_config_options` flags unknowns |
| pytest 9.1.1 emits "Unknown config option: pytest_plugins" warning | **Fact** | HIGH | `_validate_config_options()` in `_pytest/config/__init__.py` |
| The `permissive_criteria` fixture is never registered → "fixture not found" | **Fact** | HIGH | Plugin module never imported; fixture not in conftest scope |
| `-p testing.moderation_fixtures` crashes with `AppRegistryNotReady` | **Fact** (as reported by ISO-4 agent) | HIGH | Plugin loaded at step 4, `django.setup()` at step 5 |
| `moderation_fixtures.py:12` has top-level Django import | **Fact** | HIGH | Source code read |
| 18 tests across 2 files depend on the broken fixtures | **Fact** | HIGH | grep across `src/` |
| This is a "pytest-9 regression" | **Inference (refuted)** | LOW | `pytest_plugins` as ini option has been invalid in all pytest versions; defect introduced by commit `87d83ce`, not by pytest 9 |
| CI is currently broken for these 18 tests | **Inference** | MEDIUM | CI runs `-m "not seed"` which includes `slow`/`integration`; tests use `permissive_criteria` |
| Root conftest.py would fix plugin loading (after Django setup) | **Inference** | HIGH | pytest-django changelog v2.4.0: "import Django models in project conftest.py files, since pytest-django will be initialized before the conftest.py is loaded" |
| Lazy imports make `-p` loading safe | **Fact** | HIGH | pytest docs: `-p` loads "early during startup"; deferred import moves Django access to fixture runtime |

---

## 9. Action Items

1. **[Fix Defect A]** Remove `pytest_plugins = ["testing.moderation_fixtures"]` from
   `pyproject.toml:164` and add `pytest_plugins = ("testing.moderation_fixtures",)` as
   a module-level variable in **both** existing conftest files:
   - `src/backend/conftest.py` (backend tree)
   - `src/telegram_bot/tests/conftest.py` (bot tree)

   **Why not root `conftest.py`:** 55 test files import `from conftest import create_test_ad`,
   which would resolve to a root conftest instead of `src/backend/conftest.py`,
   causing `ImportError`.

   **Why not `-p` in addopts:** Post-fix verification (1459 passed, 2 failed, 37 errors)
   shows that `-p testing.moderation_fixtures` does not reliably propagate fixtures
   to xdist worker processes under `--dist loadgroup`. See
   `.ai/research/25-fast-gate-analysis.md` for the full analysis.

2. **[Fix Defect B]** Move the top-level `from apps.moderation.models import
   ModerationCriteria` in `moderation_fixtures.py:12` inside the fixture
   functions (lazy import pattern).

3. **[Defense-in-depth]** Add `strict_config = true` to
   `[tool.pytest.ini_options]` so future unknown ini options fail CI immediately
   instead of silently warning.

4. **[ISO-4 verification]** Add a dedicated test that forces
   `TrustCalculator.calculate_and_save` to raise and asserts the ad stays
   `PUBLISHED` (the core ISO-4 invariant). This test does not depend on the
   `permissive_criteria` fixture and can verify ISO-4 independently.

5. **[Commit ISO-4]** Commit the already-applied `auto_moderation.py` change
   separately from the fixture-registration fix.

---

## 10. References

- Post-fix analysis: `.ai/research/25-fast-gate-analysis.md` — why `-p` in addopts
  fails under xdist and the shadowing-safe conftest approach
- ISO-4 agent session transcript: `ses_f5bbc9f5affeM6FqtUys0QCBvg`
- Gate 0 findings: `.ai/research/23-gate0-findings.md`
- Plan: `.ai/plans/23-test-isolation-flakiness.md` (Block D — ISO-4, §613)
- Problem statement: `.ai/problems/Problem_02.md` (§1e, §5.4, §6.4)
- Audit findings: `.ai/audit/99-validation/03-db-concurrency-validated-findings.md` (line 81)
- Test-isolation audit: `.ai/audit/15-test-isolation/findings.md` (lines 106, 149, 150, 170, 173, 284, 294)
- `pyproject.toml:164` — ini-level `pytest_plugins` registration
- `pyproject.toml:204` — `pytest>=9.1.1` pin
- `src/backend/testing/moderation_fixtures.py:12` — top-level Django import
- `src/backend/apps/moderation/services/auto_moderation.py:271` — `TrustCalculator().calculate_and_save()` call site
- `src/backend/apps/moderation/services/auto_moderation.py:27` — `from apps.trust.services.trust_calculator import TrustCalculator` (module-level import at line 24)
- `src/backend/conftest.py` — root backend conftest (no `pytest_plugins`)
- `docs/99-agent/rules.md` — project conventions
- `.github/workflows/ci.yml:111` — CI runs `pytest -m "not seed"` (includes slow/integration)
- `docker/entrypoint-test.sh:46` — test entrypoint runs `uv run pytest ${PYTEST_OPTS:- ...}`
- pytest 9.1.1 changelog — https://docs.pytest.org/en/stable/changelog.html
- pytest source `_pytest/config/__init__.py` — `_validate_config_options`, `consider_module`
- pytest-django docs — [Configuring Django settings](https://pytest-django.readthedocs.io/en/latest/configuring_django.html)
- pytest-django changelog v2.4.0 — `pytest_load_initial_conftests` support
- pytest docs — [How to install and use plugins](https://docs.pytest.org/en/stable/how-to/plugins.html)
