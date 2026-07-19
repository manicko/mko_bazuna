---
name: implement-multiple-tasks
description: Execute semantic development tasks safely and incrementally using implementor subagents with validation and completion control
agent: implementor-orchestrator
alwaysApply: false
allowed-tools:
  - read_file
  - write_to_file
  - execute_command
  - list_files
  - search_files
  - new_task
---

<objective>
Execute implementation tasks through an orchestrator + implementor workflow.

</objective>

<process>

Follow the process below step by step 

## 1. User prompt
 - Ask: "How many tasks should be implemented in this run?"
- Store answer as `{MAX_TASKS}` 
- Ask: "How many subagents can run in parallel?"
- Store answer as`{MAX_SUBAGENTS}`


## 2. Load and Summarize Project Context

- `AGENTS.md`
- `docs/SPEC.md`
- `README.md`

Summarize into `{MAIN_CONTEXT}`


## 3. Prepare Execution Loop

- Read execution order: `.ai/tasks/todo/order.yaml` to understand the dependencies 
- List task-files in `.ai/tasks/todo/*`
- Select up to `{MAX_TASKS}` files as `{TASKS_FILES_TO_IMPLEMENT}`, preserving execution order.


## 4. Task Execution Loop

For each task file in `{TASKS_FILES_TO_IMPLEMENT}` one at a time:

### 4.1  Prepare {subagent_prompt} using template below do not add text from Task file

<subagent_prompt>

## What To Do
1. Read the task file {TASK_FILE_ABS_PATH}. Understand scope, affected files, acceptance criteria.
2. Read `docs/98-reference/ast-editor.md` for proper tools usage. Always use replace_function  to avoid indentation errors.
2. Validate preconditions: semantic targets exist, depends_on tasks are done.
  If already implemented: rename to *_DONE.yaml, move to done/, return IMPLEMENTATION_COMPLETE.
3. Implement: edit only required files.  
4. If found a bug or any problem not relates to the task - don't solve, but create the new file with report to .ai/audit/00-bug_report/ХХ-report.md
XX - free number.
5. Validate:
   - Python: uv run ruff check <files>, uv run mypy <files>, uv run basedpyright <files>, uv run pytest <paths>
   - Frontend: npm run build, npm run lint, npm run test
  Fix only issues caused by your changes.
  -If tests conflict with architecture:
    -- update tests
    -OR
    -- remove obsolete tests
  -Do NOT degrade architecture for outdated tests.

6. Finalize: rename task file to *_DONE.yaml, move to .ai/tasks/done/.
If you see changes in files not related to the task it is normal - other agents are doing their task in parallel.

Output:
Return ## IMPLEMENTATION_COMPLETE or ## IMPLEMENTATION_BLOCKED.
Include: summary, files modified, validation results, problems found.


Project Context:

{MAIN_CONTEXT}


GIT: Do not execute any Git command that modifies the repository state. You are working on the same files with other agents.
Use ruff to clean blank lines

</subagent_prompt>


### 4.2  Spawn Implementor Subagent

Run up to {MAX_SUBAGENTS} subagent at a time. If errors switch to 1 - never parallel.

```
Task(
  prompt="{subagent_prompt}",
  agent="implementor",
  mode = "subagent",
  description="Implement task {TASK_FILE_NAME}"
)
```

### 4.3 Handle Subagent Return & Finalization Check

  - if no subagent report or error - restart task
  - if task finished check the agent report:
      - ensure task file moved to `done/*_DONE.yaml` (absent from `todo/`).  
      -  validate related to the task-files changes (ignore file changes not related to the task) 
          ```powershell
          git diff HEAD --stat   
          ```

      - **If checks pass:**
          ```powershell
          git add <task-related files>
          git commit -m "{type}({scope}): {description}" -m "Task: {TASK_FILE_NAME}"
          ```
        **Rules:**
        - Always `git add <specific files>` — never `-A` or `.`
        - Commit as soon as any agents done. Parallel agent tasks can be joined in one commit.

        **If checks fail:**
        - `git restore <task-related files only>` (only if 100% sure of breakage)
        - Re-spawn implementor with error details
        - Do NOT continue or touch unrelated files

### 4.5 Continue or Stop
If `{COMPLETED_TASKS} >= {MAX_TASKS}`: STOP.
Otherwise: next task, spawn fresh subagent.

</process>

<output>

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IMPLEMENTATION RUN COMPLETE ✓
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Tasks completed: {COMPLETED_TASKS}/{MAX_TASKS}

Completed tasks:
- {TASK_NAME}

Validation:
- task finalization verified
- done/ migration verified
- git commit created per task by orchestrator

Status:
✓ Architecture preserved
✓ Tests validated
✓ Lint/type checks validated
```

</output>

<success_criteria>

* [ ] User execution limit requested
* [ ] One subagent per task with proper prompt
* [ ] Orchestrator reviews diffs and commits (not subagent)
* [ ] git add <specific files> only (never add -A / add .)
* [ ] git restore only <specific files> with user confirmation
* [ ] Task renamed to *_DONE.yaml, moved to done/
* [ ] One conventional commit per task (or batch of tasks if done in parallel) by orchestrator
* [ ] Failed finalization triggers corrective subagent

</success_criteria>
