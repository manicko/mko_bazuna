# Code Context — Moderator Deactivation Privilege Guard

Audit of `C:\py_dev\mko_bazuna` @ `1257603`. Read-only investigation, no files modified.

## Original requirement

> moderators may deactivate ordinary sellers, but must not be able to deactivate staff/superusers/other moderators.

## 0. Headline finding

**The requirement is already implemented, verbatim, by commit `f2fd392` (`feat(users): give operators an account kill-switch (plan 18 B-1..B-5)`, 2026-10-02).** The exact sentence of the requirement is quoted in the service docstring at `src/backend/apps/users/services/deactivation.py`. The escalation guard exists at **both** layers (admin permission predicate + service target scope) and is pinned by 8 tests.

The real work left is (a) the *sibling* moderation lever `is_banned`, which has **no** privilege guard at all, (b) the fact that "moderator" is not a first-class role, and (c) several documented, deliberately-open residuals.

## 1. What is already implemented

### 1.1 Role model — there is no `MODERATOR` role

| Symbol | Path | Notes |
|---|---|---|
| `UserRole(StrEnum)` | `src/backend/apps/core/enums.py` | **Exactly 3 members:** `ANONYMOUS="anonymous"`, `SELLER="seller"`, `ADMIN="admin"`. Exported in `__all__`. |
| `User.role` (property) | `src/backend/apps/users/models.py` | `is_staff or is_superuser → ADMIN`; authenticated → `SELLER`; else `ANONYMOUS`. Docstring cites "Phase 15 spec". |

**There is no `is_moderator` field, no `MODERATOR` enum member, no roles Group, and no seeding of a moderator group anywhere in the repo.** "Moderator" is a *documented synonym* for the Django `is_staff` flag:

- `docs/01-spec/technical-specification.md`: "**Moderator = admin role** (no separate moderator role)."
- `docs/04-user-stories/admin-stories.md` header: "**Moderator = admin role** (no separate role, decision A)."
- `docs/01-spec/spec-index.md`: "moderator = admin role".
- `docs/02-database/db-enums.md` §UserRole: `ADMIN` → *Administrator/moderator* → `is_staff or is_superuser`.
- Provisioning: `src/backend/apps/core/management/commands/create_admin_user.py` only ever creates `is_staff=True, is_superuser=True`. There is **no** command that creates a moderator (`is_staff` only).

### 1.2 User model — status/flag fields

`src/backend/apps/users/models.py` → `class User(AbstractUser)`, `db_table = "users"`, `USERNAME_FIELD = "username"`.

Identity: `username` (nullable), `telegram_id`, `chat_id` (unique, never nullified).
Account state: `is_banned`, `is_deleted`, `is_declined`, `ads_auto_publish`, `telegram_premium`.
Lifecycle timestamps: `deleted_at`, `consent_given_at`, `consent_revoked_at`.
Other: `preferred_city`, `telegram_language`, `source`, custom `groups` / `user_permissions` `related_name="users"`.

**There is no custom manager or queryset on `User`.** `AccountStateMiddleware._resolve_user` depends on `User.objects.get(chat_id=...)` resolving *unfiltered* rows — `src/backend/apps/users/services/account_state.py` docstring explicitly forbids ever installing `account_state_q` on a manager.

`is_active` is the inherited Django field — the operator kill-switch.

### 1.3 Enums of statuses/actions

| Enum | Path | Members relevant here |
|---|---|---|
| `ModeratorActionType(StrEnum)` | `apps/core/enums.py` | `REJECT`, `BAN_ACCOUNT`, `SOFT_DELETE`, `CRITERIA_CHANGE`, `OTHER` — **no `deactivate`/`reactivate` member** |
| `BulkModerationAction(StrEnum)` | `apps/core/enums.py` | `APPROVE`, `REJECT`, `FLAG` |
| `BulkModerationError(StrEnum)` | `apps/core/enums.py` | stable client-facing error strings |
| `ApproveOutcome(StrEnum)` | `apps/core/enums.py` | `PUBLISHED`, `CRITERIA_REJECTED`, `TRANSITION_REFUSED` |
| `AccountState(NamedTuple)` | `apps/users/services/account_state.py` | `is_banned`, `is_deleted`, `is_declined`, `ads_auto_publish`, `consent_revoked` |
| `DeactivationResult(NamedTuple)` | `apps/users/services/deactivation.py` | `changed`, `skipped_self`, `skipped_privileged`, `already_in_state` |

**There is no account-status `StrEnum`.** Account state is 5 independent booleans — `apps/users/services/account_state.py` documents this (the docstring is stale: it says "Three independent flags" then returns five). Finding `18-D4` (whether these should be one concept) is recorded **undecided**.

### 1.4 The deactivation service (the requirement's home)

`src/backend/apps/users/services/deactivation.py` — **the single writer of the operator `is_active` lever.**

- `deactivate_users(queryset, actor) -> DeactivationResult`
- `reactivate_users(queryset, actor) -> DeactivationResult`
- `_resolve_targets(queryset, actor, *, target_is_active) -> tuple[QuerySet[User], DeactivationResult]` (private shared resolver)
- `class DeactivationResult(NamedTuple)`

Target scope logic in `_resolve_targets`:

```python
privileged = queryset.filter(is_staff=True) | queryset.filter(is_superuser=True)
if actor.is_superuser:
    permitted = queryset; skipped_privileged = 0
else:
    permitted = queryset.exclude(is_staff=True).exclude(is_superuser=True)
    skipped_privileged = privileged.exclude(pk=actor.pk).distinct().count()
skipped_self = queryset.filter(pk=actor.pk).count()
writable = permitted.exclude(pk=actor.pk).filter(is_active=not target_is_active)
```

Self-exclusion is checked first and is unconditional (applies to a superuser too). Both writes are `targets.update(is_active=...)` inside `transaction.atomic()`, **no** `select_for_update()` (documented decision, tripwire-tested).

**Notable:** `deactivation` is **not** re-exported from `src/backend/apps/users/services/__init__.py` — callers import the full module path. Deliberate (import-cycle hazard documented in `account_state.py`).

### 1.5 Admin surface

`src/backend/apps/users/admin.py` → `class UserAdmin(admin.ModelAdmin)`

- `form = UserChangeForm`, `add_form = UserCreationForm`
- `actions = ["deactivate_user", "reactivate_user"]`
- `deactivate_user` — `@admin.action(description="Deactivate selected users", permissions=["deactivate"])`
- `reactivate_user` — `@admin.action(description="Reactivate selected users", permissions=["deactivate"])`
- `_deactivation_message(verb, result)` — builds the operator toast
- **`has_deactivate_permission(request)` → `request.user.is_staff or request.user.is_superuser`** (the actor gate)
- `has_add_permission` → `is_superuser`; `has_change_permission` → `is_staff`; `has_delete_permission` → `is_superuser`; `has_view_permission` → `is_staff`
- `withdraw_consent_action` — `@admin.action`-decorated but **deliberately NOT in `actions`** (gate `G-B`); do-not-register comment block above it
- Module-level constants: `WEB_ONLY_ENFORCEMENT`, `SKIPPED_ROWS_PREFIX = "Skipped:"`, `ALREADY_IN_STATE_CLAUSE`

**Escalation hardening already present:** `fieldsets` contains **no `is_staff` and no `is_superuser` field at all**, and both are absent from `readonly_fields`. `get_readonly_fields()` returns `readonly_fields` whenever `obj` is set, leaving `preferred_city` the only writable field on change. This closes the old `AUT-005` self-escalation (a moderator writing their own `is_superuser`).

**Known gap, documented, deliberately not built:** `ReadOnlyPasswordHashWidget` renders a "Reset password" link to `<id>/password/`, which has **no route**. `get_urls()` has no `permissions` hook, and `has_change_permission` ignores `obj` — so building it would let a moderator overwrite a superuser's password. Deferred to phase 15 `15-AUTHZ-003`.

### 1.6 Ban (the *other* moderation lever)

`src/backend/apps/moderation/admin_actions.py`

| Symbol | Guard on target privilege? |
|---|---|
| `approve_ad(ad, moderator_id) -> ApproveOutcome` | n/a (ad-level) |
| `reject_ad(ad, moderator_id, reason)` | n/a (ad-level) |
| `soft_delete_ad(ad, moderator_id, reason)` | n/a (ad-level) |
| `bulk_approve` / `bulk_reject` / `bulk_delete` | n/a (ad-level) |
| **`ban_user_for_ad(ad, moderator_id, reason)`** | **NONE** — `User.objects.select_for_update().get(id=ad.user_id)`; sets `user.is_banned = True` unconditionally |
| **`bulk_ban_users(queryset, moderator_id, reason)`** | **NONE** — `User.objects.filter(id__in=user_ids).update(is_banned=True)` |

Audit trail: `src/backend/apps/moderation/services/moderation_log.py` → `log_ban_account(user_id, moderator_id, reason)` writes `ModeratorActionType.BAN_ACCOUNT` to `ModeratorActionLog`.

Other symbols in that module: `log_auto_fail`, `log_manual_reject`, `log_auto_publish`, `log_manual_publish`, `log_soft_delete`, `set_moderation_failed`, `set_rejected`, `set_published`.

### 1.7 Moderation views / decorators

`src/backend/apps/moderation/views/decorators.py`

- `staff_required(view_func)` → `Http404` if `not is_authenticated or request.user.role != UserRole.ADMIN`
- `staff_required_api(view_func)` → `401` (with `WWW-Authenticate: Bearer`) / `403` / `405`; checks role **before** method

`src/backend/apps/moderation/views/review.py` — `moderation_review`, `approve_ad`, `reject_ad`, `ban_user` (all `@staff_required`; the first three also `@require_POST` except `moderation_review`).
`src/backend/apps/moderation/views/api_bulk.py` — `bulk_moderation_action` (`@staff_required_api`, `MAX_BULK_ACTIONS = 100`, `_append_error`). **No `ban` branch.**
`src/backend/apps/moderation/views/queue.py` — `moderation_queue`.
`src/backend/apps/moderation/urls.py` — `app_name = "moderation"`; names `queue`, `review`, `approve`, `reject`, `ban`, `bulk_action`.

`src/backend/apps/ads/admin.py` → `class AdAdmin`: `action_reject`, `action_approve`, **`action_ban_user`** (`@admin.action(description="Ban users from selected ads")` → `bulk_ban_users(queryset, request.user.id, "Bulk ban via admin action")`), `action_soft_delete`, `_apply_status_change`, `changelist_view`; `has_view_permission` / `has_change_permission` → `is_staff or is_superuser`. **No `has_delete_permission` override, no `permissions=` list on its actions.**

### 1.8 Other permission surfaces (for the role-consistency picture)

- `src/backend/apps/ads/views/listings.py` → `media_gate(request, image_key)`: gates on **raw `request.user.is_staff`** (not `UserRole.ADMIN`).
- `src/backend/apps/moderation/admin.py` → `ModerationCriteriaAdmin` (`save_model` sets `updated_by`), `ModeratorActionLogAdmin` (fully read-only).
- Other `ModelAdmin` permission overrides: `apps/analytics/admin.py`, `apps/categories/admin.py`, `apps/core/admin.py`, `apps/lookups/admin.py`, `apps/locations/admin.py`, `apps/users/admin.py` (`ConsentRecordAdmin`, `LoginTokenAdmin`).
- **No `permissions.py`, no DRF, no permission mixin / base `ModelAdmin` exists anywhere.** Each class re-implements predicates.

## 2. Does the requirement match the implementation?

**Yes — for `is_active`, exactly.** A moderator *can* deactivate ordinary sellers; a moderator *cannot* touch a staff/superuser/peer-moderator row.

Where a moderator can currently deactivate a user:

| # | Entry point | Path | Actor gate | Target-scope gate |
|---|---|---|---|---|
| 1 | Users changelist → *Deactivate selected users* | `admin:users_user_changelist` → `UserAdmin.deactivate_user` → `deactivation.deactivate_users` | `has_deactivate_permission` → `is_staff or is_superuser` | `_resolve_targets` → `.exclude(is_staff).exclude(is_superuser).exclude(pk=actor.pk)` |
| 2 | Users changelist → *Reactivate selected users* | `UserAdmin.reactivate_user` → `reactivate_users` | same | same (so a moderator cannot undo a superuser's disable) |
| 3 | `manage.py shell` | `deactivation.deactivate_users(...)` directly | **none** (documented split) | yes |
| 4 | Django admin change form | `is_active` is read-only on change; field not in add view | `has_change_permission` → `is_staff` | n/a |

**Where a moderator can act on another user *without* any privilege guard (the actual gap vs. the requirement's spirit):**

| # | Entry point | Path | Target guard |
|---|---|---|---|
| 5 | Moderation review page → *Ban User* | `moderation:ban` → `review.ban_user` → `admin_actions.ban_user_for_ad` | **NONE** |
| 6 | Ads changelist → *Ban users from selected ads* | `AdAdmin.action_ban_user` → `admin_actions.bulk_ban_users` | **NONE** |
| 7 | Ads changelist / review → approve, reject, soft-delete | `approve_ad`, `reject_ad`, `soft_delete_ad`, bulk variants | ad-level only; a moderator **can** soft-delete or reject another moderator's *ad* |

So: **a moderator can ban a superuser** (`moderation:ban` on an ad authored by a superuser, or `AdAdmin.action_ban_user`). `is_banned` blocks login (`can_login`) and publishing (`can_publish_ad`), so this is a genuine denial-of-service / lockout escalation on a privileged account — the same class of harm the requirement forbids for deactivation.

**No bot-tier deactivation command exists.** The bot has no `/deactivate` or `/ban` handler; `src/telegram_bot/` contains no writer of `is_active` or `is_banned`.

## 3. Architecture, dependencies, constraints

### Layering (as practiced, not as documented)

```
Views / decorators / ModelAdmin actions (apps/*/views/*, apps/*/admin.py)
        ↓
Services (apps/*/services/*)             ← business logic + the ONLY place row-scope lives
        ↓
Models / QuerySets (apps/*/models.py)
```

Conventions observed:

- **Service functions take `actor`/`moderator_id` as an explicit argument**, never `request`.
- **Authorization is split deliberately** into *actor scope* (permission layer: `has_*_permission`, `permissions=`, `@staff_required`) and *target/row scope* (service layer: queryset exclusions). `deactivation.py` documents this split at length — Django's `permissions=` can only express actor scope.
- `StrEnum` for all fixed values (project rule 10). `deactivation` deliberately uses a `NamedTuple`, adding **no** migration and **no** new enum.
- Pydantic at boundaries (`apps/moderation/schemas.py` → `BulkModerationRequest`; `apps/users/schemas.py`).
- `select_for_update()` + ascending-pk lock ordering for read-then-write paths; bare bulk `UPDATE` with no prior read takes no lock.
- Structured logging via `logger = logging.getLogger(__name__)`; `mask_telegram_id` for PII in logs (`apps/core/utils/sanitize.py`).

### Runtime model

Two processes, one DB: **web** (gunicorn sync WSGI, HTMX MPA) + **bot** (aiogram, `django.setup()` + shared ORM). Shared service modules are imported by both. This is why `UserRole` is documented as "the single source of truth consumed by both the web process and the bot process."

### Dual-process enforcement divergence

| Tier | `is_active = False` | Mechanism |
|---|---|---|
| Web, existing session | **Killed next request** | `AuthenticationMiddleware` → `ModelBackend.get_user()` → `user_can_authenticate()` → `user.is_active`. Holds only because `AUTHENTICATION_BACKENDS` is unset (single `ModelBackend`). |
| Web, new issuance | **Refused** `410` at `login_status` (before first session write) | `B-05` |
| Web, `django_session` row | **Survives** until `expire_date` — inert, retained. No `clearsessions` janitor exists anywhere. | known gap |
| **Bot (Telegram)** | **NOT revoked.** A deactivated user reaches every bot handler. | `AccountStateMiddleware` reads `is_banned`/`is_deleted`/`is_declined`/`consent_revoked`, **never `is_active`** |

### Relevant repository rules

- `AGENTS.md` + `.kilo/rules/project.md`: English only; production code is king; single responsibility; avoid overengineering; follow existing patterns; StrEnum for constants; no `print()`; migrations for schema; **docs stay current**; small modules; **i18n is part of DoD**.
- `.kilo/rules/commands.md`: `.\Makefile.ps1 test` = fast gate (skips `seed`); `.\Makefile.ps1 test-all` = full; `.\Makefile.ps1 test-recreate` after migration changes. Tests run **only** via the `test` Compose service (`mko-bazuna-test` project, host PG on :5433) — never `uv run pytest` locally. Fixtures: `seller` (900000001), `user` (900000002), `category`, `city`, `create_test_ad(...)`. **Bot tests cannot import the backend conftest** (`src/telegram_bot/tests/conftest.py` redefines fixtures, async `user`).
- `docs/00-overview/doc-maintenance-rules.md` — governs the doc updates this work implies.

### Test layout for these areas

| Area | Path |
|---|---|
| Operator deactivation (the requirement) | `src/backend/apps/users/tests/test_admin_deactivate_user.py` |
| Role enum / `User.role` | `src/backend/apps/users/tests/test_user_roles.py` |
| Account state predicates | `src/backend/apps/users/tests/test_account_state.py` |
| Admin field contract / PII containment | `src/backend/apps/users/tests/test_admin_change_form.py`, `test_admin_pii_containment.py` |
| Login / `is_active` refusal | `src/backend/apps/users/tests/test_login.py` |
| Moderation actions + ban | `src/backend/apps/moderation/tests/test_admin_actions.py` (`TestBulkLockingStructure.test_bulk_ban_users_not_locked`) |
| `staff_required` / `staff_required_api` | `src/backend/apps/moderation/tests/test_decorators.py` |
| Moderation views | `src/backend/apps/moderation/tests/test_moderation_views.py` |
| Bot-tier deactivation probe | `src/telegram_bot/tests/test_account_state_deactivation_probe.py` |
| Banned-seller-relist gap | `src/backend/apps/ads/tests/test_edit.py::TestBannedSellerRelistKnownGap` |
| Trust / verify | `src/backend/apps/trust/tests/test_trust_calculator.py`, `test_trust_tags.py` |

Fixture pattern in `test_admin_deactivate_user.py`: module-local `staff_user` / `superuser` built with `get_or_create` on telegram_id block `93xxxxxxx`, because root `conftest.py` is contended territory.

`test_admin_deactivate_user.py` currently pins, with hard-coded literals (not the imported constants, deliberately, so a reword goes red):

- non-staff redirected (302) and its POST changes nothing
- both `is_staff` and `is_superuser` reach the action; `has_deactivate_permission is not has_delete_permission`
- `is_active=False` flips no other flag
- self-exclusion
- **`test_moderator_cannot_target_a_superuser_or_staff_row`** — covers peer `is_staff` moderator, full superuser fixture, **and** a `is_superuser=True, is_staff=False` row (the reason `.exclude(is_superuser=True)` cannot be dropped)
- `test_superuser_can_target_a_staff_row` (positive half)
- `test_moderator_cannot_reactivate_a_superuser`
- web session revoked next request; `django_session` row survives (encoded as a *known gap*)
- idempotence; reactivation
- toast names bot-tier limit; reports skipped counts; reports already-in-state
- structural: `transaction.atomic()` present, `select_for_update` absent (3 guards)

### i18n

`src/backend/locale/{ru,bs,en}/LC_MESSAGES/django.po`. Existing msgids relevant to moderation: `"Ban User"`, `"Ban User (Telegram ID: %(tid)s)"`, `"Ban Reason"`, `"Reason for banning this user..."`, `"Moderation Actions"`, `"Moderator Performance"`, `"Moderator ID"`, `"Moderator #%(mid)s"`, `"Moderation Queue"`, `"Moderate Ad"`, `"On Moderation"`, `"Failed Moderation"`, `"Moderation Analytics"`, `"Avg Time to Moderate"`, `"Rejection reasons will appear after moderators reject ads."`

**There are zero msgids for deactivate/reactivate.** The admin action descriptions and the entire `WEB_ONLY_ENFORCEMENT` / `Skipped:` toast are deliberate English-only literals on a staff-only surface. `apps/users/admin.py` records the decision explicitly and notes the i18n completeness gate (`test_no_hardcoded_visible_text`) scans **templates only**, so `admin.py` is not flagged. **If any new user-visible string is added on this surface, `ru`/`bs` msgstr must be non-empty** (`en` may be empty).

## 4. Discrepancies and risks

### HIGH — escalation still open on the `is_banned` levers

1. **`bulk_ban_users` has no privilege guard.** `User.objects.filter(id__in=user_ids).update(is_banned=True)` with no `is_staff`/`is_superuser` exclusion and no self-exclusion. Reachable by any `is_staff` user via `AdAdmin.action_ban_user`.
2. **`ban_user_for_ad` has no privilege guard.** `@staff_required`-only. A moderator can ban the owner of any ad, including a superuser's or another moderator's. `is_banned` blocks login and publishing, so the outcome is a privileged lockout — exactly the harm the requirement forbids for deactivation, on a sibling lever.
3. Neither path reports refused rows; both silently drop nothing and enforce nothing. `bulk_ban_users` returns a `count` that counts *user_ids seen*, not users actually banned, and includes `user_id` values for rows that may be privileged.

### HIGH — "moderator" is not a first-class role

4. **`UserRole` has no `MODERATOR` member.** Every moderator check in the repo is `is_staff or is_superuser` spelled out. The requirement's distinction between "ordinary sellers" and "staff/superusers/**other moderators**" is only *approximately* expressible: `is_staff` is overloaded to mean both "moderator" and "staff", and there is no way to express a moderator who is *not* staff.
5. **Three divergent implementations of "is this an admin".** `User.role` (declared source of truth) vs. `media_gate`'s raw `request.user.is_staff` vs. Django's `AdminSite.has_permission` (requires `is_staff`, so a superuser with `is_staff=False` is locked out of all 17 changelists while `staff_required` calls them ADMIN). Recorded as **`AUTHZ-003`, HIGH, Open, tracker `15-authz-AUTHZ-003`** in the phase-15 audit (file currently deleted from the worktree; recoverable via `git show HEAD:.ai/audit/15-authorization/findings.md`).
6. **15 of 17 `ModelAdmin` classes declare no permission override**, so a moderator with only `is_staff` gets `403` on 12 of 17 admin models. **No group, seeding command, or fixture exists to provision them.** Part of `AUTHZ-003`.

### MEDIUM — documented residuals on the deactivation path itself

7. **Bot tier not revoked.** `is_active=False` is web-only; a deactivated user reaches every bot handler. Pinned by `test_account_state_deactivation_probe.py` *by design*. Owner: phase 15 `15-AUTHZ-001`.
8. **`django_session` row survives deactivation.** No `clearsessions` janitor exists anywhere in `src/`, `docs/`, `docker/`, `.github/`, `Makefile`, `Makefile.ps1`. Owner: `15-AUTHZ-001`.
9. **No per-request web gate for `is_banned` / `is_deleted` / `is_declined`.** `MIDDLEWARE` is a pinned 15-entry list with no such gate. A banned seller keeps a working dashboard for up to 14 days and **can re-list** (`TestBannedSellerRelistKnownGap`). Recorded as **`AUTHZ-001`, HIGH, Open**.
10. **The web-revocation guarantee is backend-conditional.** It holds only because `AUTHENTICATION_BACKENDS` is unset. Adding a second backend that does not consult `user_can_authenticate()` silently weakens it. Flagged in every relevant docstring — a future auth-backend author must re-read it.
11. **The actor gate is admin-only.** The service's own docstring is explicit: `deactivate_users` enforces *target* scope only; a direct caller (view, future API) bypasses `has_deactivate_permission` and gets the target scope but not the actor gate. Accepted as "shell access is already total compromise" — but it means a new view must remember to re-check actor scope.
12. **The dead `<id>/password/` link.** `UserAdmin` switches the change view to `UserChangeForm`, whose `ReadOnlyPasswordHashWidget` renders a "Reset password" link to a route that does not exist; following it produces a 302 to the admin index reading *"user with ID '1/password' doesn't exist. Perhaps it was deleted?"* — which reads as data loss. Deliberately not built, because building it with today's `has_change_permission` (ignores `obj`) would let a moderator overwrite a superuser's password. Owner: `15-AUTHZ-003`.

### LOW

13. **Operator deactivation writes no audit row.** `ModeratorActionType` has no `deactivate`/`reactivate` member and `deactivation.py` writes no `ModeratorActionLog` — only `logger.info`. Bans get a `ModeratorActionLog` row; deactivations do not. Asymmetric auditability for two levers an operator uses interchangeably.
14. **No unban path exists at all.** `grep` for `update(is_banned=False)`, `is_banned = False`, `unban_user`, `def unban` returns nothing in production code. `is_banned` is read-only on the change form and one-way from the UI. Recorded in `admin-stories.md` §US-A4 as an operator-shell operation. Same for `US-A14`'s "Admin can manually verify sellers": `SellerVerification.verified_by_admin` exists and is scored, but **no admin action writes it**.
15. **`skipped_privileged` is an advisory count, not a refusal.** Refused rows are silently removed and reported in a toast. A bulk script or API consumer reading only `DeactivationResult.changed` sees a success. The admin toast mitigates this for humans only.
16. **`_resolve_targets` count-vs-write race.** Counts and the `UPDATE` must observe one snapshot; the docstring scopes the risk to *report accuracy* (off by one), since the exclusions are `WHERE` clauses evaluated at `UPDATE` time. Correct as documented, but the "reported" count can under-report.
17. **`account_state.py` module docstring is stale** — says "Three independent flags" then lists and returns five (`is_banned`, `is_deleted`, `is_declined`, `ads_auto_publish`, `consent_revoked`).

## 5. Documentation state

| Document | State re: this requirement |
|---|---|
| `docs/01-spec/technical-specification.md` | **Accurate.** §"Operator contract for `is_active`" documents the two actions, `has_deactivate_permission`, the non-privileged target scope, and decisions `18-D1`/`18-D2`/`18-Q7`. Also documents moderator = admin role. |
| `docs/99-agent/architecture.md` §"Operator-Facing Account Kill-Switch" | **Accurate and detailed.** States plainly: "a moderator **can** disable an ordinary seller … a moderator **cannot** touch a staff/superuser row; the bot tier is unenforced." Names the false-claim correction, the backend-conditional guarantee, and `04-AUTHZ` residuals. |
| `docs/ops/docker-deployment.md` | **Accurate.** Operator inventory row: "**Moderators may deactivate ordinary sellers only** … A superuser's selection is unrestricted." |
| `docs/04-user-stories/admin-stories.md` §US-A4 | **Partially stale.** Documents ban/unban/delete. Says nothing about deactivate/reactivate. The ban-reachability note is accurate but does not mention that ban lacks a privilege guard. |
| `docs/02-database/db-enums.md` §UserRole | Accurate; `18-D4` (should the account flags be one concept) is undecided and deliberately unresolved. |
| `docs/05-owner-decisions/index.md` | No entry for the deactivate/ban privilege matrix — a product decision was taken (`18-D1`/`18-Q7`) but is recorded only in code docstrings and `technical-specification.md`. |
| `.ai/plans/18-account-deactivation-execution.md` | Executed (`B-1..B-5`). Explicitly declares itself **pre-work for `15-AUTHZ-003`, not a substitute**. |

## 6. Planning implications (advisory)

- **Do not re-implement the deactivation target scope.** It exists, it is correct, it is tested, and its invariants are pinned by substring guards that will fail loudly if someone "helpfully" removes the `.exclude(is_superuser=True)` or adds `select_for_update()`.
- The open work is the **`is_banned` sibling** (`bulk_ban_users`, `ban_user_for_ad`) — same defect class, no guard, no test, and it is a **stronger** lockout than deactivation because it survives into the bot tier's login gate.
- If a `UserRole.MODERATOR` member is ever added, the scope is wider than this requirement: it touches `media_gate`, `AdminSite.has_permission`, all 17 `ModelAdmin` classes, `AUTHZ-003`, and the `technical-specification.md` "moderator = admin role" line. That is phase-15 `15-AUTHZ-003` territory, not this task.
- The lightest high-value increment is mirroring `DeactivationResult` semantics in the two ban paths (exclude `is_staff`/`is_superuser`/self, count and report the refusals) — same layering, same service position, same test surface as `test_admin_deactivate_user.py`.
