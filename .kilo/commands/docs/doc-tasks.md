---
name: doc-tasks
description: doc-tasks
agent: auditor
alwaysApply: false
---


# Task: Update Project documentation Based on Implemented Functionality

## Goal

Analyze the current project implementation, development plans, and existing documentation, then update documentation: `docs` by adding only truly significant functionality that is currently missing from the documentation following instructions: `docs/00-overview/doc-maintenance-rules.md`.

---

# Workflow

## Step 1. Analyze the documentation

Review:

* ## CRITICAL: documentation formatting requirements  
  `docs/00-overview/doc-maintenance-rules.md`

* Project documentation  
  `docs/*`

* Project architecture structure  
  `STRUCT.md`

Identify:

* project functionality
* overall architecture
* documentation sections
* non-functional requirements

---

## Step 2. Analyze Development Tasks

For each file:

* identify the feature goal
* evaluate the scope of changes
* extract business-significant capabilities
* distinguish between:
  * full-feature functionality
  * technical refactoring
  * bug fixes
  * infrastructure changes
  * minor UX/API improvements

Create a detailed list of significant changes and new functionality — `{feature_list}`.

---

## Step 3. Validate Inclusion Criteria

For each item in `{feature_list}`, verify the following.

### 3.1. The Functionality Is Significant

Functionality is considered significant if it:

* adds a new business capability
* introduces a new user workflow
* changes the system architecture model
* adds a new subsystem/module/domain
* significantly expands the API, processing pipeline, or data model
* affects security, scalability, roles, permissions, or data lifecycle

Do NOT include in the documentation:

* bug fixes
* renaming
* behavior-preserving refactoring
* internal optimizations
* minor UI/API improvements
* local infrastructure changes
* test utilities
* temporary workaround solutions

---

### 3.2. The Functionality Is Missing From the Current documentation

Check whether the functionality is already described:

* directly
* partially
* conceptually
* through a related feature

Do not duplicate existing documentation sections.

---

### 3.3. Prepare Justification

For each included functionality, provide:

* why the functionality is considered significant
* why it is missing from the documentation

Remove from `{feature_list}` everything that does not pass validation.

---

## Step 4. Update the documentation

For all validated items in `{feature_list}`, update the documentation in:

`docs/*`

CRITICAL: STRICTLY FOLLOW REQUIREMENTS: docs/00-overview/doc-maintenance-rules.md

---

# Expected Result

The updated documentation must:

* reflect the actual significant functionality implemented in the system
* remain a high-level architectural document
* avoid technical noise and low-level implementation details
* stay consistent with the current project state