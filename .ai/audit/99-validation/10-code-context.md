# Code Context — Code Quality Findings (Phase 10 Audit)

## Scope

Validated audit report: `.ai/audit/99-validation/10-code-quality-validated-findings.md` (7 findings, QLT-001–QLT-007) + new prerequisite finding FQ-001.

**Verification method:** live `uv run ruff check --select G004`, source reads via `read`/`grep` tools, `git log`, and `Get-Content -ReadCount 0` line counting (PowerShell `Measure-Object -Line` was found unreliable for these files — it under-reported `ad_create.py` as 896; the true count is 1393 per both the `read` tool and `-ReadCount 0`).

**Two-process model:** web (gunicorn sync WSGI, Django 5.2) + bot (aiogram 3.x, `django.setup()` + shared ORM). Two DB-backed processes sharing ORM models — extraction of bot data helpers must respect the bot→backend direction (backend never imports the bot).

## Finding Status (verified against current code + git log)

| ID | Severity | Type | Status | Current Action |
|----|----------|------|--------|----------------|
| QLT-001 | HIGH | BEST-PRACTICE | Validated | **PARTIAL** — Stage 1 (submit_ad extraction) DONE; 15 inline sync_to_async ORM helpers remain |
| QLT-002 | HIGH | BEST-PRACTICE | Validated (narrower) | **NEEDS ACTION** — all token pairs still raw literals; callbacks.py absent |
| QLT-003 | MEDIUM | BEST-PRACTICE | Validated | **NEEDS ACTION** — listings() still fat; search.py still duplicates |
| QLT-004 | MEDIUM | BEST-PRACTICE | Validated | **NEEDS ACTION** — edit POST still unvalidated except reactivation |
| QLT-005 | MEDIUM | BEST-PRACTICE | Validated (+ FQ-001) | **NEEDS ACTION** — unwrapped strings; Russian msgids; gate template-only |
| QLT-006 | LOW | BEST-PRACTICE | Validated (count drift corrected) | **NEEDS ACTION** — G004 not enabled; live count 48 (audit: 49) |
| QLT-007 | LOW | BEST-PRACTICE | Validated (count nuance) | **NEEDS ACTION** — 9 bare annotations; Cyrillic comment |
| FQ-001 | MEDIUM | SPEC-DEVIATION | Validated (new) | **NEEDS ACTION** (prerequisite of QLT-005) |

---

## QLT-001 — Bot `ad_create.py` (1393 lines) god-module

**File:** `src/telegram_bot/handlers/ad_create.py` — 1393 lines (audit: 1311; +82 drift).

### What is already implemented
- **Stage 1 DONE** — `submit_ad` + `SubmitAdInput` extracted to `apps/ads/services/submission.py` (commit `bb2ccdb refactor(qlt-001): extract inert submission.py`). Confirmed:
  - `ad_create.py:25` → `from apps.ads.services.submission import SubmitAdInput, submit_ad`
  - `ad_create.py:841` → `is_valid, errors = await sync_to_async(submit_ad)(...)`
  - `submit_ad` now invoked from both bot (`:841`, via `sync_to_async`) and web edit reactivation (`edit.py:178`, sync). Commit log confirms QLT-001 follow-ups: `9bc5c4c` (rewire process_preview → submit_ad, delete update_ad_and_moderate), `a4586c4` (route ad_edit reactivation through submit_ad). Per `git log`, `ad_create.py` is the most-churned handler file.
- `telegram_bot/services/` contains `rate_limit.py` + `__init__.py` only (no `ad_data.py` yet).

### What STILL matches the plan (not done)
- **15 sync_to_async ORM helpers still inlined** in the handler (audit said 14). **Drift: one new helper `_get_ad_status` (line 926) was added after the audit.** Helper section now `# Helper functions using sync_to_async` at **line 889** (audit: 859; +30 shift), running 889–1393.
  - Full list of sync_to_async-wrapped ORM helpers:
    | # | Function | Line | Notes |
    |---|----------|------|-------|
    | 1 | `create_draft_ad` | 892 | ORM (Ad DRAFT upsert) |
    | 2 | `_get_ad_status` | 926 | **NEW** (not in audit's 14) — ORM (Ad read) |
    | 3 | `delete_draft` | 948 | ORM |
    | 4 | `search_categories` | 973 | ORM (Category) |
    | 5 | `get_city_by_name` | 988 | ORM (City) |
    | 6 | `get_all_cities` | 1005 | ORM (City) |
    | 7 | `get_category` | 1087 | ORM |
    | 8 | `get_city` | 1104 | ORM |
    | 9 | `get_resolved_purposes` | 1169 | sync_to_async BUT delegates to `CategoryLookupResolver` |
    | 10 | `get_resolved_features` | 1194 | delegates (same) |
    | 11 | `get_resolved_conditions` | 1219 | delegates (same) |
    | 12 | `get_default_purpose` | 1239 | ORM |
    | 13 | `get_lookup_item_by_slug` | 1263 | ORM |
    | 14 | `get_lookup_item` | 1282 | ORM |
    | 15 | `get_feature_names` | 1304 | ORM |
  - **Nuance not caught by audit:** `download_photo` (1018) and `save_photo` (1032) do NOT use `sync_to_async` — `download_photo` is natively `await bot.download()`; `save_photo` uses `asyncio.to_thread` (1077). `translate_all_languages` (1121) uses `asyncio.gather`. The audit's "media helpers (download_photo, save_photo)" as sync_to_async was slightly inaccurate; they are still inlined non-ORM helpers nonetheless.
- **Keyboard builders still inlined** in helper section: `build_purpose_keyboard` (1330), `build_condition_keyboard` (1354), `build_feature_keyboard` (1368); plus `build_currency_keyboard` (526) sitting outside the helper section (near the price handler).
- **`except ValueError, Exception:` still present** at **line 620** (audit: 600; +20 shift). Verified parses as implicit tuple; redundant since `Exception ⊃ ValueError`.

### Affected test files (import coupling)
11 test files import/ patch handlers from `ad_create` — **the blockiest risk for the QLT-001 extraction**:
- `test_ad_create.py` — imports `create_draft_ad, process_preview, cmd_cancel, delete_draft, process_photos, translate_all_languages`; patches `telegram_bot.handlers.ad_create.download_photo`, `.save_photo`, `.validate_photo`, `.check_upload_rate_limit`, `.delete_photo`, `.translate_all_languages`.
- `test_ad_create_condition.py` — imports `AdCreateForm, process_condition, build_feature_keyboard`.
- `test_multi_lang_translation.py` — imports `translate_all_languages`.
- `test_price_payload.py` — imports `AdCreateForm, process_price_currency`.
- `test_create_draft_ad.py` — imports `create_draft_ad, delete_draft`.
- `test_site_name_greeting.py` — imports `cmd_post`; patches `ad_create.create_draft_ad`, `ad_create.get_site_name_async`.
- `test_save_photo_integration.py` — imports `create_draft_ad`.

**Risk:** Moving the 15 helpers into `telegram_bot/services/ad_data.py` breaks 7 test files' direct imports + 5 patch targets (`mock.patch("telegram_bot.handlers.ad_create.X")`) unless either (a) re-exports are left in `ad_create.py`, or (b) every test import/patch path is updated. `test_site_name_greeting.py`'s patch of `get_site_name_async` is a false positive in the audit's concern it patches an unrelated symbol.

### Discrepancies vs audit
- Audit helper-section start `859-1311` → **now 889-1393**. All audit line citations for this file are **+20 to +78 stale** (early handlers +20; helper-section keyboard builders +44–78).
- Audit counted "14 sync_to_async ORM helpers" → **now 15** (`_get_ad_status` added post-audit).
- Audit cited orphan `telegram_bot/services/__pycache__/media.cpython-314.pyc` → **already absent** (the `__pycache__` now holds only `__init__` + `rate_limit`). The stale-bytecode hazard is resolved; no pruning needed.

---

## QLT-002 — Callback-data tokens & locale list are raw string literals

### Current state (confirmed, all still raw literals)
**Token pairs still present at BOTH filter and builder sites** (line numbers shifted +20 on filters, +44–78 on builders vs audit):

| Token | Filter site | Builder site(s) | Audit cited |
|-------|-------------|-----------------|-------------|
| `purpose:` | 320 `c.data.startswith("purpose:")` | 1347 `f"purpose:{purpose.slug}"` | 300 / 1265 |
| `condition:` | 350 `startswith("condition:")` | 1363 `f"condition:{condition.slug}"` | 330 / 1281 |
| `feature:` | 396 `startswith("feature:")` | 1387 `f"feature:{feature.id}"` | 376 / 1305 |
| `price_currency:` | 568 `startswith("price_currency:")` | 531/533/535 `"price_currency:EUR"` etc. | 548 / 511-515 |
| `price_free` | 556 `callback.data == "price_free"` | 537 `callback_data="price_free"` | 536 / 517 |
| `features_done` | 385 `callback.data == "features_done"` | 1389 `callback_data="features_done"` | 365 / 1389 |

**New drift not in audit:** `price_currency:` builder at 531/533/535 are **plain string literals** (not f-strings), and line 569 does a third raw copy via `callback.data.replace("price_currency:", "")` — a 3-way duplication the audit under-counted. `price_free` and `features_done` filters use `==`, not `startswith`, so the "filter/builder" frame holds but the comparison differs.

### Already centralized (audit's scope-narrowing confirmed)
- `language.py:27` → `LANG_CALLBACK_PREFIX = "lang:"`; reused at filter `language.py:50` (`F.data.startswith(LANG_CALLBACK_PREFIX)`) and builder `language.py:98` (`f"{LANG_CALLBACK_PREFIX}{locale.value}"`).
- `alerts.py:31` → `UNSUB_ON_PREFIX = "unsub_on:"`; reused at `alerts.py:141` (filter) and `alerts.py:162` (`f"{UNSUB_ON_PREFIX}{token}"`).
- `alerts.py:21` → `from apps.search.services.immediate_alerts import UNSUB_CALLBACK_PREFIX`; used at `alerts.py:103` (filter).

### Locale list drift
- `ad_create.py:832, 836` → `translate_all_languages(original_title, ["ru", "bs", "en"])` (audit: 804/808; +28 shift).
- `ad_create.py:27` → `from apps.core.enums import AdStatus, LanguageLocale` — `LanguageLocale` IS imported but **only used** for `LanguageLocale.from_code` (850) and `LanguageLocale.BOSNIAN` (852); `.values()` is never called. Confirmed genuine unused-enum violation.
- `core/enums.py:190` → `class LanguageLocale(StrEnum)`; `:198` → `def values(cls) -> list[str]`. Confirmed method exists.

### login.py drift
- `login.py:62` → `callback_data="contact_us"` (audit: 61; +1 shift), duplicating `contact.py:35` → `CONTACT_US_CALLBACK: Final[str] = "contact_us"` (which is itself used at `contact.py:57, 162`).

### `callbacks.py` does NOT exist
- `src/telegram_bot/schemas/` holds only `__init__.py`, `message_payloads.py`, `saved_search.py`. No `callbacks.py`. The recommendation targets a genuinely new module.

### Affected test files
- `test_ad_create_condition.py` — imports `build_feature_keyboard` (uses `feature:` token).
- `test_ad_create.py`, `test_multi_lang_translation.py` — exercise `translate_all_languages` (the `["ru","bs","en"]` literal).
- No test directly asserts on `purpose:`/`condition:`/`feature:`/`price_free`/`features_done`/`contact_us` literals (filters are matched at runtime via `lambda c: c.data.startswith(...)`).

---

## QLT-003 — Web `listings.py` (522 lines) fat view

**File:** `src/backend/apps/ads/views/listings.py` — 522 lines (audit: 508; +14 drift).

### Current state (confirmed, still fat)
- `listings()` function now starts at **line 214** (audit: 201; +13 shift). Body runs 214–~474 (Paginator at 453, context assembly 466–474), ~260 lines. Module total 522.
- Inline filter/sort/pagination confirmed at current lines:
  - `category.get_descendants(include_self=True)` — 302 (audit 288)
  - `suggest_city` did-you-mean — 311-330
  - manual `int(min_price)`/`Decimal` coercion swallowing `ValueError`/`TypeError` with bare `pass` — 338-364 (audit 338-364)
  - `ads.filter(listing_purpose__slug=...)` — 384 (audit 384)
  - `ads.filter(features__slug=slug)` — 401 (audit 401)
  - `if/elif` sort against `AdSort` — 415-427
  - `annotate_favorites` — 431-435
  - `Paginator(ads, PER_PAGE)` — 453 (audit 439)
  - context assembly — 466-474
- `listings.py` has **0 G004 hits** (confirmed — it logs plain `logger.warning("...")`/`logger.info("...")` literals). The audit's corrected file set stands.

### search.py reimplementations confirmed (parallel filter logic)
`src/backend/apps/search/views/search.py` (374 lines) re-implements the same predicates (audit cited 78/105/131/147/255/257; **current lines shifted +1**):
- `get_descendants(include_self=True)` — 79 (and 203)
- `price_normalized_eur__gte=int(min_price)` — 106 (audit 105)
- `price_normalized_eur__lte=int(max_price)` — 111
- `listing_purpose__slug` — 132 (audit 131)
- `features__slug=slug` — 148 (audit 147)
- `order_by(F("price_normalized_eur").asc(...))` / `.desc(...)` — 256/258 (audit 255/257)

### Thin-service precedent confirmed
- `apps/search/services/alert_query.py` — 228 lines, contains `get_descendants` + `price_normalized_eur__gte` filters (the pattern QLT-003's recommendation says to mirror).

### Affected test files
- `apps/ads/tests/test_listings.py` (if it asserts on `listings()` output or inline filter behavior). The extraction to `ListingsQuery` must preserve the exact queryset/filter semantics or these tests break.

---

## QLT-004 — Web edit POST bypasses Pydantic

**File:** `src/backend/apps/ads/views/edit.py` — 355 lines (audit: ~334; +21 drift). Imports include `SubmitAdInput` already.

### Current state (confirmed, still bypassed except reactivation)
- `ad_edit` POST path:
  - Lines 134-137: reads `request.POST.get("title")`, `("description")`, `("price_amount")`, `("price_currency")` directly.
  - Lines 142-147: `price_amount_value = Decimal("0")` with silent `except Exception: price_amount_value = Decimal("0")` fallback to Free (audit cited 142-147 — unchanged).
  - Lines 149-159: currency coercion with `CurrencyCode()` + `except ValueError: pass` (audit 158-159 → now 158-159; `+0` — the surrounding comments shifted the block but the except lines held). **Currency-fallback-on-invalid semantics preserved** (audit's architectural note confirmed).
  - Reactivation branch at **line 178**: `passed, errors = submit_ad(SubmitAdInput(ad_id=ad_id, title_ru=new_title, ...))` — validates via Pydantic DTO (audit confirmed; unchanged).
  - Unvalidated `ad.save(update_fields=[...])` branches: 217-226 (text edit), 254-261 (price-only), 271-280 (else/other-status) — all still bypass any DTO (audit cited 217-226, 234-241, 253-261, 271-280).
- Helpers present (not previously cited by audit): `_text_fields_changed` and `_apply_price_change` are module-level private functions (def at top of grep output) — partial extraction already happened for price/text diffing, but the POST values themselves are still parsed ad-hoc, not via a DTO.

### Affected test files
- `apps/ads/tests/test_edit.py` — audit commit log shows `a4586c4 refactor(qlt-001): add test_edit.py baseline`. Any `AdEditInput` DTO refactor must preserve: (a) currency-fallback-on-invalid (lines 149-159), (b) unconditional title/description overwrite (214-215, 268-269 — a latent validation gap a DTO would surface), (c) the `auto_moderate` bool-branch (238) that renders `_("Ad failed moderation checks")`.

---

## QLT-005 — Bot i18n inconsistent

### Current state (confirmed)
**`alerts.py`** (247 lines) — imports lines 1-35, **no `gettext`/`_`** (imports: `logging, re, aiogram, sync_to_async, SavedSearch, UNSUB_CALLBACK_PREFIX`). Raw user-facing literals:
- English: 50 (`"Please login first with /start login_<token>"`), 57-58 (`"You have no saved searches.\n..."`), 62 (`"Your saved searches:"`), 64, 84 (`"...Reply with number to toggle, or /cancel to exit."`).
- Russian: 119 (`"Не удалось отключить уведомления"`), 127 (button `"Включить уведомления"`), 138 (`"Уведомления отключены"`), 153 (`"Не удалось включить уведомления"`), 161 (button `"🔕 Отключить этот поиск"`), 172 (`"Уведомления включены"`), 199 (`"Эта ссылка недействительна..."`), 203-204 (`"Уведомления отключены для этого сохранённого поиска..."` / `"Чтобы включить их снова, используйте /alerts."`).
- (Audit cited older lines 119/138/153/161/172/199/203-204 — all confirmed, shifted.)

**`ad_create.py`** — imports lines 10-47, **no `gettext`/`_`** (confirmed). Hardcoded Russian fallback at **line 167**: `"Top-level categories: Товары, Услуги, Недвижимость"` (audit: 147; +20 shift). Other bot messages throughout (e.g. 583, 867-869, 874-876, 886) are raw English literals — also unwrapped.

**`contact.py`** (284 lines) — imports `from django.utils.translation import gettext as _` (line 19). Uses **Russian as msgid** (Django convention violation):
- 200: `_("Ошибка: не удалось определить отправителя")` (audit: 175)
- 212: `_("объявление больше недоступно")` (audit: 175)
- 216: `_("продавец больше недоступен для связи")` (audit: 188)
- 235: `_("Ваш запрос отправлен продавцу анонимно. Ожидайте ответа в этом чате.")` (audit: 247 region)
- 284: `ANONYMOUS_BUYER_LABEL = _("Покупатель")` (audit: 247)
- 133: `_("Contact us")` — English msgid, OK (contrast).

**i18n completeness gate** — `apps/ads/tests/test_i18n_completeness.py`:
- `_collect_template_files()` (117-134): iterates `settings.TEMPLATES` DIRs, `rglob("*.html")`, excludes `admin/`, `analytics/moderation_dashboard.html`, `components/feature_tag.html` (DB-based i18n, exempt). **Scans templates only — never `src/telegram_bot/**/*.py`**. Confirmed template-only by construction (audit's wording nuance confirmed).

### What is already implemented
- Nothing for bot i18n wrapping. `contact.py`/`login.py`/`language.py` are the ONLY bot files using `_()` (contact.py, login.py partially). `alerts.py` and `ad_create.py` have zero wrapping.

### Affected test files
- `test_multi_lang_translation.py` — imports `translate_all_languages`; the only bot test touching translation. After adding `_()` + FQ-001 activation, this test must assert per-user locale rendering.
- `test_i18n_completeness.py` — gate must be extended to scan `telegram_bot/handlers/` for bare user-facing literals and non-English msgids (audit's advisory recommendation).

---

## QLT-006 — Pervasive f-string logging (G004 not enforced)

### Current state (confirmed via live `ruff --select G004`)
- `pyproject.toml:118-124` → `select = ["E","F","I","B","UP"]`, `ignore = ["E501"]`. **`G` is absent** → G004 unguarded (audit confirmed; unchanged).
- **LIVE total: 48 G004 hits** (audit + cache `.cache/ruff_g004.txt` said 49; **-1 drift since audit**).
- **Per-file (current):**
  | File | Hits |
  |------|------|
  | `ads/views/edit.py` | **8** |
  | `users/views/consent.py` | **8** |
  | `moderation/services/moderation_log.py` | 6 |
  | `media/services/filesystem.py` | 5 |
  | `users/services/account_state.py` | 5 |
  | `users/services/deletion.py` | 5 |
  | `moderation/admin_actions.py` | 4 |
  | `moderation/views/review.py` | 3 |
  | `ads/views/delete.py` | 2 |
  | `telegram_bot/handlers/ad_create.py` | 2 |
  | `ads/views/listings.py` | 0 |
  | **Total** | **48** |
- **edit.py G004 exact current lines: 108, 230, 262, 281, 306, 314, 340, 353.** The audit's QLT-006 validation note cited "108, 230, 242, 261, 286, 294, 320, 333" — **only 108 and 230 still match; the other 6 are stale by +14 to +22** (edit.py grew from audit's ~334 to 355 lines). Anyone using the audit's edit.py line citations will look ~20 lines too early.
- ad_create.py G004 hits: `save_photo` warning at **1082** (`logger.warning(f"Storage key collision: {key}, regenerating")`), `download_photo` error at **1027** (`logger.error(f"Failed to download photo {file_id}: {e}")`).
- `%s` lazy-format contrast still confirmed: `core/services/contact.py` (logger.info("...%s", ...)).

### Drift / risk
- **Default `ruff check src/backend src/telegram_bot` is NOT clean** — reports `Found 2 errors`, both `I001` (import block un-sorted/un-formatted) in two auto-generated migrations:
  - `apps/ads/migrations/0005_remove_ad_ix_ads_delete_sweep_ad_ix_ads_delete_sweep.py:3`
  - `apps/ads/migrations/0006_ad_ix_ads_draft_sweep.py:3`
  - These migrations are from the DB-001/DB-002 indexing work (commit `750edbe`). **Audit V-01 claimed "PASS (clean)" — the gate has deteriorated post-audit.** Enabling `G004` will surface the 48 hits; these 2 I001 hits are a separate pre-existing gate failure that will block `ruff check --fix` until resolved.

---

## QLT-007 — Bare `dict`/`list`/`set` annotations; Cyrillic comment

### Current state (confirmed, all 9 still bare — audit count correct)
Bare annotations now at **shifted lines** (audit's 721/767/1087/1112/1137/1157/1249/1272/1287 → current):

| Audit line | Current line | Signature |
|-----------|--------------|-----------|
| 721 | **749** | `show_preview(message, data: dict)` |
| 767 | **795** | `_format_preview_price(data: dict)` |
| 1087 | **1169** | `get_resolved_purposes(...) -> list` |
| 1112 | **1194** | `get_resolved_features(...) -> list` |
| 1137 | **1219** | `get_resolved_conditions(...) -> list` |
| 1157 | **1239** | `get_default_purpose(..., purposes: list)` |
| 1249 | **1331** | `build_purpose_keyboard(..., purposes: list)` |
| 1272 | **1354** | `build_condition_keyboard(conditions: list)` |
| 1287 | **1369** | `build_feature_keyboard(features: list, selected_ids: set)` |

- Audit's "8 signatures" enumeration omitted `build_purpose_keyboard` (1249); the validation note reconciled this to "9 locations." All 9 confirmed bare. Note the audit's line list cited 9 lines but the enumerated signatures listed 8 — the validation note correctly flagged `build_purpose_keyboard` as the 9th.
- `translate_all_languages` (1121-1123) is **NOT bare** — uses parameterized `target_locales: list[str]` / `-> dict[str, str]`. (Audit did not claim it was bare; this confirms the audit's line-citations 1112/1137 refer to `get_resolved_features`/`get_resolved_conditions`, not translate_all_languages.)
- Cyrillic comment confirmed at `alerts.py:30`: `# Re-enable callback prefix (complements the "Отключить" button).`

### Affected test files
- `test_ad_create.py`, `test_ad_create_condition.py` — import `build_feature_keyboard` (signature `features: list, selected_ids: set`), which is in the same helper section targeted by QLT-001 extraction. Audit's note to fold QLT-007 parameterizing into the QLT-001 pass is correct — avoids duplicate churn.

---

## FQ-001 — Bot never activates per-user locale (prerequisite of QLT-005)

### Current state (confirmed — still a genuine gap)
- **Zero `translation.activate` / `translation.override` calls in `src/telegram_bot/`** (grep across the whole tree: no matches).
- `language.py` (230 lines) persists the user's choice but never activates it:
  - `language.py:42` → `current_lang = await _get_user_language(user_id)` (READS the stored code, then... nothing).
  - `language.py:106` → `def _get_user_language(user_id) -> str` (reads `User.telegram_language`, line 118).
  - `language.py:116` → `def _set_user_language(...)` (writes `User.telegram_language`, line 118).
  - The read value at line 42 is **not** piped into any `translation.activate()`.
- **Bot middleware registration (`main.py`, 91 lines, read in full):**
  - `main.py:22-26` imports `AccountStateMiddleware, DatabaseConnectionMiddleware, UpdateIdDedupMiddleware` (+ `LivenessMiddleware` from lifecycle).
  - `main.py:57-63` registers: `UpdateIdDedupMiddleware`, `LivenessMiddleware`, `AccountStateMiddleware` (all `dp.update.middleware`), `DatabaseConnectionMiddleware` as `outer_middleware`. **No locale middleware.**
  - Routers included (75-80): `login_router, ad_create_router, alerts_router, ad_copy_router, language_router, contact_router`.
- **Web activation exists (web-only):** `core/middleware/language.py:141` → `translation.activate(lang)` (inside `_set_language_code`, called by `LanguagePreMiddleware`). Confirmed web-only — the bot imports nothing from this module.
- **`conftest.py` `dp` fixture** (`src/telegram_bot/tests/conftest.py:44-83`) mirrors `main.py`'s middleware stack (lines 77-81): `UpdateIdDedupMiddleware`, `LivenessMiddleware`, `AccountStateMiddleware`, `DatabaseConnectionMiddleware`. **No locale middleware** in tests either. **DISCREPANCY:** the fixture omits `ad_copy_router` and `language_router` that `main.py` includes (lines 78-80) — a test/production wiring drift that also means any new i18n middleware added to `main.py` would NOT be exercised by the `dp` fixture unless explicitly added to `conftest.py:77-81`.

### Wiring implication for the fix
A bot-side per-user locale activator must be registered on `dp.update.middleware` in **two** places:
1. `main.py` — add a new middleware class import (line 22-26) + registration (after line 62, before/around `AccountStateMiddleware`).
2. `telegram_bot/tests/conftest.py` `dp` fixture (line 77-81) — same registration, so bot i18n behavior is testable.

### Affected test files
- `test_multi_lang_translation.py` — the only existing bot i18n test; mocks the content-translation path (`override_settings`), not activation. Must be extended to assert per-user `translation.activate` is invoked and renders in the user's `telegram_language`.
- All bot handler tests (via the `dp` fixture) will exercise the new middleware once added to `conftest.py`.

---

## Cross-Finding: Shared `ad_create.py` remediation surface (rollout sequencing)

The audit's dependency chain (lines 367-370) is **current and accurate**:
1. **QLT-001 → QLT-002:** keyboard builders (`build_purpose/condition/feature/currency_keyboard`) are at 526/1330/1354/1368 — extracting them (QLT-001) without centralizing their tokens (QLT-002) relocates raw literals into `services/ad_data.py`. → Introduce `BotCallbackPrefix` StrEnum **within** the QLT-001 keyboard-builder extraction.
2. **QLT-002 → QLT-005:** the same `build_*` keyboard functions are where button **labels** would be wrapped in `_()`. Do i18n wrapping in the same pass.
3. **FQ-001 → QLT-005:** wrapping is a no-op without per-user `translation.activate()`.

**Additional coupling discovered during verification (beyond the audit's stated chain):** `build_currency_keyboard` (526) sits OUTSIDE the helper section (near `process_price_currency`, line 547) — it must be co-relocated with the inline `price_currency:`/`price_free` filter+builder extraction, or the token-centralization pass will miss its literals at 531/533/535/537/569.

## Discrepancies vs. Validated Findings Doc (summary)

| # | Audit claim | Current reality | Impact |
|---|-------------|-----------------|--------|
| 1 | QLT-001 helper section `859-1311`, file 1311 lines, 14 helpers | Helper section `889-1393`, file **1393** lines, **15** helpers (`_get_ad_status` added) | Audit line citations all +20 to +78 stale; count +1 |
| 2 | QLT-006 edit.py G004 at "108, 230, 242, 261, 286, 294, 320, 333" | Actual: **108, 230, 262, 281, 306, 314, 340, 353** | 6 of 8 citations stale (+14 to +22) |
| 3 | QLT-006 "Found 49 errors" | **Live: 48 errors** (-1 since audit) | One G004 fix landed post-audit |
| 4 | Audit V-01: `ruff check src/backend src/telegram_bot` → "PASS (clean)" | **Now: Found 2 errors** (I001 in migrations 0005, 0006) | Default gate deteriorated; blocks `ruff --fix` rollout |
| 5 | Orphan `telegram_bot/services/__pycache__/media.cpython-314.pyc` | **Already absent** | Stale-bytecode hazard resolved; no pruning needed |
| 6 | QLT-002 `price_currency:` builder = 511-515, price_free = 536/517 | Builder is **plain literals at 531/533/535** + `.replace("price_currency:", "")` at 569 (3-way dup) | Slightly worse drift than audit stated |
| 7 | QLT-005 `contact.py:175,179,188,247` Russian msgids | Shifted to **200, 212, 216, 235, 284** | Audit citations stale (+23 to +37) |
| 8 | QLT-001 "media helpers (download_photo, save_photo)" as sync_to_async | `download_photo` uses `await bot.download`; `save_photo` uses `asyncio.to_thread` | Mislabeling; they're still inlined, just not sync_to_async |
| 9 | conftest `dp` fixture mirrors main.py routers | Fixture OMITS `ad_copy_router` + `language_router` (main includes them) | Test/prod wiring drift; new middleware must hit both files |
| 10 | `pyproject.toml:118-124` (ruff select) | Now `118-124` still (select at 118-124) — **matches**; E501 ignore at 127 | No drift in config location |

## Affected Files & Test Inventory (consolidated)

**Production files requiring change per the plan:**
- `src/telegram_bot/handlers/ad_create.py` — QLT-001 (extract 15 helpers + 4 keyboards), QLT-002 (tokens), QLT-005 (wrap ~10 messages), QLT-006 (2 G004), QLT-007 (9 annotations)
- `src/telegram_bot/handlers/alerts.py` — QLT-005 (wrap ~13 Russian + 5 English), QLT-007 (Cyrillic comment)
- `src/telegram_bot/handlers/contact.py` — QLT-005 (5 Russian msgids → English)
- `src/telegram_bot/handlers/login.py:62` — QLT-002 (import CONTACT_US_CALLBACK)
- `src/telegram_bot/schemas/callbacks.py` — QLT-002 (NEW)
- `src/telegram_bot/services/ad_data.py` — QLT-001 (NEW extraction target)
- `src/telegram_bot/main.py` + `src/telegram_bot/tests/conftest.py` — FQ-001 (new locale middleware both places)
- `src/backend/apps/ads/views/edit.py` — QLT-004 (AdEditInput DTO), QLT-006 (8 G004 @ 108,230,262,281,306,314,340,353)
- `src/backend/apps/ads/views/listings.py` — QLT-003 (ListingsQuery service)
- `src/backend/apps/search/views/search.py` — QLT-003 (share query object)
- `src/backend/apps/users/views/consent.py` — QLT-006 (8 G004)
- `src/backend/apps/...` (6 more files) — QLT-006 (remaining 28 G004 hits)
- `pyproject.toml` — QLT-006 (add `G` to select)
- `apps/ads/tests/test_i18n_completeness.py` — QLT-005 (extend gate to bot .py)

**Test files affected by QLT-001 extraction (import/patch coupling):**
`test_ad_create.py`, `test_ad_create_condition.py`, `test_multi_lang_translation.py`, `test_price_payload.py`, `test_create_draft_ad.py`, `test_site_name_greeting.py`, `test_save_photo_integration.py` — 7 files, ~30 import/patch sites against `telegram_bot.handlers.ad_create.*` symbols (`create_draft_ad`, `delete_draft`, `process_photos`, `process_preview`, `cmd_cancel`, `cmd_post`, `build_feature_keyboard`, `translate_all_languages`, `AdCreateForm`, `process_price_currency`, `process_condition` + patches on `download_photo`/`save_photo`/`validate_photo`/`check_upload_rate_limit`/`delete_photo`/`get_site_name_async`).

**Test files for QLT-005/FQ-001:** `test_multi_lang_translation.py`, `test_i18n_completeness.py`, plus the `dp` fixture in `conftest.py`.

## Rollout-safety notes
- QLT-004 currency-fallback-on-invalid (edit.py:149-159) and unconditional title/description overwrite (214-215, 268-269) are undocumented edge semantics — `AdEditInput` must model them or `test_edit.py` regresses.
- QLT-001 extraction direction (bot→backend) must not create an import cycle: backend apps must not import `telegram_bot`.
- The 2 I001 migration errors (Discrepancy #4) mean the **default** `ruff check` gate is not clean — enabling `G004` and running `ruff check --fix` will auto-resolve both the G004 hits and these I001 hits (the `I` rule is already enabled, so `--fix` covers both). They are a separate pre-existing gate failure, not a blocker, but contradict the audit's V-01 "PASS (clean)" claim.
- FQ-001 middleware must be added under `dp.update.middleware` (so it wraps both Message and CallbackQuery) in both `main.py:57-63` and `conftest.py:77-81`.
