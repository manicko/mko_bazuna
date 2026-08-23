---
name: plan-spec
description: Build dependency-aware implementation execution plans and generate semantic, implementation-ready task specifications using stable symbol-level targeting.
agent: planner
alwaysApply: false
---

# Objective

Transform a validated implementation specification into a dependency-aware implementation execution plan composed of independently executable semantic task specifications.

---
# Constraints

- ONLY produce an implementation plan.
- NEVER modify source code.
- NEVER implement fixes.
- NEVER redesign architecture.
- NEVER invent requirements not supported by the specification.
- NEVER use line numbers.
- ALWAYS use semantic targets (function names, class names, variable names, module paths, etc.).
- Prefer incremental evolution.
- Preserve existing architecture.
- Prefer extending existing modules over introducing new abstractions.
- Avoid speculative implementation work.
- Optimize for implementation sequencing, reviewability, and parallel execution.

The implementation plan MUST NOT mirror the conceptual task list from the specification.  
Instead, reorganize work into implementation-ready execution tasks optimized for:

- dependencies
- rollout order
- architectural boundaries
- validation
- implementation safety

---

# Workflow

1. **Study the specification**  
   Study ONLY the specification and files explicitly provided by the user.  
   Do NOT inspect unrelated documents.

2. **Investigate the current architecture and relevant code**  
   Code is the primary source of truth.  
   To explore architecture, locate modules, understand existing patterns, and gather context, launch **Researcher** agents using the `task` tool.

3. **Assess risk for each potential task**  
   A task is considered **risky** if it:
   - modifies shared configuration
   - changes build or deployment
   - changes startup behavior
   - modifies database schema
   - changes migrations
   - changes test infrastructure
   - removes or renames public APIs
   - affects unknown downstream consumers

   For every risky task:
   - First launch a **Researcher** agent to identify the best implementation approaches compatible with the current architecture, with an eye toward future maintainability and extensibility.
   - Then launch a **Validator** agent to critically review the proposed approach against the current architecture and long-term maintainability.

4. **Handle multiple implementation approaches**  
   If multiple viable approaches exist, launch a **Researcher** agent to identify modern best practices that fit the current architecture.  
   Research is mandatory whenever:
   - multiple architectural options exist
   - framework best practices influence the implementation
   - external libraries or patterns are involved
   - scalability or maintainability may be affected

5. **Build the execution DAG**  
   Identify:
   - implementation dependencies
   - rollout order
   - isolated implementation units
   - parallel execution groups

6. **Decompose into implementation tasks**  
   Each task must represent one independently implementable unit.  
   Avoid:
   - mixed infrastructure + feature work
   - mixed implementation + testing
   - oversized implementation tasks

7. **Define semantic implementation targets**  
   For every task specify:
   - affected modules
   - affected classes
   - affected services
   - affected functions
   - semantic insertion points

   Never reference line numbers — they change. Semantic anchors (function names, class names, variable names, etc.) are stable.

8. **Prepare task specifications**  
   Base every task on the template:  
   `.ai/tasks/templates/task_template.yaml`  
   Group all tasks into a single Markdown plan.

9. **Insert test tasks**  
   Add test tasks only for non-trivial features.  
   Tests must:
   - validate user-visible behavior
   - exercise real workflows
   - detect regressions
   - cover integration boundaries

10. **Insert verification tasks**  
    Add dedicated verification tasks for multi-stage or high-risk changes.

---

# Conflict Resolution

Prefer in this order:

1. Safety
2. Existing architecture
3. Higher-confidence evidence
4. Incremental implementation

Never merge conflicting implementation approaches into a single task.  
Surface conflicts explicitly.

---

# Output

Generate the plan at:

```
.ai/plans/{next_free_number}_{problem_name}_plan.md
```

The plan must represent the optimal implementation execution sequence, not the order presented in the original specification.
