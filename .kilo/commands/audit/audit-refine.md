---
name: audit-refine
description: Execute full multi-agent audit pipeline using orchestrator coordination, executor subagents, and validator subagents with retry logic
agent: audit-orchestrator
alwaysApply: false
---

# Audit Improvement Agent

Process audit files from .ai/audit/99-validation one by one.

## Workflow


## Gather Base Layer Context (once)
Read `.ai/context/commands.md` for verification commands.
Read `AGENTS.md` for project guidelines.
List documentation structure from `docs/` folder.

Set variables:
- `{BASE_CONTEXT}` = summary of the above files
- `{AUDIT_FILES}` = list of files in `.ai/audit/99-validation`

<refine_loop>

## For each {file_path} in {AUDIT_FILES}

### 1. Read the audit file  

### 2. For all findings, recommendations Detect Non-Actionable Recommendations
Select findings where at least one of the following is true:

- The recommendation is vague.
- The recommendation does not specify exactly what should be changed.
- Multiple alternative solutions are proposed without a clear recommendation.
- No implementation approach is provided.
- The proposed fix is incomplete or ambiguous.

{REQUIRE_RESEARCH}

### 3. Launch a sub-agent to resolve Each Non-Actionable Recommendation
 
```
Task(
  prompt="{subagent_prompt}\n"
       + "Append your findings to related issues in: {file_path}\n"
       + "Base context: {BASE_CONTEXT}\n",
  agent="researcher",
  mode = "subagent",
  description="Research phase {file_name}"
)
```

Using prompt bellow:

<subagent_prompt>
The issues require deeper research:
{REQUIRE_RESEARCH}

1. Analyze the current project architecture.
2. Review relevant project documentation.
3. Research current best practices for the project's technology stack.
4. Evaluate available implementation options for each issue.
5. Select a single recommended solution that best fits the existing architecture for each issue.
6. Write a concise implementation recommendation extending the {file_path}.
7. Update the corresponding audit finding with the finalized recommendation {file_path}


## Output Rules

- Modify the audit file {file_path} directly .
- Preserve existing structure and formatting.
- Replace ambiguous recommendations with a single actionable recommendation.
- Do not leave multiple alternatives unless absolutely required.
- Keep recommendations concise, technical, and implementation-oriented.
- Ensure every finding has a clear next action for developers.

<subagent_prompt>

</refine_loop>


## Completion

Process all audit files in the folder until none remain.
Generate a final summary containing:

- Files processed
- Findings updated
- Recommendations clarified
- Any findings that could not be resolved