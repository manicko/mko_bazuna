---
id: 28
domain: external-api
source: .ai/audit/99-validation/09-external-api-validated-findings.md
status: draft
tags: [i18n, nginx, security-headers, csp, hsts, redis, backfill, translation, secrets]
related:
  - .ai/audit/09-external-api/findings.md
  - .ai/plans/27-search-fts-fixes.md
  - docker/nginx/nginx.conf
  - src/backend/apps/ads/management/commands/backfill_translations.py
  - src/backend/apps/core/services/translation.py
  - src/backend/apps/core/views.py
  - src/backend/config/settings/base.py
  - src/backend/config/settings/prod.py
  - docs/01-spec/architecture-structure.md
  - docs/ops/docker-deployment.md
---

# Plan 28 — External API Hardening Fixes (6 findings)

## 0. Summary

Six validated findings from the **09-external-api** audit phase require fixes.
All six are independently deployable (confirmed by the validation phase's
Rollout Safety matrix). This plan decomposes them into 9 execution blocks with
two dependency chains (code → test): 09-EXT-01 (B1 → B2) and 09-EXT-04
(B7 → B8). Three are code changes, one is nginx config, two are documentation,
and one (B5) is tracking-document creation.

```
B1 (code: 09-EXT-01) ──> B2 (test: 09-EXT-01)
B3 (code: 09-EXT-05)    standalone
B4 (conf: 09-EXT-03)    Researcher gate (preload eligibility)
B5 (docs: 09-EXT-02)    standalone (tracking milestone)
B6 (conf: 09-EXT-04a)   standalone (nginx rate limit)
B7 (code: 09-EXT-04b) ──> B8 (test: 09-EXT-04c)
B9 (docs: 09-EXT-07)    standalone (secret rotation)
```

---

## 1. Resolution Status

| Finding | Priority | Type | Status | Block(s) |
|---------|----------|------|--------|----------|
| 09-EXT-01 | HIGH | SPEC-DEVIATION | Open | B1, B2 |
| 09-EXT-02 | MEDIUM | BEST-PRACTICE | Open | B5 |
| 09-EXT-03 | MEDIUM | SPEC-DEVIATION | Open | B4 |
| 09-EXT-04 | MEDIUM | BEST-PRACTICE | Open | B6, B7, B8 |
| 09-EXT-05 | LOW | BEST-PRACTICE | Open | B3 |
| 09-EXT-07 | LOW | DOC-UPDATE | Open | B9 |
| 09-EXT-06 | — | — | Rejected (not reproducible) | — |
| CF-EXT-01 | — | — | Stale cross-phase conflict (resolved) | — |
| CF-EXT-02 | — | — | Stale cross-phase conflict (resolved) | — |

---

## 2. Block Summary

| Block | Finding | Primary | Gate(s) | Scope | Dependencies |
|-------|---------|---------|---------|-------|--------------|
| B1 | 09-EXT-01 | Implementor | Researcher, Auditor | `backfill_translations.py`: rename wrapper, switch to `translate_text()` | — |
| B2 | 09-EXT-01 | Validator | — | `test_backfill_translations.py`: update patch target + failure semantics | B1 |
| B3 | 09-EXT-05 | Implementor | Validator | `base.py`: `REDIS_URL` default `""` | — |
| B4 | 09-EXT-03 | Implementor | Researcher, Auditor | `nginx.conf`: HSTS `preload` (Path A) or `proxy_hide_header` (Path B) | — |
| B5 | 09-EXT-02 | docs-specialist | — | Create Phase 2 CSP enforcement tracking milestone doc | — |
| B6 | 09-EXT-04a | Implementor | — | `nginx.conf`: dedicated `location /csp-report/` with `login_limit` rate zone | — |
| B7 | 09-EXT-04b | Implementor | Validator | `core/views.py:csp_report()`: Pydantic schema validation + INFO log | — |
| B8 | 09-EXT-04c | Validator | — | `test_csp_report.py`: schema validation tests + log-level assertion | B7 |
| B9 | 09-EXT-07 | docs-specialist | — | `docker-deployment.md`: secret rotation procedures + env var table | — |

---

## 3. Execution Order & Dependency DAG

```
Phase 1 (parallel — 7 independent blocks, different findings/files/agents):
  B1 (backfill code)        ──|
  B3 (REDIS_URL default)    ──|
  B4 (HSTS preload)         ──|
  B5 (CSP Phase 2 tracking) ──|
  B6 (nginx csp-report loc)  ──|
  B7 (csp_report schema)    ──|
  B9 (secret rotation docs) ─|

Phase 2 (after Phase 1 dependencies):
  B2 (backfill tests)      ← B1
  B8 (csp_report tests)    ← B7

Phase 3 (full regression):
  make test (fast gate, skips seed suite)
```

```
B1 ──> B2
B3    (standalone)
B4    (standalone, Researcher gate)
B5    (standalone, docs)
B6    (standalone)
B7 ──> B8
B9    (standalone, docs)
```

**B4 + B5 coordination (deployment):** Both touch nginx security headers
(B4 adds `preload` to HSTS; B5 is docs only). No code dependency, but the
deployment of B4 should be coordinated with B5's tracking milestone so the
Phase 2 CSP enforcement doc references the correct HSTS state.

**B6 + B7 + B8 are independent of each other** (different files: nginx.conf vs
views.py vs test_csp_report.py). B6 (nginx rate limit) cannot be unit-tested
without nginx integration — it is verified by structural config inspection +
manual smoke test. B7 (view schema validation + log level) is verified by B8
(test_csp_report.py). B7 and B6 can be deployed independently and in parallel.

**B1 + B2 are tightly coupled.** B2's patch target changes from
`translate_cached_generic` to `translate_text` — the test will fail to import
or mock correctly if B1 is not applied. They must be applied together in the
same commit/review cycle.

---

## 4. Execution Blocks

### Block B1 — 09-EXT-01: Route backfill through `translate_text()` + wrapper rename

**Finding:** 09-EXT-01 (HIGH, SPEC-DEVIATION, P1, Effort S)

**Status:** CONFIRMED not-yet-fixed. `backfill_translations.py` calls
`translate_cached_generic()` directly (line 41), bypassing the circuit-breaker,
retry, and timeout logic in `translate_text()`. The local `_translate_text`
wrapper (line 26) shadows the public `translate_text` symbol, creating a naming
collision. The per-field skip logic (`if translated_title is not None`) assumes
`None`-on-failure, but `translate_text()` returns the original text on failure
(not `None`).

```yaml
id: b1_backfill_uses_translate_text
title: Route backfill_translations through translate_text() instead of translate_cached_generic()
priority: high
depends_on: []
source_reference: .ai/audit/99-validation/09-external-api-validated-findings.md
source_section: "09-EXT-01 (lines 84-97)"

task_description: >
  In `src/backend/apps/ads/management/commands/backfill_translations.py`,
  replace the direct `translate_cached_generic()` call with the public
  `translate_text()` entry point so the backfill inherits the same
  circuit-breaker, retry (2 attempts, exponential backoff), and ~500ms timeout
  that the bot's ad-creation path uses (`telegram_bot/services/ad_data.py:307`).

  Three concrete changes:

  1. Rename the module-level wrapper `_translate_text` → `_translate_for_backfill`
     to eliminate the naming collision with the public `translate_text`
  (imported from `apps.core.services.translation`). The wrapper's signature
  stays the same: `(text: str, target: str) -> str`.

  2. Inside the wrapper body, change the import and call from:
     ```python
     from apps.core.services.translation import translate_cached_generic
     return translate_cached_generic(text, "ru", target)
     ```
     to:
     ```python
     from apps.core.services.translation import translate_text
     return translate_text(text, "ru", target)
     ```
     The source locale remains `"ru"` — the backfill translates existing Russian
     ads, matching the current `translate_cached_generic(text, "ru", target)`
     call. The bot path uses `"auto"` (ad_data.py:307) but that is a different
     code path (real-time user input, not backfill).

  3. Simplify the wrapper: since `translate_text()` handles empty/whitespace
     input (returns it unchanged) and all error paths internally (returns
     original text on failure), the wrapper no longer needs its own
     `try/except (httpx.HTTPStatusError, httpx.RequestError, httpx.TimeoutException)`
     block, the `if not text` guard, or the `httpx` import. The wrapper becomes
     a thin pass-through that delegates to `translate_text`.

  4. Adjust the per-field skip logic in `handle()` — see Decision Point D1.
     The current code uses `if translated_title is not None:` to decide whether
     to populate the updates dict. With `translate_text()` returning original
     text (never `None`) on failure, this check is always-true under Path A.
     Under Path B (compare-to-original), an additional comparison is added.

  Decision Point D1 (see §8) determines whether the backfill stores the
  original text on failure (Path A, consistent with bot) or skips the field
  (Path B, preserves current NULL-on-failure semantics). Path A is the
  recommended default; Path B is the alternative if the team decides
  NULL-on-failure is required.

description: >
  The `translate_text()` function (`translation.py:143-237`) is the public
  entry point that wraps `translate_cached_generic` with a circuit-breaker
  (3 failures → 60s cooldown), 2-retry with exponential backoff, and a
  ~500ms socket timeout. The backfill command bypasses all of this by calling
  `translate_cached_generic` directly (which has no retry, no circuit-breaker,
  and relies solely on the `lru_cache`). On a Google Translate API hiccup,
  the backfill would get a raw exception (caught by its own try/except and
  returning `None`) instead of the graceful fallback the bot path enjoys.

  The local `_translate_text` wrapper (`backfill_translations.py:26`) shadows
  the public `translate_text` symbol — if any future code in this module
  tries to use `translate_text` via `from apps.core.services import translate_text`
  and then calls it unqualified, Python resolves to the module-level
  `_translate_text` first (if they had the same name), creating a subtle
  shadowing bug. The rename to `_translate_for_backfill` eliminates this.

  The `translate_text()` return contract (`translation.py:160-237`) is:
  - Empty/whitespace input → returned unchanged (no API call)
  - Circuit open → returns original text (no API call)
  - All retries exhausted → returns original text (logged at INFO)
  - Success → returns translated text

  Neither path raises an exception to the caller — the backfill's own
  `try/except` around `Ad.objects.filter(pk=ad.pk).update(...)` (line 124)
  remains for DB-level errors only.

goals:
  - Rename `_translate_text` → `_translate_for_backfill` (eliminate naming collision with public `translate_text`)
  - Replace `translate_cached_generic(text, "ru", target)` call with `translate_text(text, "ru", target)`
  - Simplify wrapper: remove httpx import, inner try/except, and empty-text guard (translate_text handles these)
  - Adjust per-field skip logic per Decision Point D1 (original-text fallback vs NULL-on-failure-via-comparison)
  - Ensure the import is lazy (inside function body) — same as current pattern, avoids circular import during management command discovery

files:
  - path: src/backend/apps/ads/management/commands/backfill_translations.py
    targets:
      - type: module_level_function
        name: _translate_text
      - type: function
        name: _translate_for_backfill
      - type: method
        name: handle
        container: Command
    semantic_anchors:
      replace:
        type: import
        value: "from apps.core.services.translation import translate_cached_generic"
      insert_after:
        type: function_def
        value: "def _translate_for_backfill("

accepted_implementation_paths:
  - path: "A (recommended): original-text fallback"
    change: Remove `if translated_title is not None` check entirely; always populate the updates dict with translate_text's result (original on failure). Simplify _translate_for_backfill to a thin pass-through.
  - path: "B (alternative): preserve NULL-on-failure via comparison"
    change: After calling translate_text, compare result to original text. If equal (fallback detected), set to None and skip field population. More complex but preserves current behavior.

acceptance_criteria:
  - The wrapper function is named `_translate_for_backfill` (no `_translate_text` symbol exists in the module)
  - The import is `from apps.core.services.translation import translate_text` (not `translate_cached_generic`)
  - The call is `translate_text(text, "ru", target)` with source locale "ru"
  - The `httpx` import is removed (no longer needed — translate_text handles all errors internally)
  - The inner `try/except` for httpx exceptions is removed (translate_text owns error handling)
  - The empty-text guard (`if not text or not text.strip(): return None`) is removed (translate_text handles this)
  - The per-field skip logic reflects Decision Point D1
  - `ruff check src/backend/apps/ads/management/commands/backfill_translations.py` passes
  - `basedpyright src/backend/apps/ads/management/commands/backfill_translations.py` passes

required_tests:
  - Existing `test_backfill_translations.py` must be updated (B2) — the patch target changes
  - Full: `src/backend/apps/ads/tests/test_backfill_translations.py` — all tests pass after B2 applies the test updates

implementation_sequence:
  1. Read `_translate_text` function body and `handle()` field-skip loop in backfill_translations.py
  2. Rename `_translate_text` → `_translate_for_backfill`
  3. Change import from `translate_cached_generic` to `translate_text`
  4. Change call from `translate_cached_generic(text, "ru", target)` to `translate_text(text, "ru", target)`
  5. Remove `httpx` import, inner try/except, and empty-text guard from the wrapper
  6. Adjust per-field skip logic per Decision Point D1 (resolve before coding)
  7. Run ruff + basedpyright on the changed file
  8. (After B2) Run backfill tests: `$dc run --rm -e PYTEST_OPTS="src/backend/apps/ads/tests/test_backfill_translations.py --tb=short" test`

architectural_constraints:
  - The `translate_text` import MUST remain lazy (inside `_translate_for_backfill` body) — same as the current `translate_cached_generic` lazy import, to avoid circular import during management command discovery (the `apps.ads` models import triggers settings load, which may import `apps.core.services` transitively)
  - The source locale MUST be `"ru"` (the backfill translates existing Russian ads — ad.title and ad.description are the Russian originals stored in the DB)
  - The bot path (`ad_data.py:307`) uses `source_locale="auto"` — this is a different code path and must NOT be changed
  - `translate_text()` is exported from `apps.core.services.__init__.py` (line 11, 18) AND defined in `apps.core.services.translation` (line 143) — both import paths work; the lazy import should use the defining module (`apps.core.services.translation`) for consistency with the current code and to match the test patch target pattern
  - The outer `try/except` around `Ad.objects.filter(pk=ad.pk).update(**updates)` (line 124) must remain for DB-level errors

risks:
  - Behavioral change (Path A): on translation API failure, the backfill stores the original Russian text in title_en/title_bs fields instead of leaving them NULL. This is consistent with the bot path but means the search vectors for EN/BS will index Russian text as "English"/"Bosnian." This degrades cross-language recall but does NOT crash. Must be verified acceptable.
  - Circuit-breaker state sharing: The module-level `_CIRCUIT_BREAKER` singleton in `translation.py:104` is shared with the bot process. If the backfill triggers circuit-open, subsequent bot translations will also short-circuit until cooldown. This is the intended behavior (shared upstream health), but operators should be aware.
  - If the httpx import is removed but some error type (httpx.HTTPStatusError) is still referenced in the wrapper body, ruff will catch it. The wrapper should have zero httpx references after the change.

agents:
  primary: Implementor
  research_gate: Researcher
  reason: >
    B1 has a genuine architectural decision (D1: NULL-on-failure vs
    original-text fallback) that requires understanding the consequences on
    cross-language FTS recall. The Researcher should verify the bot path's
    error-handling semantics (ad_data.py:322) and whether the backfill should
    match. An Auditor gate verifies the lazy-import pattern and naming
    collision resolution don't introduce circular-import or shadowing bugs.
```

---

### Block B2 — 09-EXT-01: Update backfill tests for `translate_text()`

**Finding:** 09-EXT-01 (HIGH, SPEC-DEVIATION) — test portion

**Status:** CONFIRMED not-yet-fixed. `test_backfill_translations.py` patches
`translate_cached_generic` (line 31), which will break after B1 switches the
backfill to `translate_text`. The failure test (`test_translation_failure_skips_gracefully`)
assumes `None`-on-failure semantics, but `translate_text()` returns original
text on failure.

```yaml
id: b2_update_backfill_tests
title: Update test_backfill_translations.py for translate_text() patch target and original-text fallback
priority: high
depends_on: [b1_backfill_uses_translate_text]
source_reference: .ai/audit/99-validation/09-external-api-validated-findings.md
source_section: "09-EXT-01 (lines 97-99)"

task_description: >
  In `src/backend/apps/ads/tests/test_backfill_translations.py`, update all
  tests to patch `translate_text` instead of `translate_cached_generic`.

  Changes required:

  1. Change the patch target constant from:
     `_TRANSLATE_PATCH = "apps.core.services.translation.translate_cached_generic"`
     to:
     `_TRANSLATE_PATCH = "apps.core.services.translation.translate_text"`

  2. Update `_fake_translate` signature: `translate_text` has the same
     3-arg signature as `translate_cached_generic` (text, source_locale,
     target_locale), so no signature change is needed. The mock body stays
     the same: `return f"{text}_{target_locale}"`.

  3. Update `test_translation_failure_skips_gracefully`:
     Currently patches `translate_cached_generic` to return `None`. After B1,
     the backfill calls `translate_text`, which NEVER returns None — it returns
     the original text on failure (circuit open, retries exhausted, etc.).
     The test must:
     - Patch at the `translate_text` level, returning `original_text`
       (simulating fallback) OR
     - Patch `_translate_via_api` to raise (simulating real failure →
       translate_text falls back to original text) and assert the field
       gets the original text (Path A) or stays NULL (Path B).
     The choice follows Decision Point D1.

  4. Add a new test `test_uses_translate_text_not_raw_api`:
     Asserts that `translate_text` is called (not `translate_cached_generic`
     directly) — verifying the backfill goes through the circuit-breaker path.
     Patch `translate_text` and assert `mock_translate.call_count == 4`
     (title + desc × 2 locales).

  5. Ensure `_reset_translation_state`-equivalent cleanup: since the mock
     patches `translate_text` at the module level, and the mock is scoped to
     the `with patch(...)` block, no explicit cleanup is needed (unlike
     `test_translation.py` which resets the lru_cache + circuit breaker).

description: >
  The current test suite patches `translate_cached_generic` directly, which is
  what the backfill currently calls. After B1 (the backfill calls
  `translate_text`), patching `translate_cached_generic` would still intercept
  the call (since `translate_text` calls it internally via the executor), but
  that defeats the purpose — we want to verify the backfill uses the
  circuit-breaker-protected entry point. The test must patch `translate_text`
  at the module level to assert the correct import/call path, mirroring how
  the bot path is tested (`test_multi_lang_translation.py`).

  The failure test (`test_translation_failure_skips_gracefully`) is the most
  affected: its current assertion (`mock_translate.return_value = None`) is
  incompatible with `translate_text`'s contract (returns original text, never
  None). This test must be rewritten to reflect the new fallback semantics.

goals:
  - Update `_TRANSLATE_PATCH` from `translate_cached_generic` to `translate_text`
  - Update `test_translation_failure_skips_gracefully` for original-text fallback behavior (Path A) or comparison-based skip (Path B)
  - Add `test_uses_translate_text_not_raw_api` verifying translate_text is the patched entry point
  - Ensure all 4+ existing/interactions pass after B1 code change

files:
  - path: src/backend/apps/ads/tests/test_backfill_translations.py
    targets:
      - type: module_level_constant
        name: _TRANSLATE_PATCH
      - type: module_level_function
        name: _fake_translate
      - type: method
        name: test_translation_failure_skips_gracefully
        container: TestBackfillTranslations

acceptance_criteria:
  - `_TRANSLATE_PATCH` targets `apps.core.services.translation.translate_text`
  - `test_translates_ads_with_null_fields` passes with the translate_text mock (4 calls)
  - `test_idempotent_when_all_translations_present` still passes (translate not called)
  - `test_no_ads_succeeds` still passes
  - `test_translation_failure_skips_gracefully` reflects translate_text's fallback behavior (Path A: field gets original text; Path B: field stays NULL via comparison)
  - `test_uses_translate_text_not_raw_api` passes, asserting translate_text (not translate_cached_generic) is called

required_tests:
  - test: updated backfill tests
    command: '$dc run --rm -e PYTEST_OPTS="src/backend/apps/ads/tests/test_backfill_translations.py --tb=short" test'
    expectation: all tests pass (4 existing updated + 1 new = 5)
  - test: regression — translation service tests unaffected
    command: '$dc run --rm -e PYTEST_OPTS="src/backend/apps/core/tests/test_translation.py --tb=short" test'
    expectation: all 12 existing tests pass (translate_text behavior unchanged)

implementation_sequence:
  1. Apply B1 code change first (Implementor)
  2. Change `_TRANSLATE_PATCH` constant target
  3. Update `test_translation_failure_skips_gracefully` for new fallback semantics (D1)
  4. Add `test_uses_translate_text_not_raw_api`
  5. Run backfill tests + translation tests in parallel

architectural_constraints:
  - The mock target `apps.core.services.translation.translate_text` works because `_translate_for_backfill` does a lazy import (`from apps.core.services.translation import translate_text`) inside the function body on every call — patching the module attribute intercepts each import
  - `translate_text` has the same 3-arg signature as `translate_cached_generic` (text, source_locale, target_locale), so `_fake_translate` needs no signature change
  - The mock returns `f"{text}_{target_locale}"` — this differs from the original text, so the Path A "original-text fallback" detection would NOT trigger (the translation succeeded). To test fallback, the mock must be configured to return the original text or `None`
  - `test_translation.py` uses an autouse fixture `_reset_translation_state` to reset the lru_cache + circuit breaker. The backfill tests do NOT need this because they patch `translate_text` at the module level (bypassing the real function entirely), so no shared state is touched

risks:
  - Low: if the patch target doesn't match the lazy import path, `patch` silently doesn't intercept and the test passes trivially (false positive). The new `test_uses_translate_text_not_raw_api` mitigates this by asserting `mock_translate.call_count`.
  - Low: if D1 Path B is chosen (comparison-based NULL-on-failure), the `test_translation_failure_skips_gracefully` assertions differ from Path A. The test must be written after D1 is resolved.

agents:
  primary: Validator
  reason: >
    B2 is a test-only update that verifies B1's code change. The Validator
    writes the updated assertions and runs them. The test will fail on B1-unfixed
    code (patch target mismatch), proving it catches the regression. No Researcher
    gate — the test mechanics are standard pytest `patch` pattern.
```

---

### Block B3 — 09-EXT-05: REDIS_URL default → empty string

**Finding:** 09-EXT-05 (LOW, BEST-PRACTICE, P1, Effort XS)

**Status:** CONFIRMED not-yet-fixed. `base.py:281` defaults
`REDIS_URL` to `"redis://localhost:6379/0"`, which creates a false connection
target in dev/test. The actual `CACHES` backend in dev/test settings
overrides `LOCATION` to `LocMemCache`, but `REDIS_URL` is still read by
`telegram_bot/main.py:53` and `config.settings.base.py:290` (`CACHES["default"]["LOCATION"]`).

```yaml
id: b3_redis_url_default_empty
title: Change REDIS_URL default in base.py from redis://localhost:6379/0 to empty string
priority: low
depends_on: []
source_reference: .ai/audit/99-validation/09-external-api-validated-findings.md
source_section: "09-EXT-05 (lines 67-70)"

task_description: >
  In `src/backend/config/settings/base.py`, change the `env()` call for
  `REDIS_URL` from `default="redis://localhost:6379/0"` to `default=""`.

  Single change at the `REDIS_URL = env(...)` assignment (base.py:281).

  The existing inline comment (base.py:278-280) already documents that the
  empty-string default is the intended dev/test behavior:
  > Production: REDIS_URL=redis://redis:6379/0 (set via env, single source of truth).
  > Dev/test: REDIS_URL="" (empty) — CACHES is overridden in dev/test settings
  > and main.py falls back to MemoryStorage when this is falsy.

  The code is already designed for the empty default — the bug is purely
  that the `default=` argument contradicts the documented intent.

description: >
  The `REDIS_URL` setting at `base.py:281` defaults to
  `"redis://localhost:6379/0"`. In dev/test, this default is never the
  correct endpoint (there is no Redis on localhost:6379 in the Docker
  test setup — the test DB is on port 5433). The dev/test settings
  (`dev.py:40`, `test.py:59`) override `CACHES["default"]["LOCATION"]` to
  `LocMemCache`, so the cache backend is correct — but `REDIS_URL` is also
  read directly by `telegram_bot/main.py:53` (`redis_url = getattr(settings, "REDIS_URL", "") or ""`)
  which falls back to `MemoryStorage` when falsy. The non-empty local default
  could cause the bot to attempt a Redis connection to localhost:6379 in
  dev/test before the `or ""` fallback triggers. Since `getattr(settings, "REDIS_URL", "")`
  returns the settings value (not empty), the `or ""` only applies if
  `REDIS_URL` is falsy — the current default `"redis://localhost:6379/0"` is
  truthy, so the bot would try to connect to localhost:6379.

goals:
  - Change `REDIS_URL` default from `"redis://localhost:6379/0"` to `""` in base.py
  - Align the code with the documented intent (base.py:278-280 comment)
  - No changes to dev.py, test.py, or main.py (they already handle the empty case)

files:
  - path: src/backend/config/settings/base.py
    targets:
      - type: module_level_assignment
        name: REDIS_URL

acceptance_criteria:
  - `REDIS_URL = env("REDIS_URL", default="")` in base.py
  - The inline comment (base.py:278-280) already documents the empty-default intent — no doc change needed
  - `ruff check src/backend/config/settings/base.py` passes

required_tests:
  - test (structural): assert REDIS_URL defaults to empty when env unset
    command: '$dc run --rm -e PYTEST_OPTS="src/backend/config/settings/tests/test_settings_defaults.py::test_redis_url_defaults_empty --tb=short" test'
    expectation: REDIS_URL is "" when REDIS_URL env var is absent
  - test (regression): existing settings tests still pass
    command: '$dc run --rm -e PYTEST_OPTS="src/backend/config/settings/tests/ --tb=short" test'
    expectation: all existing settings tests pass (dev/test CACHES override unchanged)

implementation_sequence:
  1. Change the `default=` argument on the `env()` call for REDIS_URL
  2. Run ruff check on base.py
  3. Run new test + existing settings tests

architectural_constraints:
  - The empty-string default is already handled by all consumers:
    - `telegram_bot/main.py:53`: `redis_url = getattr(settings, "REDIS_URL", "") or ""` — empty → MemoryStorage
    - `base.py:290`: `CACHES["default"]["LOCATION"] = REDIS_URL` — overridden by dev.py:40 and test.py:59 to LocMemCache
    - `prod.py` does NOT override REDIS_URL — production must set it via env (the `.env.prod` file always sets `REDIS_URL=redis://redis:6379/0`)
  - No migration needed (settings constant, not a DB column)
  - The `env.list()` / `environ.Env` library is used for parsing (base.py imports `environ`)

risks:
  - Negligible: the empty default is already the documented intent and is handled by all consumers
  - Very Low: if any code path reads REDIS_URL and expects a non-empty value at import time, it would now get "". A grep shows the only consumers are main.py (handles empty) and base.py CACHES (overridden in dev/test). Production sets the env var.

agents:
  primary: Implementor
  secondary: Validator
  reason: >
    B3 is a single-line settings change. A Validator gate confirms the default
    via a subprocess-isolated test (matching the pattern in
    test_settings_secrets.py). No Researcher or Auditor gate — the change
    is a one-line default fix with zero ambiguity.
```

---

### Block B4 — 09-EXT-03: HSTS `preload` enforcement in nginx

**Finding:** 09-EXT-03 (MEDIUM, SPEC-DEVIATION, P1, Effort S)

**Status:** CONFIRMED not-yet-fixed. nginx emits
`Strict-Transport-Security: max-age=31536000; includeSubDomains` without
`preload` at 3 locations (`nginx.conf:42, 72, 93`). Django's `prod.py:135`
sets `SECURE_HSTS_PRELOAD = True` (emitting `; preload`). There is no
`proxy_hide_header Strict-Transport-Security` anywhere in nginx — both headers
reach the browser as two separate HSTS headers with different directives,
creating a dual-header inconsistency.

```yaml
id: b4_hsts_preload_in_nginx
title: Add HSTS preload to nginx or suppress duplicate via proxy_hide_header
priority: medium
depends_on: []
source_reference: .ai/audit/99-validation/09-external-api-validated-findings.md
source_section: "09-EXT-03 (lines 85-92)"

task_description: >
  In `docker/nginx/nginx.conf`, resolve the dual-HSTS-header inconsistency
  by choosing ONE of two implementation paths:

  Path A — Add `preload` to all 3 nginx HSTS directives:
    Change `"max-age=31536000; includeSubDomains"` to
    `"max-age=31536000; includeSubDomains; preload"` at:
    - server-level (line 42)
    - /static/ block (line 72)
    - /protected-media/ block (line 93)

  Path B — Suppress nginx HSTS, let Django be single source of truth:
    Add `proxy_hide_header Strict-Transport-Security;` at the server level
    (inside the `server { listen 443 ssl; }` block, before any location).
    Remove the 3 `add_header Strict-Transport-Security` lines (42, 72, 93)
    — Django's SecurityMiddleware (enabled at `base.py:148`) emits the HSTS
    header with `preload` on all proxied responses.

  Decision Point D2 (see §8) selects between Path A and Path B.
  Path B requires verifying that Django's SecurityMiddleware runs for ALL
  location blocks (including `internal` locations like /protected-media/).

  Additionally, update `docs/ops/docker-deployment.md:592` ("Security Headers"
  subsection) to document the HSTS behavior accurately — currently it only
  lists nginx's header without `preload` and omits Django's dual header.
  (This doc update can be done as part of B9's doc-pass if the team prefers
  to consolidate doc edits, but the nginx.conf structural change is B4's scope.)

description: >
  nginx is the TLS terminator and sets the browser-facing HSTS header
  (`nginx.conf:42`). Django's SecurityMiddleware (`base.py:148`) ALSO sets
  an HSTS header via `SECURE_HSTS_SECONDS`/`SECURE_HSTS_PRELOAD`/`SECURE_HSTS_INCLUDE_SUBDOMAINS`
  (`prod.py:132-135`). Without `proxy_hide_header`, both headers are sent to
  the browser as two separate `Strict-Transport-Security` headers:
  - nginx: `max-age=31536000; includeSubDomains` (no preload)
  - Django: `max-age=31536000; includeSubDomains; preload`

  Browsers process the first HSTS header they receive and may ignore the
  second. The `preload` directive is lost — defeating `SECURE_HSTS_PRELOAD = True`
  in prod.py.

  Path A (add preload to nginx) is simpler — one directive added to each of
  the 3 HSTS `add_header` lines. The nginx header then matches Django's.

  Path B (proxy_hide_header) is cleaner — single source of truth (Django).
  But it requires that Django's SecurityMiddleware runs for ALL responses,
  including nginx `internal` locations like /protected-media/ (nginx.conf:88-104)
  which serve files directly via `alias` without proxying to Django. If
  `proxy_hide_header` suppresses nginx's header and Django doesn't serve
  the response, /protected-media/ responses would have NO HSTS header at all.

  HSTS preload list eligibility (if Path A with `preload`) requires:
  - Valid SSL certificate on all subdomains
  - No `www` redirect chain
  - Same-domain serving (no cross-domain resources requiring HSTS)
  This must be verified against the production infrastructure (Cloudflare/ALB
  per the validated finding line 89).

goals:
  - Path A: Add `; preload` to all 3 HSTS directives in nginx.conf (lines 42, 72, 93)
  - Path B: Add `proxy_hide_header Strict-Transport-Security;` + remove 3 HSTS add_header lines
  - Update docs/ops/docker-deployment.md:592 to document HSTF behavior accurately
  - (If Path A): verify HSTS preload list eligibility against production infra

files:
  - path: docker/nginx/nginx.conf
    targets:
      - type: directive
        name: add_header Strict-Transport-Security
        occurrences: [42, 72, 93]
      - type: block
        name: server
        (for Path B: add proxy_hide_header inside this block)

implementation_sequence:
  1. Researcher gate: verify HSTS preload list eligibility (Path A) or Path B internal-location coverage
  2. Auditor gate: verify the chosen path resolves the dual-header inconsistency
  3. Apply the chosen path to nginx.conf
  4. Structural test: assert nginx.conf HSTS directive matches chosen path
  5. Update docs/ops/docker-deployment.md:592

architectural_constraints:
  - Production nginx is the TLS terminator (docker-compose.prod.yml mounts certs at /etc/nginx/certs/)
  - Django SecurityMiddleware is enabled (base.py:148) and active in prod (prod.py does not disable it)
  - /protected-media/ (nginx.conf:88-104) is an `internal` location served via `alias /media_volume/` — NOT proxied to Django. Under Path B, this location needs its own HSTS add_header (or accept no HSTS on protected media, which is acceptable since these are image responses behind access-controlled URLs)
  - /static/ (nginx.conf:61-76) IS proxied to Django (`proxy_pass http://web:8000/static/`) — Django's SecurityMiddleware runs and emits HSTS
  - The `/csp-report/` location (added in B6) must NOT be exempt from HSTS
  - `SECURE_HSTS_PRELOAD = True` in prod.py:135 is already set — the inconsistency is purely that nginx's header (without preload) may override Django's

risks:
  - MEDIUM: HSTS preload is a browser-level setting — once a browser sees `preload`, it caches it for the max-age duration (1 year). If the site does NOT qualify for the preload list (e.g., a subdomain lacks a valid cert), deploying preload without submitting to the preload list is harmless (just sets HSTS for 1 year). But submitting to the list is irreversible without de-listing. The `preload` directive in the header is a prerequisite for list submission but does NOT submit by itself.
  - Medium: under Path B, /protected-media/ responses (internal location, not proxied to Django) would lose their HSTS header unless explicitly re-added. This is a minor risk (image responses only, access-controlled) but must be documented.
  - Low: adding `preload` to nginx means browsers will hard-cache HSTS for 1 year even from localhost (if the dev nginx were misconfigured for HTTPS). The dev override (`docker-compose.dev.override.yml`) uses HTTP with port 8000 directly — no nginx in dev — so this is not a concern.

required_tests:
  - test (structural): assert the chosen path is in nginx.conf
    command: '$dc run --rm web nginx -t -c /etc/nginx/nginx.conf'
    expectation: nginx config passes syntax validation
  - test (structural): verify HSTS preload directive consistency
    command: 'grep -c "preload" docker/nginx/nginx.conf'
    expectation: Path A → ≥3 matches; Path B → `proxy_hide_header Strict-Transport-Security` present and no duplicate HSTS

implementation_sequence:
  1. Researcher verifies preload eligibility (Path A) OR internal-location coverage (Path B)
  2. Apply chosen path to nginx.conf
  3. Run `nginx -t` (syntax validation)
  4. Structural grep to confirm consistency
  5. Update docker-deployment.md:592

agents:
  primary: Implementor
  research_gate: Researcher
  auditor_gate: Auditor
  reason: >
    B4 has a genuine technical decision (D2: Path A vs Path B) with
    infrastructure-dependent implications (preload list eligibility, internal
    location coverage). The Researcher must verify the production TLS
    topology (Cloudflare/ALB) before `preload` is safe. The Auditor confirms
    the chosen path resolves the dual-header inconsistency across all 3 HSTS
    locations.
```

---

### Block B5 — 09-EXT-02: CSP Phase 2 enforcement tracking milestone

**Finding:** 09-EXT-02 (MEDIUM, BEST-PRACTICE, P2, Effort S)

**Status:** CONFIRMED not-yet-fixed. The nginx CSP is in Report-Only mode
(`nginx.conf:53, 75, 97`) with `unsafe-inline` in `script-src` and
`style-src`. There is no tracking document, milestone, or migration plan for
Phase 2 (switching to enforcing CSP, removing `unsafe-inline`, migrating to
nonce/hash). The `architecture-structure.md:325` mentions Phase 2 as
"deferred" with no follow-up tracking.

```yaml
id: b5_csp_phase2_tracking_milestone
title: Create tracking milestone document for CSP Report-Only to enforcing migration
priority: medium
depends_on: []
source_reference: .ai/audit/99-validation/09-external-api-validated-findings.md
source_section: "09-EXT-02 (lines 78-83)"

task_description: >
  Create a tracking milestone document at `.ai/tracking/csp-phase2-enforcement.md`
  that establishes the Phase 2 CSP enforcement plan as a tracked deliverable.

  The document must contain:
  1. Current state: CSP is Report-Only with `unsafe-inline` (nginx.conf:53).
     Report-Only means violations are collected but not enforced — zero
     rollout risk. Reports are POSTed to `/csp-report/` (csp_report view,
     core/urls.py:14).
  2. Phase 1 goal (already done): Deploy Report-Only CSP to collect violation
     data without blocking any resources.
  3. Phase 2 goal (tracked here): Migrate to enforcing `Content-Security-Policy`
     with the following sub-tasks:
     a. Audit all inline scripts and styles in templates (identify what
        `unsafe-inline` currently accommodates).
     b. Replace inline scripts with nonce-based or hash-based allow-lists.
     c. Replace inline styles with hash-based allow-lists.
     d. Switch `Content-Security-Policy-Report-Only` to enforcing
        `Content-Security-Policy` in nginx.conf (3 locations: server-level,
        /static/, /protected-media/).
     e. Keep the report-uri/report-to endpoint active for fallback monitoring.
  4. Success criteria: Zero CSP violations in Report-Only mode for 7 days
     before enforcing. Violations can be inspected via the csp_report view's
     INFO logging (see B7/B8).
  5. Owner, priority, and dependencies (depends on B7/B8 schema validation
     being reliable enough to distinguish real violations from noise).

description: >
  The CSP Report-Only policy (`nginx.conf:50-53`) was deployed as Phase 1
  with zero rollout risk. The `architecture-structure.md:325` doc notes
  Phase 2 as "deferred" but provides no tracking artifact, milestone, or
  migration plan. Without a tracked milestone, Phase 2 remains orphaned —
  the `unsafe-inline` directive (which exists specifically to accommodate
  current templates) may never be removed, leaving the site without enforcing
  CSP indefinitely.

  The CSP report schema validation (B7/B8) makes the `/csp-report/` endpoint
  reliable enough to distinguish real violations from noise — this is the
  gating prerequisite for Phase 2 enforcement.

goals:
  - Create `.ai/tracking/csp-phase2-enforcement.md` tracking milestone document
  - Document current state (Report-Only, unsafe-inline)
  - Define Phase 2 sub-tasks (audit inline sources, migrate to nonce/hash, switch to enforcing)
  - Define success criteria (7 days zero violations in Report-Only)
  - Reference B7/B8 as the gating prerequisite (reliable report ingestion)

files:
  - path: .ai/tracking/csp-phase2-enforcement.md
    targets:
      - type: document_root
        name: csp-phase2-enforcement

acceptance_criteria:
  - The tracking document exists at .ai/tracking/csp-phase2-enforcement.md
  - It documents the current Report-Only state with unsafe-inline
  - It defines Phase 2 sub-tasks (audit, nonce/hash migration, enforcing switch)
  - It states the 7-day zero-violation success criterion
  - It references B7/B8 (CSP report schema validation) as the gating prerequisite

required_tests:
  - None (documentation-only change, no code path affected)

implementation_sequence:
  1. Read nginx.conf:47-53 (CSP Report-Only server-level header)
  2. Read architecture-structure.md:324-325 (Phase 1/Phase 2 description)
  3. Read core/views.py:93-109 (csp_report view — referenced as the report receiver)
  4. Create .ai/tracking/csp-phase2-enforcement.md with the 5 required sections
  5. Verify the document is discoverable (linked from architecture-structure.md or referenced by B8)

architectural_constraints:
  - The tracking document is a planning artifact, not a code change — it creates no runtime impact
  - It must reference B7/B8 as gating prerequisites (schema-validated report ingestion is needed before trusting Report-Only data for Phase 2 migration)
  - It must NOT prescribe the exact nonce/hash migration approach — that is Phase 2's decision, to be worked out when Phase 2 begins

risks:
  - None (documentation-only)
  - Very Low: the tracking document may become stale if Phase 2 never begins — mitigation: link it from the audit phase instruction file (.kilo/commands/audit/phases/09-external-api.md) so it appears in future audits

agents:
  primary: docs-specialist
  reason: >
    09-EXT-02 is BEST-PRACTICE (documentation/tracking). The docs-specialist
    creates the tracking milestone document. No code, test, Researcher, or
    Auditor gate — the migration plan is Phase 2's responsibility, not this
    phase's implementation.
```

---

### Block B6 — 09-EXT-04a: nginx dedicated `location /csp-report/` with tighter rate limit

**Finding:** 09-EXT-04 (MEDIUM, BEST-PRACTICE, P2, Effort S)

**Status:** CONFIRMED not-yet-fixed. The `/csp-report/` endpoint is currently
handled by the catch-all `location /` block (`nginx.conf:146-153`) with the
`browse_limit` zone (`rate=20r/s, burst=40`). CSP violation reports should be
rate-limited more tightly (the finding recommends `login_limit` zone at
`rate=10r/s, burst=10`).

```yaml
id: b6_nginx_csp_report_location
title: Add dedicated nginx location block for /csp-report/ with login_limit rate zone
priority: medium
depends_on: []
source_reference: .ai/audit/99-validation/09-external-api-validated-findings.md
source_section: "09-EXT-04 (lines 51-57)"

task_description: >
  In `docker/nginx/nginx.conf`, insert a dedicated `location /csp-report/`
  block before the catch-all `location /` block (before line 146).

  The block must:
  - Use `limit_req zone=login_limit burst=10 nodelay;` (the login_limit zone
    is already defined at nginx.conf:24: `rate=10r/s`)
  - Proxy to the Django web service: `proxy_pass http://web:8000;`
  - Set standard proxy headers (Host, X-Real-IP, X-Forwarded-For,
    X-Forwarded-Proto) — matching the pattern in existing location blocks
  - NOT inherit the server-level CSP or HSTS headers (nginx `add_header`
    inheritance drops inherited headers when a location has its own
    add_header — but since this location has no add_header of its own,
    the server-level headers DO apply). No explicit re-declaration needed.

  Placement: before `location /` (nginx.conf:146) so it takes precedence
  over the catch-all. nginx matches longest-prefix, so `/csp-report/`
  naturally wins over `/` — but placing it first improves readability and
  follows the existing convention (location /login/, /search/, /health/,
  /moderation/ all appear before the catch-all).

description: >
  CSP violation reports can be volumetrically targeted — a malicious page
  could trigger millions of violations from a victim's browser, flooding the
  `/csp-report/` endpoint (a POST to a Django view with no DB write — just
  logging). The current catch-all `location /` uses `browse_limit`
  (`rate=20r/s, burst=40`) — generous for browsing but loose for reports.
  The finding recommends `login_limit` (`rate=10r/s`) with `burst=10` —
  tighter, appropriate for a low-volume monitoring endpoint.

  The `/csp-report/` URL is already wired in Django
  (`core/urls.py:14: path("csp-report/", views.csp_report, name="csp_report")`)
  and the nginx CSP header points to it (`nginx.conf:53: report-uri /csp-report/`).

goals:
  - Insert dedicated `location /csp-report/` block in nginx.conf before the catch-all `location /`
  - Use `limit_req zone=login_limit burst=10 nodelay;`
  - Standard proxy headers (Host, X-Real-IP, X-Forwarded-For, X-Forwarded-Proto)

files:
  - path: docker/nginx/nginx.conf
    targets:
      - type: location_block
        name: location /
        (insert_before this block)

acceptance_criteria:
  - A `location /csp-report/` block exists in nginx.conf before `location /`
  - It uses `limit_req zone=login_limit burst=10 nodelay;`
  - It proxies to `http://web:8000` with standard headers
  - `nginx -t` passes (syntax validation)
  - The existing `login_limit` zone (nginx.conf:24) is reused (no new zone defined)

required_tests:
  - test (structural): verify the location block and rate limit
    command: 'grep -A5 "location /csp-report/" docker/nginx/nginx.conf'
    expectation: matches the expected block with login_limit and burst=10
  - test (smoke): manual — `nginx -t` in the dev container
    command: '.\\Makefile.ps1 nginx-test  (or equivalent nginx -t)'
    expectation: configuration valid

implementation_sequence:
  1. Read nginx.conf:106-114 (location /login/ block as reference template)
  2. Read nginx.conf:145-153 (location / catch-all as insertion point)
  3. Insert the /csp-report/ block before location /
  4. Run `nginx -t` (syntax validation)

architectural_constraints:
  - The `login_limit` zone (nginx.conf:24: `zone=login_limit:10m rate=10r/s`) is already defined — do NOT re-define it
  - The /csp-report/ block must use the same `proxy_pass http://web:8000` + standard headers pattern as /login/ (nginx.conf:107-113)
  - This block is independent of B7 (view schema validation) — nginx rate limiting applies regardless of Django's validation logic
  - The CSP `report-uri /csp-report/` directive (nginx.conf:53) already points to this path

risks:
  - Low: if the rate limit is too tight, legitimate browsers under heavy load (e.g., a news site linking to the classifieds) could be blocked from reporting violations. `burst=10 nodelay` allows 10 immediate reports before 429s — acceptable for a classifieds site with moderate traffic.
  - Low: misplacement (after `location /` instead of before) — nginx longest-prefix-match handles this, but readability suffers.

agents:
  primary: Implementor
  reason: >
    B6 is a low-risk nginx config addition — a single location block reusing
    an existing rate-limit zone. No Researcher or Auditor gate. The structural
    test (grep + nginx -t) is straightforward.
```

---

### Block B7 — 09-EXT-04b: CSP report schema validation + INFO log level

**Finding:** 09-EXT-04 (MEDIUM, BEST-PRACTICE) — view portion

**Status:** CONFIRMED not-yet-fixed. `csp_report()` view (`core/views.py:93-109`)
accepts any JSON payload without schema validation, and logs at `WARNING` level
(`core/views.py:108`), which may trigger false-positive alerts since CSP
reports represent real browser activity, not errors.

```yaml
id: b7_csp_report_schema_validation
title: Add Pydantic schema validation and downgrade log level to INFO in csp_report view
priority: medium
depends_on: []
source_reference: .ai/audit/99-validation/09-external-api-validated-findings.md
source_section: "09-EXT-04 (lines 54-60)"

task_description: >
  In `src/backend/apps/core/views.py`, harden the `csp_report()` function
  (line 93) with two changes:

  1. Schema validation: After parsing JSON (line 105), validate the structure
     before logging. Define a minimal Pydantic v2 model:

     ```python
     class CSPReportPayload(BaseModel):
         model_config = ConfigDict(populate_by_name=True, extra="ignore")
         document_uri: str | None = Field(default=None, alias="document-uri")
         referrer: str | None = None
         violated_directive: str | None = Field(default=None, alias="violated-directive")
         blocked_uri: str | None = Field(default=None, alias="blocked-uri")
         original_policy: str | None = Field(default=None, alias="original-policy")
         status_code: int | str | None = Field(default=None, alias="status-code")
         source_file: str | None = Field(default=None, alias="source-file")
         line_number: int | None = Field(default=None, alias="line-number")
         column_number: int | None = Field(default=None, alias="column-number")
         disposition: str | None = None
     ```

     The top-level wrapper `{"csp-report": {...}}` is checked:
     ```python
     if not isinstance(report, dict) or "csp-report" not in report:
         return JsonResponse({"error": "Missing 'csp-report' key"}, status=400)
     ```
     Then validate the inner dict:
     ```python
     try:
         CSPReportPayload(**report["csp-report"])
     except ValidationError:
         return JsonResponse({"error": "Invalid CSP report schema"}, status=400)
     ```

     Alternative (simpler, no Pydantic): a dict-based structural check:
     ```python
     if not isinstance(report, dict) or not isinstance(report.get("csp-report"), dict):
         return JsonResponse({"error": "Invalid CSP report"}, status=400)
     ```
     Pydantic is the recommended approach (project convention — rule 11).

  2. Log level: Change `logger.warning("CSP violation report: %s", report)`
     (line 108) to `logger.info(...)`. CSP reports are expected operational
     data (browsers reporting real violations), not error conditions.

description: >
  The `csp_report()` view (`core/views.py:93-109`) accepts arbitrary JSON
  and logs it at WARNING level. Without schema validation, malformed or
  malicious payloads (non-dict, missing csp-report key, oversized bodies)
  are processed and logged, potentially filling disk via log spam. The
  WARNING level causes false-positive alerting — CSP reports are normal
  browser behavior, not application errors.

  The project uses Pydantic v2 extensively for boundary validation
  (`search/schemas.py`, `moderation/schemas.py`, `users/schemas.py`,
  `ads/services/listings_query.py`). A Pydantic model for CSP reports
  follows the established pattern and provides extensibility (future
  report-type discrimination, field extraction for querying).

  The W3C CSP Level 3 report format is:
  ```json
  {"csp-report": {"document-uri": "...", "referrer": "...",
  "violated-directive": "...", "blocked-uri": "...",
  "original-policy": "...", "status-code": 200, ...}}
  ```
  (Reporting API v1 uses `{"type": "csp-violation", "body": {...}}` but
  the current CSP header uses the legacy `report-uri` directive, so the
  `csp-report` format is what browsers send.)

goals:
  - Add Pydantic CSPReportPayload model (or dict-based validation) to core/views.py
  - Validate JSON body has `csp-report` dict key before processing
  - Return 400 on missing key or invalid schema
  - Change `logger.warning` → `logger.info` for the CSP report log line
  - Preserve existing behavior: 405 on non-POST, 400 on invalid JSON

files:
  - path: src/backend/apps/core/views.py
    targets:
      - type: function
        name: csp_report
      - type: module_level_class
        name: CSPReportPayload

acceptance_criteria:
  - csp_report() validates the request body has a dict-valued "csp-report" key
  - csp_report() returns 400 on missing "csp-report" key
  - csp_report() returns 400 on invalid schema (Pydantic ValidationError or dict check)
  - csp_report() returns 200 on valid CSP report (existing behavior preserved)
  - logger uses INFO level (not WARNING) for valid reports
  - 405 on non-POST, 400 on invalid JSON (existing behavior preserved)
  - ruff check + basedpyright pass on views.py

implementation_sequence:
  1. Read csp_report() function (core/views.py:93-109)
  2. Add Pydantic import (BaseModel, ConfigDict, Field, ValidationError) to views.py
  3. Define CSPReportPayload model
  4. Insert schema validation after json.loads (line 105)
  5. Change logger.warning → logger.info (line 108)
  6. Run ruff + basedpyright on views.py
  7. (After B8) Run test_csp_report.py

architectural_constraints:
  - The Pydantic model goes in `core/views.py` (same file as csp_report) — no new module needed (single-responsibility: the model is only used by this view)
  - The CSP report format uses hyphenated keys ("document-uri", "violated-directive") — Pydantic aliases (`alias="..."`) handle this
  - `extra="ignore"` on the model config allows browsers to send additional fields without failing validation (CSP spec may add fields)
  - The existing test_csp_report.py sends `{"csp-report": {"violated-directive": "script-src"}}` — this is a valid minimal report (all fields optional). The existing `test_post_valid_report_returns_200` should continue to pass.
  - The model uses `from __future__ import annotations` (views.py should already have this or use `|` union syntax)
  - The view must NOT persist reports to the DB — just validate and log (no model change, no migration)

risks:
  - Low: Pydantic ValidationError on a field that the existing test sends as a different type (e.g., status-code as string). The model allows `int | str | None` for status_code to handle this.
  - Low: the existing test `test_post_valid_report_returns_200` sends a minimal report (only `violated-directive`). If the Pydantic model makes `document-uri` required, the test breaks. The model must make ALL fields optional (default=None) so the minimal report validates.
  - Very Low: the INFO log level change may reduce visibility in monitoring dashboards that alert on WARNING. This is the intended behavior change — CSP reports are not errors.

required_tests:
  - Existing: test_csp_report.py tests must still pass (with updates in B8)
  - New (B8): test_post_invalid_schema_returns_400, test_post_missing_csp_report_key_returns_400, test_info_log_level

agents:
  primary: Implementor
  secondary: Validator
  reason: >
    B7 is a code change to the csp_report view. A Validator gate (B8) writes
    and runs the schema-validation tests. No Researcher gate — the CSP report
    format is a stable W3C spec. No Auditor gate — the change is additive
    (validation returns 400 on invalid input; valid input is unaffected).
```

---

### Block B8 — 09-EXT-04c: Update CSP report tests for schema validation + log level

**Finding:** 09-EXT-04 (MEDIUM, BEST-PRACTICE) — test portion

**Status:** CONFIRMED not-yet-fixed. `test_csp_report.py` has 3 tests but none
verify schema validation (the view currently accepts any JSON). After B7 adds
validation, the existing tests must be preserved and new tests added.

```yaml
id: b8_update_csp_report_tests
title: Add schema validation tests and log-level assertion to test_csp_report.py
priority: medium
depends_on: [b7_csp_report_schema_validation]
source_reference: .ai/audit/99-validation/09-external-api-validated-findings.md
source_section: "09-EXT-04 (lines 58-60)"

task_description: >
  In `src/backend/apps/core/tests/test_csp_report.py`, add tests that verify
  the schema validation and log-level change introduced by B7.

  Preserve all 3 existing tests (they test the 405/200/400-JSON paths, which
  B7 does not change). Add:

  1. `test_post_missing_csp_report_key_returns_400`:
     Send `{"some-other-key": "value"}` → assert 400.
     Send `{}` (empty dict) → assert 400.

  2. `test_post_non_dict_csp_report_value_returns_400`:
     Send `{"csp-report": "not-a-dict"}` → assert 400.
     Send `{"csp-report": ["array"]}` → assert 400.

  3. `test_post_valid_report_logs_at_info_level` (uses caplog):
     Send a valid minimal CSP report → assert 200, and verify the log
     record level is INFO (not WARNING).

  4. `test_post_valid_report_with_all_fields_returns_200`:
     Send a complete CSP report (document-uri, referrer, violated-directive,
     blocked-uri, original-policy) → assert 200. Verifies the Pydantic model
     accepts all standard CSP fields.

description: >
  The existing `test_csp_report.py` has 3 tests:
  - `test_get_returns_405` (non-POST → 405)
  - `test_post_valid_report_returns_200` (valid JSON with csp-report key → 200)
  - `test_post_invalid_json_returns_400` (malformed JSON → 400)

  After B7, a new validation layer is inserted between JSON parsing and logging.
  The existing tests should continue to pass (the minimal report
  `{"csp-report": {"violated-directive": "script-src"}}` is a valid CSP
  report — all fields optional). But if the Pydantic model makes any field
  required, the existing `test_post_valid_report_returns_200` would break.
  B7's `acceptance_criteria` requires all fields optional precisely to
  preserve this test.

  The new tests verify the validation actually works (rejects malformed
  structure) and that the log-level change is real.

goals:
  - Preserve 3 existing tests unchanged
  - Add test: missing `csp-report` key → 400
  - Add test: `csp-report` value not a dict → 400
  - Add test: valid report logged at INFO level (caplog)
  - Add test: valid report with all standard CSP fields → 200

files:
  - path: src/backend/apps/core/tests/test_csp_report.py
    targets:
      - type: class
        name: TestCSPReport
        (new class for validation tests — or module-level functions matching existing pattern)

acceptance_criteria:
  - All 3 existing tests pass unchanged
  - `test_post_missing_csp_report_key_returns_400` passes
  - `test_post_non_dict_csp_report_value_returns_400` passes
  - `test_post_valid_report_logs_at_info_level` passes (caplog asserts INFO, not WARNING)
  - `test_post_valid_report_with_all_fields_returns_200` passes

required_tests:
  - test: full csp_report test suite
    command: '$dc run --rm -e PYTEST_OPTS="src/backend/apps/core/tests/test_csp_report.py --tb=short" test'
    expectation: all tests pass (3 existing + 4 new = 7)

implementation_sequence:
  1. Apply B7 code change first (Implementor)
  2. Add the 4 new test functions
  3. Run the full test_csp_report.py suite
  4. If any existing test fails, B7's model config is too strict — adjust extra="ignore" / defaults

architectural_constraints:
  - The test file uses `pytest.mark.unit` (no DB) — the schema validation is pure Python, no DB needed
  - `caplog` fixture is available (pytest built-in) — use `caplog.at_level(logging.INFO, logger="apps.core.views")`
  - The existing test pattern uses module-level functions (not classes) — follow this convention
  - The test uses `django.test.Client` + `reverse("core:csp_report")` — preserve this pattern
  - JSON body must be `.encode()` to bytes and sent with `content_type="application/json"` (matching existing pattern)

risks:
  - Low: if the Pydantic model in B7 makes any field required, `test_post_invalid_json_returns_400` (which sends `{"csp-report": {"violated-directive": "script-src"}}`) would break — B7's acceptance criteria prevent this
  - Low: caplog may not capture INFO logs if the logger propagates differently — use `caplog.at_level(logging.INFO)` which is the pytest-recommended pattern

agents:
  primary: Validator
  reason: >
    B8 is a test-only update that verifies B7's schema validation and log-level
    change. The Validator writes the assertions and runs them. The test will
    fail on B7-unfixed code (no 400 on missing key; WARNING log level), proving
    it catches the regression. No Researcher gate — the CSP report format is a
    stable W3C spec. No Auditor gate — tests are additive.
```

---

### Block B9 — 09-EXT-07: Secret rotation procedures for `BOT_TOKEN` and `GOOGLE_TRANSLATE_API_KEY`

**Finding:** 09-EXT-07 (LOW, DOC-UPDATE, P1, Effort XS)

**Status:** CONFIRMED not-yet-fixed. `docs/ops/docker-deployment.md` documents
`DJANGO_SECRET_KEY` rotation (line 328) but has no procedure for
`BOT_TOKEN` or `GOOGLE_TRANSLATE_API_KEY` — both are required production secrets
(`base.py:71`, `prod.py:101-113`). Additionally, `GOOGLE_TRANSLATE_API_KEY` is
completely absent from the Environment Variables table (line 326-348).

```yaml
id: b9_secret_rotation_docs
title: Add BOT_TOKEN and GOOGLE_TRANSLATE_API_KEY rotation procedures + env var table entry
priority: low
depends_on: []
source_reference: .ai/audit/99-validation/09-external-api-validated-findings.md
source_section: "09-EXT-07 (lines 194-201)"

task_description: >
  In `docs/ops/docker-deployment.md`, make two documentation changes:

  1. Add `GOOGLE_TRANSLATE_API_KEY` to the Environment Variables table
     (currently between `REDIS_URL` at line 340 and `PLAUSIBLE_HOST` at line 341,
     alphabetical order by variable name). Entry:
     | `GOOGLE_TRANSLATE_API_KEY` | Yes (prod) | Google Cloud Translation API v2 key used by `apps.core.services.translation.translate_text()`. Required in production (prod.py:109 fail-fast guard). Empty in `.env.dev` (dummy key: `dev-only-dummy-key-not-for-production`). Rotate if committed to VCS or exposed. After rotation, restart the `bot` container — the translation service lazily imports the key at call time via `settings.GOOGLE_TRANSLATE_API_KEY`. |

  2. Add rotation procedure for `BOT_TOKEN` and `GOOGLE_TRANSLATE_API_KEY`
     following the `DJANGO_SECRET_KEY` format (line 328, which reads:
     "Rotate this key if it may have been committed to VCS or exposed. ...
     After rotation, restart the web and bot containers together").

     For `BOT_TOKEN` (insert after the DJANGO_SECRET_KEY row, line 328 — it's
     already in the table at line 330 but without rotation guidance):
     Update the BOT_TOKEN description to add: "Rotate if compromised: get a
     new token from @BotFather, update `BOT_TOKEN` in `.env.prod`, then
     `docker compose ... up -d bot`. This project uses long-polling (not
     webhooks), so no Telegram-side URL reconfiguration is needed. After
     rotation, the old token is immediately invalidated."

     For `GOOGLE_TRANSLATE_API_KEY` (insert into the table, not yet present):
     Include the rotation note in its table entry (described above in change 1)
     AND add a dedicated "Rotating Secrets" subsection after the Environment
     Variables table (after line 353) that references both tokens. This
     subsection mirrors the DJANGO_SECRET_KEY inline guidance.

description: >
  The Environment Variables table (`docker-deployment.md:326-348`) documents
  `DJANGO_SECRET_KEY` (line 328) with rotation guidance, `BOT_TOKEN` (line 330)
  with no rotation guidance, and `REDIS_URL` (line 340). `GOOGLE_TRANSLATE_API_KEY`
  is completely absent despite being a required production secret
  (`prod.py:107-113`: `ImproperlyConfigured` if empty in production).

  Both `BOT_TOKEN` (Telegram impersonation risk) and `GOOGLE_TRANSLATE_API_KEY`
  (quota/billing abuse risk) have the same fail-fast guard pattern as
  `DJANGO_SECRET_KEY` — `prod.py:101-105` and `prod.py:109-113`.

  The `DJANGO_SECRET_KEY` entry (line 328) sets the doc precedent: inline
  rotation guidance + impact description. The B9 change follows this pattern.

goals:
  - Add `GOOGLE_TRANSLATE_API_KEY` row to the Environment Variables table (alphabetical, after REDIS_URL, before PLAUSIBLE_HOST)
  - Add rotation guidance to the `BOT_TOKEN` row (line 330) — update the description text
  - Add a "Rotating Secrets" subsection after the Environment Variables table documenting the BOT_TOKEN and GOOGLE_TRANSLATE_API_KEY rotation procedures
  - Reference the impact (token invalidation, container restart) and the no-webhook-reconfiguration note for BOT_TOKEN

files:
  - path: docs/ops/docker-deployment.md
    targets:
      - type: table_row
        name: DJANGO_SECRET_KEY
        (reference format)
      - type: table_row
        name: BOT_TOKEN
        (add rotation guidance to description)
      - type: table_row
        name: REDIS_URL
        (anchor for GOOGLE_TRANSLATE_API_KEY insertion point)

implementation_sequence:
  1. Read the Environment Variables table (lines 326-353)
  2. Read the DJANGO_SECRET_KEY row (line 328) as the format template
  3. Add GOOGLE_TRANSLATE_API_KEY row (after REDIS_URL, line 340)
  4. Update BOT_TOKEN row (line 330) description with rotation guidance
  5. Add "Rotating Secrets" subsection after line 353
  6. Verify the Rate Limiting table (line 584) does not need a /csp-report/ entry — that is B6's structural test's concern, not a doc change

architectural_constraints:
  - Follow the exact format of the DJANGO_SECRET_KEY row (line 328) for rotation guidance
  - BOT_TOKEN already exists in the table (line 330) — B9 updates its description column in-place (does not add a new row)
  - GOOGLE_TRANSLATE_API_KEY does NOT exist in the table — B9 adds a new row
  - The rotation procedure for BOT_TOKEN: "new token from @BotFather → update .env.prod → restart bot container" because this project uses long-polling (main.py uses `run_polling`, not webhooks) — no Telegram webhook URL reconfiguration needed
  - GOOGLE_TRANSLATE_API_KEY is read at call time via `settings.GOOGLE_TRANSLATE_API_KEY` (translation.py:134) — lazy, so a container restart picks up the new key (no code change needed for rotation)

acceptance_criteria:
  - GOOGLE_TRANSLATE_API_KEY row exists in the Environment Variables table
  - BOT_TOKEN row includes rotation guidance ("Rotate if compromised: get a new token from @BotFather...")
  - A "Rotating Secrets" subsection exists after the table
  - The DJANGO_SECRET_KEY row is used as the format reference (unchanged)
  - No code changes (documentation-only)

required_tests:
  - None (doc-only change)
  - Verify: no string changes in .po files (no i18n impact)

agents:
  primary: docs-specialist
  reason: >
    09-EXT-07 is a DOC-UPDATE finding. Both changes are documentation edits
    to docker-deployment.md. No code, test, Researcher, or Auditor gate.
```

---

## 5. Implementation Constraints

1. **No migrations** — six of six findings involve runtime code changes (function call, settings default, view validation), nginx config, or documentation. No schema, index, constraint, or data changes.

2. **09-EXT-01 import path consistency** — The backfill's `_translate_for_backfill` wrapper must import `translate_text` from `apps.core.services.translation` (the defining module), NOT from `apps.core.services` (the package `__init__.py`). The test patch target (`apps.core.services.translation.translate_text`) must match the import path in the code, because `patch()` replaces the attribute on the module where it is *looked up*. Both paths resolve to the same function, but the lazy-import-in-function-body pattern means the backfill re-reads the module attribute on every call — patching `apps.core.services.translation.translate_text` intercepts each call.

3. **09-EXT-01 naming collision** — The wrapper MUST be renamed away from `_translate_text` so it does not shadow or confuse future imports of the public `translate_text`. The name `_translate_for_backfill` is descriptive of single responsibility (rule 4).

4. **09-EXT-03 dual HSTS source** — nginx is the TLS terminator and emits HSTS server-side. Django's `SecurityMiddleware` (base.py:148) ALSO emits HSTS because `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` (base.py:101) makes Django treat proxied requests as secure. Any path that suppresses nginx's header must ensure Django's header covers the same URLs. The `internal` location `/protected-media/` (nginx.conf:88-104) is served by nginx directly (not proxied to Django) — Path B requires re-adding HSTS to this location.

5. **09-EXT-03 preload list eligibility** — The `preload` directive is only meaningful if the site is submitted to the HSTS preload list
   (hstspreload.org). Submission requires: valid cert on ALL subdomains,
   no `www` redirect chain, no cross-origin resources. The production
   topology (Cloudflare/ALB) must be verified before `preload` is added
   (Path A) or before claiming Django's `SECURE_HSTS_PRELOAD = True` is
   sufficient (Path B). This is the B4 Researcher gate.

6. **09-EXT-04 Pydantic model in views.py** — The CSP report schema model goes
   in `core/views.py` (same file as `csp_report`), not a new `schemas.py`
   module. This is justified by single-responsibility: the model is used by
   exactly one view and has no other consumers. If a future phase adds
   report querying/persistence, a `schemas.py` module can be extracted then.

7. **09-EXT-04 existing test compatibility** — The Pydantic model must make
   ALL fields optional (`default=None`) so the existing
   `test_post_valid_report_returns_200` (which sends a 1-field report:
   `{"csp-report": {"violated-directive": "script-src"}}`) continues to pass
   without modification.

8. **09-EXT-05 REDIS_URL consumers** — The empty-string default is already
   handled by all consumers (verified via grep):
   - `telegram_bot/main.py:53`: `redis_url = getattr(settings, "REDIS_URL", "") or ""` — empty → MemoryStorage
   - `base.py:290`: `CACHES["default"]["LOCATION"] = REDIS_URL` — overridden to
     `LocMemCache` in `dev.py:40` and `test.py:59`
   - `prod.py` does NOT override `REDIS_URL` — production always sets the env
     var (`REDIS_URL=redis://redis:6379/0` in `.env.prod`)

9. **09-EXT-01 bot vs backfill source locale** — The bot path (`ad_data.py:307`)
   calls `translate_text(text, "auto", loc)` with `"auto"` source (real-time
   user input of unknown language). The backfill translates existing Russian
   ads and MUST use `"ru"` as the source locale. These are different code paths
   and must not be conflated.

10. **09-EXT-04 nginx location ordering** — The `/csp-report/` location
    (B6) uses longest-prefix matching, so it naturally wins over the
    catch-all `location /`. However, the existing convention places
    rate-limited locations (login, search, health, moderation) before the
    catch-all. B6 follows this convention for readability and to match
    the existing structural pattern.

11. **09-EXT-04 `login_limit` zone reuse** — The `login_limit` zone
    (nginx.conf:24: `zone=login_limit:10m rate=10r/s`) is defined in the
    `http` block and is already used by `location /login/`. B6 reuses it
    for `/csp-report/` — no new zone definition. If the team later wants
    a separate zone, that is a future change.

---

## 6. Test Strategy

### 6.1 Existing Test Coverage (Must Preserve)

| Test File | Test | What It Verifies | Status after fix |
|-----------|------|-----------------|------------------|
| `test_backfill_translations.py::TestBackfillTranslations::test_translates_ads_with_null_fields` | Null fields get translated, 4 calls, original_language set | Must still pass (after B2 updates patch target) |
| `test_backfill_translations.py::...::test_idempotent_when_all_translations_present` | Already-translated skips translation | Must still pass |
| `test_backfill_translations.py::...::test_no_ads_succeeds` | No-op when no ads | Must still pass |
| `test_backfill_translations.py::...::test_translation_failure_skips_gracefully` | None-on-failure → fields stay NULL | **Must be rewritten** (B2) — translate_text returns original text, not None |
| `test_csp_report.py::test_get_returns_405` | Non-POST → 405 | Must still pass (B7 doesn't change method check) |
| `test_csp_report.py::test_post_valid_report_returns_200` | Valid JSON → 200 | Must still pass (B7 schema must accept minimal report) |
| `test_csp_report.py::test_post_invalid_json_returns_400` | Malformed JSON → 400 | Must still pass (B7 doesn't change JSON parsing) |
| `test_translation.py` (12 tests) | Circuit breaker + translate_text retry/fallback | Must still pass (B1 doesn't change translate_text itself) |
| `test_csp_report.py` (3 existing tests) | All pass | Must still pass after B7+B8 |

### 6.2 New Regression Tests

| Test | Finding | Block | File | What It Verifies |
|------|---------|-------|------|-----------------|
| `test_uses_translate_text_not_raw_api` | 09-EXT-01 | B2 | `test_backfill_translations.py` | Patching `translate_text` at module level intercepts calls (proving backfill uses the circuit-breaker entry point, not `translate_cached_generic` directly) |
| `test_redis_url_defaults_empty` | 09-EXT-05 | B3 | `test_settings_defaults.py` (new) | REDIS_URL defaults to `""` when env unset |
| `test_post_missing_csp_report_key_returns_400` | 09-EXT-04 | B8 | `test_csp_report.py` | Missing `csp-report` key → 400 |
| `test_post_non_dict_csp_report_value_returns_400` | 09-EXT-04 | B8 | `test_csp_report.py` | `{"csp-report": "string"}` → 400 |
| `test_post_valid_report_logs_at_info_level` | 09-EXT-04 | B8 | `test_csp_report.py` | Log level is INFO (not WARNING) |
| `test_post_valid_report_with_all_fields_returns_200` | 09-EXT-04 | B8 | `test_csp_report.py` | Complete CSP report accepts all standard fields |

### 6.3 Test Execution Commands

```powershell
# Alias (copy once)
$dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'

# B1+B2 — backfill translation tests (code then test)
$dc run --rm -e PYTEST_OPTS="src/backend/apps/ads/tests/test_backfill_translations.py src/backend/apps/core/tests/test_translation.py --tb=short" test

# B3 — REDIS_URL default test (after adding to test_settings_defaults.py)
$dc run --rm -e PYTEST_OPTS="src/backend/config/settings/tests/ --tb=short" test

# B4 — nginx syntax validation (structural)
# Run inside dev container:
docker compose --project-name mko-bazuna-dev run --rm --entrypoint "" web nginx -t

# B6 — nginx csp-report structural (grep)
grep -A5 "location /csp-report/" docker/nginx/nginx.conf

# B7+B8 — CSP report tests
$dc run --rm -e PYTEST_OPTS="src/backend/apps/core/tests/test_csp_report.py --tb=short" test

# FULL fast gate (all affected: backfill, translation, csp, settings)
$dc run --rm --env PYTEST_SKIP_MARKERS=seed test
```

---

## 7. Decision Points (Open)

| Decision | Options | Recommendation | Who Decides | Block |
|----------|---------|----------------|-------------|-------|
| D1: 09-EXT-01 fallback semantics | (A) Store original text on failure (consistent with bot path `ad_data.py:322`) — `if translated is not None` becomes always-true, remove the check; (B) Compare `translate_text` result to original — if equal, skip field (preserve NULL-on-failure) | (A) — consistency with the bot path is more important than preserving NULL semantics. The "degraded recall" impact (Russian text in EN/BS fields) is already the bot path's behavior. If NULL-on-failure is critical, B can be implemented with a comparison check. | Implementor (with team input on recall vs. consistency) | B1 |
| D2: 09-EXT-03 HSTS approach | (A) Add `preload` to all 3 nginx HSTS directives; requires preload-list eligibility check; (B) Add `proxy_hide_header Strict-Transport-Security` + remove 3 nginx HSTS add_headers, let Django (with `SECURE_HSTS_PRELOAD=True`) be the sole source — requires /protected-media/ HSTS handling | **(A) — Path B is structurally flawed**: `proxy_hide_header` suppresses the *upstream (Django)* HSTS header, not nginx's own `add_header`. Removing all 3 nginx HSTS add_headers + adding `proxy_hide_header` = zero HSTS on all responses. Path A (add `; preload` to all 3 directives) is simpler, preserves all existing HSTS behavior, and avoids the `/protected-media/` internal-location edge case entirely. | Implementor | B4 |
| D3: 09-EXT-04 schema validation approach | (A) Pydantic v2 model (project convention, rule 11) with `extra="ignore"` and all-optional fields; (B) Dict-based structural check (simpler, no new model) | (A) — Pydantic is the established pattern (`search/schemas.py`, `moderation/schemas.py`, `users/schemas.py`). Provides extensibility for future report querying. | Implementor | B7 |

**Researcher gates:**
- D1: The Researcher should verify whether the bot path (`ad_data.py:307-322`) consistently stores original text on failure — if so, Path A (consistency) is the right default. The existing `test_multi_lang_translation.py` and `test_translation.py` test the bot path's behavior.
- D2: The Researcher should verify HSTS preload list eligibility against the production topology (Cloudflare/ALB) — specifically whether all subdomains have valid certs and there's no `www` redirect chain. If Path A is chosen, the Researcher confirms the site qualifies; if Path B is chosen, the Researcher confirms /protected-media/ internal location coverage.

---

## 8. Agent Assignment Matrix

| Block | Primary | Researcher Gate | Auditor Gate | Validator Gate | Reason |
|-------|---------|----------------|-------------|----------------|--------|
| B1 | Implementor | D1: fallback semantics (NULL vs original-text) | Verify import path + naming collision resolution | — | HIGH/P1. Spec deviation in translation service usage. D1 is an architectural decision with cross-language recall impact. |
| B2 | Validator | — | — | Self (writes tests) | Test-only block. Verifies B1. |
| B3 | Implementor | — | — | Validator (writes default test) | LOW/P1. Trivial settings default. Validator confirms via test. |
| B4 | Implementor | D2: HSTS preload eligibility | Verify no dual HSTS headers after chosen path | — | MEDIUM/P1. nginx config change affecting all HTTPS responses. D2 impacts infrastructure. |
| B5 | docs-specialist | — | — | — | DOC-UPDATE. Tracking document creation only. |
| B6 | Implementor | — | — | — | LOW/P2. nginx location block, reuses existing zone. Structural test (grep + nginx -t). |
| B7 | Implementor | — | — | Validator (writes schema tests) | MEDIUM/P2. View code change. D3 (Pydantic vs dict) — low ambiguity, project convention dictates Pydantic. |
| B8 | Validator | — | — | Self (writes tests) | Test-only. Verifies B7. |
| B9 | docs-specialist | — | — | — | DOC-UPDATE. Documentation edits only. |

**Auditor gate checklist (B1, B4):**
- B1: Confirm `translate_text` is imported from `apps.core.services.translation` (the defining module, matching the test patch target). Confirm the wrapper is renamed and `httpx` import + inner try/except are fully removed. Confirm the source locale is `"ru"` (not `"auto"`).
- B4: If Path A, confirm all 3 HSTS directives include `preload` (no inconsistency). If Path B, confirm `proxy_hide_header` is placed inside the `server { listen 443 }` block and /protected-media/ has HSTS re-added.

**Researcher gate checklist (B1, B4):**
- B1 (D1): Verify `ad_data.py:322` (`translated[loc] = text`) — the bot stores original text on failure. Confirm `test_translation.py::test_translate_text_fallback_on_error` asserts `result == original`. Recommend Path A if consistency is preferred.
- B4 (D2): Query the production infrastructure — does the domain qualify for HSTS preload list (valid cert on all subdomains, no www redirect chain)? If Path B, verify which nginx `internal`/non-proxied locations exist (only /protected-media/) and whether Django's SecurityMiddleware covers all proxied locations.

**Validator gate checklist (B3, B7, B8):**
- B3: Test asserts `REDIS_URL == ""` when env unset, using subprocess isolation (matching `test_settings_secrets.py` pattern).
- B7: Test asserts 400 on missing `csp-report` key, 400 on non-dict value, 200 on valid minimal report, INFO log level.
- B8: Same as B7 (B7 and B8 are co-implemented; the Validator writes B8's tests as part of B7's verification).

---

## 9. Rollback Plan

All changes are confined to 2 production source files (`backfill_translations.py`,
`core/views.py`), 1 settings file (`base.py`), 1 nginx config (`nginx.conf`),
2 test files (`test_backfill_translations.py`, `test_csp_report.py`), 1 new
test file (`test_settings_defaults.py`), 1 new tracking doc, 1 existing doc
(`docker-deployment.md`). No migrations or schema changes.

| Block | Rollback Action |
|-------|-----------------|
| B1 | Revert `translate_text` → `translate_cached_generic` import + call; restore `httpx` import + inner try/except; restore `_translate_text` name; revert per-field skip logic to `is not None` check |
| B2 | Revert `_TRANSLATE_PATCH` to `translate_cached_generic`; delete `test_uses_translate_text_not_raw_api`; restore original `test_translation_failure_skips_gracefully` semantics |
| B3 | Revert `REDIS_URL` default from `""` to `"redis://localhost:6379/0"`; delete `test_settings_defaults.py` |
| B4 (Path A) | Revert `; preload` additions on all 3 HSTS directives |
| B4 (Path B) | Remove `proxy_hide_header Strict-Transport-Security;`; restore 3 HSTS `add_header` directives |
| B5 | Delete `.ai/tracking/csp-phase2-enforcement.md` |
| B6 | Remove the `location /csp-report/` block |
| B7 | Remove `CSPReportPayload` model; remove schema validation; revert `logger.info` → `logger.warning` |
| B8 | Delete the 4 new tests; restore original 3-test state |
| B9 | Revert BOT_TOKEN row description; remove GOOGLE_TRANSLATE_API_KEY row; delete "Rotating Secrets" subsection |

**B1 + B2 atomic rollback:** The wrapper rename + import change (B1) and
the test patch target change (B2) are complementary — the tests cannot mock
the old symbol if the code uses the new one. Revert both together.

**B7 + B8 atomic rollback:** The schema validation (B7) and its tests (B8)
are complementary — B8's tests assert 400 on missing keys, which requires
B7's validation. Revert both together.

**B4 + B5 coordination:** B4 (nginx HSTS) and B5 (CSP tracking doc) are
documentation/config only — B5 references B4's HSTS state. If B4 is rolled
back, B5's tracking doc should be annotated with the rollback status.

**No data migration:** All changes are runtime code (function call, settings
default, view validation), nginx config, or documentation. No schema, index,
or constraint modifications. Existing ad rows, translation cache entries,
search vectors, cache entries, and user data are unaffected.

---

## 10. Advisory Recommendations (Out of Scope for This Phase)

These are noted for future work but are explicitly out of scope for Plan 28:

1. **HSTS preload list submission** (09-EXT-03 Path B) — After choosing Path B
   (proxy_hide_header + Django HSTS), the team may submit the domain to the
   HSTS preload list (hstspreload.org). This requires: valid cert on ALL
   subdomains, `preload` in the HSTS header (Django's `SECURE_HSTS_PRELOAD=True`
   provides this), and submission via the web form. The submission + DNS
   verification process is a manual operations task, not a code change.

2. **CSP Phase 2 enforcement** (09-EXT-02/B5) — The actual migration from
   Report-Only to enforcing CSP, plus the `unsafe-inline` removal, is a
   separate phase with its own implementation plan. B5 creates the tracking
   milestone; the execution is deferred.

3. **CSP violation report querying** (09-EXT-04/B7) — A future phase could
   persist CSP reports to a database table and build a dashboard for
   violation analysis. This would require a new model, migration, and
   admin interface. B7's Pydantic model is designed for forward-compatibility
   (extra="ignore", all fields optional).

4. **Bot token rotation automation** (09-EXT-07/B9) — A future phase could
   add a management command to rotate `BOT_TOKEN` via the Telegram Bot API
   (`setWebhook`/`getMe` validation). The current project uses long-polling
   (no webhook reconfiguration needed), so manual rotation is simpler. B9
   documents the manual procedure.
