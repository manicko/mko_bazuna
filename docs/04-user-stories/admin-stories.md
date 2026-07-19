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
---

## Purpose

Admin-role user stories. **Moderator = admin role** (no separate role, decision A). Domain rules
referenced as "decision X" live in
[technical-specification.md](../01-spec/technical-specification.md).

## Stories

### US-A1 — Admin auth
Separate login or Telegram with confirmed role. Unauthorized attempts are logged.

### US-A2 — List all ads
List all ads (ID, title, category, city, status, published date); filter by
status/category/city/date.

### US-A3 — Moderate ads
Unpublish, delete, change status, or ban all of a user's ads. Actions are instant and logged to
`ModeratorActionLog`.

### US-A4 — Manage users
Block/unblock/delete users. A blocked user cannot post but may still browse.

### US-A5 — Auto-remove stale ads
Background sweep: archive @2 months, delete @4 months (from `published_at`); logged. See decision J.

### US-A6 — Delete inactive users
Delete users inactive beyond a configurable threshold; their ads are deactivated.

### US-A7 — Manage categories & cities
Add/edit/deactivate categories and cities. Entities in use are not deletable. See decision D.

### US-A8 — Manage consent
View consent fact and revoke it (triggers the decision F withdrawal flow: `consent_revoked_at` +
soft-delete + 30-day PII erasure).

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
