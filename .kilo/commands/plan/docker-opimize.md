# Task: Optimize Docker Build Performance via Proper Ignore Rules

Analyze the Docker build inputs and related ignore/exclusion rules to identify unnecessary files, packages, caches, and artifacts that increase Docker build context or image size, and produce a verified, dependency-aware implementation plan.

The orchestrator **must not perform repository inspection, measurement, profiling, or deep research itself**. Its role is to **delegate work to specialized agents, enforce the workflow order, synthesize structured agent reports, and produce the final implementation plan**.

All repository analysis, best-practice research, risk assessment, and validation must be delegated to the designated agents.

## Step 1. Baseline Current State

**Agent:** `researcher`

Delegate analysis of the current architecture and codebase.

The agent must identify **every relevant file/configuration** where Docker build inputs, ignore rules, inclusion/exclusion rules, or recursive file processing are defined, including where applicable:

* `.dockerignore`
* `.gitignore`
* Dockerfiles and `COPY` / `ADD`
* dependency definitions (`requirements*`, Poetry, etc.)
* Django settings / management commands
* build scripts / Makefiles / CI scripts
* tooling that recursively scans project files

The report must identify the current behavior and relevant dependencies, without proposing speculative changes.

## Step 2. Research Best Practices

**Agent:** `researcher`

For every identified configuration/file, research modern best practices relevant to the project's stack and workflow.

Focus exclusively on:

* minimizing Docker build context
* excluding local/dev/test artifacts
* avoiding unnecessarily broad `COPY . .`
* separating build-time and runtime dependencies
* preventing package-manager caches and temporary files from entering images
* multi-stage builds and layer cleanup where applicable
* preventing related tooling from recursively processing unnecessary files

Provide concrete, applicable examples and explain which practices are relevant to the current architecture.

## Step 3. Audit Current State

**Agent:** `auditor`

Using the reports from Steps 1–2, audit the current implementation.

Classify findings as:

* correctly implemented
* missing
* suboptimal

Keep **only actionable improvements** that can affect Docker build performance, build context size, image contents, packages, caches, artifacts, or related tooling.

In particular, assess:

* `.dockerignore` completeness
* overly broad `COPY` / `ADD`
* unnecessary files entering the image
* dev/test/build dependencies in runtime images
* package-manager caches and build artifacts
* duplicated or inconsistent ignore rules
* recursive tooling such as `compilemessages`

Discard noise and unrelated refactoring.

## Step 4. Assess Risks and Implementation Options

**Agent:** `researcher`

For **each candidate improvement** produced by Step 3, assess:

* risks and possible breakage
* side effects
* downstream impact
* development and CI implications
* compatibility with the existing architecture
* preferred implementation approach
* viable alternatives, where relevant

The agent must base recommendations on the actual repository state and avoid speculative work.

## Step 5. Independently Validate Candidate Approaches

**Agent:** `researcher`

For **each candidate improvement**, independently verify the proposed implementation approach.

Focus on:

* whether the change actually reduces unnecessary Docker context/image contents
* whether required runtime/build files remain available
* dependency implications
* interaction with Docker build layers and caching
* interaction with Django/build tooling
* whether a lower-risk alternative exists

Return a structured recommendation for each candidate.

## Step 6. Build Dependency-Aware Implementation Plan

**Agent:** `planner`

Using all previous agent reports, create a dependency-aware implementation plan.

The plan must organize changes around:

1. **Docker Build Context** — exclude unnecessary files and directories before they reach the build context.
2. **Dockerfile Inputs** — narrow overly broad `COPY` / `ADD` instructions where justified.
3. **Runtime Dependencies** — prevent dev/test/build-only packages from entering production images.
4. **Build Artifacts and Caches** — prevent or remove package-manager caches, temporary files, and generated artifacts.
5. **Related Tooling** — prevent commands such as `compilemessages` from recursively processing irrelevant directories.

For every planned change, specify:

* exact file(s)
* required modification
* rationale
* dependencies/order
* risk considerations
* validation criteria

Output path:

`C:\py_dev\mko_bazuna\.ai\plans`

## Step 7. Validate the Implementation Plan

**Agent:** `validator`

Critically review the complete plan for:

* completeness
* correctness
* safety
* architectural fit
* dependency ordering
* risk coverage
* measurable impact on Docker build context/image contents
* preservation of required functionality
* absence of speculative work

Identify concrete deficiencies or required corrections.

## Step 8. Refine the Final Plan

**Agent:** `planner`

Using the Validator report, refine the implementation plan.

The final plan must:

* incorporate all justified corrections
* preserve the strict scope of this task
* maintain dependency-aware ordering
* clearly distinguish context exclusions from image exclusions
* distinguish build-time dependencies from runtime dependencies
* include validation criteria for each change
* contain no unresolved speculative work

The refined plan must be written to:

`C:\py_dev\mko_bazuna\.ai\plans`

## Orchestrator Responsibilities

The orchestrator must:

* execute the steps in the exact order above
* delegate all substantive work to the specified agents
* pass relevant structured reports between agents
* ensure each agent receives the necessary context from previous steps
* reject unsupported or speculative findings
* synthesize the final result from agent reports
* ensure the final plan is internally consistent and dependency-aware

The orchestrator must **not** independently inspect the repository, perform measurements, conduct deep research, or make implementation decisions that should be delegated to an agent.

## Constraints

* Focus exclusively on Docker build performance, build context size, image size, included packages/artifacts, and related ignore/exclusion tooling.
* Prefer incremental, low-risk changes.
* Preserve the existing architecture.
* No speculative work.
* Every proposed change must be supported by repository evidence or verified best practice.
* Distinguish clearly between:

  * files that should not enter the **build context**
  * files that may enter the context but should not enter the **image**
  * dependencies required only at **build time**
  * files that related tooling should not recursively process
