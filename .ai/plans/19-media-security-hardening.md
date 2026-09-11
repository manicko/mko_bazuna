---
id: media-security-hardening
domain: plan
tags:
  - media-security
  - me-001
  - me-002
  - me-003-secondary
  - me-004
  - me-005
  - me-006
  - path-traversal
  - rate-limiting
  - decompression-bomb
  - media-gate
  - delete-photo
  - process-photos
related:
  - .ai/audit/99-validation/07-media-validated-findings.md
  - .ai/plans/code-context-media-07.md
  - src/backend/apps/media/services/filesystem.py
  - src/backend/apps/ads/models.py
  - src/backend/apps/ads/views/listings.py
  - src/telegram_bot/handlers/ad_create.py
  - src/telegram_bot/services/rate_limit.py
  - src/backend/apps/analytics/models.py
  - docs/99-agent/architecture.md
  - docs/99-agent/rules.md
---

# Media Security Hardening — Execution DAG

**Source findings:** ME-001 (CRITICAL), ME-002 (HIGH), ME-003-secondary (advisory),
ME-004 (HIGH), ME-005 (MEDIUM, advisory), ME-006 (HIGH) — all validated in
`.ai/audit/99-validation/07-media-validated-findings.md`.

**Status snapshot:** ENT-001 relocation, NEW-ME-007, PC-004, and 2/7 ME-002 sweeps
are **already committed**. Six findings remain OPEN — decomposed into five
execution blocks below.

---

## 1. Execution Graph (dependency-ordered)

```
Block 0  ME-003-secondary Research Gate     ✅ (Researcher)     [resolved: Option B — MediaDeletionError model]
         Must resolve the event-emission approach before the delete_photo PR.

Block 1  ME-001 — Path Traversal Hardening    ⏳ (Implementor)     [Block 0]
          Primary CWE-22 boundary: containment in delete_photo,
          model validators/constraints on AdImage fields, save() guard,
          media_gate/_serve_image containment, migration, regression test.

Block 2  ME-003-secondary — Error Escalation  ⏳ (Implementor)     [Block 0, same PR as Block 1]
          Escalate logger.error → structured event on retry exhaustion.

Block 3  ME-002 — Sweep Thumbnail Cleanup    ⏳ (Implementor)     [Block 1]
          5 remaining sweeps → AdImage.storage_keys() instead of
          values_list("image", flat=True). Regression test for thumbnails.

Block 4  ME-004 + ME-006 — Upload Flow Guard  ⏳ (Implementor)     [no deps]
          Same PR — both modify process_photos. Count cap + rate limiter.
          Parallel-safe with Blocks 1–3 (different code paths).

Block 5  ME-005 — Decompression Bomb           ⏳ (Implementor)     [no deps]
          Set Image.MAX_IMAGE_PIXELS. Advisory, low-risk.
          Parallel-safe with Blocks 1–4.
```

**Parallelization:** Blocks 4 and 5 are independent of Blocks 1–3 and may be
executed in parallel. Block 2 is packaged with Block 1 in a single PR (same
function, same file). Block 3 is blocked on Block 1 only — the model-level
validators and constraints added in ME-001 ensure that thumbnail keys passed
to `delete_photo` during sweeps are traversal-safe at rest.

---

## Already Done (verified in working tree)

| Item | Location | Evidence |
|---|---|---|
| ENT-001 | `apps/media/services/filesystem.py` | `delete_photo` relocated; all 7 backend import sites use `from apps.media.services.filesystem import delete_photo`; old bot-path removed |
| NEW-ME-007 | `enums.py`, `sweep_orphaned_media.py` | `SWEEP_ORPHANED_MEDIA=103`, `CATALOG_LOAD=104`; sweep uses `delete_photo` (not `os.remove`); scheduled in `entrypoint-scheduler.sh`; tests present |
| PC-004 | `ads/models.py` | `AdImage.storage_keys()` at `AdImage` class; `test_adimage_storage_keys.py` (5 unit tests) |
| ME-002 partial (2/7) | `consent_hard_delete.py`, `deletion.py` | Both use `img.storage_keys()` list-comprehension pattern; tests in `test_sweep_commands.py:test_collects_thumbnail_keys_for_media_cleanup` and `test_deletion.py:test_withdraw_returns_all_thumbnail_storage_keys` |

---

## Block 0 — ME-003-secondary Research Gate ✅ RESOLVED

**Status:** ✅ COMPLETE · **Agent:** Researcher · **Outcome:** Option B selected

**Selected approach:** Dedicated `MediaDeletionError` model in `apps/media/models.py`
- `AnalyticsEvent` rejected: no payload field (5 cols only), `record_event` silently swallows failures (wrong vehicle for error observability), no media event type, `delete_photo` has no user_id/ad_id in scope
- No non-DB telemetry exists (no sentry/prometheus/structlog/JSON logging config) → structured logging has no consumer
- Option D rejected: sweep backstop recovers orphan *files* but provides zero visibility into *why/how often* deletions fail
- **Spec:** New `MediaDeletionError` model (`storage_key` TextField, `error_type` CharField 120, `error_message` CharField 1000, `attempts` PositiveSmallIntegerField, `created_at` auto_now_add); best-effort `try/except` recording that preserves `delete_photo`'s "never raise" contract; all 9 callers run outside `transaction.atomic()`; first migration `apps/media/migrations/0001_initial.py` (media app has no models/migrations yet)
- **Full recommendation:** `.ai/research/07-media-error-escalation.md`

### Scope (investigation only — no code changes)

- `apps/analytics/models.py` — `AnalyticsEvent` model (5 fields: `event_type`, `timestamp`, `user` FK, `ad` FK, `source`)
- `apps/core/enums.py` — `AnalyticsEventType` StrEnum (16 members; none relate to media/file deletion)
- `apps/media/services/filesystem.py` — `delete_photo` retry-exhaustion path (the `logger.error` call at the exhausted-retry branch)
- `ad/apps/analytics/services/` — how existing analytics events are created and consumed (to match the established pattern)
- Any non-DB telemetry/logging infrastructure (if one exists, the findings' "e.g. AnalyticsEvent" is just a suggestion)

### Preconditions

None.

### Why this block

The validated findings recommend escalating `delete_photo`'s exhausted-retry
`logger.error` to a "structured metric/event (e.g. AnalyticsEvent)" but list
`AnalyticsEvent` as an *example*, not a decision. This is the only finding in
the plan with genuine technical uncertainty:

1. **`AnalyticsEvent` has no metadata field** — the model is a 5-column table
   (`event_type`, `timestamp`, `user`, `ad`, `source`). A media-deletion
   failure needs to capture at minimum the `storage_key` and the `OSError`
   message, neither of which maps to any existing column. The model schema
   does not support `extra_data` / `jsonb` / `message` fields.

2. **No media-deletion event type exists** — `AnalyticsEventType` covers
   registrations, ad lifecycle, search, moderation, contacts, trust, but has
   zero failure/infra-event members. Adding one is a schema+enum change
   requiring a migration and `fill`-/backfill considerations.

3. **Alternative approaches unverified** — a structured `logger.error(...)`
   with a recognizable format might suffice as "structured enough" for log
   scraping / alerting; or a dedicated `MediaReaperEvent` model might be
   cleaner than overloading `AnalyticsEvent`; or the sweep backstop
   (`sweep_orphaned_media`) already provides eventual reconciliation, making
   per-failure events lower-value.

### Decision gate

The Researcher must determine and document:
- Whether `AnalyticsEvent` is the right vehicle (requires new enum member +
  schema extension for error payload), or whether a simpler structured log /
  dedicated model is more appropriate.
- Exact `AnalyticsEventType` member name(s) to add (if using `AnalyticsEvent`).
- What data to capture (storage_key hash? error class? attempt count?).

**Outcome blocks:**
- If `AnalyticsEvent` is chosen: Block 2 proceeds to add a new
  `AnalyticsEventType.MEDIA_DELETE_FAILED` member + use the `ad`/`source`
  fields if applicable, plus any migration needed for metadata.
- If a simpler approach is chosen: Block 2 proceeds with structured logging or
  a lighter-weight signal.

### Uncertainty flags

- **HIGH:** No existing event-type member covers media/infra failures. The
  `AnalyticsEvent` model has no arbitrary-payload field — storing
  `storage_key` or error text requires a schema decision.
- **MEDIUM:** Whether the `sweep_orphaned_media` backstop (Block 0 in NEW-ME-007, already done) already provides sufficient observability coverage — if so, per-failure events may be lower priority than the findings' "secondary" classification implies.

---

## Block 1 — ME-001: Path Traversal Hardening (CRITICAL)

**Status:** ⏳ REMAINING · **Agent:** Implementor · **Risk:** HIGH
**PR packaging:** Blocks 1 + 2 in the same PR (both modify `delete_photo`)

### Scope

1. **`delete_photo` containment check** — `apps/media/services/filesystem.py`
   - Canonicalize: `resolved = os.path.realpath(os.path.join(MEDIA_ROOT, storage_key))`
   - Assert: `resolved` starts with `os.path.realpath(MEDIA_ROOT)` + `os.sep`
   - Reject early: keys containing NUL bytes, leading `/`, or `..` path segments
   - Must preserve existing retry/backoff behavior and the `FileNotFoundError`
     terminal handling — containment check happens before the retry loop
   - **Do NOT** remove or alter the retry loop; the containment check is a
     pre-condition guard before `os.remove`

2. **`AdImage` model field validators** — `apps/ads/models.py`
   - Add `RegexValidator` to `image`, `thumbnail_small`, `thumbnail_medium`,
     `thumbnail_large` fields with pattern:
     `^[A-Za-z0-9][A-Za-z0-9._-]*(/[A-Za-z0-9][A-Za-z0-9._-]*)*\.jpg$`
   - This is **defense-in-depth** (prevents poisoned keys at rest), NOT the
     primary security boundary. The `delete_photo` containment check is the
     real boundary.
   - Follow the existing `RegexValidator` pattern already in
     `apps/core/models.py:bot_username` field

3. **`AdImage.CheckConstraint`** — `apps/ads/models.py` / `AdImage.Meta`
   - Add a `CheckConstraint` to `AdImage.Meta.constraints` (currently
     `Meta` has only `db_table` + `ordering`) enforcing the same key format
     at the DB level for all 4 fields
   - Follow the existing `CheckConstraint` pattern on the `Ad` model
     (16 constraints already in `Ad.Meta`)
   - **Requires a migration** — new DB-level constraint

4. **`AdImage.save()` containment guard** — `apps/ads/models.py`
   - The `save()` method builds `os.path.join(media_root, self.image)` for
     SHA-256 computation with no containment check
   - Add a `_assert_storage_key_contained()` guard (shared helper, also used
     by `delete_photo`) or inline `os.path.realpath` containment assertion
     before the file-exists check in `save()`

5. **Serving-path containment** — `apps/ads/views/listings.py`
   - `media_gate` view: the existing control-character check (`any(ord(ch) < 0x20)`)
     rejects NUL but does NOT prevent `../`. Add `os.path.realpath` containment
     assertion on the resolved path before serving, in addition to the existing
     DB-exists lookup (which is NOT the security boundary)
   - `_serve_image` helper: add the same containment guard before `open()`
   - `X-Accel-Redirect` header: the raw `image_key` is passed to nginx — add
     containment check before constructing the redirect URL

6. **Regression test** — `apps/ads/tests/test_media_security.py`
   - Add a test that injects a poisoned `AdImage.image` value (e.g.
     `../../../etc/passwd.jpg`) into a real DB row, then calls `delete_photo`
     and asserts it does **not** delete files outside `MEDIA_ROOT` (the
     containment check raises or skips)
   - Add a test that a valid key (UUID pattern) still deletes successfully
   - Add a test that `media_gate` rejects a crafted `image_key` containing
     `../` even if no matching `AdImage` row exists

### Preconditions

- Block 0 completed (ME-003-secondary approach decided — both blocks share `delete_photo` in the same PR, so the Researcher decision on the error-escalation approach must be known before writing the combined PR)

### Why this block

ME-001 is the **primary CWE-22 path-traversal boundary**. The current `delete_photo`
joins `MEDIA_ROOT` + `storage_key` and calls `os.remove` with zero canonicalization.
Any poisoned `AdImage.image` value (possible via seed/import/admin writes) escapes
`MEDIA_ROOT`. The validated findings identify this as the root-cause for
ME-001, ME-002 (same unvalidated field for thumbnails), and the serving path
in `media_gate`/`_serve_image`.

The model-level `RegexValidator` + `CheckConstraint` is defense-in-depth: it
prevents poisoned keys from persisting in the DB at rest, which makes ME-002's
propagation of `storage_keys()` into sweeps safe-by-construction (ME-002 depends
on ME-001 per the plan's ordering constraint).

### Risk gates

- **Migration:** New `CheckConstraint` on `AdImage` requires a DB migration;
  verify no existing data violates the regex (seed image keys use UUID pattern
  or `seed/<name>.jpg`, both conform). If any existing key violates the regex,
  the migration must handle backfilling or use a `NOCHECK` strategy.
- **Serving path:** `_serve_image` is the dev-only fallback (DEBUG=True);
  `media_gate` is the production path (X-Accel-Redirect). Both must be hardened.
- **Bot import:** `ad_create.py` imports from `apps.media.services.filesystem`
  — verify the bot process can reach the backend module at runtime (already
  true post-ENT-001).

---

## Block 2 — ME-003-secondary: Escalate Deletion Failures (advisory)

**Status:** ⏳ REMAINING · **Agent:** Implementor · **Risk:** LOW-MEDIUM
**PR packaging:** Blocks 1 + 2 in the same PR (both modify `delete_photo`)

### Scope

1. **`delete_photo` error escalation** — `apps/media/services/filesystem.py`
   - In the exhausted-retry branch (currently `logger.error(...)` then `return`),
     emit a structured event/metric instead of (or in addition to) the plain log.
   - **Exact mechanism is decided by Block 0 (Researcher).** This block's
     implementation is contingent on the Researcher's recommendation:
     - If `AnalyticsEvent` is chosen: add `AnalyticsEventType.MEDIA_DELETE_FAILED`
       to the enum, create an `AnalyticsEvent` row with `storage_key` (truncated
       or hashed to avoid PII — though keys are UUIDs, not PII), and capture the
       error class/message. May require a schema extension for an error-payload
       field (see Block 0 uncertainty).
     - If structured logging is sufficient: emit a `logger.error` with a
       machine-parseable format including key, error type, and attempt count.
     - If a dedicated model is recommended: define it per the Researcher's spec.

2. **No regression test** — ME-003-secondary is advisory; the escalation is an
   observability improvement on the error path. A light assertion (e.g. "event
   created on retry exhaustion") is warranted only if the Researcher chooses
   the `AnalyticsEvent` path (medium surface area).

### Preconditions

- Block 0 completed (approach decided)
- Block 1 completed (same PR — `delete_photo` is modified by both blocks)

### Why this block

The validated findings flag `delete_photo`'s retry-exhaustion path as swallowed:
after 3 attempts, `logger.error(...)` and `return` — no retry queue, no
observable metric. A failed physical deletion leaves an orphan file invisible
between hourly `sweep_orphaned_media` runs. Escalating to a structured event
makes transient failures observable for ops.

### Uncertainty flags

- **CONTINGENT on Block 0:** The implementation approach is entirely determined
  by the Researcher's decision. This block's scope item (1) is a placeholder
  that will be refined after Block 0 delivers its recommendation.

---

## Block 3 — ME-002: Sweep Thumbnail Cleanup (HIGH)

**Status:** ⏳ REMAINING · **Agent:** Implementor · **Risk:** LOW-MEDIUM
**PR packaging:** Standalone (no shared function with other findings)

### Scope

1. **Update 5 sweep commands** — each currently collects only
   `values_list("image", flat=True)` and passes keys to `delete_photo`:

   | Command | File | Current pattern |
   |---|---|---|
   | `delete_sweep` | `apps/core/management/commands/delete_sweep.py` | `values_list("image", flat=True)` |
   | `purge_deleted_ads` | `apps/core/management/commands/purge_deleted_ads.py` | `values_list("image", flat=True)` |
   | `purge_rejected_ads` | `apps/core/management/commands/purge_rejected_ads.py` | `values_list("image", flat=True)` |
   | `purge_failed_ads` | `apps/core/management/commands/purge_failed_ads.py` | `values_list("image", flat=True)` |
   | `sweep_drafts` | `apps/core/management/commands/sweep_drafts.py` | `values_list("image", flat=True)` |

   **Required change in each:** Replace the `values_list("image", flat=True)`
   collection with the `storage_keys()` list-comprehension pattern already
   established in `consent_hard_delete.py` and `deletion.py`:

   ```python
   storage_keys = [
       key
       for img in AdImage.objects.filter(ad_id__in=ad_ids)
       for key in img.storage_keys()
   ]
   ```

   This collects `image` + `thumbnail_small` + `thumbnail_medium` +
   `thumbnail_large` (truthy only) per `AdImage` row, ensuring thumbnail files
   are not orphaned on disk during retention sweeps.

2. **Regression test** — `apps/core/tests/test_sweep_commands.py`
   - Add a `test_collects_thumbnail_keys_for_media_cleanup` test (mirroring
     the existing one for `consent_hard_delete`) for **each** of the 5 sweep
     commands: create an `AdImage` with all 4 keys set, monkeypatch
     `delete_photo`, run the command, assert all 4 keys were passed to
     `delete_photo`
   - Verify the existing `len(storage_keys)` log count now reflects 4× the
     image count (not 1×)

### Preconditions

- Block 1 completed — ME-001's `RegexValidator`/`CheckConstraint` on
  `thumbnail_*` fields guarantees that thumbnail keys in the DB are traversal-safe
  before they're passed to the hardened `delete_photo`

### Why this block

Every retention/PII sweep currently deletes only the main `image` key, leaving
three thumbnail files (`-small.jpg`, `-medium.jpg`, `-large.jpg`) orphaned on
disk per `AdImage`. The `storage_keys()` method (PC-004, already implemented
at `AdImage.storage_keys()`) returns all 4 keys. Two sweeps already use it
(`consent_hard_delete.py`, `deletion.py`); five remain. This collapses 7
maintenance points into 1 model method, eliminating drift.

The `sweep_orphaned_media` backstop (NEW-ME-007, already done) will eventually
reclaim these orphans, but it runs hourly — explicit cleanup in each sweep
ensures prompt reclamation and keeps the DB/file-system consistent within the
sweep's own transaction window.

### Risk gates

- **Deduplication:** Seed thumbnails are shared across ads and are NOT stored in
  `AdImage` rows. The sweep excludes `seed/` — verify this exclusion is
  preserved when switching to `storage_keys()`. The `sweep_orphaned_media`
  command already handles this via its `_SEED_SUBDIR` exclusion, but the
  individual sweeps operate on `AdImage` rows only (no seed data), so no
  special handling is needed in the 5 sweep files.
- **Performance:** Iterating `AdImage` instances (vs. `values_list`) adds one
  Python object per row. For large sweeps (thousands of ads), verify the
  `iterator()` / chunk pattern isn't needed — these sweeps already load `ad_ids`
  into memory and filter by `__in`, so the instance iteration is O(n) in memory
  and acceptable for the 4-month retention windows.

---

## Block 4 — ME-004 + ME-006: Upload Flow Guard (HIGH)

**Status:** ⏳ REMAINING · **Agent:** Implementor · **Risk:** MEDIUM
**PR packaging:** Blocks 4 + 6 in the same PR (both modify `process_photos`)

### Scope

1. **Hard count cap before download** — `apps/ads/handlers/ad_create.py` (`process_photos` function)
   - Add `if len(photos) >= 5:` check **before** the `download_photo` call
   - Reject with message: `"You have sent 5 photos. Send 'done' to finish, or /cancel to abort."`
   - This prevents the post-5th-photo orphan file problem: photos are saved to
     disk via `save_photo` before the `PhotoCountPayload` validation at "done"

2. **Fix inverted error message** — `apps/ads/handlers/ad_create.py` (`process_photos` function)
   - Current message (at the "done" handler): `"Please send at least 1 photo (you have {count})."`
   - The `PhotoCountPayload` validator (`photo_count: Annotated[int, Field(ge=1, le=5)]`)
     rejects both `count=0` and `count>5` with the same message
   - Fix: when `count > 5`, message must say "maximum 5 photos"; when `count=0`,
     message must say "at least 1 photo"
   - Split the "done" handler into two distinct error paths

3. **Wire rate limiter** — `apps/ads/handlers/ad_create.py` (`process_photos` function)
   - Import: `from telegram_bot.services.rate_limit import check_upload_rate_limit`
   - Call `check_upload_rate_limit(user_id)` **before** `download_photo` (after
     retrieving `user_id` from FSM state via `data.get("user_id")` — already
     used at `data["user_id"]` in `create_draft_ad` flow)
   - If `False`: respond with `"Uploading too fast, please wait a moment."` and return
   - The `user_id` is available in FSM state (set by `cmd_post` at state initiation)

4. **Unit test for rate limiter** — `telegram_bot/tests/test_rate_limit_service.py`
   - Add `TestUploadRateLimit` class mirroring the existing
     `TestContactStartRateLimit`: 10 allowed, 11th blocked, per-user isolation,
     custom limit/period kwargs

5. **Bot handler test for upload cap + rate limit** — `telegram_bot/tests/test_ad_create.py`
   - Test that the 6th photo upload is rejected before `download_photo` is called
   - Test that a rate-limited user receives the cooldown message
   - Mock `download_photo` and `save_photo` to avoid real Telegram/file I/O

### Preconditions

- `check_upload_rate_limit` exists and is tested in isolation (Block 4, sub-task 4)
   — the function is already implemented at `rate_limit.py`; only the call-site is missing

### Why this block

ME-004: Without a pre-download count cap, a user can upload unbounded photos
(each ~2MB), wasting disk and CPU. The only existing 1–5 enforcement
(`PhotoCountPayload`) fires at "done" — AFTER photos are already written.
Photos beyond the 5th become orphans (no `AdImage` row is ever created).

ME-006: The `check_upload_rate_limit` function (10 req/60s) is fully implemented
using the atomic `cache.add`/`cache.incr` pattern but has **zero call sites**.
Wiring it into `process_photos` provides burst-abuse protection. The parallel
search-side rate limiter (`apps/search/services/rate_limit`) is already in use,
so this follows an established pattern.

### Risk gates

- **FSM state access:** `user_id` must be confirmed available in `process_photos`'s
  `data` dict. Verified: `cmd_post` sets `data["user_id"]` at FSM initiation;
  `process_photos` reads `data = await state.get_data()` at entry.
- **Rate limiter semantics:** The `cache.add`/`incr` pattern means the first
  request creates the key (count=1), subsequent requests increment. The check
  `current <= limit` allows exactly `limit` requests. The 11th is blocked.
  Verify this matches the existing `TestContactStartRateLimit` behavior.

---

## Block 5 — ME-005: Decompression Bomb Protection (MEDIUM, advisory)

**Status:** ⏳ REMAINING · **Agent:** Implementor · **Risk:** LOW
**PR packaging:** Standalone (no shared function with other findings)

### Scope

1. **Set `Image.MAX_IMAGE_PIXELS`** — project-wide
   - Location: `apps/media/services/filesystem.py` (the module that imports PIL
     `Image`/`ImageOps` and is consumed by both the bot process — via
     `ad_create.py` imports — and the backend process — via sweep commands).
     Setting it here at module level protects both execution contexts.
   - **Rationale for this location over `ready()`:** The bot process has no
     `AppConfig` (it boots via `telegram_bot/main.py` → `django.setup()`).
     The `MediaConfig` at `apps/media/apps.py` has no `ready()` override.
     Module-level setting in `filesystem.py` is the single choke point —
     PIL is only ever imported through this module in the media pipeline.
   - Value: `2560 * 2560 * 2` (= 13,312,000 pixels) — just above the 2560×2560
     dimension ceiling enforced by `validate_photo`, allowing the transposed
     decode but rejecting anything significantly larger
   - **Do NOT** change the existing `validate_photo` dimension check order (the
     findings note the decode-before-dimension-check issue, but ME-005's scope is
     the `MAX_IMAGE_PIXELS` guard, not reordering the validation pipeline)

2. **Verify Pillow enforcement** — `apps/ads/tests/test_media_security.py`
   - Add a test asserting that `validate_photo` on a >3000×3000px image
     returns `(False, "Failed to process image.")` after the
     `MAX_IMAGE_PIXELS` guard triggers (Pillow raises `DecompressionBombError`
     which is caught by the existing `except Exception` in `validate_photo`)

### Preconditions

None.

### Why this block

`validate_photo` enforces a 2MB byte-size cap, then calls
`Image.open()` + `ImageOps.exif_transpose()` (which forces a full pixel decode)
**before** the dimension check. Without `Image.MAX_IMAGE_PIXELS`, Pillow uses
its default (~89M pixel warning, ~178M pixel error). A 10000×10000px JPEG
under 2MB compressed would decode fully (~300MB RGB buffer) before the
dimension check rejects it. Setting `MAX_IMAGE_PIXELS` to a value near the
2560×2560 ceiling causes Pillow to raise `DecompressionBombError` during
`Image.open`/`exif_transpose`, short-circuiting the full decode.

### Risk gates

- **Low risk:** This is advisory with no behavioral change for valid images
  (2560×2560 < 13.3M pixels). The existing `except Exception` in
  `validate_photo` already catches `DecompressionBombError` and returns
  `"Failed to process image."`.
- **Import ordering:** `Image.MAX_IMAGE_PIXELS` must be set before any
  `Image.open` call. Module-level assignment in `filesystem.py` (which imports
  `Image` at top) guarantees this for any code path that imports this module.

---

## Verification Strategy (cross-block)

| Block | Verification | Test location | Priority |
|---|---|---|---|
| 1 (ME-001) | Regression: poisoned `AdImage.image` → `delete_photo` refuses | `apps/ads/tests/test_media_security.py` `TestPhysicalDeletion` | REQUIRED |
| 1 (ME-001) | Regression: `media_gate` rejects `../` in `image_key` | `apps/ads/tests/test_media_security.py` `TestPathTraversalRejection` | REQUIRED |
| 1 (ME-001) | Migration passes on existing seed data (no key violations) | `make test-recreate` | REQUIRED |
| 2 (ME-003-secondary) | Contingent on Block 0 decision | Per Researcher recommendation | IF `AnalyticsEvent` chosen |
| 3 (ME-002) | Regression: 5 sweeps pass all 4 keys to `delete_photo` | `apps/core/tests/test_sweep_commands.py` (per command) | REQUIRED |
| 4 (ME-004/006) | Upload cap: 6th photo rejected before download | `telegram_bot/tests/test_ad_create.py` | REQUIRED |
| 4 (ME-004/006) | Rate limiter: 11th request blocked | `telegram_bot/tests/test_rate_limit_service.py` | REQUIRED |
| 5 (ME-005) | Large image → `validate_photo` returns False | `apps/ads/tests/test_media_security.py` | RECOMMENDED (medium) |

**Fast-gate coverage:** Blocks 1, 3, 4 verification tests must pass on
`make test` (Docker Compose fast gate). Block 5 test is recommended for the fast
gate. Block 2 verification is contingent on Block 0.

**No `make test-all` required** — no changes to seed image pipelines or FTS.

---

## Rollback / Risk Containment Notes

- **ME-001 `CheckConstraint`:** If existing DB data contains a key violating the
  regex, the migration will fail on deploy. Mitigation: run a data migration
  first (or use `NOT VALID` + background validation) to clean any poisoned keys
  before enforcing. This is the highest-risk item — flag for pre-deploy DB audit.
- **ME-004 upload cap:** The 5-photo cap is a UX regression for sellers who
  previously could upload >5 (even though the "done" validator rejected them).
  The cap now rejects at upload-time, which is the correct behavior but changes
  the error timing. Communicate this in the bot response messages.
- **ME-006 rate limiter:** If the bot runs as a single process with LocMemCache
  (dev), the limiter is per-process. In production (Redis), it's shared across
  bot process replicas — verify the cache backend is configured in the deploy
  environment. This is the existing behavior for the search-side limiter, so
  no new risk.
