---
name: docs-audit-tasks-refine
description: docs-audit-tasks-refine
agent: auditor
alwaysApply: false
---

# Task: Align Audit Tasks With Project Specification

## Goal

Review and improve all audit task files so they accurately reflect the current project specification, architecture, and domain logic.

Audit tasks must remain focused on their intended audit scope while becoming more complete, meaningful, and specification-driven.

---

# Source Materials

Study the following project documentation:

* `docs/SPEC.md`
* `README.md`
* `docs/STRUCT.md`
* `docs/**`

Build a clear understanding of:

* system architecture
* domains and subsystems
* backend/frontend boundaries
* data flows
* APIs
* business logic
* infrastructure layers
* testing strategy
* non-functional requirements

---

# Target Files

Process all audit task files:

`.kilo/commands/audit/*.md`

---

# Audit Improvement Cycle

Process files sequentially.

For each audit file:

---

## Step 1. Analyze the Audit File

Determine:

* audit purpose
* audit type:
  * general audit
  * testing audit
  * database audit
  * API audit
  * architecture audit
  * security audit
  * infrastructure audit
  * etc.
* intended scope and boundaries
* covered subsystems/domains

Do not assume the audit is global if it is domain-specific.

---

## Step 2. Map Audit Scope to Specification

Compare the audit against the actual specification and architecture.

Identify:

* missing important areas
* shallow coverage
* specification mismatches
* obsolete checks
* generic/non-domain checks
* areas lacking business-context validation

Validate that the audit reflects:

* real system architecture
* actual domain workflows
* existing modules/subsystems
* current APIs and data flows
* frontend/backend interactions where applicable

---

## Step 3. Evaluate Audit Quality

Verify that the audit:

* correctly covers its target domain
* covers the domain comprehensively
* is sufficiently deep rather than superficial
* produces meaningful engineering findings
* validates real behavior and architecture
* focuses on business and system risks
* avoids purely formal or checkbox-style verification

The audit must verify substance, not documentation appearance.

---

## Step 4. Improve the Audit File

For every identified issue:

* update the appropriate section of the audit file
* keep wording concise and precise
* add missing domain checks
* improve validation depth
* remove weak or generic checks
* replace abstract statements with concrete verification goals

Do NOT:

* turn the audit into a system design document
* add implementation-level logs or low-level technical noise
* duplicate the specification
* over-expand the audit scope beyond its intended focus

Strictly preserve the original audit specialization.

Example:

* test audit → remains test-focused
* DB audit → remains DB-focused
* API audit → remains API-focused

---

# Cross-Layer Validation

Where applicable, ensure the audit covers both frontend and backend aspects, including:

* API contracts
* validation consistency
* state/data flow
* error handling
* permissions/security boundaries
* synchronization between UI and backend behavior

Only include cross-layer checks when relevant to the audit scope.

---

# Expected Result

All audit task files must:

* align with the current project specification
* reflect actual system architecture and domains
* contain meaningful and sufficiently deep audit criteria
* remain specialized and focused
* avoid generic, shallow, or purely formal checks
* stay concise, structured, and actionable