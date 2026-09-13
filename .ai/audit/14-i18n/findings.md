---
phase: "14"
phase_name: "Internationalization & Localization Correctness"
date: "2026-09-13"
auditor: "Executor (subagent)"
validator: ""
mode: "problems-only"
id_prefix: "I18N"
report_status: "draft"
severity_taxonomy: ".kilo/commands/audit/phases/14-audit-i18n.md#severity-taxonomy"
---

# Audit Findings — Internationalization & Localization Correctness

## Executive Summary

Seven findings (1 CRITICAL, 3 HIGH, 2 MEDIUM, 1 LOW). Confirmed correct: locale-priority chain, DB-based i18n cache segmentation, fallback accessors, per-ad title filtering, plural-form rules, `.mo` compilation, immediate-alert notification localization, and per-language FTS vectors. Three structural gaps: (1) the daily saved-search digest (`send_alerts.py:_format_digest`) ignores the identity's stored Telegram language and ships hardcoded English with raw Russian ad titles; (2) the `?lang=` parameter path rejects language variants like `en-US` instead of normalizing to `en` (spec calls for `LanguageLocale.from_code()` which is never called); (3) the completeness test gate strips `<title>`/`<head>` tags from its scan, never extracts msgids from templates, and does not check hreflang, plural forms, or locale switching — masking multiple rendering defects.

## Scope & Methodology

**Scope:** Web locale middleware (`apps/core/middleware/language.py`, `apps/core/enums.py`), per-user Telegram language in bot notifications (`apps/search/services/immediate_alerts.py`, `apps/search/management/commands/send_alerts.py`), DB-based i18n fallback accessors (`Category`/`City`/`LookupItem.get_name`), submenu cache key locale segmentation (`apps/categories/views.py:46-59`), i18n completeness gate (`apps/ads/tests/test_i18n_completeness.py`), 15 public/seller-facing templates for `<title>`, `<html lang>`, `hreflang`, `dir`, inline-JS i18n, `.po`/`.mo` artifacts (`src/backend/locale/`), and the i18n spec (`docs/01-spec/i18n-spec.md`).

### Runtime Verification

| R# | Check | Method | Result |
|----|-------|--------|--------|
| R-01 | Locale priority: param > cookie > Accept-Language > default | Read `LanguagePreMiddleware.process_request` (language.py L59-76) | PASS |
| R-02 | `lang_pref` cookie TTL ~1 year | Read `LANGUAGE_COOKIE_MAX_AGE` (language.py L36) | PASS — 365 days |
| R-03 | Accept-Language normalizes `en-US` → `en` | Read `_parse_accept_language` (language.py L133-145) | PASS |
| R-04 | Submenu cache key carries locale segment | Read `categories/views.py:46-59` | PASS |
| R-05 | `name_i18n` populated for all 3 languages | grep seed fixtures + script output | PASS |
| R-06 | Immediate alerts honor `user.telegram_language` | Read `immediate_alerts.py:171-172` | PASS |
| R-07 | No raw `.get_name` bypass in templates | grep `.get_name` in templates | PASS |
| R-08 | `.mo` compiled for every `.po` | glob `locale/**/*.mo` (3 files) | PASS |
| R-09 | Plural-form rules correct (nplurals=3) | Read .po headers | PASS — ru/bs: nplurals=3, en: nplurals=2 |
| R-10 | `?lang=` param normalizes variants | Read `_apply_lang_param` → `_is_valid_language` | FAIL — en-US rejected |
| R-11 | Daily digest respects per-user language | Read `send_alerts.py:165, 185-197` | FAIL — no user/locale |
| R-12 | `hreflang` emitted per language | grep across templates | FAIL — 0 matches |
| R-13 | `<title>` tags localized | grep `<title` (15 matches) | PARTIAL — 1/15 unlocalized |
| R-14 | `<html lang>` reflects active locale | grep `<html lang=` (15 matches) | FAIL — all `lang="en"` |
| R-15 | `dir=` attribute discipline | grep `dir=` across templates | FAIL — 0 matches |
| R-16 | Completeness gate covers title/hreflang/plurals | Read test_i18n_completeness.py L122-133, L246-265 | FAIL — gate is narrow |
| R-17 | Cross-.po msgid consistency | Python script (`tmp_extract_fix.py`) | PASS — 329 msgids each |

> PASS results prove the audit was thorough; they are METHODOLOGY evidence, NOT findings.

**Tools used:** `grep`, `read` (source inspection), Python script for .po/template extraction analysis.

**Assumptions:** Production uses Redis-backed cache (LocMemCache in dev/test); PostgreSQL 18; Django 5.2; bot shares the web DB via `django.setup()` + shared ORM; migrations run exactly once before both processes start.

## Findings Summary

| ID | Title | Severity | Status | Category |
|----|-------|----------|--------|----------|
| I18N-001 | Daily digest ignores per-user bot language | CRITICAL | Open | Per-user Language Binding |
| I18N-002 | `?lang=` param does not normalize variants (`en-US`→`en`) | HIGH | Open | Locale-priority Normalization |
| I18N-003 | Completeness gate is narrow; no template-to-.po extraction | HIGH | Open | Completeness Coverage |
| I18N-004 | `hreflang`/`rel="alternate"` missing on all pages | HIGH | Open | SEO / hreflang |
| I18N-005 | Untranslated `<title>` in `ads/dashboard.html` | MEDIUM | Open | Title Tags |
| I18N-006 | `<html lang="en">` hardcoded + no `dir` attribute | MEDIUM | Open | Script & Direction |
| I18N-007 | `en` `.po` POT-Creation-Date stale (6 days behind ru/bs) | LOW | Open | Pipeline Hygiene |

## Distribution

**Severity counts**

| CRITICAL | HIGH | MEDIUM | LOW |
|----------|------|--------|-----|
| 1 | 3 | 2 | 1 |

**Status counts**

| Status | Count |
|--------|-------|
| Open | 7 |

## Findings by Severity

### CRITICAL

#### I18N-001: [CRITICAL] — Daily digest ignores per-user bot language

| Field | Value |
|---|---|
| **ID** | I18N-001 |
| **Title** | Daily digest ignores per-user bot language |
| **Severity** | CRITICAL |
| **Category** | Per-user Language Binding |
| **File(s)** | `src/backend/apps/search/management/commands/send_alerts.py:165, 185-197` |
| **Status** | Open |
| **Problem** | The daily saved-search digest path (`send_alerts.py`) does not propagate the identity's stored Telegram language to notification content. `_send_user_digests` fetches the user (L149) but calls `self._format_digest(unique_ads)` (L165) WITHOUT passing the user or their locale. `_format_digest` (L185-197) hardcodes English strings (`f"New ads matching your saved searches ({len(ads)} found):\n"`) and renders `ad.title[:50]` (the raw Russian `Ad.title` column), never reading `user.telegram_language`, never activating a translation context, and never using `gettext`. The immediate-alert path (`immediate_alerts.py:171-172`) does this correctly: it reads `user.telegram_language`, wraps rendering in `translation_override(locale)`, and calls `ad.get_title(locale)` / `ad.city.get_name(locale)`. |
| **Impact** | A Bosnian-speaking user (`telegram_language="bs"`) receives the daily digest in English with Russian ad titles, while immediate alerts render correctly in Bosnian. This is the only notification channel where per-user language binding is broken. Per the phase severity taxonomy: "Per-user bot language not propagated to notifications" is CRITICAL. |
| **Root Cause** | `_format_digest` was written independently of `immediate_alerts.py:build_alert_message` and never integrated with the per-user language binding pattern. It has no `user` or `locale` parameter and uses no `gettext`/translation-override primitives. |
| **Recommendation** | (1) Extend `_send_user_digests` to pass `user.telegram_language` into `_format_digest`. (2) Wrap message construction in `translation.override(locale)`. (3) Replace hardcoded f-strings with `gettext()` calls so they are extracted into `.po` files. (4) Replace `ad.title[:50]` with `ad.get_title(locale)[:50]`. Mirror the pattern in `immediate_alerts.py:112-131`. |
| **Effort** | S |
| **Priority** | P0 |

| **Related Findings** | I18N-003 (gate doesn't verify bot notification localization) |

**Evidence — `send_alerts.py:165`** *(supports: "_format_digest called without user/locale context")*:
```python
message = self._format_digest(unique_ads)
```

**Evidence — `send_alerts.py:185-197`** *(supports: "_format_digest hardcodes English, uses raw ad.title")*:
```python
def _format_digest(self, ads: list) -> str:
    lines = [f"New ads matching your saved searches ({len(ads)} found):\n"]
    for ad in ads:
        price_str = (
            f" - {format_price_value(ad.price_amount, ad.price_currency)}"
            if ad.price_amount is not None
            else ""
        )
        lines.append(f"• {ad.title[:50]}\n  {price_str}\n")
    return "\n".join(lines)
```

**Evidence — `send_alerts.py:147-149`** *(supports: "user object fetched but locale never read")*:
```python
for user_id, ads in user_ads.items():
    user = await User.objects.aget(id=user_id)
    ...
```

**Evidence — `immediate_alerts.py:168-172`** *(supports: "immediate-alert path correctly reads user.lang + translation_override")*:
```python
locale = getattr(user, "telegram_language", None) or LanguageLocale.RUSSIAN.value
text, reply_markup = build_alert_message(ad, saved_search, locale=locale)
```

---

### HIGH

#### I18N-002: [HIGH] — `?lang=` query parameter does not normalize language variants

| Field | Value |
|---|---|
| **ID** | I18N-002 |
| **Title** | `?lang=` query parameter does not normalize language variants |
| **Severity** | HIGH |
| **Category** | Locale-priority Normalization |
| **File(s)** | `src/backend/apps/core/middleware/language.py:104, 147-150` |
| **Status** | Open |
| **Problem** | The i18n spec (i18n-spec.md L63-64) states "The resolved code is normalized by `LanguageLocale.from_code()` (accepts `en-US` → `en`...)." The `LanguagePreMiddleware` never calls `from_code()`. Instead, `_apply_lang_param` (L104) validates the raw `?lang=` value via `_is_valid_language(lang)` (L148-150), which performs a direct membership check `lang in LanguageLocale.values()`. A variant like `en-US` fails this check, is logged as a warning, and falls back to `settings.LANGUAGE_CODE` (`ru`) instead of normalizing to `en`. The `Accept-Language` path (`_parse_accept_language`, L142) achieves normalization by coincidence via manual `.split("-")[0]`, but the `?lang=` path has no such normalization. |
| **Impact** | A user clicking `?lang=en-US` gets Russian instead of English. The spec promises `from_code()` normalization; the implementation bypasses it. Per the phase taxonomy, incomplete normalization where a documented normalization function exists but is not used is HIGH. |
| **Root Cause** | `_apply_lang_param` calls `_is_valid_language` (raw string membership check) instead of routing through `LanguageLocale.from_code()` for normalization before validation. |
| **Recommendation** | Replace `_is_valid_language(lang)` in `_apply_lang_param` with `LanguageLocale.from_code(lang, fallback=None)` — if the result is non-None, use it; if None, log and fall back. Apply the same `from_code()` pattern in `_parse_accept_language` to remove the manual `.split("-")[0]` duplication. Also reconcile the fallback default: spec says `bs`, code uses `settings.LANGUAGE_CODE` (`ru`). |
| **Effort** | S |
| **Priority** | P1 |

| **Related Findings** | I18N-003 (gate doesn't test `?lang=` normalization) |

**Evidence — `language.py:104, 147-150`** *(supports: "direct membership check, no normalization")*:
```python
if not self._is_valid_language(lang):          # en-US → False
    logger.warning("Ignoring invalid lang parameter: %s", lang)
    self._set_language_code(request, settings.LANGUAGE_CODE)  # → ru, not en
```
```python
@staticmethod
def _is_valid_language(lang: str) -> bool:
    return lang in LanguageLocale.values()     # {"ru","bs","en"} — no normalization
```

**Evidence — `language.py:142`** *(supports: "Accept-Language path normalizes by manual split")*:
```python
lang = accept_language.split(",")[0].split("-")[0]  # en-US → en (manual, not from_code)
```

**Evidence — `i18n-spec.md:63-64`** *(supports: "spec says from_code() is used")*:
```text
The resolved code is normalized by LanguageLocale.from_code() (accepts en-US → en,
falls back to bs when unsupported).
```

---

#### I18N-003: [HIGH] — Completeness gate is narrow; no template-to-.po extraction

| Field | Value |
|---|---|
| **ID** | I18N-003 |
| **Title** | Completeness gate is narrow; no template-to-.po extraction |
| **Severity** | HIGH |
| **Category** | Completeness Coverage |
| **File(s)** | `src/backend/apps/ads/tests/test_i18n_completeness.py:122-133, 246-265` |
| **Status** | Open |
| **Problem** | The completeness gate (`test_i18n_completeness.py`) has 5 tests but does NOT verify what the phase task requires. (1) `_SKIP_TAGS` includes `"head"` (L125) and `"title"` (L131), so `test_no_hardcoded_visible_text` strips all `<title>` content before scanning — making any untranslated title text invisible (masks I18N-005). (2) `test_extraction_completeness` (L246-265) only checks cross-.po consistency (that msgids in one .po exist in all others); it does NOT extract msgids from templates and verify they exist in the .po files. (3) No test checks `hreflang` emission, plural-form correctness, or locale-switching re-render. The spec (i18n-spec.md L268-278) documents `test_extraction_completeness` as verifying "every `{% trans %}` msgid exists in all three `.po` files" — but the test only verifies cross-.po consistency, not template-to-.po extraction. |
| **Impact** | The gate passes green while 10 `{% blocktrans %}`/`{% plural %}` blocks, all 15 hardcoded `<html lang>` attributes, all missing `hreflang`, and untranslated `<title>` strings ship to production undetected. This directly enabled I18N-004, I18N-005, and I18N-006 to be found by manual inspection rather than by CI. |
| **Root Cause** | The gate was scoped to the original 4 Spec_29 T-13 guards. The phase-14 dimensions (title, hreflang, plurals, switching, template-to-po extraction) were never added. `_SKIP_TAGS` treating `title`/`head` as non-visible is overly broad. |
| **Recommendation** | (1) Remove `"title"` from `_SKIP_TAGS`. (2) Add `test_template_extraction_coverage`: extract all `{% trans %}`, `{% blocktrans %}`, `{% plural %}`, `{{ _("…") }}` msgids from templates and assert each exists in all three `.po` files. (3) Add `test_hreflang_present`. (4) Add `test_plural_forms`: assert each `.po` `Plural-Forms` header matches CLDR. (5) Add `test_locale_switch_re_render`. |
| **Effort** | M |
| **Priority** | P1 |

| **Related Findings** | I18N-004, I18N-005, I18N-006, I18N-007 |

**Evidence — `test_i18n_completeness.py:122-133`** *(supports: "`_SKIP_TAGS` includes `head` and `title`")*:
```python
_SKIP_TAGS = (
    "script", "style", "head", "meta",
    "input", "br", "hr", "link", "title", "code",
)
```

**Evidence — `test_i18n_completeness.py:246-265`** *(supports: "`test_extraction_completeness` only checks cross-.po consistency")*:
```python
def test_extraction_completeness() -> None:
    """Every msgid in one .po file exists in all other .po files."""
    all_msgids = set()
    by_lang = {}
    for po_path in _po_files():
        entries = _parse_po_entries(...)
        msgids = {msgid for msgid, _ in entries if msgid}
        by_lang[lang] = msgids
        all_msgids.update(msgids)
    for lang, msgids in by_lang.items():
        missing = all_msgids - msgids   # ← only cross-.po, NOT template extraction
```

**Evidence — script output** *(supports: "10 blocktrans/plural blocks not checked by extraction test")*:
```text
=== {% blocktrans %} / plural blocks NOT checked by extraction test ===
  privacy.html: 4 entries (site_name, code tags)
  ads/dashboard.html: 2 plural entries (counter view/contacts)
  ads/edit.html: 1 entry (Photo counter)
  users/login_issue.html: 1 entry (Login to site_name)
  ads/partials/ad_list.html: 2 entries (Price range, No results)
  Total blocktrans/endtrans: 10
```

---

#### I18N-004: [HIGH] — `hreflang`/`rel="alternate"` missing on all pages

| Field | Value |
|---|---|
| **ID** | I18N-004 |
| **Title** | `hreflang`/`rel="alternate"` missing on all pages |
| **Severity** | HIGH |
| **Category** | SEO / hreflang |
| **File(s)** | All templates under `src/backend/templates/` (0 matches) |
| **Status** | Open |
| **Problem** | No template emits `<link rel="alternate" hreflang="...">` for the supported language matrix (ru, bs, en). Grep across all `.html` templates returns zero matches for `hreflang`. The phase task §5(f) requires hreflang for the supported matrix; §5(f) evidence states "Missing hreflang on language switches is a finding." |
| **Impact** | Search engines cannot discover per-language alternate URLs; hreflang-related SEO credit is lost and cross-language canonicalization risks duplicate-content penalties. Locale switching relies solely on cookie/param with no discoverability signal for crawlers. |
| **Root Cause** | No base template or context processor injects hreflang `<link>` tags into the `<head>`. |
| **Recommendation** | Add hreflang link tags to the base template's `<head>`. Use `{{ request.path }}?lang=<code>` as the href for each `LanguageLocale` value, excluding a self-referential `x-default`. A context processor that emits the list of supported locales is the cleanest insertion point. |
| **Effort** | M |
| **Priority** | P1 |

| **Related Findings** | I18N-003 (gate doesn't verify hreflang) |

**Evidence — grep** *(supports: "Zero hreflang or rel=alternate across all templates")*:
```text
$ grep -rn "hreflang" src/backend/templates/
No files found
```

---

### MEDIUM

#### I18N-005: [MEDIUM] — Untranslated `<title>` string in `ads/dashboard.html`

| Field | Value |
|---|---|
| **ID** | I18N-005 |
| **Title** | Untranslated `<title>` string in `ads/dashboard.html` |
| **Severity** | MEDIUM |
| **Category** | Title Tags |
| **File(s)** | `src/backend/templates/ads/dashboard.html:12` |
| **Status** | Open |
| **Problem** | `<title>Dashboard - {{ site_name }}</title>` uses a bare English "Dashboard" string not wrapped in `{% trans %}`. All 14 other page templates correctly use `{% trans "…" %}` (or `{{ ad|get_title:LANGUAGE_CODE }}` for detail.html). |
| **Impact** | Users viewing the seller dashboard in `bs` or `ru` see the browser-tab title in English while the rest of the page is localized — inconsistent UI. Invisible to the test gate because `_SKIP_TAGS` strips `<title>` (I18N-003). |
| **Root Cause** | The `{% trans %}` tag was omitted during template authoring for this one page. |
| **Recommendation** | Wrap the literal: `<title>{% trans "Dashboard" %} - {{ site_name }}</title>`. Verify `msgstr` exists for "Dashboard" in `ru.po`/`bs.po`. |
| **Effort** | T |
| **Priority** | P2 |

| **Related Findings** | I18N-003 (gate excludes title tags) |

**Evidence — `ads/dashboard.html:12`** *(supports: "bare English Dashboard in title")*:
```django
<title>Dashboard - {{ site_name }}</title>
```

**Evidence — grep `<title`** *(supports: "14/15 templates correctly localize")*:
```text
14 templates use {% trans "..." %} or {{ ...|get_title:LANGUAGE_CODE }}
1 template (dashboard.html:12) uses bare <title>Dashboard - ...
```

---

#### I18N-006: [MEDIUM] — `<html lang="en">` hardcoded + no `dir` attribute on all templates

| Field | Value |
|---|---|
| **ID** | I18N-006 |
| **Title** | `<html lang="en">` hardcoded + no `dir` attribute on all templates |
| **Severity** | MEDIUM |
| **Category** | Script & Direction |
| **File(s)** | All 15 page templates (e.g. `ads/dashboard.html:8`) |
| **Status** | Open |
| **Problem** | All 15 page templates hardcode `<html lang="en">` regardless of the active locale (ru, bs, or en). None bind to `{{ LANGUAGE_CODE }}`. No template emits a `dir` attribute, so BiDi direction discipline is absent. |
| **Impact** | Screen readers announce content in an English voice regardless of the rendered language; search engines index pages as English. The phase taxonomy (§5(h)) requires `dir` attribute discipline; its absence is MEDIUM. |
| **Root Cause** | Templates were scaffolded with a static `<html lang="en">` and never updated to bind to `LANGUAGE_CODE`. The `i18n` context processor provides `LANGUAGE_CODE` and `LANGUAGE_BIDI` but no template consumes them for the root element. |
| **Recommendation** | Replace `<html lang="en">` with `<html lang="{{ LANGUAGE_CODE|lower }}" dir="{{ LANGUAGE_BIDI|yesno:"rtl,ltr" }}">` in all 15 templates (single base-template edit if they extend a common base). Since ru/bs/en are all LTR, `dir="ltr"` is correct — the fix is explicitness/consistency, not RTL. |
| **Effort** | S |
| **Priority** | P2 |

| **Related Findings** | None |

**Evidence — grep** *(supports: "All 15 templates hardcode lang=en, zero dir attrs")*:
```text
$ grep -rn '<html lang="en"' src/backend/templates/
15 matches — every page template

$ grep -rn 'dir=' src/backend/templates/
No files found
```

---

### LOW

#### I18N-007: [LOW] — `en` `.po` POT-Creation-Date stale (6 days behind ru/bs)

| Field | Value |
|---|---|
| **ID** | I18N-007 |
| **Title** | `en` `.po` POT-Creation-Date stale (6 days behind ru/bs) |
| **Severity** | LOW |
| **Category** | Pipeline Hygiene |
| **File(s)** | `src/backend/locale/en/LC_MESSAGES/django.po`, `src/backend/locale/ru/LC_MESSAGES/django.po`, `src/backend/locale/bs/LC_MESSAGES/django.po` |
| **Status** | Open |
| **Problem** | The `en` `.po` file has `POT-Creation-Date: 2026-09-04 10:29-0500` while `ru` and `bs` both have `2026-09-10 04:56-0500` — a 6-day staleness gap. The script confirmed all three files have 329 msgids and are cross-consistent (no missing msgids), so current extraction is functionally correct. The staleness indicates the `en` file was not re-extracted in the same batch as `ru`/`bs`, suggesting per-locale rather than atomic extraction. |
| **Impact** | Risk of future drift: if `makemessages` is run for `ru`/`bs` but not `en`, new msgids could be missing from `en` and `test_extraction_completeness` would still pass (cross-.po only). A template-to-.po extraction test (I18N-003) would catch this; the current gate would not. |
| **Root Cause** | The extraction pipeline (`makemessages`) is likely run per-locale (`-l ru -l bs -l en`) without a synchronization check ensuring all `.po` files share the same `POT-Creation-Date`. |
| **Recommendation** | (1) Re-run `makemessages` for all languages in a single invocation to resynchronize. (2) Add an assertion in `test_i18n_pipeline.py` that all three `.po` files share the same `POT-Creation-Date`. |
| **Effort** | T |
| **Priority** | P2 |

| **Related Findings** | I18N-003 (gate doesn't check extraction staleness) |

**Evidence — script output** *(supports: "POT-Creation-Date mismatched across locales")*:
```text
=== POT-Creation-Date per locale ===
  bs: "POT-Creation-Date: 2026-09-10 04:56-0500\n"
  en: "POT-Creation-Date: 2026-09-04 10:29-0500\n"
  ru: "POT-Creation-Date: 2026-09-10 04:56-0500\n"
```

---

## Cross-Finding Analysis

- **Merge candidates:** None — each finding has a distinct root cause.
- **Conflicting evidence:** None.
- **Dependency chains:** I18N-005 (untranslated "Dashboard" title) is masked by I18N-003 (gate excludes `<title>` tags). Fixing I18N-003 by removing `title` from `_SKIP_TAGS` would surface I18N-005 in CI. I18N-007 (stale `en` `.po`) is masked by the same cross-.po-only extraction check in I18N-003.

## Remediation Roadmap

| Order | ID | Severity | Effort | Priority | Recommendation (summary) |
|-------|----|----------|--------|----------|--------------------------|
| 1 | I18N-001 | CRITICAL | S | P0 | Localize `_format_digest` with `user.telegram_language` + `translation.override` + `gettext` + `ad.get_title(locale)` |
| 2 | I18N-002 | HIGH | S | P1 | Normalize `?lang=` via `LanguageLocale.from_code()`; reconcile fallback default (spec: bs, code: ru) |
| 3 | I18N-003 | HIGH | M | P1 | Remove `title` from `_SKIP_TAGS`; add template-to-.po extraction, hreflang, plural-form, and locale-switch gate tests |
| 4 | I18N-004 | HIGH | M | P1 | Add `hreflang`/`rel="alternate"` link tags to base template `<head>` |
| 5 | I18N-005 | MEDIUM | T | P2 | Wrap "Dashboard" in `{% trans %}` in `ads/dashboard.html` |
| 6 | I18N-006 | MEDIUM | S | P2 | Bind `<html lang>` to `{{ LANGUAGE_CODE }}` + add `dir` attribute in all 15 templates |
| 7 | I18N-007 | LOW | T | P2 | Re-run `makemessages` for all locales; assert `POT-Creation-Date` synchronized in `test_i18n_pipeline.py` |

## Rollout Safety

| ID | Risk | Backward-compatible? | Test gap (must cover) |
|----|------|----------------------|-----------------------|
| I18N-001 | Low | Yes | No test asserts daily digest content is localized per user language |
| I18N-002 | Low | Yes | No test passes `?lang=en-US` and asserts resolution to `en` |
| I18N-003 | Med | Yes | Gate lacks template-to-po extraction, title, hreflang, plural, switch tests |
| I18N-004 | Low | Yes | No test asserts `<link rel="alternate" hreflang>` in rendered HTML |
| I18N-005 | Low | Yes | Gate excludes `title` from scanning — would not catch regression |
| I18N-006 | Low | Yes | No test asserts `<html lang>` matches active locale or `dir` present |
| I18N-007 | Low | Yes | No check on `POT-Creation-Date` synchronization across locales |

## Appendices

### Appendix A — Confirmed correct behaviors (not findings)

| Behavior | Evidence |
|----------|----------|
| Locale priority chain (param > cookie > Accept-Language > default) | `language.py:59-76` |
| `lang_pref` cookie TTL = 1 year | `language.py:36` — `365 * 24 * 60 * 60` |
| Accept-Language normalizes `en-US` → `en` | `language.py:142` — `.split("-")[0]` |
| Submenu cache key includes `<locale>` segment | `categories/views.py:46-59` |
| `name_i18n` populated for all 3 languages | Seed fixtures (cities.json, YAML categories) |
| Immediate alerts honor `user.telegram_language` | `immediate_alerts.py:168-172` |
| Fallback chain: locale → ru → name | `categories/models.py:53-62`, `locations/models.py:45-54`, `lookups/models.py:88-96` |
| No raw `.get_name` bypass in templates | grep `.get_name` in templates — 0 matches |
| `.mo` compiled for every `.po` | glob `locale/**/*.mo` — 3 files (ru, bs, en) |
| Plural-form rules correct | ru/bs: `nplurals=3` Slavic rule; en: `nplurals=2` |
| Per-language FTS vectors | Spec i18n-spec.md L161-175 — `search_vector_ru/bs/en` |
| `ad.title_en`/`ad.title_bs` columns exist | `ads/models.py:43-75` |
| Ad title via `get_title` filter | `ads/detail.html:14` — `{{ ad|get_title:LANGUAGE_CODE }}` |

### Appendix B — Script output (extraction completeness)

```text
=== PO FILE MSGID COUNTS ===
  bs: 329 msgids
  en: 329 msgids
  ru: 329 msgids
  Total unique: 329
  bs: consistent with all [OK]
  en: consistent with all [OK]
  ru: consistent with all [OK]

=== TEMPLATE EXTRACTION (33 templates, excluded 4) ===
  Template msgids (inline trans + gettext): 214

=== MISSING FROM .po FILES ===
  All 214 template msgids in all .po files [OK]

=== {% blocktrans %} / plural blocks NOT checked by extraction test ===
  privacy.html: 4 entries (site_name, code tags)
  ads/dashboard.html: 2 plural entries (counter view/contacts)
  ads/edit.html: 1 entry (Photo counter)
  users/login_issue.html: 1 entry (Login to site_name)
  ads/partials/ad_list.html: 2 entries (Price range, No results)
  Total blocktrans/endtrans: 10
```

### Appendix C — Grep evidence (FAIL conditions)

```text
$ grep -rn "hreflang" src/backend/templates/
No files found

$ grep -rn '<html lang="en"' src/backend/templates/
15 matches — all page templates

$ grep -rn 'dir=' src/backend/templates/
No files found

$ grep -rn '<title' src/backend/templates/
15 matches — 14 wrapped in {% trans %} or get_title filter; 1 bare ("Dashboard")
```
