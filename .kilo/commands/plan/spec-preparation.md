---
name: spec-preparation
description: Analyze a product request, resolve ambiguities, coordinate research and produce a development-ready specification.
---

# Objective

Convert a business request into a complete analytical specification.

## Workflow

0. Ask User to provide the context: problem definition, the file path with decisions or problem description.  

1. Analyze the request and summarize:
   - business goal
   - scope
   - constraints
   - assumptions

2. Break the work into independent conceptual development tasks.
   For each task describe:
   - purpose
   - expected outcome
   - dependencies

3. Identify gray areas - ambiguities that prevent accurate specification.

- undefined business rules
- unclear user behavior
- missing edge cases
- conflicting requirements
- acceptance ambiguity
- incomplete workflows
- integration uncertainty

Separate gray areas from confirmed requirements.

4. Ask user as the Product Owner only the questions required to resolve business uncertainty.
Provide questions with options to choose basing on the best practices and highlight recommended options. 

Questions should focus on:
- product behavior
- business rules
- priorities
- user expectations
- acceptance criteria

Do not ask about technical implementation.

Collect answers for the the specification.

5. Create Researcher tasks for every significant investigation.

   Research instructions must require the Researcher to:
   - investigate the current architecture relevant to the problem;
   - investigate modern best practices for solving the problem based on the existing architecture;
   - identify feasible implementation approaches;
   - if multiple approaches exist, describe the top 2–3 and clearly recommend the preferred option with rationale.

6. Review research results.
   If findings are weak, incomplete, inconsistent, or unsupported by evidence, launch additional Researcher tasks until the result is actionable.

7. Produce the final analytical specification containing:
   - problem statement
   - confirmed requirements
   - conceptual development tasks
   - Product Owner decisions
   - research summary
   - assumptions
   - constraints
   - risks
   - open questions
   - out of scope
   - definition of ready

  Save to `.ai\problems\{next_free_number}_{problem_name}_spec.md`