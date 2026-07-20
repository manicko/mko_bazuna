# Bug report — MEDIA_ROOT / STATIC_ROOT resolve under /app/src but volumes mount elsewhere

**ID:** BUG-002
**Severity:** HIGH (deployment correctness)
**Scope:** out-of-scope for task_001 (import-root research) — discovered while auditing
`docker/Dockerfile` and `src/backend/config/settings/base.py`.
**Status:** reported (not fixed here)

## Symptom

Uploaded media and collected static files are written to ephemeral image paths instead of
the persistent volume / copied location, so they are lost on container restart and not
served by nginx/whitenoise.

## Root cause

`src/backend/config/settings/base.py`:

```python
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
STATIC_ROOT = BASE_DIR / "staticfiles"   # -> /app/src/staticfiles
MEDIA_ROOT  = BASE_DIR / "media"         # -> /app/src/media
```

The settings file lives at `src/backend/config/settings/base.py`; four parents up is
`/app/src` (not `/app`). So in-container:

- `MEDIA_ROOT  = /app/src/media`
- `STATIC_ROOT = /app/src/staticfiles`

But the deployment mounts/points elsewhere:

- `docker-compose.yml` mounts `media_volume` at `/app/media` (web + bot services), and
  nginx proxies `/media_volume` (prod) — none of these equal `/app/src/media`.
- `docker/Dockerfile` runs `collectstatic` (outputs to `/app/src/staticfiles`) but copies
  `COPY --from=builder ... /app/staticfiles` (the wrong path), and serves via whitenoise
  from `STATIC_ROOT` = `/app/src/staticfiles`.

Result: media uploads land in `/app/src/media` (ephemeral, not the volume) and static is
collected to `/app/src/staticfiles` but the image only carries `/app/staticfiles`.

## Evidence

- `base.py` `BASE_DIR` chain (4 parents from `src/backend/config/settings/base.py` → `src`).
- `docker-compose.yml`: `media_volume:/app/media` (web, bot).
- `docker/Dockerfile`: `COPY --from=builder ... /app/staticfiles`.

## Recommendation (for a separate task)

Either (1) set `MEDIA_ROOT`/`STATIC_ROOT` to paths that match the mounts
(`/app/media`, `/app/staticfiles`), or (2) move the source tree so `BASE_DIR` resolves to
`/app` (e.g. layout `config`/`apps` directly under `/app`). Do NOT fix as part of the
import-root boot fix (task_006).
