# 99 — Audit Findings Validation

> Audit phase. LLM-auditor instruction. Architecture-agnostic: described via
> ARCHITECTURAL LAYERS, ZONES OF RESPONSIBILITY, KEY RISKS, GOALS. NOT tied to
> specific files, modules, or functions. Must stay valid if the architecture
> changes.
>
> **Output mode:** `problems-only` — report only findings; do not narrate a clean
> bill of health. Emits a rolling anchored-summary checkpoint at each stage of the
> 4-step audit pipeline.

## 1. Goal

Validate each audit finding for technical correctness, current applicability,
architectural fit, and operational value; produce a self-contained validated
report per phase. This is the *Researcher verification* stage of the realized
4-step pipeline (Auditor analysis → Researcher verification → Token-safe
docs-specialist edits → Final consistency audit).

## 2. System Under Audit (layers & zones)

**Layers:** auditor findings → validation store → validated reports → final
consistency audit.

**Zones of responsibility:** findings ingestion (R1), cross-finding analysis (R2),
per-finding validation (R3), rollout-safety assessment (R4), report assembly,
rolling-checkpoint emission.

**Key risks:** stale findings approved as valid; conflicting evidence left
unresolved; unsafe rollout ordering; reports that depend on source files (violates
Phase 3 token-safety).

## 3. Prerequisites

- Docker + PostgreSQL test DB (host port 5433) with `--reuse-db` caching.
- Completed auditor phase handbooks (`.kilo/commands/audit/phases/NN-*.md`).
- Validation store path — per-phase copies named
  `{phase_number}-{phase_name}-validated.md`.
- Project specification, README, Pydantic models / `StrEnum` values,
  configuration templates (for the dead-code mandatory cross-reference, §5).
- Linter + type-checker (`ruff`, `basedpyright`) available in the test image.

## 4. Runtime Verification (mandatory)

A rolling anchored-summary checkpoint is emitted after each of R1–R4.

**R1 — Copy Source Findings**
Copy the auditor's per-phase findings file as the base for the validated report
in the validation store, named per phase (e.g.
`{phase_number}-{phase_name}-validated.md`). All edits are applied inline to this
copy. The final file must be fully self-contained — the reader should never need
to consult the original.

Checkpoint 1 fields: stage = *Auditor analysis*, findings-in-scope count,
evidence anchor, blockers.

**R2 — Cross-Finding Analysis**
Scan findings across all phases:

- **Same root cause** → mark as merge candidate. Note which finding IDs overlap
  and which absorbs which.
- **Conflicting evidence** (e.g. one phase says "all commands work", another
  says "run command crashes") → flag as cross-phase conflict. CRITICAL.
- **Dependency chains** → note if fixing one finding depends on another.

Checkpoint 2 fields: stage = *Researcher verification*, cross-phase conflict
count, merge-candidate count.

**R3 — Validate Each Finding**
For every finding, verify:

1. **Technical correctness** — is the problem real? Check the actual code.
2. **Current applicability** — is the codebase still in this state?
3. **Architectural fit** — does the recommendation align with project patterns?
4. **Operational value** — is the fix worth the effort at this project scale?

Checkpoint 3 fields: stage = *Per-finding validation*, per-finding decision tally
(Validated / Reclassified / Merged / Rejected).

**R4 — Assess Rollout Safety**
Check: circular dependencies, hidden dependency chains, unsafe rollout ordering,
fragile insertion points. Add any detected issues as new findings.

## 5. Audit Dimensions (checks + evidence)

### Type-Specific Rules

**[SPEC-DEVIATION]**
- Determine: code should change, or docs should change?
- If code is better than docs → reclassify as `[DOC-UPDATE]`.
- If docs are better than code → keep as spec deviation.

**[BEST-PRACTICE]**
- Reject if overengineered or adds complexity without clear maintenance benefit.
- Reject if ROI is negative for project scale.
- **Splitting large files / smaller functions and modules is high ROI** — shorter
  code units are easier to edit, review, and maintain with lower risk of
  corruption. Do not reject modularization findings as "overengineering" unless
  the split introduces unnecessary indirection or abstraction.

**[DOC-UPDATE]**
- Verify the proposed doc change accurately reflects code reality.

### Dead-Code Findings — mandatory spec cross-reference

1. Check the project specification document for the feature.
2. Check the project README for the feature.
3. Check Pydantic models / `StrEnum` values.
4. Check configuration templates.

If the spec, models, or config reference the component → **reject the "dead code"
label** and reclassify as `[SPEC-DEVIATION]` (missing integration, not dead code).

### Rejection Criteria

Reject findings that are: already implemented, stale, duplicates, low ROI,
architecture-breaking, operationally unsafe, overly complex, or conflicting
with project direction.

**Every rejection must include a clear reason.**

## 6. Cross-Cutting (owned here, not duplicated)

This section is owned by Phase 99 and is not duplicated in any other phase.

- **Same root cause** → merge candidate (see §11 Reporting — Merged).
- **Conflicting evidence** between phases → cross-phase conflict (CRITICAL).
- **Dependency chains** → rollout-ordering constraint (see §4 R4 and §8).

## 7. Edge Cases

- **Conflict vs. complement** — a finding may conflict with one in another phase
  (escalate as `VAL-`) or legitimately complement it (retain both, cross-ref).
- **Merge where evidence is incomplete** — preserve original content for
  reference; add a `Validation Note` block (§11) listing merged IDs.
- **Findings that span multiple phases** — split or cross-reference; the
  absorbing finding carries the merged content.
- **Stale-but-similar** — a finding may be rejected as stale while a sibling
  finding (same root cause) is validated; record the relationship in
  §11 Merged Findings.

## 8. Severity Taxonomy

| Severity | Meaning | Checkpoint impact |
|----------|---------|-------------------|
| **Critical** | Cross-phase conflict; rollout-safety blocker | Must resolve before downstream stage proceeds |
| **High** | Stale/overbroad BEST-PRACTICE; rejected finding | Document in summary; blocks merge into report |
| **Medium** | Reclassified or merged finding | Note in checkpoint; proceed |
| **Low** | DOC-UPDATE candidate | Approve inline |

## 9. Recommended Sequence

The realized 4-step pipeline, with a rolling anchored-summary checkpoint emitted
at each stage:

```text
 ┌──────────────────────────────┐   CHKPT 1   ┌──────────────────────────────┐
 │ 1. Auditor analysis          │  ──────────▶  │ findings-in-scope +          │
 │    (phase handbooks)         │              │ evidence anchors captured    │
 └──────────────────────────────┘             └──────────────────────────────┘
          │  R1 copy                      │
          ▼                              ▼
 ┌──────────────────────────────┐   CHKPT 2   ┌──────────────────────────────┐
 │ 2. Researcher verification/   │  ──────────▶  │ cross-phase conflicts +       │
 │    refinement                 │              │ merge candidates tallied      │
 │    → .kilo/research/<NN>.md   │              │ per-finding decisions begun   │
 └──────────────────────────────┘             └──────────────────────────────┘
          │  R3 + R4 validate              │
          ▼                              ▼
 ┌──────────────────────────────┐   CHKPT 3   ┌──────────────────────────────┐
 │ 3. Token-safe docs-specialist│  ──────────▶  │ final per-finding decision    │
 │    in-place edits            │              │ tally (V / RC / M / R)        │
 │    (≤2 agents parallel;       │              │ reports self-contained        │
 │     NO source reads)          │              │ checkpoint closure            │
 └──────────────────────────────┘             └──────────────────────────────┘
          │  §11 Reporting                 │
          ▼                              ▼
 ┌──────────────────────────────┐   CHKPT 4   ┌──────────────────────────────┐
 │ 4. Final consistency audit   │  ──────────▶  │ pipeline integrity OK;        │
 │    (checkpoint closure)      │              │ all checkpoints closed        │
 └──────────────────────────────┘             └──────────────────────────────┘
```

Stage gates (no downstream stage starts until its entry checkpoint is green):

- **Stage 1 → 2:** Checkpoint 1 must confirm findings are copied and ingestible.
- **Stage 2 → 3:** The research file (`<NN>.md`) must contain verified evidence
  and concrete recommendations; docs-specialist reads **only** `99-*.md`
  handbooks + research files — **no source reads**.
- **Stage 3 → 4:** Inline edits applied; report is self-contained, no live
  source-file references in checklists.
- **Stage 4:** Final consistency audit closes all open checkpoints and emits
  Checkpoint 4 (closed).

## 10. Finding Prefix

Validation-level findings discovered *during* this phase use prefix
**`VAL-`** (e.g. `VAL-001` for a cross-phase conflict, `VAL-002` for a detected
rollout-safety issue). These represent issues with the audit inputs
themselves (conflict, merge, stale, unsafe rollout ordering) rather than
source-code defects, and are recorded at the end of the Findings section
(§11 — Reporting).

## 11. Reporting

Decisions are applied inline to the copied findings file:

| Action | How to apply |
|--------|-------------|
| **Validated** | Keep as-is. |
| **Reclassified** | Update the `Type` field. Add a `Validation Note` block below the heading. |
| **Merged** | Keep content for reference. Add a `Validation Note` block listing merged IDs and target location. |
| **Rejected** | Replace the finding block with: `### {ID}: ~~{title}~~ [REJECTED]` + `> **Rejection reason:** {explanation}` |
| **Cross-phase conflicts** | Add as new finding entries (`VAL-`) at the end of the Findings section. |
| **Rollout safety issues** | Add as new finding entries (`VAL-`) if detected. |

### Validation Note Format

Add directly after the `### {ID}:` heading for merged or reclassified findings:

```markdown
> **Validation Note:**
> - **Action:** {merged | reclassified}
> - **Detail:** {rationale}
> - **See also:** {other finding IDs or sections}
```

### Rolling Checkpoint Format

Each stage emits an anchored-summary checkpoint. Records stage, findings count,
key decisions, evidence anchor, and checkpoint status (open → closed).

```markdown
## Checkpoint N — {stage name}

- **Stage:** {Auditor analysis | Researcher verification | Per-finding validation | Final audit}
- **Findings in scope:** {count} (Validated {n}, Reclassified {n}, Merged {n}, Rejected {n})
- **Evidence anchor:** {self-contained file / line reference — no live source reads}
- **Dependencies / blockers:** {none | …}
- **Checkpoint status:** {open | closed}
```

### Validation Summary

Append at the end of the file:

```markdown
## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | N | — |
| Reclassified | N | ID1, ID2 |
| Merged | N | ID3 → ID4 |
| Rejected | N | ID5, ID6 |
| VAL- (cross-phase / rollout) | N | VAL-001, ... |

### Rejected Findings

| ID | Title | Reason |
|----|-------|--------|
| ID5 | ... | ... |

### Merged Findings

| Original ID | Merged Into | Rationale |
|-------------|-------------|----------|
| ID3 | ID4 (Phase XX) | ... |

### Reclassified Findings

| ID | Original Type | New Type | Rationale |
|----|---------------|----------|-----------|
| ID1 | BEST-PRACTICE | SPEC-DEVIATION | ... |
```

## Constraints

- DO NOT modify source code.
- DO NOT generate implementation code.
- DO NOT redesign architecture.
- ONLY validate safety, consistency, and applicability.
- Prefer conservative decisions. Prefer rejection over unsafe approval.
- Phase 3 (docs-specialist) edits are token-safe: **no source file reads**;
  only `99-*.md` handbooks and research files (`.kilo/research/99-*.md`) are
  read. ≤2 agents in parallel.
- No file renames.
- Every report must be self-contained — the reader never needs to consult the
  original auditor finding or any source file.
