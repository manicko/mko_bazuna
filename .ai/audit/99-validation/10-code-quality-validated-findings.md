---
name: 10-code-quality
phase: code-quality
template: .ai/audit/templates/audit-findings.md
status: complete
validated: yes
validator: validator
validated_date: 2026-09-05
---

# Phase 10 Audit Findings — Code Quality (Validated)

**Executor:** audit-executor
**Validator:** validator
**Template:** .ai/audit/templates/audit-findings.md
**Status:** complete
**Validated:** yes

**Scope:** Typing/type safety; StrEnum for all fixed values; logging-not-print; separation of concerns (bot handlers + web views as thin adapters); module/function size + SRP; Pydantic v2 DTOs at bot+web boundaries; English-only; migration discipline; DRY across the two processes (shared business-logic/seam layer). Static tools: ruff, basedpyright. Runtime: Docker not started (static analysis only).

> **Validator's note on tool mode:** The phase scope (findings.md line 4) states "basedpyright (strict)," but `pyproject.toml [tool.basedpyright]` sets `typeCheckingMode = "standard"` with several per-rule `report* = "none"` overrides (lines 194-202). This is a phase-description inaccuracy, not a finding-level issue. Both tools were run by the validator and reported 0 errors / 0 warnings / 0 notes (see R1 below), consistent with the findings.

This file is the self-contained validated report. The reader does not need to consult the original findings file (`.ai/audit/10-code-quality/findings.md`).

---

## Runtime Verification Evidence

| Check | Result | Notes |
|-------|--------|-------|
| R1 — `uv run ruff check src/backend src/telegram_bot` | PASS | `All checks passed!` — 0 errors. Matches findings.md summary. |
| R2 — `uv run basedpyright src/backend src/telegram_bot` | PASS | `0 errors, 0 warnings, 0 notes`. Matches findings.md summary. Note: config is `typeCheckingMode = "standard"` (not "strict" as phase scope claims); several `report*` rules are overridden to `"none"` at config level. |
| R3 — `print(` in production code | PASS | `grep '^\s*print\(' src/**/*.py` → 0 matches. The only `print` occurrence is a string literal in `tests/test_settings_secrets.py:65`, not a call. |
| R4 — File line counts | PASS | `ad_create.py`: Python `splitlines()` confirms 1506 lines (PowerShell `Measure-Object -Line` returned 929 due to an encoding/line-wrapping artifact — Python is authoritative). |
| R5 — `SearchSuggestionSource` StrEnum values | PASS | `core/enums.py:179-185`: `USER_HISTORY="user_history"`, `POPULAR_SEARCH="popular_search"`, `CATEGORY="category"`, `CITY="city"` — match frontend section list in `header_catalog.html:312`. |

---

## Cross-Finding Analysis

### Dependency Chains

| Finding | Depends on | Depends on by | Notes |
|---------|-----------|---------------|-------|
| QLT-001 | — | QLT-003 (indirectly) | QLT-001 extracts ad-submission orchestration into a shared service; the `auto_moderate(ad)` call within `_update_and_moderate` (ad_create.py:1233) internally creates AnalyticsEvent records that QLT-003 proposes centralizing. Moving the orchestration to a service layer aligns QLT-001 and QLT-003 — no conflict. |
| QLT-002 | — | — | Independent: autocomplete response typing. |
| QLT-003 | — | — | Independent: analytics event DRY. Overlaps file (auto_moderation.py) with QLT-004 but different concern (analytics DRY vs. type-ignore quality). Not merge candidates. |
| QLT-004 | — | — | Independent: type-ignore hygiene. |
| QLT-005 | — | — | Independent: `Any` return-type hygiene. Thematic sibling of QLT-002 (both `Any` at seams) but different modules. Not merge candidates. |

### Conflicts Detected

No cross-finding conflicts. All five findings are independently valid and non-overlapping in their remediation targets.

### Unsafe Rollout Sequences

- **QLT-001 must be applied atomically** with QLT-003's analytics-centralization if both touch `_update_and_moderate`'s `auto_moderate(ad)` call path: extracting submission orchestration moves the `AnalyticsEvent.objects.create` calls (currently inside `auto_moderate`) into the service layer, which is exactly where QLT-003 wants them. The two fixes compose cleanly — no conflict.
- **QLT-002 `type` key removal is NOT safe without coordinated changes.** See QLT-002 validation note.

### Fragile Insertion Points

- QLT-002's "drop `type` key" recommendation targets a key consumed by `header_catalog.html:313,327` and asserted in 12+ test locations. Dropping it without updating consumers is a fragile insertion point — flagged in the QLT-002 validation note.
- QLT-004's `priority_calculator.py:63` suppression is on a `for word in criteria.banned_words:` loop (not `transaction.atomic()`), which is a different pattern from the majority — a `for`-loop iteration type issue rather than a context-manager one.

---

## Findings

---

### QLT-001: Bot ad-creation handler embeds business logic, ORM writes, validation, and thumbnail I/O in the handler instead of delegating to a shared service layer

| Field | Value |
|-------|-------|
| **ID** | QLT-001 |
| **Severity** | HIGH |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/telegram_bot/handlers/ad_create.py` (1506 lines; `_update_and_moderate` lines 1076-1239); `src/backend/apps/ads/services/` (only `copy_service.py` + `images.py` — no submission/publish orchestrator) |
| **Classification** | advisory |
| **Validation Status** | **VALIDATED** |

**Evidence Quality:** HIGH — all line references verified exact.

**Validator's Verification:**

- Read `ad_create.py:1076-1245` — confirmed `_update_and_moderate` (async inner `_update_and_moderate()` defined at 1077, called at 1241) spans body lines 1081-1239.
  - Lines 1105-1120: currency coercion (`CurrencyCode` isinstance check + `ValueError` recovery). Confirmed.
  - Lines 1124-1136: `PriceNormalizer().normalize_to_eur(...)` with `except Exception:` swallow-and-null. Confirmed.
  - Lines 1140-1153: multi-language field assignment (`title_bs`, `description_bs`, `title_en`, `description_en`, `original_language`). Confirmed.
  - Lines 1160-1199: filesystem thumbnail generation (`ThumbnailService.generate_thumbnails` + `open(..., "rb")`) with `except Exception:` swallow. Confirmed.
  - Lines 1212-1221: `AdImageService.create_or_skip(...)` ORM writes. Confirmed.
  - Line 1225: `ad.transition_to(AdStatus.ON_MODERATION)` (DRAFT→ON_MODERATION). Confirmed.
  - Line 1201: `with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]`. Confirmed.
  - Line 1233: `auto_moderate(ad)` — validation IS delegated to the shared moderation service (comment at 1227-1231 confirms). The finding correctly notes this: auto_moderation handles validation/ban-words/duplicates, but the field assembly, currency/price normalization, thumbnail+image persistence, and status transition remain inline.
- Read `ad_create.py` via Python `splitlines()` — confirmed 1506 total lines (authoritative; PowerShell `Measure-Object -Line` returned 929 due to encoding artifact).
- Directory listing of `src/backend/apps/ads/services/` — confirmed only `copy_service.py` and `images.py` exist. No `submission.py` or equivalent orchestrator. The `auto_moderate()` function lives in `apps/moderation/services/auto_moderation.py` — it performs validation only, not the full submission orchestration (field assembly, thumbnail generation, image persistence, status transition).
- Read `ads/views/edit.py:167-168` — confirmed `ad.transition_to(AdStatus.ON_MODERATION)` re-implemented inline in the web edit view (same state-transition rule duplicated).
- `ruff check` and `basedpyright` both pass (0 errors).

**Architectural Fit:** ALIGNS. §4(d) requires thin handlers delegating to a shared service layer; §4(i) requires DRY across processes (one submission orchestrator shared by bot and web). The bot is the sole ad producer (`AdSource.TELEGRAM`), so extraction yields direct shared-seam value.

**Rollout Safety:** Non-atomic fix. Move submission orchestration into `apps/ads/services/submission.py`; make `ad_create.py` a thin FSM adapter; route `edit.py` through the same orchestrator. No circular dependency risk — the service layer would depend on `apps.ads.models` (already a dependency of the handler).

---

### QLT-002: Autocomplete web boundary returns untyped `dict[str, Any]` (no Pydantic DTO) and emits a redundant duplicate enum-value key

> **Validation Note:**
> - **Action:** validated with correction
> - **Detail:** The core finding — `dict[str, Any]` return, no Pydantic DTO at the web boundary, and a duplicate `type`/`source` key pair carrying identical `SearchSuggestionSource` values — is fully verified. However, the `"type"` key is NOT truly droppable: it is actively consumed by the frontend template (`header_catalog.html:313` checks `s.type === section || s.source === section`; `:327` reads `s.type || s.source`) and asserted in 12+ test locations (`test_autocomplete.py:136, 222, 527-528, 539, 549, 554, 562, 575, 588, 600, 614`). All three suggestion producers — `get_user_search_history` (via autocomplete.py:71-72), `get_entity_suggestions` (entity_suggestions.py:74-75), and `get_popular_suggestions` (popular_search.py:76-77) — emit BOTH `source` and `type` with the same value. So the key is a verbatim data-level duplicate, but it has downstream consumers. The Pydantic DTO extraction remains recommended; the `type` key should be deprecated gradually (or kept alongside `source`) with coordinated frontend+test updates, not dropped abruptly.
> - **See also:** QLT-005 (shared theme: `Any` at service seams)

| Field | Value |
|-------|-------|
| **ID** | QLT-002 |
| **Severity** | MEDIUM |
| **Type** | SPEC-DEVIATION |
| **Affected Modules** | `src/backend/apps/search/views/autocomplete.py` (lines 9, 60, 71-72, 79, 83, 87-92); downstream: `header_catalog.html:313,327`; tests: `test_autocomplete.py` (12+ assertions on `type`/`source`) |
| **Classification** | advisory |
| **Validation Status** | **VALIDATED** |

**Evidence Quality:** HIGH — all line references verified exact.

**Validator's Verification:**

- Read `autocomplete.py:1-99` (full file):
  - Line 9: `from typing import Any` — confirmed.
  - Line 60: `suggestions: list[dict[str, Any]] = []` — confirmed.
  - Lines 71-72: `"source": SearchSuggestionSource.USER_HISTORY.value` and `"type": SearchSuggestionSource.USER_HISTORY.value` — both keys, identical value — confirmed.
  - Line 79: `suggestions.extend(entity_suggestions)` — confirmed.
  - Line 83: `suggestions.extend(popular)` — confirmed.
  - Lines 87-92: dedup via `item.get("text", "")` duck-typing on `dict[str, Any]` — confirmed.
  - No Pydantic model imported or used in the response path — confirmed (imports are only `logging`, `Any`, `HttpRequest`, `JsonResponse`, `SearchSuggestionSource`, and service functions).
- Read `entity_suggestions.py:1-92` — `get_entity_suggestions` returns `list[dict]` (line 38), emits both `"source"` (line 74) and `"type"` (line 75) with `SearchSuggestionSource.CATEGORY.value` / `.CITY.value`. Confirmed.
- Read `popular_search.py:1-81` — `get_popular_suggestions` returns `list[dict]` (line 48), emits both `"source"` (line 76) and `"type"` (line 77) with `SearchSuggestionSource.POPULAR_SEARCH.value`. Confirmed.
- Read `header_catalog.html:300-334`:
  - Line 312: section loop `['city', 'category', 'popular_search', 'user_history']` — matches `SearchSuggestionSource` enum values (`CITY="city"`, `CATEGORY="category"`, `POPULAR_SEARCH="popular_search"`, `USER_HISTORY="user_history"` at `core/enums.py:182-185`). Confirmed.
  - Line 313: `s.type === section || s.source === section` — consumes `type` key. Confirmed.
  - Line 327: `escapeHtml(s.type || s.source || '')` — consumes `type` key with `source` fallback. Confirmed.
- Grep `test_autocomplete.py` for `"type"` and `"source"` — 20 matches. Specific assertions:
  - `:135-136`: `assert "source" in suggestion` / `assert "type" in suggestion`
  - `:137`: `assert suggestion["source"] in [...]`
  - `:205`: docstring "User-history suggestions carry `type == source == 'user_history'`"
  - `:222`: `user_history_suggestions[0]["type"]`
  - `:523`: docstring "Each suggestion has text, source, and type keys"
  - `:527-528`: `assert "source" in r` / `assert "type" in r`
  - `:539,549,554,562,575,588,600,614`: `r.get("type") == "category"` / `"city"` — filter by `type` key.
- Grep `test_autocomplete_template.py` for `"type"`/`"source"` — 0 matches (this template test does not assert on these keys).
- `SearchSuggestionSource` StrEnum at `core/enums.py:179-185` — confirmed: `USER_HISTORY="user_history"`, `POPULAR_SEARCH="popular_search"`, `CATEGORY="category"`, `CITY="city"`.

**Architectural Fit:** ALIGNS with §4(a) (no untyped `Any`), §4(f) (Pydantic v2 DTO at web boundary), §4(b) (StrEnum for fixed values). The untyped `dict[str, Any]` return violates the boundary-DTO requirement. The untyped `list[dict]` on `get_entity_suggestions` and `get_popular_suggestions` compounds the issue.

**Rollout Safety:** The Pydantic DTO extraction is non-breaking if the DTO preserves all existing keys (`text`, `source`, `type`, plus extras like `slug`, `category_path`, `hit_count`). The `type` key must be preserved (or frontend+tests updated in lockstep) — see validation note. Low risk.

---

### QLT-003: Analytics event recording is not centralized — registration + publish recorded inline in two process-specific sites instead of a single shared helper

| Field | Value |
|-------|-------|
| **ID** | QLT-003 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/telegram_bot/handlers/login.py:190-194` (REGISTRATION_CREATED inline + eager f-string log); `src/backend/apps/moderation/services/auto_moderation.py:234,251,257` (MODERATION_REJECTED, AD_PUBLISHED, MODERATION_APPROVED inline); vs. centralized `src/backend/apps/core/services/contact.py:114,118,133,137` |
| **Classification** | advisory |
| **Validation Status** | **VALIDATED** |

**Evidence Quality:** HIGH — all line references verified exact.

**Validator's Verification:**

- Read `login.py:155-197` — confirmed:
  - Line 190: `AnalyticsEvent.objects.create(event_type=AnalyticsEventType.REGISTRATION_CREATED, user_id=user.id)` — inline, inside `sync_to_async` closure `_handle()`, no try/except. Confirmed.
  - Line 194: `logger.info(f"Registration event recorded for user {user.id}")` — eager f-string interpolation (the one logging-style violation in prod non-test code). Confirmed.
- Read `auto_moderation.py:225-260` — confirmed:
  - Line 234: `AnalyticsEvent.objects.create(event_type=AnalyticsEventType.MODERATION_REJECTED, user_id=ad.user_id, ad_id=ad.id)` — inline, inside `_fail_moderation`. Confirmed.
  - Line 231: `with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]` — wraps the create. Confirmed.
  - Line 251: `AnalyticsEvent.objects.create(event_type=AnalyticsEventType.AD_PUBLISHED, user_id=ad.user_id, ad_id=ad.id)` — inline, inside `_pass_moderation`. Confirmed.
  - Line 257: `AnalyticsEvent.objects.create(event_type=AnalyticsEventType.MODERATION_APPROVED, user_id=ad.user_id, ...)` — inline. Confirmed.
- Read `core/services/contact.py:97-141` — confirmed:
  - Lines 114-117: `record_contact_initiated()` creates `AnalyticsEvent` at `core/services/contact.py:114`. Confirmed.
  - Line 118: `logger.info("Contact initiated event recorded for buyer %s", user_id)` — lazy `%s` interpolation. Confirmed.
  - Lines 133-136: `record_contact_response()` creates `AnalyticsEvent` at `core/services/contact.py:133`. Confirmed.
  - Line 137: `logger.info("Contact response event recorded for seller %s", user.id)` — lazy `%s` interpolation. Confirmed.
- Pattern confirmed: contact uses a centralized service with lazy logging; registration and moderation publish events are inline with an eager f-string at the registration site.

**Architectural Fit:** ALIGNS with §4(i) (shared rules in one service layer, not duplicated across handlers/processes) and §12 (lazy logging style). The contact pattern is the established convention; the other two sites deviate.

**Rollout Safety:** Non-atomic, incremental. Introduce `core/services/analytics.py` with `record_event(...)`; route login.py:190 and auto_moderation.py:234,251,257 through it. No behavioral change (same event types, same fields). The f-string→`%s` change at login.py:194 is a trivial string-format fix.

---

### QLT-004: Undocumented broad `# pyright: ignore[reportGeneralTypeIssues]` suppressions mask Django async/ORM type-checker friction

| Field | Value |
|-------|-------|
| **ID** | QLT-004 |
| **Severity** | MEDIUM |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `ad_create.py:1201`; `login.py:166,174`; and repo-wide — 29 blanket suppressions across ~17 files |
| **Classification** | advisory |
| **Validation Status** | **VALIDATED** with quantitative correction (29, not "30+") |

**Evidence Quality:** MEDIUM-HIGH — all specific file:line references verified correct. The count claim "30+" is an overstatement; actual is 29.

**Validator's Verification:**

- Grep `pyright: ignore\[reportGeneralTypeIssues\]` across `src/` — returned exactly **29 matches** (not "30+" as the finding states). All 29 sites verified:
  - 28 are `with transaction.atomic():` context managers (the documented Django ORM/async friction point).
  - 1 is `priority_calculator.py:63` — a `for word in criteria.banned_words:` loop (NOT a `transaction.atomic()` block). This is a `for`-loop iteration type issue, a different pattern from the majority.
- Full list of files and lines:
  | File | Lines | Pattern |
  |------|-------|---------|
  | `telegram_bot/handlers/login.py` | 166, 174 | `transaction.atomic()` |
  | `telegram_bot/handlers/ad_create.py` | 1201 | `transaction.atomic()` |
  | `apps/ads/services/copy_service.py` | 28 | `transaction.atomic()` |
  | `apps/analytics/management/commands/rollup_daily_metrics.py` | 42 | `transaction.atomic()` |
  | `apps/moderation/admin_actions.py` | 103 | `transaction.atomic()` |
  | `apps/users/views/consent.py` | 380 | `transaction.atomic()` |
  | `apps/users/services/deletion.py` | 116 | `transaction.atomic()` |
  | `apps/media/management/commands/backfill_thumbnails.py` | 56 | `transaction.atomic()` |
  | `apps/media/management/commands/sweep_orphaned_media.py` | 86 | `transaction.atomic()` |
  | `apps/moderation/services/priority_calculator.py` | 63 | `for` loop (not `transaction.atomic()`) |
  | `apps/search/management/commands/send_alerts.py` | 50 | `transaction.atomic()` |
  | `apps/moderation/services/moderation_log.py` | 182, 198, 218 | `transaction.atomic()` (×3) |
  | `apps/moderation/services/auto_moderation.py` | 231, 248 | `transaction.atomic()` (×2) |
  | `apps/seed/services/seed_service.py` | 90, 233 | `transaction.atomic()` (×2) |
  | `apps/currencies/management/commands/recompute_normalized_prices.py` | 51 | `transaction.atomic()` |
  | `apps/core/management/commands/cleanup_login_tokens.py` | 40 | `transaction.atomic()` |
  | `apps/core/management/commands/archive_sweep.py` | 40 | `transaction.atomic()` |
  | `apps/core/management/commands/consent_hard_delete.py` | 45 | `transaction.atomic()` |
  | `apps/core/management/commands/purge_deleted_ads.py` | 44 | `transaction.atomic()` |
  | `apps/core/management/commands/delete_sweep.py` | 43 | `transaction.atomic()` |
  | `apps/core/management/commands/purge_failed_ads.py` | 42 | `transaction.atomic()` |
  | `apps/core/management/commands/purge_rejected_ads.py` | 43 | `transaction.atomic()` |
  | `apps/core/management/commands/sweep_drafts.py` | 42 | `transaction.atomic()` |
  | **Total** | **29** | **28 `transaction.atomic()` + 1 `for` loop** |
- Confirmed by running `uv run basedpyright src/backend src/telegram_bot` → `0 errors, 0 warnings, 0 notes`. The 0-error result is maintained in part by these inline suppressions: removing them would surface `reportGeneralTypeIssues` violations for Django's loosely-typed ORM/async context managers.
- Read `basedpyright` config in `pyproject.toml:194-202` — confirms `typeCheckingMode = "standard"` (NOT "strict" as the phase scope describes), with `reportArgumentType`, `reportCallIssue`, `reportMissingImports`, etc. set to `"none"` at config level. `reportGeneralTypeIssues` is NOT overridden, so it IS enforced at the "standard" level — the inline `# pyright: ignore` comments are what suppress it for these specific lines.

**Architectural Fit:** ALIGNS with §4(a) which allows `Any`/ignores only where a framework signature forces it and requires documentation. The `transaction.atomic()` context-manager typing friction is a known Django/pyright issue that warrants scoped, documented ignores (e.g. `# Django: transaction.atomic() returns an untyped context manager stub`), not blanket `reportGeneralTypeIssues` catches.

**Quantitative Correction:** The finding states "30+ blanket suppressions." Grep confirms 29. This is a minor overstatement. The substance (blanket suppression without rationale across ~17 files, masking real type errors) is accurate and undisputed.

**Rollout Safety:** Comment-only, zero-risk. The existing `# pyright: ignore[reportGeneralTypeIssues]` already names the specific rule (it is not a silent/blanket catch) — the only gap is a missing rationale. Add a rationale to all 29 sites documenting the verified root cause: `django-stubs` is not a project dependency (`reportMissingTypeStubs = "none"` at `pyproject.toml:196`; neither runtime deps `pyproject.toml:10-29` nor dev deps `pyproject.toml:208-218` list it), so Django ORM APIs — `transaction.atomic()` / `Atomic`'s context-manager protocol and `JSONField` attributes — are untyped to basedpyright, while `reportGeneralTypeIssues` is enforced (not overridden to `"none"` at `pyproject.toml:194-202`). Follow the project's existing `# noqa: RULE - rationale` separator convention (e.g. `# noqa: F401 - side-effect: register signals`): for the 28 `transaction.atomic()` sites append ` - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped` after the `]` in `# pyright: ignore[reportGeneralTypeIssues]`; for `priority_calculator.py:63` append ` - Django: django-stubs not installed; JSONField 'banned_words' has no static type`. No runtime, import, or module change — 0 lines of executable code added. **Rejected alternative — typed wrapper:** A `@contextmanager` wrapper around `transaction.atomic()` would (a) discard `Atomic`'s dual context-manager/decorator usage and savepoint-nesting semantics, (b) fail to cover the 1 non-`atomic()` site (`priority_calculator.py:63`, a `JSONField` `for` loop) leaving it still blanketed, and (c) force re-imports across 28 sites for a cosmetic concern — violating project rules #4 (small focused modules) and #5 (avoid overengineering). Ruff config (`select = ["E","F","I","B","UP"]`; no `PGH` rules at `pyproject.toml:123-129`) imposes no ignore-code requirement, so a rationale comment is the sole change needed.

---

### QLT-005: Production lookup-cache service returns untyped `list[Any]` (and `apps: Any` on catalog builder), eroding the shared-type seam

| Field | Value |
|-------|-------|
| **ID** | QLT-005 |
| **Severity** | LOW |
| **Type** | BEST-PRACTICE |
| **Affected Modules** | `src/backend/apps/lookups/services/cache_service.py:9,28,34,47,56`; `src/backend/apps/categories/catalog/builder.py:33,55` |
| **Classification** | advisory |
| **Validation Status** | **VALIDATED** with line-reference corrections |

**Evidence Quality:** MEDIUM — substance correct, but line references for `builder.py` in the original finding are inaccurate (corrected below).

**Validator's Verification:**

- Read `cache_service.py:1-92` — confirmed:
  - Line 9: `from typing import Any` — confirmed.
  - Line 28: `def get_all_groups() -> list[Any]:` — confirmed (docstring at 29-33 says "List of LookupGroup instances").
  - Line 34: `from apps.lookups.models import LookupGroup` — deferred import inside the function body; concrete type is knowable. Confirmed.
  - Line 47: `def get_active_items(group_code: str) -> list[Any]:` — confirmed (docstring at 49-55 says "List of active LookupItem instances").
  - Line 56: `from apps.lookups.models import LookupItem` — deferred import inside the function body; concrete type is knowable. Confirmed.
- Read `builder.py:1-57` — **corrected line references**:
  - The finding cites `builder.py:17` for `from typing import Any` — **incorrect**. Actual line is **33** (`from typing import Any`).
  - The finding cites `builder.py:36` for `apps: Any = None` — **incorrect**. Actual line is **55** (`apps: Any = None`) in the `load_catalog()` signature at `builder.py:53-57`.
  - The finding cites `builder.py:2,34` for "docstring documents apps.get_model()" — the module docstring starts at line 2; the `apps.get_model()` documentation is in `load_catalog`'s docstring at lines 86-92 (not line 34). The substance (docstring documents `apps.get_model()`) is accurate.
- Read `builder.py:50-74` — confirmed `load_catalog` signature at lines 53-57: `def load_catalog(config_path: str | Path, apps: Any = None, rewrite_yaml: bool = True) -> dict[str, str]:`. The `apps` parameter docstring (lines 86-92) documents it as "Django migration apps registry (`apps.get_model()`) when called from a migration; `None` for standalone/live usage." Django exposes `django.apps.Apps` for this — the `Any` is avoidable.
- Confirmed by running `uv run basedpyright src/backend src/telegram_bot` → `0 errors, 0 warnings, 0 notes`. These `Any` types pass because they opt out of checking — `LookupGroup`/`LookupItem` are imported inside the function body (line 34/56), proving the concrete types are directly available; `apps` can be typed as `django.apps.Apps | None`.
- `AutocompleteSuggestion` DTO (QLT-002) and this finding share the theme of untyped returns at shared seams — but they are in different modules and should be fixed independently.

**Architectural Fit:** ALIGNS with §4(a) (no `Any` masking real issues), §4(d) (thin adapters + shared types), §4(i) (shared business-logic/seam layer). The lookup cache is consumed by the web process for category/listing rendering and autocomplete — an untyped return erodes the seam.

**Rollout Safety:** Trivial. Replace `list[Any]` → `list[LookupGroup]` / `list[LookupItem]` (deferred import already in scope); replace `apps: Any` → `Apps | None` (import `from django.apps import Apps`). No runtime behavior change.

---

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 3 | QLT-001, QLT-003, QLT-004 |
| Reclassified | 0 | — |
| **Validated with correction note** | 2 | QLT-002 (type-key downstream consumers caveat); QLT-005 (builder.py line-reference corrections) |
| Merged | 0 | — |
| Rejected | 0 | — |

### Findings by Severity (Post-Validation)

| Severity | Count | IDs |
|----------|-------|-----|
| CRITICAL | 0 | — |
| HIGH | 1 | QLT-001 |
| MEDIUM | 3 | QLT-002, QLT-003, QLT-004 |
| LOW | 1 | QLT-005 |
| **Total** | **5** | |

### Evidence Quality Assessment

| ID | Evidence Quality | Notes |
|----|------------------|-------|
| QLT-001 | **High** | All 6 inline-logic segments, file line count (1506, verified via Python), services-dir listing, edit.py re-implementation — all verified at exact line numbers. |
| QLT-002 | **High** | `dict[str, Any]`, duplicate keys, no-Pydantic, and all 12+ downstream test/template consumers verified. CAVEAT added: `type` key is actively consumed by `header_catalog.html:313,327` and tests — not droppable without coordination. |
| QLT-003 | **High** | All 3 inline `AnalyticsEvent.objects.create()` sites (login.py:190, auto_moderation.py:234/251/257) and the centralized contact.py pattern (lazy `%s` logging) verified exact. |
| QLT-004 | **Medium-High** | All 29 suppression sites verified across 17 files with exact patterns (`transaction.atomic()` ×28 + `for` loop ×1). Count is 29, not "30+" (minor overstatement). Config verified: `typeCheckingMode = "standard"` (not "strict" as phase scope claims). |
| QLT-005 | **Medium** | `list[Any]` returns, deferred model imports, and `apps: Any` all verified. **Line references for `builder.py` are inaccurate**: `from typing import Any` at line 33 (cited as 17); `apps: Any = None` at line 55 (cited as 36). Substance fully correct. |

### Rejected Findings

None.

### Merged Findings

None.

### Reclassified Findings

None formally reclassified (all retain original types). QLT-002 and QLT-005 received validation **correction notes** rather than type changes because the underlying spec violations are genuine.

---

## Rollout Recommendations (Priority Order)

1. **QLT-001 (HIGH)** — Extract ad-submission orchestrator into `apps/ads/services/submission.py`. Atomic: move field-assembly, currency/price normalization, thumbnail+AdImage persistence, and DRAFT→ON_MODERATION transition out of `ad_create.py` and `edit.py` into one shared entry point. Makes the web edit view reuse the bot's submission path (DRY). Effort: large.
2. **QLT-003 (MEDIUM)** — Introduce `core/services/analytics.py` with `record_event(...)`; route `login.py:190` and `auto_moderation.py:234/251/257` through it; switch login.py:194 f-string to lazy `%s`. Effort: small. Complements QLT-001 (extracted orchestrator can call the centralized recorder).
3. **QLT-002 (MEDIUM)** — Model autocomplete with a Pydantic `AutocompleteSuggestion` DTO; serialize via `model_dump(mode="json")`. **Do NOT drop `type` yet** — it is consumed by `header_catalog.html:313,327` and asserted in 12+ test locations. Deprecate gradually or update consumers in lockstep. Effort: small.
4. **QLT-004 (MEDIUM)** — Add a rationale comment to each existing rule-scoped `# pyright: ignore[reportGeneralTypeIssues]` across all 29 sites (28 `transaction.atomic()` + 1 `JSONField` `for` loop), documenting the verified root cause: `django-stubs` is not a project dependency so Django ORM context-manager/JSONField APIs are untyped, while `reportGeneralTypeIssues` is enforced at config. Follow the `# noqa: RULE - rationale` separator convention already used in the codebase. Comment-only, zero-risk; no imports, modules, or runtime change. Effort: small.
5. **QLT-005 (LOW)** — Type `LookupCacheService.get_all_groups`/`get_active_items` with concrete `LookupGroup`/`LookupItem`; type `builder.load_catalog`'s `apps` as `Apps | None`. Effort: trivial.

### Cross-Finding Rollout Ordering

- **QLT-001 → QLT-003 (recommended first):** Extract submission orchestrator (QLT-001) first, then centralize analytics within the new service layer (QLT-003). The `auto_moderate(ad)` call at `ad_create.py:1233` stays in the orchestrator; its inline `AnalyticsEvent.objects.create` calls move to `core/services/analytics.py`. No circular dependency — `submission.py` would depend on `apps.ads.models` + `apps.moderation.services` + `apps.core.services.analytics`, all of which already depend on `apps.ads.models`.
- **QLT-002 and QLT-005 are independent** — can be applied in parallel with no shared files.
- **QLT-004 is a pure comment-only refactor** — safe to apply anywhere in the sequence; no behavioral impact.
- **QLT-002's `type`-key removal is NOT recommended** in this phase — flag it for a coordinated frontend+test update in a follow-up phase. The Pydantic DTO extraction (keeping `type`) is safe to do now.

### Rollout Safety

- No circular dependencies introduced by any recommendation.
- No fragile insertion points (all target stable, named functions/classes/methods).
- QLT-002 `type`-key removal was the only fragile point — flagged and deferred.
- All fixes are additive or comment-only; no schema or migration changes required.
