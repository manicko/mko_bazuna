---
name: 12-production-ops
status: draft
validated: no
executor: auditor
problems-only: true
---

# Phase 12 — Production Operations, Security & Observability

## Purpose

What the deployed system is made of and what decides its content; what a deployment brings up, what a restart must re-establish and what a revert leaves behind; what an observer
is told when something is wrong; and what a failure costs in data. This file names what to examine and under which angle — the executing auditor discovers the concrete artifacts.

**Scope Boundaries** — taken in: the health, liveness and readiness endpoint and probe contract (from 01), and the edge tier, transport security and certificate lifecycle (from 09, 02). Deferred by this phase: which origins
and cookie attributes are honoured, per environment → 02; which surfaces a request-forgery check reaches and whether it runs on each → 15, as are object-level access and staff-surface authorization; process lifecycle and boot ordering → 01;
settings and secrets → 02; pooler configuration semantics → 03, owning only whether the production path enables the pooler at all; measured latency → 13; integration claims → 09; source-level logging hygiene → 10; test-suite adequacy → 11.
→ 16: a response-header policy as configured, and the origins a rendered page actually fetches under it, are 16's; the edge transport, address resolution, and the collection endpoint a violation is reported to are this phase's.
Which checks gate, and by what trigger, stays here.

## Audit Blocks

Each block is independent — execute any one with no knowledge of the others, and each carries its own evidence. Where a property cannot be settled in the environment at hand —
standing up a separate stack to restore into end to end, or inducing a dependency failure to probe an endpoint — establish it from what is observable and state plainly what
could not be verified and why. A passing check is methodology, never a finding, and any sound evidence is admissible: nothing here gates a finding on this phase's own list.

### 1. Container runtime posture

*Establish, per long-lived service, the identity it runs as and the capability, filesystem, privilege and resource restrictions it actually carries in the **merged** production
definition rather than in one manifest alone — an inherited directive and a restated one are not the same evidence, and a restriction missing from a later layer may still be
present. Establish what the runtime boundary publishes to the network, and which image-level defaults every service silently inherits, including one-shot and scheduled
containers that never open the port a default probe polls.*
Evidence: per service — effective identity and restrictions after merge, published ports, inherited defaults; one restriction present in only one of the layered definitions.

### 2. What decides the artifact's content

*Every input that can change the built artifact without a source change: base images and their versions, tools fetched during the build, and components pulled at automation
time. For each, establish whether it is pinned, whether its integrity is verified before use, and whether an automated updater covers that class of input at all. Establish
whether the coordinates used to publish, to deploy and to pull name the same object, and whether the version a revert would select is immutable.*
Evidence: the external-input inventory with a pin verdict and an integrity verdict each; the three identifiers compared; the mutability of the revert target.

### 3. A control that runs, reports clean, and examines nothing

*Take every automated control in the build, pipeline and deployment surface that produces a pass/fail signal — a scanner, a static analyser, a linter, a type checker, a secret
scan, a probe, a rehearsal job, a shipped regression test — and separate three questions per control: does it exist, what scope does it declare, what did it actually examine.
Establish what is configured to be enforced and which suppressions are sanctioned before judging any result; never infer a missing tool, and never treat a non-zero issue
count as a defect by itself. A control whose declared and actual scope differ is a finding however green it is: characteristically one whose paths resolve against the wrong
working directory, so it examines nothing, reports no issues and exits successfully.*
Evidence: per control — existence, declared scope, the file / item / series count it actually examined, and whether any shipped guard would notice a change in that scope.

### 4. What makes a check a gate

*Establish which checks can prevent something from happening, as distinct from which checks report. What triggers the automation, what ordering or dependency makes a verdict
reach the artifact, whether the artifact can be published or deployed regardless of a verdict, and whether credentials reach components that run before the gates. Establish
what overlapping or re-entrant runs do to shared state.*
Evidence: per check — trigger events, the dependency that would make it blocking, and the path by which an artifact or a deployment proceeds with the check failing or not having run.

### 5. Deployment provenance and service coverage

*Establish which artifact a deployment actually runs and whether that derivation is a verified one or a mutable reference. Then compare the service set the production topology
defines against the service set the deployment path actually enables: a component the stack defines and the deployment never starts, a conditionally-enabled component the
deployment path never turns on, and a component the forward path updates but the revert path does not. Whether a component is gated by design is a decision to read, not a
defect; the question is whether the production path enables it at all — how such a component is configured and sized is another phase's.*
Evidence: the resolved production service list against the service list each deployment and revert command enables; the artifact identity on each path.

### 6. Rollout and rollback under a real restart

*Ask what a full restart of the stack requires to be re-established, in what order, and what an external observer experiences while it happens. Establish whether a fronting tier
re-resolves the address it forwards to, or keeps the one it resolved when the component behind it was recreated. Establish what a success gate actually exercises relative to
the path a client takes: a check run from inside the component being verified cannot observe the tiers in front of it. Establish whether a revert restores a whole-stack
known-good state — the same service set, the same resolved address for every tier, the same schema expectation — or only the part it names.*
Evidence: the boot-order and address-resolution dependency chain after a restart; the components outside the success gate; the forward and revert paths compared service by service.

### 7. The health contract an observer can act on

*Establish the endpoints and probes an observer acts on: which signals exist, which gate, which merely inform, and whether each is **enabled in the deployed configuration**
rather than merely available. Where a dependency's liveness is staged into readiness before the hard one, establish its default and freshness rule against the shipped
configuration: does the default hide a real failure, and does the staging have a defined end state? Establish whether a wedged process is distinguishable from a healthy
idle one, whether a restart threshold can flap the boot chain, what an unauthenticated caller learns, and what a default probe reports for a container that never serves the probed port.*
Evidence: per signal — endpoint, gating or informational, enabled state in the deployed configuration, the disclosure a caller receives; one condition that answers healthy for a broken process.

### 8. The edge tier: transport security, certificates, and what is exposed

*Establish how the fronting tier resolves the address it forwards to and whether that resolution survives the address changing. Establish which requests reach a control and
which bypass it, and whether any monitoring path is restricted in a way the documented consumption model cannot reach. Establish how transport is negotiated, and the certificate
lifecycle end to end: where material comes from, how long it lives, what happens on expiry, whether expiry is observable before it happens, and what the tier does when the
material is absent.*
Evidence: the resolution model and its behaviour when the address behind it changes; the request-path × control matrix; the certificate's origin, lifetime, renewal path, and behaviour when missing.

### 9. Backup consistency and durability

*Establish whether each artifact the backup produces is internally consistent at the moment it was taken, and separately whether it survives the loss of what it protects: where
it physically lives, on which device, and whether the loss event it exists for also destroys it. Establish what each option passed to the backup tool actually does, judged by what
it changes rather than by what its name suggests — an option that reduces the flushing of the artifact's own output weakens durability and is not a consistency mechanism.
Establish whether the effective interval matches the nominal one, whether old artifacts are removed, and whether a job that stops is noticed.*
Evidence: per artifact — what it is taken from, what it is written to, the location relative to the thing it protects; each backup option with the behaviour it changes; the effective interval and the retention mechanism.

### 10. Evidence that a backup restores

*Establish whether any path — scheduled or manual — exercises a backup artifact that was actually taken, rather than one generated moments earlier from a database it also just
created. A rehearsal that restores its own input proves nothing about recovering from a real one, and an artifact that survives the loss of what it protects is not by itself
evidence that it restores. Establish what would have to be true for the stated recovery objectives to hold, and whether the stated preconditions are running.*
Evidence: for the rehearsal path — the origin of the artifact it restores and the origin of the data inside it; the recovery objectives with the state of each precondition.

### 11. Observability end to end

*Establish which signals are produced, which are consumed, and whether anything in the deployed system consumes them — an alert expression over a series no component emits is
not an alert. Establish whether the documented collection path is reachable from where a collector would actually sit, and whether a condition that matters has any signal at
all. Establish whether an operator has a channel that would tell them, and whether every log path reaches the same structured, redacting output — including the serving layer's
own access and error logs, and the failure modes of the tracking client's own initialisation, which can take down the processes it exists to report on. Measuring latency itself
belongs to the performance phase.*
Evidence: the signal inventory with produced / consumed verdicts; one alert expression against the series the system actually emits; the paths by which a log line can bypass the redacting output.

### 12. Runbooks and operational documentation as executable artifacts

*Establish whether the procedures a responder is told to follow would run as written on the host they would be run on: required state, required credentials, required files,
assumed tool versions. Establish whether each operational claim in the deployment, rollback, restore and incident corpus — a control that is live, a cadence, a value, a path — is
still true of the system as deployed. Treat a comment, a docstring and a runbook line as claims to be tested against the executing path; documentation describing a system other
than the one deployed is itself a finding. Claims about the integration surface are another phase's; the operational corpus is this phase's.*
Evidence: the operational-claim inventory with a true / false verdict each; one procedure with the step that fails on the deployed host and why.

## Severity Taxonomy

Grade by **effect and blast radius**, not by mechanism name; rate what is true now, not the worst consequence if triggered.

- **CRITICAL** — a control believed to be active that is not, on the path that decides whether an unvetted artifact reaches production, so that nothing distinguishes a vetted subject from an
  unvetted or an unexamined one for a reviewer or for the system's own records. An empty band is a valid outcome — do not populate it with a hypothetical, and do not promote an item for sounding alarming.
- **HIGH** — a state the system is in now where the failure is neither survivable nor observable: a recovery or a revert that does not restore a whole-stack known-good state; a
  protection that does not survive the operation it exists for; a signal produced and never consumed, so nothing distinguishes a quiet system from a broken one.
- **MEDIUM** — degraded operability with a workaround: a control present and effective in part; a documented procedure or claim that is inaccurate, but whose consequence an
  operator can work around; a gap visible only on a path the operator would have to know to look for.
- **LOW** — documentation and hygiene drift with no runtime consequence today.

## Report Output

- Findings path: `.ai/audit/12-production-ops/findings.md`
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `OPS-` — **already in use** in shipped source, tests, workflows and runbooks from a prior cycle, with at least one identifier already resolving to two different findings; check for a collision before minting an ID and report it rather than creating a second namespace
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence
- Empty state, exactly: `No problems found in this phase.`
