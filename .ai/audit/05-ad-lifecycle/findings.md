---
# Report metadata — fill once per phase report.
phase: "05"
phase_name: "ad-lifecycle"
date: "2026-09-28"
auditor: "Executor (subagent)"
validator: ""  # Phase 99 only — omit/blank for raw phase findings
mode: "problems-only"
# Correct prefix per phase: 01-ENT, 02-CFG, 03-DB, 04-AUT, 05-AD, 06-PII, 07-MED, 08-SRH, 09-EXT, 10-QLT, 11-TST, 12-OPS, 13-PERF, 14-I18N
id_prefix: "AD"
# report_status = lifecycle of the report document (draft → validated)
# per-finding Status (in Findings Summary + field table below) = lifecycle of the individual finding (Open → Validated/Rejected/Merged/Reclassified/Deferred)
report_status: "draft"  # "draft" for raw phases; Phase 99 sets to "validated"
severity_taxonomy: ".kilo/commands/audit/phases/05-audit-ad-lifecycle.md#severity-taxonomy"  # pointer to phase rubric, NOT hardcoded
---

# Audit Findings — Ad Lifecycle, Categories & Moderation

## Executive Summary

15 problems were found in the ad lifecycle: 1 critical, 4 high, 7 medium, 3 low. The single
critical problem is that any staff member with admin-site access can publish an advertisement
that has never passed the mandatory review check, simply by changing a dropdown on the ad's
admin page — content that the business believes is gated can therefore reach the public
marketplace unreviewed, and nothing in the system records that it happened.

The high-severity problems are all about seller-visible correctness rather than security: a
seller who corrects an ad that was rejected by the automatic check gets no response at all and
watches it disappear; duplicating an ad makes both ads share the same photo files, so deleting
one permanently breaks the other; archiving an ad by hand destroys it two months later even
though the published rules promise four; and two users pressing "post" at the same moment can
break the creation dialog. Business impact is loss of seller trust and unrecoverable loss of
seller content; the underlying design (state machine, retention sweeps, review gate) is
otherwise sound and all existing automated tests pass.

## Scope & Methodology

**Scope:** The `Ad` aggregate and its `AdStatus` state machine (`Ad.transition_to`), the
`AdStatus`/lifecycle timestamp contract and its DB check constraints, the bot ad-creation FSM
and its durable `DRAFT` persistence, the automatic review gate (`apps/moderation`), the
category tree and its rename→search-vector propagation, the 1–5 photo collection
(`AdImage` / `AdImageService`), and all eight retention sweeps (`sweep_drafts`,
`archive_sweep`, `delete_sweep`, `purge_failed_ads`, `purge_rejected_ads`,
`purge_deleted_ads`, `consent_hard_delete`, plus the consent soft-delete path).

### Runtime Verification

Each claim in a finding must be reproducible. Record the verification checks below.

| R# | Check | Method | Result |
|----|-------|--------|--------|
| R-01 | Every legal transition sets the correct lifecycle timestamps (`published_at`, `original_published_at`, `archived_at`, `rejected_at`, `moderation_failed_at`, `deleted_at`) | Scripted walk of `DRAFT→ON_MODERATION→PUBLISHED→ARCHIVED→PUBLISHED→ARCHIVED→ON_MODERATION` and `ON_MODERATION→ON_MODERATION_FAILED→REJECTED` against a live PostgreSQL 18 scratch DB (`.ai/tmp` probe A) | PASS |
| R-02 | `published_at` resets on every `PUBLISHED` transition; `original_published_at` set once and immutable | Probe A, with 1.1 s sleeps between transitions | PASS |
| R-03 | Forbidden transitions are rejected (`DRAFT→PUBLISHED`, `DRAFT→ARCHIVED`, `ON_MODERATION_FAILED→PUBLISHED`, `ON_MODERATION_FAILED→ON_MODERATION`, `REJECTED→PUBLISHED`, `REJECTED→ON_MODERATION`, `PUBLISHED→REJECTED`, `DELETED→PUBLISHED`, `DELETED→ARCHIVED`) | 9-case table driven against `transition_to`; all raised `ValueError` | PASS |
| R-04 | No non-`PUBLISHED` ad (`ON_MODERATION`, `ON_MODERATION_FAILED`, `REJECTED`, `ARCHIVED`) appears in the public listing queryset | `ListingsQuery.build_queryset(ListingsQueryParams())` — the single service used by both `ads.views.listings` and `search.views.search` | PASS |
| R-05 | `DRAFT` is the only `ON_MODERATION`-capable transient; the moderation gate is the only writer of `PUBLISHED` | `grep` of all 20 `transition_to(` call sites: `PUBLISHED` is written only from `moderation_log.set_published`, reached only via `auto_moderate._pass_moderation` | PASS |
| R-06 | Non-staff cannot reach any moderation action | `Client.force_login(seller)` → `/admin/moderation/queue/`, `/admin/moderation/review/<id>/`, POST `/admin/ads/ad/<id>/change/` all returned `302` | PASS |
| R-07 | Category rename propagates to `Ad.category_name` **and** recomputes all four search vectors | Renamed a leaf category; ad's `category_name` became `ZzzRenamedProbeCat`, `search_vector` contained the new token and no longer the old one | PASS |
| R-08 | Category tree invariants: self-parent / cycle rejected; `is_active=False` removes ads from listings | `parent = self` → `mptt.exceptions.InvalidMove`; inactive-category ad absent from `ListingsQuery` | PASS |
| R-09 | Photo count gate: 0 photos and 6 photos fail moderation, 5 photos publish | `auto_moderate` on 0/6/5-photo ads → `False/False/True` | PASS |
| R-10 | Photo ordering preserved; `AdImage` FK integrity | 6 rows stored with `position` `[0..5]`; `Meta.ordering = ["position"]` | PASS |
| R-11 | Every sweep deletes **only** its own status at its retention boundary; active rows survive; AdImage rows CASCADE | `sweep_drafts` 29 m/31 m, `archive_sweep` 59 d/61 d, `delete_sweep` 61 d, `purge_failed_ads` 6 d/8 d, `purge_rejected_ads` 89 d/91 d, `purge_deleted_ads` 119 d/121 d — every boundary behaved as documented, and `Pub59`/`Failed6`/`Rej89`/`Del119` all survived the full sweep battery | PASS |
| R-12 | Sweeps are idempotent (second run is a no-op) | `sweep_drafts` and every purge run twice | PASS |
| R-13 | Consent withdrawal soft-deletes every ad of the seller and sets `deleted_at` | `withdraw_consent(user)` → all ads `deleted`, all `deleted_at` populated | PASS |
| R-14 | Text-edit on a `PUBLISHED` ad re-hides, re-moderates and recomputes the search vector | POST edit → status left `PUBLISHED`, vector gained the new token, lost the old one, 1 new `ModeratorActionLog` row | PASS |
| R-15 | **Django admin change form cannot set `status`/lifecycle timestamps directly** | POST `/admin/ads/ad/<id>/change/` with `status=published` + hand-picked `published_at`/`original_published_at` | **FAIL → AD-001** |
| R-16 | **`ON_MODERATION` is a durable state** (pending-queue semantics) | After a full `submit_ad`, `Ad.objects.filter(status=ON_MODERATION).count() == 0`; `get_pending_queue_size() == 0` | **FAIL → AD-008** |
| R-17 | **Editing an `ON_MODERATION_FAILED` ad resubmits it and resets its purge timer** | POST edit on a failed ad | **FAIL → AD-002** |
| R-18 | **A copied ad owns its own photo files** | `copy_ad` then hard-delete the source ad | **FAIL → AD-003** |
| R-19 | **Manual archive is hard-deleted on the same 2-month-from-`published_at` clock as auto-archive** | Archive a freshly published ad, back-date `archived_at` by 61 d, run `delete_sweep` | **FAIL → AD-004** |
| R-20 | **`create_draft_ad` survives a concurrent-insert `IntegrityError`** | Real unique-index violation inside `transaction.atomic()` followed by the code's own retry sequence | **FAIL → AD-005** |
| R-21 | **`copy_ad` is safe while a dialog is already open** | `copy_ad` with an open `DRAFT` | **FAIL → AD-012** |
| R-22 | **A duplicated photo cannot silently strip photos from a different ad** | `AdImageService.create_or_skip` on a second ad of the same seller | **FAIL → AD-006** |
| R-23 | **An in-progress dialog is not purged by the 30-minute draft sweep** | Draft age is measured from `created_at`, not last activity | **FAIL → AD-007** |
| R-24 | **A price-only edit restarts the auto-archive clock** | POST price-only edit, compare `published_at` | **FAIL → AD-009** |
| R-25 | Static analysis clean | `uv run ruff check` over `apps/ads`, `apps/moderation`, `apps/categories`, `core/management/commands`, `telegram_bot` | PASS |
| R-26 | Type check clean | `uv run basedpyright` over the same scope | FAIL (4 pre-existing errors, all in `apps/moderation/tests/test_admin_actions.py`, all `reportGeneralTypeIssues` on the untyped `advisory_lock` context manager — test-only, not production) |
| R-27 | Existing lifecycle/moderation/category/photo test suite green | `pytest -n 0` on 26 scoped files: 82 + 232 + 75 tests | PASS |
| R-28 | Bulk-moderation endpoint rejects a non-modifiable ad cleanly and without error-level noise | POST `{"action":"reject"}` for an `ARCHIVED` ad | **FAIL → AD-010** |
| R-29 | `ARCHIVED → PUBLISHED` clears `archived_at` | Archive then reactivate, print `archived_at` | **FAIL → AD-011** (the surrounding R-01 walk otherwise passes) |
| R-30 | `AdImage.(ad, position)` is unique and positions are contiguous | `AdImage._meta` introspection: `unique_together == ()`, no count constraint | **FAIL → AD-014** |
| R-31 | Flipping only `ads_auto_publish=False` hides the seller's live ads | `ListingsQuery.build_queryset` filters `user__is_declined=False` only; `ads_auto_publish` is never consulted | **FAIL → AD-015** |
| R-32 | The transition matrix is reachable/testable as a named constant | `ALLOWED_TRANSITIONS` is a local variable inside `Ad.transition_to`; not importable | **FAIL → AD-013** |

**Tools used:** `grep`/`glob` (source discovery), `docker compose run … test python manage.py shell`
(six throwaway probe scripts against an isolated `audit05_probe` PostgreSQL database, dropped
afterwards), Django test `Client`, `ruff`, `basedpyright`, `pytest` via the
`mko-bazuna-test` compose project.

**Assumptions:** PostgreSQL 18 as shipped in `postgres:18-alpine`; CPython 3.14 (so PEP 758
`except A, B:` syntax in `apps/categories/signals.py:67` is valid and is **not** reported as a
defect); production `config.settings.prod` behaves like `config.settings.test` for lifecycle
behaviour (same ORM, same triggers — the probe DB was bootstrapped with
`migrate --run-syncdb` + `setup_search_triggers` + `load_exchange_rates` + `load_catalog`,
mirroring `bootstrap_reference_data`); the `mko-bazuna-dev` stack was **not** used (it is
crash-looping on a placeholder `BOT_TOKEN` — see CFG-001) and no live dev data was touched.

**Isolation note:** all runtime work ran in a dedicated `audit05_probe` database inside the
`mko-bazuna-test` PostgreSQL container so that the other parallel auditors' `test_mko_bazuna_gw*`
databases and the `mko-bazuna-test` web container were not disturbed. No repository file was
created or modified; probe scripts were written to `.ai/tmp/` and deleted.

---

## Findings Summary

| ID | Title | Severity | Status | Category |
|----|-------|----------|--------|----------|
| AD-001 | Django admin change form bypasses the state machine and the moderation gate entirely | CRITICAL | Open | Security / Integrity |
| AD-002 | Editing an auto-failed ad is a silent dead end — no re-moderation, purge timer never resets | HIGH | Open | Correctness |
| AD-003 | `copy_ad` aliases the source ad's photo files, so deleting the source breaks the copy | HIGH | Open | Data Integrity |
| AD-004 | Manually archived ads are hard-deleted 60 days after the manual archive, not 4 months from `published_at` | HIGH | Open | Data Loss |
| AD-005 | `create_draft_ad`'s `IntegrityError` recovery is dead code — the retry always raises `TransactionManagementError` | HIGH | Open | Reliability |
| AD-006 | Seller-scoped photo dedup returns another ad's row, silently stripping photos and orphaning files | MEDIUM | Open | Correctness |
| AD-007 | Draft sweep uses `created_at`, so an active >30 min dialog is purged mid-flow and reported as a moderation failure | MEDIUM | Open | Correctness |
| AD-008 | `ON_MODERATION` is never a durable state — the pending-moderation queue and metrics are permanently empty | MEDIUM | Open | Maintainability |
| AD-009 | Price/photo-only edit does not restart the auto-archive clock, contradicting US-S7 | MEDIUM | Open | Spec Deviation |
| AD-010 | Bulk-moderation JSON API duplicates the bulk service without transactions or row locks and swallows state-machine errors | MEDIUM | Open | Reliability |
| AD-011 | `archived_at` is not cleared on `ARCHIVED → PUBLISHED`, leaving a stale archive timer on live ads | MEDIUM | Open | Correctness |
| AD-012 | `copy_ad` is a second `DRAFT`-creation route that violates the one-draft-per-user index and leaks the raw DB error to the seller | MEDIUM | Open | Correctness |
| AD-013 | The transition matrix is a method-local dict rebuilt on every call — no single, inspectable registry | LOW | Open | Maintainability |
| AD-014 | `AdImage.position` has no uniqueness or contiguity constraint, so gallery order is not guaranteed | LOW | Open | Data Integrity |
| AD-015 | `ads_auto_publish=False` does not hide the seller's published ads, contradicting US-S9 | LOW | Open | Spec Deviation |

## Distribution

**Severity counts**

| CRITICAL | HIGH | MEDIUM | LOW |
|----------|------|--------|-----|
| 1 | 4 | 7 | 3 |

**Status counts**

| Status | Count |
|--------|-------|
| Open | 15 |

## Findings by Severity

### CRITICAL

#### AD-001: [CRITICAL] — Django admin change form bypasses the state machine and the moderation gate entirely

| Field | Value |
|---|---|
| **ID** | AD-001 |
| **Title** | Django admin change form bypasses the state machine and the moderation gate entirely |
| **Severity** | CRITICAL |
| **Category** | Security / Integrity (ISO 25010: Integrity of data, Confidentiality of moderation) |
| **File(s)** | `src/backend/apps/ads/admin.py:101-107`, `src/backend/apps/ads/admin.py:69-78`, `src/backend/apps/ads/models.py:363-500` |
| **Status** | Open |
| **Problem** | `AdAdmin.readonly_fields` lists only `moderation_failed_at`, `rejected_at`, `published_by`, `moderated_by`, `listing_purpose`. Every other lifecycle field is an editable form control: `status`, `published_at`, `original_published_at`, `archived_at`, `deleted_at`, and `user`. A staff account can therefore submit a normal `ModelForm` save that writes `status = PUBLISHED` straight into the column, completely skipping `Ad.transition_to()` and, more importantly, `auto_moderate()` — the automatic check that US-A10 designates as "the only automatic gate before PUBLISHED". The form also lets the moderator hand-pick `published_at`/`original_published_at`, so the DB check constraints (`ck_ads_published_at_if_published`) do not even fire. The same form can re-assign the ad to a different owner. |
| **Impact** | Content the business believes is guaranteed-reviewed can be put on the public marketplace without ever passing the banned-word, length, price, image-count, per-user-ads or duplicate-title checks — a moderator typo or a well-meaning "fix the ad for this seller" in the admin is indistinguishable from a reviewed publish. There is **no** `ModeratorActionLog` row and no `AnalyticsEvent`, so the audit trail US-A3 depends on has a silent hole and a policy violation is undetectable after the fact. Re-assigning `user` also silently transfers ownership of an ad, its analytics and its `AdFavorite` rows to another account. |
| **Root Cause** | The state machine is a method on the model (`Ad.transition_to`) rather than a write path the ORM enforces, so any code that saves the model directly bypasses it. `AdAdmin` was configured to make the *timestamps* read-only but left the *status* column and the owner FK editable, so the one surface an operator actually uses day-to-day is also the one surface with no guardrail. |
| **Recommendation** | Add `status`, `published_at`, `original_published_at`, `archived_at`, `deleted_at` and `user` to `AdAdmin.readonly_fields`, and drop the four `action_*` bulk buttons in favour of a single `reject` / `soft_delete` action that call the existing `moderation.admin_actions` services (which already log to `ModeratorActionLog`). If moderators genuinely need a manual publish, expose it as an explicit admin action that routes through `approve_ad()` → `auto_moderate()` so the audit row is always written. |
| **Effort** | S |
| **Priority** | P0 |

| Field | Value |
|---|---|
| **CWE** | CWE-284 (Improper Access Control) / CWE-693 (Protection Mechanism Failure) |
| **Likelihood** | HIGH |

| Field | Value |
|---|---|
| **Related Findings** | AD-008, AD-010 |

**Evidence — `src/backend/apps/ads/admin.py:101-114`** *(supports: "`status` and every lifecycle timestamp are editable form controls, so a plain ModelForm save writes the status column directly")*:
```python
    readonly_fields = [
        "moderation_failed_at",
        "rejected_at",
        "published_by",
        "moderated_by",
        "listing_purpose",
    ]
    date_hierarchy = "created_at"
    actions = [
        "action_reject",
        "action_ban_user",
        "action_soft_delete",
        "action_approve",
    ]
```

**Evidence — R-15 (live PostgreSQL 18, admin change-form POST)** *(supports: "a DRAFT ad was published through the admin with no moderation check, no audit log, and its owner reassigned")*:
```text
=== R3: Django admin direct status overwrite ===
  admin POST status -> HTTP 200 | status=published published_at=2026-09-27 05:00:00+00:00 owner=24
  owner is the STAFF user (reassigned)? True
  ModeratorActionLog rows: 0
  readonly_fields: ['moderation_failed_at', 'rejected_at', 'published_by', 'moderated_by', 'listing_purpose']
  status readonly: False
  published_at readonly: False
  user readonly: False
  actions: ['action_reject', 'action_ban_user', 'action_soft_delete', 'action_approve']

=== B2: force DRAFT -> DELETED (no gate) ===
  draft->DELETED via admin form: status=deleted deleted_at=2026-09-27 05:00:00+00:00
  moderation logs: 0
```

---

### HIGH

#### AD-002: [HIGH] — Editing an auto-failed ad is a silent dead end: no re-moderation, purge timer never resets

| Field | Value |
|---|---|
| **ID** | AD-002 |
| **Title** | Editing an auto-failed ad is a silent dead end — no re-moderation, purge timer never resets |
| **Severity** | HIGH |
| **Category** | Correctness (ISO 25010: Functional suitability) |
| **File(s)** | `src/backend/apps/ads/views/edit.py:248-265`, `src/backend/templates/ads/dashboard.html:102-127`, `src/backend/apps/core/management/commands/purge_failed_ads.py:44-50` |
| **Status** | Open |
| **Problem** | `ad_edit` has an explicit `else` branch for "other statuses" that writes `title`, `description` and price straight onto the row with `ad.save(update_fields=[...])`. For an ad in `ON_MODERATION_FAILED` this means the seller's corrections are saved, but the status is *not* moved back to `ON_MODERATION`, `auto_moderate()` is *not* re-run, and `moderation_failed_at` is *not* reset. The ad therefore keeps counting down the original 7-day purge clock while sitting in a status the state machine only allows to leave via `→ REJECTED` (i.e. to a moderator, never to the seller). |
| **Impact** | The dashboard labels these ads "Action required" and offers an Edit button, so a seller who follows the UI's own instruction spends effort fixing the ad and gets HTTP 200 with no feedback, no re-review, and no publication. Seven days after the *original* failure the ad is hard-purged and the seller's rewritten content is gone. A seller can hit this repeatedly and never recover a single failed ad. |
| **Root Cause** | `ad_edit` branches on `PUBLISHED` and `ARCHIVED` but has no `ON_MODERATION_FAILED` branch. `transition_to` deliberately forbids `ON_MODERATION_FAILED → ON_MODERATION` (a seller must not be able to re-enter the gate unchecked), so the "resubmit" transition simply was never built; the view's catch-all branch papers over the gap with a bare save. |
| **Recommendation** | Add an `ON_MODERATION_FAILED` branch to `ad_edit` that routes through `submit_ad()` exactly like the `PUBLISHED` + text-change branch does — but first decide the policy. The clean option is a dedicated driver call that moves `ON_MODERATION_FAILED → ON_MODERATION`, clears `moderation_failed_at`, and re-runs `auto_moderate()`; the strict option is to keep it terminal and instead surface an explicit "this ad cannot be edited, create a new one" state on the dashboard so the UI stops advertising an action that does not exist. Either way, do not silently accept the edit and let the purge timer run. |
| **Effort** | S |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **CWE** | n/a (correctness) |
| **Likelihood** | HIGH |

| Field | Value |
|---|---|
| **Related Findings** | AD-007, AD-008 |

**Evidence — `src/backend/apps/ads/views/edit.py:248-265`** *(supports: "the catch-all branch saves text/price without touching status, moderation_failed_at, or auto_moderate")*:
```python
        else:
            # Other statuses (ON_MODERATION, ON_MODERATION_FAILED): direct save
            ad.title = dto.title
            ad.description = dto.description
            ad = _apply_price_change(ad, dto.price_amount, price_currency_value)
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
```

**Evidence — `src/backend/templates/ads/dashboard.html:126-127`** *(supports: "the UI promises an action for failed ads that the view cannot perform")*:
```html
                                    {% if status == 'on_moderation_failed' or status == 'rejected' %}
                                        <p class="text-xs text-red-600 mt-2">{% trans "Action required" %}</p>
```

**Evidence — R-17 (live edit of an `ON_MODERATION_FAILED` ad, failed 6 d 23 h earlier)** *(supports: "content is rewritten, status unchanged, purge timer untouched, no re-moderation")*:
```text
=== C3: web edit of an ON_MODERATION_FAILED ad ===
  HTTP 200 -> status=on_moderation_failed
  title now='Completely rewritten valid title'
  moderation_failed_at still=2026-09-21 07:58:55.241670+00:00 (purge timer NOT reset)
  survived purge_failed_ads? True
  ModeratorActionLog rows for this ad: 0
```

---

#### AD-003: [HIGH] — `copy_ad` aliases the source ad's photo files, so deleting the source breaks the copy

| Field | Value |
|---|---|
| **ID** | AD-003 |
| **Title** | `copy_ad` aliases the source ad's photo files, so deleting the source breaks the copy |
| **Severity** | HIGH |
| **Category** | Data Integrity (ISO 25010: Integrity) |
| **File(s)** | `src/backend/apps/ads/services/copy_service.py:58-68`, `src/backend/apps/media/signals.py:21-40`, `src/telegram_bot/handlers/ad_copy.py:54` |
| **Status** | Open |
| **Problem** | `copy_ad` creates a new `AdImage` row per source image but copies `image`, `thumbnail_small`, `thumbnail_medium` and `thumbnail_large` **verbatim** — the two ads now point at the same physical files. The `AdImage` `pre_delete` receiver deletes a file as soon as *any* referencing `AdImage` row is deleted; it has no reference count and no "still referenced?" check. The code comment even states this as intended ("new rows, same storage keys — no file duplication"). |
| **Impact** | The two ads share a fate they should not share. When the source ad is hard-deleted — by `purge_deleted_ads` at 120 days, by `delete_sweep` after 60 days archived, or by `consent_hard_delete` at 30 days — the files vanish and the copy is left with `AdImage` rows pointing at non-existent keys. The published copy renders broken/404 images in its gallery and fails the media route, while the DB shows the photos as present so nothing detects the loss. Because both ads belong to the *same* seller, this fires on ordinary retention sweeps with no operator action at all. |
| **Root Cause** | De-duplicating storage keys was chosen to avoid copying bytes, but the storage layer assumes exclusive ownership of a key: `delete_adimage_files_on_delete` unconditionally erases it. Neither layer models "this key has N referencing rows". |
| **Recommendation** | Pick one and make it explicit. Either (a) copy the bytes to fresh UUID keys for the new ad (same pattern the bot already uses: `generate_storage_key()` + write), or (b) make the `pre_delete` receiver reference-count: only call `delete_photo()` when no other `AdImage` row still references that key. Option (b) is cheaper and also protects any other aliasing path added later. |
| **Effort** | M |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **CWE** | n/a (data integrity) |
| **Likelihood** | MEDIUM |

| Field | Value |
|---|---|
| **Related Findings** | AD-012 |

**Evidence — `src/backend/apps/ads/services/copy_service.py:58-68`** *(supports: "the copy reuses the source's storage keys")*:
```python
        # Copy images (new rows, same storage keys — no file duplication)
        for img in source.images.all():
            AdImage.objects.create(
                ad=new_ad,
                image=img.image,
                telegram_file_id=img.telegram_file_id,
                position=img.position,
                thumbnail_small=img.thumbnail_small,
                thumbnail_medium=img.thumbnail_medium,
                thumbnail_large=img.thumbnail_large,
            )
```

**Evidence — `src/backend/apps/media/signals.py:29-40`** *(supports: "any single AdImage row deletion erases the file unconditionally")*:
```python
    keys = list(instance.storage_keys())
    if not keys:
        return

    def _cleanup() -> None:
        for key in keys:
            try:
                delete_photo(key)
            except Exception:  # noqa: BLE001 — never let FS failure break the cascade
                logger.exception("Failed to delete media file for key: %s", key)

    transaction.on_commit(_cleanup)
```

**Evidence — R-18 (live: copy a 2-photo ad, then hard-delete the source)** *(supports: "the copy survives but both of its photo files are gone from disk")*:
```text
=== E1: copy_ad aliases the source ad's photo files ===
  source images: ['probe-copy-1.jpg', 'probe-copy-2.jpg']
  copy id=157 status=draft images=['probe-copy-1.jpg', 'probe-copy-2.jpg']
  same storage keys reused: True
  distinct AdImage rows: 4 (expected 4)
=== E2: hard-deleting the SOURCE ad wipes the COPY's photo files ===
  copy still exists: True ; copy AdImage rows: 2
    file probe-copy-1.jpg on disk: False
    file probe-copy-2.jpg on disk: False
```

---

#### AD-004: [HIGH] — Manually archived ads are hard-deleted 60 days after the manual archive, not 4 months from `published_at`

| Field | Value |
|---|---|
| **ID** | AD-004 |
| **Title** | Manually archived ads are hard-deleted 60 days after the manual archive, not 4 months from `published_at` |
| **Severity** | HIGH |
| **Category** | Data Loss (ISO 25010: Integrity, Availability) |
| **File(s)** | `src/backend/apps/ads/views/edit.py:298-300`, `src/backend/apps/core/management/commands/delete_sweep.py:45-51`, `src/backend/apps/core/management/commands/archive_sweep.py:45-55` |
| **Status** | Open |
| **Problem** | Both archive routes converge on the same `ARCHIVED` state, but only one of them is anchored to the seller's activity clock. `archive_sweep` archives when `published_at` is older than 60 days, and `delete_sweep` then removes `ARCHIVED` rows whose `archived_at` is older than 60 days — for an auto-archived ad that is exactly 4 months from `published_at`, as documented. `ad_archive` (the seller's manual "Archive" button) sets `archived_at = now()` on a *freshly published* ad, so the delete clock starts from the moment of the click rather than from `published_at`. |
| **Impact** | A seller who archives an ad they might want back loses it permanently in 60 days even if it was published a day ago, and even if they never touch it again. US-S7 promises "2 months after last publish/**edit** → ARCHIVED; 4 months → permanently removed. Timers count from `published_at`", and US-A5 repeats "delete @4 months (from `published_at`)" — the code delivers 2 months from an arbitrary click for the manual path. There is no notification to the seller before the hard delete, and `DELETED` rows are recoverable for 120 days but `ARCHIVED` rows are not (they are deleted outright). |
| **Root Cause** | The model has a single `ARCHIVED` status and a single `archived_at` column but no discriminator for *why* the ad was archived, so two different retention intents collapse into one timer. The `db-retention.md` table documents the ARCHIVED rule only as "2 months (from archived_at)", which silently contradicts the user stories. |
| **Recommendation** | Decide the intended semantic and make the code match the user stories. The least-surprising fix is to make `delete_sweep` measure the ARCHIVED clock from `COALESCE`-style "last activity" (`GREATEST(published_at, archived_at)`) rather than `archived_at` alone, so a manual archive can never shorten a seller's retention. If the current behaviour is actually intended, update US-S7/US-A5 and `db-retention.md` to say "2 months from the archive event, whether automatic or manual", and surface an in-dashboard countdown so the seller knows the ad is on a deletion clock. |
| **Effort** | S |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **CWE** | n/a (data loss) |
| **Likelihood** | MEDIUM |

| Field | Value |
|---|---|
| **Related Findings** | AD-009, AD-011 |

**Evidence — `src/backend/apps/ads/views/edit.py:296-300`** *(supports: "the manual archive anchors `archived_at` to the click, not to `published_at`")*:
```python
        if ad.status == AdStatus.PUBLISHED:
            ad.transition_to(AdStatus.ARCHIVED)
            logger.info("Ad %s archived by user %s", ad_id, request.user.id)
```

**Evidence — `src/backend/apps/core/management/commands/delete_sweep.py:45-51`** *(supports: "the hard-delete clock is 60 days from `archived_at`, with no reference to `published_at`")*:
```python
                cutoff_date = timezone.now() - timedelta(days=60)

                queryset = Ad.objects.filter(
                    status=AdStatus.ARCHIVED,
                    archived_at__lt=cutoff_date,
                )
```

**Evidence — R-19 (archive an ad published seconds earlier, back-date `archived_at` 61 d, run `delete_sweep`)** *(supports: "a freshly published ad is permanently destroyed")*:
```text
=== C6: manual archive then delete_sweep 60d (independent of published_at) ===
  after manual archive: status=archived archived_at=2026-09-28 06:58:57.052756+00:00
  hard-deleted 61d after a manual archive of a freshly published ad: True
```

---

#### AD-005: [HIGH] — `create_draft_ad`'s `IntegrityError` recovery is dead code — the retry always raises `TransactionManagementError`

| Field | Value |
|---|---|
| **ID** | AD-005 |
| **Title** | `create_draft_ad`'s `IntegrityError` recovery is dead code — the retry always raises `TransactionManagementError` |
| **Severity** | HIGH |
| **Category** | Reliability (ISO 25010: Fault tolerance) |
| **File(s)** | `src/telegram_bot/services/ad_data/orm.py:48-67` |
| **Status** | Open |
| **Problem** | `_create()` opens `transaction.atomic()` and then, inside the `except IntegrityError` handler, runs two more statements (`Ad.objects.filter(...).delete()` and `Ad.objects.create(...)`). Because `atomic()` here is the **outermost** block on the connection, Django does not create a savepoint for it — the failing INSERT has already aborted the PostgreSQL transaction, and every subsequent statement in the block is refused. The recovery path therefore cannot execute; it always raises `TransactionManagementError: An error occurred in the current transaction. You can't execute queries until the end of the 'atomic' block.` |
| **Impact** | The comment promises "Clean up and retry" for exactly the concurrent-`/post` race the code was written to survive, and that promise is never kept. A seller who sends `/post` twice in quick succession (two devices, a double tap, a retried Telegram update) gets an unhandled exception out of `cmd_post` — no draft row, no FSM state, and no reply from the bot. The stated "at most one in-progress DRAFT per user" invariant is instead maintained only by the delete-then-create, which means the second request *destroys* the first dialog's row: the seller sees the new dialog in the bot but the ad id in FSM state is already gone. |
| **Root Cause** | The retry was written as if the surrounding `atomic()` created a savepoint. It does not (Django only creates savepoints for *nested* atomic blocks), so the `except` handler is operating on an aborted transaction. Separately, `create_draft_ad` deletes the user's existing DRAFT before inserting, so the insert can only ever fail on a genuine race — i.e. the failure it is worst placed to handle. |
| **Recommendation** | Give the retry its own savepoint: wrap the failing statement in `with transaction.atomic():` (a *nested* block, which does create a savepoint) so the rollback is local, then perform the cleanup and retry outside that inner block. Keep the advisory-lock or a `select_for_update()` on the user row as the primary serializer so the `IntegrityError` path is genuinely a backstop rather than the main mechanism. |
| **Effort** | S |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **CWE** | n/a (reliability) |
| **Likelihood** | MEDIUM |

| Field | Value |
|---|---|
| **Related Findings** | AD-007, AD-012 (Phase 03 owns the locking *mechanism*; this finding is about the FSM DRAFT-persistence contract) |

**Evidence — `src/telegram_bot/services/ad_data/orm.py:48-67`** *(supports: "the retry statements run inside the outermost atomic() that the IntegrityError just aborted")*:
```python
    @sync_to_async
    def _create() -> Ad:
        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]
            # Remove any pre-existing in-progress DRAFT for this user before
            # creating a fresh one (Option D: delete + recreate). AdImage rows
            # CASCADE-delete via the FK. Orphaned media files are reclaimed by
            # sweep_orphaned_media.
            existing = Ad.objects.filter(user_id=user_id, status=AdStatus.DRAFT)
            if existing.exists():
                existing.delete()

            try:
                return Ad.objects.create(user_id=user_id, status=AdStatus.DRAFT)
            except IntegrityError:
                # Race: a concurrent create_draft_ad slipped through the above
                # check before the unique index was enforced. Clean up and retry.
                Ad.objects.filter(user_id=user_id, status=AdStatus.DRAFT).delete()
                return Ad.objects.create(user_id=user_id, status=AdStatus.DRAFT)
```

**Evidence — R-20 (real `uq_ads_single_draft_per_user` violation, then the code's own retry sequence)** *(supports: "the recovery path is unreachable — every statement after the IntegrityError is refused")*:
```text
=== B9: real IntegrityError inside atomic, then another query ===
  caught IntegrityError: duplicate key value violates unique constraint "uq_ads_single_draft_per_user"
  retry path FAILED: TransactionManagementError An error occurred in the current
  transaction. You can't execute queries until the end of the 'atomic' block.

=== B10: concurrent create_draft_ad (2 threads) ===
  results: [('ok', 82), ('ok', 83)]
  DRAFT rows for user: 1
```

**Evidence — D5 (second `/post` supersedes the first dialog's row)** *(supports: "the surviving DRAFT is the newer one, so the first dialog's ad_id is dangling")*:
```text
=== D5: seller deleting then re-creating (unique DRAFT index interaction) ===
  first draft id=153 still exists=False; second id=154
  submit_ad on the SUPERSEDED draft -> ok=False errors=['Ad not found']
```

---

### MEDIUM

#### AD-006: [MEDIUM] — Seller-scoped photo dedup returns another ad's row, silently stripping photos and orphaning files

| Field | Value |
|---|---|
| **ID** | AD-006 |
| **Title** | Seller-scoped photo dedup returns another ad's row, silently stripping photos and orphaning files |
| **Severity** | MEDIUM |
| **Category** | Correctness (ISO 25010: Functional suitability) |
| **File(s)** | `src/backend/apps/ads/services/images.py:62-78`, `src/backend/apps/ads/services/submission.py:217-227`, `src/backend/apps/moderation/services/auto_moderation.py:186-189` |
| **Status** | Open |
| **Problem** | `AdImageService.create_or_skip` looks up any `AdImage` of the *same seller* with a matching `sha256` and, on a hit, returns the existing row instead of creating one — even when that row belongs to a **different ad**. `submit_ad` ignores the return value, so the new ad ends up with fewer images than the seller uploaded (including zero). The dedup key is per-seller, not per-ad, but the effect being applied is per-ad. |
| **Impact** | A seller who posts the same photo on a second listing gets a listing with no photos, which then fails the `min_images = 1` automatic check. The seller is shown only "Ad failed moderation. Please check your content and try again." — a message that points at their text, not at the invisible photo problem — with no way to diagnose it. In production the file *was* already written and promoted to permanent storage by `move_staging_to_permanent`, so every occurrence also leaves an unreferenced original + three thumbnails on disk, reclaimable only by the orphan sweep. |
| **Root Cause** | The dedup predicate (`sha256` + `ad__user_id`) and the effect (`return the existing row`) are mismatched: the query is seller-scoped while the result is consumed as if it were ad-scoped. A correct version would either scope the query to `ad=ad`, or hard-link/copy the file and create a new row. |
| **Recommendation** | Scope the duplicate lookup to the ad being written (`AdImage.objects.filter(sha256=sha256, ad=ad)`) and keep the seller-wide log line only as a hint. If cross-ad reuse is genuinely wanted, copy the bytes to a fresh storage key so the new ad owns its own file, and keep the caller's return value so `submit_ad` can report "duplicate photo skipped" instead of failing the whole ad. |
| **Effort** | S |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **CWE** | n/a (correctness) |
| **Likelihood** | MEDIUM |

| Field | Value |
|---|---|
| **Related Findings** | AD-003 |

**Evidence — `src/backend/apps/ads/services/images.py:64-78`** *(supports: "a sha256 hit on any of the seller's ads short-circuits creation for the current ad")*:
```python
        if sha256:
            duplicate = AdImage.objects.filter(
                sha256=sha256,
                ad__user_id=ad.user_id,
            ).first()
            if duplicate is not None:
                logger.info(
                    "AdImage dedup: sha256=%s ad_id=%s user_id=%s "
                    "skipped (existing pk=%s)",
                    sha256[:12],
                    ad.pk,
                    ad.user_id,
                    duplicate.pk,
                )
                return duplicate
```

**Evidence — R-22 (live: same photo attached to a second ad of the same seller)** *(supports: "the second ad ends up with 0 photos and the returned row belongs to the first ad")*:
```text
=== B11: photo dedup across two ads of the same seller ===
  adA images=1  adB images=0
  returned row ad id for 2nd upload: 84 (adB id=85 adA id=84)
```

---

#### AD-007: [MEDIUM] — Draft sweep uses `created_at`, so an active >30 min dialog is purged mid-flow and reported as a moderation failure

| Field | Value |
|---|---|
| **ID** | AD-007 |
| **Title** | Draft sweep uses `created_at`, so an active >30 min dialog is purged mid-flow and reported as a moderation failure |
| **Severity** | MEDIUM |
| **Category** | Correctness (ISO 25010: Reliability) |
| **File(s)** | `src/backend/apps/core/management/commands/sweep_drafts.py:44-50`, `src/backend/apps/ads/services/submission.py:170-173`, `src/telegram_bot/handlers/ad_create/submit.py:94-101` |
| **Status** | Open |
| **Problem** | The 30-minute DRAFT retention is measured from `created_at` — the moment `/post` created the row — and never from `updated_at` or any later FSM step. The dialog has nine sequential steps (category → purpose → condition → features → city → title → description → price → photos), each of which involves user thinking time and, for photos, an upload round-trip. Nothing in the dialog touches the `Ad` row until submit, so a seller who is actively answering step 3 is indistinguishable from an abandoned row. When the sweep wins the race, `submit_ad` cannot find the row and returns `(False, ["Ad not found"])`. |
| **Impact** | Two compounding problems. (1) Legitimate work is destroyed mid-flow with no warning to the seller, and the staging photo files already uploaded for that dialog are never cleaned by the sweep (DRAFT ads have no `AdImage` rows yet — the sweep's "collect storage keys" loop always finds none for real bot drafts), so they are only reclaimed later by the orphan sweep. (2) The failure is mis-reported: `process_preview` renders every `submit_ad` failure as "Ad failed moderation. Please check your content and try again." and then clears the FSM state, so the seller is told their content is at fault when the draft was simply deleted underneath them — and the dialog is destroyed, so they cannot retry. |
| **Root Cause** | The retention rule is expressed as "abandoned after 30 min" but implemented as "created more than 30 min ago", and the two only coincide for a dialog abandoned at step one. The bot's error handling then collapses three distinct failure modes (`Ad not found`, moderation failure, translation failure) into one message. |
| **Recommendation** | Anchor the window to the last FSM activity — the cheapest correct version is to have each `ad_create` step handler touch the draft's `updated_at` (or push a `last_activity_at` into the sweep's filter) so the timer measures inactivity, as US-S2 states ("Abandoned drafts auto-deleted on **idle** timeout"). Separately, give `submit_ad` a distinguishable return for "draft no longer exists" and have `process_preview` tell the seller the dialog expired and to run `/post` again, instead of blaming their content. |
| **Effort** | S |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **CWE** | n/a (correctness) |
| **Likelihood** | MEDIUM |

| Field | Value |
|---|---|
| **Related Findings** | AD-002, AD-005 |

**Evidence — `src/backend/apps/core/management/commands/sweep_drafts.py:44-50`** *(supports: "the window is `created_at`-based, so any in-progress dialog older than 30 min is eligible")*:
```python
                # Query draft ads older than 30 minutes
                cutoff_date = timezone.now() - timedelta(minutes=30)

                queryset = Ad.objects.filter(
                    status=AdStatus.DRAFT,
                    created_at__lt=cutoff_date,
                )
```

**Evidence — `src/backend/apps/ads/services/submission.py:170-173`** *(supports: "a swept draft is reported as the generic 'Ad not found' string")*:
```python
        try:
            ad = Ad.objects.select_for_update().get(id=input.ad_id)
        except Ad.DoesNotExist:
            return False, ["Ad not found"]
```

**Evidence — R-23 (live: sweep a live draft, then submit)** *(supports: "the seller's dialog is destroyed and reported as a failure")*:
```text
=== C2: DRAFT mid-dialog killed by 30-min sweep -> submit says 'Ad not found' ===
  submit_ad after sweep -> ok=False errors=['Ad not found']
```

---

#### AD-008: [MEDIUM] — `ON_MODERATION` is never a durable state — the pending-moderation queue and metrics are permanently empty

| Field | Value |
|---|---|
| **ID** | AD-008 |
| **Title** | `ON_MODERATION` is never a durable state — the pending-moderation queue and metrics are permanently empty |
| **Severity** | MEDIUM |
| **Category** | Maintainability (ISO 25010: Analysability, Conformity) |
| **File(s)** | `src/backend/apps/ads/services/submission.py:229-241`, `src/backend/apps/ads/views/edit.py:336-343`, `src/backend/apps/ads/views/dashboard.py:64-66`, `src/backend/apps/analytics/services/moderation_analytics.py:102-108`, `src/backend/apps/moderation/services/priority.py:62-65` |
| **Status** | Open |
| **Problem** | Both writers of `ON_MODERATION` (`submit_ad` and `ad_reactivate`) immediately call `auto_moderate()` inside the *same* transaction, and `auto_moderate` always drives the ad to `PUBLISHED` or `ON_MODERATION_FAILED` before committing. `ON_MODERATION` is therefore never observable outside the transaction that created it — no committed row is ever left in that state. Four separate features still treat it as a durable state: the seller's "On Moderation" dashboard bucket, `ModerationAnalytics.get_pending_queue_size()`, `PriorityService.get_queued_ads()`, and the `status__in=[ON_MODERATION, ON_MODERATION]` half of the `max_ads_per_user` count. |
| **Impact** | The seller-facing "On Moderation" tab is always empty, so a seller cannot tell whether their submitted ad is queued. The moderation queue view (US-A12) can only ever show auto-failed ads, so the priority score computed at submit time is never surfaced for a pending ad. `get_pending_queue_size()` — the headline number on the moderation dashboard (US-A13) — is structurally always `0`, which makes the metric useless for alerting on a stuck pipeline: it can never distinguish "nothing pending" from "the pipeline is broken". |
| **Root Cause** | The design is synchronous (submit → check → publish in one transaction), which is a legitimate choice, but the schema and the consuming code were never updated to match. The `ON_MODERATION` status, its partial indexes (`IX_ads_draft_sweep` sits next to it in the same conditional-index family) and the queue/analytics queries all still assume an asynchronous queue that does not exist. |
| **Recommendation** | Choose one and make it consistent. If the synchronous gate is the intent, drop `ON_MODERATION` from the durable status set: remove the empty dashboard bucket, define `get_pending_queue_size()` as the count of `ON_MODERATION_FAILED` ads awaiting human review (or deprecate the metric), and narrow the `max_ads_per_user` count to `PUBLISHED` only. If an asynchronous queue is wanted instead, commit the submit at `ON_MODERATION` and move `auto_moderate()` to a worker/management command — that is a larger change and should be an explicit decision, not a side effect of this audit. Either way, document the chosen semantics in `docs/02-database/db-enums.md`, which currently describes `ON_MODERATION` as a state ads occupy. |
| **Effort** | M |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **CWE** | n/a (maintainability) |
| **Likelihood** | HIGH |

| Field | Value |
|---|---|
| **Related Findings** | AD-002, AD-001 |

**Evidence — `src/backend/apps/ads/services/submission.py:229-241`** *(supports: "`ON_MODERATION` and the moderation verdict are committed in the same transaction")*:
```python
        # Transition DRAFT -> ON_MODERATION (state machine requires this step)
        ad.transition_to(AdStatus.ON_MODERATION)

        # Delegate to shared auto-moderation service
        # Handles: banned_words, duplicate_title, all validations,
        # ModeratorActionLog, AnalyticsEvent (with enum member), status transitions
        # DB-001: auto_moderate is inside the outer atomic() so its inner
        # atomic() blocks become savepoints. If auto_moderate raises, the
        # entire submit_ad transaction rolls back — the ad stays DRAFT
        # (not committed in ON_MODERATION).
        from apps.moderation.services.auto_moderation import auto_moderate

        passed = auto_moderate(ad)
```

**Evidence — `src/backend/apps/analytics/services/moderation_analytics.py:102-108`** *(supports: "the pending-queue metric counts a status that is never committed")*:
```python
def get_pending_queue_size() -> int:
    """
    Returns:
        Number of ads currently in moderation queue (ON_MODERATION status).
    """
    return Ad.objects.filter(status=AdStatus.ON_MODERATION).count()
```

**Evidence — R-16 (live: full `submit_ad` then inspect the DB)** *(supports: "no committed row is ever left in `ON_MODERATION`")*:
```text
=== D3: is ON_MODERATION ever a durable state? ===
  submit_ad -> ok=True errors=[] terminal status=published
  any ON_MODERATION rows left in DB: 0
  analytics get_pending_queue_size() -> 0
  priority queue rows: 2
  AdModerationPriority rows created automatically: 4
```

---

#### AD-009: [MEDIUM] — Price/photo-only edit does not restart the auto-archive clock, contradicting US-S7

| Field | Value |
|---|---|
| **ID** | AD-009 |
| **Title** | Price/photo-only edit does not restart the auto-archive clock, contradicting US-S7 |
| **Severity** | MEDIUM |
| **Category** | Spec Deviation (ISO 25010: Conformity) |
| **File(s)** | `src/backend/apps/ads/views/edit.py:233-246`, `src/backend/apps/ads/models.py:449-453`, `docs/04-user-stories/seller-stories.md:50-53` |
| **Status** | Open |
| **Problem** | US-S7 specifies the retention clock as "2 months after last **publish/edit**", and `docs/02-database/db-schema.md:146` confirms `published_at` is "UPDATED on every PUBLISHED transition (timer reset)". The price-only branch of `ad_edit` saves `price_amount`, `price_currency`, `price_normalized_eur` and `updated_at` but never touches `published_at`, and no `PUBLISHED` transition occurs on that path. So a price-only edit — the exact action a seller performs to keep a listing alive — bumps `updated_at` and leaves the archive clock running. |
| **Impact** | A seller who updates the price of a listing that is 59 days old still has that listing archived by the next `archive_sweep` run, even though they just touched it. The seller-visible symptom is a listing that quietly disappears from search the day after they refreshed its price, and the archive → hard-delete chain (AD-004) then starts against an ad the seller believes they just refreshed. The same applies to the photo path described in US-S5, which the web view does not implement at all. |
| **Root Cause** | The auto-archive timer was anchored to the only field that the model can update safely (`published_at`, protected by `ck_ads_published_at_if_published`), but no one connected the other "seller activity" signals to it. `updated_at` already tracks the activity and is already indexed, so the model needed a deliberate decision rather than an implementation. |
| **Recommendation** | Pick the authoritative signal. The cleanest is to let `archive_sweep` filter on `Greatest(published_at, updated_at)` — `updated_at` is `auto_now` on every write, so it already means "last seller or system activity" and needs no new writes. If you prefer to keep the sweep simple, bump `published_at` in the price-only branch (safe: the check constraint only requires it to be non-null for `PUBLISHED` rows) and note the change in `db-schema.md:146`. Then decide whether the web edit form should also accept photo changes, since US-S5 promises "price/**photo** edits publish instantly" and the view currently discards any uploaded files. |
| **Effort** | S |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **CWE** | n/a (spec deviation) |
| **Likelihood** | MEDIUM |

| Field | Value |
|---|---|
| **Related Findings** | AD-004, AD-011 |

**Evidence — `src/backend/apps/ads/views/edit.py:233-246`** *(supports: "the price-only branch saves `updated_at` but never `published_at`")*:
```python
            price_currency_value = _validate_price_currency(dto.price_currency)
            _validate_price_change(
                ad,
                dto.price_amount,
                ad.price_amount,
                price_currency_value,
                ad.price_currency,
            )
            # Price-only edit: publish instantly (no moderation re-check)
            ad = _apply_price_change(ad, dto.price_amount, price_currency_value)
            ad.save(
                update_fields=[
                    "price_amount",
                    "price_currency",
                    "price_normalized_eur",
                    "updated_at",
                ]
            )
```

**Evidence — `docs/04-user-stories/seller-stories.md:50-53`** *(supports: "the specification anchors the clock to the last publish *or edit*")*:
```markdown
### US-S7 — Auto-archive & removal
2 months after last publish/edit → `ARCHIVED`; 4 months → permanently removed. Timers count from
`published_at` (reset on every `PUBLISHED` transition). Seller sees archived ads in the dashboard
and can reactivate them (text re-checked). See decision J.
```

**Evidence — R-24 (live: price-only edit, then compare `published_at`)** *(supports: "`updated_at` moves but `published_at` does not")*:
```text
=== D1: price-only edit — does it reset published_at (US-S7 'after last edit')? ===
  HTTP 200 status=published price=777.00
  published_at before=2026-09-28 07:05:25.667230+00:00 after=2026-09-28 07:05:25.667230+00:00 unchanged=True
  updated_at bumped?  True
```

---

#### AD-010: [MEDIUM] — Bulk-moderation JSON API duplicates the bulk service without transactions or row locks and swallows state-machine errors

| Field | Value |
|---|---|
| **ID** | AD-010 |
| **Title** | Bulk-moderation JSON API duplicates the bulk service without transactions or row locks and swallows state-machine errors |
| **Severity** | MEDIUM |
| **Category** | Reliability (ISO 25010: Fault tolerance) |
| **File(s)** | `src/backend/apps/moderation/views/api_bulk.py:69-88`, `src/backend/apps/moderation/admin_actions.py:140-227`, `src/backend/apps/moderation/services/moderation_log.py:93-124` |
| **Status** | Open |
| **Problem** | The JSON endpoint `POST /moderation/api/v1/bulk-action/` re-implements the same four bulk operations that already exist as admin actions in `apps/moderation/admin_actions.py`, but does so with none of their guarantees: no `transaction.atomic()` wrapper, no `select_for_update()` on the target rows, and a bare `except Exception` per ad that logs at ERROR and reports a generic "Processing failed" to the client. The `FLAG` branch additionally fetches the ad with no status filter and calls `PriorityService().calculate_and_save()` outside any transaction. |
| **Impact** | A moderator bulk-rejecting a selection while an automated action or another moderator touches the same ad has no serialization, so partial application is possible (some ads logged as rejected, others not) with no atomic boundary to fall back on. The broad `except` swallows the state machine's own `ValueError` — the exact signal that the ad was not in a modifiable state — so an operator who selects the wrong set sees only "Processing failed" with no indication of why, and every such occurrence is logged at ERROR level (verified: `Bulk moderation failed for ad 125: Invalid transition: archived -> rejected`) which will pollute alerting with what is really user input error. Duplicated bulk logic in two places is also a maintenance trap: a fix to `bulk_reject` will not reach the API. |
| **Root Cause** | Two parallel implementations of one domain operation. The admin actions were written with the correct transaction/lock discipline; the JSON endpoint was added later as a thin adapter but grew its own loop instead of delegating. |
| **Recommendation** | Delete the loop in `api_bulk.py` and have each branch call the corresponding function in `apps/moderation.admin_actions` (`bulk_approve` / `bulk_reject` / `bulk_ban_users` / the soft-delete action), which already return `(processed, errors)` and handle locking. Replace the bare `except Exception` with a narrow one and distinguish `AdTransitionError` (a 409-style "ad is not in a modifiable state") from genuine infrastructure errors so an operator gets a usable message and the log stays at a sane level. Add `transaction.atomic()` around the `FLAG` branch. |
| **Effort** | S |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **CWE** | n/a (reliability) |
| **Likelihood** | LOW |

| Field | Value |
|---|---|
| **Related Findings** | AD-001, AD-008 |

**Evidence — `src/backend/apps/moderation/views/api_bulk.py:69-88`** *(supports: "per-ad loop with no transaction, no row lock, and a bare `except Exception`")*:
```python
        for pk in selected_items:
            ad = None
            try:
                ad = Ad.objects.get(pk=pk)
                if action == "approve":
                    if approve_ad(ad):
                        completed += 1
                    else:
                        errors.append({"id": pk, "error": "Not in reviewable state"})
                elif action == "reject":
                    reason = payload.get("reason", "Bulk rejected by moderator")
                    if reject_ad(ad, reason=reason):
                        completed += 1
                    else:
                        errors.append({"id": pk, "error": "Processing failed"})
                elif action == "ban":
                    ban_user_for_ad(ad, reason=payload.get("reason", "Bulk action"))
                    completed += 1
                elif action == "flag":
                    PriorityService().calculate_and_save(ad)
                    completed += 1
            except Exception:
                logger.exception("Bulk moderation failed for ad %s", pk)
                errors.append({"id": pk, "error": "Processing failed"})
```

**Evidence — R-28 (live: bulk-reject an ad that is not in a modifiable state)** *(supports: "the state machine's ValueError is logged at ERROR and reported as a generic failure")*:
```text
Bulk moderation failed for ad 125: Invalid transition: archived -> rejected. Allowed targets from archived: on_moderation, published

=== C8: bulk moderation JSON API on a PUBLISHED ad ===
  bulk reject of PUBLISHED ad -> HTTP 200 body=b'{"completed": 0, "errors": [{"id": 125, "error": "Processing failed"}]}'
  n2 status after bulk reject: archived
```

---

#### AD-011: [MEDIUM] — `archived_at` is not cleared on `ARCHIVED → PUBLISHED`, leaving a stale archive timer on live ads

| Field | Value |
|---|---|
| **ID** | AD-011 |
| **Title** | `archived_at` is not cleared on `ARCHIVED → PUBLISHED`, leaving a stale archive timer on live ads |
| **Severity** | MEDIUM |
| **Category** | Correctness (ISO 25010: Integrity) |
| **File(s)** | `src/backend/apps/ads/models.py:446-455`, `src/backend/apps/ads/models.py:370-393` |
| **Status** | Open |
| **Problem** | `transition_to` clears the "other" timestamps for a new status but not for the status being left. Entering `ON_MODERATION` explicitly nulls `archived_at`, `deleted_at`, `rejected_at` and `moderation_failed_at`; entering `PUBLISHED` only nulls `moderated_by` and `moderation_failed_at`. So a direct `ARCHIVED → PUBLISHED` reactivation leaves `archived_at` at the moment of archiving on an ad that is live, visible in listings and indexed by `IX_ads_pub_listing`. |
| **Impact** | The status/timestamp invariant documented in `docs/02-database/db-schema.md:179` ("`published_at` (PUBLISHED), `archived_at` (ARCHIVED), …") is one-directional in the DB, so nothing rejects the inconsistent row — it just sits there. Any future query or report that reasons about an ad from `archived_at` (a retention report, a "last hidden" column, a metric that drops the `status` filter for performance) will mis-classify live ads, and a future sweep that is refactored to reuse `archived_at` as a generic inactivity signal would hard-delete live listings. Today the blast radius is contained only because `delete_sweep` also filters on `status = ARCHIVED`. |
| **Root Cause** | The "clear the timestamps of the state you are leaving" logic was written per-target-status rather than per-source-status, so it is applied inconsistently across the matrix. The `PUBLISHED` branch predates the reactivation path and was never revisited. |
| **Recommendation** | Make the rule explicit in `transition_to`: compute the set of "other" lifecycle timestamps from the *source* status and null all of them, so the matrix has one uniform invariant. Add a model-level or DB-level test asserting that for every legal edge, a timestamp is non-null if and only if its status is active — `apps/ads/tests/test_ad_constraints.py` already exercises the one-way direction, so extending it to both directions is a small, high-value addition. |
| **Effort** | S |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **CWE** | n/a (correctness) |
| **Likelihood** | MEDIUM |

| Field | Value |
|---|---|
| **Related Findings** | AD-004, AD-009 |

**Evidence — `src/backend/apps/ads/models.py:446-462`** *(supports: "the PUBLISHED branch clears only `moderated_by` and `moderation_failed_at`, not `archived_at`")*:
```python
        if new_status == AdStatus.PUBLISHED:
            # published_at doubles as the archive-sweep timer (archive @ 2 months)
            # and is reset on EVERY PUBLISHED transition, so an ad a moderator
            # re-approves gets a fresh window. original_published_at is set once
            # and never changed, preserving the first-publication timestamp.
            self.published_at = timestamp
            if self.original_published_at is None:
                self.original_published_at = timestamp
            self.moderated_by_id = moderator_id
            self.moderation_failed_at = None
            self.rejected_at = None
        elif new_status == AdStatus.ARCHIVED:
            self.archived_at = timestamp
```

**Evidence — R-29 (live: archive then reactivate, print `archived_at`)** *(supports: "the stale archive timestamp survives into the live `PUBLISHED` state")*:
```text
=== R1: legal transitions + side effects ===
  ->ARCHIVED                   status=archived    pub=06:54:58 orig=06:54:58 arch=06:54:59 del=- fail=- rej=-
  ->PUBLISHED (reactivate)     status=published    pub=06:55:00 orig=06:54:58 arch=06:54:59 del=- fail=- rej=-
  ARCHIVED->ON_MODERATION      status=on_moderation pub=06:55:00 orig=06:54:58 arch=- del=- fail=- rej=-

=== C10: archived_at NOT cleared on ARCHIVED->PUBLISHED reactivate ===
  status=published archived_at=2026-09-28 06:57:57.555063+00:00 (stale from archive step: True)
```

---

#### AD-012: [MEDIUM] — `copy_ad` is a second `DRAFT`-creation route that violates the one-draft-per-user index and leaks the raw DB error to the seller

| Field | Value |
|---|---|
| **ID** | AD-012 |
| **Title** | `copy_ad` is a second `DRAFT`-creation route that violates the one-draft-per-user index and leaks the raw DB error to the seller |
| **Severity** | MEDIUM |
| **Category** | Correctness (ISO 25010: Functional suitability, Confidentiality of error detail) |
| **File(s)** | `src/backend/apps/ads/services/copy_service.py:28-56`, `src/telegram_bot/handlers/ad_copy.py:53-62`, `src/backend/apps/ads/models.py:353-357` |
| **Status** | Open |
| **Problem** | `create_draft_ad` is the designated single entry point for starting a dialog: it normalises any existing `DRAFT` for the user before inserting, so "at most one in-progress DRAFT" holds by construction. `copy_ad` is a second, independent route — reached directly from `src/telegram_bot/handlers/ad_copy.py:54` — that instantiates `Ad(...)` and calls `save()` with no status argument (so the model default `DRAFT` applies) and no pre-cleanup. The `uq_ads_single_draft_per_user` partial unique index (`src/backend/apps/ads/models.py:353-357`) therefore rejects the insert whenever the seller already has an open dialog. The bot handler catches bare `Exception` and answers `_("Failed to copy ad: {error}").format(error=e)`. |
| **Impact** | `/copy <id>` simply fails for any seller who is mid-dialog, with a message that renders the raw psycopg/PostgreSQL text — a table name, a constraint name and internal schema detail — into a Telegram chat. It is also a localization and tone failure: the same key is used for a permission error, a missing ad and a database fault, so the user cannot act on any of them. The lifecycle consequence is worse than cosmetic: because the copy is a `DRAFT`, it is subject to the 30-minute sweep (AD-007), yet the seller never received an ad id they could use if the dialog is lost. |
| **Root Cause** | DRAFT creation is not modelled as a single domain operation. Two modules construct the same aggregate's initial state independently, only one of which honours the invariant, and the bot treats an infrastructure exception as a user-facing validation message. |
| **Recommendation** | Make `create_draft_ad` the only writer of the `DRAFT` state: have `copy_ad` accept an already-created ad id (or call `create_draft_ad` itself and then populate it), so the "one open dialog per seller" normalisation and the unique-index race handling live in exactly one place. In `ad_copy.py`, catch the specific expected conditions (`PermissionError`, `Ad.DoesNotExist`, and a dedicated `DraftInProgress` signal) and answer with a specific, translated message; reserve the `except Exception` branch for a generic apology plus an admin-facing log. |
| **Effort** | S |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **CWE** | CWE-209 (Generation of Error Message Containing Sensitive Information) |
| **Likelihood** | MEDIUM |

| Field | Value |
|---|---|
| **Related Findings** | AD-003, AD-005 |

**Evidence — `src/backend/apps/ads/services/copy_service.py:38-53`** *(supports: "the copy is constructed directly with the model-default DRAFT status and no pre-cleanup of the seller's existing draft")*:
```python
        new_ad = Ad(
            user_id=seller_user_id,
            category=source.category,
            city=source.city,
            # Copy all language variants
            title=source.title,
            title_en=source.title_en,
            title_bs=source.title_bs,
            description=source.description,
            description_en=source.description_en,
            description_bs=source.description_bs,
            original_language=source.original_language,
            # Copy listing purpose
            listing_purpose_id=source.listing_purpose_id,
        )
        new_ad.save()
```

**Evidence — `src/telegram_bot/handlers/ad_copy.py:53-62`** *(supports: "the raw exception text is formatted into the seller-facing message")*:
```python
    try:
        new_ad = await sync_to_async(copy_ad)(ad_id, user_id)
        logger.info("Ad %d copied to draft %d by user %d", ad_id, new_ad.id, user_id)
    except PermissionError:
        await message.answer(_("You can only copy your own ads."))
        return
    except Exception as e:
        logger.exception("Failed to copy ad %d for user %d", ad_id, user_id)
        await message.answer(_("Failed to copy ad: {error}").format(error=e))
        return
```

**Evidence — R-21 (live: `/copy` while a dialog is already open)** *(supports: "the unique index fires and its text is what the seller sees")*:
```text
open DRAFT before /copy: id=159
copy_ad RAISED IntegrityError
  message surfaced to the seller by ad_copy.py: duplicate key value violates
  unique constraint "uq_ads_single_draft_per_user"
```

---

### LOW

#### AD-013: [LOW] — The transition matrix is a method-local dict rebuilt on every call — no single, inspectable registry

| Field | Value |
|---|---|
| **ID** | AD-013 |
| **Title** | The transition matrix is a method-local dict rebuilt on every call — no single, inspectable registry |
| **Severity** | LOW |
| **Category** | Maintainability (ISO 25010: Modularity, Analysability) |
| **File(s)** | `src/backend/apps/ads/models.py:395-409` |
| **Status** | Open |
| **Problem** | `ALLOWED_TRANSITIONS` is a dict literal built inside `transition_to` on every invocation, mapping `AdStatus` to a `set[AdStatus]`. It is never exposed, so nothing outside the model can ask "is X → Y legal?", every caller re-derives the same knowledge as an `if` chain over statuses, and the project's own "no magic strings, fixed value sets in a named model" rule is met only inside a method body rather than in a module-level, testable constant. |
| **Impact** | Low direct risk — the matrix itself is correct (R-01 through R-03 all pass). The cost is maintainability: the matrix is invisible to tests that do not drive real transitions, invisible to documentation tooling, and duplicated as implicit knowledge in `submit_ad`, `ad_edit`, `moderation_log`, `admin_actions` and `deletion`. Adding a status today means editing the model plus auditing five call sites for status-name comparisons. |
| **Recommendation** | Hoist the matrix to a module-level `Mapping[AdStatus, frozenset[AdStatus]]` in `apps/core/enums.py` (next to `AdStatus`) or a small `apps/ads/transitions.py`, and add a public `is_transition_allowed(src, dst)` helper so callers and tests can query it instead of re-deriving. That also gives the docs generator a single source to read. This is a pure refactor with no behaviour change. |
| **Effort** | S |
| **Priority** | P3 |

| Field | Value |
|---|---|
| **CWE** | n/a (maintainability) |
| **Likelihood** | LOW |

| Field | Value |
|---|---|
| **Related Findings** | — |

**Evidence — `src/backend/apps/ads/models.py:395-409`** *(supports: "the matrix is a method-local dict, rebuilt per call and not reachable from outside the model")*:
```python
        allowed = {
            AdStatus.DRAFT: {AdStatus.ON_MODERATION},
            AdStatus.ON_MODERATION: {
                AdStatus.PUBLISHED,
                AdStatus.REJECTED,
                AdStatus.ON_MODERATION_FAILED,
            },
            AdStatus.ON_MODERATION_FAILED: {AdStatus.REJECTED},
            AdStatus.REJECTED: set(),  # terminal state (re-publish requires a new ad)
            AdStatus.PUBLISHED: {AdStatus.ARCHIVED, AdStatus.ON_MODERATION},
            AdStatus.ARCHIVED: {AdStatus.ON_MODERATION, AdStatus.PUBLISHED},
            AdStatus.DELETED: set(),  # terminal
        }
        if new_status not in allowed.get(current, set()):
```

---

#### AD-014: [LOW] — `AdImage.position` has no uniqueness or contiguity constraint, so gallery order is not guaranteed

| Field | Value |
|---|---|
| **ID** | AD-014 |
| **Title** | `AdImage.position` has no uniqueness or contiguity constraint, so gallery order is not guaranteed |
| **Severity** | LOW |
| **Category** | Data Integrity (ISO 25010: Integrity) |
| **File(s)** | `src/backend/apps/ads/models.py:564-566`, `src/backend/apps/ads/models.py:612-635` |
| **Status** | Open |
| **Problem** | `AdImage` has four `CheckConstraint`s (image-key format) and four indexes, but no `unique_together` on `(ad, position)` and no check that positions form `0..n-1`. `Meta.ordering = ["position"]` is the only thing making the gallery deterministic. The one production writer (`submit_ad`, positions from the bot's `AdCreateState.photos` list) happens to produce distinct contiguous values, and `copy_ad` copies the source's positions, so the invariant holds today by construction. |
| **Impact** | Contained today. The risk is that any future writer — a photo-reordering endpoint (US-S5 promises photo edits, currently unimplemented), a re-import, or a manual admin fix — can create duplicate or gapped positions, after which "the first photo" (used as the ad's cover image in listings and search) becomes whichever row the planner returns first, and that choice is not stable. |
| **Recommendation** | Add `unique_together = (("ad", "position"),)` to `AdImage.Meta` and a migration. If you are not ready to guarantee contiguity (a reordering flow that temporarily duplicates positions is a legitimate design), at least add the uniqueness constraint and document that gaps are permitted. |
| **Effort** | S |
| **Priority** | P3 |

| Field | Value |
|---|---|
| **CWE** | n/a (data integrity) |
| **Likelihood** | LOW |

| Field | Value |
|---|---|
| **Related Findings** | AD-006 |

**Evidence — R-10 (introspected `AdImage._meta`)** *(supports: "no uniqueness on `(ad, position)` and no count constraint exist")*:
```text
  AdImage meta constraints: ['ck_ad_images_image_key_format', 'ck_ad_images_thumb_small_key_format',
    'ck_ad_images_thumb_medium_key_format', 'ck_ad_images_thumb_large_key_format']
  AdImage unique_together: ()
  AdImage indexes: ['IX_adimages_image', 'IX_adimages_thumb_small', 'IX_adimages_thumb_medium', 'IX_adimages_thumb_large']
```

---

#### AD-015: [LOW] — `ads_auto_publish=False` does not hide the seller's published ads, contradicting US-S9

| Field | Value |
|---|---|
| **ID** | AD-015 |
| **Title** | `ads_auto_publish=False` does not hide the seller's published ads, contradicting US-S9 |
| **Severity** | LOW |
| **Category** | Spec Deviation (ISO 25010: Conformity) |
| **File(s)** | `src/backend/apps/ads/services/listings_query.py:134-139`, `src/backend/apps/users/admin.py:25`, `docs/04-user-stories/seller-stories.md:59-61` |
| **Status** | Open |
| **Problem** | US-S9 states that the publishing ban "`ads_auto_publish=False` blocks new ads and hides existing ads (not deleted)". The publish block is implemented (`AccountState.can_publish_ad`), but the "hides existing ads" half is not: the public queryset filters on `user__is_declined=False` only. In practice the consent-decline flow sets **both** flags together, so the behaviour is correct for the user-facing decline button — the gap only appears when an operator flips `ads_auto_publish` alone from the user admin page, which is exposed in `UserAdmin.list_display`/`list_editable`. |
| **Impact** | An operator who "bans publishing" for a seller via the admin sees the ban take effect on new posts while every existing listing stays live in search and on the site, with no error or warning. Two similarly named flags with different scopes is an easy place to make a compliance mistake. |
| **Recommendation** | Either drop `ads_auto_publish` from the admin's editable fields and document that hiding is controlled by `is_declined`, or make the visibility rule explicit and derive it from a single state object (e.g. `AccountState.is_ads_visible`) so listings, search, alerts and the dashboard all agree. Updating US-S9 to describe the two flags separately is also acceptable if the current split is intentional. |
| **Effort** | S |
| **Priority** | P3 |

| Field | Value |
|---|---|
| **CWE** | n/a (spec deviation) |
| **Likelihood** | LOW |

| Field | Value |
|---|---|
| **Related Findings** | — |

**Evidence — `src/backend/apps/ads/services/listings_query.py:134-139`** *(supports: "visibility is gated on `is_declined` only — `ads_auto_publish` is not consulted")*:
```python
        ads = (
            Ad.objects.filter(status=AdStatus.PUBLISHED, user__is_declined=False)
            .filter(Q(category__isnull=True) | Q(category__is_active=True))
            .select_related("category", "city", "user")
            .prefetch_related("features", "user__trust_score", "images")
        )
```

**Evidence — `docs/04-user-stories/seller-stories.md:59-61`** *(supports: "the story attributes both halves of the behaviour to `ads_auto_publish`")*:
```markdown
### US-S9 — Publishing ban
`ads_auto_publish=False` blocks new ads and hides existing ads (not deleted). Reversible;
independent of account deletion and account ban (decision O1).
```

---

## Deprecated / Superseded Findings

None. No finding from this phase was withdrawn during the audit.

## Recommendations summary

| # | Finding | Severity | Effort | Priority |
|---|---------|----------|--------|----------|
| AD-001 | Admin change form bypasses state machine + moderation gate | CRITICAL | S | P0 |
| AD-002 | Auto-failed ad is a dead end; purge timer never resets | HIGH | S | P1 |
| AD-003 | `copy_ad` aliases photo files | HIGH | M | P1 |
| AD-004 | Manual archive hard-deleted 60 days after the click | HIGH | S | P1 |
| AD-005 | `create_draft_ad` `IntegrityError` recovery is dead code | HIGH | S | P1 |
| AD-006 | Photo dedup strips photos from a different ad | MEDIUM | S | P1 |
| AD-007 | Draft sweep uses `created_at`; failure mis-reported | MEDIUM | S | P1 |
| AD-008 | `ON_MODERATION` never durable; queue/metrics empty | MEDIUM | M | P2 |
| AD-009 | Price-only edit does not restart the archive clock | MEDIUM | S | P2 |
| AD-010 | Bulk-moderation API duplicates the service, no transaction | MEDIUM | S | P2 |
| AD-011 | `archived_at` not cleared on reactivation | MEDIUM | S | P2 |
| AD-012 | `copy_ad` bypasses the draft entry point; leaks DB error | MEDIUM | S | P2 |
| AD-013 | Transition matrix is a method-local dict | LOW | S | P3 |
| AD-014 | `AdImage.position` unconstrained | LOW | S | P3 |
| AD-015 | `ads_auto_publish=False` does not hide ads | LOW | S | P3 |

**Theme.** Two structural changes would close most of this list at once and are worth
sequencing first:

1. **Make `Ad` status changes go through one place.** The single highest-leverage change is to
   make the Django admin (and any future writer) go through the same driver the services use,
   which closes AD-001 outright and removes the "re-derive the matrix in five call sites" tax
   behind AD-013. Doing that first also makes AD-002 and AD-012's fixes natural rather than
   bolt-on.
2. **Make "seller activity" a first-class concept in retention.** AD-004, AD-007 and AD-009 are
   all the same underlying gap: three timers (`published_at`, `archived_at`, `created_at`) are
   each anchored to the event that *created* the state rather than to the event that made the
   seller care about it. Introducing a single, explicitly-defined "last seller activity" signal
   that all three sweeps read would fix the family together and make US-S7's wording literally
   true.

**Not recommended.** Do not add a second moderation layer, a workflow engine, or a generic
"lifecycle framework". The state machine is small, correct and well covered; it needs a caller's
discipline, not more abstraction.

## Phase template compliance checklist

| Check | Status |
|---|---|
| Every claim tied to concrete evidence (file:line, runtime observation, test name) | Yes |
| Every finding includes a falsifiable **Problem / Impact / Root Cause / Recommendation** | Yes |
| Every finding has **CWE** (security) or **"n/a — <category>"** | Yes |
| Every finding has **Likelihood** | Yes |
| Every finding has **Related Findings** (cross-referenced, not repeated) | Yes |
| Every finding has **Evidence** block with verbatim file:line or runtime log | Yes |
| Complexity vs. benefit stated for every recommendation (no "enterprise patterns for a small project") | Yes |
| No scope violation (DB/transaction *mechanics* left to Phase 03; authz left to Phase 14) | Yes |
| No code modified during the audit | Yes — all runtime work in a throwaway `audit05_probe` database, probe scripts removed |
| Severity assigned from the phase taxonomy | Yes |
| ID prefix matches the assigned phase (`AD-`) and is globally unique | Yes |

## Documentation gaps

Docs inspected: `docs/01-spec/spec-index.md`, `docs/01-spec/technical-specification.md`,
`docs/02-database/db-schema.md`, `docs/02-database/db-enums.md`, `docs/02-database/db-indexes.md`,
`docs/02-database/db-retention.md`, `docs/04-user-stories/seller-stories.md`,
`docs/04-user-stories/admin-stories.md`, `docs/ops/docker-deployment.md`.

Gaps found (each has a corresponding finding; the *documentation* fix is listed for completeness):

1. **`ON_MODERATION` is documented as an occupied state.** `docs/02-database/db-enums.md:31` and
   `db-schema.md:172` describe it in the present tense as a state an ad is in, and US-A12/US-A13
   build a queue and a "pending queue size" metric on top of it. In the shipped synchronous design
   no ad is ever committed in that state. → AD-008. (Choose the design, then update `db-enums.md`,
   `db-schema.md` and the two admin stories together.)
2. **ARCHIVED retention is documented two different ways.** `docs/02-database/db-retention.md:30`
   says "2 months (from archived_at)" while `seller-stories.md:50-53` and
   `admin-stories.md:64-65` say the clock counts from `published_at` and deletion happens at
   4 months. Both cannot be true for the manual-archive path. → AD-004.
3. **`docs/02-database/db-retention.md:67-68` contains a duplicated fragment** —
   "`deleted_at` is older than `deleted_at` is older than 120 days" — an editing slip that makes
   the retention rule hard to parse. Purely cosmetic, folded into AD-004's file list.
4. **The Django admin's lifecycle capability is undocumented.** No doc states whether
   moderators are *supposed* to be able to set `status` directly. US-A3 says "Unpublish, delete,
   change status, or ban all of a user's ads … logged to `ModeratorActionLog`", which reads as
   *authorising* a status change — so the code is arguably compliant with the story while
   violating the gate in US-A10. → AD-001 needs a doc decision, not just a code change: either
   narrow US-A3 or add a mandatory audit row.
5. **Search-vector trigger DDL is not versioned as a migration.** The `ads_search_vector_update`
   trigger and the `categories_name_propagate` rename trigger are created by
   `setup_search_triggers` (run from `entrypoint.sh` and `bootstrap_reference_data`), not by a
   Django migration, so a database built with a bare `manage.py migrate` silently has no
   `search_vector` maintenance at all. The propagation itself is correct (R-07 passes) and this is
   noted for the database/operations phases rather than filed here.

