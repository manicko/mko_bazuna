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
  - rules
---

## Purpose

Authoritative implementation architecture for the **multilingual (i18n) feature** of Mko Bazuna
(commit `f661532`). It complements the product-level language decisions in
[`technical-specification.md > §G`](technical-specification.md) (content language, search, city match)
and the operational extraction/compile pipeline in
[`../99-agent/rules.md`](../99-agent/rules.md) (§"i18n Pipeline").

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

`LANGUAGE_CODE = "ru"`, `USE_I18N = True`,
`LANGUAGES = [("ru","Russian"),("bs","Bosnian"),("en","English")]`, and
`LOCALE_PATHS = [BASE_DIR / "backend" / "locale"]` in `config/settings/base.py`.

Language is resolved per request by a single custom authority —
`LanguagePreMiddleware` (`apps/core/middleware/language.py`) — which calls
`translation.activate(lang)` and sets `request.LANGUAGE_CODE`. **Django's bundled `LocaleMiddleware`
is NOT in `MIDDLEWARE`.**

| Priority | Source | Setting / value |
|---|---|---|
| 1 (highest) | `?lang=<code>` query parameter | GET param `lang` |
| 2 | Persisted choice | `lang_pref` cookie (1-year max age) |
| 3 | Browser hint | `Accept-Language` header |
| 4 (default) | System default | `settings.LANGUAGE_CODE` (`ru`) |

**Normalisation for all three sources.** Every source is normalised through
`LanguageLocale.from_code` (`apps/core/enums.py`) before it reaches the single typed sink
`LanguagePreMiddleware._set_language_code`, which accepts a `LanguageLocale` member (never a raw
`str`) and activates it. There is no branch that passes a raw string to the sink, so
`request.LANGUAGE_CODE` is always a member of `settings.LANGUAGES`. A non-canonical BCP-47 tag
(`en-US`, `ru-RU`, `de-DE`) therefore resolves to a supported locale; an unsupported code falls back
to `LanguageLocale.BOSNIAN`.

**`Accept-Language` q-value rule.** `_parse_accept_language` parses the header with Django's
`parse_accept_lang_header`, iterates members in descending `q` order, and **skips any member whose
`q == 0`** ("not acceptable"). It returns the first tag that maps to a `LanguageLocale` member; when
the header is present but no tag is supported, resolution falls back to `LanguageLocale.BOSNIAN`.
An absent or empty header returns `None`, and `process_request` then falls back to
`settings.LANGUAGE_CODE` (`ru`), normalised through `LanguageLocale.from_code`.

**Session write is not unconditional.** On the `?lang=` path only, when the base tag is an
explicitly supported code, the middleware persists the preference to the `lang_pref` cookie and, for
an **authenticated** user whose session is available, writes the `django_language` session key. An
unsupported `?lang=` value is logged and does **not** write the cookie or session; it resolves to the
Bosnian fallback for that request only. The `lang_pref` `set_cookie` in `process_response` is the
authoritative server-side writer — the language switcher no longer writes it from JavaScript.

The active language is
exposed to templates via `LANGUAGE_CODE` through the `apps.core.context_processors.language`
context processor (`apps/core/context_processors.py`).

Templates read `LANGUAGE_CODE` to select the locale passed to the name-localization filters (see
[Category / city name localization](#category-city-entity-name-localization)).

> **Dynamic `<html>` language binding (I18N-006):** all 15 page templates replace the hardcoded
> `<html lang="en">` with `<html lang="{{ LANGUAGE_CODE|lower }}" dir="{{ LANGUAGE_BIDI|yesno:"rtl,ltr" }}">`,
> driven by `LANGUAGE_CODE` (from the `apps.core.context_processors.language` processor) and
> `LANGUAGE_BIDI` (from Django's built-in `django.template.context_processors.i18n`, enabled at
> `config/settings/base.py`). All three configured languages (Russian, Bosnian, English) use
> left-to-right scripts, so the `dir` attribute renders `ltr` for all locales. The
> `dir="{{ LANGUAGE_BIDI|yesno:"rtl,ltr" }}"` pattern is forward-compatible: if an RTL-script
> language is ever added to `LANGUAGES` and Django's `LANGUAGES_BIDI`, the attribute will
> automatically render `rtl` for that language.

## Per-User Language (Telegram Bot)

`User.telegram_language` (`apps/users/models.py`) is a required `CharField(max_length=5,
default=LanguageLocale.RUSSIAN.value)` whose `choices` are the `LanguageLocale` values. It is the
single source of truth for the language a seller receives in Telegram, and is **not null/blank**
(default `"ru"`). Added in `apps/users/migrations/0005_user_telegram_language.py` (depends on
`0004_consentrecord`).

Telegram users set it through the bot:

- `/language` command (`telegram_bot/handlers/language.py` `cmd_language`) renders an inline
  keyboard with one `InlineKeyboardButton` per `LanguageLocale` — `🇷🇺 Русский`, `🇧🇦 Bosanski`,
  `🇬🇧 English` — the currently-selected one prefixed with `✅ `.
- Callback data is `lang:<code>` (`BotCallbackPrefix.LANG`); the handler validates the code through
  `LanguageLocale`, then:
  - **Registered users** — `_set_user_language` persists the choice via
    `User.objects.filter(id=...).update(telegram_language=...)` (no full model save).
  - **Anonymous users** — the choice is stashed in a temporary cache keyed
    `bot_anon_lang:{telegram_id}` (TTL 3600, `ANON_LANG_CACHE_TTL` in
    `apps/core/utils/cache.py`) via `set_cached_anon_language`, so the preference survives across
    updates before the user registers.
- **Reconcile at login (EC-5):** when an anonymous deep-linker completes `/start login_<token>` and a
  **new** `User` row is created, `handle_login_orm` (`telegram_bot/handlers/login.py`) backfills the
  temp-cached language onto `User.telegram_language` (DB value wins for a fresh row), then clears the
  temp cache (`invalidate_anon_language_cache`) so a later login cannot re-apply a stale choice.
- `/language` is **not** login-gated: anonymous users receive the same keyboard and see the temp-store
  choice (or the default). The "🌐 Language" button in the `/start` greeting opens it via
  `BotCallbackPrefix.LANG_OPEN`.

**Runtime activation (FQ-001):** `LanguageMiddleware` (`telegram_bot/middlewares/language.py`) is
registered in `telegram_bot/main.py` (and in the bot test conftest) as an update-level middleware
that runs **before** `AccountStateMiddleware`. It resolves `event.from_user.id` to the preferred
language via `_resolve_user_language` (using `sync_to_async`), calls `translation.activate(lang)`
before handler dispatch, and calls `translation.deactivate()` in a `finally` block to prevent locale
leakage between updates on the same asgiref worker thread. The resolution fallback chain is:

| Priority | Source |
|---|---|
| 1 (highest) | Persisted `User.telegram_language` (registered users) |
| 2 | Temporary anon-lang cache `bot_anon_lang:{telegram_id}` (anonymous users who chose a language) |
| 3 (default) | `settings.LANGUAGE_CODE` |

This ensures all `_()`-wrapped strings in bot handlers — including denial messages from
`AccountStateMiddleware` — render in the user's preferred language. The anonymous temp-cache choice
is reconciled onto the `User` row at first login (see above). See the
[language switch](../99-agent/architecture.md#bot-language-switch) seam in the architecture doc for
the broader bot UX context.

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
| `Category` | locale → `ru` → `name` | `apps/categories/models.py` |
| `City` | locale → `ru` → `name` | `apps/locations/models.py` |
| `LookupItem` | locale → `ru` → `slug` | `apps/lookups/models.py` |

Templates do **not** call `get_name` directly. They use the `localized_content` template-tag filters
(`apps/core/templatetags/localized_content.py`), each taking an explicit `locale` and implementing
**locale → ru → original/name/slug** fallback:

| Filter | Signature | Behavior |
|---|---|---|
| `get_category_name` | `(category, locale=LanguageLocale.RUSSIAN)` | `""` if `None`, else `category.get_name(locale)` |
| `get_city_name` | `(city, locale=LanguageLocale.RUSSIAN)` | `""` if `None`, else `city.get_name(locale)` |
| `get_lookup_name` | `(item, locale=LanguageLocale.RUSSIAN)` | `item.get_name(locale)` (used by `feature_tag.html`, DB-based i18n) |
| `get_title` | `(ad, locale=LanguageLocale.RUSSIAN)` | `ad.get_title(locale)` |
| `get_description` | `(ad, locale=LanguageLocale.RUSSIAN)` | `ad.get_description(locale)` |

Per-ad content lives in `Ad.title` (Russian base) / `Ad.title_en` / `Ad.title_bs` and the matching
`description_*` columns (`apps/ads/models.py`). `Ad.get_title(locale)` iterates
`[f"title_{locale}", "title"]` returning the first truthy value; `Ad.get_description(locale)` is a
separate method with the analogous behaviour, both on the `Ad` model in `apps/ads/models.py`.

Entity-suggestion matching threads the locale explicitly: `get_entity_suggestions(prefix,
limit=5, locale=LanguageLocale.RUSSIAN)` (`apps/search/services/entity_suggestions.py`) resolves category and
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
`search_vector_en` (plus a legacy `search_vector` column + `IX_ads_search_gin` index that are
retained **for backward compatibility only** — all FTS read paths use the per-language
`search_vector_ru/bs/en` columns — and are **candidates for removal in a future migration**;
see [`db-schema.md`](../02-database/db-schema.md) > Search) — maintained by the
`ads_search_vector_fn` trigger. `LanguageLocale` maps a resolved locale to the matching vector
column and PostgreSQL text-search configuration:

| Locale | `fts_config` | Vector column (`fts_vector_field`) |
|---|---|---|
| `ru` | `russian` | `search_vector_ru` |
| `bs` | `simple` | `search_vector_bs` |
| `en` | `english` | `search_vector_en` |

(`apps/core/enums.py`, `LanguageLocale`). The buyer's resolved `LANGUAGE_CODE` selects the vector column
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
- `<locale>` — built via
  `LanguageLocale.from_code(request.LANGUAGE_CODE, fallback=LanguageLocale.RUSSIAN).value`
  (`apps/categories/views.py`, `category_submenu`), so the segment is a normalised supported code
  rather than the raw `request.LANGUAGE_CODE` attribute.
- TTL 300 s (`SUBMENU_CACHE_TTL`) with a 60 s stale-serve window (`SUBMENU_CACHE_STALE_TTL`)
  and a 30 s single-flight lock (`SUBMENU_CACHE_LOCK_TTL`); the fragment is cached via
  `category_submenu()` in `apps/categories/views.py`, which calls
  `get_with_stale_revalidate()` from `apps/core/utils/swr_cache.py`.

The locale segment is the key correctness property: without it, a Russian submenu render would be
reused for a Bosnian visitor.

**Cache / `Vary` contract.** The cache key above carries the locale explicitly, so the fragment does
not rely on HTTP content negotiation. The `Vary` behaviour is documented in the
`LanguagePreMiddleware` module docstring (`apps/core/middleware/language.py`): the middleware emits
`Vary: Accept-Language` (plus `Content-Language`), which is its **only** `Vary` contribution and does
**not** cover cookie-driven locale. On the real stack, `Vary: Cookie` reaches token-bearing responses
**incidentally** via `CsrfViewMiddleware` (any template that called `get_token()`), while the two
token-free HTMX fragments (`ads/partials/ad_list.html`, `categories/partials/mega_submenu.html`) can
lose it. The middleware deliberately adds no `Vary: Cookie` today; making it deliberate is deferred
until a shared cache is introduced. See the module docstring for the full contract.

## Timezone and Date Localization

Display timezone is `TIME_ZONE = "Europe/Podgorica"`, a hard-coded literal beside `LANGUAGE_CODE` in
`config/settings/base.py`. It is **not** read through `env()`, has **no** `ALLOWED_ENV_VARS` entry and
no `.env*.example` line (Product Owner ruling Q4, 2026-10-03). `USE_TZ` stays Django's default
(`True`), so stored timestamps remain UTC-aware and only presentation moves to the display timezone.

Dates are rendered through Django's locale-aware `date` filter using named format attributes, so each
string follows the active locale's formats:

| Template | Format attribute |
|---|---|
| `ads/detail.html` | `DATE_FORMAT` |
| `analytics/seller_dashboard.html` | `DATE_FORMAT` |
| `ads/partials/ad_list.html` | `SHORT_DATE_FORMAT` |
| `cabinet/search_history.html` | `DATETIME_FORMAT` |

Two templates also render a machine-readable `<time datetime="…">` attribute built with the literal
`date:'Y-m-d'` pattern (`ads/detail.html` and `ads/partials/ad_list.html`). That attribute is
**ISO-8601 and locale-independent by design** — it is not converted to the display timezone and not
localized, because it exists for machines (HTML semantics, crawlers), not for readers. Only the
human-visible text beside it uses the localized format attributes above.

## Localized Notifications

Bot alerts (saved-search / new-matching-ad notifications) are localized to the recipient's
preference rather than the request locale. `build_alert_message(ad, saved_search, locale=...)`
(`apps/search/services/immediate_alerts.py`) wraps every `gettext` call in
`translation_override(locale)`, and `locale` is read per-recipient from
`User.telegram_language` in `_build_payload`, defaulting to Russian:

```
locale = getattr(user, "telegram_language", None) or LanguageLocale.RUSSIAN.value
```

Message content is then built with the ad and city rendered in that locale (`ad.get_title(locale)`,
`ad.city.get_name(locale)`). Immediate alerts and the daily digest are the two paths where
`User.telegram_language` drives alert-message rendering.

The **daily digest** path (`apps/search/management/commands/send_alerts.py`, I18N-001) mirrors
the immediate-alert pattern. `send_alerts` is dispatched by the scheduler's `DAILY_COMMANDS` on
the first hourly tick at or after 08:00 UTC each calendar day — there is no cron entry in the
containerised deployment. Its advisory lock (`AdvisoryLockId.ALERT_DELIVERY_TASK`) is for
**concurrency** control, not repeat protection; the run-level idempotency mechanism is the
durable daily marker ([`db-schema.md`](../02-database/db-schema.md#scheduler_daily_state-singleton)),
which records the day only after every daily command exits 0, so a restart mid-day does not
re-fire the set.
 `_format_digest` accepts a `locale` parameter, wraps its `gettext()` call in
`translation_override(locale)`, and renders each ad title via `ad.get_title(locale)` (truncated to
50 characters) instead of the Russian-only `ad.title`. The call site (`_send_user_digests`)
resolves `locale` per recipient from `user.telegram_language` (defaulting to
`LanguageLocale.RUSSIAN.value`); the msgid `"New ads matching your saved searches ({count} found):\n"`
is extracted and translated in all three `.po` files (ru, bs, en).

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
`apps.core.services.translation.translate_text` helper, which uses httpx against
the Google Cloud Translation API, runs in parallel via `asyncio.gather` + `asyncio.to_thread`, enforces a 500 ms
timeout, a circuit breaker (3 failures → 60 s cooldown), and an LRU cache. No user PII
(`telegram_id`, `username`, IP) is included in the request (decision G, data flow). Because the
Russian vector is built from this translated content,
`to_tsvector('russian', …)` is correct for `search_vector_ru`.

> Egress is a best-effort, non-identifying content transfer — see the
> [Translation Egress](#translation-egress) contract above and
> [`technical-specification.md §G`](technical-specification.md).
>
> The former cross-reference here pointed at `../96-researches/i18n-translation-egress.md`; that
> research note was **never committed** and the whole `docs/96-researches/` directory does not exist.
> The contract it would have described is the section above, which is the live source of truth.

## Python-side `gettext` Usage

`gettext` / `gettext_lazy` is now used in production Python for the first time, covering 16
user-facing strings across 7 files (UI labels, `HttpResponseForbidden` bodies, `TimeRange` and
dashboard status labels, alert digest header). Runtime `gettext` is used for request-time strings; `gettext_lazy` for
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
| `apps/search/management/commands/send_alerts.py` | "New ads matching your saved searches" (1) | `gettext` (runtime) |

QLT-005 extended `_()` wrapping to the seven Telegram bot handler modules under
`telegram_bot/handlers/` (`alerts.py`, `ad_create.py`, `ad_copy.py`, `contact.py`,
`login.py`, `language.py`, `support.py`). These are runtime `gettext` calls activated per-update by
`LanguageMiddleware` (FQ-001), which resolves `User.telegram_language` and calls
`translation.activate()` before handler dispatch.

## Development & CI Integration

The static extraction/compile pipeline (Makefile targets, Dockerfile + entrypoint
`compilemessages`, `.po`/`.mo` layout under `backend/locale`, `.mo` git-ignored) is documented in
[`../99-agent/rules.md`](../99-agent/rules.md) (§"i18n Pipeline", "Workflow").
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
| `test_template_extraction_coverage` | msgids extracted from `{% trans %}`/`{{ _("…") }}`/`{% blocktrans %}` templates each exist in all three `.po` files |
| `test_hreflang_present` | every page template renders `<link rel="alternate" hreflang>` (via `components/locale_head.html` partial, I18N-004) |
| `test_hreflang_include_in_every_page_template` | source-level: every in-scope non-partial page template contains the `components/locale_head.html` include (BLOCK 8 / 14-I18N-008) |
| `test_plural_forms` | each `.po` `Plural-Forms` header matches CLDR rules |
| `test_locale_switch_re_render` | `?lang=bs` content re-renders in the Bosnian locale |
| `test_bot_no_hardcoded_messages` | (QLT-005) AST-scans **all of `src/telegram_bot` except `tests/`** (widened by BLOCK 8 / 14-I18N-006) for user-facing Bot/API method calls (`.answer()`, `.reply()`, `.edit_text()`, etc.) whose text arg is a bare string literal or f-string rather than a `_()` call |
| `test_no_cyrillic_msgids` | (QLT-005) no `msgid` in any `.po` file contains Cyrillic characters; msgids must be English |
| `test_bs_msgstr_has_no_cyrillic` | (BLOCK 9 / N-1) locale-scoped sibling of `test_no_cyrillic_msgids`: a Cyrillic code point in a **`bs` `msgstr`** is a violation (Bosnian is Latin), every `msgstr` form inspected; `ru`'s legitimate Cyrillic stays exempt. The three knowingly-shipped-as-is strings are consulted by msgid against the named `_BS_MSGSTR_LATIN_SCRIPT_EXEMPTIONS` set (Q1 ruling 2026-10-05, option b — `OPEN-PENDING-REVIEWER`) |
| `test_reverse_stale_entry_gate` | (BLOCK 11 / 14-I18N-014) reverse of `test_extraction_completeness`: every catalogue msgid must exist in a real in-process source extraction (Python `ast` + full-root template scan) — a msgid that leaves the source must not linger. The wrapped multi-line msgid is compared as its joined string (parsed, never regexed). The three runtime-live `_lazy` strings are exempted by the single `_EXTRACTION_GAP_MSGIDS` definition |
| `test_no_obsolete_entries_in_any_catalogue` | (BLOCK 11 / 14-I18N-014, `test_i18n_pipeline.py`) zero `#~` obsolete blocks in **every** catalogue (post-prune target is zero; the pre-prune `7/7/1` justified the block but is not the invariant asserted) |
| `test_title_tags_translated` | Page `<title>` tags localize per language |
| `test_plural_forms_runtime` | `{% blocktrans count %}` selects correct CLDR plural form at runtime |
| `test_all_languages_ltr` | All configured languages use LTR scripts; `LANGUAGE_BIDI` is False for ru/bs/en |
| `test_no_hardcoded_js_strings` | Inline `<script>` blocks contain no untranslated prose string literals |
| `test_bot_no_raw_model_field_access` | AST-scans the widened bot scope (all of `src/telegram_bot` except `tests/`) for raw `.name`/`.title`/`.description` access |
Part C of `test_i18n_completeness.py` AST-scans the widened bot scope — all of
`src/telegram_bot` except `tests/` (BLOCK 8 / 14-I18N-006), which reaches the
`middlewares/` package (including the locale-activating `language.py`), `retry.py`,
`states.py`, `main.py`, the `schemas/` package and the nine-module
`handlers/ad_create/` package — to enforce that all user-facing bot strings are
wrapped in `_()`, activated at runtime by `LanguageMiddleware` (FQ-001).
User-facing strings that are deliberately not translated are listed once in the
named exemption sets (`_BOT_EXEMPT_FUNCTIONS`, `_BS_MSGSTR_LATIN_SCRIPT_EXEMPTIONS`,
`_EXTRACTION_GAP_MSGIDS`) and consulted by symbol, never by line number.

The scan scope excludes the `admin/` staff subtree, the analytics/moderation dashboards, and
`components/feature_tag.html` (DB-based i18n via `get_lookup_name`) — these three template
exclusions mirror the `exclude_subpaths` tuple in `test_i18n_completeness.py`. **Model metadata is
an explicit, unconditional exemption:** `verbose_name` / `help_text` on Django model fields are not
scanned and are intentionally not wrapped in `gettext_lazy`. The exemption entails no catalogue
entry and no runtime change; the admin tests asserting English field text are unchanged (14-I18N-013
Option A). `test_i18n_pipeline.py` adds
unit checks for `.po` existence, `msgstr` non-emptiness, the `component_tag` template filter,
the plural-aware parser case (`test_parse_po_entries_reports_blank_non_final_form`, BLOCK 7), and
`test_pot_creation_date_sync` — which asserts all three `.po` files share an identical
`POT-Creation-Date` (since `makemessages` runs all locale flags in a single invocation) — plus the
durable obsolete-symmetry assertion `test_no_obsolete_entries_in_any_catalogue` (BLOCK 11).

> **Definition of Done (automatable):** every new visible UI string wrapped in `{% trans %}`; all
> `{% trans %}` msgids extracted into `ru`/`bs`/`en` `.po`; `ru`+`bs` `msgstr` non-empty (`en`
> follows Django convention — empty `msgstr` means the msgid is already English); `compilemessages`
> succeeds; no raw `.get_name` calls in templates. The operational checklist lives in the
> completeness gate above and in [`../99-agent/rules.md`](../99-agent/rules.md) (§"i18n Pipeline",
> "Completeness gate"); this spec is the authoritative current description.
>
> The former cross-reference here pointed at `../99-agent/i18n-definition-of-done-research.md`; that
> pre-implementation research report was **never committed** and no such file exists in
> `docs/99-agent/`.

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
- [`rules.md`](../99-agent/rules.md) — agent coding rules; the operational extraction/compile pipeline and the i18n `Completeness gate` (§"i18n Pipeline").
