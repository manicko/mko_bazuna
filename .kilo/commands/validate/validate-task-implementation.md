---
name: validate-task-implementation
description: Audit completed implementation tasks for correctness, architectural safety, rollout integrity, and production readiness
agent: validator
alwaysApply: false
---

# Implementation Audit Workflow

## Step 0 — Ensure Docker Environment is Running

Start Docker services in **both development and test modes** (never production) before executing any test or verification commands. Follow the setup instructions in `docs/11-guides/docker.md`. Confirm all required containers are in `running` or `healthy` state before proceeding. If the environment cannot be started, document why and skip dependent steps.

## Objective

Audit completed implementation tasks to ensure:
- implementation correctness
- architectural consistency
- production readiness
- semantic integrity
- rollout safety
- maintainability
- requirement completeness
- doc updates were applied (when tasks included doc changes)

Detect:
- incomplete implementations
- regressions
- architectural violations
- hidden side effects
- unsafe changes
- stale assumptions
- partial rollouts
- broken contracts
- missing doc updates (code changed but docs weren't updated)

Provide:
- detailed audit findings
- required fixes
- quality assessment
- risk analysis
- execution verdict
- separated: mandatory rework vs advisory improvements

---

# Constraints

- DO NOT implement fixes
- DO NOT modify source code
- DO NOT redesign architecture
- DO NOT rewrite completed tasks
- Prefer conservative auditing
- Prefer reporting risks over assuming correctness
- Focus on factual validation only
- All findings must be evidence-based

---

# Workflow

## Step 1 — Load Context

Study:
- original task specifications in `.ai/tasks/done/*`
- validated findings
- dependency graph
- architecture documentation
- semantic anchor maps
- rollout ordering
- acceptance criteria
- implementation requirements

Understand:
- intended behavior
- expected architecture boundaries
- rollout expectations
- dependency constraints

---

## Step 2 — Load Completed Implementations

Study:
- modified files
- implementation diffs
- related commits
- updated dependencies
- configuration changes
- migrations
- tests
- rollout changes

Analyze:
- actual implementation scope
- affected systems
- integration surface
- hidden side effects

---

## Step 3 — Validate Implementation Completeness

Validate:
- all task requirements implemented
- acceptance criteria satisfied
- no partially completed logic
- no missing integrations
- no skipped edge cases
- no placeholder implementations
- no TODO/FIXME leftovers

Detect:
- incomplete flows
- dead code
- orphaned logic
- unconnected features
- partially migrated behavior

---

## Step 4 — Validate Architectural Integrity

Validate:
- architecture boundaries preserved
- dependency direction remains correct
- layering consistency maintained
- no hidden coupling introduced
- no architecture drift
- modularity preserved

Reject:
- cross-layer leakage
- tightly coupled additions
- business logic inside UI/infrastructure
- unsafe dependency shortcuts
- violation of clean architecture principles

---

## Step 5 — Validate Semantic Safety

Validate:
- semantic targets remain stable
- symbol references remain valid
- integrations remain deterministic
- lifecycle boundaries preserved
- transaction boundaries respected

Detect:
- fragile implementations
- unsafe assumptions
- unstable integrations
- hidden execution paths
- semantic ambiguity

---

## Step 6 — Validate Code Quality

Validate:
- implementation readability
- maintainability
- naming clarity
- typing correctness
- proper abstraction levels
- predictable control flow
- explicit behavior

Detect:
- overengineering
- duplicated logic
- magic values
- hidden side effects
- unnecessary complexity
- weak typing
- unclear responsibilities

Validate standards:
- comments/logs in English
- comments only for non-trivial logic
- reusable patterns preferred
- no inconsistent implementation styles

---

## Step 7 — Validate UX/UI Consistency

Validate:
- responsive behavior
- accessibility
- loading/error/empty states
- interaction consistency
- design system alignment
- predictable user flows

Detect:
- broken UX flows
- inconsistent UI behavior
- visual regressions
- accessibility issues
- unstable interactions

Reject:
- unclear user feedback
- inconsistent state handling
- fragile UI logic

---

## Step 8 — Validate Reliability and Safety

Validate:
- error handling
- rollback safety
- backward compatibility
- migration safety
- state consistency
- API contract stability

Detect:
- unsafe mutations
- race conditions
- inconsistent state transitions
- unhandled failures
- fragile async flows
- breaking API changes

---

## Step 9 — Validate Tests and Verification

Validate:
- tests reflect actual behavior
- tests cover critical flows
- acceptance criteria verified
- integration points validated
- edge cases tested

Detect:
- outdated tests
- meaningless assertions
- missing coverage
- false-positive tests
- implementation-test mismatch

Important:
- code correctness has priority over outdated tests
- if implementation is correct and tests are obsolete, report test fixes instead of implementation rollback

---

## Step 10 — Validate Rollout Readiness

Validate:
- implementation safe for rollout
- dependencies deployed in correct order
- feature flags handled safely
- configuration consistency maintained
- migrations safe to execute

Detect:
- unsafe deployment ordering
- hidden rollout dependencies
- incompatible environments
- missing migration steps
- rollback risks

---

## Step 11 — Produce Validation Report

Create validation report:

- `.ai/tasks/validation/implementation_audit_<next_number>.md`

Where:
- `<next_number>` = next free sequential number

---

# Audit Report Structure

## Executive Summary

Include:
- overall implementation quality
- production readiness verdict
- risk level
- architecture compliance status
- rollout readiness

---

## Verified Correct Implementations

List:
- correctly completed tasks
- validated integrations
- confirmed acceptance criteria
- architecture-safe implementations

---

## Findings and Problems

For every issue include:
- severity
- affected files/modules
- exact problem
- architectural impact
- execution risk
- rollback risk
- required correction

Classify:
- critical
- major
- minor
- informational

---

## Architectural Warnings

Include:
- layering violations
- hidden coupling
- architecture drift
- maintainability concerns
- scalability concerns

---

## Semantic Stability Warnings

Include:
- fragile integrations
- unstable anchors
- unsafe assumptions
- hidden side effects
- lifecycle inconsistencies

---

## UX/UI Findings

Include:
- accessibility issues
- responsiveness issues
- inconsistent flows
- missing states
- unclear interactions

---

## Test and Verification Findings

Include:
- outdated tests
- missing coverage
- invalid assertions
- integration verification gaps
- required test updates

---

## Rollout Risk Analysis

Include:
- unsafe deployment ordering
- migration risks
- rollback complexity
- environment inconsistencies
- dependency rollout concerns

---

## Required Fixes Before Approval

List:
- blocking issues
- required corrections
- mandatory validations
- unresolved risks

---

## Final Verdict

One of:
- APPROVED
- APPROVED WITH WARNINGS
- REQUIRES FIXES
- REJECTED

---

# Expected Result

Result must include:
- implementation quality assessment
- architectural compliance validation
- semantic safety analysis
- rollout readiness analysis
- verified completed work
- detected risks and regressions
- required corrections
- production readiness verdict

Result must NOT include:
- implementation code
- automatic fixes
- speculative redesign
- unverified assumptions
- architecture rewrites