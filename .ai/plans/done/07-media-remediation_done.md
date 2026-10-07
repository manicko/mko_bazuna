---
plan_id: "07-media-remediation"
phase: "07"
phase_name: "Media Storage, Serving & Photo Lifecycle"
source_report: ".ai/audit/99-validation/07-media-validated-findings.md"
source_findings: ".ai/audit/07-media/findings.md"
date: "2026-09-29"
planner: "Planner (subagent)"
anchor_commit: "aa2a6b0"
report_anchor_commit: "9e96b84"
status: "planned"
findings_in_scope: 12
findings_open: 11
findings_partial: 0
findings_merged_away: 1
findings_rejected: 0
blocks: 12
---

# Execution Plan — Phase 07 Remediation (Media Storage, Serving & Photo Lifecycle)

## 0. Header, provenance and scope statement

### 0.1 Provenance

| Item | Value |
|---|---|
| Source report | `.ai/audit/99-validation/07-media-validated-findings.md` (validated, 1442 lines) |
| Source findings file | `.ai/audit/07-media/findings.md` — **deleted from the working tree** (tracked deletion). Recorded for traceability only; **not** an input, and **not** a problem to fix. No block may restore it. |
| Report anchor commit | `9e96b84` (recorded in the report metadata — **stale**) |
| Code-context document | `.ai/tmp/code-context-phase07.md` (707 lines, Auditor) |
| **Working anchor commit for this plan** | **`aa2a6b0`** (`git rev-parse --short HEAD`, taken before writing) |
| Date | 2026-09-29 |
| Findings in scope | 12 (`MEDIA-001` … `MEDIA-012`) + 6 validation-level items (`VAL-001` … `VAL-006`) |
| Verdicts in the source report | Confirmed unchanged 3 · Adjusted 4 · **New 1** (`MEDIA-012`, auditor miss) · **Merged 1** (`MEDIA-003` → `03-DB-005`) · Rejected 0 |
| State at the anchor | **0 already fixed · 11 still open · 0 partial · 0 rejected · 1 merged out** |
| Validated severity split | **0 CRITICAL · 4 HIGH** (`MEDIA-001`, `002`, `004`, `012`) **· 5 MEDIUM** (`005`, `006`, `007`, `008`, `009`) **· 2 LOW** (`010`, `011`) |
| Phases 01/02 effect on media | **None.** No media file, setting, migration or template was touched by either phase |
| Execution blocks | 12 (11 code/config/doc, 1 of them split into a service half and a bot-wiring half) |
| Implementor concurrency | 1, strictly sequential (project rule: only one implementor at a time) |

**Naming convention used by this plan.** Every citation of this phase's own findings is
**cycle-scoped `07-MEDIA-0NN`**, never bare `MEDIA-0NN`. `VAL-003` is load-bearing on this:
shipped source already contains `HIGH-001`, `MED-001`, `MED-002`, `MED-003`, `MED-008` and
`ME-003` as markers from *prior* audit cycles (`apps/core/tests/test_ad_image_delete_signal.py`,
`apps/ads/tests/test_copy_ad.py`, `apps/media/tests/test_filesystem.py`,
`telegram_bot/services/ad_data/media.py`). `MED-` already means the *07* phase inside
shipped source comments. Bare `MEDIA-0NN` in a comment, docstring, tracker entry or commit
message is ambiguous and is forbidden.

**The ownership decision is already published and is not this plan's to reopen.** The
validated report answers the question phase 05 reserved to phase 07: a storage key may be
referenced by **N ≥ 1** `AdImage` rows, and bytes are freed **only when the last referencing
row goes away**. Phase 05's `AD-003` is **RETIRED**; the byte-copy branch is forbidden. See
§5.4. BLOCK 2 implements the decision; it does not re-derive it.

---

### 0.2 Evidence basis — read this before executing any block

Two narrative inputs plus the tree. They do not fully agree with each other, and in **six**
places the report's own supporting claim does not survive contact with the tree.
**The tree at `aa2a6b0` is the authority.** Where they disagree, the disagreement is
recorded here, and the plan is built on the tree's answer.

#### 0.2.1 Corrections to the report — the tree wins

| # | Claim | Report says | **Tree at `aa2a6b0` says** | Consequence for this plan |
|---|---|---|---|---|
| **C-1** | `MEDIA-001` evidence #3: the seed manifest's default pool is "injected into every category's key map", so cross-category key sharing is *guaranteed at volume* | 1004 distinct filenames across 1004 entries; default pool injected into every category; cross-ad **and** cross-user collisions guaranteed | **The `default.photos` array in `apps/seed/fixtures/images/photo_manifest.json` is EMPTY.** 1004 entries, **1004 distinct filenames, 0 filenames listed twice, 205 categories.** The `generate()` loop that pushes the default pool into every `category_key_map` is real but **inert** with the shipped manifest. Cross-**category** sharing does not occur. Cross-ad, cross-owner sharing **within** a category is real and is the dominant shape (~4.9 keys per category, 1–3 drawn per ad, different owners) | The **invariant** (N references, free on last) is unaffected — it is forced by `copy_ad` and by the schema. Only the **reach narrative** is overstated. BLOCK 10 must not write the default-pool story into any document, and no block may "simplify" the seed path on the assumption that cross-category sharing exists |
| **C-2** | `MEDIA-002`: "Expect `apps/ads/tests/test_ad_image_service.py` (and any test asserting cross-ad dedup) to require rewriting" | a test-expectation change is required | **No such assertion exists.** `TestAdImageServiceCreateOrSkip` has four tests; `::test_returns_existing_duplicate_same_user` uses the **same ad twice**, so it stays green under a re-scope to `(ad, sha256)`. No other caller in any test. **The predicted test rewrite does not exist** | `MEDIA-002`'s rollout risk drops Med → **Low**. `test_ad_image_service.py` must be left **untouched**; a new cross-ad test is *additive*. Project rule 2 ("production code is king") is **not engaged** for MEDIA-002 — the justification is `technical-specification.md`'s ≥1-photo sentence, and the **commit message must cite that, not a test** |
| **C-3** | `MEDIA-006`: "A bad `location` regex would 403 real photos and **there is no automated test for nginx** … treat as a manual gate" | no test possible | **`src/backend/tests/test_nginx_config.py` already exists** — `pytest.mark.unit`, no database, with a brace-depth `_location_block(text, location_match)` extractor and three shipped assertions on the `/metrics` block. `src/backend/tests/test_compose_contract.py` is the sibling harness | `MEDIA-006` is **not** an untestable manual gate. Both config edits are covered by string assertions in the existing harness (which reads `nginx.conf` only; extending it to `nginx.dev.conf` is a small in-pattern addition). The residual manual gate shrinks to exactly one thing: confirming the new regex does not 403 a real media key **in the deployed stack** |
| **C-4** | `MEDIA-010`: a new `AdvisoryLockId` member; the report's amendment implies `13` is free | the next free integer is 13 | **`REPAIR_BOT_USERNAME = 13` already exists** (unstaged, a concurrent phase-02 agent's work, and it will land). The next free integer is **14** — phase 06's plan already says so | BLOCK 8 must **re-read `apps/core/enums.py` immediately before allocating**, tell the coordinator first, and change `enums.py` + `advisory_lock.py`'s allocation docstring + `test_advisory_lock_ids.py` in **one commit** |
| **C-5** | `MEDIA-009`: "four documents describe the storage key" | 4 documents | **7 locations across 5 files + 2 source docstrings.** Newly identified and **not in the report's list**: `docs/04-user-stories/seller-stories.md` **US-S5 — Edit ad** ("Price/photo edits publish instantly") and `docs/ops/docker-deployment.md` ("Storage keys are UUID v4") | BLOCK 10's scope is **wider** than filed. The two newly identified files must be routed, not silently dropped (Q07-12) |
| **C-6** | `MEDIA-002` impact: a photo-less ad renders `<img src="">`, "a **broken-image icon** on the listing grid" | broken image | **Refuted on all four surfaces.** `ads/partials/ad_list.html` guards with `{% if ad.images.first %}` around the card image; `ads/detail.html` guards the whole gallery with `{% if ad.images.all %}`; `ads/dashboard.html` guards; `admin/moderation/review.html` renders an explicit `{% trans "No photos" %}` | The user-visible symptom is a **missing photo / "No photos"**, not a broken image. `MEDIA-002` remains HIGH-worthy (a published ad that violates the ≥1-photo spec sentence, plus 4 orphaned files per occurrence) but **the broken-image narrative is checkably false and must not appear in the plan, in a commit message, or in a docstring** |

#### 0.2.2 The four hazards that constrain how any block may be implemented

These are the constraints that make a naive fix wrong. Every block below carries the ones
that apply to it in its task `extra_context`.

1. **`media_gate` must not gain a filesystem check** (`MEDIA-012`). It would break a large
   block of `apps/ads/tests/test_media_security.py` — `TestMediaAccessControl` (9 tests),
   `TestMediaGateDeclinedUser` (3), `TestMediaGateThumbnailResolution` (7) and
   `TestMediaGateCacheControl` (9) all build `AdImage` rows through the
   `_create_ad_with_image` helper, which writes a physical file **only** when both
   `media_root=` and `file_bytes=` are supplied. The sharpest case is
   `TestMediaAccessControl::test_shared_seed_key_across_multiple_ads_returns_200`: two
   distinct PUBLISHED ads sharing `seed/birds_04.jpg`, asserting `200` +
   `X-Accel-Redirect`, deliberately writing **no file**. **Detection belongs in
   `sweep_orphaned_media`, not in the request path.** The report's own recommendation is
   correct and now has a hard test-based justification.
2. **`test_delete_photo_single_call.py` is the hardest constraint in the phase.** It
   monkeypatches **`apps.media.signals.delete_photo`** and asserts every storage key reaches
   it **exactly once** across six sweep/consent paths (`delete_sweep`, `purge_failed_ads`,
   `purge_rejected_ads`, `purge_deleted_ads`, `sweep_drafts`, `consent_hard_delete`,
   `withdraw_consent`) plus a `sweep_orphaned_media` control. A "skip if still referenced"
   check satisfies it (the key is simply not passed); a "check → unlink → re-check" design
   does not. `MEDIA-002`'s reclaim must therefore call
   **`apps.media.services.filesystem.delete_photo` directly**, never the re-exported
   `apps.media.signals.delete_photo`.
3. **`sweep_orphaned_media.Command.handle` is triple-claimed**: phase-03 BLOCK 8, `MEDIA-012`
   and `MEDIA-007`. `_STAGING_TTL_SECONDS` is phase-03 BLOCK 6's. The serialisation is
   stated once in §4 and repeated in §5.3.
4. **`docs/01-spec/technical-specification.md` is phase-06-reserved.** Four of
   `MEDIA-009`/`MEDIA-011`'s doc targets sit on reserved files. **Route them; do not edit.**

#### 0.2.3 Runtime re-verification required before a block relies on a claim

Cheap, and they belong to each block's Auditor pre-step, not to the Implementor:

1. `AdImageService.create_or_skip` still filters `ad__user_id=ad.user_id` and
   `submit_ad` still discards its return value (`MEDIA-002`).
2. `delete_adimage_files_on_delete` still calls `delete_photo(key)` unconditionally per key
   inside a `transaction.on_commit` closure, and is still registered by identity in
   `pre_delete._live_receivers(AdImage)` (`MEDIA-001`) —
   `apps/media/tests/test_media_config.py::test_pre_delete_signal_registered_for_adimage`
   asserts **by function identity**, so the receiver must not be renamed.
3. `generate_thumbnails` still opens each target with `O_CREAT|O_EXCL|O_WRONLY` and iterates
   `SIZES` in insertion order SMALL→MEDIUM→LARGE (`MEDIA-004`).
4. `_preprocess_one` still checks **only** the `-small` variant, and `generate()` still
   builds the three `thumbnail_*` fields from the static `_thumbnail_key` string helper
   without consulting the `ThumbnailService` return value (`MEDIA-008`).
5. `media_gate` still emits `X-Accel-Redirect` with no filesystem check on the
   `DEBUG=False` branch (`MEDIA-012`).
6. `strip_photo_exif` still passes **no** `quality=` argument, and
   `ThumbnailService.QUALITY == 85` is still an explicit class attribute (`MEDIA-011`).
7. `apps/media/admin.py` still does not exist, and `MediaDeletionError` is still absent from
   `admin.site._registry` (`MEDIA-010`).
8. **`AdvisoryLockId`'s next free integer, re-read at that moment** — `13` is taken by
   concurrent work, so `14` is the answer today and may not be tomorrow (C-4).

**No runtime claim in this plan was executed by this Planner.** No database, no test suite,
no migration, no container. Every statement above is a static read of the tree at
`aa2a6b0` plus the Auditor's and Validator's recorded findings.

---

### 0.3 Scope statement (explicit)

**In scope — 11 phase-07-owned findings.** `MEDIA-001`, `002`, `004`, `005`, `006`, `007`,
`008`, `009`, `010`, `011`, `012`. Plus **three non-finding work items** the report's
*Required Fixes* and *Advisory Recommendations* demand and that are cheap enough to be
correctly bounded:

- the **`deleted += 1` miscount** in `sweep_orphaned_media.Command.handle` (attempts counted
  as confirmed removals, folded in from `MEDIA-003` → `DB-005`'s second correction) — BLOCK 6;
- the **reconcile-store-against-database test assertion** that rubric §4.7 asks for and that
  no block else provides — BLOCK 6;
- the **`ME-003` traceability reconcile** in `apps/media/models.py`'s module docstring
  (a bare prior-cycle finding id that is not resolvable from the repository) — BLOCK 8.

**Not in scope — 1 finding.**

- **`MEDIA-003` is merged away to `03-DB-005` (phase 03, BLOCK 8).** The tree confirms the
  mechanism is present and unremediated: `submit_ad` calls `move_staging_to_permanent` **before**
  `with transaction.atomic():` and takes no `AdvisoryLockId.SWEEP_ORPHANED_MEDIA`, and
  `sweep_orphaned_media` snapshots via `_collect_referenced_keys()` then deletes
  `on_disk - referenced` with no re-check. **Phase 07 ships no staging-window fix.** Two
  obligations remain and are carried here: (i) the **revenue** side of the same diff is
  `MEDIA-012`, which **is** in scope (BLOCK 6), so the two directions of one reconciliation
  are owned by two different phases and that must be stated; (ii) `DB-005` should
  cross-reference `MEDIA-012` rather than assert that detection is impossible. **Routed
  to the coordinator** (§5.1, §5.2) — phase 07 does not edit `.ai/audit/**`.

**One finding is explicitly *not* re-filed with a narrower name.** The `MEDIA-002` /
`AD-006` overlap is resolved in §5.5: `MEDIA-002` is the higher-rated record (HIGH vs
phase 05's MEDIUM), phase 05 BLOCK 13 ships **no production code** if this plan lands first,
and phase 07 does not touch the ads-side `submit_ad` photo-count semantics that phase 05's
Q6 owns.

**One decision gate can collapse scope rather than grow it.** `Q07-6` asks whether
photo-level moderation is deliberately deferred for phase 1. The report itself says that if
it is, the honest action is a one-line doc fix, not a finding. BLOCK 11 states both branches;
**this plan does not choose** (§0.5, BLOCK 11's gate).

---

### 0.4 Severity corrections

The report's own movement is upheld in full and is **not** re-litigated:

| ID | Movement | This plan's position |
|---|---|---|
| `MEDIA-001` | CRITICAL → **HIGH** | **Upheld.** The phase rubric's CRITICAL bucket is an exhaustive four-item list this belongs to none of; the blast radius on the bot path is bounded by `copy_ad`'s own `PermissionError` on a foreign source; and `DB-005`, whose *identical user-visible outcome* requires a race, was rated MEDIUM by phase 03. Severity parity forbids rating the deterministic same-tenant case higher. **Stays P0 and still requires an architectural change** — that claim survives intact |
| `MEDIA-005` | reclassified from `SPEC-DEVIATION` to **`BEST-PRACTICE` (capability gap)** | **Upheld.** The spec's own parenthetical names *account ban* as the lever, and it is implemented and wired (`AdAdmin.actions` contains `action_ban_user`, confirmed by source). What remains is a missing capability, not a violated spec |
| `MEDIA-007` | MEDIUM held, **mechanism corrected** | **Upheld.** `/post` does **not** reset the 5-photo cap — `state.update_data` *merges*, so `photos` survives. `/cancel`'s `state.clear()` and plain walk-away are the churn vectors. The ≈2.4 GB / 2 h arithmetic is unchanged |
| `MEDIA-009` | reclassified explicitly to **`DOC-UPDATE`** | **Upheld.** The code is right (dropping `ad_id` would *reduce* unguessability, which is the actual security goal) and the docs are wrong |
| `MEDIA-011` | reclassified explicitly to **`DOC-UPDATE`** | **Upheld**, with the code half retained: the constant is a maintainability fix, the spec lines are a documentation fix |
| `MEDIA-003` | **merged out**, severity capped at `DB-005`'s MEDIUM | **Upheld** and routed. A racy deletion window is a smaller defect than a deterministic one, and the report's CRITICAL-claim chain for it is now closed |

**Corrections this Planner makes to the report's supporting detail** (none change a
finding's status, and all are load-bearing for scoping):

- **C-1** — the seed default pool is empty. The *invariant* is unaffected; the *reach
  narrative* is overstated. Do not carry it into a document.
- **C-2** — `MEDIA-002`'s predicted test rewrite **does not exist**. Its rollout risk drops
  to Low and project rule 2 is not engaged.
- **C-3** — `MEDIA-006` **is** testable; a harness already exists.
- **C-4** — the free `AdvisoryLockId` integer is **14**, not 13.
- **C-5** — `MEDIA-009`'s doc surface is **7 locations / 5 files + 2 docstrings**, not 4
  documents; two of them were never filed.
- **C-6** — `MEDIA-002`'s broken-image claim is **refuted**. Do not repeat it.

**One severity this Planner would have moved and does not.** `MEDIA-012` is filed HIGH by the
Validator as a new finding. That rating is upheld, and this plan deliberately schedules it
**third** rather than first (§4.1) even though it is the highest-ROI item in the report,
because it edits the one function that three parties claim. Being early is worth less than
being mergeable.

---

### 0.5 Open technical questions — resolved here, or explicitly gated in their block

**This plan does not choose where technical uncertainty exists.** All **fourteen** questions
the code context raises are carried forward. Each produces either a labelled
**decision required before implementation** gate inside its block, with the options and
their consequences, or a named routing to the coordinator. **Silence is not an acceptable
outcome for any of them.**

| ID | Question | Block | Who decides | Status |
|---|---|---|---|---|
| **Q07-1** | With the seed manifest's `default.photos` empty (C-1), what is the **actual** cross-user shared-key population in a seeded environment? Re-measure from the `AdGenerator` category distribution and `image_count` 1–3, not from the report's 1004-filename narrative | **BLOCK 2** (measurement) → cited by **BLOCK 10** | **Researcher**, in BLOCK 2's pre-block step | **RESOLVED 2026-10-01 — MEASURED.** Cross-user shared keys are ROUTINE: ~33% of image rows and ~55% of seeded ads at shipped defaults. See §0.6 |
| **Q07-2** | Does `auto_moderate` (or any publication gate) require **at least one** `AdImage`? If not, `technical-specification.md`'s ≥1-photo sentence is unbacked today and `MEDIA-002` needs a **new** enforcement point, not only a dedup re-scope | **BLOCK 1** | **Researcher**, then **Planner** | **RESOLVED 2026-10-01 — a gate DOES exist** (`_validate_image_count` + `ModerationCriteria.min_images` default 1), which INVERTS this block's impact statement. See §0.6 |
| **Q07-3** | Should `MEDIA-002`'s reclaim be `delete_photo` on the freshly staged key, and does it interact badly with phase-03 BLOCK 8's Option A (files living in a *second* sweep-excluded directory until commit)? Deleting a filesystem path from inside a transaction that may roll back is the **inverse desync** | **BLOCK 1** | **Planner**, re-checked against phase-03 BLOCK 8's Q7/Q8 outcome | **RESOLVED 2026-10-01 — `on_commit` reclaim targeting `STAGING_PREFIX + key`, plus `permanent_keys` pruning.** The plan's `delete_photo(key)` draft is a SILENT NO-OP. See §0.6 |
| **Q07-4** | Exact shape of `MEDIA-001`'s reference check: which queryset, `exclude(pk=…)` or not, inline or a new service helper, and does the "`on_commit` means the departing row is already gone" property get its own assertion? | **BLOCK 2** | **Planner** (Researcher supplies the call-site and index inventory) | **MOOT 2026-10-01 — SHIPPED in `64a9de6`.** BLOCK 2 and Q07-4 are RETIRED; do not re-implement. See §0.6 |
| **Q07-5** | Does `MEDIA-005`'s moderator action need a **new** `AdvisoryLockId` or a `select_for_update` on the `AdImage`? And does it route through the existing `apps/moderation/admin_actions.py` pattern, which phase 03 owns for locking and phase 06 owns for reason redaction? | **BLOCK 11** | **Planner + coordinator** | **RESOLVED 2026-10-01 — ROW lock, single photo, `ModeratorActionType.OTHER`, canned reason, matching `inspect.getsource` guard.** No new `AdvisoryLockId`. See §0.6 |
| **Q07-6** | If photo-level moderation is deliberately **deferred** for phase 1, what exactly changes? The report offers "the honest action is a one-line doc fix … not a finding" and that option was never closed | **BLOCK 11** (and BLOCK 12 inherits it) | **Owner (product) + coordinator** | **GATED.** This is a **scope** decision and it flips the block between S and M effort |
| **Q07-7** | For `MEDIA-007`: is the byte budget **global** (`MEDIA_ROOT/staging` total) or **per-seller**? A global budget lets one seller trip a global rejection; a per-seller budget needs per-seller attribution, which the deliberately PII-free `staging/<uuid>.jpg` key format does **not** carry | **BLOCK 7** | **Researcher** (attribution feasibility) → **Planner** | **RESOLVED 2026-10-01 — per-seller attribution is INFEASIBLE (not open); the choice collapses to a GLOBAL budget, chosen.** See §0.6 |
| **Q07-8** | For `MEDIA-007`'s metric: a `Gauge` updated only on the hourly sweep is a **stale** reading for alerting. `django-prometheus` runs in **multiprocess** mode (`PROMETHEUS_MULTIPROC_DIR`) and the sweep runs in a **different process** from web and bot — gauge semantics across processes need stating | **BLOCK 7** | **Researcher** | **RESOLVED 2026-10-01 — NO METRIC SHIPPED.** The gauge is structurally unexportable (scheduler has no `PROMETHEUS_MULTIPROC_DIR`; tmpfs is web-only). See §0.6 |
| **Q07-9** | For `MEDIA-012`: should the dangling-row report cover `seed/` and `staging/`, and should it be a flag (`--check`), a distinct exit code, or both? `_walk_media_files` excludes both; `_collect_referenced_keys` does not | **BLOCK 6** | **Planner** | **RESOLVED 2026-10-01 — a `--check` MODE on `sweep_orphaned_media` reusing lock 103, with `CommandError`.** The plan's `on_disk` reuse is a guaranteed false positive. See §0.6 |
| **Q07-10** | Does any shipped test assert the **exact set** of `admin.site._registry` keys? If so, adding `apps/media/admin.py` is disruptive rather than additive | **BLOCK 8** | **Researcher** (one grep + one test run) | **RESOLVED 2026-10-01 — the risk does NOT exist** (`_registry` has zero matches in `src/`). Delete the whole line of reasoning. See §0.6 |
| **Q07-11** | Re-confirm Pillow's default JPEG quality is still **75** for the pinned Pillow version. The Validator measured 75 on Pillow 12.3.0 by MD5 match; the code context did not re-measure, and the number *is* the finding | **BLOCK 4** | **Researcher** (one MD5 check, in-image) | **RESOLVED 2026-10-01 — default MEASURED as 75, and `quality=75` is byte-identical.** `STORED_JPEG_QUALITY = 75` on `strip_photo_exif`; blast radius is ZERO. See §0.6 |
| **Q07-12** | For `MEDIA-009`/`011` doc work: route the `technical-specification.md` edits to phase 06, and decide whether `docs/ops/docker-deployment.md` and `docs/04-user-stories/seller-stories.md` (both newly identified, C-5, neither in the report's list) are in phase 07's scope or a docs sweep's | **BLOCK 10** | **Coordinator** | **ROUTED + GATED** |
| **Q07-13** | For `MEDIA-006`: does the dev config *intentionally* omit `/csp-report/` and `/metrics`? If the two configs are meant to be symmetric, the added block belongs in a shared include rather than be pasted twice. `docker/nginx/` has no include fragment beyond `mime.types`, so a third file would be a structural change | **BLOCK 9** | **Researcher** → **Planner** | **RESOLVED 2026-10-01 — drift is THREE locations; duplicate, do NOT introduce an `include`.** Dev `/health/` omission is recorded as intentional. See §0.6 |
| **Q07-14** | For `MEDIA-010`: is a **retention command** the right shape, or does `MediaDeletionError` want an admin action to clear rows? An admin-only read surface (the report's minimum) may be sufficient for a LOW | **BLOCK 8** | **Planner** | **RESOLVED 2026-10-01 — BOTH: a read-only admin AND a retention command.** No bulk clear, no retry action. See §0.6 |

**Resolved in this plan, with the reasoning stated** (these are not open questions; they are
rulings so a block does not re-derive them):

- **The ownership model.** N references; free on last reference; implemented as a reference
  *check* in the existing `on_commit` callback. **No schema change, no migration, no new
  model.** The report's first-listed option (a unique index on `ad_images.image`) is
  **infeasible** and is recorded as such so no implementer dead-ends on it: `media_gate`'s
  own docstring *depends* on non-uniqueness and uses `filter` specifically to survive it;
  `copy_ad`'s aliasing is behind a shipped `/copy` command with dedicated green tests; and
  the seed generator produces cross-owner sharing at volume. The report's second option (a
  refcounted `MediaObject` row) costs a model, a migration, a de-duplication backfill, a new
  resolution path on every key lookup, **and still needs the seed-sharing special case** —
  it buys the same behaviour for a great deal more machinery. Project rules 5 and 7
  ("avoid overengineering", "follow existing patterns") point at the reference check.
- **Where `MEDIA-012`'s detection lives.** In `sweep_orphaned_media`, reusing
  `AdvisoryLockId.SWEEP_ORPHANED_MEDIA`, alongside the existing `--dry-run`. **Not** in
  `media_gate`. This is not a stylistic preference — hazard 1 in §0.2.2 shows the request
  path would break a large block of the media-security suite.
- **`MEDIA-008` after `MEDIA-004`, never before.** `MEDIA-008` *reuses* `MEDIA-004`'s
  stale-file-versus-race guard. Fixing 008 first re-introduces the defect class it inherits.

---

### 0.6 Gate resolutions — 2026-10-01 (Auditor → Researcher pass)

**Scope.** The Auditor re-verified the tree and overturned several load-bearing premises,
including one that retires a block outright. The Researcher then closed Q07-1, -2, -3, -5,
-7, -8, -9, -10, -11, -13 and -14, and closed **Q07-4 as moot**.

**Still open and NOT closed:** **Q07-6** (defer photo-level moderation for phase 1 — an
owner/scope decision that flips BLOCK 11/12 between S and M effort) and **Q07-12** (doc
routing). Both are routed to the coordinator.

#### 0.6.1 BLOCK 2 is SHIPPED — retire it

Commit `64a9de6` **is** `MEDIA-001`. Verified three ways. It shipped in
`src/backend/apps/media/signals.py` → `delete_adimage_files_on_delete` as a
**`pre_delete`** receiver, **fully inline**, using a **key-set membership test**
(`AdImage.objects.filter(image__in=keys).exclude(pk=instance.pk).values_list("image", flat=True)`),
with the reference check in the signal body and `on_commit` wrapping **only** the
`delete_photo` loop. `technical-specification.md` line 88 already documents it verbatim.

**Do not re-implement.** Three tripwires bind any future refactor:
- `exclude(pk=instance.pk)` — dropping it **permanently stops all file deletion**, because
  at `pre_delete` the row still exists, so a naive `filter(image=key).exists()` always
  matches the row itself.
- The module-level `delete_photo` binding in `apps.media.signals` — four test functions in
  `apps/core/tests/test_delete_photo_single_call.py` patch that exact name (parametrized,
  so 8 collected cases), plus one patching
  `apps.media.management.commands.sweep_orphaned_media.delete_photo`. A helper that
  re-imports `delete_photo` from `filesystem` makes all of them miss.
- `apps/media/tests/test_media_config.py` asserts the **handler object identity** is in
  `pre_delete._live_receivers(AdImage)` — a rename breaks it.

**What BLOCK 10 must record instead.** Q07-1's measurement changes the documented reach
materially. Cross-`AdImage` key sharing is a **routine production state, not an edge
case**: `copy_ad` produces it by design, and at shipped seed defaults **~33% of image
rows sit on a key shared by ≥2 ads, touching ~55% of ads**. Mechanism: uniform leaf-category
draw, a category-keyed pool with `random_elements(unique=True)`, and
`SeedService.run` calling `AdImage.objects.bulk_create` — **bypassing
`create_or_skip` entirely**, so the seed deliberately manufactures the sharing population.
Consequences: BLOCK 10's storage-key sentence **cannot claim a key "identifies" an ad**;
the shared-key case is a first-class documented state; and **any BLOCK 1 test must build
its own two-ad same-seller fixture** — seed data is not a usable substrate.

#### 0.6.2 Resolved decisions

| Gate | Decision | Why the alternatives lost |
|---|---|---|
| **Q07-2** | A ≥1-photo gate **does** exist: `auto_moderation._validate_image_count` against `ModerationCriteria.min_images` (default 1, admin-editable, cached 300 s). `technical-specification.md` line 149 already says "cannot publish without ≥1 photo" and the code already does it — **no doc drift**. | The plan assumed no gate. It exists. **This inverts BLOCK 1's impact statement**: a *full* dedup hit lands the ad in `ON_MODERATION_FAILED`, never PUBLISHED. The real user-visible bug is a **partial** hit publishing the ad with **silently fewer photos than the seller uploaded** — worse than the orphan leak, and not caught by `min_images`. That is `MEDIA-002`'s actual impact and is fixed by the predicate re-scope. |
| **Q07-3** | **Two coordinated changes in `submit_ad`**, not one line in `AdImageService`: (1) prune `permanent_keys` in place; (2) register the reclaim via `transaction.on_commit` **before** the promote registration, targeting `STAGING_PREFIX + key`. | The plan's `delete_photo(key)` draft is a **silent no-op**: at reclaim time the key has already been rewritten to the *permanent* key by `plan_staging_promotion`, while the bytes are still at `staging/<key>` — and `delete_photo` **returns silently** on `FileNotFoundError`, so nothing is reclaimed and nothing is logged above WARN. Pruning is not an optional second half: without it, promotion `os.replace`s the surviving staged file into permanent storage with **no row referencing it**, defeating the reclaim entirely. **Pruning is also what makes the ordering free of noise** — once the key is out of `permanent_keys`, promotion never sees it, so there is no `FileNotFoundError` and no `logger.exception`. Rejected: inline reclaim (on rollback it destroys the seller's staged file while FSM state still lists it, manufacturing a worse unobservable failure than the leak it fixes). |
| **Q07-11** | **`STORED_JPEG_QUALITY = 75` on `strip_photo_exif`.** The default was **measured**, not deferred: on the locked wheel (`pillow 12.3.0`) an explicit `quality=75` is **byte-identical** to the current output (same md5, `optimize` held constant); 74 and 76 differ, 85 is 606 bytes vs 534. | Because output is byte-identical, **the `sha256` blast radius is zero** — no stored original changes, no dedup key moves, seed unaffected. The gate the plan opened ("do not change the value unless a specific defect is demonstrated") is satisfied vacuously. The target is `strip_photo_exif` (the permanent original, re-encoded on every upload, served as-is) — **not** `ThumbnailService`, which has specified `QUALITY = 85` explicitly all along. Re-open for the coordinator only if a value ≠ 75 is proposed with a demonstrated defect; a synthetic-image delta at 85 is not evidence. |
| **Q07-9** | **A `--check` mode on `sweep_orphaned_media`**, reusing lock 103, failing via `raise CommandError`. The check does its **own** `os.path.exists` probe and suppresses `staging/` as the only special case. | A new command would need an `AdvisoryLockId` (14 is free; 10 is reserved and reads like a typo), three edits to `test_sweep_lock_structure.py`'s set-equality lists, an **exact-list** `HOURLY_COMMANDS` edit, and three docs tables — all to duplicate a key-collection loop. `--check` has zero precedent in the repo but `--dry-run` means "preview a destructive action", so borrowing it would be a semantic lie; `--check` is the least surprising name. `CommandError` is the established idiom (`load_catalog`, `profile_queries`, `send_alerts`) and Django turns it into exit 1; `bootstrap_reference_data`'s numeric code is a one-off and the wrong precedent. **The plan's reuse of `_walk_media_files`'s `on_disk` set is a guaranteed false positive** — it excludes `seed/` while `referenced` *contains* `seed/…` keys, so every seed key would be flagged dangling. `seed/` needs no special case provided the join uses the stored key **verbatim**; stripping the prefix is the trap. |
| **Q07-7** | **Per-seller attribution is INFEASIBLE — mark it closed, not open.** The choice collapses to a **global budget**, chosen. | `save_photo`'s key is pure `uuid4`; `SubmittedPhoto` carries **no `user_id` and no `ad_id`**; the FSM photo list is per-dialog and `state.update_data` overwrites, so abandoned dialogs are unreachable; the staging tree is flat and every writer shares one container uid; mtime yields age, not owner. No reliable mechanism exists without changing the key format, which BLOCK 7 is explicitly forbidden to do. Free rider: FSM-scoped reclaim is **already implemented** in `cmd_cancel`. |
| **Q07-8** | **No metric ships.** A structured `logger.info` of staging bytes at the enforcement point instead. | A `Gauge` set by the hourly sweep is **structurally unexportable**, which is stronger than "stale": the sweep is not a gunicorn worker, so `mark_process_dead` never reaps its `gauge_*.db` file; and the **scheduler service has no `PROMETHEUS_MULTIPROC_DIR`**, while the `/tmp/prometheus_multiproc` tmpfs is mounted on **`web` only** — so the value is not merely unreaped, it is **invisible to the scraped directory**. The bot has the same defect. A future gauge needs a compose change (env + tmpfs on `scheduler` and `bot`) plus a non-gunicorn reaper: a separate, explicitly-scoped piece of work. Consequently **no `apps/media/metrics.py` is created** and `prometheus-slo-alerts.yaml` / `grafana-slo-dashboard.json` are **not** touched — adding a media alert to a file no media metric feeds would be a broken contract. `MEDIA-007` is "staging has no space budget"; the budget *is* the fix. |
| **Q07-10 / Q07-14** | **Both** halves: a read-only `MediaDeletionErrorAdmin` **and** a retention command (lock 14, `DAILY_COMMANDS`, exact-list scheduler assertion updated). **No bulk clear, no retry action.** | `_registry` has **zero matches in `src/`**; `is_registered` appears twice, both per-model. The registry risk does not exist and the admin is purely additive with no migration. But admin alone does not fix unbounded accumulation, and a retention command alone leaves the table invisible. Rejected on evidence: the table has **no index on `storage_key`** and **no attempts threshold**, so a bulk action over either seq-scans an unbounded table and needs a migration; and re-driving deletions is a **new recovery mechanism**, not an admin feature — the hourly sweep already self-heals orphans, and a second differently-triggered deletion path is a second source of divergence. Precedent: `SupportTicketAdmin` is a read-only audit surface with add/delete disabled. |
| **Q07-5** | **Row lock**, single photo, in `apps/moderation/admin_actions.py` alongside `soft_delete_ad`, following `ban_user_for_ad`. `ModeratorActionType.OTHER`, a **canned** `reason` constant, and a **matching `inspect.getsource` guard**. | `admin_actions.py` contains **zero** `advisory_lock` calls — advisory locks are the scheduled-job idempotency device, and here one would be a cross-process lock on a single row, semantically wrong and a deadlock vector against the sweep. The module's shape is `atomic()` + `order_by("pk")` + `select_for_update`, with `bulk_approve`'s comment stating the reason. A bulk photo-delete would bypass the per-row audit and reason. `OTHER` already covers "not reject/ban/soft-delete/criteria-change" and `action_type` drives every `list_filter` while no reader distinguishes a new value. A **canned** reason sidesteps redaction entirely — there is **no** redaction on this path today (`redact_search_query` is search-analytics only; `mask_telegram_id` is used for *logging*, never for the stored `reason`), and a free-text prompt would mean shipping an unredacted PII field. `test_bulk_ban_users_not_locked` proves the repo deliberately asserts **absence** where locking is out of scope, so a new destructive action without a structural pin would be the only unguarded function in the module. |
| **Q07-13** | **Drift is THREE locations** (`/health/`, `/csp-report/`, `= /metrics`). **Duplicate** the block; do **not** introduce an `include`. Record the dev `/health/` omission as intentional. | An `include` fragment needs a **new mount line in all three compose files** — and `docker-compose.yml` and `docker-compose.dev.override.yml` mount to the *same target*, so omitting `docker-compose.prod.yml` **silently drops the control in production**. Worse, `test_nginx_config.py::_location_block` line-scans a file and brace-walks it, so an `include`d fragment is **invisible to the harness** — converting testable configuration into untestable. The shared surface is three `proxy_pass` + four header lines, already duplicated today for `/static/` and `/protected-media/`. Dev `/health/` is not fixed because the container healthcheck hits `web:8000/health/live/` **directly**, bypassing nginx; adding it is a behaviour change to an opt-in dev-only path, not symmetry. All three `limit_req_zone` definitions are already byte-identical, so **no new zone is needed**. |

#### 0.6.3 Two reachability traps the implementor must not miss

1. **BLOCK 11's action would be invisible under the current admin predicates.**
   `AdImageAdmin` sets `has_add_permission`, `has_change_permission` **and**
   `has_delete_permission` all to `False`. Django's `ModelAdmin.get_actions` filters on
   `allowed_permissions`, and `delete_selected` carries `permissions=["delete"]` — so with
   `has_delete_permission → False` **even the default delete action is filtered out**, and
   `changelist_view` requires view-or-change. A new
   `@admin.action(permissions=["delete"], …)` would therefore never appear in the UI. The
   block must open **exactly one** predicate (`has_delete_permission` → `is_staff`),
   deliberately leaving add/change `False`, test reachability through `get_actions(request)`
   rather than by asserting the attribute exists, and decide **explicitly** whether
   re-exposing Django's `delete_selected` on that changelist is acceptable — overriding
   `get_actions` to drop it if not, rather than leaving it as an accident.
2. **The `has_delete_permission` predicate is phase 15's surface.** It is a one-line,
   one-symbol, additive change on a model whose images are not PII — and the alternative
   finding is that a moderator cannot remove a photo at all. Route it to the coordinator
   with that two-line argument; do not block BLOCK 11 on it.

#### 0.6.4 Corrections to this plan's prose (tree wins)

| # | Correction |
|---|---|
| 1 | **BLOCK 2 and Q07-4 are RETIRED as shipped** (`64a9de6`). See §0.6.1 for the three tripwires. |
| 2 | **BLOCK 1 constraint 2 (`delete_photo(key)` on the key alone) is a silent no-op.** The key is already permanent; the bytes are at `staging/<key>`; `delete_photo` returns silently on `FileNotFoundError`. |
| 3 | **BLOCK 1 is two coordinated changes in `submit_ad`**, not one line in `AdImageService`: prune `permanent_keys` in place **and** register the reclaim `on_commit` before the promote registration. Pruning is what removes the promotion noise — the ordering is only "noisy" if pruning is skipped. |
| 4 | **BLOCK 1's impact statement is wrong** and must be replaced with the silent-partial-loss statement (see §0.6.2, Q07-2). There is no spec drift at `technical-specification.md`. |
| 5 | **BLOCK 4's target is `strip_photo_exif`**, and the plan's own BLOCK 4 text already says so — the "inverted framing" critique applies to a misreading, not to the plan. What changed is that the default is now **measured**, so the coordinator gate closes. |
| 6 | **BLOCK 4: declare the constant in `filesystem.py`,** beside `strip_photo_exif` — **not** in `thumbnails.py` as the plan says. `filesystem.py` and `thumbnails.py` have no import edge in either direction, so routing a constant from the high-level service into the low-level module creates a dependency existing for no other reason. Replace the plan's cross-module *proximity* assertion ("the two constants are declared adjacently") with a **behavioural** test: `strip_photo_exif`'s output is byte-identical to an explicit `quality=75` encode of the same image. |
| 7 | **BLOCK 6: the plan's reuse of `on_disk` is a guaranteed false positive** on every `seed/` key. Also `ReferencedKey` (the plan's proposed dataclass) **does not exist in `src/`** — do not introduce it. |
| 8 | BLOCK 6's test references are wrong: `test_delete_photo_called_within_lock_scope` lives in `apps/media/tests/test_sweep_orphaned_media.py::TestSweepLockScope`, **not** `apps/core/tests/test_sweep_lock_structure.py`; and that file has **9** tests in **2** classes, not 8. `db-retention.md`'s real path is `docs/02-database/db-retention.md`. |
| 9 | **BLOCK 7 ships no metric** and creates no metrics module; the two ops files are untouched. Option (b) per-seller is **infeasible**, not open. |
| 10 | **BLOCK 8: delete the "registry enumeration may break" risk entirely** (Q07-10). Add: **no bulk clear, no retry action**, with the missing-index reason stated; the retention command goes in `DAILY_COMMANDS` with the **exact-list** scheduler assertion updated, and `AdvisoryLockId` **14** re-read at allocation time (`test_advisory_lock_ids.py` validates members and references but does **not** catch reuse). |
| 11 | **BLOCK 9's drift is three locations, not two**, and the mechanism is duplication, not an `include`. |
| 12 | **BLOCK 11's advisory-lock framing is wrong** (row lock). Add: single photo (not a filtered set), `OTHER` (no new enum member), a **canned** reason, a matching `inspect.getsource` guard, and the `has_delete_permission` reachability trap in §0.6.3. |
| 13 | BLOCK 1 should also add `.order_by("pk").first()` to `create_or_skip`'s duplicate lookup — one token, on a line the block rewrites anyway — so the winner is deterministic once an ad holds 2+ rows with the same digest. |
| 14 | `apps/media/models.py`'s `MediaDeletionError` docstring says "Production path: none — diagnostics only" while being the sole persistence target of `filesystem.py::_record_deletion_error`. Correct it (comments only, one file). |

#### 0.6.5 New findings filed by this pass

- **`07-NEW-01`** — a **partial** dedup hit publishes an ad with silently fewer photos than
  the seller uploaded. Owned by BLOCK 1's predicate re-scope; filed so the impact statement
  is not lost.
- **`07-NEW-02`** — `create_or_skip`'s duplicate lookup uses `.first()` with no
  `ORDER BY`, so the winner is DB-order-dependent when one seller holds 3+ copies of the
  same bytes. Pre-existing; fixed in BLOCK 1.
- **`07-NEW-03`** — the scheduler service has no `PROMETHEUS_MULTIPROC_DIR` and the bot has
  no `/metrics` endpoint at all, so **no non-web process can export a custom metric**.
  Prerequisite for any future media metric; a compose-level change, not a media change.
- **`07-NEW-04`** — the dev nginx has no `/health/` location, so any probe through nginx in
  dev 404s. Recorded as intentional (the healthcheck bypasses nginx); route separately if
  the coordinator disagrees.

---

## 1. Environment and command contract for the implementor

**This environment is Windows 11 / PowerShell 7.** `make` requires WSL or GNU Make; use
`.\Makefile.ps1 <target>`. `head` / `tail` are unavailable in PowerShell.

### 1.1 Tests are Docker-only — `uv run pytest` on the host always fails

There is no PostgreSQL on `localhost:5432`. Every test run goes through the `test` service
of the `mko-bazuna-test` Compose project.

```powershell
# Fast gate (skips the nightly `seed` suite) — the default iteration command
$dc run --rm --env PYTEST_SKIP_MARKERS=seed test

# Targeted run
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="-k test_name" test
$dc run --rm -e PYTEST_OPTS="src/backend/apps/media/tests/test_sweep_orphaned_media.py --tb=short" test

# Full suite (only when the change touches seeding or images — BLOCK 5 does)
$dc run --rm test

# Fresh schema — only if a block adds a migration (none is expected; see §6.2)
$dc run --rm --env PYTEST_OPTS="--create-db --tb=short -n auto --maxprocesses=4 --dist loadgroup" test
```

with, copied once per session:

```powershell
$dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'
```

**Two caveats that will silently produce a wrong result if ignored:**

- `--env-file .env.test` is **required**. Without it compose aborts on `${POSTGRES_*?}`
  interpolation. **Never** substitute the `mko-bazuna-dev` project name.
- Setting `PYTEST_OPTS` **replaces** the defaults
  (`--reuse-db --tb=short --durations=10 -n auto --maxprocesses=4 --dist loadgroup`), so a
  targeted run loses xdist parallelism **and** DB reuse. The value is **unquoted** in
  `docker/entrypoint-test.sh`, so it is word-split on spaces: `-k test_name` and bare file
  paths work; **quoted multi-token values do not**. Never use `--override-ini=addopts=` — it
  strips `--import-mode=importlib`, which `pyproject.toml` requires.

**Concurrent runs collide on the single `test_mko_bazuna` database.** If a gate goes red while
other phase agents are running, **re-run it serially** before reporting it as a defect.
Teardown races surface as `FATAL: database "test_mko_bazuna" does not exist` and
`relation "..." does not exist`, **not** as product failures.

**`src/telegram_bot/tests/conftest.py` redefines the canonical fixtures as an `async user`.**
Bot tests cannot import the backend conftest. Blocks 1 and 7 touch bot-side files but do not
add bot tests; BLOCK 12 is the one that adds them, and it must use the bot conftest.

Canonical fixtures (backend): `seller` (900000001), `user` (900000002), `category`, `city`,
and `create_test_ad(user, category, city, *, status=AdStatus.PUBLISHED, **kwargs)`.

### 1.2 Lint, typecheck, i18n

```powershell
uv run ruff check <path>            # lint
uv run ruff check --fix <path>      # auto-fix, including import sorting (I001)
uv run basedpyright <path>          # typecheck
uv run djlint src/backend/templates/   # only if a template changes (BLOCK 12 may)
```

`.\Makefile.ps1 format` runs `ruff check --fix src/`, **not** `ruff format`. `ruff format`
only rewraps lines and does **not** sort imports.

**i18n is part of DoD.** Every user-visible string is wrapped in `{% trans %}` /
`{% blocktrans %}` (templates) or `gettext` / `gettext_lazy` (Python). `msgstr` must be
**non-empty** for `ru` and `bs`; `en` may be empty (the msgid is English).
`apps/ads/tests/test_i18n_completeness.py` is **gate-enforced**.

**Which blocks add strings:** BLOCK 7 (the staging-budget rejection message in the bot) and
BLOCKs 11 and 12 (the moderator action description and the seller-facing bot messages).
**`make makemessages` / `make compilemessages` do not work on Windows + Docker Desktop** —
use the lightweight `--no-deps --entrypoint ""` form in `.kilo/rules/commands.md` if a `.po`
genuinely has to change. **Append** to the locale files. **Never** regenerate wholesale:
`src/backend/locale/*/LC_MESSAGES/django.po` is shared with phases 05, 06, 11 and 14, and a
wholesale regeneration would discard their entries.

### 1.3 Git contract — one implementor, sequential, one commit per block

- **One Implementor at a time.** Never two. Never a background implementor.
- If a block is stopped mid-way, **resume the existing session**; do not launch a new agent.
- Each block is committed **separately**, explicitly staged: `git add <specific files>` —
  **never** `git add -A`, **never** `git add .`.
- Message form, matching the repo style:
  `"{type}({scope}): {description}"`, e.g.
  `fix(media): free a storage key only on the last reference (07-MEDIA-001)`,
  `fix(ads): scope photo dedup to the target ad and reclaim the skip (07-MEDIA-002)`,
  `feat(media): report dangling AdImage rows in the orphan sweep (07-MEDIA-012)`,
  `docs(media): state the storage-key ownership rule (07-MEDIA-009)`.
  Every citation is **cycle-scoped `07-MEDIA-0NN`** (§0.1).
- **Never** `git reset`, `git checkout`, `git restore`, `git stash`, `--amend`,
  `--no-verify`, or any other history mutation. Never force-push.
- **Other agents are working in parallel.** Files you did not change appearing in
  `git status` is normal — the working tree already carries untracked phase-02 work and
  19 tracked `.ai/audit/**` deletions. **Never** revert, stash or `git checkout` a file you
  did not write. **If a file you are about to edit already has uncommitted changes from
  another agent, stop and report it** rather than clobbering it.
- Do not commit unless the block's instructions say to. This Planner committed nothing.

### 1.4 Standing project rules (restated for every block)

- **English only** — comments, logs, docstrings, error messages, docs.
- **No `print()`.** `logger = logging.getLogger(__name__)` with lazy `%s` formatting.
- Stack: Python 3.14 · Django 5.2 LTS (`>=5.2.16,<6.0`) · PostgreSQL 18 · aiogram 3.x ·
  native PostgreSQL FTS. **Two processes, one DB:** web (gunicorn sync WSGI, HTMX MPA)
  and bot (aiogram, `django.setup()` + shared ORM). **Migrations run exactly once** before
  both start — a migration that must run in only one process is a defect.
- The bot FSM has **no** built-in PG storage: the ad dialog is persisted as an `Ad` row in
  `DRAFT` via the ORM.
- **Django ORM is the persistence layer.** Pydantic v2 is used **only** at system
  boundaries (bot input, settings schemas). Do not introduce Pydantic DTOs into the
  view/service path. (`apps/media/schemas.py::SubmittedPhoto` already owns the media
  boundary DTO — follow it, do not copy it inward.)
- **All schema changes via Django migrations.** No hand-written DDL. Migration numbers are
  sequential **per app**; **never renumber or edit an existing migration.** Check the
  directory immediately before generating.
- **Fixed values via `StrEnum`** (project rule 10) — never plain strings, dicts or lists.
  Existing in-repo precedent: `AdvisoryLockId`, `AdStatus`, `SupportTicketStatus`.
  A configurable threshold (BLOCK 7's byte budget) is a **Django setting**, not a literal.
- **Business logic lives in `services/`**; no new logic in a view or a handler beyond the
  thin boundary change its block requires.
- Small, focused modules and functions. **Composition over inheritance.** Follow existing
  patterns; **no new abstraction without strong justification**; no speculative redesign;
  no scope creep. Prefer the simple, obvious solution (project rule 5).
- **Production code is king.** If a test conflicts with the architecture or the business
  logic, **fix the test** — and say which change and why in the commit body.
- **Filesystem side effects happen only after commit, via `transaction.on_commit()`**,
  except where a block's gate explicitly records a different, reasoned choice.
  **`delete_adimage_files_on_delete` already establishes this pattern; any new byte-freeing
  path must reuse it rather than invent another.**
- **No task target is a line number.** Every target is a file plus a **semantic** anchor: a
  class, a method, a module-level constant, a named attribute, a function call, a URL route
  name, a management-command name, a template block, a model field.

### 1.5 Test authoring standard for every block

Tests verify **logic and component interaction**, not implementation trivia. No test that
asserts a literal private name, a line number, a template-string substring, a column count
produced by introspection, or the mere presence of a symbol. Assert on **observable
behaviour** and on **absence of danger**.

Good targets for this phase:

- two `AdImage` rows sharing one key, **different owners** → delete one → the file **still
  exists**; delete the second → the file **is gone**;
- identical bytes posted to two ads by the same seller → **both** ads have exactly one image
  **and** zero orphan files remain on disk;
- a photo-less ad is rejected, or is accepted **only** under the recorded `Q07-2` answer —
  never silently;
- a `ThumbnailService.generate_thumbnails` call that fails on the second size leaves **no
  partial files** behind, and a leftover `-small.jpg` against a `NULL` column is
  **regenerated** rather than skipped;
- after `ImageGenerator.generate`, every `thumbnail_*` value on the row points at a file that
  actually exists on disk;
- `sweep_orphaned_media --check` reports a row whose file is gone and reports nothing when
  the store and the database agree — **including for `seed/` keys**;
- a moderator's photo removal writes exactly one `ModeratorActionLog` row, refuses a
  non-staff caller, and **leaves the file in place** when another `AdImage` row still
  references the key;
- a stored original decodes at the **named** quality constant and the two quality constants
  are declared adjacently, so a reviewer sees them side by side.

Never assert: *"a filesystem check happens in `media_gate`"*, *"the `delete` call was made
twice"*, *"the value is `85`"* (assert the named constant is **used**, not its number), or
any enumerated admin-registry set (that is exactly `Q07-10`).

### 1.6 Task shape for every block

Each block's implementor task follows `.ai\tasks\templates\task_template.yaml`: semantic
`targets` with `type` / `name`, `semantic_anchors`, `changes`, `acceptance_criteria`,
`source_reference` / `source_section` / `source_blocks`, and an `extra_context` block
carrying the block's binding constraints verbatim. Verification is **inline** for
low/medium-risk blocks; a **separate Validator task is mandatory for every HIGH-risk block
and for every block whose acceptance depends on a decision the Implementor was told not to
make** — which in this plan is BLOCKS 1, 2, 6, 7, 8, 11 and 12.

---

## 2. Scope decisions table (acceptance contract for execution)

| ID | Disposition | Block | Final severity | One-line reason |
|---|---|---|---|---|
| `07-MEDIA-001` | **implement — a reference check inside the existing `on_commit` callback.** No schema change, no migration, no new model. **Shape is gated (Q07-4)** | BLOCK 2 | **HIGH** · P0 | The only deterministic same-tenant data-loss path in the phase. A false "last reference" destroys live bytes; a false "still referenced" leaks a file the hourly sweep reclaims. Only one of those is recoverable, so the check is biased toward the second |
| `07-MEDIA-002` | **implement — re-scope the predicate to `(ad, sha256)`, return an explicit result, and reclaim the promoted files.** Reclaim **placement** is gated (Q07-2, Q07-3) | BLOCK 1 | **HIGH** · P0 | Reproduced: the second ad publishes with **zero** images, violating the ≥1-photo spec sentence, and 4 files are orphaned per occurrence. `test_ad_image_service.py` does **not** pin the old behaviour (C-2), so this is an unopposed behaviour change with a Low rollout risk |
| `07-MEDIA-003` | **merged away — no work item here.** Two obligations routed to §5.1 and §5.2 | — | MEDIUM (absorbed by `03-DB-005`) | Same mechanism and same remedy as phase 03 BLOCK 8, which also absorbed phase 01's `ENT-009`. **Two patches to the same two functions would each be partial.** Phase 07 ships **no** staging-window fix |
| `07-MEDIA-004` | **implement — atomic writes (temp + `os.replace`, unlink partials) plus a repair guard that prefers the stale-file case over the race case.** Whether `submit_ad`'s blanket `except Exception` stays is gated | BLOCK 3 | **HIGH** · P1 | Reproduced twice: the repair command is **permanently** blocked (a leftover `-small.jpg` aborts on the first `SIZES` iteration, so MEDIUM and LARGE are never attempted), and the leftovers stay unreferenced. The documented self-healing command reports progress while achieving nothing |
| `07-MEDIA-005` | **implement — split in two.** The removal service and the moderator action; the seller-facing bot wiring. **Hard dependency on BLOCK 2.** **Deferred for phase 1 is a live branch (Q07-6)** | BLOCK 11 (service + admin) + BLOCK 12 (bot) | MEDIUM · P1 | A photo containing a phone number or a face can only leave a live ad by destroying the whole listing — the seller's text, views and analytics. `AdImage` is append-only by construction: no service, no admin action, no FSM step owns single-image removal |
| `07-MEDIA-006` | **implement — the documented block verbatim in both configs, plus `limit_req` on `location /media/`, covered by the **existing** nginx harness (C-3).** Config shape is gated (Q07-13) | BLOCK 9 | MEDIUM · P2 | The block is genuinely **absent from the repository** — `deny all` occurs exactly once in the whole config set, on `location = /metrics`. There is **no execution path** today (`/media/` is proxied to Django, `/protected-media/` is `internal`), so this is false assurance plus an unrated request path, not an exploit |
| `07-MEDIA-007` | **implement — a configured byte budget beside the TTL, plus a `staging_bytes` gauge and a translated rejection message.** Budget shape and metric semantics are gated (Q07-7, Q07-8) | BLOCK 7 | MEDIUM · P1 | ≈2.4 GB of permanently-unreferenced staging bytes per abusive account inside one 2 h window, on a volume shared with nginx and the web tier — exhaustion stops photo serving **for the whole site**. The TTL is a *time* policy; there is no *space* policy anywhere |
| `07-MEDIA-008` | **implement — build the `AdImage` thumbnail fields from the real `ThumbnailService` return value**, and extend or drop the single-variant cache check. **Hard dependency on BLOCK 3** | BLOCK 5 | MEDIUM · P2 | A stale `-small` cache hit makes `_preprocess_one` return `True` while `generate()` records all three keys — so the database asserts two files that were never written. Both escape routes are closed: `_walk_media_files` skips `seed/`, and `backfill_thumbnails` hits the same `O_EXCL` guard. Dev/demo path only |
| `07-MEDIA-009` | **implement — documentation only, and it is 7 locations / 5 files + 2 docstrings, not 4 documents (C-5).** **Hard dependency on BLOCK 2** (write the *decided* rule). Four targets are reserved and **routed** (Q07-12) | BLOCK 10 | MEDIUM · P1 | This documentation *is* the specification the erasure and retention reviews rely on, and it asserts a key structure the code does not produce. A repository-wide search for `refcount` / `reference count` / `ownership` across `docs/` returns **nothing** — the invariant survives only as an undocumented assumption |
| `07-MEDIA-010` | **implement — admin registration plus retention.** A retention command **and** a new `AdvisoryLockId` (id **14**, C-4) is the fuller shape; admin-only is the report's minimum. **Gated on Q07-10 and Q07-14** | BLOCK 8 | LOW · P2 | `MediaDeletionError` is write-only: no reader, no prune, no `expires`, no alert, **not in `admin.site._registry`**, **zero** references in `docs/`. The table is also an unbounded growth source that masks the signal it exists to raise. LOW is correct because `logger.error` keeps the underlying condition visible |
| `07-MEDIA-011` | **implement — a named `STORED_JPEG_QUALITY` constant** placed beside `ThumbnailService.QUALITY`. The spec correction is **reserved and routed** (Q07-12) | BLOCK 4 | LOW · P2 | Pillow's default (measured at exactly 75 by MD5 match, Pillow 12.3.0) applies to every seller photo, at a quality the code never chose out loud. Two spec sentences say *"No server-side photo optimization in phase 1"* and *"serves full-size compressed photos"* — both contradicted by the shipped pipeline. The code is the better artefact; the **docs** should change |
| `07-MEDIA-012` | **implement — a dangling-row report mode on `sweep_orphaned_media`, reusing lock 103, plus a store↔database assertion in the suite.** Scope and signalling are gated (Q07-9). **Folded in:** the `deleted += 1` miscount | BLOCK 6 | **HIGH** · P1 | `media_gate` authorises on the presence of a row and **never checks the filesystem**: under `DEBUG=False` a dangling key returns `200 OK` + `X-Accel-Redirect` to a path nginx cannot serve. No 4xx from Django, no log record, no metric anywhere. Every dangling row from `MEDIA-001`, `004`, `008` or `DB-005` is invisible until a human notices a broken image, and then unrecoverable without seller re-upload |
| **Rubric §4.7 assertion** | **implement — one non-finding work item:** a test that diffs the media store against `AdImage` rows **including `seed/`** | BLOCK 6 | — | The reconciliation exists; the **assertion** does not. The Auditor's original diff excluded `seed/` — precisely where most shared keys live — and the suite's existing "missing key" test passes for the wrong reason (it creates **no** row) |
| **`ME-003` traceability** | **implement — one non-finding work item:** reconcile the dangling prior-cycle finding id in `apps/media/models.py`'s module docstring | BLOCK 8 | — | It points at a finding id from a prior audit cycle that is not resolvable from the repository. Same reasoning as `VAL-003`: restore the traceability or drop the id, in the same commit that touches the model |
| **Q07-6 deferral branch** | **not a finding, but a live branch:** if photo-level moderation is deferred for phase 1, the honest action is a one-line doc correction, and BLOCK 11's code scope collapses | BLOCK 11 | — | The report says so explicitly and never closed the option. **This plan does not choose** |
| **Q07-12 reserved docs** | **ROUTED, not planned** — `technical-specification.md` (phase 06), `db-retention.md` (phase 06 BLOCK 15 **and** phase 03 BLOCK 5) | BLOCK 10 | — | Four of the seven stale locations sit on files other phases hold. §5.2, §6.1 |

---

## 3. Execution blocks

Twelve blocks, eleven of which ship code, configuration or documentation and one
(BLOCK 6) which ships the guardrail that makes the other four HIGH/MEDIUM findings
*detectable* while they are being fixed. **One Implementor, strictly sequential, one commit
per block** (§1.3).

**The safe serial order is 1 → 12** (§4.1). It is *not* severity order, and that is
deliberate: BLOCK 1 is the P0 that shrinks BLOCK 2's problem, and BLOCK 6 — the highest-ROI
item in the report — is scheduled third among the HIGH items because it edits the one
function that three parties claim.

**Blocks 1, 2, 6, 7, 8, 11 and 12 carry an unresolved decision gate.** Their Implementor
task must state, in `extra_context`, that the block **may not start** until the gate's answer
is written down with its consequences accepted. A block whose gate is unanswered does not
start. §8.1 checks that a written answer exists for all fourteen questions.

---

### BLOCK 1 — Scope the photo dedup to the target ad, and reclaim the skipped files (07-MEDIA-002)

| | |
|---|---|
| **Findings owned** | `07-MEDIA-002` |
| **Depends on** | **nothing in-plan.** External: phase-03 BLOCK 8's **Q7/Q8 outcome** is an *input* to the Q07-3 gate below, but the block does not wait for phase 03 to land — it waits only for the *recorded option* |
| **Blocks** | BLOCK 2 (hard) |
| **Priority** | **P0** |
| **Risk level** | **HIGH** — a byte-freeing operation in a transaction that can roll back |
| **Required agents** | **Auditor · Researcher · Planner · Implementor · Validator — all five** |

**Why this is first.** The audited chain put `MEDIA-001` before `MEDIA-002`; that chain is
**inverted**. `MEDIA-002`'s fix creates a fresh row under a freshly generated **unique** key
(`generate_storage_key()`), and reclaiming the skipped file is safe under *either* ownership
model. Landing it first **removes the accidental-aliasing vector entirely**, shrinking
`MEDIA-001`'s problem from three producers of a shared key to two intentional ones. Shipping
`MEDIA-001` first would encode a guard against a defect that is about to stop existing.

**What is wrong.** `AdImageService.create_or_skip` hashes the on-disk file and looks for a
match scoped to **`ad__user_id=ad.user_id`** — to the *seller*, not the ad. On a hit it
returns the existing row and creates nothing; `submit_ad` discards the return value and never
counts rows. Net effect per occurrence: the new ad publishes with **zero** images, and the
four files it staged are promoted to permanent storage with no row referencing them. The bot
has **no** `telegram_file_id` short-circuit — every upload is downloaded, `strip_photo_exif`
re-encoded and re-stored — so re-posting the same source photo deterministically yields
byte-identical stored bytes, an identical `sha256`, and therefore a deterministic dedup hit.

**Decision required before implementation — Q07-2 (is there a photo-count gate anywhere?)**

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | No gate exists or is needed: the dedup re-scope alone is the whole fix | **Gains:** the smallest correct change; the ad always gets the photo it was given. **Costs:** the spec sentence *"Photos: 1–5 mandatory … cannot publish without ≥1 photo"* stays **unbacked by code**. A seller who reaches `submit_ad` with an empty `photos` list still publishes a photo-less ad. The finding is closed; the spec sentence is not made true |
| **(b)** | Add an explicit ≥1-photo enforcement point (in `submit_ad` before the transition, or in the publication gate) alongside the re-scope | **Gains:** makes the spec sentence true, and closes the class rather than the instance. **Costs:** a **new** rejection path with a **new user-visible error message** (i18n deliverable: non-empty `ru` **and** `bs`); a new failure mode for the `AdEditInput` branches, which pass `photos=[]` **on both paths that reach `submit_ad`** and would be rejected; it is a *behaviour change on a new path* that phase 05's BLOCKs 2, 8 and 12 also touch |

**The Implementor must not choose between (a) and (b).** The Researcher traces
`auto_moderate`'s validation set and every pre-transition guard, states the answer, and the
Planner records the option chosen with the consequences accepted. Under (b) the block's
surface grows into `technical-specification.md`-adjacent behaviour and the i18n gate; the
Planner must say so in the decision record.

**Decision required before implementation — Q07-3 (where does the reclaim fire?)**

This is the block's sharpest technical question and it is **not** decided here. The reclaim
must fire after `create_or_skip` returns `created=False`, which happens **inside**
`submit_ad`'s `with transaction.atomic():` block. Deleting a filesystem path from inside a
transaction that may roll back is the **inverse** of `MEDIA-012`'s defect: a rollback would
leave a committed row and a **live** file — an orphan in the opposite direction.

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | `transaction.on_commit(...)` for the reclaim | **Gains:** the project's established pattern for byte effects, and zero new mechanism — `delete_adimage_files_on_delete` already does exactly this. **Costs:** a rollback **leaves the promoted files on disk unreferenced**, i.e. the same residue `DB-005` already produces. Detectable by BLOCK 6's report, reclaimable by the hourly sweep. Perfectly consistent with the rest of the media layer's stated contract |
| **(b)** | Collect the skipped keys in a list inside the atomic block and delete them **after** the block exits, in a `try/finally` | **Gains:** covers the rollback case too, so no orphans on either path. **Costs:** a `finally` block that deletes files is itself new machinery and diverges from the on-commit pattern every other byte effect follows; on rollback the keys may never have been written, so the reclaim must tolerate a missing file (it already does — `delete_photo` retries then records a `MediaDeletionError`) |
| **(c)** | Delete inline, inside the atomic block, immediately on the `created=False` branch | **Gains:** nothing. **Costs:** **the worst option** and explicitly disfavoured: on rollback it leaves the row and removes the file, i.e. a **live ad pointing at a missing file** — precisely `MEDIA-012`'s unobservable failure, manufactured deliberately. Listed only so it is visibly rejected |

**The interaction with phase 03 BLOCK 8 is the reason this is a gate.** Under DB-005's
**Option A** (keep promoted files in a *second* sweep-excluded directory until the row
commits, then move), the freshly staged key's **location** at reclaim time depends on a
design phase 03 has not settled. The reclaim must be written against the *key*, never against
a hard-coded directory, so it survives whichever option wins. The Auditor must state which
option phase 03 has recorded **at the time this block runs**, and the Implementor must write
the reclaim against `apps.media.services.filesystem.delete_photo(key)` on the key alone.

**Surface**

| Path | Symbols | Change |
|---|---|---|
| `src/backend/apps/ads/services/images.py` | `AdImageService.create_or_skip` | Re-scope the predicate from `ad__user_id=ad.user_id` to `ad=ad`; return an explicit result carrying `created: bool` (a `StrEnum` per rule 10, or a `NamedTuple`/dataclass consistent with the module's existing shape). **Its docstring currently says *"Deduplication is scoped per seller"* — a docstring change is mandatory if the scope changes** |
| `src/backend/apps/ads/services/images.py` | `AdImageService._compute_sha256` | read-only; confirm `AdImage.save()`'s auto-computed hash of the **promoted** bytes stays correct |
| `src/backend/apps/ads/services/submission.py` | `submit_ad` | Consume the return value instead of discarding it; collect the keys of every non-created result; fire the reclaim at the gate's chosen placement |
| `src/backend/apps/media/services/filesystem.py` | `delete_photo` | read-only call site — **import it directly, not via `apps.media.signals`** (binding constraint) |

**Binding constraints for the Implementor**

1. **Reclaim through `apps.media.services.filesystem.delete_photo`, directly.**
   `apps.media.signals.delete_photo` is the monkeypatch target of
   `apps/core/tests/test_delete_photo_single_call.py`, which asserts every key reaches it
   **exactly once** across six sweep and consent paths. A reclaim routed through the signals
   module perturbs that count and BLOCK 2 then inherits a red test.
2. **The freshly staged key is always unique** (`generate_storage_key()` in
   `ad_create/photos.py::process_photos`), so deleting it is safe under either ownership
   model. This is what makes BLOCK 1 safe to land **before** BLOCK 2.
3. **`test_ad_image_service.py` must be left untouched** (C-2). It does not pin the old
   behaviour. Adding a cross-ad test is *additive coverage*, not a rewrite.
4. **The commit message cites the spec sentence, not a test.** Project rule 2 is not engaged
   for this finding — there is no red test to justify bending code around. Say which
   justification is being used.
5. **Do not** add a `telegram_file_id` short-circuit. It is stored but explicitly not used for
   dedup and not usable in an `<img src>`; a short-circuit is a **separate decision**, not
   part of this finding.
6. **Do not** change `AdImage.storage_keys()`, `move_staging_to_permanent`,
   `save_photo`, or any `Ad` transition. Phase 03 BLOCK 8 owns the first two.
7. `submit_ad` is the **most contested file in the plan set** (phase-03 BLOCKs 3, 5, 6, 8;
   phase-05 BLOCKs 5, 12, 13). Re-read immediately before editing; stage explicitly.

**Tests to add** (logic and component interaction, per §1.5)

1. Identical bytes posted to **two ads of the same seller** → **both** ads have exactly one
   image, and the two rows carry **different** storage keys.
2. The same scenario leaves **zero orphan files** on disk after the reclaim — asserted over
   the staging-promoted path, i.e. the original plus all three thumbnails.
3. The same scenario for **two different sellers** is unchanged (it was already unopposed;
   this asserts it did not regress).
4. **Rollback behaviour**, matching the chosen Q07-3 option and asserting the *option's*
   guarantee: under (a) a rolled-back submit leaves the promoted files unreferenced **and
   the row absent** (a detectable orphan, not a dangling row); under (b) no file survives.
   **The test encodes the decision, and the decision is named in the test's docstring.**
5. `create_or_skip` called with the **same** ad twice still returns the existing row
   (`test_returns_existing_duplicate_same_user` stays green **unchanged** — prove it).

**Keep green, do not edit**

`apps/ads/tests/test_ad_image_service.py` in full · `apps/core/tests/test_delete_photo_single_call.py`
in full · `apps/media/tests/test_thumbnail_integration.py::TestSavePhotoThumbnailIntegration` ·
`apps/telegram_bot/tests/test_save_photo_integration.py` (phase 03 BLOCK 8's surface — if
it has landed, **re-read, do not assume**) · `apps/ads/tests/test_copy_ad.py` in full.

**Gates**

`$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/ads/tests/test_ad_image_service.py src/backend/apps/core/tests/test_delete_photo_single_call.py src/backend/apps/media/tests/test_thumbnail_integration.py --tb=short" test`
→ then `.\Makefile.ps1 test` → then `uv run ruff check src/` and `uv run basedpyright src/`.

**Risk and rollback**

- *Rollout risk: LOW* (C-2 — no shipped test encodes the old behaviour). *Compatibility:*
  yes for existing data; a seller who reposted a photo now gets an image where they
  previously got none, which is strictly closer to the spec. Existing photo-less ads stay
  photo-less; **no backfill is scheduled** (de-scoped, §6.2).
- *Filesystem-vs-database consistency:* the whole point of the block, and the reason for the
  Q07-3 gate. Under option (a) a rollback produces an **orphan file** (recoverable, sweepable);
  under option (c) it would produce a **dangling row** (unrecoverable). Option (c) is rejected.
- *Migration / backfill hazards:* **none.** No schema change is expected.
- *Rollback:* revert the commit. A revert leaves the reclaim's re-scope undone, which
  restores the defect — no data was destroyed, and no file was removed whose row survives.
- *Cross-phase:* phase 05 BLOCK 13 is parked on this block (§5.5).

---

### BLOCK 2 — Free a storage key only when the last referencing row goes away (07-MEDIA-001)

| | |
|---|---|
| **Findings owned** | `07-MEDIA-001`, plus **Q07-1**'s measurement |
| **Depends on** | **BLOCK 1** (hard) |
| **Blocks** | BLOCK 10, BLOCK 11 (both hard) |
| **Priority** | **P0** |
| **Risk level** | **HIGH** — the only block in the plan that can destroy live bytes |
| **Required agents** | **Auditor · Researcher · Planner · Implementor · Validator — all five** |

**Why second.** BLOCK 1 removes the accidental-aliasing vector. This block encodes the
invariant: *a storage key may be referenced by N ≥ 1 `AdImage` rows, and the bytes are freed
only when the **last** referencing row goes away.* The schema already declares this:
`ad_images.image` is a plain `CharField` with four non-unique indexes and no uniqueness
constraint, and its `CheckConstraint`s enforce only the key **format**. `media_gate`'s own
docstring depends on non-uniqueness and uses `filter` rather than `get` specifically to
survive it. Non-uniqueness is the design; the defect is that the **delete path** is unaware
of it.

**What is wrong.** `delete_adimage_files_on_delete` collects `instance.storage_keys()` and
calls `delete_photo(key)` for each, unconditionally, inside a `transaction.on_commit`
closure. Two shipped code paths create keys referenced by more than one row: `copy_ad`
(which aliases the source ad's keys verbatim, behind a shipped `/copy` command) and the seed
generator (cross-owner sharing within a category at volume). The trigger is an ordinary
seller action, not a race: `/post` → `create_draft_ad` → `existing.delete()` → CASCADE →
`pre_delete`.

**Decision required before implementation — Q07-4 (the exact shape of the check)**

| Option | What it is | Trade-offs |
|---|---|---|
| **(a)** | **Inline** an `AdImage.objects.filter(Q(image=key) \| Q(thumbnail_small=key) \| …).exists()` inside the existing `on_commit` closure, per key | **Gains:** the smallest possible diff; no new module, no new import, no new seam. Follows project rules 5 and 7. All four columns are indexed, so the check is an indexed `EXISTS`. **Costs:** the predicate is duplicated in intent if BLOCK 11's removal service later needs it (BLOCK 11 must **reuse**, not copy) |
| **(b)** | A small named helper on the media layer — e.g. `apps/media/services/references.py::key_is_still_referenced(key) -> bool` — called from the signal and, later, from BLOCK 11's service | **Gains:** exactly one place expresses "is this key still referenced", which is what stops BLOCK 11 from becoming a second data-loss route. **Costs:** a new module in an app whose surface is currently four service files. Defensible **only** if BLOCK 11 is scheduled — which it is |
| **(c)** | A refcount column / `MediaObject` model | **Explicitly rejected before implementation.** It costs a model, a migration, a de-duplication backfill of existing keys, a new resolution path on every key lookup, **and still needs the seed-sharing special case** — it buys the identical behaviour for a great deal more machinery. Recorded so no implementer re-derives it |

**This Planner's read, not a decision:** (a) and (b) are both acceptable and the difference
is one module. The gate exists because the choice determines whether BLOCK 11 has something
to reuse. The Planner must record which was chosen and why.

**Failure direction is correct by construction and must be stated in the code comment.** If
two rows sharing a key are deleted in concurrent transactions, each `on_commit` may still see
the other, so both **skip** — a **leak**, which the hourly sweep reclaims. The reverse — a
false "last reference" — is what destroys live data, and it cannot occur. **Leaks are
recoverable; data loss is not.** The check must be biased toward the first outcome.

**`on_commit` semantics are load-bearing.** The callback fires after commit, i.e. the
departing row is **already out of the count**, which is what makes the off-by-one structurally
impossible. **Do not move the check to `pre_delete` time.** A test must assert this property
explicitly rather than leaving it as a comment.

**Surface**

| Path | Symbols | Change |
|---|---|---|
| `src/backend/apps/media/signals.py` | `delete_adimage_files_on_delete` | Before `delete_photo(key)`, test whether any **other** row still references the key across all four columns and **skip** if so. **The function must not be renamed** — `apps/media/tests/test_media_config.py::test_pre_delete_signal_registered_for_adimage` asserts it is among `pre_delete._live_receivers(AdImage)` **by identity** |
| `src/backend/apps/media/services/references.py` | *(new, only under Q07-4 option (b))* | one named predicate |
| `src/backend/apps/ads/models.py` | `AdImage.storage_keys` | **read-only.** Do not change its signature or return order — `test_adimage_storage_keys.py` pins it and it is the collector the signal, `soft_delete_user_ads` and `delete_draft` all rely on |
| `src/backend/apps/ads/services/copy_service.py` | `copy_ad` | **read-only.** Aliasing is legal behaviour under the ownership model. Do not "fix" it (phase-05 BLOCK 14 owns a comment-only edit) |

**Binding constraints for the Implementor**

1. **`test_delete_photo_single_call.py` must stay green unchanged.** A "skip if referenced"
   check satisfies it — the key is simply not passed. A "check → unlink → re-check" design
   does **not**, and is therefore forbidden.
2. **`test_ad_image_delete_signal.py` must stay green unchanged.** All three of its tests use
   a single-ad, single-row fixture, so a reference check keeps them passing; note that
   `::test_delete_photo_failure_does_not_rollback_cascade` asserts *every* key reached
   `delete_photo`, which the skip still satisfies in the single-ad case.
3. **Do not rename the receiver** (constraint above) and do not change how
   `MediaConfig.ready()` imports it.
4. **The failure direction is the comment's subject.** A reviewer must be able to see, from
   the code, that a leak was chosen over a data loss, and why.
5. **No migration, no backfill, no schema change.** Existing shared rows become safe
   immediately; nothing is de-duplicated.
6. **Do not touch `media_gate`.** Adding a filesystem check there breaks a large block of
   `test_media_security.py` (§0.2.2 hazard 1) — that is `MEDIA-012`'s answer and it is "not
   the request path".

**Researcher pre-block step — Q07-1 (measure, do not re-derive from the report)**

With the seed manifest's `default.photos` empty (C-1), the report's "cross-category
default-pool sharing" narrative does not hold. The Researcher re-measures the **actual**
cross-user shared-key population from the `AdGenerator` category distribution and the
`image_count` 1–3 draw, and states: (i) how many distinct ads reference at least one key also
referenced by an ad of a **different** owner, in a seeded environment of realistic size; and
(ii) whether that population is material to the invariant decision. **It is not** — the
invariant is forced by `copy_ad` and by the schema regardless — but the number is what
BLOCK 10 must not contradict when it writes the reach into a document, and what the
Validator uses to check BLOCK 2's own test fixture is production-shaped.

**Tests to add**

1. **The invariant test the report asks for:** two `AdImage` rows sharing one key → delete one
   → **the file still exists**; delete the second → **the file is gone**. Same for the `seed/`
   key shape with **two different owners**.
2. **`on_commit` ordering:** inside `pytest.mark.django_db(transaction=True)`, assert the check
   runs **after** the departing row is gone — i.e. a single-ad delete does free the file. If
   the check were moved to `pre_delete` time this test fails.
3. **Store↔database reconciliation including `seed/`** (the rubric §4.7 assertion, delivered
   here as well as in BLOCK 6 because this is the block that can create the divergence):
   after the block's own create/delete cycles, no `AdImage` key lacks a file and no file lacks
   a row. **`seed/` is in scope for this diff; the original Auditor's diff excluded it and
   that is the audit defect `VAL-005` records.**
4. **Negative case:** a key referenced only by the departing row is deleted (proves the check
   is not simply "never delete").

**Keep green, do not edit**

`apps/core/tests/test_delete_photo_single_call.py` in full ·
`apps/core/tests/test_ad_image_delete_signal.py` in full ·
`apps/media/tests/test_media_config.py` in full ·
`apps/ads/tests/test_adimage_storage_keys.py` in full ·
`apps/ads/tests/test_copy_ad.py` in full.

**Gates**

`$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/core/tests/test_delete_photo_single_call.py src/backend/apps/core/tests/test_ad_image_delete_signal.py src/backend/apps/media/tests/test_media_config.py --tb=short" test`
→ then `.\Makefile.ps1 test` → then `uv run ruff check src/` and `uv run basedpyright src/`.

**Risk and rollback**

- *Rollout risk: MED-HIGH.* The fix changes **when** bytes are freed. The failure modes are
  asymmetric: a false "last reference" destroys live data; a false "not last" leaks a file.
  The check runs inside `on_commit`, so the off-by-one is structurally impossible — that is
  the control.
- *Filesystem-vs-database consistency:* the block moves the system from *unidirectional* to
  *conservative* reconciliation. A leaked file is reclaimed by the hourly sweep; the
  acceptance criteria require no regression in that direction.
- *Migration / backfill hazards:* **none.**
- *Rollback:* a plain revert restores the defect and is safe — no data was destroyed by the
  fix. The one irreversible consequence is any file a buggy run already leaked; the sweep
  reclaims those, so nothing is lost permanently.
- *Cross-phase:* the `pre_delete` half of phase 05's `AD-003` is absorbed here and
  `AD-003` is **retired** (§5.4). Phase 07 must not resurrect it.

---

### BLOCK 3 — Thumbnail writes must be atomic on disk, and the repair guard must actually repair (07-MEDIA-004)

| | |
|---|---|
| **Findings owned** | `07-MEDIA-004` |
| **Depends on** | **nothing in-plan** (serialised after BLOCK 1 on `submission.py`) |
| **Blocks** | BLOCK 5 (hard) |
| **Priority** | **P1** |
| **Risk level** | **HIGH** — it changes the contract a shipped test pins by name |
| **Required agents** | **Auditor · Researcher · Planner · Implementor · Validator — all five** |

**What is wrong.** `generate_thumbnails` loops `SIZES` (a `dict`, insertion order
SMALL → MEDIUM → LARGE) and each iteration opens its target with
`os.open(path, O_CREAT | O_EXCL | O_WRONLY)` and writes. A failure part-way (ENOSPC, EIO, a
killed worker) leaves 0–2 files on disk and raises. `submit_ad` catches **`except Exception`**
around the whole per-photo block, sets all three `thumbnail_*` fields to `None` and
continues; `move_staging_to_permanent` then still promotes whatever survived, so the row is
written with NULL thumbnails and 1–2 unreferenced files beside it.

The repair command cannot fix it. `_read_and_generate` guards **only** with
`except FileExistsError: … return None`, logging *"already exist … (race), skipping"*. Because
`SIZES` iterates SMALL first, a leftover `-small.jpg` aborts on the **first** iteration, so
MEDIUM and LARGE are never even attempted. The Validator ran the command **twice** and the
state survived both runs: this is permanent, not transient. `O_EXCL` is doing double duty as
the idempotency guard, which is exactly why "already generated" and "half-written leftover"
are indistinguishable.

**The direction that matters.** The **stale** case must win over the **race** case. A genuine
concurrent double-generation is harmless — both writers produce byte-identical `O_EXCL`-guarded
output — while a stale file is permanent data loss. The fix is therefore: *if the target file
already exists **and** the row's column is `NULL`, the file is stale: delete and regenerate.*

**The one design question, which the Planner must record before code**

`apps/media/tests/test_thumbnails.py::test_atomic_write_collision_raises_file_exists` **pins
the `FileExistsError` contract explicitly**. Two paths:

| Option | What it is | Consequence |
|---|---|---|
| **(a)** | Keep `generate_thumbnails` raising `FileExistsError` on a pre-existing target; put the *stale-file discrimination* in the **callers** — `backfill_thumbnails._read_and_generate` (which knows the column is `NULL`) and, later, `ImageGenerator._preprocess_one` (BLOCK 5) | **Gains:** the shipped test stays green **unchanged**; the discrimination lives exactly where the information ("is the column NULL?") exists; `O_EXCL` keeps doing its original job. **Costs:** two callers must each implement the check — which is precisely what BLOCK 5 *reuses*, so it is one helper, not two |
| **(b)** | Move the discrimination **into** `generate_thumbnails` (delete-and-regenerate on collision) and rewrite `test_atomic_write_collision_raises_file_exists` | **Gains:** one place, no caller can forget. **Costs:** rewrites a **shipped green test** that pins a deliberate contract (project rule 2: fix the test, say why); the service then needs to know the caller's column state to be safe, which it does not have — it would have to treat *every* collision as stale, which changes behaviour for a genuine concurrent generation |

**The Planner must choose and record.** This is not a Researcher question — both shapes are
understood — but it is a real fork with a test consequence, and the plan will not present it
as settled.

**Surface**

| Path | Symbols | Change |
|---|---|---|
| `src/backend/apps/media/services/thumbnails.py` | `ThumbnailService.generate_thumbnails` | Render all three variants into memory, materialise each as a temp file in the **destination directory**, and `os.replace` them into place only after all three succeed; unlink partials on failure. Per the option above, either keep or drop the `FileExistsError` contract |
| `src/backend/apps/media/management/commands/backfill_thumbnails.py` | `Command._read_and_generate` | Replace the blanket `except FileExistsError → return None` with a guard that discriminates: existing file + `NULL` column ⇒ stale ⇒ delete and regenerate; existing file + populated column ⇒ genuinely already generated ⇒ skip |
| `src/backend/apps/ads/services/submission.py` | `submit_ad` (the per-photo thumbnail block) | **See the gate below** — whether the blanket `except Exception` stays |

**Decision required before implementation — does `submit_ad`'s blanket catch stay?**

The bare `except Exception` is *why* the failure is silent: it swallows `FileNotFoundError`
on the original, `OSError` on write, and a programming error alike, and turns all of them
into "no thumbnails". It is **not** strictly part of `MEDIA-004`'s finding, and BLOCK 1 has
just edited the same function.

- *Keep it* — smallest diff; the new atomic write already makes the partial-file residue
  impossible, so the remaining failure mode is "no thumbnails", which is exactly the
  existing contract. The block must then add **one** log record at `warning` naming the key
  and the exception, so the condition is observable (it is currently invisible, which is the
  finding's "no test, metric or dashboard detects it" complaint).
- *Narrow it* — better signal, but it is a behaviour change on a path phase 05's BLOCKs 5
  and 12 also own, and it can turn a previously-successful publish into an exception.

**The Planner must record the choice and the reason. This plan does not choose.**

**Binding constraints for the Implementor**

1. **Do not depend on `SIZES` iteration order** for correctness, whatever option is chosen.
2. **`_read_and_generate` returns `tuple[int, dict[str, str]] | None` and only fills columns
   still `NULL`.** Its return type and its "only fill missing" rule are load-bearing, and the
   command's three-phase structure (I/O outside the transaction, persist in one short
   transaction, no lock re-acquisition) is documented as *relying on `_read_and_generate`
   idempotency*. Changing that assumption must be stated in the docstring.
3. **All eight `apps/media/tests/test_backfill_thumbnails.py` tests must keep passing**,
   including `::test_backfill_partial_thumbnails_only_fills_missing` and
   `::test_backfill_skips_records_with_all_thumbnails`.
4. **Do not touch the seed generator** in this block. BLOCK 5 owns it.
5. The temp files must be created **in the destination directory**, not in a system temp
   directory — `os.replace` is only atomic within one filesystem.

**Tests to add**

1. **Stale-file-versus-race:** a leftover `-small.jpg` against a row with `NULL`
   `thumbnail_small` is **regenerated**, and after the run all three columns are populated
   and all three files exist.
2. **Genuine race preserved:** a populated column plus an existing file is **skipped** — no
   delete, no rewrite.
3. **Partial-write residue:** a failure on the second size leaves **no partial files** behind
   (and the pre-existing files that were there before the call are untouched).
4. **All-or-nothing:** a successful call materialises all three, and the temp files do not
   survive.
5. **The `on_commit`-time property:** the repair is idempotent — running it twice is a no-op
   the second time (the Validator's own reproduction ran it twice to prove the *defect*;
   this test pins the fix).

**Keep green, do not edit** *(unless option (b) is chosen, in which case
`test_atomic_write_collision_raises_file_exists` is rewritten deliberately and the reason is
named in the commit body)*

`apps/media/tests/test_thumbnails.py` in full ·
`apps/media/tests/test_backfill_thumbnails.py` in full ·
`apps/ads/tests/test_copy_ad.py` in full (unrelated, but `submission.py` is shared).

**Gates**

`$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/media/tests/test_thumbnails.py src/backend/apps/media/tests/test_backfill_thumbnails.py --tb=short" test`
→ then `.\Makefile.ps1 test` → then both static gates.

**Risk and rollback**

- *Rollout risk: LOW* — it only changes behaviour on a failure path that currently loses
  data. *Compatibility:* yes.
- *Filesystem-vs-database consistency:* strictly improved. Before, a partial write left files
  with no row; after, the write is all-or-nothing.
- *Migration / backfill hazards:* **none.** Note that a **data** repair of already-broken
  rows is *not* scheduled — BLOCK 5 re-enables the seed path and BLOCK 6 makes the residue
  visible; re-running `backfill_thumbnails` in an environment that has real broken rows is
  an **operational** action, not this block's (§6.2).
- *Rollback:* a plain revert is safe. Files written by the new code are valid complete
  variants and are harmless under the old code's skip rule.
- *Cross-phase:* **none direct.** `_STAGING_TTL_SECONDS` and `Command.handle` belong to phase
  03; this block touches neither.

---

### BLOCK 4 — Name the stored-original JPEG quality, and route the two stale spec sentences (07-MEDIA-011)

| | |
|---|---|
| **Findings owned** | `07-MEDIA-011` (code half) |
| **Depends on** | **nothing in-plan** (serialised after BLOCK 3 because both declare a quality constant in the same module) |
| **Blocks** | BLOCK 10 (soft — the doc block must state the shipped quality), BLOCK 5 (soft — the seed block re-encodes through the same call) |
| **Priority** | **P2** |
| **Risk level** | **LOW** — a named constant, no schema change, no data destruction |
| **Required agents** | **Auditor · Researcher · Planner · Implementor · Validator** (Researcher is **mandatory** for Q07-11; **Validator is mandatory** because the finding's headline number is inherited, not re-measured) |

**Decision required before implementation — Q07-11 (re-measure the default)**

The Validator measured Pillow's default JPEG quality at **exactly 75** by MD5-matching
Pillow **12.3.0** output against explicit qualities 70/74/76/80/85. The code context did **not**
re-measure it and inherited the number, and listed it under "unverified at runtime". The
number *is* the finding, and Pillow's default is not a stable API. The Researcher performs
**one** MD5 check in-image against the Pillow version pinned in `pyproject.toml` and records
the result in the commit body. **If it is no longer 75, the finding's narrative is corrected
in the commit message, not silently.**

**What is wrong.** `strip_photo_exif` calls
`img.save(buf, format="JPEG", optimize=True, comment=b"", exif=b"")` with **no `quality`
argument**, so Pillow's default applies to every seller photo — a second re-compression on
top of the compression Telegram already applied, at a quality the code never chose out loud.
`ThumbnailService.QUALITY = 85` is an explicit class attribute in the same package, which is
the in-tree precedent for how this project expresses the choice. The defect is the **unnamed**
number, not the number: a future "optimisation pass" has nothing to reason from.

**The change.** Declare a named `STORED_JPEG_QUALITY` constant **beside**
`ThumbnailService.QUALITY` so the two are comparable at a glance, with a one-line comment
saying what it governs, and pass it at the save call. **Do not change the value** unless the
Researcher demonstrates a specific defect: the point is that the number is *chosen out loud
and reviewable*, not that it is different.

**The consequence that must be stated, not discovered later:** passing an explicit quality
changes stored bytes for **new uploads only**. Already-stored photos keep their current
encoding, so the store becomes **mixed-quality**. That is an accepted, documented consequence
— say it in the commit body and in BLOCK 10's doc text.

**The documentation half is routed, not shipped.** Two spec sentences — *"No server-side
photo optimization in phase 1"* and *"phase 1 serves full-size compressed photos"* — are
contradicted by the shipped pipeline (a full re-encode plus three derivative sizes). They sit
on `docs/01-spec/technical-specification.md`, which is **phase-06-reserved**. **Do not edit
it.** BLOCK 10 carries the written request to the coordinator (Q07-12, §5.2), and this
block's commit body records the exact replacement text so phase 06 can apply it.

**Surface**

| Path | Symbols | Change |
|---|---|---|
| `src/backend/apps/media/services/thumbnails.py` | module scope, beside `ThumbnailService.QUALITY` | declare `STORED_JPEG_QUALITY` with a one-line comment |
| `src/backend/apps/media/services/filesystem.py` | `strip_photo_exif` | pass the named quality at the save call. **A module-level constant is preferred over a new parameter** — a parameter changes a signature that two production apps and the test suite call |

**Binding constraints for the Implementor**

1. **Do not remove the EXIF/ICC strip.** `img.info.pop("exif")`, `img.info.pop("icc_profile")`
   and `exif=b""` are required and independently verified working. "Optimising" by deleting
   the re-encode is **forbidden** — the finding asks for a named constant, not a smaller file.
2. **Do not change the value** without a stated, demonstrated reason.
3. **Do not touch `technical-specification.md`** (§5.3, phase-06 reservation).
4. **Do not touch `_preprocess_one` or `generate`** — that is BLOCK 5.
5. **The `ME-003` and `HIGH-001` legacy citations in nearby test docstrings are not this
   block's** — the `ME-003` one is BLOCK 8's.

**Tests to add**

1. A stored original encodes at the **named constant** — asserted by reading the constant the
   save call uses, **not** by asserting the literal `85` or `75`. The property under test is
   *"the quality is declared, named and used"*, which is the finding.
2. The two quality constants are declared **adjacently**, so a reviewer can compare them —
   asserted by import, not by reading the source text.
3. The **behavioural** contracts are untouched: dimensions preserved, EXIF stripped, ICC
   stripped, JPEG comment removed, XMP packet removed, no disk write from the strip call.
   These are the eight existing `TestStripPhotoExif` tests and they must stay green
   **unchanged** — they assert behaviour, not bytes, and the whole point is that the
   constant does not perturb them.

**Keep green, do not edit**

`apps/media/tests/test_filesystem.py::TestStripPhotoExif` (8 tests) ·
`apps/media/tests/test_save_photo_exif.py` in full ·
`apps/ads/tests/test_media_security.py::TestExifStripping` (6 tests) ·
`apps/media/tests/test_media_config.py::test_max_image_pixels_is_set` ·
`apps/media/tests/test_thumbnails.py` in full (BLOCK 3's file — do not perturb it).

**Gates**

`$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/media/tests/test_filesystem.py src/backend/apps/media/tests/test_save_photo_exif.py --tb=short" test`
→ then `.\Makefile.ps1 test` → then `uv run ruff check src/` and `uv run basedpyright src/`.

**Risk and rollback**

- *Rollout risk: LOW.* No schema change, no data destruction, no behavioural contract
  altered. *Compatibility:* yes.
- *Stored-bytes effect:* one-way. New uploads encode at the named quality; existing uploads
  keep theirs. A revert does **not** restore the previous bytes for already-stored files, and
  the mixed-quality store is the accepted, documented cost.
- *Filesystem-vs-database consistency:* unaffected — no row and no key changes.
- *Migration / backfill hazards:* **none.**
- *Served URLs:* unchanged.
- *Rollback:* a plain revert.

---

### BLOCK 5 — Stop the seed pipeline asserting thumbnails it never wrote (07-MEDIA-008)

| | |
|---|---|
| **Findings owned** | `07-MEDIA-008` |
| **Depends on** | **BLOCK 3** (hard — this block *reuses* that block's stale-file-versus-race guard) |
| **Blocks** | nothing in-plan |
| **Priority** | **P2** |
| **Risk level** | **LOW-MEDIUM** — dev/demo path only, but it changes a return type a shipped test calls directly |
| **Required agents** | **Auditor · Researcher · Planner · Implementor · Validator** |

**Why this is a separate block from BLOCK 4.** They share one call (`strip_photo_exif`) but
they are **different findings with different risk profiles, different verification and
different blast radii**. `MEDIA-011` is a named constant on the live upload path;
`MEDIA-008` is a data-integrity defect in the seed pipeline, dev/demo only, whose fix changes
a function's return contract. BLOCK 3 supplies the guard this block reuses, so it must be
adjacent to BLOCK 3 in the order — it is. Keeping them separate means the full-suite run
BLOCK 5 requires is scoped to the block that actually needs it.

**Why it must not precede BLOCK 3.** `MEDIA-008`'s fix depends on the *stale-file-versus-
race* discrimination that `MEDIA-004`'s fix introduces. Fixing 008 first re-introduces the
defect class it inherits: a half-written seed variant would be skipped rather than
regenerated, and the row would still assert a file that does not exist. **Hard edge
3 → 5.**

**What is wrong.** `ImageGenerator._preprocess_one` checks `if os.path.exists(f"{stem}-small.jpg"): return True`
for **one of the three** outputs it is caching, then calls `generate_thumbnails` inside a
`try/except FileExistsError` that logs and returns `True` anyway. Meanwhile
`ImageGenerator.generate` builds every `AdImage` with
`thumbnail_small/medium/large` from the static `_thumbnail_key` string helper and **never
consults the `ThumbnailService` return value it already holds**. The database therefore
asserts `-medium.jpg` and `-large.jpg` that were never written. Both escape routes are closed:
`_walk_media_files` skips `seed/` so the sweep never reclaims, and `backfill_thumbnails` hits
the same `O_EXCL` guard (BLOCK 3 fixes that guard; **that is the dependency**).

**The fix removes the defect class, not the instance.** `_preprocess_one` returns the
**actual generated keys** (or a truthful `None`), and `generate()` builds the row's
`thumbnail_*` fields from that return value — so the database can never assert a file that
was not written. The single-variant cache check is either **extended to all three variants**
or **dropped** in favour of `ThumbnailService`'s own idempotency, which after BLOCK 3 handles
"already generated" correctly. **The Planner records which, with the reason.** Dropping it is
the smaller change and is what makes the truthful return sufficient; extending it is the
smaller diff for a caller that does not want to re-encode on every seed run.

**Surface**

| Path | Symbols | Change |
|---|---|---|
| `src/backend/apps/seed/generators/images.py` | `ImageGenerator._preprocess_one` | return the actual generated keys or a truthful `None`; extend or drop the single-variant cache check; **reuse BLOCK 3's stale-file guard** |
| `src/backend/apps/seed/generators/images.py` | `ImageGenerator.generate` | build the three `thumbnail_*` fields from `_preprocess_one`'s return value instead of from `_thumbnail_key` alone |
| `src/backend/apps/seed/generators/images.py` | `ImageGenerator._thumbnail_key` | becomes the fallback for the sizes that genuinely were generated. **Do not delete it** — tests assert key *shape*, and it is still the right way to compute a key |
| `src/backend/apps/seed/services/seed_service.py` | `SeedService._backfill_image_hashes` *(read only, unless the Researcher's finding requires it)* | confirm a `NULL` thumbnail column does not break the hash re-read |

**Binding constraints for the Implementor**

1. **`MEDIA-003`/`DB-005` is out of scope, and this block must not drift into it.**
   `_walk_media_files` skips `seed/` and that exclusion is **phase-03 BLOCK 8's** to change.
   This block changes **what the generator records**, not **what the sweep excludes**. Phase
   07 ships no staging-window fix.
2. **`_preprocess_one` is called directly by a shipped test**
   (`test_seed.py::TestImageGenerator::test_seed_original_strips_jpeg_comment`, which asserts
   a **truthy** return). A return-type change lands there. Update it **only** to match the new
   return contract, with the reason named, and **preserve the EXIF-stripping assertion** — that
   is the test's real subject.
3. **`seed_service.py` uses `AdImage.objects.bulk_create(..., batch_size=5000)`**, which
   **skips `AdImage.save()`** and therefore its containment assert and SHA-256 computation;
   `_backfill_image_hashes` then re-reads each file and `update()`s the hash. A row whose
   `thumbnail_*` column is now `NULL` must not break that re-read. The **Researcher states
   whether it tolerates a `NULL` thumbnail**, and the block adds a test that says so rather
   than assuming.
4. **The full suite must be run, not the fast gate.**
   `TestSeedCommandEnhanced::test_media_cleanup` is `@pytest.mark.real_images` and is in the
   `seed` marker the fast gate skips. **This is the only block in the plan that requires
   `$dc run --rm test`.**
5. **Do not touch `strip_photo_exif` or `STORED_JPEG_QUALITY`** — that is BLOCK 4.

**Tests to add**

1. After `ImageGenerator.generate`, **every** `thumbnail_*` value on **every** created row
   points at a file that actually exists on disk — asserted over the whole generated set, not
   a single row. **This is the finding.**
2. A half-written state (original + only `-small.jpg` present) is **regenerated**, not
   reported as complete — i.e. BLOCK 3's guard is genuinely reused, and this test would fail
   if the guard were bypassed or re-implemented differently.
3. `_preprocess_one` returns something falsy when it cannot produce the thumbnails it would
   otherwise claim, and `generate()` respects that: **no row is written asserting a file that
   does not exist.**
4. A `seed_service` run over the **shipped** manifest (whose `default.photos` is empty —
   C-1) still produces a store that reconciles against its rows. This asserts C-1's fact
   rather than assuming it, and it is the test that would fail if someone "fixed" the seed
   path on the false default-pool narrative.
5. `test_seed_original_strips_jpeg_comment` updated to the new return contract, with the
   EXIF-stripping assertion preserved.

**Keep green, do not edit**

`apps/seed/tests/test_seed.py::TestImageGenerator::test_generates_ad_images` ·
`::test_image_keys_have_correct_format` · `::TestSeedCommandEnhanced::test_media_cleanup` ·
`apps/media/tests/test_thumbnails.py` in full (BLOCK 3's file) ·
`apps/media/tests/test_filesystem.py` in full (BLOCK 4's file).

**Gates**

`$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/seed/tests/test_seed.py --tb=short" test`
→ then **`$dc run --rm test` (the full suite — the nightly `seed` marker)** →
then `uv run ruff check src/` and `uv run basedpyright src/`.

**Risk and rollback**

- *Rollout risk: LOW.* Dev/demo environments only — the spec scopes `seed` to development.
  *Compatibility:* yes.
- *Filesystem-vs-database consistency:* this block is **the** fix for the seed half of the
  class BLOCK 6 makes detectable. `seed_service._clean` `shutil.rmtree`s the whole `seed/`
  directory and recreates it, so a **reseed is non-destructive** (seed data only) and is the
  operational recovery.
- *Migration / backfill hazards:* **none** — no schema change. A reseed is a data operation
  and is an **operator's** decision, not this block's (§6.2).
- *Rollback:* a plain revert. The return-type change is fully reversible; no data is lost,
  because a revert restores the *over-claiming* behaviour, not destroyed bytes.

---

---

### BLOCK 6 — Detect the dangling rows the reconciler does not cover (07-MEDIA-012 + the rubric §4.7 assertion)

| | |
|---|---|
| **Findings owned** | `07-MEDIA-012`, plus the **store↔database reconciliation assertion** and the **`deleted += 1` miscount** folded in from `MEDIA-003` → `DB-005` |
| **Depends on** | **nothing in-plan.** External: **phase-03 BLOCK 6** (`_STAGING_TTL_SECONDS`) and **phase-03 BLOCK 8** (`_walk_media_files`, `_reclaim_stale_staging`, `Command.handle`) — a **hard** external gate |
| **Blocks** | BLOCK 7 (same function) |
| **Priority** | **P1** |
| **Risk level** | **HIGH** — three-way file contention, and the block edits the one function the phase is most likely to conflict on |
| **Required agents** | **Auditor · Researcher · Planner · Implementor · Validator — all five** |

**Why this is the guardrail and why it is still scheduled here.** `media_gate` runs three
checks — key containment, a referencing `AdImage` row, and an authorization predicate on that
row's ad — and then, under `DEBUG=False`, returns `200 OK` with an `X-Accel-Redirect` to
`/protected-media/<key>`. **There is no `os.path.exists` / storage-existence check on that
branch**; existence is checked only in the `DEBUG=True` fallback. So a dangling key yields
HTTP 200, a valid header, a 404 at the browser from nginx's `internal` block, **no log
record, no exception and no metric anywhere in the stack.** The system has a
**unidirectional** reconciler — the sweep deletes files nobody references — and **no
detector at all** in the other direction. Every dangling row produced by `MEDIA-001`,
`MEDIA-004`, `MEDIA-008` or `DB-005` is invisible until a human notices, and then
unrecoverable without seller re-upload, because the original bytes are gone and
`backfill_thumbnails` regenerates only derivatives.

**Why it is NOT on the request path.** §0.2.2 hazard 1: a filesystem check in `media_gate`
breaks `TestMediaAccessControl` (9), `TestMediaGateDeclinedUser` (3),
`TestMediaGateThumbnailResolution` (7) and `TestMediaGateCacheControl` (9), because
`_create_ad_with_image` writes a physical file only when both `media_root=` and
`file_bytes=` are supplied and most call sites supply neither. The sharpest single case is
`::test_shared_seed_key_across_multiple_ads_returns_200`, which creates two distinct PUBLISHED
ads sharing `seed/birds_04.jpg`, asserts `200` + `X-Accel-Redirect`, and deliberately writes
**no file** — it is a shared-key *serving* guard whose entire subject is the row and
authorization logic. Detection belongs in the sweep. **This is binding and non-negotiable.**

**Decision required before implementation — Q07-9 (scope and signalling)**

`_walk_media_files` excludes `seed/` and `staging/`; `_collect_referenced_keys` covers all
four columns and excludes nothing. The two directions therefore have different scopes, and
`VAL-005` records that the original Auditor's store↔database diff **excluded `seed/`** —
precisely the directory where most shared keys live.

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | A `--check` (or `--dry-run`-adjacent) **flag** on `sweep_orphaned_media` that lists keys with no file, plus a stderr summary line. Reuses `AdvisoryLockId.SWEEP_ORPHANED_MEDIA` — the check is read-only and cheap | **Gains:** no new command, no new lock id, no scheduler change, no new `AdvisoryLockId` (which would collide with BLOCK 8's allocation). **Costs:** no machine-readable exit status, so a scheduler or CI cannot gate on it without parsing text |
| **(b)** | A distinct **exit code** (and/or `--json`) when a dangling row is found | **Gains:** gateable, alerting-friendly — which is what phase 12 needs. **Costs:** a non-zero exit from a command that is otherwise non-destructive is a behaviour change for anything that shells out to it; `test_sweep_lock_structure.py::TestSweepLockScope::test_delete_photo_called_within_lock_scope` and the scheduler's own exit handling must be checked for the new code path |
| **(c)** | Both, with a scope switch (`--include-seed`, `--include-staging`) | **Gains:** the most complete, and it makes the reconciliation **symmetric** with the sweep's own exclusions. **Costs:** the most surface, and the sweep's exclusions are **phase 03 BLOCK 8's to change** — a `--include-staging` flag that *reports* on a directory the sweep *ignores* is a second, contradictory policy statement in the same file |

**Scope question that must be answered regardless of option:** does the report cover `seed/`
and `staging/`? **A reconciliation that excludes `seed/` is the defect `VAL-005` records.**
The Planner records the answer with its reason. Extending `_walk_media_files` to *include*
`seed/` for the **report** direction is a phase 03 BLOCK 8 question and must not be decided
here — a report-only scope that does not change the sweep's deletion scope is safe, and that
is the likely shape.

**Surface**

| Path | Symbols | Change |
|---|---|---|
| `src/backend/apps/media/management/commands/sweep_orphaned_media.py` | `Command.add_arguments` | add the check mode / flag / exit-code surface per the chosen option |
| `src/backend/apps/media/management/commands/sweep_orphaned_media.py` | `Command.handle` | the dangling-row report; and the **`deleted += 1` fix** — it currently increments per **attempt**, not per confirmed removal, so `"Deleted N orphaned media files"` is not a measurement. Either have `delete_photo` report whether it removed anything, or verify after the loop. `delete_photo` currently returns `None`, so this is a small, explicit contract addition |
| `src/backend/apps/media/management/commands/sweep_orphaned_media.py` | `_collect_referenced_keys`, `_walk_media_files` | **read-only unless the Q07-9 scope answer requires a report-only extension.** Both are **phase-03 BLOCK 8's**; do not change the *deletion* scope |
| `src/backend/apps/media/tests/` | a new store↔database reconciliation test | the rubric §4.7 assertion, **including `seed/`** |
| `src/backend/apps/ads/tests/test_media_security.py` | **read-only** | it must stay green **unchanged** — that is the proof that detection did not leak into `media_gate` |

**A working precedent exists for the loop:** `seed_service._backfill_image_hashes` already
performs `os.path.exists(MEDIA_ROOT / img.image)` per row. Follow it.

**Binding constraints for the Implementor**

1. **`media_gate` is read-only in this block.** No `os.path.exists`, no `FileResponse`, no
   cache-header change. §0.2.2 hazard 1.
2. **Reuse `AdvisoryLockId.SWEEP_ORPHANED_MEDIA`.** The report is read-only and the
   `test_delete_photo_single_call.py` control case already exercises this command. **Do not
   allocate a new `AdvisoryLockId` here** — BLOCK 8 needs that integer.
3. **Any deletion this block performs must stay inside the lock scope.**
   `test_sweep_lock_structure.py::TestSweepLockScope::test_delete_photo_called_within_lock_scope`
   asserts every `delete_photo` call happens while the lock is held. A read-only report mode
   does not violate it; the `deleted += 1` fix must not move a call out of it.
4. **All nine existing `test_sweep_orphaned_media.py` tests must stay green**, including
   `test_seed_subdir_excluded`, `test_staging_file_survives_sweep`,
   `test_stale_staging_file_reclaimed` and `test_fresh_staging_file_preserved`. **A
   dangling-row report mode must not disturb any of them** — in particular the two exclusion
   tests, which is where a scope mistake shows up first.
5. **Do not change `_STAGING_TTL_SECONDS`.** It is phase-03 BLOCK 6's.
6. **The new assertion must be a test, not a command invocation.** Rubric §4.7 asks for the
   diff; a test is the only thing that runs on every commit.

**Tests to add**

1. **The store↔database reconciliation**, after the suite's own create/delete cycles:
   **zero dangling rows** — every `AdImage` key in every column has a file — **and zero
   orphan files** in the swept scope, with **`seed/` included**. This is the assertion that
   would have caught `MEDIA-001`, `MEDIA-004` and `MEDIA-008` at their source.
2. The check mode **reports** a row whose file has been removed and **reports nothing** when
   the store and the database agree.
3. The exit code / JSON, if that option is chosen: a dangling row produces the documented
   status, and a clean run does not.
4. **`deleted += 1` counts removals, not attempts:** a `delete_photo` that fails is not
   counted, and the success line reflects reality. *(Assert behaviour — that the reported
   count matches the number of files actually gone — never the log string itself.)*
5. **The negative proof:** `media_gate` still returns `200` + `X-Accel-Redirect` for a
   shared key with **no file on disk** — i.e. `test_shared_seed_key_across_multiple_ads_returns_200`
   is green **unchanged**. This is the test that proves the finding was fixed in the right
   place.

**Keep green, do not edit**

`apps/media/tests/test_sweep_orphaned_media.py` in full ·
`apps/core/tests/test_delete_photo_single_call.py::test_sweep_orphaned_media_delete_photo_once_per_key` ·
`apps/core/tests/test_sweep_lock_structure.py` in full ·
`apps/ads/tests/test_media_security.py` in full ·
`apps/core/tests/test_observability.py` in full.

**Gates**

`$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/media/tests/test_sweep_orphaned_media.py src/backend/apps/ads/tests/test_media_security.py src/backend/apps/core/tests/test_sweep_lock_structure.py --tb=short" test`
→ then `.\Makefile.ps1 test` → then both static gates.

**Risk and rollback**

- *Rollout risk: LOW* — read-only, plus a report mode. *Compatibility:* yes.
- *Rollout risk (external): MEDIUM* — a merge conflict with phase 03 BLOCK 8 is the realistic
  failure, not a logic error. Mitigation: the external gate; §5.3 names the file; the block
  re-reads immediately before editing and stages explicitly.
- *Filesystem-vs-database consistency:* this block is the **only** thing in the phase that
  makes the other direction observable. Its value is not in fixing anything — it is in
  bounding detection latency from unbounded to one sweep period.
- *Migration / backfill hazards:* **none.** **Automatic repair is explicitly out of scope**
  (§6.2): the original bytes are gone, so "repair" would mean nulling columns or deleting
  rows, both of which are destructive and are an operator's decision informed by the report.
- *Rollback:* a plain revert. The report is read-only; the `deleted += 1` fix changes a
  number, not an outcome.
- *Cross-phase:* **phase 03 BLOCK 8 must have landed or must be scheduled around this block.**
  `DB-005` should cross-reference this finding rather than assert that detection is
  impossible (§5.2).

---

### BLOCK 7 — A staging byte budget beside the TTL, and a `staging_bytes` gauge (07-MEDIA-007)

| | |
|---|---|
| **Findings owned** | `07-MEDIA-007` |
| **Depends on** | **BLOCK 6** (hard — the same `Command.handle`) |
| **Blocks** | nothing in-plan |
| **Priority** | **P1** |
| **Risk level** | **MEDIUM** — a new rejection branch on a live user path, with an i18n deliverable |
| **Required agents** | **Auditor · Researcher · Planner · Implementor · Validator — all five** |

**What is wrong.** Every accepted photo is written to `MEDIA_ROOT/staging/<uuid>.jpg` and the
whole directory is **excluded** from the orphan sweep. The only reclamation is
`_reclaim_stale_staging(media_root, _STAGING_TTL_SECONDS)` with
`_STAGING_TTL_SECONDS = 2 * 60 * 60` — a **time** policy with no **space** policy anywhere.
Admission control is measured in events (10 uploads / 60 s per `user_id`) and count (5 photos
per FSM list), not in bytes; `MAX_PHOTO_BYTES` (2 MB) is per photo, and it is enforced
pre-download and again by the bounded download writer — so a scripted account can accumulate
≈2.4 GB of permanently-unreferenced staging bytes **inside one TTL window**, on a volume
shared with nginx, the web tier and `/protected-media/`. Exhaustion stops photo serving for
the **whole site**, not just for the abusive seller. This is a slow-burn availability vector,
not an instant outage, and the report rates it MEDIUM for that reason.

**The TTL stays.** It is the right backstop *once* a space-based guard exists. Do not
replace it, lower it, or "simplify" by deleting it. And do not touch the constant — it is
**phase-03 BLOCK 6's** (`03-DB-003`), and the budget must be designed against the TTL that
block settles, not against today's 2 h.

**Decision required before implementation — Q07-7 (global or per-seller?)**

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | **Global** budget on `MEDIA_ROOT/staging` as a whole | **Gains:** implementable with what exists. The key format `staging/<uuid>.jpg` is **deliberately PII-free** — it carries no `user_id`, no `telegram_id`, no `username` — and adding attribution would mean either a key-format change (which would break the media gate's unguessability rationale and every `AdImage` key `CheckConstraint`) or a side table (a migration, a model, and a second thing to reconcile). **Costs:** one seller can trip a **global** rejection — a legitimate seller is refused an upload because an abusive account filled the volume. That is a real fairness cost and the message must not pretend otherwise |
| **(b)** | **Per-seller** budget | **Gains:** no cross-seller denial; the abusive account is contained alone. **Costs:** requires per-seller attribution, which the deliberately PII-free key format does **not** carry. Either the staging key changes (breaking the unguessability contract, the `KEY_FORMAT_REGEX`-derived `CheckConstraint`s and every `AdImage.storage_keys()` consumer) or a mapping is introduced. That is a **schema and storage-contract change** for a MEDIUM availability finding |
| **(c)** | Global budget **plus** an FSM-reset cleanup that deletes the seller's own staged files when the counter is dropped (`/cancel`, walk-away) | **Gains:** keeps (a)'s simplicity and adds a targeted reduction. **Costs:** `cmd_cancel` currently deletes only the **current draft's** keys via `delete_photo(photo["storage_key"])` before `delete_draft(...)`, while `state.clear()` drops the counter regardless of status — so the cleanup's exact shape and what happens to `state["photos"]` afterwards is a design question, and the FSM list is the source of truth `cmd_cancel`'s existing cleanup relies on |

**The Researcher's job on Q07-7 is feasibility, not preference:** state whether per-seller
attribution is achievable *without* changing the staging key format or adding a table. If it
is not, that is a finding the Planner records and (a) or (c) follows. **This plan does not
choose.**

**Decision required before implementation — Q07-8 (gauge semantics across processes)**

`django-prometheus` runs in **multiprocess** mode (`PROMETHEUS_MULTIPROC_DIR`) and the sweep
runs in a **different process** from web and bot. A `Gauge` updated only on the hourly sweep
is a **stale** reading for alerting — up to an hour old, which is the entire window the
finding is about. The Researcher states what is actually achievable: a `Gauge.set()` per
upload in the bot process (a real-time reading, at the cost of a `scandir` on the upload path
and multiprocess-gauge lifetime semantics), a sweep-only `Gauge` (cheap, stale, and
phase 12's alerting decision), or a **counter** of bytes accepted instead of a gauge (a
monotone total, which is what a capacity alert actually wants). **This is phase 12's
alerting decision to consume; phase 07 supplies the read surface and states which semantics
it shipped.**

**A cost note the block must respect.** Computing the staging size is an `os.walk` of one
directory. On the upload path that is acceptable only if bounded — `os.scandir` over the top
level, or a counter accumulated by the sweep and **read** by the upload path rather than
recomputed. The sweep already walks the directory hourly; reusing its number is strictly
cheaper than a second walk, and it is the natural answer to the staleness half of Q07-8.

**Surface**

| Path | Symbols | Change |
|---|---|---|
| `src/backend/config/settings/base.py` | settings block near `MEDIA_ROOT` / `MEDIA_URL` | a **configured** byte budget (project rule 10: settings-driven, not a hard-coded constant). Append; do not reorder a setting another phase annotated |
| `src/backend/config/settings/prod.py` *(only if the budget must be environment-overridable)* | prod overrides | follow the existing pattern; re-read immediately before editing — it is phase-02 territory |
| `src/telegram_bot/handlers/ad_create/photos.py` | `process_photos` | reject the upload when `MEDIA_ROOT/staging` exceeds the budget, with a **translated** message. Note the ordering already enforced: 5-photo cap → `check_upload_rate_limit` → `MAX_PHOTO_BYTES` pre-check → bounded download → `validate_photo` → `save_photo`. **The budget check must be cheap and must come before the download** |
| `src/telegram_bot/handlers/ad_create/entry.py` | `cmd_cancel` | only under Q07-7 option (c) |
| `src/backend/apps/media/management/commands/sweep_orphaned_media.py` | `Command.handle` | only under the Q07-8 answer, and then **extend** — never define a second exclusion or reclamation policy |
| `src/backend/locale/{ru,bs,en}/LC_MESSAGES/django.po` | append-only | the new rejection message: **non-empty `ru` and `bs`** |
| metric exposure | `staging_bytes` | per the Q07-8 answer; `/metrics` is already mounted at the URL root and proxied by nginx behind `allow 127.0.0.1; deny all;` |

**Binding constraints for the Implementor**

1. **i18n is part of DoD.** The rejection message is user-visible. `ru` **and** `bs` msgstr
   must be non-empty or `apps/ads/tests/test_i18n_completeness.py` fails. **Append** to the
   `.po` files; never regenerate wholesale (phases 05, 06, 11 and 14 share them).
2. **Do not change `_STAGING_TTL_SECONDS`** (phase-03 BLOCK 6) and do not remove the TTL.
3. **Do not change the sweep's exclusion set.** `/media/staging/**` is inside the swept
   `MEDIA_ROOT` but excluded by directory — a `staging_bytes` gauge is therefore **not**
   double-counted by the orphan sweep, and equally the directory is invisible to every current
   reconciler, which is exactly the blind spot this block is closing.
4. **Do not change the 5-photo cap, the 10/60 s rate limit, or `MAX_PHOTO_BYTES`.** The budget
   is an *additional* guard, not a replacement.
5. **Do not attribute staging files to sellers** unless Q07-7 concludes it is possible
   without a key-format change or a new table. The PII-free key format is a design property,
   not an oversight.
6. **`Command.handle` is edited in BLOCK 6 too** — the hard edge, and the reason the
   re-immediate-read rule applies.

**Tests to add**

1. An upload is **rejected with the translated message** when the staging directory exceeds
   the budget, and the message resolves in `ru` and `bs` (non-empty `msgstr`).
2. An upload is **accepted** when it is under the budget — the positive case, asserted
   explicitly, not only the rejection.
3. A **rejected upload writes no file**: the rejection happens before the download, so no
   bytes and no key are consumed.
4. Under Q07-7 option (c), `/cancel` deletes **that seller's** staged keys and leaves another
   seller's staged files untouched.
5. The TTL path still works: a **fresh** staging file is preserved and a **stale** one is
   reclaimed — i.e. the budget addition did not disturb `test_fresh_staging_file_preserved`
   or `test_stale_staging_file_reclaimed`, and the new test proves it rather than assuming.

**Keep green, do not edit**

`apps/media/tests/test_sweep_orphaned_media.py` in full ·
`apps/core/tests/test_observability.py` in full (the `/metrics` substrate) ·
`src/backend/tests/test_nginx_config.py::test_nginx_metrics_restricted_to_localhost`
(unchanged — this block adds no nginx surface) ·
`apps/ads/tests/test_i18n_completeness.py` green.

**Gates**

`$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/media/tests/test_sweep_orphaned_media.py src/backend/apps/ads/tests/test_i18n_completeness.py --tb=short" test`
→ then `.\Makefile.ps1 test` → then both static gates.

**Risk and rollback**

- *Rollout risk: LOW-MEDIUM.* The behaviour change is narrow (one rejection branch) and the
  failure is a refused upload, not data loss.
- *Filesystem-vs-database consistency:* unaffected. No row is created or destroyed.
- *Migration / backfill hazards:* **none** — a setting and a threshold, not a schema change.
- *Rollback:* a plain revert, plus a note that a **global** budget can refuse a legitimate
  seller while an abusive account fills the volume. The compensating control is the
  `staging_bytes` gauge, which is why the metric is part of the block and not an optional
  extra.
- *Cross-phase:* `config/settings/base.py` is shared with phase 02 and phase 04 — append only,
  re-read immediately (§5.3).

---

### BLOCK 8 — Give `MediaDeletionError` a reader, a retention policy and an admin surface (07-MEDIA-010 + the `ME-003` traceability reconcile)

| | |
|---|---|
| **Findings owned** | `07-MEDIA-010`, plus the **`ME-003` traceability** non-finding work item |
| **Depends on** | **nothing in-plan.** Contends externally with **phase-06 BLOCK 15**, which also appends to `HOURLY_COMMANDS` and also allocates an `AdvisoryLockId` |
| **Blocks** | nothing in-plan |
| **Priority** | **P2** |
| **Risk level** | **MEDIUM** — the lock-id allocation is a three-file, one-commit, coordinator-notified change |
| **Required agents** | **Auditor · Researcher · Planner · Implementor · Validator — all five** |

**What is wrong.** `MediaDeletionError` (`db_table = "media_deletion_errors"`) is written by
`_record_deletion_error` whenever `delete_photo` exhausts its three retries with exponential
backoff. The whole write is wrapped in a `try/except` and never raises. And then: **no reader,
no prune, no `expires`, no alert, not in `admin.site._registry`, and zero references in
`docs/` or `docker/`.** The designed escalation path cannot be used — an operator must know
to `psql` the table — and the table is itself an unbounded growth source that masks the
signal it exists to raise. A persistent condition (a read-only `MEDIA_ROOT`, an immutable
mount) writes one row per key per sweep run, forever. LOW is the right rating because the
`logger.error` line keeps the underlying condition visible; nothing is silently lost.

**Decision required before implementation — Q07-10 (is the admin registration additive?)**

`apps/media/admin.py` **does not exist** — this would be a new file in an app that has none,
and Django's auto-discovery would then put `MediaDeletionError` into `admin.site._registry`.
The report quoted a full registry list from introspection; the code context did **not** locate
a shipped test that asserts that exact set, and flagged the question. The Researcher answers
it with one grep and one test run: if a test asserts the **exact** set of
`admin.site._registry` keys, the registration is disruptive and that test must be updated
**deliberately, with the reason named**; if not, it is purely additive and nothing else
moves. **This plan does not guess.** Note that `VAL-006` is the standing rule for this class
of claim: for any statement about an admin capability, introspect
`admin.site._registry[Model].get_form(request)` and `get_actions(request)` — do not infer
from the permission flags in source.

**Decision required before implementation — Q07-14 (retention command, or admin action, or both?)**

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | A `sweep_media_deletion_errors --older-than N` command, added to `HOURLY_COMMANDS`, with a **new** `AdvisoryLockId` member, `--dry-run`, and an admin registration as the read surface | **Gains:** bounds the table, which is the half of the finding that is a *growth* problem; the report's own amendment. **Costs:** a new lock id (three files, one commit, coordinator told first), a `HOURLY_COMMANDS` entry that changes `test_scheduler_wiring.py` and `test_sweep_lock_structure.py`, and the TTL number `N` is a judgement call that is **not** obviously a legal or product one here — the rows are diagnostic, not personal data |
| **(b)** | **Admin-only**: register the model with `created_at` / `error_type` filters and a `readonly_fields`-only change form, and stop there | **Gains:** the report's **minimum**; the read path exists and the growth problem is visible and therefore someone else's decision. **Costs:** the table keeps growing without bound, which is half the finding |
| **(c)** | (a) **plus** an admin action to clear selected rows | **Gains:** an operator can act without shell access, and the action is auditable in the UI. **Costs:** a **new** write surface on a model in an app with no admin yet; more i18n; more surface to get right for a LOW |

**This plan's read, not a decision:** (a) with a **recorded** TTL and a mandatory `--dry-run`
is the fuller shape and matches the report; (b) is defensible for a LOW and is a legitimate
outcome of the Q07-14 gate. The Planner records the option and the accepted consequences.

**The lock-id rule is absolute.** `AdvisoryLockId` is a **contract**; reusing an id is how
two commands serialise silently, and `test_advisory_lock_ids.py` will **not** catch reuse —
this is a human rule, not an automated one. The new member requires **three files in one
commit**: `apps/core/enums.py`, the lock-allocation table in
`apps/core/utils/advisory_lock.py`'s module docstring, and
`apps/core/tests/test_advisory_lock_ids.py`. **The next free integer is 14, not 13** (C-4) —
a concurrent phase-02 agent took `13` in an unstaged working-tree change that will land.
**Re-read `enums.py` immediately before allocating.** Never renumber an existing member;
`CONSENT_HARD_DELETE == 3` and every other id is fixed.

**Surface**

| Path | Symbols | Change |
|---|---|---|
| `src/backend/apps/media/admin.py` | *(new file)* `MediaDeletionErrorAdmin` | register with `list_display`, `list_filter` on `created_at` / `error_type`, a `search_fields` entry, and a `readonly_fields`-only change form. Follow `LoginTokenAdmin` / `ConsentRecordAdmin`, not a new pattern |
| `src/backend/apps/media/management/commands/sweep_media_deletion_errors.py` | `Command` *(new, under option (a))* | retention sweep, `--older-than` (with a recorded default), **mandatory `--dry-run`**, taking a new `AdvisoryLockId` and running **inside** `transaction.atomic()` with `session=False`, exactly as every entry in `test_sweep_lock_structure.py::SWEEP_COMMANDS` does |
| `src/backend/apps/core/utils/scheduler.py` | `HOURLY_COMMANDS` | append the new command name. Note `_validate_commands` **does not raise** if a command is missing from the list — it is simply never dispatched, and `test_scheduler_wiring.py` will notice |
| `src/backend/apps/core/enums.py` + `apps/core/utils/advisory_lock.py` + `apps/core/tests/test_advisory_lock_ids.py` | `AdvisoryLockId` | the new member, the docstring table, the guard test — **one commit** |
| `src/backend/apps/core/tests/test_sweep_lock_structure.py` | `SWEEP_COMMANDS`, `_LOCK_TARGET_MODULES` | add the new command to **both** lists |
| `src/backend/apps/media/models.py` | module docstring | the **`ME-003` traceability reconcile**: the docstring cites a prior-cycle finding id that is not resolvable from the repository. Restore the traceability or drop the id, in the same commit that touches the model. **Do not** add a new bare finding id in its place — use `07-MEDIA-0NN` |
| `src/backend/apps/media/management/commands/sweep_orphaned_media.py` | the `deleted += 1` counter | **already delivered in BLOCK 6.** This block only needs to note that the same defect class is what makes this table necessary |

**Binding constraints for the Implementor**

1. **Coordinator told before the enum is touched**, and the three files change in one commit.
2. **Re-read the free integer** at the moment of allocation (C-4).
3. **`delete_photo`'s existing contract is unchanged** by this block: the three-attempt
   backoff, the `logger.error`, and the never-raise `_record_deletion_error` are all
   load-bearing. The block adds a **reader**; it does not change the writer.
4. **The alert predicate belongs to phase 12.** Phase 07 supplies the read surface only. The
   predicate is simply
   `MediaDeletionError.objects.filter(created_at__gt=now() - 1h).exists()` — record it in the
   block's commit body or the docstring so phase 12 can consume it, and add **no** alerting.
5. **`_record_deletion_error` must keep swallowing its own errors.** A failure to record a
   failure must never propagate into a delete path.
6. If option (a) is chosen, `--dry-run` deletes nothing, and a row **inside** the TTL survives
   with its message intact.

**Tests to add**

1. `MediaDeletionError` is reachable through the admin changelist with a `created_at` and an
   `error_type` filter, and its change form exposes **no** editable field. *(Assert the
   *absence of an edit surface*, not an enumerated field count.)*
2. Under option (a): `--dry-run` deletes nothing; a real run deletes a row past the TTL and
   **keeps** a row inside it; running it twice is a no-op the second time; the scheduler still
   starts with the new `HOURLY_COMMANDS` entry.
3. The new command takes the lock **inside** `transaction.atomic()` with `session=False` —
   proven by the existing `test_sweep_lock_structure.py` machinery, not by a new bespoke spy.
4. A failing `delete_photo` still records a row **and** still does not raise — the never-raise
   contract, preserved.
5. If Q07-10 finds an exact-registry-set test: it is updated **deliberately**, the reason is
   named, and the diff adds no other assertion.

**Keep green, do not edit**

`apps/media/tests/test_filesystem.py::TestDeletePhoto` in full (including
`::test_delete_photo_logs_media_deletion_error_on_retry_exhaustion`, which cites `ME-003`) ·
`apps/core/tests/test_advisory_lock_ids.py` in full (unless the new member requires the
three-file change) · `apps/core/tests/test_sweep_lock_structure.py` in full ·
`apps/core/tests/test_scheduler_wiring.py` in full ·
`apps/media/tests/test_sweep_orphaned_media.py` in full.

**Gates**

`$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/core/tests/test_advisory_lock_ids.py src/backend/apps/core/tests/test_sweep_lock_structure.py src/backend/apps/core/tests/test_scheduler_wiring.py src/backend/apps/media/tests/test_filesystem.py --tb=short" test`
→ then `.\Makefile.ps1 test` → then both static gates.

**Risk and rollback**

- *Rollout risk: LOW* — additive, no data destroyed on the first run. *Compatibility:* yes.
- *Migration / backfill hazards:* **none.** The table and its migration already exist. **A
  retention sweep is destructive** — hence the mandatory `--dry-run`, a recorded TTL, and the
  statement in §8 that a revert does **not** restore purged rows. A mis-set TTL is
  corrected forward, never by "restoring the data".
- *Lock hazard:* the highest-probability process failure in the block is a **silent
  id collision**, which no test catches. The three-file-one-commit rule and the re-read are
  the control.
- *Rollback:* a plain revert of the code. Rows already purged by a retention run **do not
  return**; say so in the commit body.
- *Cross-phase:* **phase-06 BLOCK 15** also appends to `HOURLY_COMMANDS` and also allocates a
  lock id. Both phases allocate "the next free integer" and can collide. **The coordinator
  sequences the two allocations** (§5.3).

---

### BLOCK 9 — Ship the nginx script-execution block and rate-limit `location /media/` (07-MEDIA-006)

| | |
|---|---|
| **Findings owned** | `07-MEDIA-006` |
| **Depends on** | **nothing in-plan.** No edge to any other block; it is a green-field config block |
| **Blocks** | nothing in-plan |
| **Priority** | **P2** |
| **Risk level** | **MEDIUM** — a bad `location` regex 403s every genuine photo on the site, and the shipped harness reads only `nginx.conf` |
| **Required agents** | **Auditor · Researcher · Planner · Implementor · Validator** (Researcher for Q07-13; **Validator is mandatory** because the one irreducible risk is a deployed-stack behaviour no unit test can reach) |

**What is wrong.** `docs/01-spec/architecture-structure.md` documents, verbatim, that nginx
blocks script execution with
`location ~* /media/.*\.(php|py|cgi|pl|sh)$ { deny all; return 403; }`. **It does not exist** —
not in `nginx.conf`, not in `nginx.dev.conf`, not in any fragment. `docker/nginx/` contains
exactly two config files and `certs/`; both configs include only `/etc/nginx/mime.types`. A
recursive scan for `\.php|\.cgi|deny all` returns **one** hit: the `deny all` inside
`location = /metrics`. Separately, `location /media/` declares **no `limit_req`** while
`/login/`, `/search/`, `/moderation/` and `/` all do, and `media_gate` has no
application-level limiter of its own — so every published photo request reaches Django and
PostgreSQL at unlimited rate, issuing two `EXISTS` queries per request.

**There is no execution path today**, and this plan does not pretend otherwise. `/media/` is
**proxied to Django**, never served as static content, and `/protected-media/` is `internal`
with a MIME whitelist. The real cost is **false assurance** (a reader of the architecture doc
believes a control exists) plus an unrated request path that is a perfect 403/404/200 oracle
for key enumeration. MEDIUM, not higher. Do not upgrade it.

**Decision required before implementation — Q07-13 (paste twice, or a shared include?)**

The two configs are **not** symmetric: `nginx.dev.conf` omits `location = /metrics` and
`location /csp-report/`, and the dev config's `browse_limit` rates a different location set.
The report says "add the block to both". The Researcher's job is to state whether the
omissions are **deliberate dev simplifications** or **drift**.

- If deliberate: add the block to both configs (it is a *security* control, and the dev
  config already carries `nosniff`, the MIME whitelist and `internal`), and **say** in the
  commit body that the configs are intentionally asymmetric so the next reader does not
  "fix" the other asymmetry.
- If drift, or if the two files are meant to stay in step: a **shared include fragment** is
  the durable answer, and it also satisfies the report's own advisory — *"prefer one assertion
  over two doc fixes"*, the same anti-pattern phase 01's `VAL-003` identified for Compose.
  But `docker/nginx/` has **no include fragment beyond `mime.types`**, so a third file is a
  **structural change** to the image's config layout and needs the Planner to say so and name
  the risk (an include that is not mounted, or is mounted at a different path in the dev
  override, silently disables the control).

**This Planner does not choose.** Both options are implementable; the difference is
durability against a third environment being added later.

**The harness already exists (C-3) — this is not an untestable manual gate.**
`src/backend/tests/test_nginx_config.py` is `pytest.mark.unit`, needs **no database**, and
ships a brace-depth `_location_block(text, location_match)` extractor that already handles
nested blocks such as `types { … }`, plus three assertions on the `/metrics` block and a
docstring that states the method (`Path.read_text()`, no external Nginx parsing dependency,
repo root resolved by searching upward for `pyproject.toml`). It currently reads
**`nginx.conf` only**; extending it to `nginx.dev.conf` is a small, in-pattern addition.
`src/backend/tests/test_compose_contract.py` is the sibling harness for Compose-level
contracts and is where the report's "one assertion" advisory would live if it is adopted.

**Surface**

| Path | Symbols | Change |
|---|---|---|
| `docker/nginx/nginx.conf` | `location /media/`; a new script-execution `location` block | add the documented block **verbatim**; add `limit_req zone=browse_limit burst=40 nodelay;` to `/media/`, matching `location /`. **`browse_limit` is already defined in both configs** (`10m rate=20r/s`) so **no new zone is needed** |
| `docker/nginx/nginx.dev.conf` | same | the same two changes, per the Q07-13 answer |
| `src/backend/tests/test_nginx_config.py` | `_location_block`; new test functions | assert the script-execution block exists and contains `deny all` **and** `return 403`, in **both** configs; assert `/media/` carries a `limit_req` |
| `docker/nginx/media-hardening.conf` *(new, only under the Q07-13 include option)* | — | the shared fragment plus the `include` lines in both configs |
| `docs/01-spec/architecture-structure.md` | the `/media/` security bullet | **BLOCK 10's**, not this block's. Once the block exists, the doc becomes **true**, and BLOCK 10's remaining correction there is the "keys are UUID v4" claim |

**Binding constraints for the Implementor**

1. **The block is a 403 or 404 risk for genuine photos.** A typo in the regex — an
   unescaped dot, a missing `$` anchor, a greedy quantifier — turns a site-wide image
   outage. The harness tests catch a *missing* block; they do **not** catch a regex that
   matches a real key. That is the one irreducible residual and it is the manual gate below.
2. **Do not add a new `limit_req_zone`.** Reuse `browse_limit`; the configs already define it.
3. **Do not change `location /protected-media/`.** It is correct: `internal`, `alias`,
   `nosniff`, `Content-Disposition: inline`, a MIME whitelist of `image/jpeg`, and
   `default_type application/octet-stream`.
4. **Do not add an application-level rate limiter to `media_gate`.** The `limit_req` is the
   in-pattern answer; an app-level limiter would be a second policy in a different language.
   (An `apps/search/services/rate_limit.py`-style limiter exists elsewhere in the tree if an
   app-level limit is ever wanted — and `listings()` already calls
   `check_deep_link_render_rate_limit` — but it is not this block.)
5. **`/media/<path:image_key>` is routed by Django's `<path:>` converter**, which is what lets
   a slash-bearing `seed/<filename>.jpg` key through. The nginx block must not shadow that
   path shape.
6. **`config/urls.py` mounts `django_prometheus.urls` at `""`**, so `/metrics` is served by
   Django; `MediaConfig` and `test_observability.py` pin the middleware ordering and
   `test_nginx_config.py` pins the nginx block. Do not disturb any of the three.

**The one manual gate (deployment smoke check, not a test)**

Confirm in a running stack, in **both** configurations, that **one real media key still
returns 200 + `X-Accel-Redirect` and serves its bytes** after the change, and that a
`/media/x.php`-shaped request is refused. `nginx -t` for syntax. The code context records
that no HTTP hop exists in the development environment (the dev web/bot containers
crash-loop on a placeholder `BOT_TOKEN`), so this is an **operator step in a deployed
stack**, recorded as done in the commit body. It is the *only* manual gate left in the plan
after C-3.

**Tests to add** (following the harness's established pattern — string-level assertions via
`Path.read_text()`, no external Nginx binary, no database)

1. Both configs declare a script-execution `location` for `/media/` containing `deny all`
   **and** `return 403`.
2. Both configs' `location /media/` carries a `limit_req` directive.
3. The block is **after** the proxying `/media/` location in evaluation terms — i.e. the
   regex form is a `~*` match, not a prefix, so `proxy_pass` is not shadowed. *(Assert the
   location header form, which is a real nginx semantic, not a substring.)*
4. The existing `/metrics` assertions still pass **unchanged**.

**Keep green, do not edit**

`src/backend/tests/test_nginx_config.py`'s three existing tests and its `_location_block`
helper · `src/backend/tests/test_compose_contract.py` in full ·
`apps/core/tests/test_observability.py` in full ·
`apps/ads/tests/test_media_security.py` in full (this block changes **no** Django view).

**Gates**

`$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/tests/test_nginx_config.py src/backend/tests/test_compose_contract.py --tb=short" test`
→ then `.\Makefile.ps1 test` → then both static gates → then `nginx -t` for both configs and
the manual real-key smoke check.

**Risk and rollback**

- *Rollout risk: LOW for the assertions, MEDIUM for the deployment.* The realistic failure is
  a regex typo shipping as a site-wide image outage. The harness plus `nginx -t` plus the
  real-key smoke check are the three controls, and the third is irreducible.
- *Served URLs: unchanged.* `/media/<key>` and `/protected-media/<key>` keep their current
  shapes; this block adds a **refusal** for script-shaped requests, which no legitimate key
  can take.
- *Filesystem-vs-database consistency:* unaffected — nginx is configuration, not a reconciler.
- *Migration / backfill hazards:* **none.**
- *Rollback:* a plain revert plus an nginx reload. **If the new block is 403ing real photos,
  the revert is the incident response** and it should be immediate, not scheduled.
- *Cross-phase:* none direct. Phase 13 (`PERF-*`) owns the `AdImage` lookup load; the
  `limit_req` here reduces it, which is a complement, not an overlap.

---

### BLOCK 10 — Document the storage-key ownership rule and correct the seven stale doc locations (07-MEDIA-009)

| | |
|---|---|
| **Findings owned** | `07-MEDIA-009`, plus the **doc half of `07-MEDIA-011`** routed to this block |
| **Depends on** | **BLOCK 2** (hard — the rule must be the **decided** one), **BLOCK 4 and BLOCK 5** (soft — the shipped quality and the shipped seed behaviour must be stated as they are) |
| **Blocks** | nothing in-plan |
| **Priority** | **P1** |
| **Risk level** | **MEDIUM** — documentation only, but **four of the seven locations are on files other phases hold** |
| **Required agents** | **Auditor · Researcher · Planner · Implementor · Validator** (Validator is mandatory: a doc block whose content is wrong is worse than no block, and four targets are reserved) |

**Why this is documentation and not code.** The code is right. `generate_storage_key()`
returns `f"{uuid.uuid4()}.jpg"` with **no `ad_id`**, and that is deliberate: adding an
`ad_id` would make keys **sequential and guessable**, which is the opposite of the actual
security goal. This is the report's §5 `[SPEC-DEVIATION]` → `[DOC-UPDATE]` reclassification
applied correctly. **Do not change `generate_storage_key()`.**

**The doc surface is 7 locations across 5 files + 2 source docstrings, not 4 documents (C-5).**
The report filed four; the Auditor found three more, two of which appear in **no** plan in the
set. The full census:

| # | Location | Claim | Reality | Owner |
|---|---|---|---|---|
| 1 | `docs/02-database/db-schema.md` (field comment for `ad_images.image`) | key contains "only ad_id + UUID v4" | `<uuid4>.jpg` | **phase 07** |
| 2 | `docs/02-database/db-schema.md` (Zone R6/R8 callout) | "`ad_images.image` key is ad-scoped + UUID v4" | not ad-scoped | **phase 07** |
| 3 | `docs/01-spec/architecture-structure.md` (`/media/` security bullet) | documents an nginx script-execution block that does not exist, **and** "media keys are UUID v4" | BLOCK 9 makes the first half true; the second half is false | **phase 07** (after BLOCK 9) |
| 4 | `docs/ops/docker-deployment.md` (media security list) | "Storage keys are UUID v4 (unguessable, non-sequential)" | seed keys are `seed/<filename>.jpg` — semantic and enumerable | **phase 07 — newly identified, Q07-12** |
| 5 | `docs/04-user-stories/seller-stories.md` **US-S5 — Edit ad** | "Price/photo edits publish instantly (≤5s)" | no photo input exists; `photos=[]` on **both** branches that reach `submit_ad` | **phase 07 — newly identified, Q07-12** |
| 6 | `docs/01-spec/technical-specification.md` decision J (`:154`) | "Price/photo edits publish immediately" | same | **PHASE 06-RESERVED — route** |
| 7 | `docs/01-spec/technical-specification.md` (`:77` / `:79` / `:88` / `:149`) | "No server-side photo optimization in phase 1"; "serves full-size compressed photos"; erasure "removes physical ad-image files"; "cannot publish without ≥1 photo" | the first two are contradicted by the shipped pipeline; the erasure claim is true only under an exclusivity invariant the code violates in three places; the fourth is the sentence `MEDIA-002` is justified against | **PHASE 06-RESERVED — route** |
| 8 | `docs/02-database/db-retention.md` (`:102`) | erasure "removes physical ad-image files" | same | **PHASE 06 BLOCK 15 *and* PHASE 03 BLOCK 5 — route** |
| 9 | `src/backend/apps/ads/views/edit.py` — module docstring **and** `ad_edit` docstring (two locations, one file) | "Price/photo edits: save immediately, status stays PUBLISHED" | both `submit_ad` branches pass `photos=[]`; the code and docstring agree that only **price** is editable | **phase 07** (source, not `docs/`) |

**A repository-wide search for `refcount` / `reference count` / `same storage key` /
`ownership` across `docs/` returns nothing.** The invariant survives only as an undocumented
assumption, restated slightly differently in three places. This documentation *is* the
specification the erasure and retention reviews rely on, and it asserts a key structure the
code does not produce — an operator debugging a missing file would look for an ad-scoped key
format that has never existed.

**What the ownership sentence must say — and what it must not say.** It must record the
**decided** rule: *a storage key may be referenced by N ≥ 1 `AdImage` rows; bytes are freed
only when the last referencing row goes away.* It must **not** be written as an
"except `seed/`" placeholder — the report explicitly rejects that, and C-1 sharpens why: with
the shipped manifest the seed sharing is **within-category, cross-owner, at volume**, so it is
the case the rule must **handle**, not an exception to carve out. It must also state the real
key scheme: `<uuid4>.jpg` for bot uploads, `staging/<uuid4>.jpg` in flight,
`seed/<filename>.jpg` for seed data, and the reason there is no `ad_id` (**unguessability**).

**Binding constraints for the Implementor**

1. **Four of the seven locations are on reserved files. Route them; do not edit them.**
   `docs/01-spec/technical-specification.md` is **phase-06-reserved** (its BLOCKS 4, 11, 14
   edit it). `docs/02-database/db-retention.md` is claimed by **phase-06 BLOCK 15** *and*
   **phase-03 BLOCK 5**. The block's deliverable for those is a **written, specific request**
   naming the exact sentence and the exact replacement text, handed to the coordinator — not
   an edit.
2. **Write the ownership rule only after BLOCK 2 has landed**, and write the rule as
   **shipped**, not as intended. If BLOCK 2 landed under Q07-4 option (b) with a named
   helper, the doc names the helper.
3. **Do not restate MEDIA-001's reach narrative from the report.** The seed default pool is
   empty (C-1). Use BLOCK 2's **Q07-1 measurement** for any reach statement, and if no
   measurement is available, state the invariant **without** a reach claim.
4. **The photo-edit claim has three locations, not one** (#5, #6, #9) and they must say the
   same thing: **price** edits publish immediately; **photo** editing is not implemented in
   phase 1. If `submit_ad`'s `photos=[]` is a placeholder for planned work, say *that*
   explicitly — what is forbidden is leaving three places promising a feature with no code.
5. **Do not state anything the code does not do.** Every claim in the corrected text is
   checkable against a symbol: `generate_storage_key`, `STAGING_PREFIX`,
   `ImageGenerator._thumbnail_key`, `strip_photo_exif` + `STORED_JPEG_QUALITY`.
6. **`edit.py` is source, not documentation** — but the two docstrings are documentation and
   they are in phase 07's surface. Change **only** the docstrings; no behaviour.
7. **`architecture-structure.md`'s nginx bullet becomes true only after BLOCK 9.** If BLOCK 9
   has not landed, the bullet must not be edited to claim the block exists.

**Decision required before routing — Q07-12 (scope of the two newly identified files)**

`docs/ops/docker-deployment.md` (#4) and `docs/04-user-stories/seller-stories.md` (#5) are
**not in the report's list** and appear in **no** other plan in the set. The coordinator
decides whether they are phase 07's (they are phase 07's subject matter and this plan has
them on its table) or belong to a documentation sweep. **This plan assumes they are in scope
and routes the question, rather than silently dropping them or silently editing files that
may be another phase's.** A de-scoped location with no destination is a re-filed finding.

**Tests** — **none.** This is a documentation-only block. Phase 06's precedent is explicit
and this block follows it: a documentation block adds **no** behavioural test, because there
is no behaviour to verify and a test asserting a document's wording is the "trivial
implementation detail" test §1.5 forbids. Verification is a **Validator read-through**: every
sentence in the corrected text is checked against the named symbol, and every reserved
location has a written request.

**Keep green, do not edit**

`apps/ads/tests/test_edit.py` in full (the docstring change must not touch behaviour) ·
`src/backend/tests/test_nginx_config.py` in full · `docs/01-spec/spec-index.md` (**nobody**
in this plan edits it) · `docs/02-database/db-schema.md`'s **other** tables (only the
`ad_images` region is touched).

**Gates**

`uv run djlint src/backend/templates/` (only if a template changed — it should not) ·
`.\Makefile.ps1 test` · `uv run ruff check src/` · `uv run basedpyright src/` ·
plus the **Validator read-through** against the named symbols.

**Risk and rollback**

- *Rollout risk: LOW.* No behaviour changes. *Compatibility:* total.
- *Documentation risk: HIGH* — this is the block's real risk. A correction that is wrong, or
  that is overtaken by a concurrent phase's edit, leaves a document asserting something false
  again. Mitigation: the read-through; the re-read-immediately rule; the "say only what the
  code does" constraint; the reserved locations are **routed, not edited**.
- *Migration / backfill hazards:* none.
- *Served URLs: unchanged.*
- *Rollback:* a plain revert of the doc and docstring changes. The **routed requests** to
  phase 03 / phase 06 are not reverted by this plan — they are consumed by those phases, and
  §5.2 records that they were handed over.
- *Cross-phase:* **the highest-contention documentation block in the plan set.** Four
  reserved locations, two newly identified ones, and a file (`edit.py`) phase 05's BLOCKs 2
  and 8 own behaviourally (§5.3).

---

### BLOCK 11 — Single-photo removal: one service, one moderator action, one audit row (07-MEDIA-005, service + admin half)

| | |
|---|---|
| **Findings owned** | `07-MEDIA-005` (service + moderator surface) |
| **Depends on** | **BLOCK 2** (hard — see below), and on **Q07-6's answer** |
| **Blocks** | BLOCK 12 (hard) |
| **Priority** | **P1** |
| **Risk level** | **HIGH** — a **new delete surface** on `AdImage`; the first path that can free bytes outside `pre_delete` |
| **Required agents** | **Auditor · Researcher · Planner · Implementor · Validator — all five** |

**The hard dependency, and why it is not negotiable.** `AdImage` is append-only by
construction: no service, no admin action, no FSM step owns single-image removal. The seller
edit form submits `photos=[]` on **both** branches that reach `submit_ad` and has no photo
control at all; the bot has no per-photo handler (`cmd_cancel` bulk-cleans a `DRAFT` only);
`AdImageAdmin` has `actions = []` and `has_add/change/delete_permission` all `False`; and
`AdAdmin` declares **no inlines**, so `AdImage` is not reachable from the ad change form
either. A moderator's only options today are "ban the seller" or "destroy the listing" — and
the latter destroys the seller's text, views and analytics, which is disproportionate for a
photo containing a phone number or a face.

**Writing a removal service before BLOCK 2 would build a second data-loss route**, because it
would free bytes with no reference check. The one place that owns the invariant must be
BLOCK 2's, and this block must **reuse** it, never re-implement it. This is the report's own
rule: *"Do not start this before `MEDIA-001` lands."*

**The report's correction, upheld.** The headline "no such control exists" is **refuted**:
the spec's own parenthetical names *account ban* as the lever, and it is implemented and wired
(`AdAdmin.actions` contains `action_ban_user`, confirmed by source and by registered-admin
introspection). What remains is a **capability gap** — no lever removes one photo while
preserving the ad, its text, its view count and its analytics. Reclassified to
`BEST-PRACTICE`; the doc claims that described the *missing* feature were moved to
`MEDIA-009` (BLOCK 10).

**Decision required before implementation — Q07-6 (is photo-level moderation in scope for phase 1?)**

This is a **scope** decision, and the plan will not make it. The report itself says that if
photo-level moderation is *deliberately deferred* for phase 1, "the honest action is a
one-line doc fix … not a finding" — and never closed that option.

- **(a) Implement it** (BLOCK 11 + BLOCK 12 as written). Costs: two new user-facing surfaces,
  a new permission predicate, a new audit write, i18n, and a coordination requirement with
  phase 15's RBAC layer.
- **(b) Defer it for phase 1.** Then: the service, the admin action and the bot callback are
  **not** built; BLOCK 12 does not exist; the correct action is a **one-line doc correction**
  recording that the spec's coarser levers (archive, ban, destroy) are the only photo-level
  options in phase 1, plus a cross-reference so the next audit does not re-derive the finding
  as a spec deviation. **The finding is then closed as a recorded decision, not silently
  dropped** — and `technical-specification.md` is again the file the correction touches, so it
  is **routed** (Q07-12, §5.2), not edited.

**Who decides:** the **owner (product)**, with the coordinator. It is a product scope
question, not an engineering one.

**Decision required before implementation — Q07-5 (locking and the moderation pattern)**

| Question | Options | Consequence |
|---|---|---|
| Does the removal need a **new `AdvisoryLockId`** or a `select_for_update` on the `AdImage`? | A **new lock id** (a fourth allocation contending with BLOCK 8's and phase 06's) · a **`select_for_update`** on the row · **neither** | Lock id: most robust, highest process cost, and it competes for an integer BLOCK 8 is already allocating. `select_for_update`: correct for a single-row delete, and it is what `soft_delete_ad` uses for ad rows. **Neither** is defensible only if the removal is a single-row `DELETE` in a transaction — because `pre_delete` already fires, and BLOCK 2's check already runs inside `on_commit` |
| Does it route through `apps/moderation/admin_actions.py`? | Route through it · a media-layer service only | Routing through it gives a consistent reason/audit shape for free, but **phase 03 owns that module's lock behaviour and phase 06 owns its reason redaction.** Not routing means the media layer owns its own audit write and duplicates the `ModeratorActionLog` shape. **Neither neighbouring phase may be modified without the coordinator** |

**The Planner records both answers. The Implementor does not choose.**

**The permission predicate is phase 15's surface; the field set is phase 05 BLOCK 6's.**
`AdImageAdmin` is the class this block touches; `AdAdmin`'s field set is **not** touched.
`test_media_security.py` must assert the new path is **staff-only** — and if phase 15's RBAC
layer lands concurrently, the two must be sequenced together or the new action inherits
`has_delete_permission = False` semantics inconsistently. **A new delete surface that is not
permission-gated and not audited is an authorization gap**, which is precisely what this
block must not create.

**Surface**

| Path | Symbols | Change |
|---|---|---|
| `src/backend/apps/media/services/…` *(new module, or an addition to an existing media service)* | `remove_ad_image(ad_image, actor, *, reason)` | the **single** owner of single-image removal. Deletes the row; the row deletion fires `pre_delete` → BLOCK 2's `on_commit` check → the bytes are freed **only if no other row still references the key**. **It must not call `delete_photo` directly** — that would be the second data-loss route this block exists to avoid |
| `src/backend/apps/ads/admin.py` | `AdImageAdmin` — add an `action_remove` | requires a **reason string**, is staff-gated, and writes exactly one `ModeratorActionLog` row so the action is auditable like every other moderation action. `@admin.action`, then **assigned to `actions`** (an unassigned `@admin.action` is exactly the defect phase 04 found in `UserAdmin.withdraw_consent_action` — verify it is wired) |
| `src/backend/apps/ads/admin.py` | `AdImageAdmin` — `has_delete_permission` | this is the crux: the class currently returns `False` for delete. A **new** delete surface on a class that declares itself non-deleting needs an explicit, argued answer — and it is the surface phase 15 audits. The Planner must state the intended predicate even if the implementation defers to phase 15 |
| `src/backend/apps/ads/admin.py` | `AdAdmin` | **read-only.** Do not add an inline, do not change its field set |
| `src/backend/apps/moderation/admin_actions.py` | *(only if Q07-5 routes through it)* | the reason and audit flow only — **no behaviour change to the actions themselves** |

**Binding constraints for the Implementor**

1. **Reuse BLOCK 2's reference check. Do not re-implement it and do not call `delete_photo`.**
2. **Staff-only, and audited.** Exactly one `ModeratorActionLog` row per removal, with the
   reason. `test_media_security.py` asserts both halves.
3. **New user-visible strings** (the action description, and BLOCK 12's bot messages) need
   non-empty `ru` **and** `bs` msgstr. Append-only; never regenerate wholesale.
4. **Do not touch `AdAdmin`'s field set** (phase 05 BLOCK 6) or its permission predicates
   (phase 15).
5. **Do not touch `copy_ad`, `AdImage.storage_keys()`, or `delete_adimage_files_on_delete`.**
6. **If a lock id is needed, it is a fourth allocation.** Coordinator first; three files, one
   commit; re-read the free integer (C-4).
7. **Verify by introspection, not by reading `admin.py`** (`VAL-006`): a permission or
   capability claim about this class requires
   `admin.site._registry[AdImage].get_form(request)` and `.get_actions(request)`.
8. **The removal must be safe when another row still references the key** — the shared-byte
   case from `MEDIA-001` applies to a moderator's removal exactly as it does to a cascade.

**Tests to add**

1. A staff moderator removes one photo: the row is gone, **one** `ModeratorActionLog` row is
   written, and **the ad, its text, its status and its view count are untouched.**
2. A non-staff caller is refused and **nothing** is deleted and **no** audit row is written.
3. **The shared-key case:** two `AdImage` rows on two different ads share a key; a moderator
   removes one → **the file still exists** and the other ad's image still serves. This is the
   test that proves the block reuses BLOCK 2's invariant rather than re-implementing it.
4. A removal with an empty reason is refused — the reason is mandatory, not advisory.
5. `AdImageAdmin.get_actions(request)` includes the new action **and it is reachable from the
   UI** (i.e. it is in `actions`, not only decorated).

**Keep green, do not edit**

`apps/ads/tests/test_media_security.py` in full (the new assertions are **added** to the
relevant class; the existing ones are not rewritten) ·
`apps/ads/tests/test_copy_ad.py` in full · `apps/core/tests/test_ad_image_delete_signal.py`
in full · `apps/media/tests/test_media_config.py` in full ·
phase 04's `test_admin_pii_containment.py` (it covers `UserAdmin`, not `AdImageAdmin` —
verify it is not affected).

**Gates**

`$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/ads/tests/test_media_security.py src/backend/apps/ads/tests/test_copy_ad.py --tb=short" test`
→ then `.\Makefile.ps1 test` → then both static gates →
plus `uv run basedpyright src/backend/apps/ads/admin.py` for the new action's typing.

**Risk and rollback**

- *Rollout risk: MEDIUM-HIGH.* A **new capability** with a **new delete surface** and a
  **new authorization decision**, landing on a class that currently declares itself
  non-deleting.
- *Filesystem-vs-database consistency:* the block adds a second place bytes can be freed.
  That is precisely why it is hard-blocked on BLOCK 2 and why it must route the free through
  the row deletion rather than through `delete_photo`.
- *Migration / backfill hazards:* **none** — no schema change is expected. A new
  `ModeratorActionLog` row is additive and append-only.
- *Rollback:* a plain revert removes the new surface and the service. **Photos already removed
  by a moderator do not come back** — that is an intentional moderation action with an audit
  row, and the commit body must say so.
- *Cross-phase:* **phase 15** owns the permission predicate and must be told **before** this
  lands; **phase 05** owns `AdAdmin`'s field set; **phase 03** and **phase 06** own
  `moderation/admin_actions.py` (§5.3).

---

### BLOCK 12 — Let a seller drop one photo from the bot's photo step (07-MEDIA-005, bot half)

| | |
|---|---|
| **Findings owned** | `07-MEDIA-005` (seller-facing surface) |
| **Depends on** | **BLOCK 11** (hard — the service must exist) **and** on **Q07-6** (if moderation is deferred, this block does not exist) |
| **Blocks** | nothing in-plan |
| **Priority** | **P1** |
| **Risk level** | **MEDIUM** — a new FSM affordance; **no** new delete surface, because it routes through BLOCK 11's service |
| **Required agents** | **Auditor · Researcher · Planner · Implementor · Validator — all five** |

**Why this is a separate block from BLOCK 11.** They are one finding with two risk profiles.
BLOCK 11 creates the first path that can free bytes outside `pre_delete` and carries the
authorization and audit decisions. BLOCK 12 is a **seller-facing FSM affordance** that only
*consumes* the service, adds no new authority, and carries a completely different
deliverable: i18n strings, a callback handler, and a decision about what happens to
`state["photos"]`. Separating them means the riskier half can be reviewed, shipped and (if
necessary) reverted on its own, and the cheap half can be deferred without losing the
expensive half. **Q07-6's deferral answer deletes this block and leaves BLOCK 11 intact**,
which is only expressible if they are separate.

**What is missing.** The bot has no per-photo handler. `process_photos` appends to
`state["photos"]` and enforces the 5-photo cap *before* the download; `cmd_post` calls
`state.update_data(ad_id=ad.id)`, which **merges** — so the photos list survives a `/post`
— and `cmd_cancel` calls `state.clear()` and deletes only the **current draft's** keys via
`delete_photo(photo["storage_key"])` before `delete_draft(...)`, dropping the counter
regardless of status. There is no way to remove a photo the seller regrets without starting
over.

**The design questions this block must answer before code**

1. **What happens to `state["photos"]` after a removal?** The FSM list is the source of truth
   `cmd_cancel`'s cleanup and BLOCK 7's budget check both read. A removal must keep it
   consistent: the entry is dropped, `position` values are re-derived (and `AdImage.position`
   is the subject of phase 05 BLOCK 10's uniqueness constraint, so a re-numbering here must
   not conflict), and the 5-photo cap must reflect the *new* count — otherwise a seller can
   upload five, remove one, and upload five more without limit.
2. **Does the removal free the staged bytes immediately, or leave the key for promotion?**
   A photo removed **before** `submit_ad` was never promoted; its file is a staging file
   subject to the 2 h TTL. Deleting it immediately is a byte effect and must use the
   established `on_commit` / service pattern — **or** simply leave it to the TTL, which is
   simpler and already correct. The Planner records which and why. **Do not** call
   `apps.media.signals.delete_photo` from the bot: it is the monkeypatch target of
   `test_delete_photo_single_call.py`.
3. **Does the seller need a confirmation step?** Removing a photo is not reversible from the
   seller's side (the original bytes are gone). The report does not say. This is a UX
   question the Planner records rather than assumes.
4. **Does the removal apply only inside an open dialog, or also to a published ad?** The
   finding is about a photo on a **live** ad. A seller editing a published ad today reaches
   `ad_edit`, which has **no** photo control and submits `photos=[]` — so a bot-side removal on
   a published ad is a *different* flow from a dialog-time one, and BLOCK 10's doc correction
   (#5, #6, #9) says photo editing does not exist in phase 1. **The two must not be
   conflated**: this block is a **dialog-time** affordance unless the Planner records a
   different scope, and the published-ad path is a **separate capability** that BLOCK 11
   serves only for moderators today.

**Surface**

| Path | Symbols | Change |
|---|---|---|
| `src/telegram_bot/handlers/ad_create/photos.py` | `process_photos`; a new per-photo removal handler | the callback, the FSM update, the 5-photo-cap re-derivation |
| `src/telegram_bot/handlers/ad_create/entry.py` | `cmd_cancel`, `cmd_post` | **read-only unless** the Q-D record in point 1 requires touching the counter reset. `cmd_cancel` must continue to find a consistent `state["photos"]` |
| the media service from BLOCK 11 | `remove_ad_image` | **read-only call site** — the bot must not implement its own removal |
| `src/backend/locale/{ru,bs,en}/LC_MESSAGES/django.po` | append-only | the confirmation / removal-result strings, non-empty `ru` and `bs` |
| a keyboard/markup builder for the photos step | *(only if one is needed)* | follow the existing photos-step markup; do not invent a new pattern |

**Binding constraints for the Implementor**

1. **Route through BLOCK 11's service.** The bot gets no removal authority of its own.
2. **i18n is part of DoD** — non-empty `ru` **and** `bs`; `test_i18n_completeness.py` is
   gate-enforced. **Append** to the locale files.
3. **Do not touch `_STAGING_TTL_SECONDS`** (phase 03 BLOCK 6) or the sweep's exclusion set
   (phase 03 BLOCK 8) — including if the removal leaves a staged file for the TTL.
4. **Do not change the 5-photo cap's meaning.** It is per-FSM-list; the removal keeps the
   invariant honest rather than relaxing it.
5. **Do not call `apps.media.signals.delete_photo`.** Use
   `apps.media.services.filesystem.delete_photo` (or, better, the TTL) so
   `test_delete_photo_single_call.py` is untouched.
6. **`src/telegram_bot/tests/conftest.py` redefines the canonical fixtures as an `async
   user`.** Bot tests cannot import the backend conftest.
7. **Do not conflate dialog-time removal with published-ad photo editing** (design question 4).
   If the Planner scopes this block to the dialog only, that scope must be **recorded** so
   BLOCK 10's doc correction is written against the right promise.

**Tests to add**

1. A seller removes the second of three staged photos: the FSM list has two entries, the
   5-photo cap reflects the new count (the seller can upload three more, **not** five), and a
   re-submission creates exactly two `AdImage` rows.
2. Removing the **last** photo is handled gracefully — the message is correct and the flow
   does not leave the FSM in a state where `submit_ad` receives an empty list it cannot
   explain.
3. `/cancel` after a removal deletes only the **remaining** keys — no double-delete, no
   orphaned `state["photos"]` entry, and `delete_photo` reaches each key at most once.
4. Every new message resolves in `ru` and `bs` with a non-empty `msgstr`.
5. A **non-owner** cannot invoke the removal callback for another seller's draft — the
   handler resolves the draft from the FSM state, not from a caller-supplied id.

**Keep green, do not edit**

`src/telegram_bot/tests/test_save_photo_integration.py` in full (phase 03 BLOCK 8's surface —
**re-read if it has landed**) · `telegram_bot/tests/**` upload and FSM tests in full ·
`apps/ads/tests/test_ad_image_service.py` in full · `apps/ads/tests/test_edit.py` in full.

**Gates**

`$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/telegram_bot/tests/ --tb=short" test`
→ then `.\Makefile.ps1 test` → then both static gates →
plus `apps/ads/tests/test_i18n_completeness.py` explicitly.

**Risk and rollback**

- *Rollout risk: MEDIUM.* A new FSM affordance; the failure is a seller who cannot remove a
  photo, not data loss. The FSM is also a **shared** structure: a bug here can break
  `/post`, `/cancel` and `submit_ad` for every seller, which is why the "remove the last
  photo" and "`/cancel` after a removal" tests are mandatory.
- *Filesystem-vs-database consistency:* low. A staged file removed before promotion is
  either deleted through the service pattern or left to the TTL; both are safe. **The
  staged-file residue is invisible to every current reconciler** — the blind spot `MEDIA-007`
  and `MEDIA-012` share — which is why the design record must say which path was taken.
- *Migration / backfill hazards:* **none.**
- *Rollback:* a plain revert. **Photos a seller already removed do not come back**; the commit
  body must say so.
- *Cross-phase:* the bot's `ad_create` handlers are shared with phase 02's in-flight work and
  phase 05's BLOCK 11 (`ad_copy`); re-read before editing (§5.3).

---

## 4. Dependency graph

### 4.1 Execution order (the safe serial order)

One Implementor, strictly sequential. Every block is one commit (§1.3).

| # | Block | Findings | Depends on (in-plan) | External gate | Risk |
|---|---|---|---|---|---|
| 1 | Scope the photo dedup to the target ad | `07-MEDIA-002` | — | phase-03 BLOCK 8's **recorded** Q7/Q8 option; **Q07-2**, **Q07-3** | **HIGH** |
| 2 | Free a key only on the last reference | `07-MEDIA-001` | 1 | **Q07-1** (measurement), **Q07-4** (shape) | **HIGH** |
| 3 | Atomic thumbnail writes + a repair guard | `07-MEDIA-004` | — (serialised on `submission.py` behind 1) | the option record for `FileExistsError`; the blanket-catch decision | **HIGH** |
| 4 | Name the stored-original JPEG quality | `07-MEDIA-011` | — | **Q07-11** | LOW |
| 5 | Seed: assert only what was written | `07-MEDIA-008` | 3 | the cache-check decision | LOW-MEDIUM |
| 6 | Dangling-row reconciliation + the §4.7 assertion | `07-MEDIA-012` + the `deleted += 1` miscount | — | **phase-03 BLOCK 6 and BLOCK 8** (hard external); **Q07-9** | **HIGH** |
| 7 | Staging byte budget + `staging_bytes` | `07-MEDIA-007` | 6 | **Q07-7**, **Q07-8** | MEDIUM |
| 8 | `MediaDeletionError` reader + retention | `07-MEDIA-010` + the `ME-003` reconcile | — | **Q07-10**, **Q07-14**; coordinator for the lock id | MEDIUM |
| 9 | nginx script block + `/media/` rate limit | `07-MEDIA-006` | — | **Q07-13**; the deployed-stack real-key smoke check | MEDIUM |
| 10 | The storage-key ownership rule + 7 doc locations | `07-MEDIA-009` | 2 (hard), 4 + 5 (soft) | **Q07-12** routing; phase 06 for the reserved files | MEDIUM |
| 11 | Single-photo removal: service + moderator action | `07-MEDIA-005` (a) | 2 (hard) | **Q07-6** (owner), **Q07-5**; phase 15 told **before** | **HIGH** |
| 12 | Single-photo removal: the bot's photo step | `07-MEDIA-005` (b) | 11 (hard) | **Q07-6**; four design questions in §3 | MEDIUM |

### 4.2 The DAG and why each edge exists

```
  [1 dedup re-scope + reclaim]        [3 atomic thumbnails + repair guard]
        |                                      |
        v                                      v
  [2 reference check in on_commit]       [5 seed truthful return]
        |                                    
        |   (nothing)   [4 STORED_JPEG_QUALITY]  <-- independent
        |         |            
        +---------+-----------+
                  v
            [10 the ownership rule + 7 doc locations]
                  ^
        (external: phase-03 BLOCK 6, BLOCK 8)
                  v
            [6 dangling-row report + §4.7 assertion]
                  |
                  v
            [7 staging byte budget + gauge]

  (nothing) --> [8 MediaDeletionError reader + retention]
  (nothing) --> [9 nginx block + /media/ limit_req]

  [2] --> [11 removal service + moderator action] --> [12 bot photo removal]
```

**Each edge, with the reason it exists:**

| Edge | Why it exists |
|---|---|
| **1 → 2** | `MEDIA-002`'s fix creates a fresh row under a freshly generated **unique** key and reclaims the skipped file, which is safe under *either* ownership model. Landing it first **removes the accidental-aliasing vector entirely**, shrinking `MEDIA-001` from three producers of a shared key to two intentional ones. `MEDIA-001` first would encode a guard against a defect that is about to stop existing. This is the **inversion of the audited chain**, and it is deliberate |
| **3 → 5** | `MEDIA-008` *reuses* `MEDIA-004`'s stale-file-versus-race guard. Fixing 5 first re-introduces the defect class it inherits: a half-written seed variant would be skipped rather than regenerated, and the row would still assert a file that does not exist |
| **1 → 3** | Both edit `submit_ad`. One Implementor, one block at a time; the second re-reads the first's diff. **Not** a logic dependency |
| **2 → 10** | The doc must record the **decided** rule, not a placeholder. Writing "N references, freed on the last" before the check exists documents an intent; writing it after documents a behaviour. The report is explicit: the ownership sentence is written **only after** the invariant lands |
| **4 → 10** | The doc must state the shipped quality, including the mixed-quality consequence. Soft: the doc block can proceed with BLOCK 4's decision record if BLOCK 4 has not landed, but the sentence is better written last |
| **5 → 10** | The doc must describe the seed thumbnail behaviour as shipped. Soft, for the same reason |
| **6 → 7** | Both edit `sweep_orphaned_media.Command.handle`. The single-variant report must land before the byte-budget work, so the sweep's "what does it do" story is written once. This is the **in-plan half** of the three-way contention in §5.3 |
| **2 → 11** | A removal service that frees bytes outside `pre_delete` becomes a **second data-loss route** unless it is built on top of the invariant. The report is explicit: *"Do not start this before `MEDIA-001` lands."* This is the plan's hardest non-negotiable edge |
| **11 → 12** | The bot must consume the service, never re-implement it. Separating them also makes `Q07-6`'s deferral answer expressible: "defer" deletes BLOCK 12 and leaves BLOCK 11 intact |
| **6 → (external phase-03 BLOCK 6, BLOCK 8)** | `Command.handle`, `_walk_media_files` and `_reclaim_staging` are claimed by phase 03, and `_STAGING_TTL_SECONDS` is phase-03 BLOCK 6's alone. BLOCK 6 edits that function, so it is sequenced against phase 03 rather than parallel to it |
| **7 → (external phase-03 BLOCK 6)** | The byte budget is a **space** policy designed to sit beside a **time** policy. The TTL is phase 03's to settle; designing the budget against today's 2 h would be designing against a number that may change |
| **8 → (external coordinator)** | A new `AdvisoryLockId` requires `enums.py` + the allocation docstring in `advisory_lock.py` + `test_advisory_lock_ids.py` in **one commit**, with the coordinator told **first**, and the free integer re-read at that moment (C-4: it is **14**, not 13) |
| **8 → (external phase-06 BLOCK 15)** | Phase 06 also appends to `HOURLY_COMMANDS` and also allocates a lock id. Two phases computing "the next free integer" concurrently is the single most likely cross-phase collision in this plan set |
| **11 → (external phase 15)** | Phase 15 owns the `AdImageAdmin` permission predicate. A new delete surface landing without phase 15 knowing inherits `has_delete_permission = False` semantics inconsistently. **Phase 15 is told before BLOCK 11 lands** |

### 4.3 Where there is deliberately no edge, and why

| Pair with no edge | Why |
|---|---|
| **1 ↔ 3, 1 ↔ 4, 4 ↔ 9** | Different files, different concerns. `1` touches `images.py` + `submission.py`; `3` touches `thumbnails.py` + `backfill_thumbnails.py`; `4` touches `filesystem.py` + one constant; `9` touches two nginx files and one test module. They are sequenced only because a single Implementor runs them one at a time |
| **3 ↔ 4** | Both declare a quality-related constant in `apps/media/services/thumbnails.py`, which is a **file** edge, not a correctness one. `4` must re-read `3`'s diff. Either order is correct |
| **6 ↔ 8** | BLOCK 6 reuses lock 103; BLOCK 8 allocates a **new** id. The only interaction is that BLOCK 8 must not take an integer BLOCK 6 might have wanted — and BLOCK 6 explicitly reuses 103, so there is no interaction. Both touch `test_sweep_lock_structure.py` in different lists, which is a **file** edge, serialised by the single Implementor |
| **7 ↔ 8** | Different settings, different commands, different files. Their only shared surface is `config/settings/base.py` (BLOCK 7) and nothing (BLOCK 8) |
| **9 ↔ 10** | BLOCK 9 makes the architecture doc's nginx bullet *true*; BLOCK 10 corrects the same bullet's key claim. They are sequenced by content (10 after 9) not by correctness, and the edge is recorded in BLOCK 10's own text rather than as a graph edge, because BLOCK 10 is also allowed to proceed with a "block not yet shipped" caveat |
| **12 ↔ anything** | BLOCK 12 is a leaf. It consumes BLOCK 11's service and reads FSM state. Nothing in the plan depends on it |

### 4.4 The three-way serialisation on `sweep_orphaned_media` — stated once

The code context records that this command is claimed by **three** parties and one of its
module constants by a fourth. This plan states the order once so it is not re-derived:

```
phase-03 BLOCK 6  (_STAGING_TTL_SECONDS — the time policy)
        |
        v
phase-03 BLOCK 8  (the exclusion set + the promotion window; DB-005 Option A/B/C)
        |
        +-------------------------------+
        |                               |
        v                               v
phase-07 BLOCK 6                  phase-07 BLOCK 7
(07-MEDIA-012: the revenue          (07-MEDIA-007: the space policy
 side — dangling rows,              beside the TTL, plus the gauge)
 reusing lock 103,
 plus the `deleted += 1` fix)
```

Rules that follow, and are binding:

1. **Phase 07 extends the directory contract; it does not define a second one.** BLOCK 6's
   report scope and BLOCK 7's budget are added to what phase 03 settles. Neither block may
   change the **deletion** scope of `_walk_media_files`.
2. **Both blocks re-read `Command.handle` immediately before editing** and stage explicitly.
   A merge conflict there is an expected outcome, not an error to be resolved by clobbering.
3. **If phase 03 BLOCK 8 has not landed, BLOCK 6 waits.** The plan does not branch the sweep
   around an unsettled design.
4. **`_STAGING_TTL_SECONDS` is not phase 07's.** Neither BLOCK 6 nor BLOCK 7 may change it.
5. **BLOCK 1's reclaim is written against the key, never against a directory** — so it
   survives whichever `DB-005` option wins.

### 4.5 The four orders that are unsafe

1. **BLOCK 2 before BLOCK 1** — a reference check written while an accidental-aliasing
   producer is still live encodes a guard for a defect that BLOCK 1 removes, and BLOCK 1
   then changes the row-count assumptions the check was tuned against.
2. **BLOCK 5 before BLOCK 3** — the seed block reuses a guard that does not exist yet, and
   would re-implement it differently, producing two implementations of the same rule.
3. **BLOCK 11 before BLOCK 2** — the second data-loss route. **Non-negotiable.**
4. **BLOCK 6 or 7 while phase-03 BLOCK 8 is mid-edit on the same function** — two agents in
   the same method. This is not a gate but a **scheduling** constraint: the coordinator
   sequences the two phases.

### 4.6 What the DAG does *not* decide

The DAG orders blocks. It does **not** resolve `Q07-1` … `Q07-14`. Each is a gate inside a
block, recorded in that block's `extra_context` and as a row in §0.5. **A block whose gate is
unanswered does not start.** §8.1 checks that a written answer exists for all fourteen.

---

## 5. Cross-phase coordination

Plans `.ai/plans/01-…` through `.ai/plans/06-pii-consent-remediation.md` exist; phases 08–15
are being planned in parallel right now. This section is the boundary contract. It is
deliberately **one-directional**: phase 07 states what it owns, what it will not touch, and
where its boundaries lie. **It does not attempt to contact or negotiate with the other
agents.**

### 5.1 What phase 07 already owns and must not re-ship

| Phase 07 artefact | What phase 07 must not do | Boundary |
|---|---|---|
| **The storage-key ownership model.** The validated report answers the question phase 05 reserved to phase 07: **N references; bytes freed only on the last reference.** `MEDIA-001` implements it and `MEDIA-009` documents it | Phase 07 must not **re-open** the decision, and must not ship the refcounted-`MediaObject` alternative. `_collect_referenced_keys` and `delete_adimage_files_on_delete` are phase 07's; no other phase may change them | Recorded in this plan (§0.5, BLOCK 2). The unique-index option is recorded as **infeasible** so no implementer dead-ends on it |
| **`07-MEDIA-001` absorbs the `pre_delete` half of phase 05's `AD-003`** | Phase 07 must not resurrect `AD-003` in any form, and must not accept a phase-05 "half-fix" | §5.4 |
| **`07-MEDIA-002` is the record for the seller-scoped-dedup behaviour**, at HIGH, superseding phase 05's `AD-006` at MEDIUM | Phase 07 must not implement the ads-side photo-count semantics that phase 05's Q6 owns, and must not change `submit_ad`'s transition rules | §5.5 |
| **`07-MEDIA-012` owns the *revenue* side of the media store↔database diff** | Phase 07 must not ship the staging-window fix (that is `03-DB-005`), and must not assert that detection is impossible | §5.2 |
| **All of `apps/media/**`** | Phase 07 is its **sole** owner. Phase 05's plan declares it read-only for every phase-05 block | No conflict. Phase 07's BLOCK 11 touches `apps/ads/admin.py`, not `apps/media/**` |
| **The media serving contract** — `media_gate`'s row-and-authorization lookup, `X-Accel-Redirect` on the `DEBUG=False` branch, `Cache-Control`/`Vary` on 403/404 | Phase 07 must **not** add a filesystem check to `media_gate`, must not change its cache headers, and must not add an application-level rate limiter | §0.2.2 hazard 1. BLOCK 9's `limit_req` is the in-pattern rate control |

### 5.2 What phase 07 must **not** do, for other phases' sake

| Other phase | What phase 07 must not do | Boundary |
|---|---|---|
| **Phase 03 — `03-DB-005` (BLOCK 8)** | Phase 07 ships **no** staging-window fix. `submit_ad`'s promotion call site, `move_staging_to_permanent`, `_walk_media_files`, `_reclaim_stale_staging` and `Command.handle` are phase 03's contract | Phase 07's BLOCK 6 and BLOCK 7 land on the **same** `Command.handle` — §4.4 serialises them. Phase 07 **extends** the directory contract; it does not define a second one |
| **Phase 03 — `03-DB-003` (BLOCK 6)** | Phase 07 must not change `_STAGING_TTL_SECONDS`. BLOCK 7's byte budget is designed **against** the TTL that block settles | The 2 h value in the report is what ships today; the budget must not be calibrated to it as if it were settled |
| **Phase 03 — `03-DB-011` (BLOCK 1)** | Phase 07 must not touch the six sweeps' redundant `storage_keys` pre-collectors. They are phase 03's to remove | `apps/media/**` is phase 07's but those six call sites are **outside** it |
| **Phase 03 — `AdvisoryLockId` allocation** | Phase 07 must not allocate a new id without the coordinator being told **first**, and then `enums.py`, `advisory_lock.py`'s docstring and `test_advisory_lock_ids.py` change **in one commit** | C-4: the free id is **14**, not 13. `CONSENT_HARD_DELETE == 3` and every other id is never renumbered |
| **Phase 05 — `AD-003`** | Phase 05 must not ship the byte-copy fix. Phase 07 must not resurrect it. Under the refcount model `copy_ad`'s aliasing is **legal behaviour** | §5.4. `copy_ad` is read-only for every phase-07 block; phase-05 BLOCK 14 owns a comment-only edit |
| **Phase 05 — `AD-006` / BLOCK 13** | If phase 07 ships BLOCK 1 first, **phase-05 BLOCK 13 ships no production code** and becomes a cross-reference. Phase 07 must not touch the ads-side framing | §5.5 |
| **Phase 05 — `AdAdmin`'s field set (BLOCK 6)** | Phase 07's BLOCK 11 touches `AdImageAdmin`, **not** `AdAdmin`'s fields | `AdAdmin`'s editable field set is phase 05's |
| **Phase 06 — `technical-specification.md`** | **Phase 06 holds the reservation.** Phase 07 must **route**, not edit. Four of `MEDIA-009`/`011`'s doc targets sit on reserved files | BLOCK 10 delivers a **written request** naming the exact sentence and the exact replacement text |
| **Phase 06 BLOCK 15 / Phase 03 BLOCK 5 — `db-retention.md`** | Phase 07 must not edit the erasure sentence. Re-read before touching, if the coordinator ever authorises it | BLOCK 10 routes |
| **Phase 06 BLOCK 15 — `HOURLY_COMMANDS` and the lock id** | Phase 07's BLOCK 8 appends to the same list and allocates from the same sequence. **The coordinator sequences the two allocations** | §5.3 |
| **Phase 12 — alerting** | Phase 07 supplies the **read surface only**: the `staging_bytes` gauge, the dangling-row report, and the `MediaDeletionError` predicate. **Phase 07 adds no alert and no notification** | The predicates are recorded in the commit bodies so phase 12 can consume them |
| **Phase 13 — performance** | `MEDIA-006`'s `limit_req` reduces the unbounded `AdImage` lookup load on `media_gate`'s hot path; that is a **complement** to `PERF-*`, not a claim on it. And `MEDIA-012` must **not** add a per-request stat | Phase 13 owns query plans and index decisions. Phase 07 adds no index |
| **Phase 14 — i18n** | `src/backend/locale/*/LC_MESSAGES/django.po` is **shared**. Phase 07's BLOCKS 7, 11 and 12 **append**; they never regenerate wholesale | A wholesale `makemessages` would discard phases 05, 06, 11 and 14's entries |
| **Phase 15 — authorization** | Phase 07's BLOCK 11 adds a **delete surface** on `AdImage`. The permission predicate is **phase 15's**; phase 07 must not write an ad-hoc predicate that phase 15 then has to reconcile | Phase 15 is **told before** BLOCK 11 lands. If phase 15's RBAC layer lands concurrently, the two must be sequenced together |
| **Phase 11 / all phases — test rewrites** | Phase 07 claims only its **incidental** rewrites: `test_seed_original_strips_jpeg_comment` (BLOCK 5, return contract), and `test_thumbnails.py::test_atomic_write_collision_raises_file_exists` **only if** the recorded option is (b) (BLOCK 3), and an exact-registry-set test **only if** Q07-10 finds one (BLOCK 8) | **Each is named, justified, and must not grow into new coverage while being rewritten** |

### 5.3 Shared-artefact reservations

| Artefact | Claimed by | Risk and rule |
|---|---|---|
| **`src/backend/apps/media/management/commands/sweep_orphaned_media.py`** | **Phase 03: BLOCKS 6 and 8** · **Phase 07: BLOCK 6** (`Command.handle`, the report mode, the `deleted += 1` fix) · **Phase 07: BLOCK 7** (the gauge, if Q07-8's answer needs it) | **The most contended file in the plan set.** Three parties, three blocks. §4.4 states the order. Phase 03 goes first; then phase 07 BLOCK 6; then BLOCK 7. One Implementor, one block at a time, each re-reading the previous diff. **Do not merge two of these into one commit** even when they look adjacent |
| **`src/backend/apps/ads/services/submission.py`** | **Phase 03: BLOCKS 3, 5, 6, 8** · **Phase 05: BLOCKS 5, 12, 13** · **Phase 07: BLOCK 1** (the reclaim) and **BLOCK 3** (the thumbnail `except` decision) | The single most contested file across the whole plan set. Phase 07 touches it in **two** blocks, serialised (1 then 3), each re-reading. Phase 07 must not change the transition table, the promotion call site, or the photo-count semantics phase 05's Q6 owns |
| **`src/backend/apps/ads/admin.py`** | **Phase 05: BLOCK 6** (`AdAdmin`'s field set) · **Phase 15** (permission predicates) · **Phase 07: BLOCK 11** (`AdImageAdmin.action_remove` only) | Three claims, three different classes. Phase 07 touches **one** class in **one** block and must not touch `AdAdmin`'s fieldsets or predicates. Re-read immediately before editing |
| **`src/backend/apps/moderation/admin_actions.py`** | **Phase 03** (lock behaviour) · **Phase 06** (reason redaction) · **Phase 04** (comments only) · **Phase 07: BLOCK 11** (only if Q07-5 routes through it) | If BLOCK 11 routes through it, it touches the **reason and audit flow** only — **no behaviour change to the actions themselves.** Coordinator decides the routing |
| **`src/backend/apps/core/enums.py` + `apps/core/utils/advisory_lock.py` docstring + `test_advisory_lock_ids.py`** | **Phase 07: BLOCK 8** · **Phase 06: BLOCK 15** | **Three files, one commit, coordinator told first.** C-4: `13` is taken by concurrent phase-02 work; the free id is **14**. `test_advisory_lock_ids.py` does **not** catch id reuse — this is a human rule, not an automated one |
| **`src/backend/apps/core/utils/scheduler.py`** (`HOURLY_COMMANDS`) | **Phase 07: BLOCK 8** · **Phase 06: BLOCK 15** | Any other phase appending an entry changes `test_scheduler_wiring.py` and `test_sweep_lock_structure.py` too. Check the list at implementation time. `_validate_commands` does **not** raise on a missing entry — the command is simply never dispatched, and the test notices |
| **`src/backend/apps/core/tests/test_sweep_lock_structure.py`** | **Phase 07: BLOCK 8** (`SWEEP_COMMANDS`, `_LOCK_TARGET_MODULES`) · **Phase 03** (its own amendments) | BLOCK 8 adds a new command to **both** lists. If phase 03's amendments have landed, **re-read, do not assume** the list contents |
| **`src/backend/config/settings/base.py`** | **Phase 02** (in-flight) · **Phase 04** (multiple blocks) · **Phase 07: BLOCK 7** (one setting) | Append-only; never reorder a setting another phase annotated. Re-read immediately before editing |
| **`docker/nginx/nginx.conf`, `docker/nginx/nginx.dev.conf`** | **Phase 07: BLOCK 9** · **Phase 01** (`CFG-001`/`CFG-002` context) | Phase 06 and phase 12 do not edit these. If Q07-13's answer creates a **shared include fragment**, that is a structural change to the image's config layout and must be named as such |
| **`src/backend/tests/test_nginx_config.py`** | **Phase 07: BLOCK 9** | Existing helper `_location_block` and the three `/metrics` assertions must keep passing **unchanged**. New assertions are **added** |
| **`docs/01-spec/technical-specification.md`** | **Phase 06: BLOCKS 4, 11, 14** (phase 06 **holds the reservation**) | **Phase 07 does not edit it.** BLOCK 10 routes the `MEDIA-011` quality sentences, the `MEDIA-009` erasure caveat, the decision-J photo-edit claim and the ≥1-photo sentence to the coordinator with exact replacement text |
| **`docs/02-database/db-retention.md`** | **Phase 06: BLOCK 15** · **Phase 03: BLOCK 5** | The erasure sentence is `MEDIA-009`'s. **Route, do not edit** |
| **`docs/01-spec/architecture-structure.md`** | **Phase 07: BLOCK 10** (the `/media/` security bullet) | Only after BLOCK 9 has landed, so the bullet does not claim a block that does not exist |
| **`docs/02-database/db-schema.md`** | **Phase 07: BLOCK 10** (the `ad_images.image` region only) · **Phase 06: BLOCK 13/17** (other tables) | Different regions, different commits. Only the `ad_images` region is phase 07's |
| **`docs/04-user-stories/seller-stories.md`** | **Phase 07: BLOCK 10** (US-S5) · **Phase 05** (US-S7) · **Phase 11** (story reconciliation) | **Q07-12** decides whether US-S5 is phase 07's or a docs sweep's. Phase 05 owns US-S7; do not touch it |
| **`docs/ops/docker-deployment.md`** | **Phase 07: BLOCK 10** (the media-security list) | **Q07-12** decides scope. Not named in the report and not in any other plan in the set |
| **`src/backend/apps/ads/views/edit.py`** | **Phase 05: BLOCKS 2 and 8** (behaviour) · **Phase 07: BLOCK 10** (the two docstrings **only**) | Docstrings are documentation and are phase 07's. The two `submit_ad(… photos=[])` branches and `_apply_price_change` are **phase 05's**. Phase 07 changes **no** behaviour in this file |
| **`src/backend/apps/media/models.py`** | **Phase 07: BLOCK 8** (the `ME-003` docstring reconcile) | No schema change. The `MediaDeletionError` table and its migration already exist |
| **`src/telegram_bot/handlers/ad_create/`** | **Phase 02** (in-flight) · **Phase 05: BLOCK 11** (`ad_copy`) · **Phase 07: BLOCKS 7 and 12** | Phase 07 touches `photos.py` (budget check) and `entry.py` (only if Q07-7 option (c)) in BLOCK 7, and the FSM in BLOCK 12. Re-read before editing |
| **`src/backend/locale/*/LC_MESSAGES/django.po`** | **Phase 07: BLOCKS 7, 11, 12** · **Phase 14** · **Phase 05/06** | **Append; never regenerate wholesale.** `ru` and `bs` both non-empty for every new string |
| **`src/backend/conftest.py`** | **Nobody in this plan** | The most contended file in the repository. **No block in this plan may edit it.** If a block appears to need a new fixture, that is a signal the test is over-fitted |
| **`.ai/audit/**`** | **Nobody.** Unmodifiable by mandate | `git status --short .ai` must show **no new modifications** beyond the pre-existing deletions and this plan's own file |
| **`.ai/plans/**`** | Each Planner owns its own plan file | This plan may not edit `01-…` through `06-…`. Every cross-reference lives in **this** file |

### 5.4 The `AD-003` / `MEDIA-001` boundary — closed, and not re-openable

| Half of phase 05's `AD-003` | Layer | Owner | Status |
|---|---|---|---|
| `pre_delete` erases a key with no "still referenced?" check | `apps/media/signals.py` | **Phase 07 — `MEDIA-001`** | **ABSORBED.** BLOCK 2 carries the invariant and the refcount decision |
| `copy_ad` reuses the source ad's storage keys | `apps/ads/services/copy_service.py` | **Phase 05 — `AD-003`** | **RETIRED.** Under the refcount model the aliasing is **legal behaviour, not a bug**: the data-loss half is retired by BLOCK 2, and what survives is a design trade-off with no defect in it — a copy shares bytes with its source, which is cheap in disk and means the copy has no independent photo lifecycle |

Three consequences, stated so nobody has to re-derive them:

1. **Phase 05 must not ship the byte-copy fix.** Doing so alongside a refcount-aware
   `pre_delete` pays for both remediations and gains nothing — the exact hazard phase 05's
   `VAL-004` warned about. `.ai/plans/05-ad-lifecycle-remediation.md` §5.6 already records
   `AD-003` as **RETIRED** and §5.1 states the one thing phase 05 must never do.
2. **Phase 07 must not resurrect it.** No phase-07 block may convert aliasing into a byte
   copy, add a uniqueness constraint to `ad_images.image`, or change `copy_ad`. BLOCK 2
   lists `copy_ad` as **read-only**.
3. **The infeasible option is recorded so it stays closed.** A unique index on
   `ad_images.image` cannot be created: `media_gate`'s own docstring *depends* on
   non-uniqueness and uses `filter` specifically to survive it; the seed generator produces
   cross-owner sharing at volume; and `copy_ad`'s aliasing is behind a shipped `/copy` command
   with dedicated green tests. A refcounted `MediaObject` row costs a model, a migration, a
   de-duplication backfill, a new resolution path on every key lookup, **and still needs the
   seed-sharing special case** — the same behaviour for far more machinery. Project rules 5
   and 7 point at the reference check.

### 5.5 The `AD-006` / `MEDIA-002` ownership question — resolved by ratio, and the tie-breaker

Phase 05's plan §5.5 is explicitly an **open question** and it *asks and waits*: `AD-006`'s
minimal fix is *"re-scope the lookup to `(ad, sha256)`"*; `MEDIA-002`'s fix additionally
**reclaims the skipped file**. Phase 05's own tie-breaker is recorded verbatim: *"re-scoping
the lookup alone does **not** address the orphaned promoted file."*

**The resolution, stated once so it is not re-derived:**

- **The higher rating wins.** `MEDIA-002` is **HIGH**; phase 05's `AD-006` is **MEDIUM**.
  `MEDIA-002` is the record.
- **If phase 07's BLOCK 1 lands first**, phase-05 BLOCK 13 **ships no production code** and
  becomes a cross-reference. The orphan consequence is a named part of BLOCK 1 and is not
  optional there.
- **C-2 sharpens this.** The tree shows **no shipped green test encodes cross-ad dedup**, so
  the re-scope is an **unopposed behaviour change**, not a test-expectation change. Phase 05
  has even less reason to ship a competing half-fix: it would be a strictly weaker change to
  the same predicate in the same function.
- **If phase 05 ships first** (it must not, but if it does), BLOCK 1 must **re-read**
  `create_or_skip` immediately before editing, and must still deliver the reclaim — the half
  phase 05 planned to omit is the half that leaves four files per occurrence.
- **What phase 07 does not take:** the **photo-count enforcement** question. Whether any gate
  requires ≥1 `AdImage` is `Q07-2` and it is a **scope** question, not a mechanism one; the
  ads-side framing of it belongs to phase 05. If `Q07-2` resolves to option (b), BLOCK 1's
  scope grows into a new rejection path with a new translated message, and **the coordinator
  must be told before that lands** so phase 05 can stop work on the same predicate.

### 5.6 The `MEDIA-003` → `03-DB-005` merge — what the record must say

Phase 03 is the record. Phase 07 ships nothing for it. Two corrections the record should
carry, and phase 07 **routes both** rather than editing `.ai/audit/**`:

1. **"No self-healing path" is overstated.** The sweep is one-directional, but the *revenue*
   side of the same diff — detecting a row whose file is missing — did not exist anywhere
   until the Validator filed `MEDIA-012`. `DB-005` should cross-reference `MEDIA-012` rather
   than assert that detection is impossible. **The detector is phase 07 BLOCK 6.**
2. **`deleted += 1` counts attempts, not confirmed removals**, so the command's success line
   ("Deleted N orphaned media files") is not a measurement. **Folded into phase 07 BLOCK 6**,
   and `DB-005` should note that it is fixed there rather than shipping it twice.

### 5.7 Forward dependencies other phases should plan around

| Phase | Depends on phase 07 for | Risk if phase 07 is silent |
|---|---|---|
| **03 — db/concurrency** | BLOCK 6 needs phase-03 BLOCKS 6 and 8 to have settled; BLOCK 7 needs BLOCK 6's TTL. Phase 03 also owns the promotion/exclusion-set design that BLOCK 1's reclaim is written against | Two agents edit `Command.handle` concurrently; or phase 07 designs a byte budget against a 2 h TTL that phase 03 is about to change |
| **05 — ad-lifecycle** | BLOCK 13 (AD-006) is superseded if BLOCK 1 lands. `AD-003` is retired and must not be shipped. BLOCK 10's doc correction on the photo-edit promise must agree with phase 05's BLOCKs 2 and 8 | Phase 05 ships the byte-copy fix alongside a refcount-aware `pre_delete` and the project pays for both; or a competing half-fix to the same predicate |
| **06 — PII/consent** | Phase 06 holds `technical-specification.md`; BLOCK 10 routes four sentences to it. Both phases allocate an `AdvisoryLockId` and both append to `HOURLY_COMMANDS` | Two phases compute "the next free integer" concurrently and **one command silently never takes its lock** — `test_advisory_lock_ids.py` does not catch reuse. And the spec's ≥1-photo and no-optimisation sentences stay wrong |
| **11 — tests** | The three incidental rewrites this plan schedules, and the fact that BLOCK 5 is the only block requiring the **full** suite | Phase 11 re-derives a coverage gap that BLOCK 6's §4.7 assertion already closes, or skips the nightly `seed` marker |
| **12 — production-ops** | Three read surfaces: the `staging_bytes` gauge, the dangling-row report, and the `MediaDeletionError` predicate | Phase 12 invents its own queries, or alerts on a signal nobody can produce |
| **13 — performance** | `MEDIA-006`'s `limit_req` reduces the unbounded `AdImage` lookup load; `MEDIA-012`'s sweep-based detection adds a read-only loop over rows once per hour, not per request | Phase 13 plans for a `media_gate` hot path this phase already relieved, or adds an index for a loop that runs hourly |
| **14 — i18n** | BLOCKS 7, 11 and 12 add strings; the locale files are append-only and shared | A wholesale regeneration by any phase discards phase 07's `ru`/`bs` entries, or the i18n gate failure gets triaged as a regression instead of a consequence |
| **15 — authorization** | BLOCK 11 adds a **delete surface** on `AdImage` and depends on phase 15's permission predicate being settled | A new delete surface lands with an unstated predicate, and phase 15 either re-derives it or reconciles two copies |

---

## 6. Out of scope for this plan

Every de-scoping below is **routed**, not dropped. A de-scoped item with no destination is a
re-filed finding.

### 6.1 De-scoped by ownership (routed, not dropped)

| Item | Routed to | Why |
|---|---|---|
| **`07-MEDIA-003`** — the promote-before-transaction window and the sweep's snapshot→walk→unlink with no re-check | **Phase 03, `03-DB-005` (BLOCK 8)**, which also absorbed phase 01's `ENT-009` | Byte-identical mechanism and remedy. **Phase 07 must not ship a staging-window fix.** Two obligations phase 07 *does* carry: the detector is `MEDIA-012` (BLOCK 6), and `DB-005`'s record should carry the two corrections in §5.6 |
| **Phase 05's `AD-003`** — the `copy_ad` byte-copy question | **Phase 05**, as **retired**. §5.4 states the ruling | Resolved by the refcount decision: aliasing is legal behaviour, not a bug. Phase 07 must not resurrect it |
| **The `AdImageAdmin` permission predicate** | **Phase 15** | BLOCK 11 creates a delete surface; the *predicate* is phase 15's. Phase 07 must not write an ad-hoc one |
| **`AdAdmin`'s editable field set** | **Phase 05 BLOCK 6** | Independently re-confirmed by `MEDIA-005`'s introspection, but phase 05 owns the fix. Phase 07's BLOCK 11 touches `AdImageAdmin` only |
| **`docs/01-spec/technical-specification.md`** — the ≥1-photo sentence, the no-optimisation / full-size pair, the erasure caveat, decision J's photo-edit claim | **Phase 06** (it holds the reservation; its BLOCKS 4, 11, 14 edit the file) | BLOCK 10 delivers a written request naming each sentence and its exact replacement text. **Phase 07 does not edit the file** |
| **`docs/02-database/db-retention.md`** — the erasure-removes-physical-files claim | **Phase 06 BLOCK 15** and **Phase 03 BLOCK 5** | Two claims on one file. Routed with exact replacement text |
| **The `DB-005` Option A/B/C decision** (the promotion/exclusion-set design) | **Phase 03 BLOCK 8's Q7/Q8** | Phase 07's BLOCK 1 writes its reclaim against the **key**, not a directory, so it survives whichever option wins. The **choice** is phase 03's |
| **The `MEDIA-002` enforcement point, if `Q07-2` resolves to option (b)** | **Co-ordinator** — a scope expansion touching the ads-side photo semantics | Under option (b) BLOCK 1 grows a new rejection path with a new translated message. Phase 05's Q6 owns the ads-side framing; the coordinator decides who ships it |
| **Alerting for the three read surfaces** (`staging_bytes`, dangling rows, `MediaDeletionError`) | **Phase 12** | Phase 07 supplies the read surface and records the predicate in the commit body. **No alert is built here** |
| **The unbounded `AdImage` lookup load on `media_gate`'s hot path** | **Phase 13** | `MEDIA-006`'s `limit_req` reduces it — a complement. Phase 07 adds **no index** and **no per-request stat** |
| **The `NIST-3` `test_nginx_config.py` coverage gap for `nginx.dev.conf`** | — (closed here) | **Not** de-scoped: BLOCK 9 extends the existing harness to both configs, which is in-pattern and cheap |
| **`VAL-006` (admin-capability methodology)** | — (binding rule, not a work item) | Upheld as a standing rule: for any admin capability claim, introspect `admin.site._registry[Model].get_form(request)` and `get_actions(request)`. BLOCK 8 and BLOCK 11 both carry it |
| **`VAL-003` (the ID-collision convention)** | — (binding convention, not a work item) | Upheld: every citation in this plan is cycle-scoped `07-MEDIA-0NN`. BLOCK 8 also reconciles the `ME-003` citation that motivated it |
| **`VAL-005` (the Auditor's diff excluded `seed/`; the "missing key" test passes for the wrong reason)** | — (closed here) | BLOCK 2 and BLOCK 6 both deliver the reconciliation **including `seed/`**, and BLOCK 6's negative test proves `media_gate` is unchanged. The finding is closed by the work, not routed |
| **`VAL-004` (the report's first-listed option is infeasible)** | — (closed, recorded) | §5.4 records why a unique index cannot be created, so no future implementer dead-ends on it |
| **Populating the seed manifest's empty `default.photos` pool** | **Nobody — explicitly not a work item** | C-1: the shipped manifest's default pool is empty, so cross-category key sharing does not occur today. Populating it would *create* a sharing pattern the system does not have and would make `MEDIA-001`'s fix carry load it does not need. **There is no finding here**, and BLOCK 2's Q07-1 measurement is a measurement, not a defect report |

### 6.2 De-scoped by design (deliberately not done here)

| Item | Why |
|---|---|
| **A unique constraint on `ad_images.image`** | Explicitly forbidden. §5.4 states the three pieces of shipped evidence that make it infeasible. It is also a **migration** on the hottest image table, for a fix that costs four lines |
| **A refcounted `MediaObject` model** | Explicitly rejected before implementation. A model, a migration, a de-duplication backfill, a new lookup path — and it still needs the seed-sharing special case, so it buys the identical behaviour for far more machinery (project rules 5 and 7) |
| **A filesystem check in `media_gate`** | Explicitly forbidden, and it is the single most important negative in this plan. It breaks `TestMediaAccessControl` (9), `TestMediaGateDeclinedUser` (3), `TestMediaGateThumbnailResolution` (7) and `TestMediaGateCacheControl` (9), most sharply
  `::test_shared_seed_key_across_multiple_ads_returns_200` — two PUBLISHED ads sharing a key, asserting `200`, deliberately writing **no file**. It also adds a stat to the hottest image path. Detection belongs in the sweep (BLOCK 6) |
| **An application-level rate limiter on `media_gate`** | BLOCK 9's nginx `limit_req` is the in-pattern control and reuses the existing `browse_limit` zone. An app-level limiter would be a second policy in a different language, on a path the report itself rates MEDIUM |
| **Automatic repair of dangling rows** (nulling columns, deleting rows) | Explicitly out of scope. The original bytes are gone; "repair" is destructive, and whether to null a column or drop a row is an **operator's** decision informed by BLOCK 6's report. The block ships **detection**, which is what converts an unbounded silent failure into a bounded observable one |
| **A backfill of `MEDIA-004`'s already-broken rows** | No data migration is scheduled. Re-running `backfill_thumbnails` in an environment with real broken rows is an **operational** action; BLOCK 3 re-enables the command and BLOCK 6 makes the residue visible |
| **A reseed of the `seed/` directory** | Non-destructive, but a data operation and an **operator's** decision. BLOCK 5 makes the generator correct; the recovery is a reseed, not a migration |
| **Re-deriving stored bytes after `MEDIA-011`'s constant** | The mixed-quality store is the accepted, documented cost. A re-encode of already-stored originals would be a destructive, unbounded data operation for a LOW maintainability finding |
| **A `telegram_file_id` short-circuit for upload dedup** | `telegram_file_id` is stored but explicitly **not** used for dedup and not usable in an `<img src>`. Adding a short-circuit is a **separate decision** with its own trade-offs, and it is the mechanism that makes `MEDIA-002`'s dedup hit deterministic — which is a fact to record, not a behaviour to add |
| **A per-seller staging budget, if Q07-7 concludes attribution is infeasible** | The staging key is **deliberately** PII-free. Making it per-seller means either a key-format change — which would break the unguessability rationale, the `KEY_FORMAT_REGEX`-derived `CheckConstraint`s and every `AdImage.storage_keys()` consumer — or a new mapping table. That is a storage-contract change for a MEDIUM availability finding. The gate decides; the plan does not pre-empt it |
| **A shared nginx include fragment, if Q07-13 concludes the configs are intentionally asymmetric** | A third file in `docker/nginx/` is a structural change to the image's config layout, and an include that is not mounted silently disables the control. The gate decides |
| **Restoring data after a revert** | BLOCKS 1, 3, 4, 8, 11 and 12 all have one-way data effects. The rollback story is *"stop it running for new operations"* plus a stated fact that the destroyed data does not return — never a reverse migration that re-creates the problem. Each block's commit body says so |
| **Enabling any new feature flag** | No flag is introduced. `MEDIA-007`'s budget is a **setting**, not a toggle; the rollout gate is BLOCK 6 having landed so the residue is observable |

### 6.3 Explicitly forbidden while implementing

1. Adding a filesystem check, a `FileResponse`, or any cache-header change to `media_gate`.
2. Adding a unique index or constraint on `ad_images.image`, or converting `copy_ad` aliasing
   into a byte copy.
3. Renaming `delete_adimage_files_on_delete`, or changing `AdImage.storage_keys()`'s signature
   or return order.
4. Routing any new byte-freeing path through `apps.media.signals.delete_photo` rather than
   through the row deletion and `on_commit` chain — or through
   `apps.media.services.filesystem.delete_photo` when the row deletion is the correct trigger.
5. Changing `_STAGING_TTL_SECONDS`, `_walk_media_files`'s **deletion** scope, or
   `_reclaim_stale_staging`.
6. Moving `submit_ad`'s `move_staging_to_permanent` inside the transaction, or taking
   `AdvisoryLockId.SWEEP_ORPHANED_MEDIA` on the write side — that is `03-DB-005`.
7. Reusing an existing `AdvisoryLockId` value for a new command.
8. Editing `docs/01-spec/technical-specification.md` or `docs/02-database/db-retention.md`.
9. Editing `AdAdmin`'s field set, `fieldsets` or permission predicates.
10. Removing the EXIF/ICC strip, or changing `ThumbnailService.QUALITY`.
11. Running a wholesale `makemessages`, regenerating a locale file, or reverting another
    phase's entries.
12. Editing `.ai/audit/**`, another phase's plan file, `src/backend/conftest.py`, or the audit
    rubric.
13. `git reset` / `git checkout` / `git restore` / `git stash` / `--amend` / force-push, or
    reverting a file another agent changed.
14. `git add -A` or `git add .`; committing more than one block in one commit; committing
    without an explicit instruction.
15. Writing a test that asserts a line number, an enumerated admin-registry set, a literal
    private name, a hard-coded quality number, or the mere presence of a symbol.
16. Repeating the report's refuted claims: the seed default-pool narrative (C-1), the
    broken-image icon (C-6), "no automated test for nginx" (C-3), or "no test asserts cross-ad
    dedup" (C-2, in the *opposite* direction — there is **no** such test).

---

## 7. Per-block risk register

Severity here is **this Planner's assessment of execution risk for the change**, not the
finding's severity. "FS↔DB" covers filesystem-versus-database consistency. "Migration" covers
DDL, backfill and rollback. "Lock" covers advisory-lock allocation. "Txn" covers `atomic()`
nesting and rollback semantics. "Contention" covers shared files. "URL" covers any change to
a served URL shape.

| Block | Risk | Kind | Likelihood | Impact | Mitigation / detection | Residual |
|---|---|---|---|---|---|---|
| **All** | An implementor runs `git add -A` and commits the 19 pre-existing `.ai/audit/**` deletions or another phase's uncommitted work | Process | Med | **High** | §1.3's hard staging rule; `git status --short` immediately before **every** commit; the audit tree is unmodifiable by mandate; §5.3 names every contended file | Very low |
| **All** | A block runs with its gate unanswered, or the Implementor silently picks an option | Process | Med | **High** | Every gate is a labelled decision in §3 and a row in §0.5, repeated verbatim in the task YAML's `extra_context`; §8.1 checks a written answer exists for all fourteen | Low |
| **All** | A block's tests are **asserted** rather than **run**, or run on the host where there is no database | Process | Med | **High** | Every block names its exact Docker gate command; tests run **only** through the `test` service (§1.1) | Low |
| **All** | A red gate is captured while another phase's validator is running and a teardown race is reported as a product defect | Process | High | Med | §1.1: re-run **serially** before reporting. The symptom to recognise is `test_mko_bazuna does not exist` / `relation "..." does not exist` | Low |
| **All** | A **shipped green test** that pins a defect is "fixed" by changing production code instead | Correctness | Med | **High** | Project rule 2 is restated in §1.4. **Only three** assertions are slated for treatment, each named and justified: `test_seed_original_strips_jpeg_comment` (BLOCK 5, return contract); `test_atomic_write_collision_raises_file_exists` (BLOCK 3, **only** under the recorded option (b)); an exact-registry-set test (BLOCK 8, **only if** Q07-10 finds one). C-2 shows `MEDIA-002` needs **none** | Low |
| **All** | A new user-visible string ships without non-empty `ru` **and** `bs` | i18n | Med | Med | Only BLOCKS 7, 11 and 12 add strings; each names the locale files; §5.3 forbids a wholesale regeneration that would clobber phases 05, 06, 11 and 14 | Low |
| **All** | The plan's refuted claims are repeated by an implementor who read only the report | Correctness | **High** | Med | §0.2.1 states C-1 … C-6; §6.3 item 16 forbids repeating any of them; the **negative test** in BLOCK 6 and the **manifest test** in BLOCK 5 are the tripwires | Low |
| **1** | The reclaim deletes a file inside `transaction.atomic()` and a rollback leaves a row with a **missing** file — manufacturing `MEDIA-012`'s unobservable failure on purpose | FS↔DB · Txn | **Med** | **High** | **Q07-3** is a hard gate; option (c) is listed and visibly rejected; the rollback test in BLOCK 1 encodes the chosen option's guarantee and names it in its docstring; the Implementor is told to write the reclaim against the **key**, so it survives `DB-005`'s Option A | Low |
| **1** | The reclaim is routed through `apps.media.signals.delete_photo` and perturbs the exactly-once counters | Correctness | Med | Med | Binding constraint 1; `test_delete_photo_single_call.py` is in the block's gate command and in its "keep green" list | Very low |
| **1** | The Implementor rewrites `test_ad_image_service.py` because the report told it to | Scope | Med | Low | C-2 forbids it; the report's claim is corrected in the binding constraints; the block's "keep green" list names the file | Very low |
| **1** | The re-scope creates a row whose `sha256` collides with an **existing** row on the same ad, so the ad ends with a duplicate | Correctness | Low | Med | The predicate is `(ad, sha256)`, which is already the same-ad contract the shipped test pins; the "both ads have exactly one image" test asserts the count | Very low |
| **1** | `submit_ad` is edited on a stale read and phase 03's or phase 05's concurrent change is clobbered | Contention | **High** | Med | §5.3 names it as the most contested file in the plan set; §1.3 staging rule; re-read immediately; stop and report rather than clobber | Med — accepted |
| **2** | The check is moved to `pre_delete` time, reintroducing the off-by-one and deleting a key another row still references | Correctness · FS↔DB | Low | **High** | Binding constraint: the `on_commit` property is stated in the code comment **and** asserted by its own test | Very low |
| **2** | A "check → unlink → re-check" design is used instead of "check → skip", so a key reaches `delete_photo` twice | Correctness | Med | Med | Q07-4's options are specified with this consequence named; `test_delete_photo_single_call.py` is the tripwire and is in the gate command | Low |
| **2** | The receiver is renamed, breaking `test_media_config.py`'s by-identity assertion | Correctness | Low | Low | Binding constraint 3; the test is in the "keep green" list and in the gate command | Very low |
| **2** | The check is implemented on one column and a shared **thumbnail** key still gets freed | Correctness | Med | **High** | The block requires all four columns (`image`, `thumbnail_small/medium/large`); the test's "still exists" assertion covers a shared key on every column the report names | Low |
| **2** | BLOCK 1 has not landed, so the check guards an accidental-aliasing producer that is about to disappear, and its row-count assumptions are wrong | Process | Med | Med | Hard edge 1 → 2; §4.2 states the reason | Very low |
| **3** | Option (b) is chosen and the blanket `except Exception` is **narrowed**, turning a previously-successful publish into an exception on a path phase 05 also owns | Regression · Txn | Med | **High** | The catch decision is an explicit gate with both options stated; the block's "keep green" list and §5.3's `submission.py` reservation; the commit body must name the change | Low |
| **3** | The temp files are created in a system temp directory, so `os.replace` is not atomic and a cross-device move silently degrades to a copy | FS↔DB | Med | Med | Binding constraint 5: temp files go in the **destination directory**; the all-or-nothing test asserts no temp file survives | Low |
| **3** | The stale-file guard is written to prefer "stale" unconditionally, so a genuine concurrent double-generation now deletes and rewrites | Correctness | Low | Low | The block requires both cases to be tested — stale regenerates, populated skips | Very low |
| **4** | The constant's value is changed "while we are here", re-encoding every new upload and making the store mixed-quality without anyone deciding it | Regression | Med | Med | Binding constraint 2; the mixed-quality consequence is required in the commit body | Low |
| **4** | The spec sentences are edited instead of routed, colliding with phase 06's four blocks | Contention | Med | Med | Binding constraint 3; §5.3 names the reservation; BLOCK 10 carries the written request | Low |
| **5** | BLOCK 3 has not landed, so the stale-file guard the fix reuses does not exist and is re-implemented differently | Correctness | Low | Med | Hard edge 3 → 5; test 2 fails if the guard is bypassed | Very low |
| **5** | A `NULL` thumbnail column breaks `_backfill_image_hashes` and every seeded row gets an empty `sha256`, which then makes `MEDIA-002`'s dedup behave differently in a seeded environment | FS↔DB · Correctness | Med | Med | Binding constraint 3 requires the Researcher to answer it and a test to state it, rather than assuming | Low |
| **5** | The return-type change is not propagated to `ImageGenerator._preprocess_images` (the deprecated eager variant) | Correctness | Med | Low | The block's surface list names the module; the "keep green" list covers `test_seed.py` in full | Very low |
| **6** | Detection leaks into `media_gate` and breaks ~28 tests across four classes, most sharply `::test_shared_seed_key_across_multiple_ads_returns_200` | Correctness | Med | **High** | §0.2.2 hazard 1, §6.2, §6.3 item 1, and BLOCK 6's **negative test** that asserts the shared-key 200 is still returned; `test_media_security.py` is in the gate command | Very low |
| **6** | A merge conflict with phase-03 BLOCK 8 on `Command.handle` is resolved by clobbering one side | Contention | **High** | Med | The external gate; §4.4's order; §5.3 names the file; the block re-reads and stages explicitly; §1.3's stop-and-report rule | Med — accepted |
| **6** | The report mode's scope is chosen so that `seed/` is excluded — reproducing the exact defect `VAL-005` records | Correctness | Med | Med | **Q07-9** forces a written answer; BLOCK 2 and BLOCK 6 both require the reconciliation **including `seed/`**; the block's test 1 is the tripwire | Low |
| **6** | The `deleted += 1` fix changes a contract some operator script parses | Compatibility | Low | Low | The change makes the number *true*; §2 records it as folded in from `DB-005`'s second correction. Assert behaviour, not the log string | Very low |
| **7** | A **global** budget refuses a legitimate seller because an abusive account filled the volume, and the message implies otherwise | Product | **High** | Med | **Q07-7** is a gate; the block requires the positive case to be tested explicitly, not only the rejection; the block's rollback section names the fairness cost as the accepted trade-off of a global budget | Med — accepted |
| **7** | Per-seller attribution is implemented by changing the staging key format, breaking the unguessability rationale and every key `CheckConstraint` | Design | Low | **High** | Binding constraint 5; the Researcher's task is **feasibility**, and a negative finding forces (a) or (c) | Very low |
| **7** | The gauge is set only in the hourly sweep, so phase 12's alert fires on a reading up to an hour stale — the exact window the finding is about | Observability | **High** | Med | **Q07-8** forces a written answer about multiprocess gauge semantics before the metric ships; the block's commit body states which semantics shipped | Med — accepted |
| **7** | The budget check walks the staging directory on every upload | Performance | Med | Low | The block requires a bounded implementation (`os.scandir` over the top level, or a value the sweep already computed and the upload path **reads**) | Low |
| **8** | The new `AdvisoryLockId` **reuses** a value, and two commands serialise silently | Correctness · Lock | Low | **High** | `test_advisory_lock_ids.py` does **not** catch reuse — stated in the block. Three files, one commit, coordinator told first, free integer re-read at that moment (C-4: **14**, not 13) | Very low |
| **8** | Phase 06 BLOCK 15 allocated the same integer between phase 07's read and its write | Lock · Contention | Med | **High** | §5.3 names the shared pair; the coordinator sequences the two allocations | Low |
| **8** | The retention sweep's TTL is invented rather than recorded, and purges diagnostic rows an operator still needs | **Irreversible** | Med | Med | **Q07-14** forces a written answer; `--dry-run` is mandatory; a row inside the TTL is proven to survive; §8 states a revert does **not** restore purged rows | Low |
| **8** | `apps/media/admin.py` breaks a test that asserts the exact `admin.site._registry` set | Correctness | Low | Low | **Q07-10** forces the question to be answered before the file is created; if such a test exists it is updated **deliberately** with the reason named and no other assertion added | Very low |
| **8** | The `HOURLY_COMMANDS` entry is forgotten, the command is never dispatched, and `_validate_commands` does not raise | Correctness | Low | Med | Binding constraint: `_validate_commands` does **not** raise on a missing entry; `test_scheduler_wiring.py` is in the gate command and in the "keep green" list | Very low |
| **9** | A regex typo in the script-execution block 403s **every** genuine photo — a site-wide image outage | Regression | Med | **High** | The harness asserts the block exists and carries `deny all` and `return 403`; `nginx -t` for syntax; and the **irreducible** deployed-stack real-key smoke check is recorded as an operator step in the commit body | Med — accepted |
| **9** | The added block shadows `location /media/`'s `proxy_pass`, so no image is proxied at all | Regression | Low | **High** | Test 3 asserts the location is a `~*` match, not a prefix — a real nginx semantic, not a substring; the real-key smoke check is the second control | Very low |
| **9** | A shared include fragment is added and the file is not mounted in one of the two environments, **silently disabling** the control | Config | Low | **High** | Q07-13 makes this a gate, not a default; the block must state that a third file is a structural change to the image's config layout and name the failure mode | Very low |
| **10** | The ownership rule is written **before** BLOCK 2 lands, so the document states an intent rather than a behaviour | Documentation | Med | Med | Hard edge 2 → 10; the block may not start until BLOCK 2 has landed | Very low |
| **10** | The doc is written from the **report's** reach narrative, which C-1 shows is false for the shipped manifest | Documentation | Med | Med | Binding constraint 3; the corrected text must use BLOCK 2's **Q07-1** measurement or state the invariant **without** a reach claim; BLOCK 5's manifest test is the tripwire | Low |
| **10** | A reserved file is edited instead of routed, and a concurrent phase's block loses its edit | Contention | Med | **High** | Binding constraint 1; §5.3 names both reservations; the block's deliverable for those is a **written request**, and §6.1 records the routing | Low |
| **10** | A corrected sentence is overtaken by phase 05's BLOCKs 2 and 8, which own the same photo-edit promise | Documentation | Med | Med | The commit body names the files phase 05 owns behaviourally; the "second editor re-reads" rule from §5.3 | Low |
| **10** | The `architecture-structure.md` bullet is corrected to claim an nginx block that BLOCK 9 has not shipped yet | Documentation | Low | Med | Binding constraint 7; the block may not make the claim until BLOCK 9 has landed | Very low |
| **11** | The removal service calls `delete_photo` directly instead of deleting the row, becoming a **second data-loss route** | FS↔DB | Med | **High** | Hard edge 2 → 11; binding constraint 1; test 3 (the shared-key case) is the tripwire and fails if the service bypasses the invariant | Low |
| **11** | The new delete surface is not permission-gated or not audited, creating an authorization gap | Security | Med | **High** | All five agents required; test 2 asserts a non-staff caller is refused **and** that no audit row is written; test 1 asserts exactly one `ModeratorActionLog` row; phase 15 is told **before** the block lands | Low |
| **11** | The `@admin.action` is decorated but not assigned to `actions`, so it exists and is unreachable | Correctness | Med | Med | Test 5 asserts it appears in `AdImageAdmin.get_actions(request)` — introspection, not source reading (`VAL-006`) | Very low |
| **11** | `Q07-6` is never answered and the block ships the expensive half of a capability the owner wanted deferred | Process | Med | Med | The gate is in §0.5, in the block, and in the task YAML; §8.1 checks a written answer exists. The block's two branches are both written out, so "deferred" is an executable outcome and not a dead end | Low |
| **12** | The FSM `photos` list is left inconsistent after a removal, so `/cancel` double-deletes a key or `submit_ad` receives a stale list | Correctness · FS↔DB | Med | Med | The four design questions are recorded before code; tests 1 and 3 are mandatory; `test_delete_photo_single_call.py` is in the "keep green" list so the at-most-once property is checked | Low |
| **12** | The 5-photo cap is not re-derived, so a seller can upload five, remove one and upload five more — **circumventing the very cap** | Correctness | Med | Med | Test 1 asserts the new count explicitly: the seller can upload three more, **not** five. Binding constraint 4 | Very low |
| **12** | The bot implements its own removal instead of consuming BLOCK 11's service | Design | Med | Med | Binding constraint 1; the "keep green" list covers the media tests, so a divergent implementation shows up as a code-review failure rather than a green suite | Low |
| **12** | The bot calls `apps.media.signals.delete_photo`, perturbing the exactly-once counters | Correctness | Low | Med | Binding constraint 5 names the exact module and the exact alternative | Very low |
| **12** | A new bot string ships without `bs`, failing the gate, and it is triaged as a regression | i18n | Med | Low | Binding constraint 2; test 4 asserts both locales resolve; §1.2 states the sequence and the append-only rule | Very low |

---

## 8. Definition of done for the whole plan

Phase 07 is complete when **all** of the following hold.

### 8.1 Scope

- [ ] All 12 filed IDs have a recorded disposition: **11 implemented** (`07-MEDIA-001`, `002`,
      `004`, `005` (across BLOCKS 11 and 12), `006`, `007`, `008`, `009`, `010`, `011`,
      `012`) and **1 merged away** (`07-MEDIA-003` → `03-DB-005`, restated so it is not
      silently re-filed).
- [ ] The three non-finding work items shipped: the **`deleted += 1` fix** and the **§4.7
      store↔database assertion** (BLOCK 6), and the **`ME-003` traceability reconcile**
      (BLOCK 8).
- [ ] **All fourteen** questions `Q07-1` … `Q07-14` are either answered with a **written**
      record naming the option chosen and the consequences accepted, or explicitly
      **routed** with a named destination. **Silence is not an acceptable outcome for any of
      them**, and a block whose gate is unanswered did not start.
- [ ] Every de-scoping in §6 has a named destination; none was dropped.
- [ ] The `AD-003` retirement (§5.4) and the `AD-006`/`MEDIA-002` tie-breaker (§5.5) were
      **communicated to the coordinator**, not left implicit.

### 8.2 Gates — all green

- [ ] `uv run ruff check src/` → exit 0.
- [ ] `uv run basedpyright src/` → **0 errors**.
- [ ] `.\Makefile.ps1 test` → full suite green (seed marker skipped) after **every** block.
- [ ] **`$dc run --rm test` (the full suite, including the nightly `seed` marker) green after
      BLOCK 5.** This is the only block that requires it.
- [ ] `apps/ads/tests/test_i18n_completeness.py` green after BLOCKS 7, 11 and 12.
- [ ] **Every block's exact gate command from §3 was run and green** — not the full suite
      alone.
- [ ] `apps/core/tests/test_advisory_lock_ids.py` and `apps/core/tests/test_sweep_lock_structure.py`
      green after BLOCK 8, with the three lock files changed in **one** commit.
- [ ] `apps/core/tests/test_scheduler_wiring.py` green after BLOCK 8.
- [ ] `apps/core/tests/test_delete_photo_single_call.py` green after **every** block that
      touches a byte-freeing path (BLOCKS 1, 2, 3, 6, 7, 11, 12).
- [ ] `makemigrations --check` clean — **no block in this plan expects a migration**, so a
      pending migration is a scope error.
- [ ] `git status --short .ai` shows **no new modifications** beyond the pre-existing
      `.ai/audit/**` deletions and this plan's own file.
- [ ] Every red-gate observation was **re-run serially** before being reported as a defect.
- [ ] No commit was made without an explicit instruction; no `git reset`, `git checkout`,
      `git restore` or `git stash` was run at any point.

### 8.3 Per-finding behavioural confirmation

- [ ] **`07-MEDIA-001`** — two `AdImage` rows sharing one key, **different owners**: delete one
      → the file **still exists** and the other ad's image still serves; delete the second →
      the file **is gone**. The check runs **after** commit (its own test proves it), across
      **all four** key columns. `test_delete_photo_single_call.py`,
      `test_ad_image_delete_signal.py`, `test_media_config.py` and `test_copy_ad.py` all pass
      **unchanged**. No migration, no new model, no backfill.
- [ ] **`07-MEDIA-002`** — identical bytes posted to two ads of the **same seller** → both ads
      have exactly one image with **different** keys, and **zero orphan files** remain on disk
      after the reclaim. The same-ad dedup case still returns the existing row.
      `test_ad_image_service.py` is **untouched**. The rollback test encodes the recorded
      Q07-3 option and names it. The commit body cites the ≥1-photo spec sentence, **not** a
      test.
- [ ] **`07-MEDIA-004`** — a leftover `-small.jpg` against a `NULL` column is **regenerated**
      and all three columns end populated; a populated column plus an existing file is
      **skipped**; a failure on the second size leaves **no partial files**; a successful call
      leaves **no temp files**; a second repair run is a no-op.
      `test_thumbnails.py` and `test_backfill_thumbnails.py` pass, and the
      `FileExistsError` contract is either preserved or rewritten **with the reason named**.
- [ ] **`07-MEDIA-005`** — a staff moderator removes one photo: the row is gone, **one**
      `ModeratorActionLog` row is written, and the ad, its text, its status and its view count
      are **untouched**. A non-staff caller is refused with **nothing** deleted and **no** audit
      row. **The shared-key case: the file still exists and the other ad's image still
      serves** — proving the service reuses the invariant rather than re-implementing it. An
      empty reason is refused. The action is reachable from the UI. On the bot side: removing
      the second of three photos leaves the FSM consistent, the 5-photo cap reflects the new
      count, `/cancel` deletes only the remaining keys, and a non-owner cannot invoke the
      callback.
- [ ] **`07-MEDIA-006`** — **both** nginx configs declare a script-execution `location` for
      `/media/` containing `deny all` **and** `return 403`, as a `~*` match (not a prefix);
      both `/media/` locations carry a `limit_req` reusing `browse_limit`; the three existing
      `/metrics` assertions pass **unchanged**; `/protected-media/` is untouched; **no new
      `limit_req_zone` was added**. `nginx -t` passes for both configs and the deployed-stack
      real-key smoke check is **recorded as done** in the commit body.
- [ ] **`07-MEDIA-007`** — an upload above the configured budget is **refused with a translated
      message** that resolves in `ru` **and** `bs`; an upload under it is **accepted**; a
      refused upload writes **no file**; a fresh staging file is **preserved** and a stale one
      **reclaimed** (the TTL is untouched). `_STAGING_TTL_SECONDS` is byte-identical to before.
      The `staging_bytes` gauge exists with the **recorded** semantics from Q07-8.
- [ ] **`07-MEDIA-008`** — after `ImageGenerator.generate`, **every** `thumbnail_*` value on
      **every** created row points at a file that exists; a half-written state is
      **regenerated**, not reported complete; a seed run over the **shipped** (empty-`default`)
      manifest reconciles against its rows. The full suite including the `seed` marker is
      green. The sweep's **deletion** scope is unchanged.
- [ ] **`07-MEDIA-009`** — the ownership rule is stated as **shipped** (N references, freed on
      the last) and **not** as an "except `seed/`" placeholder; the real key scheme is stated
      with the reason there is no `ad_id`; the photo-edit claim says **price** in all three
      places; `architecture-structure.md` claims the nginx block only **after** BLOCK 9 landed.
      A repository-wide search for `refcount` / `reference count` / `ownership` across `docs/`
      now returns the rule. **Four reserved locations were routed with exact replacement text
      and none was edited.**
- [ ] **`07-MEDIA-010`** — `MediaDeletionError` is reachable through the admin changelist with
      `created_at` and `error_type` filters and **no** editable field. If the retention command
      was chosen: `--dry-run` deletes nothing, a row inside the TTL survives with its message
      intact, a row past it is deleted, a second run is a no-op, and the scheduler still starts.
      The new lock id is **14 or whatever is free at that moment**, `SWEEP_ORPHANED_MEDIA == 103`
      is unchanged, and `delete_photo`'s never-raise contract survives.
- [ ] **`07-MEDIA-011`** — the quality is **declared, named and used**, asserted by reading the
      constant the save call uses and **not** by asserting a literal number; the two quality
      constants are **adjacent**; the eight `TestStripPhotoExif` tests and the six
      `TestExifStripping` tests pass **unchanged**; the mixed-quality consequence is stated in
      the commit body. The two spec sentences were **routed, not edited**.
- [ ] **`07-MEDIA-012`** — the check mode **reports** a row whose file is gone and **reports
      nothing** when the store and the database agree, with the **recorded** scope from Q07-9;
      the store↔database assertion (rubric §4.7) finds **zero** dangling rows and **zero**
      orphan files, **`seed/` included**; the reported deletion count matches the number of
      files actually removed; all nine existing `test_sweep_orphaned_media.py` tests pass; and
      **the negative proof holds** — `media_gate` still returns `200` + `X-Accel-Redirect` for
      a shared key with **no file on disk**.

### 8.4 Cross-phase integrity

- [ ] **No staging-window fix was shipped.** `move_staging_to_permanent`, its call site in
      `submit_ad`, and the sweep's **deletion** scope are byte-identical to before this plan
      (`03-DB-005` is phase 03's).
- [ ] `_STAGING_TTL_SECONDS` is unchanged (phase-03 BLOCK 6).
- [ ] `AdvisoryLockId.SWEEP_ORPHANED_MEDIA == 103` is unchanged; `CONSENT_HARD_DELETE == 3` was
      not renumbered; a new member exists **only** if BLOCK 8 required one, in which case
      `enums.py`, `advisory_lock.py`'s docstring and `test_advisory_lock_ids.py` changed in
      **one** commit and the coordinator was notified **before**. **No id was reused.**
- [ ] `docs/01-spec/technical-specification.md` and `docs/02-database/db-retention.md` were
      **not edited** by any phase-07 block; the routed requests were handed to the coordinator
      with exact replacement text.
- [ ] `AdAdmin`'s field set, fieldsets and permission predicates are unchanged; `AdImageAdmin`
      changed only by BLOCK 11's action.
- [ ] `copy_ad` is **unchanged** — the aliasing is legal under the ownership model, and
      `test_copy_ad.py` passes **unchanged**. `AD-003` was not resurrected.
- [ ] `delete_adimage_files_on_delete` is still registered **by identity** and was not
      renamed; `AdImage.storage_keys()`'s signature and order are unchanged.
- [ ] `apps/moderation/admin_actions.py` is unchanged, or changed only in the reason/audit
      flow under the recorded Q07-5 answer — with **no** behaviour change to the actions.
- [ ] `media_gate` is **byte-identical** to before this plan apart from nothing: no filesystem
      check, no cache-header change, no application-level limiter.
- [ ] `/protected-media/` is unchanged; no new `limit_req_zone` exists.
- [ ] `ThumbnailService.QUALITY == 85` is unchanged; the EXIF/ICC strip is intact.
- [ ] `src/backend/conftest.py` is **unmodified**.
- [ ] Locale files were **appended** to, never regenerated wholesale; `ru` and `bs` are
      non-empty for every new or changed string.
- [ ] No alert, no notification and no new feature flag was introduced — phase 12 consumes the
      read surfaces.
- [ ] No migration was created, renumbered or edited.
- [ ] The audit tree shows no new modifications; **no other phase's plan file was edited**;
      this plan file is the only file created or modified.

### 8.5 Project conventions

- [ ] Every new constant is a named module-level constant, a `StrEnum` / `IntEnum` member, or
      a **Django setting** (BLOCK 7's budget) — never an inline literal or a dict of strings
      (project rule 10).
- [ ] No `print()`; `logger = logging.getLogger(__name__)` with lazy `%s` formatting.
- [ ] All comments, docstrings, log messages, error messages and docs are in **English**.
- [ ] Pydantic v2 appears only at a system boundary; none was added to a view, a service or a
      handler. `apps/media/schemas.py::SubmittedPhoto` is the media boundary DTO and was
      followed, not copied inward.
- [ ] Business logic lives in `services/`; no new logic was added to a view or a handler
      beyond the thin boundary change its block requires.
- [ ] Filesystem side effects happen only **after** commit via `transaction.on_commit()`, or
      under a **recorded** gate decision (BLOCK 1's Q07-3 option (b) is the only candidate).
- [ ] Every non-trivial behaviour change has a test that verifies **logic and component
      interaction** — not a variable's absence, not a log string, not a line count, not an
      introspected field count, and **not** a hard-coded quality number. (BLOCKS 4 and 10 add
      one property test and no behavioural test respectively; both are justified in place.)
- [ ] No task target is a line number; every target is a file plus a semantic symbol
      (class, method, module constant, attribute, function call, URL route name, command name,
      template block, model field).
- [ ] `uv run ruff check --fix src/` was run if imports were reordered (`ruff format` is
      **not** the project convention).
- [ ] Every new finding citation is cycle-scoped `07-MEDIA-0NN`; no bare `MEDIA-0NN` was
      written into a comment, a docstring or a commit message. No new `ME-003`-style
      prior-cycle id was introduced.

### 8.6 Deliverables

- [ ] The `07-MEDIA-003` → `03-DB-005` merge and its two corrections (§5.6) were **communicated
      to the coordinator** — the detector is phase 07's, and `DB-005` should not assert that
      detection is impossible.
- [ ] The `AD-003` retirement (§5.4) and the `AD-006`/`MEDIA-002` tie-breaker (§5.5) were
      **communicated**, so phase 05 does not ship the byte-copy fix or a competing half-fix.
- [ ] The four **reserved documentation locations** were routed with exact replacement text
      (Q07-12), and the two **newly identified** locations (`docker-deployment.md`, US-S5) were
      either claimed explicitly or handed over with a named owner (§6.1).
- [ ] The **coordinator** was notified **before** BLOCK 8's lock allocation, with phase 06
      BLOCK 15's allocation sequenced against it.
- [ ] **Phase 15** was notified **before** BLOCK 11's delete surface landed.
- [ ] Every one-way data effect (BLOCKS 1, 3, 4, 8, 11, 12) has a commit body stating that
      the affected data does not return on a revert.
- [ ] BLOCK 9's deployed-stack real-key smoke check is **recorded as done**, in the commit
      body, with the date — it is the one manual gate in the plan and it is not a test.
- [ ] The audit-pipeline corrections (`VAL-001`, `VAL-002`, `VAL-003`, `VAL-004`, `VAL-005`,
      `VAL-006`) are restated in the final report so none is re-derived next cycle.
- [ ] This plan file is updated to mark each block's completion, so the phase coordinator has a
      single status surface.
- [ ] No commit was made without an explicit user request, and **this Planner changed no file
      other than this plan**.
