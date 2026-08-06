---
name: audit-multi-phase
description: Execute full multi-agent audit pipeline using orchestrator coordination, executor subagents, and validator subagents with retry logic
agent: audit-orchestrator
alwaysApply: false
allowed-tools:
  - read_file
  - write_to_file
  - list_files
  - search_files
  - new_task
---

<objective>
Execute the complete multi-agent audit pipeline: prepare context, execute all phases with executors, validate findings.
Max allowed parallel subagents = 2

</objective>

<process>



## 0 Select Phases

list of files in `.kilo/commands/audit/phases/`
filter out `99-audit-validate.md`.

Present the list to the user as a numbered table:

| # | Phase | File |
|---|-------|------|
| {N} | {name} | `{filename}` |
...

**Ask the user:** which phases to execute? Options:
- `all` — run all listed phases
- comma-separated numbers (e.g. `1,3,4`) — run selected phases only

Store the result as `{SELECTED_PHASES}`.
From `{SELECTED_PHASES}` parse each remaining filename (`NN-audit-name.md`) to extract phase number and name.


## 1. Gather Base Layer Context (once)


Read `.ai/context/commands.md` for verification commands.
Read `AGENTS.md` for project guidelines.
List documentation structure from `docs/` folder.

Set variables:
- `{BASE_CONTEXT}` = summary of the above files
- `{REPORT_TEMPLATE_PATH}` = `.ai/audit/templates/audit-findings.md`

*DO NOT* Read executor role or executor tasks and templates, just provide links
*DO NOT* Read production code, full documentation content


## 2. Execute Phase Loop

For each phase file in `{SELECTED_PHASES}` 

<phase_loop>

### 2.1 Extract Phase Metadata
- `{TASK_PATH}` = full path to phase file
- `{PHASE_NUMBER}`, `{PHASE_NAME}` = parsed from filename `NN-audit-name.md`
- `{OUTPUT_PATH}` = `.ai/audit/{PHASE_NUMBER}-{PHASE_NAME}/findings.md`

### 2.2 Launch Executor
Max allowed parallel subagents = 2
```
Task(
  prompt="Read and execute phase task: {TASK_PATH}n"
       + "Write findings to: {OUTPUT_PATH}\n"
       + "Report template: {REPORT_TEMPLATE_PATH}\n"
       + "Base context: {BASE_CONTEXT}\n"
       + "problems_only = TRUE\n",
  agent="auditor",
  mode = "subagent",
  description="Execute audit phase {PHASE_NUMBER} - {PHASE_NAME}"
)
```

### 2.3 Verify Executor Output
Check that `{OUTPUT_PATH}` exists and is not empty.
If missing or empty: retry once, then escalate on second failure.

### 2.4 Launch Validator (skip for Phase 99)

```
Task(
  prompt="Read validation task: .kilo/commands/audit/phases/99-audit-validate.md\n"
       + "Validate findings at: {OUTPUT_PATH}\n"
       + "Write validation report to: .ai/audit/99-validation/{PHASE_NUMBER}-{PHASE_NAME}-validated-findings.md\n"
       + "Base context: {BASE_CONTEXT}\n"
       + "problems_only = TRUE\n",
  agent = "validator",
  mode = "subagent",
  description="Validate phase {PHASE_NUMBER} - {PHASE_NAME}",
)
```

### 2.5 Verify Validation Output
Check that `.ai/audit/99-validation/{PHASE_NUMBER}-{PHASE_NAME}-validated.md` exists.
If missing or empty: retry once, then escalate on second failure.

</phase_loop>

</process>

<output>

---------------------
AUDIT COMPLETE

Phases completed: {N}/{N}
Validated findings: {N} total

By severity:
- CRITICAL: {n}
- HIGH: {n}
- MEDIUM: {n}
- LOW: {n}
---------------------

</output>

<retry_rules>

- Max 2 retry per phase (3 total attempts maximum)
- On second failure: escalate to user with structured failure report (phase number, error, missing outputs)
- Rejected findings cleaned from file before merge
</retry_rules>
