# Task: HTMX 2.x Compatibility Audit

## Objective

Audit all HTMX 1.9.x usage in the Mko Bazuna codebase and determine the feasibility, risks, scope, and migration steps required to upgrade to HTMX 2.x.

The output must distinguish between:

1. APIs that are unchanged and require no migration.
2. APIs that are deprecated or behaviorally changed.
3. APIs that were removed and require code changes.
4. Extensions/integrations that require separate compatibility work.

C:\py_dev\mko_bazuna\.ai\audit\problems\{next-free-number}_htmx_report.md

## Context

PO-5 decision: upgrade HTMX to 2.x rather than patching the existing `htmx.get` usage with `htmx.ajax`.

Before engineering work on T8 (B6 fix) proceeds, we need a compatibility report establishing the actual HTMX 1.9 → 2.x migration impact.

## Scope

Audit the entire repository, including all `.html` templates and any JavaScript embedded in templates.

### 1. JavaScript API inventory

Find every occurrence of the following HTMX APIs:

* `htmx.get`
* `htmx.post`
* `htmx.ajax`
* `htmx.extend`
* `htmx.on`
* `htmx.config`
* `htmx.swap`

Also search for:

* `htmx.trigger`
* `htmx.process`
* `htmx.find`
* `htmx.findAll`
* `htmx.remove`
* `htmx.addClass`
* `htmx.removeClass`
* `htmx.toggleClass`
* `htmx.takeClass`
* `htmx.closest`
* `htmx.values`
* `htmx.defineExtension`
* `htmx.logger`

Do not assume the initially listed APIs are the complete surface area.

For every occurrence record:

* file path
* line number
* API used
* short description of usage
* whether migration is required
* migration notes

### 2. HTMX HTML attribute inventory

Audit HTMX attributes across all templates, including:

* `hx-get`
* `hx-post`
* `hx-put`
* `hx-patch`
* `hx-delete`
* `hx-trigger`
* `hx-target`
* `hx-swap`
* `hx-select`
* `hx-select-oob`
* `hx-swap-oob`
* `hx-push-url`
* `hx-replace-url`
* `hx-boost`
* `hx-confirm`
* `hx-sync`
* `hx-include`
* `hx-vals`
* `hx-headers`
* `hx-indicator`
* `hx-disabled-elt`
* `hx-preserve`
* `hx-history`
* `hx-history-elt`
* `hx-disinherit`
* `hx-inherit`
* `hx-encoding`
* `hx-ext`

Identify attributes whose semantics, defaults, inheritance rules, or supported values changed between HTMX 1.9.x and 2.x.

### 3. Breaking-change investigation

Compare the exact HTMX 1.9.x documentation/API with HTMX 2.x documentation and changelog.

Explicitly investigate:

* `htmx.ajax()` availability and API/signature in HTMX 2.x
* `htmx.get()` / `htmx.post()` behavior and signatures
* `htmx.config` changes
* `htmx.swap()` API/signature changes
* event API changes
* extension API changes
* removed/deprecated APIs
* changed defaults
* changed request/swap behavior
* changed DOM-processing behavior
* changes affecting CSP/module usage, if applicable
* browser-support changes
* changes affecting existing template attributes

**Important:** Do not assume that an API is removed merely because a secondary source says so. Verify each breaking-change claim against authoritative HTMX 2.x documentation/changelog.

In particular, verify the claim:

> `htmx.ajax()` removed → `htmx.ajaxRemoved()` + new API

and report whether this claim is actually correct. If incorrect, explicitly state the correct HTMX 2.x behavior.

### 4. Extension compatibility

Inventory all HTMX extensions used by the codebase, including values referenced through `hx-ext` and any JavaScript extension registration/loading.

For each extension determine:

* extension name
* version currently used, if discoverable
* HTMX 1.9 compatibility
* HTMX 2.x compatibility
* whether an upgrade is required
* migration risk
* relevant documentation/changelog reference

Pay particular attention to WebSockets, SSE, response-targets, morphing, Alpine integrations, or any project-specific/custom extensions.

### 5. Template impact

Produce an inventory of files affected by the migration.

For every affected file include:

`path:line — usage — impact — required change`

Provide totals for:

* number of affected files
* number of affected JavaScript call sites
* number of affected HTMX attributes
* number of affected extensions
* number of changes requiring manual engineering work

Separate "usage exists" from "usage requires migration".

### 6. Risk assessment

Rank each identified compatibility issue:

* **High** — likely to break production behavior or requires substantial code changes.
* **Medium** — localized code changes or meaningful behavioral validation required.
* **Low** — no/low code impact, documentation-only change, or easily validated compatibility.

For each risk include:

* affected API/feature
* evidence
* affected files/call sites
* expected failure mode
* recommended mitigation
* confidence level

### 7. Engineering effort

Estimate migration effort using T-shirt sizing:

* **S** — straightforward upgrade, limited code changes
* **M** — several localized changes and regression testing
* **L** — significant API/extension changes or broad template impact

Provide both:

1. effort for the HTMX version upgrade itself;
2. effort for resolving repository-specific incompatibilities.

Do not estimate effort based solely on the number of call sites; account for extension compatibility and behavioral testing.

### 8. Migration strategy

Recommend a concrete upgrade strategy.

Evaluate:

* direct upgrade from HTMX 1.9.x → 2.x
* dual-version support
* feature flag / staged rollout
* compatibility shim, if appropriate
* test-first migration

For this codebase, recommend the simplest strategy that provides adequate safety.

Include a step-by-step migration plan covering:

1. Freeze/inventory current HTMX usage.
2. Verify all third-party/custom extensions.
3. Update HTMX dependency.
4. Apply required API/template changes.
5. Run automated tests.
6. Exercise HTMX interactions manually/integration tests.
7. Validate browser behavior.
8. Remove temporary compatibility code, if any.
9. Deploy/roll out.

Do not recommend dual-version support or a feature flag unless the audit identifies a concrete reason they are necessary.

## Sources

Use authoritative HTMX sources as the primary reference:

* HTMX documentation: https://htmx.org/docs/
* HTMX API documentation
* HTMX 1.x documentation/changelog
* HTMX 2.x documentation/changelog
* Official HTMX extension documentation/repositories where applicable

The audit must first establish the current 1.9.x behavior and then compare it against HTMX 2.x.

Do not rely on blog posts or Stack Overflow as the primary evidence for breaking-change claims.

## Constraints

* **Do NOT make any code changes.**
* Only inspect and analyze the repository.
* Do not modify templates, JavaScript, dependencies, package files, or configuration.
* Verify breaking-change claims against authoritative documentation.
* Clearly distinguish verified facts from assumptions.
* Include exact file paths and line numbers for repository findings.

## Deliverable

Create exactly one file:

`.ai/research/htmx-2x-migration-audit.md`

The report should contain:

1. Executive summary
2. Current HTMX version and loading mechanism
3. HTMX JavaScript API inventory
4. HTMX template attribute inventory
5. Extension inventory
6. HTMX 1.9 → 2.x compatibility matrix
7. Breaking changes ranked by severity
8. Affected files and call sites
9. Engineering effort estimate
10. Recommended migration strategy
11. Step-by-step migration plan
12. Open questions / uncertainties
13. Source references

## Acceptance Criteria

The audit is complete when:

* Every occurrence of the specified `htmx.*` APIs has been identified.
* HTMX attributes and extensions have also been audited.
* Every claimed breaking change has an authoritative source.
* The `htmx.ajax()` removal claim has been explicitly verified or corrected.
* Affected files include exact path and line numbers.
* Risks are ranked High/Medium/Low with rationale.
* Engineering effort has an S/M/L estimate.
* A concrete migration strategy is recommended.
* No repository files other than `.ai/research/htmx-2x-migration-audit.md` are modified.
