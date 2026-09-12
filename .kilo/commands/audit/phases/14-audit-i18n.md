# 14 — Internationalization & Localization Correctness

> Audit phase. LLM-auditor instruction. Architecture-agnostic: described via
> ARCHITECTURAL LAYERS, ZONES OF RESPONSIBILITY, KEY RISKS, GOALS. NOT tied to
> specific files, modules, or functions. Must stay valid if the architecture changes.
>
> **Output mode:** `problems-only` — report only findings; do not narrate a clean bill of health.

## 1. Goal

Verify that runtime locale resolution, fallback-chain semantics, per-user
language binding, DB-based i18n (JSONB fields + locale cache keys), and
completeness beyond the test gate are all correct: only the selected language
is rendered, fallback chains resolve as documented (not raw `.name` bypasses),
per-user language propagates to bot-rendered notifications, the test gate is
comprehensive (title tags, hreflang, plural forms, locale switching, inline-JS),
and RTL/Bidi readiness is maintained for the supported scripts.

## 2. System Under Audit (layers & zones)

| Zone | Concern |
|------|---------|
| **Runtime Locale Resolution** | A request-time middleware resolves the active language from priority order (query param → cookie → Accept-Language → default) with language normalization (`en-US`→`en`, fallback→`bs`/`ru`) and persists the choice in a long-TTL cookie. |
| **Fallback-Chain Resolution** | Name/title/description resolution on Category, City, and LookupItem follows a `locale → ru → name` fallback chain via the documented accessors — never a raw `.name` bypass. |
| **Per-User Language Binding** | The identity's stored Telegram language is propagated to bot-rendered notification content (alert messages, saved-search notifications). |
| **DB-Based i18n** | Catalog names use a JSONB `name_i18n` field populated per language; the submenu cache key carries a `<locale>` segment so locale bleed cannot occur. |
| **Completeness Coverage** | The CI completeness test gate (no-hardcoded-visible-text, extraction completeness, no-empty-msgstr, mo-compiled) is comprehensive — covering title tags, hreflang, plural-form rules, locale switching correctness, and inline-JS i18n holes. |
| **Script & Direction** | The supported scripts (Russian Cyrillic, Bosnian Latin + Cyrillic) are rendered with correct `dir` attribute discipline and text-direction handling. |
| **Test-Gate Exemptions** | DB-based i18n exemptions (e.g. `feature_tag.html` via the lookup-name accessor) are intentional and documented — not gaps the gate silently misses. |

## 3. Prerequisites

- Services runnable and seeded across all content languages (ru, bs, en).
- Ability to issue requests with varying Accept-Language, `lang` cookie, and `lang` query param.
- Bots/identities with per-user Telegram language configured.
- The external translation service mocked (no real calls in tests).
- Ability to inspect rendered HTML for title tags, hreflang, `dir`, and inline JS.
- Ability to run the completeness test gate and inspect `.po`/`.mo` artifacts.

## 4. Runtime Verification (mandatory)

Execute, then capture evidence (rendered HTML, HTTP headers, cache keys, notification text):

1. **Locale priority** — request the same page with `lang` param, `lang` cookie, differing `Accept-Language`, and none → assert the priority order resolves correctly; assert `en-US` normalizes to `en` and the fallback default applies.
2. **Name fallback** — render a Category/City/LookupItem with a missing `name_i18n` locale entry → assert it falls back through the documented chain (not a raw `.name` bypass); assert autocomplete uses the accessor, not `.name`.
3. **Per-user bot language** — trigger an alert/saved-search notification for a `bs`-language identity → assert the notification text renders in `bs`, not the site default.
4. **Cache locale segment** — render a submenu in `ru`, then in `bs` → assert distinct cache keys per locale; assert NO stale-language serve.
5. **Completeness gate breadth** — run the gate → confirm it does NOT cover title tags, hreflang, plural forms, or locale switching (documented gap); confirm it passes with holes the runtime audit would catch.
6. **Exemption surface** — confirm which templates/accessors are exempt from the gate and that the exhaustion is intentional.
7. **Script/direction** — render Bosnian content in both Latin and Cyrillic contexts → assert `dir` attribute discipline; assert no mojibake in mixed-script pages.

## 5. Audit Dimensions (checks + evidence)

### (a) Locale-priority resolution & normalization — CRITICAL
The active language resolves by the documented priority chain and normalizes variants; the cookie persists with a long TTL.
- Evidence: `lang` param wins over cookie wins over Accept-Language wins over default; `en-US`→`en`; fallback default applied; `lang` cookie TTL set to ~1 year. A middleware ordering that lets cookie override param, or no normalization, is a finding.

### (b) Fallback-chain correctness (no raw `.name` bypass) — CRITICAL
Category/City/LookupItem names resolve via the documented `locale → ru → name` chain through the accessors, never a raw `.name` read.
- Evidence: accessor-based resolution on rendered pages and in autocomplete; the documented bug where autocomplete calls raw `.name` without `LANGUAGE_CODE` is a finding.

### (c) Per-user language in bot notifications — HIGH
Bot-rendered alerts and saved-search notifications honor the identity's stored Telegram language.
- Evidence: notification content rendered in the user's language, not the site default; the bot notification path reads the user's language field.

### (d) DB-based i18n & cache locale segmentation — CRITICAL
`name_i18n` JSONB population is correct; the submenu cache key carries a `<locale>` segment so a Russian-rendered entry is never served to a Bosnian visitor.
- Evidence: cache keys include a `<locale>` segment per the i18n spec; populated `name_i18n` rows; the documented bug where the submenu cache key omits language is a finding.

### (e) Completeness-gate breadth beyond the CI test — HIGH
The completeness gate is comprehensive: it covers title tags, hreflang, plural-form rules, locale switching, and inline-JS i18n holes (not only no-hardcoded-text / extraction / no-empty-msgstr / mo-compiled).
- Evidence: the gate test file (narrow, 4 tests) does NOT exercise title tags, hreflang, plurals, or locale switching; a comprehensive gate is a finding only if the runtime audit surfaces holes. Documenting the gap as a known incompleteness is itself a finding.

### (f) Title tags, hreflang, plurals — HIGH
Page `<title>` carries the localized string; `hreflang` is emitted for the supported language matrix; plural-form rules select the correct form per language.
- Evidence: rendered `<title>` per language; `<link rel="alternate" hreflang="...">` per language (excluding self-referential `x-default`); plural form selection correct for each of ru/bs/en. Missing hreflang on language switches is a finding.

### (g) Locale switching & inline-JS i18n — MEDIUM
Locale switchers update the cookie/param and re-render correctly; inline JavaScript that emits user-visible strings is wrapped in `{% blocktrans %}`/gettext and re-translated on switch.
- Evidence: switch link sets the right cookie and the next render uses the new language; no inline JS string bypasses gettext.

### (h) RTL / Bidi direction — MEDIUM
The `dir` attribute is set correctly per language/script context; mixed-script (Latin + Cyrillic Bosnian) renders without mojibake.
- Evidence: `dir="ltr"`/`dir="rtl"` discipline on `html`/container elements; mixed-script pages tokenize correctly. Missing `dir` discipline is a finding.

### (i) Test-gate exemptions — LOW
DB-based i18n exemptions (e.g. `feature_tag.html` via the lookup-name accessor) are intentional and documented, not silently missed.
- Evidence: exemption documented in the project rules; the exempt accessor is the only path for that template's dynamic text. An undocumented exemption is a finding.

## 6. Cross-Cutting (owned here, not duplicated)

This phase owns **runtime i18n/localization correctness** and the **completeness of the i18n test gate**. It explicitly does NOT audit:

- **Phase 06 (PII consent semantics)** — locale selection. Phase 06 owns consent state; this phase owns language resolution and fallback semantics.
- **Phase 08 (per-language FTS search-vector mechanism)** — how the FTS index is built/maintained per language. Phase 08 owns the search-vector mechanism; this phase audits runtime locale resolution and fallback *correctness* (not the search-index mechanism).
- **Phase 09 dimension (c) — translation client egress (timeout, circuit-breaker, no PII sent)** — translation-client *resilience* and PII-to-third-party. Phase 09(c) owns the translation client failure handling; this phase audits *locale/fallback correctness* of the rendered content and per-user language binding.
- **Phase 10 (code-quality / no-hardcoded-text test gate)** — source-level i18n hygiene. Phase 10 owns the no-hardcoded-text rule and module quality; this phase audits runtime locale behavior and the *comprehensiveness* of the completeness gate.
- **Phase 11 (test-coverage for i18n completeness gate)** — test coverage of the completeness gate itself. Phase 11 verifies the test safety net; this phase audits *runtime i18n correctness* and whether the gate is *comprehensive*. (Phase 11 confirms the gate exists and passes; this phase confirms the gate is comprehensive.)

## 7. Edge Cases

- Category/City name missing for the active locale, present in `ru` → must fall through `ru`, not return empty/raw `.name`.
- Autocomplete input using raw `.name` without `LANGUAGE_CODE` → renders in the wrong/default language (documented problem 09).
- `en-US` variant sent in Accept-Language → must normalize to `en`, not fail to match.
- Identity with no stored Telegram language → notification falls back to the site default without error.
- Submenu cache key omits locale → Russian submenu served to a Bosnian visitor (documented problem 09).
- Locale switcher sets the cookie but the next render still uses the old language → middleware ordering or cookie-visibility bug.
- Inline JS string not wrapped in gettext → ships in the site default language after a switch.
- Mixed Latin+Cyrillic Bosnian content → `dir="ltr"` discipline must not break bidirectional runs.
- `feature_tag.html` exempt from the completeness gate → must be the *only* exemption and must be documented.

## 8. Severity Taxonomy

- **CRITICAL**
  - Raw `.name` bypass for Category/City/LookupItem rendering or autocomplete (documented problem 09).
  - Submenu cache key omits locale → locale bleed (Russian served to Bosnian) (documented problem 09).
  - Per-user bot language not propagated to notifications.
  - `name_i18n` population absent or incorrect for a supported language.
- **HIGH**
  - Locale priority chain broken (cookie overrides `lang` param; no normalization).
  - Title tags not localized per language.
  - `hreflang` missing or incorrect for the supported matrix.
  - Plural-form rules wrong per language (ru/bs/en).
  - Completeness gate narrow (no title-tag/hreflang/plural/locale-switch coverage) despite runtime holes.
- **MEDIUM**
  - Locale switcher does not re-render in the new language.
  - Inline JS strings bypass gettext.
  - RTL/Bidi `dir` discipline missing on mixed-script pages.
- **LOW**
  - `lang` cookie TTL not the documented ~1 year.
  - Undocumented exemption from the completeness gate (beyond the intentional `feature_tag.html` case).

## 9. Recommended Sequence

1. Discovery — map the locale middleware, fallback accessors, per-user language field, DB-based i18n + cache keys, completeness gate, title/hreflang/plural handling, and exemptions.
2. Runtime verification (§4).
3. Per-dimension checks (§5 a–i).
4. Cross-cutting (§6) and edge cases (§7).
5. Consolidate findings.

## 10. Finding Prefix

Use `I18N-` for all findings in this phase.

## 11. Reporting

- `problems-only: true`.
- Each finding: severity, zone, evidence (rendered HTML / HTTP header / cache key / notification text / grep hit), and recommendation with effort/priority.
- Append incrementally (≤100 lines per write) to the phase findings file per `docs/99-agent/rules.md`.
