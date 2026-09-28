---
phase: "04"
phase_name: "Authentication & Login Token Security"
source_report: ".ai/audit/04-auth-login/findings.md"
date: "2026-09-28"
auditor: "Executor (subagent)"
validator: "Kilo (validator subagent)"
mode: "problems-only"
id_prefix: "AUT"
report_status: "validated"
findings_in_scope: 7
verdict_tally: "Confirmed 4 · Adjusted 2 · Reclassified 1 · Rejected 0"
---

# Validated Findings — Authentication & Login Token Security (Phase 04)

This report is self-contained. Every claim below was re-derived from the source tree
and, where stated, from a read-only introspection inside the `mko-bazuna-test` image.
No code was modified. The reader needs neither the original findings file nor any
source file to act on this document.

## Verdicts at a glance

| ID | Title (abbrev.) | Auditor sev. | **Verdict** | **Final sev.** | One-line justification |
|----|-----------------|--------------|-------------|----------------|------------------------|
| AUT-001 | Login token not bound to the issuing browser | HIGH | **CONFIRMED** | HIGH | Zero session reference at issuance or consumption; the forwarded-deep-link takeover path executes exactly as described. |
| AUT-002 | Ban/decline/delete never revokes live web session | HIGH | **CONFIRMED + RECLASSIFIED** | HIGH | Real, but only 3 of 4 revocation paths are open (self-service withdraw already logs out) and it contradicts `technical-specification.md:101-102` — so it is a SPEC-DEVIATION, not a hardening nicety. |
| AUT-003 | Rate limit keyed on client-controlled `X-Forwarded-For` | MEDIUM | **CONFIRMED** | MEDIUM | Three verbatim copies of the helper; nginx `$proxy_add_x_forwarded_for` keeps the attacker value at index 0. Spec citation overstated; nginx's own `$binary_remote_addr` limit still caps exposure. |
| AUT-004 | `User.is_active` kill-switch ignored by Telegram login | MEDIUM | **CONFIRMED** | MEDIUM | `auth_login()` bypasses `ModelBackend.user_can_authenticate()`; `is_active` is proven to be an editable admin control. |
| AUT-005 | No password reset / validators for the admin login | MEDIUM | **ADJUSTED** | **HIGH** | The `/admin/` change form exposes `password` as a **plain-text `CharField`** that is written unhashed — a worse, previously unreported defect; and the proposed `AUTH_PASSWORD_VALIDATORS` fix would not actually validate the bootstrap password. |
| AUT-006 | No `SESSION_COOKIE_AGE`; 14-day Django default | LOW | **ADJUSTED / RECLASSIFIED** | LOW | Factually correct, but `technical-specification.md:143` specifies "until … long idle", which the code does not implement — SPEC-DEVIATION, not BEST-PRACTICE. |
| AUT-007 | State-changing GET `login_issue`, no token invalidation | LOW | **CONFIRMED** | LOW | GET routing and the bare `INSERT` verified; the `<img>`/prefetch claim survives the `JSExecutionMiddleware` check because that middleware blocks nothing. |

Severity movement: 0 CRITICAL, 2 HIGH, 3 MEDIUM, 2 LOW → 0 CRITICAL, **3 HIGH**, 3 MEDIUM, 2 LOW.
Type movement: AUT-002 and AUT-006 → **SPEC-DEVIATION**.

---

## Checkpoint 1 — Auditor analysis

- **Stage:** Auditor analysis
- **Findings in scope:** 7 (CRITICAL 0, HIGH 2, MEDIUM 3, LOW 2); prefix `AUT-`
- **Evidence anchor:** `.ai/audit/04-auth-login/findings.md` (640 lines, self-contained, 18 runtime checks R-01…R-18)
- **Dependencies / blockers:** dev `web`/`bot` containers crash-looping (placeholder `BOT_TOKEN` in `.env.dev`) — no live HTTP evidence obtainable; validation was source-level plus read-only introspection in the test image.
- **Checkpoint status:** closed

## Checkpoint 2 — Researcher verification

- **Stage:** Researcher verification
- **Cross-phase conflicts:** 1 ownership conflict (VAL-001), 1 doc-vs-doc conflict (VAL-005)
- **Merge candidates:** 1 implementation pair — AUT-001 + AUT-007 share one prerequisite (`session_key`), but different root causes, so **retained as two findings, one commit**; not a merge.
- **Audit-input defects found:** 5 (VAL-001…VAL-005), including one finding-ID collision (VAL-002) and one coverage gap carrying a live defect (VAL-004).
- **Checkpoint status:** closed

## Checkpoint 3 — Per-finding validation

- **Stage:** Per-finding validation
- **Decisions:** Validated unchanged 4 (AUT-001, AUT-003, AUT-004, AUT-007) · Reclassified 2 (AUT-002, AUT-006 — Type changed, severity held) · Severity-adjusted 1 (AUT-005 MEDIUM → HIGH, scope expanded) · Merged 0 · Rejected 0
- **Evidence anchor:** this document; all line references below are verified against the working tree at commit `33345c9`
- **Checkpoint status:** closed

---

## Findings

### AUT-001 — [HIGH] — Login token is not bound to the browser session that issued it

**Verdict: CONFIRMED — HIGH (unchanged).**

**Verified.** `login_issue` never touches `request.session`; it performs a bare insert
(`apps/users/views/consent.py:323-329`), and `login_status` authenticates on the token
alone (`consent.py:398-430`, then `auth_login(request, user)` at `consent.py:459`).
`LoginToken` (`apps/users/models.py:185-214`) carries only `token_hash`, `telegram_id`,
`created_at`, `expires_at`, `consumed_at` — no session or device column. `users/urls.py:20`
routes issuance as a plain `GET`. `users/login_issue.html:37-48` renders the page's own
`csrf_token`, which the attacker holds for their own browser, so CSRF provides no origin
assurance.

**Attack path re-executed mentally against source, step by step:**

1. Attacker `GET /login/issue/` → receives raw token `T`; row inserted unbound.
2. Attacker sends the victim `https://t.me/<bot>?start=login_T`.
3. Victim taps it; the bot's single-statement claim (`telegram_bot/handlers/login.py:169-187`,
   `UPDATE … WHERE token_hash=%s AND telegram_id IS NULL AND consumed_at IS NULL AND expires_at>%s RETURNING …`)
   binds `telegram_id = <victim>`.
4. Attacker `POST`s `T` to `/login/status/` from their own browser with their own CSRF token.
   `request.POST["token"]` matches, the token is unconsumed/unexpired/claimed → `consumed_at` set.
5. `User.objects.get(telegram_id=<victim>)` resolves, `can_login()` passes, `auth_login()` writes
   the victim's session into the **attacker's** browser.

**No severity inflation.** CRITICAL would be wrong: the attack needs the victim to tap a
supplied link, and the attacker must already be able to deliver a Telegram link. Credential-less
full account takeover via a routine user action is HIGH, not CRITICAL.

**Corrections to the plan (do not change the verdict):**

- The finding's own caveat is correct and load-bearing: `SessionMiddleware` persists only a
  *modified* session, so `login_issue` must write to the session to obtain a key. The report
  understates two consequences of that. (a) It converts a currently cookie-less, session-less
  endpoint into one that writes a `django_session` row and a `Set-Cookie` for **every** anonymous
  visitor and every third-party prefetched `<img>` hit — i.e. it multiplies the very write
  amplification AUT-007 flags. (b) It silently breaks six currently-green tests
  (see VAL-003).
- **Cheaper alternative worth choosing deliberately instead of a schema change:** store
  `token_hash` in `request.session` at issuance and require the session value to equal the
  posted token at consumption. Same assurance, no migration, no new table growth, and it reuses
  Django's session store. Pick one approach — the migration-based `session_key` column and the
  session-store approach are alternatives, not a package.
- Keep the POST-only + CSRF contract on `login_status` as-is; it is already correct and is
  not the defect.

---

### AUT-002 — [HIGH] — Banning/deleting/declining never revokes the live web session

**Verdict: CONFIRMED and RECLASSIFIED as SPEC-DEVIATION — HIGH (unchanged).**

> **Validation Note:**
> - **Action:** reclassified
> - **Detail:** The defect is real, but two things in the original report are wrong. (1) It is
>   **partially pre-fixed**: `consent.py:256-259` already calls `logout(request)` on the
>   self-service withdraw path, shipped in commit `25bbe64 fix(users): invalidate session on
>   consent withdrawal (AUT-002)` (2026-09-24). One of four revocation paths is closed. The
>   finding should be restated as "session invalidation exists on exactly one of four paths",
>   not as wholly open. (2) The Type is SPEC-DEVIATION, because
>   `docs/01-spec/technical-specification.md:101` states DECLINE "blocks seller login/actions"
>   and `:102` states WITHDRAW "flushes the web session via `logout(request)` — the withdrawn
>   identity is logged out immediately and **can no longer act on seller features**". The code
>   satisfies neither statement for a live session. This is a deviation from a documented
>   requirement.
> - **See also:** VAL-001 (Phase 15 ownership), VAL-005 (spec-index vs technical-specification
>   conflict), AUT-004, AUT-006

**Verified.**

| Path that changes account state | Revokes the live web session? | Evidence |
|---|---|---|
| Self-service consent withdraw (web) | **Yes** | `consent.py:254-259` — `withdraw_consent(user)` then `logout(request)` |
| Admin bulk "Withdraw consent" | No | `apps/users/admin.py:55-65` — `withdraw_consent(user)` only; the target's session is never touched |
| Moderator ban (single ad) | No | `apps/moderation/admin_actions.py:98-100` — `user.is_banned = True; save(update_fields=["is_banned"])` |
| Moderator bulk ban | No | `apps/moderation/admin_actions.py:255` — `User.objects.filter(...).update(is_banned=True)` |
| Self-service decline | No | `consent.py:208-212` — `decline_consent(user)`, no logout |

**The gate runs once, at session creation.** `can_login()` is invoked in exactly one production
place, `consent.py:449`. `can_login` (`apps/users/services/account_state.py:96-106`) inspects
only `is_banned` and `is_declined`; `is_deleted` is deliberately excluded (pinned by
`test_account_state.py:170-178`, on the grounds that withdrawal nulls `telegram_id`, which
blocks *re-login* but not an *existing* session). No account-state middleware exists in
`MIDDLEWARE` (`config/settings/base.py:196-211` — 14 entries, none of them one). The bot does
gate per message (`telegram_bot/middlewares/permissions.py:102-108`); the web does not. A
soft-deleted user's session is not even flagged for the UI — `apps/users/context_processors.py:101-102`
only forces `consent_shown = True`.

**Impact, stated precisely** (the original over-broadens it in one direction and under-states
another). `ads/views/edit.py:94-101` enforces ownership with a 403, so a banned user cannot touch
other people's ads; and a text edit re-enters `ON_MODERATION`, so it is not a moderation bypass.
What *is* un-gated: **in-place price and photo edits of already-published ads** (a genuine fraud
vector — no re-moderation), ad deletion, the seller dashboard, seller analytics, and the whole
cabinet (saved searches, favourites, search history). The finding also implies the banned seller
can keep creating ads; they cannot — the web has no ad-create view and the bot middleware blocks
them. `can_publish_ad()` exists and is exhaustively tested but is called from **no production
code path**, so it does not narrow the gap either. Severity HIGH is retained because a routine
abuse-response control is inert, the spec explicitly promises the opposite, and the price-edit
vector touches live listings.

**Recommendation — the finding's part (1) is right; part (2) is confused and should be dropped.**
Adding a shared web-side account-state gate (middleware or a `require_active_seller` decorator
reusing `get_account_state()`) is the correct, single-source-of-truth fix. The write-side
suggestion is not implementable as written: `Session.objects.filter(session_data__contains=...)`
is rejected in the text and the replacement — scanning all `Session` rows and decoding
`_auth_user_id` — is O(all sessions) per moderation action and is worse than the disease. Revoke
per user, or rely on the gate. Also note that fixing AUT-004 as "enforce `is_active`" should land
in the **same** gate, otherwise the project grows two parallel state vocabularies.

---

### AUT-003 — [MEDIUM] — Rate limit keyed on a client-controlled `X-Forwarded-For`

**Verdict: CONFIRMED — MEDIUM (unchanged).**

**Verified, and broader than reported.** `_get_client_ip` takes element 0 of
`HTTP_X_FORWARDED_FOR` with no trusted-proxy validation, in **three** verbatim copies:

- `apps/users/services/login_rate_limit.py:63-79`
- `apps/core/services/contact_rate_limit.py:24-29`
- `apps/search/services/rate_limit.py:69-85` — **omitted from the finding's File(s) list**
  (the recommendation does name it, so the substance is right; the file list is incomplete)

`docker/nginx/nginx.conf` uses `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;`
in **every** location (lines 65, 85, 116, 126, 134, 144, 153, 164, 176). That variable *appends*
`$remote_addr` to whatever the client sent, so index 0 is exactly the attacker-controlled value.
Rotating the header yields a fresh cache key per request and the counter never exceeds 1.

**Corrections to the report:**

- **The spec citation is overstated.** The report says `spec-index.md:75` and
  `technical-specification.md:140` "advertise a 10 requests / 60 s per IP" property. Neither line
  mentions 10/60 — both say only "rate-limited". The spec promises that rate limiting *exists*;
  the exact quota is a code decision. The defect stands; restate the citation.
- **The mitigating control is real and the report is right to keep it.** nginx's
  `limit_req_zone $binary_remote_addr zone=login_limit:10m rate=10r/s` (`nginx.conf:24`) keys on
  the real peer address and is therefore *not* bypassable by header rotation. Combined with
  `location /login/ { limit_req … burst=20 nodelay; }` (`nginx.conf:112`), the exposure is bounded
  at roughly 10 `LoginToken` INSERTs per second per source, not unbounded. That bound is exactly
  why this is MEDIUM and not HIGH — do not let it be upgraded on re-reading.
- **Rollout caveat the report misses.** `$remote_addr` is the real client *only because nginx
  terminates TLS itself* (`nginx.conf:38,55-56` — certificates mounted in the nginx container).
  The preferred fix (overwrite the header with `$remote_addr`) silently collapses every client
  into a single bucket if a CDN or load balancer is ever placed in front. Implement
  **nginx-overwrite plus** a `TRUSTED_PROXY_CIDRS`-aware helper, never overwrite alone.
- The de-duplication advice stands and is the highest-ROI part of this finding: three copies of
  the same six-line function is a real maintainability defect on its own.

---

### AUT-004 — [MEDIUM] — `User.is_active` kill-switch silently ignored

**Verdict: CONFIRMED — MEDIUM (unchanged).**

**Verified, and the premise is now proven rather than asserted.** `User` inherits
`AbstractUser` (`apps/users/models.py:19`), so `is_active` exists. No `AUTHENTICATION_BACKENDS`
is set in any settings module, so Django's default `ModelBackend` is in effect — and
`ModelBackend.user_can_authenticate()` *does* enforce `is_active` for the `/admin/` password
login. The Telegram path never runs a backend at all: `consent.py:459` calls the low-level
`auth_login(request, user)`, which writes the session directly. `can_login()`
(`account_state.py:96-106`) reads only `is_banned` and `is_declined`. A repo-wide grep finds no
read of `User.is_active` on any authentication or authorization path.

The auditor asserted that `is_active` is "editable in the `/admin/` change form" because
`UserAdmin` does not restrict `fields`/`fieldsets`. I confirmed this by introspecting the real
form in the test image (see VAL-004): `is_active` is present as an editable field. The premise
holds.

The finding's likelihood note is also correct as written: the bot's `AccountStateMiddleware`
gates on banned/deleted/declined only (`permissions.py:102-108`), so a deactivated account keeps
full bot access as well as full web access.

**Type note.** The finding is filed as an authentication defect. It is equally a
*specification* defect: the project ships a control the spec never asked for and never wires up.
Enforcing it is the lower-risk direction and is what the report recommends; the alternative
(drop the column by migration and hide the fieldset) is a legitimate product decision that this
audit should not make. Keep the finding, keep it MEDIUM, and treat "enforce vs. remove" as a
decision to be taken explicitly rather than left implicit.

---

### AUT-005 — [MEDIUM] → [HIGH] — Password recovery, validators, **and the admin change form**

**Verdict: ADJUSTED — severity raised MEDIUM → HIGH, scope expanded.**

> **Validation Note:**
> - **Action:** reclassified (severity MEDIUM → HIGH; scope expanded)
> - **Detail:** Two independent reasons. (1) A materially worse defect on the same code path was
>   missed by the auditor: `UserAdmin` exposes `password` as a **plain-text `CharField`** that is
>   written to the database **unhashed** (VAL-004). (2) The original recommendation is
>   **technically wrong and would create false assurance** — see below.
> - **See also:** VAL-004 (the evidence), VAL-005 (`prod.py` comment), AUT-002 (both touch
>   `UserAdmin`)

**What was verified as reported.** `config/urls.py:11-23` mounts only
`django_prometheus`, `admin`, and the project apps — `django.contrib.auth.urls` and any
`PasswordResetView` are absent. `AUTH_PASSWORD_VALIDATORS` appears in no settings module. The
only password-hashing configuration anywhere is the test-only MD5 hasher
(`config/settings/test.py:57`). `User.USERNAME_FIELD = "username"` (`models.py:127`) really is
the sole password credential, bootstrapped from `$ADMIN_PASSWORD` by
`docker/entrypoint-create-admin.sh:18-27` → `apps/core/management/commands/create_admin_user.py`.
No recovery runbook exists in `docs/ops/`.

**Why severity rises — the missed defect.** `apps/users/admin.py:14-41` declares no `fields`,
`fieldsets`, `form`, or `add_form`; `readonly_fields` covers only `consent_given_at`,
`consent_revoked_at`, `deleted_at`. Django therefore auto-builds a `ModelForm` from the model.
Read-only introspection in the `mko-bazuna-test` image (no rows written, admin form only):

```text
FORM FIELDS: ['ads_auto_publish', 'chat_id', 'date_joined', 'email', 'first_name', 'groups',
 'is_active', 'is_banned', 'is_declined', 'is_deleted', 'is_staff', 'is_superuser', 'last_login',
 'last_name', 'password', 'preferred_city', 'source', 'telegram_id', 'telegram_language',
 'telegram_premium', 'user_permissions', 'username']
PASSWORD FIELD: CharField | widget: AdminTextInputWidget
is_active present: True
last_login present: True | date_joined present: True
```

`ModelAdmin.save_model` calls `obj.save()`, and the `users` app registers no `pre_save` signal
(the only receivers in the project are in `apps/core/signals.py`, for `SiteConfig` and
`SupportContactModel`). Consequences:

- Any `is_staff` user — and per `User.role` (`models.py:157-172`) `is_staff` **is** the moderator
  role; there is no separate moderator role — can open `/admin/users/<id>/change/` and read that
  account's PBKDF2 hash as cleartext in the HTML source.
- The same user can type an arbitrary string into that field. It is stored **verbatim, unhashed**,
  so `check_password()` can never match it again. Overwriting a superuser's password this way is
  a permanent, silent lockout of the highest-privilege credential.

Django ships `UserChangeForm` + `ReadOnlyPasswordHashField` for exactly this reason; the custom
`UserAdmin` dropped them. `last_login` and `date_joined` are likewise editable, which is
incidental noise by comparison.

**Why the original recommendation must be rewritten.** It proposes adding
`AUTH_PASSWORD_VALIDATORS` so that "any future password — including one supplied to
`create_admin_user` — is policy-checked". That is incorrect. Django runs `AUTH_PASSWORD_VALIDATORS`
only from `UserCreationForm` / `SetPasswordForm` / `UserChangeForm`; `create_admin_user.py:116`
calls `user.set_password(password)` directly, which does **not** invoke them, and the command's
only check is non-empty (`create_admin_user.py:67-70`). Adding the setting would validate nothing
on the one credential that matters. Additionally the command is **skip-if-exists**
(`create_admin_user.py:78-89`), so re-running it never rotates a password — there is no rotation
path at all, which is stronger than the report's "no policy forcing rotation".

**Restated scope, in fix order:**

1. Restore password handling on the admin change form: `form = UserChangeForm` (or
   `readonly_fields += ["password"]` plus an explicit set-password action), and call
   `update_session_auth_hash()` when the password changes so other live sessions are not
   silently invalidated.
2. Add `AUTH_PASSWORD_VALIDATORS` to `config/settings/base.py` **and** call
   `password_validation.validate_password(password, user)` explicitly inside `create_admin_user`.
   The setting alone is not sufficient.
3. Recovery: either wire a staff-gated `password_reset` view, or — if that is deliberately out of
   scope for a single-moderator deployment — correct the misleading justification at
   `config/settings/prod.py:198-199`, which cites "password resets" as a reason `EMAIL_HOST` is
   mandatory in production, and add a `docs/ops/` runbook for shell-based credential reset and
   rotation. Option 3b is cheap and can ship independently of 1 and 2.

---

### AUT-006 — [LOW] — Session lifetime falls back to the 14-day Django default

**Verdict: ADJUSTED / RECLASSIFIED as SPEC-DEVIATION — LOW (unchanged).**

> **Validation Note:**
> - **Action:** reclassified
> - **Detail:** The factual claim is correct, but `docs/01-spec/technical-specification.md:143`
>   specifies "**Session:** persistent cookie, survives browser restart until explicit logout or
>   **long idle**". `SESSION_COOKIE_AGE`, `SESSION_EXPIRE_AT_BROWSER_CLOSE`,
>   `SESSION_SAVE_EVERY_REQUEST`, `SESSION_ENGINE` and `SESSION_COOKIE_NAME` appear in no
>   settings module; only the `Secure` flags are set (`base.py:139-144`, `dev.py:31`,
>   `test.py:23`, `prod.py:216-217`). Django's defaults therefore give a 14-day **absolute**
>   expiry with no sliding, so an actively-used seller is logged out at exactly 14 days and an
>   abandoned one survives exactly 14 days. Neither reading of "until … long idle" is implemented.
>   That is a documented-requirement deviation, so SPEC-DEVIATION is the correct Type.
> - **See also:** AUT-002 (the exposure window this widens), Phase 02 (transport-security flags)

**Severity held at LOW, deliberately.** The deviation makes the session *shorter* than an
attacker would like rather than longer, it changes no access decision, and a one-line
`SESSION_COOKIE_AGE` change does not move AUT-001 or AUT-002 at all. The report is right that this
blunts those findings without fixing them.

**Recommendation accepted as written**, with one correction: setting `SESSION_COOKIE_AGE` shorter
gives a shorter *absolute* cap only. If the intent is the spec's "long idle" semantics, that needs
`request.session.set_expiry()` at login plus an idle-refresh strategy — the report mentions
`set_expiry()` but pairs it with the age change in a way that reads as sufficient. Either state
the policy as absolute-only (and amend `:143` to say so) or implement the idle semantics; do not
ship the age change believing the spec line is now satisfied.

---

### AUT-007 — [LOW] — `login_issue` is a state-changing GET that never invalidates prior tokens

**Verdict: CONFIRMED — LOW (unchanged). Implement together with AUT-001.**

**Verified.** `users/urls.py:20` routes issuance as a plain `GET`;
`consent.py:326-329` performs a bare `LoginToken.objects.create(...)` with no lookup of the
requesting browser's prior outstanding tokens. Every reload, extra tab, or prefetch therefore
mints an additional independently-claimable 5-minute credential.

I specifically tested the report's `<img>`/prefetch claim, because `JSExecutionMiddleware` could
have invalidated it. It does not: `apps/core/middleware/js_check.py:28-29` only *sets*
`request.js_verified` and blocks nothing, and `apps/core/templatetags/telegram_tags.py:121-129`
states the deep-link tag renders "regardless of the `js_verified` context flag". An
unauthenticated third-party GET does reach `LoginToken.objects.create()`. The claim holds.

The dead context value is confirmed dead: `bot_username` is passed at `consent.py:331,339`, but
`users/login_issue.html:23` sources the username from the `{% telegram_deep_link %}` tag, whose own
docstring (`telegram_tags.py:163`) resolves it internally via `get_bot_username()`. Trivial
cleanup, zero risk.

**Not a merge, but one implementation unit.** The root causes differ (AUT-001 is a missing binding;
AUT-007 is a missing credential lifecycle), so both findings stand — but AUT-007's own
recommendation states that the invalidation step "becomes trivial once AUT-001 adds `session_key`".
Sequence AUT-001 first, then AUT-007, in the same commit. If the validator's cheaper
session-store approach (see AUT-001) is chosen instead, AUT-007's invalidation is a single
`session.pop()` and the model change disappears entirely.

The report correctly declines to recommend converting issuance to POST — that would break the
QR/deep-link UX for no security gain now that a binding exists. Keep that decision.

---

## VAL findings (audit-input defects)

### VAL-001 — Cross-phase ownership conflict: AUT-002 vs. Phase 15

**Type:** cross-phase conflict · **Severity:** High (blocks merge until resolved)

`15-audit-authorization.md:128` fixes the boundary explicitly: "Phase 04 (Authentication — V2
'who are you?') — token issuance, claim/consumption, cookie attributes, and session
establishment. Phase 04 owns *authentication*; Phase 15 owns *authorization*. … Phase 15 verifies
[the role] is honored on every protected resource." Its dimension §5(f), *Cross-process
authorization consistency*, is graded HIGH, and "the bot enforces state per message, the web does
not" is the textbook instance of that dimension.

A web-side account-state gate is therefore **Phase 15(f)** work. Resolution: Phase 04 retains
AUT-002 for the session-layer consequences only — that `ban_user_for_ad`, `bulk_ban_users` and
`UserAdmin.withdraw_consent_action` fail to invalidate the session they caused to exist, and that
`can_login` is a one-shot gate. Phase 15 owns the per-request gate. Both phases must not file the
same middleware. If Phase 15 has not yet run when AUT-002 is actioned, re-check at merge time.

### VAL-002 — Cross-audit finding-ID collision (remediation hazard)

**Type:** audit-input defect · **Severity:** High (blocks the remediation tracker)

`AUT-001`, `AUT-002` and `AUT-003` in this report are **already in use as identifiers by unrelated
work**, and a fourth audit cycle's IDs are hard-coded in the shipped source:

| Reference in source | What that `AUT-00N` actually meant |
|---|---|
| `apps/core/tests/test_login_issue_template.py:56` — "(AUT-001)" | deep-link button is the only actionable control (not session binding) |
| `apps/users/tests/test_login.py:2, 429` — "AUT-009" | web login views / the login rate-limit contract |
| `telegram_bot/middlewares/permissions.py:117`, `tests/test_account_state_middleware.py:311, 731` — "AUT-001" / "AUT-003" | FSM `user_id` backfill; middleware chain ordering |
| `apps/users/views/consent.py:256`, `apps/users/tests/test_consent.py:341` — "AUT-002" | a **previous** audit's session-invalidation finding, already remediated in commit `25bbe64` (2026-09-24) |

Consequence: a remediation tracker keyed on bare `AUT-00N` will collide across audit cycles and
may close the wrong item. This audit is read-only and cannot fix the collision, so the requirement
propagates: the final report must key these findings phase-qualified (`04-AUT-00N`), and any
tracker consuming them must not reuse bare IDs. Fixing the stale in-source comments is a separate,
optional cleanup.

### VAL-003 — Rollout safety: AUT-001 silently breaks six green tests

**Type:** rollout-safety · **Severity:** Medium

`apps/users/tests/test_login.py` constructs `LoginToken` rows directly and asserts HTTP 200 from
`/login/status/`: lines 160-182 (`test_login_status_200_claimed_and_user_exists`), 262-286
(`test_consumed_token_cannot_be_reused`), 288-318
(`test_bot_phase_claim_completes_when_user_exists`), and — through the `_claim_login` helper at
lines 348-358 — all three `TestLoginPreferredCitySync` tests at 373-425. Every one of those rows
has no `session_key`. Under AUT-001's recommended "reject NULL `session_key`" policy all six
return 410.

The original Rollout Safety table acknowledged the *production* effect but not the *test* effect.
Per the project rule that production code is king, the tests are what change — but sequence the
work so the suite is not left red mid-rollout, and decide the NULL-legacy-row policy explicitly
before shipping: **reject** NULL (every token in flight at deploy time dies — a 5-minute window
of user-visible login failure) or **accept-if-NULL** (the binding is bypassable for any token
minted before the migration completes). The second is defensible given the 5-minute TTL, but it
must be a conscious choice, not an accident of query construction.

### VAL-004 — Coverage gap: the `/admin/` change-form surface was never enumerated

**Type:** audit-input defect (missed live defect) · **Severity:** High

The auditor's 18 runtime checks never touched the Django admin form surface, and as a result
missed a live credential-integrity defect that belongs in AUT-005. Reproduced read-only in the
`mko-bazuna-test` image (admin form introspection only — no rows written, no code changed):

```powershell
# reproduction (Docker, mko-bazuna-test, config.settings.test, admin form only)
python -c "import os,django; os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings.test'); django.setup(); ..."
# UserAdmin.get_form(request, obj=None, change=True) with a permissive stub user
```

Output is quoted in AUT-005 above. The defect: `password` is bound as a `forms.CharField` rendered
with `AdminTextInputWidget` (a plain text input) and is written verbatim by
`ModelAdmin.save_model` → `obj.save()`, with no `pre_save` hashing receiver registered anywhere in
the `users` app. It is folded into AUT-005 by this validation. **If the final report prefers a
separate ID, AUT-005 must not be closed without it.** The same introspection also corroborates
AUT-004's premise that `is_active` is genuinely offered to operators.

### VAL-005 — Doc-vs-doc conflict feeding AUT-002 and AUT-005

**Type:** cross-phase conflict (documentation) · **Severity:** Medium

Two current spec documents disagree about the exact behaviour AUT-002 is filed under:

- `docs/01-spec/spec-index.md:74` — "DECLINE blocks seller **login only** (no erasure, contact
  still works)".
- `docs/01-spec/technical-specification.md:101` — "DECLINE = browse-only: blocks seller
  login/**actions** AND hides the user's PUBLISHED ads …".

The two readings imply different behaviour for precisely the case at issue (a declined user's
*live* session). This validation adopts the technical specification's reading — it is the more
detailed, more explicitly maintained of the two, and `spec-index.md` is explicitly a summary
("Spec summary" in the project guidelines). `spec-index.md:74` should be corrected to say
"login and seller actions".

Same class of defect, same phase: `config/settings/prod.py:198-199` justifies a hard `EMAIL_HOST`
fail-fast partly with "transactional emails (**password resets**, alert notifications, seller
confirmations)" — but no password-reset flow exists anywhere in the repository. That comment
misleads operators into believing a recovery mail path is live (AUT-005).

---

## Cross-Finding Analysis (revised)

**Merge candidates:** none accepted. AUT-001 and AUT-007 are implemented as one commit but retain
separate root causes and separate IDs. AUT-006 and AUT-002 share an exposure *window* but not a
root cause — AUT-002 is a missing revocation hook, AUT-006 a missing lifetime policy, and the fixes
are independent; the original report's reasoning here is correct and is retained.

**Conflicting evidence:** two, both recorded above — VAL-001 (Phase 04 vs Phase 15 ownership) and
VAL-005 (spec-index vs technical-specification). Neither is a contradiction about the *code*, so
neither is Critical, but both must be resolved before Phase 15 merges its own authorization
findings.

**Dependency chains:**

- `AUT-001 → AUT-007` — hard prerequisite. Session binding must land before per-browser token
  invalidation is expressible. Ship as one commit.
- `AUT-004 → AUT-002` — soft. If AUT-002's gate is built, `is_active` should be folded into it,
  otherwise the project carries two parallel state vocabularies enforced by two different layers.
- `VAL-004 → AUT-005` — hard. The admin-form fix must land with or before the validator work;
  adding `AUTH_PASSWORD_VALIDATORS` alone leaves the plaintext write path open.
- `AUT-006` — independent of everything; ships alone, remediates nothing.
- `AUT-003` — independent; the nginx-overwrite and helper-de-duplication halves are separable and
  the de-duplication is the higher-ROI half.

## Rollout Safety (revised)

| ID | Risk | Backward-compatible? | Test gap that must be covered |
|----|------|----------------------|--------------------------------|
| AUT-001 | **High** | No | Six tests in `apps/users/tests/test_login.py` create `LoginToken` rows directly and assert 200 (VAL-003) — all must be updated. New: token minted in session A cannot be consumed from session B; matching `session_key` still consumes; the NULL-legacy-row policy is asserted explicitly. Also assert the new `django_session` write does not break anonymous browsing or the `preferred_city` reconciliation. |
| AUT-002 | Medium | Partly | A currently banned/declined user's next request will now redirect instead of rendering the dashboard — expected, but assert it. Unaffected users' sessions survive. Bot path unchanged. |
| AUT-003 | Low | Yes | Two requests with distinct `HTTP_X_FORWARDED_FOR` but identical `REMOTE_ADDR` share one counter and the 11th is throttled. The three call sites (`login`, `contact`, `search`) all exercise the new shared helper. |
| AUT-004 | Low | Depends on the choice | `is_active=False` gets 410 from `/login/status/` and is blocked by the bot middleware; `is_active=True` path unchanged. |
| AUT-005 | Medium | Yes | Admin change form renders the password hash as read-only (or not at all); a typed password is stored hashed, never verbatim; `create_admin_user` rejects a password failing the validators. |
| AUT-006 | Low | Behavioural | `settings.SESSION_COOKIE_AGE` value asserted; a session created after the change expires at the configured age. |
| AUT-007 | Low | Yes | A second `/login/issue/` in the same session leaves exactly one unconsumed token for that session. |

## Remediation Roadmap (revised order)

| Order | ID | Severity | Effort | Priority | Action |
|-------|----|----------|--------|----------|--------|
| 0 | VAL-004 → AUT-005 | HIGH | S | **P0** | Restore password handling on the `UserAdmin` change form (plaintext hash disclosure + unhashed write). Independent of everything else; smallest fix with the largest consequence. |
| 1 | AUT-001 + AUT-007 | HIGH | M | P0 | Bind the token to the issuing browser (schema or session-store approach — pick one), enforce it at consumption, then invalidate prior tokens per browser. |
| 2 | AUT-002 (+ AUT-004 folded in) | HIGH | M | P0 | Web-side account-state gate mirroring `AccountStateMiddleware`, reusing `get_account_state()`; include `is_active` in the same gate. Reconcile ownership with Phase 15 first (VAL-001). |
| 3 | AUT-003 | MEDIUM | S | P1 | nginx overwrites `X-Forwarded-For` with `$remote_addr` **plus** a `TRUSTED_PROXY_CIDRS`-aware shared helper replacing all three copies. |
| 4 | AUT-004 (residual) | MEDIUM | S | P1 | Decide enforce-vs-remove explicitly; surface the flag in `UserAdmin.list_display`/`list_filter` whichever way it goes. |
| 5 | AUT-005 (residual) | HIGH→MEDIUM | S | P1 | `AUTH_PASSWORD_VALIDATORS` **plus** an explicit `validate_password()` call in `create_admin_user`; then wire a staff-gated reset view or correct `prod.py:198` and add a `docs/ops/` runbook. |
| 6 | AUT-006 | LOW | S | P2 | Set `SESSION_COOKIE_AGE` explicitly; align `technical-specification.md:143` with whichever of absolute-only vs. idle semantics is actually implemented. |
| 7 | VAL-005 | MEDIUM | S | P2 | Correct `spec-index.md:74` ("login **and actions**") and the `prod.py:198` password-reset claim. Docs-only, no code risk. |

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 4 | AUT-001, AUT-003, AUT-004, AUT-007 |
| Reclassified (Type) | 2 | AUT-002, AUT-006 → SPEC-DEVIATION |
| Severity-adjusted | 1 | AUT-005 MEDIUM → HIGH (scope expanded) |
| Merged | 0 | AUT-001 + AUT-007 share a commit, not a root cause |
| Rejected | 0 | — |
| VAL- (cross-phase / rollout / coverage) | 5 | VAL-001 … VAL-005 |

### Rejected Findings

| ID | Title | Reason |
|----|-------|--------|
| — | — | No finding was rejected. Every claim survived source re-verification; the defects that were wrong (AUT-005's validator claim, AUT-003's file list and spec citation, AUT-002's "wholly open" framing) were corrections inside surviving findings, not grounds for rejection. |

### Merged Findings

| Original ID | Merged Into | Rationale |
|-------------|-------------|-----------|
| — | — | No merges. AUT-001 and AUT-007 are sequenced into one commit but keep separate IDs and separate root causes. |

### Reclassified Findings

| ID | Original Type | New Type | Rationale |
|----|---------------|----------|-----------|
| AUT-002 | Session management / CWE-613 | **SPEC-DEVIATION** | `technical-specification.md:101-102` explicitly promises DECLINE blocks seller actions and WITHDRAW flushes the session; the code does neither for a live session. Partially pre-fixed by commit `25bbe64` — restate as 3 of 4 revocation paths open. |
| AUT-006 | Session management / CWE-613 (best-practice) | **SPEC-DEVIATION** | `technical-specification.md:143` specifies "until … long idle"; an absolute 14-day cap with no sliding implements neither that nor a shorter policy. |
| AUT-005 | Credential management / CWE-640 | **SPEC-DEVIATION (credential integrity)** + **HIGH** | The `/admin/` change form writes `users.password` unhashed and renders the hash in cleartext — an undocumented, unenforced control surface, not merely a missing recovery flow. |

## Required Fixes

1. **Close the plaintext password write path on the admin change form** (VAL-004 / AUT-005). Any
   `is_staff` user can currently read a superuser's password hash and permanently destroy their
   credential. This is the highest-consequence defect found in this phase and it is not currently
   in anyone's backlog.
2. **Bind `LoginToken` to the issuing browser and enforce it at consumption** (AUT-001), in the
   same commit as the per-browser invalidation (AUT-007), and update the six affected tests as one
   change so the suite is never red mid-rollout.
3. **Add a web-side account-state gate** (AUT-002 + AUT-004), reusing `get_account_state()` as the
   single source of truth shared with the bot — after resolving ownership with Phase 15 (VAL-001).
4. **Do not ship `AUTH_PASSWORD_VALIDATORS` as the AUT-005 fix** without the explicit
   `validate_password()` call in `create_admin_user`; the setting alone validates nothing on the
   bootstrap credential.
5. **Resolve the two documentation conflicts** (VAL-005) so the AUDIT-002 verdict rests on a single
   unambiguous spec statement.
6. **Key the remediation tracker on `04-AUT-00N`, not `AUT-00N`** (VAL-002) — bare IDs already
   refer to unrelated work in three prior audit cycles.

## Advisory Recommendations

- **Fold `is_active` into the AUT-002 gate** rather than shipping a separate `can_login` change.
  Two independent account-state vocabularies enforced by two layers is how this class of bug
  recurs.
- **Prefer the session-store approach over a new column** for AUT-001, unless per-browser token
  enumeration is needed for an audit requirement: it needs no migration, no new table growth, and
  makes AUT-007 a one-line `session.pop()`.
- **Guard the nginx change with `TRUSTED_PROXY_CIDRS`.** Overwriting `X-Forwarded-For` with
  `$remote_addr` is correct *today* only because nginx terminates TLS itself; add the trust list in
  the same change so a future CDN does not collapse all clients into one bucket.
- **De-duplicate `_get_client_ip` first.** Three verbatim copies of the same six-line helper is
  independently worth fixing, and it makes every later change to the trust policy a one-line edit
  instead of three.
- **Add a `SESSION_*` / `AUTH_*` policy block to `config/settings/base.py` with a comment per
  setting.** Six of the seven findings in this phase are "the control exists in Django but the
  project never configured it". A single annotated block makes that class of gap visible at review
  time instead of audit time.
- **Note for the next phase that consumes this report:** the `/admin/` change-form surface was not
  enumerated in Phase 04's methodology. Other phases that own admin-facing code (15 authorization,
  06 PII) should introspect their registered `ModelAdmin` form fields the same way rather than
  reasoning from `admin.py` source alone.
