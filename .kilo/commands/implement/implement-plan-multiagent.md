---
name: implement-plan-multiagent

description: Execute development plan incrementally using adaptive multi-agent workflow

alwaysApply: false

---

# Task: Multi-Agent Plan Implementation

## Objective

Execute the development plan safely and incrementally.

The Tech Lead is **orchestrator only**:

- Coordinate agents
- Pass only required context
- Control dependencies and execution order
- Commit completed blocks
- Run final validation

The Tech Lead never implements code or performs implementation-level validation.

---

# Workflow

## 1. Inspect relevant current architecture and implementation 

Launch an `Auditor` to inspect the current codebase relevant to the plan.

Ask it to determine:

- What is already implemented
- Whether the plan matches the current implementation
- Relevant architecture, dependencies, and constraints
- Important discrepancies or risks

Save the concise result as `{code_context}`.


## 2. Decompose Plan
Then launch a `Planner` with the plan and `{code_context}`.

Ask it to:
- Decompose the plan into logical execution blocks
- Identify dependencies and execution order
- Assess implementation, rollout, regression, and compatibility risks
- Identify multiple implementation paths alternatives when relevant, for maintainability, future evolution, and project conventions
- **Not choose the final implementation approach when technical uncertainty exists**
- For each block, determine whether the following agents are required:
  - **High risks** - all agents below 
  - **Auditor** — deeper code/architecture investigation due to uncertainty or complexity
  - **Researcher** — modern best practices, multiple viable approaches, architectural/support implications
  - **Planner** — detailed pre-implementation design, architecture, testing, or complex execution
  - **Validator** — independent review when implementation risk is high
- Identify the reason for each required agent
- Keep the scope minimal and avoid speculative redesign
- Important: Never change code, you only plan

Save the result as `{plan_context}`.



## 3. Execute Blocks

Execute blocks according to `{plan_context}`.

Independent blocks may be prepared in parallel, including `Auditor`, `Researcher`, and `Planner` work.

**Never run multiple `Implementor` agents in parallel.**

For each block, execute the required agents sequentially and pass context forward.

---
### 3.1 Auditor — if required

Launch `Auditor`  with:

`{plan_context_exec_block}`

Inspect the current implementation and architecture relevant to the block:
* Code and architecture
* Existing patterns and constraints
* Current implementation
* Risks
* Important: Never change code
Return `{context_a}`.

### 2.2 Researcher — if required

Launch a `Researcher` with:

`{plan_context_exec_block} + {context_a}`

- Identify viable alternatives when relevant
- Research the relevant modern practices 
- Evaluate viable implementation approaches
- Assess architectural, implementation, rollout, regression, and compatibility risks
- Select the **best implementation path** for maintainability, future evolution, and project conventions
- Avoid speculative redesign
- Important: Never change code
Return `{context_r}`.


### 2.3 Planner — if required

Launch a `Planner` with:

`{plan_context_exec_block} + {context_a} + {context_r}`

Create the implementation task for the `Implementor`.

Use **semantic code units only**:
- Files
- Modules
- Classes
- Functions
- Methods
- Components

**Never use line numbers.**

Define:
- Exact implementation scope
- Implementation sequence
- Architectural constraints
- Required tests

Tests should verify **logic and component interaction**, not trivial implementation details.

Important: Never change code

Return `{plan_task}`.



### 2.4 Implementor

Launch **`Implementor`** (one at a time) with the required context:

`{context_a} + {context_r} + {plan_task}`

Implementor owns the local cycle:

- Implementation
- Required tests
- Relevant tests, lint, and type checks
- Fixing failures
- Local validation
- Commit only the current work item
```bash
git add <specific-files>
git commit -m "{type}({scope}): {description}"
```

You are working with other agents in parallel if you see changes not done by you - it is normal.
Never ran `git reset`, `git checkout`
Never rewrite history.

- Return only when locally validated and commit

---


## 3. Documentation

After all implementation blocks are complete:

Launch `Doc-specialist`.

Ask it to update only the documentation affected by the implementation, following:

`mko_bazuna/docs/00-overview/doc-maintenance-rules.md`

Do not introduce unrelated documentation changes.

Commit documentation changes separately.
```bash
git add <specific-files>
git commit -m "{type}({scope}): {description}"
```
You are working with other agents in parallel if you see changes not done by you - it is normal.
Never ran `git reset`, `git checkout`
Never rewrite history.
Important: Never change code
---

## 4. Final Validation

Launch `Validator` for the completed implementation.

Check:

* Plan completeness
* Cross-block integration
* Architectural consistency
* Regressions
* Tests and quality gates
* Documentation
* Unrelated changes
* Important: Never change code

## 5. If issues are found:
Launch one `Implementor` to fix and commit
Validate locally

---

# Constraints
* Only Implementor can change code. Instruct other agents to not change any code file.
* Execute only the agents required for the current block
* Pass concise context between agents
* Independent non-Implementor agents may run in parallel
* **Never run multiple Implementors in parallel**

---

# Expected Result

* Current implementation understood before execution planning
* Plan decomposed into dependency-aware work blocks
* Agent usage adapted to block complexity and risk
* Each block implemented, locally validated, and committed separately
* Documentation updated according to repository rules
* Final validation passed
* Architecture and project conventions preserved

---

# Plan File

