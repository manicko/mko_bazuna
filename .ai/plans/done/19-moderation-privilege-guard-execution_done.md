# Plan 19 — Moderation Privilege Guard on the `is_banned` Lever (Execution Plan)

**Status:** ready to execute · **Numbering:** 19 · **Created:** 2026-10-03
**Origin:** the literal requirement of plan `18-Q7` re-raised by the user on 2026-10-03, after the
Auditor established that the requirement is already satisfied for `is_active` and **not** satisfied
for the sibling lever `is_banned`.
**Precondition:** the user directed that the general plan phase be skipped; this file is the
Execution plan only.
**Decision owner:** coordinator. Constraint inherited verbatim from `18-D1` / `18-Q7` — *a
non-superuser operator may act on ordinary sellers only; superusers are unrestricted.*

---

## 0. Provenance and drift control

Every structural claim below is taken from
`.ai/context/19-moderation-privilege-guard-code_context.md` (audit of `C:\py_dev\mko_bazuna` @
`1257603`, read-only). **Nothing in this plan was re-derived by a second read of the source tree.**
This repo has a documented history of stale citations; `B-1`'s Auditor re-check exists precisely
because this plan is written against an audit of a code path that has never been guarded.

| Source | Role |
|---|---|
| `.ai/context/19-moderation-privilege-guard-code_context.md` | **Primary input.** Architecture, symbol inventory, test inventory, risk list, doc state. |
| `.ai/plans/18-account-deactivation-execution.md` @ `f2fd392` | The precedent to mirror; also the frozen prior art this plan must not disturb. |
| `.ai/tasks/templates/task_template.yaml` | The shape `B-1`'s Planner must emit. |
| `.kilo/rules/project.md` | Repo rules (English only, production code is king, StrEnum, no `print()`, migrations, docs current, small modules, i18n is part of DoD). |
| `.kilo/rules/commands.md` | Test/lint invocation. |

**Citation rule for this plan:** semantic anchors only — files, modules, classes, functions, enum
members, test node IDs, doc section headings. **No line numbers anywhere**, in this plan or in any
task derived from it.

---

## 1. The decisive fact

The requirement sentence, verbatim:

> moderators may deactivate ordinary sellers, but must not be able to deactivate
> staff/superusers/other moderators.

**This sentence is already implemented, tested, and shipped** for the `is_active` kill-switch:
`src/backend/apps/users/services/deactivation.py` (the single writer of the operator `is_active`
lever, whose service docstring quotes the requirement), enforced at both layers — actor scope via
`UserAdmin.has_deactivate_permission` in `src/backend/apps/users/admin.py`, target scope via
`deactivation._resolve_targets` — and pinned by
`src/backend/apps/users/tests/test_admin_deactivate_user.py` (plan 18, commit `f2fd392`).

**Do not re-implement, refactor, reword, or "improve" the deactivation path.** That module is
tripwire-protected: several of its tests assert **deliberate hard-coded-literal substrings** rather
than the imported constants, precisely so that a reword — or the removal of
`.exclude(is_superuser=True)` — goes red. `B-1`'s Validator gate exists to prove those tripwires
still fire after this plan lands.

> **CORRECTED 2026-10-03 by the `B-1` Researcher** — the sentence above overstates the mechanism.
> The hard-coded-literal substrings are real, but they guard the **operator message text** (3
> guards) and the **`transaction.atomic` / `select_for_update` source shape** (3 guards). **No
> assertion anywhere in the repo inspects the source text of `.exclude(is_superuser=True)`,**
> `.exclude(is_staff=True)`, `privileged`, or `permitted`. The `is_superuser` exclusion *is*
> protected — but **behaviourally**, by the `is_superuser=True, is_staff=False` fixture row in
> `test_moderator_cannot_target_a_superuser_or_staff_row`, not by a literal substring. Full
> classification and its consequence for Option `C`: **§11**, facts **(b)** and `19-Q1`.

**The open work is the sibling lever `is_banned`**, same defect class, no guard at all, and
arguably a *stronger* lockout: it blocks `can_login` and `can_publish_ad`, and it is **not**
web-only — `AccountStateMiddleware` reads it, so it is enforced in the bot tier too. Two unguarded
writers exist:

| Symbol | File | Current guard on the target | Reachability |
|---|---|---|---|
| `ban_user_for_ad(ad, moderator_id, reason)` | `src/backend/apps/moderation/admin_actions.py` | `@staff_required` on the caller only — **no target guard** | route `moderation:ban` → `moderation.views.review.ban_user` |
| `bulk_ban_users(queryset, moderator_id, reason)` | `src/backend/apps/moderation/admin_actions.py` | **none** — no privilege exclusion, no self-exclusion | `AdAdmin.action_ban_user` in `src/backend/apps/ads/admin.py` |

Neither reports a refusal. `bulk_ban_users` returns a count of *user ids seen*, not users actually
banned, so a privileged row that ought to have been refused is reported as a success.

**Consequence:** today a moderator can ban a superuser — a genuine denial-of-service escalation on
a privileged account, the same class of harm `18-Q7` forbids for deactivation.

---

## 2. Scope reconciliation

### 2.1 Already satisfied — do not touch

| Item | Home | Why it is closed |
|---|---|---|
| `is_active` target scope for a non-superuser operator | `deactivation._resolve_targets` | Excludes `is_staff`, `is_superuser`, and the actor's own row; superuser unrestricted. |
| `is_active` actor scope | `UserAdmin.has_deactivate_permission` | `is_staff or is_superuser`; distinct from `has_delete_permission`. |
| `is_active` escalation via the change form | `UserAdmin.fieldsets` / `readonly_fields` / `get_readonly_fields` | `is_staff` / `is_superuser` are absent from the fieldset entirely; `is_active` is read-only on change. |
| Refusal reporting for `is_active` | `UserAdmin._deactivation_message` + `DeactivationResult.skipped_self` / `.skipped_privileged` | The pattern this plan mirrors. |
| Self-exclusion for `is_active` | `_resolve_targets` (unconditional, even for a superuser) | The pattern this plan mirrors. |
| Web-tier session revocation on `is_active = False` | `ModelBackend.user_can_authenticate` via `AuthenticationMiddleware` | Probed in plan 18 `B-3`; backend-conditional and documented as such. |

### 2.2 Open — this plan's work

| # | Gap | Owner block |
|---|---|---|
| **G-1** | `ban_user_for_ad` has no target-scope guard. A moderator can ban the owner of any ad, including a superuser's or a peer moderator's. | `B-1` |
| **G-2** | `bulk_ban_users` has no target-scope guard and no self-exclusion. Reachable by any `is_staff` user through the ads changelist. | `B-1` |
| **G-3** | Neither path reports a refusal. A partly-refused selection reads as full success; the returned count is not a count of bans performed. | `B-1` (result type), `B-2` (surfacing) |
| **G-4** | No audit-trail discipline for a refused ban: a refusal must not write a `ModeratorActionLog` `BAN_ACCOUNT` row (`moderation.services.moderation_log.log_ban_account`). | `B-2` |
| **G-5** | `docs/04-user-stories/admin-stories.md` §US-A4 documents ban but does not say ban lacks a privilege guard — a reader of the doc would assume parity with deactivation. | `B-4` |

### 2.3 Explicitly out of scope

Each item below is real, documented, and **owned elsewhere**. Naming them here is the point: this
plan must not be read as closing any of them.

| Out of scope | Owner | Why it is not this plan |
|---|---|---|
| Introducing `UserRole.MODERATOR` | `15-AUTHZ-003` | "Moderator" is a *documented synonym* for Django's `is_staff` flag (`docs/01-spec/technical-specification.md`, `docs/04-user-stories/admin-stories.md`, `docs/02-database/db-enums.md` §UserRole). Adding a real role would touch the spec line, `media_gate`, `AdminSite.has_permission`, and all 17 `ModelAdmin` classes. The requirement is fully expressible with `is_staff` / `is_superuser` / self. |
| `media_gate` (raw `request.user.is_staff` in `ads/views/listings.py`) | `15-AUTHZ-003` | Divergence #2 of three divergent "is this an admin" implementations. Unrelated to ban target scope. |
| `AdminSite.has_permission` | `15-AUTHZ-003` | Requires `is_staff`, so a `is_superuser=True, is_staff=False` row is locked out of all 17 changelists while `staff_required` calls it ADMIN. Pre-existing; this plan neither fixes nor depends on it. |
| The 15-of-17 `ModelAdmin` permission overrides that declare no override | `15-AUTHZ-003` | Role-consistency debt, not a ban-target-scope defect. |
| Bot-tier `is_active` revocation | `15-AUTHZ-001` | `AccountStateMiddleware` never reads `is_active`. A residual, asserted on purpose by `src/telegram_bot/tests/test_account_state_deactivation_probe.py`. **Note the asymmetry that motivates this plan:** `is_banned` *is* read by the bot tier, which is exactly why a bad ban is worse than a bad deactivation. |
| `django_session` janitor | `15-AUTHZ-001` | No `clearsessions` job exists. Rows survive until `expire_date`. No `is_banned`-specific change is planned here. |
| Per-request web gate for `is_banned` (and `is_deleted` / `is_declined`) | `15-AUTHZ-001` | `MIDDLEWARE` is a pinned 15-entry list with no such gate; a banned seller keeps a working dashboard and can re-list (`TestBannedSellerRelistKnownGap`). This plan blocks the *privileged* ban; it does not tighten enforcement of a legitimate one. |
| The dead `<id>/password/` route | `15-AUTHZ-003` | `ReadOnlyPasswordHashWidget` renders a "Reset password" link to a route that does not exist. Building it with today's `has_change_permission` (which ignores `obj`) would let a moderator overwrite a superuser's password. Untouched. |

**Also out of scope, by the same logic:** an un-ban path (none exists anywhere in the repo; recorded
as `D-19-2` below), a `ModeratorActionType.DEACTIVATE` member, and any `is_deleted` / `is_deleted_at`
writer. If `B-1`'s Researcher finds a *further* writer of `is_banned` that the audit missed, that is
a **scope finding to report to the coordinator**, not work to absorb silently.

---

## 3. Execution blocks

Strictly serial: **`B-1 → B-2 → B-3 → B-4`**. Each block's commit body carries its own gate
closure. No block may start before the previous is committed and green. Rationale for strictness:
`B-2` cannot be written until `B-1`'s result type is fixed; `B-3` cannot assert refusal counts until
`B-1`/`B-2` agree on what is reported; `B-4` must describe shipped behaviour, not intended
behaviour.

### B-1 — Service-layer target scope for the ban path · **HIGH RISK**

**Goal.** Give the `is_banned` lever the same two-layer protection `is_active` has: a target scope
that a non-superuser operator cannot exceed, a result object that reports refusals, and a single
place where the rule lives so no caller can bypass it.

**Why HIGH RISK** (this is the block that earns the full agent set): it is a security boundary; it
writes an irreversible-from-the-UI flag; the placement is a genuine architectural choice; and the
adjacent plan-18 module is protected by literal substring tripwires that a well-meaning refactor
would break.

#### Exact semantic code units

| Unit | File | Role in this block |
|---|---|---|
| `ban_user_for_ad(ad, moderator_id, reason)` | `src/backend/apps/moderation/admin_actions.py` | Add the target-scope check. Currently `User.objects.select_for_update().get(id=ad.user_id)` then sets `is_banned = True` unconditionally. |
| `bulk_ban_users(queryset, moderator_id, reason)` | `src/backend/apps/moderation/admin_actions.py` | Add target scope **and** self-exclusion. Currently `User.objects.filter(id__in=user_ids).update(is_banned=True)`. |
| `log_ban_account(user_id, moderator_id, reason)` | `src/backend/apps/moderation/services/moderation_log.py` | **Caller.** Must not be reached for a refused target (gate `19-G2`). |
| `_resolve_targets(queryset, actor, *, target_is_active)` | `src/backend/apps/users/services/deactivation.py` | **Read-only reference.** The semantics to mirror. **Do not edit.** |
| `DeactivationResult` | `src/backend/apps/users/services/deactivation.py` | **Read-only reference** for the result shape. **Do not edit.** |
| `log_ban_account` call sites inside `admin_actions` | `src/backend/apps/moderation/admin_actions.py` | Placement of the audit write relative to the guard. |
| `User` | `src/backend/apps/users/models.py` | **Read-only reference.** `is_banned` is an existing boolean field → **no migration** (repo rule 13). |

#### Placement — **undecided; Researcher owns this, not this plan**

Three viable paths. They are **not** pre-decided here.

| Option | Shape | For | Against |
|---|---|---|---|
| **A — extend `admin_actions.py` in place** | Both ban functions gain the exclusion inline; a module-private resolver is added next to them | **Smallest possible diff.** One module already owns *both* ban writers, so the rule has exactly one home. The structural tripwire test `TestBulkLockingStructure::test_bulk_ban_users_not_locked` already inspects *this* file, so it keeps working unchanged. No new import edge, and no exposure to the `users/services/__init__.py` import-cycle hazard that `account_state.py` documents. | `admin_actions.py` becomes the home of a second, parallel implementation of the privilege predicate. The `DeactivationResult` semantics are re-derived rather than shared. |
| **B — new `src/backend/apps/users/services/ban.py`** | A service module mirroring `deactivation.py` exactly; `admin_actions.ban_user_for_ad` / `.bulk_ban_users` become thin callers | **Symmetry with the shipped precedent** — same layer, same result type, same test surface, so a future reader finds the two levers side by side. Account-state writes live under `users`, where the flag lives. Naturally hosts a future un-ban path (`D-19-2`) and any future `is_deleted` sibling. | New file and a new cross-app service import from `moderation` → `users.services`. The `deactivation` module is deliberately **not** re-exported from `users/services/__init__.py`, so this must import the full module path and must not "tidy" that up. |
| **C — extract a shared privileged-target resolver** and have both `deactivation.py` and the ban path use it | A helper such as a privileged-target filter used by `_resolve_targets` and the ban functions | One implementation of the rule; a future lever cannot drift. | **Constrained by plan 18's tripwires.** `deactivation._resolve_targets` currently contains the literal `.exclude(is_superuser=True)` that at least one test asserts as a hard-coded substring. Extracting it moves that literal and will go red — by design. This option is only viable if `B-1`'s Researcher proves *exactly* which guards are literal and *which* would survive; otherwise it must be rejected, because a refactor of shipped, tripwire-protected code is not worth de-duplicating two predicates. |

**Researcher's deliverable for this decision** (this is the single highest-value question in the
plan): the four facts listed under *Required agents* below. **The decision must be recorded in the
`B-1` commit body with the evidence that produced it**, so the next editor does not re-litigate it.

#### Semantics to implement (the mirror, restated so nothing is lost)

| Rule | `is_active` precedent | Required on the ban path |
|---|---|---|
| Privilege predicate | `is_staff=True` OR `is_superuser=True` | **Identical.** Both members — including the `is_superuser=True, is_staff=False` row, which is precisely why `.exclude(is_superuser=True)` cannot be dropped. |
| Actor rule | superuser unrestricted; non-superuser excludes privileged | **Identical.** A non-superuser `moderator_id` is restricted. |
| Self-exclusion | `pk=actor.pk`, unconditional (applies to a superuser too) | **Identical, and the case is sharper here:** `is_banned` has **no un-ban path anywhere in production code** (`D-19-2`), and there is no per-request web gate for it, so a self-ban is an operator lockout that the UI cannot repair. Self-exclusion is not optional on this lever. |
| Idempotence | already-in-state rows are excluded from the write and counted | Mirror for ban: a second ban of an already-banned row must not count as a change. |
| Locking | no `select_for_update` on the bulk `UPDATE` (documented decision, tripwire-tested) | **Keep it that way** — see §4. |
| Audit | `logger.info` naming the skipped counts | Mirror: `logger = logging.getLogger(__name__)`; **no `print()`** (rule 12). |
| Result type | `DeactivationResult(NamedTuple)` | Mirror the shape. A `NamedTuple` adds **no** migration and **no** new `StrEnum` (rule 10 is satisfied by the type, not by a new enum). |
| Schema | no migration | **No migration.** No column, table, or index changes. |

#### Dependencies

None upstream. `B-1` is the root of this plan.

#### Risks

| # | Risk | Severity | Containment |
|---|---|---|---|
| `19-R1` | **The change turns out to be a privilege *removal*.** A moderator legitimately uses *Ban users from selected ads* over a selection that happens to include a staff row (e.g. a staff member testing with a real ad). The ban is refused and the operator does not notice. | **High** | `B-2` must **report** the refusal loudly, and the refusal count must be visible in the same toast. This is the same failure mode `18-D1` solved with `skipped_privileged`, and the reason a bare `changed` count is not sufficient. |
| `19-R2` | A `bulk_ban_users` return-type change breaks an un-enumerated caller. | **High** | Researcher's caller inventory (below) **before** the signature changes. If any caller exists outside `AdAdmin.action_ban_user`, it is a `B-1` task, not a follow-up. |
| `19-R3` | An implementer refactors `deactivation.py` to share code, and plan 18's literal substring tripwires go red — or, worse, someone "fixes" a red tripwire by weakening the test. | **High** | `deactivation.py` is listed as a **read-only reference** above. `B-1`'s Validator gate re-runs `test_admin_deactivate_user.py` **unmodified**. Rule 2 applies in both directions: if a test and the architecture genuinely conflict, fix the test — but here the architecture is correct and pinned, so the *code* is what must not move. |
| `19-R4` | Scope creep into `15-AUTHZ-001` — someone adds the missing per-request `is_banned` gate "while they are here", touching the pinned `MIDDLEWARE` list. | Medium | §2.3 names it out of scope. The `MIDDLEWARE` list must stay at its current length. |
| `19-R5` | A fourth writer of `is_banned` exists that the audit missed, so the new guard is bypassable from a surface nobody checked. | Medium | Researcher's writer inventory (below). A positive finding is a **coordinator escalation**, not silent scope. |
| `19-R6` | `select_for_update` gets "helpfully" added to `bulk_ban_users` because it reads before writing. | Low | §4 — the invariant is kept deliberately, and the existing tripwire stays green. The next editor gets a docstring sentence, exactly as plan 18 did. |

#### Required agents

| Agent | Required | Justification |
|---|---|---|
| **Researcher** | **Yes — first.** | Owns the placement decision (`A` / `B` / `C`) and must first produce four facts: **(a)** the complete caller inventory of `ban_user_for_ad` and `bulk_ban_users` across `src/backend` **and** `src/telegram_bot` (the bot tree has its own conftest and cannot import the backend's); **(b)** which assertions in `test_admin_deactivate_user.py` are **hard-coded-literal substring guards** versus behavioural, i.e. exactly what Option `C` would break; **(c)** whether `apps/moderation` already imports from `apps/users/services/` — the precedent that decides whether Option `B`'s import is idiomatic or novel; **(d)** an exhaustive writer inventory for `User.is_banned` in production code. (a) and (d) are correctness gates, not diligence. |
| **Auditor** | **Yes — re-confirm, narrowly scoped.** | The entire plan is written against an audit of a path that has never been guarded, at commit `1257603`. Re-confirm **only** §1.6 of the code context: the exact signatures, return values, and present guard state of `ban_user_for_ad` / `bulk_ban_users`, and the reachability of both call sites. A stale signature makes `B-1`'s return-type change wrong on arrival. **No architecture re-derivation** — the code context is the authority. |
| **Planner** | **Yes.** | The placement decision is not expressible as one mechanical edit, so `B-1`/`B-2` must be decomposed into `task_template.yaml` tasks with `files[].targets` (`type: class` / `method` / `function`, by name) and `semantic_anchors` (`insert_after` / `insert_before` by symbol or call). Emit the task YAMLs **after** the Researcher's placement decision and **before** any code is written. |
| **Implementor** | **Yes.** | Writes the guard, the result type, the docstrings (including the no-lock rationale), and the `logger.info` reporting skipped counts. |
| **Validator** | **Yes — this is the block's real gate.** | Proves plan 18 survived: `src/backend/apps/users/tests/test_admin_deactivate_user.py` runs **unmodified and green**, every literal tripwire still fires, and `deactivation.py` is byte-unchanged unless Option `C` was chosen *and* the Researcher's inventory (b) proves it safe. Also confirms **no migration** was generated and no new `StrEnum` was introduced. |

**Intra-block order:** Researcher ∥ Auditor (both read-only, parallel) → Planner → Implementor →
Validator. Auditor and Researcher are read-only and independent; the Planner's output depends on
Researcher's placement answer, not on the Auditor's re-confirmation.

#### Gates (recorded in the `B-1` commit body)

- **`19-G1`** — the chosen placement option is named, with the Researcher's four facts and the
  trade-off that decided it.
- **`19-G2`** — `log_ban_account` is unreachable for a refused target; no `BAN_ACCOUNT` audit row
  exists for a ban that did not happen.
- **`19-G3`** — no `select_for_update` added to the bulk path; the existing locking tripwire is
  green and untouched (§4).
- **`19-G4`** — no migration; no new `StrEnum`; the result type is a `NamedTuple`; no `print()`.
- **`19-G5`** — `deactivation.py` and `test_admin_deactivate_user.py` are unmodified
  (or, under Option `C` only, a per-line justification is recorded and `19-G6` passes).
- **`19-G6`** — `.\Makefile.ps1 test` green, or the exact failing node IDs recorded with a
  one-line reason each.

---

### B-2 — Caller surfaces: report the refusal to the operator · **MEDIUM-HIGH**

**Goal.** Make every refusal **visible**. A guard whose refusals are invisible converts a
privileged-lockout escalation into a silent partial success, which is the operator's worst
outcome and is a finding in its own right.

**Why not folded into `B-1`:** the two callers have different surfaces and different reporting
idioms (a `message_user` toast vs. a template-backed view). Mixing them would make the diff
unreviewable and would couple a security change to a UI-text change.

#### Exact semantic code units

| Unit | File | Change |
|---|---|---|
| `AdAdmin.action_ban_user` | `src/backend/apps/ads/admin.py` | Consume the new result and report it to the operator. Today it calls `bulk_ban_users(queryset, request.user.id, "Bulk ban via selected ads")` and discards the count. |
| `AdAdmin.changelist_view` | `src/backend/apps/ads/admin.py` | **Reference only** — confirm no change is needed to the changelist itself. |
| `ban_user` | `src/backend/apps/moderation/views/review.py` | Surface a refusal to the moderator. Decorated `@staff_required`; **the decorator stays untouched** (`19-R7`). |
| `moderation_review`, `approve_ad`, `reject_ad` | `src/backend/apps/moderation/views/review.py` | **Read-only reference** for the view's existing post-action idiom (redirect target + message mechanism). Do not invent a second convention. |
| `staff_required` | `src/backend/apps/moderation/views/decorators.py` | **Do not touch.** It is the *actor* gate; target scope lives in the service. Adding a target check here would duplicate `B-1` in the view — the exact mistake plan 18 documented. |
| `log_ban_account` | `src/backend/apps/moderation/services/moderation_log.py` | Ensure refusal short-circuits the audit write. |
| review template for `moderation:ban` | `src/backend/templates/` (the template `review.ban_user` renders) | **Only if** the refusal notice is rendered there — see the i18n decision in §6, which is different for this surface than for the admin toast. |

**Requirements, restated so nothing is assumed**

1. A partly-refused selection **must not** read as a success. The refusal count is reported in the
   same message as the success count — the same shape as
   `UserAdmin._deactivation_message` / `SKIPPED_ROWS_PREFIX` in `apps/users/admin.py`, including
   the `already_in_state` clause if `B-1` adopted one.
2. A **fully** refused selection must read as a refusal, not as "0 banned".
3. The `AdAdmin` message must not imply a total lockout. This matters *more* on the ban lever than
   on the deactivation lever, because the ban is **not** web-only: `AccountStateMiddleware` reads
   `is_banned`, so a banned user's bot interaction *is* curtailed, while their **existing web
   session is not** (no per-request gate — `15-AUTHZ-001`). The truthful statement is therefore
   two-sided: *login and publishing are refused; the current web session keeps working until it
   expires.* State that, do not simplify it.
4. The refusal path must be a clean, non-500 outcome on both surfaces.
5. **The moderator's own ad** is a live self-ban path: banning the owner of an ad you authored
   targets yourself. `B-1`'s self-exclusion handles it; `B-2` must not surface it as an error
   page.

#### Dependencies

`B-1` — blocked on it. The result type and its field names are `B-2`'s input.

#### Risks

| # | Risk | Severity | Containment |
|---|---|---|---|
| `19-R7` | Someone "hardens" `staff_required` with a target check while editing the file. | **High** | `staff_required` is listed as do-not-touch. The split (actor scope in the permission layer, target scope in the service) is documented at length in `deactivation.py`; plan 18 §`B-1` recorded the same prohibition for the same reason. |
| `19-R8` | The refusal message over-promises: "locked out everywhere" is false (no per-request gate), and "banned" alone is ambiguous about the surviving session. | Medium | Requirement 3 above. This is `18-D2`'s rule restated for a lever with a **different** tier profile — do not copy the deactivation wording verbatim. |
| `19-R9` | New operator-facing text added to a **template** without `ru`/`bs` msgstr, failing the i18n completeness gate. | Medium | §6's i18n decision, which is deliberately **split** between the admin toast and the view. |
| `19-R10` | A `message_user` string lands in a template scan and is flagged, or an operator string lands in a `.po` and is flagged as an untranslated admin literal. | Low | §6 decides each surface explicitly so the Implementor does not choose per-string. |

#### Required agents

| Agent | Required | Justification |
|---|---|---|
| **Implementor** | **Yes.** | The two caller edits plus their operator messaging. |
| **Researcher** | **Yes — narrow, one deliverable.** | Establish the existing post-action idiom of `review.ban_user`: which message mechanism it already uses, what it redirects to, and whether the rendered template already has a message block. This plan's author did not read that view's body and will not guess at it. Bounded: one view, one template, one question. |
| **Validator** | **Yes.** | `test_decorators.py` (the `staff_required` / `staff_required_api` contract) and `test_moderation_views.py` must stay green; the refusal path must be verified to return a clean non-500 response on both surfaces; and the audit-row assertion from `19-G2` must hold end to end. |
| **Auditor** | No. | The architecture was established once, this cycle, by the code context. |
| **Planner** | No. | `B-2` is mechanical once `B-1`'s result type is fixed. Splitting it into tasks is `B-1`'s Planner's job. |

---

### B-3 — Tests · **MEDIUM**

**Goal.** Pin the new behaviour with the same rigor plan 18 used, using deliberate hard-coded
literals for the guard so that a future reword or a dropped `.exclude(is_superuser=True)` goes red.

**New module:** `src/backend/apps/moderation/tests/test_admin_ban_privilege_guard.py`, with
`pytestmark = [pytest.mark.django_db, pytest.mark.integration]`, mirroring
`src/backend/apps/users/tests/test_admin_deactivate_user.py`.

**Not** `test_admin_actions.py` (that module owns the ad-level moderation actions and the locking
tripwire — a second concern, and a heavily contended file), and **not** a bot test (there is no bot
writer of `is_banned`).

**Fixture pattern:** copy the module-local `staff_user` / `superuser` construction from
`test_admin_deactivate_user.py` — `get_or_create` on a reserved `93xxxxxxx` `telegram_id` block.
`src/backend/conftest.py` is contended territory and supplies `seller`, `user`, `category`, `city`,
`create_test_ad(...)` but **no** admin/superuser fixture. Bot tests cannot import the backend
conftest at all.

#### Required test inventory

| # | Test | Asserts |
|---|---|---|
| 1 | `test_non_staff_cannot_reach_the_ban_action` | Anti-actor-scope: the action is absent for a plain seller and a POST changes nothing. **Anti-vacuity pair with #2.** |
| 2 | `test_moderator_and_superuser_can_reach_the_ban_action` | Positive control for both actor classes. Without it, #1 passes if the action is simply broken. |
| 3 | **`test_moderator_cannot_ban_a_superuser_or_staff_row`** | **The `18-Q7` guard for the ban lever — the most important test in this plan.** Moderator selects {ordinary seller, peer `is_staff` moderator, full superuser, **and a `is_superuser=True, is_staff=False` row**}; only the seller changes; `skipped_privileged == 3`. The fourth row is the reason `.exclude(is_superuser=True)` cannot be dropped, exactly as in plan 18. |
| 4 | **`test_superuser_can_ban_a_staff_row`** | The positive half of #3. Prevents over-application of the guard. |
| 5 | **`test_moderator_cannot_ban_themselves`** | Self-exclusion on the ban lever, asserted through the **view** path (the reachable self-ban is "ban the owner of my own ad"). Row unchanged. |
| 6 | `test_bulk_ban_users_is_idempotent` | A second ban reports `changed == 0` and performs no second write. |
| 7 | `test_bulk_ban_users_counts_refusals_separately_from_bans` | The returned count is **bans performed**, not user ids seen. Directly pins `G-3`. |
| 8 | `test_a_refused_ban_writes_no_moderation_action_log_row` | `19-G2`: `ModeratorActionLog` gets no `BAN_ACCOUNT` row for a ban that did not happen. |
| 9 | `test_operator_message_reports_refused_rows` | The `AdAdmin` toast names the refused count on a partial selection. |
| 10 | `test_operator_message_does_not_claim_total_lockout` | The toast does not imply the ban revokes the current web session (there is no per-request gate). The `18-D2` rule, restated. |
| 11 | `test_ban_user_view_surfaces_a_refusal_without_error` | A refused ban on `moderation:ban` returns a clean non-500 response and leaves the target unbanned. |
| 12 | **Structural service-shape tests** (mirroring the `test_bulk_ban_users_not_locked` precedent) | `transaction.atomic` present and `select_for_update` absent in the new ban guard; the `.exclude(is_superuser=True)` literal present; no `StrEnum`; no import from `account_state.py` or `deletion.py`. |

**Literal-guard discipline (copied from plan 18's stated intent):** in #3, #4, #7 and #12, assert
against **hard-coded literals**, not the imported constants, so that renaming or rewording the
constant or predicate does not silently pass. This is deliberate and must be called out in the test
module's docstring so a future editor does not "fix" the duplication.

#### Dependencies

`B-1` (the behaviour), `B-2` (the operator messaging asserted by #9, #10, #11).

#### Risks

| # | Risk | Severity | Containment |
|---|---|---|---|
| `19-R11` | An **existing** ban test in `test_admin_actions.py` currently asserts that a moderator **can** ban a staff row, or that a superuser-only path is unrestricted. | Medium | If found, that test encodes the defect, not the contract. Correct it deliberately and record the change in the `B-3` commit body. Rule 2: production code is king — but here production code is *being corrected*, so the test follows it, and the correction is a **recorded decision**, not a quiet rewrite. Do not delete coverage to make the suite green. |
| `19-R12` | A test duplicates the implementation's logic (re-deriving the exclusion in the test) and passes vacuously. | Medium | Tests #3/#4/#7 assert **observable state and counts**, not query shapes. The structural tests (#12) cover shape by source inspection, as the existing precedent does. |
| `19-R13` | A test depends on `apps/moderation/tests/conftest.py` fixtures that do not exist. | Low | Module-local fixtures only, per the plan-18 pattern. |

#### Required agents

| Agent | Required | Justification |
|---|---|---|
| **Implementor** | **Yes.** | The twelve tests, in the new module. |
| **Validator** | **Yes.** | Runs the new module plus the full `apps/moderation` and `apps/users` test trees, adjudicates `19-R11` under rule 2, and confirms the untouched suites (`test_admin_actions.py`, `test_admin_deactivate_user.py`, `test_decorators.py`, `test_moderation_views.py`) are green. |
| **Auditor** / **Researcher** / **Planner** | No. | The test inventory is specified here; it needs execution, not re-derivation. |

---

### B-4 — Documentation · **LOW**

**Goal.** Make the ban lever's privilege contract discoverable, so the next reader of
`admin-stories.md` does not assume an absence of a guard means an absence of a defect. Add only;
**correct nothing that is already correct.**

**Files to touch — and only these.** Full detail in §5.

| File | Change |
|---|---|
| `docs/04-user-stories/admin-stories.md` §US-A4 | Add the ban privilege scope. This is the one **materially stale** doc. Also correct its silence on deactivate/reactivate **only if** the Doc-specialist can do so in one sentence; otherwise record it as a residual. |
| `docs/01-spec/technical-specification.md` | Add a sibling paragraph to the existing §"Operator contract for `is_active`", stating the `is_banned` target scope. **Additive — do not edit the `18-D1` / `18-D2` / `18-Q7` record and do not touch the "moderator = admin role" line.** |
| `docs/ops/docker-deployment.md` | Add one operator-inventory row (or extend the existing ban row) recording that a moderator's ban of a staff/superuser row is refused and reported. Keep the table's shape: one row per **operator need**. |
| `docs/99-agent/architecture.md` §"Operator-Facing Account Kill-Switch" | Add a ban-parity sentence and a pointer to this plan. **Do not re-litigate** the backend-conditional `ModelBackend` claim or the `is_banned` tier profile already recorded there. |
| `docs/05-owner-decisions/index.md` | **Recommended, non-blocking.** Add **one cross-reference row** to the ban-scope decision. Do not duplicate the decision text — it already lives in `technical-specification.md` and in code docstrings. |

**Must NOT be touched (would be churn):** `docs/02-database/db-enums.md` §UserRole (accurate;
`18-D4` is *deliberately* undecided and must stay that way), `docs/02-database/db-retention.md`
(byte-unchanged is a carried-forward phase-04 exit condition, and this plan adds no retention row),
`.ai/plans/18-account-deactivation-execution.md` (executed history), and `.ai/audit/**`.

**Governed by** `docs/00-overview/doc-maintenance-rules.md`. Repo rule 14 (docs stay current) and
rule 16 (i18n is part of DoD) both apply.

#### Dependencies

`B-3`. Docs must describe shipped, green behaviour.

#### Risks

| # | Risk | Severity | Containment |
|---|---|---|---|
| `19-R14` | Doc churn: an editor "improves" already-accurate sections, burying the one real correction. | Medium | The must-not-touch list above. Validator for `B-3` extends to a diff review of `B-4`: the diff must be additive only. |
| `19-R15` | The docs now read as if this plan closed `15-AUTHZ-003` or `15-AUTHZ-001`. | Medium | Every added paragraph names the residuals it does **not** close — same discipline as plan 18's closing note. |

#### Required agents

| Agent | Required | Justification |
|---|---|---|
| **Implementor** (acting as **Doc-specialist**) | **Yes.** | All doc edits. Additive only. |
| **Auditor** / **Researcher** / **Planner** / **Validator** | No standalone requirement. | The `B-3` Validator reviews the `B-4` diff for additive-only compliance and cross-references. If the coordinator runs a dedicated Doc agent, it substitutes for the Implementor here — the agent set for this block is otherwise unchanged. |

---

## 4. Regression and compatibility assessment

### 4.1 The locking tripwire — **deliberate decision: the invariant is KEPT**

`src/backend/apps/moderation/tests/test_admin_actions.py::TestBulkLockingStructure::test_bulk_ban_users_not_locked`
pins that `bulk_ban_users` takes **no** `select_for_update`. `B-1` **keeps this invariant, and the
test is not modified.**

Reasoning:

- The guard is a **`WHERE`-clause exclusion**, evaluated by the database at `UPDATE` time — exactly
  the mechanism the shipped deactivation service uses. `_resolve_targets` performs a read only to
  *count* refusals; the exclusions themselves are re-evaluated by the `UPDATE`. Adding a lock
  would not make the guard more correct, because the predicate is not read-then-decided in
  application code.
- The deactivation service — the approved precedent, shipped in `f2fd392` and tripwire-tested
  against adding a lock — takes **no** lock for its bulk `UPDATE`. Mirroring it means the two
  levers have one documented locking policy, not two.
- `ban_user_for_ad` **does** `select_for_update()` the `User` today, because it *reads* the user
  (`User.objects.select_for_update().get(id=ad.user_id)`) and then writes the field on the
  instance. That is a genuine read-then-write and its lock is legitimate. **This is not a
  contradiction:** read-then-write on an instance takes a lock; a bare bulk `UPDATE` does not.
  `B-1` must leave `ban_user_for_ad`'s existing lock alone and must not add a lock to
  `bulk_ban_users`.
- The test therefore stays green **unmodified**, which is itself part of `19-G3`.

**The obligation that comes with keeping it:** the new ban guard's docstring must carry the same
one-sentence rationale plan 18 recorded for `deactivation.py` — *"no lock: a bulk `UPDATE` does not
read, and the exclusions are `WHERE` clauses evaluated at write time"* — so the next editor does
not "fix" it and trip the test.

**If, contrary to the above, an Implementor concludes a lock is required** (e.g. a discovered
read-then-decide inside `bulk_ban_users` that this plan's author could not see), that is a
**coordinator escalation**: the change to `test_bulk_ban_users_not_locked` requires an explicit
decision recorded in the commit body, mirroring plan 18's `B-5` amendment discipline. It is never a
silent test edit.

### 4.2 Existing ban tests

`src/backend/apps/moderation/tests/test_admin_actions.py` is the current home of the ban tests. The
code context names only one test in it by node ID
(`TestBulkLockingStructure::test_bulk_ban_users_not_locked`); the remainder must be **enumerated by
the `B-1` Researcher** and by the `B-3` Implementor against the working tree, not guessed at here.

Two categories matter:

| Category | Expectation |
|---|---|
| Tests of `ban_user_for_ad` / `bulk_ban_users` **against ordinary sellers** | Must stay **green, unmodified**. The new guard is a no-op for a non-privileged, non-self target — this is the compatibility guarantee. Any breakage here is a defect in `B-1`, not in the test. |
| A test that asserts a **privileged or self** target **is** banned by a moderator | **None exists.** Enumerated 2026-10-03 by the `B-1` Researcher: all four ban call sites target a **non-privileged, non-self** user. `19-R11` needs no rule-2 correction. See §11.1 and `19-Q5`. |

`B-3`'s new module is additive; it must not be used as a reason to move or renumber existing tests.

### 4.3 `staff_required` / `staff_required_api` decorator tests

`src/backend/apps/moderation/tests/test_decorators.py` — **must stay green and unmodified.**
`staff_required` is the **actor** gate (`Http404` unless authenticated and
`request.user.role == UserRole.ADMIN`); `staff_required_api` returns `401`/`403`/`405` and checks
role **before** method. This plan adds **no** target check to either decorator, by design: the
split between actor scope (permission layer) and target scope (service layer) is the architecture
plan 18 established and documented at length in `deactivation.py`. A decorator change here would
duplicate the rule in a layer that cannot be enforced consistently across the two admin surfaces
and the one view.

The `role == UserRole.ADMIN` comparison in `staff_required` is worth naming explicitly: it resolves
via `User.role` (`is_staff or is_superuser → ADMIN`). That is consistent with `B-1`'s predicate and
is **not** in tension with the `AdminSite.has_permission` divergence (`15-AUTHZ-003`, out of scope).

### 4.4 Other surfaces that must remain green

| Surface | Test module | Why |
|---|---|---|
| Moderation views | `test_moderation_views.py` | `B-2` edits `review.ban_user`. |
| Moderation actions (approve / reject / soft-delete / bulk) | `test_admin_actions.py` | Untouched, but share the file `B-1` extends. |
| Deactivation kill-switch | `test_admin_deactivate_user.py` | **Must stay green unmodified** — the tripwire set (`19-R5`). |
| Admin change form / PII containment | `test_admin_change_form.py`, `test_admin_pii_containment.py` | `AdAdmin` is edited in `B-2`; these pin admin field contracts. |
| Banned-seller relist | `src/backend/apps/ads/tests/test_edit.py::TestBannedSellerRelistKnownGap` | Encodes that a banned seller can re-list — a **known gap** under `15-AUTHZ-001`. It must remain a *known-gap* test; `B-1` does not change it. |
| Bot account state | `src/telegram_bot/tests/test_account_state_deactivation_probe.py` | `is_banned` **is** read by `AccountStateMiddleware`; this plan must not change bot-tier behaviour, only who may set the flag. |
| i18n completeness | `test_i18n_completeness.py` | See §6. |

### 4.5 Blast radius

- **No migration.** `is_banned` already exists. `makemigrations --check` must report no new
  migration.
- **`MIDDLEWARE` length** must not change (pinned 15-entry list; `apps/core/tests/test_observability.py`
  asserts first and last only, but the count is a documented constant).
- **No new `StrEnum`, no new column, no new model** → no `18-D4` pressure on the account-state
  taxonomy, which stays deliberately undecided.
- **`bulk_ban_users`' return type changes, and so does `ban_user_for_ad`'s.** These are the only
  signature changes and the only compatibility risks; the Researcher's caller inventory (a) is the
  gate.

  > **CORRECTED 2026-10-03 by the `B-1` Researcher.** This bullet previously claimed
  > `bulk_ban_users` was *"the only signature change."* **That is wrong.**
  > `ban_user_for_ad(ad, moderator_id, reason) -> None` must **also** start returning a result, or
  > `B-2` / gate `19-G4` (*"Surface a refusal to the moderator"*) has nothing to surface. Both
  > existing test call sites ignore the return, so both changes are safe; only
  > `AdAdmin.action_ban_user` consumes a returned value, and it consumes `bulk_ban_users`'.
  > See **§11** fact **(a)** and escalation **ESC-2**.

---

## 5. Documentation impact

Per `docs/00-overview/doc-maintenance-rules.md`. "TOUCH" means this plan's work requires an edit.

| Document | Verdict | What changes — and what must not |
|---|---|---|
| `docs/04-user-stories/admin-stories.md` §US-A4 | **TOUCH — the only materially stale doc** | It documents ban/unban/delete and is silent on deactivate/reactivate, and its ban-reachability note does not say ban lacks a privilege guard. Add the ban scope. Adding the deactivate/reactivate mention is a **one-sentence courtesy, not a DoD item** — do not let it expand. |
| `docs/01-spec/technical-specification.md` | **TOUCH (additive)** | Add a sibling paragraph to §"Operator contract for `is_active`" for the `is_banned` target scope. **Do not edit** the `18-D1` / `18-D2` / `18-Q7` record, and **do not touch** the "Moderator = admin role (no separate moderator role)" line — that is `15-AUTHZ-003`'s to change. |
| `docs/ops/docker-deployment.md` | **TOUCH (additive)** | The operator inventory's existing deactivation row is accurate. Add the parallel ban row: a moderator's ban of a staff/superuser row is refused, and the refusal is reported. Keep the one-row-per-operator-need shape. |
| `docs/99-agent/architecture.md` §"Operator-Facing Account Kill-Switch" | **TOUCH (additive)** | Add ban-parity and a pointer to this plan. The section is accurate and detailed — it already names the false-claim correction, the backend-conditional guarantee, and the `04-AUTHZ` residuals. **Preserve all of that verbatim.** |
| `docs/05-owner-decisions/index.md` | **RECOMMENDED, non-blocking** | The privilege matrix has **no** entry; the decision currently lives only in code docstrings and `technical-specification.md`. Add **one cross-reference row**, not a duplicate of the decision. |
| `docs/02-database/db-enums.md` §UserRole | **DO NOT TOUCH** | Accurate. `18-D4` (should the account flags be one concept) is **deliberately undecided**; this plan adds no new flag and must not present the taxonomy as settled. |
| `docs/02-database/db-retention.md` | **DO NOT TOUCH** | Byte-unchanged is a carried-forward phase-04 exit condition. This plan adds no retention row. |
| `.ai/plans/18-account-deactivation-execution.md` | **DO NOT TOUCH** | Executed history. Its closing note ("pre-work for `15-AUTHZ-003`, not a substitute") stands. |
| `.ai/context/19-...-code_context.md`, `.ai/audit/**` | **DO NOT TOUCH** | Audit record. |
| `docs/04-user-stories/admin-stories.md` §US-A14 (verify-admin) | **DO NOT TOUCH** | `SellerVerification.verified_by_admin` is scored but no admin action writes it — an unrelated gap. Do not absorb it. |

**Every added paragraph must name what it does not close**: the bot-tier `is_active` residual, the
`django_session` janitor, the missing per-request `is_banned` gate, and the whole moderator-contract
question. Naming them is what stops this plan's landing from being read as phase 15 closing.

---

## 6. Definition of done

### 6.1 Commands

| Check | Command | Scope |
|---|---|---|
| **Fast gate (the authoritative one)** | `.\Makefile.ps1 test` | Whole backend + bot suites, `seed` marker skipped. Runs in Docker via the `mko-bazuna-test` project (host PG on :5433). **Never bare `uv run pytest`** — there is no DB on `localhost:5432` locally. |
| Full suite (only if a seeding/image path is touched — it should not be) | `.\Makefile.ps1 test-all` | ~35 min, includes the nightly `seed` suite. |
| Fresh schema (only if a migration appears — it must not) | `.\Makefile.ps1 test-recreate` | `--create-db`. |
| Lint | `uv run ruff check src/backend/apps/moderation/` and `uv run ruff check src/backend/apps/ads/` | Both apps are edited. |
| Typecheck | `uv run basedpyright src/backend/apps/moderation/` and `uv run basedpyright src/backend/apps/ads/` | **No new suppression permitted.** Plan 18's precedent: the only tolerated suppression is the verbatim `transaction.atomic` note, copied from the existing `admin_actions` usage — and it is needed only if the new code introduces an `atomic()` block. |
| Templates | `uv run djlint src/backend/templates/` | Only if `B-2` touches a template (see §6.3). |
| Migrations | `makemigrations --check` reports **no** new migration | Structural guarantee of §4.5. |

### 6.2 i18n — **explicit decision, deliberately split by surface**

The precedent, as recorded in `src/backend/apps/users/admin.py`: the admin action `description=`
strings and the entire `WEB_ONLY_ENFORCEMENT` / `Skipped:` toast family are **deliberate
English-only literals on a staff-only surface**. The i18n completeness gate
(`test_no_hardcoded_visible_text`) scans **templates only**, so `admin.py` is not flagged. There are
**zero** msgids for deactivate/reactivate. Plan 18's DoD item 5 recorded that this is the accepted
precedent.

**Decision:**

| Surface | Decision | Consequence |
|---|---|---|
| **`AdAdmin.action_ban_user`'s `message_user` toast** (Django admin messages framework, operator-only, same surface as `UserAdmin._deactivation_message`) | **Follows the existing precedent — English-only literal, no `.po` edit.** | None. This is the deliberate, documented staff-only decision, and consistency with the kill-switch toast the operator already reads is worth more than a translation nobody asked for. |
| **Anything rendered into a template** — including a refusal notice on the `moderation:ban` view's rendered page | **MUST be translated.** `{% trans %}` / `gettext` with **non-empty `msgstr` for `ru` and `bs`** (`en` may be empty, since the msgid is English). | If `B-2`'s Researcher finds no existing message block on that page, the cheapest compliant path is for the view to pass a short machine-readable refusal reason and let the template translate it. A `StrEnum` of refusal reasons is the rule-10-compliant shape, but it is a **new type for one call site** — weigh it against plain counts plus an existing convention. The choice belongs to `B-2`'s Implementor under Validator review, and must be recorded in the commit body. |

**Both messages must still be truthful about tiers** (§4 / `B-2` requirement 3): a ban refuses
**login and publishing**, and does **not** revoke an existing web session. Do not write
"locked out everywhere".

**Extraction, if any new msgid is added** (`ru`, `bs`, `en`; `.mo` files are gitignored and are
compiled at image build, container start, and in the CI `i18n` job):

```powershell
$dev = 'docker compose --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.override.yml --project-name mko-bazuna-dev'
$dev run --rm --no-deps --entrypoint "" web python src/backend/manage.py makemessages -l ru -l bs -l en --no-location
```

`make makemessages` does not work on this platform; use the form above. Then
`.\Makefile.ps1 test` must pass `test_i18n_completeness.py`.

### 6.3 Per-block gates (each recorded in its own commit body)

- **`B-1`** — `19-G1` … `19-G6` satisfied; placement option named with evidence; no migration; no
  new `StrEnum`; `deactivation.py` and its test module unmodified.
- **`B-2`** — refusals visible on both surfaces; a partial selection never reads as a success; no
  tier over-claim; no `staff_required` change; the message-layer decision recorded.
- **`B-3`** — all twelve tests exist and pass; the four literal guards use hard-coded substrings;
  `test_bulk_ban_users_not_locked` green **unmodified**; every §4.4 surface green.
- **`B-4`** — diff is additive only; the must-not-touch list is respected; every added paragraph
  names the residuals it does not close.

### 6.4 Phase-level

1. `.\Makefile.ps1 test` green.
2. `uv run ruff check` clean on both edited apps.
3. `uv run basedpyright` clean on both edited apps, **no new suppression**.
4. `makemigrations --check` → no new migration.
5. i18n: per §6.2 — `.po` unchanged if and only if no template string was added; otherwise `ru`/`bs`
   msgstr non-empty and `test_i18n_completeness.py` green.
6. `docs/02-database/db-enums.md` and `docs/02-database/db-retention.md` **byte-unchanged**.
7. `.ai/audit/**` and `.ai/plans/18-account-deactivation-execution.md` untouched.
8. This plan file is the **only** new non-code artifact.

---

## 7. Deferred work register

Consolidation index, not new invention. Each item has an owner; this plan does not absorb any of
them. Verify every attribution before relying on it.

| # | Work | Owner |
|---|---|---|
| `D-19-1` | The full moderator contract, including whether `UserRole.MODERATOR` should exist, and the 15-of-17 `ModelAdmin` permission overrides, `media_gate`, and `AdminSite.has_permission`. | `15-AUTHZ-003` |
| `D-19-2` | **No un-ban path exists anywhere in production code.** A ban is one-way from the UI; `is_banned` is read-only on the change form. An operator shell is the only remedy. This plan makes the ban *safer to apply* and does not make it *reversible*. | product + phase 15 (plan 18 `D-5`) |
| `D-19-3` | Bot-tier `is_active` revocation; the `django_session` janitor; the per-request web gate for `is_banned` / `is_deleted` / `is_declined` (so a banned seller keeps a session and can re-list). | `15-AUTHZ-001` (plan 18 `D-1`/`D-2`/`D-3`) |
| `D-19-4` | Operator deactivation writes **no** `ModeratorActionLog` row — `ModeratorActionType` has no `deactivate`/`reactivate` member — while bans do. Asymmetric auditability for two levers an operator uses interchangeably. | phase 15 (plan 18 finding 13) |
| `D-19-5` | The dead `<id>/password/` route rendered by `ReadOnlyPasswordHashWidget`. | `15-AUTHZ-003` (plan 18 finding 12) |
| `D-19-6` | `18-D4` — whether `is_active`, `is_banned`, `is_deleted` are one concept. | product / phase 15 BLOCK 9. **Deliberately undecided; `B-4` must not present it as settled.** |
| `D-19-7` | `account_state.py`'s module docstring is stale — says "Three independent flags", lists and returns five. Trivial, unrelated, **not** this plan's. | housekeeping |
| `D-19-8` | **The actor-privilege decision is read without a row lock.** `_resolve_ban_targets` reads the actor's `is_superuser` unlocked, so a concurrent demotion between the decision and the `UPDATE` could in principle apply a scope the actor no longer holds. **Identical to the shipped `deactivation._resolve_targets` precedent**, which reads `actor.is_superuser` off a request-scoped instance — so locking it would contradict the documented no-lock policy. Recorded because `is_banned` has no un-ban path (`D-19-2`), which raises the cost of the race relative to `is_active`. Raised by the `B-1` Validator; **no action in this plan.** | phase 15 / product (`15-AUTHZ-001`) |
| `D-19-9` | **`can_publish_ad()` is dead code carrying a security-relevant promise.** It reads as the enforcement point for "a ban stops publishing" and has **no production call site** (tests only). Publishing *is* in fact refused for a banned account — but by the bot tier's all-interactions gate in `AccountStateMiddleware`, combined with ad creation being bot-only, not by this predicate. A future editor could reasonably delete it as unused and break a promise the ban copy makes. Raised by the `B-2` Validator; **no action in this plan.** | phase 15 / product |
| `D-19-10` | **`docs/99-agent/architecture.md` is over the 1000-line hard split threshold** — 975 lines at `1257603`, **1017 at `8592c34`**, so this plan created the repo's only *new* breach in a file `B-4` was told to edit. `8592c34` recorded no deferral, which the maintenance rules require. **Deferred here with this owner entry** rather than split inside a privilege fix: §3 `B-4` forbade restructuring, and splitting a 1017-line agent-facing doc is a separate work item. **Booked as `F1`; must be closed before plan 19 is signed off.** | docs / phase 15 (`D-19-1` workstream) |
| `D-19-11` | **`docs/ops/docker-deployment.md` is 1446 lines**, past the same threshold — and was **1438 before this plan**, so the breach is **pre-existing** and not a plan-19 violation. Recorded because `B-4`'s threshold flag named the wrong file and miscounted it (~1137), which is how `D-19-10` was missed. | docs / phase 15 (`D-19-1` workstream) |

---

## 8. Open questions carried by this plan

| ID | Question | Owner | Status |
|---|---|---|---|
| `19-Q1` | **Where does the ban target-scope rule live** — extend `admin_actions.py` (`A`), a new `apps/users/services/ban.py` (`B`), or a shared resolver (`C`)? | Researcher, in `B-1` | **RESOLVED 2026-10-03 — Option `A`**, extend `src/backend/apps/moderation/admin_actions.py` in place, with a module-private resolver and a `BanResult(NamedTuple)`. Decisive trade-off: *the guard must stay in the same function body as the write it constrains*, because the only two structural tripwires that exist are source-inspection guards on `ban_user_for_ad` and `bulk_ban_users` themselves — and `test_ban_user_for_ad_uses_atomic` asserts `select_for_update` is **present**. `B` keeps the wrappers' `atomic()` and lock textually in `admin_actions.py` while relocating the predicate that decides what those blocks write, and adds an unpinned `moderation → users.services` edge plus (for `19-G2`) the first `users → moderation` service import in the codebase. `C` is **rejected on cost, not on test-redness** — see §11. The four evidence facts are in **§11**; the three escalated items in **§11.6**. |
| `19-Q2` | **Does the ban guard mirror `18-D1` exactly** — superuser unrestricted, non-superuser excludes `is_staff` / `is_superuser` / self? | coordinator | **RESOLVED 2026-10-03 — YES.** Entailed directly by the user's literal sentence, which names all three protected classes: "staff/superusers/**other moderators**". A non-superuser operator may therefore act on ordinary sellers only; a superuser is unrestricted. A narrower rule (e.g. moderators may still ban *peer* moderators) is **contradicted by the requirement as written** and would be a different guard. No open question remains for `B-1`. |
| `19-Q3` | **Is self-exclusion unconditional on the ban lever**, including for a superuser? | coordinator | **RESOLVED 2026-10-03 — YES, unconditional.** Mirrors `_resolve_targets`, and the case is stronger here than for deactivation: there is no un-ban path (`D-19-2`) and no per-request web gate, so a self-ban is an operator lockout the UI cannot repair. Applies to superusers too. |
| `19-Q4` | **Do the admin toast and the view notice need a new msgid, or does the view have an existing message convention?** | Researcher, in `B-2`; decided by Implementor in `B-2` | **OPEN.** Drives §6.2's split. If the view has no message block, adding one is a template change and a `.po` change. |
| `19-Q5` | **Does an existing ban test assert a privileged target is bannable?** | Implementor, in `B-3` | **RESOLVED 2026-10-03 — NO.** The `B-1` Researcher enumerated every ban call site: all four target a **non-privileged, non-self** user (the `seller` fixture / plain `User.objects.create`). `19-R11` needs **no** rule-2 correction and no test is rewritten. See **§11** fact **(a)** and §4.2. |

---

## 9. Rejected alternatives

| Option | Verdict | Why |
|---|---|---|
| Re-implement or "harden" the `is_active` deactivation path | **Forbidden** | Shipped, correct, and pinned by deliberate hard-coded-literal substring tripwires. A reword or a dropped `.exclude(is_superuser=True)` must go red — that is the design. |
| Put the ban target check in `staff_required` / `staff_required_api` | **Forbidden** | Actor scope and target scope are deliberately split; a decorator can only express the first, and it would duplicate the rule in a layer shared by surfaces with different reporting needs. |
| Put the ban target check in the two callers (view + `ModelAdmin` action) | **Rejected** | Two implementations of a security rule, one per surface. This is precisely the mistake plan 18 documented when it moved `is_active` target scope out of the view and into the service. |
| Refuse silently (current behaviour) | **Rejected** | A partly-refused selection reading as success is an operator hazard and a finding of its own (`G-3`, `19-R1`). |
| Add a per-request web gate for `is_banned` while here | **Forbidden here** | `MIDDLEWARE` is a pinned 15-entry list; the gate is `15-AUTHZ-001`. `19-R4`. |
| Add `select_for_update` to `bulk_ban_users` "for safety" | **Rejected** | See §4.1. The exclusions are `WHERE` clauses evaluated at `UPDATE` time; the lock adds contention without changing correctness, and it breaks an intentional tripwire. |
| Add an un-ban action to make self-ban recoverable | **Rejected** | Out of scope (`D-19-2`, product). Self-exclusion is the mitigation available inside this plan. |
| Introduce `UserRole.MODERATOR` to express "moderator" precisely | **Rejected** | The requirement is fully expressible with `is_staff` / `is_superuser` / self. Adding the role would touch the spec line, `media_gate`, `AdminSite.has_permission`, and all 17 `ModelAdmin` classes — `15-AUTHZ-003`. |
| Record the decision in `docs/05-owner-decisions/index.md` as a full decision entry | **Rejected as written** | The decision is already recorded in `technical-specification.md` and in code docstrings. A cross-reference row is enough; duplicating the text creates a second source of truth that will drift. |
| Generalise the guard to `is_deleted` / `is_declined` | **Rejected** | No operator writer for those flags was identified in the audit. If `B-1`'s Researcher finds one (`19-R5`), that is a coordinator escalation, not silent scope. |

---

## 10. Closing note on ownership

This plan is **pre-work for `15-AUTHZ-001` and `15-AUTHZ-003`, not a substitute for either.** It
closes the one escalation the literal requirement names, on the one lever where it is still open.
It adds **no** permission predicate, **no** role, **no** migration, and **no** new enforcement
point — it adds a target scope in the service layer and a refusal report in the two operator
surfaces, mirroring what plan 18 already shipped for `is_active`.

**Do not let this plan's landing be read as the moderator contract closing, or as a privileged
lockout being impossible.** A moderator can still act on ordinary sellers' ads (approve, reject,
soft-delete) with no target guard, because those are ad-level actions — item 7 of the code
context's §2 table. That is a different defect class and a different plan.

---

## 11. `B-1` Researcher record — `19-Q1` answered, four facts established

Read-only research against `C:\py_dev\mko_bazuna` @ `1257603` (clean `src/`; `f2fd392` confirmed
present as the plan-18 commit). Semantic anchors only, no line numbers, per §0's citation rule.
**No production code, test, or other plan/audit/context file was modified.**

### 11.1 Fact (a) — caller inventory of `ban_user_for_ad` and `bulk_ban_users`

Complete across `src/backend` **and** `src/telegram_bot`. The bot tree was searched
independently, as its conftest forbids importing the backend's: **zero** references to either
symbol, to `is_banned` as a writer, or to `admin_actions` anywhere under `src/telegram_bot/`
production code.

`ban_user_for_ad(ad, moderator_id, reason) -> None` — **4** references:

| Kind | Symbol | Exact usage |
|---|---|---|
| **Production** | `apps.moderation.views.review.ban_user` | `ban_user_for_ad(ad, request.user.id, request.POST.get("ban_reason", "No reason provided") or "No reason provided")` — positional; return **discarded**. Wrapped by the view's own `transaction.atomic()` (nested savepoint over the callee's). |
| Test | `apps.moderation.tests.test_admin_actions.TestBanAtomicRollback.test_ban_user_for_ad_atomic_on_log_failure` | `ban_user_for_ad(ad, moderator.id, "policy violation")` — positional; patches `apps.moderation.admin_actions.log_ban_account` to raise; asserts `pytest.raises(RuntimeError)` and `seller.is_banned is False`. Return discarded. |
| Test | `...TestBulkLockingStructure.test_ban_user_for_ad_uses_atomic` | `inspect.getsource(ban_user_for_ad)`; asserts `"transaction.atomic" in src` **and `"select_for_update" in src`** (a **positive** guard). |
| Reference | `apps.users.services.deactivation` (module docstring, "Why no row lock") | Prose citation only. |

`bulk_ban_users(queryset, moderator_id, reason) -> int` — **3** references:

| Kind | Symbol | Exact usage |
|---|---|---|
| **Production** | `apps.ads.admin.AdAdmin.action_ban_user` | `bulk_ban_users(queryset, request.user.id, "Bulk ban via admin action")`; result bound to `count`, then interpolated `f"Banned {count} user(s)."`. **The only return-value consumer in the repo.** |
| Test | `apps.moderation.tests.test_admin_actions.TestBanAtomicRollback.test_bulk_ban_users_atomic_on_log_failure` | `bulk_ban_users(Ad.objects.all(), moderator.id, "policy violation")`; patches `log_ban_account` to fail after the first call; asserts `pytest.raises(RuntimeError)` and that all three users stay unbanned. Return discarded. |
| Test | `...TestBulkLockingStructure.test_bulk_ban_users_not_locked` | `inspect.getsource(bulk_ban_users)`; asserts `"select_for_update" not in src` and `"transaction.atomic" in src`. |

**`19-R2` verdict: PASSES — no un-enumerated caller exists.** Both changes are safe because both
existing test call sites discard the return. The gate fired anyway, twice: see **ESC-1** (the
`ban_user_for_ad` return type) and **ESC-2** (the `B-1`→`B-2` toast window).

### 11.2 Fact (b) — literal tripwire inventory of `test_admin_deactivate_user.py`

Seventeen test functions. **6** are hard-coded-literal guards; **11** are behavioural (one of those
carries a structural *identity* assertion that is not a source substring).

| Class | Count | Guards | Substrings asserted |
|---|---|---|---|
| **Literal — rendered message text** (guards `UserAdmin._deactivation_message`, **not** the predicate) | 3 | `test_operator_message_names_the_bot_tier_limit`; `test_operator_message_reports_skipped_rows`; `test_operator_message_reports_already_in_state_rows` | `"cannot get back in"`, `"NOT enforced in the Telegram bot"`; `"Skipped:"`, `"1 privileged"`, `"0 privileged"` (negated); `"Deactivated 1 user(s)"`, `"1 already in the requested state"` |
| **Literal — source inspection** (`inspect.getsource`) | 3 | `TestDeactivationServiceStructure.test_deactivate_users_is_atomic_and_not_locked`; `...test_reactivate_users_is_atomic_and_not_locked`; `...test_resolve_targets_takes_no_row_lock` | `"transaction.atomic()"` present + `"select_for_update"` absent (×2); `"select_for_update"` absent on `_resolve_targets` |
| **Behavioural** | 11 | `test_non_admin_cannot_reach_the_deactivate_action`; `test_moderator_and_superuser_can_reach_the_deactivate_action` *(+ `has_deactivate_permission is not has_delete_permission`)*; `test_deactivate_user_sets_is_active_false_and_flips_no_other_flag`; `test_deactivate_user_excludes_the_acting_user`; **`test_moderator_cannot_target_a_superuser_or_staff_row`**; `test_superuser_can_target_a_staff_row`; `test_moderator_cannot_reactivate_a_superuser`; `test_deactivate_user_revokes_an_existing_web_session`; `test_deactivate_user_leaves_the_django_session_row_in_place`; `test_deactivate_users_service_is_idempotent`; `test_reactivate_user_restores_an_enabled_account` | — |

**The correction, stated exactly:** a tree-wide search for `exclude(is_superuser` /
`exclude(is_staff` / `getsource` across `src/` returns **no** assertion against the privilege
predicate's source. The single occurrence of the string `.exclude(is_superuser=True)` in the whole
test tree is **docstring prose** inside `test_moderator_cannot_target_a_superuser_or_staff_row`.
The `is_superuser` axis is protected by the `_make_user(..., is_superuser=True, is_staff=False)`
row and the assertions `superuser_only.is_active is True` and `result.skipped_privileged == 3` —
i.e. **behaviourally, through the public API.** The protection is real and adequate; only the
claimed *mechanism* was wrong.

**Exactly which guards survive Option `C`** (predicate extracted to a shared helper that
`_resolve_targets` calls):

| Guard | Survives? | Why |
|---|---|---|
| `test_resolve_targets_takes_no_row_lock` | **Yes** | Asserts only `select_for_update` absence. A predicate helper contains none. |
| `test_deactivate_users_is_atomic_and_not_locked` / `..._reactivate_...` | **Yes** | Inspect the *public* functions, untouched by a predicate extraction. |
| 3 message-text guards | **Yes** | Produced by `apps/users/admin.py`, untouched. |
| 11 behavioural tests | **Yes** | All drive `deactivate_users` / `reactivate_users`. |
| **Nothing goes red.** | | |

**So the plan's stated blocker for `C` is factually wrong** (*"Extracting it moves that literal and
will go red — by design"*). `C` is rejected on cost — see §11.5.

### 11.3 Fact (c) — import precedent for Option `B`

**`apps/moderation/` has zero imports from `apps.users.services/`** — production *and* tests. It
imports `apps.users.models` in exactly six places: production
`apps/moderation/admin_actions.py` and `apps/moderation/services/moderation_log.py`; tests
`test_admin_actions.py`, `test_moderation_log.py`, `test_moderation_views.py`,
`test_priority_service.py`. Option `B`'s import would therefore be **novel for this app**.

It is **not** novel for the repo: `apps/search` → `apps.users.services.account_state.account_state_q`
exists in three production modules (`apps/search/services/alert_query.py`,
`apps/search/services/immediate_alerts.py`, `apps/search/management/commands/send_alerts.py`).
The edge class is established; the `moderation → users.services` instance is not.

**Hazard mechanics, verified rather than inherited.** Importing **any** `apps.users.services.*`
submodule executes `apps/users/services/__init__.py`, which imports `.deletion`, which imports
`apps.ads.models`, `apps.search.models`, and `apps.search.services.cache`
(`bump_search_cache_version`), which imports `apps.ads.services.listings_query`.
`deactivation` is deliberately absent from `users/services/__init__.py`, but a full-path import
still triggers the package `__init__` — so `deactivation` carries the same closure, and
`deactivation.py`'s own *"adding a writer widens that closure"* note is accurate about the effect.

- There is **no hard import cycle today** — nothing in that closure imports `apps.moderation` at
  module level.
- There **is** a closure widening, and the only cold-interpreter tripwire for this edge
  (`test_account_state.py::test_alert_query_imports_in_fresh_interpreter`) probes the
  **`search → users`** direction only. Option `B` would add an **unpinned** `moderation →
  users.services` edge.

**The decisive `B`-specific cost, `19-G2`.** `apps/users/services/` contains **zero** imports from
`apps.moderation` (checked across all eight service modules: `account_state`, `consent_record`,
`deactivation`, `deletion`, `login_rate_limit`, `login_token`, `pii_inventory`, plus `__init__`).
Satisfying `19-G2` — *no `BAN_ACCOUNT` row for a ban that did not happen* — from `ban.py` requires
calling `moderation.services.moderation_log.log_ban_account`, i.e. the **first `users →
moderation` service edge in the codebase** and an inversion of the established `moderation → users`
direction. Option `B` therefore either inverts the app dependency or splits `19-G2`'s enforcement
back out into `admin_actions.py` — losing the "one place" property that justified `B` in the first
place.

**Weighing, honestly:** Option `B` is idiomatic *only if* the ban service later grows an un-ban path
(`D-19-2`) or a third lever. Both are out of scope, and `D-19-2` is explicitly rejected in §9. Today
`B` buys symmetry and pays for it with a novel edge on this app, an unpinned one, and an app-level
inversion. **Not worth it.**

### 11.4 Fact (d) — writer inventory for `User.is_banned` (production code only)

Writers of `True` — **exactly the two the audit named**:

| # | Symbol | Mechanism |
|---|---|---|
| 1 | `apps.moderation.admin_actions.ban_user_for_ad` | `user.is_banned = True` + `user.save(update_fields=["is_banned"])`, guarded by `if not user.is_banned`. Read-then-write; legitimately holds `select_for_update()`. |
| 2 | `apps.moderation.admin_actions.bulk_ban_users` | `User.objects.filter(id__in=user_ids).update(is_banned=True)`. Bare bulk `UPDATE`, no lock, no pre-filter. |

Writers of `False`:

| # | Symbol | Classification |
|---|---|---|
| 3 | `apps.users.models.User.is_banned` | Field-level `default=False`. A **creation-time** default, not an operational writer; the only `False` path in production code. |
| 4 | `apps.seed.generators.users.UserGenerator.generate` | `is_banned=False` in the `User(...)` constructor kwargs for unsaved seeder instances. Confined to `apps/seed`; cannot produce a ban and cannot un-ban. |

Confirmed **absent** (each verified by targeted search, not assumed):

- **No `User.save()` override.** The repo's `save()` overrides are in `apps/ads/models.py`,
  `apps/search/models.py`, `apps/core/models.py` — not `apps/users/models.py`.
- **No `bulk_update` on `User`.** The only production `bulk_update` is
  `Ad.objects.bulk_update` in `apps/currencies/management/commands/recompute_normalized_prices.py`.
- **No raw SQL** touching `is_banned`: no `RawSQL`, no `cursor()` statement, no `extra()`. The
  repo's `cursor()` uses are in search-trigger setup, login-token hashing, analytics, profile
  queries, advisory locks, and tests — none reference `is_banned`.
- **No form write path, therefore no form `default=`.** There is **no** `apps/users/forms.py`;
  `UserAdmin` uses `django.contrib.auth.forms.UserChangeForm` / `UserCreationForm` directly.
  `is_banned` appears in both `fieldsets` and `readonly_fields`, `get_readonly_fields()` returns the
  full `readonly_fields` list whenever `obj` is set, and on add `get_fieldsets()` returns
  `add_fieldsets`, which does not contain `is_banned`.
- **No custom `Manager` / `QuerySet` on `User`** — no manager-level default filter or writer.
- **No un-ban path**, which re-confirms `D-19-2`: no `update(is_banned=False)`, no
  `is_banned = False` assignment, no `unban` symbol in production code.
- **Bot tree:** `src/telegram_bot/middlewares/permissions.py` **reads** `state.is_banned` only;
  `src/telegram_bot/handlers/contact.py` mentions it in docstrings only. Zero writers.

**`19-R5` verdict: NO positive finding.** Exactly the two known writers; no coordinator escalation;
no scope absorbed. `19-R5` is discharged.

### 11.5 `19-Q1` decision — Option `A`

**Option `A` — extend `src/backend/apps/moderation/admin_actions.py` in place.** Both ban functions
gain the exclusion; one module-private resolver sits beside them; `BanResult(NamedTuple)` mirrors
`DeactivationResult`.

**The decisive trade-off: the guard must live in the same function body as the write it
constrains.** The only two structural tripwires that exist are `inspect.getsource` guards on
`ban_user_for_ad` and `bulk_ban_users` **themselves**, and
`test_ban_user_for_ad_uses_atomic` asserts `select_for_update` is **present**. Under Option `B`
the wrappers must keep `transaction.atomic()` *and* their lock textually in `admin_actions.py`
while the predicate deciding what those blocks write moves to another module — the rule and the
write are separated by a function boundary and an import edge, the tripwires keep passing while
pinning less, and `19-G2` then needs an app-level inversion (§11.3). Option `A` keeps guard and
write co-located, both tripwires green **unmodified**, `test_bulk_ban_users_not_locked` untouched,
zero new import edges, zero new dependencies, and the smallest reviewable diff.

**Why not `C`.** §11.2 proves nothing goes red, so the plan's blocker is wrong — but the argument
against `C` was never test-redness. `deactivation.py` is a declared **read-only reference**, §9
forbids touching it, and `19-R3` rates the refactor **High**. The predicate is three lines;
de-duplicating three lines across two app modules adds a module, a cross-app import edge, and a new
edit surface for **zero functional gain** (rules 5 and 7). It is also weaker *in kind*, even though
equal in count: after extraction the predicate would be guarded only behaviourally from two call
sites, with no source-level pin at all — strictly worse for a future editor who rewords the helper.

**Result type: `BanResult(NamedTuple)`** with `changed`, `skipped_self`, `skipped_privileged`,
`already_in_state` — a field-for-field mirror of `DeactivationResult`. It satisfies rule 10 with **no
new `StrEnum`** and needs **no migration**. **Both** ban functions return it.

**Caller reporting (`B-2`) falls out of the shape.** All four fields are exactly what both surfaces
need, and `changed` is *bans performed* — which is the direct fix for `G-3`'s "count of user ids
seen":

- `AdAdmin.action_ban_user` interpolates `result.changed` instead of the old `count` and appends the
  three skip counts, mirroring `UserAdmin._deactivation_message`'s `SKIPPED_ROWS_PREFIX` +
  dropped-clause structure — with the ban-specific two-sided truth (login and publishing refused;
  the current web session survives), never "locked out everywhere".
- `review.ban_user` needs **no new convention and no new template block**: the module already
  imports `django.contrib.messages` and the sibling `approve_ad` posts
  `messages.warning(request, ...)` before its redirect. (That is also the answer `19-Q4` needs; this
  block does not close it, but it removes the open question's premise.)

A partly-refused selection **cannot** read as success with this type: `changed == 0` with
`skipped_privileged > 0` is representable and must be rendered as a refusal (`B-2` requirement 2).

### 11.6 Escalated to the coordinator

| ID | Item |
|---|---|
| **ESC-1** | **§4.5's "only signature change" is wrong** — `ban_user_for_ad` must also stop returning `None`, or `B-2`/`19-G4` has nothing to surface. Corrected inline in §4.5. Both existing test callers discard the return, so it is safe. |
| **ESC-2** | **`B-1` → `B-2` ordering hazard.** Once `bulk_ban_users` returns a `BanResult`, `AdAdmin.action_ban_user`'s existing `f"Banned {count} user(s)."` renders the `NamedTuple` **repr** to the operator until `B-2` lands — i.e. `19-R1`'s exact failure mode arriving by accident. Either the one-line toast rides in `B-1`, or the two blocks share one commit for `apps/ads/admin.py`. |
| **ESC-3** | **The `B-1` Validator gate must be re-scoped.** `19-G5` currently reads *"every literal tripwire still fires."* Per §11.2 the concrete set is: the **3** `transaction.atomic` / `select_for_update` source guards, the **3** message-text literal guards, and the **`18-Q7` behavioural guards** (`test_moderator_cannot_target_a_superuser_or_staff_row`, `test_superuser_can_target_a_staff_row`, `test_moderator_cannot_reactivate_a_superuser`). Corrected inline in §1. |
| **ESC-4** | **No `19-R5` escalation.** Fact (d) found no writer beyond the two the audit named. Two `False`-only writers exist (the field `default` and the seeder) and neither can produce or clear a ban. Nothing to decide. |

**Not escalated, recorded for the audit trail:** the requirement's sentence is scoped to `is_active`,
and this plan extends it to `is_banned`. Because `is_banned` has **no un-ban path** (`D-19-2`) and
no per-request web gate, the ban guard's unconditional self-exclusion (`19-Q3`) is *stricter* than
the literal requirement for `is_active`. That is the right call and already resolved — flagged only
so the record shows it was a deliberate widening rather than a literal reading.

---

## 12. `B-1` Auditor record — re-confirmation, and two coordinator decisions

Read-only re-confirmation against `C:\py_dev\mko_bazuna` @ `1257603`, live tree. **`src/` is clean
against HEAD**; no commit has landed since `f2fd392`, which is the commit immediately preceding the
audit commit. All seven files named for `B-1` are unmodified.

### 12.1 Confirmed

`ban_user_for_ad(ad: Ad, moderator_id: int, reason: str) -> None` and
`bulk_ban_users(queryset, moderator_id: int, reason: str) -> int` — signatures exactly as the plan
assumed. No target guard, no self-exclusion on either path. `ban_user_for_ad` holds
`select_for_update()` (a genuine read-then-write on the instance); `bulk_ban_users` does not (a bare
bulk `UPDATE`). §4.1's locking decision holds.

`deactivation.py` is byte-unchanged, still contains the literal
`.exclude(is_staff=True).exclude(is_superuser=True)`, and still has no `select_for_update` in its
code. The `B-1` tripwire claim rests on a true foundation.

`19-R11` **does not materialise:** `test_admin_actions.py` contains no occurrence of `is_staff` or
`is_superuser` at all. Its two ban tests use a plain non-staff `User.objects.create(...)` moderator
against the ordinary `seller` fixture — non-privileged actor, non-privileged non-self target. Both
stay green under `B-1` unchanged. This is §4.2's compatibility guarantee, confirmed by reading.

### 12.2 Corrections to the plan

| # | Correction |
|---|---|
| 1 | **`AdAdmin.action_ban_user` does NOT discard the count.** It binds `count = bulk_ban_users(...)` and interpolates `f"Banned {count} user(s)."` at `level="success"`. `B-2`'s "discards the count" and its misquoted reason literal (`"Bulk ban via selected ads"` — the live value is `"Bulk ban via admin action"`) are both wrong. **Sharper consequence:** that toast is today a *false-success surface* — `level="success"`, `Banned N user(s).`, counting rows that were already banned and rows that ought to have been refused. This strengthens `G-3`/`G-4`. |
| 2 | **A second tripwire exists and §4.1 names only one.** `TestBulkLockingStructure::test_ban_user_for_ad_uses_atomic` asserts `"transaction.atomic" in src` **and `"select_for_update" in src`** on `ban_user_for_ad` — a **positive** guard. `B-1` may not remove that lock either. |
| 3 | **`moderator_id` is an `int` pk, not a `User`.** `_resolve_targets` receives the actor *instance* and reads `actor.is_superuser` / `actor.pk` directly. The ban path receives only an id, so the mirror **must resolve the actor by lookup** to reproduce the superuser-unrestricted branch. This is a load-bearing signature fact the plan omitted. |
| 4 | **`ban_user_for_ad`'s write is conditional on `not user.is_banned`**, not unconditional as the code context stated. The function is fully idempotent (no second write, no second audit row). The code context's claim is imprecise; the **defect stands** — there is no *privilege* condition, which is what matters. |
| 5 | **`bulk_ban_users` calls `log_ban_account` BEFORE the `UPDATE`, once per distinct non-null `user_id`, inside the loop, fully unconditionally.** Consequences: the bulk path is **not idempotent in the audit trail** (a repeat ban writes a second `BAN_ACCOUNT` row — asymmetric with `ban_user_for_ad`, whose log call sits inside the not-already-banned branch), and `19-G2` is violated in the *inverse* direction today — an audit row is written before the ban is known to have happened. `TestBanAtomicRollback::test_bulk_ban_users_atomic_on_log_failure` **depends on the loop completing before the `UPDATE`**, so `B-1` must not reorder it. |
| 6 | **A free win, and a trap.** `update()`'s matched-row count is currently discarded. Because a bare `UPDATE` reports *matched* rows, `changed` can only be taken from it **after** adding a `.filter(is_banned=False)` pre-filter — exactly the trap `DeactivationResult`'s docstring documents and the reason plan 18 pre-filters. Mirroring only the exclusions and reading `update()`'s return would silently reintroduce the plan-18 bug. |
| 7 | Code context §1.7's "the first three also `@require_POST`" is imprecise: only `approve_ad` carries `@require_POST`; `reject_ad` and `ban_user` use an in-body method check returning a **302, not a 405**. |

### 12.3 `19-Q4` premise removed

`review.ban_user` uses **no** message mechanism today — it `logger.info`s and redirects to
`/admin/ads/ad/?status__exact=on_moderation`. The idiom already exists in the same module: `messages`
is imported, sibling `approve_ad` posts `messages.warning(request, _APPROVE_OUTCOME_MESSAGES[outcome])`
against a module-level `dict[ApproveOutcome, str]`, and `admin/moderation/review.html` already carries
a `{% if messages %}` block. `ban_user` redirects to the admin changelist, not the review page, so a
refusal message renders with **no template change**. The question `19-Q4` asked is answered; only the
message-layer decision remains open for `B-2`.

---

## 13. Coordinator decisions — `2026-10-03`

Recorded here because each one changes what `B-1`'s Implementor does, and none of them is derivable
from the requirement or the code alone.

### `19-D1` — ESC-2 resolved: the one-line toast fix **rides in `B-1`**

Once `bulk_ban_users` returns a `BanResult`, the existing
`f"Banned {count} user(s)."` renders the `NamedTuple` **repr** to the operator — `19-R1`'s exact
failure mode arriving by accident, and a *worse* one (an unreadable blob at `level="success"`).

**Decision: `B-1` includes the minimal `AdAdmin.action_ban_user` correction** — interpolate
`result.changed` instead of the old `count`, and append the skip counts in the established
`SKIPPED_ROWS_PREFIX` / dropped-clause shape. `B-2` then *extends* that same toast (the two-sided
tier truth) and adds the `review.ban_user` notice.

**Rationale:** every commit must leave the operator surface truthful. A commit that renders a
`NamedTuple` repr is a regression even if the next commit fixes it, and this repository's history is
one commit per reviewable work item. The alternative — the two blocks sharing one commit — collapses
the separation of concerns that put `B-2` in its own block in the first place. The scope added is one
file and one line, so the diff stays reviewable.

### `19-D2` — §4.1's docstring obligation re-scoped: the rationale must live **outside** the function body

§4.1 obliges the new guard to carry a one-sentence no-lock rationale, so the next editor does not add
a lock. As written, that obligation is in **direct conflict** with a tripwire:
`test_bulk_ban_users_not_locked` runs `inspect.getsource(bulk_ban_users)` and asserts
`"select_for_update" not in src` — a substring check over the **whole function source**. A docstring
or comment *inside* `bulk_ban_users` naming that token **fails the test**.

`TestDeactivationServiceStructure`'s own docstring already documents this exact hazard, which is why
`deactivation.py`'s "Why no row lock" section sits in the **module** docstring while all three of its
guards inspect *function* sources.

**Decision: put the no-lock rationale in the `admin_actions.py` module docstring (or a comment
immediately above `bulk_ban_users`), never inside `bulk_ban_users`'s own body.** `inspect.getsource`
on a function begins at its decorator/def line, so a preceding comment is not part of the inspected
source. The invariant and the test are both kept unmodified, and the rationale is still discoverable
one screen above the function.

### `19-D3` — `19-G2`'s enforcement shape for the bulk path

Correction 5 shows `log_ban_account` today fires before the `UPDATE` for every candidate. Fixing
`19-G2` therefore means the audit write must be reached **only for targets that were actually
banned** — which requires the pre-filter from correction 6 to land first, so the permitted set is
known before the loop runs.

**Decision:** order the implementation as (i) resolve the actor, (ii) compute the permitted /
self-excluded / already-banned sets, (iii) run the audit loop over the **permitted-and-changing**
targets only, (iv) `UPDATE` with the privilege exclusions, the self-exclusion, and
`.filter(is_banned=False)` — in that order, inside the existing `transaction.atomic()`. The `UPDATE`
stays after the loop so `TestBanAtomicRollback::test_bulk_ban_users_atomic_on_log_failure` keeps its
meaning, and the `Implementor` must **verify that test still exercises what it claims** rather than
assume it.

### `19-D4` — the `B-1` Validator gate, re-scoped per ESC-3

`19-G5` is corrected to the concrete set from §11.2: the **3** `transaction.atomic` /
`select_for_update` source guards, the **3** message-text literal guards, and the **`18-Q7` behavioural
guards** (`test_moderator_cannot_target_a_superuser_or_staff_row`,
`test_superuser_can_target_a_staff_row`, `test_moderator_cannot_reactivate_a_superuser`) — plus, per
correction 2, `TestBulkLockingStructure::test_ban_user_for_ad_uses_atomic` as a **fourth** source
guard that must stay green in its positive form. `deactivation.py` and
`test_admin_deactivate_user.py` remain unmodified, and `makemigrations --check` must report none.

---

## 14. `B-1` task — issued to the `Implementor`

Produced by the `B-1` Planner from §11 (Researcher), §12 (Auditor) and §13 (coordinator
decisions `19-D1`..`19-D4`). Everything below is settled; the Implementor must not re-open it.

```yaml
# ── Plan 19, block B-1 ───────────────────────────────────────────────────────
# Verification is INLINE (see .ai/tasks/templates/task_template.yaml): the
# Implementor runs `tests_to_run` and `validation_commands` itself and checks
# `acceptance_criteria` before marking this task complete. Do NOT create a
# separate verification task. The B-1 Validator agent then performs the
# `19-G1`..`19-G6` gate review over the SAME commit.
#
# CITATION RULE (plan 19 §0): semantic anchors only — files, modules, classes,
# functions, methods, test node IDs, doc section headings. NO LINE NUMBERS, not
# in this task, not in the commit body, not in a comment or docstring you write.

id: 19-b1-ban-privilege-guard

title: "Guard the is_banned lever with a service-layer target scope, a BanResult, and a truthful ban toast"

priority: high

depends_on: []   # B-1 is the root of plan 19 (plan §3 "Dependencies: None upstream")

# ── Plan/Audit report source (REQUIRED when a task originates from a plan or audit) ──
source_reference: .ai\plans\19-moderation-privilege-guard-execution.md
source_section: "B-1 — Service-layer target scope for the ban path · HIGH RISK"
source_blocks:
  - "B-1 — Service-layer target scope for the ban path · HIGH RISK"
# Settled records this task is derived from — read them, do not re-derive them:
#   §11  B-1 Researcher record  (19-Q1 = Option A; facts (a)-(d); ESC-1..ESC-4)
#   §12  B-1 Auditor record     (12.2 corrections 1-7; 12.3 19-Q4 premise removed)
#   §13  Coordinator decisions  (19-D1 toast in B-1; 19-D2 no-lock rationale
#                                placement; 19-D3 audit-write ordering;
#                                19-D4 re-scoped Validator gate)
#   §4.1 the locking tripwire decision; §4.2 the compatibility guarantee
#   §2.3 / §7 / §9 / §10 explicit out-of-scope list
# Read-only reference (do not edit, do not "tidy", do not re-export):
#   src/backend/apps/users/services/deactivation.py
#   src/backend/apps/users/tests/test_admin_deactivate_user.py
# Repo rules: AGENTS.md, .kilo/rules/project.md, .kilo/rules/commands.md

description: >
  Close the `18-Q7` privilege-guard defect on the sibling lever `is_banned`, the way plan 18
  closed it for `is_active`. The requirement is verbatim and must not be weakened: "moderators
  may deactivate ordinary sellers, but must not be able to deactivate
  staff/superusers/other moderators." For the ban lever, today a moderator can ban a
  superuser, and `is_banned` is a *stronger* lockout than `is_active` because it blocks
  `can_login` and `can_publish_ad` and is read by the bot tier's `AccountStateMiddleware`.

  Per `19-Q1` the placement is **Option A, decided**: extend
  `src/backend/apps/moderation/admin_actions.py` in place. That module already owns **both**
  writers of `User.is_banned` in production code (§11.4 fact (d); `19-R5` found no third
  writer), so the rule gets exactly one home, zero new app-to-app import edges, and the two
  existing source tripwires keep working **unmodified**.

  The rule is a **target scope**, not an actor gate. Actor scope stays in the permission layer
  (`AdAdmin.has_view_permission` / `has_change_permission`, `moderation.views.decorators.staff_required`)
  and is **not touched**. Target scope goes into the service layer, so no caller — the
  `moderation:ban` view, the ads changelist action, or a future `manage.py shell` call — can
  bypass it. This is the split plan 18 documented at length in `deactivation.py`; blurring it
  is the specific failure this block exists to prevent.

  Three things land together in this one commit, because each is required for the other two
  to be correct: (1) the target scope on both ban writers, (2) a `BanResult` that reports
  refusals and reports **bans performed** rather than **rows seen** (fixing `G-3`'s false
  success), and (3) the minimal `AdAdmin.action_ban_user` toast correction that `19-D1` pulled
  forward from `B-2` so no commit ever renders a `NamedTuple` repr to an operator.

goals:
  - "A non-superuser operator cannot ban an `is_staff=True` OR `is_superuser=True` target, through EITHER ban writer; a superuser stays unrestricted. Both privilege axes are covered, including the `is_superuser=True, is_staff=False` row."
  - "Self-exclusion is unconditional on this lever — it applies to a superuser actor too. There is no un-ban path (`D-19-2`) and no per-request web gate for `is_banned`, so a self-ban is an operator lockout the UI cannot repair."
  - "`log_ban_account` is reached ONLY for targets that were actually banned. No `BAN_ACCOUNT` `ModeratorActionLog` row may exist for a ban that did not happen (`19-G2`). Today the bulk path writes the audit row *before* the write, for every candidate, including rows the guard will refuse."
  - "`changed` means bans performed, not user ids seen. A bare `UPDATE` reports MATCHED rows, so the writable set must carry a `.filter(is_banned=False)` pre-filter before `update()`'s return value is read as `changed`. This is the plan-18 trap; skipping it silently reintroduces the bug `DeactivationResult`'s own docstring warns about."
  - "The returned result makes a partly-refused selection representable (`changed == 0` with `skipped_privileged > 0`) so the operator surface can stop reading a refusal as a success."
  - "Guard and write stay co-located in the same function body. Both source tripwires stay green unmodified; the bulk path takes no row lock; the single-ad path keeps its existing legitimate lock."
  - "No migration, no new `StrEnum`, no new app-to-app import edge, no `print()`, and the four read-only-reference files come out byte-unchanged."

extra_context: |
  ## The rule, stated once (do not re-derive, do not paraphrase into something weaker)

  | Rule | `is_active` precedent (`deactivation._resolve_targets`) | Required on the ban path |
  |---|---|---|
  | Privilege predicate | `is_staff=True` OR `is_superuser=True` | Identical. **Both** members. `.exclude(is_superuser=True)` cannot be dropped: without it, a `is_superuser=True, is_staff=False` row slips through. |
  | Actor rule | superuser unrestricted; non-superuser excludes privileged | Identical. A non-superuser `moderator_id` is restricted. |
  | Self-exclusion | `pk = actor.pk`, unconditional, applies to a superuser too | Identical, and sharper here (no un-ban path, no per-request web gate). |
  | Category order | **self first, then privilege**, so a self+privileged row is counted once, as `skipped_self` | Identical. Required in both writers. |
  | Idempotence | already-in-state rows excluded from the write and counted | Identical: a second ban of an already-banned row is not a change. |
  | Locking | no `select_for_update` on the bulk `UPDATE` (documented, tripwire-tested) | Keep it. `ban_user_for_ad`'s existing lock is legitimate (read-then-write on an instance) and must be KEPT. |
  | Audit | `logger.info` naming the skipped counts | Mirror. `logger = logging.getLogger(__name__)` already exists at module level. **No `print()`** (repo rule 12). |
  | Result type | `DeactivationResult(NamedTuple)` | `BanResult(NamedTuple)`, field-for-field. Satisfies repo rule 10 with **no** new `StrEnum`; needs **no** migration. |
  | Schema | no migration | No migration. `is_banned` already exists. |

  ## `BanResult` — the exact contract (field-for-field mirror of `DeactivationResult`)

  ```
  changed            bans actually performed
  skipped_self       selected rows equal to the actor's own pk (counted first, never double-counted)
  skipped_privileged selected rows the actor may not touch: `is_staff=True` OR `is_superuser=True`
  already_in_state   rows the actor WAS permitted to touch that were already banned (a no-op)
  ```

  `changed` is the number of rows the pre-filtered `UPDATE` targeted, **because** the
  already-banned rows were removed first. A bare `UPDATE` reports matched rows, not changed
  rows (Postgres semantics) — the pre-filter exists for exactly that reason. A future editor
  must not remove it on the assumption that the database reports changes; the `BanResult`
  docstring must say so, mirroring `DeactivationResult`'s.

  ## `19-D3` — the required implementation order inside `bulk_ban_users`

  All four steps inside the **existing** `transaction.atomic()` block, in this order:

  1. resolve the actor (superuser or not) from `moderator_id`;
  2. compute the permitted / self-excluded / already-banned sets and the three counts;
  3. run the audit loop over the **permitted-and-changing** targets only, in ascending pk
     order, so the loop is deterministic;
  4. the single `UPDATE` carrying the privilege exclusions, the self-exclusion, and
     `.filter(is_banned=False)`.

  Step 4 stays **after** step 3 because
  `TestBanAtomicRollback::test_bulk_ban_users_atomic_on_log_failure` depends on the loop
  completing before the write. `19-D3` obliges you to **verify that test still exercises what
  its name claims** and to record the verification in the commit body — not assume it.
  The loop-then-`UPDATE` order also *fixes* today's inverse `19-G2` violation, where an audit
  row is written before the ban is known to have happened.

  ## The resolver — one home, both writers

  One module-private resolver is the single place the rule exists, and BOTH ban writers call
  it. `19-Q1`'s decisive trade-off is that the guard must live in the same function body as the
  write it constrains, because the only structural tripwires that exist are `inspect.getsource`
  guards on `ban_user_for_ad` and `bulk_ban_users` themselves. Do not split the predicate
  between the resolver and a second inline copy: that is two homes, and it is what Option `C`
  was rejected for.

  `moderator_id` is an **`int` pk**, not a `User` instance (Auditor correction 3). The
  superuser-unrestricted branch is therefore reproduced by a **lookup**, not by reading an
  attribute off a passed actor. Fail **closed**: a `moderator_id` naming no existing row is
  treated as a non-superuser, so it is restricted. That is the safe default for an input the
  repository has no legitimate producer for; record the decision in the commit body.

  The candidate set is built from the ids the caller supplies, so `None` and dangling ids
  simply match no row and are neither banned nor counted — which preserves the existing
  `if user_id:` tolerance of `bulk_ban_users` without a per-item guard in the loop.

  `ban_user_for_ad` still performs its own `select_for_update()` read of the target (that read
  is what makes the lock legitimate, and the tripwire asserts the lock is PRESENT), still keeps
  its `User.DoesNotExist` branch and the operator log line that goes with it, and then asks the
  shared resolver for the authoritative decision on that single pk. Re-asking the resolver
  rather than re-deriving the rule in the function body is deliberate: if the resolver is wrong,
  both writers are wrong identically. The cost is two extra cheap `SELECT`s on a single-moderator
  action, which is the correct trade against duplicating a security predicate (repo rules 5, 7).

  ## `19-D2` — where the no-lock rationale may and may not live

  `TestBulkLockingStructure::test_bulk_ban_users_not_locked` runs
  `inspect.getsource(bulk_ban_users)` and asserts `"select_for_update" not in src` over the
  **whole function source**. Two consequences an implementer gets wrong easily:

  * `inspect.getsource` of a function **starts at the `def` line and therefore INCLUDES the
    function's own docstring**. So `bulk_ban_users`'s docstring may describe the target scope,
    the result and the counts, but it **must not contain the literal token `select_for_update`**
    (or any spelling of it). Say "takes no row lock" and point at the module docstring.
  * The rationale itself goes in the **`admin_actions.py` module docstring** (preferred) or in a
    comment block **immediately above** `bulk_ban_users` — a preceding comment is not part of the
    inspected source. Never inside the function body. This mirrors what
    `deactivation.py` already does with its "Why no row lock" section sitting in the *module*
    docstring while all three of its guards inspect *function* sources.

  The positive counterweight: `TestBulkLockingStructure::test_ban_user_for_ad_uses_atomic`
  asserts `"select_for_update" in src` on `ban_user_for_ad`. That lock is a **positive** guard
  and it is the fourth source guard the B-1 Validator must see green (correction 2, `19-D4`).

  ## `19-D1` — the minimal `AdAdmin.action_ban_user` correction

  The live code binds `count = bulk_ban_users(...)` and interpolates
  `f"Banned {count} user(s)."` at `level="success"` (Auditor correction 1). Once the return type
  is a `BanResult`, that line renders the `NamedTuple` **repr** to the operator — `19-R1`'s exact
  failure mode arriving by accident. So the toast fix rides in `B-1`:

  * bind `result = bulk_ban_users(...)`;
  * interpolate `result.changed`, not the old `count`;
  * append the skip counts in the established `SKIPPED_ROWS_PREFIX` / dropped-clause shape,
    mirroring `UserAdmin._deactivation_message` in `src/backend/apps/users/admin.py`: a
    `Skipped:` label followed by the non-zero clauses only, among
    `N self`, `N privileged (not permitted)`, `N already in the requested state`.

  Three hard limits on that edit:

  * **Do not import `SKIPPED_ROWS_PREFIX` / `ALREADY_IN_STATE_CLAUSE` from `apps.users.admin`.**
    `ads/admin.py` importing from `users/admin.py` is a NEW app-to-app import edge and
    inverts the established direction. Define the label as a **module-level constant in
    `apps/ads/admin.py`**, with a short comment recording that the literal-duplication is
    deliberate so a test can pin it (that is exactly the pattern `apps/users/admin.py`
    documents for its own three constants).
  * **No two-sided tier truth in `B-1`.** The truthful statement — a ban refuses login and
    publishing, but does NOT revoke an existing web session — is `B-2`'s. Do not write
    "locked out everywhere", and do not add `WEB_ONLY_ENFORCEMENT`-style copy here.
  * **Do not add or change the `review.ban_user` notice.** `B-2` owns that surface, and
    `apps/moderation/views/review.py` is not in `files[]` below. `ban_user_for_ad` returning a
    value that this view discards is **not** a break; it is `B-2`'s input.
  * Leave `level="success"` exactly as it is and leave the reason literal
    `"Bulk ban via admin action"` untouched (note: the plan's `B-2` section misquotes it as
    `"Bulk ban via selected ads"`; the live value is the one above). Escalating the message
    level for a fully-refused selection is `B-2`'s decision, not `B-1`'s.

  ## i18n — no `.po` change in this block

  Per plan §6.2 the `AdAdmin` `message_user` toast is a **staff-only** surface following the
  shipped precedent recorded in `apps/users/admin.py`: deliberate English-only literals, no
  msgid. The i18n completeness gate `test_no_hardcoded_visible_text` scans **templates only**.
  No template is touched in `B-1`, therefore: run **no** `makemessages`, edit **no** `.po`, and
  confirm `.\Makefile.ps1 test` passes `test_i18n_completeness.py`. (`make makemessages` does not
  work on this platform anyway; the whole question is moot here.)

  ## Tests — why `B-1` needs its own

  The plan defers the twelve-test module to `B-3`. `B-3` cannot be the first place the guard is
  exercised: a security change that is not locally validatable cannot be reviewed, and `B-2`
  consumes `B-1`'s result type without being able to check that it is right. So `B-1` delivers
  the **minimum** that makes the change reviewable on its own commit, and `B-3` then **extends
  the same module** — it must not create a second file and must not rewrite what lands here.

  `B-1`'s minimum is exactly: the `18-Q7` guard proven on the bulk path, its positive half, the
  unconditional self-exclusion, the `changed`-means-bans-performed semantics, `19-G2` proven by
  absence of an audit row, the single-ad writer's guard, the `19-D1` toast contract, and one
  structural guard on the new resolver. A reviewer who cannot answer "does a moderator still get
  to ban a superuser, and does a refused ban leave an audit trail" from this commit has not been
  given enough.

  `B-3` retains the rest: the actor-reachability pair, the **view-path** self-ban, the fuller
  operator-message contract, the `moderation:ban` non-500 refusal, and the complete
  structural inventory.

  Conventions for the new module, from `src/backend/apps/users/tests/test_admin_deactivate_user.py`:

  * `pytestmark = [pytest.mark.django_db, pytest.mark.integration]` (both markers are registered
    in `pyproject.toml`; `integration` is a DB test, `seed` is unrelated and skipped by the gate).
  * **Module-local** `staff_user` / `superuser` fixtures built with `get_or_create` on a
    reserved `93xxxxxxx` `telegram_id` block, so `--reuse-db` works. `src/backend/conftest.py` is
    contended and supplies **no** admin or superuser fixture — do not add one. Bot tests cannot
    import the backend conftest at all; this module is backend-only.
  * The block **`9300003xx` is unclaimed** and is the one `B-1` reserves for this module.
    Taken already: `930000001`-`930000106` (`test_admin_change_form.py`,
    `test_admin_pii_containment.py`, `test_admin_change_form`/`test_support_admin.py`),
    `930000110`-`930000124` (`test_admin_deactivate_user.py`), `930000201`
    (`test_password_recovery.py`), `940000202` (cabinet), `9455xxxxx` (core). Re-check before
    committing, and never collide with `900000xxx` (moderation) or `99xxxxxxx` blocks.
  * Import `create_test_ad` from `conftest` exactly as `test_admin_actions.py` does; the
    existing `seller` / `user` / `category` / `city` fixtures come from `src/backend/conftest.py`.
  * The module docstring must record the **literal-guard discipline**: where a test asserts a
    hard-coded substring rather than an imported constant, that duplication is deliberate so a
    reword goes red, and a future editor must not "fix" it.
  * Assert **observable state and counts**, never query shapes. A test that re-derives the
    exclusion in the test body passes vacuously (`19-R12`).

  ## Explicitly NOT in this block

  * `apps/users/services/deactivation.py` — read-only reference, **byte-unchanged**. No
    shared-resolver extraction, no de-duplication of the predicate, no "tidying" of
    `users/services/__init__.py`.
  * `apps/users/tests/test_admin_deactivate_user.py` — **byte-unchanged**, and green.
  * `apps/moderation/tests/test_admin_actions.py` — **byte-unchanged** and green, both tripwires
    included. This is where the `19-R2` compatibility guarantee is proven: its two ban tests use a
    plain non-privileged, non-self moderator against the ordinary `seller` fixture, so the guard
    is a no-op for them and they must not need a single edit (`19-R11` needs no rule-2
    correction — Auditor confirmed the file contains no occurrence of `is_staff` or
    `is_superuser` at all).
  * `apps/moderation/services/moderation_log.py` — `log_ban_account` is a **caller**, not an
    enforcement point. Do not add a target check there; the guard belongs in `admin_actions.py`.
  * `apps/moderation/views/review.py`, `apps/moderation/views/decorators.py` — `B-2` owns the
    view; `staff_required` is the **actor** gate and must never grow a target check (`19-R7`).
  * `apps/users/admin.py` — mirror reference only. Do not import from it and do not edit it.
  * `apps/users/models.py`, `src/backend/conftest.py`, any `.po` catalog, any template, any
    migration, `docs/**` (`B-4`), `apps/seed/**`.
  * `UserRole.MODERATOR` (`D-19-1`), an un-ban path (`D-19-2`), a per-request `is_banned` web
    gate (`D-19-3`), a `ModeratorActionType.DEACTIVATE` member (`D-19-4`), the dead
    `<id>/password/` route (`D-19-5`), the `is_active`/`is_banned` taxonomy (`D-19-6`), and the
    stale `account_state.py` docstring (`D-19-7`). All are named out of scope in plan §2.3 and
    §7. Touching `MIDDLEWARE` is `19-R4` and is forbidden.
  * Do not invent a new `StrEnum` for refusal reasons. Counts only. (`19-Q4`'s
    `StrEnum`-of-reasons question is `B-2`'s, and §12.3 has already removed its premise.)

files:
  # ── File 1 ────────────────────────────────────────────────────────────────
  - path: src/backend/apps/moderation/admin_actions.py

    targets:
      - type: module          # module docstring: the `19-D2` no-lock rationale + rule statement
        name: admin_actions
      - type: class           # NEW
        name: BanResult
      - type: function        # NEW, module-private
        name: _resolve_ban_targets
      - type: function        # CHANGED
        name: ban_user_for_ad
      - type: function        # CHANGED
        name: bulk_ban_users

    semantic_anchors:
      # More than one anchor per slot, so each is a list of {type, value} pairs.
      # The template's single-pair form is the one-element case of this.
      insert_before:
        - type: function
          value: approve_ad
      insert_after:
        - type: class          # BanResult sits immediately after BanResult's
          value: DeactivationResult   # mirror counterpart in the read-only
                                        # reference module (different file —
                                        # use the repo's established
                                        # one-result-type-per-module
                                        # placement: directly above
                                        # `_resolve_ban_targets`)
        - type: function       # `ban_user_for_ad` — the shared resolver
          value: _resolve_ban_targets   # goes here, beside the two writers

  # ── File 2 ────────────────────────────────────────────────────────────────
  - path: src/backend/apps/ads/admin.py

    targets:
      - type: class
        name: AdAdmin
      - type: method          # CHANGED
        name: action_ban_user
      - type: method          # NEW, module-private; mirrors UserAdmin._deactivation_message
        name: _ban_message
      - type: assignment      # NEW module-level constant; do NOT import from apps.users.admin
        name: SKIPPED_BANNED_ROWS_PREFIX

    semantic_anchors:
      insert_before:
        - type: class
          value: AdAdminImageAdmin
      insert_after:
        - type: assignment
          value: _TIMESTAMP_FIELD_FOR_STATUS   # the constant belongs with the
                                               # other module-level operator
                                               # message constants, not inside
                                               # the class body

  # ── File 3 ────────────────────────────────────────────────────────────────
  - path: src/backend/apps/moderation/tests/test_admin_ban_privilege_guard.py

    targets:
      - type: file            # BRAND-NEW module. B-1 seeds it; B-3 EXTENDS this
        name: test_admin_ban_privilege_guard  # same file, never a second one.

    semantic_anchors:
      insert_after: []        # n/a — new file
      insert_before: []       # n/a — new file

changes:

  - action: add_code

    description: >
      (1) Extend the module docstring of `admin_actions.py` with two sections, in the style of
      `deactivation.py`'s module docstring: a "Ban target scope" section naming `19-Q1` /
      Option A, the three predicate rules, the self-then-privilege category order, the `int`-pk
      actor lookup, and the deliberate actor-scope/target-scope split; and a "Why no row lock on
      the bulk ban path" section carrying the rationale `19-D2` requires. Name the token
      `select_for_update` freely there — the module docstring is not in any inspected function
      source — and state that the note must stay outside `bulk_ban_users`'s body because
      `test_bulk_ban_users_not_locked` is a whole-function-source substring check.

    code_hint: |
      # module docstring, appended — template only, do not paste verbatim
      Ban target scope (plan 19 ``B-1``, ``19-Q1``/``19-Q7``)
      ----------------------------------------------------
      Both writers of ``User.is_banned`` in production code are in this module,
      so the rule has exactly one home here: a non-superuser ``moderator_id``
      may not ban an ``is_staff=True`` OR ``is_superuser=True`` row, nor their
      own row. A superuser is unrestricted. **Self-exclusion is unconditional,
      including for a superuser** — there is no un-ban path (``D-19-2``) and no
      per-request web gate for this flag, so a self-ban is an operator lockout
      the UI cannot repair. Skip categories are counted **self first, then
      privilege**, so a self+privileged row is counted once. Actor scope
      ("may this operator run the action") stays in the permission layer and is
      deliberately not re-implemented here; see ``deactivation.py`` for the
      same split on the ``is_active`` lever.

      Why no row lock on the bulk ban path
      ------------------------------------
      ``bulk_ban_users`` takes no ``select_for_update()``: a bare bulk ``UPDATE``
      does not read, and the privilege / self / already-banned exclusions are
      ``WHERE`` clauses evaluated by the database at write time, so a lock would
      buy nothing. ``ban_user_for_ad`` **does** lock, because it reads a row and
      writes fields from the read instance. **Do not "fix" the bulk path.**
      This rationale lives here, not in the function, because
      ``TestBulkLockingStructure::test_bulk_ban_users_not_locked`` asserts the
      token's absence over the whole function source — a docstring or comment
      inside ``bulk_ban_users`` that named it would fail the test.

  - action: add_code

    description: >
      (2) Add `BanResult(NamedTuple)` to `admin_actions.py` with the four mirror fields
      `changed`, `skipped_self`, `skipped_privileged`, `already_in_state` in that order. Its
      docstring must carry the `DeactivationResult` warning verbatim in spirit: a bare `UPDATE`
      reports MATCHED rows, so `changed` is only the bans-performed count **because** the
      writable set is pre-filtered to `is_banned=False`, and a future editor must not remove that
      filter. It must also state that self is checked before privilege so the skip categories
      never double-count a row. No persistence, no migration, no new `StrEnum` (repo rule 10 is
      satisfied by the `NamedTuple` itself).

    code_hint: |
      class BanResult(NamedTuple):
          """Outcome of a bulk ban. ``changed`` is bans performed ..."""

          changed: int
          skipped_self: int
          skipped_privileged: int
          already_in_state: int

  - action: add_code

    description: >
      (3) Add the module-private resolver `_resolve_ban_targets` to `admin_actions.py`, placed
      between the two ban writers. Signature: takes the candidate user **ids** (an iterable,
      because `bulk_ban_users` has a set of ids, not a `User` queryset) and the actor's
      `moderator_id: int`; returns `tuple[QuerySet[User], BanResult]`. Responsibilities, in
      order: (a) resolve the actor by lookup — `moderator_id` is an int pk, so the
      superuser-unrestricted branch is reproduced by asking the database whether that pk is a
      superuser, failing **closed** to "restricted" for an unknown pk; (b) build the candidate
      queryset from the ids, which naturally drops `None` and dangling ids so they are neither
      banned nor counted; (c) compute `skipped_self` first, then `skipped_privileged`; (d) return
      a writable queryset = permitted, minus the actor's own pk, filtered to `is_banned=False`,
      plus a `BanResult` with `changed=0` for the caller to replace. **Do not** put a row lock in
      this resolver: a lock here would apply to both writers and would defeat the documented
      policy. Its docstring is a safe place for the rationale, because no tripwire inspects it.

    code_hint: |
      def _resolve_ban_targets(
          user_ids: Iterable[int], moderator_id: int
      ) -> tuple[QuerySet[User], BanResult]:
          """Apply the ban target scope; return the writable set and the counts."""
          candidates = User.objects.filter(pk__in=set(user_ids))
          actor_is_superuser = User.objects.filter(
              pk=moderator_id, is_superuser=True
          ).exists()

          if actor_is_superuser:
              permitted = candidates
              skipped_privileged = 0
          else:
              permitted = candidates.exclude(is_staff=True).exclude(is_superuser=True)
              privileged = candidates.filter(is_staff=True) | candidates.filter(
                  is_superuser=True
              )
              skipped_privileged = privileged.exclude(pk=moderator_id).distinct().count()

          skipped_self = candidates.filter(pk=moderator_id).count()
          writable = permitted.exclude(pk=moderator_id).filter(is_banned=False)
          already_in_state = (
              permitted.exclude(pk=moderator_id).filter(is_banned=True).count()
          )
          return writable, BanResult(
              changed=0,
              skipped_self=skipped_self,
              skipped_privileged=skipped_privileged,
              already_in_state=already_in_state,
          )

  - action: add_code

    description: >
      (4) Change `ban_user_for_ad` in `admin_actions.py` to return `BanResult` instead of `None`,
      and to refuse a target the resolver excludes. Keep, unchanged: the `transaction.atomic()`
      block, the `User.objects.select_for_update().get(id=ad.user_id)` read **and its lock**, the
      `User.DoesNotExist` branch with its existing operator log line, the
      `user.save(update_fields=["is_banned"])` write, the `log_ban_account` call, and the
      `mask_telegram_id` log line. New shape, inside the existing atomic block: keep the locked
      read and the `DoesNotExist` early path (which now returns an all-zero `BanResult`), then ask
      `_resolve_ban_targets([user.pk], moderator_id)` for the authoritative single-target
      decision. Write, and reach `log_ban_account`, **only** when the resolver's writable set
      contains that pk — that is `19-G2` for this path, and it is why the audit call must not sit
      outside the guarded branch. A refused target gets a `logger.warning` naming the refusal
      reason (self / privileged / already banned) and a non-500, exception-free return. Outside
      the block, replace the current `changed=1` with
      `result = result._replace(changed=1)` where the write happened, then emit a single
      `logger.info` naming `changed` plus all three skip counts and a
      `target_scope=unrestricted|non_privileged_only` marker, mirroring `deactivate_users`, then
      return. Do not move `log_ban_account` out of the atomic block: that is what
      `TestBanAtomicRollback::test_ban_user_for_ad_atomic_on_log_failure` depends on.

  - action: add_code

    description: >
      (5) Change `bulk_ban_users` in `admin_actions.py` to return `BanResult` instead of `int`, in
      the `19-D3` order. Keep the id collection from the ad queryset and the existing
      `transaction.atomic()`. Inside the block: call `_resolve_ban_targets` first; then iterate
      the **writable** queryset in ascending pk order and call `log_ban_account` for each of
      those targets **only** (this replaces the current unconditional per-`user_id` loop and is
      the `19-G2` fix — no audit row may be written for a target the guard refuses or that was
      already banned); then issue **one** `UPDATE` on that same writable queryset and take
      `changed` from its return value. Keep the `UPDATE` **after** the loop. Keep
      `with transaction.atomic():` spelled literally in the body (the tripwire asserts it) and
      keep every occurrence of the row-lock token **out** of this function, including its own
      docstring. Return the replaced `BanResult` and emit one `logger.info` naming the counts and
      the actor's scope. `bulk_ban_users`' own docstring must document the new return type and the
      three counts, and must not contain the forbidden token.

    code_hint: |
      # ordering only — the existing `with transaction.atomic():` wraps all of it
      targets, result = _resolve_ban_targets(user_ids, moderator_id)

      for banned_id in targets.order_by("pk").values_list("pk", flat=True):
          log_ban_account(user_id=banned_id, moderator_id=moderator_id, reason=reason)

      result = result._replace(changed=targets.update(is_banned=True))

  - action: add_code

    description: >
      (6) `AdAdmin.action_ban_user` in `apps/ads/admin.py`: bind `result = bulk_ban_users(...)`
      and report it through the new private `AdAdmin._ban_message(result)`, mirroring
      `UserAdmin._deactivation_message`. `_ban_message` builds
      `f"Banned {result.changed} user(s)."` and, when any skip count is non-zero, appends
      `" Skipped: "` plus the non-zero clauses joined by `", "` — the same clause forms as the
      deactivation toast. Define `SKIPPED_BANNED_ROWS_PREFIX = "Skipped:"` as a module-level
      constant in this file with a comment recording that the literal is duplicated from
      `apps/users/admin.py` **on purpose**: importing it would create a new app-to-app import edge
      and inverts the established direction, and the duplication is what lets a test pin the
      literal. Add `BanResult` to the file's **existing**
      `from apps.moderation.admin_actions import (...)` statement — that edge already exists, so
      this is not a new one; do not open a second import statement for it. Leave `level="success"`
      and the reason literal `"Bulk ban via admin action"` exactly as they are. Do not add the
      two-sided tier truth and do not touch `review.ban_user`; both are `B-2`'s.

  - action: add_code

    description: >
      (7) New module `src/backend/apps/moderation/tests/test_admin_ban_privilege_guard.py` carrying
      `B-1`'s minimum behavioural proof (see `required_tests`). Module docstring records the
      literal-guard discipline. `pytestmark = [pytest.mark.django_db, pytest.mark.integration]`.
      Module-local `staff_user` / `superuser` fixtures via `get_or_create` on the reserved
      `9300003xx` block, plus a small `_make_user` helper, all copied from
      `test_admin_deactivate_user.py`. Do **not** add a fixture to `src/backend/conftest.py`.

tests_to_run:
  # B-1's minimum. B-3 extends this same module with the remaining inventory;
  # it must not re-create or rewrite these.
  new:
    - "src/backend/apps/moderation/tests/test_admin_ban_privilege_guard.py::test_moderator_cannot_ban_a_superuser_or_staff_row"
    - "src/backend/apps/moderation/tests/test_admin_ban_privilege_guard.py::test_superuser_can_ban_a_staff_row"
    - "src/backend/apps/moderation/tests/test_admin_ban_privilege_guard.py::test_moderator_cannot_ban_themselves"
    - "src/backend/apps/moderation/tests/test_admin_ban_privilege_guard.py::test_bulk_ban_users_reports_bans_performed_not_rows_seen"
    - "src/backend/apps/moderation/tests/test_admin_ban_privilege_guard.py::test_bulk_ban_users_is_idempotent_on_repeat"
    - "src/backend/apps/moderation/tests/test_admin_ban_privilege_guard.py::test_a_refused_ban_writes_no_ban_account_audit_row"
    - "src/backend/apps/moderation/tests/test_admin_ban_privilege_guard.py::test_ban_user_for_ad_refuses_a_privileged_owner"
    - "src/backend/apps/moderation/tests/test_admin_ban_privilege_guard.py::test_operator_toast_reports_bans_performed_and_skipped_rows"
    - "src/backend/apps/moderation/tests/test_admin_ban_privilege_guard.py::TestBanScopeStructure::test_resolve_ban_targets_takes_no_row_lock"
  untouched_but_must_stay_green:
    - "src/backend/apps/moderation/tests/test_admin_actions.py::TestBulkLockingStructure::test_bulk_ban_users_not_locked"
    - "src/backend/apps/moderation/tests/test_admin_actions.py::TestBulkLockingStructure::test_ban_user_for_ad_uses_atomic"
    - "src/backend/apps/moderation/tests/test_admin_actions.py::TestBanAtomicRollback::test_ban_user_for_ad_atomic_on_log_failure"
    - "src/backend/apps/moderation/tests/test_admin_actions.py::TestBanAtomicRollback::test_bulk_ban_users_atomic_on_log_failure"
    - "src/backend/apps/moderation/tests/test_admin_actions.py"   # whole module: the 19-R2 guarantee
    - "src/backend/apps/users/tests/test_admin_deactivate_user.py" # whole module: unmodified
    - "src/backend/apps/moderation/tests/test_decorators.py"        # staff_required untouched
    - "src/backend/apps/moderation/tests/test_moderation_views.py"
    - "src/backend/apps/ads/tests/test_admin_change_form.py"
    - "src/backend/apps/ads/tests/test_admin_pii_containment.py"
    - "src/backend/apps/ads/tests/test_edit.py::TestBannedSellerRelistKnownGap"
    - "src/telegram_bot/tests/test_account_state_deactivation_probe.py"
    - "src/backend/apps/core/tests/test_i18n_completeness.py"

validation_commands:
  # Docker only. NEVER bare `uv run pytest` — there is no DB on localhost:5432.
  fast_gate: '.\Makefile.ps1 test'        # authoritative; skips the `seed` marker
  targeted: >
    $dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'
    $dc run --rm -e PYTEST_OPTS="-k ban" test
    # Caveat from .kilo/rules/commands.md: setting PYTEST_OPTS REPLACES the defaults, so a
    # targeted run loses xdist parallelism and --reuse-db. Bare file paths and single-token
    # values work; a quoted multi-token value such as -k "a b" does NOT.
  full_suite: "NOT required — no seeding or image path is touched"
  test_recreate: "NOT required — no migration may be generated; do not run it"
  lint: >
    uv run ruff check src/backend/apps/moderation/admin_actions.py
    uv run ruff check src/backend/apps/moderation/tests/test_admin_ban_privilege_guard.py
    uv run ruff check src/backend/apps/ads/admin.py
  typecheck: >
    uv run basedpyright src/backend/apps/moderation/admin_actions.py
    uv run basedpyright src/backend/apps/moderation/tests/test_admin_ban_privilege_guard.py
    uv run basedpyright src/backend/apps/ads/admin.py
    # No new suppression. The only tolerated suppression is the verbatim existing
    # `# pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed;
    # Atomic.__enter__/__exit__ untyped` already carried on this module's atomic lines.
    # Neither rewritten function adds a new `atomic()` block, so no new suppression should be
    # needed. If basedpyright demands one on a line you did not add, STOP and escalate.
  no_migration: >
    $dev = 'docker compose --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.override.yml --project-name mko-bazuna-dev'
    $dev run --rm --no-deps --entrypoint "" web python src/backend/manage.py makemigrations --check --dry-run
    # Must report no changes. A generated migration is a B-1 failure, not a follow-up.
  i18n: 'No .po edit. Confirm `.\Makefile.ps1 test` passes test_i18n_completeness.py.'
  diff_audit: >
    git status --porcelain   # exactly three paths may appear: the two production files and
                             # the one new test module. Anything else is out of scope —
                             # especially src/backend/apps/users/**, the .po catalogs, and
                             # every template.
    git diff --stat -- src/backend/apps/users/services/deactivation.py src/backend/apps/users/tests/test_admin_deactivate_user.py src/backend/apps/moderation/tests/test_admin_actions.py
    # Must be empty: those three are read-only/tripwire-protected.

architectural_constraints:
  - "One home for the rule. The privilege + self + already-banned predicate exists in exactly one place, `_resolve_ban_targets`, and BOTH ban writers call it. A second inline copy in a function body is a defect, not a convenience."
  - "Actor scope (permission layer) vs target scope (service layer) must not be blurred. Do NOT add a target check to `staff_required` / `staff_required_api`, to `AdAdmin.has_view_permission` / `has_change_permission`, or to `AdAdmin`'s `actions` / `permissions=`. Django's `permissions=` can only express actor scope; enforcing a per-row scope in a caller is the exact mistake plan 18 moved out of the view and into the service."
  - "Source tripwire #1, negative: `TestBulkLockingStructure::test_bulk_ban_users_not_locked` — `bulk_ban_users` keeps NO row lock, and its own docstring may not contain the token. If it goes red, the fix is in the production code, never in the test (`19-R3`, plan §4.1)."
  - "Source tripwire #2, positive: `TestBulkLockingStructure::test_ban_user_for_ad_uses_atomic` — `ban_user_for_ad` KEEPS its `select_for_update()` and its `transaction.atomic`."
  - "Tripwire #3, the rollback pair: `TestBanAtomicRollback` — the ban write and its audit row must stay in one `atomic()` block, and the bulk `UPDATE` must stay AFTER the audit loop. `19-D3` requires you to verify `test_bulk_ban_users_atomic_on_log_failure` still exercises what its name claims and to record that verification in the commit body."
  - "Read-only reference files — byte-unchanged: src/backend/apps/users/services/deactivation.py, src/backend/apps/users/tests/test_admin_deactivate_user.py, src/backend/apps/moderation/tests/test_admin_actions.py, src/backend/apps/moderation/services/moderation_log.py, src/backend/apps/users/models.py, src/backend/apps/users/admin.py, src/backend/apps/moderation/views/review.py, src/backend/apps/moderation/views/decorators.py, src/backend/conftest.py, and every locale `.po` catalog."
  - "No new app-to-app import edge. `admin_actions.py` gains no new cross-app import at all; the two additions are stdlib/framework only (`typing.NamedTuple`, `typing.Iterable`, `django.db.models.QuerySet`) plus the module-local `User`, which is already imported. `apps/ads/admin.py` adds `BanResult` to its EXISTING `from apps.moderation.admin_actions import (...)` statement, so that edge is unchanged — and it must NOT gain an import of `apps.users.admin`."
  - "No migration, no new model, no new field, no new `StrEnum`, no new index. `is_banned` already exists. Repo rule 10 is satisfied by the `NamedTuple` result type."
  - "No `print()` anywhere (repo rule 12). `logger = logging.getLogger(__name__)` already exists at module level; use `logger.info` for the count summary, `logger.warning` for a refused target. Reuse the already-imported `mask_telegram_id` for PII in log output."
  - "English only (repo rule 1): docstrings, comments, log messages and the operator toast are clear English."
  - "Small focused units (repo rules 4, 5, 7): the resolver does the scope and the counts and nothing else; the two writers do their own writes; the toast lives in one private method. Follow the established patterns rather than introducing new abstractions."
  - "Docs are NOT in this block. `B-4` owns every doc edit; `docs/02-database/db-enums.md` and `docs/02-database/db-retention.md` must stay byte-unchanged, and `18-D4` must not be presented as settled."

required_tests:
  location: >
    src/backend/apps/moderation/tests/test_admin_ban_privilege_guard.py — BRAND NEW in B-1, and
    the SAME module B-3 extends. Not `test_admin_actions.py` (tripwire home, heavily contended,
    second concern) and not a bot test (there is no bot writer of `is_banned`).
  conventions: >
    Module docstring records the literal-guard discipline. `pytestmark = [pytest.mark.django_db,
    pytest.mark.integration]`. Module-local `staff_user` / `superuser` via `get_or_create` on the
    reserved unclaimed `9300003xx` block, plus a `_make_user` helper, copied from
    test_admin_deactivate_user.py. `create_test_ad` imported from `conftest` as
    test_admin_actions.py does. Assert observable state and counts, never query shapes; never
    re-derive the exclusion inside a test body (`19-R12`).
  why_this_is_the_minimum: >
    B-3 owns the twelve-test module, but B-1 cannot be reviewed without a locally runnable proof
    that (a) a moderator can no longer ban a privileged row, (b) a superuser still can, (c) self
    is refused unconditionally, (d) `changed` means bans performed, (e) a refused ban leaves no
    `BAN_ACCOUNT` row, (f) the single-ad writer is guarded too, (g) the toast is truthful, and
    (h) the new resolver did not grow a lock. A reviewer who cannot answer those eight questions
    from this commit has been given too little; a reviewer who has those eight does not need the
    remaining four tests to sign off. Those four (actor-reachability pair, view-path self-ban,
    the fuller operator-message contract, and the `moderation:ban` non-500 refusal) depend on
    `B-2`'s messaging, so they belong in `B-3`.
  inventory:
    - name: test_moderator_cannot_ban_a_superuser_or_staff_row
      asserts: >
        The `18-Q7` guard for the ban lever — the most important test in the plan. A moderator
        drives `bulk_ban_users` over a selection of {ordinary seller, peer `is_staff` moderator,
        full superuser, AND a `is_superuser=True, is_staff=False` row}. Assert
        `result.changed == 1` and `result.skipped_privileged == 3`; the seller is banned; the
        other three rows are untouched after `refresh_from_db`. The fourth row is precisely why
        `.exclude(is_superuser=True)` cannot be dropped — with only the two-flag superuser
        fixture present, dropping it would go undetected.
    - name: test_superuser_can_ban_a_staff_row
      asserts: >
        The positive half, so the guard cannot be over-applied: a superuser acting on a peer
        `is_staff` row gets `changed == 1`, `skipped_privileged == 0`, and the row is banned.
    - name: test_moderator_cannot_ban_themselves
      asserts: >
        Self-exclusion at the service layer: a moderator's own row in the selection yields
        `changed == 0`, `skipped_self == 1`, and the row stays unbanned. Cover the superuser
        variant too (a superuser is unrestricted **except** for their own row — `19-Q3`), since
        that is the branch a naive `is_superuser` shortcut drops. The reachable view-path
        self-ban ("ban the owner of an ad you authored") is `B-3`'s test.
    - name: test_bulk_ban_users_reports_bans_performed_not_rows_seen
      asserts: >
        The plan-18 trap, pinned. A superuser selects {one unbanned seller, one already-banned
        seller, one privileged row}. Assert `changed == 1` — not 2, not 3 —
        `already_in_state == 1`, `skipped_privileged == 0` (a superuser is unrestricted, so the
        privileged row IS banned; use a moderator for the privileged part or a separate
        selection), and that exactly one `BAN_ACCOUNT` audit row was written. A bare `UPDATE`
        would report 2 here.
    - name: test_bulk_ban_users_is_idempotent_on_repeat
      asserts: >
        A second identical `bulk_ban_users` call reports `changed == 0` and
        `already_in_state == 1`, and writes no second `BAN_ACCOUNT` row. This also fixes the
        audit-trail asymmetry the Auditor found: today a repeat bulk ban writes a duplicate row.
    - name: test_a_refused_ban_writes_no_ban_account_audit_row
      asserts: >
        `19-G2`, proven by absence. A moderator's selection containing a privileged row and a
        self row produces zero `ModeratorActionLog` rows with
        `ModeratorActionType.BAN_ACCOUNT` for either of them, and exactly one for the permitted
        seller. This is the assertion that goes red against today's code, where the audit row is
        written before the guard is even consulted.
    - name: test_ban_user_for_ad_refuses_a_privileged_owner
      asserts: >
        `G-1`, the single-ad writer. A moderator runs `ban_user_for_ad` on an ad whose owner is a
        superuser (and, in the same test or a sibling case, on an ad the moderator authored):
        `changed == 0`, the target is not banned after `refresh_from_db`, and no `BAN_ACCOUNT`
        row exists. Include the positive control that the same call against an ordinary seller
        still bans and still audits, so the test cannot pass vacuously.
    - name: test_operator_toast_reports_bans_performed_and_skipped_rows
      asserts: >
        The `19-D1` correction, at the minimum contract `B-1` owns. Drive the real endpoint
        `admin:ads_ad_changelist` with `action=action_ban_user` over a mixed selection as a
        moderator and read the messages off the response. Assert **hard-coded** literals, not
        imported constants: `"Banned 1 user(s)"`, `"Skipped:"`, `"1 privileged"`. Also assert
        the `NamedTuple` repr is absent — the specific regression `19-D1` exists to prevent.
        The fuller messaging contract (tier truth, no total-lockout claim) is `B-3`'s tests #9
        and #10.
    - name: "TestBanScopeStructure::test_resolve_ban_targets_takes_no_row_lock"
      asserts: >
        One structural source guard on the NEW function, mirroring the existing
        `test_bulk_ban_users_not_locked` precedent: `inspect.getsource(_resolve_ban_targets)`
        contains no `select_for_update`. A lock there would apply to both writers, and neither
        of the two existing tripwires could see it. Document in the class docstring what
        substring guards do and do not prove.

acceptance_criteria:
  # ── 19-G1 ──────────────────────────────────────────────────────────────────
  - "19-G1 — the commit body names the placement option as Option A with the Researcher's four
     facts (a) caller inventory, (b) literal-tripwire classification, (c) import precedent,
     (d) `is_banned` writer inventory — and the decisive trade-off: the guard must stay in the
     same function body as the write it constrains, because both structural tripwires inspect
     those two functions and one of them asserts a lock is PRESENT. Also record that Option C is
     rejected on cost, not on test-redness, per §11.5."
  - "The guard lives in `_resolve_ban_targets` in `admin_actions.py` and is called by BOTH
     `ban_user_for_ad` and `bulk_ban_users`. No second implementation of the predicate exists
     anywhere in the repo, and no caller-side check was added."
  # ── 19-G2 ──────────────────────────────────────────────────────────────────
  - "19-G2 — `log_ban_account` is unreachable for a refused target on BOTH writers. No
     `BAN_ACCOUNT` `ModeratorActionLog` row exists for a ban that did not happen, and a repeat
     bulk ban writes no duplicate row. Pinned by
     `test_a_refused_ban_writes_no_ban_account_audit_row`."
  # ── 19-G3 ──────────────────────────────────────────────────────────────────
  - "19-G3 — no row lock added to `bulk_ban_users` or to `_resolve_ban_targets`.
     `TestBulkLockingStructure::test_bulk_ban_users_not_locked` and
     `test_ban_user_for_ad_uses_atomic` are both green and both unmodified; the second keeps its
     positive lock assertion satisfied by the existing `select_for_update()` read."
  - "The no-lock rationale for the bulk ban path lives in the `admin_actions.py` module docstring
     (or a comment immediately above `bulk_ban_users`) and is NOT inside either function's own
     body, per 19-D2."
  # ── 19-G4 ──────────────────────────────────────────────────────────────────
  - "19-G4 — no migration (`makemigrations --check --dry-run` reports no changes); no new
     `StrEnum`; the result type is a `BanResult(NamedTuple)` with exactly the four mirror fields;
     no `print()` — `logger = logging.getLogger(__name__)` is the only output path."
  # ── 19-G5 (re-scoped by 19-D4) ─────────────────────────────────────────────
  - "19-G5 — `src/backend/apps/users/services/deactivation.py`,
     `src/backend/apps/users/tests/test_admin_deactivate_user.py` and
     `src/backend/apps/moderation/tests/test_admin_actions.py` are byte-unchanged (confirm with
     `git diff --stat`), and their tripwires all still fire: the 3
     `transaction.atomic`/`select_for_update` source guards, the 3 message-text literal guards,
     and the 3 `18-Q7` behavioural guards
     (`test_moderator_cannot_target_a_superuser_or_staff_row`,
     `test_superuser_can_target_a_staff_row`, `test_moderator_cannot_reactivate_a_superuser`)."
  # ── 19-G6 ──────────────────────────────────────────────────────────────────
  - '19-G6 — `.\Makefile.ps1 test` green, or the exact failing node IDs recorded in the commit
     body with a one-line reason each. No test was weakened, deleted, or skipped to get there.'
  # ── 19-D1 ──────────────────────────────────────────────────────────────────
  - "19-D1 — `AdAdmin.action_ban_user` interpolates `result.changed` and appends the
     `SKIPPED_ROWS_PREFIX` dropped clauses; it cannot render a `BanResult` repr at any
     intermediate commit state. It does NOT yet carry the two-sided tier truth and does NOT add
     the `review.ban_user` notice — both are `B-2`'s. `SKIPPED_BANNED_ROWS_PREFIX` is a
     module-level constant in `apps/ads/admin.py`; there is no import of `apps.users.admin`."
  # ── 19-D3 ──────────────────────────────────────────────────────────────────
  - "19-D3 — inside `bulk_ban_users`'s existing `transaction.atomic()` the order is: resolve
     actor, compute permitted/self-excluded/already-banned, audit loop over permitted-and-changing
     targets only, then the single pre-filtered `UPDATE`. The `UPDATE` is still AFTER the loop, and
     the commit body records the explicit verification that
     `test_bulk_ban_users_atomic_on_log_failure` still exercises what its name claims."
  # ── 19-Q2 / 19-Q3 ──────────────────────────────────────────────────────────
  - "19-Q2 — a non-superuser operator is refused `is_staff=True` OR `is_superuser=True` targets
     on both writers, including the `is_superuser=True, is_staff=False` row; a superuser is
     unrestricted. The requirement is not weakened anywhere."
  - "19-Q3 — self-exclusion is unconditional and applies to a superuser actor too."
  # ── compatibility and hygiene ──────────────────────────────────────────────
  - "Compatibility (plan §4.2) — every existing ban test in `test_admin_actions.py` against an
     ordinary, non-privileged, non-self target stays green unmodified. The guard is a no-op for
     that case; any breakage there is a defect in this change, not in the test."
  - "`admins` actor gate untouched — no change to `staff_required`, `staff_required_api`,
     `AdAdmin.has_view_permission`, `AdAdmin.has_change_permission`, `AdAdmin.actions`, or any
     `permissions=` list. `test_decorators.py` and `test_moderation_views.py` stay green."
  - "Exactly three paths in `git status --porcelain`: `src/backend/apps/moderation/admin_actions.py`,
     `src/backend/apps/ads/admin.py`, and the new
     `src/backend/apps/moderation/tests/test_admin_ban_privilege_guard.py`. No template, no `.po`,
     no doc, no migration, no `src/backend/conftest.py`."
  - "This task's block is `B-1` only. `B-2` (both operator surfaces, the two-sided tier truth, the
     `review.ban_user` notice), `B-3` (the remaining tests, extending this same module) and `B-4`
     (docs) are untouched, and none of their symbols was pre-empted here."

open_questions: []
resolved_by_this_task:
  - >
    "Does `bulk_ban_users` take an extra `SELECT` because `ban_user_for_ad` shares the resolver?
    Yes, and that is the decision: two cheap `SELECT`s on a single-moderator action, traded for a
    single authoritative implementation of a security predicate. The alternative — a second,
    narrower private predicate for the single-ad path — was rejected because it creates two homes
    for the same rule, which is the failure mode `19-Q1` was decided against. If the coordinator
    overrides this, the override is a coordinator decision recorded in the commit body, not a
    silent edit."
  - >
    "What happens when `moderator_id` names no existing `User` row? Fail CLOSED: treat the actor as
    non-superuser, so the selection is restricted. The Researcher found no production or test
    producer for such an id, and failing closed is the safe default for a nonsense input. Recorded
    here so the next editor does not read it as an oversight."
  - >
    "Do B-1's tests go in a new module or in `test_admin_actions.py`? A new module, at the exact
    path B-3 is specified to own, so B-3's work is purely additive and the tripwire file stays
    byte-unchanged. This is a sequencing decision, not a change to B-3's inventory."
not_blocking:
  - >
    "B-2 still owes the message-layer decision that `19-Q4` left open after §12.3 removed its
    premise, and owes the escalation of the toast level for a fully-refused selection. Neither
    blocks B-1; `B-1` makes the refusal visible, which is what `19-R1` requires."
```

---

## 15. `B-1` gate result — **ACCEPT** (`a1f8229`)

All 15 gate checks **PASS**: `19-G1`, `19-G2`, `19-G3`, `19-G4`, `19-G5`, `19-G6`, `19-D1`,
`19-D3`, `19-Q2`, `19-Q3`, plus scope, architectural fit, test quality, quality gates,
regressions, and the reported failure. `.\Makefile.ps1 test` on `a1f8229`: **2832 passed, 0
failed**. `ruff` clean, `basedpyright` **0 errors / 0 warnings / 0 notes**, zero added
suppressions, no migration.

**Mutation check on the requirement (gate 7).** Removing `.exclude(is_superuser=True)` from the
writable predicate turns `assert result.changed == 1` **and** `assert superuser_only.is_banned is
False` red — two independent assertions, because the test carries the `is_superuser=True,
is_staff=False` row that the two-flag superuser fixture would have masked. `skipped_privileged == 3`
would still pass, which is exactly why `changed` and the per-row `refresh_from_db()` assertions are
the load-bearing ones. The test is not vacuous.

**Reported failure adjudicated: pre-existing flake, not caused by `a1f8229`.** `git diff` over
`src/backend/apps/search/` is empty; nothing on the ban path executes during a `/search/` GET;
`1257603` touches alert-delivery paths behind `IMMEDIATE_ALERTS_ENABLED = False`, also not on the
request path. Root cause is a wall-clock assertion (`elapsed_ms <= 2000`) on a loaded host, in
`test_search_slo.py`. Not fixed by this plan.

### 15.1 Coordinator disposition of the Validator's findings

| # | Finding | Disposition |
|---|---|---|
| 1 | `_ban_refusal_reason` was not in §14's `files[].targets`, and its `"not_in_target_set"` branch is unreachable (`ban_user_for_ad` passes exactly `[user.pk]`, so `candidates` always contains it). | **`B-2`** — drop the unreachable branch or replace it with an assertion that names the invariant. Scope creep in the Implementor's file, cheap to close, and an untested default branch is a trap. |
| 2 | Both writers re-run `User.objects.filter(pk=moderator_id, is_superuser=True).exists()` **purely to label a log string** — a **fourth** expression of a check `_resolve_ban_targets` already performed in the same call, costing an extra round-trip per ban. Worse, the marker is evaluated **after** the `atomic()` block commits, so it can in principle report a scope different from the one that actually governed the write. §14's `resolved_by_this_task` also **understated** the cost ("two extra cheap `SELECT`s"). | **`B-2` — mandatory.** This is a *reporting* defect on a block whose entire purpose is truthful reporting: a marker that can name the wrong scope is the same false-success class as `G-3`/`G-4`. Fix by having the resolver surface the scope it actually applied, and drop the redundant query. Correct the cost disclosure in the same commit body. |
| 3 | The self-then-privilege "counted once" rule is only half-pinned: no test asserts `skipped_privileged == 0` for a self **and** privileged row, so dropping `.exclude(pk=moderator_id)` from the privileged **count** would not go red. Write scope is unaffected, so this is a reporting-accuracy hole, not a security hole. | **`B-3`** — one added line in `test_moderator_cannot_ban_themselves`. |
| 4 | `apps/moderation/views/review.py::ban_user` unconditionally logs `"Admin %s banned user via ad %s"` after **discarding** the new `BanResult`. For a refused ban that line is now **false** — a second false-success surface. | **`B-2` — mandatory.** `review.py` is B-2's file; the plan would otherwise *introduce* the defect it exists to remove. |
| 5 | The actor-privilege decision is read without a lock, so a concurrent demotion between decision and `UPDATE` could in principle apply a stale scope. | **No action.** Identical to the shipped `deactivation._resolve_targets` precedent; locking it would contradict the documented no-lock policy. Recorded in §7 as a residual. |
| 6 | §11.2 counts "Seventeen test functions" in `test_admin_deactivate_user.py`; there are **16**. | **Correction only.** The file is read-only and unchanged; no gate depends on the count. |

Findings 1, 2 and 4 are therefore **added to `B-2`'s scope**. Finding 3 is **added to `B-3`'s
inventory**. Finding 5 joins the §7 deferred register. Finding 6 corrects §11.2.

---

## 16. `B-2` decisions — `2026-10-03`

From the bounded Researcher pass (items 1–8, each CONFIRMED except item 5, which **corrects** the
block's premise).

### `19-D5` — `19-Q4` RESOLVED: the `messages` framework, **no** `.po` change, **no** template change

`ban_user` redirects to `/admin/ads/ad/?status__exact=on_moderation` — the Django admin changelist.
That target inherits Django's shipped `admin/change_list.html` → `admin/base_site.html` →
`admin/base.html`, which renders `{% block messages %}`; the project overrides **no** admin chrome
template (`src/backend/templates/admin/` holds only `moderation/review.html` and
`moderation/queue.html`); and `django.contrib.messages.context_processor.messages` is enabled. **A
`messages.*` call posted before the redirect is genuinely visible.** The silent-no-op failure mode
does not apply.

**The i18n premise in §6.2 is CORRECTED for this surface.** `approve_ad`'s outcome sentences live in
`_APPROVE_OUTCOME_MESSAGES`, a module-level `dict[ApproveOutcome, str]` of **English Python
literals**, and appear in **zero** `.po` files for `ru`, `bs` or `en`. The rendering template is
Django's own untranslated admin chrome, and `test_no_hardcoded_visible_text` scans **project
templates only** — a Python literal handed to `messages.*` is invisible to it.

**Decision:** `B-2` adds its refusal sentences to a module-level mapping in `review.py`, exactly as
`_APPROVE_OUTCOME_MESSAGES` does. **No `.po` edit, no `makemessages`, no template edit.** The
`ru`/`bs` obligation would trigger **only** if a new string were rendered into
`templates/admin/moderation/review.html` — which B-2 must not do.

### `19-D6` — message levels: `warning` in the view, `error` for a fully-refused admin action

The repo is genuinely split, so this is a recorded choice, not an accident:

| Surface | Level | Precedent relied on |
|---|---|---|
| `review.py::ban_user` refusal | `messages.warning` | `approve_ad` — the **only** `messages.*` call anywhere in `src/` is `messages.warning` in this same view. Module-internal consistency wins. |
| `AdAdmin.action_ban_user`, **fully refused** selection (`changed == 0` with a non-zero skip) | `level="error"` | `AdAdmin`'s own refusal paths (`MaxAdsExceeded`, transition `ValueError`) already use `level="error"`. "The action did not take effect" is error. |

Recorded counter-precedent: `UserAdmin.deactivate_user` / `reactivate_user` report the structurally
identical skip-count case at the **default INFO** level, with no `level=` argument. B-2 deliberately
**does not** copy that, because B-2's subject is "did this action take effect", and a `success`-level
toast on a fully-refused selection is precisely the false-success class this plan exists to remove.
A **partial** success keeps its existing level — only the fully-refused case escalates.

### `19-D7` — finding 2 fixed by widening the resolver's return, not `BanResult`

Both writers re-run `User.objects.filter(pk=moderator_id, is_superuser=True).exists()` purely to
label a `target_scope=` log marker, in the eager argument list of a `logger.info` **after** the
`atomic()` block — so it costs a round-trip on every ban, is evaluated even when INFO is disabled,
and can in principle report a scope different from the one that governed the write.

**Decision: widen `_resolve_ban_targets` to a 3-tuple carrying the scope marker**, per the
Researcher's option (a). The resolver already computes `actor_is_superuser` exactly once as its own
branch predicate, so this is free. Rejected: adding a `scope` member to `BanResult` — it churns
every `BanResult` construction site (three in production, several in tests) for a **log-only**
concern, which is rule 5 over-engineering. `test_admin_ban_privilege_guard.py::TestBanScopeStructure::test_resolve_ban_targets_takes_no_row_lock`
asserts only token absence, so the arity change is safe under it.

**Also recorded, not actioned:** the marker literals `"unrestricted"` / `"non_privileged_only"` are
duplicated four times — twice in `admin_actions.py`, twice in the read-only `deactivation.py`. A
shared `StrEnum` cannot be introduced without editing a read-only file, so the duplication stands.
B-2 must not "fix" half of it.

### `19-D8` — finding 1 resolved as a documented invariant, not a deletion

`_ban_refusal_reason`'s `"not_in_target_set"` branch is unreachable **for today's only caller**
(`ban_user_for_ad` passes exactly `[user.pk]`, so `candidates` always contains the tested row), but
the branch is what makes the helper's `-> str` return **total** for a caller that does not. The
Researcher's analysis shows every refusal path maps onto a counted category.

**Decision: keep the branch, document the totality invariant in the docstring.** No `StrEnum` for a
log-only reason vocabulary (rule 5). Dropping it would make the helper partial on a `str` return,
which is worse than a documented fallback.

### `19-D9` — a newly discovered structural tripwire in `B-2`'s file

`src/backend/apps/moderation/tests/test_moderation_views.py::TestBanUserView` (and
`::test_ban_user_uses_select_for_update_and_atomic`) inspect **`review.ban_user`'s own source** for
the `transaction.atomic` and `select_for_update` tokens. **Both must remain.** `B-2` edits this
function's body, so this is the highest-risk tripwire in the block: any refactor that moves the
`atomic()` block out of `ban_user`, or relocates the locked read, goes red. `B-2` must confirm both
survive unmodified, and the test module must come out byte-unchanged.

---

## 17. `B-2` gate result — `8d0486f`, pending validation

### `19-D10` — `19-D8` **CORRECTED** by the `B-2` Implementor; the deviation is ACCEPTED

`8d0486f` did two things `19-D8` did not authorise: it added a `BanRefusalReason(StrEnum)` and
promoted `ban_refusal_reason` from module-private to cross-module. **Both are accepted, and
`19-D8` is corrected in hindsight — the instruction, not the code, was wrong.**

`19-D8` said *"do not introduce a `StrEnum` for a log-only reason vocabulary"*, reasoning from repo
rule 5 (avoid overengineering). But the same `B-2` brief also required the view's refusal mapping to
be a **module-level, explicitly-typed `dict` keyed by a `StrEnum`**, mirroring
`_APPROVE_OUTCOME_MESSAGES: dict[ApproveOutcome, str]`. Those two instructions are mutually
unsatisfiable: the vocabulary cannot be "log-only" while it is simultaneously the key type of a
public mapping. `19-D8` was internally inconsistent, and the Implementor resolved it in the only
direction the rest of the rules allow.

| Rule | Effect | How the implementation complies |
|---|---|---|
| **10** — fixed values must use `StrEnum` | favours the enum | One type, four members, one vocabulary shared by producer and message mapping — instead of bare literals in `admin_actions` **and** a parallel set of string keys in `review.py`. |
| **7** — follow existing patterns | favours the enum | Mirrors `_APPROVE_OUTCOME_MESSAGES`, the same module's established idiom. |
| **5** — avoid overengineering | favours the enum | A second, duplicate vocabulary would be the overengineering. |
| **15** — small focused units | neutral | The helper keeps a single responsibility; only its **visibility** changed, because it now serves two modules and a cross-module symbol must be public. |

`19-G4`'s "no new `StrEnum`" was a **`B-1`** gate with a narrower intent: do **not** add an enum for
the *result* type, because the `NamedTuple` already satisfies rule 10. `BanResult` remains untouched
and that gate is **not** reopened. The new enum carries a **different concept** — the refusal
*reason*, which `B-2` genuinely introduced — and substitutes for nothing.

**Net:** the requirement is unaffected, the actor/target split is unaffected, and the tripwires are
unaffected. The deviation makes the code *more* consistent with the module it lives in. The
`B-2` Validator is asked to confirm no collateral damage — in particular that `ban_user_for_ad`'s
four refusal literals were left semantically unchanged, that the enum is a genuine fixed-value
vocabulary rather than a speculative abstraction, and that no test or tripwire was edited to absorb
the rename.

### 17.1 `B-2` gate result — **REJECT** (`8d0486f`), 14/15 gates pass

Passing: `19-D9` structural tripwire (both source tokens intact, `test_moderation_views.py`
byte-unchanged), the false-log fix, refusal visibility, `19-D6` levels (4/4), `19-D7` (redundant
round-trip gone, `BanResult` untouched, the no-lock guard green **unedited**), `19-D10` **upheld**,
`19-D5` i18n, `19-R7` actor gate, read-only files, scope, requirement integrity, architectural fit,
quality gates, and regressions — `.\Makefile.ps1 test`: **2832 passed, 0 failed**.

**`19-D10` is upheld**, with the correction that §17's rationale *overstated* what the enum replaced:
before `B-2` there was no string key set anywhere — `review.py` had no ban messages at all. The
enum's real justification is narrower and still sufficient: its values are the key type of a public
mapping, so rule 10 applies to them.

#### `R1` — BLOCKING. The two-sided tier truth is undelivered.

§3's `B-2` requirement 3 says *"login and publishing are refused; the current web session keeps
working until it expires. **State that, do not simplify it.**"* `B-1`'s `19-D1` deferred it here
explicitly. **The coordinator's `B-2` brief specified only the negative half** — "must NOT claim a
total lockout" — so the Implementor complied and the positive half was never requested. That is a
brief defect, not an Implementor defect: the brief under-specified a requirement the plan states in
full.

All four refusal sentences and the admin toast describe a **non-event**; none states what a ban
actually does. `19-R8` (`"banned" alone is ambiguous about the surviving session`) is therefore
still open. The precedent is `UserAdmin._deactivation_message`'s `WEB_ONLY_ENFORCEMENT` constant.

#### `R2` — BLOCKING. The `NOT_IN_TARGET_SET` totality invariant is **false as written**, and yields a false reason to the operator.

`19-D8` and both docstrings argue unreachability from *"every refusal path maps onto a counted
category"*. That reasoning covers only the **resolver** path. `ban_user_for_ad`'s
`User.DoesNotExist` early return yields `BanResult(changed=0, skipped_self=0, skipped_privileged=0,
already_in_state=0)` — **all four counts zero**, and the new view feeds exactly that shape to
`ban_refusal_reason`, producing *"the ad's owner is outside the set of accounts you may ban."* The
truth in that case is *"the owner account no longer exists."* Practically unreachable today
(`Ad.user` is a non-nullable `CASCADE` FK, and `ban_user` locks the ad row before the user is
re-read), but the written invariant is wrong and the one falsifying path hands the operator a false
cause.

#### `W2` — a gap in `B-3`'s specification, recorded now

`B-3`'s test #10 `test_operator_message_does_not_claim_total_lockout` asserts only the **absence** of
a lockout claim, so the current text passes it **vacuously**. `B-3`'s inventory must gain a
**positive** assertion that the tier truth is present, or the `R1` gap survives `B-3` and reaches
`B-4`, which would then document shipped behaviour that omits it.

#### Non-blocking, recorded not actioned

Advisory A — `BanRefusalReason` (typed) now coexists in one module with the untyped scope markers
`"unrestricted"` / `"non_privileged_only"` in `admin_actions`. `19-D7` forbids fixing half the
cross-module duplication and that was followed; the within-module asymmetry is recorded for the next
maintainer. Advisory B — `fully_refused` can evaluate to an `int`; behaviourally correct, `bool(...)`
is cleaner; folded into the fix. W4 — the working tree is dirty outside `src/`; no gate is affected
because the review diffs the commit range.

### 17.2 `B-2` re-validation — **ACCEPT** (`39bf74f`), 14/14

`R1` and `R2` both genuinely resolved. `.\Makefile.ps1 test`: **2832 passed, 0 failed.** ruff clean,
basedpyright 0/0/0, no new suppression. Exactly three files, no test touched, no doc touched, every
read-only file byte-unchanged. **`19-D5`, `19-D6`, `19-D7`, `19-D9`, `19-D10`, `19-R7`, `19-G4` all
still hold.** The fix commit changed **zero executable lines** in `admin_actions.py` (AST-identical
to `8d0486f` after stripping docstrings).

`R1` verified against code, not accepted on assertion: the bot half is right because
`AccountStateMiddleware` denies **every** bot interaction (and ad creation is bot-only — there is no
web ad-create route); the login half is right because `can_login` gates on `is_banned`; and the
session half is right — and materially *different* from `is_active` — because `MIDDLEWARE` has no
account-state gate and `ModelBackend` checks `is_active` only. The two levers have **opposite** tier
profiles and the copy reflects that.

`R2` verified by tracing every routing path into `ban_refusal_reason`: exactly **one** shape reaches
`NOT_IN_TARGET_SET` today (the deleted-owner early return), and the new cause-neutral sentence is true
for it and for the hypothetical future shape. No reachable shape renders a false cause.

**Requirement integrity — final read.** It holds end to end on **both** levers, at two independent
layers: `deactivation._resolve_targets` for `is_active`, `admin_actions._resolve_ban_targets` for
`is_banned` (the single home, called by **both** production writers). A **peer moderator is
`is_staff=True`**, so "other moderators" is covered by the same exclusion as staff and superusers.
There is **no third write path**: `UserAdmin` lists `is_banned` in `fieldsets`, but
`get_readonly_fields()` returns the full `readonly_fields` list whenever `obj` is set and
`add_fieldsets` omits it, so the admin change form cannot write the flag. The only carve-out is by
design and documented — a **superuser** is unrestricted, minus their own row.

### 17.3 `B-3` spec corrections — MANDATORY, from the `B-2` Validator

**`W2` is wider than recorded.** §3's `B-3` test #10
(`test_operator_message_does_not_claim_total_lockout`) asserts **absence only**, so it passes even if
every tier clause is deleted. Worse: **no test anywhere in the repo asserts any of the new operator
copy** — `test_admin_actions.py` and `test_moderation_views.py` contain no reference to `Skipped:`,
`Banned … user`, `_ban_message`, or `not applied`. All of `8d0486f`'s messaging is unpinned, not just
the tier truth, and the `ads/admin.py` comment *"a local literal is what lets a test pin the stable
substring"* describes an intent that was never fulfilled.

**`B-3`'s inventory therefore gains four tests, and its existing #10 is superseded.** The
**literal-guard discipline is load-bearing here**: every invariant substring must be **hard-coded**,
never `BAN_TIER_ENFORCEMENT in text` while importing the constant — otherwise the test stays green if
the constant is reworded. This is the tautology hazard
`test_admin_deactivate_user.py::test_operator_message_names_the_bot_tier_limit` exists to document.

| Replaces | Test | Asserts |
|---|---|---|
| **#10** | `test_ban_operator_message_states_the_two_sided_tier_truth` | `AdAdmin` toast carries the positive tier truth: `"refuses login and publishing"`, `"is enforced in the Telegram bot"`, `"does not revoke an existing web session"`; **and** the anti-over-claim half `"locked out everywhere" not in text` / `"cannot get back in" not in text`; **and** the clause appears exactly **once** (not boilerplate). |
| — (new) | `test_ban_view_refusal_states_the_two_sided_tier_truth` | The **`moderation:ban` view** surface — the surface `R1` was really about, and which today has **no** test. A peer `is_staff` moderator owns the ad → `PRIVILEGED` refusal; asserts the refusal sentence plus all three tier substrings, once. |
| — (new) | `test_ban_tier_wording_is_identical_on_both_surfaces` | Cross-surface drift pin. **Importing the constants here is correct** — the assertion is about *equality*, not content: `ads_admin.BAN_TIER_ENFORCEMENT == review.BAN_TIER_ENFORCEMENT`. Also asserts `len(_BAN_REFUSAL_MESSAGES) == 4` and that the tier text is **not** a fifth member nor repeated inside the four values — the only thing currently pinning the "not boilerplate" requirement. |
| — (new) | `test_not_in_target_set_refusal_copy_asserts_no_cause` | Pins `R2`: the cause-neutral sentence is present and the **retired** false-cause wording (`"outside the set of accounts you may ban"`) is absent. |

Plus §15.1 **finding 3**, already assigned to `B-3`: add to `test_moderator_cannot_ban_themselves` a
line asserting `skipped_privileged == 0` for a row that is **both** self **and** privileged — today
both `skipped_privileged == 0` assertions are superuser-actor cases, so dropping
`.exclude(pk=moderator_id)` from the privileged **count** would not go red. A reporting-accuracy
hole, not a security hole.

### 17.4 `B-4` advisories — from the `B-2` Validator

1. **`can_publish_ad()` has no production call site** (tests only). "A ban refuses publishing" is
   nonetheless **true** — publishing is refused because `AccountStateMiddleware` denies *all* bot
   interactions and ad creation is bot-only. **`B-4` must not describe the ban as a `can_publish_ad`
   gate**; that predicate is currently dead in production.
2. **A new deferred finding:** `can_publish_ad()` is dead code carrying a security-relevant promise —
   it looks like the enforcement point for "a ban stops publishing" and is not called anywhere in
   production. Out of scope here, recorded in §7 so the next plan does not rediscover it.
3. **Minor, recorded not actioned:** on the `moderation:ban` view the tier clause appears only on the
   **refusal** path — a successful `ban_user` posts no message, so the moderator gets no tier
   statement there. Pre-existing from `8d0486f`; adding a success-path operator message is a new
   decision, not part of this plan.

---

## 18. Final validation — **ACCEPT** (`1257603..8592c34`)

The requirement holds end to end. `\.\Makefile.ps1 test` **2849 passed, 0 failed**; ruff clean;
basedpyright clean; **no migration**; no `.po`/template change; every tripwire and read-only module
byte-unchanged; `MIDDLEWARE` still 15 entries; no out-of-scope item leaked in. Test growth across the
chain is monotonic — 9 → 17 → 22 → 26 tests, 44 → 103 assertions — and **no test was weakened,
deleted, or skipped**; every `-` line in the chain's `src/` diff is docstring prose, a comment, a
variable rename, or a redundant re-import.

**Requirement integrity.** The only two production writers of `User.is_banned=True` are in
`admin_actions.py`, and both route through `_resolve_ban_targets`. `UserAdmin` cannot write the flag
(read-only on change, absent from `add_fieldsets`). No management command, form, `bulk_update`,
`save()` override, raw SQL, or bot writer exists. A peer moderator is `is_staff=True` and is excluded
by the same clause. `is_active` is unchanged from plan 18. **Both levers closed.**

**Paths still open — all on a different flag class, none a target-scope gap:**
ad-level approve/reject/soft-delete carry no target scope (§2.3, documented in all four docs);
`AdminSite.has_permission` (`15-AUTHZ-003`); the dead `<id>/password/` route (`D-19-5`);
`is_deleted`/`is_declined` are unguarded **by absence** — no operator writer exists;
`D-19-4`'s audit asymmetry.

### 18.1 Required bookkeeping — disposition

| # | Finding | Disposition |
|---|---|---|
| **F1** | `docs/99-agent/architecture.md` crossed the maintenance rules' **hard 1000-line split threshold** in `8592c34` (975 → 1017 lines, `+42`), unrecorded. `8592c34` created the repo's only *new* breach, in a file B-4 was told to edit. | **Deferred, owner assigned — see `D-19-10`.** The rules' alternative to splitting is a recorded deferral with an owner, and §3 `B-4` explicitly forbade restructuring a document. Splitting a 1017-line agent-facing doc is a separate work item, not a by-product of a privilege fix. **Must be booked before plan 19 closes.** |
| **F2** | The Doc-specialist's threshold flag named `docs/ops/docker-deployment.md` at "~1137" lines. It is **1446** — and **1438 before this change**, i.e. a **pre-existing** breach, correctly adjudicated as *not* a plan-19 violation but **missed the one this change actually caused** (F1). Separately, `8592c34`'s commit body is **2 lines** (subject only) against 54–107 for every other block, so §6.3's `B-4` gate is satisfied only by the review, not by the record §3's preamble requires. | **Corrected here — this section is the record.** History is not rewritten: amending `8592c34` would violate the no-history-rewrite rule, so the gate closure is recorded in the plan instead. The line-count error is corrected: **1446**, pre-existing, owner `D-19-11`. |

### 18.2 Advisories — disposition

| # | Finding | Disposition |
|---|---|---|
| **A2** | **The resolver's fail-closed default on an unknown `moderator_id` is unpinned** — the most material residual gap. Both scope-marker tests use real rows, so inverting the default (unknown ⇒ superuser ⇒ unrestricted) leaves the whole suite green. It is a **recorded security decision** (§14 `resolved_by_this_task`), documented in three places, with executable protection zero. | **CLOSED** — see `19-D11` below. |
| **A1** | `target_scope` returns bare `str` literals while the same module gained `BanRefusalReason(StrEnum)`. **§17.1's stated justification is inaccurate**: it claimed a shared enum "cannot be introduced without editing a read-only file". A `BanTargetScope(StrEnum)` could live in `admin_actions.py` untouched by `deactivation.py`; only making `deactivation.py` *use* it needs that file. | **Recorded as `D-19-12`, not actioned.** Both consumers are module-private, so this is internal consistency rather than a broken contract, and changing a return type after every block has been validated and documented is poor value. The correction to §17.1's reasoning is recorded here so the next editor does not inherit the false claim. |
| **A3** | The view's `messages.warning` level on refusal is unpinned — a silent downgrade to `info` is green. | **Recorded, not actioned.** Low-medium; `19-D6` recorded the level for the **admin toast** (pinned by `test_fully_refused_ban_toast_is_reported_at_error_level`), and the view has exactly one message call site. |
| **A4** | `ban_user_for_ad`'s `User.DoesNotExist` early return is unpinned — and it is the reachable producer of the all-zero shape `R2`'s cause-neutral copy exists for. Practically unreachable (non-nullable `CASCADE` FK; ad row locked first). | **Recorded, not actioned.** Exercising it needs raw SQL with deferred constraints; the copy it produces **is** pinned by `test_not_in_target_set_refusal_copy_asserts_no_cause`. |
| **A5** | The tier clause is absent on the view's success path. | **Advise against pinning.** A success-path message is a plausible future improvement; pinning "no message" would freeze a gap. Correct as documentation. |
| **M1** | Two source-shape tests in the new module duplicate `test_admin_actions.py`'s canonical tripwires byte-for-byte. Per §3 test #12, so not a defect. | **Recorded, not actioned.** Dropping the copies and cross-referencing the canonical class would leave the resolver's own guard as the only new structural test. Accepted cost of a third edit site. |
| **A6** | §14 cites `src/backend/apps/core/tests/test_i18n_completeness.py`; the file is at `src/backend/apps/ads/tests/`. | Correction only; the full gate ran regardless. |
| **A7** | Plan 19's execution plan and code-context file are **untracked**, while plan 18's is tracked. | Bookkeeping for whoever commits the `.ai` artefacts. |
| **A8** | One new `# type: ignore[arg-type]`, in a test helper, copied verbatim from the reference §14 mandated. | **Not a deviation.** Production code adds zero suppressions; this is §14 item 7's explicit instruction. |

---

## 19. `A2` closed — `c569b52`, and plan 19 sign-off

`test_resolve_ban_targets_fails_closed_for_an_unknown_actor` pins the resolver's fail-closed default
for a `moderator_id` that names no row: the returned scope marker is the hard-coded restricted
literal, an ordinary seller is writable while a peer `is_staff` row and a superuser row are not
(asserted as observable `is_banned` state after the write), and `skipped_privileged == 2`. The actor
id used is far above every id the suite creates, so it cannot name a real row; the `None` case is
correctly **not** covered because the parameter is typed `int` and `basedpyright` would reject it.

**Non-vacuity was proven empirically, not asserted.** The Implementor temporarily inverted the default
in production to fail open, confirmed the new test goes red at the first assertion while all 26
existing tests stay green, then restored `admin_actions.py` byte-for-byte
(`git diff 8592c34 -- src/backend/apps/moderation/admin_actions.py` empty). That is the strongest
available evidence, and it is exactly the mutation §18.2 flagged as uncovered.

### 19.1 Final state

| | |
|---|---|
| **Chain** | `1257603` → `a1f8229` → `8d0486f` → `39bf74f` → `60be413` → `a2004bb` → `2cfa072` → `8592c34` → `c569b52` |
| **Requirement** | *"moderators may deactivate ordinary sellers, but must not be able to deactivate staff/superusers/other moderators."* — **holds end to end on both levers**, at two independent layers, with no third write path. |
| **Authoritative gate** | `\.\Makefile.ps1 test` → **2850 passed, 0 failed** (3 pre-existing naive-datetime warnings in `test_seed.py`). |
| **Quality gates** | `ruff check` clean; `basedpyright` 0 errors / 0 warnings / 0 notes; **no migration**; no `.po` or template change; production adds **zero** suppressions. |
| **Blast radius** | 4 production files touched (`admin_actions.py`, `ads/admin.py`, `views/review.py`) + 1 test module + 5 docs. **No schema change, no new enforcement point, no new role, no new app-to-app import edge.** |
| **Test surface** | 9 → 17 → 22 → 26 → **27** tests; 44 → **~110** assertions. Monotonic growth; no test weakened, deleted, or skipped anywhere in the chain. |
| **Read-only / tripwire files** | `deactivation.py`, `users/admin.py`, `test_admin_deactivate_user.py`, `test_admin_actions.py`, `test_moderation_views.py`, `test_decorators.py`, `moderation_log.py`, `views/decorators.py`, `conftest.py`, `config/`, `locale/`, `templates/`, `telegram_bot/`, `apps/seed/`, `docs/02-database/db-enums.md`, `docs/02-database/db-retention.md`, `.ai/audit/**`, plan 18 — **all byte-unchanged**. |

### 19.2 What plan 19 is, and is not

It closes the **one** escalation the literal requirement names, on the **one** lever where it was
still open. It adds **no** permission predicate, **no** role, **no** migration, and **no** new
enforcement point — a target scope in the service layer and a refusal report on two operator
surfaces, mirroring what plan 18 shipped for `is_active`.

**Its landing must not be read as the moderator contract closing.** Deferred register §7 carries
**twelve** items, the load-bearing ones being: `D-19-1` (the moderator contract — `UserRole.MODERATOR`,
`media_gate`, `AdminSite.has_permission`, the ModelAdmin permission overrides), `D-19-2` (**no
un-ban path exists anywhere in production code** — this plan made the ban *safer to apply*, not
*reversible*), `D-19-3` (bot-tier `is_active` revocation, the `django_session` janitor, the missing
per-request web gate — a banned seller keeps a session and can re-list), `D-19-9`
(`can_publish_ad()` is dead code carrying a security-relevant promise), and `D-19-10`/`D-19-11` (two
docs over the 1000-line split threshold, one of them newly caused by this plan).

A moderator can still **approve, reject, or soft-delete an ad** owned by a superuser or a peer
moderator: ad-level actions carry no target scope. That is a different defect class and a different
plan, and all four documents now say so.
