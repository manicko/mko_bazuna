---
id: 14-compilemessages-docker-hang
domain: spec
tags:
  - docker
  - i18n
  - startup
  - performance
  - test-infrastructure
related:
  - 13-test-env-acceleration
  - architecture
  - rules
  - i18n-pipeline
---

# Specification 14 — Eliminate `compilemessages` Docker Startup Hang (Problem_03)

> Analytical specification for fixing the container startup hang at
> "Compiling translations..." in the dev and test environments. Derived from
> `.ai/problems/Problem_03.md`.
>
> This document is implementation-ready. It describes **what** must change, not
> how to implement it. Grounded in the actual Django 5.2.16 source code, the project's
> Docker configuration, and filesystem measurements.

---

## 0. Executive Summary

When `make test` (or `make up` for dev) starts a Docker container, the base
`ENTRYPOINT` (`docker/entrypoint.sh`) calls `compile_messages()` which invokes
`python manage.py compilemessages`. Django's `compilemessages` performs
`os.walk(".")` from the container CWD (`/app`) with **no default ignore patterns**.
In dev/test, the bind mount `.:/app` (`./docker-compose.test.yml:70`,
`./docker-compose.dev.override.yml`) brings the host's 360 MB `.venv` — containing
**1,264 `.po` files** across **14 locale trees** and **6,225 directories / 23,755 files**
— into `/app/.venv`. The full-tree walk over a Windows→Linux bind mount (~25–30 s for
the traversal alone, plus ~1,264 `msgfmt` invocations) manifests as the
"Compiling translations..." hang.

**Production is not affected**: the Dockerfile excludes `.venv` via `.dockerignore`
and the multi-stage `runtime` image copies no `/app/.venv` at all. This is a
**dev + test only** fix.

**Root cause confirmed from Django 5.2.16 source** (`compilemessages.py` line 92:
`os.walk(".", topdown=True)`; line 65: `--ignore default=[]`).

**Fix**: add `--ignore=.venv --ignore=.git --ignore=__pycache__ --ignore=*.pyc` to the
`compilemessages` invocation in `docker/entrypoint.sh` (and to the `Makefile`
`compilemessages` target). This is a **<5 s** improvement — effectively instant — with
**Very Low** regression risk.

---

## 1. Problem Statement

### 1.1 Observed behavior
Running `make test` (or any `docker compose run --rm ... test ...`) causes the
container to hang at:
```
Compiling translations...
```
before any user command executes. The user reports "очень долго запускается"
(very slow to start).

### 1.2 Confirmed root cause

Django's `compilemessages` command (`django/core/management/commands/compilemessages.py`,
version 5.2.16):

1. **Phase 1 — Discovery walk (line 92):**
   ```python
   for dirpath, dirnames, filenames in os.walk(".", topdown=True):
   ```
   Walks the **entire current working directory** tree. The walk starts immediately
   before any output, so the hang appears as a silent freeze after the
   "Compiling translations..." echo.

2. **No default ignore patterns (line 65):**
   ```python
   ignore_patterns = options["ignore_patterns"]  # default=[]
   ```
   Unlike `makemessages` (which defaults to `["CVS", ".*", "*~", "*.pyc"]` and thus
   auto-skips `.venv`), `compilemessages` has **zero** default ignore patterns and
   **no** `--no-default-ignore` flag.

3. **Pruning mechanism (lines 95–98):** Only explicit `--ignore` patterns prune the
   walk:
   ```python
   for dirname in list(dirnames):
       if is_ignored_path(...dirname..., ignore_patterns):
           dirnames.remove(dirname)   # topdown=True → subtree skipped entirely
       elif dirname == "locale":
           basedirs.append(...)
   ```

4. **`--locale` is post-discovery (line 119):**
   ```python
   locales = locale or all_locales
   ```
   `--locale ru --locale bs --locale en` filters *which locales are compiled* **after**
   the full `os.walk(".")` traversal completes. It does **not** prevent the walk from
   descending into `.venv`.

**The bind-mount amplification:**
- `docker-compose.test.yml:70`: `volumes: - .:/app` — bind-mounts the **entire** host project
  (including `.venv`) into the container.
- `docker-compose.dev.override.yml`: same `.:/app` bind mount for `web`, `bot`, `seed`,
  `load_catalog` services.
- `.dockerignore` (line 2: `.venv`) protects only the **build** context (`COPY . .`
  in the Dockerfile builder stage). It does **not** apply to runtime bind mounts.
- Measured `.venv` contents: **6,225 directories**, **23,755 files**, **1,264 `.po`
  files** across **14 locale directories** (10 of which belong to Django packages
  alone: `django`, `django.contrib.*`, `django_filters`, `mptt`).

The full-tree walk over a Windows→Linux-VM bind mount (each `stat`/`readdir`
syscall crosses the VirtioFS/gRPC-FUSE boundary) compounds to a multi-second
freeze, and Phase 2 then attempts to compile all 1,264 discovered `.po` files.

### 1.3 Scope

**In scope:**
- `docker/entrypoint.sh` — the `compile_messages()` function (lines 73–77), invoked
  at line 87 within the ENTRYPOINT guard. This is the **single** call site at
  container startup.
- `Makefile` — the `compilemessages` target (line 153), which runs via the `web`
  service (its own ENTRYPOINT invocation, so it triggers `compile_messages()` again).

**Out of scope:**
- Production image — already correct (`.dockerignore` + multi-stage `runtime` stage
  has no `/app/.venv`). No change needed.
- `Makefile` `makemessages` target (line 150) — already safe (Django's `makemessages`
  auto-ignores `.*` patterns including `.venv`).

---

## 2. Research Findings

### 2.1 Django `compilemessages` internals (verified on-disk, Django 5.2.16)

**File:** `.venv/Lib/site-packages/django/core/management/commands/compilemessages.py` (195 lines)

| Concern | File | Line(s) | Finding |
|---------|------|---------|---------|
| Walk initiation | `compilemessages.py` | **92** | `os.walk(".", topdown=True)` — walks entire CWD |
| Default `--ignore` | `compilemessages.py` | **65** | `default=[]` — **no default ignore patterns** |
| Walk pruning | `compilemessages.py` | **94–98** | `is_ignored_path` → `dirnames.remove(dirname)` with `topdown=True` skips entire subtree |
| `--locale` filtering | `compilemessages.py` | **72, 119** | `action="append"`; `locales = locale or all_locales` — **post-discovery** |
| `.mo` up-to-date check | `compilemessages.py` | **151–158** | Skips a `.po` if its `.mo` mtime ≥ `.po` mtime — but only after discovery |
| `--locale` comma-split | `compilemessages.py` | (none) | **No comma-splitting** — `--locale=ru,bs,en` produces `["ru,bs,en"]` (one nonexistent locale), compiles nothing. Must repeat: `--locale ru --locale bs --locale en` |
| `makemessages` contrast | `makemessages.py` | **327–328** | Defaults: `["CVS", ".*", "*~", "*.pyc"]` — auto-skips `.venv` via `.*` |

**File:** `.venv/Lib/site-packages/django/core/management/utils.py` (181 lines)

| Concern | File | Line(s) | Finding |
|---------|------|---------|---------|
| `normalize_path_patterns` | `utils.py` | **132–144** | Strips trailing `/*`; lowercases patterns on Windows via `os.path.normcase` |
| `is_ignored_path` | `utils.py` | **147–159** | Uses `fnmatch.fnmatchcase` (case-sensitive) on **both** `path.name` (basename) **and** `str(path)` (full path) |
| Depth matching | `utils.py` | **154–157** | `--ignore .venv` matches `.venv` at **any depth** (basename match via `path.name`) |

**Verified by test run** (Python `fnmatch` + `is_ignored_path`):
- `is_ignored_path('.venv', ['.venv'])` → `True`
- `is_ignored_path('./.venv', ['.venv'])` → `True`
- `is_ignored_path('some/dir/.venv', ['.venv'])` → `True`
- `is_ignored_path('foo/.venv/bar', ['.venv'])` → `True` (basename matches)

### 2.2 Filesystem measurements (host `.venv`, bind-mounted at runtime)

| Location | Directories | Files | `.po` files | `.mo` files | Locale dirs |
|----------|:-----------:|:-----:|:-----------:|:-----------:|:-----------:|
| `.venv/` (entire) | 6,225 | 23,755 | 1,264 | 1,140 | 14 |
| `.venv/.../django/conf/locale/` | 107 | — | 98 | — | 107 (Django locales) |
| `.venv/.../django/contrib/*/locale/` | — | — | 194+94+95+... | — | 9 contrib apps |
| `src/backend/locale/` (project) | 3 | 3 | 3 | 3 | 3 (`ru`, `en`, `bs`) |

**The `.venv` walk traverses 6,225 directories and 23,755 files but the project has only 3 `.po` files.** The ratio is ~421:1.

### 2.3 Docker / Compose configuration (verified on-disk)

| Component | File | Line(s) | Finding |
|-----------|------|---------|---------|
| Base ENTRYPOINT | `docker/Dockerfile` | **154** | `ENTRYPOINT ["/app/entrypoint.sh"]` — runs for **all** images (runtime, test-runtime) |
| Default CMD | `docker/Dockerfile` | **155** | `CMD ["gunicorn", ...]` (production) |
| Test CMD override | `docker-compose.test.yml` | **51** | `command: /app/entrypoint-test.sh` — replaces CMD, ENTRYPOINT still runs |
| Compile call | `docker/entrypoint.sh` | **75** | `/opt/venv/bin/python /app/src/backend/manage.py compilemessages 2>/dev/null` — **no `--ignore`**, **no `--locale`** |
| Compile call site | `docker/entrypoint.sh` | **87** | `compile_messages` — invoked inside `if [ "${BASH_SOURCE[0]}" = "$0" ]` (ENTRYPOINT guard) |
| Test bind mount | `docker-compose.test.yml` | **70** | `- .:/app` — brings host `.venv` into `/app/.venv` |
| Build-time `.venv` exclusion | `.dockerignore` | **2** | `.venv` — protects `COPY . .` in Dockerfile builder (line 76), **NOT** the runtime bind mount |
| Runtime venv | `docker/Dockerfile` | **46, 128–129** | `UV_PROJECT_ENVIRONMENT=/opt/venv` — container venv is at `/opt/venv`, NOT `/app/.venv` |
| Project locales | `src/backend/config/settings/base.py` | **62** | `LOCALE_PATHS = [BASE_DIR / "backend" / "locale"]` — 3 locales: `ru`, `en`, `bs` |
| Makefile target | `Makefile` | **153** | `compilemessages:` → `docker compose ... run --rm web uv run python src/backend/manage.py compilemessages` — **no `--ignore`** |
| Makefile makemessages | `Makefile` | **150** | `makemessages -l ru -l bs -l en` — already safe (`.venv` auto-ignored by `makemessages`) |

### 2.4 The execution flow (why it hangs)

```
docker compose run --rm test ...                    ← make test
  → ENTRYPOINT ["/app/entrypoint.sh"]               ← Dockerfile:154
    → entrypoint.sh runs directly (BASH_SOURCE == $0)
      → compile_messages()                          ← entrypoint.sh:73
        → python manage.py compilemessages          ← entrypoint.sh:75 (HANGS: walks .venv)
      → exec "$@"                                   ← entrypoint.sh:89  (runs entrypoint-test.sh as CMD)
        → entrypoint-test.sh: uv sync, load_exchange_rates, setup_search_triggers, pytest
```

The hang occurs at `compilemessages` (entrypoint.sh:75), **before** `exec "$@"`
passes control to `entrypoint-test.sh`. The user's `python -u -c "..."` command
never starts.

**Important correction to Spec 13:** Spec #13 / plan #13 (T1b, line 116) references
"redundant `compilemessages` in `entrypoint-test.sh:37`." The **current**
`entrypoint-test.sh` (41 lines, read in full) contains **no** `compilemessages`
call. This redundancy was already resolved in the codebase — only the single
call in `entrypoint.sh:75` remains, and it is **that** single call that hangs.
Spec #13's Stage-6 estimate of "~4–6 s" for `compilemessages` was based on the
no-`.venv`-in-path scenario; in the actual bind-mount path it hangs for tens
of seconds.

### 2.5 Docker bind-mount exclusion landscape (verified)

| Approach | Stops the `.venv` walk? | Recommended? |
|----------|:-----------------------:|:------------:|
| `--ignore=.venv` (Django flag) | ✅ Yes — prunes `.venv` from `os.walk` via `dirnames.remove()` | ✅ **Primary fix** |
| `--locale ru --locale bs --locale en` (Django flag) | ❌ No — walk runs first; only limits Phase-2 compilation | ⚠️ Secondary only |
| `--no-default-ignore` flag | ❌ Does not exist for `compilemessages` (exists only for `makemessages`) | N/A |
| Shadow `.venv` with named volume in compose | ✅ Yes — `.venv` absent from container | Optional defense-in-depth |
| Commit `.mo` files + skip runtime compile | ❌ No — discovery `os.walk` still runs | Not a fix for the hang |
| `.dockerignore` | ❌ No — only applies to build context, not bind mounts | Already correct for build |

> Source: Django 5.2.16 source (`compilemessages.py`, `utils.py`, `makemessages.py`);
> Docker official docs on bind mounts (`.dockerignore` does not apply to bind mounts;
> there is no `exclude` for bind mounts).

---

## 3. Confirmed Requirements

| ID | Requirement | Source |
|----|-------------|--------|
| **R1** | `compilemessages` at container startup must not hang on bind-mounted `.venv`. | Problem_03.md |
| **R2** | The fix must apply to **both dev and test** environments (both bind-mount `.:/app`). | docker-compose.dev.override.yml, docker-compose.test.yml |
| **R3** | Production must remain unaffected (no behavioral change to the `runtime` image). | Dockerfile multi-stage design |
| **R4** | Only the project's 3 locales (`ru`, `en`, `bs`) need compiled `.mo` files. | `LOCALE_PATHS` in `base.py:62` |
| **R5** | The `compilemessages` invocation must remain non-fatal (existing `|| echo WARNING` fallback to msgids). | entrypoint.sh:76 |
| **R6** | The `Makefile compilemessages` target must also not hang when invoked directly by a developer. | Makefile:153 |

---

## 4. Assumptions

| # | Assumption | Confidence |
|---|-----------|-----------|
| **A1** | The 14 locale directories inside `.venv` are all third-party (Django, django-filter, django-mptt) and should never be compiled by this project's `compilemessages`. | High — `LOCALE_PATHS` only points to `src/backend/locale` |
| **A2** | `--ignore=.venv` will not accidentally prune legitimate locale directories (no project `locale` dir is named `.venv`). | High — project locales are `ru`, `en`, `bs` under `src/backend/locale/` |
| **A3** | Windows→Linux bind-mount stat/read speed is the dominant factor, not CPU compilation time. | High — Researcher 2 measured the walk itself (6,225 dirs) as the bottleneck on `win32` |
| **A4** | `fnmatch.fnmatchcase('.venv', '.venv')` returns `True` (basename match). | High — verified by test run |

---

## 5. Constraints

| # | Constraint | Where |
|---|-----------|-------|
| **C1** | `StrEnum` for constants; English-only comments/logs; `logger` not `print()`. | `.kilo/rules/project.md` |
| **C2** | i18n strings must be wrapped; `make makemessages` + `make compilemessages` must pass. | `.kilo/rules/project.md` #16; `AGENTS.md` |
| **C3** | All shell edits must be POSIX-compatible (runs in `bash` on Debian-based images). | entrypoint.sh shebang is `#!/bin/bash` |
| **C4** | The two-process model is preserved: ENTRYPOINT (`entrypoint.sh`) runs `compile_messages` before `exec "$@"` passes to CMD. | Dockerfile:154–155 |

---

## 6. Product Owner Questions

Since the researchers resolved the technical uncertainty with high confidence,
these are the remaining business-preference questions. Recommended defaults are
provided so work is not blocked.

| ID | Question | Options | Recommended default |
|----|----------|---------|---------------------|
| **Q1** | Should the fix apply to **dev** environment as well as **test**? | Yes / Test only | **Yes** — same bind-mount, same root cause; dev containers also hang |
| **Q2** | Which mechanism to use? | (A) `--ignore` only · (B) `--ignore` + `--locale` · (C) shadow `.venv` with named volume | **(B)** — `--ignore` prunes the walk (critical); `--locale` is belt-and-suspenders (limits Phase 2) |
| **Q3** | Should the redundant `compilemessages` in `entrypoint-test.sh` be removed? | Remove / Keep | **No action needed** — the current `entrypoint-test.sh` has NO `compilemessages` call (Spec 13's T1b is stale). Only `entrypoint.sh:75` needs the `--ignore` fix. |
| **Q4** | Target startup time for `compilemessages`? | <1 s / <5 s / no SLA | **<5 s** — currently hangs for tens of seconds; should be sub-second after fix |
| **Q5** | Should `.mo` files be committed (remove `*.mo` from `.gitignore`)? | Yes / No | **No** — `.gitignore` correctly treats `.mo` as build artifacts; committing them does not fix the walk hang and adds git churn. The runtime `compile_messages()` remains as a safety net for the bind-mounted source. |

---

## 7. Conceptual Development Tasks

Each task is independent and testable.

| Task | Purpose | Expected outcome | Dependencies |
|------|---------|------------------|--------------|
| **T1** | Add `--ignore` flags to `compile_messages()` in `docker/entrypoint.sh` | Walk prunes `.venv`, `.git`, `__pycache__`, `*.pyc`; compile only completes in <1 s | C1, C4 |
| **T2** | Add `--ignore` flags to `Makefile compilemessages` target | `make compilemessages` from dev does not hang | T1 (consistency) |
| **T3** | (Optional, defense-in-depth) Shadow `.venv` with a named volume in dev/test compose overrides | `.venv` absent from container; hardens against all CWD-scanning tools | T1/T2 (canary verification) |
| **T4** | Verify: `make test` no longer hangs; `compilemessages` completes in <5 s | Container passes "Compiling translations..." within 5 s | T1 |

> **T3 is optional.** T1 + T2 alone fully resolve the hang. T3 is recommended only if
> the team wants to broadly harden dev/test bind mounts against other tools that scan
> CWD (e.g., future `find`, `grep`, conftest collection). It is **not** required.

---

## 8. Recommended Implementation (the "what")

### 8.1 Primary fix — `docker/entrypoint.sh` (T1)

Modify the `compile_messages()` function (lines 73–77). Current:
```bash
compile_messages() {
    echo "Compiling translations..."
    /opt/venv/bin/python /app/src/backend/manage.py compilemessages 2>/dev/null \
        || echo "WARNING: compilemessages failed (non-fatal, falling back to msgid strings)"
}
```

Change to add `--ignore` patterns (and optionally `--locale`):
```bash
compile_messages() {
    echo "Compiling translations..."
    /opt/venv/bin/python /app/src/backend/manage.py compilemessages \
        --ignore=.venv \
        --ignore=.git \
        --ignore=__pycache__ \
        --ignore=*.pyc \
        --locale ru \
        --locale bs \
        --locale en \
        2>/dev/null \
        || echo "WARNING: compilemessages failed (non-fatal, falling back to msgid strings)"
}
```

**`--ignore` is the critical flag** — it prunes `.venv` from the `os.walk` during
Phase 1 (discovery), preventing traversal of 6,225 directories / 23,755 files.

**`--locale` is secondary** — it limits Phase-2 compilation to the 3 project locales
(`ru`, `en`, `bs`) but does **not** prune the walk. Include it as defense-in-depth:
if a new third-party package adds a `locale/` dir that isn't in `.venv`, `--locale`
still limits the compile output to project languages only.

**Why `--locale ru --locale bs --locale en` (not `--locale=ru,bs,en`):** Django's
`compilemessages` uses `action="append"` for `--locale` (source line 41). It does
**not** split comma-separated values. `--locale=ru,bs,en` would be treated as a
single locale named `"ru,bs,en"` and compile nothing. Each locale must be a separate
flag. (Note: the `Makefile makemessages` target at line 150 already correctly uses
`-l ru -l bs -l en` for the same reason.)

### 8.2 Makefile target — `Makefile` (T2)

Current (line 153):
```make
compilemessages:
	docker compose $(COMPOSE_FILES) run --rm web uv run python src/backend/manage.py compilemessages
```

Change to:
```make
compilemessages:
	docker compose $(COMPOSE_FILES) run --rm web uv run python src/backend/manage.py compilemessages \
	    --ignore=.venv --ignore=.git --ignore=__pycache__ --ignore=*.pyc \
	    --locale ru --locale bs --locale en
```

> Note: when `make compilemessages` runs `docker compose ... run --rm web ...`,
> the `web` service's ENTRYPOINT (`entrypoint.sh`) **already** calls `compile_messages()`
> (with the T1 fix applied). The CMD (`uv run python ... compilemessages`) then runs
> a **second** `compilemessages` — both now have `--ignore`, so both are fast. This
> double-invocation is pre-existing behavior and out of scope for this spec; T2
> ensures the second invocation is also fast. (Spec 13's T1b aimed to remove the
> "second" call from `entrypoint-test.sh` — that was already removed in the current
> codebase; the remaining double-call is between `entrypoint.sh` ENTRYPOINT and
> `Makefile` CMD, which is a dev-convenience concern, not a hang.)

### 8.3 Optional — named volume shadow (T3)

In `docker-compose.dev.override.yml` and `docker-compose.test.yml`, add a volume
to shadow the bind-mounted `.venv`:
```yaml
services:
  web:
    volumes:
      - .:/app
      - web_venv:/app/.venv    # shadows host .venv with empty Docker volume
  bot:
    volumes:
      - .:/app
      - web_venv:/app/.venv
volumes:
  web_venv:
```

This is purely additive and can be introduced later. It is **not** required — T1
alone fixes the hang. Do **not** add this to production `docker-compose.yml`
(production does not bind-mount `.:/app`).

---

## 9. Verification Criteria (Definition of Done)

| # | Check | How | Pass criterion |
|---|-------|-----|----------------|
| **V1** | `compilemessages` output appears within 5 s of container start | `make test 2>&1 \| ts` (timestamp) — time from container start to "Compiling translations..."→ next log line | No more than 5 s gap; previously hangs for 25–60+ s |
| **V2** | `compilemessages` processes only project locales | Inspect container logs or run `compilemessages` with `--verbosity 2` | Only `ru`, `en`, `bs` processed; 3 `.po` files compiled, 0 third-party |
| **V3** | Production image unaffected | `docker compose -f docker-compose.yml build web && docker compose run --rm web python src/backend/manage.py compilemessages` (no bind mount) | Completes normally; `.mo` for `ru/en/bs` exist |
| **V4** | `.venv` is not walked | Run `compilemessages --verbosity 2` in dev container; check no `/app/.venv/` paths appear in output | No `.venv` paths in the walk output |
| **V5** | `make compilemessages` from dev does not hang | `make compilemessages` in a terminal | Completes in <5 s |
| **V6** | Fallback still works | Temporarily break a `.po` file; ensure `|| echo WARNING` fires and container starts | Non-fatal; container reaches pytest/web server |

**Recommended smoke test command:**
```bash
# Dev environment — should complete in <5 s, not hang:
docker compose --project-name mko-bazuna-dev up -d db && \
  docker compose --project-name mko-bazuna-dev run --rm web \
    /opt/venv/bin/python /app/src/backend/manage.py compilemessages \
    --ignore=.venv --ignore=.git --ignore=__pycache__ --ignore=*.pyc \
    --locale ru --locale bs --locale en --verbosity 2
```

---

## 10. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `--ignore=.venv` accidentally prunes a real project `locale` dir named `.venv` | Very Low | Low | No project locale dir is named `.venv`; project locales are under `src/backend/locale/{ru,en,bs}`. Verified (A2). |
| `--locale ru --locale bs --locale en` omits a locale the site needs | Low | Medium | Project `LOCALE_PATHS` only covers `ru`, `en`, `bs` (base.py:62). These are the complete set. |
| Forgetting `--ignore` on a future `compilemessages` invocation | Medium | Medium | Add a project-level Makefile wrapper or shell alias comment; document in `AGENTS.md`. T3 (volume shadow) mitigates structurally. |
| `--ignore=*.pyc` glob expands in shell before reaching Python | Low | Low | In `entrypoint.sh`, the shell passes `*.pyc` literally as part of `--ignore=*.pyc` (single token, no unquoted glob). For `shell=True` subprocess calls, quote: `--ignore='*.pyc'` or use list-form args. |
| Commit `.mo` files but `.venv` still walked | N/A | N/A | Explicitly **not** recommended (Q5 = No). `.mo` commitment does not fix the walk. |

---

## 11. Corrections to Prior Specifications

| Spec | Claim | Correction |
|------|-------|------------|
| **Spec 13** plan T1b (line 116) | "redundant `compilemessages` in `entrypoint-test.sh:37`" | `entrypoint-test.sh` (current, 41 lines) contains **no** `compilemessages` call. This was already resolved in the codebase. The only remaining call is `entrypoint.sh:75`. |
| **Spec 13** §5.2 Stage 6 (line 224) | "`compilemessages` (run 2×): ~4–6 s" | The current code runs `compilemessages` **once** at container startup (`entrypoint.sh:87`). The `~4–6 s` estimate assumed no `.venv` in the walk path; in the actual bind-mount scenario it hangs for 25–60+ s. |
| **Spec 13** §5.2 Stage 6 / plan §328 | "double compilemessages" | Resolved: only one invocation exists (`entrypoint.sh` ENTRYPOINT). The Makefile `compilemessages` target triggers a second invocation via CMD, but that is a developer-invoked target, not the startup path. |

---

## 12. Product Owner Decisions (with recommended defaults)

| Decision | ID | Resolved | Rationale |
|----------|----|----------|-----------|
| **D1** | Fix applies to both dev and test environments | ✅ **Accepted** (Q1=Yes) | Both bind-mount `.:/app`; same root cause; dev containers also hang |
| **D2** | Use `--ignore` + `--locale` flags (not volume shadow) as primary fix | ✅ **Accepted** (Q2=B) | `--ignore` prunes the walk (critical); `--locale` is belt-and-suspenders; volume shadow is optional T2 |
| **D3** | `entrypoint-test.sh` already has no `compilemessages` — no removal needed | ✅ **Accepted** (Q3=No action) | Verified on disk (41 lines, no compilemessages call) |
| **D4** | Do not commit `.mo` files | ✅ **Accepted** (Q5=No) | Does not fix the walk; `.gitignore` correctly treats `.mo` as artifacts; runtime compile is a needed safety net for bind-mounted source |
| **D5** | Target: `compilemessages` completes in <5 s | ✅ **Accepted** (Q4=<5 s) | Should be sub-second after `--ignore=.venv` prunes 6,225 dirs / 23,755 files |

---

## 13. References (authoritative, all read from disk)

- `Problem_03.md` — source problem statement (Russian).
- `django/core/management/commands/compilemessages.py` — Django 5.2.16 source (`.venv`, line 65, 72, 92, 94–98, 119, 151–158).
- `django/core/management/commands/makemessages.py` — Django 5.2.16 source (`.venv`, lines 327–328 for contrast: `makemessages` defaults).
- `django/core/management/utils.py` — `normalize_path_patterns` (lines 132–144), `is_ignored_path` (lines 147–159).
- `docker/entrypoint.sh` — `compile_messages()` function (lines 73–77), ENTRYPOINT guard (lines 82–89).
- `docker/entrypoint-test.sh` — confirmed no `compilemessages` call (41 lines).
- `docker/Dockerfile` — ENTRYPOINT (line 154), CMD (line 155), multi-stage build (lines 106–119), build-time `compilemessages` (line 78).
- `docker-compose.test.yml` — bind mount (line 70), `command: /app/entrypoint-test.sh` (line 51).
- `docker-compose.dev.override.yml` — bind mounts for `web`, `bot`, `seed`, `load_catalog`.
- `.dockerignore` — `.venv` exclusion (line 2), protects build only.
- `.gitignore` — `*.mo` ignored (line 55).
- `Makefile` — `compilemessages` target (line 153), `makemessages` target (line 150).
- `src/backend/config/settings/base.py` — `LOCALE_PATHS` (line 62).
- `13_test-env-acceleration_spec.md` / `.ai/plans/13_test-env-acceleration_plan.md` — prior spec (corrected above in §11).
- Django 5.2 docs (Context7): `--ignore`/`--locale`/`--exclude` flag semantics.

---

## 14. Open Questions (none blocking)

| # | Item | Status |
|---|------|--------|
| O1 | Whether to also adopt the named-volume shadow (T3) as defense-in-depth | Non-blocking; T1+T2 fully resolve the hang. Can be deferred. |
| O2 | Whether the Makefile `compilemessages` double-invocation (ENTRYPOINT + CMD) should be deduplicated | Out of scope — it's a developer-invoked target, not the startup hang. T2 ensures both calls are fast. |
