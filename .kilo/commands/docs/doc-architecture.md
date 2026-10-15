---
name: doc-architecture
description: Explore the Project and Create Product and Architecture Documentation
alwaysApply: false
---


# Task: Explore the Project and Create Product and Architecture Documentation

## 1. Objective

Study the existing project and produce documentation that helps two audiences understand it:

1. **Product owner:** what problem the product solves, who it is for, how users work with it, what happens to the data, and what the intended product behavior should be.
2. **Technical lead or developer:** what the system consists of, what each component is responsible for, how the components relate to one another, how data is processed, and where important rules are implemented.

The documentation must describe both the current implementation and the product owner's intent: what the product is meant to become and why.

Use the following as sources of evidence:
- source code;
- existing documentation;
- tests and usage examples;
- configuration files;
- Git history, when available and useful for understanding changes;
- the product owner's answers to questions raised during the investigation.

Do not infer the author's intent from code alone. When the purpose or desired behavior cannot be established reliably, record the uncertainty and ask the product owner.

## 2. Constraints

This is an investigation and documentation task, not an implementation task.

- Do not modify application code, architecture, dependencies, or business logic.
- Do not fix discovered defects as part of this task.
- Do not install additional dependencies or run potentially destructive operations unless necessary and appropriately authorized.
- You may read code, configuration, tests, and documentation, and run safe checks when their effects are understood and they do not put data at risk.
- If running the application or tests is not possible, continue with static analysis and clearly state the limitation.
- Do not claim that runtime behavior has been verified if you only inspected the relevant code.
- Do not delete existing documentation. Inspect it first, then supplement or update it consistently.
- Do not describe assumed functionality as already implemented.
- Do not make product decisions on behalf of the owner.

## 3. Investigation Principles

### 3.1. Support important claims with evidence

For every important conclusion, identify its source:
- file path;
- function, class, command, or configuration key;
- line range when useful;
- a test that supports the behavior, if one exists.

For external documents, link to the relevant existing project materials.

### 3.2. Distinguish levels of certainty

In working notes and documentation, distinguish between:

- **Confirmed by code:** the behavior can be directly traced through the implementation.
- **Covered by a test:** a test specifies or checks the behavior. State separately whether the test was actually run.
- **Confirmed by the product owner:** the owner explicitly explained or approved the requirement.
- **Assumption:** a possible explanation that has not been confirmed.
- **Open question:** additional information is required to reach a conclusion.

If the code, tests, README, and owner's answers contradict one another, do not silently choose one source. Describe the discrepancy and its implications.

### 3.3. Describe behavior, not just file structure

Do not limit the analysis to lists of classes and functions.

For each important scenario, determine:
1. Who or what initiates the operation.
2. What input data is supplied.
3. What validations are performed.
4. What transformations and business rules are applied.
5. Which components participate and how they pass data to each other.
6. What result is produced and where it goes.
7. What happens when data is invalid, configuration is missing, or another error occurs.
8. Which parts of the behavior are confirmed and which remain uncertain.

Verify component relationships by following actual calls, arguments, and return values. Do not infer interactions solely from component names or import statements.

## 4. Work Stages

### Stage 1. Project inventory

Inspect:
- repository and directory structure, including the purpose of important files;
- README and other existing documentation;
- entry points, such as public functions, CLI commands, APIs, UI entry points, scheduled jobs, or other ways to run the system;
- dependencies and configuration;
- tests, sample data, and fixtures;
- key data models, formats, and storage locations.

Create a concise project map: the main parts, their apparent responsibilities, and the files where their implementation lives.

Do not describe every file mechanically. Focus on the parts needed to understand the product, its behavior, and its data flows.

### Stage 2. Reconstruct current behavior

Identify and trace the main scenarios supported by the current implementation.

Depending on the project, investigate:
- how a user or another system initiates an operation;
- how configuration and prerequisites are prepared;
- where input data comes from and what formats it uses;
- how data is read, validated, transformed, matched, enriched, or persisted;
- where business rules are implemented;
- how missing, invalid, duplicate, unexpected, or unrecognized values are handled;
- which intermediate and final outputs are produced;
- how errors and results are surfaced to users or calling systems;
- which files, databases, settings, external services, or other resources are changed.

For every significant scenario, trace the path from its entry point to its result and, where applicable, to error handling.

Document limitations only when supported by code, tests, or other evidence. Do not conclude that functionality is absent merely because you have not found its implementation yet.

### Stage 3. Analyze the architecture and component relationships

Identify:
- the major logical components;
- the responsibility of each component;
- dependencies and call direction;
- public interfaces versus internal implementation details;
- interactions with files, databases, configuration, external services, or other systems;
- execution flow for key operations;
- error handling and significant side effects;
- shared rules, cross-cutting mechanisms, and common configuration.

Create simple Mermaid diagrams where they improve understanding.

At minimum, prepare:
1. A system context diagram showing external actors and systems, where applicable.
2. A component diagram showing the main components and their relationships.
3. A data-flow diagram showing how inputs become outputs.
4. A sequence diagram for one or two key scenarios, including an important error path if relevant.

Avoid unnecessarily complex UML. Diagrams should be understandable to someone who is not familiar with the codebase.

### Stage 4. Draft documentation of the current state

Based on confirmed findings, draft the documents described in Section 5.

Describe what is implemented today. Where behavior is unclear or sources conflict, do not invent an explanation; link the uncertainty to a relevant question in the open-questions register.

At this stage, do not present assumed target behavior as an approved product requirement.

### Stage 5. Ask the product owner questions

After inspecting the code, prepare a list of important questions that cannot be answered reliably from the repository alone.

Questions should concern the product and its behavior, not require the owner to understand architecture, libraries, or implementation details.

Examples of useful question areas:
- What user problem is a particular processing step intended to solve?
- What does a specific field or value mean in the input data?
- What makes the data valid from the user's point of view?
- What should happen to records or requests that cannot be processed or interpreted?
- Under what circumstances should processing stop, and when should it continue with a warning?
- What result should the user receive, and how will it be used downstream?
- Which limitations are intentional, and which are not yet decided?
- Is the product intended to remain a standalone application or become a reusable step in a larger workflow?

These are examples, not a mandatory questionnaire. Ask only questions tied to specific uncertainties found during the investigation.

For each question, explain:
1. What the code or documentation currently reveals.
2. What remains unclear.
3. Why the answer matters to product behavior.
4. The question in plain, neutral language.
5. Clear alternatives where useful, without implying that one is automatically correct.

Do not ask the owner about details that can be established from the repository. Avoid asking the owner to choose libraries or classes unless the choice directly affects the product's behavior or constraints.

Prioritize questions by their impact on understanding the product and the risk of implementing the wrong behavior. Ask questions interactively, preferably one at a time, and allow the owner to clarify an answer. Do not finalize the target behavior for a topic until the owner has answered.

If there are many questions, start with the most consequential ones: product purpose, data-processing rules, behavior in ambiguous cases, expected outputs, and intended ways of using the product.

### Stage 6. Document the target product

After receiving the owner's answers, update the documentation to describe:
- the problem the product is intended to solve;
- primary users and their goals;
- key user scenarios;
- expected behavior for valid and invalid inputs;
- confirmed data-processing rules;
- the purpose of outputs and who or what consumes them;
- constraints and explicitly out-of-scope scenarios;
- criteria for deciding whether the product behaves as intended.

Keep these requirements distinct from the current implementation.

If desired behavior differs from the code, document the discrepancy as a gap between the current implementation and the owner's intent. Do not fix it as part of this task.

If the owner has not answered a question, keep it open. Do not fill the gap with a guess.

### Stage 7. Validate and finish

After interviewing the owner and updating the documentation:
- check that descriptions of current behavior match the implementation;
- check that descriptions of target behavior match the owner's answers;
- recheck important component relationships;
- verify that source paths and links are valid;
- compare key scenario descriptions with available tests;
- identify tests that were inspected but not run;
- ensure that assumptions and open questions are not presented as facts;
- check terminology for consistency across all documents.

Prepare a final report listing the documents created or updated, the findings, discrepancies, owner-confirmed decisions, remaining open questions, investigation limitations, and recommended next steps.

## 5. Recommended Deliverables

Create documentation in `docs/`, after first inspecting the existing documentation structure. Do not create duplicate documents if suitable ones already exist.

### `docs/PRODUCT.md` — Product purpose and target behavior

Describe:
- the problem the product solves and why it matters;
- who uses it;
- the main jobs users need to accomplish;
- key user scenarios;
- expected outputs and who uses them;
- owner-confirmed intent;
- constraints, non-goals, and success criteria;
- unresolved product questions.

Write primarily in the language of users and the relevant domain. Include technical details only when they help explain product behavior.

### `docs/CURRENT_BEHAVIOR.md` — How the project works today

Describe:
- available entry points and ways to run the system;
- main operations and scenarios;
- expected inputs;
- observable transformations and processing rules;
- outputs;
- errors, warnings, and edge cases;
- configuration that affects behavior;
- discovered limitations and unverified areas.

Support important factual claims with links to the relevant source code or tests.

### `docs/DATA_FLOW.md` — Data movement and transformation

Describe:
- where data comes from and its formats;
- the structure and purpose of key files, tables, fields, or messages;
- which transformations occur and in what order;
- validation, matching, enrichment, or processing rules;
- how missing values, duplicates, unknown values, and errors are handled;
- which intermediate and final outputs are created;
- what is known about data provenance and preservation of original values;
- which rules are confirmed, assumed, or awaiting the owner's input.

Do not invent the business meaning of fields or rules based only on technical names.

### `docs/ARCHITECTURE.md` — Technical architecture

Describe:
- the system context;
- the purpose of major components;
- relationships and call direction;
- public interfaces and entry points;
- configuration and external dependencies;
- execution flow for key scenarios;
- interactions with file systems, databases, and external services;
- significant technical limitations, risks, and known trade-offs.

Include clear Mermaid diagrams and links to important implementation locations. Do not turn this document into an exhaustive list of every class and file.

### `docs/OPEN_QUESTIONS.md` — Questions, gaps, and decisions

Track:
- questions for the product owner;
- answers and decisions made by the owner;
- discrepancies between code, documentation, and owner intent;
- assumptions that require validation;
- known product and technical limitations;
- unresolved topics.

For every significant item, record its status and impact on the product. When a question is answered, preserve the decision and its rationale rather than simply deleting the question.

If the project already uses a different documentation structure, adapt these suggestions to it and avoid unnecessary duplication.

Update the README only as needed to link to the new documentation and explain where readers should start.

## 6. Documentation Quality Requirements

The final documentation must:
- begin with a clear explanation of the product's purpose;
- be useful to both the product owner and technical specialists;
- explain why major components exist and how they interact;
- describe concrete data flows and processing rules;
- include examples and diagrams where they materially improve understanding;
- reference code, tests, and confirmed decisions;
- clearly distinguish current behavior, target behavior, and assumptions;
- make defects, contradictions, and requirements gaps visible;
- use consistent terminology throughout;
- avoid unsupported business rules;
- remain concise enough for a small or medium-sized project.

Do not create a complete formal architecture-documentation suite, document every module, or introduce a new specification-management system unless the project clearly needs one.

## 7. Acceptance Criteria

The task is complete when:

1. The documentation clearly explains the product's purpose and how users are expected to use it.
2. The main real-world scenarios supported by the current implementation are documented from input to output.
3. The reader can understand which components participate in those scenarios, what each is responsible for, and how they relate.
4. Key data-transformation rules and important error-handling behavior are documented.
5. Significant technical claims are supported by links to source code or tests.
6. Current behavior is separated from target behavior and assumptions.
7. The product owner has been asked specific questions about unclear product rules and data interactions.
8. The owner's answers have been incorporated; unanswered questions remain explicitly open.
9. Gaps between owner intent and implementation are documented, but application code has not been changed.
10. Another developer can use the documentation to begin understanding the project without having to reread the entire repository from scratch.
11. The final report lists deliverables, investigation limitations, findings, and recommended next steps.

Begin with Stage 1. Do not modify application code. First reconstruct and substantiate the current state, then ask the owner for clarification where needed, and only afterward finalize the documentation of the target product.
