# 07 — Media Handling & Security

> Audit phase. LLM-auditor instruction. Architecture-agnostic: described via
> ARCHITECTURAL LAYERS, ZONES OF RESPONSIBILITY, KEY RISKS, GOALS. NOT tied to
> specific files, modules, or functions. Must stay valid if the architecture changes.
>
> **Output mode:** `problems-only` — report only findings; do not narrate a clean bill of health.

## 1. Goal

Verify that photos are ingested, stored, served, and purged securely: unpredictable
URLs, no PII in image bytes, correct access control for unpublished/withdrawn ads,
bounded validation, no orphaned files/rows, and complete media removal on retention
expiry and on PII erasure.

## 2. System Under Audit (layers & zones)

| Zone | Concern |
|------|---------|
| **Upload Ingestion** | The bot receives photo payloads; validates type/size/dimensions/count; generates a random storage key; persists bytes + a photo-collection row tied to the ad. |
| **Storage / Naming** | The media store holds files under UUID-v4 keys with no embedded identity. Local store today, contractually swappable to object storage. |
| **Serving / Access Control** | A reverse proxy serves `/media/` over TLS. App-level access control filters which ads are public; the static layer itself has no per-request auth. |
| **Retention / Sweep** | Scheduled sweeps remove photo files + rows when ads pass retention (draft, failed-moderation, rejected, archived, deleted). Must be idempotent. |
| **Transform / Thumbnail** | Any resize/transform step must be memory/time-bounded with error handling. |
| **Cross-Cutting Privacy** | PII-erasure (phase 06) and ad-lifecycle transitions must cascade to physical media removal. |

## 3. Prerequisites

- Services runnable via the documented Docker commands (web + bot + DB + reverse proxy).
- A throwaway media store (isolated `MEDIA_ROOT`), synthetic JPEGs only — NO real photos, NO PII in image bytes.
- `exiftool` (or equivalent) available to inspect image metadata.
- Linter, type-checker, and media tests available.

## 4. Runtime Verification (mandatory)

Execute, then capture evidence (storage listing, HTTP responses, DB state):

1. **Upload validation** — send valid JPEG via bot → accepted and stored. Send wrong type, oversize, over-dimension, >5 photos, and rapid spam → each rejected with correct limit enforced.
2. **Access control** — fetch a photo URL of a DRAFT / unpublished / rejected / deleted / withdrawn-seller ad directly via the reverse proxy → assert NOT served (404/403). Fetch a PUBLISHED ad photo → assert served.
3. **Path traversal** — attempt crafted keys / `../` and encoded variants → assert rejected, no directory escape.
4. **EXIF / metadata** — upload a photo carrying GPS/device/timestamp metadata → assert stripped (or verified absent) in the stored bytes via `exiftool`.
5. **Retention / sweep** — seed an ad past its retention window; run the relevant sweep → assert BOTH the file and the DB row are removed; in-window ads kept; concurrent sweeps idempotent (no double-delete, no in-use deletion).
6. **PII-erasure cascade** — withdraw a seller's consent → assert referenced media files are physically removed, not just DB rows.
7. **Storage hygiene** — diff media-store contents against DB rows → assert no orphaned files or dangling rows.
8. **Key randomness** — assert all storage keys are UUID v4 (no sequential/versioned/identity-bearing keys).
9. **Quality gates** — run linter, type-checker, and media test suite.

## 5. Audit Dimensions (checks + evidence)

### (a) Access control / URL unpredictability — CRITICAL
Unpublished/withdrawn/deleted-ad photos must not be fetchable via direct URL.
- Evidence: reverse proxy serves only what the app exposes; UUID v4 keys not enumerable; no sequential identifier in paths.

### (b) Upload validation — HIGH
Type (magic bytes, not extension), size, dimensions, count 1–5, and rate limits enforced.
- Evidence: invalid inputs rejected; spam throttled; no oversize/over-count accepted.

### (c) EXIF / metadata stripping — CRITICAL
No PII (GPS, device, timestamps) persists in stored image bytes.
- Evidence: `exiftool` shows no residual metadata; if upstream already strips, verify that assumption holds.

### (d) Storage hygiene — HIGH
No orphaned files (row deleted, file remains) or dangling rows (file missing). FK cascade + file removal atomic.
- Evidence: store/DB diff clean; transaction boundaries cover file + row together.

### (e) Retention / sweep correctness — HIGH
Files + rows removed on retention; in-use files kept; sweeps idempotent; timing accurate.
- Evidence: seeded expired ad fully purged; concurrent runs safe; retention windows correct.

### (f) PII-erasure media cascade — CRITICAL
Withdrawal/erasure removes referenced physical media, not only DB rows.
- Evidence: after erasure, referenced files gone; no recoverable media remains.

### (g) Transform / thumbnail safety — MEDIUM
If a transform step exists: bounded memory/time, handled errors on corrupt/zero-byte/oversize input.
- Evidence: no worker crash or unbounded allocation on malicious input.

### (h) Filename / path-traversal safety — CRITICAL
Storage keys contain only safe characters; no path separators; canonical extension enforced.
- Evidence: crafted filenames/keys rejected; no escape beyond media root.

## 6. Cross-Cutting (owned here, not duplicated)
- **Serving access model** must hide photos of non-PUBLISHED, soft-deleted, and withdrawn-seller ads (ties to phase 05 status + phase 06 consent). Reverse-proxy caching must not serve stale deleted photos.
- **Retention coordination** with ad-lifecycle sweeps (archive/deleted/failed/rejected/draft) so files are removed consistently with rows.
- **PII-erasure integration**: phase 06 owns the trigger; this phase owns the physical media removal mechanics.

## 7. Edge Cases
- Ad deleted while a photo upload is in flight → no orphaned partial file.
- Sweep runs concurrently with a new upload → just-uploaded file not deleted.
- Seller withdraws (erasure) mid-upload → files cleared.
- Corrupt / zero-byte / huge image → rejected or bounded, worker not crashed.
- Reverse-proxy cache serves a deleted photo → cache invalidation on status change.
- Two ads reference the same file (dedup) → sweep uses reference counting, not premature delete.
- UUID collision (theoretical) → no `IntegrityError` fallback gap.

## 8. Severity Taxonomy

- **CRITICAL**
  - Unpublished/withdrawn/deleted-ad photo fetchable via direct URL.
  - PII (EXIF/metadata) leaks in served image bytes.
  - Path traversal executes or escapes media root.
  - PII-erasure leaves referenced media behind.
- **HIGH**
  - Orphaned files/rows (disk bloat or dangling refs).
  - Sweep deletes in-use files or races (non-idempotent).
  - No upload size/type/count/rate limits (abuse possible).
  - Reverse proxy serves restricted content without app auth.
- **MEDIUM**
  - Transform step unbounded in memory/time.
  - Retention not enforced (disk fills).
  - Storage keys not UUID v4 / predictable.
  - EXIF only partially stripped.
- **LOW**
  - Missing type hints on media entry points.
  - Log verbosity includes identity.
  - Advisory lock not logged on entry/exit.

## 9. Recommended Sequence
1. Discovery — map photo-collection entity, upload/serving/sweep flows, transform, erasure cascade.
2. Runtime verification (§4).
3. Per-dimension checks (§5 a–h).
4. Cross-cutting (§6) and edge cases (§7).
5. Consolidate findings.

## 10. Finding Prefix
Use `MED-` for all findings in this phase.

## 11. Reporting
- `problems-only: true`.
- Each finding: severity, zone, evidence (path/line/HTTP response/command output), and recommendation with effort/priority.
- Append incrementally (≤100 lines per write) to the phase findings file per `docs/99-agent/rules.md`.
