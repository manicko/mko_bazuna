---
name: audit-orphaned
description: Identify files in the repository that are genuinely unused, orphaned, or accidental leftovers
alwaysApply: false
---

# Task: Audit for Truly Unused / Orphaned Files

## Objective

Identify files in the repository that are genuinely unused, orphaned, or accidental leftovers and can safely be considered for removal.

Strictly distinguish them from files that are intentionally unreferenced but still required by the project.

## Scope

Focus on potential leftovers such as:

* One-off scripts.
* Old experiments.
* Temporary/log/backup files.
* Dead modules.
* Unused assets.
* Stale test fixtures.
* Other accidental repository artifacts.

Protect and exclude from the removal candidates:

* Documentation.
* Configuration and tooling.
* Entry points and externally invoked scripts.
* Migrations, seeds, fixtures, and generated files.
* Files referenced dynamically or through non-code mechanisms.
* Files required by CI, Docker, package managers, build tools, templates, or external integrations.

## Analysis Method

Use multiple signals; never rely on a single check.

1. **Dependency / reachability analysis**

   * Identify project entry points.
   * Build or inspect the dependency graph.
   * Identify files unreachable from known entry points.

2. **Repository-wide reference search**

   * Search for filename, relative path, file stem, exported symbols, and relevant string references.
   * Check code, tests, configuration, scripts, templates, and CI.

3. **Project tooling**

   * Use appropriate static-analysis/dead-code tools available for the stack.
   * Configure entry points and project boundaries correctly before trusting results.
   * Treat configuration gaps and dynamic imports as potential false positives.

4. **Git history**

   * Check creation / last modification dates and meaningful historical usage.
   * Recent or frequently changed files require higher scrutiny.
   * History is supporting evidence, not proof of unused status.

5. **Project conventions**

   * Check naming patterns, special directories, generated artifacts, conventions, and external usage.

## Classification

Classify findings by confidence:

* **High confidence** — strong evidence that the file is genuinely unused and safe to propose for removal.
* **Medium confidence** — likely unused, but requires human review.
* **Low confidence** — possible dynamic/external/special usage; do not propose for deletion.

Prefer false negatives over false positives.

## Deliverable

Output path for the report:`.ai/audit/orphaned-files/report.md`

Produce two tables.

### Table 1 — File-level Findings

Sort primarily by **folder path alphabetically**, then by file path.

| Folder | File Path | Extension | Created | Last Modified | Confidence | Why Considered Unused | Evidence / Checks                      | Action        |
| ------ | --------- | --------- | ------- | ------------- | ---------- | --------------------- | -------------------------------------- | ------------- |
| ...    | ...       | ...       | ...     | ...           | High       | ...                   | No imports, no references, unreachable | Review/Delete |

Use **Created** and **Last Modified** as supporting metadata only.

The most important fields are **Confidence**, **Reason**, **Evidence / Checks**, and **Action**.

### Table 2 — Extension Summary

Group findings by file extension to identify patterns.

| Extension | Candidate Files | High Confidence | Medium/Low Confidence | Common Reasons      |
| --------- | --------------: | --------------: | --------------------: | ------------------- |
| `.log`    |             ... |             ... |                   ... | Temporary artifacts |
| `.ts`     |             ... |             ... |                   ... | Unreachable modules |
| ...       |             ... |             ... |                   ... | ...                 |

## Additional Output

Include:

* Protected / excluded categories and why.
* Borderline cases requiring human review.
* Any limitations of static analysis.
* Recommended next step for each high-confidence candidate: **delete / archive / keep**.

Do not delete files as part of this task unless explicitly requested.

## Constraints

* Do not recommend deletion solely because a file has no code import.
* Do not treat missing textual references as conclusive evidence.
* Do not remove or flag configuration, documentation, generated, or externally used files without strong evidence.
* Do not dump every unreferenced file; provide a curated, actionable report.
* Base conclusions on the current repository state plus Git history.
* When in doubt, classify as **Medium/Low confidence** rather than recommending deletion.
