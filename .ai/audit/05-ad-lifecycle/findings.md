---
# Report metadata — fill once per phase report.
phase: "05"
phase_name: "Ad Lifecycle, Categories & Moderation"
date: "2026-09-12"
auditor: "Executor (subagent)"
validator: ""  # Phase 99 only — omit/blank for raw phase findings
mode: "problems-only"
# Correct prefix per phase: 01-ENT, 02-CFG, 03-DB, 04-AUT, 05-AD, 06-PII, 07-MED, 08-SRH, 09-EXT, 10-QLT, 11-TST, 12-OPS, 13-PERF, 14-I18N
id_prefix: "AD"
# report_status = lifecycle of the report document (draft → validated)
# per-finding Status (in Findings Summary + field table below) = lifecycle of the individual finding (Open → Validated/Rejected/Merged/Reclassified/Deferred)
report_status: "draft"  # "draft" for raw phases; Phase 99 sets to "validated"
severity_taxonomy: ".kilo/commands/audit/phases/05-audit-ad-lifecycle.md#severity-taxonomy"  # pointer to phase rubric, NOT hardcoded
# Structural enforcement (replaces the buried ID-preservation comment):
---

# Audit Findings — Ad Lifecycle, Categories & Moderation

## Executive Summary

Eight problems were found across the ad lifecycle, category tree, and moderation gate. The most severe is a **missing re-moderation step on web text-edit**: when a seller edits the title/description of a live published ad, the ad is moved to `ON_MODERATION` but never auto-checked, so it never republishes automatically — published ads silently vanish from the site, and manually approving them publishes edited text without the automated safety checks. Two MEDIUM findings follow: the `ARCHIVED` purge window is measured from `published_at` (not `archived_at`, causing manual archives to outlive the intended window with an inconsistent doc), and the bot creates DRAFT rows with no concurrency/duplicate guard. The remainder are LOW: a stale draft-retention doc value, a full-scan draft sweep, a state-machine bypass in `archive_sweep`, a type-checker failure in a moderation test, and an `is_active` leak in keyword search.

> Note on IDs: `AD-001` and `AD-002` are pre-existing reference tags embedded in `apps/ads/models.py:396` (`# manual review of auto-failed ads (AD-001)`) and `docs/02-database/db-retention.md:20` (`purge_deleted_ads` command → `AD-002`); both map to already-implemented behavior confirmed by the test suite, so findings continue from `AD-003`.

## Scope & Methodology

**Scope:** Ad status enum + `transition_to` driver (`apps/ads/models.py`), the bot ad-creation FSM persisted as DRAFT rows (`telegram_bot/handlers/ad_create.py`), the auto-moderation gate (`apps/moderation/services/auto_moderation.py`, `moderation_log.py`, `admin_actions.py`, `views/review.py`, `views/api_bulk.py`), the web edit/reactivate views (`apps/ads/views/edit.py`), the category tree + rename triggers (`apps/categories/models.py`, `signals.py`, `apps/ads/management/commands/setup_search_triggers.py`), the photo-collection entity (`AdImage`), the six retention sweeps (`apps/core/management/commands/*sweep*.py`, `*purge*.py`), and the `db-retention.md` spec.

### Runtime Verification

Each claim below is reproducible. Concrete evidence is captured per finding.

| R# | Check | Method | Result |
|----|-------|--------|--------|
| R-01 | Full transition matrix + side-effects (published_at, original_published_at once-only, archived_at cleared on reactivate, search_vector on text-edit) | `-k lifecycle` (26 passed) + `-k moderation` (207 passed) + repro test `test_textedit_does_not_remoderate` | PASS (side-effects correct; re-moderation gap surfaced as AD-003) |
| R-02 | Forbidden transitions rejected (DRAFT→PUBLISHED, DELETED terminal, ARCHIVED→REJECTED, bulk PUBLISHED without published_at) | `test_ad_lifecycle.py`, `test_ad_constraints.py`, `test_admin_actions.py` | PASS |
| R-03 | Auto-check is the only gate before PUBLISHED; no DRAFT/ON_MODERATION/ON_MODERATION_FAILED ad in public listings/search | `search.py:65`, `listings.py:269` filter `status=PUBLISHED`; `auto_moderate` only caller of PUBLISH | PASS (no leak; AD-003 is a re-moderation gap, not a public leak) |
| R-04 | FSM DRAFT cleanup on cancel; 30-min sweep correctness | `cmd_cancel` deletes DRAFT+photos (`ad_create.py:105-119`); `test_deletes_drafts_older_than_30_minutes` | PASS (AD-009 is a duplicate-DRAFT gap, separate) |
| R-05 | Category integrity (no cycle/orphan; rename propagates name + search vector; admin-only) | `test_search_triggers.py` rename + i18n cascade (15 passed) | PASS (D5 satisfied) |
| R-06 | Purge/sweep: correct status+window+lock+cascade+idempotency | `test_sweep_commands.py` (all sweep tests pass; lock IDs asserted) | PASS (AD-005 is a retention-basis nuance, not a wrong-status purge) |
| R-07 | Lint + type-checker + lifecycle/moderation/category/photo test-suite | `ruff check` PASS; `basedpyright` FAIL (1 error); lifecycle 26 / moderation 207 / search-triggers 15 passed | LINT PASS, TYPECHECK FAIL (→ AD-008), TESTS PASS |

**Tools used:** `ruff check`, `basedpyright`, `grep -rn` (via Grep), `uv run pytest` inside the `mko-bazuna-test` Docker compose (DB healthy on :5433), source inspection of trigger SQL (`setup_search_triggers.py`).

**Assumptions:** PostgreSQL 18; Django 5.2 LTS; `django-stubs` is **not** installed (per inline comments), so `basedpyright` reports Django-API typing gaps; the bot runs as one process sharing the ORM with the web process; the scheduler runs sweeps hourly; categories are admin-managed via `load_catalog` (no public write endpoint for categories).

## Findings Summary

| ID | Title | Severity | Status | Category |
|----|-------|----------|--------|----------|
| AD-003 | Text-edit of a published ad skips auto-moderation (ad stuck hidden / edited text unmoderated) | HIGH | Open | Correctness |
| AD-005 | ARCHIVED purge measured from published_at, not archived_at (doc/spec retention conflict) | MEDIUM | Open | Data retention |
| AD-009 | Bot `/post` creates a DRAFT with no guard against an existing in-progress DRAFT (duplicate/orphan) | MEDIUM | Open | FSM persistence |
| AD-004 | db-retention.md lists DRAFT retention as 7 days; code enforces 30 minutes | LOW | Open | Documentation |
| AD-006 | sweep_drafts has no partial index on (status=DRAFT, created_at) → full table scan | LOW | Open | Performance |
| AD-007 | archive_sweep bypasses the transition_to driver via queryset.update() | LOW | Open | State-machine integrity |
| AD-008 | basedpyright fails on test_priority_service.py:500 (response.headers indexing; no django-stubs) | LOW | Open | Type safety |
| AD-010 | Ads in deactivated (is_active=False) categories still appear in keyword search | LOW | Open | Search correctness |

## Distribution

**Severity counts**

| HIGH | 1 |
| MEDIUM | 2 |
| LOW | 5 |

**Status counts**

| Status | Count |
|--------|-------|
| Open | 8 |

## Findings by Severity

### HIGH

#### AD-003: [HIGH] — Text-edit of a published ad skips auto-moderation (ad stuck hidden / edited text unmoderated)

| Field | Value |
|---|---|
| **ID** | AD-003 |
| **Title** | Text-edit of a published ad skips auto-moderation (ad stuck hidden / edited text unmoderated) |
| **Severity** | HIGH |
| **Category** | Correctness |
| **File(s)** | `src/backend/apps/ads/views/edit.py:208-230` (text-edit branch); compared with `edit.py:326-331` (reactivate) and `src/backend/apps/ads/services/submission.py:186` |
| **Status** | Open |
| **Problem** | The `has_text_change` branch of `ad_edit` sets the new title/description, persists via `ad.save()`, then calls `ad.transition_to(AdStatus.ON_MODERATION)` and redirects to the dashboard — but **never invokes `auto_moderate()`**. Every other path that lands an ad in `ON_MODERATION` runs auto-moderation: the bot's `process_preview` calls `submit_ad`→`auto_moderate` (`ad_create.py:813`, `submission.py:186`), and the web reactivation branch calls `auto_moderate(ad)` directly (`edit.py:331`). There is no `post_save` signal that auto-moderates (`moderation/signals.py` only computes priority and schedules alerts), so the text-edit path is the sole route into `ON_MODERATION` with no moderation follow-up. |
| **Impact** | (1) A published ad that the seller edits (a common action) is re-hidden in `ON_MODERATION` and **never automatically republished** — it sits hidden indefinitely until a human moderator reviews the queue, effectively removing the ad from the site. (2) If a moderator manually approves it, the **newly edited text is published without the automated checks** (title/description length, image count 1–5, banned words, duplicate-title, max-ads-per-user) — so edited content bypasses the auto-check gate that normally runs on submit. |
| **Root Cause** | The text-edit branch was implemented to re-hide the ad (PUBLISHED→ON_MODERATION) per zone C2 but copied the transition without wiring the `auto_moderate()` call that the reactivation and submit paths include. The two code paths (text-edit vs reactivation) diverged. |
| **Recommendation** | Mirror the reactivation path: after `ad.transition_to(AdStatus.ON_MODERATION)` in the text-edit branch, call `auto_moderate(ad)` and reuse its pass/fail semantics (pass → redirect to dashboard; fail → re-render `edit.html` with an error, matching the reactivation branch). |
| **Effort** | M |
| **Priority** | P0 |

**Evidence — `src/backend/apps/ads/views/edit.py:208-230`** *(supports: text-edit branch transitions to ON_MODERATION without calling auto_moderate)*:
```python
elif ad.status == AdStatus.PUBLISHED:
    if has_text_change:
        ad.title = new_title
        ad.description = new_description
        ad = _apply_price_change(ad, price_amount_value, price_currency_value)
        ad.save(update_fields=[...])
        # Use transition_to for status change to ON_MODERATION
        ad.transition_to(AdStatus.ON_MODERATION)
        logger.info(f"Ad {ad_id} text edited, moved to ON_MODERATION")
        # ↑ NO auto_moderate() call here (contrast reactivation at edit.py:328-331)
        return redirect("ads:dashboard")
```

**Evidence — contrast: reactivation path calls auto_moderate** *(supports: the sibling reactivation path invokes re-moderation, proving the text-edit branch is the divergence)*:
```python
# edit.py:326-331
if ad.status == AdStatus.ARCHIVED:
    ad.transition_to(AdStatus.ON_MODERATION)
    auto_moderate(ad)  # ← text-edit branch omits this
```

**Evidence — runtime repro** *(supports: auto_moderate is provably never called during text-edit; ad remains ON_MODERATION)*:
```text
test_textedit_does_not_remoderate PASSED
  assert mocked.call_count == 0   # auto_moderate NOT invoked by text-edit
  assert ad.status == AdStatus.ON_MODERATION   # ad stuck hidden, never republished
1 passed
```

**Related Findings:** AD-007 (both touch direct vs driver-managed state writes)

### MEDIUM

#### AD-005: [MEDIUM] — ARCHIVED purge measured from published_at, not archived_at (doc/spec retention conflict)

| Field | Value |
|---|---|
| **ID** | AD-005 |
| **Title** | ARCHIVED purge measured from published_at, not archived_at (doc/spec retention conflict) |
| **Severity** | MEDIUM |
| **Category** | Data retention |
| **File(s)** | `src/backend/apps/core/management/commands/delete_sweep.py:47-52`; `src/backend/apps/ads/models.py:299-303`; `docs/02-database/db-retention.md:30,78-82` |
| **Status** | Open |
| **Problem** | `delete_sweep` purges `ARCHIVED` ads where `published_at < now() - 120 days`, and the partial index `IX_ads_delete_sweep` is on `(status, published_at)` (condition `status=ARCHIVED`). The ARCHIVED retention window is therefore anchored to **publish time, not archive time**. For an auto-archived ad (archived by `archive_sweep` at 60 days after publish) this equals 2 months after archive — matching the spec. But for a **manually archived** ad (`ad_archive` view, PUBLISHED→ARCHIVED today) whose `published_at` is recent, the row survives ~120 days from publish, far exceeding the intended "2 months in ARCHIVED" window. Additionally `db-retention.md` labels ARCHIVED retention as "4 months" (line 30/79), while the phase spec defines it as "2 months" — the two specs disagree, and there is no partial index on `(status, archived_at)` to express a from-archive window. |
| **Impact** | Manually-archived ads are over-retained (stay hidden but consume DB/disk rows well past the intended 2-month ARCHIVED window). The doc/spec contradiction also misleads retention/GDPR analysis (Phase 06 consent erasure uses a separate 30-day path, so no PII leak, but the window math is undocumented and inconsistent). |
| **Root Cause** | The purge window reuses `published_at` (already indexed for the auto-archive→purge pipeline) instead of `archived_at`; the retention table in `db-retention.md` was written from the `published_at` reference point and was never reconciled with the phase spec's "2 months from archive" intent. |
| **Recommendation** | (a) Reconcile the retention table in `db-retention.md` to state the ARCHIVED window is "2 months measured from `archived_at`" (60 days) — or explicitly document the publish-anchored 120d design if over-retention is intentional; (b) if from-archive is intended, change `delete_sweep` to filter on `archived_at` and add a partial index `IX_ads_delete_sweep` on `(status, archived_at)`. |
| **Effort** | M |
| **Priority** | P1 |

**Evidence — `src/backend/apps/core/management/commands/delete_sweep.py:45-52`** *(supports: ARCHIVED purge keyed on published_at, 120-day cutoff)*:
```python
# Status is ARCHIVED, published_at older than 4 months
cutoff_date = timezone.now() - timedelta(days=120)
queryset = Ad.objects.filter(
    status=AdStatus.ARCHIVED,
    published_at__lt=cutoff_date,
)
```

**Evidence — `src/backend/apps/ads/models.py:299-303`** *(supports: purge index is on published_at, not archived_at)*:
```python
models.Index(
    name="IX_ads_delete_sweep",
    fields=["status", "published_at"],
    condition=Q(status=AdStatus.ARCHIVED),
),
```

**Evidence — `docs/02-database/db-retention.md:30,81-82`** *(supports: doc says ARCHIVED = "4 months" / DELETE_AGE_DAYS=120, vs spec 2 months)*:
```text
| ARCHIVED | 4 months | delete_sweep | IX_ads_delete_sweep |
| DELETE_AGE_DAYS = 120  # days before hard-deleting archived ads
```

**Evidence — runtime test codifying published_at basis** *(supports: test_sweep_commands TestDeleteSweep uses published_at@200d to trigger deletion)*:
```python
old = create_test_ad(..., status=AdStatus.ARCHIVED, published_at=timezone.now() - timedelta(days=200))
call_command("delete_sweep"); assert not Ad.objects.filter(pk=old.pk).exists()
```

**Related Findings:** AD-004 (both concern db-retention.md accuracy)

### LOW

#### AD-004: [LOW] — db-retention.md lists DRAFT retention as 7 days; code enforces 30 minutes

| Field | Value |
|---|---|
| **ID** | AD-004 |
| **Title** | db-retention.md lists DRAFT retention as 7 days; code enforces 30 minutes |
| **Severity** | LOW |
| **Category** | Documentation |
| **File(s)** | `src/backend/apps/core/management/commands/sweep_drafts.py:45`; `docs/02-database/db-retention.md:32,82`; `src/backend/apps/core/tests/test_sweep_commands.py:206` |
| **Status** | Open |
| **Problem** | `db-retention.md` documents DRAFT retention as "7 days" (lines 32 and 82) with no env var, but `sweep_drafts` hard-codes `timedelta(minutes=30)`, and the phase spec defines DRAFT retention as "30 minutes." The doc contradicts both the implementation and the spec. |
| **Impact** | Engineers/operators reading the doc believe abandoned drafts are retained for 7 days, skewing retention/GDPR and storage expectations; the doc is not a trustworthy source of truth. |
| **Root Cause** | The doc was not updated when the 30-minute DRAFT window was implemented (or vice-versa). |
| **Recommendation** | Update `db-retention.md` line 32 and line 82 to read "30 minutes" with advisory lock 4, matching `sweep_drafts.py` and the phase spec. Add a short note that the 30-min window bounds orphaned-photo exposure from a crashed bot FSM. |
| **Effort** | S |
| **Priority** | P2 |

**Evidence — `src/backend/apps/core/management/commands/sweep_drafts.py:44-45`** *(supports: code uses 30 minutes)*:
```python
# Query draft ads older than 30 minutes
cutoff_date = timezone.now() - timedelta(minutes=30)
```

**Evidence — `docs/02-database/db-retention.md:32,82`** *(supports: doc says 7 days)*:
```text
| DRAFT | 7 days | sweep_drafts | *(no index — full scan)* |
| sweep_drafts | *(none)* | 7 days | Delete DRAFT ads older than 7 days |
```

#### AD-006: [LOW] — sweep_drafts has no partial index on (status=DRAFT, created_at) → full table scan

| Field | Value |
|---|---|
| **ID** | AD-006 |
| **Title** | sweep_drafts has no partial index on (status=DRAFT, created_at) → full table scan |
| **Severity** | LOW |
| **Category** | Performance |
| **File(s)** | `src/backend/apps/ads/models.py:286-288` (index list); `src/backend/apps/core/management/commands/sweep_drafts.py:47-50`; `docs/02-database/db-retention.md:32` |
| **Status** | Open |
| **Problem** | `sweep_drafts` filters `status=DRAFT AND created_at < cutoff`. The model has no partial index for this; the only DRAFT-touching index `IX_ads_user_status` is on `(user_id, status)` and cannot serve the `created_at` range. `db-retention.md` itself flags this as "(no index — full scan)". Under bot load, the DRAFT population can grow between the 30-minute sweep runs, so each sweep scan grows with usage. |
| **Impact** | Hourly sweep cost scales with the total DRAFT count rather than a tight index seek; at scale this is O(n) per run and competes with foreground ad writes. Bounded today (30-min window keeps DRAFTs few) but degrades as volume grows. |
| **Root Cause** | No partial index was added for the DRAFT sweep predicate, and the doc admits the gap rather than tracking it as remediable. |
| **Recommendation** | Add a partial index `IX_ads_draft_sweep` on `(status, created_at) WHERE status='draft'` (or `created_at` first) so the sweep is an index range scan. Track it as a remediation item, not just a doc caveat. |
| **Effort** | S |
| **Priority** | P2 |

**Evidence — `src/backend/apps/ads/models.py:285-288`** *(supports: no DRAFT+created_at partial index exists)*:
```python
models.Index(
    name="IX_ads_user_status",
    fields=["user_id", "status"],
),
# (next: IX_ads_archive_sweep) — no (status, created_at) WHERE DRAFT index
```

#### AD-007: [LOW] — archive_sweep bypasses the transition_to driver via queryset.update()

| Field | Value |
|---|---|
| **ID** | AD-007 |
| **Title** | archive_sweep bypasses the transition_to driver via queryset.update() |
| **Severity** | LOW |
| **Category** | State-machine integrity |
| **File(s)** | `src/backend/apps/core/management/commands/archive_sweep.py:47,62-65`; `src/backend/apps/ads/models.py:352-398` (`transition_to`) |
| **Status** | Open |
| **Problem** | `archive_sweep` performs `queryset.update(status=AdStatus.ARCHIVED, archived_at=timezone.now())` — a direct status assignment that bypasses `transition_to()`. The phase spec (A2) requires that *all* transitions pass through the driver. The bypass here is currently safe (the queryset is pre-filtered to `status=PUBLISHED`, the matrix allows PUBLISHED→ARCHIVED, and the `ck_ads_archived_at_if_archived` CheckConstraint is satisfied), but it skips `transition_to`'s `refresh_from_db()` stale-row guard, its `ALLOWED_TRANSITIONS` validation, and Django's `auto_now` `updated_at` (bulk `update()` does not bump `updated_at`). |
| **Impact** | No current data corruption (constraints hold), but the bypass sets a precedent: a future change to the sweep filter or the matrix would silently archive rows outside the validated driver. The stale `updated_at` also means sweep-archived rows don't refresh their "last modified" signal used by other tooling. |
| **Root Cause** | The sweep uses a bulk `update()` for throughput rather than per-row `transition_to()`, trading the matrix guard for speed. |
| **Recommendation** | Either (a) document this as an intentional bulk path with an assertion that the filter predicates exactly match the allowed transition (so A2 is audibly satisfied), or (b) route through `transition_to()` per-row inside the advisory lock (accept the throughput cost, which is small given the 60-day window rarely batches many rows). At minimum, include `updated_at=timezone.now()` in the `update()` so the modified-at signal stays accurate. |
| **Effort** | M |
| **Priority** | P2 |

**Evidence — `src/backend/apps/core/management/commands/archive_sweep.py:47,62-65`** *(supports: direct status overwrite via queryset.update, bypassing transition_to)*:
```python
queryset = Ad.objects.filter(
    status=AdStatus.PUBLISHED,
    published_at__lt=cutoff_date,
)
updated_count = queryset.update(
    status=AdStatus.ARCHIVED,
    archived_at=timezone.now(),
)
```

#### AD-008: [LOW] — basedpyright fails on test_priority_service.py:500 (response.headers indexing; django-stubs gap)

| Field | Value |
|---|---|
| **ID** | AD-008 |
| **Title** | basedpyright reports `reportIndexIssue` on moderation test (R7 type-check failure) |
| **Severity** | LOW |
| **Category** | Type safety |
| **File(s)** | `src/backend/apps/moderation/tests/test_priority_service.py:500` |
| **Status** | Open |
| **Problem** | The phase R7 type-check is not clean: `basedpyright src/backend/apps/moderation` (and `apps/ads`) reports one error: `test_priority_service.py:500:16 - error: "__getitem__" method not defined on type "cached_property" (reportIndexIssue)`. The project does not install `django-stubs` (inline comments note this), so `response.headers[...]` cannot be resolved; the project elsewhere suppresses this class of gap with `# pyright: ignore[reportGeneralTypeIssues]`, but this line lacks the suppression. |
| **Impact** | A noisy type-check failure in the moderation test suite; the line itself is correct at runtime (it ran green in `test_unauthenticated_returns_401`), but the failure masks real type regressions and breaks a clean `basedpyright` gate. |
| **Root Cause** | Missing `pyright: ignore` annotation (or `django-stubs`/a TypedDict for `HttpResponseHeaders`) on a Django-API index expression in a test. |
| **Recommendation** | Add `# pyright: ignore[reportIndexIssue]` to line 500 (or install `django-stubs`) so the moderation test suite type-checks cleanly and R7 passes. |
| **Effort** | S |
| **Priority** | P2 |

**Evidence — basedpyright output** *(supports: one type error in the moderation test scope)*:
```text
test_priority_service.py:500:16 - error: "__getitem__" method not defined on type "cached_property" (reportIndexIssue)
1 error, 0 warnings, 0 notes
```

#### AD-009: [MEDIUM] — Bot `/post` creates a DRAFT with no guard against an existing in-progress DRAFT

| Field | Value |
|---|---|
| **ID** | AD-009 |
| **Title** | Bot `/post` creates a DRAFT with no guard against an existing in-progress DRAFT (duplicate/orphan on concurrent restart) |
| **Severity** | MEDIUM |
| **Category** | FSM persistence |
| **File(s)** | `src/telegram_bot/handlers/ad_create.py:77-97, 862-896`; `src/backend/apps/ads/models.py:166-347` (Meta — no uniqueness constraint) |
| **Status** | Open |
| **Problem** | `/post` (`cmd_post`) calls `create_draft_ad` → `Ad.objects.create(user_id, status=DRAFT)` unconditionally; it neither checks for nor cleans up a pre-existing in-progress DRAFT for that user, and there is no DB constraint preventing multiple DRAFT rows per user. If a seller restarts the flow (or double-taps `/post`, or the bot crashes mid-FSM), a second DRAFT is created and the FSM state is overwritten with the new `ad_id` — the old DRAFT row and any already-uploaded photo files it references are orphaned. `/cancel` only cleans the current FSM session's `photos` (from state), so an orphaned prior DRAFT+photos are reclaimed only by the 30-minute `sweep_drafts` and the backstop `sweep_orphaned_media`. |
| **Impact** | Brief existence of duplicate DRAFT rows and orphaned photo files per concurrent/restarted session; under sustained bot load this multiplies orphaned rows/files between sweep cycles, and a user can end up with two half-built DRAFTs. Phase spec B3 ("concurrent post/session cannot duplicate a user's DRAFT") is not satisfied. |
| **Root Cause** | No single-DRAFT-per-user invariant (no partial unique index, no service-level guard) mirrors the FSM session, which is per-chat state in aiogram. |
| **Recommendation** | Before creating a new DRAFT, either resume the existing in-progress DRAFT (re-load it into FSM state) or delete it + its photo files. Add a partial unique index `uq_ads_single_draft_per_user` on `(user_id) WHERE status='draft'` to enforce the invariant at the DB layer, and handle the resulting `IntegrityError` in `create_draft_ad`. |
| **Effort** | M |
| **Priority** | P1 |

**Evidence — `src/telegram_bot/handlers/ad_create.py:77-97`** *(supports: /post creates a new DRAFT without checking an existing one)*:
```python
@router.message(Command("post"))
async def cmd_post(message: types.Message, state: FSMContext) -> None:
    ...
    # Create draft ad
    ad = await create_draft_ad(user_id=data["user_id"])
    await state.set_state(AdCreateForm.category)
    await state.update_data(ad_id=ad.id)   # ← overwrites any prior ad_id; old DRAFT orphaned
```

**Evidence — `src/backend/apps/ads/models.py`** *(supports: no uniqueness guard on a per-user DRAFT; only DRAFT row shown in Meta.constraints/indexes is absent)*:
```python
# Ad.Meta.constraints — only ck_* timestamp constraints; no unique constraint on (user_id, status=DRAFT)
```

#### AD-010: [LOW] — Ads in deactivated categories still appear in keyword search

| Field | Value |
|---|---|
| **ID** | AD-010 |
| **Title** | Ads in deactivated (is_active=False) categories still appear in keyword search |
| **Severity** | LOW |
| **Category** | Search correctness |
| **File(s)** | `src/backend/apps/search/views/search.py:64-68`; `src/backend/apps/categories/models.py:33-36` (help_text) |
| **Status** | Open |
| **Problem** | `Category.is_active` help_text states "Inactive categories hide their ads," but the keyword-search base queryset (`Ad.objects.filter(status=AdStatus.PUBLISHED)`) does not filter `category__is_active=True`. Deactivating a category correctly removes it from navigation (`Category.objects.filter(is_active=True)`) and 404s its category listing page (`search.py:76`, `listings.py:282`), but ads in a deactivated category remain reachable via keyword search (their `search_vector` was built at write time with the old category name and is never cleared). |
| **Impact** | Admin deactivation of a category does not fully remove that category's existing ads from the site — they remain discoverable by keyword, contradicting the field's documented contract. Low frequency (category deactivation is a rare admin action) and no direct PII/security exposure. |
| **Root Cause** | The search/listings base querysets gate on `Ad.status` only, not on the referenced category's `is_active`. |
| **Recommendation** | Add `category__is_active=True` to the search (and listing) base queryset, guarded for ads with `category IS NULL` (or enforce `category_id IS NOT NULL` for PUBLISHED ads via a CheckConstraint so the join is always safe). Until then, document that deactivation only removes navigation, not keyword discovery. |
| **Effort** | S |
| **Priority** | P2 |

**Evidence — `src/backend/apps/search/views/search.py:64-68`** *(supports: base queryset filters only PUBLISHED, not category.is_active)*:
```python
ads = (
    Ad.objects.filter(status=AdStatus.PUBLISHED)
    .select_related("category", "city", "user")
    .prefetch_related("features")
)
```

**Evidence — `src/backend/apps/categories/models.py:33-36`** *(supports: model documents the hiding intent)*:
```python
is_active = models.BooleanField(
    default=True,
    help_text="Inactive categories hide their ads",
)
```

## Cross-Finding Analysis

- **Merge candidates:** AD-004 and AD-005 both stem from `db-retention.md` drift (DRAFT window + ARCHIVED window definition). They are kept separate because AD-004 is a pure doc value and AD-005 adds a code-level timer-basis issue.
- **Conflicting evidence:** None.
- **Dependency chains:** AD-007 (archive_sweep driver bypass) is adjacent to AD-005 (purge timer basis) — both touch the ARCHIVED pipeline, but are independent fixes. AD-003's fix should reuse the `auto_moderate()` wiring already proven by the reactivation tests, so its Effort is bounded.

## Remediation Roadmap

| Order | ID | Severity | Effort | Priority | Recommendation (summary) |
|-------|----|----------|--------|----------|--------------------------|
| 1 | AD-003 | HIGH | M | P0 | Call auto_moderate() in the text-edit branch of ad_edit; republish on pass, re-render with error on fail |
| 2 | AD-009 | MEDIUM | M | P1 | Guard/unique-constrain a single DRAFT per user; resume or clean the prior DRAFT in create_draft_ad |
| 3 | AD-005 | MEDIUM | M | P1 | Reconcile ARCHIVED retention to archived_at (60d) + partial index, or document the publish-anchored 120d design |
| 4 | AD-004 | LOW | S | P2 | Fix db-retention.md DRAFT row to 30 minutes |
| 5 | AD-006 | LOW | S | P2 | Add partial index IX_ads_draft_sweep on (status, created_at) WHERE status='draft' |
| 6 | AD-007 | LOW | M | P2 | Document archive_sweep's deliberate bulk update (or route through transition_to); include updated_at in the update() |
| 7 | AD-008 | LOW | S | P2 | Suppress/fix the basedpyright error at test_priority_service.py:500 |
| 8 | AD-010 | LOW | S | P2 | Exclude inactive-category ads from keyword search/listings (null-safe); enforce category NOT NULL for PUBLISHED |

## Rollout Safety

| ID | Risk | Backward-compatible? | Test gap (must cover) |
|----|------|----------------------|-----------------------|
| AD-003 | Med | No (behavior change: edited ads now auto-republish or re-render with error) | Add a text-edit test asserting auto_moderate IS called and the pass/fail redirect mirrors reactivation (test_edit.py currently only covers reactivation) |
| AD-009 | Med | No (new uniqueness constraint; create_draft_ad must handle IntegrityError/resume) | Concurrent/restart /post test asserting exactly one DRAFT per user survives |
| AD-005 | Low | Partial (doc-only if design is kept as-is; data/index change if basis moves) | Sweep test seeding a manually-archived ad (archived_at recent, published_at old) must be purged by the from-archive window |
| AD-004 | None | Yes | N/A (doc edit) |
| AD-006 | Low | Yes (additive index) | n/a — monitor sweep runtime |
| AD-007 | Low | Yes (additive updated_at) | Verify archive_sweep still sets archived_at and (if added) updated_at |
| AD-008 | None | Yes | Run basedpyright clean |
| AD-010 | Low | Partial (could drop NULL-category published ads) | Test that an ad in an is_active=False category is absent from search; test NULL-category published ads are not dropped |
