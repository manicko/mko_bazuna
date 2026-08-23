---
id: i18n-translation-egress
domain: researches
tags:
  - i18n
  - translation
  - search
  - fts
  - security
related:
  - i18n-translation-pipeline-gap-analysis
  - db-schema
  - db-indexes
  - technical-specification
---

## Purpose

Document the **implemented** ad-content translation pipeline — how seller-submitted ad text in
any supported language is normalized to the Russian base language and how the per-language search
vectors are populated, searched, and kept in sync.

This is a runtime **architecture + security** reference. It is distinct from the static
UI-string `gettext` (`.po`/`.mo`) pipeline, which is a separate and currently-incomplete concern
— see [i18n-translation-pipeline-gap-analysis.md](../99-agent/i18n-translation-pipeline-gap-analysis.md).

The stored per-language `search_vector_*` columns and their DB trigger are specified in
[db-schema.md > ads > Search](../02-database/db-schema.md), and the publication-time policy is
described in [technical-specification.md §G](../01-spec/technical-specification.md).

## Main Concepts

- **Base language is Russian.** `title`/`description` hold the Russian text; `title_<lang>` /
  `description_<lang>` hold display translations; `original_language` records the seller's source
  language.
- **Translate at publication only.** The egress to the third-party provider runs solely when an
  ad is created/published by the bot — never on the search path.
- **Search is pre-translated.** Buyers search in their own language against per-language vectors.
  There is **no query-time translation** and **no third-party call** during search.
- **Resilient, bounded egress.** A circuit breaker, timeout, LRU cache, and original-text
  fallback keep the provider from blocking ad creation or leaking failures.

## Pipeline overview

```
Seller input  (ru / bs / en / Montenegrin)
      │
      ▼  (bot ad-creation confirm step)
core.translation.translate_text
      │  • Google Translate (deep-translator GoogleTranslator)
      │  • ThreadPoolExecutor (max_workers=4), ~500ms timeout
      │  • circuit-breaker (3 failures → 60s cooldown) + LRU cache (128 / 256 entries)
      │  • original-text fallback on failure
      ▼
Ad.title / description (Russian base) + _en / _bs (display columns)
      │
      ▼  (DB trigger: ads_search_vector_fn, migration 0007)
search_vector_ru / search_vector_bs / search_vector_en
      │  ( GIN indexes: IX_ads_search_gin_ru / _bs / _en )
      ▼
Buyer search
  • LanguageLocale.from_code(request.LANGUAGE_CODE)
  • SearchQuery(websearch, config=<locale.fts_config>) on <locale.fts_vector_field>
  • SearchRank ordering  —  NO query-time translation
```

## Components

### Language locale authority

`apps.core.enums.LanguageLocale` (StrEnum) — `RUSSIAN="ru"`, `BOSNIAN="bs"`, `ENGLISH="en"`.
Each value maps to (a) a PostgreSQL text-search config and (b) a vector column:

| Locale | `fts_config` | `fts_vector_field` |
|---|---|---|
| `ru` | `russian` | `search_vector_ru` |
| `bs` | `simple` | `search_vector_bs` |
| `en` | `english` | `search_vector_en` |

`from_code(language_code, fallback=BOSNIAN)` normalizes locale tags (e.g. `en-US`→`en`).

`apps.core.middleware.language.LanguagePreMiddleware` is the **single** language authority
(Django's `LocaleMiddleware` is removed from the stack). Priority: `?lang=X` → `lang_pref`
cookie → `Accept-Language` header → `ru`. Preference persists via a 1-year `lang_pref` cookie
and, for authenticated users, the session.

### Translation service

`apps.core.services.translation` — shared by the bot (ad creation) and the backfill command.

| Element | Detail |
|---|---|
| Provider | Google Translate via `deep-translator` `GoogleTranslator` |
| Concurrency | `ThreadPoolExecutor(max_workers=4)` for parallel per-language translation |
| Timeout | ~500 ms per call |
| Circuit breaker | `TranslationCircuitBreaker` (module singleton): 3 failures → 60 s cooldown |
| Cache | `lru_cache`: `translate_cached` (128 entries, bs→ru); `translate_cached_generic` (256 entries) |
| Fallback | On failure / open circuit, returns the original text (never blocks ad creation) |

The bot ad-creation dialog translates the title/description in parallel across languages at the
`confirm` step, populates the localized columns, then transitions the ad to `ON_MODERATION` so
that `to_tsvector('russian', …)` is correct for the base vector.

### Backfill command

`management.commands.backfill_translations` — one-shot migration of existing Russian-base ads
into the `en`/`bs` columns via `GoogleTranslator(source="ru")`. Batch size 100, idempotent
(skips already-populated fields), sets `original_language="ru"` when null.

## Search integration

The web `search` view resolves the active locale from `request.LANGUAGE_CODE` via
`LanguageLocale.from_code` and selects the matching vector column + text-search config:

```
SearchQuery(query, search_type="websearch", config=locale.fts_config)
    annotated on locale.fts_vector_field
    ranked by SearchRank
```

Queries are searched **in the buyer's own language** against pre-translated vectors. There is
**no query-time translation** and no external egress on the search path. Single-word queries
also apply locale-aware fuzzy category detection (`difflib`).

## Security & data flow boundaries

- **Publication-time egress only.** The provider is invoked solely when an ad is published;
  search/autocomplete never call it.
- **No PII.** Requests contain only ad title/description text — no `telegram_id`, `username`,
  or IP.
- **Resilience.** The circuit breaker trips after 3 failures (60 s cooldown); the 500 ms timeout
  prevents slow-provider stalls; the original-text fallback preserves ad usability when
  translation is unavailable.
- **Static UI strings are separate.** The `gettext` `.po`/`.mo` pipeline for interface labels is
  a distinct concern (see the gap analysis) and is **not** part of this egress.

## Related documents
- [db-schema.md — ads localized columns + FTS vectors](../02-database/db-schema.md)
- [db-indexes.md — GIN indexes & dual-write trigger](../02-database/db-indexes.md)
- [technical-specification.md §G — content language & translation egress](../01-spec/technical-specification.md)
- [i18n-translation-pipeline-gap-analysis.md — static gettext pipeline gap](../99-agent/i18n-translation-pipeline-gap-analysis.md)
- [Translation service source](../../src/backend/apps/core/services/translation.py)
