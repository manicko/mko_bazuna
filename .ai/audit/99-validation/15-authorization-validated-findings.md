---
phase: "15"
phase_name: "Authorization & Access Control"
source: ".ai/audit/15-authorization/findings.md"
validated: "2026-09-28"
validator: "Reviewer (subagent)"
id_prefix: "AUTHZ"
severity_taxonomy: ".kilo/commands/audit/phases/15-audit-authorization.md#severity-taxonomy"
mode: "problems-only"
---

# Validated Findings — Phase 15: Authorization & Access Control

Self-contained. Every claim below was re-derived from the working tree at the
recorded commit; no statement requires reading the auditor's report or any
source file to act on.

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 3 | AUTHZ-004, AUTHZ-006, AUTHZ-007 |
| Validated with content correction (severity held) | 3 | AUTHZ-001, AUTHZ-002, AUTHZ-009 |
| Reclassified (type changed, severity held) | 1 | AUTHZ-005 → SPEC-DEVIATION |
| Adjusted (content materially corrected) | 2 | AUTHZ-003 (HIGH held), AUTHZ-008 (LOW held) |
| Merged | 0 | AUTHZ-001 is *coupled* to 04-AUT-002, not merged — see Cross-Phase Reconciliation §1 |
| Rejected | 0 | No finding was rejected whole. Six **sub-claims** were rejected — see Rejected Sub-Claims. |
| VAL- (audit-input / rollout) | 5 | VAL-001 … VAL-005 |

**Headline.** The three HIGH findings are all real and all survive independent
reproduction. Two of them are mis-scaled in ways that matter to a remediation
tracker, and one of them (`AUTHZ-003`) carries a recommendation that would
*expand* moderator privilege if implemented as written. The most valuable output
of this validation is therefore not a verdict but three corrections: the
`submit_ad` guard as specified is a tautology for its own web caller; the
moderator role **is** self-provisionable through the admin, so "not deployable"
is false; and the CSRF taxonomy entry needs a ruling before AUTHZ-004 can be
banded consistently with the other phases.

### Decision table

| ID | Title | Auditor severity | Verdict | Final severity | One-line justification |
|----|-------|------------------|---------|----------------|------------------------|
| AUTHZ-001 | No per-request account-state gate | HIGH | **CONFIRMED** (2 corrections) | HIGH | Reproduced end-to-end through the real `ban_user_for_ad` path: `is_banned=True`, session key unchanged, `dashboard=200`, `save-search=200`; no gate exists in `MIDDLEWARE`. |
| AUTHZ-002 | `submit_ad()` ignores `user_id` | HIGH | **CONFIRMED** (2 required amendments) | HIGH *(taxonomy-mandated; currently unreachable)* | Foreign `ad_id` row was mutated across tenants with the wrong actor id; but the reported `-> True / published` is content-dependent (I got `False / on_moderation_failed`) and the recommended guard is a **tautology** for the web caller. |
| AUTHZ-003 | `ADMIN` has three implementations | HIGH | **ADJUSTED** | HIGH *(band held; impact substantially reduced; recommendation REJECTED)* | 17 registered admins and 12/17 changelist denials confirmed; but "no provisioning mechanism anywhere" is **refuted** by a live self-grant, and the proposed 17-class mixin would grant write access to 9 deliberately read-only models. |
| AUTHZ-004 | `GET /login/issue/` writes without CSRF | MEDIUM | **CONFIRMED** | MEDIUM | Reproduced with `enforce_csrf_checks=True`: two anonymous `GET`s, `LoginToken` 0→1→2. MEDIUM held; the handbook's CRITICAL entry is ambiguous for state-changing `GET` (VAL-001). |
| AUTHZ-005 | `can_publish_ad()` dead + wrong flag set | MEDIUM | **RECLASSIFIED** | MEDIUM | Dead-code label rejected by the mandatory spec cross-reference — `technical-specification.md:101` specifies the behaviour, so this is a **missing integration (SPEC-DEVIATION)**; `can_publish_ad(declined)=True` reproduced. |
| AUTHZ-006 | `DailyAdMetricsAdmin.has_delete_permission` | MEDIUM | **CONFIRMED** | MEDIUM | Reproduced: `True` for `AnonymousUser` and for a seller; blocked only by `AdminSite.has_permission`, and `AnalyticsEventAdmin` shows the correct pattern. |
| AUTHZ-007 | `ad_edit` authorizes on an unlocked read | MEDIUM | **CONFIRMED** | MEDIUM | Structure reproduced verbatim; **distinct root cause from AUTHZ-002** (caller scope vs service scope) and `ad_archive`/`ad_reactivate` already implement the fix in the same file. |
| AUTHZ-008 | `staff_required_api` ordering + bogus `Bearer` | LOW | **ADJUSTED** | LOW | The `Bearer` challenge is real and unimplemented; the claimed `422`-instead-of-`405` consequence is **refuted** — the decorator returns `405` before the view runs. |
| AUTHZ-009 | No logging/metrics on denials | LOW | **CONFIRMED** | LOW | `decorators.py` defines `logger` and calls it **zero** times; `delete.py`/`edit.py` do log, so the inconsistency is real. |

---

## Methodology

**What I re-derived independently.** Nothing in the auditor's evidence blocks
was accepted on trust. Specifically, and as the phase-15 brief requires, the
`ModelAdmin` surface was enumerated by **introspecting the registered admin
objects**, not by reading `admin.py`:

```text
[type(m.__name__) and getattr(type(ma), p) is not getattr(admin.ModelAdmin, p)
 for (m, ma) in admin.site._registry.items() for p in
 ("has_view_permission","has_change_permission","has_add_permission","has_delete_permission")]
```

Reading `admin.py` alone is what produced phase 07's false `MEDIA-005` and
phase 10's stale root cause; it is not a sufficient instrument here, because
`has_view_or_change_permission` (the predicate the changelist actually calls)
is a disjunction that source reading invites you to get wrong.

**Environment.** All runtime evidence was produced against a **private**
`postgres:18-alpine` instance on a scratch database created by
`connection.creation.create_test_db()`. The shared
`mko-bazuna-test-db-*` container was never connected to; the phantom
`mko_bazuna` database named by `config.settings.test` was never written. The
scratch container and the `.ai/tmp/` probe scripts were deleted afterwards; the
working tree contains no source modifications.

**Five probes, all read-only against production code:**

| # | Instrument | What it produced |
|---|-----------|-----------------|
| 1 | `admin.site._registry` introspection + per-`ModelAdmin` permission calls | 17-class census, override census, `has_delete_permission` reachability |
| 2 | Django test client (real middleware stack, real templates) | 17 changelist URLs × 5 identities, `/admin/` index, session-revocation matrix, `submit_ad` repro, `login_issue` CSRF, predicate matrix, IDOR matrix, `staff_required_api` |
| 3 | Admin action functions + HTTP | dead-approval attribution, ban-path session evidence, `media_gate` source, logging census, `UserAdmin`/`AdAdmin` form field contracts |
| 4 | Admin change-form POST as a plain moderator | moderator self-provisioning, plaintext password write |
| 5 | `AdAdmin.get_form` | `AD-001` field-contract cross-check |
| R | `ruff check` + `basedpyright` over the authorization surface | reproduced the auditor's R-08 exactly |

**Confirmed methodology claims.** R-08 reproduced verbatim: `ruff` → *All checks
passed!*; `basedpyright` → *0 errors, 0 warnings, 0 notes*. The webhook
N/A claim is correct: `telegram_bot/main.py` uses `dp.run_polling(bot)` and no
webhook endpoint exists. `SESSION_COOKIE_AGE` is indeed never overridden
(`1209600` s = 14.0 d, `SESSION_SAVE_EVERY_REQUEST=False`,
`SESSION_EXPIRE_AT_BROWSER_CLOSE=False`, db engine) — verified at runtime, not
inferred.

---

## Per-Finding Validation

### AUTHZ-001 — [HIGH] — No per-request account-state gate

**Verdict: CONFIRMED. Severity HIGH held.** Two corrections; one required
amendment to the recommendation.

**Independently reproduced, and more sharply than reported.** The auditor
flipped the flags directly. I drove the *real* moderator ban path
(`ban_user_for_ad`) against a live authenticated session:

```text
  victim dashboard=200  session_rows=3
  ban_user_for_ad  -> None
  is_banned=True   session_rows_after=3   same_session_key=True
  victim dashboard   AFTER ban -> 200
  victim save-search AFTER ban -> 200
  bulk_ban_users -> 1
```

Per-flag session matrix (fresh authenticated session per row):

```text
  baseline         dashboard=200  save-search=200
  is_banned        dashboard=200  save-search=200
  is_declined      dashboard=200  save-search=200
  is_deleted       dashboard=200  save-search=200
  consent_revoked  dashboard=200  save-search=200
  is_active=False  dashboard=302  save-search=302
```

`MIDDLEWARE` (`config/settings/base.py:196-211`) contains 14 entries and none is
an account-state gate; a substring search for an account/state middleware
returns `[]`. `can_login` has exactly **one** production call site
(`apps/users/views/consent.py:449`, inside `login_status`). `is_active=False`
is genuinely handled by `ModelBackend.get_user()` → `user_can_authenticate()`,
so the auditor's carve-out is right.

**Correction 1 — the revocation-path count is wrong, and understates the
problem.** The report says *"Three of the four revocation paths"*. The code has
**five** account-state-changing paths, of which **four** leave the live session
authorized:

| Path | Revokes? | Evidence |
|------|----------|----------|
| Self-service `POST /consent/withdraw/` | **Yes** | session key becomes `None`, row count drops, `dashboard` → 302 |
| Self-service `POST /consent/decline/` | No | `consent.py:208-209` calls `decline_consent(user)` then redirects to the dashboard |
| Admin `UserAdmin.withdraw_consent_action` | No | `users/admin.py:55-65` |
| Moderator `ban_user_for_ad` | No | `moderation/admin_actions.py:98-100` |
| Moderator `bulk_ban_users` | No | `moderation/admin_actions.py:255` |

(Note for the tracker: phase 04's own headline says "3 of 4" while its evidence
table lists five rows with one closed. The code is the tie-breaker: **4 of 5**.)

**Correction 2 — the finding adds design, but not a second defect.** See
Cross-Phase Reconciliation §1. AUTHZ-001 is the *remedy* AUT-002 was
actioned-against; it must not be counted as an independent item.

**Required amendment — the shared predicate must be a two-level contract, or
this fix perpetuates the bug it is meant to end.** The recommendation specifies
`account_state_verdict(user) -> AccountStateVerdict(allowed, reason)`, an
**instance-level** predicate. That is exactly the shape (`get_account_state()`
returns a `NamedTuple` over a `User` instance) that phase 08's validator
identified as the reason no queryset-level visibility predicate was ever
written. If AUTHZ-001 ships only the instance-level verdict, the
owner-blocked SRCH-004 / SRCH-008 / 06-VAL-003 items stay blocked for a fourth
phase. The predicate must therefore expose, from the same declaration:

1. the per-request verdict (this phase's gate), and
2. the **terms** — the named `User` flag expressions a queryset filter can be
   composed from — so that `06-VAL-003`'s audience predicate and `SRCH-004`'s
   ad predicate can be built on it.

The *semantics* of those terms stay owned by phases 06/08; AUTHZ-001 must only
make them expressible. See Cross-Phase Reconciliation §3.

**Recommendation accepted as written** on every other point: DENY set
`{is_banned, is_deleted, is_declined, consent_revoked}`; `is_active` explicitly
excluded; `logout(request)` on deny; placement immediately after
`AuthenticationMiddleware`; and — importantly — the explicit instruction *not*
to fold the ad-visibility predicate into the gate. That last point is correct
and is verified below.

### AUTHZ-002 — [HIGH] — `submit_ad()` ignores the `user_id` it is handed

**Verdict: CONFIRMED. Severity HIGH held** (see the band note below). Two
required amendments; one evidence correction that a future validator will hit.

**Reproduced, with a different result than reported.**

```text
  before = title='B draft'  status=draft  user_id=2  (B's ad)
  submit_ad(ad_id=B's draft, user_id=A) -> False ['Ad failed moderation checks']
  after  = title='A15 hijack'  status=on_moderation_failed  user_id=2  price=999.00
```

The **cross-tenant write is confirmed** — B's row was overwritten with A's
title, description, category, city and price, and its lifecycle status was
driven, with the actor id in the DTO never consulted. Source confirms the
mechanism: `SubmitAdInput.user_id: int | None` is declared at
`ads/services/submission.py:54` and the token `user_id` appears **nowhere** in
the `submit_ad` body; the row is loaded at line 171 by
`Ad.objects.select_for_update().get(id=input.ad_id)` with no owner filter.

**Evidence correction (important — do not use the reported return value as the
acceptance test).** The report's `-> True []` / `status=published` did **not**
reproduce. Whether the hijacked ad ends `published` or `on_moderation_failed`
depends entirely on whether the injected content passes auto-moderation. I
injected obviously-flaggable text and got `False`. A validator who reproduces
this and sees `False` must **not** conclude the finding is refuted — the row was
still mutated. The correct assertion is *"the row changed"*, not *"the call
returned `True`"*.

**Reachability — verified, and it is genuinely nil today.** All three call
sites: `ads/views/edit.py:160` and `:203` (both inside the ownership-checked
POST branch, `ad_id` from the URL kwarg) and
`telegram_bot/handlers/ad_create/submit.py:62` (`ad_id` and `user_id` both read
from the same per-chat FSM dict, and `entry.py:57` writes `ad_id` only inside
the `/post` flow that is itself `user_id`-gated). No management command, job or
API endpoint calls `submit_ad`. Confirmed by whole-repo search.

**Severity band — stated honestly.** The phase-15 taxonomy's HIGH entry is
*"No ownership check on one resource type (even if never exploited in
testing)"*, which describes this case almost verbatim, so HIGH is the
handbook-mandated band and I have not overridden it. But the taxonomy has no
category for "real defect, no reachable path", and the operational risk today
is **zero**: the defect is a latent one that becomes an exploit the first time
someone adds a fourth caller. The finding's own `Likelihood: MEDIUM` and its
reachability disclosure are the right framing. **Required Fixes ranks it third
by *sequence*, not by risk**, and flags the guard as defence-in-depth.

**Required amendment 1 (blocking) — the recommended guard is a tautology for
the web caller and would give false assurance.** Both `edit.py` call sites pass
the **ad's own** owner, not the actor:

```text
  edit.py:170   user_id=ad.user_id
  edit.py:213   user_id=ad.user_id
```

So `if ad.user_id != input.user_id: return False` is always `False` on the web
path. Implemented literally, the guard protects nothing while *looking* like it
protects the main write path. The fix is two halves and must land together:
`submit_ad` compares `ad.user_id` against `input.user_id`, **and** `edit.py:170`
and `:213` pass `request.user.id`. A regression test must assert both — a
mismatched `user_id` leaves the row byte-identical, *and* a POST by a
non-owner with a valid body is refused before `submit_ad` is reached.

**Required amendment 2 — the guard belongs after the lock, inside the existing
`transaction.atomic()`,** so the check and the mutation share a snapshot. That
is already what the recommendation says, and it is the same invariant
`AUTHZ-007` is about — but at a different scope (see §AUTHZ-007 below; the two
are **not** the same root cause and must not be merged).

**Refinement of the Impact claim (downward).** The report says "the next caller
… silently becomes a cross-tenant write". True, but the blast radius is
narrower than implied: the row is a `DRAFT` or `ARCHIVED` ad, and the write path
runs `auto_moderate` inside the same transaction, so a hijacked draft is
moderated, not silently published. The realistic outcomes are a *defaced* or
*failed* ad, and — worse for the platform — a seller whose draft is destroyed by
another seller. That is a denial-of-service against a specific object at least
as much as it is a data-integrity breach.

### AUTHZ-003 — [HIGH] — The `ADMIN` role has three divergent implementations

**Verdict: ADJUSTED. Severity HIGH held on taxonomy grounds; Impact materially
reduced; Recommendation REJECTED as written and replaced.** One sub-claim
refuted. This is the finding that needed the most correction.

**Confirmed by enumeration (independently, as required).**

```text
  total registered ModelAdmin classes : 17
    16 project admins (ads×2, analytics×2, categories, core×3, locations,
                        lookups×2, moderation×2, users×3)
     1 Django's own  auth.group (GroupAdmin, auto-registered by
       django.contrib.auth + admin autodiscovery; auth.user is NOT registered
       because AUTH_USER_MODEL is swapped)
  override has_view_permission        : 3  -> ads.ad, ads.adimage, users.user
  => rely on per-model perm for view  : 14
  override NOTHING at all             : 3  -> auth.group, core.supportcontact,
                                           lookups.lookupitem
```

**Confirmed: 17 changelists, 12 of them 403 for a plain `is_staff` moderator.**
Effective HTTP status, one real request per cell:

```text
  changelist                            ANON SELLER STAFF SUPER(no staff) SUPER+STAFF
  /admin/ads/ad/                         302   302   200      302             200
  /admin/ads/adimage/                    302   302   200      302             200
  /admin/analytics/analyticsevent/       302   302   403      302             200
  /admin/analytics/dailyadmetrics/       302   302   403      302             200
  /admin/auth/group/                     302   302   403      302             200
  /admin/categories/category/            302   302   200      302             200
  /admin/core/siteconfig/                302   302   403      302             200
  /admin/core/supportcontact/            302   302   403      302             200
  /admin/core/supportticket/             302   302   403      302             200
  /admin/locations/city/                 302   302   200      302             200
  /admin/lookups/lookupgroup/            302   302   403      302             200
  /admin/lookups/lookupitem/             302   302   403      302             200
  /admin/moderation/moderationcriterion/ 302   302   403      302             200
  /admin/moderation/moderatoractionlog/  302   302   403      302             200
  /admin/users/consentrecord/            302   302   403      302             200
  /admin/users/logintoken/               302   302   403      302             200
  /admin/users/user/                     302   302   200      302             200
  /admin/ (index)                        302   302   200      302             200
```

The auditor's headline count — *12 of 17* — is **correct**. Their prose list of
what a moderator *can* reach (`Ad`, `AdImage`, `Category`, `City`, `User`) is
also correct: `CategoryAdmin` and `CityAdmin` override `has_change_permission`
to `request.user.is_staff`, and the changelist gate is the **disjunction**
`has_view_or_change_permission`, so they are reachable despite having no
`has_view_permission` override. *(An earlier pass of this validation measured
`has_view_permission` in isolation and got 14/17; the disjunction is the correct
predicate and the auditor's number is the right one. Recorded so the next
validator does not repeat the error.)*

**Confirmed: the superuser-not-staff lockout and its inconsistency with
`staff_required`.**

```text
  SUPER(is_staff=False)  /admin/            -> 302   (redirect to admin login)
  SUPER(is_staff=False)  /admin/users/user/ -> 302
  SUPER(is_staff=False)  /moderation/queue/ -> 200   (staff_required: role==ADMIN)
  SUPER(is_staff=False)  /analytics/moderation/ -> 200
  admin_site.has_permission(SUPER no staff) = False
  User.role(SUPER no staff)                 = UserRole.ADMIN
```

`AdminSite.has_permission` is `is_active and is_staff`; `User.role` is
`is_staff or is_superuser`; `staff_required` uses `role`. Three answers, one
question. The fourth divergence — `media_gate` at `ads/views/listings.py:186`
gates on the raw `request.user.is_staff`, so the same superuser-not-staff is
denied media that `staff_required` grants them — is confirmed at source
(`:185-194` the staff branch, `:200-205` the `ad__user__is_declined=False`
branch).

**Confirmed: the inverted `UserAdmin` ladder.** `users/admin.py:43-53` — a
superuser-not-staff gets `add=True, delete=True` but `view=False, change=False`
on `users.User`; a plain moderator gets `view=True, change=True` but
`add=False, delete=False`.

**REJECTED SUB-CLAIM — "no seeding command, group, or fixture exists anywhere
in the repo to grant them" / "the moderator role is not deployable".** This is
false, and the false part is load-bearing for the Impact. `UserAdmin` declares
no `fields`/`fieldsets`/`form`, so Django auto-builds a `ModelForm` over every
editable model field; introspection of the registered admin object gives:

```text
  editable base fields (22): password, last_login, is_superuser, first_name,
    last_name, email, is_staff, is_active, date_joined, username, telegram_id,
    chat_id, is_banned, is_deleted, is_declined, ads_auto_publish,
    telegram_premium, preferred_city, telegram_language, source, groups,
    user_permissions
  password -> CharField / AdminTextInputWidget / required=True
  fieldsets=None  form=ModelForm  get_readonly_fields overridden=False
```

Combined with `has_change_permission = request.user.is_staff`, a plain moderator
can edit **their own** row. Proven, live, through the admin UI:

```text
  moderator is_staff=True is_superuser=False role=admin
  GET  /admin/users/user/<own id>/change/  -> 200
  GET  /admin/users/user/add/              -> 403          (has_add = is_superuser)
  GET  /admin/lookups/lookupitem/  BEFORE  -> 403
  POST /admin/users/user/<own id>/change/  (user_permissions=[lookups.view_lookupitem])
  moderator has view_lookupitem AFTER: True
```

So **a moderator is self-provisionable**, and the "403 on 12 of 17" describes
the out-of-the-box state rather than an undeployable role. This *reduces* the
finding's operational severity. It also **raises* a different one: the same
form lets that moderator set `is_superuser` on their own row, and I observed
`is_staff` silently cleared when a POST omitted the checkbox (un-checked
`BooleanField`s are submitted as absent, so the form's own save path
de-staffed the user mid-probe, after which their `role` became `seller`). That
escalation is **`04-AUT-005` / `04-VAL-004` / `PII-103`** and is *not* re-filed
here — but it means the aggregate blast radius of this pair is HIGH, and it must
not be dropped when AUTHZ-003 is re-banded.

**Correction to the census.** *"15 of 17 ModelAdmin classes declare no
permission override … the two that do override"* is not coherent and is not
what the registry says. Correct statement: **14 of 17** have no
`has_view_permission` override and therefore fall back to per-model
`auth.Permission` for the read gate; **3** declare no override at all; **3**
(Ad, AdImage, User) answer `view` on raw flags. The root cause — the enum was
never wired into the layers that decide — is unaffected.

**REJECTED RECOMMENDATION (a) — `AdminRolePermissionMixin` on all 17 classes
is disproportionate *and unsafe as written*.** A mixin that resolves `ADMIN` via
`UserRole.ADMIN` and gates `add`/`change`/`delete` would grant a plain moderator
**write** access to every model that does not re-declare an opt-out. Six of
those classes are read-only **by deliberate data-protection policy**, not by
oversight:

```text
  AnalyticsEventAdmin    add=False change=False delete=False  "Events are preserved for metrics"
  ModeratorActionLogAdmin add/change/delete = False            audit trail
  ConsentRecordAdmin     add=False                             GDPR Article 7(1) record
  LoginTokenAdmin        add=False change=False                credential material
  SupportTicketAdmin     add=False delete=False                audit trail
  SiteConfigAdmin        add=False delete=False                singleton
  AdImageAdmin           add=False change=False delete=False
```

Adding four uniform grants to those seven classes is a **privilege expansion**,
not a tightening — the opposite of a least-privilege fix. The proposal also
conflates two independent questions: *how the ADMIN role is resolved* (this
finding) and *which actions each model permits* (per-class least-privilege,
currently hand-rolled and mostly correct).

**Replacement recommendation (narrower, and safe).**

1. **Resolve the role once, in one place, and reuse it.** Add a
   `resolve_admin_role(user) -> UserRole` (or make `User.role` the single
   accessor) and have `media_gate` call `request.user.role == UserRole.ADMIN`
   instead of `request.user.is_staff`. This is a two-line change that removes
   one of the four answers and is safe.
2. **Reconcile `AdminSite.has_permission` with `User.role`, and pick one.**
   Either (i) override `AdminSite.has_permission` to
   `request.user.is_active and request.user.role == UserRole.ADMIN` — the
   superuser-not-staff lockout disappears and the system matches
   `staff_required`; or (ii) declare in writing that a superuser is *always*
   `is_staff=True` and enforce it at provisioning (`create_admin_user` already
   sets both; add a test that `is_superuser=True` implies `is_staff=True`).
   Option (i) is one method and matches the existing `staff_required` contract;
   recommend (i), and adopt (ii) as a test either way.
3. **Do *not* add a blanket mixin.** If a shared base is wanted later, it must
   resolve only the *role* and must default to **deny** for `add`/`change`/
   `delete`, with each class opting in explicitly — which is 17 × 3 explicit
   declarations and should be costed as such before anyone starts.
4. **Write the moderator contract down once** and assert it with a test that
   iterates `admin.site._registry` — which is precisely the instrument that
   produced this report's strongest evidence. The contract must state the
   answer to: *does a plain `is_staff` moderator get write access to the
   moderation criteria, the audit log, and the support desk?* Today the answer
   is "no, and there is no documented reason".
5. **Close the self-escalation here as a dependency, not as a fix.** The
   `UserAdmin` field contract is `04-AUT-005`'s. AUTHZ-003 should *cite* it as
   a hard prerequisite of the moderator contract, and the two should be tracked
   as one remediation.

**Severity note.** I am holding HIGH because the handbook's HIGH band names
exactly this ("Role confusion: a SELLER resolves to ADMIN (or vice versa)";
"Divergent authorization logic between web and bot processes"), not because the
"12 of 17" framing survives — it does not, in the form given. If the
orchestrator prefers to band on the *residual* (lockout + missing contract,
with escalation owned by `04-AUT-005`), the honest residual band is **MEDIUM**,
and the combined `AUTHZ-003 + 04-AUT-005` pair is HIGH. Record the choice
explicitly; do not let a re-band silently drop the escalation.

### AUTHZ-004 — [MEDIUM] — `GET /login/issue/` writes without CSRF

**Verdict: CONFIRMED. Severity MEDIUM held.**

```text
  Client(enforce_csrf_checks=True)
  LoginToken rows 0 -> 1  (GET /login/issue/  status=200)
              -> 2         (GET again        status=200)
  no CSRF token supplied; no hostile Referer needed
```

Source confirms the shape exactly: `apps/users/urls.py:20` registers the view on
a bare `path("login/issue/", login_issue, …)`; `consent.py:297` decorates it with
`@never_cache` only — no `@require_POST`, no `csrf_exempt` — and
`consent.py:326` performs `LoginToken.objects.create(...)` unconditionally after
two rate-limit checks. The report's file/line citations are exact.

The auditor's own severity caveat is the right call and I endorse it: a literal
reading of §8's CRITICAL entry ("State-changing web request accepted without a
valid CSRF token") would band this CRITICAL, but no identity, session or
protected resource is affected; the token is a bearer credential that must still
be claimed by a Telegram identity; it expires in 5 minutes; and both rate limits
hold. The ambiguity is escalated as **VAL-001** rather than decided silently,
which is the correct handling.

**Two additions the report does not carry, both material to rollout:**

- nginx fronts `location /login/` with `limit_req … burst=20 nodelay`
  (phase 04's validator confirmed the zone keys on `$binary_remote_addr`), so the
  amplification is bounded at the edge as well as in-app. That bound is the
  reason MEDIUM is right and it should be stated in the final report.
- `/login/issue/` is reached from the **Telegram deep-link landing page**, and
  `04-VAL-003` warns that any change to the login flow's *write* behaviour
  already breaks six green tests. The GET→POST change must therefore be checked
  against `apps/users/tests/test_login_issue_template.py` and
  `apps/core/tests/test_login_issue_template.py`, which the report's rollout row
  does not name.

### AUTHZ-005 — [MEDIUM] — `can_publish_ad()` is dead and omits `is_declined`

**Verdict: RECLASSIFIED → SPEC-DEVIATION. Severity MEDIUM held.** The
mandatory dead-code cross-reference (§5) rejects the report's framing.

**Step 1 — the "dead code" label does not survive the spec cross-reference.**

| Source | Result |
|--------|--------|
| Project spec | `docs/01-spec/technical-specification.md:101` — *"**DECLINE = browse-only:** blocks seller login/actions AND hides the user's PUBLISHED ads…"*; `:85` and `spec-index.md:74` carry the same decision. The **behaviour** is specified; `docs/01-spec/architecture-structure.md:42` even lists `account_state` as a service. |
| README | no additional reference |
| Pydantic models / `StrEnum` | `UserRole` (`apps/core/enums.py:288`) documents `ADMIN → is_staff or is_superuser`; no publish-gate enum exists. `AccountState` (`users/services/account_state.py:16-23`) is a `NamedTuple`, not a Pydantic model. |
| Config templates | none reference a publish gate |

Because the spec references the component, the finding is **not** "dead code" —
it is a **missing integration**: the specified predicate exists, is exported, is
unit-tested, and is wired into neither process. Reclassified accordingly.

**Step 2 — the substantive claims all reproduce.**

```text
  can_publish_ad non-test references: 3
    users/services/account_state.py:51        (definition)
    users/services/__init__.py:6             (import)
    users/services/__init__.py:20            (__all__)
  => zero production callers; zero bot callers; zero web callers

  normal                  can_login=True   can_publish_ad=True
  banned                  can_login=False  can_publish_ad=False
  deleted                 can_login=True   can_publish_ad=False
  declined                can_login=False  can_publish_ad=True    <-- wrong
  ads_auto_publish=False  can_login=True   can_publish_ad=False
  consent_revoked         can_login=True   can_publish_ad=True    <-- wrong
```

The live publish gate is `AccountStateMiddleware._check_publish_permission`
(`telegram_bot/middlewares/permissions.py:192-220`), which consults
`ads_auto_publish` alone and returns `(True, "")` for an unregistered identity
(line 208). A declined seller is blocked today only because
`_check_user_state` denies them first at line 176 — an unrelated earlier check
that happens to be stricter. The finding is right that the documented predicate
is the wrong one, and right that the test suite
(`users/tests/test_account_state.py:85-140`) pins the wrong flag set, so the
suite protects the wrong answer.

**Correction — one more wrong answer, in the same direction.** The report names
only `is_declined`. `consent_revoked` is also `True`: `can_publish_ad` tests
`is_banned`, `is_deleted` and `ads_auto_publish`, and `AccountState` carries
`consent_revoked` (line 23, derived at line 47). GDPR-withdrawn is a strictly
stronger state than soft-deleted, and the predicate denies the weaker one while
allowing the stronger. The DENY branch must be
`{is_banned, is_deleted, is_declined, consent_revoked}` — the same set
AUTHZ-001 uses, which is the argument for the single shared predicate.

**Dependency, not duplicate (point 6).** AUTHZ-005 does **not** overlap:

- **`AD-008` / `05-VAL-003`** (dead `ON_MODERATION` state, dead human-approval
  path) — different subsystem; a publish *gate* and a publish *state machine*
  are orthogonal. Reproduced the phase-05 path independently to be sure:
  `approve_ad(ON_MODERATION) -> False`, `approve_ad(ON_MODERATION_FAILED) ->
  False`, `bulk_approve(queryset of 2) -> 0`, `POST /moderation/approve/<id>/ ->
  404`, `POST /moderation/review/<id>/approve/ -> 404`, while
  `POST /moderation/reject/<id>/ -> 302` and `POST /moderation/ban/<id>/ -> 302`.
  Phase 05 owns it; AUTHZ-005 correctly does not touch it.
- **`PII-105`** (DECLINE is a one-way door) — **coupled, not duplicated.** PII-105
  option (a) would make a declined seller regain web login; if that option is
  taken, the publish gate becomes the *only* thing keeping a declined seller
  from posting, and AUTHZ-005's missing `is_declined` term becomes the whole
  control. AUTHZ-005 must be sequenced **after** the PII-105 owner decision, not
  in parallel with it.
- **`spec-index.md:74` vs `technical-specification.md:101`** — the two
  authoritative lines disagree ("DECLINE blocks seller **login only**" vs
  "blocks seller login/**actions**"). This is `04-VAL-005` / `PII-113`, already
  filed. AUTHZ-005's claim that "the documented semantic (browse-only) is the
  enforced one" rests on the contested line, so its *type* (spec deviation) is
  only well-founded once that conflict is resolved. Recorded, not re-litigated.

**Prior record cross-reference.** `docs/99-agent/test-audit-block-f-findings.md:193`
already lists *"No test for `can_publish_ad` when `is_declined=True`"* as a
**test-coverage gap**. That is a different artefact from this defect, and the
distinction matters: the prior record would be closed by *adding a test* that
locks in the current (wrong) answer, whereas AUTHZ-005 requires the predicate to
change first. Note this in the tracker or the two will race.

### AUTHZ-006 — [MEDIUM] — `DailyAdMetricsAdmin.has_delete_permission()` returns `True`

**Verdict: CONFIRMED. Severity MEDIUM held.**

```text
  has_delete_permission(AnonymousUser)   = True
  has_delete_permission(SELLER)          = True
  has_delete_permission(STAFF)           = True
  has_delete_permission(SUPER no staff)  = True
  admin_site.has_permission(anon/seller) = False   <-- the only thing that stops it
  HTTP POST delete as SELLER -> 302 (/admin/login/?next=…)
  HTTP POST delete as ANON   -> 302
```

Source: `apps/analytics/admin.py:99-101` returns a constant `True` and never
touches `request`; the sibling `AnalyticsEventAdmin` at `:47-49` returns `False`
for the same reason class, which is the in-repo precedent for the fix.

**Correction to the impact, downward.** The report's *"any relaxation of the
site-level gate … would grant anonymous deletion of analytics rows"* is right
about the coupling but the phrasing implies a near-term path. There is none:
`AdminSite.has_permission` is Django's, and nothing in the project overrides it.
The honest statement is that this is a **defence-in-depth defect with no
current exploit** — which is what MEDIUM means, and the report should say so
rather than implying a live anonymous-delete capability.

**Scope check on the recommendation's last sentence.** "Add the same
`request`-consulting assertion to the other `has_*_permission` overrides that
currently return constants" is correct as a *test* but must not become a
refactor. Of the constant-returning overrides, `False` is always safe;
`True` is the only dangerous direction, and this is the only one. A blanket
sweep would touch 17 classes for one defect. Keep it to this class plus a
regression test.

### AUTHZ-007 — [MEDIUM] — `ad_edit` authorizes on an unlocked read

**Verdict: CONFIRMED. Severity MEDIUM held. Root cause is distinct from
AUTHZ-002 — do not merge.**

**Structure reproduced verbatim** (`ads/views/edit.py`):

```text
   91  ad = get_object_or_404(Ad, id=ad_id)                     unlocked read
   94  if ad.user_id != request.user.id: ... return 403         the check
  116  with transaction.atomic():
  117  ad = get_object_or_404(Ad.objects.select_for_update(), id=ad_id)   re-read, NOT re-checked
  ...    every branch below mutates THIS instance and passes its ad_id to submit_ad
```

The transfer vector is real: `AdAdmin`'s auto-built form has **24** editable
fields and `user` is one of them (`readonly_fields` does not include it) — plus
`status`, `published_at`, `original_published_at`, `archived_at`, `deleted_at`.
So `04`/`05`'s AD-001 is the only writer that can move an ad between owners, and
the window between line 94 and line 117 is exactly the window in which it can
happen.

**Current behaviour is correct** — cross-seller attempts denied on every path:

```text
  SELLER_A GET   <B's PUBLISHED>/edit/       -> 403
  SELLER_A GET   <B's DRAFT>/edit/          -> 403
  SELLER_A GET   <B's ON_MODERATION>/edit/  -> 403
  SELLER_A POST  <B's ad>/archive/          -> 403
  SELLER_A POST  <B's ad>/delete/           -> 403
  SELLER_A POST  <B's ad>/reactivate/       -> 403
  SELLER_A GET   <own ad>/edit/             -> 200
```

**Why this is NOT the same root cause as AUTHZ-002** (explicitly requested):
AUTHZ-002 is a **service-scope** defect — the shared orchestrator has no
ownership predicate at all, and the fix belongs inside `submit_ad`. AUTHZ-007 is
a **caller-scope** defect — the predicate exists in the view but is evaluated
against a different snapshot than the mutation. Different layer, different
owner, different fix. They *compose* (AUTHZ-002's guard becomes defence-in-depth
once AUTHZ-007's atomic re-check lands) and they must be landed in that order,
but merging them would hide one behind the other's diff.

**Strengthening evidence the report does not have — the fix already exists
40 lines below in the same file.** `ad_archive` (`:283-296`) and `ad_reactivate`
(`:321-334`) both do `with transaction.atomic():` → `select_for_update()` →
**then** the ownership check on the locked instance. `ad_edit` is the lone
outlier. This converts AUTHZ-007 from a design question into a one-view
consistency fix with an in-repo precedent, and it is the cheapest structural
item in the phase. The report's "Root Cause" is also slightly off: the row lock
was not "introduced around the mutation without moving the authorization" —
the lock was added to `ad_edit` only (DB-003), and the two siblings were
written correctly.

### AUTHZ-008 — [LOW] — `staff_required_api` ordering and the `Bearer` challenge

**Verdict: ADJUSTED. Severity LOW held.** Claim 1 confirmed; **claim 2 refuted.**

**Confirmed — the challenge is factually wrong.** `Bearer` appears in exactly
three places in the repository: the decorator
(`moderation/views/decorators.py:51`) and two test files that assert it. There is
no DRF, no `authtoken`, no token middleware, no API-key setting. The only
credential on `/moderation/api/v1/bulk-action/` is the Django session cookie, so
the challenge sends an on-call engineer hunting for a bearer-token bug that does
not exist.

**REJECTED SUB-CLAIM — "an `ADMIN` sending a `GET` passes the role check, falls
through the method check, and reaches `bulk_moderation_action`, which then fails
on an empty body and returns `422`".** The decorator's third branch is a `return`,
not a fall-through, so the view body is never entered on a non-`POST` request:

```text
  AnonymousUser            -> 401  WWW-Authenticate=Bearer
  SELLER                   -> 403
  ADMIN      GET           -> 405          (not 422, and not "OK")
  SUPER-no-staff GET       -> 405
  SUPER-no-staff POST      -> 200
```

`bulk_moderation_action`'s `422` branch (`api_bulk.py:44-50`) is reachable only on
a `POST` with an unparseable body. The report's own live-probe line
(`staff_required_api(ADMIN, GET) -> OK  <-- falls through to the view`) is
therefore wrong, and the `422`-instead-of-`405` rollout risk in its safety table
does not exist.

**What survives, and it is smaller.** Reordering the method check first would
change only the *diagnostic* status for two cases that are already denied
correctly: anonymous `GET` 401→405 and seller `GET` 403→405. That is a
consistency improvement, not a defect. Keep the reordering; delete the 422
claim.

**New rollout-safety item the report misses.** Four assertions in two files pin
the bogus header and will fail the moment it is corrected or removed:

```text
  apps/moderation/tests/test_decorators.py:185, 198
  apps/moderation/tests/test_priority_service.py:489
    assert response.headers["WWW-Authenticate"] == "Bearer"
```

These are tests asserting a wrong contract. Per project rule 2 (production code
is king) the assertions change, not the code — but the change must be made in
the same commit, or the phase will look red.

### AUTHZ-009 — [LOW] — No logging or metrics on denied authorization decisions

**Verdict: CONFIRMED. Severity LOW held.** Matches the handbook's LOW band
verbatim ("Log verbosity includes role/identity on denied requests", "No
metrics on denied authorization attempts").

```text
  moderation/views/decorators.py : logger defined, logger.* calls = 0
  apps/ads/views/delete.py       : logger.* calls = 2
  apps/ads/views/favorite.py     : logger.* calls = 0
  apps/ads/views/edit.py         : logger.* calls = 3   (edit, archive, reactivate)
```

An unused module-level `logger` in `decorators.py:16` is the sharpest single
piece of evidence: the intent was there and was never wired. The report's
`toggle_favorite` claim is confirmed by the `favorite.py` count.

**One correction to the recommendation's placement.** The report proposes
instrumenting the shared decorators. That is right for the two admin gates, but
the *highest-value* denials are the per-object ones in the ad views, which
already log a human-readable message with no stable machine-readable code. The
useful change is a **stable reason code** (`authz.deny reason=not_owner
user=… path=… resource=ad:42`) emitted from a single helper that both the
decorators and the ad views call — otherwise the phase creates a third
denial-logging convention alongside the two that already exist. Pair it with
AUTHZ-001's new middleware so the new gate is instrumented on day one.

---

## Rejected Sub-Claims

Six claims inside validated findings are false as written. Clean them from the
report before the final consistency pass.

| # | Claim in | Verdict | Evidence |
|---|---------|---------|----------|
| 1 | AUTHZ-002: `submit_ad(...) -> True`, ad ends `published` | **Partly refuted** | Return value is content-dependent; my repro returned `False` / `on_moderation_failed` with the row still mutated. Assert on the row, not the return value. |
| 2 | AUTHZ-003: "no seeding command, group, or fixture exists anywhere … the moderator role is not deployable" | **Refuted** | A plain moderator reached their own `UserAdmin` change form (200) and self-granted `lookups.view_lookupitem`; `has_perm` went `False → True`. |
| 3 | AUTHZ-003: "15 of 17 declare no permission override … the two that do override" | **Refuted (arithmetic)** | 14 of 17 lack `has_view_permission`; 3 declare nothing at all; 3 override `view`. |
| 4 | AUTHZ-008: "an `ADMIN` sending a `GET` … reaches `bulk_moderation_action` … returns `422`" and the probe line `staff_required_api(ADMIN, GET) -> OK` | **Refuted** | The decorator returns `405` before the view body. |
| 5 | AUTHZ-003 / Cross-Finding: "`UserAdmin` … among 25 base fields"; "`AdAdmin` … among 29 base fields" | **Refuted (stale numbers)** | Introspection: `UserAdmin` 22 editable base fields; `AdAdmin` 24. (See VAL-003.) |
| 6 | AUTHZ-001: "Three of the four revocation paths … are open" | **Understated** | Five account-state-changing paths exist; four are open (self-service **decline** is a fifth the report omits). |

---

## Cross-Phase Reconciliation

### 1. How AUTHZ-001 and AUT-002 relate (point 2)

**They are one defect with one remedy. A tracker must not count them twice.**

Both records were validated HIGH by different validators against the same two
spec lines:

| | `04-AUT-002` (phase 04, validated) | `15-AUTHZ-001` (this phase) |
|---|---|---|
| Type after validation | SPEC-DEVIATION | Security / Broken Access Control |
| Defect | `ban_user_for_ad`, `bulk_ban_users`, `UserAdmin.withdraw_consent_action` never revoke the session; `can_login` is a one-shot gate | the web tier has no per-request gate at all |
| Root cause | *"the authorization decision point for account state exists in two divergent shapes"* | *verbatim the same sentence* |
| Remedy | "a shared web-side account-state gate (middleware or a `require_active_seller` decorator reusing `get_account_state()`)" | `AccountStateGateMiddleware` + `account_state_verdict()` + a stated DENY set + `logout()` on deny + the `is_active` carve-out + the explicit non-goal |

**Does AUTHZ-001 add design? Yes — materially, but not a second defect.** It
resolves the four things AUT-002's validated recommendation left open: the
mechanism (middleware vs decorator), the DENY set (which adds
`consent_revoked`, a flag `can_login` never tests), the `is_active` carve-out,
and the response shape. That is a real contribution and it is the reason this
phase's output is worth more than AUT-002's. It is **not** an independent
finding: the Impact, the exposure window and the root cause are the same.

**Why the split is nonetheless correct and must be preserved.** Phase 04's
`VAL-001` resolved the ownership question in advance and *dictated* this shape:

> Phase 04 retains AUT-002 for the session-layer consequences only — that
> `ban_user_for_ad`, `bulk_ban_users` and `UserAdmin.withdraw_consent_action`
> fail to invalidate the session they caused to exist, and that `can_login` is a
> one-shot gate. Phase 15 owns the per-request gate. **Both phases must not file
> the same middleware.**

AUTHZ-001 is on the right side of that line: it does not re-file the missing
`logout()` calls, and it does not implement them. **Required action for the
tracker:** key both records to one remediation item, keep both IDs, and let
`04-VAL-001`'s "both phases must not file the same middleware" constraint govern
who writes the code. If AUT-002 is actioned first, its per-path `logout()` calls
become defence-in-depth under AUTHZ-001's gate; if AUTHZ-001 lands first, AUT-002
reduces to "and revoke eagerly too". Either order is safe; shipping two
competing middlewares is not.

**One correction propagates between them.** AUTHZ-001's revocation-path count
(4 of 5 open) is the number that should appear in the final report for *both*
records. Phase 04's headline "3 of 4" does not match its own evidence table.

### 2. Ownership boundaries — independently verified (point 4)

The auditor claims **no boundary was crossed**. That claim is **verified**. All
five boundaries checked against source, not against the report's self-assessment:

| # | Boundary | Verdict | How verified |
|---|----------|---------|--------------|
| 1 | Did **not** re-file `AUT-002` | **Respected** | `AUT-002` appears only in Related Findings as *"remediated by this gate — not duplicated"*, and in the deliberate non-filing list. No second file of the missing-`logout()` paths. (Relationship documented above; see §1.) |
| 2 | Did **not** re-file `SRCH-008` / `is_banned`-in-search | **Respected** | `SRCH-008` is cited once, explicitly as *"explicitly NOT re-filed per the Phase 08 validator ruling recorded at `15-audit-authorization.md:132`"*. No visibility-predicate claim is made anywhere in the nine findings. The `is_banned` DENY term in AUTHZ-001 is a **session** term (can this identity act), not a **listing** term (is this ad public) — verified against `ads/views/listings.py:200-205` and `ads/services/listings_query.py:135`, neither of which is touched. |
| 3 | Two predicates kept **separate**, not collapsed, not a default-manager filter | **Respected** | AUTHZ-001(d) explicitly forbids folding `user__is_declined=False` (cited at the correct line, `listings_query.py:135`) into the gate. No default-manager filter is proposed anywhere. AUTHZ-005 also keeps publish gating in `apps/users` and ad visibility in `apps/ads`. **One amendment required**: the shared predicate must expose its queryset-level *terms*, or phases 06/08 remain blocked — see §3. |
| 4 | Did **not** re-file `AUT-001/004/005`, `AD-001`, `PII-103/104`, or phases 04/05/06/07/09 findings | **Respected** | `AUT-001`, `AUT-004`, `AUT-005`, `AD-001`, `PII-103` appear only as cross-references with explicit "not re-filed" notes. The one place AUTHZ-003's *Impact* leans on AUT-005 (moderator self-escalation) is used as a dependency argument, and AUTHZ-003 says so in as many words: *"the `UserAdmin` form defect itself is `AUT-005` / `04-AUT-004` / `PII-103` and is **not** re-filed here."* I re-derived the underlying facts without reusing the auditor's numbers (22-field form; `user`/`is_superuser`/`user_permissions` editable; plaintext password write observed) so the cross-reference is not load-bearing on their evidence. |
| 5 | Phase-05 dead approval path **verified and attributed**, not duplicated | **Respected** | Independently reproduced: `approve_ad(ON_MODERATION) -> False`; `approve_ad(ON_MODERATION_FAILED) -> False`; `bulk_approve(queryset of 2) -> 0`; `POST /moderation/approve/<id>/ -> 404`; `POST /moderation/review/<id>/approve/ -> 404`; `POST /moderation/reject/<id>/ -> 302`; `POST /moderation/ban/<id>/ -> 302`. The single added observation — that `reject` and `ban` are the only working moderator write actions — is an authorization-surface fact, not a re-file of `05-VAL-003`. |

**No boundary violation found.** Two observations, neither a violation:

- AUTHZ-005's coupling to `PII-105` is a *sequencing* dependency that neither
  phase recorded. AUTHZ-005 depends on PII-105's DECLINE-reversibility decision,
  because option (a) there removes the web-login block and leaves the publish
  gate as the only control. Recorded here so neither phase is surprised.
- AUTHZ-003's Impact cites AUT-005's self-escalation. Legitimate as a
  dependency, and correctly labelled. It does mean the *aggregate* severity of
  the pair must not be re-banded downward by fixing AUTHZ-003 alone.

### 3. The open cross-phase decision: SRCH-004 / SRCH-008 (point 5)

**Question asked:** is this phase expected to unblock them?
**Answer: no — phase 15 does not own them, and cannot unblock them by itself.**

Phase 08's validator recorded the state: `SRCH-004` and `SRCH-008` are
**owner-blocked** and have now been open across two phases; `SRCH-008` folds
into `SRCH-004` completely; and both are *already* owned by phase 06 via
`06-PII-104` recommendation item 2. This phase's own handbook
(`15-audit-authorization.md:132`) is explicit that "what is public" predicate
*semantics* stay with phases 05/08 and that phase 15 only verifies that
non-public objects are not reachable through authorization failures. Phase 15
correctly did not re-file them, and re-filing them would have violated boundary
2.

**But phase 15 can and should remove the *technical* blocker without taking
ownership.** The enabling gap both phases identified is that
`get_account_state()` is instance-level, so no queryset filter can call it.
AUTHZ-001 is about to create a shared account-state predicate; if that predicate
is instance-level only, the gap is reproduced one module over and the items stay
blocked for a fourth phase. **This is the decision that is needed, and it is
small:**

> **DECISION REQUIRED (AUTHZ-001):** the shared account-state predicate must be
> declared at two levels from one source —
> (a) a **per-request verdict** for the web gate and the bot middleware
> (instance-level, phase 15), and
> (b) the named **`User` flag terms** a queryset can be composed from
> (querysets-level, consumed by `06-VAL-003` on `User`/`SavedSearch` and by
> `SRCH-004` on `Ad`).
> Phase 15 owns (a) and the *shape* of (b). Phase 06 owns the `User` audience
> predicate's semantics; phase 08 owns the `Ad` ad-visibility predicate's
> semantics. **`IMMEDIATE_ALERTS_ENABLED` must stay `False` until both land**
> (default `False`, `config/settings/base.py`; the daily digest is live and
> ungated today).

**The product decision that is still outstanding** — and phase 15 should state
it plainly rather than resolve it: whether `is_banned` belongs in the
**public-visibility** predicate. Phase 08 folded `SRCH-008` into `SRCH-004`
precisely so the question is argued as one product decision (should a banned
seller's ads stay publicly visible?) rather than smuggled in as a consent fix.
That decision is a product call, not an authorization call, and no amount of
work in phase 15 settles it. It is now open across three phases; the
recommended next step is to put it in front of the product owner with the
one-paragraph version of the trade-off, not to re-file it a fourth time.

---

## Findings Requiring Architectural or Structural Change

Six of nine. The three that are not are cheap and should be taken first — they
also de-risk the expensive ones.

**1. One shared account-state decision point, at two levels — AUTHZ-001 (+ AUTHZ-005)**
The single most important change in the phase, and the one other phases are
waiting on. Requires: a named predicate in `apps/users/services/account_state.py`
returning a reason enum; a `StrEnum` reason type per project rule 10;
`AccountStateMiddleware` refactored to call it (so the bot and web answers are
byte-identical by construction, not by parallel maintenance); an
`AccountStateGateMiddleware` in `apps/users/middlewares/` registered immediately
after `AuthenticationMiddleware`; `logout(request)` plus a 403/redirect on deny;
and the queryset-level terms (Cross-Phase §3). Ordering: the extraction must
land with the middleware in **one** commit, and AUTHZ-005's
`_check_publish_permission` refactor must land in the **same** commit, or the
project ships two competing account-state vocabularies — which is exactly the
class of defect this finding exists to end. Effort: M, not S. The report's
1-person-day estimate does not include the bot-side refactor, the reason enum,
or the queryset terms.

**2. A declared moderator contract and one role resolver — AUTHZ-003**
Not the 17-class mixin. Requires: `media_gate` on the role predicate;
`AdminSite.has_permission` reconciled with `User.role` (one method); the
moderator contract written down (does `is_staff` grant write access to the
moderation criteria, the audit log, and the support desk?); and a test that
iterates `admin.site._registry` to assert it. The `is_staff`-grants-full-`ADMIN`
option (i) matches the existing `staff_required` decorator and this project's
documented "is_staff IS the moderator role" position; option (ii) (a seeded
`Group`) matches Django's model and contradicts the documented position. **Pick
one, write it down, enforce it in a test.** Effort: S for items 1-2 and 4; the
contract decision is the real cost.

**3. An explicit authorization contract at the service boundary — AUTHZ-002 (+ AUTHZ-007)**
Requires: `SubmitAdInput.user_id` becomes a *meaningful* actor id — meaning
`edit.py:170` and `:213` must pass `request.user.id`, and `submit_ad` must
compare it on the locked row; plus `ad_edit` moves its ownership assertion
inside `transaction.atomic()` on the locked instance, matching the pattern
`ad_archive` and `ad_reactivate` already use in the same file. The
architectural point: **the service stops being a trusted-internal orchestrator
and starts being a boundary.** Effort: S. The docstring currently says nothing
about the trust model, which is the real reason the omission was invisible.

**Not structural:** AUTHZ-004 (a route/method change plus a form, gated on one
product decision about the deep-link UX), AUTHZ-006 (one method), AUTHZ-008
(two one-line edits plus four test assertions), AUTHZ-009 (one helper, and it
should ride along with #1).

---

## Rollout Analysis

| ID | Risk | Backward-compatible? | Must-cover test gap |
|----|------|----------------------|----------------------|
| AUTHZ-001 | **High** — the gate will terminate live sessions the instant a moderator bans, declines or soft-deletes anyone, including the operator's own test account. It will read as a bug in the first 24 h. | Partly — public routes untouched; `is_active=False` already redirects today | Each of `is_banned`/`is_deleted`/`is_declined`/`consent_revoked` ⇒ logout + 403; anonymous and public routes unaffected; a restricted-but-valid seller (`ads_auto_publish=False`) still reaches the dashboard; **the bot's allow/deny answers are byte-identical before and after the extraction**; the queryset-level terms are reachable from a filter. |
| AUTHZ-003 | **High, and the report understates the direction** — the *correct* fix (option i: `is_staff` grants full ADMIN) is a deliberate privilege **expansion** for moderators; the *proposed* fix (blanket mixin) is a privilege expansion on 7 read-only models. Both need an explicit review of the 17-model matrix, not a rubber stamp. | **No** — the moderator contract changes either way | A provisioned moderator can reach the moderation-critical models; a seller and an anonymous user still get 302/403 on every `/admin/` URL; a superuser with `is_staff=False` is either given admin access or declared unsupported — **pick one in the test**; `media_gate` answers identically for staff and superuser. |
| AUTHZ-002 | **Low** — a strict guard surfaces any caller that was relying on the check's absence. | Yes | `submit_ad` with a mismatched `user_id` leaves the row byte-identical **and** returns `(False, [...])`; **the web caller now passes `request.user.id`, asserted explicitly**; the bot `/post` → `process_preview` path still publishes. |
| AUTHZ-007 | **Low** — narrower than the report states, because the correct pattern already exists twice in the same file. | Yes | Owner edit GET renders 200 and POST saves; non-owner GET and POST both 403; the DB-003 row lock is still taken; the reactivation and error branches use the authorized locked row. |
| AUTHZ-005 | **Medium** — the answers for `is_declined` and `consent_revoked` change, and `test_account_state.py` currently pins the old ones. | **No** | `is_declined=True` and `consent_revoked` ⇒ publish denied from both the bot middleware and the shared predicate; `ads_auto_publish=False`, banned and deleted ⇒ still denied. |
| AUTHZ-004 | **Medium** — a GET deep link from a bookmark, a messenger or a headless client must degrade gracefully. | **No** — route and method change | `GET /login/issue/` no longer writes (or 405s); the CSRF-protected POST issues a token; both rate limits still apply; the bot's `/start login_<token>` handshake is unchanged; **`apps/users/tests/test_login_issue_template.py` and `apps/core/tests/test_login_issue_template.py` still pass** (see AUTHZ-004 additions). |
| AUTHZ-006 | **Low** — a superuser relying on the accidental grant is unaffected (a superuser passes the new check). | Yes | `has_delete_permission` is `False` for `AnonymousUser` and a seller, `True` for a superuser; the HTTP delete view still returns 302 for non-staff. |
| AUTHZ-008 | **Low, but four assertions break** — the report's `422` risk is refuted; the real breakage is `test_decorators.py:185,198` and `test_priority_service.py:489`, which assert the wrong `WWW-Authenticate` value. | **No** — status code and header change | `GET /moderation/api/v1/bulk-action/` returns 405 for an ADMIN; the 401/403 responses are unchanged; the four pinned assertions are updated **in the same commit** (production code is king; the assertions are what change). |
| AUTHZ-009 | **Low** — new log lines on denial paths increase volume; keep at `WARNING` with a stable reason code. | Yes | A denied request emits exactly one line containing the reason code and the user id; the counter increments once per denial. |

**Execution readiness.** All cited file:line anchors were re-read at this
commit, and every runtime claim was reproduced. Targets verified to exist:
`AccountStateMiddleware`, `submit_ad`, `ad_edit`, `ad_archive`, `ad_reactivate`,
`can_publish_ad`, `can_login`, `get_account_state`, `login_issue`,
`staff_required`, `staff_required_api`, `ban_user_for_ad`, `bulk_ban_users`,
`approve_ad`, `bulk_approve`, and all 17 registered `ModelAdmin` classes.
**7 of 9 findings are immediately actionable.** The two that are not:
AUTHZ-003 (blocked on the moderator-contract decision) and AUTHZ-005 (blocked on
`PII-105`'s DECLINE-reversibility decision and on the
`spec-index`/`technical-specification` conflict).

---

## Required Fixes

Ordered by dependency, not by severity.

**P0 — ship before rollout**

1. **AUTHZ-007 + AUTHZ-002 — one commit, two scopes.** First, move `ad_edit`'s
   ownership assertion inside `transaction.atomic()` on the locked instance,
   matching `ad_archive`/`ad_reactivate` in the same file. Then make
   `SubmitAdInput.user_id` a real actor id: `edit.py:170` and `:213` pass
   `request.user.id`, and `submit_ad` compares it on the locked row and returns
   `(False, [...])` on mismatch. **Assert on the row being unchanged, not on the
   return value.** Record the trust model in the `submit_ad` docstring.
2. **AUTHZ-001 + AUTHZ-005 — one commit, one predicate.** Extract
   `account_state_verdict()` with a `StrEnum` reason; refactor
   `AccountStateMiddleware._check_user_state` **and** `_check_publish_permission`
   to call it; add `AccountStateGateMiddleware` after
   `AuthenticationMiddleware`; DENY on `{is_banned, is_deleted, is_declined,
   consent_revoked}`; `logout(request)` on deny; declare the queryset-level
   `User` terms in the same module. Do not ship `can_publish_ad` and the new
   verdict side by side — delete it or reduce it to a wrapper, and retarget
   `test_account_state.py` to the new predicate in the same commit.
3. **AUTHZ-003 (narrow form).** `media_gate` → the role predicate;
   `AdminSite.has_permission` → `is_active and role == UserRole.ADMIN`; write
   the moderator contract; add the `admin.site._registry` test. **Do not add the
   blanket `AdminRolePermissionMixin`** (VAL-005). Cite `04-AUT-005` as a hard
   prerequisite and do not close AUTHZ-003 without it.
4. **AUTHZ-006.** `DailyAdMetricsAdmin.has_delete_permission` consults `request`
   (`role == ADMIN and is_superuser`), mirroring `AnalyticsEventAdmin`. Plus one
   regression test. No refactor of the other constant-returning overrides.

**P1 — ship in the same cycle**

5. **AUTHZ-004.** Decide the deep-link UX, then move token issuance behind
   `@require_POST` + CSRF. Re-run the two `test_login_issue_template.py` files.
6. **AUTHZ-009.** One reason-coded denial helper used by the decorators *and* the
   ad views, plus the `authz_denials_total` counter. Land with #2 so the new
   gate is instrumented on day one.
7. **AUTHZ-008.** Check the method first (405), drop or rename the `WWW-Authenticate`
   header, and update the four pinning assertions in the same commit.

**P2 — record the decisions**

8. **VAL-001** — a ruling on the CSRF severity entry for state-changing `GET`s,
   applied consistently across phases.
9. **Cross-Phase §3 decision** — the two-level predicate contract, and the
   escalation of the `is_banned` product decision to the product owner (open
   across three phases).
10. **VAL-002/003/004** — the evidence-quality and tracker corrections below.

---

## Advisory Recommendations

Not required to close any finding; each prevents a class of the above.

1. **Encode the introspection instrument as a test, not a one-off probe.** A
   single test that iterates `admin.site._registry`, asserts a documented
   moderator contract, and fails on any class that diverges is the cheapest
   durable defence in this phase — and it is the instrument that produced the
   strongest evidence in both this report and the auditor's. It is also the
   instrument that would have caught the `DailyAdMetricsAdmin` constant.
2. **A `has_delete_permission`-style rule: `True` requires a `request`
   consultation.** Deny-by-default on grants. Three of the phase's findings are
   "an override that ignores its argument", which is a shape, not three bugs.
3. **Decide the moderator contract in a *decision record*, not in a mixin.** The
   question "what may `is_staff` do?" has one answer and it belongs in
   `docs/`, with the registry test as its executable form. A base class answers
   a different question ("how is the role read?") and answering it uniformly is
   what would grant write access to the audit log.
4. **Make the `submit_ad` trust model explicit in the docstring, and add a
   `guards:` line to the DTO docstring** naming the invariant every caller must
   uphold. The DTO advertised an actor and the body ignored it; that gap is
   invisible in review precisely because nothing states the precondition.
5. **Promote `docs/99-agent/test-audit-block-f-findings.md:193` to a live
   assertion.** It already flags `can_publish_ad`/`is_declined`; once the
   predicate is fixed, that line becomes a test and stops being a comment that
   a future audit re-discovers.
6. **A pre-merge check for `ModelAdmin` drift.** A tiny script that prints
   `(model, overridden-permissions, effective-per-model-fallback)` as a diffable
   table, run in CI or at review time. This finding's entire cost is that the
   table did not exist.

---

## VAL Findings (audit-input and rollout defects)

### VAL-001 — Severity taxonomy is ambiguous for state-changing `GET` requests

**Type:** audit-input defect · **Severity:** Medium · **Blocks:** AUTHZ-004 banding

`15-audit-authorization.md:8` (CRITICAL) reads *"State-changing web request
accepted without a valid CSRF token"* — no method restriction. §2's zone and §5(h)
read *"State-changing POST/PUT/DELETE"* and *"CSRF is not enforced on read-only
(GET) endpoints"*. `/login/issue/` is a `GET` that is **not** read-only: it
inserts a `LoginToken` row. A literal §8 reading makes AUTHZ-004 CRITICAL; a §5(h)
reading makes it a MEDIUM CSRF gap. The auditor flagged the ambiguity rather than
deciding it silently, which is correct, but it must now be decided once and
applied to every phase that hits it. **Recommendation:** amend §8 to
*"state-changing request (any method) that mutates state without a CSRF token,
where the mutation affects an authenticated identity or a protected resource"*
— which lands AUTHZ-004 at MEDIUM on stated grounds rather than by argument.

### VAL-002 — Appendix A mixes missing routes with permission outcomes

**Type:** evidence quality · **Severity:** Medium

Four of the admin URLs in the report's Appendix A do not exist, and their `404`s
are therefore route-resolution failures being read as authorization results:

```text
  /admin/search/savedsearch/          -> no ModelAdmin for search.SavedSearch
  /admin/media/mediafile/             -> no ModelAdmin for media.MediaFile
  /admin/trust/sellertrustscore/      -> no ModelAdmin for trust.SellerTrustScore
  /admin/currencies/exchangerate/     -> no ModelAdmin for currencies.ExchangeRate
  /admin/analytics/analytics-event/   -> typo; the registered path is
                                         /admin/analytics/analyticsevent/
```

A fifth path shape needs stating as a fact rather than an accident: **four
models have no admin surface at all** — `SavedSearch`, `MediaFile`,
`SellerTrustScore`, `ExchangeRate`. Whether that is deliberate (no UI needed) or
an omission is a question this phase does not own, but the report presents four
`404`s in a role matrix as if they were denials. Rebuild the table from
`admin.site._registry` and label non-registered models explicitly.

### VAL-003 — Stale field counts in the "verified, not re-filed" section

**Type:** evidence accuracy · **Severity:** Low

```text
  report: UserAdmin ... "among 25 base fields"    actual: 22 editable base fields
  report: AdAdmin   ... "among 29 base fields"    actual: 24 editable base fields
```

The *substance* of both cross-references is right (and I re-derived both
independently: `password` is a plain `CharField`/`AdminTextInputWidget` with no
hashing hook; `user`, `status`, `published_at`, `original_published_at`,
`archived_at`, `deleted_at` are all editable on `AdAdmin`). Only the counts are
stale, most likely carried over from `04-VAL-004` / `AD-001`. Because these lines
are the *evidence* for a not-re-filed decision, stale numbers weaken an
otherwise clean boundary statement. Take the counts from introspection.

### VAL-004 — Tracker hazard: `AUTHZ-` / `AUT-` / `AUTZ-` are three prefixes for
one remediation stream

**Type:** audit-input defect · **Severity:** Low (tracker hygiene) · **Blocks:**
remediation-tracker keying

The auditor's deviation from the handbook's `AUTZ-` prefix is **correctly
justified and should be upheld**: `AUTZ-003` is an in-source marker in
`apps/users/tests/test_user_roles.py:2`, so the handbook prefix would collide
with shipped source. But the collision record is incomplete. Phase 04's
`VAL-002` already established that `AUT-001`, `AUT-002` and `AUT-003` are in use
as bare identifiers by unrelated work (including a *previously remediated* item
at `apps/users/views/consent.py:256`), and phase 06 and 08 validators both
recorded the same. So the stream now has three prefixes and one burned set.
**Requirement propagates:** the final report must key every finding
phase-qualified (`04-AUT-002`, `15-AUTHZ-001`), and any tracker must refuse bare
`AUT-001`-style keys. The same requirement already appears in `04-VAL-002`,
`05-VAL-005` and `08-VAL-005`; consolidate it once in the final report rather
than restating it per phase.

### VAL-005 — Rollout safety: `AUTHZ-003`'s proposed mixin is a privilege expansion

**Type:** rollout safety · **Severity:** High (blocks implementation as written)

The recommendation *"add a shared `AdminRolePermissionMixin` … that all 17
admins inherit, resolving `ADMIN` via `request.user.role == UserRole.ADMIN` and
gating `add` / `change` / `delete` on separate, explicit methods"* has an
unexamined second-order effect. Any class that does not re-declare an opt-out
would gain the grant, and seven classes are read-only **by deliberate
data-protection policy**:

```text
  AnalyticsEventAdmin     add/change/delete = False   "Events are preserved for metrics"
  ModeratorActionLogAdmin add/change/delete = False   audit trail
  ConsentRecordAdmin      add = False                 GDPR Article 7(1) record
  LoginTokenAdmin         add/change = False          credential material
  SupportTicketAdmin      add/delete = False          audit trail
  SiteConfigAdmin         add/delete = False          singleton
  AdImageAdmin            add/change/delete = False
```

Implementing the mixin as described turns an audit trail into a mutable table
and a consent record into an editable one — a strictly larger security incident
than the one the finding is fixing. This is a **rollout-safety blocker on the
recommendation, not on the finding**, and it is why the replacement in the
AUTHZ-003 section is deny-by-default. The narrower alternative — fix
`media_gate` and `AdminSite.has_permission`, write the contract, test it — closes
the real defect at a fraction of the cost and with none of this risk.

---

## Warnings

- **Double-counting risk (the highest-probability failure in this phase).**
  AUTHZ-001 ↔ `04-AUT-002` are one defect; AUTHZ-003 ↔ `04-AUT-005` are one
  remediation. A tracker that counts four HIGH items here has counted two
  problems.
- **The severity band on AUTHZ-003 is doing more work than the evidence
  supports.** It is held at HIGH on taxonomy grounds while its stated impact has
  been substantially reduced. Re-band it explicitly, and do not let the re-band
  reach `04-AUT-005`.
- **AUTHZ-002's guard is a trap as written.** Shipping `if ad.user_id !=
  input.user_id` without also changing `edit.py:170`/`:213` produces a green
  test suite and zero protection.
- **A reproduction of AUTHZ-002 that returns `False` is not a refutation.** The
  write happened either way; only the moderation outcome differs.
- **`IMMEDIATE_ALERTS_ENABLED` must stay `False`** until both the audience and
  ad-visibility predicates exist. The daily digest is live and ungated today.
- **Reading `admin.py` is not a sufficient instrument for this surface.** The
  changelist gate is a disjunction; a per-method read gets it wrong in both
  directions. Three separate auditors have now been misled by source-reading this
  area.
- **Do not let the phase-15 CSRF ruling be made locally** (VAL-001) — it will be
  cited by every later phase that finds a state-changing `GET`.

---

## Checkpoints

### Checkpoint 1 — Auditor analysis
- **Stage:** Auditor analysis
- **Findings in scope:** 9 (CRITICAL 0 · HIGH 3 · MEDIUM 4 · LOW 2)
- **Evidence anchor:** `.ai/audit/15-authorization/findings.md`, R-01…R-08, Appendices A–D
- **Dependencies / blockers:** none
- **Checkpoint status:** closed

### Checkpoint 2 — Researcher verification
- **Stage:** Researcher verification
- **Findings in scope:** 9
- **Cross-phase conflicts:** 1 (`AUTHZ-001` ↔ `04-AUT-002` — same defect, different phase half; resolved by `04-VAL-001`'s pre-existing split, documented in §1)
- **Merge candidates:** 0 accepted. 2 rejected merges: (`AUTHZ-001`,`04-AUT-002`) — coupled, not merged, per `04-VAL-001`; (`AUTHZ-002`,`AUTHZ-007`) — different scope, must stay separate IDs
- **Evidence anchor:** 5 private-instance probe runs + `ruff` + `basedpyright`; `admin.site._registry` introspection
- **Checkpoint status:** closed

### Checkpoint 3 — Per-finding validation
- **Stage:** Per-finding validation
- **Findings in scope:** 9 (Validated 3 · Validated-with-correction 3 · Reclassified 1 · Adjusted 2 · Rejected 0)
- **Rejected sub-claims:** 6 (see Rejected Sub-Claims)
- **VAL- findings:** 5 (VAL-001…VAL-005)
- **Evidence anchor:** this document; all runtime claims reproducible against the recorded commit
- **Checkpoint status:** closed

### Checkpoint 4 — Final audit
- **Stage:** Final audit
- **Findings in scope:** 9 + 5 VAL
- **Pipeline integrity:** OK — no cross-phase conflict left unresolved; 2 conflicts documented and resolved by pre-existing rules; 1 decision escalated (§3)
- **Checkpoint status:** open (pending the final consistency pass)
