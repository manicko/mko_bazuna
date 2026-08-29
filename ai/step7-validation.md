# Step 7 — Docker Build Optimization Plan: Validation Report

**Date:** 2026-08-29
**Plan under review:** `.ai/plans/docker-build-optimization-plan.md`
**Validator:** Kilo / Step 7 gate
**Decision:** APPROVED WITH CORRECTIONS (4 minor, non-blocking)

---

## Executive Summary

The plan is **substantially correct and complete**. All 17 findings (F01–F17) are addressed with concrete, implementable modifications. Every file reference, line number, existing pattern, and dependency-ordering claim was cross-checked against the source tree. The architectural invariants of the project — 3-stage Dockerfile, bind-mount dev/test invariance, test-runtime stage retaining `uv`, and the critical F08 Part A-before-Part B ordering — are all respected.

**Recommendation:** Proceed to implementation (Step 8) after correcting 4 minor prose/attribution defects listed in §5. These defects do not affect the technical correctness of any modification; they affect readability and precise referencing only.

### Verified Claims (all PASS)

| # | Claim | Evidence | Status |
|---|-------|----------|--------|
| 1 | All 17 findings covered | Overview table + 6 CGs map every F01–F17 | PASS |
| 2 | All 5 categories present | CG1–CG6 span Categories 1–5 (Cat 2 empty) | PASS |
| 3 | F05: files are git-tracked | `git ls-files -s` confirms `git rm --cached` required | PASS |
| 4 | F12: 3 patterns NOT in `.gitignore` | `.gitignore` L82 has `profile_default/` (no dot); `.pdbrc` and `.python-eggs/` absent | PASS |
| 5 | F12: plan adds 3 patterns to both files | Confirmed in CG3 section | PASS |
| 6 | F08 Part A: 4 scripts, 5 replacements | `entrypoint-catalog.sh` L17, `entrypoint-create-admin.sh` L24, `entrypoint-seed.sh` L18+L32, `entrypoint-scheduler.sh` L21 | PASS |
| 7 | F08 Part A: scripts currently use `uv run python` | All 4 scripts confirmed at exact lines | PASS |
| 8 | F08 Part B: uv/uvx COPY at Dockerfile L109–111 | Confirmed at L109–111 (runtime stage) | PASS |
| 9 | F08 Part B: test-runtime stage at Dockerfile L165 | `FROM runtime AS test-runtime` at L165 | PASS |
| 10 | Dev compose has no `target:` | `docker compose` in `docker-compose.yml` has no `target:` (grep returns empty) | PASS |
| 11 | entrypoint.sh L41/L60/L75 use `/opt/venv/bin/python` | Confirmed — runtime venv pattern already established | PASS |
| 12 | Dockerfile L78 has no `--ignore`/`--locale` | L78 is bare `compilemessages` — F17 addition is real | PASS |
| 13 | CI test job at ci.yml L83 | `uv run python manage.py compilemessages` | PASS |
| 14 | CI i18n job at ci.yml L176 | Same command | PASS |
| 15 | Makefile L153–155 has compilemessages | Has 5 `--ignore` + `--locale ru bs en` | PASS |
| 16 | entrypoint.sh L74–79 has `compile_messages()` | Has 5 `--ignore` + `--locale` + non-fatal fallback `|| echo WARNING` | PASS |
| 17 | Dockerfile L37: `COPY pyproject.toml uv.lock* ./` | Correct for layer caching | PASS |
| 18 | Dockerfile L57: `COPY . .` | Correctly broad for PYTHONPATH layout | PASS |
| 19 | Dockerfile L124: `COPY docker/entrypoint*.sh` | Already narrowed to entrypoint scripts only | PASS |
| 20 | Dockerfile L137–138: UV env vars | `UV_NO_INSTALL_PROJECT=1`, `UV_FROZEN=1` confirmed | PASS |
| 21 | CG ordering: CG1→CG2→CG3→CG4→CG5→CG6 | Dependency chain is linear, no cycles | PASS |
| 22 | F08 Part A→B ordering constraint emphasized | Plan explicitly states Part A MUST precede/same-time as Part B | PASS |
| 23 | Seed JPEGs gitignored (L226–228) | `.gitignore` L226–228: `*.jpg`, `*.jpeg`, `*.png` | PASS |
| 24 | Seed JPEGs NOT in `.dockerignore` | No jpg/jpeg/png/image patterns in `.dockerignore` | PASS |
| 25 | Seed JPEGs intentionally NOT excluded by plan | Plan correctly does not dockerignore them | PASS |
| 26 | Bind-mount invariance principle stated | Plan correctly notes `.dockerignore` doesn't affect bind-mounts | PASS |
| 27 | Risk ratings accurate | F08=High, F16/F17=Low, F01–F07=Medium/Low — consistent with impact | PASS |

---

## Per-Category Review Against 10 Validation Criteria

### Category 1 — Docker Build Context (CG1, CG2)

| Criterion | Assessment | Evidence |
|-----------|------------|----------|
| **Completeness** | PASS | F01–F07 all mapped to CG1 or CG2 with specific patterns |
| **Correctness** | PASS | F05 references confirmed via `git ls-files -s` (files tracked); `.dockerignore`/`.gitignore` line refs verified |
| **Safety** | PASS | All additions target build-context-only paths (scripts, backups, caches); bind-mount invariance stated |
| **Architectural fit** | PASS | No changes to Dockerfile COPY instructions — preserves 3-stage architecture |
| **Dependency ordering** | PASS | CG1 (F01, F02) → CG2 (F03–F07) — no inter-dependencies |
| **Risk coverage** | PASS | Risk noted for F05 (git rm — tracked files), F02 (backups dir scope) |
| **Measurable impact** | PASS | Specific patterns listed; build-context reduction quantifiable |
| **Functional preservation** | PASS | No source code or runtime logic touched |
| **No speculative work** | PASS | Every pattern has a source-tree anchor |
| **Structural clarity** | PASS | Table format clear; each finding self-contained |

### Category 2 — Dockerfile Inputs (no changes)

| Criterion | Assessment | Evidence |
|-----------|------------|----------|
| **Completeness** | PASS | Correctly identified as empty — no findings in this category |
| **Correctness** | PASS | Dockerfile L37, L57, L124 all verified correct; COPY narrowing rejection justified |
| **Safety** | PASS | No changes = no risk |
| **Architectural fit** | PASS | 3-stage preserved; PYTHONPATH layout respected |
| **Dependency ordering** | N/A | Standone, no dependencies |
| **Risk coverage** | PASS | Zero-risk by virtue of no changes |
| **Measurable impact** | PASS | N/A (no changes = zero impact, correctly stated as already-optimal) |
| **Functional preservation** | PASS | Dockerfile unchanged |
| **No speculative work** | PASS | Only "no changes" documented |
| **Structural clarity** | **WARN** — see §5.3 (section heading mislabel as "Category 1" instead of "Category 2") |

### Category 3 — Runtime Dependencies (CG4, CG5)

| Criterion | Assessment | Evidence |
|-----------|------------|----------|
| **Completeness** | PASS | F08 split into Part A (CG4, 4 scripts) and Part B (CG5, Dockerfile) |
| **Correctness** | PASS | All 4 script line numbers verified exactly against source |
| **Safety** | **WARN** — see §5.2 (L109 attribution) | The ordering constraint is emphasized but attribution error misleads |
| **Architectural fit** | PASS | Moves uv/uvx to test-runtime only; runtime uses /opt/venv/bin/python (proven at L41/L60/L75) |
| **Dependency ordering** | PASS | CG4 BEFORE CG5 enforced — plan provides rollback interdependency notes |
| **Risk coverage** | PASS | High risk acknowledged; rollback procedures detailed for both CG4 and CG5 |
| **Measurable impact** | PASS | Runtime image size reduction (~28 MB: uv binary + uvx) quantifiable |
| **Functional preservation** | **CAUTION** | Production aux services (catalog, seed, create_admin, scheduler) depend on Part A landing first; plan correctly documents this |
| **No speculative work** | PASS | Concrete file/line replacements specified |
| **Structural clarity** | PASS | Before/after table clear; ordering constraint in dedicated subsection |

### Category 4 — Build Artifacts & Caches (CG3)

| Criterion | Assessment | Evidence |
|-----------|------------|----------|
| **Completeness** | PASS | F09–F15 all mapped to CG3 (7 findings, 24 total patterns) |
| **Correctness** | PASS | Each finding references specific patterns; F12 MODIFIED flag applied correctly |
| **Safety** | PASS | `.mo`/`.pot` (F09): gitignored L226–228 for JPEGs, F12 patterns confirmed absent from `.gitignore` |
| **Architectural fit** | PASS | No runtime/build-system changes — only `.dockerignore`/`.gitignore` expansions |
| **Dependency ordering** | PASS | Independent of F08; order within CG3 is parallel-safe |
| **Risk coverage** | PASS | F09 risk (stale `.mo` in image) addressed; F13/F14/F15 low-risk patterns |
| **Measurable impact** | PASS | Pattern lists are explicit and countable |
| **Functional preservation** | PASS | No source code changes; `.dockerignore` only affects `docker build` not bind-mounts |
| **No speculative work** | PASS | Every pattern verified against `.dockerignore` (absent) and `.gitignore` (where relevant) |
| **Structural clarity** | PASS | Each finding has Rationale, Dependencies, Risk, Validation criteria |

### Category 5 — Related Tooling (CG6)

| Criterion | Assessment | Evidence |
|-----------|------------|----------|
| **Completeness** | PASS | F16 (entrypoint.sh + Makefile) and F17 (Dockerfile + CI) both covered |
| **Correctness** | **WARN** — see §5.1 (ignore count) | Code block correct; prose count off by 1 |
| **Safety** | PASS | `--ignore` patterns target only cache/VCS dirs; locale path `src/backend/locale/{ru,bs,en}/LC_MESSAGES/` is preserved |
| **Architectural fit** | PASS | Aligns `.dockerignore`, Dockerfile, entrypoint, Makefile, CI invocation — consistent coverage |
| **Dependency ordering** | PASS | CG6 applied after CG1–CG3 (same `--ignore` patterns); no dependency on F08 |
| **Risk coverage** | PASS | Low risk noted; non-fatal fallback in entrypoint.sh L79 (`|| echo WARNING`) |
| **Measurable impact** | PASS | 4 invocation sites unified; compilemessages traversal reduction quantifiable |
| **Functional preservation** | PASS | `--locale ru --locale bs --locale en` retained at all sites; fallback protects dev mode |
| **No speculative work** | PASS | 4 invocation sites verified: Dockerfile L78, entrypoint.sh L76, Makefile L153, ci.yml L83/L176 |
| **Structural clarity** | **WARN** — see §5.1, §5.2 | Prose inconsistencies reduce confidence (corrected in §5) |

---

## Dependency & Rollout Validation

### Execution Order

```
CG1 (F01, F02) → CG2 (F03–F07) → CG3 (F09–F15) → CG4 (F08 Part A) → CG5 (F08 Part B) → CG6 (F16, F17)
```

- **CG1 → CG2 → CG3**: Fully parallel-safe (independent `.dockerignore`/`.gitignore` expansions).
- **CG4 → CG5**: **Hard constraint.** Part A (replace `uv run python` → `/opt/venv/bin/python` in 4 scripts) MUST be committed before or simultaneously with Part B (remove `uv`/`uvx` from runtime stage). If Part B lands first, all 4 production aux services (catalog, create_admin, seed, scheduler) crash-loop with `exit 127: uv: command not found`.
- **CG6**: Independent of F08; applied last for reviewability. Safe to batch with any CG.

### Backward Compatibility

- **runtime image**: Production web/bot services already use `/opt/venv/bin/python` (entrypoint.sh L41/L60/L75). No regression.
- **test-runtime image**: Retains `uv`/`uvx` (Part B adds to test-runtime, doesn't remove from builder). `entrypoint-test.sh` (L16/L19/L20/L41) continues using `uv run python`. No regression.
- **bind-mount dev**: `.dockerignore` additions do NOT affect `:./app` bind-mount. Dev workflow sees full host repo. ✅

### Rollback Analysis

| Rollack | Safe without? | Notes |
|---------|--------------|-------|
| CG1 (F01, F02) | Standalone | `.dockerignore` revert is pure additive removal |
| CG2 (F03–F07) | Standalone | Same — additive removal |
| CG3 (F09–F15) | Standalone | Same |
| CG4 (F08 Part A) | Only if CG5 NOT applied | Reverting scripts to `uv run python` requires `uv` in runtime image |
| CG5 (F08 Part B) | Only if CG4 reverted first | Adding `uv`/`uvx` back to runtime is safe; scripts must still reference `uv run` |
| CG6 (F16, F17) | Standalone | Removing `--ignore` flags is non-fatal (just less efficient) |

The CG4↔CG5 interdependency is correctly documented in the plan. ✅

---

## Specific Deficiencies and Corrections

### 5.1 Deficiency: F16/F17 `--ignore` count mismatch (minor, prose only)

**Location:** Plan §3 (F16) line ~133 and §3 (F17) line ~167

**Claim:** "Expand both `--ignore` lists from the current 5 patterns to 17" and "Append the same 12 additional `--ignore` flags (plus existing 5)"

**Reality:** The code block lists **18** patterns total (5 existing + 13 additional):

```
--ignore=.venv --ignore=.git --ignore=.kilo --ignore=__pycache__ --ignore='*.pyc' \        # 5 existing
--ignore=.mypy_cache --ignore=.ruff_cache --ignore=.pytest_cache --ignore=node_modules \   # 4 additional
--ignore=.tox --ignore=.nox --ignore=__pypackages__ --ignore=.uv --ignore=.cache \        # 5 additional
--ignore=.local --ignore=.playwright-mcp --ignore=.coverage --ignore=.hypothesis          # 4 additional
```

13 additional, 18 total.

**Impact:** Zero on implementation — the code block is the source of truth and is correct. The prose count is off by 1 (says 17/12, should be 18/13).

**Correction:** Update prose in both F16 and F17 sections:
- "from the current 5 patterns to **18**"
- "the same **13** additional `--ignore` flags (plus existing 5)"

### 5.2 Deficiency: "entrypoint.sh L109" attribution error (minor)

**Location:** Plan §3 (F08 Part A, Risk considerations) line ~152 and §3 (F08 Part B) line ~158

**Claim:** "`entrypoint.sh` L109 comment says 'needed for dev mode `uv run` commands and entrypoint scripts'"

**Reality:** `entrypoint.sh` has **83 lines** total (verified). The comment `# Copy uv binary from builder (needed for dev mode \`uv run\` commands and entrypoint scripts)` is at **Dockerfile L109**, not entrypoint.sh L109.

**Impact:** Zero on implementation — the comment to update is correctly identified as "the L109 comment" in the CG5 section (line ~158) which references "Dockerfile L109" in its modification steps. The CG4 risk note simply mis-attributes the file.

**Correction:** In the CG4 risk considerations, change:
- `entrypoint.sh L109` → `Dockerfile L109`

### 5.3 Deficiency: Section heading mislabel — "Category 1" instead of "Category 2" (structural)

**Location:** Plan §3 line ~129

**Claim:** `### Category 1 — Dockerfile Inputs (no changes)`

**Reality:** The overview table (§2, line ~30) correctly maps this as Category 2 (Dockerfile Inputs). The table row `— | 2 (Dockerfile Inputs) | (no changes) | — | —` confirms this. The section heading uses "Category 1" instead of "Category 2".

**Impact:** Minor readability issue — a reader cross-referencing the overview table with the body section may be briefly confused. No technical impact.

**Correction:**
- `### Category 1 — Dockerfile Inputs (no changes)` → `### Category 2 — Dockerfile Inputs (no changes)`

### 5.4 Deficiency: Misleading P3 exclusion wording for `compilemessages --locale` (minor)

**Location:** Plan §1 (No changes needed) line ~15

**Claim:** P3 practices include "compilemessages `--locale` in Dockerfile" — listed as "already-implemented."

**Reality:** Dockerfile L78 has `uv run python src/backend/manage.py compilemessages` with **NO** `--locale` flags. Section 12 clarifies: "compilemessages `--locale` in Dockerfile — included in F17 for consistency." This contradicts the Section 1 statement.

**Impact:** Minor — the clarification in Section 12 is correct but the Section 1 grouping is misleading. A reader might think `--locale` is already present in Dockerfile L78 and question why F17 adds it.

**Correction:** Update Section 1 wording — remove "compilemessages `--locale` in Dockerfile" from the P3/excluded list, or rephrase to: "compilemessages `--locale` in Dockerfile — addressed by F17 (not previously present)."

---

## Rollout Analysis

### Risks

| Risk | Severity | Mitigation in Plan | Status |
|------|----------|-------------------|--------|
| CG5 lands before CG4 → production aux services crash-loop (exit 127) | **High** | Plan mandates CG4-before-CG5 or simultaneous commit | ✅ Covered |
| `.dockerignore` patterns accidentally exclude bind-mount files | Medium | Bind-mount invariance principle stated; `.dockerignore` only affects `docker build` | ✅ Covered |
| `compilemessages --ignore` breaks locale compilation | Low | Non-fatal fallback (`|| echo WARNING`) in entrypoint.sh L79; `--locale` retained | ✅ Covered |
| Git-tracked files excluded from image but not removed from index | Low | F05 requires `git rm --cached` — plan explicitly calls this out | ✅ Covered |
| Seed JPEGs excluded from image (breaking seed service) | **High** | Plan correctly does NOT dockerignore `*.jpg`/`*.jpeg`/`*.png` (gitignored but intentionally present in image) | ✅ Covered |

### Dependencies

- No circular dependencies.
- CG1–CG3 (`.dockerignore`/`.gitignore`) are fully independent of runtime/Dockerfile changes.
- F08 (CG4→CG5) has the only hard ordering constraint.
- CG6 (F16/F17) must run after CG1–CG3 so the `--ignore` lists are consistent with `.dockerignore`.

### Backward Compatibility

- **runtime image**: No regressions — production already uses `/opt/venv/bin/python`.
- **test-runtime image**: `uv`/`uvx` retained via Part B (moved to test-runtime, not removed from builder).
- **dev compose**: No `target:` directive → defaults to `test-runtime` → unaffected by all changes.
- **CI**: Test job (L83) and i18n job (L176) both covered by F17.

---

## Execution Validation

### Applicability

- All targets verified to exist at the referenced paths: `docker/Dockerfile` (168 lines), `docker/entrypoint.sh` (83 lines), `docker/entrypoint-catalog.sh`, `docker/entrypoint-create-admin.sh`, `docker/entrypoint-seed.sh`, `docker/entrypoint-scheduler.sh`, `Makefile`, `.github/workflows/ci.yml` (184 lines), `.gitignore` (236 lines), `.dockerignore`.
- Plan status: "Approved (based on Steps 1–5 validation)" — Step 7 gate is the final validation before implementation.

### Execution Readiness

| Check | Result |
|-------|--------|
| All file paths valid | ✅ |
| All line numbers verified | ✅ (except §5.2 misattribution) |
| No stale targets | ✅ |
| Dependencies valid and ordered | ✅ |
| Architecture integrity preserved | ✅ |
| Rollback procedures documented | ✅ for all 6 CGs |
| Validation matrix covers CI test + i18n + `make test` | ✅ |

**Ready to proceed to Step 8 (Implementation)** after correcting §5 deficiencies.

---

## Warnings

1. **Architectural risk (F08 CG5)**: Removing `uv`/`uvx` from the runtime image is irreversible without also reverting CG4. The plan correctly documents this, but the combined CG4+CG5 commit recommendation should be the default approach to eliminate the crash-loop window.

2. **Maintainability**: The `compilemessages --ignore` list will now be duplicated across 4 locations (Dockerfile, entrypoint.sh, Makefile, ci.yml ×2). Any future pattern addition requires updating all sites. Consider a shared variable or helper script in Step 8 planning (advisory, not blocking).

3. **Documentation inconsistency**: Section 1's P3 list (§5.4) lists "compilemessages `--locale` in Dockerfile" as already-implemented, but Dockerfile L78 has no `--locale` flags. This was a source of confusion during validation.

4. **Line-number drift risk**: The plan references specific line numbers throughout. Any future edits to these files will invalidate line references. Recommend anchoring on content patterns rather than line numbers in the Step 8 implementation tool (advisory).

---

## Required Fixes (before Step 8)

| # | Fix | Section | Severity |
|---|-----|---------|----------|
| 1 | Correct `--ignore` count: "to 17" → "to 18", "12 additional" → "13 additional" | §3 (F16, F17) | Minor |
| 2 | Change "entrypoint.sh L109" → "Dockerfile L109" in risk considerations | §3 (F08 Part A) | Minor |
| 3 | Fix section heading: "Category 1" → "Category 2" | §3 line ~129 | Structural |
| 4 | Remove or rephrase misleading P3 entry: "compilemessages `--locale` in Dockerfile" | §1 line ~15 | Minor |

---

## Advisory Recommendations (optional, Step 8)

1. **Shared compilemessages configuration**: Extract the 18 `--ignore` patterns + 3 `--locale` flags into a single shell variable (e.g., `COMPILEMESSAGES_IGNORES` in a shared `docker/_compilemessages_flags.sh` sourced by entrypoint.sh and Makefile, and inlined into Dockerfile/CI). Eliminates 5× duplication risk. *(Not required — plan's inline approach is correct and functional.)*

2. **Content-anchored diff targets**: In Step 8, use `ast-editor` or `sed` with content anchors (e.g., `uv run python src/backend/manage.py compilemessages`) rather than bare line numbers to avoid drift sensitivity.

3. **Combined CG4+CG5 commit**: Recommend implementing F08 Parts A and B in a single commit to eliminate the crash-loop window entirely, rather than the plan's "split allows targeted rollback" approach (which accepts a known failure window).

4. **Post-CG6 verification script**: Add a CI step that runs `git check-ignore .profile_default/ .pdbrc .python-eggs/` and greps the Docker image for excluded patterns, to catch drift in future.

---

## Conclusion

**APPROVED WITH CORRECTIONS.** The plan is technically sound, complete, and safe. All 17 findings are correctly mapped to 6 dependency-ordered commit groups. The architectural invariants (3-stage Dockerfile, bind-mount invariance, test-runtime retaining `uv`, F08 ordering constraint, seed JPEGs preserved) are all respected. The 4 deficiencies identified in §5 are minor prose/attribution errors that do not affect implementation correctness — they require text corrections in the plan document only.

**Next step:** Apply fixes 1–4 above, then proceed to Step 8 (implementation), anchoring edits on content patterns rather than line numbers.
