---
plan_id: "04-auth-login-remediation"
phase: "04"
phase_name: "Authentication & Login Token Security"
source_report: ".ai/audit/99-validation/04-auth-login-validated-findings.md"
date: 2026-09-29
planner: "Planner agent (stealth/space-bunny-alpha)"
anchor_commit: "4fd8bd0"
status: "planned"
findings_in_scope: 12
findings_implemented: 7
findings_partially_implemented: 2
val_binding_constraints: 3
val_hygiene: 1
val_split: 1
blocks: 9
---

# Execution Plan — Phase 04 Remediation (Authentication & Login Token Security)

## 0. Header, provenance and scope statement

### 0.1 Provenance

| Field | Value |
|---|---|
| Phase | 04 — Authentication & Login Token Security |
| Source report | `.ai/audit/99-validation/04-auth-login-validated-findings.md` (Auditor + Validator output; per-phase `findings.md` no longer exists in the tree) |
| Code context | `.ai/tmp/code-context-phase04.md` (~56 KB, produced for this phase) |
| Report anchor commit | `33345c9` (stale; several report line citations no longer resolve — see 0.4) |
| Code-context anchor commit | `9443ade` |
| Working-tree HEAD at plan time | `4fd8bd0` — **one commit past the code context**: `test(ci): guard the deploy-check env block against prod-settings drift (CFG-002 durability half)`. Verified: it touches CI/deploy-check surface only, no phase-04 file. Every phase-04 fact below was re-verified at `4fd8bd0`. |
| Predecessor plans | `.ai/plans/01-entry-architecture-remediation.md`, `.ai/plans/02-config-secrets-remediation.md` |
| Finding ID namespace | `04-` (phase-qualified). `AUT-001`…`AUT-007`, `VAL-001`…`VAL-005` |
| Status of findings | **0 already fixed · 7 still open · 0 partial · 0 rejected** |
| Repo | `C:\py_dev\mko_bazuna` |

### 0.2 Evidence basis — read this before executing any block

**Verified in the tree at `4fd8bd0` (re-derived, not copied from the report).** These are the facts every block depends on.

1. **The token lifecycle was already extracted.** Phase 01 BLOCK 10 (`aa71faa`) created
   `src/backend/apps/users/services/login_token.py`, which owns issuance, claim and
   consume. The validated report's `apps/users/views/consent.py` line citations for
   `AUT-001` and `AUT-007` are **stale** — the code is no longer there. Both findings
   remain open; the remediation point narrowed to `issue_token()` in that module,
   which already documents `AUT-007` as its landing site (also recorded in
   `docs/99-agent/architecture.md` → "Login Token Lifecycle Seam (ENT-005)" →
   "The `AUT-007` boundary and the two existing deleters"). **The report and the tree
   disagree; the tree wins.**

2. **`claim_token`'s `RETURNING` clause is a schema contract, not a convenience.**
   It lists `LoginToken`'s *complete* field set (`id, token_hash, telegram_id,
   created_at, expires_at, consumed_at`) and is consumed with
   `zip(..., strict=True)` + `LoginToken(**…)`. Adding a column to `login_tokens`
   without editing that list raises `TypeError` **on the bot claim path**. This is
   the single largest implementation hazard in the phase.

3. **The three deleters are fixed and closed to further additions.** `LoginToken`
   rows are deleted only by `users/services/deletion.py::withdraw_consent` and
   `core/management/commands/cleanup_login_tokens.py` (hourly, `expires_at < now()`,
   `AdvisoryLockId.CLEANUP_LOGIN_TOKENS`). The `login_token` module docstring forbids
   a third deleter. **`AUT-007` invalidation is a fourth writer, not a deleter, and
   is permitted; a `DELETE` introduced by this phase is not.**

4. **`django_session` has no janitor.** `clearsessions` appears **nowhere** in the
   repository — not in `HOURLY_COMMANDS`, not in `DAILY_COMMANDS`, not in any
   entrypoint, not in any management command. `SESSION_ENGINE` is unset, so the DB
   backend (`django.contrib.sessions`, present in `INSTALLED_APPS`, with
   `SessionMiddleware` at the top of `MIDDLEWARE`) is in use. This is load-bearing
   for `AUT-001` — see 3.3 and BLOCK 3.

5. **Three identical private `_get_client_ip` copies** exist, all trusting
   `HTTP_X_FORWARDED_FOR` unconditionally and taking `split(",")[0]`:
   `apps/users/services/login_rate_limit.py`, `apps/core/services/contact_rate_limit.py`,
   `apps/search/services/rate_limit.py`.

6. **`docker/nginx/nginx.conf` sets `proxy_set_header X-Forwarded-For
   $proxy_add_x_forwarded_for;` in 9 locations** (the report says 8). Every one of
   them is `$proxy_add_x_forwarded_for` = *append* semantics, so a client-supplied
   `X-Forwarded-For` prefix survives into the header Django reads. The first
   comprehension step is therefore attacker-controlled. nginx also emits HSTS and
   Django sets `USE_X_FORWARDED_HOST = True`, so nginx **is** the trusted edge.

7. **No `AUTH_PASSWORD_VALIDATORS`, no `SESSION_COOKIE_AGE`, no
   `AUTHENTICATION_BACKENDS` anywhere** in `config/settings/` (`base.py`, `dev.py`,
   `test.py`, `prod.py`, `oneshot.py`). Django's defaults are in force: the session
   cookie is a 14-day sliding expiry that refreshes on every write; **no password
   validator is configured at all**. `SESSION_COOKIE_SECURE/HTTPONLY/SAMESITE` are
   all explicitly set in `base.py`; only `SESSION_COOKIE_SECURE` is overridden
   (down) in `dev.py` and `test.py`.

8. **`UserAdmin` declares no `fields`, no `fieldsets`, no `form`.** Django auto-builds
   a `ModelForm` over every editable `User` field. The same defect is recorded twice:
   as `04-AUT-005` / `04-VAL-004` (phase 04, credential half) and as `PII-103`
   (phase 06, identity + consent half), which phase 06's validator **merged into
   `04-AUT-005`**. **One fix, one commit.** There is no `forms.py` and no
   `admin_forms.py` anywhere in the repo — this would be the first.

9. **The direct-`LoginToken`-row test count is 7, not 6.** Six live in
   `apps/users/tests/test_login.py` (five in `TestLoginStatus`, plus the shared
   `_claim_login` helper) and one in `apps/users/tests/test_consent.py`
   (`TestLoginTokens::test_login_consume_no_raw_telegram_id`). All seven construct
   the row directly with a fresh `Client()` that never issued a token.

10. **Four green tests are owned by other phases and this phase will change them.**
    See 4.4. Project rule 2 — *production code is king* — governs all four: the test
    changes, not the production code, and each change lands in the **same commit** as
    the production change that invalidates the test.

11. **`AccountState` is instance-level and has no `is_active` term.**
    `apps/users/services/account_state.py` exposes `get_account_state(user) ->
    AccountState` (a `NamedTuple` over a `User` *instance*), `can_login(user) -> bool`,
    `can_publish_ad(user) -> bool` and `get_state_badge(user) -> str`. `can_login`
    tests exactly two flags: `is_banned` and `is_declined`. `is_active` is not a term
    anywhere in that module.

12. **`can_login` has a 7-call-site blast radius** (confirmed independently of the
    report): `consent.py::login_status` and `consent_accept`, `dashboard/views.py::home`
    × 2, `dashboard/services.py::seller_context`, `ads/views/my_ads.py::my_ads`,
    `ads/services/edit.py` (ad-edit ownership check), and the bot
    `AccountStateMiddleware._check_user_state`.

13. **`Middleware` has 14 entries and no account-state gate.** The authenticated tier
    is gated by per-view decorators (`@login_required`, `@seller_required`,
    `@staff_required`), which test *authentication*, not *account state*.

14. **Moderation ban entry points.** `moderation/views/review.py::ban_user` is a
    `POST`-guarded, `@staff_required` view that wraps `ban_user_for_ad` in
    `transaction.atomic()` with `Ad.objects.select_for_update()`. The services
    `ban_user_for_ad` and `bulk_ban_users` have **neither a `request` nor, in
    `bulk_ban_users`, a per-user object** — `bulk_ban_users` issues a single
    `User.objects.filter(id__in=user_ids).update(is_banned=True)`.

15. **`test_bulk_ban_users_not_locked` is a phase-03 tripwire.** It asserts a
    `select_for_update` is **not** issued for the bulk-ban path. Adding row locks to
    close a phase-04 finding would break it.

16. **`AUT-002`'s evidence table has 5 rows, 1 closed, 4 open** — not "3 of 4" as
    the report headline says. See 0.4.

17. **`config/settings/prod.py` asserts a password-reset capability the system does
    not have.** Its `EMAIL_HOST` fail-fast comment names "password resets" as a
    production requirement, and `docs/ops/docker-deployment.md` names
    "password-reset" tokens twice. No `password_reset` URL, no
    `PasswordResetView`, no mail template exists anywhere. There is a real
    `EMAIL_HOST` guard; the *claim* attached to it is false.

### 0.3 Explicit scope statement

**In scope and owned by this plan — 7 findings, all still open at the anchor:**

| Finding | Severity | Title | Landing block(s) |
|---|---|---|---|
| `04-AUT-001` | HIGH | Login token not bound to the browser that requested it | BLOCK 3 |
| `04-AUT-002` | HIGH | Revocation paths never invalidate the session they caused | BLOCK 6 (**session-layer half only**) |
| `04-AUT-003` | MEDIUM | Rate-limit key is a client-controlled `X-Forwarded-For` prefix | BLOCK 7 |
| `04-AUT-004` | MEDIUM | `is_active=False` is not enforced | BLOCK 4 |
| `04-AUT-005` | HIGH | Admin form accepts plaintext passwords; no validators; no recovery | BLOCK 1, BLOCK 2, BLOCK 5 |
| `04-AUT-006` | LOW | Session lifetime contradicts the spec | BLOCK 8 |
| `04-AUT-007` | LOW | Token accumulation (invalidation half) | BLOCK 3 (**invalidation half only**) |

**In scope as binding constraints or routing decisions — 5 VAL findings:**

| Finding | Disposition |
|---|---|
| `04-VAL-001` | **Binding constraint** on BLOCK 6. Splits `AUT-002` from `15-AUTHZ-001`: phase 04 keeps the *session-layer* half, phase 15 owns the per-request gate. Hard rule: **both phases must not file the same middleware.** |
| `04-VAL-002` | **Partly** a tracker/process requirement (a DoD deliverable, §8.1); **partly** an optional in-source comment-hygiene pass in BLOCK 9. |
| `04-VAL-003` | **Binding constraint** on BLOCK 3. The binding design must be settled *before* implementation, with 7 tests and 2 green tests accounted for. |
| `04-VAL-004` | **Binding constraint** on BLOCK 1. The admin-form fix must land with or before BLOCK 2, and the form-introspection test is mandatory. |
| `04-VAL-005` | **Split.** `docs/01-spec/spec-index.md` DECLINE-semantics conflict → **routed to phase 06 (`PII-113`, which phase 06 declared "the finding of record")**. The false *password-reset* claim in `config/settings/prod.py` and `docs/ops/docker-deployment.md` → **BLOCK 5**. |

**Not in scope and why** — see §6.

**Nothing outside this list may be changed by this plan.** Every block's file surface
is enumerated in §3; a change outside it is a scope violation, not a judgement call.

### 0.4 Severity corrections

The report is the authority on verdicts and severities. It contains **one internal
severity-tally error**, recorded here the way phase 01 recorded its own.

| # | Item | Report says | Tree / arithmetic says | Disposition |
|---|---|---|---|---|
| S-1 | `AUT-002` revocation-path count | Headline: "3 of 4". Its own evidence table has **5 rows, 1 closed, 4 open**. `15-AUTHZ-001`'s validator reached the same number and explicitly wrote *"phase 04's own headline says '3 of 4' while its evidence table lists five rows with one closed. The code is the tie-breaker: **4 of 5**."* | **4 of 5** | Use **4 of 5** in the tracker and in BLOCK 6's test coverage. The headline is wrong; the table is right. |
| S-2 | `VAL-003` direct-row test count | "six" | **seven** — six in `test_login.py` **+** `test_consent.py::TestLoginTokens::test_login_consume_no_raw_telegram_id` | Use **seven**. |
| S-3 | Post-validation severity tally | `## Validation Summary` says `0 CRITICAL · 3 HIGH · 3 MEDIUM · 2 LOW` — that is **8 items for 7 findings**. The per-finding `Final severity` column reads HIGH, HIGH, MEDIUM, MEDIUM, HIGH, LOW, LOW = **3 HIGH · 2 MEDIUM · 2 LOW**. | **3 HIGH · 2 MEDIUM · 2 LOW** | The summary line is arithmetically impossible. **Planner-raised input defect `04-VAL-006`** (new ID, this plan only): severity-tally error, same class as phase 01's `VAL-005`. The per-finding column governs. No finding's band changes. |
| S-4 | `prod.py` password-reset comment | cites the comment at `prod.py:198-199` | the guard and its comment are at `config/settings/prod.py`, in the `EMAIL_HOST` fail-fast block; the line moved | Locate by **symbol/behaviour** ("the `EMAIL_HOST` fail-fast block"), never by the stale number. |
| S-5 | nginx `X-Forwarded-For` locations | 8 | **9** (`proxy_add_x_forwarded_for` appears 9× in `docker/nginx/nginx.conf`) | Count the occurrences; do not trust either number without counting. |
| S-6 | Report anchor | `33345c9` | HEAD is `4fd8bd0`; `apps/users/views/consent.py` no longer contains the token code the report cites for `AUT-001`/`AUT-007` | **The tree is authority.** See 0.2 item 1. |
| S-7 | `04-VAL-005` `technical-specification.md` line refs | `:101`, `:143` | still resolve, but **phase 06 (`PII-113`) is editing that same document** | Do not edit the technical specification from this plan. §6.2. |

**No severity band is changed by this plan.** S-1 through S-7 are citation, count and
arithmetic corrections only.

### 0.5 Open technical questions — resolved here, or explicitly deferred

Seven questions are open. **This plan does not answer any of them.** Each is routed
either to a pre-step that must complete before the owning block starts, or to an
explicit "decision required before implementation" gate carried by the block with
its options and consequences. Recording an answer here and implementing it would
violate the brief.

| Q | Question | Owner block | Route | Status |
|---|---|---|---|---|
| **Q1** | Which browser-binding design for `AUT-001`: a `LoginToken` column, a `django_session` key, or a non-session per-browser cookie? | BLOCK 3 | **(a)** Researcher + Planner pre-step **must complete before** the block starts | **OPEN** — options and consequences in 3.3 |
| **Q2** | What is the trusted-proxy topology in front of nginx? | BLOCK 7 | **(a)** Auditor pre-step (re-derive the deployment topology) + Researcher (proxy-header best practice) **must complete before** the block starts | **OPEN** — consequences in 3.7 |
| **Q3** | Should `is_active` be **enforced** (as a real kill-switch) or **removed** from the `User` model as dead? | BLOCK 4 | **(b)** decision gate carried by the block | **OPEN** — options in 3.4 |
| **Q4** | Does the report's premise for `is_active` on the web still hold — i.e. can a live session with `is_active=False` still reach a protected view today? | BLOCK 4 | **(a)** Auditor pre-step — re-derive the claim, do not copy it. Phase 15's matrix says `is_active=False` **already** yields a 302, which would refute the premise. | **OPEN** — the re-derivation is itself the deliverable |
| **Q5** | Should a credential-recovery path be built, or should the `EMAIL_HOST` fail-fast and the ops docs be corrected to stop claiming password resets? | BLOCK 5 | **(b)** decision gate carried by the block | **OPEN** — options in 3.5. Coupled to phase 02's `EMAIL_BACKEND` work (`CFG-004`) |
| **Q6** | Absolute-only session expiry, or a real "long idle" sliding expiry that matches the spec's wording? | BLOCK 8 | **(b)** decision gate carried by the block | **OPEN** — options in 3.8 |
| **Q7** | Are `AUT-002`'s per-path `logout()` calls worth shipping at all, or are they redundant defence-in-depth under phase 15's gate? | BLOCK 6 | **(b)** decision gate carried by the block | **OPEN** — the evidence needed to decide it is in 3.6 |

**Two further questions this plan raises, which no report recorded:**

| Q | Question | Owner block | Route |
|---|---|---|---|
| **Q8** | Should `consent_decline` log the user out? Today `can_login(is_declined=True) is False` and `test_account_state.py` pins it, but `06-PII-105` (option (a) — DECLINE becomes reversible and web login is regained) would make that logout *newly restrictive*. The `04-VAL-005` doc conflict feeds both. | BLOCK 6 | **(b)** decision gate. **Hard gate: BLOCK 6 must not ship the decline-path logout before phase 06's `PII-105` decision is known.** |
| **Q9** | Is there an operational gate (`nginx -t`, config reload, container restart) the implementor can actually run to validate an nginx change? The phase-04 validator noted `nginx -t` was **not** run at audit time. | BLOCK 7 | **(a)** Auditor pre-step — confirm before editing; BLOCK 7 carries a recorded fallback if no gate exists |

**Correction to the code context that BLOCK 3 depends on.** The code context states
that under the session-store approach "the helper needs no change at all". **That is
incorrect.** All seven direct-row tests create a fresh `Client()` that never issues a
token, so *under either design* the browser binding is absent and the endpoint answers
`410`. The tests must be revised under **both** options. The asymmetry between the two
options is real, but it is not "one option needs no test changes" — it is "one option
needs a migration and a `RETURNING` edit; the other needs a session write on an
endpoint that is currently cookie-less".

---

## 1. Environment and command contract for the implementor

**This environment is Windows 11 / PowerShell 7.** `make` requires WSL or GNU Make;
use `.\Makefile.ps1 <target>`. `head` / `tail` are unavailable in PowerShell.

### 1.1 Tests are Docker-only — `uv run pytest` on the host always fails

There is no PostgreSQL on `localhost:5432`. Every test run goes through the `test`
service of the `mko-bazuna-test` Compose project.

```powershell
# Fast gate (skips the nightly `seed` suite) - the default iteration command
$dc run --rm --env PYTEST_SKIP_MARKERS=seed test

# Targeted run
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="-k test_name" test
$dc run --rm -e PYTEST_OPTS="src/backend/apps/users/tests/test_login_token.py --tb=short" test

# Full suite (only when the change touches seeding or images)
$dc run --rm test

# Fresh schema (after a migration lands)
$dc run --rm --env PYTEST_OPTS="--create-db --tb=short -n auto --maxprocesses=4 --dist loadgroup" test
```

with, copied once per session:

```powershell
$dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'
```

**Two caveats that will silently produce a wrong result if ignored:**

- `--env-file .env.test` is **required**. Without it compose aborts on
  `${POSTGRES_*?}` interpolation. Never substitute the `mko-bazuna-dev` project name.
- Setting `PYTEST_OPTS` **replaces** the defaults
  (`--reuse-db --tb=short --durations=10 -n auto --maxprocesses=4 --dist loadgroup`),
  so a targeted run loses xdist parallelism and DB reuse. Never use
  `--override-ini=addopts=` - it strips `--import-mode=importlib`, which
  `pyproject.toml` requires.

Canonical wrappers `.\Makefile.ps1 up | test | test-all | test-recreate | test-down`
manage the project name and env file for you. Prefer them.

### 1.2 Lint, typecheck, i18n

```powershell
uv run ruff check <path>            # lint
uv run ruff check --fix <path>      # auto-fix, including import sorting (I001)
uv run basedpyright <path>          # typecheck
uv run djlint src/backend/templates/  # only if a template changes
```

**i18n is part of DoD.** Every user-visible string is wrapped in `{% trans %}` /
`{% blocktrans %}` (templates) or `gettext` / `gettext_lazy` (Python). `msgstr` must
be **non-empty** for `ru` and `bs`; `en` may be empty (the msgid is English). `.mo`
files are gitignored and compiled at image build, at container start, and in the CI
`i18n` job - manual `compilemessages` is rarely needed. `make makemessages` /
`make compilemessages` **do not work** on Windows + Docker Desktop; use the
lightweight `--no-deps --entrypoint ""` form in `.kilo/rules/commands.md` if a `.po`
actually has to change. Run `test_i18n_completeness.py` after any string change.

### 1.3 Git contract - one implementor, sequential, one commit per block

- **One Implementor at a time.** Never two. Never a background implementor.
- If a block is stopped mid-way, **resume the existing session**; do not launch a new
  agent.
- Each block is committed separately, explicitly staged:
  `git add <specific files>` - never `git add -A`, never `git add .`.
- Message form, matching the repo style observed in the log
  (`test(ci): guard the deploy-check env block against prod-settings drift (CFG-002 durability half)`):
  `"{type}({scope}): {description}"`, e.g. `fix(users): declare UserAdmin fieldset contract`,
  `test(users): bind login token to the issuing browser`, `chore(users): annotate auth/session policy settings`.
- **Never** `git reset`, `git checkout`, `git restore`, `git stash`, `--amend`,
  `--no-verify`, or any other history mutation. Never force-push.
- **Other agents are working in parallel.** Files you did not change appearing in
  `git status` is normal. **Never** revert, stash or `git checkout` a file you did not
  write. If a file you are about to edit already has uncommitted changes from another
  agent, stop and report it rather than clobbering it.
- Do not commit unless the block's instructions say to.

### 1.4 Standing project rules (restated for every block)

- **English only** - comments, logs, docstrings, error messages, docs.
- **No `print()`.** `logger = logging.getLogger(__name__)`.
- Stack: Python 3.14 - Django 5.2 LTS (`>=5.2.16,<6.0`) - PostgreSQL 18 - aiogram 3.x -
  native PostgreSQL FTS. **Two processes, one DB:** web (gunicorn sync WSGI, HTMX MPA)
  and bot (aiogram, `django.setup()` + shared ORM). **Migrations run exactly once**
  before both start - a migration that must run in only one process is a defect.
- **Django ORM is the persistence layer.** Pydantic v2 is used only at system
  boundaries (bot input, settings schemas). Do not introduce Pydantic DTOs into the
  view/service path.
- **All schema changes via Django migrations.** No hand-written DDL.
- **Fixed values via `StrEnum`** (project rule 10) - never plain strings or dicts.
  `login_token.ConsumeOutcome` is the existing in-repo pattern to follow.
- Small, focused modules and functions. **Composition over inheritance.** Follow
  existing patterns; **no new abstraction without strong justification**; no
  speculative redesign; no scope creep.
- **Production code is king.** If a test conflicts with the architecture or the
  business logic, fix the test - and say which change and why in the commit body.

### 1.5 Test authoring standard for every block

Tests must verify **logic and component interaction**, not implementation trivia. No
test that asserts a literal private name, a line number, a template-string substring,
or the mere presence of a symbol. Good targets for this phase:

- a wrong-browser consume returns `410` while the right-browser consume returns `200`;
- a second open tab produces exactly the expected number of live tokens;
- the admin change form's field set does not contain `is_superuser`, **and** saving a
  user through it does not turn a plaintext write into a usable credential;
- a rate-limit key built from a forged `X-Forwarded-For` is identical to the key built
  from a request with no such header, for a client behind a trusted proxy;
- a session for a banned user is invalidated on the next request **through the real
  entry point**, not through a hand-built fixture.

Fixtures are canonical in `src/backend/conftest.py`: `seller` (900000001), `user`
(900000002), `category`, `city`, and
`create_test_ad(user, category, city, *, status=AdStatus.PUBLISHED, **kwargs)`.
`src/telegram_bot/tests/conftest.py` redefines these as an **async** `user`; bot
tests cannot import the backend conftest.

---

## 2. Scope decisions table

The disposition every finding receives. `**` = the plan is not closing it in this phase.

| Finding | Disposition | Block | Rationale | Where routed if not here |
|---|---|---|---|---|
| `04-AUT-001` | **Implement** (design-gated on Q1) | 3 | Real, HIGH, still open; the only in-repo mechanism that can bind a token to a browser | — |
| `04-AUT-002` | **Implement, session-layer half only** | 6 | `04-VAL-001` splits it from `15-AUTHZ-001`. The *per-request gate* is phase 15's; the *revocation at the point of change* is phase 04's. Shipping both middlewares is the named failure mode. | Per-request gate → phase 15 (`15-AUTHZ-001`) |
| `04-AUT-003` | **Implement** (design-gated on Q2, Q9) | 7 | Real rate-limit bypass; three duplicated copies; nginx appends to a client-supplied header | — |
| `04-AUT-004` | **Implement** (decision-gated on Q3, Q4) | 4 | The field is a real model field that code sets and no code reads. Leaving it is not "conservative"; it is a trap. But enforce-vs-remove is genuinely undetermined. | Enforcement *inside* the gate → phase 15 (`15-AUTHZ-001`) |
| `04-AUT-005` | **Implement, three parts** | 1, 2, 5 | Same root cause as `PII-103`; three distinct mechanisms (form contract, bootstrap policy, recovery + the false claim). Split because they have different risk profiles and different gates. | — |
| `04-AUT-006` | **Implement or document** (decision-gated on Q6) | 8 | The deviation is real and stated. Option (c) - correct the spec and ship nothing - is admissible and is cheapest. | — |
| `04-AUT-007` | **Implement, invalidation half only** | 3 | The CSRF/`GET`-writes half is `15-AUTHZ-004`, which phase 15 owns; moving `login_issue` to `@require_POST` from this phase would collide with their route/method decision. | CSRF / route / method → phase 15 (`15-AUTHZ-004`) |
| `04-VAL-001` | **Binding constraint** | 6 | "Both phases must not file the same middleware." Adopted verbatim as a hard rule. | — |
| `04-VAL-002` | **Tracker requirement (DoD) + optional comment hygiene** | 9 | The tracker keying is a process deliverable (§8.1), not a code change. The in-source `AUT-00N` comments are informational; cleaning them is a comments-only commit. | — |
| `04-VAL-003` | **Binding constraint** | 3 | "The binding design must be settled before implementation, not during." The column-vs-session-store choice is a Q1 gate. | — |
| `04-VAL-004` | **Binding constraint** | 1, 2 | "The admin-form fix must land with or before the validator work, and the form-introspection test is mandatory." Encoded as the edge `BLOCK 1 -> BLOCK 2`. | — |
| `04-VAL-005` | **Split** | 5 | Phase 06 declared `PII-113` "the finding of record" and `04-VAL-005` "a cross-reference". Only the *password-reset claim* half stays with phase 04. | `spec-index.md` DECLINE-semantics conflict → phase 06 (`PII-113`) |
| `04-VAL-006` | **New (Planner)** | 0.4 | Severity-tally arithmetic error in the report's own summary line (8 items for 7 findings). Recorded, not implemented. | — |

**De-scoping decisions, stated so they are not re-litigated:**

1. **No per-request account-state middleware from this phase.** The validator
   reproduced the defect end to end; this phase does not fix it. That is phase 15's
   `15-AUTHZ-001`, and shipping a competing gate is the exact failure
   `04-VAL-001` names.
2. **No CSRF / route / method change to `login_issue`.** `15-AUTHZ-004` owns it, and
   their recommendation includes a product decision about deep-link UX that phase 04
   must not pre-empt.
3. **No `MEDIA_ROOT` / session-store switch, no `SESSION_ENGINE` change.** Tempting
   for BLOCK 3's Q1 option (a) and BLOCK 8, and explicitly out of bounds here.
4. **No `clear_cookies` / `clear_sessions` management command.** BLOCK 3 may *note*
   the missing janitor in the module docstring; adding a janitor is a different
   finding and belongs to whichever phase owns session storage.
5. **No `django_session` global or `session_data LIKE` sweep** for `AUT-002`. The
   report already rejected it as fragile, unverifiable and unshippable; BLOCK 6
   records the same rejection rather than re-litigating it.
6. **No change to the phase-06 or phase-15 audit reports, and none to
   `docs/01-spec/technical-specification.md`.** Phase 06 (`PII-113`) is editing both.

---

## 3. Execution blocks

Nine blocks. Each is a coherent, independently committable unit. Only semantic code
units are named - files, modules, classes, functions, methods - never line numbers.
Block numbers are assigned in execution order (see §4.1).

---

### BLOCK 1 - `UserAdmin` field contract: close the auto-built form (`04-AUT-005`, `04-VAL-004`, merged `PII-103`)

| | |
|---|---|
| **Findings owned** | `04-AUT-005` (credential half + consent half), `04-VAL-004`, `PII-103` (merged into `04-AUT-005` by phase 06) |
| **Depends on** | none - this is the entry point of the plan |
| **Blocks** | BLOCK 2 (`04-VAL-004`: the form fix lands with or before the validator work) |
| **Priority** | **P0** - highest consequence, smallest diff |
| **Risk level** | **HIGH** (privilege escalation + credential write in a single class) |
| **Required agents** | **Implementor, Auditor, Researcher, Planner, Validator** (all) |

**Why this is first.** It is a one-class change with no call-site fan-out, no
migration, no shared artefact beyond one file, and it closes the single largest
security hole in the phase. Everything else in this plan depends on the admin surface
being trustworthy (phase 15's `AUTHZ-003` cites it as a hard prerequisite; phase 06's
`PII-107` depends on the form fix landing first).

**Agent requirement decision**

- **Implementor - required.** One `ModelAdmin` subclass, one test module.
- **Auditor - required.** Two things must be re-derived rather than copied, and one
  of them is not obvious: (i) the exact current field set, by form introspection, so
  the new `fieldsets` is built from the live `User` field list and not from a report
  that said "22"; (ii) whether `LoginTokenAdmin`'s explicit `readonly_fields` list and
  absence of `fields` still behave correctly - a *new* column on `LoginToken` (BLOCK 3
  option (a)) interacts with a `ModelAdmin` that declares `readonly_fields` but no
  `fields`. That is a BLOCK 3 question surfaced here; the Auditor records the answer
  so BLOCK 3 does not rediscover it.
- **Researcher - required.** The form design is a genuine multi-approach question with
  support and security implications: (a) Django's own
  `django.contrib.auth.forms.UserChangeForm` (brings
  `ReadOnlyPasswordHashField`, so a plaintext write is structurally impossible),
  (b) `UserAdmin.fieldsets` alone with `password` moved to `readonly_fields`, or
  (c) a purpose-built form in a new module. There is **no `forms.py` and no
  `admin_forms.py` anywhere in the repo**, so (c) creates the first one. The
  Researcher must establish which option is both minimal and durable, and must
  confirm the interaction with `AUTHZ-003`'s role predicate and with the
  `ListFilter`-only `is_staff` / `is_superuser` filters already declared.
- **Planner - required.** The field *partition* is a design decision with real
  operational consequences: which fields become `readonly`, which become editable by
  a superuser only, and whether `is_declined` / `is_deleted` / `ads_auto_publish` are
  removed from the form entirely (phase 06's position) or moved to a dedicated
  moderation-only action. This is a small module whose interface must be fixed before
  code is written.
- **Validator - required.** This is a privilege-escalation fix. A Validator must
  confirm independently that a plain `is_staff` moderator can no longer reach
  `is_superuser`, `user_permissions`, `groups` or the password field, and that
  existing operator workflows that used the removed fields are recorded as intentionally
  broken.

**Findings and notes carried forward**

- **`04-VAL-004` - binding.** The form-introspection test is **mandatory** and lands
  in this block, not later. `test_admin_pii_containment.py` covers `list_display`
  helpers only; there is currently **no test anywhere that asserts the admin form's
  field set.**
- **`PII-103` - merged here by phase 06's validator, explicitly.** "Same root cause,
  byte for byte. ... One `fieldsets` declaration. Two patches to the same class would
  be a partial fix at best." Phase 06's own roadmap puts this at order 0. **Do not
  patch `UserAdmin` twice; phase 06 must not patch it either.**
- **Field count.** The report and phase 06 both say 22 editable base fields. That
  number was produced by introspection; re-derive it rather than hard-coding it, and
  assert on the *absence* of the dangerous fields rather than on a count.

**Open choice - form design (Q-new, resolved by the Researcher/Planner pre-step)**

| Option | What it is | Maintainability | Future evolution | Project-convention fit |
|---|---|---|---|---|
| **A** | Reuse `django.contrib.auth.forms.UserChangeForm` as `UserAdmin.form`, plus an explicit `fieldsets` | Highest - zero new code; Django keeps the hash widget and `set_password` flow correct | Any `User` field added later still must be added to `fieldsets` by hand | Best - no new module, no new pattern, uses the framework |
| **B** | `fieldsets` only; `password` moved to `readonly_fields` | Simple, but leaves the plaintext-write path structurally reachable if the model field is ever re-exposed | Weakest - nothing prevents regression | Acceptable |
| **C** | A purpose-built form in a new `apps/users/forms.py` | Most control, most code | Best long-term isolation | Weakest - introduces the repo's first `forms.py` for one class |

**This plan does not choose.** The Researcher + Planner pre-step must record a
decision. The strong prior is **A** (project rules 5 and 7: prefer the obvious,
follow existing patterns, no new abstraction without justification), but that prior is
not this plan's to convert into a decision.

**File surface (semantic units)**

| File | Symbols touched | Notes |
|---|---|---|
| `src/backend/apps/users/admin.py` | `UserAdmin` - add `form`, possibly `add_form`, `fieldsets`; amend `readonly_fields`, `list_display`, `list_filter` | The only production file |
| `src/backend/apps/users/forms.py` or `admin_forms.py` | **New, only if option C is chosen** | Does not exist today |
| `src/backend/apps/users/tests/test_admin_pii_containment.py` | Extend with the form-introspection test class | Existing module, already owns admin-surface PII assertions |
| `src/backend/config/urls.py` | `urlpatterns` (read-only) | To locate the admin prefix for the test |
| `docs/02-database/db-schema.md` | `users` table column notes | Only if a field is added or removed, which option A/B/C all avoid |

**`UserAdmin.withdraw_consent_action` is explicitly OUT of this block.** It is
BLOCK 6's surface. Do not touch it here.

**Implementor task** (`.ai/tasks/templates/task_template.yaml` shape)

```yaml
id: task_04_b01_useradmin_field_contract
title: "Declare an explicit field contract on UserAdmin (AUT-005 / PII-103)"
priority: high
depends_on: []
source_reference: ".ai/plans/04-auth-login-remediation.md"
source_section: "BLOCK 1 - UserAdmin field contract"
source_blocks: ["BLOCK 1"]
description: >
  UserAdmin declares no `fields`, no `fieldsets` and no `form`, so Django's
  ModelAdmin.get_form() auto-builds a ModelForm over every editable User field,
  including `password` (bound as a CharField and written verbatim by
  save_model -> obj.save() with no pre_save hasher), `is_superuser`,
  `user_permissions` and every consent-state flag. Declare the field contract
  explicitly and add the mandatory form-introspection test.
goals:
  - "close the plaintext-password write path through the admin change form"
  - "make identity, privilege and consent-state fields non-editable through the form"
  - "land 04-VAL-004's mandatory form-introspection test in the same commit"
files:
  - path: "src/backend/apps/users/admin.py"
    targets:
      - type: class
        name: UserAdmin
    semantic_anchors:
      insert_before:
        type: method
        name: has_add_permission
      replace:
        type: attribute
        value: readonly_fields
  - path: "src/backend/apps/users/tests/test_admin_pii_containment.py"
    targets:
      - type: class
        name: TestAdminPiiContainment
changes:
  - action: add_code
    description: >
      Declare the explicit field contract per the recorded Researcher/Planner
      decision (fieldsets and/or form). `password` must never be writable as
      plaintext; `is_superuser`, `user_permissions` and `groups` must not be
      reachable by a plain is_staff moderator; `is_declined`, `is_deleted` and
      `ads_auto_publish` must not be editable through the change form.
    code_hint: |
      # Option A shape - confirm with the pre-step decision before writing
      from django.contrib.auth.forms import UserChangeForm

      form = UserChangeForm
      fieldsets = (...)  # explicit, introspected from User._meta.get_fields()
acceptance_criteria:
  - "introspecting UserAdmin.get_form() yields no `password` CharField write path"
  - "a plain is_staff moderator cannot change is_superuser / user_permissions / groups"
  - "consent-state flags are not editable through the change form"
  - "an existing operator workflow that used a removed field is recorded as intentionally broken"
tests_to_run:
  - "src/backend/apps/users/tests/test_admin_pii_containment.py"
  - "src/backend/apps/users/tests/test_consent.py"
```

**Tests required** (logic and interaction, not implementation trivia)

1. **Form-introspection test (mandatory, `04-VAL-004`).** Assert on the *absence* of
   `password`, `is_superuser`, `user_permissions`, `groups`, `is_declined`,
   `is_deleted`, `ads_auto_publish` from the change form's field set. Do **not** assert
   a field count - the number must not be the contract.
2. **Credential test.** Save a user through the real admin change view with a
   plaintext value in the password field and assert the stored credential is not
   usable as that value. If option A is chosen, assert the widget renders the hash
   form.
3. **Permission test.** Authenticate a plain `is_staff` moderator (not a superuser),
   GET their own `UserAdmin` change form, and assert the privilege fields are absent -
   this reproduces the phase-15 validator's live self-grant probe and must now fail to
   escalate.
4. **Regression.** `test_admin_pii_containment.py`'s four existing
   `list_display`-helper tests must still pass unchanged.

**Risk and rollback**

- *Security regression if done wrong:* making a field `readonly` that an operator
  depends on is a visible functional regression; leaving one privilege field editable
  is an incomplete fix. Both are caught by tests 1 and 3.
- *Rollout:* instant, no migration, no data change. Reversible by reverting the single
  commit.
- *Rollback:* a straight revert restores the previous form. There is no data to
  restore.
- *Cross-phase:* phase 15 `AUTHZ-003` and phase 06 `PII-107` both cite this as a hard
  prerequisite. This block must not be deferred behind either.

---

### BLOCK 2 - Bootstrap password policy: `AUTH_PASSWORD_VALIDATORS` and `create_admin_user` (`04-AUT-005`, part 2)

| | |
|---|---|
| **Findings owned** | `04-AUT-005` (policy half) |
| **Depends on** | **BLOCK 1** - `04-VAL-004`: the admin-form fix lands with or before the validator work |
| **Blocks** | BLOCK 5, BLOCK 9 |
| **Priority** | P1 |
| **Risk level** | MEDIUM |
| **Required agents** | **Implementor, Planner, Validator** - Auditor **not** required, Researcher **not** required |

**Agent requirement decision**

- **Implementor - required.** Two settings lines and one management command.
- **Auditor - NOT required.** The whole surface is two files, both fully enumerated
  above (0.2 item 7). There is no uncertainty to resolve; the only unknowns are
  policy choices, which are not code-architecture questions.
- **Researcher - NOT required.** Django's built-in validator set is standard
  framework surface, and the repo already has a pattern to follow. Surveying external
  password-policy sources would add ceremony without changing the answer.
- **Planner - required.** The design question is real and small: which validators to
  enable, and - more importantly - how an explicit policy interacts with a
  bootstrap command whose entire job is "create the first account". A policy that
  rejects the operator's chosen password must **fail the command with a clear message**,
  not silently weaken itself, and the `skip if the user already exists` branch must not
  be made to fail.
- **Validator - required.** This changes the only credential that matters on the box
  and it can lock the operator out of `/admin/`. A Validator must confirm the failure
  mode is a clear, actionable error and that no existing test or documented bootstrap
  command breaks.

**Findings and notes carried forward**

- **`04-VAL-004`.** The form fix must land first so that "no admin path can set a weak
  password" is true end to end. Encoded as the edge `BLOCK 1 -> BLOCK 2`.
- **The skip-if-exists trap.** `create_admin_user` has three early-return branches
  (existing `telegram_id`, existing `username`, empty password). Validation must be
  placed so that the *already-exists* path is unaffected and the *empty* check keeps
  its current, clearer message.
- **Phase 02 coupling.** `EMAIL_*` settings are phase 02's `CFG-004` territory. This
  block touches `base.py` but **not** any `EMAIL_*` key. See §5.5.

**Open choice - validator set (small, decided by the Planner, recorded)**

At minimum `MinimumLengthValidator` and `CommonPasswordValidator`;
`NumericPasswordValidator` and `UserAttributeSimilarityValidator` are the debatable
two. Whatever is chosen goes into `AUTH_PASSWORD_VALIDATORS` in
`src/backend/config/settings/base.py` **with a comment naming the length and the
reason**, so the next reader does not have to look it up. This is a one-line-of-record
decision for the Planner, not a phase-level gate.

**File surface**

| File | Symbols | Notes |
|---|---|---|
| `src/backend/config/settings/base.py` | add `AUTH_PASSWORD_VALIDATORS`; annotate the existing `SESSION_COOKIE_*` / `CSRF_COOKIE_*` block | BLOCK 9 also annotates this file - sequence BLOCK 9 last |
| `src/backend/apps/core/management/commands/create_admin_user.py` | `handle`, the `--password` argument | The only other production file |
| `src/backend/apps/core/tests/` (new or existing command-test module) | — | The command currently has no validator test |

**Implementor task**

```yaml
id: task_04_b02_bootstrap_password_policy
title: "Configure AUTH_PASSWORD_VALIDATORS and validate the bootstrap admin password"
priority: high
depends_on: [task_04_b01_useradmin_field_contract]
source_reference: ".ai/plans/04-auth-login-remediation.md"
source_section: "BLOCK 2 - Bootstrap password policy"
description: >
  No AUTH_PASSWORD_VALIDATORS is configured anywhere, so Django's default empty
  list is in force and every weak password is accepted. Configure the validator
  set in base.py and call validate_password() explicitly in create_admin_user
  so the policy cannot be bypassed by the bootstrap path.
goals:
  - "give every credential a policy, including the bootstrap credential"
  - "make a policy failure a clear actionable error, not a silent downgrade"
files:
  - path: "src/backend/config/settings/base.py"
    targets:
      - type: module
        name: AUTH_PASSWORD_VALIDATORS
    semantic_anchors:
      insert_before:
        type: assignment
        value: SESSION_COOKIE_SECURE
  - path: "src/backend/apps/core/management/commands/create_admin_user.py"
    targets:
      - type: class
        name: Command
      - type: method
        name: handle
    semantic_anchors:
      insert_after:
        type: function_call
        value: options.__getitem__
      insert_before:
        type: function_call
        value: set_password
changes:
  - action: add_code
    description: >
      Configure AUTH_PASSWORD_VALIDATORS with the recorded validator set and
      an explanatory comment; call django.contrib.auth.password_validation
      .validate_password(password, user=None) after the existing empty-password
      check and before set_password, converting DjangoValidationError into a
      non-zero CommandError with the human-readable message.
acceptance_criteria:
  - "a weak password is rejected by create_admin_user with a clear error and no user row"
  - "a strong password creates the user exactly as before"
  - "the already-exists skip branch is unaffected by the policy"
  - "base.py documents the chosen length and why"
tests_to_run:
  - "src/backend/apps/core/tests/ (the create_admin_user command tests)"
```

**Tests required**

1. A weak password raises a `CommandError` (or `ValidationError`) and leaves no `User`
   row behind.
2. A strong password creates the user; the stored credential authenticates.
3. The "user already exists" branch still skips silently - it must not start failing
   because of the new policy.
4. The empty-password branch keeps its own, more specific message.

**Risk and rollback**

- *Rollout:* instant, no migration. **The one real risk is operator lockout** - if the
  policy is stricter than the password the operator bootstrapped with, `create_admin_user`
  will refuse and the documented runbook command in `docs/ops/` will break. The
  implementor must check that doc and BLOCK 5 must correct it if needed.
- *Rollback:* revert the settings block; the command reverts with it. No data change.

---

### BLOCK 3 - Login-token browser binding and per-browser invalidation (`04-AUT-001`, `04-AUT-007`)

| | |
|---|---|
| **Findings owned** | `04-AUT-001` (invalidation-independent binding), `04-AUT-007` (**invalidation half only**) |
| **Depends on** | none in this plan (its gate is Q1, not a block) |
| **Blocks** | BLOCK 4, BLOCK 6 - both edit `apps/users/views/consent.py` |
| **Priority** | **P0** |
| **Risk level** | **HIGH** - the largest single diff in the phase, touching a security-critical handshake shared by two processes |
| **Required agents** | **Implementor, Auditor, Researcher, Planner, Validator** (all) |

**Agent requirement decision**

- **Implementor - required.**
- **Auditor - required.** Two real unknowns: (i) whether the enforcement point belongs
  in the service (`login_token.py`, which already owns the whole lifecycle) or in the
  view, given that `TestLoginHandshakeOwnership::test_consent_view_has_no_token_logic`
  forbids `LoginToken` and `hashlib` inside `consent.py`; (ii) what a *legacy* token
  with no binding means in a deployment where tokens are already in flight.
- **Researcher - required.** Q1 has at least three defensible designs with different
  operational and security characteristics, and the choice is not derivable from the
  code. The Researcher must survey browser-binding mechanisms for a two-phase
  out-of-band handshake, including the standard "token must be redeemed by the session
  that requested it" pattern and the known failure modes of each.
- **Planner - required.** `04-VAL-003` states it outright: "The binding design must be
  settled before implementation, not during." The Planner must produce the interface
  first - the signature change, the enforcement point, the rejection semantics - and
  hand it to the Implementor as a fixed contract.
- **Validator - required.** This is a two-process handshake (bot claims, web consumes)
  whose invariant is zero-TOCTOU on both halves. A Validator must confirm the claim /
  consume agreement tests still hold, that the new binding does not open a race, and
  that a rollback cannot leave a half-bound token.

**Open choice - Q1 binding approach. DECISION REQUIRED BEFORE IMPLEMENTATION.**

A **Researcher + Planner pre-step must complete and be recorded before this block
starts.** The plan does not pick.

Both viable designs converge on the **same service interface**, which is the one
decision that *is* settled here:

> `issue_token()` gains a *binding* parameter supplied by the caller; `consume_token()`
  (or `claim_token()`, depending on where enforcement lands) gains the matching check;
  the caller passes the value it holds. The **option** decides only *where the binding
  is persisted* and *what the legacy/absence semantics are*.

| Option | Mechanism | Cost | Consequence if chosen |
|---|---|---|---|
| **A - column** | New nullable `LoginToken` column holding the issuing browser's `session_key`; `login_issue` passes `request.session.session_key`, `login_status` requires a match | **New migration** in `apps/users/migrations/`. **Must** extend `claim_token`'s `RETURNING` list to include the new column, or `zip(..., strict=True)` + `LoginToken(**...)` raises `TypeError` **on the bot path**. The module docstring's "complete field set" contract must be updated in the same commit. | Enforcement is server-side and independent of the session store. Row growth is bounded - `cleanup_login_tokens` (hourly, advisory lock) is the janitor. Legacy rows and rows with no session (a client that refused the cookie) need an explicit policy. `LoginTokenAdmin` interaction must be re-checked (see BLOCK 1's Auditor task). `docs/02-database/db-schema.md` needs the new column. |
| **B - session store** | `login_issue` writes the token hash into `request.session`; `login_status` compares the posted token against the session value | No migration, no `RETURNING` edit, no schema contract change | **Converts a currently cookie-less endpoint into a session-writing one on every anonymous hit and every prefetch.** Verified: **`clearsessions` appears nowhere in the repository** - not in `HOURLY_COMMANDS`, not in `DAILY_COMMANDS`, not in any entrypoint - so `django_session` has **no janitor** and the rows accumulate without bound. The binding is also destroyed by any session flush between issue and consume. |
| **A' - non-session browser id** | A second, long-lived `login_issue` cookie holding a random browser id; a `LoginToken` column holds that id | Same migration and `RETURNING` cost as A, plus a second cookie | Survives session flushes. Costs a second cookie to manage, clear and document, and a second thing to leak. Listed for completeness; it is strictly more surface than A. |

**Cross-cutting consequences that apply to A, B and A' alike**

- **All seven direct-row tests must be revised.** Not six. See §4.4 item 1. The code
  context's claim that option B leaves them unchanged is **wrong**; all seven create a
  `LoginToken` row directly with a fresh `Client()` that never issued a token, so the
  binding is absent under every design and the endpoint answers `410`. The tests must
  be rewritten to obtain a token through `login_issue` (or to set the binding
  explicitly) before asserting on `login_status`.
- **A prefetch-safe form is a hard requirement, not a nicety.** `login_issue.html`
  embeds Open Graph tags, and several headless clients prefetch links. A binding that
  invalidates on every second request would make login unreliable in exactly the
  browser that needs it. The chosen design must tolerate a repeat issue from the same
  browser.
- **`TestIssueToken::test_two_issues_differ` is owned by `04-AUT-007`** and will fail
  once invalidation lands. It asserts that two `issue_token()` calls return different
  raw tokens - which remains true, because `AUT-007`'s remedy is that a *prior
  outstanding token is invalidated*, not that a fresh token cannot be minted. The test
  conflicts because it implicitly assumes multiple live tokens per browser. See §4.4
  item 2.
- **`TestLoginHandshakeOwnership`** is the structural guard for this block: `LoginToken`
  and `hashlib` must not appear in `consent.py`. Whatever design is chosen must keep
  the enforcement inside the service and pass only an opaque value from the view.

**`04-AUT-007` scope, stated precisely.** This block implements **only the
invalidation**: prior outstanding tokens for the same browser are invalidated when a
new one is issued, so a browser holds at most one live token. The **CSRF / `GET`-writes
half is `15-AUTHZ-004` and is out of scope** (§2 row `04-AUT-007`). Do not add
`@require_POST` to `login_issue`, do not change the route, and do not add a form.

**File surface**

| File | Symbols | Notes |
|---|---|---|
| `src/backend/apps/users/services/login_token.py` | `issue_token`, `consume_token`, `claim_token`, `ConsumeOutcome`; the module docstring's `RETURNING` and `AUT-007` boundary sections | The whole remediation point. Keep the two-phase predicate asymmetry; do not unify it. |
| `src/backend/apps/users/models.py` | `LoginToken` | **Only under option A / A'** |
| `src/backend/apps/users/migrations/` | one `AddField` migration | **Only under option A / A'**. Shared artefact - §5.6 |
| `src/backend/apps/users/views/consent.py` | `login_issue`, `login_status` | View passes the binding; owns no token logic |
| `src/backend/apps/users/tests/test_login_token.py` | `TestIssueToken`, `TestClaimToken`, `TestConsumeToken`, `TestClaimConsumeAgreement`, `TestLoginHandshakeOwnership` | Existing structural guards - do not weaken them |
| `src/backend/apps/users/tests/test_login.py` | `TestLoginStatus`, the `_claim_login` helper | Six of the seven direct-row tests |
| `src/backend/apps/users/tests/test_consent.py` | `TestLoginTokens` | The seventh |
| `docs/02-database/db-schema.md` | `login_tokens` table | **Only under option A / A'** |
| `docs/99-agent/architecture.md` | "The `AUT-007` boundary and the two existing deleters" | Update the boundary text once `AUT-007` lands |

**Implementor task**

```yaml
id: task_04_b03_token_binding
title: "Bind a login token to the browser that requested it and invalidate the prior one"
priority: high
depends_on: []
source_reference: ".ai/plans/04-auth-login-remediation.md"
source_section: "BLOCK 3 - Login-token browser binding and per-browser invalidation"
description: >
  Implement the recorded Q1 decision. issue_token() gains a caller-supplied
  binding; consumption requires the same binding; a new issue invalidates the
  browser's prior outstanding token. All seven direct-row tests and
  TestIssueToken::test_two_issues_differ are revised in the same commit.
goals:
  - "close AUT-001: a token cannot be redeemed by a browser that did not request it"
  - "close AUT-007: a browser holds at most one live outstanding token"
  - "keep the claim/consume zero-TOCTOU asymmetry intact"
  - "keep LoginToken and hashlib out of consent.py"
files:
  - path: "src/backend/apps/users/services/login_token.py"
    targets:
      - type: function
        name: issue_token
      - type: function
        name: consume_token
    semantic_anchors:
      insert_before:
        type: function_call
        value: LoginToken.objects.create
  - path: "src/backend/apps/users/views/consent.py"
    targets:
      - type: function
        name: login_issue
      - type: function
        name: login_status
    semantic_anchors:
      insert_after:
        type: function_call
        value: issue_token
acceptance_criteria:
  - "a token issued to browser A and redeemed by browser B returns 410"
  - "issuing a second token for browser A invalidates A's first, prefetch-safely"
  - "a repeat issue from the same browser still yields a working login"
  - "claim/consume agreement and ownership tests are unchanged and still pass"
  - "under the column option, claim_token's RETURNING matches LoginToken's field set exactly"
tests_to_run:
  - "src/backend/apps/users/tests/test_login_token.py"
  - "src/backend/apps/users/tests/test_login.py"
  - "src/backend/apps/users/tests/test_consent.py"
  - "src/telegram_bot/tests/ (the login handshake tests)"
```

**Tests required** (logic and component interaction)

1. **Wrong-browser rejection.** Issue in one client, redeem in a second client, assert
   `410` and assert the token is **not** consumed - a rejected redemption must not burn
   the legitimate browser's token.
2. **Same-browser success** end to end: `login_issue` -> bot claim -> `login_status`
   returns `200` and establishes a session.
3. **Prefetch tolerance.** Two issues from the same browser followed by one redemption
   succeeds; the count of live tokens for that browser is exactly one.
4. **Invalidation semantics.** After a second issue, the *first* token is no longer
   claimable - asserted through `claim_token`, not through a raw SQL count.
5. **Bot path unaffected.** `handle_login_orm` and the 12 bot test call sites keep their
   current signatures; the bot never supplies a binding and must not be asked to.
6. **All seven direct-row tests revised** to obtain the token through the issuing
   path, not by inserting the row.
7. **Regression:** `TestLoginHandshakeOwnership` passes unchanged. If it has to change,
   the block is wrong.

**Risk and rollback**

- *Security regression:* an over-strict binding locks legitimate users out (the most
  likely failure mode, given prefetch). A too-loose binding leaves `AUT-001` open while
  the tests still pass. Test 1 and test 3 together are the guard.
- *Session/cookie behaviour change:* under option B, `/login/issue/` begins emitting
  `Set-Cookie` and writing `django_session`. Anything that assumes the endpoint is
  cookie-less (caching, `never_cache` interaction, a CDN) is affected.
- *Migration hazard (option A):* the `RETURNING` list and the model field set must be
  edited in the **same commit**. A migration that lands without the `RETURNING` edit
  passes `makemigrations --check` and fails at runtime on the bot path only - which is
  the harder half to test. Run the full bot handshake test set, not just the web one.
- *Rollback:* revert the commit. Under option A the migration must be reverted with it
  (`RemoveField` forward or a paired revert) so a half-applied schema is never live.

---

### BLOCK 4 - `is_active` kill-switch: enforce or remove (`04-AUT-004`)

| | |
|---|---|
| **Findings owned** | `04-AUT-004` |
| **Depends on** | BLOCK 3 (both edit `login_status`; sequence so the file is not edited twice) |
| **Blocks** | nothing in this plan; hands a recorded decision to phase 15 |
| **Priority** | P1 |
| **Risk level** | **HIGH** (a disputed security control, and a direct contradiction with another phase) |
| **Required agents** | **Implementor, Auditor, Researcher, Planner, Validator** (all) |

**Agent requirement decision**

- **Implementor - required.**
- **Auditor - required.** Q4 is an **open re-derivation**, not a fact to copy. The
  report's premise is that a live session with `is_active=False` can still act; phase
  15's own matrix says `is_active=False` **already** yields a 302 on the web, which
  would refute it. Someone must actually run the current code and record which is true
  before a single line is written. The Auditor must also establish every reader and
  writer of `is_active` - the report names the writers; the readers must be enumerated,
  not assumed to be zero.
- **Researcher - required.** Enforce-vs-remove is a real best-practice question with
  two defensible answers (Django's `Model.is_active` exists precisely for
  "disable without delete"; a permanently `True` field is a maintenance trap that later
  readers will read as a control). The Researcher must establish which of those this
  project is, given that the product's own disable paths are ban / decline / soft-delete
  - all of which are *already* modelled as dedicated fields.
- **Planner - required.** Whichever option is chosen changes a shared predicate's
  vocabulary, and that predicate is being built by **phase 15**, not here. The Planner's
  job is to write a decision record phase 15 can consume.
- **Validator - required.** A kill-switch whose semantics are disputed, touching the
  login path, cannot be reviewed by the same reading that produced the dispute.

**Open choices - Q3 (enforce vs remove) and Q4 (is the premise true).**
**DECISION REQUIRED BEFORE IMPLEMENTATION.**

| Option | What it is | Blast radius | Consequence |
|---|---|---|---|
| **A - enforce** | `is_active=False` denies the authenticated tier, through the same shared account-state predicate that BLOCK 6 and phase 15's gate use | 7+ call sites of `can_login`; the bot's `AccountStateMiddleware`; a new DENY term in a shared vocabulary | Makes a real control out of a dead field. **But the enforcement point is phase 15's middleware, not this phase's** - so the honest deliverable here is the predicate term plus a decision record, not a shipped gate. Touches the bot, so it must be tested on both sides. |
| **B - remove** | `RemoveField` migration, drop the `is_active` term from every `User` construction in tests and factories, delete the dead admin form control | Every fixture and factory that sets `is_active`; a migration; the shared `User` field set | No new semantics to keep true. **But a `RemoveField` on a table that also carries the phase-06 erasure work and the phase-15 role work is a shared-artefact collision** (§5.6), and it forecloses the escape hatch for a compromised moderator account. |
| **C - status quo, recorded** | Ship no code; record in the decision log that the field is inert and that the product's disable paths are the three modelled flags | Zero | Cheapest, and arguably honest. **But it leaves a field named `is_active` that code sets and no code reads** - exactly the class of trap this phase exists to close, and it re-opens the question in every future audit. |

**This plan does not choose.** The Auditor must first answer Q4, because the answer
changes which options are even coherent: if the web already 302s on `is_active=False`,
the "enforce" option is mostly about *naming and location* rather than behaviour, and
the finding's premise is materially wrong and should be re-banded by whoever re-runs
the validator.

**Findings and notes carried forward**

- **`04-AUT-004` contradicts `15-AUTHZ-001`, deliberately.** Phase 15's recommendation
  names the DENY set `{is_banned, is_deleted, is_declined, consent_revoked}` and
  **explicitly carves `is_active` out of it**. The two phases cannot both be right.
  Phase 15's own rollout row records that `is_active=False` already redirects. **This
  plan does not implement a DENY set; it resolves only the field's status** and hands
  the gate vocabulary to phase 15. See §5.3.
- **The report's own numbers do not hold.** It claims `is_active=False` is "invisible
  end to end" in the 7 places `can_login` is called; phase 15's matrix contradicts that
  for the web tier. The Auditor must settle this from the code, not from either report.
- **Two pre-existing tests already describe the intended behaviour**
  (`test_account_state.py::test_can_login_returns_false_for_declined_user` and
  `..._for_banned_user`). They constrain this block and must not be broken.

**File surface**

| File | Symbols | Notes |
|---|---|---|
| `src/backend/apps/users/models.py` | `User` (the `is_active` field) | **Only under option B** (migration) |
| `src/backend/apps/users/services/account_state.py` | `AccountState`, `get_account_state`, `can_login` | **Only under option A** |
| `src/backend/apps/users/admin.py` | `UserAdmin` | `list_filter` only if the field is removed from the form - must be sequenced with BLOCK 1 |
| `src/backend/apps/users/migrations/` | one `RemoveField` migration | **Only under option B** - shared artefact (§5.6) |
| `src/backend/apps/users/tests/test_account_state.py` | `TestCanLogin` | Existing constraints; do not weaken |
| bot `AccountStateMiddleware` (`_check_user_state`) | — | **Option A only**; touches the bot process |
| `docs/01-spec/technical-specification.md` | — | **OUT OF SCOPE** - phase 06 `PII-113` is editing it (§6.2) |

**Implementor task**

```yaml
id: task_04_b04_is_active_kill_switch
title: "Resolve the is_active field: enforce as a kill-switch, remove, or record as inert"
priority: high
depends_on: [task_04_b03_token_binding]
source_reference: ".ai/plans/04-auth-login-remediation.md"
source_section: "BLOCK 4 - is_active kill-switch"
description: >
  The User.is_active field is written by code and read by no code. Phase 15's
  AUTHZ-001 deliberately carves is_active OUT of its DENY set and phase 15's own
  matrix shows is_active=False already redirects on the web, which refutes the
  phase-04 premise. Resolve Q4 by re-deriving the current behaviour, then take the
  recorded Q3 decision.
goals:
  - "record whether is_active currently has any effect, from the code"
  - "leave no field that code sets and no code reads, without contradicting phase 15"
  - "hand phase 15 a decision record it can use for its DENY set"
files:
  - path: "src/backend/apps/users/services/account_state.py"
    targets:
      - type: function
        name: can_login
      - type: class
        name: AccountState
    semantic_anchors:
      insert_before:
        type: return_statement
acceptance_criteria:
  - "the Q4 re-derivation is written down with the code path that produced it"
  - "the chosen option is recorded with its reason, not just applied"
  - "phase 15's DENY set is contradicted in writing, not silently"
tests_to_run:
  - "src/backend/apps/users/tests/test_account_state.py"
  - "src/backend/apps/users/tests/ (the dashboard and ad-ownership tests)"
  - "src/telegram_bot/tests/ (only if option A touches the bot middleware)"
```

**Tests required**

1. **The Q4 derivation test.** With the shipped code, assert what actually happens to a
   request from a session whose user has `is_active=False`. Name the test for the
   behaviour, not the option. If the derivation says "already denied", the test
   documents that; if it says "still allowed", the test is the failing proof the
   finding rests on.
2. **Option A only:** `is_active=False` denies the authenticated tier on the web **and**
   in the bot, with the same answer on both sides.
3. **Option B only:** `makemigrations --check` is clean and no fixture, factory or
   `User.objects.create(...)` call in the tree still passes `is_active`.
4. **Regression:** the two existing `test_account_state.py::TestCanLogin` tests pass
   unchanged. `can_publish_ad` and `get_state_badge` are untouched by this block.

**Risk and rollback**

- *Security regression:* option A, if the derivation is wrong, breaks login for any
  account the product or an operator disabled. Option B removes the ability to
  disable an account without deleting it - which is what `is_deleted` exists for, but
  that is a policy statement nobody has made.
- *Compatibility:* option B breaks every `User` factory and fixture that sets
  `is_active`; the count is not known until the change is made, and it spans both
  `conftest.py` files, including the **bot** one.
- *Cross-phase:* option A's enforcement point is phase 15's middleware. Shipping a
  competing gate from this block is the failure `04-VAL-001` names.
- *Rollback:* option A reverts as a code change. Option B needs the migration reverted
  with it.

---

### BLOCK 5 - Credential recovery, and the false password-reset claim (`04-AUT-005`, part 3; `04-VAL-005`, half)

| | |
|---|---|
| **Findings owned** | `04-AUT-005` (recovery half), `04-VAL-005` (**only** the password-reset-claim half) |
| **Depends on** | BLOCK 2 (a recovery path is governed by the policy BLOCK 2 configures) |
| **Blocks** | BLOCK 9 (this block owns one of the comments BLOCK 9 annotates) |
| **Priority** | P2 |
| **Risk level** | MEDIUM |
| **Required agents** | **Implementor, Researcher, Planner, Validator** - Auditor **not** required |

**Agent requirement decision**

- **Implementor - required.**
- **Auditor - NOT required.** The surface is fully enumerated: one comment in
  `config/settings/prod.py`, two statements in `docs/ops/docker-deployment.md`, and
  the absence of any password-reset route. There is no code-architecture uncertainty;
  the uncertainty is a product decision.
- **Researcher - required.** "Should this product have a self-service password-reset
  flow" is a product-and-security question with a real support/lifecycle dimension, and
  option (a) introduces a new admin surface (the reset UI) that BLOCK 1's field
  contract interacts with. The Researcher must establish what a minimal, correct
  implementation would cost and what the operational alternatives are.
- **Planner - required.** The block must be bounded: it is the *lowest-value* item in
  the plan and the most tempting place to start redesigning. The Planner must keep it
  to the decision plus its consequence.
- **Validator - required.** The block's highest-value half is **deleting a false
  claim**. A Validator must confirm the surviving `EMAIL_HOST` fail-fast is intact and
  that the docs no longer promise a capability the system lacks, without weakening a
  real control to do it.

**Findings and notes carried forward**

- **`04-VAL-005` is split, and this block is the half that stays.** Phase 06's `PII-113`
  is the finding of record for the `spec-index.md` DECLINE-semantics conflict and
  `04-VAL-005` is a cross-reference there. **This block must not edit
  `docs/01-spec/spec-index.md` or `docs/01-spec/technical-specification.md`.**
- **The false claim, verified:** `config/settings/prod.py`'s `EMAIL_HOST` fail-fast
  comment names password resets as a production requirement, and
  `docs/ops/docker-deployment.md` names password-reset tokens twice. There is no
  `password_reset` URL, no `PasswordResetView`, no reset template anywhere. **The
  `EMAIL_HOST` guard itself is legitimate and must survive** - it is a real
  fail-fast for transactional mail (phase 02 territory). Only the *claim* is wrong.
- **Phase 02 coupling.** `EMAIL_BACKEND` and the `EMAIL_*` block are `CFG-004`'s. This
  block touches the *comment* above the guard, never the guard and never the setting.
  Coordinate rather than collide (§5.5).

**Open choice - Q5. DECISION REQUIRED BEFORE IMPLEMENTATION.**

| Option | What it is | Consequence |
|---|---|---|
| **a - build recovery** | A `PasswordResetView` + route + templates + mail templates, wired into `config/urls.py` | Large. Adds a new admin-ish surface (the reset form), new `.po` strings in `ru` and `bs`, a new mail template, and a new dependency on `EMAIL_HOST` being correct in production. **Immediately re-opens the `EMAIL_HOST` question in a much more expensive way** - today the guard protects alert notifications and seller confirmations; with a reset flow it protects the only account-recovery path. Must land after BLOCK 2, and arguably after phase 02's `CFG-004` has settled `EMAIL_BACKEND`. |
| **b - correct the docs** | Rewrite the `prod.py` comment and the two `docker-deployment.md` statements to name the real reasons `EMAIL_HOST` is required (alert notifications, seller confirmations) and state that credential recovery is operator-mediated | Small, honest, zero new surface. Leaves operators without a documented recovery procedure, which is the actual gap. |
| **c - correct the docs and add an operator runbook** | (b) **plus** a documented operator procedure for resetting a credential through `manage.py`, with no new user-facing surface | Small, and closes the real gap. Requires a judgment on whether a `changepassword`-style management command already covers it - verify before writing anything new. **The prior is strongly in favour of (c) if Django's built-in `changepassword` is sufficient**, because that is the obvious solution the project rules (5, 7) point to. |

**This plan does not choose.** The Researcher + Planner pre-step must record a
decision. Note that (a) is the only option that is a *large* change; if (a) is chosen,
this block must be re-planned before it starts, not implemented as written here.

**File surface**

| File | Symbols | Notes |
|---|---|---|
| `src/backend/config/settings/prod.py` | the `EMAIL_HOST` fail-fast block - **comment only** | Never the guard, never `EMAIL_HOST` itself |
| `docs/ops/docker-deployment.md` | the secret-rotation section; the env-var table row for `DJANGO_SECRET_KEY` | Wording only |
| `src/backend/config/urls.py` | `urlpatterns` | **Option (a) only** |
| `src/backend/templates/` (new) | reset templates | **Option (a) only** - i18n applies, `ru` + `bs` non-empty |
| `src/backend/apps/core/management/commands/` | a reset command | **Option (c) only, and only if Django's `changepassword` is insufficient** |

**Implementor task**

```yaml
id: task_04_b05_credential_recovery
title: "Resolve credential recovery and correct the false password-reset claim"
priority: medium
depends_on: [task_04_b02_bootstrap_password_policy]
source_reference: ".ai/plans/04-auth-login-remediation.md"
source_section: "BLOCK 5 - Credential recovery and the false password-reset claim"
description: >
  The prod.py EMAIL_HOST comment and two docker-deployment.md statements claim a
  password-reset capability that does not exist. No password_reset URL, view or
  template exists anywhere. Take the recorded Q5 decision: build recovery, or
  correct the documentation (and, if chosen, add an operator runbook).
goals:
  - "stop the system documenting a capability it does not have"
  - "keep the legitimate EMAIL_HOST fail-fast fully intact"
  - "close the operator's real gap without inventing a new user-facing surface"
files:
  - path: "src/backend/config/settings/prod.py"
    targets:
      - type: module
        name: EMAIL_HOST
    semantic_anchors:
      replace:
        type: comment
        value: "Fail fast: EMAIL_HOST is required in production"
  - path: "docs/ops/docker-deployment.md"
    targets:
      - type: section
        name: "environment variables"
changes:
  - action: update_doc
    description: >
      Replace the password-reset claim with the real reasons EMAIL_HOST is
      required. If the Q5 decision is (a), this documentation change still
      applies and lands first, separately from the new flow.
acceptance_criteria:
  - "no document claims a password-reset capability the system lacks"
  - "the EMAIL_HOST fail-fast still refuses to boot without it"
  - "the operator has a documented way to recover a credential"
  - "any new user-visible string is translated for ru and bs"
tests_to_run:
  - "src/backend/apps/core/tests/ (the settings and command tests)"
  - "src/backend/apps/users/tests/ (the admin/auth tests)"
```

**Tests required**

1. A settings-level test that production settings still refuse to import with an empty
   `EMAIL_HOST` - the guard must not have been weakened while the comment was
   corrected.
2. If option (c): a test that the documented operator procedure actually works against a
   real user, end to end.
3. If option (a): the full reset flow, plus `test_i18n_completeness.py`, plus a
   `ru`/`bs` translation check on the new templates.
4. **No test is required for a documentation-only option (b)** beyond test 1.

**Risk and rollback**

- *Security regression:* the real risk is *removing a real control by accident* - the
  `EMAIL_HOST` guard is load-bearing for phase 02's work and for alert delivery. Test 1
  is the guard on that.
- *Blast radius:* option (a) is the only item in this plan that adds a user-facing
  surface, and it is the one most likely to be underestimated. If (a) is chosen, re-plan
  rather than execute.
- *Rollback:* (b) and (c) revert as doc/text changes. (a) needs the route, templates
  and `.po` entries reverted together.

---

### BLOCK 6 - Session revocation on account-state transitions (`04-AUT-002`, phase-04 half)

| | |
|---|---|
| **Findings owned** | `04-AUT-002` (**session-layer half only** - the per-request gate is phase 15's) |
| **Depends on** | BLOCK 3 and BLOCK 4 (all three edit `apps/users/views/consent.py`; sequence so the file is edited once per change, not three times) |
| **Blocks** | nothing |
| **Priority** | P1 |
| **Risk level** | **HIGH** (owns the phase's most contested ownership boundary) |
| **Required agents** | **Implementor, Auditor, Researcher, Planner, Validator** (all) |

**Agent requirement decision**

- **Implementor - required.**
- **Auditor - required.** Three questions must be answered from the code before
  anything is written: (i) which of the five account-state transitions can reach a
  `request` at all; (ii) whether a *target user's* session can be reached from a
  request made by someone else (an admin or a moderator); (iii) exactly what
  `ban_user_for_ad` and `bulk_ban_users` receive - the report's own text says neither
  has a `request`, and the Auditor must confirm that against the current signatures
  rather than trusting the report.
- **Researcher - required.** Q7 is a "is this worth shipping" question with a real
  precedent dimension: does the project want eager revocation (defence in depth, a
  predictable revocation event) or lazy revocation (a single per-request gate, the
  industry default)? Both are defensible; they have very different cost and one of them
  is a global O(sessions) problem.
- **Planner - required.** The block must produce a decision record phase 15 can consume
  *and* a code change that is provably not a second gate. The Planner owns that line.
- **Validator - required.** Shipping two competing account-state mechanisms is the
  single named failure mode of this phase. A Validator must confirm against the merged
  tree that exactly one gate exists.

**Open choices - Q7 (are the `logout()` calls worth shipping) and Q8 (the decline
path). DECISION REQUIRED BEFORE IMPLEMENTATION.**

**Q7 options**

| Option | What it is | Consequence |
|---|---|---|
| **a - ship every `logout()`** | Add session invalidation at each of the four open transitions | Two of the four are cheap (`consent_withdraw` already has one; the decline path is `request.user`). **Two are not: for the admin bulk-withdraw action, the moderator's single-ban view and the bulk-ban path, the affected identity is not the requester.** There is no `request` for the target, `bulk_ban_users` has no per-user object at all, and Django provides no queryset over "sessions belonging to user X" - the `_auth_user_id` lives inside an encoded `session_data` blob. The report already rejected a `LIKE`/decode scan as fragile, unverifiable and unshippable. **Closing them at the view layer would require either a new index on session ownership (a schema change for phase 04) or a global sweep.** |
| **b - ship only what the request already identifies** | `consent_withdraw` (already done) and - subject to Q8 - `consent_decline`; record the other three as subsumed by phase 15's gate | Small, correct, honest. Leaves the three hard paths to the mechanism that can actually cover them. **Costs nothing and duplicates nothing.** |
| **c - ship nothing; record the decision** | No code; a decision record naming phase 15's `AUTHZ-001` as the owner of all four | Cheapest. But the decline path - the one path that is genuinely, cheaply fixable here - stays open for another phase. |

**The evidence that makes Q7 decidable** (and it points, without deciding): of the
**4 open paths out of 5 rows**, only **`consent_decline`** has the property that the
identity whose state changed is the identity making the request. For
`UserAdmin.withdraw_consent_action`, `ban_user_for_ad` and `bulk_ban_users` the
affected identity belongs to *somebody else's* session, and the view layer structurally
cannot reach it. Phase 15's `AccountStateGateMiddleware`, which calls `logout(request)`
on the affected user's own next request, covers all four for free. **This is why
`04-VAL-001`'s split is the right split.**

**Q8 options (the decline path only) - HARD GATE**

| Option | What it is | Consequence |
|---|---|---|
| **a - `consent_decline` logs the user out** | `logout(request)` after `decline_consent(user)`, authenticated users only | Today `can_login(is_declined=True) is False`, so the logout is consistent with the enforced behaviour and with the one `04-VAL-005` document reading. **But phase 06's `PII-105` option (a) makes DECLINE reversible and regains web login** - at which point this logout becomes a *new* restriction on a path that is supposed to be recoverable, and the recovery affordance `PII-105` is simultaneously fixing becomes unusable. |
| **b - do not** | Leave the decline path to `can_login`'s next-request check | Defensible today. Leaves a window in which the session is still valid and the user can act until a protected view re-checks. |

**HARD GATE: BLOCK 6 must not ship the decline-path `logout()` before phase 06's
`PII-105` decision is known.** This dependency is recorded by **neither** report.
It is also the reason `04-VAL-005` matters operationally: the doc conflict is not
cosmetic, it is load-bearing for a code decision.

**Findings and notes carried forward**

- **`04-VAL-001` - binding.** "Both phases must not file the same middleware." This
  block ships **no middleware, no decorator, and no new gate**. It may add `logout()`
  calls at the points of change. If a reviewer sees a second gate appear in this block,
  the block is wrong.
- **`04-AUT-002`'s count is 4 of 5 rows, not 3 of 4** (§0.4 S-1). The five rows:
  self-service withdraw (**closed**), admin bulk withdraw (**open**), moderator single
  ban (**open**), moderator bulk ban (**open**), self-service decline (**open**).
- **Phase 03 tripwire.** `test_bulk_ban_users_not_locked` asserts that
  `bulk_ban_users` does **not** issue `select_for_update`. Do not add row locks to
  close a phase-04 finding.
- **`consent_decline` has a fourth open path the report's table does not list as a
  separate row but which the validator counted**: it is the fifth row and it is open.

**File surface**

| File | Symbols | Notes |
|---|---|---|
| `src/backend/apps/users/views/consent.py` | `consent_decline` | **Q8 only**; the one cheaply fixable path |
| `src/backend/apps/moderation/views/review.py` | `ban_user` | Record only, under option (c); no code change is possible here (see Q7) |
| `src/backend/apps/moderation/admin_actions.py` | `ban_user_for_ad`, `bulk_ban_users` | **Out of scope for this block's code.** Record the reason in the block's decision record. |
| `src/backend/apps/users/services/deletion.py` | `withdraw_consent` | Read-only reference - it already deletes the user's `LoginToken` rows |
| `src/backend/apps/users/tests/test_consent.py` | consent-view tests | Existing constraints |
| `src/backend/apps/users/tests/test_account_state.py` | `TestCanLogin` | Existing constraints - do not weaken |
| decision record (`.ai/` or the block's commit body) | — | The Q7/Q8 decision and its reason |

**Implementor task**

```yaml
id: task_04_b06_session_revocation
title: "Revoke the session at the point an account state change invalidates it (AUT-002 session layer)"
priority: high
depends_on: [task_04_b03_token_binding, task_04_b04_is_active_kill_switch]
source_reference: ".ai/plans/04-auth-login-remediation.md"
source_section: "BLOCK 6 - Session revocation on account-state transitions"
description: >
  Four of the five account-state transitions that change a user's authorization
  state never invalidate the session they caused. Three of the four cannot be
  fixed at the view layer because the affected identity is not the requester and
  Django offers no queryset over a user's sessions. Ship only what the request
  already identifies, record the rest, and ship NO gate - phase 15 owns the
  per-request gate (04-VAL-001).
goals:
  - "close the decline path if and only if Q8 permits"
  - "record the three unreachable-at-view-layer paths with their reason"
  - "ship zero middleware and zero competing gates"
files:
  - path: "src/backend/apps/users/views/consent.py"
    targets:
      - type: function
        name: consent_decline
    semantic_anchors:
      insert_after:
        type: function_call
        value: decline_consent
      insert_before:
        type: assignment
        value: target
acceptance_criteria:
  - "no middleware, decorator or shared gate is added by this block"
  - "the Q7 and Q8 decisions are recorded with their reason"
  - "a logged-out declined user cannot reach a protected view"
  - "test_bulk_ban_users_not_locked still passes - no row locks were added"
tests_to_run:
  - "src/backend/apps/users/tests/test_consent.py"
  - "src/backend/apps/users/tests/test_account_state.py"
  - "src/backend/apps/moderation/tests/ (the ban-action tests)"
```

**Tests required**

1. **Decline path (Q8 = a only):** an authenticated user who POSTs `/consent/decline/`
   is logged out, and their next request to a protected view is redirected to login.
   Assert the interaction end to end, through the real URL.
2. **Anonymous decline is unaffected:** an anonymous POST to `/consent/decline/` must
   not blow up and must not attempt a logout of nobody.
3. **Withdraw path is unchanged:** the existing `consent_withdraw` logout still
   behaves as it does today - this is a regression guard on the one already-closed row.
4. **The three unreachable paths:** a test that documents, per path, that the session
   survives - so the record is executable, not a comment. If Q7 = (c), these are the
   block's only tests and they must be named as known-gap tests, not as passing
   behaviour.
5. **Regression:** `test_bulk_ban_users_not_locked` passes unchanged.

**Risk and rollback**

- *Security regression:* the failure mode of Q8 = (a) under phase 06's `PII-105` option
  (a) is that a user who declined can no longer recover through the affordance
  `PII-105` is building. That is why Q8 is a hard gate, not a preference.
- *Session/cookie behaviour change:* `logout()` flushes the session and rotates the
  CSRF token. Any open HTMX fragment in the same page will 400. `consent_decline`
  redirects to `ads:dashboard`, which is a full navigation, so this should not fire -
   but it is the first thing to check if a decline test starts failing on CSRF.
- *Rollback:* a straight revert. No schema change, no data change.
- *Cross-phase:* the hard one. If phase 15 ships `AccountStateGateMiddleware` first,
  this block's decline-path logout becomes defence in depth (fine). If this block is
  skipped entirely, phase 15's gate still covers the decline path. **Either order is
  safe; two gates are not.**

---

### BLOCK 7 - Trusted-proxy-aware client IP: one helper, and the header it reads (`04-AUT-003`)

| | |
|---|---|
| **Findings owned** | `04-AUT-003` |
| **Depends on** | none in this plan (its gates are Q2 and Q9, not blocks) |
| **Blocks** | nothing |
| **Priority** | P1 |
| **Risk level** | **HIGH** - nginx is the TLS terminator; a mistake here collapses every client into one rate-limit bucket, which is a self-inflicted denial of service |
| **Required agents** | **Implementor, Auditor, Researcher, Planner, Validator** (all) |

**Agent requirement decision**

- **Implementor - required.**
- **Auditor - required.** Q2 is a pre-step: the trusted-proxy topology in front of
  nginx must be **re-derived**, not assumed. The Auditor must establish whether nginx
  is the first hop, whether anything (a CDN, a cloud load balancer, a corporate proxy)
  sits in front of it, and what `docker-compose.prod.yml` actually wires. Q9 is also an
  Auditor task: confirm whether an operational validation gate exists before the nginx
  file is edited.
- **Researcher - required.** The correct way to resolve a forwarded client address
  behind a known proxy chain is a well-documented problem with several incorrect
  folklore answers, and the security consequences of each differ. The Researcher must
  establish the current best practice for trusted-proxy resolution, the header a
  well-configured edge should set, and the failure mode of each variant.
- **Planner - required.** The block has two separable halves with different risk
  profiles and different testability. The Planner must fix the order (helper first,
  nginx second) and the shape of the shared helper, including where the trust
  configuration lives.
- **Validator - required.** The nginx half cannot be exercised by the test suite at
  all. A Validator must confirm the change is internally consistent and that the
  failure direction is the safe one.

**Open choices - Q2 (topology) and Q9 (operational gate).
Auditor pre-step required before this block starts.**

| Q2 outcome | What changes |
|---|---|
| **nginx is the first hop** (nothing in front) | The trust boundary is exactly one hop. The helper trusts `X-Forwarded-For` **only** when the immediate peer is a configured proxy address, and resolves the *rightmost* untrusted entry rather than `split(",")[0]`. nginx may be left with `$proxy_add_x_forwarded_for` if the helper is correct - but overwriting is still preferable, because it removes the attacker-controlled prefix at the source rather than defending against it downstream. |
| **something sits in front of nginx** | The chain is longer. The trust configuration must list the full chain, and which hop is the client becomes the last entry not in the trusted set. **This is the case the validator warned about:** if a CDN or load balancer is added later and only nginx's overwrite is applied without extending the trusted set, every client collapses into one bucket. |
| **unknown / cannot be established** | The block must not guess. Ship the **de-duplication half only** (one shared helper, three call sites, behaviour-preserving on the current single-hop topology) and record the trust half as blocked. See "Partial shipping" below. |

| Q9 outcome | What changes |
|---|---|
| **a validation gate exists** (`nginx -t` runnable, a compose config validation, or a container restart that surfaces a config error) | The nginx half ships in this block. |
| **no gate exists** | The nginx half is **deferred** with a recorded reason, and only the Python half ships. An unvalidated `nginx.conf` change that fails at reload takes the whole site down. The de-duplication is still worth shipping: it removes two of the three copies and makes the trust model a single, testable object. |

**Partial shipping is explicitly supported.** The report's own priority order puts
de-duplication above the nginx change, and the de-duplication is the half the test
suite can actually reach. A partial BLOCK 7 that ships the helper and records the
nginx half as blocked is a **complete, acceptable outcome** of this block.

**Findings and notes carried forward**

- **Three identical private copies**, all trusting `HTTP_X_FORWARDED_FOR`
  unconditionally and taking the first comma-separated element:
  `apps/users/services/login_rate_limit.py::_get_client_ip`,
  `apps/core/services/contact_rate_limit.py::_get_client_ip`,
  `apps/search/services/rate_limit.py::_get_client_ip`. `ruff` does **not** flag
  private-symbol duplication, so nothing enforces this today.
- **nginx appends, it does not overwrite.** `proxy_set_header X-Forwarded-For
  $proxy_add_x_forwarded_for;` appears in **9** locations in
  `docker/nginx/nginx.conf` (the report says 8). The `proxy_add_` form appends to any
  client-supplied value, so a client that sends
  `X-Forwarded-For: 1.2.3.4` produces `1.2.3.4, <real client>` in Django, and
  `split(",")[0]` returns the attacker's value.
- **`test_x_forwarded_for_takes_precedence` asserts the defect.** It sets
  `REMOTE_ADDR` and `HTTP_X_FORWARDED_FOR` to different values and asserts the header
  wins. Under any trust model that respects a configured proxy, that assertion becomes
  conditional on the peer being trusted. See §4.4 item 3 - **the test changes, the
  production code does not bend to it.**
- **nginx is demonstrably the trusted edge** in this project: it terminates TLS
  (Django sets `SECURE_PROXY_SSL_HEADER`), it emits HSTS alongside Django, and
  `USE_X_FORWARDED_HOST = True`. The trust model is not hypothetical.

**File surface**

| File | Symbols | Notes |
|---|---|---|
| **New** `src/backend/apps/core/services/client_ip.py` (or an equivalently named single module) | one `get_client_ip(request)` | Placement is the Planner's call; it is a cross-app concern, and `apps/core/services/` already hosts `contact_rate_limit.py` and `site_config.py`. **Verify there is no existing home first.** |
| `src/backend/apps/users/services/login_rate_limit.py` | `_get_client_ip` (delete), the module's rate-limit function | Delegate to the shared helper |
| `src/backend/apps/core/services/contact_rate_limit.py` | `_get_client_ip` (delete), `check_deep_link_render_rate_limit` | Delegate |
| `src/backend/apps/search/services/rate_limit.py` | `_get_client_ip` (delete), the rate-limit function | Delegate |
| `src/backend/config/settings/base.py` | a new trusted-proxy setting (name and type are the Researcher's call) | Must be a named, documented setting with a comment. **Do not invent a Django setting name without verifying Django 5.2 does not already provide one.** |
| `src/backend/config/settings/dev.py`, `test.py` | the same setting, if the default is "trust nothing" | Dev and test must both be explicit |
| `docker/nginx/nginx.conf` | all 9 `proxy_set_header X-Forwarded-For ...` directives | **Only if Q9 found a validation gate** |
| `src/backend/apps/core/tests/test_contact_rate_limit.py` | `test_x_forwarded_for_takes_precedence` | Must change (§4.4 item 3) |
| `src/backend/apps/users/tests/test_login.py` | `TestLoginRateLimitCheck` | Rate-limit behaviour regression |
| `docs/ops/docker-deployment.md` | the reverse-proxy section | Document the trust model; one line, no redesign |

**Implementor task**

```yaml
id: task_04_b07_client_ip
title: "Resolve the client IP through a trusted-proxy-aware helper shared by all three rate limiters"
priority: high
depends_on: []
source_reference: ".ai/plans/04-auth-login-remediation.md"
source_section: "BLOCK 7 - Trusted-proxy-aware client IP"
description: >
  Three private _get_client_ip copies trust HTTP_X_FORWARDED_FOR unconditionally
  and take split(",")[0]. nginx sets the header with $proxy_add_x_forwarded_for
  in 9 locations, so the first element is client-controlled. Extract one shared
  helper that trusts the header only when the immediate peer is a configured
  proxy, and resolve the last untrusted entry.
goals:
  - "make the rate-limit key unforgeable by a client-supplied header"
  - "delete two of the three private copies"
  - "ship the nginx half only if an operational validation gate exists"
files:
  - path: "src/backend/apps/core/services/client_ip.py"
    targets:
      - type: function
        name: get_client_ip
    semantic_anchors: {}
  - path: "src/backend/apps/users/services/login_rate_limit.py"
    targets:
      - type: function
        name: _get_client_ip
    semantic_anchors:
      delete:
        type: function
        name: _get_client_ip
acceptance_criteria:
  - "a forged X-Forwarded-For produces the same key as no header at all"
  - "a request whose peer is a trusted proxy and whose chain has one extra hop resolves to the right address"
  - "all three rate limiters call one shared helper; only one copy of the logic exists"
  - "the nginx half either ships with a recorded validation result, or is deferred with a recorded reason"
tests_to_run:
  - "src/backend/apps/core/tests/test_contact_rate_limit.py"
  - "src/backend/apps/users/tests/test_login.py"
  - "src/backend/apps/search/tests/ (the rate-limit tests)"
```

**Tests required** (logic and interaction)

1. **Forgery is neutralised.** A request from an untrusted peer carrying
   `X-Forwarded-For: 1.2.3.4` and a different `REMOTE_ADDR` produces the key for
   `REMOTE_ADDR` - that is, the same key a request with no header would produce.
2. **A trusted proxy is honoured.** A request whose `REMOTE_ADDR` is a configured proxy
   with a single-entry header resolves to the header value.
3. **A longer chain resolves to the last untrusted entry**, not the first element -
   this is the assertion that distinguishes a correct implementation from a folklore
   one.
4. **All three rate limiters produce identical keys for the same request.** This is the
   interaction test that proves the de-duplication actually happened.
5. **Behaviour regression:** an existing rate-limit trip still trips, and
   `TestLoginRateLimitCheck` passes.

**Risk and rollback**

- *The dominant risk is self-inflicted denial of service, not bypass.* If the trusted
  set is wrong - empty in production, or the peer address never matching - **every
  client resolves to the same key and one client can rate-limit the whole platform.**
  This is why the default must be **trust nothing**, with dev and test configured
  explicitly, and why test 1 is the one that must exist before the change lands.
- *Second risk:* applying the nginx overwrite *without* a correct trusted set collapses
  all clients at the nginx layer, where no Python test can see it. Both halves must
  land together or the nginx half must be deferred.
- *Shared-artefact note:* `docker/nginx/nginx.conf` and `config/settings/base.py` are
  touched by other phases' work. Stage only these files; never revert another's change
  in them (§1.3).
- *Rollback:* the Python half reverts as a code change. **The nginx half does not revert
  safely if it was never validated** - a broken directive takes the site down at
  reload, not at commit.

---

### BLOCK 8 - Session lifetime policy (`04-AUT-006`)

| | |
|---|---|
| **Findings owned** | `04-AUT-006` |
| **Depends on** | none in this plan (its gate is Q6) |
| **Blocks** | BLOCK 9 (which annotates the setting this block may add) |
| **Priority** | P2 |
| **Risk level** | LOW-MEDIUM |
| **Required agents** | **Implementor, Researcher, Planner, Validator** - Auditor **not** required |

**Agent requirement decision**

- **Implementor - required.**
- **Auditor - NOT required.** The fact is a one-line absence: `SESSION_COOKIE_AGE` is
  unset in every settings module, so Django's 14-day default applies. Verified.
- **Researcher - required.** Absolute vs sliding session lifetime is a standard
  security-design question with well-documented trade-offs, and what the spec
  actually promises is a question about the document, not the code.
- **Planner - required.** All three options are small; the Planner's job is to keep the
  block from expanding into session-storage work (§6, de-scoping item 3).
- **Validator - required.** Option (b) changes session behaviour globally and interacts
  with BLOCK 3's possible session write. A one-line settings change with a global
  behavioural effect deserves a second reading.

**Open choice - Q6. DECISION REQUIRED BEFORE IMPLEMENTATION.**

**The facts:** no `SESSION_COOKIE_AGE` is set anywhere, so Django's default applies -
a 14-day **sliding** expiry, refreshed on every write to the session. The technical
specification is worded as an **absolute** 14 days: the `SESSION_COOKIE_AGE` gap is a
**documentation** defect. The report therefore rates this LOW and recommends a
documentation change, not necessarily a code change.

| Option | What it is | Consequence |
|---|---|---|
| **a - absolute** | Set `SESSION_COOKIE_AGE` explicitly and stop refreshing | Closes the code/spec gap in the conservative direction. But the default is already 14 days, so this changes almost nothing operationally - it makes an existing behaviour explicit. Cheap and safe. |
| **b - real idle timeout** | Set the age **and** add sliding refresh at the intended point (e.g. `SESSION_SAVE_EVERY_REQUEST`, or an explicit `set_expiry` on activity) | Matches the spec's "after 14 days of inactivity" wording. **This is the real change**, and it is global: it alters every session's lifetime, it interacts with BLOCK 3's option B (a session-writing endpoint), and it is the option most likely to be misread as a security improvement when it is a behaviour change. |
| **c - document only** | Correct the spec to say the session expires after 14 days **of inactivity** and ship no code | The report's own recommendation, and the cheapest. Honest, and it leaves the behaviour exactly as Django defines it. **The prior is strongly in favour of (c)**, because the code is not wrong - the document is. But (c) requires editing the technical specification, which **phase 06 `PII-113` is also editing** (§5.5, §6.2). |

**This plan does not choose.** The Researcher + Planner pre-step must record a
decision. Note that (c) is blocked on a cross-phase document edit, which is a
sequencing fact, not a reason to prefer (a).

**File surface**

| File | Symbols | Notes |
|---|---|---|
| `src/backend/config/settings/base.py` | the `SESSION_COOKIE_*` block | Options (a) and (b) |
| `src/backend/config/settings/dev.py`, `test.py` | same | Only if the test suite needs a different lifetime |
| `docs/01-spec/technical-specification.md` | the session-lifetime statement | **Option (c) only - and only after coordinating with phase 06.** Phase 06's `PII-113` is editing this file; a concurrent edit to the same document from two phases is a lost-update hazard. §5.5 |
| session-affecting tests | `apps/users/tests/`, `apps/core/tests/`, fixtures using `force_login` | Option (b) only |

**Implementor task**

```yaml
id: task_04_b08_session_lifetime
title: "Reconcile the session lifetime with the specification"
priority: low
depends_on: []
source_reference: ".ai/plans/04-auth-login-remediation.md"
source_section: "BLOCK 8 - Session lifetime policy"
description: >
  No SESSION_COOKIE_AGE is configured, so Django's 14-day sliding default applies
  while the specification promises a 14-day absolute expiry. Take the recorded Q6
  decision.
goals:
  - "make the code and the specification agree about session lifetime"
  - "do not change session behaviour unless the decision says to"
files:
  - path: "src/backend/config/settings/base.py"
    targets:
      - type: module
        name: SESSION_COOKIE_AGE
    semantic_anchors:
      insert_after:
        type: assignment
        value: SESSION_COOKIE_SAMESITE
acceptance_criteria:
  - "the shipped behaviour matches the recorded Q6 decision"
  - "the specification states the shipped behaviour"
  - "no session behaviour changes under option (c)"
tests_to_run:
  - "src/backend/apps/users/tests/"
  - "src/backend/apps/core/tests/ (the settings tests)"
```

**Tests required**

1. **Option (a)/(b) only:** a session's age is exactly what the decision says, asserted
   through a real request cycle, not by reading a setting.
2. **Option (b) only:** an active session survives past the idle window and an inactive
   one does not - both halves, because the failure mode of a sliding-expiry change is
   that one of them is wrong.
3. **Option (c) only:** a settings-level test that the documented and configured
   lifetimes agree, so the next reader does not have to re-derive it.
4. **Regression:** the BLOCK 3 handshake tests still pass under any option - a session
   lifetime change must not break a 5-minute login handshake.

**Risk and rollback**

- *Session/cookie behaviour change:* option (b) logs users out more or less often than
  today, globally, including phase 06's `PII-105` recovery fixtures and every
  `force_login`-based test. That is the whole reason this is P2 and decision-gated.
- *Interaction with BLOCK 3:* under Q1 option B, `/login/issue/` writes the session. If
  BLOCK 8 option (b) also changes when the session expires, the two interact. BLOCK 8
  runs after BLOCK 3, so the interaction is observable - do not merge them into one
  commit.
- *Rollback:* options (a) and (b) revert as a settings change. Option (c) reverts as a
  document change, which is not safely revertible if phase 06 has since edited the same
  paragraph.

---

### BLOCK 9 - Annotation and identifier hygiene, comments only (advisory + `04-VAL-002`)

| | |
|---|---|
| **Findings owned** | `04-VAL-002` (in-source comment half), plus the report's advisory recommendation |
| **Depends on** | BLOCK 2, BLOCK 8 (it annotates settings those blocks add or change) |
| **Blocks** | nothing |
| **Priority** | P2 |
| **Risk level** | **LOW** - zero behaviour change, by construction |
| **Required agents** | **Implementor only.** No Auditor, no Researcher, no Planner, no Validator beyond normal commit review. |

**Agent requirement decision**

- **Implementor - required.**
- **Auditor / Researcher / Planner - NOT required.** There is no behaviour to change and
  no uncertainty to resolve. If this block starts growing, it has stopped being
  comments-only and has become a design change; stop and re-plan.
- **Validator - NOT required at the agent level.** The guard is mechanical: the diff
  must contain no executable change. That is checked in review and in §7.

**What this block does**

1. **Add an annotated `SESSION_*` / `AUTH_*` policy block** to
   `src/backend/config/settings/base.py`: one comment per setting saying what it is
   and why it is (or is not) configured. Six of the seven findings in this phase are
   "the control exists in Django but the project never configured it", and after this
   plan that will be visible in one place instead of being re-derived per audit.
2. **Clean the stale in-source `AUT-00N` comments** (12 references across 6 files).
   These comments were accurate when written and are now wrong because phase 01 moved
   the code. Each must be corrected to describe what the code *now* does.

**The two comments that are already correct and must not be touched**:
`login_token.py`'s module docstring sections *"The `AUT-007` boundary"* and
*"The `RETURNING` / model-shape coupling"*, and the `AUT-007` paragraph in
`docs/99-agent/architecture.md`. They are accurate, and the second is load-bearing
documentation for BLOCK 3.

**`04-VAL-002`'s tracker half is NOT this block.** The requirement that every key be
phase-qualified (`04-AUT-002`, never `AUT-002`) is a **process deliverable**, recorded
in §8.1 of this plan. It requires no code and no comment.

**File surface**

| File | Notes |
|---|---|
| `src/backend/config/settings/base.py` | The annotated `SESSION_*` / `AUTH_*` block |
| `src/backend/apps/users/views/consent.py` | Stale `AUT-00N` comments only |
| `src/backend/apps/moderation/admin_actions.py` | Comment only - **no behaviour change; `bulk_ban_users` must stay lock-free** |
| `src/backend/apps/users/admin.py` | Comment only |
| `src/backend/apps/core/tests/test_admin_pii_containment.py` | Comment only |
| The remaining file that carries a stale reference | Locate by searching for `AUT-00`; do not assume the file list |

**Implementor task**

```yaml
id: task_04_b09_annotation_hygiene
title: "Annotate the auth/session policy settings and correct stale audit-id comments"
priority: low
depends_on: [task_04_b02_bootstrap_password_policy, task_04_b08_session_lifetime]
source_reference: ".ai/plans/04-auth-login-remediation.md"
source_section: "BLOCK 9 - Annotation and identifier hygiene"
description: >
  Comments and comments only. Add an annotated SESSION_*/AUTH_* policy block to
  base.py, and correct the stale in-source AUT-00N comments so they describe the
  code as it is after phase 01's extraction and after this plan's changes.
goals:
  - "make the auth/session policy readable in one place"
  - "leave no comment in the tree that describes code that no longer exists"
files:
  - path: "src/backend/config/settings/base.py"
    targets:
      - type: module
        name: SESSION_COOKIE_SECURE
    semantic_anchors: {}
changes:
  - action: add_code
    description: >
      Comments and docstrings only. No executable statement may change. The
      diff must contain no behavioural change of any kind.
acceptance_criteria:
  - "the diff contains no executable change"
  - "no comment in the tree references code that has moved or has been removed"
  - "the two already-correct AUT-007 comments are unchanged"
tests_to_run:
  - "full fast gate - a comment-only diff that fails it means a comment was not the only change"
```

**Tests required**

- **The full fast gate.** A comment-only diff that fails any test means the block has
  changed something executable. That single check is this block's whole test budget.
- A repository search confirming no `AUT-00N` comment still points at code that has
  moved.

**Risk and rollback**

- *The only real risk* is a comment change that quietly reformats or reorders code. The
  fast gate catches it. Run it.
- *Do not* clean up the two correct `AUT-007` comments, and do not improve any
  docstring that another phase is concurrently editing.
- *Rollback:* a straight revert; no risk either way.

---

## 4. Dependency graph

### 4.1 Execution order (the safe serial order)

Nine blocks, **one Implementor at a time**, each committed separately:

> **BLOCK 1 → BLOCK 2 → BLOCK 3 → BLOCK 4 → BLOCK 5 → BLOCK 6 → BLOCK 7 → BLOCK 8 → BLOCK 9**

Two properties this order guarantees, and both are deliberate:

- **No block is ever implemented before its decision gate is closed.** BLOCK 3 waits on
  the Q1 Researcher + Planner pre-step; BLOCK 4 carries the Q3/Q4 gate; BLOCK 5 the Q5
  gate; BLOCK 6 the Q7/Q8 gate; BLOCK 7 the Q2/Q9 Auditor pre-step; BLOCK 8 the Q6
  gate. **No block is started with an open question and a "we will decide while coding".**
- **HIGH risk first.** BLOCKS 1, 3, 4, 6 and 7 are HIGH and all carry all four
  supporting agents. They run before the LOW-risk annotation block and before either
  P2 settings block, so the phase's most dangerous work is done while reviewer
  attention is fresh.

### 4.2 The DAG and why each edge exists

```
        [BLOCK 1  UserAdmin field contract]   (P0, HIGH, all agents)
                     |
                     |  04-VAL-004: "the admin-form fix must land
                     |  with or before the validator work"
                     v
        [BLOCK 2  Password validators +
                 create_admin_user]            (P1, MEDIUM, 3 agents)
                     |                    \
                     |  policy exists      \  04-VAL-004: BLOCK 9 annotates
                     |  before a recovery   \ the AUTH_* settings BLOCK 2 adds
                     |  path can be        \
                     |  governed            v
                     |              [BLOCK 8  Session lifetime]  (P2, Q6 gate)
                     |                     |        \
                     |                     |        \  BLOCK 9 annotates the
                     |                     |         \ SESSION_* settings
                     |                     v          v
                     |              [BLOCK 9  Annotation + ID hygiene]
                     |                        (P2, Implementor only)
                     v
        [BLOCK 3  Token browser binding +
                 per-browser invalidation]   (P0, HIGH, all agents, Q1 gate)
                     |          \
                     |           \  both edit consent.py: one file, one pass
                     |            \
                     v             v
        [BLOCK 4  is_active kill-switch]   [BLOCK 6  Session revocation]
          (P1, HIGH, all agents, Q3/Q4)     (P1, HIGH, all agents, Q7/Q8)
                     |                            ^
                     |  no code edge; a RECORD   |  soft: BLOCK 6's decision
                     |  edge - phase 15's DENY    |  record must respect
                     |  vocabulary is affected    |  BLOCK 4's outcome
                     v                            |
              (phase 15 AUTHZ-001)  <------------+

        [BLOCK 5  Credential recovery + doc claims]  (P2, MEDIUM, Q5 gate)
        [BLOCK 7  Client IP / trusted proxy]        (P1, HIGH, all agents, Q2/Q9)
```

| Edge | Kind | Why the edge exists |
|---|---|---|
| **1 → 2** | **Hard** | `04-VAL-004`, verbatim: *"The admin-form fix must land with or before the validator work."* Without BLOCK 1, a validator in `base.py` still does not stop a moderator from setting a weak password through the auto-built change form, and the block would ship a policy with a bypass. |
| **2 → 5** | **Hard** | A credential-recovery path is governed by the policy BLOCK 2 configures. Building a reset flow first and a policy second means the flow has no defined password requirements. |
| **3 → 4** | **Hard (shared file)** | Both edit `login_status`. Sequential so the file is edited by one change at a time and neither implementor has to re-read the other's change. |
| **3 → 6** | **Hard (shared file)** | Both edit `consent.py`. Same reason. |
| **4 → 6** | **Soft** | Not a code dependency. BLOCK 6's decision record must state BLOCK 4's `is_active` outcome so that phase 15 receives one coherent account of the field's status, and so BLOCK 6 does not accidentally reintroduce a term BLOCK 4 removed. |
| **2 → 9** | **Hard** | BLOCK 9's policy block annotates the `AUTH_PASSWORD_VALIDATORS` setting BLOCK 2 adds. Annotating a setting that does not exist yet, or annotating it and then having BLOCK 2 rewrite it, is pure churn. |
| **8 → 9** | **Hard** | Same: BLOCK 9 annotates the `SESSION_*` block that BLOCK 8 may change. |
| **1 → 9** | **Implicit** | BLOCK 9 also corrects stale comments in `apps/users/admin.py`, which BLOCK 1 rewrites. Clean comments must be written against the final code, not the pre-BLOCK-1 code. |

**Node-level dependency notes**

- **BLOCK 1 has no inbound edge** - it is the entry point. Nothing in the phase
  depends on it *for correctness* except BLOCK 2 (`04-VAL-004`) and BLOCK 9 (comment
  hygiene), but phase 15's `AUTHZ-003` and phase 06's `PII-107` both cite it as a hard
  prerequisite externally.
- **BLOCK 7 has no edges at all.** It shares `config/settings/base.py` with BLOCKS 2, 8
  and 9, but it is scheduled after BLOCK 2 and before BLOCK 8, so the shared file is
  never edited concurrently by two of this phase's own blocks. Its dependency is on an
  **Auditor pre-step**, not on another block.
- **BLOCK 5 has no inbound edge from any HIGH block** other than BLOCK 2, because it is
  P2 and can be scheduled after the HIGH work without risk.

### 4.3 Where there is deliberately no edge, and why

| Pair | Why no edge |
|---|---|
| BLOCK 3 ↔ BLOCK 7 | Different subsystems (`login_token` vs rate-limit key derivation). BLOCK 7's Q1-style uncertainty is about the proxy topology, not the login handshake. |
| BLOCK 4 ↔ BLOCK 7 | Unrelated. BLOCK 4 could run first or last with no interaction. |
| BLOCK 5 ↔ BLOCK 7/8 | Unrelated. BLOCK 5 is one comment plus possibly a doc; BLOCK 7 and BLOCK 8 are settings and infrastructure. |
| BLOCK 6 ↔ BLOCK 7/8 | Unrelated. The soft 4 → 6 edge above is the only relationship. |

**If any of these "no edge" pairs turn out to conflict** - because a parallel phase
landed a change in the same file - the implementor must stop and report, not merge the
concerns.

### 4.4 The four green tests this phase will change

Project rule 2 - *production code is king* - governs all four. **Each test change lands
in the same commit as the production change that invalidates it**, and each commit body
states which changed and why.

| # | Test | Currently asserts | Changed by | What changes, and why |
|---|---|---|---|---|
| **1** | The **seven** direct-row tests: five in `apps/users/tests/test_login.py::TestLoginStatus` plus the shared `_claim_login` helper, and `apps/users/tests/test_consent.py::TestLoginTokens::test_login_consume_no_raw_telegram_id` | They construct a `LoginToken` row directly with a fresh `Client()` and assert the endpoint's outcome. `_claim_login` additionally asserts `200`. | **BLOCK 3** (`04-AUT-001`) | Under **any** browser-binding design, a token minted outside `login_issue` has no binding, so the endpoint correctly answers `410`. The tests are asserting a condition the security fix makes impossible. **They are rewritten to obtain the token through the issuing path**, or to set the binding explicitly. The production code is not weakened to keep them passing. *(The code context's claim that the session-store option needs no change here is wrong - see 0.5.)* |
| **2** | `apps/users/tests/test_login_token.py::TestIssueToken::test_two_issues_differ` | Two `issue_token()` calls yield different raw tokens - true today, and **still true after `AUT-007`**, because the remedy is that a *prior outstanding* token is invalidated, not that a fresh token cannot be minted. The test conflicts because it implicitly assumes multiple live tokens per browser are normal. | **BLOCK 3** (`04-AUT-007`) | The two-issue assertion is kept. What changes is what the test says about the **first** token: under `AUT-007` it is no longer claimable. The test is extended, not weakened - it becomes the direct test of the invalidation behaviour. |
| **3** | `apps/core/tests/test_contact_rate_limit.py::test_x_forwarded_for_takes_precedence` | `X-Forwarded-For` (nginx) is preferred over `REMOTE_ADDR`, with the two set to different values. | **BLOCK 7** (`04-AUT-003`) | **This test asserts the defect.** Preferring a client-supplied header unconditionally is precisely the bug. Under a trust model, the header is honoured **only when the immediate peer is a configured proxy**; the test becomes conditional on that, and the untrusted-peer case (header ignored) becomes a new, mandatory assertion. |
| **4** | `apps/users/tests/test_login_token.py::TestLoginHandshakeOwnership::test_consent_view_has_no_token_logic` | `LoginToken` and `hashlib` must not appear in `apps/users/views/consent.py`; the view owns no token logic. | **BLOCK 3** - must **not** change | This is a **structural guard**, not a stale assertion. It exists to keep the handshake in one module. BLOCK 3 must satisfy it: the view passes an opaque binding value and keeps no token logic. **If this test has to be modified, BLOCK 3 is wrong.** |

**A fifth test is a tripwire, not a casualty:**

- `apps/moderation/tests/...::test_bulk_ban_users_not_locked` asserts that
  `bulk_ban_users` issues **no** `select_for_update`. It belongs to phase 03's
  transaction-boundary work. **BLOCK 6 must not add row locks to close an
  authorization finding.** If closing `AUT-002` seems to require them, that is the
  signal that `AUT-002` is not closable at the service layer - which is exactly what
  Q7 concludes.

---

## 5. Cross-phase coordination

Phases 01 and 02 are executed or in flight. Phases 03 and 05-15 are being planned in
parallel by other Planner agents. **This section states boundaries; it does not attempt
coordination with them.** Where two phases touch one artefact, the ownership rule below
is the tie-breaker.

### 5.1 What phase 04 already owns and must not re-ship

| Already landed (phase 01) | Where it lives | What phase 04 must **not** do |
|---|---|---|
| The `LoginToken` lifecycle extracted into one service | `apps/users/services/login_token.py` - `issue_token`, `claim_token`, `consume_token`, `ConsumeOutcome`, `ConsumeResult`, `IssuedToken` | Do not re-create a token helper in a view, a middleware or an admin. `AUT-001` and `AUT-007` land **inside `issue_token`**, which the module docstring already reserves for them. |
| The `ENT-005` architectural boundary, documented | `docs/99-agent/architecture.md` → "Login Token Lifecycle Seam (ENT-005)" | Do not re-document the seam, and do not move a lifecycle operation out of the module. |
| Phase 01's decision that the phase-04 report's `consent.py` citations are stale | this plan, 0.2 item 1 | Do not chase the report's line citations. Work from the module. |
| `server_timing` instrumentation on the login views | `apps/core/middleware/server_timing.py` | Not a phase-04 concern. Do not remove it while editing `login_issue` / `login_status`. |

### 5.2 What phase 04 must not do for other phases' sake

1. **Must not build the per-request account-state gate.** It is phase 15's
   `15-AUTHZ-001`, and `04-VAL-001`'s rule is that both phases must not file the same
   middleware. Phase 04's `AUT-002` half is the *revocation at the point of change*.
2. **Must not change `login_issue`'s route or method.** `15-AUTHZ-004` owns the
   `GET`-writes-without-CSRF finding and it includes a product decision about deep-link
   UX. Adding `@require_POST` from this phase would pre-empt that decision and
   invalidate `apps/core/tests/test_login_issue_template.py` and
   `apps/users/tests/test_login_issue_template.py`, both of which phase 15's own rollout
   table names.
3. **Must not fix `can_publish_ad` or the queryset-level visibility predicate.** Both
   belong to phase 15 `AUTHZ-005` and to phase 06 `VAL-003` / `PII-104`, and phase 15's
   rollout explicitly forbids shipping `can_publish_ad` and a new verdict side by side -
   that reconciliation is theirs, in their commit, with their test retargeting.
4. **Must not touch `AccountStateMiddleware` in the bot** except under BLOCK 4 option A
   with a bot-side test. Phase 15 is refactoring that middleware to call a shared
   predicate; two changes to one function from two phases is a merge conflict with a
   security meaning.
5. **Must not edit `docs/01-spec/technical-specification.md` casually.** Phase 06
   `PII-113` is editing it. BLOCK 8 option (c) and any BLOCK 6 documentation of the
   decline path touch it - coordinate first (§5.5).
6. **Must not fix `04-VAL-005`'s `spec-index.md` half.** Phase 06 declared `PII-113` the
   finding of record. Phase 04's `04-VAL-005` becomes a cross-reference, and the
   tracker - not this plan - closes it.

### 5.3 The authorization overlap with phase 15 - the highest-risk boundary in the plan

Three overlaps, each with a different resolution. **The single rule underneath all
three: phase 04 ships session-layer work; phase 15 ships the gate.**

| Overlap | Phase 04 finding | Phase 15 finding | Resolution | Enforcement |
|---|---|---|---|---|
| **AUT-002 / AUTHZ-001** | The three revocation paths that do not flush a session; `can_login` is a one-shot gate | The web tier has **no per-request gate at all** - reproduced end to end (ban, session key unchanged, dashboard 200) | **Split, not merged.** Phase 15's validator is explicit: *"They are one defect with one remedy. A tracker must not count them twice."* Phase 15 owns the per-request gate; phase 04 owns the *eager* revocation where the view already has the identity. | **Hard rule: both phases must not file the same middleware.** BLOCK 6 may add `logout()` calls. It may not add middleware, a decorator, or a shared predicate. If a reviewer sees a second gate appear, BLOCK 6 is wrong. |
| **AUT-004 / AUTHZ-001** | `is_active=False` is not enforced | AUTHZ-001's recommendation **deliberately carves `is_active` OUT of its DENY set**, and its own matrix records that `is_active=False` already redirects on the web | **The two cannot both be right, and this plan does not silently pick one.** BLOCK 4 resolves only the *field's status* and writes a decision record. The DENY-set question belongs to phase 15, whose `AUTHZ-001` owns the predicate's vocabulary. | BLOCK 4 must state, in writing, that it contradicts or supports phase 15's carve-out, with the evidence. Silence is not an option - a silent ship here is how a security control gets added to a gate in one phase and removed in the next. |
| **AUT-005 / AUTHZ-003** | `UserAdmin`'s auto-built form exposes a plaintext password write, `is_superuser` and `user_permissions` | The `ADMIN` role has three divergent implementations; the validator cites `04-AUT-005` as a **hard prerequisite** and says AUTHZ-003 must not be closed without it | **Sequenced, both owned by phase 04.** Phase 06's `PII-103` is merged into the same fix, so this is the one field contract in the project. | BLOCK 1 must not be deferred behind AUTHZ-003. Phase 15 audits the *permission predicate* only and must cite `04-AUT-005` rather than re-file the field set. Phase 15's own `VAL-005` explicitly rejects the blanket 17-class mixin as a privilege expansion; nothing in this plan may reintroduce one. |

**Also cross-cutting:** the shared `request.user` surface. `MIDDLEWARE` has 14 entries
and no account-state gate; the authenticated tier is currently gated by per-view
decorators (`@login_required`, `@seller_required`, `@staff_required`) that test
*authentication*, not *account state*. Phase 15 will add a gate after
`AuthenticationMiddleware`. **Phase 04 does not reorder `MIDDLEWARE` and does not add to
it.** Any change to `MIDDLEWARE` in this plan is a defect.

### 5.4 The PII / consent overlap with phase 06

| Shared thing | Phase 04's position | Phase 06's position | Rule |
|---|---|---|---|
| **`UserAdmin` field contract** | `04-AUT-005` + `04-VAL-004` (credential half) - **owner** | `PII-103` (identity + consent half) - **merged into `04-AUT-005`** by phase 06's own validator: *"One `fieldsets` declaration. Two patches to the same class would be a partial fix at best."* | **One declaration, one commit, phase 04 owns it.** Phase 06 must not patch `UserAdmin` again. Phase 06's `PII-107` is sequenced to depend on it. |
| **`04-VAL-005` doc conflict** | `04-VAL-005` is the finding of record for the *password-reset claim* half only (BLOCK 5) | `PII-113` is the finding of record for the DECLINE-semantics conflict; `04-VAL-005` is a **cross-reference** there | Phase 04 does not edit `spec-index.md` or `technical-specification.md` for this. |
| **`PII-105` (DECLINE reversibility) → BLOCK 6** | BLOCK 6's decline-path `logout()` (Q8) depends on this decision | `PII-105` option (a) would make DECLINE reversible and regain web login | **Hard gate.** BLOCK 6 must not ship the decline-path logout before `PII-105` is decided. Neither report records this dependency. |
| **`ConsentRecord` and the admin withdraw action** | `UserAdmin.withdraw_consent_action` is BLOCK 6's surface, and BLOCK 6 is expected to record it as unreachable-at-view-layer | `PII-107` (move the `ConsentRecord` write into `withdraw_consent()`) is sequenced **with** the PII-103/04-AUT-005 fix, i.e. after BLOCK 1 | BLOCK 1 must not touch `withdraw_consent_action`; BLOCK 6 must not change the `ConsentRecord` write. |
| **`mask_telegram_id`** | Not a phase-04 surface, but BLOCK 9's comment pass touches files that use it | `PII-112` changes its construction and **will change every derived value**; `test_sanitize.py` pins `length == 13` and will fail | Phase 04's tests must not assert on a mask's length or shape. |
| **Session-key retention** | Not a phase-04 surface | `PII-116` absorbs the `ConsentRecord` `session_key` TTL half | Noted so BLOCK 3's option B (a session-stored token hash) is not confused with `ConsentRecord.session_key`. They are different things. |

### 5.5 The db-concurrency overlap with phase 03

Phase 03 owns transaction boundaries. Phase 04 touches three of them and must respect,
not redo, them.

| Phase 03 item | Where it lives | Phase 04's obligation |
|---|---|---|
| **DB-002** - the login handshake's transaction boundary | `login.handle_login_orm` opens one outer `transaction.atomic()`; `claim_token` and `consume_token` deliberately open **none** - the module docstring states the caller owns the transaction and the service owns the predicate | **Do not add, move or nest an `atomic()` in `login_token.py`.** BLOCK 3 changes the *arguments* to `issue_token` / `consume_token`, not their transaction behaviour. `claim_token`'s `now` parameter stays required and stays computed by the caller before the transaction opens - changing that moves the timestamp inside the transaction, which the docstring explicitly forbids. |
| **DB-004** - `record_event` / `AnalyticsEvent` transaction handling | The consent views call `record_consent_action(...)` | BLOCK 6's `consent_decline` change must not alter when `record_consent_action` runs relative to `logout()`. The existing order (service first, cookies, then the audit write) is the pattern; keep it. |
| **DB-010** - the moderation action boundaries | `ban_user_for_ad` takes `User.objects.select_for_update()`; `bulk_ban_users` deliberately does **not** | **BLOCK 6 must not add row locks to `bulk_ban_users`.** `test_bulk_ban_users_not_locked` is the tripwire. If closing `AUT-002` appears to require locks there, that is evidence the service layer is the wrong place - which is Q7's conclusion. |
| **Migrations run exactly once, before both processes start** | the deploy entrypoint chain | BLOCK 3's option A migration is a normal Django migration and is covered by this. No migration may be authored that must run in only one process. |
| **Advisory locks** | `cleanup_login_tokens` (hourly) is the janitor for `login_tokens`; phase 01 added a durable marker for the scheduler | BLOCK 3's option A adds row growth; `cleanup_login_tokens` already bounds it. **This is the reason option A has a janitor and option B does not** (0.2 item 4) - and the reason BLOCK 3 must not add a fifth deleter or a fourth scheduler entry. |

**Shared settings file:** `config/settings/base.py` is edited by BLOCKS 2, 7, 8 and 9 -
four of this phase's own blocks, sequenced so only one touches it at a time - and by
other phases. Stage only the intended files; never revert another agent's concurrent
change to that file (§1.3).

### 5.6 Shared-artefact reservations

| Artefact | Reserved by | Rule |
|---|---|---|
| `src/backend/config/settings/base.py` | phase 02 (`CFG-*`), phase 04 (BLOCKS 2, 7, 8, 9), others | One phase's blocks at a time. Append-only where possible; never reorder a setting another phase annotated. |
| `src/backend/apps/users/admin.py` | phase 04 (BLOCK 1, BLOCK 9), phase 15 (`AUTHZ-003` cites it) | Phase 04 owns the **field contract**. Phase 15 audits the **permission predicate** and must cite `04-AUT-005`. |
| `src/backend/apps/users/models.py` + `apps/users/migrations/` | phase 04 (BLOCK 3 option A, BLOCK 4 option B), phase 06 (erasure columns), phase 15 (role fields) | Migration numbers are sequential in `apps/users/migrations/`. **Never renumber or edit an existing migration.** If another phase has landed a migration, this phase's next number is theirs + 1 - re-check, do not assume `0003_`. |
| `src/backend/apps/users/services/login_token.py` | phase 01 (owner), phase 04 (BLOCK 3) | `AUT-007` and `AUT-001` land here and nowhere else. The `RETURNING` list and the `AUT-007` boundary docstring are load-bearing for phase 01's architecture decision. |
| `src/backend/apps/moderation/admin_actions.py` | phase 03 (lock behaviour), phase 05 (ad lifecycle), phase 04 (BLOCK 9 comments only) | Phase 04 touches **comments only**. No behaviour change, no locks. |
| `docker/nginx/nginx.conf` | phase 04 (BLOCK 7), possibly phase 12 (production ops) | If phase 12 has reserved it, BLOCK 7's nginx half is deferred and only the Python half ships. Record which. |
| `docs/01-spec/technical-specification.md` | phase 06 (`PII-113`) | Phase 04 edits only under BLOCK 8 option (c), and only after checking for a concurrent edit. |
| `docs/99-agent/architecture.md` | phase 01 (the `ENT-005` section), phase 04 (BLOCK 3's `AUT-007` paragraph) | Update the `AUT-007` boundary text **once**, when BLOCK 3 lands. |
| `docs/02-database/db-schema.md` | phase 04 (BLOCK 3 option A), phase 06 (erasure columns) | Update the `login_tokens` table only if BLOCK 3 takes option A. |

---

## 6. Out of scope for this plan

### 6.1 De-scoped by ownership (routed, not dropped)

| Item | Why out of scope here | Where it lives |
|---|---|---|
| The per-request account-state gate / middleware | `04-VAL-001`'s rule: both phases must not file the same middleware | Phase 15, `15-AUTHZ-001` |
| `login_issue` behind `@require_POST` + CSRF; the `GET`-writes defect | The recommendation includes a product decision about deep-link UX, and phase 15 names both `test_login_issue_template.py` files in its own rollout row | Phase 15, `15-AUTHZ-004` |
| `is_active` in the DENY set | Phase 15 owns the predicate's vocabulary and deliberately carves it out | Phase 15, `15-AUTHZ-001` |
| Reconciling `can_publish_ad` with a new shared verdict | Phase 15's rollout forbids shipping both side by side; the reconciliation belongs in their commit with their test retargeting | Phase 15, `15-AUTHZ-005` |
| The moderator role contract and `AdminSite.has_permission` | Phase 15, `AUTHZ-003` - and its `VAL-005` rejects the blanket mixin as a privilege expansion | Phase 15, `15-AUTHZ-003` |
| `04-VAL-005`'s `spec-index.md` DECLINE-semantics conflict | Phase 06 declared `PII-113` the finding of record and `04-VAL-005` a cross-reference | Phase 06, `PII-113` |
| The `ConsentRecord` write moving into `withdraw_consent()` | Phase 06, `PII-107`; sequenced after `04-AUT-005` | Phase 06, `PII-107` |
| `mask_telegram_id()` construction change | Phase 06, `PII-112`; it changes every derived value | Phase 06, `PII-112` |
| Any `is_deleted` / `is_banned` visibility predicate in search or listings | Explicitly *not* re-filed by phase 15; owned by phases 06 and 08 | Phases 06 / 08 |

### 6.2 De-scoped by design (deliberately not done here)

1. **No `SESSION_ENGINE` change, no `MEDIA_ROOT` switch, no cookie-storage migration.**
   Tempting under BLOCK 3 option B and BLOCK 8 option (b); explicitly out of bounds.
2. **No `clearsessions` / `clear_cookies` management command, and no new scheduler
   entry.** BLOCK 3 may *note* in `login_token.py`'s docstring that `django_session`
   has no janitor - a fact with no cheap fix in this phase. Adding a janitor is a
   different finding and belongs to whichever phase owns session storage.
3. **No `django_session` global scan, and no `session_data` `LIKE`/decode sweep** for
   `AUT-002`. The report already rejected it as fragile, unverifiable and unshippable.
   BLOCK 6 records the rejection with the reason rather than re-litigating it.
4. **No row locks added to `bulk_ban_users`.** Phase 03 owns that boundary and
   `test_bulk_ban_users_not_locked` is the guard.
5. **No session invalidation for the three admin/moderator ban paths.** See Q7 - the view
   layer structurally cannot reach another identity's session.
6. **No PII-DTO, no service-layer Pydantic, no new `apps/audit` module.** The erasure
   registry is phase 06's Required Fix 1.
7. **No rewrite of the technical specification.** Phase 06 is editing it; the only
   phase-04 edit permitted is BLOCK 8 option (c)'s session-lifetime sentence, and only
   with coordination.
8. **No seed-data, no fixture reshaping, no conftest redesign.** Unless BLOCK 4 option B
   requires it, in which case it is a consequence of a recorded decision, not a
   preference.
9. **No `technical-specification.md` band for `is_active`** - see §6.1.
10. **No severity re-banding.** This plan corrects counts and citations (0.4) and adds
    one new input defect (`04-VAL-006`). It does not change any finding's band. If a
    pre-step's derivation invalidates a premise - as BLOCK 4's Q4 may - the
    **re-banding belongs to whoever re-runs the Validator**, not to the Implementor.

### 6.3 Explicitly forbidden while implementing

- Editing **any** file under `.ai/audit/` - including the validated reports and
  `04-VAL-005`'s two files. They are evidence, not work items.
- Adding middleware, or reordering `MIDDLEWARE`.
- Changing the route or HTTP method of `/login/issue/` or `/login/status/`.
- Adding a fourth deleter for `LoginToken` rows, or a fourth `HOURLY_COMMANDS` entry.
- Adding a fifth `send()` argument in a way that breaks the 12 bot call sites of
  `handle_login_orm`, or the `now`-parameter contract of `claim_token`.
- Introducing `print()`, a bare `except`, a magic literal where a `StrEnum` or a
  `Final` constant belongs, or a new dependency.
- Reverting, stashing or `git checkout`ing a file another agent changed.

---

## 7. Per-block risk register

Risk bands: **H** = can cause a security regression, data loss or an outage ·
**M** = can cause a functional regression or a broken deployment · **L** = cosmetic or
documentation.

| Block | Implementation | Rollout / compatibility | Regression | Security | Migration / data | **Overall** |
|---|---|---|---|---|---|---|
| **1** - `UserAdmin` field contract | **M** - the field partition is a design choice; the wrong one breaks operator workflows | **L** - no schema, no deploy step | **M** - any test asserting the old field set fails | **H** - the fix *is* the security control; an incomplete field set leaves self-escalation open | **L** - none | **H** |
| **2** - Password validators | **L** - two settings, one command | **M** - **operator lockout is the real risk**: the documented bootstrap command in `docs/ops/` may start failing | **L** - no existing test covers the command's validator | **M** - a policy with a bypass is worse than none | **L** - none | **M** |
| **3** - Token binding + invalidation | **H** - the largest diff; a **new column without a `RETURNING` edit fails at runtime on the bot path only** | **H** - a failed migration leaves a half-bound token; option B changes `/login/issue/` from cookie-less to session-writing, with **no `clearsessions` janitor anywhere** | **H** - 7 direct-row tests + `test_two_issues_differ` must change; a prefetch-hostile binding locks out real users | **H** - over-loose leaves `AUT-001` open with green tests; over-strict breaks login | **M** - option A only; shared artefact (§5.6) | **H** |
| **4** - `is_active` | **M** - three coherent options, none obviously right | **M** - option A's enforcement point is phase 15's, so shipping it here creates a second gate | **M** - option B breaks every `is_active` fixture across **both** conftests including the bot's | **H** - this field is the kill-switch; choosing wrong removes a control that exists | **M** - option B only; `RemoveField` on a contended table | **H** |
| **5** - Recovery + doc claim | **M** - option (a) is a genuine feature, not a fix | **M** - option (a) adds a user-facing surface and makes `EMAIL_HOST` load-bearing for account recovery | **L** | **M** - the real risk is deleting a real control while correcting a false claim | **L** - none | **M** |
| **6** - Session revocation | **M** - the view-layer solution exists for exactly one of four paths | **M** - `logout()` flushes the session and rotates CSRF; an open HTMX fragment in the same page 400s | **L** | **H** - and the boundary risk is higher: **shipping a second gate** is the named failure mode | **L** - none | **H** |
| **7** - Client IP / trusted proxy | **M** - a trust model is easy to get subtly wrong | **H** - an invalid `nginx.conf` takes the site down at **reload**, and no Python test can see it | **M** - `test_x_forwarded_for_takes_precedence` asserts the defect and must change | **H** - but note the direction: the dominant failure is **self-inflicted DoS** (one bucket for every client), not bypass | **L** - none | **H** |
| **8** - Session lifetime | **L** | **M** - option (b) changes session lifetime globally, including phase 06's fixtures | **M** - every `force_login`-based test is in scope under (b) | **L** - and the risk is misreading (b) as a security win when it is a behaviour change | **L** | **M** |
| **9** - Annotation hygiene | **L** | **L** | **L** - the fast gate is the whole guard | **L** | **L** | **L** |

**Cross-cutting risks that apply to the plan as a whole**

| Risk | Where it bites | Mitigation |
|---|---|---|
| **Stale-citation drift.** The report is anchored at `33345c9`; the tree is at `4fd8bd0`; two `consent.py` citations are already wrong. | Every block that cites the report | Target **symbols**, never line numbers. Where a line number appears in this plan it is a locator, not a target. |
| **Open questions implemented "in flight".** Nine questions, seven blocks, and an implementor under time pressure. | BLOCKS 3, 4, 5, 6, 7, 8 | A block with an open gate **does not start**. Record the decision, then implement. This is stated in each block, not just here. |
| **Two phases, one defect, two fixes.** AUT-002/AUTHZ-001 and AUT-005/AUTHZ-003. | BLOCKS 1, 6 | §5.3. Phase 04 ships session-layer work and a field contract; phase 15 ships the gate and the role contract. A second middleware is a defect. |
| **Test-ownership collisions.** Nine tests across six files are owned by other phases' findings. | BLOCKS 3, 7 | §4.4. Each change lands in the same commit as the production change that caused it. |
| **Lost update on shared artefacts.** `base.py`, `admin.py`, `users/models.py`, `migrations/`, `nginx.conf`, `technical-specification.md`. | BLOCKS 1, 2, 3, 4, 7, 8, 9 | §5.6. Stage specific files; never revert another's change; re-check the next migration number rather than assuming it. |
| **Session/cookie behaviour changes stacking.** BLOCK 3 (option B) and BLOCK 8 (option b) both change session lifetime or persistence, and BLOCK 6's `logout()` rotates CSRF. | BLOCKS 3, 6, 8 | They are separate commits in a fixed order (3 → ... → 6 → 8), so the interaction is observable and attributable. **Never merge them.** |
| **A partial block silently counted as complete.** BLOCK 7 can legitimately ship half. | BLOCK 7 | Partial shipping is explicitly supported *and must be recorded as partial* - the deferred half is a named follow-up, not a silent omission. |

---

## 8. Definition of done for the whole plan

### 8.1 Tracker and process deliverables (no code)

1. **Every finding key is phase-qualified** (`04-AUT-002`, never `AUT-002`). Phase 15's
   validator independently recorded the same requirement (`VAL-004`), and phase 06's
   too - three phases have now filed it. This is `04-VAL-002`'s tracker half.
2. **The reconciliation counts are corrected in the tracker**: `AUT-002` is **4 of 5**
   rows (not 3 of 4); `VAL-003`'s direct-row test count is **7** (not 6).
3. **`04-VAL-006` is recorded** (this plan, 0.4 S-3): the report's post-validation
   severity tally reads 8 items for 7 findings. The per-finding column governs:
   **3 HIGH, 2 MEDIUM, 2 LOW**. No band changes.
4. **Each of the seven open questions is closed in writing** with the decision, the
   reason, and who made it. An unresolved Q is a **blocker on its block**, not a
   deferral.
5. **Each cross-phase boundary in §5 is acknowledged by the owning phase** before
   either side's block ships. Not negotiated here - just not violated.
6. **This plan file is left uncommitted for review** and is not edited by any Implementor.

### 8.2 Per-block exit conditions (all must hold)

| # | Condition |
|---|---|
| 1 | The block's decision gate was **closed and recorded before** the first code change. |
| 2 | `.\Makefile.ps1 test` (or the equivalent `test`-service fast gate) is green. |
| 3 | `uv run ruff check <changed paths>` clean. |
| 4 | `uv run basedpyright <changed paths>` clean, with no new suppression. |
| 5 | `makemigrations --check` reports no pending model change - **unless** the block is BLOCK 3 option A or BLOCK 4 option B, in which case the migration is present, reviewed, and run exactly once before both processes start. |
| 6 | Every test in the block's "Tests required" list exists, asserts **behaviour and component interaction**, and passes. |
| 7 | Every test this block was expected to change (§4.4) is changed **in the same commit**, and the commit body says which changed and why. |
| 8 | No structural guard was weakened. `TestLoginHandshakeOwnership` and `test_bulk_ban_users_not_locked` pass **unchanged**, or the block is wrong. |
| 9 | Any new user-visible string is wrapped in `gettext`/`{% trans %}` with non-empty `msgstr` for `ru` and `bs`; `test_i18n_completeness.py` passes. |
| 10 | Every new fixed value is a `StrEnum` member or a `Final` constant, not a literal. |
| 11 | No `print()`. New log lines use `logger` and a stable reason code. |
| 12 | Documentation updated where the block changed a contract: `docs/02-database/db-schema.md` (option A), `docs/99-agent/architecture.md` (BLOCK 3's `AUT-007` boundary, once), `docs/ops/docker-deployment.md` (BLOCKS 5, 7). |
| 13 | The commit is **one block**, staged with explicit `git add <files>`, message `"{type}({scope}): {description}"`. |
| 14 | `git status` shows no modification to any file outside the block's declared file surface, other than changes made by *other* agents. |
| 15 | No `.ai/audit/` file was modified. No git history was rewritten. |

### 8.3 Phase-level exit conditions

| # | Condition |
|---|---|
| 1 | All nine blocks committed, each green, each with its exit conditions met. |
| 2 | **Exactly one** account-state enforcement mechanism exists in the merged tree. If a gate exists, it is phase 15's. This is verified against the **merged** state, not against either phase's branch. |
| 3 | Exactly one `fieldsets`-style declaration exists on `UserAdmin`. |
| 4 | Exactly one copy of the client-IP logic exists. |
| 5 | `LoginToken` has exactly two deleters - `withdraw_consent` and `cleanup_login_tokens` - and the scheduler still has exactly the entry count it had before. |
| 6 | `claim_token`'s `RETURNING` list matches `LoginToken`'s field set **exactly** (assert it with a test, not with a comment - this is the trap that turns a migration into a bot-path `TypeError`). |
| 7 | Full fast gate green on the merged tree, including both `conftest.py` suites (backend and bot). |
| 8 | Every open question has a recorded answer, and every **deferred** half (BLOCK 7's nginx half, BLOCK 3's option A if A' was chosen, BLOCK 4's option if it was (c)) is recorded as an explicit follow-up, not as a closed finding. |
| 9 | The tracker shows `04-AUT-001`…`04-AUT-007` closed, with `04-VAL-001`…`04-VAL-005` and the new `04-VAL-006` dispositioned per §2 - **and the three cross-phase IDs (`15-AUTHZ-001`, `15-AUTHZ-003`, `PII-103`) still open on the phase-15 and phase-06 trackers**, because phase 04 closing its half does not close theirs. |

### 8.4 What "done" explicitly is not

- **Not** "the admin can no longer be self-escalated." That is BLOCK 1 plus phase 15's
  role work; the admin surface is not closed by this plan.
- **Not** "a banned user's session is dead." That is phase 15's per-request gate. This
  plan closes the decline path (if Q8 permits) and records the rest.
- **Not** "login is bound to a browser and the CSRF gap is fixed." The binding is
  BLOCK 3; the CSRF gap is phase 15's `15-AUTHZ-004`.
- **Not** "`is_active` works." BLOCK 4 resolves the field's status. Whether it is
  enforced inside the gate is phase 15's DENY-set decision.
- **Not** "the rate limiter is safe." BLOCK 7 makes the key unforgeable. Whether the
  nginx header is overwritten depends on Q9 and may legitimately remain open.

This plan is a **phase-04 remediation**. It is complete when phase 04's seven findings
and five VAL findings have the dispositions in §2, every question is answered, and no
boundary in §5 has been crossed - not when the platform's authentication story is
finished. It is not.



