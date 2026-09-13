---
# Report metadata — fill once per phase report.
phase: "10"
phase_name: "Code Quality"
date: "2026-09-12"
auditor: "Executor (subagent)"
validator: ""  # Phase 99 only — omit/blank for raw phase findings
mode: "problems-only"
# Correct prefix per phase: 01-ENT, 02-CFG, 03-DB, 04-AUT, 05-AD, 06-PII, 07-MED, 08-SRH, 09-EXT, 10-QLT, 11-TST, 12-OPS, 13-PERF, 14-I18N
id_prefix: "QLT"
# report_status = lifecycle of the report document (draft → validated)
# per-finding Status (in Findings Summary + field table below) = lifecycle of the individual finding (Open → Validated/Rejected/Merged/Reclassified/Deferred)
report_status: "draft"  # "draft" for raw phases; Phase 99 sets to "validated"
severity_taxonomy: ".kilo/commands/audit/phases/10-audit-code-quality.md#severity-taxonomy"  # pointer to phase rubric, NOT hardcoded
# Structural enforcement (replaces the buried ID-preservation comment):
---

# Audit Findings — Code Quality

## Executive Summary

Seven problems were found across typing, constants, logging, layering, module size, boundary validation, and i18n. The two highest-severity issues are both layering failures in the Telegram bot: `ad_create.py` is a 1311-line god-module that embeds 15+ `sync_to_async` ORM data-access helpers and business logic directly in the handler (instead of a shared service layer), and the bot's callback-data protocol tokens (`"purpose:"`, `"condition:"`, `"feature:"`, `"price_currency:"`, `"price_free"`, `"features_done"`, `"lang:"`, `"unsub_on:"`) are raw string literals duplicated between filter lambdas and keyboard builders with no single source of truth — a mismatch silently breaks bot routing. Three medium findings follow: the web `listings` view duplicates the same fat-view pattern (~280 lines of filter/sort/pagination logic inline), the web edit POST bypasses Pydantic validation on its main text/price-edit path while a sibling path validates, and bot i18n is inconsistent (alerts.py and ad_create.py emit unwrapped Russian/English strings; contact.py uses Russian msgid text; the completeness gate scans templates only, so bot strings are uncovenanted). Two low findings close out the report: pervasive f-string logging (49 sites, inconsistent with `%s` style) and bare `dict`/`list` annotations in the bot handler. The shared contact rule (zone R2) is correctly centralized in `apps.core.services.contact` — confirmed DRY across the bot+web seam.

## Scope & Methodology

**Scope:** Static + structural audit of `src/backend/` (Django apps: ads, analytics, cabinet, categories, core, currencies, locations, lookups, media, moderation, search, trust, users) and `src/telegram_bot/` (handlers, schemas, services, middlewares, lifecycle, main). Entry points (`config.wsgi`, `manage.py`, `telegram_bot/main.py`) and settings (`config/settings/*`) reviewed. CI workflow not present in workspace (`.github/` absent) so the `makemigrations --check` gate could not be verified from source; migration discipline cross-checked via git tree + raw-SQL inspection.

### Runtime Verification

| R# | Check | Method | Result |
|----|-------|--------|--------|
| R-01 | Linter clean across repo | `uv run ruff check src/backend src/telegram_bot` → `All checks passed!` | PASS |
| R-02 | Type-checker: no production Any masking; framework-forced Any documented | `basedpyright src/backend src/telegram_bot` → 1 error, both in `test_priority_service.py:500` (django-stubs `cached_property` gap, tracked as AD-008 Phase 05); all production `Any` is framework signatures (Django `request`, aiogram middleware/handler) or test fixtures | PASS |
| R-03 | No `print()` in production code (entry points included) | `grep "print(" src/` → 1 hit, `config/settings/tests/test_settings_secrets.py:70` (subprocess test string, not code) | PASS |
| R-04 | StrEnum for all fixed values; no raw strings where an enum exists | `grep` for callback-data prefixes, `["ru","bs","en"]`, `("new","used")`, `"contact_us"` duplication | FAIL → QLT-002 |
| R-05 | Every module uses `logging.getLogger(__name__)`, no `print` | `grep "print(" src/` clean on prod; grep `logger =\` confirms module loggers | PASS (style drift → QLT-006) |
| R-06 | Handlers/views delegate; no ORM/validation in presentation | Review `ad_create.py`, `alerts.py`, `listings.py`; contrast `contact.py` delegation to `core/services/contact.py` | FAIL → QLT-001, QLT-003; PASS (contact) |
| R-07 | Module/function size within SRP targets | Line counts via `Measure-Object` | FAIL → QLT-001 (1311), QLT-003 (508) |
| R-08 | Pydantic v2 at bot input + web POST before ORM writes | Review `message_payloads.py` (DTOs), `consent.py` (ConsentSubmission), `edit.py` POST branches | PARTIAL FAIL → QLT-005 |
| R-09 | English-only in comments/logs/errors (non-user-facing) | `grep` cyrillic in `logger.*` calls → none; cyrillic in comments only in tests + `alerts.py:30` | PASS (minor → QLT-007) |
| R-10 | Every schema change has a migration; no in-code DB mutation | `grep` raw SQL → only advisory locks + search-trigger DDL (managed command); git tree clean on source; apps with no models (api/cabinet/seed) correctly have no migrations | PASS |
| R-11 | Shared rules not duplicated in both processes | `can_contact_seller`/`get_seller_for_contact`/`record_*` all delegate to `_check_seller_contactable` in `core/services/contact.py` (web via `contact_tags.py`, bot via `handle_contact_orm`) | PASS |

**Tools used:** `ruff check`, `basedpyright`, `grep`/`Select-String` across `src/`, `Measure-Object -Line`, `git status`, source inspection of handler/view/service files.

**Assumptions:** Production runs Django 5.2 LTS + PostgreSQL 18 with Redis-backed `django-redis` cache; `django-stubs` is NOT installed (per inline comments), so `basedpyright` reports Django-API typing gaps that are suppressed project-wide with `# pyright: ignore[...]`; bot runs as one process sharing the ORM with the web process; `MEMORY`/`LocMemCache` dev/test settings mask the async-boundary cache issues captured in Phase 01.

## Findings Summary

| ID | Title | Severity | Status | Category |
|----|-------|----------|--------|----------|
| QLT-001 | Bot `ad_create.py` (1311 lines) is a god-module: 15+ sync_to_async ORM data-access helpers + business logic embedded in handler | HIGH | Open | Separation of Concerns / SRP |
| QLT-002 | Callback-data protocol tokens & locale list are raw string literals with no StrEnum/enum source of truth (drift breaks routing) | HIGH | Open | StrEnum / Constants |
| QLT-003 | Web `listings.py` (508 lines) fat view embeds filter/sort/pagination/price-parse logic inline in the view | MEDIUM | Open | Separation of Concerns / SRP |
| QLT-004 | Web edit POST text/price-edit path bypasses Pydantic validation (sibling reactivation path validates) | MEDIUM | Open | Boundary validation / Pydantic |
| QLT-005 | Bot i18n inconsistent: alerts.py & ad_create.py emit unwrapped Russian/English strings; contact.py uses Russian msgid; gate scans templates only | MEDIUM | Open | i18n / Conventions |
| QLT-006 | Pervasive f-string logging (49 sites) — inconsistent with `%s` lazy style, not enforced by ruff config | LOW | Open | Logging conventions |
| QLT-007 | Bare `dict`/`list` annotations without type parameters in bot handler (ad_create.py); one cyrillic word in a comment | LOW | Open | Type safety / English-only |

## Findings by Severity

### HIGH

#### QLT-001: [HIGH] — Bot `ad_create.py` (1311 lines) is a god-module embedding data-access + business logic in the handler

| Field | Value |
|---|---|
| **ID** | QLT-001 |
| **Title** | Bot `ad_create.py` (1311 lines) is a god-module embedding data-access + business logic in the handler |
| **Severity** | HIGH |
| **Category** | Separation of Concerns / Single Responsibility |
| **File(s)** | `src/telegram_bot/handlers/ad_create.py:1-1311` (15+ data-access helpers at lines 862-1311) |
| **Status** | Open |
| **Problem** | `ad_create.py` is the ad-creation FSM router AND defines 15+ `sync_to_async`-wrapped ORM data-access helpers (`create_draft_ad`, `delete_draft`, `search_categories`, `get_city_by_name`, `get_all_cities`, `get_category`, `get_city`, `get_lookup_item`, `get_lookup_item_by_slug`, `get_feature_names`, `get_resolved_purposes`, `get_resolved_features`, `get_resolved_conditions`, `get_default_purpose`) plus business-logic helpers (`show_preview`, `_format_preview_price`, `translate_all_languages`) and media helpers (`download_photo`, `save_photo`). The data-access helpers are not bot-specific � they are generic Ad/Category/City/LookupItem lookups that a shared service layer would own, so the web process (separate process, same ORM/DB) cannot reuse them and must re-implement equivalents. |
| **Impact** | (1) Bot and web processes cannot share generic data lookups � each re-implements ORM queries, violating DRY across the process seam. (2) Embedding data-access + formatting logic in the handler makes it untestable in isolation and inflates the module far past SRP. (3) Bare `list`/`dict` return annotations (`get_resolved_purposes() -> list`, `show_preview(data: dict)`) and a redundant `except ValueError, Exception:` (line 600) compound the quality signal. |
| **Root Cause** | No dedicated bot service layer exists for ad data access � the only bot-side service module (`telegram_bot/services/`) contains only `rate_limit.py`. All ORM/data-access helpers were inlined into the handler for convenience, mixing presentation, data-access, and business logic. |
| **Recommendation** | (1) Extract the 15+ data-access helpers into `telegram_bot/services/ad_data.py`, or where generic, into the backend service layer (`apps/ads/services/`, `apps/locations/services/`, `apps/lookups/services/`) so the web process can import them. (2) Keep handlers thin: translate FSM state to/from UI messages only. (3) Replace bare `list`/`dict` with parameterized generics; fix `except ValueError, Exception:` to `except (ValueError, ArithmeticError):`. |
| **Effort** | M |
| **Priority** | P1 |

**Evidence � `src/telegram_bot/handlers/ad_create.py`** *(supports: 15+ sync_to_async ORM helpers inlined in the handler; module is 1311 lines; bare `list`/`dict` annotations; redundant except)*: the helper section runs `ad_create.py:859-1311`.
```python
async def get_resolved_purposes(category_id: int) -> list:     # line 1087 � bare list + ORM in handler
    @sync_to_async
    def _get():
        cat = Category.objects.get(id=category_id)                # raw ORM in handler
        return list(resolver.get_resolved_purposes(cat))
    return await _get()

async def show_preview(message: types.Message, data: dict) -> None:  # line 721 � bare dict
async def _format_preview_price(data: dict) -> str:                  # line 767 � bare dict
except ValueError, Exception:                                         # line 600 � redundant
```

**Contrast � `telegram_bot/services/` contains only `rate_limit.py`** *(supports: no shared service layer for ad data access, confirming helpers were inlined by convenience)*.

**Contrast � correct delegation pattern in `contact.py:230-242`** *(supports: the codebase has the right pattern elsewhere, confirming ad_create.py is the deviation)*: `handle_contact_orm` delegates R2 gating + analytics to `apps.core.services.contact` instead of inlining ORM.
---

#### QLT-002: [HIGH] � Callback-data protocol tokens & locale list are raw string literals with no StrEnum/enum source of truth

| Field | Value |
|---|---|
| **ID** | QLT-002 |
| **Title** | Callback-data protocol tokens & locale list are raw string literals with no StrEnum/enum source of truth |
| **Severity** | HIGH |
| **Category** | StrEnum / Constants (phase dimension b) |
| **File(s)** | `src/telegram_bot/handlers/ad_create.py` (300,308,330,337,365,376,377,511-517,536,548-549,1265,1281,1294-1295,1305,1307); `language.py:27,98`; `alerts.py:31,141,148`; `login.py:61`; `ad_create.py:804,808` |
| **Status** | Open |
| **Problem** | Bot callback-data protocol tokens are raw string literals with no centralized constant/enum, and the SAME prefix appears in two places that must stay in lock-step: (a) the `lambda c: c.data.startswith(PREFIX)` filter on the router decorator, and (b) the `callback_data=f"{PREFIX}..."` builder. If the prefix changes in only one site, the bot silently stops recognizing that callback class. In `ad_create.py`: `purpose:` (filter 300 vs builder 1265), `condition:` (330 vs 1281), `feature:` (376 vs 1305), `price_currency:` (548 vs builder 511-515), `price_free` (536 vs 517), `features_done` (365 vs 1307). Additionally `login.py:61` hardcodes `callback_data="contact_us"` rather than reusing `CONTACT_US_CALLBACK` from `contact.py:34` � direct duplication. Separately, `translate_all_languages` is called with a raw `["ru", "bs", "en"]` list (ad_create.py:804,808) instead of `LanguageLocale.values()`, despite that `StrEnum` existing in `core/enums.py`. |
| **Impact** | A one-character typo or prefix rename in only the filter (or only the builder) makes an entire callback family silently dead � the handler receives the callback but no route matches. Because filters are dynamic `lambda`s (not enum-gated), the breakage is silent: no lint, no type error, no test necessarily. The `["ru","bs","en"]` literal can drift from `LanguageLocale` if a locale is added or removed. |
| **Root Cause** | aiogram callback-data tokens are conventionally plain strings, so the codebase never modeled them as a `StrEnum`/`Final` constant set; prefixes were inlined at use sites. The locale list was hand-written rather than deriving from the existing `LanguageLocale` enum. |
| **Recommendation** | (1) Introduce a `BotCallbackPrefix` StrEnum in `telegram_bot/schemas/callbacks.py` imported by both filter lambdas and builders. (2) Replace `["ru","bs","en"]` with `LanguageLocale.values()`. (3) Remove the `"contact_us"` literal in `login.py:61` and import `CONTACT_US_CALLBACK` from `contact.py`. |
| **Effort** | S |
| **Priority** | P1 |

**Evidence � callback-data prefix duplicated between filter lambda and builder** *(supports: prefix must stay in lock-step; drift silently breaks routing)*:
```python
# ad_create.py:300  (filter on the decorator)
@router.callback_query(AdCreateForm.purpose, lambda c: c.data and c.data.startswith("purpose:"))
# ad_create.py:1265 (builder)
        builder.button(text=text, callback_data=f"purpose:{purpose.slug}")
```

**Evidence � `login.py:61` duplicates `contact_us` as a raw string** *(supports: the constant exists at contact.py:34 but login.py hardcodes the same literal)*:
```python
# contact.py:34
CONTACT_US_CALLBACK: Final[str] = "contact_us"
# login.py:61
                            text="Contact us", callback_data="contact_us"
```

**Evidence � raw locale list vs existing LanguageLocale enum** *(supports: `["ru","bs","en"]` literal ignores the canonical enum)*:
```python
# ad_create.py:804,808
title_translations = await translate_all_languages(original_title, ["ru", "bs", "en"])
desc_translations = await translate_all_languages(orig_desc, ["ru", "bs", "en"])
# core/enums.py:197-200
    @classmethod
    def values(cls) -> list[str]:
        return [m.value for m in cls]   # canonical source � not used by the call site
```

### MEDIUM

#### QLT-003: [MEDIUM] � Web `listings.py` (508 lines) fat view embeds filter/sort/pagination logic inline

| Field | Value |
|---|---|
| **ID** | QLT-003 |
| **Title** | Web `listings.py` (508 lines) fat view embeds filter/sort/pagination logic inline in the view |
| **Severity** | MEDIUM |
| **Category** | Separation of Concerns / Single Responsibility |
| **File(s)** | `src/backend/apps/ads/views/listings.py:201-480` (the `listings()` function, ~280 lines); module totals 508 lines |
| **Status** | Open |
| **Problem** | The `listings()` function (lines 201-480) performs request-parameter parsing, queryset filtering (category subtree via `get_descendants`, city resolution + did-you-mean via `suggest_city`, price-range `int`/`Decimal` coercion, listing-purpose/condition/features slug filters with `distinct()`), sort mapping (`if/elif` against `AdSort`), favorite-state annotation (`annotate_favorites`), pagination (`Paginator`), and context assembly � all inline in the view. None of this filtering/sorting logic is delegated to a service/query-builder, so it is untestable outside a full HTTP request and is not reusable by other views (e.g. the search view re-implements parallel filter logic). |
| **Impact** | A 280-line view is hard to review, test, and maintain; filter logic that could be shared is duplicated conceptually across `listings.py` and `search/views/search.py`. Manual `int`/`Decimal` coercion (lines 340-364) silently swallows `ValueError` rather than validating via a DTO. A small change to a filter predicate risks the 250+ line function. |
| **Root Cause** | The MPA HTMX pattern encourages request-orchestration in the view, so filter/sort/pagination logic was written directly in `listings()` rather than extracted to a query service. |
| **Recommendation** | Extract a `ListingsQuery` service (e.g. `apps/ads/services/listings_query.py`) that accepts parsed params (ideally a Pydantic DTO) and returns a `QuerySet`/paginated result; the view becomes a thin adapter (parse params ? call service ? render). This mirrors how `contact.py`/`alerts.py` delegate to `apps/core/services` and `apps/search/services/alert_query.py`. |
| **Effort** | M |
| **Priority** | P2 |

**Evidence � `src/backend/apps/ads/views/listings.py:201-480`** *(supports: ~280-line view mixing param parsing, filtering, sort, pagination, context)*:
```python
def listings(request, category_slug=None, city_slug=None):           # line 201
    ...
    # Category filter (subtree)                                       # line 274
    # City filter with did-you-mean                                     # line 304
    # Price range filter with manual int/Decimal coercion               # line 332
    # Listing purpose / condition / features filters                    # line 366
    # Sorting: if/elif against AdSort                                   # line 413
    # Annotate favorites, Paginate, build context                       # line 429
    return render(request, "ads/list.html", context)                  # line 480
```

#### QLT-004: [MEDIUM] � Web edit POST text/price-edit path bypasses Pydantic validation (sibling reactivation path validates)

| Field | Value |
|---|---|
| **ID** | QLT-004 |
| **Title** | Web edit POST text/price-edit path bypasses Pydantic validation (sibling reactivation path validates) |
| **Severity** | MEDIUM |
| **Category** | Boundary validation / Pydantic (phase dimension f) |
| **File(s)** | `src/backend/apps/ads/views/edit.py:112-263` (text-edit + price-edit branches, no DTO); contrast `edit.py:178-191` (reactivation uses `SubmitAdInput`) and `consent.py:112` (`ConsentSubmission.model_validate`) |
| **Status** | Open |
| **Problem** | The `ad_edit` POST handler reads `request.POST.get("title")`, `request.POST.get("description")`, `request.POST.get("price_amount")`, `request.POST.get("price_currency")` directly with manual `.strip()` + `Decimal()` coercion (lines 134-159) and writes to the ORM via `ad.save(update_fields=...)` (lines 217-226, 234-241) � without any Pydantic DTO. This bypasses the project rule that every web form POST is validated by Pydantic v2 before an ORM write. The sibling reactivation branch (line 178) DOES validate via `SubmitAdInput(...)`, and `consent.py:112` validates via `ConsentSubmission` � so the boundary coverage is inconsistent: the most-common edit path is unvalidated while the less-common reactivation path is. |
| **Impact** | Title/description length, price range, and currency validity are only enforced reactively (by `auto_moderate` after save, or by `Decimal()` falling back to 0). Invalid/oversized input is persisted to the DB before rejection, widening the window for the bad row to be read by concurrent requests. The inconsistency also means future ad-validation rules added to `SubmitAdInput` won't automatically cover the standard edit path. |
| **Root Cause** | The edit view was written before/around the shared `SubmitAdInput` DTO, so the text/price branches parse POST ad-hoc while the reactivation branch was refactored to use the DTO. |
| **Recommendation** | Route all `ad_edit` POST branches through a Pydantic edit DTO (e.g. extend `SubmitAdInput` or add `AdEditInput` with `title`/`description`/`price_amount`/`price_currency`/`photos` fields and validation) and validate before any ORM write, mirroring `consent.py`'s `_parse_submission` pattern. |
| **Effort** | M |
| **Priority** | P2 |

**Evidence � `src/backend/apps/ads/views/edit.py:134-159`** *(supports: POST parsed ad-hoc, no DTO, then written at line 217)*:
```python
new_title = (request.POST.get("title") or "").strip()          # line 134 � raw POST, no DTO
new_description = (request.POST.get("description") or "").strip()
new_price_amount = request.POST.get("price_amount")
...
price_amount_value = Decimal("0")
if new_price_amount not in (None, ""):
    try:
        price_amount_value = Decimal(new_price_amount)          # manual coercion
    except Exception:
        price_amount_value = Decimal("0")                      # silent fallback to Free
...
ad.title = new_title; ad.description = new_description
ad = _apply_price_change(ad, ...)
ad.save(update_fields=[...])                                   # line 217 � ORM write, no validation
```
**Contrast � `src/backend/apps/ads/views/edit.py:178`** *(supports: the reactivation branch validates via the DTO, proving the standard branch is the gap)*: `passed, errors = submit_ad(SubmitAdInput(ad_id=ad_id, title_ru=new_title, ...))`.

#### QLT-005: [MEDIUM] � Bot i18n inconsistent: unwrapped strings, Russian msgids, template-only gate

| Field | Value |
|---|---|
| **ID** | QLT-005 |
| **Title** | Bot i18n inconsistent: alerts.py & ad_create.py emit unwrapped Russian/English strings; contact.py uses Russian msgid; completeness gate scans templates only |
| **Severity** | MEDIUM |
| **Category** | i18n / Conventions (phase dimension g) |
| **File(s)** | `src/telegram_bot/handlers/alerts.py` (no `_` import; Russian strings at 50,119,127,138,153,161,172,199,203-204); `src/telegram_bot/handlers/ad_create.py` (no `_` import; hardcoded Russian at 147); `src/telegram_bot/handlers/contact.py:175,179,188,247` (Russian msgid text); `src/backend/apps/ads/tests/test_i18n_completeness.py:8,11,115,147,184-203` (gate scope) |
| **Status** | Open |
| **Problem** | Bot handlers apply i18n (`rule #16: i18n is part of DoD`) inconsistently: (1) `alerts.py` and `ad_create.py` do NOT import `gettext`/`_` and emit raw string literals to users � `alerts.py` in Russian (`"?? ??????? ????????? ???????????"`, `"??????????? ?????????"`, `"?? ????????? ???? ?????"`) and `ad_create.py` mixing English messages with a hardcoded Russian fallback (`"Top-level categories: ??????, ??????, ????????????"` at line 147). (2) `contact.py` wraps strings in `_()` but uses Russian as the msgid (`_("?????????? ?????? ??????????")`, `_("Отключить")`) � violating the Django convention that msgids be English (so `en`/`bs` catalogs keyed on a Russian source msgid produce wrong output). (3) The i18n completeness gate (`test_i18n_completeness.py`) scans templates only and explicitly excludes the bot; there is no test asserting bot strings are wrapped or that msgids are English. |
| **Impact** | Bot output is effectively Russian-only for non-English users: the `en`/`bs` locales cannot be satisfied because (a) most strings are never extracted (no `_()`), and (b) where `_()` is used the msgid is Russian so the catalog lookup is inconsistent. The gate gives false confidence � `make compilemessages` + the completeness tests pass while the bot ships untranslated. |
| **Root Cause** | The bot was written for a Russian/Bosnian audience with ad-hoc localization; the i18n pipeline (rule #16, `makemessages`) was designed around Django templates and never extended to bot string literals. |
| **Recommendation** | (1) Wrap ALL user-facing bot strings in `gettext`/`_()` across `ad_create.py` and `alerts.py` (add the import). (2) Make msgids English in `contact.py` (use English msgid + Russian translation in the `.po`), not Russian-as-msgid. (3) Extend the i18n completeness gate (or add a `test_bot_i18n.py`) to assert bot handlers have no bare user-facing string literals and no non-English msgids. |
| **Effort** | M |
| **Priority** | P2 |

**Evidence � `alerts.py` has no `gettext` import; Russian strings emitted raw** *(supports: unwrapped user-facing Russian)*:
```python
# alerts.py imports (lines 11-21) � NO `from django.utils.translation import gettext as _`
import logging
import re
from aiogram import F, Router, types
from apps.search.models import SavedSearch
...
await callback.answer("?? ??????? ????????? ???????????")   # line 119 � raw Russian, unwrapped
await callback.answer("??????????? ?????????")               # line 138 � raw Russian, unwrapped
```
**Evidence � `ad_create.py` hardcoded Russian inside an English message** *(supports: mixed-language, unwrapped)*: `ad_create.py:147`:
```python
        await message.answer(
            "No categories found. Please try another keyword. "
            "Top-level categories: ??????, ??????, ????????????"   # hardcoded Cyrillic, not extracted
        )
```
**Evidence � `contact.py` uses Russian as the msgid** *(supports: msgid convention violation)*: `contact.py:175,247`:
```python
await message.answer(_("?????????? ?????? ??????????"))      # Russian msgid
ANONYMOUS_BUYER_LABEL = _("Отключить")                      # Russian msgid
```

### LOW

#### QLT-006: [LOW] � Pervasive f-string logging (49 sites) inconsistent with lazy `%s` style

| Field | Value |
|---|---|
| **ID** | QLT-006 |
| **Title** | Pervasive f-string logging (49 sites) inconsistent with lazy `%s` style, not enforced by ruff |
| **Severity** | LOW |
| **Category** | Logging conventions |
| **File(s)** | 49 sites across `ads/views/{listings,edit,delete}.py`, `media/services/filesystem.py`, `moderation/{admin_actions,services/{auto_moderation,moderation_log}.py,views/review.py}`, `users/services/{account_state,deletion}.py`, `users/views/consent.py`, `telegram_bot/handlers/ad_create.py` |
| **Status** | Open |
| **Problem** | 49 call sites use `logger.*(f"...")` (ruff rule G004) while the shared service layer in the same codebase consistently uses lazy `%s` formatting (e.g. `contact.py:115` `logger.info("Contact initiated event recorded for buyer %s", user_id)`, `core/services/analytics.py`). The project's ruff config does NOT enable G004 (default `ruff check` passes clean), so the inconsistency is unguarded. |
| **Impact** | F-string logging eagerly formats the message string and interpolates all arguments before the logger level check � wasted CPU on production INFO logs that may be filtered, and inconsistent style across the codebase makes it harder to grep/structure log output. Low operational impact but a real maintainability smell. |
| **Root Cause** | Mixed authoring style: view/handler authors used f-strings; service authors used `%s`. No style rule (G004) was enabled to enforce one. |
| **Recommendation** | Enable ruff rule `G004` (or `flake8-logging-format`) in `pyproject.toml` and run `ruff check --fix` to canonicalize to lazy `%s` formatting project-wide. |
| **Effort** | S |
| **Priority** | P2 |

**Evidence � `ruff check --select G004` reports 49 violations** *(supports: pervasive, unguarded f-string logging)*:
```text
G004 Logging statement uses f-string
  --> src/backend/apps/ads/views/edit.py:108:13   (12 hits in edit.py alone)
  ...
  --> src/telegram_bot/handlers/ad_create.py:953:22
  --> src/telegram_bot/handlers/ad_create.py:1000:28
Found 49 errors.
```
**Evidence � contrast: same codebase uses lazy `%s`** *(supports: the canonical style exists in the service layer)*: `src/backend/apps/core/services/contact.py:115`:
```python
    logger.info("Contact initiated event recorded for buyer %s", user_id)
```

#### QLT-007: [LOW] � Bare `dict`/`list` annotations in bot handler; one Cyrillic word in a comment

| Field | Value |
|---|---|
| **ID** | QLT-007 |
| **Title** | Bare `dict`/`list` annotations in bot handler (ad_create.py); one Cyrillic word in a comment |
| **Severity** | LOW |
| **Category** | Type safety / English-only |
| **File(s)** | `src/telegram_bot/handlers/ad_create.py:721,767,1087,1112,1137,1157,1249,1272,1287`; `src/telegram_bot/handlers/alerts.py:30` |
| **Status** | Open |
| **Problem** | `ad_create.py` uses bare `dict` and `list` (no type parameters) in 8 signatures � `show_preview(data: dict)`, `_format_preview_price(data: dict)`, `get_resolved_purposes(...) -> list`, `get_resolved_conditions(...) -> list`, `get_default_purpose(..., purposes: list)`, `build_condition_keyboard(conditions: list)`, `build_feature_keyboard(features: list, selected_ids: set)` � undermining the strict-typing rule. Additionally `alerts.py:30` contains a Cyrillic word in an otherwise-English comment: `# Re-enable callback prefix (complements the "Отключить" button).` |
| **Impact** | Bare generics hide element types from readers and the type-checker, weakening the "strict type hints everywhere" guarantee for the bot's public handler API. The Cyrillic comment is a minor English-only drift. |
| **Root Cause** | Author convenience / incompleteness in adding type parameters; the Cyrillic word is a literal translation of the button label embedded in a comment. |
| **Recommendation** | (1) Parameterize the bare `dict`/`list`/`set` annotations (e.g. `data: dict[str, object]`, `-> list[LookupItem]`, `selected_ids: set[int]`). (2) Replace the Cyrillic word in the comment with English (`"Disable"`). |
| **Effort** | S |
| **Priority** | P2 |

**Evidence � bare annotations in `ad_create.py`** *(supports: 8 bare `dict`/`list`/`set` signatures)*:
```python
async def show_preview(message: types.Message, data: dict) -> None:           # line 721
def _format_preview_price(data: dict) -> str:                                  # line 767
async def get_resolved_purposes(category_id: int) -> list:                      # line 1087
async def get_resolved_features(category_id: int) -> list:                     # line 1112
async def get_resolved_conditions(category_id: int) -> list:                    # line 1137
async def get_default_purpose(category_id: int, purposes: list) -> ...:        # line 1157
def build_condition_keyboard(conditions: list) -> ...:                         # line 1272
def build_feature_keyboard(features: list, selected_ids: set) -> ...:          # line 1287
```
**Evidence � `alerts.py:30`** *(supports: one Cyrillic word in an English comment)*:
```python
# Re-enable callback prefix (complements the "Отключить" button).
```

---

### Cross-Finding Analysis

All seven findings trace to two root gaps rather than seven isolated bugs:

| Gap | Finding(s) | Fix surface |
|---|---|---|
| **Callback-data tokens are treated as ad-hoc strings, not modeled constants** | QLT-002 (HIGH) | Introduce `BotCallbackPrefix` StrEnum + route both filter-lambdas and builders through it; remove the `contact_us` duplication in `login.py:61`. |
| **`webedit` POST is the only web form path not validated by a Pydantic DTO before ORM write** � the inconsistency itself is the risk | QLT-004 (MEDIUM) | Extend `SubmitAdInput`-style DTO coverage to the standard edit path; the reactivation branch already proves the pattern works. |
| (secondary) Fat web views are tolerated by the MPA stack, so the SoC smell is concentrated in `listings.py` (QLT-003); bot i18n was never part of the extraction pipeline (QLT-005); logging style and bare annotations are unguarded (QLT-006, QLT-007). | QLT-001, 003, 005, 006, 007 | Thin-view service extraction; wrap bot strings + English msgids; enable G004; parameterize generics. |

**No finding here contradicts phase 01�09 audit evidence** � QLT-005 confirms the bot i18n gap that phase 10's `test_i18n_completeness.py` scope (templates-only) leaves out of coverage; QLT-004 matches the `SubmitAdInput` DTO already referenced in the spec.

### Remediation Roadmap

| Priority | Finding | Effort | Dependency | Notes |
|---|---|---|---|---|
| P1 | QLT-002 | S | none | Highest leverage: silent callback death on prefix drift. |
| P1 | QLT-001 | S | none (bot side only) | Bot refactor; no web risk. |
| P2 | QLT-004 | M | none | Align edit path onto existing DTO pattern. |
| P2 | QLT-003 | M | none (web side) | Extract `ListingsQuery`; optional follow-up to de-dup vs `search.py`. |
| P2 | QLT-005 | M | i18n pipeline | Bot strings ? `_()` + English msgids; extend gate. |
| P2 | QLT-006 | S | ruff config | `G004` enable + `ruff check --fix`. |
| P2 | QLT-007 | S | none | Parameterize generics; one comment edit. |

> Ordering rationale: QLT-002 and QLT-001 are bot-only and lowest-risk to ship; QLT-004/QLT-003 are web-touching and should be validated against the existing ad-creation tests (`AdCreateInput`/`SubmitAdInput`); QLT-005/006/007 are cleanup with no behavioural change.

### Rollout Safety

The findings file is produced under `.ai/audit/10-code-quality/findings.md` (gitignored `.ai/` is audit scratch). To persist it in the repo (per project doc-maintenance rules), move to `docs/99-audit/10-code-quality.md` and add to `docs/01-spec/spec-index.md` audit index before committing. No production code is modified by this phase; all recommendations are **advisory**. Recommended verification before acting on any item: run `make test` (fast gate, skips `seed`) in the `mko-bazuna-test` compose project and confirm the ad-creation + i18n completeness tests remain green.

---

### Appendices

#### Appendix A � Severity Counts

| Severity | Count | IDs |
|---|---|---|
| CRITICAL | 0 | � |
| HIGH | 2 | QLT-001, QLT-002 |
| MEDIUM | 3 | QLT-003, QLT-004, QLT-005 |
| LOW | 2 | QLT-006, QLT-007 |
| **Total** | **7** | |

#### Appendix B � Assumptions

- StrEnum is the project's canonical constant form (rule #10; `StrEnum` examples at `apps/core/enums.py:197`, `apps/ads/models.py:52`).
- `gettext`/`gettext_lazy` is the correct i18n API for Python (rule #16).
- `SubmitAdInput` (referenced in `edit.py:178`) is a Pydantic v2 DTO � validated by `consent.py` precedent (`ConsentSubmission`).
- Web layer is gunicorn sync WSGI (HTMX MPA); bot is aiogram 3.x (`aiogram 3.x` per AGENTS.md).
- Audit scratch path `.ai/audit/` is local-only; persistence step is advisory.

#### Appendix C � Files Inventoried (this phase)

Scope: StrEnum/violations, Pydantic-boundary adherence, i18n, logging style, SoC/size, type annotations across the two processes sharing the ORM.

| Area | File(s) sampled | Method |
|---|---|---|
| Bot � ad create (god module) | `src/telegram_bot/handlers/ad_create.py` (471 lines) | grep `startswith` vs `f"{prefix:"`; `def ` outline; `_` import absent |
| Bot � callback protocol | `ad_create.py` (filter/builder pairs); `login.py:61`; `contact.py:34` | grep `callback_data=`, `startswith` |
| Bot � i18n | `ad_create.py`, `alerts.py`, `contact.py` | grep `gettext`/`_` import; Russian literals |
| Bot � logging | `ad_create.py`, `alerts.py` | ruff `--select G004` + grep `logger` |
| Web � listings | `apps/ads/views/listings.py` (508) | grep `^def ` + line range |
| Web � edit | `apps/ads/views/edit.py` | grep `request.POST.get`, `ad.save`, `SubmitAdInput` |
| Web � consent (counter-example) | `apps/users/views/consent.py` | grep `model_validate`, `SubmitAdInput` |
| Core � enums | `apps/core/enums.py` (StrEnum) | grep `class LanguageLocale` |
| i18n gate | `apps/ads/tests/test_i18n_completeness.py` | read scope lines 115,147,184-203 |

(Modules deliberately large-but-correct by design � see R# note: `consent.py:448` delegates to `apps.users.services`; `search.py:373` was in-scope of phase 08 and is thin. These are recorded but not filed as SoC violations.)

#### Appendix D � Validation Checklist

- [x] Findings grounded in file path + line number + code snippet
- [x] Each finding has Severity, Effort, Priority, Recommendation
- [x] Cross-Finding Analysis ties findings to root gaps
- [x] Remediation Roadmap ordered by dependency + risk
- [x] Rollout Safety notes persistence path + test gate
- [ ] Persistence: move `.ai/audit/10-code-quality/findings.md` ? `docs/99-audit/10-code-quality.md` and register in `docs/01-spec/spec-index.md` audit index (pending user confirmation)
- [ ] Follow-up: re-run `ruff check --select G004` after recommendation to confirm 0 (or stable) before enabling rule
