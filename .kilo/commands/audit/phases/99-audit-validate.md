---
name: 99-validate
description: Validate audit findings and produce a self-contained validated report per phase
agent: validator
alwaysApply: false
---

# Audit Findings Validation

## Objective

Validate each audit finding for correctness, applicability, and architectural safety. Produce a self-contained validated report per phase.

## Process

### Step 1 — Copy Source Findings

Copy the auditor's per-phase findings file as the base for the validated report in the validation store, named per phase (e.g. `{phase_number}-{phase_name}-validated.md`).

All edits are applied inline to this copy. The final file must be fully self-contained — the reader should never need to consult the original.

### Step 2 — Cross-Finding Analysis

Scan findings across all phases:

- **Same root cause** → mark as merge candidate. Note which finding IDs overlap and which absorbs which.
- **Conflicting evidence** (e.g. one phase says "all commands work", another says "run command crashes") → flag as cross-phase conflict. This is CRITICAL.
- **Dependency chains** → note if fixing one finding depends on another.

### Step 3 — Validate Each Finding

For every finding, verify:

1. **Technical correctness** — is the problem real? Check the actual code.
2. **Current applicability** — is the codebase still in this state?
3. **Architectural fit** — does the recommendation align with project patterns?
4. **Operational value** — is the fix worth the effort at this project scale?

#### Type-Specific Rules

**[SPEC-DEVIATION]**
- Determine: code should change, or docs should change?
- If code is better than docs → reclassify as `[DOC-UPDATE]`.
- If docs are better than code → keep as spec deviation.

**[BEST-PRACTICE]**
- Reject if overengineered or adds complexity without clear maintenance benefit.
- Reject if ROI is negative for project scale.
- **Splitting large files/smaller functions and modules is high ROI** — shorter code units are easier to edit, review, and maintain with lower risk of corruption. Do not reject modularization findings as "overengineering" unless the split introduces unnecessary indirection or abstraction.

**[DOC-UPDATE]**
- Verify the proposed doc change accurately reflects code reality.

**"Dead code" findings — mandatory spec cross-reference:**
1. Check the project specification document for the feature.
2. Check the project README for the feature.
3. Check Pydantic models / `StrEnum` values.
4. Check configuration templates.

If the spec, models, or config reference the component → **reject the "dead code" label** and reclassify as `[SPEC-DEVIATION]` (missing integration, not dead code).

#### Rejection Criteria

Reject findings that are: already implemented, stale, duplicates, low ROI, architecture-breaking, operationally unsafe, overly complex, or conflicting with project direction.

**Every rejection must include a clear reason.**

### Step 4 — Assess Rollout Safety

Check: circular dependencies, hidden dependency chains, unsafe rollout ordering, fragile insertion points. Add any detected issues as new findings.

### Step 5 — Write Validated Report

Apply decisions inline to the copied findings file:

| Action | How to apply |
|--------|-------------|
| **Validated** | Keep as-is. |
| **Reclassified** | Update the `Type` field. Add a `Validation Note` block below the heading. |
| **Merged** | Keep content for reference. Add a `Validation Note` block listing merged IDs and target location. |
| **Rejected** | Replace the finding block with: `### {ID}: ~~{title}~~ [REJECTED]` + `> **Rejection reason:** {explanation}` |
| **Cross-phase conflicts** | Add as new finding entries at the end of the Findings section. |
| **Rollout safety issues** | Add as new finding entries if detected. |

#### Validation Note Format

Add directly after the `### {ID}:` heading for merged or reclassified findings:

```markdown
> **Validation Note:**
> - **Action:** {merged | reclassified}
> - **Detail:** {rationale}
> - **See also:** {other finding IDs or sections}
```

#### Validation Summary

Append at the end of the file:

```markdown
## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | N | — |
| Reclassified | N | ID1, ID2 |
| Merged | N | ID3 → ID4 |
| Rejected | N | ID5, ID6 |

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
