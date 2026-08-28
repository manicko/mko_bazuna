---
id: 14-compilemessages-docker-hang-plan
domain: plan
tags:
  - docker
  - i18n
  - performance
  - startup
  - test-infrastructure
  - risk:very-low
related:
  - 14_compilemessages-docker-hang_spec
  - 13_test-env-acceleration_plan
  - i18n-pipeline
source_spec: .ai/problems/14_compilemessages-docker-hang_spec.md
---

# Implementation Plan 14 — Eliminate `compilemessages` Docker Startup Hang

> Transforms `14_compilemessages-docker-hang_spec.md` into a dependency-aware,
> independently-executable task set. The spec is already research-backed
> (Django 5.2.16 source citations, verified `fnmatch`/`is_ignored_path` results,
> filesystem measurements, options analysis). This plan preserves that work and
> sequences it for safe, reviewable rollout. **No research agents required** —
> the findings are authoritative and on-disk state has been reconciled (§2).

---

## 1. Overview

| Dimension | Current state | Target state |
|---|---|---|
| Container startup | Hangs at "Compiling translations..." for 25–60+ s (walks host `.venv` via bind mount) | `compilemessages` completes in <5 s (sub-second) |
| Root cause | `python manage.py compilemessages` in `compile_messages()` runs with **no `--ignore`**; Django's `compilemessages` has zero default ignore patterns and `os.walk(".")` descends into bind-mounted `/app/.venv` (6,225 dirs / 23,755 files / 1,264 `.po`) | `--ignore=.venv --ignore=.git --ignore=__pycache__ --ignore='*.pyc'` prunes the walk at the `dirnames.remove()` step (topdown=True) |
| Scope | Dev (`.:/app` bind mount) + test (`.:/app` bind mount) | Production `runtime` image untouched (`.venv` excluded at build by `.dockerignore`; no bind mount) |

**Single fix primitive:** add `--ignore` patterns (prunes `os.walk`) **+** `--locale ru --locale bs --locale en` (limits Phase-2 compile to project locales only). Both flags are standard Django 5.2 `compilemessages` options (spec §2.1).

---

## 2. Findings vs Spec (on-disk reconciliation)

| Spec § | Spec claim | On-disk verification | Notes |
|---|---|---|---|
| §2.4 / §2.5 | `entrypoint.sh:75` is the single startup `compilemessages` call site | Confirmed: `compile_messages()` defined at `entrypoint.sh` `compile_messages` fn; invoke at the ENTRYPOINT guard (`if [ "${BASH_SOURCE[0]}" = "$0" ]`) | Consumer surface is known and bounded |
| §2.5 | `entrypoint-test.sh` (41 lines) has NO `compilemessages` call; Spec 13's `entrypoint-test.sh:37` removal is stale | Confirmed: `entrypoint-test.sh` reads 41 lines, ends with `uv run pytest ...` | No stale double-call to remove |
| §2.5 | `make compilemessages` triggers a SECOND `compilemessages` (via CMD override) after ENTRYPOINT already ran it | Confirmed: `web` service has no `entrypoint:` override → Dockerfile `ENTRYPOINT ["/app/entrypoint.sh"]`; `make compilemessages` passes a CMD override (`uv run python ... compilemessages`) → ENTRYPOINT runs `compile_messages()` first, then `exec "$@"` runs the CMD. **Two invocations.** | This is why T2 is required (not mere consistency) |
| §2.3 / R4 / A2 | Project locales are `ru`, `en`, `bs`; `LOCALE_PATHS = [BASE_DIR / "backend" / "locale"]` | Confirmed: `base.py` `LANGUAGES = [("ru",…),("bs",…),("en",…)]`; `LOCALE_PATHS = [BASE_DIR / "backend" / "locale"]` → `src/backend/locale/{ru,en,bs}` | `--locale ru --locale bs --locale en` covers the complete set |
| §2.3 / R3 | Production build-time `compilemessages` (`Dockerfile:78`) is unaffected; runtime image has no `/app/.venv` | Confirmed: `.dockerignore:2` excludes `.venv` from build context; `Dockerfile:128-129` sets `UV_PROJECT_ENVIRONMENT=/opt/venv` (container venv ≠ host `.venv`) | Prod is structurally safe — `--ignore=.venv` finds nothing to ignore |
| §2.3 / Q5 | `.gitignore:55` → `*.mo` ignored | Confirmed | Q5 (do not commit `.mo`) supported — runtime `compile_messages()` remains the safety net |
| §5.4 / §14 | Prior Spec 13 Stage-6 "~4–6 s" estimate assumes no `.venv` in walk path | Confirmed stale → real bind-mount path hangs 25–60+ s | This spec (#14) supersedes |

**No contradictions within spec #14.** All claims verified on disk. No corrections needed beyond what the spec self-documents.

---

## 3. Task Dependency Graph (DAG)

```
T1 ──┐
T2 ──┤
  │  │
  ▼  ▼
V1 (verification gate)        ← canary proof the hang is gone
  │
  ▼
T3 (OPTIONAL) — volume shadow  ← defense-in-depth; only after V1 passes
```

- **T1** and **T2** edit *independent files* with the *same flag set*: parallelizable.
- **V1** depends on both (confirms the behavioral DoD: no hang, only 3 locales, `.venv` not walked, `.mo` green, prod unaffected).
- **T3** is optional and **blocked on V1** (canary: harden only after the fix is proven).

---

## 4. Task Specifications

### T1 — Add `--ignore` + `--locale` flags to `compile_messages()` in `docker/entrypoint.sh`

- **Priority:** Critical (primary fix; resolves the startup hang for dev + test).
- **Risk:** Very Low — non-fatal fallback (`|| echo WARNING ...`) preserved; `set -e` respected (`cmd || echo` is a guarded list); worst case degrades gracefully to msgid fallback exactly as today's failure mode.
- **Files:** `docker/entrypoint.sh`
- **Semantic anchor:** `compile_messages` function → the `python ... compilemessages` invocation inside it.

**Current behavior** (semantically): `compile_messages()` invokes `/opt/venv/bin/python /app/src/backend/manage.py compilemessages 2>/dev/null` with no `--ignore`/`--locale`, then falls back to a WARNING echo on failure.

**Changes:**
1. Add `--ignore=.venv --ignore=.git --ignore=__pycache__ --ignore='*.pyc'` to prune `os.walk(".")` from descending into the bind-mounted host `.venv` (6,225 dirs / 23,755 files / 1,264 `.po`). The `.venv` basename match is verified by spec §2.1 (`is_ignored_path('.venv', ['.venv']) → True`).
2. Add `--locale ru --locale bs --locale en` (repeated `action="append"` form — **not** `--locale=ru,bs,en`, which Django treats as one nonexistent locale). Limits Phase-2 compile to the 3 project locales (belt-and-suspenders; does *not* prune the walk).
3. **Quote `'*.pyc'`** (single quotes) — spec §10 risk-row #4 mitigation: prevents the shell from attempting pathname expansion of `*.pyc` in the bash recipe. The resulting argv token is `--ignore=*.pyc` (identical semantics; strictly safer). POSIX-compatible (`#!/bin/bash`).
4. Preserve `2>/dev/null` and the `|| echo "WARNING..."` non-fatal fallback (R5).

**Acceptance criteria / inline verification:**
- `compile_messages()` invocation contains `--ignore=.venv` and `--locale ru --locale bs --locale en`.
- `2>/dev/null ... || echo "WARNING"` fallback intact.
- Running the dev/test container no longer hangs at "Compiling translations...".

**blocked_by:** none
**Risk note:** `--ignore=.venv` cannot prune a legitimate project locale (no project locale dir is named `.venv` — A2 verified). In production the image has no `/app/.venv`, so the flag is a harmless no-op (R3).

---

### T2 — Add `--ignore` + `--locale` flags to `Makefile` `compilemessages` target

- **Priority:** High (R6: `make compilemessages` from dev must not hang).
- **Risk:** Very Low — developer-invoked target; fails non-fatally via the container's `entrypoint.sh` fallback.
- **Files:** `Makefile`
- **Semantic anchor:** `compilemessages` Make target (the `docker compose ... run --rm web uv run python ... compilemessages` recipe).

**Context (why T2 is required, not just "consistency"):** The dev `web` service has no `entrypoint:` override, so it inherits the Dockerfile `ENTRYPOINT ["/app/entrypoint.sh"]`. `make compilemessages` passes a **CMD override** (`uv run python ... compilemessages`). At startup: ENTRYPOINT runs `compile_messages()` (T1-fixed), then `exec "$@"` runs the CMD `compilemessages` **again** — a second `os.walk(".")` with no `--ignore` unless T2 adds it. Both invocations must carry `--ignore` (spec §8.2).

**Changes:**
1. Append `--ignore=.venv --ignore=.git --ignore=__pycache__ --ignore='*.pyc' --locale ru --locale bs --locale en` to the `compilemessages` recipe (Makefile line-continuation `\`), matching T1's flag set verbatim for consistency.
2. Use the same repeated `--locale` form (not comma-joined).

**Acceptance criteria / inline verification:**
- `make compilemessages` completes in <5 s (use the same `COMPOSE_FILES` dev profile).
- No `FileNotFoundError`/walk explosion in output.

**blocked_by:** [T1]  *(soft: review the flag set once in T1, then replicate in T2)*
**Risk note:** The `'*.pyc'` single-quote is shell-consumed and yields argv `--ignore=*.pyc`; safe under the recipe's `/bin/sh`.

---

### V1 — Verification Gate (Definition of Done)

- **Priority:** Critical · **Risk:** Low (verification only, no prod-code change).
- **blocked_by:** [T1, T2]
- **Purpose:** Prove the behavioral DoD from spec §9 (the fix's value is the hang elimination, which must be demonstrated, not assumed). No existing automated test asserts timing or `.venv`-exclusion, so this gate is the acceptance proof.

**Checks (run sequentially after T1+T2):**

| Check | Command | Pass criterion |
|---|---|---|
| V1 startup timing | `make test 2>&1 \| ts '%.s'` (or `time`-equivalent) | Gap between container start and first post-"Compiling translations..." log line ≤ 5 s (was 25–60+ s) |
| V2 only project locales compiled | dev container: `/opt/venv/bin/python /app/src/backend/manage.py compilemessages --ignore=.venv --ignore=.git --ignore=__pycache__ --ignore='*.pyc' --locale ru --locale bs --locale en --verbosity 2` | Only `ru`, `en`, `bs` listed; 3 `.po` compiled; 0 third-party |
| V4 `.venv` not walked | same `--verbosity 2` run | No `/app/.venv/` paths appear in walk output |
| V5 `make compilemessages` | `make compilemessages` from a terminal | Completes in <5 s |
| Regression (`.mo` contract) | `make test` (fast gate) | `test_i18n_pipeline.py::test_mo_files_exist` green (3 `.mo` files present under `src/backend/locale/`) |
| V6 non-fatal fallback | (reasoning — no execution) | `|| echo "WARNING: compilemessages failed..."` path preserved; a broken `.po` cannot hang or crash startup |

**Production-affected reasoning (V3, no run required):** Production `runtime` image has no `/app/.venv` (build excludes it via `.dockerignore:2`; container venv is `/opt/venv`). `--ignore=.venv` is a no-op in prod; the builder-stage `compilemessages` (`Dockerfile` builder stage) runs against a clean context. ⇒ R3 holds by construction.

**Acceptance:** all rows pass. T3 (optional hardening) may proceed only after V1 passes.

---

### T3 — (OPTIONAL) Shadow bind-mounted `.venv` with a named volume in dev/test compose

- **Priority:** Low · **Risk:** Low · **Domain:** Docker compose (additive only).
- **blocked_by:** [V1]  *(canary: harden only after the core fix is proven)*
- **Status:** Optional. T1+T2 fully resolve the hang (spec §7: "T1 + T2 alone fully resolve the hang"). T3 hardens against *other* CWD-scanning tools (future `find`, conftest collection, etc.).

**Files:** `docker-compose.dev.override.yml`, `docker-compose.test.yml`

**Semantic anchors:** `web` / `bot` volumes (dev); `test` service volumes (test); top-level `volumes:` block.

**Changes:**
1. In `docker-compose.dev.override.yml`: append `- web_venv:/app/.venv` to the `web` and `bot` services' existing `volumes:` lists (placed *after* the `.:/app` bind mount so the named volume shadows it). Declare `web_venv:` under the top-level `volumes:`.
2. In `docker-compose.test.yml`: append `- web_venv:/app/.venv` to the `test` service's `volumes:`; declare `web_venv:` under the top-level `volumes:`.
3. **Do NOT touch production `docker-compose.yml`** (it does not bind-mount `.:/app`).

**Why safe:** The container's Python env is `/opt/venv` (`Dockerfile:129`), not `/app/.venv`. The `/app/.venv` path only exists because the *dev/test bind mount* copies the host `.venv` into the container. Shadowing it with an empty named volume removes that leak without affecting any runtime import path.

**Acceptance:** `make test` + `make up` (dev) start cleanly; no service depends on `/app/.venv` at runtime.

---

## 5. Execution Order (phased)

### Phase 1 — Core fix (parallel)
```
T1 (entrypoint.sh compile_messages) ──┐
T2 (Makefile compilemessages target) ──┤
                                       ▼
                                      V1 (verification gate)
```
- T1 and T2 are independent-file, same-pattern edits → execute in parallel; review together for flag-set consistency.
- V1 gates both before any optional work.

### Phase 2 — Optional hardening (post-canary)
```
T3 (named-volume shadow, dev + test compose)
```
- Only after V1 passes. Independently reviewable; no prod impact.

**Critical path:** T1 ‖ T2 → V1 ≈ minutes (single small shell + Makefile edit, then one `make test` cycle to confirm). No migrations, no schema, no public API change, no test-infrastructure change beyond confirming the existing `test_mo_files_exist` guard stays green.

---

## 6. Appendix A — Files Referenced (authoritative, on-disk)

| Artifact | Path | Role |
|---|---|---|
| ENTRYPOINT script | `docker/entrypoint.sh` | `compile_messages()` fn + ENTRYPOINT guard (T1) |
| Makefile target | `Makefile` | `compilemessages` recipe (T2) |
| Test compose | `docker-compose.test.yml` | bind mount `.:/app`; `test` service CMD override |
| Dev compose override | `docker-compose.dev.override.yml` | bind mounts for `web`/`bot` |
| Dockerfile | `docker/Dockerfile` | `ENTRYPOINT` (builder/runtime/test-runtime); builder `compilemessages`; no `/app/.venv` in image |
| `.dockerignore` | `.dockerignore:2` | `.venv` excludes build context |
| `.gitignore` | `.gitignore:55` | `*.mo` ignored (Q5) |
| Project locales | `src/backend/config/settings/base.py` | `LOCALE_PATHS`; `LANGUAGES = ru/bs/en` |
| Regression guard | `src/backend/apps/ads/tests/test_i18n_pipeline.py` | `test_mo_files_exist` asserts 3 `.mo` files |
| Source spec | `.ai/problems/14_compilemessages-docker-hang_spec.md` | R1–R6, §8 implementation, §9 DoD |

---

## 7. Appendix B — Risk Summary

| Risk | Likelihood | Impact | Mitigation | Task |
|---|---|---|---|---|
| `--ignore=.venv` prunes a real project locale dir named `.venv` | Very Low | Low | No project locale named `.venv` (locales under `src/backend/locale/{ru,en,bs}`) — verified (A2) | T1 |
| `--locale ru/bs/en` omits a needed locale | Low | Medium | `LANGUAGES`/`LOCALE_PATHS` cover exactly these 3 — verified | T1, T2 |
| `--ignore='*.pyc'` glob expands in shell | Low | Low | Single-quote the token; whole-word pattern `--ignore=*.pyc` cannot match a filename | T1, T2 |
| T2 double-invocation (ENTRYPOINT + CMD) missed | — | — | Captured as T2 rationale; both invocations fixed | T2 |
| Forgotten `--ignore` on future `compilemessages` calls | Medium | Medium | Document flag set in this plan + `AGENTS.md` i18n note; T3 (volume shadow) provides structural defense-in-depth | T1, T2, T3 |
| Startup regression (container fails to start) | Very Low | High | `|| echo WARNING` fallback preserved; `set -e` respected via guarded list | T1, V1 |

---

## 8. Appendix C — Recommended Commands (from spec §9)

```bash
# Smoke test (dev) — should be sub-second, not hang:
docker compose --project-name mko-bazuna-dev up -d db && \
  docker compose --project-name mko-bazuna-dev run --rm web \
    /opt/venv/bin/python /app/src/backend/manage.py compilemessages \
    --ignore=.venv --ignore=.git --ignore=__pycache__ --ignore='*.pyc' \
    --locale ru --locale bs --locale en --verbosity 2

# Full verification:
make test            # fast gate; "Compiling translations..." completes instantly; test_mo_files_exist green
make compilemessages # <5 s
```
