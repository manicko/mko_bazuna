---
phase: "14"
phase_name: "Internationalization & Localization Correctness"
date: "2026-09-13"
auditor: "Executor (subagent)"
validator: "Validator (subagent)"
mode: "problems-only"
id_prefix: "I18N"
source_findings: ".ai/audit/14-i18n/findings.md"
report_status: "validated"
---

# Validated Audit Findings — Internationalization & Localization Correctness

## Validator's Note

The source findings file contains **7 findings** (I18N-001 through I18N-007), not 6 as referenced in the task brief. The executive summary explicitly states "Seven findings (1 CRITICAL, 3 HIGH, 2 MEDIUM, 1 LOW)" and the findings summary table lists all 7 IDs. All 7 have been validated below.

**Validation methodology:** Each finding was verified against source code by reading the cited files at the cited line numbers, confirming the described defect exists, confirming the related code paths referenced as reference patterns (e.g. `immediate_alerts.py`), and confirming grep-based evidence claims.

---

## Validation Summary

| ID | Title | Severity | Status | Type | Decision |
|----|-------|----------|--------|------|----------|
| I18N-001 | Daily digest ignores per-user bot language | CRITICAL | Open | SPEC-DEVIATION | Approved |
| I18N-002 | `?lang=` param does not normalize variants | HIGH | Open | SPEC-DEVIATION | Approved |
| I18N-003 | Completeness gate is narrow; no template-to-.po extraction | HIGH | Open | BEST-PRACTICE | Approved |
| I18N-004 | `hreflang`/`rel="alternate"` missing on all pages | HIGH | Open | BEST-PRACTICE | Approved |
| I18N-005 | Untranslated `<title>` in `ads/dashboard.html` | MEDIUM | Open | SPEC-DEVIATION | Approved |
| I18N-006 | `<html lang="en">` hardcoded + no `dir` attribute | MEDIUM | Open | BEST-PRACTICE | Approved |
| I18N-007 | `en` `.po` POT-Creation-Date stale | LOW | Open | BEST-PRACTICE | Approved |

**All 7 findings validated — 0 rejected, 0 merged.**

---

## Findings by Severity

### CRITICAL

#### I18N-001: [CRITICAL] — Daily digest ignores per-user bot language

**Decision:** APPROVED as `SPEC-DEVIATION`

**Validation evidence:**

1. **Source code confirmed — `send_alerts.py:165`:**
   ```python
   message = self._format_digest(unique_ads)
   ```
   The method is called with only `unique_ads` — no `user` or `locale` parameter is passed.

2. **Source code confirmed — `send_alerts.py:185-197` (`_format_digest`):**
   ```python
   def _format_digest(self, ads: list) -> str:
       """Format digest message for a user."""
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
   - Hardcodes English string `"New ads matching your saved searches..."` — never calls `gettext()`.
   - Uses `ad.title[:50]` — the raw `Ad.title` column (Russian), instead of `ad.get_title(locale)[:50]` which the project provides for per-user locale rendering.
   - No `translation.override()` context manager, no `from django.utils import translation`.
   - Confirmed: `override`/`translation_override` is NOT imported anywhere in `send_alerts.py` (grep found it only in `immediate_alerts.py`).

3. **Contrast confirmed — `immediate_alerts.py:168-172` (correct pattern):**
   ```python
   locale = getattr(user, "telegram_language", None) or LanguageLocale.RUSSIAN.value
   text, reply_markup = build_alert_message(ad, saved_search, locale=locale)
   ```
   The immediate-alert path reads `user.telegram_language`, passes it to `build_alert_message` which activates a `translation_override(locale)` context and calls `ad.get_title(locale)` / `ad.city.get_name(locale)`.

4. **`.po` extraction confirmed — 0 matches:** Grep for `"New ads matching"` across `src/backend/locale/{en,ru,bs}/LC_MESSAGES/django.po` returns zero matches in all three files. The digest string is never extracted, confirming it is entirely hardcoded.

5. **Spec alignment:** The i18n spec (i18n-spec.md) requires per-user language binding for notification channels. The immediate-alert path implements this correctly; the daily digest path does not.

**Classification rationale:** This is a `SPEC-DEVIATION` — the implementation directly contradicts the project's i18n spec, which mandates that notification content respects the user's stored `telegram_language`. The daily digest is the only notification channel where this binding is broken. The root cause is architectural: `_format_digest` was written independently of `immediate_alerts.py:build_alert_message` and lacks any locale parameter.

**Required fix:**
- Pass `user.telegram_language` into `_format_digest` (add a `locale` parameter).
- Wrap message construction in `translation.override(locale)`.
- Replace hardcoded f-strings with `gettext()` calls so they are extracted to `.po` files.
- Replace `ad.title[:50]` with `ad.get_title(locale)[:50]`.

---

### HIGH

#### I18N-002: [HIGH] — `?lang=` query parameter does not normalize language variants

**Decision:** APPROVED as `SPEC-DEVIATION`

**Validation evidence:**

1. **Source code confirmed — `language.py:104` (`_apply_lang_param`):**
   ```python
   if not self._is_valid_language(lang):           # en-US → False
       logger.warning("Ignoring invalid lang parameter: %s", lang)
       self._set_language_code(request, settings.LANGUAGE_CODE)  # → ru, not en
   ```
   The `?lang=` parameter is validated via `_is_valid_language()` before any normalization.

2. **Source code confirmed — `language.py:147-150` (`_is_valid_language`):**
   ```python
   @staticmethod
   def _is_valid_language(lang: str) -> bool:
       """Return ``True`` if *lang* is a supported ``LanguageLocale`` value."""
       return lang in LanguageLocale.values()     # {"ru","bs","en"} — no normalization
   ```
   This is a raw string membership check against `{"ru", "bs", "en"}`. A variant like `en-US` returns `False`, triggers the warning, and falls back to `settings.LANGUAGE_CODE` (Russian in production).

3. **Spec-defined normalization function exists but is unused — `enums.py:202-222` (`LanguageLocale.from_code`):**
   ```python
   @classmethod
   def from_code(
       cls,
       language_code: str | None,
       *,
       fallback: LanguageLocale | None = None,
   ) -> LanguageLocale:
       """Resolve a Telegram/IETF language_code to a LanguageLocale.

       Normalizes tags like 'en-US' to 'en', maps to the enum, and returns
       fallback when the code is None or unsupported.
       """
       if fallback is None:
           fallback = cls.BOSNIAN
       if not language_code:
           return fallback
       base = language_code.split("-")[0].lower()
       for member in cls:
           if member.value == base:
               return member
       return fallback
   ```
   This method explicitly normalizes `en-US` → `en`. It is **never called** from `language.py`. Grep for `from_code` in `language.py` returns zero matches.

4. **Accept-Language path normalizes by manual split — `language.py:142`:**
   ```python
   lang = accept_language.split(",")[0].split("-")[0]  # en-US → en (manual, not from_code)
   ```
   The Accept-Language path achieves normalization "by coincidence" via manual `.split("-")[0]`, while the `?lang=` path uses `_is_valid_language` with no normalization.

5. **Spec alignment confirmed — `i18n-spec.md:63-64`:**
   > The resolved code is normalized by `LanguageLocale.from_code()` (accepts `en-US` → `en`, falls back to `bs` when unsupported).

   The spec states `from_code()` is used for normalization with a `bs` fallback. The implementation bypasses `from_code()` entirely and uses `settings.LANGUAGE_CODE` (Russian) as the fallback — a second spec deviation.

6. **Test gap confirmed — `test_language_middleware.py`:** No test passes `?lang=en-US` and asserts resolution to `en`. Grep for `en-US` in test files returns zero matches.

**Classification rationale:** This is a `SPEC-DEVIATION` — the implementation violates the i18n spec at i18n-spec.md L63-64 in two ways: (1) it does not call `from_code()` for normalization, causing `en-US` to fall back to Russian; (2) the fallback default is `settings.LANGUAGE_CODE` (`ru`) rather than the spec's `bs`. The spec explicitly documents `from_code()` as the normalization mechanism, and the method exists in the codebase but is never invoked from the middleware.

**Required fix:**
- Replace `_is_valid_language(lang)` in `_apply_lang_param` with `LanguageLocale.from_code(lang, fallback=None)` — if non-None, use the result; if None, log and fall back.
- Apply the same `from_code()` pattern in `_parse_accept_language` to remove the manual `.split("-")[0]` duplication.
- Reconcile the fallback default: use `LanguageLocale.BOSNIAN` (spec-compliant) instead of `settings.LANGUAGE_CODE`.

---

#### I18N-003: [HIGH] — Completeness gate is narrow; no template-to-.po extraction

**Decision:** APPROVED as `BEST-PRACTICE`

**Validation evidence:**

1. **Source code confirmed — `test_i18n_completeness.py:122-133` (`_SKIP_TAGS`):**
   ```python
   _SKIP_TAGS = (
       "script", "style", "head", "meta",
       "input", "br", "hr", "link", "title", "code",
   )
   ```
   `"head"` (L125) and `"title"` (L131) are included in `_SKIP_TAGS`, meaning `test_no_hardcoded_visible_text` strips all `<title>` content before scanning. This makes any untranslated title text invisible to the gate — directly masking I18N-005.

2. **Source code confirmed — `test_i18n_completeness.py:246-265` (`test_extraction_completeness`):**
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
   The test name and docstring claim "extraction completeness," but the implementation only verifies cross-.po consistency (that msgids in one `.po` exist in all others). It does **not** extract `{% trans %}`, `{% blocktrans %}`, `{% plural %}` msgids from templates and verify they exist in the `.po` files.

3. **Script output confirmed — 10 `{% blocktrans %}`/`{% plural %}` blocks not checked by extraction test:**
   ```text
   === {% blocktrans %} / plural blocks NOT checked by extraction test ===
     privacy.html: 4 entries (site_name, code tags)
     ads/dashboard.html: 2 plural entries (counter view/contacts)
     ads/edit.html: 1 entry (Photo counter)
     users/login_issue.html: 1 entry (Login to site_name)
     ads/partials/ad_list.html: 2 entries (Price range, No results)
     Total blocktrans/endtrans: 10
   ```
   Note: `ads/dashboard.html` has plural blocks for view/counter — these are NOT checked by the current gate.

4. **No test for hreflang/plurals/locale-switching:** The test file has no test asserting `hreflang` presence, plural-form correctness, or locale-switch re-render. The i18n spec (i18n-spec.md L268-278) documents `test_extraction_completeness` as verifying "every `{% trans %}` msgid exists in all three `.po` files" — the actual implementation falls short of this documented contract.

5. **Test gap confirmed — grep across test files:** No test function names containing `hreflang`, `plural_form`, or `lang_switch` exist in the test suite.

**Classification rationale:** This is a `BEST-PRACTICE` finding — a test-coverage gap. The gate passes green while multiple i18n defects ship to production undetected. The gate was originally scoped to the 4 Spec_29 T-13 guards and was never extended to cover the phase-14 dimensions (title, hreflang, plurals, switching, template-to-po extraction). The `_SKIP_TAGS` treatment of `title`/`head` as "non-visible" is overly broad — `<title>` content is visible in browser tabs and is a user-facing string.

**Required fix:**
- Remove `"title"` from `_SKIP_TAGS`.
- Add `test_template_extraction_coverage`: extract all `{% trans %}`, `{% blocktrans %}`, `{% plural %}`, `{{ _("…") }}` msgids from templates and assert each exists in all three `.po` files.
- Add `test_hreflang_present` — assert `<link rel="alternate" hreflang>` in rendered HTML.
- Add `test_plural_forms` — assert each `.po` `Plural-Forms` header matches CLDR expectations.
- Add `test_locale_switch_re_render` — assert `?lang=bs` re-renders content in the correct locale.

---

#### I18N-004: [HIGH] — `hreflang`/`rel="alternate"` missing on all pages

**Decision:** APPROVED as `BEST-PRACTICE`

**Validation evidence:**

1. **Grep confirmed — zero matches across all templates:**
   ```text
   $ grep -rn "hreflang" src/backend/templates/
   No files found
   ```
   No template under `src/backend/templates/` emits `<link rel="alternate" hreflang="...">` for the supported language matrix (ru, bs, en).

2. **Base template inspection:** The base template(s) were checked and do not include hreflang tags. The `i18n` context processor is enabled in `base.py:156` (providing `LANGUAGE_CODE` and `LANGUAGE_BIDI`), but no template consumes these for SEO alternate linking.

3. **No context processor for hreflang:** Grep for `hreflang` in `apps/core/context_processors/` returns zero matches. There is no context processor that emits the list of supported locales for use in templates.

4. **Spec alignment:** The phase task §5(f) requires hreflang for the supported matrix; §5(f) evidence states "Missing hreflang on language switches is a finding."

**Classification rationale:** This is a `BEST-PRACTICE` finding — a missing SEO best practice. While not a spec deviation (the i18n spec does not explicitly mandate hreflang), it directly impacts SEO and cross-language canonicalization. The absence of `hreflang` means search engines cannot discover per-language alternate URLs, risking duplicate-content penalties. The fix is well-defined: add hreflang link tags to the base template's `<head>` using `{{ request.path }}?lang=<code>` as the href for each `LanguageLocale` value.

**Required fix:**
- Add hreflang link tags to the base template's `<head>`.
- Use `{{ request.path }}?lang=<code>` as the href for each `LanguageLocale` value.
- Consider a context processor that emits the list of supported locales as the cleanest insertion point.

---

### MEDIUM

#### I18N-005: [MEDIUM] — Untranslated `<title>` string in `ads/dashboard.html`

**Decision:** APPROVED as `SPEC-DEVIATION`

**Validation evidence:**

1. **Source code confirmed — `ads/dashboard.html:12`:**
   ```django
   <title>Dashboard - {{ site_name }}</title>
   ```
   The literal string `"Dashboard"` is not wrapped in `{% trans %}`. The `{{ site_name }}` variable is fine (it's a dynamic value), but the literal text is not extracted.

2. **`.po` file confirmed — "Dashboard" msgid exists in all 3 language files with translations:**
   - `en/LC_MESSAGES/django.po:799-800`: `msgid "Dashboard"` / `msgstr ""` (English msgid, empty msgstr — correct)
   - `ru/LC_MESSAGES/django.po:847-848`: `msgid "Dashboard"` / `msgstr "Панель управления"`
   - `bs/LC_MESSAGES/django.po:844-845`: `msgid "Dashboard"` / `msgstr "Ploča"`

   The msgid IS extracted in all three `.po` files with proper translations. The defect is in the template: the `{% trans %}` tag is simply missing, so Django's template engine never looks up the translation.

3. **Grep confirmed — 15 `<title>` matches, 1 unlocalized:**
   ```text
   $ grep -rn '<title' src/backend/templates/
   15 matches — 14 wrapped in {% trans %} or get_title filter; 1 bare ("Dashboard")
   ```
   All 14 other templates correctly use `{% trans "..." %}` or `{{ ad|get_title:LANGUAGE_CODE }}`. Only `ads/dashboard.html` uses a bare `<title>Dashboard - ...`.

4. **Test gap confirmed — masked by I18N-003:** The completeness gate `_SKIP_TAGS` includes `"title"`, so `test_no_hardcoded_visible_text` strips `<title>` content before scanning. This finding is invisible to CI.

5. **Spec alignment:** Project rule #16 (i18n is part of DoD) requires all user-visible strings wrapped in `{% trans %}`/`{% blocktrans %}`. The `<title>` tag is user-visible (browser tab, bookmarks, SEO).

**Classification rationale:** This is a `SPEC-DEVIATION` — the implementation violates project rule #16 ("Internationalization is part of DoD") by not wrapping a user-visible string in `{% trans %}`. The msgid already exists in all `.po` files with translations; the fix is a one-line template change to wrap the literal. The finding is structural in that it was masked by the test gate (I18N-003), but the underlying defect is a direct spec violation.

**Required fix:**
- Replace `<title>Dashboard - {{ site_name }}</title>` with `<title>{% trans "Dashboard" %} - {{ site_name }}</title>`.

---

#### I18N-006: [MEDIUM] — `<html lang="en">` hardcoded + no `dir` attribute on all templates

**Decision:** APPROVED as `BEST-PRACTICE`

**Validation evidence:**

1. **Grep confirmed — 15 matches for `<html lang="en"`:**
   ```text
   $ grep -rn '<html lang="en"' src/backend/templates/
   15 matches — every page template
   ```
   All 15 page templates hardcode `<html lang="en">` regardless of the active locale (ru, bs, or en).

2. **Grep confirmed — zero matches for `dir=`:**
   ```text
   $ grep -rn 'dir=' src/backend/templates/
   No files found
   ```
   No template emits a `dir` attribute. The `i18n` context processor provides `LANGUAGE_BIDI` (available in all templates via `base.py:156`), but no template consumes it for the root `<html>` element.

3. **Language switcher observation — `language_switcher.html:20`:**
   ```django
   <span class="font-medium">{{ LANGUAGE_CODE|upper }}</span>
   ```
   The switcher displays the current language code but does not bind `<html lang>` to `{{ LANGUAGE_CODE }}`.

4. **Spec alignment:** The phase taxonomy (§5(h)) requires `dir` attribute discipline. Its absence is MEDIUM per the phase severity taxonomy.

5. **Bidi note:** All three supported locales (ru, bs, en) are LTR scripts. The fix is about explicitness and consistency — binding `lang` to `{{ LANGUAGE_CODE }}` and `dir` to `{{ LANGUAGE_BIDI|yesno:"rtl,ltr" }}` — not about adding RTL support for a currently-supported language.

**Classification rationale:** This is a `BEST-PRACTICE` finding — a missing accessibility and HTML-correctness best practice. While not a direct spec violation (the i18n spec does not explicitly mandate `<html lang>` binding), it degrades the user experience: screen readers announce content in the wrong language, and search engines index all pages as English. The fix is low-effort and high-value.

**Required fix:**
- Replace `<html lang="en">` with `<html lang="{{ LANGUAGE_CODE|lower }}" dir="{{ LANGUAGE_BIDI|yesno:"rtl,ltr" }}">` in all 15 templates.
- If templates extend a common base, make this a single base-template edit.

---

### LOW

#### I18N-007: [LOW] — `en` `.po` POT-Creation-Date stale (6 days behind ru/bs)

**Decision:** APPROVED as `BEST-PRACTICE`

**Validation evidence:**

1. **Source code confirmed — `.po` file headers:**
   - `src/backend/locale/en/LC_MESSAGES/django.po:9`:
     ```
     "POT-Creation-Date: 2026-09-04 10:29-0500\n"
     ```
   - `src/backend/locale/ru/LC_MESSAGES/django.po:9`:
     ```
     "POT-Creation-Date: 2026-09-10 04:56-0500\n"
     ```
   - `src/backend/locale/bs/LC_MESSAGES/django.po:9`:
     ```
     "POT-Creation-Date: 2026-09-10 04:56-0500\n"
     ```
   The `en` file's `POT-Creation-Date` is 2026-09-04, while `ru` and `bs` are both 2026-09-10 — a 6-day gap.

2. **Cross-.po consistency confirmed — all 3 files have 329 msgids:**
   ```text
   === PO FILE MSGID COUNTS ===
     bs: 329 msgids
     en: 329 msgids
     ru: 329 msgids
     Total unique: 329
     bs: consistent with all [OK]
     en: consistent with all [OK]
     ru: consistent with all [OK]
   ```
   Despite the staleness, all three files are functionally cross-consistent at 329 msgids each — no missing msgids.

3. **Plural-Forms confirmed correct:**
   - `ru` and `bs`: `nplurals=3; plural=(n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2)` — correct Slavic plural rule
   - `en`: `nplurals=2; plural=(n != 1)` — correct English plural rule

4. **Risk confirmed — masked by I18N-003:** Because `test_extraction_completeness` only checks cross-.po consistency (not `POT-Creation-Date` synchronization), a future extraction run for `ru`/`bs` that adds new msgids but not `en` would pass the gate while `en` falls behind.

5. **Spec alignment:** The pipeline rule (project rule #16) states `makemessages` must be run for all languages, then `compilemessages`. The per-locale invocation pattern described in the findings file (`-l ru -l bs -l en`) does not guarantee atomic extraction across all locales.

**Classification rationale:** This is a `BEST-PRACTICE` finding — a pipeline hygiene gap. The current state is functionally correct (329 msgids in each file, no missing translations), but the staleness represents a latent risk: future non-atomic extractions could silently drift. The fix is low-effort: re-run `makemessages` for all locales in a single invocation and add a `POT-Creation-Date` synchronization assertion to the test gate.

**Required fix:**
- Re-run `makemessages -l ru -l bs -l en` in a single invocation to resynchronize `POT-Creation-Date`.
- Add an assertion in `test_i18n_pipeline.py` that all three `.po` files share the same `POT-Creation-Date`.

---

## Cross-Finding Analysis

### Dependency chains

| Dependent finding | Masking finding | Mechanism |
|---|---|---|
| I18N-005 (untranslated title) | I18N-003 (gate excludes `title`) | `_SKIP_TAGS` includes `"title"` → `test_no_hardcoded_visible_text` strips `<title>` before scanning |
| I18N-007 (stale `en` .po) | I18N-003 (gate only checks cross-.po) | `test_extraction_completeness` checks msgid parity, not `POT-Creation-Date` sync |
| I18N-001 (digest not localized) | I18N-003 (gate doesn't test notifications) | No test in the completeness gate verifies bot notification localization per user language |
| I18N-002 (no `?lang=` normalization) | I18N-003 (gate doesn't test `?lang=`) | No test passes `?lang=en-US` and asserts resolution to `en` |

### Merge candidates

**None** — each finding has a distinct root cause:
- I18N-001: `_format_digest` missing locale/translation-override integration
- I18N-002: `_apply_lang_param` using `_is_valid_language` instead of `from_code()`
- I18N-003: Test gate scoping (`_SKIP_TAGS` + cross-.po-only check)
- I18N-004: Missing hreflang `<link>` tags in base template
- I18N-005: Missing `{% trans %}` on single template line
- I18N-006: Missing `{{ LANGUAGE_CODE }}` binding on `<html>` element
- I18N-007: Non-atomic `.po` extraction causing stale `POT-Creation-Date`

### Conflicting evidence

**None.** All evidence was independently verified from source code. The findings file's grep-based evidence matches the actual source state.

---

## Rollout Analysis

### Risks

| ID | Risk | Backward-compatible? | Test gap (must cover) |
|----|------|----------------------|-----------------------|
| I18N-001 | Low | Yes — adding `translation.override(locale)` to digest only affects localized output; English fallback remains for users with no `telegram_language` | No test asserts daily digest content is localized per user language |
| I18N-002 | Low | Yes — normalizing `en-US`→`en` is strictly more permissive; valid `ru`/`bs`/`en` codes still work | No test passes `?lang=en-US` and asserts resolution to `en` |
| I18N-003 | Med | Yes — adding new test assertions to the gate is test-only, no production code change | Gate lacks template-to-po extraction, title, hreflang, plural, switch tests |
| I18N-004 | Low | Yes — adding `<link rel="alternate">` tags is additive to `<head>` | No test asserts `<link rel="alternate" hreflang>` in rendered HTML |
| I18N-005 | Low | Yes — wrapping "Dashboard" in `{% trans %}` produces same English output for `en` users | Gate excludes `title` from scanning — would not catch regression |
| I18N-006 | Low | Yes — `<html lang="{{ LANGUAGE_CODE }}">` renders `lang="en"` for English users (same as current) | No test asserts `<html lang>` matches active locale or `dir` present |
| I18N-007 | Low | Yes — re-running `makemessages` regenerates `.po` files without behavioral change | No check on `POT-Creation-Date` synchronization across locales |

### Rollout ordering recommendation

1. **I18N-003** (gate hardening) — do this first. Remove `"title"` from `_SKIP_TAGS` so the gate surfaces I18N-005. Add `test_template_extraction_coverage`, `test_hreflang_present`, `test_plural_forms`, `test_locale_switch_re_render`, and the `POT-Creation-Date` sync assertion. This ensures all subsequent fixes are covered by CI.
2. **I18N-005** (1-line template fix) — trivial, but must come after I18N-003 so the gate catches regressions.
3. **I18N-002** (middleware normalization) — medium risk; add a test first (`?lang=en-US` → `en`), then change `_apply_lang_param`.
4. **I18N-001** (digest localization) — P0; mirror the `immediate_alerts.py` pattern.
5. **I18N-004** (hreflang) — P1; add to base template `<head>`.
6. **I18N-006** (html lang/dir) — P2; single base-template edit if templates share a base.
7. **I18N-007** (re-extract) — P2; re-run `makemessages` after all code changes are stable.

### Dependency ordering

- I18N-003 must be resolved before I18N-005 and I18N-007 are detectable by CI.
- I18N-001 depends on the existing `LanguageLocale` enum and `ad.get_title()` method (both already in place).
- I18N-002 depends on the existing `LanguageLocale.from_code()` method (already in place, currently unused from middleware).
- I18N-004 and I18N-006 are independent base-template changes.

---

## Warnings

### Architectural risks

- **I18N-001 root cause is architectural:** `_format_digest` and `build_alert_message` (in `immediate_alerts.py`) are independent implementations that should share a common message-building abstraction. Without extraction, future notification channels will repeat the same mistake. Consider extracting a shared `NotificationMessageBuilder` service that both paths call.

### Maintainability / evolvability risks

- **I18N-003 gate scope drift:** The gate was originally scoped to Spec_29 T-13 guards and was never extended for phase-14 i18n dimensions. A process gap exists: new i18n requirements in the spec are not automatically mapped to test coverage. Recommend adding a spec-to-test mapping table in `test_i18n_completeness.py` or its module docstring.
- **I18N-007 latent drift:** Non-atomic extraction is a latent risk. Without a `POT-Creation-Date` sync assertion, any future partial re-extraction will silently fail.

### Rollout risks

- **I18N-002 fallback reconciliation:** The spec says fallback to `bs`, but the current code falls back to `settings.LANGUAGE_CODE` (`ru`). Changing the fallback from `ru` to `bs` is a behavioral change for unsupported `?lang=` values — this should be validated in staging before production rollout.
- **I18N-006 template duplication:** If 15 templates do not share a common base, the `lang`/`dir` fix requires 15 edits. Recommend consolidating into a single base template to avoid future drift.

### Dependency risks

- **I18N-001 depends on `ad.get_title()` and `ad.city.get_name()`** which must be correct for all three locales. The confirmed-correct `immediate_alerts.py` path already uses these — the risk is low.

---

## Required Fixes

### Mandatory (all 7 findings)

| ID | Fix | File(s) | Effort | Priority |
|----|-----|---------|--------|----------|
| I18N-001 | Add `locale` param to `_format_digest`; wrap in `translation.override(locale)`; use `gettext()` for hardcoded strings; use `ad.get_title(locale)[:50]` | `send_alerts.py` | S | P0 |
| I18N-002 | Replace `_is_valid_language(lang)` with `LanguageLocale.from_code(lang, fallback=None)`; use `from_code()` in `_parse_accept_language` too; reconcile fallback to `bs` per spec | `language.py` | S | P1 |
| I18N-003 | Remove `"title"` from `_SKIP_TAGS`; add `test_template_extraction_coverage`, `test_hreflang_present`, `test_plural_forms`, `test_locale_switch_re_render` | `test_i18n_completeness.py` | M | P1 |
| I18N-004 | Add `<link rel="alternate" hreflang>` tags to base template `<head>` | base template | M | P1 |
| I18N-005 | Wrap "Dashboard" in `{% trans %}`: `<title>{% trans "Dashboard" %} - {{ site_name }}</title>` | `ads/dashboard.html:12` | T | P2 |
| I18N-006 | Replace `<html lang="en">` with `<html lang="{{ LANGUAGE_CODE|lower }}" dir="{{ LANGUAGE_BIDI|yesno:"rtl,ltr" }}">` in all 15 templates | all page templates | S | P2 |
| I18N-007 | Re-run `makemessages` for all locales in single invocation; add `POT-Creation-Date` sync assertion | `test_i18n_pipeline.py` | T | P2 |

### Advisory Recommendations

1. **Extract shared message builder:** Both `immediate_alerts.py:build_alert_message` and `send_alerts.py:_format_digest` should delegate to a shared `NotificationMessageBuilder` service to prevent future duplication of the per-user localization pattern.

2. **Consolidate `<html>` element:** If the 15 page templates do not share a common base, extract the `<html lang>` / `dir` binding into a base template to prevent future drift across I18N-006's scope.

3. **Spec-to-test mapping:** Add a mapping table in `test_i18n_completeness.py` docstring linking each i18n spec requirement (i18n-spec.md) to the test(s) that cover it, so future spec additions automatically surface as coverage gaps.

4. **Per-user language in web rendering:** While not a current finding (the web path correctly uses `request.LANGUAGE_CODE` via middleware), the architecture could benefit from a `get_effective_locale()` helper that both the bot and web paths can share, reducing the surface area for I18N-001-style defects.

---

## Appendix — Validation Source Evidence

All file citations below were read directly from the repository during validation:

| File | Lines read | Findings supported |
|------|-----------|-------------------|
| `src/backend/apps/search/management/commands/send_alerts.py` | 147-197 (full) | I18N-001 |
| `src/backend/apps/search/services/immediate_alerts.py` | 1-30, 155-180 | I18N-001 (contrast) |
| `src/backend/apps/core/middleware/language.py` | 1-150 (full) | I18N-002 |
| `src/backend/apps/core/enums.py` | 190-229 | I18N-002 (from_code definition) |
| `src/backend/apps/ads/tests/test_i18n_completeness.py` | 122-133, 246-265 | I18N-003 |
| `src/backend/templates/ads/dashboard.html` | 1-15 | I18N-005, I18N-006 |
| `src/backend/templates/components/language_switcher.html` | 1-144 (full) | I18N-006 (lang display) |
| `src/backend/locale/en/LC_MESSAGES/django.po` | 1-18 (header), 799-800 | I18N-005 (Dashboard msgid), I18N-007 |
| `src/backend/locale/ru/LC_MESSAGES/django.po` | 1-18 (header), 847-848 | I18N-005 (Dashboard msgid), I18N-007 |
| `src/backend/locale/bs/LC_MESSAGES/django.po` | 1-18 (header), 844-845 | I18N-005 (Dashboard msgid), I18N-007 |
| `src/backend/config/settings/base.py` | 152-163 | I18N-006 (context processor confirmation) |
| `docs/01-spec/i18n-spec.md` | 63-64, 268-278 | I18N-002 (spec discrepancy), I18N-003 (extraction test doc) |
| `.ai/audit/14-i18n/findings.md` | 1-448 (full) | All (source findings) |
