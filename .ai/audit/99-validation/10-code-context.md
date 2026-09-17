# Code Context — Code Quality Findings (Phase 10 Audit)

> **Status: LIVE working-tree state, 2026-09-17.** This document supersedes the
> prior `10-code-context.md` (which described a *pre-refactor* "NEEDS ACTION"
> state). The working tree has since implemented Blocks B–E, so every finding
> below is updated against the **current** source. Findings that remain
> unaddressed are explicitly flagged.

## Working-tree state (READ THIS FIRST — gates commit risk)

The refactor is **implemented but NOT committed**. `git status --short` shows:

- **Committed** (in `7ec80c7 chore plans`): Block A ruff G004/I001 pass on
  `apps/common/models/ad.py`; the 4 legacy `apps/ads/services/*.py` were created in
  that commit; the prior `10-code-context.md` + plan `22-code-quality-fixes.md`
  + test-audit docs were added.
- **Uncommitted — Block B–E implementations** (`git status` = ` M` / `??`):

| Change type | Files | Block |
|---|---|---|
| new (untracked) | `src/telegram_bot/services/ad_data.py` (533) | C |
| new (untracked) | `src/telegram_bot/schemas/callbacks.py` (29) | C |
| new (untracked) | `src/telegram_bot/middlewares/language.py` (80) | B/FQ-001 |
| new (untracked) | `src/backend/apps/ads/services/listings_query.py` (263) | D |
| modified | `src/telegram_bot/handlers/ad_create.py` (1393→926) | C |
| modified | `src/backend/apps/ads/services/submission.py` (+`AdEditInput`) | E |
| modified | `src/backend/apps/ads/views/edit.py`, `listings.py`, `search/views/search.py` | D,E |
| modified | `src/telegram_bot/{main.py, middlewares/__init__.py, handlers/{contact,alerts,language,ad_copy,login}.py, tests/conftest.py, tests/test_*.py}` | B,C |
| modified | `src/backend/locale/{ru,bs,en}/LC_MESSAGES/django.po`, `tests/test_i18n_completeness.py` | B |
| deleted (wrote-tree) | `.ai/audit/99-validation/10-code-context.md`, `10-failing-tests-root-cause-audit.md` | — |

**Implication:** All Block B–E status = "structurally implemented in working tree
**and runtime-verified green**" (fast gate: 1576 passed, 0 failed). Commit gated on
clearing the QLT-007 pyright findings (§Runtime Verification) and the QLT-002
`contact_us` token-consolidation advisory.

## Scope

The 7 code-quality findings mapped to `docs/99-agent/architecture.md` and plan
`.ai/plans/22-code-quality-fixes.md` (block gates A–E + FQ-001):

| Plan block | Finding ID | Type | Subject |
|---|---|---|---|
| A | QLT-006 | BEST-PRACTICE | ruff `G` (G004) gate |
| B | FQ-001 | SPEC-DEVIATION | bot per-user locale middleware |
| B | QLT-005 | BEST-PRACTICE | i18n wrapping + `.po` completeness |
| C | QLT-001 | BEST-PRACTICE | bot `ad_create.py` god-module extraction |
| C | QLT-002 | BEST-PRACTICE | callback-token centralization |
| C | QLT-007 | BEST-PRACTICE | `# type: ignore` hygiene + StrEnum models |
| D | QLT-003 | BEST-PRACTICE | listings/search queryset extraction |
| E | QLT-004 | BEST-PRACTICE | ad-edit `AdEditInput` DTO |

## Verification method

- `uv run ruff check src/backend src/telegram_bot` → **All checks passed** (read-only).
- Source reads + `grep` for token/registration absence.
- `git status` / `git show` for commit vs. work-tree attribution.
- `.po` grep `^msgstr ""$` per locale.
- Compose `test` service (fast-gate, `PYTEST_SKIP_MARKERS=seed`) launched against the
  running `mko-bazuna-test-db-1` (postgres:18-alpine) — results in §Runtime Verification.

## Two-process model

Web (gunicorn sync WSGI, HTMX MPA) + bot (aiogram 3.x). Both call `django.setup()`
and share the ORM over one PostgreSQL. Direction is **bot → backend only**:
`ad_data.py`, `ad_create.py`, `language.py` import `apps.*`; no `apps.*` module
imports `telegram_bot.*` (verified: reverse import would be cyclic — see plan
§5.4). All extraction targets below respect this.

## Finding status (updated vs. prior audit)

| ID | Severity | Type | Prior | **Live** | Evidence |
|---|---|---|---|---|---|
| QLT-006 | LOW | BEST-PRACTICE | NEEDS ACTION | **IMPLEMENTED** | pyproject `select` has `"G"` (124); ruff clean |
| FQ-001 | MEDIUM | SPEC-DEVIATION | NEEDS ACTION | **IMPLEMENTED** | `language.py:27`; `main.py:62` before `AccountStateMiddleware` @66; conftest:81 |
| QLT-005 | MEDIUM | BEST-PRACTICE | NEEDS ACTION | **IMPLEMENTED** | ru/bs 0 empty msgstr (394 msgids); `ad_create.py` `_()`; `test_i18n_completeness.py` modified |
| QLT-001 | HIGH | BEST-PRACTICE | PARTIAL (Stage 1) | **IMPLEMENTED** | `ad_data.py` (533) holds all extracted helpers; `ad_create.py` 1393→926 |
| QLT-002 | HIGH | BEST-PRACTICE | NEEDS ACTION | **IMPLEMENTED (ad_create)** | `callbacks.py` StrEnum; 0 raw tokens in `ad_create.py`; §Gap: `contact_us` duplicated |
| QLT-007 | LOW | BEST-PRACTICE | NEEDS ACTION | **PARTIAL — NOT VERIFIED** | `# pyright: ignore` remains in `edit.py:124,285,322`; `basedpyright` not run this pass |
| QLT-003 | MEDIUM | BEST-PRACTICE | NEEDS ACTION | **IMPLEMENTED** | `ListingsQuery` (263) + `listings.py`/`search.py` thin |
| QLT-004 | MEDIUM | BEST-PRACTICE | NEEDS ACTION | **IMPLEMENTED** | `AdEditInput` (submission.py:59); `edit.py:135` |

---

## Block A — QLT-006: ruff `G` (G004) gate

**Plan acceptance (22 §3.2):** `"G"` in `[tool.ruff.lint] select`;
`ruff check src/backend src/telegram_bot` → 0 errors.

**Live evidence:**
- `pyproject.toml:124` → `"G",  # flake8-logging-format (G004: f-string in logging → lazy %s)`
- `uv run ruff check src/backend src/telegram_bot` → **`All checks passed!`**
- `apps/common/models/ad.py` carries the committed G004 fix from `7ec80c7`.

**Status:** IMPLEMENTED / committed. No further action.

---

## Block B — FQ-001 + QLT-005: per-user locale + i18n

**Plan acceptance (22 §4):** FQ-001 — `LanguageMiddleware` in `telegram_bot/middlewares/`,
exported from `__init__.py`, registered in `main.py` on `dp.update.middleware` **before**
`AccountStateMiddleware`; also wired in `conftest.py` atomically. QLT-005 — bot strings
wrapped in `_()`; `ru`/`bs` msgstrs non-empty.

**Live evidence:**
- **New file** `src/telegram_bot/middlewares/language.py` (80 lines):
  `LanguageMiddleware(BaseMiddleware)` (`language.py:27`). Activates
  `translation.activate(lang)` around handler dispatch; `event.from_user.id` →
  `User.telegram_language` via `_resolve_user_language` (`language.py:62`,
  `@sync_to_async`); falls back to `settings.LANGUAGE_CODE` when no user / no
  `from_user`. `deactivate()` in `finally` prevents thread-local locale leakage
  across updates on a shared asgiref worker (correct two-process concern).
- **`middlewares/__init__.py`** (13 lines) exports `LanguageMiddleware` (4, `__all__` 11).
- **`main.py:62`** → `dp.update.middleware(LanguageMiddleware())`, comment at 60
  ("must run before AccountStateMiddleware"), `AccountStateMiddleware` @66. ✓ order.
- **`tests/conftest.py:81`** mirrors the same ordering (dispatcher fixture mirrors
  production). `conftest.py:83` → `AccountStateMiddleware` after; the `# pyright: ignore`
  at conftest:83 is test-only. ✓ both files edited atomically (status ` M`).
- Token source: `ad_create.py` (bot handlers) and `listings.py`/`search.py` (web) were
  wrapped in `gettext as _` (web already used `gettext`).
- **`.po` completeness** (grep `^msgstr ""$`):
  - msgids (excl. header) across `ru`/`bs`/`en`: **394**.
  - `ru`: 0 empty non-header `msgstr` (only the file header at LC line 6).
  - `bs`: 0 empty non-header `msgstr`.
  - `en`: per spec §16 may be empty (msgid = English); not gated.

**Note / minor caveat:** `LanguageLocale.from_code("invalid")` raises — plan §5.3 flags
invalid-code handling; no new test added in working tree. `ru`/`bs` translation of the
newly-wrapped bot strings is complete.

**Status:** IMPLEMENTED.

---

## Block C — QLT-001 + QLT-002 + QLT-007: bot god-module extraction + token centralization

### QLT-001 — `ad_create.py` (1393 → 926 lines) extraction

**Plan acceptance (22 §5):** `telegram_bot/services/ad_data.py` contains all 15
extracted `sync_to_async` ORM helpers **+ `download_photo` + `save_photo` +
`translate_all_languages` + 4 keyboard builders**; bot→backend import direction only.

**Live evidence:**
- **New file** `src/telegram_bot/services/ad_data.py` (533 lines):
  - `__all__` (51–55) lists `"download_photo"`, `"save_photo"`, and `translate_all_languages`.
  - `download_photo` @182 (`async def`, fetches via `Bot`).
  - `save_photo` @196 (`async def`, writes staging).
  - `translate_all_languages` @270 (`async def`).
  - sync_to_async ORM-helper block ~80–443 (nested `_create`/`_get`/`_search`/
    `_delete`/`_write` closures inside `@sync_to_async` funcs — the "15" target set).
  - 4 builders: `build_currency_keyboard` @444, `build_purpose_keyboard` @462,
    `build_condition_keyboard` @488, `build_feature_keyboard` @506.
  - All builders consume `BotCallbackPrefix` (grep: 25 `BotCallbackPrefix` references in
    `ad_data.py` + `ad_create.py` + `callbacks.py`).
- **`ad_create.py` slimmed 1393→926 lines.** Imports now:
  - `from apps.ads.services.submission import SubmitAdInput, submit_ad` (23)
  - `from telegram_bot.schemas.callbacks import BotCallbackPrefix` (33)
  - `from telegram_bot.services.ad_data import (...)` (40)
  - `class AdCreateForm(StatesGroup)` (76) retained.
- **`submit_ad` now shared:** called from bot `process_preview` (via `sync_to_async`,
  `ad_create.py:23` import) **and** web edit reactivation (`edit.py:163`).
  `submission.py` docstring (1–13) documents the currency-coercion divergence (Path 2).

**Status:** IMPLEMENTED. Extraction targets all present in `ad_data.py`.

### QLT-002 — callback-token centralization

**Plan acceptance (22 §6):** no raw callback tokens in `ad_create.py`; `callbacks.py`
defines `BotCallbackPrefix`.

**Live evidence:**
- **New file** `src/telegram_bot/schemas/callbacks.py` (29 lines):
  `class BotCallbackPrefix(StrEnum)` with 8 members — `PURPOSE, CONDITION, FEATURE,
  PRICE_CURRENCY, PRICE_FREE, FEATURES_DONE, CONTACT_US` (20–26). `__all__` (29).
- **`ad_create.py` raw-token scan** (grep for
  `purpose:|condition:|feature:|price_currency:|price_free|features_done|contact_us`)
  → **0 raw callback literals**. The 3 matches are benign: `default_purpose` var (238),
  a `# Single purpose:` comment (254), and `_("Select item condition:")` (303).
  All 10 token usages route through `BotCallbackPrefix.*` (filter lambdas:
  ad_create.py 357/365/388/395/423/434/435/578/590/591; builders via `ad_data.py`).

**Gap (advisory):** `BotCallbackPrefix.CONTACT_US` (callbacks.py:26) is **defined but
unused**. `src/telegram_bot/handlers/contact.py:35` declares its own
`CONTACT_US_CALLBACK: Final[str] = "contact_us"` and `CONTACT_US_PATTERN` (31) — the
same sentinel, duplicated outside the StrEnum. QLT-002's acceptance only scopes
`ad_create.py` (which is clean), so this is a **consistency** gap, not a regression.
*Recommendation:* route `contact.py` through `BotCallbackPrefix.CONTACT_US` (trivial,
but touches the contact deep-link regex — verify `test_contact_us.py` after).
(Out of scope for QLT-002 as written; flagged for follow-up.)

**Status:** IMPLEMENTED for `ad_create.py` / `ad_data.py`.

### QLT-007 — `# type: ignore` / StrEnum model annotations

**Plan acceptance (22 §5, staging table row C):** QLT-007 in Block C scope.

**Live evidence:**
- **NOT verified in working tree.** `basedpyright` was not executed (ruff does not
  cover type-ignores). Remaining `# pyright: ignore[...]` directives in live source:
  - `edit.py:124`, `edit.py:285`, `edit.py:322` → `# pyright: ignore[reportGeneralTypeIssues]`
    (all on `with transaction.atomic():` — caused by `django-stubs` not installed).
  - `conftest.py:83` (bot tests) → `# pyright: ignore[reportAbstractUsage]`.
  - `listings_query.py` / `submission.py` / `ad_data.py` — no type-ignores observed.
- The plan's "9 bare `# type:` annotations in `apps/common/models/ad.py`" target file
  is **not in the working-tree `M` set** — `ad.py` is unchanged since `7ec80c7`, so
  any pre-existing bare annotations there remain.

**Status:** PARTIAL / NOT VERIFIED. *Recommendation:* run
`uv run basedpyright src/backend/apps/ads/views/edit.py src/telegram_bot/services/ad_data.py
src/telegram_bot/services/language.py` and remediate the `transaction.atomic()`
suppressions (install `django-stubs` or annotate the `Atomic` context manager) to
close QLT-007. Do **not** touch `apps/common/models/ad.py` StrEnum fields until
pyright confirms the current state.

---

## Block D — QLT-003: listings/search queryset extraction

**Plan acceptance (22 §8):** `ListingsQuery` class in
`apps/ads/services/listings_query.py`; `ListingsQueryParams` Pydantic DTO validates
all filter params (no silent `except: pass`); `listings()` + `search()` delegate;
queryset semantics identical.

**Live evidence:**
- **New file** `src/backend/apps/ads/services/listings_query.py` (263 lines):
  - `ListingsQueryParams(BaseModel)` (40–105) — `category_slug, city_slug,
    min_price, max_price, purpose_slug, condition_slug, feature_slugs, sort, user_id,
    page, per_page`; three `@field_validator(mode="before")`:
    `_coerce_int_or_none` (64), `_coerce_sort` (77), `_coerce_page` (92). Invalid
    inputs coerce to safe defaults — **replaces the old silent `except: pass`**
    (docstring 43–47).
  - `ListingsQuery` (107–263): `PER_PAGE = 24`; `build_queryset` (118–192) preserves
    the original pipeline order (PUBLISHED base → category-subtree → city → price →
    purpose → condition → features AND+distinct → sort → `annotate_favorites`);
    `_apply_sort` (195–204); `active_price_range` (207–218);
    `resolve_filter_options` (221–263).
- **`apps/ads/views/listings.py` (271 lines):** `listings()` (207–262) now thin —
  `params = ListingsQueryParams(...)` (235–242) → `ListingsQuery.build_queryset(params)`
  (243) + `resolve_filter_options` (245) + `active_price_range` (251). Still owns
  request-scoped concerns: rate limit (218), did-you-mean city/category, HTMX partial
  selection.
- **`apps/search/views/search.py` (296 lines):** `search()` (39–170) same delegation;
  FTS (`_apply_fts`, 173–233) intentionally stays view-level (docstring
  `listings_query.py:14`: "the FTS branch (`q` param …)`). `LanguageLocale.from_code`
    (182) + per-language `SearchQuery`/`SearchRank` preserved.
- `ListingsQueryParams` field names **diverge** from form-query-param names
  (`purpose_slug` vs `listing_purpose`, `condition_slug` vs `condition`) — mapping done
  in each view (listings.py:238, search.py:89/90). Semantics preserved.

**Test coverage note:** no file literally named `test_listings.py` exists in the tree
(`test_listings.py` was not present in `git status`), but listings queryset is covered
by `test_listings_context.py` + `test_listings_sort.py`, and search by
`test_search_view.py` (see Block E test-audit findings). Accept.

**Status:** IMPLEMENTED / verified (§Runtime Verification). `test_listings_context.py`,
`test_listings_sort.py`, `test_search_view.py` all green in the fast gate.

---

## Block E — QLT-004: ad-edit `AdEditInput` DTO

**Plan acceptance (22 §7):** `AdEditInput` Pydantic DTO in
`apps/ads/services/submission.py`, **sibling to `SubmitAdInput`** (not a modification);
`test_edit.py` passes (behavior preserved); `SubmitAdInput` unchanged (bot flow).

**Live evidence:**
- **`submission.py` (256 lines)** now hosts both DTOs:
  - `SubmitAdInput(BaseModel)` (37–56) — unchanged shape (ad_id, title_ru/desc_ru,
    price_amount, price_currency, photos, feature_ids, listing_condition_id, …).
  - `AdEditInput(BaseModel)` (59–110) — NEW. Fields `title=""`, `description=""`,
    `price_amount=Decimal("0")`, `price_currency: CurrencyCode | None = None`.
    Validators model the web-edit divergences explicitly:
    - `_coerce_price_amount` (90–99): empty/unparseable → `Decimal("0")` (Free) —
      preserves old `except Exception` fallback (plan §7.2 line 852).
    - `_coerce_price_currency` (101–110): invalid/blank → `None` — preserves old
      `except ValueError: pass` "keep current currency" behavior (plan §7.1 line 850).
    - `_strip_text` (83–88) for title/description.
    - `TODO(QLT-004)` (72–75): blank title/description still overwrite (intent preserved,
      not closed this pass — matches plan's "preserve blanket-overwrite, defer").
  - `submit_ad` (113–256) documented currency-coercion divergence (Path 2, 123–133).
- **`edit.py` (346 lines):** `ad_edit` POST now `dto = AdEditInput.model_validate(request.POST)`
  (135) before any `.save()`; `_text_fields_changed` (66–77) + `_apply_price_change`
  (30–63) pure helpers; `submit_ad(SubmitAdInput(...))` for reactivation (163);
  `transaction.atomic()` + `select_for_update()` around POST (124–125, DB-003 row lock).
- `SubmitAdInput` consumers unchanged: bot `ad_create.py:23` (still `from …import
  SubmitAdInput, submit_ad`). ✓ bot flow unaffected.

**Status:** IMPLEMENTED (DTO is a new sibling; `SubmitAdInput` untouched).

---

## Cross-cutting runtime model notes (for downstream gates)

- **Bot FSM persistence:** ad dialog kept as an `Ad` row in `DRAFT` (spec); `submit_ad`
  transitions DRAFT→ON_MODERATION then `auto_moderate`→PUBLISHED/FAILED (submission.py
  240–252). `edit.py` reactivation ARCHIVED→ON_MODERATION via `submit_ad`.
- **Postgres FTS:** per-language vectors; `setup_search_triggers` mgmt command
  (entrypoint runs it before pytest). `SearchRank`/`SearchQuery(websearch)` in search.
- **Two-process DB sharing:** both gunicorn workers and bot call `django.setup()`;
  migrations run once before both start. The `LanguageMiddleware._resolve_user_language`
  DB hit per update is the documented optional-cache concern (plan §4.2 line 358) —
  **not** implemented (simple dict cache) — acceptable for sequential-per-chat bot.

## Discrepancies & gaps (must resolve before commit)

1. **QLT-007 unverified** — `basedpyright` not run; 3 `transaction.atomic()` pyright
   suppressions in `edit.py` + 1 in `conftest`. (ADVISORY)
2. **QLT-002 partial** — `contact.py:35` duplicates `BotCallbackPrefix.CONTACT_US`
   rather than importing it. (ADVISORY)
3. **Runtime gate (Block D/E):** the fast-gate run resolved green —
   **1576 passed, 0 failed, 0 errors (104.74s)**; `testpaths = ["src/backend",
   "src/telegram_bot"]` (pyproject:163) so both backend and bot trees exercised the
   extraction. See §Runtime Verification.
4. **Test-audit block findings** (`docs/99-agent/test-audit-block-{a..g}-findings.md`,
   untracked) are **static-analysis only** ("bash blocked globally") and pre-date the
   B–E extraction. Several cite mock-target / patch-path fragility that the extraction
   may have invalidated (e.g. `test_edit.py` patches
   `apps.ads.views.edit.auto_moderate` — still valid today since `edit.py:25` still
   imports it, but reactivation now also calls `submit_ad`). Reconcile before merging.

## Runtime verification

- **Lint gate (Block A):** `uv run ruff check src/backend src/telegram_bot` →
  `All checks passed!` (ruff `select` includes `"G"`, pyproject:124). ✅
- **Test gate:** compose `test` service (`--env-file .env.test`,
  `PYTEST_SKIP_MARKERS=seed`) against the running `mko-bazuna-test-db-1`
  (postgres:18-alpine, healthy). `pyproject.toml:163` →
  `testpaths = ["src/backend", "src/telegram_bot"]` (both test trees collected).
  ```
  1576 passed, 371 warnings in 104.74s (0:01:44)   — 0 failed, 0 errors
  ```
  Modules exercising the B–E refactor that collected & passed (per warnings summary):
  `test_edit.py`, `test_search_view.py`, `test_listings_context.py`,
  `test_listings_sort.py`, `test_i18n_completeness.py`,
  `test_multi_lang_translation.py`, `test_ad_create.py`, `test_create_draft_ad.py`,
  `test_contact_us.py`, `test_unsubscribe.py` → Blocks B, C, D, E gates satisfied. ✅
- **Typecheck gate:** `basedpyright` not executed (QLT-007 still open). ⏳
- **Noise (non-blocking):** 6 Django security WARNINGS (W008/W009/W012/W016/W018/W021)
  — pre-existing test env (`DEBUG=True`, test `SECRET_KEY`); plus a
  `CacheKeyWarning` in `test_detail_context.py` from a `MagicMock`-keyed cache
  assertion (pre-existing; Block A test-audit §5). Not failures.
