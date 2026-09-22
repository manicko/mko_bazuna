---
name: audit-phases-refinement
description: Refine existing audit phases to match the current architecture while preserving their original intent
agent: tech-lead
alwaysApply: false
---
# Task: Audit Phases Refinement
---

# Workflow
Do not argue on the workflow, just follow.

## Step 0. Phase Selection
**Tech Lead action (before launching agents):**
Ask the user which phases from `.kilo\commands\audit\phases` should be refined:
- specific phase numbers / names, or
- all existing phases.

Proceed only with the confirmed selection. Process phases **one by one**.

---

## Step 1. Execute phase loop

For each phase file in selected phases

### 1.1 Architecture & Phase Analysis
**Launch Agent:** `auditor`

For the current phase:
- Build a high-level understanding of the relevant parts of the current system architecture (structure, main components, interactions). Collect only top-level information.
- Analyse every existing block of the phase: purpose, scope, and focus.
- Evaluate how well the blocks match and cover the current architecture.
- Identify gaps, outdated content, duplicates, overlaps, and incorrectly split blocks.

Return a structured report containing:
1. High-level architecture context relevant to this phase.
2. Assessment of each existing block (fit / outdated / gap / overlap).
3. List of concrete problems to address.

**Important:** Never change any code or existing audit phase files.

---

### 1.2. Research & Recommendations (per selected phase)
**Launch Agent:** `researcher`

Using the Auditor’s report:
- Verify completeness of the current block set against the architecture.
- Determine which blocks should be added, changed, merged, split, or removed.
- Review and improve the formulations of blocks for clarity and independence.
- Identify modern analysis practices and angles that are useful for each block.
- Flag any other issues that reduce quality, consistency, or laconicity.

Return a structured recommendation containing:
- Proposed final set of blocks (keep / modify / add / remove / merge).
- Suggested short, self-contained formulations for each block.
- Recommended modern practices / analysis angles (briefly).
- Any remaining quality or brevity concerns.

**Important:** Never change any code or existing audit phase files.

---

### 1.3. Apply Changes (per selected phase)
**Launch Agent:** `doc-specialist`

Using the Auditor and Researcher outputs:
- Edit the phase file in place.
- Preserve the original essence and overall responsibility of the phase.
- Align every block with the current high-level architecture.
- Make each block maximally short, independent, and practical (checklist style).
- Ensure descriptions guide *what* and *how to look*, without prescribing concrete files, modules, or rigid steps.
- Keep numbering and file structure consistent with existing conventions.


**Key requirements for the result:**
- Each block remains an independent task that a separate auditor can execute.
- Blocks must reflect the high-level architecture — name and description alone should make clear what to analyse.
- Descriptions guide the auditor on *how to look* and *under what angle*, but must **not** prescribe specific files, modules, or step-by-step procedures.
- Incorporate modern analysis practices where they add value.
- Maximum brevity and clarity: final phases must read as concise checklists, not detailed methodologies.

**Important:** Modify only the selected phase file. Do not touch code or other phase files.

---


## Step 2. Final Consistency Check (after all selected phases)
**Launch Agent:** `auditor`

- Verify that all refined phases:
  - remain consistent with each other and with high-level architecture,
  - keep distinct responsibilities,
  - use the same concise checklist style,
  - contain no residual outdated or overlapping blocks.
  - Each block remains an independent task that a separate auditor can execute.
  - Blocks must reflect the high-level architecture — name and description alone should make clear what to analyse.
- Produce a short validation report.

**Important:** Never change any code or phase files at this stage.

---

## Step 3. Final Adjustments
**Launch Agent:** `doc-specialist`

- Apply the fixes and improvements identified in the Step 5 validation report.
- Make only the necessary changes to the affected phase files.
- Preserve the original essence, checklist style, and independence of blocks.
- Ensure the final versions fully satisfy the Goal and Key requirements.

**Important:** Modify only the phase files listed in the validation report. Do not touch code or unrelated files.


# Expected Result
- User-selected phases refined one by one.
- Each refined phase is a concise checklist of independent blocks aligned with current architecture.
- Original essence of every phase preserved.
- Final auditor validation confirming consistency and quality.

## Goal
Adapt the selected existing audit phases to the current architecture.  
Preserve the original essence of each phase, but change, add, merge, remove, or rework individual blocks as needed so they accurately reflect the system.



