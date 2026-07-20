# Bug report — stray SQLite database file committed under src/backend

**ID:** BUG-003
**Severity:** MEDIUM (image bloat / potential dev-data leak)
**Scope:** out-of-scope for task_001 (import-root research) — discovered while checking
for hidden consumers of the broken import root.
**Status:** reported (not fixed here)

## Symptom

`src/backend/mko_bazuna` is a 241 KB binary file whose first 16 bytes are
`SQL ite format 3\0` — i.e. a **SQLite database**, not a Python module. It sits inside the
source tree that is copied into the container image.

## Root cause

A SQLite DB was created at `src/backend/mko_bazuna` (likely a local `migrate` run with a
SQLite fallback, or a misconfigured `NAME`). It was never removed and is not excluded by
`.dockerignore`, so `COPY . .` in `docker/Dockerfile` ships it into every built image.

## Impact

- Bloats the image with an unintended artifact.
- If it contains local/dev data, that data is baked into the image.
- Confusing dead artifact in the import-root directory.

## Evidence

```
PS> $bytes = ReadAllBytes("src/backend/mko_bazuna")[0..15]; $bytes -join ','
83,81,76,105,116,101,32,102,111,114,109,97,116,32,51,0   # "SQLite format 3\0"
PS> (Get-Item src/backend/mko_bazuna).Length
241664
```

`.dockerignore` excludes `*.egg-info/`, `__pycache__/`, `media/`, `staticfiles/` but
**not** arbitrary `.sqlite3`/DB files under `src/`.

## Recommendation (for a separate task)

- Delete `src/backend/mko_bazuna` from the working tree (after confirming it is not the
  live DB for any needed local state).
- Add a `.dockerignore` rule (e.g. `*.sqlite3` / `*.db` / `src/backend/mko_bazuna`) so
  local DB files are never copied into the image.
- Confirm `DATABASES` always points at PostgreSQL (spec mandates PostgreSQL only) and no
  code path falls back to SQLite.
