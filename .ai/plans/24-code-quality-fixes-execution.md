---
id: 24-code-quality-fixes-execution
domain: plan
tags:
  - code-quality
  - qlt-001
  - qlt-002
  - qlt-003
  - qlt-004
  - qlt-005
  - submission-orchestrator
  - analytics-dr
  - autocomplete-dto
  - pyright-ignores
  - typing-hygiene
related:
  - .ai/audit/99-validation/10-code-quality-validated-findings.md
  - .ai/audit/99-validation/10-code-quality-source-reaudit.md
  - .ai/tasks/templates/task_template.yaml
  - .ai/tasks/templates/task_template_verification.yaml
  - src/backend/apps/core/services/analytics.py
  - src/backend/apps/core/services/__init__.py
  - src/backend/apps/core/services/contact.py
  - src/backend/apps/core/tests/test_analytics_service.py
  - src/telegram_bot/handlers/ad_create.py
  - src/telegram_bot/handlers/login.py
  - src/backend/apps/ads/services/
  - src/backend/apps/ads/views/edit.py
  - src/backend/apps/moderation/services/auto_moderation.py
  - src/backend/apps/analytics/services/trust_analytics.py
  - src/backend/apps/ads/views/listings.py
  - src/backend/apps/search/views/search.py
  - src/backend/apps/search/views/autocomplete.py
  - src/backend/apps/search/services/entity_suggestions.py
  - src/backend/apps/search/services/popular_search.py
  - src/backend/apps/search/services/search_history.py
  - src/backend/templates/components/header_catalog.html
  - src/backend/apps/lookups/services/cache_service.py
  - src/backend/apps/categories/catalog/builder.py
  - src/backend/apps/ads/tests/test_save_photo_integration.py
  - src/backend/apps/search/tests/test_autocomplete.py
  - src/backend/apps/seed/management/commands/send_alerts.py
  - pyproject.toml
  - AGENTS.md
  - .kilo/rules/commands.md
---

# Code-Quality Finding Fixes — Execution Plan (Phase 10)

**Plan ID:** `24-code-quality-fixes-execution`  
**Source:** `.ai/audit/99-validation/10-code-quality-validated-findings.md` (validated 2026-09-05)  
**Source re-audit:** `.ai/audit/99-validation/10-code-quality-source-reaudit.md` (2026-09-11)  
**Status:** QLT-003 partially implemented (Sep 8); QLT-001/002/004/005 remain open. 12 execution blocks across 5 findings.  
**Generated:** 2026-09-11 — Planning only. No code modified.

---

## 1. Baseline — What Is Already Done

QLT-003's core recommendation was **already implemented** by commit `5b80f7b` (Sep 8):

| Deliverable | Status | Details |
|---|---|---|
| `apps/core/services/analytics.py` | **Done** | `record_event(event_type, user_id=None, *, ad_id=None, source=None) -> AnalyticsEvent \| None` — transaction-transparent (bare `.objects.create()`, no own `atomic()`), catches all exceptions, uses lazy `%s` logging, annotated `# noqa: BLE001 — analytics must never break the request` |
| `record_event` export in `__init__.py` | **Missing** | `core/services/__init__.py` exports `record_contact_initiated`/`record_contact_response` from `.contact` but does NOT export `record_event` — inconsistency |
| Wired into `listings.py` (AD_VIEWED) | **Done** | `apps/ads/views/listings.py` — `record_event(AnalyticsEventType.AD_VIEWED, user_id=ad.user_id, ad_id=ad.id)` |
| Wired into `search.py` (SEARCH_PERFORMED) | **Done** | `apps/search/views/search.py` — `record_event(AnalyticsEventType.SEARCH_PERFORMED, user_id=...)` |
| Existing tests | **Partial** | `apps/core/tests/test_analytics_service.py` — 4 tests (happy path, minimal call, anonymous, failure). **No rollback-gate test.** |

QLT-001, QLT-002, QLT-004, QLT-005 remain **not implemented**.

---

## 2. Remaining Work Summary

| # | Block ID | Finding | Scope | Agents | Risk |
|---|----------|---------|-------|--------|------|
| 1 | `qlt004_pyright_rationale` | QLT-004 | Add rationale to 39 `# pyright: ignore[reportGeneralTypeIssues]` sites (37 prod + 2 test) | Implementor | zero (comment-only) |
| 2 | `qlt005_typing_hygiene` | QLT-005 | Replace `list[Any]`/`apps: Any`/`session: Any` with concrete types across 3 files | Implementor | trivial |
| 3 | `qlt002_autocomplete_dto` | QLT-002 | Pydantic `AutocompleteSuggestion` DTO; preserve `type` key | Implementor | low |
| 4 | `qlt003_contact_migration` | QLT-003a | Migrate `contact.py` creates to `record_event` + export from `__init__.py` | Implementor | low |
| 5 | `qlt003_login_migration` | QLT-003b | Migrate `login.py` REGISTRATION_CREATED to `record_event` (also fixes eager f-string) | Implementor | low |
| 6 | `qlt003_auto_moderation_migration` | QLT-003c | Migrate 3 inline creates in `auto_moderation.py` (inside atomics) to `record_event` | Implementor | medium (inside atomic) |
| 7 | `qlt003_trust_analytics_migration` | QLT-003d | Migrate `trust_analytics.py` `record_trust_event` to delegate to `record_event` | Implementor | low |
| 8 | `qlt003_rollback_gate_test` | QLT-003f | Add rollback-gate test to `test_analytics_service.py` | Validator | low |
| 9 | `qlt001_stage1_inert_submission` | QLT-001 | Introduce inert `submission.py` with `SubmitAdInput` + `submit_ad()` | Implementor | large (new module) |
| 10 | `qlt001_stage2_bot_rewire` | QLT-001 | Replace `update_ad_and_moderate` call in `process_preview` with `submit_ad`; delete old function; update `test_save_photo_integration.py` imports | Implementor | medium (bot rewire) |
| 11 | `qlt001_stage1.5_test_edit` | QLT-001 | **BLOCKING:** Create `apps/ads/tests/test_edit.py` for reactivation path | Implementor | medium |
| 12 | `qlt001_stage3_edit_migration` | QLT-001 | Migrate `edit.py` reactivation branch through `submit_ad` (currency coercer gate) | Implementor | medium (behavioral risk) |

**Deferred (out of phase scope):**
- QLT-001 Stage 4 (QLT-00003 application at orchestrator seam) — absorbed into QLT-003 blocks above (see §4).
- QLT-003 batch site: `send_alerts.py` `AnalyticsEvent.objects.bulk_create` — deferred to Phase 01 ENT-007.
- QLT-003 ENT-007 sites: `listings.py` + `search.py` — already migrated via `record_event`.
- QLT-001 `ad_reactivate` view (separate from `ad_edit` reactivation branch) — secondary DRY target, note only.

---

## 3. QLT-001 → QLT-003 Ordering Assessment

> **The original findings recommended QLT-001 before QLT-003 for "pattern coherence" — extracting the submission orchestrator first, then centralizing analytics at that orchestrator→`auto_moderate` seam.**

**This ordering constraint has relaxed.** Assessment:

1. **`record_event` already exists and is stable** (created Sep 8). The canonical recording helper is available — QLT-003 no longer needs to "introduce" it.
2. **The remaining QLT-003 migration targets are inside those modules' own function bodies** — `contact.py`'s `record_contact_initiated`/`record_contact_response`, `login.py`'s `_handle` closure, `auto_moderation.py`'s `_fail_moderation`/`_pass_moderation`, and `trust_analytics.py`'s `record_trust_event`. None of these are in the orchestrator code that QLT-001 extracts.
3. **`auto_moderate()` is called from both the bot handler and the web edit view.** QLT-001's extraction (Stage 2) moves the *calling* orchestration (field assembly, thumbnails, DB writes, status transition) into `submit_ad`, but `auto_moderate` itself remains a called service with the same internal structure. The inline creates inside `auto_moderate` (in `_fail_moderation`/`_pass_moderation`) are unchanged by QLT-001.
4. **`ad_create.py` and `auto_moderation.py` are different files.** QLT-001 modifies `ad_create.py` (bot handler) and `edit.py` (web view); QLT-003 modifies `auto_moderation.py` (moderation service). No file-level overlap → no merge conflict.

**Conclusion:** QLT-001 and QLT-003 can proceed **in parallel**. The "pattern coherence" goal is achieved by simply calling `record_event` from within `auto_moderate` — no dependency on `submission.py`. The QLT-001 Stage 4 recommendation ("Apply QLT-003") is removed from the QLT-001 sequence; QLT-003 is fully self-contained.

---

## 4. Dependency DAG

```
                          QLT-001 (sequential chain)
                          ─────────────────────────
  qlt001_stage1_inert_submission (A1)              ◄── no predecessor
          │
          └──► qlt001_stage2_bot_rewire (A2)        ◄── depends: A1
          │
  qlt001_stage1.5_test_edit (A3)                   ◄── independent
          │                                           (tests vs handler files)
          └──► qlt001_stage3_edit_migration (A4)   ◄── depends: A1, A3
              [currency_coercer decision gate]      (also depends on A1's submit_ad
               existing & A3's behavioral baseline) and the gate

                          QLT-002 (single block)
                          ─────────────────────
  qlt002_autocomplete_dto (B1)                     ◄── independent

                          QLT-003 (independent cluster)
                          ────────────────────────────
  All depend on record_event existing (DONE Sep 8).
  All touch disjoint files — parallel-safe.

  qlt003_contact_migration (C1)                     ◄── independent
  qlt003_login_migration (C2)                       ◄── independent
  qlt003_auto_moderation_migration (C3)             ◄── independent
  qlt003_trust_analytics_migration (C4)             ◄── independent
  qlt003_rollback_gate_test (C5)                    ◄── independent
          │                                           (validates C3's atomicity)
          (file-sharing note: C3 + D1 both touch     but not blocked on them)
          auto_moderation.py — sequential if
          multiple Implementors)

                          QLT-004 (comment-only)
                          ─────────────────────
  qlt004_pyright_rationale (D1)                     ◄── independent (comment-only
                                                        no runtime/import/module change)

                          QLT-005 (trivial typing)
                          ────────────────────────
  qlt005_typing_hygiene (E1)                        ◄── independent (trivial type
                                                        annotation changes)
```

**Parallel-safe groups** (disjoint files, can execute concurrently if multiple Implementors available):
- `{B1, C1, C2, C3, C4, C5, D1, E1}` — all disjoint files
- `A3` is parallel-safe with `A1` and `A2` (test files vs handler code)

**Sequential chains:**
- `A1 → A2 → A4` (QLT-001 stages; `A3` is a parallel-safe precondition for `A4`)
- `A4` blocked on `currency_coercer decision gate`

**File-sharing constraint (same file, sequential):**
- `C3` (auto_moderation.py creates → record_event) and `D1` (pyright ignore rationale) both edit `auto_moderation.py` — if running with multiple Implementors, execute sequentially. With a single Implementor this is naturally sequential.

---

## 5. Rollout Sequence

| Step | Block | Parallel-safe with | Notes |
|------|-------|-------------------|-------|
| 1 | `qlt004_pyright_rationale` (D1) | all other blocks | Zero-risk comment-only; builds momentum. |
| 2 | `qlt005_typing_hygiene` (E1) | D1 done; B1, C1–C5 | Trivial type annotations; disjoint files. |
| 3 | `qlt002_autocomplete_dto` (B1) | D1, E1, C1–C5 | Small Pydantic DTO; preserves `type` key. |
| 4 | `qlt003_contact_migration` (C1) | D1, E1, B1, C2–C5 | Establishes `__init__.py` export consistency. |
| 5 | `qlt003_login_migration` (C2) | all (disjoint) | Also fixes eager f-string. |
| 6 | `qlt003_auto_moderation_migration` (C3) | D1 sequential (same file); others parallel-safe | Highest-risk QLT-003 site (inside atomics). |
| 7 | `qlt003_trust_analytics_migration` (C4) | all (disjoint) | One call site. |
| 8 | `qlt003_rollback_gate_test` (C5) | all (disjoint) | Validates C3's transaction transparency. |
| 9 | `qlt001_stage1_inert_submission` (A1) | A3, D1, E1, B1, C1–C5 | New `submission.py`, no callers — inert. |
| 10 | `qlt001_stage2_bot_rewire` (A2) | A3, and all QLT-002/003/004/005 blocks | Deletes `update_ad_and_moderate`. |
| 11 | `qlt001_stage1.5_test_edit` (A3) | A1, A2, and all other blocks | BLOCKING precondition for A4. |
| 12 | `qlt001_stage3_edit_migration` (A4) | — | Depends: A1 ✓, A3 ✓, Currency Gate. |

**PR grouping recommendation:**
- **PR 1:** D1 + E1 (momentum: comment rationale + trivial typing)
- **PR 2:** B1 (QLT-002 Pydantic DTO)
- **PR 3:** C1 + C2 + C4 (QLT-003 migrations — disjoint files, can be one PR)
- **PR 4:** C3 + C5 (QLT-003 auto_moderation migration + rollback test — atomic pair)
- **PR 5:** A1 + A2 + A3 + A4 (QLT-001 staged extraction — sequential within PR)

> The single-Implementor constraint makes parallel-safe blocks effectively sequential. The only **hard ordering constraints** are: A1→A2→A4, A4→{A1, A3, Currency Gate}, A4-after-A3. Everything else is interchangeable.

---

## 6. Execution Blocks

<!-- TASK_START: qlt004_pyright_rationale -->

### Block 1: QLT-004 — Add rationale to all `# pyright: ignore[reportGeneralTypeIssues]` suppressions

```yaml
id: qlt004_pyright_rationale
title: "QLT-004: Append rationale comment to all 39 pyright:ignore[reportGeneralTypeIssues] sites"
source_reference: .ai/plans/24-code-quality-fixes-execution.md
source_section: "Block 1: QLT-004"
priority: medium
depends_on: []              # comment-only, zero-risk, safe to do first
classification: advisory
risk: zero                  # no runtime, import, module, or logic change
agents: [Implementor]
```

**Description:**  
QLT-004 targets blanket `# pyright: ignore[reportGeneralTypeIssues]` suppressions that mask Django ORM/async type-checker friction without a rationale. The count is **39** (corrected from findings' 29): 37 production + 2 test, across 27 files. 28 sites suppress `django.db.transaction.atomic()` context-manager typing friction; 1 site (`priority_calculator.py` `for word in criteria.banned_words:`) suppresses a `JSONField` iteration typing issue. The remaining 10 sites were added by post-validation commits (Sep 8–9) and were missing from the original findings table entirely.

The root cause (verified by re-audit): `django-stubs` is **not** a project dependency (`pyproject.toml` has no `django-stubs` in runtime or dev groups), so Django ORM context-manager protocols and `JSONField` attributes are untyped to basedpyright, while `reportGeneralTypeIssues` IS enforced (it is NOT overridden to `"none"` in `pyproject.toml [tool.basedpyright]`).

**Rationale text to append:**

| Pattern | Rationale text (appended after `]`) |
|---|---|
| `with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]` | `- Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped` |
| `for word in criteria.banned_words:  # pyright: ignore[reportGeneralTypeIssues]` | `- Django: django-stubs not installed; JSONField 'banned_words' has no static type` |

Follows the project's existing `# noqa: RULE - rationale` separator convention (confirmed at `analytics.py:52`, `apps/core/apps.py:20`, `apps/moderation/apps.py:18`, etc.).

**Implementation scope (semantic — files + functions/symbols):**

Production files (37 sites, 26 files):

| File | Symbols affected | Pattern |
|---|---|---|
| `telegram_bot/handlers/login.py` | `handle_login_orm` (`_handle` closure) | `transaction.atomic()` ×2 |
| `telegram_bot/handlers/ad_create.py` | `update_ad_and_moderate` (`_update_and_moderate`) | `transaction.atomic()` ×1 |
| `apps/ads/views/edit.py` | `ad_edit`, `ad_archive`, `ad_reactivate` | `transaction.atomic()` ×3 |
| `apps/ads/services/copy_service.py` | `copy_ad` | `transaction.atomic()` ×1 |
| `apps/analytics/management/commands/rollup_daily_metrics.py` | command `handle` | `transaction.atomic()` ×1 |
| `apps/moderation/admin_actions.py` | `_bulk_action_loop`, `bulk_reject`, `bulk_delete` | `transaction.atomic()` ×4 |
| `apps/moderation/views/review.py` | `reject_ad`, `approve_ad` | `transaction.atomic()` ×2 |
| `apps/moderation/services/moderation_log.py` | `_fail_moderation`, `_pass_moderation`, `record_moderation_log` | `transaction.atomic()` ×3 |
| `apps/moderation/services/auto_moderation.py` | `_fail_moderation`, `_pass_moderation` | `transaction.atomic()` ×2 |
| `apps/moderation/services/priority_calculator.py` | `calculate_priority` | `for word in criteria.banned_words:` ×1 |
| `apps/categories/catalog/builder.py` | `load_catalog` | `transaction.atomic()` ×1 |
| `apps/seed/services/seed_service.py` | `_seed_ads`, `_seed_categories` | `transaction.atomic()` ×2 |
| `apps/currencies/management/commands/recompute_normalized_prices.py` | command `handle` | `transaction.atomic()` ×1 |
| `apps/media/management/commands/backfill_thumbnails.py` | command `handle` | `transaction.atomic()` ×1 |
| `apps/media/management/commands/sweep_orphaned_media.py` | command `handle` | `transaction.atomic()` ×1 |
| `apps/search/management/commands/send_alerts.py` | management command | `transaction.atomic()` ×1 |
| `apps/users/views/consent.py` | `consent_view` | `transaction.atomic()` ×1 |
| `apps/users/services/deletion.py` | `delete_user` | `transaction.atomic()` ×1 |
| `apps/core/management/commands/cleanup_login_tokens.py` | command `handle` | `transaction.atomic()` ×1 |
| `apps/core/management/commands/archive_sweep.py` | command `handle` | `transaction.atomic()` ×1 |
| `apps/core/management/commands/consent_hard_delete.py` | command `handle` | `transaction.atomic()` ×1 |
| `apps/core/management/commands/purge_deleted_ads.py` | command `handle` | `transaction.atomic()` ×1 |
| `apps/core/management/commands/delete_sweep.py` | command `handle` | `transaction.atomic()` ×1 |
| `apps/core/management/commands/purge_failed_ads.py` | command `handle` | `transaction.atomic()` ×1 |
| `apps/core/management/commands/purge_rejected_ads.py` | command `handle` | `transaction.atomic()` ×1 |
| `apps/core/management/commands/sweep_drafts.py` | command `handle` | `transaction.atomic()` ×1 |

Test files (2 sites, 1 file):

| File | Symbols affected | Pattern |
|---|---|---|
| `apps/ads/tests/test_edit_views_locking.py` | test methods for locking | `transaction.atomic()` ×2 |

**Two-pass approach (recommended for momentum):**
- Pass 1: 10 post-validation sites not in the original findings table (`edit.py` ×3, `review.py` ×2, `builder.py` ×1, `admin_actions.py` ×3, `test_edit_views_locking.py` ×2, `moderation_log.py` ×3 shifted lines).
- Pass 2: 29 sites from the original findings table.

> **Out of scope (NOT part of QLT-004):** `# pyright: ignore[reportArgumentType]` sites in `users/models.py` (×5) and `categories/models.py` (×1); `# pyright: ignore[reportAbstractUsage]` in `telegram_bot/tests/conftest.py` (×1); `# type: ignore[no-redef]` in `builder.py` (×2, mypy). These use different rule codes and are a related but separate hygiene concern.

**Architectural constraints:**
- Ruff config (`pyproject.toml [tool.ruff.lint]`) selects `["E","F","I","B","UP"]` with `ignore = ["E501"]`. No `PGH` rules — no noqa-code requirement. Rationale comment is the sole change.
- The `# noqa: RULE - rationale` separator convention uses ` - ` (space-hyphen-space). Match this for pyright ignores.

**Tests / verification:**
- No test execution needed (comment-only).
- `uv run ruff check src/` — 0 errors (comments are valid).
- `uv run basedpyright src/backend src/telegram_bot` — still 0 errors (comments don't affect type checking).
- Grep verification: all 39 `# pyright: ignore[reportGeneralTypeIssues]` sites now contain ` - Django:` rationale text.

```powershell
# Verify all 39 sites have rationale
uv run ruff check src/ ; uv run basedpyright src/backend src/telegram_bot
```

**Acceptance criteria:**
- All 39 `# pyright: ignore[reportGeneralTypeIssues]` sites have a ` - Django: django-stubs not installed; <untyped API>` rationale appended.
- 28 `transaction.atomic()` sites: rationale = `Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped`.
- 1 `for`-loop site (`priority_calculator.py`): rationale = `Django: django-stubs not installed; JSONField 'banned_words' has no static type`.
- No executable code added; no imports changed; no runtime behavior change.
- `ruff check` and `basedpyright` remain at 0 errors.
- Out-of-scope `reportArgumentType`/`reportAbstractUsage` sites left unchanged.

<!-- TASK_END: qlt004_pyright_rationale -->

---

<!-- TASK_START: qlt005_typing_hygiene -->

### Block 2: QLT-005 — Replace untyped `list[Any]` / `apps: Any` / `session: Any` with concrete types

```yaml
id: qlt005_typing_hygiene
title: "QLT-005: Type LookupCacheService returns, builder.load_catalog apps param, search_history session param"
source_reference: .ai/plans/24-code-quality-fixes-execution.md
source_section: "Block 2: QLT-005"
priority: low
depends_on: []              # trivial; disjoint files
classification: advisory
risk: trivial
agents: [Implementor]
```

**Description:**  
QLT-005 targets untyped `list[Any]` returns and `Any` parameters at shared service seams. Three locations confirmed by re-audit:

1. **`cache_service.py`** — `LookupCacheService.get_all_groups() -> list[Any]` (concrete type: `LookupGroup`, already imported inside the function body at the deferred import) and `get_active_items(group_code) -> list[Any]` (concrete type: `LookupItem`, already imported inside the function body).
2. **`builder.py`** — `load_catalog(config_path, apps: Any = None, ...)`: the `apps` parameter is the Django migration apps registry (`django.apps.Apps`); `Any` is avoidable. Additionally, `search_history.py` (not cited in original findings but identified by re-audit) has untyped `session: Any` at three sites.
3. **`search_history.py`** — `session: Any` at `_record_session_history` signature, `record_search_history` signature, and `get_user_search_history` signature (concrete type: `SessionBase` from `django.contrib.sessions.backends.base`).

**Implementation scope:**

| File | Current | Replace with | Import to add |
|---|---|---|---|
| `lookups/services/cache_service.py` | `from typing import Any` (line 9) | Remove import (if no other `Any` usage) | `LookupGroup` / `LookupItem` already imported in function bodies |
| `lookups/services/cache_service.py` | `get_all_groups() -> list[Any]` | `-> list[LookupGroup]` (deferred import at line 34 already brings `LookupGroup` into scope) | — |
| `lookups/services/cache_service.py` | `get_active_items(...) -> list[Any]` | `-> list[LookupItem]` (deferred import at line 56 already brings `LookupItem` into scope) | — |
| `categories/catalog/builder.py` | `from typing import Any` (line 28) | Keep (used by internal `_load_lookups`/`_load_categories`/`_load_bindings`/`_load_category_paths` dict params) | `from django.apps import Apps` |
| `categories/catalog/builder.py` | `load_catalog(..., apps: Any = None, ...)` | `apps: Apps | None = None` | — |
| `search/services/search_history.py` | `from typing import Any` (line 14) | Remove import; add `from django.contrib.sessions.backends.base import SessionBase` | `SessionBase` |
| `search/services/search_history.py` | `_record_session_history(session: Any, ...)` | `session: SessionBase | None` | — |
| `search/services/search_history.py` | `record_search_history(..., session: Any = None)` | `session: SessionBase | None = None` | — |
| `search/services/search_history.py` | `get_user_search_history(..., session: Any = None)` | `session: SessionBase | None = None` | — |

**Architectural constraints:**
- `cache_service.py` uses **deferred imports** (inside function bodies) for `LookupGroup`/`LookupItem` to avoid circular imports. The return-type annotations must reference types resolved at call time. Since `get_all_groups` and `get_active_items` are standalone `@staticmethod` methods (not part of a model class), the deferred import pattern is safe — the type annotation is evaluated at call time. Use `from __future__ import annotations` at the top if not already present, OR keep deferred imports inside the function body (which already exist).
- `builder.py`'s `apps` parameter: `django.apps.Apps` is the correct type for the migration apps registry. The deferred `apps.get_model()` pattern (at `_load_lookups`, `_load_categories`, etc.) confirms this — `apps` is only used when non-None (migration context) and the type is `Apps | None`.
- `search_history.py`'s `session` parameter: `SessionBase` is the Django abstract base for all session backends (including `db` backend). `from django.contrib.sessions.backends.base import SessionBase` is the correct import.

**Tests / verification:**
- `uv run basedpyright src/backend/apps/lookups/services/cache_service.py src/backend/apps/categories/catalog/builder.py src/backend/apps/search/services/search_history.py`
- `uv run ruff check` on the same three files.
- No functional test required (type annotation only; runtime behavior unchanged).

```powershell
uv run basedpyright src/backend/apps/lookups/services/cache_service.py src/backend/apps/categories/catalog/builder.py src/backend/apps/search/services/search_history.py
```

**Acceptance criteria:**
- `cache_service.py`: `get_all_groups() -> list[LookupGroup]`, `get_active_items(...) -> list[LookupItem]`, no `Any` import remaining if unused.
- `builder.py`: `load_catalog(..., apps: Apps | None = None, ...)` with `from django.apps import Apps` imported.
- `search_history.py`: all three `session` parameters typed `SessionBase | None`, no `Any` import remaining.
- `basedpyright` reports 0 errors on all three files.
- No runtime behavior change (annotations only).

<!-- TASK_END: qlt005_typing_hygiene -->

---

<!-- TASK_START: qlt002_autocomplete_dto -->

### Block 3: QLT-002 — Introduce Pydantic `AutocompleteSuggestion` DTO at the web boundary

```yaml
id: qlt002_autocomplete_dto
title: "QLT-002: Replace untyped dict[str, Any] autocomplete boundary with Pydantic AutocompleteSuggestion DTO"
source_reference: .ai/plans/24-code-quality-fixes-execution.md
source_section: "Block 3: QLT-002"
priority: medium
depends_on: []              # independent — disjoint files from all other blocks
classification: advisory
risk: low                   # non-breaking if all keys preserved; type key NOT dropped
agents: [Implementor]
```

**Description:**  
The autocomplete endpoint returns `list[dict[str, Any]]` — no Pydantic DTO at the web boundary, and all three suggestion producers emit both a `source` and `type` key carrying identical `SearchSuggestionSource` enum values. QLT-002 validates the core issue but adds a critical caveat: the `type` key is **actively consumed** by `header_catalog.html` (line 326: `s.type === section || s.source === section`; line 340: `escapeHtml(s.type || s.source || '')`) and asserted in 12+ test locations in `test_autocomplete.py` (lines 134-136, 221-222, 526-528, 538, 548, 553, 561, 574, 587, 599, 613). The `type` key must be **preserved** (not dropped) — it should be deprecated gradually or kept alongside `source` with coordinated frontend + test updates in a follow-up.

**Viable implementation paths:**

1. **Pydantic DTO with both keys (RECOMMENDED):** Create `AutocompleteSuggestion` model with `text`, `source`, `type`, `slug`, `category_path`, `hit_count` fields. Producers return `list[AutocompleteSuggestion]`; the view serializes via `model_dump(mode="json")`. The `type` key is preserved (kept alongside `source`) — no frontend/test impact. The DTO introduces type safety at the boundary without breaking consumers.
2. **Drop `type` now:** Replace `type` with `source` only. **Rejected** — breaks `header_catalog.html:326,340` and 12+ test assertions without coordinated updates. Fragile insertion point.

**Approach chosen:** Path 1 — Pydantic DTO preserving all existing keys. The `type` key is marked `@deprecated` in the DTO docstring for future gradual removal (Phase 2 coordination with frontend).

**Implementation scope:**

1. **New DTO** — Location TBD by Implementor: either `apps/search/schemas/autocomplete.py` (if a `schemas/` package exists for search) or `apps/search/views/autocomplete.py` (co-located). The DTO class `AutocompleteSuggestion` with fields:
   - `text: str`
   - `source: SearchSuggestionSource`
   - `type: SearchSuggestionSource` (kept for backward compat; `@deprecated` in docstring)
   - `slug: str | None = None`
   - `category_path: str | None = None`
   - `hit_count: int | None = None`

2. **`apps/search/views/autocomplete.py`** — function `autocomplete`:
   - Remove `from typing import Any` import.
   - Change `suggestions: list[dict[str, Any]] = []` to use `list[AutocompleteSuggestion]`.
   - Replace dict-literal construction (`{"text": ..., "source": ..., "type": ...}`) with `AutocompleteSuggestion(...)` instantiation.
   - Replace dedup logic (`item.get("text", "")`) with attribute access (`item.text`).
   - Serialize via `suggestion.model_dump(mode="json")` in the `JsonResponse`.

3. **`apps/search/services/entity_suggestions.py`** — function `get_entity_suggestions`:
   - Change return type from `list[dict]` to `list[AutocompleteSuggestion]`.
   - Replace dict-literal construction with `AutocompleteSuggestion(...)` instantiation.
   - Import `AutocompleteSuggestion`.

4. **`apps/search/services/popular_search.py`** — function `get_popular_suggestions`:
   - Change return type from `list[dict]` to `list[AutocompleteSuggestion]`.
   - Replace dict-literal construction with `AutocompleteSuggestion(...)` instantiation.
   - Import `AutocompleteSuggestion`.

5. **`apps/core/enums.py`** — `SearchSuggestionSource` StrEnum: no change (values already correct: `USER_HISTORY="user_history"`, `POPULAR_SEARCH="popular_search"`, `CATEGORY="category"`, `CITY="city"`).

6. **`templates/components/header_catalog.html`** — no change (consumes `type` and `source` as before; both preserved by the DTO).

7. **`apps/search/tests/test_autocomplete.py`** — no change required (all 12+ assertions on `type`/`source` continue to pass since both keys are preserved via `model_dump(mode="json")`).

**Architectural constraints:**
- The DTO lives at the **web boundary**. The three producers (`entity_suggestions.py`, `popular_search.py`, `search_history.py`'s `get_user_search_history`) must return typed objects, not raw dicts.
- `model_dump(mode="json")` serializes StrEnum values to their string values (e.g. `"user_history"`) — JSON output identical to current.
- The `type` key is preserved as a deprecated alias for `source` — no consumer breakage.

**Tests / verification:**
- Existing `test_autocomplete.py` tests must continue to pass (all `type`/`source` assertions hold).
- Add one new test: `test_suggestions_serialize_type_and_source` — assert `s["type"] == s["source"]` for all suggestion types after `model_dump(mode="json")`.
- `uv run ruff check` + `uv run basedpyright` on all three source files + the new DTO file.
- Smoke: `autocomplete` view returns `{"suggestions": [...], "query": ...}` with same shape (all keys present).

```powershell
$dc run --rm -e PYTEST_OPTS="-k 'test_autocomplete'" test
uv run ruff check src/backend/apps/search/views/autocomplete.py src/backend/apps/search/services/entity_suggestions.py src/backend/apps/search/services/popular_search.py
```

**Acceptance criteria:**
- `AutocompleteSuggestion` Pydantic v2 model exists with `text`, `source`, `type`, `slug`, `category_path`, `hit_count` fields.
- `autocomplete()` returns `AutocompleteSuggestion` objects serialized via `model_dump(mode="json")`.
- `get_entity_suggestions` and `get_popular_suggestions` return `list[AutocompleteSuggestion]`.
- No `dict[str, Any]` in the autocomplete response path.
- `type` key still present in JSON output (preserved for frontend + tests).
- All 12+ existing test assertions on `type`/`source` pass unchanged.
- `ruff check` / `basedpyright` clean on all touched files.

<!-- TASK_END: qlt002_autocomplete_dto -->

---

<!-- TASK_START: qlt003_contact_migration -->

### Block 4: QLT-003a — Migrate `contact.py` to `record_event` + export from `core/services/__init__.py`

```yaml
id: qlt003_contact_migration
title: "QLT-003: Route contact.py AnalyticsEvent.create through record_event; add export to core/services/__init__.py"
source_reference: .ai/plans/24-code-quality-fixes-execution.md
source_section: "Block 4: QLT-003a"
priority: medium
depends_on: []              # record_event already exists (Sep 8)
classification: advisory
risk: low                   # contact.py already follows the centralized canonical pattern
agents: [Implementor]
```

**Description:**  
`contact.py` already contains the canonical centralized pattern (`record_contact_initiated` / `record_contact_response` with lazy `%s` logging). However, these functions still call `AnalyticsEvent.objects.create(...)` inline instead of routing through the now-existing `record_event` helper. This block consolidates them onto the single canonical recorder and resolves the export inconsistency: `core/services/__init__.py` exports `record_contact_initiated`/`record_contact_response` but does NOT export `record_event`.

**Implementation scope:**

1. **`apps/core/services/contact.py`** — functions `record_contact_initiated` and `record_contact_response`:
   - Replace `AnalyticsEvent.objects.create(event_type=AnalyticsEventType.CONTACT_INITIATED, user_id=user_id)` with `record_event(AnalyticsEventType.CONTACT_INITIATED, user_id=user_id)`.
   - Replace `AnalyticsEvent.objects.create(event_type=AnalyticsEventType.CONTACT_RESPONSE, user_id=user.id)` with `record_event(AnalyticsEventType.CONTACT_RESPONSE, user_id=user.id)`.
   - Keep the lazy `%s` logging (`logger.info("Contact initiated event recorded for buyer %s", user_id)` etc.) — already correct.
   - Replace `from apps.analytics.models import AnalyticsEvent` import with `from apps.core.services.analytics import record_event` (remove the now-unused `AnalyticsEvent` import).

2. **`apps/core/services/__init__.py`** — add `record_event` to the exports (matching the `contact.py` convention):
   - Add `from .analytics import record_event` to the import block.
   - Add `"record_event"` to `__all__`.

**Architectural constraints:**
- `record_event` is transaction-transparent (no own `atomic()`). `record_contact_initiated` and `record_contact_response` are NOT called inside an `atomic()` block — they are post-save event recorders. So no transaction boundary change.
- The `record_event` call returns `AnalyticsEvent | None` but `contact.py` functions return `None`. The return value is ignored (the existing pattern in `listings.py` and `search.py` also ignores it).
- Same event types, same fields, same timestamp defaults — no behavioral change.

**Tests / verification:**
- Existing `test_autocomplete.py` / contact-related tests should continue to pass.
- Add a test assertion in `test_analytics_service.py` or contact tests: `test_contact_initiated_routes_through_record_event` — assert `AnalyticsEvent` row is created with `CONTACT_INITIATED` event type when `record_contact_initiated` is called. (Or verify via mock that `record_event` is called.)
- `uv run ruff check` + `uv run basedpyright` on both files.

```powershell
$dc run --rm -e PYTEST_OPTS="-k 'test_contact'" test
uv run ruff check src/backend/apps/core/services/contact.py src/backend/apps/core/services/__init__.py
```

**Acceptance criteria:**
- `contact.py` calls `record_event` for both `CONTACT_INITIATED` and `CONTACT_RESPONSE` events.
- `from apps.analytics.models import AnalyticsEvent` import removed from `contact.py` (if no other usage).
- `record_event` exported from `core/services/__init__.py` (`__all__` + import).
- Lazy `%s` logging preserved.
- No behavioral change (same event types, same fields).
- `ruff check` / `basedpyright` clean.

<!-- TASK_END: qlt003_contact_migration -->

---

<!-- TASK_START: qlt003_login_migration -->

### Block 5: QLT-003b — Migrate `login.py` REGISTRATION_CREATED to `record_event` (fixes eager f-string)

```yaml
id: qlt003_login_migration
title: "QLT-003: Migrate login.py REGISTRATION_CREATED inline create to record_event (also lazy-f logs)"
source_reference: .ai/plans/24-code-quality-fixes-execution.md
source_section: "Block 5: QLT-003b"
priority: medium
depends_on: []              # independent — disjoint file
classification: advisory
risk: low                   # single event type, post-atomic
agents: [Implementor]
```

**Description:**  
`login.py`'s `handle_login_orm` function contains an inline `AnalyticsEvent.objects.create(event_type=AnalyticsEventType.REGISTRATION_CREATED, user_id=user.id)` inside the `_handle` sync_to_async closure, followed by an eager f-string log: `logger.info(f"Registration event recorded for user {user.id}")`. This is one of 38 eager f-strings across production code (not "the only one" as the original findings claimed). Moving the create into `record_event` is the side effect that fixes this specific f-string → lazy `%s` conversion as part of the migration.

The `AnalyticsEvent.objects.create` at this site is **post-atomic** — the `transaction.atomic()` at `login.py` (inside `_handle`) wraps only the token claim (`_claim_login_token`), not the analytics event. So `record_event`'s transaction transparency is preserved (no nested atomic concern).

**Implementation scope:**

1. **`telegram_bot/handlers/login.py`** — function `handle_login_orm` (inside `_handle` closure):
   - Replace `AnalyticsEvent.objects.create(event_type=AnalyticsEventType.REGISTRATION_CREATED, user_id=user.id)` with `record_event(AnalyticsEventType.REGISTRATION_CREATED, user_id=user.id)`.
   - Replace `logger.info(f"Registration event recorded for user {user.id}")` with `logger.info("Registration event recorded for user %s", user.id)` (lazy `%s`).
   - Replace `from apps.analytics.models import AnalyticsEvent` with `from apps.core.services.analytics import record_event` (remove unused `AnalyticsEvent` import). Keep `AnalyticsEventType` import.

**Architectural constraints:**
- The create is outside any `transaction.atomic()` — safe to migrate (transaction-transparent `record_event` has no effect on the surrounding token-claim atomic).
- `record_event` returns `AnalyticsEvent | None` but the return value is discarded (the existing code discards the create result).
- Log-text change: `f"Registration event recorded for user {user.id}"` → `"Registration event recorded for user %s"`. Verify no alerting/log-parsing rule keys on the old f-string text before landing (the re-audit notes this as a minor log-format change).

**Tests / verification:**
- Existing login tests should continue to pass (event still created).
- Add test: `test_registration_event_uses_record_event` — assert that calling the login handler with a new user creates an `AnalyticsEvent` with `REGISTRATION_CREATED` (or mock `record_event` and assert it's called).
- `uv run ruff check` + `uv run basedpyright` on `login.py`.

```powershell
$dc run --rm -e PYTEST_OPTS="-k 'test_registration or test_login'" test
uv run ruff check src/telegram_bot/handlers/login.py
```

**Acceptance criteria:**
- `login.py` calls `record_event(AnalyticsEventType.REGISTRATION_CREATED, user_id=user.id)` instead of `AnalyticsEvent.objects.create(...)`.
- The eager f-string log is converted to lazy `%s` interpolation.
- `AnalyticsEvent` import removed (only `AnalyticsEventType` + `record_event` retained).
- No behavioral change (same event type, same `user_id` field).
- `ruff check` / `basedpyright` clean.

<!-- TASK_END: qlt003_login_migration -->

---

<!-- TASK_START: qlt003_auto_moderation_migration -->

### Block 6: QLT-003c — Migrate `auto_moderation.py` 3 inline creates to `record_event` (inside atomics)

```yaml
id: qlt003_auto_moderation_migration
title: "QLT-003: Migrate 3 inline AnalyticsEvent.create sites in auto_moderation.py (_fail_moderation + _pass_moderation) to record_event"
source_reference: .ai/plans/24-code-quality-fixes-execution.md
source_section: "Block 6: QLT-003c"
priority: medium
depends_on: []              # independent — record_event already exists; auto_moderate internals
                              # are not modified by QLT-001
classification: advisory
risk: medium                 # 3 sites inside transaction.atomic() — verify no self-atomic
agents: [Implementor]
```

**Description:**  
`auto_moderation.py` has three inline `AnalyticsEvent.objects.create` calls inside `transaction.atomic()` blocks:

| Function | Event type | Inside atomic? |
|---|---|---|
| `_fail_moderation` | `MODERATION_REJECTED` | Yes (`atomic` at `_fail_moderation`) |
| `_pass_moderation` | `AD_PUBLISHED` | Yes (`atomic` at `_pass_moderation`) |
| `_pass_moderation` | `MODERATION_APPROVED` | Yes (same atomic) |

`record_event` must NOT open its own `transaction.atomic()`. These sites are inside the caller's atomic scope, so a bare `record_event` call preserves the correct commit/rollback semantics. The critical risk: if `record_event` opened its own atomic (it does NOT — verified in `analytics.py`), it would create a nested savepoint that commits the event during a failed moderation rollback (commit-during-failure inconsistency). The existing `record_event` is correctly transaction-transparent.

**This is the highest-priority QLT-003 migration** because `auto_moderate` is the shared moderation seam called from both the bot handler and the web edit view. Centralizing these events at the `record_event` seam establishes the unified pattern.

**Implementation scope:**

1. **`apps/moderation/services/auto_moderation.py`** — functions `_fail_moderation` and `_pass_moderation`:
   - In `_fail_moderation`: replace `AnalyticsEvent.objects.create(event_type=AnalyticsEventType.MODERATION_REJECTED, user_id=ad.user_id, ad_id=ad.id)` with `record_event(AnalyticsEventType.MODERATION_REJECTED, user_id=ad.user_id, ad_id=ad.id)`.
   - In `_pass_moderation`: replace `AnalyticsEvent.objects.create(event_type=AnalyticsEventType.AD_PUBLISHED, user_id=ad.user_id, ad_id=ad.id)` with `record_event(AnalyticsEventType.AD_PUBLISHED, user_id=ad.user_id, ad_id=ad.id)`.
   - In `_pass_moderation`: replace `AnalyticsEvent.objects.create(event_type=AnalyticsEventType.MODERATION_APPROVED, user_id=ad.user_id, ad_id=ad.id)` with `record_event(AnalyticsEventType.MODERATION_APPROVED, user_id=ad.user_id, ad_id=ad.id)`.
   - Replace `from apps.analytics.models import AnalyticsEvent` with `from apps.core.services.analytics import record_event` (remove unused `AnalyticsEvent` import). Keep `AnalyticsEventType` import.

2. **File-sharing note with QLT-004 (Block 1):** QLT-004 also edits `auto_moderation.py` to add rationale to the `# pyright: ignore[reportGeneralTypeIssues]` lines in `_fail_moderation` and `_pass_moderation`. Both blocks edit the same file — with a single Implementor this is naturally sequential. If multiple Implementors, execute C3 and D1 sequentially.

**Architectural constraints:**
- `record_event` is called INSIDE the existing `transaction.atomic()` blocks (236, 253). It does NOT open its own atomic. The caller's transaction governs commit/rollback.
- Same event types (`MODERATION_REJECTED`, `AD_PUBLISHED`, `MODERATION_APPROVED`), same fields (`user_id`, `ad_id`), same timestamp defaults — no behavioral change.
- `TrustCalculator().calculate_and_save(ad.user)` at the end of `_pass_moderation` is outside the scope of this migration (it's not an analytics event).

**Tests / verification:**
- **Rollback-gate test (REQUIRED — also in Block 8/C5):** assert that when `_pass_moderation`'s `transaction.atomic()` rolls back (e.g., via `transaction.set_rollback(True)`), the `record_event` calls inside are NOT persisted. This verifies `record_event`'s transaction transparency.
- Existing moderation tests (`test_ad_lifecycle.py`, `test_transition_concurrency.py`) should pass — same event types/fields.
- `uv run ruff check` + `uv run basedpyright` on `auto_moderation.py`.

```powershell
$dc run --rm -e PYTEST_OPTS="-k 'test_moderation or test_auto_moderate or test_pass_moderation or test_fail_moderation'" test
uv run ruff check src/backend/apps/moderation/services/auto_moderation.py
```

**Acceptance criteria:**
- All 3 inline `AnalyticsEvent.objects.create` calls in `_fail_moderation`/`_pass_moderation` replaced with `record_event(...)` calls.
- `record_event` is called inside the existing `transaction.atomic()` blocks — no new atomic opened.
- Same event types, same `user_id`/`ad_id` fields — no behavioral change.
- `AnalyticsEvent` import removed (only `AnalyticsEventType` + `record_event` retained).
- Rollback-gate test passes (event inside atomic is NOT committed on rollback).
- `ruff check` / `basedpyright` clean.

<!-- TASK_END: qlt003_auto_moderation_migration -->

---

<!-- TASK_START: qlt003_trust_analytics_migration -->

### Block 7: QLT-003d — Migrate `trust_analytics.py` `record_trust_event` to delegate to `record_event`

```yaml
id: qlt003_trust_analytics_migration
title: "QLT-003: Delegate trust_analytics.py record_trust_event to canonical record_event"
source_reference: .ai/plans/24-code-quality-fixes-execution.md
source_section: "Block 7: QLT-003d"
priority: low
depends_on: []              # independent — disjoint file
classification: advisory
risk: low                   # parameterized call, no caller changes
agents: [Implementor, Validator]
```

**Description:**  
`trust_analytics.py`'s `record_trust_event(user_id, event, source=None)` performs an inline `AnalyticsEvent.objects.create(event_type=event, user_id=user_id, source=source)` with lazy `%s` logging. The function is semi-centralized (it's already a service function) but lives in `apps/analytics/services/` rather than the canonical `apps/core/services/analytics.py`. Per the QLT-003 resolution: `apps/core/services/analytics.py` is canonical (reuses the `contact.py` convention); `trust_analytics.py` should delegate to it.

**Implementation scope:**

1. **`apps/analytics/services/trust_analytics.py`** — function `record_trust_event`:
   - Replace `AnalyticsEvent.objects.create(event_type=event, user_id=user_id, source=source)` with `record_event(event_type=event, user_id=user_id, source=source)`.
   - Replace `from apps.analytics.models import AnalyticsEvent, DailyAdMetrics` with `from apps.analytics.models import DailyAdMetrics` (keep `DailyAdMetrics` for `get_seller_daily_metrics`; remove `AnalyticsEvent` if no other usage in the file) + `from apps.core.services.analytics import record_event`.
   - Keep the existing lazy `%s` logging: `logger.info("Trust event recorded: user=%s event=%s", user_id, event)`.

2. **Callers of `record_trust_event`** — no change required. The function signature `record_trust_event(user_id, event, source=None)` is preserved; only the internal implementation changes to delegate to `record_event`. All callers (seed generator, trust calculator, etc.) are unaffected.

**Architectural constraints:**
- `record_trust_event` is NOT called inside a `transaction.atomic()` block (verified — it's a post-moderation event recorder). `record_event`'s transaction transparency is preserved.
- The `source` parameter maps directly to `record_event`'s `source` kwarg.
- The `event` parameter maps to `record_event`'s `event_type` positional arg.
- Same event types, same fields — no behavioral change for callers.

**Tests / verification:**
- Existing `test_trust_calculator.py` and `trust_analytics` tests should pass.
- Verify `DailyAdMetrics` import is preserved (used by `get_seller_daily_metrics`).
- `uv run ruff check` + `uv run basedpyright` on `trust_analytics.py`.

```powershell
$dc run --rm -e PYTEST_OPTS="-k 'test_trust'" test
uv run ruff check src/backend/apps/analytics/services/trust_analytics.py
```

**Acceptance criteria:**
- `record_trust_event` calls `record_event(event_type=event, user_id=user_id, source=source)` instead of `AnalyticsEvent.objects.create(...)`.
- `AnalyticsEvent` import removed from `trust_analytics.py` (if no other usage); `DailyAdMetrics` import preserved.
- `record_event` imported from `apps.core.services.analytics`.
- No caller signature changes (backward compatible).
- Same event types, same fields — no behavioral change.
- `ruff check` / `basedpyright` clean.

<!-- TASK_END: qlt003_trust_analytics_migration -->

---

<!-- TASK_START: qlt003_rollback_gate_test -->

### Block 8: QLT-003f — Add rollback-gate test for `record_event` transaction transparency

```yaml
id: qlt003_rollback_gate_test
title: "QLT-003: Add rollback-gate test — record_event inside auto_moderation atomic must NOT persist on rollback"
source_reference: .ai/plans/24-code-quality-fixes-execution.md
source_section: "Block 8: QLT-003f"
priority: medium
depends_on: [qlt003_auto_moderation_migration]   # validates C3's transaction transparency
classification: advisory
risk: low                   # test-only addition
agents: [Validator]
```

**Description:**  
The existing `test_analytics_service.py` has 4 tests covering success and failure paths but **no rollback-gate test**. This is a critical verification gap: `record_event` is called inside `auto_moderation.py`'s `transaction.atomic()` blocks (lines 236, 253). The test must assert that when the surrounding transaction rolls back, the `AnalyticsEvent` row is NOT persisted — verifying the transaction-transparency guarantee (no nested atomic, no commit-during-failure).

**Implementation scope:**

1. **`apps/core/tests/test_analytics_service.py`** — add to `TestRecordEvent` class:
   - `test_record_event_inside_rollback_not_persisted`: Create a `record_event` call inside a `with transaction.atomic():` block, then force a rollback via `transaction.set_rollback(True)` (or raise an exception inside the atomic). Assert that `AnalyticsEvent.objects.count() == 0` after the block exits — the event was not committed.
   - `test_record_event_inside_commit_persisted`: Create a `record_event` call inside a `with transaction.atomic():` block with no rollback. Assert the event IS persisted (`AnalyticsEvent.objects.count() == 1`). This confirms the positive path within an atomic scope.

2. **No production code changes.**

**Architectural constraints:**
- The test uses `transaction.atomic()` + `transaction.set_rollback(True)` (or an inner exception) to simulate a moderation failure rollback.
- `@pytest.mark.django_db` is required (existing `pytestmark` already set to `[pytest.mark.django_db, pytest.mark.integration]`).
- The test must use the Django test DB transaction handling correctly — `transaction.set_rollback(True)` works within a `django_db` test (the outer test transaction is rolled back naturally, but the `set_rollback` forces the inner atomic to roll back its changes).

**Tests / verification:**
- `uv run pytest` or Docker Compose test with `-k 'test_record_event_inside_rollback_not_persisted or test_record_event_inside_commit_persisted'`.
- Verify: rollback test asserts 0 events after rollback; commit test asserts 1 event after successful atomic.
- `uv run ruff check` + `uv run basedpyright` on the test file.

```powershell
$dc run --rm -e PYTEST_OPTS="-k 'test_record_event_inside_rollback_not_persisted or test_record_event_inside_commit_persisted'" test
```

**Acceptance criteria:**
- `test_analytics_service.py` contains `test_record_event_inside_rollback_not_persisted` — asserts 0 `AnalyticsEvent` rows after `record_event` inside a rolled-back `transaction.atomic()`.
- `test_analytics_service.py` contains `test_record_event_inside_commit_persisted` — asserts 1 `AnalyticsEvent` row after `record_event` inside a committed `transaction.atomic()`.
- Both tests pass.
- No production code changes.
- `ruff check` / `basedpyright` clean on test file.

<!-- TASK_END: qlt003_rollback_gate_test -->

---

<!-- TASK_START: qlt001_stage1_inert_submission -->

### Block 9: QLT-001 Stage 1 — Introduce inert `submission.py` (no callers)

```yaml
id: qlt001_stage1_inert_submission
title: "QLT-001: Introduce inert apps/ads/services/submission.py with SubmitAdInput DTO + submit_ad()"
source_reference: .ai/plans/24-code-quality-fixes-execution.md
source_section: "Block 9: QLT-001 Stage 1"
priority: high
depends_on: []              # no predecessor — inert (no callers yet)
classification: mandatory   # HIGH severity finding
risk: large                 # new module, large code movement
agents: [Implementor, Researcher]
decision_gate: REQUIRED    # SubmitAdInput Pydantic vs dataclass; submit_ad sync vs async
```

**Description:**  
`update_ad_and_moderate` in `telegram_bot/handlers/ad_create.py` (1512 lines) embeds business logic, ORM writes, validation, and thumbnail I/O in the handler. It performs: currency coercion, price normalization, multi-language field assignment, filesystem thumbnail generation, `AdImageService.create_or_skip`, DRAFT→ON_MODERATION transition, and delegates to `auto_moderate`. The shared service layer (`apps/ads/services/`) has no submission orchestrator — only `copy_service.py` and `images.py` exist.

This block introduces an **inert** `submission.py` — a verbatim extraction of `_update_and_moderate`'s body, with NO callers wired yet. Zero runtime/test impact.

**Decision gate (must resolve before implementation):**
- **`SubmitAdInput` type:** Pydantic v2 model (per project rule #11: "All models and validation use Pydantic v2 at system boundaries") OR plain dataclass. The bot handler already uses Pydantic DTOs (`telegram_bot/schemas/message_payloads.py`). **Recommended:** Pydantic v2 — but the Implementor must confirm the existing patterns in `apps/ads/services/` (do other service functions accept Pydantic DTOs or individual params?).
- **`submit_ad` sync vs async:** The current `update_ad_and_moderate` is async (wraps sync `_update_and_moderate` in `sync_to_async`). The web edit view (`edit.py`) is a sync Django view. `auto_moderate` (the called service) is sync. **Recommended:** `submit_ad` should be **sync** (in the backend service layer), called directly from the web edit view, and called via `sync_to_async(submit_ad)(...)` from the bot handler — matching the `auto_moderate` pattern (sync service, called from both processes). The Implementor must verify this calling pattern against the bot handler's async context.

**Implementation scope:**

1. **New file:** `src/backend/apps/ads/services/submission.py` — module containing:
   - `SubmitAdInput` (Pydantic v2 model or dataclass — decision gate) with fields mirroring `update_ad_and_moderate`'s parameters: `ad_id`, `title_ru`, `desc_ru`, `category_id`, `city_id`, `price_amount`, `price_currency`, `photos`, `user_id`, `title_bs`, `desc_bs`, `title_en`, `desc_en`, `original_language`, `listing_purpose_id`, `feature_ids`, `listing_condition_id`.
   - `submit_ad(input: SubmitAdInput) -> tuple[bool, list[str]]` — a verbatim copy of `_update_and_moderate()`'s body (the `@sync_to_async` inner function), preserving:
     - Thumbnail generation **before** the `transaction.atomic()` block (filesystem I/O outside tx to avoid FS/DB desync on rollback).
     - `transaction.atomic()` wrapping `ad.save()` + `AdImageService.create_or_skip` + `ad.transition_to(AdStatus.ON_MODERATION)`.
     - `auto_moderate(ad)` **outside** the atomic block.
     - Currency coercion (`isinstance(price_currency, CurrencyCode)` + `ValueError` recovery → `None`).
     - Price normalization (`PriceNormalizer().normalize_to_eur` with `except Exception` swallow-and-null).
     - Multi-language field assignment.

2. **No changes** to any caller. `process_preview` in `ad_create.py` still calls `update_ad_and_moderate`. No imports added.

**Viable implementation paths:**
1. **`submit_ad` as sync function, `SubmitAdInput` as Pydantic v2** — matches `auto_moderate` (sync service). Bot wraps in `sync_to_async`. Web edit calls directly.
2. **`submit_ad` as async function** — would require the web edit view to use `sync_to_async` wrapper, introducing async-in-sync friction. Less clean.

**Rejected:** Inlining the extraction into `ad_create.py` (the handler) — violates §4(d) "thin handlers delegating to a shared service layer" and §4(i) "DRY across the two processes."

**Architectural constraints:**
- The `transaction.atomic()` boundary must be preserved exactly: thumbnails → atomic DB+images+transition → `auto_moderate` (outside atomic). See re-audit QLT-001 verification: "atomic at 1197 ends line 1221; auto_moderate at 1229 is outside the atomic."
- The currency coercion logic is copied verbatim (including the invalid→`None` behavior). The web edit's "keep-current" behavior is NOT addressed here — that's Block 12/A4's currency gate.
- `submit_ad` must import from `apps.ads.models`, `apps.currencies.enums`, `apps.currencies.services.price_normalizer`, `apps.media.services.thumbnails`, `apps.core.enums`, `apps.moderation.services.auto_moderation`, `django.db.transaction` — all already dependencies of the handler.

**Tests / verification:**
- Inert module — no callers, no test impact.
- `uv run ruff check src/backend/apps/ads/services/submission.py` — must parse (even if unused).
- `uv run basedpyright src/backend/apps/ads/services/submission.py` — type-check the new module.
- Verify no import is added to `ad_create.py` or any caller.

```powershell
uv run ruff check src/backend/apps/ads/services/submission.py
uv run basedpyright src/backend/apps/ads/services/submission.py
```

**Acceptance criteria:**
- `apps/ads/services/submission.py` exists with `submit_ad` function + `SubmitAdInput` type.
- `submit_ad`'s body is a verbatim copy of `_update_and_moderate`'s logic (currency coercion, price normalization, multi-lang, thumbnails-before-atomic, atomic DB+images+transition, auto_moderate after atomic).
- NO caller imports or calls `submit_ad` — completely inert.
- `ruff check` / `basedpyright` clean on the new module.
- No migration required.

<!-- TASK_END: qlt001_stage1_inert_submission -->

---

<!-- TASK_START: qlt001_stage2_bot_rewire -->

### Block 10: QLT-001 Stage 2 — Rewire bot handler to call `submit_ad`; delete `update_ad_and_moderate`

```yaml
id: qlt001_stage2_bot_rewire
title: "QLT-001: Rewire process_preview to call submit_ad; delete update_ad_and_moderate; update test imports"
source_reference: .ai/plans/24-code-quality-fixes-execution.md
source_section: "Block 10: QLT-001 Stage 2"
priority: high
depends_on: [qlt001_stage1_inert_submission]   # MUST ship after inert submission.py
classification: mandatory
risk: medium                                     # bot rewire; test import updates
agents: [Implementor, Validator]
```

**Description:**  
With the inert `submission.py` in place, rewire the bot handler to use the shared service. Replace the `await update_ad_and_moderate(...)` call in `process_preview` with a `submit_ad` call, delete the now-dead `update_ad_and_moderate` function (and its inner `_update_and_moderate`), and update the 2 import sites in `test_save_photo_integration.py` that reference `update_ad_and_moderate`.

**Implementation scope:**

1. **`telegram_bot/handlers/ad_create.py`** — function `process_preview`:
   - Replace `await update_ad_and_moderate(ad_id=..., title_ru=..., ...)` call with `await sync_to_async(submit_ad)(SubmitAdInput(ad_id=..., ...))` (or the equivalent calling pattern — decision gate: `sync_to_async(submit_ad)(...)` vs. `submit_ad` being async).
   - The `SubmitAdInput` is constructed from the same parameters currently passed to `update_ad_and_moderate`.
   - Delete the `async def update_ad_and_moderate(...)` function (lines ~1038–1237) — no longer referenced.
   - Remove now-unused imports (`AdImageService` is now in `submission.py`, `PriceNormalizer`, `CurrencyCode`, `ThumbnailService`, etc. — only if not used elsewhere in `ad_create.py`).
   - Add import: `from apps.ads.services.submission import SubmitAdInput, submit_ad`.

2. **`telegram_bot/tests/test_save_photo_integration.py`** — 2 import blocks:
   - Replace `update_ad_and_moderate` in the `from telegram_bot.handlers.ad_create import (...)` import with `submit_ad` + `SubmitAdInput` (or import from the new service module).
   - Update the 2 call sites (lines ~97, ~148) that call `await update_ad_and_moderate(...)` to use `submit_ad`.

3. **`telegram_bot/tests/test_ad_create.py`** — verify no import of `update_ad_and_moderate` (re-audit confirmed it only imports `process_preview` and `create_draft_ad` via `from telegram_bot.handlers.ad_create import create_draft_ad, process_preview`). If `submit_ad` needs to be called in any test, add the import. The docstring reference (if any) should be updated.

**Architectural constraints:**
- `process_preview` must still `await` the submission call — `submit_ad` is sync, so it's wrapped in `sync_to_async` (matching the current `update_ad_and_moderate` pattern which wraps sync `_update_and_moderate` in `sync_to_async`).
- The return type is `tuple[bool, list[str]]` — unchanged.
- `auto_moderate` is still called inside `submit_ad` (via the extracted body) — no change to moderation behavior.
- The 2 test import sites in `test_save_photo_integration.py` are the ONLY imports of `update_ad_and_moderate` (re-audit confirmed: `test_ad_create.py` only imports `process_preview` and `create_draft_ad`, not `update_ad_and_moderate`).

**Tests / verification:**
- Existing tests that call `process_preview` (which now calls `submit_ad`) must pass — behavioral equivalence.
- `test_save_photo_integration.py` tests (thumbnail integration) must pass after import update.
- `test_ad_create.py` tests must pass (no import change needed — doesn't import `update_ad_and_moderate`).
- Green gate: all bot-side tests pass.

```powershell
$dc run --rm -e PYTEST_OPTS="-k 'test_save_photo or test_ad_create or test_preview'" test
uv run ruff check src/telegram_bot/handlers/ad_create.py src/telegram_bot/tests/test_save_photo_integration.py
```

**Acceptance criteria:**
- `process_preview` calls `submit_ad` (via `sync_to_async`) instead of `update_ad_and_moderate`.
- `update_ad_and_moderate` and `_update_and_moderate` functions deleted from `ad_create.py`.
- `test_save_photo_integration.py` imports updated (2 sites) — no reference to deleted function.
- `test_ad_create.py` unaffected (doesn't import `update_ad_and_moderate`).
- All bot-side tests pass (behavioral equivalence verified).
- `ruff check` / `basedpyright` clean.

<!-- TASK_END: qlt001_stage2_bot_rewire -->

---

<!-- TASK_START: qlt001_stage1.5_test_edit -->

### Block 11: QLT-001 Stage 1.5 — Create `apps/ads/tests/test_edit.py` (BLOCKING precondition)

```yaml
id: qlt001_stage1.5_test_edit
title: "QLT-001: Create apps/ads/tests/test_edit.py integration tests for ad_edit reactivation path (BLOCKING)"
source_reference: .ai/plans/24-code-quality-fixes-execution.md
source_section: "Block 11: QLT-001 Stage 1.5"
priority: high
depends_on: []              # independent — tests current edit.py behavior
                              # parallel-safe with A1 (Stage 1) and A2 (Stage 2)
classification: mandatory   # BLOCKING: Stage 3 cannot proceed without this
risk: medium                 # new test file; must assert correct existing behavior
agents: [Implementor, Validator]
```

**Description:**  
QLT-001 Stage 3 migrates the `ad_edit` reactivation path (`is_reactivation` branch) through `submit_ad`. Before that migration, an integration test must exist that asserts the **current** (pre-migration) behavior of the reactivation path — so the migration can be verified as behaviorally equivalent. `apps/ads/tests/` currently contains no `test_edit.py` (confirmed by directory listing: `test_adimage_storage_keys.py`, `test_ad_constraints.py`, `test_ad_lifecycle.py`, `test_ad_localization.py`, `test_auth_nav.py`, `test_breadcrumbs_render.py`, `test_catalog_filters.py`, `test_dashboard_stats.py`, `test_detail_context.py`, `test_detail_render.py`, `test_edit_views_locking.py`, `test_favorites.py`, `test_gallery_markup.py`, `test_i18n_*.py`, `test_listings_context.py`, `test_listings_sort.py`, `test_media_security.py`, `test_price_format.py`, `test_script_gating.py`, `test_search_triggers.py`, `test_transition_concurrency.py` — no `test_edit.py`).

Note: `test_edit_views_locking.py` exists but tests DB-003 row-locking, NOT the reactivation business logic.

**Implementation scope:**

1. **New file:** `src/backend/apps/ads/tests/test_edit.py` — integration tests for the `ad_edit` reactivation path, using existing `conftest.py` fixtures (`seller`, `user`, `category`, `city`, `create_test_ad`).

2. **Test cases to add** (asserting current pre-migration behavior of the `is_reactivation` branch):

| Test | Description | Asserts |
|---|---|---|
| `test_edit_reactivation_archived_to_on_moderation` | ARCHIVED ad edited with `is_reactivation` → status transitions to ON_MODERATION, auto_moderate invoked | `ad.status == AdStatus.ON_MODERATION`; `auto_moderate` called |
| `test_edit_reactivation_passes_auto_moderate` | Reactivation where content passes moderation → redirects to dashboard, status PUBLISHED | `response.redirect_chain` includes `ads:dashboard`; `ad.status == AdStatus.PUBLISHED` |
| `test_edit_reactivation_fails_auto_moderate` | Reactivation where content fails moderation → re-renders edit page with error | Response renders `ads/edit.html`; `ad.status == AdStatus.ON_MODERATION_FAILED` |
| `test_edit_reactivation_currency_keep_current` | Reactivation with invalid currency → keeps existing ad currency (NOT coerced to None) | `ad.price_currency` unchanged from pre-edit value |
| `test_edit_reactivation_price_normalized_recomputed` | Reactivation with valid price → `price_normalized_eur` recomputed via PriceNormalizer | `ad.price_normalized_eur` matches `PriceNormalizer().normalize_to_eur(price_amount, currency)` |
| `test_edit_reactivation_text_updated` | Reactivation updates title/description from POST data | `ad.title == new_title`; `ad.description == new_description` |

3. **The currency behavior** is explicitly asserted in `test_edit_reactivation_currency_keep_current` — this pins the "keep-current" behavior so that when `submit_ad` is wired in (Block 12), the currency-coercion policy reconciliation must preserve it (either via parameterized `on_invalid="keep"` or by passing the current currency as a fallback).

**Architectural constraints:**
- Tests must run against the **current** code (before Stage 3 migration) — they assert the existing behavior of `ad_edit`'s reactivation branch.
- Use `pytest.mark.django_db` (or the `integration` marker per the project's test markers).
- Mock `auto_moderate` where asserting its invocation (like `test_save_photo_integration.py` does at its patch site).
- Tests must NOT depend on `submit_ad` existing yet (they test the view, not the service).

**Tests / verification:**
- `$dc run --rm -e PYTEST_OPTS="-k 'test_edit_reactivation'" test` — all tests pass against current code.
- `uv run ruff check` + `uv run basedpyright` on the new test file.
- This test file is the **behavioral baseline** — all assertions must hold BEFORE Stage 3 migrates the reactivation path through `submit_ad`.

```powershell
$dc run --rm -e PYTEST_OPTS="-k 'test_edit_reactivation'" test
```

**Acceptance criteria:**
- `apps/ads/tests/test_edit.py` exists with ≥6 integration tests covering the reactivation path.
- All tests pass against the current `edit.py` (pre-migration).
- `test_edit_reactivation_currency_keep_current` asserts the "keep-current" currency behavior (pins the divergence with the bot's "coerce to None").
- Tests use existing `conftest.py` fixtures (`seller`, `user`, `category`, `city`, `create_test_ad`).
- `ruff check` / `basedpyright` clean on the new file.

<!-- TASK_END: qlt001_stage1.5_test_edit -->

---

<!-- TASK_START: qlt001_stage3_edit_migration -->

### Block 12: QLT-001 Stage 3 — Migrate `edit.py` reactivation branch through `submit_ad` (currency gate)

```yaml
id: qlt001_stage3_edit_migration
title: "QLT-001: Route ad_edit reactivation branch through submit_ad; reconcile currency coercion policy"
source_reference: .ai/plans/24-code-quality-fixes-execution.md
source_section: "Block 12: QLT-001 Stage 3"
priority: high
depends_on:
  - qlt001_stage1_inert_submission      # submit_ad must exist
  - qlt001_stage1.5_test_edit           # test_edit.py must exist and pass (BLOCKING)
classification: mandatory
risk: medium                             # behavioral risk on active user flow
agents: [Implementor, Validator]
decision_gate: REQUIRED                 # currency coercion reconciliation
```

**Description:**  
Migrate the `is_reactivation` branch of `ad_edit` in `apps/ads/views/edit.py` to route through the shared `submit_ad` service (from Block 9). The reactivation path currently does: field update → `ad.save()` → `ad.transition_to(AdStatus.ON_MODERATION)` → `auto_moderate(ad)`. After migration, it delegates to `submit_ad` with `photos=None` and `original_language=None`.

**Decision gate — currency coercion policy (MUST resolve before implementation):**

The bot's `submit_ad` coerces invalid currency → `None` (via `CurrencyCode(str(price_currency))` with `ValueError` recovery). The web edit's `_apply_price_change` keeps the existing currency on `ValueError`. If `submit_ad` becomes the single coercer, the edit flow's "keep-current" behavior silently changes to "set None" — a behavioral change on an active user flow.

**Viable approaches:**
1. **Parameterize the coercer** (`on_invalid="none" | "keep"`): `submit_ad` accepts a policy parameter. The bot passes `on_invalid="none"` (default); the edit reactivation passes `on_invalid="keep"` with the current `ad.price_currency` as fallback. This preserves both behaviors.
2. **Document as intentional divergence:** Keep `submit_ad`'s "coerce to None" as-is; the edit path pre-validates currency via `_apply_price_change` before calling `submit_ad`. Document the divergence in `submit_ad`'s docstring.

**Recommended:** Path 1 (parameterize) — it preserves both behaviors explicitly and avoids silent behavior change. The `test_edit_reactivation_currency_keep_current` test (Block 11) pins this requirement.

> **Not choosing the final approach here** — this is a genuine behavior-change decision. The Implementor must select and document the approach. If Path 2 is chosen, the behavioral divergence must be explicitly documented in the `submit_ad` docstring and the `test_edit_reactivation_currency_keep_current` test must assert the "keep" behavior is preserved via pre-validation.

**Implementation scope:**

1. **`apps/ads/views/edit.py`** — function `ad_edit` (the `is_reactivation` branch):
   - Replace the reactivation path's inline logic (field update, save, `transition_to(ON_MODERATION)`, `auto_moderate`) with a call to `submit_ad(SubmitAdInput(...))`.
   - Pass `photos=None`, `original_language=None` (no photo upload or translation in edit context).
   - Pass existing ad field values through `SubmitAdInput`.
   - The currency parameter must reconcile the "keep-current" behavior — either via the parameterized coercer (Path 1) or via pre-validation (Path 2).
   - Leave the text-edit-hide branch (`has_text_change` within `PUBLISHED` status) and price-only-edit branch **as-is** — they must NOT call `auto_moderate` (per findings). Only the reactivation branch migrates.

2. **`submit_ad` / `submission.py`** — if Path 1 (parameterized coercer) is chosen:
   - Add `on_invalid_currency: Literal["none", "keep"] = "none"` parameter to `SubmitAdInput`.
   - Modify the currency coercion logic to honor the policy (when `on_invalid="keep"`, coerce to the existing currency if available).

3. **`ad_reactivate` view** (separate function at `edit.py`) — secondary target: also calls `auto_moderate` + `transition_to(ON_MODERATION)`. The findings focus on the `is_reactivation` branch of `ad_edit`. This view can be migrated in a follow-up (it's a simpler case — no text/price editing, just status + moderation). **Not in scope for this block** — deferred.

**Architectural constraints:**
- The reactivation branch's existing `transaction.atomic()` + `select_for_update()` (DB-003 locking at line 124) must be preserved or adapted. The re-audit notes `edit.py:124` is a `transaction.atomic()` with `select_for_update()` — `submit_ad` uses its own `transaction.atomic()` internally. If the reactivation path enters `submit_ad`'s atomic while already in one, Django handles nested atomics via savepoints — but the `select_for_update()` lock must be acquired under the right transaction. The Implementor must verify the locking semantics are preserved.
- `photos=None` and `original_language=None` in the `SubmitAdInput` — the thumbnailing loop in `submit_ad` must handle `None`/empty photos gracefully (it iterates `for photo in photos:` — `None` would crash; must guard with `photos or []`).
- The `test_edit.py` tests (Block 11) must still pass after migration — behavioral equivalence.

**Tests / verification:**
- `$dc run --rm -e PYTEST_OPTS="-k 'test_edit_reactivation'" test` — all `test_edit.py` tests pass after migration (behavioral equivalence).
- `test_edit_views_locking.py` tests still pass (DB-003 locking preserved).
- `uv run ruff check` + `uv run basedpyright` on `edit.py` and `submission.py`.

```powershell
$dc run --rm -e PYTEST_OPTS="-k 'test_edit_reactivation'" test
```

**Acceptance criteria:**
- The `is_reactivation` branch of `ad_edit` routes through `submit_ad(SubmitAdInput(...))`.
- `photos=None` and `original_language=None` passed to `SubmitAdInput`.
- Currency coercion policy reconciled (Path 1 or Path 2 chosen and documented).
- `test_edit_reactivation_currency_keep_current` still passes (no silent "keep"→"None" behavior change).
- Text-edit-hide and price-only-edit branches unchanged (still inline, no `auto_moderate`).
- DB-003 `select_for_update()` locking preserved.
- All `test_edit.py` tests pass (behavioral equivalence).
- `ruff check` / `basedpyright` clean.

<!-- TASK_END: qlt001_stage3_edit_migration -->

---

## 7. Cross-Cutting Risks & Gates

### 7.1 QLT-001 Currency-Coercion Decision Gate (Block 12)

**Risk:** If `submit_ad` (bot's "invalid currency → None" coercion) is wired into `edit.py`'s reactivation path without reconciliation, the edit flow silently changes from "keep existing currency" to "set currency to None." This is a behavior change on an active seller user flow (ARCHIVED → reactivation).

**Mitigation:** Block 12 is **blocked** on resolving the currency policy (Path 1: parameterize, or Path 2: document + pre-validate). The `test_edit_reactivation_currency_keep_current` test (Block 11) pins the "keep" behavior and serves as the verification gate.

### 7.2 QLT-001/QLT-003 Ordering (Relaxed)

As assessed in §3, the original QLT-001 → QLT-003 ordering recommendation is **no longer a hard constraint**. `record_event` exists (Sep 8). The `auto_moderation.py` inline creates (QLT-003 Block 6) are inside `auto_moderate`'s own functions, not in the orchestrator code QLT-001 extracts. QLT-001 and QLT-003 can proceed in parallel.

**Caveat:** If QLT-003 Block 6 (auto_moderation.py migration) and QLT-004 Block 1 (pyright ignore rationale) run with separate Implementors, they both edit `auto_moderation.py` — execute sequentially. With a single Implementor, this is naturally sequential.

### 7.3 QLT-002 `type` Key Deprecation (Deferred)

The `type` key in autocomplete suggestions is consumed by `header_catalog.html` (lines 326, 340) and asserted in 12+ test locations. QLT-002 (Block 3) preserves the key via the Pydantic DTO — no consumer breakage. The actual *removal* of `type` (deprecating it to `source`-only) is deferred to a follow-up phase with coordinated frontend + test updates. **Not safe to do now** without updating `header_catalog.html` and all 12+ test assertions.

### 7.4 QLT-004 Scope Precision

QLT-004 targets **only** `# pyright: ignore[reportGeneralTypeIssues]`. The 7 `# pyright: ignore[reportArgumentType]` sites in `users/models.py` (×5) and `categories/models.py` (×1), plus the 1 `# pyright: ignore[reportAbstractUsage]` in `telegram_bot/tests/conftest.py`, are a **related but out-of-scope** hygiene concern (different rule codes). They are noted here for future tracking but NOT included in the 39-site QLT-004 count.

### 7.5 QLT-005 `builder.py` `Any` Retained for Internal Helpers

QLT-005 retypes `load_catalog`'s `apps: Any` → `Apps | None`. However, `builder.py`'s internal helpers (`_load_lookups`, `_load_categories`, `_load_bindings`, `_load_category_paths`) also use `apps: Any` and `dict[str, Any]` / `list[dict[str, Any]]` parameters. The `dict[str, Any]` usages are genuine (JSON/YAML data shapes) and should NOT be retyped. The `apps: Any` in those helpers should also be retyped to `Apps | None` for consistency — this is within the scope of Block 2 (E1) but the Implementor should verify.

### 7.6 Single Implementor → effective sequential execution

With one Implementor, all parallel-safe blocks execute one-at-a-time. Only the documented dependency gates constrain ordering:
- A1 → A2 → A4 (QLT-001 stages)
- A4 → {A1, A3, Currency Gate} (QLT-001 Stage 3)
- C5 depends on C3 (rollback test validates the auto_moderation migration)
- C3 and D1 share `auto_moderation.py` (sequential within single Implementor)

Every other pair is interchangeable.

---

## 8. Verification Matrix

| Block | Finding | Test file(s) | Verification command | Marker |
|---|---|---|---|---|
| 1 (D1) | QLT-004 | (none — comment only) | `uv run ruff check src/ ; uv run basedpyright src/backend src/telegram_bot` | N/A |
| 2 (E1) | QLT-005 | (none — type-only) | `uv run basedpyright src/backend/apps/lookups/services/cache_service.py src/backend/apps/categories/catalog/builder.py src/backend/apps/search/services/search_history.py` | N/A |
| 3 (B1) | QLT-002 | `apps/search/tests/test_autocomplete.py` | `$dc run --rm -e PYTEST_OPTS="-k 'test_autocomplete'" test` | `integration django_db` |
| 4 (C1) | QLT-003a | `apps/core/tests/` (contact tests) | `$dc run --rm -e PYTEST_OPTS="-k 'test_contact'" test` | `integration django_db` |
| 5 (C2) | QLT-003b | `telegram_bot/tests/test_login_handlers.py` | `$dc run --rm -e PYTEST_OPTS="-k 'test_login'" test` | `integration django_db asyncio` |
| 6 (C3) | QLT-003c | `apps/moderation/tests/test_auto_moderation.py` / `test_ad_lifecycle.py` | `$dc run --rm -e PYTEST_OPTS="-k 'test_moderation or test_auto_moderate'" test` | `integration django_db` |
| 7 (C4) | QLT-003d | `apps/analytics/tests/` (trust tests) | `$dc run --rm -e PYTEST_OPTS="-k 'test_trust'" test` | `integration django_db` |
| 8 (C5) | QLT-003f | `apps/core/tests/test_analytics_service.py` | `$dc run --rm -e PYTEST_OPTS="-k 'test_record_event_inside_rollback_not_persisted or test_record_event_inside_commit_persisted'" test` | `integration django_db` |
| 9 (A1) | QLT-001 | (none — inert) | `uv run ruff check src/backend/apps/ads/services/submission.py ; uv run basedpyright src/backend/apps/ads/services/submission.py` | N/A |
| 10 (A2) | QLT-001 | `telegram_bot/tests/test_save_photo_integration.py`, `telegram_bot/tests/test_ad_create.py` | `$dc run --rm -e PYTEST_OPTS="-k 'test_save_photo or test_ad_create'" test` | `integration django_db asyncio` |
| 11 (A3) | QLT-001 | `apps/ads/tests/test_edit.py` (new) | `$dc run --rm -e PYTEST_OPTS="-k 'test_edit_reactivation'" test` | `integration django_db` |
| 12 (A4) | QLT-001 | `apps/ads/tests/test_edit.py` (existing + post-migration) | `$dc run --rm -e PYTEST_OPTS="-k 'test_edit_reactivation'" test` | `integration django_db` |

**Fast-gate coverage:** Blocks 1, 2, 9, 12 require only `ruff`/`basedpyright` (no test DB). All other blocks require Docker Compose test DB (PostgreSQL 18 on port 5433).

**Full suite (regression safety after all blocks):**
```powershell
$dc run --rm test
```

---

## 9. Risk Assessment

| Block | Finding | Risk | Mitigation |
|---|---|---|---|
| D1 (Block 1) | QLT-004 | **Zero** — comment-only | `ruff check` + `basedpyright` confirm no semantic change |
| E1 (Block 2) | QLT-005 | **Trivial** — annotations only | `basedpyright` confirms type correctness; deferred imports already in scope |
| B1 (Block 3) | QLT-002 | **Low** — DTO preserves all keys | 12+ test assertions pin `type`/`source`; `model_dump(mode="json")` preserves output shape |
| C1 (Block 4) | QLT-003a | **Low** — already-canonical pattern | Same event types/fields; `record_event` is transaction-transparent |
| C2 (Block 5) | QLT-003b | **Low** — single event, post-atomic | Eager f-string fix is trivial; same event type |
| C3 (Block 6) | QLT-003c | **Medium** — inside `transaction.atomic()` | Block 8 (C5) rollback-gate test verifies no commit-during-failure |
| C4 (Block 7) | QLT-003d | **Low** — delegates to `record_event` | No caller signature change; same event type/fields |
| C5 (Block 8) | QLT-003f | **Low** — test-only | New test; no production change |
| A1 (Block 9) | QLT-001 | **Large** — new module, code movement | Inert (no callers); verbatim copy preserves behavior |
| A2 (Block 10) | QLT-001 | **Medium** — bot rewire | Green gate: all bot tests pass; `update_ad_and_moderate` deletion verified no remaining imports |
| A3 (Block 11) | QLT-001 | **Medium** — new test file | Tests assert current behavior; pass before any migration |
| A4 (Block 12) | QLT-001 | **Medium** — active user flow (reactivation) | Currency gate decision + `test_edit_reactivation_currency_keep_current` test pins behavior; DB-003 locking preserved |

### Agent intervention summary

- **Block 1 (D1), Block 2 (E1):** Implementor only. Comment-only / type-only. No review risk.
- **Block 3 (B1):** Implementor. Validator verifies 12+ test assertions still pass.
- **Blocks 4-7 (C1-C4):** Implementor. Validator verifies event types/fields unchanged via existing moderation/login/contact tests.
- **Block 8 (C5):** Validator (test creation). Depends on C3.
- **Block 9 (A1):** Implementor + Researcher (decision gate: Pydantic vs dataclass, sync vs async).
- **Block 10 (A2):** Implementor. Validator green-gate on bot tests.
- **Block 11 (A3):** Implementor + Validator (test must pass against current code).
- **Block 12 (A4):** Implementor + Validator. **Decision gate** (currency policy) must resolve before implementation.

**No Auditor agent required** — findings already validated (Sep 5) and re-audited (Sep 11).

---

## 10. Git Strategy

| Commit | Contents | Type |
|--------|----------|------|
| 1 | Block 1 (QLT-004 rationale) + Block 2 (QLT-005 typing) | `style(qlt-004,qlt-005): add pyright ignore rationale + concrete return types` |
| 2 | Block 3 (QLT-002 Pydantic DTO) | `refactor(qlt-002): introduce AutocompleteSuggestion DTO at autocomplete boundary` |
| 3 | Blocks 4-7 (QLT-003 remaining migrations + Block 8 test) | `refactor(qlt-003): centralize remaining AnalyticsEvent.create sites via record_event + rollback-gate test` |
| 4 | Block 9 (inert submission.py) | `refactor(qlt-001): extract inert submission.py with submit_ad` |
| 5 | Block 10 (bot rewire) | `refactor(qlt-001): rewire process_preview to submit_ad; delete update_ad_and_moderate` |
| 6 | Block 11 (test_edit.py) | `test(qlt-001): add test_edit.py integration tests for reactivation path` |
| 7 | Block 12 (edit.py migration) | `refactor(qlt-001): route ad_edit reactivation through submit_ad` |

> **Recommended:** Single PR with Commits 1-7 (or split into PR-per-finding). Within QLT-001, the staged sequence (A1→A2→A3→A4) must be maintained — each stage green before the next.

---

## 11. Artifacts

| Artifact | Status | Location |
|----------|--------|----------|
| Validated findings | ✅ Reference | `.ai/audit/99-validation/10-code-quality-validated-findings.md` |
| Source re-audit | ✅ Reference | `.ai/audit/99-validation/10-code-quality-source-reaudit.md` |
| Execution plan (this file) | ✅ Active | `.ai/plans/24-code-quality-fixes-execution.md` |
| Task template | ✅ Reference | `.ai/tasks/templates/task_template.yaml` |
| Verification task template | ✅ Reference | `.ai/tasks/templates/task_template_verification.yaml` |
| QLT-003 recorder (already exists) | ✅ Reference | `src/backend/apps/core/services/analytics.py` |
| QLT-003 exporter (missing) | ✅ Reference | `src/backend/apps/core/services/__init__.py` |
| QLT-003 existing test | ✅ Reference | `src/backend/apps/core/tests/test_analytics_service.py` |
| QLT-001 handler | ✅ Reference | `src/telegram_bot/handlers/ad_create.py` |
| QLT-001 edit view | ✅ Reference | `src/backend/apps/ads/views/edit.py` |
| QLT-001 test imports | ✅ Reference | `src/telegram_bot/tests/test_save_photo_integration.py` |
| QLT-003 auto_moderation | ✅ Reference | `src/backend/apps/moderation/services/auto_moderation.py` |
| QLT-003 contact (canonical) | ✅ Reference | `src/backend/apps/core/services/contact.py` |
| QLT-003 login | ✅ Reference | `src/telegram_bot/handlers/login.py` |
| QLT-003 trust_analytics | ✅ Reference | `src/backend/apps/analytics/services/trust_analytics.py` |
| QLT-002 autocomplete | ✅ Reference | `src/backend/apps/search/views/autocomplete.py` |
| QLT-002 entity_suggestions | ✅ Reference | `src/backend/apps/search/services/entity_suggestions.py` |
| QLT-002 popular_search | ✅ Reference | `src/backend/apps/search/services/popular_search.py` |
| QLT-002 template consumer | ✅ Reference | `src/backend/templates/components/header_catalog.html` |
| QLT-002 tests | ✅ Reference | `src/backend/apps/search/tests/test_autocomplete.py` |
| QLT-005 cache_service | ✅ Reference | `src/backend/apps/lookups/services/cache_service.py` |
| QLT-005 builder | ✅ Reference | `src/backend/apps/categories/catalog/builder.py` |
| QLT-005 search_history | ✅ Reference | `src/backend/apps/search/services/search_history.py` |
| QLT-003 deferred batch site | ✅ Reference | `src/backend/apps/search/management/commands/send_alerts.py` |
| SearchSuggestionSource enum | ✅ Reference | `src/backend/apps/core/enums.py` (`class SearchSuggestionSource`) |
| ruff config | ✅ Reference | `pyproject.toml [tool.ruff.lint]` (lines ~117-128) |
| basedpyright config | ✅ Reference | `pyproject.toml [tool.basedpyright]` (lines ~187-195) |

---

*This plan is execution-oriented. It decomposes 5 validated code-quality findings into 12 dependency-aware execution blocks with semantic anchors (no line numbers in implementation scope), inline safety gates, and a clear verification matrix. QLT-003 is partially implemented — the plan accounts for the existing `record_event` function and the remaining 7 inline migration sites. The QLT-001→QLT-003 ordering constraint is assessed and relaxed. Generated: 2026-09-11 — Planning only. No code modified.*
