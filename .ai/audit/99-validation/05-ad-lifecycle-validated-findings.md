---
# Report metadata — validated per Phase 99.
phase: "05"
phase_name: "Ad Lifecycle, Categories & Moderation"
date: "2026-09-12"
auditor: "Executor (subagent)"
validator: "validator (Phase 99)"
mode: "problems-only"
id_prefix: "AD"
report_status: "validated"  # Phase 99 sets to "validated"
severity_taxonomy: ".kilo/commands/audit/phases/05-audit-ad-lifecycle.md#severity-taxonomy"
---

# Audit Findings (Validated) — Ad Lifecycle, Categories & Moderation

> **Validator's note.** This report is self-contained: every finding below was
> checked against the live source tree (`src/backend/...`, `src/telegram_bot/...`),
> the phase rubric `.kilo/commands/audit/phases/05-audit-ad-lifecycle.md`, the
> retention design doc `docs/02-database/db-retention.md`, and — where the finding
> is a type-checker/runtime claim — a direct tool run (`basedpyright`, `ruff`).
> Each finding carries an inline **Validation** block stating the action taken,
> the validation type (`SPEC-DEVIATION` / `BEST-PRACTICE` / `DOC-UPDATE`), the
> evidence surveyed, and any source-reference drift from the original audit.

## Executive Summary

Eight problems were found across the ad lifecycle, category tree, and moderation gate. The most severe is a **missing re-moderation step on web text-edit**: when a seller edits the title/description of a live published ad, the ad is moved to `ON_MODERATION` but never auto-checked, so it never republishes automatically — published ads silently vanish from the site, and manually approving them publishes edited text without the automated safety checks. Two MEDIUM findings follow: the `ARCHIVED` purge window is measured from `published_at` (not `archived_at`, causing manual archives to outlive the intended window with an inconsistent doc), and the bot creates DRAFT rows with no concurrency/duplicate guard. The remainder are LOW: a stale draft-retention doc value, a full-scan draft sweep, a state-machine bypass in `archive_sweep`, a type-checker failure in a moderation test, and an `is_active` leak in keyword search.

**Validation posture:** all 8 findings are **Validated** (no rejection, no reclassification across types, no merger). The auditor's decision to keep AD-004 and AD-005 separate is confirmed correct (AD-004 is a doc-value drift; AD-005 is a code timer-basis + spec conflict).

> Note on IDs: `AD-001` and `AD-002` are pre-existing reference tags embedded in `apps/ads/models.py:396` (`# manual review of auto-failed ads (AD-001)`) and `docs/02-database/db-retention.md:20` (`purge_deleted_ads` command → `AD-002`); both map to already-implemented behavior confirmed by the test suite, so findings continue from `AD-003`.

## Scope & Methodology

**Scope:** Ad status enum + `transition_to` driver (`apps/ads/models.py`), the bot ad-creation FSM persisted as DRAFT rows (`telegram_bot/handlers/ad_create.py`), the auto-moderation gate (`apps/moderation/services/auto_moderation.py`, `moderation_log.py`, `admin_actions.py`, `views/review.py`, `views/api_bulk.py`), the web edit/reactivate views (`apps/ads/views/edit.py`), the category tree + rename triggers (`apps/categories/models.py`, `signals.py`, `apps/ads/management/commands/setup_search_triggers.py`), the photo-collection entity (`AdImage`), the six retention sweeps (`apps/core/management/commands/*sweep*.py`, `*purge*.py`), and the `db-retention.md` spec.

### Runtime Verification

Each claim below is reproducible. Concrete evidence is captured per finding.

| R# | Check | Method | Result |
|----|-------|--------|--------|
| R-01 | Full transition matrix + side-effects (published_at, original_published_at once-only, archived_at cleared on reactivate, search_vector on text-edit) | `-k lifecycle` (26 passed) + `-k moderation` (207 passed) | PASS (side-effects correct; re-moderation gap surfaced as AD-003) |
| R-02 | Forbidden transitions rejected (DRAFT→PUBLISHED, DELETED terminal, ARCHIVED→REJECTED, bulk PUBLISHED without published_at) | `test_ad_lifecycle.py`, `test_ad_constraints.py`, `test_admin_actions.py` | PASS |
| R-03 | Auto-check is the only gate before PUBLISHED; no DRAFT/ON_MODERATION/ON_MODERATION_FAILED ad in public listings/search | `search.py:65`, `listings.py:269` filter `status=PUBLISHED`; `auto_moderate` only caller of PUBLISH (`moderation_log.set_published`) | PASS (no leak; AD-003 is a re-moderation gap, not a public leak) |
| R-04 | FSM DRAFT cleanup on cancel; 30-min sweep correctness | `cmd_cancel` deletes DRAFT+photos (`ad_create.py:105-119`); `test_deletes_drafts_older_than_30_minutes` | PASS (AD-009 is a duplicate-DRAFT gap, separate) |
| R-05 | Category integrity (no cycle/orphan; rename propagates name + search vector; admin-only) | `test_search_triggers.py` rename + i18n cascade (15 passed) | PASS (D5 satisfied) |
| R-06 | Purge/sweep: correct status+window+lock+cascade+idempotency | `test_sweep_commands.py` (all sweep tests pass; lock IDs asserted: ARCHIVE_SWEEP=1, DELETE_SWEEP=2, SWEEP_DRAFTS=4) | PASS (AD-005 is a retention-basis nuance, not a wrong-status purge) |
| R-07 | Lint + type-checker | `ruff check` **PASS**; `basedpyright src/.../moderation/tests/test_priority_service.py` → **FAIL (1 error, reportIndexIssue)** | TYPECHECK FAIL (→ AD-008) |

> **Validator R-07 note:** R-07 originally cited `test_textedit_does_not_remoderate` as a repro for AD-003. That test is **not committed** to the tree (it does not exist under `src/`) — it was a one-off repro run during the audit. The underlying gap it demonstrates is nevertheless confirmed by direct source inspection (see AD-003 validation). R-07's `ruff check PASS` and `basedpyright` failure were reproduced by the validator (output quoted in AD-008).

**Tools used:** `ruff check` (re-run by validator: `All checks passed!`), `basedpyright` (re-run by validator: 1 error at `test_priority_service.py:500:16`), `grep -rn` (via Grep), `uv run pytest` inside the `mko-bazuna-test` Docker compose (DB healthy on :5433), source inspection of trigger SQL (`setup_search_triggers.py`) and the six sweep commands.

**Assumptions:** PostgreSQL 18; Django 5.2 LTS; `django-stubs` is **not** installed (per inline comments) — confirmed by dependency scan (no `django-stubs`/`django_stubs` in `pyproject.toml` or imports); `basedpyright` config at `pyproject.toml:187-195` suppresses many report codes but **not** `reportIndexIssue`; the bot runs as one process sharing the ORM with the web process; the scheduler runs sweeps hourly; categories are admin-managed via `load_catalog` (no public write endpoint for categories).

## Findings Summary

| ID | Title | Severity | Status | Category | Type (validated) |
|----|-------|----------|--------|----------|-------------------|
| AD-003 | Text-edit of a published ad skips auto-moderation (ad stuck hidden / edited text unmoderated) | HIGH | Open | Correctness | SPEC-DEVIATION |
| AD-005 | ARCHIVED purge measured from published_at, not archived_at (doc/spec retention conflict) | MEDIUM | Open | Data retention | SPEC-DEVIATION |
| AD-009 | Bot `/post` creates a DRAFT with no guard against an existing in-progress DRAFT (duplicate/orphan) | MEDIUM | Open | FSM persistence | SPEC-DEVIATION |
| AD-004 | db-retention.md lists DRAFT retention as 7 days; code enforces 30 minutes | LOW | Open | Documentation | DOC-UPDATE |
| AD-006 | sweep_drafts has no partial index on (status=DRAFT, created_at) → full table scan | LOW | Open | Performance | BEST-PRACTICE |
| AD-007 | archive_sweep bypasses the transition_to driver via queryset.update() | LOW | Open | State-machine integrity | SPEC-DEVIATION |
| AD-008 | basedpyright fails on test_priority_service.py:500 (response.headers indexing; no django-stubs) | LOW | Open | Type safety | BEST-PRACTICE |
| AD-010 | Ads in deactivated (is_active=False) categories still appear in keyword search | LOW | Open | Search correctness | SPEC-DEVIATION |

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

> **Validation:** ✅ **Validated — SPEC-DEVIATION (no change).** Confirmed by direct source inspection: `edit.py:229` calls `ad.transition_to(AdStatus.ON_MODERATION)` in the PUBLISHED+text-edit branch then redirects to the dashboard (`edit.py:244`) with **no** `auto_moderate()` call. Contrast: the reactivation branch routes through `submit_ad`→`auto_moderate` (`edit.py:178-191` / `submission.py:186`), and the standalone reactivation view calls `auto_moderate(ad)` directly (`edit.py:331`). `moderation/signals.py` `post_save` handlers only compute priority (`signals.py:50`) and schedule alerts — **none** auto-moderate. The only production path to PUBLISHED is `moderation_log.set_published`→`Ad.transition_to(PUBLISHED)` (`moderation_log.py:243`), reached solely via `auto_moderate` (grep for `transition_to(AdStatus.PUBLISHED)` confirms no other production caller). Thus text-edited ads land in `ON_MODERATION` and are never auto-republished; a manual approve later publishes edited text without the auto-check gate. Matches zone C2 / check A4 ("text-edit re-hide + re-moderation"). Severity HIGH (published ads vanish from site) is appropriate. **Source-reference drift:** the finding's evidence line refs `edit.py:326-331` now resolve to the standalone `ad_reactivate` view (still calls `auto_moderate` directly) — substantive claim unchanged. The repro test `test_textedit_does_not_remoderate` is **not committed** (audit-only repro).

#### AD-003: [HIGH] — Text-edit of a published ad skips auto-moderation (ad stuck hidden / edited text unmoderated)

| Field | Value |
|---|---|
| **ID** | AD-003 |
| **Title** | Text-edit of a published ad skips auto-moderation (ad stuck hidden / edited text unmoderated) |
| **Severity** | HIGH |
| **Category** | Correctness |
| **File(s)** | `src/backend/apps/ads/views/edit.py:208-230` (text-edit branch); compared with `edit.py:326-331` (reactivate) and `src/backend/apps/ads/services/submission.py:186` |
| **Status** | Open |
| **Type** | SPEC-DEVIATION |
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
        ad.save(
            update_fields=[
                "title",
                "description",
                "price_amount",
                "price_currency",
                "price_normalized_eur",
                "updated_at",
            ]
        )

        # Use transition_to for status change to ON_MODERATION
        ad.transition_to(AdStatus.ON_MODERATION)
        logger.info(f"Ad {ad_id} text edited, moved to ON_MODERATION")
        # ↑ NO auto_moderate() call here (contrast reactivation at edit.py:328-331)
        return redirect("ads:dashboard")
```

**Evidence — contrast: reactivation path calls auto_moderate** *(supports: the sibling reactivation path invokes re-moderation, proving the text-edit branch is the divergence)*:
```python
# edit.py:326-331 (standalone ad_reactivate view)
if ad.status == AdStatus.ARCHIVED:
    # Update status to ON_MODERATION for re-check (transition_to clears archived_at)
    ad.transition_to(AdStatus.ON_MODERATION)

    # Run auto-moderation check
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

> **Validation:** ✅ **Validated — SPEC-DEVIATION (no change).** Confirmed: `delete_sweep.py:47-52` cuts ARCHIVED purge on `published_at__lt=now-120d`; `IX_ads_delete_sweep` (models.py:299-303) is on `(status, published_at)` WHERE ARCHIVED. For auto-archived ads (archive_sweep at 60d-from-publish) this coincidentally yields 2 months-in-ARCHIVED; for manually-archived ads (`ad_archive` view, `edit.py:292-293` → `transition_to(ARCHIVED)` sets `archived_at` at edit.py:449) `published_at` is recent so the row survives ~120 days-from-publish ≈ 4 months-in-ARCHIVED, exceeding the phase spec's "ARCHIVED | 2 months | purge" (`05-audit-ad-lifecycle.md:74`). `db-retention.md:30,79` state "4 months"/"120 days" — contradicting the phase spec. All sibling sweeps key on the terminal status's *own* timestamp (purge_deleted→deleted_at, purge_rejected→rejected_at, purge_failed→moderation_failed_at), making `delete_sweep`'s `published_at` basis the inconsistent outlier. Severity MEDIUM appropriate. **Source-reference drift:** the cited `DELETE_AGE_DAYS = 120` line lives in the Configuration block (`db-retention.md:116`), not 78-82; content is accurate. **Advisory uncovered:** `db-retention.md` "Configuration" env-var table (lines 112-120) lists `DELETE_AGE_DAYS`/`ARCHIVE_AGE_DAYS` etc. as env vars, but every sweep **hardcodes** the day count and reads no env var — a doc-vs-code drift (tangential, not a cross-finding conflict).

#### AD-005: [MEDIUM] — ARCHIVED purge measured from published_at, not archived_at (doc/spec retention conflict)

| Field | Value |
|---|---|
| **ID** | AD-005 |
| **Title** | ARCHIVED purge measured from published_at, not archived_at (doc/spec retention conflict) |
| **Severity** | MEDIUM |
| **Category** | Data retention |
| **File(s)** | `src/backend/apps/core/management/commands/delete_sweep.py:47-52`; `src/backend/apps/ads/models.py:299-303`; `docs/02-database/db-retention.md:30,78-82` |
| **Status** | Open |
| **Type** | SPEC-DEVIATION |
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

**Evidence — phase spec conflict** *(supports: spec defines ARCHIVED retention as 2 months)*:
```text
| ARCHIVED | 2 months | purge |
```

**Related Findings:** AD-004 (both concern db-retention.md accuracy)

> **Validation evidence added:** sibling sweeps correctly anchor on their terminal timestamp — `purge_deleted_ads.py:47` (`deleted_at`), `purge_rejected_ads.py:47` (`rejected_at`), `purge_failed_ads.py:46` (`moderation_failed_at`), `archive_sweep.py:45-49` (`published_at` is correct here, since it archieves *published* ads by age). `delete_sweep` is the sole outlier. `Ad.transition_to(ARCHIVED)` (models.py:448-450) sets `archived_at`, so a from-archive rewrite has a populated column to rely on (manual archive via `ad_archive` view reaches the same branch).

### LOW

> **Validation:** ✅ **Validated — DOC-UPDATE (no change).** Confirmed: `sweep_drafts.py:45` hardcodes `timedelta(minutes=30)`; `db-retention.md:32` and `:82` state "7 days" with no env var; phase spec `05-audit-ad-lifecycle.md:73` defines DRAFT retention as "30 minutes". The doc contradicts both the implementation and the spec. The `sweep_drafts` lock is `AdvisoryLockId.SWEEP_DRAFTS = 4` (`enums.py:29`), which the recommendation correctly references. Code is correct; doc is outdated. Severity LOW appropriate.

#### AD-004: [LOW] — db-retention.md lists DRAFT retention as 7 days; code enforces 30 minutes

| Field | Value |
|---|---|
| **ID** | AD-004 |
| **Title** | db-retention.md lists DRAFT retention as 7 days; code enforces 30 minutes |
| **Severity** | LOW |
| **Category** | Documentation |
| **File(s)** | `src/backend/apps/core/management/commands/sweep_drafts.py:45`; `docs/02-database/db-retention.md:32,82`; `src/backend/apps/core/tests/test_sweep_commands.py:206` |
| **Status** | Open |
| **Type** | DOC-UPDATE |
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

> **Validation evidence added:** the phase spec retention table (`05-audit-ad-lifecycle.md:73`) states `| DRAFT | 30 minutes | purge |`, confirming the code is correct and the doc is the outlier. The committed test `test_deletes_drafts_older_than_30_minutes` (test_sweep_commands.py:206) codifies 30 minutes, matching code.

#### AD-006: [LOW] — sweep_drafts has no partial index on (status=DRAFT, created_at) → full table scan

| Field | Value |
|---|---|
| **ID** | AD-006 |
| **Title** | sweep_drafts has no partial index on (status=DRAFT, created_at) → full table scan |
| **Severity** | LOW |
| **Category** | Performance |
| **File(s)** | `src/backend/apps/ads/models.py:286-288` (index list); `src/backend/apps/core/management/commands/sweep_drafts.py:47-50`; `docs/02-database/db-retention.md:32` |
| **Status** | Open |
| **Type** | BEST-PRACTICE |
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

> **Validation evidence added:** the Ad index list (models.py:256-319) was reviewed in full — indexes present are `IX_ads_search_gin*`, `IX_ads_pub_listing`, `IX_ads_pub_purpose`, `IX_ads_user_status`, `IX_ads_price_normalized_eur`, `IX_ads_archive_sweep` (status, published_at / PUBLISHED), `IX_ads_delete_sweep` (status, published_at / ARCHIVED), `IX_ads_purge_failed`, `IX_ads_rejected_sweep`, `IX_ads_purge_deleted`. **No** `(status, created_at) WHERE DRAFT` index exists. The `IX_ads_archive_sweep` partial index is on `published_at`, not `created_at`, and is scoped to PUBLISHED — useless to the DRAFT sweep. Recommendation (additive partial index, S effort) is not overengineering; accepted.

#### AD-007: [LOW] — archive_sweep bypasses the transition_to driver via queryset.update()

| Field | Value |
|---|---|
| **ID** | AD-007 |
| **Title** | archive_sweep bypasses the transition_to driver via queryset.update() |
| **Severity** | LOW |
| **Category** | State-machine integrity |
| **File(s)** | `src/backend/apps/core/management/commands/archive_sweep.py:47,62-65`; `src/backend/apps/ads/models.py:352-398` (`transition_to`) |
| **Status** | Open |
| **Type** | SPEC-DEVIATION |
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

> **Validation evidence added:** `Ad.transition_to` (models.py:352-485) enforces `ALLOWED_TRANSITIONS` (PUBLISHED→{ARCHIVED, ON_MODERATION}) and sets `archived_at` for the ARCHIVED target (models.py:448-450) — which the bulk path replicates manually. `Ad.Meta.constraints` (models.py:325-328) `ck_ads_archived_at_if_archived` (`~Q(ARCHIVED) | Q(archived_at__isnull=False)`) holds because the update sets `archived_at`. The phase spec's severity taxonomy (`05-audit-ad-lifecycle.md:217`) explicitly lists "direct status overwrite bypassing the driver" as a CRITICAL-level pattern — here the outcome is correct, so the LOW impact rating is justifiable, but the *mechanism* still violates the A2 check. Classification as SPEC-DEVIATION is correct; the documented-intentional-bulk-path option is an acceptable remediation. The minimal fix (include `updated_at=timezone.now()` in the update) is safe and recommended regardless.

#### AD-008: [LOW] — basedpyright fails on test_priority_service.py:500 (response.headers indexing; django-stubs gap)

| Field | Value |
|---|---|
| **ID** | AD-008 |
| **Title** | basedpyright reports `reportIndexIssue` on moderation test (R7 type-check failure) |
| **Severity** | LOW |
| **Category** | Type safety |
| **File(s)** | `src/backend/apps/moderation/tests/test_priority_service.py:500` |
| **Status** | Open |
| **Type** | BEST-PRACTICE |
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

> **Validation evidence added:** Re-ran `uv run basedpyright src/backend/apps/moderation/tests/test_priority_service.py` — output is **identical** to the finding: `test_priority_service.py:500:16 - error: "__getitem__" method not defined on type "cached_property" (reportIndexIssue)` / `1 error, 0 warnings, 0 notes`. Line 500 (`assert response.headers["WWW-Authenticate"] == "Bearer"`) has no `pyright: ignore` (confirmed by grep — the codebase uses `# pyright: ignore[reportGeneralTypeIssues]` on 24 Django `transaction.atomic()` sites, but `reportIndexIssue` is a distinct code and is **not** suppressed anywhere). `pyproject.toml:187-195` confirms `typeCheckingMode = "standard"` with `reportMissingTypeStubs = "none"` (so the *absence* of django-stubs is intentional and silent; the residual is the `headers` index expression). Fix is trivial, low-risk, restores a clean R7 gate. Not overengineering.

#### AD-009: [MEDIUM] — Bot `/post` creates a DRAFT with no guard against an existing in-progress DRAFT

| Field | Value |
|---|---|
| **ID** | AD-009 |
| **Title** | Bot `/post` creates a DRAFT with no guard against an existing in-progress DRAFT (duplicate/orphan on concurrent restart) |
| **Severity** | MEDIUM |
| **Category** | FSM persistence |
| **File(s)** | `src/telegram_bot/handlers/ad_create.py:77-97, 862-896`; `src/backend/apps/ads/models.py:166-347` (Meta — no uniqueness constraint) |
| **Status** | Open |
| **Type** | SPEC-DEVIATION |
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
# Confirmed: the only UniqueConstraint in the Ad model is none; the single
# UniqueConstraint in the file is uq_user_ad_favorite on AdFavorite (models.py:753).
```

> **Validation evidence added:** `create_draft_ad` (ad_create.py:862-896) does `Ad.objects.create(user_id=user_id, status=AdStatus.DRAFT)` with no existence check. `cmd_cancel` (ad_create.py:105-123) only deletes the `ad_id` held in the *current* FSM state — an orphaned prior DRAFT is not cleaned. `Ad.Meta` (models.py:320-347) constraints are all timestamp `CheckConstraint`s; grep for `UniqueConstraint`/`unique_together` in models.py returns only `unique_together=[("ad","feature")]` on `AdFeature` (712) and `uq_user_ad_favorite` on `AdFavorite` (753) — **no** per-user DRAFT uniqueness. `cmd_post` unconditionally overwrites `ad_id` in state (ad_create.py:97), confirming the orphan mechanism. Violates phase-spec B3. Severity MEDIUM appropriate.

#### AD-010: [LOW] — Ads in deactivated (is_active=False) categories still appear in keyword search

| Field | Value |
|---|---|
| **ID** | AD-010 |
| **Title** | Ads in deactivated (is_active=False) categories still appear in keyword search |
| **Severity** | LOW |
| **Category** | Search correctness |
| **File(s)** | `src/backend/apps/search/views/search.py:64-68`; `src/backend/apps/categories/models.py:33-36` (help_text) |
| **Status** | Open |
| **Type** | SPEC-DEVIATION |
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

> **Validation evidence added:** `search.py:64-68` confirmed: base queryset is `status=AdStatus.PUBLISHED` only — no `category__is_active` filter. `listings.py:268-272` is identically gated (`status=AdStatus.PUBLISHED` only). FTS keyword search (search.py:208-211) annotates rank and filters on the per-language `search_vector` of PUBLISHED ads — an ad whose category was deactivated after publish still matches its existing vector and is surfaced. `categories/models.py:33-36` confirms the "Inactive categories hide their ads" contract (phase spec D4: "is_active correctly hides/shows"). **Minor source-reference drift:** the finding's supporting claim that a deactivated category "404s its listing page" is inaccurate — `search.py:76` / `listings.py:282` do `Category.objects.get(slug=..., is_active=True)` which raises `DoesNotExist` and falls to a "did-you-mean/suggested" path, not an HTTP 404. The core leak (keyword search) is unaffected and remains valid. Recommendation stands; the null-category guard note is appropriate given `Ad.category` is nullable (models.py:112-119).

## Cross-Finding Analysis

- **Merge candidates:** AD-004 and AD-005 both stem from `db-retention.md` drift (DRAFT window + ARCHIVED window definition). Kept separate: AD-004 is a pure doc-value error (7 days vs 30 min) → DOC-UPDATE; AD-005 is a code timer-basis issue (published_at vs archived_at) + a doc/spec (4 vs 2 month) conflict → SPEC-DEVIATION. The auditor's separation is **confirmed correct** — merging would conflate a doc fix with a code/index change.
- **Conflicting evidence:** None within this phase. The db-retention.md env-var table (Configuration section) claims retention is env-driven, but all sweeps hardcode day counts — this is a doc-vs-code drift, not a cross-finding contradiction (no other finding relies on env-driven retention).
- **Dependency chains:**
  - AD-007 (archive_sweep bypass) and AD-005 (delete_sweep purge basis) both touch the ARCHIVED pipeline but are **independent fixes**: archive_sweep *writes* ARCHIVED rows; delete_sweep *reads* them.
  - AD-003's fix reuses the `auto_moderate()` wiring already proven by the reactivation tests (`test_edit.py`), so its Effort is bounded and it has **no dependency** on other findings.
  - AD-009 (add single-DRAFT-per-user constraint) has an internal ordering dependency documented under Rollout (data de-dup before constraint).
- **Validator-addressed conflicts:** none.

## Remediation Roadmap

| Order | ID | Severity | Effort | Priority | Type | Recommendation (summary) |
|-------|----|----------|--------|----------|------|--------------------------|
| 1 | AD-003 | HIGH | M | P0 | SPEC-DEVIATION | Call auto_moderate() in the text-edit branch of ad_edit; republish on pass, re-render with error on fail |
| 2 | AD-009 | MEDIUM | M | P1 | SPEC-DEVIATION | Guard/unique-constrain a single DRAFT per user; resume or clean the prior DRAFT in create_draft_ad |
| 3 | AD-005 | MEDIUM | M | P1 | SPEC-DEVIATION | Reconcile ARCHIVED retention to archived_at (60d) + partial index, or document the publish-anchored 120d design |
| 4 | AD-004 | LOW | S | P2 | DOC-UPDATE | Fix db-retention.md DRAFT row to 30 minutes |
| 5 | AD-006 | LOW | S | P2 | BEST-PRACTICE | Add partial index IX_ads_draft_sweep on (status, created_at) WHERE status='draft' |
| 6 | AD-007 | LOW | M | P2 | SPEC-DEVIATION | Document archive_sweep's deliberate bulk update (or route through transition_to); include updated_at in the update() |
| 7 | AD-008 | LOW | S | P2 | BEST-PRACTICE | Suppress/fix the basedpyright error at test_priority_service.py:500 |
| 8 | AD-010 | LOW | S | P2 | SPEC-DEVIATION | Exclude inactive-category ads from keyword search/listings (null-safe); enforce category NOT NULL for PUBLISHED |

## Rollout Safety

| ID | Risk | Backward-compatible? | Test gap (must cover) | Validated? |
|----|------|----------------------|-----------------------|------------|
| AD-003 | Med | No (behavior change: edited ads now auto-republish or re-render with error) | Add a text-edit test asserting auto_moderate IS called and the pass/fail redirect mirrors reactivation (test_edit.py currently only covers reactivation) | ✅ |
| AD-009 | Med | No (new uniqueness constraint; create_draft_ad must handle IntegrityError/resume) | Concurrent/restart /post test asserting exactly one DRAFT per user survives | ✅ |
| AD-005 | Low | Partial (doc-only if design is kept as-is; data/index change if basis moves) | Sweep test seeding a manually-archived ad (archived_at recent, published_at old) must be purged by the from-archive window | ✅ |
| AD-004 | None | Yes | N/A (doc edit) | ✅ |
| AD-006 | Low | Yes (additive index) | n/a — monitor sweep runtime | ✅ |
| AD-007 | Low | Yes (additive updated_at) | Verify archive_sweep still sets archived_at and (if added) updated_at | ✅ |
| AD-008 | None | Yes | Run basedpyright clean | ✅ |
| AD-009† | Med | No | **Migration must de-dup existing per-user DRAFTs before adding the partial unique index, else PostgreSQL CREATE CONSTRAINT fails** | ✅ (validator-flag) |

† AD-009 rollout risk elevated by migration sequencing, not by the finding's recommendation.

**Rollout safety issues detected (validator-added):**
1. **AD-009 migration sequencing (critical rollout gate):** A partial unique index on `(user_id) WHERE status='draft'` will **fail to create** if any user already has ≥2 DRAFT rows (PostgreSQL enforces uniqueness on creation). Rollout must run a data-cleanup migration *first* (resume the newest DRAFT into FSM state, delete the orphan + its image files), then add the constraint. Without this, the migration blocks in production.
2. **AD-005 test codifies published_at basis:** `TestDeleteSweep` (test_sweep_commands.py:111-130) seeds ARCHIVED ads with `published_at@200d` and **no** `archived_at`. If the code moves to an `archived_at` basis, these tests must set `archived_at` — otherwise the rows won't be purged and the tests would falsely pass only because `archived_at` is NULL (and `NULL < cutoff` is never true). The rollout-safe replacement test must seed `archived_at@200d` with a recent `published_at`.
3. **AD-003 behavior change:** text-edit currently always redirects to dashboard (ad siloed in ON_MODERATION). Post-fix, a failing edit re-renders `edit.html` with an error and leaves the ad in ON_MODERATION_FAILED (via `_fail_moderation`). This changes the visible outcome for sellers whose edited text fails checks — communicate in release notes.

**Circular / hidden dependencies:** None. AD-003, AD-005, AD-009 are independent. AD-007 and AD-005 share the ARCHIVED pipeline but touch disjoint operations (write vs read). No fragile insertion points beyond the migration sequencing noted above.

## Execution Validation

- **Targets still exist:** All cited files and line ranges are present and unchanged from the audit: `edit.py:208-244`/`299-335`, `submission.py:186`, `moderation_log.py:243`, `moderation/signals.py` (priority+alerts only), `delete_sweep.py:47-52`, `archive_sweep.py:47-65`, `sweep_drafts.py:45-50`, `db-retention.md:30/32/79/116`, `categories/models.py:33-36`, `search.py:64-68`, `listings.py:268-272`, `ad_create.py:77-97`/`862-896`, `models.py:285-347`/`352-398`, `test_priority_service.py:500`. ✅
- **Dependencies remain valid:** `AdStatus` enum (`enums.py:47-55`) values unchanged; `auto_moderate`/`set_published` signatures unchanged; `archive_sweep` still uses `AdvisoryLockId.ARCHIVE_SWEEP`; `delete_sweep` still `AdvisoryLockId.DELETE_SWEEP`; `sweep_drafts` still `AdvisoryLockId.SWEEP_DRAFTS`. ✅
- **Plan is current:** This validation targets the Phase 99 validate task and the `findings.md` produced by the Phase 05 audit; no architectural drift observed between audit and validation. ✅
- **Assumption checks:** `django-stubs` absence re-confirmed (no dependency, no imports); `basedpyright` failure reproduced verbatim; `ruff check` passes on all cited paths. ✅

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 8 | AD-003, AD-004, AD-005, AD-006, AD-007, AD-008, AD-009, AD-010 |
| Reclassified | 0 | — |
| Merged | 0 | — |
| Rejected | 0 | — |

### Rejected Findings

_None._ All eight findings were verified against the live source tree, the phase spec, and (for the type-check/runtime claims) a direct tool re-run. Every finding remains applicable.

### Merged Findings

_None._ AD-004 and AD-005 share the `db-retention.md` root cause but are correctly kept separate by the auditor: AD-004 is a doc-value drift (DRAFT 7d→30min), AD-005 is a code timer-basis issue (published_at vs archived_at) plus a spec-vs-doc contradiction (ARCHIVED 4 vs 2 months). Merging would conflate a DOC-UPDATE with a SPEC-DEVIATION and a doc+code+index change.

| Original ID | Would merge into | Rationale for *not* merging |
|-------------|------------------|-----------------------------|
| AD-004 | AD-005 | AD-004 is doc-only (30 min vs 7 days); AD-005 is code/index + spec conflict. Distinct fix owners, distinct types (DOC-UPDATE vs SPEC-DEVIATION). |

### Reclassified Findings

_None._ The auditor's Categories map cleanly to validation Types; no Type reclassification was warranted:

| ID | Category | Assigned Type | Rationale |
|----|----------|---------------|-----------|
| AD-003 | Correctness | SPEC-DEVIATION | Violates zone C2 / check A4 (text-edit must re-moderate) |
| AD-005 | Data retention | SPEC-DEVIATION | Violates phase-spec 2-month ARCHIVED (manual-archive case) + doc/spec conflict |
| AD-009 | FSM persistence | SPEC-DEVIATION | Violates phase-spec B3 (single DRAFT per user) |
| AD-004 | Documentation | DOC-UPDATE | Code correct; doc says 7 days vs code/spec 30 min |
| AD-006 | Performance | BEST-PRACTICE | Additive index; no spec text violated |
| AD-007 | State-machine integrity | SPEC-DEVIATION | Violates phase-spec A2 (no direct status overwrite bypassing driver) |
| AD-008 | Type safety | BEST-PRACTICE | Tooling-hygiene / type-gate; no product spec violated |
| AD-010 | Search correctness | SPEC-DEVIATION | Violates phase-spec D4 / `is_active` help-text contract |

## Rollout Analysis (validator-added)

- **Sequencing:** AD-009 constraint must be preceded by its data-dedup migration; AD-003 (P0) is independent and should ship first; AD-005 and AD-007 are independent ARCHIVED-pipeline touches and may ship together or separately.
- **Backward compatibility:** AD-003 and AD-009 are behavior/schema changes (non-backward-compatible — see Rollout Safety table); AD-004/AD-006/AD-008 are additive/doc-only (backward-compatible).
- **Rollback feasibility:** AD-003 (code change) and AD-009 (constraint + migration) require migration rollback scripts; the constraint should be dropped only after confirming no orphaned DRAFTs depend on the new resume path. AD-005's index change is trivially reversible.
- **Migration safety:** AD-009's partial unique index requires a pre-deployment data migration (see risk #1). AD-005's index rewrite on `IX_ads_delete_sweep` should use `CONCURRENTLY`/offline index swap to avoid lock on a large ARCHIVED partial.
- **Test isolation:** AD-005 and AD-009 fixes both require updating `test_sweep_commands.py` (TestDeleteSweep, TestSweepDrafts) and bot FSM tests respectively; ensure `--reuse-db` does not mask the schema change (use `--create-db` for the first run after migration).

## Warnings

- **AD-003 (P0):** the only finding that makes published ads silently vanish from the public site (silenced in ON_MODERATION indefinitely). Highest-priority remediation.
- **AD-009 migration sequencing:** a naive `migrations.AlterField`/index addition will fail in production if duplicate DRAFTs exist per user. This is the single highest rollout risk across all findings.
- **db-retention.md Configuration drift:** the env-var table (lines 112-120) advertises `DELETE_AGE_DAYS`, `ARCHIVE_AGE_DAYS`, etc., but no sweep reads any env var — all six hardcode their day counts. This misleads operators during incident response and should be reconciled (doc the hardcode, or implement env-driven values) — filed as an advisory, not a new finding (out of Phase 05 scope).
- **AD-010 supporting detail:** the finding's claim that a deactivated category "404s its listing page" is inaccurate (it falls to a did-you-mean path). Does not affect the core finding.
- **Staleness of AD-003 repro test:** `test_textedit_does_not_remoderate` is not in the committed tree — the gap it demonstrates is real (confirmed by inspection) but is not currently regression-guarded. Commit a regression test as part of the fix.

## Required Fixes

1. **AD-003 (P0, SPEC-DEVIATION):** Wire `auto_moderate(ad)` into the text-edit branch of `ad_edit` (edit.py) after `transition_to(ON_MODERATION)`; on pass redirect to dashboard, on fail re-render `edit.html` with the error (mirror reactivation). Add a committed regression test asserting `auto_moderate` is called and pass/fail redirects differ (replace the audit-only repro).
2. **AD-009 (P1, SPEC-DEVIATION):** Enforce single-DRAFT-per-user. In `create_draft_ad` (ad_create.py), resume-or-delete any existing in-progress DRAFT (and its orphan photos) before creating a new one. Add a data migration to de-dup pre-existing per-user DRAFTs, then add the partial unique index `uq_ads_single_draft_per_user` on `(user_id) WHERE status='draft'`; handle `IntegrityError`.
3. **AD-005 (P1, SPEC-DEVIATION):** Reconcile ARCHIVED retention to the phase spec (2 months in ARCHIVED). Change `delete_sweep` to filter on `archived_at < now-60d` and relocate `IX_ads_delete_sweep` to `(status, archived_at)` WHERE ARCHIVED; update `db-retention.md` to "2 months from `archived_at`". Update `TestDeleteSweep` to set `archived_at`.

## Advisory Recommendations

- **AD-004 (DOC-UPDATE, P2):** Update `db-retention.md` lines 32 and 82 to "30 minutes" + advisory-lock-4 note.
- **AD-006 (BEST-PRACTICE, P2):** Add partial index `IX_ads_draft_sweep (status, created_at) WHERE status='draft'`.
- **AD-007 (SPEC-DEVIATION, P2):** At minimum include `updated_at=timezone.now()` in `archive_sweep`'s `update()`; document the deliberate bulk path with an assertion that the PUBLISHED filter matches the allowed PUBLISHED→ARCHIVED transition (audibly satisfies A2).
- **AD-008 (BEST-PRACTICE, P2):** Add `# pyright: ignore[reportIndexIssue]` at `test_priority_service.py:500` to restore a clean R7 type-check gate.
- **AD-010 (SPEC-DEVIATION, P2):** Add `category__is_active=True` to the search and listings base querysets (null-safe via `Q(category__isnull=True) | Q(category__is_active=True)`), and add a `CheckConstraint` forbidding `PUBLISHED` ads with a `NULL` category so the join is always safe.
- **db-retention.md Configuration:** Either implement env-driven retention (read `ARCHIVE_AGE_DAYS`/`DELETE_AGE_DAYS` etc.) or replace the env-var table with the actual hardcoded values to prevent operator confusion.

---

*Validation performed by the Phase 99 validator against the live source tree, the Phase 05 rubric, and direct `basedpyright`/`ruff` re-runs. No source code was modified.*
