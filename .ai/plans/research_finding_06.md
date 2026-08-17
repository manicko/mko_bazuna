# Research: Finding 05 + 06 — Translator Consolidation

**Finding IDs:** 05 (MEDIUM), 06 (MEDIUM)
**Researcher:** task `ses_ff011f9f5ffevvenL4hp4qLwdq`
**Date:** 2026-08-17

---

## Current State

### Bot-side translator (`src/telegram_bot/handlers/ad_create.py`)
- `translate_all_languages(text, target_locales)` (line 798): async, uses `asyncio.gather` of `translate_one` which calls `asyncio.to_thread(_do_translate_to, text, target)` wrapped in `asyncio.wait_for(..., timeout=15.0)` with bare `except Exception: return text`.
- No circuit breaker, no caching, 15s timeout (spec violation — spec mandates ~500ms).
- `_do_translate_to(text, target)` (line 792): synchronous `GoogleTranslator(source="auto", target=target).translate(text)` wrapper. Only caller is `translate_all_languages`.
- Call site: `process_preview`, `confirm` branch (lines 942-954): `translate_all_languages(original_title, ["ru", "bs", "en"])`.
- Test coverage: `test_multi_lang_translation.py` (8 tests) mocks `ad_create._do_translate_to`. `test_ad_create.py` patches whole `translate_all_languages`.

### Search-side translator (`src/backend/apps/search/services/query_translator.py`)
- `TranslationCircuitBreaker` class (lines 29-83): 3 failures → open, 60s cooldown, half-open recovery.
- `_CIRCUIT_BREAKER` singleton (line 83), `_EXECUTOR = ThreadPoolExecutor(max_workers=1)` (line 22).
- `TRANSLATION_TIMEOUT_SECONDS = 0.5` (line 26).
- `translate_cached` (lru 128, bs→ru) (line 128), `translate_cached_generic` (lru 256) (line 151).
- `translate_query(text, source_locale, target_locale)` (line 170): circuit-breaker open check → executor.submit().result(timeout=0.5) → record success/failure → graceful fallback.
- `invalidate_translation_cache()` (line 146).
- Call sites: `search/views/search.py:95` (`translate_query`), `search/services/alert_query.py:50` (`translate_query_bs_to_ru`).
- Test coverage: `test_query_translator.py` (7 tests) imports `_CIRCUIT_BREAKER`, `translate_cached`, `translate_query_bs_to_ru`; patches `apps.search.services.query_translator.GoogleTranslator.translate`.

### Architectural context
- Two processes, one DB: gunicorn WSGI web (3 workers) + aiogram bot. Both call `django.setup()`.
- Dependency direction: bot → backend apps (established). Reverse (backend → bot) is forbidden.
- Spec: `technical-specification.md:106` — bot must translate using deep-translator + parallel asyncio.gather.
- `StrEnum` `LanguageLocale` (RUSSIAN/BOSNIAN/ENGLISH) exists in `core/enums.py:160`.

---

## Alternatives

| Alt | Description | Verdict |
|-----|-------------|---------|
| a | Harden bot-only: add circuit breaker + reduce timeout 15s→500ms + add LRU cache to `translate_all_languages`. Leave `query_translator.py` untouched. | Addresses Finding 05 symptom only. Does NOT resolve Finding 06's core complaint (two divergent implementations). Perpetuates two breaker/cache/timeout trios. |
| b | Create a shared `TranslationService` class both call into. | Introduces a class-based service pattern that exists nowhere in the codebase. Violates "follow existing patterns" / "avoid overengineering". |
| c | **SELECTED** — Relocate translator to `apps/core/services/translation.py`. Bot imports `translate_text` via `asyncio.to_thread` + `asyncio.gather`. Search-side `query_translator.py` becomes thin re-export shim. | Eliminates duplication. Reuses well-tested breaker/timeout/cache. Follows module-level-singleton pattern. Bot→`apps.core` is established import direction. |
| d | Bot imports only `TranslationCircuitBreaker` class; self-implements translate+timeout+cache. | Still two translate implementations. Partial dedup. |
| e | Async-native translator (aiohttp/httpx to real API). | Rejected: new dependency, no free async endpoint. |
| f | Put translator in `telegram_bot/services/`; search imports it. | Rejected: inverts dependency direction (backend → bot). |
| g | Retries/backoff instead of circuit breaker. | Rejected: no cache, no hard latency bound, doesn't address structural divergence. |

## Evaluation Matrix

| Alt | Correctness | Architecture Fit | Maintainability | Rollout Risk | Rollback |
|-----|------------|-----------------|-----------------|-------------|----------|
| a | Med | Med | Med | Low | High |
| b | High | Low (new pattern) | Med | Med | Med |
| **c** | **High** | **High** | **High** | **Med** | **High** |
| d | Med | Med | Med | Low-Med | High |
| f | Low | Low (wrong direction) | Low | Med | Med |

## Selected Solution: Alternative (c)

### Rationale
Finding 06's complaint is specifically that two translators have "vastly different resilience profiles." Alternative (a) mitigates the bot but leaves two implementations — doesn't resolve finding 06. Alternative (c) eliminates duplication while reusing the battle-tested search-side breaker/timeout/cache, preserving the spec-mandated parallel `asyncio.gather` on the bot side.

### Key design decision: `_EXECUTOR` max_workers
Current: `max_workers=1`. Recommendation: bump to `max_workers=4` so the bot's 3-locale parallel `asyncio.gather` + `asyncio.to_thread(translate_text, ...)` doesn't serialize (~3×500ms = 1.5s worst case with 1 worker; ~500ms with 4 workers).

### Test compatibility
The re-export shim in `query_translator.py` imports `GoogleTranslator` into its namespace. The test patches `apps.search.services.query_translator.GoogleTranslator.translate` — since `GoogleTranslator` is a class, patching its `translate` method affects all instances regardless of which module imported the class. `_CIRCUIT_BREAKER` and `translate_cached` are the same objects (re-exported references), so direct attribute access in tests works.

### Files changed
- NEW: `src/backend/apps/core/services/translation.py`
- EDIT: `src/backend/apps/search/services/query_translator.py` → re-export shim
- EDIT: `src/telegram_bot/handlers/ad_create.py` (rewrite `translate_all_languages`; delete `_do_translate_to`, `translate_to_russian` [dead], `_do_translate` [dead])
- EDIT: `src/telegram_bot/tests/test_multi_lang_translation.py` (patch-target update + parity tests)
- EDIT: `src/backend/apps/core/services/__init__.py` (export)
- DOCS: `docs/01-spec/search-patterns.md`, `docs/01-spec/technical-specification.md`, `docs/03-packages/dependency-collisions.md`
- UNCHANGED: `src/backend/apps/search/views/search.py`, `src/backend/apps/search/services/alert_query.py`, `src/backend/apps/search/tests/test_query_translator.py`

### Residual risks
- 500ms timeout for longer ad text: mitigated by LRU cache + graceful fallback (data model supports `original_language` fallback).
- Shared circuit breaker couples bot+search outage behavior: desirable (global fail-fast during Google Translate outage), bounded at 60s.
