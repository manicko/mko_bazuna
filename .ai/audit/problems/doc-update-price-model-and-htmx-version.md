# Documentation Discrepancy Report — Zero-Based Pricing & Site Name Centralization

**Date:** 2026-09-02
**Context:** Analysis of 5 source plan documents against current codebase implementation and existing project documentation.

---

## Summary

| # | Discrepancy | Spec/Plan Source | Current Code | Impact |
|---|---|---|---|---|
| D1 | Plan 19 (SiteConfig) specifies an admin-configurable site name model with shared cache, bot/web injection, and RunPython data migration | `.ai/plans/19_site-name_centralization_plan.md` (T1–T11) | Not implemented — no `SiteConfig` model, no `site_config` service, no template replacements, all 22 "Mko Bazuna" occurrences still hardcoded | Planned functionality not yet built; cannot be documented as implemented |
| D2 | Existing docs say bot price step is "price (if applicable)" | `docs/01-spec/technical-specification.md` (line 148); `docs/04-user-stories/seller-stories.md` (line 35) | Price is mandatory: `Ad.price_amount` is `null=False, default=Decimal("0")`; bot has no Skip option, explicit Free button sets `Decimal("0")` | Stale spec contradicts implemented behavior; docs must be updated to "mandatory, zero = Free" |
| D3 | `db-schema.md` documents `price_amount` as nullable | `docs/09-database/db-schema.md` (line 134) | Model field is `null=False, default=Decimal("0")` (non-null, mandatory) | Schema doc is factually incorrect |
| D4 | Templates/docs show `{% if ad.price_amount %}` (truthiness) for price display | `docs/01-spec/ui-patterns.md` (line 69); `docs/01-spec/design-system.md` (line 443); `docs/06-design-system/components.md` (lines 387, 475) | Actual templates use `{% if ad.price_amount is not none %}` — truthiness would hide Free (price=0) ads | Docs show pre-implementation pattern that would hide Free ads |
| D5 | No documentation of "Free" label for zero-price display | All docs (checked: ui-patterns, design-system, components, search-patterns) | `format_price_value()` returns `gettext("Free")` for `amount == 0` | Significant display behavior missing from documentation |
| D6 | `filter-ui.md` shows clear-all as plain `<a href>` link to `{% url 'ads:list' %}` | `docs/01-spec/filter-ui.md` (lines 376–383) | `ad_list.html` uses `<a hx-get="?page=1&lang=…" hx-push-url="true">` — preserves path params (category/city), resets all query params including q/sort | Docs show wrong implementation mechanism |
| D7 | `search-patterns.md` describes price sort as "placing ads with no price (NULL) last" | `docs/01-spec/search-patterns.md` (line 163) | Price is never NULL (default=0); zero-price (Free) ads sort last via `price_normalized_eur.asc(nulls_last=True)` | Stale description contradicts non-null price model |
| D8 | Docs reference HTMX 1.9.12 | `docs/01-spec/ui-patterns.md` (line 289); `docs/96-researches/htmx_dropdown_breadcrumb_patterns_research.md` | All 5 page templates load HTMX 2.0.10 from jsDelivr CDN with SRI; `htmx.ajax` used (not `htmx.get`) | Version pinning is stale; security (SRI) not documented |

---

## Detailed Discrepancy Records

### D1: SiteConfig Planned but Not Implemented

**Plan/Spec source:** `.ai/plans/19_site-name_centralization_plan.md` (T1–T11)

**Planned behavior:**
- `SiteConfig` singleton model in `apps/core/models.py`
- `get_site_name()` / `get_site_name_async()` service in `apps/core/services/site_config.py`
- `site_config` context processor in `apps/core/context_processors.py` registered in `base.py`
- Bot greeting injection in `login.py` and `ad_create.py`
- `post_save` cache invalidation signal with Redis/LocMem cache
- `0001_initial.py` + `0002_seed_default.py` migrations (RunPython seed)
- 22 hardcoded "Mko Bazuna" → `{{ site_name }}` replacements across templates
- 3 new i18n msgids extracted via makemessages

**Current code (verified by researcher):**
- No `apps/core/models.py` exists — `apps/core/` has only `__init__.py`, `apps.py`, `context_processors.py`, `enums.py`, `urls.py`, `views.py`, `tests/`, and `migrations/__init__.py` (non-migrated app)
- `context_processors.py` has `plausible_host`, `language`, `header_context` — no `site_config`
- `cache.py` has `CRITERIA_CACHE_*` helpers only — no `SITE_CONFIG_CACHE_*`
- Bot greetings in `login.py` L47–49 and `ad_create.py` L122–125 still hardcoded
- All 22 "Mko Bazuna" occurrences remain as `{% trans "Mko Bazuna" %}` or raw text

**Classification:** Advisory — planned functionality not yet implemented. Documentation cannot describe features that do not exist in code. Recommend documenting this as planned/in-progress in `docs/05-owner-decisions/index.md` or noting the gap.

---

### D2: Price Step Described as "if applicable" but Implemented as Mandatory

**Plan/Spec source:** `docs/01-spec/technical-specification.md` line 148; `docs/04-user-stories/seller-stories.md` line 35; `.ai/plans/done/18_price-enforcement_and-filter-reset_plan.md` (T3, T4)

**Planned/specified behavior (plan 18):**
- Price is mandatory: `Ad.price_amount` is `null=False, default=Decimal("0")`
- Zero = Free/Charity, explicitly enterable
- Bot has explicit "Free" button (callback `price_free`), no "Skip" option
- `PricePayload.price_amount` is `Decimal` (not `Decimal | None`)

**Current code (verified):**
- `apps/ads/models.py`: `price_amount = DecimalField(max_digits=10, decimal_places=2, null=False, blank=False, default=Decimal("0"))`
- `telegram_bot/handlers/ad_create.py`: `build_currency_keyboard` renders "🆓 Free" + 4 currency buttons; no Skip button; `process_price_currency` handles `price_free` callback setting `Decimal("0.00")`
- `schemas/message_payloads.py`: `price_amount: Decimal = Field(ge=0)`

**Discrepancy:** Docs say "price (if applicable)" — contradicts the implemented mandatory-price model.

---

### D3 through D8: Documentation Accuracy Issues

These are documentation-only discrepancies (docs don't match implemented code):

| # | Doc file | Stale claim | Current reality |
|---|---|---|---|
| D3 | `db-schema.md:134` | `price_amount (DECIMAL(10,2), nullable)` | `null=False, default=Decimal("0")` |
| D4 | `ui-patterns.md:69`, `design-system.md:443`, `components.md:387,475` | `{% if ad.price_amount %}` | `{% if ad.price_amount is not none %}` |
| D5 | All price display docs | No mention of "Free" label | `format_price_value` returns `gettext("Free")` for `0` |
| D6 | `filter-ui.md:376-383` | `<a href="{% url 'ads:list' %}">` plain link | `<a hx-get="?page=1&lang=…" hx-push-url="true">` preserving path params |
| D7 | `search-patterns.md:163` | "no price (NULL) last" | Price never NULL; Free (price=0) sorts last |
| D8 | `ui-patterns.md:289` | "HTMX 1.9.12 is loaded" | HTMX 2.0.10 from jsDelivr CDN with SRI |

---

## Doc Updates Applied

The following documentation files are updated as part of this task to resolve D2–D8:

- `docs/02-database/db-schema.md` — price_amount schema corrected (D3)
- `docs/01-spec/ui-patterns.md` — price display Free label, `is not none` check, HTMX version (D4, D5, D8)
- `docs/01-spec/design-system.md` — price display Free label, `is not none` check (D4, D5)
- `docs/06-design-system/components.md` — price display Free label, `is not None` check (D4, D5)
- `docs/01-spec/technical-specification.md` — price mandatory in bot FSM (D2)
- `docs/04-user-stories/seller-stories.md` — price mandatory in US-S2 (D2)
- `docs/01-spec/search-patterns.md` — price sort description updated (D7)
- `docs/01-spec/filter-ui.md` — clear-all implementation corrected, price-range summary block added (D6)
- `docs/01-spec/spec-index.md` — price model entry updated (D2)

D1 (SiteConfig not implemented) is recorded here but requires no doc update — the feature does not exist in code. See `.ai/plans/19_site-name_centralization_plan.md` for the implementation plan.
