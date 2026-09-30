---
name: 16-client-rendered-surface
status: draft
validated: no
executor: auditor
problems-only: true
---

# Phase 16 — Client-Rendered Surface & Browser Trust Boundary

## Purpose

Everything that runs after a response has left the application server. Which origins a rendered page actually fetches, whether each third-party asset is pinned and verified, whether a
response-header policy constrains the document it was attached to, what inline script writes into the page, and the client-asserted state a server-side rendering decision is steered by. Only
part of this is a security question; the rest is whether a page that returns is a page a person can browse, search, read, contact through and post from. This file names what to examine and
under which angle; the executing auditor discovers the concrete artifacts.

**Scope Boundaries** — other phases own: the edge tier as transport — its address resolution, its request-path × control matrix, and whether anything in the deployed system consumes the
collection endpoint a policy violation is reported to, so that the "is anything reading this" question is 12's and not this phase's, as is whether a check runs before a change and what makes a
check a gate rather than a report (12); cookie, origin and backend policy *values* per environment, this phase owning only whether a rendered page's real fetches agree with what those
values permit (02); the identity an assertion is bound to, and the session-layer consequences that follow from it, this phase owning only what the server does with the asserted value (04);
outbound calls to third-party *services* and the inbound machine-readable
surface form, neither of which is a script asset a browser fetches at render time (09); request-forgery coverage per surface, this phase raising no request-trust question (15); the media path
end to end, this phase owning only what a rendered document does with an image once it is already referenced (07); personal-data containment and any consent gate a third-party widget
enforces server-side, this phase owning what executes in the client and neither filing the other's question (06); a declared contract carrying no enforcement point *as a documentation
finding*, this phase measuring what the document actually does against that contract (10); whether a decision is exercised by a test, this phase owning the rendered outcome itself (11);
response latency and what a response costs, not what it instructs (13). A mechanism another phase owns is recorded as a deferral with its owner named, and the block still covers the
decision this phase makes.

## Audit Blocks

Each block is independent — execute any one with no knowledge of the others, and each carries its own evidence. Evidence is a class, not a check list: an enumerated origin, a resolved
subresource, an observed document, a reproduced request, or a static proof that a stated property does not hold; the method is the auditor's. A passing check is methodology, never a finding,
and any sound evidence is admissible: nothing here gates a finding on this phase's own list. No person is present in the environment the system is deployed in, and a page that was never
opened is not a page that passed — where a property can only be settled by executing a document, establish it from what is observable, say plainly what could not be verified, and never
record an unexercised page as a clean one. A documented intent to tighten a control is not the tightened control: grade the deployed form, and treat the pending form as a claim about the
future with consequences of its own.

### 1. The origins a rendered page fetches, against the origins a policy permits

*Take every external subresource the rendered pages load — the script, style, font, image and frame sources among them — and set that inventory against what each response-header directive
admits. Establish, per directive and per location the policy is declared in, whether the directive is inherited where it is not restated, whether one location re-declares what another leaves
to inheritance, and whether a directive reaches the subresource requests it is meant to govern at all. An origin admitted by a policy that no page fetches from is not a harmless leftover —
it is a permission nothing constrains, and it is evidence about whatever review produced the list. Where a page fetches from an origin no directive admits, establish what the page does with
the refusal: the subresource blocked, the document still legible, the feature it backed simply absent, or the interactivity gone.*
Evidence: the external-subresource inventory per rendered page against the admitted-origin set per directive and per location; the origins declared with no page fetching from them; the
pages fetching from an origin no directive admits.

### 2. The integrity and pinning posture of each third-party asset

*Per third-party asset, establish whether what is named is a fixed version or a moving tag, whether an integrity attribute is present at all, and where one is present whether the declared
digest can actually verify what the origin returns — a digest for a file the origin no longer serves verifies nothing and fails closed forever. Establish whether one dependency is loaded
under one posture everywhere it appears: a page carrying an integrity attribute alongside a sibling page loading the identical asset without one is a defect in the weaker page, and the
difference between them is precisely what has to be noticed. Establish whether a first-party dependency is fetched from a third-party origin at render time, and what that origin then
learns about every visitor, including the ones who never post.*
Evidence: per asset — pinned or moving reference, integrity attribute present or absent, digest verifiable against the content actually served; the surfaces loading one dependency under
differing postures.

### 3. What an enforcing form of a report-only control would refuse

*Where a control is deployed in a mode that records violations without blocking them, and the recorded corpus or the project's own backlog carries an intent to move it to the enforcing
mode, establish exactly what the rendered pages load that the enforcing form would refuse. A remediation known in advance to break a core user path is this phase's finding: what it breaks,
and where the breakage lands. Whether the project holds a check that would run beforehand, and what would make a check a gate rather than a report, is the operational question another phase
owns — establish what the intended change is written down as, whether the target mode is named at all, whether the admitted-origin list moves with it, and whether the change carries a step that
re-exercises the site afterwards, recording the absence of such a step as a deferral with that phase named. A control whose intended value is an edit nobody has run is graded on the value, and
the two are separate questions.*
Evidence: the subresource set an enforcing mode would refuse, per page; the queued remediation for that control and the verification step it does or does not carry; the page's behaviour with the
refused resources, established rather than assumed.

### 4. Client-asserted state that steers a server rendering decision

*For every value a client can set that the server later reads to choose what it renders — a hint carried in a request, a flag agreed per session, a value round-tripped through the page and
read back — establish whether the client's assertion is corroborated by anything the server itself observed, and what the decision is worth when it is not. Distinguish a value that only
selects a presentation variant from one that decides whether a document is produced at all, and treat the second as the finding. A rendering decision steered by a client assertion is
not thereby wrong; it is a decision whose only evidence is the party it decides about, which is worth establishing rather than assuming in either direction.*
Evidence: the client-settable values a rendering decision reads, with the corroboration each carries and what each decision is worth without it.

### 5. What inline script and embedded widgets do to the document

*Take every behaviour that manipulates the document after load: the markup it writes, the focus it moves, the element it measures, the class it toggles. For each, establish what it does when
the element it expects is absent, when the element it expects has been replaced by a partial update, and when its assumptions about shape or ordering no longer hold — a behaviour that degrades
to a readable page is not a finding, and one that throws before the page is usable is. Establish what a scripted surface is when scripting is unavailable: whether the document it enhances
is still complete and navigable, or whether the content, the control, or the only route to it lived in the script. Establish whether an embedded third-party widget is a hard dependency
of the page carrying it or an adornment, and what the page looks like if it never loads.*
Evidence: per scripted behaviour — the element assumptions it carries and its observed behaviour when each fails; the state of a page with scripting unavailable; the dependency order
between each page and each widget it embeds.

### 6. The declared accessibility contract measured against the document

*Where a written contract states target sizes, contrast ratios, focus treatment, labelling, keyboard reachability or script-direction handling, treat each stated rule as a claim to be measured
against the templates that must satisfy it, and record a rule with no measurement and no enforcement point as unenforced rather than as satisfied. Establish which rules are mechanically
checkable and whether anything checks them, and which are not checkable and are therefore enforced only by whoever wrote the markup last. Establish keyboard reachability on the surfaces
where the document is built dynamically, and where focus lands after a partial update — a landing point a keyboard or screen-reader user cannot continue from is a defect in the surface, not
in the reader. Reading a documented rule as a claim to be tested is this phase's work; whether the document that has to satisfy the rule exists at all is another phase's.*
Evidence: the declared rules with a measured verdict each and the enforcement point where one exists; the surfaces where dynamic content is not keyboard-reachable; the post-update focus
landing point.

## Severity Taxonomy

Grade by **effect and blast radius**, not by mechanism name.

- **CRITICAL** — a core user path — browse, search, view, contact, post — is broken in an environment actually deployed, by a client-side condition a person reaches through
  ordinary use.
- **HIGH** — a control that is configured or documented as constraining the client and does not constrain it: a report-only policy relied on elsewhere as though it were enforcing; an asset
  loaded from a movable reference with no integrity attribute on a page carrying user-supplied content; a rendering decision steered by a client assertion with nothing behind it, where the
  decision governs whether a document is produced rather than how it is styled.
- **MEDIUM** — one surface loading a dependency under a different integrity or pinning posture than another surface loading the same dependency; a scripted surface that fails hard on an
  unexpected element shape rather than degrading to a readable page; a documented remediation that would break a core path, whose own verification step is not part of it; a contract rule
  nothing enforces where no page violates it today.
- **LOW** — inline script whose only document writes stay within its own subtree; a declared origin no page fetches from, in a directive nothing relies on; a stated contract rule with no
  measurement and no divergence today; drift between a policy's declared form and the shape the pages actually need.

Anchored to **present state**: rate what is true now, not the worst consequence a defect would have if it were triggered. An empty band is a valid outcome — do not populate it with a
hypothetical.

## Report Output

- Findings path: `.ai/audit/16-client-rendered-surface/findings.md`
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `CLI-`
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence
- Empty state, exactly: `No problems found in this phase.`
