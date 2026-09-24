---
phase: "05"
phase_name: "Ad Lifecycle, Categories & Moderation"
date: "2026-09-23"
auditor: "Executor (subagent)"
validator: "Validation Agent"
mode: "problems-only"
id_prefix: "AD"
report_status: "validated"
severity_taxonomy: ".kilo/commands/audit/phases/05-audit-ad-lifecycle.md#severity-taxonomy"
---

# Validated Audit Findings — Ad Lifecycle, Categories & Moderation

> Validation report for Phase 05 findings (AD-001 through AD-004). Source findings
> copied from `.ai/audit/05-ad-lifecycle/findings.md` with inline validation
> decisions applied. All evidence citations below are self-contained — the reader
> need not consult the original findings file or source code.

## Checkpoint 1 — Auditor analysis

- **Stage:** Auditor analysis
- **Findings in scope:** 4 (AD-001 CRITICAL, AD-002 HIGH, AD-003 MEDIUM, AD-004 MEDIUM)
- **Evidence anchor:** `.ai/audit/05-ad-lifecycle/findings.md` (copied as base); source files verified via direct inspection of `deletion.py`, `models.py` (Ad.transition_to, ALLOWED_TRANSITIONS), `auto_moderation.py`, `moderation_log.py`, `submission.py`, `signals.py`, `cache.py`, all six sweep/purge management commands, `conftest.py` (create_test_ad), and test files `test_search_cache.py`, `test_auto_moderation.py`, `test_ad_lifecycle.py`, `test_edit.py`.
- **Blockers:** None.
- **Checkpoint status:** Closed

## Checkpoint 2 — Researcher verification

- **Stage:** Researcher verification
- **Cross-phase conflicts:** 0 (verified against Phase 03 DB-concurrency findings — see VAL-001 below for merge candidate, not conflict)
  - **Merge candidates:** 1 — AD-004 Variant 1 (archive_sweep missing `select_for_update`) is the same root cause as **DB-010** (Phase 03, HIGH). Both address identical code and identical fix.
- **Per-finding decisions begun:**
  - AD-001: Validated (bypass confirmed at `deletion.py:217-220`)
  - AD-002: Validated (off-by-one confirmed in `auto_moderation.py:204-212` and `moderation_log.py:225-241`)
  - AD-003: Validated → Reclassified (code correct, docs stale → DOC-UPDATE)
  - AD-004: Validated (both variants confirmed in source)
- **Checkpoint status:** Closed

## Checkpoint 3 — Per-finding validation

All four findings passed technical-correctness verification against the actual source code. See the per-finding sections below.

- **Findings in scope:** 4 (Validated 3, Reclassified 1, Merged 0 inline, Rejected 0)
- **Per-finding decisions:** Validated: AD-001, AD-002, AD-004 | Reclassified: AD-003 | Merged: AD-004-Variant1 → DB-010 | Rejected: —
- **Evidence anchor:** Inline source citations in each finding's evidence blocks below.
- **Checkpoint status:** Closed

## Checkpoint 4 — Final consistency audit

- **Stage:** Final audit
- **Findings in scope:** 4 validated + 2 VAL- (cross-phase)
- **Pipeline integrity:** All checkpoints closed; report is self-contained.
- **Checkpoint status:** Closed

---

## Findings

### CRITICAL

#### AD-001: [CRITICAL] — `soft_delete_user_ads` bypasses the `transition_to` driver via `QuerySet.update()`

| Field | Value |
|:---|---|
| **ID** | AD-001 |
| **Title** | `soft_delete_user_ads` bypasses the `transition_to` driver via `QuerySet.update()` |
| **Severity** | CRITICAL |
| **Category** | State-machine integrity |
| **File(s)** | `src/backend/apps/users/services/deletion.py:217-220` |
| **Status** | Open |
| **Type** | [SPEC-DEVIATION] |

**Validation: VALIDATED** — All claims verified against source code.

**Problem** (verified): The consent-withdrawal service `soft_delete_user_ads` (in `apps/users/services/deletion.py`) soft-deletes all of a user's ads with a single bulk `Ad.objects.filter(user=user).update(status=AdStatus.DELETED, deleted_at=now)` at lines 217-220. Django's `QuerySet.update()` performs a direct SQL `UPDATE` that bypasses the model's `save()` method entirely — and therefore bypasses:

1. **`transition_to()` matrix validation** (`ALLOWED_TRANSITIONS` at `models.py:394-408`) — no check that DELETED is reachable from the current status. (In practice DELETED is always-allowed from any state, so this is latent rather than active.)
2. **`refresh_from_db()` staleness guard** (line 413) — no re-read of the current DB state.
3. **`post_save` signal firing** — the `@receiver(post_save, sender=Ad)` handler `bump_search_cache_on_ad_change` at `search/signals.py:63-64` is silently skipped.
4. **`updated_at` auto-refresh** — `updated_at = models.DateTimeField(auto_now=True)` (line 182) only fires on `save()`, not on `QuerySet.update()`, so consent-withdrawal leaves `updated_at` stale.

**Impact** (verified): The `transaction.on_commit(lambda: bump_search_cache_version())` at `deletion.py:228` is a band-aid that compensates **only** the search-cache version bump (confirmed: `bump_search_cache_version` in `search/services/cache.py:182-190` delegates to `bump_search_version`). It does **not** compensate:

- `updated_at` staleness (confirmed: `auto_now=True` does not fire on `QuerySet.update()`).
- Any future `post_save` receivers or `transition_to` side-effect logic added to the DELETED transition path.

The test at `search/tests/test_search_cache.py:933-957` (`TestSearchCacheInvalidationOnWithdrawal::test_withdrawal_bumps_cache_version`) confirms the historical bypass and locks in the `on_commit` compensation — but its comment (lines 936-938) explicitly states it is a fix for the cache bump only, not for the general signal/side-effect bypass.

**Root Cause** (verified): `QuerySet.update()` is treated as functionally equivalent to per-row `transition_to()` when it is not. The `on_commit` callback compensates one signal-derived side-effect (cache version) but leaves `updated_at` staleness and absent signal firing unaddressed.

**Recommendation** (validated, aligns with project patterns): Route consent-withdrawal soft-deletion through `transition_to(AdStatus.DELETED)` per row inside the existing `transaction.atomic()` block, or — if bulk performance is required — add a follow-up loop that calls `ad.save(update_fields=["status", "deleted_at"])` per row to fire `post_save` and refresh `updated_at`. The explicit `on_commit` cache bump should then be removed as redundant (since `transition_to` → `save(update_fields=["status", "deleted_at"])` fires the `post_save` signal, and `"status"` is in `_SEARCH_RELEVANT_FIELDS` at `signals.py:46`, so the cache version is bumped by the signal itself).

| Effort | Priority |
|:---|:---|
| M | P0 |

**Evidence — `apps/users/services/deletion.py:217-228`** (bypass confirmed):
```python
# Soft-delete all ads: set status=DELETED, deleted_at=now
ads_deleted = Ad.objects.filter(user=user).update(
    status=AdStatus.DELETED,
    deleted_at=now,
)
# ... explicit compensation only for cache:
transaction.on_commit(lambda: bump_search_cache_version())
```

**Evidence — `apps/ads/models.py:410-429`** (`transition_to` is the single source of truth):
```python
# DB-003: re-read from DB to defeat stale-state races (DB vs. bot
# process, concurrent sweeps). Raises Ad.DoesNotExist if a hard-delete
# sweep removed the row between caller fetch and transition.
self.refresh_from_db()
current = AdStatus(self.status)
# DELETED is a terminal state - no transitions allowed from it
if current == AdStatus.DELETED:
    raise ValueError(...)
# any -> DELETED is always allowed
if target == AdStatus.DELETED:
    if current != AdStatus.DELETED:
        self.status = AdStatus.DELETED
        self.deleted_at = timezone.now()
        self.save(update_fields=["status", "deleted_at"])  # fires post_save
    return
```

**Evidence — `apps/search/signals.py:46`** (`"status"` is in `_SEARCH_RELEVANT_FIELDS`):
```python
_SEARCH_RELEVANT_FIELDS = frozenset({
    "status", "title", "title_en", "title_bs",
    "description", "description_en", "description_bs",
    "category", "city", "price_amount", "price_normalized_eur",
    "listing_purpose", "listing_condition", "published_at",
})
```

**Evidence — `apps/search/tests/test_search_cache.py:936-938`** (test documents the historical bypass):
> Previously, soft_delete_user_ads used QuerySet.update() which bypasses post_save signals, so the cache version was NOT bumped on consent withdrawal. This test locks in the fix: the on_commit callback added to soft_delete_user_ads must fire after the transaction commits.

**Rollout safety:**
| ID | Risk | Backward-compatible? | Test gap (must cover) |
|:---|:---|:---|:---|
| AD-001 | High | No | Test that `updated_at` is refreshed on consent withdrawal; test that all `post_save` side-effects fire |

---

#### AD-002: [HIGH] — `max_ads_per_user` quota includes the ad being submitted/approved, over-blocking at limit boundary

| Field | Value |
|:---|---|
| **ID** | AD-002 |
| **Title** | `max_ads_per_user` quota includes the ad being submitted/approved, over-blocking at limit boundary |
| **Severity** | HIGH |
| **Category** | Moderation-gate correctness |
| **File(s)** | `src/backend/apps/moderation/services/auto_moderation.py:204-212`; `src/backend/apps/moderation/services/moderation_log.py:225-241` |
| **Status** | Open |
| **Type** | [SPEC-DEVIATION] |

**Validation: VALIDATED** — All claims verified against source code.

**Problem** (verified): Two checks count the in-flight ad as an "active" ad:

1. **Advisory check** (`_validate_max_ads_per_user`, `auto_moderation.py:204-212`): The function signature is `_validate_max_ads_per_user(user_id: int, max_ads: int)` — it takes **no** `ad_id` parameter and does **no** `.exclude(id=ad_id)`. At submission time the ad is already in `ON_MODERATION` (transitioned in `submit_ad` at `submission.py:232` before `auto_moderate` is called at line 243). So the count includes the current ad.

2. **Authoritative check** (`set_published`, `moderation_log.py:225-241`): Locks the user row with `select_for_update()`, counts `Ad.objects.filter(user_id=ad.user_id, status__in=[PUBLISHED, ON_MODERATION]).count()` — **no** `.exclude(id=ad.id)` — and uses `if active_count >= max_ads` (line 236). At publish time the ad is still `ON_MODERATION`, so it is counted.

Confirmed by `conftest.py:269`: `create_test_ad` defaults to `status=AdStatus.ON_MODERATION`, matching the real submission flow where the ad enters ON_MODERATION before moderation.

**Impact** (verified): With `max_ads_per_user = N`, a user with `N−1` PUBLISHED ads cannot submit or get approved for their Nth ad:
- Advisory check: count = N (N−1 PUBLISHED + 1 ON_MODERATION), `N < N` → `False` → ad sent to `ON_MODERATION_FAILED`.
- Authoritative check: count = N, `N >= N` → `True` → raises `MaxAdsExceeded`.
- Effectively capped at `max_ads − 1` active ads. With `max_ads=1`, even the first ad can never be published (count=1, `1 >= 1` → raises).

**Root Cause** (verified): `_validate_max_ads_per_user` receives no `ad_id` to exclude. By contrast, `_is_duplicate_title` at `auto_moderation.py:215-221` correctly uses `.exclude(id=ad_id)`. The `>=` comparison in `set_published` also contributes: it should either exclude the current ad or use `>` instead of `>=`.

**Recommendation** (validated, aligns with existing patterns): In `_validate_max_ads_per_user`, accept and exclude `ad_id` (mirroring `_is_duplicate_title`): `Ad.objects.filter(user_id=user_id, status__in=active_statuses).exclude(id=ad_id).count() < max_ads`. In `set_published`, exclude the current ad or change `>=` to `>`. The existing tests at `test_auto_moderation.py:528-599` and `:640-671` encode the current (incorrect) behavior and must be updated.

| Effort | Priority |
|:---|:---|
| S | P0 |

**Evidence — `apps/moderation/services/auto_moderation.py:204-212`** (advisory check, no ad_id exclusion):
```python
def _validate_max_ads_per_user(user_id: int, max_ads: int) -> bool:
    """Validate user has not exceeded max active ads limit."""
    active_statuses = [AdStatus.PUBLISHED, AdStatus.ON_MODERATION]
    count = Ad.objects.filter(
        user_id=user_id,
        status__in=active_statuses,
    ).count()
    return count < max_ads  # no .exclude(id=ad_id)
```

**Evidence — `apps/moderation/services/moderation_log.py:225-241`** (authoritative check, `>=` with no exclusion):
```python
with transaction.atomic():
    User.objects.select_for_update().get(pk=ad.user_id)
    max_ads = ModerationCriteria.get_singleton().max_ads_per_user
    active_statuses = [AdStatus.PUBLISHED, AdStatus.ON_MODERATION]
    active_count = Ad.objects.filter(
        user_id=ad.user_id,
        status__in=active_statuses,
    ).count()
    if active_count >= max_ads:  # raises at exactly max_ads, not above
        raise MaxAdsExceeded(...)
```

**Evidence — `test_auto_moderation.py:566-600`** (test encodes the off-by-one):
> With 0 existing PUBLISHED ads and 1 ON_MODERATION ad (the target):
> - max_ads=2: re-count = 1 (the ON_MODERATION ad) → 1 < 2 → passes.
> - max_ads=1: re-count = 1 (the ON_MODERATION ad) → 1 >= 1 → raises.

This proves that with `max_ads=1`, even the user's first ad (in ON_MODERATION) cannot be published — the ad itself is counted, making `1 >= 1` true.

**Rollout safety:**
| ID | Risk | Backward-compatible? | Test gap (must cover) |
|:---|:---|:---|:---|
| AD-002 | High | No | Test that a user with `max_ads-1` published ads can successfully submit the `max_ads`-th ad |

---

### MEDIUM

#### AD-003: [DOC-UPDATE] — `ARCHIVED → ON_MODERATION` transition exists in code but is absent from the spec's legal-transition list

> **Validation Note:**
> - **Action:** reclassified
> - **Detail:** Original type was `[SPEC-DEVIATION] / [DOC-UPDATE]`. Per the Phase 99 rule "If code is better than docs → reclassify as [DOC-UPDATE]": the code correctly implements and uses the `ARCHIVED → ON_MODERATION` transition, but the spec and class-level docstring omit it. No code change required.
> - **See also:** [VAL-001](#val-001-cross-phase-merge-candidate-ad-004-variant-1--db-010) (Phase 03 DB-010 covers the same archive_sweep code)

| Field | Value |
|:---|---|
| **ID** | AD-003 |
| **Title** | `ARCHIVED → ON_MODERATION` transition exists in code but is absent from the spec's legal-transition list |
| **Severity** | MEDIUM |
| **Category** | State-machine integrity |
| **File(s)** | `src/backend/apps/ads/models.py:402` |
| **Status** | Open |
| **Type** | [DOC-UPDATE] (was: [SPEC-DEVIATION]) |

**Validation: VALIDATED → RECLASSIFIED as [DOC-UPDATE]** — Code is correct; documentation is stale.

**Problem** (verified): The `ALLOWED_TRANSITIONS` matrix in `Ad.transition_to()` at `models.py:394-408` defines:

```python
AdStatus.ARCHIVED: {AdStatus.PUBLISHED, AdStatus.ON_MODERATION},
```

This allows an archived ad to transition to ON_MODERATION. The spec (`docs/01-spec/spec-index.md:80-82`) lists only:

```
`PUBLISHED → ARCHIVED → PUBLISHED` (reactivation); `PUBLISHED → ON_MODERATION` (text edit);
any → `DELETED`.
```

The `db-schema.md` (line 174) similarly lists only `PUBLISHED → ARCHIVED → PUBLISHED (reactivation, text re-moderation)` without explicitly listing `ARCHIVED → ON_MODERATION`.

**Impact** (verified): The transition is real and used in production code:

- `src/backend/apps/ads/views/edit.py:330-332`: The `ad_reactivate` view calls `ad.transition_to(AdStatus.ON_MODERATION)` when `ad.status == AdStatus.ARCHIVED`.
- `src/backend/apps/ads/services/submission.py:8-9`: The `submit_ad` docstring states "the web edit view's `ad_edit` reactivation branch, which transitions an `ARCHIVED` ad back to `ON_MODERATION`."
- `src/telegram_bot/tests/test_ad_lifecycle.py:211-215`: Test `test_original_published_at_immutable_on_second_moderation_cycle` exercises the full cycle `ARCHIVED → ON_MODERATION → PUBLISHED`.
- `src/backend/apps/ads/tests/test_edit.py:77-125`: `TestReactivationStatusTransition` tests verify `ARCHIVED → ON_MODERATION` via the web edit reactivation POST.

The **class-level docstring** at `models.py:27-38` lists:
```
- PUBLISHED -> ARCHIVED -> PUBLISHED (reactivation)
```
but omits `ARCHIVED → ON_MODERATION`. (Note: the **`transition_to` method docstring** at `models.py:367-392` DOES include it: `- ARCHIVED -> PUBLISHED | ON_MODERATION` at line 374. The omitting docstring is the class-level lifecycle summary, not the method-level transition matrix documentation.)

**Root Cause** (verified): The spec and class-level docstring were written before the edit-reactivation feature was added. The code and method docstring were updated, but the spec and class docstring were not.

**Evidence gap in original finding** (validation note): The original finding's evidence block for `models.py:33` shows two lines:
```
- PUBLISHED -> ARCHIVED -> PUBLISHED (reactivation)
- ARCHIVED -> PUBLISHED (reactivation)
```
The actual class docstring at `models.py:33` contains only the first line. The second line (`- ARCHIVED -> PUBLISHED (reactivation)`) does not exist at that location — it appears to be a conflation with the `transition_to` method docstring at `models.py:374` which states `- ARCHIVED -> PUBLISHED | ON_MODERATION`. This inaccuracy in the evidence does not affect the finding's validity: the omission of `ARCHIVED → ON_MODERATION` from the class-level docstring and the spec is real and verified.

**Recommendation** (validated): Update `spec-index.md` (line 81) to include `ARCHIVED → ON_MODERATION` in the legal-transition list. Update the class-level docstring at `models.py:30-35` to include `ARCHIVED → ON_MODERATION (edit-then-re-moderate)`. No code change required — the transition is correct and used.

| Effort | Priority |
|:---|:---|
| S | P2 |

**Evidence — `apps/ads/models.py:402`** (matrix includes ARCHIVED → ON_MODERATION):
```python
AdStatus.ARCHIVED: {AdStatus.PUBLISHED, AdStatus.ON_MODERATION},
```

**Evidence — `apps/ads/views/edit.py:330-332`** (production usage of ARCHIVED → ON_MODERATION):
```python
if ad.status == AdStatus.ARCHIVED:
    ad.transition_to(AdStatus.ON_MODERATION)
    # Run auto-moderation check
    auto_moderate(ad)
```

**Evidence — `docs/01-spec/spec-index.md:80-82`** (spec omits the transition):
```
`DRAFT → ON_MODERATION → PUBLISHED | REJECTED | ON_MODERATION_FAILED`;
`PUBLISHED → ARCHIVED → PUBLISHED` (reactivation); `PUBLISHED → ON_MODERATION` (text edit);
any → `DELETED`.
```

**Evidence — `test_ad_lifecycle.py:211-215`** (test exercises the cycle):
```python
# Full cycle: ARCHIVED -> ON_MODERATION -> PUBLISHED
ad.transition_to(AdStatus.ARCHIVED)
ad.refresh_from_db()
ad.transition_to(AdStatus.ON_MODERATION)
ad.refresh_from_db()
auto_moderate(ad)
```

**Rollout safety:**
| ID | Risk | Backward-compatible? | Test gap (must cover) |
|:---|:---|:---|:---|
| AD-003 | Low | Yes | None — documentation-only change |

---

#### AD-004: [BEST-PRACTICE] — Purge/sweep commands collect media keys before bulk DELETE without row locks (TOCTOU race)

| Field | Value |
|:---|---|
| **ID** | AD-004 |
| **Title** | Purge/sweep commands collect media keys before bulk DELETE without row locks (TOCTOU race) |
| **Severity** | MEDIUM |
| **Category** | Purge/sweep correctness |
| **File(s)** | `src/backend/apps/core/management/commands/archive_sweep.py:72-81`; `delete_sweep.py:63-78`; `purge_failed_ads.py:63-71`; `sweep_drafts.py:62-70` |
| **Status** | Open |
| **Type** | [BEST-PRACTICE] |

> **Validation Note:**
> - **Action:** merged (partial)
> - **Detail:** Variant 1 (archive_sweep missing `select_for_update`) is the same root cause as Phase 03 finding **DB-010** (HIGH). See [VAL-001](#val-001-cross-phase-merge-candidate-ad-004-variant-1--db-010). Variant 2 (hard-delete sweeps: pre-collect storage_keys before delete) is unique to this finding. Additionally, two commands not listed in the original finding — `purge_rejected_ads.py` and `purge_deleted_ads.py` — share the same Variant 2 pattern. See [VAL-002](#val-002-evidence-gap-ad-004-variant-2-under-reports-affected-commands).
> - **See also:** DB-010 (Phase 03), Phase 03 R-11 (complementary — confirms bulk DELETE WHERE self-corrects, distinct from the key-collection race)

**Validation: VALIDATED** — Both variants confirmed against source code.

**Variant 1 (archive_sweep)** — verified:
- `archive_sweep.py:73-75`: Iterates `queryset.order_by("pk")` **without** `.select_for_update()`. Each row is processed by `ad.transition_to(AdStatus.ARCHIVED)` (line 75).
- `Ad.transition_to()` at `models.py:413` calls `self.refresh_from_db()` (unlocked SELECT), then validates the transition matrix, then `self.save(update_fields=...)` at line 495.
- Since `PUBLISHED → ARCHIVED` is always valid in the matrix (`ALLOWED_TRANSITIONS[AdStatus.PUBLISHED] = {ARCHIVED, ON_MODERATION}` at `models.py:401`), a reactivated ad (ARCHIVED → PUBLISHED by the seller via `edit.py:332`) that appears in the pre-evaluated queryset will pass the matrix check and be re-archived by the sweep, even though its `published_at` was just reset to `now()` by the reactivation. The sweep does not re-check the `published_at < cutoff` filter after `refresh_from_db()`.
- **Cross-reference:** Every other Ad-status-mutating code path uses `select_for_update()` — `edit.py:116`, `edit.py:279` (archive), `edit.py:316` (reactivate), `delete.py:41`, `review.py:73` (approve_ad), `review.py:103` (reject_ad), `review.py:142` (ban_user_for_ad), `submission.py:167` (submit_ad). `archive_sweep` is the sole exception. (Confirmed by the grep in Phase 03 DB-010, findings.md:102-113.)

**Variant 2 (delete_sweep, purge_failed_ads, sweep_drafts)** — verified:
- All three commands follow the same pattern:
  ```python
  ad_ids = list(queryset.values_list("id", flat=True))       # T1: snapshot IDs
  storage_keys = [key for img in AdImage.objects.filter(ad_id__in=ad_ids) ...]  # T2: collect keys
  deleted_count, _ = queryset.delete()                       # T3: DELETE (WHERE re-evaluates)
  for storage_key in storage_keys:                           # T4: delete files
      delete_photo(storage_key)
  ```
- The `queryset.delete()` generates a `DELETE WHERE status=X AND timestamp_col < cutoff` SQL statement. If an ad transitioned out of the target status between T1 and T3, the DELETE's WHERE clause no longer matches that row, so it is **not** deleted from the DB. But `storage_keys` (collected at T2) still includes that ad's image keys, so `delete_photo()` at T4 physically removes files still referenced by a live (reactivated/submitted) ad.
- **Cross-reference:** Phase 03 R-11 confirmed that bulk `delete()` does not need `select_for_update()` for the DELETE operation itself (the WHERE clause self-corrects at execution time). The AD-004 Variant 2 issue is about the **key collection** that precedes the DELETE — a distinct concern from the DELETE's locking needs. No conflict exists between R-11 and AD-004 Variant 2.

**Evidence gap (validation finding):** The original finding lists three commands for Variant 2 (delete_sweep, purge_failed_ads, sweep_drafts) but two additional commands share the identical pattern:

- `purge_rejected_ads.py:64-73` — same `ad_ids` + `storage_keys` + `queryset.delete()` pattern.
- `purge_deleted_ads.py:64-73` — same pattern.

(`consent_hard_delete.py:67-93` also collects `storage_keys` at lines 72-76 before `queryset.delete()` at line 87, but its risk profile differs: it hard-deletes users whose ads are already in DELETED status, and DELETED is terminal in the transition matrix — so the likelihood of an ad transitioning out of DELETED between T1 and T3 is effectively zero.)

**Recommendation** (validated, aligns with project patterns):
- **Variant 1 (archive_sweep):** Add `.select_for_update()` to the queryset (same fix as Phase 03 DB-010).
- **Variant 2 (hard-delete sweeps):** Restructure to delete the Ad rows first, then collect `AdImage.storage_keys()` for images that **still exist** (orphaned ones) before physical deletion — or add a post-delete re-check that only deletes files for `AdImage` rows that were actually cascade-deleted. This fix does **not** require `select_for_update()` (consistent with Phase 03 R-11).

| Effort | Priority |
|:---|:---|
| M | P1 |

**Evidence — `archive_sweep.py:72-82`** (Variant 1: no `select_for_update`):
```python
for ad in queryset.order_by("pk"):       # ← no .select_for_update()
    try:
        ad.transition_to(AdStatus.ARCHIVED)  # ← refresh_from_db() sees current state,
    except (ValueError, Ad.DoesNotExist):   #   PUBLISHED→ARCHIVED is valid, proceeds
        logger.warning(...)
        continue
    updated_count += 1
```

**Evidence — `delete_sweep.py:63-78`** (Variant 2: keys collected before delete):
```python
ad_ids = list(queryset.values_list("id", flat=True))       # ← snapshot at T1
storage_keys = [                                          # ← collected at T2
    key
    for img in AdImage.objects.filter(ad_id__in=ad_ids)
    for key in img.storage_keys()
]
deleted_count, _ = queryset.delete()                      # ← DELETE at T3
for storage_key in storage_keys:                          # ← T4: deletes files
    delete_photo(storage_key)                              #   even if ad reactivated
```

**Evidence — `models.py:410-413`** (`refresh_from_db` is unlocked):
```python
# DB-003: re-read from DB to defeat stale-state races (DB vs. bot
# process, concurrent sweeps). Raises Ad.DoesNotExist if a hard-delete
# sweep removed the row between caller fetch and transition.
self.refresh_from_db()
```

**Rollout safety:**
| ID | Risk | Backward-compatible? | Test gap (must cover) |
|:---|:---|:---|:---|
| AD-004-V1 | Medium | Yes | Concurrent sweep + reactivation test; verify no re-archiving of reactivated ads |
| AD-004-V2 | Medium | Yes | Verify no media files deleted for live ads under concurrent status transition; test with purge_rejected_ads and purge_deleted_ads added |

---

## VAL-001: Cross-phase merge candidate — AD-004 Variant 1 and DB-010 (Phase 03)

- **Type:** Cross-phase merge candidate
- **Severity:** Informational (both findings are valid; same fix)
- **Finding:** AD-004 Variant 1 (Phase 05, MEDIUM) and DB-010 (Phase 03, HIGH) both identify the **same root cause**: `archive_sweep.py` iterates `Ad.objects.filter(status=PUBLISHED, published_at__lt=cutoff)` without `.select_for_update()`, then calls `transition_to(ARCHIVED)` per row, creating a race window between `refresh_from_db()` (unlocked read) and `save()` (write).
- **Fix:** Identical — add `.select_for_update().order_by("pk")` to the queryset in `archive_sweep.py:47-50`. Add a structural assertion to `test_sweep_archive.py`.
- **Recommendation:** Merge. Phase 03 DB-010 is the absorbing finding (higher severity: HIGH vs MEDIUM; more general framing as "lost-update race"). Phase 05 AD-004 Variant 1 adds the specific "reactivated ad re-archived" scenario as additional context. DB-013 (Phase 03, LOW — missing test) is the companion safety net that should be resolved alongside the fix.
- **Rollout note:** Both findings assign this to P1. No conflict — proceed with the single fix and associated tests.

## VAL-002: Evidence gap — AD-004 Variant 2 under-reports affected commands

- **Type:** Evidence incompleteness
- **Severity:** Informational
- **Finding:** AD-004 Variant 2 lists three affected commands (`delete_sweep.py`, `purge_failed_ads.py`, `sweep_drafts.py`) but two additional commands share the identical `storage_keys`-collected-before-`delete()` pattern:
  - `purge_rejected_ads.py:64-69` — same pattern.
  - `purge_deleted_ads.py:64-69` — same pattern.
- **Note:** `consent_hard_delete.py:72-76` also collects keys before delete, but its risk is negligible (DELETED is terminal — no transition can move an ad out of DELETED status between key collection and delete).
- **Recommendation:** Extend the Variant 2 fix and test coverage to include `purge_rejected_ads` and `purge_deleted_ads`.

---

## Cross-Finding Analysis

- **Merge candidates:**
  | Original Finding | Merged Into | Phase | Rationale |
  |---|---|---|---|
  | AD-004 Variant 1 (archive_sweep missing `select_for_update`) | DB-010 | Phase 03 | Same root cause (missing row lock), same code (`archive_sweep.py:47-50`), same fix (`.select_for_update()`), same test gap (DB-013). Phase 03 DB-010 absorbs Phase 05 AD-004 Variant 1 (higher severity, more general framing). |

- **Conflicting evidence:** None.
  - Phase 03 R-11 ("sweep commands using bulk `delete()` do not need `select_for_update`") — PASS is **complementary** to AD-004 Variant 2, not conflicting: R-11 validates that the DELETE's WHERE clause self-corrects (no locking needed for the DELETE), while AD-004 Variant 2 identifies a separate TOCTOU in the pre-DELETE key collection. Both are correct.
  - Phase 06 PII-002 confirms the consent-withdrawal flow (`withdraw_consent`) produces `status=DELETED` — consistent with AD-001's premise; no conflict.

- **Dependency chains:**
  | Finding | Depends On | Blocking? |
  |---|---|---|
  | AD-001 | None | No |
  | AD-002 | None | No |
  | AD-003 | None | No |
  | AD-004-V1 | None (overlaps DB-010 from Phase 03) | No — resolve concurrently with DB-010 |
  | AD-004-V2 | None | No |

---

## Rollout Analysis

### Sequencing

All four findings are independent of one another. The recommended fix order follows the existing roadmap in the original findings file:

1. **AD-001** (P0, CRITICAL) — consent withdrawal correctness
2. **AD-002** (P0, HIGH) — quota over-blocking
3. **AD-004** (P1, MEDIUM) — TOCTOU race (resolve concurrently with Phase 03 DB-010)
4. **AD-003** (P2, MEDIUM) — documentation update (can be done at any time)

### Backward compatibility

| Finding | Backward-compatible? | Risk | Notes |
|---|---|---|---|
| AD-001 | No | High | Switching from `QuerySet.update()` to `transition_to()` per-row changes signal behavior (post_save now fires) and refreshes `updated_at`. The `on_commit` cache bump becomes redundant and should be removed to avoid double-bumping. Tests must verify all side-effects fire. |
| AD-002 | No | High | Excluding the in-flight ad from the count changes the quota boundary. Tests at `test_auto_moderation.py:528-599` and `:640-671` encode the current (incorrect) behavior and must be updated. |
| AD-003 | Yes | Low | Documentation-only. No code or test changes required. |
| AD-004 | Yes | Medium | Adding `select_for_update()` (Variant 1) is backward-compatible but increases lock hold duration. Restructuring key collection (Variant 2) is backward-compatible. Tests must verify no media files deleted for live ads under concurrent transitions. |

### Rollback feasibility

| Finding | Rollback strategy |
|---|---|
| AD-001 | Revert to `QuerySet.update()` + `on_commit` compensation. No data migration needed (status and deleted_at already stored correctly). |
| AD-002 | Revert quota check to include current ad. Tests revert to encoding the off-by-one behavior. |
| AD-004 | Remove `select_for_update()` / revert key-collection restructure. No data migration needed. |

---

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 3 | AD-001, AD-002, AD-004 |
| Reclassified | 1 | AD-003: [SPEC-DEVIATION] → [DOC-UPDATE] |
| Merged (cross-phase) | 1 | AD-004 Variant 1 → DB-010 (Phase 03) |
| Rejected | 0 | — |
| VAL- (cross-phase / rollout) | 2 | VAL-001, VAL-002 |

### Rejected Findings

None.

### Merged Findings

| Original ID | Merged Into | Phase | Rationale |
|---|---|---|---|
| AD-004 Variant 1 (archive_sweep missing `select_for_update`) | DB-010 | Phase 03 | Same root cause: `archive_sweep.py` queryset lacks `.select_for_update()`. Same fix. DB-010 is absorbing (HIGH severity, more general "lost-update" framing; AD-004 Variant 1 adds the reactivation scenario as complementary context). DB-013 (Phase 03, LOW — missing test) is the companion. |

### Reclassified Findings

| ID | Original Type | New Type | Rationale |
|----|---------------|----------|-----------|
| AD-003 | [SPEC-DEVIATION] | [DOC-UPDATE] | Per Phase 99 rule: "If code is better than docs → reclassify as [DOC-UPDATE]." The `ALLOWED_TRANSITIONS` matrix correctly includes `ARCHIVED → ON_MODERATION` (models.py:402), the transition is used in production (`edit.py:332`), and is tested (`test_ad_lifecycle.py:211`, `test_edit.py:84-125`). The spec (`spec-index.md:81`, `db-schema.md:174`) and the class-level docstring (`models.py:33`) omit the transition. No code change needed — documentation update only. |

### Evidence Accuracy Notes

| Finding | Note |
|---|---|
| AD-003 | The finding's evidence block for `models.py:33` shows two lines (`- PUBLISHED -> ARCHIVED -> PUBLISHED (reactivation)` and `- ARCHIVED -> PUBLISHED (reactivation)`), but the class-level docstring at that line number contains only the first. The second line appears to be conflated with the `transition_to` method docstring at `models.py:374` (`- ARCHIVED -> PUBLISHED | ON_MODERATION`). This inaccuracy does not affect the finding's validity: the omission from the class docstring and spec is real. |

### VAL Findings

| ID | Finding |
|:---|:---|
| VAL-001 | Cross-phase merge candidate: AD-004 Variant 1 and DB-010 (Phase 03) identify the same root cause (archive_sweep missing `select_for_update()`). Fix and tests should be resolved together. |
| VAL-002 | Evidence gap: AD-004 Variant 2 under-reports affected commands. `purge_rejected_ads.py` and `purge_deleted_ads.py` share the identical storage_keys-before-delete pattern. `consent_hard_delete.py` also has the pattern but risk is negligible (DELETED is terminal). |
