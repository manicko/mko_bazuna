# Plan 18 — Operator-Facing Account Deactivation (Execution Plan)

**Status:** ready to execute · **Numbering:** 18 (17 is phase 05's) · **Created:** 2026-10-02
**Origin:** emergent gap from phase 04 `B-01` + `B-05`, routed by the coordinator 2026-10-02.
**Decision owner:** coordinator. Option A (superuser-only admin action) chosen; option C (writable `is_active`) **prohibited**.

---

## 0. Provenance and drift control

Every citation below was re-derived against the working tree at commit `86d2f0c` on 2026-10-02.
This repo has a documented history of stale citations (phase 04's validator found a refuted
invariant at nine sites; phase 15's validator found a refuted sub-claim). **A future editor must
re-verify before implementing** and record the commit they verified against.

**Sources**

| Source | Role |
|---|---|
| `docs/99-agent/architecture.md:611-661` | The gap record this plan closes |
| `docs/ops/docker-deployment.md:1174-1183` | The operator inventory this plan fills |
| `.ai/plans/15-authorization-remediation.md` | `GATE Q1` (BLOCK 6), `15-AUTHZ-003` (BLOCK 9) |
| `.ai/plans/16-auth-login-remediation-execution.md` | Gates `G-A`, `G-B`, `G-D`; phase 04's known-gap discipline |
| Runtime probe, 2026-10-02 | The decisive fact in §1 — see below |

---

## 1. The decisive fact, and a correction to two documents

**A documented claim is false, and it changes the plan's value.**

`docs/99-agent/architecture.md:645-646` asserts:

> *"A `django_session` row is never invalidated on an account-state change, so `is_active` was
> never a revocation tool — it only blocks future issuance."*

That is **false for the web tier.** `is_active=False` revokes an already-authenticated session on
the **next request**, because `AuthenticationMiddleware` resolves the user per request:

```
AuthenticationMiddleware.request.user
  -> django.contrib.auth.get_user(request)
     -> load_backend(...).get_user(user_id)
        -> ModelBackend.get_user()  ->  user_can_authenticate(user)  ->  user.is_active
     -> None becomes AnonymousUser()
```

**Runtime evidence** (throwaway probe, deleted after the run; `django_db`, real
`SessionMiddleware`, real `ModelBackend`, `force_login` to establish the session *first*):

```
  client.force_login(seller)
  GET /dashboard/                        -> 200          (baseline, session live)
  seller.is_active = False; save()
  GET /dashboard/                        -> 302          (existing session killed)
  force_login(seller) ; GET /dashboard/  -> 302          (new issuance refused)
```

The existing session and a fresh attempt are indistinguishable. This is also independently
consistent with phase 15's validator, which recorded the same `302` for `is_active=False` at
`.ai/audit/99-validation/15-authorization-validated-findings.md:126-132`.

**Consequences for this plan**

1. The disable half and the **web** revocation half are **one operation**. The coordinator's
   original framing — "solves the disable gap *and* the session half of `04-AUT-002`" — **holds**.
2. **Two documents must be corrected** as part of this work (see `B-4`):
   - `docs/99-agent/architecture.md:643-649` — the claim above.
   - `docs/ops/docker-deployment.md:1185-1189` — *"it does **not** invalidate an already-issued
     session cookie"*. Literally true of the cookie (the row survives until expiry), but
     operationally misleading: the identity becomes anonymous immediately. Rewrite to state both.
3. **`04-AUT-002` stays NOT closed.** Narrowing the claim is not closing the finding. What
   remains open is in §E.

### Scope boundary — what `is_active = False` does and does not do

| Tier | Effect of `is_active = False` | Verified |
|---|---|---|
| Web, existing session | **Killed on next request** (anonymous) | probe, above |
| Web, new issuance | Refused (`login_status` → `410`, `B-05`) | `B-05` |
| Web, `django_session` row | **Survives** until `expire_date` — inert but retained | by construction |
| **Bot (Telegram)** | **Now enforced — plan 21 (2026-10-03, renumbered from 19).** `B-3` probed and found the bot did **not** block a deactivated user. Plan 19 added `is_active` to the shared predicate and an `is_active` branch to `AccountStateMiddleware`, with a support carve-out (no-arg `/start`, `SUPPORT_START`, support-intake free text). `D-2` is **closed**; the three other flags remain unenforced. | `B-3` probe (plan 18); plan 19 `B-1`/`B-2` |
| `is_banned` / `is_deleted` / `is_declined` | **Unaffected** — no per-request check exists for any of them | `04-AUT-002` |

The guarantee is also **backend-dependent**: it holds because `ModelBackend.user_can_authenticate()`
is consulted per request. Adding a second auth backend without that check weakens it. Record this
as a known condition in the docstrings, not as an assumption.

---

## 2. The gap being closed

```
B-01  UserAdmin change form: is_active read-only   ──┐
                                                      ├─►  no operator path to is_active = False
B-05  login_status refuses is_active = False (410)  ──┘
```

- `UserAdmin.readonly_fields` (`src/backend/apps/users/admin.py:126-145`) contains `"is_active"`
  at line **140**, and `get_readonly_fields()` (`:163-177`) returns that set whenever `obj` is set.
- `UserAdmin.has_change_permission` (`:196-197`) returns `request.user.is_staff` and **ignores
  `obj`** — so a writable `is_active` let any moderator disable arbitrary users, including
  superusers. `B-01` was correct to close it.
- The only writer of `is_active = False` anywhere in the repo would be `manage.py shell`
  (`docs/ops/docker-deployment.md:1178`).

**Consequence:** an operator responding to abuse has no supported lever. The only enforcement of
the disabled state is unreachable.

---

## 3. Execution blocks

Strictly serial: `B-1 → B-2 → B-3 → B-4 → B-5`. Each block's commit body carries its own gate
closure. No block may start before the previous is committed and green.

### B-1 — The service module

**New file** `src/backend/apps/users/services/deactivation.py`

```python
def deactivate_users(queryset: QuerySet[User], actor: User) -> DeactivationResult
def reactivate_users(queryset: QuerySet[User], actor: User) -> DeactivationResult
```

`DeactivationResult` is a `NamedTuple` (project rule 10 — a fixed value must be a type, not a
dict): `changed: int`, `skipped_self: int`, `skipped_privileged: int`. The two skip counts exist
**because `18-D1` makes them reachable** — the operator must be able to see that a selection was
partly refused, or a silently-short count reads as success.

| Constraint | Value | Why |
|---|---|---|
| **Target scope** | **In the service, not the view.** `if not actor.is_superuser: queryset = queryset.exclude(is_staff=True).exclude(is_superuser=True)` | `18-D1` + `18-Q7`. The `18-D1` answer is *superusers and moderators*, which must **not** become a blanket `is_staff` gate — that is the `B-01` escalation (`has_change_permission` ignores `obj`). Enforcing it in the service means a view cannot bypass it. |
| Self-exclusion | `queryset.exclude(pk=actor.pk)` | **Mandatory.** The operator is in the queryset. |
| Transaction | `with transaction.atomic():` + one bulk `QuerySet.update()` | `moderation/admin_actions.py:291-301` |
| Pyright | `# pyright: ignore[reportGeneralTypeIssues] - Django: django-stubs not installed; Atomic.__enter__/__exit__ untyped` | verbatim from `admin_actions.py:291` |
| Row lock | **none** | `bulk_ban_users` (`:276-302`) has none. `ban_user_for_ad` (`:111-113`) *does* `select_for_update()` the `User` — but that one reads-then-writes; a bulk `UPDATE` does not. **Record the choice in the docstring so the next editor does not "fix" it.** |
| Audit | `logger.info(...)` naming skipped counts | `.ai/plans/16-...:3839` rejected a bare reason-code enum: *"no consumer, no column, no reader"* |
| Schema | **no migration** | nothing persisted is added |
| Enum | **none** | the return type is a `NamedTuple`, not a persisted fixed value |

**Do not** add the writer to `account_state.py`. It is a **read-only predicate module** and its own
docstring warns of an import-cycle hazard via `users/services/__init__.py`; adding a writer and
re-exporting it widens that closure. **Do not** add it to `deletion.py` — that is the terminal
consent-erasure module and `is_active = False` is reversible and retains PII.

**Gate `18-G1`:** no `select_for_update` in the new module; no import from `account_state.py` or
`deletion.py`; no `StrEnum`; no migration.

### B-2 — The admin surface

**File** `src/backend/apps/users/admin.py`

```python
actions = ["deactivate_user", "reactivate_user"]   # strings, per AdAdmin.actions (ads/admin.py:243-248)

def has_deactivate_permission(self, request) -> bool:
    return request.user.is_staff or request.user.is_superuser   # 18-D1

@admin.action(description="Deactivate selected users", permissions=["deactivate"])
def deactivate_user(self, request, queryset) -> None: ...

@admin.action(description="Reactivate selected users", permissions=["deactivate"])
def reactivate_user(self, request, queryset) -> None: ...
```

| Decision | Choice | Justification |
|---|---|---|
| Predicate | **new named `has_deactivate_permission`**, `is_staff or is_superuser` | Matches `User.role == ADMIN` (`is_staff or is_superuser`, `apps/core/enums.py`), i.e. the existing `staff_required` answer — **not** a new fifth divergence. **Do not reuse `has_delete_permission`** (`:199-200`): disabling is not deleting, and `docker-deployment.md:1179` distinguishes them in prose. A named predicate is discoverable by phase 15's registry contract test (`15-authorization-remediation.md:2232`); a piggyback on `delete` is not. |
| Gate mechanism | `permissions=["deactivate"]` | Django 5.2 dispatches to `has_deactivate_permission` |
| **Target scope** | **Not in the view — in the service (`B-1`).** | The predicate answers *"may this actor run the action"*, not *"may this actor act on this row"*. Django's `permissions=` cannot express the second. A moderator running the action over a selection containing a superuser must have that row silently removed — and the count of removals must be **reported**, not swallowed. |
| Pyright on the predicate | **none** | the `has_*_permission` methods at `:193-203` carry none; only the three untyped Django hooks (`:163`, `:179`, `:185`) do |
| Signature | `def deactivate_user(self, request, queryset)` | matches `AdAdmin.action_reject` (`ads/admin.py:410-416`) |
| `withdraw_consent_action` | **leave dead** | `:205-215` is `@admin.action`-decorated but never registered. `G-B` deliberately did not register it (irreversible PII erasure). **Adding an `actions = [...]` list creates exactly the code shape that could tempt a future editor to register it — leave a comment saying so.** |

**Operator messaging must state the limit, and must report skips.** Per `18-D2` the promise is
*"this person cannot get back in"* — **not** *"locked out everywhere"*. `message_user` must
therefore state that the change is **immediate on the web tier and not enforced in the Telegram
bot**, and per `18-D1` it must **report how many selected rows were skipped** as self or
privileged. A "Deactivated N users" toast that hides a skip reads as success on a partial
operation. This is `18-D2` and it is **not optional**.

> **Amendment (plan 21, 2026-10-03; renumbered from 19).** The bot-tier half of that wording is no longer true: plan
> 19 enforces `is_active` in the bot with a Support restoration carve-out. `DEACTIVATION_ENFORCEMENT_NOTE`
> (renamed from `WEB_ONLY_ENFORCEMENT`) now states enforcement on **both** tiers plus the carve-out.
> The original requirement is preserved here as the plan-18 record; the current requirement is the
> amended one.

**Gate `18-G2`:** `has_deactivate_permission` and `has_delete_permission` are distinct methods;
the action is gated by its own permission, not by `change`; `withdraw_consent_action` is still
unregistered; the docstring names the bot-tier limit.

### B-3 — The bot-tier probe (a gate, not a code change)

**A probe test, kept as a permanent test, that asserts the current behaviour.**

The web tier is proven by §1. The bot tier is **not**. Write a test that drives a deactivated
user through a bot handler and record the actual outcome — the hypothesis is that **nothing
blocks them**, because the bot resolves identity per message and `B-05` only guarded the web
issuance point.

- If the bot is **not** blocked, the test asserts the residual with an owner-naming docstring
  (`15-AUTHZ-001`), per the known-gap-test discipline at `.ai/plans/16-...:6723-6731`.
- If the bot **is** blocked, the test is a positive assertion and `B-2`'s operator messaging must
  be narrowed accordingly.

**Do not write bot-revocation code in this plan.** It belongs to `15-AUTHZ-001`.

**Gate `18-G3`:** the probe exists, its outcome is recorded in the commit body, and `B-2`'s
messaging matches the probe's result. **If `B-3` lands after `B-2` and contradicts it, fix
`B-2` — do not leave the messaging aspirational.**

### B-4 — Documentation corrections and parity

| File | Change |
|---|---|
| `docs/99-agent/architecture.md:611-661` | Update the kill-switch record: the disable path now exists; `is_active=False` **does** revoke the web session (cite the probe); the bot tier is not revoked; `04-AUT-002` remains **NOT closed**. |
| `docs/99-agent/architecture.md:643-649` | **Correct the false claim** (§1). |
| `docs/ops/docker-deployment.md:1174-1183` | Operator inventory: replace the *"nowhere in the admin"* row for disable with the real path; add one row for re-enable. |
| `docs/ops/docker-deployment.md:1185-1189` | Rewrite: the cookie survives but the identity is anonymous from the next request. |
| `docs/01-spec/technical-specification.md` §H | Record the operator-facing contract if §H states account-state semantics. |

Keep the table's shape: one row per **operator need**, so disable and re-enable become two rows.

**Gate `18-G4`:** no stale claim of "nowhere in the admin" survives for disable or re-enable;
`04-AUT-002` is still recorded as NOT closed.

### B-5 — Phase 15 amendments (do not edit phase 15's plan in this block)

Record the required amendments in the commit body of `B-5` for a later editor:

| Target | Current | Required |
|---|---|---|
| `15-authorization-remediation.md` `GATE Q1` | *"neither plan has landed"* | False. Phase 04 landed; `B-01` and `B-05` are in. The question is no longer hypothetical. |
| `15-authorization-remediation.md` BLOCK 6 | DENY set excludes `is_active`, *"subject to GATE Q1"* | `is_active` is **already** enforced per-request by `ModelBackend` (proven). The exclusion is correct, but the reason is different from the one recorded — the gate is `ModelBackend`, not nothing. |
| `15-authorization-remediation.md` BLOCK 9 | `15-AUTHZ-003` registry contract test | Must discover and reconcile the new `has_deactivate_permission` predicate. |
| `15-authorization-remediation.md` §5 `U1` | *"the status for an existing session is not statically derivable"* | **Now derived and measured** (§1). Cite the probe. |

---

## 4. Product decisions required

Each is answerable in one or two sentences. **Do not resolve these silently in code.**

**All six answered by the product owner on 2026-10-02.** The answers and the one safety
constraint the coordinator added on top of `18-D1` are recorded below. **`18-D1` changes a
design constraint** — see §3 `B-2` and `R-4`.

| # | Question | **Decision (2026-10-02)** | Consequence recorded |
|---|---|---|---|
| **18-D1** | Who may deactivate? | **Superusers AND moderators.** | **NOT a blanket `is_staff` gate.** A moderator reaching *every* row is the escalation `B-01` closed (`has_change_permission` ignores `obj`). Decided as **actor-scope + target-scope**: the action is available to any ADMIN, but **a non-superuser actor may not target a staff or superuser row**, and `reactivate_user` is under the same restriction — otherwise a moderator could undo a superuser's disable. Implemented in the **service**, not the view, so it cannot be bypassed. See `B-1`, `B-2`, `R-4`. |
| **18-D2** | What does "deactivate" promise? | **The recommended option** — *"this person cannot get back in"*, stated plainly. | The operator message **must** name the bot-tier limit (`B-2`) and must not imply total lockout. The web tier is immediate (`B-5` in §1's table / test 5); the bot tier is bounded by `B-3`'s probe. **Superseded 2026-10-03:** plan 19 enforced `is_active` in the bot (with a support carve-out), so the bot-tier limit no longer exists; `WEB_ONLY_ENFORCEMENT` was renamed to `DEACTIVATION_ENFORCEMENT_NOTE` and reworded to both-tier enforcement + Support carve-out, and its pinning test renamed (see `18-Q5`). |
| **18-D3** | Ship reactivation in the same change? | **Yes.** | `deactivate_users` / `reactivate_users` ship together in `B-1`, and both actions in `B-2`. Both carry the `18-D1` target restriction. |
| **18-D4** | Three overlapping account-state flags? | Recorded; **not decided here.** | Deferred to `D-4` / phase 15 BLOCK 9. `B-4` must not present the three flags as a settled taxonomy. |
| **18-D5** | Ads on deactivation? | Unchanged. | `B-4` records the current behaviour; no scope expansion. |
| **18-D6** | 14-day session lifetime? | Cross-reference only. | `B-10`'s gap stays open (`D-10`). Do not re-decide the value. |
| **18-D4** | Are `is_active`, `is_banned`, `is_deleted` three concepts product actually wants? | Three overlapping "cannot use this account" flags with **different** levers and **different** enforcement points. `is_banned` has **no un-ban path at all**. The operator inventory will grow a row per flag. | **Confirm or merge them.** Not this plan's to decide; it must not be left implicit while the table grows. | `B-4` table | product |
| **18-D5** | What happens to a deactivated account's ads? | Deactivation stops login. It does **not** unpublish ads, and a live bot session can still act. The related accepted residual is at `architecture.md:526-539` (a banned seller keeps a session **and can relist**). | Record as-is in `B-4`; do not expand scope. | non-blocking | product |
| **18-D6** | Is a 14-day session lifetime acceptable for this control? | `SESSION_COOKIE_AGE = 60*60*24*14` (`config/settings/base.py:207`), set literally by phase 04 `B-10`. `architecture.md:606-620` records *"No product decision has been taken on the value."* For deactivation the operator-relevant number is **"a live session outlives the deactivation by up to 14 days on the bot tier"** — on the web tier §1 makes it immediate. | Accept for the web tier; the bot-tier number is the real exposure. **Cross-reference `B-10`'s still-open gap — do not re-decide the value here.** | non-blocking | product |

---

## 5. Deferred work register

Real, needed, **not owned by this plan**. Each has an existing owner; this is a consolidation
index, not new invention. Verify each attribution before relying on it.

| # | Work | Owner | Named at |
|---|---|---|---|
| D-1 | **Session revocation for `is_banned` / `is_deleted` / `is_declined`.** `is_active` is the only flag with a per-request gate, and only because `ModelBackend` supplies it. The other three still leave a live session. `04-AUT-002`, HIGH, **NOT closed**. | `15-AUTHZ-001` (phase 15 BLOCK 6) | `architecture.md:526-539` |
| D-2 | **Bot-tier account-state enforcement.** **CLOSED by plan 21 (2026-10-03, renumbered from 19).** `B-3` probed (2026-10-02) that the bot did **not** block a deactivated user — `AccountStateMiddleware` read `is_banned` / `is_deleted` / `is_declined` / `consent_revoked`, never `is_active`. Plan 19 added `is_active` to the shared `get_account_state` predicate and an `is_active` branch (with a support carve-out for the restoration channel) to the middleware. `test_account_state_deactivation_probe.py` was inverted rather than deleted; the matrix is pinned by `test_bot_deactivation_matrix.py`. The probe's residual is no longer asserted because it no longer exists. | `15-AUTHZ-001` — **closed** | this plan, `B-3`; closed by plan 19 |
| D-3 | **`django_session` rows are never deleted** on any account-state change. Inert, but retained. `django_session.session_data` is zlib+HMAC-signed with **no user column**, so a `LIKE` scan is **impossible, not slow**. Gate `G-A` is CLOSED and rules the decode scan and the per-request gate out of non-phase-15 hands; `User.session_epoch` was explicitly rejected as phase 15's. | `15-AUTHZ-001` | `.ai/plans/16-...:3656-3668`, `:3840` |
| D-4 | **Full moderator contract** — including whether `has_deactivate_permission` is the right gate. | `15-AUTHZ-003` (BLOCK 9) | `15-authorization-remediation.md:2232` |
| D-5 | **`is_banned` has no un-ban path** anywhere in the repo. | product + phase 15 | `docker-deployment.md:1177` |
| D-6 | **No `clearsessions` janitor** anywhere in the repo; `docs/02-database/db-retention.md` has **no `django_session` row** and **must not be edited** (phase-04 exit condition). | phase 12 | `docker-deployment.md`, `architecture.md` |
| D-7 | **Anonymous `django_session` growth** — up to 43,200 rows/IP/day. | phase 12 | `architecture.md` § `04-AUT-006` |
| D-8 | **`withdraw_consent_action` is dead code** — decorated, never registered. **Deliberate** (`G-B`). `B-2` creates a new `actions = [...]` list, which is the shape that could tempt a future editor to register it. Leave a comment. | phase 15 BLOCK 9 | `users/admin.py:205-215` |
| D-9 | **`create_admin_user` password-policy msgid untranslated.** | `.po` maintainer | `architecture.md` § `04-AUT-005` |
| D-10 | **`B-10`'s session-lifetime product decision** still untaken. | product | `architecture.md:606-620` |

---

## 6. Test ownership

**New module** `src/backend/apps/users/tests/test_admin_deactivate_user.py`, with
`pytestmark = [pytest.mark.django_db, pytest.mark.integration]`.

Not `test_admin_pii_containment.py` (PII masking plus a second concern; `pytest.mark.unit`) and
not `test_admin_change_form.py` (owns the *form* contract). An action is neither.

**No superuser/admin fixture exists in `src/backend/conftest.py`** — it has `seller`, `user`,
`buyer`, `category`, `city`, `make_user`. Copy the module-local pattern from
`test_admin_change_form.py:32-52` (`staff_user` at `telegram_id=930000101`, `superuser` at
`930000102`). Its docstring records that `conftest.py` is contended territory.

**Action-vs-form-field is orthogonal, so these must stay green untouched:**
`test_admin_pii_containment.py::test_change_form_has_no_writable_account_state_field`,
`::test_change_form_keeps_preferred_city_writable`,
`::test_change_form_fieldset_never_exposes_an_uneditable_field`, and
`test_admin_change_form.py::test_non_superuser_moderator_cannot_flip_account_state`.

| # | Test | Asserts |
|---|---|---|
| 1 | `test_non_admin_cannot_reach_the_deactivate_action` | A plain **non-staff** seller: the action is absent from `get_actions(request)` and a POST leaves `is_active` `True`. |
| 2 | `test_moderator_and_superuser_can_reach_the_deactivate_action` | Positive control for **both** actor classes (`18-D1`). **Anti-vacuity** — without it, test 1 passes if the action is simply broken. |
| 3 | `test_deactivate_user_sets_is_active_false_and_flips_no_other_flag` | Real changelist POST; `is_active is False` and `is_banned` / `is_deleted` / `is_declined` / `ads_auto_publish` untouched. The action must not become a back door into the flags `B-01` retired. |
| 4 | `test_deactivate_user_excludes_the_acting_user` | Operator selects their own row; `is_active` unchanged, `skipped_self == 1`. Self-lockout guard. |
| 5 | **`test_moderator_cannot_target_a_superuser_or_staff_row`** | Moderator selects {ordinary seller, moderator, superuser}; only the seller changes; `skipped_privileged == 2`. **This is the `18-Q7` guard — the single most important test in the plan.** |
| 6 | **`test_superuser_can_target_a_staff_row`** | The positive half of `18-Q7`: a superuser's selection is not restricted. Prevents the guard from being over-applied. |
| 7 | **`test_moderator_cannot_reactivate_a_superuser`** | The `reactivate_user` half of the same guard. A moderator must not be able to undo a superuser's disable. |
| 8 | `test_deactivate_user_revokes_an_existing_web_session` | `force_login`, `GET /dashboard/` → 200, deactivate, `GET /dashboard/` → 302. **This is the §1 probe promoted to a permanent assertion.** |
| 9 | `test_deactivate_user_leaves_the_django_session_row_in_place` | The row **survives**. Assert the residual with an owner-naming docstring (`15-AUTHZ-001`, gate `G-A`), per `.ai/plans/16-...:6723-6731`. |
| 10 | `test_deactivate_users_service_is_idempotent` | Second call returns `changed == 0`; no extra write. |
| 11 | `test_reactivate_user_restores_an_enabled_account` | The inverse. |
| 12 | **`test_operator_message_states_the_bot_tier_and_the_support_carve_out`** | `18-D2` as amended by plan 21: the `message_user` text states enforcement on **both** tiers plus the Support carve-out. Renamed from `test_operator_message_names_the_bot_tier_limit` when the old web-only claim became false. |
| 13 | **`test_operator_message_reports_skipped_rows`** | `18-D1`: a partial selection reports its skips. |
| 14 | `test_bot_tier_account_state_after_deactivation` | The `B-3` probe, kept permanent. Owner-naming docstring if it asserts a residual. |

**Retired:** the old test 1 (`test_moderator_cannot_reach_the_deactivate_action`) and test 9
(`test_permission_predicates_are_distinct_methods`) are **replaced**, not extended. The
predicate-identity idea survives as a one-line assertion inside test 2 — with `18-D1` the
predicate is no longer superuser-only, so "distinct from `has_delete_permission`" now matters for
a different reason: widening `delete` must not widen `deactivate`, and vice versa.

Add a service-shape test by source inspection, mirroring the `test_bulk_ban_users_not_locked`
precedent in `apps/moderation/tests/test_admin_actions.py`: `"transaction.atomic" in src`,
`"select_for_update" not in src`.

**Do not touch** `bulk_ban_users`, `AdAdmin`, or `apps/moderation/tests/test_admin_actions.py`.

---

## 7. Risks

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| R-1 | The new `actions` list tempts a future editor to register `withdraw_consent_action`, reopening irreversible PII erasure from an admin surface. | **High** | Comment at `users/admin.py:205-215` naming `G-B`. `D-8`. |
| R-2 | An operator reads "Deactivated" as "locked out everywhere" and the bot still serves the user. | **High** | `B-2` operator messaging names the limit; `B-3` measures it; `18-D2` decides the promise. |
| R-3 | Self-lockout: a superuser bulk-selects their own row. | Medium | `queryset.exclude(pk=actor_id)` in the service, **plus** test 4. Not fully mitigable for a fat-fingered selection — the paired reactivation is the real mitigation (`18-D3`). |
| R-4 | **The action becomes a moderator-escalation vector.** `18-D1` puts moderators in the actor seat, and `has_change_permission` ignores `obj` — so without the target scope a moderator reaches every row, including superusers. `reactivate_user` is the sharper edge: a moderator could undo a superuser's disable. | **High** | Target scope **in the service**, not the view (`B-1`); tests 5, 6 and 7; `18-Q7` must be answered before `B-2` ships; BLOCK 9's registry contract test inherits it. |
| R-5 | A silently-skipped privileged row makes a partial selection read as success. | Medium | `DeactivationResult` carries `skipped_self` / `skipped_privileged`; `message_user` reports them (`B-2`); tests 5 and 13. |
| R-5 | Shipping a *corrected* claim (`is_active` revokes web sessions) makes readers generalise it to all flags. | Medium | State the `ModelBackend` dependency in every docstring and in `B-4`. `D-1` keeps the other flags open. |
| R-6 | The `ModelBackend` guarantee silently weakens if a second auth backend is added. | Low | Record as a known condition in `B-1`'s and `B-2`'s docstrings, not as an assumption. |
| R-7 | A plan citation is stale by the time this is implemented. | Medium | Re-verify against a named commit before `B-1`; record it in the `B-1` commit body. |

---

## 8. Definition of done

**Per block** — its own gate closure in its commit body:

- `B-1` — new module; `18-G1` satisfied; no migration; no new `StrEnum`.
- `B-2` — actions registered; `18-G2` satisfied; `withdraw_consent_action` still unregistered; operator messaging names the bot-tier limit.
- `B-3` — probe exists, is permanent, and its result is recorded.
- `B-4` — no stale "nowhere in the admin" survives; the `architecture.md:643-649` false claim is corrected; `04-AUT-002` still reads NOT closed.
- `B-5` — the four phase-15 amendments recorded for a later editor.

**Phase-level**

1. The §6 test table (fourteen tests, #1–#14) exists and passes, plus the
   service-shape inspection tests §6 requires. **As delivered:** thirteen of the
   fourteen live in `src/backend/apps/users/tests/test_admin_deactivate_user.py`
   (#1–#13), the `B-3` probe (#14) lives in
   `src/telegram_bot/tests/test_account_state_deactivation_probe.py` (the bot
   suite is async and its conftest redefines the DB fixtures), and three
   structural source-inspection tests cover `deactivate_users`,
   `reactivate_users` and `_resolve_targets`. Total: **17 tests** — 16 in the
   users module, 1 in the bot tree.
2. `uv run ruff check src/backend/apps/users/` — clean.
3. `uv run basedpyright src/backend/apps/users/` — clean, no new suppression.
4. `uv run djlint src/backend/templates/` — no template change, so trivially clean.
5. **No `.po` edit.** `test_no_hardcoded_visible_text` scans **templates only**;
   `users/admin.py:61-70` documents admin headings as deliberately English-only literals on a
   staff-only surface. Confirm the new `description=` strings follow that, and that the i18n
   completeness gate still passes.
6. **Fast gate green:** `.\Makefile.ps1 test`.
7. `docs/02-database/db-retention.md` **byte-unchanged** — phase-04 exit condition.
8. `.ai/audit/**` untouched.

**Blast radius — verified 2026-10-02:** there is **no** exact-count test for admin actions,
`readonly_fields`, or `MIDDLEWARE` length. `get_actions(` and `.actions` appear **nowhere** in
the test suite. `apps/core/tests/test_observability.py` asserts `MIDDLEWARE` first and last only.
(`HOURLY_COMMANDS`/`DAILY_COMMANDS` *do* have exact-`==` tests in
`apps/core/tests/test_scheduler.py`, but that class of pinned-count test does not exist for admin
and this plan must not introduce one.)

---

## 9. Open questions carried by this plan

| ID | Question | Owner | Status |
|---|---|---|---|
| `18-Q1` | Superusers only, or moderator-capable? (`18-D1`) | product | **ANSWERED 2026-10-02** — both, with a target restriction (see §4). Superseded by `18-Q7`. |
| `18-Q2` | What does "deactivate" promise? (`18-D2`) | product | **ANSWERED 2026-10-02** — *"cannot get back in"*, stated plainly; **amended 2026-10-03 by plan 19**: the promise now holds on both tiers (enforcement + Support carve-out), so the operator message states both-tier enforcement rather than a bot-tier limit. |
| `18-Q3` | Pair shipped or alone? (`18-D3`) | product | **ANSWERED 2026-10-02** — pair, both under the `18-D1` restriction. |
| `18-Q4` | Three overlapping account-state flags? (`18-D4`) | product | Open — deferred to `D-4` / phase 15 BLOCK 9. Non-blocking. |
| `18-Q5` | Bot-tier behaviour after deactivation? | `B-3` probe, then `15-AUTHZ-001` | **ANSWERED 2026-10-02 by the `B-3` probe; SUPERSEDED 2026-10-03 by plan 19.** The probe found the bot did **not** block a deactivated user, so `B-2`'s operator message correctly stated web-only enforcement *at the time*. Plan 19 then enforced `is_active` in the bot with a support carve-out and closed `D-2`. The old `WEB_ONLY_ENFORCEMENT` constant was **renamed and reworded** to `DEACTIVATION_ENFORCEMENT_NOTE` (both-tier enforcement + Support carve-out), and its pinning test renamed to `test_operator_message_states_the_bot_tier_and_the_support_carve_out`. The earlier "reword deferred" note is **resolved**. |
| `18-Q6` | 14-day session lifetime acceptable? (`18-D6`) | product | Cross-reference only; `D-10` stays open. Non-blocking. |
| `18-Q7` | **Is the target restriction correct?** A moderator may deactivate/reactivate **non-staff** rows only; a superuser may act on anyone. | **ANSWERED 2026-10-02 by the product owner** — *"moderators may deactivate ordinary sellers, but must not be able to deactivate staff/superusers/other moderators."* This is now a decision, not a coordinator safety constraint. `B-1`'s target scope and tests 5, 6 and 7 implement it verbatim. |

**A note on ownership, as the coordinator required.** This plan is **pre-work for phase 15
BLOCK 9**, not a substitute for it. It adds one named permission predicate that BLOCK 9's registry
contract test must discover and reconcile, and it does not resolve the moderator contract. If
BLOCK 9 lands first, `18-D1` and `18-Q6` are answered there and this plan collapses to `B-1`
through `B-4`. **Do not let this plan's landing be read as `15-AUTHZ-003` closing.**

---

## 10. Rejected alternatives

| Option | Verdict | Why |
|---|---|---|
| C — make `is_active` writable on the change form | **Prohibited** | `has_change_permission` returns `is_staff` and ignores `obj` (`users/admin.py:196-197`); a writable `is_active` let any moderator disable arbitrary users including superusers. `B-01` closed this correctly. |
| B — leave it as `manage.py shell` | Rejected | An incident-response lever should not be a shell command. The coordinator's call. |
| Reuse `has_delete_permission` as the gate | Rejected | Semantically false — disabling is not deleting; `docker-deployment.md:1179` distinguishes them in prose. Also invisible to BLOCK 9's registry test. |
| `request.session.flush()` in the action | **Forbidden** | The `ban_user` wrong-target trap, gate `G-D`: it flushes the **operator's** session and leaves the target live. Strictly worse than doing nothing. |
| A `django_session` decode scan | **Forbidden here** | `session_data` is zlib-compressed + HMAC-signed with no user column; a `LIKE` scan matches **zero rows, always** — impossible, not slow. Gate `G-A` is CLOSED and assigns both mechanisms to `15-AUTHZ-001`. |
| A `User.session_epoch` column | **Forbidden here** | `.ai/plans/16-...:3840`: *"REJECTED — forbidden here. Correct, and it is phase 15's."* |
| Register `withdraw_consent_action` while adding `actions` | **Forbidden** | `G-B`. Irreversible PII erasure from an admin surface. |