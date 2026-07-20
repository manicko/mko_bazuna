# Research Report: Ad Lifecycle Transitions Centralization

**Task ID:** task_004_research_ad_transition_centralization  
**Date:** 2026-07-20  
**Status:** COMPLETE - RECOMMENDATION: GO-WITH-CHANGES  

---

## 1. Enumerated Transition Call Sites

### 1.1 Direct `status=` Assignments (Mutators)

| File | Line(s) | Current Status → New Status | Context |
|------|---------|---------------------------|---------|
| `ads/views/edit.py` | 104 | `ON_MODERATION` (reactivation entry) | `ad_edit()` reactivation flow |
| `ads/views/edit.py` | 133 | `ON_MODERATION` (text edit) | `ad_edit()` text edit on PUBLISHED |
| `ads/views/edit.py` | 187 | `ARCHIVED` | `ad_archive()` manual archive |
| `ads/views/edit.py` | 221 | `ON_MODERATION` | `ad_reactivate()` reactivation entry |
| `ads/views/delete.py` | 49 | `DELETED` | `ad_delete()` soft delete |
| `moderation/services/moderation_log.py` | 177 | `ON_MODERATION_FAILED` | `set_moderation_failed()` |
| `moderation/services/moderation_log.py` | 193 | `REJECTED` | `set_rejected()` |
| `moderation/services/moderation_log.py` | 215 | `PUBLISHED` | `set_published()` |
| `telegram_bot/handlers/ad_create.py` | 542 | `ON_MODERATION_FAILED` | `_update_and_moderate()` failed moderation |
| `telegram_bot/handlers/ad_create.py` | 557 | `PUBLISHED` | `_update_and_moderate()` auto-publish (DUPLICATE LOGIC) |
| `moderation/admin_actions.py` | 35 | `PUBLISHED` | `approve_ad()` manual approve |
| `moderation/admin_actions.py` | 56 | `REJECTED` | `reject_ad()` manual reject |
| `moderation/admin_actions.py` | 104 | `DELETED` | `soft_delete_ad()` moderator delete |
| `core/management/commands/archive_sweep.py` | 60 | `ARCHIVED` | bulk `.update()` for 60-day sweep |
| `core/management/commands/delete_sweep.py` | N/A | N/A | Uses `.delete()`, no status update |
| `core/management/commands/purge_failed_ads.py` | N/A | N/A | Uses `.delete()`, no status update |
| `core/management/commands/purge_rejected_ads.py` | N/A | N/A | Uses `.delete()`, no status update |
| `users/services/deletion.py` | 97 | `DELETED` | `soft_delete_user_ads()` bulk `.update()` |

### 1.2 Read-Only Status Checks (Consumers using `status=`)

| File | Line(s) | Usage |
|------|---------|-------|
| `search/views/search.py` | 40 | `status=AdStatus.PUBLISHED` filter (public listings) |
| `ads/views/listings.py` | 46, 87 | `status=AdStatus.PUBLISHED` filter (ad detail, listings) |
| `ads/views/dashboard.py` | 40-54 | Status-grouped queries for user dashboard |
| `moderation/views/review.py` | 46, 70, 94 | Moderation queue filtering |
| `moderation/admin_actions.py` | 32, 53, 101, 129, 148, 149, 196 | Status checks in admin actions |
| `ads/views/edit.py` | 80, 123, 186, 219 | Status checks for edit flow control |
| `core/services/contact.py` | 43, 85 | Contact eligibility check (PUBLISHED only) |
| `telegram_bot/handlers/contact.py` | 136 | Contact eligibility check (PUBLISHED only) |

---

## 2. Allowed Transition Matrix (from Ad model docstring)

```
DRAFT → ON_MODERATION
ON_MODERATION → PUBLISHED | REJECTED | ON_MODERATION_FAILED
PUBLISHED → ARCHIVED → PUBLISHED (reactivation)
PUBLISHED → ON_MODERATION (text edits, hidden)
any → DELETED
```

**Timer Side-Effects:**
- `published_at`: Set on every → PUBLISHED transition, drives archive timer
- `original_published_at`: Set once on FIRST publish, IMMUTABLE (audit only)
- `archived_at`: Set on → ARCHIVED transition
- `deleted_at`: Set on → DELETED transition
- `moderation_failed_at`: Set on → ON_MODERATION_FAILED
- `rejected_at`: Set on → REJECTED

---

## 3. Call Sites Requiring Rewiring (feeds TASK_005)

### 3.1 Must Rewire - Individual Instance Transitions

| Component | Location | Action |
|-----------|----------|--------|
| `ads/views/edit.py` | `ad_archive()` line 187 | Replace `ad.status = AdStatus.ARCHIVED` |
| `ads/views/edit.py` | `ad_reactivate()` line 221 | Replace `ad.status = AdStatus.ON_MODERATION` |
| `ads/views/edit.py` | `ad_edit()` lines 104, 133 | Replace `ad.status = AdStatus.ON_MODERATION` |
| `ads/views/delete.py` | `ad_delete()` line 49 | Replace `ad.status = AdStatus.DELETED` |
| `moderation/services/moderation_log.py` | `set_moderation_failed()` line 177 | Replace `ad.status = AdStatus.ON_MODERATION_FAILED` |
| `moderation/services/moderation_log.py` | `set_rejected()` line 193 | Replace `ad.status = AdStatus.REJECTED` |
| `moderation/services/moderation_log.py` | `set_published()` line 215 | Replace `ad.status = AdStatus.PUBLISHED` |
| `moderation/admin_actions.py` | `approve_ad()` line 35 | Replace `ad.status = AdStatus.PUBLISHED` |
| `moderation/admin_actions.py` | `reject_ad()` line 56 | Replace `ad.status = AdStatus.REJECTED` |
| `moderation/admin_actions.py` | `soft_delete_ad()` line 104 | Replace `ad.status = AdStatus.DELETED` |
| `telegram_bot/handlers/ad_create.py` | `_update_and_moderate()` lines 542, 557 | Replace inline status assignments (should use `set_published`/`set_moderation_failed` OR `transition_to`) |

### 3.2 Must NOT Rewire - Bulk Operations

| Component | Location | Reason |
|-----------|----------|--------|
| `core/management/commands/archive_sweep.py` | line 59-61 | Uses `queryset.update()` for performance; bypassing model logic is intentional for batch operations |
| `users/services/deletion.py` | line 96-98 | Uses `queryset.update()` for performance; bulk user ad deletion |

**Note:** These bulk operations intentionally bypass transition guards for performance and do not need centralized transition logic.

---

## 4. `transition_to()` Signature Proposal

```python
from django.utils import timezone
from apps.core.enums import AdStatus

def transition_to(
    self,
    target_status: AdStatus,
    *,
    ad_moderator_id: int | None = None,
    ad_rejected_at: bool = False,  # Used by set_rejected for moderated_by
) -> None:
    """
    Atomically transition ad to a new status with timer side-effects.
    
    Validates transition is allowed per lifecycle matrix before state change.
    Handles published_at/original_published_at timestamps for PUBLISHED transitions.
    
    Args:
        target_status: The target AdStatus to transition to.
        ad_moderator_id: Optional moderator ID for PUBLISHED/REJECTED transitions.
        ad_rejected_at: If True, set rejected_at (for set_rejected delegation).
        
    Raises:
        ValueError: If the transition is not allowed from current status.
    """
```

**Alternative signatures to consider:**
- `transition_to(target_status: AdStatus, moderator_id: int | None = None) -> None` - simpler, relies on callers to set `moderated_by_id` separately if needed
- `transition_to(target_status: AdStatus, **timestamp_fields) -> None` - allows explicit timestamp control for testing

---

## 5. Research Conclusions

### Recommendation: **GO-WITH-CHANGES**

**Reasons to proceed:**
1. **Valid transitions are well-defined and stable** - The matrix in the Ad docstring has remained consistent
2. **Multiple scattered transition points** create risk for invalid state mutations
3. **Timer logic is duplicated** - `set_published()` and `_update_and_moderate()` both set `published_at` and `original_published_at` independently
4. **Validation is missing** - No guard against invalid transitions at the model level

**Key Changes Required:**
1. Add `transition_to()` method to `Ad` model after `__str__` method
2. `set_published()`, `set_moderation_failed()`, `set_rejected()` should delegate to `transition_to()`
3. `ad_archive()`, `ad_reactivate()`, `ad_delete()` should use `transition_to()`
4. `_update_and_moderate()` in `ad_create.py` should use `set_published()`/`set_moderation_failed()` instead of inline assignments
5. `admin_actions.py` functions should use `transition_to()` (or the set_* helpers)
6. Bulk sweeps (`archive_sweep`, `soft_delete_user_ads`) should remain as-is using `.update()`

**Critical Observation:**
The `_update_and_moderate()` function in `ad_create.py` (lines 542-560) contains **duplicate timer logic** that should be consolidated into `set_published()`. This is a bug: the ad creation flow bypasses `set_published()` and duplicates its core logic, creating a second source of truth for timestamp handling.

---

## 6. Files Modified for This Research

None - this is a research task. The implementation will be tracked in TASK_005.