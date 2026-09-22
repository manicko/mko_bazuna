# 15 — Authorization & Access Control

> Audit phase. LLM-auditor instruction. Architecture-agnostic: described via
> ARCHITECTURAL LAYERS, ZONES OF RESPONSIBILITY, KEY RISKS, GOALS. NOT tied to
> specific files, modules, or functions. Must stay valid if the architecture changes.
>
> **Output mode:** `problems-only` — report only findings; do not narrate a clean bill of health.
>
> **Standards basis:** OWASP ASVS V4 (Authorization / Access Control), OWASP Top 10
> #1 (Broken Access Control), NIST SP 800-53 AC family (Access Control).

## 1. Goal

Verify that **authorization** — *what an authenticated identity may do* — is enforced
consistently across the dual-process (web WSGI + bot async) system:

- **Role definitions** and **permission assignments** (a fixed role enum consumed by both processes).
- **Object-level authorization (IDOR prevention)** on every seller-owned resource (ad, photo, draft).
- **Admin-interface protection** — administrative surfaces reachable only by the `ADMIN` role.
- **Anti-CSRF** — state-changing web requests require a valid CSRF token.
- **Access-control fail-secure on exceptions** — unresolved identity or check failure defaults to `DENY`.
- **Least-privilege** across all web endpoints and bot commands.

This phase owns **authorization ("what can you do?") — ASVS V4**. It does **not** own
**authentication ("who are you?")** — token issuance/claim/consumption, cookie attributes,
and session establishment are owned by **Phase 04**. Phase 15 picks up *after* a session is
established and asks whether every subsequent request is authorized.

## 2. System Under Audit (layers & zones)

The runtime is a **two-process, one-database** classifieds board: an anonymous-buyer
web UI (server-rendered HTMX MPA over gunicorn WSGI) and a seller-side Telegram bot
(async aiogram event loop), both sharing one PostgreSQL database and the same role model.

Roles (fixed-value enum — `StrEnum`, architecture-agnostic):

| Role | Meaning |
|------|---------|
| `ANONYMOUS` | Unauthenticated buyer — browse, search, view detail only. No owner-scoped actions. |
| `SELLER` | Authenticated seller (login-token claimed in Phase 04) — owns & manages own ads. |
| `ADMIN` | Staff/superuser — ad moderation, catalog/lookup administration, reference-data loaders. |

| Zone | Concern | Key risks |
|------|---------|-----------|
| **Identity / Role Model** | The identity carries a role claim; roles are a fixed `StrEnum`; role assignment is the single source of truth consumed by both processes. | Role confusion (seller escalated to admin); divergent role resolution between web and bot; magic strings instead of the role enum. |
| **Admin-Interface Protection** | All administrative surfaces (ad moderation, catalog/category management, lookup administration, reference-data loaders) require the `ADMIN` role. | Non-admin reaches an admin endpoint; admin surface returns `200` to a `SELLER`; admin URLs leaked to non-admins. |
| **Object-Level Authorization (IDOR)** | Every seller-owned resource (ad, photo, draft) is gated by an ownership predicate (`resource.owner_id == identity.id`). No seller may access another seller's object by identifier manipulation. | IDOR on `draft` or `photo` (not just `ad`); ownership check bypassed by a missing predicate on one resource type. |
| **Web Endpoint Access Control** | Each web route enforces least-privilege by role: public routes (browse, search, detail) are `ANONYMOUS`-accessible; seller routes (edit, archive, delete, favorite, dashboard) require `SELLER`; admin routes require `ADMIN`. | Route without a role gate; `ANONYMOUS` reaching a `SELLER`-only route; `SELLER` reaching an `ADMIN`-only route; `ANONYMOUS` mutating state. |
| **Bot Command Access Control** | Each bot command enforces least-privilege by role: greeting/help are public; ad-creation FSM entry and seller actions require `SELLER`; admin commands (moderate, manage catalog) require `ADMIN`. | Unauthenticated Telegram identity issuing a seller/admin command; command accessible to the wrong role; no role guard on a mutating command. |
| **Authorization Decision Point** | A single, shared authorization predicate (role check + object ownership) is invoked identically by the web process and the bot process via the shared ORM. | Divergent logic between processes; per-route/per-command ad-hoc checks that drift; duplicated predicates that fall out of sync. |
| **Fail-Secure on Exception** | When the identity cannot be resolved or an authorization check raises, the decision defaults to `DENY` (not `allow`). | Exception in a role check resolves to `allow`; missing identity resolves to a privileged role; `None`-role permitted through. |
| **CSRF Protection** | State-changing web requests without a valid CSRF token are rejected; the CSRF cookie is `Secure` + `HttpOnly` + `SameSite=Lax`. The bot process (no browser session) is not CSRF-relevant, but webhook updates (if present) verify the sender. | State-changing POST/PUT/DELETE accepted without a CSRF token; CSRF cookie missing `Secure`/`SameSite`; `csrf_exempt` on a mutating endpoint. |

## 3. Prerequisites

- Services runnable via the documented Docker commands (web + bot + DB + reverse proxy).
- Synthetic identities/roles (`ANONYMOUS`, `SELLER`, `ADMIN`) — **no real PII**.
- Ability to issue requests as each role (session cookie for web; bot update for bot).
- Ability to manipulate object identifiers to attempt IDOR across every seller-owned resource type.
- Linter, type-checker, and the access-control / authorization test suite available.
- External integrations (Telegram gateway, translator) **mocked** — no real calls, no cost, no PII egress.

## 4. Runtime Verification (mandatory)

Execute the discovery mapping, then capture evidence for each verification item.

### Discovery

Map the architecture before checking behavior. Use roles, not names.

1. **Role-model mapping** — locate the role enum and the role-assignment seam (where a claimed login token in Phase 04 produces a `SELLER` role; where `is_staff`/`is_superuser` produces `ADMIN`).
2. **Admin-surface mapping** — enumerate every admin-only route/command and confirm it is gated by the `ADMIN` role.
3. **Object-ownership mapping** — enumerate every seller-owned resource type (ad, photo, draft) and confirm each retrieval/mutation path checks ownership.
4. **Authorization-decision mapping** — confirm both web and bot invoke the same authorization predicate for equivalent operations; locate any ad-hoc per-route/per-command checks.
5. **CSRF mapping** — confirm CSRF middleware is enabled for state-changing methods and that the CSRF cookie attributes are `Secure` + `HttpOnly` + `SameSite=Lax`.

### Verification

1. **R1 — Role-to-resource matrix.** For each protected resource type and each role, attempt access; record the response code (`200`/`302` = allowed; `403`/`404`/`302-to-login` = denied).
2. **R2 — IDOR attempts (web).** As `SELLER A`, attempt to view/edit/delete/favorite `SELLER B`'s ad by direct identifier; attempt to fetch `SELLER B`'s photos/drafts by identifier → assert denied (`403`/`404`).
3. **R3 — IDOR attempts (bot).** As `SELLER A` issuing bot commands, attempt to view/edit/delete/favorite `SELLER B`'s ad via the bot → assert denied.
4. **R4 — Admin surface.** As `ANONYMOUS` and `SELLER`, attempt to reach admin-only endpoints (moderation, catalog management, reference loaders) → assert denied (`403`/`404`).
5. **R5 — Bot command authorization.** As each role, issue each bot command → assert allowed/disallowed per the matrix; confirm an unauthenticated (non-claimed) Telegram identity is rejected from seller/admin commands.
6. **R6 — CSRF enforcement.** Submit a state-changing POST/PUT/DELETE without a CSRF token → assert `403`; with a valid token → assert accepted.
7. **R7 — Fail-secure on exception.** Simulate an authorization-check exception (identity resolution failure, DB error during the ownership check) → assert `DENY`, not `allow`.
8. **R8 — Linter + type-check + access-control test suite.** Run over the authorization surface; record failures.

> Findings without R1–R8 evidence are not admissible under `problems-only`.

## 5. Audit Dimensions (checks + evidence)

### (a) Role definitions & least-privilege — CRITICAL
Roles are a fixed `StrEnum`; every route/command is gated by the minimum required role; no `ANONYMOUS` mutates state; no `SELLER` reaches `ADMIN`-only surfaces.
- Evidence: role enum source; route/command-to-role map; R1 matrix; R4/R5 denials.

### (b) Object-level authorization / IDOR prevention — CRITICAL
Every seller-owned resource (ad, photo, draft) is protected by an ownership predicate. No seller may reach another seller's resource by identifier manipulation.
- Evidence: R2/R3 IDOR attempts denied across *all* resource types; ownership check present on every retrieval/mutation path.

### (c) Admin-interface protection — CRITICAL
All admin surfaces require the `ADMIN` role; non-admins receive `403`/`404`, never `200`; admin URLs are not leaked to non-admins.
- Evidence: R4; role-guard on every admin route/command.

### (d) Web endpoint access control — CRITICAL
Each web route enforces the documented role. Public routes are `ANONYMOUS`-accessible; seller routes require `SELLER`; admin routes require `ADMIN`.
- Evidence: route-to-role map; R1 matrix; unauthorized access returns `403`/`404`/`302-to-login`.

### (e) Bot command access control — CRITICAL
Each bot command enforces the documented role. Unauthenticated Telegram identities are rejected from seller/admin commands.
- Evidence: command-to-role map; R5; unauthenticated command rejected.

### (f) Cross-process authorization consistency — HIGH
The same role + ownership predicates are enforced identically by the web and bot processes (shared ORM). No divergent logic.
- Evidence: both processes invoke the same authorization decision point; equivalent operations yield identical allow/deny results.

### (g) Fail-secure on exceptions — CRITICAL
When identity resolution or an authorization check raises, the decision defaults to `DENY`. No exception path resolves to `allow`.
- Evidence: R7; no fallback to a privileged role when the check fails.

### (h) CSRF protection — HIGH
State-changing web requests without a valid CSRF token are rejected; the CSRF cookie is `Secure` + `HttpOnly` + `SameSite=Lax`; CSRF is not enforced on read-only (GET) endpoints.
- Evidence: R6; CSRF cookie attribute inspection; no `csrf_exempt` on mutating endpoints.

## 6. Cross-Cutting (owned here, not duplicated)

This phase owns the **authorization model, object-level access control, admin protection, and CSRF enforcement** — "what you can do" *after* authentication. It explicitly does **not** duplicate:

- **Phase 04 (Authentication — V2 "who are you?")** — token issuance, claim/consumption, cookie `Secure`/`HttpOnly`/`SameSite` attributes, and session establishment. Phase 04 owns *authentication*; Phase 15 owns *authorization*. They meet at the session: a claimed token produces a `SELLER` role, which Phase 15 verifies is honored on every protected resource. (CSRF cookie *attributes* overlap conceptually, but the *token issuance/claim authn flow* is Phase 04; Phase 15 audits CSRF *enforcement* on state-changing requests.)
- **Phase 05 (Ad lifecycle, moderation gate, category tree, photo collection, sweeps)** — ad state-machine *correctness* and *side-effects*. Phase 15 owns the *ownership/authorization check* across all object types; Phase 05 owns the *status transition* correctness. A `SELLER` reaches `edit`/`delete` only because Phase 15 authorizes the ownership check; Phase 05 then verifies the `PUBLISHED → ON_MODERATION` transition fires correctly once the owner is authorized.
- **Phase 06 (PII / consent semantics + contact-gating)** — DECLINE vs WITHDRAW semantics and the contact-gating *predicate*. Phase 15 owns the *framework that enforces* the predicate consistently across both processes; Phase 06 owns the *semantics* of each condition. A withdrawn seller's ads are hidden because the ownership/authorization decision point returns `false` — Phase 15 verifies the framework honors that; Phase 06 defines the condition.
- **Phase 07 (Media file handling)** — ingestion, storage, transform, and physical purge. Phase 15 owns the *authorization model* that gates which ads/photos are reachable; Phase 07 owns the file-handling *mechanics*. A photo is reachable only if its ad is `PUBLISHED` and the requester is authorized — Phase 15 verifies the authorization gate; Phase 07 verifies the file is physically removed on purge.
- **Phase 08 (Search & FTS)** — the search mechanism, per-language FTS, ranking, pagination, and the visibility predicate. Phase 15 owns *object-level authorization* (only the rightful owner's ads are editable; only `PUBLISHED` ads are publicly visible). The "what is public" predicate semantics are owned by Phase 05/08; Phase 15 verifies that non-public objects are *not reachable* through authorization failures.
- **Phase 09 (External integrations)** — translation-client egress, reverse-proxy TLS/headers, async↔sync bridge. Phase 09(c) owns translation-client PII egress; Phase 15 verifies no PII reaches unauthorized surfaces via authorization failures.
- **Phase 11 (Test safety net)** — Phase 15 *specifies* the IDOR / cross-tenant access test scenarios (seller A cannot view/edit/delete/favorite seller B's ad via web UI and bot commands); Phase 11 *verifies* those scenarios exist, are meaningful, and pass.

## 7. Edge Cases

- IDOR via **every** seller-owned resource type, not just ads: photo ID, draft ID.
- Admin endpoint reached via alternate routing, URL casing, or HTTP method override.
- Bot command issued by an unauthenticated (non-claimed) Telegram identity.
- CSRF token valid for one session but replayed on another session.
- Authorization check raises on a consent-withdrawn / deleted identity → must `DENY`, not crash-open.
- Ownership check passes but the resource is in a non-editable status (e.g. `ON_MODERATION`) → the status gate (Phase 05) and the ownership gate (Phase 15) are both enforced, independently.
- Race between an ownership check and a concurrent ownership transfer (cross-tenant move) → lock or atomic re-check.
- `ANONYMOUS` user tapping a seller-only HTMX fragment endpoint (e.g. favorite heart) → must not persist anything or reveal state.
- Admin endpoint returns a distinct denial for unauthenticated vs. authenticated-but-non-admin (avoid leaking admin URL existence to anonymous).

## 8. Severity Taxonomy

- **CRITICAL**
  - `ANONYMOUS` mutates state (POST/PUT/DELETE on a state-changing endpoint).
  - `SELLER` reaches an `ADMIN`-only surface (moderation, catalog management, reference loaders).
  - IDOR on any seller-owned resource — `SELLER A` accesses `SELLER B`'s ad, photo, or draft.
  - Authorization check raises → resolves to `allow` (crash-open) instead of `DENY`.
  - State-changing web request accepted without a valid CSRF token.
- **HIGH**
  - Role confusion: a `SELLER` resolves to `ADMIN` (or vice versa).
  - Divergent authorization logic between web and bot processes.
  - Admin URL leaked to non-admins (endpoint reveals itself with a `200`/redirect to non-admin).
  - CSRF cookie missing `Secure` or `SameSite=Lax`.
  - No ownership check on one resource type (even if never exploited in testing).
- **MEDIUM**
  - A seller-only route lacks an explicit role-aware check (relies on an authentication gate alone) — returns `302`-to-login, not `403`.
  - Bot command has no role guard but is low-impact (e.g. help text) — still a least-privilege gap.
  - CSRF enforced on a read-only (GET) endpoint — usability regression, not security.
- **LOW**
  - Missing type hints on authorization helpers.
  - Log verbosity includes role/identity on denied requests.
  - No metrics on denied authorization attempts.

## 9. Recommended Sequence

1. Discovery (§4 Discovery) — map the role enum, admin surfaces, object-ownership paths, authorization decision point, and CSRF config.
2. Runtime verification (§4 Verification).
3. Per-dimension checks (§5 a–h).
4. Cross-cutting (§6) and edge cases (§7).
5. Consolidate findings.

## 10. Finding Prefix

Use `AUTZ-` for all findings in this phase.

## 11. Reporting

- **Output mode:** `problems-only: true`.
- Write findings to `.ai/audit/15-authorization/findings.md` using the template `.ai/audit/templates/audit-findings.md`.
- **Incremental append**, ≤100 lines per pass, per `docs/99-agent/rules.md`.
- **Problems-only rules (restated):** only findings; omit passing rows; if none → `No problems found in this phase.`; each finding = runtime evidence (R1–R8) + exact consequence.
