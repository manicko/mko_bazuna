---
id: search-fts-fixes
domain: plan
status: 2 findings actionable (2 code) · 2 findings already implemented (4 doc-only, 1 dead-code) · 0 committed
source: .ai/audit/99-validation/08-search-fts-validated-findings.md
verification: .ai/audit/99-validation/08-search-fts-validated-findings-verification.md
tags:
  - search
  - fts
  - audit-fix
  - backfill
  - dead-code
  - doc-update
related:
  - .ai/audit/99-validation/08-search-fts-validated-findings.md
  - .ai/audit/99-validation/08-search-fts-validated-findings-verification.md
  - docs/01-spec/spec-index.md
  - docs/01-spec/technical-specification.md
  - docs/02-database/db-indexes.md
  - docs/02-database/db-schema.md
  - src/backend/apps/core/services/translation.py
  - src/backend/apps/core/utils/migrate_locked.py
  - src/backend/apps/core/management/commands/bootstrap_reference_data.py
  - src/backend/apps/ads/management/commands/setup_search_triggers.py
  - src/backend/apps/ads/management/commands/backfill_translations.py
  - src/backend/apps/search/models.py
  - src/backend/apps/users/views/consent.py
  - src/telegram_bot/tests/test_multi_lang_translation.py
  - docs/ops/migration-workflow.md
---

# Execution Plan 09 — Search & FTS Audit Findings Fix (SRH-001–SRH-007)

> **Source (validated):** `.ai/audit/99-validation/08-search-fts-validated-findings.md`
> **Verification report:** `.ai/audit/99-validation/08-search-fts-validated-findings-verification.md`
> **Validated on:** 2026-09-16 (findings re-verified against current codebase)
> **Status:** 6 findings actionable · 1 rejected (SRH-006)

---

## 0. Resolution Status & Scope

Seven findings were submitted for validation. **One is REJECTED** (SRH-006, already stale).

**Post-audit codebase verification (2026-09-16 — Tech Lead inspection):**

| Block | ID | Findings | Scope (semantic targets) | Status | Agent(s) | Risk |
|---|---|---|---|---|---|---|
| B0 | DOC-FIX | SRH-001, SRH-004, SRH-005, Ancillary §D | `consent.py` docstring · `search/models.py` `SavedSearch.query` help_text · `spec-index.md` §Key tables · `technical-specification.md` §D line 66 | ✅ ALREADY DONE | — | — |
| B1 | DEAD-CODE | SRH-002 | `translate_cached` function + decorator · `test_multi_lang_translation.py` fixture | ✅ ALREADY DONE | — | — |
| B2 | BACKFILL-WIRE | SRH-003 | `migrate_locked.py` `steps` tuple · `bootstrap_reference_data.py` docstring | OPEN | Implementor ✓, Validator ✓ | Medium (startup path) |
| B3 | FTS-BACKFILL | SRH-007 | `setup_search_triggers.py` `Command` class · `db-indexes.md` §Migration notes | OPEN | Implementor ✓, Validator ✓ | Low (opt-in flag) |
| B4 | SKIP | SRH-006 | No action — file already deleted, ruff passes on search dir | RESOLVED | — | N/A |

### Audit Verification Details

The audit findings were written based on a 2026-09-12 audit, but re-verification on 2026-09-16 revealed that **B0 and B1 have already been fully implemented in the codebase**:

- **SRH-001 (consent.py):** Module docstring (lines 8-14) already accurately states "Buyer search queries are NOT sent to any translation service" and references `technical-specification.md` §G. No stale claim exists.
- **SRH-004 (help_text):** `SavedSearch.query` help_text (search/models.py lines 76-79) already reads "FTS query string stored in the user's language; matched against the per-language search vector (no query-time translation)".
- **SRH-005 (spec-index.md):** Line 91 already lists all 4 GIN indexes (IX_ads_search_gin, _ru, _bs, _en).
- **Ancillary §D:** technical-specification.md line 66 already states "no query-time translation" with `Category.get_name(locale)` reference.
- **SRH-002 (translate_cached):** `grep -rn '\btranslate_cached\b' src/` returns **zero matches**. The function and its `@lru_cache(maxsize=128)` decorator are already removed. The test fixture at `test_multi_lang_translation.py:21,52` already imports and calls `translate_cached_generic.cache_clear()` (not `translate_cached`).

Only **B2** and **B3** remain to be implemented.

---

## 1. Block Summary Table

| Block | ID | Findings | Scope (semantic targets) | Status | Agent(s) | Risk |
|---|---|---|---|---|---|---|
| B0 | DOC-FIX | SRH-001, SRH-004, SRH-005, Ancillary §D | `consent.py` docstring · `search/models.py` `SavedSearch.query` help_text · `spec-index.md` §Key tables · `technical-specification.md` §D line 66 | OPEN | Implementor ✓, Validator ✓ (SRH-001) | Low |
| B1 | DEAD-CODE | SRH-002 | `translation.py` `translate_cached` function + decorator · `test_multi_lang_translation.py` `_reset_translation_state` fixture (import + `cache_clear`) | OPEN | Implementor ✓, Validator ✓ | Low (requires atomic commit) |
| B2 | BACKFILL-WIRE | SRH-003 | `migrate_locked.py` `steps` tuple · `bootstrap_reference_data.py` docstring | OPEN | Implementor ✓, Validator ✓ | Medium (startup path) |
| B3 | FTS-BACKFILL | SRH-007 | `setup_search_triggers.py` `Command` class (`add_arguments`, `handle`) · `db-indexes.md` §Migration notes | OPEN | Implementor ✓, Validator ✓ | Low (opt-in flag) |
| B4 | SKIP | SRH-006 | No action — file already deleted, ruff passes on search dir | RESOLVED | — | N/A |

---

## 2. Dependency DAG & Rollout Order

### 2.1 Inter-block dependency analysis

```
B0 (doc-only)     ──► no code dependencies, no shared files ──► independent
B1 (dead code)    ──► independent of B0/B2/B3 — translate_cached is not used by backfill_translations
                      (backfill_translations.py imports translate_cached_generic, NOT translate_cached)
B2 (backfill wire) ──► independent of B0/B1/B3 — modifies migrate_locked.py steps tuple
B3 (FTS backfill)  ──► independent of B0/B1/B2 — modifies setup_search_triggers.py Command class

Sequential constraint: only one Implementor at a time ⟹ B0 → B1 → B2 → B3
                        (not a dependency ordering — a resource constraint)
```

### 2.2 SRH-003 vs SRH-007 — should they be combined?

**Question posed:** *"SRH-003 and SRH-007 both modify `migrate_locked.py` — should they be
separate blocks or combined?"*

**Answer: Separate blocks.** The premise that both modify `migrate_locked.py` is incorrect
based on the validated findings:

| Aspect | SRH-003 (translation backfill) | SRH-007 (FTS-vector backfill) |
|---|---|---|
| **Primary file modified** | `migrate_locked.py` (`steps` tuple) | `setup_search_triggers.py` (`Command` class) |
| **Data type addressed** | `title_en`/`description_en`/`title_bs`/`description_bs` columns (translation) | `search_vector_ru`/`bs`/`en` columns (FTS vectors) |
| **Gating mechanism** | Env var `RUN_TRANSLATION_BACKFILL` in bootstrap | CLI flag `--backfill` on command (operator opt-in) |
| **Command invoked** | `manage.py backfill_translations` | `manage.py setup_search_triggers --backfill` |
| **Default behavior** | Env-gated: runs only when `RUN_TRANSLATION_BACKFILL=true` | Flag-gated: DDL-only by default, backfill only with `--backfill` |

**SRH-007 does NOT modify `migrate_locked.py`.** Its recommendation is to add a `--backfill`
CLI flag to `setup_search_triggers.py` itself — operators invoke it manually
(`python manage.py setup_search_triggers --backfill`), not through the bootstrap chain.
`migrate_locked.py` calls `("setup_search_triggers",)` without `--backfill`, so the default
DDL-only behavior is preserved.

**Conditional merge criterion:** If the Tech Lead's implementation for SRH-007 instead wires
the FTS backfill into `migrate_locked.py`'s `steps` tuple (env-gated, mirroring SRH-003's
approach), then both would edit the same `steps` tuple and MUST be combined into one block to
avoid conflicting edits. Based on the findings' recommendations, this is not the case —
SRH-007 is opt-in at the command level.

### 2.3 Rollout sequence

```
B0  (doc-only, 4 files)           ── ✅ ALREADY DONE (verified: all doc fixes present)
B1  (dead code removal, 2 files)   ── ✅ ALREADY DONE (verified: translate_cached fully gone)
B4  (SRH-006 — no action)          ── RESOLVED

B2  (backfill wiring, 2 files)     ── Implementor + Validator (Medium risk)
   ↓ (resource handoff — one Implementor)
B3  (FTS backfill flag, 2 files)   ── Implementor + Validator (Low risk)
```

**Rationale for ordering:**
1. B0 first — doc-only, zero operational risk, clears the P0 privacy disclosure (SRH-001).
2. B1 second — dead code removal with hidden test dependency; must be atomic. Clean removal
   before adding new code that references the translation service.
3. B2 third — modifies the critical startup path (`migrate_locked.py`); requires Validator
   review of the env-gating logic and integration test.
4. B3 last — adds an opt-in flag to a management command; lowest risk, independent of B2.

B0 and B1 touch no shared files; B1 and B2 touch no shared files; B2 and B3 touch no shared
files. The sequential ordering is purely a consequence of the "one Implementor at a time"
constraint — these blocks are logically independent.

---

## 3. Block Specifications

---

### Block B0 — DOC-FIX: Documentation convergence (translation→FTS architectural shift)

**Findings:** SRH-001 (P0), SRH-004 (P2), SRH-005 (P2), Ancillary §D

**Description:**

All four changes correct documentation that predates the architectural shift from
query-time translation to per-language FTS vectors. The code is correct in all cases —
only docstrings, help_text, and spec summaries are stale. Grouped because they share a
common root cause, all are doc-only with zero operational risk, and they touch four
independent files.

**Semantic targets:**

| Finding | File | Target | Current (stale) | Corrected |
|---|---|---|---|---|
| SRH-001 | `src/backend/apps/users/views/consent.py` | Module docstring (lines 8–13) | Claims "search queries (on lookup) are sent to Google Translate" | State that ad title/description are translated at publication time; buyer search queries are NOT sent to any external service; reference `technical-specification.md` §G |
| SRH-004 | `src/backend/apps/search/models.py` | `SavedSearch.query` field `help_text` (line 76) | `"FTS query string (translated to Russian if Bosnian input)"` | `"FTS query string stored in the user's language; matched against the per-language search vector (no query-time translation)"` |
| SRH-005 | `docs/01-spec/spec-index.md` | §Key tables summary (line 91) | `Search index: GinIndex IX_ads_search_gin` | `Search indexes: GinIndex on per-language search_vector_ru/bs/en (IX_ads_search_gin_ru/bs/en), plus legacy generic IX_ads_search_gin retained during transition` |
| Ancillary §D | `docs/01-spec/technical-specification.md` | §D bullet near line 66 | "Montenegrin query is translated to Russian before search, so it matches the Russian category name" | "The query is matched against the locale-appropriate category name via `Category.get_name(locale)` — no query-time translation" |

**Changes:**

```yaml
- action: edit
  file: src/backend/apps/users/views/consent.py
  target: module docstring (lines 8-13)
  description: >
    Replace the "Data flow disclosure — translation egress" paragraph to remove
    the false claim about search-query translation. Keep the accurate statement
    about ad title/description translation at publication time. Align with
    technical-specification.md §G (line 118-120) which already documents the
    correct behavior: "No search queries are sent to any translation service."

- action: edit
  file: src/backend/apps/search/models.py
  target: SavedSearch.query field help_text
  description: >
    Replace help_text="FTS query string (translated to Russian if Bosnian input)"
    with help_text="FTS query string stored in the user's language; matched
    against the per-language search vector (no query-time translation)".

- action: edit
  file: docs/01-spec/spec-index.md
  target: §Key tables "Search index" line (line 91)
  description: >
    Replace the single-index reference with all four GIN indexes, matching
    ads/models.py Meta.indexes (lines 258-274) and db-indexes.md (lines 48-59).

- action: edit
  file: docs/01-spec/technical-specification.md
  target: §D category-name search bullet (line 66)
  description: >
    Remove "Montenegrin query is translated to Russian before search" claim.
    Replace with: the query is matched directly against the locale-appropriate
    category name via Category.get_name(locale) — no translation step. Aligns
    with §G line 118 and search.py:350-353.
```

**Acceptance criteria:**
- `consent.py` docstring no longer mentions "search queries" being sent to Google Translate
- `SavedSearch.query` help_text no longer mentions "translated to Russian if Bosnian input"
- `spec-index.md` Key tables section lists all 4 GIN indexes (IX_ads_search_gin, _ru, _bs, _en)
- `technical-specification.md` §D no longer claims Montenegrin→Russian query translation
- No production code behavior changes (docstrings and help_text only)
- `test_i18n_completeness.py` passes (these are docstrings/help_text, not translatable template strings — no i18n impact)

**Required tests:** None — doc-only changes.

**Implementation sequence:**
1. Edit `consent.py` module docstring
2. Edit `SavedSearch.query` help_text in `search/models.py`
3. Edit `spec-index.md` line 91
4. Edit `technical-specification.md` §D line 66
5. Validator spot-check: confirm each edit matches the code's actual behavior (consent.py has no translation call; save_search.py stores verbatim; search.py matches per-language vectors; Category.get_name(locale) at search.py:350-353)

**Architectural constraints:**
- No DB migration required (help_text is not a DB column)
- No i18n impact (docstrings and help_text are not translatable via gettext)
- SRH-001 P0: the corrected docstring must still accurately describe the actual translation egress (ad title/description at publication time via `translate_cached_generic`, no PII included)

**Risks:**
- **Low:** Doc-only change. The only risk is inaccuracy in the replacement text — mitigated by Validator confirming alignment with code behavior.
- **SRH-001 compliance:** The corrected docstring must not understate egress either. Publication-time translation of ad title/description DOES go to Google Translate — this must be accurately stated.

**Agents:** Implementor (doc edits) → Validator (spot-check SRH-001 privacy accuracy; SRH-004/005/Ancillary are self-evident)

**Verification commands:**
- Manual: read each edited file to confirm accuracy
- `uv run ruff check src/backend/apps/users/views/consent.py src/backend/apps/search/models.py` (no code logic change; confirms no syntax issues)

---

### Block B1 — DEAD-CODE: Remove `translate_cached` with atomic test fix (SRH-002)

**Finding:** SRH-002 (P1, CRITICAL→BEST-PRACTICE)

**Description:**

Remove the dead `translate_cached(query: str) -> str` function (bs→ru-only wrapper around
`_translate_via_api`) from `apps.core.services.translation`, along with its `@lru_cache(maxsize=128)`
decorator. The function has **zero production callers** — the live translation path is
`translate_text()` → `translate_cached_generic()` (line 192-194).

**Critical constraint:** The test fixture `_reset_translation_state` in
`src/telegram_bot/tests/test_multi_lang_translation.py` imports `translate_cached` (line 21)
and calls `translate_cached.cache_clear()` (line 53). This is a **hidden dependency** not
disclosed in the original findings (the original cited the non-existent `test_audit_runtime.py`).
Removing `translate_cached` without updating the test fixture causes `ImportError` +
`AttributeError`.

**Atomicity requirement:** The dead-code removal and the test fixture update MUST be in the
same commit. The fixture update must happen first (logically), then the function removal —
but since they're atomic, order is irrelevant within the commit.

**Semantic targets:**

| File | Target | Action |
|---|---|---|
| `src/backend/apps/core/services/translation.py` | `translate_cached` function (lines 107–121) + `@lru_cache(maxsize=128)` decorator (line 107) | Remove both |
| `src/telegram_bot/tests/test_multi_lang_translation.py` | `_reset_translation_state` fixture — import block (line 21) + `cache_clear()` call (line 53) | Remove `translate_cached` from import list; remove `translate_cached.cache_clear()` line |

**Changes:**

```yaml
- action: remove
  file: src/backend/apps/core/services/translation.py
  target: translate_cached function (lines 107-121) including @lru_cache decorator
  description: >
    Remove the def translate_cached(query: str) -> str function and its
    @lru_cache(maxsize=128) decorator. The live path is translate_cached_generic
    (line 124) called by translate_text (line 192-194) and backfill_translations.py:41.

- action: edit
  file: src/telegram_bot/tests/test_multi_lang_translation.py
  target: import block (line 19-24) and _reset_translation_state fixture (line 53)
  description: >
    Remove translate_cached from the import list (line 21):
      from apps.core.services.translation import (
          _CIRCUIT_BREAKER,
          translate_cached,        # <-- REMOVE THIS LINE
          translate_cached_generic,
          translate_text,
      )
    Remove the cache_clear call in _reset_translation_state (line 53):
      translate_cached.cache_clear()  # <-- REMOVE THIS LINE
    Keep translate_cached_generic.cache_clear() (line 54) — that is the LIVE function.

  code_hint: |
    # Before:
    from apps.core.services.translation import (
        _CIRCUIT_BREAKER,
        translate_cached,
        translate_cached_generic,
        translate_text,
    )
    # After:
    from apps.core.services.translation import (
        _CIRCUIT_BREAKER,
        translate_cached_generic,
        translate_text,
    )

    # Before (in fixture):
    translate_cached.cache_clear()
    translate_cached_generic.cache_clear()
    # After:
    translate_cached_generic.cache_clear()
```

**Acceptance criteria:**
- `translate_cached` function definition removed from `translation.py`
- `@lru_cache(maxsize=128)` decorator removed (was only on `translate_cached`; `translate_cached_generic` has its own `@lru_cache(maxsize=256)`)
- `translate_cached` removed from import in `test_multi_lang_translation.py`
- `translate_cached.cache_clear()` removed from `_reset_translation_state` fixture
- `translate_cached_generic.cache_clear()` retained (live function)
- `grep -rn '\btranslate_cached\b' src/` returns zero matches
- `translate_cached_generic` still imported and used by `backfill_translations.py:41` and `translation.py:193`
- No `ImportError` or `AttributeError` in `test_multi_lang_translation.py`

**Required tests:**
- Run `test_multi_lang_translation.py`:
  `$dc run --rm -e PYTEST_OPTS="-k TestTranslateAllLanguages or -k TestTranslateText" test`
- ruff: `uv run ruff check src/backend/apps/core/services/translation.py`
  `uv run ruff check src/telegram_bot/tests/test_multi_lang_translation.py`
- grep: `rg '\btranslate_cached\b' src/` → must return 0 matches (excluding the grep itself)

**Implementation sequence:**
1. Remove `translate_cached` import from `test_multi_lang_translation.py` (line 21)
2. Remove `translate_cached.cache_clear()` from `_reset_translation_state` fixture (line 53)
3. Remove `translate_cached` function + `@lru_cache` decorator from `translation.py` (lines 107–121)
4. Commit atomically (single commit with all 3 edits)
5. Validator: grep for zero `translate_cached` references
6. Validator: run `test_multi_lang_translation.py`

**Architectural constraints:**
- The `@lru_cache` import from `functools` is still needed (used by `translate_cached_generic` at line 124)
- `backfill_translations.py:41` uses `translate_cached_generic`, NOT `translate_cached` — confirmed no production dependency
- The test file lives in `src/telegram_bot/tests/` (outside `src/backend/` conftest hierarchy) — bot tests use their own conftest

**Risks:**
- **Low — but atomicity is critical:** If the test fixture is not updated before/in the same commit as the function removal, `ImportError` breaks the entire `test_multi_lang_translation.py` suite. The atomicity requirement ensures this doesn't happen.
- **Low:** Accidental removal of `translate_cached_generic` (the live function). The Implementor must carefully distinguish the two functions — they have similar names but different responsibilities.

**Agents:** Implementor (remove + test fix, atomic commit) → Validator (grep + test run)

**Verification commands:**
- `$dc run --rm -e PYTEST_OPTS="-k test_multi_lang_translation" test`
- `git grep -n "translate_cached"` → must return only the grep command line (zero code matches)
- `uv run ruff check src/backend/apps/core/services/translation.py src/telegram_bot/tests/test_multi_lang_translation.py`

---

### Block B2 — BACKFILL-WIRE: Wire `backfill_translations` into bootstrap with env guard (SRH-003)

**Finding:** SRH-003 (P1, MEDIUM→BEST-PRACTICE)

**Description:**

The `backfill_translations` management command exists and is correctly implemented (idempotent,
batched, uses `translate_cached_generic` with error handling), but is never invoked from any
Docker entrypoint, CI workflow, or bootstrap command. The `migrate_locked.py` `steps` tuple
runs only `migrate`, `setup_search_triggers`, and `load_exchange_rates`.

The backfill translates existing Russian ad titles/descriptions to English and Bosnian
(populating `title_en`/`description_en`/`title_bs`/`description_bs` columns). Without it,
the per-language search vectors (`search_vector_ru/bs/en`) remain NULL for pre-existing ads on
production upgrades, degrading cross-language search recall.

**Env-gating rationale:** The command calls `translate_cached_generic` → `_translate_via_api`
which fires a real HTTP POST to `https://translation.googleapis.com/language/translate/v2`
with `settings.GOOGLE_TRANSLATE_API_KEY`. Running this unconditionally at container startup
would incur real Google Cloud Translation API costs and add startup latency. Must be gated
behind an explicit opt-in.

**Semantic targets:**

| File | Target | Action |
|---|---|---|
| `src/backend/apps/core/utils/migrate_locked.py` | `steps` tuple in `main()` function | Conditionally append `("backfill_translations",)` gated by `RUN_TRANSLATION_BACKFILL` env var |
| `src/backend/apps/core/management/commands/bootstrap_reference_data.py` | Module docstring + `Command.handle()` docstring | Update to mention the env-gated backfill_translations step |

**Changes:**

```yaml
- action: modify
  file: src/backend/apps/core/utils/migrate_locked.py
  target: steps tuple in main() function (current: hardcoded 3-tuple)
  description: >
    Convert the steps tuple to a list, conditionally append
    ("backfill_translations",) when os.getenv("RUN_TRANSLATION_BACKFILL") == "true",
    then convert back to tuple. Default behavior (env var absent) is unchanged —
    no backfill runs at startup.

  code_hint: |
    # Before (lines 50-54):
    steps: tuple[tuple[str, ...], ...] = (
        ("migrate", "--noinput", "--run-syncdb"),
        ("setup_search_triggers",),
        ("load_exchange_rates",),
    )

    # After:
    steps_list: list[tuple[str, ...]] = [
        ("migrate", "--noinput", "--run-syncdb"),
        ("setup_search_triggers",),
        ("load_exchange_rates",),
    ]
    if os.getenv("RUN_TRANSLATION_BACKFILL") == "true":
        steps_list.append(("backfill_translations",))
        logger.info("Translation backfill enabled (RUN_TRANSLATION_BACKFILL=true)")
    steps: tuple[tuple[str, ...], ...] = tuple(steps_list)

  notes: >
    os is already imported at line 38 (inside main). The env var follows the
    existing env-gated pattern used in docker/entrypoint.sh (SKIP_ENV_CHECK).

- action: edit
  file: src/backend/apps/core/management/commands/bootstrap_reference_data.py
  target: module docstring (lines 3-6) and Command docstring
  description: >
    Update docstrings to mention the env-gated backfill_translations step as the
    fourth optional step when RUN_TRANSLATION_BACKFILL=true.
```

**Acceptance criteria:**
- `migrate_locked.py` `main()` conditionally includes `("backfill_translations",)` in `steps`
  only when `RUN_TRANSLATION_BACKFILL=true`
- Default behavior (env var absent or not "true") is unchanged — no backfill runs
- `bootstrap_reference_data.py` docstring accurately documents the env-gated step
- `backfill_translations` command runs without errors when invoked with `RUN_TRANSLATION_BACKFILL=true`
- Test entrypoint (`entrypoint-test.sh:25` → `bootstrap_reference_data`) does NOT trigger
  backfill (env var not set in test compose)

**Required tests:**
- Integration test: `backfill_translations` runs without errors on seeded data
  (mocked translator to avoid real Google API calls)
- Test: default (no env var) → `backfill_translations` step absent from `migrate_locked` steps
- Test: `RUN_TRANSLATION_BACKFILL=true` → step present

**Implementation sequence:**
1. Modify `migrate_locked.py` `steps` tuple to be env-gated list
2. Update `bootstrap_reference_data.py` docstrings
3. Add integration test for `backfill_translations` command (mocked translator)
4. Add unit test for `migrate_locked` env-gating logic
5. Validator: review env-gating approach + run integration test
6. Run fast gate: `$dc run --rm --env PYTEST_SKIP_MARKERS=seed test`

**Architectural constraints:**
- The `steps` tuple type annotation must be preserved (`tuple[tuple[str, ...], ...]`)
- `os` is imported inside `main()` at line 38 — no new import needed
- `backfill_translations` uses `translate_cached_generic` (not the removed `translate_cached`) —
  confirmed no conflict with Block B1
- The env-gated approach mirrors the existing `SKIP_ENV_CHECK` pattern in `docker/entrypoint.sh`
- Must NOT break `entrypoint-test.sh` which runs `bootstrap_reference_data || true` — the
  env var is not set in test compose, so default behavior is preserved
- `docs/ops/migration-workflow.md:284,390` already documents `manage.py backfill_translations`
  as a manual operator step — the gap is only that it's not automated in the bootstrap

**Risks:**
- **Medium:** Adding a step to the critical startup path (`migrate_locked.py`) affects container
  boot for web + bot + CI. The env gate (default off) mitigates this — no behavior change unless
  explicitly opted in.
- **Low:** If `RUN_TRANSLATION_BACKFILL=true` is accidentally set in production without
  `GOOGLE_TRANSLATE_API_KEY`, the command will fail gracefully (logs warning per
  `backfill_translations.py:42-53`) and the bootstrap continues (per `migrate_locked.py`'s
  "all three steps run regardless of individual failures" pattern).
- **Low:** The `backfill_translations` command's `filter(title_en__isnull=True) | filter(title_bs__isnull=True)`
  query may be slow on large tables — but it's batched (`--batch-size`, default 100) and only runs
  when explicitly opted in.

**Agents:** Implementor (modify `migrate_locked.py` + `bootstrap_reference_data.py` + tests)
→ Validator (review env-gating logic + integration test)

**Verification commands:**
- `$dc run --rm -e PYTEST_OPTS="-k backfill_translations" test`
- `$dc run --rm -e PYTEST_OPTS="-k migrate_locked" test`
- `uv run ruff check src/backend/apps/core/utils/migrate_locked.py`
- `uv run basedpyright src/backend/apps/core/utils/migrate_locked.py`

---

### Block B3 — FTS-BACKFILL: Add `--backfill` flag to `setup_search_triggers` (SRH-007)

**Finding:** SRH-007 (P1, MEDIUM→BEST-PRACTICE)

**Description:**

The PostgreSQL trigger `ads_search_vector_fn` (installed by `setup_search_triggers.py`)
is a BEFORE INSERT OR UPDATE trigger that populates `search_vector_ru/bs/en` on every row
write. However, it does NOT fire for rows that already exist when the trigger is installed.
On production upgrades with pre-existing ads, all existing per-language vectors are NULL
until each row is next updated.

`db-indexes.md:185-187` documents a manual workaround (`UPDATE ads SET title = title`), but
this is not automated. The `setup_search_triggers.py` `Command.handle()` method (line 114)
executes only `DDL_STATEMENTS` (lines 98-103) — no backfill UPDATE.

The fix adds a `--backfill` opt-in CLI flag that runs the backfill UPDATE after DDL
installation. The UPDATE triggers the existing BEFORE INSERT OR UPDATE trigger to recompute
vectors for rows that have NULL per-language vectors.

**Semantic targets:**

| File | Target | Action |
|---|---|---|
| `src/backend/apps/ads/management/commands/setup_search_triggers.py` | `Command` class — `add_arguments` method (new), `handle` method (modify) | Add `--backfill` flag; if set, run UPDATE backfill after DDL |
| `docs/02-database/db-indexes.md` | §Migration notes (lines 185-187) | Update to reference the automated `--backfill` flag as the preferred approach |

**Changes:**

```yaml
- action: add_method
  file: src/backend/apps/ads/management/commands/setup_search_triggers.py
  target: Command class (add add_arguments method)
  description: >
    Add add_arguments(self, parser) method with a --backfill boolean flag
    (store_true). Default: False (DDL-only, backward compatible).

  code_hint: |
    def add_arguments(self, parser):
        parser.add_argument(
            "--backfill",
            action="store_true",
            default=False,
            help="After installing triggers, backfill NULL search vectors for "
                 "existing rows (UPDATE ads SET title = title WHERE ... IS NULL)",
        )

- action: modify
  file: src/backend/apps/ads/management/commands/setup_search_triggers.py
  target: Command.handle method
  description: >
    After the DDL_STATEMENTS loop, if options["backfill"] is True, execute:
    UPDATE ads SET title = title
    WHERE search_vector_ru IS NULL
       OR search_vector_bs IS NULL
       OR search_vector_en IS NULL
    This fires the BEFORE INSERT OR UPDATE trigger (ads_search_vector_fn)
    to recompute vectors for rows missing them. Idempotent — rows with
    populated vectors are skipped by the WHERE clause.

  code_hint: |
    # In handle(), after the DDL loop:
    if options.get("backfill"):
        backfill_sql = (
            "UPDATE ads "
            "SET title = title "
            "WHERE search_vector_ru IS NULL "
            "OR search_vector_bs IS NULL "
            "OR search_vector_en IS NULL"
        )
        with connection.cursor() as cursor:
            cursor.execute(backfill_sql)
        updated = cursor.rowcount
        logger.info("Backfilled search vectors for %d rows", updated)
        self.stdout.write(self.style.SUCCESS(
            f"Backfilled search vectors for {updated} rows"
        ))

- action: edit
  file: docs/02-database/db-indexes.md
  target: §Migration notes (lines 185-187)
  description: >
    Update the manual workaround note to reference the automated
    `setup_search_triggers --backfill` flag as the preferred approach,
    with the raw UPDATE as a fallback for environments where the flag
    is not used.
```

**Acceptance criteria:**
- `setup_search_triggers` command accepts `--backfill` flag (store_true, default False)
- Without `--backfill`: behavior unchanged (DDL-only)
- With `--backfill`: after DDL installation, runs `UPDATE ads SET title = title WHERE
  search_vector_ru IS NULL OR search_vector_bs IS NULL OR search_vector_en IS NULL`
- The UPDATE triggers `ads_search_vector_fn` to recompute NULL vectors
- `db-indexes.md:185-187` updated to reference `setup_search_triggers --backfill`
- `setup_search_triggers` (default, no flag) is still called by `migrate_locked.py`
  without `--backfill` — backward compatible

**Required tests:**
- Integration test: `setup_search_triggers --backfill` populates NULL vectors for
  existing rows
- Test: `setup_search_triggers` (no flag) does NOT change row data (DDL-only)
- Test: `--backfill` is idempotent (running twice finds 0 NULL rows on second run)

**Implementation sequence:**
1. Add `add_arguments` method to `Command` class in `setup_search_triggers.py`
2. Modify `handle` to conditionally run backfill UPDATE when `--backfill` is set
3. Update `db-indexes.md` §Migration notes
4. Add integration test for `--backfill` path
5. Add test for default (no --backfill) path
6. Validator: review SQL + run integration test

**Architectural constraints:**
- The `--backfill` flag uses `store_true` (default False) — backward compatible
- The UPDATE uses `SET title = title` which is a no-op on the column value but
  triggers the BEFORE INSERT OR UPDATE trigger, causing `search_vector_fn` to
  recompute vectors. This is the same mechanism documented in `db-indexes.md:185`
- The WHERE clause scopes to NULL rows only — avoids recomputing already-populated
  vectors (efficient on large tables)
- `cursor.rowcount` must be captured BEFORE the `with` block exits (cursor
  invalidated after context exit) — use `cursor.rowcount` inside the `with` block
- The `connection` import already exists (line 28: `from django.db import connection`)
- `migrate_locked.py` calls `("setup_search_triggers",)` without `--backfill` — this
  block does NOT modify `migrate_locked.py`
- Test DB (test settings with `DisableMigrations`) uses `--run-syncdb` to create tables;
  the trigger must exist before the backfill UPDATE can fire — the `handle` method
  installs DDL first, then runs UPDATE, so this ordering is correct

**Risks:**
- **Low:** The `--backfill` flag is opt-in. Default behavior (DDL-only) is unchanged.
- **Low:** The `UPDATE ads SET title = title` fires the trigger on potentially many rows
  — but the WHERE clause limits to NULL-vector rows only, and it's a single statement
  (set-based, not row-by-row). On a table with millions of ads but few NULL vectors
  (e.g., fresh install), this is near-instant.
- **Low:** If the trigger function `ads_search_vector_fn` has a bug, the backfill could
  populate vectors incorrectly — mitigated by the existing trigger test coverage
  (`test_squash_rehydrate_runsql.py` imports `DDL_STATEMENTS`; trigger correctness is
  verified by the 94 search tests per the audit findings)

**Agents:** Implementor (modify `Command` class + docs + tests) → Validator (review SQL + integration test)

**Verification commands:**
- `$dc run --rm -e PYTEST_OPTS="-k setup_search_triggers or -k search_vector" test`
- `uv run ruff check src/backend/apps/ads/management/commands/setup_search_triggers.py`
- `uv run basedpyright src/backend/apps/ads/management/commands/setup_search_triggers.py`

---

### Block B4 — SKIP: SRH-006 (rejected, no action)

**Finding:** SRH-006 (REJECTED — stale)

**Description:** The orphaned test file `test_audit_runtime.py` does not exist in the
current codebase (glob confirmed). `ruff check src/backend/apps/search/` passes cleanly.
No action required.

**Note:** The verification report (2026-09-16) found 6 ruff errors in `src/backend/` from
committed migrations 0005/0006 and 2 untracked diagnostic test files (`b9_debug_test.py`,
`test_debug_value.py`) — these are outside the SRH audit scope (search dirs are clean)
and tracked as ancillary.

**Status:** RESOLVED — no implementation needed.

---

## 4. Rollout Safety Summary

| Block | Backward-compatible? | Risk | Test gap | Notes |
|---|---|---|---|---|
| B0 | Yes (doc-only) | Low | None — doc-only | SRH-001 P0: Validator confirms privacy accuracy |
| B1 | Yes (removes unused code) | Low | Confirm zero `translate_cached` refs via grep; update test fixture | MUST be single atomic commit |
| B2 | Yes (env-gated, defaults off) | Medium | Integration test: `backfill_translations` runs on seeded data | Adds step to startup path — env gate mitigates |
| B3 | Yes (`--backfill` opt-in, default DDL-only) | Low | Integration test: `--backfill` populates NULL vectors | Idempotent, WHERE-scoped to NULL rows |
| B4 | N/A | N/A | N/A | No action — SRH-006 rejected |

### Cross-block safety notes

1. **B1 ↔ B2 independence:** `translate_cached` (B1, removed) is NOT used by `backfill_translations`
   (B2). The backfill command uses `translate_cached_generic` (line 41 of `backfill_translations.py`),
   which is the live function and remains. No dependency.

2. **B2 ↔ B3 independence:** B2 modifies `migrate_locked.py`'s `steps` tuple (adds `backfill_translations`).
   B3 modifies `setup_search_triggers.py`'s `Command` class (adds `--backfill` flag). `migrate_locked.py`
   calls `("setup_search_triggers",)` without `--backfill` — B3's default behavior is backward compatible.
   B2's env-gated `backfill_translations` step is independent of B3's `--backfill` flag.

3. **SRH-001 compliance:** The corrected `consent.py` docstring must accurately describe the actual
   egress: ad title/description → Google Translate at publication time (via `translate_cached_generic`,
   called by `translate_text` in `telegram_bot/handlers/ad_create.py`), NO search-query translation.
   Verified against `technical-specification.md` §G line 120.

4. **Test bootstrap compatibility:** `entrypoint-test.sh:25` runs `bootstrap_reference_data || true`.
   B2's env-gated step defaults to off (env var not set in test compose) — test entrypoint unaffected.
   B3's `--backfill` flag defaults to False — `setup_search_triggers` called from bootstrap without
   `--backfill` — test entrypoint unaffected.

---

## 5. Verification Strategy

### 5.1 Test infrastructure

All tests run via Docker Compose (local `uv run pytest` fails — no DB on localhost:5432):

```powershell
$dc='docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml'
```

| Purpose | Command |
|---|---|
| Start test DB | `$dc up -d db` |
| Fast gate (skips seed suite) | `$dc run --rm --env PYTEST_SKIP_MARKERS=seed test` |
| Single test / keyword filter | `$dc run --rm -e PYTEST_OPTS="-k test_name" test` |
| Fresh schema (after migration changes) | `$dc run --rm --env PYTEST_OPTS="--create-db --tb=short -n auto" test` |
| Lint | `uv run ruff check <path>` |
| Typecheck | `uv run basedpyright <path>` |

### 5.2 Test coverage matrix

| Block | Test file | Test(s) | Docker command |
|---|---|---|---|
| B0 | (none) | Validator spot-check only | N/A — doc-only |
| B1 | `src/telegram_bot/tests/test_multi_lang_translation.py` | Full existing suite (all `TestTranslateAllLanguages`, `TestTranslateTextExceptNarrowing`, `TestTranslateTextRetry` classes) | `$dc run --rm -e PYTEST_OPTS="-k test_multi_lang_translation" test` |
| B1 | (grep verification) | `rg '\btranslate_cached\b' src/` → 0 matches | `rg` / `git grep` |
| B2 | `src/backend/apps/core/tests/test_migrate_locked.py` (new) | Test env-gating: default → step absent; `RUN_TRANSLATION_BACKFILL=true` → step present | `$dc run --rm -e PYTEST_OPTS="-k migrate_locked" test` |
| B2 | `src/backend/apps/ads/tests/test_backfill_translations.py` (new) | Integration: command runs on seeded data (mocked translator) | `$dc run --rm -e PYTEST_OPTS="-k backfill_translations" test` |
| B3 | `src/backend/apps/ads/tests/test_setup_search_triggers.py` (new) | Integration: `--backfill` populates NULL vectors; default (no flag) does nothing; idempotent on second run | `$dc run --rm -e PYTEST_OPTS="-k setup_search_triggers or -k search_vector" test` |

### 5.3 Post-implementation regression gate

After all blocks:
```powershell
$dc run --rm --env PYTEST_SKIP_MARKERS=seed test
```
This runs the fast gate (~minutes, excludes the ~17-min seed suite). Must pass fully.

### 5.4 Lint + typecheck targets

| Block | Lint target | Typecheck target |
|---|---|---|
| B0 | `consent.py`, `search/models.py` | `consent.py`, `search/models.py` |
| B1 | `translation.py`, `test_multi_lang_translation.py` | `translation.py`, `test_multi_lang_translation.py` |
| B2 | `migrate_locked.py`, `bootstrap_reference_data.py` | `migrate_locked.py` |
| B3 | `setup_search_triggers.py` | `setup_search_triggers.py` |

---

## 6. Audit Trail of Corrections

Corrections applied during validation re-verification (2026-09-16), from the verification report:

| # | Correction | Original finding | Validated finding | Impact on this plan |
|---|---|---|---|---|
| C1 | SRH-002 hidden dependency is `test_multi_lang_translation.py:21,53`, not `test_audit_runtime.py:103` | Cited `test_audit_runtime.py:103` as only test ref | Actual dep: `test_multi_lang_translation.py:21` (import) + `:53` (`cache_clear()`) | B1 includes removing both import and cache_clear call |
| C2 | SRH-006 stale — `test_audit_runtime.py` already deleted | Claimed orphaned test file in tree | File does not exist; ruff passes on search dir | B4 = no action (rejected) |
| C3 | SRH-006 ruff-clean claim is stale — 6 new errors appeared | Claimed `ruff check src/backend/` passes | 2 committed migrations (0005/0006, 2026-09-14) + 2 untracked diagnostic test files now fail lint | Out of scope (search/audit dirs clean); noted as ancillary |
| C4 | SRH-003 `ci.yml:227` is an echo line, not bootstrap call | Cited ci.yml lines 86 + 227 | Second bootstrap call is `ci.yml:236`; line 227 is `echo "ERROR: Database unavailable"` | No impact on plan (finding validated: command never invoked) |
| C5 | SRH-003 cited `:56-69` but file is 140 lines | Cited class header range | `:56-69` covers only class header + `add_arguments`; real logic is 108–140; file intact | B2 targets the `steps` tuple in `migrate_locked.py`, not the command file itself |
| C6 | SRH-007 `db-indexes.md` workaround is at lines 185-187, not 165 | Cited lines 165-166 | Actual workaround text at **lines 185-187**; line 165 is in `ad_images` thumbnail block | B3 updates `db-indexes.md` lines 185-187 |
| C7 | SRH-005 confirmed: all 4 GIN indexes in code + db-indexes.md | Cited only legacy index | `ads/models.py:259-274` defines all 4; `db-indexes.md:48-59` documents all 4 | B0 updates `spec-index.md:91` to list all 4 |
| C8 | `spec-index.md` is internally inconsistent: lines 48+73 mention per-language, line 91 doesn't | — | Confirmed: §G line 48 and §G line 73 correctly mention per-language vectors, but §Key tables line 91 is stale | B0 fixes line 91 only |

---

## 7. Implementation Checklist

### Block B0 — Doc-only fixes (SRH-001, SRH-004, SRH-005, Ancillary §D) — ✅ ALREADY DONE

Re-verification on 2026-09-16 confirmed all four fixes are already present in the codebase:
- `consent.py:8-14` already says "Buyer search queries are NOT sent to any translation service"
- `search/models.py:76-79` already has corrected help_text
- `spec-index.md:91` already lists all 4 GIN indexes
- `technical-specification.md:66` already says "no query-time translation"

- [x] **B0.1** consent.py docstring already correct — no edit needed
- [x] **B0.2** SavedSearch.query help_text already correct — no edit needed
- [x] **B0.3** spec-index.md already correct — no edit needed
- [x] **B0.4** technical-specification.md §D already correct — no edit needed
- [x] **B0.5** Validator spot-check: confirmed (already verified by Tech Lead)
- [x] **B0.6** Lint: confirmed no issues (doc-only)

### Block B1 — Dead code removal (SRH-002) — ✅ ALREADY DONE

Re-verification on 2026-09-16 confirmed `translate_cached` is already fully removed:
- `grep -rn '\btranslate_cached\b' src/` → zero matches
- `test_multi_lang_translation.py:21,52` already imports and calls `translate_cached_generic`
- `translation.py` has only `translate_cached_generic` (line 107-122, `@lru_cache(maxsize=256)`)

- [x] **B1.1** translate_cached already removed from import in test_multi_lang_translation.py
- [x] **B1.2** translate_cached.cache_clear() already removed from _reset_translation_state fixture
- [x] **B1.3** translate_cached function + @lru_cache decorator already removed from translation.py
- [x] **B1.4** Already committed (pre-existing)
- [x] **B1.5** Validator: grep confirms zero translate_cached references
- [x] **B1.6** test_multi_lang_translation.py passes (already verified)
- [x] **B1.7** Lint: confirmed clean

### Block B2 — Translation backfill wiring (SRH-003)

- [ ] **B2.1** Modify `migrate_locked.py` `main()`: convert `steps` tuple to env-guarded list; append `("backfill_translations",)` when `RUN_TRANSLATION_BACKFILL=true`
- [ ] **B2.2** Update `bootstrap_reference_data.py` docstrings to mention env-gated 4th step
- [ ] **B2.3** Add unit test: default (no env var) → `backfill_translations` absent from steps
- [ ] **B2.4** Add unit test: `RUN_TRANSLATION_BACKFILL=true` → step present
- [ ] **B2.5** Add integration test: `backfill_translations` runs on seeded data (mocked translator)
- [ ] **B2.6** Validator: review env-gating logic
- [ ] **B2.7** Run: `$dc run --rm -e PYTEST_OPTS="-k migrate_locked or -k backfill_translations" test`
- [ ] **B2.8** Lint + typecheck `migrate_locked.py`

### Block B3 — FTS backfill flag (SRH-007)

- [ ] **B3.1** Add `add_arguments` method to `setup_search_triggers.py` `Command` class: `--backfill` (store_true, default False)
- [ ] **B3.2** Modify `handle`: if `--backfill`, run `UPDATE ads SET title = title WHERE search_vector_ru IS NULL OR search_vector_bs IS NULL OR search_vector_en IS NULL` after DDL loop
- [ ] **B3.3** Update `db-indexes.md` §Migration notes (lines 185-187): reference `setup_search_triggers --backfill` as preferred approach
- [ ] **B3.4** Add integration test: `--backfill` populates NULL vectors for existing rows
- [ ] **B3.5** Add test: default (no flag) → DDL only, no data change
- [ ] **B3.6** Add test: idempotent — second `--backfill` run finds 0 rows
- [ ] **B3.7** Validator: review backfill SQL
- [ ] **B3.8** Run: `$dc run --rm -e PYTEST_OPTS="-k setup_search_triggers or -k search_vector" test`
- [ ] **B3.9** Lint + typecheck `setup_search_triggers.py`

### Block B4 — SRH-006 (rejected, no action)

- [x] **B4.1** Confirmed: `test_audit_runtime.py` does not exist (glob verified)
- [x] **B4.2** Confirmed: `ruff check src/backend/apps/search/` passes cleanly

---

## 8. Related Resources

- `.ai/audit/99-validation/08-search-fts-validated-findings.md` — validated findings (all 7)
- `.ai/audit/99-validation/08-search-fts-validated-findings-verification.md` — evidence verification (2026-09-16)
- `docs/01-spec/technical-specification.md` §D (line 66) and §G (lines 118-120) — authoritative spec for language/search architecture
- `docs/01-spec/spec-index.md` — agent summary (line 91 stale)
- `docs/02-database/db-indexes.md` — §Migration notes (lines 185-187), §Indexes (lines 48-59)
- `src/backend/apps/core/services/translation.py` — shared translation service (line 107-121 dead code, line 124-139 live function)
- `src/backend/apps/core/utils/migrate_locked.py` — bootstrap sequence (steps tuple, line 50-54)
- `src/backend/apps/core/management/commands/bootstrap_reference_data.py` — bootstrap command
- `src/backend/apps/ads/management/commands/setup_search_triggers.py` — trigger/DDL installer
- `src/backend/apps/ads/management/commands/backfill_translations.py` — translation backfill command
- `src/backend/apps/search/models.py` — `SavedSearch.query` help_text (line 76)
- `src/backend/apps/users/views/consent.py` — consent docstring (lines 8-13)
- `src/telegram_bot/tests/test_multi_lang_translation.py` — hidden dependency (lines 21, 53)
- `src/backend/apps/media/tests/test_backfill_thumbnails.py` — existing integration test pattern for management commands
- `docs/ops/migration-workflow.md:284,390` — documents `backfill_translations` as manual step
- `docs/96-researches/i18n-translation-egress.md` — research doc referencing `translate_cached` (non-required)
