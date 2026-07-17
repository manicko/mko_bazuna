---
name: discuss-phase
description: Gather context through adaptive questioning before planning
argument-hint: "<file_number>"
allowed-tools:
  - read_file
  - write_to_file
  - execute_command
  - list_files
  - search_files
  - ask_followup_question
  - execute_command
  - new_task
  - browser_action
  - use_mcp_tool
---

## Objective

Extract implementation decisions that downstream agents need. Produce `DECISION_{file_number}.md` so researcher and planner can act without re-asking the user.

## Input

- `CONTEXT_{file_number}.md` — phase description and requirements
- `AGENTS.md`, project rules, README.md, SPEC.md — project context

## Output

- `DECISION_{file_number}.md` — locked decisions, KiloCode discretion areas, deferred ideas

## Steps

1. Ask user for the CONTEXT file number(s) to discuss. Wait for response.
2. Load `CONTEXT_{file_number}.md` from `.ai/problems/`.
3. Check if `DECISION_{file_number}.md` already exists — offer update/view/skip.
4. Analyze the phase goal and generate 3-4 phase-specific gray areas (not generic categories).
5. Present gray areas as multi-select — user chooses which to discuss. No skip option.
6. Deep-dive each selected area — ask 4 questions per area, then offer more/next.
7. Write `DECISION_{file_number}.md` with sections matching discussed areas.
8. Offer next steps (research or plan).

## Scope Guardrail

- Discussion clarifies **HOW** to implement, not **WHETHER** to add more.
- If user suggests new capabilities → "That's its own phase. I'll note it for later."
- Capture deferred ideas — don't lose them, don't act on them.

## Domain-Aware Gray Areas

Gray areas depend on what's being built:

- Something users **SEE** → layout, density, interactions, states
- Something users **CALL** → responses, errors, auth, versioning
- Something users **RUN** → output format, flags, modes, error handling
- Something users **READ** → structure, tone, depth, flow
- Something being **ORGANIZED** → criteria, grouping, naming, exceptions

## What NOT to Ask About

KiloCode handles these — don't ask the user:

- Technical implementation details
- Architecture choices
- Performance concerns
- Scope expansion

## Success Criteria

- Gray areas identified through intelligent analysis
- User chose which areas to discuss
- Each selected area explored until satisfied
- Scope creep redirected to deferred ideas
- `DECISION_{file_number}.md` captures decisions, not vague vision
- User knows next steps
