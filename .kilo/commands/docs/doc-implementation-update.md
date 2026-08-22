---
name: doc-implementation-update
description: Update project documentation based on implemented significant functionality using multi-agent research
agent: docs-specialist
alwaysApply: false
---

# Task: Update Documentation Based on Implemented Significant Functionality

## Goal
Analyze the current project implementation (code, architecture, development plans/specs) together with existing documentation, identify only truly significant new or changed functionality that is missing from the docs, and update the documentation accordingly.

**Critical constraint:** The doc-specialist has very limited memory.  
Therefore the specialist **must** launch Researcher agents for every step that requires reading large amounts of context (specs, code, architecture docs, existing documentation). The specialist itself only collects the structured summaries returned by the Researchers and performs the final writing/editing of the documentation.

Strictly follow the documentation rules in `docs/00-overview/doc-maintenance-rules.md` (if present).

---

# Workflow

## Step 1. Launch Researchers – Identify Significant Functionality from Specifications / Plans

Spawn one or more Researcher agents to:

- Read every relevant specification, development plan, or architecture document listed in the **Source Documents** section (or discovered in the project).
- For each specification / plan, extract only the **important** planned or implemented changes that should be considered for documentation.
- Apply the significance criteria strictly:

  **Functionality is considered significant if it:**
  - adds a new business capability
  - introduces a new user workflow
  - changes the system architecture model
  - adds a new subsystem / module / domain
  - significantly expands the API, processing pipeline, or data model
  - affects security, scalability, roles, permissions, or data lifecycle

  **Do NOT include:**
  - bug fixes
  - renaming
  - behavior-preserving refactoring
  - internal optimizations
  - minor UI / API improvements
  - local infrastructure changes
  - test utilities
  - temporary workaround solutions

- Produce a structured list of candidate significant features with short justification for each.

Collect the summaries. Do **not** read the full source documents yourself.

## Step 2. Launch Researchers – Verify Current Implementation & Architecture

Spawn Researcher agents to:

- Inspect the actual codebase and architecture (`STRUCT.md`, relevant architecture docs, modules, APIs, data models).

- Cross-check each candidate significant feature against the current implementation to determine how it is actually implemented and behaves.

- Treat the current code as the source of truth for implementation details and documented behavior.

- Extract the precise current implementation details and architectural context that are relevant for documentation (high-level only).

- Note any important deviations from the original plans that affect how the feature should be described.

Obtain concise implementation and architecture reports from the Researchers.

## Step 3. Launch Researchers – Determine Documentation Impact & Required Updates

Spawn Researcher agents to:

- Review the current project documentation (`docs/*` and especially `docs/00-overview/doc-maintenance-rules.md`).
- For each verified significant feature, determine:
  - Which existing documentation sections (if any) are affected.
  - Whether the feature is already described (directly, partially, conceptually, or via a related feature).
  - Exactly how the feature should be described following the project documentation rules.
  - Recommended structure and placement of the updates.
- Identify any contradictions, overlaps, or missing high-level context.

Collect structured recommendations on what to update and how.



## Step 4. Implementation Discrepancy Reporting

If on Step 3. the Researcher identifies a discrepancy between the planned or specified behavior and the current code implementation:
- Create a detailed discrepancy report in .ai/audit/problems`.
- For each discrepancy, describe which requirement, specification, or planned behavior differs from the current implementation.
- Include the specific relevant files, modules, and implementation details needed to understand the discrepancy.
- Keep these findings separate from the documentation update unless the discrepancy changes how the implemented functionality must be documented.



## Step 5. Apply the Updates (doc-specialist only)

Using **only** the summaries and reports returned by the Researcher agents:

- Update the relevant files under `docs/*`.
- Ensure the documentation remains high-level and architecture-oriented.
- Include only significant functionality; exclude all technical noise and low-level implementation details.
- Strictly follow `docs/00-overview/doc-maintenance-rules.md`.
- Do not re-read large original documents or the full codebase yourself. Rely exclusively on Researcher outputs.

---

# Expected Result

Updated project documentation that:

- Accurately reflects only the significant implemented functionality
- Is consistent with the current architecture and codebase
- Contains no technical noise, bug fixes, refactors, or minor changes
- Follows the project documentation rules
- Has been produced by the doc-specialist after collecting and synthesizing research from multiple Researcher agents

---

# Source Documents / Context
