# Research — Container boot & Python packaging strategy (T001)

**Source task:** `task_001_research_boot_packaging` (research, `type: research`)
**Feeds:** `task_006_fix_container_boot` (ENT-001 / ENT-007)
**Verdict:** **GO (with changes)** — adopt strategy **(b) PYTHONPATH**.

---

## 1. Root cause (ENT-001 / ENT-007)

- `docker/Dockerfile` installs deps with `uv sync --frozen --no-install-project`
  (builder stage), so the project package is **never installed** into the venv.
- `pyproject.toml` `[tool.setuptools.packages.find]` declares
  `where = ["."]` and `include = ["mko_bazuna*", "mko_bazuna.src", "mko_bazuna.core"]`,
  but **no `mko_bazuna*` package exists**. The real top-level importable names are
  `apps`, `config`, `theme` (under `src/backend`) and `telegram_bot` (under `src`).
- Confirmed dead config: `mko_bazuna.egg-info/top_level.txt` is **empty** — setuptools
  discovered zero top-level packages, matching nothing.
- The actual layout is **split across two roots**, which is the crux of the strategy choice:
  - `src/backend` → `apps`, `config`, `theme`, `manage.py`
  - `src` → `telegram_bot`, plus `src/__init__.py`

## 2. Strategy decision

Two strategies were on the table; **(b) is lower risk** and is the recommended fix.

### (a) Install the project (`uv sync` without `--no-install-project` + fix discovery)
- Requires reconciling `[tool.setuptools.packages.find]` to the split layout. A single
  `where` cannot span both `src/backend` and `src`; it would need two `[[tool.setuptools.packages.find]]`
  directives (one per root).
- **Collision risk:** the top-level names `apps`, `config`, `theme` are extremely generic.
  Installing them into the shared venv `site-packages` invites namespace collisions with
  any other dependency that claims those names and makes the deployment order-dependent.
- Larger rebuild surface and more moving parts for a container-only benefit.

### (b) `PYTHONPATH=/app/src/backend:/app/src` (CHOSEN)
- Handles both import roots natively and **isolates** them from `site-packages` — no
  generic-name collision risk.
- Already present in the current `docker/Dockerfile` (builder **and** runtime `ENV`),
  so this research confirms the in-flight fix is correct rather than proposing fresh work.
- Keeps `--no-install-project`, avoiding setuptools discovery churn and a larger rebuild.
- `uv run` only injects the **current working directory** onto `sys.path`, not
  `/app/src` or `/app/src/backend`; the explicit `ENV PYTHONPATH` is what makes all
  processes importable from `WORKDIR /app`.

**Verdict:** GO (with changes). Strategy (b) is correct and already applied in the
Dockerfile. `task_006` must (1) confirm the `ENV PYTHONPATH` survives in both stages,
(2) verify every entrypoint below boots, and (3) reconcile the dead `pyproject.toml`
package-discovery block so the file is honest (see §5).

## 3. Per-process import roots (chosen layout)

| Root | Resolves |
|------|----------|
| `/app/src/backend` | `apps`, `config`, `theme`, `manage.py` |
| `/app/src` | `telegram_bot` |

## 4. Every entrypoint that depends on the chosen layout

Enumerated from `docker-compose.yml`, `docker-compose.prod.yml`, and the entrypoint scripts:

1. **web** — `gunicorn config.wsgi:application` (needs `config` from `/app/src/backend`).
2. **bot** — `python -m telegram_bot.main` (needs `telegram_bot` from `/app/src`;
   transitively imports `apps`/`config` after `django.setup()` — see ENT-002 / T007).
3. **migrate** — `uv run python -c "from apps.core.utils.migrate_locked import main"`,
   which then `subprocess`-runs `src/backend/manage.py migrate` (needs `apps` + `config`).
4. **scheduler** — `entrypoint-scheduler.sh` loops `src/backend/manage.py <command>`
   (`archive_sweep`, `delete_sweep`, …) (needs `apps` + `config`).
5. **test (CI)** — `entrypoint-test.sh` runs `uv run pytest --tb=short` from `/app`;
   `conftest.py` does `django.setup()` → `config.settings.test` (needs `config`).
   Covered by the `PYTHONPATH` `ENV` **and** by `pyproject.toml`
   `[tool.pytest.ini_options] pythonpath = ["src/backend", "src"]` (pytest adds these
   during collection). `--import-mode=importlib` does NOT add the repo root, so the
   explicit `pythonpath` is required (ENT-006, merged into T006).

All five resolve correctly once `ENV PYTHONPATH=/app/src/backend:/app/src` is present in
the image. No other process or script imports from a divergent root.

## 5. Hidden-consumers check (acceptance: none of the broken import root)

- Grep across `src/` for `import mko_bazuna` / `from mko_bazuna` / `mko_bazuna.` →
  **zero matches**. No code imports via the (non-existent) `mko_bazuna` package.
- The only `mko_bazuna` references are:
  - `pyproject.toml` dead `include = ["mko_bazuna*", ...]` patterns (config only, inert
    under `--no-install-project`).
  - `mko_bazuna.egg-info/` build metadata (generated, `.dockerignore`d).
  - A stray `src/backend/mko_bazuna` **SQLite database file** (241 KB) — see bug report
    `00-bug_report/03-stray_sqlite_under_src_backend.md`; it is data, not an import consumer,
    but it would be copied into the image by `COPY . .` (not covered by `.dockerignore`).
- `src/telegram_bot/__init__.py` eagerly imports handlers/middlewares → that is the
  ENT-002 import-order defect, owned by `task_007`, **not** an import-root consumer.

**Conclusion:** no hidden consumers of the broken import root beyond the entrypoints in §4.

## 6. pyproject changes (decision for task_006)

Because strategy (b) keeps `--no-install-project`, the `[tool.setuptools.packages.find]`
block is inert at runtime, but it is **misleading** (ENT-007). Recommended minimal change
to make the file honest and future-proof:

```toml
# Project is NOT installed in the image; import roots are provided via
# ENV PYTHONPATH=/app/src/backend:/app/src (see docker/Dockerfile).
# If installation is ever enabled, discover the real split layout:
[[tool.setuptools.packages.find]]
where = ["src/backend"]
include = ["apps*", "config*", "theme*"]

[[tool.setuptools.packages.find]]
where = ["src"]
include = ["telegram_bot*"]
```

This replaces the dead `mko_bazuna*` patterns. Low priority for boot, but satisfies
ENT-007's "reconcile package discovery" and prevents a future `uv sync` (without
`--no-install-project`) from silently installing nothing.

## 7. Out-of-scope issues (logged as bug reports, NOT part of this fix)

- **Media/static root vs volume mount mismatch** — `base.py` `BASE_DIR` resolves to
  `/app/src` in-container (settings live at `src/backend/config/settings/base.py`, four
  parents up = `src`), so `MEDIA_ROOT=/app/src/media` and `STATIC_ROOT=/app/src/staticfiles`.
  But `docker-compose.yml` mounts `media_volume` at `/app/media` and the Dockerfile copies
  `/app/staticfiles`. Uploads/static would land on ephemeral image paths, not the
  persistent volume. Logged in `00-bug_report/02-media_static_root_mount_mismatch.md`.
- **Stray SQLite file under `src/backend`** — see `00-bug_report/03-stray_sqlite_under_src_backend.md`.

---

## Verdict (explicit)

**GO (with changes).** Strategy (b) `PYTHONPATH=/app/src/backend:/app/src` is the
lower-risk fix and is already present in `docker/Dockerfile` (both stages). `task_006`
should treat this as GO-WITH-CHANGES: verify all five entrypoints (§4) boot/collect under
the image `ENV PYTHONPATH`, and reconcile the dead `pyproject.toml` discovery block (§6).
Do **not** switch to strategy (a): the generic top-level names (`apps`, `config`, `theme`)
make `site-packages` installation collision-prone and the split two-root layout makes a
single setuptools `find` awkward.
