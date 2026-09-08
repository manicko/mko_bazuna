# DB-002 Implementation Plan — `max_ads_per_user` TOCTOU Fix

**Handoff source:** Auditor report (Block 2: DB-002) + existing plan at `.ai/plans/03_db_concurrency_fix_matrix.md` (lines 59–117).
**Dependency gate:** DB-001 (bot `close_old_connections` middleware) MUST be deployed first — commit `2039249` confirms it is already committed. The `select_for_update()` lock in DB-002 needs a healthy, refreshable connection (see Rollout Safety, §3 of validated findings).
**Risk class:** Complex / High-risk — contract change: `set_published` raises a new typed exception, rippling across 3 writer paths.
**Migration required:** No — this is a pure concurrency-guard logic change. No schema change.

---

## 0. Executive Summary

The `max_ads_per_user` advisory count (`_validate_max_ads_per_user`, plain `.count()`) has a TOCTOU race: two concurrent publishes can both pass the count check and both commit, exceeding the cap. Additionally, the web `approve_ad` path performs **no** count check at all.

**Fix:** Centralize an authoritative, locked re-count inside `set_published`'s existing `transaction.atomic()`. Lock the `User` row via `User.objects.select_for_update().get(pk=ad.user_id)`, re-count `Ad` rows with `status ∈ {PUBLISHED, ON_MODERATION}`, and raise `MaxAdsExceeded` if `count >= max_ads` *before* calling `transition_to(PUBLISHED)`.

**Why one edit covers all writers:** All three publish paths converge on `set_published`:
- Bot: `ad_create.py:1233` → `auto_moderate(ad)` → `_pass_moderation(ad)` → `set_published(ad)`
- Web review: `review.py:65` → `admin_actions.approve_ad` → `set_published(ad, moderator_id=...)`
- Web bulk: `admin_actions.bulk_approve` → `approve_ad` → `set_published(ad, moderator_id=...)` (no separate web-path edit needed)

---

## 1. Decision Outcomes (D1–D5)

### D1: Getting `max_ads` inside `set_published` — **Chosen: option (a)**

`set_published` calls `ModerationCriteria.get_singleton().max_ads_per_user` directly (fresh, uncached) at the top of its `transaction.atomic()` block.

**Rationale:** This is the *authoritative* race-safety check — the cached 300s value is intentionally stale and must not be trusted for a lock-then-re-count sequence. The advisory pre-check in `auto_moderate` (`_validate_max_ads_per_user` using the cached tuple) remains as a fast-path rejection for the common over-cap case; the locked re-count inside `set_published` is the ground truth.

> **Do NOT** pass `max_ads` as an optional parameter (option c). It would require every caller to supply it, including the web path (`admin_actions.approve_ad`) which currently has no `max_ads` available. Fetching directly from the singleton inside `set_published` keeps the contract simple and is a single-point change.

### D2: When re-count fails — **Chosen: raise, do NOT call `_fail_moderation` from inside `set_published`**

`set_published` raises `MaxAdsExceeded`. The exception propagates up through:
- `_pass_moderation`'s `transaction.atomic()` (rolls back → User lock released, no PUBLISHED transition, no AnalyticsEvent committed)
- `auto_moderate` catches it → calls `_fail_moderation(ad)` → returns `False`

**Rationale (Tech Lead decision from plan, line 65):** `set_published` lives in `moderation_log.py`; `_fail_moderation` lives in `auto_moderation.py`. Calling `_fail_moderation` from `set_published` would create a cross-module dependency in the wrong direction and would also fail for the web path (where `set_published` is called directly from `admin_actions.approve_ad` with no auto-fail expectation). Letting the exception propagate is the clean contract: the caller decides how to handle the failure.

**Web path UX (review.py `approve_ad` view):** The moderator manually approved — the right UX is to block the publish, leave the ad in `ON_MODERATION`, and show the moderator an error message on the admin change page. The ad must NOT silently transition to `ON_MODERATION_FAILED` (that would erase the moderator's explicit approval intent and require moderator intervention to re-approve).

### D3: Exception handling at callers — **Chosen: catch at each public boundary**

| Caller | Location | Handling |
|--------|----------|----------|
| **Bot** `auto_moderate` | `auto_moderation.py:164` (`_pass_moderation(ad)`) | Wrap `_pass_moderation(ad)` in `try/except MaxAdsExceeded`: call `_fail_moderation(ad)` + `return False`. Bot handler at `ad_create.py:1233` is **unchanged** — `auto_moderate` already returns `False`, and the handler already shows "Ad failed moderation" (line 1239). `MaxAdsExceeded` never reaches the bot handler. |
| **Web review view** | `review.py:51-68` (`approve_ad` view) | Wrap `do_approve(...)` in `try/except MaxAdsExceeded`: log at WARN level, add a user-visible error message (via `django.contrib.messages` — see note below), redirect back to the review page. Ad stays `ON_MODERATION`. |
| **Web bulk** `bulk_approve` | `admin_actions.py:114-129` | Wrap per-ad `approve_ad(...)` call in `try/except MaxAdsExceeded`: log + `continue` (skip that ad, do NOT abort the entire bulk operation). |
| **Web single** `admin_actions.approve_ad` | `admin_actions.py:25-41` | **No change** — let `MaxAdsExceeded` propagate to the calling view. The single-ad path has no sensible "continue" behavior; the view decides UX. |

**Messages framework note:** `django.contrib.messages` is NOT currently imported anywhere in `src/backend/`. However, the review template (`review.html`) is a standard Django template rendered via `render()`, so `django.contrib.messages` is available (it's in `INSTALLED_APPS` by default). The Implementor should add `from django.contrib import messages` to `review.py` and display the message in the template. Alternatively, return an `HttpResponseBadRequest` (400) with a translated message — simpler, no template change. **Decision deferred to Implementor** (see OQ-2).

### D4: `exceptions.py` is untracked — **Chosen: rewrite + `git add`**

`exceptions.py` exists on disk but is `git status`?` `??` (untracked). It currently has `MaxAdsExceeded(user_id, limit)` with `self.limit`. **The plan (line 70) requires `MaxAdsExceeded(user_id, active_count, max_ads)`** — 3 args with `active_count` carrying the real-time count for diagnostics.

The Implementor must **rewrite** the existing file to the 3-arg signature and `git add` it. Do NOT leave the 2-arg version — it will not match the `raise MaxAdsExceeded(user_id=..., active_count=..., max_ads=...)` call site in `set_published`.

### D5: `_validate_max_ads_per_user` advisory pre-check — **Chosen: keep as-is**

Keep the advisory pre-check in `auto_moderate` (line 154). It is a fast-path optimization: the cached 300s criteria lets the bot reject the common over-cap case *before* hitting the DB lock, reducing lock contention. It is redundant with the authoritative re-count in `set_published`, but it is not harmful (the worst case is it says "pass" and `set_published` catches the real race). The `check()` function (line 338) also keeps using it for pre-submission validation.

> No change to `_validate_max_ads_per_user` or `_get_cached_criteria`.

---

## 2. File-by-File Implementation Requirements

### 2.1 `src/backend/apps/moderation/services/exceptions.py` — REWRITE + `git add`

**Current state:** Untracked file with 2-arg `MaxAdsExceeded(user_id, limit)`.
**Action:** Rewrite to 3-arg signature with `error_code` and docstring describing the locked re-count design.

```python
"""
Custom exceptions for moderation services.

Each exception has a single, well-defined trigger condition and a stable
``error_code`` attribute so callers can branch on it without string matching.
"""

__all__ = ["MaxAdsExceeded"]


class MaxAdsExceeded(Exception):
    """Raised when a user has reached their maximum active-ads limit.

    Triggered inside ``set_published()`` when the authoritative, locked
    re-count of PUBLISHED + ON_MODERATION ads exceeds
    ``ModerationCriteria.max_ads_per_user``.  This is the race-safe guard:
    the early check in ``auto_moderate()`` / ``check()`` is advisory only;
    the authoritative check inside ``set_published()`` runs under
    ``select_for_update()`` with the user row locked.
    """

    error_code = "max_ads_exceeded"

    def __init__(self, user_id: int, active_count: int, max_ads: int) -> None:
        self.user_id = user_id
        self.active_count = active_count
        self.max_ads = max_ads
        super().__init__(
            f"User {user_id} has reached the maximum of {max_ads} active ads "
            f"(currently has {active_count})."
        )
```

**Verification:** `git add src/backend/apps/moderation/services/exceptions.py`

### 2.2 `src/backend/apps/moderation/services/moderation_log.py` — EDIT `set_published`

**Current `set_published` (lines 208–224):** Has `transaction.atomic()` wrapping `transition_to(PUBLISHED)` + logging, but no lock, no re-count, no raise.

**Action:** Add imports at module level; insert lock + re-count + raise at the top of the existing `transaction.atomic()` block.

**New imports (add to the existing import section, lines 8–14):**

```python
# Existing imports (lines 8–14):
import logging
from typing import TYPE_CHECKING

from django.db import transaction

from apps.core.enums import AdStatus, ModeratorActionType
from apps.moderation.models import ModeratorActionLog

# ADD:
from apps.ads.models import Ad  # module-level — safe, no circular import (ads.models does not import moderation)
from apps.moderation.services.exceptions import MaxAdsExceeded
from apps.moderation.models import ModerationCriteria  # extend existing import
from apps.users.models import User
```

> **Circular-import check:** `apps.ads.models` does not import from `apps.moderation`. `apps.users.models.User` (extends `AbstractUser`) does not import from `apps.moderation`. `ModerationCriteria` is in the same app as the existing `ModeratorActionLog` import. Safe.

**Modified `set_published` (lines 208–224 → new body):**

```python
def set_published(ad: "Ad", moderator_id: int | None = None) -> None:  # noqa: UP037
    """Set ad status to PUBLISHED with optional moderator and log the action.

    Wrapped in ``transaction.atomic()`` to ensure the status transition and
    audit log entry are committed or rolled back together (DB-002).

    Before transitioning, locks the User row (``select_for_update``), fetches
    the current ``max_ads_per_user`` from the singleton, and performs an
    authoritative re-count of the user's active ads (PUBLISHED + ON_MODERATION).
    Raises ``MaxAdsExceeded`` if the count is at or above the cap — the
    transaction rolls back, releasing the User lock, and the ad remains in its
    current status.

    Args:
        ad: The Ad instance to publish.
        moderator_id: The moderator user ID (None for auto-publish).

    Raises:
        MaxAdsExceeded: If the user has already reached their active-ads cap.
    """
    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]
        # DB-002: lock User row + authoritative re-count (closes TOCTOU for all 3 writers)
        User.objects.select_for_update().get(pk=ad.user_id)
        max_ads = ModerationCriteria.get_singleton().max_ads_per_user
        active_count = Ad.objects.filter(
            user_id=ad.user_id,
            status__in=[AdStatus.PUBLISHED, AdStatus.ON_MODERATION],
        ).count()
        if active_count >= max_ads:
            raise MaxAdsExceeded(
                user_id=ad.user_id,
                active_count=active_count,
                max_ads=max_ads,
            )

        ad.transition_to(AdStatus.PUBLISHED, moderator_id=moderator_id)

        if moderator_id:
            log_manual_publish(ad_id=ad.id, moderator_id=moderator_id)
        else:
            log_auto_publish(ad_id=ad.id, user_id=ad.user_id)
```

**Key correctness point:** The `MaxAdsExceeded` is raised *inside* `transaction.atomic()`. Django rolls back the savepoint (or the full transaction if this is the outermost), releasing the `User` row lock. The `Ad` row is never modified because `transition_to` is called *after* the raise. This is correct.

### 2.3 `src/backend/apps/moderation/services/auto_moderation.py` — EDIT `auto_moderate`

**Current (line 164):**
```python
    # All checks passed - publish
    _pass_moderation(ad)
    return True
```

**Action:** Wrap `_pass_moderation(ad)` in `try/except MaxAdsExceeded`. Import `MaxAdsExceeded`.

**Import addition (after line 14, `from apps.core.enums import ...`):**
```python
from apps.moderation.services.exceptions import MaxAdsExceeded
```

> **No circular import:** `exceptions.py` has zero Django imports (pure Python). Safe to import at module level.

**Modified publish block (lines 163–165):**
```python
    # All checks passed - publish
    try:
        _pass_moderation(ad)
    except MaxAdsExceeded:
        # Authoritative locked re-count in set_published() found the user at
        # or over their cap.  _pass_moderation's transaction has already
        # rolled back (releasing the User lock); fail the ad for manual review.
        _fail_moderation(ad)
        return False
    return True
```

**Why this is correct:** `_pass_moderation` (lines 241–265) wraps `set_published(ad)` + 2× `AnalyticsEvent.objects.create()` in its own `transaction.atomic()`. When `set_published` raises, that inner transaction rolls back — no PUBLISHED transition, no analytics events, User lock released. Then `auto_moderate` catches and calls `_fail_moderation(ad)` which opens a *new* transaction to transition the ad to `ON_MODERATION_FAILED` and log it. The ad was still `ON_MODERATION` (untouched by the rolled-back `set_published`), so `ON_MODERATION → ON_MODERATION_FAILED` is a valid transition per the matrix.

### 2.4 `src/backend/apps/moderation/views/review.py` — EDIT `approve_ad` view

**Current (lines 49–68):**
```python
@require_POST
@staff_required
def approve_ad(request: HttpRequest, ad_id: int) -> HttpResponse:
    ...
    ad = get_object_or_404(Ad, id=ad_id, status=AdStatus.ON_MODERATION)
    do_approve(ad, request.user.id)
    logger.info(f"Admin {request.user.id} approved ad {ad_id}")
    return redirect(f"/admin/ads/ad/{ad_id}/change/")
```

**Action:** Wrap `do_approve(...)` in `try/except MaxAdsExceeded`. On catch: log WARN, add error message, redirect back to the review page (so the moderator sees the ad still in queue).

```python
@require_POST
@staff_required
def approve_ad(request: HttpRequest, ad_id: int) -> HttpResponse:
    ...
    ad = get_object_or_404(Ad, id=ad_id, status=AdStatus.ON_MODERATION)
    try:
        do_approve(ad, request.user.id)
    except MaxAdsExceeded as exc:
        logger.warning(
            f"Admin {request.user.id} attempted to approve ad {ad_id} "
            f"but user {exc.user_id} has reached their ad limit "
            f"({exc.active_count}/{exc.max_ads})."
        )
        messages.error(
            request,
            _("Cannot approve: the seller has reached their maximum active ads limit "
              "({active} of {max}). The ad remains in moderation.").format(
                active=exc.active_count, max=exc.max_ads
            ),
        )
        return redirect("moderation:review", ad_id=ad_id)

    logger.info(f"Admin {request.user.id} approved ad {ad_id}")
    return redirect(f"/admin/ads/ad/{ad_id}/change/")
```

**Imports to add:**
```python
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from apps.moderation.services.exceptions import MaxAdsExceeded
```

**i18n:** The error message uses `gettext_lazy` (project rule #16). Run `makemessages` after adding (see Quality Gates). The `messages` framework must be in `INSTALLED_APPS` — verify before implementing.

**Note on redirect target:** `redirect("moderation:review", ad_id=ad_id)` assumes a URL name `moderation:review`. Check `urls.py`; if no named URL exists, fall back to `"/moderation/review/{ad_id}/"` (hardcode is acceptable if that's the existing pattern — the current code hardcodes `/admin/ads/ad/{ad_id}/change/`).

### 2.5 `src/backend/apps/moderation/admin_actions.py` — EDIT `bulk_approve`

**Current (lines 114–129):**
```python
def bulk_approve(queryset, moderator_id: int) -> int:
    count = 0
    for ad in queryset.filter(status=AdStatus.ON_MODERATION):
        approve_ad(ad, moderator_id)
        count += 1
    return count
```

**Action:** Wrap per-ad `approve_ad(...)` in `try/except MaxAdsExceeded`. Import `MaxAdsExceeded`. Catch → log + `continue`.

```python
def bulk_approve(queryset, moderator_id: int) -> int:
    count = 0
    for ad in queryset.filter(status=AdStatus.ON_MODERATION):
        try:
            approve_ad(ad, moderator_id)
        except MaxAdsExceeded as exc:
            logger.warning(
                f"Bulk approve skipped ad {ad.id}: user {exc.user_id} "
                f"reached max ads ({exc.active_count}/{exc.max_ads})."
            )
            continue
        count += 1
    return count
```

**Import to add (top of file):**
```python
from apps.moderation.services.exceptions import MaxAdsExceeded
```

### 2.6 `src/backend/apps/moderation/services/__init__.py` — Optional export

The plan (line 71) says "(Optional) export `MaxAdsExceeded`". **Recommended:** add it for discoverability.

```python
from .exceptions import MaxAdsExceeded

__all__ = [
    ...
    "MaxAdsExceeded",
]
```

### 2.7 Bot handler `ad_create.py` — NO CHANGE REQUIRED

`auto_moderate(ad)` (line 1233) is called *outside* the `transaction.atomic()` block at line 1201 — but this is fine: `auto_moderate` catches `MaxAdsExceeded` internally (2.3) and returns `False`. The handler already shows "Ad failed moderation" (line 1239). **No edit needed here.**

---

## 3. Test Plan (new + existing)

### Existing tests that must remain green (verify after change):

| Test | File | Why it still passes |
|------|------|--------------------|
| `test_auto_moderate_pass_sets_published_and_analytics` | `test_auto_moderation.py:451` | Default cap=10, creates 1 ad; count=1 < 10 |
| `test_approve_ad_routes_through_set_published` | `test_admin_actions.py:38` | Mocks `set_published` — `MaxAdsExceeded` never fires |
| `test_approve_transitions_to_published` | `test_moderation_views.py:269` | Default cap=10, 1 ad; count=1 < 10 |
| `test_approve_ad_transitions_on_moderation_to_published` | `test_approve_ad_side_effects.py:37` | Default cap=10, 1 ad; count=1 < 10 (also mocks `on_commit`) |
| All `test_ad_lifecycle.py` tests | bot tests | Uses `permissive_criteria` (max_ads=100), 1–2 ads per test; count ≤ 2 < 100 |
| `test_approve_ad_no_alerts_when_immediate_alerts_disabled` | `test_approve_ad_side_effects.py:50` | count=1 < 10 |

### New tests to write:

**T1 — `test_moderation_log.py` (NEW file):**
- `test_set_published_raises_max_ads_exceeded` — directly call `set_published` on an ad whose user has `max_ads` PUBLISHED ads. Assert `MaxAdsExceeded` raised with correct `user_id`, `active_count`, `max_ads`. Assert ad status unchanged (rolled back).
- `test_set_published_succeeds_under_cap` — call `set_published` with `max_ads=2`, user has 1 active ad. Assert PUBLISHED, no raise.
- `test_set_published_lock_released_on_rollback` — verify the User row lock is released after the raise (structural assertion or follow-up query succeeds).

**T2 — `test_auto_moderation.py` (extend):**
- `TestMaxAdsRaceCondition` — two concurrent `auto_moderate` calls (threads) with `max_ads=2`, user has 1 PUBLISHED + 2 ON_MODERATION drafts. Assert exactly 1 PUBLISHED + 1 ON_MODERATION_FAILED after both complete (the classic TOCTOU proof test).

**T3 — `test_admin_actions.py` (extend):**
- `test_bulk_approve_skips_over_cap` — `bulk_approve` with 2 ON_MODERATION ads from a user at cap (1 existing PUBLISHED, 1 ON_MODERATION new, max=1). Assert 1 approved, 1 skipped, no exception raised, no abort.

**T4 — `test_moderation_views.py` (extend):**
- `test_approve_over_cap_returns_error` — POST to approve an ad whose user is at cap. Assert ad stays `ON_MODERATION`, response is a redirect (302) to review page, and an error message is present in the response context/cookie.

**Parametrize fixtures:** Tests that need a specific cap should use `monkeypatch` on `ModerationCriteria.get_singleton` or set the singleton's `max_ads_per_user` field directly and `.save()`.

---

## 4. Risk Analysis & Trade-offs

### Lock contention on the `User` row
- `SELECT FOR UPDATE` on the `User` row is held for the duration of `set_published`'s `transaction.atomic()` (lock + re-count + `transition_to` + logging). This is sub-millisecond in practice.
- **Risk:** If the DB connection dies mid-transaction (before DB-001 middleware was deployed), the lock is stranded. DB-001 is deployed first — mitigated.
- **Risk:** Under PgBouncer transaction-mode (confirmed in `base.py:188`), `SELECT FOR UPDATE` works correctly — the lock is tied to the transaction, released at commit. No issue.

### Deadlock potential
- **Web path:** fetch Ad (`select_for_update`) → `set_published` locks User → consistent order (Ad→User). No deadlock.
- **Bot path:** no Ad fetch → locks User only. No conflict with web.
- **Sweeps:** lock Ad rows in PK order, no User lock. No circular wait.
- Validated safe in plan §214–220.

### The `_fail_moderation` call in `auto_moderate` happens *outside* the User lock
- `set_published` raises → `_pass_moderation`'s tx rolls back (lock released) → `auto_moderate` catches → calls `_fail_moderation` (new tx, no User lock needed).
- This is safe because `ON_MODERATION → ON_MODERATION_FAILED` does not touch the user's ad count — no race window on the failure path.

### Web UX trade-off: keep ad in ON_MODERATION vs transition to ON_MODERATION_FAILED
- **Chosen:** Keep in `ON_MODERATION`, show moderator an error message. This preserves the moderator's intent and lets them retry if the cap is raised or another ad is archived.
- **Alternative (rejected):** Auto-fail the ad. This discards the moderator's explicit approval and forces the seller to re-submit. The plan explicitly rejects this for the web path (D2).
- **Bot path:** The ad *is* auto-failed (`_fail_moderation` in `auto_moderate`), which matches the existing pattern — the bot is not a human moderator, so auto-failing is appropriate. The seller can re-submit later.

### Cache staleness of `max_ads`
- `set_published` reads `ModerationCriteria.get_singleton().max_ads_per_user` fresh (not cached). If an admin lowers the cap from 10 to 5 mid-flight, the next publish will enforce 5 immediately. The advisory check in `auto_moderate` uses the 300s cache — it may still allow a re-count that later fails under the lock. This is acceptable: worst case is one extra locked re-count before the real rejection.

### `select_for_update` under SQLite
- Tests run against PostgreSQL (Docker `mko-bazuna-test-db` on port 5433). `select_for_update` works correctly. No SQLite test path to worry about.

---

## 5. Open Questions (for Implementor decision)

**OQ-1:** Confirm `django.contrib.messages` is in `INSTALLED_APPS` and its middleware is in `MIDDLEWARE`. If not, either add it (minimal config change) or fall back to `HttpResponseBadRequest` with a translated message. **Researcher not required** — check `settings.py`.

**OQ-2:** The review template (`review.html`) does not currently render `messages`. If using the messages framework, add a `{% if messages %}` block to `review.html`. If using `HttpResponseBadRequest` (400), no template change needed but the UX is a raw error page. **Decision:** Recommend `messages` + redirect (better UX, follows Django convention).

**OQ-3:** Should the bot handler give a *specific* "you've reached your ad limit" message instead of the generic "Ad failed moderation"? The plan intentionally does NOT change the bot handler (the error is generic). If a seller-specific message is desired, `auto_moderate` would need to return a richer error type, and `process_preview` (ad_create.py:841–849) would need to branch on it. **Out of scope for DB-002** — flagged for a future UX enhancement. **No Researcher required.**

**OQ-4:** `bulk_approve` logs + skips, but does not surface per-ad results to the caller. If the admin bulk-approves 20 ads and 3 are skipped, they see no feedback. **Consider:** return a list of skipped ad IDs from `bulk_approve`. **No Researcher required** — implementor decides; this is an enhancement, not a correctness issue.

---

## 6. Researcher Gates (when to summon Researcher)

| Point | Researcher required? | Rationale |
|-------|---------------------|-----------|
| R1 | **No** | D1 (fresh singleton fetch) is the obvious choice for an authoritative check — no research needed. |
| R2 | **No** | D2 (raise vs set_failed) is resolved by the Tech Lead decision in the plan (line 65). |
| R3 | **No** | D3 (caller handling) is determined by existing patterns: bot catches internally, web view catches, bulk catches per-ad. |
| R4 | **No** | D4 (exceptions.py untracked) is resolved: rewrite to 3-arg signature + `git add`. |
| R5 | **No** | D5 (advisory pre-check) is resolved: keep as-is (fast-path, not harmful). |
| R6 | **Yes — conditional** | Only if `django.contrib.messages` is NOT in `INSTALLED_APPS`. Then the Researcher should confirm the exact middleware setup needed for the test DB environment, to avoid a config drift. **Check settings first; summon only if missing.** |
| R7 | **No** | Deadlock analysis is already validated in the existing plan (§214–220). |
| R8 | **No** | Lock-contention thresholds are not a concern at this scale (sub-ms hold time, transaction-mode PgBouncer, DB-001 deployed first). |

**Conclusion:** The Researcher is required **only if** `django.contrib.messages` is absent from `INSTALLED_APPS` (OQ-1). All other decisions have sufficient precedent in the existing plan and codebase.

---

## 7. Quality Gates

```bash
# Lint + format
uv run ruff check \
  src/backend/apps/moderation/services/exceptions.py \
  src/backend/apps/moderation/services/moderation_log.py \
  src/backend/apps/moderation/services/auto_moderation.py \
  src/backend/apps/moderation/services/__init__.py \
  src/backend/apps/moderation/views/review.py \
  src/backend/apps/moderation/admin_actions.py

uv run ruff format --check src/backend/apps/moderation/

# Typecheck
uv run basedpyright \
  src/backend/apps/moderation/services/exceptions.py \
  src/backend/apps/moderation/services/moderation_log.py \
  src/backend/apps/moderation/services/auto_moderation.py

# No migration needed (no schema change)

# Tests (Docker only)
$dc run --rm -e PYTEST_OPTS="-k 'auto_moderation or admin_actions or moderation_views'" test

# New race-condition test (requires real concurrency — ensure --dist is NOT loadgroup
# for the specific race test, or mark it @pytest.mark.slow and run in a separate session)
$dc run --rm -e PYTEST_OPTS="-k 'TestMaxAdsRaceCondition'" test
```

**i18n:** If adding user-visible strings to templates (OQ-2), run:
```bash
uv run python src/backend/manage.py makemessages -l ru -l bs -l en --no-location
uv run python src/backend/manage.py compilemessages --locale ru --locale bs --locale en
```
Verify with `test_i18n_completeness.py`.

**Git:** `git add src/backend/apps/moderation/services/exceptions.py` — this is the critical step (D4). The file is currently untracked.

---

## 8. Rollout Sequence & Dependencies

```
[DB-001 already committed (2039249)]
    │
    ▼
[DB-002 — this plan]
  ├── Step 1: Rewrite exceptions.py + git add
  ├── Step 2: Edit set_published (lock + re-count + raise)
  ├── Step 3: Edit auto_moderate (catch + _fail_moderation)
  ├── Step 4: Edit review.py approve_ad view (catch + error response)
  ├── Step 5: Edit admin_actions.bulk_approve (catch per-ad)
  ├── Step 6: Edit services/__init__.py (export MaxAdsExceeded — optional)
  ├── Step 7: Write new tests (T1–T4)
  └── Step 8: Run quality gates + test suite
    │
    ▼
[DB-003 — depends on DB-002 being in review.py]
```

**Atomicity of deploy:** All 6 source files must deploy together. A partial deploy where `set_published` raises but `auto_moderate`/view haven't been updated would cause an unhandled exception to propagate to the bot handler (500) and the web view (500). The CI gate (quality gates above) ensures all files are consistent before merge. There is no viable incremental rollout — the contract change is atomic.
