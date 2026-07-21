# Research Report: App-Level Media Access Gate (nginx X-Accel-Redirect Handoff)

**Task ID:** task_004_research_media_gate
**Related finding:** MED-001 (CRITICAL) — `.ai/audit/07-media/findings.md`
**Date:** 2026-07-20
**Type:** research
**Status:** COMPLETE — RECOMMENDATION: **GO-WITH-CHANGES**

---

## 1. Problem Statement (MED-001)

`docker/nginx/nginx.conf:56-76` serves `/media/` directly from the shared
`media_volume` via `alias /media_volume/;` with **no per-request access
control**. nginx cannot query the DB, so it serves any file present in the
volume regardless of the owning ad's status (`DRAFT`, `ON_MODERATION`,
`ON_MODERATION_FAILED`, `REJECTED`, `ARCHIVED`, `DELETED`) or the seller's
consent state. The only protection is UUID-v4 unpredictability of the storage
key — "security by obscurity", not access control.

The phase goal requires that unpublished/withdrawn/deleted-ad photos are NOT
fetchable by direct URL. The current design fails this.

**Current serving facts:**
- `MEDIA_URL = "media/"`, `MEDIA_ROOT = BASE_DIR.parent / "media"` (`config/settings/base.py:145-148`).
- Storage key is a bare `<uuid>.jpg` (bot) or bare `<uuid>` (model helper) — see MED-005; the key never encodes `ad_id`, so a gate view must resolve `AdImage.image` → `Ad` via the DB.
- `AdImage.image_url` returns `f"{settings.MEDIA_URL}{self.image}"` (`ads/models.py:352-357`). Every template consumes this property.

---

## 2. Consumers of `/media/` URLs (acceptance criterion #2)

All consumers render through `AdImage.image_url`. There is **no** JS/CSS or API
consumer of raw media paths; the property is the single choke point.

| Template | Line(s) | Context | Viewer | Ad status shown |
|----------|---------|---------|--------|-----------------|
| `templates/ads/detail.html` | 34-39 | Public ad detail gallery | Anonymous / any | PUBLISHED only (view filters `status=PUBLISHED`) |
| `templates/ads/list.html` | 68-70 | Public listing card thumbnail | Anonymous / any | PUBLISHED only (view filters `status=PUBLISHED`) |
| `templates/ads/dashboard.html` | 48-50 | Seller dashboard thumbnail (`images.first`) | **Owner (authenticated)** | PUBLISHED **and ARCHIVED** (both `prefetch_related("images")`) |
| `templates/ads/edit.html` | 83-87 | Seller edit form existing-photos preview | **Owner (authenticated)** | Editable statuses (incl. non-PUBLISHED) |
| `templates/admin/moderation/review.html` | 74-83 | Moderation photo grid + lightbox | **Staff/superuser** | `ON_MODERATION`, `ON_MODERATION_FAILED` |

**Backend read sites of `image_url` / images:** `ads/models.py:352` (property),
`moderation/services/auto_moderation.py:175` (`ad.images.count()`, no URL).

**Critical implication:** A naive "serve only if `Ad.status == PUBLISHED`"
gate would **break three legitimate consumers**:
1. Seller dashboard thumbnails for **ARCHIVED** ads.
2. Seller edit-form previews for non-PUBLISHED ads.
3. Staff moderation photo grid for `ON_MODERATION` / `ON_MODERATION_FAILED` ads.

The gate must therefore implement an **authorization matrix**, not a single
status check.

---

## 3. Access-Control Matrix (view responsibility)

For a request `GET /media/<key>` the gate resolves `AdImage(image=<key>)` →
`Ad`, then authorizes:

| Requester | Ad status | Decision |
|-----------|-----------|----------|
| Anyone (anon or auth) | `PUBLISHED` | **ALLOW** |
| Authenticated owner (`ad.user_id == request.user.id`) | any except `DELETED` | **ALLOW** (dashboard/edit previews) |
| Staff / superuser | `ON_MODERATION`, `ON_MODERATION_FAILED` (moderation queue) | **ALLOW** |
| Staff / superuser | any (broad admin preview) | **ALLOW** (recommended, mirrors admin visibility) |
| Anyone | `DRAFT`, `REJECTED`, `DELETED`, `ARCHIVED` (non-owner) | **404** |
| Any | key not found / traversal / non-`.jpg` | **404** |

Notes:
- Return **404 (not 403)** for unauthorized so existence is not leaked (matches `_staff_required` in `moderation/views/review.py` which raises `Http404`).
- `DELETED` must be denied even to the owner (soft-deleted = erased from user view).
- Consent-withdrawn: sweeps hard-delete rows/files (MED-003 scope); the gate additionally denies because the `AdImage` row will be gone → 404 by lookup miss.

---

## 4. Handoff Design — internal location + X-Accel-Redirect (acceptance criterion #1)

### 4.1 Flow

```
Browser ──GET /media/<key>──▶ nginx (public location /media/)
                                   │  proxy_pass ──▶ web:8000  (Django gate view)
                                   │                     │ resolve AdImage→Ad, authorize
                                   │                     │ if allowed:
                                   │                     │   HttpResponse(status=200)
                                   │                     │   X-Accel-Redirect: /protected_media/<key>
                                   │                     │   Content-Type: image/jpeg
                                   │                     │   (no body)
                                   │◀── response with X-Accel-Redirect header
                                   │
                                   ▼ internal location /protected_media/ (alias media_volume)
                              nginx opens file from volume, streams bytes to browser
```

Django performs **only** the DB lookup + authorization; nginx does the actual
byte streaming (efficient, keeps gunicorn sync workers free). The internal
location is unreachable directly (`internal;` → external requests to
`/protected_media/` get 404).

### 4.2 nginx changes (`docker/nginx/nginx.conf`)

Replace the current public `location /media/` (alias) with a proxy to the gate
view, and add a new `internal` location that keeps the existing hardening
headers + MIME whitelist:

```nginx
# Public entry: gated by Django
location /media/ {
    proxy_pass http://web:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

# Internal: only reachable via X-Accel-Redirect from the gate view
location /protected_media/ {
    internal;
    alias /media_volume/;

    # keep R8 hardening (moved verbatim from old /media/ block)
    add_header X-Content-Type-Options nosniff always;
    add_header Content-Disposition inline always;
    add_header X-Frame-Options DENY always;
    add_header Content-Security-Policy "default-src 'none'; img-src 'self' data:; object-src 'none'" always;
    types { image/jpeg jpg jpeg; }
    default_type application/octet-stream;

    expires 30d;
    add_header Cache-Control "private, max-age=2592000" always;  # private: do not shared-cache gated media
}
```

Notes:
- The script-execution `deny` block (`\.(php|py|cgi|sh)$`) becomes moot because only `.jpg` keys reach the view, but it can be retained on `/protected_media/` for defense-in-depth.
- `X-Accel-Redirect` requires the target path to match an nginx location; use `/protected_media/<key>` (distinct prefix from public `/media/`).
- The gate view must **not** set `Content-Length`; nginx sets it from the file.
- Optional edge rate-limit (`limit_req`) can be added to `/media/` later (MED-007), non-blocking for this task.

### 4.3 Django gate view responsibilities

Single small view (single responsibility): resolve → authorize → hand off.

```python
# apps/ads/views/media.py  (new module)
def serve_ad_image(request: HttpRequest, key: str) -> HttpResponse:
    """Authorize access to an ad photo, then hand off to nginx via X-Accel-Redirect."""
    # 1. Validate key shape (defense-in-depth: no slashes / traversal).
    # 2. image = AdImage.objects.select_related("ad").get(image=key)  -> 404 on miss
    # 3. Authorize per matrix (PUBLISHED | owner-non-deleted | staff-moderation).
    # 4. On allow: build empty HttpResponse, set:
    #       resp["X-Accel-Redirect"] = f"/protected_media/{key}"
    #       resp["Content-Type"] = "image/jpeg"
    #    Do NOT read the file in Python.
    # 5. On deny/miss: raise Http404.
```

Responsibilities kept **out** of the view: byte streaming, caching headers,
MIME mapping (all nginx). Keep the module tiny; reuse `AdStatus` enum and the
existing `_staff_required`-style check (or `request.user.is_staff`).

**Dev fallback:** In `DEBUG` (no nginx), `X-Accel-Redirect` is ignored and the
browser gets an empty body. Provide a dev branch that returns
`FileResponse(open(path, "rb"), content_type="image/jpeg")` when
`settings.DEBUG` (or a dedicated setting) so local dev / tests still render
images. Tests assert on the `X-Accel-Redirect` header in the gated (non-DEBUG)
path.

### 4.4 Route placement (acceptance criterion — route placement)

Two viable placements; **recommendation: dedicated `apps.ads` route** because
media is ad-owned and the authorization logic needs `Ad`/`AdStatus`.

Option A (recommended) — add to `apps/ads/urls.py`, but mounted at the
`/media/` prefix. Since `ads.urls` is included at root (`config/urls.py:14`),
add the media path there so it resolves as `/media/<key>`:

```python
# apps/ads/urls.py
from apps.ads.views.media import serve_ad_image
path("media/<str:key>", serve_ad_image, name="serve_media"),
```

`MEDIA_URL` stays `"media/"`, so `AdImage.image_url` (`/media/<key>`) already
targets this route — **no template changes required.**

Option B — a dedicated `path("media/<str:key>", ...)` directly in
`config/urls.py` before the app includes. Functionally equivalent; slightly
less cohesive.

Do **not** rely on Django's `static()` media helper (dev-only, ungated).

---

## 5. Regression Analysis

| Consumer | Before | After gate | Risk |
|----------|--------|-----------|------|
| Public detail/list (PUBLISHED) | served | served (matrix: ALLOW) | none |
| Owner dashboard (ARCHIVED thumb) | served | served **iff owner authed** | LOW — owner is `@login_required` on dashboard; request to `/media/` carries session cookie via same origin → owner check passes |
| Owner edit preview | served | served iff owner authed | LOW — same as above |
| Staff moderation grid | served | served iff staff | LOW — review view is `_staff_required`; media request carries staff session |
| Direct URL to DRAFT/REJECTED/DELETED | served (BUG) | **404** | intended fix |
| Hotlink to PUBLISHED photo | served | served | unchanged (public) |

**Caching caveat:** switch `Cache-Control` from `public, immutable` to
`private` for gated media so a shared/CDN cache never serves a photo of an ad
that later transitions away from PUBLISHED. Browser-private caching is still
fine.

**Performance:** each image request now hits gunicorn for a single indexed
`AdImage` lookup (add/confirm DB index on `AdImage.image`; currently
`CharField(max_length=64)` with no `db_index=True` — recommend `db_index=True`
in the implementation task to keep lookups O(log n) under gallery load).

**Session/cookie:** owner/staff checks require the media request to be
same-origin with cookies. `<img src="/media/...">` on the same site sends
cookies by default → works. No CORS concern.

---

## 6. Recommendations for the Implementation Task (task_044)

1. **nginx:** replace public `/media/` alias with `proxy_pass` to web; add
   `internal` `location /protected_media/` carrying the existing hardening
   headers + JPEG MIME whitelist; set `Cache-Control: private`.
2. **View:** new `apps/ads/views/media.py::serve_ad_image` — resolve
   `AdImage→Ad`, authorize per §3 matrix, set `X-Accel-Redirect` +
   `Content-Type: image/jpeg`; `DEBUG` fallback via `FileResponse`.
3. **Route:** add `path("media/<str:key>", serve_ad_image, name="serve_media")`
   to `apps/ads/urls.py` (root-mounted → `/media/<key>`). No template edits;
   `AdImage.image_url` already emits this path.
4. **Model:** add `db_index=True` to `AdImage.image` (lookup key) via migration.
5. **Key validation:** reject keys containing `/`, `..`, or not matching a
   UUID`.jpg` shape before DB lookup (defense-in-depth vs traversal).
6. **Tests (feeds MED-008):**
   - DRAFT/REJECTED/DELETED photo → 404 for anon.
   - PUBLISHED photo → 200 with `X-Accel-Redirect: /protected_media/<key>`.
   - Owner sees own ARCHIVED photo; non-owner does not.
   - Staff sees `ON_MODERATION` photo; anon does not.
   - Unknown key / traversal → 404.
7. **Docs:** update `docs/01-spec/architecture-structure.md:46-48` (currently
   says photos served "as is") to describe the gated `X-Accel-Redirect` design.

**Out of scope (own findings):** EXIF stripping (MED-002), physical file
deletion in sweeps (MED-003/004), key-generator unification (MED-005). The gate
must **not** be blocked on these.

---

## 7. Verdict (acceptance criterion #3)

### Recommendation: **GO-WITH-CHANGES**

**Go**, because:
- The `X-Accel-Redirect` handoff is the standard, low-risk pattern; the codebase already has a single choke point (`AdImage.image_url`) so no template churn is needed.
- The route can reuse the existing `/media/` prefix and `MEDIA_URL`, making the change transparent to all consumers.

**With changes** (must be honored, else regressions):
1. The gate is an **authorization matrix**, not a bare `status == PUBLISHED`
   check — it must additionally allow the **owner** (non-DELETED) and **staff**
   (moderation queue), or dashboard/edit/moderation previews break.
2. Add a **`DEBUG` `FileResponse` fallback** so local dev/tests still serve
   images (X-Accel-Redirect is nginx-only).
3. Switch gated media to **`Cache-Control: private`** to prevent shared caches
   from serving photos of ads that later leave PUBLISHED.
4. Add **`db_index=True`** on `AdImage.image` and **key-shape validation**
   before the DB hit.

---

## 8. Files Modified for This Research

None — this is a research task. Implementation is tracked in task_044.
The affected files inspected: `docker/nginx/nginx.conf`,
`src/backend/config/urls.py`, `src/backend/apps/ads/urls.py`,
`src/backend/apps/ads/views/listings.py` (plus `ads/models.py`,
`ads/views/dashboard.py`, `moderation/views/review.py`, and the five templates
listed in §2).
