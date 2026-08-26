---
id: i18n-spec
domain: spec
tags:
  - i18n
  - localization
  - architecture
  - fts
  - telegram
related:
  - technical-specification
  - db-schema
  - db-categories
  - db-enums
  - architecture
  - i18n-translation-pipeline-gap-analysis
---

## Purpose

Authoritative implementation architecture for the **multilingual (i18n) feature** of Mko Bazuna
(commit `f661532`). It complements the product-level language decisions in
[`technical-specification.md > §G`](technical-specification.md) (content language, search, city match)
and the operational extraction/compile pipeline in
[`../99-agent/i18n-translation-pipeline-gap-analysis.md`](../99-agent/i18n-translation-pipeline-gap-analysis.md).

This document is the single source of truth for the **runtime and behavioral mechanics** of
localization: per-request language resolution, per-user Telegram language, category/city/entity
name localization, per-language full-text search wiring, localized notifications, and the
automated completeness gate. Schema fields are summarized here; column-level detail lives in
[`../02-database/db-schema.md`](../02-database/db-schema.md).

## Main Concepts

- **Three UI languages:** `ru` (Russian, content base), `bs` (Bosnian, latin), `en` (English).
  Language codes are backed by the `LanguageLocale` StrEnum (`apps/core/enums.py`).
- **Two language authorities:** a *per-request* language (for the web UI, resolved by middleware)
  and a *per-user* language (`User.telegram_language`, for localized Telegram bot messages).
- **Split content strategy:** user-facing UI strings use Django `gettext`/`{% trans %}`; stored
  catalogue data (categories, cities, lookups) uses `name_i18n` JSONB + `get_name(locale)`; search
  uses per-language FTS vectors. The three layers are kept separate, not unified.
- **No query-time translation:** search runs per-language against pre-translated vectors
  (decision G in [`technical-specification.md`](technical-specification.md)).
- **DB-based i18n exemption:** `feature_tag.html` renders via `get_lookup_name` against
  `LookupItem.name_i18n` and is intentionally outside the `gettext` extraction/completeness scan.

## Runtime Language Resolution (Web UI)

`LANGUAGE_CODE = "ru"` (L55), `USE_I18N = True` (L56), `LANGUAGES = [("ru","Russian"),("bs","Bosnian"),("en","English")]` (L57-61), and `LOCALE_PATHS = [BASE_DIR / "backend" / "locale"]` (L62) in `config/settings/base.py`.

Language is resolved per request by a single custom authority —
`LanguagePreMiddleware` (`apps/core/middleware/language.py`) — which calls
`translation.activate(lang)` and sets `request.LANGUAGE_CODE`. **Django's bundled `LocaleMiddleware`
is NOT in `MIDDLEWARE`.**

| Priority | Source | Setting / value |
|---|---|---|
| 1 (highest) | `?lang=<code>` query parameter | GET param `lang` |
| 2 | Persisted choice | `lang_pref` cookie (1-year max age) |
| 3 | Browser hint | `Accept-Language` header |
| 4 (default) | System default | `ru` |

The resolved code is normalized by `LanguageLocale.from_code()` (accepts `en-US` → `en`, falls back
to `bs` when unsupported). A session key `django_language` is also written. The active language is
exposed to templates via `LANGUAGE_CODE` through the `apps.core.context_processors.language`
context processor (`apps/core/context_processors.py` L22-24).

Templates read `LANGUAGE_CODE` to select the locale passed to the name-localization filters (see
[Category / city name localization](#category-city-entity-name-localization)).

## Per-User Language (Telegram Bot)

`User.telegram_language` (`apps/users/models.py` L102-107) is a required `CharField(max_length=5,
default=LanguageLocale.RUSSIAN.value)` whose `choices` are the `LanguageLocale` values. It is the
single source of truth for the language a seller receives in Telegram, and is **not null/blank**
(default `"ru"`). Added in `apps/users/migrations/0005_user_telegram_language.py` (depends on
`0004_consentrecord`).

Telegram users set it through the bot:

- `/language` command (`telegram_bot/handlers/language.py` `cmd_language`) renders an inline
  keyboard with one `InlineKeyboardButton` per `LanguageLocale` — `🇷🇺 Русский`, `🇧🇦 Bosanski`,
  `🇬🇧 English` — the currently-selected one prefixed with `✅ `.
- Callback data is `lang:<code>` (`LANG_CALLBACK_PREFIX = "lang:"`); the handler validates the code
  through `LanguageLocale`, then `_set_user_language` updates `User.telegram_language` via
  `User.objects.filter(id=...).update(telegram_language=...)` (no full model save).

The stored language drives per-user message localization in bot notifications (see
[Localized notifications](#localized-notifications)) and is exposed to the web context for
alert content.

## Category / City / Entity Name Localization

Stored catalogue data keeps Russian in the base `name` column and translations in a `name_i18n`
JSONB column `{"ru": ..., "bs": ..., "en": ...}` on `Category`, `City`, `LookupItem`, and
`LookupGroup` (see [`db-schema.md`](../02-database/db-schema.md) > `categories`, `cities`, `lookup_items`).
`get_name(locale)` implements the fallback chain **locale → ru → name** (with `slug` as the final
fallback for `LookupItem`).

| Model | `get_name(locale)` fallback | Location |
|---|---|---|
| `Category` | locale → `ru` → `name` | `apps/categories/models.py` L53-62 |
| `City` | locale → `ru` → `name` | `apps/locations/models.py` L45-54 |
| `LookupItem` | locale → `ru` → `slug` | `apps/lookups/models.py` L88-96 |

Templates do **not** call `get_name` directly. They use the `localized_content` template-tag filters
(`apps/core/templatetags/localized_content.py`), each taking an explicit `locale` and implementing
**locale → ru → original/name/slug** fallback:

| Filter | Signature | Behavior |
|---|---|---|
| `get_category_name` | `(category, locale="ru")` | `""` if `None`, else `category.get_name(locale)` |
| `get_city_name` | `(city, locale="ru")` | `""` if `None`, else `city.get_name(locale)` |
| `get_lookup_name` | `(item, locale="ru")` | `item.get_name(locale)` (used by `feature_tag.html`, DB-based i18n) |
| `get_title` | `(ad, locale="ru")` | `ad.get_title(locale)` |
| `get_description` | `(ad, locale="ru")` | `ad.get_description(locale)` |

Per-ad content lives in `Ad.title` (Russian base) / `Ad.title_en` / `Ad.title_bs` and the matching
`description_*` columns (`apps/ads/models.py` L43-75). `Ad.get_title(locale)` iterates
`[f"title_{locale}", "title"]` returning the first truthy value; `get_description(locale)` is
analogous (`apps/ads/models.py` L464-487).

Entity-suggestion matching threads the locale explicitly: `get_entity_suggestions(prefix,
limit=5, locale="ru")` (`apps/search/services/entity_suggestions.py` L36-38) resolves category and
city labels via `get_name(locale)`, so autocomplete matches the active UI language.

## Feature Tag Rendering (Catalog + Detail)

Ad features (`LookupItem` of group `LISTING_FEATURE`) are rendered as localized tagged
`<span>` badges through a dedicated partial, `components/feature_tag.html`. This is
**DB-based i18n** — the partial renders its label via the `get_lookup_name` template filter
(`apps/core/templatetags/localized_content.py`), which delegates to
`LookupItem.get_name(locale)` against the `name_i18n` JSONB column, and is therefore
intentionally outside the `gettext` extraction/completeness scan (see above).

The partial is included in three rendering paths:

- **Catalog listing cards** — `ads/partials/ad_list.html` renders up to 4 features per
  card (`{% for f in ad.features.all|slice:":4" %}`) via
  `{% include "components/feature_tag.html" with feature=f only %}`.
- **Ad detail page** — `ads/detail.html` renders `display_features`, a category-scoped
  subset (see below), via `{% include "components/feature_tag.html" with feature=f only %}`.
- The `component_tag` template filter (`apps/ads/templatetags/global_tags.py`) renders
  the partial via `render_to_string` for inline use.

All four views that render ad cards or detail pages use `prefetch_related("features")`
to eliminate N+1 queries: `listings()`, `search()`, `favorites_list()`, and
`ad_detail()`.

On the detail page, features are filtered to those **applicable to the ad's category**
before rendering. Because `LookupItem` has no direct `category` FK, the resolver does not
filter by category; instead `CategoryLookupResolver.get_resolved_feature_codes(category)`
walks the MPTT ancestor chain (nearest-explicit-ancestor-wins) to compute the set of
feature slugs valid for that category, then `display_features` is built by selecting only
the ad's features whose slug falls in that set. This suppresses category-inappropriate
features (e.g., "mileage" on a real-estate ad). Cross-referenced from
[`db-categories.md`](../02-database/db-categories.md) > Ad integration.

## Per-Language Full-Text Search

Each `Ad` carries per-language `TSVECTOR` columns — `search_vector_ru`, `search_vector_bs`,
`search_vector_en` (plus a legacy `search_vector` during the dual-write transition, not yet
dropped; see [`db-schema.md`](../02-database/db-schema.md) > Search) — maintained by the
`ads_search_vector_fn` trigger. `LanguageLocale` maps a resolved locale to the matching vector
column and PostgreSQL text-search configuration:

| Locale | `fts_config` | Vector column (`fts_vector_field`) |
|---|---|---|
| `ru` | `russian` | `search_vector_ru` |
| `bs` | `simple` | `search_vector_bs` |
| `en` | `english` | `search_vector_en` |

(`apps/core/enums.py` L187-237.) The buyer's resolved `LANGUAGE_CODE` selects the vector column
and config; category names are indexed per language via `name_i18n->>'bs'` / `->>'en'` (falling
back to the Russian `name`) at `weight 'C'`. No query-time translation occurs (decision G).

## Submenu Cache Localization

The catalog mega-submenu is a cached HTML fragment. Its cache key includes a **locale segment** so
that the same category tree is never served in the wrong language:

```
category:submenu:<tree_version>:<slug>:<locale>
```

- `<tree_version>` — atomic counter in `apps.categories.cache` (`category:tree_version`), bumped
  by `Category` / `CategoryPath` save+delete signals, so a single increment invalidates all
  cached submenus.
- `<locale>` — `request.LANGUAGE_CODE or "ru"` (resolved by `LanguagePreMiddleware`).
- TTL 300 s (`SUBMENU_CACHE_TTL`); rendered in `apps/categories/views.py` L46-59.

The locale segment is the key correctness property: without it, a Russian submenu render would be
reused for a Bosnian visitor.

## Localized Notifications

Bot alerts (saved-search / new-matching-ad notifications) are localized to the recipient's
preference rather than the request locale. `build_alert_message(ad, saved_search, locale=...)`
(`apps/search/services/immediate_alerts.py` L96-142) wraps every `gettext` call in
`translation_override(locale)`, and `locale` is read per-recipient from
`User.telegram_language` in `_build_payload` (L145-161), defaulting to Russian:

```
locale = getattr(user, "telegram_language", None) or LanguageLocale.RUSSIAN.value
```

Message content is then built with the ad and city rendered in that locale (`ad.get_title(locale)`,
`ad.city.get_name(locale)`). This is the only path where `User.telegram_language` affects alert
message rendering.

> **`SavedSearch.language` vs. `User.telegram_language` — two distinct locale authorities:**
> `SavedSearch.language` (see [`db-schema.md`](../02-database/db-schema.md) > SavedSearch) is the
> language the buyer saved the search in; it selects **which** per-language FTS vector
> (`search_vector_ru/bs/en`) the matching query runs against, set from `request.LANGUAGE_CODE` at
> save time (`cabinet/views/saved_searches.py`) and consumed by `search/services/alert_query.py`.
> It does **not** affect message text. `User.telegram_language` is the per-recipient language used
> to **render** the alert message. A buyer who saved a search in Bosnian (`bs`) but later switches
> their Telegram UI language to English will be *matched* via the `bs` vector but *notified* in
> English.

## Translation Egress

Seller input may arrive in any supported language, but **title + description are translated to
Russian at ad publication**. The bot delegates to the shared
`apps.core.services.translation.translate_text` helper, which uses `deep-translator` against
Google Translate, runs in parallel via `asyncio.gather` + `asyncio.to_thread`, enforces a 500 ms
timeout, a circuit breaker (3 failures → 60 s cooldown), and an LRU cache. No user PII
(`telegram_id`, `username`, IP) is included in the request (decision G, data flow). Because the
Russian vector is built from this translated content,
`to_tsvector('russian', …)` is correct for `search_vector_ru`.

> Egress is a best-effort, non-identifying content transfer — see
> [`../96-researches/i18n-translation-egress.md`](../96-researches/i18n-translation-egress.md)
> and [`technical-specification.md §G`](technical-specification.md).

## Python-side `gettext` Usage

`gettext` / `gettext_lazy` is now used in production Python for the first time, covering 15
user-facing strings across 6 files (UI labels, `HttpResponseForbidden` bodies, `TimeRange` and
dashboard status labels). Runtime `gettext` is used for request-time strings; `gettext_lazy` for
module/class-level constants. `Http404(...)` messages are intentionally left untranslated —
Django's default 404 handler does not surface them to users in production.

| File | Strings | Variant |
|---|---|---|
| `apps/core/context_processors.py` | "Entire country" + 5 JS labels | `gettext` (runtime) |
| `apps/core/enums.py` | `TimeRange` labels (3) | `gettext_lazy` |
| `apps/ads/views/dashboard.py` | status labels (5) | `gettext_lazy` |
| `apps/ads/views/edit.py` | error + 3 × `HttpResponseForbidden` | `gettext` (runtime) |
| `apps/ads/views/delete.py` | `HttpResponseForbidden` (1) | `gettext` (runtime) |
| `apps/ads/views/listings.py` | `HttpResponseForbidden` (1) | `gettext` (runtime) |

## Development & CI Integration

The static extraction/compile pipeline (Makefile targets, Dockerfile + entrypoint
`compilemessages`, `.po`/`.mo` layout under `backend/locale`, `.mo` git-ignored) is documented in
[`../99-agent/i18n-translation-pipeline-gap-analysis.md`](../99-agent/i18n-translation-pipeline-gap-analysis.md).
This section records only the behavioral gate.

**CI i18n gate** — a dedicated `i18n` job runs in `ci.yml` parallel to `build`/`test`/`lint`/
`typecheck`/`lint-templates`; it runs `compilemessages` then
`test_i18n_completeness.py` + `test_i18n_pipeline.py` (all `@pytest.mark.unit`, no database).
The `test` job also runs `compilemessages` before pytest (`ci.yml`).

**Completeness tests** (`apps/ads/tests/test_i18n_completeness.py`) enforce the multilingual
Definition of Done on every fast-gate run:

| Test | Verifies |
|---|---|
| `test_no_hardcoded_visible_text` | visible text in public/seller templates wrapped in `{% trans %}`/`{% blocktrans %}`/`{{ _("…") }}` |
| `test_extraction_completeness` | every `{% trans %}` msgid exists in all three `.po` files |
| `test_no_empty_msgstr` | `ru`/`bs` `msgstr` non-empty; `en` follows Django convention (empty = msgid is English) |
| `test_no_raw_get_name_in_templates` | no raw `{{ obj.get_name }}` — must use `|get_category_name:LANGUAGE_CODE` / `|get_city_name:LANGUAGE_CODE` filters |
| `test_mo_compiled` | `.mo` exists for every `.po` |

The scan scope excludes the `admin/` staff subtree, the analytics/moderation dashboards, and
`components/feature_tag.html` (DB-based i18n via `get_lookup_name`). `test_i18n_pipeline.py` adds
unit checks for `.po` existence, `msgstr` non-emptiness, and the `component_tag` template filter.

> **Definition of Done (automatable):** every new visible UI string wrapped in `{% trans %}`; all
> `{% trans %}` msgids extracted into `ru`/`bs`/`en` `.po`; `bs`+`en` `msgstr` non-empty (`ru` may
> equal `msgid`); `compilemessages` succeeds; no raw `.get_name` calls in templates. See
> [`../99-agent/i18n-definition-of-done-research.md`](../99-agent/i18n-definition-of-done-research.md)
> for the full checklist — a pre-implementation research report whose identified gaps were
> implemented in `f661532`; this spec is the authoritative current description.

## Languages

| Code | Name | Role |
|---|---|---|
| `ru` | Russian | Content base language; `title`/`description`/`name` base columns |
| `bs` | Bosnian (latin) | UI + search target |
| `en` | English | UI + search target |

## Related Documents

- [`technical-specification.md`](technical-specification.md) — §G product-level language decisions; §F/§K consent behavior.
- [`db-schema.md`](../02-database/db-schema.md) — `users.telegram_language`; `ads.title_en/title_bs`; `name_i18n` columns; per-language `search_vector_*`.
- [`db-categories.md`](../02-database/db-categories.md) — submenu cache key `<locale>` segment.
- [`db-enums.md`](../02-database/db-enums.md) — `LanguageLocale`.
- [`architecture.md`](../99-agent/architecture.md) — two-process model (bot + web share the user language field).
- [`i18n-translation-pipeline-gap-analysis.md`](../99-agent/i18n-translation-pipeline-gap-analysis.md) — operational extraction/compile pipeline + gettext inventory.
