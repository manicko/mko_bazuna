---
# Report metadata — fill once per phase report.
phase: "07"
phase_name: "media"
date: "2026-09-28"
auditor: "Executor (subagent)"
validator: "Validator (subagent)"
mode: "problems-only"
# Correct prefix per phase: 01-ENT, 02-CFG, 03-DB, 04-AUT, 05-AD, 06-PII, 07-MED, 08-SRH, 09-EXT, 10-QLT, 11-TST, 12-OPS, 13-PERF, 14-I18N
id_prefix: "MEDIA-"
# report_status = lifecycle of the report document (draft → validated)
report_status: "validated"
severity_taxonomy: ".kilo/commands/audit/phases/07-audit-media.md#severity-taxonomy"
---

# Validated Audit Findings — 07 MEDIA

> **Scope of this document.** Self-contained validation of `.ai/audit/07-media/findings.md`
> (11 findings, `MEDIA-001`…`MEDIA-011`) against commit **`9e96b84`**. Finding IDs are
> preserved verbatim; none were renumbered. Every verdict below was reached by reading the
> shipped source and by independent runtime reproduction in the `mko-bazuna-test` image —
> the auditor's own probe output was **not** taken on trust.
>
> **Method.** Static re-derivation of all eleven mechanisms from source, plus two throwaway
> probes run inside the `mko-bazuna-test` image against a scratch database
> (`audit07v_probe`, dropped) with `MEDIA_ROOT` pointed at a `tempfile.mkdtemp()` directory
> (removed). No file in the repository's `media/` directory and no row in the phantom
> `mko_bazuna` database was read for writing, modified or deleted. Both probe scripts were
> deleted afterwards. **16/16 probe checks reproduced the stated behaviour**, and four
> additional evidence blocks were produced that the auditor did not have.
>
> **One auditor evidence correction.** MEDIA-001's Rollout-Safety table states "No test
> exists for a key referenced by two `AdImage` rows." That is **overstated** —
> `apps/ads/tests/test_media_security.py:681-700` builds exactly that state. The accurate
> statement is narrower and worse: a shared-key test exists for the **serving** path and
> none for the **delete** path. See VAL-005.

## Validation Verdict Summary

| ID | Verdict | Severity (was → is) | One-line justification |
|----|---------|--------------------|--------------------------|
| MEDIA-001 | **ADJUSTED** | CRITICAL → **HIGH** | Reproduced deterministically, but the phase's own CRITICAL bucket is an exhaustive four-item list this does not belong to, and the blast radius is same-seller only on the bot path. Recommendation inverted: the report's *first-listed* option is infeasible. |
| MEDIA-002 | **CONFIRMED** | HIGH (held) | Reproduced: second ad gets 0 images, `create_or_skip` returns the first ad's row, 4 files orphaned. |
| MEDIA-003 | **MERGED → DB-005** | — (DB-005 = MEDIUM) | Byte-for-byte the same mechanism *and* the same fix as DB-005; DB-005 is the record. Do not ship twice. |
| MEDIA-004 | **CONFIRMED** | HIGH (held) | Reproduced twice: the repair command is permanently blocked, and the leftover files stay unreferenced. |
| MEDIA-005 | **ADJUSTED** | MEDIUM (held) | The admin half is confirmed by introspection, but the premise "no control exists" is refuted — the spec's own parenthetical names *account ban*, which is implemented and wired. Retained as a capability gap, not a spec deviation. |
| MEDIA-006 | **CONFIRMED** | MEDIUM (held) | The documented block is genuinely **absent from the repository**, not merely from a docs file. `deny all` appears exactly once in the whole nginx config set, on `location = /metrics`. |
| MEDIA-007 | **ADJUSTED** | MEDIUM (held) | No byte budget confirmed; but the stated trigger is wrong — `/post` does *not* reset the 5-photo cap, `/cancel` and walk-away do. |
| MEDIA-008 | **CONFIRMED** | MEDIUM (held) | Reproduced: a stale `-small` cache hit makes `_preprocess_one` return `True` while `generate()` would still record all three keys. |
| MEDIA-009 | **CONFIRMED + extended** | MEDIUM (held) | All three doc claims verified false against code. Absorbs the photo-edit doc citations displaced from MEDIA-005. |
| MEDIA-010 | **CONFIRMED** | LOW (held) | Confirmed by registered-admin introspection: not registered; write-side only; zero references in `docs/`. |
| MEDIA-011 | **CONFIRMED** | LOW (held) | Pillow 12.3.0's default JPEG quality is **exactly 75** — verified by MD5 match, not by recall. |
| **MEDIA-012** | **NEW (auditor miss)** | **HIGH** | Nothing anywhere detects or repairs a dangling row: `media_gate` returns **HTTP 200 + `X-Accel-Redirect`** for a key whose file does not exist. Silent, unlogged, unrecoverable. |

**Result: 0 rejected · 3 confirmed unchanged · 4 adjusted · 1 merged · 1 new.**
Severity distribution **1 CRIT / 3 HIGH / 5 MED / 2 LOW → 0 CRIT · 4 HIGH · 5 MED · 2 LOW**
(+1 new HIGH, +1 merged out).

## Distribution

| | CRITICAL | HIGH | MEDIUM | LOW | Merged out | New |
|---|---|---|---|---|---|---|
| As audited | 1 | 3 | 5 | 2 | 0 | 0 |
| As validated | **0** | **4** | **5** | **2** | **1** | **1** |

---

# HIGH

## MEDIA-001: [HIGH] — Storage keys have no owner or reference count; deleting one ad destroys another ad's photos

> **Validation Note:**
> - **Action:** adjusted — severity CRITICAL → **HIGH**; recommendation inverted; evidence corrected.
> - **Detail:** The mechanism is 100% real and I reproduced it independently, but three of the
>   auditor's framings are wrong and each of them is load-bearing. (1) **The CRITICAL label is
>   inflated**: `07-audit-media.md` §8 reserves CRITICAL for an exhaustive four-item list
>   (photo fetchable by direct URL · EXIF leak · traversal escape · PII-erasure leaves media
>   behind). This is none of them — it is the *opposite* of the privacy item, because the
>   over-deletion removes bytes rather than leaving them. §7 names the shared-key case as an
>   *edge case* whose stated remedy is "sweep uses reference counting, not premature delete",
>   and §8's HIGH bucket already covers it verbatim: *"Orphaned files/rows (disk bloat or
>   dangling refs)"* and *"Sweep deletes in-use files or races (non-idempotent)"*.
>   (2) **The blast radius is bounded by `copy_ad`'s own ownership check**
>   (`copy_service.py:35-36` raises `PermissionError` on a foreign source), so on the bot path
>   the damage is confined to **one seller's own ads**. The auditor's Impact paragraph claims
>   `consent_hard_delete` "can delete files belonging to an unrelated ad" — true only for
>   `seed/` keys, i.e. only in dev/demo, which `technical-specification.md:217` scopes to
>   development. (3) **The auditor's own evidence refutes their "race" framing** — they
>   correctly state the trigger is "an ordinary `/post`, not a race". A deterministic,
>   same-tenant defect does not outrank a racy one; `DB-005`, whose *identical user-visible
>   outcome* ("a live ad permanently points at a missing file") requires a race, was rated
>   **MEDIUM** by phase 03 and upheld. Severity parity demands this be no higher than HIGH.
>   The one place the auditor is right and I am raising the bar: the report's **first-listed
>   recommendation is infeasible** and would dead-end an implementer (see the Recommendation
>   block and VAL-004). MEDIA-001 remains P0, effort M, and it **does** require an
>   architectural change — that claim survives intact.
> - **See also:** AD-003 (Phase 05 — this finding absorbs its `pre_delete` half; see §Cross-Phase
>   Reconciliation §1), MEDIA-002 (shares the remedy ordering), MEDIA-009, MEDIA-012,
>   DB-005 (**do not merge** — different root cause), VAL-002, VAL-004.

| Field | Value |
|---|---|
| **ID** | MEDIA-001 |
| **Severity** | HIGH (adjusted down from CRITICAL) · **P0** · Effort M |
| **Type** | SPEC-DEVIATION |
| **Category** | Data integrity / Architecture |

### The ownership question, answered (this is the decision Phase 05 asked Phase 07 to make)

**How many `AdImage` rows may reference one storage key? Answer: N, N ≥ 1. The invariant is
"a key is freed only when its *last* referencing row goes away."** A refcount is the correct
model, not an accident to be designed away. Five pieces of shipped evidence force this, and
three of them make the report's "exclusive key" option unimplementable:

| # | Evidence | Consequence |
|---|----------|-------------|
| 1 | `ad_images.image` is a plain `CharField` with four non-unique indexes and **no unique constraint** (`apps/ads/models.py:548-557, 636-653`). The only CHECKs enforce the *key format*, never uniqueness (`:615-634`). | Non-uniqueness is the schema's declared state. |
| 2 | `media_gate`'s own docstring **depends on non-uniqueness**: *"A storage key is **not** guaranteed to be unique. Seed data deliberately reuses `seed/<filename>` … so the lookup uses `filter` rather than `get` to avoid `MultipleObjectsReturned`"* (`apps/ads/views/listings.py:135-139`, restated at `:172-174`). | A unique index would not merely be redundant — it would contradict a documented design decision, and `filter`→`get` would be a separate refactor. |
| 3 | The seed manifest holds **1004 distinct filenames** across 1004 manifest entries, and `ImageGenerator.generate()` injects the **default pool into every category's key map** (`apps/seed/generators/images.py:114-120`) before drawing with `random_elements(unique=True)`. Uniqueness is per-ad; **cross-ad collisions are guaranteed at volume**, across ads owned by **different users**. | Seed keys are structurally shared *by design and at scale*. "Make the key exclusive" would require duplicating bytes per ad — the exact opposite of what `media_gate` and the storage contract were built around. |
| 4 | `copy_ad` aliases keys (`copy_service.py:58-68`) behind a shipped bot command `/copy` (`telegram_bot/handlers/ad_copy.py:26,54`), and **six green tests assert the aliasing** (`apps/ads/tests/test_copy_ad.py:135-141`, docstring `:7` "images (new rows, same storage keys)"). | Intentional, tested behaviour. Changing it is an ads-layer decision, not a media-layer side effect. |
| 5 | `pre_delete` deletes unconditionally (`apps/media/signals.py:29-38`) and **three green tests assert that behaviour** (`apps/core/tests/test_ad_image_delete_signal.py:38,74,117`). | The delete path is the *only* thing that is wrong. Nothing else needs to move. |

### Recommendation (replaces the report's ordering — the report's option (a) cannot be built)

**Do this — a reference check inside the existing `on_commit` callback. No schema change, no
migration, no new model:**

1. In `delete_adimage_files_on_delete` (`apps/media/signals.py:29-38`), before calling
   `delete_photo(key)`, test whether any *other* row still references the key across all four
   columns (`image`, `thumbnail_small/medium/large`) and **skip deletion if so**. The callback
   already runs after commit, so the departing row is already out of the count — the check is
   a simple indexed `EXISTS`, and all four columns carry indexes (`models.py:636-653`).
2. **Failure direction is correct by construction.** If two rows sharing a key are deleted in
   concurrent transactions, each `on_commit` may still see the other → both skip → a *leak*,
   which the hourly orphan sweep reclaims. The reverse — a false "last reference" — is what
   destroys live data, and it cannot occur. Leaks are recoverable; data loss is not.
3. Add the invariant test the report asks for: *"after deleting one of two rows sharing a key,
   the file still exists; after deleting the second, it is gone."* Plus a store↔DB diff that
   **includes `seed/`** (the auditor's excluded it — see VAL-005).
4. Record the ownership rule in one sentence in `db-schema.md` (MEDIA-009 does the doc work).

**Why this beats the report's refcounted-blob-row option:** the `MediaObject`/`ref_count` table
the report offers as the alternative costs a model, a migration, a data backfill to
de-duplicate existing keys, a new resolution path on every key lookup, **and** it still needs
the seed-sharing special case from evidence #3 — so it buys the same behaviour for a great deal
more machinery. The project's own rules ("avoid overengineering", "follow existing patterns",
"production code is king") point at the four-line change.

**Do NOT do this (the report's first-listed option, infeasible):** "keep one physical file per
upload and make `AdImage.image` *exclusive*". A unique index on `ad_images.image` cannot be
created while seed shares keys (evidence #3), and `copy_ad`'s aliasing (evidence #4) would
have to be converted to a byte copy — rewriting six passing tests and negating the
`media_gate` rationale. Logged as **VAL-004**.

### Problem (confirmed)

`AdImage.storage_keys()` returns the original plus every non-null thumbnail
(`apps/ads/models.py:705-719`), and `pre_delete` collects them and calls `delete_photo` for
each with no check that another row still references the same key
(`apps/media/signals.py:29-38`). Two production paths create keys referenced by more than one
row — `copy_ad` (`copy_service.py:58-68`) and the seed generator (`images.py:175-186`) — and
`seed_service.py:242` proves the second is at scale. The trigger is an ordinary seller action,
not a race: `/post` → `create_draft_ad` (`telegram_bot/handlers/ad_create/entry.py:53`) →
`existing.delete()` (`services/ad_data/orm.py:55-57`) → CASCADE → `pre_delete`.

### Independent reproduction (scratch DB + temp `MEDIA_ROOT`; 16/16 checks passed)

```text
=== A. MEDIA-001: copy_ad aliasing + DRAFT-delete cascade ===
[OK] A1.copy_ad creates a SECOND AdImage row with the same key
     rows_with_key=2  copy_status=draft
[OK] A2.deleting the DRAFT destroys the PUBLISHED ad's files
     on_disk={'audit07v-aaaa.jpg': False, 'audit07v-aaaa-small.jpg': False,
              'audit07v-aaaa-medium.jpg': False, 'audit07v-aaaa-large.jpg': False}
[OK] A3.the PUBLISHED ad's AdImage row survives (dangling)  published_rows=1

=== A'. Blast radius on a key shared by two ads with different owners ===
     (exactly the seed/ shape; reachable via the hourly purge_deleted_ads
      after any AdAdmin.action_soft_delete in a seeded environment)
[OK] A4.deleting ONE ad that shares a key kills the other ad's photo
     file_exists=False  other_ad_rows=1
```

### Impact (confirmed, and now *wider* than the auditor stated)

A live, published listing loses its photo bytes **permanently**. The report is right that no
self-healing path exists — and my probe closes the last loophole in that claim: see
**MEDIA-012**, which shows the access-control layer returns **`200 OK` with
`X-Accel-Redirect`** for a key whose file is gone, so nothing in the system ever learns it
happened. The report's documentation concern also stands: `db-retention.md:102` and
`technical-specification.md:88` both assert that erasure removes physical ad-image files,
which holds **only** under an exclusivity assumption the code violates in three places.

### Evidence correction

The report's Problem field lists `AdImageService.create_or_skip` among the producers of
*shared* keys. It is not. On a dedup hit it creates **no row at all** — it returns the
*other ad's* row and leaves the freshly staged file **orphaned** (that is MEDIA-002, a
different defect with a different fix). The only two producers of a key referenced by N>1
rows are `copy_ad` and the seed generator. Trimming this keeps MEDIA-001 from being
"fixed" in a way that leaves MEDIA-002 behind.

---

## MEDIA-002: [HIGH] — Per-seller content dedup silently drops the second ad's photo and orphans the whole file set

> **Validation Note:**
> - **Action:** confirmed unchanged (HIGH held); one reachability claim tightened.
> - **Detail:** Reproduced end to end. I additionally closed the reachability question the
>   report left implicit: the bot's photo handler has **no `telegram_file_id` short-circuit**
>   (`telegram_bot/handlers/ad_create/photos.py:58-123` downloads, re-encodes and stores on
>   every upload), and `save_photo` writes the **EXIF-stripped, re-encoded** bytes
>   (`services/ad_data/media.py:110,114-119`). So re-uploading the same source photo
>   deterministically yields byte-identical stored bytes → identical `sha256` → dedup hit.
>   The spec citation is verified verbatim: `technical-specification.md:149` — *"Photos: 1–5
>   mandatory … cannot publish without ≥1 photo."* No code path enforces it: `submit_ad`
>   (`ads/services/submission.py:218-227`) discards `create_or_skip`'s return value and
>   never counts rows.
> - **See also:** MEDIA-001 (ordering — see Rollout Analysis), AD-006 (Phase 05 filed the
>   same behaviour from the ads side at MEDIUM; this is the media-side record and the
>   higher of the two ratings should win).

| Field | Value |
|---|---|
| **ID** | MEDIA-002 |
| **Severity** | HIGH (held) · **P0** · Effort S |
| **Type** | SPEC-DEVIATION |
| **Category** | Correctness |

### Problem (confirmed)

`AdImageService.create_or_skip` hashes the on-disk file and looks for a match scoped to
**`ad__user_id=ad.user_id`** — i.e. to the *seller*, not the *ad*
(`apps/ads/services/images.py:62-78`). On a hit it returns the existing row and creates
nothing. The caller discards the return value (`ads/services/submission.py:218-227`), so the
skip is invisible. Net effect per occurrence: the new ad publishes with **zero** images, and
the 4 files it staged (original + 3 thumbnails) are promoted to permanent storage with no row
referencing them. The only trace is an INFO log (`images.py:70-77`).

### Independent reproduction

```text
=== B. MEDIA-002 ===
[OK] B1.second ad ends up with ZERO images      b1_images=1  b2_images=0
[OK] B2.create_or_skip returns the OTHER ad's row (caller cannot tell)
     returned_pk=5  belongs_to_ad=5   (ad1=5  ad2=6)
[OK] B3.the 2nd file set (4 files) is orphaned on disk   orphans_on_disk=4/4
```

### Impact (confirmed, with one amplification the report missed)

The report's impact is right. The amplification is in the *rendering*: `ad_list.html:108` is
`{{ ad.images.first.thumbnail_small_url|default:ad.images.first.image_url }}`. When `images.first`
is `None` — which is exactly this bug's state — Django resolves both sides to the empty string
and emits `<img src="">`, i.e. a **broken-image icon on the listing grid**, not a neutral
fallback. The seller's photo-less ad is therefore visibly broken in the one place buyers scan.
`dashboard.html:81` and `review.html:77,81` use `image_url` directly and are equally affected.

### Recommendation (accepted, with the storage-reclaim half made concrete)

Scope the dedup to the target ad — `AdImage.objects.filter(sha256=sha256, ad=ad)` — so a
reposted photo on a new ad creates its own row under its own key. Then have `create_or_skip`
return an explicit result (`created: bool`) and have `submit_ad` **delete the promoted files it
just staged** when `created is False`; the staged key is always freshly generated and unique
(`photos.py:111` → `generate_storage_key()`), so deleting it is safe *regardless* of which
ownership model MEDIA-001 adopts. Add the test the report names: identical bytes to two ads ⇒
both ads have one image, zero orphans. Expect `apps/ads/tests/test_ad_image_service.py` (and
any test asserting cross-ad dedup) to require rewriting — that is a test-expectation change
that follows from the spec, not a distortion of production code.

---

## MEDIA-004: [HIGH] — Thumbnail generation is not atomic; a partial set permanently blocks the repair command

> **Validation Note:**
> - **Action:** confirmed unchanged (HIGH held).
> - **Detail:** Reproduced, and I confirmed the *permanence* the report claims by running the
>   repair command **twice** — the state survives both runs, so this is not a transient
>   ordering artefact. Root cause verified as stated: `generate_thumbnails` loops the three
>   sizes writing each with `O_CREAT|O_EXCL|O_WRONLY` and no rollback
>   (`apps/media/services/thumbnails.py:74-98`), and the repair path's *only* guard is
>   `except FileExistsError: return None` (`.../backfill_thumbnails.py:199-204`). Because
>   `SIZES` is a dict iterated in insertion order SMALL→MEDIUM→LARGE
>   (`thumbnails.py:25-29`), a leftover `-small.jpg` aborts the repair on the **first**
>   iteration, so medium and large are never even attempted. The same `O_EXCL` flag is doing
>   double duty as the idempotency guard, which is why the two cases are indistinguishable —
>   the report's root-cause statement is exact.
> - **See also:** MEDIA-008 (same guard needed there), MEDIA-003/DB-005 (both leave orphans),
>   MEDIA-012 (the leftovers are themselves undetectable).

| Field | Value |
|---|---|
| **ID** | MEDIA-004 |
| **Severity** | HIGH (held) · **P1** · Effort S |
| **Type** | SPEC-DEVIATION |
| **Category** | Reliability |

### Problem (confirmed)

If `generate_thumbnails` dies part-way (ENOSPC, EIO, killed worker) the already-written files
stay on disk and the caller sees an exception. `submit_ad:153-159` catches *every* exception,
sets all three `thumbnail_*` fields to `None` and continues; `move_staging_to_permanent` then
still promotes the surviving files. The `AdImage` row is created with NULL thumbnails while
one or two files exist unreferenced. The repair command cannot fix it: `_read_and_generate`
re-calls `generate_thumbnails`, which raises `FileExistsError` on the first size, and the
handler logs *"already exist … (race), skipping"* and returns `None` — forever.

### Independent reproduction

```text
=== D. MEDIA-004: partial thumbnails ===
[OK] D1.first backfill CANNOT repair the row (O_EXCL FileExistsError -> skip)
     after_run1 small=None
[OK] D2.second backfill still cannot repair it (permanent, not transient)
     after_run2 small=None
     (command log line observed in-container: "Thumbnail files already exist for
      AdImage 6 (race), skipping" — emitted on BOTH runs)
```

### Impact (confirmed)

An ad permanently loses its thumbnails. Templates fall back to the full-size original
(`ad_list.html:108`, `detail.html:48,100,102`), so the visible effect is oversized originals
and a layout/bandwidth regression — and **no test, metric or dashboard detects it**. The
documented self-healing command reports progress while achieving nothing, so an operator sees
the same "N records need backfill" count forever. Each occurrence also leaves 1–2 unreferenced
files on disk.

### Recommendation (accepted)

Make the write transactional on disk: render all three variants into memory, then materialise
each as a temp file in the destination directory and `os.replace` them into place only after
all three succeed, unlinking partials on failure. Then make the repair guard discriminate: if
the target file already exists **and** the row's column is NULL, the file is stale — delete
and regenerate rather than skipping. Reuse that same guard in `ImageGenerator._preprocess_one`
(MEDIA-008). Note the direction that matters: the *stale* case must win over the *race* case,
because a genuine concurrent double-generation is harmless (both write byte-identical
`O_EXCL`-guarded output) while a stale file is permanent data loss.

---

## MEDIA-012: [NEW] — Nothing detects or repairs a dangling `AdImage` row; `media_gate` returns 200 for a file that does not exist

> **Validation Note:**
> - **Action:** new — **auditor miss**, filed by the validator at HIGH.
> - **Detail:** The auditor's R-17 store↔DB diff found 5 dangling rows and correctly concluded
>   "no automatic repair". They stopped one step short. The *detection* half is the larger
>   defect and it is media-owned: the serving path is the only component that touches every
>   image on every request, and it **authorises a request purely on the presence of an
>   `AdImage` row — it never checks the filesystem**. Under `DEBUG=False` it therefore returns
>   `200 OK` + `X-Accel-Redirect` for a key whose file is gone, so nginx's `internal` location
>   404s at the browser with **no error, no log line and no metric anywhere in the stack**. The
>   only "missing key" test in the suite passes for the wrong reason: it creates *no row*
>   (`test_media_security.py:702-708`), so the 404 comes from the row check, not a file check.
> - **See also:** MEDIA-001, MEDIA-003→DB-005, MEDIA-004, MEDIA-008 (all three produce
>   undetectable dangling rows), DB-011 (Phase 03 — the sweeps pre-collect keys for a log line).

| Field | Value |
|---|---|
| **ID** | MEDIA-012 |
| **Severity** | HIGH · **P1** · Effort S |
| **Type** | SPEC-DEVIATION |
| **Category** | Data integrity / Observability |

### Problem (confirmed by direct reproduction)

`media_gate` (`apps/ads/views/listings.py:126-215`) runs three checks — key containment, a
referencing `AdImage` row, and an authorization predicate on that row's ad — and then, when
`DEBUG=False`, returns:

```python
response = HttpResponse()
response["X-Accel-Redirect"] = f"/protected-media/{image_key}"   # listings.py:212-213
```

There is **no `os.path.exists` / storage-existence check** on this branch. Existence is only
checked in the `DEBUG=True` fallback (`_serve_image`, `listings.py:117-119`). The system
therefore has a *unidirectional* reconciler — the orphan sweep deletes files nobody references
— and **no detector at all** in the other direction. The rubric's mandatory runtime check §4.7
("diff media-store contents against DB rows → assert no orphaned files or dangling rows")
asks for a reconciler, not a consumer; the reconciler exists, the assertion does not.

### Independent reproduction — the decisive observation

```text
=== A''. User-visible consequence of a dangling key ===
[OK] A5.media_gate authorises the dangling key and hands nginx a dead path
     gate_authorized=True  testclient_status=200
     xaccel='/protected-media/audit07v-shared.jpg'
     file_on_disk=False
```

HTTP **200**, a valid `X-Accel-Redirect` to a path that does not exist, and a file that is not
on disk. The browser receives a 404 from nginx's `internal` block. There is no 4xx from
Django, no exception, no log record, and no counter that could ever fire. Compare the suite's
existing coverage:

```text
test_media_security.py:702  test_non_existent_thumbnail_key_returns_404  -> 404 PASS
```

That test creates **no `AdImage` row**, so it exercises the row lookup, not the filesystem.
The suite therefore *looks* like it covers dangling files and does not. This is precisely the
false assurance the report attributed to the nginx doc (MEDIA-006) — the same failure mode, in
the test suite instead of the architecture doc.

### Impact

Every dangling row produced by MEDIA-001, MEDIA-004, MEDIA-008 or DB-005 is **invisible until
a human happens to notice a broken image on a live listing**, and is then **unrecoverable**
without seller re-upload, because the original bytes are gone and `backfill_thumbnails`
regenerates only derivatives. Blast radius: one ad per occurrence; the cost is the detection
latency, which is currently unbounded. A single nightly reconciliation that logs and counts
dangling rows (and, optionally, alerts) converts an unbounded, silent failure into a bounded,
observable one. This is the single highest-ROI item in the report: it is a read-only
`AdImage.objects.values(...)` + `os.path.exists` loop plus a log line, and it is the guardrail
that makes the other four findings *detectable* while they are being fixed.

### Recommendation

1. Extend the existing sweep command with a **dangling-row report** (`--check` / `--dry-run`
   mode that lists `AdImage` keys with no file on disk, and a stderr summary line) rather than
   adding a new hourly command and a new `AdvisoryLockId`. Reuse lock 103; the check is
   read-only and cheap.
2. Add a test that fails on any dangling row after the existing test suite's own
   create/delete cycles — this is the missing assertion in rubric §4.7 and would have caught
   MEDIA-001, MEDIA-004 and MEDIA-008 at their source.
3. Do **not** add a filesystem check to `media_gate` on the hot path: it would add a stat per
   image request for a condition that (after items 1–2) is already surfaced. Detection belongs
   in the sweep, not the request path.

---

# MERGED OUT

## MEDIA-003: [MERGED → DB-005] — Hourly orphan sweep deletes files an in-flight upload has just promoted but not yet referenced

> **Validation Note:**
> - **Action:** **merged into DB-005** (Phase 03 is the record). Do not ship separately.
> - **Detail:** The mechanism reproduces exactly (my check C1, below). But DB-005's own
>   validation note already states this is *"the **same defect and the same fix** as Phase 01's
>   ENT-009 — do not ship it twice"*, and its **preferred** recommendation is verbatim the
>   option (a) MEDIA-003 proposes: *"keep new files under a directory the sweep excludes —
>   mirroring the existing `staging/` exclusion at `sweep_orphaned_media.py:64-69` — until
>   the owning `AdImage` row commits, then move them."* MEDIA-003 says: *"leave the promoted
>   originals under `staging/` and let a post-commit step rename them (so the sweep's
>   `staging/` exclusion covers the whole window)."* Same mechanism, same remedy, same
>   exclusion set, same lock id.
>   **Where the genuine division of labour lies:** phase 03 explicitly stated that DB-005 is
>   *"architectural … the media storage contract"* and that the transaction/lock mechanics
>   belong to it. So **DB-005 owns the contract and the mechanism.** What is left for the media
>   layer is *not* this finding — it is MEDIA-012 (there is no detector on the other side of
>   the same diff), which the report never separated out.
>   **Consequence of merging:** the merged-away severity is capped at DB-005's **MEDIUM**. A
>   racy deletion window is a smaller defect than a deterministic one (MEDIA-001), and the
>   audit's own CRITICAL-claim chain for this item is now closed.
> - **See also:** DB-005 (Phase 03, absorbs), ENT-009 (Phase 01, already absorbed by DB-005),
>   MEDIA-012, DB-011.

| Field | Value |
|---|---|
| **ID** | MEDIA-003 → **DB-005** |
| **Severity** | — (DB-005 = MEDIUM) |
| **Type** | SPEC-DEVIATION |
| **Category** | Cross-process consistency |

### Independent reproduction (confirms DB-005, adds no new information)

```text
=== C. MEDIA-003 ===
[OK] C1.sweep deletes a promoted-but-unreferenced file
     exists=False  rows_before=3  rows_after=3      (sweep reported "Deleted 5 orphaned media files")
```

### Content preserved for reference (the DB-005 half of this defect, for the record)

`submit_ad` promotes staged files to permanent `MEDIA_ROOT` at
`apps/ads/services/submission.py:166` — *before* `transaction.atomic()` at `:169` — and takes
no `AdvisoryLockId.SWEEP_ORPHANED_MEDIA`. `sweep_orphaned_media` runs hourly, holds lock 103,
snapshots referenced keys from `AdImage` rows only (`:41-50`), and deletes `on_disk -
referenced` (`:139-142`) with no re-check at unlink time. The window is the whole `os.walk`,
not a microsecond, and recurs every hour (`apps/core/utils/scheduler.py:57-64`). The staging
subdirectory was created precisely to hold that window, but `move_staging_to_permanent`
(`apps/media/services/filesystem.py:44-84`) closes it by renaming the file *out* of the
protected prefix before the row exists. All of this is now **owned by DB-005**.

### Two corrections to carry into DB-005's record

1. **"No self-healing path" is over-stated in the DB-005/MEDIA-003 wording.** The sweep is
   one-directional, but the *revenue* side of the same diff — detecting a dangling row — does
   not exist anywhere. That gap is **MEDIA-012**, and DB-005 should cross-reference it rather
   than assert that detection is impossible.
2. **`deleted += 1` counts unverified deletions** (`sweep_orphaned_media.py:158-161`): the
   counter increments per *attempt*, not per confirmed removal, so the command's success line
   ("Deleted N orphaned media files") is not a measurement. It is cosmetic today (a failed
   `delete_photo` writes a `MediaDeletionError`, which nothing reads — MEDIA-010) but it makes
   the operator-facing number untrustworthy. Fold into MEDIA-010's fix.

---

# MEDIUM

## MEDIA-005: [MEDIUM] — No photo-level removal lever; a bad photo can only be removed by destroying the whole ad

> **Validation Note:**
> - **Action:** adjusted — premise partly refuted, capability gap retained; the displaced
>   documentation citations are folded into **MEDIA-009** (merged addendum).
> - **Detail:** The report's headline *"No such control exists"* is **refuted**. Read the spec
>   sentence it cites in full: `technical-specification.md:76` — *"Phase-1 moderation is
>   **text-only** (US-A10). Bad photos removed manually by moderator (incl. account ban)."*
>   The parenthetical **names the lever the spec actually intends**, and it is implemented and
>   wired. Registered-`ModelAdmin` introspection (not `admin.py` reading) shows
>   `AdAdmin.get_actions(request)` returns
>   `['delete_selected', 'action_reject', 'action_ban_user', 'action_soft_delete', 'action_approve']`
>   — so `action_ban_user` is reachable from the admin UI today. Classifying this as a
>   *spec deviation* is therefore wrong; the spec grants a coarser lever and the code has it.
>   What genuinely remains is a **capability gap**: no lever removes one photo while preserving
>   the ad, its text, its view count and its analytics. The admin half of the report is
>   **confirmed** — introspection of `AdImageAdmin` yields an auto-built `AdImageForm` with
>   editable fields `['ad', 'thumbnail_small', 'thumbnail_medium', 'thumbnail_large', 'sha256']`,
>   `actions=[]`, and `has_add/change/delete_permission` all `False`, so the form is
>   unreachable. Severity MEDIUM held: the gap is real, proportionate remedies exist, and the
>   spec anticipated the situation.
> - **See also:** MEDIA-001 (**hard dependency** — a removal must not free shared bytes),
>   MEDIA-009 (absorbs the doc citations displaced from here), AUT-* / phase 15 (admin RBAC
>   scope), VAL-006 (how to check this class of claim).

| Field | Value |
|---|---|
| **ID** | MEDIA-005 |
| **Severity** | MEDIUM (held) · **P1** · Effort M |
| **Type** | BEST-PRACTICE (capability gap) — was reported as Operability / Spec deviation |
| **Category** | Operability |

### Problem (confirmed, reframed)

`AdImage` is append-only by construction: no service, no admin action, no FSM step owns
single-image removal. The seller-facing edit form submits `photos=[]` on both branches that
reach `submit_ad` (`apps/ads/views/edit.py:169` and `:212`) and has no photo control at all.
The bot has no per-photo handler — `cmd_cancel` only bulk-cleans a `DRAFT`
(`telegram_bot/handlers/ad_create/entry.py:86-91`). Verified by introspection:

```text
--- AdImage: REGISTERED
    inlines=[]   readonly_fields=['image', 'telegram_file_id', 'position']
    perms add=False change=False delete=False view=True
    form=AdImageForm editable_fields=['ad', 'thumbnail_small', 'thumbnail_medium',
                                      'thumbnail_large', 'sha256']
    actions=[]
```

`AdAdmin` has **no inlines**, so `AdImage` is not reachable through the ad change form either.
Note this introspection also re-confirms Phase 05's AD-001 independently: `AdAdmin`'s
`AdForm` exposes `status`, `published_at`, `original_published_at`, `archived_at`, `deleted_at`
and `user` as editable — the exact field set Phase 05 reported.

### Impact (confirmed)

A photo containing a phone number, a face, or anything else that must come off a live ad can
only be removed by deleting or archiving the whole ad — which destroys the seller's text, views
and analytics. That is disproportionate, and per MEDIA-001 the whole-ad lifecycle routes that
*do* exist are themselves the mechanism that can delete files belonging to other ads. A
moderator's realistic options today are "ban the seller" or "destroy the listing".

### Recommendation (accepted, reclassified)

Own single-photo removal in **one** place and wire it to both audiences:
`remove_ad_image(ad_image, actor)` in the media layer, which deletes the row and — per
MEDIA-001's decision — **checks for other referencing rows before freeing the bytes** (never
duplicating that logic). A moderator `AdImageAdmin.action_remove` that requires a reason string
and writes a `ModeratorActionLog` row, so the action is auditable like every other moderation
action; and a bot callback letting the seller drop a photo by position in the photos step.
**Do not start this before MEDIA-001 lands** — see Rollout Analysis.

**If photo-level moderation is deliberately deferred for phase 1**, then the honest action is a
one-line doc fix (below), not a finding. Both doc claims that describe the *missing* feature
were moved to MEDIA-009 because they are documentation defects, not capability defects.

---

## MEDIA-006: [MEDIUM] — `/media/` is unrated and the nginx script-execution block documented in the spec does not exist

> **Validation Note:**
> - **Action:** confirmed unchanged (MEDIUM held); the "genuinely absent vs. only absent from a
>   docs file" question is resolved decisively.
> - **Detail:** Asked explicitly — is the block **absent from the repository** or merely
>   **absent from a docs file**? It is **absent from the repository.** `docker/nginx/` contains
>   exactly two config files and no include fragment that could carry it (`nginx.conf:11` and
>   `nginx.dev.conf:14` include only `/etc/nginx/mime.types`). A recursive scan of `docker/`
>   for `\.php|\.cgi|deny all` returns **one** hit: `nginx.conf:162`, inside
>   `location = /metrics`. Per-location parsing shows `/media/` is the **only** public
>   location with no rate limit.
> - **See also:** MEDIA-009 (same doc-vs-config drift class), PERF-* (Phase 13 — the unbounded
>   `AdImage` lookup load is theirs; this finding stays on the nginx surface).

| Field | Value |
|---|---|
| **ID** | MEDIA-006 |
| **Severity** | MEDIUM (held) · **P2** · Effort S |
| **Type** | SPEC-DEVIATION |
| **Category** | Security hardening / Spec deviation |

### Reproduction — the whole nginx config set, parsed per location

```text
--- nginx.conf ---
  php_deny_block=False
  media_has_limit_req=False
  rated_locations=['/login/', '/search/', '/moderation/', '/csp-report/', '/']
  deny_all_lines=['deny all;']            <- line 162, location = /metrics only
--- nginx.dev.conf ---
  php_deny_block=False
  media_has_limit_req=False
  rated_locations=['/login/', '/search/', '/moderation/', '/']
  deny_all_lines=[]                       <- no deny-all at all in dev
```

Independent static trace confirming the same shape by hand:

```text
nginx.conf:81   location /media/ {          <- proxy_pass to web:8000, NO limit_req
nginx.conf:90   location /protected-media/ { internal; nosniff ... }   <- correct
nginx.conf:111  location /login/      { limit_req zone=login_limit  burst=20 nodelay; }
nginx.conf:121  location /search/     { limit_req zone=search_limit burst=40 nodelay; }
nginx.conf:140  location /moderation/ { limit_req zone=browse_limit burst=40 nodelay; }
nginx.conf:171  location /            { limit_req zone=browse_limit burst=40 nodelay; }
```

### Problem (confirmed)

`docs/01-spec/architecture-structure.md:218` documents, verbatim:
*"nginx blocks script execution (`location ~* /media/.*\.(php|py|cgi|pl|sh)$ { deny all;
return 403; }`); `X-Content-Type-Options: nosniff`; whitelist `image/jpeg`, default
`application/octet-stream`, `Content-Disposition: inline`; media keys are UUID v4 (unguessable,
non-sequential)."* Two of those three controls are real (the `nosniff` header at
`nginx.conf:43,96` and the MIME whitelist on `/protected-media/`). **The script-execution block
is not**, in either config, in any fragment. Separately, `location /media/` declares no
`limit_req` zone while four sibling public locations do, and `media_gate` has no
application-level limiter of its own — so every published photo request reaches Django and
PostgreSQL at unlimited rate, issuing the two `EXISTS` queries per request visible at
`listings.py:182` and `:200-204`.

### Impact (confirmed, correctly bounded by the report)

No direct exploit today: `/media/` is proxied to Django, never served as static content, and
`/protected-media/` is `internal` with a MIME whitelist, so there is no execution path. The
real cost is the **false assurance** — a reader of the architecture doc believes a control
exists — plus the unrated request path, which is the cheapest lever for enumerating keys
because the gate's 403/404/200 responses are a perfect oracle, and the cheapest way to drive
origin bandwidth to saturation over the full image corpus. The report is right to rate this
MEDIUM and **not** to upgrade it.

### Recommendation (accepted)

(1) Add the documented block verbatim to both `nginx.conf` and `nginx.dev.conf` — it costs one
`location` and makes the doc true. (2) Add `limit_req zone=browse_limit burst=40 nodelay;` to
`location /media/`, matching `location /`. Verify against a **real** media key before rollout:
a bad `location` regex would 403 genuine photos, and no automated test covers nginx — see
Rollout Analysis. (3) Close the drift permanently: the report's suggestion of a
`docker compose config` assertion is the right instinct, and Phase 01's VAL-003
(*"contracts expressed in a single Compose file with nothing asserting every environment has
them"*) is the same anti-pattern — prefer one assertion over two doc fixes.

---

## MEDIA-007: [MEDIUM] — Staging churn has no byte budget; the 2 h TTL bounds residence time, not the rate

> **Validation Note:**
> - **Action:** adjusted — MEDIUM held; the stated trigger mechanism is **wrong** and is
>   corrected.
> - **Detail:** The report claims *"the 5-photo cap is scoped to one FSM flow — starting
>   `/post` again resets it."* **It does not.** `cmd_post` calls
>   `state.update_data(ad_id=ad.id)` (`ad_create/entry.py:57`), which **merges** into the
>   existing FSM payload and therefore **preserves `photos`**. So the 5-photo cap survives a
>   `/post`, and the churn vector is instead `/cancel` — which calls `state.clear()`
>   (`entry.py:100`) and drops the counter while `cmd_cancel`'s own cleanup
>   (`entry.py:86-91`) only deletes the *current* draft's staged keys — plus plain walk-away,
>   which reaches the 2 h TTL path directly. The arithmetic that matters is unaffected:
>   `RATE_LIMIT_REQUESTS = 10` per `RATE_LIMIT_PERIOD = 60` s keyed by `user_id`
>   (`telegram_bot/services/rate_limit.py:21-24`), each capped at 2 MB by
>   `MAX_PHOTO_BYTES` (enforced pre-download at `ad_create/photos.py:87-89` **and** by the
>   bounded download writer at `services/ad_data/media.py:34,41-67`), so ≈2.4 GB of
>   unreferenced staging bytes per abusive account is reachable inside one 2 h TTL window.
> - **See also:** OPS-* (Phase 12 owns volume alerting), MEDIA-012 (the staging directory is
>   excluded from reconciliation, so nothing measures it), DB-011.

| Field | Value |
|---|---|
| **ID** | MEDIA-007 |
| **Severity** | MEDIUM (held) · **P1** · Effort S |
| **Type** | BEST-PRACTICE |
| **Category** | Availability |

### Problem (confirmed)

Every accepted photo is written to `MEDIA_ROOT/staging/<uuid>.jpg`
(`ad_data/media.py:109-119`) and the whole directory is excluded from the orphan sweep
(`sweep_orphaned_media.py:67-69`). The **only** reclamation is
`_reclaim_stale_staging(media_root, _STAGING_TTL_SECONDS)` with
`_STAGING_TTL_SECONDS = 2 * 60 * 60` (`:38, 76-110`) — a *time* policy with no *space* policy
anywhere. The only admission control is measured in events (10/minute) and count (5/flow), not
in bytes, and there is no per-seller byte budget, no staging-directory size check, and no metric
on either.

### Impact (confirmed, correctly characterised as slow-burn)

A single scripted account can accumulate ≈2.4 GB of permanently-unreferenced staging bytes
inside one TTL window, and the volume is shared with nginx, the web tier and `/protected-media/`
— so exhaustion stops photo serving for the whole site, not just for the abusive seller. The
report is right to call this a slow-burn availability vector rather than an instant outage,
and right that the TTL is the right backstop once a space-based guard exists.

### Recommendation (accepted, with one simplification)

Keep the TTL. Add a **space-based** guard beside it: in `process_photos`
(`ad_create/photos.py:69-123`), reject the upload — with a **translated** message, since i18n
is part of DoD and `test_i18n_completeness.py` is gate-enforced — when `MEDIA_ROOT/staging`
exceeds a configurable byte budget, and/or delete the seller's own staging files at the point
the FSM counter is reset. Emit a `staging_bytes` gauge so ops can alert before the volume
fills. Prefer a **configured budget** over a hard-coded constant, consistent with the project's
`StrEnum`-for-constants and settings-driven configuration rules.

---

## MEDIA-008: [MEDIUM] — The seed pipeline records thumbnail keys it never wrote, and `seed/` is exempt from reconciliation

> **Validation Note:**
> - **Action:** confirmed unchanged (MEDIUM held); reproduction added.
> - **Detail:** Reproduced with the exact state a hand-cleanup or an interrupted run leaves
>   behind — original + only `-small.jpg` present. `_preprocess_one` inspects **one** of the
>   three outputs it is caching and returns `True` on a hit, leaving medium and large
>   unwritten (`apps/seed/generators/images.py:304-316`), while `generate()` writes all three
>   keys into the `AdImage` row unconditionally via `_thumbnail_key` (`:175-186`) — never
>   consulting the `ThumbnailService` return value it already holds. The `except
>   FileExistsError` branch at `:313-314` compounds it by returning `True` after merely
>   logging. Two escape routes are closed off: `_walk_media_files` skips `seed/` entirely
>   (`:64-66`), so the orphan sweep never reclaims; and `backfill_thumbnails` hits the same
>   `O_EXCL` guard as MEDIA-004, so the repair command is also blocked.
> - **See also:** MEDIA-004 (**must land first** — it supplies the stale-file-vs-race guard
>   this finding reuses), MEDIA-001 (`seed/` is where most shared keys live), MEDIA-012,
>   VAL-005.

| Field | Value |
|---|---|
| **ID** | MEDIA-008 |
| **Severity** | MEDIUM (held) · **P2** · Effort S |
| **Type** | SPEC-DEVIATION |
| **Category** | Data integrity |

### Independent reproduction

```text
=== E. MEDIA-008 ===
[OK] E1._preprocess_one returns True on a stale -small cache hit, leaving medium/large
     unwritten while generate() would still record all 3 keys
     returned=True
     before=['apartments_04-small.jpg', 'apartments_04.jpg']
     after =['apartments_04-small.jpg', 'apartments_04.jpg']     <- nothing added
     claimed   =['seed/apartments_04-small.jpg',
                  'seed/apartments_04-medium.jpg',              <- never written
                  'seed/apartments_04-large.jpg']               <- never written
     actually_present=['seed/apartments_04-small.jpg']
```

### Impact (confirmed)

Dev/demo environments — and any environment that runs `seed`, which
`technical-specification.md:217` scopes to development — can hold ads whose
`thumbnail_small/medium/large_url` point at missing files. Templates fall back to
`|default:image.image_url` (`ad_list.html:108`, `detail.html:48,100,102`), so the visible
symptom is oversized originals and a layout regression rather than a hard error — easy to miss,
and it disappears only by manually deleting `-small.jpg` and re-running. Correctly scoped by the
report as a dev/demo-path defect.

### Recommendation (accepted)

Have `_preprocess_one` return the **actual generated keys** (or a truthful `None`) and build the
`AdImage` thumbnail fields from that return value, so the database can never assert a file that
was not written — this is a small change that removes a whole class of the defect rather than
patching one instance. Extend the cache check to all three variants, or drop it and rely on
`ThumbnailService`'s `O_EXCL` (which already handles "already generated" correctly). Reuse the
stale-file-vs-race guard from **MEDIA-004**, so a half-written seed variant is regenerated
rather than skipped — which is also why MEDIA-004 must land first.

---

## MEDIA-009: [MEDIUM] — No documented storage-key ownership model; the DB docs assert a key structure the code does not produce

> **Validation Note:**
> - **Action:** confirmed + **extended** (merged addendum from MEDIA-005); MEDIUM held.
> - **Detail:** All three documentation claims verified **false against the shipped code**, line
>   for line. **Extension:** this finding also absorbs the two documentation defects displaced
>   from MEDIA-005 — `apps/ads/views/edit.py:6` and `:79` ("Price/photo edits: save
>   immediately, status stays PUBLISHED" / "PUBLISHED + price/photo edit: stays PUBLISHED") and
>   `docs/01-spec/technical-specification.md:154` ("Price/photo edits publish immediately") all
>   describe photo editing that does not exist: both branches that reach `submit_ad` pass
>   `photos=[]` (`edit.py:169`, `:212`). The code and docstring agree that only **price** is
>   editable; the two disagree only about **photos**. These belong here rather than in
>   MEDIA-005 because they are documentation defects, not capability defects, and because
>   MEDIA-001's ownership rule must be documented **once**, here.
> - **See also:** MEDIA-001 (**the ownership sentence is written only after the ownership model
>   is decided**), MEDIA-005 (source of the folded citations), MEDIA-006, MEDIA-011.

| Field | Value |
|---|---|
| **ID** | MEDIA-009 |
| **Severity** | MEDIUM (held) · **P1** · Effort S |
| **Type** | DOC-UPDATE |
| **Category** | Documentation |

### Problem (confirmed) + merged addendum

Four documents describe the storage key, and **none states who owns the bytes**:

| Document | Claim | Code reality |
|---|---|---|
| `db-schema.md:320-321` | key contains *"only ad_id + UUID v4"* | `generate_storage_key()` returns `f"{uuid.uuid4()}.jpg"` — **no ad_id** (`apps/media/services/filesystem.py:174-176`) |
| `architecture-structure.md:218` | *"media keys are UUID v4 (unguessable, non-sequential)"* | seed keys are `seed/<filename>.jpg` — semantic, enumerable, and shared across ads (`apps/seed/generators/images.py:111, 318-328`) |
| `db-retention.md:102` + `technical-specification.md:88` | erasure *"removes physical ad-image files"* | true only under an exclusivity invariant the code violates in three places (MEDIA-001) |
| *(new)* `edit.py:6,79` + `technical-specification.md:154` | *"Price/photo edits publish immediately"* | no photo input exists; `photos=[]` on both branches (`edit.py:169, 212`) |

A repository-wide search for `refcount` / `reference count` / `same storage key` /
`ownership` across `docs/` returns nothing — the invariant survives only as an undocumented
assumption, restated slightly differently in three places.

### Impact (confirmed)

This documentation **is** the specification the erasure and retention reviews rely on, and it
is wrong in the one respect that matters most (exclusivity). An operator debugging a missing
file would look for an ad-scoped key format that has never existed. The report is right that
this is a **DOC-UPDATE and not a code defect**: dropping `ad_id` from the key would *reduce*
unguessability, which is the actual security goal, so the code is right and the docs are wrong.
That is the §5 `[SPEC-DEVIATION]` → `[DOC-UPDATE]` reclassification rule applied correctly by
the auditor.

### Recommendation (accepted, extended)

1. Rewrite `db-schema.md:320-321` to state the real scheme — `<uuid4>.jpg` for bot uploads,
   `staging/<uuid4>.jpg` in flight, `seed/<filename>.jpg` for seed data; **no ad_id, by
   design, to preserve URL unguessability** — and state the ownership rule in one sentence.
2. **Write that ownership sentence only after MEDIA-001 lands**, and write the *decided* rule
   (N references, refcount-aware free), not the "except `seed/`" placeholder the report
   proposes. The placeholder would be wrong on arrival: evidence #3 in MEDIA-001 shows seed
   sharing is at scale and cross-user, so it is the case the rule must *handle*, not an
   exception to carve out.
3. Add the same rule next to the `/media/` security bullet at `architecture-structure.md:218`,
   and qualify `db-retention.md:102` / `technical-specification.md:88` with a pointer to it.
4. Fix the "keys are UUID v4" claim to note the `seed/` exception.
5. **(new, from the merged addendum)** Correct `edit.py:6,79` and `technical-specification.md:154`
   to say **price** edits publish immediately and photo editing is not implemented in phase 1 —
   or, if `submit_ad`'s `photos=[]` is a placeholder for planned work, say so explicitly. Three
   places currently promise a feature with no code.

---

# LOW

## MEDIA-010: [LOW] — `MediaDeletionError` is a write-only escalation table — no reader, no retention, no admin

> **Validation Note:**
> - **Action:** confirmed unchanged (LOW held); introspection used instead of `grep`.
> - **Detail:** Confirmed by registered-`ModelAdmin` introspection rather than by reading
>   `admin.py`, which is the technique Phase 04's validation mandated for exactly this class of
>   claim. `MediaDeletionError` is **not in `admin.site._registry`**. A source-wide search
>   (excluding tests) finds the symbol in exactly four places — its own model definition, its
>   migration, and the two write/except lines in `filesystem.py:241-250` — and **zero**
>   occurrences anywhere in `docs/` or `docker/`. There is no reader, no prune command, no
>   `expires` policy and no alert.
> - **See also:** OPS-* (Phase 12 owns the alert), the `deleted += 1` miscount folded in from
>   MEDIA-003→DB-005 (see that finding's second correction), VAL-003 (new lock-id rule).

| Field | Value |
|---|---|
| **ID** | MEDIA-010 |
| **Severity** | LOW (held) · **P2** · Effort S |
| **Type** | BEST-PRACTICE |
| **Category** | Observability |

### Problem (confirmed)

`apps/media/models.py:5` states the model exists *"enabling operational escalation (ME-003)"*,
and `_record_deletion_error` writes a row whenever `delete_photo` exhausts its three retries
(`filesystem.py:229, 233-250`). Nothing ever reads it. Reproduction:

```text
--- MediaDeletionError: not registered
--- source-wide hits (excl. tests):
    src/backend/apps/media/models.py:4,11,56
    src/backend/apps/media/services/filesystem.py:241,243,250
    src/backend/apps/media/migrations/0001_initial.py:13
    src/backend/apps/seed/... (none)   docs/ (0)   docker/ (0)
registered_admins = ['Ad','AdImage','AnalyticsEvent','Category','City','ConsentRecord',
                     'DailyAdMetrics','Group','LoginToken','LookupGroup','LookupItem',
                     'ModerationCriteria','ModeratorActionLog','SiteConfig','SupportContact',
                     'SupportTicket','User']
```

### Impact (correctly rated LOW by the auditor)

The designed escalation path cannot be used: an operator must know to `psql` the table, and the
table is itself an unbounded growth source that masks the signal it exists to raise. A
persistent condition — a read-only `MEDIA_ROOT`, an immutable mount — writes one row per key
per sweep run, forever. The underlying problem is still visible via
`logger.error("Failed to delete photo %s after %s attempts"…)` (`filesystem.py:222-228`), so
nothing is silently lost, which is exactly why LOW is correct and MEDIUM would not be.

### Recommendation (accepted, with one amendment)

Add `apps/media/admin.py` registering `MediaDeletionError` with `created_at` / `error_type`
filters and a `readonly_fields`-only change form, and add a `sweep_media_deletion_errors
--older-than N` retention command. **Amendment:** the report correctly notes that reusing
`AdvisoryLockId.SWEEP_ORPHANED_MEDIA` is inappropriate — a *new* `AdvisoryLockId` member is
required by the project's StrEnum rule, and any new lock id must be added to
`apps/core/tests/test_sweep_lock_structure.py` (see Rollout Analysis). The alert half belongs
to Phase 12; the alertable condition is simply
`MediaDeletionError.objects.filter(created_at__gt=now()-1h).exists()`.

---

## MEDIA-011: [LOW] — Stored originals are re-encoded at Pillow's default quality 75 with no documented rationale

> **Validation Note:**
> - **Action:** confirmed unchanged (LOW held); the "75" is now **measured**, not recalled.
> - **Detail:** The report's factual claim is exact. `strip_photo_exif` calls
>   `img.save(buf, format="JPEG", optimize=True, comment=b"", exif=b"")` with **no `quality`
>   argument** (`apps/media/services/filesystem.py:266-272`). Rather than trusting recall about
>   Pillow's default, I determined it empirically against the shipped Pillow **12.3.0** in the
>   test image by MD5-comparing the default encoding against explicit qualities — and it is
>   **exactly 75, and only 75**. `ThumbnailService.QUALITY = 85` is explicit by contrast
>   (`apps/media/services/thumbnails.py:21`), so the inconsistency the report describes is real.
> - **See also:** MEDIA-009 (the adjacent spec lines that must change).

| Field | Value |
|---|---|
| **ID** | MEDIA-011 |
| **Severity** | LOW (held) · **P2** · Effort S |
| **Type** | DOC-UPDATE |
| **Category** | Maintainability / Documentation |

### Measurement

```text
Pillow 12.3.0
quality 70 -> md5 differs
quality 74 -> md5 differs
quality 75 -> md5 MATCHES the no-quality-argument encoding   <- the default is 75
quality 76 -> md5 differs
quality 80 -> md5 differs
quality 85 -> md5 differs
shipped call (optimize=True, comment=b"", exif=b"") -> 311 bytes (this synthetic image)
```

### Problem (confirmed)

`strip_photo_exif` saves with `optimize=True` and no `quality`, so Pillow's default (75)
applies — every seller photo is re-compressed a second time on top of the compression Telegram
already applied, at a quality the code never chose out loud. Separately,
`technical-specification.md:77` states *"**No server-side photo optimization in phase 1** —
accept Telegram-compressed images, store in our storage (decision E-storage), serve as-is"*,
and `:79` states *"phase 1 serves full-size compressed photos"* — both directly contradicted by
the shipped pipeline (full re-encode + three derivative sizes).

### Impact (correctly rated LOW)

Two small, non-urgent costs. Quality: photos are stored at a lower effective quality than the
seller uploaded, unchangeable without a code edit, with no test or doc recording the intent — so
a future "optimisation pass" has nothing to reason from. Documentation: a reader of the spec
would conclude no re-encoding happens, and could wrongly conclude the EXIF strip does not
either. The report is right that the **code** is the better artefact here and the **docs**
should change (a §5 reclassification applied correctly).

### Recommendation (accepted)

Keep the re-encode — stripping EXIF/ICC is required and independently verified working, and the
auditor's own R-06/R-07 established that. Make the choice explicit: add a named
`STORED_JPEG_QUALITY` constant with a short comment next to the save call, so the number is
reviewable and tunable, and place it beside the existing `ThumbnailService.QUALITY = 85` so the
two qualities can be compared at a glance. Then correct `technical-specification.md:77` and
`:79` to describe the actual pipeline: EXIF/ICC stripped, re-encoded at the named quality,
three derivative sizes generated.

---

# Cross-Phase Reconciliation

## 1. AD-003 (Phase 05) must be split — **resolved; the answer is "N references, refcount-aware free"**

Phase 05's validator ruled (VAL-004) that AD-003 straddles two layers, that the two candidate
remediations are **mutually exclusive**, and that Phase 07 must own the decision *"does a media
storage key have one owner or N?"*. This section is that decision. **The question is settled
and the split is drawn as follows.**

| Half | Layer | Owner | Status after this report |
|---|---|---|---|
| `pre_delete` erases a key with no "still referenced?" check | `apps/media/signals.py:21-40` | **Phase 07 — MEDIA-001** | **ABSORBED.** MEDIA-001 now carries the ownership invariant *and* the refcount decision. |
| `copy_ad` reuses the source ad's storage keys | `apps/ads/services/copy_service.py:58-68` | **Phase 05 — AD-003** | **RETAINED but downgraded to a non-defect.** See below. |

### The answer: how many rows may reference one storage key?

**N, where N ≥ 1. The invariant is "free the bytes only when the last referencing row goes
away."** Five pieces of shipped evidence force this — full table and reasoning in MEDIA-001
above. The three decisive ones: (a) `media_gate`'s own docstring **depends on** non-unique keys
and uses `filter` specifically to survive them; (b) the seed manifest (1004 filenames, default
pool injected into every category) guarantees **cross-ad, cross-user** sharing at scale, and
`media_gate` was hardened for exactly that; (c) `copy_ad`'s aliasing is behind a shipped
command with six passing tests. Non-uniqueness is the design, not the defect. **The defect is
solely that the delete path is unaware of it.**

### Which candidate fix is chosen

**Reference counting — and specifically a reference *check* inside the existing `on_commit`
callback, which needs no schema change, no migration and no new model.** This resolves Phase
05's mutual-exclusion constraint decisively: the two options are exclusive, and the
evidence-based winner is the refcount branch, *not* the byte-copy branch. Consequently:

- **Phase 05's AD-003 must be re-scoped before it is actioned.** Under the refcount model,
  `copy_ad` aliasing is **legal behaviour, not a bug**: the data-loss half of AD-003 is
  retired by MEDIA-001's fix. What survives in AD-003 is a *design trade-off with no defect in
  it* — "a copy shares bytes with its source, which is cheap in disk and means the copy has no
  independent photo lifecycle." The bot already tells the seller *"You can now change the
  listing purpose, price, title, and description"* (`ad_copy.py:81-83`), i.e. photos are not
  offered as copy-editable, so the shared-bytes trade-off is currently invisible to the seller
  and there is nothing to fix. **AD-003 should be closed as "absorbed by MEDIA-001", with its
  residual recorded as an optional disk-cost decision — not shipped as a half-fix.**
- **Do not let both phases ship half a fix.** If Phase 05 implements "copy the bytes" *and*
  MEDIA-001 implements refcounting, the project pays for both and gains nothing — the exact
  hazard Phase 05's VAL-004 warned about. Phase 05 must not start AD-003's code change before
  this report lands.

### Recommended rollout order (dependency chain — the auditor's chain 1 is inverted)

| # | Item | Why it must be here |
|---|---|---|
| 1 | **MEDIA-002** (scope dedup to the target ad) | **Must be first, and it does *not* depend on MEDIA-001** — the auditor's chain 1 ("MEDIA-001 → MEDIA-002") is wrong. MEDIA-002's fix creates a fresh row under a freshly generated unique key, and reclaiming the skipped file is safe under *either* ownership model. Landing it first **removes the accidental-aliasing vector entirely**, shrinking MEDIA-001's problem from three producers to two intentional ones. |
| 2 | **MEDIA-001** (reference check in `on_commit`; no schema change) | The invariant. Safe to land once MEDIA-002 has stopped adding aliases. Backward-compatible with existing shared rows. |
| 3 | **MEDIA-012** (dangling-row reconciliation) | The guardrail. Lands early so the other items become *observable* while they are being fixed. |
| 4 | **MEDIA-005** (single-photo removal) | **Hard dependency on MEDIA-001** (the auditor's chain 4 is correct): a removal must not free bytes another row still references. A removal service written before the invariant is exactly how a second data-loss path gets built. |
| 5 | **MEDIA-009** (document the decided ownership rule) | **Hard dependency on MEDIA-001** (the auditor's chain 2 is correct). Write the decided rule, not the pre-decision placeholder. |
| 6 | **MEDIA-004 → MEDIA-008** | The auditor's chain 3 is correct and the direction is right: 008 reuses 004's stale-file guard, so fixing 008 first re-introduces the same defect class. |
| — | **MEDIA-003 → DB-005** | Independent of everything above; owned by Phase 03. |

## 2. MEDIA-003 vs. DB-005 and ENT-009 — **duplicate; DB-005 is the record**

**Verdict: MEDIA-003 is a duplicate of DB-005, and DB-005 is the record.** The reasoning is
threefold and each part is checkable:

1. **Phase 03 already ruled on it, in writing, before this phase ran.** DB-005's validation note
   states ENT-009 (Phase 01) is *"the **same defect and the same fix** … do not ship it twice"*,
   and phase 01's ENT-009 named `submission.py:166`, `sweep_orphaned_media.py:137-165` and
   lock 103 — the identical file:line triple MEDIA-003 cites.
2. **The remedies are textually identical.** DB-005's *preferred* option — *"keep new files under
   a directory the sweep excludes — mirroring the existing `staging/` exclusion at
   `sweep_orphaned_media.py:64-69` — until the owning `AdImage` row commits, then move them"* —
   is MEDIA-003's option (a) word for word in substance. Two reports proposing the same change to
   the same two functions is a merge, not a complement.
3. **Phase 03 set the ownership boundary, and MEDIA-003 stayed inside it.** Phase 03 stated
   DB-005 is *"architectural"* because *"the durable remedy changes the media storage contract"*,
   and that the transaction/lock mechanics belong to it. MEDIA-003's own Cross-Finding Analysis
   concedes it *"files only the filesystem consequence"* and *"does not restate the locking
   analysis"* — which is precisely DB-005's territory. The genuine media-owned remainder is not
   MEDIA-003 at all; it is **MEDIA-012** (there is no detector on the far side of the same
   diff), which this report separates out for the first time.

**So: both, with the record assigned.** The *mechanism* is DB-005's (single copy, in Phase 03's
report). The *distinct media-owned consequence* — that the outcome is silently unobservable and
unrecoverable — was never filed by anyone and is now **MEDIA-012** in this report. **Phase 03's
report remains the record for MEDIA-003; this report files no competing copy.** The two
corrections in the MEDIA-003 block above (the "no self-healing path" over-statement, and the
`deleted += 1` miscount) should be folded into DB-005's and MEDIA-010's records respectively.

**Merged-away severity: MEDIUM** (capped at DB-005's rating).

## 3. Overlap with Phase 06 (PII & consent) — **none is a PII-inventory duplicate; one is a complement**

Checked against all six Phase-06 findings named in the reconciliation request:

| Phase-06 item | Media overlap | Verdict |
|---|---|---|
| **PII-104** (consent-blind alert fan-out) | **None.** No media finding touches `apps/search`, `send_alerts`, `immediate_alerts`, or `SavedSearch`; the media surface is `AdImage`/`MEDIA_ROOT` only. The two reports share no file, no function and no mechanism. | **Correctly kept separate.** Phase 06's own instruction stands — do not merge. |
| **PII-101 / 109 / 110 / 111 / 114** (symptoms of the absence of a declarative PII inventory) | **None shares the root cause.** All five are *undeclared personal data* — `SupportTicket`'s raw Telegram identifiers, seller-authored `title`/`description`, `SellerVerification.phone_number`, and related. A media finding would share that root cause only if it were about **personal data that exists but is not inventoried**. Every media finding is about **non-personal files whose lifecycle is wrong**; storage keys are documented as carrying no `user_id`/`telegram_id`/`username` (`models.py:537,550`; verified against `generate_storage_key()`), and the auditor independently confirmed no EXIF/GPS survives into stored bytes. | **No merge. No root-cause overlap.** Nothing in this phase is a symptom of the missing PII inventory, so there is nothing to cross-reference instead of re-report. |
| **MEDIA-001's `consent_hard_delete` over-deletion** | **Genuine relationship, opposite direction.** MEDIA-001 notes the 30-day `consent_hard_delete` cascade can delete files it should not. Phase 06's PII-101/105/111 are all about erasure that **fails to remove** data. This is the mirror image: erasure that removes **too much**. | **Complement — cross-reference, do NOT merge.** It is the same *ownership invariant* as MEDIA-001, not the PII-inventory root cause, and it lives in a different layer. Phase 06 should note that "erasure over-reaches" as a residual risk under `consent_hard_delete`; the fix is MEDIA-001's, in the media layer. |

**MEDIA-009 does touch PII-adjacent documentation** (`db-retention.md:102`,
`technical-specification.md:88` both assert erasure removes physical ad-image files). That is a
documentation defect about media lifecycle, not an inventory defect about personal data — the
assertion is *approximately* true, it is just missing an exclusivity caveat. It stays in
MEDIA-009 and is cross-referenced, not merged.

**Confirmation: no media finding shares the missing-PII-inventory root cause, and no media
finding is a duplicate of PII-104.** One complement is recorded above.

---

# Validation-Level Findings (`VAL-`)

These concern the audit inputs and rollout safety, not source-code defects.

## VAL-001: MEDIA-003 is a duplicate of DB-005/ENT-009 — **cross-phase conflict, CRITICAL for pipeline integrity**

- **Severity:** CRITICAL (cross-phase duplicate; must be resolved before the merged reports ship)
- **Detail.** Phase 03 merged **ENT-009 → DB-005** with the note *"do not ship it twice"*, but
  Phase 07 filed the same mechanism as **MEDIA-003** anyway, with the same file:line triple and
  the same remedy. Two validated reports now carry the same fix. Resolved: **DB-005 is the
  record; MEDIA-003 is merged out** (see §Cross-Phase Reconciliation §2).
- **Also:** Phase 01's ENT-009 validator note flagged ENT-006/ENT-009 as *"open dependency"*
  pending a Phase 03 and Phase 07 merge check. That check is now complete — **ENT-009 is
  absorbed by DB-005 and MEDIA-003 into DB-005**. ENT-006 remains Phase 03's (absorbed by
  DB-004).

## VAL-002: AD-003 must be re-scoped before Phase 05 actiones it — **resolves Phase 05's VAL-004**

- **Severity:** HIGH (rollout-safety; blocks a half-fix)
- **Detail.** Phase 05 published its decision request and reserved the answer to Phase 07. This
  report answers it: **the refcount branch wins** (§Cross-Phase Reconciliation §1). Under it,
  AD-003's data-loss claim is **retired by MEDIA-001's fix** and `copy_ad` aliasing becomes legal
  behaviour with no defect in it. **Phase 05 must not implement "copy the bytes" as a fix** —
  doing so alongside a refcount-aware `pre_delete` pays for both remediations and gains nothing.
  AD-003 should be re-labelled *"absorbed by MEDIA-001"*, retaining only an optional disk-cost
  trade-off note. MEDIUM here reflects a cross-phase bookkeeping risk, not code risk.

## VAL-003: MEDIA-001/002's fixes will break 10 currently-green tests, and `MEDIA-` IDs collide with IDs already in shipped source

- **Severity:** MEDIUM (rollout-safety)
- **Detail.** (a) **Test breakage, quantified.** A reference check in `pre_delete` invalidates
  three tests that assert the *current* unconditional behaviour —
  `apps/core/tests/test_ad_image_delete_signal.py:38` (cascade removes physical files),
  `:74` (delete_photo failure does not roll back the cascade), `:117` (bulk delete fires the
  signal) — all of which use a single-ad, single-row fixture and will still pass only if the
  fixture also asserts the file is gone; a *shared-key* case is what is missing, so these are
  likely fine, but the MEDIA-002 change invalidates the cross-ad dedup expectation in
  `apps/ads/tests/test_ad_image_service.py` and the aliasing assertion at
  `apps/ads/tests/test_copy_ad.py:135-141`. Per the project's *"production code is king"* rule
  these are **test-expectation changes that follow from the spec**, not distortions — but they
  must be done deliberately, in the same commit, or the branch goes red and the change gets
  reverted under time pressure. (b) **ID-collision hazard.** Finding IDs from prior audit cycles
  are already hard-coded in shipped source: `test_ad_image_delete_signal.py:2` references
  **"HIGH-001"**, and `test_copy_ad.py:14` references `uq_ads_single_draft_per_user` by name.
  `MEDIA-` is a *new* series but `MED-` is already used in source comments
  (`telegram_bot/services/ad_data/media.py:34,76,83`; `ad_create/photos.py:84`) to mean the
  *07* phase. **Key the remediation tracker on `07-MEDIA-0NN`** and do not refer to "MED-001" in
  a ticket — it is ambiguous with the pre-existing `MED-*` references.

## VAL-004: MEDIA-001's first-listed recommendation is infeasible as written and will dead-end an implementer

- **Severity:** MEDIUM (audit-input defect)
- **Detail.** The report offers two options as equals and names the byte-copy/exclusive-key
  option *"cheapest correct"*. It is neither cheap nor buildable: a unique key is impossible
  while seed shares keys across ads and owners at scale (1004 filenames, default pool injected
  into every category), `media_gate`'s documented rationale *depends on* non-uniqueness, and
  `copy_ad`'s aliasing has six passing tests and a shipped command behind it. An implementer
  following the report's ordering would attempt a unique index, fail the migration, and
  possibly "resolve" it by deleting seed rows. The report's own second option (a refcounted
  `MediaObject`) also over-engineers for this codebase — it needs a model, a migration, a
  de-duplication backfill, a new lookup path, and *still* needs the seed special case. **The
  validated answer is neither listed option**: a reference check in the existing `on_commit`
  callback, four lines, no migration, correct failure direction. Recorded in MEDIA-001's
  Recommendation.

## VAL-005: The auditor's store↔DB diff excluded `seed/` — precisely where most shared keys live — and the suite's "missing key" test passes for the wrong reason

- **Severity:** MEDIUM (audit-input defect)
- **Detail.** (a) R-17's diff counted *"files on disk (non seed/staging) = 40"* and reported
  *"DANGLING ROWS = 5"*. Excluding `seed/` removes the highest-volume source of shared keys in
  the system (MEDIA-001 evidence #3) and the only **cross-user** aliasing in production-shaped
  code, so the headline understates the defect's reach. A conforming reconciliation for rubric
  §4.7 must include `seed/` — or state explicitly that it does not and why. (b)
  `apps/ads/tests/test_media_security.py:702-708` (`test_non_existent_thumbnail_key_returns_404`)
  asserts 404 for a key with **no `AdImage` row**, so it exercises the *row* lookup, not the
  filesystem. The suite therefore appears to cover dangling files and does not — which is how
  MEDIA-012 (an auditor miss) went unnoticed. (c) MEDIA-001's Rollout-Safety claim *"No test
  exists for a key referenced by two `AdImage` rows"* is **overstated**:
  `test_media_security.py:681-700` builds exactly that state. The accurate and narrower claim —
  no such test exists on the *delete* path — should replace it.

## VAL-006: MEDIA-005's premise "no moderator control exists" is refutable only by `ModelAdmin` introspection, not by reading `admin.py`

- **Severity:** LOW (audit-input / methodology defect)
- **Detail.** Phase 04's validation established that registered-`ModelAdmin` **form-field
  introspection** is mandatory wherever an admin surface is judged — reading `admin.py` misses
  auto-built `ModelForm`s (that is how Phase 04 found the plaintext-`password` field on
  `UserAdmin`). MEDIA-005 was written from `admin.py` and drew a false conclusion: the spec's own
  parenthetical names *account ban* as the lever, and `AdAdmin.get_actions(request)` returns
  `['delete_selected', 'action_reject', 'action_ban_user', 'action_soft_delete',
  'action_approve']` — so the lever is implemented and wired. Introspection here also confirmed
  the *rest* of the finding (`AdImageAdmin`: `actions=[]`, add/change/delete all `False`,
  `AdAdmin` has no inlines) and independently re-confirmed Phase 05's AD-001 field set. **Rule
  for future phases: for any claim about an admin capability, introspect
  `admin.site._registry[Model].get_form(request)` and `get_actions(request)`; do not infer from
  the permission flags in `admin.py`.**

---

# Rollout Safety Analysis

| ID | Risk | Backward-compatible? | Test gap that must be covered |
|---|---|---|---|
| **MEDIA-001** | **Med-High.** The fix changes *when* bytes are freed. Failure modes are asymmetric: a false "last reference" destroys live data; a false "not last" leaks a file, which the hourly sweep reclaims. The check runs inside `on_commit`, so the departing row is already gone from the count — the off-by-one is structurally impossible. | **Yes** — no schema change, no migration, no data backfill. Existing shared rows become safe immediately. | Add: two rows sharing a key → delete one → **file still exists**; delete the second → **file is gone**. Plus the same for the `seed/` shape (two *different* owners). Plus a store↔DB diff **including `seed/`** (VAL-005). Existing `test_ad_image_delete_signal.py` should stay green. |
| **MEDIA-002** | Med. A seller who reposted a photo now gets an image where they previously got none — a behaviour change that is strictly closer to `technical-specification.md:149`. Existing photo-less ads stay photo-less (no backfill). | Yes for existing data. | `test_ad_image_service.py`'s cross-ad dedup expectation must be rewritten. Add: identical bytes to two ads ⇒ **both** ads have one image **and** zero orphans on disk. |
| **MEDIA-003 → DB-005** | Med. Narrowing what the sweep deletes means orphans survive one extra cycle — harmless, but disk dashboards shift by one period. | Yes | `apps/media/tests/test_sweep_orphaned_media.py`'s genuine-orphan test must keep passing. Add: a file newer than the sweep start is not deleted. (Owned by Phase 03.) |
| **MEDIA-004** | Low. Only changes behaviour on a failure path that currently loses data. | Yes | Add a stale-file-vs-race case (leftover file + NULL column ⇒ regenerated) and a partial-write case asserting **no partial files remain**. |
| **MEDIA-012** | Low. Read-only; adds a report mode to an existing command. | Yes | Add: after the suite's own create/delete cycles, assert **zero dangling rows** — this is the missing assertion in rubric §4.7 and would have caught MEDIA-001, MEDIA-004 and MEDIA-008 at source. |
| **MEDIA-005** | **Med.** A *new* delete surface on `AdImage`. If it is not permission-gated and audited it becomes an authorization gap (Phase 15's territory). | **No** — new capability. | `test_media_security.py` must assert the new path is staff-only **and** writes a `ModeratorActionLog` row. **Hard dependency: MEDIA-001 must land first.** |
| **MEDIA-007** | Low. A new rejection branch in a bot handler; requires a translated message (i18n is part of DoD; `test_i18n_completeness.py` is gate-enforced). | Yes | New i18n strings with non-empty `ru` and `bs` msgstr; `en` may be empty. The fast gate must pass. |
| **MEDIA-006** | Low. Pure nginx config. **A bad `location` regex would 403 real photos and there is no automated test for nginx** — a typo ships as a site-wide image outage. | Yes | No test possible. Verify with `nginx -t` **and one request for a real media key in the deployed stack**, in both `nginx.conf` and `nginx.dev.conf`. Treat as a manual gate. |
| **MEDIA-008** | Low. Dev/seed path only. | Yes | `apps/seed/tests/test_seed.py` and the `real_images`-marked tests must be re-run with the truthful-return assertion. |
| **MEDIA-009** | Low. Documentation only. | Yes | n/a. **Hard dependency: write the rule after MEDIA-001 decides it.** |
| **MEDIA-010** | Low. Adds an admin read surface **and** a new hourly command. | Yes | The new command needs an `AdvisoryLockId` member added to `apps/core/tests/test_sweep_lock_structure.py` (StrEnum rule). |
| **MEDIA-011** | Low. A named constant; changing the value changes stored bytes for **new uploads only** — already-stored photos keep their current encoding, so the store becomes mixed-quality. Note that in the change. | Yes | `test_save_photo_exif.py` / `test_thumbnail_integration.py` still pass unchanged. |

### Circular and hidden dependencies

- **No circular dependency exists within this phase.** The report's own chain 1
  (MEDIA-001 → MEDIA-002) is **wrong and inverted** — MEDIA-002 does not depend on MEDIA-001's
  model choice, and landing it first strictly reduces MEDIA-001's surface. Corrected chain in
  §Cross-Phase Reconciliation §1.
- **One hidden dependency outside this phase:** AD-003 (Phase 05) is blocked on this report's
  ownership decision. Until it is published, **Phase 05 must not implement the byte-copy fix** —
  see VAL-002.
- **One hidden dependency on Phase 03:** MEDIA-003 is merged into DB-005, so the staging-window
  fix is sequenced by Phase 03. If Phase 03 is scheduled first, MEDIA-012 still lands
  independently and is unaffected.
- **Rollout-safety blocker for phase 15 / admin scope:** MEDIA-005 adds a *delete* surface on
  `AdImage`. If Phase 15 also lands an RBAC layer, the two must be sequenced together or the new
  action will inherit `has_delete_permission = False` semantics inconsistently. Coordinate.

# Required Fixes

1. **Publish the ownership decision** — *N references; free the bytes only when the last
   referencing row goes away* — and implement it as a reference check inside the existing
   `pre_delete` `on_commit` callback. No schema change, no migration, no new model. (MEDIA-001)
2. **Land MEDIA-002 before MEDIA-001.** Scope the dedup to the target ad and delete the files
   `submit_ad` staged when `create_or_skip` returns `created=False`. (MEDIA-002)
3. **Do not action AD-003's byte-copy fix.** Re-label it *"absorbed by MEDIA-001"* and retain
   only the disk-cost trade-off note. (VAL-002 → Phase 05)
4. **Do not ship a second copy of the staging-window fix.** DB-005 (Phase 03) is the record;
   MEDIA-003 is closed here. (VAL-001 → Phase 03)
5. **Add dangling-row reconciliation to `sweep_orphaned_media`** (report mode + count, reusing
   lock 103) and an assertion of zero dangling rows to the media test suite. (MEDIA-012)
6. **Make thumbnail writes atomic on disk** (temp + `os.replace`, unlink partials) and make the
   repair guard prefer the stale-file case over the race case. (MEDIA-004) — **before** MEDIA-008.
7. **Build the seed `AdImage` thumbnail fields from the real `ThumbnailService` return value.**
   (MEDIA-008)
8. **Add the documented nginx block to both configs and rate-limit `location /media/`**, verified
   with `nginx -t` and one real media request. (MEDIA-006)
9. **Add a staging byte budget and a `staging_bytes` metric** alongside the TTL, with translated
   rejection messages. (MEDIA-007)
10. **Register `MediaDeletionError` in the admin and add a retention sweep** with a **new**
    `AdvisoryLockId` member registered in `test_sweep_lock_structure.py`. (MEDIA-010)
11. **Correct four documents** to the real key scheme, the decided ownership rule, the erasure
    caveat, and the absence of photo editing. (MEDIA-009 + MEDIA-011 + the MEDIA-005 addendum)
12. **Name the stored-original JPEG quality** as a constant beside `ThumbnailService.QUALITY`, and
    record that changing it affects new uploads only. (MEDIA-011)

# Advisory Recommendations (optional, not required fixes)

- **Make `sweep_orphaned_media`'s success line a measurement.** `deleted += 1` counts attempts,
  not confirmed removals (`:158-161`), so "Deleted N orphaned media files" is not a fact. Have
  `delete_photo` return whether it removed anything, or verify after the loop. Cheap, and it is
  the number an operator trusts.
- **Prefer one assertion over two doc fixes for nginx hardening.** Phase 01's VAL-003 identified
  the same anti-pattern ("contracts expressed in a single file with nothing asserting every
  environment has them"). A single `docker compose config` assertion that the documented
  locations exist would have caught MEDIA-006 and prevents its recurrence, at lower cost than
  editing the doc every time.
- **Add a `sha256`-based invariant test rather than a storage-key one.** A test asserting
  "no two `AdImage` rows in *different* ads share a key, except `seed/`" would have caught
  `copy_ad`'s aliasing and MEDIA-002 at their source, and it is the invariant the codebase
  actually wants — it does not depend on the key format changing.
- **Reconcile the `ME-003` reference in `apps/media/models.py:5`.** It points at a finding ID
  from a prior audit cycle that is not resolvable from the repository. Either restore the
  traceability or drop the ID, per the same reasoning as VAL-003.
- **Consider surfacing `staging_bytes` and dangling-row counts on the existing metrics endpoint**
  rather than inventing a new alerting path — Phase 12 owns alerting and should consume them.

# Cross-Reference Index

| Other phase's ID | Relationship | Record |
|---|---|---|
| **DB-005** (03) | **Absorbs MEDIA-003.** Same mechanism, same fix. Phase 03 is the record. | Phase 03 |
| **ENT-009** (01) | Already absorbed by DB-005. This report's merge check closes Phase 01's open dependency. | Phase 03 |
| **ENT-006** (01) | Absorbed by DB-004. Out of scope here; flagged only so it is not re-filed. | Phase 03 |
| **AD-003** (05) | **Split resolved.** `pre_delete` half → MEDIA-001 (absorbed). `copy_ad` half stays in Phase 05 but is **downgraded to a non-defect** under the refcount decision. Phase 05 must not implement the byte-copy fix. | **This report** (decision) / Phase 05 (residual) |
| **AD-006** (05) | Same behaviour as MEDIA-002 from the ads side, rated MEDIUM there. MEDIA-002 is the higher-rated record. | **This report** |
| **AD-005** (05) | Merged into DB-001 (Phase 03). No media relevance. | Phase 03 |
| **AD-001** (05) | No shared root cause. Re-confirmed independently here by `AdAdmin` form introspection — the same field set Phase 05 reported. | Phase 05 |
| **DB-009** (03) | `copy_ad` IntegrityError on `uq_ads_single_draft_per_user` is the reason the aliasing window is narrow (a `/copy` while a draft exists fails outright). Complementary, not duplicate. | Phase 03 |
| **DB-011** (03) | Sweeps pre-collect storage keys purely for a log line. Same "trustworthy telemetry" concern as MEDIA-010. | Phase 03 |
| **PII-104** (06) | **No overlap.** Explicitly confirmed not merged, per Phase 06's instruction. | Phase 06 |
| **PII-101/109/110/111/114** (06) | **No shared root cause** — all are undeclared *personal data*; every media finding is about non-personal files with a wrong lifecycle. Nothing to cross-reference instead of re-report. | Phase 06 |
| **`consent_hard_delete` over-deletion** | **Complement to Phase 06, not a duplicate.** Erasure that removes *too much* is the mirror image of PII-101/105/111. Fix is MEDIA-001's, in the media layer. | **This report** / Phase 06 (cross-ref) |
| **CFG-001 / CFG-002** (02) | Cited only to explain why no live reverse-proxy hop was available. Both hold. | Phase 02 |

---

# Honest Assessment of the Auditor's "Not Audited" List

All four disclosed gaps were re-checked. **The list is honest — nothing material was omitted
without disclosure, and no undisclosed gap invalidates a finding.**

| Disclosed gap | Validator assessment |
|---|---|
| **The live reverse proxy** (no HTTP through nginx; `mko-bazuna-dev-web-1`/`bot-1` crash-looping per CFG-006) | **Honest and correctly scoped.** Confirmed: both dev containers are in a restart loop on a placeholder `BOT_TOKEN` in `.env.dev`, so no live hop was available to any agent. I closed the gap from the other direction — I read and per-location-parsed both nginx configs in full and confirmed MEDIA-006's two claims (documented block genuinely absent; `/media/` the only unrated public location). The residual risk the auditor names is real but narrow: whether nginx honours `X-Accel-Redirect`, the `image/jpeg` whitelist and `internal` was **not** exercised. This is carried as a **manual pre-rollout gate** in MEDIA-006's rollout row, not as a finding. |
| **`MediaDeletionError` on a real failing filesystem** (retry exhaustion never triggered) | **Honest.** Verified the path by reading only: `delete_photo`'s 3-attempt exponential backoff, terminal `FileNotFoundError`, and the `_record_deletion_error` write are all as described. The finding is LOW precisely because the `logger.error` path keeps the signal visible, so no injection was needed. No gap. |
| **Scale behaviour of the orphan sweep** (`os.walk` over a large `MEDIA_ROOT`; snapshot→walk→unlink window) | **Honest, and correctly delegated.** Phase 03's DB-005 owns the window mechanics (its own validation note confirms), and the operational consequence of a long walk — the transaction *and* lock 103 are held for the whole traversal — is Phase 03's to rate, not Phase 07's. MEDIA-003 is merged into DB-005 accordingly. No gap in this phase. |
| **`AdImage` authorization beyond the admin permission flags** (Phase 15 owns RBAC) | **Honest, and the conclusion is benign — but the auditor used the wrong instrument.** I closed this gap with the technique Phase 04's validation mandated: registered-`ModelAdmin` **form-field and action introspection**, not `admin.py` reading. `AdImageAdmin` yields an auto-built `AdImageForm` with editable fields `['ad', 'thumbnail_small', 'thumbnail_medium', 'thumbnail_large', 'sha256']` and `actions=[]`, but `has_add/change/delete_permission` are all `False`, so the form is **unreachable**; `AdAdmin` has no inlines. So there is no `AdImage` authorization gap. Note the *cost* of the wrong instrument: reading `admin.py` also produced MEDIA-005's false premise that no moderator lever exists at all, which introspection refuted (VAL-006). |
| **The real `media/` volume** (untouched by design) | **Honest, and respected.** Every reproduction ran against a `tempfile.mkdtemp()` `MEDIA_ROOT`, removed in a `finally` block. Scratch database `audit07v_probe` dropped; both probe scripts deleted; `SELECT datname FROM pg_database WHERE datname LIKE 'audit%'` returns **zero rows**. The phantom `mko_bazuna` database was never written. |
| **gitleaks / pre-commit** (not installed) | **Honest.** Confirmed not installed on this host. No secret scan was run and none is claimed. No secret value was read or quoted; only variable *names* appear in this report. |

**Disclosed-gap verdict: honest, complete, and correctly delegated. No undisclosed gap
invalidates any finding.** The one methodological defect — reaching an admin conclusion from
source text instead of introspection — is recorded as VAL-006, and its one false conclusion is
corrected inside MEDIA-005 rather than left standing.

---

## Checkpoint 1 — Auditor analysis (inherited)

- **Stage:** Auditor analysis
- **Findings in scope:** 11 (CRITICAL 1, HIGH 3, MEDIUM 5, LOW 2), prefix `MEDIA-`
- **Evidence anchor:** `.ai/audit/07-media/findings.md` @ commit `9e96b84`; 20-row runtime
  verification table; 2 probe scripts + 2 scratch databases, both since removed
- **Dependencies / blockers:** none — the dev stack was unavailable, which the auditor disclosed
  and worked around correctly
- **Checkpoint status:** closed

## Checkpoint 2 — Researcher verification

- **Stage:** Researcher verification
- **Cross-phase conflicts:** 2 (VAL-001 MEDIA-003↔DB-005 duplicate; VAL-002 AD-003 split
  resolution owed to Phase 05)
- **Merge candidates:** 2 — MEDIA-003 → DB-005 (confirmed duplicate, DB-005 is the record);
  the photo-edit doc citations from MEDIA-005 → MEDIA-009 (intra-phase)
- **Rejected as duplicates:** 1 (MEDIA-003 does not survive as an independent finding)
- **Independent reproductions:** 16/16 probe checks reproduced the stated behaviour against a
  scratch DB; 4 additional evidence blocks produced (A4 cross-user seed sharing, A5 the
  `media_gate` 200-on-a-dead-path, E1 stale seed cache hit, F1 per-location nginx parse);
  1 Pillow default-quality measurement (MD5 match at exactly 75); 1 registered-`ModelAdmin`
  introspection of `Ad`, `AdImage`, `MediaDeletionError`
- **Checkpoint status:** closed

## Checkpoint 3 — Per-finding validation

- **Stage:** Per-finding validation
- **Findings in scope:** 12 (Validated 3, Adjusted 4, Merged 1, New 1) + 6 `VAL-` findings
- **Decisions:**
  - **Validated unchanged (6):** MEDIA-002 (HIGH), MEDIA-004 (HIGH), MEDIA-008 (MEDIUM),
    MEDIA-009 (MEDIUM, +extension), MEDIA-010 (LOW), MEDIA-011 (LOW)
  - **Adjusted (4):** MEDIA-001 (CRITICAL→HIGH, recommendation inverted, evidence corrected),
    MEDIA-005 (premise refuted, capability gap retained), MEDIA-006 (confirmed, gap resolved
    decisively), MEDIA-007 (trigger mechanism corrected)
  - **Merged (1):** MEDIA-003 → DB-005
  - **New (1):** MEDIA-012 (HIGH) — auditor miss
  - **Rejected (0):** no finding was stale, duplicate, low-ROI, or architecture-breaking
- **Evidence anchor:** this file — self-contained; no live source reads required by a reader
- **Dependencies / blockers:** VAL-001 and VAL-002 are cross-phase actions on Phases 03 and 05
  respectively; both are decisions, not code
- **Checkpoint status:** closed

## Checkpoint 4 — Final consistency audit

- **Stage:** Final audit
- **Findings in scope:** 12 + 6 `VAL-`; 0 rejected; all checkpoints closed
- **Cross-phase state:** DB-005 owns the staging-window fix (MEDIA-003 merged); this report owns
  the storage-key-ownership decision and MEDIA-012; Phase 05 must re-scope AD-003 and must not
  implement the byte-copy fix
- **Pipeline integrity:** OK — no finding is shipped twice, no fix is half-owned, every
  cross-phase question asked of this phase is answered in writing
- **Rollout blockers:** none introduced. Two pre-existing constraints carried forward —
  MEDIA-005 is hard-blocked on MEDIA-001, and MEDIA-009's ownership sentence is hard-blocked on
  MEDIA-001's decision
- **Checkpoint status:** closed

---

# Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| **Validated (unchanged)** | 6 | MEDIA-002, MEDIA-004, MEDIA-008, MEDIA-009, MEDIA-010, MEDIA-011 |
| **Adjusted** | 4 | MEDIA-001 (CRITICAL→HIGH), MEDIA-005 (premise refuted), MEDIA-006 (gap resolved), MEDIA-007 (trigger corrected) |
| **Merged** | 1 | MEDIA-003 → DB-005 (Phase 03) |
| **Rejected** | **0** | — |
| **New (auditor miss)** | 1 | MEDIA-012 (HIGH) |
| **Extended (merged addendum)** | 1 | MEDIA-009 absorbs the photo-edit doc citations from MEDIA-005 |
| **VAL- (cross-phase / rollout)** | 6 | VAL-001 … VAL-006 |

**Final severity: 0 CRITICAL · 4 HIGH (MEDIA-001, MEDIA-002, MEDIA-004, MEDIA-012) · 5 MEDIUM
(MEDIA-005, MEDIA-006, MEDIA-007, MEDIA-008, MEDIA-009) · 2 LOW (MEDIA-010, MEDIA-011)**
plus 1 merged out and 1 new.

## Rejected Findings

**None.** All 11 audited findings are technically real and currently applicable at commit
`9e96b84`; none is stale, already-implemented, low-ROI, architecture-breaking, or
over-engineered. Four required adjustment and one was merged; two were extended with evidence
the auditor did not have; one new finding was added. `MEDIA-003` is the only entry removed from
the report body, and it is **merged, not rejected** — its content is preserved above and in
DB-005.

## Merged Findings

| Original ID | Merged Into | Rationale |
|-------------|-------------|-----------|
| **MEDIA-003** | **DB-005** (Phase 03) | Same mechanism (promote-before-transaction vs. snapshot→walk→unlink, no lock on the write side) and the **same remedy** — DB-005's preferred option is MEDIA-003's option (a) in substance. Phase 03 had already merged Phase 01's ENT-009 into DB-005 with the explicit instruction *"do not ship it twice"*. Phase 03 also set the boundary: DB-005 owns the media storage contract and the transaction/lock mechanics. The genuinely media-owned remainder — that the outcome is silently unobservable — is filed separately as **MEDIA-012**. Merged-away severity capped at MEDIUM. |
| *(from MEDIA-005)* photo-edit doc citations | **MEDIA-009** | `edit.py:6,79` and `technical-specification.md:154` promise photo editing that does not exist. Those are documentation defects, not capability defects, and they belong with the other doc claims that must change together — and after the ownership decision MEDIA-001 makes. |

## Reclassified Findings

| ID | Original framing | New framing | Rationale |
|----|------------------|-------------|-----------|
| **MEDIA-001** | CRITICAL · Data integrity / Architecture | **HIGH** · SPEC-DEVIATION | The phase's own §8 CRITICAL bucket is an exhaustive four-item list (direct-URL fetch · EXIF leak · traversal escape · erasure leaves media) and this belongs to none of them; it is the *inverse* of the privacy item. §7 names the shared-key case an edge case whose remedy is reference counting, and §8's HIGH bucket already covers it ("dangling refs", "sweep deletes in-use files"). Blast radius is same-seller only on the bot path (`copy_ad` raises `PermissionError` on a foreign source); the cross-user case is `seed/`-only and therefore dev-only. `DB-005` — the *same user-visible outcome*, requiring a race — was rated MEDIUM and upheld by Phase 03. Stays **P0**, effort M, and **still requires an architectural change**. |
| **MEDIA-005** | MEDIUM · Operability / **Spec deviation** | MEDIUM · **BEST-PRACTICE** (capability gap) | The premise "no such control exists" is **refuted**: the cited spec sentence's own parenthetical names *account ban* as the lever, and `AdAdmin.get_actions()` returns `['delete_selected', 'action_reject', 'action_ban_user', 'action_soft_delete', 'action_approve']` — implemented and wired. What remains is a missing *photo-level* capability, not a spec violation. The doc claims that describe the missing feature moved to MEDIA-009. |
| **MEDIA-007** | MEDIUM · Availability (BEST-PRACTICE) | MEDIUM · Availability (BEST-PRACTICE, **mechanism corrected**) | Not a reclassification of type but of fact: `/post` does **not** reset the 5-photo cap (`state.update_data` merges, `entry.py:57`); `/cancel`'s `state.clear()` (`entry.py:100`) and plain walk-away do. The byte-budget finding and the ~2.4 GB/2 h arithmetic are unchanged. |
| **MEDIA-009** | MEDIUM · Documentation | MEDIUM · **DOC-UPDATE** (explicit) | The auditor reasoned correctly to "docs should change, not the code" (dropping `ad_id` would reduce unguessability, the actual security goal) without naming the §5 `[DOC-UPDATE]` category. Recorded explicitly so the docs-specialist treats it as such. |
| **MEDIA-011** | LOW · Maintainability / Documentation | LOW · **DOC-UPDATE** (explicit) | Same reasoning: the code's re-encode is the better artefact and the spec is stale. Named explicitly. |

## Confirmed Findings — One-Line Justifications

| ID | Justification |
|----|---------------|
| **MEDIA-002** (HIGH) | Reproduced: the second ad gets 0 images, `create_or_skip` returns the *first* ad's row, 4 files orphaned — and the bot has no `telegram_file_id` short-circuit, so the dedup hit is deterministic, not incidental. |
| **MEDIA-004** (HIGH) | Reproduced twice: the repair command is permanently blocked (`O_EXCL` on the first size, SMALL→MEDIUM→LARGE), the leftovers stay unreferenced, and the state survives a second run. |
| **MEDIA-006** (MEDIUM) | The documented block is **absent from the repository**, not merely from a docs file: `deny all` occurs exactly once in the whole nginx config set, on `location = /metrics`. |
| **MEDIA-008** (MEDIUM) | Reproduced: a stale `-small` cache hit makes `_preprocess_one` return `True` while `generate()` would still record all three keys; both the sweep and the repair command are closed off to that row. |
| **MEDIA-009** (MEDIUM) | All three doc claims verified false against code line-for-line, plus two more absorbed from MEDIA-005. |
| **MEDIA-010** (LOW) | Confirmed by registered-admin introspection: not registered, write-side only, zero references in `docs/`. |
| **MEDIA-011** (LOW) | Pillow 12.3.0's default JPEG quality **measured** at exactly 75 by MD5 match; `ThumbnailService.QUALITY = 85` is explicit by contrast. |

## Findings Requiring an Architectural or Structural Change

Per the validation brief, these are the findings that cannot be closed by a local patch:

| ID | Change required | Why a patch is insufficient |
|----|-----------------|---------------------------|
| **MEDIA-001** | **Yes — architectural.** Decide and enforce a storage-key ownership invariant in the media layer. | `pre_delete` is the *only* wrong component; the consumers (`copy_ad`, the seed generator, `media_gate`) all correctly assume sharing. Changing one function's semantics from "own the key" to "reference-count the key" changes the media layer's storage contract. **The validated implementation is nevertheless small** (a reference check in the existing `on_commit` callback, no schema change) — architectural in *decision*, compact in *diff*. Phase 05's VAL-004 and this report's VAL-002 both make the decision the deliverable. |
| **MEDIA-012** | **Yes — structural.** Add a reconciler for the direction the sweep does not cover. | A one-directional reconciler is not a reconciler. The gap is the *absence of a class of component*, which no local edit can supply; it needs a new report mode, a new assertion in the test suite, and an alerting hook (Phase 12). |
| **MEDIA-005** | **Yes — structural, and gated on MEDIA-001.** A new delete surface on `AdImage`, with an owner, a moderator action, an audit trail and a bot affordance. | `AdImage` is append-only by construction; adding removal introduces the first path that can free bytes outside `pre_delete`, so it must be built *on top of* MEDIA-001's invariant or it becomes a second data-loss route. |
| **MEDIA-003 → DB-005** | **Yes — architectural (Phase 03 owns it).** Change the media storage contract so a file is not visible in the swept `MEDIA_ROOT` until its row commits. | Changes when files become visible, not one function. The remedy also relocates the staging→permanent move across the transaction boundary. |
| **MEDIA-002** | **No — local.** Scope the dedup to the target ad; make the skip observable; reclaim the staged files. | A scope change in one queryset plus a return-type change. Behaviour-visible but structurally contained. |
| **MEDIA-004 / MEDIA-008** | **No — local.** Atomic writes; a discriminating repair guard; a truthful return value. | Both are changes of *how* one module writes and reports. Small, well-bounded, and testable. |
| **MEDIA-007 / MEDIA-010 / MEDIA-011** | **No — local.** A budget, an admin registration, a named constant. | Additive; no contract changes. |
| **MEDIA-006 / MEDIA-009** | **No — configuration and documentation.** | No code contract involved. |
