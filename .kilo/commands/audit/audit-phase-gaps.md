---
name: audit-phases-review
description: Assess whether the current audit phases adequately cover the architecture and determine the minimum required new audit phases
agent: tech-lead
alwaysApply: false
---
# Task: Audit Phases Coverage Review


# Workflow
Do not argue on the workflow, just follow.

## Step 1. Study Current Architecture and Existing Audit Phases

**Launch Agent:** `auditor`

- Build a high-level understanding of the current system architecture: overall structure, main components, and how they interact.
- Collect only top-level information — no deep dives into implementation details.
- Examine all current audit phases located at:  
  `.kilo\commands\audit\phases`
- Extract the purpose, scope, and focus of each phase.
- Produce two clear blocks of information:
  1. **Architecture overview** — how the system is structured and how its components interact at a high level.
  2. **Audit coverage map** — which blocks/areas the current audit phases investigate.
- This combined context will be passed to the next researchers.

**Important: Never change any code or existing audit phase files.**

---

## Step 2. Independent Research

**Launch Agent:** `researcher` × 4 (four independent instances, same task)
Divergence of opinions is expected and valuable.

All researchers receive identical instructions and the two information blocks from Step 1:

1. Study modern audit practices for systems with similar architecture.
2. Answer only the high-level question:Do we need new audit phases, or are the existing phases sufficient and only need improvement?
3. Do **not** perform a detailed review of every existing phase (that is a future task).  
4.  Distinguish between: 
    - adding a new audit phase 
    - extending/improving existing phases

Each researcher returns an independent structured opinion containing:
- Assessment of coverage sufficiency
- Recommendation: “refine existing” / “add new phase(s)” / “both”
- Brief justification and suggested new phase themes (if any)

**Important: Never change any code or existing audit phase files.**

---

## Step 3. Validate & Consolidate

**Launch Agent:** `validator`

- Collect and compare the four independent researcher reports.
- Evaluate the proposed options for necessity, overlap, and value.
- Produce a final list of **minimally necessary new phases** (or explicitly state that none are required).
- Justify each decision.

**Important: Never change any code or existing audit phase files.**

---

## Step 4. Create New Phase Specifications (conditional)

**Condition:** Execute only if Step 3 recommends one or more new phases.

**Launch Agent:** `doc-specialist`

- Create the audit phase task following the structure and conventions of existing phases 
- Assign the next available phase number (`12`, `13`, etc.) 
- Define a distinct audit responsibility not already adequately covered 
- Keep the scope minimal and non-overlapping 
- Preserve consistency with existing phase formats

**Important: Never change any code or existing audit phase files.**

---

## Step 5. Final Document Audit

**Launch Agent:** `auditor`

Ask it to verify: 
- New phase documents match the approved Validator recommendations and overall audit convention
- Each phase has a clear and distinct responsibility
- Consistency, completeness, and adherence to the process constraints
- Numbering and structure are correct 


**Prompt addition:** Do not change any code.

---

# Expected Result
- Combined high-level architecture overview + audit coverage map from Step 1.
- Four independent researcher perspectives on phase coverage.
- Validator decision on the minimal set of required new phases (or confirmation that none are needed).
- New phase specification files (if required) numbered 12+.
- Final auditor validation report confirming process integrity.
