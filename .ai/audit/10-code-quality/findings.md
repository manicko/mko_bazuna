# Phase 10 Audit Findings — Code Quality

**Executor:** audit-executor
**Phase scope (zones):** Typing/type safety; StrEnum for all fixed values; logging-not-print; separation of concerns (bot handlers + web views as thin adapters); module/function size + SRP; Pydantic v2 DTOs at bot+web boundaries; English-only; migration discipline; DRY across the two processes (shared business-logic/seam layer). Static tools: ruff, basedpyright (strict). Runtime: Docker not started (static analysis only).

**Status:** complete
**Validated:** no (static analysis only; Docker runtime not executed this phase)

> Cross-phase dedup note: Bot↔ORM/sync bridge DB-connection churn is owned by phase 03 (DB-001); translation-client retry/backoff is owned by phase 09 (EXT-001); rate-limit gaps on the public browse surface are owned by phase 09 (EXT-003). Findings below are scoped to code-quality concerns NOT already filed.

---

## Findings

---

### QLT-001: Bot ad-creation handler embeds business logic, ORM writes, validation, and thumbnail I/O in the handler instead of delegating to a shared service layer

| Field | Value |
|-------|-------|
| **ID** | QLT-001 |
| **Severity** | HIGH |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/telegram_bot/handlers/ad_create.py` (1506 lines; `_update_and_moderate`, `_submit_for_moderation`); `src/backend/apps/ads/services/` (only `copy_service.py` + `images.py` — no submission/publish orchestrator) |
| **Classification** | advisory |
| **Phase checks** | §4(d) handlers thin adapters delegating to shared service; no ORM/validation/formatting in presentation; §4(e) module/function size + SRP; §4(i) DRY across processes |

**Description:** Per §4(d), bot handlers must be thin adapters that delegate to the shared business-logic layer; the bot ad-creation handler instead embeds the whole submission orchestration inline. `ad_create.py` is 1506 lines (phase-10 target for module size is "small, focused"; this is the largest production file). `_update_and_moderate` (`ad_create.py:1076-1239`) performs: currency coercion (`CurrencyCode` coercion, lines 1105-1120), price normalization (`PriceNormalizer().normalize_to_eur`, lines 1124-1136), multi-language translation-field assignment (lines 1140-1153), filesystem thumbnail generation inside the handler (`ThumbnailService.generate_thumbnails` + `open(..., "rb")`, lines 1160-1199), `AdImageService.create_or_skip` row writes (lines 1212-1221) and the DRAFT→ON_MODERATION state transition (`ad.transition_to(AdStatus.ON_MODERATION)`, line 1225) — all within `transaction.atomic()`. The comment at `ad_create.py:1227-1231` itself says "Delegate to shared auto-moderation service" for validation, yet the field assembly, price-normalization, thumbnail+image persistence and status transition remain in the handler. There is no `apps.ads.services.submission` (or equivalent) orchestrator for the web process to share, so the only producer of ads (bot, per `AdSource.TELEGRAM`) owns this logic with no seam. The web edit view (`ads/views/edit.py:167-303`) re-implements `transition_to(ON_MODERATION)` directly too, so the state-transition rule is duplicated rather than centralized.

**Evidence:**
- `src/telegram_bot/handlers/ad_create.py` — 1506 lines total; `_update_and_moderate` body lines 1076-1239
- `ad_create.py:1105-1136` — currency coercion + `PriceNormalizer().normalize_to_eur(...)`, `except Exception:` (line 1130) swallow-and-null
- `ad_create.py:1160-1199` — `ThumbnailService(settings.MEDIA_ROOT).generate_thumbnails(...)` + `open(original_path,"rb")` filesystem I/O inline, `except Exception:` swallow (line 1189)
- `ad_create.py:1212-1225` — `AdImageService.create_or_skip(...)` ORM writes + `ad.transition_to(AdStatus.ON_MODERATION)` inline
- `ad_create.py:1201` — `with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]`
- `src/backend/apps/ads/services/` contains only `copy_service.py`, `images.py` (no submission/publish service)
- contrast: `src/backend/apps/ads/views/edit.py:167-168` re-does `ad.transition_to(AdStatus.ON_MODERATION)` inline

**Recommendation:** [BEST-PRACTICE] Extract ad-submission orchestration (field assembly, currency/price-normalization, thumbnail+AdImage persistence, status transition) into a shared `apps.ads.services.submission` service with one entry point (e.g. `submit_for_moderation(ad_id, **fields) -> Ad`); keep `ad_create.py` as a thin FSM adapter that validates input via the existing Pydantic message payloads (`telegram_bot.schemas.message_payloads`) and calls the service. Route `ads/views/edit.py` through the same orchestrator so the transition rule lives once. Effort: large. Priority: recommended.

---

### QLT-002: Autocomplete web boundary returns untyped `dict[str, Any]` (no Pydantic DTO) and emits a redundant duplicate enum-value key

| Field | Value |
|-------|-------|
| **ID** | QLT-002 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/search/views/autocomplete.py` (lines 60, 71-72, 87) |
| **Classification** | advisory |
| **Phase checks** | §4(a) no `Any` masking real issues; §4(f) Pydantic v2 at web boundary; §4(b) fixed values via StrEnum |

**Description:** `autocomplete` is a web boundary returning a JSON response, yet it builds results as `list[dict[str, Any]]` (`autocomplete.py:60`, `:87`) and mutates those dicts in place — no Pydantic DTO serializes the response, so the output type is opaque to callers and to `basedpyright` (which is why `Any` appears here). Each user-history item is built with two keys carrying the same value: `"source": SearchSuggestionSource.USER_HISTORY.value` and `"type": SearchSuggestionSource.USER_HISTORY.value` (`autocomplete.py:71-72`) — the `type` key is a verbatim duplicate of `source`, indicating an earlier field that was renamed to `source` and never removed. Entity/popular suggestions are extended in as already-`dict[str, Any]` (`autocomplete.py:79,83`), so the merge/dedup loop (`autocomplete.py:85-92`) relies on `.get("text")` duck-typing rather than a typed schema. Per §4(f) every web POST/GET returning structured data should be validated/serialized through Pydantic before crossing the boundary.

**Evidence:**
- `src/backend/apps/search/views/autocomplete.py:9` — `from typing import Any`
- `autocomplete.py:60` — `suggestions: list[dict[str, Any]] = []`
- `autocomplete.py:71` — `"source": SearchSuggestionSource.USER_HISTORY.value,`
- `autocomplete.py:72` — `"type": SearchSuggestionSource.USER_HISTORY.value,`  (identical value → redundant key)
- `autocomplete.py:79,83` — `suggestions.extend(entity_suggestions)` / `extend(popular)` from services returning `Any`-typed structures
- `autocomplete.py:88-92` — dedup via `item.get("text", "")` duck-typing
- no Pydantic model imported/used in the file's response path

**Recommendation:** [BEST-PRACTICE] Model each suggestion with a Pydantic `AutocompleteSuggestion` DTO (`text`, `source: SearchSuggestionSource`, optional `type`) and serialize via `model_dump(mode="json")` in the `JsonResponse`; drop the redundant `type` key (or keep only if a downstream consumer needs it — grep for `"type"` consumers in `frontend`/`templates`). Effort: small. Priority: recommended.

---

### QLT-003: Analytics event recording is not centralized — registration + publish recorded inline in two process-specific sites instead of a single shared helper

| Field | Value |
|-------|-------|
| **ID** | QLT-003 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/telegram_bot/handlers/login.py:189-194` (REGISTRATION_CREATED inline in bot handler); `src/backend/apps/moderation/services/auto_moderation.py:234,251,257` (AD_PUBLISHED/REJECTED/MODERATION_APPROVED inline); vs the centralized `src/backend/apps/core/services/contact.py:114,133` (CONTACT_INITIATED/CONTACT_RESPONSE) |
| **Classification** | advisory |
| **Phase checks** | §4(i) shared rules (analytics recording) live in ONE place, not duplicated in both handlers; §12 no print() / proper logging |

**Description:** §4(i) requires that shared rules — explicitly "analytics recording" — live in one service layer, not be copy-pasted into handlers. Today the pattern is inconsistent across the codebase. **Contact** events ARE centralized: `core/services/contact.py` exposes `record_contact_initiated` / `record_contact_response` and uses lazy `logger.info("Contact initiated event recorded for buyer %s", user_id)`. But **registration** is recorded inline inside the bot login handler: `AnalyticsEvent.objects.create(event_type=AnalyticsEventType.REGISTRATION_CREATED, user_id=user.id)` at `login.py:190`, inside `handle_login_orm`'s `sync_to_async` closure, with an eager f-string log `logger.info(f"Registration event recorded for user {user.id}")` (`login.py:194`) — the opposite of `contact.py`'s lazy style, so this is the one logging-style violation found in production non-test code. **Publish moderation** events are likewise recorded inline in the moderation service (`auto_moderation.py:234,251,257`) rather than via a shared recorder. So there are three distinct inline `AnalyticsEvent.objects.create(...)` sites for event types that share the `AnalyticsEventType` enum, while contact is extracted — a DRY violation and an inconsistency risk: a new event type or a shared field (e.g. extra metadata) must be added in multiple places and the logging style diverges.

**Evidence:**
- `src/telegram_bot/handlers/login.py:190` — `AnalyticsEvent.objects.create(event_type=AnalyticsEventType.REGISTRATION_CREATED, user_id=user.id)` inline in bot handler
- `login.py:194` — `logger.info(f"Registration event recorded for user {user.id}")` (eager f-string; only such violation found in prod non-test code)
- `src/backend/apps/moderation/services/auto_moderation.py:234,251,257` — inline `AnalyticsEvent.objects.create(...)` for REJECTED/APPROVED/AD_PUBLISHED inside moderation service
- `src/backend/apps/core/services/contact.py:114,133` — the ONE centralized recorder (`record_contact_initiated`, `record_contact_response`) with lazy `%s` logging

**Recommendation:** [BEST-PRACTICE] Introduce a single `core/services/analytics.py` with `record_event(event_type: AnalyticsEventType, user_id: int | None = None, **extra) -> AnalyticsEvent` and route registration (login.py) and moderation publish events (auto_moderation.py) through it, matching contact's pattern. Adopt lazy `%s` interpolation everywhere (drop the f-string at login.py:194). Effort: small. Priority: recommended.

---

### QLT-004: Undocumented broad `# pyright: ignore[reportGeneralTypeIssues]` suppressions mask Django async/ORM type-checker friction

| Field | Value |
|-------|-------|
| **ID** | QLT-004 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/telegram_bot/handlers/ad_create.py:1201`; `src/telegram_bot/handlers/login.py:166,174`; and repo-wide — 30+ blanket `# pyright: ignore[reportGeneralTypeIssues]` suppressions incl. `src/backend/apps/ads/services/copy_service.py:28`, `src/backend/apps/users/views/consent.py:380`, `src/backend/apps/users/services/deletion.py:116`, `src/backend/apps/moderation/services/{auto_moderation,moderation_log,priority_calculator}.py`, plus a dozen management commands |
| **Classification** | advisory |
| **Phase checks** | §4(a) type-checker clean except framework-forced `Any` (documented); §7 edge case "Any used to make the type-checker pass, masking real issues" |

**Description:** §4(a) allows `Any` only where a framework signature forces it and requires it to be documented. Across the repo, the catch-all `# pyright: ignore[reportGeneralTypeIssues]` suppresses Django ORM/async friction (e.g. `transaction.atomic()` as a context manager, `sync_to_async`-wrapped closures) because Django stubs type the manager/DB layer loosely, rather than using a scoped, documented ignore. This broad bucket suppression means a *real* general-type error in any of the 30+ sites is silently swallowed (e.g. a wrong tuple shape from `_handle` at `login.py:195`). This is the exact Any/mask-to-pass pattern §7 flags; `basedpyright` reports 0 errors repo-wide only because the suppressions hide the gap.

**Evidence:**
- `src/telegram_bot/handlers/ad_create.py:1201` — `with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]`
- `src/telegram_bot/handlers/login.py:166` — `with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]`
- `login.py:174` — second identical `transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]`
- grep shows 30+ `# pyright: ignore[reportGeneralTypeIssues]` hits across the repo (bot handlers, `ads/services/copy_service.py`, `users/views/consent.py`, `users/services/deletion.py`, moderation services, and a dozen management commands) — all blanket-suppressing Django ORM/async friction with no inline rationale, so a real general-type error in any of them is hidden
- `basedpyright` reports `0 errors` repo-wide — i.e. the suppressions are what keeps these files green

**Recommendation:** [BEST-PRACTICE] Replace broad `# pyright: ignore[reportGeneralTypeIssues]` with targeted ignores that name the specific rule + a `# Django: ...` rationale, or introduce thin typed wrappers/casts so the assertion is localized; at minimum document *why* each suppression is needed so a future real error is not hidden. Effort: small. Priority: recommended.

---

### QLT-005: Production lookup-cache service returns untyped `list[Any]` (and `apps: Any` on catalog builder), eroding the shared-type seam

| Field | Value |
|-------|-------|
| **ID** | QLT-005 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/backend/apps/lookups/services/cache_service.py:28,47` (`list[Any]` return); `src/backend/apps/categories/catalog/builder.py:36` (`apps: Any = None` — should be Django `Apps`); `src/backend/apps/search/views/autocomplete.py:9,60,87` (`Any`) |
| **Classification** | advisory |
| **Phase checks** | §4(a) no `Any` masking real issues; §4(d) thin adapters + shared types; §4(i) shared business-logic/seam layer |

**Description:** §4(a) requires strict hints everywhere with `Any` only where a framework signature forces it (documented). The lookup cache service is a shared seam consumed by the web process but returns `list[Any]`: `LookupCacheService.get_all_groups() -> list[Any]` (`cache_service.py:28`) returns prefetched `LookupGroup` querysets (docstring says "List of LookupGroup instances") and `get_active_items(...) -> list[Any]` (`cache_service.py:47`) returns `LookupItem` querysets — both should be `list[LookupGroup]` / `list[LookupItem]` (the deferred-import model is already referenced at `cache_service.py:34,56`, so the concrete type is knowable). Similarly `categories/catalog/builder.py:36` types the migration-context `apps` argument as plain `Any` (`apps: Any = None`) even though Django exposes `django.apps.Apps`/`django.db.migrations.state.Apps` and the docstring (`builder.py:13-32`) describes `apps.get_model()`. Since `basedpyright` passes, these `Any`s are *not* framework-forced — they are lazy annotations, so they silently disable type-checking of every call site for these shared lookups (autocomplete, catalog rendering, etc.), which is the seam-risk §4(i) warns about.

**Evidence:**
- `src/backend/apps/lookups/services/cache_service.py:9` — `from typing import Any`
- `cache_service.py:28` — `def get_all_groups() -> list[Any]:`
- `cache_service.py:34` — `from apps.lookups.models import LookupGroup` (type is available, so `Any` is avoidable)
- `cache_service.py:47` — `def get_active_items(group_code: str) -> list[Any]:`
- `src/backend/apps/categories/catalog/builder.py:2,34` — docstring documents `apps.get_model()`; `builder.py:17` `from typing import Any`; `builder.py:36` `apps: Any = None`
- `basedpyright` clean (0 errors) — these `Any`s pass because they opt out of checking, not because they are forced

**Recommendation:** [BEST-PRACTICE] Type `get_all_groups`/`get_active_items` with concrete `LookupGroup`/`LookupItem` (deferred import inside the function body is fine); type `builder.load_catalog`'s `apps` as `Apps | None` from `django.apps`/`django.db.migrations.state`. Effort: trivial. Priority: recommended (low).

---

## Summary

| Severity | Count | IDs |
|----------|-------|-----|
| CRITICAL | 0 | — |
| HIGH | 1 | QLT-001 |
| MEDIUM | 3 | QLT-002, QLT-003, QLT-004 |
| LOW | 1 | QLT-005 |

**Static-tool results:** `uv run ruff check src/backend src/telegram_bot` → `All checks passed!`; `uv run basedpyright src/backend src/telegram_bot` → `0 errors, 0 warnings, 0 notes`. Runtime verification was not executed (Docker not started); findings are from static analysis per phase scope. `print(` grep across production code: zero hits (the only match is a string literal inside `tests/test_settings_secrets.py:65`, not a call). StrEnum drift: no raw status/sort/currency/cookie literals found in production code paths (only in migrations' `RunPython` default seeds and legacy backward-compat cookie values). 

## Mandatory Fixes

(None — classification of all findings is advisory; no `print()` in production, no missing-migration, no security/data-loss issue surfaced this phase.)

## Advisory Recommendations

- **QLT-001** (HIGH): extract ad-submission orchestration (field assembly, currency/price normalization, thumbnail + `AdImage` persistence, DRAFT→ON_MODERATION transition) into a shared `apps.ads.services.submission` service; make `ad_create.py` and `ads/views/edit.py` thin callers of it.
- **QLT-002** (MEDIUM): model autocomplete results with a Pydantic `AutocompleteSuggestion` DTO serialized via `model_dump(mode="json")`; delete the redundant `type` key that duplicates `source`.
- **QLT-003** (MEDIUM): add a single `core/services/analytics.py` `record_event(...)` helper; route registration (login.py) and moderation publish events (auto_moderation.py) through it matching `contact.py`; switch the f-string log at login.py:194 to lazy `%s`.
- **QLT-004** (MEDIUM): replace blanket `# pyright: ignore[reportGeneralTypeIssues]` with scoped ignores carrying a rationale, or add typed wrappers, across the 30+ sites so real type errors are not masked.
- **QLT-005** (LOW): type `LookupCacheService.get_all_groups`/`get_active_items` with concrete `LookupGroup`/`LookupItem` and `builder.load_catalog`'s `apps` with `Apps | None`; drop the avoidable `Any` so the shared lookup seam stays type-checked.
