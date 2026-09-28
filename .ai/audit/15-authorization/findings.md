---
# Report metadata — fill once per phase report.
phase: "15"
phase_name: "Authorization & Access Control"
date: "2026-09-28"
auditor: "Executor (subagent)"
validator: ""  # Phase 99 only — omit/blank for raw phase findings
mode: "problems-only"
# Correct prefix per phase: 01-ENT, 02-CFG, 03-DB, 04-AUT, 05-AD, 06-PII, 07-MED, 08-SRH, 09-EXT, 10-QLT, 11-TST, 12-OPS, 13-PERF, 14-I18N
# NOTE: phase file §10 specifies `AUTZ-`; that prefix is ALREADY burned as an
# in-source remediation marker in apps/users/tests/test_user_roles.py:2
# ("Tests for the UserRole StrEnum and User.role property (AUTZ-003)"), which is
# the exact ID-collision hazard the orchestrator flagged. This report therefore
# uses `AUTHZ-` per the orchestrator instruction, and every finding is keyed to
# tracker id `15-authz-AUTHZ-00N`.
id_prefix: "AUTHZ"
report_status: "draft"
severity_taxonomy: ".kilo/commands/audit/phases/15-audit-authorization.md#severity-taxonomy"
---

# Audit Findings — Authorization & Access Control

## Executive Summary

Three high-severity authorization defects were confirmed by running the real application
code. First, a seller who is banned, who declines consent, or who withdraws consent keeps a
fully working website account for a full two weeks, because nothing re-checks their status
after login — so the decision to block them happens once and then is never revisited. Second,
the shared service that finalises an ad ignores the seller identity it is handed, so a wrong
seller can rewrite another seller's draft if any future caller forgets its own check. Third,
the "administrator" role is defined three different ways in three different layers, which
locks legitimate moderators out of most of the admin area while letting a few superusers be
locked out entirely. No cross-seller data leak, no anonymous state change, and no CSRF bypass
on a form endpoint were found; the buyer-facing catalogue and all cross-seller attempts were
correctly refused. Nine issues in total: three high, four medium, two low.

## Scope & Methodology

**Scope:** Every web route (`config/urls.py` and all 10 app `urls.py`), the 17 registered
`ModelAdmin` classes, the 7 aiogram routers and their 24 handlers, the shared account-state /
ownership predicates in `apps/users`, `apps/ads` and `apps/core`, and the CSRF/session
configuration in `config/settings`. Covered both processes of the dual-process runtime and
their shared decision points.

### Runtime Verification

Each claim in a finding must be reproducible. Record the verification checks below.

| R# | Check | Method | Result |
|----|-------|--------|--------|
| R-01 | Route-to-role matrix for 46 URL/method pairs as ANONYMOUS / SELLER / STAFF / SUPERUSER | Django test client (`enforce_csrf_checks=True` and `=False` variants) against private PG `mko_bazuna_audit15` | PASS |
| R-02 | IDOR: SELLER_A → SELLER_B ad (PUBLISHED/DRAFT/ON_MODERATION) edit/archive/delete/reactivate/favorite, saved-search edit/toggle/delete, media key | Django test client + ORM state assertions before/after | PASS (all denied) |
| R-03 | Bot IDOR: `/copy <ad_id>` of another seller's ad, `unsub:<token>` of another seller's saved search | `copy_ad` / `_resolve_owned` direct invocation + source audit of all 24 handlers | PASS (all denied) |
| R-04 | Admin surface as ANONYMOUS and SELLER: `/admin/` index + 17 changelists, `/moderation/*` (6 routes), `/analytics/moderation/` | Per-`ModelAdmin` `has_view/change/add/delete_permission` matrix over `admin.site._registry` + HTTP status per role | FAIL (AUTHZ-003, AUTHZ-006) |
| R-05 | Bot command authorization: every command/callback handler, unauthenticated (unregistered) Telegram identity | Source audit of all `@router.message` / `@router.callback_query` gates + live `_check_user_state` / `_check_publish_permission` | PASS (with a caveat recorded in AUTHZ-005) |
| R-06 | CSRF: 13 state-changing POSTs without a token, plus a GET that writes | `Client(enforce_csrf_checks=True)`; `CSRF_COOKIE_*` and emitted `Set-Cookie` inspection | FAIL (AUTHZ-004) |
| R-07 | Fail-secure: `staff_required` / `staff_required_api` for `AnonymousUser`; `can_login` / `can_publish_ad` for every account-state flag | Direct invocation + `RequestFactory` | PASS (all denial paths), FAIL on the *absence* of a gate (AUTHZ-001) |
| R-08 | Linter + type-checker over the authorization surface | `uv run ruff check <12 paths>` → "All checks passed!"; `uv run basedpyright <7 paths>` → "0 errors, 0 warnings, 0 notes" | PASS |

> PASS results prove the audit was thorough; they are METHODOLOGY evidence, NOT findings.

**Tools used:** `ruff`, `basedpyright`, `grep -rn`, `docker exec` (Django 5.2 test client
against a private `postgres:18-alpine` instance), `admin.site._registry` introspection
(`get_form` / `has_*_permission`), aiogram middleware direct invocation.

**Assumptions:** Production runs `config.settings.prod` (CSRF/SESSION cookies `Secure=True`,
`SameSite=Lax`, `HttpOnly=True` — `base.py:139-144`); `SESSION_COOKIE_AGE` is **not** overridden
anywhere, so the Django default 1 209 600 s (14 days) applies (verified at runtime); the bot uses
long polling, not a webhook, so the phase's webhook-sender-verification edge case is N/A; the
phase-05 dead approval path was **verified but not re-filed** (see Cross-Finding Analysis).

<!-- Phase 99 ADDS a Methodology Cross-Check here: re-run each R# check against the live source. -->

## Findings Summary

| ID | Title | Severity | Status | Category | Tracker |
|----|-------|----------|--------|----------|---------|
| AUTHZ-001 | No per-request account-state gate: a banned / consent-declined / GDPR-withdrawn seller keeps a working web session for 14 days | HIGH | Open | Security (Broken Access Control) | 15-authz-AUTHZ-001 |
| AUTHZ-002 | `submit_ad()` ignores the `user_id` it is handed — proven service-layer IDOR on another seller's draft | HIGH | Open | Security (IDOR) | 15-authz-AUTHZ-002 |
| AUTHZ-003 | The `ADMIN` role has three divergent implementations and the moderator role is not deployable | HIGH | Open | Security / Architecture (Role model) | 15-authz-AUTHZ-003 |
| AUTHZ-004 | `GET /login/issue/` performs an unauthenticated DB write outside CSRF protection and is cross-site triggerable | MEDIUM | Open | Security (CSRF) | 15-authz-AUTHZ-004 |
| AUTHZ-005 | `can_publish_ad()` has no production caller; the live publish gate checks one flag and omits `is_declined` | MEDIUM | Open | Maintainability / Security | 15-authz-AUTHZ-005 |
| AUTHZ-006 | `DailyAdMetricsAdmin.has_delete_permission()` returns `True` for `AnonymousUser` and for a SELLER | MEDIUM | Open | Security (Least privilege) | 15-authz-AUTHZ-006 |
| AUTHZ-007 | `ad_edit` authorizes on an unlocked read, then mutates a different, re-fetched, unlocked row | MEDIUM | Open | Security (IDOR / TOCTOU) | 15-authz-AUTHZ-007 |
| AUTHZ-008 | `staff_required_api` checks role before method and advertises a non-existent `Bearer` scheme | LOW | Open | Maintainability | 15-authz-AUTHZ-008 |
| AUTHZ-009 | No logging and no metrics on denied authorization decisions | LOW | Open | Observability | 15-authz-AUTHZ-009 |

## Distribution

**Severity counts**

| CRITICAL | HIGH | MEDIUM | LOW |
|----------|------|--------|-----|
| 0 | 3 | 4 | 2 |

**Status counts**

| Status | Count |
|--------|-------|
| Open | 9 |

> Status is `Open` for all findings in raw phase reports.

## Findings by Severity

### HIGH

#### AUTHZ-001: [HIGH] — No per-request account-state gate: a banned / consent-declined / GDPR-withdrawn seller keeps a working web session for 14 days

| Field | Value |
|---|---|
| **ID** | AUTHZ-001 |
| **Title** | No per-request account-state gate: a banned / consent-declined / GDPR-withdrawn seller keeps a working web session for 14 days |
| **Severity** | HIGH |
| **Category** | Security — Broken Access Control (OWASP A01); NIST SP 800-53 AC-2, AC-3 |
| **File(s)** | `src/backend/config/settings/base.py:196-211` (no gate middleware), `src/backend/apps/users/services/account_state.py:83-106`, `src/backend/apps/moderation/admin_actions.py:98-100`, `src/backend/apps/moderation/admin_actions.py:255`, `src/backend/apps/users/admin.py:55-65`, `src/telegram_bot/middlewares/permissions.py:24-135` (the gate that exists, bot-side only) |
| **Status** | Open |
| **Tracker** | 15-authz-AUTHZ-001 |
| **Problem** | The bot process evaluates `is_banned` / `is_deleted` / `is_declined` / `consent_revoked` on **every** inbound update through `AccountStateMiddleware`, but the web process has **no equivalent per-request check at all**. `can_login()` runs only once, at session creation in `login_status`, and afterwards nothing re-reads the account-state flags. `SESSION_COOKIE_AGE` is never overridden, so the Django default 1 209 600 s (14 days) applies. Three of the four revocation paths — `ban_user_for_ad` (admin_actions.py:98-100), `bulk_ban_users` (admin_actions.py:255) and `UserAdmin.withdraw_consent_action` (users/admin.py:55-65) — flip the flags and never touch the session. Only self-service `consent_withdraw` calls `logout()` (consent.py:256-259). This is *not* a re-filing of `AUT-002`: it is the Phase 15 §5(f) **gate** deliverable assigned to this phase, and it is the remediation vehicle for `AUT-002`. |
| **Impact** | A seller banned for abuse, a seller who has withdrawn consent under GDPR Article 7(3), and a seller who soft-deleted their account all keep a fully authenticated seller session for up to 14 days. During that window they can read their dashboard, create saved searches (which produce Telegram alert fan-out), edit, archive, delete and re-publish their own ads, and browse the full site as a logged-in user. For a GDPR-withdrawn identity this means the controller continues processing personal data — and continuing to send the seller alerts — after the erasure request. For a banned seller it means the ban is advisory for the web tier while it is absolute for the bot. |
| **Root Cause** | The authorization decision point for account state exists in two divergent shapes instead of one: the bot re-implements the decision inline in `AccountStateMiddleware._check_user_state` (permissions.py:160-190) on every update, while the web tier treats the login-time `can_login()` result as permanent. There is no middleware in `MIDDLEWARE` that re-evaluates account state, and `apps/users` exports no `is_session_valid`-style predicate for one to call. |
| **Recommendation** | **(a)** Extract the middleware's decision into `apps/users/services/account_state.py` as one shared predicate, e.g. `account_state_verdict(user) -> AccountStateVerdict(allowed: bool, reason: AccountStateReason)`, and have `AccountStateMiddleware` call it — so both processes share a single decision point. **(b)** Add `AccountStateGateMiddleware` in `apps/users/middlewares/`, registered in `MIDDLEWARE` immediately after `AuthenticationMiddleware`, that for every `request.user.is_authenticated` request re-reads the flags and, on DENY, calls `logout(request)` and returns `HttpResponseForbidden` (or a redirect for HTML). **(c)** Gate the DENY set on `is_banned`, `is_deleted`, `is_declined` and `consent_revoked` — the same four the bot already denies on. **`is_active` is already handled correctly and needs no work**: `ModelBackend.get_user()` honours `user_can_authenticate()`, verified below. **(d)** Do **not** fold the ad-visibility predicate (`user__is_declined=False` in `listings_query.py:135`, owned by Phase 08) into this gate — that predicate answers "is this ad publicly visible", this gate answers "is this session still authorized". They are two predicates with two owners and must stay separate. |
| **Effort** | S (1 person-day) |
| **Priority** | P0 |

| Field | Value |
|---|---|
| **CWE** | CWE-613 (Insufficient Session Expiration) / CWE-285 (Improper Authorization) |
| **Likelihood** | HIGH |
| **Related Findings** | AUT-002 (remediated by this gate — not duplicated), AUT-004, AUTHZ-005 |

**Evidence — session-revocation matrix** *(supports: "during the ban / decline / withdraw window the session is still fully authorized — `dashboard=200` and `save-search=200` under every account-state flag")*:
```text
### session revocation matrix (AUT-002 gate design input)
  baseline seller_b                      dashboard=200 archive=302 save-search=200
  is_banned=True                         dashboard=200 archive=302 save-search=200
  is_declined=True                       dashboard=200 archive=302 save-search=200
  is_deleted=True (GDPR soft-delete)     dashboard=200 archive=302 save-search=200
  consent_revoked_at set                 dashboard=200 archive=302 save-search=200
  is_active=False                        dashboard=302 archive=302 save-search=302
  is_banned=True (repeat, after unban)   dashboard=200 archive=302 save-search=200
  ADMIN GET seller-A's draft edit form -> 403 (no admin override)
```

**Evidence — `src/backend/config/settings/base.py:196-211`** *(supports: "the web middleware stack contains no account-state gate, while the bot has `AccountStateMiddleware`")*:
```python
MIDDLEWARE = [
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.core.middleware.language.LanguagePreMiddleware",
    "apps.core.middleware.city_resolution.CityResolutionMiddleware",
    "apps.core.middleware.preferred_city.PreferredCityMiddleware",
    "apps.core.middleware.js_check.JSExecutionMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_prometheus.middleware.PrometheusAfterMiddleware",
]
```

**Evidence — `src/backend/apps/moderation/admin_actions.py:98-100, 255`** *(supports: "2 of the 3 revocation paths flip a flag and never touch the session")*:
```python
        if not user.is_banned:
            user.is_banned = True
            user.save(update_fields=["is_banned"])          # no logout / no session flush
...
        User.objects.filter(id__in=user_ids).update(is_banned=True)   # bulk path, same omission
```

**Evidence — session policy at runtime** *(supports: "the exposure window is the full 14-day default")*:
```text
  SESSION_COOKIE_AGE      = 1209600 s = 14.0 days
  SESSION_SAVE_EVERY_REQUEST = False
  SESSION_EXPIRE_AT_BROWSER_CLOSE = False
  SESSION_ENGINE = django.contrib.sessions.backends.db
  middleware has AccountState equivalent: []
```

---
#### AUTHZ-002: [HIGH] — `submit_ad()` ignores the `user_id` it is handed — proven service-layer IDOR on another seller's draft

| Field | Value |
|---|---|
| **ID** | AUTHZ-002 |
| **Title** | `submit_ad()` ignores the `user_id` it is handed — proven service-layer IDOR on another seller's draft |
| **Severity** | HIGH |
| **Category** | Security — IDOR / Insecure Direct Object Reference (OWASP A01); NIST SP 800-53 AC-3 |
| **File(s)** | `src/backend/apps/ads/services/submission.py:54`, `src/backend/apps/ads/services/submission.py:169-173`, `src/backend/apps/ads/views/edit.py:91-101`, `src/telegram_bot/handlers/ad_create/submit.py:62-85` |
| **Status** | Open |
| **Tracker** | 15-authz-AUTHZ-002 |
| **Problem** | `SubmitAdInput` declares a `user_id: int \| None` field (submission.py:54) that reads as the authorized actor, but `submit_ad()` never compares it to the ad's owner. It locks and loads the row by `id` alone (`Ad.objects.select_for_update().get(id=input.ad_id)`, submission.py:171) and then overwrites title, description, category, city, price, features, images and status, and runs auto-moderation, which can publish it. Proven live: `submit_ad(ad_id=<B's DRAFT>, user_id=<A>)` returned `True` and left B's draft as `published` with A's injected title and price. |
| **Impact** | The single service both processes call to finalise an ad carries no ownership predicate, so object-level authorization for ads is delegated entirely to each caller. Today neither caller lets a foreign `ad_id` reach it (the web view pre-checks, the bot reads `ad_id` from the per-chat FSM), so no live cross-seller exploit exists. But the next caller that trusts the DTO — a new bot command, a management command, an API endpoint, a bulk job — silently becomes a cross-tenant write. The `user_id` field actively misleads a reviewer into believing the check exists. |
| **Root Cause** | The service is written as a trusted-internal orchestrator (it assumes its caller already authorized the ad) while its DTO advertises an actor identity. Nothing in the type signature, the docstring, or a test asserts that the DTO's `user_id` is meaningful, so the omission is invisible at review time. |
| **Recommendation** | Inside the existing `transaction.atomic()` block, immediately after the locked fetch, assert ownership and fail closed: `if ad.user_id != input.user_id: logger.warning(...); return False, ["Ad does not belong to this user"]`. Keep the DTO field (it is the correct seam) and add a regression test that calls `submit_ad` with a mismatched `user_id` and asserts the row is unchanged. Phase 05 owns the `Ad` state machine — this change adds a guard only, it does not alter `transition_to` / `auto_moderate` semantics. |
| **Effort** | S (0.5 person-day) |
| **Priority** | P0 |

| Field | Value |
|---|---|
| **CWE** | CWE-639 (Authorization Bypass Through User-Controlled Key) |
| **Likelihood** | MEDIUM |
| **Related Findings** | AUTHZ-007 (the caller-side TOCTOU on the same view), 05-VAL-003 / VAL-003 (dead approval path — not duplicated) |

**Evidence — `src/backend/apps/ads/services/submission.py:54, 169-173`** *(supports: "`user_id` is accepted in the DTO and never compared to the ad owner")*:
```python
    user_id: int | None          # line 54 — accepted, never used for authorization
...
    with transaction.atomic():
        try:
            ad = Ad.objects.select_for_update().get(id=input.ad_id)   # line 171 — no owner filter
        except Ad.DoesNotExist:
            return False, ["Ad not found"]
        # line 176+: ad.title/description/category/price overwritten unconditionally
        # line 230: ad.transition_to(AdStatus.ON_MODERATION) -> auto_moderate(ad) may publish
```

**Evidence — live service invocation** *(supports: "a wrong seller rewrote and published another seller's draft")*:
```text
### shared service ownership predicate — submit_ad()
  submit_ad(ad_id=B's draft, user_id=A) -> True []
  B's draft is now: title='A15 hijack' status=published price=999.00
```

---

#### AUTHZ-003: [HIGH] — The `ADMIN` role has three divergent implementations and the moderator role is not deployable

| Field | Value |
|---|---|
| **ID** | AUTHZ-003 |
| **Title** | The `ADMIN` role has three divergent implementations and the moderator role is not deployable |
| **Severity** | HIGH |
| **Category** | Security / Architecture — Role model (OWASP A01); NIST SP 800-53 AC-3, AC-6 |
| **File(s)** | `src/backend/apps/users/models.py:157-172`, `src/backend/apps/moderation/views/decorators.py:29, 53`, `src/backend/apps/ads/views/listings.py:186`, `src/backend/apps/users/admin.py:43-53`, `src/backend/apps/categories/admin.py:69`, all 17 `ModelAdmin` classes under `src/backend/apps/*/admin.py` |
| **Status** | Open |
| **Tracker** | 15-authz-AUTHZ-003 |
| **Problem** | `User.role` (models.py:157-172) is the declared single source of truth: `is_staff or is_superuser -> ADMIN`. Three layers do not use it. (1) `media_gate` gates on the raw `request.user.is_staff` (listings.py:186), so a superuser with `is_staff=False` is denied media that `staff_required` would allow. (2) Django's own `AdminSite.has_permission` requires `is_staff`, so the same superuser is redirected to the login page on **all 17** `/admin/` changelists — they are locked out of the entire admin. (3) 15 of 17 `ModelAdmin` classes declare no permission override, so they fall back to per-model `auth.Permission` checks; a moderator with only `is_staff=True` gets `403` on 12 of 17 admin models, and no seeding command, group, or fixture exists anywhere in the repo to grant them. The two that do override produce an inverted ladder: `UserAdmin.has_view_permission = is_staff` but `has_add_permission = is_superuser`, so a moderator can *edit* users (including their own `is_superuser` flag, per `AUT-005`) but not create one. |
| **Impact** | The moderator role — `is_staff`, which this project documents as *the* moderator role — cannot actually be used: a freshly elevated moderator can reach `Ad`, `AdImage`, `Category`, `City` and `User` and is silently refused on `LookupGroup`, `LookupItem`, `ModerationCriteria`, `ModeratorActionLog`, `SiteConfig`, `SupportContact`, `SupportTicket`, `AnalyticsEvent`, `DailyAdMetrics`, `ConsentRecord`, `LoginToken` and `Group`. Moderators therefore cannot moderate against the criteria, read the audit log, manage contact/support data, or grant anyone permissions. In the other direction a superuser who is not staff is denied the whole admin. Because `AUT-005` lets a moderator write `is_superuser` on their own row through `UserAdmin`, a moderator can self-escalate into a *broader* role than the intended `ADMIN` contract — the inconsistency is not only a usability problem. |
| **Root Cause** | The `UserRole` enum was introduced as a role model but was never wired into the layers that actually make authorization decisions. There is no shared `ModelAdmin` base class or permission mixin, so each admin class either re-implements the check against raw Django flags or silently inherits the per-model permission default. Nothing asserts at startup or in a test that `is_staff` is sufficient for the moderator role. |
| **Recommendation** | **(a)** Add a shared `AdminRolePermissionMixin` in `apps/core/admin.py` (or `apps/core/admin_base.py`) that all 17 admins inherit, resolving `ADMIN` via `request.user.role == UserRole.ADMIN` and gating `add` / `change` / `delete` on separate, explicit methods. **(b)** Replace `request.user.is_staff` in `media_gate` (listings.py:186) with the same `UserRole.ADMIN` predicate. **(c)** Decide the moderator contract in one place and document it: either (i) `is_staff` grants full `ADMIN` and every admin inherits the mixin with per-action opt-outs, or (ii) moderators get a `Group` and the deploy seeds it. Option (i) matches the existing `staff_required` decorator and the documented "`is_staff` IS the moderator role" position; option (ii) matches Django's model. Pick one and enforce it. **(d)** Add a test that iterates `admin.site._registry` and asserts a freshly provisioned moderator can reach the moderation-critical models. Note: this finding is scoped to *role resolution and provisioning*; the `UserAdmin` form defect itself is `AUT-005` / `04-AUT-004` / `PII-103` and is **not** re-filed here. |
| **Effort** | M (2-3 person-days) |
| **Priority** | P0 |

| Field | Value |
|---|---|
| **CWE** | CWE-269 (Improper Privilege Management) |
| **Likelihood** | HIGH |
| **Related Findings** | AUT-005 / 04-AUT-004 / PII-103 (referenced, not re-filed) |

**Evidence — per-`ModelAdmin` permission matrix** *(supports: "a plain `is_staff` moderator is denied on 12 of 17 admin models; a superuser who is not staff cannot view or change `users.User` at all")*:
```text
model                            ANON   SELLER   STAFF(is_staff,no perms)   SUPER(is_staff=False)
ads.Ad                           F/F/F/F        F/F/F/F        True/True/False/False     True/True/True/True
ads.AdImage                      F/F/F/F        F/F/F/F        True/False/False/False    True/False/False/False
lookups.LookupGroup              F/F/F/F        F/F/F/F        False/False/False/False   True/True/True/True
lookups.LookupItem               F/F/F/F        F/F/F/F        False/False/False/False   True/True/True/True
moderation.ModerationCriteria    F/F/F/F        F/F/F/F        False/False/False/False   True/True/False/False
moderation.ModeratorActionLog    F/F/F/F        F/F/F/F        False/False/False/False   True/False/False/False
core.SiteConfig                  F/F/F/F        F/F/F/F        False/False/False/False   True/True/False/False
core.SupportContact              F/F/F/F        F/F/F/F        False/False/False/False   True/True/True/True
users.ConsentRecord              F/F/F/F        F/F/F/F        False/False/False/False   True/True/False/True
users.User                       F/F/F/F        F/F/F/F        True/True/False/False     False/False/True/True   <-- inverted
legend: view/change/add/delete
```

**Evidence — effective HTTP status per role** *(supports: "the superuser-not-staff is redirected to login on every admin changelist (302), i.e. has zero admin access, while `staff_required` says the same identity is `ADMIN`")*:
```text
  /admin/ads/ad/                     ANON= 302 SELLER= 302 STAFF= 200 SUPER= 302
  /admin/lookups/lookupitem/         ANON= 302 SELLER= 302 STAFF= 403 SUPER= 302
  /admin/moderation/moderationcriterion/  ANON= 302 SELLER= 302 STAFF= 403 SUPER= 302
  /admin/users/user/                 ANON= 302 SELLER= 302 STAFF= 200 SUPER= 302
### R4b non-Django admin surfaces (staff_required decorator)
  staff_required(is_superuser)       -> OK            <-- role says ADMIN
```

**Evidence — three implementations of one predicate** *(supports: "`User.role`, `media_gate` and `ModelAdmin` each answer "is this an admin" differently")*:
```python
# apps/users/models.py:157-172          the declared source of truth
    @property
    def role(self) -> UserRole:
        if self.is_staff or self.is_superuser: return UserRole.ADMIN
        ...

# apps/moderation/views/decorators.py:29,53   the app's own gate — uses role
        if not request.user.is_authenticated or request.user.role != UserRole.ADMIN: raise Http404

# apps/ads/views/listings.py:186               a third answer — raw is_staff
    if request.user.is_staff:

# apps/users/admin.py:43-53                    a fourth answer — raw flags, inverted
    def has_add_permission(self, request): return request.user.is_superuser
    def has_change_permission(self, request, obj=None): return request.user.is_staff
```

---
### MEDIUM

#### AUTHZ-004: [MEDIUM] — `GET /login/issue/` performs an unauthenticated DB write outside CSRF protection and is cross-site triggerable

| Field | Value |
|---|---|
| **ID** | AUTHZ-004 |
| **Title** | `GET /login/issue/` performs an unauthenticated DB write outside CSRF protection and is cross-site triggerable |
| **Severity** | MEDIUM |
| **Category** | Security — CSRF / unsafe method (OWASP A01); NIST SP 800-53 SC-13 |
| **File(s)** | `src/backend/apps/users/views/consent.py:297-342` (`login_issue`), `src/backend/apps/users/urls.py:20` |
| **Status** | Open |
| **Tracker** | 15-authz-AUTHZ-004 |
| **Problem** | `login_issue` is registered as `GET /login/issue/` and has no `@require_POST`. Every request inserts a `LoginToken` row (`LoginToken.objects.create(...)`, consent.py:326). Django's `CsrfViewMiddleware` never engages on a safe method, so this is the only write endpoint in the application that carries no CSRF token, and it is reachable by a plain cross-site `<img src>`, `<link>`, redirect or prefetch from an anonymous visitor with no interaction. |
| **Impact** | An attacker page can mass-create `login_tokens` rows (10 requests / 60 s per IP, `login_rate_limit.py:19-20`) and consume the login-issue rate-limit budget of real users on the same egress IP, degrading the Telegram login funnel. There is no account-takeover or data-disclosure path: the token must still be claimed by a Telegram identity to be useful, and it expires in 5 minutes. **Severity note for the validator:** a literal reading of the phase taxonomy ("state-changing web request accepted without a valid CSRF token" = CRITICAL) would rate this CRITICAL; I have rated it MEDIUM because the request is a `GET` (the taxonomy entry assumes POST/PUT/DELETE), the write is rate-limited, the row is short-lived, and no identity, session or protected resource is affected. Flagging the ambiguity explicitly rather than deciding it silently. |
| **Root Cause** | The endpoint was given a `GET` route because it renders a page, and the write it performs was treated as a side effect of rendering rather than as the operation the route exists for. Nothing in the code review path flags "this view mutates state" — there is no `require_POST` and no test asserting the method. |
| **Recommendation** | Change the route to `POST /login/issue/` with `@require_POST`, and have `login_issue.html` submit a small CSRF-protected form (or an HTMX `hx-post`) that receives the deep link via the response. If a bare `GET` deep link must keep working, split the concern: `GET` renders the page, `POST` issues the token, and `GET` never writes. Keep both existing rate limits. This finding is scoped to the **CSRF exposure of the endpoint**; Phase 04 owns the `LoginToken` issuance/claim mechanics and `AUT-001` (token not bound to the issuing browser session) — do not let the two fixes overlap. |
| **Effort** | S (0.5 person-day) |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **CWE** | CWE-352 (Cross-Site Request Forgery) |
| **Likelihood** | MEDIUM |
| **Related Findings** | AUT-001, 04-AUT-00x (LoginToken mechanics — referenced, not re-filed) |

**Evidence — `src/backend/apps/users/urls.py:20` + `consent.py:297-342`** *(supports: "a GET route that unconditionally inserts a row, with no `require_POST` and therefore no CSRF token")*:
```python
    path("login/issue/", login_issue, name="login_issue"),          # urls.py:20
...
@never_cache                                            # consent.py:297 — no @require_POST
def login_issue(request: HttpRequest) -> HttpResponse:
    if not check_deep_link_render_rate_limit(request): return HttpResponse(status=429)
    if not login_rate_limit_check(request):              return HttpResponse(status=429)
    raw_token = secrets.token_urlsafe(24)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    LoginToken.objects.create(                           # consent.py:326 — DB WRITE on GET
        token_hash=token_hash, expires_at=timezone.now() + timedelta(minutes=5),
    )
```

**Evidence — live probe with `enforce_csrf_checks=True`** *(supports: "the write happens with no CSRF token, is repeatable, and is not blocked by a hostile `Referer`")*:
```text
### CSRF: /login/issue/ is a GET that WRITES a LoginToken row
  GET /login/issue/ -> 200; LoginToken rows 3 -> 4 (no CSRF token supplied)
  second GET -> 5 rows total (repeatable, no CSRF)
  GET with hostile Referer -> 200; rows now 6
```

---

#### AUTHZ-005: [MEDIUM] — `can_publish_ad()` has no production caller; the live publish gate checks one flag and omits `is_declined`

| Field | Value |
|---|---|
| **ID** | AUTHZ-005 |
| **Title** | `can_publish_ad()` has no production caller; the live publish gate checks one flag and omits `is_declined` |
| **Severity** | MEDIUM |
| **Category** | Maintainability / Security — divergent authorization predicate |
| **File(s)** | `src/backend/apps/users/services/account_state.py:51-80`, `src/backend/apps/users/services/__init__.py:6,20`, `src/telegram_bot/middlewares/permissions.py:192-220`, `src/backend/apps/core/services/contact.py:27-45` |
| **Status** | Open |
| **Tracker** | 15-authz-AUTHZ-005 |
| **Problem** | `can_publish_ad()` is defined, exported from the `apps.users.services` package and covered by `test_account_state.py`, but a whole-repo grep finds only three non-test references: the definition and the two re-export lines. It gates nothing. The only publish authorization in production is `AccountStateMiddleware._check_publish_permission` (permissions.py:192-220), which checks `ads_auto_publish` **alone** and returns `(True, "")` for an unregistered identity. The documented predicate is also wrong for a browse-only seller: `can_publish_ad(User(is_declined=True))` returns `True`, because it tests only `is_banned`, `is_deleted` and `ads_auto_publish`. |
| **Impact** | The "shared publish predicate" the architecture expects does not exist, and the predicate that *is* documented returns the wrong answer for the DECLINE state. Today a declined seller is still blocked, but only because `_check_user_state` denies them earlier for an unrelated reason. Any new caller that reaches for the documented, tested, exported `can_publish_ad()` would authorize publishing for a consent-declined account — the exact state the consent banner is designed to prevent. Four independent copies of the account-state decision now exist (`can_login`, `can_publish_ad`, `AccountStateMiddleware`, `_check_seller_contactable` in `core/services/contact.py:27-45`), and they disagree. |
| **Root Cause** | The predicate was written to spec and unit-tested in isolation but never wired into either process. Because the unit test asserts the current (incorrect) flag set, the test suite actively protects the wrong behaviour. |
| **Recommendation** | Fold this into the single shared predicate introduced by `AUTHZ-001`: have `_check_publish_permission` call the same `account_state_verdict()` that the web gate will call, so the publish decision is derived from one flag set. Add `is_declined` to that verdict's publish branch so the documented semantic ("browse-only") is the enforced one. Then either delete `can_publish_ad` and update `test_account_state.py` to target the new predicate, or keep it as a thin wrapper over the verdict. Do not ship both. |
| **Effort** | S (0.5 person-day) |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **CWE** | CWE-285 (Improper Authorization) |
| **Likelihood** | LOW |
| **Related Findings** | AUTHZ-001 (the shared predicate this folds into), SRCH-008 / `is_banned` in search — **explicitly NOT re-filed** per the Phase 08 validator ruling recorded at `15-audit-authorization.md:132` |

**Evidence — dead predicate + wrong flag set** *(supports: "`can_publish_ad` gates nothing and returns True for a declined seller")*:
```text
### dead predicate check — can_publish_ad callers
  non-test references to can_publish_ad: 3
    /app/src/backend/apps/users/services/account_state.py:51:def can_publish_ad(user: User) -> bool:
    /app/src/backend/apps/users/services/__init__.py:6:    can_publish_ad,
    /app/src/backend/apps/users/services/__init__.py:20:    "can_publish_ad",
### cross-process predicate inventory
  can_login(banned)=False can_login(declined)=False can_login(deleted)=True can_login(inactive)=True
  can_publish_ad(banned)=False can_publish_ad(deleted)=False can_publish_ad(declined)=True
```

**Evidence — `src/telegram_bot/middlewares/permissions.py:192-220`** *(supports: "the only live publish gate checks `ads_auto_publish` alone and allows unregistered identities")*:
```python
        if not state.ads_auto_publish:
            return (False, _("Your account has publishing restrictions. ..."))
        return (True, "")
    # and, in _check_user_state:
        except User.DoesNotExist:
            return (True, "")  # User not registered yet
```

---
#### AUTHZ-006: [MEDIUM] — `DailyAdMetricsAdmin.has_delete_permission()` returns `True` for `AnonymousUser` and for a SELLER

| Field | Value |
|---|---|
| **ID** | AUTHZ-006 |
| **Title** | `DailyAdMetricsAdmin.has_delete_permission()` returns `True` for `AnonymousUser` and for a SELLER |
| **Severity** | MEDIUM |
| **Category** | Security — Least privilege (OWASP A01); NIST SP 800-53 AC-6 |
| **File(s)** | `src/backend/apps/analytics/admin.py:99-101` |
| **Status** | Open |
| **Tracker** | 15-authz-AUTHZ-006 |
| **Problem** | The override ignores its `request` argument entirely and returns a constant `True`, so the per-model permission check grants delete to *every* identity, including `AnonymousUser` and an ordinary seller. Verified live: `has_delete_permission(AnonymousUser) = True`, `has_delete_permission(SELLER) = True`. The request is currently blocked one layer up, because `AdminSite.has_permission()` (`is_active and is_staff`) refuses the session first, so the HTTP result is a `302` to `/admin/login/`. The sibling `AnalyticsEventAdmin` two classes above does the same thing correctly — it returns `False` unconditionally. |
| **Impact** | An authorization check that grants an operation to the entire internet is only safe because a different, unrelated check happens to run first. Any relaxation of the site-level gate, any `ModelAdmin` subclass reuse, or any code that consults `has_delete_permission()` for UI or API decisions would grant anonymous deletion of analytics rows. The `True` also makes the admin's own UI (delete buttons, `has_delete_permission` in templates) inconsistent with the effective behaviour, and it removes the only place where a future per-model rule could live. |
| **Root Cause** | The method was written to express "metrics are deletable for cleanup" and was read as a statement about the data rather than as a decision about the actor. The `request` parameter is accepted but never consulted, so the function is not an authorization check at all. |
| **Recommendation** | Change it to mirror the sibling and to route through the role model: `return request.user.role == UserRole.ADMIN and request.user.is_superuser`. Delete access to aggregated metrics is a superuser operation, consistent with `has_add_permission = False` / `has_change_permission = False` on the same class. Add the same `request`-consulting assertion to the other `has_*_permission` overrides in the repo that currently return constants. |
| **Effort** | S (0.25 person-day) |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **CWE** | CWE-862 (Missing Authorization) |
| **Likelihood** | LOW |
| **Related Findings** | AUTHZ-003 (the shared `ADMIN` predicate this should use) |

**Evidence — `src/backend/apps/analytics/admin.py:91-101`** *(supports: "the three overrides return constants; the delete one is `True` regardless of the request")*:
```python
    def has_add_permission(self, request):
        """Metrics are created by management command, not via admin."""
        return False

    def has_change_permission(self, request, obj=None):
        """Metrics are read-only."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Metrics can be deleted for cleanup."""
        return True                      # <-- request never consulted
```

**Evidence — live probe** *(supports: "granted to anonymous and to a SELLER; blocked only by the site-level `is_staff` gate")*:
```text
### DailyAdMetricsAdmin.has_delete_permission reachability
  has_delete_permission(AnonymousUser) = True
  admin_site.has_permission(AnonymousUser) = False
  has_delete_permission(SELLER)        = True
  admin_site.has_permission(SELLER)     = False
  HTTP POST delete as SELLER -> 302 (/admin/login/?next=/admin/analytics/dailyadmetrics/1/delete/)
  HTTP POST delete as ANON   -> 302
```

---

#### AUTHZ-007: [MEDIUM] — `ad_edit` authorizes on an unlocked read, then mutates a different, re-fetched, unlocked row

| Field | Value |
|---|---|
| **ID** | AUTHZ-007 |
| **Title** | `ad_edit` authorizes on an unlocked read, then mutates a different, re-fetched, unlocked row |
| **Severity** | MEDIUM |
| **Category** | Security — IDOR / TOCTOU (OWASP A01); NIST SP 800-53 AC-3 |
| **File(s)** | `src/backend/apps/ads/views/edit.py:91-101` (check), `src/backend/apps/ads/views/edit.py:116-117` (re-fetch) |
| **Status** | Open |
| **Tracker** | 15-authz-AUTHZ-007 |
| **Problem** | `ad_edit` performs its ownership check on an unlocked `get_object_or_404(Ad, id=ad_id)` at line 91-101, then, for POST, opens a transaction and re-reads the row with `get_object_or_404(Ad.objects.select_for_update(), id=ad_id)` at line 116-117. The re-read is **not** re-authorized, and it is the instance that every subsequent branch mutates and hands to `submit_ad`. The two reads are separate queries on separate snapshots. |
| **Impact** | The ownership decision and the mutation are not made against the same row version, so the guarantee "you may only edit what you own" holds only for as long as nobody changes `ad.user_id` between the two statements. The only writer that can do that is the admin form (`AdAdmin` exposes `user` as an editable field — `AD-001`), so the window is narrow but real and it is exactly the race the phase's §7 edge cases call out ("race between an ownership check and a concurrent ownership transfer"). A moderator reassigning an ad while a seller submits an edit would let the seller's write land on a row that is no longer theirs. |
| **Root Cause** | The row lock (added for DB-003) was introduced around the mutation without moving the authorization inside the same critical section, so the check and the lock are in different scopes. |
| **Recommendation** | Move the ownership assertion inside `transaction.atomic()` and perform it on the locked instance: after line 117, add `if ad.user_id != request.user.id: return HttpResponseForbidden(...)` and drop the earlier unlocked check for the POST path (keep it for the GET path, which needs the object to render). Then use that single locked instance throughout — the re-fetch inside the reactivation branch (line 178) and the `Ad.objects.prefetch_related(...).get(id=ad_id)` in the two error branches should also be the authorized locked row. This is a strict improvement over both the current code and `AUTHZ-002`'s service-side guard; the two compose. |
| **Effort** | S (0.5 person-day) |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **CWE** | CWE-367 (TOCTOU Race Condition) |
| **Likelihood** | LOW |
| **Related Findings** | AUTHZ-002 (the same view, service-side guard), AD-001 (`AdAdmin` exposes `user` — referenced, not re-filed) |

**Evidence — `src/backend/apps/ads/views/edit.py:91-101, 116-117`** *(supports: "the check runs on a different query than the mutation, and the re-fetch is unauthorized")*:
```python
    ad = get_object_or_404(Ad, id=ad_id)                       # line 91  — unlocked read
    if ad.user_id != request.user.id:                          # line 94  — check here
        logger.warning("User %s attempted to edit ad %s owned by %s", ...)
        return HttpResponseForbidden(_("You do not have permission to edit this ad."))
...
    with transaction.atomic():
        ad = get_object_or_404(Ad.objects.select_for_update(), id=ad_id)   # line 117 — no re-check
        # everything below mutates THIS instance and passes its ad_id to submit_ad
```

**Evidence — cross-seller attempts are nevertheless denied today** *(supports: "severity is MEDIUM, not CRITICAL — the current behaviour is correct, the structure is what is unsound")*:
```text
### R2 IDOR — SELLER_A against SELLER_B resources
  SELLER_A GET  /1/edit/      -> 403      (PUBLISHED,  B's)
  SELLER_A GET  /2/edit/      -> 403      (DRAFT,     B's)
  SELLER_A GET  /3/edit/      -> 403      (ON_MODERATION, B's)
  SELLER_A POST /1/archive/   -> 403
  SELLER_A POST /1/delete/    -> 403
  SELLER_A POST /2/reactivate/-> 403
  SELLER_A GET  /cabinet/saved-searches/1/edit/  -> 404   (B's saved search)
  SELLER_A POST /cabinet/saved-searches/1/toggle/-> 403
  -- owner sanity --  SELLER_A GET own edit -> 200
```

---

### LOW

#### AUTHZ-008: [LOW] — `staff_required_api` checks role before method and advertises a non-existent `Bearer` scheme

| Field | Value |
|---|---|
| **ID** | AUTHZ-008 |
| **Title** | `staff_required_api` checks role before method and advertises a non-existent `Bearer` scheme |
| **Severity** | LOW |
| **Category** | Maintainability / Correctness |
| **File(s)** | `src/backend/apps/moderation/views/decorators.py:36-58` |
| **Status** | Open |
| **Tracker** | 15-authz-AUTHZ-008 |
| **Problem** | The decorator resolves the identity, then the role, then the method, in that order. Two consequences: (1) the `401` response carries `WWW-Authenticate: Bearer`, but the system has no bearer authentication on this endpoint — the only credential is a Django session cookie — so the challenge is factually wrong and will mislead any client or on-call engineer; (2) an `ADMIN` sending a `GET` passes the role check, falls through the method check, and reaches `bulk_moderation_action`, which then fails on an empty body and returns `422` instead of the `405` the decorator documents. |
| **Impact** | No unauthorized access — the role check is correct and does fail closed. The cost is diagnostic: a `422` on a wrong-method request and a bogus auth challenge send the next person looking for a bearer-token bug that does not exist. This is the only API-shaped authorization surface in the repository, so it is the pattern future endpoints will copy. |
| **Root Cause** | The decorator was written as three independent early returns in the wrong order, and the `WWW-Authenticate` header was added by analogy with a token-authenticated API rather than from the actual credential model. |
| **Recommendation** | Check `request.method` first and return `405`; then return `401` **without** the `WWW-Authenticate` header (or, if the header is wanted for future-proofing, use a scheme name that matches the real credential, e.g. `Session`). Both changes are one-line reorders. |
| **Effort** | S (0.25 person-day) |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **CWE** | CWE-209 (Generation of Error Message Containing Sensitive Information) — borderline; no sensitive data is disclosed |
| **Likelihood** | LOW |
| **Related Findings** | AUTHZ-003 |

**Evidence — `src/backend/apps/moderation/views/decorators.py:45-57`** *(supports: "role is checked before method, and the 401 advertises a scheme the system does not implement")*:
```python
    def wrapper(request: HttpRequest, *args: object, **kwargs: object) -> JsonResponse:
        if not request.user.is_authenticated:
            return JsonResponse(
                {"error": "Authentication required"}, status=401,
                headers={"WWW-Authenticate": "Bearer"},     # no bearer auth exists
            )
        if request.user.role != UserRole.ADMIN:
            return JsonResponse({"error": "Staff access required"}, status=403)
        if request.method != "POST":                        # method checked last
            return JsonResponse({"error": "POST required"}, status=405)
        return view_func(request, *args, **kwargs)
```

**Evidence — live probe** *(supports: "the role gate itself is correct and fails closed in both directions")*:
```text
  staff_required_api(AnonymousUser) -> <JsonResponse status_code=401>
  staff_required_api(SELLER)         -> <JsonResponse status_code=403>
  staff_required_api(ADMIN, GET)     -> OK          <-- falls through to the view
  POST /moderation/api/v1/bulk-action/  ANON=401 SELLER=403 STAFF=200 SUPER=200
```

---

#### AUTHZ-009: [LOW] — No logging and no metrics on denied authorization decisions

| Field | Value |
|---|---|
| **ID** | AUTHZ-009 |
| **Title** | No logging and no metrics on denied authorization decisions |
| **Severity** | LOW |
| **Category** | Observability |
| **File(s)** | `src/backend/apps/moderation/views/decorators.py:19-58`, `src/backend/apps/ads/views/favorite.py:40-46` |
| **Status** | Open |
| **Tracker** | 15-authz-AUTHZ-009 |
| **Problem** | The two shared authorization decorators emit nothing when they deny. `staff_required` raises a bare `Http404("Not found")` and `staff_required_api` returns a JSON error body; neither logs the identity, the reason, or the path. `toggle_favorite` returns the `login_prompt` fragment to an anonymous caller without logging. The ad-ownership denials in `edit.py` / `delete.py` *do* log (`logger.warning("User %s attempted to edit ad %s owned by %s")`), so the codebase is already inconsistent. `django_prometheus` is installed and the endpoints are wrapped by `PrometheusBeforeMiddleware`, but there is no authorization-denial counter. |
| **Impact** | Repeated IDOR probing, a broken privilege-escalation attempt, or a misconfigured moderator cannot be detected from the logs, and the failure is silent. A `403` denial and a genuine "row does not exist" are indistinguishable in the audit trail because both arrive as `404`/`403` with no record of which check fired. This is the single cheapest signal for catching `AUTHZ-002` and `AUTHZ-003` being exploited in the wild. |
| **Root Cause** | Denials were treated as control flow rather than as events worth recording; the existing `logger.warning` calls in the ad views were added ad hoc rather than centralised in the shared decorators. |
| **Recommendation** | Log every denial in the shared decorators with a stable reason code, matching the existing style in `edit.py`: `logger.warning("authz.deny reason=%s user=%s path=%s", reason, request.user.pk, request.path)`. Add a `django_prometheus.Counter` named `authz_denials_total` labelled by `reason` and increment it at the same points. The project rule "no `print()`, use `logging`" already applies — this is a consistency and observability fix, not a new pattern. |
| **Effort** | S (0.5 person-day) |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **CWE** | CWE-778 (Insufficient Logging) |
| **Likelihood** | MEDIUM |
| **Related Findings** | AUTHZ-002, AUTHZ-003, AUTHZ-006 |

**Evidence — `src/backend/apps/moderation/views/decorators.py:27-33`** *(supports: "the shared admin gate denies silently")*:
```python
    @wraps(view_func)
    def wrapper(request: HttpRequest, *args: object, **kwargs: object) -> object:
        if not request.user.is_authenticated or request.user.role != UserRole.ADMIN:
            raise Http404("Not found")          # no logger call anywhere in this module
        return view_func(request, *args, **kwargs)
```

**Evidence — `src/backend/apps/ads/views/delete.py:45-53`** *(supports: "the codebase is already inconsistent — the ad views do log, the shared decorators do not")*:
```python
        # Authorization check: must own the ad
        if ad.user_id != request.user.id:
            logger.warning(
                "User %s attempted to delete ad %s owned by %s",
                request.user.id, ad_id, ad.user_id,
            )
            return HttpResponseForbidden(_("You do not have permission to delete this ad."))
```

---

## Cross-Finding Analysis

- **Merge candidates:** `AUTHZ-003` and `AUTHZ-006` share the root cause "each `ModelAdmin` re-implements (or omits) its own role check instead of using one shared predicate". They are kept separate because the fixes are different in kind: `AUTHZ-003` needs a shared mixin plus a documented moderator contract, `AUTHZ-006` is a one-line constant. Merge only if a single "admin authorization base class" change absorbs both. `AUTHZ-001` and `AUTHZ-005` also overlap — `AUTHZ-005`'s fix is explicitly folded into `AUTHZ-001`'s shared predicate — and must be delivered in one commit to avoid two competing account-state predicates.
- **Conflicting evidence:** none. The two apparent conflicts both resolve on inspection: (a) `is_active=False` returns `302` in the session matrix while `can_login(inactive)=True` — these are different layers (`ModelBackend.get_user()` honours `user_can_authenticate()`, `can_login()` does not), and the `can_login` half is `AUT-004`, already owned by Phase 04; (b) `submit_ad` accepted a foreign `user_id` yet no HTTP/bot entrypoint could reach it — the service defect is real, the exploitability is not.
- **Dependency chains:** `AUTHZ-002` -> `AUTHZ-007` (both guard the same write path; landing `AUTHZ-002` first makes `AUTHZ-007` defence-in-depth rather than load-bearing). `AUTHZ-001` -> `AUTHZ-005` (the shared predicate is created by `AUTHZ-001`; `AUTHZ-005` folds into it). `AUTHZ-003` -> `AUTHZ-006` (the shared mixin should supply the correct predicate `AUTHZ-006` currently hardcodes to `True`).
- **Verified, NOT re-filed (phase-05 dead approval path, `05-VAL-003` / VAL-003):** `approve_ad()` returned `False` for both `ON_MODERATION` and `ON_MODERATION_FAILED`; `bulk_approve(2 rows)` returned `0`; `POST /moderation/approve/<id>/` returned `404` for every role; `POST /moderation/review/<id>/approve/` returned `404` because the route does not exist (`moderation/urls.py:16` is `approve/<int:ad_id>/`). Confirmed dead and confirmed owned by Phase 05 — the only authorization-relevant observation added here is that `reject` and `ban` remain the sole working moderator write actions.
- **Verified, NOT re-filed (already-confirmed defects):** `AUT-005` / `04-AUT-004` / `PII-103` — the `UserAdmin` auto-built form exposes `password` as a plain `CharField` / `AdminTextInputWidget` among 25 base fields with `save_model` / `save_form` inherited (no hashing hook), alongside `is_staff` / `is_superuser`. `AD-001` — `AdAdmin` exposes `status`, `user`, `published_at`, `original_published_at`, `archived_at`, `deleted_at` among 29 base fields. Both were reproduced here and are referenced by ID only.
- **Deliberately NOT filed, per ownership boundaries:** `SRCH-008` / `is_banned` in search (Phase 08 validator ruling, `15-audit-authorization.md:132`); the two account-state predicates `(A) ad-visibility` in `listings_query.py` and `(B) audience/account-state` in `apps/users` remain separate and are not collapsed in `AUTHZ-001`'s recommendation; `AUT-001`, `AUT-002` (only the *gate* is delivered here), `PII-104` and all of Phase 04/05/06/07/09's findings.
- **Clean by runtime evidence (methodology, not findings):** R2/R3 IDOR denied on every seller-owned resource type (ad in 3 statuses, draft, saved search, media key); `media_gate` returns `403` for a `DRAFT` ad's image to anonymous and to a seller; the anonymous favourite tap persists nothing (`AdFavorite` rows by A for B's ad = 0) and returns the `login_prompt` fragment; `staff_required` returns an indistinguishable `404` to anonymous and to a seller, so admin URLs are not leaked; every one of 13 state-changing POSTs was refused without a CSRF token; `staff_required_api` returned `401`/`403` for anonymous/seller; `CSRF_COOKIE_SECURE` / `HTTPONLY` / `SAMESITE` are `True` / `True` / `Lax` in `base.py` and the emitted `Set-Cookie` carries `HttpOnly; SameSite=Lax; Secure`; `is_active=False` correctly kills a live web session.

## Remediation Roadmap

| Order | ID | Severity | Effort | Priority | Recommendation (summary) |
|-------|----|----------|--------|----------|--------------------------|
| 1 | AUTHZ-001 | HIGH | S | P0 | Add `AccountStateGateMiddleware` (web) over one shared `account_state_verdict()` predicate that `AccountStateMiddleware` also calls; DENY on `is_banned`/`is_deleted`/`is_declined`/`consent_revoked` |
| 2 | AUTHZ-003 | HIGH | M | P0 | Introduce a shared `AdminRolePermissionMixin` resolving `ADMIN` via `UserRole.ADMIN`; replace `media_gate`'s raw `is_staff`; write down the moderator contract and test it against `admin.site._registry` |
| 3 | AUTHZ-002 | HIGH | S | P0 | Assert `ad.user_id == input.user_id` on the locked row inside `submit_ad`'s transaction; return `(False, [...])` on mismatch; add a regression test |
| 4 | AUTHZ-005 | MEDIUM | S | P1 | Deliver together with AUTHZ-001: the shared predicate becomes the only publish gate; add `is_declined` to the publish branch; delete or wrap `can_publish_ad` and retarget `test_account_state.py` |
| 5 | AUTHZ-004 | MEDIUM | S | P1 | Move token issuance to `POST /login/issue/` with `@require_POST` so CSRF applies |
| 6 | AUTHZ-006 | MEDIUM | S | P1 | Make `DailyAdMetricsAdmin.has_delete_permission` consult `request` (`role == ADMIN and is_superuser`) instead of returning `True` |
| 7 | AUTHZ-007 | MEDIUM | S | P1 | Move the ownership assertion inside `ad_edit`'s `transaction.atomic()` and re-check on the `select_for_update` instance |
| 8 | AUTHZ-009 | LOW | S | P2 | Log every authorization denial with a stable reason code and add an `authz_denials_total` Prometheus counter |
| 9 | AUTHZ-008 | LOW | S | P2 | Reorder `staff_required_api` to check the method first; drop or correct the `WWW-Authenticate: Bearer` header |

## Rollout Safety

| ID | Risk | Backward-compatible? | Test gap (must cover) |
|----|------|----------------------|-----------------------|
| AUTHZ-001 | **Med** — a newly introduced gate will terminate live sessions the moment a moderator bans a user. That is the intent, but it will look like a bug in the first 24 h, and an over-broad DENY set (e.g. including `ads_auto_publish`) would lock out legitimate restricted sellers. | Yes (public routes untouched) | Needs: banned / declined / soft-deleted / consent-revoked / `is_active=False` each ⇒ 403 + `logout()`; anonymous and public routes unaffected; a restricted-but-valid seller (`ads_auto_publish=False`, nothing else) still reaches the dashboard; the bot's allow/deny answers are byte-identical before and after the extraction. |
| AUTHZ-003 | **High** — tightening a shared admin base class can revoke access that operators rely on today (e.g. the moderator's current `User`/`Ad` access), and loosening per-model defaults could expose `LookupItem`, `ModerationCriteria` or `SupportContact` to anyone with `is_staff`. Ship behind an explicit review of the 17-model matrix. | No — deliberate change to the moderator contract | Needs: a provisioned moderator can reach moderation-critical models; a seller and an anonymous user still get 302/403 on every `/admin/` URL; a superuser with `is_staff=False` is either given admin access or the docs say it is unsupported (pick one); `media_gate` answers identically for staff and superuser. |
| AUTHZ-002 | **Low** — a strict guard will surface any caller that was relying on the missing check. Confirm the web edit and bot submit paths still pass before merging. | Yes | Needs: `submit_ad` with a mismatched `user_id` leaves the row byte-identical and returns `(False, [...])`; the web text-edit and reactivation branches still succeed for the owner. |
| AUTHZ-005 | **Low** — retiring `can_publish_ad` requires rewriting `test_account_state.py`, which currently asserts the wrong flag set. | No — the predicate's answers change for `is_declined` | Needs: `is_declined=True` ⇒ publish denied from both the bot middleware and the shared predicate; `ads_auto_publish=False` ⇒ still denied; banned/deleted ⇒ still denied. |
| AUTHZ-004 | **Med** — making `/login/issue/` a POST means the login page's deep link is now behind a form post. If the page is opened directly from a bookmark, a messenger link, or a headless client, the flow must degrade gracefully. | No — the method and route change | Needs: `GET /login/issue/` no longer writes (or 405s); the CSRF-protected POST issues a token; the rate limits still apply; the bot's `/start login_<token>` handshake is unchanged. |
| AUTHZ-006 | **Low** — if a superuser currently relies on the accidental grant, nothing breaks (a superuser passes the new check). | Yes | Needs: `has_delete_permission` is `False` for `AnonymousUser` and a SELLER, `True` for a superuser; the HTTP delete view still returns `302` for non-staff. |
| AUTHZ-007 | **Med** — re-authorizing on the locked row changes the failure mode from `403` (current, correct) to a possible `403` in a *new* place, and the error-rendering branches re-fetch the ad. Verify the edit form still renders for the owner. | Yes | Needs: owner edit GET renders 200 and POST saves; non-owner GET and POST both 403; the row-lock (DB-003) is still taken. |
| AUTHZ-009 | **Low** — new log lines on denial paths will increase log volume; keep them at `WARNING` with a stable reason code so they are greppable and rate-limited by log level. | Yes | Needs: a denied request emits exactly one line containing the reason code and the user id; the counter increments once per denial. |
| AUTHZ-008 | **Low** — reordering means a wrong-method request from an ADMIN now returns `405` instead of `422`. Any client that keys on `422` must be updated. | No — status code change for admin clients | Needs: `GET /moderation/api/v1/bulk-action/` returns `405` for an ADMIN; the `401` and `403` responses are unchanged. |

## Appendices

### Appendix A — Full R1/R4 role-to-route matrix (46 URL/method pairs)

```text
METHOD URL                                  expected              ANON SELLER_A ADMIN
GET    /                                    public                200  200      200
GET    /search/                             public                200  200      200
GET    /api/search/autocomplete             public                200  200      200
GET    /1/                    (B's PUBLISHED ad)  public detail  200  200      200
GET    /media/a15/b.jpg          (B's PUBLISHED)  public media   404  404      404   (file absent in probe FS)
GET    /health/                             public                200  200      200
GET    /csp-report/                         public (GET?)         405  405      405
POST   /csp-report/                         public                403  403      403   (CSRF: browser reports carry no token)
GET    /dashboard/                          SELLER                302  200      200
GET    /analytics/trust/                    SELLER                302  200      200
GET    /cabinet/                            SELLER                302  200      200
GET    /cabinet/favorites/                  SELLER                302  200      200
GET    /cabinet/saved-searches/             SELLER                302  200      200
GET    /cabinet/search-history/             SELLER                302  200      200
GET    /2/edit/                 (B's DRAFT) SELLER (other owner)  302  403      403
POST   /2/archive/                          SELLER (other owner)  403  403      403
POST   /2/delete/                           SELLER (other owner)  403  403      403
POST   /2/reactivate/                       SELLER (other owner)  403  403      403
POST   /favorite/1/                         SELLER                403  403      403
POST   /save-search/                        SELLER                403  403      403
POST   /api/preferred-city/                 ANONYMOUS-ok          403  403      403
POST   /consent/accept/                     ANONYMOUS-ok          403  403      403
POST   /consent/decline/                    ANONYMOUS-ok          403  403      403
POST   /consent/withdraw/                   SELLER                403  403      403
POST   /login/status/                       ANONYMOUS-ok          403  403      403
GET    /login/issue/                        ANONYMOUS-ok          200  200      200   <-- AUTHZ-004: writes on GET
GET    /logout/                             ANONYMOUS             405  405      405   (POST-only)
GET    /moderation/queue/                   ADMIN                 404  404      200
GET    /moderation/review/3/                ADMIN                 404  404      200
POST   /moderation/approve/3/               ADMIN                 403  403      403   (CSRF; see AUTHZ-004 note)
POST   /moderation/reject/3/                ADMIN                 403  403      403
POST   /moderation/ban/3/                   ADMIN                 403  403      403
POST   /moderation/api/v1/bulk-action/      ADMIN                 403  403      403
GET    /analytics/moderation/               ADMIN                 404  404      200
GET    /admin/                              ADMIN                 302  302      200
GET    /admin/users/user/                   ADMIN                 302  302      200
GET    /admin/ads/ad/                       ADMIN                 302  302      200
GET    /admin/ads/adimage/                  ADMIN                 302  302      200
GET    /admin/lookups/lookupitem/           ADMIN                 302  302      403   <-- AUTHZ-003
GET    /admin/categories/category/          ADMIN                 302  302      200
GET    /admin/locations/city/               ADMIN                 302  302      200
GET    /admin/search/savedsearch/           ADMIN                 302  302      404
GET    /admin/moderation/moderationcriterion/ ADMIN               302  302      404
GET    /admin/analytics/analytics-event/    ADMIN                 302  302      404
GET    /admin/media/mediafile/              ADMIN                 302  302      404
GET    /admin/trust/sellertrustscore/       ADMIN                 302  302      404
GET    /admin/currencies/exchangerate/      ADMIN                 302  302      404
```

### Appendix B — R6 CSRF matrix (13 state-changing POSTs, `enforce_csrf_checks=True`)

```text
  SELLER_A no-token POST /4/archive/                        -> 403
  ANON       no-token POST /4/archive/                        -> 403
  SELLER_A no-token POST /4/delete/                         -> 403
  ANON       no-token POST /4/delete/                         -> 403
  SELLER_A no-token POST /5/edit/                           -> 403
  ANON       no-token POST /5/edit/                           -> 403
  SELLER_A no-token POST /favorite/4/                       -> 403
  ANON       no-token POST /favorite/4/                       -> 403
  SELLER_A no-token POST /save-search/                      -> 403
  ANON       no-token POST /save-search/                      -> 403
  SELLER_A no-token POST /api/preferred-city/               -> 403
  ANON       no-token POST /api/preferred-city/               -> 403
  SELLER_A no-token POST /consent/accept/                   -> 403
  ANON       no-token POST /consent/accept/                   -> 403
  SELLER_A no-token POST /consent/withdraw/                 -> 403
  ANON       no-token POST /consent/withdraw/                 -> 403
  SELLER_A no-token POST /moderation/approve/3/             -> 403
  ANON       no-token POST /moderation/approve/3/             -> 403
  SELLER_A no-token POST /moderation/ban/3/                 -> 403
  ANON       no-token POST /moderation/ban/3/                 -> 403
  SELLER_A no-token POST /moderation/api/v1/bulk-action/    -> 403
  ANON       no-token POST /moderation/api/v1/bulk-action/    -> 403
  SELLER_A no-token POST /cabinet/saved-searches/2/delete/  -> 403
  ANON       no-token POST /cabinet/saved-searches/2/delete/  -> 403
  SELLER_A no-token POST /cabinet/saved-searches/2/toggle/  -> 403
  ANON       no-token POST /cabinet/saved-searches/2/toggle/  -> 403
  SELLER_A no-token POST /cabinet/search-history/clear/     -> 403
  ANON       no-token POST /cabinet/search-history/clear/     -> 403
  SELLER_A bogus-token saved-search delete -> 403
  CSRF cookie settings: SECURE=False HTTPONLY=True SAMESITE=Lax   (test.py overrides Secure for plain HTTP)
  Set-Cookie on GET /: csrftoken=...; HttpOnly; Max-Age=31449600; Path=/; SameSite=Lax; Secure
  base.py:142-144 (prod/dev): CSRF_COOKIE_SECURE=True CSRF_COOKIE_HTTPONLY=True CSRF_COOKIE_SAMESITE="Lax"
```

### Appendix C — Phase-05 dead approval path, verified and attributed (NOT re-filed)

```text
### dead human moderation-approval path (attribution: phase 05)
  approve_ad(ON_MODERATION)        -> False
  approve_ad(ON_MODERATION_FAILED) -> False
  bulk_approve(2 rows)             -> 0
  statuses after: on_moderation_failed / on_moderation_failed
  ModeratorActionLog rows: 5        (auto_moderation entries only; no moderator-approval entry)
  POST /moderation/approve/8/ (ADMIN) -> 404
  GET  /moderation/review/8/ (ADMIN)  -> 200
  POST /moderation/review/8/approve/  -> 404  (documented URL in the phase-05 finding does not exist)
  POST /moderation/ban/8/      (ADMIN) -> 302  (ban_user works: no status filter)
  POST /moderation/reject/8/   (ADMIN) -> 302  (reject_user works: ON_MODERATION|ON_MODERATION_FAILED)
```

### Appendix D — Bot command → role map (R5)

```text
command / callback                    gate                                    unauthenticated identity
/start login_<token>                 none (public)                           ALLOWED by design (creates the user)
/start contact_<ad_id>               public; R2 gate in core/services/contact ALLOWED (browse-only)
/start contact_us                    public, rate-limited, bots rejected     ALLOWED
/start unsub_<token>                 _resolve_owned() -> stable chat_id      DENIED (no state change)
/alerts                               FSM user_id required                    DENIED ("Please login first")
/copy <ad_id>                        FSM user_id + copy_ad PermissionError   DENIED for another seller's ad
/post                                 FSM user_id required                    DENIED ("Please login first")
/cancel                               no user_id gate; acts on FSM ad_id only  N/A (per-chat FSM, no cross-tenant reach)
/language, lang_* callbacks           optional user_id; no server mutation   ALLOWED (no-op without a session)
support callbacks / SupportUsState    optional user_id                        ALLOWED (public support desk)
ad_create FSM steps (category/city/   FSM state reached only after /post      UNREACHABLE without a prior /post
  text/price/photos/preview/submit)     which is itself user_id-gated
AD-LEVEL CHECK: AccountStateMiddleware blocks banned / deleted / declined / consent-revoked on EVERY update;
  it returns (True, "") for an unregistered chat, which is correct because the per-command user_id gate
  then rejects. Verified live:
    _check_user_state(unregistered chat 999999999)        -> (True, '')   (unregistered, handlers re-gate)
    _check_publish_permission(unregistered chat)          -> (True, '')   <-- AUTHZ-005
Webhook sender verification: N/A — telegram_bot/main.py:130 uses dp.run_polling(bot); no webhook endpoint exists.
```