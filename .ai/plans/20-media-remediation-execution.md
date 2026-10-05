# Phase 07 Media Remediation — Execution Plan

- Source plan: `.ai/plans/07-media-remediation.md` (rationale, gates, question records `Q07-1`…`Q07-14` live there — do not re-derive)
- Ground truth audit against HEAD. **Correction: the recorded SHA is stale — it is a moving target because other agents commit in parallel. Re-verify with `git log --oneline -1` at the start of each block.** SHAs observed during BLOCK 2b research: `b7ba213` (plan written) → `673dea9` → `dbb83ee` (latest read).
- Owner decisions: **Q07-6 = (b)** → BLOCK 12 (seller bot affordance) **DEFERRED, will not be built**. **Q07-12 = (a)** → `docs/ops/docker-deployment.md` + `docs/04-user-stories/seller-stories.md` **IN SCOPE** for BLOCK 10.
- BLOCK 2 is RETIRED (shipped `64a9de6`) but shipped **defective** → BLOCK 2b.
- **11 blocks** to execute. One Implementor at a time. One commit per block. No `git add -A`.

### Working-tree hazards re-verified at HEAD `b7ba213`
| Target | State | Consequence |
|---|---|---|
| `src/backend/config/settings/base.py` | **CLEAN** (audit said dirty) | BLOCK 7's settings hazard is reduced to append-only + re-read |
| `docs/01-spec/technical-specification.md` | **CLEAN** (audit said dirty) | BLOCK 10 still **routes** it — never edits |
| **`docs/ops/docker-deployment.md`** | **DIRTY +16/−16** (plan 18/19 account-state) | **NEW hazard.** BLOCK 10 edits a file with uncommitted work → append-only, re-read immediately, stop-and-report |
| `src/backend/locale/{ru,bs,en}/django.po` | **DIRTY** (+593/+418/+609) | BLOCK 11 i18n target → append-only, never regenerate |
| `apps/media/**`, `apps/ads/**`, `handlers/ad_create/` | **CLEAN** | All block targets are HEAD-relative |
| `apps/media/migrations/` | stale `0003_mediadeletionerror_uq_*.pyc` with no `.py` | BLOCK 8: confirm `makemigrations --check` clean first |
| Test DB | `mko-bazuna-test-db-1 Up (healthy)` | gates may run now |

---

## Block list and serial order

| # | Block | Finding | Depends on | Risk | Agents |
|---|---|---|---|---|---|
| 2b | Four-column reference check + reusable helper | `07-MEDIA-001` regression | 2 (shipped) | HIGH | Auditor, Researcher, Planner, Implementor, Validator |
| 1 | Scope photo dedup to target ad + reclaim | `07-MEDIA-002` | 2b | HIGH | all five |
| 3 | Atomic thumbnail writes + repair guard | `07-MEDIA-004` | 1 | HIGH | all five |
| 4 | Name stored-original JPEG quality | `07-MEDIA-011` | 3 | LOW | Implementor, Validator |
| 5 | Seed generator asserts only what it wrote | `07-MEDIA-008` | 3 | LOW-MED | Planner, Implementor, Validator |
| 6 | Dangling-row reconciliation + deletion counter | `07-MEDIA-012` | — (phase-03 gate LANDED) | HIGH | Auditor, Planner, Implementor, Validator |
| 7 | Staging byte budget + gauge | `07-MEDIA-007` | 6 | MED | Auditor, Planner, Implementor, Validator |
| 8 | Deletion-error reader + retention | `07-MEDIA-010` | — | MED | Auditor, Planner, Implementor, Validator |
| 9 | nginx script block + `/media/` rate limit | `07-MEDIA-006` | — | MED | Researcher, Planner, Implementor, Validator |
| 10 | Ownership rule + doc corrections | `07-MEDIA-009` | 2b (hard), 4, 5, 9 | MED | Auditor, Planner, Implementor, Validator |
| 11 | Moderator single-photo removal service + admin action | `07-MEDIA-005` | 2b (hard) | HIGH | all five |

### Dependency graph — re-derived for the drift

- **BLOCK 6 ↔ phase 03 (BLOCKS 6+8): GATE SATISFIED.** `aa0baf2` landed `_STAGING_TTL_SECONDS` justification + `touch_staging_photos`; `35441e0` replaced `move_staging_to_permanent` with `plan_staging_promotion` + `promote_media_files` in `on_commit`. The plan's BLOCK 1/4/6 external gate is **void**. BLOCK 6 no longer contends with phase 03.
- **BLOCK 6 → 7** is now a **file edge only** (`sweep_orphaned_media.py` supplies the bounded byte source), not an external gate.
- **BLOCK 2b → 11 is a NEW hard edge.** BLOCK 11 must "reuse, not re-implement" the reference check; no reusable helper exists today, so 2b must **extract** one.
- **BLOCK 2b → 10 is a NEW hard edge.** The ownership rule must describe the **fixed four-column** check, not the shipped one-column shape.
- **BLOCK 9 → 10** hard: `architecture-structure.md` may claim the nginx script block only after it ships.
- **BLOCKS 4 and 5 → 10** soft: the corrections reference the shipped quality constant and the seed behaviour.
- **BLOCK 3 → 5** hard (the stale-file guard BLOCK 5 reuses).
- Serial order is forced by a single Implementor; it is **`2b → 1 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11`**. BLOCK 2b leads because it is the only **live data-loss path**, has no dependency, and creates the helper BLOCK 11 requires.

---

## BLOCK 2b — Four-column reference check + reusable helper

**Findings owned.** `07-MEDIA-001` plan-compliance repair (not a new finding).
**Depends on.** BLOCK 2 (shipped `64a9de6`). **Risk.** HIGH — destroys live bytes.

**Required agents.**
- **Auditor** — enumerate *every* deviation of the shipped receiver from the plan's BLOCK 2 requirement (one-column filter, `pre_delete`-time evaluation, cascade leak), so the repair is complete rather than partial. **DONE** — all three deviations confirmed against Django 5.2.17 `Collector.delete()` source and `can_fast_delete`/`_has_signal_listeners` in-image; `pre_delete` is sent for every collected instance before `delete_batch`, and no fast-path bypass exists.
- **Researcher** — query shape for a four-column reference lookup (chained `Q(...)|Q(...)` vs four `__in` passes) and its PostgreSQL plan/row-count cost on the hottest indexed path. **DONE** — see "RESEARCHER DECISIONS" and "Query-shape measurement" below. The combined shape wins, and the earlier 18 ms/Seq-Scan claim is withdrawn with its root cause identified.
- **Planner** — extract the helper into a new module without breaking the module-level `delete_photo` binding or the by-identity registration assertion.
- **Implementor** — land the helper, delegate from the signal, add the four-column tests.
- **Validator** — confirm the helper is the **single owner** of the still-referenced predicate and that BLOCK 11 can consume it without re-implementing.

**What is wrong.** `delete_adimage_files_on_delete` in `apps/media/signals.py` computes `shared` from `AdImage.objects.filter(image__in=keys).exclude(pk=…).values_list("image", flat=True)` — the departing row's `storage_keys()` yields **all four** key columns, but `shared` only ever holds other rows' `image` values. A key shared via `thumbnail_small`/`thumbnail_medium`/`thumbnail_large` is therefore freed while another `AdImage` still references it. Live data-loss path: row A (`image=X, thumbnail_small=Y`) and row B on another ad (`image=Z, thumbnail_small=Y`); deleting A yields `keys=[X,Y]`, and because B's `image` is `Z` — neither `X` nor `Y` — `filter(image__in=[X, Y])` **never matches B at all**, so `shared=set()` and `orphaned=[X, Y]` → **`delete_photo(Y)` destroys B's thumbnail.** (The source plan's trace wrote `shared={Z}`; that holds only in the special case `Z ∈ keys_A`. In the general case the set is **empty**. The conclusion is unchanged; only the trace was wrong.) Second deviation: the check runs at `pre_delete` time, not after commit as the plan specified — `64a9de6` reached the right semantics via `.exclude(pk=instance.pk)`, but in a multi-row cascade Django sends `pre_delete` for all instances before any `DELETE`, so two sharing rows both skip → a **leak**. Third consequence: the check is inline in the signal body, so BLOCK 11's "reuse, do not re-implement" dependency is **unsatisfiable** — there is no reusable helper (`apps/media/services/` contains only `filesystem.py`, `hash_service.py`, `thumbnails.py`).

**RESEARCHER DECISIONS (BLOCK 2b) — binding on the Implementor.**
- **OC-1 → option (b): move the *filter* into the `on_commit` closure; capture keys by value at `pre_delete`.** Verified against Django 5.2.17 `Collector.delete()` source in-image: `pre_delete` is sent for every collected instance *before* `delete_batch`, and `setattr(instance, pk, None)` runs *after* the `atomic()` block — so at closure time `instance.pk` may already be `None`. The closure therefore **must not touch `instance`**, and the predicate is written **unexcluded** ("referenced by any row"), because the departing rows are gone. This eliminates the multi-row-cascade leak and narrows the concurrent-insert race to the window between one query and one `unlink`. `.exclude(pk=…)` is **removed**, not kept.
- **Query shape → a single combined `Q(...__in=...) | Q(...__in=...) | Q(...__in=...) | Q(...__in=...)` + `.exists()`**, matching `media_gate`'s existing idiom (rule 7). **The prior claim that this shape costs 18 ms (Seq Scan) and makes a catch-up sweep ~20× slower is an artefact and is withdrawn** — see "Query-shape measurement" below.
- **Helper** → new module `apps/media/services/references.py`, public surface of exactly **one function** `unreferenced_keys(keys: Sequence[str]) -> list[str]` plus the column constant. No class, no manager/queryset method on `AdImage`, no `is_referenced()`/`referenced_keys()` variants (rules 5, 15 — BLOCK 1 and BLOCK 11 both compose `unreferenced_keys`; a second predicate would break constraint 1). The helper owns the **predicate only**; the signal keeps ownership of key collection, `on_commit` registration and the FS error boundary (rule 3).
- **Column names → a module-level tuple constant** `KEY_COLUMNS: Final[tuple[str, ...]] = ("image", "thumbnail_small", "thumbnail_medium", "thumbnail_large")` in `references.py`, in `storage_keys()` order. **Not** a `StrEnum`: rule 10 targets magic values and dicts, and this is one immutable ordered tuple that replaces four duplicated literal lists; the two sibling modules (`sweep_orphaned_media._collect_referenced_keys`, `media_gate`'s `key_q`) already express the same four names as plain literals, so an enum would be the odd one out. **Not** derived from `AdImage._meta`: the model carries no marker distinguishing key columns from `telegram_file_id`/`sha256`, so pure derivation is impossible without a model change. **Not** modified from metadata either — it would be a model change, and constraint 7 forbids it. The drift risk against `storage_keys()` is handled by the **relational** test in required test 6, which is the deliverable — not the enum.

**Query-shape measurement (Researcher, re-run in-image; supersedes the Auditor's figures).** 20 000-row and 100 000-row scratch tables carrying the same four btree indexes, negative case (no row references the keys — the common orphaned-file case), driven through Django 5.2.17's own backend on PostgreSQL 18, interleaved A/B, median of ten trials of 200 executions:

| shape | 20 k rows | 100 k rows |
|---|---|---|
| shipped 1-column `filter(image__in=keys)` | 1.72 ms | — |
| **combined 4-column `Q(...__in=…)` + `.exists()`** | **1.33 ms** | **1.43 ms** |
| 4× chained single-column `.exists()` | 4.18 ms | 4.29 ms |

Raw trials do not overlap (combined max 1.49 ms, chained min 3.40 ms). **The combined shape is ~3× faster than the chained shape and shows no growth from 20 k to 100 k rows**, because it is one statement, one snapshot, one planning pass over a `BitmapOr` of the four existing indexes.

**Why the Auditor's 18 ms / Seq Scan does not reproduce — root cause identified.** `config/settings/base.py::_db_options()` sets **`"prepare_threshold": None`** (explicitly, for PgBouncer async safety, zone C5), and `config/settings/test.py` preserves it. Django 5.2's `DatabaseWrapper.get_connection_params()` forces `prepare_threshold=None` for psycopg3 even without the project setting. With `prepare_threshold=None`, psycopg **never prepares**, so every execution is an unnamed statement and PostgreSQL always builds a **custom plan** with the actual bind values in hand. A generic plan — which is what produces the untyped-parameter selectivity guess and the Seq Scan flip — **cannot occur in this project in any environment** (dev, test, prod, behind PgBouncer). A literal-SQL `EXPLAIN` on the same 20 k-row table also yields `BitmapOr`, not Seq Scan. All four indexes (`IX_adimages_image`, `IX_adimages_thumb_small`, `IX_adimages_thumb_medium`, `IX_adimages_thumb_large`) are present in `test_mko_bazuna` and fully usable → **no migration**. **Consequence: there is no ~20× catch-up-sweep regression to record; the combined shape is within noise of the shipped one-column query.** The commit body should state the measured per-row cost instead (~1.3–1.9 ms; 2 500 receiver invocations ≈ 3–5 s).

**Surface (semantic units only).**
- `apps/media/signals.py::delete_adimage_files_on_delete` — delegate to the helper; keep the module-level `delete_photo` binding; keep the bare global lookup **inside** the closure
- **new** `apps/media/services/references.py` — single-owner helper covering all four key columns
- `src/backend/apps/core/tests/test_ad_image_delete_signal.py` — **extend (real path — the plan's `apps/media/tests/…` path does not exist and pytest aborts the whole run on a bad path)**
- **new** `src/backend/apps/media/tests/test_references.py`
- **NOT touched:** `apps/media/services/__init__.py`. Its docstring scopes itself to "Media **filesystem** utilities"; `references.py` is a DB predicate, and the two sibling non-filesystem service modules (`hash_service.py`, `thumbnails.py`) are **not** re-exported — all 10 of their call sites import by full module path (`from apps.media.services.thumbnails import ThumbnailService`). Import `unreferenced_keys` the same way.

**Binding constraints.**
1. The helper is the **sole owner** of the still-referenced predicate. No second implementation.
2. `apps/media/signals.py` must keep binding `delete_photo` at **module level** — **16** monkeypatch call sites across **9** modules patch `"apps.media.signals.delete_photo"` **by string**. The closure body must therefore call `delete_photo(key)` as a **bare global lookup**; do not capture it into a local, a default arg, or `functools.partial`. Full list in "Keep green" below.
3. `delete_adimage_files_on_delete` must **not** be renamed and must stay registered on **`pre_delete`** — `test_media_config.py` asserts membership **by identity**. Moving the receiver to `post_delete` is the textbook-correct Django answer (`Collector.delete()` sends `post_delete` after that model's own `delete_batch`, so the departing rows are already gone) but it **fails that shipped green test** and is therefore out of scope. The `post_delete` alternative is recorded here so a later reader knows it was considered, not missed.
4. **The reference predicate is evaluated in the `on_commit` closure, after commit, unexcluded.** Consequences the Implementor must honour: (a) `keys` is captured **by value** into the closure (a `tuple`), never referenced through `instance`; (b) the closure **must not read `instance`** — `Collector.delete()` sets `instance.pk = None` after its `atomic()` block, and `.exclude(pk=None)` raises `ValueError`; (c) `.exclude(pk=instance.pk)` is **removed**. `pre_delete` keeps only: capture `keys`, early-return if empty, register `on_commit`.
5. `AdImage.storage_keys()`'s signature and return order are unchanged, and **`unreferenced_keys()` must return its input keys in the same order**. This is load-bearing, not cosmetic: `apps/users/tests/test_deletion.py` asserts `deleted_keys == result` (ordered list equality), and `test_ad_image_delete_signal.py` asserts `sorted(called_keys) == sorted(keys)`.
6. `delete_photo`'s never-raise contract is untouched. The existing `try/except Exception:  # noqa: BLE001` **inside the `on_commit` closure stays exactly as-is** — it is load-bearing: `delete_photo` calls `assert_storage_key_contained`, which **raises `ValueError`** on a traversal key, and this handler is the only thing absorbing it (`test_media_security.py::TestPhysicalDeletion::test_delete_photo_rejects_traversal_key` pins the `ValueError`). No *additional* `try/except` is added, and none is removed.
7. No migration, no new model, no new index, no backfill. The four indexes already exist.
8. **The multi-row-cascade leak is ELIMINATED, not documented.** Under the shipped shape two sharing rows in one `Collector` batch each see the other still present, both classify every key as shared, both skip `delete_photo`, and after commit **zero rows reference the key** — a silent leak. The chosen option removes the cause. The docstring must instead record the **residual** characteristic of the chosen shape: a shared key in a multi-row cascade is freed **twice** (both closures run post-commit, both find no referencing row), so the second `delete_photo` hits the terminal `FileNotFoundError` path and logs `WARNING "Photo not found (already deleted)"`. This is harmless — `delete_photo` returns before `_record_deletion_error`, so **no `MediaDeletionError` row and no BLOCK 8 escalation** — and it is the same shape the codebase already tolerates when `sweep_orphaned_media` races the signal. Do **not** add cross-callback de-duplication state to suppress it (rules 5, 15).
9. Comment must cite the shipped shape, not the plan's text.
10. **Corrected forbidden item (the source plan's item 4 is self-contradictory).** It reads "no new byte-freeing path routed through `apps.media.signals.delete_photo` … **or through `apps.media.services.filesystem.delete_photo`** when row deletion is the trigger" — but the shipped receiver does exactly that by design. Correct restatement: **no NEW entry point is created.** The existing `signals.delete_photo` → `filesystem.delete_photo` chain is retained as the single byte-freeing route, and BLOCK 11 must route through it rather than around it.

**Required tests** (logic + component interaction).
1. A key shared **only** through `thumbnail_small` survives the other row's deletion; the same for `thumbnail_medium` and `thumbnail_large`. *This is the defect's tripwire — it fails on the shipped code.*
2. The original `image`-shared case still survives (regression on `64a9de6`). `test_file_is_kept_while_another_adimage_references_the_key` already covers it and must stay green untouched — note it shares via `image` only, which is precisely why it passes on the defective one-column code.
3. Deleting the **last** referencing row frees the key (no over-retention). `test_unreferenced_file_is_still_deleted` is the negative guard for this and must stay green.
4. **Corrected (was unsatisfiable under `pre_delete`-time evaluation).** A cascade deleting **two rows that share a key in one transaction** frees the file. Assert: both rows are gone, the shared file **no longer exists** on disk, no exception escaped the `on_commit` callback, and `delete_photo` **was invoked at least once** for the shared key (`count(key) >= 1`). *Do not assert `count(key) == 1`* — the chosen option deliberately frees a shared key once per departing row, and pinning exactly-once here would contradict the very leak this test exists to prove is gone. `count >= 1` still fails on the shipped code, where the count is `0`, so it remains a valid tripwire.
5. The helper is exercised **through** the signal, not only in isolation — component interaction.
6. **Anti-drift (new, replaces a symbol-presence test).** Assert the column constant and `AdImage` agree as a *relationship*, not as a symbol: (a) every name in the constant resolves to a concrete field on `AdImage`; (b) a fully-populated `AdImage` instance satisfies `storage_keys() == list(<constant>)`. This fails loudly if a fifth key column is added to the model without updating the helper. Project rule 15 forbids a test that pins the mere presence of a symbol — this pins an equality between two shipped units, which is a different thing.
7. `media_gate` is unchanged and still performs **no filesystem check** — `test_media_security.py::TestMediaAccessControl::test_shared_seed_key_across_multiple_ads_returns_200` (empty `MEDIA_ROOT`, no file written, asserts 200 + `X-Accel-Redirect`) must stay green. It is in the keep-green list; do not "unify" `media_gate`'s predicate with the helper's (different job: authorise a request vs. test key liveness, and a single key vs. a key list).

**Keep green / do not edit.** All nine modules that patch `apps.media.signals.delete_photo` by string (the prior list named three — this tripwire was understated):
`src/backend/apps/core/tests/test_delete_photo_single_call.py` (×3) · `src/backend/apps/core/tests/test_sweep_delete.py` (×2) · `src/backend/apps/core/tests/test_sweep_consent.py` (×2) · `src/backend/apps/core/tests/test_sweep_purge_deleted.py` (×2) · `src/backend/apps/core/tests/test_sweep_drafts.py` (×1) · `src/backend/apps/core/tests/test_sweep_purge_failed.py` (×1) · `src/backend/apps/core/tests/test_sweep_purge_rejected.py` (×1) · `src/backend/apps/core/tests/test_ad_image_delete_signal.py` (×1) · `src/backend/apps/users/tests/test_deletion.py` (×3).
Also do not edit: `src/backend/apps/media/tests/test_media_config.py` · `src/backend/apps/ads/tests/test_media_security.py` · `src/backend/apps/ads/tests/test_copy_ad.py` · `src/backend/apps/ads/tests/test_ad_image_service.py` (BLOCK 1's file) · `src/backend/apps/media/tests/test_filesystem.py` · `apps/ads/models.py::AdImage.storage_keys` and its `Meta` · `copy_ad` · `apps/ads/views/listings.py::media_gate` · `src/backend/conftest.py`.
*Every existing fixture in those nine modules is single-ad / single-row with distinct keys, so all four keys are orphaned after commit and every one of them fires exactly one `delete_photo` call — the exactly-once assertions are unaffected by the move to post-commit evaluation. Verified by reading each of the 16 call sites.*

**Gate (exact).**
```
$dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/core/tests/test_ad_image_delete_signal.py src/backend/apps/media/tests/test_references.py src/backend/apps/media/tests/test_media_config.py src/backend/apps/ads/tests/test_copy_ad.py src/backend/apps/ads/tests/test_media_security.py src/backend/apps/core/tests/test_delete_photo_single_call.py src/backend/apps/core/tests/test_sweep_delete.py src/backend/apps/core/tests/test_sweep_consent.py src/backend/apps/core/tests/test_sweep_purge_deleted.py src/backend/apps/core/tests/test_sweep_drafts.py src/backend/apps/core/tests/test_sweep_purge_failed.py src/backend/apps/core/tests/test_sweep_purge_rejected.py src/backend/apps/users/tests/test_deletion.py --tb=short" test
.\Makefile.ps1 test
uv run ruff check src/
uv run basedpyright src/
```
*Path correction: the first path was `apps/media/tests/test_ad_image_delete_signal.py`, which does not exist. The real path is `apps/core/tests/test_ad_image_delete_signal.py` — the module lives under `core`, not `media`. pytest aborts the entire run on a bad path, so a stale gate silently skips every assertion below it.*

**Risk and rollback.** Highest-severity block in the plan — it is the only one that can destroy a live file. Revert = restore the shipped receiver, which reinstates the four-column defect. **No data is recoverable once a shared thumbnail is freed**, so the commit body must state that a revert does not restore deleted files. The fix only ever *narrows* deletion, so worst case is a **leak** (recoverable by re-running `sweep_orphaned_media`), never a loss.

**Performance.** No catch-up-sweep regression: the combined four-column predicate measures **~1.3–1.9 ms per deleted row** under this project's connection configuration, within noise of the shipped one-column query (~1.7 ms). 2 500 receiver invocations ≈ **3–5 s**, not the ~45 s previously estimated. The earlier figure was measured with prepared statements enabled, which this project disables on purpose (see "Query-shape measurement"). State the measured number and the `prepare_threshold=None` reason in the commit body.

**Residual risk (accepted).** A concurrent transaction can insert an `AdImage` referencing a key between the closure's reference query and its `unlink`. The window is one query plus one `os.remove` — down from the whole transaction under the shipped shape — but it is not closed, and closing it would need row-level locking on `ad_images`, which is a speculative redesign (rules 5, 7). The residual is *bounded by the same conservative bias the block already documents*: the alternative error direction destroys live bytes unrecoverably, whereas `sweep_orphaned_media` reclaims leaked files hourly.

### Execution plan

> **Template decision (recorded).** The primary `task_template.yaml` shape is used for the implementation task: the verification variant carries only `id / title / type / status / depends_on / verifies / verification_steps / pass_criteria / failure_action` and has no `description`, `goals`, `extra_context`, `files`, `changes` or `acceptance_criteria` — it cannot carry an Implementor brief. The verification variant shape is therefore emitted **in addition**, as the companion review task the block's agent list mandates ("all five" agents for BLOCK 2b).

```yaml
id: task_07-media-2b-implementation
title: "BLOCK 2b — Four-column reference check + reusable helper"
priority: high
status: pending
depends_on: []

source_reference: .ai\plans\20-media-remediation-execution.md
source_section: "BLOCK 2b — Four-column reference check + reusable helper"
source_blocks:
  - "BLOCK 2b — Four-column reference check + reusable helper"

description: >
  Repair the shipped `07-MEDIA-001` defect and extract the reusable reference
  predicate that BLOCK 1 and BLOCK 11 have a hard dependency on.

  Commit `64a9de6` shipped the "keep a media file whose `AdImage` key is still
  referenced by another ad" fix **inline** inside the `pre_delete` receiver
  `delete_adimage_files_on_delete` in `src/backend/apps/media/signals.py`, and
  covered **only the `image` column**. But `instance.storage_keys()` returns up
  to **four** columns (`image` NOT NULL; `thumbnail_small`, `thumbnail_medium`,
  `thumbnail_large` nullable), and the shipped `shared` set was built from
  other rows' `image` values only — so **a key shared only through a thumbnail
  column is freed while another `AdImage` still references it.**

  Corrected data-loss trace (the source plan's `shared={Z}` was wrong — in the
  general case `shared` is the **empty set**). Row A on ad 1:
  `storage_keys() == ['aaa.jpg', 'shared-small.jpg']`. Row B on a different ad:
  `image='zzz.jpg'`, `thumbnail_small='shared-small.jpg'`. The shipped
  `filter(image__in=['aaa.jpg', 'shared-small.jpg'])` never matches B's `image`
  (it is `zzz.jpg`), so `shared == set()`, `orphaned ==
  ['aaa.jpg', 'shared-small.jpg']`, and **`delete_photo('shared-small.jpg')
  destroys B's thumbnail while B still references it.**

  Second deviation: the check is evaluated at `pre_delete` time. Django's
  `Collector.delete()` sends `pre_delete` for **every** collected instance
  **before** any `delete_batch` (verified against Django 5.2.17 in-image), so two
  sharing rows deleted in one cascade each see the other still present, both
  skip, and after commit **zero rows reference the key** — a silent leak,
  reproduced twice in-container. Reachable in production: `copy_ad` gives one
  user two ads sharing all four keys; `consent_hard_delete` issues one
  `User.objects.filter(...).delete()`, i.e. one Collector batch, so both skip.

  Third problem: the check is inline, so BLOCK 11's "reuse, do not
  re-implement" dependency is **unsatisfiable** — `apps/media/services/` holds
  only `__init__.py`, `filesystem.py`, `hash_service.py` and `thumbnails.py`.

  Deliverable: a new `apps/media/services/references.py` owning the sole
  still-referenced predicate over **all four** key columns, plus a rewritten
  receiver that evaluates that predicate **inside** the `transaction.on_commit`
  closure — after commit, unexcluded. **No migration, no index, no model
  change, no new configuration.**

goals:
  - "Add `unreferenced_keys()` as the single owner of the still-referenced predicate, covering all four key columns in one combined `Q` statement."
  - "Evaluate the predicate in the `on_commit` closure, after commit and unexcluded, so a key shared through any column survives and the multi-row cascade leak is eliminated."
  - "Keep the by-string `delete_photo` monkeypatch contract (16 sites / 9 modules), the by-identity `pre_delete` registration, and the load-bearing `try/except Exception` error boundary intact."
  - "Cover the actual regression — a key shared only via `thumbnail_small` / `thumbnail_medium` / `thumbnail_large` — with tests that fail on the shipped code."
  - "Add a relational anti-drift test binding `KEY_COLUMNS` to `AdImage` so a fifth key column cannot be added silently."
  - "Land exactly one commit with explicit path staging; touch nothing outside the declared surface."

extra_context: >
  ## BINDING — Researcher decisions D1-D5 (SETTLED. Do not re-open, do not redesign.)

  **D1 — move the filter into the `on_commit` closure.** `pre_delete` does
  exactly three things: capture `keys` by value, early-return if empty, register
  the closure via `transaction.on_commit`. The closure computes the orphan set
  **inside itself** and calls `delete_photo(key)` as a **bare global lookup** —
  never captured into a local, a default argument, or `functools.partial`, or the
  16 string-patch sites break. The predicate is written **unexcluded** ("referenced
  by any row") because the departing rows are gone by closure time.
  `.exclude(pk=instance.pk)` is **removed**, and with it the current docstring's
  "do not simplify the exclusion away" warning — that warning existed only
  because the exclusion was load-bearing. **The closure must not touch
  `instance`** (its `pk` may already be `None`; `.exclude(pk=None)` raises
  `ValueError`). `post_delete` was considered and is recorded as *considered,
  not missed*: it is the textbook Django answer and also fixes the leak, but it
  fails the by-identity registration assertion in
  `apps/media/tests/test_media_config.py::test_pre_delete_signal_registered_for_adimage`,
  so it is out of scope.
  Accepted consequence: in a multi-row cascade a shared key is passed to
  `delete_photo` **once per departing row**. The second call hits the terminal
  `FileNotFoundError` path and returns **before** `_record_deletion_error`, so
  **no `MediaDeletionError` row and no BLOCK 8 escalation** — one WARN line only.

  **D2 — single combined four-column `Q(...)` statement.** The combined
  `Q(image__in=...) | Q(thumbnail_small__in=...) | Q(thumbnail_medium__in=...) |
  Q(thumbnail_large__in=...)` in **one** query, matching `media_gate`'s existing
  idiom in `apps/ads/views/listings.py` (rule 7). **The Auditor's performance
  case is withdrawn**: its 18 ms Seq-Scan flip requires a generic plan, but
  `config/settings/base.py::_db_options()` sets **`prepare_threshold: None`**
  (PgBouncer safety, zone C5) and `config/settings/test.py` preserves it, so
  psycopg never prepares and PostgreSQL always builds a custom plan with real
  bind values. Re-measured in-image, interleaved A/B, median of ten 200-exec
  trials, negative case: combined 4-column = **1.33 ms at 20 k rows, 1.43 ms at
  100 k**; 4x chained = 4.18 / 4.29 ms; shipped 1-column = 1.72 ms.
  Distributions do not overlap. **No migration, and no sweep regression to
  record** — per-row cost is approximately the shipped query. Rule 7 is
  satisfied *and* it is faster.

  **MANDATORY REFINEMENT TO D2 (for the Validator to confirm, not to re-litigate).**
  D2's measured shape terminates in `.exists()`. `unreferenced_keys()` is
  contracted to return the **per-key** orphan subset of a multi-key input, and
  `.exists()` collapses that to one boolean — `True` would mean "at least one
  key is referenced", which cannot say *which*. Implementing it literally would
  either return `[]` and leak every file, or return `keys` and delete every live
  file: both are the data-loss outcome this block exists to remove. Therefore
  keep D2's load-bearing content verbatim — one combined four-column `Q`, one
  statement, one snapshot, one planning pass, `BitmapOr` over the four existing
  btree indexes, no chained per-column passes — and terminate it in a per-key
  projection (`.values_list(*KEY_COLUMNS)` folded into a `set[str]` in Python).
  This is the same plan shape and the same measured cost class as D2; only the
  terminal projection differs, because the question is per-key. Do **not** add a
  single-key `.exists()` fast path: two code paths for one answer is
  overengineering (rule 5). Record this refinement in the commit body so the
  BLOCK 10 census and the Validator both see it.

  **D3 — new module `apps/media/services/references.py`; the public surface is
  ONE function `unreferenced_keys(keys: Sequence[str]) -> list[str]` plus the
  column constant.** No class. No manager or queryset method on `AdImage`. No
  `is_referenced()` / `referenced_keys()` variants — BLOCK 1 and BLOCK 11 both
  compose `unreferenced_keys`, and a second predicate would break "sole owner"
  immediately. The helper owns the **predicate only**; the signal keeps key
  collection, `on_commit` registration and the filesystem error boundary
  (rule 3). **`apps/media/services/__init__.py` must NOT be touched** — its
  docstring scopes it to "Media **filesystem** utilities"; the two sibling
  non-filesystem service modules (`hash_service.py`, `thumbnails.py`) are **not**
  re-exported and all 10 of their call sites import by full path
  (`from apps.media.services.thumbnails import ThumbnailService`). Import
  `unreferenced_keys` the same way:
  `from apps.media.services.references import unreferenced_keys`.
  **`unreferenced_keys()` must preserve input key order** — load-bearing, not
  cosmetic: `apps/users/tests/test_deletion.py` asserts ordered list equality
  (`deleted_keys == result`).
  The helper performs **no filesystem I/O** — it is a database predicate only.

  **D4 — columns as an ordered tuple, not a `StrEnum`.**
  `KEY_COLUMNS: Final[tuple[str, ...]] = ("image", "thumbnail_small",
  "thumbnail_medium", "thumbnail_large")`, in `storage_keys()` order. Rule 10
  targets magic values and dicts; this is one immutable ordered tuple replacing
  four duplicated literal lists, and the two sibling sites
  (`sweep_orphaned_media._collect_referenced_keys`, `media_gate`'s `key_q`)
  already express the same four names as plain literals — an enum would be the
  odd one out. Derivation from `AdImage._meta` is impossible without a model
  change (no marker distinguishes key columns from `telegram_file_id` /
  `sha256`). **Anti-drift is a relational test, not an enum** — see required
  test 6. Project rule 15 forbids only symbol-presence pins, and an equality
  between two shipped units is a different thing.
  Use `from typing import Final` — the established project convention.

  **D5 — residual risk, accepted.** A concurrent transaction can insert an
  `AdImage` referencing a key between the closure's query and its `unlink`. Down
  from the whole transaction under the shipped shape, but not closed; closing it
  needs row-level locking on `ad_images`, which is a speculative redesign. The
  bias stays conservative: the reverse error destroys live bytes unrecoverably,
  whereas `sweep_orphaned_media` reclaims leaked files hourly.

  ## HARD TRIPWIRES — the shipped receiver's contract that must survive verbatim
  1. `apps/media/signals.py` must keep binding `delete_photo` at **module
     level** — **16** monkeypatch sites across **9** modules patch
     `"apps.media.signals.delete_photo"` **by string**. The closure body must call
     `delete_photo(key)` as a **bare global lookup**; do not capture it into a
     local, a default argument, or `functools.partial`.
  2. `delete_adimage_files_on_delete` must **not** be renamed and must stay
     registered on **`pre_delete`**. `test_media_config.py` asserts membership
     **by identity**.
  3. The existing `try/except Exception:  # noqa: BLE001` + `logger.exception`
     around each `delete_photo` call **stays exactly as-is**. It is load-bearing:
     `delete_photo` calls `assert_storage_key_contained`, which **raises
     `ValueError`** on a traversal key and is not caught inside `delete_photo`.
     This handler is the only thing absorbing it —
     `apps/ads/tests/test_media_security.py::TestPhysicalDeletion::test_delete_photo_rejects_traversal_key`
     pins the `ValueError`. **No additional `try/except` is added, and none is
     removed.**
  4. `delete_photo` returns `None` on every path; 3 attempts; backoff 0.1 / 0.2 s;
     `FileNotFoundError` is terminal and returns **before**
     `_record_deletion_error`; last failure -> `logger.error` +
     `_record_deletion_error`; `_record_deletion_error` never raises. **This
     contract is untouched.**
  5. `AdImage.Meta` carries `ordering=["position"]`,
     `uq_ad_images_ad_position` on `(ad, position)`, four regex
     `CheckConstraint`s and **four non-unique btree indexes**
     `IX_adimages_image`, `IX_adimages_thumb_small`, `IX_adimages_thumb_medium`,
     `IX_adimages_thumb_large`. **No migration needed — and none may be added.**
  6. `copy_ad` aliases all four key columns verbatim and its docstring already
     documents dependence on "the signal's existence check". **Read-only for
     this block.**
  7. `media_gate` already expresses the four-column predicate as
     `Q(image=...) | Q(thumbnail_small=...) | Q(thumbnail_medium=...) | Q(thumbnail_large=...)`
     + `.exists()`. It performs **no filesystem check** and must stay that way:
     `apps/ads/tests/test_media_security.py::TestMediaAccessControl::test_shared_seed_key_across_multiple_ads_returns_200`
     points `MEDIA_ROOT` at an **empty** tmp dir, writes **no file**, and asserts
     200 + `X-Accel-Redirect`. **Do not "unify" `media_gate` with the helper** —
     different job (authorise a request vs. test key liveness; a single key vs. a
     key list).
  8. `Collector.delete()` sends `pre_delete` for **every** collected instance
     **before** any `delete_batch`, and `setattr(instance, pk, None)` runs
     **after** the `atomic()` block. `can_fast_delete` is False for `AdImage`
     (`_has_signal_listeners`), so there is no fast-path bypass. **This is the
     entire justification for D1** and must be stated in the module docstring.

  ## DO NOT TOUCH
  `apps/ads/models.py::AdImage` (including `storage_keys()`, `Meta`, the four
  indexes and every constraint) - `apps/ads/services/copy_service.py::copy_ad` -
  `apps/ads/views/listings.py::media_gate` -
  `apps/media/services/__init__.py` - `apps/media/services/filesystem.py`
  (including `delete_photo`) -
  `apps/media/management/commands/sweep_orphaned_media.py::_collect_referenced_keys` -
  `src/backend/conftest.py` - any file under `.ai/audit/**` - any other plan file -
  `docs/01-spec/technical-specification.md` - `docs/**/db-retention.md` -
  `src/backend/locale/*/django.po`.
  **No migration. No new model, field, constraint or index. No new setting, no
  `limit_req`, no new dependency. No locale change** — this block adds **no**
  user-visible string, so i18n extraction and the completeness gate are
  unaffected. Do not edit the `AdImage` model to make the column constant
  derivable.

  ## GATE (exact — run in this order)
  ```
  $dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'
  $dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/core/tests/test_ad_image_delete_signal.py src/backend/apps/media/tests/test_references.py src/backend/apps/media/tests/test_media_config.py src/backend/apps/ads/tests/test_copy_ad.py src/backend/apps/ads/tests/test_media_security.py src/backend/apps/ads/tests/test_adimage_storage_keys.py src/backend/apps/core/tests/test_delete_photo_single_call.py src/backend/apps/core/tests/test_sweep_delete.py src/backend/apps/core/tests/test_sweep_consent.py src/backend/apps/core/tests/test_sweep_purge_deleted.py src/backend/apps/core/tests/test_sweep_drafts.py src/backend/apps/core/tests/test_sweep_purge_failed.py src/backend/apps/core/tests/test_sweep_purge_rejected.py src/backend/apps/users/tests/test_deletion.py --tb=short" test
  .\Makefile.ps1 test
  uv run ruff check src/
  uv run basedpyright src/
  ```
  *Path correction — the first path is `apps/core/tests/test_ad_image_delete_signal.py`,
  **not** `apps/media/tests/...`: the module lives under `core`, not `media`.
  **A bad path in `PYTEST_OPTS` aborts the entire run**, so a stale gate silently
  skips every assertion after it. Every path above must exist before you run.*

  Test-environment notes (binding):
  - Tests run **only** through the `test` Compose service. Host Python has no
    Django; a local `uv run pytest` always fails.
  - `PYTEST_OPTS` **replaces** the entrypoint defaults
    (`--reuse-db --tb=short --durations=10 -n auto --maxprocesses=4 --dist loadgroup`),
    so this targeted run is single-process. That is expected.
  - `.\Makefile.ps1 test` is the real gate and skips the nightly `seed` marker.
    No migration means **no** `.\Makefile.ps1 test-recreate` is required.
  - **Concurrent-session hazard:** another agent is running tests against the
    same database right now. A gate run can return transient errors that do not
    reproduce on an identical re-run. **Re-run the identical command serially
    before reporting any red gate**, and only report red after it reproduces
    twice. Never "fix" a transient failure by editing a test.

  ## ROLLBACK
  Highest-severity block in the plan — it is the only one that can destroy a
  live file. Rollback = restore the shipped receiver, which reinstates the
  four-column defect. **A revert does not restore deleted files**: no shared
  thumbnail freed under the defective shape is recoverable. The fix only ever
  *narrows* deletion, so the worst case of the fix itself is a **leak**,
  recoverable by re-running `sweep_orphaned_media` — never a loss.

  ## COMMIT — ONE commit, explicit paths only
  Message: `fix(media): free a media key only when no AdImage row references it in any column`
  **Stage explicit paths. Never `git add -A`, never `git add .`, never
  `git add <directory>`.** The execution plan file, `staticfiles/` and other
  agents' untracked files must not be swept in. Files to stage, and nothing else:
  `src/backend/apps/media/services/references.py`,
  `src/backend/apps/media/signals.py`,
  `src/backend/apps/media/tests/test_references.py`,
  `src/backend/apps/core/tests/test_ad_image_delete_signal.py`.
  **Never** `git reset`, `git checkout`, `git restore`, `git stash`, `--amend`,
  or force-push — other agents work in parallel and changes you did not make are
  normal. If `git status` shows unrelated modified files
  (e.g. `apps/ads/admin.py`, `apps/core/utils/sanitize.py` from phase 06),
  leave them untouched and unstaged. Inspect `git status` and `git diff` before
  committing, and stage only the four paths above.

  The commit body **must** record all seven items below:
  1. The **corrected** data-loss trace, explicitly noting that the source plan's
     `shared={Z}` was wrong and that `shared` is the **empty set** in the general
     case.
  2. That the evaluation moved into the `transaction.on_commit` closure and
     **why** (Django sends `pre_delete` for every collected instance before any
     `DELETE`, so a `pre_delete`-time check sees siblings that are about to
     disappear and leaks the file), and that this eliminated the multi-row
     cascade leak.
  3. The deliberate **leak-over-data-loss bias** and its one irreducible residual
     (D5): a concurrent insert between the query and the `unlink`.
  4. The measured per-row cost — **~1.3-1.9 ms**, within noise of the shipped
     one-column query — and that **no migration and no index were added**, with
     the `prepare_threshold: None` reason (generic plans cannot occur in this
     project, so the withdrawn 18 ms Seq-Scan flip cannot occur either).
  5. That a **multi-row cascade may call `delete_photo` twice for a shared key**
     and that this logs one WARN and writes **no** `MediaDeletionError` row
     (`FileNotFoundError` returns before `_record_deletion_error`), so there is
     no BLOCK 8 escalation.
  6. The **deferred** note, **corrected by plan 23 Phase 3** (the deferral is
     retired; this entry is kept as the record of what was believed):
     `sweep_orphaned_media._collect_referenced_keys` and `media_gate`'s `key_q`
     still duplicate the four column names and do **not** yet consume
     `KEY_COLUMNS`. The framing "They perform *different* predicates" is **half
     right, and the half it gets wrong** is what made this look like a predicate
     problem instead of a vocabulary-ownership problem. These are **not** three
     semantically independent predicates: they are **one shared key-membership
     predicate, expressed three times, plus two independent site-specific
     semantics.** For a single non-empty key `k` the key-membership half is a
     **tautology across sites** — `Q(col__in=[k])` ≡ `Q(col=k)` for a singleton,
     and the falsy-candidate filter is inert because `media_gate`'s path converter
     requires a non-empty segment, so an empty key can never reach it. What
     genuinely differs is:

     | Independent semantic | Site | What it is |
     |---|---|---|
     | **Authorisation** | `media_gate` | An *orthogonal* predicate (`account_state_q("ad__user__")`, `ad__status=AdStatus.PUBLISHED`). Site 1 has no notion of it. |
     | **Census vs probe** | `sweep_orphaned_media` | A *whole-table* projection consumed as a filesystem set-difference (`on_disk - referenced`), not a per-candidate answer. |

     **⚠ The three must NOT be merged, and both failure modes are named:**
     folding the **authorisation** filter into a shared helper would make
     **unpublished/declined ads' images publicly readable**; replacing the
     **census** with a candidate-filtered query would **delete every file outside
     the candidate list**. Anyone revisiting this deferral must not re-attempt the
     merge. The original rationale — *"BLOCKS 7, 8 and 10 have file edges on those
     modules"* — is now **stale**: BLOCKS 7, 8 and 10 have all **shipped**.
     **⚠ Homonym warning:** "census" names two different things — a **code** census
     (enumerate the sites that enumerate key columns) and a **documentation** census
     (enumerate stale doc sentences). This deferral pointed at a *code* census, but
     BLOCK 10 was a *documentation* census; **BLOCK 10 did not discharge this**. The
     consolidation was delivered separately by plan 23 (commits `c514a8ca`,
     `3d908f3b`, `0a00f3a9`, `0efa6314`, `6de51f40`).
  7. The **mandatory D2 refinement** recorded in `extra_context` above:
     a per-key projection instead of `.exists()`, and why `.exists()` cannot
     answer a per-key question.

files:
  - path: src/backend/apps/media/services/references.py
    targets:
      - type: constant
        name: KEY_COLUMNS
      - type: function
        name: unreferenced_keys
    semantic_anchors:
      insert_after:
        type: import_statement
        value: "from apps.ads.models import AdImage"
      insert_before: {}

  - path: src/backend/apps/media/signals.py
    targets:
      - type: import_statement
        name: "from apps.media.services.references import unreferenced_keys"
      - type: function
        name: delete_adimage_files_on_delete
    semantic_anchors:
      insert_after:
        type: import_statement
        value: "from apps.media.services.filesystem import delete_photo"
      insert_before:
        type: constant
        value: logger

  - path: src/backend/apps/media/tests/test_references.py
    targets:
      - type: module
        name: test_references
    semantic_anchors:
      insert_after: {}
      insert_before: {}

  - path: src/backend/apps/core/tests/test_ad_image_delete_signal.py
    targets:
      - type: class
        name: TestAdImageDeleteSignal
    semantic_anchors:
      insert_after: {}
      insert_before: {}

changes:
  - action: add_code
    description: >
      Create `src/backend/apps/media/services/references.py`. A full **English**
      module docstring. It must state, in prose, (a) **why the evaluation
      happens in `on_commit`** — Django's `Collector.delete()` sends `pre_delete`
      for every collected instance before any `DELETE`, so a `pre_delete`-time
      check still sees sibling rows that are about to disappear, which both leaks
      the file in a multi-row cascade and leaves a concurrent-insert window
      spanning the whole transaction; and (b) **why the predicate is
      unexcluded** — by closure time the departing rows are already deleted, so
      "referenced by any row" is the correct question, and
      `.exclude(pk=instance.pk)` would raise `ValueError` because `Collector`
      sets `instance.pk = None` after its `atomic()` block. Also state that this
      module is a **database predicate only and performs no filesystem I/O**,
      that the signal retains ownership of key collection, `on_commit`
      registration and the filesystem error boundary, and that the column tuple
      is duplicated (not derived) because the model carries no marker
      distinguishing key columns from `telegram_file_id` / `sha256`.
      Then declare `KEY_COLUMNS` (`from typing import Final`; project
      convention) in `storage_keys()` order, and `unreferenced_keys`.

  - action: add_code
    description: >
      Implement `unreferenced_keys(keys: Sequence[str]) -> list[str]` in
      `references.py`. Behaviour: drop falsy keys from the candidate set; return
      `[]` immediately when the candidate set is empty (no query issued);
      otherwise issue **one** queryset using the single combined four-column
      `Q(...) | Q(...) | Q(...) | Q(...)` with `__in` lookups; fold the returned
      per-column values into a referenced-key set; return
      `[key for key in keys if key not in referenced]` so **input order is
      preserved** exactly. Docstring must state the preserved-order contract and
      the single-statement / BitmapOr rationale, and must not claim the function
      touches the filesystem.

  - action: modify_code
    description: >
      Rewrite the body of `delete_adimage_files_on_delete` in
      `src/backend/apps/media/signals.py` to the D1 shape, and add the
      `unreferenced_keys` import by full module path.
      **Kept byte-for-byte:** the function name, the
      `@receiver(pre_delete, sender=AdImage)` decorator, the module-level
      `from apps.media.services.filesystem import delete_photo` binding, the
      `(sender, instance, **kwargs)` signature, and the
      `try/except Exception:  # noqa: BLE001 - never let FS failure break the
      cascade` + `logger.exception("Failed to delete media file for key: %s",
      key)` pair around each `delete_photo(key)` call.
      **Removed:** `.exclude(pk=instance.pk)`, the inline `shared` set, the
      inline `orphaned` list, the `if not orphaned: return` early exit from
      `pre_delete`, and the docstring's "Do not 'simplify' the exclusion away"
      warning (its premise is gone).
      **New shape:** capture `keys = tuple(instance.storage_keys())` by value;
      return early only when `keys` is falsy; define the closure, which calls
      `unreferenced_keys(keys)` and then loops the result calling
      `delete_photo(key)` as a bare global lookup; register it with
      `transaction.on_commit(_cleanup)`. The closure **must not** reference
      `instance`, `sender` or `kwargs`.
      **Docstring:** replace it with an accurate one that explains key capture at
      `pre_delete` time, post-commit unexcluded evaluation, four-column coverage,
      and the shared-key double-call characteristic. Cite the **shipped shape**
      (one-column filter plus `pre_delete`-time evaluation), not the source
      plan's prose.

  - action: add_test
    description: >
      **New** `src/backend/apps/media/tests/test_references.py` — the
      predicate-level and relational tests, alongside `test_filesystem.py`,
      because `references.py` lives in `apps/media/services/`. Cover:
      (1) **anti-drift, relational** — every name in `KEY_COLUMNS` resolves to a
      concrete field on `AdImage` via `AdImage._meta.get_field(name)` (a typo
      raises `FieldDoesNotExist`), **and** a fully-populated `AdImage` satisfies
      `storage_keys() == list(KEY_COLUMNS)`. Together these fail loudly if a
      fifth key column is added to the model without updating the constant.
      Assert the **relationship**, never the mere presence of a symbol — rule 15
      forbids symbol-presence pins.
      (2) **order preservation** — a mixed input of referenced, unreferenced and
      blank keys returns the unreferenced ones in their original input order.
      (3) **per-column coverage** — parametrized over `KEY_COLUMNS`: a key
      referenced by another row through column X (including `thumbnail_small`,
      `thumbnail_medium`, `thumbnail_large`) is excluded from the result. This
      is the predicate-level statement of the defect.
      Keep the module small and typed per project convention; use
      `pytest.mark.django_db`. The `seller` / `category` / `city` fixtures and
      `create_test_ad(user, category, city, *, status=...)` come from
      `src/backend/conftest.py` (**unmodified**). Two `AdImage` rows require two
      distinct ads (unique constraint `uq_ad_images_ad_position`).

  - action: add_test
    description: >
      **Extend** `src/backend/apps/core/tests/test_ad_image_delete_signal.py` —
      the **real** path; the plan's `apps/media/tests/...` path does not exist and
      pytest aborts the whole run on a bad path. Keep all five existing tests
      **untouched and green**, in particular
      `test_file_is_kept_while_another_adimage_references_the_key` (which shares
      via `image` **only**, and therefore passes on the defective code — it is
      the `64a9de6` regression guard, not this block's tripwire) and
      `test_unreferenced_file_is_still_deleted` (the negative guard proving no
      over-retention). Add, inside the existing
      `@pytest.mark.django_db(transaction=True)` class and reusing its
      `isolated_media_root` fixture and `monkeypatch.setattr(settings,
      "MEDIA_ROOT", ...)` pattern:
      (4) **thumbnail-shared-key survival, parametrized over
      `thumbnail_small`, `thumbnail_medium`, `thumbnail_large`** — the actual
      regression being fixed; no existing test covers it. Row A on ad 1 with a
      distinct `image` plus the shared key in the parametrized column; row B on a
      second ad with its own distinct `image` plus the **same** shared key in the
      same column. Delete A inside `transaction.atomic()`. Assert the shared file
      still exists on disk and row B still references it. To assert the call
      boundary as well as the filesystem outcome, monkeypatch
      `"apps.media.signals.delete_photo"` with a recorder that appends the key
      **and then delegates** to the real `delete_photo`
      (`from apps.media.services.filesystem import delete_photo as real`,
      imported locally, matching the module's existing local-import style) —
      then assert the shared key is absent from the recorded calls. This pattern
      exercises the by-string patch contract and the filesystem effect in one
      test. **This test fails on the shipped code**, where `delete_photo` is
      called with the shared key and the file is destroyed.
      (5) **cascade-freed** — two ads, same owner, two `AdImage` rows sharing the
      `image` key and one thumbnail key; delete **both in one
      `transaction.atomic()`** (one Collector batch, e.g.
      `Ad.objects.filter(pk__in=[...]).delete()`). Assert: both rows are gone,
      both shared files are **gone** from disk, no exception escaped the
      `on_commit` callback, and `delete_photo` **was invoked at least once** for
      each shared key — `called_keys.count(shared_key) >= 1`. **Do NOT assert
      `== 1`**: the chosen option deliberately frees a shared key once per
      departing row, so pinning exactly-once here would contradict the very leak
      this test exists to prove is gone. `>= 1` still fails on the shipped code,
      where the count is `0`, so it remains a valid tripwire. Add a comment
      naming this reasoning at the assertion.

acceptance_criteria:
  - "New module `src/backend/apps/media/services/references.py` exists with an English module docstring that explains the `on_commit` evaluation, the unexcluded predicate, the no-filesystem-I/O scope, and why the column tuple is duplicated rather than derived."
  - "`KEY_COLUMNS` is `Final[tuple[str, ...]]` with exactly `(\"image\", \"thumbnail_small\", \"thumbnail_medium\", \"thumbnail_large\")` in `storage_keys()` order, declared with `from typing import Final`."
  - "`unreferenced_keys(keys: Sequence[str]) -> list[str]` is the module's only function; no class, no manager or queryset method, no `is_referenced()` / `referenced_keys()` variant exists anywhere in `src/`."
  - "The predicate is ONE combined four-column `Q(...) | Q(...) | Q(...) | Q(...)` query — no chained per-column `.exists()` passes, no `for column in KEY_COLUMNS: ... .filter(...)` loop."
  - "`unreferenced_keys` returns keys in **input order**; an empty/blank candidate set returns `[]` without issuing a query."
  - "`delete_adimage_files_on_delete` captures `keys` as a `tuple` at `pre_delete` time, returns early only when `keys` is falsy, and registers the closure via `transaction.on_commit`."
  - "`unreferenced_keys(keys)` is called INSIDE the closure; the closure body contains no reference to `instance`, `sender` or `kwargs`."
  - "`delete_photo(key)` inside the closure is a bare global lookup — no local alias, no default argument, no `functools.partial`, no lambda wrapper."
  - "`.exclude(pk=instance.pk)` and the 'do not simplify the exclusion away' docstring warning are both gone; the replacement docstring is accurate and cites the shipped one-column / `pre_delete`-time shape."
  - "The `try/except Exception:  # noqa: BLE001` + `logger.exception` boundary around each `delete_photo` call is present, unchanged, and is the only try/except in the closure."
  - "`apps/media/services/__init__.py` is byte-identical — `git diff --stat` shows it untouched."
  - "`AdImage.storage_keys()`, `AdImage.Meta` and the four indexes are unchanged; `git diff` on `src/backend/apps/ads/models.py` is empty; **no migration file was created**."
  - "`copy_ad`, `media_gate`, `delete_photo`, `services/filesystem.py`, `sweep_orphaned_media.py`, `src/backend/conftest.py`, every `.po` file and every file under `docs/` are unchanged."
  - "New `src/backend/apps/media/tests/test_references.py` contains the relational anti-drift test (every `KEY_COLUMNS` name resolves to a concrete `AdImage` field **and** a fully-populated row satisfies `storage_keys() == list(KEY_COLUMNS)`), the order-preservation test, and the per-column reference-coverage test. No test asserts mere symbol presence."
  - "`src/backend/apps/core/tests/test_ad_image_delete_signal.py` gains the parametrized thumbnail-shared-key survival test (all three thumbnail columns) and the cascade-freed test asserting `called_keys.count(shared_key) >= 1` — never `== 1`. All five pre-existing tests in that module are unmodified."
  - "New tests demonstrably fail against the pre-fix receiver: re-run the two new signal tests with the shipped body restored (in a scratch edit, then reverted) and confirm red. If you cannot demonstrate this, say so explicitly in the task report rather than claiming the tripwire works."
  - "Gate run 1 (the 13-path `PYTEST_OPTS` command above) passes with every path verified to exist first."
  - "`.\Makefile.ps1 test` passes."
  - "`uv run ruff check src/` and `uv run basedpyright src/` both pass with no new diagnostics."
  - "Any red gate was re-run **serially** on the identical command and reproduced twice before being reported. Transient first-run failures from the concurrent test session are not reported as red."
  - "Exactly **one** commit, message `fix(media): free a media key only when no AdImage row references it in any column`, staged by explicit path only — `git show --stat` lists exactly the four intended files and nothing else (no plan file, no `staticfiles/`, no other agent's files)."
  - "The commit body records all seven required items: the corrected data-loss trace (including that `shared` is empty in the general case); the move to `on_commit` and why; the leak-over-data-loss bias plus the D5 residual; the measured ~1.3-1.9 ms per-row cost with the `prepare_threshold: None` reason and the explicit 'no migration, no index'; the accepted double `delete_photo` call for a shared key in a multi-row cascade logging one WARN and writing no `MediaDeletionError`; the deferred note that `_collect_referenced_keys` and `key_q` do not yet consume `KEY_COLUMNS`; and the mandatory D2 per-key-projection refinement."
  - "`git status` shows no unrelated file staged, and no `git reset` / `git checkout` / `git restore` / `git stash` / `--amend` / force-push was used at any point."
```

```yaml
id: task_07-media-2b-verification
title: "Verify — BLOCK 2b Four-column reference check + reusable helper"
type: verification
status: pending

depends_on:
  - task_07-media-2b-implementation

verifies:
  - task_07-media-2b-implementation

verification_steps:
  - build: "uv run ruff check src/ && uv run basedpyright src/"
  - test: "$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS=\"src/backend/apps/core/tests/test_ad_image_delete_signal.py src/backend/apps/media/tests/test_references.py src/backend/apps/media/tests/test_media_config.py src/backend/apps/ads/tests/test_copy_ad.py src/backend/apps/ads/tests/test_media_security.py src/backend/apps/ads/tests/test_adimage_storage_keys.py src/backend/apps/core/tests/test_delete_photo_single_call.py src/backend/apps/core/tests/test_sweep_delete.py src/backend/apps/core/tests/test_sweep_consent.py src/backend/apps/core/tests/test_sweep_purge_deleted.py src/backend/apps/core/tests/test_sweep_drafts.py src/backend/apps/core/tests/test_sweep_purge_failed.py src/backend/apps/core/tests/test_sweep_purge_rejected.py src/backend/apps/users/tests/test_deletion.py --tb=short\" test   # then: .\\Makefile.ps1 test"
  - smoke_check: "git show --stat HEAD lists exactly four files (references.py, signals.py, test_references.py, test_ad_image_delete_signal.py); `git diff HEAD~1 --name-only` shows no plan file, no locale file, no docs file and no migration."

pass_criteria:
  - "build succeeds — ruff and basedpyright both clean"
  - "all tests pass — the targeted 13-path run and `.\Makefile.ps1 test` are green, re-run serially if a first run is red"
  - "smoke_check confirms one commit with exactly the four intended paths staged explicitly"
  - "`apps/media/services/references.py` is the SOLE owner of the still-referenced predicate — a repo-wide search finds no second implementation in `signals.py`, `copy_ad`, `media_gate`, `sweep_orphaned_media.py` or elsewhere, and no `is_referenced()` / `referenced_keys()` variant exists"
  - "the receiver keeps the module-level `delete_photo` binding, keeps the `pre_delete` registration by identity, and calls `delete_photo` as a bare global lookup inside the closure — so all 16 string-patch sites across the 9 named modules still intercept it"
  - "the `try/except Exception` boundary is present and is the only one in the closure; `test_delete_photo_rejects_traversal_key` is green, proving the `ValueError` from `assert_storage_key_contained` is still absorbed"
  - "`.exclude(pk=instance.pk)` and the stale exclusion warning are gone; the closure never references `instance`"
  - "the D2 refinement is honoured: one combined four-column `Q` in a single statement, no chained per-column `.exists()` passes, terminating in a per-key projection — and the commit body explains why `.exists()` cannot answer the per-key question"
  - "`KEY_COLUMNS` order equals `storage_keys()` order and the relational anti-drift test binds them; no symbol-presence pin is used as a substitute"
  - "no migration, no model change, no index, no new setting, no locale change; `services/__init__.py`, `AdImage`, `copy_ad`, `media_gate`, `filesystem.py` and `conftest.py` are byte-identical"
  - "BLOCK 11 can consume `unreferenced_keys` **without re-implementing** the predicate — confirm by reading the helper's signature and body, not by trusting the commit message"
  - "the commit body records all seven required items, including the corrected data-loss trace and the deferred `_collect_referenced_keys` / `key_q` note for the BLOCK 10 census"

failure_action: return task_07-media-2b-implementation to rework
```

**Keep green / do not edit — the 9 modules that patch `apps.media.signals.delete_photo` by string** (16 sites; the earlier plan named only three, understating the tripwire):
`src/backend/apps/core/tests/test_delete_photo_single_call.py` (x3) ·
`src/backend/apps/core/tests/test_ad_image_delete_signal.py` (x1, extend only) ·
`src/backend/apps/core/tests/test_sweep_delete.py` (x2) ·
`src/backend/apps/core/tests/test_sweep_consent.py` (x2) ·
`src/backend/apps/core/tests/test_sweep_purge_deleted.py` (x2) ·
`src/backend/apps/core/tests/test_sweep_drafts.py` (x1) ·
`src/backend/apps/core/tests/test_sweep_purge_failed.py` (x1) ·
`src/backend/apps/core/tests/test_sweep_purge_rejected.py` (x1) ·
`src/backend/apps/users/tests/test_deletion.py` (x3).
Also do not edit: `src/backend/apps/media/tests/test_media_config.py` ·
`src/backend/apps/ads/tests/test_media_security.py` ·
`src/backend/apps/ads/tests/test_copy_ad.py` ·
`src/backend/apps/ads/tests/test_ad_image_service.py` (BLOCK 1's file) ·
`src/backend/apps/ads/tests/test_adimage_storage_keys.py` (the `storage_keys` unit tests) ·
`src/backend/apps/media/tests/test_filesystem.py` ·
`apps/ads/models.py::AdImage` (including `storage_keys()` and `Meta`) · `copy_ad` ·
`apps/ads/views/listings.py::media_gate` · `src/backend/conftest.py`.
*Every existing fixture in those nine modules is single-ad / single-row with
distinct keys, so all four keys are orphaned after commit and every one of them
fires exactly one `delete_photo` call — the exactly-once assertions are
unaffected by the move to post-commit evaluation. Verified by reading each of the
16 call sites.*

---

## BLOCK 1 — Scope photo dedup to the target ad + reclaim

**Findings owned.** `07-MEDIA-002`.
**Depends on.** BLOCK 2b — **landed** (`59cc460`). Corrected: BLOCK 1 does **NOT** route the reclaim through `references.unreferenced_keys` (see D3 below). The remaining dependency is the *ownership* edge only — BLOCK 2b's helper stays the sole reference predicate, and BLOCK 1 introduces none. **Risk.** HIGH — `submit_ad` is the most contended file in the plan set.

**Required agents.**
- **Auditor** — **done.** Two plan premises falsified (C-2; "the skipped file" singular).
- **Researcher** — **done.** Five decisions below (D1–D5).
- **Planner** — design the two coordinated edits and the rollback test that encodes placement B.
- **Implementor** — land the re-scope + reclaim.
- **Validator** — independent review; the block writes into a HELD file.

**What is wrong.** `AdImageService.create_or_skip` in `apps/ads/services/images.py:75-78` filters `sha256=digest, ad__user_id=ad.user_id`, so a photo posted to a **second** ad by the **same seller** is skipped, the row is not created, and the freshly written files are orphaned on disk. `submit_ad` in `apps/ads/services/submission.py:358-368` discards `create_or_skip`'s return value, so nothing reclaims them.

**Corrected: the orphan is FOUR files, not one.** At the moment the duplicate is detected the bytes are at
`MEDIA_ROOT/staging/<uuid>.jpg` **plus** `staging/<uuid>-{small,medium,large}.jpg` — the bot's `save_photo._write` wrote the original, and `ThumbnailService.generate_thumbnails` derived the three thumbnails from the **staging** key (`stem, _ = os.path.splitext(original_key)` → `stem == "staging/<uuid>"`). All four are already in `permanent_keys`. Range is **1–4**: `submit_ad`'s bare `except Exception` (line 282-288) nulls all three thumbnail fields and appends nothing on a generation failure, leaving exactly one staged file. **Reclaiming only `STAGING_PREFIX + key` would delete the original and let `promote_media_files` promote the three orphans to permanent storage.** The key set is therefore the photo's own four fields — `photo.storage_key`, `photo.thumbnail_small`, `photo.thumbnail_medium`, `photo.thumbnail_large` — filtered for truthy. **Never hardcode `-small` / `-medium` / `-large` derivations**; that shape already exists as `AdImage.storage_keys()` (`apps/ads/models.py:747-761`).

**Q07-2 / Q07-3 are pre-answered by ground truth — not open.**
- **Q07-2 = option (a).** `_validate_image_count` (`ad.images.count()` vs `min_images`/`max_images`, default 1/5) already gates submission. A full dedup hit → `ON_MODERATION_FAILED`; a partial hit publishes with fewer photos. **No new gate.**
- **Q07-3** — at reclaim time the bytes are still at `staging/<key>` (promotion is post-commit). `delete_photo(<permanent key>)` is a **silent no-op** (`filesystem.py:250-258`: it joins `MEDIA_ROOT` with the key verbatim and hits the terminal `FileNotFoundError` path). The reclaim must prune the keys from `permanent_keys` **and** register a post-commit delete targeting `STAGING_PREFIX + key` for each.

---

## Researcher's decisions (D1–D5) — binding on the Implementor

### D1 — Reclaim architecture: **(b)** — a sibling of `promote_media_files` in `apps/media/services/filesystem.py`

| Option | Verdict |
|---|---|
| (a) inline in `submit_ad` | **Rejected.** Puts four field names, a `STAGING_PREFIX` composition, `delete_photo` calls and an error boundary into the most contended file in the plan set. Violates rules 3, 4. Also untestable without a DB. |
| **(b) `reclaim_staged_keys(keys)` in `filesystem.py`** | **CHOSEN.** `filesystem.py` already owns the staging lifecycle (`plan_staging_promotion`, `promote_media_files`), `STAGING_PREFIX`, `delete_photo`, and the never-propagate contract. The new function is ~12 lines beside two existing siblings that split the lifecycle into the same three phases. Testable **in isolation**: `tmp_path` + `override_settings(MEDIA_ROOT=…)`, no DB, no `sync_to_async`, no xdist, milliseconds — versus every reclaim assertion otherwise requiring `django_db(transaction=True)` in the async telegram_bot package. |
| (c) a method on `SubmittedPhoto` | **Partially adopted — as a pure field accessor only.** A DTO must never delete bytes: that would create a **second byte-freeing owner** and break global constraint 10 and BLOCK 11's "reuse, do not re-implement" edge. But `SubmittedPhoto.storage_keys()` (mirroring `AdImage.storage_keys()`, rule 7) is in-pattern for rule 11 — `SubmittedPhoto` **is** the media boundary DTO — and it must **not** import `STAGING_PREFIX`: `apps/media/schemas.py:8-13` declares the module a leaf specifically so `filesystem.py` can import it. A field-accessor method imports nothing, so the leaf claim stays true; extend the module docstring to say so. |
| (d) a new module | **Rejected.** 12 lines do not earn a module (rule 15 in the other direction), and it would split the staging lifecycle across files. |

**Consequence.** Two edits outside `submission.py`: a new `SubmittedPhoto.storage_keys()` in `apps/media/schemas.py`, and a new `reclaim_staged_keys(keys)` in `apps/media/services/filesystem.py` that composes `STAGING_PREFIX + key`, calls `delete_photo`, and wraps **each** key in `try/except Exception` + `logger.exception` — byte-for-byte the `apps/media/signals.py:62-67` `_cleanup` convention.

- **Leave `apps/media/services/__init__.py` untouched.** BLOCK 2b's `references.py` is not exported there and `submission.py` imports from full module paths (`submission.py:39-43`). Match the precedent; do not churn the surface.
- **Leave `plan_staging_promotion` untouched.** It keeps its own local `key_fields` tuple (`filesystem.py:85`). Unifying the two enumerations is a separate, non-blocking cleanup — recording it in the commit body is enough.

### D2 — Key set and deletion: the **caller** prunes with an in-place slice assignment; the pure helper produces the key set; the FS helper deletes

Three mechanisms, and why:

| Mechanism | Failure mode |
|---|---|
| **Rebind** — `permanent_keys = [k for k in permanent_keys if …]` | **Silent permanent orphan.** The promotion closure captures the **list object**, not its contents. Rebinding leaves the closure holding the original list, so all four files promote to permanent and the reclaim's `delete_photo("staging/<key>")` then hits the terminal `FileNotFoundError` and returns silently. Exactly placement C's failure. |
| **In-place slice assignment** — `permanent_keys[:] = […]` | **None.** `[:] =` mutates the existing list object; the identity captured by `lambda keys=permanent_keys` is unchanged, so the callback observes the pruned contents. |
| Prune inside `filesystem.py` (mutating a passed list) | **Implicit.** A function whose job is to mutate a caller-owned list is harder to read and harder to unit-test. `plan_staging_promotion` **returns** the list, so its consumer mutating it is symmetric. |

**Mechanism (chosen).** In the `create_or_skip` loop, collect the duplicate photos' staging keys via `SubmittedPhoto.storage_keys()`; then, still inside the transaction (in-memory only — constraint 2 is satisfied because no filesystem call happens there), prune with `permanent_keys[:] = [...]`; then register **one** `on_commit` reclaim immediately before the existing promotion hook.

**Which half is load-bearing — and the sharper reason.** The prune, because `permanent_keys` is the contract "these files will be moved to permanent storage on commit". The prune keeps it truthful **in both directions**: on a successful reclaim the file is deleted and never moved; **on a failed reclaim** (three `delete_photo` retries exhausted → `MediaDeletionError` recorded) the file is *not* moved either, so its bytes stay in `staging/` where `_STAGING_TTL_SECONDS` (2 h, `sweep_orphaned_media.py:55`) reclaims them. **Without the prune, a failed reclaim leaves the file staged, `promote_media_files` moves it to permanent, and it becomes a permanent orphan.** The ordering (reclaim before promotion) is defence-in-depth against a future prune regression — not free, but not the primary guarantee. Ship both; say which is which.

**Note for the Implementor:** with the prune complete, the promotion hook never sees a reclaimed key, so no `logger.exception` noise is produced. With an *incomplete* prune, `promote_media_files` would `os.replace` a missing source, raising `FileNotFoundError` — which `filesystem.py:124-134` already swallows via `except OSError` (it logs and continues). Harmless, but four ERROR lines per duplicate.

**Skip detection — keep `create_or_skip`'s return type `AdImage`.** The source plan proposed an explicit `created` result. That would break shipped assertions on the returned row in `src/backend/apps/media/tests/test_thumbnail_integration.py:149-172` (`.thumbnail_*` access) and four tests in `test_ad_image_service.py` (`.pk`, `.image`, `.sha256`). Instead, a skip is identified as `returned.image != photo.storage_key`, with this proof written into the code comment:

> A skip can only mean the predicate matched a *different* row. The offered key was minted fresh by `generate_storage_key()` (`uuid.uuid4()`) and `save_photo` retries on `FileExistsError` with a new key, so **no `AdImage` row can already carry it**. Hence `returned.image != photo.storage_key` is exactly "not created". It is also the same argument that makes `unreferenced_keys` unnecessary here — one proof, two uses.

The mis-classification direction is asymmetric and must stay impossible: reading a *created* row as a skip would delete bytes a live row references. The proof closes it; the comment must state it.

### D3 — `unreferenced_keys` is **not** composed. Correct the plan's Surface and constraint

| # | Why the predicate cannot change the outcome |
|---|---|
| 1 | The key comes from `generate_storage_key()` → `uuid.uuid4()`, regenerated on `FileExistsError`. **No row can carry it** — the row was never created. |
| 2 | Another ad cannot reference it. Under `(ad, sha256)` a cross-ad byte-identical upload creates **its own row with its own key**. The key is never shared — that is the point of BLOCK 1. |
| 3 | A `copy_ad` alias cannot reference it. `copy_ad` copies keys from **existing rows on a source ad**; it never calls `create_or_skip` and never writes a file. Provably unreachable. |
| 4 | Cost: one four-column `Q` + `.values_list` fold, measured **1.33–1.43 ms** per duplicate hit, to return its own input. |

BLOCK 2b's own module docstring (`references.py:33-35`) scopes the helper to *"the **predicate only** … the signal retains ownership of key collection, `on_commit` registration and the filesystem error boundary"*. BLOCK 1 has a **key-collection** problem, not a predicate problem. **Do not add a defensive query that cannot change the outcome.** Record the four-point reason in the commit body so BLOCK 11's "reuse, do not re-implement" edge stays intact — BLOCK 11 consumes `unreferenced_keys` for **row deletion**, which is a different trigger, and BLOCK 1 introduces no second predicate.

### D4 — The test that pins the defect: **rewrite in place (option a)**, in BLOCK 1's commit

`src/telegram_bot/tests/test_save_photo_integration.py::TestSubmitAdStagingMove::test_dedup_survives_deferred_promotion` asserts `AdImage.objects.filter(ad__user_id=user.id).count() == 1` across two ads of one seller. Under `(ad, sha256)` that becomes 2. Verified green at HEAD `59cc460`; red after the re-scope by direct consequence.

| Option | Verdict |
|---|---|
| (a) **rewrite** | **CHOSEN.** Re-point at the **same** ad; the test's stated purpose is preserved unchanged. |
| (b) delete | Rejected. Its purpose — pinning the explicit `sha256=` override under deferred promotion — is a live guard: remove `sha256=` from the `submit_ad` call site and `_compute_sha256(<permanent key>)` returns `""`, the `if digest:` guard silently disables dedup, and no test would see it. |
| (c) leave red | Not viable. |
| (d) split into two | Rejected **for this test**. The split that is needed is *rewrite this test to its stated purpose* + *add new tests for the new behaviour* — not two rewrites of one test. A second test re-running the same `submit_ad` path would double the slowest, most contention-prone assertions in the suite and grow the rewrite into new coverage, which the source plan's §6.3 forbids. |

**Two mechanical traps the Implementor must handle — a naive rewrite silently stops testing anything:**

1. **A second `submit_ad` on the same ad returns `INVALID_TRANSITION`.** `submit_ad` requires `DRAFT → ON_MODERATION`, and with `auto_moderate` patched the ad is left unresolved in `ON_MODERATION`, which is not in `ALLOWED_TRANSITIONS[ON_MODERATION]`. The test must **re-arm the ad to `DRAFT`** between submissions and say why in a comment. `create_draft_ad`'s second call (and its DRAFT-uniqueness comment) is deleted.
2. **Positions must differ** (`0` then `1`). `AdImage.Meta` declares `uq_ad_images_ad_position`; if the tripwire is broken and a second row is created at `position=0` the test would fail with `IntegrityError`, not the clean count assertion.

**The rewritten test must still assert, so its purpose is not lost:**
1. `first_image.sha256 != ""` — deferred promotion did not empty the digest. *(verbatim from today)*
2. `first_image.sha256 == expected_digest` — the digest is of the **staged** bytes. *(verbatim from today)*
3. Same-ad second submission with identical bytes → `AdImage.objects.filter(ad=<that ad>).count() == 1` **and** the returned row's `pk` equals the first row's `pk`.
4. **The tripwire must survive:** remove `sha256=` from the `submit_ad` call site and assertion 3 fails with `count == 2` (both digests become `""`, the guard skips dedup, the second row inserts at `position=1`). *Demonstrate this red before the fix is considered done.*

**Commit-body reason, as it should read:** *"C-2 in the source plan claimed no shipped test encoded cross-ad dedup. That is falsified: `test_dedup_survives_deferred_promotion` asserted `AdImage.objects.filter(ad__user_id=user.id).count() == 1` across two ads of one seller. The assertion is rewritten in place — not deleted, not split — and it is absent from the source plan's risk register because C-2 was wrong. The rewrite re-points the assertion at the same ad so the test's stated purpose, pinning the explicit `sha256=` override under deferred promotion, is preserved unchanged."*

**Which commit: BLOCK 1's.** BLOCK 10 is a documentation pass (`docs/**` plus docstrings); a code test rewrite there is out of scope and would leave BLOCK 1 red in the interim. It is also an explicit exception to BLOCK 1's keep-green rule for `test_save_photo_integration.py`, which is *not* on the keep-green list — so no exception is needed.

### D5 — Storage trade-off, and two risks the Auditor did not name

**D4 (storage).** The re-scope **increases** retained storage: a seller posting the same photo to N ads now holds N×4 referenced files instead of 1×4. But the bytes were **already being written** by `save_photo` — the old path leaked 4 files per occurrence to the hourly sweep. The re-scope converts **unreferenced bytes into referenced bytes**; it does not create new ones. The steady-state increase is that duplicates are retained under the ad's retention policy instead of reclaimed within the hour, bounded by `max_images` (default 5) per ad. This is the same ownership invariant `db-retention.md` and BLOCK 2b's shared-key logic already document.

**Commit body must record it as a conscious decision**: name the trade, name the bound (`max_images`), state plainly that the old path leaked rather than saved, and state that **seller-global upload dedup is explicitly a non-goal** — a different design with a different ownership model.

**Docstring rationale: correct it in BLOCK 1, not BLOCK 10.** `AdImageService`'s class docstring claims the dedup *"keeps storage and the `sha256` index lean"* — a rationale that now justifies the opposite of the shipped behaviour. It is in `images.py`, the file the block edits; rule 14 requires docs stay current. Three sentences go false and **all three** must be fixed in this commit:
- `images.py:20-26` — the class docstring (*"byte-identical to one they have already attached to **another ad**"* / *"keeps storage … lean"*).
- `images.py:47-71` — `create_or_skip`'s (*"Deduplication is scoped per seller"*, *"already attached to another ad"*).
- **`apps/ads/models.py:700-706` — `AdImage.save()`'s (*"duplicate uploads **by the same seller** are detected and logged"*).** Not in the Auditor's list. The plan's do-not-edit entry names `AdImage.storage_keys` and its `Meta`, **not** `save`, so this one sentence is in scope. **Recommend fixing it here**; if the Implementor judges the file too contended, route it to BLOCK 10 explicitly rather than dropping it.

The three `docs/**` sentences (`db-indexes.md:291`, `db-schema.md`, `technical-specification.md:149`) are **routed to BLOCK 10, never edited here**; cite the spec's *≥1-photo* sentence, which is already correct, and do not edit that file (phase 06 holds it).

**D5a — No race, and the real ordering hazard.** `run_and_clear_commit_hooks` (verified in-image, Django 5.2.17) does `_, func, robust = current_run_on_commit.pop(0)` — it **pops before calling** and calls **unguarded** when `robust=False`. Consequences, both verified:
- Callbacks run **FIFO in registration order**, synchronously, in the same thread immediately after commit. So `delete_photo` and `os.replace` are a **strictly ordered sequence, not a race**, for any key that reaches both hooks.
- **An unguarded raise kills every later callback.** If the reclaim callback raised, `promote_media_files` would never run and every surviving photo would strand in `staging/` for 2 h. `delete_photo`'s `assert_storage_key_contained` **raises `ValueError` outside its retry loop** (`filesystem.py:249`), and `staging/<uuid>.jpg` passes the key-format regex — so this is a latent trap, not a live bug. Hence the **per-key** `try/except Exception` inside the callback, exactly as `apps/media/signals.py:62-67` does. **`robust=True` is deliberately NOT used**: it is unused in this repository (0 call sites) and it does not give per-key isolation inside a loop — the first failing key would abort the rest.

**D5b — One `on_commit` registration per submission, not per photo.** Callback count is bounded at 4 by `max_images`, so this is not about cost; it is about (i) **ordering** — one registration placed immediately before the promotion hook guarantees *all* reclaims precede *all* promotions, and any future hook registered between per-photo callbacks would silently break that; and (ii) **failure isolation** — the per-key `try/except` lives inside the single callback's loop, so one bad key cannot abort the others. Per-photo registrations would multiply the surface for no gain.

**D5c — Additional findings the Auditor did not name.**
1. **`apps/media/tests/test_thumbnail_integration.py:149` calls `create_or_skip` directly.** This is the concrete reason the return type must stay `AdImage`. Add to the keep-green list.
2. **`07-NEW-02` — add `.order_by("pk")` to the duplicate lookup.** Under `(ad, sha256)` an ad *can* legitimately hold 2+ rows with the same digest: `copy_ad` copies `sha256` values from the source ad, and `SeedService` uses `bulk_create` (bypassing `create_or_skip`). Without an `ORDER BY` the returned winner is DB-order-dependent on shipped data. One token, on a line the block already rewrites. **Required, not optional.**
3. **The shared test DB is periodically poisoned** by a hung `mko-bazuna-test-test-run-*` container holding a session on `test_mko_bazuna` (63 `DuplicateDatabase` / "accessed by other users" errors, zero assertion failures). `run --rm` is leaving containers behind. A wall of *setup* errors is contention, not a defect — re-run serially before reporting red.

---

**Surface (semantic units only).**
- `apps/ads/services/images.py::AdImageService.create_or_skip` — re-scope the predicate to `(ad, sha256)`; add `.order_by("pk")`; two docstrings
- `apps/ads/services/submission.py::submit_ad` — detect the skip; collect staging keys; prune in place; register one reclaim `on_commit`
- `apps/media/services/filesystem.py` — **new** `reclaim_staged_keys(keys)`, sibling to `promote_media_files`
- `apps/media/schemas.py::SubmittedPhoto` — **new** pure `storage_keys()` (no imports); docstring note that the module stays a leaf
- `apps/ads/models.py::AdImage.save` — one docstring sentence
- `apps/media/services/filesystem.py::STAGING_PREFIX` / `delete_photo` / `plan_staging_promotion` / `promote_media_files` — **consumed, not changed**
- `apps/media/services/references.py` — **NOT** composed (D3). Must not change.
- `src/backend/apps/ads/tests/test_ad_image_service.py` — extend
- `src/telegram_bot/tests/test_save_photo_integration.py` — one test rewritten (D4)

**Binding constraints.**
1. The reclaim calls `apps.media.services.filesystem.delete_photo` directly — the same receiver `apps/media/signals.py::_cleanup` calls. **No NEW byte-freeing entry point is created.** (Do not route through `apps.media.signals.delete_photo`; that would perturb the exactly-once counters `test_delete_photo_single_call.py` pins.)
2. Filesystem side effects happen **only** via `transaction.on_commit`. The prune is in-memory and lives inside the transaction.
3. The reclaim targets `STAGING_PREFIX + key` for **each** of the photo's four key fields, filtered for truthy — **1–4 keys, never one**; pruning `permanent_keys` is mandatory (D2).
4. Register the reclaim `on_commit` **inside** the `transaction.atomic()` block, **after `auto_moderate`**, immediately before the existing promotion `on_commit`. **"After the `DoesNotExist` return" is not sufficient:** `INVALID_TRANSITION` is an early `return`, not an exception, so `Atomic.__exit__` **commits** and any hook registered before it **fires** — it would delete the skipped file, and the seller's re-confirm would then hit `plan_staging_promotion`'s `FileNotFoundError` → `PHOTO_UNAVAILABLE` → the handler clears `photos` and forces a full re-upload. That is a data-loss-on-retry regression created by an over-eager reclaim.
5. `submit_ad`'s transition table, `auto_moderate` call and return contract are unchanged. `create_or_skip`'s return type stays `AdImage`.
6. **CORRECTED — C-2 is FALSE.** `src/telegram_bot/tests/test_save_photo_integration.py::TestSubmitAdStagingMove::test_dedup_survives_deferred_promotion` **does** encode cross-ad dedup and **must** be rewritten (D4). The source plan's risk register missed it because C-2 was wrong. Every other test in `test_ad_image_service.py` stays green unchanged and is extended, not rewritten.
7. No migration. No new model, field, or index. **BLOCK 1 must NOT add `0002_alter_moderatoractionlog_reason.py`** — see the gate note below.
8. `copy_ad` is **read-only**; no byte copy; no unique constraint on `ad_images.image`.
9. Re-scoping to `(ad, sha256)` may leave an ad with duplicate-looking rows only if `sha256` is empty — the predicate is guarded by `if digest:` and stays guarded.
10. Commit body cites the ≥1-photo **spec sentence**, not a test.
11. `permanent_keys` is pruned with an **in-place slice assignment** (`permanent_keys[:] = …`), never rebound (D2).
12. Each `delete_photo` call is wrapped in `try/except Exception` + `logger.exception` (D5a). `robust=True` is not used.

**Required tests.**
1. **`reclaim_staged_keys` unit test** — new module or in `apps/media/tests/test_filesystem.py`. `tmp_path` + `override_settings(MEDIA_ROOT=…)`, **no DB**: four staged files deleted; a missing file is silent; **one key that makes `assert_storage_key_contained` raise `ValueError`** (e.g. `"staging/../x.jpg"` → `..` in parts) is swallowed, logged, and the **remaining keys are still deleted** — this is the per-key-isolation tripwire (D5a) and it is the cheapest, highest-value test in the block.
2. **Same-ad duplicate in ONE submission** (the primary reclaim fixture) — two byte-identical photos at `position` 0 and 1 in a single `submit_ad`: exactly **1** `AdImage` row, photo 0's four files promoted to permanent, **photo 1's four staged files absent from both `staging/` and permanent storage**. Gaps in `position` are legal (`AdImage.Meta`: *"Contiguity is intentionally NOT enforced… `copy_ad` preserves [0, 2, 5] verbatim"*). This is the most likely production trigger, needs no second `create_draft_ad`, and is simpler than the cross-ad case.
3. **Cross-ad, same seller** — two ads, identical bytes → **each ad has exactly one row with different keys**, and **zero orphan files** on disk. (Plan Required Test 1.)
4. **Cross-ad unit test in `test_ad_image_service.py`** — `create_or_skip(ad_a, key)` then `create_or_skip(ad_b, key)`, same seller, same bytes → two rows, different pks. The direct guard against over-scoping the fix; the shipped `test_returns_existing_duplicate_same_user` (same ad three times, asserts the INFO log contains `dedup`) stays green and unchanged.
5. **Rollback** — placement B. Use `auto_moderate(side_effect=RuntimeError(...))` (no sleeps) so the atomic rolls back: **both** photos' staged files are still present, `AdImage` count is 0, nothing was promoted. The docstring **names placement B and the option it rejects**. `test_submit_ad_rolls_back_when_auto_moderate_raises` (`test_submission.py:82`) is the authoritative fixture — its own docstring states *"In the real bot path there is no enclosing transaction, so the atomic block is a real commit boundary."*
6. **Ordering / `INVALID_TRANSITION`** — a submission whose transition is refused: the skipped photo's staged file **still exists** afterwards. This is the only test that pins constraint 4, and it fails if the reclaim is moved above `auto_moderate`. `test_submit_ad_invalid_transition_returns_outcome_not_raises` (`test_submission.py:442`) is the fixture.
7. **Moderation-failure reclaim** — `auto_moderate → False` still **commits**, so the hooks fire: the skipped file is reclaimed and `outcome is MODERATION_FAILED`. `test_submit_ad_moderation_failure_returns_moderation_failed` (`test_submission.py:402`) is the fixture.
8. **Rewrite of `test_dedup_survives_deferred_promotion`** per D4 — same ad, DRAFT re-arm, positions 0 then 1, assertions 1–4 listed there, **tripwire demonstrated red** before the fix.

**Every new test must call `create_test_ad(..., status=...)` explicitly.** `src/backend/apps/core/tests/test_ad_factory_contract.py` AST-walks **every** `.py` under `src/backend` and `src/telegram_bot` (except `conftest.py`) and fails on any `create_test_ad` / `create_test_ad_bulk` call that is not status-grounded. A bare `create_test_ad(seller, category, city)` in a new test **fails this whole-repository gate even though the test itself passes.**

**Keep green / do not edit.**
`src/backend/apps/ads/tests/test_ad_image_service.py` (extend only) · `src/backend/apps/ads/tests/test_media_security.py` · `src/backend/apps/core/tests/test_delete_photo_single_call.py` · `src/backend/apps/ads/tests/test_copy_ad.py` · `apps/moderation/services/auto_moderation.py` · `src/backend/conftest.py`.
*Additions, all verified unaffected:*
- `src/backend/apps/ads/tests/test_adimage_storage_keys.py` — **5 `pytest.mark.unit` tests, no DB**; the reclaim's key set mirrors `storage_keys()`, so keep them green as the anti-drift anchor for D1(c).
- `src/backend/apps/media/tests/test_thumbnail_integration.py` — calls `create_or_skip` **directly** at line 149; pins the return type stays `AdImage`.
- `src/backend/apps/ads/tests/test_submission.py` — the four named transaction/transition pins, plus `test_missing_staged_file_reports_a_recoverable_error` (line 139), which pins `payload.photos[0].storage_key == storage_key` — the `SubmittedPhoto` is **not** rewritten on the `FileNotFoundError` path.
- `src/backend/apps/media/tests/test_filesystem.py` — `TestPromoteMediaFiles` and `TestDeletePhoto` untouched.
- `src/backend/apps/media/tests/test_references.py` — BLOCK 2b's helper must not change; "does not compose" is the point.
- `src/backend/apps/core/tests/test_ad_factory_contract.py` — the whole-repository status-grounding gate.
- `src/backend/apps/core/tests/test_ad_image_delete_signal.py` — BLOCK 2b's signal tests.

**Gate (exact).**
```
$dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/telegram_bot/tests/test_save_photo_integration.py src/backend/apps/ads/tests/test_ad_image_service.py src/backend/apps/ads/tests/test_submission.py src/backend/apps/ads/tests/test_adimage_storage_keys.py src/backend/apps/media/tests/test_thumbnail_integration.py src/backend/apps/media/tests/test_filesystem.py src/backend/apps/media/tests/test_references.py src/backend/apps/core/tests/test_ad_image_delete_signal.py src/backend/apps/core/tests/test_delete_photo_single_call.py src/backend/apps/core/tests/test_ad_factory_contract.py src/backend/apps/ads/tests/test_media_security.py src/backend/apps/ads/tests/test_copy_ad.py --tb=short" test
.\Makefile.ps1 test
uv run ruff check src/
uv run basedpyright src/
```
**The gate as previously written could not reach `test_save_photo_integration.py` at all** — it named no path under `src/telegram_bot`, so the one test BLOCK 1 must rewrite was invisible to the targeted run. `PYTEST_OPTS` is word-split on spaces (unquoted in `docker/entrypoint-test.sh`), so pass bare paths only. Setting `PYTEST_OPTS` **replaces** the defaults, losing xdist parallelism and `--reuse-db`.

**Pre-existing red gate — NOT BLOCK 1's.** `test_migrations.py::test_makemigrations_check` is red from commit `b3fde27`, which changed `ModeratorActionLog.reason.help_text` without shipping `0002_alter_moderatoractionlog_reason.py`. **A plain `makemigrations --check` lies:** `config/settings/test.py` sets `MIGRATION_MODULES = DisableMigrations()`, so the check prints "No changes detected" regardless of reality — reproduce under `config.settings.test_migrations` to see it. BLOCK 1 adds no migration; **attribute the failure and prove the attribution** in the commit body.

**Risk and rollback.** Placement B is chosen from the four-way matrix: `on_commit`, registered before the promotion hook, with the prune. **One-way data effect: the reclaim deletes bytes, and a revert does not restore them.** Worst case of the re-scope is a **leak** (recoverable by `sweep_orphaned_media`), never a loss — with one exception the ordering constraint 4 removes: registering above `auto_moderate` would let `INVALID_TRANSITION`'s commit fire the reclaim and force a full re-upload. Rollback = stop shipping the re-scope; the predicate reverts and orphans return to the sweep. `submission.py` is HELD by phase 05 — re-read immediately before editing, stage explicitly by path, and **stop and report** rather than clobber. `apps/ads/admin.py` is **M** (comment-text only, another agent's) — **do not stage it.** This execution plan is **untracked** (`?? .ai/plans/20-media-remediation-execution.md`) — never swept in by a stray `git add`.

**Courtesy notification.** Phase 05's `AD-006` is this same predicate and phase 05 plans no competing half-fix; phase 05 must also retire `AD-003` (the byte-copy fix) — which BLOCK 1 makes permanently moot, because after the re-scope no key is ever shared between two ads.

### Planner task — BLOCK 1 implementation brief

> **Template decision (recorded).** BLOCK 1 is **HIGH** risk and writes into a file HELD by phase 05, so the primary `task_template.yaml` shape carries the Implementor brief and the **verification** variant is emitted **in addition**, as the companion review task the block's agent list mandates.

```yaml
id: task_07-media-1-implementation
title: "BLOCK 1 — Scope photo dedup to the target ad + reclaim the skipped upload"
priority: high
status: pending
depends_on: []

source_reference: .ai\plans\20-media-remediation-execution.md
source_section: "BLOCK 1 — Scope photo dedup to the target ad + reclaim"
source_blocks:
  - "BLOCK 1 — Scope photo dedup to the target ad + reclaim"

description: >
  Repair finding `07-MEDIA-002`. `AdImageService.create_or_skip` filters the
  duplicate lookup on `sha256=digest, ad__user_id=ad.user_id`, so a photo posted
  to a **second ad by the same seller** is skipped: no row is created and the
  freshly written files are orphaned on disk. `submit_ad` discards
  `create_or_skip`'s return value, so nothing reclaims them.

  Two coordinated edits, plus the reclamation they enable:

  1. **Re-scope the predicate** from `(sha256, seller)` to `(ad, sha256)`, with
     an explicit `.order_by("pk")`.
  2. **Reclaim the skipped photo's staged bytes** — as a **post-commit**
     `transaction.on_commit` delete, registered **after `auto_moderate`** and
     **immediately before** the existing `promote_media_files` registration,
     together with an **in-place slice prune** of `permanent_keys`.

  The orphan is **1-4 files, not one.** At the moment the duplicate is detected
  the bytes are `staging/<uuid>.jpg` plus up to three siblings
  (`staging/<uuid>-{small,medium,large}.jpg`), because
  `ThumbnailService.generate_thumbnails` derives `stem` from the **staging** key.
  All four are already in `permanent_keys` and none is referenced by any row.
  Range 1-4 because `submit_ad`'s bare `except Exception` in the thumbnail loop
  nulls all three thumbnail fields and appends nothing on a generation failure.
  Reclaiming only the original would promote the three orphans to permanent
  storage. **The key set is the photo's own four fields** — `storage_key`,
  `thumbnail_small`, `thumbnail_medium`, `thumbnail_large` — filtered for
  truthy. **Never derive** `-small`/`-medium`/`-large` by string surgery.

  Q07-2/Q07-3 are pre-answered: `_validate_image_count` already gates
  `min_images <= ad.images.count() <= max_images` (1/5). A full dedup hit yields
  `MODERATION_FAILED`; a partial hit publishes with fewer photos. **No new gate,
  no new rejection path.** Seller-global upload dedup is an explicit **non-goal**.

  Deliverable: the re-scope, a pure `SubmittedPhoto.storage_keys()` accessor, a
  sibling `reclaim_staged_keys` in `apps/media/services/filesystem.py`, the
  prune + single `on_commit` registration in `submit_ad`, three corrected
  docstrings, one in-place test rewrite, and six new tests. **No migration, no
  model field, no index, no configuration.**

goals:
  - "Re-scope the duplicate predicate to (ad, sha256) with an explicit .order_by(\"pk\"), so a seller may post the same photo to two ads and each ad gets its own row with its own key."
  - "Reclaim every staged file of a skipped photo (1-4 keys) through a post-commit on_commit hook registered after auto_moderate and immediately before the existing promote_media_files registration."
  - "Prune permanent_keys with an in-place slice assignment so the promotion closure never sees a reclaimed key — including when the reclaim itself fails."
  - "Keep create_or_skip's return type AdImage; identify a skip by comparing the returned row's .image against the offered key, with the uuid4 proof and the mis-classification asymmetry written into the code comment."
  - "Add SubmittedPhoto.storage_keys() as a pure field accessor that mirrors AdImage.storage_keys() and imports nothing, so apps/media/schemas.py remains a leaf and SubmittedPhoto never deletes bytes."
  - "Add filesystem.reclaim_staged_keys(keys) as a sibling of plan_staging_promotion and promote_media_files, composing STAGING_PREFIX + key and wrapping every delete_photo call in try/except Exception + logger.exception."
  - "Correct the three docstrings that go false (AdImageService class docstring, create_or_skip, AdImage.save) in this commit; route the three docs/** sentences to BLOCK 10."
  - "Rewrite test_dedup_survives_deferred_promotion in place so it pins its stated purpose instead of cross-ad dedup, and add coverage that fails on the shipped code."

extra_context: >
  ## BINDING — Researcher decisions D1-D5 (SETTLED. Do not re-open, do not
  ## redesign. This brief restates them so the Implementor needs no other input.)

  **D1 — architecture: a sibling `reclaim_staged_keys` in
  `apps/media/services/filesystem.py`.** That module already owns the staging
  lifecycle (`plan_staging_promotion`, `promote_media_files`), `STAGING_PREFIX`,
  `delete_photo` and the never-propagate contract. The new function is ~12 lines
  beside two siblings that already split the same lifecycle into the same phases,
  and it is testable **in isolation** with `tmp_path` +
  `override_settings(MEDIA_ROOT=...)` — no DB, milliseconds — versus every other
  reclaim assertion needing `django_db(transaction=True)` in the async bot
  package. **Rejected:** inline in `submit_ad` (four field names,
  `STAGING_PREFIX` composition, `delete_photo` calls and an error boundary in the
  most contended file in the plan set — rules 3/4, and untestable without a DB);
  a new module (12 lines do not earn one — rule 15); and a deleting method on
  `SubmittedPhoto` (**forbidden** — a second byte-freeing owner breaks global
  constraint 10 and BLOCK 11's edge). **Partially adopted:** `SubmittedPhoto` gets
  the field accessor only. A field accessor imports nothing, so `schemas.py`
  stays the leaf `filesystem.py` is allowed to import; extend that module
  docstring to say so.

  **D2 — the caller prunes; the accessor produces the key set; the FS helper
  deletes.** The promotion closure is `lambda keys=permanent_keys:
  promote_media_files(keys)` — the default argument captures the **list object**,
  so `permanent_keys[:] = [...]` preserves the identity the callback holds and
  the prune is visible to it. **Rebinding** (`permanent_keys = [...]`) is the
  **silent-orphan failure mode**: the closure keeps the original list, all four
  files promote, and the reclaim then no-ops on terminal `FileNotFoundError`.
  Pruning inside `filesystem.py` is implicit and harder to read;
  `plan_staging_promotion` *returns* the list, so its consumer mutating it is
  symmetric.
  **The prune is the load-bearing half**, and it keeps `permanent_keys` truthful
  *on reclaim failure*: if `delete_photo` exhausts its retries the file is not
  moved either, so its bytes stay in `staging/` for the TTL. Without the prune a
  failed reclaim promotes and orphans the file. The reclaim-before-promotion
  **ordering** is defence-in-depth against a future prune regression — ship both,
  and say which is which.
  **Return type stays `AdImage`.** An explicit `created` flag would break
  `apps/media/tests/test_thumbnail_integration.py` (`.thumbnail_*` access) and
  four tests in `test_ad_image_service.py` (`.pk`, `.image`, `.sha256`). Skip =
  `returned.image != photo.storage_key`. The proof — `generate_storage_key()`
  mints `uuid.uuid4()` and `save_photo` retries on `FileExistsError` with a new
  key, so **no row can already carry the offered key** — is also the same
  argument that disqualifies `unreferenced_keys`. One argument, two uses.
  Mis-classification is asymmetric: reading a *created* row as a skip would
  delete bytes a live row references. The closure must be commented.

  **D3 — `unreferenced_keys` (BLOCK 2b) is NOT composed.** Four-point reason, to
  be recorded in the commit body so BLOCK 11's "reuse, do not re-implement" edge
  stays intact: (1) the key is a fresh `uuid4()`, regenerated on
  `FileExistsError` — no row can carry it because the row was never created, so
  the predicate is trivially true; (2) under `(ad, sha256)` a cross-ad
  byte-identical upload creates **its own row with its own key**, so the key is
  never shared; (3) `copy_ad` copies keys from existing rows on a source ad, never
  calls `create_or_skip` and never writes a file — provably unreachable; (4) it
  costs a measured 1.33-1.43 ms per hit to return its own input. BLOCK 2b's
  docstring scopes the helper to *"the predicate only … the signal retains
  ownership of key collection, `on_commit` registration and the filesystem error
  boundary"*. **BLOCK 1 has a key-collection problem, not a predicate problem.**
  `apps/media/services/references.py` must not change.

  **D4 — rewrite `test_dedup_survives_deferred_promotion` in place, in this
  commit.** BLOCK 10 is a docs pass, so a code rewrite there is out of scope and
  would leave BLOCK 1 red. **Rejected:** deletion (its purpose — pinning the
  explicit `sha256=` override under deferred promotion — is a live guard: remove
  `sha256=` and `_compute_sha256(<permanent key>)` returns `""`, the `if digest:`
  guard silently disables dedup and nothing would see it); leaving it red;
  splitting into two tests (§6.3 forbids growing the rewrite into new coverage,
  and a second `submit_ad` doubles the slowest, most contention-prone
  assertions in the suite). **Two mechanical traps a naive rewrite hits:** (i) a
  second `submit_ad` on the **same** ad returns `INVALID_TRANSITION` — the test
  must **re-arm the ad to `DRAFT`** between submissions, with a comment saying
  why; (ii) **positions must differ** (`0` then `1`) or a broken tripwire yields
  `IntegrityError` from `uq_ad_images_ad_position` instead of the clean count
  assertion.

  **D5 — storage trade-off, and the two risks the Auditor did not name.**
  (a) The re-scope **increases** retained storage — N ads, N x 4 referenced files
  instead of 1 x 4 — but the bytes were **already being written**; the old path
  *leaked* 4 files per occurrence to the hourly sweep. The re-scope converts
  **unreferenced bytes into referenced bytes**; the steady-state increase is
  bounded by `max_images` (default 5). Record it as a conscious decision.
  (b) **No race, one registration per submission.** Django's
  `run_and_clear_commit_hooks` does `_, func, robust = current_run_on_commit.pop(0)`
  — it **pops before calling** and calls **unguarded** when `robust=False`. So
  callbacks are FIFO, synchronous and same-thread (a strictly ordered sequence,
  not a race) **but an unguarded raise kills every later callback** —
  `promote_media_files` would never run and every surviving photo would strand
  in `staging/` for 2 h. `delete_photo`'s `assert_storage_key_contained` raises
  `ValueError` **outside** its retry loop and `staging/<uuid>.jpg` passes the key
  regex, so this is latent. Hence the **per-key** `try/except Exception`, exactly
  as `apps/media/signals.py::_cleanup` does. **`robust=True` is deliberately NOT
  used** — 0 call sites in this repo, and it gives no per-key isolation inside a
  loop. **One** registration per submission, not per photo, for ordering (all
  reclaims precede all promotions) and failure isolation, not callback count.
  (c) **`.order_by("pk")` is REQUIRED (`07-NEW-02`)**: `copy_ad` copies `sha256`
  and `SeedService` uses `bulk_create`, so one ad can legitimately hold 2+ rows
  with the same digest; without an explicit order the winner is DB-order
  dependent on already-shipped data.

  ## Transaction shape — verified, and the reason for the exact hook placement

  All filesystem writes happen **before** `transaction.atomic()`; the
  transaction is DB-only plus hook registrations. `DRAFT_GONE` (`DoesNotExist`)
  and `INVALID_TRANSITION` (`ValueError`) are early **returns**, not exceptions,
  so `Atomic.__exit__` **commits normally** and any hook registered before them
  **fires**. Registering the reclaim above `auto_moderate` would delete the
  skipped file on an `INVALID_TRANSITION` commit, and the seller's re-confirm
  would then hit `plan_staging_promotion`'s `FileNotFoundError` ->
  `PHOTO_UNAVAILABLE` -> the handler clears `photos` and forces a full re-upload.
  **That is a data-loss-on-retry regression created by an over-eager reclaim.**
  By the time the `create_or_skip` loop runs, `plan_staging_promotion` has already
  rewritten `photo.storage_key` **in place** to its permanent form and
  `_permanent_thumbnail_key` has stripped the staging prefix from all three
  thumbnail fields — so `photo.storage_keys()` yields **permanent** keys, which
  is exactly the form `permanent_keys` holds and exactly what
  `reclaim_staged_keys` needs to compose `STAGING_PREFIX + key` from. No second
  key form exists at that point.

  **The web `ad_edit` path is unaffected:** it wraps `submit_ad` in an outer
  atomic but hardcodes `photos=[]`, so `create_or_skip` never runs there.

  ## Test constraints that will red-line this task

  - `apps/core/tests/test_ad_factory_contract.py` AST-walks **every** `.py` under
    `src/backend` and `src/telegram_bot` (except `conftest.py`) and fails on any
    `create_test_ad` / `create_test_ad_bulk` call that is not **status-grounded**
    (literal `status=`, or an enclosing function declaring a `status` parameter,
    or an enclosing dict literal with a `"status"` key). A bare
    `create_test_ad(seller, category, city)` in a new test **fails this
    whole-repository gate even though the test itself passes.**
  - `test_ad_image_service.py` asserts the dedup skip still logs at **INFO** with
    the substring `dedup` — do **not** move, reword or re-level that log line.
  - `test_missing_staged_file_reports_a_recoverable_error` pins
    `payload.photos[0].storage_key == storage_key` — the `SubmittedPhoto` is **not**
    rewritten on the `FileNotFoundError` path. Do not touch the pre-flight
    ordering (`plan_staging_promotion` stays first, before any I/O).
  - `apps/core/tests/test_delete_photo_single_call.py` is **unaffected**: it
    patches `signals.delete_photo` and sweep-command bindings and never invokes
    `submit_ad`. Reclaim calls **`filesystem.delete_photo`** directly — the same
    receiver `signals._cleanup` calls — so the exactly-once counters are
    undisturbed. Do **not** route through `apps.media.signals.delete_photo`.

  ## Environment

  - Docker test DB on 5433 (`.\Makefile.ps1 test-db` / `$dc up -d db` if down).
  - **Another agent is running tests concurrently right now.** A wall of
    *setup* errors (`DuplicateDatabase`, `ObjectInUse`, "accessed by other
    users") as opposed to assertion failures is **contention, not a defect** —
    re-run the identical command **serially** before reporting red.
  - `src/backend/apps/media/**` clean. `src/backend/apps/ads/admin.py` is **M**
    (comment text only, another agent's) and
    `src/backend/apps/users/services/deactivation.py` is **M** (another agent's) —
    **do not stage either**. `src/backend/conftest.py` clean.
  - `submission.py` is HELD by phase 05 — re-read it immediately before editing,
    stage explicitly by path, and **stop and report** rather than clobber.

files:

  - path: src/backend/apps/ads/services/images.py

    targets:
      - type: class
        name: AdImageService
      - type: method
        name: AdImageService.create_or_skip

    semantic_anchors:

      edit:
        - type: docstring
          value: AdImageService
        - type: docstring
          value: AdImageService.create_or_skip
        - type: queryset_filter
          value: AdImage.objects.filter

  - path: src/backend/apps/media/schemas.py

    targets:
      - type: class
        name: SubmittedPhoto

    semantic_anchors:

      insert_after:
        type: class_definition
        value: SubmittedPhoto

      edit:
        - type: module_docstring
          value: apps/media/schemas.py

  - path: src/backend/apps/media/services/filesystem.py

    targets:
      - type: function
        name: reclaim_staged_keys

    semantic_anchors:

      insert_after:
        type: function
        value: promote_media_files

      insert_before:
        type: function
        value: assert_storage_key_contained

  - path: src/backend/apps/ads/services/submission.py

    targets:
      - type: function
        name: submit_ad

    semantic_anchors:

      edit:
        - type: function_call
          value: AdImageService.create_or_skip
        - type: function_call
          value: auto_moderate
        - type: function_call
          value: transaction.on_commit

      insert_before:
        type: function_call
        value: promote_media_files

  - path: src/backend/apps/ads/models.py

    targets:
      - type: method
        name: AdImage.save

    semantic_anchors:

      edit:
        - type: docstring
          value: AdImage.save

  - path: src/backend/apps/media/tests/test_filesystem.py

    targets:
      - type: test_class
        name: TestReclaimStagedKeys

    semantic_anchors:

      insert_after:
        type: test_class
        value: TestPromoteMediaFiles

  - path: src/backend/apps/ads/tests/test_submission.py

    targets:
      - type: module
        name: test_submit_ad

    semantic_anchors:

      append_after:
        type: function
        value: test_submit_ad_invalid_transition_returns_outcome_not_raises

  - path: src/backend/apps/ads/tests/test_ad_image_service.py

    targets:
      - type: test_class
        name: TestAdImageServiceCreateOrSkip

    semantic_anchors:

      append_to:
        type: test_class
        value: TestAdImageServiceCreateOrSkip

  - path: src/telegram_bot/tests/test_save_photo_integration.py

    targets:
      - type: test_method
        name: TestSubmitAdStagingMove.test_dedup_survives_deferred_promotion

    semantic_anchors:

      replace_body:
        type: test_method
        value: TestSubmitAdStagingMove.test_dedup_survives_deferred_promotion

changes:

  - action: edit_predicate

    description: >
      **1. `AdImageService.create_or_skip` — re-scope the duplicate predicate and
      order the winner.**

      Replace `ad__user_id=ad.user_id` with the target ad itself and add an
      explicit `.order_by("pk")`. The `if digest:` guard stays exactly as it is
      (constraint 9 — an ad may still end up with duplicate-looking rows when
      `sha256` is empty, and the guard is what prevents the lookup).
      The **return type stays `AdImage`**; nothing about `AdImage.objects.create`
      changes. The `logger.info("AdImage dedup: ...")` call stays put, at INFO,
      with the substring `dedup` — `test_ad_image_service.py` pins it.

      **Why `.order_by("pk")` is required (`07-NEW-02`), not optional:**
      `copy_ad` copies `sha256` from the source ad's rows and `SeedService` uses
      `bulk_create`, both bypassing `create_or_skip`. Under `(ad, sha256)` one ad
      can therefore hold 2+ rows with the same digest on **already-shipped data**;
      without an explicit order the returned winner is DB-order dependent.

      **Skip detection lives in the caller, not here** (D2): a skip is
      `returned.image != photo.storage_key`.

    code_hint: |
      if digest:
          duplicate = (
              AdImage.objects.filter(ad=ad, sha256=digest)
              .order_by("pk")
              .first()
          )
          if duplicate is not None:
              logger.info(
                  "AdImage dedup: sha256=%s ad_id=%s user_id=%s "
                  "skipped (existing pk=%s)",
                  digest[:12],
                  ad.pk,
                  ad.user_id,
                  duplicate.pk,
              )
              return duplicate

  - action: edit_docstring

    description: >
      **2. `images.py` — both docstrings, which go false under the re-scope.**

      `AdImageService`'s class docstring currently claims a photo
      "byte-identical to one they have already attached to **another ad**" is
      returned instead of creating a duplicate, and that this "keeps storage and
      the `sha256` index lean". `create_or_skip`'s docstring says "Deduplication
      is scoped per seller" and "already attached to another ad". **Both are now
      the opposite of shipped behaviour** — a rationale that justifies the
      opposite of what the code does is worse than a stale sentence, so both are
      corrected **here, not in BLOCK 10** (the file is already being edited; rule
      14). Also correct the `ad:` argument's stated reason ("Must already be
      persisted so that `user_id` is available for the dedup query") — the
      predicate now uses the ad itself.

      State the new scope plainly: dedup is **per ad**; a byte-identical photo
      posted to a *different* ad by the *same* seller is a distinct upload and
      creates its own row with its own key. State that a skip is signalled to the
      caller by `returned.image != <offered key>`, and give the proof
      (`generate_storage_key()` mints `uuid.uuid4()`; `save_photo` retries on
      `FileExistsError` with a new key; therefore no row can already carry the
      offered key — so a differing `.image` is exactly "not created"). Note the
      asymmetry that keeps this safe: mis-reading a *created* row as a skip would
      delete bytes a live row references, which is why the caller must compare
      against the offered key and not against a truthiness test.

    code_hint: |
      class AdImageService:
          """Create ``AdImage`` rows with content-aware deduplication.

          Deduplication is scoped **per ad**: if the same ad already has an
          ``AdImage`` whose ``sha256`` matches the newly uploaded file, that
          existing row is returned instead of creating a duplicate, and the skip
          is logged.  The same photo attached to a *different* ad — including a
          different ad of the *same* seller — is a distinct upload and creates
          its own row with its own storage key; seller-global upload dedup is
          deliberately not a goal here.

          A skip is observable as ``returned.image != offered_key``: the offered
          key is minted fresh by ``generate_storage_key()`` (``uuid.uuid4()``)
          and retried on ``FileExistsError``, so no existing row can carry it.
          """

  - action: add_method

    description: >
      **3. `SubmittedPhoto.storage_keys()` — a pure field accessor, no imports.**

      Add one method to `SubmittedPhoto` in `apps/media/schemas.py` returning
      the photo's four key fields — `storage_key`, `thumbnail_small`,
      `thumbnail_medium`, `thumbnail_large` — in **exactly the order
      `AdImage.storage_keys()` uses**, each filtered for truthy. It mirrors
      `AdImage.storage_keys()` (rule 7); `SubmittedPhoto` *is* the media boundary
      DTO (rule 11).

      **It must not import `STAGING_PREFIX` and must not delete bytes.** It
      composes nothing, it composes nothing about paths — it only reads its own
      fields. `apps/media/schemas.py`'s module docstring declares the module a
      leaf precisely so `filesystem.py` can import it without a cycle; a field
      accessor imports nothing, so the leaf claim survives. **Extend that module
      docstring to say so**, so the next reader does not "fix" the apparent
      asymmetry between this accessor and `AdImage.storage_keys()` by importing
      the prefix here.

      Because `plan_staging_promotion` and `_permanent_thumbnail_key` have already
      rewritten these fields **in place** to permanent form by the time the caller
      reads them, the returned values are **permanent** keys — the same form
      `permanent_keys` holds and the same form `reclaim_staged_keys` prefixes
      with `STAGING_PREFIX`. The docstring must say that, so a reader does not
      add a `removeprefix` that would double-strip.

    code_hint: |
      def storage_keys(self) -> list[str]:
          """Return this photo's non-empty storage keys.

          Mirrors ``AdImage.storage_keys()`` — same four fields, same order —
          so a reclaim can be keyed off a submitted photo exactly as a deletion
          is keyed off a persisted row.

          Returns **permanent-form** keys: ``plan_staging_promotion`` and the
          thumbnail pipeline rewrite the staging prefix away in place before any
          caller reads these fields, so callers that need the staged path
          compose ``STAGING_PREFIX + key`` themselves.

          Pure field access — no I/O, no imports, no byte deletion.
          """
          return [
              key
              for key in (
                  self.storage_key,
                  self.thumbnail_small,
                  self.thumbnail_medium,
                  self.thumbnail_large,
              )
              if key
          ]

  - action: add_function

    description: >
      **4. `reclaim_staged_keys(keys)` — new sibling in
      `apps/media/services/filesystem.py`, between `promote_media_files` and
      `assert_storage_key_contained`.**

      Signature: `def reclaim_staged_keys(keys: Iterable[str]) -> None`. For each
      key, compose `STAGING_PREFIX + key` and call the module's own
      `delete_photo` with that staged key — **not** the permanent key, and **not**
      `apps.media.signals.delete_photo`. At reclaim time (post-commit, before
      promotion) the bytes are still at `staging/<key>`, so `delete_photo` on the
      permanent key is a silent no-op that reclaims nothing.

      **Per-key `try/except Exception` + `logger.exception`**, byte-for-byte the
      convention in `apps/media/signals.py::_cleanup`, with the same
      `# noqa: BLE001` reason. This is not defensive decoration: `delete_photo`
      calls `assert_storage_key_contained` **outside** its retry loop and it
      raises `ValueError`, while Django's `run_and_clear_commit_hooks` **pops**
      each callback before calling it **unguarded** when `robust=False` — so an
      unguarded raise would kill `promote_media_files` and strand every surviving
      photo in `staging/` for 2 h. `robust=True` is deliberately **not** used (0
      call sites in this repo, and it gives no per-key isolation inside a loop).

      **Never-propagate contract**, matching `promote_media_files`: the function
      returns `None` and raises nothing. **Full English docstring** stating: what
      it deletes, why the key is prefixed, the post-commit-only contract, the
      per-key isolation rationale, that a missing file is silent (it already is,
      via `delete_photo`'s terminal `FileNotFoundError` path), and that it must
      never be called inside a transaction.

      **Do not** unify `plan_staging_promotion`'s local `key_fields` tuple with
      this path — it keeps its own; that cleanup is separate and non-blocking.
      Record the deferral in the commit body.

    code_hint: |
      def reclaim_staged_keys(keys: Iterable[str]) -> None:
          """Delete the staged bytes of an upload that was never referenced.

          For each *key* (permanent form), removes ``staging/<key>`` through
          :func:`delete_photo` — the same receiver ``apps.media.signals._cleanup``
          calls, so ``delete_photo`` remains the sole byte-freeing entry point.

          Used when ``AdImageService.create_or_skip`` **skipped** an upload as a
          content duplicate: the row was not created, so no key references the
          files the submission pipeline already wrote, and they must not be
          promoted.  The caller has pruned those keys out of the list it hands
          to :func:`promote_media_files`.

          This runs **post-commit**, from a ``transaction.on_commit`` callback,
          and **never propagates**.  Each key is wrapped individually: Django
          pops ``on_commit`` callbacks before invoking them and calls unguarded
          callbacks without a ``try``, so a single unhandled failure would abort
          every later callback — including ``promote_media_files`` — and strand
          the ad's surviving photos in ``staging/`` until TTL reclamation.  One
          bad key must never cost the others.

          Args:
              keys: Permanent storage keys whose staged bytes are unreferenced
                  (as returned by ``SubmittedPhoto.storage_keys()``).

          Note:
              A missing staged file is silent: ``delete_photo`` treats
              ``FileNotFoundError`` as terminal and returns.
          """
          for key in keys:
              try:
                  delete_photo(f"{STAGING_PREFIX}{key}")
              except Exception:  # noqa: BLE001 - never let a reclaim abort promotion
                  logger.exception("Failed to reclaim staged file %s", key)

  - action: add_prune_and_hook

    description: >
      **5. `submit_ad` — capture the skip, prune in place, register ONE reclaim
      hook immediately before the existing promotion hook, after `auto_moderate`.**

      Inside the `create_or_skip` loop, bind the returned row. When
      `returned.image != photo.storage_key` the upload was **skipped**: append
      `photo.storage_keys()` to a local `reclaimed_keys` list. Put the
      skip-detection comment at this site (D2's proof plus the
      mis-classification asymmetry) — the proof is what makes both the
      classification and the decision not to query `unreferenced_keys` safe.

      Then, still inside the transaction and still inside the loop region,
      **prune with an in-place slice assignment**:

          permanent_keys[:] = [k for k in permanent_keys if k not in reclaimed]

      **Never rebind** `permanent_keys = [...]`. The promotion closure captures
      the **list object** through `lambda keys=permanent_keys`, so a rebind leaves
      the closure holding the original list: all four files promote to permanent,
      and the reclaim then no-ops on terminal `FileNotFoundError`. That is the
      silent-orphan failure mode. The prune also keeps `permanent_keys` truthful
      when the reclaim itself fails — a file whose `delete_photo` exhausted its
      retries is not moved either, so its bytes stay in `staging/` for the TTL
      instead of becoming a permanent orphan. **The prune is the load-bearing
      half; the ordering is defence in depth.**

      The prune and the key collection are pure in-memory list work, so the
      constraint "filesystem side effects only via `transaction.on_commit`"
      holds.

      **Then register exactly ONE `on_commit` reclaim — placed immediately before
      the existing `promote_media_files` registration and after
      `passed = auto_moderate(ad)`.** Registering earlier is a real regression,
      not a style choice: `DRAFT_GONE` and `INVALID_TRANSITION` are early
      **returns**, so `Atomic.__exit__` **commits**, and a hook registered above
      `auto_moderate` would fire and delete the skipped file — the seller's
      re-confirm would then hit `plan_staging_promotion`'s `FileNotFoundError` ->
      `PHOTO_UNAVAILABLE` -> the handler clears `photos` and forces a full
      re-upload. Guard the registration with `if reclaimed_keys:` so a submission
      with no duplicate registers no extra hook. Because Django runs callbacks
      FIFO in registration order, this placement guarantees **all** reclaims
      precede **all** promotions.

      Nothing else in `submit_ad` changes: the transition table, the
      `auto_moderate` call, the `if digest:`-equivalent guards, the
      `DRAFT_GONE` / `INVALID_TRANSITION` / `PHOTO_UNAVAILABLE` returns, the
      thumbnail loop, `staged_digests`, the pre-flight ordering, and the return
      contract are all untouched. `submission.py` is HELD by phase 05 — re-read
      it immediately before editing and **stop and report** rather than clobber.

    code_hint: |
      reclaimed_keys: list[str] = []
      for index, photo in enumerate(input.photos):
          created = AdImageService.create_or_skip(
              ad=ad,
              image=photo.storage_key,
              telegram_file_id=photo.telegram_file_id,
              position=photo.position,
              thumbnail_small=photo.thumbnail_small,
              thumbnail_medium=photo.thumbnail_medium,
              thumbnail_large=photo.thumbnail_large,
              sha256=staged_digests[index],
          )
          # A differing ``.image`` is exactly "not created": the offered key was
          # minted fresh by generate_storage_key() (uuid4, retried on
          # FileExistsError), so no row can already carry it.  Reading a
          # *created* row as a skip would delete bytes a live row references,
          # which is why this compares keys rather than testing truthiness.
          if created.image != photo.storage_key:
              reclaimed_keys.extend(photo.storage_keys())

      if reclaimed_keys:
          # In-place slice: the promotion closure holds THIS list object via
          # ``lambda keys=permanent_keys``, so a rebind would leave it holding
          # the unpruned list and promote the orphans.  Pruning also keeps the
          # contract truthful when a reclaim fails - the bytes then stay in
          # staging/ for TTL reclamation instead of becoming permanent orphans.
          reclaimed = set(reclaimed_keys)
          permanent_keys[:] = [k for k in permanent_keys if k not in reclaimed]

      # ... after ``passed = auto_moderate(ad)``:

          # Registered AFTER auto_moderate, immediately BEFORE promotion: the
          # DRAFT_GONE / INVALID_TRANSITION paths are early *returns*, so the
          # atomic block still commits and any hook registered above would fire -
          # deleting the skipped file out from under the seller's re-confirm.
          # One registration per submission, so every reclaim precedes every
          # promotion and a single failing key cannot abort the rest.
          if reclaimed_keys:
              transaction.on_commit(
                  lambda keys=list(reclaimed_keys): reclaim_staged_keys(keys)
              )
          transaction.on_commit(
              lambda keys=permanent_keys: promote_media_files(keys)
          )

  - action: edit_docstring

    description: >
      **6. `AdImage.save()`'s docstring — the third false sentence.**

      `apps/ads/models.py::AdImage.save`'s docstring says
      ``AdImageService.create_or_skip()`` is used "so that duplicate uploads **by
      the same seller** are detected and logged". That is false after the
      re-scope. The plan's do-not-edit entry names `storage_keys` and `Meta`,
      **not** `save`, so this one sentence is in scope. Change it to "duplicate
      uploads **to the same ad**".

      **Touch nothing else in `apps/ads/models.py`** — not `storage_keys()`, not
      `Meta` (including `uq_ad_images_ad_position` and the contiguity comment),
      not the indexes, no new field, no new constraint, **no migration**.

      **Route, do not edit, the three `docs/**` sentences** that also go false —
      they belong to BLOCK 10:
      `docs/02-database/db-indexes.md` (`IX_adimages_sha256`, commented "photo
      deduplication lookup"), `docs/02-database/db-schema.md` ("SHA-256 hex
      digest for per-user deduplication"), and
      `docs/01-spec/technical-specification.md` ("If the same user already has an
      image with the same hash, the duplicate is skipped (reuses existing
      storage)" — **phase 06 holds that file**). Cite the spec's sibling
      "cannot publish without >=1 photo" sentence in the commit body as the
      invariant that still holds; **never edit it**.

  - action: rewrite_test

    description: >
      **7. Rewrite `test_dedup_survives_deferred_promotion` IN PLACE, in this
      commit.** `src/telegram_bot/tests/test_save_photo_integration.py`,
      class `TestSubmitAdStagingMove`. It currently asserts
      `AdImage.objects.filter(ad__user_id=user.id).count() == 1` across **two ads
      of one seller** — it encodes cross-ad dedup and goes red by direct
      consequence of the re-scope. Verified green at HEAD `59cc460`; the source
      plan's C-2 claim that no shipped test does this is **falsified**.

      Re-point the assertion at the **same** ad, preserving the test's stated
      purpose — pinning the explicit `sha256=` override under deferred promotion.
      Keep the existing docstring's warning about removing `sha256=` and add the
      re-scope context.

      **Two mechanical traps — a naive rewrite silently stops testing anything:**

      1. **Re-arm the ad to `DRAFT` between submissions.** `submit_ad` requires
         `DRAFT -> ON_MODERATION`; with `auto_moderate` patched the ad is left in
         `ON_MODERATION`, which is not in `ALLOWED_TRANSITIONS[ON_MODERATION]`, so
         the second `submit_ad` returns `INVALID_TRANSITION`. Set the status back
         to `DRAFT` between the two submissions and **say why in a comment**.
         `create_draft_ad`'s second call — and its DRAFT-uniqueness comment — is
         deleted.
      2. **Positions must differ: `0` then `1`.** `AdImage.Meta` declares
         `uq_ad_images_ad_position`; if the tripwire is broken and the second row
         is attempted at `position=0` the test fails with `IntegrityError` instead
         of the clean count assertion.

      The rewritten test must still assert all four, so its purpose is not lost:
      (1) `first_image.sha256 != ""` — **verbatim from today**; (2)
      `first_image.sha256 == expected_digest` — **verbatim from today**; (3) the
      same-ad second submission with identical bytes yields
      `AdImage.objects.filter(ad=<that ad>).count() == 1` **and** the returned
      row's `pk` equals the first row's `pk` (the `pk` check is what proves it was
      a skip rather than a silently-not-created row); (4) **the tripwire must
      survive** — remove `sha256=` from the `submit_ad` call site and assertion 3
      must fail with `count == 2` (both digests become `""`, the `if digest:`
      guard skips dedup, and the second row inserts at `position=1`).
      **Demonstrate that red before the fix is considered done**, and record it
      in the commit body.

      Do not delete the test, do not leave it red, do not split it into two.

  - action: add_tests

    description: >
      **8. New tests — six, placed where each belongs. Every new
      `create_test_ad` / `create_test_ad_bulk` call MUST be status-grounded**
      (literal `status=`) or the whole-repository gate
      `apps/core/tests/test_ad_factory_contract.py` fails even though the test
      itself passes.

      **(a) No-DB unit test for `reclaim_staged_keys` —
      `src/backend/apps/media/tests/test_filesystem.py`, new class
      `TestReclaimStagedKeys` placed after `TestPromoteMediaFiles`.** The module
      is already `pytestmark = [pytest.mark.unit]`. Use `tmp_path` +
      `override_settings(MEDIA_ROOT=...)`; **no DB, no `django_db`, no
      `sync_to_async`, milliseconds.** Cover:
        - four permanent keys whose four staged files exist -> all four staged
          files removed and **no** permanent file created;
        - a key whose staged file is already gone -> silent, no exception;
        - **the per-key-isolation tripwire, the cheapest and highest-value test in
          the block:** a key that makes `assert_storage_key_contained` raise
          `ValueError` — pass `"../x.jpg"` as the *key* so the composed argument
          is `"staging/../x.jpg"`, whose parts contain `..` — is swallowed and
          logged, and **the remaining keys are still deleted**. Without the
          per-key `try/except` this fails; with it the loop continues.

      **(b) Intra-submission duplicate reclaim (the primary fixture) —
      `src/backend/apps/ads/tests/test_submission.py`, a new module-level test
      near the staging cases.** Two **byte-identical** photos at `position` 0 and 1
      inside **one** `submit_ad`: photo 0 creates the row, photo 1 is skipped,
      leaving a gap at `position=1`. Assert exactly **1** `AdImage` row, photo 0's
      files promoted to permanent, and **photo 1's staged files absent from both
      `staging/` and permanent storage** (this is the 4-file reclaim — assert on
      the thumbnails too, not just the original). Gaps are legal:
      `AdImage.Meta` states *"Contiguity is intentionally NOT enforced...
      `copy_ad` preserves [0, 2, 5] verbatim"*. This is the most likely
      production trigger and needs no second `create_draft_ad`.
      Build the input with real staged bytes under `override_settings(MEDIA_ROOT=tmp_path)`,
      modelled on `test_missing_staged_file_reports_a_recoverable_error`, which
      already constructs a photos-carrying `SubmitAdInput` inline in this module.

      **(c) Rollback (placement B) — `test_submission.py`.** With
      `auto_moderate(side_effect=RuntimeError(...))` (**no sleeps**) the atomic
      rolls back. Assert **both** photos' staged files are still present, the
      `AdImage` count is 0, and **promotion never ran** — no permanent file
      exists. The docstring **names placement B and the option it rejects**.
      `test_submit_ad_rolls_back_when_auto_moderate_raises` is the authoritative
      fixture: its own docstring states *"In the real bot path there is no
      enclosing transaction, so the atomic block is a real commit boundary."*

      **(d) Ordering / `INVALID_TRANSITION` — `test_submission.py`.** The **only**
      test that pins the hook placement: a submission whose transition is refused
      still has the skipped photo's staged file **present afterwards**.
      `create_test_ad(seller, category, city, status=AdStatus.REJECTED)` is the
      fixture — `test_submit_ad_invalid_transition_returns_outcome_not_raises`
      already proves a REJECTED ad returns `INVALID_TRANSITION` while the atomic
      **commits**. This test fails if the reclaim is moved above `auto_moderate`.

      **(e) Moderation-failure reclaim — `test_submission.py`.** `auto_moderate`
      returning `False` still **commits**, so the hooks fire: the skipped photo's
      staged files **are** reclaimed and `outcome is
      SubmitAdOutcome.MODERATION_FAILED`.
      `test_submit_ad_moderation_failure_returns_moderation_failed` is the
      fixture.

      **(f) Cross-ad over-scoping guard —
      `src/backend/apps/ads/tests/test_ad_image_service.py`, appended to
      `TestAdImageServiceCreateOrSkip`.** `create_or_skip(ad_a, key)` then
      `create_or_skip(ad_b, key)` for the **same seller** with identical bytes ->
      **two rows with different pks and different `image` keys**. This is the
      direct guard against over-scoping the fix. The shipped
      `test_returns_existing_duplicate_same_user` (same ad three times, asserting
      the INFO log contains `dedup`) stays **green and unchanged**.

      **No new test is needed for the `AdImage.save()` docstring** — it is a
      comment change with no behavioural surface, and
      `src/backend/apps/ads/tests/test_adimage_storage_keys.py` (5
      `pytest.mark.unit` tests, no DB; **note the filename has no underscore
      between `ad` and `image`**) already anchors the four-key enumeration that
      `SubmittedPhoto.storage_keys()` mirrors. Keep it green as the anti-drift
      anchor; do not edit it.

  - action: no_change

    description: >
      **9. DO NOT TOUCH — verified outside the declared surface.**

      - `filesystem.py::plan_staging_promotion` (including its local
        `key_fields` tuple), `promote_media_files`, `STAGING_PREFIX`,
        `STAGING_SUBDIR`, `KEY_FORMAT_REGEX`, `delete_photo`,
        `assert_storage_key_contained`, `_record_deletion_error`,
        `generate_storage_key`, and the module docstring's staging paragraph.
      - `apps/media/services/__init__.py` — BLOCK 2b's `references.py` is not
        exported there and `submission.py` imports from full module paths. Match
        the precedent; do not churn the surface.
      - `apps/media/services/references.py` — **not composed, must not change**
        (D3). `apps/media/signals.py` in full, including `_cleanup` and its
        `on_commit(_cleanup)` registration.
      - `apps/ads/views/listings.py::media_gate`; `apps/ads/services/copy_ad`
        (or wherever `copy_ad` lives) — read-only, no byte copy.
      - `AdImage.storage_keys()` and `AdImage.Meta` (including
        `uq_ad_images_ad_position` and the contiguity comment) and every index.
      - `ALLOWED_TRANSITIONS` and the state machine.
      - `src/backend/conftest.py`; `src/telegram_bot/tests/conftest.py`.
      - Any `.po` / `.mo`; no user-visible string changes, so no i18n work.
      - Everything under `docs/**` — including the three sentences routed to
        BLOCK 10, and the spec's already-correct "cannot publish without >=1
        photo" sentence.
      - `.ai/audit/**`, every other plan file, `.ai/context/**`, `.ai/tmp/**`.
      - `src/backend/apps/ads/admin.py` (**M** — another agent's comment text),
        `src/backend/apps/users/services/deactivation.py` (**M** — another
        agent's), `src/backend/apps/moderation/tests/test_moderation_reason_redaction.py`
        (**M** — another agent's),
        `src/backend/config/settings/tests/test_deploy_check_env_parity.py`
        (**M** — another agent's) and the untracked
        `src/backend/apps/moderation/migrations/0002_alter_moderatoractionlog_reason.py`
        (**??** — another agent's fix for the pre-existing `b3fde27` migration
        drift). Do not edit, do not stage, any of them.
      - `apps/moderation/services/auto_moderation.py`.
      - **No migration. In particular BLOCK 1 must NOT add
        `0002_alter_moderatoractionlog_reason.py`** — that drift belongs to
        commit `b3fde27` and another phase.

files_do_not_stage:
  - src/backend/apps/ads/admin.py
  - src/backend/apps/users/services/deactivation.py
  - src/backend/apps/moderation/tests/test_moderation_reason_redaction.py
  - src/backend/config/settings/tests/test_deploy_check_env_parity.py
  - src/backend/apps/moderation/migrations/0002_alter_moderatoractionlog_reason.py
  - .ai/plans/20-media-remediation-execution.md
  - staticfiles/
  - .ai/tmp/
  - .ai/context/
  - .ai/plans/17-ad-lifecycle-execution.md
  - .ai/plans/19-moderation-privilege-guard-execution.md

gate: |
  # 1. Targeted run — 12 paths, LED BY src/telegram_bot/tests/test_save_photo_integration.py
  $dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'
  $dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/telegram_bot/tests/test_save_photo_integration.py src/backend/apps/ads/tests/test_ad_image_service.py src/backend/apps/ads/tests/test_submission.py src/backend/apps/ads/tests/test_adimage_storage_keys.py src/backend/apps/media/tests/test_thumbnail_integration.py src/backend/apps/media/tests/test_filesystem.py src/backend/apps/media/tests/test_references.py src/backend/apps/media/tests/test_media_config.py src/backend/apps/core/tests/test_ad_image_delete_signal.py src/backend/apps/core/tests/test_delete_photo_single_call.py src/backend/apps/core/tests/test_ad_factory_contract.py src/backend/apps/ads/tests/test_media_security.py src/backend/apps/ads/tests/test_copy_ad.py --tb=short" test

  # 2. Fast full gate
  .\Makefile.ps1 test

  # 3. Lint and typecheck
  uv run ruff check src/
  uv run basedpyright src/

  # Serial re-run rule
  # Another agent is running tests concurrently. A wall of SETUP errors
  # (DuplicateDatabase, ObjectInUse, "accessed by other users") with zero
  # assertion failures is CONTENTION, not a defect. Re-run the IDENTICAL command
  # serially and reproduce twice before reporting red.

  # Migration-drift attribution
  # test_migrations.py::test_makemigrations_check was RED BEFORE BLOCK 1, from
  # commit b3fde27 (ModeratorActionLog.reason.help_text changed without
  # 0002_alter_moderatoractionlog_reason.py). config/settings/test.py sets
  # MIGRATION_MODULES = DisableMigrations(), so a plain `makemigrations --check`
  # prints "No changes detected" REGARDLESS of reality. To SEE the drift use
  # config.settings.test_migrations. BLOCK 1 adds no migration.
  #
  # CONCURRENCY: at plan-writing time another agent's UNTRACKED
  # src/backend/apps/moderation/migrations/0002_alter_moderatoractionlog_reason.py
  # is already in the working tree, so the drift may be fixed mid-block. Re-READ
  # the gate result instead of asserting it: if it is still red, attribute it to
  # b3fde27 and prove the attribution in the commit body; if another agent's
  # migration has already landed it, record that instead. Either way DO NOT STAGE
  # that file — it is not BLOCK 1's.

keep_green_do_not_edit:
  # The 12 gate paths above, plus, by name:
  - "src/backend/apps/ads/tests/test_ad_image_service.py — EXTEND ONLY; the existing test_returns_existing_duplicate_same_user (same ad three times) and its INFO-level 'dedup' log assertion are unchanged."
  - "src/backend/apps/media/tests/test_media_config.py — config defaults; untouched."
  - "src/backend/apps/ads/tests/test_copy_ad.py — reads AdImage.storage_keys(); untouched."
  - "src/backend/apps/media/tests/test_references.py — BLOCK 2b's unreferenced_keys must not change; 'BLOCK 1 does not compose it' is the point."
  - "src/backend/apps/core/tests/test_ad_image_delete_signal.py — BLOCK 2b's signal tests; untouched."
  - "src/backend/apps/core/tests/test_delete_photo_single_call.py — UNAFFECTED by construction: it patches signals.delete_photo and sweep-command bindings and never invokes submit_ad."
  - "src/backend/apps/core/tests/test_ad_factory_contract.py — the whole-repository status-grounding gate; untouched but MUST pass."
  - "src/backend/apps/ads/tests/test_adimage_storage_keys.py — 5 pytest.mark.unit tests, no DB; the anti-drift anchor for the four-key enumeration. NOTE the filename has no underscore between 'ad' and 'image'."
  - "src/backend/apps/media/tests/test_thumbnail_integration.py — calls create_or_skip DIRECTLY; pins that the return type stays AdImage (.thumbnail_* access)."
  - "src/backend/apps/ads/tests/test_submission.py — the four named transaction/transition pins stay green unchanged; only ADD new tests (additive optional parameter on the shared input helper is acceptable, but no existing call site may change)."
  - "src/backend/apps/media/tests/test_filesystem.py — TestPromoteMediaFiles and TestDeletePhoto untouched; the new class is additive."
  - "src/backend/apps/ads/tests/test_media_security.py, src/backend/apps/ads/tests/test_copy_ad.py, src/backend/apps/media/tests/test_media_config.py, src/backend/apps/media/tests/test_references.py, src/backend/apps/core/tests/test_ad_image_delete_signal.py — untouched."
  - "src/backend/conftest.py; apps/moderation/services/auto_moderation.py; apps/media/signals.py; apps/media/services/__init__.py; apps/media/services/references.py."

commit:
  message: "fix(ads): scope photo dedup to the target ad and reclaim skipped uploads"
  staging: |
    Stage by EXPLICIT PATH ONLY. Never `git add -A`, never `git add .`, never
    `git add <dir>`. Untracked noise that a stray `git add` would sweep in:
    .ai/plans/20-media-remediation-execution.md (this execution plan, untracked),
    staticfiles/, .ai/tmp/, .ai/context/19-moderation-privilege-guard-code-context.md,
    .ai/plans/17-ad-lifecycle-execution.md, .ai/plans/19-moderation-privilege-guard-execution.md,
    src/backend/apps/moderation/migrations/0002_alter_moderatoractionlog_reason.py
    (another agent's fix for the pre-existing b3fde27 migration drift).
    Plus the other agents' MODIFIED files that must never be staged:
    src/backend/apps/ads/admin.py,
    src/backend/apps/users/services/deactivation.py,
    src/backend/apps/moderation/tests/test_moderation_reason_redaction.py,
    src/backend/config/settings/tests/test_deploy_check_env_parity.py.
    One commit. No `git reset` / `git checkout` / `git restore` / `git stash` /
    `--amend` / force-push at any point.
  body_must_record: |
    Fourteen items, all of them load-bearing for a later block or a reviewer:

    C-1  Predicate re-scope from (sha256, seller) to (sha256, ad); finding
         07-MEDIA-002; seller-global upload dedup is an explicit NON-GOAL.
    C-2  .order_by("pk") is REQUIRED (07-NEW-02): copy_ad copies sha256 and
         SeedService bulk_creates, so one ad can hold 2+ same-digest rows on
         shipped data and the winner would otherwise be DB-order dependent.
    C-3  Return type stays AdImage; skip == returned.image != photo.storage_key.
         The proof — generate_storage_key() mints uuid4 and save_photo retries
         on FileExistsError, so no row can carry the offered key — is ONE
         argument used TWICE: it justifies the classification AND the decision
         not to query unreferenced_keys. Mis-classification is asymmetric
         (reading a created row as a skip deletes live bytes), so the call site
         is commented.
    C-4  The FOUR-POINT reason unreferenced_keys is not composed: (1) the key is
         a fresh uuid4 no row can carry; (2) under (ad, sha256) a cross-ad
         byte-identical upload creates its own row with its own key, so the key
         is never shared; (3) copy_ad copies keys from existing rows on a source
         ad, never calls create_or_skip and never writes a file —
         provably unreachable; (4) it costs a measured 1.33-1.43 ms per hit to
         return its own input. BLOCK 2b's helper stays the SOLE reference
         predicate so BLOCK 11 consumes it without re-implementing.
    C-5  The orphan is 1-4 FILES, not one: the thumbnail loop's bare
         `except Exception` nulls all three thumbnail fields and appends nothing,
         leaving exactly one staged file. The key set is the photo's own four
         fields via the new pure SubmittedPhoto.storage_keys(); -small/-medium/
         -large are never derived by string surgery.
    C-6  SubmittedPhoto is a field accessor only and never deletes bytes — a
         second byte-freeing owner would break global constraint 10 and BLOCK
         11's edge. It imports nothing, so apps/media/schemas.py stays the leaf
         filesystem.py is allowed to import; the module docstring says so.
    C-7  reclaim_staged_keys is a sibling of plan_staging_promotion and
         promote_media_files, not a new module (12 lines do not earn one). Each
         key is wrapped in try/except Exception + logger.exception because
         delete_photo's assert_storage_key_contained raises ValueError OUTSIDE
         its retry loop and Django's run_and_clear_commit_hooks POPS callbacks
         before calling them unguarded when robust=False — an unguarded raise
         kills every later callback, promote_media_files included, stranding
         every surviving photo in staging/ for 2 h. robust=True is deliberately
         NOT used: 0 call sites in this repo and no per-key isolation in a loop.
    C-8  Placement B chosen from the four-way matrix. (A) inside atomic() is
         UNSAFE — it converts a retryable OperationalError 55P03 into a lost
         upload. (B) on_commit before promotion is correct: on rollback neither
         hook runs and the staged files remain for the existing 2 h TTL, already
         pinned by test_submit_ad_rollback_leaves_files_in_staging. (C) after
         promotion is wrong — a permanent orphan. (D) B + prune is equivalent to
         B, which PROVES THE PRUNE IS THE LOAD-BEARING HALF. The
         reclaim-before-promotion ORDERING is defence in depth against a future
         prune regression, not the primary guarantee.
    C-9  The registration sits AFTER auto_moderate and IMMEDIATELY BEFORE the
         promotion registration. "After the DoesNotExist return" is not
         sufficient: INVALID_TRANSITION is an early RETURN, not an exception, so
         Atomic.__exit__ COMMITS and any hook registered before it FIRES — it
         would delete the skipped file, the seller's re-confirm would then hit
         plan_staging_promotion's FileNotFoundError -> PHOTO_UNAVAILABLE -> the
         handler clears photos and forces a full re-upload. That is a
         data-loss-on-retry regression created by an over-eager reclaim.
    C-10 permanent_keys is pruned with an IN-PLACE slice assignment, never
         rebound: the promotion closure holds the LIST OBJECT via
         `lambda keys=permanent_keys`. Rebinding is the silent-orphan failure
         mode — all four files promote and the reclaim then no-ops on terminal
         FileNotFoundError. The prune also keeps permanent_keys truthful when
         the reclaim FAILS: delete_photo exhausting its retries means the file is
         not moved either, so its bytes stay in staging/ for TTL reclamation.
    C-11 ONE on_commit registration per submission, not per photo — for
         ordering (all reclaims precede all promotions) and failure isolation
         (the per-key boundary lives inside one loop), not callback count.
    C-12 Storage trade-off recorded as a conscious decision: the bytes were
         ALREADY being written; the old path LEAKED 4 files per occurrence to the
         hourly sweep. The re-scope converts unreferenced bytes into referenced
         bytes. Steady-state increase is bounded by max_images (default 5) per
         ad. Seller-global dedup is a non-goal, not an oversight.
    C-13 Three false docstrings corrected in THIS commit (AdImageService class
         docstring, create_or_skip, AdImage.save). Three docs/** sentences are
         ROUTED to BLOCK 10, not edited: db-indexes.md (IX_adimages_sha256),
         db-schema.md (per-user deduplication), technical-specification.md
         (reuses existing storage — phase 06 holds it). The spec's sibling
         "cannot publish without >=1 photo" sentence is CITED as still correct,
         never edited.
    C-14 C-2 in the source plan claimed no shipped test encoded cross-ad dedup.
         That is FALSIFIED: test_dedup_survives_deferred_promotion asserted
         AdImage.objects.filter(ad__user_id=user.id).count() == 1 across two ads
         of one seller, and it is absent from the source plan's risk register
         because C-2 was wrong. The assertion is rewritten IN PLACE — not
         deleted, not split — re-pointed at the same ad so the test's stated
         purpose (pinning the explicit sha256= override under deferred
         promotion) is preserved unchanged. Also recorded here: the pre-existing
         migration drift (test_migrations.py::test_makemigrations_check, from
         commit b3fde27, visible only under config.settings.test_migrations
         because config/settings/test.py sets DisableMigrations) is ATTRIBUTED
         and left unfixed; this commit adds no migration.
  verify: "git show --stat HEAD lists exactly the intended files and nothing else; git diff HEAD~1 --name-only shows no plan file, no locale file, no docs file, no admin.py and no migration."

acceptance_criteria:
  - "`AdImageService.create_or_skip` filters the duplicate lookup on the target **ad** (`filter(ad=ad, sha256=digest)`), with an explicit `.order_by(\"pk\")`, the `if digest:` guard intact, and no reference to `ad__user_id` in the predicate."
  - "The return type is still `AdImage`; `test_thumbnail_integration.py` (which calls `create_or_skip` directly and reads `.thumbnail_*`) and the four `test_ad_image_service.py` assertions on `.pk` / `.image` / `.sha256` are green unchanged."
  - "The dedup skip still logs at **INFO** with the substring `dedup`, unmoved and unreworded."
  - "`SubmittedPhoto.storage_keys()` exists, returns `storage_key`, `thumbnail_small`, `thumbnail_medium`, `thumbnail_large` in `AdImage.storage_keys()` order filtered for truthy, **imports nothing**, and the `apps/media/schemas.py` module docstring records that the leaf claim survives."
  - "`SubmittedPhoto` never deletes bytes and `apps/media/schemas.py` never imports `STAGING_PREFIX`."
  - "`filesystem.reclaim_staged_keys(keys: Iterable[str]) -> None` exists as a sibling of `promote_media_files`, composes `STAGING_PREFIX + key`, calls `delete_photo` directly (never `apps.media.signals.delete_photo`), wraps **each** key in `try/except Exception` + `logger.exception` with the BLE001 noqa, and never propagates."
  - "`submit_ad` prunes with `permanent_keys[:] = [...]`; there is **no** rebinding of `permanent_keys` anywhere in the function."
  - "Exactly **one** `on_commit` reclaim registration per submission, guarded by `if reclaimed_keys:`, placed **after `auto_moderate`** and **immediately before** the existing `promote_media_files` registration."
  - "`submit_ad`'s transition table, `auto_moderate` call, `DRAFT_GONE` / `PHOTO_UNAVAILABLE` / `INVALID_TRANSITION` returns, thumbnail loop, `staged_digests`, pre-flight ordering and return contract are unchanged."
  - "`test_dedup_survives_deferred_promotion` is **rewritten in place** (not deleted, not split): same ad, re-armed to `DRAFT` between submissions with a comment saying why, positions `0` then `1`, keeping `sha256 != \"\"` and `sha256 == expected_digest` verbatim, plus the same-ad count assertion AND the returned-`pk` equality."
  - "**The tripwire was demonstrated red before the fix was called done:** removing `sha256=` from the `submit_ad` call site makes the rewritten test fail with `count == 2`, not `IntegrityError`."
  - "The no-DB `TestReclaimStagedKeys` test exists and passes without a database; its `ValueError`-raising key (composed argument `\"staging/../x.jpg\"`, whose parts contain `..`) proves per-key isolation — the remaining keys are still deleted."
  - "The intra-submission duplicate test proves the **1-4 file** reclaim: exactly one `AdImage` row, photo 0 promoted, and photo 1's original **and thumbnails** absent from both `staging/` and permanent storage."
  - "The rollback test proves placement B: on `auto_moderate` raising, both photos' staged files survive, `AdImage` count is 0, and nothing was promoted."
  - "The `INVALID_TRANSITION` test proves the hook placement: after a refused transition the skipped photo's staged file **still exists**."
  - "The moderation-failure test proves `auto_moderate -> False` still commits and the hooks still fire."
  - "Every new `create_test_ad` / `create_test_ad_bulk` call is **status-grounded**, so `apps/core/tests/test_ad_factory_contract.py` stays green."
  - "All three false docstrings are corrected — `AdImageService`, `create_or_skip`, `AdImage.save` — and `save`'s sentence now says \"to the same ad\"."
  - "`AdImage.storage_keys()`, `AdImage.Meta` and every index are byte-identical; no model field, constraint or index changed; **no migration was added**, and `0002_alter_moderatoractionlog_reason.py` was NOT created."
  - "`plan_staging_promotion`, `promote_media_files`, `STAGING_PREFIX`, `STAGING_SUBDIR`, `delete_photo`, `apps/media/services/__init__.py`, `apps/media/signals.py`, `apps/media/services/references.py`, `media_gate`, `copy_ad`, `ALLOWED_TRANSITIONS` and both `conftest.py` files are byte-identical."
  - "No `.po` / `.mo` file changed and nothing under `docs/**` changed — including the three sentences routed to BLOCK 10."
  - 'The 12-path targeted run led by `src/telegram_bot/tests/test_save_photo_integration.py` is green, and `.\Makefile.ps1 test` is green.'
  - "`uv run ruff check src/` and `uv run basedpyright src/` are both clean."
  - "Any red gate was re-run **serially** on the identical command and reproduced twice before being reported; transient setup errors from the concurrent session are not reported as red."
  - "`test_migrations.py::test_makemigrations_check` is attributed, not silently passed over: re-read the gate result rather than asserting it — if still red, the commit body proves the attribution to `b3fde27` with the `DisableMigrations` reason; if another agent's untracked `apps/moderation/migrations/0002_alter_moderatoractionlog_reason.py` has already resolved it, the commit body records that instead. **Not** fixed by BLOCK 1 and **not** staged by BLOCK 1 in either case."
  - "Exactly **one** commit, message `fix(ads): scope photo dedup to the target ad and reclaim skipped uploads`, staged by explicit path only — `git show --stat` lists exactly the intended files and nothing else (no plan file, no `staticfiles/`, no `admin.py`, no other agent's files, no migration)."
  - "The commit body records all fourteen items C-1 through C-14 listed in `commit.body_must_record`."
  - "`git status` shows no unrelated file staged, and no `git reset` / `git checkout` / `git restore` / `git stash` / `--amend` / force-push was used at any point."
```

```yaml
id: task_07-media-1-verification
title: "Verify — BLOCK 1 Scope photo dedup to the target ad + reclaim the skipped upload"
type: verification
status: pending

depends_on:
  - task_07-media-1-implementation

verifies:
  - task_07-media-1-implementation

verification_steps:
  - build: "uv run ruff check src/ && uv run basedpyright src/"
  - test: "$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS=\"src/telegram_bot/tests/test_save_photo_integration.py src/backend/apps/ads/tests/test_ad_image_service.py src/backend/apps/ads/tests/test_submission.py src/backend/apps/ads/tests/test_adimage_storage_keys.py src/backend/apps/media/tests/test_thumbnail_integration.py src/backend/apps/media/tests/test_filesystem.py src/backend/apps/media/tests/test_references.py src/backend/apps/media/tests/test_media_config.py src/backend/apps/core/tests/test_ad_image_delete_signal.py src/backend/apps/core/tests/test_delete_photo_single_call.py src/backend/apps/core/tests/test_ad_factory_contract.py src/backend/apps/ads/tests/test_media_security.py src/backend/apps/ads/tests/test_copy_ad.py --tb=short\" test   # then: .\\Makefile.ps1 test"
  - smoke_check: "git show --stat HEAD — exactly the intended files, no plan file, no staticfiles/, no admin.py, no deactivation.py, no locale, no docs, no migration. Then re-read the three production diffs and confirm: the predicate filters on (ad, sha256) with .order_by('pk'); permanent_keys is pruned with an in-place slice; exactly one reclaim on_commit registration sits after auto_moderate and immediately before promote_media_files; reclaim_staged_keys wraps every key in try/except Exception + logger.exception."

pass_criteria:
  - "build succeeds — ruff and basedpyright both clean"
  - "all tests pass — the 12-path targeted run led by src/telegram_bot/tests/test_save_photo_integration.py, then .\\Makefile.ps1 test; any first-run red is re-run serially and reproduced twice before being called red"
  - "smoke_check confirms one commit whose path list is exactly the intended files and which contains no plan file, no staticfiles/, no admin.py, no deactivation.py, no .po/.mo, no docs file and no migration"
  - "`create_or_skip` filters on (ad, sha256) with an explicit .order_by('pk'), the return type is still AdImage, and the dedup skip still logs at INFO with the substring 'dedup'"
  - "the skip test in submit_ad compares returned.image against the offered key and the site carries the uuid4 proof plus the mis-classification asymmetry — confirmed by reading the comment, not by trusting the commit message"
  - "`permanent_keys` is pruned by in-place slice assignment only; a repo read of submit_ad finds no rebinding of permanent_keys and the promotion closure still reads `lambda keys=permanent_keys`"
  - "exactly ONE reclaim on_commit registration exists, guarded by `if reclaimed_keys:`, located after the auto_moderate call and immediately before the promote_media_files registration"
  - "the INVALID_TRANSITION test is green — proving the reclaim does not fire on a refused transition; this is the test that fails if the hook is moved above auto_moderate"
  - "the rollback test is green and shows staged files surviving with zero AdImage rows and no promotion — placement B"
  - "reclaim_staged_keys composes STAGING_PREFIX + key, calls filesystem.delete_photo directly (not apps.media.signals.delete_photo), wraps EACH key in try/except Exception + logger.exception, and never raises"
  - "the no-DB TestReclaimStagedKeys passes without a database and its 'staging/../x.jpg' key proves per-key isolation — the remaining keys are still deleted and the exception is logged"
  - "the intra-submission duplicate test asserts the full 1-4 file range: photo 1's original AND all three thumbnails are absent from both staging/ and permanent storage"
  - "`SubmittedPhoto.storage_keys()` exists, mirrors AdImage.storage_keys() field order filtered for truthy, imports nothing, and apps/media/schemas.py still declares itself a leaf"
  - "no second byte-freeing entry point was created: SubmittedPhoto does not delete, and no new module was added — reclaim_staged_keys is a sibling in filesystem.py"
  - "`unreferenced_keys` is NOT composed and apps/media/services/references.py is byte-identical; a repo-wide read finds no new reference predicate in this block"
  - "AdImage.storage_keys(), AdImage.Meta and the indexes are byte-identical; no model field, constraint or index changed; no migration was added and 0002_alter_moderatoractionlog_reason.py was NOT created"
  - "plan_staging_promotion, promote_media_files, STAGING_PREFIX, STAGING_SUBDIR, delete_photo, apps/media/services/__init__.py, apps/media/signals.py, media_gate, copy_ad, ALLOWED_TRANSITIONS and both conftest.py files are byte-identical"
  - "the three corrected docstrings are present and no sentence in docs/** was edited — the three known-false doc sentences are still there for BLOCK 10, and the spec's 'cannot publish without >=1 photo' sentence is untouched"
  - "test_migrations.py::test_makemigrations_check is attributed to commit b3fde27 with the DisableMigrations reason in the commit body, not fixed, and demonstrably unrelated to this change"
  - "the commit body records all fourteen items C-1 through C-14, including the four-point reason unreferenced_keys is not composed and the falsification of the source plan's C-2"
  - "the execution plan file remains untracked and .ai/tmp/, staticfiles/ and both other agents' modified files are absent from the commit"

failure_action: return task_07-media-1-implementation to rework

rollback_task: none — the reclaim deletes bytes, which a revert cannot restore. Rollback means STOPPING the re-scope (the predicate reverts and orphans return to the hourly sweep), not un-deleting files. Worst case of the change itself is a LEAK, recoverable by sweep_orphaned_media, never a loss.
```

---

## BLOCK 3 — Atomic thumbnail writes + repair guard

**Findings owned.** `07-MEDIA-004`.
**Depends on.** BLOCK 1 (same `submission.py` neighbourhood; serial order only). **Risk.** HIGH — one-way data effect on files.

**Required agents.**
- **Auditor** — confirm the write path has no temp-file discipline and enumerate every caller that depends on the current `FileExistsError` contract. **Answered by the Researcher below**; nothing is left to audit.
- **Researcher** — **DONE.** OC-2 resolved with verified `os.link` / `os.replace` / POSIX semantics plus an in-container probe. **No open research question remains in this block.**
- **Planner** — light: record the write-mode enum's shape and the guard's decision table. Nothing architectural is open; the Implementor may proceed from this brief.
- **Implementor** — land the publish helper, the write-mode enum, and the backfill guard.
- **Validator** — mandatory: the block changes how bytes reach `MEDIA_ROOT`, touches a shipped contract, and interacts with `submit_ad`'s catch.

**What is wrong — three defects, verified against the live tree (Researcher).**

**D1 — the publish step is not atomic; a final path can hold a truncated file.** `ThumbnailService.generate_thumbnails` writes each size **directly to its final path**: `os.open(target_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)` → `os.write` → `os.close`. The directory entry becomes visible at `os.open` time, so any failure after that point — short write, `ENOSPC`, `EIO`, `SIGKILL`, container restart — leaves a **truncated or zero-length file at a final path**. `O_EXCL` buys create-or-fail and nothing else. A caller observes a successful-looking return from `os.open` followed by an exception, or no exception at all after a crash. `submit_ad`'s catch then nulls all three columns, so the corrupt file is **unreferenced** and only the hourly orphan sweep removes it — recovery by luck, not by design. Nothing in the codebase can distinguish a truncated `-small.jpg` from a good one. Both the module docstring ("with EXIF orientation correction, LANCZOS resampling, and **atomic writes**") and the method docstring ("writes **atomically** to `storage_dir`") already claim the guarantee the code does not provide.

**D2 — the partial-set state is not merely incomplete, it is *permanently unrepairable*.** `SIZES` iterates small → medium → large and `_read_and_generate` swallows `FileExistsError`. So: run 1 writes `-small.jpg` and dies; run 2's **first** `O_EXCL` raises `FileExistsError` on `-small.jpg`, is logged as `"(race), skipping"`, and returns `None`. Every subsequent run repeats byte-for-byte. The row is only ever repaired by the **`sweep_orphaned_media` cron** deleting the unreferenced file — `docs/ops/docker-deployment.md` schedules that sweep hourly, while `backfill_thumbnails` is **not scheduled at all** (`grep backfill_thumbnails docs/ops/*.md` → no hit). A backfill command that cannot repair the state its own writer creates is the defect's worst expression, and it is invisible in the logs: every run reports a plausible "race".

**D3 — the guard conflates three states into one action.** `_read_and_generate` maps (i) fresh, (ii) stale leftover from a dead run, and (iii) genuine concurrent generation all to `None`/skip. Only (ii) needs regeneration; (iii) needs a no-op; today neither happens.

`submit_ad`'s blanket `except Exception` is **not** part of the defect — see the decision below.

**OC-2 — RESOLVED by the Researcher. There is a third option; the shipped green test is preserved unchanged.**

The register's premise is right about `os.replace` and wrong that only two options exist. Verified against **Python 3.14.8 official documentation** (`docs.python.org/3/library/os.html`):

> `os.replace(src, dst, …)` — "If dst exists and is a file, it will be **replaced silently** if the user has permission. The operation may fail if src and dst are on different filesystems. If successful, the renaming will be an atomic operation (this is a POSIX requirement)."

So `os.replace` can never raise `FileExistsError`, and option (b) — rewriting the contract — would otherwise have been forced. **`os.link` (POSIX `link(2)`) satisfies both requirements in one syscall with no TOCTOU window.** Verified against **The Open Group Base Specifications Issue 7, IEEE Std 1003.1-2017**, `link(2)`:

> "The `link()` function shall **atomically** create a new link for the existing file and the link count of the file shall be incremented by one."
> "[**EEXIST**] The `path2` argument resolves to an existing directory entry or refers to a symbolic link."
> "If `link()` fails, no link shall be created and the link count of the file shall remain unchanged."
> "[EXDEV] The link named by `path2` and the file named by `path1` are on different file systems…"

Python maps `EEXIST` to `FileExistsError`; `os.link` availability is "Unix, Windows". **Empirically confirmed in this project's own container** (`docker compose --project-name mko-bazuna-test … run --rm --no-deps --entrypoint "" web python`, Python 3.14): `os.link` succeeded on the `media_volume` **named volume** at `/app/media` (the real `MEDIA_ROOT` mount — a named volume, not a host bind mount, so there is no virtiofs/FUSE hard-link caveat) and on `/tmp`; a **second** link raised `FileExistsError` with `errno == 17`; `os.replace` over the same destination clobbered silently.

**Mechanism comparison.**

| Option | Atomic full content? | `FileExistsError` on collision? | TOCTOU | Verdict |
|---|---|---|---|---|
| (a) temp + `os.replace` | Yes | **No** — silently overwrites | n/a | Rejected: loses the property the test pins |
| (b) temp + pre-check + `os.replace` | Yes | Only in the single-threaded case | **Yes** — a concurrent writer is clobbered between check and replace | Rejected: preserves the *assertion*, destroys the *invariant* |
| (c) keep `O_EXCL`, verify after write | **No** — the corrupt window is exactly what we are fixing | Yes | n/a | Rejected: it is the status quo plus a lint |
| (d) temp + **`os.link`** + unlink temp | **Yes** (atomic link) | **Yes** (EEXIST by POSIX) | **None** | **CHOSEN** for the create path |
| (e) temp + `os.replace` | Yes | n/a | n/a | **CHOSEN** for the repair path only, where overwriting is the intent |

**Decision.** One publish helper plus a write mode:

- `CREATE_ONLY` (**default; every existing caller unchanged**): write the temp file, `os.link(temp_path, target_path)`, then unlink the temp in a `finally`. A collision raises `FileExistsError` **exactly as today**.
- `REPLACE` (**new; repair callers only**): write the temp file, then `os.replace(temp_path, target_path)` — the rename consumes the temp, so no separate cleanup call is needed.

**`test_atomic_write_collision_raises_file_exists` is PRESERVED.** Its inline comment's mechanism reference changes only (`# Second call with same key raises FileExistsError (O_EXCL)` → names `os.link`); the `pytest.raises(FileExistsError)` assertion, the first successful call, and the test's purpose — *a concurrent double-generation never silently clobbers* — are untouched. **No shipped test is rewritten, so project rule 2 is never invoked, and the risk-register row at the bottom of this plan (which names this test as one of only two slated for treatment) is void for BLOCK 3.** `apps/seed/generators/images.py::_preprocess_one`, which also catches `FileExistsError`, keeps working unchanged for the same reason.

**Atomicity boundary: per FILE, not per call.** Each published file is either absent or complete; the three sizes are independent. The reasoning is the asymmetry: a row with `thumbnail_small` populated and the others `NULL` is a **detectable and repairable** state (the guard below keys off exactly that, and BLOCK 5's cache check does too), whereas a **truncated** file is unrepairable because nothing can distinguish it from a good one. The guarantee worth buying is therefore content integrity per file. The set-level guarantee is not worth its cost: honouring it would require **deleting already-published files** on a mid-set failure — a strictly worse property (a deletion race against a concurrent reader) that still would not hold across a `SIGKILL` between the first and second publish. Project rule 5 decides it. **The spec's required test 1 is amended accordingly** (see Required tests).

**Correctness note on a repair-mode `os.replace`:** a reader (nginx serving `/media/`) sees either the whole old file or the whole new one, never a mixture — the same atomicity class as the create path.

**Surface (semantic units only).**
- `apps/media/services/thumbnails.py::ThumbnailService.generate_thumbnails` — the write path, its signature and its docstring
- `apps/media/services/thumbnails.py` — the publish helper (temp → link/replace → cleanup) and the module constant for the temp-name suffix
- `apps/core/enums.py` — the new write-mode `StrEnum`, declared beside `ThumbnailSizeStrEnum`
- `apps/media/management/commands/backfill_thumbnails.py::Command._read_and_generate` — the swallowed `FileExistsError` and the mode decision
- `apps/media/management/commands/backfill_thumbnails.py::Command.handle` — the repair-mode wiring (no new CLI flag; see the guard decision)
- `src/backend/apps/media/tests/test_thumbnails.py` — publish-helper and mode tests
- `src/backend/apps/media/tests/test_backfill_thumbnails.py` — repair-guard tests

**Repair guard — shape and location (Researcher decision).**

**The database column is the single source of truth; the file is derived state.** The guard's only input is therefore the row's column state, and the two states the spec fused need no discrimination at all:

| `thumbnail_*` columns | Target file on disk | Action | Log |
|---|---|---|---|
| all three populated | any | **skip** — no service call | — (Phase 1's queryset does not select it in the first place) |
| ≥1 `NULL` | none of the three present | `CREATE_ONLY` | — |
| ≥1 `NULL` | ≥1 present | **`REPLACE`** — the stale-leftover case (D2) | INFO naming `stale-leftover` and the conflicting size |

A **genuine concurrent generation** needs no separate branch: another backfill run that already wrote the files but has not yet run Phase 3 presents the *same* observable state (columns `NULL`, files present), and `REPLACE` rewrites byte-identical content from the same original — atomic, idempotent and harmless. Converging the two cases on one action is the whole simplification; **the guard does not try to tell them apart and must not grow a heuristic that does.**

- **Location: the decision lives in the management command; the capability lives in the service.** `_read_and_generate` is the only place that knows the column state, and `ThumbnailService` is a DB-free filesystem service today — it must stay one. So `generate_thumbnails` gains a **keyword-only** `mode` parameter typed by a new `StrEnum` in `apps/core/enums.py` beside `ThumbnailSizeStrEnum` (project rule 10), defaulting to `CREATE_ONLY`, and the command chooses the value. One code path for encode; one branch in the publish helper.
- **No new shared predicate module, and this is deliberate.** The check is three `os.path.exists` calls. Putting it in `apps/media/services/references.py` would violate that module's stated boundary verbatim — "This module is a **database predicate only** — it performs no filesystem I/O" — and a new module for three `exists()` calls is overengineering (project rule 5). Recorded for accuracy: `unreferenced_keys` lives in `references.py`, **not** in `filesystem.py`.
- **No new CLI flag. `REPLACE` is the default for a `NULL`-column row.** The current behaviour for such a row is "skip forever", which is never what an operator wants from a backfill; a flag would add a second mode to document and test for no gain.
- **What BLOCK 5 reuses is the capability, not the helper**: BLOCK 5 consumes `mode=REPLACE` from the service. BLOCK 5's seed path decides from disk state, not column state.

**`submit_ad` catch — decision: KEEP the blanket `except Exception`, unchanged.**

Consequence, stated plainly: a thumbnail failure (including a `FileExistsError` collision, which the new create path still raises) continues to publish the ad with all three columns `NULL`, exactly as today, and stays pinned by `src/telegram_bot/tests/test_save_photo_integration.py::TestSavePhotoThumbnailsIntegration::test_thumbnails_null_on_generation_failure`. Four reasons, in order of weight:

1. **`apps/ads/services/submission.py` is HELD by phase 05** and is the most contended file in the plan set — BLOCK 1 has just landed in it (`4ffd427`). Narrowing the catch buys this block nothing the writer fix does not already buy.
2. The catch's contract is **pinned by a shipped green test** (asserts `outcome is PUBLISHED` *and* all three columns `NULL`). Narrowing it would break that test or force a second contract rewrite under project rule 2.
3. Pillow's failure surface from `thumbnail()` / `save()` is wide and not exhaustively typed (`UnidentifiedImageError`, `Image.DecompressionBombError`, `MemoryError`, `struct.error`, `OSError`, plus the `ValueError` the service raises itself). A narrowed tuple is either incomplete — reintroducing publish failures on a live user path — or a long tail that documents nothing.
4. The catch **is not the defect**. It is a deliberate "media failure must not block a publish" boundary, and with atomic publishes it becomes *consistent with the filesystem* for the first time: a failure now leaves **no partial file**, so nulling all three columns matches what is on disk. That is the real repair, and it happens upstream.

Record in the commit body: the catch was reviewed and deliberately left alone, with reasons 1 and 4. **The keep-green clause "except the recorded catch decision" is therefore moot — the file is not edited at all.**

**Binding constraints.**
1. **Write mode is a `StrEnum`** (`CREATE_ONLY` / `REPLACE`) declared in `apps/core/enums.py` beside `ThumbnailSizeStrEnum`, passed as a **keyword-only** parameter defaulting to `CREATE_ONLY`. No plain strings, no dicts (project rule 10).
2. `CREATE_ONLY` publishes with **`os.link`**; `REPLACE` publishes with `os.replace`. No other mechanism is permitted, and **no pre-existence check may be added anywhere** — it would create the TOCTOU window that makes option (b) worthless.
3. Temp files are created in the **destination directory** — `os.path.dirname(target_path)`, which for a staged photo is `MEDIA_ROOT/staging/` — never a system temp dir. A cross-device move degrades to a non-atomic copy and the guarantee becomes a lie. `EXDEV` is therefore impossible by construction; **do not add an `EXDEV` fallback** (there is nothing to handle, and `promote_media_files`' existing fallback covers a different mount layout).
4. **The temp file must be created with `os.open(…, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666)`.** `tempfile.mkstemp` is **forbidden**: it creates files with mode `0600`, and after the link/replace the published file would inherit that mode. nginx serves `/media/` as `user nginx` — a different uid from the app's `app` (uid 1000, `USER app` in `docker/Dockerfile`) — so every image on the site would return 403. Verified in-container: the current `os.open` path yields mode `0o755` (umask-derived), so passing `0o666` reproduces today's permissions exactly. **This is the highest-impact trap in the block and it has its own required test.**
5. Temp names are unique and never collide with a real key: `.{basename}.{uuid4().hex}{TEMP_SUFFIX}` with `TEMP_SUFFIX: Final[str]` as a module constant. A name that is not `*.jpg` also keeps a temp file from ever matching `KEY_FORMAT_REGEX` or an `AdImage` column.
6. **Cleanup on every in-process failure path**: the temp is unlinked in a `finally` that swallows only `FileNotFoundError`. It survives neither a successful call nor a failed one. A `SIGKILL`ed process can still leave one, and that is acceptable because both reapers already collect it: a temp in `MEDIA_ROOT` is an unreferenced file for the hourly `sweep_orphaned_media` (it routes through `delete_photo`, whose containment check passes), and a temp in `staging/` is collected by `_reclaim_stale_staging` after 2 h. **Self-healing by construction — state this in the docstring rather than claiming it cannot happen.**
7. Atomicity is claimed **per file**, and **crash-durability is not claimed at all** (no `fsync` of the temp or the directory). Today's writer has the same gap; adding `fsync` is out of scope. The docstring must not imply durability.
8. `ThumbnailService.QUALITY == 85` is **unchanged** (BLOCK 4's file), and so are `SIZES`, `FORMAT`, `RESAMPLING` and `PROGRESSIVE`.
9. The EXIF orientation correction and the `convert("RGB")` in `generate_thumbnails` are **untouched**.
10. The module docstring and `generate_thumbnails`'s docstring are updated to describe what the code now guarantees (per-file atomicity, `CREATE_ONLY` create-or-fail, the mode parameter). **A docstring must never claim a guarantee the code does not provide** — that is the defect this block exists to remove. `_read_and_generate`'s docstring loses its `None` = "(race condition)" wording and gains the decision table.
11. Backfill I/O stays **outside** `transaction.atomic()` (verified still true — the three-phase structure from `4cf417b` is intact) and outside the advisory lock.
12. **`apps/ads/services/submission.py` is not edited at all** (see the catch decision). Phase 05 holds the file; re-read it immediately before any incidental touch and stop if it has moved.
13. No migration, no model change, no index, no new setting, no new dependency. `MAX_PHOTO_BYTES` untouched.
14. `media_gate`, `copy_ad`, `AdImage.storage_keys()` and `KEY_FORMAT_REGEX` are untouched.

**Required tests** (logic + component interaction). `test_thumbnails.py` grows from 11 tests; `test_backfill_thumbnails.py` from 8.

In `src/backend/apps/media/tests/test_thumbnails.py`:
1. **The preserved contract.** `test_atomic_write_collision_raises_file_exists` unchanged: first call succeeds, second raises `FileExistsError`. Additionally assert the three files from the first call are **still byte-identical** after the failed second call — that is the "does not silently clobber" half of the original purpose, which a bare `pytest.raises` never actually verified.
2. **A published file is group/world-readable.** `mode & 0o044` is non-zero for a freshly published thumbnail (constraint 4's tripwire; a regression here is a silent site-wide image outage that no other test would catch).
3. **A failure mid-write leaves no partial and no temp file.** Inject the failure *inside* the write step; assert the destination is **absent** — not zero-length, not truncated — and that **no** temp file remains in the directory.
4. **A failure on the second size** (injected at `MEDIUM`) leaves the first size **complete and valid**, the later sizes absent, and no temp file. **This is the spec's old test 1, amended:** the assertion is "every file present at a final path is complete", *not* "no files are present". Per-file atomicity is the shipped guarantee; a per-call rollback is explicitly out of scope and must **not** be implemented to satisfy the old wording.
5. **No temp file survives a successful call** — the directory listing after a successful call contains exactly the three final names.
6. **`REPLACE` overwrites** an existing complete file (content replaced, file still a valid JPEG) and **overwrites a truncated leftover** (the pre-existing corrupt-byte class), and creates the file when absent.
7. **Temp files land in the destination directory**, including for a `staging/`-prefixed key — assert `MEDIA_ROOT/staging/` is used, not `MEDIA_ROOT` and not a system temp dir.
8. Every existing size / format / progressive / aspect / EXIF assertion stays green unchanged.

In `src/backend/apps/media/tests/test_backfill_thumbnails.py`:
9. **The stuck-state regression test (D2's tripwire).** Pre-create `-small.jpg` on disk with the row's columns all `NULL` — exactly the state a dead run leaves — then run the command. Assert **all three columns end populated and all three files exist and decode**. Under today's code this row is skipped forever; it is the single most important new test in the block.
10. **A populated column plus an existing file is preserved.** The existing partial-thumbnail test already covers this; keep it green.
11. **A second repair run is a no-op** — column values unchanged, populated columns not rewritten, no error counted.
12. Component interaction: `generate_thumbnails` → `backfill_thumbnails` → the row's three `thumbnail_*` values all point at files that exist and each decodes as a valid JPEG.

**Keep green / do not edit.**
`test_thumbnail_integration.py` · `test_save_photo_exif.py` · `test_media_config.py` · `test_ad_image_service.py` · `test_delete_photo_single_call.py` · `test_filesystem.py` · `test_references.py` · `test_sweep_orphaned_media.py` · `src/backend/apps/seed/tests/test_seed.py` (its `ImageGenerator` case calls `_preprocess_one` directly) · **`src/telegram_bot/tests/test_save_photo_integration.py`** (pins the `submit_ad` catch — the spec's keep-green list omitted it) · `apps/ads/services/submission.py` (**the whole file; the catch decision is "no change"**) · `apps/seed/generators/images.py` (its `except FileExistsError` keeps working *because* the contract is preserved) · `ThumbnailService.QUALITY` · `src/backend/conftest.py`.

**Gate (exact).**
```
$dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/media/tests src/backend/apps/ads/tests/test_ad_image_service.py --tb=short" test
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/telegram_bot/tests/test_save_photo_integration.py --tb=short" test
.\Makefile.ps1 test
uv run ruff check src/
uv run basedpyright src/
```
The bot module is a **second invocation** on purpose: it has its own `conftest.py` (bot tests cannot import the backend one), and the spec's single invocation omitted it entirely, which would have left the `submit_ad` contract unpinned at the gate. A wall of *setup* errors (`DuplicateDatabase`, `ObjectInUse`) is another agent running the suite concurrently — re-run serially before reporting red. `test_search_slo` is a known environmental flake and is not in this gate. `uv run basedpyright src/` has **3 pre-existing** errors in `apps/search/tests/test_immediate_alerts.py` and `apps/users/tests/test_login.py`: the baseline is 3, not 0.

**Commit-body items (required, in this order).**
1. OC-2 resolution — `os.link` publish for the create path — with both citations (Python 3.14.8 `os.replace` "replaced silently"; POSIX Issue 7 `link(2)` "shall atomically create" plus `[EEXIST]`) and the in-container probe result, including that `media_volume` is a named volume so hard links are supported.
2. **Explicit statement that no shipped test was rewritten.** `test_atomic_write_collision_raises_file_exists` is preserved; only the mechanism reference in its comment changed; the added byte-identity assertion strengthens the invariant it was written to protect. Project rule 2 is therefore not invoked.
3. Per-file (not per-call) atomicity and why: the truncated-file class is unrepairable while the partial-set class is detectable and repairable, so per-call rollback would buy a weaker and more dangerous guarantee.
4. The file-mode trap: temp files are created `0o666`-and-umask, **not** via `tempfile.mkstemp`, because nginx reads `/media/` as a different uid and `0600` would 403 every image.
5. The `submit_ad` catch was reviewed and **deliberately left unchanged**, with the reason: `submission.py` is phase-05-held and its contract is pinned by `test_thumbnails_null_on_generation_failure`.
6. The stale-leftover guard: the decision table, the "the column is the source of truth" rule, and that a genuine race converges on the same action (no race heuristic was added).
7. The one-way data effect: a backfill run over a `NULL`-column row now **overwrites** the leftover files for that row. Bytes are complete at every instant and content is deterministic from the same original.

**Corrections to the spec's premises (do not repeat the spec's text).**
- "There is no third option" for OC-2 — **false**. `os.link` is a third mechanism that preserves the contract *and* atomicity with no TOCTOU.
- "A failure on the second size leaves … a half-written state that the seed generator's cache check then reports as complete" — the seed half is BLOCK 5's defect, not this one. The correct statement is D2: the backfill's own `FileExistsError` catch makes the row **permanently** unrepairable without the hourly orphan sweep.
- Required test 1 as written ("a failure on the second size leaves **no partial files**") contradicts the chosen boundary and is **amended** to "no partial *content*, no temp file".
- The keep-green list omitted `src/telegram_bot/tests/test_save_photo_integration.py`, and the gate omitted it from the test run.
- The file-mode requirement is absent from the spec entirely and is the block's largest single risk.
- The guard's repair cannot reach a **truncated file on a row whose columns are all populated**: such a row is excluded by Phase 1's queryset and by design (the command backfills missing columns). A decode check inside the guard would be dead code, because `REPLACE` already rewrites the file whenever the guard fires. The populated-but-corrupt class is routed to **BLOCK 6** (dangling-row reconciliation) as a follow-up question, deliberately **not** solved here.

**Risk and rollback.** One-way data effect on files. Rollback = stop shipping; reverting restores the non-atomic writer and **already-generated files stay**; no reverse migration. The narrowest blast radius is `MEDIA_ROOT`. Residual after landing: (a) **crash-durability is not claimed** — no `fsync`, identical to today; (b) a `SIGKILL` can leave one temp file, reaped by the existing sweep / staging TTL; (c) a create-path collision on the *second* size still leaves the first size on disk (unreferenced → swept hourly), because per-call rollback was rejected; (d) a backfill run re-encodes the leftovers it repairs, so if a future change alters thumbnail encoding, repaired rows get the new encoding while untouched rows keep the old — files stay complete and atomic throughout, which is the invariant that matters; (e) `os.link` requires a filesystem with hard-link support — verified on this project's `media_volume` named volume and on `/tmp`; an exotic `MEDIA_ROOT` mount without it would surface as a propagating `OSError` (already caught by both existing callers) rather than a silent downgrade, because no fallback is implemented on purpose. BLOCK 3 is the hard prerequisite for BLOCK 5, which consumes `mode=REPLACE`.

---

## BLOCK 4 — Name the stored-original JPEG quality

**Findings owned.** `07-MEDIA-011`.
**Depends on.** BLOCK 3 (serial order; declares a second quality constant in the same subsystem). **Risk.** LOW.

**Required agents.**
- **Auditor** — confirm `filesystem.py` and `thumbnails.py` have **no import edge** in either direction, and that `STORED_JPEG_QUALITY` exists nowhere in `src/`.
- **Researcher** — **not required.** Q07-11 is resolved by measurement (Pillow's effective default is **75**, verified in-image). There is no remaining best-practices question.
- **Planner** — light: record **where** the constant is declared and **substitute** the now-impossible proximity test. Both are decisions, not edits.
- **Implementor** — declare the constant, use it, update the docstring, add one property test.
- **Validator** — mandatory: the block's headline number is **inherited from a measurement**, and the test must assert the *wiring*, never the literal.

**What is wrong.** `strip_photo_exif` in `apps/media/services/filesystem.py` saves with `optimize=True, comment=b"", exif=b""` and **passes no `quality=`**. Every stored original therefore uses Pillow's **implicit default** (75), while `ThumbnailService.QUALITY == 85` in `apps/media/services/thumbnails.py` is explicit. The store is mixed-quality and **no name anywhere records the original's number** — a maintainer changing `ThumbnailService.QUALITY` has no way to discover that originals are stored differently. The plan's premise that `STORED_JPEG_QUALITY` already exists is **refuted**: the symbol is nowhere in `src/`, so it must be **declared fresh**. The plan's "two quality constants adjacent" test is also **impossible** — `filesystem.py` and `thumbnails.py` share no import edge, so adjacency cannot be asserted without creating a structural coupling the block should not introduce for one constant.

**Surface (semantic units only).**
- `apps/media/services/filesystem.py` — **new** module constant `STORED_JPEG_QUALITY`, declared at module level
- `apps/media/services/filesystem.py::strip_photo_exif` — pass `quality=STORED_JPEG_QUALITY`
- `apps/media/services/filesystem.py::strip_photo_exif` docstring — record the explicit quality and the mixed-store consequence
- **new** `src/backend/apps/media/tests/test_stored_jpeg_quality.py`
- **routed, never edited**: `docs/01-spec/technical-specification.md`

**Binding constraints.**
1. Declare in `apps/media/services/filesystem.py`. Do **not** import from `thumbnails.py` and do **not** create an import edge between the two modules.
2. `STORED_JPEG_QUALITY` is a module-level constant (project rule 10) — not an inline literal, not a dict.
3. The value is **not changed "while we are here"**. 75 is inherited from Q07-11's measurement; the mixed-quality store is the accepted, documented cost and the commit body must state it.
4. The test **reads the constant the save call uses** and asserts the wiring — it must **never** assert a literal number (that would pin a measurement as a contract).
5. The two stale spec sentences are **routed to phase 06 with exact replacement text, never edited**.
6. `ThumbnailService.QUALITY == 85` is **unchanged**; the EXIF/ICC strip is **intact**; `comment=b"", exif=b""` stays.
7. No migration, no setting, no new dependency, no new module.

**Required tests.**
1. **The only new test in this block:** the value the save call uses and the module constant are the same — read both and compare, never assert a literal. *This is a property test, not a behavioural test, and that is justified in place: the finding is a naming/traceability defect, and a literal assertion would convert the inherited measurement into a contract.*

**Keep green / do not edit.**
`src/backend/apps/media/tests/test_save_photo_exif.py` (all eight `TestStripPhotoExif` and six `TestExifStripping` tests) · `apps/media/services/thumbnails.py` in full · `docs/01-spec/technical-specification.md` · `src/backend/conftest.py`.

**Gate (exact).**
```
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/media/tests/test_stored_jpeg_quality.py src/backend/apps/media/tests/test_save_photo_exif.py src/backend/apps/media/tests/test_thumbnails.py --tb=short" test
.\Makefile.ps1 test
uv run ruff check src/
uv run basedpyright src/
```

**Risk and rollback.** Lowest-risk block in the plan. Rollback restores Pillow's implicit default; **no stored bytes are re-encoded** (the constant affects new uploads only), and re-encoding existing originals is explicitly out of scope. The only material risk is scope creep into a value change — forbidden by binding constraint 3. No coordinator notification required.

---

## BLOCK 5 — Seed generator asserts only what it wrote

**Findings owned.** `07-MEDIA-008`.
**Depends on.** BLOCK 3 (**hard** — the stale-file guard BLOCK 5 reuses is created there). **Risk.** LOW-MEDIUM.
**Gate class.** **The only block requiring the full suite, including the nightly `seed` marker.**

**Required agents.**
- **Auditor** — re-verify the seed pipeline end to end (`ImageGenerator.generate`, `_preprocess_one`, `_thumbnail_key`, the `bulk_create` path) so the truthfulness gap is pinned to a real symbol.
- **Researcher** — **not required.** The plan's feasibility question (does a `NULL` thumbnail break `_backfill_image_hashes`?) is answered by ground truth: `seed_service.py` reads **only** `img.image` and never touches `thumbnail_*`. **Non-issue.** What remains is a local design choice for the Planner.
- **Planner** — required: **OC-3** (extend vs drop the single-variant cache check) is a design decision with test consequences.
- **Implementor** — land the generator fix and its tests.
- **Validator** — mandatory: the block changes a return contract that a shipped test calls directly.

**What is wrong.** `ImageGenerator._preprocess_one` in `apps/seed/generators/images.py` returns `True` **before** calling `ThumbnailService.generate_thumbnails` if the `-small` file exists. That single-variant cache check short-circuits the whole service, so a **half-written state** (small present, medium/large missing) is reported complete. `generate()` then builds all three `thumbnail_*` values from `_thumbnail_key(key, size)` **without consulting the service**, so `AdImage` rows are created pointing at files that were never written. `AdImage.objects.bulk_create` bypasses `save()`, so nothing downstream catches it. Net effect: the seed reports success and manufactures dangling references.

**Three plan premises corrected — do not repeat the plan's text.**
- **Do NOT write** the plan's test for `_backfill_image_hashes` surviving a `NULL` thumbnail. It has **no subject** — `seed_service.py` reads **only** `img.image`.
- **Positions already develop gaps today** via `continue` on a falsy `_preprocess_one`. Contiguity is deliberately **unenforced** under `uq_ad_images_ad_position`. **The fix must not renumber.**
- `photo_manifest.json`'s `default.photos` is **empty** (`{"photos":[]}`), so the default-pool injection loop is **inert**; cross-category sharing does not occur. Cross-**owner** sharing **within** a category is real (`random_elements(unique=True)` + `bulk_create`, bypassing `create_or_skip`). This is **C-1** — do not repeat the seed default-pool narrative.

**Surface (semantic units only).**
- `apps/seed/generators/images.py::ImageGenerator._preprocess_one` — the single-variant cache check
- `apps/seed/generators/images.py::ImageGenerator.generate` — position construction and thumbnail key derivation
- `apps/seed/generators/images.py::ImageGenerator._preprocess_images` — the deprecated eager variant; the return-type change **must** be propagated here
- `apps/seed/generators/images.py::ImageGenerator._thumbnail_key` — consumed, not changed
- `src/backend/apps/seed/tests/` — the seed-image test module
- `photo_manifest.json` — asserted, **never edited**

**Binding constraints.**
1. **Do not renumber `position`.** Gaps are legal and contiguity is deliberately unenforced.
2. **OC-3 stays open** — extend the cache check to all three variants, or drop it. Record the choice and its reason in the commit body.
3. The generator must assert **what it wrote**, not what it intended: a returned `thumbnail_*` value must have a file behind it, or the position is skipped exactly as today.
4. `bulk_create` stays. No per-row `save()` loop, no post-`bulk_create` repair pass, no `AdImage.save()` override.
5. `_preprocess_images` (eager, deprecated) is kept consistent with the lazy path or explicitly delegated to it.
6. **Do not populate** `photo_manifest.json`'s `default.photos` — an empty pool is the shipped manifest (C-1).
7. The sweep's **deletion** scope is unchanged; `sweep_orphaned_media.py` is read-only for this block.
8. No migration, no schema change, no new setting.
9. The full suite including the `seed` marker is **mandatory** — this is the only block that may need it.

**Required tests** (logic + component interaction).
1. After `ImageGenerator.generate`, **every** `thumbnail_*` value on **every** created row points at a file that exists.
2. A half-written state (small present, medium missing) is **regenerated**, not reported complete.
3. A seed run over the **shipped** manifest reconciles against its rows — including the inert empty `default.photos` pool. *This is the C-1 tripwire.*
4. The eager `_preprocess_images` variant propagates the same return contract.

**Keep green / do not edit.**
The full `seed` marker suite · `apps/seed/services/seed_service.py::_backfill_image_hashes` (and the module generally) · `apps/ads/models.py` (`uq_ad_images_ad_position`, `storage_keys`) · `photo_manifest.json` · `apps/media/management/commands/sweep_orphaned_media.py` · `src/backend/conftest.py`.

**Gate (exact).**
```
$dc run --rm -e PYTEST_OPTS="src/backend/apps/seed/tests src/backend/apps/media/tests/test_sweep_orphaned_media.py --tb=short" test
$dc run --rm test          # FULL suite, seed marker included — mandatory for this block only
.\Makefile.ps1 test
uv run ruff check src/
uv run basedpyright src/
```

**Risk and rollback.** Touches the slowest suite in the project; expect the longest gate. A return-contract change may collide with the shipped `test_seed_original_strips_jpeg_comment` assertion — under project rule 2 the **test** is treated if it conflicts, and the commit body names it. Rollback = revert the generator; **already-seeded rows keep their gaps** and any half-written thumbnails remain. Recovery is a **reseed**, which is an **operator** action, never a migration.

### Planner decision — **OC-3 RESOLVED: EXTEND** the cache check to all three variants

**The crux is decisive and it decides the question: `_preprocess_one` CANNOT reuse BLOCK 3's guard, so "drop the check and let BLOCK 3 decide" is not available.**

`_decide_write_mode` is a `@staticmethod` on `backfill_thumbnails.Command` with the signature `_decide_write_mode(ad_image: AdImage, storage_dir: Path) -> WriteMode`. It decides by reading `getattr(ad_image, _SIZE_COLUMNS[size_enum])` — i.e. the row's **`thumbnail_*` columns**. In the seed path there is **no row**: `generate()` builds unsaved `AdImage` instances in memory and `seed_service.py:166` `bulk_create`s them only **after** `generate()` returns. There is no column state, therefore no input for `_decide_write_mode`, therefore nothing to delegate to. Two further reasons not to reach for it: it is a **private** module constant of a **management command** (a generator importing a management command inverts the layering), and BLOCK 3's Researcher already recorded the intended seam — *"BLOCK 5 consumes `mode=REPLACE` from the service. BLOCK 5's seed path decides from disk state, not column state"* (plan line 2073). **BLOCK 5 consumes the enum value, not the helper.** This block keeps its own disk-state decision, which is the only state that exists at that point in the lifecycle.

**"Drop" is worse in both variants, for a mechanical reason:**

| Drop variant | Why it fails |
|---|---|
| always `generate_thumbnails(...)` with the default `CREATE_ONLY` | `generate_thumbnails` iterates `self.SIZES` in insertion order **SMALL → MEDIUM → LARGE** and publishes each with `os.link`. On any repeat selection of an already-encoded photo the **first** iteration raises `FileExistsError` and **aborts the loop** — medium and large are never attempted. That is *literally the original defect*: with the old `except FileExistsError: … return True` still in place, a photo with only `-small` is again reported complete; with the swallow removed, `FileExistsError` propagates out of `generate()` and **aborts the whole seed run**. Both outcomes are unacceptable. |
| always `generate_thumbnails(..., mode=WriteMode.REPLACE)` | Truthful, but it re-decodes and re-encodes all three variants on **every** call, with no fast path at all. |

**The cost of the extended check is negligible; the cost of dropping is real.** Verified against the live code:

- The extended check is **three `os.path.exists()` calls instead of one**, per `_preprocess_one` invocation. A default seed run is `seed --ads 600` with `image_count` 1–3 → ≈**1 200** invocations, so ≈**2 400 extra `stat()` syscalls** — microseconds each, against a run that performs on the order of a thousand JPEG decodes plus three LANCZOS resizes and progressive encodes apiece. The check is not the cost; the encode is.
- `_preprocess_one` is invoked once per **(ad, selected photo)** pair, not once per distinct photo. The manifest holds **205 categories** and **1 004 distinct photo filenames**. With ≈1 200 selections drawn from a 1 004-photo pool, a substantial number of photos are selected by **more than one ad**, and each such repeat is a full three-variant re-encode if the fast path is gone.
- The fast path therefore does **not** survive across runs anyway: `SeedService._clean()` `shutil.rmtree`s `MEDIA_ROOT/seed` before every seeded run. Dropping the check buys **nothing** on a fresh run (where nothing is cached to hit) and costs a re-encode on every within-run repeat. Extend strictly dominates.

**The check and the service agree on the size set by construction, so the register's coupling objection does not bite.** Neither side hard-codes `("small","medium","large")`: the generator iterates `ThumbnailSizeStrEnum` (the same `StrEnum` the service iterates) and builds each filename as `f"{stem}-{size.value}.jpg"` — the identical form the service uses. One shared predicate, derived from one enum, drives both the fast path and the post-condition.

**Mode on the repair path → `WriteMode.REPLACE`, explicitly.** The repair path is entered precisely when *at least one* target is missing and others may be present; `CREATE_ONLY` would abort on the first present size (SMALL is first) and never reach the missing one. `REPLACE` publishes all three deterministically from the same in-memory bytes, so a present file is rewritten byte-identically — idempotent — and the missing ones are created. In the seed path a present file with no row is the **normal** case rather than an anomaly, precisely because the row does not exist yet; that is the same `REPLACE` semantic BLOCK 3 assigned to a stale leftover. **The `except FileExistsError: … return True` swallow is removed**: with `REPLACE`, `os.link` is never called, so `FileExistsError` cannot originate from `generate_thumbnails` (`os.replace` raises `OSError` subclasses, never `FileExistsError`); keeping a provably-unreachable handler that returns truthy is the exact shape that manufactures dangling references. Genuine failures (`ValueError` from undecodable bytes, `OSError`) now propagate — identical to today's non-cached path, and strictly more truthful.

**Verified project-rule-2 outcome — the shipped test is NOT treated.** The risk register lists `test_seed_original_strips_jpeg_comment` as slated for treatment. Inspected: its only call-site assertion is `assert gen._preprocess_one(f"seed/{fixture_name}", seed_dir, thumbnail_service)` — a bare truthiness assert. A non-empty `dict` is truthy, and `_preprocess_one` returns `None` (falsy) only on a missing fixture or a failed post-condition. **The test passes unchanged**, so rule 2 is **not** invoked by this block. It is `@pytest.mark.seed`, so it does not run in `.\Makefile.ps1 test` at all — which is a second, independent reason the block's full-suite gate is mandatory.

**Interaction with the binding constraints.** Neither interacts. `bulk_create` stays (constraint 4) — the block changes only what the in-memory `AdImage` objects carry before that unchanged call. `position` is not renumbered (constraint 1) — it still comes from `enumerate(selected, start=1)` *before* the skip decision, so the pre-existing gap behaviour is preserved verbatim and contiguity stays deliberately unenforced under `uq_ad_images_ad_position`.

### Planner task — BLOCK 5 implementation brief

> **Template decision (recorded).** BLOCK 5 changes a return contract that a shipped `seed`-marked test calls directly, so the **verification** variant is emitted **in addition** to the primary `task_template.yaml` shape, as the block's agent list mandates ("Validator — mandatory").

```yaml
id: task_07m05_seed_thumbnail_truthfulness

title: Assert only the seed thumbnails the generator actually wrote

priority: high

status: pending

depends_on:
  - phase07_block3_thumbnail_publish   # SHIPPED as 3544e4b

source_reference: .ai\plans\20-media-remediation-execution.md
source_section: BLOCK 5 — Seed generator asserts only what it wrote
source_blocks:
  - "BLOCK 5 — Seed generator asserts only what it wrote"

description: >
  ImageGenerator._preprocess_one returns True before calling
  ThumbnailService.generate_thumbnails when only the -small file exists, so a
  half-written state (small present, medium/large missing) is reported complete.
  generate() then builds all three thumbnail_* values from _thumbnail_key without
  consulting the service, and AdImage.objects.bulk_create bypasses save(), so the
  seed manufactures rows pointing at files that were never written.

  Per resolved OC-3: EXTEND the cache check to all three variants. When all three
  exist, skip the service entirely. When one or more are missing, publish with
  WriteMode.REPLACE (BLOCK 3's repair mode) so the missing variants are written
  and the present ones are rewritten byte-identically. Change _preprocess_one to
  return the verified size->storage-key mapping (or None), build the three
  thumbnail_* columns from that mapping in generate(), and verify the published
  files exist before returning. Delete the except FileExistsError swallow — it is
  unreachable under REPLACE and is the mechanism that turns a failed publish into
  a "success".

goals:
  - A returned thumbnail_* value always has a file behind it, or the position is skipped via the existing continue path
  - A half-written state (small present, medium or large missing) is repaired, never reported complete
  - Preserve the within-run encode fast path so re-running the seed over existing files stays idempotent
  - Propagate the new return contract to the deprecated eager _preprocess_images variant by delegation
  - Do not renumber position; do not replace bulk_create; do not renumber or add migrations

extra_context: >
  Ground truth the Implementor must not re-derive:

  - ThumbnailService.generate_thumbnails(img_bytes, original_key, *, mode=WriteMode.CREATE_ONLY)
    takes a KEYWORD-ONLY mode (BLOCK 3, 3544e4b). It iterates self.SIZES in
    insertion order SMALL -> MEDIUM -> LARGE. CREATE_ONLY publishes each variant
    with os.link and raises FileExistsError on the first EXISTING target, which
    ABORTS the loop, so a later missing variant is never attempted. REPLACE
    publishes with os.replace and never raises FileExistsError. Temp files are
    written in the destination directory at 0o666-and-umask (never mkstemp),
    because nginx serves /media/ as a different uid.
  - WriteMode is a StrEnum in apps/core/enums.py (CREATE_ONLY / REPLACE).
  - backfill_thumbnails.Command._decide_write_mode is a private staticmethod that
    decides from the AdImage thumbnail_* COLUMNS. The seed path has no AdImage row
    at preprocessing time (bulk_create runs after generate() returns), so it has
    no input and must NOT be imported or reused. The seed path decides from DISK
    state. BLOCK 5 consumes the mode VALUE, not the helper.
  - _clean() in apps/seed/services/seed_service.py rmtree's MEDIA_ROOT/seed before
    every seeded run, so the fast path never hits ACROSS runs; its only live value
    is within-run dedup across ads selecting the same photo.
  - Manifest: 205 categories, 1004 distinct photos, default.photos == [] (empty).
  - Shipped test src/backend/apps/seed/tests/test_seed.py::
    TestImageGenerator::test_seed_original_strips_jpeg_comment is @pytest.mark.seed
    and asserts only truthiness of _preprocess_one's return. A non-empty dict is
    truthy, so it passes UNCHANGED. Project rule 2 is NOT invoked. Do not edit it.
  - Three plan premises are FALSIFIED; do not reproduce them:
    (1) Do NOT write the plan's test for _backfill_image_hashes surviving a NULL
        thumbnail — it has no subject. seed_service._backfill_image_hashes reads
        ONLY img.image (Path(media_root)/img.image) and never touches thumbnail_*.
        apps/seed/services/seed_service.py is READ-ONLY for this block.
    (2) Position gaps are NOT a defect. They already occur via continue on a falsy
        _preprocess_one, and contiguity is deliberately unenforced under
        uq_ad_images_ad_position (AdImage docstring says so explicitly).
    (3) photo_manifest.json's default.photos is {"photos":[]}, so the default-pool
        injection loop is INERT and cross-category sharing does not occur. Do not
        repeat the source plan's default-pool narrative.
  - Fix C-1 in the plan text: the empty default pool is the SHIPPED manifest state.
    photo_manifest.json is asserted, NEVER edited.
  - strip_photo_exif + the original write in _preprocess_one are OUT OF SCOPE.
    Keep the original write on both paths (the fast path included); skipping it
    would let a stale unstripped original survive and break the shipped
    MED-003 test.
  - apps/seed/tests/conftest.py patches seed_service.ImageGenerator only, so
    tests that import ImageGenerator directly are unaffected by that autouse stub.

  Working tree: other agents have uncommitted work. apps/seed/generators/images.py
  and apps/seed/tests/test_seed.py are both CLEAN. Never stage anything else.

files:
  - path: src/backend/apps/seed/generators/images.py
    targets:
      - type: class
        name: ImageGenerator
      - type: method
        name: _preprocess_one
      - type: method
        name: generate
      - type: method
        name: _preprocess_images
      - type: method
        name: _thumbnail_key
    semantic_anchors:
      insert_before:
        type: return_statement
        scope: ImageGenerator._preprocess_one

  - path: src/backend/apps/seed/tests/test_seed.py
    targets:
      - type: class
        name: TestImageGenerator
    semantic_anchors:
      insert_after:
        type: class
        name: TestImageGenerator

  - path: src/backend/apps/seed/fixtures/images/photo_manifest.json
    targets:
      - type: constant
        name: default.photos
    semantic_anchors: []
    note: >
      READ-ONLY. Asserted by a new test only. Never edited, never populated.

changes:

  - action: modify
    description: >
      Add one private predicate on ImageGenerator that reports whether all three
      thumbnail variants for a storage key exist in seed_dir, and use it as BOTH
      the fast-path gate and the post-publish post-condition, so both branches are
      gated by the same check and a returned key is never a prediction. Derive the
      size set from ThumbnailSizeStrEnum — do NOT hard-code
      ("small","medium","large"), and do NOT import _SIZE_COLUMNS from the
      backfill management command (private, wrong layering).
    code_hint: |
      def _thumbnails_present(self, storage_key: str, seed_dir: str) -> bool:
          """True when every thumbnail variant for *storage_key* exists on disk."""
          return all(
              os.path.exists(
                  os.path.join(seed_dir, self._thumbnail_name(storage_key, size))
              )
              for size in ThumbnailSizeStrEnum
          )

  - action: modify
    description: >
      ImageGenerator._preprocess_one — the truthfulness fix. Change the return type
      from bool to dict[ThumbnailSizeStrEnum, str] | None and its semantics from
      "I intended to write this" to "these keys have files behind them".

        1. Missing fixture -> log the existing warning and return None (unchanged
           behaviour, now expressed as None).
        2. Read the fixture, strip_photo_exif, write the original (UNCHANGED).
        3. If _thumbnails_present(...) -> return the mapping built from
           _thumbnail_key for each ThumbnailSizeStrEnum, WITHOUT calling the
           service. This is the extended cache check and it preserves the
           within-run encode fast path.
        4. Otherwise call
           thumbnail_service.generate_thumbnails(img_bytes, filename, mode=WriteMode.REPLACE).
           The mode MUST be explicit: the default CREATE_ONLY raises
           FileExistsError on the first present variant and aborts before reaching
           the missing one. Verify the service returned one key per member of
           ThumbnailSizeStrEnum (the size-set agreement check), then re-run
           _thumbnails_present as the post-condition. If it fails, log at ERROR
           and return None.
        5. Return the mapping built from _thumbnail_key, or None.

      DELETE the `except FileExistsError: logger.warning("Thumbnails already
      exist ...")` swallow. Under REPLACE it is unreachable (os.replace never
      raises FileExistsError), and it is the mechanism that converts a failed
      publish into a "success". Do NOT add a replacement broad catch: ValueError
      and OSError must propagate, as they already do on the non-cached path.

      _thumbnail_key is consumed, not changed.
    code_hint: |
      published = thumbnail_service.generate_thumbnails(
          img_bytes, filename, mode=WriteMode.REPLACE
      )
      if set(published) != set(ThumbnailSizeStrEnum):
          logger.error("Thumbnail size set mismatch for %s", filename)
          return None
      if not self._thumbnails_present(storage_key, seed_dir):
          logger.error("Thumbnails missing after publish for %s", filename)
          return None
      return {
          size: self._thumbnail_key(storage_key, size.value)
          for size in ThumbnailSizeStrEnum
      }

  - action: modify
    description: >
      ImageGenerator.generate — build the three thumbnail_* columns from the
      mapping _preprocess_one returns instead of from _thumbnail_key, so the row
      carries what the generator verified.

        - Change the guard from `if not self._preprocess_one(...): continue` to
          `published = self._preprocess_one(...)` / `if published is None: continue`.
          The skip path is the EXISTING continue and its effect on positions is
          unchanged.
        - Assign thumbnail_small/medium/large by indexing the mapping with
          ThumbnailSizeStrEnum.SMALL/MEDIUM/LARGE. Three explicit keywords — no
          setattr, no dict of column-name strings (project rule 10).
        - position is UNCHANGED: still enumerate(selected, start=1), still
          computed before the skip decision. Do NOT renumber, compact, or
          re-sequence positions. Gaps are legal and contiguity is deliberately
          unenforced under uq_ad_images_ad_position.
        - Do NOT touch the category_key_map construction, _find_category_keys,
          _ensure_seed_dir, or the ThumbnailService construction.
    code_hint: |
      for position, key in enumerate(selected, start=1):
          published = self._preprocess_one(key, seed_dir, thumbnail_service)
          if published is None:
              continue
          ad_images.append(AdImage(
              ad=ad,
              image=key,
              position=position,
              thumbnail_small=published[ThumbnailSizeStrEnum.SMALL],
              thumbnail_medium=published[ThumbnailSizeStrEnum.MEDIUM],
              thumbnail_large=published[ThumbnailSizeStrEnum.LARGE],
          ))

  - action: modify
    description: >
      ImageGenerator._preprocess_images (eager, deprecated) — DELEGATE. Keep its
      public return type list[str] (it has no callers anywhere in the tree; changing
      it would be gratuitous churn), but derive membership from the new contract:
      append the storage key when _preprocess_one returns non-None. Do NOT use a
      bare truthiness test — an empty/falsy check against a dict is an accident,
      not a contract, and this is the call site that would silently drift.
      Update its docstring to state the delegation and that it shares the lazy
      path's verified-files contract.
    code_hint: |
      for entry in manifest_entries:
          storage_key = f"seed/{entry['filename']}"
          if self._preprocess_one(storage_key, seed_dir, thumbnail_service) is not None:
              keys.append(storage_key)

  - action: add_code
    description: >
      Tests in src/backend/apps/seed/tests/test_seed.py. Mark every test that
      performs a real encode with @pytest.mark.seed (they are covered by the
      mandatory full-suite gate; they will not run under Makefile.ps1 test). The
      C-1 manifest tripwire needs no DB and no encode, so mark it @pytest.mark.unit
      so it runs in the fast gate.

      Prefer isolation over the shipped test's technique: the shipped
      test_generates_ad_images writes 1004 dummy JPEGs into the real fixtures dir.
      Do not copy that. Use monkeypatch.setattr("apps.seed.generators.images.FIXTURES_IMAGES_DIR", tmp_path)
      with a small hand-written photo_manifest.json and tmp_path for MEDIA_ROOT —
      images.py reads FIXTURES_IMAGES_DIR as a module global inside _load_manifest
      and _preprocess_one, so patching the module attribute covers both.

      Add to TestImageGenerator (reusing its existing autouse _setup_class ad, which
      already passes a literal status= to create_test_ad):

      1. Truthfulness (required test 1) — after generate(), every thumbnail_*
         value on EVERY returned AdImage is non-null AND
         (MEDIA_ROOT / key).exists(). Iterate all three columns on all rows.
      2. Half-written state (required test 2, the OC-3 tripwire) — write the
         original and -small only, delete -medium and -large, then call
         generate(); assert the returned mapping names all three, that medium and
         large now exist, and that the row's columns match. Fails if the
         single-variant check is left in place.
      3. C-1 manifest tripwire (required test 3) — read the SHIPPED
         photo_manifest.json and assert default.photos == [] (the empty default
         pool) and that the manifest has 205 categories; then reconcile the
         created rows against the manifest and the filesystem: every image key
         maps to a manifest fixture that exists and every thumbnail_* to an
         existing file. Do NOT run the generator over all 1004 photos — bound it.
      4. Eager contract (required test 4) — call _preprocess_images with a small
         explicit manifest_entries list; assert it returns the key for a photo
         whose files exist, omits a key whose fixture is missing, and that every
         returned key has all three variants on disk.
      5. Fast path preserved (OC-3) — with all three variants present,
         _preprocess_one returns a mapping and ThumbnailService.generate_thumbnails
         is NEVER called (patch the method and assert not called). This is what
         distinguishes EXTEND from DROP and stops a later "simplification" from
         silently reintroducing the cost.
      6. Mode wiring (OC-3) — in the half-written state, assert the service was
         called with mode=WriteMode.REPLACE. Without this, the repair aborts on
         FileExistsError at the present -small and never reaches -medium.
      7. Failure is not swallowed — make generate_thumbnails raise (ValueError or
         OSError) and assert the exception PROPAGATES out of _preprocess_one;
         _preprocess_one must not return a truthy value.

      Every new create_test_ad / create_test_ads_bulk call must be status-grounded
      with a literal status= (the factory is create_test_ads_bulk, plural 'ads').
      apps/core/tests/test_ad_factory_contract.py walks the whole tree and fails
      the ENTIRE repository gate otherwise — even if the new test itself passes.

      DO NOT write a test for _backfill_image_hashes surviving a NULL thumbnail —
      it has no subject. DO NOT edit or weaken
      TestImageGenerator::test_seed_original_strips_jpeg_comment; it passes
      unchanged.
    code_hint: |
      @pytest.mark.seed
      def test_half_written_state_is_repaired(self, tmp_path) -> None:
          # original + -small on disk, -medium / -large absent
          published = gen._preprocess_one(storage_key, seed_dir, service)
          assert published is not None
          assert set(published) == set(ThumbnailSizeStrEnum)
          for key in published.values():
              assert (tmp_path / key).exists()

acceptance_criteria:
  - After ImageGenerator.generate, every thumbnail_* value on every created AdImage is non-null and points at a file that exists
  - A half-written state (small present, medium or large missing) is repaired via WriteMode.REPLACE, never reported complete
  - The all-three-present fast path returns the mapping WITHOUT calling ThumbnailService.generate_thumbnails
  - The repair path passes mode=WriteMode.REPLACE explicitly; the mode kwarg is asserted by a test
  - The except FileExistsError swallow is gone; a failing publish propagates instead of returning a truthy value
  - ImageGenerator._preprocess_images delegates to _preprocess_one and tests membership with `is not None`
  - position is NOT renumbered; no position compaction, no contiguity enforcement; existing gap behaviour preserved
  - AdImage.objects.bulk_create stays; no per-row save() loop, no post-bulk_create repair pass, no AdImage.save() override
  - photo_manifest.json is unmodified; a test asserts default.photos == []
  - src/backend/apps/seed/services/seed_service.py unmodified
  - No migration, no schema change, no new setting, no new module
  - Every new create_test_ad / create_test_ads_bulk call passes a literal status=
  - apps/core/tests/test_ad_factory_contract.py green
  - TestImageGenerator::test_seed_original_strips_jpeg_comment passes UNCHANGED (project rule 2 not invoked)
  - Gate green, in order:
      $dc run --rm -e PYTEST_OPTS="src/backend/apps/seed/tests src/backend/apps/media/tests/test_sweep_orphaned_media.py --tb=short" test
      $dc run --rm test
      .\Makefile.ps1 test
      uv run ruff check src/
      uv run basedpyright src/
  - Committed with explicit paths only (never -A, never ., never a directory)
```

**Do not touch (binding).** `AdImage.objects.bulk_create` (stays) · `apps/ads/models.py` (`uq_ad_images_ad_position`, `storage_keys`) · `apps/media/management/commands/sweep_orphaned_media.py` · `src/backend/conftest.py` · `apps/media/services/references.py` · `apps/media/services/filesystem.py` (incl. `strip_photo_exif`) · `apps/media/signals.py` · `apps/media/schemas.py` · `apps/media/services/thumbnails.py` (BLOCK 3's landed file — consume `WriteMode`, do not edit) · `apps/seed/services/seed_service.py` · `apps/seed/tests/conftest.py` · `photo_manifest.json` · `docs/**` · `.ai/**`.

**Commit (only when explicitly instructed; one commit, explicit paths).**
```
git add src/backend/apps/seed/generators/images.py src/backend/apps/seed/tests/test_seed.py
git commit
```
Message:
```
fix(seed): assert the thumbnails the seed generator wrote
```
Body, in this order:
1. The corrected truthfulness gap: `_preprocess_one` short-circuited on a single `-small` and returned `True` **before** calling the service, so a half-written state was reported complete and `bulk_create` inserted rows pointing at files that were never written.
2. **OC-3 = EXTEND**, with the reason: the check becomes all-three-variants; "drop" is unavailable because BLOCK 3's guard (`_decide_write_mode`) decides from `AdImage` **columns** and the seed path has **no row** at preprocessing time, and because `CREATE_ONLY` aborts the `SMALL → MEDIUM → LARGE` loop on the first present target. The repair path therefore publishes with `WriteMode.REPLACE` — the mode value BLOCK 3 recorded for this block. Note `SeedService._clean()` rmtree's the seed dir per run, so the fast path's only live value is within-run dedup; it is preserved because the check is now a verified post-condition as well as a skip gate.
3. The three falsified plan premises: the `_backfill_image_hashes` NULL-thumbnail test has **no subject** (`seed_service` reads only `img.image`); position gaps are **not** a defect (pre-existing, contiguity deliberately unenforced under `uq_ad_images_ad_position`, and this change does not renumber); the default-pool narrative is wrong.
4. **C-1**: `photo_manifest.json`'s `default.photos` is `{"photos":[]}` — empty, so the default-pool injection loop is inert and cross-category sharing does not occur. The manifest is asserted, never edited.
5. The position-gap non-issue, stated as a deliberate non-change.
6. **No shipped test was treated under project rule 2.** `test_seed_original_strips_jpeg_comment` asserts only the truthiness of `_preprocess_one`'s return, and a non-empty `dict` is truthy; it passes unchanged. (It is `@pytest.mark.seed`, which is why this block's full-suite gate is mandatory.)

```yaml
id: verify_task_07m05_seed_thumbnail_truthfulness

title: Verify — Assert only the seed thumbnails the generator actually wrote

type: verification

status: pending

depends_on:
  - task_07m05_seed_thumbnail_truthfulness

verifies:
  - task_07m05_seed_thumbnail_truthfulness

verification_steps:
  - build: uv run ruff check src/
  - typecheck: uv run basedpyright src/
  - test: $dc run --rm -e PYTEST_OPTS="src/backend/apps/seed/tests src/backend/apps/media/tests/test_sweep_orphaned_media.py --tb=short" test
  - full_suite: $dc run --rm test
  - fast_gate: .\Makefile.ps1 test
  - smoke_check: >
      Read apps/seed/generators/images.py and confirm, by symbol and not by line
      number: (a) `_preprocess_one` no longer contains any `except FileExistsError`
      that returns truthy; (b) its annotation is a mapping-or-None and the
      generator builds the three `thumbnail_*` columns by indexing that mapping
      with `ThumbnailSizeStrEnum`, not by calling `_thumbnail_key` inside
      `generate`; (c) exactly one call site passes `mode=` to
      `generate_thumbnails` and it is `WriteMode.REPLACE`; (d)
      `_preprocess_images` filters on `is not None`; (e) `position` still comes
      from `enumerate(selected, start=1)` and no compaction was introduced;
      (f) `AdImage.objects.bulk_create` and `apps/seed/services/seed_service.py`
      are byte-identical to `3544e4b`; (g) `photo_manifest.json` is byte-identical
      to `3544e4b`.
  - diff_scope: >
      git diff --stat 3544e4b..HEAD — must list ONLY
      src/backend/apps/seed/generators/images.py and
      src/backend/apps/seed/tests/test_seed.py. Any other path is another agent's
      work or a scope error.
  - negatives: >
      Confirm the fast path still calls generate_thumbnails ZERO times when all
      three variants exist, and that the repair path calls it with REPLACE and
      reaches -medium after -small is present. If the repair path can abort on
      FileExistsError, the defect is only relocated.

pass_criteria:
  - ruff exits 0
  - basedpyright reports no NEW error — the baseline is 3 pre-existing errors in apps/search/tests/test_immediate_alerts.py and apps/users/tests/test_login.py, not 0
  - the targeted seed + sweep run is green
  - the FULL suite including the `seed` marker is green (mandatory; the only block that requires it)
  - .\Makefile.ps1 test is green
  - every smoke_check and diff_scope assertion holds
  - the commit staged exactly two files by explicit path, with the prescribed subject line
  - every red observation was re-run SERIALLY before being reported; a wall of setup errors (DuplicateDatabase, ObjectInUse, DeadlockDetected) is another agent's concurrent run, not a defect
  - test_search_slo is not in this gate (known environmental flake under host load)

failure_action: return task_07m05_seed_thumbnail_truthfulness to rework

rollback_task: none — reverting the generator restores the pre-block defect; already-seeded rows keep their gaps and recovery is an operator reseed, never a migration
```

---

## BLOCK 6 — Dangling-row reconciliation + truthful deletion counter

**Findings owned.** `07-MEDIA-012`, plus `03-DB-005`'s second correction (`deleted += 1`) and the §4.7 store↔database assertion.
**Depends on.** Nothing in-plan. **The phase-03 external gate is SATISFIED.** **Risk.** HIGH — the command deletes files.

**Drift note — the largest change from the source plan.** Phase-03 BLOCK 6 and BLOCK 8 have **both LANDED**. The plan's "wait for phase 03" step is **void** and there is **no longer any contention** on this file. The command is already registered in `SWEEP_COMMANDS`, `EXPECTED_SWEEP_COMMANDS` and `_LOCK_TARGET_MODULES` — **all three are left untouched**, and BLOCK 6 adds **no** lock id.

**Required agents.**
- **Auditor** — re-verify the walk/collect asymmetry and the counting path against the shipped command, and confirm the phase-03 reservation is genuinely released.
- **Researcher** — **not required.** No best-practices or architectural-support question remains; Q07-9 is resolved by plan §0.6.2.
- **Planner** — required: the report mode's scope, the exit-code contract, and **OC-4** (how a confirmed-deletion signal is obtained without breaking the existing monkeypatch stubs).
- **Implementor** — land the check mode and the counter fix.
- **Validator** — mandatory: the negative proof (`media_gate` untouched) is the single most important assertion in the plan and must be independently verified.

**What is wrong.** `sweep_orphaned_media.Command` supports `--dry-run` **only** — no `--check`, no report mode, no exit code. The revenue half of the same diff the sweep performs — detecting a row whose file is **missing** — therefore exists nowhere, leaving an unbounded silent failure with no observable signal. Second, the deletion loop is `for key in sorted(orphans): delete_photo(key); deleted += 1`, but `delete_photo` returns `None` and swallows failures, so **every attempt counts** — including `FileNotFoundError` (terminal, returns early) and retry exhaustion. The success line "Deleted N orphaned media files" is **not a measurement**. Third, and decisive for design: a report computed as `referenced - on_disk` is a **guaranteed false positive on `seed/`**, because `_walk_media_files` skips `seed/` while `_collect_referenced_keys` does not — **every** seed key would be flagged. The reconciliation must **include `seed/`**. Fourth, `_reclaim_stale_staging` uses bare `os.remove`, bypassing `delete_photo`'s retry and its `MediaDeletionError` path — a second, unreconciled deletion route. (Its own `reclaimed` count **is** accurate, because it increments only after a successful `os.remove`; the miscount is specific to the orphan loop.)

**Negative proof is mandatory.** `media_gate` must still return `200` + `X-Accel-Redirect` for a shared key with **no file on disk**. No filesystem check may be added to the serving path. Note that the `vary_on_headers` / `Cache-Control` change means a dangling key now returns `200` + `X-Accel-Redirect` + `no-store` — the row is cheaper to detect and no less costly to serve. Detection belongs in the sweep, never in the view.

**Surface (semantic units only).**
- `apps/media/management/commands/sweep_orphaned_media.py::Command.add_arguments` — the check/report mode alongside `--dry-run`
- `apps/media/management/commands/sweep_orphaned_media.py::Command.handle` — the report path and the corrected counter
- `apps/media/management/commands/sweep_orphaned_media.py::_walk_media_files` — reconciliation scope **including `seed/`**
- `apps/media/management/commands/sweep_orphaned_media.py::_collect_referenced_keys` — consumed, not changed
- `apps/media/management/commands/sweep_orphaned_media.py::_reclaim_stale_staging` — read-only for this block
- `src/backend/apps/media/tests/test_sweep_orphaned_media.py` — extend
- `src/backend/apps/media/tests/test_media_security.py` — the negative proof

**Binding constraints.**
1. **No filesystem check, no `FileResponse`, no cache-header change in `media_gate`.** `media_gate` is otherwise byte-identical.
2. The reconciliation scope **includes `seed/`** (plan §0.6.2). Reusing `_walk_media_files`' skip as-is reproduces the exact defect `VAL-005` records.
3. `--check` **reuses** `AdvisoryLockId.SWEEP_ORPHANED_MEDIA` (**103**) — **no new lock id**. The report path exits via `CommandError` on a non-zero count so `cron`/monitoring observes it.
4. `--dry-run` and `--check` are **mutually exclusive**; both are non-destructive.
5. The command body stays inside the **existing** `transaction.atomic()` + advisory lock — `TestSweepLockScope::test_delete_photo_called_within_lock_scope` pins it.
6. `_STAGING_TTL_SECONDS` is **unchanged**, and `_reclaim_stale_staging`'s **deletion** scope is **unchanged**.
7. The counter fix asserts **behaviour**, not the log string. No test may pin the string; the number becoming *true* is the point.
8. **OC-4 stays open — the Implementor's Planner decides.** Obtaining a confirmed-deletion signal must not break the existing tests that monkeypatch `delete_photo` with a stub returning `None`. Whatever mechanism ships is recorded in the commit body.
9. The bare-`os.remove` divergence in `_reclaim_stale_staging` is **recorded in the commit body and routed to phase 12**, not fixed here.
10. `SWEEP_COMMANDS`, `EXPECTED_SWEEP_COMMANDS` and `_LOCK_TARGET_MODULES` are **not** edited by this block.

**Required tests** (logic + component interaction).
1. The check mode **reports** a row whose file is gone, and **reports nothing** when the store and the database agree — with the recorded scope **including `seed/`**. *Test 1 is the tripwire: it fails if the scope excludes `seed/`.*
2. **Negative proof (mandatory).** `media_gate` still returns `200` + `X-Accel-Redirect` for a shared key with **no file on disk**.
3. The reported deletion count equals the number of files **actually removed** — a `FileNotFoundError` attempt and a retry-exhaustion attempt are not counted as deletions.
4. `--dry-run` and `--check` are mutually exclusive and both non-destructive.
5. The store↔database assertion finds **zero** dangling rows and **zero** orphan files, `seed/` **included**.
6. All **nine** existing tests across `TestSweepOrphanedMedia` and `TestSweepLockScope` pass **unchanged**.

**Keep green / do not edit.**
All nine tests in `test_sweep_orphaned_media.py` · `src/backend/apps/ads/tests/test_media_security.py` · `apps/ads/views/media.py` (does not exist) · `delete_photo`'s signature and never-raise contract · `AdvisoryLockId` · `test_sweep_lock_structure.py`'s three lists · `_STAGING_TTL_SECONDS` · `src/backend/conftest.py`.

**Gate (exact).**
```
$dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/media/tests/test_sweep_orphaned_media.py src/backend/apps/ads/tests/test_media_security.py src/backend/apps/media/tests/test_media_config.py --tb=short" test
.\Makefile.ps1 test
uv run ruff check src/
uv run basedpyright src/
```

**Risk and rollback.** The command **deletes files**; rollback is revert-the-code and **deleted files do not return**. The report mode is the safe surface and lands in the same commit. Contention risk is now **low** — the file is clean and phase 03 is finished, so the plan's "merge conflict on `Command.handle`" risk is retired.

---

---

## BLOCK 7 — Staging byte budget

**Findings owned.** `07-MEDIA-007`.
**Depends on.** BLOCK 6 (file edge only — supplies the bounded byte source; the phase-03 gate is void). **Risk.** MEDIUM — a new rejection branch on a **live** user path.

**Required agents.**
- **Auditor** — re-verify `process_photos`' exact ordering and that `save_photo` is the last byte-writing step, so the check lands in the only correct position.
- **Researcher** — budget-sizing methodology (what volume is legitimate concurrent in-flight traffic, what an abusive account accumulates per TTL window) and the Prometheus multiprocess-gauge semantics behind Q07-8.
- **Planner** — placement of the check, the bounded-cost mechanism, and the fairness wording.
- **Implementor** — land the setting, the check, the translated refusal, and the reading.
- **Validator** — mandatory: a new refusal on the seller path with an i18n gate and an inherently unfair global cap.

**What is wrong.** Nothing bounds the volume of `MEDIA_ROOT/staging/`. `ImageGenerator`… rather, the bot's `process_photos` runs **5-photo cap → `check_upload_rate_limit` → `MAX_PHOTO_BYTES` → `save_photo` → `state.update_data`** and contains **no budget check anywhere**. An abusive account can therefore accumulate staged bytes until the media volume is full, at which point **every** seller on the platform fails to publish — an availability failure caused by one account. Because the staging key is `f"{uuid.uuid4()}.jpg"` it is deliberately **PII-free**, so per-seller attribution is infeasible without a key-format change that would break the unguessability rationale and every key `CheckConstraint`. The control is therefore necessarily **global**.

**Q07-8 CONFIRMED — the gauge does not ship.** `PROMETHEUS_MULTIPROC_DIR` and the tmpfs `/tmp/prometheus_multiproc` are set **only on the `web`** service. The `scheduler` exists only in the prod profile and its env has no such variable; `bot` has no `/metrics`. A gauge written only by the hourly sweep is therefore **structurally unexportable**. Ship a **log-based reading** instead, and record in the commit body that the metric was deliberately **not** emitted and why — so phase 12 does not plan an alert on a signal nobody can produce.

**Surface (semantic units only).**
- `src/backend/config/settings/base.py` — **new** setting appended beside `MEDIA_ROOT` / `MEDIA_URL`
- `src/telegram_bot/handlers/ad_data/photos.py::process_photos` — the budget check
- `src/telegram_bot/services/ad_data/media.py` — `MAX_PHOTO_BYTES`, `save_photo`, `touch_staging_photos` (consumed, **not** changed; this is the post-`9e11eba` home, **not** `ad_create/`)
- `apps/media/services/filesystem.py` — `STAGING_SUBDIR` / `STAGING_PREFIX` (**there is no `paths.py`**)
- `apps/media/management/commands/sweep_orphaned_media.py` — supplies the bounded byte source
- `src/backend/locale/{ru,bs,en}/LC_MESSAGES/django.po` — **appended** only

**Binding constraints.**
1. The check is **bounded**. Do **not** walk the staging tree per upload. Prefer a `staging_bytes` figure the sweep already computes and the upload path **reads**; a `os.scandir` over the top level is the fallback and must be O(entries), never O(depth).
2. The check runs **before** `save_photo` — a refused upload writes **no file**.
3. The budget is **global**, and the fairness cost is **accepted and documented**: a legitimate seller can be refused because an abusive account filled the volume. The commit body states this.
4. `MAX_PHOTO_BYTES`, `save_photo` and `touch_staging_photos` are **unchanged**.
5. `_STAGING_TTL_SECONDS` is **unchanged** and the sweep's **exclusion** set is **unchanged** — the TTL stays the backstop, the budget is the primary control.
6. **No Prometheus gauge ships.** A log-based reading is emitted instead, with the Q07-8 rationale in the commit body.
7. The setting is a **named Django setting** (project rule 10), not an inline literal, and is **appended** to `base.py` beside `MEDIA_ROOT` — re-read `base.py` immediately before editing even though it is clean at `b7ba213`.
8. i18n is part of the DoD: the refusal message resolves with **non-empty `ru` and `bs`**, and is **appended** to the `.po` files. All three are dirty with ~1620 uncommitted lines from other phases — a wholesale `makemessages` would destroy them and is **forbidden**. Use the project append sequence (see `docs/99-agent/commands.md`); never `--no-location`-regenerate.
9. No migration, no key-format change, no new module in `apps/media/services/`.
10. The budget check does **not** alter the FSM's photo list or the 5-photo cap.

**Required tests** (logic + component interaction).
1. An upload **above** the budget is refused with a message that resolves in `ru` **and** `bs`.
2. An upload **under** the budget is **accepted** — the positive case is tested explicitly, not only the rejection.
3. A refused upload writes **no file** and consumes no key.
4. A fresh staging file is **preserved** and a stale one is **reclaimed** by the existing TTL — proving the budget did not replace the backstop.
5. `_STAGING_TTL_SECONDS` is **byte-identical** to before.
6. The cost assertion: the per-upload check does not scale with staging depth (assert the mechanism, not a wall-clock number).

**Keep green / do not edit.**
`src/backend/apps/media/tests/test_sweep_orphaned_media.py` (all nine) · `src/telegram_bot/tests/` media handlers · `_STAGING_TTL_SECONDS` · the sweep's exclusion set · `MAX_PHOTO_BYTES` / `save_photo` / `touch_staging_photos` signatures · `src/backend/conftest.py` · the ~1620 uncommitted locale lines from other phases.

**Gate (exact).**
```
$dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/ads/tests/test_i18n_completeness.py src/backend/apps/media/tests/test_sweep_orphaned_media.py src/telegram_bot/tests --tb=short" test
.\Makefile.ps1 test
uv run ruff check src/
uv run basedpyright src/
```

**Risk and rollback.** The fairness cost (constraint 3) is the accepted trade-off of a global budget and is **MEDIUM, accepted**. Rollback = remove the check and the setting; **staged files already written stay** and the TTL continues to reclaim them, so the failure mode reverts to the pre-block one rather than worsening. No lock id, no migration.

---

## BLOCK 8 — Deletion-error reader + retention

**Findings owned.** `07-MEDIA-010`, plus the `ME-003` traceability reconcile.
**Depends on.** Nothing in-plan. **Risk.** MEDIUM — introduces an **irreversible** purge.

**Required agents.**
- **Auditor** — re-read `AdvisoryLockId` and the allocation docstring at the **moment of allocation**, and confirm the stale `0003` migration artefact is harmless via `makemigrations --check`.
- **Researcher** — retention-semantics evidence for a diagnostic table (what an operator needs to see, and for how long), to underwrite the TTL.
- **Planner** — required: **OC-5** (`HOURLY_COMMANDS` vs `DAILY_COMMANDS` — the source plan contradicts itself) and the retention command's contract.
- **Implementor** — land the admin reader, the retention command, and the three-file lock allocation in **one** commit.
- **Validator** — mandatory: the purge is irreversible and the lock id is allocated from a band shared with phase 06.

**What is wrong.** `MediaDeletionError` rows are written by `delete_photo`'s failure path and are reachable **nowhere** — `apps/media/admin.py` does **not** exist. A `MediaDeletionError` therefore means "a file we could not delete" with **no operator surface**: the condition is invisible until someone reads the table by hand. There is also no retention, so the table grows without bound under a persistent condition. `models.py`'s opening line cites an unresolvable prior-cycle id `ME-003`, so the finding that motivates the model cannot be traced.

**Q07-10 ANSWERED: NO.** The only `admin.site` usages in the tree are two `is_registered` calls in `apps/core/tests/test_support_admin.py`. Nothing asserts the exact registry set, so registration is **purely additive** and **no test needs updating**.

**Surface (semantic units only).**
- **new** `apps/media/admin.py` — `MediaDeletionErrorAdmin`, `readonly_fields = []`, `list_display` / `list_filter` on `created_at` and `error_type`
- **new** `apps/media/management/commands/purge_media_deletion_errors.py` — retention, `--older-than` and `--dry-run`
- `apps/media/models.py` — the `ME-003` traceability reconcile only
- `apps/core/enums.py::AdvisoryLockId` — the new member
- `apps/core/utils/advisory_lock.py` — the allocation docstring's table
- `apps/core/tests/test_advisory_lock_ids.py`
- `apps/core/tests/test_sweep_lock_structure.py` — **three** lists, not two
- `apps/core/utils/scheduler.py` — the dispatch entry (**per OC-5**)

**Binding constraints.**
1. **The coordinator is told BEFORE `enums.py` is touched.** Phase 06 BLOCK 15 allocates from the same band.
2. **Next free id is `14`** — confirmed at `b7ba213` and corroborated by the allocation docstring ("IDs 14-99 are reserved for future scheduled jobs"). **Re-read at the allocation moment**; `test_advisory_lock_ids.py` does **not** catch reuse.
3. **Three files, one commit:** `apps/core/enums.py`, the allocation table in `advisory_lock.py`'s docstring, `test_advisory_lock_ids.py`. Then the **separate** `test_sweep_lock_structure.py` edit touches **three** lists — `SWEEP_COMMANDS`, `EXPECTED_SWEEP_COMMANDS` (an **exact `frozenset`** asserted by the test) and `_LOCK_TARGET_MODULES`.
4. `AdvisoryLockId.SWEEP_ORPHANED_MEDIA == 103` is **unchanged**; `CONSENT_HARD_DELETE == 3` is **not** renumbered.
5. `_record_deletion_error` **keeps swallowing its own errors** — a failure to record a failure must never propagate into a delete path.
6. `delete_photo`'s three-attempt backoff, its `logger.error` and its **never-raise** contract are **unchanged**.
7. The admin reader has **no editable field**. New `AdvisoryLockId` members are named per project rule 10; **no bare prior-cycle id** is introduced — use `07-MEDIA-010`.
8. `--dry-run` is **mandatory** and deletes nothing. A row **inside** the TTL survives with its message intact.
9. **No alerting ships.** The phase-12 predicate `MediaDeletionError.objects.filter(created_at__gt=now() - 1h).exists()` is **recorded in the commit body** so phase 12 can consume it.
10. **OC-5 stays open** — the Implementor's Planner decides `HOURLY_COMMANDS` vs `DAILY_COMMANDS` and records it. Note `_validate_commands` does **not** raise on a missing entry, so a forgotten dispatch fails silently.
11. `makemigrations --check` is **clean before starting** — a stale `0003_mediadeletionerror_uq_media_deletion_error_key_type.cpython-314.pyc` exists with no matching `.py`. **No migration is created by this block**; a pending migration is a scope error.
12. All new admin strings are **appended** to the locale files with non-empty `ru` and `bs`.

**Required tests** (logic + component interaction).
1. `MediaDeletionError` is reachable through the admin changelist with `created_at` and `error_type` filters and **no** editable field — verified by `get_form(request)` introspection, not source reading.
2. `--dry-run` deletes nothing.
3. A row **inside** the TTL survives with its message intact; a row **past** it is deleted.
4. A second run is a **no-op**.
5. The scheduler still starts, and `_validate_commands` passes.
6. The new id is **not** a reuse and `SWEEP_ORPHANED_MEDIA == 103` still holds.
7. `_record_deletion_error` still swallows a DB failure (component interaction with `delete_photo`).

**Keep green / do not edit.**
`src/backend/apps/core/tests/test_sweep_lock_structure.py`'s existing entries · `test_advisory_lock_ids.py`'s existing ids · `delete_photo` · `_record_deletion_error` · `AdAdmin`'s field set and permission predicates · `src/backend/conftest.py` · the uncommitted locale lines.

**Gate (exact).**
```
$dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/core/tests/test_advisory_lock_ids.py src/backend/apps/core/tests/test_sweep_lock_structure.py src/backend/apps/core/tests/test_scheduler_wiring.py src/backend/apps/media/tests/test_filesystem.py --tb=short" test
.\Makefile.ps1 test
uv run ruff check src/
uv run basedpyright src/
```

**Risk and rollback.** **Irreversible.** A revert of the retention command does **not** restore purged rows. Rollback = stop scheduling the command; already-purged rows stay purged. `--dry-run` first is mandatory operational practice and is stated in the commit body. Retention is index-backed (`created_at` and `error_type` are both indexed), so the plan's "seq-scans an unbounded table" argument does **not** apply to this query.

### Planner task — BLOCK 8 execution plan

> **Template decision (recorded).** BLOCK 8 ships an **irreversible** purge and allocates a lock id from a band a second phase is also allocating from, and the block's own agent list mandates "**Validator — mandatory**". The **verification** variant is therefore emitted **in addition to** the primary `task_template.yaml` shape.

#### Ground truth settled by this Planner (do not re-derive)

| Question | Answer | Evidence |
|---|---|---|
| **OC-5 — `HOURLY_COMMANDS` or `DAILY_COMMANDS`?** | **`HOURLY_COMMANDS`, appended LAST** | see "OC-5 decision" below |
| **Next free `AdvisoryLockId`?** | **`15`** | `enums.py` at `81dd644` holds `1-9, 11, 12, 13, 14, 100, 101, 102, 103, 104, 110, 111`. `CONSENT_RECORD_SWEEP = 14` (`fd5201d`) consumed the id the plan still calls free. `15` is free — verified by reading the live enum, **not** the plan |
| **`makemigrations --check` before starting?** | **CLEAN** | run this Planner: `docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml run --rm --no-deps --entrypoint "" -e DJANGO_SETTINGS_MODULE=config.settings.test_migrations test python src/backend/manage.py makemigrations --check --dry-run` → **`No changes detected`**. The orphan `.pyc` artefacts (`0002_dedup_media_deletion_errors`, `0003_mediadeletionerror_uq_media_deletion_error_key_type`) have no `.py` and are inert; `MIGRATION_MODULES = DisableMigrations()` under `config.settings.test` is why a plain check would have lied |
| **`apps.media` admin autodiscovery?** | **Works** | `config/settings/base.py::INSTALLED_APPS` contains `apps.media`; `AdminConfig.autodiscover_modules()` imports `apps/media/admin.py` with no further wiring |
| **Staff/admin fixture for the reader tests?** | **None exists** — build one locally | `src/backend/conftest.py` has `make_user(telegram_id, *, is_staff=False, consent_revoked=False)` and **no** staff/permission fixture, and `conftest.py` is do-not-touch. Mirror `apps/core/tests/test_support_admin.py::_local_staff_user` + `_local_changelist_request` |

**🔴 Three corrections to the block text above, made by this Planner.**

1. **"Next free id is `14`" is stale.** It says "confirmed at `b7ba213`"; phase 06's `fd5201d` has since taken **14** as `CONSENT_RECORD_SWEEP`. The verified value is **15**. The block's own constraint 2 ("re-read at the allocation moment") remains binding — `15` is what the live file says **today**, and the Implementor must re-read once more immediately before editing.
2. **Constraint 12 ("all new admin strings are appended to the locale files") is VACUOUS — do not touch `django.po`.** `list_display` / `list_filter` entries name **model fields**, so Django derives their labels from auto-generated `verbose_name`s (`"created_at" → "created at"`, `"error_type" → "error type"`) which are **not** `gettext`-wrapped. If the admin declares no `verbose_name`, no `short_description`, and no `changelist_view` template override, it introduces **zero translatable strings** and the `ru` / `bs` completeness gate is unaffected. The uncommitted locale lines belong to other agents and stay untouched.
3. **A file missing from the Surface list must be edited: `src/backend/apps/core/tests/test_scheduler.py`.** `TestSchedulerConstants::test_hourly_commands_match_spec` asserts `HOURLY_COMMANDS == [ …9 names… ]` and `test_daily_commands_include_send_alerts` asserts `DAILY_COMMANDS == [ …3 names… ]` — both **exact list equality**. Whichever list OC-5 picks, this file's pinned literal must gain the new name. This is the **same class** of pin as `EXPECTED_SWEEP_COMMANDS` and is committed with it.

#### OC-5 decision — `HOURLY_COMMANDS` (appended last)

The source plan contradicts itself: its surface table says `HOURLY_COMMANDS`, its correction register says `DAILY_COMMANDS`. **Decided: `HOURLY_COMMANDS`, appended at the END of the list.** Five reasons, in decisive order.

1. **Decisive — a daily command's exit code is load-bearing for the durable daily marker, and an hourly one is not.** `scheduler.run_one_cycle` calls `daily_marker.record_daily(day)` **only** when `daily_ok` (every daily command exited 0) **and** `_stop_event` is clear. A non-zero exit from any daily command leaves the day unrecorded, so the **entire** daily set is re-dispatched on the next hourly tick — bounded at ~16 attempts/day — re-sending search-alert digests (`send_alerts`) and re-running the analytics rollup. An hourly command's exit code touches only `_write_liveness_marker`. This block introduces an **irreversible** purge whose natural failure mode *is* a DB error, so putting it in the daily set would let a media-retention hiccup suppress `CONSENT_RECORD_SWEEP` for the rest of the day and spam sellers with duplicate alert digests. That blast radius is unacceptable and is a consequence of *placement alone*.
2. **Phase 06's precedent is not transferable — the precedent's own reasoning excludes this command.** `purge_consent_records` sits in `DAILY_COMMANDS` because it **never deletes** ("anonymises, never deletes", per its docstring) and "returns 0 on every non-exceptional outcome" — that sentence exists *precisely* so the daily marker is safe. `purge_media_deletion_errors` **does** delete, so it inherits the same coupling while losing the property that made the coupling harmless. "Follow the comparable purge" would copy the slot and invert the reason it was chosen.
3. **The "hourly clears diagnostics faster" argument is weak, and I do not claim it.** With a **30-day** TTL, hourly vs daily shifts the effective deletion instant by at most 24 h inside a 720 h window. The diagnostic window is set by the **TTL**, not the cadence. Neither cadence makes a fresh row disappear sooner.
4. **The per-run cost is negligible and the cadence is already this subsystem's habit.** The query is a single index-backed `DELETE … WHERE created_at < cutoff` on `idx_media_del_err_created` (the source plan's "seq-scans an unbounded table" argument does not apply), the command is idempotent, and 24 extra subprocess dispatches per day is the same shape as the nine existing hourly commands — including `sweep_orphaned_media`, **the very command whose failure path writes these rows**, whose own internal TTL is `_STAGING_TTL_SECONDS = 2h`. The media subsystem demonstrably runs on an hourly clock.
5. **Contention is EQUAL, so it does not break the tie — it only has to be recorded.** Both lists are pinned by exact equality in `test_scheduler.py` (see correction 3), and `DAILY_COMMANDS`'s leading comment was rewritten by phase 06 in `fd5201d`. So **yes** — DAILY would land in a list another phase also owns, and so does HOURLY; neither is exclusive. The tie is broken on blast radius alone (reason 1), not on file ownership.

**Consequences of choosing HOURLY, all binding.**
- **Append at the END. Never insert.** `apps/core/tests/test_scheduler_error_handling.py` indexes these lists **positionally** — `HOURLY_COMMANDS[0]`, `HOURLY_COMMANDS[2]` (×4), `DAILY_COMMANDS[0]` (×4), `DAILY_COMMANDS[1]` — and `apps/core/tests/test_scheduler.py` does the same. Appending at index 9 preserves indices 0-8 exactly. Inserting anywhere else is an unrequested edit to those tests.
- **The command must exit 0 on every non-exceptional outcome**, including an empty eligible set and `--dry-run`, so a routine no-op never ages the liveness marker into an `unhealthy` scheduler container. It must still raise on a genuine failure (a stale liveness marker is the correct signal there).
- `_validate_commands(HOURLY_COMMANDS + DAILY_COMMANDS)` runs in `run_scheduler` **before** the loop. It raises `CommandError` on an **unreachable** name, so a misspelled command is caught at start-up. ⚠ But it does **not** validate that a *listed* command is *dispatched* correctly beyond membership, and a **forgotten** dispatch entry (the command never added to the list) fails **silently** — `test_scheduler.py::test_hourly_commands_match_spec` is the only thing that catches it, which is why correction 3 is not optional.

#### Doc-drift routed out of BLOCK 8 (`docs/**` is do-not-touch here)

This block makes three documentation statements false. **Do not edit them.** Record each in the commit body and route:

| File | What goes stale | Route |
|---|---|---|
| `docs/01-spec/architecture-structure.md` — the hourly command list and the lock-id allocation table (row `15` is absent) | new hourly command + new lock id | **BLOCK 10** (already in its Surface) |
| `docs/ops/docker-deployment.md` — the scheduled-commands table | new hourly command | **BLOCK 10** (already in its Surface; append-only, file is dirty with another phase's edits) |
| `docs/02-database/db-retention.md` — the retention table, the command census, and the sentence *"All retention values are hardcoded in the respective management command source files. **No environment variables or CLI arguments (beyond `--dry-run`) are read for retention durations**"* | `--older-than` **is** a CLI argument that **is** a retention duration, so that sentence becomes **false** | ⚠ **UNROUTED.** BLOCK 10 constraint 9 says this file is "not touched". **Raise on the board to `main`; do not edit.** |

**Accepted residual in code.** `apps/media/services/filesystem.py::_record_deletion_error`'s docstring still cites the unresolvable `ME-003`. That file is do-not-touch for this block, so the id survives in one place. Recorded, not fixed.

```yaml
id: task_07m08_media_deletion_error_reader_and_retention

title: Add a read-only MediaDeletionError admin reader and a 30-day retention purge

priority: high

status: pending

depends_on: []          # nothing in-plan; phase 06's fd5201d only shifts the id band

source_reference: .ai\plans\20-media-remediation-execution.md
source_section: BLOCK 8 — Deletion-error reader + retention
source_blocks:
  - "BLOCK 8 — Deletion-error reader + retention"

description: >
  MediaDeletionError rows are written by delete_photo's failure path and are
  reachable nowhere — apps/media/admin.py does not exist, so "a file we could
  not delete" has no operator surface and the condition is invisible until
  someone reads the table by hand. There is also no retention, so the table grows
  unbounded under a persistent condition.

  Ship two new read-only surfaces and nothing else:

  1. apps/media/admin.py — MediaDeletionErrorAdmin, fully read-only
     (readonly_fields = [], has_add_permission False, has_change_permission
     False, no has_view_permission override so view access requires the
     media.view_mediadeletionerror permission AND staff status via
     AdminSite.has_permission). list_display and list_filter cover created_at
     and error_type; ordering is ("-created_at",) because the reader's primary
     use is "what failed recently" and the column is already indexed.
  2. apps/media/management/commands/purge_media_deletion_errors.py — bounded
     retention. --older-than takes DAYS and defaults to 30; --dry-run reports
     and deletes nothing. The command takes a transaction-scoped advisory lock
     inside transaction.atomic() on the production path (including the
     --dry-run path is NOT required — the branch happens after the lock, as in
     purge_consent_records), so the entry in test_sweep_lock_structure.py's
     three lists is satisfied.

  Also: allocate AdvisoryLockId.PURGE_MEDIA_DELETION_ERRORS = 15 (three files,
  one commit), append "purge_media_deletion_errors" to HOURLY_COMMANDS, pin the
  new name into the two exact-list test literals, and reconcile models.py's
  unresolvable (ME-003) traceability citation to the resolvable 07-MEDIA-010.

goals:
  - A staff user can open the MediaDeletionError changelist and filter by error_type and created_at
  - The reader exposes no editable field: Django refuses to build a change form for it at all
  - MediaDeletionError rows older than the TTL (30 days by default) are deleted; rows inside it survive with error_message intact
  - --dry-run deletes nothing and reports what it would remove
  - A second run is a no-op (idempotent)
  - The purge is serialised by its own transaction-scoped advisory lock (15), and the lock takes a value no other member holds
  - No alerting ships; the phase-12 predicate is recorded in the commit body instead
  - No migration, no new model field, no new index, no dependency, no new translatable string

extra_context: >
  Ground truth the Implementor must not re-derive:

  - VERIFIED LOCK ID = 15. apps/core/enums.py::AdvisoryLockId currently holds
    1,2,3,4,5,6,7,8,9,11,12,13,14,100,101,102,103,104,110,111. The plan's
    "next free id is 14" is STALE — phase 06's fd5201d allocated
    CONSENT_RECORD_SWEEP = 14. Re-read the live enum immediately before editing
    anyway: other agents commit in parallel and two phases computing "the next
    free integer" concurrently means one command silently never takes its lock.
    test_advisory_lock_ids.py does NOT catch reuse.
  - Reuse is INVISIBLE by default and must be asserted relationally. Assigning a
    value an existing member holds makes IntEnum create an ALIAS: the new
    attribute resolves, but its .name is the OLD member's name and
    list(AdvisoryLockId) does not grow. So assert
    AdvisoryLockId.PURGE_MEDIA_DELETION_ERRORS.name ==
    "PURGE_MEDIA_DELETION_ERRORS" (an alias flips this), and
    len({m.value for m in AdvisoryLockId}) == len(list(AdvisoryLockId))
    (no alias anywhere). Pin SWEEP_ORPHANED_MEDIA == 103 and
    CONSENT_HARD_DELETE == 3 as non-renumbered.
  - OC-5 is DECIDED: HOURLY_COMMANDS, appended LAST (never inserted —
    test_scheduler_error_handling.py indexes HOURLY_COMMANDS[0] and [2]
    positionally, and test_scheduler.py does the same). The full rationale is in
    "OC-5 decision" above; do not re-open it.
  - test_scheduler.py must be edited too — its Surface omission is corrected in
    "Three corrections" above. TestSchedulerConstants::test_hourly_commands_match_spec
    asserts HOURLY_COMMANDS == [exactly 9 names].
  - test_sweep_lock_structure.py asserts THREE things at once:
    {name for name, _ in SWEEP_COMMANDS} == EXPECTED_SWEEP_COMMANDS (an exact
    frozenset), len(lock_calls) == len(EXPECTED_SWEEP_COMMANDS) (one lock site
    per listed command), and monkeypatch.setattr(f"{module}.advisory_lock", spy)
    for every module in _LOCK_TARGET_MODULES. Miss any one of the three lists and
    the test fails. Note the spy REPLACES advisory_lock, so call_command runs the
    command's real body with a no-op lock — the command must therefore handle an
    empty table and return 0.
  - CRITICAL TEST TRAP: MediaDeletionError.created_at is auto_now_add=True, so
    MediaDeletionError.objects.create(created_at=...) SILENTLY IGNORES the
    argument. Every retention test must create the row and then
    MediaDeletionError.objects.filter(pk=row.pk).update(created_at=<value>).
    Otherwise every row is "now", nothing is ever past the TTL, and the delete
    assertions pass vacuously.
  - No Ad, AdImage or user row is needed for any new test: MediaDeletionError has
    no foreign keys by design ("the row is self-contained"). Add ZERO
    create_test_ad / create_test_adbulk calls — the ad-factory contract test
    walks the whole repo, and any call without a literal status= (or a
    status-declaring **kwargs forwarder) fails the ENTIRE repository gate.
  - conftest.py is do-not-touch and has no staff fixture. Build the reader's
    staff actor locally with
    make_user(<distinct telegram_id>, is_staff=True) plus
    user.user_permissions.add(*Permission.objects.filter(content_type__app_label="media", codename="view_mediadeletionerror"))
    and a changelist request with RequestFactory + reverse("admin:media_mediadeletionerror_changelist")
    + CookieStorage messages, exactly as
    apps/core/tests/test_support_admin.py::_local_staff_user /
    _local_changelist_request do. Use a telegram_id no other media test uses.
  - "No editable field" is proven by get_form(request) INTROSPECTION, not by
    reading source. With has_add_permission False and has_change_permission
    False, ModelAdmin.get_form raises ImproperlyConfigured for BOTH
    change=False and change=True (Django 5.2 raises when
    `not can_add and not can_change`). That raise IS the assertion: Django
    refuses to build a change form at all. Also pin
    list(MediaDeletionErrorAdmin.readonly_fields) == [] as metadata introspection.
  - Staff-only view access is enforced by AdminSite.has_permission (which
    requires user.is_active and user.is_staff), NOT by ModelAdmin. Do NOT add a
    has_view_permission override. Test the site-level gate: a non-staff user
    holding the view permission still gets admin.site.has_permission(...) is False.
  - Do NOT add has_delete_permission, search_fields or date_hierarchy. They are
    outside the settled surface; a manual delete cannot violate the TTL. Recorded
    as a deliberate omission, not an oversight.
  - i18n: this admin introduces ZERO translatable strings (labels come from
    auto-generated field verbose_names, which are not gettext-wrapped). Do NOT
    edit src/backend/locale/**/django.po — the uncommitted lines there belong to
    other agents. The i18n completeness gate must stay green untouched.
  - Precondition already verified by the Planner:
    makemigrations --check under DJANGO_SETTINGS_MODULE=config.settings.test_migrations
    prints "No changes detected". The orphan __pycache__/0002_*.pyc and 0003_*.pyc
    have no matching .py and are inert. A pending migration appearing later is a
    scope error — this block creates none.
  - Command shape follows apps/core/management/commands/purge_consent_records.py:
    module docstring naming the TTL and the lock id, _RETENTION_DAYS constant
    for the default, add_arguments with --older-than (type=int, default=30) and
    --dry-run, handle() opening transaction.atomic() then advisory_lock(...)
    before any branch, CommandError for --older-than < 1 (a 0 or negative TTL
    would delete the whole table including rows written a second ago), and a
    return of None / exit code 0 on every non-exceptional outcome including an
    empty set and --dry-run. Keep the existing
    `# pyright: ignore[reportGeneralTypeIssues]` comment on the transaction.atomic()
    line — django-stubs is not installed.
  - delete_photo's three-attempt backoff, its logger.error and its never-raise
    contract are UNCHANGED. _record_deletion_error keeps swallowing its own
    errors. apps/media/services/filesystem.py is not edited at all.
  - Working tree: other agents have uncommitted work (locale files,
    src/backend/apps/users/services/deactivation.py, docs/**, staticfiles/,
    .ai/tmp/, the .ai/audit/** deletions, the untracked plan file). Stage by
    EXPLICIT PATH only — never `git add -A`, never `.`, never a directory.

files:

  - path: src/backend/apps/media/admin.py
    targets:
      - type: class
        name: MediaDeletionErrorAdmin
    semantic_anchors:
      insert_after:
        type: decorator
        value: "@admin.register(MediaDeletionError)"

  - path: src/backend/apps/media/management/commands/purge_media_deletion_errors.py
    targets:
      - type: class
        name: Command
      - type: method
        name: handle
      - type: method
        name: add_arguments
    semantic_anchors: []

  - path: src/backend/apps/core/enums.py
    targets:
      - type: class
        name: AdvisoryLockId
    semantic_anchors:
      insert_after:
        type: assignment
        value: "CONSENT_RECORD_SWEEP = 14"

  - path: src/backend/apps/core/utils/advisory_lock.py
    targets:
      - type: function
        name: advisory_lock
      - type: docstring_section
        name: "Lock ID allocation (transaction-scoped table)"
    semantic_anchors:
      insert_after:
        type: docstring_line
        value: "14  CONSENT_RECORD_SWEEP         consent-record retention sweep"
    note: >
      Docstring table ONLY. No executable line in this module changes.

  - path: src/backend/apps/core/tests/test_advisory_lock_ids.py
    targets:
      - type: class
        name: TestAdvisoryLockIdMembers
    semantic_anchors:
      insert_after:
        type: class
        name: TestAdvisoryLockIdMembers

  - path: src/backend/apps/core/tests/test_sweep_lock_structure.py
    targets:
      - type: constant
        name: SWEEP_COMMANDS
      - type: constant
        name: EXPECTED_SWEEP_COMMANDS
      - type: constant
        name: _LOCK_TARGET_MODULES
    semantic_anchors: []
    note: >
      THREE lists, one commit. Missing any one fails the suite.

  - path: src/backend/apps/core/tests/test_scheduler.py
    targets:
      - type: class
        name: TestSchedulerConstants
      - type: method
        name: test_hourly_commands_match_spec
    semantic_anchors:
      insert_after:
        type: method
        name: test_hourly_commands_match_spec

  - path: src/backend/apps/core/utils/scheduler.py
    targets:
      - type: constant
        name: HOURLY_COMMANDS
    semantic_anchors:
      insert_after:
        type: list_entry
        value: purge_deleted_ads

  - path: src/backend/apps/media/models.py
    targets:
      - type: module_docstring
        name: Media models for Mko Bazuna
    semantic_anchors: []
    note: >
      ONE citation only: the opening line's "(ME-003)" -> "(07-MEDIA-010)".
      Nothing else in this file changes. No new field, no new index, no Meta edit.

  - path: src/backend/apps/media/tests/test_purge_media_deletion_errors.py
    targets:
      - type: class
        name: TestPurgeMediaDeletionErrors
    semantic_anchors: []

  - path: src/backend/apps/media/tests/test_media_admin.py
    targets:
      - type: class
        name: TestMediaDeletionErrorAdmin
    semantic_anchors: []

  - path: src/backend/apps/media/tests/test_filesystem.py
    targets:
      - type: class
        name: TestDeletePhoto
    semantic_anchors:
      insert_after:
        type: method
        name: test_delete_photo_logs_media_deletion_error_on_retry_exhaustion
    note: >
      ADDITIVE ONLY — one new method at the end of the class. Zero existing line
      in this 812-line file is modified. This file carries BLOCK 3's and BLOCK
      6's landed tests; do not reflow or reformat it.

changes:

  - action: add_code
    description: >
      NEW src/backend/apps/media/admin.py. A single registered, fully read-only
      reader for MediaDeletionError.

        - @admin.register(MediaDeletionError) on MediaDeletionErrorAdmin.
        - list_display = ("created_at", "storage_key", "error_type", "attempts")
          — created_at and error_type first and last, so the reader answers
          "what failed, and how".
        - list_filter = ["error_type", "created_at"] — both columns are already
          indexed (idx_media_del_err_type / idx_media_del_err_created), so both
          filters are index-backed.
        - readonly_fields = [] — literally empty, per the settled constraint.
        - ordering = ("-created_at",) — newest-first is the reader's primary use
          (the phase-12 predicate is created_at__gt=now()-1h) and the column is
          indexed.
        - has_add_permission(self, request) -> False and
          has_change_permission(self, request, obj=None) -> False, each with a
          one-line docstring saying the rows are written by delete_photo.
        - NO has_view_permission override (staff-only is enforced by
          AdminSite.has_permission), NO has_delete_permission, NO search_fields,
          NO date_hierarchy, NO @admin.display description, NO changelist_view
          override, NO module-level logger that is never used.
        - A module docstring naming 07-MEDIA-010 and stating the retention
          command that bounds the table. English only, no print().
    code_hint: |
      """
      Read-only Django admin surface for ``MediaDeletionError`` (07-MEDIA-010).

      ``delete_photo`` writes a row whenever a deletion exhausts its retries,
      and until now nothing could read them. Rows are never created, edited or
      deleted here — this is a diagnostic reader only. Bounded by
      ``purge_media_deletion_errors``.
      """

      import logging

      from django.contrib import admin

      from apps.media.models import MediaDeletionError

      logger = logging.getLogger(__name__)


      @admin.register(MediaDeletionError)
      class MediaDeletionErrorAdmin(admin.ModelAdmin):
          """Changelist-only reader for recorded deletion failures."""

          list_display = ["created_at", "storage_key", "error_type", "attempts"]
          list_filter = ["error_type", "created_at"]
          readonly_fields = []
          ordering = ("-created_at",)

          def has_add_permission(self, request) -> bool:
              """Rows are written by delete_photo, never by an operator."""
              return False

          def has_change_permission(self, request, obj=None) -> bool:
              """The reader is diagnostic; nothing here is editable."""
              return False

  - action: add_code
    description: >
      NEW src/backend/apps/media/management/commands/purge_media_deletion_errors.py.

        - Module docstring: the TTL is 30 days and is the reason the table is
          bounded; the lock id is 15; the command is IRREVERSIBLE and
          --dry-run is the mandatory first run. Name 07-MEDIA-010.
        - _RETENTION_DAYS = 30 module constant (the --older-than default), with a
          comment that both needed columns are already indexed so the predicate
          is an index scan, not the seq scan the source plan feared.
        - add_arguments: --older-than, type=int, default=_RETENTION_DAYS, help
          text stating DAYS; and --dry-run (store_true, dest="dry_run"). Both
          are NOT mutually exclusive with anything else.
        - handle():
            1. older_than = options["older_than"]; if older_than < 1 raise
               CommandError("--older-than must be at least 1 day; 0 or negative
               would delete every row including one written a second ago").
            2. with transaction.atomic(): with
               advisory_lock(AdvisoryLockId.PURGE_MEDIA_DELETION_ERRORS):
               — THE LOCK IS TAKEN BEFORE ANY BRANCH, on both the dry-run and the
               destructive path, so the lock-structure spy reaches it either way
               and two schedulers never race even a report.
            3. cutoff = timezone.now() - timedelta(days=older_than);
               eligible = MediaDeletionError.objects.filter(created_at__lt=cutoff)
            4. if dry_run: log and self.stdout.write the count, then return
               (deletes nothing — not a queryset that is built and abandoned,
               not a flag checked after .delete()).
            5. deleted_count, _per_model = eligible.delete(); log.info; one
               self.stdout.write(self.style.SUCCESS(...)).
            6. Return None -> exit code 0 on every non-exceptional outcome,
               including an empty eligible set.
        - Keep the `# pyright: ignore[reportGeneralTypeIssues]` comment on the
          transaction.atomic() line exactly as the sibling commands do
          (django-stubs is not installed).
        - ONE DELETE statement. No batching, no keyset pagination, no loop: the
          predicate is a single indexed range and the table is small by
          construction (rule 5).
    code_hint: |
      _RETENTION_DAYS = 30

      class Command(BaseCommand):
          """Delete MediaDeletionError rows older than the retention window."""

          help = "Delete recorded media deletion failures older than N days (default 30)"

          def add_arguments(self, parser) -> None:
              """Add the retention window (days) and the non-destructive mode."""
              parser.add_argument(
                  "--older-than",
                  type=int,
                  default=_RETENTION_DAYS,
                  help="Retention window in days (default: %(default)s)",
              )
              parser.add_argument(
                  "--dry-run",
                  action="store_true",
                  dest="dry_run",
                  default=False,
                  help="Report the count that would be deleted without deleting",
              )

          def handle(self, *args, **options) -> None:
              """Purge aged MediaDeletionError rows under the retention lock."""
              older_than: int = options["older_than"]
              dry_run: bool = options["dry_run"]

              if older_than < 1:
                  raise CommandError(
                      f"--older-than must be at least 1 day; got {older_than}. "
                      "A non-positive window would delete every row, including "
                      "one written a second ago."
                  )

              cutoff = timezone.now() - timedelta(days=older_than)

              with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped
                  with advisory_lock(AdvisoryLockId.PURGE_MEDIA_DELETION_ERRORS):
                      eligible = MediaDeletionError.objects.filter(created_at__lt=cutoff)

                      if dry_run:
                          count = eligible.count()
                          logger.info("DRY RUN: would delete %d rows older than %d days", count, older_than)
                          self.stdout.write(
                              self.style.WARNING(
                                  f"DRY RUN: {count} deletion-error rows would be deleted."
                              )
                          )
                          return

                      deleted_count, _per_model = eligible.delete()
                      logger.info("Purged %d deletion-error rows older than %d days", deleted_count, older_than)

              self.stdout.write(self.style.SUCCESS(f"Purged {deleted_count} deletion-error rows."))

  - action: modify
    description: >
      apps/core/enums.py::AdvisoryLockId — add ONE member,
      PURGE_MEDIA_DELETION_ERRORS = 15, immediately after
      CONSENT_RECORD_SWEEP = 14. No existing member is renumbered, reordered
      or removed; SWEEP_ORPHANED_MEDIA stays 103 and CONSENT_HARD_DELETE stays 3.

      RE-READ THE LIVE FILE IMMEDIATELY BEFORE THIS EDIT. Another agent may have
      taken 15. If 15 is taken, stop and report on the board rather than picking
      the next integer yourself — two phases guessing the same free id is the
      exact failure this constraint exists to prevent.

      The coordinator (main) must be notified on the board BEFORE this file is
      touched.
    code_hint: |
          CONSENT_RECORD_SWEEP = 14
          PURGE_MEDIA_DELETION_ERRORS = 15

  - action: modify
    description: >
      apps/core/utils/advisory_lock.py — the transaction-scoped allocation table
      in advisory_lock's docstring, one new row directly under the
      "14  CONSENT_RECORD_SWEEP" line. No executable line in the module changes.
      The trailing prose ("IDs 14-99 are reserved for future scheduled jobs")
      stays as written — 15 is inside the reserved band, so it remains true.
    code_hint: |
                14  CONSENT_RECORD_SWEEP         consent-record retention sweep
                15  PURGE_MEDIA_DELETION_ERRORS  deletion-error retention purge

  - action: modify
    description: >
      apps/core/tests/test_advisory_lock_ids.py — the allocation record. Add ONE
      test method to TestAdvisoryLockIdMembers that pins the new member AND
      proves non-reuse relationally (an IntEnum value collision creates a silent
      ALIAS, which is the failure mode this test exists to catch):

        - AdvisoryLockId.PURGE_MEDIA_DELETION_ERRORS.value == 15
        - AdvisoryLockId.PURGE_MEDIA_DELETION_ERRORS.name ==
          "PURGE_MEDIA_DELETION_ERRORS"  (an alias resolves the OLD name)
        - len({m.value for m in AdvisoryLockId}) == len(list(AdvisoryLockId))
          (no alias exists anywhere on the enum)
        - AdvisoryLockId.SWEEP_ORPHANED_MEDIA == 103
        - AdvisoryLockId.CONSENT_HARD_DELETE == 3

      And ONE test that the advisory_lock docstring's transaction-scoped table
      contains a row naming the new member, so the three-file one-commit
      constraint cannot be satisfied by two files.

      No existing test in this file is edited.
    code_hint: |
          def test_purge_media_deletion_errors_lock_is_not_a_reuse(self) -> None:
              """Lock 15 is allocated to the media retention purge and aliases nothing."""
              member = AdvisoryLockId.PURGE_MEDIA_DELETION_ERRORS

              assert member.value == 15
              # A value collision makes IntEnum an ALIAS: the attribute resolves
              # but .name is the pre-existing member's name.
              assert member.name == "PURGE_MEDIA_DELETION_ERRORS"
              # No alias anywhere on the enum (distinct values == distinct members).
              assert len({m.value for m in AdvisoryLockId}) == len(list(AdvisoryLockId))

          def test_existing_lock_ids_are_not_renumbered(self) -> None:
              """Ids other blocks depend on keep their values."""
              assert AdvisoryLockId.SWEEP_ORPHANED_MEDIA == 103
              assert AdvisoryLockId.CONSENT_HARD_DELETE == 3

  - action: modify
    description: >
      apps/core/tests/test_sweep_lock_structure.py — THREE lists, one commit,
      or the suite goes red:

        1. SWEEP_COMMANDS — append ("purge_media_deletion_errors",
           AdvisoryLockId.PURGE_MEDIA_DELETION_ERRORS). APPEND; the set assertion
           is order-insensitive but keep the file's existing order.
        2. EXPECTED_SWEEP_COMMANDS — add "purge_media_deletion_errors" to the
           frozenset literal. This is an EXACT frozenset compared with `==`
           against {name for name, _ in SWEEP_COMMANDS}, AND its length drives
           `assert len(lock_calls) == len(EXPECTED_SWEEP_COMMANDS)`. Omitting it
           breaks both; adding it without the other two breaks the spy loop.
        3. _LOCK_TARGET_MODULES — append
           "apps.media.management.commands.purge_media_deletion_errors". Without
           it, monkeypatch.setattr raises AttributeError because the command
           module binds advisory_lock at import time.

      The new command must be safe to run bare under the spy (call_command with
      no arguments, advisory_lock replaced by a no-op): handle() must tolerate an
      empty table and exit 0. No existing entry in the three lists is modified,
      reordered or removed.
    code_hint: |
          ("purge_consent_records", AdvisoryLockId.CONSENT_RECORD_SWEEP),
          ("purge_media_deletion_errors", AdvisoryLockId.PURGE_MEDIA_DELETION_ERRORS),
          # ... and in EXPECTED_SWEEP_COMMANDS:
              "purge_media_deletion_errors",
          # ... and in _LOCK_TARGET_MODULES:
          "apps.media.management.commands.purge_media_deletion_errors",

  - action: modify
    description: >
      apps/core/tests/test_scheduler.py::TestSchedulerConstants — the pinned
      HOURLY_COMMANDS literal in test_hourly_commands_match_spec gains
      "purge_media_deletion_errors" as the TENTH and LAST entry.

      This is NOT in the block's original Surface list; the Planner found it by
      reading the live file. test_hourly_commands_match_spec asserts
      `HOURLY_COMMANDS == [ ...9 names... ]` by exact list equality, so omitting
      it turns the full gate red.

      No other test in this 831-line file is edited. In particular, do NOT touch
      the positional uses of HOURLY_COMMANDS[0] / [2] or DAILY_COMMANDS[0] / [1]
      — appending at the end preserves every index.
    code_hint: |
              "purge_rejected_ads",
              "purge_deleted_ads",
              "purge_media_deletion_errors",
              ]

  - action: modify
    description: >
      apps/core/utils/scheduler.py::HOURLY_COMMANDS — append
      "purge_media_deletion_errors" as the LAST entry (OC-5, decided).
      APPEND, never insert: test_scheduler_error_handling.py indexes
      HOURLY_COMMANDS[0] and HOURLY_COMMANDS[2] positionally.

      Add a short comment in the existing leading block explaining WHY this purge
      is hourly rather than daily: an hourly command's exit code cannot suppress
      the durable daily marker, so a media-retention failure never re-dispatches
      send_alerts or rollup_daily_metrics. That is the whole reason for the
      placement and it must survive in the file.

      DAILY_COMMANDS is NOT touched. HOURLY_COMMANDS / DAILY_COMMANDS / the
      dispatch loop / _validate_commands / _write_liveness_marker are otherwise
      unchanged.
    code_hint: |
      # Phase 4 hourly sweeps + Phase 2 purges + the media deletion-error
      # retention purge (07-MEDIA-010, AdvisoryLockId.PURGE_MEDIA_DELETION_ERRORS).
      # The purge is hourly, not daily, because a DAILY command's exit code is
      # load-bearing for the durable daily marker: a non-zero exit would leave the
      # day unrecorded and re-dispatch send_alerts / rollup_daily_metrics on every
      # subsequent hourly tick. An hourly command only gates the liveness marker.
      HOURLY_COMMANDS: list[str] = [
          ...
          "purge_deleted_ads",
          "purge_media_deletion_errors",
      ]

  - action: modify
    description: >
      apps/media/models.py — ONE citation, nothing else. The module docstring's
      opening line currently reads "... enabling operational escalation (ME-003)."
      and ME-003 resolves to nothing in this repository. Reconcile it to the
      cycle-scoped id this block actually closes: "(07-MEDIA-010)".

      Restore, do not drop: the observable gap the citation names — a deletion
      failure with no operator surface — is what 07-MEDIA-010 closes, so dropping
      the id would discard real traceability while restoring an unresolvable one
      replaces it with a resolvable one.

      Accepted residual: apps/media/services/filesystem.py::_record_deletion_error's
      docstring carries the same stale ME-003 and that file is do-not-touch for
      this block. Record it; do not fix it.

      No new field, no new index, no Meta edit, no __str__ edit in this file.
    code_hint: |
      """
      Media models for Mko Bazuna.

      ``MediaDeletionError`` records filesystem deletion failures that exhausted
      all retries in ``delete_photo``. It has an operator surface
      (``apps.media.admin.py``) and a bounded retention window
      (``purge_media_deletion_errors``, 30 days) as of 07-MEDIA-010.
      """

  - action: add_code
    description: >
      NEW src/backend/apps/media/tests/test_purge_media_deletion_errors.py.
      pytestmark = [pytest.mark.django_db]. A module-local
      _aged_row(**overrides) helper that creates the row and then forces
      created_at with .filter(pk=...).update(created_at=...) — the auto_now_add
      trap, named in extra_context, must be visible in the helper's docstring so
      it cannot be reintroduced. No Ad is ever created.

      Required behaviour:
        - test_dry_run_deletes_nothing — two aged rows; --dry-run; both still
          present; the reported/expected count is 1 (the past-TTL one).
        - test_row_inside_ttl_survives_with_message_intact — a 29-day-old row
          with a distinctive error_message survives the default run AND its
          storage_key, error_type, error_message and attempts are unchanged
          (refresh_from_db, not just a count).
        - test_row_past_ttl_is_deleted — a 31-day-old row is gone.
        - test_default_retention_window_is_30_days — omit --older-than; a
          29-day-old row survives and a 31-day-old row does not. Pins the
          default without reading the argparse declaration.
        - test_second_run_is_a_no_op — run twice; the first deletes 1, the
          second deletes 0 and the table count is unchanged. Idempotence.
        - test_older_than_must_be_at_least_one_day — --older-than 0 and -1 both
          raise CommandError and delete nothing.
        - test_command_exits_zero_on_an_empty_table — call_command on an empty
          table raises nothing (this is the state the lock-structure spy runs it
          in).

      Assert on querysets and the command's exit behaviour, not on log text.
    code_hint: |
      pytestmark = [pytest.mark.django_db]

      def _aged_row(*, age_days: int, **overrides) -> MediaDeletionError:
          """Create a row whose ``created_at`` is *age_days* in the past.

          ``created_at`` is ``auto_now_add=True``, so passing it to ``create()``
          is SILENTLY IGNORED — the argument must be forced with an ``UPDATE``
          afterwards, or every row reads as "now" and the delete assertions pass
          vacuously.
          """
          fields = {
              "storage_key": f"{uuid4()}.jpg",
              "error_type": "PermissionError",
              "error_message": "denied by the filesystem",
              "attempts": DELETE_PHOTO_MAX_ATTEMPTS,
          }
          fields.update(overrides)
          row = MediaDeletionError.objects.create(**fields)
          MediaDeletionError.objects.filter(pk=row.pk).update(
              created_at=timezone.now() - timedelta(days=age_days)
          )
          row.refresh_from_db()
          return row

      def test_row_inside_ttl_survives_with_message_intact() -> None:
          row = _aged_row(age_days=29, error_message="distinct message body")

          call_command("purge_media_deletion_errors")

          row.refresh_from_db()
          assert row.error_message == "distinct message body"
          assert row.attempts == DELETE_PHOTO_MAX_ATTEMPTS

  - action: add_code
    description: >
      NEW src/backend/apps/media/tests/test_media_admin.py.
      pytestmark = [pytest.mark.unit] for the metadata/permission tests and
      django_db only where a row or a staff actor is needed (see extra_context
      for the local staff actor and changelist request).

      Required behaviour:
        - test_media_deletion_error_is_registered_in_admin.
        - test_get_form_refuses_to_build_a_change_form — get_form(request)
          raises ImproperlyConfigured for change=False AND change=True. This is
          the "no editable field" proof and it is INTROSPECTION, never a source
          read.
        - test_readonly_fields_is_empty — list(...readonly_fields) == [].
        - test_list_display_and_list_filter_cover_created_at_and_error_type.
        - test_changelist_resolves_both_filters — build the real changelist via
          model_admin.get_changelist_instance(request) and assert both entries
          appear in ChangeList.list_filter with the expected field paths, so the
          filters are proven RESOLVABLE against the queryset rather than merely
          named. Needs django_db.
        - test_add_and_change_permissions_are_false; test_view_permission_follows
          the view perm; test_non_staff_with_the_view_perm_is_refused_by_the_site
          (admin.site.has_permission(request) is False for a non-staff actor
          holding the perm, True for the staff actor).
        - test_changelist_renders_for_staff — a real changelist render for a
          staff actor, mirroring
          apps/core/tests/test_support_admin.py::test_support_ticket_changelist_renders_masked_identifiers.
          This is the reachability assertion for the block's whole premise.
    code_hint: |
      from django.contrib.admin.sites import AlreadyRegistered  # noqa: F401  (doc only)
      from django.core.exceptions import ImproperlyConfigured

      def _staff_actor(telegram_id: int) -> User:
          """Build a staff user holding only the changelist permission."""
          actor = make_user(telegram_id, is_staff=True)
          actor.user_permissions.add(
              *Permission.objects.filter(
                  content_type__app_label="media",
                  codename="view_mediadeletionerror",
              )
          )
          return actor

      def test_get_form_refuses_to_build_a_change_form() -> None:
          """No editable field: Django will not build a change form at all (07-MEDIA-010)."""
          model_admin = MediaDeletionErrorAdmin(MediaDeletionError, admin.site)
          request = MagicMock()

          # Introspection, not a source read: with add and change both denied,
          # ModelAdmin.get_form raises for change=False AND change=True.
          with pytest.raises(ImproperlyConfigured):
              model_admin.get_form(request)
          with pytest.raises(ImproperlyConfigured):
              model_admin.get_form(request, change=True)

      @pytest.mark.django_db
      def test_changelist_resolves_both_filters() -> None:
          """Both declared filters resolve against the real queryset."""
          model_admin = MediaDeletionErrorAdmin(MediaDeletionError, admin.site)
          request = _local_changelist_request(_staff_actor(941000001))

          changelist = model_admin.get_changelist_instance(request)

          assert {"error_type", "created_at"} <= {
              entry.field_path for entry in changelist.list_filter
          }

  - action: add_code
    description: >
      src/backend/apps/media/tests/test_filesystem.py — ADDITIVE: one new method
      at the END of TestDeletePhoto, immediately after
      test_delete_photo_logs_media_deletion_error_on_retry_exhaustion. Zero
      existing line in the file is modified.

      test_delete_photo_swallows_a_failed_deletion_error_record: patch
      apps.media.models.MediaDeletionError.objects.create with
      side_effect=OperationalError("db down"), patch os.remove with
      PermissionError and filesystem time.sleep (so no real backoff), call
      delete_photo("locked.jpg"). Assert it does NOT raise, that remove was
      attempted DELETE_PHOTO_MAX_ATTEMPTS times, and that caplog contains
      "Failed to persist MediaDeletionError". This is the component
      interaction: the retention table's writer is unchanged and still cannot
      break a delete path.
    code_hint: |
          @pytest.mark.django_db
          def test_delete_photo_swallows_a_failed_deletion_error_record(self, caplog) -> None:
              """A DB failure while recording the failure never propagates (07-MEDIA-010)."""
              from django.db import OperationalError

              from apps.media.models import MediaDeletionError

              with (
                  patch(
                      "apps.media.services.filesystem.os.remove",
                      side_effect=PermissionError("denied"),
                  ) as mock_remove,
                  patch("apps.media.services.filesystem.time.sleep"),
                  patch.object(
                      MediaDeletionError.objects,
                      "create",
                      side_effect=OperationalError("db down"),
                  ),
              ):
                  delete_photo("locked.jpg")  # must not raise

              assert mock_remove.call_count == DELETE_PHOTO_MAX_ATTEMPTS
              assert "Failed to persist MediaDeletionError" in caplog.text

acceptance_criteria:
  - MediaDeletionError is reachable through the admin changelist with working
    created_at and error_type filters and NO editable field — proven by
    get_form(request) raising ImproperlyConfigured for both change=False and
    change=True, NOT by reading the source file
  - --dry-run deletes nothing and reports the eligible count
  - A row inside the TTL survives with its storage_key, error_type, error_message
    and attempts byte-intact; a row past it is deleted
  - The default window is 30 days, proven by behaviour with no --older-than flag
  - A second run is a no-op (idempotent)
  - --older-than 0 and --older-than -1 raise CommandError and delete nothing
  - The command takes advisory_lock(AdvisoryLockId.PURGE_MEDIA_DELETION_ERRORS)
    inside transaction.atomic() on the production path, proven by the existing
    spy test in test_sweep_lock_structure.py
  - purge_media_deletion_errors appears in HOURLY_COMMANDS (LAST), in
    SWEEP_COMMANDS, in EXPECTED_SWEEP_COMMANDS and in _LOCK_TARGET_MODULES — all
    three structure-test lists, plus the exact HOURLY_COMMANDS literal in
    test_scheduler.py
  - AdvisoryLockId.PURGE_MEDIA_DELETION_ERRORS is 15, its .name is itself (no
    IntEnum alias), SWEEP_ORPHANED_MEDIA is still 103 and CONSENT_HARD_DELETE is
    still 3
  - The advisory_lock.py docstring table records the new allocation row
  - _record_deletion_error still swallows a DB failure and delete_photo's
    three-attempt backoff, logger.error and never-raise contract are unchanged
  - The reader introduces ZERO translatable strings and
    src/backend/locale/**/django.po is untouched
  - makemigrations --check under config.settings.test_migrations reports no
    changes — this block creates NO migration
  - uv run ruff check src/ exits 0; uv run basedpyright src/ reports zero NEW
    diagnostics — the baseline is 3 pre-existing errors in
    apps/search/tests/test_immediate_alerts.py and apps/users/tests/test_login.py
  - every new create_test_ad / create_test_adbulk call is status-grounded with a
    literal status=; this block adds ZERO such calls
  - three commits, explicit paths only; the lock allocation lands as its own
    three-file commit before any test-list pin moves
  - the coordinator (main) was notified on the board BEFORE enums.py was edited

gate: |
  $dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'
  $dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/core/tests/test_advisory_lock_ids.py src/backend/apps/core/tests/test_sweep_lock_structure.py src/backend/apps/core/tests/test_scheduler.py src/backend/apps/core/tests/test_scheduler_error_handling.py src/backend/apps/core/tests/test_scheduler_daily_marker.py src/backend/apps/core/tests/test_scheduler_wiring.py src/backend/apps/media/tests/test_purge_media_deletion_errors.py src/backend/apps/media/tests/test_media_admin.py src/backend/apps/media/tests/test_filesystem.py --tb=short" test
  .\Makefile.ps1 test
  uv run ruff check src/
  uv run basedpyright src/

  # Migration precondition — must print "No changes detected". A pending
  # migration is a SCOPE ERROR, not a pre-existing condition (verified clean at
  # 81dd644 by the Planner).
  docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml run --rm --no-deps --entrypoint "" -e DJANGO_SETTINGS_MODULE=config.settings.test_migrations test python src/backend/manage.py makemigrations --check --dry-run

do_not_touch: >
  delete_photo and _record_deletion_error in
  apps/media/services/filesystem.py (including its stale ME-003 docstring) ·
  apps/media/signals.py · apps/media/services/** (incl. references.py and
  thumbnails.py) · AdAdmin's field set and permission predicates ·
  apps/ads/** · apps/media/models.py beyond the single ME-003 citation ·
  MediaDeletionError.Meta (no new field, no new index) ·
  src/backend/conftest.py · src/backend/locale/** · docs/** (route, never edit) ·
  .ai/** · DELETE_PHOTO_MAX_ATTEMPTS / DELETE_PHOTO_BASE_DELAY.

commit:
  - message: "feat(core): allocate the media deletion-error retention lock"
    paths:
      - src/backend/apps/core/enums.py
      - src/backend/apps/core/utils/advisory_lock.py
      - src/backend/apps/core/tests/test_advisory_lock_ids.py
    note: >
      Three files, one commit, BEFORE any test list moves. Notify the
      coordinator on the board before editing enums.py. Message body must record
      that 15 was taken from the "IDs 14-99 are reserved" band after phase 06
      consumed 14, and that the plan's "next free id is 14" was stale.
  - message: "test(core): pin the retention command into the lock and scheduler lists"
    paths:
      - src/backend/apps/core/tests/test_sweep_lock_structure.py
      - src/backend/apps/core/tests/test_scheduler.py
    note: >
      Three lists in the first file, one exact HOURLY_COMMANDS literal in the
      second. Both files are list-assertion pins, not behaviour.
  - message: "feat(media): add a deletion-error reader and a 30-day retention purge"
    paths:
      - src/backend/apps/media/admin.py
      - src/backend/apps/media/management/commands/purge_media_deletion_errors.py
      - src/backend/apps/media/models.py
      - src/backend/apps/core/utils/scheduler.py
      - src/backend/apps/media/tests/test_purge_media_deletion_errors.py
      - src/backend/apps/media/tests/test_media_admin.py
      - src/backend/apps/media/tests/test_filesystem.py
    note: >
      Stage by explicit path. Never `git add -A`, never `.`, never a directory —
      the working tree holds other agents' uncommitted work (locale files,
      docs/**, users/services/deactivation.py, staticfiles/, .ai/tmp/, the
      untracked plan file, and the deleted .ai/audit/** tree).
```

**Commit body — mandatory content for commit 3**, in this order:
1. The reader and the retention window, and that the purge is **irreversible**: `--dry-run` is the mandatory first run, and a revert does not restore purged rows.
2. **OC-5 = `HOURLY_COMMANDS`, appended last**, with the decisive reason: a daily command's exit code gates the durable daily marker, so a media-purge failure would re-dispatch `send_alerts` and `rollup_daily_metrics` on every subsequent tick; phase 06's `purge_consent_records` earns that slot precisely because it never deletes and always exits 0. An hourly command only gates the liveness marker.
3. **No alerting ships.** Recorded for phase 12: the predicate
   `MediaDeletionError.objects.filter(created_at__gt=now() - 1h).exists()`.
4. The retention query is **index-backed** on `created_at`; the source plan's
   "seq-scans an unbounded table" argument does not apply.
5. The plan's "next free id is `14`" was **stale** — phase 06's `fd5201d` took
   `CONSENT_RECORD_SWEEP = 14`; this block verified **15** against the live enum
   immediately before allocating.
6. **Doc drift routed, not edited** (see the routing table above), including the
   `db-retention.md` sentence that `--older-than` falsifies, which is currently
   **unrouted** and raised on the board.
7. Accepted residual: `filesystem.py::_record_deletion_error`'s docstring still
   cites the unresolvable `ME-003` (do-not-touch file).
8. Deliberate omissions: no `search_fields`, no `date_hierarchy`, no
   `has_delete_permission` override, no `has_view_permission` override.

```yaml
id: verify_task_07m08_media_deletion_error_reader_and_retention

title: "Verify — MediaDeletionError reader + 30-day retention purge"

type: verification

status: pending

depends_on:
  - task_07m08_media_deletion_error_reader_and_retention

verifies:
  - task_07m08_media_deletion_error_reader_and_retention

verification_steps:
  - build: uv run ruff check src/
  - typecheck: uv run basedpyright src/
  - targeted: $dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/core/tests/test_advisory_lock_ids.py src/backend/apps/core/tests/test_sweep_lock_structure.py src/backend/apps/core/tests/test_scheduler.py src/backend/apps/core/tests/test_scheduler_error_handling.py src/backend/apps/core/tests/test_scheduler_daily_marker.py src/backend/apps/core/tests/test_scheduler_wiring.py src/backend/apps/media/tests/test_purge_media_deletion_errors.py src/backend/apps/media/tests/test_media_admin.py src/backend/apps/media/tests/test_filesystem.py --tb=short" test
  - full_suite: $dc run --rm test
  - fast_gate: .\Makefile.ps1 test
  - migration_precondition: >
      docker compose --project-name mko-bazuna-test --env-file .env.test
      -f docker-compose.yml -f docker-compose.test.yml run --rm --no-deps
      --entrypoint "" -e DJANGO_SETTINGS_MODULE=config.settings.test_migrations
      test python src/backend/manage.py makemigrations --check --dry-run
      Must print "No changes detected". Verified clean at 81dd644 by the
      Planner; a pending migration here is a SCOPE ERROR introduced by this
      block, not a pre-existing condition.
  - smoke_check: >
      Read by symbol, never by line number. (a) apps/media/admin.py declares
      MediaDeletionErrorAdmin with readonly_fields == [] and overrides ONLY
      has_add_permission and has_change_permission — there is no
      has_view_permission, has_delete_permission, search_fields, date_hierarchy
      or changelist_view override. (b) The command takes
      advisory_lock(AdvisoryLockId.PURGE_MEDIA_DELETION_ERRORS) INSIDE
      transaction.atomic() and BEFORE the --dry-run branch. (c) The command has
      exactly ONE delete statement and no loop. (d)
      AdvisoryLockId.PURGE_MEDIA_DELETION_ERRORS == 15, CONSENT_RECORD_SWEEP ==
      14, SWEEP_ORPHANED_MEDIA == 103, CONSENT_HARD_DELETE == 3, and no other
      id moved. (e) purge_media_deletion_errors is the LAST entry of
      HOURLY_COMMANDS (not inserted), and DAILY_COMMANDS is byte-identical to
      its pre-block content. (f) The name appears in all THREE
      test_sweep_lock_structure.py lists and in the pinned HOURLY_COMMANDS
      literal in test_scheduler.py. (g) apps/media/models.py differs from its
      pre-block content in the ME-003 citation ONLY — no field, index, Meta or
      __str__ edit. (h) apps/media/services/filesystem.py is byte-identical to
      its pre-block content (delete_photo, _record_deletion_error and the two
      DELETE_PHOTO_* constants). (i) src/backend/locale/** is untouched and
      apps/media/admin.py contains no gettext call and no user-visible string.
      (j) git diff --stat shows no docs/** and no .ai/** path.
  - negatives: >
      Tripwires that must each be demonstrated red against the shipped body and
      reverted byte-identically (confirm with SHA256): (1) remove the entry from
      EXPECTED_SWEEP_COMMANDS only -> the exact-frozenset assertion fails;
      (2) remove the entry from _LOCK_TARGET_MODULES only -> monkeypatch
      AttributeError; (3) drop "purge_media_deletion_errors" from
      test_scheduler.py's pinned HOURLY_COMMANDS literal -> that exact-equality
      assertion fails; (4) move the lock acquisition AFTER the --dry-run branch,
      or outside atomic() -> the spy test fails on in_atomic/session; (5) set
      --older-than default to 0 -> test_default_retention_window_is_30_days
      fails; (6) give has_change_permission a True path -> the get_form
      ImproperlyConfigured assertion fails. Also confirm the command exits 0 on
      an empty table, so a routine no-op does not age the scheduler liveness
      marker into an unhealthy container.
  - diff_scope: >
      Three commits. Commit 1 stages exactly
      src/backend/apps/core/enums.py,
      src/backend/apps/core/utils/advisory_lock.py and
      src/backend/apps/core/tests/test_advisory_lock_ids.py. Commit 2 stages
      exactly src/backend/apps/core/tests/test_sweep_lock_structure.py and
      src/backend/apps/core/tests/test_scheduler.py. Commit 3 stages the seven
      reader/retention/test paths. Any other path — docs/**, .ai/**,
      src/backend/locale/**, src/backend/apps/moderation/**,
      src/backend/apps/users/**, staticfiles/ — is another agent's work or a
      scope error. Verify with `git show --stat` on each of the three commits.

pass_criteria:
  - ruff exits 0
  - basedpyright reports no NEW diagnostic — the baseline is 3 pre-existing
    errors in apps/search/tests/test_immediate_alerts.py and
    apps/users/tests/test_login.py, not 0
  - the targeted 9-path run is green
  - .\Makefile.ps1 test is green, including test_ad_factory_contract.py (the
    repo-wide status-grounding gate) and the i18n completeness test
  - makemigrations --check under config.settings.test_migrations prints "No
    changes detected"
  - every smoke_check and negatives assertion holds
  - the three commits staged exactly their listed paths, in order, with the
    prescribed subjects
  - the coordinator was notified on the board before enums.py was edited, and
    15 was re-verified against the live enum at that moment
  - every red observation was re-run SERIALLY and reproduced TWICE before being
    reported; a wall of setup errors (DuplicateDatabase, ObjectInUse,
    DeadlockDetected, "terminating connection due to administrator command") is
    another agent's concurrent run, not a defect
  - test_search_slo is NOT in this gate (known environmental flake under host
    load) — if it fails, confirm it is the flake and attribute it, do not fix it

failure_action: return task_07m08_media_deletion_error_reader_and_retention to rework
```

---

## BLOCK 9 — nginx script-execution block + `/media/` rate limit

**Findings owned.** `07-MEDIA-006`.
**Depends on.** Nothing in-plan. **Risk.** MEDIUM on paper, **LOW after research** — see "Corrected residual" in the RESEARCH DECISIONS section: `KEY_FORMAT_REGEX` proves the legitimate keyspace is disjoint from the deny set, so a regex typo cannot 403 a conforming photo. Green-field, no shipped behaviour changes.

**Required agents.**
- **Auditor** — confirm neither config has a script-execution location, that `deny all` appears once (only on `= /metrics`), and that both `/media/` locations are `proxy_pass http://web:8000` with no `limit_req`.
- **Researcher + Planner** — **merged and complete.** nginx `location` matching semantics, `deny`/`return` phase ordering, `limit_req` burst semantics for an image-heavy `no-store` path, block placement, and the shadow-proof assertion strategy are all settled with doc/source/live-nginx evidence in the RESEARCH DECISIONS section below. **Do not re-open them.**
- **Implementor** — insert the exact text from D4 into both configs and add the three tests from D4. No design decisions remain.
- **Validator** — mandatory: `nginx -t` for both configs via the corrected compose commands, **plus** the deployed-stack real-key smoke check (constraint 9). The smoke check is now a *confirmation* of the in-test regex model rather than the sole defence, but it is **not** optional — Python `re` is not PCRE.

**What is wrong.** Neither shipped nginx site declares a script-execution `location` for `/media/`. `deny all` appears exactly once in each config, on `= /metrics` only. `MEDIA_ROOT` is nginx-served, so **a `.php`/`.py`/`.cgi`/`.pl`/`.sh` file landing under the media volume would be served** by the server. Separately, both `/media/` locations proxy to the web app with **no `limit_req`**, while `browse_limit` already exists in **both** configs at `10m rate=20r/s` — the in-pattern control is already defined and simply not applied to the media path.

> **Corrected for honesty (D5.1).** The word *executed* was overstated and is dropped above. Under the **shipped** configs `/media/` is `proxy_pass` only — no `root`, no `alias`, no `fastcgi_pass`, no `ssi on` — and the only `alias` lives in the `internal` `/protected-media/`, so nginx never touches the filesystem for `/media/`. Django's `media_gate` resolves the key against an `AdImage` row and 404s anything unreferenced. `07-MEDIA-006` is therefore a **latent / defence-in-depth** control: a name-based tripwire that becomes load-bearing the moment anyone adds `root`/`alias`/`fastcgi_pass`/`ssi on` to the media path. That is a legitimate reason to ship it. It is **not** a live RCE today, and no document may claim otherwise.

**Surface (semantic units only).**
- `docker/nginx/nginx.conf` — `location /media/` gains `limit_req`; a new `location ~* ^/media/.*\.(?:php|py|cgi|pl|sh)(?:/|$) { deny all; return 403; }` is inserted **immediately before** it
- `docker/nginx/nginx.dev.conf` — the identical two additions, byte for byte
- `src/backend/tests/test_nginx_config.py` — extend using the existing `_PROXIED_CONFIGS` parametrization and helpers; add only the two local selectors `_header` / `_by_header_prefix` from D4
- `docs/01-spec/architecture-structure.md` — **routed to BLOCK 10**, never edited here

**Q07-13 ANSWERED: DELIBERATE, and documented.** `test_nginx_config.py`'s own module docstring states that both shipped sites must satisfy the client-IP trust invariant and that *"the dev site has fewer locations (no `/health/`, `/csp-report/` or `= /metrics` block), so every new assertion is written to be location-agnostic."* That committed statement of intent is the documentary evidence for the decision: **duplicate** the block into both configs; add **no** shared `include` fragment, because an unmounted include **silently disables** the control. Quote the docstring into the commit body.

**Binding constraints.** *(Settled wording; see the RESEARCH DECISIONS section below for the evidence behind each.)*
1. **Reuse `browse_limit`. Add NO new `limit_req_zone`.** The zone already exists in both files at `10m rate=20r/s` (`nginx.conf:26`, `nginx.dev.conf:29`). The directive is **`limit_req zone=browse_limit burst=40 nodelay;`**, placed **directly above `proxy_pass`** inside `location /media/` — identical in both files and identical to `/moderation/` and `/`. Do **not** write `limit_req_status` (both files already set `429` at `http` level) and do **not** use `limit_req_dry_run` (it leaves `07-MEDIA-006` unclosed).
2. The new block is a **`~*` (regex) match, not a prefix**, and its pattern is exactly **`^/media/.*\.(?:php|py|cgi|pl|sh)(?:/|$)`** — `\.` escaped, `~*` caseless, **no trailing `$` anchor**, the five spec extensions and nothing more. A prefix location either hard-fails (`duplicate location`) or silently 403s every photo; an unescaped `.` inverts the control and 403s every photo. Test 1 pins all of this semantically, not by substring.
3. The new block carries **`deny all`** and **`return 403`** (`deny all` first), and **must NOT carry a `proxy_pass`** — `test_proxied_locations_overwrite_x_real_ip` would fail otherwise. It must also carry **no `limit_req`**: `return` short-circuits in the rewrite phase, so `limit_req` in this block would be dead config.
4. **Assert via `_iter_location_blocks` and the block's first line — not `_location_block`.** `_brace_block` starts at the `location` line, so leading comments are excluded and the header is exact; this makes every new assertion order-independent and immune to the first-match hazard `_location_block`'s docstring warns about. No new assertion's search string may appear on an earlier line or inside the new comment.
5. `location /protected-media/` is **untouched**. Both files end **without a trailing newline** — insert in the middle and leave the final byte alone.
6. Use the existing `_PROXIED_CONFIGS` parametrization over **both** files — do **not** introduce a new mechanism. Every new assertion is **location-agnostic**, per the module's own docstring.
7. The three existing `/metrics` assertions pass **unchanged**; neither new comment line contains `= /metrics`, so `_location_block` still resolves only the metrics block.
8. **No application-level rate limiter on `media_gate`** — a second policy in a different language is the wrong shape. `media_gate` is untouched.
9. **One irreducible manual gate:** a real-key smoke check in a **deployed** stack, recorded as **done** in the commit body **with the date**. The Python-`re` model in test 1 is a faithful but *non-PCRE* stand-in for nginx's matching; the deployed check confirms the model. It is now a confirmation step, not the sole defence. It must assert, on a **24-thumbnail listing page**, that every `<img>` renders and the access log contains **no 429 on any `/media/` request**.
10. `nginx -t` passes for **both** configs, via the corrected compose commands in the gate below. Record honestly that `nginx -t` **does not** detect the silent prefix-replacement outage — it only catches the duplicate-prefix variant.

**Required tests.** *(Concretised in D4; all three are parametrized over `_PROXIED_CONFIGS`.)*
1. **Both** configs declare **exactly one** location whose header modifier is **`~*`** and whose body contains `deny all` **and** `return 403` **and no `proxy_pass`**; its extracted regex, compiled caseless, **denies** the 10 hostile URIs (including `/media/x.php/a.jpg`, `/media/x.PHP`, `/media/x.jpg.php`) and **allows** the 9 genuine key shapes (including `/media/<uuid>.jpg`, `/media/<uuid>-small.jpg`, `/media/seed/kvartiry_01.jpg`, `/media/a.jpg?x=.php`). Failure messages name the offending URI and the word `OUTAGE`.
2. Both `/media/` locations carry **`limit_req zone=browse_limit`** with **`nodelay`**; the file contains **exactly three** `limit_req_zone` directives and `browse_limit` is defined **exactly once** — a census assertion, so it cannot pass on a file with no zones at all.
3. The three existing `/metrics` assertions pass unchanged; `/protected-media/` is unchanged.

**Keep green / do not edit.**
All seven existing tests in `src/backend/tests/test_nginx_config.py` · `_PROXIED_CONFIGS` · `_brace_block` / `_location_block` / `_iter_location_blocks` / `_proxied_locations` · `browse_limit` · `limit_req_status 429;` (already at `http` level in both files — do **not** duplicate it inside `/media/`) · `location /protected-media/` · `apps/ads/views/listings.py` (`_serve_image` / `media_gate` — the block is nginx-only, no application change) · `KEY_FORMAT_REGEX` in `apps/media/services/filesystem.py` (the residual argument in "Corrected residual" depends on it — **do not widen the key format without re-running this analysis**) · `generate_storage_key()` · `ThumbnailService` suffixes · `ListingsQuery.PER_PAGE = 24` and `templates/ads/partials/ad_list.html` (the `burst=40` sizing depends on one image per card and 24 per page) · `src/backend/conftest.py`.

**Gate (exact).**
```
$dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/tests/test_nginx_config.py --tb=short" test
.\Makefile.ps1 test

# nginx -t — CORRECTED (see D5). There is no nginx binary on the Windows host
# (`Get-Command nginx` returns nothing) and the bare-image route fails:
# `proxy_pass http://web:8000` is resolved at CONFIG-PARSE time, so a throwaway
# container without `web` in DNS dies with
#   [emerg] host not found in upstream "web" in /etc/nginx/nginx.conf:62
# and `ssl_certificate /etc/nginx/certs/fullchain.pem` is absent (no openssl in
# nginx:alpine to mint one). The working route is the compose network, which
# resolves `web` and mounts ./docker/nginx/certs (dev) — VERIFIED, both configs
# return "syntax is ok / test is successful":
$dev = 'docker compose --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.override.yml --project-name mko-bazuna-dev'
& $dev run --rm --no-deps --entrypoint nginx nginx -t                                             # nginx.dev.conf (default mount)
& $dev run --rm --no-deps --entrypoint nginx -v "${PWD}/docker/nginx/nginx.conf:/etc/nginx/nginx.conf:ro" nginx -t   # nginx.conf (prod), bind-swapped
```
`docker compose` **can** reach the nginx registry — the first run pulled `nginx:alpine` (74.5 MB) successfully.

**Risk and rollback.** A regex typo in the script-execution block **403s every genuine photo** — a site-wide image outage. Rollback = revert both config files; no data effect and no DB effect. See the corrected residual below.

---

## BLOCK 9 — RESEARCH DECISIONS (Researcher + Planner, 2026-10-03)

Every claim below is backed by the official nginx docs, nginx source, or a **running nginx/1.27.5** measured in this environment. Confidence is stated per item.

### D1 — the regex form, and why a prefix is catastrophic

**Location matching order (HIGH — nginx.org/en/docs/http/request_processing.html, verbatim):**
> "nginx first searches for the most specific prefix location given by literal strings **regardless of the listed order**. … Then nginx checks locations given by regular expression **in the order listed in the configuration file**. The first matching expression stops the search and nginx will use this location. If no regular expression matches a request, then nginx uses the most specific prefix location found earlier."

**Why a prefix would be catastrophic.** A prefix `location /media/` is not shadowed by the regex — it *competes for the same slot*. Two outcomes, both bad, both **confirmed by measurement**:
- **Add** a second `location /media/` → nginx refuses to start: `[emerg] duplicate location "/media/" in /etc/nginx/nginx.conf:18`. Loud, caught by `nginx -t`.
- **Replace / convert** the existing block to the deny block → `nginx -t` **passes** and `/media/a.jpg` returns **403**. Silent, site-wide image outage. Measured.

**The form to write (this exact line, in both files):**
```nginx
location ~* ^/media/.*\.(?:php|py|cgi|pl|sh)(?:/|$) {
```

| Decision | Rationale |
|---|---|
| `~*`, not `~` | nginx uses **PCRE**; `~*` sets `NGX_REGEX_CASELESS`. Measured: `/media/a.PHP` → 403, `/media/a.Php` → 403. A case-sensitive `~` would serve both. Filenames come from Telegram and from operator-restore paths, so case must not be a bypass. |
| `\.` **not** `.` | PCRE `.` matches any character, so `^/media/.*.(?:jpg\|…)$` matches `/media/<uuid>.jpg`. **MEASURED: that typo returns 403 for `/media/a.jpg` and 200 for `/media/a.php` — the control inverted.** This is the single highest-consequence typo in the block. |
| `^/media/` anchored at the head | Confines the deny to the media path. Measured: `/static/a.php` → 200 (untouched). Keeps the change in scope and stops the block from silently becoming a global script ban. |
| `.*` **and no `$` anchor** | `location ~*` is an **unanchored search over the whole normalised URI**. A trailing `$` is exactly what breaks the path-info form. **MEASURED with `$` anchored: `/media/x.php/a.jpg` → 200.** The regex must stay unanchored at the end. |
| `(?:/\|$)` after the extension | Tightens without anchoring: requires the extension to end a path segment. Measured: `/media/a.phpx` → 200 (not over-blocked), `/media/a.php/a.jpg` → 403, `/media/a.jpg.php` → 403. |
| `(?:…)` non-capturing | Avoids consuming `$1`..`$9` in a block that needs none. |
| No quoting | The pattern contains no `{`, `}`, or `;`, so nginx's tokenizer needs none. The nginx doc's own example, `location ~* \.(gif\|jpg\|png)$`, is unquoted. |

**Percent-encoding cannot bypass it (MEASURED).** `/media/a.p%68p` → **403**. nginx matches locations against the *decoded* URI, so encoding the extension does not help. Query strings are not matched at all (`"locations of all types test only a URI part of request line without arguments"` — verified: `/media/a.jpg?x=.php` → 200).

**Live end-to-end matrix on the real patched `nginx.dev.conf`**, with the real Django upstream (`403` = deny block, `404` = proxied to Django and the proxy is intact):

| URI | Status | Meaning |
|---|---|---|
| `/media/<uuid>.jpg` | 404 | proxied — **no shadowing** |
| `/media/<uuid>-small.jpg` | 404 | proxied |
| `/media/seed/kvartiry_01.jpg` | 404 | proxied |
| `/media/<uuid>.php` | **403** | denied |
| `/media/<uuid>.PHP` | **403** | denied (case) |
| `/media/<uuid>.php/a.jpg` | **403** | denied (path-info) |
| `/media/<uuid>.jpg.php` | **403** | denied |
| `/media/<uuid>.phpx` | 404 | proxied — not over-blocked |
| `/protected-media/<uuid>.jpg` | 404 | still `internal`, untouched |

### D2 — `deny all` **and** `return 403` in the same block

**Phase ordering (HIGH — nginx source).** `ngx_http_core_module.h`:
```c
NGX_HTTP_FIND_CONFIG_PHASE, NGX_HTTP_REWRITE_PHASE,   /* index 3 */
NGX_HTTP_PREACCESS_PHASE,
NGX_HTTP_ACCESS_PHASE,                                 /* index 6 */
```
`ngx_http_rewrite_init()` pushes `ngx_http_rewrite_handler` into `phases[NGX_HTTP_REWRITE_PHASE]`; `ngx_http_access_init()` pushes `ngx_http_access_handler` into `phases[NGX_HTTP_ACCESS_PHASE]`. The handler returns 403, the REWRITE-phase checker calls `ngx_http_finalize_request(r, 403)` — the request ends before ACCESS runs.

**MEASURED, decisively.** `location /x/ { deny all; return 200 "RETURN-REACHED\n"; }` → **HTTP 200, body `RETURN-REACHED`**. No `access forbidden by rule` in the error log. Same shape with `return 404` → 404, not 403. **`return` always wins; `deny all` is unreachable dead config in this block.**

**No config error and no startup warning.** `ngx_http_access_rule()` only errors on an invalid CIDR and only warns on `"low address bits … are meaningless"` — neither applies to `deny all`. `nginx -t` on the patched configs emitted no warning.

**Decision — keep both, and say honestly why.** The spec and its tests require both, so shipping both is right; the redundancy is defence in depth against a future edit that drops the `return` line, which would leave `deny all` as the only control. But the plan must not imply both are active: **`return 403` is the load-bearing directive and `deny all` is a belt-and-braces fallback.** Order `deny all` first, matching the in-file `= /metrics` precedent (`allow` / `deny` before `proxy_pass`). Block body, exactly:
```nginx
            deny all;
            return 403;
```
No `allow` — `allow 127.0.0.1` would be actively wrong here and would weaken the block if `return` were ever dropped.

### D3 — `limit_req` on the media path

`browse_limit` is defined identically in both files — `nginx.conf:26`, `nginx.dev.conf:29`:
```nginx
    limit_req_zone $binary_remote_addr zone=browse_limit:10m rate=20r/s;
```
and both files set `limit_req_status 429;` at `http` level (`nginx.conf:29`, `nginx.dev.conf:32`) with the comment *"Return 429 (Too Many Requests) instead of nginx default 503 on rate limit."*

**Directive (identical in both files, first line inside `location /media/`, above `proxy_pass`):**
```nginx
            limit_req zone=browse_limit burst=40 nodelay;
```

| Sub-decision | Decision | Rationale |
|---|---|---|
| **burst value** | **`burst=40`** | Matches `/moderation/` and `/` **exactly** (`limit_req zone=browse_limit burst=40 nodelay`) — rule 7, follow existing patterns, and the whole framing of this block is "the in-pattern control is defined and simply not applied". **Measured:** 41 concurrent `/media/` requests all pass, the 42nd+ is rejected. Real ceiling is **24**: `ListingsQuery.PER_PAGE = 24` and `templates/ads/partials/ad_list.html:108` renders exactly **one** `loading="lazy"` image per card. Headroom 1.7×. **`burst=20` would have been wrong:** measured 21 pass / 24 rejected for a 45-request burst — a 24-thumbnail page loses images. |
| **`nodelay`** | **required** | Docs: *"If delaying of excessive requests while requests are being limited is not desired, the parameter nodelay should be used."* Measured: `burst=20` **without** `nodelay` produced the same 21/24 split but took **1147 ms** wall vs **148 ms** with `nodelay` — accepted thumbnails are *delayed*, which is worse than a fast 429 for an image grid. |
| **`limit_req_status 403`?** | **NO — omit it.** | The *directive* default is 503, but the **effective** value is already **429**: both files set `limit_req_status 429;` at `http` level, and `limit_req_status` is a normal inheritable directive. Measured: rejections come back **429**. Writing an explicit `403` here would (a) contradict the file's own stated intent, (b) collide with the deny block's 403 so a rate-limited image is indistinguishable from a denied script in access logs, and (c) put a *cache* status on a *throttle*. **429 for a hotlinked image is right and 403 for a missing one is unrelated** — the media path's 404s come from Django and are untouched by this change. |
| **`limit_req_dry_run`** | **NO — do not use it** | Directive confirmed to exist (appeared 1.17.1; default `limit_req_dry_run off`; verified accepted by nginx/1.27.5). It is a *diagnostic* mode: *"requests processing rate is not limited, however … excessive requests is accounted as usual"*, and rejections surface as `$limit_req_status = REJECTED_DRY_RUN` with the response **delayed, not refused**. Shipping it would leave `07-MEDIA-006` **unclosed** while looking closed. Keep it available as a one-line rollback lever if the deployed smoke check ever shows 429s on legitimate browsing — that is the honest use. |
| **new `limit_req_zone`?** | **NO** | `browse_limit` already exists in both files at `10m rate=20r/s`. Binding constraint 1. |
| **placement** | inside `location /media/`, **directly above `proxy_pass`** | `limit_req` context is `http, server, location`, and it runs in PREACCESS — which is *after* REWRITE. **MEASURED consequence:** a location with `limit_req … ; return 200 "…"` served **45/45 with zero 429s** — `return` short-circuits before `limit_req` ever evaluates. So (a) the deny block must **not** carry `limit_req`, it would be dead; and (b) `limit_req` is only effective in a **proxying** location, which `/media/` is. |

**Realistic page-turn measurement** (`burst=40 nodelay`, 24 images per page, no inter-request pacing): page 1 → 24×200, page 2 at +2 s → 24×200, page 3 at +0.5 s → 24×200. **Zero 429s.**

### D4 — placement and the assertion strategy

**Placement: immediately BEFORE `location /media/`, after `location /static/`.** Functionally order-independent (regexes are consulted *after* the longest prefix regardless of position, and neither config has another regex location), but adjacency makes the guard and the guarded path readable as a pair, and it is the defensive order if a regex location is ever added later.

**Exact config text to insert into BOTH files** (identical bytes; the only pre-existing difference between the two files around this region is the surrounding comment set):

```nginx
        # Script-execution deny for the nginx-served MEDIA_ROOT (07-MEDIA-006).
        # A ~* regex location is mandatory: a prefix /media/ block would replace
        # the proxying block below and 403 every genuine photo. `return` is
        # evaluated in the rewrite phase and wins; `deny all` is defence in depth.
        location ~* ^/media/.*\.(?:php|py|cgi|pl|sh)(?:/|$) {
            deny all;
            return 403;
        }

        # Media files proxied to Django for per-request access control
        location /media/ {
            limit_req zone=browse_limit burst=40 nodelay;
            proxy_pass http://web:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
```

**Assertion strategy.** Use `_iter_location_blocks` + the block's own **first line** as the selector. `_brace_block` starts at the `location` line, so comments above it are excluded and the header is exact. This makes every assertion **order-independent and immune to the `_location_block` first-match hazard** the module docstring warns about — no search string is ever matched against a comment or an earlier block.

Shared local helpers (no new mechanism, no change to the four existing helpers):
```python
_SCRIPT_DENY_EXTS = ("deny all", "return 403")


def _header(block: str) -> str:
    """The `location ... {` line of a block, normalised (leading comments excluded)."""
    return block.splitlines()[0].strip()


def _by_header_prefix(text: str, prefix: str) -> list[str]:
    """Every location block whose header line starts with *prefix*."""
    return [b for b in _iter_location_blocks(text) if _header(b).startswith(prefix)]
```
`_by_header_prefix(text, "location /media/")` matches `location /media/ {` and correctly rejects `location ~* ^/media/…`, `location /protected-media/ {`, and `location / {`. All three were confirmed against the real files.

**Test 1 — `~*` script-execution location with `deny all` + `return 403` (parametrized over `_PROXIED_CONFIGS`):**
```python
deny = [b for b in _iter_location_blocks(text)
        if all(m in b for m in _SCRIPT_DENY_EXTS)]
assert len(deny) == 1, f"{conf_path.name}: expected exactly one script-deny location, got {len(deny)}"
assert "proxy_pass" not in deny[0], "deny block must not proxy (would break X-Real-IP invariant)"
match = re.match(r"^location\s+(?P<mod>[~*^=]*)\s*(?P<rx>\S.*?)\s*\{$", _header(deny[0]))
assert match, "unparsable location header"
assert match.group("mod") == "~*", f"must be a ~* regex match, got {match.group('mod')!r}"
```
Then the **semantic** half — this is what actually defends against the outage. Extract the regex out of the config and exercise it, rather than substring-matching it:
```python
uri_only = lambda u: u.split("?", 1)[0]          # nginx matches the URI, not arguments
denied = re.compile(match.group("rx"), re.IGNORECASE)   # ~* -> PCRE caseless
must_allow = ["/media/<uuid>.jpg", "/media/<uuid>-small.jpg", "/media/<uuid>-medium.jpg",
              "/media/<uuid>-large.jpg", "/media/seed/kvartiry_01.jpg",
              "/media/staging/<uuid>.jpg", "/media/a.phpx", "/media/a.notphp.jpg",
              "/media/a.jpg?x=.php"]
must_deny = ["/media/x.php", "/media/x.PHP", "/media/x.Php", "/media/x.py",
             "/media/x.cgi", "/media/x.pl", "/media/x.sh",
             "/media/x.php/a.jpg", "/media/x.jpg.php", "/media/sub/dir/x.php"]
outage = [u for u in must_allow if denied.search(uri_only(u))]
assert not outage, f"OUTAGE: deny regex would 403 genuine photos: {outage}"
missed = [u for u in must_deny if not denied.search(uri_only(u))]
assert not missed, f"deny regex does not deny: {missed}"
```
Every `must_allow` entry is a real key shape from `generate_storage_key()` (`filesystem.py:260-262`), `ThumbnailService` (`-small` / `-medium` / `-large`), `staging/`, and the `seed/<slug>` convention — not invented strings.

**Test 2 — `limit_req` reusing `browse_limit`, and no new zone:**
```python
zones = [l.strip() for l in text.split("\n") if l.strip().startswith("limit_req_zone")]
assert len(zones) == 3, f"{conf_path.name}: no new limit_req_zone may be added; found {len(zones)}"
assert sum("zone=browse_limit:" in z for z in zones) == 1, "browse_limit must be defined exactly once"
media = _by_header_prefix(text, "location /media/")
assert len(media) == 1, f"expected exactly one `location /media/`, got {len(media)}"
assert "limit_req zone=browse_limit" in media[0], "must reuse browse_limit"
assert "nodelay" in media[0], "must use nodelay so thumbnails are never delayed"
assert "proxy_pass" in media[0], "limit_req must sit in the proxying location"
```
**Why the negative assertion cannot pass vacuously:** it is a **census**, not an absence check. `len(zones) == 3` is a positive equality — the block is deleted, a 4th zone is added, or `browse_limit` is renamed, and the test fails. An `assert "media_limit" not in text`-style check would pass on a config with no `limit_req_zone` at all. The cost is that a *legitimate* future zone now fails this test; that is the intended trade for BLOCK 9's binding constraint and is the same shape BLOCK 10 needs for its doc census.

**Test 3 — the three existing `/metrics` assertions and `/protected-media/` unchanged.** Already satisfied: the new block contains no `proxy_pass` (so `_proxied_locations` skips it), `/protected-media/` is not edited, and `_location_block(text, "= /metrics")` still matches only the metrics block — neither new comment contains `= /metrics`.

**Non-vacuousness, measured.** The strategy was executed against 8 configs with the four existing helpers copied verbatim. Result: **PASSES** on both patched real configs; **FAILS** on both unpatched real configs; **FAILS** with `must be a ~* regex match, got ''` on the prefix-deny catastrophe; **FAILS** with `OUTAGE: deny regex would 403 genuine photos: ['/media/<uuid>.jpg', …]` on the unescaped-dot typo; **FAILS** with `regex does not deny: ['/media/x.php/a.jpg']` on the `$`-anchored counterfeit; **FAILS** with `expected exactly one script-deny location, got 0` when the block is absent. Every failure names the concrete offending URI.

### D5 — corrections to the spec

1. **"would be executed or served by the server" is overstated for the shipped configs** — state the honest impact. `location /media/` is `proxy_pass` only: no `root`, no `alias`, no `fastcgi_pass`, no `ssi on`, and `location /protected-media/` (the only `alias`) is `internal`. nginx therefore **never touches the filesystem** for `/media/` — it proxies to Django, whose `media_gate` resolves the key against an `AdImage` row and returns `X-Accel-Redirect: /protected-media/<key>` with `Cache-Control: no-store` (`views/listings.py:191-193`). An unreferenced `.php` gets **404**. So `07-MEDIA-006` is a **latent / defence-in-depth** control: it is a name-based tripwire that becomes load-bearing the moment anyone adds `root`/`alias`/`fastcgi_pass`/`ssi on` to the media path. That is a legitimate reason to ship it; it is not a live RCE today, and the plan must not claim otherwise.
2. **The gate command is wrong and cannot work.** `nginx -t -c docker/nginx/nginx.conf` needs a host nginx binary (none installed) and, even in `nginx:alpine`, fails at config-parse time on `host not found in upstream "web"` plus a missing `ssl_certificate` (`nginx:alpine` ships no openssl to mint one). Replaced with the two verified `docker compose … run --rm --no-deps --entrypoint nginx nginx -t` invocations above. `--entrypoint nginx` is required — the default `docker-entrypoint.sh` runs `/docker-entrypoint.d/` scripts first.
3. **`nginx -t` does NOT catch the catastrophic mistake.** Measured: the prefix-deny config passes `nginx -t` cleanly and then 403s every photo. `nginx -t` only catches the *duplicate*-prefix variant, via `[emerg] duplicate location`. This must be said explicitly, because the gate line is the block's only mechanical anti-outage check.
4. **Extension list kept at exactly the spec's five** (`php`, `py`, `cgi`, `pl`, `sh`). Deliberate: `KEY_FORMAT_REGEX` (`filesystem.py:45-48`) proves the legitimate keyspace is `[A-Za-z0-9._-]` segments **terminated by `.jpg`**, so every extra extension is pure typo surface for zero present-day gain. Recorded residual: `.phtml`, `.phar`, `.shtml`, `.htaccess` are **not** covered. That is acceptable precisely because nothing in the shipped config can execute them (point 1) — and it is the first thing to revisit if anyone ever adds `ssi on` or a `root` to `/media/`.
5. **`deny all` is dead config, not an active control** (D2). Keep it; do not document it as active.
6. **Trailing-newline artefact.** Both files currently end without a newline. An `edit`-based insertion that rewrites the file end will produce a spurious `+}` diff line. Insert in the middle of the file and leave the final byte alone.

### Corrected residual (replaces the MEDIUM-accepted line above)

The plan's *"likelihood MEDIUM, impact HIGH, residual MEDIUM accepted"* is **over-conservative and should be downgraded to LOW**, on evidence:

- **The legitimate keyspace is provably disjoint from the deny set.** `generate_storage_key()` returns `f"{uuid.uuid4()}.jpg"`; `ThumbnailService` appends `-small` / `-medium` / `-large`; seed keys are `seed/<slug>.jpg`; staging keys are `staging/<uuid>.jpg`. `KEY_FORMAT_REGEX` requires the URI to end in `.jpg`, and the deny regex requires `.<script-ext>` followed by `/` or end-of-URI. A conforming key **cannot** match. So a typo can only ever deny files that were *already* outside the conforming keyspace — never a genuine photo.
- **Test 1's semantic half is now a mechanical gate, not a mitigation.** It is the third control and it is *redundant with `nginx -t`* on the duplicate case and *superior to it* on the silent-replacement case. The plan's line *"the second control against shadowing is test 3's `~*` assertion"* should be restated: the controls are (i) the `~*` + extracted-regex semantic assertion, (ii) `nginx -t`, and (iii) the deployed smoke check.
- **What is genuinely irreducible:** the Python `re` model is not PCRE. For this pattern shape (`^` anchor, `~*` caseless, `(?:)`, `\.`, alternation) the two engines agree, and every case was confirmed against a running nginx/1.27.5 — but the model is a model. Binding constraint 9's deployed-stack check therefore **stays mandatory**; it is now a confirmation step rather than the sole defence.
- **Rollback:** `git revert` of both config files. No data effect, no DB effect, no migration.

---

## BLOCK 10 — Ownership rule + documentation corrections

**Findings owned.** `07-MEDIA-009`.
**Depends on.** BLOCK 2b (**hard** — the rule must describe the **fixed four-column** check), BLOCK 9 (**hard** — the nginx bullet may not be claimed until it ships), BLOCKS 4 and 5 (soft — the corrections reference the shipped quality constant and the shipped seed behaviour). **Risk.** MEDIUM — documentation; the impact of wrong documentation on a security invariant is HIGH. **Priority: P1.**

**Required agents.**
- **Auditor** — mandatory. The source plan's premise is **false** and its census is **wrong**; a full re-census of every stale location is the block's first task, not an assumption.
- **Researcher** — **not required.** No best-practices or support question remains; every mechanism this block documents has already shipped.
- **Planner** — required: the reconcile strategy (one file contradicts itself), and the routing package for the two reserved locations.
- **Implementor** — land the corrections.
- **Validator** — mandatory: a documentation block that *states the wrong behaviour* is worse than no block, and verification here is a read-through against named symbols.

**What is wrong — the plan's premise is FALSE.** The source plan asserts that *"a repository-wide search for `refcount` / `reference count` / `same storage key` / `ownership` across `docs/` returns nothing"*. It does not. **The ownership invariant is already documented in three committed places** (`db-schema.md`, `db-retention.md`, `technical-specification.md`). Its literal search claim survives — the four `ownership` hits are unrelated — but its **conclusion** does not. BLOCK 10 is therefore **not** "state the invariant"; it is **"reconcile a self-contradiction inside one file and finish a partially-completed correction."**

The self-contradiction: inside `docs/02-database/db-schema.md`, the `ad_images.image` field comment **and** the Zone R6/R8 callout both claim the key is **`ad_id` + UUID v4** (ad-scoped, unique to one ad), while a paragraph **eight lines below** correctly states the key is **not** unique to one row and is freed only on the last reference. Same file, same section.

**Two locations drop out of the census.**
- `docs/02-database/db-retention.md` is **already correct** — it names the reference check, `apps.media.signals`, `AdImage.storage_keys()`, `copy_ad` aliasing, the `exclude(pk=…)` exclusion and its load-bearing reason, and records that the check retired as `64a9de6`. **Nothing left to route. The phase-06 / phase-03 reservation on this file is LIFTED.**
- In `docs/01-spec/technical-specification.md` only **two** sentences remain stale; the erasure sentence and the ≥1-photo sentence are already correct or true.

**Surface (semantic units only).**
- `docs/02-database/db-schema.md` — the `ad_images.image` field comment, the Zone R6/R8 callout, and the `sha256` per-user-deduplication comment (goes **false** after BLOCK 1)
- `docs/01-spec/technical-specification.md` — **routed to phase 06 with exact replacement text, NEVER edited**
- `docs/04-user-stories/seller-stories.md` (US-S5) — **IN SCOPE** per Q07-12=(a)
- `docs/ops/docker-deployment.md` — **IN SCOPE** per Q07-12=(a)
- `docs/01-spec/architecture-structure.md` — the two nginx script-block claims
- `src/backend/apps/ads/views/edit.py` — two module docstrings plus inline comments and one log string; **docstrings and comments only, no behaviour**
- `apps/media/services/references.py` (BLOCK 2b) — the behaviour being documented

**Binding constraints.**
1. The rule is stated as **shipped**: a key may be referenced by **N ≥ 1** `AdImage` rows, and bytes are freed **only when the last referencing row goes away**.
2. Describe BLOCK 2b's **actual** check — **all four** key columns — and its **post-commit** evaluation, **honestly**, including the residual characteristics the block's binding constraint 8 records: a shared key in a multi-row cascade is freed **once per departing row**, and a concurrent insert between the reference query and the `unlink` is the irreducible residual. Do **not** claim the multi-row-cascade leak was merely "accepted as a bias" — BLOCK 2b **eliminated** it by moving the predicate into the `on_commit` closure. (This constraint previously read "`pre_delete`-time evaluation … the documented multi-row-cascade leak bias"; that was true of the shipped `64a9de6` shape but is no longer true of what BLOCK 2b lands.)
3. State the **real** key scheme — `<uuid4>.jpg`, `staging/<uuid4>.jpg` in flight, `seed/<filename>.jpg` — **with the reason there is no `ad_id`** (URL anonymity, Zone R6).
4. **No reach claim.** The seed default pool is **empty**, so "N references in production" is unmeasured. Either state the invariant without a number or cite BLOCK 2b's measurement.
5. **Do not** write it as an *"except `seed/`"* placeholder.
6. **Because Q07-6=(b)**, the corrected photo-edit text must say all three things: **price** edits publish immediately, **moderator** photo removal exists, and **seller-side** photo editing **does not exist in phase 1**. BLOCK 12 is deferred, so this correction is what closes `MEDIA-005`'s seller-facing half.
7. `technical-specification.md` is **routed with exact replacement text, never edited** — it is HELD by phase 06.
8. `docs/ops/docker-deployment.md` is **DIRTY** at `b7ba213` with another phase's account-state edits: **append-only**, **re-read immediately** before editing, and **stop and report** on conflict. Never clobber.
9. `docs/02-database/db-retention.md` is **not touched**.
10. `edit.py` changes are **docstrings and comments only — no behaviour**. Phase 05 owns that file's behaviour; a second editor re-reads before acting.
11. The `architecture-structure.md` nginx claim is made **only after** BLOCK 9 has landed.
12. **No behavioural tests.** Verification is a **Validator read-through against the named symbols**.
13. English only; no `print()`; no new identifiers; cite `07-MEDIA-009` (cycle-scoped) and **no** bare `MEDIA-0NN`.

**Required tests.**
None. Verification is a Validator read-through confirming every corrected sentence against the named symbol it describes, plus a repository-wide search confirming no remaining stale claim.

**Keep green / do not edit.**
`docs/01-spec/technical-specification.md` (routed only) · `docs/02-database/db-retention.md` (lifted) · `edit.py`'s **behaviour** · the uncommitted account-state edits in `docs/ops/docker-deployment.md` · `.ai/audit/**` · other phases' plan files.

**Gate (exact).**
```
$dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'
.\Makefile.ps1 test
uv run ruff check src/
uv run basedpyright src/
# plus: Validator read-through against the named symbols; git diff --stat on docs/
```

**Risk and rollback.** No code effect; rollback is `git revert` of the doc commit. The real risks are **Content** (2): an ownership rule written **before** BLOCK 2b lands would state an intent rather than a behaviour — hence the hard edge; and the block may not claim the nginx block before BLOCK 9 — hence that hard edge. Routing rather than editing a reserved file is what prevents losing a concurrent phase's work.

---

## BLOCK 11 — Moderator single-photo removal

**Findings owned.** `07-MEDIA-005` — the **moderator** half only. The seller-facing bot affordance (source-plan BLOCK 12) is **DEFERRED** per Q07-6=(b).
**Depends on.** BLOCK 2b (**hard**). **Risk.** HIGH — a new delete surface on a table with an aliasing invariant.

**Required agents.**
- **Auditor** — re-verify the `AdImageAdmin` permission surface by **introspection** and confirm the phase-15 RBAC layer has **not** landed (what landed is phase 19's moderation-lever privilege guard, a **different** surface).
- **Researcher** — admin `get_actions` filtering semantics: how `permissions=["delete"]` interacts with `has_delete_permission`, and the established row-lock shape in `moderation/admin_actions.py`.
- **Planner** — required: **OC-6** (which of exactly two predicates is opened) and the reason/audit flow.
- **Implementor** — land the service, the action, the audit row and the translations.
- **Validator** — mandatory: a new delete surface plus an authorization decision.

**What is wrong.** A moderator reviewing an ad with an inappropriate photo has **no** way to remove that single photo — the only lever is deleting the whole ad. `AdImageAdmin` declares **no `actions` at all**, `has_add_permission` / `has_change_permission` / `has_delete_permission` all return `False`, and `has_view_permission` is `is_staff or is_superuser`. So the changelist is **reachable** but **no action appears**.

**The trap — a decorated-but-invisible action is exactly the defect phase 04 found.** With `has_delete_permission` returning `False`, Django's `get_actions` filters `delete_selected` (which carries `permissions=["delete"]`) — and **any** `@admin.action(permissions=["delete"])` is filtered out **too**. Opening the wrong predicate, or both, produces an action that exists in source and is absent from the UI. **Exactly one** of `has_delete_permission` or the action's `permissions` may be opened; which one is **OC-6**.

**Surface (semantic units only).**
- **new** `apps/media/services/ad_image_admin_actions.py` — the removal service (deletes the **row**)
- `apps/media/admin.py` — `AdImageAdmin` gains `actions` and the single opened predicate
- `apps/moderation/admin_actions.py` — **read-only**; its pattern is followed, not modified
- `apps/core/enums.py::ModeratorActionType` — `OTHER` member reused
- `apps/media/services/references.py` (BLOCK 2b) — **consumed**
- `src/backend/locale/{ru,bs,en}/LC_MESSAGES/django.po` — **appended** only
- **new/extended** test module for the service and the action

**Binding constraints.**
1. **Hard dependency on BLOCK 2b.** The service **deletes the row** and lets BLOCK 2b's `on_commit` path free the bytes. It must **NOT** call `delete_photo` directly — that would be a **second data-loss route** bypassing the invariant.
2. **OC-6 stays open.** Exactly one predicate is opened. Record which and why in the commit body.
3. Verification is by **introspection** — `admin.site._registry[AdImage].get_actions(request)` and `.get_form(request)` — **never** by reading source permission flags.
4. The action **appears** in `get_actions(request)` for a staff request and is **absent** for a non-staff request. Staff-only **and** audited: **exactly one** `ModeratorActionLog` row per removal.
5. A non-staff caller is refused with **nothing deleted and no audit row**.
6. An empty reason is **refused**.
7. The reason is a **canned** value routed through `moderation/admin_actions.py`'s existing pattern with `ModeratorActionType.OTHER`. Phase 06's reason-redaction has **not** landed there, so a canned reason sidesteps redaction entirely. Do **not** add free-text reason storage.
8. **No new `AdvisoryLockId`.** A row lock is correct for a single-row delete; follow the established `select_for_update()` + `order_by("pk")` shape.
9. `AdAdmin`'s field set, fieldsets and permission predicates are **untouched**. `AdAdmin` declares no inlines and none is added.
10. `copy_ad` is **untouched**.
11. New admin strings resolve with **non-empty `ru` and `bs`**, **appended** — never regenerated.
12. i18n is part of the DoD.

**Required tests** (logic + component interaction).
1. A staff moderator removes one photo → the row is gone, **exactly one** `ModeratorActionLog` row is written, and the ad, its text, its status and its view count are **untouched**.
2. A non-staff caller is refused — **nothing deleted and no audit row**.
3. **The shared-key case (tripwire):** the file **still exists** and the other ad's image still serves — proving the service **reuses** BLOCK 2b's invariant rather than re-implementing it.
4. An empty reason is refused.
5. The action is **reachable from the UI** — asserted through `get_actions(request)`, not source reading.
6. The shared-key case survives end to end through the **admin action**, not only the service.

**Keep green / do not edit.**
`src/backend/apps/users/tests/test_admin_pii_containment.py` — it lives under `apps/users/tests/`, **not** `apps/core/tests/`, and covers `AdAdmin`, **not** `AdImageAdmin` · `apps/moderation/admin_actions.py` (zero locks, no redaction, clean) · `AdAdmin`'s field set and predicates · `copy_ad` · `src/backend/apps/core/tests/test_sweep_lock_structure.py` · `delete_photo` · the uncommitted locale lines · `src/backend/conftest.py`.

**Gate (exact).**
```
$dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/media/tests src/backend/apps/users/tests/test_admin_pii_containment.py src/backend/apps/ads/tests/test_i18n_completeness.py src/backend/apps/core/tests/test_delete_photo_single_call.py --tb=short" test
.\Makefile.ps1 test
uv run ruff check src/
uv run basedpyright src/
```

**Risk and rollback.** A new **delete surface** plus an authorization decision. Two named failure modes carry HIGH impact: (a) the service calls `delete_photo` directly and becomes a second data-loss route — mitigated by binding constraint 1 and tripped by test 3; (b) the surface is ungated or unaudited — mitigated by tests 1, 2 and 5. Rollback = remove the action and the service; **photos already removed do not return**, so the commit body must state that. **Phase 15 is notified before this block lands.**

---

## Open choices register

None of these is decided by this Planner. Each names the agent that resolves it and where the answer is recorded.

| ID | Block | Question | Options and consequences | Resolved by |
|---|---|---|---|---|
| **OC-1** | 2b | Where the reference predicate is evaluated | **(a)** Keep the shipped `pre_delete`-time evaluation with `.exclude(pk=…)` — zero structural change, but a multi-row cascade sends `pre_delete` for all rows before any `DELETE`, so two sharing rows both skip and the file **leaks**. **(b)** Move only the *filter* into the `on_commit` closure, keeping key collection at `pre_delete` — strictly better semantics, no cascade leak, and the module-level `delete_photo` binding and the identity assertion both survive; but it changes when the DB query runs, and the `exclude(pk=…)` comment must be rewritten. | **RESOLVED by Researcher = (b).** Verified against Django 5.2.17 `Collector.delete()` source: `instance.pk` is set to `None` *after* the `atomic()` block, so the closure must not touch `instance` and the predicate must be written unexcluded. Elapsed: eliminates the cascade leak and narrows the concurrent-insert race to query-plus-unlink. Cost: a shared key in a multi-row cascade is freed once per departing row, so the second call logs `WARNING "Photo not found (already deleted)"` and writes **no** `MediaDeletionError`. All 16 existing patch sites use single-row fixtures, so nothing breaks. Recorded in BLOCK 2b's binding constraint 4 and 8 and in the helper docstring. |
| **OC-2** | 3 | `FileExistsError` vs `os.replace` | `os.replace` **cannot** raise `FileExistsError` — the two are **mutually exclusive**. **(a)** Explicit pre-existence check before the replace: preserves the contract and `test_atomic_write_collision_raises_file_exists` unchanged, at the cost of a TOCTOU window and an extra stat per size. **(b)** Rewrite the contract: atomicity is kept and the check is dropped, but a **shipped green test** must be changed under project rule 2 and the reason named. No third option. | Implementor's Planner; recorded in BLOCK 3's commit body |
| **OC-3** | 5 | The single-variant cache check | **(a)** Extend it to all three variants — correct, but the check and `generate_thumbnails` must then agree on the size set, coupling the generator to the service. **(b)** Drop it and always regenerate — simplest and always truthful, at the cost of redundant work on every seeded photo. | **RESOLVED by Planner = (a) EXTEND**, repair path publishes with `WriteMode.REPLACE`. Decisive evidence: `_decide_write_mode` decides from `AdImage` **columns** and the seed path has **no row** at preprocessing time (`bulk_create` runs after `generate()` returns), so (b) cannot delegate to BLOCK 3's guard; and `CREATE_ONLY` iterates `SIZES` SMALL→MEDIUM→LARGE with `os.link`, so it aborts on the first **present** target and never reaches the missing one — (b) reproduces the defect or aborts the run. The size-set coupling is dissolved by deriving both sides from `ThumbnailSizeStrEnum`; the check doubles as the post-publish post-condition. `_clean()` rmtree's the seed dir per run, so the fast path's only value is within-run dedup — preserved because it costs 2 extra `stat()`s against a full re-encode. Recorded in BLOCK 5's Planner decision and commit body |
| **OC-4** | 6 | Obtaining a confirmed-deletion signal | `delete_photo` returns `None` and swallows failures. **(a)** Give `delete_photo` a return value — changes a shipped contract that eight tests monkeypatch with a stub returning `None`, so every stub must be updated. **(b)** Verify existence after the call in the sweep — leaves the contract alone, but the check is racy against a concurrent sweep. **(c)** Have `delete_photo` accept an optional callback — narrowest blast radius, but adds a parameter to a load-bearing function. | Implementor's Planner; recorded in BLOCK 6's commit body |
| **OC-5** | 8 | `HOURLY_COMMANDS` vs `DAILY_COMMANDS` | The source plan **contradicts itself** — its surface table says `HOURLY_COMMANDS`, its own correction says `DAILY_COMMANDS`. **(a)** Hourly matches every other retention/purge command and bounds the table fastest. **(b)** Daily matches the diagnostic nature of the table and adds least scheduler churn. Note `_validate_commands` does **not** raise on a missing entry, so a forgotten dispatch fails **silently**. | Implementor's Planner; recorded in BLOCK 8's commit body |
| **OC-6** | 11 | Which predicate is opened | With `has_delete_permission → False`, Django filters `delete_selected` **and** any `permissions=["delete"]` action. **(a)** Open `has_delete_permission` — one change, but it also re-enables `delete_selected`, i.e. bulk row deletion, which is a **larger** surface than intended. **(b)** Open only the action's `permissions` — keeps `delete_selected` filtered out, so the **only** delete path is the audited service; but it inverts the current admin convention. **Exactly one** may be opened. | Implementor's Planner, with phase 15 informed first; recorded in BLOCK 11's commit body |

---

## Proposed recorded values

The owner delegated two figures. Both are recorded here as **proposals** and may be overridden.

### BLOCK 7 — staging byte budget: **2 GiB** (`MEDIA_STAGING_BYTE_BUDGET`)

- **Arithmetic it must bound.** `MAX_PHOTO_BYTES` is 2 MB per photo; the FSM caps a dialog at 5 photos; the rate limiter allows 10 uploads / 60 s per user. That is ≈1.2 GB/hour for one account, ≈**2.4 GB** inside one 2 h `_STAGING_TTL_SECONDS` window — and the TTL is a **backstop**, not the control.
- **What legitimate traffic needs.** Worst case ≈11 MB per fully-staged dialog (one 2 MB original plus three derived sizes). **2 GiB is ≈180 concurrent fully-staged dialogs** of headroom — generous for a Telegram-driven board, and the number an operator can reason about.
- **Why it bites inside one window.** At 2 GiB the budget stops a single account **before** the TTL would, which is the entire point of making space the primary control and the TTL the backstop.
- **Why global.** The staging key is `<uuid4>.jpg` — deliberately PII-free. Per-seller attribution needs a key-format change that breaks unguessability and every key `CheckConstraint`. The fairness cost (a legitimate seller refused because an abusive account filled the volume) is **accepted and documented** in the commit body.
- **Shape.** A named Django setting (project rule 10), env-overridable so an operator can raise it without a code change. The check is **bounded** — a value the sweep already computes and the upload path **reads**, with a top-level `os.scandir` as fallback.

### BLOCK 8 — `MediaDeletionError` retention TTL: **30 days** (`--older-than` default)

- **The rows are diagnostic, not personal data.** `storage_key` is an unguessable UUID (or a `seed/` filename), `error_type` is a class name, and `error_message` is `str(exc)[:1000]` — a filesystem path under `MEDIA_ROOT`. No PII, so this is an operational-retention judgement, not a privacy one — which is why the number is a Planner's to propose rather than Legal's.
- **The query is index-backed.** `MediaDeletionError.Meta` indexes `created_at` **and** `error_type`, so the retention sweep does **not** seq-scan an unbounded table. The source plan's argument against an unindexed sweep does not apply here.
- **Why 30 days.** It matches retention vocabulary already in the project (`consent_hard_delete` uses a hardcoded 30 days), so an operator needs no new mental model. It is long enough that a **chronic** condition is visibly chronic across a monthly ops cycle, and short enough that the table cannot mask a signal. Under a persistent condition the table holds *N keys × 24 sweeps/day × 30 days* — bounded per key, not per second.
- **Why not 7 or 90.** 7 days is shorter than the review cycle in which a chronic condition would be noticed. Beyond 90 days buys nothing: the condition is **re-recorded hourly** while it persists, so a fresh row always exists regardless of age.
- **Shape.** `--dry-run` is mandatory and deletes nothing; a row inside the TTL survives with its message intact; the purge is **irreversible** and the commit body says so. **No alert ships** — the phase-12 predicate `MediaDeletionError.objects.filter(created_at__gt=now() - 1h).exists()` is recorded for phase 12 to consume.

---

## Coordinator notifications required

| When | Notification | Why |
|---|---|---|
| **Before BLOCK 8 touches `enums.py`** | The `AdvisoryLockId` allocation (**14**, re-read at that moment) | Phase 06 BLOCK 15 allocates from the same band. Two phases computing "the next free integer" concurrently means **one command silently never takes its lock** — `test_advisory_lock_ids.py` does not catch reuse. Three files in **one** commit. |
| **Before BLOCK 11 lands** | The `AdImageAdmin` delete surface and the **OC-6** predicate choice | Phase 15 owns the authorization predicate and its RBAC layer has **not** landed. A new delete surface with an unstated predicate forces phase 15 to re-derive it or reconcile two copies. |
| **During BLOCK 10** | The **routing package** for `technical-specification.md` — exact replacement text for the two stale sentences | Phase 06 holds the reservation and its own blocks edit the file. Phase 07 **routes, never edits**. |
| **During BLOCK 10** | The `edit.py` and `seller-stories.md` photo-edit corrections | Phase 05 owns that file's **behaviour** and the same photo-edit promise. A second editor re-reads; the second correction to overtake the first wins. |
| **During BLOCK 10** | The `docs/ops/docker-deployment.md` edit | The file is **dirty** with another phase's uncommitted account-state edits. The coordinator sequences the two. |
| **Before BLOCK 1 lands** | The `AD-003` retirement and the `AD-006`/`MEDIA-002` tie-breaker | Phase 05 must not ship the byte-copy fix or a competing half-fix to the same predicate. |
| **With BLOCK 7** | The staging-budget figure, and that **no gauge ships** | Phase 12 must not plan an alert on `staging_bytes` — the metric is deliberately **not** emitted (Q07-8: unexportable outside `web`). Phase 12 consumes the log reading instead. |
| **With BLOCK 6** | The dangling-row report predicate and scope | Phase 12's read surface. Scope **includes `seed/`**. |
| **With BLOCK 8** | The retention predicate | Phase 12's second read surface. No alert is built in phase 07. |
| **Before phase 03 is told anything** | BLOCK 1 prunes `permanent_keys` and targets `STAGING_PREFIX + key` | The external gate is **void** — phase 03's BLOCKS 6 and 8 landed — so this is a courtesy notification, not an approval. |
| **At plan close** | `03-DB-005`'s two record corrections (§5.6 of the source plan) | `DB-005` should not assert that detection is impossible — the detector is phase 07's BLOCK 6 — and should note the `deleted += 1` fix landed there rather than shipping it twice. |
| **At plan close** | `07-MEDIA-001` shipped **defective** and is repaired by BLOCK 2b | `db-retention.md` and `technical-specification.md` both cite it as a closed finding. The coordinator must know the shipped shape was incomplete. |

---

## Global DoD checklist

Corrected for the drift. The source plan's §8 is the baseline; every item below that differs is marked.

### Scope
- [ ] **11 blocks** executed: `2b, 1, 3, 4, 5, 6, 7, 8, 9, 10, 11`.
- [ ] **BLOCK 2 is marked shipped-but-defective**; BLOCK 2b closes its four-column gap. Do **not** record `07-MEDIA-001` as closed on the strength of `64a9de6` alone.
- [ ] **BLOCK 12 is DEFERRED** per Q07-6=(b) and was **not** built. `07-MEDIA-005` is closed on its **moderator** half only; the seller-facing half is closed by BLOCK 10's documentation correction, not by code.
- [ ] `07-MEDIA-003` remains merged into `03-DB-005` and is **not** re-filed.
- [ ] **All fourteen** `Q07-1` … `Q07-14` are answered in writing or explicitly routed. **Silence is not an acceptable outcome.** Gates pre-answered by ground truth this cycle: Q07-2 (option a), Q07-8 (no gauge), Q07-10 (**no** registry test), Q07-11 (measured **75**), Q07-13 (**duplicate**, no include).
- [ ] Every de-scoping has a named destination; none was dropped.
- [ ] `AD-003`'s retirement and the `AD-006`/`MEDIA-002` tie-breaker were **communicated**.

### Gates — all green
- [ ] `uv run ruff check src/` → exit 0. `uv run basedpyright src/` → **0 errors**.
- [ ] `.\Makefile.ps1 test` green after **every** block.
- [ ] `$dc run --rm test` — the **full** suite including the `seed` marker — green after **BLOCK 5** only. *This is the only block that requires it.*
- [ ] `test_i18n_completeness.py` green after BLOCKS 7 and 11. **BLOCK 12 no longer contributes.**
- [ ] **Every block's exact gate command was run and green** — not the full suite alone.
- [ ] `test_advisory_lock_ids.py` and `test_sweep_lock_structure.py` green after BLOCK 8, with the three lock files in **one** commit and **three** lists edited in the structure test.
- [ ] `test_scheduler_wiring.py` green after BLOCK 8.
- [ ] `test_delete_photo_single_call.py` green after **every** block touching a byte-freeing path — **BLOCKS 2b, 1, 3, 6, 7, 11**. *Corrected: BLOCK 2 is shipped; BLOCK 12 is deferred.*
- [ ] `makemigrations --check` clean — **no block expects a migration**, so a pending migration is a scope error. Check **before** BLOCK 8 given the stale `0003` `.pyc`.
- [ ] `nginx -t` passes for **both** configs after BLOCK 9.
- [ ] `git status --short .ai` shows no new modifications beyond the pre-existing `.ai/audit/**` deletions and this plan file.
- [ ] Every red-gate observation was **re-run serially** before being reported as a defect.
- [ ] No commit without explicit instruction; no `git reset` / `checkout` / `restore` / `stash` / `--amend` / force-push.

### Per-finding behavioural confirmation
- [ ] **`07-MEDIA-001`** — a key shared through **each** of the three thumbnail columns survives the other row's deletion; deleting the last referencing row frees it; `copy_ad` is unchanged. Verified through the signal, not only the helper.
- [ ] **`07-MEDIA-002`** — identical bytes to two ads of the same seller → both ads have exactly one image with **different** keys and **zero orphan files** after the reclaim; the same-ad duplicate still returns the existing row. `test_ad_image_service.py` untouched.
- [ ] **`07-MEDIA-004`** — a leftover `-small.jpg` against a `NULL` column is **regenerated**; populated plus existing is **skipped**; a failure on the second size leaves **no partial files**; a success leaves **no temp files**; a second run is a no-op.
- [ ] **`07-MEDIA-005`** — a staff moderator removes one photo: row gone, **exactly one** `ModeratorActionLog` row, ad/text/status/view count untouched; non-staff refused with nothing deleted and no audit row; **the shared-key case: the file still exists and the other ad's image still serves**; an empty reason is refused; the action appears in `get_actions(request)`. *No seller-facing bot assertion — BLOCK 12 is deferred.*
- [ ] **`07-MEDIA-006`** — **both** configs declare a script-execution `location` for `/media/` with `deny all` **and** `return 403`, as a **`~*`** match; both `/media/` locations carry a `limit_req` **reusing `browse_limit`**; the three existing `/metrics` assertions pass unchanged; `/protected-media/` untouched; **no new `limit_req_zone`**.
- [ ] **`07-MEDIA-007`** — an upload above the budget is refused with a message resolving in `ru` **and** `bs`; one under it is **accepted**; a refused upload writes **no file**; a fresh staging file is preserved and a stale one reclaimed; `_STAGING_TTL_SECONDS` byte-identical. **No gauge ships** and the Q07-8 rationale is recorded.
- [ ] **`07-MEDIA-008`** — after `ImageGenerator.generate`, **every** `thumbnail_*` on **every** created row points at a file that exists; a half-written state is **regenerated**; positions are **not** renumbered; the shipped (empty-`default`) manifest reconciles against its rows. Full suite green. The sweep's **deletion** scope unchanged.
- [ ] **`07-MEDIA-009`** — the ownership rule is stated as **shipped** (N ≥ 1 references, freed on the last) across **all four** columns with the cascade-leak bias stated honestly; the real key scheme is stated with the reason there is no `ad_id`; **no reach claim**; **no** "except `seed/`" placeholder; the photo-edit text says **price** in all locations and names the moderator/seller split; the nginx claim appears **only after** BLOCK 9. **Two** reserved locations routed with exact text and neither edited. *Corrected census: `db-retention.md` dropped; `technical-specification.md` reduced to two stale sentences.*
- [ ] **`07-MEDIA-010`** — `MediaDeletionError` reachable through the changelist with `created_at` and `error_type` filters and no editable field; `--dry-run` deletes nothing; a row inside the TTL survives with its message intact; a row past it is deleted; a second run is a no-op; the scheduler still starts. The new id is **14 or whatever is free at that moment**, `SWEEP_ORPHANED_MEDIA == 103` unchanged, `delete_photo`'s never-raise contract intact.
- [ ] **`07-MEDIA-011`** — the quality is **declared, named and used**, asserted by reading the constant the save call uses and **not** by asserting a literal; the eight `TestStripPhotoExif` and six `TestExifStripping` tests pass **unchanged**; the mixed-quality consequence is in the commit body; the spec sentences were **routed, not edited**.
- [ ] **`07-MEDIA-012`** — the check mode **reports** a row whose file is gone and **reports nothing** when store and database agree, with scope **including `seed/`**; the reported deletion count matches files actually removed; all **nine** existing sweep tests pass; and **the negative proof holds** — `media_gate` still returns `200` + `X-Accel-Redirect` for a shared key with **no file on disk**.

### Cross-phase integrity
- [ ] **No staging-window fix was shipped.** `plan_staging_promotion` / `promote_media_files` and the sweep's **deletion** scope are byte-identical to before. `_STAGING_TTL_SECONDS` unchanged. *Corrected: `move_staging_to_permanent` no longer exists; `03-DB-005` landed.*
- [ ] **No phase-03 contention** on `sweep_orphaned_media.py` — the external gate is satisfied and BLOCK 6 edits `SWEEP_COMMANDS` / `EXPECTED_SWEEP_COMMANDS` / `_LOCK_TARGET_MODULES` **nowhere**.
- [ ] `AdvisoryLockId.SWEEP_ORPHANED_MEDIA == 103` unchanged; `CONSENT_HARD_DELETE == 3` not renumbered; a new member exists only if BLOCK 8 required one, with three files in **one** commit and the coordinator notified **before**. **No id reused.**
- [ ] `technical-specification.md` and `db-retention.md` were **not edited** by any phase-07 block. *Corrected: `db-retention.md` needs no routing at all.*
- [ ] `AdAdmin`'s field set, fieldsets and permission predicates unchanged; `AdImageAdmin` changed **only** by BLOCK 11's action and **exactly one** predicate (OC-6).
- [ ] `copy_ad` unchanged; `test_copy_ad.py` passes unchanged; `AD-003` not resurrected.
- [ ] `delete_adimage_files_on_delete` still registered **by identity**, not renamed; `AdImage.storage_keys()`'s signature and order unchanged.
- [ ] `apps/moderation/admin_actions.py` unchanged — BLOCK 11 follows its pattern without modifying it.
- [ ] `media_gate` is **byte-identical** to before this plan: no filesystem check, no cache-header change, no application-level limiter. *Still true after the `vary_on_headers` / `Cache-Control` change, which predates this plan.*
- [ ] `/protected-media/` unchanged; no new `limit_req_zone` exists.
- [ ] `ThumbnailService.QUALITY == 85` unchanged; the EXIF/ICC strip is intact.
- [ ] `src/backend/conftest.py` is **unmodified**.
- [ ] Locale files were **appended** to, never regenerated wholesale; `ru` and `bs` non-empty for every new string; the ~1620 uncommitted lines from other phases survive.
- [ ] No alert, no notification, no new feature flag. No migration created, renumbered or edited.
- [ ] The audit tree shows no new modifications; no other phase's plan file was edited; **this plan file is the only file created or modified** by the Planner.

### Project conventions
- [ ] Every new constant is a named module-level constant, a `StrEnum`/`IntEnum` member, or a Django setting — never an inline literal or a dict of strings.
- [ ] No `print()`; `logger = logging.getLogger(__name__)` with lazy `%s` formatting.
- [ ] English only.
- [ ] Pydantic v2 appears only at a system boundary; none added to a view, service or handler. `apps/media/schemas.py::SubmittedPhoto` was followed, not copied inward.
- [ ] Business logic lives in `services/`; no new logic in a view or handler beyond the thin boundary change its block requires.
- [ ] Filesystem side effects happen only **after** commit via `transaction.on_commit()`.
- [ ] Every non-trivial behaviour change has a test verifying **logic and component interaction** — not a variable's absence, not a log string, not a line count, not a hard-coded quality number. BLOCK 4's single property test is justified in place; BLOCK 10 adds **no** behavioural test by design.
- [ ] **No task target is a line number.** Every target is a file plus a semantic symbol. Line numbers appear in this plan only as quoted evidence.
- [ ] `ruff check --fix src/` if imports were reordered (`ruff format` is **not** the convention).
- [ ] Every new finding citation is cycle-scoped `07-MEDIA-0NN`; no bare `MEDIA-0NN` and no new prior-cycle id.

---

## Risk register

Severity is **execution risk for the change**, not the finding's severity. "FS↔DB" covers filesystem-versus-database consistency. "Lock" covers advisory-lock allocation. "Txn" covers `atomic()` nesting. "Contention" covers shared files. "URL" covers any change to a served URL shape. "Irreversible" covers one-way data effects.

| Block | Risk | Kind | Likelihood | Impact | Mitigation / detection | Residual |
|---|---|---|---|---|---|---|
| **All** | An implementor runs `git add -A` and commits the 19 pre-existing `.ai/audit/**` deletions or another phase's uncommitted work | Process | Med | **High** | Explicit-path staging; `git status --short` immediately before **every** commit; the audit tree is unmodifiable by mandate | Very low |
| **All** | A block runs with an open choice unanswered, or the Implementor silently picks one | Process | Med | **High** | All six OCs are in the register above with the resolving agent named; the commit body is the record | Low |
| **All** | Tests are **asserted** rather than **run**, or run on the host where there is no database | Process | Med | **High** | Every block names its exact `$dc` gate; tests run **only** through the `test` service | Low |
| **All** | A red gate is captured while another phase's validator runs and a teardown race is reported as a product defect | Process | **High** | Med | Re-run **serially** before reporting. Symptom: `test_mko_bazuna does not exist` | Low |
| **All** | A **shipped green test** that pins a defect is "fixed" by changing production code | Correctness | Med | **High** | Project rule 2 restated. Only **two** assertions are slated for treatment, each named: `test_atomic_write_collision_raises_file_exists` (BLOCK 3, **only** under OC-2 option b) and `test_seed_original_strips_jpeg_comment` (BLOCK 5, return contract). C-2 shows `MEDIA-002` needs **none**, and Q07-10 shows BLOCK 8 needs **none** | Low |
| **All** | A new user-visible string ships without non-empty `ru` **and** `bs` | i18n | Med | Med | Only BLOCKS 7 and 11 add strings (**BLOCK 12 deferred**); each names the locale files and the append-only rule | Low |
| **All** | The audit's refuted claims are repeated by an implementor who read only the source plan | Correctness | **High** | Med | The ground-truth corrections are restated in each affected block's "what is wrong"; the negative test in BLOCK 6 and the manifest test in BLOCK 5 are the tripwires | Low |
| **2b** | The four-column fix is applied but the cascade leak is neither fixed nor documented | Correctness | Med | Med | Binding constraint 8; the leak is an explicit test case; OC-1 forces the choice into the open | Low |
| **2b** | The helper is extracted but the signal keeps a second, divergent check | Correctness | Med | **High** | Binding constraint 1 (single owner); test 5 exercises the helper **through** the signal | Very low |
| **2b** | Removing the module-level `delete_photo` binding breaks the string-keyed monkeypatch | Correctness | Med | Med | Binding constraint 2; `test_delete_photo_single_call.py` is in the gate command and the keep-green list | Very low |
| **1** | The reclaim deletes inside `transaction.atomic()` and a rollback leaves a row with a **missing** file | FS↔DB · Txn | Low | **High** | Q07-3 is settled: the reclaim is `on_commit`-only. Test 3 encodes the guarantee and names it | Very low |
| **1** | The reclaim targets the permanent key instead of the staging path — a **silent no-op** that leaves four orphans per occurrence | FS↔DB | Med | **High** | Binding constraint 3, stated with the shipped `plan_staging_promotion` reality; test 1 asserts **zero orphan files** | Low |
| **1** | `submit_ad` is edited on a stale read and a concurrent phase's change is clobbered | Contention | **High** | Med | Re-read immediately; stage explicitly; **stop and report** rather than clobber | Med — accepted |
| **3** | OC-2 is resolved as "keep raising `FileExistsError`" **without** the pre-existence check, so `os.replace` silently overwrites | Correctness · FS↔DB | Med | **High** | The two options are stated as mutually exclusive in the register; `test_atomic_write_collision_raises_file_exists` is in the gate command and is the tripwire | Low |
| **3** | Temp files land in a system temp dir, so `os.replace` degrades to a cross-device copy | FS↔DB | Med | Med | Binding constraint 2; the all-or-nothing test asserts no temp file survives | Low |
| **3** | `submit_ad`'s blanket `except Exception` is narrowed and turns a successful publish into an exception | Regression · Txn | Med | **High** | The catch decision is an explicit sub-decision with both outcomes written out; `submission.py`'s phase-05 reservation applies | Low |
| **4** | The value is changed "while we are here", re-encoding every new upload | Regression | Med | Med | Binding constraint 3; the mixed-quality consequence is required in the commit body | Low |
| **4** | The test asserts a literal `75`, converting an inherited measurement into a contract | Correctness | Med | Med | Binding constraint 4; the test reads the constant the save call uses | Low |
| **5** | OC-3 picks "extend", coupling the generator's cache check to the service's size set | Design | Med | Low | The coupling is recorded in the commit body; the two sets must agree and a test pins it | Low |
| **5** | The fix renumbers `position`, collapsing deliberate gaps | Correctness | Med | Low | Binding constraint 1; test 3 asserts gaps remain and are valid under `uq_ad_images_ad_position` | Very low |
| **5** | The plan's NULL-thumbnail test is written anyway, against a subject that does not exist | Process | Med | Low | Stated explicitly in "what is wrong" and forbidden by the binding constraints | Very low |
| **6** | Detection leaks into `media_gate` and breaks ~28 tests across four classes | Correctness | Med | **High** | Binding constraint 1; test 2 is the **mandatory** negative proof; `test_media_security.py` is in the gate command | Very low |
| **6** | The report scope excludes `seed/`, reproducing the exact defect `VAL-005` records | Correctness | Med | Med | Binding constraint 2; test 1 is the tripwire and fails if the scope excludes `seed/` | Low |
| **6** | OC-4 changes `delete_photo`'s contract and breaks eight monkeypatch stubs | Correctness | Med | Med | All three options are costed in the register; the commit body names the mechanism | Low |
| **6** | A merge conflict with phase 03 on `Command.handle` | Contention | **Low** | Med | **Retired** — phase-03 BLOCKS 6 and 8 landed; the file is clean | Very low |
| **7** | A **global** budget refuses a legitimate seller because an abusive account filled the volume | Product | **High** | Med | Test 2 asserts the positive case explicitly; the fairness cost is **accepted** and named in the rollback section | Med — accepted |
| **7** | The per-upload check walks the staging tree, adding cost to the hot upload path | Performance | Med | Low | Binding constraint 1 (bounded; prefer the sweep's existing figure) | Low |
| **7** | A wholesale `makemessages` destroys ~1620 uncommitted locale lines from other phases | i18n · Contention | Med | **High** | Binding constraint 8; append-only; the files are dirty and the hazard is named in the block | Low |
| **7** | A gauge is emitted and phase 12 alerts on a signal nobody can scrape | Observability | Med | Med | Q07-8 recorded; **no gauge ships**; the log reading and the rationale go in the commit body | Low |
| **8** | The new `AdvisoryLockId` **reuses** a value and two commands serialise silently | Correctness · Lock | Low | **High** | `test_advisory_lock_ids.py` does **not** catch reuse — stated in the block. Id **14** re-read at allocation; three files, one commit; coordinator told first | Very low |
| **8** | Phase 06 BLOCK 15 allocated the same integer in between | Lock · Contention | Med | **High** | The coordinator sequences the two allocations; this is the block's first notification | Low |
| **8** | The TTL is invented rather than recorded and purges diagnostic rows an operator still needs | **Irreversible** | Med | Med | The TTL is **proposed and reasoned** above; `--dry-run` is mandatory; a row inside the TTL is proven to survive; a revert does **not** restore purged rows | Low |
| **8** | The `HOURLY_COMMANDS` entry is forgotten and `_validate_commands` does not raise | Correctness | Low | Med | OC-5 forces a written answer; `test_scheduler_wiring.py` is in the gate command and the keep-green list | Very low |
| **8** | A pending migration from the stale `0003` artefact is mistaken for the block's own | Process | Low | Med | Binding constraint 11: `makemigrations --check` clean **before** starting | Very low |
| **9** | A regex typo in the script-execution block **403s every genuine photo** — a site-wide image outage | Regression | Med | **High** | The harness asserts the block exists and carries `deny all` and `return 403`; `nginx -t` for both; the **irreducible** deployed-stack real-key smoke check is a recorded operator step | Med — accepted |
| **9** | The added block shadows `location /media/`'s `proxy_pass`, so no image is proxied | Regression | Low | **High** | Test 1 asserts the `~*` match, a real nginx semantic rather than a substring; `_location_block`'s first-match behaviour is addressed by positioning | Very low |
| **9** | The block is given a `proxy_pass` and the existing proxied-locations test fails | Correctness | Low | Med | Binding constraint 3; `test_proxied_locations_overwrite_x_real_ip` is in the keep-green list | Very low |
| **10** | The ownership rule is written describing the source plan's **text** rather than what BLOCK 2b actually ships | Documentation | Med | Med | Binding constraint 2 — re-read it, it now specifies the **post-commit** evaluation; the hard edge on BLOCK 2b; a Validator read-through against the named symbols | Low |
| **10** | A reserved file is edited instead of routed and a concurrent phase loses its work | Contention | Med | **High** | Binding constraints 7 and 9; the deliverable for reserved files is a **written request** | Low |
| **10** | The dirty `docs/ops/docker-deployment.md` is clobbered by another phase's account-state edits | Contention | Med | **High** | Binding constraint 8: append-only, re-read immediately, **stop and report**; the coordinator sequences the two | Low |
| **10** | The census is taken from the source plan and misses locations, producing a half-fix | Documentation | **High** | Med | The Auditor's full re-census is the block's **first task**; the plan's premise is recorded as false | Low |
| **10** | The nginx block is claimed before BLOCK 9 lands | Documentation | Low | Med | Hard edge BLOCK 9 → 10; binding constraint 11 | Very low |
| **11** | The service calls `delete_photo` directly and becomes a **second data-loss route** | FS↔DB | Med | **High** | Hard edge BLOCK 2b → 11; binding constraint 1; test 3 is the tripwire and fails if the service bypasses the invariant | Low |
| **11** | The delete surface is ungated or unaudited | Security | Med | **High** | All five agents required; tests 1, 2 and 5; phase 15 is told **before** the block lands | Low |
| **11** | The action is decorated but filtered out by `get_actions` — a decorated-but-invisible action | Correctness | Med | Med | OC-6 forces exactly one predicate to be opened; test 5 introspects `get_actions(request)`, never source flags (`VAL-006`) | Very low |
| **11** | A free-text reason is stored and phase 06's reason-redaction later has to handle existing rows | Design | Med | Low | Binding constraint 7: a **canned** reason with `ModeratorActionType.OTHER`, sidestepping redaction entirely | Low |
| **11** | Bulk `delete_selected` is re-enabled as a side effect of opening `has_delete_permission` | Security | Med | **High** | OC-6 option (a) is costed explicitly; whichever is chosen is recorded and introspected in a test | Low |