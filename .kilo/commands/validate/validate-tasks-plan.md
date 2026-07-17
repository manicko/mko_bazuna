---
name: validate-tasks-plan
description: Validate semantic implementation task specifications, dependency integrity, semantic targeting stability, and execution applicability before implementation
agent: validator
alwaysApply: false
---

# Task Specification Validation Workflow

## Objective

Validate semantic implementation tasks before execution to ensure:
- execution safety
- architectural consistency
- dependency correctness
- semantic target stability
- rollout survivability
- correct handling of different finding types (spec-deviation vs best-practice vs doc-update)

Reject:
- unsafe tasks
- stale tasks
- ambiguous targeting
- invalid dependency sequencing
- architecture-breaking changes
- tasks that should be doc-updates instead of code changes

## Constraints

- DO NOT modify source code
- DO NOT implement tasks
- DO NOT redesign architecture
- DO NOT expand task scope
- Prefer conservative validation
- Prefer rejection over unsafe approval

---

# Workflow

## Step 1 — Load Context

Study:
- validated findings
- dependency graph
- semantic anchor maps
- structure maps
- existing tasks
- execution ordering files

---

## Step 2 — Load Tasks

Study tasks and order from:
- `.ai/tasks/todo`

Analyze:
- task metadata
- semantic targets
- dependency definitions
- rollout ordering

---

## Step 3 — Validate Task Structure

Validate:
- yaml validity
- required fields
- task naming
- task id uniqueness
- dependency references

Check naming:
- `TASK_<XXX>_<task_id>_<short_name>.yaml`

Validate:
- numbering consistency
- sortable rollout order

---

## Step 4 — Validate Dependency Integrity

Validate:
- `depends_on` correctness
- topological ordering
- rollout consistency
- dependency graph integrity
- safe execution ordering

Detect:
- circular dependencies
- hidden dependency chains
- invalid rollout sequencing
- overlapping execution phases

---

## Step 5 — Validate Semantic Targeting

Validate:
- symbol existence
- anchor existence
- semantic uniqueness
- insertion stability
- target survivability

Reject:
- ambiguous targets
- fragile anchors
- unstable insertion zones
- line-based assumptions

Prefer:
- symbol-level targeting
- stable semantic anchors
- lifecycle boundaries
- transaction boundaries
- function-call anchors

---

## Step 6 — Validate Scope Isolation

Validate:
- one coherent responsibility per task
- minimal affected surface
- execution independence
- low coupling
- architectural isolation

Reject:
- broad rewrites
- mixed responsibilities
- tightly coupled modifications
- speculative changes

---

## Step 7 — Validate Architectural Safety

Validate:
- architecture boundaries
- dependency direction
- layering consistency
- backward compatibility
- integration safety

Reject:
- architecture-breaking tasks
- unsafe cross-layer changes
- hidden coupling
- architecture drift

---

## Step 8 — Validate Execution Readiness

Validate:
- implementation clarity
- actionable changes
- measurable acceptance criteria
- validation/tests
- rollout applicability

Check:
- task still relevant
- functionality not already implemented
- assumptions still valid

---

## Step 9 — Produce Validation Result

Create validation report:

- `.ai/tasks/validation/tasks_validated_findings_<next_number>.md`

Where:
- `<next_number>` = next free sequential number

Report must include:
- approved tasks
- rejected tasks
- dependency warnings
- semantic stability warnings
- rollout warnings
- required corrections
- stale or invalid assumptions
- unsafe execution areas

For every rejected task:

1. Rename task file:
- `*_REJECTED.yaml`

2. Update task content with:
- rejection reason
- stale assumptions
- unsafe areas
- dependency conflicts
- semantic instability
- required fixes before reconsideration

Rejected tasks must MUST NOT be deleted.
---

# Expected Result

Result must include:
- validated task set
- approved execution graph
- dependency validation results
- semantic stability analysis
- execution safety warnings
- rejected task analysis
- rollout consistency validation

Result must NOT include:
- code changes
- implementation code
- speculative redesign
- automatic task rewrites