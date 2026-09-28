---
# Report metadata — fill once per phase report.
phase: "14"
phase_name: "i18n"
date: "2026-09-28"
auditor: "Executor (subagent)"
validator: ""  # Phase 99 only — omit/blank for raw phase findings
mode: "problems-only"
id_prefix: "I18N"
report_status: "draft"
severity_taxonomy: ".kilo/commands/audit/phases/14-audit-i18n.md#severity-taxonomy"
---

# Audit Findings — i18n

## Executive Summary

The multi-language site is mostly well built: the language switcher works, the automated
check that every visible word is translated passes, and seller notifications are correctly
sent in each buyer's own language. This audit found 15 issues. The two that matter most to
business are (1) a language-preference cookie that is trusted without any checking, so a
single bad cookie value can make the entire site show Russian category, city, product and
description text to a visitor who selected English or Bosnian, and (2) prices and timestamps
being formatted with US conventions on a site for Montenegro and Bosnia — prices with a dot
instead of a comma in Russian and Bosnian, and all dates computed in the America/Chicago
time zone. Neither is a crash; both are wrong-by-default output that a seller or buyer could
act on incorrectly. No finding requires an architectural change; all fixes are localized.

## Scope & Methodology

**Scope:** Runtime locale resolution and its cookie/param/header priority chain, the
`locale → ru → name` fallback accessors on `Category`/`City`/`LookupItem`/`Ad`, per-user
Telegram language propagation into bot handlers and alerts, the submenu fragment cache key,
the `test_i18n_completeness.py` / `test_i18n_pipeline.py` gate and its exemptions, `.po`/`.mo`
catalogues for `ru`/`bs`/`en`, `{% trans %}`/`gettext` wrapping across
`src/backend/templates/` and `src/telegram_bot/`, Django `verbose_name`/`help_text`/admin
labels, and date/number/currency format localization. `src/templates/` was inspected and is
empty. No code, `.po`, or `.mo` file was modified.

### Runtime Verification

| R# | Check | Method | Result |
|----|-------|--------|--------|
| R-01 | Locale priority `?lang=` > cookie > `Accept-Language` > default | Read-only `RequestFactory` probe driving `LanguagePreMiddleware` in the `mko-bazuna-test` container (`.ai/tmp/probe_locale.py`, deleted) | PASS |
| R-02 | `?lang=en-US` normalizes to `en` | same probe | PASS |
| R-03 | Unsupported code falls back to `bs` and does **not** persist a cookie | same probe (`?lang=de`, `Accept-Language: fr`) | PASS (per spec) |
| R-04 | `lang_pref` cookie value is normalized/validated like the param | same probe with `lang_pref=en-US`, `EN`, `xx` | **FAIL** → I18N-001 |
| R-05 | `locale → ru → name` fallback on Category/City/LookupItem/Ad | Probe over unsaved model instances per locale string (`.ai/tmp/probe_locale2.py`) | PASS for canonical codes; **FAIL** for non-canonical → I18N-001 |
| R-06 | `lang_pref` cookie TTL is ~1 year and the value is persisted | Probe of `response.cookies` | PASS (`Max-Age=31536000`) |
| R-07 | Submenu cache key carries a `<locale>` segment | Read `apps/categories/views.py:51`; `grep category:submenu` | PASS |
| R-08 | Per-user Telegram language reaches bot handlers and both alert paths | Read `telegram_bot/middlewares/language.py`, `apps/search/services/immediate_alerts.py:134`, `apps/search/management/commands/send_alerts.py:225` | PASS |
| R-09 | Completeness gate passes | `docker compose … run --rm -e PYTEST_OPTS="…test_i18n_completeness.py …test_i18n_pipeline.py …test_i18n_category_city.py -q" test` → 27 passed | PASS |
| R-10 | No `{% trans %}` msgid is missing from any `.po` | `makemessages -l ru -l bs -l en --no-location` in a throwaway container copy of `/app/src`, set-diffed against the checked-in catalogues (`new=0` for all three) | PASS |
| R-11 | `test_no_empty_msgstr` detects an empty plural form | In-memory `.po` sample with `msgstr[0] ""` run through `testing.i18n_helpers._parse_po_entries` | **FAIL** → I18N-005 |
| R-12 | CLDR plural selection at runtime (ru/bs 3-form) | Probe rendering the exact `ads/dashboard.html:95` blocktrans for n=0,1,2,4,5,11,21,22,25 | PASS |
| R-13 | `dir="ltr"` discipline on every page template | `grep 'html lang='` → all 15 page templates carry `dir="{{ LANGUAGE_BIDI\|yesno:"rtl,ltr" }}"`; `get_language_bidi()` False for ru/bs/en | PASS |
| R-14 | hreflang emitted by every page template | `grep locale_head` → all 15 include `components/locale_head.html` | PASS (gate itself does not assert this → I18N-008) |
| R-15 | Price formatting is locale-aware | Probe of `format_price_value` under `translation.override` | **FAIL** for fractional amounts → I18N-003 |
| R-16 | Timestamps are rendered in the site's timezone | Probe of `settings.TIME_ZONE` | **FAIL** (`America/Chicago`) → I18N-004 |
| R-17 | `load_exchange_rates` writes localized currency names (boundary check) | Read `apps/currencies/models.py` — `ExchangeRate` has no `name_i18n`; currency display is ISO-4217 code only | PASS (clean boundary; the phase-09 API-008 finding is not i18n-adjacent) |

> PASS results prove the audit was thorough; they are METHODOLOGY evidence, NOT findings.

**Tools used:** `grep`/`glob`/`read` over the working tree; `docker run` on
`mko-bazuna-dev-web:latest` (xgettext 0.23.1) for the extraction diff;
`docker compose --project-name mko-bazuna-test …` for the gate run and for four read-only
Python probes; `.venv/Scripts/python.exe` for the local format/parser probes.

**Assumptions:** `config.settings.test` is the settings module under test
(`LANGUAGE_CODE = "en"`, `TIME_ZONE` unset); production uses `config.settings.prod`, which
does not override `TIME_ZONE` either. `.mo` files present in the working tree are compiled
artifacts and their presence is not treated as a defect. `gitleaks`/`pre-commit` are not
installed on this host, so no secret-scanning verification was performed. The
`mko_bazuna` database was not written to at any point — all runtime probes used
`RequestFactory`, `response.cookies`, and unsaved model instances, with no DB access.

<!-- Phase 99 ADDS a Methodology Cross-Check here. -->

## Findings Summary

| ID | Title | Severity | Status | Category |
|----|-------|----------|--------|----------|
| I18N-001 | `lang_pref` cookie locale is neither normalized nor validated → whole catalogue silently degrades to Russian | HIGH | Open | Correctness / i18n runtime |
| I18N-002 | Unvalidated cookie locale becomes the submenu cache-key segment → unbounded cache-key cardinality | MEDIUM | Open | Operability / i18n runtime |
| I18N-003 | Prices render with the en-US decimal separator in `ru` and `bs` | HIGH | Open | Correctness / format localization |
| I18N-004 | `TIME_ZONE` is never set (`America/Chicago`) and date patterns are hardcoded to en-US | HIGH | Open | Correctness / format localization |
| I18N-005 | `test_no_empty_msgstr` only inspects the last plural form | MEDIUM | Open | Test-gate completeness |
| I18N-006 | Bot i18n gate scans only `handlers/` (+`services/`) — `lifecycle.py`, `main.py`, `middlewares/`, `schemas/` are unscanned | MEDIUM | Open | Test-gate completeness |
| I18N-007 | Template i18n gate scans only `TEMPLATES["DIRS"]`, ignoring `APP_DIRS` | MEDIUM | Open | Test-gate completeness |
| I18N-008 | `test_hreflang_present` never asserts that page templates include the partial | MEDIUM | Open | Test-gate completeness |
| I18N-009 | Language switcher gates its cookie write on consent while the server writes it unconditionally | MEDIUM | Open | Consistency |
| I18N-010 | Active-price filter chip interpolates raw, unformatted `Decimal` values | MEDIUM | Open | Correctness / format localization |
| I18N-011 | `lang_pref` cookie is emitted without `Secure`/`HttpOnly`/`SameSite` | LOW | Open | Hardening |
| I18N-012 | `Vary: Accept-Language` only — the documented proxy/page-cache contract does not hold for cookie-driven locale | LOW | Open | Operability |
| I18N-013 | Django `verbose_name`/`help_text` are untranslated English; admin renders English in every locale | LOW | Open | Localization coverage |
| I18N-014 | Four orphaned msgids left in all three catalogues; no gate detects stale entries | LOW | Open | Catalog hygiene |
| I18N-015 | `Accept-Language` q-values are ignored, so a supported lower-ranked tag is skipped | LOW | Open | Correctness / i18n runtime |

## Distribution

**Severity counts**

| HIGH | MEDIUM | LOW | CRITICAL |
|------|--------|-----|----------|
| 3 | 7 | 5 | 0 |

**Status counts**

| Status | Count |
|--------|-------|
| Open | 15 |

> Note: Status is `Open` for all findings in raw phase reports. Phase 99 validation mutates Status.

## Findings by Severity

### HIGH

#### I18N-001: [HIGH] — `lang_pref` cookie locale is neither normalized nor validated → whole catalogue silently degrades to Russian

| Field | Value |
|---|---|
| **ID** | I18N-001 |
| **Title** | `lang_pref` cookie locale is neither normalized nor validated → whole catalogue silently degrades to Russian |
| **Severity** | HIGH (rubric: "Locale priority chain broken (… no normalization)") |
| **Category** | Correctness — runtime locale resolution |
| **File(s)** | `src/backend/apps/core/middleware/language.py:66-69`, `src/backend/apps/core/middleware/language.py:111-130`, `src/backend/apps/categories/models.py:54-63`, `src/backend/apps/locations/models.py:46-55` |
| **Status** | Open |
| **Problem** | `LanguagePreMiddleware.process_request` validates and normalizes only the `?lang=` query parameter (via `LanguageLocale.from_code`, then a `base in LanguageLocale.values()` re-check before persisting). The cookie branch calls `self._set_language_code(request, lang)` on the raw cookie string, which forwards it straight into `translation.activate()` and onto `request.LANGUAGE_CODE`. Templates then pass `request.LANGUAGE_CODE` verbatim to `|get_category_name`, `|get_city_name`, `|get_lookup_name`, `|get_title` and `|get_description`, whose fallback chain is `locale → ru → name`. Because the lookup is an exact dict key test, any non-canonical locale string misses and silently falls through to the **Russian** `name_i18n` entry. |
| **Impact** | A single cookie value turns an English/Bosnian page into one whose chrome is in the selected language but whose entire catalogue — category names, city names, feature tags, ad titles and ad descriptions — is Russian. Sellers and buyers read the wrong content and cannot tell why. The same unchecked string is echoed into `<html lang=…>`, the `Content-Language` header, and (see I18N-002) the submenu cache key. The value is trivially attacker/user-controllable: any client can set `lang_pref` for the parent domain. |
| **Root Cause** | The normalization/validation logic lives in `_apply_lang_param` only; the cookie branch (`process_request` lines 66-69) was never given the same treatment even though the docstring at lines 5-6 and `docs/01-spec/i18n-spec.md:63` claim the resolved code "is normalized by `LanguageLocale.from_code()`". |
| **Recommendation** | Route all three sources through one resolver: `self._set_language_code(request, LanguageLocale.from_code(raw, fallback=LanguageLocale.BOSNIAN).value)`. Additionally, when the incoming locale is not one of the three configured codes, do not pass the raw string to `translation.activate()` at all — activate the fallback so the gettext catalogue resolves correctly. Apply the same guard to `_parse_accept_language`'s return value. Consider normalising inside the model accessors too (`_resolve(locale) -> Locale`), so a bad locale degrades to `ru` deliberately rather than accidentally. |
| **Effort** | S |
| **Priority** | P0 |
| **Reproduction Steps** | 1. `GET /` with `Cookie: lang_pref=en-US`, no `?lang=`. 2. Observe `<html lang="en-us">` and `Content-Language: en-us`. 3. Compare rendered category/city/ad titles: they are the Russian `name_i18n` values. Same for `lang_pref=EN`, `lang_pref=en_US`, `lang_pref=xx`. |
| **Related Findings** | I18N-002, I18N-011 |

**Evidence — `src/backend/apps/core/middleware/language.py:61-76`** *(supports: "the cookie branch is the only priority source that is passed through unvalidated")*:
```python
lang = request.GET.get("lang")
if lang is not None:
    self._apply_lang_param(request, lang)   # normalizes + validates
    return

lang = request.COOKIES.get(LANGUAGE_COOKIE_NAME)
if lang is not None:
    self._set_language_code(request, lang)  # RAW STRING, no from_code()
    return

lang = self._parse_accept_language(request) # normalizes
```

**Evidence — runtime probe of `LanguagePreMiddleware`** *(supports: "`?lang=en-US` normalizes; the cookie does not")*:
```text
param=bs, cookie=ru, accept=ru   -> {'request.LANGUAGE_CODE': 'bs', ...}
param=en-US, cookie=ru           -> {'request.LANGUAGE_CODE': 'en', ...}
cookie=en-US (unnormalised)      -> {'request.LANGUAGE_CODE': 'en-us', 'translation.get_language()': 'en-us'}
cookie=xx (unsupported)          -> {'request.LANGUAGE_CODE': 'xx',    'translation.get_language()': 'xx'}
```

**Evidence — runtime probe of the accessors under non-canonical locales** *(supports: "an `en-us` request renders Russian names and Russian ad text")*:
```text
locale='ru'    cat='Транспорт'  city='Подгорица'  ad_title='Продаю велосипед'
locale='bs'    cat='Transport'  city='Podgorica'  ad_title='Prodajem bicikl'
locale='en'    cat='Transport'  city='Podgorica'  ad_title='Selling a bicycle'
locale='en-us' cat='Транспорт'  city='Подгорица'  ad_title='Продаю велосипед'
locale='EN'    cat='Транспорт'  city='Подгорица'  ad_title='Продаю велосипед'
locale='xx'    cat='Транспорт'  city='Подгорица'  ad_title='Продаю велосипед'
```

**Evidence — `src/backend/apps/categories/models.py:54-63`** *(supports: "the fallback is an exact-key test, so a non-canonical locale always lands on `ru`")*:
```python
def get_name(self, locale: str = LanguageLocale.RUSSIAN) -> str:
    """Get localized name with fallback chain: locale -> ru -> name."""
    name_i18n = getattr(self, "name_i18n", None)
    if name_i18n:
        if locale in name_i18n:
            return name_i18n[locale]
        if "ru" in name_i18n:
            return name_i18n["ru"]
    return str(self.name)
```

**Evidence — `src/backend/apps/core/tests/test_language_middleware.py:284-301`** *(supports: "no test covers a non-canonical cookie value — the test gap that lets this ship")*:
```python
cases = [
    ({"lang": "en"}, None, None, "en"),              # ?lang= wins
    (None, {"lang_pref": "bs"}, None, "bs"),         # cookie  (canonical only)
    (None, None, "en-US,en;q=0.9", "en"),             # Accept-Language
    (None, None, "fr-FR,fr;q=0.9", "bs"),             # unsupported -> bs per spec
    ({}, None, None, "en"),                          # nothing -> default
]
```

---

#### I18N-003: [HIGH] — Prices render with the en-US decimal separator in `ru` and `bs`

| Field | Value |
|---|---|
| **ID** | I18N-003 |
| **Title** | Prices render with the en-US decimal separator in `ru` and `bs` |
| **Severity** | HIGH |
| **Category** | Correctness — format localization (numbers/currency) |
| **File(s)** | `src/backend/apps/ads/templatetags/price_tags.py:43-58`, `src/backend/apps/ads/tests/test_price_format.py:22-32` |
| **Status** | Open |
| **Problem** | `_format_amount` converts the `Decimal` to a **string** (`format(rounded, "f")`) and hands that string to `django.contrib.humanize`'s `intcomma`. `intcomma` only applies locale-aware `number_format` when its argument is a `float`/`Decimal`; for a `str` it does `int(value)`, which raises `ValueError` on any amount with a fractional part, and the `except` branch recurses with `use_l10n=False`, which hard-codes `,` as the grouping separator and leaves the `.` decimal separator untouched. Russian requires `,` as the decimal mark and a non-breaking space as the grouping mark; Bosnian requires `,` and `.`. Both are served en-US formatting. The behaviour is also self-inconsistent: `format_price_value(1250, "BAM")` produces a correctly localized `1 250 BAM` in Russian (no `.` in the string, so `int()` succeeds), while `format_price_value(1234.56, "EUR")` produces `1,234.56` everywhere. |
| **Impact** | On every ad card, ad detail page, search-result chip and Telegram alert, the price of a Bosnian or Russian user is displayed with a `.` decimal separator. In those languages `1.234,56` is the correct rendering; `1,234.56` reads as "one and two hundred thirty-four" to a Russian reader — the exact confusion the locale settings exist to prevent. The mismatch between the grouped-integer chip and the decimal card price on the same screen also makes the filter summary look inconsistent. |
| **Root Cause** | `intcomma` is being used as if it were locale-agnostic string formatting. Its `str` fallback path is documented in Django's source as non-localized, but the call site treats it as localization-aware — the test docstring at `test_price_format.py:24-28` explicitly asserts the opposite ("`intcomma` uses the active locale's grouping separator… a narrow no-break space for the RU locale"), and no test asserts a locale-specific separator, so the belief went unchallenged. |
| **Recommendation** | Pass the `Decimal` to `intcomma` instead of the pre-formatted string (or call `django.utils.formats.number_format(value, use_l10n=True, force_grouping=True)` directly, which is what `intcomma` delegates to). The trailing-zero trim already performed on the string must be preserved — trim the `Decimal`'s exponent first (`value.normalize()` with an `adjusted()` guard) rather than the rendered text. Update `test_format_price_value_uses_intcomma` to assert the exact per-locale output for a fractional amount, e.g. `override("ru") -> "1\xa0234,56 EUR"`, `override("bs") -> "1234,56 EUR"`; per project rule "production code is king", the test follows the corrected behaviour. |
| **Effort** | S |
| **Priority** | P0 |
| **Reproduction Steps** | 1. `translation.override("ru")`, call `format_price_value(Decimal("1234.56"), "EUR")` → `'1,234.56 EUR'`. 2. Call `format_price_value(Decimal("99.9"), "RSD")` → `'99.9 RSD'` (expected `'99,9 RSD'`). 3. Compare with `format_price_value(Decimal("1250"), "BAM")` → `'1 250 BAM'` (correct), showing the inconsistency. |
| **Related Findings** | I18N-010 |

**Evidence — `src/backend/apps/ads/templatetags/price_tags.py:43-58`** *(supports: "a string is passed to `intcomma`, forcing the non-localized fallback")*:
```python
def _format_amount(value: Decimal) -> str:
    """Format a Decimal amount for display (up to 2 decimals, comma thousands)."""
    from django.contrib.humanize.templatetags.humanize import intcomma

    rounded = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP).normalize()
    formatted = format(rounded, "f")
    if "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")
    return intcomma(formatted)          # <-- str, not Decimal
```

**Evidence — `.venv/…/django/contrib/humanize/templatetags/humanize.py:67-80`** *(supports: "`intcomma` only localizes `float`/`Decimal`; a `str` hits the hard-coded `,` path")*:
```python
def intcomma(value, use_l10n=True):
    if use_l10n:
        try:
            if not isinstance(value, (float, Decimal)):
                value = int(value)          # ValueError for "1234.56"
        except (TypeError, ValueError):
            return intcomma(value, False)   # non-localized fallback
        else:
            return number_format(value, use_l10n=True, force_grouping=True)
    result = str(value)                     # "," grouping hard-coded below
```

**Evidence — runtime probe, actual vs. `number_format` expectation** *(supports: "`ru` and `bs` are wrong; `en` is right by coincidence")*:
```text
en actual: '1,234.56 EUR' | expected: '1,234.56 EUR'
ru actual: '1,234.56 EUR' | expected: '1\xa0234,56 EUR'
bs actual: '1,234.56 EUR' | expected: '1234,56 EUR'

en intcomma('1234.56')='1,234.56'  intcomma(Decimal('1234.56'))='1,234.56'
ru intcomma('1234.56')='1,234.56'  intcomma(Decimal('1234.56'))='1\xa0234,56'
bs intcomma('1234.56')='1,234.56'  intcomma(Decimal('1234.56'))='1234,56'
```

**Evidence — `src/backend/apps/ads/tests/test_price_format.py:22-32`** *(supports: "the existing test asserts grouping happened but never asserts the locale separator, so it cannot catch this")*:
```python
def test_format_price_value_uses_intcomma() -> None:
    """Large amounts get a thousands separator (grouping applied).

    ``intcomma`` uses the active locale's grouping separator (e.g. ',' or a
    narrow no-break space for the RU locale), so the test asserts grouping
    happened without depending on the exact separator.
    """
    result = format_price_value(Decimal("12345"), CurrencyCode.EUR)
    assert "12345" not in result
    assert result.startswith("12")
    assert result.endswith("345 EUR")
```

---

#### I18N-004: [HIGH] — `TIME_ZONE` is never set (`America/Chicago`) and date patterns are hardcoded to en-US

| Field | Value |
|---|---|
| **ID** | I18N-004 |
| **Title** | `TIME_ZONE` is never set (`America/Chicago`) and date patterns are hardcoded to en-US |
| **Severity** | HIGH |
| **Category** | Correctness — format localization (dates) |
| **File(s)** | `src/backend/config/settings/base.py:128-136` (no `TIME_ZONE`), `src/backend/templates/ads/detail.html:160`, `src/backend/templates/ads/partials/ad_list.html:144`, `src/backend/templates/cabinet/search_history.html:43`, `src/backend/templates/analytics/seller_dashboard.html:87` |
| **Status** | Open |
| **Problem** | No settings module sets `TIME_ZONE`, so Django's default `America/Chicago` (UTC-5/-6) applies, while `USE_TZ` is `True` (Django 5 default). Every user-visible timestamp — "Published:", the ad-card date, the search-history timestamps, the seller-dashboard metric dates — is computed and rendered in US Central time for a site whose cities are all in Montenegro. Independently, the templates hardcode the en-US date pattern `'M d, Y'` / `'M d'` / `'M d, H:i'` instead of using the locale's `DATE_FORMAT` (`ru: 'j E Y г.'`, `bs: 'j. N Y.'`), so even the ordering is month-first where day-month-year is correct. |
| **Impact** | A European visitor sees publish times shifted by 5-7 hours, and for ads published between 00:00 and 07:00 local the *calendar day itself* is wrong — a day-old ad can read as published today. Combined with the forced month-first pattern, a Russian user sees `Опубликовано: Сен 05, 2026` where `5 сен. 2026 г.` is correct. Search history and analytics dates are equally wrong. This is the timestamp a buyer uses to judge whether a listing is fresh. |
| **Root Cause** | `TIME_ZONE` was never added to `base.py` (the i18n block sets `LANGUAGE_CODE`, `USE_I18N`, `LANGUAGES`, `LOCALE_PATHS` and nothing else), and the templates reach for `{{ x|date:'M d, Y' }}` — a US pattern — instead of `{{ x|date:'DATE_FORMAT' }}` or the locale-aware `{{ x|date }}`. Neither choice is covered by the i18n gate, which only inspects translation wrapping, not format tokens. |
| **Recommendation** | Set `TIME_ZONE = "Europe/Belgrade"` in `config/settings/base.py` next to `LANGUAGE_CODE` (make it env-overridable via `env("TIME_ZONE", default="Europe/Belgrade")` so a future operator can change it without a code change). Replace the four hardcoded patterns with the locale format names: `'SHORT_DATE_FORMAT'` for the ad card, `'DATE_FORMAT'` for the detail/seller-dashboard rows, and `'DATETIME_FORMAT'` for search history. Add a `unit` test asserting `settings.TIME_ZONE` and that a known UTC instant renders to the expected Europe/Belgrade local time. |
| **Effort** | S |
| **Priority** | P1 |
| **Reproduction Steps** | 1. In the test container, `settings.TIME_ZONE` → `'America/Chicago'`, `USE_TZ` → `True`. 2. `timezone.localtime(datetime(2026,9,5,23,30, tzinfo=utc))` → `2026-09-05T18:30:00-05:00` (i.e. 06:30 on 6 Sep in Belgrade). 3. Render `{{ d|date:'M d, Y' }}` under `override("ru")` → `'Сен 05, 2026'`; under `override("bs")` → `'Sep. 05, 2026'`. |
| **Related Findings** | I18N-003, I18N-010 |

**Evidence — `src/backend/config/settings/base.py:128-136`** *(supports: "the i18n block sets the language but never the timezone")*:
```python
# Internationalization
LANGUAGE_CODE = "ru"
USE_I18N = True
LANGUAGES = [
    ("ru", "Russian"),
    ("bs", "Bosnian"),
    ("en", "English"),
]
LOCALE_PATHS = [BASE_DIR / "backend" / "locale"]
# no TIME_ZONE  -> Django default "America/Chicago"
```

**Evidence — runtime probe** *(supports: "`TIME_ZONE` is `America/Chicago` and the default date formats differ per locale from what the templates force")*:
```text
TIME_ZONE     = 'America/Chicago'
USE_TZ        = True
timezone.localtime(datetime(2026,9,5,23,30,utc)) = 2026-09-05T18:30:00-05:00
en card=[Sep 05] detail=[Sep 05, 2026] hist=[Sep 05, 09:30]   DATE_FORMAT='N j, Y'
ru card=[Сен 05] detail=[Сен 05, 2026] hist=[Сен 05, 09:30]   DATE_FORMAT='j E Y г.'
bs card=[Sep. 05] detail=[Sep. 05, 2026] hist=[Sep. 05, 09:30] DATE_FORMAT='j. N Y.'
```

**Evidence — hardcoded en-US patterns** *(supports: "all four date renderings bypass the locale format")*:
```text
src/backend/templates/ads/detail.html:160   {% trans "Published:" %} {{ ad.published_at|date:'M d, Y' }}
src/backend/templates/ads/partials/ad_list.html:144  {{ ad.published_at|date:'M d' }}
src/backend/templates/cabinet/search_history.html:43 {{ entry.created_at|date:"M d, H:i" }}
src/backend/templates/analytics/seller_dashboard.html:87 {{ metric.date|date:"M d, Y" }}
```

---

### MEDIUM

#### I18N-002: [MEDIUM] — Unvalidated cookie locale becomes the submenu cache-key segment → unbounded cache-key cardinality

| Field | Value |
|---|---|
| **ID** | I18N-002 |
| **Title** | Unvalidated cookie locale becomes the submenu cache-key segment → unbounded cache-key cardinality |
| **Severity** | MEDIUM |
| **Category** | Operability — cache keying (i18n runtime) |
| **File(s)** | `src/backend/apps/categories/views.py:51`, `src/backend/apps/core/middleware/language.py:66-69` |
| **Status** | Open |
| **Problem** | The submenu fragment cache key is `category:submenu:<tree_version>:<slug>:<request.LANGUAGE_CODE or 'ru'>`. The `<locale>` segment is doing its documented job — it does prevent a Russian fragment being served to a Bosnian visitor — but because `request.LANGUAGE_CODE` is the unvalidated cookie string from I18N-001, the segment is attacker-controlled. Every distinct cookie value produces a distinct cache entry per category slug, each held for `SUBMENU_CACHE_TTL` (300 s) plus a 60 s stale-serve window and a 30 s single-flight lock. |
| **Impact** | A client walking the `lang_pref` cookie through N distinct values forces N×|categories| fragment renders and cache entries. The fragments are cheap HTML but each miss re-renders the submenu template and does DB work; the cached entries consume Redis for up to ~6 minutes each. The practical ceiling is Redis memory, not correctness, but it turns a free-to-set cookie into a cache-fill lever with no rate limit on the endpoint. |
| **Root Cause** | Keying on a raw request attribute rather than on a value that has passed through the `LanguageLocale` enum. The key would be safe by construction if it were built from `LanguageLocale.from_code(request.LANGUAGE_CODE).value` (or from `translation.get_language()` after the middleware has normalized it). |
| **Recommendation** | Fixing I18N-001 closes this automatically, because `request.LANGUAGE_CODE` will then always be one of three values. As defence in depth, normalise again at the key-building site: `locale = LanguageLocale.from_code(request.LANGUAGE_CODE, fallback=LanguageLocale.RUSSIAN).value`. Cross-referenced against Phase 12/13 (operational capacity) — this finding is filed here because the untrusted value originates in the locale middleware. |
| **Effort** | S |
| **Priority** | P1 |
| **Related Findings** | I18N-001 |

**Evidence — `src/backend/apps/categories/views.py:51`** *(supports: "the cache key embeds the unvalidated request attribute")*:
```python
cache_key = f"category:submenu:{get_tree_version()}:{category.slug}:{request.LANGUAGE_CODE or 'ru'}"
```

**Evidence — runtime probe** *(supports: "the `<locale>` segment takes whatever the cookie held")*:
```text
cookie=en-US (unnormalised)  -> {'request.LANGUAGE_CODE': 'en-us', ...}
cookie=xx (unsupported)      -> {'request.LANGUAGE_CODE': 'xx',    ...}
```

---

#### I18N-005: [MEDIUM] — `test_no_empty_msgstr` only inspects the last plural form

| Field | Value |
|---|---|
| **ID** | I18N-005 |
| **Title** | `test_no_empty_msgstr` only inspects the last plural form |
| **Severity** | MEDIUM |
| **Category** | Test-gate completeness |
| **File(s)** | `src/backend/testing/i18n_helpers.py:45-52`, `src/backend/apps/ads/tests/test_i18n_completeness.py:428-437`, `src/backend/apps/ads/tests/test_i18n_pipeline.py:48-61` |
| **Status** | Open |
| **Problem** | `_parse_po_entries` resets `cur_msgstr` on every line that starts with `msgstr`, including `msgstr[N]`. A plural entry therefore keeps only the **last** form (`msgstr[2]` for `ru`/`bs`); `msgstr[0]` and `msgstr[1]` are discarded before any caller sees them. Both copies of `test_no_empty_msgstr` then ask the parser "is any msgstr blank?", which for a plural entry is only ever a question about `msgstr[2]`. |
| **Impact** | The DoD contract "msgstr must be non-empty for `ru` and `bs`" is unenforced for plural entries. A translator (or a bulk edit) can blank the Russian singular form and the gate stays green; at runtime the dashboard then renders `1 просмотров` instead of `1 просмотр` and `2 контактов` instead of `2 контакта` — grammar errors on a seller-facing analytics page that CI is supposed to prevent. The current catalogues happen to be correct, so this is a latent hole rather than a live defect. |
| **Root Cause** | The shared parser was written to return a single `(msgid, msgstr)` pair per entry, so it has no representation for multiple plural forms. The docstring acknowledges the flattening ("sharing the first `msgstr` value encountered") but the implementation actually keeps the last, and neither caller of the two copies noticed. |
| **Recommendation** | Change `_parse_po_entries` to return `list[tuple[str, list[str]]]` (msgid → all msgstr forms) and update the three call sites to flatten with "any form blank is a violation": `empty = [m for m, forms in entries if m and any(not f.strip() for f in forms)]`. The plural-form header count is already validated by `test_plural_forms`, so the parser can additionally assert the number of forms matches `nplurals` for that locale. Add a regression test that feeds `_parse_po_entries` a plural entry with a blank `msgstr[0]` and asserts the blank is reported. |
| **Effort** | S |
| **Priority** | P1 |
| **Reproduction Steps** | 1. Feed `_parse_po_entries` a `.po` snippet whose `msgstr[0]` is `""` and whose `msgstr[1]`/`[2]` are filled (probe in Appendix A). 2. Observe that the parsed `msgstr` is `msgstr[2]`. 3. Observe that the gate's "empty msgids" list is empty. |
| **Related Findings** | I18N-006, I18N-007, I18N-008 |

**Evidence — `src/backend/testing/i18n_helpers.py:45-52`** *(supports: "`cur_msgstr` is reset on every `msgstr[N]` line, so only the last plural form survives")*:
```python
elif stripped.startswith("msgstr"):
    in_msgstr = True
    rest = stripped[len("msgstr") :]
    if rest.startswith("["):
        rest = rest[rest.index("]") + 1 :]   # index discarded
    cur_msgstr = [_unescape(rest)]           # <-- previous forms dropped
```

**Evidence — `src/backend/apps/ads/tests/test_i18n_completeness.py:428-437`** *(supports: "the gate asks only whether the (last) msgstr is blank")*:
```python
def test_no_empty_msgstr() -> None:
    """``ru`` and ``bs`` have no empty ``msgstr``; ``en`` is exempt."""
    for po_path in _po_files():
        locale_code = po_path.parent.parent.name
        if locale_code == "en":
            continue
        text = po_path.read_text(encoding="utf-8")
        entries = _parse_po_entries(text)
        empty = [msgid for msgid, msgstr in entries if msgid and not msgstr.strip()]
        assert not empty, f"{po_path}: empty msgstr for msgids: {empty}"
```

**Evidence — in-memory probe of the parser (see Appendix A)** *(supports: "a blank `msgstr[0]` is invisible to the gate")*:
```text
parsed entries:
  msgid='%(counter)s view' msgstr='%(counter)s просмотров'
  msgid='%(counter)s views' msgstr='%(counter)s просмотров'
msgids reported EMPTY by the gate's parser: []
EXPECTED (msgstr[0] is blank): ['%(counter)s view']
GATE BLIND SPOT CONFIRMED: True
```

---

#### I18N-006: [MEDIUM] — Bot i18n gate scans only `handlers/` (+`services/`); `lifecycle.py`, `main.py`, `middlewares/`, `schemas/` are unscanned

| Field | Value |
|---|---|
| **ID** | I18N-006 |
| **Title** | Bot i18n gate scans only `handlers/` (+`services/`); `lifecycle.py`, `main.py`, `middlewares/`, `schemas/` are unscanned |
| **Severity** | MEDIUM |
| **Category** | Test-gate completeness |
| **File(s)** | `src/backend/apps/ads/tests/test_i18n_completeness.py:796-799`, `src/backend/apps/ads/tests/test_i18n_completeness.py:959-966`, `src/telegram_bot/lifecycle.py:36-55` |
| **Status** | Open |
| **Problem** | `test_bot_no_hardcoded_messages` collects files from `telegram_bot/handlers/` only, and `test_bot_no_raw_model_field_access` from `handlers/` + `services/`. The remaining bot modules that can carry user-visible text — `telegram_bot/lifecycle.py`, `telegram_bot/main.py`, `telegram_bot/middlewares/*.py`, `telegram_bot/schemas/*.py` — are outside both scans. `lifecycle.py` proves the gap is reachable: it declares the Telegram `/` command menu with four user-visible `BotCommand(description=...)` literals per language, and the `makemessages` diff shows that `"Start"`, `"Language"`, `"Post ad"` and `"Alerts"` were previously `gettext` msgids that stopped being extracted. |
| **Impact** | The gate cannot distinguish "intentionally localized literal" from "regression where a `_()` wrapper was dropped" outside `handlers/`. Today `lifecycle.py` is fine — the literals are deliberate (documented at `lifecycle.py:31-35`) and are registered per `language_code` via `set_my_commands(commands, language=lang)`. The risk is the next change: unwrapping or adding a message in `middlewares/` or `main.py` passes CI silently. Phase 10 owns source-level i18n hygiene; this finding is about the *gate's* blind spot, which is owned here. |
| **Root Cause** | The collector hard-codes two subdirectories instead of walking `telegram_bot/` and excluding only `tests/`. The `main.py` and `lifecycle.py` modules were added after the gate was written. |
| **Recommendation** | Change `_collect_bot_handler_files` to `rglob("*.py")` over `settings.BASE_DIR / "telegram_bot"` with an exclusion for `tests/`, and add `BotCommand` to `_BOT_USER_FACING_METHODS`' keyword-argument set (`description=`) so the command menu is covered by the same rule. Record the four now-dead msgids (`Start`, `Language`, `Post ad`, `Alerts` — see I18N-014) as an expected exemption in the gate, with a comment pointing at `lifecycle.py:31-35`, so the exemption is documented rather than silent. |
| **Effort** | S |
| **Priority** | P1 |
| **Related Findings** | I18N-005, I18N-007, I18N-008, I18N-014 |

**Evidence — `src/backend/apps/ads/tests/test_i18n_completeness.py:796-799`** *(supports: "the hardcoded-message scan is limited to `handlers/`")*:
```python
def _collect_bot_handler_files() -> list[Path]:
    """Return every ``*.py`` file under ``src/telegram_bot/handlers/``."""
    handlers_dir = settings.BASE_DIR / "telegram_bot" / "handlers"
    return sorted(handlers_dir.rglob("*.py"))
```

**Evidence — `src/backend/apps/ads/tests/test_i18n_completeness.py:959-966`** *(supports: "the raw-field scan adds `services/` but still not the module root or `middlewares/`")*:
```python
def _collect_bot_source_files() -> list[Path]:
    """Return every ``*.py`` file under ``handlers/`` and ``services/``."""
    base = settings.BASE_DIR / "telegram_bot"
    files: list[Path] = []
    for sub in ("handlers", "services"):
        files.extend(sorted((base / sub).rglob("*.py")))
    return files
```

**Evidence — `src/telegram_bot/lifecycle.py:31-55`** *(supports: "user-visible `BotCommand` descriptions live outside the scanned subtree")*:
```python
# Localized Telegram command menu (EC-3). The ru/bs entries carry their final
# localized descriptions directly as literals. The en entries are English
# literals too (NOT gettext msgids): using eager ``_()`` here would freeze
# them to the import-time locale ...
_COMMANDS: dict[str, list[BotCommand]] = {
    "ru": [BotCommand(command="start", description="Начать"), ...],
    "bs": [BotCommand(command="start", description="Početak"), ...],
    "en": [BotCommand(command="start", description="Start"),
           BotCommand(command="language", description="Language"),
           BotCommand(command="post", description="Post ad"),
           BotCommand(command="alerts", description="Alerts")],
}
```

---

#### I18N-007: [MEDIUM] — Template i18n gate scans only `TEMPLATES["DIRS"]`, ignoring `APP_DIRS`

| Field | Value |
|---|---|
| **ID** | I18N-007 |
| **Title** | Template i18n gate scans only `TEMPLATES["DIRS"]`, ignoring `APP_DIRS` |
| **Severity** | MEDIUM |
| **Category** | Test-gate completeness |
| **File(s)** | `src/backend/apps/ads/tests/test_i18n_completeness.py:80-100`, `src/backend/config/settings/base.py:215-236` |
| **Status** | Open |
| **Problem** | `_collect_template_files()` iterates `settings.TEMPLATES[*]["DIRS"]` only. The project configures `APP_DIRS: True`, so Django's loader also resolves `<app>/templates/**` for every entry in `INSTALLED_APPS`, but none of those files are reachable by `test_no_hardcoded_visible_text`, `test_no_raw_get_name_in_templates`, `test_template_extraction_coverage`, `test_no_hardcoded_js_strings` or `test_title_tags_translated`. Today this is latent — all 43 templates live under `src/backend/templates/` and `src/templates/` is empty — but the gate's own docstring ("public/seller-facing templates") overstates its coverage. |
| **Impact** | The natural refactor for a modular Django app — moving a template next to its app under `src/backend/apps/<app>/templates/` — silently removes it from the i18n gate, and an untranslated string in it ships. Nothing in the test suite or CI detects the loss of coverage. |
| **Root Cause** | The collector was written when only project-level `DIRS` templates existed; `APP_DIRS` was never incorporated. |
| **Recommendation** | Derive the file set from the configured template engine instead: iterate `django.template.engines["django"].engine.get_default()`'s `template_loaders` (or, more simply, add `[Path(app.path) / "templates" for app in apps.get_app_configs() if (Path(app.path) / "templates").is_dir()]` to the roots). Keep the existing `exclude_subpaths` applied to the path relative to each root. Add a guard assertion that at least one app-level `templates/` directory is discovered, or an explicit `pytest.skip`-free note, so the day an app gains one the gate covers it. |
| **Effort** | S |
| **Priority** | P2 |
| **Related Findings** | I18N-005, I18N-006, I18N-008 |

**Evidence — `src/backend/apps/ads/tests/test_i18n_completeness.py:91-100`** *(supports: "only `DIRS` is walked; `APP_DIRS` is never consulted")*:
```python
exclude_subpaths = (
    "admin/",
    "analytics/moderation_dashboard.html",
    "components/feature_tag.html",
)
files: list[Path] = []
for tmpl_cfg in settings.TEMPLATES:
    for d in tmpl_cfg.get("DIRS", []):        # <-- APP_DIRS ignored
        d = Path(d)
        for f in d.rglob("*.html"):
            rel = f.relative_to(d).as_posix()
            if any(rel.startswith(ex) for ex in exclude_subpaths):
                continue
            files.append(f)
return files
```

**Evidence — template inventory (read-only)** *(supports: "no app-level `templates/` directory exists today, so the gap is latent")*:
```text
Get-ChildItem -Path src -Recurse -Directory -Filter templates
  C:\py_dev\mko_bazuna\src\templates          (empty)
  C:\py_dev\mko_bazuna\src\backend\templates  (43 .html files, all under DIRS[0])
```

---

#### I18N-008: [MEDIUM] — `test_hreflang_present` never asserts that page templates include the partial

| Field | Value |
|---|---|
| **ID** | I18N-008 |
| **Title** | `test_hreflang_present` never asserts that page templates include the partial |
| **Severity** | MEDIUM |
| **Category** | Test-gate completeness |
| **File(s)** | `src/backend/apps/ads/tests/test_i18n_completeness.py:568-591` |
| **Status** | Open |
| **Problem** | The test renders `components/locale_head.html` in isolation with a bare `RequestFactory` request and asserts the rendered fragment contains one `hreflang` per configured language (and no `x-default`). It never checks that any page template `{% include %}`s that fragment. The docstring states "every page template renders `<link rel="alternate" hreflang>` … included by every page template", but the assertion covers only the partial. |
| **Impact** | SEO alternates are a per-page concern; a new page template (or a refactor that moves the include into a base template some pages do not extend) ships with no `hreflang` and no failing test. The gate reads as if the property is enforced when it is not. Today all 15 page templates do include it, so this is a coverage gap rather than a live defect. |
| **Root Cause** | The test was scoped to prove the partial is correct (Option B in the original design note) and its name/docstring were then read as proving the site-wide property. |
| **Recommendation** | Add a source-level assertion to the same test: for every `settings.TEMPLATES[*]["DIRS"]` template whose basename is not a partial (i.e. not under `components/`, `partials/`, `badges/`), assert its source contains `{% include "components/locale_head.html" %}`. This keeps the test at `unit` speed and needs no rendering. If a base-template refactor happens later, the assertion should follow the include to whatever partial holds it. |
| **Effort** | S |
| **Priority** | P2 |
| **Related Findings** | I18N-005, I18N-006, I18N-007 |

**Evidence — `src/backend/apps/ads/tests/test_i18n_completeness.py:568-591`** *(supports: "only the partial is rendered; no page template is inspected")*:
```python
def test_hreflang_present() -> None:
    """Every page template renders a ``<link rel="alternate" hreflang>`` link
    for every configured language (I18N-004). ..."""
    request = RequestFactory().get("/")
    rendered = get_template("components/locale_head.html").render({"request": request})
    expected_langs = {code for code, _ in settings.LANGUAGES}
    found_langs = {lang for lang in expected_langs if f'hreflang="{lang}"' in rendered}
    missing = expected_langs - found_langs
    assert not missing, f"Missing hreflang tags for languages: {sorted(missing)}"
    assert 'hreflang="x-default"' not in rendered
```

**Evidence — `grep -rn locale_head src/backend/templates`** *(supports: "all 15 page templates do include it today")*:
```text
users/login_issue.html:11  privacy.html:11  ads/detail.html:15  ads/dashboard.html:13
ads/edit.html:10  ads/list.html:11  cabinet/hub.html:10  cabinet/favorites.html:12
cabinet/settings.html:11  cabinet/search_history.html:11  cabinet/saved_searches.html:11
cabinet/saved_search_edit.html:12  analytics/seller_dashboard.html:15
analytics/moderation_dashboard.html:13  admin/moderation/review.html:12
(16 matches, 15 page templates + the partial's own header comment)
```

---

#### I18N-009: [MEDIUM] — Language switcher gates its cookie write on consent while the server writes it unconditionally

| Field | Value |
|---|---|
| **ID** | I18N-009 |
| **Title** | Language switcher gates its cookie write on consent while the server writes it unconditionally |
| **Severity** | MEDIUM |
| **Category** | Consistency / coupling |
| **File(s)** | `src/backend/templates/components/language_switcher.html:99-110`, `src/backend/apps/core/middleware/language.py:87-93` |
| **Status** | Open |
| **Problem** | The switcher's inline JavaScript writes the `lang_pref` cookie only inside a `{% if consent_preferences %}` guard. The middleware, however, writes the same cookie unconditionally in `process_response` whenever a `?lang=` parameter was supplied, regardless of consent state. The client-side branch is therefore dead in practice: the navigation to `?lang=bs` always triggers the server-side `set_cookie`. |
| **Impact** | Two problems in one place. Operationally, locale persistence *appears* to depend on the cookie-consent decision — a future change to the middleware (or a cached page rendered before consent) would silently break the language switcher for non-consenting visitors, with no test to catch it. For the privacy side, the intent is inverted: the gate implies `lang_pref` is a consent-gated cookie, while the server sets it for everyone — a contradiction that Phase 06 (PII/consent) should reconcile, and that this phase flags because the switcher is i18n behaviour. |
| **Root Cause** | The preference is persisted in two independent places (client JS and server middleware) with different gating conditions and no shared comment explaining that one is a progressive enhancement over the other. |
| **Recommendation** | Decide the contract once and write it down. If the server-side write is authoritative (recommended — it is the only one that runs on a plain `?lang=` link), delete the `{% if consent_preferences %}` wrapper and the `setCookie` JS helper from the switcher, and add a comment stating that the server sets `lang_pref` in `LanguagePreMiddleware.process_response`. If the consent gate is meant to be real, move the gate into `process_response` as well and coordinate the change with Phase 06. Either way, `docs/01-spec/technical-specification.md` §F/§K should name `lang_pref` explicitly as necessary-or-not. |
| **Effort** | S |
| **Priority** | P2 |
| **Related Findings** | I18N-011, I18N-012 |

**Evidence — `src/backend/templates/components/language_switcher.html:99-110`** *(supports: "the client-side cookie write is consent-gated")*:
```html
links.forEach(function(link) {
    link.addEventListener('click', function(e) {
        var lang = link.getAttribute('data-lang');
        {% if consent_preferences %}
        if (lang) {
            setCookie(COOKIE_NAME, lang, COOKIE_MAX_AGE, COOKIE_PATH);
        }
        {% endif %}
        // Allow default browser navigation (href carries ?lang=X)
        closeDropdown();
    });
});
```

**Evidence — `src/backend/apps/core/middleware/language.py:87-93`** *(supports: "the server sets the same cookie with no consent check")*:
```python
cookie_value = getattr(request, "_lang_cookie_value", None)
if cookie_value is not None:
    response.set_cookie(
        LANGUAGE_COOKIE_NAME,
        cookie_value,
        max_age=LANGUAGE_COOKIE_MAX_AGE,
    )
```

**Evidence — runtime probe** *(supports: "the server-side cookie is emitted for `?lang=bs` regardless of any consent context")*:
```text
?lang=bs   cookies={'lang_pref': 'bs'} raw=[' lang_pref=bs; expires=Tue, 28 Sep 2027 09:48:38 GMT; Max-Age=31536000; Path=/']
```

---

#### I18N-010: [MEDIUM] — Active-price filter chip interpolates raw, unformatted `Decimal` values

| Field | Value |
|---|---|
| **ID** | I18N-010 |
| **Title** | Active-price filter chip interpolates raw, unformatted `Decimal` values |
| **Severity** | MEDIUM |
| **Category** | Correctness — format localization |
| **File(s)** | `src/backend/templates/ads/partials/ad_list.html:44-53`, `src/backend/apps/ads/services/listings_query.py:208-220` |
| **Status** | Open |
| **Problem** | The active price-range chip renders `{% blocktrans with min=active_price_min max=active_price_max %}Price: {{ min }}–{{ max }}{% endblocktrans %}`. `active_price_min`/`active_price_max` are plain `Decimal` values from `ListingsQuery.active_price_range`; Django stringifies a `Decimal` in `{{ … }}` without applying `number_format`, so the chip shows `1000.50` with an ASCII decimal point and no thousands grouping, and no currency code — while the ad cards in the very same response render through `|format_price` with grouping and an ISO code. |
| **Impact** | On a Russian or Bosnian listing page the filter summary shows a differently-formatted price from the cards it filters, in the wrong notation for the locale. Users comparing the chip to a card price have to re-read the number. The template gate does not catch it: the text *is* wrapped, only the interpolation is unformatted. |
| **Root Cause** | The view exposes `Decimal`s for the chip instead of pre-formatted strings, and the template uses `blocktrans` interpolation (which cannot apply a filter chain to the placeholder) rather than composing a localized value with the label as a separate `{% trans %}`. |
| **Recommendation** | Format in the view — expose `active_price_min`/`active_price_max` as strings produced by the same helper the cards use (`format_price_value`, or a narrower `format_amount` that omits the currency) — and keep the chip label as a plain `{% trans "Price:" %}`. Alternatively keep the `Decimal` and use `{% blocktrans %}` for the label only, appending the pre-formatted values. Either way, add a `unit` test that renders the chip under `override("ru")` and asserts the decimal separator. |
| **Effort** | S |
| **Priority** | P1 |
| **Related Findings** | I18N-003 |

**Evidence — `src/backend/templates/ads/partials/ad_list.html:44-53`** *(supports: "raw Decimals are interpolated next to localized card prices")*:
```html
{% if active_price_min or active_price_max %}
    <span class="inline-flex items-center px-3 py-1 bg-orange-100 text-orange-800 rounded-full text-sm">
        {% blocktrans with min=active_price_min max=active_price_max %}Price: {{ min }}–{{ max }}{% endblocktrans %}
```
```html
<!-- same response, cards: -->
<p class="text-blue-600 font-bold text-xl mb-2">{{ ad|format_price }}</p>
```

**Evidence — `src/backend/apps/ads/services/listings_query.py:208-220`** *(supports: "the view passes `Decimal`s, not formatted strings")*:
```python
@staticmethod
def active_price_range(params: ListingsQueryParams) -> tuple[Decimal | None, Decimal | None]:
    """Return ``(min, max)`` as ``Decimal`` for template rendering."""
    lo = Decimal(params.min_price) if params.min_price is not None else None
    hi = Decimal(params.max_price) if params.max_price is not None else None
    return (lo, hi)
```

**Evidence — `src/backend/locale/ru/LC_MESSAGES/django.po`** *(supports: "the label is translated but the values are not")*:
```text
msgid  'Price: %(min)s–%(max)s'
msgstr 'Цена: %(min)s–%(max)s'
```

---

### LOW

#### I18N-011: [LOW] — `lang_pref` cookie is emitted without `Secure`/`HttpOnly`/`SameSite`

| Field | Value |
|---|---|
| **ID** | I18N-011 |
| **Title** | `lang_pref` cookie is emitted without `Secure`/`HttpOnly`/`SameSite` |
| **Severity** | LOW |
| **Category** | Hardening |
| **File(s)** | `src/backend/apps/core/middleware/language.py:87-93` |
| **Status** | Open |
| **Problem** | `response.set_cookie(LANGUAGE_COOKIE_NAME, cookie_value, max_age=…)` uses Django's defaults: `secure=False`, `httponly=False`, `samesite=None`. Every other cookie the project issues is hardened — `SESSION_COOKIE_SECURE = True`, `SESSION_COOKIE_SAMESITE = "Lax"`, `CSRF_COOKIE_SECURE = True` (`config/settings/base.py:139-144`) and again in `prod.py:216-217`. The language cookie is the only one that opts out. |
| **Impact** | The cookie carries a three-value language code, so the confidentiality impact is nil. The consistency impact is not: on a deployment where TLS is terminated upstream and a plain-HTTP path is reachable, this cookie is sent in clear while the session cookie is not, and the absence of `SameSite` makes it a candidate for cross-site overwrite — which, per I18N-001, is enough to change a visitor's rendered language. |
| **Root Cause** | The middleware sets only `max_age`; the `secure`/`samesite` policy that `base.py` applies to the session/CSRF cookies is not applied here. |
| **Recommendation** | `response.set_cookie(..., max_age=LANGUAGE_COOKIE_MAX_AGE, secure=settings.SESSION_COOKIE_SECURE, samesite=settings.SESSION_COOKIE_SAMESITE, httponly=True)` — `httponly=True` is free (the cookie is never read by JavaScript once I18N-009 removes the client-side writer). Cross-reference Phase 02, which owns the general cookie-hardening policy. |
| **Effort** | S |
| **Priority** | P2 |
| **Related Findings** | I18N-009, I18N-012 |

**Evidence — runtime probe of the emitted cookie** *(supports: "no Secure, HttpOnly or SameSite attribute")*:
```text
?lang=bs  cookies={'lang_pref': 'bs'}
  raw=[' lang_pref=bs; expires=Tue, 28 Sep 2027 09:48:38 GMT; Max-Age=31536000; Path=/']
```

**Evidence — `src/backend/config/settings/base.py:139-144`** *(supports: "the rest of the cookie policy is hardened; this one is not")*:
```python
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
```

---

#### I18N-012: [LOW] — `Vary: Accept-Language` only; the documented proxy/page-cache contract does not hold for cookie-driven locale

| Field | Value |
|---|---|
| **ID** | I18N-012 |
| **Title** | `Vary: Accept-Language` only; the documented proxy/page-cache contract does not hold for cookie-driven locale |
| **Severity** | LOW |
| **Category** | Operability |
| **File(s)** | `src/backend/apps/core/middleware/language.py:16-19`, `src/backend/apps/core/middleware/language.py:94-95` |
| **Status** | Open |
| **Problem** | `process_response` calls `patch_vary_headers(response, ("Accept-Language",))` and the module docstring states the response contract is kept "forward-compatible with any future reverse proxy / page cache". Two of the three priority sources — the `lang_pref` cookie and the `?lang=` query parameter — are not in `Vary`. A shared cache that honours `Vary` will therefore key only on `Accept-Language` and may serve a Russian body to a visitor whose cookie selects Bosnian. |
| **Impact** | None today: no `proxy_cache`/`fastcgi_cache` is configured in `docker/nginx/nginx.conf` or `nginx.dev.conf`, and no CDN is in front. The risk is latent — the moment a page cache is added (which the docstring anticipates), the stated contract silently does not hold. |
| **Root Cause** | The `Vary` set was chosen when only `Accept-Language` was considered, and was not revisited when the cookie and query-parameter sources were added to the priority chain. |
| **Recommendation** | Add `"Cookie"` to the `patch_vary_headers` tuple so the emitted contract matches the documented one, or — preferred, and cheaper for any future cache — mark language-bearing responses `Cache-Control: private` / `Vary: Cookie` explicitly at the point a shared cache is introduced. Note in the docstring which of the two the project relies on so the next reader does not assume the current `Vary` is sufficient. |
| **Effort** | S |
| **Priority** | P2 |
| **Related Findings** | I18N-011 |

**Evidence — `src/backend/apps/core/middleware/language.py:16-19, 94-95`** *(supports: "the contract claims proxy/page-cache compatibility but only varies on the header")*:
```python
# This middleware also replaces ``LocaleMiddleware``'s response contract:
# ``Vary: Accept-Language`` and ``Content-Language`` headers, keeping the
# behaviour forward-compatible with any future reverse proxy / page cache.
...
patch_vary_headers(response, ("Accept-Language",))
response.headers.setdefault("Content-Language", translation.get_language())
```

**Evidence — runtime probe** *(supports: "`Cookie` is absent from `Vary` on every response")*:
```text
?lang=bs   Vary='Accept-Language' Content-Language='bs'
no param   Vary='Accept-Language' Content-Language='en'
```

---

#### I18N-013: [LOW] — Django `verbose_name`/`help_text` are untranslated English; admin renders English in every locale

| Field | Value |
|---|---|
| **ID** | I18N-013 |
| **Title** | Django `verbose_name`/`help_text` are untranslated English; admin renders English in every locale |
| **Severity** | LOW |
| **Category** | Localization coverage |
| **File(s)** | `src/backend/apps/core/models.py:44-45`, `src/backend/apps/core/models.py:90`, `src/backend/apps/ads/models.py:46-236`, `src/backend/apps/currencies/models.py:29-53`, `src/backend/apps/locations/models.py:20-40` |
| **Status** | Open |
| **Problem** | Every model `verbose_name`/`verbose_name_plural` and `help_text` in the project is a plain English string literal, not `gettext_lazy(...)`. Django's `ModelAdmin` renders `verbose_name` through `capfirst()` without translating it, and `help_text` verbatim. The completeness gate excludes the `admin/` template subtree but nothing in the gate inspects model metadata, and the documented exemption (`docs/01-spec/i18n-spec.md`) covers `feature_tag.html` only. |
| **Impact** | Staff-only: moderators and admins see English column labels and field help regardless of their language, while Django's own admin chrome (`Save`, `Delete`, `Search`) *is* localized by Django's bundled catalogues. The mix is jarring and makes the staff surface inconsistent with the localized public site. No buyer or seller impact. |
| **Root Cause** | Model metadata was written as developer documentation rather than as user-facing copy, and no rule states that admin-only metadata is exempt from the i18n DoD. |
| **Recommendation** | Pick one and document it. If the admin is English-only by design, record `admin/` **and model metadata** in the documented exemption list in `docs/01-spec/i18n-spec.md` so the coverage claim is accurate. If it should follow the locale, wrap `verbose_name`/`help_text` in `gettext_lazy` and run `makemessages --no-obsolete`; the mechanical cost is low and the catalogue grows by roughly 60 entries. Which option is right is a product decision, not an engineering one. |
| **Effort** | M (if translated) / S (if documented as exempt) |
| **Priority** | P2 |
| **Related Findings** | I18N-014 |

**Evidence — `src/backend/apps/core/models.py:44-45, 90`** *(supports: "`verbose_name` is a bare literal, not `gettext_lazy`")*:
```python
class Meta:
    verbose_name = "Site Config"
    verbose_name_plural = "Site Config"
...
    class Meta:
        verbose_name = "Support Contact"
```

**Evidence — `src/backend/apps/ads/models.py:52-79`** *(supports: "`help_text` is English-only developer prose")*:
```python
title = models.CharField(..., help_text="Ad title in Russian (translated from seller input)")
title_en = models.CharField(..., help_text="Ad title in English")
title_bs = models.CharField(..., help_text="Ad title in Bosnian")
description = models.TextField(..., help_text="Ad description in Russian (translated from seller input)")
```

---

#### I18N-014: [LOW] — Four orphaned msgids left in all three catalogues; no gate detects stale entries

| Field | Value |
|---|---|
| **ID** | I18N-014 |
| **Title** | Four orphaned msgids left in all three catalogues; no gate detects stale entries |
| **Severity** | LOW |
| **Category** | Catalog hygiene |
| **File(s)** | `src/backend/locale/{ru,bs,en}/LC_MESSAGES/django.po`, `src/telegram_bot/lifecycle.py:36-55` |
| **Status** | Open |
| **Problem** | The `makemessages -l ru -l bs -l en --no-location` extraction, run against a throwaway container copy of the source tree, removes six msgids that are still present in all three checked-in catalogues: `Start`, `Language`, `Post ad`, `Alerts` (superseded by the per-language `_COMMANDS` literals in `lifecycle.py`), plus `Please login first.` and `Cannot approve: the ad owner has reached the maximum number of active ads.` (message rewording). `makemessages` without `--no-obsolete` marks stale entries `#~` rather than deleting them, and the `.po` files here are not in sync with a fresh extraction. No gate test compares the source inventory against the catalogues in the "removed" direction. |
| **Impact** | Dead entries accumulate silently: translators review and translate strings that will never render, and a reviewer grepping a `.po` for a string can be misled into believing a code path is translated. Runtime impact is nil. |
| **Root Cause** | The extraction command documented in `.kilo/rules/commands.md` omits `--no-obsolete`, so obsolete entries are never pruned, and `test_extraction_completeness` only checks the "added" direction (`all_msgids - msgids` per locale). |
| **Recommendation** | Add `--no-obsolete` to the documented `makemessages` invocation and run it once to clean the catalogues. Add a `unit` test that runs the msgid set through the same extraction helper and asserts the catalogue has no entry that is absent from the source (or, cheaper and equally effective, assert the set difference is empty using a checked-in list of documented exemptions — which is what I18N-006 recommends recording for the four command-menu strings). |
| **Effort** | S |
| **Priority** | P2 |
| **Related Findings** | I18N-005, I18N-006 |

**Evidence — set-diff of msgids before/after a fresh `makemessages`** *(supports: "six msgids exist in the catalogues but no longer in the source")*:
```text
##### ru
before=402 after=396 new=0 removed=6
  - 'Alerts'
  - 'Cannot approve: the ad owner has reached the maximum number of active ads.'
  - 'Language'
  - 'Please login first.'
  - 'Post ad'
  - 'Start'
##### bs   (identical: new=0 removed=6)
##### en   (identical: new=0 removed=6)
```
> `new=0` for all three locales is the positive result of R-10: every `{% trans %}`/`gettext` msgid in the source already exists in every catalogue.

---

#### I18N-015: [LOW] — `Accept-Language` q-values are ignored, so a supported lower-ranked tag is skipped

| Field | Value |
|---|---|
| **ID** | I18N-015 |
| **Title** | `Accept-Language` q-values are ignored, so a supported lower-ranked tag is skipped |
| **Severity** | LOW |
| **Category** | Correctness — runtime locale resolution |
| **File(s)** | `src/backend/apps/core/middleware/language.py:144-160` |
| **Status** | Open |
| **Problem** | `_parse_accept_language` takes `accept_language.split(",")[0]` and resolves only that tag. If the highest-ranked tag is unsupported, the middleware returns the `bs` fallback immediately instead of considering the remaining preferences. A browser sending `Accept-Language: de-DE,ru;q=0.8,bs;q=0.6` — the shape Chrome produces for a German UI with Russian and Bosnian secondary preferences — is served Bosnian, even though Russian is an explicitly configured locale the user ranked above Bosnian. |
| **Impact** | Users with a non-supported primary UI language and a supported secondary one land on the wrong default. The behaviour is documented as intentional ("falls back to BOSNIAN for unsupported codes", `i18n-spec.md:63-64`), so this is a spec-level trade-off rather than a bug — but the spec does not state the q-value behaviour, and a one-line loop removes the surprise at negligible cost. |
| **Root Cause** | The RFC 9110 preference list is parsed positionally rather than by descending `q` value with a supported-code scan. |
| **Recommendation** | Parse the header into `(tag, q)` pairs, drop `q=0`, sort descending by `q`, and return the first tag that `LanguageLocale.from_code` maps to a configured locale; only then fall back to `BOSNIAN`. Update `docs/01-spec/i18n-spec.md:63-64` to state the q-value rule so the behaviour is specified rather than incidental. If the simpler behaviour is preferred, keep the code and add the q-value note to the spec so the next reader is not surprised. |
| **Effort** | S |
| **Priority** | P2 |
| **Related Findings** | I18N-001 |

**Evidence — `src/backend/apps/core/middleware/language.py:153-160`** *(supports: "only the first tag is examined")*:
```python
accept_language = request.META.get("HTTP_ACCEPT_LANGUAGE", "")
if not accept_language:
    return None
first_tag = accept_language.split(",")[0]
resolved = LanguageLocale.from_code(first_tag, fallback=LanguageLocale.BOSNIAN)
return resolved.value
```

**Evidence — runtime probe** *(supports: "a supported, explicitly preferred `ru` is skipped in favour of the `bs` fallback")*:
```text
accept=de-DE,ru;q=0.8     -> {'request.LANGUAGE_CODE': 'bs', ...}
accept=en-US              -> {'request.LANGUAGE_CODE': 'en', ...}
```

---

## Cross-Finding Analysis

- **Merge candidates:** none. Each finding has a distinct root cause (middleware validation,
  cache-key construction, a library call signature, a missing setting, a parser bug, a
  collector scope, a duplicated write path, a template interpolation). I18N-002 is the only
  one fixed as a side-effect of another (I18N-001), and it is kept separate because its
  remediation differs (defence-in-depth normalisation at the key-building site).
- **Conflicting evidence:** none. The `makemessages` set-diff reports `new=0` (no missing
  msgids) while I18N-014 reports six orphan msgids; these are the two directions of the same
  comparison and are mutually consistent, not contradictory.
- **Dependency chains:** I18N-002 depends on I18N-001 for its primary fix. I18N-006, I18N-007
  and I18N-008 all widen the same gate and can be implemented in one pass; I18N-005 and
  I18N-014 both touch the `.po` parsing/inventory story and are best done together, since
  fixing the parser to be plural-aware is a prerequisite for a credible "no orphan entries"
  test.

## Remediation Roadmap

| Order | ID | Severity | Effort | Priority | Recommendation (summary) |
|-------|----|----------|--------|----------|--------------------------|
| 1 | I18N-001 | HIGH | S | P0 | Normalise/validate the `lang_pref` cookie through `LanguageLocale.from_code` before `translation.activate()` |
| 2 | I18N-003 | HIGH | S | P0 | Pass the `Decimal` (not a string) to `intcomma` in `_format_amount`; assert per-locale separators in `test_price_format.py` |
| 3 | I18N-004 | HIGH | S | P1 | Set `TIME_ZONE` (env-overridable) and replace the four hardcoded en-US date patterns with locale format names |
| 4 | I18N-002 | MEDIUM | S | P1 | Re-normalise the locale at the submenu cache-key build site (defence in depth) |
| 5 | I18N-010 | MEDIUM | S | P1 | Format `active_price_min/max` with the same helper the ad cards use |
| 6 | I18N-005 | MEDIUM | S | P1 | Make `_parse_po_entries` return all plural forms; make `test_no_empty_msgstr` check each |
| 7 | I18N-006 | MEDIUM | S | P1 | Widen the bot gate to all of `telegram_bot/` minus `tests/`; add `BotCommand(description=)` |
| 8 | I18N-008 | MEDIUM | S | P2 | Assert every page template includes `components/locale_head.html` |
| 9 | I18N-007 | MEDIUM | S | P2 | Derive template roots from app configs so `APP_DIRS` templates are scanned |
| 10 | I18N-009 | MEDIUM | S | P2 | Remove the consent-gated client-side cookie write (or gate the server write) and document the contract |
| 11 | I18N-011 | LOW | S | P2 | Add `secure`/`samesite`/`httponly` to the `lang_pref` cookie |
| 12 | I18N-012 | LOW | S | P2 | Add `Cookie` to `Vary` (or mark responses private) so the documented cache contract holds |
| 13 | I18N-015 | LOW | S | P2 | Parse `Accept-Language` q-values and scan for the first supported tag; document the rule |
| 14 | I18N-014 | LOW | S | P2 | Add `--no-obsolete` to the documented `makemessages`; add a stale-entry gate test |
| 15 | I18N-013 | LOW | S/M | P2 | Decide and document: translate `verbose_name`/`help_text`, or record model metadata as an exemption |

## Rollout Safety

| ID | Risk | Backward-compatible? | Test gap (must cover) |
|----|------|----------------------|-----------------------|
| I18N-001 | Low | Yes (canonical values behave identically) | New: `lang_pref=en-US`/`EN`/`xx` must resolve to a configured locale and render `en`/`bs` names, not `ru` |
| I18N-003 | Low | Yes for `en`; changes rendered price strings for `ru`/`bs` | Update `test_format_price_value_uses_intcomma` to assert exact `ru`/`bs` output; add a fractional-amount case |
| I18N-004 | Med | No — every rendered timestamp shifts | New: assert `settings.TIME_ZONE`; assert a known UTC instant renders to Europe/Belgrade local time; snapshot-check the four templates |
| I18N-002 | Low | Yes | Covered indirectly by I18N-001; add an assertion that the cache key locale is one of `ru`/`bs`/`en` |
| I18N-010 | Low | Yes | New: render the chip under `override("ru")` and assert the decimal separator |
| I18N-005 | Low | Yes | New: parser unit test with a blank `msgstr[0]` must be reported |
| I18N-006 | Med | Yes if the four `lifecycle.py` literals are exempted as documented | New: gate must pass on the current tree after the scope widening |
| I18N-008 | Low | Yes | New: the include assertion must pass for all 15 page templates |
| I18N-007 | Low | Yes | New: assert the collector finds at least one root; no behaviour change today |
| I18N-009 | Med | Yes (server write already authoritative) | New: assert `?lang=bs` still sets `lang_pref` with no consent context; assert the JS no longer contains the gate |
| I18N-011 | Low | Yes | New: assert `secure`/`samesite` on the emitted cookie |
| I18N-012 | Low | Yes | Header-only change; no functional test needed beyond a header assertion |
| I18N-015 | Med | Yes for single-tag headers | Update `test_thread_local_matches_request_language_code` with a q-valued header case |
| I18N-014 | Low | Yes | New: stale-entry assertion; run `makemessages --no-obsolete` once and commit the result |
| I18N-013 | Med (if translated) | No — admin labels change | Existing admin tests must tolerate translated labels; snapshot the moderation templates if they assert on English field text |

## Appendices

### Appendix A — `.po` parser plural blind spot (in-memory reproduction)

Run with the project venv; the repository `.po` files are read only and never modified.

```python
import sys
sys.path.insert(0, "src/backend")
from testing.i18n_helpers import _parse_po_entries

SAMPLE = '''
msgid ""
msgstr ""
"Content-Type: text/plain; charset=UTF-8\\n"

msgid "plain"
msgstr "обычный"

#, python-format
msgid "%(counter)s view"
msgid_plural "%(counter)s views"
msgstr[0] ""
msgstr[1] "%(counter)s просмотра"
msgstr[2] "%(counter)s просмотров"
'''

entries = _parse_po_entries(SAMPLE)
for msgid, msgstr in entries:
    print(f"  msgid={msgid!r} msgstr={msgstr!r}")
empties = [m for m, s in entries if m and not s.strip()]
print("reported EMPTY:", empties)          # -> []
print("should be:", ["%(counter)s view"])  # -> blank msgstr[0] missed
```

Output:

```text
  msgid='' msgstr='Content-Type: text/plain; charset=UTF-8\n'
  msgid='plain' msgstr='обычный'
  msgid='%(counter)s view' msgstr='%(counter)s просмотров'
  msgid='%(counter)s views' msgstr='%(counter)s просмотров'
reported EMPTY: []
should be: ['%(counter)s view']
```

*(supports the claim: "`test_no_empty_msgstr` cannot observe a blank singular plural form —
see I18N-005.")*

### Appendix B — `makemessages` set-diff (throwaway container copy, repo untouched)

`makemessages` was executed inside a `docker run --rm` container that copied `/app/src` to
`/tmp/w` first, so the host `.po` files were never written.

```bash
docker run --rm --entrypoint "" \
  -e DJANGO_BUILD=1 -e DJANGO_SETTINGS_MODULE=config.settings.dev \
  -e DJANGO_SECRET_KEY=audit-scratch -e DEBUG=False -e POSTGRES_PASSWORD=audit-scratch \
  mko-bazuna-dev-web:latest bash -lc '
  cp -a /app/src /tmp/w/src; cd /tmp/w
  cp -a src/backend/locale /tmp/po-before
  /opt/venv/bin/python src/backend/manage.py makemessages -l ru -l bs -l en --no-location \
    --ignore=.venv --ignore=.git --ignore=__pycache__ --ignore=*.pyc \
    --ignore=node_modules --ignore=static'
# then set-diff /tmp/po-before/<lang>/… against src/backend/locale/<lang>/…
```

*(supports the claim: "no msgid is missing from any catalogue (R-10) and six are orphaned
(R-14 / I18N-014)." — see the finding block for the full output.)*

### Appendix C — Runtime probe inventory (all read-only, all deleted after the audit)

| Probe | Method | Findings supported |
|---|---|---|
| `probe_locale.py` | `RequestFactory` + `LanguagePreMiddleware.process_request/process_response`; 14 param/cookie/header permutations | R-01…R-04, I18N-001, I18N-011, I18N-012, I18N-015 |
| `probe_locale2.py` | `response.cookies` inspection; `Category`/`City`/`LookupItem`/`Ad` accessors over unsaved instances for 8 locale strings; `{% blocktrans %}`-free `html lang/dir` render | I18N-001, I18N-011, I18N-012 |
| `probe_format.py` | `format_price_value` and `{{ d\|date:… }}` under `translation.override('en'/'ru'/'bs')` | I18N-003, I18N-004 |
| `probe_tz.py` | `settings.TIME_ZONE`, `timezone.get_current_timezone()`, `timezone.localtime()` | I18N-004 |
| `probe_plural.py` | Exact `ads/dashboard.html:95` blocktrans rendered for n = 0,1,2,4,5,11,21,22,25 | R-12 (PASS) |
| `probe_parser.py` | `_parse_po_entries` on an in-memory plural entry with a blank `msgstr[0]` | I18N-005 (Appendix A) |

Gate run (`docker compose --project-name mko-bazuna-test --env-file .env.test -f
docker-compose.yml -f docker-compose.test.yml run --rm -e PYTEST_OPTS="src/backend/apps/ads/tests/test_i18n_completeness.py src/backend/apps/ads/tests/test_i18n_pipeline.py src/backend/apps/ads/tests/test_i18n_category_city.py --tb=short -q" test`)
→ **27 passed**, no database writes outside the ephemeral test database.

### Appendix D — Not audited (and why)

- **`RunTranslationBackfill` management command** — no command or class of that name exists
  in the tree; the only translation-backfill entry point is
  `src/backend/apps/ads/management/commands/backfill_translations.py` (class `Command`).
  Its *runtime* behaviour is Phase 09's territory (translation-client egress and the
  Google-Translate degradation contract, already filed as API-007); only its locale
  targeting was inspected here (`TARGET_LOCALES` → `title_bs`/`title_en`,
  `description_bs`/`description_en`) and found consistent with the spec.
- **Live multi-language rendering in a browser** — the dev `web`/`bot` containers are
  crash-looping on this host (placeholder credentials in `.env.dev`), so no HTTP page could
  be fetched and diffed in a real browser. All rendering claims come from server-side
  template/`gettext` execution inside the `mko-bazuna-test` project, which exercises the same
  `TEMPLATES` configuration and the compiled `.mo` catalogues.
- **`load_exchange_rates` localised-currency-name question** (handed down from Phase 09
  API-008) — resolved as **clean**: `ExchangeRate` has no `name_i18n` column and currency
  display is the ISO-4217 code alone (`apps/currencies/models.py:25-30`,
  `price_tags.py:39`). The `_NON_TRANSLATABLE_TOKENS = {"EUR","RSD","BAM"}` allowance in the
  completeness gate is therefore correct, not a gap.
- **Translation quality beyond plural correctness** — the `ru`/`bs` `msgstr` values were
  spot-checked (dashboard plurals, price/threshold strings, privacy page) and are
  grammatically correct; a full linguistic review of all 411 entries per locale is outside
  an architecture audit's remit.

---
