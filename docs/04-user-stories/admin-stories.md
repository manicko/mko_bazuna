---
id: admin-stories
domain: user-stories
tags:
  - user-stories
  - admin
  - moderation
related:
  - user-stories-index
  - technical-specification
  - db-schema
  - docker-deployment
---

## Purpose

Admin-role user stories. **Moderator = admin role** (no separate role, decision A). Domain rules
referenced as "decision X" live in
[technical-specification.md](../01-spec/technical-specification.md).

## Initial Admin Setup

### Pre-configured Admin User

The platform includes a pre-configured admin user for Django admin site access. This user is created
automatically during deployment when `ADMIN_PASSWORD` is set in the environment.

**Default Admin Credentials:**

| Field | Default | Environment Variable |
|-------|---------|---------------------|
| Username | `admin` | `ADMIN_USERNAME` |
| Password | (required for auto-creation; skipped if empty) | `ADMIN_PASSWORD` |
| Telegram ID | `-1` | `ADMIN_TELEGRAM_ID` |

**Important:** The User model uses `username` as the `USERNAME_FIELD` (not `telegram_id`). The Django
admin login form displays "Username". Enter the admin username (default: `admin`, or the
`ADMIN_USERNAME` env var) along with the password from the `ADMIN_PASSWORD` env var.

**Password policy (04-VAL-004):** the bootstrap password is validated against
`AUTH_PASSWORD_VALIDATORS` — at least 10 characters, not on Django's common-password list, not
entirely numeric, and not too similar to the username or email. A rejected password aborts
creation. See [Manual Creation](../ops/docker-deployment.md#manual-creation) for the runbook.

### Setup Methods

1. **Automatic (recommended):** Set `ADMIN_PASSWORD` in `.env` before running `docker compose up -d`
2. **Manual:** Run `docker compose run --rm web uv run python src/backend/manage.py create_admin_user`

Both paths create the account **once**. Neither can change the password of an account that
already exists: `create_admin_user` returns early — before any password write — as soon as the
username or Telegram ID is taken. Changing an existing password is
`manage.py changepassword <username>`.

Editing an existing account in the Django admin is a separate and deliberately narrow surface:
the user change form has exactly **one** writable field (`preferred_city`), so un-ban and
account-disable have no user-form path. The table of what is still reachable, and how, is in
[The Admin User Change Form Contract](../ops/docker-deployment.md#the-admin-user-change-form-contract-04-aut-005).

See [docs/ops/docker-deployment.md](../ops/docker-deployment.md#admin-user-setup) for detailed
instructions on creating and managing the admin user.

## Stories

### US-A1 — Admin auth
Separate login or Telegram with confirmed role. Unauthorized attempts are logged.

### US-A2 — List all ads
List all ads (ID, title, category, city, status, published date); filter by
status/category/city/date.

### US-A3 — Moderate ads
Unpublish, delete, change status, or ban all of a user's ads. Actions are instant and logged to
`ModeratorActionLog`.

*Admin-surface note (AD-001):* a status change made through the **Ad** change form is routed
through the lifecycle matrix instead of being written as a raw `UPDATE`, and it writes **exactly
one** `ModeratorActionLog` row through the existing moderation-log service for the target it routes
to: today the form can reach `PUBLISHED` and `DELETED` there, because `REJECTED` and
`ON_MODERATION_FAILED` are refused by the form (their timestamp columns are read-only). A form
change to `ARCHIVED`, `ON_MODERATION` or `DRAFT` still goes through the matrix guard but writes
**no** audit row; that is the recorded residual of the deferred admin-status decision. A POST that
would violate a status timestamp constraint is now a form error instead of an HTTP 500. `status` is
deliberately still editable, so a moderator may still move it; whether that is the sanctioned seam
is an open owner question, recorded in
[ad-lifecycle-remediation-record.md](../99-agent/ad-lifecycle-remediation-record.md).

### US-A4 — Manage users
Block/unblock/delete users. A blocked user cannot post but may still browse.

*Admin-surface note (04-AUT-005):* **block** remains reachable — the **Ad** changelist action
*Ban users from selected ads*. **Un-block has no admin path at all** (no unban action, no unban
service), and the user change form renders `is_banned` read-only, so un-blocking is a
`manage.py shell` operation. The requirement is unchanged; only the UI moved.

### US-A5 — Auto-remove stale ads
Background sweep: archive @2 months, delete @4 months (from `published_at`); logged. See decision J.

### US-A6 — Delete inactive users
Delete users inactive beyond a configurable threshold; their ads are deactivated.

### US-A7 — Manage categories & cities
Add/edit/deactivate categories and cities. Entities in use are not deletable. See decision D.

### US-A8 — Manage consent
View consent fact and revoke it (triggers the decision F withdrawal flow: `consent_revoked_at` +
soft-delete + 30-day PII erasure).

*Admin-surface note (04-AUT-005):* the `withdraw_consent_action` method exists on `UserAdmin` but
is **not listed in `ModelAdmin.actions`**, so the changelist never offers it, and the change form
renders the consent and erasure flags read-only. The trigger is therefore absent from the admin by
decision, not by oversight — recorded with its phase-06 owner in
[architecture.md](../99-agent/architecture.md#account-state-and-session-revocation-04-aut-002).
Revoking remains available to the user themself via *Withdraw Data* on the seller dashboard.

### US-A9 — View system logs
Admin-only view of system logs/events; filter by type/date.

### US-A10 — Automatic ad check
At submit, ads are checked against `moderation_criteria` (decision O4). On fail →
`ON_MODERATION_FAILED` + bot message (no reason disclosed). On pass → `PUBLISHED` within ≤5s. This
is the only automatic gate before `PUBLISHED`. See decision A.

### US-A11 — Manage moderation criteria & manual review
View failed/rejected lists and edit `moderation_criteria` at runtime. Manual photo review (Layer 2)
with prohibited-content categories logged as `reason` in `ModeratorActionLog` — **never shown to the
seller**. See decision O4.

### US-A12 — Moderation queue priority
Moderator sees ads sorted by priority score in the queue. Priority is computed from content risk
(banned words, repeat offender flags) and seller trust level. Each ad has a priority level
(`HIGH`, `MEDIUM`, `LOW`) and an escalation flag for senior review. See decision Q.

### US-A13 — Moderation analytics
Admin views moderation statistics: pending queue size, moderator performance metrics, and rejection
reason breakdowns. Data is aggregated via `ModerationAnalytics` service and supports time-range
filtering. See decision Q.

### US-A14 — Trust signals management
Admin views seller trust scores and verification status in the dashboard. Trust scores are
recalculated on every ad publish and mapped to `TrustLevel` (`UNVERIFIED`, `VERIFIED`, `TRUSTED`,
`PRO`). Admin can manually verify sellers and view trust history. See decision M.
