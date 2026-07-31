---
name: plan-spec
description: Build dependency-aware implementation execution plans and generate semantic implementation-ready task specifications using stable symbol-level targeting.
agent: planner
alwaysApply: false
---

# Objective

Transform a validated implementation specification into a dependency-aware implementation execution plan composed of independently executable semantic task specifications.


---

# Constraints

- ONLY produce an implementation plan
- NEVER modify source code
- NEVER implement fixes
- NEVER redesign architecture
- NEVER invent requirements not supported by the specification
- NEVER use line numbers
- ALWAYS use semantic targets
- Prefer incremental evolution
- Preserve existing architecture
- Prefer extending existing modules over introducing new abstractions
- Avoid speculative implementation work
- Optimize for implementation sequencing, reviewability, and parallel execution

The implementation plan MUST NOT mirror the conceptual task list from the specification.

Instead, reorganize work into implementation-ready execution tasks optimized for:
- dependencies
- rollout order
- architectural boundaries
- validation
- implementation safety

---

# Workflow

1. Ask the user which specification(s) should be planned.
2. Study ONLY the specification and files explicitly provided by the user.
Do NOT inspect unrelated documents.

3. If multiple implementation approaches exist, run the Researcher agent to identify modern best practices compatible with the current architecture.

Research is mandatory whenever:
- multiple architectural options exist
- framework best practices influence implementation
- external libraries or patterns are involved
- scalability or maintainability may be affected

4. Load structural context

Read:
- `.ai/structure/*`

Determine:
- dependency chains
- integration boundaries
- coupling zones
- semantic insertion points

5. Build the execution DAG

Identify:
- implementation dependencies
- rollout order
- isolated implementation units
- parallel execution groups

6. Decompose implementation
Each task must represent one independently implementable unit.

Avoid:
- mixed infrastructure + feature work
- mixed implementation + testing
- oversized implementation tasks

Split work whenever independent review or parallel implementation is possible.

7. Define semantic implementation targets

For every task specify:

- affected modules
- affected classes
- affected services
- affected functions
- semantic insertion points

Never reference line numbers.

8. Generate implementation task specifications basing on template:
`.ai/tasks/templates/task_template.yaml`
Group all tasks in one plan

9. Assess implementation risk

A task is considered risky if it:
- modifies shared configuration
- changes build or deployment
- changes startup behavior
- modifies database schema
- changes migrations
- changes test infrastructure
- removes or renames public APIs
- affects unknown downstream consumers

For risky tasks:

- create prerequisite research task
- mark implementation task as blocked
- add blocked_by reference

Implementation may proceed only after research recommends:

- Go
- Go with changes

10. Insert validation tasks

Generate testing tasks only when implementation is non-trivial.

Tests should validate:

- user-visible behavior
- workflows
- regressions
- integration boundaries

---

# Conflict Resolution

Prefer:

1. Safety
2. Existing architecture
3. Higher-confidence evidence
4. Incremental implementation

Never merge conflicting implementation approaches into one task.

Surface conflicts explicitly.

---

# Output

Generate:

`.ai/plans/{next_free_number}_{problem_name}_plan.md`

The plan must represent the optimal implementation execution sequence rather than the order presented in the specification.