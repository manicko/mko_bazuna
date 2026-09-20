---
name: implement-plan-multiagent

description: Execute development plan incrementally using adaptive multi-agent workflow

alwaysApply: false

---

# Task: Multi-Agent Plan Implementation

# Workflow
Do not argue on the workflow, just follow.
## 1. Inspect relevant current architecture and implementation 

Launch an `Auditor` to inspect the current codebase relevant to the plan.

Provide:
{plan_file} +
<original_prompt>
- What is already implemented
- Whether the plan matches the current implementation
- Relevant architecture, dependencies, and constraints
- Important discrepancies or risks
**Important: Never change any code or existing audit phase files.**
Output as `{code_context}`.
<original_prompt>


## 2. Decompose Plan
Then launch a `Planner` with the {plan_file} and `{code_context}`.

Provide:
<original_prompt>
- Decompose the plan into logical execution blocks
- Identify dependencies and execution order
- Assess implementation, rollout, regression, and compatibility risks
- Identify multiple implementation paths alternatives when relevant, for maintainability, future evolution, and project conventions
- **Not choose the final implementation approach when technical uncertainty exists**
- Keep the scope minimal and avoid speculative redesign
- For each block, determine whether the following agents are required:
  - **High risks** - all agents below 
  - **Auditor** — deeper code/architecture investigation due to uncertainty or complexity
  - **Researcher** — modern best practices, multiple viable approaches, architectural/support implications
  - **Planner** — detailed pre-implementation design, architecture, testing, or complex execution
  - **Validator** — independent plan review when implementation risk is high
**Important: Never change any code or existing audit phase files.**
<original_prompt>

Save the result as `Execution plan`: `.ai\plans\{next-number}-{plan-name}.md`.
----------------------------------

## 3. Execute Blocks

For each block, execute the required agents sequentially (following the order below):

---
### 3.1 Auditor — if required

Launch `Auditor`  with:

`{plan_context_exec_block}`

<original_prompt>
Inspect the current implementation and architecture relevant to the block:
* Code and architecture
* Existing patterns and constraints
* Current implementation
* Risks
**Important: Never change any code or existing audit phase files.**
Update `Execution plan` and Return `{context_a}`.
<original_prompt>

### 3.2 Researcher — if required

Launch a `Researcher` with:

`{plan_context_exec_block} + {context_a}`

<original_prompt>
- Identify viable alternatives when relevant
- Research the relevant modern practices 
- Evaluate viable implementation approaches
- Assess architectural, implementation, rollout, regression, and compatibility risks
- Select the **best implementation path** for maintainability, future evolution, and project conventions
- Avoid speculative redesign
**Important: Never change any code or existing audit phase files.**
Update `Execution plan` and Return `{context_r}`.
<original_prompt>

### 3.3 Planner — if required

Launch a `Planner` with:

`{plan_context_exec_block} + {context_a} + {context_r}`


<original_prompt>
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
- Use template `.ai\tasks\templates\task_template.yaml` to organize `{task_description}` in the `Execution plan`
**Important: Never change any code or existing audit phase files.**
<original_prompt>

Update `Execution plan` and Return `{task_description}`.


### 3.4 Implementor

Launch **`Implementor`** (one at a time) with the required context:

`{context_a} + {context_r} + {task_description}`
<original_prompt>
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
**Important: Never change plans or existing audit phase files.**
<original_prompt>

---


## 4. Documentation

After all implementation blocks are complete:

Launch `Doc-specialist`.

Ask it to update only the documentation affected by the implementation, following:

<original_prompt>
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
**Important: Never change any code or plans or existing audit phase files.**
<original_prompt>
---

## 5. Final Validation

Launch `Validator` for the completed implementation.

<original_prompt>
Check:

* Plan completeness
* Cross-block integration
* Architectural consistency
* Regressions
* Tests and quality gates
* Documentation
* Unrelated changes
* Important: Never change any code or existing audit phase or plan files.
<original_prompt>

## 6. If issues are found:
Launch one `Implementor` to fix and commit
Validate locally

---

# Constraints
The Tech Lead is **orchestrator only**:
- Coordinate agents
- Do **not** rewrite, summarize, replace, weaken <original_prompt>
- You may add relevant context, findings, decisions, risks, file/module information, or execution instructions 
- If you need to study the code, you launch researchers or auditors agents. You do not study yourself.

The Tech Lead understand project rules and general architecture but never implements code.* 

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

