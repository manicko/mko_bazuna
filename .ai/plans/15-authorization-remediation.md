---
plan_id: "15-authorization-remediation"
phase: "15"
phase_name: "Authorization & Access Control"
source_report: ".ai/audit/99-validation/15-authorization-validated-findings.md"
source_findings: ".ai/audit/15-authorization/findings.md (deleted in the working tree — not an input)"
code_context: ".ai/tmp/code-context-phase15.md"
date: "2026-09-29"
planner: "Planner (subagent)"
anchor_commit: "ba23277"
report_anchor_commit: "ba23277 (re-derived by the Auditor's code context; the validated report does not state its own anchor)"
status: "planned"
findings_in_scope: 9
findings_still_exist: 9
findings_partial: 0
findings_merged: 0
findings_already_fixed: 0
findings_rejected: 0
val_findings_open: 5
blocks: 12
---

# Execution Plan — Phase 15 Remediation (Authorization & Access Control)

## 0. Header, provenance and scope statement

### 0.1 Provenance

| Item | Value |
|---|---|
| **Source report (authoritative)** | `.ai/audit/99-validation/15-authorization-validated-findings.md` (1 205 lines, 9 `AUTHZ-` findings + 5 `VAL-` items, self-contained) |
| **Code context** | `.ai/tmp/code-context-phase15.md` (891 lines, Auditor) |
| **Deleted input** | `.ai/audit/15-authorization/findings.md` — **gone from the tree** (tracked deletion). It is **not** an input and **not** a defect. **No block may restore, recreate or edit anything under `.ai/audit/`** |
| **This plan's anchor** | `ba23277` (`git rev-parse --short HEAD`, taken before writing) |
| **Date** | 2026-09-29 |
| **Findings in scope** | 9 units (`AUTHZ-001` … `AUTHZ-009`) + 5 `VAL-` items (`VAL-001` … `VAL-005`) |
| **State at the anchor** | **9 still exist unchanged · 0 already fixed · 0 rejected · 0 merged · 0 pre-empted** · 5 `VAL-` open. **Zero pre-empted** because only plans 01 and 02 are `executed`; plans 03–14 are all `planned` |
| **Validated severity split** | **0 CRITICAL · 3 HIGH (`AUTHZ-001/002/003`) · 4 MEDIUM (`004/005/006/007`) · 2 LOW (`008/009`)** — with the re-band and residual notes of §0.4 |
| **Execution blocks** | **12** — 1 `mechanical`, 5 `behavioural`, 4 `structural`, 2 `conditional` (per-finding classification in §2) |
| **Implementor concurrency** | **1**, strictly sequential (project rule: only one implementor at a time) |
| **Migration** | **none.** No block ships a Django migration, and no block allocates an `AdvisoryLockId` |
| **i18n** | BLOCK 6 (gate denial) and BLOCK 10 (the CSRF form) may add **user-visible** strings; both must carry non-empty `ru` and `bs` `msgstr` and pass `test_i18n_completeness.py` |

**The anchor has drifted seven times across this programme** — `9443ade` → `4fd8bd0` →
`aa2a6b0` → `6413df5` → `e57f8f8` → `d42f778` → `ba23277`. The Implementor must take their **own**
`git rev-parse --short HEAD`** before BLOCK 1, and re-read immediately before editing any artefact
listed in §5.3. **The tree is the authority**: where the validated report and the tree disagree,
§0.2.5 says so and this plan follows the tree.

**`AUTHZ-` is a chosen, defended namespace — read this before citing one finding ID.** The
handbook's own prefix is `AUTZ-`, and the auditor's deviation from it is **correct and is upheld
by this plan**, because `AUTZ-003` is an **in-source marker shipped today** in
`src/backend/apps/users/tests/test_user_roles.py` (module docstring) — the handbook prefix would
collide with shipped source. But the collision record is incomplete (`VAL-004`): `AUT-001`,
`AUT-002` and `AUT-003` are additionally in use as **bare** identifiers in unrelated work, so the
stream now has **three prefixes and one burned set**.

**Citation convention adopted by this plan (binding in every commit body, comment, docstring and
tracker entry):** write `AUTHZ-0NN (validated 2026-09)` for a finding of this phase, and
`15-AUTHZ-0NN` when a bare key would be ambiguous. **Never** write a bare `AUT-001`-style key; the
tracker **must** refuse it. This is the same requirement already filed by `04-VAL-002`,
`05-VAL-005` and `08-VAL-005`; BLOCK 12 consolidates it once.

**Double-counting warning, stated once and repeated in §0.4.** `15-AUTHZ-001` and `04-AUT-002` are
**one defect with one remedy**. `15-AUTHZ-003` and `04-AUT-005` are **one remediation**. A tracker
that counts four HIGH items in this phase has counted **two** problems.

### 0.2 Evidence basis — read this before executing any block

#### 0.2.1 What the validated report establishes

Nine findings, all still present at `ba23277`. Verdicts: **3 CONFIRMED unchanged · 3 CONFIRMED with
content correction · 1 ADJUSTED (`AUTHZ-003`) · 1 RECLASSIFIED to SPEC-DEVIATION (`AUTHZ-005`) ·
1 ADJUSTED (`AUTHZ-008`) · 0 rejected whole**. Six **sub-claims** were rejected (§0.2.5, §0.4). Two
**recommendations** were rejected outright — `AUTHZ-003`'s blanket `AdminRolePermissionMixin`
(`VAL-005`) and the `AUTHZ-002` guard as literally written. Every runtime claim was reproduced
against a **private** `postgres:18-alpine`; the shared test container was never connected to.

**The phase's single most important structural fact, and the one that lowers BLOCKS 5–7's design
risk:** the bot's DENY set is **already exactly** `{is_banned, is_deleted, is_declined,
consent_revoked}` and is **already pinned by a shipped test** —
`src/telegram_bot/tests/test_account_state_middleware.py::TestCrossPredicateAgreement::test_matches_explicit_formula`
asserts that literal formula. **`AUTHZ-001` is therefore an extraction of existing, tested
semantics, not a new policy.** The risk in BLOCKS 5–6 is not "what should the gate deny"; it is
"can two processes answer identically *by construction* rather than by parallel maintenance".

#### 0.2.2 The three binding constraints that constrain every block in this plan

1. **Security fixes must fail closed by default, and must not depend on a default-manager filter.**
   This is a **binding** constraint, restated per block where relevant. Concretely: every gate
   this plan ships denies when its evidence is missing, absent or unevaluable; a new
   `ModelAdmin` permission answer defaults to **`False`**, never `True`; a new predicate purpose
   denies for an unrecognised account state; and a user whose session cannot be resolved is denied,
   not allowed. **A default-manager filter on `User` (or any app) is FORBIDDEN** — it would hide
   withdrawn users from `AccountStateMiddleware._resolve_user`, which resolves on `chat_id`
   precisely because withdrawn users have `telegram_id` nulled, and would re-open a hole rather
   than close one. Source of the prohibition: phase 06 §5.2, phase 08 §5.2, phase 10 §5.2.
   **Equally binding: the account-state gate is a *session* term ("can this identity act") and ad
   visibility is a *listing* term ("is this ad public").** `user__is_declined=False` must **not** be
   folded into the gate; two predicates, kept separate. Source: `AUTHZ-001(d)`, restated by phase 05
   §5.2 and phase 08 §5.2.
2. **Production code is king.** A test that pins a defect gets the **defect** fixed, not the code
   bent — and the test change lands **in the same commit** as the production change, with the rule
   cited by name in the commit body. This plan pre-authorises **six** such changes, and no others:
   BLOCK 3's five `staff_required_api` test methods; BLOCK 4's `test_submit_ad_fetches_inside_atomic`
   *only if* the guard is placed as instructed; BLOCK 5's retarget of `test_account_state.py`; BLOCK 7's
   `test_declined_user_can_publish`; BLOCK 2's `test_ad_edit_get_path_not_locked` **only if** the
   lock count is preserved as instructed. **Any other test edit that weakens an assertion is a
   finding against the block, not a prerequisite for it.**
3. **Small, focused modules and functions. Composition over inheritance. Follow existing patterns.
   No new abstraction without strong justification. No speculative redesign. No scope creep.** Three
   of this phase's most tempting remedies are rejected on this rule and are recorded as
   **prohibitions** rather than options: the 17-class `AdminRolePermissionMixin` (`VAL-005`),
   the blanket sweep of every constant-returning `has_*_permission` override, and a second
   account-state service module. **Every accepted remedy in this plan reuses a shipped primitive:**
   `ad_archive`/`ad_reactivate`/`ad_delete`'s locked-instance check, `cabinet/views/saved_searches.py::_user_search`'s
   scoped lookup, `AnalyticsEventAdmin.has_delete_permission`'s `False`, `apps/core/middleware/`'s
   one-module-per-concern package shape, and the existing `StrEnum` home in `apps/core/enums.py`.

#### 0.2.3 The protection surface as re-derived from the tree at `ba23277`

These are the load-bearing facts. Anything in a block's premise that is **not** in this table or
§0.2.4 must be re-read before the block starts.

| # | Fact | Where it is verified | Consequence |
|---|---|---|---|
| F1 | `MIDDLEWARE` has **14** entries and **no** account-state gate. `AuthenticationMiddleware` is the 7th | `config/settings/base.py::MIDDLEWARE`, re-read by this Planner | BLOCK 6 inserts **immediately after** `AuthenticationMiddleware`; the list is **append-only in place**, never reordered (§5.3) |
| F2 | `can_login` has **exactly one** production call site (`apps/users/views/consent.py::login_status`) | whole-`src` grep for `can_login` | `can_login` is a **one-shot** gate today. BLOCK 5 must not leave it as a second, divergent vocabulary |
| F3 | `can_publish_ad` has **three** non-test references — its definition, the import in `apps/users/services/__init__.py`, its `__all__` entry — and **zero** production callers | whole-`src` grep | AUTHZ-005 is a **missing integration**, not dead code. `VAL`/phase 10 **forbid** deleting it; BLOCK 5 reduces it to a wrapper over the shared declaration and BLOCK 7 changes its policy |
| F4 | The bot's live methods are **`_evaluate_user_state`** and **`_evaluate_publish_permission`**; **`_check_publish_permission` does not exist**; `_check_user_state` is a load-bearing test-facing wrapper that `__call__` does not use | `src/telegram_bot/middlewares/permissions.py` | **C-2.** Targeting the report's name produces an `AttributeError` or, worse, a **silent no-op refactor** |
| F5 | The bot's interaction DENY set is already `{is_banned, is_deleted, is_declined, consent_revoked}` and both gates **fail open for `user is None`** **by design** | same module + `TestCrossPredicateAgreement` | BLOCK 5 preserves the fail-open-for-unregistered **for the bot only** (the handler's own gate rejects an unregistered identity). The **web** gate must fail **closed** (constraint 1) |
| F6 | Four answers to "is this ADMIN": `AdminSite.has_permission` (`is_active and is_staff`, **Django's, not overridden in this repo**), `User.role` (`is_staff or is_superuser`), `staff_required` (`role == ADMIN`), `media_gate`'s raw `request.user.is_staff`. A fifth partial answer lives in the 17 `ModelAdmin` overrides | `apps/users/models.py::User.role`, `apps/moderation/views/decorators.py`, `apps/ads/views/listings.py`, `admin.site._registry` | BLOCK 9 |
| F7 | Registry census: **17** classes (16 project + Django's auto-registered `auth.group`); **3** override `has_view_permission`; **14** fall back to per-model perms; **3** declare no override at all. The changelist gate is the **disjunction** `has_view_or_change_permission` | `admin.site._registry` introspection | **Reading `admin.py` and checking `has_view_permission` in isolation gets 14/17 and is wrong.** BLOCK 9's contract test must iterate the registry, not read source |
| F8 | Seven admin classes are read-only **by deliberate policy** (`AnalyticsEventAdmin`, `ModeratorActionLogAdmin`, `ConsentRecordAdmin`, `LoginTokenAdmin`, `SupportTicketAdmin`, `SiteConfigAdmin`, `AdImageAdmin`) | the registry | **C-5 / `VAL-005` — a prohibition, not an option** |
| F9 | `UserAdmin` declares **no** `fields` / `fieldsets` / `form` / `get_readonly_fields` override, and `has_change_permission` returns bare `request.user.is_staff` with **no `obj` check** | `apps/users/admin.py` | BLOCK 9 must **cite** `04-AUT-005`, not fix it. **And** a registry test that POSTs to a moderator's own row **de-staffs the actor** (U4) |
| F10 | `ad_edit` authorizes on the **unlocked** read and re-reads under `select_for_update()` **without re-checking**; `ad_archive`, `ad_reactivate` and `ad_delete` already do it correctly | `apps/ads/views/edit.py` | BLOCK 2 is a **one-function consistency fix with an in-file precedent**, not a design question |
| F11 | `apps/ads/views/edit.py` passes **`user_id=ad.user_id`** at **both** `SubmitAdInput` literals | same file | **C-6.** A literal `if ad.user_id != input.user_id` guard is a **tautology** on the web path |
| F12 | `DailyAdMetricsAdmin.has_delete_permission` returns a constant `True` and never touches `request`; `AnalyticsEventAdmin.has_delete_permission` returns `False` for the same reason class. **Every** other constant override in the registry returns `False` | `apps/analytics/admin.py` | BLOCK 1 is one method. The blanket sweep is **forbidden** (constraint 3) |
| F13 | `login_issue` carries **`@never_cache` only**, on a bare `path("login/issue/", …)`, and calls `issue_token()` unconditionally after two rate limits. `LOGIN_URL = "/login/issue/"` | `apps/users/views/consent.py`, `apps/users/urls.py`, `config/settings/base.py` | BLOCK 10 changes a route that **every anonymous `@login_required` redirect points at** |
| F14 | `staff_required_api`'s third branch is a **`return`**, not a fall-through, so the view body is never entered on a non-`POST`. `Bearer` appears in **three** places in the repo: the decorator and two test files. There is no DRF, no `authtoken`, no token middleware | `apps/moderation/views/decorators.py` | BLOCK 3: the report's `422` claim is **refuted**; delete it from the tracker |
| F15 | `apps/moderation/views/decorators.py` declares a module-level `logger` and makes **zero** `logger.*` calls. `favorite.py` also zero; `delete.py` 2; `edit.py` 3 | same module and siblings | BLOCK 8 |
| F16 | `reject_ad` and `ban_user` use an **inline** `if request.method != "POST": return redirect(...)` (302), while the sibling `approve_ad` already uses `@require_POST` (405) | `apps/moderation/views/review.py` | BLOCK 11 — **routed to phase 15 by phase 10's Q4, and not in the validated report** |
| F17 | `src/backend/apps/users/middlewares/` **does not exist** (nor `apps/users/middlewares.py`). `AccountStateGateMiddleware`, `resolve_admin_role` and `account_state_verdict` exist nowhere in `src/` | whole-tree search | BLOCK 6 creates the package, following `apps/core/middleware/`'s shape (a package with `__init__.py`, one module per concern) |
| F18 | `docs/01-spec/technical-specification.md` states, verbatim, *"No web-side middleware redirects soft-deleted users"*. **Shipping the gate falsifies that sentence on the day it lands**, and **phase 06 holds the file** | `docs/01-spec/technical-specification.md`, phase 06 `PII-113` | **C-4.** BLOCK 6 ships a **request**, never an edit. Routed to BLOCK 12 |
| F19 | `IMMEDIATE_ALERTS_ENABLED` still reads `env.bool("IMMEDIATE_ALERTS_ENABLED", default=False)` and is in `ALLOWED_ENV_VARS` | `config/settings/base.py` | **Must stay `False`** until the audience predicate (phase 06) and the ad-visibility predicate (phase 08) both land. Phase 15 changes it |
| F20 | `test_ad_edit_get_path_not_locked` asserts `source.count("select_for_update") == 1` over the whole `ad_edit` source; `test_submit_ad_fetches_inside_atomic` asserts the fetch is inside `atomic()` by `source.index()` | `apps/ads/tests/test_edit_views_locking.py` | BLOCK 2 and BLOCK 4 have a **hard** structural constraint each. A **second** locked read, or extracting the fetch into a helper, breaks them |

#### 0.2.4 The fourteen unverified-at-runtime claims, carried with their exact verification steps

The code context ran **no** test: the suite is Docker-only and the shared test database is a
single shared resource. Every claim below is a runtime fact the validated report asserts. **Each
must be re-derived before the block that depends on it starts**, and a block that *cannot* re-derive
it must record the claim as **not measured** rather than assert it.

| # | Claim | Status at `ba23277` | Exact verification step | Block that needs it |
|---|---|---|---|---|
| **U1** | `is_active=False` already yields a **302** on `/dashboard/` and `/save-search/`, while `is_banned` / `is_declined` / `is_deleted` / `consent_revoked` yield **200** | Report runtime. Statically derivable that a **new** session cannot be established (`ModelBackend.user_can_authenticate`), but **the status for an existing session is not statically derivable** | Start the DB, then a probe test that `force_login`s a user per flag and records the status of `GET /dashboard/` and `GET /save-search/` through the real middleware stack. **Never run against the shared DB concurrently with another agent** | **6 — and Q1**, whose entire premise is this claim |
| **U2** | 12 of 17 admin changelists return **403** for a plain `is_staff` moderator | Census re-derived statically (F7) and consistent; the HTTP status is not | One test that iterates `admin.site._registry` and records `has_view_or_change_permission` per identity | **9** |
| **U3** | A superuser with `is_staff=False` is **locked out of `/admin/`** (302) but **allowed** on `/moderation/queue/` and `/analytics/moderation/` (200) | Statically derivable and confirmed (F6); the status codes are runtime | The same registry/permission-matrix test as U2, plus one `client.force_login()` per identity | **9 — and the option (i) vs (ii) decision** |
| **U4** | A moderator can self-grant `user_permissions` (and can set `is_superuser`) through their own `UserAdmin` change form, and a POST that omits an unchecked `BooleanField` **silently clears `is_staff`** | Shape confirmed statically (F9); the self-grant and the de-staff are runtime | `force_login(moderator)` → `GET /admin/users/user/<own id>/change/` (expect 200) → POST with `user_permissions` set → re-read `has_perm`. **⚠ This probe de-staffs the actor: re-`force_login` between phases of it, or the block's later assertions fail spuriously** | **9** — and it is why BLOCK 9's contract test is **read-only over the registry** |
| **U5** | `UserAdmin` has **22** editable base fields; `AdAdmin` has **24** | The report's **corrected** numbers, **not re-measured**. `VAL-003` exists precisely because the report's own numbers were stale | `ModelAdmin.get_form(request).base_fields` for both classes, in the same probe as U4. **Do not take any count on trust from any document — measure it** | **9, 12** (`VAL-003`) |
| **U6** | `GET /login/issue/` writes a `LoginToken` under `enforce_csrf_checks=True` with no token supplied | Statically confirmed (F13); the row count is runtime | A probe test with `Client(enforce_csrf_checks=True)`, two `GET`s, counting `LoginToken.objects.count()` | **10** |
| **U7** | `GET /moderation/api/v1/bulk-action/` returns **405** for an ADMIN, and 401 / 403 for anonymous / seller | The `422` claim is **refuted by reading the decorator** (F14); the 401/403/405 values themselves are report runtime | A probe test over the route with 5 identities × 2 methods | **3** |
| **U8** | `AdAdmin`'s form is the **only** place an ad can change owner (`user` is editable) | Statically plausible (`AdAdmin.readonly_fields` omits `user`); the **negative** claim ("only") needs a census | Introspect `AdAdmin.get_form(request).base_fields` for `user`, and search the whole tree for any other `Ad` write path that sets `user_id` | **2** — this is the transfer vector that makes the window real |
| **U9** | `ban_user_for_ad` leaves the victim's session key unchanged and the victim can still reach `/dashboard/` (200) | Shape confirmed statically; survival is runtime | `force_login(seller)` → `ban_user_for_ad(ad, moderator_id, reason)` → assert `client.session.session_key` is unchanged and `GET /dashboard/` is 200 | **6** |
| **U10** | The five revocation paths are **4 open, 1 closed** | Re-derived statically; the session-key outcomes are runtime | The U9 probe, extended to all five paths | **6, 12** |
| **U11** | `SESSION_COOKIE_AGE` is never overridden (`1209600` s = 14.0 d), `SESSION_SAVE_EVERY_REQUEST=False`, `SESSION_EXPIRE_AT_BROWSER_CLOSE=False` | Report runtime; no override found statically | `settings.SESSION_COOKIE_AGE` in a shell, or search `config/settings/*.py` for the three names | **6** — the exposure window the gate converts from "14 days" to "one request" |
| **U12** | nginx fronts `location /login/` with `limit_req … burst=20 nodelay`, keyed on `$binary_remote_addr` | Carried from phase 04's validator, **not re-verified in this pass** | Read `docker/nginx/nginx.conf` for the `location /login/` block and the `limit_req_zone` key | **10** — it is one half of why MEDIUM is the right band |
| **U13** | `create_admin_user` sets **both** `is_staff` and `is_superuser` (`AUTHZ-003` option (ii)'s premise) | **NOT VERIFIED** — the command was not found in `apps/users/services/` or in any `apps/*/management/commands/` the code context read | Search for `create_admin_user` across `src/` and `docs/`. **If it does not exist, option (ii) has no enforcement point and option (i) is the only coherent choice** | **9 — Q10, and it decides the option** |
| **U14** | Does anything already expose a Python-level `prometheus_client` counter? | **NOT VERIFIED** — the metrics story today is a `PrometheusBeforeMiddleware` / `PrometheusAfterMiddleware` pair in `MIDDLEWARE`, with **no client wired into any Python module** | Search for `Counter(`, `Gauge(`, `prometheus_client` under `src/`. AUTHZ-009's counter **must reuse an existing convention if one exists** | **8 — and if none exists, the counter is gated to phase 12's monitoring-stack decision** |

#### 0.2.5 Four report errors that would make a naive plan wrong

Recorded as **evidence-basis corrections**. The findings survive all four; the *citations* do not.
**The tree is the authority in every case.**

| # | What the report says | What the tree says | Verdict and consequence |
|---|---|---|---|
| **C-1** | `AUTHZ-004`'s rollout row requires `apps/users/tests/test_login_issue_template.py` and `apps/core/tests/test_login_issue_template.py` to stay green | **`apps/users/tests/test_login_issue_template.py` does not exist** (re-confirmed by this Planner: a whole-tree search finds exactly one file of that name, and it is the `apps/core` one). The real blast radius is **4 files / 10 call sites**: `apps/users/tests/test_login.py::TestLoginIssue` (5 tests) **plus 2 more `client.get("/login/issue/")` calls inside the `login_status` tests**, `apps/ads/tests/test_auth_nav.py::test_login_issue_renders_header`, and `apps/core/tests/test_contact_rate_limit.py::test_login_issue_returns_429_when_rate_limited`. The `apps/core` template test reads `users/login_issue.html` **as text** and never issues a request | **Any plan that budgets "re-run the two `test_login_issue_template.py` files" is under-scoped by four files and will go red.** BLOCK 10 names all four. The `apps/core` test's three assertions (`{% telegram_deep_link %}` present, no cleartext bot username, deep-link button not hidden on load) **must also survive** BLOCK 10's new form |
| **C-2** | The bot's publish gate is `AccountStateMiddleware._check_publish_permission` (`telegram_bot/middlewares/permissions.py`) | The method is **`_evaluate_publish_permission`**; its sibling is **`_evaluate_user_state`**. `_check_publish_permission` does not exist anywhere. `_check_user_state` still exists but is a **test-facing convenience wrapper** that `__call__` does not use, and its single-positional-argument signature is **documented load-bearing** and pinned by bot tests | **BLOCK 5 targets the real names.** Targeting the report's name produces an `AttributeError` — or, worse, a **silent no-op refactor** that leaves two vocabularies in place and reports success |
| **C-3** | `AUTHZ-008` breaks **four assertions** in two files that pin `WWW-Authenticate == "Bearer"` | It breaks **five test methods**, and **two of them pin the ordering by name**: `test_decorators.py::TestStaffRequiredApi::test_unauthenticated_get_returns_401` (*"authn check precedes method check"*) and `test_non_staff_get_checks_staff_first` (*"the 403 staff check precedes the 405 method check"*) | **Reordering breaks those two by assertion *and* by name.** Per constraint 2 the **assertions** change, not the code — and the change lands **in BLOCK 3's own commit**, or the phase looks red |
| **C-4** | *(not in the report)* — the plans do not record this | `docs/01-spec/technical-specification.md` states, verbatim, *"No web-side middleware redirects soft-deleted users; the consent banner `{% include %}` is guarded by `{% if not request.user.is_authenticated or not request.user.is_deleted %}` in all 5 template sites."* | **Shipping `AccountStateGateMiddleware` falsifies that sentence on the day it lands**, and **phase 06 holds the file** (`PII-113`; phase 06 BLOCKS 4/11/14). **Phase 15 must request the edit or ship a documented divergence — it may not edit the file unilaterally.** BLOCK 6 records the request; BLOCK 12 routes it. **This is new information: no earlier plan records it** |

### 0.3 Scope statement (explicit)

**What this plan is.** The remediation of nine `AUTHZ-` findings, five `VAL-` items, and two
questions that phase 10 explicitly routed to phase 15, decomposed into **12 independently
committable blocks** with a stated safe serial order, per-block risk, per-block agent roster, and a
**labelled decision gate wherever technical or product uncertainty exists**.

**What this plan owns, exclusively:**

| # | Owned artefact / decision | Block |
|---|---|---|
| 1 | **The per-request web account-state gate** — the middleware itself, its placement, its DENY set, its deny response | **6** |
| 2 | **The shared account-state declaration and its shape** — the two-level predicate (per-request verdict + queryset-composable terms) and the flag vocabulary both processes read | **5** |
| 3 | **The publish-gate policy** (`can_publish_ad` / the bot's publish check) | **5, 7** |
| 4 | **The `submit_ad` ownership guard** and the `edit.py` actor id that makes it meaningful | **4** |
| 5 | **`ad_edit`'s ownership assertion on the locked row** | **2** |
| 6 | **One role resolver, one moderator contract, the `AdminSite.has_permission` reconciliation** | **9** |
| 7 | **`staff_required_api`'s method ordering and its `WWW-Authenticate` challenge** | **3** |
| 8 | **The denial-instrumentation helper and the stable reason-code vocabulary** | **6, 8** |
| 9 | **`/login/issue/`'s method and CSRF protection** | **10** |
| 10 | **The moderation-surface method/`reason_category` decisions phase 10 routed here** | **11** |
| 11 | **The documentation parity this phase causes, and the tracker-key convention** | **12** |

**What this plan explicitly does not own, and where each item is routed** — the full list is §6;
the four that most constrain the blocks are:

- **The `logout()` calls on the four open revocation paths.** → **phase 04 BLOCK 6**. Phase 15
  records that three of the four are **structurally unreachable at the view layer**
  (`ban_user_for_ad(ad, moderator_id, reason)` and `bulk_ban_users(queryset, moderator_id, reason)`
  take **no `request`**, and `bulk_ban_users` never materialises a `User` at all), which is exactly
  why the *gate* is the only mechanism that can revoke them. **Phase 15 does not re-file
  `04-AUT-002` and does not implement one `logout()` call.**
- **The `UserAdmin` field contract** (no `fields` / `fieldsets` / `form`; `password` as a plain
  `CharField`; `is_superuser` and `user_permissions` self-editable). → **phase 04 BLOCK 1**, with
  `PII-103` merged into it. Phase 15 **cites** it as a hard prerequisite of BLOCK 9 and **must not
  close `AUTHZ-003` without it**.
- **The ad-visibility predicate and the audience predicate.** → **phases 05/08 and 06**. Phase 15
  owns the **framework** (the terms are expressible) and **zero** predicate semantics. No queryset
  in `apps/ads/services/listings_query.py` or `apps/search/services/alert_query.py` is touched.
- **The `technical-specification.md` DECLINE sentence and the "no web-side middleware" sentence.**
  → **phase 06** (`PII-113`, `06-VAL-003`; phase 06 BLOCKS 2/4/11/14). Phase 15 **requests**.

**What this plan ships and does not ship.** Ships **no migration**, **no `AdvisoryLockId`**, **no
model field**, **no env key**, **no new pytest dependency**, **no `testpaths` change**, and **no
edit to `src/backend/conftest.py`**. It adds **at most one** new `StrEnum` to `apps/core/enums.py`
(BLOCK 6's denial-reason vocabulary) and **one** new package (`apps/users/middlewares/`, BLOCK 6).
**Every block that appears to need one of these is a signal that it has drifted into §6.**

### 0.4 Severity corrections

The validated report's bands are **upheld**, with four corrections recorded. Where a re-band is
available, it is **not taken silently** and it **does not propagate** to another phase's record.

| ID | Report band | This plan's position | Why |
|---|---|---|---|
| `AUTHZ-001` | HIGH | **HIGH, unchanged** | Taxonomy-mandated and reproduced end-to-end through the real `ban_user_for_ad` path. **And the revocation-path count is corrected once more: there are five account-state-changing paths of which **four** are open, not "three of the four".** `consent_withdraw` is the only closed one; self-service **`consent_decline`**, `UserAdmin.withdraw_consent_action`, `ban_user_for_ad` and `bulk_ban_users` are open. Phase 04's own headline says "3 of 4" while its evidence table lists five rows with one closed — **the code is the tie-breaker, and this plan does not regress to "3 of 4"** |
| `AUTHZ-002` | HIGH | **HIGH, unchanged, and explicitly labelled unreachable** | The taxonomy's HIGH band ("no ownership check on one resource type, even if never exploited in testing") describes this almost verbatim, so the band is handbook-mandated and not overridden. **But operational risk today is zero**: all three call sites are internally consistent. The finding is a **latent** defect that becomes an exploit the first time a fourth caller appears. **The acceptance test is "the row is unchanged", never "the call returned `True`"** — the return value is content-dependent, because `auto_moderate` runs inside the same transaction |
| `AUTHZ-003` | HIGH | **HIGH, held on taxonomy grounds — and the band is explicitly contested** | The impact is materially reduced (the role **is** self-provisionable, §0.2.5-adjacent F9/U4), while a *different* escalation is owned by `04-AUT-005`. The report's own note is that banding on the **residual** gives MEDIUM, with the **combined** `AUTHZ-003 + 04-AUT-005` pair at HIGH. **This Planner does not make that call: it is GATE Q9, a coordinator ruling, non-blocking for the code.** The hard rule is that **a re-band must not silently drop the escalation** |
| `AUTHZ-005` | MEDIUM, reclassified **SPEC-DEVIATION** | **MEDIUM, unchanged; the *type* is itself gated** | Reclassification is well founded — the spec references the behaviour, so it is a missing integration, not dead code. **But its type rests on the contested DECLINE sentence** (`spec-index.md` "blocks seller **login only**" vs `technical-specification.md` "blocks seller login/**actions**"), which is **phase 06 `PII-113`'s** to resolve. **GATE Q4 + GATE Q5** |
| `AUTHZ-006` | MEDIUM | **MEDIUM, and the impact statement is corrected downward** | There is **no current exploit**: `AdminSite.has_permission` is Django's and **nothing in this project overrides it**, so anon and seller are stopped at the site level. This is a **defence-in-depth defect**. The block's commit body must say so, and must **not** imply a live anonymous-delete capability |
| `AUTHZ-007` | MEDIUM | **MEDIUM, unchanged** | Distinct root cause from `AUTHZ-002` — **caller scope vs service scope**. They compose and are ordered (`2 → 4`), but **merging them would hide one behind the other's diff** |
| `AUTHZ-008` | LOW | **LOW, unchanged — and one sub-claim is deleted** | The `422`-instead-of-`405` consequence is **refuted**: the decorator's third branch is a `return`, so the view body is never entered on a non-`POST`. **Delete the `422` claim and the `staff_required_api(ADMIN, GET) -> OK` probe line from the tracker.** What survives is a diagnostic-status consistency improvement plus a factually wrong `WWW-Authenticate: Bearer` challenge |
| `AUTHZ-009` | LOW | **LOW, unchanged** | Matches the handbook's LOW band verbatim. The sharpest evidence is a **defined-and-never-called** module-level `logger` |

**Three corrections to the *report's own arithmetic*, restated because a naive tracker will repeat
them:** (a) `AUTHZ-003`'s "15 of 17 declare no permission override" is incoherent — the correct
statement is **3 override `has_view_permission` / 14 fall back to per-model perms / 3 declare none**;
(b) the "no provisioning mechanism anywhere / not deployable" sub-claim is **refuted** by a live
self-grant; (c) the field counts **25 / 29** are stale — the real counts are **unmeasured** and must
be measured (U5), not quoted.

### 0.5 Open technical questions — resolved here, or explicitly gated in their block

**This Planner closes nothing that has technical uncertainty in it.** Every question below ends in
exactly one of three dispositions: **`RULED`** (a Planner ruling, with the alternatives and their
consequences recorded — used only where the choice is a preference, not an unknown fact),
**`GATED`** (a labelled *decision required before implementation* gate with options and
consequences, written into the block), or **`ROUTED`** (owned elsewhere; recorded, not re-filed).
**An Implementor is forbidden from choosing an option on any `GATED` question.**

| # | Question | Blocks | Owner | Disposition here |
|---|---|---|---|---|
| **Q1** | **Is `is_active` a kill-switch or dead?** The report's own matrix says `is_active=False` **already** yields a 302 on the web, which would refute `04-AUT-004`'s premise for that tier. `AUTHZ-001`'s DENY set deliberately carves it out. **Both phases' reports cannot both be right, and neither plan has landed** | 6 | phase 04 (Q3/Q4) + phase 15 (vocabulary) | **`GATED` — GATE Q1**, inside BLOCK 6, and it is a **hard gate**: it requires U1 to be re-derived first. **A silent ship here is how a control is added in one phase and removed in the next** |
| **Q2** | **Does the shared predicate expose queryset-level terms from one declaration?** (a) two levels from one source — per-request verdict + named `User` flag terms; (b) instance-level only | 5 (and transitively `06-VAL-003` and `SRCH-004`) | phase 15 (shape); phase 06 + phase 08 (semantics) | **`RULED` — R1: option (a), two levels from one declaration.** There is no unresolved *technical* uncertainty here: option (b) is precisely the defect one module over — `get_account_state()` is instance-level, so no queryset filter can call it, which is why `06-VAL-003` and `SRCH-004` have been blocked for **two** phases and would be blocked for a fourth. **Consequence recorded: phase 15 owns the *shape* and the *terms*; phase 06 owns the `User` audience predicate's semantics, phase 08 owns the `Ad` ad-visibility predicate's semantics, and neither may be inferred from phase 15's declaration.** If a Reader wants (b), the cost is recorded in §4.3 |
| **Q3** | **What may `is_staff` do?** Does a plain moderator get write access to the moderation criteria, the audit log, and the support desk? Today the answer is "no, and there is no documented reason" | 9 | **owner / product** | **`GATED` — GATE Q3**, inside BLOCK 9. **Both candidate fixes are privilege *expansions*** — the *correct* one grants moderators more, the *proposed* one grants write to seven read-only models. It needs an explicit review of the 17-model matrix, **not a rubber stamp** |
| **Q3′** | **Which route reconciles `AdminSite.has_permission` with `User.role`?** (i) override it to `is_active and role == ADMIN`; (ii) declare that a superuser is *always* `is_staff` and enforce it at provisioning | 9 | phase 15 + owner | **`GATED` — GATE Q3′**, inside BLOCK 9, and it **cannot be answered before U13**. If `create_admin_user` does not exist or does not set both, option (ii) has **no enforcement point** and only (i) is coherent |
| **Q4** | **Is `PII-105` option (a) taken** — DECLINE becomes reversible and web login is regained? | 7 (hard sequencing) | **phase 06** | **`GATED` — GATE Q4**, inside BLOCK 7. If (a), the publish gate becomes the **only** control keeping a declined seller from posting, so AUTHZ-005's missing `is_declined` term becomes *the whole control*. **BLOCK 7 does not start until the ruling is written down** |
| **Q5** | **Which line governs DECLINE semantics?** `spec-index.md:74` ("blocks seller **login only**") vs `technical-specification.md:101` ("blocks seller login/**actions** AND hides the user's PUBLISHED ads") | 7 (the finding's *type*) | **phase 06 · `PII-113`** | **`GATED` — GATE Q5**, inside BLOCK 7. Both sentences exist in the tree today |
| **Q6** | **Should a banned seller's ads stay publicly visible?** | — | **product owner** | **`ROUTED` — not phase 15's, and it gates nothing here.** Open across **three** phases (08, 06, 15). Phase 08 folded `SRCH-008` into `SRCH-004` deliberately so it is argued as **one product decision**. **No amount of work in phase 15 settles it.** The recommended next step is the one-paragraph trade-off in front of the product owner, not a fourth filing. **Phase 15 files nothing about it** |
| **Q7** | **`VAL-001`'s CSRF ruling** — is a state-changing `GET` CRITICAL or MEDIUM? The handbook's §8 and §5(h) contradict each other | 10 (the **band** only) | **the audit programme, not phase 15** | **`GATED` — GATE Q7, non-blocking for the code and blocking for the tracker.** The remedy (`@require_POST` + CSRF) is correct under either reading; only the severity is in question. **The ruling must be made once, centrally, and applied to every phase that finds a state-changing `GET` — it must not be decided locally.** Phase 15 records the recommended amendment verbatim (§3, BLOCK 10) and does not apply it |
| **Q8** | **The deep-link UX decision**: a `GET` deep link from a bookmark, a messenger or a headless client must degrade gracefully once the route becomes POST-only | 10 | **owner / product** | **`GATED` — GATE Q8**, inside BLOCK 10. Phase 04's plan names this as the reason phase 04 **may not** add `@require_POST`; phase 15 may, **but only with the UX decided** |
| **Q9** | **Is `AUTHZ-003` banded on the finding or on the residual?** | 9 (the **tracker** only) | **coordinator** | **`GATED` — GATE Q9, non-blocking for the code.** This Planner records both bands and the combined-pair band and **does not choose**. The hard rule travels with the gate: **a re-band must not silently drop the escalation** |
| **Q10** | **Does `create_admin_user` exist, and does it set both `is_staff` and `is_superuser`?** | 9 | phase 15 (verify) | **`RULED` — R2: it is a verification step, not a decision.** U13's search runs inside BLOCK 9's pre-block step and its result is written into the gate. **A block that cannot find it must say so in the gate answer** rather than assume the premise |
| **Q11** | **What does an invalid `reason_category` do in `reject_ad`?** Today *any* client string is concatenated into `ModeratorActionLog.reason` | 11 | **routed by phase 10 to phase 15** | **`GATED` — GATE Q11**, inside BLOCK 11. **Not in the validated report.** If the gate is declined or unanswered, **BLOCK 11 ships nothing and that is a legitimate outcome** |
| **Q12** | **Is a `GET` on `reject_ad` / `ban_user` a 302 (today) or a 405?** Two shipped tests assert 302; the sibling `approve_ad` already returns 405 | 11 | **routed by phase 10 to phase 15** | **`GATED` — GATE Q12**, inside BLOCK 11. **Not in the validated report.** A 302→405 change is **user-visible** and breaks recorded behaviour — see BLOCK 11's alternatives table |
| **Q13** | **Does the `technical-specification.md` sentence *"No web-side middleware redirects soft-deleted users"* get edited, or does the doc diverge?** | 6 (doc impact), 12 (routing) | **phase 06 holds the reservation**; phase 15 must **request** | **`ROUTED`, with a hard rule in BLOCK 6: phase 15 records the request and does not edit the file.** A documented divergence is an acceptable outcome; a unilateral edit is not |
| **Q14** | **Where does the denial-reason `StrEnum` live, and does phase 15 allocate in `apps/core/enums.py`?** | 6, 8 | phase 15 + coordinator | **`RULED` — R3: one new `StrEnum` appended to `apps/core/enums.py`; nothing is reordered and no `AdvisoryLockId` is allocated.** `enums.py` is **five-way contended** (phases 02/03/05/06/07), and phase 10 follows the same discipline. R3's precondition is an **immediate re-read**: if the file is under concurrent edit when BLOCK 6 starts, BLOCK 6 **stops and reports** rather than reordering another phase's work |
| **Q15** | **What response shape does the new gate return — 403, or a redirect?** The report says "`logout(request)` plus a 403/redirect on deny" **without choosing** | 6 | phase 15 (Planner) | **`GATED` — GATE Q15**, inside BLOCK 6, with the three options and their rollout consequences in BLOCK 6's alternatives table. **A 403 on every `/dashboard/` request after a moderator's bulk ban reads as a site-wide breakage in the first 24 hours**, and the report itself calls this the phase's highest rollout risk |

**Fifteen questions. Three are `RULED` (Q2, Q10, Q14) and each ruling carries its alternatives and
consequences in the row above. Nine are `GATED` inside their block. Two are `ROUTED` out (Q6, Q13).
Not one of them is left as an undecided choice presented as settled.**

---

## 1. Environment and command contract for the implementor

**This environment is Windows 11 / PowerShell 7.** `make` requires WSL or GNU Make; use
`.\Makefile.ps1 <target>`. `head` / `tail` are unavailable in PowerShell.

### 1.1 Tests are Docker-only — `uv run pytest` on the host always fails

There is no PostgreSQL on `localhost:5432`. Every test run goes through the `test` service of the
`mko-bazuna-test` Compose project. `docker/entrypoint-test.sh` performs **no** database setup:
pytest-django provisions `test_mko_bazuna`, and the session-autouse fixture in
`src/backend/conftest.py` restores reference data under advisory lock `111`.

```powershell
# Alias, copied once per session
$dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'

# Start the DB if it is not already up
docker ps --filter "name=mko-bazuna-test-db-"
$dc up -d db

# Fast gate (skips the nightly `seed` suite) - the default iteration command
$dc run --rm --env PYTEST_SKIP_MARKERS=seed test

# Targeted run
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="-k test_name" test
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/moderation/tests/test_decorators.py --tb=short" test

# Full suite (only when a change touches seeding or images - no block in this plan does)
$dc run --rm test
```

**Five caveats that will silently produce a wrong result if ignored:**

- `--env-file .env.test` is **required**; without it compose aborts on `${POSTGRES_*?}`
  interpolation. **Never** substitute the `mko-bazuna-dev` project name.
- Setting `PYTEST_OPTS` **replaces** the defaults
  (`--reuse-db --tb=short --durations=10 -n auto --maxprocesses=4 --dist loadgroup`), so a targeted
  run loses xdist parallelism and DB reuse. `PYTEST_OPTS` is also **unquoted** in
  `docker/entrypoint-test.sh`, so each token is word-split on spaces: `-k test_name` and bare
  paths work, quoted multi-token values do **not**. **Never** use
  `--override-ini=addopts=` — it strips `--import-mode=importlib`, which `pyproject.toml` requires.
- **Never run `uv run pytest` on the host.** That is the documented way to get a green gate that
  tested nothing.
- **Concurrent runs collide on the single `test_mko_bazuna` database.** If a gate goes red while
  another phase agent is running, **re-run it serially** before reporting it as a defect. Teardown
  races surface as `FATAL: database "test_mko_bazuna" does not exist` and
  `relation "..." does not exist`, not as product failures. **This phase has eleven of twelve blocks
  touching the ad, user or moderation surfaces, so the collision probability is high.**
- **The U1/U4/U5/U6/U7/U8/U9/U10 probes of §0.2.4 need a database.** Run them **serially**, never
  alongside another agent's gate.

Prefer `.\Makefile.ps1 up | test | test-all | test-recreate | test-down` — they manage the project
name and env file for you.

**The bot suite is a different target, and BLOCK 5 and BLOCK 7 need it.**
`src/telegram_bot/tests/conftest.py` **redefines** `seller` / `user` (async), so a bot test **cannot
import the backend conftest**. Run it by path:

```powershell
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/telegram_bot/tests/test_account_state_middleware.py --tb=short" test
```

**Lint and typecheck, per the block's own files only:**

```powershell
uv run ruff check <path>          # auto-fix: uv run ruff check --fix <path>
uv run basedpyright <path>
```

### 1.2 The two rules that are specific to *this* phase

1. **Security fixes must fail closed by default, and must not depend on a default-manager filter.**
   Restated from §0.2.2 constraint 1 because it is the constraint an Implementor is most likely to
   violate by accident, in three specific ways:
   - **Do not add a `default_manager` filter to `User` or any app** to make the gate "work". It
     would hide withdrawn users from `AccountStateMiddleware._resolve_user`, which resolves on
     `chat_id` *precisely because* withdrawn users have `telegram_id` nulled. **The gate is a
     request-time decision, not a queryset shape.**
   - **Do not fold `user__is_declined=False` (currently at `apps/ads/services/listings_query.py`'s
     `build_queryset`) into the gate.** Session term and listing term are two predicates and stay two.
   - **A new permission answer defaults to `False`.** `has_*_permission` returning `True` without
     consulting `request` is the exact shape of `AUTHZ-006` and must never be introduced again.
2. **Never use a line number as a task target, in any form.** Every target in every block's task
   YAML is a file plus a **semantic** anchor: a class, a method, a module-level constant, a
   settings key, a route name, a model field, a `StrEnum` member, a test class or method name, a
   decorator. This is a phase with unusually deep stale-citation risk (C-1, C-2, C-3) and line
   numbers would silently re-import it.

### 1.3 Git contract — one Implementor, sequential, one commit per block

- **One Implementor at a time.** Never two. Never a background implementor. If a block is stopped
  mid-way, **resume the existing session**; do not launch a new agent.
- Each block is committed separately, explicitly staged: `git add <specific files>` — never
  `git add -A`, never `git add .`.
- Message form, matching the repo style: `"{type}({scope}): {description}"`, e.g.
  `fix(analytics): make the metrics delete grant consult the request (AUTHZ-006 validated 2026-09)`,
  `feat(users): one account-state declaration read by both processes (AUTHZ-001 + AUTHZ-005 validated 2026-09)`.
  **Every citation uses the §0.1 convention.**
- **Never** `git reset`, `git checkout`, `git restore`, `git stash`, `--amend`, `--no-verify`, or any
  other history mutation. Never force-push. **Never revert a file another agent changed** — other
  agents work in parallel, and files you did not change appearing in `git status` is normal.
- If a file you are about to edit already has uncommitted changes from another agent, **stop and
  report it** rather than clobbering it. This is the normal case for `config/settings/base.py`,
  `apps/core/enums.py`, `apps/ads/views/edit.py`, `apps/ads/services/submission.py`,
  `apps/users/views/consent.py`, `apps/users/admin.py` and `src/backend/conftest.py`.
- **Take your own `git rev-parse --short HEAD`** before BLOCK 1. This plan is anchored at `ba23277`
  and the anchor has drifted seven times.
- Do not commit unless the block's instructions say to.

### 1.4 Standing project rules (restated for every block)

- **English only** — comments, logs, docstrings, error messages, documentation.
- **No `print()`.** `logger = logging.getLogger(__name__)` with lazy `%s` formatting. This matters
  most in BLOCK 8, the only block that adds logging as its subject, and in BLOCK 6, whose new
  middleware is the one place this phase will want to print a state.
- Stack: **Python 3.14 · Django 5.2 LTS (`>=5.2.16,<6.0`) · PostgreSQL 18 · aiogram 3.x · native
  PostgreSQL FTS.** **Two processes, one DB:** web (gunicorn sync WSGI, HTMX MPA) and bot (aiogram,
  `django.setup()` + shared ORM). **Migrations run exactly once** before both start — a migration
  that must run in only one process is a defect. **This plan ships no migration.**
- **Django ORM is the persistence layer.** **Pydantic v2 only at system boundaries** (bot input,
  settings schemas, DTOs at a request edge). Business logic lives in `services/`. **This plan adds
  no DTO and no model.** `AccountState` is a `NamedTuple` today; BLOCK 5 must not convert it to
  Pydantic — the rule puts Pydantic at boundaries, and this is internal domain logic.
- **All schema changes via Django migrations.** **This plan ships none.**
- **Fixed values via `StrEnum` / `Enum`** (project rule 10) — never plain strings, dicts or lists.
  In-repo precedent: `AdStatus`, `AdSort`, `UserRole`, `AdvisoryLockId`, `LanguageLocale`. **This
  plan adds exactly one `StrEnum` (R3, BLOCK 6's denial-reason vocabulary).**
- **i18n is part of DoD.** Wrap every user-visible string in `{% trans %}` / `{% blocktrans %}` or
  `gettext` / `gettext_lazy`; `msgstr` must be **non-empty** for `ru` and `bs` (`en` may be empty —
  the msgid is English). The gate is `apps/core/tests/test_i18n_completeness.py`. **`LOCALE_PATHS`
  is `[BASE_DIR / "backend" / "locale"]` — one catalogue serves web and bot, shared with phases
  03/05/06/07/10/11/14. Append; never regenerate wholesale. No `makemessages` regeneration in this
  plan.** BLOCK 6 (if the gate renders a user-visible denial) and BLOCK 10 (the new POST form's
  submit control) are the two blocks that may add a string; both are named in §3.
- **Small, focused modules and functions. Composition over inheritance. Follow existing patterns.
  No new abstraction without strong justification. No scope creep.**
- **Production code is king** — the six pre-authorised test changes are listed in §0.2.2 constraint
  2. Each must **invoke rule 2 by name** in its commit body.
- **Docs must stay in sync.** `docs/00-overview/doc-maintenance-rules.md` is the governing file.
  BLOCK 9 writes the moderator contract decision record; BLOCK 12 owns the documentation parity this
  phase causes. **BLOCK 12 runs last, for the same reason phase 12's and phase 13's do: documentation
  describing a system the phase has not finished changing is an encoded lie.**
- **Secret handling is governed by phase 02** (`ALLOWED_ENV_VARS`, `test_env_allowlist.py`).
  **This plan adds no env key**; `IMMEDIATE_ALERTS_ENABLED` stays `False` (F19).
- **Do not edit `src/backend/conftest.py`.** If a block appears to need a fixture, that is a signal
  the test is over-fitted — and **seven other plans forbid it and one claims it**.
- **Do not start, stop or modify any container or compose stack** except through §1.1's commands.
  Never `docker compose down -v`.

### 1.5 Test authoring standard for every block

Tests verify **logic and component interaction**, not implementation trivia. No test asserts a line
number, an introspection column count, a literal private name, a template-string substring, or the
mere presence of a symbol. Assert on **observable behaviour** and on the **absence of danger**.

**The phase-specific rule — inherited from `VAL-003` and from code context §6.3, and it is the most
important sentence in this section: a `getsource` test cannot see a defect expressed as an
absence.** `AUTHZ-005` (the absence of a production caller for `can_publish_ad`), `04-AUT-005` /
`PII-103` (the absence of `fields` / `fieldsets` on `UserAdmin`) and `AD-001` (`status` missing from
`AdAdmin.readonly_fields`) are **all** invisible to source text. Three separate auditors have now
been misled by source-reading this surface, and a fourth was misled by reading `has_view_permission`
in isolation instead of the `has_view_or_change_permission` disjunction the changelist actually
calls. **Therefore: any phase-15 regression test for `AUTHZ-003`, `AUTHZ-005` or `AUTHZ-006` must go
through `admin.site._registry`, `ModelAdmin.get_form`, or an actual call — never through source
text.**

| Instead of | Assert |
|---|---|
| `assert "Bearer" in source` | the 401 response's `WWW-Authenticate` header is the value the contract states, and the 405 path is reached for an authenticated non-`POST` |
| `assert source.count("select_for_update") == 1` (as a *new* test) | the non-owner POST is refused **and** the row is byte-identical, **and** the DB-003 row lock is still taken (the existing source test stays as a tripwire; it is not duplicated) |
| a comment saying "the reason code is emitted" | a denied request emits **exactly one** log record containing the stable reason code and the actor id, and a `caplog` assertion proves both the presence and the uniqueness |
| `len(admin.site._registry) == 17` | the **contract**: for every registered `ModelAdmin`, the answer for a plain `is_staff` moderator and for an anonymous user matches the documented moderator contract, and any class that diverges fails the test by name |
| `assert can_publish_ad(user) is True` for a declined user (today's pin) | the publish verdict for a declined user is **denied**, from the bot middleware **and** from the shared predicate, with the reason code named |

**Good targets for this phase:**

- each of `is_banned` / `is_deleted` / `is_declined` / `consent_revoked` ⇒ the session is destroyed
  and the response is the one the gate's answer chose; **and** anonymous and public routes are
  unaffected; **and** a restricted-but-valid seller (`ads_auto_publish=False`) still reaches the
  dashboard;
- the bot's allow/deny answers are **byte-identical before and after** BLOCK 5's extraction — a
  matrix assertion over the four flags plus the contact-deep-link DECLINE exception plus the
  `None` fail-open, on both processes;
- the queryset-level terms are reachable from a real `filter(...)` — a test that composes them into
  a `User` queryset and asserts the row set, so "expressible" is demonstrated rather than asserted;
- `submit_ad` with a mismatched `user_id` leaves the row **byte-identical** — asserted on the row,
  never on the return value; **and** a POST by a non-owner with a valid body is refused **before**
  `submit_ad` is reached;
- `DailyAdMetricsAdmin.has_delete_permission` is `False` for `AnonymousUser` and for a seller and
  `True` for a superuser — three identities, one call, through the registered admin object;
- `staff_required_api` returns 405 for an authenticated non-`POST` **and** 401/403 unchanged for
  the anonymous and seller cases;
- the gate's deny response is the one the gate's answer chose, and a **positive control** shows a
  normal seller's dashboard still renders `200` after the gate is installed.

**Every new guard's `acceptance_criteria` must include "and that failure is demonstrated before the
commit."** A guard that was never observed failing is a comment.

### 1.6 Task shape for every block

Each block's implementor task follows `.ai\tasks\templates\task_template.yaml`: semantic `targets`
with `type` / `name`, `semantic_anchors`, `changes`, `acceptance_criteria`,
`source_reference` / `source_section` / `source_blocks`, and an `extra_context` block carrying the
block's binding constraints **verbatim** — including, for every gated block, the gate's question ID,
its options, and the sentence **"the Implementor is forbidden from choosing an option."**

Verification is **inline** for `mechanical` blocks. A **separate Validator task is required** for
every `behavioural`, `structural` and `conditional` block, and for **all four agents** on the blocks
whose header names all four.

---

## 2. Scope decisions table (acceptance contract for execution)

`mechanical` = no observable behaviour change beyond the intended one, safe to run without a
Validator beyond the block's own tests. `behavioural` = changes an observable response, touches a
shared contract, or breaks a shipped test. `structural` = introduces a contract or a source of
truth. `conditional` = ships a reduced deliverable — or nothing — if its gate is declined.

| ID | Class | Disposition | Block | Severity | One-line reason |
|---|---|---|---|---|---|
| `AUTHZ-001` | **structural** | **implement in two blocks: 5 (the declaration, answers unchanged) then 6 (the web gate).** Two-level shape is RULING R1. Gate the gate on Q1, Q15, and phase 06's doc ruling (Q13) | **5, 6** | **HIGH** | `MIDDLEWARE` has 14 entries and no account-state gate; `can_login` has exactly one production call site; four of five revocation paths leave the live session authorized. ✔ **The DENY set is already implemented and test-pinned on the bot side** — this is an *extraction*, not a new policy, which lowers the design risk and raises the cost of getting the shape wrong once. ✔ **The report's single-commit recommendation is deliberately split here** (§4.2, edge 5→6) because a pure-refactor commit and a user-visible gate commit are independently reviewable and only one of them can be rolled back |
| `AUTHZ-002` | **behavioural** | **implement, both halves, one commit** — `submit_ad` compares the actor on the locked row **and** `edit.py` passes `request.user.id` at both literals | **4** | **HIGH** (taxonomy-mandated; **unreachable today**) | The cross-tenant write is confirmed; the recommended guard is a **tautology for its own web caller** and would give false assurance. ⚠ **The highest-consequence sequencing constraint in the phase: phase 10 BLOCK 16 already pre-commits to `user_id=request.user.id`, so a premature BLOCK 16 makes this guard permanently tautological while looking correct** |
| `AUTHZ-003` | **structural** | **implement the narrow form only — role resolver + `AdminSite` reconciliation + written contract + registry test.** Cite `04-AUT-005` as a hard prerequisite; **must not close without it** | **9** | **HIGH**, band contested (GATE Q9) | Four answers to one question; `media_gate` answers differently from `staff_required` for the same superuser. ✔ **Both candidate fixes are privilege *expansions*** — the correct one grants moderators more, the proposed one grants write to seven deliberately read-only models. **The 17-class `AdminRolePermissionMixin` is a prohibition, not an option** (`VAL-005`) |
| `AUTHZ-004` | **behavioural** | **implement, gated on Q8 (owner) and Q7 (band).** Blast radius is **4 files / 10 call sites** | **10** | **MEDIUM** (GATE Q7) | A `GET` inserts a `LoginToken` with no CSRF token. ✔ **C-1: one of the two test files the report names does not exist.** Amplification is bounded at two layers (in-app rate limits + nginx `limit_req`), and the token expires in 5 minutes and must still be claimed by a Telegram identity — which is why MEDIUM is right. **`LOGIN_URL` points at this route, so every anonymous `@login_required` redirect lands on it** |
| `AUTHZ-005` | **behavioural** | **split: 5 (unify the vocabulary with today's answers preserved) then 7 (change the publish DENY set).** Gated on Q4 + Q5 | **5, 7** | MEDIUM | `can_publish_ad` tests three flags and omits `is_declined` **and** `consent_revoked`; the live bot gate is a second, narrower predicate. ✔ **The finding's *type* (SPEC-DEVIATION) is itself gated on phase 06's DECLINE ruling.** ✔ `can_publish_ad` **must not** be deleted as dead code (phase 10 BLOCK 8 binding constraint 1) |
| `AUTHZ-006` | **mechanical** | **implement — one method plus one regression test. No sweep** | **1** | MEDIUM | A constant `True` that never consults `request`. ✔ **Impact corrected downward: no current exploit**, because `AdminSite.has_permission` is Django's and nothing here overrides it. ✔ **Every** other constant override in the registry returns `False`, so `True` is the only dangerous direction and a blanket sweep would touch 17 classes for one defect |
| `AUTHZ-007` | **behavioural** | **implement — move the ownership assertion inside the lock, copying the in-file precedent** | **2** | MEDIUM | Authorizes on the unlocked read, then re-reads under lock **without re-checking**. ✔ `ad_archive` / `ad_reactivate` / `ad_delete` already implement the fix — **one function, three precedents.** Externally gated on phase 03 BLOCK 5 and phase 05 BLOCKs 2/8 |
| `AUTHZ-008` | **behavioural** | **implement — method check first; correct or drop the `WWW-Authenticate` header; update the five test methods in the same commit** | **3** | LOW | ✔ **C-3: five test methods break, two of which pin the ordering by name.** ✔ **The report's `422` claim is refuted and is deleted from the tracker** — the third branch is a `return`, so the view body is never entered on a non-`POST`. Reordering changes only the diagnostic status for two already-denied cases |
| `AUTHZ-009` | **behavioural** | **implement — one reason-coded denial helper, used by the decorators *and* the ad views.** Counter gated on U14 + phase 12 | **8** (helper + ad views) · **6** (the gate is instrumented day one) | LOW | `decorators.py` defines a `logger` and calls it **zero** times. ✔ Otherwise the phase creates a **third** denial-logging convention alongside the two that already exist. ✔ New denial volume is real: keep it at `WARNING` with a stable reason code |
| `VAL-001` | — | **not a code change here** — a central handbook amendment phase 15 **requests and does not apply** | **10, 12** | Medium (blocks `AUTHZ-004`'s band) | The handbook's §8 CRITICAL entry and §5(h) disagree about state-changing `GET`s. **It must be ruled once, centrally, and applied to every phase that finds one — never decided inside phase 15** |
| `VAL-002` | — | **discharged by BLOCK 9** — the registry iteration replaces the mis-built role matrix | **9** | Medium (evidence quality) | Four admin URLs in the report's Appendix A **do not exist**, and their `404`s are route-resolution failures read as authorization results. ✔ Four models have **no** admin surface at all (`SavedSearch`, `MediaFile`, `SellerTrustScore`, `ExchangeRate`); `/admin/analytics/analytics-event/` is a typo. Whether that is deliberate is **not this phase's question** |
| `VAL-003` | **mechanical** | **measure (U5) in BLOCK 9 and record the measured numbers in BLOCK 12.** No field set is changed by this phase | **9, 12** | Low | The report's `25` / `29` are stale. **Do not take any count on trust from any document** |
| `VAL-004` | — | **rolled into the §0.1 citation convention and BLOCK 12's tracker record** | **12** | Low (tracker hygiene) | Three prefixes for one stream, and one burned set (`AUTZ-003` is a **shipped in-source marker**). ✔ Phase 04, 05 and 08 have all filed the same requirement; this plan consolidates it once rather than restating it per phase |
| `VAL-005` | — | **a prohibition, not a task.** Rejected option, recorded with its evidence | **§6.3, 9** | **High** (blocks implementation as written) | A blanket `AdminRolePermissionMixin` would grant write to seven models that are read-only **by deliberate data-protection policy** — turning an audit trail into a mutable table and a consent record into an editable one. **A strictly larger incident than the one the finding is fixing** |
| **Q11 / Q12** | **conditional** | **implement only if the gates are answered.** Not in the validated report; routed here by phase 10 | **11** | — | An invalid `reason_category` is concatenated into `ModeratorActionLog.reason`; a `GET` on `reject_ad` / `ban_user` is a 302 while the sibling `approve_ad` is a 405. **Declining the gate is a legitimate outcome and BLOCK 11 then ships nothing** |
| **Q1 … Q15** | — | **`GATED`** (Q1, Q3, Q3′, Q4, Q5, Q7, Q8, Q9, Q11, Q12, Q15) · **`RULED`** (Q2 → R1, Q10 → R2, Q14 → R3) · **`ROUTED`** (Q6, Q13) | **1–12, §6** | — | Eleven gates, each with options and consequences written into its block. **Three rulings, each with its alternatives recorded. Two routed out. The Implementor is forbidden from choosing an option on any gate** |

**Block classification summary:** `mechanical` = **1** · `behavioural` = **2, 3, 4, 7, 8, 10** ·
`structural` = **5, 6, 9, 12** · `conditional` = **11**.

---

## 3. Execution blocks

Twelve blocks. **One Implementor, strictly sequential, one commit per block** (§1.3). The numbering
*is* the serial order, and the order answers one question: **what must be true before the next
change can be trusted?**

```
apps/analytics/admin.py            1 only          (cheapest; uncontended; de-risks the rest)
apps/ads/views/edit.py             2, 4           (AUTHZ-007, then AUTHZ-002 — a hard edge)
apps/moderation/views/decorators.py 3 only        (with its five test methods, same commit)
users/services/account_state.py    5, 7           (one declaration, then one policy change)
telegram_bot/middlewares/         5 only          (the bot adopts it first; answers unchanged)
users/middlewares/ (NEW)          6 only          (the gate; MIDDLEWARE; the reason enum)
users/ + moderation/ + ads/        8 only          (one reason-coded denial helper, five call sites)
apps/ads/views/listings.py         9 only          (media_gate on the role; nothing else in that file)
admin site + decision record       9 only          (the contract and its executable form)
apps/users/{urls,views/consent}.py 10 only        (GET -> POST + CSRF; 4 files / 10 call sites)
apps/moderation/views/review.py    11 only         (conditional; phase-10 routed)
docs/                              12 only         (documentation parity; last)
```

**Ten of the twelve blocks carry a labelled *decision required before implementation* gate or an
external gate.** A gated block does not start until the answer is **written down**; **the
Implementor is forbidden from choosing an option** (§1.6, §8.1).

---

### BLOCK 1 — One method, and the deny-by-default rule it establishes (`AUTHZ-006`)

| | |
|---|---|
| **Findings owned** | `AUTHZ-006` (MEDIUM) · the *convention* half of `AUTHZ-001`'s fail-closed constraint (§0.2.2 rule 1) |
| **Class** | **mechanical** — one method, one precedent, no shared file |
| **Depends on** | nothing in-plan, nothing cross-phase. `apps/analytics/admin.py` is claimed by **no other plan** |
| **Blocks** | BLOCK 9 (the registry contract test is where the rule becomes executable) |
| **Priority** | **P0 as the cheapest block.** It is first because it is uncontended, it needs no gate, and it costs one method — which buys the Implementor a green commit before touching any of the six-way files |
| **Risk level** | **LOW.** The only real failure mode is over-scoping into the blanket sweep that §0.2.2 constraint 3 forbids |
| **Blast radius** | `apps/analytics/admin.py::DailyAdMetricsAdmin` and one new/extended test module |
| **Required agents** | **Researcher · Planner · Validator** (Auditor not required: single method, in-repo precedent, statically confirmed at F12) |

**The defect, in full.** `DailyAdMetricsAdmin.has_delete_permission(self, request)` returns a
constant `True` and never touches `request`. Its two siblings on the same class
(`has_add_permission`, `has_change_permission`) both return `False`. The in-repo precedent is one
class above in the same module: `AnalyticsEventAdmin.has_delete_permission` returns `False` with the
docstring *"Events are preserved for metrics."*

**State the impact honestly, because the report does not.** There is **no current exploit**:
`AdminSite.has_permission` is Django's own and **nothing in this project overrides it**, so an
anonymous or seller-identity request is stopped at the site level and returns `302` to the admin
login. This is a **defence-in-depth defect**, which is exactly what MEDIUM means. **The commit body
must say so and must not imply a live anonymous-delete capability.**

**Alternatives for the guard's shape, with trade-offs — GATE-free, because this one is a preference
and the Planner rules it:**

| Option | Shape | Maintains | Future evolution | Project convention | Consequence if wrong |
|---|---|---|---|---|---|
| **(a) — RULING** | `return bool(request.user.is_superuser and request.user.is_active and request.user.role == UserRole.ADMIN)` | Mirrors how `UserAdmin.has_add_permission` / `has_delete_permission` already express "superuser only", so a superuser who relied on the accidental grant keeps it | **Good** — the shape reads as a *policy*, not a constant, so the next class that needs it copies a precedent | ✔ matches `UserAdmin`; ✔ reuses `User.role` rather than inlining a fifth ADMIN answer (F6) | If a future moderator contract grants moderators delete on metrics, this method becomes the one outlier and must be revisited — which is a **visible** outlier, not a silent one |
| (b) | `return False` unconditionally | Simplest possible; matches `AnalyticsEventAdmin` | **Poor** — it removes a capability a superuser currently has, which is a behaviour change nobody asked for | ✔ matches the sibling exactly | **A superuser loses a working action.** That is a behaviour change disguised as a security fix, and it is the kind of thing §0.2.2 rule 1 forbids |
| (c) | Sweep **every** constant-returning `has_*_permission` override across the 17 classes into a single base class | Uniform | Uniformity is the *illusion* — the overrides encode **different** per-model policies | ✘ **violates composition over inheritance and "no abstraction without justification"** | **Rejected: 17 classes for one defect.** And the base class is the shape of the `VAL-005` privilege expansion, one app away |

**Binding constraints**

1. **One method. One class. No sweep.** Every other constant override in the registry returns
   `False`, and `False` is always safe. `True` is the only dangerous direction and this is the only
   instance of it. **Touching the other 16 classes is out of scope and is a review finding.**
2. **Deny by default.** If the check cannot be evaluated (no `request`, anonymous, a non-`User`
   object), the answer is `False`. There is no branch that returns `True` without having consulted
   `request` (§0.2.2 rule 1).
3. **Use `User.role`, not a fifth inlined expression.** `request.user.is_staff or
   request.user.is_superuser` written inline here would be exactly the divergence `AUTHZ-003` is
   about. **This is the one place this phase may reference `User.role` before BLOCK 9** — and it is
   permitted precisely because it *reduces* divergence rather than adding a fifth answer.
4. **No migration, no model field, no admin field change, no new test fixture.** The regression
   test uses `admin.site._registry` to reach the registered object — not a source inspection.
5. **The regression test goes through the registry, not the source text** (§1.5). It must call
   `has_delete_permission` with an `AnonymousUser`, with a seller, and with a superuser, and assert
   `False / False / True`. A test that reads the method's source cannot see a defect expressed as a
   return value.

**Implementor task**

```yaml
id: task_15_b01_daily_metrics_delete_grant
title: "Make DailyAdMetricsAdmin.has_delete_permission consult the request, with the deny-by-default rule (AUTHZ-006 validated 2026-09)"
priority: medium
depends_on: []
source_reference: ".ai/plans/15-authorization-remediation.md"
source_section: "BLOCK 1 - One method, and the deny-by-default rule it establishes"
source_blocks: ["BLOCK 1"]
description: >
  DailyAdMetricsAdmin.has_delete_permission returns a constant True and never touches request, so a
  grant that should be policy-derived is actually a constant. Make it consult request, deny by
  default, and express the "superuser only" answer through User.role rather than a fifth inlined
  ADMIN expression. Impact is defence-in-depth with no current exploit, because AdminSite.has_permission
  is Django's own and nothing in this project overrides it - the commit body must say so and must not
  imply a live anonymous-delete capability. Do not sweep the other 16 ModelAdmin classes: every other
  constant override in the registry returns False, False is always safe, and True is the only
  dangerous direction.
goals:
  - "has_delete_permission consults request and returns False for AnonymousUser and for a seller"
  - "a superuser still receives True, so the accidental grant a superuser relies on is preserved"
  - "the answer is expressed via User.role, not an inlined is_staff-or-is_superuser expression"
  - "the regression test reaches the method through admin.site._registry, not through source text"
extra_context: |
  BINDING CONSTRAINTS
  1. One method, one class, no sweep. Touching the other 16 registered ModelAdmin classes is out of
     scope and is a review finding.
  2. Deny by default. No branch may return True without having consulted request; an unevaluable
     check returns False.
  3. Use User.role. Writing "is_staff or is_superuser" inline here would add a fifth answer to the
     ADMIN question and is the exact divergence AUTHZ-003 is about.
  4. No migration, no model field, no admin field change, no fixture added to src/backend/conftest.py.
  5. The regression test must go through admin.site._registry and an actual call. A source-inspection
     test cannot see a defect expressed as a return value (code context 6.3, VAL-003).
  HONESTY REQUIREMENT: the commit body must describe this as defence-in-depth with no current
  exploit. Do not write "anonymous users can delete analytics rows".
  CITATION: "AUTHZ-006 (validated 2026-09)".
files:
  - path: src/backend/apps/analytics/admin.py
    targets:
      - type: class
        name: DailyAdMetricsAdmin
      - type: method
        name: has_delete_permission
    changes:
      - "Consult request; deny by default; express the superuser-only answer through User.role."
  - path: src/backend/apps/analytics/tests/test_analytics_admin_permissions.py
    targets:
      - type: module
        name: test_analytics_admin_permissions
    changes:
      - "Three identities through the registered admin object: AnonymousUser, seller, superuser."
changes:
  - action: modify_code
    description: >
      Replace the constant return with a request-consulting, deny-by-default answer mirroring
      UserAdmin.has_add_permission and AnalyticsEventAdmin.has_delete_permission.
  - action: add_code
    description: >
      Add the regression test that resolves the ModelAdmin instance from admin.site._registry and
      calls has_delete_permission with three identities, asserting False / False / True.
acceptance_criteria:
  - "has_delete_permission is False for AnonymousUser and for a seller, and True for a superuser, asserted through admin.site._registry"
  - "no branch returns True without consulting request"
  - "no new inlined is_staff-or-is_superuser expression is introduced; User.role is used"
  - "no other ModelAdmin class is modified"
  - "the commit body states defence-in-depth, no current exploit, and cites AUTHZ-006 (validated 2026-09)"
  - "the fast Docker gate is green"
tests_to_run:
  - src/backend/apps/analytics/tests/
  - src/backend/apps/users/tests/test_user_roles.py
```

**Note on verification.** Inline. There is no gate and no cross-phase ordering, so a green targeted
run plus the fast gate closes this block. **The reason this block is first is not urgency — it is
that every other block in this phase lands on a file another phase also wants, and this one does
not.**

---

### BLOCK 2 — `ad_edit` must authorize on the row it mutates (`AUTHZ-007`)

| | |
|---|---|
| **Findings owned** | `AUTHZ-007` (MEDIUM) |
| **Class** | **behavioural** — changes which snapshot the authorization decision is made on |
| **Depends on** | **external:** phase 03 BLOCK 5, then phase 05 BLOCKs 2 and 8, must have landed on `apps/ads/views/edit.py`; otherwise re-read immediately before editing |
| **Blocks** | BLOCK 4 (`AUTHZ-002` composes with it and must be written against the corrected snapshot) |
| **Priority** | **P0.** It is a one-function change with a **three-times-repeated in-file precedent**, and it is the cheapest structural item in the phase |
| **Risk level** | **MEDIUM–HIGH.** Not because the change is large, but because `edit.py` is a **six-way contested file** with **seven `getsource` tripwires** (phase 11's `TEST-010` census) and one of them counts `select_for_update` occurrences |
| **Blast radius** | `apps/ads/views/edit.py::ad_edit`; `apps/ads/tests/test_edit_views_locking.py::TestEditViewsLocking` |
| **Required agents** | **Auditor · Researcher · Planner · Validator** — all four |

**The defect, in full, in execution order.** `ad_edit` does: `@login_required` → `ad =
get_object_or_404(Ad, id=ad_id)` (**unlocked read**, and *this* is the object the authorization
decision is made on) → `if ad.user_id != request.user.id:` → `logger.warning(...)` →
`HttpResponseForbidden` → `if request.method == "GET":` render → `with transaction.atomic():` →
`ad = get_object_or_404(Ad.objects.select_for_update(), id=ad_id)` (**re-read on the locked row,
ownership NOT re-checked**) → every branch below mutates *this* instance and passes its `ad_id` to
`submit_ad`.

**The transfer vector is real** (U8): `AdAdmin` declares no `fields` / `fieldsets` / `exclude` /
`form`, and its `readonly_fields` omits `user`, `status`, `published_at`, `original_published_at`,
`archived_at` and `deleted_at`. So the window between the unlocked read and the locked re-read is
exactly the window in which an ad can change owner. **That form defect is `AD-001`, phase 05 BLOCK
6's, and is not re-filed here** — it is the reason the window matters, not this block's work.

**Why this is not `AUTHZ-002`.** `AUTHZ-002` is a **service-scope** defect: the shared orchestrator
has no ownership predicate at all, and the fix belongs inside `submit_ad`. `AUTHZ-007` is a
**caller-scope** defect: the predicate exists in the view but is evaluated against a different
snapshot than the mutation. Different layer, different owner, different fix. **They compose and are
ordered (`2 → 4`), and merging them would hide one behind the other's diff.**

**The fix already exists, three times, in the same file.** `ad_archive` and `ad_reactivate` both do
`with transaction.atomic():` → `select_for_update()` → **then** the ownership comparison on the
locked instance → 403. `apps/ads/views/delete.py::ad_delete` is a third instance. **`ad_edit` is the
lone outlier.** This is a consistency fix, not a design question, and the report's "root cause" is
slightly off: the lock was added to `ad_edit` only, and the two siblings were written correctly.

**Alternatives for the check's shape, with trade-offs — GATE-free; R4 rules it:**

| Option | Shape | Maintains | Future evolution | Project convention | Consequence if wrong |
|---|---|---|---|---|---|
| **(a) — RULING** | Move the existing `ad.user_id != request.user.id` comparison **down** to the locked instance, inside the existing `transaction.atomic()`, leaving the unlocked read for the GET render path | Minimal diff; the render path still uses a cheap unlocked read | **Good** — the mutation and its guard share one snapshot, and the guard is visibly co-located with the lock | ✔ exactly `ad_archive` / `ad_reactivate` / `ad_delete` | If the unlocked read is removed too, the GET path takes a lock it does not need and the `select_for_update` count changes — see constraint 2 |
| (b) | Add a **second** locked read and check both | Belt-and-braces | **Poor** — two snapshots, two answers, and the second one is the only one that matters | ✘ **breaks the shipped `select_for_update` count tripwire** | Two lock acquisitions per POST; a structural test fails immediately |
| (c) | Extract a helper and call it from all four views | DRY | Tempting, and **wrong here** | ✘ the helper extraction changes the `getsource` structure the tripwires inspect | `test_ad_edit_get_path_not_locked` and `test_submit_ad_fetches_inside_atomic` both break on structure, not on behaviour |
| (d) | Scope the initial lookup instead: `get_object_or_404(Ad, id=ad_id, user=request.user)` | Shortest | **Poor for this view** — it changes a 403 into a 404 and makes the lock re-read meaningless | ✔ the codebase's IDOR-safe pattern (`cabinet/views/saved_searches.py::_user_search`) — **and it is the pattern new guards should use (§1.5)** | **Changing 403 → 404 is a user-visible status change** on a route with shipped tests, and the locked re-read still needs its own check. Correct for *new* code, wrong as a retrofit here |

**Binding constraints**

1. **The guard and the mutation share one snapshot.** The ownership comparison must be evaluated on
   the instance returned by the `select_for_update()` re-read, inside the existing
   `transaction.atomic()`. **Do not add a new `transaction.atomic()` block** — the invariant is one
   atomic section, not two.
2. **`select_for_update` appears exactly once in `ad_edit`'s source, after this block.**
   `test_ad_edit_get_path_not_locked` asserts `source.count("select_for_update") == 1` over the whole
   function. Moving the check does not add a lock and the assertion survives; **adding one, or
   extracting the fetch into a helper, breaks it** (F20).
3. **The unlocked read stays for the GET render path.** It is not a lock-holding path and the
   render branch returns before the `atomic()` block. Removing it is a behaviour and structure
   change nobody asked for.
4. **The 403 response, its log line, and its ordering relative to the GET branch do not change.**
   The report confirms current behaviour is already correct on every path — cross-seller attempts
   are denied — so this block changes *when* the check happens, not *what* it answers.
5. **No new fixture in `src/backend/conftest.py`.** Use the canonical `seller` / `user` /
   `create_test_ad`. Re-`force_login` rather than mutating an identity mid-test.
6. **Re-read `edit.py` immediately before editing** and **stop and report** if another phase has an
   uncommitted change to it. The correct serial position is
   *phase 03 BLOCK 5 → phase 05 BLOCK 2 → phase 05 BLOCK 8 → **this block** → BLOCK 4 → phase 10
   BLOCK 16*.

**Implementor task**

```yaml
id: task_15_b02_ad_edit_authorized_on_locked_row
title: "Move ad_edit's ownership assertion onto the locked row it mutates (AUTHZ-007 validated 2026-09)"
priority: high
depends_on: []
source_reference: ".ai/plans/15-authorization-remediation.md"
source_section: "BLOCK 2 - ad_edit must authorize on the row it mutates"
source_blocks: ["BLOCK 2"]
description: >
  ad_edit authorizes on an unlocked read, then re-reads the row under select_for_update inside
  transaction.atomic() without re-checking ownership, so the object the decision was made on and the
  object the mutation applies to are different snapshots. Move the ownership comparison onto the
  locked instance inside the existing atomic block, copying the pattern ad_archive and ad_reactivate
  already use in the same file and ad_delete uses in delete.py. This is a caller-scope fix and is
  deliberately not merged with AUTHZ-002, which is a service-scope fix in submit_ad; the two compose
  and are ordered, this block first.
goals:
  - "the ownership comparison is evaluated on the instance returned by the locked re-read, inside the existing transaction.atomic()"
  - "select_for_update appears exactly once in ad_edit's source after this change"
  - "the GET render path still uses its cheap unlocked read"
  - "the 403 response and its log line are unchanged"
extra_context: |
  EXTERNAL GATE: phase 03 BLOCK 5, then phase 05 BLOCKS 2 and 8, must have landed on
  apps/ads/views/edit.py. Re-read the file immediately before editing. If it carries another phase's
  uncommitted change, STOP and report - do not clobber it.
  BINDING CONSTRAINTS
  1. The guard and the mutation share one snapshot. Do not add a new transaction.atomic() block.
  2. select_for_update must appear exactly once in ad_edit's source.
     test_ad_edit_get_path_not_locked asserts source.count("select_for_update") == 1. Adding a second
     locked read, or extracting the fetch into a helper, breaks it. This is a hard constraint.
  3. The unlocked read stays for the GET render path. Removing it is an unrequested structure change.
  4. The 403 response, its log line, and the ordering relative to the GET branch do not change.
  5. No new fixture in src/backend/conftest.py.
  6. THIS IS NOT AUTHZ-002. Do not add an ownership check to submit_ad in this block, and do not
     change the user_id value passed at the two SubmitAdInput literals. That is BLOCK 4.
  7. AD-001 (AdAdmin's field set, which is what makes the transfer window real) is phase 05 BLOCK 6's.
     Cite it; do not fix it.
  CITATION: "AUTHZ-007 (validated 2026-09)".
files:
  - path: src/backend/apps/ads/views/edit.py
    targets:
      - type: function
        name: ad_edit
      - type: function_call
        value: select_for_update
    semantic_anchors:
      move_after:
        type: function_call
        value: select_for_update
    changes:
      - "Move the existing ownership comparison to the locked instance, inside the existing atomic block. No new lock, no new atomic block."
  - path: src/backend/apps/ads/tests/test_edit_views_locking.py
    targets:
      - type: class
        name: TestEditViewsLocking
    changes:
      - "Read-only unless a failure is genuine. Never weaken the source-count assertion."
  - path: src/backend/apps/ads/tests/test_edit.py
    targets:
      - type: module
        name: test_edit
    changes:
      - "Extend: non-owner GET and non-owner POST are refused, the row is byte-identical, and the owner path still renders and saves."
changes:
  - action: modify_code
    description: >
      Relocate the ownership guard from the unlocked read to the locked re-read, inside the existing
      transaction.atomic(), preserving the 403 response and its warning log line.
  - action: add_code
    description: >
      Add the behavioural assertions: owner edit renders and saves; non-owner GET and POST are both
      refused; the rejected request leaves the row byte-identical; and the locked row is the one
      every branch mutates.
acceptance_criteria:
  - "the ownership comparison runs on the locked instance inside the existing atomic block, never on the unlocked read"
  - "select_for_update appears exactly once in ad_edit's source; test_ad_edit_get_path_not_locked is green and unmodified"
  - "the owner path renders 200 on GET and saves on POST, with the row-lock still taken"
  - "a non-owner GET and a non-owner POST are both refused, and the row is byte-identical afterwards"
  - "submit_ad's signature, body and the two user_id values at the SubmitAdInput literals are untouched"
  - "the fast Docker gate is green"
tests_to_run:
  - src/backend/apps/ads/tests/test_edit_views_locking.py
  - src/backend/apps/ads/tests/test_edit.py
  - src/backend/apps/ads/tests/test_delete.py
```

---

### BLOCK 3 — One decorator, one method check first, and no bearer token that does not exist (`AUTHZ-008`)

| | |
|---|---|
| **Findings owned** | `AUTHZ-008` (LOW) |
| **Class** | **behavioural** — changes a status code for two already-denied cases and removes a wrong header |
| **Depends on** | nothing in-plan. `apps/moderation/views/decorators.py` is claimed by **no other plan**; `api_bulk.py` must **not** be touched (phases 09 and 10 both say so) |
| **Blocks** | BLOCK 8 (both denials in this decorator are the highest-leverage zero-logging denial points in the project) |
| **Priority** | **P1** — cheap, uncontended, and it discharges the `logger`-with-zero-calls evidence that BLOCK 8 builds on |
| **Risk level** | **LOW**, with one sharp edge: **five test methods break, two of them by name** (C-3) |
| **Blast radius** | `apps/moderation/views/decorators.py::staff_required_api`; two test modules, five methods |
| **Required agents** | **Auditor · Planner · Validator** (no Researcher: the refutation of the `422` claim is a source-reading result, and the answer is already fixed in F14) |

**The defect, in full.** `staff_required_api` has three sequential branches, **each a `return`**:
(1) not authenticated → `401` with `headers={"WWW-Authenticate": "Bearer"}`; (2)
`request.user.role != UserRole.ADMIN` → `403`; (3) `request.method != "POST"` → `405`; then
`return view_func(...)`.

**What is refuted and must be deleted from the tracker.** The report's "an `ADMIN` sending a `GET`
passes the role check, falls through the method check, and reaches `bulk_moderation_action`, which
then fails on an empty body and returns `422`" — and its probe line
`staff_required_api(ADMIN, GET) -> OK` — are **both wrong**. The third branch is a `return`, so the
view body is never entered on a non-`POST`, and the `422` branch in
`apps/moderation/views/api_bulk.py::bulk_moderation_action` is reachable only on a `POST` with an
unparseable body. **The report's own live-probe line is the error, and the `422`-instead-of-`405`
rollout risk in its safety table does not exist.** U7 re-derives the real 401/403/405 values.

**What is confirmed, and smaller.** The `WWW-Authenticate: Bearer` challenge is **factually wrong**.
`Bearer` appears in exactly three places in the repository: the decorator and two test files. There
is **no DRF, no `authtoken`, no token middleware, no API-key setting** — the only credential on
`/moderation/api/v1/bulk-action/` is the Django session cookie. The challenge sends an on-call
engineer hunting for a bearer-token bug that does not exist. Reordering the method check first
changes only the **diagnostic** status for two cases that are already denied correctly: anonymous
`GET` 401 → 405 and seller `GET` 403 → 405. That is a consistency improvement, not a defect, and it
is worth making **because** BLOCK 8 will make this decorator emit a reason code and the current
ordering would attribute a method error to an identity error.

**Alternatives for the header, with trade-offs — GATE-free; R5 rules it:**

| Option | Shape | Maintains | Future evolution | Project convention | Consequence if wrong |
|---|---|---|---|---|---|
| **(a) — RULING** | **Drop the header entirely** on the 401 | Honest: there is no bearer scheme to name | **Good** — adding a real scheme later is an additive change | ✔ nothing in the repo uses a `WWW-Authenticate` scheme | A generic client that *requires* a challenge header sees a bare 401. The endpoint has one known caller (the moderation dashboard, session-cookie based), so this is a non-issue in-tree — and it must be **stated in the commit body** rather than assumed |
| (b) | Replace with `Session` | Signals "cookie credentials" | Reasonable | ✔ honest, one-line | `Session` is not an IANA-registered scheme, so it is an invention. It reads as a correction without being one |
| (c) | Keep `Bearer` | Nothing | Nothing | ✘ **the finding is that it is a lie** | **Rejected — this is the defect** |

**Alternatives for the ordering — GATE-free; R6 rules it:**

| Option | Shape | Maintains | Project convention | Consequence if wrong |
|---|---|---|---|---|
| **(a) — RULING** | Method check first, then authentication, then role | A `GET` is answered `405` regardless of identity, which is the most informative answer for a caller that got the verb wrong | ✔ matches `@require_POST`-first ordering used by `ad_archive`, `ad_reactivate`, `ad_delete` and `consent_withdraw` | It exposes that the endpoint exists to an unauthenticated caller. For a moderation bulk endpoint on a classifieds site that is a negligible disclosure, and the 405 body carries no data. **Stated in the commit body** |
| (b) | Authentication first, role second, method third (today) | The current shape | — | **Rejected**: it attributes a method error to an identity error, and BLOCK 8's reason codes would then be wrong by construction |
| (c) | Drop the inline method check and use `@require_POST` on the view | Delegates to Django | ✔ matches `approve_ad` | The decorator is applied to the view by other means; moving the check changes **where** the 405 comes from and is a structural change to `api_bulk.py`, which **phases 09 and 10 forbid phase 15 from touching**. **BLOCK 11 revisits this for the sibling views with a proper gate; this block does not** |

**Binding constraints**

1. **The five test methods change in this same commit, and the commit body cites project rule 2 by
   name.** They are `test_decorators.py::TestStaffRequiredApi::test_unauthenticated_returns_401`,
   `::test_unauthenticated_get_returns_401`, `::test_non_staff_get_checks_staff_first`, and
   `test_priority_service.py`'s corresponding `test_unauthenticated_returns_401`.
   **Two of them pin the ordering by name** — `test_unauthenticated_get_returns_401` (*"authn check
   precedes method check"*) and `test_non_staff_get_checks_staff_first` (*"the 403 staff check
   precedes the 405 method check"*) — so the **names** change with the assertions. **A rename that
   leaves a stale name is a review finding.**
2. **`apps/moderation/views/api_bulk.py` is read-only.** Phases 09 and 10 both forbid touching it.
   If the correct answer turns out to require a change there, **stop and report** — do not make it.
3. **`staff_required` is not modified in this block.** It is BLOCK 8's second call site, and it
   answers with a `raise Http404` rather than a response. Its behaviour is unchanged here.
4. **No new log line lands in this block.** The decorator's `logger` stays uncalled until BLOCK 8.
   This block changes *what the decorator answers*, not whether it speaks.
5. **No 401 body, 403 body, or 405 body text changes without a new msgid.** If a body string does
   change, it goes through `gettext` with non-empty `ru` and `bs` `msgstr`. The recommended
   default is that **no body string changes** — the bodies are already accurate.
6. **The `405` must be returned for an authenticated non-`POST` regardless of role**, and the
   `403` for an authenticated non-ADMIN `POST`. Both are asserted.

**Implementor task**

```yaml
id: task_15_b03_staff_required_api_ordering_and_challenge
title: "Check the method before the identity in staff_required_api, and drop the bearer challenge that does not exist (AUTHZ-008 validated 2026-09)"
priority: low
depends_on: []
source_reference: ".ai/plans/15-authorization-remediation.md"
source_section: "BLOCK 3 - One decorator, one method check first, and no bearer token that does not exist"
source_blocks: ["BLOCK 3"]
description: >
  staff_required_api emits WWW-Authenticate: Bearer on a 401 even though the repository contains no
  DRF, no authtoken, no token middleware and no API-key setting - the only credential on the bulk
  moderation endpoint is the Django session cookie - so the challenge sends an on-call engineer
  hunting a bearer bug that does not exist. Reorder the branches so the method check answers first,
  which also stops a method error being attributed to an identity error, and drop the bogus header.
  Update the five test methods in the same commit; two of them pin the ordering by name, so their
  names change with their assertions. Do not repeat the refuted 422 claim: the third branch is a
  return, so the view body is never entered on a non-POST.
goals:
  - "the 401 carries no WWW-Authenticate header naming a scheme the project does not implement"
  - "an authenticated non-POST returns 405 regardless of role; an authenticated non-ADMIN POST returns 403; an anonymous request is still refused"
  - "the five affected test methods are updated in the same commit, with the two ordering-pinning names updated too"
  - "apps/moderation/views/api_bulk.py is unchanged"
extra_context: |
  BINDING CONSTRAINTS
  1. Five test methods change in this same commit and the commit body must cite project rule 2
     ("production code is king - a test that pins a defect gets the defect fixed, not the code bent")
     by name. Two of them pin the ORDERING by name, so the names change with the assertions; a
     stale name left behind is a review finding.
  2. apps/moderation/views/api_bulk.py is READ-ONLY. Phases 09 and 10 both forbid touching it. If
     the correct answer needs a change there, STOP and report.
  3. staff_required is NOT modified in this block. Its behaviour is unchanged here; BLOCK 8 wires its
     denial logging.
  4. No new log line lands here. The decorator's module-level logger stays uncalled until BLOCK 8.
  5. Prefer that no response body string changes. If one does, it goes through gettext with non-empty
     ru and bs msgstr.
  6. DO NOT repeat the refuted claim that an ADMIN GET reaches the view and returns 422. The third
     branch is a return, not a fall-through. The 422 branch in api_bulk.py is reachable only on a
     POST with an unparseable body.
  CITATION: "AUTHZ-008 (validated 2026-09)".
files:
  - path: src/backend/apps/moderation/views/decorators.py
    targets:
      - type: function
        name: staff_required_api
    changes:
      - "Method check first; 401 without a WWW-Authenticate naming a non-existent scheme; 403 for an authenticated non-ADMIN POST."
  - path: src/backend/apps/moderation/tests/test_decorators.py
    targets:
      - type: class
        name: TestStaffRequiredApi
    changes:
      - "Update the three affected methods; rename the two that pin the ordering so the name matches the new assertion."
  - path: src/backend/apps/moderation/tests/test_priority_service.py
    targets:
      - type: method
        name: test_unauthenticated_returns_401
    changes:
      - "Assert the 401 without the bearer challenge; assert the message and the method-check-first order."
changes:
  - action: modify_code
    description: >
      Reorder the three guards and remove the bogus WWW-Authenticate header from the 401 response.
  - action: modify_code
    description: >
      Update the five affected test methods in the same commit, including the two renames, and state
      project rule 2 by name in the commit body.
acceptance_criteria:
  - "an anonymous request is refused; the 401 no longer names a bearer scheme"
  - "an authenticated non-POST returns 405 for both an ADMIN and a non-ADMIN"
  - "an authenticated non-ADMIN POST still returns 403 and an ADMIN POST still reaches the view"
  - "all five affected test methods are updated in this commit; the two ordering-pinning names match their new assertions"
  - "apps/moderation/views/api_bulk.py is byte-identical"
  - "no new log line was added here; the logger call count is unchanged at zero"
  - "the commit body cites project rule 2 by name and states the header-drop consequence"
  - "the fast Docker gate is green"
tests_to_run:
  - src/backend/apps/moderation/tests/test_decorators.py
  - src/backend/apps/moderation/tests/test_priority_service.py
```

---

### BLOCK 4 — Make `SubmitAdInput.user_id` a real actor id (`AUTHZ-002`)

| | |
|---|---|
| **Findings owned** | `AUTHZ-002` (HIGH, taxonomy-mandated, **unreachable today**) |
| **Class** | **behavioural** — changes the trust model of a service boundary |
| **Depends on** | **BLOCK 2** (hard, §4.2). **Externally:** it must land **before phase 10 BLOCK 16** |
| **Blocks** | **phase 10 BLOCK 16** — the single highest-consequence sequencing constraint in the phase |
| **Priority** | **P0.** Cheap, and the sequencing cost of deferring it is that another phase ships a permanently tautological guard |
| **Risk level** | **MEDIUM.** The code change is small; the trap is that the *obvious* implementation is a no-op that looks like a fix |
| **Blast radius** | `apps/ads/services/submission.py` (eight-way contested) and `apps/ads/views/edit.py` (six-way contested) |
| **Required agents** | **Auditor · Researcher · Planner · Validator** — all four |

**The defect, in full.** `SubmitAdInput` declares `user_id: int | None`. **The token `user_id` does
not appear anywhere in `submit_ad`'s body.** The row is fetched inside the existing
`with transaction.atomic():` by `Ad.objects.select_for_update().get(id=input.ad_id)` — with **no
owner filter and no actor comparison** — and `Ad.DoesNotExist` is the only rejection path. The DTO
advertised an actor and the body ignored it; that gap was invisible in review precisely because
nothing stated the precondition.

**The trap, stated so no one falls into it.** Both `SubmitAdInput` literals in
`apps/ads/views/edit.py` pass **`user_id=ad.user_id`** — the ad's own owner, not the actor. So
`if ad.user_id != input.user_id: return False` is **always `False` on the web path**. Implemented
literally, the guard protects nothing while *looking* like it protects the main write path, and the
test suite goes green. **The fix is two halves and they must land together.**

**Reachability, verified.** All three call sites: `edit.py` (two literals, both inside the
ownership-checked `POST` branch, `ad_id` from the URL kwarg) and
`telegram_bot/handlers/ad_create/submit.py::process_preview` (reads `ad_id` and `user_id` from the
**same per-chat FSM dict**; `entry.py::cmd_post` writes `ad_id` only inside a `/post` flow that is
itself `user_id`-gated and calls `create_draft_ad(user_id=data["user_id"])`). So on the bot path
`ad.user_id == data["user_id"]` by construction. **No management command, job or API endpoint calls
`submit_ad`.** Reachability is genuinely nil today, and this block is defence-in-depth against the
first fourth caller.

**The acceptance test is the row, never the return value.** Whether a hijacked ad ends `published`
or `on_moderation_failed` depends entirely on whether the injected content passes `auto_moderate`,
which runs inside the same transaction. The validator's repro returned `False` with the row still
mutated. **A reproduction that returns `False` is not a refutation.** Assert that **the row is
byte-identical** (title, description, category, city, price, status, `user_id`).

**Blast radius, stated honestly and downward.** The victim row is a `DRAFT` or `ARCHIVED` ad, and
`auto_moderate` runs in the same transaction, so a hijacked draft is moderated, not silently
published. The realistic outcomes are a *defaced* or *failed* ad, and a seller whose draft is
destroyed by another seller — a denial-of-service against a specific object at least as much as a
data-integrity breach.

**Alternatives for the guard's placement, with trade-offs — GATE-free; R7 rules it:**

| Option | Shape | Maintains | Future evolution | Project convention | Consequence if wrong |
|---|---|---|---|---|---|
| **(a) — RULING** | Compare inside the **existing** `transaction.atomic()`, **after** the `select_for_update()` fetch, returning `(False, [...])` on mismatch | The check and the mutation share one snapshot — the same invariant BLOCK 2 establishes at caller scope | **Good** — the service stops being a trusted-internal orchestrator and starts being a boundary | ✔ `apps/users/services/login_token.py`'s docstring states the same split: *the service layer owns the predicate, the caller owns the transaction* | None identified; the one to watch is the `source.index()` tripwire (constraint 2) |
| (b) | Compare **before** `transaction.atomic()` | Cheaper on a mismatch | **Poor** — a TOCTOU window between the check and the lock, which is precisely `AUTHZ-007`'s defect reproduced one layer down | ✘ | **The test suite goes red on `test_submit_ad_fetches_inside_atomic`**, which is the correct outcome |
| (c) | Scope the fetch: `Ad.objects.select_for_update().get(id=input.ad_id, user_id=input.user_id)` | One-line, and race-free by construction | **Good** — this is the codebase's IDOR-safe pattern (`_user_search`) | ✔ the strongest pattern available | It changes the exception the caller sees (`DoesNotExist` instead of an explicit `(False, [...])`), and `process_preview`'s error handling must be checked. **A legitimate alternative, listed so the choice is on the record — the Ruling is (a) because the explicit rejection reason is more useful to the two web callers than an exception** |
| (d) | Trust the caller; document the precondition only | Zero code | **Poor** — this is today's state, and it is why the omission was invisible | ✘ | **Rejected: it ships a docstring describing a control that does not exist** |

**Binding constraints**

1. **Both halves land in the same commit.** The guard in `submit_ad` **and** `edit.py` passing
   `request.user.id` at **both** `SubmitAdInput` literals. **A guard without the caller change is a
   tautology and is worse than no guard, because it looks like a fix.**
2. **The guard goes after the locked fetch, inside the existing `transaction.atomic()`.**
   `test_submit_ad_fetches_inside_atomic` asserts `"Ad.objects.get(id=input.ad_id)" not in source`
   and that the `select_for_update` index is **greater than** the `atomic` index. **Moving the
   fetch into a helper raises `ValueError` in that test, not a clean failure** — so the fetch stays
   inline in the function.
3. **The DTO's `user_id: int | None` may become `int` only if every caller can supply it.** Both
   web literals can; the bot's `data.get("user_id")` returns `None` when absent. **Prefer keeping
   the optional annotation and failing closed on `None`** — a missing actor id is a denial, not a
   bypass (constraint 1, §0.2.2).
4. **The docstring states the trust model and a `guards:` line names the invariant every caller must
   uphold.** This is the advisory recommendation that makes the next reviewer's job possible.
5. **The bot path must keep working.** `process_preview` still publishes; its `/post` →
   `process_preview` flow is asserted end-to-end. A bot test that cannot import the backend conftest
   must use `src/telegram_bot/tests/conftest.py`'s async `user`.
6. **No change to `auto_moderate`, to the lifecycle status machine, or to any return-value string**
   other than adding the ownership-rejection reason. **The two existing rejection reasons must be
   byte-identical**, because shipped tests assert on them.
7. **Re-read both files immediately before editing** and stop and report on a concurrent change.
   The correct serial position is *… → BLOCK 2 → **this block** → phase 10 BLOCK 16.* **If phase
   10 BLOCK 16 lands first, this block's guard is permanently tautological — escalate to the
   coordinator rather than proceeding.**

**Implementor task**

```yaml
id: task_15_b04_submit_ad_actor_ownership_guard
title: "Make SubmitAdInput.user_id a real actor id: guard on the locked row and pass the actor from the view (AUTHZ-002 validated 2026-09)"
priority: high
depends_on: ["task_15_b02_ad_edit_authorized_on_locked_row"]
source_reference: ".ai/plans/15-authorization-remediation.md"
source_section: "BLOCK 4 - Make SubmitAdInput.user_id a real actor id"
source_blocks: ["BLOCK 4"]
description: >
  submit_ad never references input.user_id: the row is fetched inside the existing atomic block with
  no owner filter and no actor comparison, so the DTO advertises an actor the body ignores. Two
  halves must land in the same commit or the guard is a no-op: submit_ad compares ad.user_id against
  input.user_id after the locked fetch inside the existing transaction.atomic(), and the two
  SubmitAdInput literals in apps/ads/views/edit.py pass request.user.id instead of the ad's own
  owner. Assert that the row is byte-identical on a mismatch - never the return value, which is
  content-dependent because auto_moderate runs in the same transaction. Record the trust model in
  the docstring with a guards: line.
goals:
  - "submit_ad refuses a mismatched actor id, leaving the row byte-identical"
  - "both SubmitAdInput literals in edit.py pass request.user.id, so the guard is meaningful on the web path"
  - "the guard is evaluated after the locked fetch, inside the existing atomic block"
  - "the bot /post -> process_preview path still publishes"
extra_context: |
  THE TRAP: implemented literally as "if ad.user_id != input.user_id: return False", this guard is
  a TAUTOLOGY on the web path, because both SubmitAdInput literals currently pass user_id=ad.user_id
  - the ad's own owner, not the actor. It would protect nothing while looking like it protects the
  main write path, and the suite would go green. Both halves MUST land in this commit.
  SEQUENCING: this block must land before phase 10 BLOCK 16, whose description already pre-commits
  to user_id=request.user.id. If phase 10 BLOCK 16 has already landed, STOP and escalate to the
  coordinator - do not proceed, because the guard would be permanently tautological.
  BINDING CONSTRAINTS
  1. Both halves in one commit. A guard without the caller change is worse than no guard.
  2. The guard goes AFTER the locked fetch, inside the EXISTING transaction.atomic().
     test_submit_ad_fetches_inside_atomic asserts the fetch is inline in the function and that its
     select_for_update index is greater than the atomic index. Moving the fetch into a helper
     raises ValueError in that test. Do not add a second atomic block.
  3. Prefer keeping user_id: int | None and failing CLOSED on None. A missing actor id is a denial,
     not a bypass.
  4. The docstring states the trust model, and a guards: line names the invariant every caller must
     uphold.
  5. The bot /post -> process_preview path still publishes. Bot tests cannot import the backend
     conftest; they use src/telegram_bot/tests/conftest.py's async user.
  6. auto_moderate, the lifecycle status machine, and the two existing rejection reason strings are
     unchanged. Shipped tests assert on those strings.
  7. Do not add a fetch-with-owner-filter variant. Option (c) was considered and recorded in the
     plan; the ruling is (a) because an explicit (False, [...]) is more useful to the two web
     callers than an exception. Do not re-open it here.
  8. Re-read both files immediately before editing. submission.py is EIGHT-way contested and
     edit.py is SIX-way. Stop and report on a concurrent change.
  CITATION: "AUTHZ-002 (validated 2026-09)".
files:
  - path: src/backend/apps/ads/services/submission.py
    targets:
      - type: class
        name: SubmitAdInput
      - type: function
        name: submit_ad
      - type: function_call
        value: select_for_update
    semantic_anchors:
      insert_after:
        type: function_call
        value: select_for_update
    changes:
      - "Compare ad.user_id against input.user_id after the locked fetch, inside the existing atomic block; return (False, [...]) on mismatch. Fail closed on a missing actor id. Add a guards: line to the docstring."
  - path: src/backend/apps/ads/views/edit.py
    targets:
      - type: function
        name: ad_edit
      - type: class
        name: SubmitAdInput
    changes:
      - "Both literals pass user_id=request.user.id, never user_id=ad.user_id."
changes:
  - action: modify_code
    description: >
      Add the actor comparison inside the existing atomic block after the locked fetch, and document
      the service's trust model.
  - action: modify_code
    description: >
      Change both SubmitAdInput constructions in ad_edit to pass the requesting user.
  - action: add_code
    description: >
      Add the regression tests: a mismatched user_id leaves the row byte-identical, AND a POST by a
      non-owner with a valid body is refused before submit_ad is reached.
acceptance_criteria:
  - "a mismatched user_id leaves the ad row byte-identical - title, description, category, city, price, status and user_id all unchanged - asserted on the row, never on the return value"
  - "a POST by a non-owner with a valid body is refused before submit_ad is reached"
  - "both SubmitAdInput literals pass request.user.id; no user_id=ad.user_id literal remains in ad_edit"
  - "the guard runs after the select_for_update fetch, inside the existing atomic block; test_submit_ad_fetches_inside_atomic is green and unmodified"
  - "a missing/None actor id is denied, not allowed"
  - "the bot /post -> process_preview path still publishes, asserted in the bot suite"
  - "the docstring states the trust model and carries a guards: line naming the caller invariant"
  - "the fast Docker gate and the bot suite are both green"
tests_to_run:
  - src/backend/apps/ads/tests/test_edit_views_locking.py
  - src/backend/apps/ads/tests/test_submission.py
  - src/backend/apps/ads/tests/test_edit.py
  - src/telegram_bot/tests/test_ad_create.py
```

---

### BLOCK 5 — One account-state declaration, two levels, read by both processes (`AUTHZ-001a` + `AUTHZ-005a`)

| | |
|---|---|
| **Findings owned** | `AUTHZ-001` (the **declaration and its shape**; HIGH) · `AUTHZ-005` (the **vocabulary** half; MEDIUM) |
| **Class** | **structural** — this block introduces the single source of truth both processes will read |
| **Depends on** | nothing in-plan. **Externally:** phase 04 §5.2 item 3 forbids phase 04 touching these five symbols; phase 05 §5.3 marks the file **read-only**; phase 06 owns `VAL-003`'s semantics; **phase 10 BLOCK 8 binding constraint 1 requires `can_publish_ad` to remain** |
| **Blocks** | **BLOCK 6** (the gate consumes the verdict) · **BLOCK 7** (the policy change) |
| **Priority** | **P0.** It is the phase's single most valuable structural change and the one phases 06 and 08 are waiting on |
| **Risk level** | **MEDIUM–HIGH.** The design risk is **low** — the DENY set already exists and is test-pinned on the bot side — and the risk is concentrated in one thing: **silently changing an answer while claiming to only move it** |
| **Blast radius** | `apps/users/services/account_state.py` (phase 05 read-only) · `apps/users/services/__init__.py` · `src/telegram_bot/middlewares/permissions.py` (**owned by no other phase**) · `apps/users/tests/test_account_state.py` · `src/telegram_bot/tests/test_account_state_middleware.py` (~30 tests) |
| **Required agents** | **Auditor · Researcher · Planner · Validator** — all four |

**What this block is, precisely.** Not a new policy. **The bot's interaction DENY set is already
exactly** `{is_banned, is_deleted, is_declined, consent_revoked}` and is **already pinned by a
shipped test** —
`src/telegram_bot/tests/test_account_state_middleware.py::TestCrossPredicateAgreement::test_matches_explicit_formula`
asserts that literal formula. `AUTHZ-001` is therefore an **extraction of existing, tested
semantics into one declaration that both processes read**, so the answers become *byte-identical by
construction* rather than by parallel maintenance. **Every answer this block ships must be the
answer that ships today** — for the bot, for `can_login`, and for `can_publish_ad`.

**Why the report's single-commit recommendation is deliberately split here (this is the plan's one
substantive deviation, and it is a safety improvement).** The report asks for the extraction, the
middleware and the publish refactor in **one commit**, so the project cannot ship two competing
account-state vocabularies. **The split preserves that invariant exactly**: BLOCK 5 creates the
declaration and makes the **bot** the first consumer; BLOCK 6 adds the web gate as the second.
**No moment exists at which two vocabularies coexist**, because only one exists from the moment
BLOCK 5 lands. What the split buys is that the highest-risk commit in the phase — a gate that
terminates live sessions and is user-visible — is a **separate, independently reviewable and
independently revertable** commit, and the pure-refactor commit in front of it is reviewable
against a simple, strong criterion: *did any answer change?* The answer must be **no**, for all of
them. See §4.2, edge 5→6.

**RULING R1 — the two-level shape (this is Q2, ruled here).** One declaration exposes both:

1. **the per-request verdict** — an instance-level, purpose-parameterised verdict, and
2. **the named `User` flag terms** a queryset filter can be composed from.

`get_account_state()` today is a `NamedTuple` over a `User` instance, and **that instance-level
shape is the reason no queryset-level visibility predicate was ever written** — `06-VAL-003`
(audience predicate on `User` / `SavedSearch`) and `SRCH-004` (ad-visibility on `Ad`) have been
owner-blocked for **two** phases and would be blocked for a fourth if the blocker is reproduced one
module over. **Phase 15 owns the shape and the terms. Phase 06 owns the `User` audience predicate's
semantics; phase 08 owns the `Ad` ad-visibility predicate's semantics.** Neither may be inferred
from what this block declares, and **phase 15 must not implement either predicate.**

| Option for the shape | Maintains | Future evolution | Project convention | Consequence if chosen |
|---|---|---|---|---|
| **(a) — RULING R1** | One declaration, two consumable levels, named terms | **Good** — phases 06/08 can build their predicates on the terms without touching this module | ✔ composition (terms + verdict) over a single fat predicate | Phase 15 must resist the temptation to also decide what the terms *mean* for listing queries |
| (b) | Instance-level verdict only | **Poor** — reproduces the blocker in a new module | ✘ | **`06-VAL-003` and `SRCH-004` stay blocked for a fourth phase.** The cost is recorded here so the choice is on the record and cannot be re-litigated silently |

**File surface (semantic units)**

| File | Symbol | Today | Reserved elsewhere? |
|---|---|---|---|
| `src/backend/apps/users/services/account_state.py` | `AccountState`, `get_account_state`, `can_login`, `can_publish_ad`, `get_state_badge` | five exported functions; the two predicates are separate and divergent | **Phase 05 §5.3 marks the file read-only; phase 04 §5.2 item 3 forbids it to reconcile the predicates; phase 10 BLOCK 8 requires `can_publish_ad` to stay.** Phase 15 claims the two-level declaration. **Do not create a second service module** — that is the class of defect both findings exist to end |
| `src/backend/apps/users/services/__init__.py` | the import list and `__all__` | five names | Add the new names; **never remove `can_publish_ad` from `__all__`** |
| `src/telegram_bot/middlewares/permissions.py` | `AccountStateMiddleware._evaluate_user_state`, `._evaluate_publish_permission`, `._check_user_state`, `._resolve_user` | the two live evaluators plus a test-facing wrapper | **No other phase may touch it** (phases 04, 05, 06 all forbid it). `_check_user_state`'s single-positional-argument signature is documented load-bearing |
| `src/backend/apps/users/tests/test_account_state.py` | `TestCanPublishAd` (9 tests), `TestCanLogin` (6), `TestGetAccountState` (6), `TestGetStateBadge` (8) | pins the whole flag matrix, **including two wrong answers** | Phase 15 claims the retarget |

**Alternatives for how the bot adopts the declaration — GATE-free; R8 rules it:**

| Option | Shape | Maintains | Future evolution | Project convention | Consequence if wrong |
|---|---|---|---|---|---|
| **(a) — RULING** | Both evaluators call the shared declaration; the middleware keeps its own decision-string vocabulary and the FSM backfill | The single-resolution contract (`_resolve_user` keyed on `chat_id`, three consumers sharing one instance) is untouched | **Good** — a fourth consumer costs one call | ✔ composition | A decision-string mapping table is a small, explicit surface. It must be **total**, and its test must cover every member |
| (b) | Delete the evaluators and inline the declaration in `__call__` | Nothing | **Poor** | ✘ | **Breaks `_check_user_state`'s documented load-bearing signature and ~30 bot tests**, and loses the interaction/publish separation that BLOCK 7 depends on |
| (c) | Leave the bot alone and add the declaration for the web only | Nothing | **Worse** — two vocabularies immediately, which is the defect | ✘ | **Rejected: this is the failure the whole phase exists to prevent** |

**Binding constraints**

1. **No answer changes.** Before and after, the bot's interaction gate denies exactly
   `{is_banned, is_deleted, is_declined, consent_revoked}` — with the **contact-deep-link DECLINE
   exception** intact; the publish gate denies exactly what it denies today; `can_login` denies
   exactly what it denies today (including `can_login(is_deleted=True) is True`, which a shipped
   test pins as intentional); and `get_state_badge` is unchanged. **The block's headline acceptance
   criterion is a before/after matrix over all four flags × {bot interaction, bot publish,
   `can_login`, `can_publish_ad`}, identical on both sides.**
2. **The `None` fail-open for the bot is preserved, and is not extended.** Both bot gates return
   `(True, "")` for an unregistered identity **by design**, because the handler's own gate rejects it.
   **The web gate in BLOCK 6 fails closed** (constraint 1, §0.2.2). Two processes, two deliberate
   answers, and the difference is **documented in the declaration**, not left to be inferred.
3. **`_check_user_state(chat_id, is_contact_link=False)` keeps its single-positional-argument
   signature.** It is documented load-bearing and pinned by bot tests. `__call__` still resolves the
   user once and still shares that instance with three consumers.
4. **Target the tree's real method names** — `_evaluate_user_state` and
   `_evaluate_publish_permission` (**C-2**). `_check_publish_permission` does not exist.
5. **`can_publish_ad` is reduced to a thin wrapper over the declaration, never deleted.** Phase 10
   BLOCK 8 binding constraint 1 forbids deletion; the finding's dead-code label was rejected
   (F3, the spec references the behaviour). Its `is_declined` / `consent_revoked` behaviour is
   **unchanged in this block** — changing it is BLOCK 7, behind two gates.
6. **`AccountState` stays a `NamedTuple`.** Project rule 11 puts Pydantic at system boundaries;
   this is internal domain logic. A conversion is scope creep.
7. **The queryset terms are declared, not used.** No queryset in `listings_query.py` or
   `alert_query.py` is touched. A test demonstrates the terms are **reachable from a real
   `filter(...)`** — that is what "expressible" means and it is the whole point of R1.
8. **No default-manager filter anywhere** (constraint 1). No `IMMEDIATE_ALERTS_ENABLED` change (F19).
9. **No new `StrEnum` in `apps/core/enums.py` in this block.** R3's enum belongs to BLOCK 6's
   denial reasons. This block's purpose vocabulary stays inside the account-state module unless a
   `StrEnum` is unavoidable — and if it is, R3's re-read rule applies.

**Implementor task**

```yaml
id: task_15_b05_shared_account_state_declaration
title: "One account-state declaration at two levels, adopted by the bot with every answer unchanged (AUTHZ-001 + AUTHZ-005 validated 2026-09)"
priority: high
depends_on: []
source_reference: ".ai/plans/15-authorization-remediation.md"
source_section: "BLOCK 5 - One account-state declaration, two levels, read by both processes"
source_blocks: ["BLOCK 5", "BLOCK 6", "BLOCK 7"]
description: >
  The web tier and the bot tier answer "may this account act" through two unrelated shapes -
  get_account_state() returning a NamedTuple over a User instance, can_login() and can_publish_ad()
  as separate predicates, and AccountStateMiddleware's own _evaluate_user_state and
  _evaluate_publish_permission - and only can_login is called anywhere in production, from one view.
  Extract ONE declaration that exposes two consumable levels from one source: a per-request verdict
  for a named purpose, and the named User flag terms a queryset filter can be composed from. Make
  the bot the first consumer. The instance-level-only shape is precisely why no queryset-level
  visibility predicate was ever written, which is why 06-VAL-003 and SRCH-004 have been blocked for
  two phases; phase 15 owns the shape and the terms, phases 06 and 08 own the semantics and this
  block must not implement either predicate. Nothing about the answers may change: the bot's DENY
  set is already exactly {is_banned, is_deleted, is_declined, consent_revoked} and is already
  test-pinned. This block adds no web middleware and changes no policy.
goals:
  - "one declaration exposes a per-request verdict and the named User flag terms a filter can compose"
  - "the bot's _evaluate_user_state and _evaluate_publish_permission both call it, and every answer is byte-identical to today's"
  - "can_login, can_publish_ad and get_state_badge keep their exact current answers and remain exported"
  - "a test demonstrates the terms are reachable from a real User.objects.filter(...)"
  - "the four-flag x four-consumer before/after matrix is identical on both sides"
extra_context: |
  THIS BLOCK CHANGES NO ANSWER. Its headline acceptance criterion is a before/after matrix over
  is_banned / is_deleted / is_declined / consent_revoked x {bot interaction, bot publish, can_login,
  can_publish_ad} that is IDENTICAL on both sides. If any cell differs, the block is wrong - not the
  matrix.
  THE DENY SET IS NOT A NEW POLICY. The bot's interaction gate already denies exactly
  {is_banned, is_deleted, is_declined, consent_revoked} and
  src/telegram_bot/tests/test_account_state_middleware.py::TestCrossPredicateAgreement::test_matches_explicit_formula
  already pins that literal formula. This block makes both processes read one declaration.
  RULING R1 (Q2): two levels from one source. Option (b), instance-level only, was considered and
  rejected: it reproduces the blocker that has kept 06-VAL-003 and SRCH-004 owner-blocked for two
  phases, in a new module. Do not re-open it.
  BINDING CONSTRAINTS
  1. No answer changes. The contact-deep-link DECLINE exception, the publish gate's narrower set,
     can_login(is_deleted=True) is True, and get_state_badge are all unchanged here.
  2. The bot's fail-open for an unregistered identity is PRESERVED and is NOT extended to the web.
     Both bot gates return (True, "") for None by design because the handler's own gate rejects an
     unregistered identity. The difference between the two processes must be documented in the
     declaration, not left to be inferred.
  3. _check_user_state(chat_id, is_contact_link=False) keeps its single-positional-argument
     signature. It is documented load-bearing and pinned by bot tests. __call__ still resolves the
     user once via _resolve_user keyed on chat_id and shares that instance with three consumers.
  4. TARGET THE REAL METHOD NAMES: _evaluate_user_state and _evaluate_publish_permission.
     _check_publish_permission does not exist. Targeting the source report's name yields an
     AttributeError or, worse, a silent no-op refactor.
  5. can_publish_ad is reduced to a thin wrapper over the declaration and NEVER deleted. Phase 10
     BLOCK 8 binding constraint 1 forbids deletion, and the finding's dead-code label was rejected:
     the spec references the behaviour, so it is a missing integration. Its is_declined and
     consent_revoked behaviour is UNCHANGED in this block - changing it is BLOCK 7 behind two gates.
  6. AccountState stays a NamedTuple. Project rule 11 puts Pydantic at system boundaries; this is
     internal domain logic.
  7. The queryset terms are DECLARED, not used. Do not touch listings_query.py or alert_query.py. A
     test demonstrates the terms compose into a real User.objects.filter(...) - that is what
     "expressible" means.
  8. No default-manager filter on User or any app. No IMMEDIATE_ALERTS_ENABLED change.
  9. No new StrEnum in apps/core/enums.py in this block. R3's enum belongs to BLOCK 6.
  10. No middleware is added here. The web gate is BLOCK 6 and it is a separate commit.
  CITATION: "AUTHZ-001 + AUTHZ-005 (validated 2026-09)".
files:
  - path: src/backend/apps/users/services/account_state.py
    targets:
      - type: class
        name: AccountState
      - type: function
        name: get_account_state
      - type: function
        name: can_login
      - type: function
        name: can_publish_ad
    changes:
      - "Add the two-level declaration: a purpose-parameterised per-request verdict, and the named User flag terms composable into a filter. Reduce can_login and can_publish_ad to thin wrappers that preserve today's exact answers. Document the bot-fail-open vs web-fail-closed difference."
  - path: src/backend/apps/users/services/__init__.py
    targets:
      - type: module
        name: services
    changes:
      - "Export the new declarations. Never remove can_publish_ad from __all__."
  - path: src/telegram_bot/middlewares/permissions.py
    targets:
      - type: method
        name: _evaluate_user_state
      - type: method
        name: _evaluate_publish_permission
      - type: method
        name: _check_user_state
      - type: method
        name: _resolve_user
    changes:
      - "Both evaluators call the shared declaration. Decision-string mapping is total. Signatures and the single-resolution contract are unchanged."
  - path: src/backend/apps/users/tests/test_account_state.py
    targets:
      - type: class
        name: TestCanPublishAd
      - type: class
        name: TestCanLogin
      - type: class
        name: TestGetAccountState
    changes:
      - "Retarget to the new declaration in the SAME commit, preserving every current answer."
changes:
  - action: add_code
    description: >
      Add the two-level declaration to apps/users/services/account_state.py: the per-request verdict
      and the named queryset-composable terms, from one source.
  - action: modify_code
    description: >
      Make both bot evaluators call the declaration, preserving the interaction/publish separation,
      the decision strings, the contact-deep-link exception and the None fail-open.
  - action: add_code
    description: >
      Add the before/after matrix test and the terms-are-composable test.
acceptance_criteria:
  - "the four-flag x four-consumer matrix is byte-identical before and after, and the test proves it"
  - "the contact-deep-link DECLINE exception, the publish gate's narrower set, can_login(is_deleted=True) is True, and get_state_badge are all unchanged"
  - "the bot's fail-open for an unregistered identity is preserved and the web's fail-closed is documented in the declaration"
  - "_check_user_state keeps its single-positional-argument signature and __call__ still resolves the user once on chat_id"
  - "the named User terms compose into a real User.objects.filter(...) and the test asserts the resulting row set"
  - "can_publish_ad still exists, is still exported, and has the same answer for is_declined and consent_revoked as it has today"
  - "no queryset in listings_query.py or alert_query.py is touched; no default-manager filter exists; IMMEDIATE_ALERTS_ENABLED is unchanged"
  - "the ~30 bot tests in test_account_state_middleware.py are green with no assertion weakened"
  - "the fast Docker gate and the bot suite are both green"
tests_to_run:
  - src/backend/apps/users/tests/test_account_state.py
  - src/telegram_bot/tests/test_account_state_middleware.py
  - src/telegram_bot/tests/test_ad_create.py
```

---

### BLOCK 6 — The per-request web gate (`AUTHZ-001b`)

| | |
|---|---|
| **Findings owned** | `AUTHZ-001` (the **gate**; HIGH) · the phase's first denial instrumentation (from `AUTHZ-009`'s vocabulary) |
| **Class** | **structural** — a new control on every request |
| **Depends on** | **BLOCK 5** (hard, §4.2). **Externally:** `config/settings/base.py` is six-way contended; phase 06 owns the `technical-specification.md` sentence this falsifies (Q13) |
| **Blocks** | BLOCK 7 (the publish policy change must not move under a gate whose own answer is unpinned) · BLOCK 8 (reuses the reason vocabulary) |
| **Priority** | **P0, and the highest rollout risk in the phase** |
| **Risk level** | **HIGH** — user-visible, session-terminating, and it will terminate the operator's own test account the first time anyone bans, declines or soft-deletes a user |
| **Blast radius** | **every authenticated web request.** `config/settings/base.py::MIDDLEWARE` · the new `apps/users/middlewares/` package · `apps/core/enums.py` |
| **Required agents** | **Auditor · Researcher · Planner · Validator** — all four |

**The defect, in full.** `MIDDLEWARE` has **14** entries and **none** is an account-state gate (F1).
`can_login` has **exactly one** production call site (F2), so it is a one-shot gate evaluated at
login time and never again. Of the **five** account-state-changing paths, **four** leave the live
session authorized: self-service `consent_decline`, `UserAdmin.withdraw_consent_action`,
`ban_user_for_ad`, and `bulk_ban_users`. Only `consent_withdraw` closes, because it calls
`logout(request)` with the requester being the affected identity. **Three of the four open paths
are structurally unreachable at the view layer** — `ban_user_for_ad(ad, moderator_id, reason)` and
`bulk_ban_users(queryset, moderator_id, reason)` take **no `request`**, and `bulk_ban_users` never
materialises a `User` at all, so Django offers no way to enumerate the sessions belonging to a
given user. **The only place that can revoke those identities is the affected user's own next
request, which is exactly what this gate is.**

**This block does not re-file `04-AUT-002` and adds no `logout()` call.** Phase 04 BLOCK 6 owns the
session-layer half, and its §5.3 is explicit: it "may not add middleware, a decorator, or a shared
predicate. If a reviewer sees a second gate appear, BLOCK 6 is wrong." **There is exactly one gate
in this programme, and this block writes it.**

**Placement.** Immediately after `AuthenticationMiddleware`, so `request.user` is populated. It must
**fail closed** for an authenticated request whose state cannot be evaluated, and it must **not**
fail closed for an anonymous request — public routes are untouched, and treating an anonymous
request as a denial would take the entire site down.

**Alternatives for the deny response — GATE-FREE, and this is the phase's most consequential
user-visible choice, so it is a labelled gate. GATE Q15:**

| Option | Shape | User experience | Rollout risk | Project convention | Consequence if wrong |
|---|---|---|---|---|---|
| (a) | `logout(request)` then **`403`** with a minimal, translated page | A banned seller who clicks a bookmark gets a bare 403 | **High** — a moderator's bulk ban makes every affected user see a 403 on every page, and operators will read it as a site-wide breakage. The report calls this the phase's highest risk | ✔ `staff_required`'s `Http404` and `ad_edit`'s `HttpResponseForbidden` are both existing denial shapes | **A 403 is a dead end**: no link home, no explanation, and it will be the top ticket in the first 24 hours |
| (b) | `logout(request)` then **`302` to `LOGIN_URL`**, which re-presents the login deep-link page | The user is told, in the site's own voice, that they must sign in again — and the login page's own `login_status` (`can_login`, 410 for banned/declined) is where the *account* reason surfaces | **Low–Medium** | ✔ `consent_withdraw` already does `logout(request)` **and** redirects; `login_required` redirects the whole site to `LOGIN_URL` today | The user is bounced to a page that will refuse them. That is *correct*, and it reuses an existing, translated surface instead of inventing a new one — **at the cost of one extra hop and no explicit "banned" wording** |
| (c) | `logout(request)` then **`403` with a translated, reason-bearing page and a link home** | Explicit and kind | Medium — a **new** user-visible surface, so it carries i18n cost and a template | ✘ a new template and a new msgid, where (a) and (b) need neither or only one | The most informative option and the most new code. **The honest cost/benefit: (b) reuses `login_status`'s existing 410 reason surface, which already distinguishes banned from declined** |

**Options (a) and (b) are both fail-closed** — the session is destroyed either way, and the
difference is the body, not the control. **The Implementor may not choose.** GATE Q15 records which
one, and BLOCK 6 must not start without it.

**Alternatives for the package home — GATE-free; R9 rules it:**

| Option | Shape | Maintains | Project convention | Consequence if wrong |
|---|---|---|---|---|
| **(a) — RULING** | New package `src/backend/apps/users/middlewares/` with `__init__.py` and `account_state_gate.py` | Small and focused | ✔ `apps/core/middleware/` is a package with one module per concern; the report names this path | None — the directory genuinely does not exist (F17) and must be created |
| (b) | A single `apps/users/middlewares.py` module | Equally small | ✘ four sibling concerns already use the package shape | A second shape in the same tree for one class |
| (c) | Add the class to `apps/core/middleware/` | No new package | ✘ **the gate is `apps/users` domain logic**; `apps/core` is cross-cutting plumbing, and phase 07/09 own that directory's other concerns | Wrong ownership, and it makes the "one declaration in `apps/users`" story untrue |

**Binding constraints**

1. **Fail closed; never fail open; never depend on a queryset.** An authenticated request whose
   account state cannot be evaluated is **denied**. An anonymous request is **not** denied by this
   gate — it is passed through, because public routes must keep working. **No default-manager filter
   is introduced anywhere** (constraint 1, §0.2.2), because it would hide withdrawn users from the
   bot's `_resolve_user`.
2. **The DENY set is `{is_banned, is_deleted, is_declined, consent_revoked}` and `is_active` is
   carved OUT — subject to GATE Q1.** `is_active=False` is already handled by
   `ModelBackend.user_can_authenticate()`, and the report's own matrix says it already yields a 302.
   **Whether the gate also destroys the session for `is_active=False` is GATE Q1, and it must be
   re-derived from U1 first.** Shipping it either way without a written answer is the failure mode
   §0.2.2 and Q1 both exist to prevent.
3. **The gate is a session term only.** It must **not** fold in `user__is_declined=False` or any
   listing-visibility term. The *visibility* predicate is phase 05/08's; the *audience* predicate is
   phase 06's.
4. **`config/settings/base.py::MIDDLEWARE` is append-only, in place.** Insert immediately after
   `AuthenticationMiddleware`. **Never reorder an entry another phase annotated**, never delete one,
   and never reformat the list. The file is claimed by phases 02, 03, 04, 06, 08, 09 and 10 — **re-read
   immediately before editing; if another phase has an uncommitted change, stop and report.**
5. **R3's `StrEnum` is appended to `apps/core/enums.py`, nothing is reordered, and no
   `AdvisoryLockId` is allocated.** If the file is under concurrent edit when this block starts,
   **stop and report** rather than reorder another phase's work.
6. **The gate is instrumented on day one** with the same reason vocabulary BLOCK 8 formalises, so
   the first denial is diagnosable. The *shared* helper and the ad views come in BLOCK 8; the gate
   itself must not ship silent.
7. **The `technical-specification.md` sentence is not edited.** Phase 06 holds the file. **Record
   the request in the commit body and route it to BLOCK 12** (C-4, Q13). **A documented divergence
   is acceptable; a unilateral edit is not.**
8. **Do not touch `ban_user_for_ad`, `bulk_ban_users`, `consent_decline` or
   `withdraw_consent_action`.** They are recorded as evidence and routed to phase 04 BLOCK 6, and
   `admin_actions.py` is five-way contended *and* moved by phase 10 BLOCK 12. **Record only.**
9. **Any new user-visible string** follows GATE Q15's answer: option (a) needs no string, option (c)
   needs a template plus non-empty `ru` and `bs` `msgstr`. The gate is part of DoD either way.
10. **The gate answers by calling BLOCK 5's declaration.** It must not re-derive any flag itself, and
    it must not import the bot middleware.

**Implementor task**

```yaml
id: task_15_b06_account_state_gate_middleware
title: "Install the per-request web account-state gate, fail closed, instrumented on day one (AUTHZ-001 validated 2026-09)"
priority: high
depends_on: ["task_15_b05_shared_account_state_declaration"]
source_reference: ".ai/plans/15-authorization-remediation.md"
source_section: "BLOCK 6 - The per-request web gate"
source_blocks: ["BLOCK 6"]
description: >
  MIDDLEWARE has 14 entries and no account-state gate, can_login has exactly one production call
  site, and four of the five account-state-changing paths leave the live session authorized. Three of
  those four are structurally unreachable at the view layer - ban_user_for_ad and bulk_ban_users take
  no request and bulk_ban_users never materialises a User - so the affected user's own next request
  is the only place the revocation can happen. Install one AccountStateGateMiddleware immediately
  after AuthenticationMiddleware, deny on {is_banned, is_deleted, is_declined, consent_revoked},
  destroy the session on deny, and emit a stable reason code from the first commit. is_active is
  carved out subject to gate Q1. Do not add a logout() call anywhere - that is phase 04 BLOCK 6, and
  shipping a second gate would violate 04-VAL-001.
goals:
  - "an authenticated request from a banned, deleted, declined or consent-revoked user is denied and its session destroyed"
  - "anonymous requests and public routes are unaffected"
  - "a restricted-but-valid seller (ads_auto_publish=False) still reaches the dashboard"
  - "the gate fails closed when account state cannot be evaluated, and passes anonymous requests through"
  - "the gate emits a stable reason code from its first commit"
  - "the technical-specification.md sentence is recorded as a request to phase 06, not edited"
extra_context: |
  GATES THAT MUST BE ANSWERED IN WRITING BEFORE IMPLEMENTATION: Q15 (the deny response shape) and Q1
  (whether is_active belongs in the DENY set, which requires U1 to be re-derived first). The
  Implementor is forbidden from choosing an option. Q1's rule is that a silent ship here is how a
  control is added in one phase and removed in the next.
  THIS IS THE ONLY GATE IN THE PROGRAMME. 04-VAL-001 reads: "Both phases must not file the same
  middleware." Phase 04 BLOCK 6 may add logout() calls and may NOT add middleware, a decorator or a
  shared predicate. Do not add a second gate, and do not add a logout() call anywhere.
  BINDING CONSTRAINTS
  1. Fail closed. An authenticated request whose account state cannot be evaluated is DENIED. An
     anonymous request is passed through - treating it as a denial would take the site down. No
     default-manager filter is introduced anywhere, on User or any app: it would hide withdrawn
     users from the bot's _resolve_user, which keys on chat_id precisely because withdrawn users have
     telegram_id nulled.
  2. The DENY set is {is_banned, is_deleted, is_declined, consent_revoked}. is_active is carved OUT,
     subject to the Q1 answer. is_active=False is already handled by
     ModelBackend.user_can_authenticate().
  3. This is a SESSION term only ("can this identity act"). Do NOT fold in user__is_declined=False or
     any listing-visibility term. Visibility is phase 05/08's; the audience predicate is phase 06's.
  4. config/settings/base.py::MIDDLEWARE is APPEND-ONLY, IN PLACE. Insert immediately after
     AuthenticationMiddleware. Never reorder an entry another phase annotated, never delete one,
     never reformat the list. Seven plans claim this file. Re-read immediately before editing; stop
     and report on a concurrent change.
  5. Append one new StrEnum to apps/core/enums.py. Reorder nothing. Allocate no AdvisoryLockId. If
     the file is under concurrent edit, STOP and report.
  6. The gate is instrumented on day one with a stable reason code, so the first denial is
     diagnosable. The shared helper and the ad views are BLOCK 8; the gate itself must not ship
     silent.
  7. Do NOT edit docs/01-spec/technical-specification.md. It states "No web-side middleware
     redirects soft-deleted users", which this block falsifies on the day it lands - but phase 06
     holds the file. Record the request in the commit body and route it to BLOCK 12.
  8. Do NOT touch ban_user_for_ad, bulk_ban_users, consent_decline or withdraw_consent_action.
     Record them as evidence and route to phase 04 BLOCK 6. admin_actions.py is five-way contended
     and is MOVED by phase 10 BLOCK 12.
  9. Any new user-visible string depends on the Q15 answer and needs non-empty ru and bs msgstr plus
     a green test_i18n_completeness.py.
  10. The gate calls BLOCK 5's declaration. It must not re-derive a flag and must not import the bot
      middleware.
  CITATION: "AUTHZ-001 (validated 2026-09)".
files:
  - path: src/backend/apps/users/middlewares/__init__.py
    targets:
      - type: module
        name: middlewares
    changes:
      - "New package, following apps/core/middleware/'s shape. The directory does not exist today."
  - path: src/backend/apps/users/middlewares/account_state_gate.py
    targets:
      - type: class
        name: AccountStateGateMiddleware
    changes:
      - "Call BLOCK 5's declaration for the interaction purpose. On deny: destroy the session and answer per GATE Q15, emitting a stable reason code. On anonymous: pass through. On unevaluable authenticated state: deny."
  - path: src/backend/config/settings/base.py
    targets:
      - type: module
        name: settings
      - type: setting
        name: MIDDLEWARE
    changes:
      - "Insert the gate immediately after AuthenticationMiddleware, in place. Append-only; reorder nothing."
  - path: src/backend/apps/core/enums.py
    targets:
      - type: module
        name: enums
    changes:
      - "Append one new StrEnum for the denial reason vocabulary. Reorder nothing; allocate no AdvisoryLockId."
  - path: src/backend/apps/users/tests/test_account_state_gate.py
    targets:
      - type: module
        name: test_account_state_gate
    changes:
      - "One case per DENY flag, the anonymous pass-through, the restricted-but-valid seller, and the fail-closed-on-unevaluable case."
changes:
  - action: add_code
    description: >
      Create the middleware package and AccountStateGateMiddleware, register it, and append the
      reason StrEnum.
  - action: add_code
    description: >
      Add the gate tests, including a positive control that a normal seller's dashboard still renders
      200 with the gate installed.
acceptance_criteria:
  - "each of is_banned, is_deleted, is_declined and consent_revoked produces a denied request with the session destroyed, and the response is the one GATE Q15 chose"
  - "anonymous requests and public routes are unaffected; a positive control shows a normal seller's dashboard renders 200 with the gate installed"
  - "a restricted-but-valid seller (ads_auto_publish=False) still reaches the dashboard"
  - "an authenticated request whose account state cannot be evaluated is denied, and a test asserts the denial"
  - "is_active handling matches the written GATE Q1 answer, and the U1 matrix is recorded in the commit body"
  - "MIDDLEWARE gained exactly one entry, immediately after AuthenticationMiddleware, with nothing reordered, deleted or reformatted"
  - "apps/core/enums.py gained exactly one appended StrEnum, with no reordering and no AdvisoryLockId allocated"
  - "a denied request emits exactly one log record carrying the stable reason code and the actor id"
  - "no default-manager filter was added; no listing-visibility term was folded into the gate; IMMEDIATE_ALERTS_ENABLED is unchanged"
  - "no logout() call was added to any view or admin action"
  - "the commit body records the request to phase 06 about the technical-specification.md sentence"
  - "the fast Docker gate is green"
tests_to_run:
  - src/backend/apps/users/tests/test_account_state_gate.py
  - src/backend/apps/users/tests/test_account_state.py
  - src/backend/apps/users/tests/test_logout.py
  - src/backend/apps/users/tests/test_consent.py
  - src/backend/apps/cabinet/tests/test_cabinet_sections.py
  - config/settings/tests/test_env_allowlist.py
```

---

### BLOCK 7 — The publish gate's DENY set, once the DECLINE decision is on the record (`AUTHZ-005b`)

| | |
|---|---|
| **Findings owned** | `AUTHZ-005` (the **policy**; MEDIUM, reclassified SPEC-DEVIATION) |
| **Class** | **behavioural** — the answers for `is_declined` and `consent_revoked` change, and shipped tests pin the wrong ones |
| **Depends on** | **BLOCK 6** (hard, §4.2). **Externally, and this is the block's real gate:** **phase 06's `PII-105` DECLINE-reversibility decision (Q4)** and **phase 06's `PII-113` DECLINE-semantics conflict (Q5)** |
| **Blocks** | BLOCK 12 (the prior record's coverage-gap line becomes a live assertion here) |
| **Priority** | **P1.** Deliberately **not** P0: the two external gates are outside this phase's control, and the report itself places this finding third by sequence, not by risk |
| **Risk level** | **MEDIUM.** The change is small; the risk is shipping it **before** the DECLINE decision, which would make the publish gate the *only* control standing between a declined seller and a post |
| **Blast radius** | `apps/users/services/account_state.py` (the publish purpose's terms) · the bot's `_evaluate_publish_permission` call site · `apps/users/tests/test_account_state.py::TestCanPublishAd` |
| **Required agents** | **Auditor · Researcher · Planner · Validator** — all four |

**The defect, in full.** `can_publish_ad` tests three flags, in order: `state.is_banned` → `False`;
`state.is_deleted` → `False`; `not state.ads_auto_publish` → `False`; else `True`. **It never tests
`is_declined` and never tests `consent_revoked`,** although `AccountState` carries both. So a
**declined** seller and a **GDPR-withdrawn** seller both return `True`. The report names only
`is_declined`; `consent_revoked` is also wrong, and it is **worse**: GDPR-withdrawn is a strictly
stronger state than soft-deleted, and the predicate denies the weaker one while allowing the
stronger.

**Why a declined seller is blocked today anyway — and why that is the defect, not a mitigation.**
The live publish gate is the bot's `_evaluate_publish_permission`, which consults `ads_auto_publish`
**alone** and returns `(True, "")` for an unregistered identity. A declined seller is blocked today
only because `_evaluate_user_state` denies them **first** — an earlier, unrelated, stricter check.
**Two predicates, one accidentally-correct answer.** If either is ever corrected in isolation, the
protection silently disappears. That is the whole finding, and it is why the remedy is a **single
declaration with a named purpose**, not a wider `if`.

**Sequencing, and it is hard.** If `PII-105` option (a) is taken — DECLINE becomes reversible and
web login is regained — then the publish gate becomes the **only** thing keeping a declined seller
from posting, and this block's missing `is_declined` term becomes **the whole control**. **AUTHZ-005
must be sequenced *after* phase 06's `PII-105` decision, not in parallel with it.** Phase 04 BLOCK 6's
decline-path `logout()` is gated on the same decision. **Neither phase recorded this dependency; it
is recorded here so neither is surprised.**

**The race with a prior record.** `docs/99-agent/test-audit-block-f-findings.md:193` already lists
*"No test for `can_publish_ad` when `is_declined=True`"* as a test-coverage gap. **Adding that test
today would pin the wrong answer.** The predicate must change **first**, in the same commit, and the
prior record's line becomes a live assertion (advisory recommendation 5). Recorded in BLOCK 12 so
the two do not race.

**Alternatives for the change's shape — GATE-free once Q4/Q5 are answered; R10 rules it:**

| Option | Shape | Maintains | Future evolution | Project convention | Consequence if wrong |
|---|---|---|---|---|---|
| **(a) — RULING** | Add `is_declined` and `consent_revoked` to the **publish purpose's term list** in BLOCK 5's declaration; both the bot's evaluator and `can_publish_ad` inherit it | One declaration, two purposes, one edit point | **Good** — a fourth flag is a one-line change in one place | ✔ the DENY branch becomes the *same set* the interaction gate uses, which is the structural argument for the shared predicate | If `PII-105` option (a) landed and the interaction gate later stops denying DECLINE, the publish purpose still denies it — **which is correct, and must be stated in the commit body so it does not look like a stale flag** |
| (b) | Fold publish into the interaction purpose — one purpose, no distinction | Simplicity | **Poor** — the two purposes have genuinely different policies (`ads_auto_publish` is a publish-only preference; the four flags are account-wide) | ✘ conflates a preference with an account state | A seller with `ads_auto_publish=False` would be denied the whole bot interaction, not just posting. **A regression, not a refactor** |
| (c) | Keep `can_publish_ad` and add a second, corrected predicate | Nothing | **Worse** — two published answers, which is the defect | ✘ | **Rejected outright** |

**Binding constraints**

1. **The publish DENY set becomes `{is_banned, is_deleted, is_declined, consent_revoked}` plus
   `ads_auto_publish == False`** — the same account-state set the interaction gate uses, plus the
   publish-only preference. **Both the bot's evaluator and `can_publish_ad` change together.**
2. **Both external gates must be answered in writing first.** Q4 (`PII-105` DECLINE reversibility,
   phase 06) and Q5 (which DECLINE sentence governs, phase 06 `PII-113`). **The Implementor is
   forbidden from choosing.** If either is unanswered, **this block does not start** and the finding
   stays open with a recorded reason.
3. **`test_declined_user_can_publish` is corrected in this same commit**, and project rule 2 is cited
   by name in the commit body — **the test pins a wrong answer; the answer changes, not the test's
   intent.** The 8 other `TestCanPublishAd` cases keep their current expectations; only the declined
   and consent-revoked answers change.
4. **The bot's interaction gate is untouched by this block.** Its DENY set does not change; only the
   publish evaluator's term list does. `TestCrossPredicateAgreement::test_matches_explicit_formula`
   must stay green, which it will, because it pins the *interaction* formula.
5. **`can_publish_ad` still exists and is still exported.** The correction happens *inside* the
   declaration it now wraps.
6. **The unregistered-identity fail-open in the publish evaluator is unchanged** (`(True, "")` for
   `None`), and stays documented as bot-specific. **This is a deliberate asymmetry with the web
   gate and must be restated in the docstring**, not silently harmonised.
7. **No queryset, no `listings_query.py`, no `alert_query.py`, no `IMMEDIATE_ALERTS_ENABLED`
   change.** A seller who cannot publish still **sees** their own ads; this block changes what they
   may **post**, not what is **public**.
8. **No user-visible string** is added. The bot's denial messages already exist; if a new one is
   needed it must be translated for `ru` and `bs` and asserted in the bot suite.

**Implementor task**

```yaml
id: task_15_b07_publish_deny_set
title: "Add is_declined and consent_revoked to the publish DENY set, in the bot and in can_publish_ad, together (AUTHZ-005 validated 2026-09)"
priority: high
depends_on: ["task_15_b06_account_state_gate_middleware"]
source_reference: ".ai/plans/15-authorization-remediation.md"
source_section: "BLOCK 7 - The publish gate's DENY set, once the DECLINE decision is on the record"
source_blocks: ["BLOCK 7"]
description: >
  can_publish_ad tests is_banned, is_deleted and ads_auto_publish, and never tests is_declined or
  consent_revoked, so a declined seller and a GDPR-withdrawn seller both return True. The live bot
  publish gate consults ads_auto_publish alone; declined sellers are blocked today only because the
  unrelated, stricter interaction gate happens to deny them first. Two predicates, one accidentally
  correct answer - and if PII-105 option (a) makes DECLINE reversible, the publish gate becomes the
  only control. Add both flags to the publish purpose's term list in the shared declaration so the
  bot evaluator and can_publish_ad change together. Correct the test that pins the wrong answer in the
  same commit and cite project rule 2 by name.
goals:
  - "a declined seller cannot publish, from the bot middleware and from can_publish_ad, for the same reason"
  - "a consent-revoked seller cannot publish, from both"
  - "ads_auto_publish=False, banned and deleted still cannot publish, for the same reasons as before"
  - "the bot's interaction gate is unchanged and its cross-predicate agreement test stays green"
extra_context: |
  GATES THAT MUST BE ANSWERED IN WRITING BEFORE IMPLEMENTATION: Q4 (phase 06's PII-105 DECLINE
  reversibility decision) and Q5 (phase 06's PII-113 DECLINE-semantics conflict). If either is
  unanswered, THIS BLOCK DOES NOT START and the finding stays open with a recorded reason. The
  Implementor is forbidden from choosing an option.
  BINDING CONSTRAINTS
  1. The publish DENY set becomes {is_banned, is_deleted, is_declined, consent_revoked} plus
     ads_auto_publish == False. The bot evaluator and can_publish_ad change TOGETHER.
  2. Correct test_declined_user_can_publish in the same commit and cite project rule 2 by name in the
     commit body. The test pins a wrong answer; the ANSWER changes, not the test's intent. The eight
     other TestCanPublishAd cases keep their current expectations - only the declined and
     consent-revoked answers change.
  3. The bot's INTERACTION gate is untouched. TestCrossPredicateAgreement::test_matches_explicit_formula
     pins the interaction formula and must stay green.
  4. can_publish_ad still exists and is still exported; it now wraps the corrected declaration.
  5. The publish evaluator's fail-open for an unregistered identity is unchanged - (True, "") for
     None - and stays documented as bot-specific. This is a deliberate asymmetry with the web gate
     and must be restated in the docstring, not silently harmonised.
  6. No queryset, no listings_query.py, no alert_query.py, no IMMEDIATE_ALERTS_ENABLED change. A
     seller who cannot publish still SEES their own ads; this block changes what they may POST, not
     what is PUBLIC.
  7. No user-visible string is added. If a new bot denial message is needed it must be translated for
     ru and bs and asserted in the bot suite.
  8. Do not add a second, corrected predicate alongside can_publish_ad. That is the defect.
  CITATION: "AUTHZ-005 (validated 2026-09)".
files:
  - path: src/backend/apps/users/services/account_state.py
    targets:
      - type: function
        name: can_publish_ad
    changes:
      - "The publish purpose's term list gains is_declined and consent_revoked, matching the interaction purpose's account-state set plus the ads_auto_publish preference."
  - path: src/telegram_bot/middlewares/permissions.py
    targets:
      - type: method
        name: _evaluate_publish_permission
    changes:
      - "Read the publish purpose from the shared declaration instead of consulting ads_auto_publish alone."
  - path: src/backend/apps/users/tests/test_account_state.py
    targets:
      - type: class
        name: TestCanPublishAd
    changes:
      - "Correct the declined case and add the consent-revoked case, in the same commit as the production change."
changes:
  - action: modify_code
    description: >
      Add the two missing account-state terms to the publish purpose in the shared declaration.
  - action: modify_code
    description: >
      Point the bot's publish evaluator at the declaration, preserving its decision strings and its
      unregistered-identity fail-open.
  - action: modify_code
    description: >
      Correct the test that pins the wrong declined answer, and add the consent-revoked case.
acceptance_criteria:
  - "a declined seller is denied publication by the bot middleware and by can_publish_ad, for the same reason code"
  - "a consent-revoked seller is denied publication by both"
  - "ads_auto_publish=False, is_banned and is_deleted are still denied, with unchanged reasons"
  - "the bot's interaction gate and TestCrossPredicateAgreement::test_matches_explicit_formula are green and unmodified"
  - "the publish evaluator's fail-open for an unregistered identity is unchanged and is documented as bot-specific"
  - "the eight other TestCanPublishAd cases keep their current expectations; only the declined and consent-revoked answers changed"
  - "the commit body cites project rule 2 by name and records both gate answers"
  - "the fast Docker gate and the bot suite are both green"
tests_to_run:
  - src/backend/apps/users/tests/test_account_state.py
  - src/telegram_bot/tests/test_account_state_middleware.py
  - src/telegram_bot/tests/test_ad_create.py
```

---

### BLOCK 8 — One reason-coded denial helper, and the ad views that already log prose (`AUTHZ-009`)

| | |
|---|---|
| **Findings owned** | `AUTHZ-009` (LOW) |
| **Class** | **behavioural** — changes log shape and introduces a counter |
| **Depends on** | BLOCK 6 (soft — the reason vocabulary is created there). **Nothing cross-phase, except the counter (U14, phase 12's Q5)** |
| **Blocks** | nothing in-plan. It is the phase's observability block and the last thing to be reviewed |
| **Priority** | **P1.** It should not be first: BLOCK 6's gate must be instrumented on day one using the vocabulary this block formalises, and BLOCK 3's decorator is the natural second consumer |
| **Risk level** | **LOW–MEDIUM.** The code is small; the risks are log-volume growth on denial paths and a counter that invents a metrics convention |
| **Blast radius** | `apps/moderation/views/decorators.py` (now BLOCK 3's) · `apps/ads/views/edit.py` (now BLOCKs 2 and 4's) · `apps/ads/views/delete.py` · `apps/ads/views/favorite.py` |
| **Required agents** | **Auditor · Planner · Validator** (no Researcher: U14's grep is a pre-block step, not a decision) |

**The defect, in full.** `apps/moderation/views/decorators.py` declares a module-level `logger` and
makes **zero** `logger.*` calls — the intent was there and was never wired, which is the sharpest
single piece of evidence in the finding. `apps/ads/views/favorite.py` also makes zero. `delete.py`
makes 2; `edit.py` makes 3. The two highest-leverage zero-logging denial points in the project are
`staff_required` (a `raise Http404`) and `staff_required_api` (three `JsonResponse` returns), and
both were in BLOCK 3's file.

**The correction to the recommendation, which this block adopts.** The report proposes instrumenting
the shared decorators. That is right for the two admin gates, but the **highest-value** denials are
the **per-object** ones in the ad views, which already log a human-readable sentence with **no
stable machine-readable code**. The useful change is a **stable reason code**
(`authz.deny reason=not_owner user=… path=… resource=ad:42`) emitted from **one** helper that both
the decorators and the ad views call. **Otherwise this phase creates a third denial-logging
convention alongside the two that already exist** — which is the same class of defect the predicate
extraction exists to end.

**Alternatives for the counter — this one is genuinely conditional, and the reason is U14:**

| Option | Shape | Maintains | Future evolution | Project convention | Consequence if wrong |
|---|---|---|---|---|---|
| (a) | `log_authz_denial(...)` emits one `logger.warning` with the reason code and the actor id, and returns; **no counter** | Nothing depends on a counter existing | **Poor** — the finding's "no metrics on denied authorization attempts" limb stays open | ✔ zero new infrastructure | The LOW finding's metrics limb is **not closed** and must be recorded as such, not quietly dropped |
| (b) | (a) plus a `prometheus_client` `Counter` named `authz_denials_total`, labelled by reason | Closes both limbs | **Good** — a counter is the right shape for a rate | ⚠ **no Python-level Prometheus client is wired into any module today** (U14); the metrics story is a middleware pair in `MIDDLEWARE`. **Adding a client is new infrastructure, and phase 12 owns the monitoring stack** | A counter in a module that nothing scrapes is a **silently dead instrument** — worse than none, because the finding looks closed. **Phase 12's Q5 is a *gated* decision on whether a monitoring stack is deployed at all** |
| (c) | (a) plus a `django-prometheus` metric through an existing export path | Closes both limbs without a new client | Depends on what U14 finds | ✔ `django_prometheus` is already a dependency and already in `MIDDLEWARE` | Only available if U14 finds a shipped convention. **If U14 finds nothing, this option does not exist** |

**Binding constraints**

1. **One helper, one convention.** Every denial this block touches goes through the same helper and
   carries a **stable, machine-readable reason code** — not a new prose format. The two existing
   prose sites it absorbs are rewritten to call it; they are not left in parallel.
2. **`WARNING` level, one record per denial, no more.** A test asserts **exactly one** record and
   that it contains the reason code and the actor id. Denial volume is real, and the report is
   explicit that it should stay at `WARNING` with a stable code rather than becoming a firehose.
3. **No `print()`.** `logger = logging.getLogger(__name__)` with lazy `%s` formatting.
4. **The counter is conditional on U14.** If no Python-level Prometheus client exists, **option (b)
   is unavailable and the block ships option (a) only**, recording the metrics limb as **open with a
   named owner (phase 12's Q5)**. **Do not add a metrics client to close a LOW finding.**
5. **`favorite.py` is not given `@login_required`.** Its guest-gate fragment endpoint deliberately
   renders for anonymous users and must keep returning a fragment, never a 302 — the module
   docstring says so, and `test_auth_nav` and the favourite-fragment tests depend on it. BLOCK 8's
   only change to that file is the denial's log record.
6. **`api_bulk.py` stays read-only.** The 405/403/401 responses' denials are logged from
   `staff_required_api` in `decorators.py`, not from the view.
7. **No behaviour change of any kind.** Every status code, body, redirect and response shape is
   identical before and after. **A block that changes an observable response is a different block.**
8. **New denial paths are not invented.** BLOCK 6's gate already emits through the same vocabulary
   and is not modified here except to route through the shared helper if the answer makes that
   cleaner.

**Implementor task**

```yaml
id: task_15_b08_denial_reason_codes
title: "Emit one stable reason code from one denial helper used by the decorators and the ad views (AUTHZ-009 validated 2026-09)"
priority: medium
depends_on: ["task_15_b06_account_state_gate_middleware"]
source_reference: ".ai/plans/15-authorization-remediation.md"
source_section: "BLOCK 8 - One reason-coded denial helper, and the ad views that already log prose"
source_blocks: ["BLOCK 8"]
description: >
  apps/moderation/views/decorators.py declares a module-level logger and calls it zero times; favorite.py
  likewise; delete.py and edit.py log prose sentences with no machine-readable code. Introduce one
  denial helper that emits exactly one WARNING record carrying a stable reason code, the actor, the
  path and the resource, and route the two decorators and the four ad-view denial sites through it -
  otherwise this phase creates a third convention alongside the two that already exist. A counter is
  conditional on whether any Python-level Prometheus client already exists; if none does, ship the
  log record only and record the metrics limb as open with phase 12 as its named owner.
goals:
  - "one helper emits exactly one WARNING record per denial, carrying a stable reason code, the actor id, the path and the resource"
  - "staff_required, staff_required_api, ad_edit, ad_archive, ad_reactivate, ad_delete and toggle_favorite all route through it"
  - "no observable response changes: identical status codes, bodies, redirects and response shapes"
  - "the metrics limb is either closed with a counter that a deployed stack scrapes, or recorded as open with a named owner"
extra_context: |
  BINDING CONSTRAINTS
  1. ONE helper, ONE convention. Every touched denial carries a stable machine-readable reason code.
     The two existing prose sites are rewritten to call the helper, not left in parallel.
  2. WARNING level, exactly one record per denial. A test asserts exactly one record and that it
     contains the reason code and the actor id. Denial volume is real.
  3. No print(). logger = logging.getLogger(__name__) with lazy %s formatting.
  4. THE COUNTER IS CONDITIONAL ON U14. Grep for Counter(, Gauge( and prometheus_client under src/
     FIRST. If no Python-level client exists, the counter option is UNAVAILABLE - ship the log record
     only and record the metrics limb as OPEN with phase 12's Q5 as its named owner. Do not add a
     metrics client to close a LOW finding. A counter nothing scrapes is a silently dead instrument
     and is worse than none.
  5. favorite.py must NOT be given @login_required. Its guest-gate fragment endpoint deliberately
     renders for anonymous users and must keep returning a fragment, never a 302. The only change to
     that file is the denial's log record.
  6. api_bulk.py stays read-only. The 401/403/405 denials are logged from staff_required_api in
     decorators.py, not from the view.
  7. No behaviour change of any kind. Identical status codes, bodies, redirects and response shapes.
  8. Do not invent new denial paths. BLOCK 6's gate already emits through the same vocabulary.
  CITATION: "AUTHZ-009 (validated 2026-09)".
files:
  - path: src/backend/apps/moderation/views/decorators.py
    targets:
      - type: function
        name: staff_required
      - type: function
        name: staff_required_api
      - type: module
        name: decorators
    changes:
      - "Wire the previously-unused module-level logger through the shared helper at each denial point."
  - path: src/backend/apps/ads/views/edit.py
    targets:
      - type: function
        name: ad_edit
      - type: function
        name: ad_archive
      - type: function
        name: ad_reactivate
    changes:
      - "Route the existing denial log lines through the shared helper, adding the stable reason code."
  - path: src/backend/apps/ads/views/delete.py
    targets:
      - type: function
        name: ad_delete
    changes:
      - "Route the existing denial log line through the shared helper."
  - path: src/backend/apps/ads/views/favorite.py
    targets:
      - type: function
        name: toggle_favorite
    changes:
      - "Add a denial log record via the shared helper. No guard change."
  - path: <Q/U14 decides: the existing shared logging home, or a new apps/core/ module>
    targets:
      - type: function
        name: log_authz_denial
    changes:
      - "The single helper, and the counter only if U14 shows a shipped convention."
changes:
  - action: add_code
    description: >
      Add the shared denial helper emitting one WARNING record with a stable reason code, the actor
      id, the path and the resource.
  - action: modify_code
    description: >
      Route the two decorators and the four ad-view denial sites through the helper, replacing the
      prose-only sites rather than running in parallel.
  - action: add_code
    description: >
      Add the exactly-one-record test and, only if U14 supports it, the labelled counter.
acceptance_criteria:
  - "a denied request emits exactly one WARNING record containing the stable reason code, the actor id, the path and the resource - asserted with caplog, including the uniqueness"
  - "the previously-unused logger in decorators.py is now called at every denial point in that module"
  - "no observable response changes; every status code, body, redirect and response shape is identical"
  - "toggle_favorite still renders a fragment for an anonymous caller and was not given @login_required"
  - "api_bulk.py is byte-identical"
  - "either a counter exists whose scrape path is verified against a deployed stack, or the metrics limb is recorded as open with phase 12's Q5 named as owner and no metrics client was added"
  - "the fast Docker gate is green"
tests_to_run:
  - src/backend/apps/moderation/tests/test_decorators.py
  - src/backend/apps/ads/tests/test_edit.py
  - src/backend/apps/ads/tests/test_delete.py
  - src/backend/apps/ads/tests/test_auth_nav.py
```

---

### BLOCK 9 — One role resolver, one moderator contract, and the registry test that enforces it (`AUTHZ-003`)

| | |
|---|---|
| **Findings owned** | `AUTHZ-003` (HIGH, band contested — GATE Q9) · discharges `VAL-002` |
| **Class** | **structural** — the block creates a *documented, executable* contract where none existed |
| **Depends on** | nothing in-plan. **Externally, and this is the block's hardest prerequisite:** **phase 04 BLOCK 1** must have landed, because `04-AUT-005` (with `PII-103` merged in) owns the `UserAdmin` field contract and AUTHZ-003 must cite it as a hard prerequisite |
| **Blocks** | BLOCK 12 (the decision record's final form) |
| **Priority** | **P0 — but the most gate-dependent block in the phase.** Three gates (Q3, Q3′, Q9) and one external prerequisite |
| **Risk level** | **HIGH — and the risk is directional: both candidate fixes are privilege expansions** |
| **Blast radius** | `apps/ads/views/listings.py::media_gate` (also phase 05 and phase 10's file) · the admin site's permission predicate · **one new decision record** · **one new registry-iterating contract test** |
| **Required agents** | **Auditor · Researcher · Planner · Validator** — all four |

**The defect, in full.** Four answers to one question:

| # | Implementation | Where | Answer for a superuser with `is_staff=False` |
|---|---|---|---|
| 1 | `AdminSite.has_permission` = `is_active and is_staff` (Django's, **not overridden in this repo**) | `django.contrib.admin` | **`False`** → 302 to the admin login |
| 2 | `User.role` = `is_staff or is_superuser` | `apps/users/models.py::User.role` | **`UserRole.ADMIN`** |
| 3 | `staff_required` checks `role != ADMIN` → `raise Http404` | `apps/moderation/views/decorators.py` | **allowed** |
| 4 | `media_gate`'s staff branch gates on raw `request.user.is_staff` | `apps/ads/views/listings.py` | **`False`** → **denied media that `staff_required` grants them** |

A fifth, partial answer lives in the 17 `ModelAdmin` overrides: `AdAdmin` / `AdImageAdmin` inline
`is_staff or is_superuser` (answer 2); `UserAdmin` uses bare `is_staff` for view/change and bare
`is_superuser` for add/delete — which is why a superuser-not-staff gets
`add=True, delete=True, view=False, change=False` on `users.User`, and a plain moderator gets
`view=True, change=True, add=False, delete=False`. **The ladder is inverted.** Phase 15 owns the
**permission predicate**; **phase 05 BLOCK 6 owns `AdAdmin`'s field set** and explicitly must not
change `has_change_permission` / `has_view_permission`; **phase 04 BLOCK 1 owns `UserAdmin`'s field
contract**, and `06-PII-103` must not patch it again.

**What is refuted and must be deleted from the tracker.** "No seeding command, group or fixture
exists anywhere in the repo to grant them" / "the moderator role is not deployable" is **false**.
`UserAdmin` declares no `fields` / `fieldsets` / `form`, so Django auto-builds a `ModelForm` over
every editable field; combined with `has_change_permission = request.user.is_staff` (no `obj`
check), a plain moderator reaches their **own** change form and can self-grant `user_permissions`.
**This reduces the finding's operational severity and raises a different one** — the same form lets
them set `is_superuser`, and a POST that omits an unchecked `BooleanField` silently clears
`is_staff`. That escalation is `04-AUT-005` / `04-VAL-004` / `PII-103`, it is **not re-filed here**,
and **AUTHZ-003 must not be closed without it.**

**⚠ The ordering hazard for this block's own test (U4).** A registry test that POSTs to a
moderator's own row **de-staffs the actor** mid-test, because un-checked `BooleanField`s submit as
absent. Later assertions in the same test then fail spuriously. **BLOCK 9's contract test is
read-only over `admin.site._registry` and never POSTs**, and the U4 probe re-`force_login`s between
its phases.

**GATE Q3 — what may `is_staff` do?** A plain moderator, today, reaches `Ad`, `AdImage` (read-only),
`Category`, `City` and `User` (writable), and is refused on the other 12 of 17 changelists. **The
answer to "may `is_staff` write to the moderation criteria, the audit log and the support desk?" is
"no — and there is no documented reason."** This is an **owner/product** decision, and it needs an
explicit review of the 17-model matrix. **The Implementor may not choose.**

| Option for the contract's content | Maintains | Project convention | Consequence if wrong |
|---|---|---|---|
| (a) `is_staff` is a *full* `ADMIN`, and the per-model write policy is declared per class | Matches the project's documented "is_staff IS the moderator role" position and `staff_required` | ✔ | **A privilege expansion for 12 changelists.** Explicitly reviewed, not a rubber stamp |
| (b) `is_staff` is a *read-only* moderator and write access is granted per model through `auth.Permission` | Matches today's effective behaviour exactly | ✔ matches 14 of 17 classes' per-model fallback | **The out-of-the-box moderator becomes read-only**, which is arguably a *reduction* — but it is still a behaviour change to 5 changelists and needs the same review |
| (c) A seeded `Group` defines the contract | Matches Django's model | ✘ contradicts the documented position | **Rejected in the report's own words.** Listed so the choice is on the record |

**GATE Q3′ — which route reconciles `AdminSite.has_permission` with `User.role`?**

| Option | Shape | Maintains | Future evolution | Project convention | Consequence if wrong |
|---|---|---|---|---|---|
| (i) | Override `AdminSite.has_permission` to `is_active and role == ADMIN` | The superuser-not-staff lockout **disappears** and the admin matches `staff_required` | **Good** — one method, and the fourth answer is gone | ✔ | **A privilege expansion**: a superuser-not-staff gains `/admin/` (it already has `/moderation/`). Wiring a project `AdminSite` subclass needs an `AppConfig.ready()` assignment and an `INSTALLED_APPS` entry — a real settings change in the six-way-contended `base.py` |
| (ii) | Declare that a superuser is **always** `is_staff=True` and enforce it at provisioning | Today's lockout becomes an *invariant* rather than a surprise | **Poor** — it leaves the lockout in place and only explains it | ✔ | **Requires an enforcement point that may not exist.** U13 is unverified: if `create_admin_user` does not exist, or does not set both, **option (ii) has no enforcement point and only (i) is coherent.** **Verify U13 first** |
| (iii) | Both: reconcile the method **and** add the invariant test | Everything | **Good** | ✔ | ✔ **The report's recommendation**: option (i) *and* option (ii) as a test either way. **This Planner records it as the leading candidate, and still gates it** — because it is a privilege expansion and Q3's contract must be settled first |

**Alternatives for the `media_gate` change — GATE-free; R11 rules it:**

| Option | Shape | Maintains | Project convention | Consequence if wrong |
|---|---|---|---|---|
| **(a) — RULING** | `media_gate`'s staff branch calls `request.user.role == UserRole.ADMIN` | The fourth answer collapses into the second; **a superuser-not-staff now answers identically here and in `staff_required`** | ✔ reuses `User.role`; ✔ a two-line change | None. **This is the one item in the block that is unconditionally correct**, and it is the item that removes one of the four answers at essentially zero risk |
| (b) | Introduce a `resolve_admin_role(user)` helper and route `media_gate`, `staff_required` and the admin site through it | One resolver | ✔ the report's item 1 suggests it | **A new indirection for two existing call sites.** Under §0.2.2 constraint 3 that is an abstraction without justification **at this size** — the property *is* the resolver. It becomes justified only if a third consumer appears, and BLOCK 9 is not allowed to create one |

**Binding constraints**

1. **No `AdminRolePermissionMixin`. No shared base class. No blanket grant. This is a prohibition, not
   an option** (`VAL-005`). Seven classes are read-only **by deliberate data-protection policy** —
   `AnalyticsEventAdmin` (*"Events are preserved for metrics"*), `ModeratorActionLogAdmin` (audit
   trail), `ConsentRecordAdmin` (GDPR Art. 7(1) record), `LoginTokenAdmin` (credential material),
   `SupportTicketAdmin` (audit trail), `SiteConfigAdmin` (singleton), `AdImageAdmin` — and a uniform
   grant turns an audit trail into a mutable table. **Any block that introduces one is wrong.**
2. **Deny by default.** Any new permission answer consults `request` and returns `False` when it
   cannot be evaluated. `True` without consulting `request` is the exact shape of `AUTHZ-006` and
   must never reappear (§0.2.2 rule 1).
3. **The contract lives in a decision record and is enforced by a registry-iterating test, not by a
   mixin.** A base class answers "how is the role read?"; the contract answers "what may `is_staff`
   do?" — **one answer, in `docs/`, with the test as its executable form.**
4. **The contract test must iterate `admin.site._registry` and use real permission calls.** A
   `getsource` test cannot see a contract expressed as an absence (§1.5), and reading `admin.py` in
   isolation produces 14/17 instead of the correct 12/17 because the changelist gate is the
   **disjunction** `has_view_or_change_permission` (F7). **Three auditors have now been misled by
   that misreading; the test must not repeat it.**
5. **The contract test never POSTs and never mutates.** See the U4 hazard above. It answers
   permission questions against a constructed `RequestFactory` request per identity.
6. **`apps/users/admin.py` is not edited.** Phase 04 BLOCK 1 owns the field contract, with
   `PII-103` merged in; phase 06 must not patch it again. **This block audits the permission
   predicate and changes nothing in that file** unless GATE Q3's answer requires it, and even then
   the field set stays phase 04's.
7. **`apps/ads/admin.py` is not edited.** Phase 05 BLOCK 6 owns the field set; phase 15 owns the
   permission predicate — and the *predicate* needs no edit here, because the recommended
   reconciliation is at the `AdminSite` and `media_gate` level, not per class.
8. **The `AUTHZ-003` finding is not closed until `04-AUT-005` has landed.** The commit body and the
   decision record both say so.
9. **`apps/ads/views/listings.py` is a shared file** (phase 05 §5.2, phase 10 BLOCKs 14/15). **Only
   `media_gate`'s staff branch is touched.** The non-staff branch's `ad__user__is_declined=False`
   filter is **read-only** and is phase 08's `SRCH-004` surface — **do not touch it.**
10. **The GATE Q9 band decision is recorded, not made.** The commit body states the residual and the
    combined-pair band, and does not re-band.
11. **No migration, no model field, no fixture in `conftest.py`.** If a contract test needs a
    moderator, construct one; do not add a fixture to the most contended file in the repository.

**Implementor task**

```yaml
id: task_15_b09_admin_role_and_moderator_contract
title: "Resolve the ADMIN role in one place, reconcile the admin site, and write the moderator contract down once (AUTHZ-003 validated 2026-09)"
priority: high
depends_on: []
source_reference: ".ai/plans/15-authorization-remediation.md"
source_section: "BLOCK 9 - One role resolver, one moderator contract, and the registry test that enforces it"
source_blocks: ["BLOCK 9"]
description: >
  Four answers to "is this ADMIN" - AdminSite.has_permission (is_active and is_staff, Django's, not
  overridden here), User.role (is_staff or is_superuser), staff_required (role == ADMIN) and
  media_gate's raw request.user.is_staff - disagree for a superuser who is not staff, and the
  UserAdmin ladder is inverted. Point media_gate at User.role, reconcile the admin site's permission
  answer with the role, write down what a plain is_staff moderator may do, and enforce that contract
  with a test that iterates admin.site._registry and makes real permission calls. Do NOT add a shared
  ModelAdmin base class: seven admin classes are read-only by deliberate data-protection policy and
  a uniform grant would turn an audit trail into a mutable table.
goals:
  - "media_gate answers identically to staff_required for a superuser who is not staff"
  - "the admin site's permission answer and User.role agree, per the written Q3' answer"
  - "the moderator contract is written once, as a decision record in docs/, with its stated answer"
  - "a test iterating admin.site._registry asserts the contract by making real permission calls for each identity"
  - "the four report errors that are not errors - the 'not deployable' claim, the 15-of-17 arithmetic, the 422 claim, the field counts - are absent from the commit body"
extra_context: |
  GATES THAT MUST BE ANSWERED IN WRITING BEFORE IMPLEMENTATION: Q3 (what may is_staff do - owner and
  product), Q3' (which route reconciles AdminSite.has_permission with User.role - note this cannot be
  answered before U13 is verified), and Q9 (the band - coordinator, non-blocking for the code, but the
  re-band must NOT let the 04-AUT-005 escalation disappear). The Implementor is forbidden from
  choosing an option.
  EXTERNAL PREREQUISITE: phase 04 BLOCK 1 must have landed. AUTHZ-003 cites 04-AUT-005 (with PII-103
  merged in) as a hard prerequisite and MUST NOT be closed without it.
  BINDING CONSTRAINTS
  1. NO AdminRolePermissionMixin, NO shared base class, NO blanket grant. This is a PROHIBITION, not
     an option (VAL-005). Seven classes are read-only by deliberate data-protection policy:
     AnalyticsEventAdmin, ModeratorActionLogAdmin, ConsentRecordAdmin, LoginTokenAdmin,
     SupportTicketAdmin, SiteConfigAdmin, AdImageAdmin. A uniform grant turns an audit trail into a
     mutable table and a consent record into an editable one - a strictly larger incident than the
     one this finding fixes.
  2. Deny by default. Any new permission answer consults request and returns False when it cannot be
     evaluated. True without consulting request is the exact shape of AUTHZ-006.
  3. The contract lives in a decision record and is enforced by a registry-iterating test, NOT by a
     mixin. A base class answers "how is the role read?"; the contract answers "what may is_staff
     do?".
  4. The contract test must iterate admin.site._registry and make REAL permission calls. A
     getsource test cannot see a contract expressed as an absence, and reading admin.py in isolation
     yields 14/17 instead of the correct 12/17 because the changelist gate is the DISJUNCTION
     has_view_or_change_permission. Three auditors have been misled by that.
  5. THE CONTRACT TEST NEVER POSTS AND NEVER MUTATES. A POST that omits an unchecked BooleanField
     silently clears is_staff, de-staffing the actor mid-test and making later assertions fail
     spuriously. Answer permission questions against a constructed request per identity.
  6. apps/users/admin.py is NOT edited for its field set - phase 04 BLOCK 1 owns that, with PII-103
     merged in. apps/ads/admin.py is NOT edited - phase 05 BLOCK 6 owns AdAdmin's field set. This
     block changes the permission PREDICATE, and only where the GATE Q3' answer says.
  7. In apps/ads/views/listings.py, ONLY media_gate's staff branch is touched. The non-staff
     branch's ad__user__is_declined=False filter is READ-ONLY and is phase 08's SRCH-004 surface.
  8. The GATE Q9 band is recorded, not made. The commit body states the residual band and the
     combined AUTHZ-003 + 04-AUT-005 pair's band, and does not re-band.
  9. Verify U13 FIRST: does create_admin_user exist, and does it set both is_staff and is_superuser?
     If it does not, option (ii) has no enforcement point and only option (i) is coherent. Record the
     answer in the gate.
  10. Measure U5 here: UserAdmin.get_form(request).base_fields and AdAdmin's. Do not take any field
      count on trust from any document. Record the measured numbers; change no field set.
  11. No migration, no model field, no fixture added to src/backend/conftest.py. Construct identities
      in the test.
  12. media_gate calls request.user.role, NOT a new resolve_admin_role indirection. At two call
      sites the property IS the resolver, and a new indirection is an abstraction without
      justification. Do not create a third consumer to justify one.
  CITATION: "AUTHZ-003 (validated 2026-09)".
files:
  - path: src/backend/apps/ads/views/listings.py
    targets:
      - type: function
        name: media_gate
    changes:
      - "The staff branch consults request.user.role == UserRole.ADMIN instead of raw request.user.is_staff. Nothing else in the function changes."
  - path: <GATE Q3' decides: the project AdminSite subclass and its AppConfig, or the provisioning route>
    targets:
      - type: class
        name: AdminSite
    changes:
      - "Reconcile the admin site's permission answer with User.role, per the written gate answer."
  - path: docs/<GATE Q3 decides the home>
    targets:
      - type: document
        name: moderator-contract
    changes:
      - "One decision record: what a plain is_staff moderator may do, per model, and why. Names 04-AUT-005 as a hard prerequisite and states that AUTHZ-003 is not closed without it."
  - path: src/backend/apps/users/tests/test_admin_role_contract.py
    targets:
      - type: module
        name: test_admin_role_contract
    changes:
      - "Iterate admin.site._registry, make real permission calls per identity, and assert the documented contract. Read-only; no POST, no mutation."
changes:
  - action: modify_code
    description: >
      Point media_gate's staff branch at User.role.
  - action: add_code
    description: >
      Add the admin-site reconciliation per the written GATE Q3' answer, and the AppConfig wiring if
      option (i) was chosen.
  - action: add_code
    description: >
      Add the decision record and the registry-iterating contract test.
acceptance_criteria:
  - "media_gate answers identically to staff_required for a superuser who is not staff, asserted through both entry points"
  - "the admin site's permission answer and User.role agree, exactly as the written GATE Q3' answer specifies, and the test names the chosen option"
  - "the decision record states the contract per model, names 04-AUT-005 as a hard prerequisite, and states that AUTHZ-003 is not closed without it"
  - "the contract test iterates admin.site._registry, makes real permission calls for anonymous, seller, plain moderator, superuser and superuser-without-staff, and fails BY CLASS NAME on any divergence"
  - "the contract test never POSTs and never mutates a User row"
  - "no ModelAdmin base class, mixin or blanket grant exists; the seven deliberately read-only classes are unchanged"
  - "apps/users/admin.py's field set and apps/ads/admin.py's field set are unchanged"
  - "media_gate's non-staff branch and its ad__user__is_declined=False filter are byte-identical"
  - "U5's field counts were measured and recorded; no count was taken from a document"
  - "U13's answer is recorded in the gate"
  - "the fast Docker gate is green"
tests_to_run:
  - src/backend/apps/users/tests/test_admin_role_contract.py
  - src/backend/apps/users/tests/test_user_roles.py
  - src/backend/apps/ads/tests/test_media.py
  - src/backend/apps/moderation/tests/test_moderation_views.py
```

**Note on `test_user_roles.py`.** It asserts `set(UserRole) == {ANONYMOUS, SELLER, ADMIN}` and —
critically — that a superuser without `is_staff` resolves to `ADMIN`. **That test already encodes
GATE Q3′'s option (ii) answer.** The plan must **reconcile with it, not overwrite it**: if option
(i) is chosen, `User.role` does not change and the test stays green; if option (ii) is chosen, this
test is the record that makes the invariant visible and is the natural home for the enforcement
assertion. **Which of the two is chosen must be visible in the diff**, or the block looks like it
contradicts a shipped test.

---

### BLOCK 10 — `/login/issue/` stops writing on a `GET` (`AUTHZ-004`)

| | |
|---|---|
| **Findings owned** | `AUTHZ-004` (MEDIUM, band per GATE Q7) · records `VAL-001`'s amendment request |
| **Class** | **behavioural** — route and method change on a route every anonymous redirect targets |
| **Depends on** | nothing in-plan. **Externally:** `apps/users/views/consent.py` and `apps/users/urls.py` are phase 04 BLOCKs 3/4/6's files — one file, sequential passes; phase 04 §5.2 item 2 names the route/method as **phase 15's** to change, having ruled that phase 04 may not |
| **Blocks** | BLOCK 12 (`VAL-001`'s central request is recorded with its evidence) |
| **Priority** | **P1.** Two gates, one of which is an **owner/product** decision about deep-link UX |
| **Risk level** | **MEDIUM** — the amplification is bounded at two layers, but the change is **user-visible** and touches a route whose URL appears in `LOGIN_URL` |
| **Blast radius** | **4 test files / 10 call sites** (C-1) · `apps/users/views/consent.py::login_issue` · `apps/users/urls.py` · `users/login_issue.html` |
| **Required agents** | **Auditor · Researcher · Planner · Validator** — all four |

**The defect, in full.** `login_issue` is registered on a **bare** `path("login/issue/", login_issue,
name="login_issue")` in `apps/users/urls.py` — no `csrf_exempt`, no name-level protection — and is
decorated with **`@never_cache` only**: no `@require_POST`. Its body is two rate-limit checks
(`check_deep_link_render_rate_limit` → 429, `login_rate_limit_check` → 429) followed by an
**unconditional** `issue_token()`, then a `render` of `users/login_issue.html` with the raw token in
the context. Two anonymous `GET`s insert two `LoginToken` rows with no CSRF token supplied.

**Why MEDIUM is the right band, and why the band is still gated.** A literal reading of the
handbook's §8 CRITICAL entry — *"state-changing web request accepted without a valid CSRF token"*,
with no method restriction — would band this CRITICAL. The MEDIUM band rests on four facts: no
identity, session or protected resource is affected; the token is a **bearer credential that must
still be claimed by a Telegram identity**; it **expires in 5 minutes**; and the amplification is
bounded at **two** layers — the two in-app rate limits and nginx's `location /login/` block with
`limit_req … burst=20 nodelay` keyed on `$binary_remote_addr` (U12). **GATE Q7 is the audit
programme's ruling, not phase 15's**, and it must be made once and applied to every phase that finds
a state-changing `GET`. **The recommended amendment, recorded for that ruling and not applied here:**
*"state-changing request (any method) that mutates state without a CSRF token, where the mutation
affects an authenticated identity or a protected resource."*

**GATE Q8 — the deep-link UX.** `LOGIN_URL = "/login/issue/"`, so this route is also the
`@login_required` redirect target. A `GET` deep link from a bookmark, a messenger preview or a
headless client must degrade gracefully once the route is POST-only. **Phase 04's plan names this as
the reason phase 04 may not add `@require_POST`; phase 15 may, but only with the UX decided.**

| Option | Shape | User experience | Project convention | Consequence if wrong |
|---|---|---|---|---|
| (a) | `@require_POST` + CSRF, with the **landing page rendering a form** that posts to the same URL; a `GET` returns 405 with a translated, actionable page | A bookmarked or messaged deep link shows a button the user presses once | ✔ one route, one template, one new form | The extra hop is real. **The mitigation is that the 405 page is not a dead end** — it must render the form, not an error |
| (b) | Split: `GET /login/issue/` renders the landing page **without issuing a token**; `POST /login/issue/` issues it | The deep link still lands on a page, and the token is only minted on intent | ✔ cleanest separation; the deep-link UX is **unchanged** | **Two behaviours on one URL**, and `LOGIN_URL` still points at the `GET`. The landing template currently receives the **raw token**, so it must stop — which means the page can no longer render a Telegram deep link on first load without a press |
| (c) | Keep `GET` and add `@csrf_protect` | Nothing changes for the user | ✔ smallest diff | **A `GET` with a CSRF token still writes, and no deep link carries one.** It does not fix the finding |

**Options (a) and (b) both fail closed** — no token without a protected `POST`. **The Implementor may
not choose.**

**Binding constraints**

1. **No token is issued on `GET`, by any route, ever.** If option (b) is chosen, the `GET` renders a
   landing page with **no `raw_token` in its context**. The `csrf` cookie, the `next` parameter and
   the `lang` parameter all survive.
2. **Both rate limits still apply on the `POST`**, and the `429` behaviour is unchanged. The
   in-app `check_deep_link_render_rate_limit` and `login_rate_limit_check` are not weakened, and
   nginx's `limit_req` is not touched.
3. **The bot's `/start login_<token>` handshake is unchanged.** The consume path is in
   `apps/users/services/login_token.py`, which is **phase 04's file** — **record only, do not edit.**
4. **The real blast radius is 4 files / 10 call sites, and the report's file list is wrong** (C-1):
   `apps/users/tests/test_login.py::TestLoginIssue` (5 tests) **plus 2 more `client.get("/login/issue/")`
   calls inside the `login_status` tests**; `apps/ads/tests/test_auth_nav.py::test_login_issue_renders_header`;
   `apps/core/tests/test_contact_rate_limit.py::test_login_issue_returns_429_when_rate_limited`; and
   `apps/core/tests/test_login_issue_template.py`, which reads the template **as text** and never
   issues a request. **All four are in `tests_to_run`.** **`apps/users/tests/test_login_issue_template.py`
   does not exist — do not create it.**
5. **The `apps/core` template test's three assertions must survive** the new form: `{% telegram_deep_link %}`
   present, no cleartext bot username, deep-link button not hidden on load. **If the new POST form
   means the deep link is only reachable after a press, the correct response is to change the
   template's design under GATE Q8's answer — not to weaken the assertion.** A change there is a
   **contract change**, so name it in the commit body.
6. **Every assertion of the form `assert response.url.startswith("/login/issue/")` is about the
   redirect target, not the method, and survives.** Those are in `test_cabinet_sections.py` (4 sites),
   `test_logout.py`, `test_consent.py` and `test_saved_search_create.py::test_requires_login` — they
   are in `tests_to_run` for that reason. **What breaks is the ~10 sites that GET the route directly
   and expect `200`.**
7. **Any new user-visible string** is wrapped in `{% trans %}` / `gettext` with **non-empty `ru` and
   `bs`** `msgstr`, and `test_i18n_completeness.py` is green. This block is one of only two in the
   phase that may add a user-visible string.
8. **`@never_cache` stays.** Removing it is not part of this finding and would re-introduce a
   caching hazard on a page that carries a raw token.
9. **Re-read `consent.py` and `urls.py` immediately before editing.** Phase 04 BLOCKs 3, 4 and 6 all
   edit `consent.py` — **one file, sequential passes, never parallel.** Stop and report on a
   concurrent change.
10. **Do not add `@require_POST` to `/login/status/`, `/logout/`, `/consent/*` or anything else.**
    One route, one change.

**Implementor task**

```yaml
id: task_15_b10_login_issue_requires_post
title: "Stop GET /login/issue/ from writing: move token issuance behind a CSRF-protected POST, with a graceful deep-link landing (AUTHZ-004 validated 2026-09)"
priority: high
depends_on: []
source_reference: ".ai/plans/15-authorization-remediation.md"
source_section: "BLOCK 10 - /login/issue/ stops writing on a GET"
source_blocks: ["BLOCK 10"]
description: >
  login_issue is registered on a bare path with @never_cache only - no @require_POST, no csrf_exempt -
  and calls issue_token() unconditionally after two rate-limit checks, so two anonymous GETs insert two
  LoginToken rows with no CSRF token supplied. Move token issuance behind a CSRF-protected POST and
  make the deep-link landing degrade gracefully, because LOGIN_URL points at this route and every
  anonymous @login_required redirect lands on it. Note the real blast radius: four test files and ten
  call sites, not the two files the source report names - apps/users/tests/test_login_issue_template.py
  does not exist and must not be created.
goals:
  - "no LoginToken row is created by any GET, with or without a CSRF cookie"
  - "the CSRF-protected POST issues exactly one token, and both rate limits still apply on it"
  - "a deep link, a bookmark and a messenger preview degrade to an actionable page rather than a dead end"
  - "the bot's /start login_<token> handshake is unchanged"
  - "all four affected test files and all ten call sites are updated or confirmed green, and every login_required redirect assertion still holds"
extra_context: |
  GATES THAT MUST BE ANSWERED IN WRITING BEFORE IMPLEMENTATION: Q8 (the deep-link UX - owner and
  product) and Q7 (VAL-001's CSRF band - the audit programme, non-blocking for the code, blocking for
  the tracker). The Implementor is forbidden from choosing an option.
  BINDING CONSTRAINTS
  1. No token is issued on GET, by any route, ever. If the gate answer renders a landing page on
     GET, that page carries no raw_token in its context. The csrf cookie, the next parameter and the
     lang parameter all survive.
  2. Both rate limits still apply on the POST and the 429 behaviour is unchanged. check_deep_link_render_rate_limit
     and login_rate_limit_check are not weakened, and nginx's limit_req is not touched.
  3. apps/users/services/login_token.py is READ-ONLY - it is phase 04's file. The bot's
     /start login_<token> handshake is unchanged.
  4. THE REAL BLAST RADIUS IS 4 FILES / 10 CALL SITES: test_login.py::TestLoginIssue (5 tests) plus 2
     more client.get("/login/issue/") calls inside the login_status tests; test_auth_nav.py::test_login_issue_renders_header;
     test_contact_rate_limit.py::test_login_issue_returns_429_when_rate_limited; and
     apps/core/tests/test_login_issue_template.py. apps/users/tests/test_login_issue_template.py DOES
     NOT EXIST - do not create it, and do not budget for it.
  5. The apps/core template test's three assertions must survive: {% telegram_deep_link %} present, no
     cleartext bot username, deep-link button not hidden on load. If the gate answer means the deep
     link is only reachable after a press, change the template's DESIGN under the gate answer - never
     weaken the assertion. Name the contract change in the commit body.
  6. Assertions of the form assert response.url.startswith("/login/issue/") are about the redirect
     TARGET, not the method, and survive unchanged. They are in test_cabinet_sections.py (4 sites),
     test_logout.py, test_consent.py and test_saved_search_create.py::test_requires_login.
  7. Every new user-visible string is wrapped in {% trans %}/gettext with NON-EMPTY ru and bs msgstr,
     and test_i18n_completeness.py is green. Append to the catalogue; never regenerate.
  8. @never_cache STAYS. Removing it is not part of this finding and would re-introduce a caching
     hazard on a page that carries a raw token.
  9. Re-read consent.py and urls.py immediately before editing. Phase 04 BLOCKS 3, 4 and 6 all edit
     consent.py - one file, sequential passes, never parallel. Stop and report on a concurrent change.
  10. Do NOT add @require_POST to /login/status/, /logout/, /consent/* or anything else. One route,
      one change.
  11. Record the VAL-001 amendment request in the commit body for the coordinator. Do not apply it and
      do not re-band locally.
  CITATION: "AUTHZ-004 (validated 2026-09)".
files:
  - path: src/backend/apps/users/views/consent.py
    targets:
      - type: function
        name: login_issue
    changes:
      - "Token issuance moves behind a CSRF-protected POST, per the GATE Q8 answer. @never_cache stays."
  - path: src/backend/apps/users/urls.py
    targets:
      - type: url_pattern
        name: login_issue
    changes:
      - "Only if the GATE Q8 answer requires a second pattern. LOGIN_URL is not changed."
  - path: src/backend/templates/users/login_issue.html
    targets:
      - type: template
        name: login_issue
    changes:
      - "The CSRF-protected form and its submit control, wrapped in {% trans %}. The deep-link assertions in apps/core/tests/test_login_issue_template.py must survive."
  - path: src/backend/apps/users/tests/test_login.py
    targets:
      - type: class
        name: TestLoginIssue
    changes:
      - "Move the issuing calls to POST; assert that GET creates no LoginToken row. Update the two login_status tests that GET the route."
  - path: src/backend/apps/ads/tests/test_auth_nav.py
    targets:
      - type: method
        name: test_login_issue_renders_header
    changes:
      - "Follow the GATE Q8 answer; the header assertion is unchanged."
  - path: src/backend/apps/core/tests/test_contact_rate_limit.py
    targets:
      - type: method
        name: test_login_issue_returns_429_when_rate_limited
    changes:
      - "Exercise the rate limit on the method that now issues."
changes:
  - action: modify_code
    description: >
      Move token issuance behind a CSRF-protected POST and make the deep-link landing actionable.
  - action: modify_code
    description: >
      Add the CSRF-protected form to the landing template with translated strings.
  - action: modify_code
    description: >
      Update all four affected test files and all ten call sites, and add the positive control that a
      GET creates no LoginToken row.
acceptance_criteria:
  - "a GET with and without a CSRF cookie creates zero LoginToken rows, asserted by row count"
  - "the CSRF-protected POST creates exactly one row, and both rate limits still return 429 on the method that issues"
  - "a deep link, a bookmark and a messenger preview reach an actionable page, not a dead end"
  - "the three assertions in apps/core/tests/test_login_issue_template.py are green and no assertion in it was weakened"
  - "every login_required redirect assertion still startswith /login/issue/ - test_cabinet_sections.py (4 sites), test_logout.py, test_consent.py, test_saved_search_create.py"
  - "the bot's /start login_<token> handshake is unchanged and apps/users/services/login_token.py is byte-identical"
  - "@never_cache is still present on login_issue"
  - "no new user-visible string lacks a non-empty ru and bs msgstr; test_i18n_completeness.py is green"
  - "the commit body records the VAL-001 amendment request and both gate answers"
  - "the fast Docker gate and the bot suite are both green"
tests_to_run:
  - src/backend/apps/users/tests/test_login.py
  - src/backend/apps/ads/tests/test_auth_nav.py
  - src/backend/apps/core/tests/test_contact_rate_limit.py
  - src/backend/apps/core/tests/test_login_issue_template.py
  - src/backend/apps/cabinet/tests/test_cabinet_sections.py
  - src/backend/apps/users/tests/test_logout.py
  - src/backend/apps/users/tests/test_consent.py
  - src/backend/apps/search/tests/test_saved_search_create.py
  - src/backend/apps/core/tests/test_i18n_completeness.py
```

---

### BLOCK 11 — The moderation surface phase 10 routed here (`Q11`, `Q12`)

| | |
|---|---|
| **Findings owned** | **No `AUTHZ-` finding.** Two questions **routed by phase 10** to phase 15 |
| **Class** | **conditional** — ships nothing if its gates are declined or unanswered |
| **Depends on** | BLOCK 3 (soft — it is the same consistency question, one file over). **Externally:** phase 10's routing; `apps/moderation/views/api_bulk.py` is read-only |
| **Blocks** | nothing |
| **Priority** | **P2.** These are live questions, already routed, and not in the validated report — which is exactly why they are easy to lose |
| **Risk level** | **MEDIUM** — a 302→405 change is **user-visible** and breaks recorded behaviour |
| **Blast radius** | `apps/moderation/views/review.py` (`reject_ad`, `ban_user`) |
| **Required agents** | **Auditor · Planner · Validator** |

**Why this block exists at all.** Phase 10's §5.2 routes two moderation-surface behaviour decisions
to phase 15: **Q2** (what an invalid `reason_category` does in `reject_ad`) and **Q4** (whether a
`GET` on `reject_ad` / `ban_user` is a 302 or a 405). **Neither is in the validated report**, and
both are live in the tree. **This block records that phase 15 holds them, and it is the last place
they can be recorded before they are lost.**

**Q12 — the method check.** `reject_ad` and `ban_user` both use an **inline**
`if request.method != "POST": return redirect(...)`, which returns **302**. Their sibling
`approve_ad` already uses `@require_POST` and returns **405**. **Two shipped tests assert the 302.**

| Option | Shape | Maintains | Project convention | Consequence if wrong |
|---|---|---|---|---|
| (a) | Replace both inline checks with `@require_POST` | All three moderation actions answer 405 for a non-POST | ✔ matches `approve_ad`, `ad_archive`, `ad_reactivate`, `ad_delete` | **A 302 becomes a 405 — user-visible, and it breaks two shipped tests** whose assertions change under project rule 2. A bookmarked or crawled `GET` on a moderation action goes from "quietly redirects" to "405" |
| (b) | Keep 302 and make `approve_ad` match | 302 everywhere | ✘ the codebase's dominant order is `@require_POST` first, and a 302 on a non-POST action is a **CSRF-adjacent smell**: a browser can be navigated to a mutating URL | **Reversing a sibling that already does the right thing, in a file phase 10 also touches** |
| (c) | Leave both | Nothing | — | **The inconsistency is permanent and undocumented.** Two shipped tests keep pinning a 302, and the next auditor re-discovers it |

**Q11 — the `reason_category` validation.** Today **any** client string is concatenated into
`ModeratorActionLog.reason`.

| Option | Shape | Maintains | Project convention | Consequence if wrong |
|---|---|---|---|---|
| (a) | Validate `reason_category` against a closed vocabulary and reject the request on an unknown value | The audit log stops accepting arbitrary client text | ✔ fixed values via `StrEnum` (project rule 10) | **An existing caller sending a free-text reason starts failing.** The 302-on-GET behaviour and the moderation review flow must be checked for a client that sends a free-text reason |
| (b) | Validate and **normalise** to a known value, keeping the free text in a separate, redacted field | No caller breaks | ⚠ phase 06 BLOCK 16 owns `reason` **redaction** in `admin_actions.py` — a two-field split touches that | **Overlaps phase 06's redaction work.** Listed so the collision is visible, not to create it |
| (c) | Leave it | Nothing | ✘ | **An audit record accepts arbitrary client-controlled text**, which is the class of defect phase 06's redaction work exists to close |

**Binding constraints**

1. **Both gates must be answered in writing, and a decline is a valid answer.** **If either is
   declined or unanswered, this block ships nothing and that is recorded, not worked around.**
2. **`apps/moderation/views/api_bulk.py` is read-only.** Phases 09 and 10 both forbid touching it.
3. **`apps/moderation/admin_actions.py` is not edited** — it is five-way contended and phase 10
   BLOCK 12 **moves** it. A `reason_category` change that would touch `ModeratorActionLog.reason`
   construction in that module **overlaps phase 06 BLOCK 16's redaction** and must be escalated
   rather than implemented here.
4. **A 302→405 change is user-visible and breaks recorded behaviour.** The two shipped 302
   assertions change in the same commit under project rule 2, cited by name, **or the change does
   not ship**. No other option is legitimate.
5. **No `is_banned` / `is_declined` / `consent_revoked` semantics change**, and nothing touches the
   account-state declaration. This block is about a **method check** and an **input vocabulary**.
6. **No new user-visible string without `ru` and `bs` translations.** A rejected `reason_category`
   returning a 400 is a new user-visible response.

**Implementor task**

```yaml
id: task_15_b11_moderation_surface_questions
title: "Answer and apply phase 10's two routed moderation-surface questions, or ship nothing (Q11 + Q12, routed by phase 10)"
priority: medium
depends_on: []
source_reference: ".ai/plans/15-authorization-remediation.md"
source_section: "BLOCK 11 - The moderation surface phase 10 routed here"
source_blocks: ["BLOCK 11"]
description: >
  Phase 10 routed two moderation-surface behaviour decisions to phase 15 and neither appears in the
  validated report. Q12: reject_ad and ban_user use an inline method check returning 302 while their
  sibling approve_ad already uses @require_POST and returns 405, and two shipped tests assert the
  302. Q11: any client string is concatenated into ModeratorActionLog.reason, so an audit record
  accepts arbitrary client-controlled text. Both gates must be answered in writing; a decline is a
  valid answer and this block then ships nothing.
goals:
  - "both gate answers are written down before any code changes"
  - "if Q12 is approved, all three moderation actions answer 405 for a non-POST and the two shipped 302 assertions change in the same commit under project rule 2"
  - "if Q11 is approved, reason_category is validated against a closed vocabulary and an unknown value is refused"
  - "if either gate is declined or unanswered, nothing is shipped and the decision is recorded"
extra_context: |
  GATES THAT MUST BE ANSWERED IN WRITING BEFORE IMPLEMENTATION: Q11 and Q12. A decline is a valid
  answer; if either is declined or unanswered THIS BLOCK SHIPS NOTHING and that is recorded, not
  worked around. The Implementor is forbidden from choosing an option.
  BINDING CONSTRAINTS
  1. Both gate answers are recorded before any code change.
  2. apps/moderation/views/api_bulk.py is READ-ONLY. Phases 09 and 10 both forbid touching it.
  3. apps/moderation/admin_actions.py is NOT edited. It is five-way contended and phase 10 BLOCK 12
     MOVES it. Any reason_category change that would touch ModeratorActionLog.reason construction
     there overlaps phase 06 BLOCK 16's redaction - ESCALATE rather than implement.
  4. A 302-to-405 change is USER-VISIBLE and breaks recorded behaviour. The two shipped 302
     assertions change in the SAME commit under project rule 2, cited by name, or the change does
     not ship. No other option is legitimate.
  5. No account-state semantics change. Nothing touches the account-state declaration or the gate.
     This block is about a METHOD CHECK and an INPUT VOCABULARY.
  6. No new user-visible string without non-empty ru and bs msgstr.
  7. Do not reverse approve_ad to 302. The codebase's dominant order is @require_POST first, and a
     302 on a non-POST mutating action is a CSRF-adjacent smell. Option (b) is listed so the choice
     is on the record, not because it is a candidate.
  CITATION: "phase 10 Q2 and Q4, routed to phase 15; not an AUTHZ finding".
files:
  - path: src/backend/apps/moderation/views/review.py
    targets:
      - type: function
        name: reject_ad
      - type: function
        name: ban_user
    changes:
      - "Only per the written GATE Q12 answer. Nothing changes if the gate is declined."
  - path: src/backend/apps/moderation/tests/test_moderation_views.py
    targets:
      - type: class
        name: TestModerationReviewLocking
    changes:
      - "The two shipped 302 assertions change in the same commit under project rule 2, if and only if Q12 is approved. The structural lock assertions are never weakened."
changes:
  - action: modify_code
    description: >
      Apply the GATE Q12 and GATE Q11 answers, or change nothing.
  - action: modify_code
    description: >
      Update the two shipped 302 assertions in the same commit, citing project rule 2 by name, if and
      only if Q12 is approved.
acceptance_criteria:
  - "both gate answers are recorded in the commit body before any code change"
  - "if Q12 is approved: all three moderation actions answer 405 for a non-POST, and the two shipped 302 assertions changed in the same commit with project rule 2 cited by name"
  - "if Q12 is declined: review.py is byte-identical and the decision is recorded"
  - "if Q11 is approved: reason_category is validated against a closed vocabulary and an unknown value is refused with a translated message"
  - "if Q11 is declined: the free-text behaviour is unchanged and the decision is recorded"
  - "apps/moderation/views/api_bulk.py and apps/moderation/admin_actions.py are byte-identical"
  - "TestModerationReviewLocking's structural assertions are green and unmodified"
  - "the fast Docker gate is green"
tests_to_run:
  - src/backend/apps/moderation/tests/test_moderation_views.py
  - src/backend/apps/moderation/tests/test_admin_actions.py
```

---

### BLOCK 12 — Documentation parity, and the tracker record (`VAL-001` request, `VAL-003`, `VAL-004`)

| | |
|---|---|
| **Findings owned** | `VAL-001` (request only) · `VAL-003` (record only) · `VAL-004` (consolidation) · the documentation this phase causes |
| **Class** | **structural** — it makes a decision and a contract *durable* |
| **Depends on** | **every code block.** It runs **last** (§4.2) |
| **Blocks** | nothing |
| **Priority** | **P0 as the last block.** Documentation describing a system the phase has not finished changing is an encoded lie — the same rule phase 12 and phase 13 both applied |
| **Risk level** | **LOW** |
| **Blast radius** | `docs/` only. **No `src/` file, no test, no settings change** |
| **Required agents** | **Auditor · Planner · Validator** (no Researcher: this block runs no verification, it records what earlier blocks measured) |

**What this block does, and — more importantly — what it does not.**

| Item | Action | Why |
|---|---|---|
| **The `technical-specification.md` collision (C-4, Q13)** | **Record the request. Do not edit the file.** The document states *"No web-side middleware redirects soft-deleted users"*, which BLOCK 6 falsifies on the day it lands. **Phase 06 holds the file** (`PII-113`; phase 06 BLOCKs 4/11/14) | A documented divergence is an acceptable outcome; a unilateral edit is not. **The request must be specific enough that phase 06 can act on it without re-deriving anything**: name the sentence, name BLOCK 6, name the gate, and state that the sentence is now false for **four** account states and not one |
| **`VAL-001`'s CSRF band (Q7)** | **Record the amendment request verbatim, with its evidence. Do not apply it, and do not re-band locally** | It must be ruled once, centrally, and applied to every phase that finds a state-changing `GET`. A local ruling will be cited by every later phase and will be wrong in a different direction each time |
| **`VAL-003`'s field counts** | Record **U5's measured** numbers and state plainly that the report's `25` / `29` were stale | These lines were the *evidence* for a not-re-filed decision. Stale numbers weaken an otherwise clean boundary statement, and the whole point of `VAL-003` is that no count should be taken on trust |
| **`VAL-004`'s prefix collision** | Consolidate the phase-qualified-key requirement **once**, here, rather than restating it per phase as `04-VAL-002`, `05-VAL-005` and `08-VAL-005` have each done | Four phases have filed the same requirement. The shipped in-source `AUTZ-003` marker means the handbook prefix is burned; `AUT-001/002/003` are additionally in use as bare identifiers. **The rule: every key is phase-qualified (`04-AUT-002`, `15-AUTHZ-001`) and a tracker must refuse a bare `AUT-001`** |
| **`docs/99-agent/test-audit-block-f-findings.md:193`** | Promote the recorded coverage gap to a **live assertion** pointing at BLOCK 7's test | The line reads *"No test for `can_publish_ad` when `is_declined=True`"*. **Adding that test before BLOCK 7 would have pinned the wrong answer** — the predicate had to change first. Now that it has, the line should name the assertion that locks in the corrected behaviour, so a future audit does not re-discover it |
| **The authorization architecture surface** | Update the agent-facing architecture/rules documentation **only if** it names the middleware stack or the admin permission contract | Project rule 14 and `docs/00-overview/doc-maintenance-rules.md`. **If the documentation does not currently describe the middleware stack, this block creates nothing** — a doc that does not exist is not a doc out of date |
| **The un-verified claims that were never re-derived** | Record every `U1`–`U14` claim that no block re-derived, with its status | §0.2.4 lists them. A claim that was not measured must be recorded as **not measured**, never as a result |

**Binding constraints**

1. **No `src/` file, no test, and no settings file is edited in this block.** If the documentation
   cannot be made true without a code change, **the code change is out of scope** and is escalated.
2. **`docs/01-spec/technical-specification.md` and `docs/01-spec/spec-index.md` are not edited.**
   Both are phase 06's (`PII-113`; `spec-index.md:74` is phase 06 BLOCK 2's sole owner). This block
   records **requests** against both.
3. **No `makemessages` regeneration.** The catalogue is appended to, never regenerated.
   `LOCALE_PATHS` is shared with phases 03/05/06/07/10/11/14.
4. **Every claim recorded here is either measured in an earlier block or labelled
   `not measured`.** No number is carried over from the validated report.
5. **The record is a record.** It states what was decided, by whom, against which gate, and what
   remains open — it does not re-argue the findings.
6. **The plan's own status changes only here.** If every block is green, this block's commit is what
   moves the tracker entries from `planned` to `implemented`, naming any finding that shipped reduced
   (BLOCK 11's decline, BLOCK 8's metrics limb) **as reduced and open, with its named owner.**

**Implementor task**

```yaml
id: task_15_b12_documentation_parity_and_tracker
title: "Make the documentation and the tracker true after the code has landed (VAL-001 request, VAL-003, VAL-004, and the spec collision)"
priority: medium
depends_on: ["task_15_b11_moderation_surface_questions"]
source_reference: ".ai/plans/15-authorization-remediation.md"
source_section: "BLOCK 12 - Documentation parity, and the tracker record"
source_blocks: ["BLOCK 12"]
description: >
  Phase 15 causes four documentation and tracker facts to become true or false, and one of them is a
  collision no earlier plan records: docs/01-spec/technical-specification.md states "No web-side
  middleware redirects soft-deleted users", which BLOCK 6's gate falsifies on the day it lands, and
  phase 06 holds the file. Record a specific request against that file and against spec-index.md's
  DECLINE sentence; record the VAL-001 CSRF band amendment as a central request without applying it
  or re-banding locally; record U5's measured field counts; consolidate the phase-qualified-key
  requirement once; and promote the prior record's can_publish_ad/is_declined coverage gap to a live
  assertion pointing at BLOCK 7's test.
goals:
  - "the phase-06 requests are specific enough to act on without re-deriving anything"
  - "no source file, test or settings file is edited in this block"
  - "every recorded number is either measured in an earlier block or labelled not measured"
  - "the tracker record names every finding that shipped reduced, with its named owner"
extra_context: |
  BINDING CONSTRAINTS
  1. No src/ file, no test, and no settings file is edited in this block. If the documentation cannot
     be made true without a code change, the code change is out of scope - escalate it.
  2. docs/01-spec/technical-specification.md and docs/01-spec/spec-index.md are NOT edited. Both are
     phase 06's (PII-113; spec-index.md is phase 06 BLOCK 2's sole owner). Record REQUESTS against
     both. A documented divergence is acceptable; a unilateral edit is not.
  3. No makemessages regeneration. The catalogue is appended to, never regenerated, and is shared
     with phases 03/05/06/07/10/11/14.
  4. Every recorded number is either measured in an earlier block or labelled "not measured". No
     number is carried over from the validated report.
  5. The record states what was decided, by whom, against which gate, and what remains open. It does
     not re-argue the findings.
  6. The tracker record names every finding that shipped reduced - BLOCK 11's declined gates, BLOCK
     8's metrics limb - as reduced AND OPEN, with its named owner. Do not mark a finding closed
     because a gate was declined.
  7. The spec-collision request must name the exact sentence, name BLOCK 6 and the gate, and state
     that the sentence is now false for four account states and not one.
  8. If the agent-facing architecture documentation does not currently describe the middleware stack
     or the admin permission contract, this block creates nothing. A doc that does not exist is not a
     doc out of date.
  CITATION: "VAL-001, VAL-003, VAL-004 (validated 2026-09)".
files:
  - path: docs/99-agent/test-audit-block-f-findings.md
    targets:
      - type: document
        name: test-audit-block-f-findings
    changes:
      - "Promote the can_publish_ad/is_declined coverage gap to a live assertion naming BLOCK 7's test."
  - path: <GATE/ownership decides: the agent-facing architecture or rules doc>
    targets:
      - type: document
        name: architecture
    changes:
      - "Only if it currently names the middleware stack or the admin permission contract. Otherwise create nothing."
changes:
  - action: add_code
    description: >
      Record the phase-06 requests against technical-specification.md and spec-index.md, the VAL-001
      amendment request, U5's measured counts, the consolidated phase-qualified-key rule, and the
      tracker status of every finding including the ones that shipped reduced.
acceptance_criteria:
  - "no file under src/ and no settings file was modified in this commit"
  - "docs/01-spec/technical-specification.md and docs/01-spec/spec-index.md are byte-identical"
  - "the phase-06 request names the exact falsified sentence, names BLOCK 6 and the gate, and states that it is now false for four account states and not one"
  - "the VAL-001 amendment is recorded verbatim as a central request, is not applied, and no local re-band was made"
  - "U5's numbers are the measured ones from BLOCK 9, labelled as measured, with the report's stale 25/29 named as stale"
  - "the phase-qualified-key rule is stated once: 04-AUT-002, 15-AUTHZ-001; a bare AUT-001 must be refused; AUTZ- is burned"
  - "docs/99-agent/test-audit-block-f-findings.md names BLOCK 7's live assertion instead of the stale coverage gap"
  - "every finding that shipped reduced is recorded as reduced AND OPEN with its named owner"
  - "every U1-U14 claim not re-derived is recorded as not measured, never as a result"
tests_to_run:
  - src/backend/apps/core/tests/test_i18n_completeness.py
```

---

## 4. Dependency graph

### 4.1 Execution order (the safe serial order)

One Implementor, strictly sequential. Every block is one commit (§1.3). The numbering *is* the
order, and the order answers one question: **what must be true before the next change can be
trusted?**

| # | Block | Findings | Class | Depends on (in-plan) | Gate | Risk |
|---|---|---|---|---|---|---|
| 1 | `DailyAdMetricsAdmin.has_delete_permission` | `AUTHZ-006` | **M** | — | — (R4) | **LOW** |
| 2 | `ad_edit` authorizes on the locked row | `AUTHZ-007` | B | — | external: phase 03 BLOCK 5, phase 05 BLOCKs 2/8 | **MED–HIGH** |
| 3 | `staff_required_api` ordering + challenge | `AUTHZ-008` | B | — | — (R5, R6) | **LOW** |
| 4 | `submit_ad`'s actor guard | `AUTHZ-002` | B | **2** | — (R7) | **MED** |
| 5 | One account-state declaration, two levels | `AUTHZ-001a`, `AUTHZ-005a` | **S** | — | R1 (Q2, ruled) · R8 | **MED–HIGH** |
| 6 | The per-request web gate | `AUTHZ-001b` | **S** | **5** | **Q15, Q1** + Q13 route | **HIGH** |
| 7 | The publish DENY set | `AUTHZ-005b` | B | **6** | **Q4, Q5** (both phase 06) | **MED** |
| 8 | Reason-coded denials | `AUTHZ-009` | B | 6 (soft) | U14 + phase 12 Q5 | LOW–MED |
| 9 | One role resolver + moderator contract | `AUTHZ-003`, `VAL-002` | **S** | — | **Q3, Q3′, Q9** + phase 04 BLOCK 1 | **HIGH** |
| 10 | `/login/issue/` requires POST | `AUTHZ-004` | B | — | **Q8** + **Q7** | MED |
| 11 | Moderation-surface questions | `Q11`, `Q12` | **C** | 3 (soft) | **Q11, Q12** | MED |
| 12 | Documentation parity + tracker | `VAL-001`, `VAL-003`, `VAL-004` | **S** | **all** | — | **LOW** |

`M` = mechanical · `B` = behavioural · `S` = structural · `C` = conditional.

### 4.2 The DAG and why each edge exists

```
  (none) --> [1 analytics admin]              (uncontended; one method; buys a green commit first)
                  |                                   \
  (none) --> [2 ad_edit on the lock]            (external: 03 B5 -> 05 B2/B8)
                  |  \
                  |   \  HARD EDGE
  (none) --> [3 staff_required_api]             \--> [4 submit_ad actor guard]
                  |                                      |
  (none) --> [5 account-state declaration] <----(no edge)--+
                  |  \
                  |   \  HARD EDGE
  (none) --> [9 ADMIN role + moderator contract]  \--> [6 the web gate] --Q15,Q1--> [7 publish DENY set] --Q4,Q5-->
                  |                                                            |                              |
  (none) --> [10 login_issue POST-only]                                        +------> [8 denial reason codes]   |
                                                                                 |                              |
  (none) --> [11 moderation surface] --Q11,Q12-------------------------[everything]--------------------------v
                                                                                                       [12 documentation parity]
```

**Each edge, with the reason it exists:**

| Edge | Kind | Why it exists |
|---|---|---|
| **2 → 4** | **hard, dependency** | ✔ The two findings are **distinct root causes** and must stay distinct IDs, but they compose. `AUTHZ-002`'s guard becomes meaningful only once the caller passes the *actor*; and BLOCK 4's regression test asserts "a non-owner POST is refused **before** `submit_ad` is reached", which is a statement about BLOCK 2's locked-instance check. Running 4 first means its test is written against a snapshot the view has not yet corrected |
| **5 → 6** | **hard, dependency** | ✔ The gate consumes the declaration. It cannot be written, reviewed or tested before it exists. **This is the edge that replaces the report's single-commit recommendation, and it does not weaken it** — see below |
| **6 → 7** | **hard, ordering** | ✔ The publish policy must not move underneath a gate whose own deny behaviour is unpinned. BLOCK 6's acceptance is a per-flag matrix; BLOCK 7 changes a *policy* that the same matrix touches. Changing the bot's publish answer before the web's account-state answer is settled means the first observable symptom of a mistake is a **bot** symptom, which is the harder one to diagnose from a moderator's report |
| **6 → 8** | soft, ordering | ✔ BLOCK 6's gate must be instrumented **on day one** using BLOCK 8's vocabulary, so BLOCK 6 creates the reason enum and BLOCK 8 formalises the shared helper and the ad views. **Soft** — BLOCK 8 is correct in any position after BLOCK 6; it is placed here so the vocabulary is fresh and the ad views have just been edited by BLOCKs 2 and 4 |
| **everything → 12** | **hard, dependency** | ✔ The same rule phase 12 and phase 13 both applied: **the truth sweep lands after every code change it documents.** `technical-specification.md`'s "no web-side middleware redirects soft-deleted users" must be re-described by whoever **owns** the file — phase 06 — and that request is only accurate once BLOCK 6 has landed and its answer is known. **There is no soft variant of this edge** |
| **3 → 11** | soft, ordering | ✔ Same consistency question, one file over. BLOCK 3 fixes a decorator's ordering; BLOCK 11 asks whether two sibling views' inline method checks should match `approve_ad`. **Soft** — BLOCK 11 is correct in any position; it is placed here so both moderation-method decisions are taken by one Implementor with one fresh reading of `review.py` |
| **1, 3, 9, 10** | **no edge** | Four blocks that share no file, no constant and no gate with anything else. `analytics/admin.py`, `moderation/views/decorators.py`, `ads/views/listings.py::media_gate`, `users/{urls,views/consent}.py` — all four are claimed by no other plan. Making them depend on anything would serialise four independently correct blocks behind the phase's three highest-risk ones |
| **9 → 10** | **no edge** | Different subsystems. BLOCK 9's privilege expansion and BLOCK 10's CSRF fix have nothing in common but the word "authorization", and coupling them would make one an hostage to the other |

**On replacing the report's single-commit recommendation (the one substantive deviation in this
plan).** The report requires the predicate extraction, the middleware and the publish refactor in
**one commit**, so the project cannot ship two competing account-state vocabularies. **The split
preserves that invariant exactly**: BLOCK 5 creates the declaration and makes the **bot** its first
consumer; BLOCK 6 adds the **web gate** as the second. **No moment exists at which two vocabularies
coexist, because only one exists from the moment BLOCK 5 lands.** What the split buys is that the
single highest-risk commit in the phase — a gate that terminates live sessions and is user-visible —
is separately reviewable and separately revertable, and that the commit in front of it is reviewable
against one strong criterion: **did any answer change?** The answer must be *no*, for all of them.
The one thing the report's single commit would have bought is that the gate and the extraction are
never separated by another phase's commit; that is handled by §5.3's reservation on
`apps/users/services/account_state.py` and `config/settings/base.py`, not by fusing two changes.

### 4.3 Where there is deliberately **no** edge, and why

| Pair with no edge | Why |
|---|---|
| **5 ↔ 9** | Two different sources of truth for two different questions. The account-state declaration answers "may this account act"; the role resolver answers "may this identity administer". Merging them would produce one predicate that answers two questions badly. **Both are "one declaration" blocks, and that shared shape is the argument for keeping them separate** |
| **1 ↔ everything** | BLOCK 1 is one method in a file no other plan claims. An edge would delay the phase's cheapest commit for no dependency that exists |
| **7 ↔ 9** | BLOCK 7 changes a *seller-facing* publish policy; BLOCK 9 changes an *administrator-facing* role answer. Their only overlap is the word "permission", and BLOCK 9's privilege expansion is the kind of change that should not be in flight when a behaviour change is being verified |
| **BLOCK 5's queryset terms ↔ phases 06/08** | ✔ **There is no edge because there is no predicate to order against.** Phase 15 declares the *terms*; phase 06 builds the `User` audience predicate and phase 08 builds the `Ad` ad-visibility predicate on them. **Phase 15 must not implement either, and neither may infer its semantics from BLOCK 5's declaration** |
| **Q2 option (b) (instance-level only) ↔ anything** | ✔ Recorded for completeness, **not a live option**. Choosing it would reproduce the blocker that has kept `06-VAL-003` and `SRCH-004` owner-blocked for two phases, in a new module. §0.5 R1's row carries the cost so it cannot be re-litigated silently |

### 4.4 The orders that are unsafe

1. **BLOCK 6 before BLOCK 5.** The gate would have to re-derive the flag set itself, which is the
   second-vocabulary defect. Worse, it would be re-derived *in the middleware*, where nothing
   asserts it against the bot's test-pinned formula.
2. **BLOCK 4 before BLOCK 2.** BLOCK 4's regression test asserts that a non-owner POST is refused
   **before** `submit_ad` is reached. Written against the uncorrected snapshot, that assertion is
   describing a race rather than a guard.
3. **Phase 10 BLOCK 16 before BLOCK 4.** ✔ **The single highest-consequence ordering error in the
   programme.** Phase 10's BLOCK 16 description already pre-commits to
   `user_id=request.user.id` and says *"never* `ad.user_id`". If BLOCK 16 lands first, BLOCK 4's
   guard has nothing to fix on the web path — it becomes a permanent tautology that looks correct
   and is protected by a green test. **If phase 10 BLOCK 16 has already landed, BLOCK 4 stops and
   escalates to the coordinator; it does not proceed.**
4. **BLOCK 7 before Q4 and Q5 are answered.** If `PII-105` option (a) landed, the publish gate is the
   **only** control keeping a declined seller from posting. Shipping a widened DENY set without the
   ruling, or shipping it *because* of the ruling without recording the ruling, are both wrong.
5. **BLOCK 9 without `04-AUT-005` landed.** The finding must cite it as a hard prerequisite and
   **must not be closed without it**. A moderator who can self-provision is the live risk, and it is
   phase 04's to fix.
6. **BLOCK 6 editing `technical-specification.md`.** ✔ Phase 06 holds the file. A unilateral edit
   creates a two-owner conflict on the phase's most contested document.
7. **Any block implementing a `ModelAdmin` base class or mixin.** ✔ Not an ordering error but the
   same class: `VAL-005` — it would turn an audit trail into a mutable table.
8. **Any block adding a default-manager filter on `User`.** ✔ It would hide withdrawn users from the
   bot's `_resolve_user` and re-open a hole.
9. **BLOCK 10 budgeting only the two `test_login_issue_template.py` files** (C-1). One does not
   exist; the real blast radius is **4 files / 10 call sites**. The block will go red.
10. **Any block writing `is_banned`, `is_declined` or `consent_revoked` into a listing queryset.**
    That is `SRCH-004` / `SRCH-008`, phase 08's and phase 06's, and Q6's unresolved product question.
11. **Any block restoring `.ai/audit/15-authorization/findings.md`** or editing anything under
    `.ai/audit/`. It is deleted; the validated report is the record.
12. **Any block allocating an `AdvisoryLockId`.** ✔ Phase 15 allocates **none**. R3's `StrEnum` is
    appended to `enums.py` and nothing is reordered.

### 4.5 What the DAG does *not* decide

The DAG orders blocks. It does **not** resolve Q1 … Q15. Each is a `RULED`, a `GATED` gate inside a
block, or `ROUTED` (§0.5), and §8.1 checks that a **written** answer exists for every `GATED` one.
**A block whose gate is unanswered does not start, and the Implementor is forbidden from choosing
the option.**

The DAG also does not sequence phase 15 against the other phases. §5 does, from phase 15's side
only. **Phase 15 does not contact, negotiate with, or wait on any other agent** — the coordinator
sequences the cross-phase gates. **Four of them are externally blocking** and the coordinator must
place them: **phase 03 BLOCK 5 + phase 05 BLOCKs 2/8 → BLOCK 2**; **phase 06's `PII-105` and
`PII-113` → BLOCK 7**; **phase 04 BLOCK 1 → BLOCK 9**; and **phase 15 BLOCK 4 → phase 10 BLOCK 16**.

---

## 5. Cross-phase coordination

**All fourteen earlier plans exist** in `.ai/plans/`. Plans 01 and 02 are `executed`; **03 through 14
are `planned`**, which is precisely why **none** of the nine findings is pre-empted. **Phase 15 is
the last phase in the programme, so this section is the programme's closing integration contract,
not merely a boundary note.** It is deliberately **one-directional**: phase 15 states what it owns,
what it will not touch, and what it must not re-ship. **It does not contact, negotiate with, or wait
on any other agent.** Where this plan records another phase's state, it records only what was
verified in the tree at `ba23277`.

### 5.1 What phases 01–14 already own, and what phase 15 must not re-ship

| Phase | What it owns | Consequence for phase 15 |
|---|---|---|
| **01** | `ENT-001` (the `child_exit` guard, `PROMETHEUS_MULTIPROC_DIR`, the tmpfs, `test_compose_contract.py`) · `ENT-003` (durable daily marker, `send_alerts` idempotency) · `ENT-004` (CI lint/typecheck scoped to `src/`) | **No overlap with any phase-15 block.** Phase 15 ships no compose change, no cron change, and no CI change. **The phase-15 gate's new middleware is inside `src/`, so it is covered by `ENT-004`'s gate — no CI edit is needed or permitted** |
| **02** | `CFG-001` (`ALLOWED_ENV_VARS`, the `DJANGO_ONESHOT` import gate) · `CFG-002` (`ci.yml`'s `deploy-check` env) | ✔ **Phase 15 adds no env key.** `IMMEDIATE_ALERTS_ENABLED` stays `False` and stays in the allowlist (F19). `test_env_allowlist.py` is green in every block. **Phase 15 edits no workflow file at all** |
| **03** | `DB-004` (`statement_timeout` / `lock_timeout`) · `DB-008` (transaction restructuring) · `03-DB-010` (lock behaviour in `admin_actions`) · BLOCK 5 (an `edit.py` pass) · BLOCK 9 (settings) | ✔ **Phase 15 adds no lock and no timeout.** **`03-DB-010` is why `bulk_ban_users` must not be given a lock:** `test_bulk_ban_users_not_locked` asserts `select_for_update` is **not** issued there. Adding locks to close an authorization finding is the signal that the service layer is the wrong place — which is BLOCK 6's whole argument. **Phase 03 BLOCK 5 is an external gate on BLOCK 2** |
| **04** | `04-AUT-002` session-layer half (**BLOCK 6**: the `logout()` calls) · `04-AUT-005` + `PII-103` (`UserAdmin`'s field contract, **BLOCK 1**) · BLOCKs 2/3/7/8/9 (`consent.py`, `urls.py`, `base.py`) · `login_token.py` | ✔ **The two most important boundaries in this phase.** `04-VAL-001` reads verbatim: *"Phase 04 retains AUT-002 for the session-layer consequences only… Phase 15 owns the per-request gate. **Both phases must not file the same middleware.**"* And `04-AUT-005`: *"Phase 15 audits the permission predicate only and must cite `04-AUT-005` rather than re-file the field set."* **Phase 15 adds no `logout()` call and no middleware to phase 04's BLOCK 6's list.** Phase 04 §5.2 item 2 names the `/login/issue/` route/method as **phase 15's** to change, having ruled phase 04 may not |
| **05** | `AD-001` (`AdAdmin`'s field set, **BLOCK 6**) · `AD-008` / `05-VAL-003` (dead `ON_MODERATION` and the dead approval path) · BLOCKs 2/8 (`edit.py`, `listings_query.py`) · `account_state.py` **read-only** | ✔ **Phase 15 owns the `AdAdmin` permission predicate; phase 05 owns the field set** — stated three times in phase 05's §5.1/§5.2/§5.3. **`AD-001` is why BLOCK 2's window is real** and is cited, not fixed. **`AD-008` is a publish *state machine*, orthogonal to a publish *gate**** — AUTHZ-005 correctly does not touch it, and so does this plan. **Phase 05 §5.3 marks `account_state.py` read-only; BLOCK 5 is the one phase-15 block that edits it, and the only one authorised to** |
| **06** | `06-PII-104` (owns `SRCH-004` / `SRCH-008`) · `PII-105` (DECLINE reversibility) · `PII-113` / `04-VAL-005` (the DECLINE sentence conflict) · `PII-103` (merged into phase 04 BLOCK 1) · BLOCK 6 (account-state **semantics**) · BLOCK 10 (`withdraw_consent_action`) · BLOCK 2 (`spec-index.md:74`) · `technical-specification.md` | ✔ **Three of phase 15's gates are phase 06's** (Q4, Q5, and Q13's doc). ✔ Phase 06 §5.2: *"Phase 06 owns the semantics of the account-state predicate; phase 15 owns the framework that enforces it across both processes"* — R1 is the framework, and phase 15 implements **no** phase-06 semantics. ✔ Phase 06 §5.2 also forbids `AccountStateMiddleware` being touched by anyone but phase 15 |
| **07** | `MEDIA-*` (nginx `limit_req`, media templates) · BLOCK 10 (`edit.py`) · BLOCK 11 (`admin_actions.py` comments) | ✔ **Complement, not a claim.** Phase 07's `limit_req` on `location /login/` is one of the two bounds that make `AUTHZ-004`'s MEDIUM band right (U12). **Phase 15 plans no media index and no nginx change** |
| **08** | `SRCH-001` · `SRCH-004` (the `Ad` ad-visibility predicate, its **semantics**) · `SRCH-007` · BLOCK 1 (`ListingsQueryParams`) · BLOCK 9 (a shared client-IP helper) | ✔ **Phase 15 touches no queryset.** Phase 08 owns the ad-visibility predicate's semantics; phase 15 owns the framework and the terms. **`listings_query.py` is read-only for phase 15** — and its `ad__user__is_declined=False` term is the one that must **not** be folded into BLOCK 6's gate. **Q6 is phase 08's and the product owner's** |
| **09** | `MEDIA-005` (refuted in phase 07) · BLOCK 10 (`media_gate`'s duplicated query) · BLOCK 15 (`ci.yml`) · the cache-failure policy | ✔ **Phase 09 BLOCK 10 has not landed**, and `media_gate` is BLOCK 9's file. **Phase 15 must assume it landed or re-measure a phase-09 defect as a phase-15 one — and it files nothing about `media_gate` beyond the one-line staff-branch change.** Phase 09 and phase 10 both forbid phase 15 from touching `api_bulk.py` |
| **10** | `admin_actions.py` **moved** (BLOCK 12) · BLOCK 7 (`reject_ad` / `ban_user`) · BLOCK 16 (`edit.py`'s `SubmitAdInput` hoist) · routes Q2 and Q4 to phase 15 | ✔ **The phase-10 edge that matters: phase 10 BLOCK 16 must land AFTER BLOCK 4** (§4.4 item 3). ✔ `admin_actions.py` is **record only** for phase 15 — five-way contended *and* moved. ✔ **BLOCK 11 is phase 15's half of phase 10's routing**, and it ships nothing if its gates are declined |
| **11** | `TEST-010` (the source-inspection census) · BLOCK 2/3 (`ci.yml`, `ci-nightly.yml`, `[tool.pytest.ini_options]`) · `conftest.py` ("nobody") | ✔ **`test_edit_views_locking.py` carries 7 `inspect.getsource` assertions** and `test_admin_actions.py` carries 5 — both in this phase's blast radius. **Phase 15's changes to those files are incidental rewrites required by a decided behaviour change, not coverage work, and phase 11 must not read them as new coverage.** ✔ **Phase 15 adds no pytest dependency, changes no `testpaths`, and adds no fixture to `conftest.py`** |
| **12** | `OPS-003` (the alert file's selectors, the monitoring stack, Q5's gated decision) · BLOCK 11/12 · runbooks | ✔ **Phase 15's only adjacency is BLOCK 8's counter**: if no Python-level Prometheus client exists, the counter is **not built**, and the metrics limb is recorded as **open with phase 12's Q5 as its named owner.** ✔ Phase 15 edits no runbook, no alert YAML and no `gunicorn.conf.py` |
| **13** | `PERF-001` (the load-test gate) · BLOCK 4 (the version-key lifetime) · `cache-strategy.md` | ✔ **No shared file with any phase-15 block.** Phase 13's citation convention is a precedent for this phase's own `AUTHZ-` convention (§0.1) |
| **14** | Locale files; the language component of a cache key | ✔ **Phase 15 adds user-visible strings in exactly two blocks (6 and 10, and only under specific gate answers).** Both append to the catalogue with non-empty `ru` and `bs`; **neither regenerates it.** Phase 14's locale work is not re-shipped and not reordered |

### 5.2 What phase 15 must **not** do, for other phases' sake

1. **Do not add `logout()` to any view or admin action.** ✔ **Phase 04 BLOCK 6's**, and the only
   closure `04-VAL-001` permits on that path. `ban_user_for_ad` and `bulk_ban_users` are **record
   only** — five-way contended, and **moved** by phase 10 BLOCK 12.
2. **Do not ship a second account-state gate, decorator or shared predicate.** ✔ `04-VAL-001`
   verbatim. **If a reviewer sees a second gate appear, phase 04 BLOCK 6 is wrong.**
3. **Do not touch `UserAdmin`'s field set, `AdAdmin`'s field set, or `LoginTokenAdmin`'s.** ✔
   Phase 04 BLOCK 1 (with `PII-103`), phase 05 BLOCK 6, and phase 04's `login_token.py`.
4. **Do not touch any queryset in `listings_query.py` or `alert_query.py`, and do not add an
   `ads_auto_publish` term to either.** ✔ A second ad-hoc predicate is what `SRCH-004` exists to
   replace. **Q6 is unresolved across three phases; phase 15 files nothing about it.**
5. **Do not add a default-manager filter anywhere.** ✔ Phases 06, 08 and 10 each forbid it. It
   would hide withdrawn users from the bot's `_resolve_user`.
6. **Do not edit `AccountStateMiddleware` from any block other than BLOCK 5.** ✔ Phases 04, 05 and
   06 all forbid it; phase 15 owns the refactor.
7. **Do not touch `api_bulk.py`, `alert_query.py`, `search_vector`, `setup_search_triggers`,
   `gunicorn.conf.py`, any workflow file, `pyproject.toml`, or `src/backend/conftest.py`.** ✔ Each
   is a named reservation elsewhere, and none is this phase's.
8. **Do not add a migration, an index, an `AdvisoryLockId`, an env key, or a pytest dependency.**
9. **Do not add a `ModelAdmin` base class, mixin, or blanket grant.** ✔ `VAL-005` — a prohibition.
10. **Do not edit `docs/01-spec/technical-specification.md` or `docs/01-spec/spec-index.md`.** ✔
    Phase 06's. **Phase 15 records requests.**
11. **Do not restore or edit anything under `.ai/audit/`**, including the deleted
    `.ai/audit/15-authorization/findings.md`.
12. **Do not implement a queryset-level audience predicate or ad-visibility predicate.** ✔ Phases 06
    and 08. Phase 15 makes the terms expressible and stops.
13. **Do not turn on `IMMEDIATE_ALERTS_ENABLED`.** ✔ It stays `False` until **both** predicates
    exist.

### 5.3 Shared-artefact reservations

The coordinator sequences these. **Phase 15's claim is stated so it can be compared; phase 15 does
not negotiate.**

| Artefact | Phase-15 claim | Other claimants | Ordering rule |
|---|---|---|---|
| **`config/settings/base.py::MIDDLEWARE`** | **BLOCK 6**, one inserted entry, **in place** | ✔ **Six-way:** phase 02 (`CFG-*`), phase 04 (BLOCKs 2/7/8/9), phase 06 BLOCK 4, phase 08 (read-only), phase 09, phase 10 BLOCK 3 | **Append-only, in place. Never reorder an entry another phase annotated, never delete, never reformat.** Re-read immediately before editing; **stop and report** on a concurrent change. This is the single most contended settings list in the programme |
| **`apps/users/services/account_state.py`** | **BLOCKS 5 and 7** | ✔ Phase 04 §5.2 item 3 (forbidden to reconcile), phase 05 §5.3 (**read-only**), phase 06 (`VAL-003` semantics), phase 10 BLOCK 8 binding constraint 1 (`can_publish_ad` must stay) | **One phase-15 owner. Phase 05's "read-only" is a restriction on *other* phases; BLOCK 5 is the phase-15 claim and is the reason R1 has an owner at all.** Re-read immediately before BLOCK 7 — BLOCK 5 has moved it |
| **`apps/users/middlewares/` (new package)** | **BLOCK 6, sole owner** | Nobody | Created by BLOCK 6. The directory does not exist today |
| **`src/telegram_bot/middlewares/permissions.py`** | **BLOCKS 5 and 7** | ✔ Phases 04, 05, 06 all **forbid** touching it; phase 15 is the sole authoriser | **One phase-15 owner.** `_check_user_state`'s single-positional-argument signature is load-bearing and is asserted |
| **`src/backend/apps/users/services/login_token.py`** | **Record only (BLOCK 10)** | ✔ **Phase 04's** | **Never edited by phase 15.** The `/start login_<token>` handshake is asserted unchanged |
| **`apps/users/admin.py::UserAdmin`** | **Record only (BLOCK 9)** | ✔ **Three-way:** phase 04 BLOCK 1 owns the **field contract** (with `PII-103` merged in), phase 06 BLOCK 10 owns `withdraw_consent_action`, phase 15 audits the **permission predicate** | **Phase 15 edits nothing in this file** unless GATE Q3's written answer requires it — and the field set stays phase 04's regardless |
| **`apps/ads/admin.py::AdAdmin`** | **Record only (BLOCKs 2, 9)** | ✔ **Phase 05 BLOCK 6 owns the field set and must not change the permission predicate** | **Phase 15 changes no field and no predicate here.** `AD-001` is cited as the transfer vector |
| **`apps/ads/views/edit.py`** | **BLOCKS 2 and 4** | ✔ **SIX-WAY:** phase 03 BLOCK 5, phase 05 BLOCKs 2/8/12, phase 07 BLOCK 10, phase 10 BLOCK 16 | **The order is fixed and it is the phase's highest-consequence constraint:** *phase 03 BLOCK 5 → phase 05 BLOCK 2 → phase 05 BLOCK 8 → **BLOCK 2** → **BLOCK 4** → phase 10 BLOCK 16.* **Re-read immediately before each block; stop and report on a concurrent change** |
| **`apps/ads/services/submission.py`** | **BLOCK 4** | ✔ **EIGHT-WAY:** phase 03 BLOCKS 3/5/6/8, phase 05 BLOCKS 5/12/13, phase 07 BLOCKS 1/3, phase 10 BLOCK 16 | The most contested service in the programme. **BLOCK 4's guard must land before phase 10 BLOCK 16** |
| **`apps/search/services/alert_query.py`** | **None** | ✔ Phases 03, 06, 08 | **Phase 15 claims nothing. Read-only. This is the ad-visibility surface, and it is `SRCH-004`'s** |
| **`apps/core/enums.py`** | **BLOCK 6, one appended `StrEnum`** | ✔ **FIVE-WAY:** phases 02, 03, 05, 06, 07 | **Append only. Reorder nothing. Allocate no `AdvisoryLockId`.** Re-read immediately before editing; **stop and report** if the file is under concurrent edit |
| **`docs/01-spec/technical-specification.md`** | **Request only (BLOCK 12)** | ✔ **Phase 06 holds the reservation** (`PII-113`; BLOCKs 4/11/14) | **Phase 15 may not edit it.** The request must be specific enough to act on without re-deriving (§BLOCK 12) |
| **`docs/01-spec/spec-index.md:74`** | **Request only (BLOCK 12)** | ✔ **Phase 06 BLOCK 2 is the sole owner** | Phase 15 may not edit it |
| **`apps/moderation/admin_actions.py`** | **Record only (BLOCKS 6, 11)** | ✔ **FIVE-WAY + a move:** phase 03 (locks), phase 04 BLOCK 9 (comments only), phase 05 BLOCK 3, phase 06 BLOCK 16 (reason redaction), phase 07 BLOCK 11; **phase 10 BLOCK 12 MOVES it** | **No code. Any `reason_category` change touching `ModeratorActionLog.reason` here overlaps phase 06 BLOCK 16 and is escalated, not implemented** |
| **`apps/moderation/views/api_bulk.py`** | **Read only (BLOCK 3)** | ✔ Phases 09 and 10 both forbid touching it | **Never edited** |
| **`apps/analytics/admin.py`** | **BLOCK 1, sole owner** | Nobody | One phase-15 owner |
| **`apps/moderation/views/decorators.py`** | **BLOCKS 3 and 8** | Nobody | One phase-15 owner, two commits apart |
| **`src/backend/apps/users/views/consent.py`** | **BLOCK 10** | ✔ **Phase 04 BLOCKs 3/4/6 all edit this file** | **One file, sequential passes, never parallel.** Re-read immediately before editing |
| **`apps/ads/views/listings.py::media_gate`** | **BLOCK 9**, the staff branch only | ✔ Phase 05 §5.2, phase 10 BLOCKs 14/15; phase 09 BLOCK 10 owns a different function in the same file | **The non-staff branch's `ad__user__is_declined=False` filter is read-only** — it is phase 08's `SRCH-004` surface |
| **`apps/ads/tests/test_edit_views_locking.py`** | **BLOCKS 2 and 4 — as tripwires** | ✔ Phase 10 (7 `getsource` assertions), phase 11 (`TEST-010`) | **Never weakened. Never duplicated with a new source-inspection assertion** (§1.5). BLOCK 4's guard placement is constrained by them |
| **`apps/moderation/tests/test_decorators.py`, `test_priority_service.py`** | **BLOCK 3 — the five methods** | Nobody | **Changed in BLOCK 3's own commit, under project rule 2, with the two ordering-pinning names updated** |
| **`src/backend/apps/users/tests/test_account_state.py`** | **BLOCKS 5 and 7** | Nobody; phase 10 lists the file's `can_publish_ad` matrix as a reference | **Retargeted in BLOCK 5 with every answer preserved; two answers corrected in BLOCK 7 under project rule 2** |
| **`src/telegram_bot/tests/test_account_state_middleware.py`** | **BLOCKS 5 and 7** | Nobody; phases 04/05/06 forbid the middleware and therefore this file | **~30 tests. No assertion weakened. `TestCrossPredicateAgreement` is the phase's strongest cross-process tripwire** |
| **`src/backend/conftest.py`** | **None** | ✔ **Seven plans forbid it; one claims it** | **Phase 15 adds no fixture. A block that needs one is over-fitted** |

### 5.4 When phase 15 lands, which earlier plans must be re-read

Read in this order. Each entry names the plan, the block, and the single fact that becomes stale
the moment BLOCK 6 or BLOCK 9 lands.

| # | Plan · block | What becomes stale when phase 15 lands | What the earlier plan must do |
|---|---|---|---|
| 1 | **phase 06 · BLOCK 6** (account-state semantics) | R1 has declared the **terms**. BLOCK 7 has changed the **publish policy**. BLOCK 6 has installed the **web gate** | **Build the `User` audience predicate on the declared terms — and on nothing phase 15 implied.** `06-VAL-003` is unblocked by the *shape*, not by any decision phase 15 made. **Q4/Q5's rulings are now on the record and BLOCK 7 is built on them** |
| 2 | **phase 08 · BLOCK 1** (`SRCH-004`) | The queryset-level **terms** now exist | **Build the `Ad` ad-visibility predicate on them.** ⚠ **Q6 is still unanswered across three phases** — the terms are expressible, the *semantics* are not. **This plan adds nothing to that decision and must not be read as having implied an answer** |
| 3 | **phase 04 · BLOCK 1** (`04-AUT-005` + `PII-103`) | BLOCK 9's moderator contract is written and now has a test that iterates the registry | **Land the `UserAdmin` field contract.** `AUTHZ-003` cannot close without it, and BLOCK 9's registry test will now *observe* the escalation rather than be blocked by it. ⚠ **The U4 ordering hazard applies to phase 04's probe too** — a POST that omits an unchecked `BooleanField` de-staffs the actor |
| 4 | **phase 10 · BLOCK 16** | BLOCK 4 has made `user_id` a real actor id | **Do not hoist `SubmitAdInput` into a helper that reintroduces `ad.user_id`.** BLOCK 4's guard is the thing that makes phase 10's hoisting safe, and it must already be landed |
| 5 | **phase 05 · BLOCK 6** (`AD-001`) | BLOCK 2's window is now closed by an in-lock re-check | **The field contract is still phase 05's**, and BLOCK 2's fix is defence-in-depth until it lands. **Nothing in phase 15 weakens the case for it** |
| 6 | **phase 04 · BLOCK 6** (the `logout()` calls) | BLOCK 6's gate terminates the session **on the affected user's next request** | **The `logout()` calls become defence-in-depth under the gate, not a replacement for it.** And `consent_decline`'s `logout()` is still gated on phase 06's `PII-105` ruling — **which is now on the record** |
| 7 | **phase 12 · BLOCK 11** (`OPS-003`) and Q5 | BLOCK 8 either found an existing Python-level Prometheus client or recorded the metrics limb as **open** | **If phase 15 recorded it open, phase 12's Q5 is its named owner** and the counter is the only outstanding limb of `AUTHZ-009` |
| 8 | **phase 07** (`MEDIA-006` / `limit_req`) | BLOCK 10 has changed `/login/issue/`'s method | **The edge bound is unchanged and still applies.** The `POST` still passes through the same `location /login/` block; if phase 07's `limit_req` is ever retuned, the MEDIUM band's second half depends on it |
| 9 | **phase 11** (`TEST-010`) | BLOCKS 2, 3, 4, 5, 7, 8, 9 rewrite assertions in **seven** source-inspection-adjacent test modules | **Re-count the census.** Phase 15's edits are incidental rewrites required by decided behaviour changes, **not new coverage**, and phase 11's ordered test-change schedule must reflect that — not read it as phase 15 expanding coverage |
| 10 | **phase 14** (locale) | BLOCKS 6 and 10 may have appended msgids | **Append-only remains the rule.** Phase 15 regenerates nothing. If phase 14 has restructured `LOCALE_PATHS`, phase 15's two new strings must land in the new structure — **re-read before BLOCK 6, not before BLOCK 12** |

### 5.5 The two items phase 15 owes the programme, which no other plan can discharge

1. **The `technical-specification.md` collision (C-4, Q13).** No earlier plan records it.
   `technical-specification.md` states *"No web-side middleware redirects soft-deleted users"*, and
   BLOCK 6 falsifies that sentence on the day it lands. **Phase 06 holds the file. Phase 15 records
   the request and does not edit it. Until phase 06 acts on it, the specification and the code
   disagree, and that disagreement is recorded, named, and owned — not hidden.**
2. **The `VAL-001` CSRF band (Q7).** No earlier plan rules it, and every later phase that finds a
   state-changing `GET` will cite whatever answer exists. **A local ruling will be wrong in a
   different direction each time.** Phase 15 records the recommended amendment verbatim, applies
   nothing, and re-bands nothing.

---

## 6. Out of scope for this plan

Every de-scoping below is **routed**, not dropped. A de-scoped item with no destination is a
re-filed finding.

### 6.1 De-scoped by design (deliberately not done here, with the rationale)

| Item | Why |
|---|---|
| **The `logout()` calls on the four open revocation paths** (`consent_decline`, `UserAdmin.withdraw_consent_action`, `ban_user_for_ad`, `bulk_ban_users`) | **`04-AUT-002`'s session-layer half, phase 04 BLOCK 6.** ✔ Three of the four are **structurally unreachable at the view layer** — `ban_user_for_ad(ad, moderator_id, reason)` and `bulk_ban_users(queryset, moderator_id, reason)` take **no `request`**, and `bulk_ban_users` never materialises a `User` at all, so Django offers no way to enumerate the sessions belonging to a given user. `04-VAL-001` ruled the split in advance: *"Both phases must not file the same middleware."* **Phase 15 records all four and implements none of them** |
| **`UserAdmin`'s field contract** (no `fields` / `fieldsets` / `form`; `password` as a plain `CharField` with no hashing hook; `is_superuser` and `user_permissions` self-editable) | **`04-AUT-005` / `04-VAL-004` / `PII-103`, merged into phase 04 BLOCK 1.** Phase 06 must not patch it again. **BLOCK 9 cites it as a hard prerequisite and `AUTHZ-003` must not be closed without it.** This is the *live* risk in the `AUTHZ-003` pair and it is **not** phase 15's to fix |
| **The `AdAdmin` field set** (`user`, `status`, `published_at`, `original_published_at`, `archived_at`, `deleted_at` all editable) | **`AD-001`, phase 05 BLOCK 6.** ✔ It is the reason BLOCK 2's transfer window is real, and citing it is how phase 15 uses it. **Phase 15 changes no admin field set anywhere** |
| **The `User` audience predicate** (who may see whom) | **`06-PII-104` recommendation item 2, phase 06 BLOCK 6.** Phase 15 makes the terms **expressible** and implements nothing. **The semantics are phase 06's, and must not be inferred from BLOCK 5's declaration** |
| **The `Ad` ad-visibility predicate** (is this ad public) | **`SRCH-004` / `SRCH-008`, phase 08, already owned by phase 06.** Phase 15 verifies only that non-public objects are not reachable *through an authorization failure* — which is BLOCK 6's DENY set, not a listing filter |
| **Should a banned seller's ads stay publicly visible? (Q6)** | **A product decision, open across three phases** (08, 06, 15). Phase 08 folded `SRCH-008` into `SRCH-004` deliberately so it is argued as **one** product decision rather than smuggled in as a consent fix. **No amount of work in phase 15 settles it, and phase 15 files nothing about it.** The next step is the one-paragraph trade-off in front of the product owner — not a fourth filing |
| **Editing `technical-specification.md` and `spec-index.md` (C-4, Q13)** | **Phase 06 holds both** (`PII-113`; `spec-index.md:74` is phase 06 BLOCK 2's sole owner). **A documented divergence is acceptable; a unilateral edit is not.** BLOCK 6 records the request; BLOCK 12 routes it |
| **The `VAL-001` CSRF band ruling (Q7)** | **The audit programme's, not phase 15's.** It must be ruled once, centrally, and applied to every phase that finds a state-changing `GET`. Phase 15 records the recommended amendment verbatim and applies nothing |
| **Deciding whether DECLINE is reversible (`PII-105`, Q4) and which DECLINE sentence governs (Q5)** | **Phase 06's.** Phase 15 *depends* on both and gates on them; it does not decide either. **The findings themselves depend on them** — `AUTHZ-005`'s *type* is only well-founded once Q5 is resolved |
| **The `AUTHZ-003` re-band (Q9)** | **The coordinator's.** Phase 15 records both bands and the combined-pair band, and does not choose. **The travelling rule is that a re-band must not silently drop the `04-AUT-005` escalation** |
| **Sweeping the other 16 `ModelAdmin` classes for constant returns** | **Every other constant override in the registry returns `False`, and `False` is always safe. `True` is the only dangerous direction and this is the only instance of it.** A blanket sweep touches 17 classes for one defect and is precisely the overengineering §0.2.2 constraint 3 forbids |
| **A `ModelAdmin` base class or mixin (any size)** | **Rejected by the validator and upheld here** — `VAL-005`. Seven classes are read-only by deliberate data-protection policy. **A base class answers "how is the role read?"; the contract answers "what may `is_staff` do?"** — two different questions, and answering the second uniformly is what would grant write access to the audit log |
| **A `resolve_admin_role` indirection** | At two call sites, `User.role` **is** the resolver. A new abstraction is unjustified at that size, and BLOCK 9 is not allowed to create a third consumer to justify one. **Recorded as R11's rejected option so it is not re-proposed** |
| **A queryset-level filter to "make the gate work"** | **FORBIDDEN outright** (§0.2.2 constraint 1). It would hide withdrawn users from `AccountStateMiddleware._resolve_user`, which resolves on `chat_id` precisely because withdrawn users have `telegram_id` nulled — **re-opening a hole rather than closing one** |
| **Decoding `session_data` to find a user's sessions, or a `session_data LIKE` sweep** | **Phase 04 §6.2 item 5 explicitly refuses it**, and it is refused again here: `_auth_user_id` lives inside an encoded blob, a sweep is unindexable, and the gate makes it unnecessary |
| **Row locks on `bulk_ban_users`** | **`03-DB-010`'s tripwire.** `test_bulk_ban_users_not_locked` asserts `select_for_update` is **not** issued there. **Adding a lock to close an authorization finding is the signal that the service layer is the wrong place — which is BLOCK 6's whole argument** |
| **A CI pre-merge check for `ModelAdmin` drift** (the report's advisory recommendation 6) | **It duplicates BLOCK 9's contract test**, which already iterates `admin.site._registry` and fails by class name on divergence. A second script printing a diffable table is a second thing to keep in sync, and phase 11 owns the test toolchain |
| **A `resolve_admin_role` / `has_delete_permission` lint rule for "True requires a request"** | **The rule is a convention (constraint 1) enforced by BLOCK 9's registry test, not a linter.** A custom ruff rule is new tooling for one convention, and phase 11 holds the test/lint toolchain |
| **`prometheus_client` adoption** | **U14 is unverified**, and no Python-level client is wired into any module today. **Adding one to close a LOW finding's metrics limb would be a silently dead instrument** if nothing scrapes it — and phase 12's Q5 is a *gated* decision on whether a monitoring stack is deployed at all. **BLOCK 8 ships the log record; the counter is conditional** |
| **Re-measuring the report's runtime claims as phase-15 results** | **U1–U14 are re-derived or labelled not measured** (§0.2.4). A number carried over from the validated report is not a phase-15 result, and BLOCK 12 records the distinction |
| **Any migration, model field, index, env key, `AdvisoryLockId`, pytest dependency, `testpaths` change, or fixture in `conftest.py`** | **This plan ships none of them.** A block that appears to need one has drifted into this section |

### 6.2 Rostered elsewhere, not dropped

| Item | Owner | Note |
|---|---|---|
| The `logout()` calls on the four open revocation paths | **Phase 04 · BLOCK 6** | ✔ `04-AUT-002`'s session-layer half. **Phase 15 records the four paths and adds zero `logout()` calls.** The gate makes three of them moot; the fourth (`consent_decline`) is still phase 04's and is still gated on `PII-105` |
| `UserAdmin`'s field contract; the moderator self-escalation | **Phase 04 · BLOCK 1** (with `PII-103`) | ✔ **This is the live half of the `AUTHZ-003` pair.** `AUTHZ-003` cites it and does not close without it |
| `login_issue`'s rate-limit helpers and `login_token.py` | **Phase 04** | **Record only.** BLOCK 10 leaves both intact |
| `AdAdmin`'s field set | **Phase 05 · BLOCK 6** | ✔ The transfer vector BLOCK 2 defends against |
| `AD-008` / `05-VAL-003` — the dead `ON_MODERATION` state and the dead approval path | **Phase 05** | ✔ A publish **state machine** is orthogonal to a publish **gate**. AUTHZ-005's reproduction of the phase-05 path was attribution, not duplication, and so is this block's silence |
| `PII-105` (DECLINE reversibility) and `PII-113` (the DECLINE sentence conflict) | **Phase 06** | ✔ **Two of BLOCK 7's hard gates** |
| The `User` audience predicate; `06-VAL-003` | **Phase 06 · BLOCK 6** | ✔ **Unblocked by R1's *shape* only.** Phase 15 implements none of its semantics |
| `technical-specification.md`; `spec-index.md:74` | **Phase 06** | ✔ **BLOCK 12's requests.** This is the plan's most under-recorded item |
| `withdraw_consent_action` | **Phase 06 · BLOCK 10** | **Record only** (one of the four open revocation paths) |
| `ModeratorActionLog.reason` redaction in `admin_actions.py` | **Phase 06 · BLOCK 16** | ✔ **Overlaps BLOCK 11's Q11 option (b) — escalated, not implemented** |
| `SRCH-004` / `SRCH-008`; the `Ad` ad-visibility predicate; **Q6** | **Phase 08 / phase 06, and the product owner** | ✔ **Phase 15 files nothing.** The terms are declared; the semantics are not phase 15's |
| `ListingsQueryParams.feature_slugs`; `SRCH-001`; `SRCH-007` | **Phase 08** | **No shared file with any phase-15 block** |
| `media_gate`'s duplicated `AdImage` query | **Phase 09 · BLOCK 10** | **Not landed.** Phase 15 changes `media_gate`'s staff branch and nothing else, and files nothing about the duplication |
| `api_bulk.py` | **Phases 09, 10** | **Read only. Never edited by phase 15** |
| `admin_actions.py`'s move; `reject_ad` / `ban_user`; **phase 10 Q2 and Q4** | **Phase 10** | ✔ **BLOCK 11 is phase 15's half of the routing and ships nothing if its gates are declined** |
| `edit.py`'s `SubmitAdInput` hoist; the `PERF-`-namespace sweep; `ci-nightly.yml` | **Phase 10 / phase 03 / phase 11** | ✔ **Phase 10 BLOCK 16 must land after BLOCK 4** (§4.4 item 3) |
| The `getsource` test census; the test toolchain | **Phase 11** | ✔ Phase 15's test edits are **incidental rewrites**, not new coverage |
| The monitoring-stack decision; the alert selectors; the runbooks | **Phase 12** | ✔ **BLOCK 8's counter is conditional on phase 12's Q5** |
| The `ENT-` entrypoint and CI work; the `CFG-` settings guards | **Phases 01, 02** | **No overlap. Phase 15 adds no env key and edits no workflow file** |
| nginx `limit_req` on `location /login/` | **Phase 07** | **Complement, not a claim.** It is one of the two bounds that make `AUTHZ-004`'s band right |

### 6.3 Explicitly forbidden while implementing

1. **Adding a `default_manager` filter to `User` or any app**, or folding
   `user__is_declined=False` / any listing-visibility term into the account-state gate.
2. **Adding a second account-state gate, decorator or shared predicate** — anywhere, for any purpose.
3. **Adding a `logout()` call to any view or admin action** (`ban_user_for_ad`, `bulk_ban_users`,
   `consent_decline`, `withdraw_consent_action`).
4. **Adding a `ModelAdmin` base class, mixin, shared permission base, or blanket grant.** ✔ `VAL-005`
   — a prohibition, not an option.
5. **Sweeping the 17 `ModelAdmin` classes** for constant-returning overrides.
6. **Returning `True` from any `has_*_permission` without having consulted `request`.** ✔ `AUTHZ-006`
   must not be reintroduced, and a new answer defaults to `False`.
7. **Deleting `can_publish_ad`, or shipping it alongside a second corrected predicate.** ✔ Phase 10
   BLOCK 8 binding constraint 1, and the finding's dead-code label was rejected.
8. **Touching any queryset in `listings_query.py` or `alert_query.py`, or writing
   `is_banned` / `is_declined` / `consent_revoked` / `ads_auto_publish` into any listing filter.**
9. **Targeting `_check_publish_permission`, or any name the report gives that the tree does not
   have.** ✔ C-2. The tree is the authority.
10. **Budgeting `apps/users/tests/test_login_issue_template.py`.** ✔ It does not exist, and creating
    it is not the fix.
11. **Adding `@login_required` to `toggle_favorite`,** or converting its guest-gate fragment into a
    302.
12. **Weakening, re-scoping or deleting any source-inspection test** in
    `test_edit_views_locking.py`, `test_admin_actions.py`, `test_moderation_views.py` or
    `test_decorators.py`. **F20's two structural assertions are the phase's hardest tripwires.**
13. **Weakening an assertion for any reason other than the six pre-authorised changes in §0.2.2
    constraint 2**, each of which must cite project rule 2 by name in its commit body.
14. **Editing `apps/users/admin.py`'s field set, `apps/ads/admin.py`'s field set,
    `apps/users/services/login_token.py`, or `apps/moderation/views/api_bulk.py`.**
15. **Editing `docs/01-spec/technical-specification.md` or `docs/01-spec/spec-index.md`.**
16. **Editing `src/backend/conftest.py`, any `config/settings/test.py`, `pyproject.toml`, or any
    `.github/workflows/**` file.**
17. **Appending, reordering or removing anything but one appended `StrEnum` in
    `apps/core/enums.py`; allocating an `AdvisoryLockId`.**
18. **Reordering, deleting or reformatting any `MIDDLEWARE` entry.** Insert one, in place, after
    `AuthenticationMiddleware`.
19. **Adding a migration, a model field, an index, an env key, or a pytest dependency; changing
    `testpaths`; turning on `IMMEDIATE_ALERTS_ENABLED`.**
20. **Implementing a queryset-level audience predicate or ad-visibility predicate,** or deciding
    what the declared terms *mean* for listing queries.
21. **Writing a test that asserts a line number, a template-string substring, a literal private name,
    an introspection column count, or the mere presence of a symbol** — or shipping a guard that
    was never **demonstrated failing**.
22. **Adding a `select_for_update` to `bulk_ban_users`, or a second locked read to `ad_edit`, or
    moving `submit_ad`'s fetch into a helper.**
23. **Regenerating the locale catalogue.** Append only; `ru` and `bs` `msgstr` non-empty.
24. **Creating, restoring or editing anything under `.ai/audit/`,** including the deleted
    `.ai/audit/15-authorization/findings.md`.
25. **Citing a bare `AUT-001`-style key,** or writing `AUTZ-` in any new artefact.
26. **Running a test on the host** (`uv run pytest` always fails), using
    `--override-ini=addopts=`, or pointing a probe at the shared `test_mko_bazuna` database while
    another agent is running.
27. **`git reset` / `git checkout` / `git restore` / `git stash` / `--amend` / force-push**, or
    reverting a file another agent changed. `git add -A` or `git add .`.
28. **Re-banding `AUTHZ-004` locally,** or applying the `VAL-001` amendment.
29. **Presenting an un-verified `U1`–`U14` claim as a phase-15 result.** A claim that was not
    measured is recorded as **not measured**.
30. **Letting a gate go unanswered and choosing an option anyway.** An unanswered gate is a stopped
    block with a recorded reason, not an Implementor decision.

---

## 7. Per-block risk register

Severity here is **this Planner's assessment of execution risk for the change**, not the finding's
severity. **Blast** covers what else feels the change. **Contention** covers shared files.
**Behaviour** covers observable response changes. **Direction** covers whether the change *grants*
access rather than removing it — a category unique to this phase and the one most likely to be
missed in review.

| Block | Risk | Kind | Likelihood | Impact | Mitigation / detection | Residual |
|---|---|---|---|---|---|---|
| **All** | A block runs with its gate unanswered, or the Implementor silently picks an option | Process | Med | **High** | Every gate is a labelled block in §3 and a row in §0.5, repeated verbatim in the task YAML's `extra_context`; §8.1 checks a **written** answer exists for each | Low |
| **All** | A security fix is implemented so that it **fails open**, or depends on a queryset filter | **Correctness** | Med | **High** | §0.2.2 constraint 1, restated in §1.2 and per block; every gate's `acceptance_criteria` includes the fail-closed case; a default-manager filter is §6.3 item 1 | Low |
| **All** | A privilege **expansion** ships without an explicit review, because it is phrased as a security fix | **Direction** | **High** for blocks 9 and 1 | **High** | Every block header states the direction; BLOCK 9's gate carries the 17-model matrix; §0.2.2 constraint 1's deny-by-default rule; `test_user_roles.py` must show the chosen option in the diff | **Med — accepted, by gate** |
| **All** | The Implementor works from the **report's** file and symbol list and follows a citation the tree does not have | Process | **High** | **High** | ✔ C-1, C-2, C-3, C-4 and §0.2.3's F1–F20. Every block's `extra_context` names the tree-correct target; **the report is evidence, not instruction** | Low |
| **All** | A red gate is captured while another phase agent runs and a teardown race is reported as a product defect | Process | **High** | Med | Concurrent runs collide on one `test_mko_bazuna`. Re-run serially before reporting. Symptoms: `test_mko_bazuna does not exist`, `relation "..." does not exist` | Low |
| **All** | A contended file is edited on a stale read — `base.py`, `enums.py`, `edit.py`, `submission.py`, `consent.py`, `UserAdmin`, `AdAdmin`, `conftest.py` | Contention | **High** | Med–High | Re-read immediately before editing; **stop and report** on a concurrent change; never stage by directory. §5.3 lists every one | **Med — accepted** |
| **All** | A blanket `ruff check --fix src/` reorders imports another phase's uncommitted work depends on | Process | Med | Med | `[tool.ruff] fix = false` is set deliberately; `--fix` is scoped to the block's own files | Low |
| **All** | An un-verified claim is quoted as a phase-15 result | Correctness | **High** | **High** | §0.2.4's U1–U14 with their verification steps; §6.3 item 29; BLOCK 12 records the un-re-derived claims as **not measured** | Low |
| **1** | The single method is widened into a sweep of the 17 admin classes | **Direction** | Med | **High** | Constraint 1; the options table records the sweep as rejected; §6.3 items 4 and 5; `no other ModelAdmin class is modified` is an acceptance criterion | Very low |
| **1** | A superuser loses a working delete action, disguised as a security fix | Behaviour | Low | Med | Ruling chooses the `is_superuser`-consulting shape over the unconditional `False`; a superuser-identity assertion is an acceptance criterion | Very low |
| **2** | The guard is moved **out** of the `atomic()` block, or a second locked read is added, and the structural tripwires go red | Correctness | Med | Med | F20; constraints 1 and 2; `test_ad_edit_get_path_not_locked` and the whole `TestEditViewsLocking` class are in `tests_to_run` | Low |
| **2** | The ownership check is removed from the GET path and the render branch starts leaking another seller's ad | Behaviour | Low | **High** | Constraint 3 keeps the unlocked read for GET; the acceptance criteria include a non-owner GET refused **and** the owner GET rendering | Very low |
| **2** | `edit.py` has been changed by phase 03 or phase 05 and the block is written against a stale structure | Contention | **High** | Med | The external gate; constraint 6; the §5.3 serial position | Low |
| **3** | The five test methods are updated, but the two that pin the ordering keep a **stale name** | Correctness | **High** | Med | C-3; constraint 1; the acceptance criterion names the renames explicitly | Low |
| **3** | The reorder is described as fixing a `422` bug, re-filing a refuted claim into the tracker | Correctness | **High** | Med | F14; the block description and constraint 6 both state the refutation; §6.3 item 9 | Very low |
| **4** | **The guard is a tautology** — shipped without the `edit.py` caller change, green suite, zero protection | **Correctness** | **High** if the halves are split | **High** | The block's opening paragraph and constraints 1 and 8; the two assertions (row byte-identical **and** non-owner POST refused before `submit_ad`) | Low |
| **4** | **Phase 10 BLOCK 16 lands first**, and the guard becomes permanently tautological while looking correct | **Correctness / sequencing** | Med | **High** | §4.4 item 3; `depends_on` plus the explicit "STOP and escalate" in `extra_context`; §5.3's ordering row | Low |
| **4** | The guard is placed before the `atomic()` block and `test_submit_ad_fetches_inside_atomic` raises `ValueError` rather than failing cleanly | Correctness | Med | Med | Constraint 2; the test is in `tests_to_run` and the mechanism of its failure is documented so it is not mistaken for a product defect | Low |
| **4** | `user_id` is tightened to `int`, and the bot's `data.get("user_id") → None` path starts raising | Behaviour | Med | Med | Constraint 3: keep it optional and **fail closed** on `None`; the bot `/post → process_preview` path is in `tests_to_run` | Low |
| **5** | **An answer changes while the block claims to only move it** — the block's own headline risk | **Correctness** | **High** | **High** | The four-flag × four-consumer before/after matrix as the headline acceptance criterion; the ~30 bot tests and the cross-predicate agreement test in `tests_to_run`; constraint 1 | Low |
| **5** | The extraction reproduces the instance-level-only shape and phases 06/08 stay blocked for a fourth phase | **Correctness** | Med | **High** | R1; constraint 7's "reachable from a real `filter(...)`" acceptance criterion | Low |
| **5** | Targeting `_check_publish_permission` produces an `AttributeError` — or a **silent no-op** that leaves two vocabularies and reports success | **Correctness** | Med | **High** | ✔ C-2; F4; constraint 4; the real names are in the task YAML's `targets` | Low |
| **5** | `test_account_state.py`'s whole flag matrix is rewritten loosely in the retarget | Correctness | Med | **High** | Constraint 1; the acceptance criteria pin each existing answer explicitly, including `can_login(is_deleted=True) is True` | Low |
| **6** | **The gate terminates live sessions the instant anyone is banned, declined or soft-deleted — including the operator's own test account.** It will read as a site-wide breakage in the first 24 hours | **Behaviour** | **High** | **High** | GATE Q15's answer is the deliberate choice; the acceptance criteria include a **positive control** (a normal seller's dashboard renders 200 with the gate installed); the reason code is emitted from day one so the first report is diagnosable | **Med — inherent** |
| **6** | A 403 dead-ends every affected user, and the top support ticket is a bare error page | Behaviour | Med | **High** | GATE Q15's alternatives table; option (b) reuses the existing translated `login_status` reason surface | Low |
| **6** | The gate is placed before `AuthenticationMiddleware`, or fails an anonymous request closed, and **the whole site goes down** | **Behaviour** | Low | **High** | F1; constraints 1 and 4; the acceptance criteria include the anonymous pass-through and the public-route check | Very low |
| **6** | `base.py::MIDDLEWARE` is reordered or reformatted while six other phases depend on it | Contention | Med | **High** | Constraint 4; §5.3's "append-only, in place"; the acceptance criterion "gained exactly one entry, with nothing reordered, deleted or reformatted" | Low |
| **6** | `enums.py` is appended to while another phase is mid-edit, and another phase's enum order is disturbed | Contention | Med | Med | R3's re-read-and-stop rule; constraint 5 | Low |
| **6** | `technical-specification.md` is edited unilaterally | Contention | Med | **High** | Constraint 7; §6.3 item 15; BLOCK 12's routing | Very low |
| **6** | The `is_active` premise is shipped silently in either direction, and the control is added in one phase and removed in the next | **Correctness** | Med | **High** | GATE Q1 is a **hard** gate requiring U1 first; the U1 matrix is a required part of the commit body | Low |
| **7** | The publish DENY set is widened **before** `PII-105` is ruled, and the wrong control is relied on | **Correctness** | Med | **High** | GATE Q4 and GATE Q5 are hard gates; "this block does not start" is in both the description and `extra_context` | Low |
| **7** | A declined seller's ability to **see** their own ads changes along with their ability to post | Behaviour | Low | **High** | Constraint 6; no queryset is touched; the acceptance criteria name the see/post distinction | Very low |
| **7** | `can_publish_ad` is deleted as dead code, against phase 10's binding constraint | Correctness | Low | **High** | F3; constraint 4; §6.3 item 7; the "still exists and is still exported" acceptance criterion | Very low |
| **8** | A `prometheus_client` counter is added and **nothing scrapes it** — the finding looks closed and the instrument is dead | **Quality** | **High** if U14 is skipped | Med | Constraint 4 and the acceptance criterion: either a verified scrape path or the limb is recorded as open with phase 12's Q5 named | Low |
| **8** | The helper becomes a **third** denial-logging convention instead of absorbing the two that exist | Correctness | Med | Med | Constraint 1; the `decorators.py` zero-call logger is the evidence; the acceptance criteria require the prose sites to be rewritten, not left in parallel | Low |
| **8** | `@login_required` reaches `toggle_favorite` on a "while we're here" basis and the guest fragment becomes a 302 | Behaviour | Med | Med | Constraint 5; `test_auth_nav.py` and the favourite-fragment tests in `tests_to_run` | Low |
| **9** | **A privilege expansion ships as a security fix.** Either the moderator contract widens 12 changelists, or the `AdminSite` override grants `/admin/` to a superuser-not-staff | **Direction** | **High** | **High** | Three gates; the alternatives tables with consequences; the moderator contract's existence in `docs/`; §0.4's travelling rule that a re-band must not drop the escalation | **Med — by gate** |
| **9** | **The 17-class mixin is implemented anyway** — it is the report's own recommendation, so an Implementor who reads only the report will build it | **Direction** | **High** | **High** | `VAL-005` in §2, §6.1 and §6.3 item 4; the block's binding constraint 1 names all seven read-only classes; the acceptance criterion "no ModelAdmin base class, mixin or blanket grant exists" | Low |
| **9** | The contract test **POSTs** and de-staffs the actor mid-test, so later assertions fail spuriously and the test is "fixed" by weakening | **Quality** | Med | Med | U4's hazard stated in the block header; constraint 5 "never POSTs and never mutates"; §1.5's rule that a `getsource` test cannot see an absence | Low |
| **9** | The contract test reads `admin.py` and counts `has_view_permission` in isolation, yielding 14/17 instead of 12/17 | **Correctness** | Med | Med | F7; constraint 4 names the disjunction explicitly; the acceptance criteria say the test fails **by class name** | Low |
| **9** | The `media_gate` change is written while phase 09 BLOCK 10 has landed, or the non-staff branch's `is_declined` filter is touched | Contention | Low | **High** | Constraint 7 and the "byte-identical" acceptance criterion; §5.3's read-only note | Very low |
| **9** | `AUTHZ-003` is closed while `04-AUT-005` is still open | **Process** | Med | **High** | The external prerequisite in the block header, constraint 8, the decision record's text, and §8.1 | Low |
| **10** | The block is budgeted against the report's two test files, one of which does not exist, and the real 4 files / 10 call sites go red | **Process** | **High** | Med | ✔ C-1; F13; constraint 4 names all four files and forbids creating the missing one; all four are in `tests_to_run` | Low |
| **10** | **`LOGIN_URL` behaviour changes** and the four `test_cabinet_sections.py` redirect assertions, `test_logout.py`, `test_consent.py` and the saved-search test break | Behaviour | Med | Med | Constraint 6; all four modules in `tests_to_run`; the assertion's target-not-method reasoning is stated in the block | Low |
| **10** | The deep-link landing becomes a dead end for a bookmarked or messaged link, and the top support ticket is a 405 page | Behaviour | Med | **High** | GATE Q8; option (b) is in the alternatives table and its cost is stated; the acceptance criteria require an **actionable** page | Med — inherent to the UX decision |
| **10** | The landing template's three deep-link assertions are weakened to make the new form pass | **Correctness** | Med | **High** | Constraint 5: change the template's **design** under the gate answer, never the assertion; name the contract change in the commit body | Low |
| **10** | `@never_cache` is dropped "while we're here", reintroducing a caching hazard on a page carrying a raw token | **Correctness** | Med | **High** | Constraint 8; the acceptance criterion "still present" | Very low |
| **11** | A 302→405 change lands without the owner deciding, breaking recorded behaviour | **Behaviour** | Med | **High** | GATE Q12; constraint 4 — the assertions change in the same commit or the change does not ship | Low |
| **11** | A `reason_category` change reaches into `admin_actions.py` and collides with phase 06 BLOCK 16's redaction | Contention | Med | Med | Constraint 3; the "byte-identical" acceptance criteria for both files; option (b) is recorded as overlapping | Low |
| **11** | The block is read as an `AUTHZ-` remediation and the finding count inflates | Process | Med | Med | The block header says **"No `AUTHZ-` finding"**; the citation is phase 10 Q2/Q4, not `AUTHZ-0NN` | Very low |
| **12** | The phase-06 request is too vague to act on and the specification stays wrong | Process | Med | Med | The acceptance criteria require the exact sentence, the block, the gate, and the "four account states, not one" statement | Low |
| **12** | The tracker marks a finding closed because a gate was **declined** | **Process** | Med | **High** | Constraint 6; the acceptance criteria require "reduced **and open**, with its named owner" | Low |
| **12** | A number from the validated report is recorded as a phase-15 measurement | Correctness | **High** | Med | Constraint 4; the `not measured` labelling requirement; §6.3 item 29 | Low |

---

## 8. Definition of done for the whole plan

Phase 15 is complete when **all** of the following hold.

### 8.1 Scope

- [ ] All **9** `AUTHZ-` findings have a recorded disposition: **9 implemented** across BLOCKS
      1–10 (`AUTHZ-001` in 5 and 6; `AUTHZ-002` in 4; `AUTHZ-003` in 9; `AUTHZ-004` in 10;
      `AUTHZ-005` in 5 and 7; `AUTHZ-006` in 1; `AUTHZ-007` in 2; `AUTHZ-008` in 3; `AUTHZ-009` in
      6 and 8), **or** an explicit, reasoned non-implementation recorded against the finding ID.
- [ ] All **5** `VAL-` items have a recorded disposition: `VAL-001` requested centrally and **not
      applied**; `VAL-002` discharged by BLOCK 9's registry iteration; `VAL-003` measured and
      recorded; `VAL-004` consolidated in the citation convention and BLOCK 12; **`VAL-005`
      upheld as a prohibition, with zero mixins in the tree**.
- [ ] BLOCK 11 and BLOCK 12 shipped, **or** each recorded as declined with its gate answer and its
      named consequence. **A declined gate is a recorded outcome, never a silent omission.**
- [ ] **Twelve commits**, one per block, explicitly staged. No squashing, no amending.
- [ ] `git status` shows **no modification under `.ai/audit/`**, and
      `.ai/audit/15-authorization/findings.md` was **not** restored.
- [ ] Zero migrations, zero model fields, zero indexes, zero `AdvisoryLockId`s, zero env keys, zero
      pytest dependencies, zero `testpaths` changes, zero fixtures added to
      `src/backend/conftest.py`.

### 8.2 Gates — all written, none chosen by an Implementor

- [ ] A **written** answer exists for every one of the eleven `GATED` questions: **Q1, Q3, Q3′,
      Q4, Q5, Q7, Q8, Q9, Q11, Q12, Q15**. Each names its owner and its date. **An unanswered gate
      is a stopped block, not a default.**
- [ ] The three `RULED` decisions are **recorded with their rejected alternatives and consequences**:
      R1 (two-level shape, over instance-level only), R2 (U13 is a verification step, not a
      decision), R3 (one appended `StrEnum` in `enums.py`).
- [ ] The two `ROUTED` items are **not** implemented and **not** re-filed: **Q6** (the
      `is_banned` public-visibility product decision) and **Q13** (the `technical-specification.md`
      edit).
- [ ] **`AUTHZ-003` is not closed while `04-AUT-005` is open** — recorded in the decision record and
      in the tracker.
- [ ] No commit body claims a gate was answered when it was not.

### 8.3 Per-finding behavioural confirmation

Every box below is an **asserted behaviour**, not a code-reading.

- [ ] `AUTHZ-001` — each of `is_banned` / `is_deleted` / `is_declined` / `consent_revoked` produces a
      denied request with the session destroyed, **and** the response is the one GATE Q15 chose;
      anonymous requests and public routes are unaffected; a restricted-but-valid seller
      (`ads_auto_publish=False`) still reaches the dashboard; an unevaluable authenticated state is
      **denied**.
- [ ] `AUTHZ-001` — the **bot's** answers are byte-identical before and after BLOCK 5, and the
      cross-process agreement test is green and unmodified.
- [ ] `AUTHZ-002` — a mismatched `user_id` leaves the ad row **byte-identical** (asserted on the
      row, never the return value); a non-owner POST is refused **before** `submit_ad` is reached; a
      `None` actor is denied; the bot's `/post → process_preview` still publishes.
- [ ] `AUTHZ-003` — `media_gate` and `staff_required` answer **identically** for a superuser who is
      not staff; the registry test fails **by class name** on any contract divergence, for all five
      identities; no mixin exists; the seven deliberately read-only classes are unchanged.
- [ ] `AUTHZ-004` — a `GET` with and without a CSRF cookie creates **zero** `LoginToken` rows; the
      protected `POST` creates exactly one; both rate limits still return 429; a deep link reaches
      an **actionable** page; the bot's `/start login_<token>` handshake is unchanged.
- [ ] `AUTHZ-005` — a declined **and** a consent-revoked seller are denied publication by the bot
      middleware and by `can_publish_ad`, for the same reason code; the interaction gate is
      unchanged; `can_publish_ad` still exists and is still exported.
- [ ] `AUTHZ-006` — `has_delete_permission` is `False` for anonymous and for a seller, `True` for a
      superuser, through `admin.site._registry`.
- [ ] `AUTHZ-007` — the ownership check runs on the locked instance inside the existing atomic
      block; `select_for_update` appears exactly once in `ad_edit`'s source; a non-owner GET and POST
      are both refused with the row byte-identical; the owner path renders and saves.
- [ ] `AUTHZ-008` — an authenticated non-`POST` returns 405; an anonymous request is refused without
      a bearer challenge; the 403 for a non-ADMIN `POST` is unchanged.
- [ ] `AUTHZ-009` — a denied request emits **exactly one** record carrying a stable reason code, the
      actor id, the path and the resource; the previously-unused `logger` in `decorators.py` is now
      called; **either** a counter exists whose scrape path is verified, **or** the metrics limb is
      recorded as open with phase 12's Q5 named.
- [ ] **Every new guard was demonstrated failing at least once** before its commit.

### 8.4 Cross-phase integrity

- [ ] **Exactly one account-state gate exists in the tree.** A search for a second gate, decorator or
      shared predicate returns nothing.
- [ ] **Zero `logout()` calls were added** to `ban_user_for_ad`, `bulk_ban_users`,
      `consent_decline` or `withdraw_consent_action`; all four are recorded as phase 04 BLOCK 6's.
- [ ] `apps/users/admin.py`, `apps/ads/admin.py`, `apps/users/services/login_token.py` and
      `apps/moderation/views/api_bulk.py` are byte-identical to `ba23277` except where a **written
      gate answer** required otherwise — and in that case the gate answer names the file.
- [ ] `listings_query.py` and `alert_query.py` are byte-identical. **No listing queryset carries an
      account-state term.**
- [ ] **No default-manager filter** exists on `User` or any app; `IMMEDIATE_ALERTS_ENABLED` is
      `False`.
- [ ] `docs/01-spec/technical-specification.md` and `docs/01-spec/spec-index.md` are byte-identical,
      and a specific request against each is recorded.
- [ ] `config/settings/base.py::MIDDLEWARE` gained **exactly one** entry, immediately after
      `AuthenticationMiddleware`, with nothing reordered, deleted or reformatted.
- [ ] `apps/core/enums.py` gained **exactly one** appended `StrEnum`, with no reordering.
- [ ] The phase-15 execution order on `apps/ads/views/edit.py` was respected, and **BLOCK 4 landed
      before phase 10 BLOCK 16**.
- [ ] §5.4's re-read list was walked; every earlier plan that had to re-read did.

### 8.5 Project conventions

- [ ] English only. No `print()`. `logger = logging.getLogger(__name__)` with lazy `%s` formatting.
- [ ] Every fixed value is a `StrEnum`; every user-visible string is wrapped in `{% trans %}` /
      `gettext`, with **non-empty `ru` and `bs`** `msgstr`; the locale catalogue was **appended to,
      never regenerated**; `test_i18n_completeness.py` is green.
- [ ] Every new `ModelAdmin` answer **denies by default** and consults `request`. No answer returns
      `True` without one.
- [ ] No new abstraction without a justification that names the shipped primitive it reuses.
- [ ] Every test verifies **logic and component interaction**, not implementation trivia; **no test
      asserts a line number**, and no task used a line number as a target.
- [ ] Every commit cites its findings with the §0.1 convention, and **no bare `AUT-001`-style key
      appears in any new artefact.**
- [ ] The six pre-authorised test changes each cite **project rule 2 by name** in their commit body.
      No other assertion was weakened, re-scoped or deleted.
- [ ] `uv run ruff check` and `uv run basedpyright` are clean on every file the phase touched.

### 8.6 Deliverables

- [ ] The tracker records all **9** findings, all **5** `VAL-` items and both phase-10-routed
      questions, each **phase-qualified**, with the two `ROUTED` items visible and unowned-by-phase-15.
- [ ] Every finding that **shipped reduced** is recorded as reduced **and open**, with its named
      owner — not as closed.
- [ ] Every `U1`–`U14` claim that was **not** re-derived is recorded as **not measured**, with its
      verification step, so the next phase does not inherit it as a result.
- [ ] The two items only phase 15 can escalate are escalated in writing: the
      `technical-specification.md` collision to **phase 06**, and the `VAL-001` CSRF band to **the
      audit programme**.
- [ ] `.ai/plans/15-authorization-remediation.md` moves from `status: "planned"` to
      `status: "implemented"` **only in BLOCK 12's commit**, and only if every box above holds.
- [ ] **The programme's closing note records that phase 15 was the last phase**, that the two
      escalation items remain open with named owners, and that no `AUTZ-` key is reusable.
