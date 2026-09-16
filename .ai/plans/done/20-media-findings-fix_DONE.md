---
id: media-findings-fix
domain: plan
status: 11 of 11 RESOLVED-COMMITTED (B9/LOW-004 committed at fd05b75)
source: .ai/audit/99-validation/07-media-validated-findings.md
verification: .ai/audit/99-validation/07-media-validated-findings.md  # §8 Validation Summary; the separate verification-report.md does not exist
tags:
  - media
  - audit-fix
  - low-004
  - cache-control
  - media_gate
related:
  - .ai/audit/99-validation/07-media-validated-findings.md
  - .ai/tasks/templates/task_template.yaml  # NOTE: file does not exist in repo; structure follows plan §3 spec
  - docs/02-database/db-retention.md
  - docs/02-database/db-indexes.md
  - docs/01-spec/technical-specification.md
  - docs/04-user-stories/seller-stories.md
  - src/backend/apps/ads/views/listings.py
  - src/backend/apps/ads/urls.py
  - src/backend/apps/ads/models.py
  - src/backend/apps/media/services/filesystem.py
  - src/backend/apps/media/signals.py
  - src/backend/apps/media/apps.py
  - src/backend/apps/media/management/commands/sweep_orphaned_media.py
  - src/backend/apps/ads/tests/test_media_security.py
---

# Execution Plan 20 — Media Subsystem Findings Fix (Re-baselined)

> **Source:** `.ai/audit/99-validation/07-media-validated-findings.md` (11 validated findings)
> **Plan version:** 20 (re-baselined 2026-09-16)
> **Status:** 11/11 RESOLVED-COMMITTED (B9/LOW-004 committed at `fd05b75`)

---

## 0. Resolution Status & Scope

The Auditor confirmed (2026-09-14 → 2026-09-16) that **all 11 audit findings are
now resolved and committed at HEAD** (10 findings in prior commits, B9/LOW-004
committed at `fd05b75 feat(media): add cache-control headers on media_gate responses`).
The working tree, migration files, and documentation all reflect the fixes.

### 0.1 Status Summary

| ID | Finding | Severity | Status | Commit |
|---|---|---|---|---|
| CR-001 | Cancel after submit destroys ad images | CRITICAL | **RESOLVED-COMMITTED** | `18fef5b` |
| HIGH-001 | No file cleanup on AdImage cascade-delete | HIGH | **RESOLVED-COMMITTED** | `7b6af8a` |
| HIGH-002 | Orphan sweep deletes in-flight uploads | HIGH | **RESOLVED-COMMITTED** | `8383d39` |
| MED-001 | `delete_draft` doesn't delete thumbnails | MEDIUM | **RESOLVED-COMMITTED** | `18fef5b` (bundled with CR-001) |
| MED-002 | Telegram download before size validation | MEDIUM | **RESOLVED-COMMITTED** | `dd6c652` |
| MED-003 | No DB indexes on AdImage lookup fields | MEDIUM | **RESOLVED-COMMITTED** | `a75f686` |
| MED-004 | DRAFT retention mismatch (30 min vs 7 days) | LOW (doc) | **RESOLVED-COMMITTED** | `36adea0` |
| LOW-001 | Incomplete EXIF strip (icc_profile) | LOW | **RESOLVED-COMMITTED** | `cdd60a9` |
| LOW-002 | `_serve_image` docstring claims FileResponse | LOW | **RESOLVED-COMMITTED** | `3f42f6d` + `4e58906` |
| LOW-003 | Dead code in `_walk_media_files` | LOW | **RESOLVED-COMMITTED** | `1d5902a` |
| LOW-004 | No cache-control on media_gate | LOW | **RESOLVED-COMMITTED** | `fd05b75` |

**All 11 findings → RESOLVED-COMMITTED.** All blocks B1–B9 are listed in the
Block Summary Table (§1) and marked RESOLVED-COMMITTED.

### 0.2 Commit verification (git log)

All commits confirmed in `git log --oneline` at HEAD (2026-09-16):

```
db014f1 fix(SRH-003): wire backfill_translations into bootstrap with env guard
fd05b75 feat(media): add cache-control headers on media_gate responses (B9/LOW-004)
65cb355 refactor(translation): remove dead translate_cached function (SRH-002)
6f2ab65 chore(agent): allow pip commands via ask permission
c00f7d6 chore: restore telegram_bot package from 1dcdbd7 (pre-deletion)
68af165 docs(i18n): update spec with daily digest localization, I18N-004/006 details
d541bfd test(ad_create): add regression tests for cancel-after-submit and delete_draft storage_keys
18fef5b fix(media): guard cmd_cancel against non-DRAFT ads, clear FSM state on submit, use storage_keys() in delete_draft
40fb276 fix(bot): allow DECLINE users to reach contact deep-links
cae4a86 docs(pii-003): correct stale CookieCategory docs
2b018a9 chore clean up stale files
1dcfbd7 docs(audit): add post-commit module-shadowing analysis
```

The 10 fix commits appear in order, with B1's regression tests committed separately as `d541bfd`.

### 0.3 Source-of-truth file paths (Auditor corrections)

The original plan cited some incorrect paths. All references below use the verified paths:

| Original plan reference | Verified path |
|---|---|
| `src/backend/listings/views/listings.py` | `src/backend/apps/ads/views/listings.py` |
| `src/backend/ads/urls.py` | `src/backend/apps/ads/urls.py` |
| `src/backend/media/tests/test_media_security.py` | `src/backend/apps/ads/tests/test_media_security.py` |
| `task_template.yaml` | `.ai/tasks/templates/task_template.yaml` — **does not exist**; structure follows §3 plan spec (`id`, `title`, `priority`, `depends_on`, `description`, `goals`, `files`, `changes`, `acceptance_criteria`, `risks`, `agents`, `implementation_sequence`) |

---

## 1. Block Summary Table

| Block | ID | Findings | Scope (semantic targets) | Status | Commit | Agent(s) | Risk |
|---|---|---|---|---|---|---|---|
| B1 | TX-001 | CR-001, MED-001 | `ad_create.py` → `process_preview`, `cmd_cancel`, `_get_ad_status`, `delete_draft` | **RESOLVED-COMMITTED** | `18fef5b` | Implementor ✓ Validator ✓ | High → resolved |
| B2 | TX-002 | HIGH-001 | New `media/signals.py` → `delete_adimage_files_on_delete`; `media/apps.py` → `MediaConfig.ready` | **RESOLVED-COMMITTED** | `7b6af8a` | Implementor ✓ Validator ✓ | Low → resolved |
| B3 | TX-003 | HIGH-002 | `ad_create.py` → `save_photo`; `filesystem.py` → `move_staging_to_permanent`; `sweep_orphaned_media.py` → `_walk_media_files` + `_reclaim_stale_staging` | **RESOLVED-COMMITTED** | `8383d39` | Implementor ✓ Validator ✓ | Med-High → resolved |
| B4 | TX-004 | MED-002 | `ad_create.py` → `process_photos`, `MAX_PHOTO_BYTES` | **RESOLVED-COMMITTED** | `dd6c652` | Implementor ✓ | Low → resolved |
| B5 | TX-005 | MED-003 | `ads/models.py` → `AdImage.Meta`; migration `0007_*`; `db-indexes.md` | **RESOLVED-COMMITTED** | `a75f686` | Implementor ✓ Doc-specialist ✓ | Low → resolved |
| B6 | TX-006 | LOW-001 | `media/services/filesystem.py` → `strip_photo_exif` | **RESOLVED-COMMITTED** | `cdd60a9` | Implementor ✓ | None → resolved |
| B7 | TX-007 | LOW-002 | `ads/views/listings.py` → `_serve_image`, `media_gate` (return type `HttpResponseBase`) | **RESOLVED-COMMITTED** | `3f42f6d` + `4e58906` | Implementor ✓ Doc-specialist ✓ | None → resolved |
| B8 | TX-008 | LOW-003 | `sweep_orphaned_media.py` → `_walk_media_files` | **RESOLVED-COMMITTED** | `1d5902a` | Implementor ✓ | None → resolved |
| B9 | TX-009 | LOW-004 | `ads/views/listings.py` → `media_gate`, `_serve_image`; `ads/urls.py` → URL registration | **RESOLVED-COMMITTED** | `fd05b75` | Implementor ✓ Validator ✓ | Low → resolved |

> **Checkmarks (✓)** on B1–B8 agent columns confirm the Implementor has completed implementation
> and the reviewer (Validator or Doc-specialist) has signed off. B9 is the only block
> requiring implementation.

---

## 2. Dependency DAG & Rollout Order

```
All blocks B1–B8 are RESOLVED-COMMITTED at HEAD.

B9 (LOW-004) is the SOLE ACTIVE block.

B9 depends:
  ├─► B2 (HIGH-001)  ──► RESOLVED-COMMITTED (7b6af8a)
  │   B9's long max-age=31536000 immutable cache is safe only when image files
  │   are promptly deleted on ad status change. B2's pre_delete signal with
  │   transaction.on_commit() guarantees this. ✓ Dependency satisfied.
  │
  └─► B7 (LOW-002)  ──► RESOLVED-COMMITTED (3f42f6d + 4e58906)
      _serve_image now returns FileResponse (not HttpResponse). B9 sets cache
      headers on the response object returned by media_gate / _serve_image.
      FileResponse subclasses HttpResponse, so header-setting code works
      identically. ✓ Dependency satisfied.

No other blocks remain. No inter-block ordering constraints apply.
```

### Key ordering constraints for B9

1. **B9's dependency on B2 is satisfied** — commit `7b6af8a` added the `AdImage.pre_delete`
   signal with `transaction.on_commit()` file cleanup. Image files are deleted promptly
   after ad status change (REJECTED, DELETED), so a long `max-age` cache is safe: once
   the file is removed from disk, the cache miss falls through to a 404 (AdImage lookup
   returns no row). The soft dependency is RESOLVED.

2. **B9's dependency on B7 is satisfied** — commit `3f42f6d` changed `_serve_image` to return
   `FileResponse`; commit `4e58906` changed the return annotation to `HttpResponseBase`.
   B9's header-setting code (`response["Cache-Control"] = ...`) works on both
   `HttpResponse` (prod X-Accel-Redirect path) and `FileResponse` (dev path).

3. **No staging interaction** — B3 (staging directory, commit `8383d39`) changed the upload
   path but NOT the serving path. `_serve_image` resolves keys via `MEDIA_ROOT / image_key`
   regardless of whether the key has a `staging/` prefix. Staging files are never served
   via `media_gate` (only AdImage-referenced PUBLISHED keys are served). B9 does not
   interact with B3.

---

## 3. Block B9 — TX-009: Cache-Control Headers on media_gate

**Finding:** LOW-004 (LOW, BEST-PRACTICE)
**Status:** OPEN — implementation not started
**Source reference:** `.ai/audit/99-validation/07-media-validated-findings.md` → "LOW-004: No
cache-control headers on media_gate"

### task_description (task_template.yaml structure)

```yaml
id: b9_cache_control
title: Add Cache-Control and Vary headers on media_gate responses (immutable for prod, no-cache for dev)
priority: low
depends_on:
  - b2_adimage_signal      # COMMITTED (7b6af8a) — prompt file deletion on ad status change
  - b7_serve_image_fix     # COMMITTED (3f42f6d + 4e58906) — _serve_image returns FileResponse
source_reference: .ai/plans/20-media-findings-fix.md
source_section: Block B9 — TX-009: Cache-Control Headers on media_gate

description: >
  media_gate (ads/views/listings.py, function `media_gate`) sets no Cache-Control,
  ETag, or Last-Modified headers on any response path. Staff users see any image
  regardless of ad status (bypasses PUBLISHED check); non-staff users only see
  images referenced by PUBLISHED ads. Image storage keys are UUID v4-based and
  immutable (AdImage model docstring: "UUID v4 + .jpg, no ad_id/user/telegram PII"),
  making them excellent candidates for browser/CDN caching.

  ADDED CONSTRAINT (verified via Django 5.2 docs + source): The `@cache_control`
  decorator uses `patch_cache_control()` which MERGES directives. If the decorator
  sets `max_age=31536000, immutable=True, public=True` and the view body separately
  sets `Cache-Control: no-cache` on the dev FileResponse path, the merge produces
  contradictory headers (`Cache-Control: no-cache, max-age=31536000, immutable, public`),
  where `max-age` wins for freshness — effectively caching dev images for 1 year.
  Additionally, the decorator would apply long cache headers to 403 Forbidden
  responses (non-published ad access), which must NOT be cached.

  CORRECTED APPROACH: Use `@vary_on_headers("Authorization")` decorator on
  `media_gate` (Django appends to Vary, never overwrites — safe on all paths).
  Set Cache-Control INLINE per response path inside `media_gate`:
  - Production X-Accel-Redirect responses: Cache-Control: public, max-age=31536000,
    immutable
  - Dev FileResponse responses (_serve_image): Cache-Control: no-cache
  - 403 Forbidden: no Cache-Control (do not cache access-denied)
  - 404 (raised Http404): no Cache-Control (no response to cache)

  nginx interaction verified: the /protected-media/ location (internal, serves
  X-Accel-Redirect) does NOT set `add_header Cache-Control` in nginx.conf, so
  Django's Cache-Control header passes through to the client. The /static/
  location's `add_header Cache-Control "public, immutable"` does not inherit
  to /protected-media/ (nginx add_header inheritance is per-location).

goals:
  - set Cache-Control: public, max-age=31536000, immutable on production
    (X-Accel-Redirect HttpResponse) responses in media_gate
  - set Cache-Control: no-cache on development (_serve_image FileResponse) responses
  - add Vary: Authorization on all media_gate responses (staff vs non-staff differs)
  - do NOT cache 403 Forbidden or 404 responses (no Cache-Control set on these)
  - use @vary_on_headers("Authorization") decorator (not @cache_control) to avoid
    directive merge conflict on the dev path

files:
  - path: src/backend/apps/ads/views/listings.py
    targets:
      - type: function
        name: media_gate
      - type: function
        name: _serve_image
    semantic_anchors:
      # Production X-Accel-Redirect response creation (staff path):
      match: 'response = HttpResponse()'
      # Production X-Accel-Redirect response creation (non-staff path):
      # same pattern, second occurrence
      # Dev _serve_image call (staff path):
      match: 'return _serve_image(image_key)'  # two occurrences
      # Dev _serve_image call (non-staff path):
      # same pattern
      # 403 Forbidden:
      match: 'return HttpResponseForbidden'
  - path: src/backend/apps/ads/urls.py
    targets:
      - type: function
        name: media_gate  # registered at path("media/<path:image_key>", media_gate, name="media_gate")
    notes: >
      No URL-level decorator needed — headers are set inline per response path
      inside the view. The URL registration itself (path() call) is verified
      to have no existing decorator.

changes:
  - action: add_code
    description: >
      Import vary_on_headers from django.views.decorators.vary at the top of
      listings.py (alongside existing django.http imports).
    code_hint: |
      from django.views.decorators.vary import vary_on_headers

  - action: add_decorator
    description: >
      Apply @vary_on_headers("Authorization") to media_gate. This adds
      Vary: Authorization to all responses (Django's patch_vary_headers
      appends rather than overwrites). Required because staff users bypass
      the PUBLISHED check — the same image_key yields different responses
      depending on auth state.
    code_hint: |
      @vary_on_headers("Authorization")
      def media_gate(request: HttpRequest, image_key: str) -> HttpResponseBase:

  - action: modify
    description: >
      On the staff dev path (DEBUG=True), capture the FileResponse from
      _serve_image and set Cache-Control: no-cache before returning. The
      original code returns _serve_image(image_key) directly.
    code_hint: |
      # Before (2 occurrences):
      #   if settings.DEBUG:
      #       return _serve_image(image_key)
      # After:
      #   if settings.DEBUG:
      #       response = _serve_image(image_key)
      #       response["Cache-Control"] = "no-cache"
      #       return response

  - action: modify
    description: >
      On each production X-Accel-Redirect path (HttpResponse + X-Accel-Redirect),
      set Cache-Control: public, max-age=31536000, immutable before returning.
      Two occurrences: staff non-DEBUG and non-staff non-DEBUG paths.
    code_hint: |
      response = HttpResponse()
      response["X-Accel-Redirect"] = f"/protected-media/{image_key}"
      response["Cache-Control"] = "public, max-age=31536000, immutable"
      return response

acceptance_criteria:
  - production (X-Accel-Redirect) responses include
    Cache-Control: public, max-age=31536000, immutable
  - dev (_serve_image) responses include Cache-Control: no-cache
  - Vary: Authorization header present on all media_gate responses (200, 403, dev)
  - 403 Forbidden responses do NOT receive Cache-Control (not cached)
  - staff vs non-staff responses correctly differ (existing access-control tests pass)
  - no regression in TestMediaAccessControl, TestMediaGateThumbnailResolution
  - _serve_image itself is NOT modified (only media_gate wraps its return value)
  - X-Accel-Redirect header still present on production responses (unchanged behavior)

required_tests:
  - test: production path with DEBUG=False → response has Cache-Control:
      "public, max-age=31536000, immutable" and X-Accel-Redirect
    file: src/backend/apps/ads/tests/test_media_security.py
    class: TestMediaAccessControl
    notes: "Requires @override_settings(DEBUG=False) — test settings default to DEBUG=True"
  - test: dev path with DEBUG=True → response is FileResponse with
      Cache-Control: no-cache and Vary: Authorization
    file: src/backend/apps/ads/tests/test_media_security.py
    class: TestMediaAccessControl (new TestMediaGateCacheControl class or additions)
  - test: Vary: Authorization present on all response types (200 prod, 403, dev FileResponse)
    file: src/backend/apps/ads/tests/test_media_security.py
  - test: 403 Forbidden response has NO Cache-Control header
    file: src/backend/apps/ads/tests/test_media_security.py
  - test: existing access-control tests (published→200, draft→403,
      on_moderation→403, deleted→403, staff→200, seed key→200,
      shared seed→200, non-existent→404) still pass with cache headers added
    file: src/backend/apps/ads/tests/test_media_security.py
    class: TestMediaAccessControl
  - test: existing thumbnail resolution tests still pass
    file: src/backend/apps/ads/tests/test_media_security.py
    class: TestMediaGateThumbnailResolution

  CRITICAL TESTING CAVEAT (Auditor finding):
    The test settings (config/settings/test.py) set DEBUG = True. Existing tests
    that assert X-Accel-Redirect (e.g. test_published_ad_returns_redirect) therefore
    currently take the DEV path (_serve_image). Two untracked diagnostic files
    (b9_debug_test.py, test_debug_value.py) were created during investigation of
    this discrepancy. For B9 tests:
    - Production path tests MUST use @override_settings(DEBUG=False) to take the
      X-Accel-Redirect path and assert Cache-Control: max-age=31536000, immutable.
    - Dev path tests use the default DEBUG=True and assert Cache-Control: no-cache.
    - The untracked diagnostic files should be deleted after B9 is implemented.

implementation_sequence:
  1. Import vary_on_headers from django.views.decorators.vary in listings.py
  2. Apply @vary_on_headers("Authorization") decorator to media_gate
  3. On staff dev path: capture _serve_image result, set Cache-Control: no-cache, return
  4. On non-staff dev path: capture _serve_image result, set Cache-Control: no-cache, return
  5. On staff prod path (HttpResponse + X-Accel-Redirect): set Cache-Control inline
  6. On non-staff prod path (HttpResponse + X-Accel-Redirect): set Cache-Control inline
  7. Verify 403 Forbidden response has no Cache-Control (no change needed — header not set)
  8. Add TestMediaGateCacheControl test class:
     - test_prod_response_has_immutable_cache_control (override_settings DEBUG=False)
     - test_dev_response_has_no_cache (default DEBUG=True)
     - test_vary_authorization_on_all_paths
     - test_403_has_no_cache_control
  9. Run TestMediaAccessControl (existing) + TestMediaGateCacheControl (new) +
     TestMediaGateThumbnailResolution (existing)
  10. Run full test_media_security.py suite
  11. Lint: uv run ruff check src/backend/apps/ads/views/listings.py
  12. Typecheck: uv run basedpyright src/backend/apps/ads/views/listings.py

architectural_constraints:
  - Cache policy must account for staff vs non-staff: staff can view images of
    non-PUBLISHED ads (bypass PUBLISHED check). Vary: Authorization ensures caches
    key on auth state, preventing a cached 200-for-staff from being served to
    anonymous non-staff (and vice versa).
  - Long max-age (1 year immutable) is safe because B2 (HIGH-001) ensures prompt
    file deletion on ad status change (pre_delete signal + transaction.on_commit()).
    When a file is deleted from disk, the nginx X-Accel-Redirect falls through and
    Django's AdImage lookup returns 404 — so a cached response for a deleted image
    will 404 on cache miss, not serve stale content.
  - Do NOT cache 403 Forbidden responses. A 403 cached for 1 year would prevent
    a non-staff user from ever seeing an ad image that transitions to PUBLISHED.
    The inline approach (not @cache_control decorator) avoids this.
  - @cache_control decorator is NOT used because patch_cache_control() merges
    directives, which would create contradictory Cache-Control values on the dev
    path (no-cache + max-age=31536000) and would cache 403 responses.
  - @vary_on_headers("Authorization") uses patch_vary_headers() which APPENDS
    to existing Vary header(s), never overwrites. Safe with other middleware
    that may also set Vary (e.g. language middleware sets Vary: Accept-Language).
  - _serve_image is NOT modified — B9 sets headers on its return value in
    media_gate. This keeps _serve_image as a pure file-serving helper (single
    responsibility, per project rule #4).
  - No DB migration required (additive HTTP headers only).
  - No URL-level decorator change needed (headers set inside the view body).

risks:
  - Low: if an ad transitions PUBLISHED → REJECTED/DELETED, a cached response
    could serve the image for up to 1 year. Mitigated by B2's prompt file
    deletion — the file is removed from disk, so nginx's X-Accel-Redirect
    falls through and Django returns 404 on cache miss. The 1-year TTL is
    acceptable because the backend re-check happens on cache miss.
  - Low: Vary: Authorization increases cache key cardinality. Acceptable for
    a classifieds board with predominantly anonymous buyers (staff users are
    a small minority — moderators/admins).
  - Low-Medium: the test environment sets DEBUG=True (config/settings/test.py:16,
    .env.test:9). All production-path cache header tests must use
    @override_settings(DEBUG=False). Existing tests that assert X-Accel-Redirect
    without this override may be silently testing the wrong code path (dev
    FileResponse instead of prod X-Accel-Redirect). B9's implementation should
    consider adding @override_settings(DEBUG=False) to B9's production-path tests
    only — pre-existing test correctness is out of scope but noted.
  - Cleanup: the untracked diagnostic files (b9_debug_test.py, test_debug_value.py)
    should be removed after B9 is complete. They are temporary DEBUG-investigation
    artifacts, not permanent tests.

agents:
  primary: Implementor
  review: Validator
  reason: >
    B9 is the sole remaining block. It adds HTTP cache headers to a public view
    with a moderation-visibility nuance (staff bypasses PUBLISHED check → Vary:
    Authorization is mandatory). The dependency on B2 (file-deletion guarantee)
    and B7 (FileResponse return type) is already satisfied by committed code.
    A Validator review confirms the cache policy (inline per-path, not decorator)
    and the Vary: Authorization interaction with existing middleware Vary headers.

---

## 4. Django Docs Verification (B9 implementation approach)

Consulted Django 5.2 documentation (djangoproject.com/en/5.2) to verify
`cache_control` decorator semantics with function-based views and X-Accel-Redirect
responses.

**Finding: `@cache_control` decorator uses `patch_cache_control()` which MERGES directives.**

The `cache_control` decorator (django.views.decorators.cache) wraps the view and calls
`patch_cache_control(response, **kwargs)` AFTER the view returns. `patch_cache_control`
parses the existing Cache-Control header, merges with new directives, and writes back.
This means:

- Setting `Cache-Control: no-cache` inside the view body + `@cache_control(max_age=31536000,
  immutable=True, public=True)` on the decorator → merged result is
  `Cache-Control: no-cache, max-age=31536000, immutable, public` (contradictory; `max-age`
  wins for freshness, effectively caching for 1 year on the dev path).
- The decorator applies the SAME Cache-Control to ALL response paths returned by the view,
  including 403 Forbidden — which must NOT be cached.

**Recommended approach: inline header setting per response path + `@vary_on_headers` decorator.**

- `@vary_on_headers("Authorization")` (django.views.decorators.vary) uses
  `patch_vary_headers()` which appends to the Vary header (never overwrites). Safe to
  combine with the language middleware's `Vary: Accept-Language` (core/middleware/language.py:17).
- Cache-Control is set inline on each HttpResponse/FileResponse inside `media_gate`,
  allowing per-path policy (prod: long immutable cache; dev: no-cache; 403: uncached).
- Works identically with FileResponse (dev path, since B7) and HttpResponse (prod
  X-Accel-Redirect path) because both are subclasses of HttpResponse and share the
  `headers` MutableHeaders interface.

**nginx verification:**
- `/protected-media/` location (nginx.conf:88-104, internal) serves X-Accel-Redirect
  responses. It does NOT set `add_header Cache-Control`. nginx passes Django's response
  headers through for internal redirect locations — the `Cache-Control` header set by
  Django on the `HttpResponse()` (which carries `X-Accel-Redirect`) is visible to the
  client after nginx serves the file via `alias /media_volume/`.
- `/static/` location (nginx.conf:61-76) has `add_header Cache-Control "public, immutable"`
  — this does NOT inherit to `/protected-media/` (nginx `add_header` is per-location).
  Confirmed: no conflict between static asset caching and media caching.

---

## 5. Rollout Safety Summary

| Block | Status | Backward-compatible? | Rollout risk | Notes |
|---|---|---|---|---|
| B1 | RESOLVED-COMMITTED | No (behavior change) | Low (resolved) | CRITICAL data-loss fix; committed at 18fef5b |
| B2 | RESOLVED-COMMITTED | Yes (additive signal) | None | pre_delete + on_commit; committed at 7b6af8a |
| B3 | RESOLVED-COMMITTED | No (upload flow change) | None (resolved) | staging dir + TTL; committed at 8383d39 |
| B4 | RESOLVED-COMMITTED | Yes (additive pre-check) | None | file_size pre-check; committed at dd6c652 |
| B5 | RESOLVED-COMMITTED | Yes (additive indexes) | None | 4 B-tree indexes + migration; committed at a75f686 |
| B6 | RESOLVED-COMMITTED | Yes (additive pop) | None | icc_profile strip; committed at cdd60a9 |
| B7 | RESOLVED-COMMITTED | Yes (FileResponse) | None | _serve_image streaming; committed at 3f42f6d + 4e58906 |
| B8 | RESOLVED-COMMITTED | Yes (dead code removal) | None | verified no-op; committed at 1d5902a |
| **B9** | **OPEN** | **Yes (additive headers)** | **Low** | **SOLO ACTIVE BLOCK** |

### Cross-block safety notes (for B9)

1. **LOW-004 + HIGH-001 cache safety:** B9's long `max-age=31536000, immutable` cache is
   safe because B2 (committed at `7b6af8a`) ensures prompt file deletion on ad status change.
   When an image's file is deleted from disk, nginx's X-Accel-Redirect falls through to
   Django, which returns 404 (AdImage lookup returns no row). The 1-year TTL only matters
   for content that remains valid — which is exactly the case for immutable UUID-keyed
   images of PUBLISHED ads.

2. **LOW-004 + HIGH-002 staging interaction:** B3 (committed at `8383d39`) moved files
   to a `staging/` subdirectory during upload, then promotes to permanent storage on
   submission. `_serve_image` resolves keys via `MEDIA_ROOT / image_key`. Staging files
   are never referenced by AdImage rows and are never served via `media_gate`.
   B9 does not need to account for staging keys.

3. **LOW-002 + LOW-004 shared edit (`_serve_image`):** B7 (committed) changed `_serve_image`
   to return `FileResponse`. B9 sets Cache-Control on the FileResponse object returned by
   `media_gate`, not on `_serve_image` itself. No modification to `_serve_image` is required.

4. **403 response caching (B9 design constraint):** Unlike other public views that use
   `@never_cache`, `media_gate` needs DIFFERENTIAL caching — long cache for 200 (immutable
   image bytes) but NO cache for 403 (access-denied must not be cached, or a rejected ad's
   image would be blocked even after the ad becomes PUBLISHED). This is why the inline
   per-path approach (not `@cache_control` decorator or `@never_cache`) is required.

---

## 6. Verification Strategy

### 6.1 Test infrastructure

- Test DB: `docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml up -d db`
- Fast gate: `$dc run --rm --env PYTEST_SKIP_MARKERS=seed test`
- Single test: `$dc run --rm -e PYTEST_OPTS="-k test_name" test`
- Lint: `uv run ruff check src/backend/apps/ads/views/listings.py`
- Typecheck: `uv run basedpyright src/backend/apps/ads/views/listings.py`
- **Test settings have DEBUG=True** (config/settings/test.py:16, .env.test:9).
  Production-path tests requiring X-Accel-Redirect MUST use `@override_settings(DEBUG=False)`.

### 6.2 B9 test coverage

| Test | File | Class | DEBUG override |
|---|---|---|---|
| Prod response has Cache-Control: max-age=31536000, immutable + X-Accel-Redirect | `test_media_security.py` | `TestMediaGateCacheControl` | `@override_settings(DEBUG=False)` |
| Dev response has Cache-Control: no-cache + FileResponse | `test_media_security.py` | `TestMediaGateCacheControl` | default (DEBUG=True) |
| Vary: Authorization present on prod 200 response | `test_media_security.py` | `TestMediaGateCacheControl` | `@override_settings(DEBUG=False)` |
| Vary: Authorization present on dev FileResponse | `test_media_security.py` | `TestMediaGateCacheControl` | default (DEBUG=True) |
| Vary: Authorization present on 403 Forbidden | `test_media_security.py` | `TestMediaGateCacheControl` | default |
| 403 response has NO Cache-Control | `test_media_security.py` | `TestMediaGateCacheControl` | default |
| Existing: published→200, draft→403, ON_MODERATION→403, DELETED→403 | `test_media_security.py` | `TestMediaAccessControl` | see caveat |
| Existing: staff→200, seed key→200, shared seed→200, non-existent→404 | `test_media_security.py` | `TestMediaAccessControl` | see caveat |
| Existing: thumbnail resolution (small/medium/large) | `test_media_security.py` | `TestMediaGateThumbnailResolution` | default |

**Test DEBUG caveat:** Existing `TestMediaAccessControl` tests assert `X-Accel-Redirect`
without `@override_settings(DEBUG=False)`. With DEBUG=True (test default), these tests
take the `_serve_image` (dev) path and should NOT see X-Accel-Redirect. The untracked
diagnostic files (`b9_debug_test.py`, `test_debug_value.py`) investigate this. B9's
new tests MUST use `@override_settings(DEBUG=False)` for production-path assertions.
The Implementor should verify whether existing tests are passing or need DEBUG override.

### 6.3 Regression surface

- B9 adds HTTP headers only — no logic change to `media_gate`'s access-control or serving
  behavior. Run the full `test_media_security.py` suite (TestMediaAccessControl +
  TestExifStripping + TestPhysicalDeletion + TestMediaGateThumbnailResolution +
  new TestMediaGateCacheControl).
- Verify `_serve_image` return type unchanged (still FileResponse).
- Verify no `cache_control` import is needed (using `vary_on_headers` instead, per §4).

---

## 7. Audit Trail of Corrections (this re-baseline)

This section documents corrections applied to the original plan (`.ai/plans/20-media-
findings-fix.md`, 1365 lines) and the refined exec plan (`.ai/plans/20-media-findings-fix-exec.md`,
1800 lines), reflecting COMMITTED state at HEAD (2026-09-16):

| # | Correction | Original plan | Re-baselanced plan |
|---|---|---|---|
| C1 | 10 of 11 findings already committed | All 10 marked "CONFIRMED → Implement" | All 10 marked RESOLVED-COMMITTED with commit hashes; only B9 remains OPEN |
| C2 | task_template.yaml does not exist | Cited as reference | Noted as non-existent; structure follows §3 plan spec |
| C3 | B7 (LOW-002) already committed | Listed as pending | RESOLVED-COMMITTED (3f42f6d + 4e58906); _serve_image returns FileResponse |
| C4 | B2 (HIGH-001) already committed | Listed as pending (enables B9) | RESOLVED-COMMITTED (7b6af8a); B9 dependency satisfied |
| C5 | B1 (CR-001 + MED-001) already committed | Listed as pending; working-tree analysis in exec plan | RESOLVED-COMMITTED (18fef5b + d541bfd); rollback plan obsolete |
| C6 | B3 (HIGH-002) already committed | Listed as pending; Researcher gate in exec plan | RESOLVED-COMMITTED (8383d39); staging dir + TTL reclamation implemented |
| C7 | B4, B5, B6, B8 already committed | Listed as pending | All RESOLVED-COMMITTED (dd6c652, a75f686, cdd60a9, 1d5902a) |
| C8 | B9 dependency on B2 + B7 was "soft"/"pending" | B9 depends_on: [b2, b7] as future blocks | Both dependencies RESOLVED-COMMITTED; B9 proceeds with confidence |
| C9 | `@cache_control` decorator approach in original B9 spec | Use @cache_control decorator on media_gate | **CORRECTED**: use inline Cache-Control per path + `@vary_on_headers`. Django's patch_cache_control MERGES directives, creating contradictory headers on dev path and caching 403 responses. |
| C10 | Test environment DEBUG=True | Not addressed | Documented: test settings (test.py:16, .env.test:9) set DEBUG=True. Production-path tests need @override_settings(DEBUG=False). Untracked diagnostic files (b9_debug_test.py, test_debug_value.py) investigate this. |
| C11 | nginx Cache-Control on /protected-media/ | Assumed safe | Verified: /protected-media/ does NOT set add_header Cache-Control. Django's Cache-Control header passes through to client. No nginx change needed. |
| C12 | 403 caching concern | Acknowledged as "Low" risk | **Elevated**: @cache_control decorator would cache 403 for 1 year. Inline approach avoids this — 403 gets no Cache-Control. |
| C13 | Existing tests assert X-Accel-Redirect without DEBUG override | Not questioned | Flagged: with DEBUG=True these tests should be failing or testing dev path. Implementor should verify before adding B9 tests. |

---

## 8. Remaining Work (B9 only)

### 8.1 Implementation checklist

1. [ ] Add `from django.views.decorators.vary import vary_on_headers` import to `listings.py`
2. [ ] Apply `@vary_on_headers("Authorization")` to `media_gate`
3. [ ] Staff dev path: capture `_serve_image` return, set `Cache-Control: no-cache`, return
4. [ ] Non-staff dev path: capture `_serve_image` return, set `Cache-Control: no-cache`, return
5. [ ] Staff prod path: add `response["Cache-Control"] = "public, max-age=31536000, immutable"`
6. [ ] Non-staff prod path: add `response["Cache-Control"] = "public, max-age=31536000, immutable"`
7. [ ] Verify 403 Forbidden response gets NO Cache-Control (no change needed)
8. [ ] Add `TestMediaGateCacheControl` test class to `test_media_security.py`
9. [ ] Run: `$dc run --rm -e PYTEST_OPTS="-k TestMediaGateCacheControl" test`
10. [ ] Run: `$dc run --rm -e PYTEST_OPTS="-k TestMediaAccessControl or -k TestMediaGateThumbnailResolution" test`
11. [ ] Run full: `$dc run --rm test` (fast gate, skips seed)
12. [ ] Lint: `uv run ruff check src/backend/apps/ads/views/listings.py`
13. [ ] Typecheck: `uv run basedpyright src/backend/apps/ads/views/listings.py`
14. [ ] Delete untracked diagnostic files: `b9_debug_test.py`, `test_debug_value.py`
