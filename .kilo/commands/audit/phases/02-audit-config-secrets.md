---
name: 02-config-secrets
status: draft
validated: no
executor: auditor
problems-only: true
---

# Phase 02 — Configuration & Secrets Management

## Purpose

Audit how configuration and secrets are declared, resolved, validated, and kept
separate across environments and automation in a **dual-process Django system**:
a web process and a bot process that share one project and one database.

Other phases own: entry/bootstrap process (01), connection pooling and runtime DB
concurrency (03), authentication (04), fixed-value enum discipline and
boundary-DTO validation (10), test-suite quality and coverage (11), TLS and
certificate lifecycle and health probes (12).

## Audit Blocks

Each block is standalone: execute in any order, with no knowledge of the others.
Every block carries its own evidence.

### 1. Settings surface & variant-selection topology

*Establish which configuration variant each running process actually loads and how
that choice is made. Treat variant selection as a per-process decision rather than
a per-environment label — confirm or refute that, including any variant that exists
only as a scenario or replay helper rather than a real environment.*
Evidence: effective variant per process, the mechanism that selects it, any
variant with no consumer.

### 2. Env-var name-contract reconciliation

*Reconcile four name universes in both directions: names actually read by code and
by shell, names admitted or flagged by whatever name check exists (it may be
permissive by design), names declared in shipped templates, and names supplied by
each deployment or automation surface. Drift in either direction is a finding;
separately judge whether the drift signal is actionable or indistinguishable from
a legitimately new variable.*
Evidence: the four sets with their symmetric difference; verdict on signal quality.

### 3. Secret validation & fail-fast behaviour

*For each guarded secret ask four questions: is a guard present, is it
unconditional, can any value reachable from a production secret file disable it,
and is the failure actionable yet free of the secret's value? Treat absent,
present-but-empty, and malformed as three distinct states. Where one boot
precondition is enforced in several places, check the implementations agree on
the condition, the skip rules, and the file they expect.*
Evidence: guard inventory with a scoping verdict; one controlled-environment
observation per guard; the failure text itself.

### 4. Secret provenance & exposure surface

*Trace where secret material can enter or leave: committed files, container build
contexts and image-build steps, process command lines and standard output, error
and traceback paths, and credentials supplied by automation. Classify every
credential-shaped literal as real, placeholder, or test fixture. Confirm ignore
coverage spans version control and the build context, not only the former.*
Evidence: classified match list; ignore-file diff per secret-bearing path; any
secret-bearing output path.

### 5. Environment separation & process parity

*Determine what must not cross between environments and between co-resident
processes, then judge each as intentional-and-complete rather than merely
different: debug and exception exposure, transport security, cookie and origin
policy, host allow-lists, backend substitution. Which origins and which cookie
attributes are honoured, per environment, is the policy half and is this phase's;
which surfaces a request-forgery check reaches, and whether it runs on each, is
the enforcement half and belongs to 15. Include whether the two processes
actually see the same required configuration, and whether a value written into
one environment's secret file can reach a process belonging to another.*
Evidence: effective-configuration diff per environment and per process (resolved
values, not source-file diffs); per environment, the honoured origins and cookie
attributes.

### 6. Automation env-parity vs. guarded configuration

*Reconstruct every environment automation claims to stand in for — containerised
execution paths versus natively executed ones — and ask whether each can still
exercise the configuration path it purports to validate. Treat the difference in
how values reach the process between the two execution styles as a first-class
object of analysis, and check each automated environment's supplied values
against the set the corresponding production guards require.*
Evidence: per automated environment — how values arrive, which guards are
exercised, which required values are absent.

### 7. Env-overridable production posture

*Identify settings whose value can change the security or delivery posture of a
running production process, and ask whether each such substitution is intended,
constrained, and re-pinned where a production variant is supposed to harden it.
Separate documented operator controls from configuration that looks like drift.*
Evidence: the list of posture-affecting settings with the pinning status of each.

### 8. Dead, ineffective & unconsumed configuration

*Three questions in one place: is each assigned setting name still read by the
pinned framework version; does every declared value reach a reachable consumer;
is every environment branch reachable under some real selection. Where a value is
derived rather than read directly, check that the derived result satisfies its
consumer's contract, not merely that the derivation exists.*
Evidence: per-name liveness verdicts; unread-name list; derived-value validity check.

## Severity Taxonomy

| Severity | Conditions |
|---|---|
| CRITICAL | A real secret obtainable by anyone who can read the artefact carrying it or the history preserving it; a production signing key or credential that is empty, invalid, or shared with another tier |
| HIGH | A production control is bypassable or silently disabled, including a validation gate that cannot run; secret values reaching logs, output, or error paths; an automated environment that no longer exercises the configuration it claims to validate |
| MEDIUM | Leakage across an environment or process boundary; ineffective transport, cookie, origin, host, or backend substitution; config-name drift, unconsumed configuration, or a setting name the framework no longer reads |
| LOW | Placeholder and template gaps; undocumented switches; missing explanatory comments |

Severity is anchored to **present state**: rate what is true now, not the worst
consequence a defect would have if it were triggered.

## Report Output

- Write findings to: `.ai/audit/02-config-secrets/findings.md`
- Use template: `.ai/audit/templates/audit-findings.md`
- **Incremental append**, ≤100 lines per pass.
- Prefix every finding ID with `CFG-`.
- Record findings only and omit passing checks. Every finding must carry
  reproducible runtime evidence and the exact consequence. If nothing is wrong in
  this phase, write exactly: `No problems found in this phase.`
- If a shipped test asserts the current behaviour as intended, still file the
  finding and record the test as a remediation blocker.
