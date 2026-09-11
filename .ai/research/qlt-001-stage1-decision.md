---
id: qlt-001-stage1-decision
domain: research
phase: code-quality
tags: [qlt-001, decision-gate, submission-orchestrator]
related:
  - .ai/plans/24-code-quality-fixes-execution.md
  - .ai/audit/99-validation/10-code-quality-source-reaudit.md
  - src/backend/apps/ads/services/
  - src/telegram_bot/handlers/ad_create.py
  - src/backend/apps/ads/views/edit.py
  - src/backend/apps/moderation/services/auto_moderation.py
  - src/backend/apps/users/schemas.py
  - src/telegram_bot/schemas/message_payloads.py
  - pyproject.toml
---

# QLT-001 Stage 1 — Block 9 (A1) Decision Gate Resolution

**Gate:** Introduce inert `submission.py` with `SubmitAdInput` + `submit_ad()`
**Status:** RESOLVED — all three decision points resolved with evidence
**Researcher confidence:** HIGH (all claims verified against current source at HEAD 2026-09-11)

---

## Decision 1: `SubmitAdInput` type — Pydantic v2 model vs plain dataclass

### Resolved: Pydantic v2 model

### Evidence

#### 1. Existing `apps/ads/services/` functions do NOT use DTOs

| File | Function | Parameters | Pattern |
|---|---|---|---|
| `copy_service.py:14` | `copy_ad` | `source_ad_id: int, seller_user_id: int` | Individual primitives |
| `images.py:44` | `AdImageService.create_or_skip` | `ad: Ad, image: str, **extra` | Individual primitives |

Neither function accepts a Pydantic DTO or a dataclass. They take individual primitive/ORM parameters. This is the local convention for simple, low-arity service functions.

The broader backend `core/services/` directory follows the same pattern:
- `analytics.py:19`: `record_event(event_type, user_id=None, *, ad_id=None, source=None)` — primitives
- `contact.py`: `record_contact_initiated(user_id)`, `record_contact_response(user)` — primitives

These functions don't cross a system boundary — they're called from within a single process with simple parameters.

#### 2. Pydantic v2 IS a project dependency

`pyproject.toml:28`: `"pydantic>=2.13.4"` — Pydantic v2, confirmed.

#### 3. Pydantic v2 DTOs exist at system boundaries in the backend

`src/backend/apps/users/schemas.py:15`:
```python
class ConsentSubmission(BaseModel):
    """Pydantic DTO for consent form submission validation (TR-06 / C-9.2)."""
    choice: ConsentChoice
    analytics: bool = False
    preferences: bool = False
    consent_version: str = Field(default="1.0", max_length=20)
```

This is a backend `apps/` DTO used at the **HTTP boundary** — constructed from `request.POST` in `apps/users/views/consent.py` and consumed by service logic. It uses `BaseModel`, `Field`, and StrEnum-typed fields — the same pattern recommended for `SubmitAdInput`.

The bot handler already uses Pydantic DTOs in `telegram_bot/schemas/message_payloads.py` (`TitlePayload`, `DescriptionPayload`, `PricePayload`, `PhotoCountPayload`) — all `BaseModel` with `Field`/`Annotated` validation.

#### 4. Project rule #11 mandates Pydantic v2 at system boundaries

> "All models and validation use Pydantic v2 at system boundaries: bot input, settings schemas, future API."

`SubmitAdInput` is constructed in **two** system-boundary contexts:
- **Bot handler** (`process_preview` in `ad_create.py`): assembled from FSM `state.get_data()` — untrusted, multi-field input.
- **Web edit view** (`ad_edit` in `edit.py`): assembled from `request.POST` — untrusted HTTP input.

Both cross the boundary into the shared backend service layer (`apps/ads/services/`). This is precisely the "at system boundaries" scenario rule #11 targets.

### Why not a plain dataclass?

The existing `apps/ads/services/` functions (`copy_ad`, `create_or_skip`) don't use DTOs because they take **2–4 simple parameters** and don't cross a system boundary — there's no need for validation or serialization. `submit_ad`'s input has **17 fields** assembled from untrusted sources (bot FSM state, HTTP POST). A dataclass provides no validation, no serialization, and no type-coercion — all of which Pydantic v2 provides at zero extra cost given it's already a dependency and used in the exact same pattern (`ConsentSubmission`).

### Why not `apps/ads/services/` convention (primitives)?

Following the primitive-parameter convention would mean `submit_ad(input)` taking 17 individual arguments — which is exactly the bloated signature the extraction is solving (`update_ad_and_moderate` currently has 17 parameters). The DTO is the entire point.

### Conclusion

**Pydantic v2 model.** Matches project rule #11, mirrors the `ConsentSubmission` DTO pattern in `apps/users/schemas.py` (backend system-boundary DTO), and is consistent with the bot handler's existing `message_payloads.py` DTOs. The fact that `copy_service.py` and `images.py` use primitives is irrelevant — they have 2–3 parameters and don't cross a boundary; `SubmitAdInput` bundles 17 untrusted fields at the bot↔web↔service seam.

---

## Decision 2: `submit_ad` sync vs async

### Resolved: SYNC function

### Evidence

#### 1. `auto_moderate` is SYNC

`src/backend/apps/moderation/services/auto_moderation.py:94`:
```python
def auto_moderate(ad: Ad) -> bool:
```
Plain (non-async) function. This is the shared moderation service called from both the bot handler and the web edit view.

#### 2. Bot handler calls `update_ad_and_moderate` via `await`

`src/telegram_bot/handlers/ad_create.py:814` (inside `process_preview`, an async function):
```python
is_valid, errors = await update_ad_and_moderate(
    ad_id=data["ad_id"],
    ...
)
```

The current `update_ad_and_moderate` (line 1038) is `async def` and wraps the sync `_update_and_moderate` inner function in `@sync_to_async` (line 1072–1073). Inside `_update_and_moderate`, `auto_moderate(ad)` is called **synchronously** at line 1229 — **outside** the `transaction.atomic()` block (which ends at line ~1221, confirmed by re-audit: "atomic at 1197 ends line 1221; auto_moderate at 1229 is outside the atomic").

So the bot's current pattern is: async wrapper → `@sync_to_async` sync inner → sync `auto_moderate` called directly.

#### 3. Web edit view calls `auto_moderate` directly (sync)

`src/backend/apps/ads/views/edit.py:24` (top-level import):
```python
from apps.moderation.services.auto_moderation import auto_moderate
```

The view `ad_edit` is **sync** (`def ad_edit(request: HttpRequest, ad_id: int) -> HttpResponse`). In the reactivation branch, `auto_moderate(ad)` is called directly at line 182.

**AST confirmation of transaction scope:** The `with transaction.atomic():` at `edit.py:124` has body ending at line 251. The `if is_reactivation:` at line 163 also ends at line 251 (confirmed by parsing the AST: the entire if/elif/else chain is inside the `with` block). So in the web edit path, `auto_moderate(ad)` at line 182 is called **inside** the `transaction.atomic()` block — a different scope from the bot path (which calls it outside the atomic). This is a pre-existing behavioral difference, not introduced by `submit_ad`.

The separate `ad_reactivate` view (`edit.py:288`) also calls `auto_moderate(ad)` synchronously at line 319, inside its own `with transaction.atomic():` block (line 302).

#### 4. `auto_moderate` is also re-exported from `apps/moderation/services/__init__.py`

`src/backend/apps/moderation/services/__init__.py:3`:
```python
from .auto_moderation import auto_moderate, check
```
Confirming it's a sync service in the `apps/` service layer, imported directly by the web view.

### Pattern analysis

The existing pattern for the shared `auto_moderate` seam is:
- **SYNC function** in the backend `apps/` service layer
- Called **DIRECTLY** (no `sync_to_async`) from sync Django views (`edit.py:182`, `edit.py:319`)
- Called from the bot handler's async context via `@sync_to_async` wrapping the sync inner function (`_update_and_moderate`)

### Why sync `submit_ad` is correct

A **sync** `submit_ad` matches the `auto_moderate` pattern exactly:
- Web edit view (`ad_edit`, sync Django view) calls `submit_ad(SubmitAdInput(...))` directly — no `sync_to_async` bridge needed (mirrors how it calls `auto_moderate(ad)` directly today).
- Bot handler (`process_preview`, async) wraps `submit_ad` in `sync_to_async`: `await sync_to_async(submit_ad)(SubmitAdInput(...))` (as described in Block 10, line 836). This mirrors the current `@sync_to_async` wrapping of `_update_and_moderate`.

### Why async `submit_ad` is wrong

An **async** `submit_ad` would invert the existing pattern:
- The sync web edit view would need `sync_to_async(submit_ad)(...)` — introducing async-into-sync friction in the wrong direction.
- `auto_moderate` is sync, so an async `submit_ad` would need to call `sync_to_async(auto_moderate)(ad)` internally — an async orchestrator calling a sync leaf, which is the reverse of the project's established pattern (`auto_moderate` is the sync leaf that everything else bridges to).

### Conclusion

**SYNC `submit_ad`.** Called directly from the web edit view (matching `auto_moderate`'s direct sync call in `edit.py`), and wrapped in `sync_to_async(submit_ad)(...)` from the bot handler's `process_preview` (matching the current `@sync_to_async` wrapping of `_update_and_moderate`). This keeps `auto_moderate` (sync leaf) called synchronously inside `submit_ad`, and eliminates the unnecessary async/sync boundary that exists today inside `ad_create.py`.

---

## Decision 3: Should Stage 1's `SubmitAdInput` include `on_invalid_currency`?

### Resolved: NO — defer to Block 12 (A4) currency gate

### Evidence

#### 1. Stage 1 is explicitly an inert, verbatim extraction

The plan (Block 9, line 761):
> "This block introduces an **inert** `submission.py` — a verbatim extraction of `_update_and_moderate`'s body, with NO callers wired yet."

The `_update_and_moderate` function (lines 1073–1237 of `ad_create.py`) hardcodes the "invalid currency → None" coercion:
```python
# ad_create.py:1101-1116
currency: CurrencyCode | None = None
if price_currency is not None:
    try:
        currency = (
            price_currency
            if isinstance(price_currency, CurrencyCode)
            else CurrencyCode(str(price_currency))
        )
    except ValueError:
        logger.warning("Invalid price_currency %r for ad %s", price_currency, ad_id)
ad.price_currency = currency.value if currency else None
```

This is a hardcoded policy: invalid currency → `None`.

#### 2. `on_invalid_currency` is explicitly a Block 12 (A4) addition

The plan (Block 12, line 985–988):
> "**`submit_ad` / `submission.py`** — if Path 1 (parameterized coercer) is chosen:
> - Add `on_invalid_currency: Literal["none", "keep"] = "none"` parameter to `SubmitAdInput`.
> - Modify the currency coercion logic to honor the policy (when `on_invalid="keep"`, coerce to the existing currency if available)."

And the DAG (line 126–127):
> `qlt001_stage3_edit_migration (A4) ◄── depends: A1`
> `[currency_coercer decision gate]`

The currency-coercion decision gate is **Block 12's** gate, not Block 9's. Block 9 is the predecessor that must ship first with the verbatim logic.

#### 3. Adding `on_invalid_currency` now would violate Stage 1 constraints

- It would add behavior **not present** in the verbatim extraction (Stage 1 must be a verbatim copy).
- It would **prematurely couple** the inert Stage 1 to Block 12's unresolved decision gate (Path 1 parameterize vs Path 2 document-as-divergence).
- The plan explicitly scopes `on_invalid_currency` to Block 12's "if Path 1 is chosen" conditional. Introducing the field in Stage 1 would mean deciding Path 1 before Block 12's analysis.

#### 4. The divergence is between bot (`None`) and web edit (`keep` current)

The re-audit (line 75–77) confirms the existing divergence:
- Bot (`ad_create.py:1101-1116`): invalid currency → `None`
- Web edit (`edit.py:151-158`): invalid `ValueError` → keeps existing currency

The verbatim extraction in Stage 1 copies the bot's "→ None" behavior. Reconciling the web edit's "keep current" behavior is Block 12's job — it will either parameterize the coercer (adding `on_invalid_currency` to `SubmitAdInput` in Block 12) or pre-validate in the edit view (Path 2, no DTO change but documented divergence).

### Conclusion

**Do NOT include `on_invalid_currency` in Stage 1's `SubmitAdInput`.** Stage 1 is an inert, verbatim extraction of the current "invalid → None" coercion logic. The `on_invalid_currency` field is introduced in **Block 12/A4** only if Path 1 (parameterized coercer) is chosen. If Path 2 (document + pre-validate) is chosen in Block 12, no `SubmitAdInput` field is added at all. Either way, Stage 1 should not include it — doing so would couple the inert extraction to a decision gate that belongs to a later block, and would violate the "verbatim copy" requirement.

---

## Summary Table

| Decision | Resolved Value | Rationale |
|---|---|---|
| `SubmitAdInput` type | **Pydantic v2 `BaseModel`** | Rule #11 (boundaries → Pydantic); mirrors `ConsentSubmission` in `apps/users/schemas.py`; bot already uses `message_payloads.py` DTOs. Existing `ads/services/` functions use primitives because they have 2–3 params and don't cross a boundary — irrelevant precedent for a 17-field boundary DTO. |
| `submit_ad` mutability | **SYNC** | Matches `auto_moderate` (sync leaf). Web view calls directly (sync); bot wraps in `sync_to_async`. Async would invert the pattern (sync view bridging async, async calling sync `auto_moderate` internally). |
| `on_invalid_currency` field | **NOT in Stage 1** | Stage 1 is a verbatim inert extraction of the "invalid → None" coercion. The field is a Block 12/A4 addition (Path 1 only). Premature inclusion couples Stage 1 to an unresolved gate and violates "verbatim copy." |

---

## Implementation Implications for Block 9 (A1)

1. **`submission.py` imports** (verbatim from `ad_create.py` lines 1–47 + 1068–1070):
   - `from apps.ads.models import Ad, AdImage`
   - `from apps.ads.services.images import AdImageService`
   - `from apps.core.enums import AdStatus, LanguageLocale, ThumbnailSizeStrEnum`
   - `from apps.currencies.enums import CurrencyCode`
   - `from apps.currencies.services.price_normalizer import PriceNormalizer`
   - `from apps.media.services.thumbnails import ThumbnailService`
   - `from apps.moderation.services.auto_moderation import auto_moderate`
   - `from django.conf import settings`
   - `from django.db import transaction`
   - `import logging`, `import os`
   - `from decimal import Decimal`
   - `from pydantic import BaseModel, Field` (for `SubmitAdInput`)

2. **`SubmitAdInput` fields** (mirroring `update_ad_and_moderate` signature, lines 1038–1056):
   - `ad_id: int`
   - `title_ru: str`
   - `desc_ru: str`
   - `category_id: int | None`
   - `city_id: int | None`
   - `price_amount: Decimal`
   - `price_currency: CurrencyCode | None`
   - `photos: list` → `list[dict]` (the photos are dicts with `storage_key`, `telegram_file_id`, `position`)
   - `user_id: int | None`
   - `title_bs: str = ""`
   - `desc_bs: str = ""`
   - `title_en: str = ""`
   - `desc_en: str = ""`
   - `original_language: str | None = None`
   - `listing_purpose_id: int | None = None`
   - `feature_ids: list[int] | None = None`
   - `listing_condition_id: int | None = None`

3. **`submit_ad(input: SubmitAdInput) -> tuple[bool, list[str]]`**: sync function, verbatim copy of `_update_and_moderate`'s body (lines 1077–1235). Accesses fields via `input.field_name` instead of bare parameter names. **No `on_invalid_currency` field** (see Decision 3).

4. **No callers**: `process_preview` still calls `update_ad_and_moderate`; `edit.py` still calls `auto_moderate` directly. No imports added to any caller.
