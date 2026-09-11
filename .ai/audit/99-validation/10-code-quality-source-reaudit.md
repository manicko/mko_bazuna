---
name: 10-code-quality-source-reaudit
phase: code-quality
template: .ai/audit/templates/audit-findings.md
status: complete
validated: no
auditor: auditor
---

# Source Audit — Code-Quality Findings (QLT-001–005) Re-Validation Against Current Source

**Audit scope:** Inspect the current (HEAD `15483f4`, 2026-09-11 10:54) source code
for the 5 validated code-quality findings documented in
`.ai/audit/99-validation/10-code-quality-validated-findings.md` (validator: 2026-09-05/06).

**Key context — codebase evolution since validation:** The validated findings were
frozen on **2026-09-05/06** (findings-file commit `e7ce009`). Between then and the
current HEAD there were **10 commits**, including:

| Commit | Date | Impact on findings |
|--------|------|--------------------|
| `5b80f7b` — "fix(analytics): extract event recording from views into service layer" | Sep 8 | **QLT-003 partially implemented** — created `core/services/analytics.py` + `record_event`, wired into `listings.py` and `search.py`, added `test_analytics_service.py` |
| `7f5f067` — "fix(ads): DB-003 select_for_update on ad_edit/archive/reactivate fetches" | Sep 8 | **QLT-004**: added 3 new `pyright: ignore` sites in `edit.py` |
| `1d7aa1c` — "fix(moderation): DB-003 select_for_update on bulk_approve/reject/delete loops" | Sep 8 | **QLT-004**: added 3 new `pyright: ignore` sites in `admin_actions.py` |
| `923bd35` — "fix(moderation): DB-003 select_for_update on approve/reject Ad fetches" | Sep 8 | **QLT-004**: added 2 new `pyright: ignore` sites in `review.py` |
| `43e75f0` — "feat: add CATALOG_LOAD advisory lock for catalog builder" | Sep 9 | **QLT-004**: added 1 new `pyright: ignore` site in `builder.py` |
| `bad66e3` — "i18n(pc-002): wrap bot handler strings in gettext" | Sep 9 | **QLT-003/QLT-004**: shifted `login.py` line numbers by +18 |
| `984bd13` — "chore(imports): fix ruff isort config and auto-fix all 178 I001 violations" | Sep 10 | **All findings**: shifted line numbers across all files via import reordering |
| `9145109` — "fix(bot): fix ruff format and import sort issues in ad_create handler" | Sep 10 | **QLT-001**: shifted `ad_create.py` line numbers |
| `93604c8` — "fix(ext-001b): add bounded retry with backoff in translate_text..." | Sep 10 | **QLT-001**: added lines to `ad_create.py` (file grew 1506→1512) |
| `5fad588` — "block 3 implement" | Sep 6 | `contact_rate_limit.py` created in `core/services/` (not mentioned in findings) |

**Conclusion:** Many validated findings are accurate **at the validation date** but stale
against the current source. The isort auto-fix (Sep 10) alone shifted line numbers
systematically across all files. QLT-003's core recommendation was already implemented
on Sep 8. QLT-004's suppression count grew from 29 to 39.

---

## QLT-001: Bot ad-creation handler embeds business logic

**Severity:** HIGH · **Type:** BEST-PRACTICE · **Status:** Substantively correct; line references stale

### Verified Claims (SUBSTANTIVE finding still valid)

1. **No submission orchestrator exists.** `src/backend/apps/ads/services/` contains only:
   - `copy_service.py` (line 28 has its own `pyright: ignore`)
   - `images.py` (85 lines, `AdImageService.create_or_skip` confirmed at lines 44-85)
   - `__pycache__/`

   No `submission.py` or `AdService` exists anywhere in the codebase (grep for `submit_ad` / `class AdService` returned zero matches).

2. **`update_ad_and_moderate` embeds business logic.** Confirmed at line 1038 of `ad_create.py`.
   The async inner function `_update_and_moderate` (decorated with `@sync_to_async`) is
   defined at line 1073 and called at line 1237. It performs all of:
   - Currency coercion (lines 1101-1116): `isinstance(price_currency, CurrencyCode)` check,
     `ValueError` recovery → `None`
   - Price normalization (lines 1120-1132): `PriceNormalizer().normalize_to_eur(...)`,
     `except Exception:` swallows and nulls
   - Multi-language field assignment (lines 1134-1149): `title_bs`, `description_bs`,
     `title_en`, `description_en`, `original_language`
   - Filesystem thumbnail generation (lines 1156-1195): `ThumbnailService.generate_thumbnails`
     + `open(..., "rb")`, `except Exception:` swallows
   - `with transaction.atomic():` at line 1197 — wraps `ad.save()` + `AdImageService.create_or_skip`
     + `ad.transition_to(AdStatus.ON_MODERATION)`
   - `AdImageService.create_or_skip(...)` at lines 1209-1217
   - `ad.transition_to(AdStatus.ON_MODERATION)` at line 1221
   - `auto_moderate(ad)` called at line 1229 — **outside** the atomic block (confirmed)

3. **edit.py re-implements `transition_to(ON_MODERATION)` inline.** Confirmed at 3 sites:
   - Line 179: reactivation path (ARCHIVED → ON_MODERATION)
   - Line 217: text-edit path (PUBLISHED → ON_MODERATION)
   - Line 316: dedicated `ad_reactivate` view (ARCHIVED → ON_MODERATION)

4. **Currency-coercion divergence confirmed:**
   - Bot (`ad_create.py:1101-1116`): invalid currency → `None`
   - Web edit (`edit.py:151-158`): invalid `ValueError` → keeps existing currency

5. **`ads/tests/` has no `test_edit.py`.** Directory listing confirms only:
   `test_adimage_storage_keys.py`, `test_adimage_thumbnail_urls.py`, `test_ad_constraints.py`,
   `test_ad_detail_queries.py`, `test_ad_image_service.py`, `test_ad_lifecycle.py`,
   `test_ad_localization.py`, `test_auth_nav.py`, `test_breadcrumbs_render.py`,
   `test_catalog_filters.py`, `test_dashboard_stats.py`, `test_detail_context.py`,
   `test_detail_render.py`, `test_edit_views_locking.py`, `test_favorites.py`,
   `test_gallery_markup.py`, `test_i18n_*.py`, `test_listings_context.py`,
   `test_listings_sort.py`, `test_media_security.py`, `test_price_format.py`,
   `test_script_gating.py`, `test_search_triggers.py`, `test_transition_concurrency.py`.
   No `test_edit.py` exists. (The blocking precondition from the findings is still relevant.)

6. **No shared `AdService` / `submit_ad` exists anywhere.** Grep for `submit_ad|class AdService|def submit` returned zero matches across `src/`.

### Discrepancies in Line References

The findings cite line numbers that are all stale against the current source.
The code was modified post-validation (Sep 8 media relocation, Sep 10 isort fix, Sep 10
retry/backoff additions). The file grew from 1506 to **1512** lines (verified via Python
`splitlines()` on Sep 11).

| Finding claims | Actual current source | Delta |
|---|---|---|
| `update_ad_and_moderate` defined ~1042 | Line **1038** | −4 |
| Called in `process_preview` at 818 | Line **814** | −4 |
| Inner `_update_and_moderate` defined at 1077 | Line **1073** | −4 |
| Inner called at 1241 | Line **1237** | −4 |
| Currency coercion 1105–1120 | Lines **1101–1116** | −4 |
| PriceNormalizer 1124–1136 | Lines **1120–1132** | −4 |
| Multi-language 1140–1153 | Lines **1134–1149** | −4 |
| Thumbnail generation 1160–1199 | Lines **1156–1195** | −4 |
| `with transaction.atomic():` at 1201 | Line **1197** | −4 |
| AdImageService.create_or_skip 1212–1221 | Lines **1209–1217** | −4 |
| `ad.transition_to(ON_MODERATION)` at 1225 | Line **1221** | −4 |
| `auto_moderate(ad)` at 1233 | Line **1229** | −4 |
| `auto_moderate` called outside atomic | Confirmed: atomic at 1197 ends line 1221; `auto_moderate` at 1229 | — |

### Discrepancy: "4 call-site imports" claim

The findings state: *"update the 4 call-site imports (ad_create.py + test_save_photo_integration.py ×2 + test_ad_create.py via process_preview)"*.

Actual import/call sites of `update_ad_and_moderate`:

| Location | Line | Actual role |
|---|---|---|
| `telegram_bot/handlers/ad_create.py:814` | Call inside `process_preview` | Local definition (function is defined at 1038 in same file) — **not an import** |
| `telegram_bot/handlers/ad_create.py:1038` | `async def update_ad_and_moderate(` | Function definition |
| `telegram_bot/tests/test_save_photo_integration.py:72–75` | `from telegram_bot.handlers.ad_create import (... update_ad_and_moderate)` | Import #1 |
| `telegram_bot/tests/test_save_photo_integration.py:97` | Call | Call #1 |
| `telegram_bot/tests/test_save_photo_integration.py:121–124` | Same import | Import #2 |
| `telegram_bot/tests/test_save_photo_integration.py:148` | Call | Call #2 |
| `telegram_bot/tests/test_ad_create.py:8` | Docstring text mentioning `update_ad_and_moderate` | **Not an import** — it is a docstring reference only |

**Correction:** There are **2 actual import sites** (both in `test_save_photo_integration.py`),
not 4. `test_ad_create.py` imports `process_preview` and `create_draft_ad` (line 120), NOT
`update_ad_and_moderate`. The findings overcount by 2.

### Exact signatures and imports verified

```python
# ad_create.py:1038-1056
async def update_ad_and_moderate(
    ad_id: int,
    title_ru: str,
    desc_ru: str,
    category_id: int | None,
    city_id: int | None,
    price_amount: Decimal,
    price_currency: CurrencyCode | None,
    photos: list,
    user_id: int | None,
    title_bs: str = "",
    desc_bs: str = "",
    title_en: str = "",
    desc_en: str = "",
    original_language: str | None = None,
    listing_purpose_id: int | None = None,
    feature_ids: list[int] | None = None,
    listing_condition_id: int | None = None,
) -> tuple[bool, list[str]]:

# ad_create.py:814 (call site in process_preview)
is_valid, errors = await update_ad_and_moderate(

# test_save_photo_integration.py:72-75 (import block)
from telegram_bot.handlers.ad_create import (
    create_draft_ad,
    update_ad_and_moderate,
)

# test_save_photo_integration.py:97 (call)
passed, errors = await update_ad_and_moderate(

# test_ad_create.py:120 (actual import — does NOT import update_ad_and_moderate)
from telegram_bot.handlers.ad_create import create_draft_ad, process_preview

# edit.py:29-33 — currency coercion (keeps existing on ValueError)
def _apply_price_change(
    ad: Ad,
    price_amount: Decimal,
    price_currency: CurrencyCode | None,
) -> Ad:

# edit.py:179 — reactivation inline transition
ad.transition_to(AdStatus.ON_MODERATION)
```

### Rollout safety impact

The 4-stage rollout sequence (inert `submission.py` → bot rewire → test_edit.py → edit.py
migration) remains structurally valid. The **precondition** — create
`apps/ads/tests/test_edit.py` before rewiring `edit.py` — is unchanged and still blocking.
The line-number shifts do not affect the logic, only the line references cited in
communication.

---

## QLT-002: Autocomplete untyped dict[str, Any] + duplicate type/source keys

**Severity:** MEDIUM · **Type:** SPEC-DEVIATION · **Status:** Confirmed; line references stale

### Verified Claims (CONFIRMED accurate in substance)

1. **`autocomplete.py:9`** — `from typing import Any` — confirmed
2. **`autocomplete.py:60`** — `suggestions: list[dict[str, Any]] = []` — confirmed
3. **`autocomplete.py:71–72`** — duplicate keys:
   ```python
   "source": SearchSuggestionSource.USER_HISTORY.value,
   "type": SearchSuggestionSource.USER_HISTORY.value,
   ```
   Both keys emit the same enum value — confirmed verbatim.

4. **`entity_suggestions.py:38`** — `def get_entity_suggestions(...) -> list[dict]:` — confirmed
5. **`entity_suggestions.py:74–75`** — emits both `"source"` and `"type"` with
   `SearchSuggestionSource.CATEGORY.value` / `.CITY.value` — confirmed

6. **`popular_search.py:48`** — `def get_popular_suggestions(...) -> list[dict]:` — confirmed
7. **`popular_search.py:76–77`** — emits both `"source"` and `"type"` with
   `SearchSuggestionSource.POPULAR_SEARCH.value` — confirmed

8. **`core/enums.py`** — `SearchSuggestionSource` StrEnum confirmed at lines 181–187:
   ```python
   class SearchSuggestionSource(StrEnum):
       """Source types for search autocomplete suggestions."""
       USER_HISTORY = "user_history"
       POPULAR_SEARCH = "popular_search"
       CATEGORY = "category"
       CITY = "city"
   ```

9. **No Pydantic model** is imported or used in the autocomplete response path — confirmed
   (imports at `autocomplete.py:8–18` are only `logging`, `Any`, `HttpRequest`,
   `JsonResponse`, `SearchSuggestionSource`, and service functions)

10. **`test_autocomplete.py`** — 12+ assertions on `type`/`source` keys confirmed at
    actual lines: 134–135, 136, 221–222, 526–527, 538, 548, 553, 561, 574, 587, 599, 613.

### Discrepancies in Line References

| Findings cite | Actual line | Delta |
|---|---|---|
| `core/enums.py:179–185` (enum range) | Lines **181–187** | +2 |
| `header_catalog.html:312` (section loop) | Line **325** | +13 |
| `header_catalog.html:313` (s.type check) | Line **326** | +13 |
| `header_catalog.html:327` (escapeHtml fallback) | Line **340** | +13 |
| `autocomplete.py:79` (extend entity_suggestions) | Line **79** | 0 |
| `autocomplete.py:83` (extend popular) | Line **83** | 0 |
| `autocomplete.py:87–92` (dedup) | Lines **88–92** | +1 |
| `test_autocomplete.py:135–136` (source/type assert) | Lines **134–135** | −1 |
| `test_autocomplete.py:222` (user_history type) | Line **221** | −1 |
| `test_autocomplete.py:527–528` (source/type assert) | Lines **526–527** | −1 |

### Discrepancy: Template file path

The findings reference `header_catalog.html:312-327`. The actual file is at:
`src/backend/templates/components/header_catalog.html` (714 lines total).
The `components/` subdirectory is missing from the findings' path.

### Exact code at the consumers (verified)

```html
<!-- header_catalog.html:325 -->
['city', 'category', 'popular_search', 'user_history'].forEach(function (section) {
    var matches = suggestions.filter(function (s) { return s.type === section || s.source === section; });
<!-- header_catalog.html:340 -->
html += '<li><a href="#" data-suggestion-type="' + escapeHtml(s.type || s.source || '')
```

### Exact imports in autocomplete.py (confirmed)

```python
# autocomplete.py:8-18
import logging
from typing import Any

from django.http import HttpRequest, JsonResponse

from apps.core.enums import SearchSuggestionSource
from apps.core.utils.sanitize import sanitize_autocomplete_query
from apps.search.services.entity_suggestions import get_entity_suggestions
from apps.search.services.popular_search import get_popular_suggestions
from apps.search.services.rate_limit import rate_limit_check
from apps.search.services.search_history import get_user_search_history
```

### Rollout safety

The Pydantic DTO extraction remains safe (preserve all keys: `text`, `source`, `type`,
`slug`, `category_path`, `hit_count`). The `type` key must NOT be dropped without
coordinated frontend + test updates — confirmed it is consumed at
`header_catalog.html:326` and `header_catalog.html:340`, and asserted in 12+ test locations.

---

## QLT-003: Centralize analytics event recording

**Severity:** MEDIUM · **Type:** BEST-PRACTICE · **Status:** CRITICAL — recommendation already partially implemented post-validation

### Major Finding: QLT-003's core recommendation has already been implemented

**Commit `5b80f7b`** (2026-09-08 11:52:48) — "fix(analytics): extract event recording from views into service layer" — created exactly the file the findings recommend:

**File:** `src/backend/apps/core/services/analytics.py` (60 lines, read in full)

```python
# analytics.py:19-25
def record_event(
    event_type: AnalyticsEventType,
    user_id: int | None = None,
    *,
    ad_id: int | None = None,
    source: AdSource | None = None,
) -> AnalyticsEvent | None:
```

The function:
- Performs NO `transaction.atomic()` — transaction-transparent (line 45-51, bare `.objects.create()`)
- Catches all exceptions, logs at ERROR with traceback, returns `None` (line 52-60)
- Uses lazy `%s` logging (line 53-59)
- Is annotated with `# noqa: BLE001` rationale (line 52)

**This file did NOT exist at validation time (Sep 5).** The findings QLT-003 (line 231)
state: *"It does not exist yet — `apps/core/services/` contains only `contact.py`,
`site_config.py`, `translation.py`."* **This is no longer true.**

### Current state of `core/services/` directory

| File | Exists at validation? | Current status |
|------|----------------------|----------------|
| `contact.py` | Yes | Present (141 lines) |
| `site_config.py` | Yes | Present |
| `translation.py` | Yes | Present |
| `analytics.py` | **NO** | **Present (Sep 8) — `record_event` created** |
| `contact_rate_limit.py` | **NO** | **Present (Sep 6) — not mentioned in findings** |
| `__init__.py` | Yes | Does NOT export `record_event` or `contact_rate_limit` |

**`core/services/__init__.py`** (20 lines, read in full) exports from `.contact`,
`.site_config`, and `.translation` only. It does NOT export `record_event` or anything from
`.analytics` or `.contact_rate_limit`. This is an inconsistency: `record_contact_initiated`
and `record_contact_response` are exported from `__init__.py`, but `record_event` is not.

### `record_event` is already wired into production at 2 sites

The findings QLT-003 claims `listings.py:69` and `search.py:230` are **deferred to
ENT-007** with "bare create". This is **no longer true** — both already use `record_event`:

| Site | `record_event` call | Event type |
|------|---------------------|------------|
| `apps/ads/views/listings.py:67-71` | `record_event(AnalyticsEventType.AD_VIEWED, user_id=ad.user_id, ad_id=ad.id)` | AD_VIEWED |
| `apps/search/views/search.py:236-238` | `record_event(AnalyticsEventType.SEARCH_PERFORMED, user_id=...)` | SEARCH_PERFORMED |

**File path errors in the findings:**

| Findings cite | Actual path |
|---|---|
| `src/backend/apps/listings.py` | `src/backend/apps/ads/views/listings.py` |
| `src/backend/apps/search/services/search.py` | `src/backend/apps/search/views/search.py` |

### Remaining inline `AnalyticsEvent.objects.create` sites (not yet migrated)

The following 8 production sites still use direct `AnalyticsEvent.objects.create`
(verified via Python grep of exact line numbers):

| File | Line | Event type | Inside `atomic()`? | Uses `record_event`? |
|------|------|------------|--------------------|---------------------|
| `login.py` | 208 | REGISTRATION_CREATED | No (post-atomic) | No |
| `login.py` | 212 | — (logger, eager f-string) | No | No |
| `auto_moderation.py` | 239 | MODERATION_REJECTED | Yes (`atomic` at 236) | No |
| `auto_moderation.py` | 256 | AD_PUBLISHED | Yes (`atomic` at 253) | No |
| `auto_moderation.py` | 262 | MODERATION_APPROVED | Yes (`atomic` at 253) | No |
| `contact.py` | 114 | CONTACT_INITIATED | No | No |
| `contact.py` | 133 | CONTACT_RESPONSE | No | No |
| `analytics/trust_analytics.py` | 106 | (parameterized) | No | No |

### Batch site (deferred)

| File | Line | Pattern |
|------|------|---------|
| `search/management/commands/send_alerts.py` | 137 | `AnalyticsEvent.objects.bulk_create(analytics_events)` — batch, not `objects.create` |

### Existing test coverage for `record_event`

**`File:** `src/backend/apps/core/tests/test_analytics_service.py` (99 lines, 4 tests)

- `test_record_event_creates_row_with_all_fields` (line 27)
- `test_record_event_minimal_call` (line 48)
- `test_record_event_anonymous_user` (line 59)
- `test_record_event_failure_returns_none_and_logs` (line 74)

**No rollback-gate test exists.** The findings QLT-003 recommendation (line 241) states:
"Add rollback-gate test: assert `record_event` inside `auto_moderation` atomic is NOT
written when that transaction rolls back." No such test exists in
`test_analytics_service.py` or elsewhere.

### Discrepancies in Line References

All line references in the findings are stale by +5 to +18 lines due to the Sep 8–10
post-validation commits (additional imports, logger lines, etc.):

| Findings cite | Actual line | Delta |
|---|---|---|
| `login.py:190` (create) | Line **208** | +18 |
| `login.py:194` (logger) | Line **212** | +18 |
| `login.py:166,174` (pyright ignores) | Lines **184,192** | +18, +18 |
| `auto_moderation.py:234` (create) | Line **239** | +5 |
| `auto_moderation.py:251` (create) | Line **256** | +5 |
| `auto_moderation.py:257` (create) | Line **262** | +5 |
| `auto_moderation.py:231,248` (pyright) | Lines **236,253** | +5, +5 |
| `contact.py:114,133` | Lines **114,133** | 0 |
| `contact.py:118,137` (logger) | Lines **118,137** | 0 |
| `trust_analytics.py:106` | Line **106** | 0 |

### Discrepancy: `trust_analytics.py` path

Findings cite `src/backend/apps/trust/services/trust_analytics.py`. No `trust/services/`
directory exists. The file is at:
`src/backend/apps/analytics/services/trust_analytics.py` (confirmed via directory listing
and Python verification).

### Discrepancy: Site count

Findings QLT-003 claims "10 production writes" (9 single-row `create` + 1 `bulk_create`).
Current actual count (production, excluding inside `record_event` itself and test code):

- **Direct `AnalyticsEvent.objects.create`**: 7 sites (login.py:208, contact.py:114/133,
  auto_moderation.py:239/256/262, trust_analytics.py:106)
- **Inside `record_event`**: 1 site (analytics.py:46 — the implementation, not a caller)
- **Via `record_event`**: 2 sites (listings.py:67, search.py:236) — already migrated
- **`bulk_create`**: 1 site (send_alerts.py:137)
- **`bulk_create` in seed**: 1 site (seed_service.py:189 — excluded as seed code)

Total unique production call sites: **9** (vs findings' claim of 10). The findings' count
of 10 included `listings.py` and `search.py` as bare creates; they are now `record_event`
calls (counted as migrated, not as separate `objects.create` sites).

### Exact signatures and imports verified

```python
# login.py:208-209
from apps.analytics.models import AnalyticsEvent
...
AnalyticsEvent.objects.create(
    event_type=AnalyticsEventType.REGISTRATION_CREATED,
    user_id=user.id,
)

# login.py:212 (eager f-string — one of 38 site-wide per findings)
logger.info(f"Registration event recorded for user {user.id}")

# auto_moderation.py:239 (inside _fail_moderation, transaction.atomic at 236)
AnalyticsEvent.objects.create(
    event_type=AnalyticsEventType.MODERATION_REJECTED,
    user_id=ad.user_id,
    ad_id=ad.id,
)

# auto_moderation.py:256-262 (inside _pass_moderation, transaction.atomic at 253)
AnalyticsEvent.objects.create(
    event_type=AnalyticsEventType.AD_PUBLISHED,
    user_id=ad.user_id,
    ad_id=ad.id,
)
AnalyticsEvent.objects.create(
    event_type=AnalyticsEventType.MODERATION_APPROVED,
    user_id=ad.user_id,
    ad_id=ad.id,
)

# listsings.py:28, 67-71 (already migrated to record_event)
from apps.core.services.analytics import record_event
...
record_event(
    AnalyticsEventType.AD_VIEWED,
    user_id=ad.user_id,
    ad_id=ad.id,
)

# search/views/search.py:26, 236-238 (already migrated to record_event)
from apps.core.services.analytics import record_event
...
record_event(
    AnalyticsEventType.SEARCH_PERFORMED,
    user_id=request.user.id if request.user.is_authenticated else None,
)
```

### AnalyticsEventType enum (confirmed, 16 values)

From `core/enums.py:66-85`:
`REGISTRATION_CREATED`, `AD_PUBLISHED`, `SEARCH_PERFORMED`,
`CONTACT_INITIATED`, `SEARCH_ALERT_MATCHED`, `AD_VIEWED`,
`CONTACT_RESPONSE`, `SELLER_VERIFIED`, `TRUST_LEVEL_UPDATED`,
`MODERATION_APPROVED`, `MODERATION_REJECTED`, `MODERATION_FLAGGED`,
`DASHBOARD_VIEWED`, `AD_EDITED`, `AD_REACTIVATED`, `CONTACT_COMPLETED`,
`AD_REPORTED` (16 total).

### Contact.py pattern (canonical, confirmed)

Lines 114-118 and 133-137 use lazy `%s` logging:
```python
# contact.py:114-118
AnalyticsEvent.objects.create(
    event_type=AnalyticsEventType.CONTACT_INITIATED,
    user_id=user_id,
)
logger.info("Contact initiated event recorded for buyer %s", user_id)

# contact.py:133-137
AnalyticsEvent.objects.create(
    event_type=AnalyticsEventType.CONTACT_RESPONSE,
    user_id=user.id,
)
logger.info("Contact response event recorded for seller %s", user.id)
```

### Recommendation Update (due to partial implementation)

The original QLT-003 rollout plan needs revision. Steps 1–2 (create `analytics.py`,
migrate `contact.py`) are **already complete**. The remaining work:
- Migrate `login.py:208` → `record_event` (also fixes eager f-string at 212)
- Migrate `auto_moderation.py:239,256,262` → `record_event` (inside atomics at 236,253)
- Migrate `contact.py:114,133` → call `record_event` instead of direct `.objects.create`
- Migrate `trust_analytics.py:106` → delegate to `record_event`
- Add `record_event` to `core/services/__init__.py` exports (inconsistent with contact.py exports)
- Add rollback-gate test (still missing)

---

## QLT-004: Undocumented broad pyright ignores

**Severity:** MEDIUM · **Type:** BEST-PRACTICE · **Status:** Count significantly understated; many line references stale

### Discrepancy: Suppression count is 39, not 29

The findings QLT-004 (line 260) states:
> "Grep `pyright: ignore[reportGeneralTypeIssues]` across `src/` — returned exactly **29 matches** (not '30+' as the finding states)."

**Python verification of the current source returns exactly 39 matches** (37 production + 2 test),
across 27 unique files. The 10 additional sites are from post-validation commits:

| Additional site | File | Line | Source commit |
|---|---|---|---|
| 3 new | `ads/views/edit.py` | 124, 268, 302 | Sep 8 `7f5f067` (DB-003 locking) |
| 2 new | `moderation/views/review.py` | 76, 123 | Sep 8 `923bd35` (DB-003 locking) |
| 1 new | `categories/catalog/builder.py` | 117 | Sep 9 `43e75f0` (CATALOG_LOAD advisory lock) |
| 3 additional | `moderation/admin_actions.py` | 131, 177, 242 | Sep 8 `1d7aa1c` (DB-003 bulk locking) |
| 2 test | `ads/tests/test_edit_views_locking.py` | 138, 147 | Sep 8 (matching production edit.py) |

**admin_actions.py specifically:** The findings table lists only line 103 (1 site).
The actual file has **4 sites**: lines 105, 131, 177, 242. Three of these are from the
Sep 8 DB-003 bulk operation commit (`1d7aa1c`) which added `transaction.atomic()` with
`select_for_update` to `bulk_approve`, `bulk_reject`, and `bulk_delete`.

### Complete current inventory (39 sites)

**Production (37 sites, 26 files):**

| File | Lines | Pattern | Notes |
|------|-------|---------|-------|
| `telegram_bot/handlers/login.py` | 184, 192 | `transaction.atomic()` | Findings say 166, 174 (−18) |
| `telegram_bot/handlers/ad_create.py` | 1197 | `transaction.atomic()` | Findings say 1201 (−4) |
| `apps/ads/views/edit.py` | 124, 268, 302 | `transaction.atomic()` | **NOT in findings table** |
| `apps/ads/services/copy_service.py` | 28 | `transaction.atomic()` | Match |
| `apps/analytics/management/commands/rollup_daily_metrics.py` | 43 | `transaction.atomic()` | Findings say 42 (+1) |
| `apps/moderation/admin_actions.py` | 105, 131, 177, 242 | `transaction.atomic()` | Findings list 1 site (103); **3 missing** |
| `apps/moderation/models` | — | — | (no sites here) |
| `apps/moderation/services/moderation_log.py` | 181, 197, 225 | `transaction.atomic()` | Findings say 182, 198, 218 (off by 1, 1, +7) |
| `apps/moderation/services/auto_moderation.py` | 236, 253 | `transaction.atomic()` | Findings say 231, 248 (+5) |
| `apps/moderation/services/priority_calculator.py` | 63 | `for` loop | Match |
| `apps/moderation/views/review.py` | 76, 123 | `transaction.atomic()` | **NOT in findings table** |
| `apps/categories/catalog/builder.py` | 117 | `transaction.atomic()` | **NOT in findings table** |
| `apps/seed/services/seed_service.py` | 90, 233 | `transaction.atomic()` | Match |
| `apps/currencies/management/commands/recompute_normalized_prices.py` | 51 | `transaction.atomic()` | Match |
| `apps/media/management/commands/backfill_thumbnails.py` | 56 | `transaction.atomic()` | Match |
| `apps/media/management/commands/sweep_orphaned_media.py` | 87 | `transaction.atomic()` | Findings say 86 (+1) |
| `apps/search/management/commands/send_alerts.py` | 51 | `transaction.atomic()` | Findings say 50 (+1) |
| `apps/users/views/consent.py` | 384 | `transaction.atomic()` | Findings say 380 (+4) |
| `apps/users/services/deletion.py` | 112 | `transaction.atomic()` | Findings say 116 (+4) |
| `apps/core/management/commands/cleanup_login_tokens.py` | 41 | `transaction.atomic()` | Findings say 40 (+1) |
| `apps/core/management/commands/archive_sweep.py` | 41 | `transaction.atomic()` | Findings say 40 (+1) |
| `apps/core/management/commands/consent_hard_delete.py` | 46 | `transaction.atomic()` | Findings say 45 (+1) |
| `apps/core/management/commands/purge_deleted_ads.py` | 43 | `transaction.atomic()` | Findings say 44 (−1) |
| `apps/core/management/commands/delete_sweep.py` | 43 | `transaction.atomic()` | Match |
| `apps/core/management/commands/purge_failed_ads.py` | 42 | `transaction.atomic()` | Match |
| `apps/core/management/commands/purge_rejected_ads.py` | 43 | `transaction.atomic()` | Match |
| `apps/core/management/commands/sweep_drafts.py` | 42 | `transaction.atomic()` | Match |

**Test (2 sites, 1 file):**

| File | Lines | Pattern |
|------|-------|---------|
| `apps/ads/tests/test_edit_views_locking.py` | 138, 147 | `transaction.atomic()` |

### Pattern breakdown
- **`transaction.atomic()` context managers:** 38 sites
- **`for` loop (JSONField iteration):** 1 site (`priority_calculator.py:63`)
- **Total:** 39 sites across 27 files

### Verified Claims (CONFIRMED)

1. **django-stubs is NOT a dependency** — grep for `django-stubs` across the entire
   repository returns 0 matches in `pyproject.toml` (and 0 matches anywhere except
   the findings markdown file itself). Confirmed absent from both runtime deps
   (`pyproject.toml:10-29`) and dev deps (`pyproject.toml:201-211`).

2. **basedpyright config** (`pyproject.toml:187-195`):
   ```toml
   [tool.basedpyright]
   typeCheckingMode = "standard"
   reportMissingTypeStubs = "none"
   reportArgumentType = "none"
   reportIncompatibleVariableOverride = "none"
   reportAttributeAccessIssue = "none"
   reportMissingImports = "none"
   reportOperatorIssue = "none"
   reportCallIssue = "none"
   ```
   - `typeCheckingMode = "standard"` (NOT "strict" as the phase scope claims) — confirmed
   - `reportMissingTypeStubs = "none"` at line 189 (findings cite line 196, off by 7)
   - `reportGeneralTypeIssues` is NOT overridden — confirmed enforced at "standard" level
   - Based on the current `pyproject.toml` (229 lines total; findings cite `:194-202`
     for config block, actual is `:187-195`)

3. **`# noqa: RULE - rationale` convention** — confirmed in codebase. Examples:
   - `apps/core/services/analytics.py:52` — `# noqa: BLE001 — analytics must never break the request`
   - `apps/core/apps.py:20` — `# noqa: F401 - side-effect: register signals`
   - `apps/moderation/apps.py:18` — `# noqa: F401 - side-effect: register signals signals`
   - `apps/lookups/apps.py:16` — `# noqa: F401`
   - `apps/categories/apps.py:14` — `# noqa: F401`
   - `app/225`: `CategoryListingPurpose.objects.update_or_create(...,  # noqa: N806`
   - `app/179`: `LookupItem = apps.get_model(...)  # noqa: N806`

4. **ruff config** (`pyproject.toml:117-128`):
   ```toml
   [tool.ruff.lint]
   select = ["E", "F", "I", "B", "UP"]
   ignore = ["E501"]
   ```
   No `PGH` rules selected — confirmed. No `noqa` ignore-code requirement imposed.

### Line-number discrepancies in findings table

Every line-number entry in the findings QLT-004 table is stale (off by 1 to +18).
The systematic shifts match the isort auto-fix commit (`984bd13`, Sep 10) which reordered
imports across all files, plus feature commits adding lines above each site:

| File | Findings cite | Actual line(s) | Delta |
|------|---------------|----------------|-------|
| `login.py` | 166, 174 | 184, 192 | +18, +18 |
| `ad_create.py` | 1201 | 1197 | −4 |
| `copy_service.py` | 28 | 28 | 0 |
| `rollup_daily_metrics.py` | 42 | 43 | +1 |
| `admin_actions.py` | 103 (×1) | 105, 131, 177, 242 (×4) | +2, +3 missing, +3 missing |
| `consent.py` | 380 | 384 | +4 |
| `deletion.py` | 116 | 112 | −4 |
| `backfill_thumbnails.py` | 56 | 56 | 0 |
| `sweep_orphaned_media.py` | 86 | 87 | +1 |
| `priority_calculator.py` | 63 | 63 | 0 |
| `send_alerts.py` | 50 | 51 | +1 |
| `moderation_log.py` | 182, 198, 218 | 181, 197, 225 | −1, −1, +7 |
| `auto_moderation.py` | 231, 248 | 236, 253 | +5, +5 |
| `seed_service.py` | 90, 233 | 90, 233 | 0 |
| `recompute_normalized_prices.py` | 51 | 51 | 0 |
| `archive_sweep.py` | 40 | 41 | +1 |
| `cleanup_login_tokens.py` | 40 | 41 | +1 |
| `consent_hard_delete.py` | 45 | 46 | +1 |
| `purge_deleted_ads.py` | 44 | 43 | −1 |
| `delete_sweep.py` | 43 | 43 | 0 |
| `purge_failed_ads.py` | 42 | 42 | 0 |
| `purge_rejected_ads.py` | 43 | 43 | 0 |
| `sweep_drafts.py` | 42 | 42 | 0 |

### Files missing from the findings table entirely

| File | Lines | Pattern | Source commit |
|------|-------|---------|---------------|
| `ads/views/edit.py` | 124, 268, 302 | `transaction.atomic()` | Sep 8 `7f5f067` |
| `moderation/views/review.py` | 76, 123 | `transaction.atomic()` | Sep 8 `923bd35` |
| `categories/catalog/builder.py` | 117 | `transaction.atomic()` | Sep 9 `43e75f0` |
| `ads/tests/test_edit_views_locking.py` | 138, 147 | `transaction.atomic()` | Sep 8 `7f5f067` |

### Rollout safety

Comment-only rationale additions remain safe. The count correction (29 → 39) means
10 additional sites need rationale comments. The 3 `edit.py` sites, 2 `review.py` sites,
and 1 `builder.py` site are in production code paths that were added after validation.

---

## QLT-005: Untyped list[Any] returns + apps: Any

**Severity:** LOW · **Type:** BEST-PRACTICE · **Status:** Substance correct; line references inaccurate

### Verified Claims (CONFIRMED)

1. **`cache_service.py:9`** — `from typing import Any` — confirmed
2. **`cache_service.py:28`** — `def get_all_groups() -> list[Any]:` — confirmed
3. **`cache_service.py:34`** — `from apps.lookups.models import LookupGroup` (deferred import inside function body) — confirmed
4. **`cache_service.py:47`** — `def get_active_items(group_code: str) -> list[Any]:` — confirmed
5. **`cache_service.py:56`** — `from apps.lookups.models import LookupItem` (deferred import inside function body) — confirmed
6. **`lookups/models.py`** — `LookupGroup` (line 11) and `LookupItem` (line 43) concrete models confirmed with:
   - `LookupGroup`: `code` (CharField), `name_i18n` (JSONField), `is_system` (BooleanField), `sort_order` (PositiveIntegerField)
   - `LookupItem`: `group` (FK to LookupGroup), `slug` (SlugField), `name_i18n` (JSONField), `sort_order`, `is_active`, `icon`, `color`

### Discrepancies in Line References (findings' own corrections are wrong)

The findings QLT-005 state that the original finding cited wrong lines, and provide
"corrected" line numbers. However, **the corrected line numbers are themselves incorrect**
against the current source:

| Claim | Findings say (corrected) | Actual line | Error |
|---|---|---|---|
| `from typing import Any` in builder.py | Line **33** | Line **28** | Findings off by +5 |
| `apps: Any = None` in builder.py | Line **55** | Line **47** | Findings off by +8 |
| `load_catalog()` signature start | Lines **53–57** | Lines **45–51** | Findings off by +8 |
| `apps.get_model()` docstring in `load_catalog` | Lines **86–92** | Line **70** | Findings off by +16 |

**Root cause:** The findings were validated on Sep 5. The isort auto-fix (Sep 10, commit
`984bd13`) reordered imports in `builder.py`, and the CATALOG_LOAD advisory-lock commit
(Sep 9, `43e75f0`) added the `advisory_lock` import and usage above `load_catalog`, shifting
all subsequent lines. The validator's correction (done at validation time) was correct
then, but the current source has shifted further.

### Additional untyped `Any` not mentioned in findings

**`search_history.py`** uses `Any` for the `session` parameter — not cited in QLT-005:
- Line 14: `from typing import Any`
- Line 27: `def _record_session_history(session: Any, normalized: str, query: str) -> None:`
- Line 40: `def record_search_history(user_id: int | None, query: str, session: Any = None) -> None:`
- Line 92: `session: Any = None,` (in `get_user_search_history` signature)

`django.sessions.backends.db.SessionStore` is the concrete type — the `Any` is avoidable.

### Exact signatures verified

```python
# cache_service.py:28
def get_all_groups() -> list[Any]:

# cache_service.py:47
def get_active_items(group_code: str) -> list[Any]:

# builder.py:45-51 (actual, not 53-57 as findings claim)
def load_catalog(
    config_path: str | Path,
    apps: Any = None,
    rewrite_yaml: bool = True,
) -> dict[str, str]:

# builder.py:28 (actual, not 33 as findings claim)
from typing import Any

# builder.py:117 (pyright ignore — not listed in QLT-004 table)
with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]
```

### Rollout safety

Trivial. Replace `list[Any]` → `list[LookupGroup]` / `list[LookupItem]` (deferred imports
already in scope). Replace `apps: Any` → `Apps | None` (import `from django.apps import Apps`).
Also apply to `search_history.py`'s `session: Any` → `SessionBase | None`. No runtime
behavior change.

---

## Cross-Finding Analysis

### Code Evolution Timeline (Sep 5–11)

| Date | Commit | Affects |
|------|--------|---------|
| Sep 5 | `19fabe2` / `e7ce009` | Findings validated / refined |
| Sep 6 | `5fad588` | `contact_rate_limit.py` created in `core/services/` |
| Sep 8 | `5b80f7b` | **`analytics.py` + `record_event` created**; wired into `listings.py` + `search.py` — QLT-003 partially implemented |
| Sep 8 | `7f5f067` | `edit.py` DB-003 locking — +3 pyright ignores (QLT-004) |
| Sep 8 | `923bd35` | `review.py` DB-003 locking — +2 pyright ignores (QLT-004) |
| Sep 8 | `1d7aa1c` | `admin_actions.py` DB-003 bulk locking — +3 pyright ignores (QLT-004) |
| Sep 9 | `43e75f0` | `builder.py` CATALOG_LOAD advisory lock — +1 pyright ignore (QLT-004) |
| Sep 9 | `bad66e3` | login.py i18n gettext wrapping — +18 lines (shifts login.py references) |
| Sep 10 | `984bd13` | isort auto-fix across ALL files — shifts line numbers system-wide |
| Sep 10 | `9145109` | ad_create.py import sort fix |
| Sep 10 | `93604c8` | ad_create.py retry/backoff additions — +6 lines (1506→1512) |
| Sep 11 | `15483f4` | HEAD (doc plan) |

### Summary of Discrepancies

| Finding | Substantive accuracy | Line reference accuracy | Count accuracy |
|---------|----------------------|------------------------|----------------|
| QLT-001 | ✅ Correct | ❌ All stale (delta −4 to +18) | ✅ `test_edit.py` absent confirmed |
| QLT-002 | ✅ Correct | ❌ Stale (delta −1 to +13) | ✅ 12+ test assertions confirmed |
| QLT-003 | ❌ Recommendation already implemented | ❌ All stale (+5 to +18) | ❌ Site count/model changed |
| QLT-004 | ✅ Pattern correct | ❌ All stale | ❌ 29 claimed → 39 actual |
| QLT-005 | ✅ Correct | ❌ Corrections themselves wrong (+5 to +16) | ✅ |

### Cross-cutting Verification

| Item | Findings claim | Actual | Match? |
|------|---------------|--------|--------|
| Test markers | "unit, integration, concurrent, asyncio, etc." | `unit, integration, seed, settings, concurrent, slow, real_images, xdist_group`; `asyncio_mode = "strict"` (config, NOT a marker) | ❌ "asyncio" is not a marker |
| Test DB via Docker Compose | `mko-bazuna-test` project | Confirmed: `docker-compose.test.yml` uses `mko-bazuna-test` project, PostgreSQL 18 on port 5433, test service with bind-mounts | ✅ |
| Canonical conftest | `src/backend/conftest.py` + `src/telegram_bot/tests/conftest.py` | Both confirmed to exist (14127 + 9637 bytes respectively) | ✅ |
| `pyproject.toml` line count | 229 lines (findings cite various line numbers) | 229 lines confirmed; basedpyright config at lines 187–195 (findings cite 194–202) | ❌ Line references off by +7 |
| `ad_create.py` line count | 1506 (Python splitlines) | **1512** (Python splitlines, Sep 11) | ❌ +6 lines |

### QLT-001/QLT-003 Interaction

The findings QLT-001 rollout plan (step 5) recommends: "Apply QLT-003: centralize
AnalyticsEvent.objects.create → core/services/analytics.py:record_event at the
already-consolidated auto_moderate seam." The `record_event` function now exists (created
Sep 8), and steps 3–4 of QLT-001 (bot rewire → edit.py migration) should migrate the bot's
`_update_and_moderate` to call `submit_ad`, which in turn would call `record_event`
instead of relying on `auto_moderate`'s inline creates.

The `auto_moderate` function itself still uses inline
`AnalyticsEvent.objects.create` at lines 239, 256, 262 (inside `transaction.atomic()`
blocks at 236, 253). These 3 sites are the highest-priority QLT-003 migration targets
given QLT-001's orchestration extraction.

### QLT-004/QLT-001 Interaction

The `ad_create.py:1197` pyright ignore is the only one inside the function the findings
want to extract (`_update_and_moderate`). After QLT-001 extraction moves this logic to
`submission.py`, the pyright ignore would move with it — the rationale comment should be
applied to the new location.

---

## Priority Action List (Revised)

1. **[QLT-004]** The 39 pyright-ignore sites (not 29) need rationale comments. 10 sites
   were added post-validation and are absent from the findings table. Priority: add
   rationale to the 10 new/missing sites first:
   - `edit.py:124,268,302` (DB-003 locking)
   - `review.py:76,123` (DB-003 locking)
   - `builder.py:117` (CATALOG_LOAD advisory lock)
   - `admin_actions.py:131,177,242` (DB-003 bulk locking)
   - `test_edit_views_locking.py:138,147` (test-only)
   Then backfill the 29 sites already identified in the findings table.

2. **[QLT-003]** Partially implemented — `analytics.py` exists and is used at 2 sites.
   Migrate the remaining 7 inline `AnalyticsEvent.objects.create` callers to `record_event`:
   - `login.py:208` (also fixes eager f-string at 212)
   - `auto_moderation.py:239,256,262` (inside atomics at 236,253 — verify no self-atomic)
   - `contact.py:114,133`
   - `trust_analytics.py:106`
   Add `record_event` to `core/services/__init__.py` exports.
   Add rollback-gate test (assert `record_event` inside `auto_moderation` atomic is
   NOT written on transaction rollback).

3. **[QLT-001]** Proceed with 4-stage rollout. Line references in documentation are stale
   (all shifted by −4 to +18). Recompute line numbers against current HEAD before
   implementation. The missing `test_edit.py` precondition remains blocking.

4. **[QLT-002]** Stale line references (template +13, tests −1). Substantive finding
   intact. Pydantic DTO extraction safe if all keys preserved. `type` key NOT droppable
   without coordinated frontend + test updates.

5. **[QLT-005]** Findings' own "corrected" builder.py line numbers (33, 55, 86–92) are
   themselves wrong against current source (actual: 28, 47, 70). Apply trivial typing
   fixes. Also address `search_history.py` `session: Any` (lines 27, 40, 92) — not
   previously cited in QLT-005.
