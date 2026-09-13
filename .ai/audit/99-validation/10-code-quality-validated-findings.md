---
# Report metadata — filled once per phase report.
phase: "99"
phase_name: "Validation"
date: "2026-09-12"
auditor: "Executor (subagent)"
validator: "Validator (kilo/poolside/laguna-s-2.1:free)"  # Phase 99 only
mode: "problems-only"
# Correct prefix per phase: 01-ENT, 02-CFG, 03-DB, 04-AUT, 05-AD, 06-PII, 07-MED, 08-SRH, 09-EXT, 10-QLT, 11-TST, 12-OPS, 13-PERF, 14-I18N
# Validated-report findings use a "V" prefix to namespace validator-added notes/new findings.
id_prefix: "QLT"
# report_status = lifecycle of the report document (draft → validated)
# per-finding Status (in Findings Summary + field table below) = lifecycle of the individual finding (Open → Validated/Rejected/Merged/Reclassified/Deferred)
report_status: "validated"  # Phase 99 sets to "validated"
severity_taxonomy: ".kilo/commands/audit/phases/10-audit-code-quality.md#severity-taxonomy"  # pointer to phase rubric, NOT hardcoded
# Structural enforcement (replaces the buried ID-preservation comment):
---

# Audit Findings — Code Quality (VALIDATED)

## Executive Summary

All seven findings from Phase 10 were inspected line-by-line against the current
codebase and re-checked with `ruff check --select G004`, `basedpyright`, `ast.parse`,
and targeted source reads. Every finding is **technically correct and currently
applicable**, so all are **VALIDATED** (none rejected or reclassified). The bot's
two HIGH-severity issues (QLT-001 god-module, QLT-002 callback-token drift) are
genuine and the web-side MEDIUM issues (QLT-003 fat view, QLT-004 unvalidated
edit POST, QLT-005 bot i18n gap) are confirmed real.

However, validation surfaced three pieces of evidence nuance that narrow the
findings' blast radius and one genuine gap that must accompany a QLT-005 fix:

1. **QLT-002 citation over-reach:** the file list cites `language.py` and
   `alerts.py` for the `lang:` / `unsub_on:` tokens, but those tokens are **already
   module-level constants** (`LANG_CALLBACK_PREFIX`, `UNSUB_ON_PREFIX`) reused
   consistently at their filter+builder sites; `unsub:` is an imported constant
   (`UNSUB_CALLBACK_PREFIX` from `apps.search.services.immediate_alerts`). The
   *genuine* drift risk is confined to the ad_create.py tokens and `login.py`'s
   `contact_us` literal — so the finding stands, but its scope is narrower than
   stated.
2. **QLT-006 evidence inaccuracy:** the audit reports "12 hits in edit.py" and
   lists `listings.py` among affected files. The verified `ruff --select G004`
   run shows **8** hits in `edit.py` and **0** in `listings.py` (total 49 is
   correct). The file list should read `ads/views/{edit,delete}.py`.
3. **QLT-001 helper count:** 14 `sync_to_async` ORM helpers exist (not "15+"); 3 of
   them (`get_resolved_*`) already delegate to the shared `CategoryLookupResolver`,
   so 11 simple lookups are the truly-inline duplicates.

Additionally, a **prerequisite gap** was found that the QLT-005 recommendation
does **not** mention: the bot process never calls `translation.activate()`, so
wrapping bot strings in `_()` alone would not render per-user locales. This is
filed as new finding **FQ-001** (dependency of QLT-005).

No finding contradicts Phases 01-09 audit evidence; QLT-005 corroborates the
bot i18n gap and QLT-003's "search re-implements parallel filter logic" is
confirmed against `search.py`.

## Scope & Methodology

**Scope (re-validated):** `src/backend/` (Django apps) and `src/telegram_bot/`
(handlers, schemas, services, middlewares, lifecycle, main). Entry points and
settings reviewed. CI workflow absent in workspace (`.github/` missing) — the
`makemigrations --check` gate could not be verified from source; migration
discipline re-checked via git tree + raw-SQL inspection (R-10 in the source
audit PASS).

### Runtime Verification (validator)

| V# | Check | Method | Result |
|----|-------|--------|--------|
| V-01 | `ruff check src/backend src/telegram_bot` | `uv run ruff check` | PASS (clean) |
| V-02 | `basedpyright src/backend src/telegram_bot` | `uv run basedpyright` | 1 pre-existing error in `test_priority_service.py:500` (django-stubs gap, tracked as AD-008 Phase 05); all production `Any` is framework signatures / test fixtures → PASS |
| V-03 | No `print()` in production code | `ruff`/`grep` | PASS (1 hit is a subprocess-test string, not code) |
| V-04 | StrEnum for fixed values | `grep` + source read | QLT-002 confirmed: ad_create.py tokens + `login.py:61` `contact_us` are raw literals |
| V-05 | Module loggers, no `print` | source read of handlers | PASS (style drift → QLT-006) |
| V-06 | Handlers delegate; no ORM in presentation | source read of `ad_create.py`, `contact.py`, `listings.py`, `edit.py` | FAIL → QLT-001, QLT-003, QLT-004 (contact.py is the correct contrast) |
| V-07 | Module size | `Measure-Object -Line` + `ast` | FAIL → QLT-001 (1311), QLT-003 (508) |
| V-08 | Pydantic at bot input + web POST | source read of payloads + `SubmitAdInput`/`ConsentSubmission` | PARTIAL FAIL → QLT-004 (edit POST bypasses DTO) |
| V-09 | English-only comments/logs/errors | `grep` cyrillic in `logger.*` + comments | PASS (minor → QLT-007) |
| V-10 | Migrations for schema changes | git tree + raw-SQL grep | PASS |
| V-11 | Shared rules not duplicated | source read of `core/services/contact.py` | PASS |
| V-12 | G004 enabled in ruff config | read `[tool.ruff.lint] select` (pyproject.toml:118-124) | FAIL → only E,F,I,B,UP selected; G absent → QLT-006 unguarded |
| V-13 | `except ValueError, Exception:` semantics | `ast.parse` on line 600 | Parses as `except (ValueError, Exception):` (implicit tuple); redundant since Exception ⊃ ValueError → QLT-001 claim accurate |
| V-14 | Bot language activation | `grep` `translation.activate` across `src/telegram_bot` | NONE in non-test bot code (only web middleware) → FQ-001 |

**Tools used:** `ruff check --select G004`, `uv run basedpyright`, `ast.parse`,
`grep`/`Select-String` across `src/`, `Measure-Object -Line`, `git log`,
source inspection of handler/view/service files, schema read of `core/enums.py`.

## Findings Summary

| ID | Title | Severity | Type | Status | Category |
|----|-------|----------|------|--------|----------|
| QLT-001 | Bot `ad_create.py` (1311 lines) god-module: 14 sync_to_async ORM helpers + business logic in handler | HIGH | BEST-PRACTICE | Validated | Separation of Concerns / SRP |
| QLT-002 | Callback-data tokens & locale list are raw string literals; no StrEnum source of truth (drift breaks routing) | HIGH | BEST-PRACTICE | Validated (narrower scope) | StrEnum / Constants |
| QLT-003 | Web `listings.py` (508 lines) fat view embeds filter/sort/pagination inline | MEDIUM | BEST-PRACTICE | Validated | Separation of Concerns / SRP |
| QLT-004 | Web edit POST text/price-edit path bypasses Pydantic validation (sibling reactivation validates) | MEDIUM | BEST-PRACTICE | Validated (with architectural note) | Boundary validation / Pydantic |
| QLT-005 | Bot i18n inconsistent: unwrapped strings; Russian msgids; template-only gate | MEDIUM | BEST-PRACTICE | Validated (+ FQ-001 prerequisite) | i18n / Conventions |
| QLT-006 | Pervasive f-string logging (49 sites) — G004 not enforced by ruff | LOW | BEST-PRACTICE | Validated (evidence corrected) | Logging conventions |
| QLT-007 | Bare `dict`/`list` annotations in bot handler; one Cyrillic comment | LOW | BEST-PRACTICE | Validated (count nuance) | Type safety / English-only |
| FQ-001 | Bot wraps strings in `_()` but never activates per-user locale (`translation.activate`) | MEDIUM | SPEC-DEVIATION | Validated (new) | i18n / Architecture |

## Findings by Severity

### HIGH

#### QLT-001: [HIGH] — Bot `ad_create.py` (1311 lines) is a god-module embedding data-access + business logic in the handler

| Field | Value |
|---|---|
| **ID** | QLT-001 |
| **Title** | Bot `ad_create.py` (1311 lines) is a god-module embedding data-access + business logic in the handler |
| **Severity** | HIGH |
| **Category** | Separation of Concerns / Single Responsibility |
| **File(s)** | `src/telegram_bot/handlers/ad_create.py:1-1311` (helper section `ad_create.py:859-1311`) |
| **Status** | Validated |
| **Type** | BEST-PRACTICE |
| **Problem** | `ad_create.py` is the ad-creation FSM router AND defines 14 `sync_to_async`-wrapped ORM data-access helpers (`create_draft_ad`, `delete_draft`, `search_categories`, `get_city_by_name`, `get_all_cities`, `get_category`, `get_city`, `get_lookup_item`, `get_lookup_item_by_slug`, `get_feature_names`, `get_resolved_purposes`, `get_resolved_features`, `get_resolved_conditions`, `get_default_purpose`) plus business-logic helpers (`show_preview`, `_format_preview_price`, `translate_all_languages`) and media helpers (`download_photo`, `save_photo`). The data-access helpers are not bot-specific — they are generic Ad/Category/City/LookupItem lookups a shared service layer would own, so the web process (separate process, same ORM/DB) cannot reuse them. |
| **Impact** | (1) Bot and web processes cannot share generic data lookups — each re-implements ORM queries, violating DRY across the process seam. (2) Embedding data-access + formatting logic in the handler makes it untestable in isolation and inflates the module far past SRP. (3) Bare `list`/`dict` return annotations and a redundant `except ValueError, Exception:` compound the quality signal. |
| **Root Cause** | No dedicated bot service layer exists for ad data access — `telegram_bot/services/` contains only `rate_limit.py`. All ORM/data-access helpers were inlined into the handler. |
| **Recommendation** | (1) Extract the data-access helpers into `telegram_bot/services/ad_data.py`, routing generic ones into the backend service layer (`apps/ads/services/`, `apps/locations/services/`, `apps/lookups/services/`) so the web process can import them. (2) Keep handlers thin: translate FSM state to/from UI messages only. (3) Replace bare `list`/`dict` with parameterized generics; fix `except ValueError, Exception:` to `except (ValueError, ArithmeticError):`. |
| **Effort** | M | **Priority** | P1 |

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Confirmed all cited facts against source: `ad_create.py` is 1311 lines (line count matches); the helper section spans `ad_create.py:859-1311`. `sync_to_async` ORM helpers counted = **14** (the finding says "15+" — minor overcount; still materially a god-module). `except ValueError, Exception:` at line 600 was verified via `ast.parse` to parse as the implicit tuple `except (ValueError, Exception):` (Python 3.14 PEG grammar treats the bare comma as a tuple); since `Exception` ⊃ `ValueError`, the redundancy is real and the recommendation to narrow to `(ValueError, ArithmeticError)` is correct (`decimal.InvalidOperation` ⟹ `ArithmeticError`). `telegram_bot/services/` confirmed to contain only `rate_limit.py` as source — BUT its `__pycache__/` holds a **stale `media.cpython-314.pyc`** with no `media.py` source (git history: commit `661c2ce fix(media): relocate media filesystem utilities from bot to apps/media` — the source moved to `apps/media/services/filesystem.py`; the orphaned `.pyc` is a hygiene artifact Python will not import). Nuuance: 3 of the 14 helpers (`get_resolved_purposes/features/conditions`) already delegate to the shared `CategoryLookupResolver` (`apps.categories.services.lookup_resolution`), so the blanket "all re-implemented by web" is slightly overstated — 11 simple lookups are the genuinely inline duplicates. Net: finding stands.
> - **See also:** QLT-002, QLT-007 (overlapping bot-handler surface); FQ-001.

*(Evidence blocks from the source findings are confirmed; snippets below are unchanged from the auditor's capture.)*

**`src/telegram_bot/handlers/ad_create.py`** *(supports: 14 `sync_to_async` ORM helpers inlined in the handler; module is 1311 lines; bare `list`/`dict` annotations; redundant except)*: the helper section runs `ad_create.py:859-1311`.
```python
async def get_resolved_purposes(category_id: int) -> list:     # line 1087 — bare list + ORM in handler
    @sync_to_async
    def _get():
        cat = Category.objects.get(id=category_id)              # raw ORM in handler
        return list(resolver.get_resolved_purposes(cat))
    return await _get()

async def show_preview(message: types.Message, data: dict) -> None:  # line 721 — bare dict
async def _format_preview_price(data: dict) -> str:                  # line 767 — bare dict
except ValueError, Exception:                                         # line 600 — redundant (verified as tuple)
```

**`telegram_bot/services/` contains only `rate_limit.py`** *(supports: no shared service layer for ad data access)*. Confirmed by directory listing (source files: `rate_limit.py`, `__init__.py` only).

**`contact.py:230-242`** *(supports: the codebase has the right delegation pattern elsewhere, confirming ad_create.py is the deviation)*: `handle_contact_orm` delegates R2 gating + analytics to `apps.core.services.contact`.

---

#### QLT-002: [HIGH] — Callback-data protocol tokens & locale list are raw string literals with no StrEnum/enum source of truth

| Field | Value |
|---|---|
| **ID** | QLT-002 |
| **Title** | Callback-data protocol tokens & locale list are raw string literals with no StrEnum/enum source of truth |
| **Severity** | HIGH |
| **Category** | StrEnum / Constants |
| **File(s)** | `src/telegram_bot/handlers/ad_create.py` (300,308,330,337,365,376,511-515,517,536,548-549,1265,1281,1294-1295,1305,1307); `language.py:27,98`; `alerts.py:31,141,148`; `login.py:61`; `ad_create.py:804,808` |
| **Status** | Validated (narrower scope) |
| **Type** | BEST-PRACTICE |
| **Problem** | Bot callback-data protocol tokens appear in two places that must stay in lock-step — (a) the `lambda c: c.data.startswith(PREFIX)` filter on the router decorator, and (b) the `callback_data=f"{PREFIX}..."` builder — with no single source of truth. In `ad_create.py`: `purpose:` (filter 300 vs builder 1265), `condition:` (330 vs 1281), `feature:` (376 vs 1305), `price_currency:` (548 vs builder 511-515), `price_free` (536 vs 517), `features_done` (365 vs 1307). Additionally `login.py:61` hardcodes `callback_data="contact_us"` rather than reusing `CONTACT_US_CALLBACK` from `contact.py:34`. Separately, `translate_all_languages` is called with a raw `["ru", "bs", "en"]` list (ad_create.py:804,808) instead of `LanguageLocale.values()`, despite that `StrEnum` existing in `core/enums.py`. |
| **Impact** | A one-character typo or prefix rename in only the filter (or only the builder) makes an entire callback family silently dead — the handler receives the callback but no route matches. Because filters are dynamic `lambda`s, the breakage is silent: no lint, no type error, no test necessarily. The `["ru","bs","en"]` literal can drift from `LanguageLocale` if a locale is added or removed. |
| **Root Cause** | aiogram callback-data tokens are conventionally plain strings, so the codebase never modeled them as a `StrEnum`/`Final` constant set; prefixes were inlined at use sites. The locale list was hand-written rather than deriving from the existing `LanguageLocale` enum. |
| **Recommendation** | (1) Introduce a `BotCallbackPrefix` StrEnum in `telegram_bot/schemas/callbacks.py` imported by both filter lambdas and builders. (2) Replace `["ru", "bs", "en"]` with `LanguageLocale.values()`. (3) Remove the `"contact_us"` literal in `login.py:61` and import `CONTACT_US_CALLBACK` from `contact.py`. |
| **Effort** | S | **Priority** | P1 |

> **Validation Note:**
> - **Action:** validated (scope narrowed)
> - **Detail:** The **genuine** drift risk is confirmed exactly as cited for the `ad_create.py` token pairs: `purpose:` (300 vs 1265), `condition:` (330 vs 1281), `feature:` (376 vs 1305), `price_currency:` (548 vs 511-517), `price_free` (536 vs 517), `features_done` (365 vs 1307) — each token is a raw string literal present at BOTH the filter site and the builder site, with no shared constant. `login.py:61` `callback_data="contact_us"` duplicating `contact.py:34` `CONTACT_US_CALLBACK` is confirmed. The `["ru","bs","en"]` literal at `ad_create.py:804,808` is confirmed, and `LanguageLocale` IS already imported (line 27) — so the literal is a genuine unused-enum violation. HOWEVER, the file-citation list over-includes two tokens that are **already centralized as module constants**: `language.py`'s `lang:` is `LANG_CALLBACK_PREFIX = "lang:"` (line 27), reused consistently at the filter (line 50 `F.data.startswith(LANG_CALLBACK_PREFIX)`) and builder (line 98 `f"{LANG_CALLBACK_PREFIX}{locale.value}"`); `alerts.py`'s `unsub_on:` is `UNSUB_ON_PREFIX = "unsub_on:"` (line 31), reused at filter (141) and builder-extraction (148). Likewise `unsub:` is the imported constant `UNSUB_CALLBACK_PREFIX` from `apps.search.services.immediate_alerts` (line 61), used at alerts.py filter 103 and the immediate_alerts builder 153. These two tokens therefore do **not** substantiate the "raw literal duplicated at both filter and builder" claim — but they remain examples of the *broader* lack of a single shared `BotCallbackPrefix` StrEnum across the bot. `telegram_bot/schemas/callbacks.py` does **not** exist yet (confirming the recommendation targets a genuinely new module; `telegram_bot/schemas/` already hosts `message_payloads.py`). The recommendation is valid and low-risk.
> - **See also:** QLT-001 (overlapping keyboard-builder extraction surface).

**Evidence — callback-data prefix duplicated between filter lambda and builder** *(confirmed for the ad_create.py pairs)*:
```python
# ad_create.py:300  (filter on the decorator)
@router.callback_query(AdCreateForm.purpose, lambda c: c.data and c.data.startswith("purpose:"))
# ad_create.py:1265 (builder)
        builder.button(text=text, callback_data=f"purpose:{purpose.slug}")
```

**Evidence — `login.py:61` duplicates `contact_us` as a raw string** *(confirmed)*:
```python
# contact.py:34
CONTACT_US_CALLBACK: Final[str] = "contact_us"
# login.py:61
                            text="Contact us", callback_data="contact_us"
```

**Evidence — raw locale list vs existing LanguageLocale enum** *(confirmed)*: `ad_create.py:804,808` call `translate_all_languages(original_title, ["ru", "bs", "en"])` while `core/enums.py:190-200` defines `LanguageLocale.StrEnum` with a `values()` classmethod returning `[m.value for m in cls]`.

---

### MEDIUM

#### QLT-003: [MEDIUM] — Web `listings.py` (508 lines) fat view embeds filter/sort/pagination logic inline

| Field | Value |
|---|---|
| **ID** | QLT-003 |
| **Title** | Web `listings.py` (508 lines) fat view embeds filter/sort/pagination logic inline in the view |
| **Severity** | MEDIUM |
| **Category** | Separation of Concerns / Single Responsibility |
| **File(s)** | `src/backend/apps/ads/views/listings.py:201-480` (the `listings()` function, ~280 lines); module totals 508 lines |
| **Status** | Validated |
| **Type** | BEST-PRACTICE |
| **Problem** | The `listings()` function (lines 201-480) performs request-parameter parsing, queryset filtering (category subtree via `get_descendants`, city resolution + did-you-mean via `suggest_city`, price-range `int`/`Decimal` coercion, listing-purpose/condition/features slug filters with `distinct()`), sort mapping (`if/elif` against `AdSort`), favorite-state annotation (`annotate_favorites`), pagination (`Paginator`), and context assembly — all inline. None of this filtering/sorting logic is delegated to a service/query-builder, so it is untestable outside a full HTTP request and is not reusable by other views. |
| **Impact** | A 280-line view is hard to review, test, and maintain; filter logic that could be shared is duplicated conceptually across `listings.py` and `search/views/search.py`. Manual `int`/`Decimal` coercion (lines 340-364) silently swallows `ValueError` rather than validating via a DTO. A small change to a filter predicate risks the 250+ line function. |
| **Root Cause** | The MPA HTMX pattern encourages request-orchestration in the view, so filter/sort/pagination logic was written directly in `listings()` rather than extracted to a query service. |
| **Recommendation** | Extract a `ListingsQuery` service (e.g. `apps/ads/services/listings_query.py`) that accepts parsed params (ideally a Pydantic DTO) and returns a `QuerySet`/paginated result; the view becomes a thin adapter (parse params → call service → render). This mirrors how `contact.py`/`alerts.py` delegate to `apps/core/services` and `apps/search/services/alert_query.py`. |
| **Effort** | M | **Priority** | P2 |

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Confirmed `listings()` spans lines 201-480 (280 lines incl. docstring, ~150 logical body) and the module is 508 lines total. Inline filter/sort/pagination confirmed: category subtree `get_descendants` (288-292), city did-you-mean via `suggest_city` (311-330), manual `int(min_price)`/`Decimal` coercion swallowing `ValueError`/`TypeError` with bare `pass` (338-364), `if/elif` sort against `AdSort` (415-427), `annotate_favorites` (431-435), `Paginator` (439-447), context assembly (452-473). The cross-reference claim that **the search view re-implements parallel filter logic** is **confirmed**: `search/views/search.py` uses the same `get_descendants` (78), `price_normalized_eur__gte=int(min_price)` (105), `listing_purpose__slug` (131), `features__slug` (147), and `order_by(F("price_normalized_eur")...)` (255, 257) patterns. The cited precedent `apps/search/services/alert_query.py` **exists** and contains `get_descendants`, `price_normalized_eur__gte` filters — confirming the thin-service pattern the recommendation asks to mirror. Operational value: MEDIUM — a shared query service would de-dup vs `search.py` and make filter logic unit-testable without an HTTP request.
> - **See also:** QLT-004 (same theme: web POST bypassing DTO validation).

*(Evidence snippet unchanged — `listings.py:201-480` confirmed.)*

---

#### QLT-004: [MEDIUM] — Web edit POST text/price-edit path bypasses Pydantic validation (sibling reactivation path validates)

| Field | Value |
|---|---|
| **ID** | QLT-004 |
| **Title** | Web edit POST text/price-edit path bypasses Pydantic validation (sibling reactivation path validates) |
| **Severity** | MEDIUM |
| **Category** | Boundary validation / Pydantic |
| **File(s)** | `src/backend/apps/ads/views/edit.py:112-263` (text-edit + price-edit branches, no DTO); contrast `edit.py:178-191` (reactivation uses `SubmitAdInput`) and `consent.py:105-115` (`ConsentSubmission.model_validate`) |
| **Status** | Validated (with architectural note) |
| **Type** | BEST-PRACTICE |
| **Problem** | The `ad_edit` POST handler reads `request.POST.get("title")`, `("description")`, `("price_amount")`, `("price_currency")` directly with manual `.strip()` + `Decimal()` coercion (lines 134-159) and writes to the ORM via `ad.save(update_fields=...)` (lines 217-226, 234-241) without any Pydantic DTO. The sibling reactivation branch (line 178) DOES validate via `SubmitAdInput(...)`, and `consent.py:112` validates via `ConsentSubmission` — so the boundary coverage is inconsistent: the most-common edit path is unvalidated while the less-common reactivation path is. |
| **Impact** | Title/description length, price range, and currency validity are only enforced reactively (by `auto_moderate` after save, or by `Decimal()` falling back to 0). Invalid/oversized input is persisted to the DB before rejection, widening the window for the bad row to be read by concurrent requests. The inconsistency means future ad-validation rules added to `SubmitAdInput` won't automatically cover the standard edit path. |
| **Root Cause** | The edit view was written before/around the shared `SubmitAdInput` DTO, so the text/price branches parse POST ad-hoc while the reactivation branch was refactored to use the DTO. |
| **Recommendation** | Route all `ad_edit` POST branches through a Pydantic edit DTO (e.g. extend `SubmitAdInput` or add `AdEditInput` with `title`/`description`/`price_amount`/`price_currency`/`photos` fields and validation) and validate before any ORM write, mirroring `consent.py`'s `_parse_submission` pattern. |
| **Effort** | M | **Priority** | P2 |

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Confirmed from source: lines 134-137 read POST ad-hoc; lines 142-147 coerce with `Decimal()` and a silent `except Exception: price_amount_value = Decimal("0")` fallback to Free; lines 217-226 and 234-241 call `ad.save(update_fields=...)` with no DTO. Line 178 confirmed: `passed, errors = submit_ad(SubmitAdInput(ad_id=ad_id, title_ru=new_title, ...))` — the reactivation branch validates. `SubmitAdInput` is a confirmed Pydantic `BaseModel` (`apps/ads/services/submission.py:36`). The `consent.py` precedent is confirmed: `_parse_submission` (lines 105-115) calls `ConsentSubmission.model_validate(request.POST.dict())`. **Architectural nuance (rollout safety):** the edit path deliberately diverges from the bot flow — lines 149-159 (with the explicit comment at 167-172) preserve the ad's **current currency on invalid input**, and the reactivation comment states "the web edit path preserves the user's existing currency on invalid input, while the bot flow always passes a valid CurrencyCode." A naive drop-in of `SubmitAdInput` would lose that semantic, so an `AdEditInput` DTO must explicitly model "keep current currency when invalid" (and decide whether blank title/description means "no change" vs "clear" — currently title/description are overwritten unconditionally even when blanked, which is itself a latent validation gap a DTO would catch). Recommendation remains valid; the DTO must preserve the documented currency-fallback behavior.
> - **See also:** QLT-003 (parallel web POST/DTO theme).

*(Evidence unchanged — `edit.py:134-159` confirmed; reactivation `SubmitAdInput` at `edit.py:178` confirmed.)*

---

#### QLT-005: [MEDIUM] — Bot i18n inconsistent: unwrapped strings, Russian msgids, template-only gate

| Field | Value |
|---|---|
| **ID** | QLT-005 |
| **Title** | Bot i18n inconsistent: alerts.py & ad_create.py emit unwrapped Russian/English strings; contact.py uses Russian msgid; completeness gate scans templates only |
| **Severity** | MEDIUM |
| **Category** | i18n / Conventions |
| **File(s)** | `src/telegram_bot/handlers/alerts.py` (no `_` import; Russian/English strings at 50,57-59,119,138,153,161,172,199,203-204); `ad_create.py` (no `_` import; hardcoded Russian at 147); `contact.py:175,179,188,247` (Russian msgid); `apps/ads/tests/test_i18n_completeness.py` (gate scope) |
| **Status** | Validated (+ FQ-001 prerequisite) |
| **Type** | BEST-PRACTICE |
| **Problem** | Bot handlers apply i18n (rule #16: i18n is part of DoD) inconsistently: (1) `alerts.py` and `ad_create.py` do NOT import `gettext`/`_` and emit raw string literals — `alerts.py` in Russian (`"Не удалось отключить уведомления"`, `"Уведомления отключены"`, `"Не удалось включить уведомления"`, `"Уведомления включены"`, `"Эта ссылка недействательна..."`, `"Уведомления отключены для этого сохранённого поиска..."`) and English (`"Please login first..."`, `"Your saved searches:"`); `ad_create.py` mixes English messages with a hardcoded Russian fallback (`"Top-level categories: Товары, Услуги, Недвижимость"` at line 147). (2) `contact.py` wraps strings in `_()` but uses Russian as the msgid (`_("объявление больше недоступно")`, `_("Покупатель")`) — violating the Django convention that msgids be English. (3) The i18n completeness gate scans templates only and does not assert bot strings are wrapped or that msgids are English. |
| **Impact** | Bot output is effectively Russian-only for non-English users: the `en`/`bs` locales cannot be satisfied because (a) most strings are never extracted (no `_()`), and (b) where `_()` is used the msgid is Russian so the catalog lookup is inconsistent. The gate gives false confidence. |
| **Root Cause** | The bot was written for a Russian/Bosnian audience with ad-hoc localization; the i18n pipeline (rule #16, `makemessages`) was designed around Django templates and never extended to bot string literals. |
| **Recommendation** | (1) Wrap ALL user-facing bot strings in `gettext`/`_()` across `ad_create.py` and `alerts.py` (add the import). (2) Make msgids English in `contact.py` (use English msgid + Russian translation in the `.po`), not Russian-as-msgid. (3) Extend the i18n completeness gate (or add a `test_bot_i18n.py`) to assert bot handlers have no bare user-facing string literals and no non-English msgids. |
| **Effort** | M | **Priority** | P2 |

> **Validation Note:**
> - **Action:** validated (recommendation incomplete — see FQ-001)
> - **Detail:** Confirmed from source: `alerts.py` imports (lines 11-21) contain **no** `gettext`/`_`; raw Russian user-facing literals confirmed at lines 119, 138, 153, 161, 172, 199, 203-204 (and English at 50, 57-59, 62, 64). `ad_create.py` imports (lines 10-47) contain **no** `gettext`/`_`; hardcoded Russian at line 147 confirmed. `contact.py` confirmed using Russian as msgid at lines 175 (`_("объявление больше недоступно")`), 179, 188, and 247 (`ANONYMOUS_BUYER_LABEL = _("Покупатель")`). The i18n gate `_collect_template_files()` in `test_i18n_completeness.py` (lines 86-106) iterates only `settings.TEMPLATES` DIRs collecting `*.html` — it never scans `src/telegram_bot/**/*.py`, so bot strings are indeed uncovenanted. **Minor wording nuance:** the finding says the gate "explicitly excludes the bot" — it does not explicitly exclude the bot; it simply never covers non-template files, so the gate is template-only by construction. **New prerequisite (FQ-001):** wrapping strings in `_()` is necessary but **not sufficient** — the bot process never calls `translation.activate()` (verified: `grep translation.activate` across `src/telegram_bot` returns no non-test hits; only the web `LanguagePreMiddleware` at `core/middleware/language.py:130` activates locale, and `User.telegram_language` is stored by `language.py` but never read for activation). Without per-user language activation, wrapped strings will still render in the default thread-local locale. The QLT-005 recommendation must be paired with FQ-001 to have behavioral effect.
> - **See also:** FQ-001 (new finding, prerequisite/dependency of QLT-005).

*(Evidence unchanged — alerts.py imports, ad_create.py:147, contact.py:175,247 confirmed.)*

---

### LOW

#### QLT-006: [LOW] — Pervasive f-string logging (49 sites) inconsistent with lazy `%s` style, not enforced by ruff

| Field | Value |
|---|---|
| **ID** | QLT-006 |
| **Title** | Pervasive f-string logging (49 sites) — not enforced by ruff |
| **Severity** | LOW |
| **Category** | Logging conventions |
| **File(s)** | 49 sites across `ads/views/{edit,delete}.py` (NOT listings.py), `media/services/filesystem.py`, `moderation/{admin_actions,services/{auto_moderation,moderation_log}.py,views/review.py`, `users/services/{account_state,deletion}.py`, `users/views/consent.py`, `telegram_bot/handlers/ad_create.py` |
| **Status** | Validated (evidence corrected) |
| **Type** | BEST-PRACTICE |
| **Problem** | 49 call sites use `logger.*(f"...")` (ruff rule G004) while the shared service layer in the same codebase consistently uses lazy `%s` formatting (e.g. `core/services/contact.py:115` `logger.info("Contact initiated event recorded for buyer %s", user_id)`, line 131; `alerts.py:241-246`). The project's ruff config does NOT enable G004 (default `ruff check` passes clean), so the inconsistency is unguarded. |
| **Impact** | F-string logging eagerly formats the message string and interpolates all arguments before the logger level check — wasted CPU on production INFO logs that may be filtered, and inconsistent style across the codebase makes it harder to grep/structure log output. Low operational impact but a real maintainability smell. |
| **Root Cause** | Mixed authoring style: view/handler authors used f-strings; service authors used `%s`. No style rule (G004) was enabled to enforce one. |
| **Recommendation** | Enable ruff rule `G004` (or `flake8-logging-format`) in `pyproject.toml` and run `ruff check --fix` to canonicalize to lazy `%s` formatting project-wide. |
| **Effort** | S | **Priority** | P2 |

> **Validation Note:**
> - **Action:** validated (evidence corrected)
> - **Detail:** `uv run ruff check --select G004 src/backend src/telegram_bot` → **Found 49 errors** (count confirmed exact). `G` is **not** in `pyproject.toml` `[tool.ruff.lint] select = ["E","F","I","B","UP"]` (lines 118-124), so the rule is unguarded — confirming the inconsistency is invisible to the default gate. The `%s` contrast is confirmed in `core/services/contact.py:115` (`logger.info("Contact initiated event recorded for buyer %s", user_id)`) and `alerts.py:241` (`logger.info("Saved search %s for user %s set active=%s via Telegram", ...)`). **Evidence corrections:** (1) the finding's evidence claims "12 hits in edit.py alone" — the actual count is **8** (edit.py:108, 230, 242, 261, 286, 294, 320, 333). (2) the file list includes `ads/views/listings.py`, but the verified ruff run shows **0** G004 hits in `listings.py` (confirmed by both the ruff output and a direct `grep "logger.*\bf\""` on listings.py returning no matches — its logs are plain `logger.warning("...")` / `logger.info("...")` literals). The corrected affected file set is `ads/views/{edit,delete}.py`, not `{listings,edit,delete}.py`. **Rollout safety:** enabling `G004` with `ruff check --fix` is mechanical and low-risk (f-string→`%s` conversion is semantically equivalent for logging); `fix=false` is the project default so the rule must be added to `select` (or a per-file `extend-select`) to take effect — a config-only change, no code rewrite required.
> - **See also:** QLT-007 (bot-handler style drift).

*(Evidence corrected per V-06/validator run: "12 hits in edit.py" → 8; listings.py removed from affected set.)*

---

#### QLT-007: [LOW] — Bare `dict`/`list` annotations in bot handler (ad_create.py); one Cyrillic word in a comment

| Field | Value |
|---|---|
| **ID** | QLT-007 |
| **Title** | Bare `dict`/`list` annotations in bot handler (ad_create.py); one Cyrillic word in a comment |
| **Severity** | LOW |
| **Category** | Type safety / English-only |
| **File(s)** | `src/telegram_bot/handlers/ad_create.py:721,767,1087,1112,1137,1157,1249,1272,1287`; `src/telegram_bot/handlers/alerts.py:30` |
| **Status** | Validated (count nuance) |
| **Type** | BEST-PRACTICE |
| **Problem** | `ad_create.py` uses bare `dict` and `list` (no type parameters) in 9 signatures — `show_preview(data: dict)`, `_format_preview_price(data: dict)`, `get_resolved_purposes(...) -> list`, `get_resolved_features(...) -> list`, `get_resolved_conditions(...) -> list`, `get_default_purpose(..., purposes: list)`, `build_purpose_keyboard(purposes: list)`, `build_condition_keyboard(conditions: list)`, `build_feature_keyboard(features: list, selected_ids: set)` — undermining the strict-typing rule. Additionally `alerts.py:30` contains a Cyrillic word in an otherwise-English comment: `# Re-enable callback prefix (complements the "Отключить" button).` |
| **Impact** | Bare generics hide element types from readers and the type-checker, weakening the "strict type hints everywhere" guarantee for the bot's public handler API. The Cyrillic comment is a minor English-only drift. |
| **Root Cause** | Author convenience / incompleteness in adding type parameters; the Cyrillic word is a literal translation of the button label embedded in a comment. |
| **Recommendation** | (1) Parameterize the bare `dict`/`list`/`set` annotations (e.g. `data: dict[str, object]`, `-> list[LookupItem]`, `selected_ids: set[int]`). (2) Replace the Cyrillic word in the comment with English (`"Disable"`). |
| **Effort** | S | **Priority** | P2 |

> **Validation Note:**
> - **Action:** validated (count nuance)
> - **Detail:** All **9** bare-annotation line citations confirmed (721, 767, 1087, 1112, 1137, 1157, 1249, 1272, 1287). Minor inconsistency: the finding says "8 signatures" but the line list cites 9 locations — `build_purpose_keyboard(purposes: list, ...)` at line 1249 is included in the line list but omitted from the 8-signature enumeration; it is nonetheless a confirmed bare `list`. `alerts.py:30` Cyrillic comment confirmed verbatim. Recommendation valid; low-risk style fix. Note: these annotations live in the helper section targeted by QLT-001's extraction — parameterizing them should be folded into that refactor to avoid duplicate churn.
> - **See also:** QLT-001.

*(Evidence unchanged — bare annotations and the alerts.py:30 comment confirmed.)*

---

### New Finding (Validator-Added)

#### FQ-001: [MEDIUM] — Bot wraps strings in `_()` but never activates the per-user locale; QLT-005 fix would be a no-op for non-default locales

| Field | Value |
|---|---|
| **ID** | FQ-001 |
| **Title** | Bot persists `User.telegram_language` but never calls `translation.activate()` in the bot process |
| **Severity** | MEDIUM |
| **Category** | i18n / Architecture |
| **File(s)** | `src/telegram_bot/handlers/language.py:116-118` (sets `telegram_language`); `src/backend/apps/core/middleware/language.py:125-130` (web-only activation); `src/telegram_bot/` (grep: no `translation.activate` in non-test code) |
| **Status** | Validated (new) |
| **Type** | SPEC-DEVIATION |
| **Problem** | The bot lets users pick a language (`language.py` writes `telegram_language` to the `User` row) and bot handlers wrap some strings in `_()` (`contact.py`, `login.py`, `language.py`). But **only the web process activates a locale** — `LanguagePreMiddleware` calls `translation.activate(lang)` at `core/middleware/language.py:130`. A grep for `translation.activate` / `translation.override` across `src/telegram_bot/` returns hits **only in test files** (`test_multi_lang_translation.py` mocks the content-translation path; `test_save_photo_integration.py` uses `override_settings` for `MEDIA_ROOT`). No bot middleware or handler activates `User.telegram_language`, so every bot message is rendered in whatever thread-local locale is active at process start (the default `LANGUAGE_CODE`). |
| **Impact** | Even after QLT-005 wraps all bot strings in `_()` and fixes Russian msgids, non-default-locale users still receive the default locale's text — the i18n investment yields no behavioral change without per-user activation. This also undermines `rules #16` (i18n is part of DoD) for the Telegram channel specifically. |
| **Root Cause** | The i18n pipeline was architected around the web request/middleware lifecycle; the aiogram bot has no equivalent per-request language-activation hook before `message.answer(...)` / `callback.answer(...)`. |
| **Recommendation** | Add a bot-side i18n activation point (e.g. an aiogram `MessageHandler`/`Middleware` that resolves the sender's `telegram_language` and calls `translation.activate(...)` around the handler, or a helper invoked before each user-facing `answer()`) so wrapped strings actually render in the user's language. This is a prerequisite/enabler for QLT-005. |
| **Effort** | S-M | **Priority** | P2 | **Dependency** | QLT-005 |

> **Validation Note:**
> - **Action:** new finding (validator-added)
> - **Detail:** Evidence: `grep -rn "translation.activate" src` → matches only `core/middleware/language.py:130` (web) + test files; no match in `src/telegram_bot/handlers/*.py`. `User.telegram_language` is written by `_set_user_language` (language.py:118) and read by `_get_user_language` (language.py:109) — but never piped into `translation.activate`. `test_i18n_completeness.py` does not assert activation (it scans templates only). Classified `SPEC-DEVIATION` (code does not satisfy the i18n DoD it otherwise advertises for the web). Reclassification to `BEST-PRACTICE` if the project intends bot i18n to be best-effort only. Low rollout risk: adding `translation.activate(user_lang)` around handler dispatch is additive and reversible.
> - **See also:** QLT-005.

---

## Cross-Finding Analysis (Validated)

**Merge candidates:** None merged. The 7 findings address distinct fix surfaces (god-module structure, constant modeling, web-view fatness, POST DTO coverage, i18n wrapping, logging style, type annotations) and merging them would conflate non-overlapping remediations. They DO share root gaps, which are noted rather than merged:

| Shared root gap | Finding IDs | Why not merge |
|---|---|---|
| `ad_create.py` is a monolithic, non-conformant handler (no service layer, no StrEnum tokens, no `_()` wrapping, f-string logging, bare generics) | QLT-001, 002, 005, 006, 007 | Fixes touch different layers (data-access extraction vs. constants vs. i18n vs. logging vs. typing); merging would scatter one coherent refactor. |
| `ad_create.py` keyboard builders (`build_purpose/condition/feature/currency_keyboard`) are the **same code** hit by QLT-001 (extraction) and QLT-002 (callback tokens) | QLT-001 + QLT-002 | Overlapping surface — see rollout note below (dependency, not a merge). |
| Web POST boundary lacks DTO validation | QLT-004 + QLT-003 (manual `int`/`Decimal` coercion without DTO) | QLT-003 is about listings filtering (read path, query params); QLT-004 is the edit write path. Related theme, different views. |
| Bot i18n incompleteness | QLT-005 + FQ-001 | FQ-001 is a prerequisite of QLT-005, folded in (not a duplicate). |

**Cross-phase conflicts:** None. The source findings' cross-phase note is corroborated: QLT-005 confirms the bot i18n gap that Phase 10's `test_i18n_completeness.py` scope (templates-only) leaves uncovered; QLT-004 matches the `SubmitAdInput` DTO already referenced in the spec (Appendix B assumption, confirmed Pydantic `BaseModel` at `apps/ads/services/submission.py:36`). QLT-003's "search re-implements parallel filter logic" was verified against `search/views/search.py` (grep matches at 78, 105, 131, 147, 255, 257) — consistent with Phase 08's note that `search.py` is thin (the alert_query service is thin; the search *view* independently re-implements filter predicates vs. `listings.py`). No contradiction with Phase 01's async-boundary/cache caveats.

**Dependency chains / hidden dependencies (Step 4):**
1. **QLT-001 → QLT-002 (overlap):** Extracting `ad_create.py`'s keyboard builders (QLT-001) without centralizing their callback tokens (QLT-002) would **relocate** the raw `purpose:`/`condition:`/`feature:`/`price_free`/`features_done` literals into the new `services/ad_data.py` rather than eliminating them. QLT-002's `BotCallbackPrefix` enum should be introduced **within** QLT-001's keyboard-builder extraction. Not a blocker, but a sequencing dependency to avoid churn.
2. **QLT-002 → QLT-005:** `build_*_keyboard` functions are the only places the callback tokens are constructed. If QLT-005 wraps keyboard button **labels** in `_()`, the same functions are already being refactored by QLT-001/QLT-002 — so do the i18n wrapping in the same pass.
3. **FQ-001 → QLT-005 (prerequisite):** Bot string wrapping is a no-op without per-user `translation.activate()` (FQ-001). QLT-005's recommendation is incomplete without FQ-001.

## Rollout Safety (Validated)

- **Circular dependencies:** None. QLT-002's `telegram_bot/schemas/callbacks.py` depends on nothing; QLT-001's `telegram_bot/services/ad_data.py` imports shared backend models (bot→backend direction only; backend never imports the bot); QLT-003's `apps/ads/services/listings_query.py` is intra-backend. No cycles.
- **Unsafe insertion points:** QLT-002's filter lambdas (`lambda c: c.data.startswith(PREFIX)`) are themselves the fragile pattern the finding identifies — replacing them with an enum is the fix; no new fragility introduced.
- **Backward compatibility:** All 7 findings are refactor/style improvements with no schema or API contract change. QLT-004's DTO refactor must preserve the documented currency-fallback behavior (noted above). FQ-001's `translation.activate()` addition is additive and reversible.
- **Test gate:** The source findings' rollout note is correct and retained — run `make test` (fast gate, skips `seed`) in the `mko-bazuna-test` compose project and confirm ad-creation + i18n completeness tests remain green. QLT-005/FQ-001 additionally benefit from a bot i18n coverage test (the finding's own suggestion).
- **Stale-artifact hazard:** `telegram_bot/services/__pycache__/media.cpython-314.pyc` is an orphan (source relocated per commit `661c2ce`). Python will not import an orphan `__pycache__` `.pyc` without source, so it is harmless at runtime, but it should be pruned (`git clean -xf`/`__pycache__` flush) to avoid confusion during QLT-001's service-layer extraction.

## Execution Validation

| Finding | Targets still exist? | Code vs docs consistent? | Architectural fit | Ready to schedule? |
|---|---|---|---|---|
| QLT-001 | ✅ `ad_create.py:859-1311` helpers present | ✅ matches source | ✅ aligns with SoC rule + rate_limit.py precedent | ✅ (P1, bot-only) |
| QLT-002 | ✅ token pairs at cited lines | ✅ matches source | ✅ aligns with StrEnum rule #10 | ✅ (P1, bot-only; fold into QLT-001) |
| QLT-003 | ✅ `listings():201-480` | ✅ matches source | ✅ aligns with thin-view pattern | ✅ (P2, web-only) |
| QLT-004 | ✅ edit.py POST branches | ✅ matches source | ✅ aligns with Pydantic rule #11 | ✅ (P2, web-only; preserve currency fallback) |
| QLT-005 | ✅ no `_` import in alerts/ad_create; Russian msgids in contact; gate template-only | ✅ matches source | ✅ aligns with i18n rule #16 | ⚠️ Requires FQ-001 first |
| QLT-006 | ✅ 49 G004 hits; G absent from ruff select | ✅ matches ruff run | ✅ aligns with logging rule #12 (%s style in core/services/contact.py) | ✅ (P2, config-only to enable; `--fix` to apply) |
| QLT-007 | ✅ 9 bare annotations; Cyrillic comment | ✅ matches source | ✅ aligns with type-safety rule #9 | ✅ (P2, folded into QLT-001 pass) |
| FQ-001 | ✅ no `translation.activate` in bot non-test code | ✅ matches grep | ✅ required for i18n DoD | ✅ (P2, prerequisite for QLT-005) |

## Warnings

- **Bot i18n is doubly broken, not singly:** QLT-005 (unwrapped strings / Russian msgids) AND FQ-001 (no locale activation). Fixing only the wrapping gives a false sense of coverage — the completeness gate (`test_i18n_completeness.py`) passes today while the bot ships effectively Russian-only because it never activates a non-default locale. Extend the gate to bot handlers.
- **QLT-006 evidence drift:** The source audit's "12 hits in edit.py" and `listings.py` inclusion are both wrong (8 hits; listings.py clean). Any follow-up verification keyed to those exact counts/files will be confused — use the corrected set `ads/views/{edit,delete}.py`.
- **Stale bytecode:** `telegram_bot/services/__pycache__/media.cpython-314.pyc` is an orphan from commit `661c2ce`. Not a runtime hazard, but signals `__pycache__` hygiene gaps that should be flushed before QLT-001's extraction.
- **QLT-004 behavioral-preservation risk:** The edit view's currency-fallback-on-invalid and the unconditional title/description overwrite are undocumented edge behaviors. A DTO refactor must encode them explicitly or the `make test` gate (which presumably asserts the fallback) will regress.

## Required Fixes

1. **QLT-002 (P1):** Introduce `BotCallbackPrefix` StrEnum in `telegram_bot/schemas/callbacks.py`; route the ad_create.py token pairs (`purpose:`, `condition:`, `feature:`, `price_currency:`, `price_free`, `features_done`) and `login.py`'s `contact_us` through it. **Do this in the same pass as QLT-001's keyboard-builder extraction** to avoid relocating raw literals.
2. **QLT-001 (P1):** Extract the 14 `sync_to_async` ORM helpers out of `ad_create.py` into `telegram_bot/services/ad_data.py` (generic lookups may live in the backend service layer for web reuse); parameterize generics (QLT-007); replace `except ValueError, Exception:` with `except (ValueError, ArithmeticError):`; prune the orphan `services/__pycache__/media.*.pyc`.
3. **QLT-005 + FQ-001 (P2):** (a) Add per-user `translation.activate()` in the bot before rendering (FQ-001) — prerequisite. (b) Wrap `alerts.py`/`ad_create.py` strings in `gettext`/`_()`; make `contact.py` msgids English; extend the i18n completeness gate to bot handlers.
4. **QLT-006 (P2):** Add `G` (or `G004`) to `pyproject.toml` `[tool.ruff.lint] select`; run `ruff check --select G004 --fix` to canonicalize. (Config change; `fix=false` is the default so enabling is opt-in.)
5. **QLT-003 (P2):** Extract `ListingsQuery` service accepting a Pydantic DTO of parsed params; make `listings()` a thin adapter; share the query object with `search.py` to de-dup filter logic.
6. **QLT-004 (P2):** Introduce an `AdEditInput` Pydantic DTO for the edit POST; validate before ORM write; explicitly model the currency-fallback-on-invalid and no-change-vs-clear semantics. Preserve the documented behavior or update tests.
7. **QLT-007 (P2):** Parameterize the 9 bare `dict`/`list`/`set` annotations; replace the Cyrillic word in `alerts.py:30` with English. (Fold into QLT-001's pass.)

## Advisory Recommendations (optional, not required)

- **Extend the i18n gate to Python:** Add a `test_bot_i18n.py` asserting no bare user-facing string literals in `telegram_bot/handlers/` and no non-English msgids in `_(...)` calls — so the completeness gate no longer gives false confidence.
- **Prefer `Final`/enum for the remaining module constants** (`LANG_CALLBACK_PREFIX`, `UNSUB_ON_PREFIX`) by folding them into the proposed `BotCallbackPrefix` StrEnum for a single bot-wide source of truth (QLT-002 enhancement).
- **Add `G004` to CI's `ruff` invocation** (not just local) so the style drift cannot regress; the project's `make format` already runs `ruff check --fix src/`.
- **De-dup feature-condition slug exclusion:** `ad_create.py:268` and `:1294` both literal `("new", "used")` — if these slugs are stable identifiers, consider a `LookupGroupCode`/condition enum rather than magic strings.

---

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged type) | 7 | QLT-001, QLT-002, QLT-003, QLT-004, QLT-005, QLT-006, QLT-007 |
| Reclassified | 0 | — |
| Merged | 0 | — (related root gaps noted, not merged — distinct fix surfaces) |
| Rejected | 0 | — |
| New (validator-added) | 1 | FQ-001 (bot locale activation prerequisite for QLT-005) |

### Rejected Findings

| ID | Title | Reason |
|----|-------|--------|
| (none) | — | All 7 source findings were verified against code and are technically correct and currently applicable. |

### Merged Findings

| Original ID | Merged Into | Rationale |
|-------------|-------------|----------|
| (none) | — | QLT-001/002/005/006/007 share the `ad_create.py`-monolith root gap but have distinct remediation layers; merging would scatter a coherent refactor. See Cross-Finding Analysis. |

### Reclassified Findings

| ID | Original Type | New Type | Rationale |
|----|---------------|----------|-----------|
| (none) | — | — | — |

---

*Report generated: 2026-09-12. Validator: kilo/poolside/laguna-s-2.1:free. Source findings file: `.ai/audit/10-code-quality/findings.md` (draft). This file is the self-contained validated report: `.ai/audit/99-validation/10-code-quality-validated-findings.md`. No source code was modified during validation. Verification commands run: `uv run ruff check`, `uv run ruff check --select G004 src/backend src/telegram_bot` (→ 49 errors), `uv run basedpyright src/backend src/telegram_bot` (1 pre-existing test-only error), `ast.parse` on `ad_create.py` line 600 except-clause, `grep` for `translation.activate`/`gettext`/`callback_data=startswith` across `src/`.*
