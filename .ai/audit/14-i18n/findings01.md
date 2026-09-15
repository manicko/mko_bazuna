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
