---
# Report metadata
phase: "05"
phase_name: "ad-lifecycle"
date: "2026-09-28"
auditor: "Executor (subagent) — .ai/audit/05-ad-lifecycle/findings.md"
validator: "Kilo (validator subagent) — Phase 99"
mode: "problems-only"
id_prefix: "AD"
report_status: "validated"
validator_severity_taxonomy: ".kilo/commands/audit/phases/05-audit-ad-lifecycle.md#severity-taxonomy"
validator_anchor_commit: "9e96b84d58fc5a0ad1eb13664c35890f22f15f29"
validator_cross_references: ".ai/audit/03-db-concurrency/findings.md (DB-*), .ai/audit/99-validation/04-auth-login-validated-findings.md (VAL-004)"
---

# Validated Findings — Ad Lifecycle, Categories & Moderation

## Executive Summary

All 15 auditor findings were independently re-derived from source and re-proved at
runtime against a throwaway `audit05v_probe` PostgreSQL 18 database. **Nothing was
rejected outright**: 7 confirmed unchanged, 6 adjusted, 2 merged into Phase 03 as
duplicates. One finding was split, producing a new `AD-016`.

The validation did change the shape of the report in three ways that matter for
remediation:

1. **AD-001 is both a CRITICAL defect *and* a specification conflict.** The code
   defect is reproduced end-to-end and matches the phase rubric's CRITICAL examples
   verbatim. But the *framing* the auditor used — "bypasses the moderation gate" —
   contradicts US-A3 and `technical-specification.md:44-45`, which explicitly
   authorise moderators to change ad status. The unambiguous violations are
   different and narrower: no `ModeratorActionLog` row, mutable
   `original_published_at` (documented IMMUTABLE), silent owner transfer, and a
   hard HTTP 500 on two of the seven statuses. Fixing AD-001 therefore needs an
   **owner decision**, not just a code patch. See §4.
2. **AD-008 is much larger than reported.** The auditor framed it as a maintainability
   wart. It is in fact a spec deviation (US-S2, US-A12, US-A13, `db-enums.md:28`) whose
   real cost is that **the entire human approval path is dead code**: the review page's
   Approve button 404s, `bulk_approve` always returns 0, and `approve_ad()` always
   returns `False`. Recorded as VAL-003.
3. **Two findings are Phase 03 duplicates** (AD-005 ≡ DB-001, AD-007 ≡ DB-003) and one
   is half-duplicate (AD-012 ⊃ DB-009). Shipping them again would produce two
   independent fixes for one root cause.

Post-validation severity: **1 CRITICAL · 4 HIGH · 8 MEDIUM · 3 LOW**, plus 4 `VAL-`
validation-level findings. Four of the CRITICAL/HIGH items genuinely require an
architectural or structural change rather than a patch — see §7.

---

## R1 — Copy Source Findings

- Auditor file: `.ai/audit/05-ad-lifecycle/findings.md` (1113 lines, 15 findings).
- Anchor commit: `9e96b84` (working tree clean; no repository file created or modified
  by either the auditor or this validation).
- Isolation: all runtime work executed inside the `mko-bazuna-test` Compose project
  against a scratch database `audit05v_probe`, bootstrapped exactly as the auditor
  described (`migrate --run-syncdb` + `load_exchange_rates` + `setup_search_triggers` +
  `load_catalog`). The scratch database and all probe scripts were removed afterwards.
  The other auditors' `test_mko_bazuna_gw*` databases and the crash-looping
  `mko-bazuna-dev` stack were not touched.
- Independent reproduction, per finding:

| Auditor check | Validator's independent result |
|---|---|
| R-15 admin form bypasses state machine | **REPRODUCED, and worse than reported** (see AD-001) |
| R-16 `ON_MODERATION` never durable | **REPRODUCED**, plus a dead human-approval path (VAL-003) |
| R-17 edit of failed ad is a dead end | **REPRODUCED** |
| R-18 copy aliases photo files | **REPRODUCED** |
| R-19 manual archive deleted early | **REPRODUCED**; auditor's proposed fix independently verified correct |
| R-20 `IntegrityError` recovery is dead | **REPRODUCED**; exact Phase 03 duplicate of DB-001 |
| R-21 `copy_ad` with an open draft | **REPRODUCED**; overlap with DB-009 |
| R-22 seller-scoped photo dedup mis-scoped | **REPRODUCED** |
| R-23 draft sweep window / error conflation | **REPRODUCED**; first half duplicates DB-003 |
| R-24 price edit does not reset the clock | **REPRODUCED** |
| R-25 ruff clean | **CONFIRMED** — `All checks passed!` over the same scope |
| R-26 basedpyright 4 errors, 1 file | **CORRECTED** — 12 errors across 2 files (§6, AD-010 evidence note) |
| R-27 existing suites green | Accepted (not re-run; `--reuse-db` with a parallel auditor in flight is the known phantom-schema hazard) |
| R-28..R-32 structural claims | **CONFIRMED** with corrected evidence (AD-010, AD-011, AD-013, AD-014, AD-015) |

### Checkpoint 1 — Auditor analysis

- **Stage:** Auditor analysis
- **Findings in scope:** 15 (CRITICAL 1, HIGH 4, MEDIUM 7, LOW 3)
- **Evidence anchor:** `.ai/audit/05-ad-lifecycle/findings.md`; anchor commit `9e96b84`
- **Dependencies / blockers:** none
- **Checkpoint status:** closed

---

## R2 — Cross-Finding Analysis

### 2.1 Merges into Phase 03 (db-concurrency, in flight)

`Phase 03 findings already exist at .ai/audit/03-db-concurrency/findings.md. Two
phase-05 findings are the *same root cause* as a phase-03 finding that is already rated
higher, with better evidence and a better recommendation.`

| Phase-05 finding | Phase-03 finding | Overlap assessment |
|---|---|---|
| **AD-005** (HIGH) — `create_draft_ad` `IntegrityError` recovery is dead code | **DB-001** (CRITICAL) — "`create_draft_ad`'s race backstop always raises `TransactionManagementError`" | **Identical.** Same function, same lines, same mechanism, same exception. DB-001 additionally reproduces it from **6 real threads** (5 of 6 raise) and supplies the in-repo precedent for the fix (`telegram_bot/handlers/login.py:227-240` already wraps `get_or_create` in a nested `atomic()` savepoint). AD-005 adds nothing DB-001 lacks. → **MERGE, do not ship twice.** |
| **AD-007** (MEDIUM) — draft sweep uses `created_at` | **DB-003** (HIGH) — "`sweep_drafts` reaps an ad the seller is still typing" | **Same root cause for the sweep half**, and DB-003 already includes the `submit_ad` recoverability recommendation. AD-007's *second* half (the bot collapsing three failure modes into one message) is a distinct defect in a distinct file with a distinct fix → **split out as AD-016** and retained here. |
| **AD-012** (MEDIUM, first half) — `copy_ad` violates the one-draft index | **DB-009** (MEDIUM) — "`copy_ad` has no handling for the single-DRAFT invariant" | DB-009 owns the DB-side behaviour. AD-012's unique, higher-value content is the **CWE-209 raw-driver error text rendered into a Telegram chat** — that is a bot-layer defect DB-009 does not cover → **AD-012 re-scoped** to that half. |

> **Explicit answer to the AD-005 scoping question:** AD-005 does **not** belong to
> phase 05. It is the *same finding* Phase 03 filed as **DB-001 at CRITICAL**, and
> DB-001's evidence and fix are strictly better. Actioning AD-005 as written would
> create two independent patches for one line of code. **Absorb AD-005 into DB-001 and
> close AD-005.** Validator reproduction of the shared claim: the outermost-`atomic()`
> retry raises `TransactionManagementError`, and the correct savepoint pattern succeeds
> — confirming DB-001, and adding the note that the savepoint must wrap **only** the
> failing INSERT with the `except` *outside* the inner block (catching inside the
> savepoint leaves the block flagged for rollback and still fails).

### 2.2 Overlap with Phase 07 (media) — not yet executed

`Phase 07 has not run. AD-003 straddles two layers and MUST be split before phase 07
executes, or the two phases will each ship half a fix.`

AD-003's root cause is stated as "neither layer models *this key has N referencing
rows*", which is a **media-layer ownership-invariant** defect, not an ads-layer defect:

| Half | Layer | Owner |
|---|---|---|
| `pre_delete` erases a storage key with no "still referenced?" check | `apps/media/signals.py:21-40` | **Phase 07** must own the decision "does a media storage key have one owner or N?" |
| `copy_ad` reuses the source's storage keys | `apps/ads/services/copy_service.py:58-68` | **Phase 05** (AD-003, retained) |

The two candidate remediations are **mutually exclusive** (copy the bytes, *or*
reference-count the delete), so the decision cannot be made twice. → **VAL-004.**

### 2.3 Dependency chains

1. **AD-001 must land before or with AD-011.** `transition_to()` clears timestamps per
   *target* status, not per *source* status. While `status` remains an admin-editable
   column, fixing AD-011 in the model does not stop an admin form from writing an
   inconsistent row directly.
2. **AD-009's fix requires a matrix change, which couples it to AD-013.**
   `ALLOWED_TRANSITIONS[PUBLISHED] = {ARCHIVED, ON_MODERATION}` — there is **no
   `PUBLISHED → PUBLISHED` edge** (verified). The spec (decision J) requires
   `published_at` to be reset on price/photo edits, so a naive "`transition_to(PUBLISHED)`"
   fix raises `ValueError`. AD-009 therefore cannot be fixed without either a new matrix
   edge or an explicit timer-bump service, and the matrix is only inspectable after
   AD-013 hoists it out of the method body.
3. **AD-008 gates a large amount of apparently-green code.** See VAL-003: any fix that
   makes `ON_MODERATION` non-durable will invalidate 34 test call sites in 10 files that
   fabricate that state.
4. **AD-004's fix invalidates its own partial index.** `IX_ads_delete_sweep` is
   `(status, archived_at) WHERE status='archived'`. The correct fix keys on
   `published_at`, so a new partial index `(status, published_at) WHERE
   status='archived'` is a hard prerequisite, not an optional extra.

### 2.4 Conflicting evidence between phases

| Claim | Phase | Conflict |
|---|---|---|
| "all moderation flows are covered by green tests" | 05 (R-27) | vs. **VAL-003**: the human approval path is unreachable at runtime, yet its tests pass because they fabricate the state (§5). Not a code conflict — a **test-fidelity** conflict. |
| "the `create_draft_ad` retry is a backstop for a race" | 05 (AD-005) | vs. **DB-001 (CRITICAL)**: the backstop cannot execute at all. Resolved by merge. |
| "ARCHIVED retention is 2 months from `archived_at`" | `db-retention.md:30,79` | vs. **US-S7:51-53** and **US-A5:64-65** ("4 months, from `published_at`") and **decision J:156** ("timers count from `published_at`"). Three authoritative documents disagree; the code matches the minority reading. This is the AD-004 root conflict. |

### Checkpoint 2 — Researcher verification

- **Stage:** Researcher verification
- **Findings in scope:** 15 (+ 1 split-off, + 4 `VAL-`)
- **Cross-phase conflicts:** 3 (1 test-fidelity, 1 duplicate, 1 doc-vs-doc)
- **Merge candidates:** 3 (AD-005→DB-001, AD-007→DB-003, AD-012⊃DB-009)
- **Dependency chains:** 4
- **Checkpoint status:** closed

---

## R3 — Per-Finding Validation

### Verdict table (read this first)

| ID | Title (abridged) | Original | **Verdict** | **New severity** | One-line justification |
|---|---|---|---|---|---|
| AD-001 | Admin form bypasses the state machine | CRITICAL | **CONFIRMED** (+ spec conflict; owner decision required) | **CRITICAL** | Reproduced end-to-end and matched by the phase rubric's CRITICAL example; the *stated* harm ("bypasses the gate") is a spec conflict, the *real* harm is the missing audit row and mutable `original_published_at`. |
| AD-002 | Editing a failed ad is a dead end | HIGH | **CONFIRMED** | **HIGH** | Reproduced: content rewritten, `moderation_failed_at` untouched, no re-moderation; rubric = "purge timing wrong (failed too late)". |
| AD-003 | `copy_ad` aliases photo files | HIGH | **ADJUSTED** (split across phases) | **HIGH** | Reproduced; must be split — the `pre_delete` refcount half belongs to Phase 07 (VAL-004). |
| AD-004 | Manual archive deleted 60 d after the click | HIGH | **CONFIRMED** | **HIGH** | Reproduced; the auditor's `GREATEST()` recommendation is **correct** (independently verified) but needs a new partial index. |
| AD-005 | `create_draft_ad` retry is dead code | HIGH | **MERGED** → `DB-001` (Phase 03) | — (DB-001 = CRITICAL) | Exact duplicate of an existing Phase 03 CRITICAL with superior evidence and a superior fix. |
| AD-006 | Seller-scoped dedup returns another ad's row | MEDIUM | **CONFIRMED** | **MEDIUM** | Reproduced: the second ad receives 0 photos and the returned row belongs to the first ad. |
| AD-007 | Draft sweep uses `created_at` | MEDIUM | **MERGED** (sweep half) → `DB-003`; error half split to **AD-016** | — (DB-003 = HIGH) + AD-016 MEDIUM | The sweep half duplicates DB-003; the bot error-conflation half is a distinct defect worth its own ID. |
| AD-008 | `ON_MODERATION` is never durable | MEDIUM | **ADJUSTED** → **SPEC-DEVIATION** | **MEDIUM** | Real, but it violates US-S2/US-A12/US-A13, and its true blast radius (a dead human-approval path) is VAL-003. |
| AD-009 | Price-only edit does not reset the clock | MEDIUM | **CONFIRMED** (SPEC-DEVIATION) | **MEDIUM** | Reproduced; decision J names the exact required mechanism, which makes the deviation unambiguous. |
| AD-010 | Bulk JSON API duplicates the bulk service | MEDIUM | **ADJUSTED** (root cause refuted, defect narrowed) | **MEDIUM** | The quoted evidence does not exist in the file and the endpoint already delegates to the service; only the missing transaction/lock and the over-broad `except` survive. |
| AD-011 | `archived_at` not cleared on reactivation | MEDIUM | **ADJUSTED** (evidence corrected) | **MEDIUM** | Claim confirmed live, but the quoted code is **not** the shipped code and the "what the PUBLISHED branch clears" description is factually wrong. |
| AD-012 | `copy_ad` leaks the raw DB error to the seller | MEDIUM | **ADJUSTED** (re-scoped) | **MEDIUM** | DB-side half duplicates DB-009; the CWE-209 bot half is unique, reproduced, and retained. |
| AD-013 | Transition matrix is method-local | LOW | **CONFIRMED** | **LOW** | Verified: no module-level registry exists; a zero-behaviour-change refactor with real maintenance value. |
| AD-014 | `AdImage.position` unconstrained | LOW | **CONFIRMED** | **LOW** | Verified: `unique_together == ()`, no contiguity constraint. |
| AD-015 | `ads_auto_publish=False` does not hide ads | LOW | **ADJUSTED** (evidence corrected) | **LOW** | Substance confirmed, but the `list_editable` citation is false; the real exposure is the auto-generated `ModelForm`. |
| **AD-016** | *(new — split from AD-007)* Bot reports an expired draft as a moderation failure and destroys the dialog | MEDIUM | **NEW** | **MEDIUM** | Distinct file, distinct fix, and the only part of AD-007 that no other phase owns. |

**Tally:** Validated unchanged 7 · Reclassified 1 · Adjusted 6 · Merged 2 · Rejected **0** · New 1.

---

## Findings by Severity (post-validation)

### CRITICAL

#### AD-001: [CRITICAL] — The admin change form writes ad lifecycle state directly, with no audit row

> **Validation Note:**
> - **Action:** confirmed (unchanged severity) + **reclassified: SPEC-DEVIATION with a required owner decision**
> - **Detail:** The mechanism is 100 % real and reproduced end-to-end. The *auditor's
>   framing* is what needed correcting: "bypasses the moderation gate" is **not** a
>   violation of US-A10, because US-A10 (decision A, `technical-specification.md:42`)
>   says the automatic check is the only **automatic** gate, and
>   `technical-specification.md:44-45` grants the moderator (== admin role) the powers
>   "unpublish, review failed ads … ban all of a user's ads". US-A3:57-59 explicitly
>   authorises "change status" and requires it to be "**logged to
>   `ModeratorActionLog`**". The code satisfies the authorisation and violates the
>   logging half, plus three things no story authorises at all.
> - **See also:** §4 (owner decision), VAL-001, VAL-005

**What was independently verified (runtime, live PostgreSQL 18, `audit05v_probe`)**

| # | Verification | Result |
|---|---|---|
| V1 | `AdAdmin.readonly_fields` at runtime | `['moderation_failed_at', 'rejected_at', 'published_by', 'moderated_by', 'listing_purpose']` — `status`, `user`, `published_at` all **not** read-only |
| V2 | Introspected `ModelForm` field list | `archived_at, deleted_at, original_published_at, published_at, status, user` **plus all four `search_vector*` fields** are editable |
| V3 | POST `status=published` + hand-picked `published_at` = *now − 999 days* on a `DRAFT` | **HTTP 302**, `status=published`, `published_at=2024-01-03 13:38:54+00:00`, `original_published_at` set to the same, **owner reassigned to the staff account**, **`ModeratorActionLog` = 0**, **`AnalyticsEvent` = 0**, ad **visible in the public listing queryset** |
| V4 | A/B against the service path | `moderation_log.set_published(ad, moderator_id)` on an equivalent ad → **`ModeratorActionLog` = 1**. The form path → 0. The audit hole is proven by contrast, not by absence of evidence. |
| V5 | Wrong-timer consequence | A moderator-set `published_at` 999 days in the past → the very next `archive_sweep` run moves the ad straight to `ARCHIVED` (`status=archived`). This is the phase rubric's CRITICAL example "wrong `published_at`/lifecycle timer (wrong archive/delete)". |
| V6 | Terminal state resurrection | `DELETED` (documented terminal) → `status=published` + `published_at` via the form → **HTTP 302, `status=published`**. The terminal-state rule is not merely bypassed, it is inverted. |
| V7 | Which statuses the form can actually write | `ON_MODERATION` 302 · `ARCHIVED` 302 · `DELETED` 302 · `PUBLISHED` 302 · **`ON_MODERATION_FAILED` → uncaught `IntegrityError` (HTTP 500, `ck_ads_moderation_failed_at_if_failed`)** · **`REJECTED` → uncaught `IntegrityError` (HTTP 500, `ck_ads_rejected_at_if_rejected`)**. Those two timestamps are in `readonly_fields`, so the form can never produce a valid row for them and the failure is raised at the DB, not at validation. |
| V8 | `search_vector` hand-editing | The form exposes it, but `ads_search_vector_update` is `BEFORE INSERT OR UPDATE … FOR EACH ROW` and rewrites the column, so a manual edit is silently discarded. **Not filed as a defect** — no impact. |

**The unambiguous violations (fix these unconditionally)**

1. **No `ModeratorActionLog` row** — US-A3:57-59 requires moderation actions to be
   logged; the form writes zero. US-A13's moderator-performance metric reads
   `published_by`/`moderated_by`, so the action is also invisible to reporting.
2. **`original_published_at` is mutable through the form.** The model help-text and
   `db-schema.md:147` both call it "**IMMUTABLE**, audit only", and decision J:156
   states it "does NOT drive sweep" — it exists purely as a first-publication audit
   marker, and the form lets anyone rewrite it.
3. **Silent owner transfer.** `user` is editable, so one form save moves the ad, its
   analytics and its `AdFavorite` rows to another account. No story authorises changing
   an ad's owner (US-A3 says "ban all of a **user's** ads" — it presumes the ad set,
   not a reassignment).
4. **Two hard 500s** (V7) — an operator selecting `REJECTED` or `ON_MODERATION_FAILED`
   gets a server error and a `CheckViolation` traceback, not a validation message.

**Refuted sub-claims (do not carry these into the fix)**
- "the DB check constraints do not even fire" — they *do* fire; V7 shows them
  rejecting `REJECTED` and `ON_MODERATION_FAILED`. They simply fire too late, as a 500.
- "route manual publish through `approve_ad()` → `auto_moderate()`" — this would
  re-run the *automatic* criteria (banned words, duplicate-title) over a decision a human
  moderator has already made, and would **fail** an approve whenever the moderator
  deliberately overrode a duplicate-title flag. It also contradicts US-A3's "Actions are
  **instant**". Recommend against.
- "drop the four `action_*` bulk buttons" — the buttons are the *correct* path
  (`bulk_approve`/`bulk_reject`/`bulk_ban_users`/`bulk_delete` all write the audit row);
  they are broken only because of AD-008/VAL-003 (`bulk_approve` filters a status that
  is never committed).

---

### HIGH

#### AD-002: [HIGH] — Editing an auto-failed ad is a silent dead end

> **Validation Note:** confirmed unchanged. Reproduced: POST → **HTTP 200**, `title`
> rewritten, `status` still `on_moderation_failed`, `moderation_failed_at` **unchanged**
> (purge timer not reset), `purge_failed_ads` does **not** reclaim the rewritten content.
> `ON_MODERATION_FAILED → ON_MODERATION` is correctly blocked by the matrix (verified),
> so no "just call the driver" fix exists — the auditor is right that this needs a
> product decision. **Scope correction:** the catch-all branch is reached by **five** of
> the seven statuses (`DRAFT`, `ON_MODERATION`, `ON_MODERATION_FAILED`, `REJECTED`,
> `DELETED`), not the two named in the finding; the dashboard renders an `Edit` link
> unconditionally (`dashboard.html:101-105`). The fix should gate the branch on an
> explicit status allow-list rather than adding one more branch.

#### AD-003: [HIGH] — `copy_ad` aliases the source ad's photo files

> **Validation Note:** adjusted — **split across phases**, see §2.2 and VAL-004.
> Reproduced: `copy_ad` → 2 new `AdImage` rows carrying byte-identical storage keys
> (`same keys reused: True`); hard-deleting the source leaves the copy alive with 2
> `AdImage` rows whose files are **absent from disk** (`file … on disk? False`). The
> failure fires on ordinary retention sweeps (`delete_sweep`, `purge_deleted_ads`,
> `consent_hard_delete`) with no operator action. Severity held at HIGH — the phase
> rubric lists "photo count/order violated" as HIGH and a live ad rendering 404s is
> that. Retained in phase 05 = the ads-layer decision; the media-layer refcount
> decision is **Phase 07's**.

#### AD-004: [HIGH] — Manually archived ads are hard-deleted 60 days after the click

> **Validation Note:** confirmed unchanged. Reproduced against a fresh manual archive
> back-dated 61 days: the current sweep **does** select the row. The auditor's proposed
> `GREATEST(published_at, archived_at)` fix was tested rather than assumed and is
> **correct**: it does *not* select the row at +61 d, and the auto-archive path is
> unaffected (verified `archived_at − published_at = 61 days`, so `GREATEST` resolves to
> `archived_at` and the auto path still fires at `published_at + 120 d` = 4 months,
> exactly as documented). **One prerequisite the auditor missed:** `IX_ads_delete_sweep`
> is `(status, archived_at) WHERE status='archived'`, so keying the sweep on
> `published_at` silently drops the index. A new partial index
> `(status, published_at) WHERE status='archived'` is part of the fix, not an
> optimisation. Note the code is not "wrong" so much as *outvoted*: `db-retention.md:30`
> agrees with the code; US-S7:51-53, US-A5:64-65 and decision J:156 agree with each
> other and against it. This is a documentation-vs-code conflict needing an owner call,
> and it is shared with AD-009 and AD-007.

---

### MEDIUM

#### AD-006: [MEDIUM] — Seller-scoped photo dedup returns another ad's row

> **Validation Note:** confirmed unchanged. Reproduced: with the photo attached to adB,
> `create_or_skip(ad=adA, image=<same key>)` returns **adB's row** (`returned row for
> adA: pk=6 ad=11`, where `adA id=10, adB id=11`); adA ends with **0 photos**, adB with 1.
> `submit_ad` ignores the return value, so the ad then fails `min_images = 1` and the
> seller is told "Ad failed moderation. Please check your content and try again." —
> a message that points at their text, not at the invisible photo problem. Severity
> held at MEDIUM (not upgraded to the rubric's HIGH "photo count violated" bucket)
> because the trigger requires the seller to deliberately submit a byte-identical file
> to a second ad; the *system* does not violate the invariant on its own.

#### AD-008: [MEDIUM] — `ON_MODERATION` is never a durable state

> **Validation Note:** reclassified **Maintainability → SPEC-DEVIATION**. Severity held
> at MEDIUM but the impact is materially larger than reported. The finding is real and
> reproduced: after both a passing and a failing `submit_ad`, **0 rows are committed in
> `ON_MODERATION`**; `get_pending_queue_size()` returns **0**; the seller dashboard's
> "On Moderation" bucket is **0**. A grep of every `transition_to(AdStatus.ON_MODERATION)`
> call site finds exactly **two production writers** — `submission.py:230` and
> `edit.py:338` — and both call `auto_moderate()` in the same transaction. What makes
> this a *specification* deviation rather than a cleanliness issue is that four
> documents promise the state exists: **US-S2:38-39** ("On submit → `ON_MODERATION`,
> not visible until checks pass"), **US-A12:90-93** (priority queue), **US-A13:95-98**
> ("pending queue size"), and `db-enums.md:28` ("awaiting auto-check (hidden)") — plus
> decision Q in the technical specification. The real cost is **VAL-003**: the whole
> human approval path is unreachable. Do not action the auditor's "drop `ON_MODERATION`
> from the durable set" branch before VAL-003 is resolved — that branch deletes the
> queue the business asked for in US-A12.

#### AD-009: [MEDIUM] — Price/photo-only edit does not restart the auto-archive clock

> **Validation Note:** confirmed unchanged, and **stronger than reported** — the spec
> names the mechanism. Reproduced: price-only POST → `published_at unchanged? True`,
> `updated_at bumped? True`. `db-schema.md:146` says `published_at` is "UPDATED on every
> PUBLISHED transition (timer reset)" and **decision J:156** says explicitly that
> `published_at` updates on every transition to `PUBLISHED` "*(incl. reactivation,
> **price/photo edits**)* — this is the 'timer reset on edit'". The deviation is
> therefore unambiguous, not a wording ambiguity. **Implementation constraint the auditor
> missed:** `ALLOWED_TRANSITIONS[PUBLISHED] = {ARCHIVED, ON_MODERATION}` — there is
> **no `PUBLISHED → PUBLISHED` edge** (verified), so "`transition_to(PUBLISHED)` on a
> price edit" raises `ValueError`. The fix needs either a new matrix edge or an
> explicit timer-bump service, and it should land together with AD-013 (hoist the
> matrix) and AD-011 (uniform timestamp clearing) or it will be re-implemented three
> different ways.

#### AD-010: [MEDIUM] — Bulk-moderation JSON API: no transaction, no row lock, errors swallowed

> **Validation Note:** adjusted — **root cause refuted, finding narrowed.** The quoted
> evidence block does not exist in the file: the real `api_bulk.py:69-88` has no `ban`
> branch (the shipped `BulkModerationAction` StrEnum is exactly
> `['approve', 'reject', 'flag']`), uses a `BulkModerationAction` StrEnum comparison
> rather than string equality, and — decisively — **already delegates to the service**:
> `approve_ad` and `reject_ad` are imported from `apps.moderation.admin_actions`
> (verified at runtime: `api_bulk.approve_ad.__module__ == 'apps.moderation.admin_actions'`).
> There is therefore **no duplicated implementation**, and the recommendation "delete
> the loop and call `bulk_approve`/`bulk_reject`" is **unexecutable** — those take a
> `QuerySet`, not an id list. Strike the root cause and the recommendation. What
> survives, and was reproduced: `Ad.objects.get(id=ad_id)` with no
> `select_for_update()` and no wrapping `transaction.atomic()`; the state machine's own
> `ValueError` is caught by a bare `except Exception`, logged at **ERROR**
> (`Bulk moderation failed for ad 27: Invalid transition: archived -> rejected. Allowed
> targets from archived: published, on_moderation`) and returned to the operator as
> `{"completed": 0, "errors": [{"id": 27, "error": "Processing failed"}]}` — a 200 with
> no indication of cause, on what is ordinary user input. The `FLAG` branch calls
> `PriorityService().calculate_and_save(ad)` outside any transaction. Severity held at
> MEDIUM (rubric: "missing transaction around transition").

#### AD-011: [MEDIUM] — `archived_at` is not cleared on `ARCHIVED → PUBLISHED`

> **Validation Note:** adjusted — **claim confirmed, evidence replaced.** Reproduced:
> after `ARCHIVED` then `→ PUBLISHED`, `archived_at` is still set on a **live** ad, and
> `Ad.objects.filter(...).update(archived_at=None)` on a `PUBLISHED` row is **accepted
> by the database** — the timestamp constraints are one-directional, exactly as the
> finding argues. But the finding's evidence quote is **not the shipped code**: it shows
> a `timestamp` local and a `PUBLISHED` branch that nulls `moderated_by` and
> `moderation_failed_at`. The real branch (`models.py:448-461`) does neither — it sets
> `published_at`, sets `original_published_at` once, and sets `published_by` when a
> moderator id is supplied. The finding's *Problem* text repeats the same error ("entering
> `PUBLISHED` only nulls `moderated_by` and `moderation_failed_at`"). The **conclusion is
> unaffected** — `archived_at` is genuinely never cleared — but any implementer following
> the quoted evidence would be editing code that does not exist. Severity held at MEDIUM
> rather than the rubric's HIGH "missing side-effect on transition" because there is
> **zero observable harm today** (verified: only `delete_sweep` reads `archived_at`, and
> it also filters `status = ARCHIVED`); the finding itself says so. The auditor's
> recommended bidirectional test in `apps/ads/tests/test_ad_constraints.py` is the
> right addition.

#### AD-012: [MEDIUM] — `ad_copy` renders the raw driver error into the seller's chat

> **Validation Note:** adjusted — **re-scoped.** The single-DRAFT-invariant half
> duplicates **DB-009** and is merged there. Retained here is the half no other phase
> owns, and it is the more serious one: reproduced live — with a DRAFT open,
> `copy_ad` raises `IntegrityError` whose text is
> `duplicate key value violates unique constraint "uq_ads_single_draft_per_user" DETAIL:  Key (user_id)=(6) already exists.`,
> and `ad_copy.py:59-61` formats that straight into the Telegram reply
> (`_("Failed to copy ad: {error}").format(error=e)`) — a table name, a constraint name
> and internal schema detail delivered to the seller (**CWE-209**). The same bare
> `except Exception` also swallows a permission error and a missing ad behind one
> untranslatable, un-actionable key, which is an i18n/tone failure as well. The fix
  (make `create_draft_ad` the single DRAFT entry point, and catch the specific
  conditions) stands.

#### AD-016: [MEDIUM] *(new — split from AD-007)* — An expired draft is reported to the seller as a moderation failure, and the dialog is destroyed

> **Validation Note:** new — extracted from AD-007 because it is a different file, a
> different failure, and a different fix. Reproduced: after `sweep_drafts` removes the
> row, `submit_ad` returns `(False, ["Ad not found"])`, and
> `telegram_bot/handlers/ad_create/submit.py:94-99` renders **every** non-success as
> `_("Ad failed moderation. Please check your content and try again.")` followed by
> `await state.clear()`. Three distinct outcomes — content genuinely failed the check,
> the draft was swept underneath the seller, and the translation layer itself failed —
> are collapsed into one message that names the wrong cause and then throws away the
> FSM state so the seller cannot retry. Fix by giving `submit_ad` a distinguishable
> return for "draft no longer exists" and rendering a recoverable "your draft expired,
> run /post again" instead of blaming the content. i18n is part of the DoD: the new
> string needs non-empty `ru` and `bs` `msgstr`.

---

### LOW

#### AD-013: [LOW] — The transition matrix is a method-local dict

> **Validation Note:** confirmed unchanged. Verified: `hasattr(apps.ads.models,
> "ALLOWED_TRANSITIONS")` is `False`; the matrix is a 15-line literal rebuilt on every
> `transition_to()` call. The matrix itself is **correct** — driving `transition_to`
> from every source raised `ValueError` exactly where the source is terminal, and
> `ON_MODERATION_FAILED → PUBLISHED` is correctly refused. Not rejected as
> "refactoring for its own sake": it is a zero-behaviour-change extraction that the
> project rules explicitly ask for ("fixed value sets … Keep them separately in
> models"), and it is a **prerequisite for AD-009's fix** (§2.3 dependency 2). Sequence
> it with AD-009 and AD-011, not after them.

#### AD-014: [LOW] — `AdImage.position` has no uniqueness or contiguity constraint

> **Validation Note:** confirmed unchanged. Verified by introspection:
> `AdImage.unique_together == ()` and `constraints == ['ck_ad_images_image_key_format',
> 'ck_ad_images_thumb_small_key_format', 'ck_ad_images_thumb_medium_key_format',
> 'ck_ad_images_thumb_large_key_format']`. The invariant holds today only because the
> sole production writer derives positions from a list. Adding
> `unique_together = (("ad", "position"),)` plus a migration is cheap and removes a
> whole class of future gallery-ordering bugs; gaps should be documented as permitted,
> as the finding itself recommends.

#### AD-015: [LOW] — `ads_auto_publish=False` does not hide the seller's published ads

> **Validation Note:** adjusted — **evidence corrected.** Reproduced: with
> `ads_auto_publish=False`, `can_publish_ad(user)` is `False` **and** the ad **is still
> in the public queryset**; flipping `is_declined=True` hides it. So the substance
> stands. But the finding's claim that the flag is "exposed in
> `UserAdmin.list_display`/**`list_editable`**" is false: `UserAdmin` never sets
> `list_editable`, so it is the empty `ModelAdmin` default. The real exposure is that
> `UserAdmin` declares no `fields`, `fieldsets` or `exclude` (verified: all three
> `None`), so Django auto-builds a `ModelForm` containing `ads_auto_publish` as an
> editable field on the change page. The recommendation stands, and the "derive a single
> visibility predicate from `AccountState`" half is the right shape — `AccountState`
> already carries all five flags and already has `can_publish_ad`; it simply has no
> `is_ads_visible` counterpart.

---

## Deprecated / Superseded Findings

`AD-005` and `AD-007` are superseded by Phase 03 (`DB-001`, `DB-003`). `AD-012` is
partially superseded by `DB-009`. No finding was withdrawn on its own merits.

---

## R4 — Validation-Level Findings (`VAL-`)

### VAL-001: Audit IDs `AD-001` and `AD-002` are already hard-coded in shipped source and docs, referring to a *different* prior cycle

- **Severity:** HIGH (remediation hazard, not a runtime defect)
- **Evidence.** `AD-001` appears in **7 source locations** and **10 documentation
  locations** in the repository, all describing earlier-cycle findings:
  `apps/ads/models.py:407` ("manual review of auto-failed ads (AD-001)"),
  `apps/ads/models.py:430`, `apps/users/services/deletion.py:211`,
  `docs/02-database/db-indexes.md:88` and `:99`, `docs/02-database/db-schema.md:173`,
  `:178` and `:181`. `AD-002` appears in
  `apps/core/management/commands/archive_sweep.py:68` and `:71`,
  `apps/moderation/services/auto_moderation.py:209`,
  `apps/moderation/services/moderation_log.py:218` and `:241`,
  `docs/02-database/db-retention.md:20` and `:49`. `AD-005` appears in
  `docs/02-database/db-schema.md:148`.
- **Why it matters.** An implementer who greps `AD-001` in `models.py` will find a
  comment about manual review of auto-failed ads and conclude the wrong thing. The
  audit-ID namespace is not unique across cycles, so **the remediation tracker must be
  keyed on `05-ad-lifecycle-AD-00N`**, not on `AD-00N`. The same hazard was independently
  found for the `04-AUT-00N` series (`VAL-002` in
  `.ai/audit/99-validation/04-auth-login-validated-findings.md`); this is the same class
  of problem, now confirmed for the ad-lifecycle series.
- **Related:** the phase-04 validator's `VAL-004` finding (plain-text `password` field in
  `UserAdmin`) was **independently corroborated** here: introspecting
  `UserAdmin`'s live change form returns a `password` field rendered with
  `AdminTextInputWidget`, alongside editable `is_banned`, `is_staff`, `is_superuser`.

### VAL-002: The test suite fabricates `ON_MODERATION` rows the system can never produce — 34 call sites in 10 files

- **Severity:** HIGH (rollout-safety blocker for AD-008)
- **Evidence.** `grep -rn "status=AdStatus.ON_MODERATION)"` returns **34 call sites
  across 10 files**, all of them tests that build the state directly through
  `create_test_ad(..., status=AdStatus.ON_MODERATION)` or an explicit
  `transition_to(ON_MODERATION)`.
- **Why it matters.** This is why all 32 of the auditor's checks passed while the
  production invariant was broken. A large part of the moderation test surface —
  `test_moderation_views.py`, `test_moderation_side_effects.py`,
  `test_admin_actions.py`, `test_moderation_log.py`,
  `test_approve_ad_side_effects.py` — is green **against a state that cannot occur**.
  Whichever way AD-008 is resolved, those 34 sites must be rewritten to reach the state
  through the real path, or the fix will be "validated" by tests that cannot fail.
  This is the single largest piece of work AD-008 carries and it is invisible in the
  auditor's `Effort: M`.

### VAL-003: Because `ON_MODERATION` is never committed, the entire human approval path is dead code

- **Severity:** HIGH — **the real cost of AD-008, and an architectural finding in its own right**
- **Evidence (runtime).**

| Surface | Gate | Result |
|---|---|---|
| `AdAdmin.action_approve` → `bulk_approve` | `queryset.filter(status=ON_MODERATION)` (`admin_actions.py:162`) | Returns **0** — the changelist can only ever report "Approved 0 ad(s)". Verified. |
| `POST /moderation/review/<id>/approve/` | `get_object_or_404(..., status=ON_MODERATION)` (`review.py:75`) | **HTTP 404.** The Approve button on the review page is dead. Verified against a freshly auto-failed ad. |
| `admin_actions.approve_ad(ad, …)` | `if ad.status != ON_MODERATION: return False` (`admin_actions.py:43`) | Returns **`False`** for every real ad. Verified. |
| `GET /moderation/review/<id>/` (detail) | `status__in=[ON_MODERATION, ON_MODERATION_FAILED]` | **HTTP 200** — reachable, but only to show ads that already failed the gate. |
| `GET /moderation/queue/` | `PriorityService.get_queued_ads` filters both statuses | 200, but lists only auto-failed ads. |

- **Consequence.** The business bought a moderation queue (decision Q, US-A12, US-A13)
  and a manual-approval capability, and shipped a control panel for a queue that is
  never populated by a passing ad and a approve button that never approves. Combined
  with AD-001 — the only way to publish is a raw form write with no audit row — the
  effective moderation model in production is "auto-gate for rejects, unlogged form
  writes for publishes". This must be stated explicitly to the owner: the two findings
  are the two halves of the same hole.
- **Related:** AD-008, AD-001.

### VAL-004: AD-003 must be split before Phase 07 executes, and its two remediations are mutually exclusive

- **Severity:** MEDIUM (cross-phase conflict — pre-emptive)
- **Detail.** See §2.2. The `pre_delete` receiver assumes exclusive key ownership; the
  ads layer assumes shared keys. Only one of the two can be changed first, and the
  choice determines whether the other is a one-line or a whole-layer change.
  **Phase 07 must own the "how many `AdImage` rows may reference one storage key?"
  invariant**, and phase 05's AD-003 keeps the `copy_ad` half. If phase 07 ships a
  refcounting `pre_delete` while AD-003's option (a) "copy the bytes" is also
  implemented, the project pays for both and gains nothing.

### VAL-005: AD-004 + AD-007 + AD-009 are one decision wearing three hats

- **Severity:** MEDIUM (rollout ordering)
- **Detail.** All three anchor a retention clock to the event that *created* the state
  rather than the event that made the seller care: `published_at` (publish, not edit),
  `archived_at` (archive, not publish), `created_at` (dialog start, not last activity).
  They also disagree with each other about where the truth lives:
  `db-retention.md:30` says `archived_at`, US-S7/US-A5/decision J say `published_at`.
  Fixing them independently produces three partial notions of "last seller activity" in
  three different files. **Recommended order:** (1) one owner decision on the retention
  anchor, (2) reconcile `db-retention.md` with the user stories, (3) then AD-013 +
  AD-011 (matrix + uniform timestamp clearing), (4) then AD-009 and AD-004, (5) then the
  new partial index for AD-004, (6) DB-003/AD-016 for the draft side.

### VAL-006: One architecture decision gates five findings, and it has not been made

- **Severity:** MEDIUM (owner decision, rollout-safety)
- **Detail.** AD-001, AD-008, AD-010, AD-011 and VAL-003 are all downstream of a single
  unanswered question: **is a moderator allowed to move an ad's status, and if so
  through which seam?** Today the answer is "yes, and through a raw form write". Every
  one of those five findings is a symptom of the absence of a single write path for ad
  lifecycle state. The auditor's own closing note ("The state machine is small, correct
  and well covered; it needs a caller's discipline, not more abstraction") is the right
  instinct, but the *specific* missing thing is not discipline — it is one owner for
  the write. Resolving this first makes AD-001, AD-010 and (part of) VAL-003
  near-trivial and prevents three teams writing three different guards.

---

## Rollout Analysis (R4)

**Rollout-safety blockers**

1. **AD-008's fix is blocked by VAL-002.** Any resolution requires rewriting 34 test
   call sites in 10 files that currently fabricate an unreachable state. Budget for the
   test migration, not just the code change.
2. **AD-001's fix must not land before the owner decision (§4).** Making `status`
   read-only removes the only working *publish* path a moderator has (the `action_*`
   buttons are dead per VAL-003). If AD-001 is actioned first without resolving VAL-003,
   moderators lose the ability to publish at all. **Order: owner decision → fix
   `bulk_approve`/the review view (or confirm the async-queue design) → then make
   `status` read-only.**
3. **AD-003 must not be actioned before Phase 07 decides the ownership invariant**
   (VAL-004) — the two fixes are mutually exclusive.
4. **AD-009 cannot be patched in isolation** (§2.3 dependency 2): the naive fix raises
   `ValueError` because there is no `PUBLISHED → PUBLISHED` edge. Ship it with AD-013.

**Hidden dependencies**

- AD-004's fix silently loses `IX_ads_delete_sweep` unless a new
  `(status, published_at) WHERE status='archived'` index ships with it.
- AD-011's model fix is bypassed while AD-001 is open (an admin form write never goes
  through `transition_to`).
- AD-002's fix interacts with VAL-006: if a single lifecycle write path is introduced
  first, the `ON_MODERATION_FAILED` resubmission has exactly one place to live.

**No circular dependencies** were found among the phase-05 findings themselves.

---

## Execution Validation

| Item | Status |
|---|---|
| All 15 findings still applicable at anchor `9e96b84` | **Yes** — 0 stale, 0 already-implemented, 0 duplicates within the phase |
| Semantic (not line-based) targets used | Yes — `Ad.transition_to`, `AdAdmin.readonly_fields`, `AdImageService.create_or_skip`, `copy_ad`, `create_draft_ad`, `bulk_approve`, `get_pending_queue_size`, `get_queued_ads` |
| Repository files modified | **None.** `git status --porcelain` shows only untracked `.ai/audit/**` artifacts |
| Scratch artefacts | `audit05v_probe` database dropped; all probe scripts under `.ai/tmp/` deleted |
| Other auditors' databases / dev stack | Untouched |
| Static gates re-run | `ruff check` over the phase scope → **All checks passed**. `basedpyright` over the phase scope → **12 errors, 0 in production** (see below) |
| **R-26 correction** | The auditor reported "4 pre-existing errors, all in `apps/moderation/tests/test_admin_actions.py`". The true figure over the same scope is **12 errors in 2 files** — 8 in `apps/ads/tests/test_edit_views_locking.py` (lines 239, 247, 292, 300) and 4 in `apps/moderation/tests/test_admin_actions.py` (lines 529, 538). All are the same `reportGeneralTypeIssues` complaint about the untyped `advisory_lock` context manager and all are **test-only**. The auditor's *conclusion* (production clean) is correct; the *count and file list* must be corrected, and this matches the phase-01 validator's independent count of 14 for the whole-repo scope. |

---

## Documentation gaps (re-verified)

| # | Gap | Owner |
|---|---|---|
| 1 | **No document states whether a moderator may set `status` directly.** US-A3 authorises it, US-A10 constrains only the *automatic* gate, `technical-specification.md:42-45` grants the moderator unpublish/review powers, and nothing says the admin change form is a supported surface. This is the §4 owner decision. | AD-001 |
| 2 | `ON_MODERATION` documented as an occupied state in four places while never committed | AD-008 / VAL-003 |
| 3 | `db-retention.md:30` vs US-S7/US-A5/decision J on the ARCHIVED clock | AD-004 / VAL-005 |
| 4 | `db-retention.md:67-68` still contains the duplicated fragment "`deleted_at` is older than `deleted_at` is older than 120 days" — confirmed still present, purely cosmetic, confirmed by the auditor | fold into AD-004's file list |
| 5 | `db-schema.md:146` promises `published_at` is "UPDATED on every PUBLISHED transition (timer reset)" and decision J:156 extends that to "price/photo edits"; the code does neither | AD-009 |
| 6 | `db-schema.md:147` and the model `help_text` both declare `original_published_at` "IMMUTABLE" while the admin form makes it editable | AD-001 |
| 7 | Search-vector trigger DDL is created by `setup_search_triggers`, not by a migration — the auditor flagged this and it remains **correct** and correctly deferred to the database/operations phases | deferred, not re-filed |
| 8 | **New.** `docs/02-database/db-indexes.md:88` and `:99`, `db-schema.md:173/178/181`, `db-retention.md:20/49`, `db-schema.md:148`, plus 7 source comments, carry audit IDs that collide with this cycle's IDs | VAL-001 |

---

## Warnings

- **Architectural.** Five findings (AD-001, AD-008, AD-010, AD-011, VAL-003) are one
  symptom: there is no single owner for a lifecycle-status write. The state machine is
  correct; what is missing is one write path, not more abstraction.
- **Test fidelity.** The suite is green against a state the system cannot reach
  (VAL-002). Green here does not mean correct — treat any AD-008 remediation as
  unvalidated until the 34 fabrications are replaced.
- **Maintainability.** `Ad.transition_to` clears timestamps per *target* status rather
  than per *source* status, so the invariant is expressed 7 times in one method
  (AD-011) and the matrix itself is invisible outside the method body (AD-013). Both
  are small, pure refactors, and both are prerequisites for AD-009.
- **Rollout.** The single largest risk in this report is shipping AD-001's
  `status` → read-only before VAL-003 is resolved: moderators would be left with no
  working publish path at all.
- **Cross-phase.** AD-005 and AD-007 must not be re-shipped alongside `DB-001`/`DB-003`;
  AD-012's DB half must not be re-shipped alongside `DB-009`; AD-003 must be split
  before phase 07 runs.
- **Documentation.** Every authoritative document about the ARCHIVED clock disagrees
  with another authoritative document. Until an owner picks one, AD-004's "correct
  behaviour" is undefined and any fix is a guess.

---

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 7 | AD-001, AD-002, AD-004, AD-006, AD-009, AD-013, AD-014 |
| Reclassified | 1 | AD-008 (Maintainability → SPEC-DEVIATION) |
| Adjusted | 6 | AD-003, AD-010, AD-011, AD-012, AD-015, and AD-001 (type + framing) |
| Merged | 2 | AD-005 → DB-001; AD-007 → DB-003 |
| Rejected | **0** | — |
| New | 1 | AD-016 (split from AD-007) |
| VAL- | 6 | VAL-001 … VAL-006 |

**Post-validation severity:** 1 CRITICAL · 4 HIGH · 8 MEDIUM · 3 LOW (+ AD-016 counted in
the 8 MEDIUM; AD-005 and AD-007 removed, their content living in Phase 03).

### Rejected Findings

None. Every finding survived independent re-derivation; six required narrowing and two
were cross-phase duplicates, but no finding was stale, already implemented, or
speculative.

### Merged Findings

| Original ID | Merged Into | Rationale |
|-------------|-------------|-----------|
| AD-005 | `DB-001` (Phase 03, CRITICAL) | Same function, same lines, same mechanism, same exception. DB-001 reproduces it from 6 threads and supplies the in-repo savepoint precedent (`telegram_bot/handlers/login.py:227-240`). Shipping both = two patches for one line. |
| AD-007 (sweep half) | `DB-003` (Phase 03, HIGH) | Same root cause (draft lifetime measured from `created_at`) and DB-003 already carries the `submit_ad` recoverability recommendation. |
| AD-012 (DB half) | `DB-009` (Phase 03, MEDIUM) | Same defect (a second DRAFT writer that ignores `uq_ads_single_draft_per_user`). The bot-facing CWE-209 half is unique and retained here. |

### Reclassified Findings

| ID | Original Type | New Type | Rationale |
|----|---------------|----------|-----------|
| AD-008 | BEST-PRACTICE (Maintainability) | **SPEC-DEVIATION** | Four documents promise a durable `ON_MODERATION`: US-S2:38-39, US-A12:90-93, US-A13:95-98, `db-enums.md:28`, plus decision Q. The code never commits it, and VAL-003 shows the consequence is a dead control surface, not a tidy-up. |

### Evidence corrections (evidence that must not be carried forward)

| Claim in the auditor's report | Truth |
|---|---|
| R-26: "4 pre-existing basedpyright errors, all in `test_admin_actions.py`" | **12 errors in 2 files** (8 in `test_edit_views_locking.py`, 4 in `test_admin_actions.py`), all test-only. Conclusion unchanged, count and file list corrected. |
| AD-010 evidence block for `api_bulk.py:69-88` | The quoted code **does not exist**. No `ban` branch; a `BulkModerationAction` StrEnum is used; and the endpoint already imports `approve_ad`/`reject_ad` from `admin_actions`. Root cause and recommendation struck. |
| AD-011 evidence block for `models.py:446-462` | The quoted code **does not exist**. The shipped `PUBLISHED` branch nulls neither `moderated_by` nor `moderation_failed_at`. Conclusion survives; quote replaced. |
| AD-015: "exposed in `UserAdmin.list_display`/`list_editable`" | `UserAdmin` never sets `list_editable`. The real exposure is the auto-generated `ModelForm` (no `fields`/`fieldsets`/`exclude`). |
| AD-001: "the DB check constraints do not even fire" | They **do** fire — as uncaught HTTP 500s for `REJECTED` and `ON_MODERATION_FAILED`. |
| AD-001: "route manual publish through `approve_ad()` → `auto_moderate()`" | Would re-apply automatic criteria to a human decision and fail an approve the moderator deliberately made. Recommend against. |
| AD-008: R-16 "priority queue rows: 2" | The queue works for `ON_MODERATION_FAILED`; `get_queued_ads()` returned 1 in the reproduction. The `ON_MODERATION` half is the dead one, and so is the whole approve path (VAL-003). |

---

## CRITICAL / HIGH items that genuinely require an architectural or structural change

| ID | Why a patch is insufficient |
|----|-----------------------------|
| **AD-001** (CRITICAL) | The fix is not "add fields to `readonly_fields`". It needs (a) one sanctioned write path for lifecycle state, (b) an `AdAdmin.save_model` override or equivalent that routes through it and writes a `ModeratorActionLog` row, and (c) an **owner decision** about whether moderators may change status at all (US-A3 vs US-A10). Plus a *structural* consequence: making `status` read-only is unsafe until VAL-003 is fixed, because `bulk_approve` and the review view currently cannot approve anything. |
| **AD-003** (HIGH) | The storage layer's ownership model is undefined: nothing states how many `AdImage` rows may reference one key. Choosing "one owner" or "N owners" is a structural decision that changes `pre_delete`, `copy_ad`, the orphan sweep's `_collect_referenced_keys`, and the staging→permanent promotion path. Cross-phase (VAL-004). |
| **AD-004** (HIGH) | Requires a data-model/index change (a new retention anchor or a new partial index) plus a documentation reconciliation across three documents that currently disagree. Not a filter tweak. |
| **AD-002** (HIGH) | Requires a product decision — either a new `ON_MODERATION_FAILED → ON_MODERATION` matrix edge (which is a deliberate loosening of a rule the state machine enforces on purpose) or a UI change that stops advertising an edit that cannot succeed. The current catch-all branch is reached by five of seven statuses, so the structural fix is an allow-list plus a state-owner, not another branch. |
| **DB-001** (via merged AD-005, CRITICAL) | Carried in Phase 03. Not a patch either: the correct fix (savepoint + a real serialiser such as `select_for_update` on the user row or an advisory lock) changes the concurrency contract of the bot's only draft-creation path. |

**Not structural** (safe as focused patches): AD-006, AD-009 *(once the matrix edge
exists — ship with AD-013)*, AD-010, AD-011, AD-012, AD-013, AD-014, AD-015, AD-016.

---

## Required Fixes

1. **Obtain the owner decision on AD-001 / §4** before any code changes to
   `AdAdmin`. Record it in `docs/04-user-stories/admin-stories.md` (US-A3) so the next
   reader knows whether a moderator may publish from the admin.
2. **Sequence AD-001 strictly after VAL-003** (or land both together).
3. **Fold AD-005 and AD-007 into `DB-001` and `DB-003`;** ship no duplicate patch.
4. **Split AD-003 and publish the storage-key-ownership decision to Phase 07 before it
   executes** (VAL-004).
5. **Correct the four evidence blocks** listed in the evidence-corrections table before
   this report is used as an implementation input.
6. **Record the AD-001/AD-002 audit-ID collision** (VAL-001) and key the remediation
   tracker on `05-ad-lifecycle-AD-00N`.
7. **Budget the VAL-002 test migration** (34 sites, 10 files) as part of AD-008, not
   after it.

## Advisory Recommendations

- Fix AD-013 and AD-011 as pure refactors *first*: they are zero-risk, they make the
  matrix inspectable, and they are prerequisites for AD-009 and for a clean AD-001
  fix.
- Give `AccountState` an `is_ads_visible` predicate (AD-015) — `can_publish_ad` already
  exists there, so the visibility rule gets one owner instead of a second ad-hoc filter.
- In `AdAdmin`, drop the four `search_vector*` fields from the form for hygiene even
  though the trigger neutralises them; a form field that silently discards input is a
  future trap.
- Consider a `status` + `archived_at` consistency `CheckConstraint` (the reverse of the
  existing one-way constraints) — it is cheap and would have caught AD-011 at write time.

---

## Checkpoint 3 — Per-finding validation

- **Stage:** Per-finding validation
- **Findings in scope:** 15 in, 14 out (AD-005 and AD-007 merged away) + AD-016 new
- **Decisions:** Validated unchanged 7 · Reclassified 1 · Adjusted 6 · Merged 2 · Rejected 0 · New 1
- **Evidence anchor:** this file (self-contained — no live source reads required)
- **Dependencies / blockers:** 3 rollout blockers (§Rollout Analysis)
- **Checkpoint status:** closed

## Checkpoint 4 — Final consistency audit

- **Stage:** Final audit
- **Pipeline integrity:** OK. Every ID `AD-001` … `AD-016` has an explicit verdict; no
  finding was silently dropped; both merges name their absorbing target; the six
  `VAL-` findings are recorded separately from source-code defects as the handbook
  requires.
- **Isolation:** `audit05v_probe` dropped; `.ai/tmp/` probe scripts removed; no
  repository file created or modified.
- **Checkpoint status:** closed
