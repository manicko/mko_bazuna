---
name: plan-tasks
description: Build dependency-aware rollout plans and generate semantic implementation-ready task specifications using stable symbol-level targeting
agent: planner
alwaysApply: false
---

## Objective

Transform validated findings into dependency-aware rollout plans with semantic task specifications.

## Constraints

- DO NOT modify source code
- DO NOT implement fixes
- DO NOT redesign architecture
- ONLY plan and generate semantic implementation tasks
- DO NOT use line numbers — use semantic anchors (modules, functions, classes)
- Prefer incremental evolution and stable semantic targeting
- Avoid broad rewrites and line-based assumptions

## Steps

1. **List** files .ai/audit/99-validation/` and `.ai/plans` (do not read contents yet) 
2. **Ask user** to select: one file, multiple files, or ALL. Wait for selection.
3. **Study** selected files — plans, validated findings, safety constraints, rollout constraints. Ignore rejected/stale findings.
4. **Load structural context** — `.ai/structure/*` dependency chains, integration boundaries, coupling zones, semantic insertion points.
5. **Build execution DAG** — isolated implementation blocks, dependency-aware task graph, rollout sequencing, parallel execution groups.
6. **Establish file-based dependencies** — tasks modifying the same file must execute sequentially with explicit `depends_on_previous_task_in_chain`, even if only one file overlaps.
7. **Define semantic targets** per task — affected files, symbol targets, anchors, insertion zones. Never use line numbers.
7. **Generate task specifications** using `.ai/tasks/templates/task_template.yaml`. 
8. **Assess risk** — for potentially disruptive tasks (config changes, test infra, schema changes, hidden consumers), mark as blocked and create prerequisite research tasks.
9. **Insert test tasks** — only for non-trivial features. Tests must validate user-visible behavior, exercise workflows, detect regressions.
10. **Insert verification tasks** — inline verification for simple tasks; dedicated verification tasks for multi-stage/high-risk changes.
11. **Generate execution ordering** using `.ai/tasks/templates/order_template.yaml`. Numbering must match rollout order. No circular dependencies.

## Task Naming

```
TASK_<XXX>_<task_id>_<short_name>.yaml
```

- `XXX` = exact execution order position
- Numbering must preserve sortable execution order

## Duplicate Detection

A task is a duplicate if: objective matches AND primary symbol targets overlap AND intended change is semantically equivalent. Merge/update instead of duplicating.

## Risk Assessment Rules

A task is **risky** if it:

- Modifies config files affecting multiple services
- Changes test infrastructure
- Removes/renames code with potential hidden consumers
- Modifies database schema or migrations
- Changes build/deployment/startup behavior
- Has unclear downstream impacts from static analysis

For risky tasks:

1. Mark task as `status: blocked` with `blocked_by: TASK_XXX_research_<topic>`
2. Create prerequisite research task identifying all dependents, assessing impact, evaluating alternatives, producing go/no-go recommendation
3. Blocked implementation task depends on research task
4. Implementation must NOT execute until research recommends "go" or "go-with-changes"

## Verification Task Pattern

```yaml
type: verification
verifies:
  - TASK_XXX
verification_steps:
  - build
  - test
  - smoke_check
pass_criteria: ...
failure_action: return task to rework
```

## Conflict Resolution

- Prefer safety constraints
- Prefer higher-confidence findings
- Surface conflicts in task metadata
- Never merge conflicting recommendations into a single task

## Output
- Semantic task YAML files in `.ai/tasks/todo/`
- Rollout ordering file (`order.yaml`)
- Dependency graph / execution DAG