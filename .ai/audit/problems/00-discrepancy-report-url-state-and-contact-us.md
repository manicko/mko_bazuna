---
id: discrepancy-report-17-18
title: Discrepancy Report — Specs 17 & 18 vs. Current Implementation
domain: audit
type: discrepancy-report
status: draft
created: 2026-09-07
---

# Discrepancy Report — Specs 17 (URL State Preservation) & 18 (Contact-Us)

## Overview

This report captures discrepancies between the signed-off implementation specs (`.ai/plans/done/17_url-state-preservation_spec_DONE.md`, `.ai/plans/done/18_contact-us_spec.md`) and the current codebase, as verified by researcher agents. It also records contradictions between prior audit findings (Block 1: `.ai/audit/11-bot-username-migration/findings.md`; Block B: `block-b-rtl-obfuscation.md`) and the implementation-verification report.

## Scope

- **Spec 17 scope:** All 8 confirmed requirements (CR-1–CR-8), 6 development tasks, PO decisions Q1–Q4.
- **Spec 18 scope:** All 11 confirmed requirements (CR-1–CR-11), 10 development tasks, PO decisions Q1–Q8.
- **Audit findings scope:** F-BU-001 through F-BU-007 (Block 1), F-BB-001 through F-BB-006 (Block B).

---

## Discrepancy 1 — CR-11 / Task 8: `js_verified` gate not enforced by the `telegram_deep_link` tag

| Field | Value |
|---|---|
| **Spec requirement** | CR-11: "If [js cookie] is absent, the `telegram_deep_link` template tag emits `href="#"` with no `data-*` attribute even at click time (graceful degradation)." |
| **Implementation finding** | **Partially implemented.** The JS-execution middleware (`apps/core/middleware/js_check.py`), the `js=true` cookie setter (`footer.html`), and the `js_verified` context processor all exist and are registered. However, the `telegram_deep_link` template tag (`telegram_tags.py`) **deliberately does not gate** on `js_verified` — it always emits the full obfuscated `data-bot-encoded` + `data-start` attributes regardless of the cookie state. |
| **Source of truth** | `src/backend/apps/core/templatetags/telegram_tags.py` L24-28, L119-123 (docstring: "The tag always renders the full interactive link"). |
| **Test coverage** | Tests **assert the deviation**: `test_footer_contact_link.py` L139-160 (`test_contact_link_remains_visible_when_js_not_verified`) and `test_rtl_obfuscation.py` L188-203 confirm that with `js_verified=False`, `data-bot-encoded` and `data-start` are still emitted. |
| **Assessment** | **Design deviation** (not an oversight). The implementer chose base64-encoding + click-time URL assembly + rate limiting as the primary defense, making the cookie-gate non-functional in the tag. The intent of CR-11 (prove JS execution to defeat non-JS scrapers) is only partially achieved (cookie is set + read) but the graceful-degradation behavior is **not implemented**. |
| **Documentation impact** | The new `docs/01-spec/contact-us.md` doc will note this deviation and document the actual behavior (base64 + click-to-reveal + rate limiting as the primary defense; the `js=true` cookie exists as defense-in-depth but does not gate the tag's output). |

---

## Discrepancy 2 — `.bot-username-rtl` CSS rule: conflicting verification reports

| Field | Value |
|---|---|
| **Spec requirement** | Spec 18 Task 3: `.bot-username-rtl { direction: rtl; unicode-bidi: bidi-override; }` must exist in the stylesheet to flip reversed display text back to readable. |
| **Implementation-report claim** | The Step-2 implementation researcher states: "`.bot-username-rtl` CSS class exists at `input.css` L12-14, compiled into `output.css`." |
| **Audit-finding claim** | Audit F-BB-001 (`block-b-rtl-obfuscation.md` L54-93) and the Step-3 doc-impact researcher both state: `grep -l "bot-username-rtl" input.css` → no match; `grep -l "bot-username-rtl" output.css` → no match (0 hits). Input.css contains only 4 lines (`@import` + `@source`), no custom rules. |
| **Assessment** | **Unresolved contradiction.** The two sources disagree on whether the CSS rule exists. The audit finding is more detailed (it quotes the exact 4 lines of `input.css` and cites a literal grep), but the implementation researcher claims to have found it at specific line numbers. This needs manual verification. |
| **Documentation impact** | Documented in the discrepancy report only. The `docs/01-spec/contact-us.md` doc will describe the intended CSS technique (CSS `direction: rtl` + `unicode-bidi: bidi-override` for display-text reversal) without asserting it exists until verified. |

---

## Discrepancy 3 — Audit F-BU-001/F-BU-002/F-BU-004 vs. implementation completion

| Field | Value |
|---|---|
| **Audit claims (Block 1)** | F-BU-001: `privacy_policy()`, `ad_detail()`, `login_issue()` still read `settings.BOT_USERNAME` instead of `get_bot_username()`. F-BU-002: `site_config()` context processor returns `site_name` only, no `bot_username`. F-BU-004: `telegram_deep_link` template tag "referenced but not implemented" — no `telegram_tags.py` exists. F-BB-002: `privacy.html` still serves cleartext `{{ bot_username }}` at L30/33/111/148/151. |
| **Implementation findings** | The Step-2 implementation researcher confirms ALL of these are **resolved**: (1) `telegram_tags.py` exists with `telegram_deep_link`, `TelegramDeepLinkCommand` StrEnum, `rtl_obfuscate` filter. (2) All consumer views use `get_bot_username()` instead of `settings.BOT_USERNAME`. (3) `header_context` context processor exposes `bot_username` sourced from `get_bot_username()`. (4) `privacy.html` uses `{% telegram_deep_link %}` tags and `|rtl_obfuscate` for display text. |
| **Assessment** | The audit findings (Block 1, Block B) were written **before** the consumer-migration implementation was completed. The implementation has since resolved all F-BU-001, F-BU-002, F-BU-004, F-BB-002 items. The audit's `validated: no` status explains why these findings describe a stale state. |
| **Documentation impact** | No doc update needed — the implementation researcher is the source of truth for the current state. The docs will reflect the implemented (not pre-implementation) behavior. |

---

## Discrepancy 4 — `rtl_obfuscate` filter technique: RTL marks vs. string reversal

| Field | Value |
|---|---|
| **Spec requirement** | Spec 18 §5.1 / Task 3: "Reverse the string, flipped visually by CSS `direction: rtl; unicode-bidi: bidi-override`." |
| **Implementation finding** | The Step-2 researcher states: "`rtl_obfuscate` filter reverses + inserts RLM marks" (`telegram_tags.py` L179-209). |
| **Audit finding** | F-BB-003 (`block-b-rtl-obfuscation.md` L156-203) states: the filter **inserts U+200F RTL marks between characters** (`"\u200f".join(value)`), it does **not** reverse the string. This **diverges** from the spec's declared reversal + CSS technique. |
| **Assessment** | **Contradiction between sources.** If the implementation researcher is correct (filter reverses + inserts RLM), the technique aligns with the spec and pairs correctly with the `bot-username-rtl` CSS class. If the audit is correct (filter only inserts RTL marks, no reversal), the technique diverges from the spec and the CSS class pairing would not work as intended. |
| **Documentation impact** | Documented here. Until the code is manually verified, the `docs/01-spec/contact-us.md` doc will describe the **spec-intended** technique (string reversal paired with `direction: rtl`), and note the audit's finding that the current implementation may use a different (RTL-mark insertion) approach. |

---

## Discrepancy 5 — `header_context()` docstring vs. return dict (F-BU-003)

| Field | Value |
|---|---|
| **Audit finding** | F-BU-003: `header_context()` docstring (L45-48) advertises `bot_username` as a context variable "resolved via the `telegram_deep_link` template tag using the `get_bot_username()` service", but the actual return dict (L93-108) contains no `bot_username` key — it only returns `root_categories`, `preferred_city_display`, `cities`, `favorites_count`, `catalog_js_labels`. |
| **Implementation finding** | The Step-2 researcher states: "Context processor exposes `bot_username` sourced from `get_bot_username()` (`context_processors.py` L93)." |
| **Assessment** | **Contradiction.** The audit says the return dict has no `bot_username` key; the implementation researcher says the context processor exposes it. This needs verification. If the context processor DOES inject `bot_username`, then templates could receive it as a raw context variable (violating CR-2), but the researcher also confirmed no template references `settings.BOT_USERNAME`. |
| **Documentation impact** | The `docs/01-spec/contact-us.md` doc will describe the **intended** architecture: templates resolve the bot username exclusively via the `telegram_deep_link` template tag, never via a raw `{{ bot_username }}` context variable. |

---

## Spec 17 — No discrepancies found

Spec 17 (URL State Preservation) is **fully implemented** with no deviations. All 8 confirmed requirements (CR-1–CR-8) and all 6 development tasks are verified present in the source. The only minor deviation (Task 5 placement — separate `htmx:afterSwap` handler in `header_catalog.html` instead of extending the one in `language_switcher.html`) is functionally equivalent and permitted by the spec text.

## Summary Table

| # | Discrepancy | Severity | Status |
|---|---|---|---|
| 1 | CR-11: `js_verified` gate not enforced by `telegram_deep_link` tag | Medium (design deviation) | Documented deviation — tests assert the behavior |
| 2 | `.bot-username-rtl` CSS rule: conflicting verification (exists vs. absent) | High (unresolved) | Requires manual verification |
| 3 | Audit F-BU-001/002/004/F-BB-002: stale findings vs. completed implementation | Low (audit is stale) | Resolved — implementation is current |
| 4 | `rtl_obfuscate` technique: reversal vs. RTL-mark insertion | Medium (unresolved) | Requires manual verification |
| 5 | `header_context()` docstring vs. return dict | Medium (unresolved) | Requires manual verification |
