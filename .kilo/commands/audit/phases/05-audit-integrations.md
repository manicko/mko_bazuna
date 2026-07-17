---
name: 04-integrations
status: complete
validated: no
executor: auditor
problems-only: true
---

# Phase 05 Audit — External Integrations

## Purpose

This is a **reusable, system-agnostic handbook** for auditing how an application
integrates with external systems (APIs, services, subprocesses, browsers, devices).
It is not tied to a specific integration, SDK, or protocol. Apply the discovery
steps and audit dimensions to whatever external integrations the system actually
has, adapting concrete names to the implementation at hand.

[Adapt these checks to the integrations the system actually has — e.g., a messaging
platform, a tabular data service, a database, a browser automation tool, a CLI
subprocess. Keep the *properties* being verified; rename only the concrete names.]

## Output Mode

`problems-only: true` — **only problems, bugs, and deviations are documented.**

- **Do NOT** write sections that say "X is correct" or "no issues found in Y".
- **Do NOT** include checklist rows where the check passes — omit them entirely.
- If a dimension has zero findings after investigation, **omit the dimension entirely**.
- Every finding must be actionable: it describes a real problem, its evidence (code/logs/output), and its impact.

---

## Discovery Stage

Before performing audit checks, discover the integration architecture:

1. **External Integration Discovery** — Locate each external client setup. Map the auth/connection flow: credentials → session/connection → client → send/fetch operations. Identify how data is fetched and dispatched.
2. **Error Handling Discovery** — Identify error-handling patterns for each integration: what happens when the service is unreachable? When credentials are invalid? When rate limits are hit?
3. **Config Injection Discovery** — Trace how credentials and settings flow from typed models into the integration clients.
4. **Lifecycle Discovery** — Identify how clients/connections are created, started, stopped, and cleaned up (connection pooling, resource disposal).

---

## Audit Scope

External integration clients, their error handling, credential management, lifecycle, and config injection.

---

## Audit Dimensions

### 1. External Integration Correctness

| Check | Description |
|-------|-------------|
| Client creation is correct | The client is created with the correct connection/session name and credentials from config (not hardcoded). |
| Auth supports the required modes | The system correctly switches between supported auth modes when applicable. |
| Operations called with correct parameters | Send/fetch operations are called with the correct target identifiers and content. |
| Rate-limit control is handled | Rate-limit errors trigger a wait-and-retry with the specified duration plus jitter. |
| Other transient errors are retried | Transient/network errors trigger retries with exponential backoff. |
| Permanent errors are not retried indefinitely | After max retries, the error is logged and the item is skipped (not retried forever). |
| Client lifecycle is managed | The client/connection is properly started and stopped; resources are disposed. |

**Evidence required:** Read the client wrapper and dispatch logic. Verify retry logic and client lifecycle.

---

## Report Output

Write findings to: `.ai/audit/05-integrations/findings.md` using template `.ai/audit/templates/audit-findings.md`.

**Write the file incrementally — append blocks of ≤100 lines each. Never write the entire report in a single call.**

Use prefix `INT-` for finding IDs.

**`problems-only: true` rules:**
- The report contains **only findings** — real problems discovered during investigation.
- Do NOT include sections, dimensions, or checklist rows where everything is correct.
- If after completing all Runtime Verification steps and all Audit Dimensions, no problems were found, write a single line: `No problems found in this phase.`
- Every finding MUST include:
  1. **Runtime evidence** — import errors, test failures, code analysis showing the bug.
  2. **Not just:** "violates invariant X" — show the exact code that violates it and the exact consequence.
