---
name: plan-phase
description: Create detailed execution plan for a phase {file_number} (PLAN_{file_number}.md) with validation loop
argument-hint: "[file_number]"
agent: planner
allowed-tools:
  - read_file
  - write_to_file
  - execute_command
  - list_files
  - search_files
  - new_task
  - browser_action
  - use_mcp_tool
---


<objective>
Create executable phase prompts (PLAN_ {file_number} .md files) for a roadmap phase with integrated research and validation.
</objective>


<process>

## 0. Ask user for a DECISION {file_numbers}  he needs to discuss. 
Stop and wait for the response.


## 1. Preparation
Load {MAIN_CONTEXT} from:

docs/SPEC.md
README.md
docs/*

Summarize it and keep as {MAIN_CONTEXT} 

## 2. Ensure Decisions Directory Exists and Load DECISION_*.md files

Load List of files and their numbers from `.ai/problems/decisions/*`

keep only mentioned by user {file_numbers} (step 0)

## 3. For each file go though steps below one by one:
### 3.1 Get next {file_number} and {short_description}
### 3.2 Load content **CRITICAL:** Store {DECISION_CONTENT} now. It must be passed to:

- **Researcher** — constrains what to research (locked decisions vs KiloCode's discretion)
- **Planner** — locked decisions must be honored, not revisited
- **Checker** — verifies plans respect user's stated vision
- **Revision** — context for targeted fixes

### 3.3 Handle Research

Check for existing research with the same file number:
`.ai/researches/RESEARCH_{file_number}.md`
{file_number} - from previous steps 

**If RESEARCH.md exists**

- Display: `Using existing research: RESEARCH_{file_number}.md`
- Skip to step 3.4 Check Existing Plans 

**If RESEARCH.md missing**

Display stage banner:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RESEARCHING PHASE {X}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
◆ Spawning researcher...
```

Proceed to spawn researcher

### Spawn phase-researcher

Fill research prompt and spawn:

```markdown
<objective>
Research how to implement Phase {file_number} and {short_description}

Answer: "What do I need to know to PLAN this phase well?"
</objective>

<phase_context>
**IMPORTANT:** 
**Decisions section**
{DECISION_CONTENT} = Locked choices — research THESE deeply, don't explore alternatives
- **KiloCode's Discretion section** = Your freedom areas — research options, make recommendations
- **Deferred Ideas section** = Out of scope — ignore completely

</phase_context>

<additional_context>
{MAIN_CONTEXT}
</additional_context>

<output>
IMPORTANT: 
Write research findings to: .ai/researches/RESEARCH_{file_number}.md
</output>
```

```
Task(
  prompt="First, read .kilo/agents/researcher.md for your role and instructions.\n\n" + research_prompt,
  subagent_type="Researcher",
  description="Research Phase {file_number}"
)
```


### Handle Researcher Return

**`## RESEARCH COMPLETE`:**
- Keep {RESEARCH_CONTENT} 
- Display: `Research complete. Proceeding to planning...`
- Continue to step 3.4 Check Existing Plans 

**`## RESEARCH BLOCKED`:**

- Display blocker information
- Offer: 1) Provide more context, 2) Skip research and plan anyway, 3) Abort
- Wait for user response



### 3.4 Check Existing Plans 

**If exists `.ai/plans/PLAN_{file_number}.md`:
** Offer to select:
 1) Continue planning (add more plans)
 2) View existing
 3) Replan from scratch. Wait for response


### 3.5 Spawn planner Agent

Display stage banner:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PLANNING PHASE {X}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

◆ Spawning planner...
```

Fill prompt with inlined content and spawn:

```markdown
<planning_context>

**Phase:** {file_number}

**Requirements (if exists):**
{MAIN_CONTEXT}

**Phase Context (if exists):**

IMPORTANT: If phase context exists below, it contains USER DECISIONS from /discuss-phase.md.

- **Decisions** = LOCKED — honor these exactly, do not revisit or suggest alternatives
- **KiloCode's Discretion** = Your freedom — make implementation choices here
- **Deferred Ideas** = Out of scope — do NOT include in this phase

{DECISION_CONTENT}

**Research (if exists):**
{RESEARCH_CONTENT} 

**Gap Closure (if --gaps mode):**
{validation_content}
{uat_content}

</planning_context>

<downstream_consumer>
Output consumed by /execute-phase.md
Plans must be executable prompts with:

- Frontmatter (wave, depends_on, files_modified, autonomous)
- Tasks in XML format
- validation criteria
- must_haves for goal-backward validation
  </downstream_consumer>

<quality_gate>
Before returning PLANNING COMPLETE:

- [ ] PLAN_{file_number}.md files created in phase directory
- [ ] Each plan has valid frontmatter
- [ ] Tasks are specific and actionable
- [ ] Dependencies correctly identified
- [ ] Waves assigned for parallel execution
- [ ] must_haves derived from phase goal
      </quality_gate>
```

```
Task(
  prompt="First, read .kilo/agents/planner.md for your role and instructions.\n\n" + filled_prompt,
  subagent_type="plan",
  description="Plan Phase {file_number}"
)
```

### 3.6  Handle Planner Return

Parse planner output.


### 3.7  Spawn validation Agent

Display:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VALIDATE PLANS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

◆ Spawning plan checker...
```

Read plan for the checker {PLAN_CONTENT}:
.ai/plans/PLAN_{file_number}.md

Fill checker prompt with inlined content and spawn:

```markdown
<validation_context>

**Phase:** {file_number}

**Plans to validate:**
{PLAN_CONTENT}

**Requirements (if exists):**
{MAIN_CONTEXT}

**Phase Context (if exists):**

IMPORTANT: If phase context exists below, it contains USER DECISIONS from /discuss-phase.md.
Plans MUST honor these decisions. Flag as issue if plans contradict user's stated vision.

- **Decisions** = LOCKED — plans must implement these exactly
- **KiloCode's Discretion** = Freedom areas — plans can choose approach
- **Deferred Ideas** = Out of scope — plans must NOT include these

{DECISION_CONTENT}

</validation_context>

<expected_output>
Return one of:

- ## validation PASSED — all checks pass
- ## ISSUES FOUND — structured issue list
  </expected_output>
```

```
Task(
  prompt=checker_prompt,
  subagent_type="validator",
  description="validate Phase {file_number} plans"
)
```

### 3.8 Handle Checker Return

**If `## validation PASSED`:**

- Display: `Plans verified. Ready for execution.`
- Proceed to step 3.10

**If `## ISSUES FOUND`:**

- Display: `Checker found issues:`
- List issues from checker output
- Check iteration count
- Proceed to step 3.9

## 12. Revision Loop (Max 3 Iterations)

Track: `iteration_count` (starts at 1 after initial plan + check)

**If iteration_count < 3:**

Display: `Sending back to planner for revision... (iteration {N}/3)`

Read current plans for revision context:
{PLANS_CONTENT} 

Spawn planner with revision prompt:

```markdown
<revision_context>

**Phase:** {file_number}
**Mode:** revision

**Existing plans:**
{PLANS_CONTENT}

**Checker issues:**
{STRUCTURED_ISSUES_FROM_CHECKER}

**Phase Context (if exists):**

IMPORTANT: If phase context exists, revisions MUST still honor user decisions.

{DECISION_CONTENT}

</revision_context>

<instructions>
Make targeted updates to address checker issues.
Do NOT replan from scratch unless issues are fundamental.
Revisions must still honor all locked decisions from Phase Context.
Return what changed.
</instructions>
```

```
Task(
  prompt="First, read .kilo/agents/planner.md for your role and instructions.\n\n" + revision_prompt,
  subagent_type="planner",
  description="Revise Phase {file_number} plans"
)
```

- After planner returns → spawn checker again (step 10)
- Increment iteration_count

**If iteration_count >= 3:**

Display: `Max iterations reached. {N} issues remain:`

- List remaining issues

Offer options:

1. Force proceed (execute despite issues)
2. Provide guidance (user gives direction, retry)
3. Abandon (exit planning)

Wait for user response.

## 13. Present Final Status

Route to `<offer_next>`.

</process>

<output>
Output this markdown directly (not as a code block):

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE {X} PLANNED ✓
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**Phase {X}: {Name}** — {N} plan(s) in {M} wave(s)

| Wave | Plans  | What it builds |
| ---- | ------ | -------------- |
| 1    | 01, 02 | [objectives]   |
| 2    | 03     | [objective]    |

Research: {Completed | Used existing | Skipped}
validation: {Passed | Passed with override | Skipped}

</output>

<success_criteria>

- [ ] .gsd/ directory validated
- [ ] Phase validated against roadmap
- [ ] Phase directory created if needed
- [ ] CONTEXT.md loaded early (step 4) and passed to ALL agents
- [ ] Research completed (unless --skip-research or --gaps or exists)
- [ ] phase-researcher spawned with CONTEXT.md (constrains research scope)
- [ ] Existing plans checked
- [ ] planner spawned with context (CONTEXT.md + RESEARCH.md)
- [ ] Plans created (PLANNING COMPLETE or CHECKPOINT handled)
- [ ] plan-checker spawned with CONTEXT.md (verifies context compliance)
- [ ] validation passed OR user override OR max iterations with user decision
- [ ] User sees status between agent spawns
- [ ] User knows next steps (execute or review)
      </success_criteria>
