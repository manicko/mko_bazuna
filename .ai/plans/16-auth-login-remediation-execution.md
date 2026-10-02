title: Execution Plan — Phase 04 (Authentication & Login Token Security)
slug: 16-auth-login-remediation-execution
phase: 04
status: decomposition only — no implementation code in this document
created: 2026-09-30
source_plan: .ai/plans/04-auth-login-remediation.md
source_report: C:/Users/Om/.local/share/kilo/tool-output/tool_0f459358f001EIIcec4ipUxVO3
verified_head: f93e7fb
source_plan_anchor: 4fd8bd0
language: en
block_count: 11
---

# Execution Plan — Phase 04 · Authentication & Login Token Security

This document decomposes `.ai/plans/04-auth-login-remediation.md` into executable
blocks. It **plans; it does not implement.** Section names in the source plan are
cited as `source plan §BLOCK N` and its open questions as `Q1`…`Q9`; the verified
code context is cited as `C-*` (claims), `X-*` (plan-vs-tree contradictions),
`D-*` (details), `U-*` (open unknowns). Gates here are `G-*`.

> **A block with an open gate does not start.** See §H.

## Contents

- **§A** Provenance, drift control, re-cut of the decomposition, CORRECTIONS table
- **§B** Execution blocks `B-01` … `B-11`
- **§C** Dependency graph, serial order, shared-artefact reservations
- **§D** Cross-phase boundaries
- **§E** Test-ownership ledger
- **§F** Risks and mitigations (plan-wide)
- **§G** Definition of done
- **§H** Open questions register
- **§I** Implementation path alternatives (undecided)

## §A · Provenance and drift control

### A.1 Sources

| Item | Value |
|---|---|
| Source plan | `.ai/plans/04-auth-login-remediation.md` (2131 lines, 9 blocks, `04-AUT-001`…`04-AUT-007` + 5 VAL findings, Q1–Q9) |
| Verified code context | Auditor's Phase-1 report, 687 lines, verified at `f93e7fb` |
| Current HEAD | `f93e7fb` |
| Source plan's anchor | `4fd8bd0` — **32 commits of drift**; every drift commit is in §0 of the code context |
| Source plan's audit file | `.ai/audit/04-auth-login/findings.md` — **deleted from the working tree** (tracked deletion). Evidence only. Never restored, never edited. |
| This document | `.ai/plans/16-auth-login-remediation-execution.md` |

### A.2 Uncommitted work owned by another agent

`git status --porcelain` at `f93e7fb` shows these modifications, all belonging to
another agent's in-flight phase-13 work:

| Path | Owner |
|---|---|
| `.ai/plans/13-db-concurrency-remediation-execution.md` | phase 13 |
| `src/backend/apps/ads/services/copy_service.py` | phase 13 |
| `src/backend/apps/ads/tests/test_copy_ad.py` | phase 13 |
| `src/backend/locale/{bs,en,ru}/LC_MESSAGES/django.po` | phase 13 (i18n) |
| `src/telegram_bot/handlers/ad_copy.py` | phase 13 |
| `src/telegram_bot/tests/test_ad_copy.py` | phase 13 |

Plus untracked `.ai/tmp/` and `staticfiles/`, and 20 tracked deletions of
`.ai/audit/**` evidence files that predate this phase.

**The phase-04 file surface is currently clean of that work.** No file named in any
block below appears in that list.

**Rule: stage specific files, never revert another's change.** `git add <path>` per
file. Never `git add -A`, never `git add .`, never `git checkout`/`git restore`/
`git stash`/`git reset`. Never edit the three `.po` files — if i18n requires a
message change, the phase-13 owner must merge first; report and stop.

### A.3 Re-cut of the decomposition: 9 source blocks → 11 execution blocks

**The block set changed.** Two blocks were split (each split is a *hard* dependency
the source plan did not name), and five were re-scoped.

| Exec id | Title | Source block | Change |
|---|---|---|---|
| `B-01` | `UserAdmin` field contract | BLOCK 1 | re-scoped (target class does not exist) |
| `B-02` | Bootstrap password policy | BLOCK 2 | re-scoped (anchor no longer resolves; risk raised) |
| `B-03` | Login-token browser binding | BLOCK 3 (binding half) | **split** — one option is non-viable |
| `B-04` | Per-browser token invalidation | BLOCK 3 (invalidation half) | **split** — hard edge `B-03 → B-04` |
| `B-05` | `is_active` resolution | BLOCK 4 | re-scoped (premise refuted by C-22) |
| `B-06` | Credential recovery + false claim | BLOCK 5 | re-scoped (claim count was wrong) |
| `B-07` | Session revocation at state transitions | BLOCK 6 | re-scoped (3 of 5 paths reachable, not 2) |
| `B-08` | Shared client-IP helper + de-duplication | BLOCK 7 (Python half) | **split** — Q2 answered; own file surface |
| `B-09` | nginx `X-Forwarded-For` + rollout | BLOCK 7 (edge half) | **split** — three unresolved external gates |
| `B-10` | Session lifetime policy | BLOCK 8 | re-scoped (premise inverted by X-11) |
| `B-11` | Auth/session settings annotation | BLOCK 9 | **re-scoped down to one file** — the audit-id sweep is reserved by phase 03 |

**Why BLOCK 3 was split.** The source plan presented `04-AUT-001` (binding) and
`04-AUT-007` (invalidation) as one block. They are separable only if invalidation can
identify "the same browser" without a binding — and it cannot: at issue time the
`LoginToken` row has no `telegram_id` (the bot claims it later), so the only
available browser identifier **is** the binding value. Splitting them makes the hard
edge explicit, isolates a MEDIUM finding from a HIGH one, and lets `B-04`'s two
docstring rewrites land in the commit that invalidates them rather than in a
hygiene block that runs last.

**Why BLOCK 7 was split.** The source plan's own text says *"Partial shipping is
explicitly supported"* and orders de-duplication above the nginx change — which means
it already has two independent outcomes. A split makes the partial outcome a block
boundary instead of an outcome to be recorded inside one block. It also separates a
**Python-only** change (bounded, testable in the fast gate) from a **production proxy**
change (ungated locally, not verifiable by the deploy health check).

**Why BLOCK 9 shrank to one file.** Phase 03's plan §5.2 item 3 reserves
`EXT-`/`AUT-`/`SRH-` marker sweeps to itself and forbids phases 04–15 from starting
one. The sweep is removed. What survives is a settings-comment block and a decision
record.

### A.4 CORRECTIONS — every `X-*` and every `C-*` that changes a block's shape

**This is the section the implementors read first.**

| Id | Source plan / code-context claim | Tree truth (verified) | Disposition |
|---|---|---|---|
| `X-1` | Phase-04 file surface has no conflicts with phases 1/2 | Phase 02 owns `EMAIL_BACKEND` in `prod.py`, `ALLOWED_ENV_VARS` in `base.py`, `PASSWORD_HASHERS` in `test.py` | **Plan instruction corrected.** §D reserves those three surfaces. `B-06` touches `prod.py` comments only |
| `X-2` | Finding `04-AUT-005` half 1 is out of scope | It is **in** scope (B-01) | Carried into `B-01` |
| `X-3` | `bulk_ban_users` is reachable with a request | Correct — it is not reachable | Block option dropped (option (a) narrowed) |
| `X-4` | "blast radius: `login_status` + `ads/dashboard/*` + `seller_required`" | **1** call site. `apps/dashboard/*` does not exist; `seller_required` does not exist; `_check_user_state` is a **test-only** wrapper `__call__` does not use | Block re-scoped (`B-05` blast radius corrected) |
| `X-5` | Phase 04 and phase 01 do not overlap | **Half-true.** Correct on files; false on `AUT-00N` (`C-19`) | See `X-6`/`X-7` |
| `X-6` | 12 `AUT-00N` references across 6 files | **15 references across 9 files** (13 across 7 in `src/`) | Block re-scoped — `B-11` no longer sweeps them |
| `X-7` | `apps/moderation/admin_actions.py`, `apps/users/admin.py`, `apps/core/tests/test_admin_pii_containment.py` carry `AUT-00N` | **None of the three contains any `AUT-00N` reference** | Block re-scoped — removed from `B-11`'s surface |
| `X-8` | BLOCK 9's rationale: comments are stale because phase 01 moved the code | **False.** No `AUT-00N` reference points at code phase 01 moved. The only phase-04 ones (`login_token.py`, `architecture.md`) are the pair the plan says must **not** be touched | Block re-scoped |
| `X-9` | Add `TestAdminPiiContainment.test_change_form_omits_credential_and_consent_fields` | **No such class.** The module has five **module-level** functions: `_assert_no_raw_telegram_id`, `test_ads_user_link_hides_telegram_id`, `test_analytics_user_link_hides_telegram_id`, `test_moderation_log_user_link_hides_telegram_id`, `test_login_token_list_display_masks_telegram_id` | **Target corrected.** `B-01`'s new test is a module-level function |
| `X-10` | "document the trusted proxy in `docs/ops/docker-deployment.md` §reverse-proxy" | **No reverse-proxy section exists.** `## Nginx Configuration` covers rate limiting, security headers, media access control, media security | Plan instruction corrected — `B-08` may create the section or record that none exists |
| `X-11` | BLOCK 8 option (c): "correct the spec to say 14 days of inactivity" | `technical-specification.md` §H: *"persistent cookie, survives browser restart until explicit logout or **long idle**"* — **no number anywhere in `docs/`** (verified: zero hits for `14 day` / `14-day` / `двух недель` / `1209600`) | **Block option dropped.** Option (c) would document a behaviour the code does not have. Corrected option set in `B-10` |
| `X-12` | `test_admin_pii_containment` transitively protects admin surfaces from PII leakage | Correct, and **`B-01` adds a second layer** on the same surface — coherent, not conflicting | Carried into `B-01` |
| `X-13` | BLOCK 3 option A: "`login_issue` passes `request.session.session_key`" | That value is **`None` for every anonymous visitor**: `login_issue` is anonymous and touches no session; the only backend session write (`apps/core/middleware/language.py::LanguagePreMiddleware._apply_lang_param`) is gated on `request.user.is_authenticated`; `SessionBase.session_key` returns `None` until `save()`/`cycle_key()` | **Block option non-viable.** Recorded, not offered. Corrected option set in `B-03` |
| `X-14` | Phase 07 "verified no automated test for nginx" | `src/backend/tests/test_nginx_config.py` exists, runs in the fast gate (`pytestmark = [pytest.mark.unit]`), and exports a reusable `_location_block(text, location_match)` extractor | **Block option corrected.** `B-09` has a content gate (see `C-7`) |
| `D-2` | BLOCK 2 anchor `insert_after: {function_call: options.__getitem__}` | `Command.handle` computes `password` via a conditional-expression arm; there is no such call | **Anchor corrected** — `insert_before: {function_call: User.objects.create}` |
| `D-3` | BLOCK 5 option (c) runbook uses `--password <pw>` | `docker/entrypoint-create-admin.sh` calls `create_admin_user` with `--username`/`--telegram-id` only; the secret comes from `ADMIN_PASSWORD` | Plan instruction corrected — `B-06`'s runbook is `ADMIN_PASSWORD=`-based |
| `D-4` | `prod.py` carries **one** false claim | **Two** comments: the `EMAIL_HOST` guard comment and the `EMAIL_BACKEND` pin comment | Block re-scoped — `B-06` covers both, the second is phase 02's surface |
| `D-5` | `docker-deployment.md` asserts password-reset in **two** places | **Three** statements | Block re-scoped |
| `D-6` | (new) env allowlist gate | `config/settings/tests/test_env_allowlist_reverse.py::test_consumed_env_vars_are_allowlisted` AST-scans the **whole tree**; an env-backed setting needs an `ALLOWED_ENV_VARS` entry **and** four `.env.*.example` updates in the same commit | Binding on `B-08`'s trusted-proxy setting |
| `D-8` | (new) `bulk_ban_users` | The only one of the four bulk helpers with **no** `OperationalError`/`is_lock_timeout` boundary | Recorded — `B-07` must not add one |
| `D-11` | (new) `base.py` contention | `ALLOWED_ENV_VARS` = phase 02; `LOG_MASK_KEY` = phase 06; phase 09 is read-only on `base.py` | §C reservation rule |
| `C-2` | (verified) `claim_token`'s `RETURNING` matches `LoginToken`'s field set | **True at `f93e7fb`.** `RETURNING id, token_hash, telegram_id, created_at, expires_at, consumed_at`; `columns = [desc[0] for desc in cursor.description]` → `LoginToken(**dict(zip(columns, row, strict=True)))` | **Phase exit condition** — must be a *test*, not a comment (§G) |
| `C-3` | (verified) no `clearsessions` janitor | True — appears nowhere in `src/`, `docker/`, `.github/`, `Makefile`, `Makefile.ps1` | Constrains `B-03` options A″/B |
| `C-4` | (verified) three `_get_client_ip` copies | True — plus a **fourth** client-IP read the source plan never names: `apps/users/services/consent_record.py` → `_anonymize_ip(request.META.get("REMOTE_ADDR") or None)` | `B-08` gate `G-8a` |
| `C-5` | (verified) 9 `$proxy_add_x_forwarded_for` | True — 9 directives; `/protected-media/` is `internal; alias /media_volume/;` (no proxy, no header) | `B-09` scope |
| `C-6` | (verified) nginx is the first hop | True — `docker-compose.yml::nginx` publishes `80:80`/`443:443` on the host, `image: nginx:alpine`; `docker-compose.prod.yml` adds only a cert mount and `media_volume:ro`; no `set_real_ip_from`, no `real_ip` | **`Q2` is answered.** `B-08` has no Auditor task |
| `C-7` / `C-19` | (verified) `nginx -t` absent; `deploy.yml` health check | True — the health gate is `docker compose exec -T web curl http://localhost:8000/health/ready/`, i.e. port 8000 **inside the web container, bypassing nginx** | `B-09` gates `G-9b` |
| `C-12` | (assumed) `LoginTokenAdmin` needs coordination | **No coordination needed.** `fields is None`, `fieldsets is None`, `readonly_fields` = all 5 concrete fields, `has_add_permission → False`, `has_change_permission → False` unconditionally | Task dropped |
| `C-13` | (verified) "seven/eight direct-row tests" | **Nine construction sites** (`X-13`-adjacent; see §E) | Reconciled in §E |
| `C-14` | (verified) `test_two_issues_differ` | Exists and contradicts `04-AUT-007` — it calls `issue_token()` with no browser id, so each call mints a fresh binding and repeated anonymous issues genuinely accumulate live tokens | `B-04` **leaves it unchanged** (the exit condition records it unchanged; see §G.1 `B-04`) |
| `C-17` | (verified) bulk helpers take no `request` | True for `ban_user_for_ad` / `bulk_ban_users` — **but `moderation/views/review.py::ban_user` HAS a `request` and the target is `ad.user`** | `B-07` re-scoped: **3 of 5 paths reachable, not 2** |
| `C-22` | (verified) Django enforces `is_active` per request | True — `ModelBackend.get_user` → `user_can_authenticate` → `AuthenticationMiddleware` installs `AnonymousUser` → `@login_required` 302s | **`04-AUT-004`'s "invisible end to end" is refuted.** `Q4` closed by audit; `B-05` re-scoped; severity re-banding belongs to the **Validator** |
| `C-21` | (verified) no existing home for the client-IP helper | `apps/core/services/` has **no** request helper; its `__init__.py` re-exports only `record_event, can_contact_seller, get_seller_for_contact, record_contact_initiated, record_contact_response, get_site_name, get_site_name_async, translate_text` | A new module is genuinely needed |
| `X-15` | `B-01`'s "Verified starting state" is anchored on `C-9` and `C-12` | **`C-9` does not exist.** This table defines `C-2`…`C-7`, `C-12`…`C-14`, `C-17`, `C-19`, `C-21`, `C-22`; `C-9`, `C-10`, `C-11`, `C-15`, `C-16`, `C-18`, `C-20` appear nowhere in `.ai/`. **Documentation defect**, not a starting-state defect | Two corrections were dropped or renumbered in the §A.3 re-cut. The claims `B-01` actually rests on are re-derived and restated **in full, inline, in `B-01`'s "Verified starting state"** (re-verified at `ba1b059`); the dangling `C-9`/`C-10` citations are removed there. No other block's `C-*` citations are affected |

### A.5 Corrections this Planner makes **to the code context itself** (verified live)

| Code-context statement | Live truth at `f93e7fb` |
|---|---|
| `apps/core/tests/test_scheduler.py` pins the hourly list via `test_scheduler_uses_canonical_hohourly_list` and `test_daily_commands_include_alerts_and_rollup` | **Neither name exists.** The real names are `TestSchedulerConstants::test_hourly_commands_match_spec` (exact `==` list assertion on the 9 `HOURLY_COMMANDS`) and `TestSchedulerConstants::test_daily_commands_include_send_alerts` |
| BLOCK 2's blast radius: a `CommandError` "blocks the whole dev/prod bootstrap chain" | **Partly wrong.** `create_admin` `depends_on: load_catalog: service_completed_successfully`, but `web`, `bot` and `seed` depend on **`load_catalog`, not `create_admin`** — a policy failure does **not** stop `web`. Real impact: **no admin user exists** until an operator creates one, and `docker compose up` reports a failed service. Still HIGH operational risk, different mechanism |
| BLOCK 4 needs an `is_active` entry in `UserAdmin.list_filter` | **No such entry exists.** `list_filter = ["is_banned", "is_deleted", "ads_auto_publish", "is_staff", "is_superuser"]` — option (b) needs no `list_filter` edit |
| BLOCK 4 option (b)'s fixture blast radius spans both conftests | **2 write sites only**: `apps/seed/generators/users.py` and `apps/seed/tests/test_seed.py`. No `is_active` fixture in either conftest |
| BLOCK 8's `SESSION_COOKIE_AGE` is "14 days, Django default" | True but **never declared anywhere in `config/settings/`**; the effective refresh is **write-triggered** (`SESSION_SAVE_EVERY_REQUEST = False`), not per-request. A read-only request does not extend the session |
| BLOCK 7's `test_nginx_config.py` "parses `nginx.conf` only" | True (`_NGINX_CONF` = `docker/nginx/nginx.conf` only), and `docker/nginx/nginx.dev.conf` has no `= /metrics`, `/health/` or `/csp-report/` block |

## §B · Execution blocks

### B-01 — `UserAdmin` field contract

| | |
|---|---|
| **Findings owned** | `04-AUT-005` (credential + consent half), `04-VAL-004`, `PII-103` (merged), `04-VAL-001` (partial) |
| **Depends on** | **`B-05`** — hard, by the `G-3` resolution below. `G-3` **closed**; `G-4` **closed** (this section) |
| **Blocks** | `B-02` (`04-VAL-004`), `B-11`; phase 15 `15-AUTHZ-003`; phase 06 `PII-107`; inbound to `B-06` (`G-6`) |
| **Priority** | P0 · **Risk HIGH** |
| **Gates** | **`G-3` CLOSED** (option (i), `B-05` first) · **`G-4` CLOSED** (**option A** + the add-view override) — recorded below, with the Implementor brief |

**Objective.** Replace `UserAdmin`'s auto-built change form with an explicit, minimal
field contract so a moderator holding `has_change_permission` cannot write
`is_superuser`, `is_staff`, `user_permissions`, `groups` or the consent booleans, and
**no admin surface accepts a plaintext password** — *including the add view*.

**Verified starting state — re-derived at `ba1b059`, inline because §A.4 has no `C-9`
or `C-10` row to point at (`X-15`). Do not trust the numbers below; re-derive them.**
`src/backend/apps/users/admin.py::UserAdmin` declares `list_display` (5), `list_filter`
(5: `is_banned`, `is_deleted`, `ads_auto_publish`, `is_staff`, `is_superuser`),
`search_fields = ["telegram_id"]`, `readonly_fields = ["consent_given_at",
"consent_revoked_at", "deleted_at"]`. It declares **no** `fields`, **no** `fieldsets`,
**no** `exclude`, **no** `form`, **no** `radio_fields`, **no** `get_form`, **no**
`get_fieldsets`, **no** `get_urls`. `User` exposes 26 editable fields; `id` is a
`BigAutoField` whose `formfield()` returns `None`, so `fields_for_model` drops it into
`ignored` — the change form therefore resolves **22 editable fields**
(26 − `id` − the 3 existing read-only). `password` resolves as
`CharField(required=True, widget=AdminTextInputWidget)` — **a plain text input whose
rendered value is the stored hash**, i.e. the raw hash is already in the change-form
HTML for every moderator today. `LoginTokenAdmin` declares `readonly_fields` for all
five concrete fields with `has_add_permission → False` and `has_change_permission →
False` unconditionally, so **no form is ever rendered** and a new `LoginToken` column
cannot reach an admin surface (`C-12`; the `LoginTokenAdmin` coordination task stays
**dropped**). `src/backend/apps/users/tests/test_admin_pii_containment.py` has **no
class** — five module-level functions: `_assert_no_raw_telegram_id`,
`test_ads_user_link_hides_telegram_id`, `test_analytics_user_link_hides_telegram_id`,
`test_moderation_log_user_link_hides_telegram_id`,
`test_login_token_list_display_masks_telegram_id` (`X-9`). **There is no admin-view
test anywhere in the repository** — `reverse("admin:…")` appears in zero test files — so
the credential test needs a new module. `src/backend/apps/users/tests/` has **no
`conftest.py`** and `src/backend/conftest.py` is off-limits (§C.3), so the new module
carries a **module-local** `staff_user` fixture, matching
`apps/ads/tests/test_auth_nav.py`, `apps/ads/tests/test_media_security.py` and
`apps/moderation/tests/test_moderation_views.py`.

#### `G-3` — CLOSED: `B-05` runs before `B-01`

**Resolution: option (i) — `B-05` first.** `B-01` is no longer the phase's entry point;
the serial order becomes §C.1's *scenario alpha*:
`B-05 → B-01 → B-02 → B-03 → B-04 → B-07 → B-08 → B-09 → B-06 → B-10 → B-11`.

**The coupling that forced this** (verified against
`.venv/Lib/site-packages/django/contrib/admin/options.py::ModelAdmin.get_form`):

- `get_form()` derives its field list from `flatten_fieldsets(self.get_fieldsets(request, obj))`
  — **not** from `get_fields()`. `get_fields()` short-circuits on `if self.fieldsets` and
  is never consulted for form construction.
- `modelform_factory(self.model, fields=flatten_fieldsets(...))` → a `fieldsets` entry
  naming a **nonexistent** model field makes `fields_for_model` raise `FieldError`,
  which `get_form()` re-raises as *"Unknown field(s) … Check fields/fieldsets/exclude
  attributes of class UserAdmin."* — at form-construction time, i.e. **every add and
  every change request 500s**.
- Therefore `G-3` = (ii)/(iii) (`B-01` first, `is_active` kept) is safe **only if
  `is_active` is absent from `fieldsets`** — *not* merely in `readonly_fields`, which is
  what §H's fallback text said. `fieldsets` + `readonly_fields` together is the natural
  thing for an Implementor to write, and it is precisely the combination that detonates.

**The constraint this imposes, which survives regardless:** `B-01`'s `fieldsets` must be
derived from the **live** `User._meta.get_fields()` at implementation time, never copied
from this document. **`B-05` option (B) (`RemoveField is_active`) stays on the table** —
choosing (i) is exactly what keeps it safe, because `B-01` then builds its field set
against the post-`B-05` model.

**`is_active` disposition is read from `G-5a` at implementation time — it is not a
branch the Implementor resolves:**

| `G-5a` | `is_active` in `fieldsets` | why |
|---|---|---|
| (A) guard `login_status` · (C) record inert · (D) extend `AccountState` | **in `fieldsets` + `readonly_fields`** | the field survives; it is an account-state kill-switch, so it must be visible and inert |
| (B) `RemoveField is_active` | **omitted from `fieldsets` entirely** | a `fieldsets` entry naming a removed field is a 500 on every add and change |

**Structural tripwire for the whole block:** the new introspection tests call
`UserAdmin.get_form(...)` directly, so a `fieldsets`/model mismatch raises `FieldError`
**in the fast gate**, before it can reach a browser. That is the cheapest possible
guard against the one failure mode this block cannot afford.

#### `G-4` — CLOSED: **option A**, plus the add-view override

**Chosen: `form = django.contrib.auth.forms.UserChangeForm` + an explicit `fieldsets`,
plus `add_form = django.contrib.auth.forms.UserCreationForm` with `add_fieldsets`,
`get_form()` and `get_fieldsets()` overrides mirroring `django.contrib.auth.admin.UserAdmin`.
No new module. `exclude` is not used. `readonly_fields` is used only for
displayed-but-inert fields.**

**Why A and not B — the decisive argument neither plan records.** Option B puts
`password` in `readonly_fields`, which *does* remove it from `base_fields`
(`get_form()` does `exclude.extend(readonly_fields)` and `fields_for_model` drops it) —
so §I.1's claim that under B "`password` stays in the form but readonly" is wrong in the
other direction. But B then renders it through
`django/contrib/admin/helpers.py::AdminReadonlyField.contents()`, and because
`password` is no longer in `form.fields`, the `getattr(widget, "read_only", False)`
short-circuit at the top of `contents()` cannot fire; execution reaches
`django/contrib/admin/utils.py::display_for_field` → `display_for_value` →
`str(value)` — the **raw hash, verbatim, into the page**. And that is not a new
disclosure B introduces: **it is the disclosure that already exists today**, because the
auto-built `CharField(AdminTextInputWidget)` renders the stored hash as its input value.
B fixes the *write* and leaves the *disclosure* exactly where it is. Only A fixes both:
`password` is a declared `ReadOnlyPasswordHashField` (`required=False`, `disabled=True`),
so `Field.disabled` makes `BoundField.value()` return `bound_data(data, initial)` — the
POSTed plaintext is discarded before validation, `construct_instance` writes the
existing hash back byte-identically, `ModelAdmin.save_model` is literally `obj.save()`
and **no hasher ever runs** — and `ReadOnlyPasswordHashWidget` renders
`hasher.safe_summary()` (masked algorithm/salt/hash) instead.

**Why A and not C.** C's only marginal content over A is a form-level `disabled` layer,
which A obtains for the same fields through `readonly_fields`, plus a `Meta.fields`
allowlist — and a `Meta.fields` list freezes the field set exactly as hard as `fieldsets`
does, so it answers none of `B-01`'s stated risk. C would also create the repository's
**first** `forms.py` for one class, against `.kilo/rules/project.md` rules 5 and 7. If
`password = ReadOnlyPasswordHashField()` is declared, C *is* A. Decided: **A**.

**The add view — IN SCOPE, and this is what makes A sufficient rather than partial.**
Today `UserAdmin.get_form(request, None)` resolves the **same 22 fields** including
`password` as a writable `CharField`, and no `UserCreationForm` confirmation or hashing
ever runs. `has_add_permission` returns `request.user.is_superuser`, so the *escalation*
half of the add view is already closed and stays phase 15's (`15-AUTHZ-003`). The
*plaintext* half is the same defect on the same class, and `04-AUT-005`'s closure
criterion is plural, so leaving it open would be a half-closure recorded as closed.
Mechanism chosen: the framework's own three pieces — `add_form`, `add_fieldsets`, and
the `get_form()` / `get_fieldsets()` pair. **Why this is mandatory, not optional** —
**correction to the Researcher's finding 4:** under A *alone* the add view does **not**
produce an empty-password-authenticable account. `django.contrib.auth.hashers.verify_password`
calls `identify_hasher("")`, which raises `ValueError`, which sets `fake_runtime = True`
and returns `False` — so `check_password("")` is `False` in Django 5.2 and the residue is
a *silently credential-less* account, not a login. The **hard** residue is a second one:
`chat_id` is `unique=True, db_index=True`, NOT NULL with **no default**, so
`Field.get_default()` returns `""`; if the add form does not carry `chat_id`, the insert
fails on a NOT NULL bigint. Both residues are removed by the override. `add_fieldsets`
deliberately carries **no** privilege flags — grants go through
`core/management/commands/create_admin_user.py::Command.handle`, which is the only
`is_staff=True, is_superuser=True` writer in the repository.

**Bonus the `B-01 → B-02` edge now rests on:** `UserCreationForm.clean_password2` /
`_post_clean` call `password_validation.validate_password`. `AUTH_PASSWORD_VALIDATORS`
is absent from every settings module today, so the call is a no-op; the moment `B-02`
lands, **the admin add view enforces the policy with no further change**. That is
`04-VAL-004`'s "no admin path can set a weak password" made concrete.

**The dead `../password/` button — DECIDED: do not add the URL.** `UserChangeForm`'s
widget template renders `<a class="button" href="{{ password_url|default:"../password/" }}">Reset
password</a>`; `password_url` is only put in context by
`django.contrib.auth.admin.UserAdmin.render_change_form`, and this project registers
only `path("admin/", admin.site.urls)` in `src/backend/config/urls.py` with no
`UserAdmin.get_urls()`. So under A the change form gains a button that **404s**.
**Not added**, because `AdminPasswordChangeForm` + `get_urls()` is a new
operator-facing credential surface and it is squarely `B-06`'s `G-6` credential-recovery
question, which is still open and unowned by this block. **Handed to `B-06` as an inbound
item.** The consequence is recorded rather than hidden: `manage.py changepassword` (and
`create_admin_user` for bootstrap) become the only reset paths, and the change form
becomes useless for a moderator who forgot a password.

#### Final field partition — the 22 fields

Rule applied, and *why* it is a rule rather than 22 independent judgements: **omit** a
field when it must not be writable **and** rendering it would imply a capability the
block is removing (the privilege set); **show it read-only** when it must be inert but an
operator legitimately needs to read it to do the job (account state, consent state,
identity, provenance, audit columns); **leave it writable** only when an operator
legitimately needs to change it *and* no service-side invariant is bypassed.

| # | Field | Partition | Grounded in what the code actually does |
|---|---|---|---|
| 1 | `password` | **in `fieldsets`** (rendered by `UserChangeForm` as a declared `ReadOnlyPasswordHashField`, `required=False`, `disabled=True`) | `ModelAdmin.save_model` is `obj.save()`; a disabled field takes `initial`, so a POSTed plaintext never reaches `cleaned_data`/`construct_instance`; the widget renders `hasher.safe_summary()`. Replaces today's raw-hash-in-an-editable-input. **Never writable, under any form.** |
| 2 | `is_superuser` | **omitted from `fieldsets`** | `User.role` maps it to `UserRole.ADMIN`; `has_change_permission` ignores `obj`, so any `is_staff` actor reaches every row including superusers. `create_admin_user.py::Command.handle` is the only grant writer. `save_related` → `form.save_m2m()` writes the m2m tables directly |
| 3 | `is_staff` | **omitted from `fieldsets`** | same self-grant argument; `moderation/views/decorators.py::staff_required` is the consumer, and `User.role` treats `is_staff` as `ADMIN` |
| 4 | `groups` | **omitted from `fieldsets`** | **zero read sites** — the only non-test hits for `groups` are `apps/lookups/`, which is a different `Group` model. Authorization is `User.role` (two flags) + per-view decorators |
| 5 | `user_permissions` | **omitted from `fieldsets`** | **zero read sites** — the only occurrence is the model declaration itself |
| 6 | `chat_id` | **omitted from the change `fieldsets`; present and writable in `add_fieldsets`** | `unique=True`, `db_index=True`, NOT NULL, **no default**; bot-owned (`users/services/login_token.py`). Today it resolves `required=True` in the change form — a required unique field an operator submits without thinking is a collision trap. It must remain writable **at creation** because `Field.get_default()` returns `""` and a NOT NULL bigint rejects that |
| 7 | `is_banned` | **in `fieldsets` + `readonly_fields`** | the sanctioned writers are `moderation/admin_actions.py::ban_user_for_ad` and `::bulk_ban_users`, both of which write a `ModerationLog` row via `log_ban_account`; a form write bypasses the moderation audit. Ban stays fully reachable from `AdAdmin.action_ban_user`. **Read `account_state.py::can_publish_ad` / `can_login` and `telegram_bot/middlewares/permissions.py`** |
| 8 | `is_deleted` | **in `fieldsets` + `readonly_fields`** | `users/services/deletion.py::withdraw_consent` is the only sanctioned writer and runs `consent_revoked_at` + `is_deleted` + `deleted_at` + PII nulling + `LoginToken` deletion + ad soft-delete inside **one** `transaction.atomic()`. A form write bypasses every step |
| 9 | `is_declined` | **in `fieldsets` + `readonly_fields`** | `decline_consent` sets it and registers `transaction.on_commit(bump_search_cache_version)`. A form write skips the bump, so `ads/views/listings.py` and `ads/services/listings_query.py` — which filter `user__is_declined=False` live — keep serving a consent-declined seller's ads out of the cache. That is a **real cache-invalidation bug**, not a style issue |
| 10 | `ads_auto_publish` | **in `fieldsets` + `readonly_fields`** | read by `account_state.py::can_publish_ad` and `telegram_bot/middlewares/permissions.py::AccountStateMiddleware` (where `False` restricts `/post`); the only writers are `give_consent` / `decline_consent` |
| 11 | `telegram_premium` | **in `fieldsets` + `readonly_fields`** | `trust/services/trust_calculator.py::TrustCalculator._get_trust_level` reads it to floor a seller at `TrustLevel.VERIFIED` regardless of score. A form write forges a trust floor. The only other writer is `seed/generators/users.py` |
| 12 | `telegram_id` | **in `fieldsets` + `readonly_fields`** | the moderator must **see** it to correlate a report with a row, and `search_fields = ["telegram_id"]` searches on it independently of the form — `get_form()` never consults `search_fields`, and `LoginTokenAdmin` already pairs `search_fields` with a `readonly_fields` entry, so there is **no** `readonly_fields`/`search_fields` trap here. It must not be **written**: `services/login_token.py::claim_token` binds a login token by `telegram_id`, so a write is an identity-takeover primitive. `withdraw_consent` nulls it, so a write would also restore erased identity linkage |
| 13 | `username` | **in `fieldsets` + `readonly_fields`** | `USERNAME_FIELD` ⇒ it is the admin login identifier (`AdminSite.login` → `AuthenticationForm`), so a rename is an account-targeted operation a moderator should not have. `withdraw_consent` sets it to `None` as part of GDPR erasure |
| 14 | `first_name` | **in `fieldsets` + `readonly_fields`** | `withdraw_consent` empties it to `""` (NOT NULL) as part of erasure; a form write repopulates erased PII |
| 15 | `last_name` | **in `fieldsets` + `readonly_fields`** | same |
| 16 | `email` | **in `fieldsets` + `readonly_fields`** | same erasure argument. **Correction to the Researcher's §6:** `AbstractUser.email` is `models.EmailField`, whose `formfield()` returns `forms.EmailField` — format **is** validated today, so that is not an extra argument for read-only. The real argument is erasure plus *zero consumers*: there is no `PasswordResetView`, no `password_reset` URL, and `EMAIL_BACKEND` is pinned in `prod.py` (phase 02's `CFG-004`) |
| 17 | `is_active` | **in `fieldsets` + `readonly_fields`**, or **omitted entirely** if `G-5a` = (B) | see the `G-3` table above. `ModelBackend.get_user` → `user_can_authenticate` → `AnonymousUser` → 302, so the field is a real kill-switch (`C-22` refutes "not enforced"); it must be visible and inert. `list_filter` has **no** `is_active` entry (§A.5), so it is invisible on the changelist either way |
| 18 | `telegram_language` | **in `fieldsets` + `readonly_fields`** | `max_length=5`, `choices=LanguageLocale`; written only by the bot's `/language`, read only by `telegram_bot/middlewares/language.py`. A form write is overwritten by the next `/language` and can break `translation.activate` |
| 19 | `source` | **in `fieldsets` + `readonly_fields`** | `choices=AdSource`, `db_index=True`, `null=True`, and it is provenance of record (`null` = real, `AdSource.SEED` = seeded). The only writer is `seed/generators/users.py`; form-write lets an operator launder a seeded row as real, destroying seed-data integrity |
| 20 | `date_joined` | **in `fieldsets` + `readonly_fields`** | `AbstractUser.date_joined = models.DateTimeField(_("date joined"), default=timezone.now)` — **not** `auto_now_add` (the Researcher's §6 says "auto-`add`" and contradicts itself in the same row), so it is genuinely writable today and a form write rewrites account age. Zero read sites in `src/` |
| 21 | `last_login` | **in `fieldsets` + `readonly_fields`** | written by `django/contrib.auth.base_user.AbstractBaseUser.last_login` / `update_last_login` on `ModelBackend.authenticate`; a form write rewrites the last-login audit trail. Zero read sites in `src/` |
| 22 | `preferred_city` | **in `fieldsets`, WRITABLE** — the single retained write | `search/views/preferred_city.py::set_preferred_city` is the sanctioned writer and does nothing beyond `request.user.preferred_city = city; save(update_fields=[...])` plus a cookie. A form write bypasses no invariant, and it is the only operator-useful correction left on the form. `apps/core/middleware/preferred_city.py` reads it (DB wins over cookie for authenticated users) |
| — | `consent_given_at`, `consent_revoked_at`, `deleted_at` | **already `readonly_fields` — keep, unchanged** | erasure/service-owned timestamps |

**Net effect on the form.** The change form's writable set becomes exactly
**`{preferred_city}`**, plus `password` as an inert read-only hash. That is the intended
shape: an all-readonly form would make `has_change_permission` decorative.

#### Operator-capability record — what becomes intentionally unreachable

The source plan's acceptance criterion *"an existing operator workflow that used a
removed field is recorded as intentionally broken"* is discharged here. **There is no
unban action anywhere in the system**: `AdAdmin.actions` is
`["action_reject", "action_ban_user", "action_soft_delete", "action_approve"]` — all
four are one-way; `moderation/admin_actions.py::ban_user_for_ad` and `::bulk_ban_users`
only ever set `is_banned = True`; `UserAdmin`'s only action is `withdraw_consent_action`.
A tree-wide search for `is_banned = False` / `is_deleted = False` outside tests returns
**no production writer**. `ads_auto_publish`'s only writers are `give_consent` and
`decline_consent`, both driven by the user's own consent flow, never by an operator.

| Operator capability | Today | After `B-01` | Recorded disposition |
|---|---|---|---|
| Set a user's password in the change form | yes (verbatim plaintext) | **no** | **intentionally broken.** Remedy: `manage.py changepassword`; bootstrap `create_admin_user`. The `docs/ops/` procedure is **`B-06`'s**, not this block's |
| Un-ban a user | **the `User` change form, and nothing else** | **no** | **intentionally broken — knowingly accepted.** Ban remains reachable from `AdAdmin.action_ban_user`; unban has no service path, no moderation-log inverse and no audit record today, so this removes an *unaudited* administrative override. Remedy is superuser/scripted. **The reversal, if the coordinator judges this unacceptable, is deleting one `readonly_fields` entry — no structural change** |
| Toggle the publishing ban (`ads_auto_publish`) | yes | **no** | **intentionally broken.** Remedy is the user's own consent flow (`give_consent` / `decline_consent`) |
| Un-soft-delete / undo erasure (`is_deleted`) | yes (bypasses `withdraw_consent`) | **no** | **intentionally correct** — WITHDRAW is terminal by design, PII is already nulled, and an "undelete" would resurrect a row with erased identity |
| Toggle browse-only (`is_declined`) | yes (bypasses the cache bump) | **no** | **intentionally correct** — the service bumps the search-cache version on commit; a form write leaves stale listings live |
| Grant/revoke `is_superuser`, `is_staff`, `groups`, `user_permissions` | yes | **no** | **intentionally broken.** Grant path: `create_admin_user.py::Command.handle`. The **predicate** is phase 15 `15-AUTHZ-003`'s; this block changes the field set only |
| Re-point `telegram_id` at another account | yes | **no** | **intentionally broken** — `claim_token` binds a login token by `telegram_id`; this is identity takeover |
| Rename `username` | yes | **no** | **intentionally broken** — `USERNAME_FIELD` (admin login identifier) and `withdraw_consent` nulls it during erasure |
| Restore erased `first_name` / `last_name` / `email` | yes | **no** | **intentionally correct** — repopulating erased PII |
| Edit `chat_id` | yes (`required=True`, unique) | **no** on change; **yes** at creation | **intentionally broken on change** — bot-owned and unique; the required-field trap is removed |
| Edit `telegram_language` | yes | **no** | **intentionally broken** — bot-owned, overwritten by the next `/language` |
| Forge `telegram_premium` | yes | **no** | **intentionally broken** — forges a `TrustLevel.VERIFIED` floor |
| Edit `date_joined` / `last_login` | yes | **no** | **intentionally correct** — pure audit columns |
| Re-label a row's provenance (`source`) | yes | **no** | **intentionally broken** — provenance of record |
| Edit `preferred_city` | yes | **yes (retained)** | intentionally retained |
| **Create a user with a hashed, confirmed, policy-validated password** | **no** | **yes (new)** | `add_fieldsets` + `UserCreationForm`; runs `validate_password`, so `B-02` applies with no further change |
| Withdraw consent from the changelist action | **no — the action was never registered** | **no (unchanged)** | `withdraw_consent_action` is byte-unchanged, but `UserAdmin` declares **no** `actions`, so `ModelAdmin.get_actions` never yields it. **CORRECTION (2026-10-01, live introspection against Django 5.2.17) — this row's premise was false.** It previously read *"yes → yes (unchanged)"* on the strength of *"it is gathered by `ModelAdmin.get_actions` from the changelist"*. **It is not gathered at all.** Full evidence, the `G-7` framing and the test `B-07` must write are in `B-07`'s "Correction applied — `withdraw_consent_action` is unreachable, and always was" |

#### Boundary limit — read this before writing the DoD

`B-01`'s goal *"consent and account-state booleans read-only in admin"* is **true of the
`User` change form and false of the admin as a whole.** `AdAdmin.has_change_permission`
returns `is_staff or is_superuser`, and `AdAdmin.action_ban_user` →
`moderation/admin_actions.py::bulk_ban_users` writes
`User.objects.filter(id__in=user_ids).update(is_banned=True)` directly. So
**`is_banned` remains admin-writable from the `Ad` changelist after `B-01` ships**, for
the ordinary user. `15-AUTHZ-003` owns the predicates; `B-01` changes **none** of the
four `has_*_permission` bodies, and that is the detection, not a claim. Recorded so the
phase report cannot overstate the closure.

**Validator advisory (2026-10-01) — the `is_active` kill-switch is reachable but
undiscoverable, and `B-01` owns the surface that decides it.** `UserAdmin` today declares
no `fields`/`fieldsets`, so the auto-built change form **is** an `is_active` write path for
any `is_staff` holder; adding `is_active` to `list_display`/`list_filter`, or an explicit
`fieldsets` that names it, would make the control visible where an operator would look for
it. Advisory only — it changes nothing in this block's decisions, tests, brief or gates.

#### Tests required — corrected list

Two constraints bind every entry: **no field-count assertion** (the count differs between
the change and add forms by construction, and the contract is the *invariant*, not the
number), and **absence alone is insufficient** — "no writable path" has three measurable
states and only two of them are acceptable.

Mechanics, verified: `UserAdmin(User, admin.site).get_form(request, obj, change=True)`.
`request` needs **only** `request.user` set to a real user instance — this `UserAdmin`
overrides all four `has_*_permission` methods to read `request.user.is_staff` /
`.is_superuser`, and `get_form` calls `has_change_permission` **only when `change=True`**
(`getattr(request, "user")` guard aside). `request._messages` is **not** required by
`get_form` — `message_user` is reached only from the save paths, and `MessageMiddleware`
is in `MIDDLEWARE`, so `django.test.Client` covers it. Use `change=True`, or the
assertion says nothing about the change view. URL names are `admin:users_user_change`
(args `(pk,)`) and `admin:users_user_add` (app_label `users`, model_name `user`; there
is **no** `admin:auth_user_password_change`). `client.force_login(staff_user)` is
sufficient — `AdminSite.has_permission` is `request.user.is_active and request.user.is_staff`.
No CSRF token needed (the test client's `enforce_csrf_checks` defaults to `False`).

**Vacuity guard — mandatory and non-negotiable.** The three module-local `staff_user`
fixtures in this repository create users with `password="x"` **in plaintext**. A
`check_password(raw) is False` assertion against such a user is true for the wrong
reason. Every credential test must therefore (a) build the target's password with
`set_password(<known raw>)`, and (b) assert the **positive control**
`target.check_password(known_raw) is True` *before* the POST. Without (b) the test also
passes on an account that never had a credential.

**In `src/backend/apps/users/tests/test_admin_pii_containment.py`** (module-level
functions per `X-9`; `pytestmark = [pytest.mark.unit]` already present; no DB writes, so
no `django_db` marker is expected):

1. `test_user_change_form_offers_no_writable_privilege_field` — resolve the form with a
   `request.user` that is `is_staff=True, is_superuser=False`, `change=True`; for
   `is_superuser`, `is_staff`, `groups`, `user_permissions` assert
   `name not in Form.base_fields or Form.base_fields[name].disabled is True`.
   *Behavioural, not trivia:* it asserts the security invariant of the deployed form, and
   because it **calls `get_form()`** it is also the block's structural tripwire — a
   `fieldsets` entry naming a field the model no longer has raises `FieldError` here.
2. `test_user_change_form_offers_no_writable_consent_or_account_state_field` — same
   mechanism for `is_declined`, `is_deleted`, `ads_auto_publish`, `is_banned`.
   *Behavioural:* the invariant is "consent and account state move only through
   `services/deletion.py`", which is enforced at the form boundary, not the class.
3. `test_user_change_form_password_is_never_a_writable_text_field` — for `password`,
   assert `name not in Form.base_fields or Form.base_fields["password"].disabled is True`,
   **and** that when present the widget is not an editable plain-text input
   (`widget.read_only is True`). *Behavioural:* "the credential is not an editable text
   box" is the property; asserting on `CharField` would be trivia, and asserting on the
   declared field *type* would be trivia.
4. `test_user_change_form_fieldset_never_exposes_an_uneditable_field` — flatten
   `UserAdmin(User, admin.site).get_fieldsets(request, obj)` with
   `django.contrib.admin.utils.flatten_fieldsets` and assert every name in the block's
   must-be-inert set is either absent or in `UserAdmin.get_readonly_fields(request, obj)`.
   *Behavioural:* `fieldsets` is what an operator sees and what drives rendering; an
   assertion on `base_fields` alone can be satisfied by a `Meta.exclude` that 500s at
   render time (`helpers.Fieldline.__iter__` → `AdminField` → `form["password"]` →
   `KeyError`). This test is what makes the `exclude`-plus-`fieldsets` trap detectable.
5. `test_withdraw_consent_action_remains_available` — assert `"withdraw_consent_action"`
   is in `UserAdmin(User, admin.site).get_actions(request)`.
   *Behavioural, not trivia:* `B-01` removes every form write path for `is_declined` /
   `is_deleted`, which makes this changelist action the **only** sanctioned erasure path,
   so its survival is an operator capability, not a class attribute. Mechanics: a
   `RequestFactory().get(...)` is enough — `@admin.action(description=...)` leaves
   `permissions=None`, so no `allowed_permissions` attribute is set and
   `_filter_actions_by_permissions` passes the action through without calling
   `has_perm`. Do **not** assert on `UserAdmin.actions`, which is `()` by default.

**In `src/backend/apps/users/tests/test_admin_change_form.py`** (new module; this is the
first admin-view test in the repository):

6. `test_change_form_html_never_renders_the_raw_password_hash` — create the target with
   `set_password(<known raw>)`, `client.force_login(staff_user)`, GET
   `reverse("admin:users_user_change", args=[target.pk])`, assert neither the raw password
   nor the full stored hash string appears in `response.content.decode()`.
   *Behavioural:* **this test fails on today's code**, because the auto-built
   `CharField(AdminTextInputWidget)` renders the stored hash as its input value. It is
   the assertion that makes option A's benefit measurable rather than asserted, and it is
   the second live defect this block closes (credential disclosure, not just credential
   write).
7. `test_admin_change_does_not_accept_a_plaintext_password` — POST
   `{"password": <plaintext>} ∪ every required key of the resolved form` to
   `admin:users_user_change` (checkboxes omitted for `False`); assert the response
   redirects/succeeds, `target.check_password(plaintext) is False`, and
   `target.password == hash_before` **byte-identical**. Positive control first
   (vacuity guard above). *Behavioural:* it drives the real view through
   `get_form → form.save(commit=False) → save_model → obj.save()` and asserts on the
   stored credential, which is the actual asset. It holds under every `G-4` option and
   fails on today's code — **this is the test that closes `04-AUT-005`.**
8. `test_non_superuser_moderator_cannot_escalate_via_the_change_form` — a non-superuser
   `is_staff` moderator POSTs `is_superuser=on` (plus every required key) to a
   **superuser's** row — reachable today because `has_change_permission` ignores `obj` —
   and asserts `target.refresh_from_db().is_superuser is False`.
   *Behavioural:* it closes the loop on the *predicate × field-set* interaction for the
   exact actor the finding describes. **The POST succeeds on today's code**, so this is a
   true regression guard rather than a restatement of the new class.
9. `test_admin_change_cannot_flip_consent_or_account_state` — same actor, an ordinary
   seller with `is_declined=False`, `is_deleted=False`, `ads_auto_publish=True`; POST
   `is_declined=on`, `is_deleted=on`, and omit `ads_auto_publish`; assert all three are
   unchanged. *Behavioural:* the invariant is the service boundary, and today this POST
   also silently skips `bump_search_cache_version`.
10. `test_admin_add_view_stores_a_hashed_confirmed_password` — a superuser fixture POSTs
    `username`, `telegram_id`, `chat_id`, `password1`, `password2` to
    `admin:users_user_add`; assert success, `created.check_password(raw) is True`,
    `created.password != raw`, and `created.has_usable_password()`.
    *Behavioural:* the only test that proves the **add view** is closed. Under today's
    code the add form has no `password1`/`password2` and writes a verbatim plaintext;
    under option A *without* the `get_form`/`get_fieldsets` override it creates a
    credential-less account and, with `chat_id` absent from the form, fails on a NOT NULL
    bigint. This is what turns the add-view decision into a testable claim.
11. `test_non_superuser_moderator_cannot_reach_the_add_view` — GET
    `admin:users_user_add` as a non-superuser `is_staff`; assert `403`.
    *Behavioural:* it pins the add view's blast radius as superuser-only, which is the
    justification for closing the plaintext half here while leaving the escalation half
    to `15-AUTHZ-003`. One line, and it catches a predicate regression.

**Regression, unchanged:** the five existing module-level `*_hides_telegram_id` tests
(`X-9`, `X-12`, §E.3) stay green and unedited.

**Scope (semantic units).**

| Path | Symbol | Change |
|---|---|---|
| `src/backend/apps/users/admin.py` | `UserAdmin.form` | **add** — `django.contrib.auth.forms.UserChangeForm` |
| `src/backend/apps/users/admin.py` | `UserAdmin.fieldsets` | **add** — the change-view contract, exactly one declaration |
| `src/backend/apps/users/admin.py` | `UserAdmin.add_form` | **add** — `django.contrib.auth.forms.UserCreationForm` (a plain class attribute; honoured **only** through the `get_form()` override) |
| `src/backend/apps/users/admin.py` | `UserAdmin.add_fieldsets` | **add** — `(None, {"classes": ("wide",), "fields": ("username", "telegram_id", "chat_id", "password1", "password2")})`; no privilege flags |
| `src/backend/apps/users/admin.py` | `UserAdmin.readonly_fields` | **amend** — keep the three existing entries, add the inert-but-visible set. **Never** add `password`: `get_form()`'s `new_attrs` trick then sets the declared field to `None`, `DeclarativeFieldsMetaclass` pops it, and the widget's `read_only` short-circuit in `AdminReadonlyField.contents()` stops firing, so the **raw hash** renders. Under option A, `password` must stay a declared, disabled field |
| `src/backend/apps/users/admin.py` | `UserAdmin.get_form` | **add** — substitute `self.add_form` when `obj is None`, else `super().get_form(...)` |
| `src/backend/apps/users/admin.py` | `UserAdmin.get_fieldsets` | **add** — return `self.add_fieldsets` when `obj is None`, else `super().get_fieldsets(...)` |
| `src/backend/apps/users/admin.py` | `UserAdmin.has_add_permission` / `has_change_permission` / `has_delete_permission` / `has_view_permission` | **byte-unchanged** — phase 15 `15-AUTHZ-003` owns the predicate |
| `src/backend/apps/users/admin.py` | `UserAdmin.withdraw_consent_action` | **byte-unchanged** — phase 06 `PII-107` owns the `ConsentRecord` write |
| `src/backend/apps/users/admin.py` | `UserAdmin.list_display` / `list_filter` / `search_fields` | **byte-unchanged** — do not reorder; `list_display`'s first entry is the row link |
| `src/backend/apps/users/tests/test_admin_pii_containment.py` | module level | add tests 1–5 |
| `src/backend/apps/users/tests/test_admin_change_form.py` | **new module** | add tests 6–11, with a **module-local** `staff_user` fixture and a module-local superuser fixture |

**Corrected out of the source plan's surface.** The `TestAdminPiiContainment` class does
not exist (`X-9`) — new tests are **module-level functions**. `list_filter` needs no
`is_active` edit (§A.5). **`src/backend/apps/users/forms.py` is NOT created** — `G-4`
chose option A, so the plan's option (c) surface is dropped.

**Out of scope.** `withdraw_consent_action`; the four `has_*_permission` bodies;
`LoginTokenAdmin`; `mask_telegram_id`; `get_urls()` / `AdminPasswordChangeForm` / the
`../password/` URL (`B-06`'s `G-6`); `config/urls.py` (read-only, needed only to confirm
the admin prefix); `config/settings/test.py::PASSWORD_HASHERS` (phase 02 owns it); any
`AUT-00N` comment (§D item 14); `ads/dashboard/*` and `seller_required` — neither exists;
`conftest.py` (§C.3). **No i18n work:** the only strings the change introduces are
Django's own (`ReadOnlyPasswordHashWidget`'s "Raw passwords are not stored…", "No
password set.", "Reset password", "Password confirmation"), which live in Django's
catalogs and are **not** project `.po` msgids. Do not open an i18n task that resolves to
nothing.

**Agents.** Implementor **yes** (ships the code) · Auditor **yes** (field-set derivation
is the block's whole risk; a wrong derivation produces a green test over a still-
exploitable form) · Researcher **yes** (done — §`G-4` above) · Planner **yes** (done) ·
Validator **yes** (modifies an authorization surface; `04-VAL-004` ordering). **No
deviation** from the source plan's HIGH → all-agents rule.

**Risks and their containment.**

| Risk | Sev | Containment |
|---|---|---|
| A `fieldsets` entry names a field that does not exist → `FieldError` → **every add and change request 500s** | **HIGH** | `G-3` resolved to (i) so the field set is built against the settled model; tests 1–4 call `get_form()` directly, so the mismatch fails the fast gate |
| `exclude` (or `form.Meta.exclude`) names a field `fieldsets` also names → `KeyError` → 500 | **HIGH** | `exclude` is not used anywhere in this block; `readonly_fields` is the only "displayed-but-inert" mechanism. Recorded as a trap in the brief |
| `password` is put in `readonly_fields` → raw hash rendered | **HIGH** | the `readonly_fields` row in the scope table says so explicitly, with the mechanism |
| `B-05` option (B) lands after `B-01` → 500 | HIGH | **eliminated by the `G-3` resolution** — `B-01` runs second |
| Losing a field nobody intended | MED | derive from `User._meta.get_fields()`, not hand-list; `get_form()` in a test proves it resolves |
| A `fieldsets` declaration freezing the field set against a later `AddField` (phase 06 erasure columns, phase 15 role fields) | MED | recorded; every `AddField` in this phase is cross-checked against `fieldsets` (§C.3). **`B-05` is the one live instance and it is now sequenced first** |
| The moderator loses the unban path | MED | knowingly accepted; ban remains reachable from the Ad changelist; the reversal is one line |
| The `../password/` button 404s | LOW | knowingly accepted and handed to `B-06`; recording it beats shipping an unowned credential surface |
| A dead `admin:users_user_add` for a project whose only user-creation path was the (broken) form | LOW | the add view now works *better* than today: hashed, confirmed, policy-validated |

**Rollback.** Delete `form`, `fieldsets`, `add_form`, `add_fieldsets`, `get_form`,
`get_fieldsets` and restore `readonly_fields` to its three entries; the auto-built form
returns. Pure class-attribute edit, no migration, no data change. If the change view must
be rolled back while keeping the add view, delete `fieldsets` and `readonly_fields`
additions only — the two views are independent.

**Definition of done (supersedes §G.1's `B-01` row, which predates this decision).**
Tests 1–11 green · the four `has_*_permission` bodies, `withdraw_consent_action`,
`list_display`, `list_filter` and `search_fields` byte-unchanged · **exactly one
`fieldsets`, one `add_fieldsets`, one `get_form` and one `get_fieldsets` on `UserAdmin`**
(the "exactly one field-contract declaration" rule in §D item 6 now spans two fieldset
tuples because the add view is in scope) · the operator-capability record above is
reproduced verbatim in the commit body · `ruff` and `basedpyright` clean on
`src/backend/apps/users/admin.py` and both test modules · fast gate green (`--create-db`
after any DB restart).

**Coordinator follow-ups outside this block's editable footprint** (recorded here so
they are not lost; `main` owns each):
1. **§C.1** — the serial order becomes scenario alpha (`B-05 → B-01 → …`); the current
   "scenario beta" text names `B-01` first and is now wrong.
2. **§C.3** — the `src/backend/apps/users/admin.py` row's "`B-01`'s `fieldsets` must be
   built on the post-`B-05` field set when `G-3` = (i)" is now unconditional, not
   conditional.
3. **§G.1** — the `B-01` row's "exactly **one** `fieldsets` declaration" needs the
   `fieldsets` + `add_fieldsets` + two-override wording above.
4. **§I.1** — option A is chosen; B is **withdrawn on the raw-hash-disclosure ground**;
   C is **withdrawn as functionally identical to A**.
5. **`B-02`'s out-of-scope line** reads *"`UserCreationForm` (that is `B-01`'s, under its
   option (c) only)"* — under option A `B-01` uses Django's `UserCreationForm`, creates
   no project file, and `add_fieldsets` now means `B-02`'s validators apply to the admin
   add view automatically. That parenthetical is stale.
6. **`B-06`'s `G-6`** gains an inbound item: the sanctioned password-reset path after
   `B-01` is `manage.py changepassword`, and the admin change form's "Reset password"
   button is a known 404 by decision.

**Implementor brief.**

```yaml
id: 04-b01-admin-field-contract
title: Replace UserAdmin's auto-built change form with an explicit field contract
priority: high
depends_on:
  - B-05            # G-3 CLOSED as (i): B-05 runs first
source_reference: .ai/plans/04-auth-login-remediation.md
source_section: BLOCK 1 — UserAdmin field contract
source_blocks: ["BLOCK 1", "04-AUT-005", "04-VAL-004", "PII-103", "04-VAL-001"]

description: >
  src/backend/apps/users/admin.py::UserAdmin declares no fields, no fieldsets and no form,
  so Django auto-builds a ModelForm over every editable User field: 22 of them, including
  password as a writable CharField(AdminTextInputWidget) whose rendered value is the stored
  hash, is_superuser, is_staff, groups, user_permissions and every consent/lifecycle
  flag. Because UserAdmin.has_change_permission ignores obj and returns request.user.is_staff,
  any staff moderator can reach every row. Declare the field contract explicitly (G-4 =
  option A) and close BOTH the change view and the add view.

goals:
  - "no admin surface accepts a plaintext password - change view AND add view"
  - "the stored password hash is never rendered into the change-form HTML"
  - "is_superuser / is_staff / groups / user_permissions are unreachable through the form"
  - "consent and account-state booleans are visible but inert through the form"
  - "the only retained write is preferred_city"
  - "behavioural assertions only - no field-count assertion"
  - "every removed operator capability is recorded as intentionally broken"

extra_context: >
  READ FIRST, IN THIS ORDER. (1) The section prose above: "Verified starting state"
  (re-derived at ba1b059 - the plan's own C-9/C-10 citations do not exist, see X-15),
  "G-3 - CLOSED", "G-4 - CLOSED", "Final field partition - the 22 fields",
  "Operator-capability record", "Boundary limit". (2) src/backend/apps/users/admin.py in
  full. (3) .venv/Lib/site-packages/django/contrib/admin/options.py::ModelAdmin.get_form
  and get_fieldsets, django/contrib/admin/helpers.py::Fieldline.__iter__ and
  AdminReadonlyField.contents, django/contrib/admin/utils.py::display_for_field, and
  django/contrib/auth/forms.py::UserChangeForm / UserCreationForm /
  ReadOnlyPasswordHashField. (4) django/contrib/auth/admin.py::UserAdmin for the
  add_form/add_fieldsets/get_form/get_fieldsets pattern.

files:
  - path: src/backend/apps/users/admin.py
    targets:
      - type: class
        name: UserAdmin
      - type: attribute
        name: readonly_fields
        note: "amend - keep the 3 existing entries, add the inert-but-visible set, NEVER add password"
      - type: method
        name: has_add_permission
        note: "reference only - body must stay byte-identical (15-AUTHZ-003)"
      - type: method
        name: has_change_permission
        note: "reference only - body must stay byte-identical (15-AUTHZ-003)"
      - type: method
        name: has_delete_permission
        note: "reference only - body must stay byte-identical (15-AUTHZ-003)"
      - type: method
        name: has_view_permission
        note: "reference only - body must stay byte-identical (15-AUTHZ-003)"
      - type: method
        name: withdraw_consent_action
        note: "reference only - body must stay byte-identical (PII-107)"
    semantic_anchors:
      insert_before:
        type: method
        name: has_add_permission
      replace:
        type: attribute
        name: readonly_fields
  - path: src/backend/apps/users/tests/test_admin_pii_containment.py
    targets:
      - type: module
        name: test_admin_pii_containment
      - type: function
        name: test_login_token_list_display_masks_telegram_id
        note: "last function in the module - insert after it"
    semantic_anchors:
      insert_after:
        type: function
        name: test_login_token_list_display_masks_telegram_id
  - path: src/backend/apps/users/tests/test_admin_change_form.py
    targets:
      - type: module
        name: test_admin_change_form
        note: "NEW module - the first admin-view test in the repository"

changes:
  - action: add_code
    description: >
      On UserAdmin add, in this order: form = django.contrib.auth.forms.UserChangeForm;
      fieldsets = the change-view contract from the partition table; add_form =
      django.contrib.auth.forms.UserCreationForm; add_fieldsets = (None,
      {"classes": ("wide",), "fields": ("username", "telegram_id", "chat_id",
      "password1", "password2")}); amend readonly_fields; add get_form(self, request,
      obj=None, **kwargs) substituting self.add_form when obj is None; add
      get_fieldsets(self, request, obj=None) returning self.add_fieldsets when obj is
      None. Mirror django/contrib/auth/admin.py::UserAdmin verbatim in shape.
    code_hint: |
      from django.contrib.auth.forms import UserCreationForm, UserChangeForm

      class UserAdmin(admin.ModelAdmin):
          form = UserChangeForm
          add_form = UserCreationForm
          fieldsets = (
              (None, {"fields": ("username", "password")}),
              ...
          )
          add_fieldsets = (
              (None, {"classes": ("wide",), "fields": ("username", "telegram_id", "chat_id", "password1", "password2")}),
          )

          def get_form(self, request, obj=None, **kwargs):
              defaults = {}
              if obj is None:
                  defaults["form"] = self.add_form
              defaults.update(kwargs)
              return super().get_form(request, obj, **defaults)

          def get_fieldsets(self, request, obj=None):
              if not obj:
                  return self.add_fieldsets
              return super().get_fieldsets(request, obj)
  - action: modify_test
    description: >
      Add module-level tests 1-5 to test_admin_pii_containment.py and create
      test_admin_change_form.py with tests 6-11 plus a module-local staff_user fixture
      (is_staff=True, is_superuser=False) and a module-local superuser fixture
      (is_staff=True, is_superuser=True). Do NOT add a fixture to src/backend/conftest.py
      or create apps/users/tests/conftest.py.

traps:
  - "NEVER express a hidden field via UserAdmin.exclude or form.Meta.exclude when fieldsets names it: get_form() passes both, fields_for_model drops it, and helpers.Fieldline.__iter__ then builds AdminField -> form[field] -> KeyError -> 500. readonly_fields is the ONLY correct mechanism for displayed-but-inert."
  - "NEVER put password in readonly_fields. get_form()'s new_attrs = dict.fromkeys(f for f in readonly_fields if f in self.form.declared_fields) sets the declared field to None, DeclarativeFieldsMetaclass pops it, password leaves base_fields, and AdminReadonlyField.contents() loses its getattr(widget, 'read_only', False) short-circuit - so display_for_field returns the RAW HASH into the page. Under option A password must stay a declared, disabled field."
  - "A fieldsets entry naming a field the model does not have raises FieldError from get_form() -> EVERY add and change request 500s. Re-read User._meta.get_fields() immediately before writing fieldsets; is_active is conditional on G-5a (omit it entirely if G-5a = option B RemoveField)."
  - "add_form and add_fieldsets are NOT ModelAdmin attributes. Django's own UserAdmin declares them as plain class attributes and honours them ONLY through the get_form()/get_fieldsets() overrides. Writing add_form without the override is a silent no-op."
  - "get_fields() is NOT consulted for form construction when fieldsets is declared - get_form() derives fields from flatten_fieldsets(get_fieldsets(...)). get_fields() short-circuits on if self.fieldsets."
  - "list_display / list_filter / search_fields resolve from the MODEL, never from the form. Removing a field from fieldsets breaks none of them; telegram_id stays searchable without being in the form. Do not reorder list_display - its first entry is the row link."
  - "readonly_fields + search_fields is NOT a conflict. get_form() never consults search_fields; LoginTokenAdmin already declares both."
  - "The existing module-local staff_user fixtures pass password='x' in PLAINTEXT. A check_password assertion against such a user is vacuously true. Build the target with set_password(<known raw>) and assert check_password(known_raw) is True BEFORE the POST."
  - "No admin:auth_user_password_change URL exists. The ReadOnlyPasswordHashWidget's 'Reset password' button resolves to ../password/ and 404s. That is a DECIDED, RECORDED outcome - do not add get_urls() or change_password_form."
  - "config/urls.py is read-only here. It registers only path('admin/', admin.site.urls)."
  - "Do not edit config/settings/test.py::PASSWORD_HASHERS (phase 02 owns it), conftest.py, or any .po file."
  - "No makemessages / compilemessages run: every new string is Django's own catalog, not a project msgid."

acceptance_criteria:
  - "check_password(plaintext) is False AND the stored hash is byte-identical after a plaintext POST to admin:users_user_change"
  - "the target's check_password(known_raw) is True before that POST (vacuity guard)"
  - "the raw password string and the full stored hash appear nowhere in the change-form HTML"
  - "is_superuser / is_staff / groups / user_permissions are absent from base_fields or disabled"
  - "is_declined / is_deleted / ads_auto_publish / is_banned are absent from base_fields or disabled"
  - "password is never a writable CharField and is never in readonly_fields"
  - "every field in UserAdmin.fieldsets resolves against the live User model - proven by a test that calls get_form()"
  - "admin:users_user_add stores a hashed, confirmed password (check_password(raw) is True, password != raw, has_usable_password() is True)"
  - "a non-superuser moderator gets 403 from admin:users_user_add and cannot set is_superuser through admin:users_user_change"
  - "withdraw_consent_action is still offered by UserAdmin.get_actions(request)"
  - "the five existing *_hides_telegram_id tests pass unchanged"
  - "the four has_*_permission bodies, withdraw_consent_action, list_display, list_filter and search_fields are unchanged"
  - "the commit body reproduces the operator-capability record, including the unban loss"

tests_to_run:
  - src/backend/apps/users/tests/test_admin_pii_containment.py
  - src/backend/apps/users/tests/test_admin_change_form.py
  - src/backend/apps/users/tests/

commands:
  lint: uv run ruff check src/backend/apps/users/admin.py src/backend/apps/users/tests/
  typecheck: uv run basedpyright src/backend/apps/users/admin.py src/backend/apps/users/tests/
  fast_gate: docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml run --rm --env PYTEST_SKIP_MARKERS=seed test
  after_db_restart: docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml run --rm -e PYTEST_OPTS="--create-db --tb=short -n auto --maxprocesses=4 --dist loadgroup" test
```

#### Validator outcome — `B-01` ACCEPTED (2026-10-01)

**ACCEPTED with required fixes; all five are now applied.** Two commits, both final:
**`a19a0ee`** — *"fix(users): declare the UserAdmin field contract"* (implementation) and
**`83622e0`** — *"test(users): harden the UserAdmin field-contract tests"* (the five
validation fixes). No gate is reopened by this acceptance and no follow-up block is
required for `B-01`. `G-4` remains **CLOSED** on **option A**, unchanged by the outcome.

**The five required fixes, all landed in `83622e0`:**

| # | Fix | Why the Validator required it |
|---|---|---|
| 1 | **Deleted** `test_withdraw_consent_action_remains_available` (test 5 in the list above) | It asserted on `UserAdmin.actions` and therefore **pinned the defect as the expected state** — it passes precisely *because* the action is unreachable, and it points the tripwire the wrong way, so a future fix would turn a green suite red. The correct test now belongs to `B-07` and asserts on `get_actions(request)`, not on the class attribute |
| 2 | Corrected the `fieldsets` name-validation set to `concrete_fields \| many_to_many \| private_fields` | That is the set `ModelAdmin` itself validates against; a looser set passes a bad `fieldsets` entry that raises `FieldError` only at render time |
| 3 | Added a `preferred_city`-writable **anti-vacuity guard** | Every other assertion in the module is satisfied by an empty or wholly-readonly form. Without this the single retained write could be dropped and the whole suite would stay green |
| 4 | Added the `exclude`-plus-`fieldsets` `KeyError` structural guard | Makes the trap that test 4 describes *detectable*, not merely described; `base_fields` assertions alone cannot see it |
| 5 | Recorded the i18n decision (below) | The block introduces admin-visible strings; recording the decision closes the i18n question explicitly instead of leaving it implicit |

**Deviation accepted and PERMANENT — `get_readonly_fields`.** `UserAdmin` overrides
`get_readonly_fields(self, request, obj=None)` and returns the inert-but-visible set
**only when `obj` is set**, instead of carrying a flat `readonly_fields` tuple. The
Validator's reasoning, recorded so it is not re-litigated:

- `ModelAdmin.get_form` extends the form's `exclude` with
  `get_readonly_fields(request, obj)` for **both** views, and `fields_for_model` drops
  excluded names **silently**. A flat `readonly_fields` naming `username` /
  `telegram_id` would therefore strip them from the **add** form — the form
  `add_fieldsets` names those two as writable — and break `telegram_id`/`username`
  persistence on `User` creation.
- It is a **first-class documented `ModelAdmin` hook**, not a framework poke.
- It mirrors `django.contrib.auth.admin.UserAdmin`'s own
  `get_fieldsets` / `get_form` pair: the same "override, don't declare" shape `G-4`
  already chose, applied to the fourth hook of the same family.
- It is **~6 lines**.
- The three alternatives considered — (i) flat `readonly_fields` plus an add-view
  `exclude`, (ii) a custom form with `Meta.exclude`, (iii) a per-view `get_form` that
  rebuilds `exclude` — are all worse. (i) reintroduces the `exclude`-plus-`fieldsets`
  `KeyError` trap this block's own test 4 guards; (ii) creates the repository's **first**
  `forms.py`, against rules 5 and 7; (iii) duplicates `get_form` for a difference one
  hook already expresses.

**Keep this deviation documented. Do not propose removing it.**

**i18n — a known, deliberate gap, and the gate does not see it.** The four `fieldsets`
group headings (`Identity`, `Account state`, `Preferences`, `Audit`) are **English-only
admin-surface labels**, deliberately **not** msgids: the `.po` catalogs are owned by
another agent at the time of writing and this phase may not touch them, so extracting
them would collide with work in flight. **Follow-up for whichever phase owns i18n.**
**Verified, not assumed:** `apps/ads/tests/test_i18n_completeness.py::test_no_hardcoded_visible_text`
scans **templates only** — and its `_collect_template_files` *excludes* the `admin/`
subpath — while `::test_bot_no_hardcoded_messages` AST-scans
**`telegram_bot/handlers/` only**. **Nothing in the repository scans `apps/*/admin.py`.**
The i18n gate is therefore **silent** on these four headings and **will stay silent**:
a future English-only admin string passes it exactly as this one did. **That is a gap in
the gate, not compliance with it.** No `.po` file was edited by this block and none may
be edited to close it.

**Do not re-litigate:** the shipped `get_readonly_fields` hook, the four `fieldsets`
group headings, and the retired `password` write path are correct and accepted.

---

### B-02 — Bootstrap password policy (`AUTH_PASSWORD_VALIDATORS` + `create_admin_user`)

| | |
|---|---|
| **Findings owned** | `04-AUT-005` (policy half), `04-VAL-004` (ordering half) |
| **Depends on** | **`B-01`** — hard, by `04-VAL-004` |
| **Blocks** | `B-06`, `B-11` |
| **Priority** | P1 · **Risk HIGH** — raised from the source plan's MEDIUM |

**Objective.** Ship a real Django password policy and enforce it on the one
password-issuing code path in the repository, so the bootstrap admin cannot be created
with a password the site would reject everywhere else.

**Verified starting state.** `AUTH_PASSWORD_VALIDATORS` is absent from **every** settings
module. `config/settings/test.py` pins `PASSWORD_HASHERS =
["django.contrib.auth.hashers.MD5PasswordHasher"]`.
`src/backend/apps/core/management/commands/create_admin_user.py::Command`:
`add_arguments` declares `--password` as `required=False, default=None` (`D-2`);
`handle` resolves `password = (options["password"] if options["password"] is not None else
os.environ.get("ADMIN_PASSWORD", ""))`, raises
`CommandError("Password cannot be empty. Please provide a valid password.")` on an
empty/whitespace value, opens `advisory_lock(AdvisoryLockId.CREATE_ADMIN, session=True)`
and then returns early on an existing `telegram_id`, an existing `username`, and
`--dry-run` — **three early returns before the create** — then calls
`User.objects.create(...)`, `user.set_password(password)`, `user.save()`,
`logger.info(...)` and writes a `SUCCESS` line. **No command test module exists for
`create_admin_user`.**

**Scope.**

| Path | Symbol | Change |
|---|---|---|
| `src/backend/config/settings/base.py` | `AUTH_PASSWORD_VALIDATORS` | add; one comment per validator saying what it enforces |
| `src/backend/apps/core/management/commands/create_admin_user.py` | `Command.handle` | run `validate_password` against the candidate **before** `User.objects.create` |
| `src/backend/apps/core/tests/test_create_admin_user.py` | module | new |

**Corrected anchor (`D-2`).** The source plan's
`insert_after: {function_call: options.__getitem__}` **does not resolve** — `handle` uses
a conditional-expression subscript arm, and no such call exists. Use
`insert_before: {function_call: User.objects.create}` inside `Command.handle`: the only
position **after all three early returns**, which is what makes the skip-if-exists trap
harmless. **Any earlier position turns a bootstrap no-op into a `CommandError`.**

**Corrected risk (MEDIUM → HIGH, with live evidence).**
`docker-compose.yml::create_admin` `depends_on: load_catalog:
service_completed_successfully`; `web`, `bot` and `seed` depend on **`load_catalog`, not
`create_admin`** — so a policy failure does **not** stop the web service. Real impact:
**the environment comes up with no admin user at all**, and `docker compose up` reports a
failed service. `docker/entrypoint-create-admin.sh` runs `set -euo pipefail` and `exec`s
the command, so a `CommandError` exits non-zero. Operational-availability change, not
web-availability — and still HIGH, because "no admin exists" is discovered at the moment
it is needed.

**Binding on the validator shape (`D-6`).** If the minimum length becomes
env-configurable, `config/settings/tests/test_env_allowlist_reverse.py::test_consumed_env_vars_are_allowlisted`
fails unless the name lands in `base.py::ALLOWED_ENV_VARS` **and** in `.env.example`,
`.env.dev.example`, `.env.prod.example`, `.env.test.example` in the **same commit**.
Prefer a literal `MinimumLengthValidator(min_length=N)` to avoid the coupling —
recorded as a recommendation, not a decision (`G-5`).

**Out of scope.** `docker/entrypoint-create-admin.sh` (phase 02 `CFG-003` owns the
`ADMIN_PASSWORD` path) · the `ADMIN_PASSWORD` resolution expression · any validation
added to the bot · `UserCreationForm` (that is `B-01`'s, under its option (c) only).

**Tests required** (`src/backend/apps/core/tests/test_create_admin_user.py`, new).

1. `test_weak_password_is_rejected` — a password below the policy raises `CommandError`
   and **creates no `User` row**.
2. `test_strong_password_creates_the_admin` — user created, `check_password` `True`.
3. `test_existing_telegram_id_skips_without_validating` — an existing row returns the
   existing WARNING and raises nothing. **This is the skip-if-exists trap; it fails
   first if the validator sits above the early returns.**
4. `test_existing_username_skips_without_validating` — same for the username arm.
5. `test_empty_password_raises_the_existing_error` — the message `"Password cannot be
   empty. Please provide a valid password."` is unchanged.

**Gates.** `G-5` — which validators, and literal versus env-configurable length.

**Agents.** Implementor **yes** · Planner **yes** (the validator set is a policy choice,
not a mechanical one) · Validator **yes** (raises MEDIUM→HIGH and touches a
startup/deploy path) · Auditor **no** and Researcher **no** — **deviation, justified:**
no external or behavioural uncertainty remains; the code surface is six statements in
one function plus one settings declaration, and the code context already priced the real
blast radius (which this Planner then corrected, §A.5). The source plan assigned all
four because it had not verified the compose dependency chain.

**Risks.** Validator above an early return → a no-op bootstrap becomes a failure
(tests 3, 4) · an over-strong default breaks an existing operator's documented password
(`G-5`; state the number in the commit body) · `MD5PasswordHasher` in `test.py`
interacts with `validate_password` (the policy is orthogonal to hashing, but the new
tests must pass under the test hasher) · the env-var variant trips
`test_env_allowlist_reverse.py` (`D-6`).

**Rollback.** Delete the `AUTH_PASSWORD_VALIDATORS` declaration and the validation block.
Both additive. Recovering an account after a failed bootstrap is an operational step:
`ADMIN_PASSWORD=<pw> python src/backend/manage.py create_admin_user --username <u>
--telegram-id <id>`.

**Definition of done.** Tests 1–5 green · `test_settings_defaults.py`,
`test_env_allowlist_reverse.py`, `test_env_allowlist.py` green · the `ADMIN_PASSWORD`
resolution expression and `docker/entrypoint-create-admin.sh` unchanged ·
`ruff`/`basedpyright` clean · `04-VAL-004` recorded: `B-01` landed first.

**Implementor brief.**

```yaml
id: 04-b02-bootstrap-password-policy
title: Ship AUTH_PASSWORD_VALIDATORS and enforce them in create_admin_user
priority: high
depends_on: [04-b01-admin-field-contract]
source_reference: .ai/plans/04-auth-login-remediation.md
source_section: BLOCK 2 — AUTH_PASSWORD_VALIDATORS + create_admin_user
source_blocks: ["BLOCK 2", "04-AUT-005", "04-VAL-004"]
description: >
  Add AUTH_PASSWORD_VALIDATORS to base.py with one comment per validator, and validate
  the resolved candidate password in create_admin_user::Command.handle before the user
  row is created.
goals:
  - "weak bootstrap password raises CommandError and creates no user"
  - "an existing telegram_id or username still returns the skip warning with no validation"
  - "no transaction.atomic added; no change to the ADMIN_PASSWORD resolution"
  - "validator minimum is a literal unless G-5 chose env-driven"
extra_context: "All binding constraints for this block are stated in the prose above (Verified starting state / Corrections applied / Out of scope). Read them before editing."
files:
  - path: src/backend/config/settings/base.py
    targets:
      - type: setting
        name: AUTH_PASSWORD_VALIDATORS
  - path: src/backend/apps/core/management/commands/create_admin_user.py
    targets:
      - type: method
        name: handle
    semantic_anchors:
      insert_before:
        type: function_call
        value: User.objects.create
  - path: src/backend/apps/core/tests/test_create_admin_user.py
    targets:
      - type: module
        name: test_create_admin_user
changes:
  - action: add_code
    description: >
      Declare AUTH_PASSWORD_VALIDATORS in base.py with one comment per validator.
      In Command.handle call django.contrib.auth.password_validation.validate_password
      on the resolved candidate, converting ValidationError to CommandError, placed
      immediately before User.objects.create.
acceptance_criteria:
  - "weak password -> CommandError, zero User rows created"
  - "existing telegram_id -> existing WARNING, no exception"
  - "existing username -> existing WARNING, no exception"
  - "empty password -> the existing message unchanged"
  - "test_env_allowlist_reverse.py and test_env_allowlist.py green"
tests_to_run:
  - src/backend/apps/core/tests/test_create_admin_user.py
  - src/backend/config/settings/tests/test_settings_defaults.py
  - src/backend/config/settings/tests/test_env_allowlist_reverse.py
```

---

### B-03 — Login-token browser binding (`04-AUT-001`)

| | |
|---|---|
| **Findings owned** | `04-AUT-001`, `04-VAL-003`, `04-VAL-007` |
| **Depends on** | **`B-05`** only for the migration number (soft — §C.1 scenario alpha already orders it first, and `G-5a` = (A) creates **no** migration) |
| **Blocks** | `B-04`, `B-07` |
| **Priority** | P0 · **Risk MEDIUM-HIGH** |
| **Gates** | **`G-1` CLOSED** — option **A′** · **`G-1a` CLOSED** — fail closed, new `ConsumeOutcome.UNBOUND`, HTTP **410** · **`G-1b` CLOSED** — session cookie, durable for the whole 300 s handshake and deliberately not longer · **`G-1c` CLOSED** — `RETURNING_COLUMNS` is the *single source of the SQL*, plus a two-half test · **`G-1d` CLOSED** — **sixteen** rewrite sites, **not twelve** (see "Corrected test count" below) · **`G-1e` CLOSED** — `login_issue`'s **body** may change, its **decorators** may not · **`G-1f` CLOSED** — verified against Django 5.2.17; the cookie-refusing case is **not** purely legacy, which changes `G-1a`'s answer · **`G-1g` CLOSED PARTIAL** — two documentation surfaces ship in this commit, `privacy.html` is deferred with a written-out owned follow-up · **`G-1h`** — a **Validator re-banding of `04-AUT-001`'s stated rationale is Owed, and is explicitly NOT a precondition** |

**All gates in this block are closed. `B-03` may start.**

**Objective.** Bind a login token to the browser that requested it, so a raw token that
leaks — through a shared device, a stolen value, a prefetching link previewer, or an
in-app browser on the same device — cannot be redeemed from a browser that did not
request it.

**CORRECTION to this block's own Objective, recorded 2026-10-01 by the B-03 Planner.**
The previous text justified the defect with *"(browser history, `Referer` leak, shared
device)"*. **The `Referer` half is not supported by the live code and is struck.**
Verified: the token is **never in a URL** — `login_status` is `@require_POST` and the
token arrives in the POST body (`users/login_issue.html` builds a `FormData` and
`fetch`es with `X-CSRFToken`); `docker/nginx/nginx.conf` and `nginx.dev.conf` set
`Referrer-Policy: strict-origin-when-cross-origin` in **three** locations each; and
Django's default `SECURE_REFERRER_POLICY` is `"same-origin"` even with nginx bypassed.
**A binding cookie does not improve the `Referer` position, and it is not claimed to.**
The two live vectors that remain — and which this block closes — are a **shared device**
and a **stolen raw value**. See `G-1h`.

#### Researcher findings — verification verdicts (all re-checked live at `83622e0`)

| Id | Claim | Verdict |
|---|---|---|
| `F-1` | The plan's `RETURNING` risk is **backwards**; the real risk is a **silent** binding loss | **CONFIRMED at the source.** `django/db/models/base.py::Model.__init__` iterates the **model's** fields and does `kwargs.pop(field.attname)` inside `try` / `except KeyError: val = field.get_default()`. A stale `RETURNING` therefore produces a **default-valued attribute, with no exception**. `TypeError` fires only in the opposite direction (a `RETURNING` name the model lacks). See `G-1c`. |
| `F-1` | `strict=True` is vacuous; order divergence is a consistency requirement, not correctness | **CONFIRMED.** `columns` and `row` both come from one `cursor.execute`, so `zip(..., strict=True)` raises `ValueError` and never fires; `dict(zip(...))` discards order and `LoginToken(**d)` is keyword-only. The plan's *"exactly **and in order**"* is therefore a **consistency** contract, restated as such in `G-1c`. |
| `F-2` | The direct-row test count is **twelve**, not nine | **CONFIRMED, AND UNDERSTATED.** Twelve is right for `test_login.py` + `test_consent.py`. **`test_login_token.py` adds four more sites the plan never named** — see "Corrected test count". |
| `F-3` | `login_issue` is **not** cookie-less | **CONFIRMED.** `users/login_issue.html` interpolates `{{ csrf_token|escapejs }}`, and `CsrfViewMiddleware.process_response` then emits `Set-Cookie: csrftoken`. This **weakens** the plan's stated cost for `A″`/`B`; see `G-1`. |
| `F-4` | The `Referer` rationale is unsupported | **CONFIRMED.** Folded into the Objective correction above and into `G-1h`. |
| `F-5` | The `secrets` tripwire is satisfiable without weakening it | **CONFIRMED.** `login_token.py` already imports `secrets` and already calls `secrets.token_urlsafe(RAW_TOKEN_ENTROPY_BYTES)`, so the browser-id mint belongs there and is returned in the existing `IssuedToken`. `consent.py` already imports from `apps.users.services.login_token` (lowercase), so the substring `LoginToken` does **not** appear; importing the **model** would break the tripwire and is forbidden. |
| `F-6` | `A″` and `B` carry a quantified session-growth vector | **CONFIRMED.** `clearsessions` appears **nowhere** in the repository; `SESSION_ENGINE`, `SESSION_COOKIE_AGE` and `SESSION_SAVE_EVERY_REQUEST` are **unset** in every settings module (DB backend, 14-day default, write-triggered refresh). Ingress is bounded at `login_rate_limit_check`'s `RATE_LIMIT_REQUESTS = 10` / `RATE_LIMIT_PERIOD = 60` per IP → **~14,400 `django_session` rows per IP per day**, retained 14 days, on an endpoint that requires **no credential**. Decisive in `G-1`. |
| `F-7` | Cookie conventions and the `delete_cookie()` `Secure` quirk | **CONFIRMED.** `SESSION_COOKIE_SECURE/HTTPONLY/SAMESITE` = `True/True/"Lax"` in `base.py` (only `SECURE` is dropped in `dev.py`/`test.py`). `django/http/response.py::HttpResponse.delete_cookie` emits `secure=True` **only** for `__Secure-`/`__Host-` prefixed names or `samesite="none"`. First-party patterns: `consent.py::_set_consent_cookie` (`max_age`, `httponly=True`, `samesite="Lax"`, `secure=True`) and `apps/search/views/preferred_city.py::set_preferred_city` (`httponly=True`, `samesite="Lax"`, `secure=request.is_secure()`, `path="/"`, plus a **hand-rolled expired-cookie form**). |
| `F-8` | `A′` creates a `privacy.html` disclosure obligation | **CONFIRMED AND WIDENED.** `templates/privacy.html` carries an explicit **7-row** cookie-inventory `<table>` with Essential / Consent-Gated columns. `apps/core/tests/test_privacy.py::TestPrivacyPage::test_privacy_page_lists_cookies` asserts a **hard-coded 5-name allowlist** (`sessionid`, `csrftoken`, `consent_given`, `lang_pref`, `preferred_city`) — it does **not** check completeness, and it already omits two cookies the table *does* list. **Nothing fails if the row is forgotten.** `docs/02-database/db-enums.md`'s `CookieCategory` section is a **second** disclosure surface naming `sessionid, csrftoken` as the always-on essential cookies. See `G-1g`. |
| `F-9` | The plan cites a test file that does not exist | **CONFIRMED.** `§D.1`'s phase-15 coordination detection names `apps/users/tests/test_login_issue_template.py`; the only such module is **`apps/core/tests/test_login_issue_template.py`**. **`§D` is outside this Planner's file surface, so the correction is recorded here and `§D.1` must be read with it.** That module holds three pure file-level assertions (`test_login_issue_template_no_cleartext_bot_username`, `…_uses_telegram_deep_link`, `…_does_not_hide_deep_link_on_load`) — **none is affected by this block**, and no template changes here. |

**Verified starting state.** `src/backend/apps/users/services/login_token.py`:
`TOKEN_TTL_SECONDS = 300`, `RAW_TOKEN_ENTROPY_BYTES = 24`,
`ConsumeOutcome(StrEnum)` = `NOT_FOUND | GONE | PENDING | LOST_RACE | CONSUMED`,
`ConsumeResult`, `IssuedToken`, `_hash_raw_token`,
`issue_token() -> IssuedToken` (**no arguments**; creates the row with only `token_hash`
and `expires_at` — `telegram_id` stays `NULL` until the bot claims it),
`claim_token(token_hash, telegram_id, now) -> LoginToken | None` (single-statement
`UPDATE ... RETURNING`; docstring: *"This function opens no `atomic()` of its own — the
caller (`handle_login_orm`) keeps the claim inside its single outer
`transaction.atomic()`"*), `consume_token(raw_token) -> ConsumeResult`.
`claim_token`'s `RETURNING id, token_hash, telegram_id, created_at, expires_at,
consumed_at` matches `LoginToken._meta.concrete_fields` attnames **exactly and in order**
(verified from `apps/users/models.py::LoginToken`'s declaration order — `id` is the
implicit PK, then `token_hash`, `telegram_id`, `created_at`, `expires_at`, `consumed_at`;
`columns = [desc[0] for desc in cursor.description]` → `LoginToken(**dict(zip(columns,
row, strict=True)))`).
`src/backend/apps/users/views/consent.py::login_issue`: `@never_cache` only — **no
`@require_POST`, no `@login_required`** — calls `check_deep_link_render_rate_limit`, then
`login_rate_limit_check`, then `issue_token()`, then renders `users/login_issue.html`. **It
never touches a session object**, but it *does* cause a `csrftoken` cookie to be set
(`F-3`). `login_status`: `@require_POST` **and** `@never_cache`; it is the **only** view in
this file that opens a `transaction.atomic()`. **The mechanism behind `X-13`, verified:**
`login_issue` is anonymous;
`apps/core/middleware/language.py::LanguagePreMiddleware._apply_lang_param` is the only
backend session write and is gated on `request.user.is_authenticated`, so it never fires
here; `SessionBase.session_key` is a plain property returning `None` until
`save()`/`cycle_key()`. **`request.session.session_key` is `None` on the only path that
matters.** Bot: `src/telegram_bot/handlers/login.py::handle_login_orm(token_hash, telegram_id,
username, first_name, last_name)` calls **`claim_token(token_hash, telegram_id, now)`** and
**must not be asked to supply a binding**. `apps/users/admin.py::LoginTokenAdmin` declares
`has_add_permission → False` and `has_change_permission → False` unconditionally, so **no
form is ever rendered and a new column reaches no admin surface** (`C-12` — the
`LoginTokenAdmin` coordination task stays **dropped**; its `readonly_fields` list does not
need extending, because with both permissions `False` it is never consulted for rendering,
and `list_display` / `list_filter` / `search_fields` do not enumerate the field set).

**Correction to `C-2` as a phase-exit condition.** `§A.4`'s `C-2` row and the module
docstring both claim that a stale `RETURNING` "raises `TypeError`". **Both are wrong** —
see `F-1` and `G-1c`. The **module docstring's** `RETURNING` / model-shape section is
rewritten **in this commit**, because leaving a factually inverted contract in the file
that owns the token lifecycle is how the next implementor repeats the error. The
`AUT-007` boundary section of the same docstring is **`B-04`'s** and is **not** touched.

#### `G-1` — CLOSED: **option A′**

**Chosen: a `LoginToken.browser_binding` column + a first-party `login_browser_id`
cookie, with the mint delegated to the service.** The column stores the **SHA-256 hex
digest** of the browser id; the raw browser id exists only in the cookie and in
`IssuedToken`. `consume_token` requires the presented browser id to digest to the stored
value.

**Why the raw value is not stored.** `docs/02-database/db-schema.md` states as a
table-level property of `login_tokens` that the raw token is *never* stored, and this
module's own docstring says *"Web-side hashing lives here and nowhere else."* Storing the
digest keeps that invariant uniform across the table instead of exempting one column, costs
one `hashlib` call in a module that already imports `hashlib`, and means a leaked database
row hands over no usable cookie value. The binding is a **correlator, not an
authenticator** — the 192-bit raw token remains the only authenticator — so an unkeyed
SHA-256 digest is the correct, proportionate construction.

**Why A″ and B are dominated — the argument, quantified.** Both write a session row on
`login_issue`, an endpoint that requires **no credential** and is bounded at
`RATE_LIMIT_REQUESTS = 10` / `RATE_LIMIT_PERIOD = 60` **per IP**. Every one of those ten
writes marks the session modified, so `SessionMiddleware` saves it — **~14,400 rows per IP
per day**, retained for the 14-day default, with **no janitor** (`clearsessions` appears
nowhere in the repository; not in `HOURLY_COMMANDS`, not in `DAILY_COMMANDS`, not in any
entrypoint). That alone makes `django_session` the largest table in the system, bought for
a binding. And it buys **no additional security**, because
`django.contrib.auth.login` **already** rotates the session key before writing
`_auth_user_id` — `flush()` when a `SESSION_KEY` is already present, `cycle_key()`
otherwise — so classic identity session-fixation is **not** introduced by a pre-login
session. Therefore:

- **`A″` is strictly dominated.** It costs **everything `A′` costs** (the migration, the
  `RETURNING` edit, the schema contract, the `db-schema.md` edit) **and adds** the
  session-growth vector **and buys nothing extra**. Worse, its binding is **destroyed by
  any `flush()`** inside the 300 s window — which `login_status` itself triggers via
  `auth_login`. A binding that the redeem step deletes is not a binding.
- **`B` is dominated by the same vector with no offsetting benefit** — it saves the
  migration and the `RETURNING` edit, and pays ~14,400 rows/IP/day for them, plus the same
  flush fragility. Its only saving is one file; the plan already prices correctness and
  growth above diff size, and the phase's risk register treats a session-store choice here
  as a MEDIUM availability risk.
- **`C` is rejected, not merely disfavoured.** It leaves `04-AUT-001` **open** behind a
  green suite, which §F.1 names as *"the dominant failure mode of `B-03`"* and §F.2 row 1
  rates **High**. A silent `C` is not available without a loud recorded re-banding of the
  finding to *accepted-risk*, and no such re-banding exists. **`C` is therefore withdrawn
  from the option set**, not carried as a fallback.

**What `A′` costs, stated plainly:** one additive nullable column; one additive
migration; one new first-party essential cookie (name, `HttpOnly`, `SameSite=Lax`,
`Secure`, `path=/`, no `max_age`); one new `ConsumeOutcome` member; one added predicate in
the consume `UPDATE`; **sixteen** test rewrite sites in the same commit; two documentation
surfaces; and **one deferred ePrivacy disclosure row** (`G-1g`).

#### `G-1a` — CLOSED: **fail closed**, `ConsumeOutcome.UNBOUND`, HTTP `410`

**Policy: a `LoginToken` row whose `browser_binding IS NULL` is **never** redeemable, and
a presented browser id that is absent or malformed is refused the same way. Both produce
the new `ConsumeOutcome.UNBOUND = "unbound"`, which `login_status` maps to `410` with a
**distinct log reason**.

**`G-1f` is settled first, because it changes this answer — and it does.** The Researcher's
precondition was that a cookie-refusing client *already* cannot complete login today,
because the poll POST needs `csrftoken`. **Verified against Django 5.2.17 at
`django/middleware/csrf.py`:** `CsrfViewMiddleware` **is** in `MIDDLEWARE` (position 7 of
15), `_check_token` calls `_get_secret(request)`, a missing/unusable `csrftoken` cookie
raises `InvalidTokenFormat` → `RejectRequest(REASON_NO_CSRF_COOKIE)` → **403**. So a client
that refuses **all** cookies indeed cannot poll — but that does **not** collapse the case,
because CSRF is satisfied by the `csrftoken` cookie **plus** the `X-CSRFToken` header, and
a client can accept `csrftoken` while **selectively** refusing or losing a *newly
introduced* cookie name: a per-cookie enterprise policy, a Safari ITP eviction, cookie-jar
eviction under storage pressure, or a user clearing only that cookie. **The `NULL`-binding
population is therefore NOT purely legacy — it also contains live users.** Fail-closed is
the right answer for that population; fail-open would hand a browser-refuser a complete
login, which is the exact bypass the block exists to remove.

**Fail-open was considered and rejected** (including the hybrid "fail-open only for legacy
`NULL` rows"). A fail-open default means *any* future writer that forgets the binding
silently restores the vulnerability, and the phase's own dominant failure mode is a green
suite over a non-fix. Its only benefit — leaving three `test_login_token.py` assertions
untouched — is a test convenience, and project rule 2 (*production code is king*) settles
that direction.

**Why the HTTP code stays `410` and only the *outcome* is new.** `users/login_issue.html`'s
polling loop branches on exactly three codes — `200`, `204`, `410` — and does nothing for
any other status (no `clearInterval`, no message), so a new HTTP status would silently
leave the loop spinning until natural expiry. `410` needs **no template change and no new
translatable string**, and the existing `410` copy — *"This login link is invalid, expired,
or already used."* — is already honest for a binding refused by the browser. The distinct
information lives in the **service's** `ConsumeOutcome` and in the **log reason**, where a
test can assert on it. A `StrEnum` member is the convention-fitting move and costs no i18n.

**Adding a member to `ConsumeOutcome` is safe for the existing assertions — verified.**
`test_login_token.py` references exactly four members (`NOT_FOUND`, `GONE`, `PENDING`,
`CONSUMED`) by identity (`is`) plus one `.value == "consumed"`; `consent.py` compares
against four members by `is`. **No assertion enumerates the members and none asserts a
count**, so a sixth member cannot break any of them. The only code that must learn the new
member is `login_status`, which is in this block's file surface.

**Degradation cost, stated for the commit body:** at deploy time every token issued in the
preceding ≤300 s has `browser_binding IS NULL` and becomes unredeemable. A user mid-handshake
sees the `410` message and re-navigates `/login/issue/`, which mints a fresh bound token.
**One-time, ≤5 minutes, no data loss, no security exposure, self-healing on retry.** A
browser that selectively refuses the cookie has the same one-retry path.

#### `G-1b` — CLOSED: **a session cookie — durable for the whole 300 s handshake, deliberately not longer**

The cookie is set with **`httponly=True`, `samesite="Lax"`, `secure=True`, `path="/"` and
**no `max_age`** (a session cookie). Statement: the binding **is** durable across the entire
300 s two-phase window — a session cookie outlives any single page view, the Telegram
round-trip and the 3 s polling interval by a very wide margin, and it is not touched by
`login_status`'s `auth_login` (a **session** cookie is unaffected by `cycle_key()`/
`flush()`, which rotate the *session id*, not the cookie jar). It is **deliberately not
durable longer**, for three reasons: the row it binds lives at most 300 s, so a longer
cookie is pure retention with no security value; a session cookie is the minimal-retention
form and is the least objectionable thing to add to the `privacy.html` inventory; and
`B-04`'s "prior outstanding tokens for the same browser" also lives only ≤300 s, so the
`B-03 → B-04` edge is fully served.

**Consequence recorded, not hidden:** a browser that closes and reopens mid-handshake loses
the cookie and the token 410s. Recovery is one re-navigation of `LOGIN_URL`.

**No clearing on decline — decided, and it removes a whole class of trap.** The cookie is
`HttpOnly`, so JavaScript cannot clear it, and **that is correct**: it is essential security
state, not consent-gated state. `consent_decline` does **not** clear it. Consequently
**this block contains no `delete_cookie()` call at all.**

**Forward trap, recorded because it is a known Django 5.2 trap:** if a later block ever
needs to clear this cookie, `HttpResponse.delete_cookie()` emits `secure=True` **only** for
`__Secure-`/`__Host-` prefixed names or `samesite="none"` — for any other name it emits
`secure=False`, which does **not** match the cookie that was set, and the browser ignores
the delete. The remedy already exists in the repository: the **hand-rolled expired-cookie
form** used by `apps/search/views/preferred_city.py::set_preferred_city`.

#### `G-1c` — CLOSED: `RETURNING_COLUMNS` is the single source of the SQL, and the test has **two** halves

**The real risk, replacing the plan's inverted one (`F-1`).** Adding a column to
`LoginToken` **cannot** raise `TypeError`. `Model.__init__` iterates the **model's** fields
and pops each attname inside a `try`, falling back to `field.get_default()` on `KeyError`
— so a stale `RETURNING` produces a **default-valued attribute and no error**. Because
`RETURNING` is literal SQL and a new column never *adds* a `RETURNING` name, a forgotten
update means **the bot path silently loses the binding on every claim with a fully green
suite.** `TypeError` fires only in the opposite direction — a `RETURNING` name the model
lacks. Severity **MEDIUM-HIGH**, type **silent**. `strict=True` is vacuous (both sequences
come from one `cursor.execute`) and order divergence is a consistency requirement, not a
correctness one.

**Mechanism — accepted from the Researcher, with one mandatory amendment.** The service
exports `RETURNING_COLUMNS: Final[tuple[str, ...]]`, **and the SQL is built from it**
(`"… RETURNING " + ", ".join(RETURNING_COLUMNS)`). *This is the amendment.* A constant that
merely sat **beside** a hand-written literal `RETURNING` list would let the constant match
the model while the SQL still returned a stale list — the test would then pass over exactly
the defect it exists to catch. Interpolating the constant is what makes the test transitively
cover the SQL. The interpolated value is a module `Final` tuple of identifiers, never user
input.

**The test — `test_login_token.py::TestClaimToken::test_claim_token_returning_matches_model_fields`,
three assertions, in one commit.** A behavioural "no exception occurs" assertion is
worthless here by construction, so every assertion is discriminating:

1. **`set(RETURNING_COLUMNS) == {f.attname for f in LoginToken._meta.concrete_fields}`** —
   the **security** assertion. This is what catches the **silent** case: a model column
   absent from the list. Named as such in the failure message.
2. **`tuple(RETURNING_COLUMNS) == tuple(f.attname for f in LoginToken._meta.concrete_fields)`**
   — the docstring's **order** contract. Documented in the assertion's message as a
   *consistency* obligation, not a security one; failing it is resolved by reordering the
   SQL, which is free.
3. **The round trip** — issue via `issue_token(browser_id=<known>)`, claim via
   `claim_token(...)`, then assert the returned instance's binding attname is **not `None`**
   **and** equals the stored value. This is the half that catches a *behavioural* loss
   (a refactor that returns a fresh or partial instance) which set-equality alone would
   pass. **Without this half the test is half a test.**

**Adding to `TestClaimToken` is not weakening it.** `TestLoginHandshakeOwnership` stays
**unedited**; the new test is a new member of a different class.

#### `G-1d` — CLOSED: every rewrite site lands in **this** commit

`§E`'s governing rule is that a test change lands in the **same commit** as the production
change it follows. **Confirmed: all rewrite sites below are in `B-03`'s single commit.**
`B-04` and `B-07` may not carry any of them.

**Corrected test count — SIXTEEN rewrite sites, not twelve.** The plan's nine was correct
at `f93e7fb`; `B-05` added three to `test_login.py` (twelve across `test_login.py` and
`test_consent.py`); and **`test_login_token.py` contributes four more the plan never
named**, because `G-1a`'s fail-closed policy changes what `consume_token` returns for a
directly-created row. The Researcher's twelve is a correct floor, not the count.

#### `G-1e` — CLOSED: `login_issue`'s **body** yes, **decorators** no

**The boundary, recorded verbatim for the Implementor.** `B-03` **may**:

- change the body of `login_issue` — specifically the `issue_token(...)` call and adding
  `response.set_cookie(...)` to the `render()` result;
- change the body of `login_status` — specifically the `consume_token(...)` call and one new
  `UNBOUND` branch;
- add the new import line for the cookie-name constant.

`B-03` **must not**:

- add `@require_POST` to `login_issue`, or remove or reorder any existing decorator on it
  (`@never_cache` stays, and stays outermost as it is today);
- add a `request.method` branch, an `HttpResponseNotAllowed` path, or any method
  discrimination to `login_issue`;
- change the route in `apps/users/urls.py`, the URL name, or the template
  `users/login_issue.html`;
- add a form to `login_issue`.

**Why the boundary is drawn there.** Phase 15 `15-AUTHZ-004` owns `04-AUT-007`'s
CSRF/POST-only half (§D.6) and will edit the **same function**. A body-only change keeps
the two edits to disjoint regions of the file, so a concurrent phase-15 landing is a
textual conflict at worst and never a semantic one. If phase 15 lands `@require_POST` first,
`B-03` still applies — the decorators are orthogonal to the cookie.

#### `G-1g` — CLOSED PARTIAL: two surfaces ship, `privacy.html` is deferred with the work written out

`privacy.html`'s new row needs a `{% trans %}` description, which needs non-empty `ru` **and**
`bs` msgstr, and **the three `.po` files are owned by another agent right now.** So the row
cannot land in `B-03` without violating that, and **this Planner edits no template and no
`.po` file.**

**What ships in `B-03` (no `.po` dependency):**

- `docs/02-database/db-schema.md` — the `login_tokens` block gains the
  `browser_binding` line and a note that the consume `UPDATE` re-asserts the binding.
  Already required by §C.3; lands in the same commit as the migration.
- `docs/02-database/db-enums.md` — the `CookieCategory` section's parenthetical
  *"(sessionid, csrftoken)"* becomes a list that includes `login_browser_id`. **Plain
  Markdown, no msgid.**

**What is deferred, with the work written out so the follow-up is mechanical** (recorded
here; **not** performed by this Planner):

1. `templates/privacy.html` — add one `<tr>` to the cookie-inventory table, cookie name
   `<code>login_browser_id</code>`, Essential column marked, Consent-Gated column empty,
   description wrapped in `{% trans %}`. That is **one** new msgid.
2. Three `.po` files (`ru`, `bs`, `en`) — one new msgstr each; **`ru` and `bs` must be
   non-empty**, `en` may be empty.
3. `apps/core/tests/test_privacy.py::TestPrivacyPage::test_privacy_page_lists_cookies` —
   add `"login_browser_id"` to the existing tuple. **No new translatable string**, so it is
   not `.po`-blocked — but it **must land with step 1**, because adding it alone leaves the
   fast gate red.

**Trigger and owner.** The follow-up fires as soon as the `.po` owner releases those files,
and must land in **one** commit covering all three steps. **It is recorded as an open
ePrivacy disclosure obligation in `B-03`'s commit body** — because `F-8` is correct that
nothing in the repository will fail if it is forgotten, and a silent compliance gap on a
legal page is exactly the class of defect this phase exists to remove.

**Why not an untranslated row now.** Every other description cell in that table is a
`{% trans %}`; a single English-only row on an `ru`/`bs` legal page is a visible
localization defect, and it is worse than a recorded, owned, one-msgid omission.

#### `G-1h` — the severity question: **close `G-1` now; the re-banding is owed, not a precondition**

**Decision: `G-1` is closed on the security argument as it stands. A Validator re-banding
of `04-AUT-001` is recorded as owed and is explicitly NOT a gate.**

**Why `F-4` does not gate it.** `F-4` removes **one of three** stated rationales (`Referer`),
not the defect. The finding's substance — *a login token issued to one browser can be
redeemed from another* — is independently verified and independently exploitable: the raw
token is a bearer credential rendered into the page (`{{ raw_token }}` and
`data-start="login_…"`), it is redeemable by whoever presents it, `login_issue` is a
**GET that creates state** (so it is prefetchable), and the two live vectors are a shared
device and a stolen raw value. **The remedy is identical under every re-banding that keeps
the finding open at MEDIUM or above.** Gating a P0 security fix on the accuracy of one
sentence in the finding would trade a closed HIGH for an open one indefinitely — which is
the precise inversion §F.2 row 1 exists to prevent.

**What is owed, and to whom.** The **Validator** records a re-banded `04-AUT-001` whose
rationale cites the **shared-device** and **stolen-value** vectors, and explicitly records
that the `Referer` rationale is **not** supported by the live code (`login_status` is
POST-only; `Referrer-Policy` is set at three nginx locations per file; Django's default
`SECURE_REFERRER_POLICY` is `same-origin`). The re-banding changes the *narrative*; the
mechanism, the tests, the migration and this block's DoD are unaffected either way.

**Transaction constraints to preserve (unchanged from the previous text, restated).**
`transaction.atomic()` **must not** be added anywhere inside
`apps/users/services/login_token.py` (it currently has **zero** occurrences — keep it zero;
phase 03 `DB-002`: the service owns the predicate, the caller owns the transaction).
`claim_token`'s signature is **unchanged** and `now` stays a **required caller-computed**
parameter. `login_issue` gains **no** `atomic()`. `login_status`'s existing `atomic()`
block **must not be widened** — and it does not need to be: the binding decision is made on
the `ConsumeResult` already returned inside it, so the new `UNBOUND` branch goes **inside**
the existing block, between the `PENDING` and the `CONSUMED` handling, and adds no query and
no write.

#### `consume_token` — the exact check order (binding, not line position)

The binding gate sits **after** `PENDING` and **before** the `UPDATE`, and is **re-asserted
inside** the `UPDATE`'s filter, so it cannot be lost to a stale read:

1. hash the raw token → `get` → miss = `NOT_FOUND` (**unchanged**);
2. `expires_at <= now` or `consumed_at is not None` = `GONE` (**unchanged**);
3. `telegram_id is None` = `PENDING` (**unchanged** — a browser polling a token it *owns*
   keeps getting `204` while the bot has not claimed);
4. **NEW** — `browser_binding IS NULL`, or the presented browser id is absent/malformed, or
   the two digests differ = **`UNBOUND`** → `410`, **and the token is NOT burned**;
5. `UPDATE … WHERE token_hash = … AND telegram_id = … AND consumed_at IS NULL AND
   expires_at > … **AND browser_binding = <presented digest>**` → `0` rows = `LOST_RACE`
   (**unchanged**), else `CONSUMED` (**unchanged**).

**Why step 4 must precede step 5 — the burn-ordering trap.** `B-05`'s commit body asserts
that a refusal still burns the token ("*the two-phase handshake must restart*") and
`test_login_status_burns_the_token_for_a_disabled_account` asserts it. That property holds
for the **user-state** refusals (`can_login`, the `is_active` guard), which all sit *after*
`consume_token` has already returned `CONSUMED`. **The binding refusal is different and must
NOT burn the token**: an attacker who fails the binding check must not be able to destroy a
legitimate user's in-flight login. That is the assertion in
`test_token_from_another_browser_is_rejected`'s second half, and it is the reason step 4
gates the `UPDATE` rather than following it. Because step 3 precedes step 4, a mismatched
browser polling a **still-unclaimed** token gets `204` — which leaks only *"a token with
this hash exists and is unclaimed"*, knowledge the holder of the raw token already has, and
nothing about the binding.

#### Field and migration shape

**Field — appended to `apps/users/models.py::LoginToken` after `consumed_at`** (declaration
order determines `concrete_fields` order, and `RETURNING_COLUMNS` must match it):

- name: **`browser_binding`**
- type: `models.CharField`
- `max_length=64` — a SHA-256 hex digest, matching `token_hash`
- `blank=True`, **`null=True`**
- `help_text` — states that it is the SHA-256 digest of the issuing browser's
  `login_browser_id` cookie, that the raw id is never stored, and that `NULL` means the row
  predates the binding
- **no `db_index`** — every lookup is by `token_hash`; `B-04` may add its own index if its
  invalidation `UPDATE` filters on it
- **no `choices`, no `StrEnum`** — it is an opaque digest, not a fixed value. (Project rule
  10 governs fixed values; this is not one.)

**`null=True` is load-bearing, not a convenience.** `src/telegram_bot/tests/conftest.py::login_token_factory`
and `TestTokenRejection::test_reject_expired_token` / `test_reject_consumed_token` create
`LoginToken` rows directly with no binding, and **the bot package must stay byte-unchanged**.
A `NOT NULL` column would make all three raise `IntegrityError`. Hence the column is
nullable, and hence **`G-1a`'s fail-closed policy is what makes the design safe** — the
nullable column is the *storage* reality; the fail-closed `UNBOUND` outcome is the
*security* answer to it. The two must be read together.

**Migration — placeholder `<NNNN>_logintoken_browser_binding.py`, `AddField` only.**

> **RE-VERIFY THE NUMBER AT WRITE TIME.** Verified at `83622e0`:
> `src/backend/apps/users/migrations/` contains exactly `0001_initial.py` and
> `0002_alter_consentrecord_ip_address.py`, so the next free number is **`0003`**. `B-05`
> under `G-5a` = (A) creates **no** migration, so nothing in this phase competes for it —
> but phase 06 (erasure columns) and phase 15 (role fields) also write this directory.
> List the directory **immediately before** generating; never assume; never renumber or
> edit an existing migration. The name follows Django's auto-generated
> `<verb>_<model>_<field>` convention — the same shape as the existing
> `0002_alter_consentrecord_ip_address`.

**Service surface — `apps/users/services/login_token.py`.** New: `BROWSER_ID_ENTROPY_BYTES`
(`16` → `secrets.token_urlsafe(16)` → a 22-char URL-safe value, 128 bits — the binding is a
correlator, not an authenticator), `LOGIN_BROWSER_ID_COOKIE` (`"login_browser_id"`), a
`_BROWSER_ID_PATTERN` (needs one `re` import), `_hash_browser_id()`, `RETURNING_COLUMNS`.
Changed: `IssuedToken` gains `browser_id`; `issue_token` gains a **keyword-only,
optional** `browser_id: str | None` (reuses a well-formed presented value, mints otherwise);
`consume_token` gains a **keyword-only, REQUIRED** `browser_id: str | None`; `ConsumeOutcome`
gains `UNBOUND`. Unchanged: `claim_token`'s signature, `TOKEN_TTL_SECONDS`,
`RAW_TOKEN_ENTROPY_BYTES`, `consume_token`'s parameter-asymmetry rationale, the two-phase
predicate asymmetry, the two-deleters rule, the `AUT-007` boundary section.

**Why `consume_token`'s new parameter is REQUIRED and keyword-only, with no default.** A
default would let a future caller silently skip the binding check — the exact
"green tests over a non-fix" shape this block exists to remove. Required means the compiler
finds every call site.

**Why `login_issue` must REUSE, not re-mint.** `login_issue` issues a **fresh token per
page view** and several headless clients prefetch links. If a second issue minted a second
browser id, token #1's row would carry binding A while the cookie now holds binding B, and
token #1 would become unredeemable — which would make login unreliable in exactly the
prefetching browser that needs it. **Reusing a well-formed presented cookie value, and only
minting when the cookie is absent or malformed, is what makes a repeat issue safe.** It is
asserted twice: `test_repeat_issue_does_not_invalidate_the_binding` (behavioural, through
the URL) and `test_repeat_issue_reuses_the_same_browser_binding` (the mint/reuse rule
itself). An attacker-supplied cookie value must **never** be written to the database
unvalidated — hence the shape check.

**Cookie write — one call, in the view, nothing else.** `response = render(request,
"users/login_issue.html", {...})` must be bound to a name (it is currently returned
directly), then `response.set_cookie(LOGIN_BROWSER_ID_COOKIE, issued.browser_id,
httponly=True, samesite="Lax", secure=True, path="/")`. The cookie-name constant is
**imported from the service**, mirroring how `consent.py` imports
`PREFERRED_CITY_COOKIE_NAME` from `apps.core.middleware.preferred_city` — the owner exports
the name. **The view mints nothing and hashes nothing** (`F-5`).

**The `secure=True` choice, and its one recorded caveat.** `_set_consent_cookie` uses
`secure=True` unconditionally, and `db-schema.md` documents first-party cookies as
*"`SECURE` + `HTTPONLY` + `SAMESITE=Lax`"*. Following that pattern is consistent and cannot
be silently downgraded later by a conditional. **Caveat recorded, not shipped:** on a
**plain-HTTP non-localhost dev host in Safari**, a `Secure` cookie is dropped and every
login 410s. The project's own quick start serves on `http://localhost:8000`, which Chrome,
Edge and Firefox treat as a secure context. The one-line remedy, if dev ever needs it, is
`secure=request.is_secure()` exactly as `preferred_city.py` does.

**The `login_issue` log line must NOT change.** `logger.info("Issued login token hash=%s...",
issued.token_hash[:8])` stays byte-identical. **No binding value — raw or digested — is
logged anywhere**, at issue or at redeem.

**Scope.** `apps/users/services/login_token.py` (`issue_token`, `claim_token`,
`consume_token`, `ConsumeOutcome`, `IssuedToken`, the `RETURNING`/model-shape docstring
section) · `apps/users/views/consent.py::login_issue`, `::login_status` ·
`apps/users/models.py::LoginToken` + one `AddField` migration ·
`apps/users/tests/test_login.py`, `test_consent.py`, `test_login_token.py` ·
`docs/02-database/db-schema.md`, `docs/02-database/db-enums.md`.

**Out of scope.** The invalidation half (`B-04`) · **any file under `src/telegram_bot/`,
including its tests** · `@require_POST` / any method branch on `login_issue`
(`G-1e`, phase 15 `15-AUTHZ-004`) · `users/login_issue.html` · `templates/privacy.html` and
the three `.po` files (`G-1g`) · `apps/users/admin.py` (`C-12` — `LoginTokenAdmin` renders
no form) · `config/settings/*` — **no setting is added or changed**, so
`test_env_allowlist_reverse.py` and `test_settings_defaults.py` are untouched · any
`AUT-00N` comment outside the two `B-04` owns.

**Tests required — the complete list for this commit.**

**Structural tripwire, unchanged:** `test_login_token.py::TestLoginHandshakeOwnership::test_consent_view_has_no_token_logic`
— including its **`secrets`** clause. `B-03` must satisfy it, not touch it: the view gains
no `secrets`, no `hashlib`, no `LoginToken` substring, no `"UPDATE login_tokens"`, no
`".update(consumed_at="`. The cookie-name import from `login_token` is safe because that
module path is lowercase.

**In `src/backend/apps/users/tests/test_login.py` — new class `TestLoginTokenBinding`:**

1. `test_token_from_another_browser_is_rejected` — issue in client A, keep A's raw token;
   claim it; redeem in a **second** `Client()` → **410**; **and** the row's `consumed_at` is
   still `None`; **and** A can then redeem the same raw token → **200** + a session. Through
   the real URLs, not a service call. *This is the test that closes `04-AUT-001`, and its
   three assertions are the three ways a binding can be decorative.*
2. `test_same_browser_redeems_end_to_end` — `GET /login/issue/` → claim via
   `apps.users.services.login_token.claim_token` (the **service** call, which is exactly
   what the bot's `handle_login_orm` performs — so the two-process handshake is exercised
   end to end **without importing the bot package**) → `POST /login/status/` → **200** +
   `"_auth_user_id" in client.session`.
3. `test_repeat_issue_does_not_invalidate_the_binding` — two `GET /login/issue/` from one
   client; claim **both**; redeem the **first** → **200**. *Prefetch tolerance.*
4. `test_repeat_issue_reuses_the_same_browser_binding` — the mint/reuse rule itself: two
   issues from one browser store the **same** `browser_binding`; two issues from two browsers
   store **different** ones.
5. `test_an_unbound_row_is_refused` — `G-1a`, end to end: issue, then
   `LoginToken.objects.filter(...).update(browser_binding=None)`, claim, redeem → **410**
   and the token is **not** burned. *This is the fail-closed assertion; without it
   `G-1a` is unenforced.*
6. `test_a_malformed_browser_cookie_is_refused` — an attacker-shaped cookie value
   (`"x" * 500`) must be **replaced** at issue time (validated, never persisted) and must
   not cause a 500 or an unbounded stored value.

**In `src/backend/apps/users/tests/test_login_token.py` — new class `TestBindingDoesNotReachTheBot`:**

7. `test_bot_claim_is_not_given_a_binding` — **source-level**, reading
   `src/telegram_bot/handlers/login.py` as text exactly as
   `TestLoginHandshakeOwnership::test_bot_handler_has_no_raw_sql` already does (via
   `Path(__file__).parents[4].joinpath("telegram_bot", "handlers", "login.py")`): assert
   `"claim_token(token_hash, telegram_id, now)"` is present and `"browser"` is absent. *The
   proof that the bot package needs no change. Asserting on source rather than importing the
   handler is what keeps `src/telegram_bot/` byte-unchanged — a signature introspection
   test would require editing a bot test file or importing aiogram from the backend suite.*

**In `src/backend/apps/users/tests/test_login_token.py` — the `G-1c` contract test:**

8. `TestClaimToken::test_claim_token_returning_matches_model_fields` — the three assertions
   in `G-1c`.

**The sixteen rewrite sites** — listed per-test with what each must become in §E.1.

**`G-1`'s record.** Option **A′**; author **the B-03 Planner**; closed **2026-10-01**.
`04-VAL-003`'s requirement (*"the binding design must be settled before implementation, not
during"*) is discharged by this section: the service signature, the enforcement point, the
rejection semantics, the field shape, the migration shape, the cookie shape and the log
shape are all fixed here.

**Risks.** **The dominant failure is a green suite over a binding that binds nothing** —
mitigated by test 1's three assertions and by test 5 · **a stale `RETURNING` silently losing
the binding on every claim with no error** (MEDIUM-HIGH, silent) — mitigated by `G-1c`'s
three assertions · **a repeat issue re-minting and destroying the binding** — mitigated by
tests 3 and 4 · **the new log line leaking PII or the binding** — mitigated by the exact
message in the brief, and by test 12 · **selective cookie refusal locking a user out** —
mitigated by fail-closed's one-retry recovery path, recorded in the commit body · **the
`secure=True` dev caveat** — recorded above · **phase 15 `15-AUTHZ-004` landing the same
function concurrently** — bounded by `G-1e` · **a migration-number collision** — bounded by
§C.3's re-verify rule.

**Rollback.** Revert the migration (an additive nullable column) and the service/view edits.
Rows written under the column become unbound — **the same state as today's rows**, and
today's rows are redeemable, so **rollback is not data-destructive** and does not
reintroduce a security regression relative to the pre-block state. Dropping the cookie
reverts to today's behaviour exactly. **Order matters:** revert the code first, then the
migration, or `claim_token`'s `RETURNING` will name a column that no longer exists — which,
per `F-1`, *is* the direction that raises `TypeError`.

**Definition of done.** Tests 1–8 green · the **sixteen** rewrite sites landed **in this
commit** · `RETURNING_COLUMNS` set-equal **and** order-equal to
`LoginToken._meta.concrete_fields`, asserted by test 8, with the round-trip assertion · the
view contains no `secrets`, no `hashlib`, no `LoginToken`, no `UPDATE login_tokens`, no
`.update(consumed_at=` · **`src/telegram_bot/` byte-unchanged — verify with `git diff
--stat -- src/telegram_bot` returning empty** · `LoginToken` still has **exactly two**
deleters · `transaction.atomic` still has **zero** occurrences in `login_token.py` ·
`login_status`'s `atomic()` block not widened · `HOURLY_COMMANDS` still exactly 9 ·
`docs/02-database/db-schema.md` and `db-enums.md` updated · **no settings change** ·
`G-1`, `G-1a`, `G-1b`, `G-1c`, `G-1d`, `G-1e`, `G-1f`, `G-1g` recorded with decisions and
authors; `G-1h` recorded as owed · **the commit body names the deferred `privacy.html` row**.

**Correction owed outside this block's file surface (recorded, not performed).** §G.1's
`B-03` row still reads *"tests 1–7 green"* and §G.2's checklist still reads *"All **nine**
`/login/status/` direct-row tests"*. Both are **superseded by this section and by §E.1**;
§G is outside this Planner's file surface, so the coordinator should update those two
strings. §D.1's phantom path is corrected at the top of this section.

**Agents.** The source plan requires all five; their work is already discharged —
**Researcher** (`U-1`: what each option really is now that `X-13` refuted the session-free
cost split — the findings table above is their output) · **Auditor** (binding-value
availability re-derived after `X-13`) · **Planner** (this section: the option, the absence
policy, the interface) · **Implementor** (ships) · **Validator** (still owed: the shipped
green tests that construct rows directly, **and** the `G-1h` re-banding).

**Implementor brief.**

```yaml
id: 04-b03-login-token-browser-binding
title: Bind a LoginToken to the browser that issued it (option A-prime)
priority: high
depends_on:
  - "G-1 CLOSED - option A-prime (see ### B-03)"
  - "G-1a CLOSED - fail closed, ConsumeOutcome.UNBOUND, HTTP 410"
  - "G-1b CLOSED - session cookie: httponly, samesite Lax, secure, path=/, NO max_age"
  - "G-1c CLOSED - RETURNING_COLUMNS is the single source of the SQL"
  - "G-1d CLOSED - all sixteen rewrite sites land in THIS commit"
  - "G-1e CLOSED - login_issue body yes, decorators no"
  - "G-1g CLOSED PARTIAL - privacy.html row deferred, see obligation below"
source_reference: .ai/plans/04-auth-login-remediation.md
source_section: "BLOCK 3 - Login-token browser binding (binding half only; the invalidation half is B-04)"
source_blocks: ["BLOCK 3", "04-AUT-001", "04-VAL-003", "04-VAL-007"]
description: >
  Add a LoginToken.browser_binding column plus a first-party login_browser_id cookie so a
  login token issued to one browser cannot be redeemed from another. issue_token() mints
  or reuses a browser id and persists only its SHA-256 digest; login_issue sets the cookie;
  consume_token() requires the presented browser id to digest to the stored value. A row
  with a NULL binding is refused, not accepted.

goals:
  - "cross-browser redemption -> 410, the token is NOT burned, and the issuer can still redeem it"
  - "same-browser redemption -> 200 plus a session"
  - "two issues from one browser keep ONE binding and the FIRST token still redeems"
  - "a NULL-binding row is refused (fail closed) and is not burned"
  - "claim_token's RETURNING provably matches LoginToken's field set - by test, both as a set and on a live round trip"
  - "zero transaction.atomic added inside login_token.py; login_status's atomic() block NOT widened"
  - "the bot package is byte-unchanged - verify with: git diff --stat -- src/telegram_bot"
  - "no new setting, no new dependency, no template change, no .po change"

extra_context: |
  EVERY BINDING CONSTRAINT IS IN THE PROSE OF ### B-03 ABOVE. Read, in this order:
  the Researcher findings verdict table; "Verified starting state"; G-1; G-1a; G-1b;
  G-1c; G-1e; "consume_token - the exact check order"; "Field and migration shape";
  "Out of scope"; and section E.1's sixteen rewrite sites. Do not re-derive them.

  TRAPS - each of these is a way this block ships green and binds nothing:

  1. The secrets tripwire. test_login_token.py::TestLoginHandshakeOwnership::
     test_consent_view_has_no_token_logic reads apps/users/views/consent.py as text and
     asserts that none of "hashlib", "secrets", "LoginToken", "UPDATE login_tokens",
     ".update(consumed_at=" appears in it. So: the browser-id MINT belongs in the SERVICE
     (login_token.py already imports secrets and already calls
     secrets.token_urlsafe(RAW_TOKEN_ENTROPY_BYTES)), and the VIEW only calls
     response.set_cookie(...). The view must never import the LoginToken MODEL - that
     would put the substring "LoginToken" in the file and turn the tripwire red.
     Importing from apps.users.services.login_token is SAFE: that path is lowercase, so
     the forbidden substring "LoginToken" does not occur in it. That test is UNCHANGED -
     satisfy it, do not edit it.
  2. RETURNING staleness is SILENT, not a TypeError. django/db/models/base.py::Model.__init__
     iterates the MODEL's fields and does kwargs.pop(field.attname) inside a try, falling
     back to field.get_default() on KeyError. So a model column missing from RETURNING
     yields a default-valued attribute and NO error. Because RETURNING is literal SQL and
     a new column never ADDS a RETURNING name, forgetting it means the bot path loses the
     binding on every claim with a fully green suite. TypeError fires only in the
     OPPOSITE direction (a RETURNING name the model lacks). Therefore: (a) build the SQL
     from RETURNING_COLUMNS with ", ".join(RETURNING_COLUMNS) - a constant merely declared
     BESIDE a hand-written literal would pass the model-comparison test while the SQL
     stayed stale; (b) a "no exception occurs" assertion is worthless here - the test must
     compare the SET (the silent case) and round-trip a real claim.
  3. login_status burn ordering. consume_token commits consumed_at EARLIER in the same
     atomic() block, so the B-05 user-state refusals (can_login, the is_active guard) all
     burn the token and their tests assert that. The BINDING refusal is the opposite case:
     it must NOT burn, so that an attacker who fails the binding check cannot destroy a
     legitimate user's in-flight login. The binding gate therefore sits AFTER the PENDING
     check and BEFORE the UPDATE, and is re-asserted inside the UPDATE's filter. Do not
     move it after the UPDATE.
  4. No atomic() in the service. login_token.py currently has ZERO occurrences of
     transaction.atomic; keep it at zero (phase 03 DB-002: the service owns the predicate,
     the caller owns the transaction). claim_token's signature is unchanged and `now` stays
     a REQUIRED caller-computed parameter. login_issue gains no atomic(). login_status's
     existing atomic() block must not gain a query or a write - the new UNBOUND branch
     returns from inside it on the ConsumeResult already in hand.
  5. REUSE the browser id, never re-mint it. login_issue issues a fresh token per page view
     and several headless clients prefetch. Re-minting on every issue would give token #1
     binding A while the cookie holds binding B, making token #1 unredeemable - login would
     break in exactly the prefetching browser that needs it. Reuse a well-formed presented
     cookie value; mint only when the cookie is absent or malformed. Never persist an
     unvalidated cookie value.
  6. The caplog PII trap - test 12. test_consent.py::TestLoginStatusNoPii::
     test_login_consume_no_raw_telegram_id asserts `str(telegram_id) not in caplog.text`
     AND `"tg_" in caplog.text`. mask_telegram_id() returns "tg_" + 8 hex chars, so the
     second assertion is satisfied only by the CONSUMED-path line. The new UNBOUND log line
     must therefore contain: the token_hash 8-char prefix (the established correlation
     convention), NO telegram_id at all (not even masked - mask_telegram_id is not needed
     and adds nothing), and NO binding value, raw or digested. Also leave the existing
     login_issue line `logger.info("Issued login token hash=%s...", issued.token_hash[:8])`
     byte-identical. Nothing logs the binding, anywhere.
  7. delete_cookie()'s Secure quirk - a FORWARD trap only. B-03 contains NO delete_cookie()
     call: the cookie is HttpOnly essential security state and is deliberately NOT cleared
     on decline. If a later block ever needs to clear it, remember that Django 5.2's
     HttpResponse.delete_cookie emits secure=True ONLY for __Secure-/__Host- prefixed names
     or samesite="none"; for any other name it emits secure=False, which does not match the
     cookie that was set and the browser ignores the delete. The remedy already exists in
     the repo: the hand-rolled expired-cookie form in
     apps/search/views/preferred_city.py::set_preferred_city.
  8. The bot package stays byte-unchanged. src/telegram_bot/handlers/login.py calls
     claim_token(token_hash, telegram_id, now) and keeps doing so. Do NOT edit
     src/telegram_bot/tests/conftest.py::login_token_factory, do NOT edit
     TestTokenRejection::test_reject_expired_token / test_reject_consumed_token, and do
     NOT add a bot-side test. That the bot needs no change is PROVEN by those tests still
     passing: the bot never supplies a binding and claim_token's WHERE clause does not
     reference one. The backend suite's proof is test 7 below (source-level).
  9. Migration number. RE-VERIFY AT WRITE TIME. Do not trust 0003.
  10. Cookie name ownership. LOGIN_BROWSER_ID_COOKIE is exported from the service and
      imported by the view, mirroring how consent.py imports PREFERRED_CITY_COOKIE_NAME
      from apps.core.middleware.preferred_city. The owner exports the name.

files:
  - path: src/backend/apps/users/services/login_token.py
    targets:
      - type: function
        name: issue_token
        change: "gains keyword-only optional browser_id: str | None = None; REUSE a well-formed presented value, else secrets.token_urlsafe(BROWSER_ID_ENTROPY_BYTES); persists browser_binding=_hash_browser_id(resolved); returns it in IssuedToken"
      - type: function
        name: claim_token
        change: "signature UNCHANGED; the SQL's RETURNING clause is built from RETURNING_COLUMNS via ', '.join(...)"
      - type: function
        name: consume_token
        change: "gains keyword-only REQUIRED browser_id: str | None; new UNBOUND step after PENDING and before the UPDATE; the UPDATE's filter gains browser_binding=<presented digest>"
      - type: class
        name: ConsumeOutcome
        change: "gains the member UNBOUND = 'unbound'"
      - type: class
        name: IssuedToken
        change: "gains the field browser_id: str"
      - type: module_constant
        name: RETURNING_COLUMNS
        change: "NEW - Final[tuple[str, ...]] - the single source of the claim SQL's RETURNING clause"
      - type: module_constant
        name: LOGIN_BROWSER_ID_COOKIE
        change: "NEW - Final[str] = 'login_browser_id'"
      - type: module_constant
        name: BROWSER_ID_ENTROPY_BYTES
        change: "NEW - Final[int] = 16 (128-bit correlator, not an authenticator)"
      - type: function
        name: _hash_browser_id
        change: "NEW - SHA-256 hex digest, mirroring _hash_raw_token"
      - type: docstring_section
        name: "The RETURNING / model-shape coupling"
        change: >
          REWRITE. It currently claims a stale RETURNING "raises TypeError" - verified
          FALSE against django/db/models/base.py::Model.__init__. State the real, silent
          risk. Do NOT touch the AUT-007 boundary section; that is B-04's.
    semantic_anchors:
      insert_after:
        type: module_constant
        value: RAW_TOKEN_ENTROPY_BYTES
      insert_before:
        type: class
        value: ConsumeOutcome

  - path: src/backend/apps/users/views/consent.py
    targets:
      - type: function
        name: login_issue
        change: >
          BODY ONLY (G-1e). Pass browser_id=request.COOKIES.get(LOGIN_BROWSER_ID_COOKIE) to
          issue_token; bind the render() result to `response`; then
          response.set_cookie(LOGIN_BROWSER_ID_COOKIE, issued.browser_id, httponly=True,
          samesite="Lax", secure=True, path="/") - no max_age. The existing
          logger.info("Issued login token hash=%s...", issued.token_hash[:8]) stays
          byte-identical. DO NOT touch @never_cache, do not add @require_POST, do not add
          any request.method branch.
      - type: function
        name: login_status
        change: >
          BODY ONLY. Pass browser_id=request.COOKIES.get(LOGIN_BROWSER_ID_COOKIE) to
          consume_token. Add the UNBOUND branch INSIDE the existing transaction.atomic()
          block, immediately after the PENDING branch and before the CONSUMED handling:
          log a WARNING carrying only the token_hash 8-char prefix and the string
          "browser binding mismatch" - no telegram_id, no binding value - and return
          HttpResponse(status=410). No new query, no new write inside the block.
    semantic_anchors:
      insert_after:
        type: function_call
        value: issue_token
      insert_before:
        type: return_statement
        value: HttpResponse
        parent: login_issue

  - path: src/backend/apps/users/models.py
    targets:
      - type: class
        name: LoginToken
        change: >
          Append browser_binding AFTER consumed_at (declaration order determines
          concrete_fields order, which RETURNING_COLUMNS must match exactly and in order):
          models.CharField(max_length=64, blank=True, null=True, help_text=...) naming it
          as the SHA-256 digest of the issuing browser's login_browser_id cookie, that the
          raw id is never stored, and that NULL means the row predates the binding. No
          db_index, no choices, no StrEnum. null=True is load-bearing - the bot's
          login_token_factory and TestTokenRejection create rows directly and src/telegram_bot
          must stay byte-unchanged, so a NOT NULL column would raise IntegrityError there.
    semantic_anchors:
      insert_after:
        type: class
        value: LoginToken
        position: "inside the class body, after the consumed_at field declaration"
        before_member:
          type: class
          name: Meta
          owner: LoginToken

  - path: src/backend/apps/users/migrations/<NNNN>_logintoken_browser_binding.py
    change: >
      NEW. One migrations.AddField operation only (model_name 'logintoken', name
      'browser_binding'). RE-VERIFY THE NUMBER AT WRITE TIME: at 83622e0 the directory
      holds exactly 0001_initial.py and 0002_alter_consentrecord_ip_address.py, so the next
      free number is 0003; B-05 under G-5a=(A) creates no migration. List the directory
      immediately before generating. Never renumber or edit an existing migration.

  - path: src/backend/apps/users/tests/test_login.py
    targets:
      - type: class
        name: TestLoginTokenBinding
        change: >
          NEW. Carries tests 1-6 below. Each obtains its token by
          client.get("/login/issue/") and keeps response.context["raw_token"], so the
          client holds the browser-id cookie the issuing path set. For a claim, call
          apps.users.services.login_token.claim_token(token_hash, telegram_id, timezone.now())
          - the exact call the bot performs, so the two-process handshake is exercised
          without importing the bot package. For expiry / already-consumed / banned /
          disabled setups, issue through the path FIRST, then force the state with an
          UPDATE - do not create the row directly, and do not let those tests degenerate
          into absence tests.
      - type: class
        name: TestLoginStatus
        change: "rewrite sites 1-8 of section E.1"
      - type: class
        name: TestLoginTokenSecurity
        change: "rewrite sites 9-10 of section E.1"
      - type: function
        name: _claim_login
        change: >
          rewrite site 11 of section E.1 - CHANGE ONCE. It receives the pytest-django
          `client` fixture, which already carries the browser-id cookie from its
          login_issue GET, so its three TestLoginPreferredCitySync dependents change
          transitively with NO body edits. Do not edit those three.
    semantic_anchors:
      insert_before:
        type: class
        value: TestLoginStatus

  - path: src/backend/apps/users/tests/test_consent.py
    targets:
      - type: class
        name: TestLoginStatusNoPii
        change: >
          rewrite site 12 of section E.1. Issue through client.get("/login/issue/") so the
          row is bound and the expected status stays 200; assert 200, then
          `str(telegram_id) not in caplog.text` and `"tg_" in caplog.text` as before. Read
          trap 6 before writing any new log line.

  - path: src/backend/apps/users/tests/test_login_token.py
    targets:
      - type: class
        name: TestBindingDoesNotReachTheBot
        change: >
          NEW. Carries test 7: read src/telegram_bot/handlers/login.py as text via
          Path(__file__).parents[4].joinpath("telegram_bot", "handlers", "login.py"), the
          same technique TestLoginHandshakeOwnership::test_bot_handler_has_no_raw_sql uses.
          Assert "claim_token(token_hash, telegram_id, now)" is present and "browser" is
          absent. Source-level on purpose: a signature-introspection test would have to
          import aiogram into the backend suite or edit a bot test file, and
          src/telegram_bot/ must stay byte-unchanged.
      - type: class
        name: TestClaimToken
        change: "ADDS test_claim_token_returning_matches_model_fields (test 8). Adding is not weakening."
      - type: function
        name: _make_token
        change: >
          rewrite site 13 of section E.1. Give it a module-level _BROWSER_ID constant and
          write browser_binding=_hash_browser_id(_BROWSER_ID) so the rows it builds are
          bound under G-1a. Do not weaken TestClaimToken's five existing tests.
      - type: class
        name: TestConsumeToken
        change: "rewrite site 14 of section E.1"
      - type: class
        name: TestClaimConsumeAgreement
        change: "rewrite sites 15-16 of section E.1"
      - type: class
        name: TestLoginHandshakeOwnership
        change: "UNCHANGED - all three tests must pass byte-identically"

  - path: docs/02-database/db-schema.md
    change: >
      The login_tokens block gains the browser_binding line (CHAR(64), nullable) and a note
      that the consume UPDATE re-asserts the binding alongside telegram_id / consumed_at /
      expires_at. Same commit as the migration.

  - path: docs/02-database/db-enums.md
    change: >
      The CookieCategory section's parenthetical "(sessionid, csrftoken)" becomes a list that
      includes login_browser_id. Plain Markdown - no msgid, so this is NOT blocked by the
      .po files being owned by another agent.

changes:
  - action: add_code
    description: >
      Model field + migration + the service surface (mint, digest, reuse, RETURNING_COLUMNS,
      the UNBOUND outcome, the consume gate) + the two view bodies + the two doc surfaces.
  - action: add_test
    description: "the six new tests in TestLoginTokenBinding and TestBindingDoesNotReachTheBot, plus test_claim_token_returning_matches_model_fields"
  - action: modify_test
    description: >
      Rewrite all SIXTEEN section E.1 sites IN THIS SAME COMMIT. Under section E's
      governing rule, a block whose production diff and test diff are in different commits
      is incomplete.

new_tests:
  - name: TestLoginTokenBinding::test_token_from_another_browser_is_rejected
    file: src/backend/apps/users/tests/test_login.py
    asserts: >
      Issue in client A, claim, redeem in a SECOND Client -> 410; the row's consumed_at is
      still None; and A can then redeem the same raw token -> 200 plus a session. Three
      assertions: the three ways a binding can be decorative.
  - name: TestLoginTokenBinding::test_same_browser_redeems_end_to_end
    file: src/backend/apps/users/tests/test_login.py
    asserts: "GET /login/issue/ -> claim_token -> POST /login/status/ -> 200 and '_auth_user_id' in client.session"
  - name: TestLoginTokenBinding::test_repeat_issue_does_not_invalidate_the_binding
    file: src/backend/apps/users/tests/test_login.py
    asserts: "two issues from one client; claim BOTH; redeem the FIRST -> 200 (prefetch tolerance)"
  - name: TestLoginTokenBinding::test_repeat_issue_reuses_the_same_browser_binding
    file: src/backend/apps/users/tests/test_login.py
    asserts: "two issues from one browser store the SAME browser_binding; two browsers store DIFFERENT ones"
  - name: TestLoginTokenBinding::test_an_unbound_row_is_refused
    file: src/backend/apps/users/tests/test_login.py
    asserts: "browser_binding forced to NULL -> redeem -> 410 and the token is NOT burned (enforces G-1a)"
  - name: TestLoginTokenBinding::test_a_malformed_browser_cookie_is_refused
    file: src/backend/apps/users/tests/test_login.py
    asserts: "a 500-char attacker cookie is replaced at issue time, never persisted, and causes no 500"
  - name: TestBindingDoesNotReachTheBot::test_bot_claim_is_not_given_a_binding
    file: src/backend/apps/users/tests/test_login_token.py
    asserts: "source-level: 'claim_token(token_hash, telegram_id, now)' present, 'browser' absent"
  - name: TestClaimToken::test_claim_token_returning_matches_model_fields
    file: src/backend/apps/users/tests/test_login_token.py
    asserts: >
      (a) set(RETURNING_COLUMNS) == {f.attname for f in LoginToken._meta.concrete_fields}
      - the SILENT-loss assertion; (b) tuple(RETURNING_COLUMNS) == tuple(attnames) - the
      docstring's ORDER contract, labelled a consistency obligation not a security one;
      (c) round trip: issue_token(browser_id=...) then claim_token(...) and the returned
      instance's browser_binding is not None and equals the stored value.

acceptance_criteria:
  - "cross-browser redemption -> 410, token NOT burned, issuer can still redeem -> 200"
  - "same-browser redemption -> 200 plus a session"
  - "two issues from one browser keep one binding and the FIRST token still redeems -> 200"
  - "a NULL-binding row -> 410 and not burned"
  - "test_claim_token_returning_matches_model_fields passes with all THREE assertions, including the round trip"
  - "test_bot_claim_is_not_given_a_binding passes"
  - "test_consent_view_has_no_token_logic UNCHANGED and green, including its secrets clause"
  - "test_bot_handler_has_no_raw_sql UNCHANGED and green"
  - "the UNBOUND log line contains no raw telegram_id and no binding value, raw or digested"
  - "git diff --stat -- src/telegram_bot returns EMPTY (bot package byte-unchanged, including its tests)"
  - "transaction.atomic still has ZERO occurrences in src/backend/apps/users/services/login_token.py"
  - "login_status's transaction.atomic() block gained no query and no write"
  - "claim_token's signature is unchanged and `now` is still a required parameter"
  - "LoginToken still has exactly two deleters (withdraw_consent, cleanup_login_tokens)"
  - "HOURLY_COMMANDS still has exactly 9 entries"
  - "no setting added or changed, so test_env_allowlist_reverse.py and test_settings_defaults.py stay green"
  - "no template and no .po file changed; djlint not required"
  - "the COMMIT BODY names the deferred privacy.html row and the Validator's owed G-1h re-banding"

commands:
  - "docker ps --filter \"name=mko-bazuna-test-db-\"    # is the test DB up?"
  - "$dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'"
  - "uv run ruff check --fix src/backend/apps/users src/backend/apps/users/tests    # --fix also sorts imports"
  - "uv run basedpyright src/backend/apps/users"
  - "$dc run --rm -e PYTEST_OPTS=\"src/backend/apps/users/tests/test_login.py src/backend/apps/users/tests/test_consent.py src/backend/apps/users/tests/test_login_token.py --tb=short\" test"
  - "$dc run --rm --env PYTEST_SKIP_MARKERS=seed test    # the fast gate"
  - "# After any DB restart, use this form instead of the fast gate:"
  - "$dc run --rm -e PYTEST_OPTS=\"--create-db --tb=short -n auto --maxprocesses=4 --dist loadgroup\" test"
  - "git diff --stat -- src/telegram_bot    # MUST be empty"
  - "Select-String -Path src/backend/apps/users/services/login_token.py -Pattern 'transaction.atomic'   # MUST be 0 hits"
  - "Select-String -Path src/backend/apps/users/tests/test_login.py,src/backend/apps/users/tests/test_consent.py,src/backend/apps/users/tests/test_login_token.py -Pattern 'LoginToken.objects.create'   # re-derive the rewrite list; do not trust this document"

known_flakes:
  - "apps/search/tests/test_search_slo.py has ONE pre-existing unrelated wall-clock failure. Not yours."
  - >
    The stale-xdist-shard signature `3 failed, 1944 passed, 651 errors` dominated by
    `post_migrate -> create_permissions -> duplicate key
    auth_permission_content_type_id_codename_01ab375a_uniq` is a TEST-DB ARTEFACT, not a
    code regression. Remedy: drop the stale shards, wait for the DB to report healthy, then
    re-run with --create-db. Do not chase it.
  - "Setting PYTEST_OPTS REPLACES the defaults and loses --reuse-db and xdist parallelism. Never use --override-ini=addopts=; it strips --import-mode=importlib."

deferred_obligations:
  - owner: Validator
    what: "Re-band 04-AUT-001 so the rationale cites the shared-device and stolen-value vectors, and record that the Referer rationale is NOT supported by the live code (login_status is POST-only; Referrer-Policy is set at three nginx locations per file; Django's default SECURE_REFERRER_POLICY is same-origin). Changes the narrative only - not the mechanism, the tests, the migration or this brief."
    gate: "G-1h - owed, explicitly NOT a precondition for shipping"
  - owner: whoever owns the three .po files, once released
    what: >
      ONE commit covering all three steps: (1) add one <tr> to templates/privacy.html's
      cookie-inventory table - <code>login_browser_id</code>, Essential marked,
      Consent-Gated empty, description in {% trans %} (one new msgid);
      (2) add that one msgstr to src/backend/locale/{ru,bs,en}/LC_MESSAGES/django.po -
      ru and bs MUST be non-empty, en may be empty;
      (3) add "login_browser_id" to the tuple in
      apps/core/tests/test_privacy.py::TestPrivacyPage::test_privacy_page_lists_cookies
      (no new translatable string, but it MUST land with step 1 or the fast gate goes red).
      Step 3 alone proves nothing if step 1 is absent, and step 1 alone is unasserted -
      which is exactly why nothing in the repository currently fails when the row is
      forgotten.
    gate: "G-1g - an open ePrivacy disclosure obligation; named in the B-03 commit body"
  - owner: B-04
    what: >
      B-04's invalidation UPDATE lands INSIDE login_token.py, never in the view (the view is
      forbidden "UPDATE login_tokens" AND the secrets import). B-04 may add a db_index on
      browser_binding if its invalidation filters on it, and may then extend
      RETURNING_COLUMNS - in which case test 8 must be updated in B-04's own commit.
```

---

### B-04 — Per-browser token supersession (`04-AUT-007`, invalidation half) — **PLANNED 2026-10-02**

| | |
|---|---|
| **Findings owned** | `04-AUT-007` (invalidation half only; the CSRF/GET-writes half is phase 15 `15-AUTHZ-004`), `04-VAL-002` (comment half for the two `AUT-007` references) |
| **Depends on** | **`B-03`** — hard, **LANDED** (`8c65548`, `818c450`, `a0bd928`) |
| **Blocks** | `B-11` |
| **Priority** | P2 · **Risk LOW** — re-rated **down from MEDIUM**; see *Re-rating* below |
| **Audit severity** | `04-AUT-007` is **LOW**, Likelihood **LOW**, Priority **P2**, CWE-352 + CWE-384. Read from `.ai/audit/04-auth-login/findings.md` at `HEAD~3` (the audit files are deleted in the working tree). |

**Objective — restated, because the plan's wording over-claimed it.** Make `issue_token`
**supersede the issuing browser's earlier _unclaimed_ live token**, so one browser profile
holds at most one *redeemable pending* token at a time.

> **"One live token per user" is NOT expressible at issue time, and this block does not
> deliver it.** At issue time the `LoginToken` row has `telegram_id = NULL` — the bot claims
> it later — so no user identity exists yet and "prior tokens for this user" cannot be
> selected. The only identity available at issue time is the **browser binding** `B-03`
> introduced. What ships is therefore **one live unclaimed token per browser profile**, which
> is what the audit's own `R-16` check asks for (*"Repeated issuance invalidates the browser's
> previous outstanding token"*). The per-user framing survives only as a *scope limit on the
> claim* — see *What this does not close*, and the `G-4h` hand-off.

**Re-rating.** The plan rated this block P1 / Risk MEDIUM. Verified at `a0bd928` the blast
radius is **one `UPDATE` inside one function, one test rewrite, five new tests, two doc
paragraphs, no migration, no index, no setting, no template, no `.po`, no bot change.**
Risk is LOW. Priority follows the audit's own P2. **This is a de-escalation, recorded here so
the coordinator does not read the lower number as a demotion of the phase.**

**What this does not close — stated so the record is honest.** After `B-03`, a raw token
redeemed from a *different* browser is already refused (`ConsumeOutcome.UNBOUND`, fail-closed,
non-burning). The residual this block leaves is: a raw token leaked from the **same browser
profile**, redeemable **by a party holding that profile's `login_browser_id` cookie**, for the
remainder of `TOKEN_TTL_SECONDS = 300`. An attacker in that position already holds the
profile's `sessionid` and `csrftoken`, so the token is not the weakest link they hold. This
block narrows that residual from *accumulating with every reload* to *one token per profile*;
it does not eliminate it, and it does not touch the phase-15 CSRF half.

**Verified starting state.** `issue_token` performs no invalidation. The defect is
stated in two places that this block must rewrite in the **same commit**: the
`login_token.py` module docstring section *"The `AUT-007` boundary"* and
`docs/99-agent/architecture.md` §*"The `AUT-007` boundary and the two existing deleters"*.
`TOKEN_TTL_SECONDS = 300`; `cleanup_login_tokens` (hourly, `AdvisoryLockId.CLEANUP_LOGIN_TOKENS
= 5`) is the janitor. **Exactly two deleters exist** — `users/services/deletion.py::withdraw_consent`
and `core/management/commands/cleanup_login_tokens.py`. This block adds **none**.
`apps/users/tests/test_login_token.py::TestIssueToken::test_two_issues_differ` — `C-14`'s
characterisation is **WRONG at `a0bd928`; corrected here.** It calls `issue_token()` twice
**with no `browser_id`**, so `_resolve_browser_id(None)` mints **two different** ids, the two
rows carry **different** bindings, and the test asserts nothing about accumulation. It passes
before and after this block and is **NOT edited**. The test that actually pins the opposite
invariant — and that this block must rewrite — is
`apps/users/tests/test_login.py::TestLoginTokenBinding::test_repeat_issue_does_not_invalidate_the_binding`,
which the plan never names. **Re-derive before editing** (§E.5 carries the command).

**Why this is a separate block (a hard edge the source plan did not name).** At issue
time the `LoginToken` row has **no `telegram_id`** — the bot claims it later — so "prior
outstanding tokens for the same browser" can only be identified by the binding value.
**Invalidation is therefore strictly downstream of the binding design.** The source plan
treated the two halves as independently implementable; they are not.

**Corrections to the plan as written — five, all verified against live code at `a0bd928`.**

| # | Plan says | Verified | Consequence |
|---|---|---|---|
| `C-15` | `test_two_issues_differ` "currently contradicts `04-AUT-007`" | it calls `issue_token()` twice **with no `browser_id`** → two different bindings → nothing about accumulation | **unedited, green.** The real collision is `test_repeat_issue_does_not_invalidate_the_binding` |
| `C-16` | the objective is "one live token per **user**" | at issue time `telegram_id IS NULL`; per-user is unselectable | the shipped scope is **per browser profile**; per-user survives only as a claim-scope limit |
| `C-17` | "B-04 **may add a `db_index`** on `browser_binding` … in which case `RETURNING_COLUMNS` grows and test 8 must be updated in B-04's own commit" | **no column, no index and no migration are needed** — the invalidation stamps the existing `consumed_at` | `RETURNING_COLUMNS` **unchanged**; `TestClaimToken::test_claim_token_returning_matches_model_fields` **unedited**; `claim_token`'s SQL and signature stay byte-unchanged; `src/telegram_bot/` stays byte-unchanged |
| `C-18` | whether invalidation targets unclaimed **or** claimed tokens is "an explicit decision" left open | including claimed tokens kills a handshake the user has already started | **decided by `G-4d`: unclaimed only** |
| `C-19` | risk: "a second `UPDATE` inside `issue_token` breaking the `DB-002` service/caller contract" | verified: the module imports `from django.db import connection` — **`transaction` is never imported**, so it structurally cannot open a transaction; both `Select-String` hits for `transaction.atomic` are inside **docstrings** | the contract holds. The *ordering* question is real and is `G-4e` |

**`G-4b` — CLOSED 2026-10-02 by the `B-04` Planner: option (a.2) — supersede at issue time,
unclaimed only, `UPDATE` before `create`.**

*Recorded before the decision, NOT chosen* (§I.2): **(a)** invalidate the browser's prior live
token(s) at issue time; **(b)** refuse to issue when a live token exists — **WITHDRAWN,
non-viable** (only the hash is persisted, so the raw value cannot be re-issued); **(c)**
time-bounded invalidation — does not deliver "one live token per browser"; **(d)** close
`04-AUT-007` on the `TOKEN_TTL_SECONDS = 300` + hourly `cleanup_login_tokens` argument.

**The chosen predicate — four conjuncts, each load-bearing:**

```
LoginToken.objects.filter(
    browser_binding=_hash_browser_id(resolved_browser_id),
    telegram_id__isnull=True,          # G-4d — never kill an in-flight handshake
    consumed_at__isnull=True,
    expires_at__gt=timezone.now(),
).update(consumed_at=timezone.now())   # G-4c — a burn, not a delete
# ...then, unchanged, the existing LoginToken.objects.create(...)
```

| Conjunct | Why it is there |
|---|---|
| `browser_binding = <digest>` | scopes to the issuing browser profile. **Excludes `NULL`** — SQL three-valued logic, verified live. `browser_binding` needs **no index**: the lookup is a scan over a table the janitor already bounds (`G-4f`) |
| `telegram_id__isnull=True` | **the in-flight protection, and the most important conjunct.** A token the bot has already claimed is mid-handshake; burning it kills a legitimate login the user has already started. This mirrors `B-03`'s `UNBOUND` rule — *a refusal must not destroy an in-flight login* — applied to supersession. **Without it the new write is attacker-triggerable against a user who has already tapped the Telegram button**, which is strictly worse than the defect |
| `consumed_at__isnull=True` | a consumed row is already inert; re-stamping it corrupts the meaning of `consumed_at` and gains nothing |
| `expires_at__gt=timezone.now()` | an expired row is already refused by both `claim_token` and `consume_token`; stamping it is write amplification for no behavioural change, and the janitor reclaims it within the hour anyway |

**Why `UPDATE … SET consumed_at` and not `DELETE`** (`G-4c`). The module's own contract — its
docstring *and* `docs/99-agent/architecture.md` — says it must not create a **third deleter**;
`users/services/deletion.py::withdraw_consent` and
`core/management/commands/cleanup_login_tokens.py` remain the only two. A burn reuses an
existing column (hence no migration) and both downstream predicates already refuse a burned
row: `claim_token`'s `WHERE` carries `consumed_at IS NULL`, and `consume_token`'s read guard
returns `GONE`. **`LoginToken` therefore still has exactly two deleters after this block, and
`HOURLY_COMMANDS` still has exactly 9 entries — no new management command and no scheduler
entry, so `TestSchedulerConstants::test_hourly_commands_match_spec` is untouched.**

**Why this cannot become a response oracle.** A superseded token surfaces through the
**existing `GONE` branch** of `login_status` → `HTTP 410`, which
`templates/users/login_issue.html`'s polling loop already handles with the copy *"This login
link is invalid, expired, or already used."* — the status already shared by six other causes.
**No new status, no new branch, no template edit, no new translatable string, and nothing that
distinguishes supersession from expiry.** The template's `login-recovery` link is revealed on
that `410` already, so a user is never stranded — one click re-issues.

**Why the rejected options stay rejected.**

> **Letter warning — the two option lists use different letters.** §I.2 / the paragraph above
> enumerate the **plan's** four: (a) invalidate at issue time, (b) refuse to issue,
> (c) time-bounded invalidation, (d) close on the TTL. The three sub-sections below use
> **(b′), (c′), (d′)** for the *semantic* candidates this Planner was asked to cost:
> invalidate-at-redeem, invalidate-at-account-state-transition, and accept-the-TTL-bound.
> **(a.2) is the chosen form of the plan's (a).** Nothing below re-labels (b) or (c).

*(b′) "invalidate at **redeem** time, per user" — **REJECTED, structurally inert.*** It is
per-*user*, so it is the candidate that most looks like it matches the finding's wording — and
it cannot work, because **`claim_token(token_hash, telegram_id, now)` binds a token to
whoever's Telegram account opened the deep link.** An attacker who steals a raw token and
claims it produces a row carrying **their own** `telegram_id`, not the victim's. A per-user
invalidation filtered on `telegram_id = <victim>` therefore **never matches the attacker's
row.** The two live tokens a per-user reading worries about are, by construction, the same
person's own tokens on their own browsers — invalidating them buys no security and breaks a
legitimate multi-device login. Verified against the live schema: `telegram_id` carries **no
index** and is only populated after the bot claims.

*(c′) "invalidate at **account-state transition**" — **REJECTED as new work: already
provided.** `withdraw_consent` already runs
`LoginToken.objects.filter(telegram_id=user_telegram_id).delete()` inside its `atomic()`
block, **before** nullifying `telegram_id`. Ban
(`moderation/admin_actions.py::ban_user_for_ad`, `bulk_ban_users`) and decline touch no token
row at all — but both are refused at redeem by `can_login(user)` returning `False`, which runs
**after** `consume_token` returned `CONSUMED`, so **the token is burned on that refusal** (the
same shape `B-05` records for `is_active=False`). **No login is possible through any
account-state path today, and every token presented on one is burned.** The only thing missing
is *proactive* deletion of a banned user's other pending rows — session/state-transition
territory that belongs to **`B-07`**. Hand it over; do not build it here.

*(d′) "close `04-AUT-007` on the 300 s TTL" — **REJECTED, with the argument it deserves.**
`TOKEN_TTL_SECONDS = 300` plus the hourly janitor already bound the exposure to one
300-second window, so (d) is nearly free. It is rejected on this phase's own stated dominant
failure mode (§F.1: *"a green suite over a non-fix"*): `R-16` would still read FAIL, the two
`AUT-007` paragraphs would still have to be rewritten to say so, and the deliverable would be
three doc edits with no mechanism. **Weighing both sides honestly:** the marginal security
value of (a.2) over (d) is *small* — the residual requires the attacker to already hold the
victim's `HttpOnly`, `SameSite=Lax`, `__Host-` cookie from the **same browser profile**, at
which point they already hold the session cookie. The argument for (a.2) is **not** a large
security delta; it is that the control is one predicate wide, adds no migration, no index and
no new state, and turns a documented FAIL into a PASS without touching the phase-15 CSRF half.
That is a deliberate, modest call — and **`G-4h` puts the final severity and the
closed-vs-weakened verdict in the Validator's hands, not the Planner's.**

**Migration, `RETURNING`, index — the three answers, all negative (`G-4f`).**

| Question | Answer, verified at `a0bd928` |
|---|---|
| **A migration?** | **No.** The write stamps the existing `consumed_at`. `apps/users/migrations/` holds `0001_initial`, `0002_alter_consentrecord_ip_address`, `0003_logintoken_browser_binding` — **the next free number is `0004_*` and B-04 does not claim it. Re-verify the directory at write time** (another block may land one). B-04 claiming no migration number is itself a contention win while `apps/users/**` is busy |
| **`RETURNING_COLUMNS`?** | **Unchanged.** No model column is added, so the tuple still equals `LoginToken._meta.concrete_fields` attnames, the `claim_token` `RETURNING` clause is untouched, and `TestClaimToken::test_claim_token_returning_matches_model_fields` — the silent-drift tripwire — is **unedited**. `claim_token`'s signature is unchanged and `now` is still required, so `src/telegram_bot/` stays byte-unchanged (`git diff --stat -- src/telegram_bot` must be empty) |
| **An index on `browser_binding`?** | **No — and the cost is measured, not assumed.** The invalidation is an **unindexed scan**. `EXPLAIN (ANALYZE, BUFFERS)` against the live test schema: `Seq Scan on login_tokens`, `Filter: ((consumed_at IS NULL) AND ((browser_binding)::text = …) AND (expires_at > now()))`, **execution 0.097 ms, 1 buffer hit.** The table carries **only** `login_tokens_pkey`, `login_tokens_token_hash_key` and one `varchar_pattern_ops` index — no index on `browser_binding`, `telegram_id`, `consumed_at` or `expires_at`. And the table is **small by construction**: `cleanup_login_tokens`'s queryset is `expires_at__lt=now` OR `consumed_at < now - 24 h`, so the hourly tick deletes **every** token older than 5 minutes and the steady-state table holds at most ~1 h of issuance. Verified: the test database's `login_tokens` currently holds **0 rows**. A second migration for a sub-millisecond scan over a janitor-bounded table is over-engineering (project rule 5). **Accepted cost, named:** if the scheduler is down the table grows without bound and the scan degrades; the mitigation is the scheduler's liveness marker, not an index |

**Transaction constraints — `DB-002` holds (`G-4e`).** `login_token.py` imports
`from django.db import connection` and **never imports `transaction`**, so the module
structurally cannot open a transaction; both `Select-String` hits for `transaction.atomic` are
inside **docstrings** and are not code. `issue_token` therefore stays outside `atomic()`,
exactly as `claim_token` and `consume_token` do, and **`login_issue` continues to own no
transaction at all** (verified: the view has no `atomic()` block; only `login_status` does,
around the consume). **The invalidation is `UPDATE`-then-`CREATE`, in that order, and the
order is load-bearing:** the row being handed to the client does not exist yet, so it is
structurally excluded — no `token_hash !=` clause is needed and the service cannot burn its
own fresh token. The reverse order would let a concurrent second issue burn the row the first
issue just committed. **There is no read-then-update anywhere in this design**, so the
"where does the transaction belong" question does not arise; if a future change ever needs one,
it belongs in the **caller** (`login_status` already owns exactly the `atomic()` that covers
`consume_token`'s read and guarded write — this block adds nothing to it).

**Concurrency residual — accepted and bounded.** Two genuinely concurrent `GET /login/issue/`
requests from the same browser (same-site prefetch racing a real navigation) can interleave so
that the second `UPDATE` burns the row the first `CREATE` just committed. The user then sees
the existing `410` + recovery link and re-issues in one click. The window is a few
milliseconds, the outcome is fail-closed (never two live tokens), and **fixing it would require
either an `atomic()` in the service — forbidden by `DB-002` — or a uniqueness constraint the
model cannot express, because the binding is only known at issue time.** Accepted.

**Out of scope.** The CSRF/GET-writes half (phase 15 `15-AUTHZ-004`: `@require_POST` on
`login_issue`, and the per-request gate) · **any change to `claim_token`'s signature, SQL or
`RETURNING`** · any file under `src/telegram_bot/` · **a third `LoginToken` deleter** ·
`cleanup_login_tokens`'s own logic · **any migration** · **any index** · **any setting** ·
any template or `.po` · `B-07`'s account-state revocation · `B-06`'s credential recovery.

**Tests required** (`apps/users/tests/test_login_token.py`, `apps/users/tests/test_login.py`).

1. `test_second_issue_supersedes_the_first` — after a second `issue_token(browser_id=X)`,
   the **first** token is no longer claimable, asserted through **`claim_token`** and
   separately through **`consume_token`** (not through a raw SQL count). **Red before the
   change, green after** — this is the defect-pinning test.
2. `test_second_token_stays_claimable_and_consumable` — the *second* token survives its own
   issuance and completes end to end. **This is the test that fails if the invalidation is
   written after the `create`**, so it is not optional.
3. `test_issue_does_not_supersede_another_browser` — a different `browser_id`'s live token
   survives this browser's issue.
4. `test_supersession_does_not_touch_a_claimed_token` — a token the bot has already claimed
   (`claim_token`) survives a subsequent `issue_token` from the same browser and still redeems.
   **This is the `G-4d` in-flight guard.** Red if `telegram_id__isnull=True` is dropped.
5. `test_supersession_ignores_null_bindings` — a row with `browser_binding = NULL` created for
   the same logical purpose is **not** burned by a real browser's issue. This is the `G-4g`
   guard; it also pins the bot-factory / pre-`B-03` population as out of scope.
6. `test_repeat_issue_does_not_invalidate_the_binding` — **REWRITTEN, not deleted.** Its name
   states the invariant this block reverses. It becomes: two issues from one browser keep one
   binding, **the second supersedes the first**, and the second redeems end to end. The
   historical guarantee (a re-mint would have broken the first token) is preserved as an
   assertion inside the rewritten test, with a docstring line naming what changed and why.
7. `TestLoginTokenBinding::test_repeat_issue_reuses_the_same_browser_binding` — **unchanged
   and green.** It reads `browser_binding` off both rows; a burn does not delete, so it holds.
   This is the control that proves the blast radius is one test, not two.
8. `TestIssueToken::test_two_issues_differ` — **unchanged and green** (`C-15`): two calls with
   no `browser_id` mint two different bindings, so nothing matches and nothing is superseded.
9. Structural, unchanged: `TestLoginHandshakeOwnership::test_consent_view_has_no_token_logic`.
   **Consequence: the supersession `UPDATE` must live in
   `apps/users/services/login_token.py`, never in `apps/users/views/consent.py`** — the view is
   forbidden the literal string `"UPDATE login_tokens"` *and* the `secrets` import.
10. Regression: every `B-03` handshake test still passes — `TestLoginTokenBinding`'s other five,
    `TestConsumeToken`, `TestClaimToken`, `TestClaimConsumeAgreement`, and both bot-side
    rejection tests in `src/telegram_bot/tests/test_login.py`.
11. The two `AUT-007` paragraphs (`login_token.py`'s module docstring section *"The `AUT-007`
    boundary"* and `docs/99-agent/architecture.md` §*"The `AUT-007` boundary and the two
    existing deleters"*) are rewritten **in this same commit** — one rewrite, one commit, per
    `04-VAL-002`. Both must state the new predicate, the `telegram_id IS NULL` exclusion, the
    prefetch/second-tab consequence, and that the deleters remain exactly two.

**A test that passes for the wrong reason — the phase's recurring failure mode.** Tests 1–5
are written to fail if the supersession is removed, narrowed, or widened. Test 8 is the trap:
it would pass whether or not the mechanism exists, because it never presents a `browser_id`.
**Do not count it as evidence.** Test 6 is the reverse trap: it is a shipped green test whose
name asserts the opposite of the finding, and it must be rewritten *and* its replacement must
assert the new behaviour — not merely deleted, because deleting it would silently drop the
re-mint regression guard `B-03` added.

**Gates — `G-4b` … `G-4g` are CLOSED by the `B-04` Planner (2026-10-02); `G-4h` … `G-4j`
remain OPEN and belong to the Validator / coordinator, not to the Implementor.** Full rows in
§H. `B-03` has landed, so the hard edge is served.

**Agents.** Implementor **yes** · Planner **yes** (done — this section) · Validator **yes**
(it reverses one shipped green test and changes a finding's status) · Auditor **no** and
Researcher **no** — **deviation, justified:** once `B-03`'s binding exists the remaining
question is purely internal to this module; there is no external fact, no Django-version
uncertainty and no architectural alternative left to investigate. The source plan's "all
agents" assumed the two halves were separable, which they are not.

**Risks — re-derived at `a0bd928`.**

| Risk | Severity | Disposition |
|---|---|---|
| **Same-site prefetch / prerender kills a user's in-flight login.** A prefetched `GET /login/issue/` carries the `SameSite=Lax` binding cookie, so it supersedes the visible tab's token; that tab then gets the existing `410` and must click the recovery link once | **MEDIUM — the real cost of this block** | Accepted, and it is why `G-4d` excludes **claimed** tokens (a user who already tapped the Telegram button is never killed by a prefetch). The plain **reload** case is *not* affected: the re-rendered page polls the new token. **A cross-site forced GET is also not a DoS vector** — `SameSite=Lax` withholds the cookie, so `issue_token(None)` mints a fresh binding and supersedes nothing. Escalated to the coordinator as `G-4i` because it is a product-acceptance question, not a code question |
| Second tab / two of the user's own devices | LOW | Accepted; the earlier tab's recovery link re-issues in one click |
| Reversing a shipped `B-03` guarantee and its test | LOW | Deliberate and documented (test 6); `B-03`'s re-mint guard is retained inside the rewrite, not dropped |
| A second `UPDATE` breaking `DB-002` | **NONE** | Structurally impossible — `transaction` is never imported by the module. Do **not** wrap `issue_token` in `atomic()` |
| Option (d) being recorded as a closure rather than a weakening | **NONE** | (d) is rejected. `G-4h` requires the Validator to state closed-vs-weakened in the commit body |
| An unindexed scan degrading if the scheduler is down | LOW | Measured at 0.097 ms on the live schema; the janitor bounds the table to ~1 h of issuance (verified: 0 rows). No index, by design (`G-4f`) |

**Rollback.** Revert the `issue_token` edit, the one test rewrite and the two docstring
paragraphs. **No schema change, no data change, no migration to reverse** — the supersession
only stamps an existing column on rows the janitor reclaims within the hour.

**Definition of done.** Tests 1–11 green, with **1 rewritten** and **5 new** · test 8
(`test_two_issues_differ`) **unchanged and green** · test 7
(`test_repeat_issue_reuses_the_same_browser_binding`) **unchanged and green** ·
`LoginToken` still has **exactly two deleters** · `HOURLY_COMMANDS` still **exactly 9** entries ·
`RETURNING_COLUMNS` still equals `LoginToken._meta.concrete_fields` attnames and
`test_claim_token_returning_matches_model_fields` is **unedited** ·
`login_token.py` still contains **no executable** `transaction.atomic` and still does not
import `transaction` · `git diff --stat -- src/telegram_bot` is **empty** ·
**no migration was created** and `0004_*` remains unclaimed by this block · no setting, no
template and no `.po` changed · the two `AUT-007` paragraphs rewritten in this commit ·
`G-4b` … `G-4g` recorded with decisions and author.

**Implementor brief.**

```yaml
id: 04-b04-token-supersession
title: Supersede the issuing browser's earlier unclaimed live login token at issue time
priority: medium          # follows the audit's own P2 for 04-AUT-007; see the block header
depends_on: [04-b03-login-token-browser-binding]   # LANDED: 8c65548, 818c450, a0bd928
source_reference: .ai/plans/04-auth-login-remediation.md
source_section: BLOCK 3 — per-browser invalidation (invalidation half)
source_blocks: ["BLOCK 3", "04-AUT-007"]
gates_closed: ["G-4b (a.2)", "G-4c", "G-4d", "G-4e", "G-4f", "G-4g"]
gates_open_for_others: ["G-4h", "G-4i", "G-4j"]
baseline: >
  114 passed in 92.74s at a0bd928 for test_login_token.py, test_login.py, test_deletion.py,
  test_sweep_login_tokens.py, test_consent.py (single-process; PYTEST_OPTS replaces the
  xdist defaults). Recorded so the Implementor can tell a regression from the baseline.
description: >
  Inside issue_token, and BEFORE the existing LoginToken.objects.create, supersede the
  issuing browser's earlier live-but-unclaimed tokens by stamping consumed_at on them.
  The predicate is scoped to the resolved browser binding digest and deliberately EXCLUDES
  claimed tokens, NULL bindings, consumed rows and expired rows. No migration, no index,
  no new setting, no template, no .po, no bot change, no new deleter.
goals:
  - "one browser profile holds at most one live UNCLAIMED login token at a time"
  - "a token the bot has already claimed survives a later issue (in-flight protection)"
  - "another browser's live token is unaffected"
  - "NULL-binding rows are excluded and left alone"
  - "LoginToken still has exactly two deleters; HOURLY_COMMANDS still 9 entries"
  - "RETURNING_COLUMNS unchanged and test_claim_token_returning_matches_model_fields unedited"
  - "the two AUT-007 paragraphs rewritten in this same commit"
extra_context: >
  Every constraint is in the prose above under: Verified starting state, Corrections applied
  (C-15..C-19), The chosen predicate, Migration/RETURNING/index, Transaction constraints,
  Out of scope. Read them before editing. The three that are easiest to get wrong: the
  telegram_id__isnull=True conjunct (G-4d), UPDATE-before-CREATE ordering (G-4e), and the
  NULL-binding exclusion (G-4g). Do NOT wrap issue_token in transaction.atomic(); the module
  must never import transaction.
files:
  - path: src/backend/apps/users/services/login_token.py
    targets:
      - type: function
        name: issue_token
      - type: function
        name: _resolve_browser_id        # read-only; reuse is what makes the predicate exact
      - type: module_docstring_section
        name: "The AUT-007 boundary"
  - path: src/backend/apps/users/tests/test_login_token.py
    targets:
      - type: class
        name: TestIssueToken             # 5 new tests land here or in a sibling class
      - type: class
        name: TestLoginHandshakeOwnership  # unchanged; the UPDATE must NOT go in the view
      - type: test
        name: TestClaimToken::test_claim_token_returning_matches_model_fields  # unchanged
  - path: src/backend/apps/users/tests/test_login.py
    targets:
      - type: class
        name: TestLoginTokenBinding
      - type: test
        name: TestLoginTokenBinding::test_repeat_issue_does_not_invalidate_the_binding  # REWRITTEN
      - type: test
        name: TestLoginTokenBinding::test_repeat_issue_reuses_the_same_browser_binding  # unchanged, must stay green
  - path: docs/99-agent/architecture.md
    targets:
      - type: section
        name: "The AUT-007 boundary and the two existing deleters"
changes:
  - action: add_code
    description: >
      In issue_token, resolve the browser id first, then run the supersession UPDATE
      (browser_binding=<digest of the resolved id>, telegram_id__isnull=True,
      consumed_at__isnull=True, expires_at__gt=timezone.now()) stamping consumed_at, then
      the existing create. Log the superseded row count at INFO with NO raw token, NO raw
      browser id and NO telegram_id — the binding digest prefix and the new token_hash
      prefix only, matching the module's existing log discipline. Keep the create's return
      value (IssuedToken) and the function signature byte-compatible.
  - action: modify_doc
    description: >
      Rewrite login_token.py's "The AUT-007 boundary" docstring section and the matching
      architecture.md section in this same commit. Both must state: the predicate and its
      telegram_id IS NULL exclusion, that it is a burn and not a third deleter, that NULL
      bindings are excluded, the prefetch/second-tab consequence, the <=300 s bound, and
      that the per-user framing is not expressible at issue time.
  - action: modify_test
    description: >
      5 new tests (supersession of the first; the second survives its own issuance; another
      browser untouched; a claimed token survives; NULL bindings untouched) plus a REWRITE
      of test_repeat_issue_does_not_invalidate_the_binding that keeps B-03's re-mint guard
      as an assertion while asserting the new supersession behaviour. Delete nothing.
acceptance_criteria:
  - "after issue_token(browser_id=X) twice, the FIRST token is neither claimable via claim_token nor redeemable via consume_token"
  - "the SECOND token is claimable and completes consume_token end to end"
  - "a token claimed by the bot before a second issue is still claimable and redeemable"
  - "a different browser_id's live token is untouched"
  - "a NULL-binding row is not burned"
  - "test_repeat_issue_does_not_invalidate_the_binding rewritten and green, re-mint guard retained"
  - "test_repeat_issue_reuses_the_same_browser_binding UNCHANGED and green"
  - "test_two_issues_differ UNCHANGED and green"
  - "TestLoginHandshakeOwnership::test_consent_view_has_no_token_logic UNCHANGED and green"
  - "RETURNING_COLUMNS == LoginToken._meta concrete attnames; test_claim_token_returning_matches_model_fields unedited"
  - "LoginToken still has exactly two deleters; HOURLY_COMMANDS still exactly 9 entries"
  - "login_token.py contains no executable transaction.atomic and does not import transaction"
  - "no migration created; no index created; no setting, template or .po touched"
commands:
  - "uv run ruff check --fix src/backend/apps/users"
  - "uv run basedpyright src/backend/apps/users"
  - "$dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'"
  - "$dc run --rm -e \"PYTEST_OPTS=src/backend/apps/users/tests/test_login_token.py src/backend/apps/users/tests/test_login.py src/backend/apps/users/tests/test_deletion.py src/backend/apps/core/tests/test_sweep_login_tokens.py src/backend/apps/users/tests/test_consent.py --tb=short\" test"
  - "$dc run --rm --env PYTEST_SKIP_MARKERS=seed test    # the fast gate"
  - "git diff --stat -- src/telegram_bot    # MUST be empty"
  - "git diff --stat -- src/backend/apps/users/migrations    # MUST be empty"
  - "Select-String -Path src/backend/apps/users/services/login_token.py -Pattern 'from django.db import'   # MUST show connection only, never transaction"
  - "Get-ChildItem src/backend/apps/users/migrations    # re-verify the next free number at write time; B-04 claims none"
  - "Select-String -Path src/backend/apps/users/tests/test_login.py,src/backend/apps/users/tests/test_login_token.py -Pattern 'issue_token|client.get(\"/login/issue/\")|_make_token|LoginToken.objects.create'   # re-derive the rewrite list; trust no count, including this document's"
known_flakes:
  - "apps/search/tests/test_search_slo.py::TestSearchResponseSLORegression::test_search_at_seed_volume_meets_slo — pre-existing wall-clock SLO failure, not this block's."
  - "test_support_delivery_email.py / test_support_delivery_telegram.py / test_analytics_service.py — pre-existing, external-DM, not this block's."
  - "The stale-xdist-shard signature (post_migrate -> create_permissions duplicate key) is a TEST-DB ARTEFACT, not a code regression. Re-run with --create-db; do not chase it."
  - "Setting PYTEST_OPTS REPLACES the defaults and loses --reuse-db and xdist parallelism. Keep -n 4 on the fast gate; never use --override-ini=addopts= (it strips --import-mode=importlib)."
residual_risk_accepted:
  - "Same-site prefetch or prerender of GET /login/issue/ supersedes the visible tab's token; that tab gets the existing 410 and one recovery click. A plain reload is NOT affected. A cross-site forced GET is NOT a DoS (SameSite=Lax withholds the cookie, so a fresh binding is minted and nothing matches)."
  - "A second tab or a second device of the same user loses its earlier pending token; one click re-issues."
  - "Two genuinely concurrent issues can interleave so the second UPDATE burns the row the first CREATE just committed. Fail-closed, milliseconds wide, self-recovering via the recovery link."
  - "04-AUT-007 is NOT fully closed: a raw token leaked from the same browser profile stays redeemable by a holder of that profile's cookie for the remainder of the 300 s TTL. The severity and the closed-vs-weakened verdict are owed to the Validator under G-4h."
deferred_obligations:
  - owner: B-07
    what: >
      Proactive deletion of a banned user's other pending LoginToken rows. Verified NOT
      needed for safety: the redeem-side can_login gate already refuses and burns every
      token on the ban and decline paths. B-04 must not build it.
    gate: "G-4j — a hand-off, not a B-04 gate"
  - owner: Validator
    what: >
      Re-band 04-AUT-007 and state closed vs weakened, and re-run the audit's R-16 check
      ("Repeated issuance invalidates the browser's previous outstanding token") against the
      shipped predicate. See G-4h.
    gate: "G-4h — owed, explicitly NOT a precondition for shipping"
  - owner: coordinator
    what: >
      Accept or reject the prefetch consequence as product behaviour. See G-4i. The Planner's
      recommendation is to accept it: the failure is one click on an affordance that already
      exists, and G-4d already removes the worst case (a claimed, mid-handshake token).
    gate: "G-4i — product acceptance, not a code gate"
  - owner: whoever owns this document outside B-04
    what: >
      §I.2's B-04 paragraph still reads "still undecided — G-4b owns it" and §G.1's B-04 row
      still says "test_two_issues_differ extended". Both are now stale. The B-04 Planner did
      not edit them: §I.2 is shared with B-03 and §G.1 is outside the B-04 edit mandate.
    gate: "not a gate — a stale cross-reference to sweep once B-04 lands"
```

---

### B-05 — `is_active` resolution (`04-AUT-004`) — premise refuted

| | |
|---|---|
| **Findings owned** | `04-AUT-004` (+ severity re-banding, which belongs to the Validator) |
| **Depends on** | **`G-3`** — ✅ **CLOSED**, option (i), `B-05` first · **`G-5a`** — ✅ **CLOSED**, option **A′** (dedicated guard in `login_status`) |
| **Blocks** | `B-07` (soft); phase 15 `15-AUTHZ-001` |
| **Priority** | P1 · **Risk HIGH** |

**Objective.** Decide, on evidence, what `User.is_active` is for in this system and either
close the one real residual path or record the field as inert — without pretending a
defect the audit refuted still exists.

**Verified starting state — and the refutation of the finding's premise.** `User`
inherits `is_active` from `AbstractUser`; it is not overridden in `apps/users/models.py`.
**No production code reads or writes `User.is_active`.** (Pre-ship census. The shipped
guard in `login_status` is now the one production **reader** — see the Validator record
below; nothing else changed.) The only writer is
`apps/seed/generators/users.py` (`is_active=True`, the `AbstractUser` default) plus one
assertion in `apps/seed/tests/test_seed.py`. **No `is_active` fixture exists in either
conftest.** `apps/users/services/account_state.py`: `AccountState(NamedTuple)` =
`(is_banned, is_deleted, is_declined, ads_auto_publish, consent_revoked)`;
`get_account_state(user)`; `can_login(user) -> bool` gates on `is_banned` and
`is_declined` **only**; `can_publish_ad` gates on `is_banned`, `is_deleted`,
`ads_auto_publish`; `get_state_badge`. **No `is_active` term anywhere.**
Call-site counts (verified): `can_login` — **1** production call site
(`users/views/consent.py::login_status`); `get_account_state` — **2**, both in the bot
(`telegram_bot/middlewares/permissions.py::_evaluate_user_state` and
`::_evaluate_publish_permission`); `can_publish_ad` — **0**.

**`Q4` is already answered** (`C-22`): `ModelBackend.get_user()` returns
`user if self.user_can_authenticate(user) else None`; `user_can_authenticate` is
`getattr(user, "is_active", True)`. `django.contrib.auth.get_user()` calls it;
`AuthenticationMiddleware` installs `AnonymousUser` when it returns `None`;
`@login_required` (13 view modules) therefore **302s**. `/admin/` login is refused by
`ModelBackend.authenticate`. **Phase 15's matrix is right; the phase-04 report's "invisible
end to end" is wrong.**

**The one real residual.** `login_status` fetches `User.objects.get(telegram_id=…)`,
checks only `can_login(user)`, then calls `auth_login(request, user)`.
`django.contrib.auth.login()` performs **no** `is_active` check. So an `is_active=False`
user completes the handshake: **HTTP 200 + a session cookie**, and is anonymous from the
next request onward. This is the entire unmediated surface.

**Corrections applied** (see §A.4/A.5). Blast radius is **1 call site**, not 7;
`ads/dashboard/*` and `seller_required` do not exist; `_check_user_state` is a **test-only**
wrapper `__call__` does not use; option (b)'s write-site count is **2**, not "every fixture
across both conftests"; **`UserAdmin.list_filter` does not list `is_active`**, so option
(b) needs no `list_filter` edit.

**`G-5a` — ✅ CLOSED by the `B-05` Planner (2026-10-01) — option (A), as a dedicated guard
in `login_status` (variant A′).** Option (B) is recorded as **permanently unavailable**.
The full decision, the rejected options, the phase-15 decision record, the final test list
and the final Implementor brief are below. **Do not reopen.**

**Corrected option set for `G-5a` — decided, not open.** Re-verified live at `fd8c423`:

| Option | Disposition | Why |
|---|---|---|
| **A** refuse the 200 **and** the session cookie for an `is_active=False` account | ✅ **CHOSEN, as variant A′** — a **dedicated guard in `login_status`**, *not* a new term inside `can_login` | The single unmediated path. Costs one guard, closes the residual, and the guard sits inside the existing one-time handshake in an existing view — **it is not a second gate**: no middleware, no decorator, no new shared predicate. See "Why A′ and not a term in `can_login`" below |
| **B** `RemoveField is_active` | ❌ **REJECTED — recorded as PERMANENTLY UNAVAILABLE, not merely rejected for this block** | **Not implementable**, and **fails open and 500s the admin** if it were. Full proof below |
| **C** record the field inert, name the residual | ❌ rejected | The honest floor, but it leaves a field that code writes and no code reads, and documents an unmediated 200+cookie path as a permanent known gap — the trap this block exists to close |
| **D** add a term to `AccountState` / `get_account_state` | ❌ rejected | A `NamedTuple` shape change with **zero** behaviour change for the bot, a breaking edit to an existing test, and a collision with phase 15's `permissions.py` refactor |

**Why option (B) is permanently unavailable — three independent blockers, all verified at
`fd8c423`.**

1. **It cannot be implemented with supported APIs.** `is_active` is declared on
   `django.contrib.auth.models.AbstractUser`; `apps.users.models.User` extends `AbstractUser`
   and does **not** re-declare it. Abstract-parent fields are **copied into** the concrete
   model's `_meta.local_fields`, and migration state is rendered from `_meta.local_fields`,
   not from the class descriptor. There is **no supported way to emit a `RemoveField`** for
   an inherited abstract field: `delattr(User, "is_active")` removes the descriptor but
   leaves the field in `_meta.local_fields` and in `ProjectState.from_apps(...)`. Doing it
   properly means either editing Django in `.venv/Lib/site-packages/` (**not project code,
   not reproducible**) or dropping the `AbstractUser` / `AbstractBaseUser` /
   `PermissionsMixin` bases and re-declaring ~10 fields. **Re-verified:** `User` is
   `class User(AbstractUser)` with `username`, `telegram_id`, `chat_id`, `is_banned`,
   `is_deleted`, `is_declined`, `ads_auto_publish`, `telegram_premium`, `preferred_city`,
   `deleted_at`, `consent_given_at`, `consent_revoked_at`, `telegram_language`, `source`,
   `groups`, `user_permissions` declared; `is_active` is not among them.
2. **If the field were genuinely absent, the kill-switch would silently fail open.**
   `ModelBackend.user_can_authenticate` is `return getattr(user, "is_active", True)`
   (verified at `django/contrib/auth/backends.py::user_can_authenticate`, Django 5.2.17).
   With the attribute gone it returns `True` — an account an operator disabled becomes
   **silently re-enabled**, and no test in the tree would fail.
3. **The admin would 500 on every view.** `ModelBackend.has_perm` / `get_all_permissions` /
   `get_user_permissions` / `has_module_perms`, `PermissionsMixin.has_perm` / `has_perms` /
   `has_module_perms` and `AdminSite.has_permission` all use **direct** attribute access
   (not `getattr` with a default), so they raise `AttributeError`; and
   `AdminSite.admin_view`'s inner wrapper calls `has_permission` on **every** admin view.

`G-3` being (i) is what made (B) *reachable* at all (a `fieldsets` entry naming a removed
field raises `FieldError` and 500s every add and change request). **The field stays.**
`B-01`'s `fieldsets` must therefore still name or omit `is_active` by its own decision, and
`B-05` creates **no migration** — which also leaves `0003_*` free for `B-03`.

**Why A′ (a dedicated guard in `login_status`) and not a new term inside `can_login`.**

Both placements are behaviourally identical to the bot: the bot **never calls `can_login`**
in production — it calls `get_account_state`, and its two call sites
(`telegram_bot/middlewares/permissions.py::_evaluate_user_state` and
`::_evaluate_publish_permission`) read **named** terms off the `NamedTuple`. Verified
again at `fd8c423`. So neither variant changes anything the bot sees, and
`test_account_state_middleware.py::TestCrossPredicateAgreement` stays green under both.

A′ is chosen for four reasons:

1. **It is not a second gate, and putting the term in `can_login` invites it to look like
   one.** `can_login` is the predicate phase 15's `15-AUTHZ-001` will build its DENY set
   on. A term there declares `is_active` a **DENY condition** — which is precisely the
   claim the evidence refutes. The accurate statement is *"no session cookie is issued on
   a disabled account"*, not *"access is denied"*. A′ keeps the truth in the one place where
   the cookie is written and `can_login` keeps its honest, narrow docstring.
2. **The log line would become inaccurate and indistinguishable.** `login_status`'s existing
   410 branch hardcodes `"Login denied for telegram_id=%s: banned"`. That message is
   **already** wrong for the decline path (a declined user is denied with a `"banned"`
   message today). A term in `can_login` would add a third wrong reason to the same line and
   make a disabled account indistinguishable from a banned one in the logs. A′ gets its own
   `logger.warning` with a stable reason code.
3. **`can_login` has a public re-export and a pinned contract.** It is in
   `apps/users.services.__init__.__all__` alongside `AccountState`, and
   `test_account_state.py::TestCanLogin` is a §E.3 tripwire whose six assertions must pass
   **unchanged** (including `deleted → True` and `ads_auto_publish=False → True`). A′ does
   not touch the predicate at all, so that tripwire is green by construction rather than by
   argument.
4. **The residual is view-specific, so the fix is view-specific.** The bug is
   `auth_login(request, user)` writing a session. Only `login_status` can do that. A
   predicate term is a wider change that buys nothing here.

**The exact change, in one sentence:** in
`apps/users/views/consent.py::login_status`, add a guard that tests `user.is_active`
**strictly after** the `User.objects.get(telegram_id=…)` lookup and **strictly before**
`auth_login(request, user)`, and return `HttpResponse(status=410)` with its own
`logger.warning` naming a stable reason code, using `mask_telegram_id(telegram_id)`.

**What this honestly buys — the wording the Implementor and the Validator must both use:**

> **No session cookie is issued on a disabled account. The token is still burned, exactly
> as on the ban and decline paths, so the two-phase handshake must restart.**

**Correction to this mandate (Validator, 2026-10-01) — the second clause of the original
sentence was false.** This section used to mandate, verbatim, *"No session cookie is issued
and no token is consumed on a disabled account."* That was wrong: `consume_token` commits
`LoginToken.consumed_at` inside `login_status`'s `transaction.atomic()` **before** the user
lookup and before the new guard, so the token **is** burned on the denial path — exactly as
on the existing ban and decline paths. The shipped test
`test_login_status_burns_the_token_for_a_disabled_account` proves it
(`assert token.consumed_at is not None`), and the brief's own `traps` entry said so before
the block shipped. The false clause originated in **this plan's own mandate**, not in the
Implementor's implementation. Commit `e106e0b` shipped it — as the commit body's second
line, while stating the correct behaviour correctly four paragraphs later, so that body is
internally contradictory. **It is not being amended**: rewriting history is forbidden, and
the commit is final evidence. **The inaccuracy is confined to the commit message** — the
shipped code, the tests and the log reason code (`"account disabled"`, masked) are correct.

**Not** *"the account is now protected"*, and **not** *"a session can no longer reach a
protected view"*. Django **already** refuses on the next request:
`ModelBackend.get_user` returns `None` for an inactive user,
`django.contrib.auth.get_user` then yields `AnonymousUser`, and `@login_required` **302s**
(verified at `fd8c423`). Today's cookie is a **write-only artefact** — its identity is
discarded on the very next request. So the **net** web-side security change of option (A)
is ≈ 0 in terms of reachable protected state; what changes is that the site stops handing
out a credential it will not honour, and stops burning a live token into a session nobody
can use. **The block's risk register is right that this can create a false sense of a
security fix — the framing above is the mitigation, and it is mandatory in the commit
message.**

**Scope: no migration, no model change, no middleware, no decorator, no new shared
predicate, no new abstraction.** `src/backend/apps/users/migrations/` is **untouched** by
this block (re-verified at `fd8c423`: exactly `0001_initial.py` and
`0002_alter_consentrecord_ip_address.py`; highest was `0002` at that commit).
*(Historical pre-flight statement, superseded: `0003_logintoken_browser_binding.py` now
exists — created by `B-03` as required. The binding invariant is restated in §G.2: no
existing migration was edited or renumbered.)*

**Out of scope.** `can_publish_ad` and the queryset visibility predicate (phase 15
`AUTHZ-005`) · `AuthStateMiddleware` (phase 15 `AUTHZ-001`) · `AccountState`,
`get_account_state`, `can_publish_ad` and `get_state_badge` ·
`src/telegram_bot/**` (unmodified, under every option) ·
`src/backend/conftest.py` (neither conftest) · severity re-banding.

---

#### Decision record for phase 15 — `15-AUTHZ-001` and the DENY vocabulary

**This is the record the source plan's BLOCK 4 owes phase 15 (§5.3 row 2). It is
mandatory: a silent ship here is how a security control gets added to a gate in one phase
and removed in the next.**

**Is phase 15's carve-out supported or contradicted? → SUPPORTED, with the reason
corrected. `is_active` must stay OUT of `15-AUTHZ-001`'s DENY set — and phase 15 must
change nothing to make that true.**

**Evidence (all verified at `fd8c423`, Django 5.2.17 at
`.venv/Lib/site-packages/django/`):**

| Claim | Evidence | Verdict |
|---|---|---|
| Django enforces `is_active` on every authenticated request | `ModelBackend.user_can_authenticate` is `getattr(user, "is_active", True)`; `ModelBackend.get_user` returns `user if self.user_can_authenticate(user) else None`; `django.contrib.auth.get_user` therefore yields `AnonymousUser`; `@login_required` **302s** | `15-AUTHZ-001`'s matrix row is **correct** |
| The enforcement is **below** any project gate it could be duplicated into | `MIDDLEWARE` has **15** entries, `DbLockTimeoutMiddleware` at position 6; `LoginRequiredMiddleware` exists in 5.2 but is **not** in the list; **no** project middleware assigns or reads `is_active` (only `is_authenticated` reads); `AUTHENTICATION_BACKENDS` is unset, so Django's single `ModelBackend` is in force | A DENY term would be **unreachable** — the identity is gone before any project middleware runs |
| The bot tier never authenticates a session | The bot reads `get_account_state`; `is_active` has **zero** references under `src/telegram_bot/`. `can_login` has **zero** production call sites outside `login_status` | The bot needs no `is_active` term |
| Adding `is_active` to the DENY set would still change behaviour **at the issuance point** | With `B-05` option A′ shipped, `POST /login/status/` for an `is_active=False` user returns **410** and sets no cookie | The change is real but it lives in **this** phase, **not** in phase 15's per-request gate |

**Therefore, the corrected reason for the carve-out.** The carve-out is right, but **not**
because the field is inert. The accurate statement is:

> `is_active` is enforced by **`ModelBackend`**, one layer **below** phase 15's gate, not by
> the project. Its enforcement is therefore **complete and unconditional** on the web tier
> and the bot tier, and adding it to `15-AUTHZ-001`'s DENY set would duplicate an
> already-effective control with an unreachable term. `is_active` is **not** a project-owned
> DENY condition and must not be recorded as one.

**What `is_active` should mean in phase 15's DENY vocabulary — three rules, binding on
`15-AUTHZ-001`:**

1. **Keep it out of the DENY set.** DENY means *"the project gate must refuse this"* — a
   contract the project does not own and cannot be shown to own. A DENY term implies a
   testable project control; there is none.
2. **Record it as a third, separate category: a *Django-owned pre-gate* term.** The
   vocabulary phase 15 writes is `{project DENY terms}` ∪ `{Django-enforced pre-gate
   terms}`, and `is_active` is in the second set. Practically: in `15-AUTHZ-001`'s
   matrix, keep the `is_active=False → redirects` row and annotate it *"enforced by
   `ModelBackend.user_can_authenticate`, not by the phase-15 gate"*. This is what stops a
   future phase from (a) removing the row on the grounds that the field is inert, or
   (b) treating the field as project-enforced and ceasing to look at its single writer.
3. **Do not conclude the field is inert — and do not conclude it is
   operator-unreachable.** The census is exactly **two** code sites outside the fix, both
   in `apps/seed/`: the single writer
   `apps/seed/generators/users.py::UserGenerator.generate` (which passes `is_active=True`,
   literally the `AbstractUser` default) and the single reader
   `apps/seed/tests/test_seed.py::TestSeedUsers::test_users_are_active`. There are
   **zero** `hasattr`/`getattr` probes, **zero** `filter(is_active=…)` on `User`, **zero**
   `.only()`/`.defer()` on `User` (the tree's four `.only()` calls are on `Ad`), **zero**
   `.raw()`/`.extra()`/`RawSQL`, no DRF, no template reference, no `is_active` in either
   conftest, and `UserAdmin` names no `is_active` in `list_display`/`list_filter`/
   `readonly_fields`/`search_fields`. **Do not confuse** `Category`, `LookupItem`,
   `SavedSearch`, `SupportContact` and `AnonymousUser.is_active` (a hard class attribute) —
   all unaffected. **The field is Django-enforced, operator-reachable, and
   undiscoverable.**

   **Correction to this rule (Validator, 2026-10-01) — the reachability claim in the
   original text was wrong.** It read *"operator-unreachable in this product"* and *"nothing
   in the product **or the admin** writes `is_active=False`"*. **Both are false.**
   `src/backend/apps/users/admin.py::UserAdmin` declares **neither `fields` nor
   `fieldsets`**, so `ModelAdmin.get_form()` derives the change form from every editable
   model field — and `is_active` **is** an editable field on that form. Verified empirically
   in the test container:

   ```
   declared fieldsets = None | declared fields = None
   get_fields() = [… 'is_active', …]
   IS_ACTIVE IN CHANGE FORM = True
   ```

   An operator holding `users.change_user` can untick **Active** and save. The kill-switch
   is therefore **operator-reachable but undiscoverable**: absent from `list_display` and
   `list_filter`, so nothing surfaces it. **This correction strengthens the shipped fix's
   justification, not the reverse:** the control is real and reachable, which is precisely
   why the issuance point was worth closing before an operator ever used it. Discovered and
   then re-used, a disabled account's write-only cookie is exactly the artefact `B-05`
   refuses to hand out. **What phase 15 must carry forward:** the field is enforced by
   Django, reachable through the admin change form, and exercised by no production code
   path today — so the fix's protection is currently test-verified rather than
   traffic-verified. (`B-01` records the discoverability advisory; the path is not
   reachable through the bot — all **39** bot-side `is_active` references are
   `SavedSearch`, plus one `Category`, and **zero** are `User.is_active`.)

**Net instruction to phase 15: no change to `15-AUTHZ-001`'s DENY set. The carve-out
stands, for a better-stated reason.**

**Severity.** The premise is materially wrong. **Re-banding belongs to the Validator**,
not the Implementor (source plan §6.2 item 10, §F.2 risk 6). **The Implementor must not
touch the severity of `04-AUT-004`.**

**Severity re-banding — RECORDED (Validator, 2026-10-01). `04-AUT-004` is re-banded from
MEDIUM to LOW. Disposition: DOWNGRADE, KEEP OPEN — not closed.** The finding is not
discharged: the control is now enforced at the issuance point, but the finding's own record
is inconsistent and is not this plan's to reconcile.

- **Canonical severity is MEDIUM**, per `.ai/audit/04-auth-login/findings.md` — not HIGH as
  this block's own brief assumed. That file carries a **second, stale, pre-existing
  `AUT-004` row reading `Low`**, added by commit `8060fcf` (*"chore(audit) done audit"*),
  sitting in the regression-impact table whose text claims the disabled user *"is blocked by
  the bot middleware"*. **The audit file therefore has two conflicting `AUT-004` rows.**
  Reconciling them belongs to whoever owns `.ai/audit/`, **not to this plan**, which is
  forbidden from touching that file.
- **Grounding for the downgrade.** The premise is **refuted** against Django 5.2.17, and the
  one unmediated issuance point is now **closed and tested** (`e106e0b`, 3 tests). But the
  field is read by **exactly one** production line (the new guard in `login_status`) and
  written by `is_active=True` **only** in `apps/seed/generators/users.py`, so the path is
  exercised **only by tests** — no production traffic reaches it. And **no tripwire prevents
  a future refactor moving the guard below `auth_login`**: the guard's position is asserted
  by tests, not by a structural check. LOW, open.
- **The audit's "blocked by the bot middleware" claim is FALSE.** All **39** bot-side
  `is_active` references under `src/telegram_bot/` belong to `SavedSearch` (plus one
  `Category`); there are **zero** `User.is_active` references under that tree. The bot
  never authenticates a web session and never reads the flag. **Pre-existing — not this
  block's doing.** Recorded here so **phase 15 does not inherit it** as a premise.

---

#### Final test list for `G-5a` = A′

Named by module and test function. Assert **behaviour**, not implementation trivia. The
production change and the test change land in the **same commit** (§E).

| # | Test | Asserts |
|---|---|---|
| 1 | `apps/users/tests/test_login.py::TestLoginStatus::test_login_status_refuses_a_disabled_account` | An `is_active=False` user, valid **already-claimed** token, POST to the **real URL** `/login/status/`: response is **not 200** (it is **410**) **and** **no session cookie is set** (`client.session` carries no `_auth_user_id`) |
| 2 | `apps/users/tests/test_login.py::TestLoginStatus::test_login_status_burns_the_token_for_a_disabled_account` | After the denial the `LoginToken` row has `consumed_at is not None`, and a second POST of the same raw token returns **410**. **Documents the intended consequence**: the token is burned exactly as on the ban and the decline paths, so the two-phase handshake must restart |
| 3 | `apps/users/tests/test_login.py::TestLoginStatus::test_login_status_200_and_session_for_an_enabled_account` | The `is_active=True` control row: **200** and a populated session. The anti-over-reach guard — a guard that refuses everyone must fail here |
| 4 | `apps/users/tests/test_account_state.py::TestCanLogin` (all six) | **Unchanged**, green: `test_normal_user_can_login`, `test_banned_user_cannot_login`, `test_declined_user_cannot_login`, `test_banned_and_declined_cannot_login`, `test_deleted_user_can_login_by_flag` (**`deleted → True`**), `test_restricted_user_can_login` (**`ads_auto_publish=False → True`**). `can_publish_ad`, `get_state_badge`, `AccountState`, `get_account_state` are **not touched** |
| 5 | `src/telegram_bot/tests/test_account_state_middleware.py` (all of it) | **Green with no edits.** Includes `TestCrossPredicateAgreement::test_matches_explicit_formula` (its parametrizations never set `is_active`) and `TestCrossPredicateAgreement::test_blocks_when_can_login_blocks` |
| 6 | `apps/users/tests/test_login_token.py::TestLoginHandshakeOwnership::test_consent_view_has_no_token_logic` | **Green unchanged.** `consent.py` contains none of `hashlib`, `secrets`, `LoginToken`, `UPDATE login_tokens`, `.update(consumed_at=` |
| 7 | `apps/users/tests/test_login.py::TestLoginStatus::test_login_status_410_user_banned` | **Green unchanged** — the ban path is untouched |
| 8 | `apps/users/tests/test_consent.py::TestLoginStatusNoPii::test_login_consume_no_raw_telegram_id` | **Green unchanged.** `caplog.at_level("INFO")` captures the new `warning` too, and it asserts `str(telegram_id) not in caplog.text` — so the new log line **must** use `mask_telegram_id(telegram_id)` |
| — | Option (B) | **No test is written.** The option is recorded as **permanently unavailable** with the three-blocker proof above. Shipping a test for it would assert a behaviour the project cannot implement |

**Option (C)'s known-gap test is not applicable** — `G-5a` = A′ is a closing option, so
test 1 is the residual proof with the closed result. *(Had (C) been chosen, test 1 would
have been a **named** known-gap test documenting today's 200+cookie behaviour, and that
naming would have been part of the acceptance.)*

**Gates.** `G-3` ✅ **CLOSED** (option (i), `B-05` first — by the `B-01` Planner, 2026-10-01;
`B-01`'s `fieldsets` must therefore be built on a model that **still has** `is_active`).
`G-5a` ✅ **CLOSED** (option A′ — by the `B-05` Planner, 2026-10-01). **No gate remains open
for this block.**

**Agents.** Implementor (ships) · Planner (`G-5a` ✅, `G-3` ✅ — both closed) · Validator
(**re-bands the severity** — the premise changed, and the source plan assigns re-banding to
the Validator, **not** the Implementor) · Auditor **done** (`C-22` confirmed against
Django 5.2.17; the reader/writer census enumerated — nothing outstanding) · Researcher
**not required** — its mandate was the enforce-vs-remove question, and `G-3` plus the option-B
proof settled it.

**Risks — accepted and recorded.** The **false sense of a security fix** (the primary
risk): the change is real but narrow, and the mandatory framing is *"no session cookie is
issued on a disabled account; the token is still burned, exactly as on the ban and decline
paths, so the two-phase handshake must restart"*, never *"the account is now
protected"*, because Django already 302s on the next request. The **Validator owns
enforcing that wording.** · A **token-burn side effect** on the denial path: intended, and
matched to the ban and decline paths, but it forces a full restart of the two-phase
handshake — asserted explicitly by test 2 so it is a decision, not a surprise. · A
**caplog interaction**: the new `warning` is captured by an existing PII test, so the line
must use `mask_telegram_id`. · **No migration collision with `B-03`** — this block creates
no migration, so `0003_*` stays free. · A **severity that stays HIGH** after the premise is
refuted, sending a search for a defect that does not exist — the **Validator**'s to fix.

**Rollback.** Delete the guard and its log line from `login_status` — one block, no
migration, no data change, no reversion. The token-burn behaviour reverts with it.

**Definition of done.** The three new tests green in the same commit as the production
change · tests 4–8 green **unchanged** · `MIDDLEWARE` byte-unchanged at **15** entries with
`DbLockTimeoutMiddleware` at position 6 · `src/backend/apps/users/migrations/` untouched
and `makemigrations --check` clean (vacuously — no model change) · `git diff` shows
**no** `src/telegram_bot/**` file, **no** conftest, **no** `account_state.py` change ·
`G-3` and `G-5a` both recorded with authors and dates · **the Validator has recorded a
re-banded severity for `04-AUT-004` against the corrected premise** · the commit message
uses the mandatory framing above.

**Implementor brief.**

```yaml
id: 04-b05-is-active-resolution
title: Refuse the session cookie for a disabled account in login_status
priority: high
depends_on: [G-3 closed, G-5a closed]   # both CLOSED 2026-10-01; this block has no open gate
source_reference: .ai/plans/04-auth-login-remediation.md
source_section: BLOCK 4 — is_active kill-switch
source_blocks: ["BLOCK 4", "04-AUT-004"]
description: >
  G-5a is CLOSED as option A, variant A' — a dedicated is_active guard inside
  login_status. It sits strictly after the User lookup and strictly before auth_login,
  the view's first session write. The change buys exactly one thing, and the commit
  message must say so in these words: "no session cookie is issued on a disabled account.
  The token is still burned, exactly as on the ban and decline paths, so the two-phase
  handshake must restart." It does NOT mean "the account is now protected" —
  django.contrib.auth's ModelBackend already discards the identity on the very next
  request, so today's cookie is a write-only artefact. The premise of 04-AUT-004
  ("invisible end to end") is refuted; the residual is this one issuance point.
goals:
  - "POST /login/status/ for an is_active=False account returns 410 and sets no session cookie"
  - "the refusal logs its own accurate reason code via mask_telegram_id, never reusing the hardcoded 'banned' message"
  - "no middleware, no decorator, no new shared predicate, no migration, no NamedTuple change"
  - "the token-consumption consequence is asserted as intended, matching the ban and decline paths"
severity_note: >
  DO NOT touch the severity of 04-AUT-004. The premise is materially wrong and RE-BANDING
  BELONGS TO THE VALIDATOR, not the Implementor (source plan §6.2 item 10; §F.2 risk 6).
  It is not in your file surface, your diff, or your commit message.
phase15_decision: >
  Recorded in the B-05 section under "Decision record for phase 15". Summary: phase 15's
  carve-out of is_active from 15-AUTHZ-001's DENY set is SUPPORTED, for a corrected
  reason — is_active is enforced by ModelBackend, one layer BELOW phase 15's gate, so a
  DENY term there would be unreachable. Keep it out of the DENY set; record it as a
  Django-owned pre-gate term. Phase 15 needs no code change. Do not add anything to a
  phase-15 artefact from this block.
files:
  - path: src/backend/apps/users/views/consent.py
    targets:
      - type: function
        name: login_status
        semantic_anchors:
          insert_before:
            function_call: auth_login
          must_not_touch: [login_issue, consent_accept, consent_decline, consent_withdraw, _reconcile_preferred_city_on_login]
  - path: src/backend/apps/users/tests/test_login.py
    targets:
      - type: class
        name: TestLoginStatus
        semantic_anchors:
          insert_after:
            function: test_login_status_410_user_banned
changes:
  - action: modify_code
    target: src/backend/apps/users/views/consent.py::login_status
    description: >
      Add a dedicated guard that tests user.is_active and returns HttpResponse(status=410).
      Placement is load-bearing: strictly AFTER the `User.objects.get(telegram_id=...)`
      lookup (the user object must exist) and strictly BEFORE `auth_login(request, user)`
      (the view's first session write). Emit its own `logger.warning` with a stable,
      greppable reason code — do NOT reuse the existing branch's hardcoded
      "Login denied for telegram_id=%s: banned" message, which is already inaccurate for
      the decline path and would become indistinguishable from a ban. Mask the id:
      `mask_telegram_id(telegram_id)`, which is already imported in this module. Keep it
      inline — a private helper for a three-line guard would be a new abstraction with no
      justification.
  - action: add_test
    target: src/backend/apps/users/tests/test_login.py::TestLoginStatus
    description: >
      Three new tests (1, 2 and 3 of the final test list). POST to the REAL url
      "/login/status/" with a valid already-claimed LoginToken, for a User created with
      is_active=False via make_user(..., is_active=False) — conftest's make_user already
      accepts **overrides, so NO conftest edit is needed and none is permitted. Assert
      behaviour: response is 410 and no session cookie is set; the token is burned
      (consumed_at is not None and a replay is 410); and the is_active=True control still
      gets 200 plus a populated session.
non_goals:
  - "adding a term to can_login — it is a publicly re-exported predicate and a §E.3 tripwire; the guard is deliberately self-contained"
  - "extending AccountState / get_account_state — a NamedTuple shape change with zero behaviour change for the bot"
  - "removing the is_active field — G-5a recorded option B as PERMANENTLY UNAVAILABLE: no supported RemoveField for an inherited AbstractUser field, and an absent field makes user_can_authenticate's getattr(user, 'is_active', True) FAIL OPEN while 500ing every /admin/** view"
  - "any change under src/telegram_bot/**"
  - "any change to MIDDLEWARE, any middleware module, any decorator, or any shared gate"
acceptance_criteria:
  - "G-5a = A' implemented, and ONLY A' — no option B/D work appears in the diff"
  - "test_login_status_refuses_a_disabled_account, test_login_status_burns_the_token_for_a_disabled_account and test_login_status_200_and_session_for_an_enabled_account are green"
  - "apps/users/tests/test_account_state.py::TestCanLogin is byte-unchanged and all six tests green, including test_deleted_user_can_login_by_flag (deleted -> True) and test_restricted_user_can_login (ads_auto_publish=False -> True)"
  - "apps/users/tests/test_login.py::TestLoginStatus::test_login_status_410_user_banned is byte-unchanged and green"
  - "src/telegram_bot/tests/test_account_state_middleware.py is green with NO edits"
  - "test_login_token.py::TestLoginHandshakeOwnership::test_consent_view_has_no_token_logic is green unchanged"
  - "test_consent.py::TestLoginStatusNoPii::test_login_consume_no_raw_telegram_id is green unchanged"
  - "MIDDLEWARE is byte-unchanged at 15 entries with DbLockTimeoutMiddleware at position 6"
  - "no migration was created; src/backend/apps/users/migrations/ is untouched (highest was 0002_alter_consentrecord_ip_address.py at B-05 time; HISTORICAL/SUPERSEDED — 0003_logintoken_browser_binding.py now exists from B-03; see §G.2's invariant: no existing migration edited or renumbered)"
  - "git diff shows no change to src/backend/conftest.py, to src/telegram_bot/conftest.py, to account_state.py, or to any users/admin.py"
  - "the new log line names a distinct reason and never reuses 'banned' for a different reason; it uses logger, never print()"
  - "the commit message states the mandatory framing: 'no session cookie is issued on a disabled account; the token is still burned, exactly as on the ban and decline paths, so the two-phase handshake must restart' — NOT 'the account is now protected'"
traps:
  - "The token is burned BEFORE the guard runs: consume_token commits consumed_at inside login_status's transaction.atomic() block, before the User lookup and before the can_login guard. The new guard is one more 410 site in that same already-burning family (the ban and decline denials burn the token the same way). Do not 'fix' the ordering, and do not move the guard inside the atomic() block."
  - "The guard must land strictly between the User lookup and auth_login(request, user). auth_login is the first session write; a guard after it is useless."
  - "consent.py must gain NONE of: hashlib, secrets, LoginToken, 'UPDATE login_tokens', '.update(consumed_at='. The existing import line already names consume_token/issue_token/ConsumeOutcome; do not add any reference to the LoginToken model or class name."
  - "The new logger.warning is captured by test_login_consume_no_raw_telegram_id, which asserts str(telegram_id) not in caplog.text at INFO level (warnings included). Always mask via mask_telegram_id(telegram_id)."
  - "The existing 410 branch's log hardcodes 'banned' and is already wrong for the decline path. Do not reuse it, and do not widen the change to fix it — that is a separate concern."
  - "login_status's decorator order is @require_POST outermost, @never_cache innermost. Do not change it, and do not change the route or the HTTP method."
  - "No print(), no bare except, no new dependency. If a fixed value is needed, use a StrEnum or a Final constant per the project rules — most likely none is."
  - "HEAD is drifting under phase 13. Re-read consent.py immediately before editing and stop and report on a concurrent change."
commands:
  test_fast: ".\Makefile.ps1 test"
  test_fresh_schema: ".\Makefile.ps1 test-recreate"
  targeted: "$dc run --rm -e PYTEST_OPTS=\"-k test_login_status\" test"
  lint: "uv run ruff check src/backend/apps/users/views/consent.py src/backend/apps/users/tests/test_login.py"
  typecheck: "uv run basedpyright src/backend/apps/users/views/consent.py"
  note: >
    Tests are Docker-only; `uv run pytest` on the host always fails. The reused test DB
    volume came out of a PostgreSQL crash-recovery: use --create-db (i.e.
    test-recreate) after any DB restart before concluding anything is broken. Setting
    PYTEST_OPTS REPLACES the defaults and loses --reuse-db and xdist parallelism.
rollback: "Delete the guard and its log line from login_status. No migration, no data change, nothing to reverse."
```

#### Validator outcome — `B-05` ACCEPTED (2026-10-01)

**ACCEPTED with zero required code changes.** Commit **`e106e0b`** — *"fix(users): refuse the
login cookie for a disabled account"* — **2 files, +87/−1**
(`src/backend/apps/users/views/consent.py`, `src/backend/apps/users/tests/test_login.py`).
The **fast gate result, independently verified by the Validator: `2598 passed`** on a
healthy DB, run with `--create-db`. No follow-up block is required for `B-05`, and no gate
is reopened by this acceptance.

**Both declared Implementor deviations were reviewed and UPHELD.**

| Deviation | Verdict | Why |
|---|---|---|
| A one-line edit to `login_status`'s docstring `Returns:` list, adding *"or account disabled"* to the **410** line | ✅ **upheld — required** | The docstring is the view's contract. Leaving it naming only *"user banned"* while the view also denies for a disabled account would make the contract stale on arrival. Not a scope creep; the opposite |
| Module-level `from conftest import make_user` in `src/backend/apps/users/tests/test_login.py` | ✅ **upheld** | The "established pattern" claim was **verified true**: `test_account_state.py` and `test_user_roles.py` both carry `from conftest import make_user` at module level (as do `test_consent.py` and `test_deletion.py` for other helpers). Not a conftest edit — `src/backend/conftest.py` is byte-unchanged, and §C.3's restriction on editing it is intact |

**Carry forward, do not re-litigate:** the shipped code, the three new tests, the placement
of the guard and the masked log reason code (`"account disabled"`) are **correct and
accepted**. The only defect found was in the **commit message prose**, traced to this
plan's own mandate and recorded above.

---


---

### B-06 — Credential recovery posture + the false password-reset claim (PLANNED)

| | |
|---|---|
| **Findings owned** | `04-VAL-005` (all of it), `04-AUT-005` (recovery half) |
| **Depends on** | `B-02` (`AUTH_PASSWORD_VALIDATORS`, soft) · `B-01` (`form = UserChangeForm`) · `B-03` (`ReadOnlyPasswordHashWidget`) |
| **Blocks** | `B-11` · phase 15 `15-AUTHZ-003` inherits the costed design (a) below |
| **Gates** | `G-6`, `G-6b` … **all closed 2026-10-02 by this Planner** |
| **Priority** | P2 · **Risk LOW** — and LOW *because* the privilege-granting surface is deferred out |

**Objective.** Stop the repository asserting a password-reset capability it does not have, and
record — on the record, for phase 15 — what the recovery capability would cost to build.

#### `G-6` — DECIDED: ship (b) + (c). Defer (a). Never build (a) or (b)-as-flow.

Letter warning, because two letterings collide. **§I.4's (a) = self-service email reset;
the Researcher's (a) = the admin password-change URL.** From here on the Researcher's letters
are used, since they name the two candidate *implementations* separately:

| Letter | Researcher meaning | Disposition |
|---|---|---|
| **(a)** | admin password-change URL (`get_urls()` + `user_change_password` + `change_password_form`) | **DEFERRED to phase 15 `15-AUTHZ-003`** |
| **(b)** | self-service email reset flow (`PasswordResetView` et al.) | **REJECTED — refused outright, never deferred** |
| **(c)** | documentation: correct the claim, document the real operator procedure | **SHIPPING** |

**(b) and (c) were never alternatives.** (b) is a *sentence* to be corrected, (c) is a *procedure*
to be repaired; they ship together as one documentation change. (a) was the only real decision.

**Why (b) is refused.** Its eligible population is **provably empty**: `PasswordResetForm.get_users()`
requires `is_active=True` **and** `has_usable_password()`, every seeded user has `make_password(None)`
→ unusable, `withdraw_consent` blanks `email` **and nulls `username`**, and nothing in production ever
writes a non-empty `email`. Worse, it has **no key**: `email` is not unique and not collected, and
`B-01` made it read-only, so there is no operator-managed address to reset *to*. And the only
password-consuming entry point in the entire application is Django's built-in `AdminSite.login`,
gated by `is_active and is_staff` — so a reset mail can only ever reach a staff account, i.e. it
*adds* an email-based takeover of the admin desk without reaching anyone else. It is **untestable
here** (no SMTP: `locmem` proves a token was rendered, not that mail arrives), so rule 2 bites
hardest — a green suite would not evidence the capability.

**Why (a) is deferred rather than shipped.** It is the cheapest surface in the phase
(0 templates, 0 URLs to write, 0 msgids) and it is still wrong *for this block*:

1. **It would be the most dangerous surface in the phase, shipped by the block with the least
   authority to review it.** `B-06`'s exit criterion is *"the finding this block exists for is a
   wrong decision under pressure"* — a documentation criterion. Phase 04 is not the authorization
   phase; `15-AUTHZ-003` owns the predicate registry and its acceptance criteria require a
   contract test across all five identities including a plain moderator. A new credential-write
   endpoint created by a docs block gets **no authorization review at all** — strictly worse than
   shipping it in phase 15 or not shipping it.
2. **It carries a verified takeover unless gated, and `get_urls()` cannot gate it.**
   Measured against the live tree: a plain `is_staff` moderator POSTing a valid password onto a
   **superuser's** row returns `302` and the superuser's credential **changes**. `ModelAdmin.get_urls()`
   has **no `permissions` hook** (unlike `withdraw_consent_action`, where `get_permissions` does the
   gating) — so the gate must live inside the view body, producing a *new local predicate* that
   `15-AUTHZ-003` must find, reconcile and test. That is §F.2's "second authorization gate ships".
3. **Its review cost is unbudgeted in phase 15.** ~55 lines is cheap in code; finding a foreign
   phase's credential surface, auditing it and writing its registry test is not. Phase 15 already
   reopens `apps/users/admin.py` for every `has_*_permission` body — one more method there is
   marginal *there*, and expensive *here*.
4. **The operator need is already met.** `manage.py changepassword <username>` works, enforces
   `AUTH_PASSWORD_VALIDATORS`, never puts the secret on argv, and takes 2–5 minutes if the username
   is known. Shipping (a) does not close this finding; it closes this finding *and* adds a surface.

**What each choice leaves broken — stated plainly:**

- **(a) chosen:** the rendered button becomes truthful, but a new credential-write surface ships with
  a local unreviewed predicate, and `B-01`'s "no privilege write on `UserAdmin`" invariant gains an
  exception.
- **(b) chosen:** a takeover vector for a population that does not exist, with no evidence a mail
  ever leaves the host.
- **(c) chosen:** six false claims die, the broken recipe is replaced with a **working, policy-enforcing,
  test-executed** procedure — and **the dead "Reset password" button survives** (a rendered 404 on a
  staff-only admin page), with credential recovery remaining CLI-only.

**The dead button survives. It is named, costed and assigned below — not fixed here.**

#### Corrections this Planner applies to the block's recorded inputs

1. **Six false `password-reset` claims in four files — not five in three.** `prod.py` ×2 (the
   `EMAIL_HOST` guard comment; the `EMAIL_BACKEND` pin comment, phase 02's surface — **reword in
   place, never moved**), `docker-deployment.md` ×3 (the `DJANGO_SECRET_KEY` env-table row; §
   *Rotating Secrets* step 4; the fail-fast table's closing paragraph), and `rollback.md` ×1 — **the
   row the audit missed**. Plus the broken § *Password Change* recipe. Honest replacement in all
   six: **"all signed tokens (sessions and CSRF tokens)"** — a Telegram `LoginToken` is a DB row
   with a `token_hash`, not a signed token. See `G-6f`.
2. **"Destructive illusion" is the *pre-`B-01`* state; the dead button is *new*.** The writable
   `password` `CharField` was written verbatim by `ModelAdmin.save_model` (`obj.save()`, no hasher),
   so `check_password` could never verify it — `identify_hasher` raised — and the raw hash was on
   screen. **The button did not exist then.** It arrives *only* because `B-01` moved `UserAdmin` to
   `form = UserChangeForm`, whose `password` field is `ReadOnlyPasswordHashField`, whose widget
   template (`django/contrib/auth/templates/auth/widgets/read_only_password_hash.html`) renders
   `<a class="button" href="{{ password_url|default:"../password/" }}">` **unconditionally** — and
   `password_url` is injected *only* by `django.contrib.auth.admin.UserAdmin.render_change_form`,
   which this project does not use. **The 404 is the one new harm `B-01` introduced**, and it stays
   **LOW** — post-`B-01` an operator gets a masked `safe_summary` and a dead link, never a broken
   credential. See `G-6i`.
3. **Django 5.2's `user_change_password` carries only `@sensitive_post_parameters_m`** — **not**
   `@csrf_protect_m` (`CsrfViewMiddleware` is in `MIDDLEWARE`; `csrf_protect` would be a second,
   redundant gate). Any future port must not add it.
4. **`ModelAdmin` has neither `user_change_password` nor `change_password_form`** — both live on
   `django.contrib.auth.admin.UserAdmin`. And `AdminConfig.ready()` calls **only** `autodiscover()`,
   so `auth.admin.UserAdmin` is **never registered**; `apps.users.admin.UserAdmin` is the sole
   registry entry for `User`. Re-basing onto it would import Django's `fieldsets`/`add_fieldsets`/
   `list_display`/`ordering`, which **name `is_staff` and `is_superuser`** and would silently hand
   back exactly the privilege writes `B-01` removed — so re-basing is a **regression**, not a cheap
   alternative to (a).
5. **`test_prod_requires_email_host` does not exist, and nothing asserts the guard fires.**
   `test_redis_url_required_in_production` *sets* `EMAIL_HOST="smtp.example.com"` to get *past* it,
   and `test_django_oneshot_does_not_bypass_prod_secrets` sets it empty but asserts only
   `ImproperlyConfigured` — satisfiable by the `SITE_URL` guard. Test 1 is therefore **new code in
   `config/settings/tests/test_settings_secrets.py`** (**not** `test_settings_defaults.py` as this
   block recorded), and it must assert the message **names `EMAIL_HOST`** or it is vacuous.
6. **Django's catalogs are per-app, and password coverage is partial.** `django/conf/locale/` is
   *core only* (349 msgids in `ru`; even `Home` is absent). Admin strings live in
   `contrib/admin/locale/{ru,bs}` and `contrib/auth/locale/{ru,bs}`, both `.mo` compiled. Absent in
   **both** `ru` and `bs`: `Password changed successfully.`, `Password-based authentication was
   disabled.`, `Conflicting form data submitted…` — the view's own result strings. Absent in `bs`
   only: `Reset password`, `Set password`, `Disable|Enable password-based authentication`. So "Django's
   shipped catalogs cover them" is **partially false** — a shipped (a) would render mostly Russian,
   partially Bosnian, with an English fallback for the result banner. **Still zero project `.po` edits
   and zero gate breaks.** See `G-6h`.
7. **A `gettext()` call in `apps/users/admin.py` is a latent gate failure.** No gate scans Python for
   `gettext` today, but a future `makemessages` extracts the new msgids into the project catalogs with
   empty `ru`/`bs` msgstr and `test_no_empty_msgstr` then fails on `.po` files this block must not
   touch. **The trap-free shape is plain English literals**, matching the class's own recorded decision
   and `withdraw_consent_action`'s precedent.
8. **`make shell` is bash** (`Makefile:230`, `Makefile.ps1:215` both say "Bash in web container"), so
   the recipe's `from django.contrib.auth import get_user_model` line is a bash syntax error. Confirmed.
9. **`changepassword` is interactive and keyed on `USERNAME_FIELD`.** Positional `username`, **no
   `--password` flag**, reads via `getpass.getpass` (**requires a TTY** — `-T` breaks it), calls
   `validate_password(p2, u)` against the **persisted** user, then `set_password` + `save`. No
   project override. Because it prompts, it satisfies `D-2`/`D-3` **more** cleanly than the
   `ADMIN_PASSWORD`-based alternative this block had recorded.

#### Verified starting state (re-verified at `3cef5b2`, Django 5.2.17)

- **§ *Password Change* recipe:** says *"use Django's built-in password change command"* — correct,
  never names it — then shows `make shell` + a Python import (broken), then offers re-running
  `create_admin_user` because it is idempotent. `create_admin_user.handle()` checks
  `User.objects.filter(telegram_id=…).exists()` and **returns before any password write**, so that
  alternative is a verified **no-op**. Both must go; the command replaces them.
- **`EMAIL_HOST` guard — survives, and is load-bearing.** `_send_mail` in
  `telegram_bot/services/support_delivery_email.py` is the **only** mail sender in `src/`, reached from
  the Telegram `/support` handler via `SUPPORT_NOTIFICATION_RECIPIENTS` or EMAIL-channel
  `SupportContact` rows. It fails open at runtime, so the boot guard is what turns a misconfigured
  SMTP host into a boot failure instead of a silent support black hole. **`B-06` edits `prod.py`
  comments only; the guard expression is byte-unchanged** — and its parenthetical list is corrected
  too, because `send_mail`'s only real recipient is the support desk: "alert notifications" and
  "seller confirmations" are not senders either.
- **No reset surface, no eligible reset population.** `config/urls.py` registers only
  `path("admin/", admin.site.urls)`; no `PasswordResetView`, no `registration/` template, no
  `token_generator`, no `LoginView`, no `authenticate()` call, no `AUTHENTICATION_BACKENDS`, no
  `admin.site.login` anywhere in `src/`.
- **`create_admin_user` is the only production writer of `is_staff=True` / `is_superuser=True`**
  (`B-01` removed both from `fieldsets`). This bounds (a): a credential written onto a **non-staff**
  row grants no admin access, so (a)'s real harm is a *staff→staff* escalation — what `G-6c` gates.
- **`UserAdmin` declares exactly one `fieldsets`** and must still at phase exit.

#### Gates — all closed 2026-10-02 by this Planner

- **`G-6` → option (c)+(b) ship; option (a) deferred to phase 15.** Full argument above; costed
  handoff below.
- **`G-6b` (`U-5`) → YES, `changepassword` alone satisfies option (c).** It needs no `--password` argv,
  no `ADMIN_PASSWORD`, and no second command. **One limitation, which must be documented, not coded
  around:** it selects on `USERNAME_FIELD = "username"`, so a row whose `username` was **nulled** by
  `withdraw_consent` is unreachable by it — and such a row also has no usable password and no
  `telegram_id`, so it could not authenticate anyway. `(c)` therefore needs no `(c′)`.
- **`G-6c` (new) = `G-1` — who may use the view, *if* (a) ever ships.** Answered now so phase 15 does
  not re-derive it: **option (i), defer — which is the whole reason (a) is not in this block.** If
  phase 15 overrides and ships (a), the gate must be **`request.user.is_superuser` inside the view
  body** (option (ii)) — reusing `has_change_permission` (option (iii)) is **rejected outright**: it
  is a verified moderator→superuser takeover with no compensating control, and `B-01` exists precisely
  to deny privilege writes on `UserAdmin`. **Residual of (ii), stated honestly:** it is a *fifth*
  local predicate that `15-AUTHZ-003`'s registry contract test must discover and reconcile; the gate
  lives in a view body, so it is invisible to `get_permissions` and to any changelist-level review.
  If phase 15 ships (ii), the gate belongs in **one named predicate method** with a docstring naming
  `15-AUTHZ-003` — not inline.
- **`G-6d` (new) = `G-2` — ship `set_unusable_password`?** **KEEP it — no form subclass.** It is
  granted free by `AdminPasswordChangeForm` via `usable_password=false`, and (a) is the only place
  that reaches the non-staff population. But the reach is bounded: a credential on a **non-staff** row
  grants no admin access (`AdminSite.has_permission` needs `is_staff`, and `create_admin_user` is the
  only grant writer), so the harm reduces to **revoking a staff credential without the old password** —
  a legitimate incident-response action, and the only in-UI credential-revocation primitive. Removing
  it costs a form class (rules 4/7) and buys nothing. **Binding on phase 15: the superuser-only gate
  from `G-6c` is what makes this safe.**
- **`G-6e` (new) = `G-3` — repair the 404 or remove the button?** **Neither, and this is a decision,
  not a deferral of the question.** Repairing *is* option (a) — deferred. Removing it means forking
  Django's `auth/widgets/read_only_password_hash.html` into project templates purely to delete a link
  (the override contains no `{% trans %}`, so it would not even trip the i18n gate — but it would rot
  silently against Django upgrades), and it would delete the very control `15-AUTHZ-003` needs working.
  **`B-06` touches neither the widget, the form, nor the template.** The button stays, its 404 is
  recorded in the runbook as an owned gap, and phase 15 makes it resolve or removes it deliberately.
- **`G-6f` (new) = `G-4` — doc scope.** **Six statements in four files + one recipe**, per correction 1.
  `B-06` owns all four files *for these statements only*. `prod.py`'s **guard expression and
  `EMAIL_BACKEND` pin are untouched.** `docs/99-agent/architecture.md` was checked and needs **no**
  edit — it says "transactional email deliverability", which is true of the support desk.
- **`G-6g` (new) = `G-5` — replace the recipe with `changepassword`?** **YES, and the two wrong
  alternatives are deleted, not supplemented.** What it means for an operator who set a password under
  the old raw-`set_password` recipe: that recipe **bypassed `AUTH_PASSWORD_VALIDATORS`**, so the stored
  credential may be shorter than 10 characters, may be a common password, or may be built from the
  username. `changepassword` validates the **new** value against `AUTH_PASSWORD_VALIDATORS` **and, for
  the first time on any admin path, against the persisted user** — `UserAttributeSimilarityValidator`
  now sees the stored `username`/`email`. **Consequence: the change will be *refused* until a
  policy-compliant value is supplied, which is the intended tightening — and a weak credential
  already in the database stays weak until the next change.** The runbook must say exactly that, or
  the refusal reads as a broken command.
- **`G-6h` (new) — i18n posture for phase 15's (a).** **Plain English literals, no `gettext`, in the
  ported view** — per correction 7. Django's own chrome already renders localized from
  `contrib/admin/locale`; only the result banner falls back to English on a staff-only page. Promotion
  path, if phase 15 wants it: wrap the strings, then have the `.po` owner run `makemessages` in the
  same change. **Do not let phase 15 half-way: `gettext` added without `.po` entries is the exact
  latent `test_no_empty_msgstr` failure this block avoids.**
- **`G-6i` (new) = `G-7` — the `UserAdmin` docstring.** It documents `B-01`'s field contract in detail
  and never mentions the 404, so any outcome leaves it stale. **Update it in the same change:
  append** a short paragraph recording that `ReadOnlyPasswordHashWidget` renders "Reset password" →
  `../password/`, which 404s because `password_url` is injected only by
  `django.contrib.auth.admin.UserAdmin.render_change_form` and this class declares no `get_urls()`;
  that the button did not exist before `B-01`; and that the gap is owned by phase 15 `15-AUTHZ-003`.
  **Docstring only — no code, no URL, no form.** This is the block's single non-test `src/` edit.

#### Tests required

1. **`config/settings/tests/test_settings_secrets.py::test_prod_requires_email_host`** *(new)* — import
   `config.settings.prod` with **only** `EMAIL_HOST=""` and every other guard satisfied
   (`DJANGO_SECRET_KEY`, `BOT_TOKEN`, `GOOGLE_TRANSLATE_API_KEY`, `SITE_URL`, `REDIS_URL`,
   `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`), assert `ImproperlyConfigured` **and** that stderr names
   `EMAIL_HOST`. **Anti-vacuity is the whole point:** a bare `ImproperlyConfigured` assertion is
   satisfiable by `SITE_URL`'s guard and is not a test. **This is the guard-weakening gate for the
   comment correction.**
2. **`apps/users/tests/test_password_recovery.py::test_documented_password_change_procedure_works`**
   *(new module)* — **execute** the documented procedure: create a staff user with a known password,
   patch `getpass.getpass` inside the `changepassword` command module, `call_command("changepassword",
   username)`, then assert `check_password(new, user.password)` and that the stored hash changed.
   **Do not pattern-match the runbook text** — the procedure must be run, not grepped.
3. **`…::test_documented_procedure_refuses_a_policy_violating_password`** *(new)* — supply a value
   failing `AUTH_PASSWORD_VALIDATORS`; assert `CommandError` **and** that the stored hash is
   **byte-identical**. This is what pins `G-6g`'s tightening claim.
4. **Tripwires, unchanged and unedited:** `apps/users/tests/test_admin_change_form.py` (all six, incl.
   `test_add_view_stores_a_hashed_password`), `apps/ads/tests/test_i18n_completeness.py`,
   `apps/core/tests/test_create_admin_user.py`, `config/settings/tests/test_settings_defaults.py`.

**`B-06` changes **0** existing tests and deletes **none** — the §E.4 tripwire set is untouched, and
no test encodes the dead-button state, so nothing must be weakened. **`git diff --stat -- src/` lists
one non-test file, `apps/users/admin.py`, and its diff is a docstring** (`G-6i`).

#### Named known-gaps with owners

| Known gap | Owner | Status |
|---|---|---|
| **Dead "Reset password" button** in the admin user change form — `href="../password/"` 404s | **phase 15 `15-AUTHZ-003`** | named here, in the runbook, and in `UserAdmin`'s docstring. Design (a) costed below. `04-AUT-005`'s recovery half is **NOT closed** |
| **No credential recovery in the admin UI** (staff-only CLI route only) | **phase 15 `15-AUTHZ-003`** | same handoff |
| **A password set under the old raw-`set_password` recipe may violate the current policy** | **operator**, via the runbook | documented, not a code gap; no code can detect it without re-hashing |
| **A row whose `username` was nulled by `withdraw_consent` is unreachable by `changepassword`** | **none — accepted** | such a row has no usable password and no `telegram_id`; it cannot authenticate |
| **Self-service password reset** | **none — refused** | no population, no key, untestable here. If ever wanted it is a new feature needing an email-collection path, an enumeration guard and a real transport |
| **`set_unusable_password` would reach non-staff rows** | **phase 15 `15-AUTHZ-003`** | bounded by `G-6d`; moot until (a) ships |

#### Handoff to phase 15 `15-AUTHZ-003` — design (a), costed

**Not a plan; a measured starting point, so phase 15 does not re-derive it.** `apps/users/admin.py`,
`UserAdmin` only: add `get_urls()` (a `super()` call plus the fixed un-namespaced path
`path("<id>/password/", self.admin_site.admin_view(self.user_change_password), name="auth_user_password_change")`
— **`get_urls()` has no `permissions` hook**), `change_password_form = AdminPasswordChangeForm`, and
`user_change_password` (~55 lines, ported from `django.contrib.auth.admin.UserAdmin.user_change_password`:
**`@sensitive_post_parameters_m` only, no `csrf_protect`**; object-and-permission preamble; the
set-password vs unset-password conflict branch; `form.save()`; `construct_change_message` +
`log_change`; `messages`; `update_session_auth_hash`; own `fieldsets` from `form.base_fields` and own
`AdminForm`). **`AdminPasswordChangeForm`'s confirmation field is `password2` — not `new_password2`;
`new_password1`/`new_password2` are the *reset* form's.** POST keys for a user with a usable password:
`password1`, `password2`, `usable_password` (`"true"`/`"false"`), submit `set-password` or
`unset-password`; for a user without one, `password1`/`password2` (`required=True`) and `set-password`
only. Gate: `request.user.is_superuser`, in **one named predicate** per `G-6c`. Tests: hash changed +
`check_password`; weak password rejected; mismatch rejected **and hash byte-identical**; and the
permission gate (moderator → `403`, hash byte-identical). `ModelAdmin` builds its **own** `fieldsets`
for this view — `get_readonly_fields` is never consulted — so **all six `B-01` introspection tests stay
green and unedited**, and re-basing onto `auth.admin.UserAdmin` is **forbidden** (correction 4).
Note also that `update_session_auth_hash` rotates only the *actor's* session key; the **target's**
existing sessions die on their next request because the session auth hash is derived from `password`.

#### Out of scope

The `EMAIL_HOST` guard expression and its setting (never) · the `EMAIL_BACKEND` pin expression
(phase 02's; reword in place) · `config/urls.py` · any new URL, view, form or template · any `.po`
file · any `apps/` file other than the `UserAdmin` **docstring** · `LOG_MASK_KEY` (phase 06) ·
`withdraw_consent_action` · every `has_*_permission` body.

#### Agents

Implementor **yes** · Researcher **yes** (done — all thirteen findings re-verified at `3cef5b2`) ·
Planner **yes** (done — this section) · Validator **yes** — the finding this block exists for is
explicitly *"a wrong decision under pressure"*, and `G-6g` hands the operator a command that *refuses*
values the old recipe accepted, so the Validator must confirm the runbook says so. Auditor **no** —
**deviation, justified:** the changed surface is 6 comment/sentence edits in 4 files plus one docstring;
the absence facts (no reset URL, no view, no template, no eligible reset population, no non-staff
password login) are all verified above and re-runnable in one search each.

#### Risks

Correcting the claim while weakening the guard (mitigated by test 1, which asserts the guard message
names `EMAIL_HOST`) · rewording the `EMAIL_BACKEND` comment colliding with phase 02's ownership (§D
item 16) · editing `docker-deployment.md`/`rollback.md` on a stale read and clobbering phase 01's,
02's, 08's or 09's work (§D item 18 — **re-read both files immediately before editing**) · the
runbook documenting a command the operator cannot execute (mitigated by tests 2 and 3, which run it) ·
**the deferred button being mistaken for a finished capability** (mitigated by the runbook sentence,
the docstring, and the table above).

#### Rollback

Revert the commit. **No behaviour existed before it and none exists after**: the only `src/` change is
a docstring, and the two new tests assert against *pre-existing* behaviour (`prod.py`'s guard, Django's
`changepassword`), so reverting the docs cannot leave a behaviour behind and cannot orphan a test.

#### Definition of done

Tests 1–3 green · `test_admin_change_form.py`, `test_i18n_completeness.py` and
`test_create_admin_user.py` unchanged and green · **a tree-wide search finds no surviving
password-reset claim the code does not support — verified by searching the tree, not by trusting this
document** · the `EMAIL_HOST` guard expression, the `EMAIL_BACKEND` pin expression, all four
`has_*_permission` bodies and the single `fieldsets` on `UserAdmin` are **byte-unchanged** ·
`ruff`/`basedpyright` clean (docs and comments only) · **no `.po` file modified** · `G-6`, `G-6b`,
`G-6c`…`G-6i` recorded in §H · `E.7` written.

**Honest bottom line.** `B-06` can deliver the finding's closure — *every password-reset claim is now
true or gone, and the operator has a procedure that is executed by a test and enforces the policy the
old recipe bypassed*. It **cannot** deliver in-admin credential recovery, and the dead "Reset password"
button **survives** this block by decision, assigned to phase 15 with a costed design and a measured
harm rather than left as an unowned surprise. That is a legitimate completion under §F.1 only because
the gap is named, owned and costed; if phase 15 does not take it, the next honest move is a new
finding, not a quieter note.

#### Implementor brief

```yaml
id: 04-b06-credential-recovery-claim
title: Correct the false password-reset claim and document the real recovery procedure
priority: medium
depends_on: [G-6 closed, G-6b closed, G-6c..G-6i closed]
source_reference: .ai/plans/04-auth-login-remediation.md
source_section: BLOCK 5 — credential recovery / false password-reset claim
source_blocks: ["BLOCK 5", "04-AUT-005", "04-VAL-005"]
description: >
  The repository asserts a password-reset capability in two comments in
  config/settings/prod.py, three statements in docs/ops/docker-deployment.md and one in
  docs/ops/rollback.md, and has no reset URL, view, form or template. The documented
  "Password Change" procedure is broken as printed (make shell is bash, not a Django
  shell) and its stated alternative is a verified no-op. Correct all six claims, replace
  the recipe with manage.py changepassword, and pin the EMAIL_HOST guard with a test.
  Do NOT build the admin password-change view and do NOT build a self-service reset flow.
  The rendered "Reset password" button stays a known gap owned by phase 15 15-AUTHZ-003.
goals:
  - "no surviving statement claims password-reset behaviour the code does not have"
  - "the EMAIL_HOST fail-fast guard expression and the EMAIL_BACKEND pin are byte-unchanged"
  - "the documented procedure is changepassword, which prompts and never puts the secret on argv"
  - "the runbook states that changepassword refuses values the old recipe accepted"
  - "the runbook names the dead Reset password button and its owner (15-AUTHZ-003)"
extra_context: >
  All binding constraints are in the prose above (Decision / Corrections 1-9 / Gates /
  Out of scope / Definition of done). Read them before editing.
files:
  - path: src/backend/config/settings/prod.py
    targets:
      - type: comment
        name: "the EMAIL_HOST fail-fast guard comment - reword the parenthetical only"
      - type: comment
        name: "the EMAIL_BACKEND pin comment (phase 02's surface - reword in place, never move)"
  - path: docs/ops/docker-deployment.md
    targets:
      - type: section
        name: "the env table's DJANGO_SECRET_KEY row"
      - type: section
        name: "the secret-rotation steps"
      - type: section
        name: "the secret-validation paragraph"
      - type: section
        name: "the Password Change section - replace the whole recipe"
  - path: docs/ops/rollback.md
    targets:
      - type: section
        name: "the DJANGO_SECRET_KEY row in the rollback/secret table"
  - path: src/backend/apps/users/admin.py
    targets:
      - type: comment
        name: "the UserAdmin class docstring - append the dead Reset password button record"
  - path: src/backend/config/settings/tests/test_settings_secrets.py
    targets:
      - type: function
        name: test_prod_requires_email_host
  - path: src/backend/apps/users/tests/test_password_recovery.py
    targets:
      - type: function
        name: test_documented_password_change_procedure_works
      - type: function
        name: test_documented_procedure_refuses_a_policy_violating_password
changes:
  - action: modify_doc
    description: >
      In each of the six false statements, replace "password-reset" with the artifacts the
      secret key actually signs - all signed tokens (sessions and CSRF tokens). A Telegram
      LoginToken is a database row with a token_hash, not a signed token.
  - action: modify_doc
    description: >
      Replace the Password Change section's recipe with
      docker compose --env-file .env.prod -f docker-compose.yml
      -f docker-compose.prod.yml run --rm web
      /opt/venv/bin/python src/backend/manage.py changepassword <username>
      Use /opt/venv/bin/python, not uv run - a one-shot run container can fail with a
      read-only /opt/venv. Keep the TTY (no -T): the command reads via getpass. Delete the
      "use make shell" block and delete the create_admin_user alternative - it is a verified
      no-op, because create_admin_user returns before any password write when telegram_id
      exists. State that the username is USERNAME_FIELD, that changepassword enforces
      AUTH_PASSWORD_VALIDATORS against the new value and, for the first time, against the
      persisted user, and that a credential set under the old recipe stays weak until the
      next change.
  - action: modify_comment
    description: >
      Append to UserAdmin's docstring: the ReadOnlyPasswordHashWidget renders "Reset
      password" -> ../password/, which 404s because password_url is injected only by
      django.contrib.auth.admin.UserAdmin.render_change_form and this class declares no
      get_urls(). Recorded as a known gap owned by phase 15 15-AUTHZ-003. Do not add
      get_urls. The button did not exist before B-01.
  - action: add_test
    description: >
      test_prod_requires_email_host: import config.settings.prod with ONLY EMAIL_HOST=""
      and every other guard satisfied, assert ImproperlyConfigured AND that stderr names
      EMAIL_HOST. A bare ImproperlyConfigured assertion is satisfiable by SITE_URL's guard
      and is not a test.
  - action: add_test
    description: >
      test_documented_password_change_procedure_works: create a staff user with a known
      password, monkeypatch getpass.getpass inside
      django.contrib.auth.management.commands.changepassword, call_command("changepassword",
      username), assert check_password(new, user.password) and that the hash changed.
      test_documented_procedure_refuses_a_policy_violating_password: supply a value
      failing AUTH_PASSWORD_VALIDATORS, assert CommandError and that the stored hash is
      byte-identical.
acceptance_criteria:
  - "all three new tests green; the four tripwire files unedited and green"
  - "the EMAIL_HOST guard expression, the EMAIL_BACKEND pin expression, all four has_*_permission bodies and the single fieldsets on UserAdmin are byte-unchanged"
  - "a tree-wide search finds no surviving password-reset claim the code does not support"
  - "no .po file is modified and no new msgid is introduced"
  - "the documented procedure was executed by tests 2 and 3, not pattern-matched"
  - "no admin password-change URL, no PasswordResetView, no registration/ template, no config/urls.py entry exists at block exit"
tests_to_run:
  - src/backend/config/settings/tests/test_settings_secrets.py
  - src/backend/apps/users/tests/test_password_recovery.py
  - src/backend/apps/users/tests/test_admin_change_form.py
  - src/backend/apps/core/tests/test_create_admin_user.py
  - src/backend/apps/ads/tests/test_i18n_completeness.py
```

<!-- superseded 2026-10-02 by the B-06 Planner: see the section above -->

---

### B-07 — Session revocation at account-state transitions (`04-AUT-002`, session half)

| | |
|---|---|
| **Findings owned** | `04-AUT-002` (**record and hand-off only — the ban-path substance is NOT closed by this block**), `04-VAL-001` (the "no second gate" rule) |
| **Depends on** | `B-01` (soft — `G-B`'s decision cites its retired form writes) · `B-05` (soft — same file) · `B-03` (hard — same file) · **`G-7`, `G-7b`, `G-A`, `G-B`, `G-D`, `G-E`, `G-F` — ALL SEVEN CLOSED 2026-10-02 by the `B-07` Planner** |
| **Blocks** | phase 15 `15-AUTHZ-001` (**the named owner of every residual below**) |
| **Priority** | P2 · **Risk LOW for the code, HIGH for the residual** |
| **Gates** | **`G-7` CLOSED** (option (b), zero production code) · **`G-7b` CLOSED** (option (b), do not ship) · **`G-A` CLOSED** (out) · **`G-B` CLOSED** (do not register) · **`G-D` CLOSED** (known-gap test) · **`G-E` CLOSED** (re-file) · **`G-F` CLOSED** (phase 15's migration) |

> **B-07 SHIPS NO PRODUCTION CODE. This is the decision, and it is recorded here so it
> cannot be read as an omission.** The Researcher's findings **refuted the block's premise**:
> the third-party PII exposure is already closed at three independent layers, the per-request
> gate belongs to phase 15, and of five open transitions exactly **one** is reachable — and
> that one **cannot be fixed by a `logout()`**, because the request it holds is the
> *moderator's*, not the target's. What `B-07` delivers is a **measured, executed,
> named known-gap suite** plus seven closed gates and four plan corrections. Read
> **"Honest bottom line"** at the end of this section before starting.

> **Supersedes three rows elsewhere in this document, which are left unedited because §A is
> a shared provenance section this Planner may not touch.** `§A.3`'s `B-07` row
> ("re-scoped (3 of 5 paths reachable, not 2)"), `§A.4`'s `C-17` ("**3 of 5 paths reachable,
> not 2**") and `§A.4`'s `X-3` are **all refuted by this section**: the count is **1 of 5**,
> and `ban_user`'s reachability premise is false. **Where they conflict, this section wins.**
> `§A.4`'s `C-3` ("no `clearsessions` janitor") is **confirmed** and is re-filed by `G-E`.

**Objective — REVISED 2026-10-02.** Convert `04-AUT-002` from an unmeasured open defect into
a set of **named, executable, owner-assigned known gaps**, and correct the plan's refuted
premises. No `logout()` is shipped, no gate is added, and `04-AUT-002` is **NOT closed**.

**Verified starting state — re-derived at `9ef5151` (do not trust the counts; re-derive).**
Five transitions; **one is closed, one is correct, and of the three open ones exactly one is
reachable** — and the reachable one is unreachable *for this block's subject*.

| Path | Whose `request`? | Target identity | State |
|---|---|---|---|
| `users/views/consent.py::consent_withdraw` | the subject's (`@login_required @require_POST`) | `request.user` | **CLOSED** — `withdraw_consent(user)` then `logout(request)`, comment naming `AUT-002`. Pinned by `test_withdraw_flushes_session_and_redirects` and `test_withdraw_workflow_returns_anonymous` |
| `users/views/consent.py::consent_accept` | the subject's | `request.user` | **CORRECT — no logout belongs here.** Accept restores capability; `give_consent` clears a prior decline. Untouched |
| `users/views/consent.py::consent_decline` | the subject's (`@require_POST`, anonymous-accessible) | `request.user` — *the requester is the changed identity* | open — **REACHABLE, and `G-7b` decides NOT to ship** (verified one-way door; see the gate) |
| `users/admin.py::UserAdmin.withdraw_consent_action` | a **moderator's** | in `queryset`, never `request.user` | open — **UNREACHABLE, and never registered** — see "Correction applied" below; `G-B` decides **do not register** |
| `moderation/views/review.py::ban_user` | **the moderator's** (`@staff_required`) | `ad.user` | open — **REACHABLE, and this is the concrete harm. `G-D` decides NO CODE, because `logout(request)` here logs out the *moderator*.** See the wrong-target trap below |

**The reachability count is 1 of 5, not 3. The plan's "3 of 5" is REFUTED and withdrawn.**
`moderation/views/review.py::ban_user` is decorated `@staff_required`, so inside its body
`request.user` is **the moderator**, while the identity that changed is `ad.user`
(`ban_user_for_ad(ad, request.user.id, …)` passes the *moderator's* id as `moderator_id`).
`django.contrib.auth.logout(request)` **has no parameter for a target user** — it flushes
`request.session`. So "has a `request`" is satisfied and the change is still impossible. The
plan's earlier correction (`C-17`, 2026-10-01) moved the count 2 → 3 on the premise that
`ban_user`'s request identifies the target. **That premise is false.** `B-07` corrects it to
**1 of 5** and records `G-D`.

`moderation/admin_actions.py::ban_user_for_ad(ad, moderator_id, reason)` — no `request`;
`with transaction.atomic():` → `User.objects.select_for_update().get(id=ad.user_id)` →
early return on `DoesNotExist` → `user.is_banned = True`,
`user.save(update_fields=["is_banned"])` + `log_ban_account(...)`.
`moderation/admin_actions.py::bulk_ban_users(queryset, moderator_id, reason)` — no
`request`; `user_ids = set(queryset.values_list("user_id", flat=True))`; inside one
`atomic()` it loops `log_ban_account(...)` per id, then a single
`User.objects.filter(id__in=user_ids).update(is_banned=True)`. **No per-user object, no
`select_for_update`, and no `OperationalError`/`is_lock_timeout` boundary** (`D-8` — the
only one of the four bulk helpers without one; **do not add one**).
`users/services/deletion.py::withdraw_consent(user)` — inside one `atomic()`: returns
`[]` when `user.is_deleted`, else deletes `LoginToken.objects.filter(telegram_id=…)`
**before** nulling `telegram_id`, then sets the flags and nulls the PII in one
`update_fields` save, then calls `soft_delete_user_ads(user)`.

**Why Django cannot enumerate another user's sessions — re-verified and sharpened
2026-10-02.** `django_session` has **three** columns: `session_key` (PK), `session_data`
(`TextField`), `expire_date` (indexed). **No user column, no reverse index, no FK.**
`SessionBase.encode` is `signing.dumps(..., compress=True)` — **zlib-compressed, base64,
HMAC-signed, never encrypted.** Verified: `'_auth_user_id' in session_data` is **`False`**
and so is `'42'`, so a `LIKE` scan is **impossible**, not merely slow. A decode scan works
but costs **O(live sessions)** — a zlib decompress plus an HMAC verify per row — and
exact-match construction is impossible because the decoded dict also carries
`_auth_user_hash`.

**The project stores nothing that would make it cheap, and the one candidate is
*incorrect*, not slow.** `ConsentRecord.session_key` (`apps/users/models.py`) is
`CharField(max_length=40, null=True)` — **unindexed**, written only on a consent action —
and it is **dead for this purpose** because `auth_login` calls `cycle_key()` on the
anonymous→authenticated transition, so the consent-time key is **not** the authenticated
key. Using it would silently fail to match live sessions. **Do not use it.**

**The retention consequence, and why the missing janitor compounds it.** `SESSION_ENGINE`
and `SESSION_COOKIE_AGE` are **unset in every settings module** (only `SESSION_COOKIE_SECURE`,
`SESSION_COOKIE_HTTPONLY` and `SESSION_COOKIE_SAMESITE` are declared — `base.py`, `dev.py`,
`prod.py`, `test.py`), so the backend is DB and the lifetime is Django's 14-day default.
`clearsessions` appears **nowhere** in `src/`, `docs/`, `docker/`, `.github/`, `Makefile` or
`Makefile.ps1`. The table is therefore **unbounded in row count**, which is what makes an
O(n) decode scan unattractive *and* what makes a privacy problem on the session blob
persist after logout is impossible.

#### The wrong-target trap in `ban_user` — CONFIRMED, and it is worse than the plan assumes

**⚠ This is the single most dangerous thing an Implementor could do in this block, and the
entire existing test suite would not catch it.** `ban_user` is `@staff_required`; its
`request` carries the **moderator**. `django.contrib.auth.logout(request)` flushes
`request.session` and takes **no target-user argument**. Adding `logout(request)` to
`ban_user` therefore logs out **the moderator who just issued the ban** and leaves the
banned seller's session **fully live**.

**How completely invisible it is — verified, not estimated.** **Five** tests, not four, would
stay green, and the fifth is itself a source-introspection test that is *indifferent* to the
addition:

| Test | What it asserts | Why a wrong-target `logout(request)` passes it |
|---|---|---|
| `apps/moderation/tests/test_moderation_views.py::TestBanUserView::test_ban_marks_user_as_banned` | `status_code == 302`, `seller.is_banned is True` | never inspects a session |
| `…::TestBanUserView::test_ban_creates_moderation_log` | a `ModeratorActionLog` row exists | never inspects a session |
| `…::TestBanUserView::test_ban_requires_post` | GET → `302`, `seller.is_banned is False` | never inspects a session |
| `…::TestBanUserView::test_ban_defaults_reason_when_not_provided` | `302`, `seller.is_banned is True` | never inspects a session |
| `…::TestModerationReviewLocking::test_ban_user_uses_select_for_update_and_atomic` | `inspect.getsource(review.ban_user)` contains `"transaction.atomic"` and `"select_for_update"` | a **substring** check — adding any statement leaves both substrings intact |

All five `force_login(staff_user)`. **The ban path therefore gets no code from this block, and
`G-D` converts the trap into a named known-gap test instead of a prohibition alone.**

#### The contact leak is ALREADY CLOSED — `04-AUT-002` must not be sized against it

`apps/core/services/contact.py::_check_seller_contactable(ad, seller)` returns `True` only
when **all five** hold: `ad.status == PUBLISHED` **and** `seller.telegram_id is not None`
**and** `not seller.is_deleted` **and** `not seller.is_banned` **and**
`seller.consent_revoked_at is None`. It is enforced at **three independent layers**:
`can_contact_seller` per render (`contact_tags.py::can_contact`), re-evaluated at delivery in
`get_seller_for_contact`, and the bot's `AccountStateMiddleware` blocks the relay — with three
tests proving ban / decline / delete / revoke each block it.

**Consequence for scoping: no third-party PII survives a ban today.** A finding described as
"a session survives a ban" is not the same finding as "a buyer's contact details leak after a
ban", and pricing the block as the latter overstates it. The web tier's real defect is
narrower and is named in `G-A`'s consequence below.

#### Correction applied — `withdraw_consent_action` is unreachable, and always was (MEDIUM)

**This block's starting state was wrong about the admin action, and so was `B-01`'s.**
The premise recorded above — that `UserAdmin.withdraw_consent_action` *"is gathered by
`ModelAdmin.get_actions` from the changelist"* — is **false**. Verified against
Django **5.2.17** and the live class:

- `ModelAdmin.actions = ()`. `UserAdmin` declares **no** `actions`, and never did.
- `ModelAdmin._get_base_actions` gathers **only** `self.actions` and
  `self.admin_site.actions`. `AdminSite.actions` is `{"delete_selected": …}`, and
  `delete_selected` carries `@admin.action(permissions=["delete"])`, so it is gated on
  `has_delete_permission` → `is_superuser`.
- **Measured:** `get_actions` as staff → `[]`; as superuser → `['delete_selected']`;
  `get_action_choices` for staff → `['']`.
- `@admin.action(description=…)` **alone** puts nothing in `get_actions`. The decorator
  marks the callable; it does not register it.
- **It is dead, not merely hidden.** `ModelAdmin.response_action` sets
  `action_form.fields["action"].choices = self.get_action_choices(request)`, a
  `ChoiceField`, so a **crafted POST cannot reach it either**.

**Pre-existing, not a `B-01` regression.** `git diff -U0 a19a0ee^ a19a0ee -- src/backend/apps/users/admin.py`
shows `withdraw_consent_action` as unchanged context and adds **no** `actions`
declaration. The action was already dead before `B-01` shipped. **Do not charge this to
`B-01`,** and do not revert `B-01` over it.

**Consequently, registering it is a NEW, IRREVERSIBLE operator capability — and it must
sit behind `B-7`, not be done incidentally.** The action nulls PII, soft-deletes users
*and their ads*, and deletes `LoginToken` rows. There is no inverse. `G-7` must decide it
explicitly, and if it decides to register it, **both** of the following are required:

| # | Required change | Why |
|---|---|---|
| 1 | **add** `actions = ("withdraw_consent_action",)` on `UserAdmin` | without it `get_actions` never yields the callable at all; the decorator is not a registration |
| 2 | **amend** the decorator to `@admin.action(permissions=["change"], description=…)` | `UserAdmin.has_change_permission` is `is_staff` **and ignores `obj`** (`15-AUTHZ-003` owns the predicate). Without an explicit `permissions` list the action is offered to **every** `is_staff` holder, so registration alone would widen the blast radius to the whole staff population |

**The test that would have been written (`G-7` = register) is NOT written — `G-B` chose
do-not-register, and this test is therefore out of scope.** Recorded so the omission is
traceable: assert `"withdraw_consent_action" in UserAdmin(User, admin.site).get_actions(request)`.
**Do NOT assert on `UserAdmin.actions`** — a previous attempt at exactly that test was
deleted from `B-01` as a defect, because it pinned the defect as the expected state and
pointed the tripwire the wrong way. `get_actions` is the observable; the class attribute
is the implementation. **And do not assert the *absence* of the action** — that would pin an
intentional decision as an invariant and would have to be deleted the moment phase 06
reverses `G-B`.

**File surface — RESOLVED by `G-B` (do-not-register): `src/backend/apps/users/admin.py` is
NOT touched at all.** No `actions` attribute is added and the decorator is not amended. The
method **body** is byte-unchanged — phase 06 `PII-107` owns the `ConsentRecord` write (§D
item 8). See `G-B` for the two reasons, the second of which is new and decisive.

#### Phase-06 record — `PII-107`: no operator-reachable erasure trigger exists (MEDIUM)

**After `a19a0ee` there is no operator-reachable `withdraw_consent` trigger on the `User`
admin at all.** `B-01` deliberately retired the unaudited form writes for `is_deleted` /
`is_declined` / the consent booleans, on the stated understanding that the changelist
action was to become the only sanctioned operator erasure path — **and it does not
exist.** Four facts, recorded so phase 06 cannot read more into the state than is there:

1. **The data-subject path is unaffected.** `apps/users/views/consent.py` →
   `consent_withdraw` (`@login_required @require_POST`) still calls
   `users/services/deletion.py::withdraw_consent(user)` and is **CLOSED** (row 1 above).
   **GDPR withdrawal by the subject still works, and `B-01` did not touch it.**
2. **The writer/trigger asymmetry must be stated, not papered over.** A `PII-107`
   closure statement of the form *"every consent-state transition goes through the
   audited service"* is **true of the writers** — there is no other writer — but there is
   **no audited operator path to trigger it**. **Record the asymmetry explicitly. Do not
   write a closure sentence that implies an operator path exists.** This is a record only;
   **no phase-06 artefact is edited from this plan.**
3. **No compensating capability was silently lost.** `B-01` retired the (unaudited) form
   writes for `is_deleted` / `is_declined` as a **decision**, recorded in `B-01`'s
   operator-capability table — not as an omission and not in reliance on the action
   existing. Removing them is correct on its own terms (a form write bypasses the
   `transaction.atomic()`, the PII nulling, the `LoginToken` deletion and the
   `bump_search_cache_version` on commit).
4. **The gap is `B-07`'s to record, phase 06's to accept — and `G-B` has now decided it.**
   `G-B` = **do-not-register**, so the operator erasure capability is **absent by decision**,
   and that decision — **not the absence** — is what phase 06's `PII-107` note must cite.
   **Add the second reason, because it is the one that actually decides it:** registering the
   action while `G-A` is out would hand a moderator a reachable erasure path whose subject's
   sessions cannot be invalidated, because the request is the moderator's (`G-B`).

**Extra constraint the source plan did not name.** `withdraw_consent`'s idempotency is
pinned by `apps/users/tests/test_consent.py::TestConsentWithdrawIdempotency`,
**including that no `LoginToken` deletion happens on the no-op path**. That test must
stay green and unedited.

#### `G-A` — CLOSED: the decode-scan revocation service is **OUT** (`04-AUT-002`, ban path)

**Decision: option (i) — out, with a loud named known-gap and a named owner (phase 15,
`15-AUTHZ-001`). Not deferred silently, and not deferred to "later".**

The only two mechanisms that could revoke a **banned** user's sessions are (a) an O(live
sessions) decode scan and (b) a per-request account-state check. **Both are owned by other
blocks, and shipping either from here is wrong on the record:**

| Rejected mechanism | Why it is not `B-07`'s to ship |
|---|---|
| **O(n) decode scan + `on_commit` hook** | It would run inside `ban_user`'s already-locked window — `ban_user` holds `Ad.objects.select_for_update()` and `bulk_ban_users` holds one `atomic()` across every `log_ban_account` insert, which is exactly what phase 03's `DB-004` pushed back on. Widening a row-lock window with an unbounded table scan is a DB-concurrency regression in a block whose finding is not about concurrency. It is also a **design collision**: the scan closes the *same* window phase 15's `15-AUTHZ-001` gate closes — permanently and at zero per-request cost — so phase 04 would ship a second, worse mechanism for one invariant, and phase 15 would inherit a second thing to remove. Rule 5 and rule 7 both point out. There is no index to add that would change the asymptotics, and the one column that looks like a shortcut (`ConsentRecord.session_key`) is **wrong**, not slow — see above |
| **A per-request account-state check** | `04-VAL-001` forbids it from this phase, and it is phase 15's `15-AUTHZ-001` by design. `MIDDLEWARE` is a pinned 15-entry list (`base.py`); a user/session-epoch column plus a middleware comparison is a migration plus a second gate. **This is the mechanism that actually closes the harm, which is precisely why deferring to its owner is correct rather than lazy** |

Option (iii), "defer entirely to phase 15", is what this **is** — but it is recorded as
option (i) plus a named known-gap, because the difference is the *record*: a phase-15 owner
must be able to find this by grepping the plan, and a coordinator must be able to see that
the phase knowingly accepted it.

**The honest security consequence — stated plainly, because "out" must never be silent:**

> **A banned seller who is already holding a web session keeps it for the remainder of its
> 14-day life, and can therefore still reach the dashboard, ad edit, archive, reactivate,
> delete, cabinet, settings, favourites, saved searches, search history and seller
> analytics. Worse, the sanction is defeatable: `ad_edit` and `ad_reactivate` have NO
> account-state check, `ad_reactivate` calls `auto_moderate(ad)` inline, `ad_edit`'s
> text-change branch routes to `submit_ad(...)` which also runs `auto_moderate` — and
> `auto_moderate` reads only `ModerationCriteria` and never `is_banned`. So a banned seller
> can archive an ad, re-post it, and auto-moderation can return it to `PUBLISHED`.**
> **A ban that lets the seller relist is not a ban.**

**Severity: HIGH. Confidence: HIGH for the code path (verified source-by-source below),
MEDIUM for the end-to-end behaviour (not executed at the time of planning — `B-07` converts
it to an executed, pinned test).** `G-D`'s known-gap test exists to close that confidence gap
by running it. **Owner: phase 15, `15-AUTHZ-001`.** It is not closable in phase 04 at any
acceptable cost.

**Verification of the relist chain, so no implementor re-derives it:**

| Unit | What was checked | Result |
|---|---|---|
| `apps/ads/views/edit.py::ad_edit` | decorators, ownership check, branches | `@login_required`; the only authorization is `ad.user_id != request.user.id` → 403. **No account-state term.** The `is_reactivation` branch calls `submit_ad(...)`; the PUBLISHED text-change branch also routes to moderation |
| `apps/ads/views/edit.py::ad_reactivate` | decorators, authorization, inline moderation | `@require_POST @login_required`; ownership only; `AdStatus.ARCHIVED → ON_MODERATION` then **`from apps.moderation.services.auto_moderation import auto_moderate; auto_moderate(ad)`** inline |
| `apps/ads/services/submission.py::submit_ad` | account-state terms | **none.** `user_id` is an input field; there is no `is_banned` / `is_deleted` / `can_publish_ad` read anywhere in the module |
| `apps/moderation/services/auto_moderation.py::auto_moderate` | what it reads | `_get_cached_criteria()` → `ModerationCriteria` only (title/description length, price, image counts, banned words, max ads, duplicate threshold). **`is_banned` never appears** |
| `apps/users/services/account_state.py::can_publish_ad` | production call sites | **ZERO** outside `apps/users/services/__init__.py`'s re-export and its own tests. **It is dead code in production** — which is why nothing on this chain consults it |

#### `G-7` — CLOSED: option **(b)**, re-scoped to **zero production code**

`Q7` asked which option to ship. **Option (b) is chosen, and after the reachability
correction (1 of 5, and that one is the wrong-target trap) option (b) and option (c) become
the same shape: nothing ships, everything is recorded.** The distinction the plan drew between
(b) and (c) — "closes something" versus "closes nothing" — dissolved once `ban_user` was
refuted. `bulk_ban_users` remains **structurally** unreachable (no `request`; Django cannot
enumerate another user's sessions). `withdraw_consent_action` remains unreachable for the
unrelated prior reason that it was **never registered in `actions`** — a product decision
`G-B` can change, not a Django limitation.

#### `G-B` — CLOSED: **DO NOT REGISTER `withdraw_consent_action`**

**`src/backend/apps/users/admin.py` is not touched at all.** Two reasons, and the second is
new:

1. **The plan's own reason, unchanged.** Registering is a **new, irreversible** operator
   capability — PII nulling, user *and* ad soft-delete, `LoginToken` deletion, **no inverse**
   — and `has_change_permission` is `is_staff` and ignores `obj`, so both `actions =
   ("withdraw_consent_action",)` **and** `@admin.action(permissions=["change"], …)` would be
   mandatory or the capability would be handed to the whole staff population.
2. **The decisive reason, and the plan does not state it: registering it while `G-A` is
   `out` would *increase* `04-AUT-002`'s residual, not close it.** `withdraw_consent_action`
   is moderator-invoked about **other** users in a `queryset`, so it has the **identical
   wrong-target problem** as `ban_user` — `logout(request)` there would log out the
   moderator. Today the action is dead, so the gap is theoretical. Registering it converts a
   theoretical gap into a **reachable** one, on the one path that erases PII. `G-A` = out
   means nothing can invalidate the subject's sessions on that path.

So the real choice is **capability versus capability-plus-a-new-reachable-session-gap**, and
the answer is unambiguous. `PII-107` keeps its MEDIUM band; `PII-105` is untouched.

**Consequence for phase 06, stated so it cannot be misread:** operator erasure capability is
**absent by decision**, and **`PII-107` must cite this decision, not the absence.** The
data-subject path (`consent_withdraw`) is unaffected and `B-01`'s retirement of the form
writes stands — it is correct on its own terms (a form write bypasses the `atomic()`, the
PII nulling, the `LoginToken` deletion and the cache bump). **No test is written under this
branch**, because a test asserting an intentionally-absent action pins an absence and would
have to be deleted the moment phase 06 reverses the decision. The decision lives here and in
the hand-off note; the absence is recorded, not asserted.

#### `G-7b` — CLOSED: **option (b) — `consent_decline` is left untouched**

**This is not "deferred pending `PII-105`". It is rejected on a code-verified ground that is
stronger, and the plan and the code context both record only the weaker one.** The Researcher's
framing was "shipping it pre-empts phase 06's `PII-105`". The stronger argument is that
**decline + `logout()` is a permanent, unrecoverable one-way door**, verified link by link:

| Link | Verified fact | Consequence |
|---|---|---|
| 1 | `decline_consent` sets `is_declined=True` and `ads_auto_publish=False` | — |
| 2 | `can_login` returns `False` when `is_declined` — pinned by `test_account_state.py::TestCanLogin::test_declined_user_cannot_login` **and** `::test_banned_and_declined_cannot_login` | after a logout the subject **cannot log in again** |
| 3 | the **only** production writer of `is_declined = False` is `give_consent` (`deletion.py`) | the recovery must go through `give_consent` |
| 4 | `give_consent` is called from `consent_accept` **only when `user is not None`**, i.e. only for an authenticated request; `consent_accept` is `@require_POST` and **anonymous-accessible**, and an anonymous POST performs **no DB mutation** | an anonymous accept **cannot** clear the decline |
| 5 | therefore decline-then-logout ⇒ no login, no accept ⇒ **`is_declined` can never be cleared** | **permanent account lockout with a working session that cannot re-authenticate** |

**And the open harm it would buy is close to zero**, which is what makes the trade
indefensible rather than merely unbalanced. A consent-declined user is **self-restricting**:
`decline_consent` already sets `ads_auto_publish=False`, and the listing queries already
filter `user__is_declined=False` live (`ads/views/listings.py`, `ads/services/listings_query.py`).
No third party gains access. The only residual is the privacy shape in `G-A`'s consequence
(up to 50 raw search queries in the subject's *other* sessions, `search_history.py::_MAX_HISTORY
= 50`) — and that residual is **identical on the ban path**, where it is unfixable for the
same reason. So shipping the decline logout would **close the wrong thing at the cost of a
data-loss-class bug.**

`G-7b` also records what would have to be true to revisit: `PII-105` must first make DECLINE
reversible **and** restore a web login for a declined user. Until then the recovery
affordance does not exist, and a logout on this path removes the only working session the
user has.

#### `G-D` — CLOSED: the `ban_user` wrong-target trap is recorded as a **named known-gap test**, not handed to the next editor

**It is recorded here, in `B-07`'s own test list, as test 3.** A hand-off note is not
sufficient here, because the plan's *existing brief* would otherwise send an Implementor to
add `logout(request)` to `ban_user` — the brief's `changes` block names that exact edit, and
its `acceptance_criteria` do not exclude it. The test is the durable form of the correction.

**This is a plan correction, not a second mechanism** (`04-VAL-001`): the plan's claim that
`ban_user` is reachable "because it has a `request`" is **refuted** and withdrawn above, and
no `logout()` is proposed for any path. The test asserts the *current* behaviour so that a
future implementor who adds the wrong-target logout sees it turn red with a name attached.

#### `G-E` — CLOSED: the missing session janitor is **re-filed as a retention/ops finding**, against `docs/02-database/db-retention.md`

**Re-filed. Owner: phase 12 (production-ops) / the retention doc's owning phase. It is
explicitly NOT `04-AUT-002`'s scope, and the reason is mechanism, not convenience:**

`clearsessions` ships with Django and **is** discoverable by `get_commands()` —
`django.contrib.sessions` is in `INSTALLED_APPS` (`base.py`) and `SessionMiddleware` is in
`MIDDLEWARE`. So it would need **no new file, no `AdvisoryLockId`, and no migration.** But
`clear_expired()` deletes **only rows past `expire_date`**, so it **cannot shorten a live
session and does nothing whatever for `04-AUT-002`**. It is a row-count and privacy-retention
control, which is a different finding with a different owner.

**And the cost is not zero, which is the reason the previous record understated it.** Both
scheduler lists are **exact-pinned** in a **phase-owned file outside `B-07`'s surface**:

| Constant | Pinned by | Cost to add `clearsessions` |
|---|---|---|
| `HOURLY_COMMANDS` (9 entries) | `apps/core/tests/test_scheduler.py::TestSchedulerConstants::test_hourly_commands_match_spec` — an exact `==` list assertion | 9 → 10 **breaks the test** |
| `DAILY_COMMANDS` (2 entries) | `…::TestSchedulerConstants::test_daily_commands_include_send_alerts` — exact `== ["send_alerts", "rollup_daily_metrics"]` | 2 → 3 **breaks the test** |

Precedent argues for hourly (`cleanup_login_tokens` is already hourly), and
`db-retention.md` would need a new row (verified: it has an ad-status retention table and an
"Other sweeps" command table, and **no session row**). **A cross-phase edit to two
exact-pinned lists in a file `B-07` does not own, in order to ship a control that does not
address this finding, is exactly the overreach rule 5 forbids.** Re-filed with its cost
measured, so the receiving phase starts from a priced item rather than a blank.

#### `G-F` — CLOSED: `test_banner_hidden_for_deleted_user` is **phase 15's migration**, named and budgeted

`apps/users/tests/test_consent.py::TestConsentBannerGuard::test_banner_hidden_for_deleted_user`
**encodes the defect.** The `deleted_user` fixture creates the user with `is_deleted=True`
**at creation**, then `client.force_login(deleted_user)` and `GET /dashboard/` → **asserts
`200`**. The class docstring states the intent: soft-deleted users *"never see the consent
banner, even when they briefly pass through a view before any redirect."* **"Briefly pass
through a view" is the defect, asserted as the expected outcome.**

**`B-07`'s migration cost is zero** — the fixture sets state at creation, so **no transition
ever runs** and nothing `B-07` ships can turn it red. **A per-request gate turns it red**,
because that gate must 302 or 403 a soft-deleted user. Recorded for **`15-AUTHZ-001`, which
must budget a rewrite of this test in its own commit**, alongside `test_banner_shown_for_active_user`
(same class, opposite sign — it stays green). The rewrite is not a deletion: the invariant
worth keeping is *"a soft-deleted user never sees the consent banner"*, which becomes
*"a soft-deleted user is refused before any view renders"*.

#### Rejected options, recorded so no implementor re-weighs them

| Option | Status | Why |
|---|---|---|
| Ship every reachable `logout()` | **REJECTED** | After the reachability correction the only reachable path is the wrong-target trap. There is nothing correct to ship |
| Ship the ban-path decode scan | **REJECTED** — `G-A` | Unbounded scan inside a locked window; duplicates phase 15's mechanism; `DB-004` and rule 5 |
| Ship the decline-path `logout()` | **REJECTED** — `G-7b` | Verified permanent one-way door, for a near-zero harm |
| Register `withdraw_consent_action` | **REJECTED** — `G-B` | Irreversible, moderator-scoped, and it *adds* a reachable session gap while `G-A` is out |
| Ship a per-request gate / middleware | **REJECTED — forbidden** | `04-VAL-001`; `MIDDLEWARE` is a pinned 15-entry list; phase 15's |
| A `StrEnum` revocation reason code | **REJECTED** | No consumer, no column, no reader — an abstraction without justification (rule 5). `ModeratorActionType` exists because `ModeratorActionLog.action_type` **is** a stored column. A `StrEnum` becomes warranted only if a persisted revocation record is introduced, which implies a migration and a far larger design |
| Add a `User.session_epoch` column | **REJECTED — forbidden here** | Correct, and it is phase 15's: a migration plus a middleware comparison, i.e. a second gate |
| Add `select_for_update` to `bulk_ban_users` | **REJECTED — forbidden** | `test_bulk_ban_users_not_locked` asserts `"select_for_update" not in inspect.getsource(bulk_ban_users)` |
| Add an `OperationalError` / `is_lock_timeout` boundary to `bulk_ban_users` | **REJECTED — forbidden** | `D-8`; it is the only one of the four bulk helpers without one and the plan freezes its body |
| `transaction.on_commit` for a new session `DELETE` | **MOOT under the chosen scope** | No new session write is introduced, so there is nothing to schedule. The recommendation is recorded for the phase that does ship one: the repo already does exactly this for the same class of irreversible side effect — `decline_consent` uses `transaction.on_commit(bump_search_cache_version)`, and `withdraw_consent`'s media deletion runs through `on_commit` with the comment *"A rollback must never remove files for rows that remain in the DB."* A session `DELETE` is the same class. Inside the transaction it would widen an already-locked window; the `on_commit` window is microseconds and in-process, before the response |

**Out of scope — hard.** **No middleware, no decorator, no shared gate, no
`MIDDLEWARE` edit** (`04-VAL-001`; it is **15** entries in `config/settings/base.py`, with
`DbLockTimeoutMiddleware` at position 6 and `SessionMiddleware` at position 4 — any
`MIDDLEWARE` change from this phase is a defect). Do not add `select_for_update` to
`bulk_ban_users` (phase 03 `DB-003`; the tripwire is the guard). Do not add an
`OperationalError`/`is_lock_timeout` boundary to `bulk_ban_users` (`D-8`). Do not change
`withdraw_consent`'s transaction shape. Do not change `record_consent_action`'s position
relative to `logout()` (phase 03 `DB-004`). Do not touch `consent_accept`. **Do not touch
`consent_decline`** (`G-7b`). **Do not add `logout(request)` to `ban_user`** — wrong target
(`G-D`). **Do not touch `src/backend/apps/users/admin.py`** (`G-B`). **Do not touch
`auto_moderate` or `submit_ad`** — the ban-path relist capability is a *record* for phase 15,
and making `auto_moderate` read `is_banned` would be a second gate in the moderation tier,
which is phase 15's surface and not this finding's.

#### Tests required — **6 new, 0 changed, 5 named known-gap**

**CORRECTION — the previous brief named `src/backend/apps/moderation/tests/test_review.py`.
That file DOES NOT EXIST.** Verified: `apps/moderation/tests/` contains `test_admin_actions.py`,
`test_approve_ad_side_effects.py`, `test_auto_moderation.py`, `test_decorators.py`,
`test_moderation_log.py`, `test_moderation_side_effects.py`, `test_moderation_views.py`,
`test_priority_service.py`, `test_priority.py`. The `ban_user` view tests live in
**`test_moderation_views.py::TestBanUserView`**. Any implementor who trusted the old brief
would have created a new file and left the real tests behind.

**The governing rule for this block is inverted relative to every other block in the phase:
these tests assert the DEFECTIVE behaviour, on purpose, so that (a) the gap is executable
rather than a claim, and (b) the moment phase 15 closes it they go red and become the
red-to-green target. Every one must carry a docstring naming the gap, its owner
(`15-AUTHZ-001`) and this block's gate. A known-gap test without that docstring is a defect.**

| # | Test | Module | Known gap it pins | Red when |
|---|---|---|---|---|
| 1 | `test_ban_leaves_the_banned_sellers_session_usable` | `apps/moderation/tests/test_moderation_views.py` (new class `TestBanUserSessionKnownGap`) | `G-A` / `G-D` — the banned seller's session survives `ban_user` | a session-revocation mechanism lands |
| 2 | `test_ban_does_not_log_out_the_moderator` | same class | `G-D` — the **wrong-target trap**. Asserts the moderator's session still works after banning | someone adds `logout(request)` to `ban_user` — **this is the tripwire for the trap the existing five tests cannot see** |
| 3 | `test_banned_seller_can_still_reach_the_dashboard` | same class | `G-A` — the web tier has zero per-request account-state enforcement | phase 15's gate lands |
| 4 | `test_banned_seller_can_archive_and_reactivate_an_ad` | `apps/ads/tests/test_edit.py` (new class `TestBannedSellerRelistKnownGap`) | `G-A` — **the concrete harm.** Drives `ad_archive` then `ad_reactivate` on a `PUBLISHED` ad owned by a `is_banned=True` seller, with the real `auto_moderate` (not mocked), and asserts the ad ends `PUBLISHED` | `ad_edit`/`ad_reactivate` gain an account-state check, **or** `auto_moderate` starts reading `is_banned` |
| 5 | `test_consent_decline_keeps_the_session_and_is_reversible` | `apps/users/tests/test_consent.py` (new class `TestConsentDeclineSessionKnownGap`) | `G-7b` — decline leaves the session usable **and** the user can re-accept through the authenticated `consent_accept`. Guards the one-way door: if a decline logout ever shipped, this goes red | a decline logout is added |
| 6 | `test_withdraw_consent_leaves_other_sessions_intact` | `apps/users/tests/test_deletion.py` or `test_consent.py` | `G-A` — `consent_withdraw` flushes **only the current** session; a second session for the same user keeps up to 50 raw search queries (`search_history.py::_MAX_HISTORY = 50`) | multi-session revocation lands |

**Test 4 is the highest-value deliverable in the block.** It converts the Researcher's
MEDIUM-confidence inference — *"a banned seller can archive an ad, re-post it, and
auto-moderation can return it to `PUBLISHED`"* — into an **executed, pinned demonstration**.
Use the **real** `auto_moderate` and a `PUBLISHED` source ad, because the value of the test
is precisely that `auto_moderate` is *not* mocked and *does not* read `is_banned`.

**Vacuity guard, mandatory on tests 1, 3, 4, 5 and 6.** `client.force_login(user)` creates a
**real** `django_session` row. Assert the session is genuinely live **before** asserting it
survives — otherwise the test passes on a client that was never logged in. Conversely, note
the trap in the other direction: **`force_login` creates the session row AFTER the fixture
sets account state**, so **almost no existing test in this repository exercises "state
changed while a session is live".** Tests 1–6 are the first that do, and they must mutate
state *after* the login, not in a fixture.

**Regression set — unchanged and green (5 tripwires):**

| Tripwire | What it enforces | Why `B-07` must not break it |
|---|---|---|
| `apps/moderation/tests/test_admin_actions.py::test_bulk_ban_users_not_locked` | `inspect.getsource(bulk_ban_users)`: `"select_for_update" not in src`, `"transaction.atomic" in src` | source-inspection; any addition to that function's body is visible |
| `apps/moderation/tests/test_moderation_views.py::TestModerationReviewLocking::test_ban_user_uses_select_for_update_and_atomic` | `inspect.getsource(review.ban_user)` contains both substrings | **the reason test 2 above is mandatory** — this test would not notice a wrong-target logout |
| `apps/users/tests/test_consent.py::TestConsentWithdrawIdempotency` | `withdraw_consent` is idempotent; **no `LoginToken` deletion on the no-op path** | pins the transaction shape `G-D`/`G-A` say not to touch |
| `apps/users/tests/test_account_state.py::TestCanLogin` | six assertions incl. `is_declined → False` | **the predicate that makes `G-7b` a one-way door.** Two of its six tests pin the decline term |
| `apps/users/tests/test_consent.py::TestConsentBannerGuard` | a soft-deleted user's dashboard returns **200** | `G-F`: encodes the defect; `B-07` leaves it green, phase 15 rewrites it |

**Not written, and why — so the absence is traceable:** `test_consent_decline_flushes_the_session`
and `test_anonymous_decline_is_unaffected` (both `G-7b` = (a) only — not chosen);
`test_withdraw_consent_action_is_registered` (`G-B` = do-not-register); and **any** assertion
on the *absence* of `withdraw_consent_action` (would pin a decision as an invariant).

**Gates.** `G-7`, `G-7b`, `G-A`, `G-B`, `G-D`, `G-E`, `G-F` — **all CLOSED 2026-10-02 by the
`B-07` Planner.** The block may start.

**Agents.** Reduced from five to three, and the reduction is itself a finding. **Researcher
and Auditor are discharged** — the reachability question they were engaged to answer has been
answered twice, and the second answer (1 of 5) refutes the first (3 of 5). Re-engaging them
would re-litigate a settled correction. **Implementor** (writes the six known-gap tests) ·
**Planner** (all seven gates, closed 2026-10-02) · **Validator** (**required** — the named
failure mode of this block is still "shipping a second gate", `04-VAL-001`, and only a
Validator can confirm `MIDDLEWARE` is byte-unchanged, that `ban_user` gained no `logout()`,
that `users/admin.py` is untouched, and that no **production** file changed at all).

**Risks.**

| Risk | Severity | Mitigation |
|---|---|---|
| **A banned seller can still relist** (`G-A`'s residual) | **HIGH, knowingly accepted** | Not mitigated in this phase — it is **not mitigable here** without a second gate or an O(n) scan. Named known-gap test 4 executes and pins it; handed to `15-AUTHZ-001` |
| **A wrong-target `logout(request)` in `ban_user`** — logs out the moderator, leaves the seller live, **and the existing five tests all stay green** | **HIGH** | Test 2 is the dedicated tripwire. Prohibited by name in the brief's `acceptance_criteria` and in "Out of scope" |
| Shipping a second gate | HIGH | Validator diff check; `MIDDLEWARE` pinned at 15 |
| A known-gap test is written without its owner docstring, so the gap becomes a silent pin | MEDIUM | Stated as a defect in the tests section; the docstring requirement is in the brief's acceptance criteria |
| A known-gap test passes **vacuously** because `force_login` never ran or because state was set in a fixture rather than after login | MEDIUM | Vacuity guard in the tests section; the brief states it as an acceptance criterion |
| Test 4 (`relist`) is flaky because it drives the real `auto_moderate` and real `ModerationCriteria` | MEDIUM | `ModerationCriteria.get_singleton()` is a fixture the suite already relies on; use the suite's existing criteria fixture, and assert on the ad's final status, not on moderation internals |
| The block is read as "nothing happened" | **MEDIUM — the real reputational risk of a zero-code block** | This section's opening note, the DoD's explicit `04-AUT-002` **not closed** statement, and the six named tests. §F.1's dominant failure mode is a green suite over a *silent* non-fix; six executed red-to-green specifications are not that |
| Phase 06 reads `PII-107` as closed | MEDIUM | `G-B` states the decision in the plan, and the Phase-06 record's item 4 requires phase 06 to cite the **decision**, not the absence |

**Rollback.** Delete the six tests. **There is no production code to roll back** — that is
the point of `G-A`/`G-B`/`G-7b`, and it makes this the cheapest-to-reverse block in the phase.
The plan edits stay.

**Definition of done.**

- The six known-gap tests exist, pass, and each names its gap, its owner (`15-AUTHZ-001`) and
  the gate that produced it in a docstring.
- **Zero production files changed.** `git diff --stat -- src/` must show **only** test files.
  Explicitly: `config/settings/base.py` byte-unchanged (`MIDDLEWARE` at 15 entries) ·
  `apps/moderation/views/review.py::ban_user` byte-unchanged (no `logout`) ·
  `apps/moderation/admin_actions.py` byte-unchanged ·
  `apps/users/views/consent.py` byte-unchanged (`consent_decline` untouched) ·
  `apps/users/admin.py` byte-unchanged · `apps/users/services/deletion.py` byte-unchanged ·
  `apps/users/services/account_state.py` byte-unchanged ·
  `apps/moderation/services/auto_moderation.py` byte-unchanged ·
  `src/telegram_bot/` byte-unchanged.
- **No new decorator** anywhere; no new module; **no migration**; no `.po` edit (owned by
  another agent); no new dependency.
- All five tripwires green and **unedited**: `test_bulk_ban_users_not_locked` ·
  `test_ban_user_uses_select_for_update_and_atomic` · `TestConsentWithdrawIdempotency` ·
  `TestCanLogin` · `TestConsentBannerGuard`.
- Fast gate green with the default `-n 4` (do **not** reduce parallelism to buy a green
  number). `test_banner_hidden_for_deleted_user` still green — `G-F`.
- **The commit body states, in the finding's own words: `04-AUT-002` is NOT closed.** It is
  re-scoped to the web tier's per-request enforcement, handed to `15-AUTHZ-001`, and
  `04-AUT-002`'s ban-path residual is named as a knowingly-accepted HIGH risk. **A commit
  body that reads as a fix is a defect in this block.**
- The hand-off note is written: six named gaps, one owner (`15-AUTHZ-001`), plus the
  re-filed janitor (`G-E`, phase 12 / `db-retention.md`) and the `PII-107` decision (`G-B`,
  phase 06).

**Implementor brief.**

```yaml
id: 04-b07-session-revocation
title: Pin 04-AUT-002's residuals as named known-gap tests (ZERO production code)
priority: medium
depends_on: [04-b03-login-token-browser-binding, G-7 closed, G-7b closed, G-A closed, G-B closed, G-D closed, G-E closed, G-F closed]
source_reference: .ai/plans/16-auth-login-remediation-execution.md
source_section: "### B-07 — Session revocation at account-state transitions (04-AUT-002, session half)"
source_blocks: ["BLOCK 6", "04-AUT-002", "04-VAL-001"]
description: >
  04-AUT-002 is NOT closed by this block and this brief ships no production code. The
  Researcher's findings refuted the block's premise: the third-party PII exposure is already
  closed at three layers, the per-request gate belongs to phase 15, and of five open account
  -state transitions exactly one is reachable — moderation.views.review.ban_user, whose
  request carries the MODERATOR, not the banned seller. django.contrib.auth.logout(request)
  has no target-user argument, so the only reachable path cannot be fixed here.

  Your deliverable is six tests that assert today's DEFECTIVE behaviour on purpose, each
  with a docstring naming the gap, its owner (phase 15, 15-AUTHZ-001) and the gate that
  produced it. They are red-to-green specifications for phase 15, not regression guards, and
  they must not be written to pass against a fix.
goals:
  - "zero production files changed - git diff --stat -- src/ shows only test files"
  - "six named known-gap tests, each with an owner-naming docstring; test 4 executes the banned-seller relist chain end to end"
  - "the wrong-target logout trap in ban_user gets its own tripwire test, because the five existing tests cannot see it"
  - "04-AUT-002 is recorded as NOT closed, with the ban-path residual named as a knowingly accepted HIGH risk"
extra_context: >
  READ FIRST, in the B-07 section of the plan: the "Verified starting state" table, "The
  wrong-target trap in ban_user", "The contact leak is ALREADY CLOSED", G-A, G-7, G-B, G-7b,
  G-D, G-E, G-F, and "Tests required". Every binding constraint is stated there.

  Traps, all verified live at 9ef5151:
  1. WRONG-TARGET LOGOUT. moderation/views/review.py::ban_user is @staff_required; its
     request.user is the MODERATOR and the changed identity is ad.user. logout(request)
     flushes request.session and has no target-user parameter, so it logs out the moderator
     and leaves the seller live. FIVE existing tests stay green: TestBanUserView's four
     (they force_login(staff_user) and assert only status_code == 302 and seller.is_banned)
     plus TestModerationReviewLocking::test_ban_user_uses_select_for_update_and_atomic,
     which is a substring check on inspect.getsource and is indifferent to the addition.
     DO NOT add logout(request) to ban_user. Write test 2 instead.
  2. SOURCE-INSPECTION TRIPWIRES. apps/moderation/tests/test_admin_actions.py::
     test_bulk_ban_users_not_locked asserts "select_for_update" not in
     inspect.getsource(bulk_ban_users) AND "transaction.atomic" in src. Do not add a row
     lock to bulk_ban_users and do not remove its atomic(). Do not add an
     OperationalError/is_lock_timeout boundary there either (D-8).
  3. TRANSACTION SHAPE. apps/users/tests/test_consent.py::TestConsentWithdrawIdempotency
     pins withdraw_consent, including that the no-op path performs NO LoginToken deletion.
     Do not restructure deletion.py::withdraw_consent.
  4. DECLINE SEMANTICS. apps/users/tests/test_account_state.py::TestCanLogin pins
     can_login(is_declined=True) is False in TWO tests. Because give_consent is the only
     clearer of is_declined and is reachable only from an AUTHENTICATED consent_accept, a
     logout on consent_decline is a PERMANENT ONE-WAY DOOR. Do not touch consent_decline.
  5. VACUITY. client.force_login(user) creates a real django_session row, and it does so
     AFTER the fixture has set account state. Almost no test in this repository exercises
     "state changed while a session is live". Your tests are the first that do: log in
     FIRST, then mutate the flag, and assert the session was genuinely live before asserting
     it survived. Otherwise the test passes on a client that was never logged in.
  6. FILE PATH. The previous brief named src/backend/apps/moderation/tests/test_review.py.
     THAT FILE DOES NOT EXIST. The ban_user tests live in test_moderation_views.py.
  7. .po FILES BELONG TO ANOTHER AGENT. apps/users/** is contended; no translatable string
     may be added, so every new test docstring stays in English and no template is touched.
  8. NO PRODUCTION CODE AT ALL. No logout, no decorator, no middleware, no migration, no
     new module, no new dependency, no StrEnum, no edit to auto_moderate or submit_ad.
files:
  - path: src/backend/apps/moderation/tests/test_moderation_views.py
    targets:
      - type: class
        name: TestBanUserSessionKnownGap
        note: "NEW sibling class next to the existing TestBanUserView. Do not modify TestBanUserView or TestModerationReviewLocking."
      - type: function
        name: test_ban_leaves_the_banned_sellers_session_usable
      - type: function
        name: test_ban_does_not_log_out_the_moderator
      - type: function
        name: test_banned_seller_can_still_reach_the_dashboard
    semantic_anchors:
      insert_after:
        type: class
        value: TestBanUserView
      note: "The new class goes AFTER TestBanUserView and BEFORE the TestModerationReviewLocking structural block. Reuse this module's existing staff_user, seller, category and city fixtures and its create_test_ad helper - do not define new ones."
  - path: src/backend/apps/ads/tests/test_edit.py
    targets:
      - type: class
        name: TestBannedSellerRelistKnownGap
        note: "NEW class. Highest-value deliverable in the block."
      - type: function
        name: test_banned_seller_can_archive_and_reactivate_an_ad
    semantic_anchors:
      insert_after:
        type: function
        value: ad_reactivate
      note: "Anchor on the module's ad-reactivation test group. Drive ad_archive then ad_reactivate on a PUBLISHED ad owned by a seller with is_banned=True. Use the REAL auto_moderate - do NOT mock it. The value of the test is precisely that auto_moderate is unmocked and does not read is_banned. Assert on the ad's final status, never on moderation internals."
  - path: src/backend/apps/users/tests/test_consent.py
    targets:
      - type: class
        name: TestConsentDeclineSessionKnownGap
      - type: function
        name: test_consent_decline_keeps_the_session_and_is_reversible
      - type: class
        name: TestConsentWithdrawIdempotency
        note: "reference only - TRIPWIRE, do not edit"
      - type: class
        name: TestConsentBannerGuard
        note: "reference only - encodes the defect, phase 15 rewrites it (G-F), B-07 leaves it green"
    semantic_anchors:
      insert_after:
        type: class
        value: TestConsentDeclineSessionKnownGap
      note: "Append the new class near the existing consent-view classes. The decline test drives the real URL because consent_decline ends in redirect('ads:dashboard') - a full navigation, so an open HTMX fragment in the same page is the first thing to check if it starts returning 400."
  - path: src/backend/apps/users/tests/test_deletion.py
    targets:
      - type: class
        name: TestWithdrawConsentMultiSessionKnownGap
      - type: function
        name: test_withdraw_consent_leaves_other_sessions_intact
    semantic_anchors:
      insert_after:
        type: function
        value: withdraw_consent
      note: "Open two independent Clients for the same user, withdraw consent through one, and assert the other session is still live and still carries its search-history entries (search_history.py::_MAX_HISTORY = 50)."
changes:
  - action: add_code
    description: >
      Six known-gap tests, no production code. Each test asserts the CURRENT, DEFECTIVE
      behaviour and its docstring must name: the gap in one sentence, the owner (phase 15,
      15-AUTHZ-001), and the gate that produced the decision (G-A, G-7b, G-D or G-E). A
      known-gap test without that docstring is a defect in this block.
acceptance_criteria:
  - "git diff --stat -- src/ lists ONLY test files. Zero production files changed."
  - "config/settings/base.py MIDDLEWARE byte-unchanged at 15 entries; no new decorator; no middleware; no migration; no new module; no new dependency"
  - "moderation/views/review.py::ban_user byte-unchanged - it does NOT contain logout( or any session call"
  - "apps/users/admin.py byte-unchanged - no actions attribute added, decorator not amended (G-B)"
  - "apps/users/views/consent.py byte-unchanged - consent_decline untouched (G-7b); consent_accept untouched; consent_withdraw's existing logout untouched"
  - "apps/moderation/admin_actions.py byte-unchanged - no select_for_update, no OperationalError boundary (D-8)"
  - "apps/users/services/deletion.py byte-unchanged - withdraw_consent's transaction shape and no-op path intact"
  - "apps/moderation/services/auto_moderation.py byte-unchanged - auto_moderate still does not read is_banned (that is the gap)"
  - "src/telegram_bot/ byte-unchanged"
  - "all six known-gap tests pass, each with an owner-naming docstring"
  - "the five tripwires are green AND unedited: test_bulk_ban_users_not_locked, test_ban_user_uses_select_for_update_and_atomic, TestConsentWithdrawIdempotency, TestCanLogin, TestConsentBannerGuard"
  - "each new test proves its session was live BEFORE asserting it survived (log in first, then mutate the flag)"
  - "the commit body states in plain words that 04-AUT-002 is NOT closed, names the ban-path residual as a knowingly accepted HIGH risk, and points at 15-AUTHZ-001. A commit body that reads as a fix is a defect."
  - "no .po file and no template is edited; every new docstring is English"
tests_to_run:
  - src/backend/apps/moderation/tests/test_moderation_views.py
  - src/backend/apps/ads/tests/test_edit.py
  - src/backend/apps/users/tests/test_consent.py
  - src/backend/apps/users/tests/test_deletion.py
  - src/backend/apps/moderation/tests/test_admin_actions.py
  - src/backend/apps/users/tests/test_account_state.py
  - src/backend/apps/users/tests/test_admin_pii_containment.py
commands:
  - "fast gate: $dc run --rm --env PYTEST_SKIP_MARKERS=seed test   (keep the default -n 4; do NOT reduce parallelism)"
  - "targeted: $dc run --rm --env PYTEST_SKIP_MARKERS=seed --env PYTEST_OPTS='<file> <file> --tb=short' test"
  - "ruff: uv run ruff check src/backend/apps/moderation/tests/ src/backend/apps/ads/tests/ src/backend/apps/users/tests/"
  - "proof of zero production change: git diff --stat -- src/ | Select-String -NotMatch 'tests'"
known_gaps_handed_off:
  - gap: "a banned seller's live web session survives moderation.views.review.ban_user; the web tier has zero per-request account-state enforcement"
    owner: "phase 15 - 15-AUTHZ-001"
    gate: G-A
    severity: HIGH
  - gap: "a banned seller can archive an ad and reactivate it, and auto_moderate can return it to PUBLISHED - a ban that lets the seller relist is not a ban"
    owner: "phase 15 - 15-AUTHZ-001"
    gate: G-A
    severity: HIGH
  - gap: "a withdrawn user's OTHER sessions keep up to 50 raw search queries; consent_withdraw flushes only the current session"
    owner: "phase 15 - 15-AUTHZ-001"
    gate: G-A
    severity: MEDIUM
  - gap: "no django_session janitor; clearsessions is absent and the table is unbounded (SESSION_ENGINE and SESSION_COOKIE_AGE are unset, so 14-day default retention). Re-filed against docs/02-database/db-retention.md - it needs a row there, and adding it to HOURLY_COMMANDS (9->10) or DAILY_COMMANDS (2->3) breaks two exact-== pinned tests in a file B-07 does not own."
    owner: "phase 12 (production-ops) / db-retention.md"
    gate: G-E
    severity: MEDIUM
  - gap: "no operator-reachable withdraw_consent trigger on the User admin, absent BY DECISION under G-B - not because registration was overlooked"
    owner: "phase 06 - PII-107 must cite the decision, not the absence"
    gate: G-B
    severity: MEDIUM
  - gap: "test_banner_hidden_for_deleted_user asserts GET /dashboard/ == 200 for a soft-deleted user, encoding the defect in its class docstring. A per-request gate turns it red. Phase 15 must budget the rewrite; B-07's migration cost is zero because the fixture sets is_deleted at creation."
    owner: "phase 15 - 15-AUTHZ-001"
    gate: G-F
    severity: MEDIUM
deferred_obligations: []
```

#### Baseline recorded 2026-10-02 at `9ef5151` — so a regression is distinguishable from the starting state

Targeted run of the whole `B-07` surface: `test_consent.py`, `test_moderation_views.py`,
`test_admin_actions.py`, `test_account_state.py`, `test_admin_pii_containment.py`,
`test_deletion.py` — **136 tests**.

- `test_consent.py` **alone: exit code 0, green.**
- The full six-file run produced **2 failures on one attempt and 0 on another, at the same
  HEAD with no code change between them**: `TestLoginStatusNoPii::test_login_consume_no_raw_telegram_id`
  and `::test_login_unbound_refusal_logs_no_pii`, both `AssertionError: assert None is not
  None` at the `claim_token(...)` call. **This is the test-DB flake `E.4` already names**, not
  a code regression: neither test touches anything in `B-07`'s surface (this block's diff
  contains no `claim_token`, no `login_issue`, no `issue_token`), and the file is green in
  isolation. **Re-run before believing it**, exactly as `E.4` instructs.
- `apps/search/tests/test_search_slo.py::…::test_search_at_seed_volume_meets_slo` is a
  wall-clock SLO assertion that fails under load. **Not a finding.**

**Keep the default `-n 4` on the fast gate.** The test DB is shared with no single-writer
gate, and reducing parallelism to buy a green number is a recorded anti-pattern in this phase.

#### Honest bottom line — what `B-07` actually delivers

**It closes almost nothing, and that is the accurate description.** Stated plainly so it
cannot be softened by a reader in a hurry:

- **Zero production lines change.** No `logout()` is added anywhere, because there is no path
  where adding one would be correct.
- **`04-AUT-002` is NOT closed.** The ban-path residual — a banned seller keeps a working
  session and can relist through `ad_edit`/`ad_reactivate`, with `auto_moderate` never reading
  `is_banned` — is **accepted at HIGH and handed to `15-AUTHZ-001`**, because the only two
  mechanisms that would close it (a per-request gate, or an unbounded decode scan) belong to
  other blocks, and shipping either here would be a second gate (`04-VAL-001`) or a
  concurrency regression (`DB-004`).
- **What it does deliver is real, and it is not nothing:** the finding's most serious claim —
  that a ban is defeatable — moves from a MEDIUM-confidence *inference* to an **executed,
  pinned demonstration** (test 4, the relist chain, real `auto_moderate`, not mocked). The
  wrong-target trap in `ban_user` acquires a **dedicated tripwire** that the five existing
  tests structurally cannot provide. Six residuals get a name, an owner and a test. Seven
  gates are closed with reasons. **Four plan corrections land**, one of which was a hard
  error that would have sent an Implementor to create a file that does not exist and add a
  `logout()` to the wrong identity.

**Weighed against the phase's dominant failure mode.** `F.1` names *"a green suite over a
non-fix"* as the failure mode to avoid, and this block produces a green suite with **no fix**.
**The distinguishing question is whether the non-fix is silent, and it is not.** It is
recorded in this section's header, in five named gap hand-offs with owners, in six tests that
turn red the moment someone fixes it, and in a commit body that is forbidden from reading as
a resolution. A coordinator grepping this plan finds the ban path's HIGH residual in one
line. **That is the difference between this block and option (c) as the plan originally wrote
it** — and it is the difference between a recorded decision and an omission.

**The one thing that would make this block a poor use of the phase's time** is if the
coordinator would rather spend it on `B-06`/`B-10`/`B-11` and accept `04-AUT-002` as a
standing phase-15 item with no phase-04 record at all. **That is a legitimate call and it is
the coordinator's, not this Planner's** — the deciding factor is that the six tests cost
roughly one test file's worth of work and remove the highest-uncertainty claim in the
finding. If the coordinator prefers to skip, the correct action is to record the skip
**loudly** in `§F`, not to let the block lapse unremarked.

---

### B-08 — Peer-gated client-IP helper + de-duplication (`04-AUT-003`, Python half)

| | |
|---|---|
| **Findings owned** | `04-AUT-003` (Python half) |
| **Depends on** | **`G-8`, `G-8a`…`G-8g` — ALL CLOSED 2026-10-01 by the `B-08` Planner.** The block may start |
| **Blocks** | `B-11`; phase 09 `API-005`'s media limiter inherits this helper. **`B-09` is NOT blocked** — §C's hard `B-08 → B-09` edge is superseded by `G-8g`: `B-08` is correct with no nginx change |
| **Priority** | P1 · **Risk HIGH** · **`B-09` optional** |

**Objective.** Replace three unconditionally-trusting `X-Forwarded-For` copies with one
helper that **gates on the socket peer before reading any header**, and resolves the correct
end of the chain when the gate is open.

**Verified starting state — three copies, logic-identical; two byte-identical.**

| Module | Symbol | Consumer | Limits |
|---|---|---|---|
| `apps/users/services/login_rate_limit.py` | `_get_client_ip` | `login_rate_limit_check` | `RATE_LIMIT_REQUESTS=10`, `RATE_LIMIT_PERIOD=60`, key `"login_rl:{ip}"` |
| `apps/core/services/contact_rate_limit.py` | `_get_client_ip` | `check_deep_link_render_rate_limit` | 60 / 600 s, key `"telegram_dl_rl:{ip}"` |
| `apps/search/services/rate_limit.py` | `_get_client_ip` | `rate_limit_check(request, *, namespace="autocomplete")` | 30 / 60 s, key `"{namespace}_rl:{ip}"` |

All three: `request.META.get("HTTP_X_FORWARDED_FOR")` → if truthy,
`split(",")[0].strip()` → else `request.META.get("REMOTE_ADDR", "unknown")`. All three use
the `cache.add` + `cache.incr` idiom with a `ValueError` fallback.
**A fourth client-IP read the source plan never names (`C-4`, `U-8`):**
`apps/users/services/consent_record.py` calls
`_anonymize_ip(request.META.get("REMOTE_ADDR") or None)`, so `ConsentRecord.ip_address`
records the **nginx container's IP** for every production request.

**`Q2` is ANSWERED by the audit (`C-6`)** — there is no Auditor task on this block.
`docker-compose.yml::nginx` publishes `80:80`/`443:443` directly on the host,
`image: nginx:alpine`; `docker-compose.prod.yml` adds only a cert mount and
`media_volume:ro`. No CDN, no load balancer, no cloud proxy anywhere in the repo.
`docker/nginx/nginx.conf` contains **no** `set_real_ip_from` and no `real_ip` usage, and
its own `limit_req_zone` keys on `$binary_remote_addr` — so **nginx-side rate limiting is
already unforgeable and is unaffected. The defect is Django-side only**, and the blast
radius is exactly three keys: login 10/60 s, deep-link 60/600 s, search/autocomplete
30/60 s.

**No existing home for the helper (`C-21`) — and the plan's chosen one is corrected below.**
`apps/core/services/` contains no request helper of any kind, and `apps/core/utils/` contains
no IP helper either, so a new module is genuinely required. The dependency direction is not
the discriminator — both packages satisfy it, because all consumers are in `apps.*` and an
`apps.*` → `telegram_bot.*` import is forbidden. **See `G-8e`: the package decision is
`apps/core/utils/`, and the plan's stated reason for `services/` is factually false
(`B-8c`).** Note also that `apps/core/services/__init__.py` re-exports eight of its own
siblings, while `apps/core/utils/__init__.py` is a bare comment with **no** re-exports — so
the move also removes a re-export decision rather than adding one.

**The existing gate that asserts the defect.** `apps/core/tests/test_contact_rate_limit.py::test_x_forwarded_for_takes_precedence`
sets `request.META["REMOTE_ADDR"] = "10.0.0.1"` and
`request.META["HTTP_X_FORWARDED_FOR"] = "203.0.113.5"` and asserts the header wins.
**Corrected 2026-10-01 — read `§E.2` before touching this test.** Its only assertion is
`check_deep_link_render_rate_limit(request) is True`, which holds because the key is a
**fresh counter**, whatever IP the helper resolved. It is a **fresh-counter assertion wearing
a precedence claim**, so it **passes unchanged under every trust model this block could
choose**; the rewrite is about *recording the old rule honestly*, not about an assertion
going red.

---

## Corrections applied — 2026-10-01 by the `B-08` Planner

Verified against the live tree at `65efb3a`. The plan claimed six things the code does not
say; each correction changes what the Implementor must do.

| # | The plan said | The tree says | Consequence |
|---|---|---|---|
| `B-8a` | "three copies, **byte-identical**" (also in the brief's `description`) | **byte-identical for 2 of 3** — `login_rate_limit._get_client_ip` and `search.rate_limit._get_client_ip` are the same 17 lines including the docstring. `contact_rate_limit._get_client_ip` differs **only** in a one-line docstring (`"""Extract the client IP, honoring X-Forwarded-For from nginx."""`). All three are **logic-identical** | no change to the work; the de-duplication premise is unaffected. The brief's prose is corrected so no reviewer greps for a third byte-identical file |
| `B-8b` | `test_x_forwarded_for_takes_precedence` "asserts the **header wins**" and is the test that must be **replaced**, implying an assertion goes red | it asserts only `is True` on a **fresh** counter. **It passes unchanged under the chosen model** (the key merely becomes `telegram_dl_rl:10.0.0.1`, also fresh) | rewrite cost is **1 test rewritten, 12 passing unchanged, 0 to fix** — and the rewrite is a *documentation* act. See `§E.2` |
| `B-8c` | `site_config.py`'s docstring says `apps/core/services/` hosts cross-app shared services, which is why the helper goes there | `site_config.py`'s docstring reads *"Shared site-config service for Mko Bazuna… Used by the web context processor (sync) and the Telegram bot (async)."* — it says **nothing** about hosting cross-app shared services | the stated justification for `services/` is false. The helper moves to **`apps/core/utils/`** — see `G-8e` below and the Scope table |
| `B-8d` | `D-6`: an env-backed setting "needs an `ALLOWED_ENV_VARS` entry **and four `.env.*.example` updates in the same commit**, or the fast gate fails" | **only the allowlist entry is gate-binding.** Verified: `test_env_allowlist.py::test_example_keys_in_allowlist` asserts `example keys ⊆ ALLOWED_ENV_VARS` (template ⇒ allowlist, **not** the reverse); `test_env_allowlist_reverse.py::test_consumed_env_vars_are_allowlisted` asserts `consumed ⊆ ALLOWED_ENV_VARS` (read ⇒ allowlist, **not** the reverse); `test_python_consumed_vars_in_allowlist` is a **hardcoded 8-name subset** assertion, not an equality. Its own docstring states the reverse direction is *"false by construction"* | the four template edits were never required. `G-8c` is decided on the merits, not on a gate cost that does not exist |
| `B-8e` | `G-8a` option text: bringing `consent_record.py` in scope requires citing "phase 06's `PII-104`/`PII-107`" | **`PII-104` is the alert-audience finding** (phase 06 BLOCK 9 — recipient selection), unrelated to client IP. The owner of `consent_record.py` is **`06-PII-107`, BLOCK 6 of `06-pii-consent-remediation.md`** (gate `Q-D7`), whose file surface names `record_consent_action` and `_anonymize_ip` and whose binding constraint 5 is *"`_anonymize_ip`'s behaviour is unchanged"* | the citation is corrected. That constraint is **satisfied by design**: `B-08` changes only what value *reaches* `_anonymize_ip`, never its body |
| `B-8f` | the trusted set "defaults to trusting nothing" | under a peer-marker predicate there is no trusted *set* to default. The invariant that actually matters is **"no public peer is trusted unless an operator lists a network containing it."** `TRUSTED_PROXY_NETWORKS` is `()` in `base.py`, `dev.py` and `test.py` and is not declared in `prod.py`, so the shipped production gate is exactly `is_loopback or is_private` | the binding line is replaced. The setting is **purely additive** — it can widen trust, never narrow it — so the assertable invariant is that **a public peer is trusted only when an operator lists a network containing it**. A mis-set value cannot cause the collapse-DoS; the residual it creates is a **bypass** if an operator lists a public range |

**Additional verified facts the plan did not carry, and the design turns on:**

1. **`X-Real-IP` is already set, already overwritten, and read by nothing.** `proxy_set_header X-Real-IP $remote_addr;`
   appears in **all 9** `proxy_set_header` blocks of `docker/nginx/nginx.conf` and **all 6** of
   `docker/nginx/nginx.dev.conf`. `proxy_set_header` overwrites, so a client cannot influence
   it through nginx. A tree-wide search finds **zero** Python reads of `HTTP_X_REAL_IP`. The
   clean header already exists; the fix is a Python-only change.
2. **`X-Forwarded-For` is appended, so `XFF[0]` is attacker-controlled end to end.** All 15
   sites use `$proxy_add_x_forwarded_for`. A client sending `XFF: 1.2.3.4` produces
   `1.2.3.4, <real client>`; `split(",")[0]` returns `1.2.3.4` — the attacker's own value.
3. **`web` is not published in production.** Verified: `docker-compose.yml` publishes only
   `nginx` (`80:80`, `443:443`); `docker-compose.prod.yml` adds only `db` (`6432:6432`) and
   volumes. **This is what makes `X-Real-IP` unforgeable in production** and it is the fact
   `G-8b` leans on. `docker-compose.dev.override.yml` publishes `web` on `8000:8000` and
   gates nginx behind `profiles: ["use-nginx"]`, so **in the default dev stack Django takes
   the connection directly** — both the "behind a proxy" and the "no proxy" path are live in
   one codebase.
4. **A literal trusted-proxy IP is not operable.** No compose file declares a `networks:` key,
   so nginx sits on a Docker-allocated per-deployment subnet. An explicit-IP trusted set would
   require a compose change outside **both** blocks' file lists.
5. **`_anonymize_ip` has no `try`/`except` around `int(ipaddress.IPv6Address(ip))`.** A value
   with no `.` that is not valid IPv6 raises `AddressValueError` → HTTP 500. Latent today
   because only `REMOTE_ADDR` reaches it; the helper's validation (§`G-8f`) removes the path.
6. **Test-client traps, all verified.** (a) A bare `HttpRequest()` starts with `META == {}`, so
   `REMOTE_ADDR` is **absent** unless set — the current `.get(..., "unknown")` default is
   **load-bearing** and a helper that subscripts `META["REMOTE_ADDR"]` raises `KeyError`.
   (b) **Two META-assignment styles** are in the tree: whole-dict replacement
   (`request.META = {"REMOTE_ADDR": "127.0.0.1"}` in `test_login.py`'s two limiter tests) and
   item assignment (`request.META["REMOTE_ADDR"] = ip` in `test_contact_rate_limit.py::_make_request`
   and `test_autocomplete.py::TestRateLimitService`). Both must work. (c)
   `django/test/client.py` hard-codes `REMOTE_ADDR="127.0.0.1"` and `wsgi.url_scheme="http"`
   and is **not proxy-aware**, so a unit test can verify the trust decision and key agreement
   but **cannot** verify anything about nginx or the bridge address.
7. **The three limiters each declare an unused `logger`.** Do not replicate it in the new
   module; run `ruff` on it.

---

## Gate decisions — `G-8a` … `G-8g`, CLOSED 2026-10-01 by the `B-08` Planner

Full reasoning and the rejected options in **`§I.6`**. The shape in one paragraph:

> **Peer gate, then header.** `REMOTE_ADDR` — the socket peer — is read first. If it is
> **absent** the helper returns `"unknown"`. If it parses and is **not** loopback and **not**
> private, the helper returns it and **no header is read at all**. Only when the peer is
> loopback/private (or falls inside a configured `TRUSTED_PROXY_NETWORKS` CIDR) are headers
> consulted, in this order: **`HTTP_X_REAL_IP`**, then `HTTP_X_FORWARDED_FOR` walked
> **right-to-left** returning the first entry that is itself not loopback/private. The chosen
> value is parsed with `ipaddress` and returned **canonically**; anything unparseable falls
> back to the socket peer, and a socket peer that will not parse falls back to `"unknown"`.

### `G-8a` — `consent_record.py`'s fourth read: **IN SCOPE**

`record_consent_action` routes its IP through the same helper. Consequences, stated:

- **One** client-IP policy ships, and the DoD's tree-wide search has a fourth site to check.
- **0 test rewrites.** `test_consent_records.py::TestAnonymizeIp`'s three tests call
  `_anonymize_ip` directly and are untouched; `::TestConsentRecording::test_ip_is_anonymized_and_ua_truncated`
  is **permissive by design** — it accepts `None` **or** any value ending in `.0`, and the
  test client sets `REMOTE_ADDR="127.0.0.1"` → the helper returns `"127.0.0.1"` →
  `_anonymize_ip` yields `"127.0.0.0"` → ends in `.0`. All four pass unchanged.
- **The `AddressValueError` crash is fixed**, not merely avoided: the helper validates before
  returning, so a malformed value never reaches `ipaddress.IPv6Address` inside
  `_anonymize_ip`. That is a real fix — today a value with no `.` that is not valid IPv6 is
  an HTTP 500.
- **`_anonymize_ip`'s body is not touched**, which keeps phase 06 `06-PII-107` BLOCK 6's
  binding constraint 5 (*"`_anonymize_ip`'s behaviour is unchanged"*) satisfied: only its input
  changes, and only to a strictly better value. **That constraint is recorded here so phase 06
  inherits it rather than rediscovering a conflict.**
- Blast radius grows by exactly one function body and one import line. No model change, no
  migration, no template, no `.po`, no new translatable string.
- **The alternative, and why it is rejected:** leaving it out keeps `ConsentRecord.ip_address`
  recording **nginx's container IP** for every production consent action — a second
  inconsistent client-IP policy in the same phase — and leaves the crash latent. Shipping
  *one* policy and *one* validator is the cheaper of the two.

### `G-8b` — the trust model: **peer-gated `X-Real-IP`, with a rightmost-untrusted `X-Forwarded-For` fallback**

**`X-Real-IP` is read, and it is PEER-GATED. This is the load-bearing constraint of the whole
block.** Trusting `X-Real-IP` *unconditionally* is the **one** variant strictly worse than the
status quo: it would replace an attacker-controlled *prefix* (`XFF[0]`) with an
attacker-controlled *whole value*. That is not a refinement, it is a regression, and it is
avoided only by the gate.

The gate is what reconciles the two facts that make this hard:

| Fact | What it forces |
|---|---|
| Through nginx, `X-Real-IP` is **overwritten** with `$remote_addr` and `web` is **not** published — a client cannot set it | (c)'s premise holds, and the fix is **Python-only** |
| In the **default dev stack** `web` **is** published on `8000:8000` with nginx behind a profile, so Django takes the connection **directly** — and any direct client can set `X-Real-IP` itself | the gate is **not optional**. A direct client is a public or unknown peer, so its `X-Real-IP` is never read |

`X-Forwarded-For` is retained as a **fallback**, resolved right-to-left, and that resolution
is correct against today's `$proxy_add_x_forwarded_for` **without** any nginx change: a client
sending `XFF: 1.2.3.4` yields `1.2.3.4, 198.51.100.7`; walking right-to-left, `198.51.100.7`
is public and is returned. The attacker's prefix is skipped because the walk *stops* at the
first non-private entry.

**Why not (a) alone — a configured trusted-proxy set.** No compose file declares `networks:`,
so a literal trusted IP is not operable without a compose change outside both blocks' file
lists. More importantly, the plan's feared failure mode — an unset or stale set collapsing
every client into one bucket, where one client locks out all logins site-wide — **does not
apply to this design**, because the private-peer half of the gate is still operative when the
set is empty. Empty set ⇒ production still resolves to nginx's address and is still
**unspoofable**; it collapses rather than bypasses, and nginx's own unforgeable
`$binary_remote_addr` limits still bound the site. The set is a purely **additive**
widening of what is already trusted, and is never the only thing trusted.

**Why not (b) alone — loopback/private ⇒ trusted, nothing else.** It is the right *safety
net* and the wrong *resolver*: a Docker sibling container (`bot`, `scheduler`) is also private
and is a different principal. (b) is kept as the **gate**; the header resolution is (c)'s job.

**Failure direction, recorded as a feature.** If a CDN or load balancer is ever inserted, the
predicate makes every client collapse onto the CDN's address. That is a **self-inflicted DoS,
immediately visible** — the safe direction. The current defect is the opposite: a *silent*
bypass nobody sees.

**Known cost, recorded, not hidden.** In the default dev stack the gate is **always open** (the
peer is the developer on loopback), so **dev silently never exercises the untrusted branch**.
The untrusted branch is exercised by unit tests only. This sentence must reach the docs
section and the commit body — a reader must not conclude the dev stack proves the gate works.

### `G-8c` — env-driven or literal: **LITERAL, and not a trusted IP at all**

The setting is a `tuple[str, ...]` of **CIDR strings** in code, defaulting to `()`. It is
**not** env-driven, for four reasons, in descending weight:

1. **There is no correct value to put in it.** No compose file declares `networks:`, so nginx's
   bridge subnet is per-deployment. Shipping an operator-facing knob whose correct value
   cannot be determined from inside the repository is shipping a trap **with a config
   surface** — a mis-set value is the self-inflicted DoS the plan itself identifies.
2. **The `# env-contract:` opt-out is not available and would be a misuse.** The test's own
   message documents the marker for *"if it is not a deployment variable"*. This **is** a
   deployment variable, so the opt-out violates the contract in spirit. And the honest route —
   an `ALLOWED_ENV_VARS` entry — costs exactly **one line in `base.py`** (`B-8d`), not four
   template edits, so there is no gate reason left to reach for the opt-out.
3. **The security argument does not need it.** The invariant that matters — *no
   public peer is trusted unless an operator lists a network containing it* —
   holds with the tuple empty and is **additive-only**: `TRUSTED_PROXY_NETWORKS`
   is `()` in `base.py`, `dev.py` and `test.py` and is not declared in `prod.py`,
   so the shipped production gate is exactly `is_loopback or is_private`, and the
   setting can only widen trust. A setting that cannot **narrow** the invariant
   is documentation, and documentation belongs in a comment and in `docs/`, not
   in the environment.
4. **The contended files are not contended.** `B-8d` removed the four-template cost, and
   `.po` files are untouched either way. Contention is not the deciding factor and is not
   claimed as one.

**Promotion path, named so it is not lost:** making the tuple env-driven is a follow-up
gated on a compose `networks:` declaration that gives nginx a stable address. Until that
exists, a code-level `()` plus a documented operator procedure is the honest floor.

### `G-8d` — setting name and type: **`TRUSTED_PROXY_NETWORKS: tuple[str, ...] = ()`**

- **Name.** Verified no Django 5.2.17 setting concerns client IP; `SECURE_PROXY_SSL_HEADER`
  governs **scheme**, not identity, and nothing in Django reads `X-Forwarded-For`. The
  name therefore shadows nothing. `TRUSTED_PROXY_NETWORKS` follows the nearest in-repo
  trust-naming precedent, `CSRF_TRUSTED_ORIGINS`, and deliberately avoids a `SECURE_` or
  `CSRF_` prefix that would be mistaken for a Django global.
- **Type.** `tuple[str, ...]` of CIDR strings — **networks, not IPs**, because a per-deployment
  container address cannot be a single literal. Annotated, matching the only annotated
  settings in `base.py` (`LOCK_TIMEOUT_SECONDS: int`, `_MAX_LOCK_TIMEOUT_SECONDS: int`).
  Membership is `ipaddress.ip_address(peer) in ipaddress.ip_network(cidr)` evaluated per
  request over a 0–2 element tuple: no import-time parsing, no `lru_cache`, no new
  abstraction (rule 5).
- **No `StrEnum`.** Recorded with its reason: `apps/core/enums.py` holds named *value sets*
  (`AdStatus`, `ConsentChoice`, `CookieCategory`, …) and a `StrEnum` member per network would
  be absurd. The three limiters use `Final` for keys and caps; this is one tuple, so it is a
  `Final`-shaped declaration, not an enum. The trust *mode* has two branches, but they are
  **the algorithm, not a setting** — and a mode that is not configurable must not be
  presented as if it were.
- **`dev.py` and `test.py` are explicit** (`TRUSTED_PROXY_NETWORKS: tuple[str, ...] = ()` in
  both), keeping the transport-parity habit. The new name **is not** added to
  `test_settings_defaults.py::_TRANSPORT_SETTINGS` — that tuple is a six-member
  `==`-compared **transport-security** contract and a trust-network list is not a transport
  setting. Tests that need a non-default value use `override_settings`.

### `G-8e` — where the helper lives: **`apps/core/utils/client_ip.py`**

`B-8c` removed the stated justification for `services/`. The package structure decides it:

- The helper is a **pure function** — `request.META` in, `str` out. It touches no cache, no
  connection, no model. `apps/core/utils/` has **zero model imports** (verified: only
  `advisory_lock.py` and `scheduler.py` import `django.db`, and neither is imported here).
- `apps/core/utils/sanitize.py` is the **structural template**: same shape (a pure transform
  over untrusted input), same `Final` constants, same Google-style `Args:`/`Returns:`, and it
  carries the same security rationale this helper does (log-injection / PII from
  user-supplied input).
- `apps/core/services/` holds services that **write**: `contact.py`, `analytics.py`,
  `site_config.py` (cached DB read), and `contact_rate_limit.py` (writes a cache counter).
- The dependency direction is satisfied either way — `telegram_bot` imports **from** `apps.*`,
  never the reverse, and no `apps.*` module imports `telegram_bot.*`. Both candidates pass.
- `apps/core/utils/__init__.py` is a bare comment (`# Core utils package`) with **no
  re-exports**, so there is **no re-export decision to make** and nothing to add. The helper
  is imported by its full path.
- `apps/core/middleware/` is a **false lead**, unchanged: `MIDDLEWARE` is a pinned 15-entry
  list (`04-VAL-001`) and a middleware taxes every request for four call sites.
- `apps/users/services/` is defensible but **inverts the dependency** — `apps.core` and
  `apps.search` would import from `apps.users`.
- **This path is part of the outbound contract** to phase 09's `API-005` media limiter, so it
  is settled here rather than moved later.

### `G-8f` — validation in the return value: **YES, for well-formedness only**

Decided explicitly, because it changes the key string.

- **The chosen value is parsed with `ipaddress` and returned canonically** (`str(addr)`).
  Unparseable ⇒ fall back to the socket peer; the socket peer unparseable ⇒ `"unknown"`. The
  helper **never returns header text verbatim and never raises.**
- **Canonicalisation changes the key for IPv6 only.** A client arriving as
  `2001:0db8:0000::1` and as `2001:db8::1` are the same client and must share a bucket.
  The three key-asserting tests all use `127.0.0.1`, which canonicalises to itself, so they
  survive — **by luck, not design.** The Implementor therefore **must** add an explicit
  IPv6 key-stability test so the survival becomes designed rather than incidental.
- **The validator does NOT reject private or reserved addresses.** That is the **gate's**
  job, and it is a trust decision, not a well-formedness one. Rejecting here would make the
  dev and test path (peer `127.0.0.1` → resolved `127.0.0.1`) fall through and change every
  key. One place decides trust; one place decides syntax.

### `G-8g` — is `B-09` mandatory: **NO. `B-08` is complete and correct on its own.**

Stated loudly because the plan's dependency table records the `B-08 → B-09` edge as **hard**,
and that is now wrong. With the peer gate, the `X-Real-IP` preference and the
right-to-left `X-Forwarded-For` walk, Django is correct against today's
`$proxy_add_x_forwarded_for` with **no nginx edit at all**. The reverse is not true and never
was: `B-09` landing alone changes nothing, because no Python code reads the header today.
`B-09` is **optional hardening** — it removes the attacker-controlled prefix at the source
rather than defending against it downstream.

**And `B-09` cannot currently be delivered, validated or rolled back by this repository's
pipeline.** Recorded so the phase's DoD is honest: `deploy.yml` never `git pull`s; the nginx
config is a **bind mount**, so `docker compose up -d` will not recreate an unchanged service;
the health gate runs **inside the web container, bypassing nginx**; and the rollback
(`up -d --force-recreate web bot`) **excludes nginx**. There is no `nginx -t`, no reload path
and no `docker compose config` gate anywhere in the repository. **That is a `B-09` problem to
solve in `B-09`, not a reason to delay `B-08`.**

### The `B-09` interface contract — what nginx must guarantee for the Python assumption to hold

| Element | Contract |
|---|---|
| **Setting** | `TRUSTED_PROXY_NETWORKS: tuple[str, ...]`, CIDR strings, `()` by default. **Present and honoured in `B-08`.** `B-09` does **not** add, rename or change it |
| **Header precedence** (gate open only) | `HTTP_X_REAL_IP` → `HTTP_X_FORWARDED_FOR` right-to-left, first non-private entry → socket peer. **`B-09` must not change this order** |
| **Return contract** | `str`: the canonical form of a valid IP, or the literal `"unknown"`. Never `None`, never raises, never verbatim header text |
| **nginx must guarantee (1)** | `proxy_set_header X-Real-IP $remote_addr;` on **every** `location` that proxies to `web`. **Already true**: 9 of 9 in `nginx.conf`, 6 of 6 in `nginx.dev.conf`. If a `location` is added without it, that location silently falls back to the `X-Forwarded-For` walk — which is still correct, but is a behaviour change nobody would notice |
| **nginx must guarantee (2)** | **`web` is not published to the host in production.** Already true: `docker-compose.yml` publishes only nginx; `docker-compose.prod.yml` adds only `db`. **If anyone ever publishes `web`, the peer gate is the only thing still holding** — and a public peer is refused, so the site degrades to `X-Forwarded-For` resolution rather than to a bypass |
| **nginx must guarantee (3)** | The `real_ip` module must **not** rewrite `$remote_addr` without a matching `set_real_ip_from`. Verified absent today. If added, `$remote_addr` becomes the *forwarded* address and the gate's premise changes silently — this is the single nginx change that could silently invalidate the whole design |
| **nginx must guarantee (4)** | `X-Forwarded-For` continues to be a **list**. `B-09`'s `$remote_addr` substitution is compatible (a one-element list) and the walk handles it |
| **`B-09`'s own constraint** | `src/backend/tests/test_nginx_config.py::test_nginx_metrics_has_proxy_headers` asserts the substring `proxy_set_header X-Forwarded-For` **inside the `= /metrics` block**. It is satisfied by both `$proxy_add_x_forwarded_for` and `$remote_addr`, so `B-09`'s edit leaves it green — but **it is a live tripwire on that block and belongs in `B-09`'s file list.** Recorded here because `B-08` may not touch it |
| **Mandatory?** | **No.** `B-09` is optional. `B-08` does not wait for it and does not depend on it |

**A `docs` obligation, and the absence to record.** `docs/ops/docker-deployment.md`'s
`## Nginx Configuration` has exactly four subsections — Rate Limiting, Security Headers,
Media Access Control, Media Security — and **no reverse-proxy or trust-model section**
(`X-10`, re-verified). This block **adds** one, under that existing heading, stating: nginx is
the first hop; `web` is not published; `X-Real-IP` is nginx-overwritten; `X-Forwarded-For` is
appended and therefore forgeable in its prefix; the peer gate is what makes either safe; the
dev stack has no proxy and so never exercises the untrusted branch; and the operator procedure
for `TRUSTED_PROXY_NETWORKS`. **A section that does not exist must not be referenced.**

**Scope.**

| Path | Symbol | Change |
|---|---|---|
| `src/backend/apps/core/utils/client_ip.py` | `get_client_ip(request) -> str` | **new module** — the single implementation, per `G-8b`/`G-8f` |
| `src/backend/apps/users/services/login_rate_limit.py` | `_get_client_ip` | **delete**; `login_rate_limit_check` delegates |
| `src/backend/apps/core/services/contact_rate_limit.py` | `_get_client_ip` | **delete**; `check_deep_link_render_rate_limit` delegates |
| `src/backend/apps/search/services/rate_limit.py` | `_get_client_ip` | **delete**; `rate_limit_check` delegates |
| `src/backend/config/settings/base.py` | `TRUSTED_PROXY_NETWORKS` | **new**, appended near the other proxy settings (`SECURE_PROXY_SSL_HEADER` / `USE_X_FORWARDED_HOST`) |
| `src/backend/config/settings/dev.py` | `TRUSTED_PROXY_NETWORKS` | **explicit** — `()` |
| `src/backend/config/settings/test.py` | `TRUSTED_PROXY_NETWORKS` | **explicit** — `()` |
| `src/backend/apps/users/services/consent_record.py` | `record_consent_action` | the `REMOTE_ADDR` read routes through the helper (`G-8a` = in). **`_anonymize_ip` is NOT touched** |
| `src/backend/apps/core/tests/test_contact_rate_limit.py` | `test_x_forwarded_for_takes_precedence` | **rewritten** (§E.2) |
| `src/backend/apps/core/tests/test_client_ip.py` | — | **new** — the helper's own unit tests (see Tests) |
| `docs/ops/docker-deployment.md` | a new subsection under `## Nginx Configuration` | the trust model, per `X-10` |

**Not in the file surface, deliberately:**

- `apps/core/services/__init__.py` — the package **does** re-export its siblings, but
  `apps/core/utils/__init__.py` is a bare comment with **no** re-exports, so there is nothing
  to add and nothing to keep consistent. Import by full path.
- `config/settings/tests/test_settings_defaults.py::_TRANSPORT_SETTINGS` — a six-member
  `==`-compared **transport-security** contract. `TRUSTED_PROXY_NETWORKS` is not a transport
  setting; adding it would put a trust list inside a TLS assertion.
- `ALLOWED_ENV_VARS` and the four `.env.*.example` templates — the setting is **not**
  env-driven (`G-8c`), and `B-8d` established no gate requires the template edits.
- Any `.po` file — **owned by another agent.** This block adds **no** user-visible string.

**Out of scope.** `docker/nginx/nginx.conf` and `docker/nginx/nginx.dev.conf` (that is
`B-09`) · nginx's `limit_req_zone $binary_remote_addr` keys (already unforgeable; phase 09
keeps them) · phase 09's `media_limit` zone and `ads/views/listings.py::media_gate` · any
change to the `cache.add`/`cache.incr` idiom or its `ValueError` fallback (leave
byte-identical) · the three rate-limit *numbers* · `MIDDLEWARE` (15 entries, `04-VAL-001`) ·
`_anonymize_ip`'s body (phase 06 `06-PII-107` BLOCK 6 constraint 5).

**Tests required.**

1. `test_untrusted_public_peer_cannot_spoof_the_rate_limit_key` — a **public** `REMOTE_ADDR`
   plus `X-Forwarded-For` produces **the same key** as a request with no header at all.
   **This test must land before the change** (source plan's rule, kept).
2. `test_untrusted_peer_cannot_spoof_the_rate_limit_key` — the same for a peer that is
   **neither** loopback **nor** private, carrying `X-Real-IP`. This is the assertion that
   pins the **gate** on the header `B-09`'s whole contract rests on, and it is the one the
   unconditional-`(c)` variant cannot pass.
   *(Historical planned names — **superseded by what shipped**: items 1 and 2 landed as
   `apps/core/tests/test_client_ip.py::TestPublicPeerCannotSpoof::test_public_peer_ignores_x_forwarded_for`
   and `…::test_public_peer_ignores_x_real_ip`. The name in this list exists nowhere in the
   repository.)*
3. `test_trusted_peer_real_ip_is_honoured` — a loopback `REMOTE_ADDR` plus a single-entry
   `X-Real-IP` resolves to the header value.
4. `test_real_ip_takes_precedence_over_forwarded_for` — a loopback peer sending **both**
   resolves to `X-Real-IP`. Pins the precedence order `B-09` is contractually forbidden to
   change.
5. `test_chain_resolves_to_the_last_untrusted_entry` — a multi-hop `X-Forwarded-For` resolves
   to the **rightmost** untrusted entry, not the first element. **This is the assertion the
   current `split(",")[0]` cannot pass**, and it is the test that makes `B-08` correct against
   today's `$proxy_add_x_forwarded_for` with no nginx change.
6. `test_malformed_header_falls_back_to_socket_peer` — a garbage `X-Real-IP` yields the
   peer. **This is the regression that would otherwise become an HTTP 500** through
   `consent_record.py::_anonymize_ip`.
7. `test_missing_remote_addr_returns_unknown` — a bare `HttpRequest()` (whose `META` is `{}`)
   returns `"unknown"` and does **not** raise. Pins the load-bearing default.
8. `test_ipv6_equivalent_forms_share_one_key` — two spellings of the same IPv6 address
   produce the **same** key. Written because the three existing key assertions use
   `127.0.0.1`, which canonicalises to itself — they survive by luck, not by design.
9. `test_all_four_consumers_agree_on_one_key` — the interaction test: the login, the
   deep-link, the search/autocomplete limiter **and** `record_consent_action` resolve the
   same value from the same request object. This is what proves the de-duplication rather
   than asserting that a module exists. **Resolved 2026-10-02:** the shipped test covered
   login + deep-link + search + autocomplete but omitted `record_consent_action`; the
   consumer was added (with `django_db`) so the ledger's four consumers are all covered.
10. `test_listed_network_with_public_peer_opens_gate` — the corrected invariant
    from `B-8f`, **already present** in `apps/core/tests/test_client_ip.py`
    (test 5 of the shipped module): a public peer is trusted **only** when an
    operator lists a network containing it. This is the positive half; the
    negative half — a public peer refused under a non-matching tuple — is
    `test_public_peer_stays_untrusted_with_trusted_networks_set`. **Do not invent
    a new test for this.**
11. Behaviour regression: an existing burst still trips;
    `apps/users/tests/test_login.py::TestLoginRateLimitCheck` passes **unchanged**;
    `test_contact_rate_limit.py`'s other cases pass unchanged;
    `test_consent_records.py` passes unchanged.
12. `config/settings/tests/test_settings_defaults.py`, `test_env_allowlist.py` and
    `test_env_allowlist_reverse.py` green (the last two **trivially** — no env read is added;
    that is the point of `G-8c`).

**Gates.** `G-8`, `G-8a` … `G-8g` — **all CLOSED 2026-10-01 by the `B-08` Planner** (see
*Gate decisions* above and `§H`).

**Agents.** Implementor **yes** · Researcher **yes** — done, and its findings are the
corrected facts above · Planner **yes** — done · Validator **yes** — the collapse-vs-bypass
distinction and the "untrusted branch is never exercised in dev" claim are **invisible to a
green suite**; the Validator must read the gate, not the test result. **Auditor — no:
deviation, justified.** `Q2`, the topology question this block's design turns on, is already
answered by `C-6`; re-deriving it is duplicated work. This remains the clearest deviation from
the source plan's HIGH → all-agents rule in this document.

**Risks.**

- **Self-inflicted DoS** — mitigated *differently* from §F.2 row 4, which is superseded here.
  The old mitigation was "trust-nothing default"; the corrected invariant is **"no public
  peer is trusted unless an operator lists a network containing it."** `TRUSTED_PROXY_NETWORKS`
  is `()` in `base.py`, `dev.py` and `test.py` and is not declared in `prod.py`, so the
  shipped production gate is exactly `is_loopback or is_private`. The setting is **purely
  additive** — it can widen trust, never narrow it — so a **mis-set value cannot cause the
  collapse-DoS**; the residual it creates is a **bypass** if an operator lists a public
  range. The collapse case still needs a **private** peer in front of Django, which is a
  topology change, not a config value.
- **The dev stack never exercises the untrusted branch** (the gate is always open on
  loopback). Accepted: the branch is covered by unit tests 1, 2 and 10, and the docs section
  says so. **A reader must not conclude the dev stack proves the gate works.**
- **A public peer reaching Django in production** (someone publishes `web`) fails the gate,
  so **no header is read at all** and the bucket is per-public-peer. That is correct and
  unspoofable, and it is immediately visible as a rate-limit anomaly — but it is a
  degradation, not a bypass, and it must not be "fixed" by trusting the header.
- **Adding the `real_ip` module to nginx without `set_real_ip_from`** would silently
  invalidate the gate's premise. Recorded in the `B-09` contract above; nginx is `B-09`'s
  file, not this block's.
- **Phase 09's media limiter** extending onto a *copy* of the helper concurrently
  (§D item 19). Mitigated: the path is published in this block's brief and in the outbound
  note.
- **`ALLOWED_ENV_VARS` collision in `base.py`** — another block just edited it. Mitigated:
  `TRUSTED_PROXY_NETWORKS` is **not** an env read, so this block adds **nothing** to
  `base.py::ALLOWED_ENV_VARS` and makes **one** surgical append near the existing proxy
  settings. Re-read `base.py` immediately before editing.

**Rollback.** Revert the three call sites to their local `_get_client_ip` and delete the new
module and the three setting declarations; the declaration is additive. **`record_consent_action`
reverts too** — it is one line. **Rollback restores the spoofable behaviour** and the
`AddressValueError` crash path: state that plainly in the rollback note.

**Definition of done.** Tests 1–12 green · **exactly one** client-IP implementation exists in
the tree — verify by searching for `_get_client_ip`, `HTTP_X_FORWARDED_FOR` and
`HTTP_X_REAL_IP` across `apps/` **and `src/telegram_bot/`**, not by trusting this document ·
**no public peer is trusted unless an operator lists a network containing it**
(test 10); `TRUSTED_PROXY_NETWORKS` is `()` in `base.py`, `dev.py` and `test.py`
and undeclared in `prod.py`, so the shipped gate is exactly
`is_loopback or is_private` ·
`dev.py` and `test.py` are explicit · `test_env_allowlist_reverse.py` and
`test_env_allowlist.py` green · the docs subsection exists under `## Nginx Configuration` and
**the dev-stack gap is stated in it** · `G-8a`…`G-8g` recorded with decisions and authors ·
**`B-08` is complete without `B-09`, and this commit body says so.**

**Implementor brief.**

```yaml
id: 04-b08-client-ip-helper
title: One peer-gated client-IP helper replacing three trusting copies
priority: high
depends_on: [G-8 closed, G-8a closed, G-8b closed, G-8c closed, G-8d closed, G-8e closed, G-8f closed, G-8g closed]
source_reference: .ai/plans/04-auth-login-remediation.md
source_section: BLOCK 7 — trusted-proxy client IP (Python half)
source_blocks: ["BLOCK 7", "04-AUT-003"]
description: >
  Replace three logic-identical, unconditionally-trusting _get_client_ip functions
  (two byte-identical) with one helper in apps/core/utils/client_ip.py that GATES ON
  THE SOCKET PEER before reading any header, prefers nginx's already-overwritten
  X-Real-IP, falls back to an X-Forwarded-For walk that resolves the RIGHTMOST
  untrusted entry, and returns a canonically-validated address or the literal
  "unknown". Route consent_record.py's fourth read through the same helper. No nginx
  change is required and B-09 does not block this block.
goals:
  - "a public peer's X-Forwarded-For or X-Real-IP cannot change the rate-limit key"
  - "a loopback/private peer's X-Real-IP is honoured, and takes precedence over X-Forwarded-For"
  - "X-Forwarded-For resolves to the RIGHTMOST untrusted entry, so today's appended header is already safe"
  - "all four consumers share one implementation - exactly one exists in the tree"
  - "a malformed address never reaches consent_record.py::_anonymize_ip (no AddressValueError / HTTP 500)"
  - "no public peer is trusted unless an operator lists a network containing it (the shipped gate is is_loopback or is_private; the tuple only widens trust)"

extra_context: |
  ALL BINDING CONSTRAINTS ARE IN THE PROSE ABOVE. Read, in this order, before editing:
    - "Corrections applied"          six plan claims corrected against the live tree
    - "Gate decisions"               G-8a .. G-8g, the chosen design, and the rejected options
    - "The B-09 interface contract"  what nginx must guarantee, and that B-09 is NOT mandatory
    - "Scope" / "Not in the file surface, deliberately" / "Out of scope"
    - "Risks"                        including the dev-stack gap that must be documented

  THE ALGORITHM, exactly:
    peer = META.get("REMOTE_ADDR")
    if peer is absent            -> return "unknown"            (never KeyError)
    if peer does not parse       -> return "unknown"
    if peer is neither loopback nor private
       and not inside any CIDR in settings.TRUSTED_PROXY_NETWORKS
                                -> return canonical(peer)       (NO header is read)
    # gate is open from here
    x_real = META.get("HTTP_X_REAL_IP")
    if x_real parses             -> return canonical(x_real)
    for entry in reversed(META.get("HTTP_X_FORWARDED_FOR", "").split(",")):
        entry = entry.strip()
        if entry parses and is not loopback and not private
                                  -> return canonical(entry)
    return canonical(peer)

  MUST NOT: add a middleware; read the header before the gate; reject private addresses in
  the validator (that is the GATE's job, and doing it here changes every dev/test key);
  index META["REMOTE_ADDR"]; return header text verbatim; change the cache.add/cache.incr
  idiom or its ValueError fallback; change the three rate-limit numbers; touch
  consent_record.py::_anonymize_ip; touch MIDDLEWARE; touch any .po file; touch any nginx
  file; add a StrEnum.

files:
  - path: src/backend/apps/core/utils/client_ip.py
    targets:
      - type: function
        name: get_client_ip
    note: >
      NEW module, in utils/ not services/ (G-8e: the helper is a pure function; utils/ has
      zero model imports; sanitize.py is the structural template). House style to match from
      sanitize.py: module docstring stating purpose, Google-style Args:/Returns:,
      `Final` for fixed values, `TYPE_CHECKING` for typing-only imports. The three limiters
      each declare an UNUSED logger - do NOT replicate that smell. Run ruff on this file.

  - path: src/backend/apps/users/services/login_rate_limit.py
    targets:
      - type: function
        name: _get_client_ip        # DELETE
      - type: function
        name: login_rate_limit_check # ip = _get_client_ip(request) -> the shared helper
    note: "the cache.add/cache.incr body stays byte-identical; only the ip assignment changes"

  - path: src/backend/apps/core/services/contact_rate_limit.py
    targets:
      - type: function
        name: _get_client_ip        # DELETE
      - type: function
        name: check_deep_link_render_rate_limit
    note: "the key is built inline in .format(ip=_get_client_ip(request)) - re-point that one expression"

  - path: src/backend/apps/search/services/rate_limit.py
    targets:
      - type: function
        name: _get_client_ip        # DELETE
      - type: function
        name: rate_limit_check

  - path: src/backend/apps/users/services/consent_record.py
    targets:
      - type: function
        name: record_consent_action
    note: >
      G-8a = IN. Re-point the ip_address line from request.META.get("REMOTE_ADDR") to the
      shared helper. _anonymize_ip's BODY IS NOT TOUCHED - phase 06 06-PII-107 BLOCK 6
      binding constraint 5 requires its behaviour to be unchanged, and only its input
      changes. Keep the `or None` semantics for the "no request" path untouched.

  - path: src/backend/config/settings/base.py
    targets:
      - type: setting
        name: TRUSTED_PROXY_NETWORKS
    note: >
      ONE surgical append, near the existing SECURE_PROXY_SSL_HEADER / USE_X_FORWARDED_HOST
      lines. Declared as TRUSTED_PROXY_NETWORKS: tuple[str, ...] = () with a comment naming
      the peer-gate invariant. This file is CONTENTED - another block just edited it. Re-read
      it immediately before editing and stop on a concurrent change. DO NOT touch
      ALLOWED_ENV_VARS (phase 02 owns it) and DO NOT reorder any existing setting.

  - path: src/backend/config/settings/dev.py
    targets:
      - type: setting
        name: TRUSTED_PROXY_NETWORKS
  - path: src/backend/config/settings/test.py
    targets:
      - type: setting
        name: TRUSTED_PROXY_NETWORKS
    note: "both explicit, both () - the setting is NOT env-driven (G-8c), so no ALLOWED_ENV_VARS entry and no .env.*.example edit"

  - path: src/backend/apps/core/tests/test_client_ip.py
    targets: []
    note: "NEW test module for tests 2, 3, 4, 6, 7, 8, 10 (see the Tests required list)"

  - path: src/backend/apps/core/tests/test_contact_rate_limit.py
    targets:
      - type: function
        name: test_x_forwarded_for_takes_precedence
    note: >
      REWRITE in place, do not delete - the record of the old rule must stay. It currently
      passes unchanged (its only assertion is `is True` on a fresh counter), so this is a
      documentation act: rename to the untrusted-peer form and make the key the subject.
      The other tests in this file, including the five TestDeepLinkRenderRateLimitView
      cases that pre-fill cache.set("telegram_dl_rl:127.0.0.1", 60), pass UNCHANGED under
      this design and must not be edited.

  - path: docs/ops/docker-deployment.md
    targets:
      - type: section
        name: "Nginx Configuration"
    note: >
      Add ONE subsection under the existing "## Nginx Configuration" heading (X-10: no
      reverse-proxy section exists today - do not reference one that does not). It must
      state: nginx is the first hop and web is not published; X-Real-IP is nginx-overwritten;
      X-Forwarded-For is appended, so its prefix is forgeable; the peer gate is what makes
      either safe; the dev stack has no proxy so the untrusted branch is never exercised
      there; and the operator procedure for TRUSTED_PROXY_NETWORKS.

changes:
  - action: add_code
    description: >
      Create apps/core/utils/client_ip.py::get_client_ip implementing the algorithm in
      extra_context verbatim; add TRUSTED_PROXY_NETWORKS to base.py, dev.py and test.py;
      delete the three local _get_client_ip functions and re-point their three call sites;
      re-point consent_record.py::record_consent_action's IP read; rewrite
      test_x_forwarded_for_takes_precedence; add apps/core/tests/test_client_ip.py; add the
      docs subsection. All in ONE commit with the tests (the ledger's governing rule).

acceptance_criteria:
  - "a public peer's header yields the same key as no header at all - for BOTH headers"
  - "a loopback/private peer's X-Real-IP is honoured and outranks X-Forwarded-For"
  - "a multi-hop X-Forwarded-For resolves to the rightmost untrusted entry, not the first"
  - "a malformed header value falls back to the socket peer and never raises"
  - "a bare HttpRequest() with an empty META returns 'unknown' and does not raise KeyError"
  - "two spellings of one IPv6 address produce one key"
  - "all three limiters AND record_consent_action resolve the same value from one request"
  - "a public peer is refused under override_settings with a NON-EMPTY TRUSTED_PROXY_NETWORKS"
  - "exactly one client-IP implementation exists in apps/ and src/telegram_bot/ - verify by search, not by reading this brief"
  - "the cache.add/cache.incr idiom and its ValueError fallback are byte-identical"
  - "consent_record.py::_anonymize_ip is byte-unchanged"
  - "no .po file, no nginx file, no MIDDLEWARE entry, and no new dependency was touched"
  - "test_env_allowlist_reverse.py, test_env_allowlist.py and test_settings_defaults.py green"

traps:
  - "A bare HttpRequest() starts with META == {}. The current .get(..., 'unknown') default is LOAD-BEARING. Subscripting META['REMOTE_ADDR'] raises KeyError in three existing tests."
  - "TWO META-assignment styles are live: whole-dict replacement (request.META = {...} in test_login.py) and item assignment (request.META['REMOTE_ADDR'] = ip in test_contact_rate_limit.py and test_autocomplete.py). Both must keep working."
  - "django/test/client.py hard-codes REMOTE_ADDR='127.0.0.1' and wsgi.url_scheme='http' and is NOT proxy-aware. A unit test can verify the trust decision and key agreement; it CANNOT verify anything about nginx or the bridge address. Do not write a test that tries."
  - "consent_record.py::_anonymize_ip has no try/except around int(ipaddress.IPv6Address(ip)) - a value with no '.' that is not valid IPv6 raises AddressValueError -> HTTP 500. Your helper's validation is what closes it. Do not 'fix' it by editing _anonymize_ip (phase 06 owns its behaviour)."
  - "src/backend/tests/test_nginx_config.py::test_nginx_metrics_has_proxy_headers asserts the substring 'proxy_set_header X-Forwarded-For' inside the '= /metrics' block. Do not touch it - it is B-09's live tripwire and belongs in B-09's file list."
  - "The three existing key-asserting tests all use 127.0.0.1, which canonicalises to itself, so they survive by LUCK. Test 8 exists so the survival becomes designed."
  - "The test DB flakes: stale xdist shards collide on several unique keys plus DeadlockDetected. That is NOT a code regression. If an error names a symbol you did not touch, re-run before believing it."

commands:
  - "uv run ruff check --fix src/backend/apps/core/utils/client_ip.py src/backend/apps/core/services/contact_rate_limit.py src/backend/apps/search/services/rate_limit.py src/backend/apps/users/services/login_rate_limit.py src/backend/apps/users/services/consent_record.py src/backend/config/settings/"
  - "uv run basedpyright src/backend/apps/core/utils/client_ip.py"
  - "$dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'"
  - "$dc run --rm -e PYTEST_OPTS='--create-db --tb=short src/backend/apps/core/tests/test_client_ip.py src/backend/apps/core/tests/test_contact_rate_limit.py' test"
  - "$dc run --rm -e PYTEST_SKIP_MARKERS=seed test"
  - "git add <one path at a time>   # never git add -A / git add . / git checkout / git stash / git reset"

commit_body_must_state:
  - "B-08 is complete and correct WITHOUT any nginx change; B-09 is optional hardening, not a prerequisite."
  - "X-Real-IP is read but PEER-GATED. Unconditional trust would be strictly worse than the pre-fix code."
  - "The dev stack never exercises the untrusted branch (no proxy in the default dev topology)."
  - "Rollback restores the spoofable key and the latent AddressValueError path."
```

---

### B-09 — nginx `X-Forwarded-For` + rollout (`04-AUT-003`, edge half) — **PLANNED 2026-10-02 · `G-9a`…`G-9e` ALL CLOSED · EDGE CONFIG EDIT DEFERRED**

| | |
|---|---|
| **Findings owned** | `04-AUT-003` (edge half) |
| **Depends on** | `B-08` (**shipped** — `49e741f`/`65efb3a`… re-verify at start) · **`G-9a`, `G-9b`, `G-9c`, `G-9d`, `G-9e` — ALL CLOSED 2026-10-02 by this Planner.** The block may start |
| **Blocks** | nothing in-plan |
| **Priority** | P1 · **Risk HIGH for the config edit it does not make** · **the block's own code surface is LOW risk** |
| **Ships** | **no nginx config change** · three textual trust-model tests · one operator-runbook documentation step · a recorded residual |
| **Defers** | the `X-Forwarded-For` directive change and the `real_ip` module — **recorded with owner and trigger below** |

**Outcome in one sentence.** With `B-08` shipped, **Django never reads `X-Forwarded-For` in
production at all**, because `proxy_set_header X-Real-IP $remote_addr;` is set at every
proxied location and `get_client_ip` returns on `X-Real-IP` — so the edge directive this
block was written to change **carries no weight on the resolution path**, while the config
edit needed to change it **cannot be delivered, validated or rolled back by this
repository's pipeline**. The block therefore ships the one thing that is deliverable and
was missing: **an executable invariant for the one nginx line the shipped Python half
actually depends on.**

---

## Verified starting state — re-verified 2026-10-02 at `8ecdaba`, **re-confirmed at `cc3af4f`**

**Drift note (recorded, because this block's facts are all HEAD-sensitive).** HEAD moved
`8ecdaba` → `cc3af4f` (`test(settings): scope the session-lifetime tests to the writes they
exclude`) during this planning pass. **Every fact in the table below was re-verified at
`cc3af4f`**, and `git diff --name-only 8ecdaba..cc3af4f -- docker/nginx/ src/backend/tests/
src/backend/apps/core/utils/client_ip.py .github/workflows/deploy.yml` is **empty** — the
intervening commit touched `src/backend/config/settings/base.py` and
`src/backend/config/settings/tests/test_session_policy.py` only, i.e. **none** of this block's
surfaces. `real_ip` is still **0 matches** under `docker/nginx/`; `test_nginx_config.py` still
has exactly **4** tests; `deploy.yml` still has **no `git` command** (its one `git ` match is an
input *description*, *"Git SHA from the CI build to deploy"*), and the rollback line is still
`up -d --force-recreate --remove-orphans web bot`.

| Fact | Value | Verified by |
|---|---|---|
| `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;` | **9** in `nginx.conf`, **6** in `nginx.dev.conf` — **15 total** | `nginx.conf`: `/static/`, `/media/`, `/login/`, `/search/`, `/health/`, `/moderation/`, `/csp-report/`, `= /metrics`, `/` · `nginx.dev.conf`: the same minus `/health/`, `/csp-report/`, `= /metrics` |
| `proxy_set_header X-Real-IP $remote_addr;` | **9/9** and **6/6** — `proxy_set_header` **overwrites**, so unforgeable *through nginx* | both files, every proxied location |
| `limit_req_zone` keys | **3 zones** (`login_limit`, `search_limit`, `browse_limit`), all on `$binary_remote_addr` — **unforgeable** | both files |
| `location` blocks | 10 in `nginx.conf`, 7 in `nginx.dev.conf`; the extra one in each is `/protected-media/` (`internal; alias /media_volume/`) — **no proxy, no headers** | both files |
| `set_real_ip_from` / `real_ip_header` | **ABSENT — zero matches tree-wide under `docker/nginx/`** | `grep real_ip docker/nginx/` |
| `REMOTE_ADDR` seen by Django in production | **always nginx's private container IP** (no compose file declares `networks:`, so the bridge subnet is per-deployment) | `C-6` |
| `TRUSTED_PROXY_NETWORKS` | **`()`** in `base.py`, `dev.py`, `test.py` | `G-8d` |
| **⇒ `B-08`'s peer gate in production** | **ALWAYS OPEN** — the peer is private, and the private branch of the gate needs no configured network | derived |
| Production readers of `X-Real-IP` / `X-Forwarded-For` | **exactly one module**: `apps/core/utils/client_ip.py` (lines 85, 89). Everything else is tests | tree-wide search |
| Dev topology | `docker-compose.dev.override.yml` publishes `web` on `8000:8000` and gates nginx behind `profiles: ["use-nginx"]` ⇒ **default dev stack has no proxy** and the peer is a **public** client ⇒ the gate is **CLOSED** and headers are correctly ignored | `C-6` / `G-8b` |

**Both topologies are live in one codebase, and the gate is correct in each — open behind
nginx, closed in front of it. That is the design working, not a contradiction to resolve.**

**The decisive observation, and the whole block in one line.** `get_client_ip` consults
`X-Real-IP` **first** and returns immediately when it parses (`client_ip.py` lines 85–87).
Through nginx `X-Real-IP` is **always** present and **always** valid. **Therefore the
`X-Forwarded-For` branch is unreachable in production.** `XFF[0]` may well still be
attacker-controlled — it is — but **nothing reads it.** Any argument for changing the
`X-Forwarded-For` directive must first explain what behaviour it would alter, and the
answer is: **none, for the only production reader in the tree.**

---

## Corrections applied — 2026-10-02 by the `B-09` Planner

Verified against the live tree at `8ecdaba` and re-confirmed at `cc3af4f` (see the drift note
above — the intervening commit touched none of this block's surfaces). Four claims in this
block's prose and in the brief as inherited were wrong or overstated; each one changed the
decision.

| # | The inherited text said | The tree says | Consequence |
|---|---|---|---|
| `B-9a` | *"Any change that removes or rewrites that directive turns this test red"* — i.e. `test_nginx_metrics_has_proxy_headers` constrains the **choice of directive** | it asserts the **directive name as a substring inside the `= /metrics` block** and **never inspects the value**. `$proxy_add_x_forwarded_for` → `$remote_addr` leaves it **GREEN** | **the test was never a constraint on *which* directive**, so it cannot be cited as a reason to prefer one. It turns red only on removing/renaming the directive or on changing the `location = /metrics` key. The block's own §I.7 was right and the framing around it was not |
| `B-9b` | *"`deploy.yml` never `git pull`s" — implying the file might reach the host another way | **no `git` command of any kind** appears in the SSH script. `actions/checkout@v4` runs on `runs-on: ubuntu-latest`, an **ephemeral runner** discarded at job end | the defect is **stronger** than recorded: it is not "may not take effect", it is **cannot be delivered at all**. `git -C /app pull` is an **operator** step, and `rollback.md` already assumes the host is a git working tree (it documents config rollback "via `git checkout`") |
| `B-9c` | `G-8g`/`I.10` pt 3: the `real_ip` module *"is the **single** nginx change that could silently invalidate the whole design"* | correct that it would, but **wrong that it is the only one**. `proxy_set_header X-Real-IP $remote_addr;` is **equally load-bearing and far likelier to be touched** — it is the branch `B-08` returns on, its absence silently reroutes resolution to the walk, and a "simplify the headers" edit or a switch to `$http_x_real_ip` would substitute a client-controlled **whole value** for a client-controlled **prefix** | the gate (`G-9d`) is built around the **`X-Real-IP` directive**, not around `real_ip`, with `real_ip` covered as the second case. Recorded so `B-08`'s outbound contract and this block do not contradict each other |
| `B-9d` | §E lists `src/backend/tests/test_nginx_config.py` under "Extend `_location_block`; do not write a new parser", implying one helper suffices | one helper does not suffice: `_location_block` takes a **match string** and returns **one** block; the gate needs **all** locations, and needs them from **two** files. `nginx.dev.conf` has **no** `= /metrics`, `/health/` or `/csp-report/` block, so a `= /metrics`-anchored helper cannot reach it | extend the **brace-depth scan** into a shared form and add a **proxied-locations enumerator** beside it; `_location_block` delegates so its four callers are byte-for-byte unaffected. Still one parser, not two |

---

## `Q9` is ANSWERED, and the answer is a content gate with no syntax gate (`C-7`, `X-14`)

`nginx -t` appears **nowhere** in `.github/`, `Makefile`, `Makefile.ps1`, `docker/` or any
script — only in plan prose. `deploy.yml`'s health gate is
`docker compose exec -T web curl -sf http://localhost:8000/health/ready/`, i.e. port 8000
**inside the web container, bypassing nginx entirely** — so the deploy health check
**cannot detect a broken nginx configuration**. **`src/backend/tests/test_nginx_config.py`
is a real, in-repo, fast-gate structural gate** (`pytestmark = [pytest.mark.unit]`) exporting
a reusable brace-depth extractor `_location_block(text, location_match)`.

**Every assertion in the module, and its status under the chosen outcome** (nothing is
touched, so nothing moves — stated per-assertion because the prompt's framing turned on it):

| Test | Asserts | Scope | Under the chosen outcome |
|---|---|---|---|
| `test_nginx_config_exists` | `docker/nginx/nginx.conf` exists | path | **GREEN** — untouched |
| `test_nginx_metrics_has_proxy_pass` | the `= /metrics` block exists and contains the substring `proxy_pass` | that block | **GREEN** — untouched |
| `test_nginx_metrics_has_proxy_headers` | the `= /metrics` block exists and contains each of the substrings `proxy_set_header Host`, `proxy_set_header X-Real-IP`, `proxy_set_header X-Forwarded-For`, `proxy_set_header X-Forwarded-Proto` | that block | **GREEN** — **value never inspected** (`B-9a`). All four directives remain |
| `test_nginx_metrics_restricted_to_localhost` | the `= /metrics` block exists and contains `allow 127.0.0.1` **and** `deny all` | that block | **GREEN** — untouched |

**A trap the Implementor must know (`B-9d`, not obvious from reading the helper).**
`_location_block` finds the **first** line containing its match string via `re.search`. The
literal `= /metrics` therefore must not be introduced **anywhere earlier in the file** —
**not even in a comment above the real location** — or all four pre-existing tests silently
switch to parsing the wrong block. This is why the new tests must be **location-agnostic**
rather than reusing a `= /metrics` anchor.

---

## Gates — `G-9a`, `G-9b`, `G-9c`, `G-9d`, `G-9e`, ALL CLOSED

Full reasoning, the rejected options and the weigh-in for each is in **`§I.7`** and
**`§I.9`**; the summary rows are in **`§H`**. The shape in one paragraph:

> **`G-9a` — no config edit; the cross-phase conflict is closed by non-claiming.** Phase 09
> keeps both `.conf` files and its BLOCKS 10/11/12 — they are the blocks that already carry
> the `nginx -t`-before-rolling discipline. Phase 04 takes only the test module. **`G-9b` —
> no repo-verifiable delivery mechanism exists, and that is the reason for the deferral.**
> `deploy.yml` cannot deliver the file (ephemeral-runner checkout, no git in the SSH
> script), the config is a `:ro` bind mount so `up -d` will not recreate an unchanged
> service, the health gate bypasses nginx, and rollback excludes nginx — so the deliverable
> is an **operator runbook**, and a `docker compose config` gate is **rejected** (`G-9e`).
> **`G-9c` — no directive changes.** `$remote_addr` changes nothing observable (the
> `X-Forwarded-For` branch is unreachable in production); the `real_ip` module is **actively
> harmful** in this topology (nginx is the first hop, so there is nothing to trust, and
> `set_real_ip_from 0.0.0.0/0` would additionally destroy `limit_req_zone
> $binary_remote_addr`). **`G-9d` — three textual tests** pinning the invariant.
> **`G-9e` — no `docker compose config` gate**, on the repository's own recorded precedent.

### `G-9c` in detail — why `real_ip` is refused rather than merely deferred

`real_ip` is **verified absent**, so this is a live decision, not a description of the
status quo. nginx's realip module replaces `$remote_addr` **only** for peers matched by a
`set_real_ip_from` entry. Three shapes, and none is safe here:

1. **`real_ip_header` alone** — **inert.** No `set_real_ip_from` matches, so `$remote_addr`
   is unchanged. Harmless but misleading: it looks like the edge is hardened and is not.
2. **`set_real_ip_from <anything>` with a default or `X-Real-IP` header** — at the edge the
   incoming `X-Real-IP` is **the client's own**, so `$remote_addr` becomes
   attacker-controlled. This is the exact hazard `G-8g` recorded, now **refused**.
3. **`set_real_ip_from 0.0.0.0/0`** (or `::/0`) — **the worst case in the whole block, and
   the reason this decision is recorded rather than left open.** It makes **every** client a
   "trusted proxy", so `$remote_addr` is client-chosen. **`limit_req_zone
   $binary_remote_addr` keys off `$remote_addr`**, so this single line would **destroy the
   nginx-side rate limiting that `B-08` declared already unforgeable** — and **no test in the
   repository covers it.** Shipping hardening that removes a control is a net loss.

**The structural reason, and the one that settles it:** `C-6` establishes nginx **is** the
first hop — no CDN, no load balancer, no proxy in front of it. **`real_ip` exists to
recover a client's address from *behind* a trusted upstream proxy. There is no upstream
proxy, so there is no address to recover.** `set_real_ip_from` has **no legitimate value to
name in this topology**; the only expressible values are inert or catastrophic. Option (ii)
is therefore not "defence in depth" — it is **attack surface with no defender**, and it is
**REFUSED**, not deferred.

---

## `G-9d` — the executable trust-model gate (the block's only code deliverable)

**Design principle, and it is the opposite of the inherited design.** Assert the
**invariant that makes `B-08` correct**, never the **current value**. `B-07`'s `G-B` already
set the precedent — *"Do not assert the action's absence — that would pin a decision as an
invariant"* — and the inherited test 1 (*"no proxied location uses `$proxy_add_x_forwarded_for`
any more"*) would have had to assert the **opposite** of today's config, i.e. pin the
forgeable-but-defended appending form as permanent. **So the `X-Forwarded-For` value is not
asserted at all.**

All three tests are **textual**, `pytest.mark.unit`, `Path.read_text()` only — **no
`nginx -t` (not runnable in CI), no `docker compose config` shell-out (`G-9e`), no new
dependency** (`ruamel.yaml` is not even needed: plain string/regex work, matching this
module's existing approach). All three run over **both** `.conf` files, which is what
prevents the recorded dev/prod divergence, and both files satisfy them today.

| # | Test name | Asserts | The silent failure it catches | Green today because |
|---|---|---|---|---|
| 1 | `test_proxied_locations_overwrite_x_real_ip` | every location containing `proxy_pass` contains **exactly** `proxy_set_header X-Real-IP $remote_addr;` | the `X-Real-IP` line being **deleted or repointed**. `B-08` returns on that header, so removing it silently reroutes every production request onto the `X-Forwarded-For` walk — the weaker fallback — with **no other gate in the repository noticing** | 9/9 and 6/6 sites match exactly |
| 2 | `test_no_proxied_location_forwards_a_client_echo_variable` | **no `proxy_set_header` line** in either file takes its value from a client-echo `$http_*` variable | `proxy_set_header X-Real-IP $http_x_real_ip;` — the **most likely** way `B-08`'s design breaks, and the one a "pass the header through" edit produces. It substitutes a client-controlled **whole value** for a client-controlled **prefix** | no `proxy_set_header` line uses `$http_*`. **The scan must be restricted to `proxy_set_header` lines** — `log_format main` legitimately uses `$http_x_forwarded_for` and `$http_user_agent`, so a whole-file `$http_` check would be red today |
| 3 | `test_real_ip_trust_is_never_wildcard` | **if** any `set_real_ip_from` is present, **no** argument is a wildcard (`0.0.0.0/0`, `::/0`, `0.0.0.0/0 ipv6`, bare `all`), **and** an explicit `real_ip_header` accompanies it | `G-9c` shape 3 — the one edit that would let any client rewrite `$remote_addr` **and** silently break `limit_req_zone $binary_remote_addr` | `real_ip` is absent, so the conditional body does not execute |

**Deliberately NOT asserted, with reasons — so the next editor does not "helpfully" add them:**

- **The `X-Forwarded-For` value.** Pinning `$proxy_add_x_forwarded_for` would freeze the
  current forgeable-but-defended form as an invariant and **resist** a future legitimate
  `$remote_addr` switch (`G-B`).
- **The `limit_req_zone` keys.** Phase 09 BLOCK 10's surface, which the plan explicitly
  forbids changing here. Test 3 already blocks the only mechanism that could compromise them.
- **The *absence* of `set_real_ip_from`.** Same `G-B` reasoning — but note test 3 is written
  as a **safety** assertion over a conditional, which is precisely the shape that catches the
  dangerous addition **without** forbidding the harmless one.

---

## `G-9b` — the deliverability gap, confirmed, and the operator runbook

**All four defects re-verified at `8ecdaba`.** The first is stronger than the plan recorded
(`B-9b`) and the fourth has no documentation at all:

1. **The file cannot reach the host.** `actions/checkout@v4` runs on `runs-on:
   ubuntu-latest` — an ephemeral runner, discarded at job end. The host is touched only by
   the `appleboy/ssh-action` script, which contains **no `git` command of any kind**. The
   bind-mount source is the host's `/app/docker/nginx/nginx.conf`, so a committed change
   **does not reach production at all**.
2. **Even a host-side change is inert** until nginx re-reads it: it is a `:ro` bind mount,
   and `up -d` **will not recreate an unchanged service**.
3. **The deploy health gate cannot see it** — it curls port 8000 **inside the web container**,
   bypassing nginx. A broken nginx config presents as a green deploy.
4. **Rollback excludes nginx** — `up -d --force-recreate --remove-orphans web bot`. And
   `docs/ops/rollback.md` **contains no nginx step at all** (two passing mentions only), so
   the exclusion is undocumented as well as unenforced.

**Can the repository verify an nginx change? No.** Not in CI, and not without adding a
compose/containers dependency to the test service — rejected (`G-9e`). **The only mitigation
available inside the repository is therefore a textual invariant over the file (`G-9d`) plus
a documented manual procedure.**

**The operator runbook — mandatory steps for applying an nginx config change by hand.** This
is the deliverable of `G-9b`, and it is what makes option (iv) worth shipping. To be added
to `docs/ops/docker-deployment.md` by the Implementor (that file is `B-09`'s for the rollout
step per `§E`; **re-read immediately before editing and stop on a concurrent change**):

1. **Update the file on the host.** `git -C /app pull` (or
   `git -C /app checkout <sha> -- docker/nginx/nginx.conf`). **`deploy.yml` does not do
   this** — the checkout runs on the ephemeral runner and the SSH script has no git command.
   Step 1 is not optional and is the step every prior attempt at an nginx change has skipped.
2. **Validate against the running container.**
   `docker compose -f docker-compose.yml -f docker-compose.prod.yml exec nginx nginx -t`.
   Run it **inside** the container so it reads the **bind-mounted** file — that is exactly
   the file nginx will load. **`nginx -t` is NOT runnable in CI; it is an operator step and
   must be reported as performed or not performed. Claiming it passed when it was not run is
   a failed block.**
3. **Reload, do not recreate.**
   `docker compose -f docker-compose.yml -f docker-compose.prod.yml exec nginx nginx -s reload`.
   Graceful, no dropped connections, and it re-reads the bind-mounted file — whereas
   `--force-recreate` needs a changed image or an explicit flag and drops connections.
   **`docker compose up -d` alone is not sufficient** (defect 2).
4. **Verify through nginx, not around it.**
   `curl -sk https://<host>/health/live/` — from outside. **The container-internal
   `/health/ready/` check is worthless as nginx verification** (defect 3): it passes with
   nginx stopped.
5. **Rollback is entirely manual for a config change.** Revert the file
   (`git -C /app checkout <previous-sha> -- docker/nginx/nginx.conf`) and repeat steps 2–4.
   `deploy.yml`'s automated rollback **will not restore it** (defect 4), and
   `docs/ops/rollback.md` has no nginx step. **If the file is changed and the image is
   rolled back, nginx keeps the new config** — an asymmetry the operator must handle
   deliberately.

**Steps 2–4 are the same discipline phase 09 already mandates** for its BLOCKS 10–12
(`nginx -t` before rolling). Naming that explicitly is why `G-9a` resolves by
non-claiming rather than by negotiation: **the blocks that already carry this discipline
should carry the file.**

---

## Out of scope

Both `.conf` files — **this block edits neither** (`G-9a`) · `limit_req_zone` keys (already
unforgeable; phase 09 BLOCK 10 forbids changing them here) · any `server_name`, TLS,
`X-Forwarded-Host` or `/csp-report/` work (phase 09 BLOCKS 11/12) · `deploy.yml` and
`docs/ops/rollback.md` (phase 12 / ops surface; the gaps are recorded as residual, not
claimed) · the Django-side trust model (that is `B-08`'s, and it is shipped).

**Tests required.**

1. **Three** new tests in `src/backend/tests/test_nginx_config.py`, per `G-9d`, over both
   `.conf` files.
2. **All four pre-existing tests in that module pass UNCHANGED** — byte-for-byte, not
   "adapted". They are the anti-regression guard for this block's own edit.
3. **Every `B-08` test still passes** — nothing on the Python side moves, so
   `apps/core/tests/test_client_ip.py` is a **regression** check, not a target.
4. **No test can exercise a reload or a syntax parse.** The commit body must name the
   validation actually performed and state that no config change was made, so no reader can
   infer a proxy edit from this commit.

**Agents.** Implementor **yes** · Researcher **no** — **deviation, justified:** the block's
research questions (`Q9`, `U-6`, `U-7`, the topology facts) are all **closed and
re-verified against the live tree in this Planner pass**, and `Q9` is answered by the audit
(`C-7`, `X-14`). Re-running a Researcher would re-derive facts already re-checked at
`8ecdaba`. Planner **yes** — `G-9a`…`G-9e` are all judgement calls. Validator **yes** — the
residual record and the three-test design must be checked for **honesty**, i.e. that the
block is not reported as having hardened the edge. Auditor **no** — `Q2`/`Q9` are closed by
the audit.

**Risks.** **The block's residual risk is misreporting, not availability**: a reader who sees
a `B-09` commit touching `test_nginx_config.py` may infer an edge fix that did not happen —
mitigated by the residual record, the explicit *"no config change"* line in the DoD, and the
commit-body requirement · **the three new tests could be written to pin current values
instead of the invariant**, re-creating the `G-B` mistake — mitigated by `G-9d`'s table ·
test 2's whole-file variant would be red today (`log_format` uses `$http_*`) — mitigated by
specifying the scan is line-scoped to `proxy_set_header` · **a dev/prod divergence in the
files themselves remains open** — it is phase 09's, recorded as residual · the
non-delivery defect (`G-9b`) is **unchanged by this block** and remains the real gap.

**Rollback.** Revert the three tests. **Rollback of a config change is not in scope because
no config change is made** — the manual procedure in `G-9b` is what a future block's rollback
must follow.

**Definition of done.** Three new tests green · **all four pre-existing
`test_nginx_config.py` tests green and unchanged** · every `B-08` test still green ·
**both `.conf` files byte-for-byte unmodified** (`git diff --stat docker/nginx/` is empty) ·
`limit_req_zone` keys untouched · the runbook section added to
`docs/ops/docker-deployment.md` naming steps 1–5 and stating that `deploy.yml` performs
none of them · `G-9a`…`G-9e` recorded with decisions and authors · the residual recorded
with owner and promotion trigger · **the commit body states plainly that no nginx
configuration was changed.** **Deferring the config edit is a success, not an omission** —
it is the only safe outcome given `G-9b`, and the block still ships a gate where none
existed.

---

## Recorded residual — `04-AUT-003`

**Disposition: the Python half is FIXED (`B-08`); the edge half is DEFERRED, not fixed, and
the deferral is owned and dated.** This must not be read as `04-AUT-003` closed.

**What `B-08` closed.** The spoof is closed **on the Python side**. A public peer sending
either header lands on the byte-identical key to sending no header. Blast radius of the
original defect was three rate-limit keys (login 10/60 s, deep-link 60/600 s,
search/autocomplete 30/60 s) plus `ConsentRecord.ip_address`.

**What remains at the edge.**

1. **`XFF[0]` is still attacker-controlled end to end** — 15 sites still append. **Currently
   harmless, and the reason is structural:** `X-Real-IP` is set at every proxied location and
   `get_client_ip` returns on it, so **`X-Forwarded-For` is never read in production**. This
   becomes live the moment any consumer reads `XFF[0]` naively — the exact defect `B-08`
   removed from three call sites.
2. **The peer gate is always open in production.** `REMOTE_ADDR` is nginx's private container
   IP and `TRUSTED_PROXY_NETWORKS` is `()`, so correctness rests entirely on nginx overwriting
   `X-Real-IP` correctly — one directive, in 15 places, in files this phase does not own.
   **Before `B-09`, nothing in the repository tested that.** Tests 1–2 (`G-9d`) now do.
3. **`REMOTE_ADDR` is never the true client IP in production.** Any future consumer reading
   `request.META["REMOTE_ADDR"]` directly gets nginx's IP. `B-08` routed `consent_record`
   through the helper; the trap for the next author remains.
4. **The private-peer residual `B-08` recorded** stands unchanged and accepted: a client
   reaching Django from a private/ULA/link-local address passes the gate, and a
   right-to-left walk reaching such an entry skips it and returns the attacker's leftmost
   prefix. Reachable only if a proxy omits `X-Real-IP`.
5. **The delivery gap itself (`G-9b`) is untouched** — four defects, none fixed by this block.
   This is the largest genuine residual and it is **not** a security finding.

**Owner.**

| Residual | Owner | Trigger to revisit |
|---|---|---|
| 1, 2 — the `X-Forwarded-For` / `X-Real-IP` edge directives | **phase 09** (owns both `.conf` files; BLOCKS 10–12 carry the `nginx -t` discipline) | either (a) `deploy.yml` gains `git -C /app pull` + `nginx -t` + `nginx -s reload` **and** the rollback includes `nginx`; or (b) the config is **baked into the image** instead of bind-mounted, so an image deploy carries it. Either converts this from "impossible to deliver" to "an ordinary change", at which point `$remote_addr` (`G-9c` a) becomes worth doing |
| 3 — `REMOTE_ADDR` misuse by future authors | **every author**, via `client_ip.py`'s docstring and `docker-deployment.md::Client IP Trust Model` | on any new request-derived identity consumer |
| 4 — the private-peer walk residual | **accepted by `B-08`**; revisit only if a proxy that omits `X-Real-IP` is ever fronted | topology change |
| 5 — the delivery/rollback gap | **phase 12 / ops** (owns `deploy.yml`, `rollback.md`) | independent of this finding |

**What a future change to the trust model must re-verify — the checklist `G-9d` partially
automates.** (a) nginx is **still the first hop** — a CDN or LB in front invalidates the
whole model and `set_real_ip_from` becomes *necessary* for the first time; (b) `proxy_set_header
X-Real-IP $remote_addr;` still present at **every** proxied location in **both** files (test 1);
(c) no `proxy_set_header` sourced from `$http_*` (test 2); (d) no wildcard `set_real_ip_from`
and no unpaired `real_ip_header` (test 3); (e) `web` still **unpublished** in production —
publishing it turns a public peer into the gate's input, which the gate refuses, so the
failure mode is per-peer buckets, i.e. **the safe direction**; (f) `TRUSTED_PROXY_NETWORKS`
still `()`.

**Consistency with `B-08`'s record — checked, and one correction made (`B-9c`).** `B-08`'s
Validator accepted the Python half **with the `real_ip` hazard recorded**; `I.10` pt 3 called
it the *single* nginx change that could silently invalidate the design. This block keeps the
hazard and **corrects the exclusivity**: the `X-Real-IP` directive is an equally load-bearing
vector and the one `G-9d` tests 1–2 actually guard. `B-08`'s conclusions are otherwise
**unchanged and not contradicted** — `G-8g`'s "`B-09` is optional hardening" is now
**confirmed as the final answer**, and `docker-deployment.md::Client IP Trust Model` needs
**no correction** because `$proxy_add_x_forwarded_for` genuinely is still in use.

---

## Implementor brief

```yaml
id: 04-b09-nginx-trust-model-gate
title: Pin the nginx client-IP trust-model invariant as an executable gate; defer the config edit
priority: high
depends_on: [04-b08-client-ip-helper (shipped), G-9a closed, G-9b closed, G-9c closed, G-9d closed, G-9e closed]
source_reference: .ai/plans/04-auth-login-remediation.md
source_section: BLOCK 7 — trusted proxy client IP (edge half)
source_blocks: ["BLOCK 7", "04-AUT-003"]
description: >
  DO NOT EDIT docker/nginx/nginx.conf OR docker/nginx/nginx.dev.conf. G-9a closed by
  non-claiming: this block takes no nginx configuration change, and both files must be
  byte-for-byte unmodified in the diff. Add three textual tests to
  src/backend/tests/test_nginx_config.py asserting the trust-model INVARIANT (not the current
  directive values), and add the G-9b operator runbook to docs/ops/docker-deployment.md.
goals:
  - "the three invariant tests are green over both .conf files"
  - "all four pre-existing test_nginx_config.py tests pass UNCHANGED"
  - "both nginx config files are untouched in the diff"
  - "a future edit that would silently invalidate B-08's peer gate turns a test red"
extra_context: >
  Read the whole B-09 section before starting. The binding facts are in "Verified starting
  state", the design rule (assert the invariant, never the current value) is in G-9d, and
  the four delivery traps are in G-9b.
files:
  - path: src/backend/tests/test_nginx_config.py
    targets:
      - type: function
        name: _location_block
        note: >
          MUST keep existing behaviour byte-for-byte — four pre-existing tests depend on it,
          including its "first matching line" semantics. Extract the shared brace-depth scan
          and have _location_block delegate to it; do not reimplement the depth logic twice.
      - type: function
        name: test_nginx_metrics_has_proxy_headers
        note: "MUST pass unchanged. Do not edit."
      - type: function
        name: test_proxied_locations_overwrite_x_real_ip
        action: add
      - type: function
        name: test_no_proxied_location_forwards_a_client_echo_variable
        action: add
      - type: function
        name: test_real_ip_trust_is_never_wildcard
        action: add
  - path: docs/ops/docker-deployment.md
    targets:
      - type: section
        name: "Nginx Configuration"
        note: >
          Add the G-9b operator runbook (5 numbered steps) at the end of the Nginx
          Configuration section, immediately after "Client IP Trust Model". Phase 01/02/08/09
          and phase 12 have all edited this file — RE-READ immediately before editing, run
          git status/git diff on it, and STOP AND REPORT on a concurrent change.
  - path: docker/nginx/nginx.conf
    note: "READ-ONLY. Must appear nowhere in the diff. Assert over it; never edit it."
  - path: docker/nginx/nginx.dev.conf
    note: "READ-ONLY. Must appear nowhere in the diff."
changes:
  - action: modify_test
    description: >
      Add three tests per G-9d, all textual (Path.read_text), pytest.mark.unit, no
      subprocess, no nginx binary, no docker, no new dependency. Run all three over BOTH
      docker/nginx/nginx.conf and docker/nginx/nginx.dev.conf (parameterise over the two
      paths). Test 2's $http_ scan must be restricted to proxy_set_header lines —
      log_format legitimately uses $http_x_forwarded_for and $http_user_agent, so a
      whole-file scan is red today.
  - action: modify_docs
    description: >
      Add the G-9b operator runbook: (1) git -C /app pull on the host, because deploy.yml
      never does it; (2) exec nginx nginx -t inside the container against the bind-mounted
      file; (3) exec nginx nginx -s reload, and state that `docker compose up -d` alone is
      NOT sufficient because the config is a :ro bind mount; (4) verify through nginx from
      outside, and state that the container-internal /health/ready/ check cannot see nginx;
      (5) rollback is entirely manual, because deploy.yml's rollback recreates only web bot.
acceptance_criteria:
  - "the three new tests pass"
  - "all four pre-existing tests in test_nginx_config.py pass UNCHANGED (byte-for-byte)"
  - "every B-08 test still passes, including apps/core/tests/test_client_ip.py"
  - "git diff --stat docker/nginx/ is EMPTY — both configs byte-for-byte unmodified"
  - "limit_req_zone still keys on $binary_remote_addr in both files"
  - "the runbook names all five steps and states that deploy.yml performs none of them"
  - "the commit body states plainly that NO nginx configuration was changed"
  - "no test asserts the X-Forwarded-For VALUE, and no test asserts the ABSENCE of set_real_ip_from"
  - "claiming nginx -t passed when it was not run is a failed block"
tests_to_run:
  - src/backend/tests/test_nginx_config.py
  - src/backend/apps/core/tests/test_client_ip.py
  - src/backend/apps/core/tests/test_contact_rate_limit.py
commands:
  - "docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml run --rm --env PYTEST_SKIP_MARKERS=seed test"
  - "uv run ruff check src/backend/tests/test_nginx_config.py"
  - "uv run basedpyright src/backend/tests/test_nginx_config.py"
  - "git diff --stat docker/nginx/   # MUST be empty"
traps:
  - "docker/nginx/nginx.conf and nginx.dev.conf are READ-ONLY in this block. Editing either fails the acceptance criteria — G-9a closed by non-claiming."
  - "_location_block matches the FIRST line containing its match string. Never introduce the literal '= /metrics' earlier in the file — not even in a comment — or all four pre-existing tests parse the wrong block."
  - "Do not edit the four existing tests, including test_nginx_metrics_has_proxy_headers. It asserts the directive NAME as a substring and never the value, so it is green today and must stay untouched."
  - "Test 2 must scan only proxy_set_header lines. log_format main uses $http_x_forwarded_for and $http_user_agent; a whole-file scan is red today."
  - "Do not assert the ABSENCE of set_real_ip_from and do not assert the X-Forwarded-For value — both pin a decision as an invariant (B-07's G-B mistake)."
  - "Do not add a limit_req_zone assertion — that is phase 09 BLOCK 10's surface."
  - "nginx.dev.conf has no '= /metrics', '/health/' or '/csp-report/' block. A = /metrics-anchored helper cannot reach it; the new tests must be location-agnostic."
  - "The config is a :ro bind mount, deploy.yml never git-pulls the host, up -d will not recreate an unchanged nginx, the deploy health gate bypasses nginx, and rollback recreates only web bot. None of this is fixed by this block; the runbook is the mitigation."
  - "Do not edit deploy.yml or docs/ops/rollback.md — phase 12 / ops surface. The gaps are recorded as residual."
  - "Keep the default -n 4 parallelism. Do not use --override-ini=addopts=."
  - "apps/search/tests/test_search_slo.py::test_search_at_seed_volume_meets_slo is a known non-regression (wall-clock SLO); it is skipped by the fast gate."
  - "Re-verify HEAD-sensitive facts at start; the working tree carries unrelated uncommitted edits to src/backend/config/settings/base.py and src/backend/config/settings/tests/test_session_policy.py. Do not touch or revert them."
```

---

### B-10 — Session lifetime policy (`04-AUT-006`) — **PLANNED 2026-10-02 · `G-10a`…`G-10i` ALL CLOSED**

| | |
|---|---|
| **Findings owned** | `04-AUT-006` (whole) · `04-VAL-002` (the `SESSION_*` half of the annotation, shared with `B-11`) |
| **Depends on** | `G-10a`…`G-10i` — **all CLOSED 2026-10-02 by this Planner** · `B-03` (**must never merge with it**: two commits, never one) |
| **Blocks** | `B-11` — hard, and the reason the two are not merged |
| **Priority** | P2 · **Risk LOW as shipped.** The plan recorded MEDIUM on the assumption that a global behaviour change might be chosen; `G-10b` chose the declaration, so the shipped diff is additive and inert. *The plan's risk band is superseded by this row, not by the Implementor.* |

**Objective.** Establish what the session lifetime **is**, make it **declared** rather
than inherited from a Django default, make the **refresh policy** declared too, and make
the specification say what the code does. **No behaviour change.** One product question —
*should the value be shorter?* — is recorded as owed and owned, not silently answered.

---

#### Verified starting state — re-verified at `259dcb4`, Django **5.2.17**

- **No `SESSION_COOKIE_AGE` and no `SESSION_SAVE_EVERY_REQUEST` anywhere in the tree.**
  Verified by a whole-`src/` search for `SESSION_COOKIE_AGE|SESSION_SAVE_EVERY_REQUEST|
  set_expiry|1209600` → **zero hits**. So Django's defaults apply: `SESSION_COOKIE_AGE =
  1209600` (14 days), `SESSION_SAVE_EVERY_REQUEST = False`,
  `SESSION_ENGINE = django.contrib.sessions.backends.db`,
  `SESSION_EXPIRE_AT_BROWSER_CLOSE = False`.
- `base.py` declares only `SESSION_COOKIE_SECURE`, `SESSION_COOKIE_HTTPONLY`,
  `SESSION_COOKIE_SAMESITE` and the `CSRF_COOKIE_*` triple, plus `CSRF_TRUSTED_ORIGINS`,
  `SECURE_SSL_REDIRECT = True`, `SECURE_PROXY_SSL_HEADER`, `USE_X_FORWARDED_HOST = True`,
  the HSTS triple, and — added by `B-03` — `LOGIN_BROWSER_ID_COOKIE_HOST_PREFIX = True`
  immediately after the `CSRF_COOKIE_SAMESITE` line. `LOGIN_URL = "/login/issue/"`.
  `CSRF_USE_SESSIONS` is **unset** (CSRF is a cookie). `AUTHENTICATION_BACKENDS` is
  absent from every settings module.
- **No number exists anywhere to implement.** A search of `docs/`, `src/`, the repo root
  and `.env*` for `14 day`, `14-day`, `двух недель`, `1209600`, `SESSION_COOKIE_AGE` and
  `SESSION_EXPIRE_AT_BROWSER_CLOSE` returns **zero hits outside plan and audit prose**.
  The only two hits in product documentation are `docs/99-agent/architecture.md`'s own
  record of the residual (*"the remainder of its 14-day life"* and *"unset, so the backend
  is the DB and the lifetime is Django's 14-day default"*) — **both already describe the
  inherited default, and both become accurate declarations once `B-10` ships.** No edit to
  `architecture.md` is needed.
- The **number is a product decision, not an engineering derivation.** `TOKEN_TTL_SECONDS
  = 300` is a **one-time handshake handoff token** and is **not** a session-lifetime
  precedent; using it as one is a category error. Recorded so the next editor does not
  make it.

---

#### The central correction — it is **write-triggered and population-dependent**, not "absolute" and not "sliding"

Both the source plan's `X-11` (*"sliding window"*) and the finding's own framing
(*"absolute"*) are **wrong as stated**. The mechanism, verified against installed Django
5.2.17 source:

- `django/contrib/sessions/middleware.py::SessionMiddleware.process_response` saves
  **only** when `(modified or settings.SESSION_SAVE_EVERY_REQUEST) and not empty`.
- `django/contrib/sessions/backends/db.py::SessionStore.create_model_instance` stamps
  `expire_date=self.get_expiry_date()`, and `backends/base.py::get_expiry_date` computes
  `modification + timedelta(seconds=get_expiry_age())`, where `get_expiry_age` returns
  `self.get_session_cookie_age()` (= `settings.SESSION_COOKIE_AGE`) **unless a
  `_session_expiry` key is present in the session dict**.

⇒ **`expire_date` is re-stamped on every session *write*, never on a read.**

**The complete production session-access inventory** (exhaustive whole-`src/` search for
`\.session\b` in non-test Python and templates — six hits, three of them reads):

| # | Site | Access | Writes the session? | Reachable by |
|---|---|---|---|---|
| 1 | `apps/users/views/consent.py::login_status` → `auth_login(request, user)` | Django's own login: `cycle_key()` (or `flush()`), then `_auth_user_id`, then `save()` | **YES — the one and only authenticated write** | the 300 s Telegram handshake |
| 2 | `apps/core/middleware/language.py::_apply_lang_param` | `request.session["django_language"] = resolved_code` | **YES**, but **only** when `?lang=` is present **and** `request.user.is_authenticated` | an authenticated user who clicks a language switch |
| 3 | `apps/search/views/search.py::search` → `record_search_history(..., session=request.session)` → `apps/search/services/search_history.py::_record_session_history` | `session["search_history"] = …` | **YES**, but **only** on the `user_id is None` branch | an **anonymous** visitor who submits a non-empty `?q=` |
| 4 | `apps/search/views/autocomplete.py` → `get_user_search_history(..., session=request.session)` | `session.get(...)` | no — a read | anyone |
| 5 | `apps/users/services/consent_record.py` | `request.session.session_key` | no — an attribute read, never a dict write, so `modified` stays `False` | anyone |
| 6 | `apps/core/middleware/preferred_city.py` | **a cookie**, not a session — this is the false lead a grep for "city" surfaces | no | anyone |

**The two halves, stated as the block must state them:**

- **Authenticated users — sellers and staff — are written exactly once, at login, and then
  never again** unless they use `?lang=`. Their lifetime is therefore **14 days absolute
  from login**, today, under the undeclared default. **The finding is factually correct
  for the population that matters**, and `04-AUT-006` is not refuted.
- **Anonymous visitors are refreshed by every recorded search**, and read-only browsing
  refreshes nothing.

**Consequence for the test design, and the reason this paragraph exists:** the plan's
single `test_session_lifetime_matches_the_declared_policy` would have exercised **only the
anonymous half** and passed without touching the population the finding is about. **Both
halves must be asserted** — see *Tests required*.

---

#### Plan corrections — three, all material

**`C-B10-1` — `X-11` is refuted as written; the source plan's option (c) is dropped, and
the re-specified (c) is what ships.** `docs/01-spec/technical-specification.md` § *H.
Telegram login behavior (US-S1)* reads: *"**Session:** persistent cookie, survives browser
restart until explicit logout or **long idle**."* That sentence is **inaccurate for the
authenticated population** — the session is 14 days from login regardless of activity,
which is neither "long idle" nor "absolute" in any sense the sentence conveys. The plan's
claim that *"the code implements a write-triggered sliding window"* is **false for
authenticated users** (they get one write), and the source plan's option (c) — *"correct
the spec to say 14 days of inactivity"* — would document a behaviour the code does not
have. **The honest edit states the number and the population split.** It ships: see `G-10e`.

**`C-B10-2` — the plan's risk line *"option (b) breaks every `force_login`-based test in
both suites"* is **not supported by the mechanism, and is withdrawn.** `Client.session`
returns a **live DB read** filtered by `expire_date__gt=now`, and `expire_date` is stamped
at `force_login`. A test asserting seconds later **cannot distinguish any age ≥ a few
seconds**, so no `force_login` test breaks under any design including (b)/(c) — and the
**169** `force_login` call sites in the tree were checked for what actually could break:
- **no test deletes a `django_session` row** and then reuses the same client's cookie
  within a request, so the one real mechanism under (b) — `SessionInterrupted`, raised
  when `session.save()` hits `UpdateError` because the row vanished mid-request — is not
  reachable. `SessionInterrupted` has **zero occurrences** in the tree.
- **no query-count assertion exists anywhere.** `assertNumQueries` and
  `django_assert_num_queries` have **zero** call sites (the only two matches in the
  repository are the *docstring* of `src/telegram_bot/tests/test_bot_query_count.py`,
  which states it deliberately does **not** use them). The extra write (b) introduces
  therefore cannot trip one.
- **no test asserts the 14-day default**, so nothing pins the defect as expected state and
  nothing needs rewriting. `B-07`'s six known-gap tests use `force_login` and assert
  session survival — cost **0** under every design.
- **The real cost of (b) is production write amplification, not tests.** Corrected.

**`C-B10-3` — the ingress arithmetic is **two different numbers**, and they were conflated.
Both are now separated, and the plan's `H.1` figure is **upheld for what it actually
measured** while the attribution in `B-10`'s framing is **corrected**.**

`login_issue` **never touches `request.session`** — it only calls
`response.set_cookie(...)` for the `login_browser_id` binding, which is a plain cookie.
Nothing on an anonymous `GET /login/issue/` marks the session modified, so
`process_response` skips `save()` and **zero** `django_session` rows are created **today**.
Two consequences, stated separately because conflating them is how the plan went wrong:

- **The plan's `~14,400 rows per IP per day` on `login_issue` is CORRECT and is UPHELD.**
  It is the cost of the **rejected `B-03` options `A″`/`B`**, which *would* have written a
  session row on that endpoint, bounded by
  `apps/users/services/login_rate_limit.py::RATE_LIMIT_REQUESTS = 10` /
  `RATE_LIMIT_PERIOD = 60` ⇒ 10 × 60 × 24 = **14,400/IP/day**, retained 14 days with no
  `clearsessions`. The `B-03` dominance argument in §H.1 therefore stands **unchanged** and
  is not affected by anything in this block. **This Planner's first pass at this correction
  wrongly impeached it; that is withdrawn.**
- **The number that describes `B-10`'s actual production vector is different and larger.**
  It is the **search path** (row 3 of the inventory above),
  `apps/search/views/search.py::search` → `record_search_history(..., session=request.session)`
  on the `user_id is None` branch, bounded by
  `apps/search/services/rate_limit.py::RATE_LIMIT_REQUESTS = 30` / `RATE_LIMIT_PERIOD = 60`
  per IP and only for a non-empty `?q=`. **Ceiling: 30 × 60 × 24 = 43,200 anonymous
  `django_session` rows per IP per day**, each retained for the full age ⇒ up to ~604,800
  rows resident per IP at steady state, from a client that refuses or loses cookies (ITP,
  enterprise policy, storage eviction) and therefore receives a **new session per request**.

**Why the separation matters, and it is not pedantry:** the two numbers sit on **different
endpoints, different rate limits, and different states of the world** — one is a cost that
*would* have been incurred, the other is a cost that **is** being incurred. Conflating them
is what allowed the plan to treat the janitor as a `login_issue` problem. It is a
**search-path** problem, and the rate limiter — not the session age — is what bounds it.
`G-10i` records the consequence.

---

#### Options — recorded, and the one chosen, stated

| Option | Mechanism | What it delivers | What it does **not** deliver | Verdict |
|---|---|---|---|---|
| **(a)** | declare `SESSION_COOKIE_AGE` (and `SESSION_SAVE_EVERY_REQUEST`) in `base.py` with a comment stating the write-triggered semantics | makes an inherited default **declared**; zero behaviour change; satisfies `04-VAL-002`'s own prescribed action (*"Set `SESSION_COOKIE_AGE` explicitly"*) | does **not** deliver the spec's "long idle", and does not shorten the window | **CHOSEN** — `G-10a` + `G-10b` |
| **(b)** | `SESSION_SAVE_EVERY_REQUEST = True` | nothing, for this population — see `G-10b` | **strictly *increases*** exposure for every actively-browsing authenticated user and delivers nothing to a sporadic one | **REJECTED** — `G-10b` |
| **(c)** | correct `technical-specification.md` §H to the number **and** the population split | closes the documentation half of the same SPEC-DEVIATION | — | **CHOSEN** — `G-10e`, second commit |
| **(d)** | record the premise as wrong and re-band, zero code | an honest floor | leaves the *undeclared* default in place, which is the actual defect | **REJECTED as the whole answer**, **adopted as the severity verdict** — `G-10a` |
| **(e)** *(new)* | env-driven `env.int("SESSION_COOKIE_AGE", …)` | an operator knob | an operator knob for a value with **no correct value derivable from the repository**, and an exception to the project's stated literal-constant rule | **REJECTED** — `G-10d` |

**Source plan's option (c) — *"correct the spec to say 14 days of inactivity"* — is
DROPPED and must not be reinstated.** It documents a behaviour the code does not have.

---

#### Gates — `G-10a` … `G-10i`, **all CLOSED 2026-10-02 by this Planner**

**`G-10a` — the lifetime value. CLOSED: declare the status quo `1209600` (14 days), and
record the *value* as an owed product decision with a named owner. Not (ii) 7 d, not (iii)
24 h.**

The declaration is the deliverable and is deliverable at any value. The **value** has no
engineering derivation — the tree-wide search returns nothing — so choosing 7 days or 24
hours would be **inventing a product requirement** in a code commit, on a finding
`04-VAL-002` classified **LOW / SPEC-DEVIATION / P2**, with three costs the shorter
options impose and no benefit that is demonstrable from the repository:

1. **Re-authentication is a Telegram round trip, not a password** (192-bit token, 300 s
   TTL, browser-bound). Every expiry sends a seller through the bot. The affected
   populations are **sellers** (~15 `@login_required` surfaces plus `consent_withdraw`,
   which is **irreversible self-erasure**) and **staff** (`/admin/`, `/moderation/**`,
   `ban_user`, the bulk API).
2. **A sporadic seller is not timed out by a 14-day window** — most never re-authenticate
   in a week, so a shorter age **creates** friction where none exists.
3. **Nothing durable is lost** (the Researcher's finding 2, verified): everything that
   matters is a DB row (`User.preferred_city`, `SearchHistory`, `ConsentRecord`,
   `AdFavorite`, `Ad` drafts swept at 30 min) or a long-lived cookie (`lang_pref` 365 d,
   `preferred_city` 1 y, the consent cookies). `CSRF_USE_SESSIONS` is unset.
   `B-03`'s `login_browser_id` cookie has **no `max_age`**, so it is a browser-session
   cookie **independent of `SESSION_COOKIE_AGE`**. There is no cart. The bot's FSM lives in
   `Ad` rows, not web sessions. The only session-stored item for an authenticated user is
   `django_language`, which is **redundant** with the 365-day `lang_pref` cookie. The one
   genuine cost is a seller mid-`ad_edit` losing unsubmitted form input — UX friction, not
   data loss.

**What (i) delivers:** the lifetime is declared with its refresh semantics; the drift the
finding names can no longer recur silently; the spec stops being wrong; the five tests
below make all of it machine-checked and **value-agnostic**.
**What (i) honestly does NOT deliver:** a shorter exposure window, and the spec's "long
idle". Both are stated below as owed, not answered.
**The product question is recorded, not buried:** *"should the seller/staff session
lifetime be shorter than 14 days, and if so what value?"* — owner **the coordinator /
product owner**, and it is **owed, not open** in the §H sense (nothing blocks `B-10` or
`B-11`). It is named in *Named known-gaps* below with the exact reason it is a product
call. **`04-AUT-006` is WEAKENED, not closed** — see *Honest bottom line*.

**`G-10b` — absolute or idle. CLOSED: option (i) — declare the age AND the refresh policy;
do not introduce an idle window.**

Declaring `SESSION_COOKIE_AGE` **only** is a **declaration, not a change**, because
authenticated sessions are *already* effectively absolute (one write, at login). The
decision is to declare **both** settings, because the finding names two absences — *"no
declared age, **no declared refresh policy**"* — and `SESSION_SAVE_EVERY_REQUEST = False`
is as much the reason a seller is never timed out as the number is. Declaring it makes
that machine-checked at zero cost.

**Option (ii) is rejected, and the reason is stronger than the plan's:** its stated
benefit — *"a stolen cookie's window becomes sliding"* — is **illusory for this
population**, and its effect is the **opposite** of a reduction:

- Today a seller who logs in once and posts an ad three weeks later **still has a
  session**, because nothing refreshes it. Under (ii) with the same 14-day age, that
  seller is **identical** — they are idle, so the window never moves. **Nothing is
  gained.**
- A seller who **keeps browsing** is *worse* off under (ii): today their session dies 14
  days after login; under (ii) every read-only response re-stamps it, so the window never
  closes while they are active. **Exposure is strictly increased for exactly the users who
  hold the longest-lived sessions.**
- The genuine anti-theft benefit of sliding — a stolen cookie that is never *used* aging
  out — is a function of the **age**, not of the flag. Delivering it requires a **shorter
  value**, which is `G-10a`'s product question, not a boolean.

Cost avoided: **+1 `UPDATE django_session` per response** carrying a non-empty session,
on the highest-traffic authenticated surfaces (`/dashboard/`, `/cabinet/`, `/admin/`,
`/moderation/**`), and the `SessionInterrupted` mechanism. Neither is fatal, and
`C-B10-2` shows neither breaks a test — but neither is worth paying for a change that
**increases** the exposure it claims to reduce.

**Option (iii) — a targeted `set_expiry` at one activity point — is rejected.** Verified:
**nothing in the tree calls `set_expiry`**, so `_session_expiry` is never set and
`get_expiry_age` always falls through to `get_session_cookie_age()`. Adding a
`set_expiry` call would (a) itself write `_session_expiry` **into the session dict**,
marking the session modified and therefore creating a write at that point — a new
behaviour to get right rather than a declaration; and (b) introduce a **per-session
override that silently diverges from the declared global policy**, which is the same class
of hidden state `04-VAL-002` objects to. It is also **redundant** with a declared
`SESSION_COOKIE_AGE` unless the value differs, which is `G-10a`'s question. If a future
editor wants an idle window, the correct shape is a **shorter declared age**, not an
override.

**`G-10c` — global flag or targeted `set_expiry`, *if* idle. CLOSED: NOT APPLICABLE.**
`G-10b` chose the declaration, so no idle window is introduced and there is no mechanism
to choose between. Recorded so the question is not reopened silently. The **one live
consequence** is promoted into the test list: because nothing calls `set_expiry` today,
test **5** pins that fact, so a future editor who adds a targeted override **trips a
test** instead of introducing an undeclared per-session policy.

**`G-10d` — literal or env-driven. CLOSED: LITERAL.**

Decided on the merits, and the merits are one-directional. The project's established
pattern for a bound with no derivable correct value is a **literal module constant**, and
every comparable constant in the tree is one — all verified live:

| Constant | Site | Form |
|---|---|---|
| `TOKEN_TTL_SECONDS` | `apps/users/services/login_token.py` | `Final[int] = 300` |
| `RATE_LIMIT_REQUESTS` / `RATE_LIMIT_PERIOD` | `apps/users/services/login_rate_limit.py` | `Final[int] = 10` / `60` |
| `RATE_LIMIT_REQUESTS` / `RATE_LIMIT_PERIOD` | `apps/search/services/rate_limit.py` | `Final[int] = 30` / `60` |
| `RATE_LIMIT_REQUESTS` / `RATE_LIMIT_PERIOD` | `apps/core/services/contact_rate_limit.py` | `Final[int] = 60` / `600` |
| `_MAX_HISTORY` | `apps/search/services/search_history.py` | `int = 50` |
| `DAILY_HOUR_UTC` | `apps/core/utils/scheduler.py` | `int = 8` |
| `LOCK_TIMEOUT_SECONDS` / `_MAX_LOCK_TIMEOUT_SECONDS` | `config/settings/base.py` | `int` |
| `SECURE_HSTS_SECONDS` | `config/settings/base.py` | `= 3600` |

`docs/02-database/db-retention.md` states the principle in the project's own words:
*"deliberately not an environment variable or a CLI argument: it is the number that bounds
the production lock hold, **so it must not be operator-variable**."* Env-driving the
session age would be the **exception** to that rule, and there is no `db-retention.md`
entry to make the exception legible.

The **gate** cost, for the record, because the plan overstated it in one direction and
understated it in another: `test_env_allowlist_reverse.py::test_consumed_env_vars_are_allowlisted`
asserts `consumed ⊆ ALLOWED_ENV_VARS`, so an env read **fails the fast gate** without an
allowlist entry; and `test_env_allowlist.py::test_example_keys_in_allowlist` asserts
`example keys ⊆ ALLOWED_ENV_VARS`, so a template entry needs the allowlist too. The
honest total for env-driving is therefore: **one `ALLOWED_ENV_VARS` line + up to four
`.env.*.example` edits, all in the same commit** — every one of them **outside `B-10`'s
stated file surface**, and `.env` templates are contended. **But the contention is not the
reason.** `D-6`/`E.4` already corrected the four template edits to *not* gate-binding, and
this Planner's choice rests on the precedent above plus the absence of a derivable correct
value. The `# env-contract:` opt-out is documented for *"not a deployment variable"* and
this **is** one, so using it would violate the contract in spirit — exactly the argument
`G-8c` accepted.
**Promotion path, named so it is not lost:** env-backing becomes defensible only when a
product owner supplies a value **and** states the deployment condition under which a
shorter one is correct (e.g. staff sessions vs seller sessions). It is not a mechanical
follow-up and must not be smuggled in as one.

**`G-10e` — the specification. CLOSED: EDIT §H, in this block, as a second commit — with a
recorded fallback.**

A decision that left `technical-specification.md` §H asserting *"long idle"* would leave
the **same** SPEC-DEVIATION in place after shipping, which is §F.1's dominant failure mode
(a finding left open behind a green suite) wearing a documentation costume. The
documentation half is not optional here; it is the other half of the defect.

**The contention is real but it is not a block, and phase 06's own plan says so.** Phase
06's `06-pii-consent-remediation.md` §5.1 reserves the file and then explicitly carves out
this block: *"**`technical-specification.md`** — phase 06 holds the reservation … All
serialise. **Phase 04 edits only under its BLOCK 8 option (c), and only after checking for
a concurrent edit**."* `PII-113` itself targets `spec-index.md` (BLOCK 2) and phase 06's
BLOCKS 4/11/14; the §H *Session* bullet is a different region of the file. §C.3 already
records the re-read rule.

**Conditions, all mandatory:**
1. The spec edit is a **separate commit** from the `base.py` declaration — never one
   commit. §E's governing rule ("a test change lands in the same commit as the production
   change it follows") is about *tests*; a documentation commit is cleaner and keeps the
   `git diff` for the code change auditable.
2. **Re-read the file immediately before editing** and `git status`/`git diff` it. **Stop
   and report on a concurrent change** — do not merge, do not regenerate, do not "help".
3. The commit body names the paragraph and the reason.
4. **No `.po` edit under any part of this block.** Verified: every shipped string is a
   Python/markdown literal, and no template is touched — so `makemessages` extracts
   nothing new and `test_i18n_completeness.py` cannot be affected. This is a **positive
   finding**: one fewer blocker than the plan assumed.

**Fallback, recorded so it cannot be silently dropped:** if a concurrent phase-06 edit is
present in the file, `B-10` ships the `base.py` declaration **alone**, and the spec edit is
recorded as a **named deferred obligation** in the commit body with the replacement text
written out, owned by the coordinator. The block is then complete **only** with that
obligation named — never quietly dropped, because nothing in the repository fails if it is
forgotten.

**`G-10f` — the session janitor. CLOSED: DECLINE `B-07`'s re-filing here. It stays where
`G-E` put it.** The Researcher's assessment is correct and is re-verified:

- The two are **independent controls**. `SESSION_COOKIE_AGE` decides when a *live* session
  dies; `SessionStore.clear_expired()` deletes only rows with `expire_date < now` (verified
  in `backends/db.py`), so **it cannot shorten a live session** and does nothing for
  `04-AUT-002` or `04-AUT-006`.
- The cost is **not** zero: `HOURLY_COMMANDS` **9 → 10** breaks the **exact-`==`**-pinned
  `apps/core/tests/test_scheduler.py::TestSchedulerConstants::test_hourly_commands_match_spec`
  — **a phase-owned file outside `B-10`'s surface** — and `docs/02-database/db-retention.md`
  would need a `django_session` row it does not have today.
- The upside is also not free to claim: `django.contrib.sessions` is already in
  `INSTALLED_APPS`, so `clearsessions` is discoverable via `get_commands()` with **no new
  command module, no `AdvisoryLockId` member and no migration** — which is why the
  hand-off must be recorded as a *decision to add it*, not as a build.

**Hand-off note, mandatory in the commit body (this is the part that is currently only in
the plan):** *"`clearsessions` is not registered. `HOURLY_COMMANDS` stays at exactly 9.
The janitor re-filed by `B-07` (`G-E`) exists **only in the execution plan** —
`docs/02-database/db-retention.md` has **no `django_session` row** today (verified: the
only three `session` matches in that file are `session-scoped` **advisory locks**). The
next editor of `db-retention.md` must add the row and the owner must register the command,
in one change, or the re-filing evaporates."*

**`G-10g` — sequence. CLOSED: `B-10` → `B-11`, serially. Do not merge.**

`B-11` explicitly declares `B-10` a hard dependency (*"annotates the **final** state, so it
runs last"*), and its output is only correct if `B-10`'s declaration exists — an
annotation pass that omitted the age would document an **incomplete** policy, which is
precisely the class of defect `04-AUT-006` is about. `B-11` is comments-only/LOW; `B-10` is
additive/MEDIUM-then-LOW. `B-03`'s `LOGIN_BROWSER_ID_COOKIE_HOST_PREFIX` is the working
precedent for the append-then-annotate handoff: `B-03` appended the setting with its
rationale comment, and the annotation block lands afterwards in the same region.

**The `base.py` rule for the Implementor, stated once and binding:** **`base.py` is
APPEND-ONLY across `B-02`, `B-03`, `B-08`, `B-10` and `B-11`.** Never reorder, never move,
never re-wrap a setting another block annotated. `B-10`'s two lines go **immediately after
`SESSION_COOKIE_SAMESITE`** — which is where `B-03` already appended
`LOGIN_BROWSER_ID_COOKIE_HOST_PREFIX`'s sibling, i.e. inside the existing
`# Security settings (TLS/SSL ready)` block, so no new heading is created and no existing
line moves. **Re-read the file immediately before editing; stop on a concurrent change.**
`B-11` annotates afterwards and does not move what `B-10` placed.

**`G-10h` — the test design. CLOSED: assert the SEMANTICS (write-triggered, both
populations), and assert the DECLARED VALUE without pinning 14 days.**

Three rules, each with a reason:

1. **Both halves, or the test is theatre.** The plan's
   `test_session_lifetime_matches_the_declared_policy` would exercise only the anonymous
   path and pass without ever touching an authenticated session — the population the
   finding is about. Tests **3** and **4** are the two halves and neither substitutes for
   the other.
2. **No test may pin 14 days as an expectation.** If `G-10a`'s product question is later
   answered "7 days", a test asserting `1209600` would go red and the implementor would be
   pushed to *edit the test to match the code* — which is the finding re-entering through
   the test suite. So: test **1** asserts the setting is **declared in the project's own
   `base.py` module** (a Django default is not an attribute of that module, so presence
   **is** the "declared, not inherited" assertion — the same shape as
   `test_settings_defaults.py::_THEME_STATICFILES_BACKEND`); test **2** proves the store
   honours **whatever** the declaration says, using `override_settings` with a small value
   so the assertion is number-independent. **The declared value is never hardcoded in a
   test.**
3. **The semantics are asserted, not the setting.** Tests 3 and 4 pin the write-triggered
   behaviour, which is the part that would silently change if someone later enabled
   `SESSION_SAVE_EVERY_REQUEST`. `C-B10-2`'s correction is what makes this possible: no
   `force_login` test can detect an age change, so the semantics must be asserted
   **directly**, through a real request cycle and the persisted `expire_date`.

**`G-10i` — why the janitor is still required. CLOSED: recorded, with corrected
arithmetic (`C-B10-3`).**

Even under the shortest defensible age, the anonymous row-creation vector is unaffected:
it is **pre-authentication** and bounded by a **rate limiter, not by the session age**. A
24-hour age would reduce the resident residue from ~14 days to ~1 day — a **proportional
reduction, not a substitute**, and one that requires no product decision to state.
Precisely: the search path creates up to **43,200 anonymous `django_session` rows per IP
per day** from a cookie-refusing client; a janitor is what reclaims them. **This is the
standing reason `B-07`'s re-filing survives `G-10f`, and it belongs in the commit body.**

**`G-10` — the umbrella gate. CLOSED by `G-10a`…`G-10i`.** The Implementor implements
exactly what those nine rows say and nothing else. If the Implementor believes one of them
is wrong, the correct action is to **stop and report**, not to re-open it.

---

**Out of scope — expanded, and every item is a boundary rather than a preference.**
`SESSION_ENGINE` — no change, no session-store migration, no `clearsessions` registration
(`G-10f`) · `SESSION_EXPIRE_AT_BROWSER_CLOSE` — the spec promises the cookie *"survives
browser restart"*, so it stays `False` and the age is the only lifetime knob ·
`SESSION_COOKIE_SECURE` / `HTTPONLY` / `SAMESITE` / `CSRF_*` — already closed, and
`_TRANSPORT_SETTINGS` stays at exactly **seven** members (`G-10d`: a **lifetime is not a
transport setting**, and adding an eighth member to a `==`-compared dev/test parity
contract is exactly the kind of well-meant widening that contract exists to prevent) ·
`SESSION_SAVE_EVERY_REQUEST` — **declared `False`, never enabled** (`G-10b`) · any
`set_expiry` call anywhere (`G-10c`) · any bot change · any migration · any management
command · merging with `B-03` (**two commits, never one**) · `ALLOWED_ENV_VARS`, `read_env()`
and the `.env.*.example` templates (`G-10d`) · `HOURLY_COMMANDS` / `DAILY_COMMANDS`
(`G-10f`) · `docs/02-database/db-retention.md` (the janitor's owner, not this block's) ·
`docs/99-agent/architecture.md` (**no edit needed** — its two 14-day statements already
describe the default and become accurate on landing) · `LOG_MASK_KEY` (phase 06) ·
any `.po` file (`G-10e` condition 4).

---

#### Tests required — **5 new in one new module · 0 changed · 0 deleted**

All five live in **one new module**, `src/backend/config/settings/tests/test_session_policy.py`.
The home is `config/settings/tests/` and not `apps/users/tests/` because two of the five
are *settings-declaration* tests and the block's production diff is a settings diff; that
directory is also where `B-06` put its two new modules, and `test_settings_defaults.py` is
**not** the right file for these (it owns the transport-tuple and staticfiles harnesses —
this is a different subject, and the plan's earlier suggestion to extend it was withdrawn).

| # | Test | Asserts | Why it exists |
|---|---|---|---|
| **1** | `test_session_lifetime_is_declared_in_base` | `config.settings.base` — **the project's own module** — has `SESSION_COOKIE_AGE` and `SESSION_SAVE_EVERY_REQUEST` as module attributes; the age is a positive `int`; `SESSION_SAVE_EVERY_REQUEST is False` | **The "declared, not inherited" assertion, and it is exact:** a Django default is not an attribute of `config.settings.base`, so *presence in that module* **is** the claim. This is the same shape as `test_settings_defaults.py::_THEME_STATICFILES_BACKEND` ("assert the resolved value, not the absence of the dead key, because absence passes on a build where the setting silently reverted to the default"). **The number itself is NOT asserted** — see `G-10h` rule 2 |
| **2** | `test_declared_age_bounds_a_real_sessions_expiry` | under `override_settings(SESSION_COOKIE_AGE=<small positive value>)`, a session created through a **real request cycle** has `expire_date` within a tolerance of `now + <small>`; and after the value has passed, `client.session` is empty | This is `04-VAL-002`'s **required** test gap (*"`settings.SESSION_COOKIE_AGE` value asserted; a session created after the change expires at the configured age"*) — satisfied **without** pinning 14 days, because the value under test is supplied by the test |
| **3** | `test_authenticated_session_is_written_once_at_login_and_never_refreshed` | **the authenticated half.** After an authenticated session exists, N **read-only** requests (no `?lang=`, no search, no consent write) leave the persisted `expire_date` **byte-identical** | **The half the plan's single test would have missed, and the half the finding is about.** It is the machine-checked form of *"a seller's session is 14 days from login, not from last activity"* — and it is the test that turns red if anyone later enables `SESSION_SAVE_EVERY_REQUEST` (`G-10b`) |
| **4** | `test_anonymous_session_is_refreshed_by_each_recorded_search` | **the anonymous half.** An anonymous visitor submitting a non-empty `?q=` gets a session whose `expire_date` is **strictly later** after a second recorded search than after the first | Proves the *other* half of the write-triggered semantics, and it is the only production path that refreshes an anonymous session. Without it, test 3's "never refreshed" reads as a general claim about all sessions, which is **false** |
| **5** | `test_no_per_session_expiry_override_exists` | (a) no `set_expiry(` call in any non-test `src/**/*.py`; (b) after a real authenticated request cycle the session dict contains **no** `_session_expiry` key | `G-10c`'s live consequence. It pins the fact that today `_session_expiry` is **never** set, so `get_expiry_age()` always falls through to the declared age. A future editor who adds a targeted `set_expiry` **trips this test** instead of silently introducing a per-session policy that diverges from the declared one. Same anti-vacuity discipline as `test_login_issue_template.py` and `test_handshake_ownership` |

**Explicitly NOT tests, and why — so an Implementor does not "helpfully" add them:**

| The plan's item | Disposition |
|---|---|
| `test_idle_window_ends_the_session` *(option (b) only)* | **Dropped** — no idle window is introduced (`G-10b`). There is nothing to test |
| `test_every_force_login_test_still_passes` | **Not a test; it is the fast gate.** Naming 169 `force_login` call sites as a "test" is not executable. The gate is the guard, and `C-B10-2` shows it cannot fail |
| `test_handshake_still_succeeds_under_the_new_lifetime` | **Kept, but as the existing suite, not a new test.** The 300 s `TOKEN_TTL_SECONDS` handshake is already covered end to end by `apps/users/tests/test_login_token.py::TestLoginHandshakeOwnership` and by `B-03`'s `test_same_browser_redeems_end_to_end`. Writing a second one is duplication, not coverage. **What the block must do instead:** name those tests in the commit body as the guard, and run them — a reviewer must be able to see that `B-03`'s handshake was re-verified, not assume it |
| "a session created after the change expires at the configured age" read as a literal 14-day wait | **Forbidden.** No test may sleep or wait 14 days, and no test may assert the literal `1209600` (`G-10h`) |

**Baseline.** `B-10` expects **0 changed and 0 deleted** tests. Re-derive before trusting
that number — the command is in the brief. **Named known non-regression:**
`apps/search/tests/test_search_slo.py::…::test_search_at_seed_volume_meets_slo` is a
wall-clock SLO test that fails under load and is **not this block's**.

---

#### Named known-gaps with owners — `B-10` ships with these open, and each is named

A known-gap that is not named here is §F.1's *"a partial block silently counted as
complete"* hazard. `B-07` shipped with **zero** production code and **five** named gap
tests; `B-10` ships **one** code change and these records.

| # | Known gap | Owner | Why it is not closed here |
|---|---|---|---|
| **1** | **The session age is 14 days and no product decision has ever been taken on it.** The finding's own classification is LOW/SPEC-DEVIATION and the *defect* was the undeclared state, which is now closed — but a 14-day unattended window on a `sessionid` remains | **Coordinator / product owner.** Owed, **not** open: nothing blocks `B-10` or `B-11` | The number is a product decision with **no engineering derivation** (`G-10a`). Recording it here rather than in a code comment is deliberate: a code comment cannot be tracked, assigned or closed |
| **2** | **A holder of the `sessionid` value has unattended access for the remainder of the age.** The cookie is **not** rotated after login, there is **no per-request account-state gate** (`B-07` proved a banned seller keeps a live session and **can relist**), and there is **no logout-all endpoint** | **Phase 15 `15-AUTHZ-001`** (the per-request gate) — owned there, recorded here | **`04-VAL-001`** forbids this phase shipping a per-request gate, and `B-07`'s `G-A` already ruled the alternative (a decode-scan revocation service) out. **A janitor would not help** — it cannot shorten a live session (`G-10f`). **The decisive framing: the 14 days is not the root cause of that HIGH residual; the missing per-request gate is.** Shortening the age would shrink the window without touching the structural defect — which is exactly why `G-10a` does not pretend to fix it |
| **3** | **`clearsessions` is not registered**, so expired session rows are never reclaimed | **`B-07`'s `G-E` re-filing** → phase 12 / `db-retention.md` | `G-10f`. The re-filing currently exists **only in the execution plan**; `db-retention.md` has no `django_session` row. The hand-off note is in the brief and in the commit-body requirement |
| **4** | **Anonymous session rows are created pre-authentication by the search path** — up to 43,200/IP/day from a cookie-refusing client, retained for the full age | Same as #3 | `G-10i`. It is a **rate-limiter**-bounded vector, not an age-bounded one, so no value of `SESSION_COOKIE_AGE` removes it. Recording it here is what keeps gap #3 from being deprioritised as "cosmetic cleanup" |
| **5** | **A seller mid-`ad_edit` at expiry loses unsubmitted form input** on re-authentication | Accepted; product | `G-10a` finding 2. UX friction, not data loss — everything durable is a DB row or a long-lived cookie. Accepted knowingly; it is the cost side of the balance that decided `G-10a` |

**`04-AUT-006` is WEAKENED, not closed. Not by this Planner — by the Validator, against
this block's corrected premise.** The recommended disposition, stated here so the Validator
acts on a record rather than re-deriving it:

> **`04-AUT-006` → WEAKENED.** The *declaration* half is **closed**: the age and the refresh
> policy are declared in `base.py` with the write-triggered semantics, and the specification
> states the number and the population split. The *value* half is **not closed** and was
> never a code defect — it is the undecided product question in known-gap #1. Severity
> **LOW / SPEC-DEVIATION / P2 stands**, re-worded: the finding as originally written said
> *"session lifetime falls back to the 14-day Django default"*, which is no longer true —
> the default is now **declared and documented**, and the residual is a deliberate,
> recorded 14-day policy plus the phase-15 per-request gate. **Do not close it as FIXED:**
> the exposure window is unchanged, and a green suite is not closure (§F.1).

**Gates.** `G-10` → **CLOSED** by `G-10a`…`G-10i` (all CLOSED 2026-10-02 by this Planner).

**Agents.** Implementor **yes** · Researcher **yes, COMPLETE** — `U-9` is answered: the
project's own documents state **no number anywhere**, which is a completed exhaustive
search, not an open question. Its six findings were re-verified against the live tree at
`259dcb4`; **three of them changed the plan** (`C-B10-1`, `C-B10-2`, `C-B10-3`) and two
were upheld (`G-10b`'s `SessionInterrupted`/query-count analysis, `G-10d`'s literal
precedent) · Planner **yes** (`G-10a`…`G-10i`, the phase-06 sequencing under `G-10e`, and
the `B-10`→`B-11` order) · Validator **yes** — **and its scope is narrow and stated**: the
re-banding of `04-AUT-006` recorded above, and confirmation that the five tests are not
vacuous. It is **not** asked to re-decide the age · Auditor **no** — **deviation,
justified, and unchanged from the plan:** `X-11` is verified live against
`technical-specification.md` §H, the absence of any number across `docs/`, `src/` and
`.env*` is a completed search, and what remains is a product decision, not an
architectural unknown.

**Risks — re-banded by `G-10b`.** The plan's list assumed a possible global behaviour
change; the shipped diff is additive and inert, so MEDIUM → **LOW**.

| # | Risk | Sev | Mitigation | Residual |
|---|---|---|---|---|
| 1 | A concurrent phase-06 edit to `technical-specification.md` is clobbered | **High** | `G-10e` conditions 1–3: separate commit, re-read immediately before editing, `git status`/`git diff` the file, **stop and report** on a concurrent change. `C.3`'s re-read rule | Low |
| 2 | A well-meaning implementor "improves" the policy by enabling `SESSION_SAVE_EVERY_REQUEST` | Med | `G-10b` states why it **increases** exposure; test 3 turns red; `SESSION_SAVE_EVERY_REQUEST is False` is pinned in test 1 | **None** |
| 3 | A test hardcodes `1209600`, so answering the product question later forces a test edit | Med | `G-10h` rule 2; test 2 supplies its own value via `override_settings`; **the declared value is never written in a test** | **None** |
| 4 | The commit documents a behaviour the code does not have (the source plan's option (c)) | **High** | Dropped by `C-B10-1`; `G-10e` requires the number **and** the population split | Low |
| 5 | `base.py` conflict with a concurrent block | Med | `G-10g`'s append-only rule; the two lines go immediately after `SESSION_COOKIE_SAMESITE`; re-read before editing | Low |
| 6 | A finding recorded as fixed while the exposure window is unchanged | **High** | The disposition above is **WEAKENED, not closed**, with the reasoning stated; §G.2's exit condition requires it | Low |
| 7 | The janitor re-filing evaporates because it lives only in this plan | Med | `G-10f`'s hand-off note is a **mandatory commit-body line**; known-gap #3 names the owner | Med — nothing in the repository fails if it is forgotten |
| 8 | Test 3 or 4 passes for the wrong reason | Med | Both must read the **persisted `expire_date`** from a real request cycle, not a session-dict value in memory; test 4 requires a **non-empty** `?q=` (an empty query is a documented no-op in `record_search_history`, and would make the test vacuous) | Low |

**Rollback.** Delete the two declared lines from `base.py` (option (a)); revert the spec
commit (option (c)). **Two commits, two independent rollbacks.** No migration, no data
change, no state to unwind — the declaration is inert, which is the point. Rollback
restores the *undeclared* default, so it is a step backwards against the finding and is
recorded as such.

**Definition of done.** Tests **1–5** green in the one new module · tests 2 and 3 execute
real request cycles and read the **persisted** `expire_date` · the two settings are
**declared** in `base.py` inside the existing `# Security settings (TLS/SSL ready)` block
with a comment stating the write-triggered semantics and the population split · **zero**
existing test files modified · the fast gate green · `ruff` and `basedpyright` clean on
every changed Python path · the spec commit landed on a freshly re-read file with `git
status` showing no phase-06 content clobbered (**or** the deferred obligation named with
its replacement text) · the **mandatory commit-body lines** present: the `clearsessions`
hand-off note, the `G-10i` ingress arithmetic, and the *"no behaviour change"* statement ·
`G-10a`…`G-10i` recorded with decisions and author.

**Implementor brief.** `G-10a`…`G-10i` are **closed**. Implement exactly what they say.
**There is nothing to decide.**

```yaml
id: 04-b10-session-lifetime
title: Declare the session lifetime and its refresh policy, and correct the spec
priority: low            # plan said medium; G-10b made the shipped diff inert (MEDIUM -> LOW)
risk: low
depends_on: [04-b03-login-token-browser-binding]   # B-03 must have landed. Never one commit with it.
source_reference: .ai/plans/04-auth-login-remediation.md
source_section: BLOCK 8 — session lifetime policy
source_blocks: ["BLOCK 8", "04-AUT-006"]
description: >
  Declare SESSION_COOKIE_AGE and SESSION_SAVE_EVERY_REQUEST literally in
  config/settings/base.py, with a comment stating the write-triggered refresh semantics and
  the population split (authenticated sessions are written once, at login; anonymous
  sessions are refreshed by each recorded search). Then correct the Session paragraph of
  docs/01-spec/technical-specification.md section H in a separate commit. No behaviour
  change. No idle window. No janitor. No env variable.

goals:
  - "the session lifetime is DECLARED, not inherited from a Django default (G-10a, G-10d)"
  - "the refresh policy is declared too, and the two halves of the population are documented (G-10b)"
  - "the specification states the number and the write-triggered semantics, and no longer says 'long idle' (G-10e)"
  - "the 300-second login handshake still completes end to end"
  - "zero existing tests are modified"

# ── The binding decision, stated once so it is never re-litigated in the diff ──
behaviour_change: none.  # SESSION_COOKIE_AGE is set to Django's own default value (1209600),
                         # and SESSION_SAVE_EVERY_REQUEST to Django's own default (False).
                         # The commit body MUST say "no behaviour change" verbatim. If you
                         # find yourself changing a value, you are implementing a decision
                         # that was refused by G-10b — stop and report instead.

extra_context: |
  All binding constraints are in the prose above. The five that will cost you if you skip
  them:

  1. WRITE-TRIGGERED, NOT SLIDING. expire_date is re-stamped only on a session WRITE
     (SessionMiddleware.process_response saves when `modified or SESSION_SAVE_EVERY_REQUEST
     and not empty`; db.SessionStore.create_model_instance stamps get_expiry_date()).
     Authenticated sessions have exactly one write — auth_login in login_status — so a
     seller's session is 14 days ABSOLUTE from login. Anonymous sessions are refreshed by
     every recorded search. Both halves must be asserted (tests 3 and 4).
  2. THE DECLARED NUMBER IS NEVER HARD-CODED IN A TEST. Test 1 asserts the setting is
     declared in config.settings.base (a Django default is not an attribute of that
     module, so presence IS the claim). Test 2 supplies its own value via
     override_settings. Nothing asserts 1209600, so answering the product question later
     changes base.py only and no test goes red.
  3. base.py IS APPEND-ONLY and SHARED (B-02, B-03, B-08, B-10, B-11). Never reorder, move
     or re-wrap a setting another block annotated. Your two lines go immediately after
     SESSION_COOKIE_SAMESITE, inside the existing `# Security settings (TLS/SSL ready)`
     block. Re-read the file immediately before editing; STOP on a concurrent change.
  4. NO .po FILE, EVER. Nothing user-visible is added, so `makemessages` extracts nothing
     and test_i18n_completeness.py cannot be affected. If you find yourself opening a .po,
     you have added a translatable string by accident — stop.
  5. TWO COMMITS, NEVER ONE. Commit 1 = base.py + the new test module (production and its
     tests together, per §E's governing rule). Commit 2 = the spec paragraph.

files:
  - path: src/backend/config/settings/base.py
    targets:
      - type: setting
        name: SESSION_COOKIE_SAMESITE
        note: >
          ANCHOR, DO NOT MODIFY. The two new declarations go immediately after this line,
          inside the existing "# Security settings (TLS/SSL ready)" block. This is the same
          region B-03 appended LOGIN_BROWSER_ID_COOKIE_HOST_PREFIX to, so no new heading is
          created and no existing line moves.
      - type: comment
        name: "the '# Security settings (TLS/SSL ready)' heading"
        note: "reference only - do not move, do not re-word"
      - type: setting
        name: SESSION_COOKIE_SECURE
        note: "reference only - do not change"
      - type: setting
        name: SESSION_COOKIE_HTTPONLY
        note: "reference only - do not change"
      - type: setting
        name: LOGIN_BROWSER_ID_COOKIE_HOST_PREFIX
        note: >
          reference only - B-03's line, with its 17-line rationale comment. Do not move it,
          do not shorten its comment, do not re-wrap it.
      - type: setting
        name: _TRANSPORT_SETTINGS
        note: >
          NOT IN base.py — it lives in
          src/backend/config/settings/tests/test_settings_defaults.py and has exactly SEVEN
          members. DO NOT add an eighth. A session LIFETIME is not a transport setting;
          _TRANSPORT_SETTINGS is a ==-compared dev/test parity contract over TLS controls.
    changes:
      - action: add_code
        target: SESSION_COOKIE_SAMESITE
        insert: after
        description: >
          Add two literal declarations plus one comment block. The comment must state, in
          prose: the value in days AND seconds; that the expiry is stamped on every session
          WRITE and never on a read; that an authenticated session has exactly one write
          (at login), so its lifetime is absolute from login; that an anonymous session is
          refreshed by each recorded search; that SESSION_SAVE_EVERY_REQUEST is False
          deliberately and why enabling it would extend the window for active users; and
          that the value is a literal, not env-driven, per the db-retention.md principle.
          Cite `04-AUT-006` with the cycle-scoped form. The comment half is `B-11`'s to
          ANNOTATE afterwards — it must not be skipped and must not be duplicated here.
        code_hint: |
          # Session lifetime (04-AUT-006). 1209600 s = 14 days, declared explicitly:
          # Django's default was in force and undocumented, so the policy was inherited
          # rather than stated. The expiry is stamped on every session WRITE and never on
          # a read — an authenticated session has exactly one write (auth_login), so a
          # seller's or moderator's session is 14 days ABSOLUTE from login, not from last
          # activity; an anonymous session is refreshed by each recorded search.
          # SESSION_SAVE_EVERY_REQUEST stays False on purpose: a sliding window would
          # extend the exposure of exactly the users who hold the longest-lived sessions
          # and would change nothing for a sporadic seller. A literal, not an env var: no
          # correct value is derivable from the repository (docs/02-database/db-retention.md).
          SESSION_COOKIE_AGE = 1209600
          SESSION_SAVE_EVERY_REQUEST = False

  - path: src/backend/config/settings/tests/test_session_policy.py
    note: >
      NEW module. This directory, not apps/users/tests/ — two of the five tests are
      settings-declaration tests and the production diff is a settings diff. Do NOT extend
      test_settings_defaults.py: it owns the transport-tuple and staticfiles harnesses.
    changes:
      - action: add_code
        description: >
          Exactly five tests, no more. Each must be non-vacuous.
          1. test_session_lifetime_is_declared_in_base — getattr on
             config.settings.base for SESSION_COOKIE_AGE (positive int) and
             SESSION_SAVE_EVERY_REQUEST (is False). Presence in that module is the
             "declared, not inherited" claim. DO NOT assert the literal 1209600.
          2. test_declared_age_bounds_a_real_sessions_expiry — under
             override_settings(SESSION_COOKIE_AGE=<small positive int>), a session created
             by a REAL request through the test client has a persisted expire_date within
             a small tolerance of now + that value; and once the value has passed,
             client.session is empty. Number-independent by construction.
          3. test_authenticated_session_is_written_once_at_login_and_never_refreshed — the
             AUTHENTICATED half. Establish an authenticated session, read the PERSISTED
             django_session.expire_date, issue N read-only requests (no ?lang=, no search,
             no consent write), re-read expire_date, assert it is unchanged. Read the row
             from the DB, not a session-dict value in memory.
          4. test_anonymous_session_is_refreshed_by_each_recorded_search — the ANONYMOUS
             half. An anonymous client submitting a NON-EMPTY ?q= gets a session; a second
             recorded search yields a strictly later expire_date. A non-empty query is
             mandatory: record_search_history returns early on an empty/whitespace query,
             which would make the test pass vacuously.
          5. test_no_per_session_expiry_override_exists — (a) no `set_expiry(` call in any
             non-test src/**/*.py; (b) after a real authenticated request cycle the session
             dict has no `_session_expiry` key. Pins the fact that nothing calls set_expiry
             today, so a future per-session override trips a test instead of silently
             diverging from the declared policy.
        code_hint: |
          # The write-triggered semantics are asserted through the PERSISTED row, because
          # a session read back from the store is already filtered by expire_date__gt=now
          # and therefore cannot distinguish one age from another (04-AUT-006 / C-B10-2).
          from django.contrib.sessions.models import Session

          def _expire_date(session_key: str):
              return Session.objects.get(session_key=session_key).expire_date

  - path: docs/01-spec/technical-specification.md
    note: >
      SECOND COMMIT ONLY. Phase 06 reserves this file but explicitly carves this block out
      (06-pii-consent-remediation.md §5.1: "Phase 04 edits only under its BLOCK 8 option
      (c), and only after checking for a concurrent edit"). Re-read the file immediately
      before editing; `git status --short` and `git diff` it; STOP AND REPORT on a
      concurrent change rather than merging or regenerating.
    targets:
      - type: section
        name: "H. Telegram login behavior (US-S1)"
      - type: list_item
        name: 'the bullet beginning "**Session:** persistent cookie, survives browser restart until explicit logout or long idle."'
    changes:
      - action: modify_doc
        description: >
          Replace that ONE bullet. It is currently false for the authenticated population —
          "long idle" promises an idle timeout the code does not implement. The replacement
          must state: the value (14 days / 1209600 s); that it is stamped at login and is
          therefore absolute from login, not from last activity; that an anonymous session
          is refreshed by each recorded search; and that the cookie survives browser
          restart. Do NOT write "14 days of inactivity" — the code does not do that
          (C-B10-1). Do not restructure the section, do not renumber, do not touch any other
          paragraph. No .po edit: this is English markdown, not a translatable string.

changes_summary: |
  2 files in commit 1 (base.py + one new test module), 1 file in commit 2 (the spec
  paragraph). Zero existing tests modified. Zero migrations. Zero management commands.
  Zero scheduler entries. Zero env vars. Zero .po edits. No bot change.
  src/telegram_bot/ must stay byte-unchanged (`git diff --stat -- src/telegram_bot` empty).

acceptance_criteria:
  - "only the recorded G-10a/G-10b/G-10d/G-10e decisions were implemented; nothing else"
  - "SESSION_COOKIE_AGE and SESSION_SAVE_EVERY_REQUEST are declared in base.py immediately after SESSION_COOKIE_SAMESITE, with a comment stating the write-triggered semantics and the population split"
  - "the comment cites 04-AUT-006 in cycle-scoped form, never a bare AUT-006"
  - "exactly five new tests, in one new module, all green; zero existing test files modified"
  - "tests 3 and 4 both present — an authenticated-half assertion and an anonymous-half assertion. A submission with only one of them is INCOMPLETE"
  - "no test hardcodes 1209600 or any literal session age"
  - "tests 2 and 3 assert through a real request cycle and read the PERSISTED django_session row"
  - "the 300-second login handshake still completes end to end (apps/users/tests/test_login_token.py::TestLoginHandshakeOwnership and B-03's test_same_browser_redeems_end_to_end re-run and named in the commit body)"
  - "git diff shows no movement of any pre-existing line in base.py — additions only, inside the existing security-settings block"
  - "_TRANSPORT_SETTINGS still has exactly SEVEN members and test_settings_defaults.py is byte-unchanged"
  - "HOURLY_COMMANDS still exactly 9; apps/core/tests/test_scheduler.py byte-unchanged; clearsessions NOT registered"
  - "docs/02-database/db-retention.md byte-unchanged; it has no django_session row and adding one is NOT this block's job"
  - "ALLOWED_ENV_VARS, read_env() and the secret guards byte-unchanged; no .env.*.example edited; test_env_allowlist_reverse.py and test_env_allowlist.py green"
  - "MIDDLEWARE byte-unchanged at 15 entries, DbLockTimeoutMiddleware at position 6"
  - "SESSION_ENGINE, SESSION_EXPIRE_AT_BROWSER_CLOSE, SESSION_COOKIE_SECURE/HTTPONLY/SAMESITE and every CSRF_* setting byte-unchanged"
  - "src/telegram_bot/ byte-unchanged; no migration generated; no management command added"
  - "no .po file touched; no template touched; djlint not required"
  - "the spec edit is its own commit, landed on a freshly re-read file, with git status showing no phase-06 content clobbered — OR the deferred obligation is named in the commit body with its replacement text"
  - "commit body states verbatim: 'no behaviour change'"
  - "commit body carries the G-10f hand-off note (clearsessions not registered; the re-filing exists only in the plan; db-retention.md has no django_session row)"
  - "commit body carries the G-10i arithmetic (up to 43,200 anonymous django_session rows per IP per day, created by the SEARCH path — not by /login/issue/, which creates none) and why the janitor is still required"
  - "the Validator has the re-banding text for 04-AUT-006: WEAKENED, not closed"

commands:
  - "Re-verify HEAD-sensitive facts before starting: git log --oneline -1"
  - "Re-derive the no-existing-test-modified claim (expect zero hits):"
  - >-
      Select-String -Path src/backend/config/settings/tests/*.py,
                           src/backend/apps/users/tests/*.py,
                           src/backend/apps/core/tests/*.py,
                           src/backend/apps/search/tests/*.py
                   -Pattern 'SESSION_COOKIE_AGE|SESSION_SAVE_EVERY_REQUEST|set_expiry'
  - "Confirm base.py is unchanged since you read it, immediately before editing:"
  - "git diff --stat -- src/backend/config/settings/base.py"
  - "Confirm the bot package stays byte-unchanged:"
  - "git diff --stat -- src/telegram_bot"
  - "Lint and typecheck:"
  - "uv run ruff check src/backend/config/settings/base.py src/backend/config/settings/tests/test_session_policy.py"
  - "uv run basedpyright src/backend/config/settings/base.py src/backend/config/settings/tests/test_session_policy.py"
  - "Targeted tests (note: setting PYTEST_OPTS REPLACES the defaults, so this loses --reuse-db and xdist):"
  - '$dc run --rm -e PYTEST_OPTS="src/backend/config/settings/tests/test_session_policy.py --tb=short" test'
  - "Then the FULL fast gate — this is the real regression gate:"
  - "$dc run --rm --env PYTEST_SKIP_MARKERS=seed test"
  - "After any test-DB restart, the mandatory form:"
  - '$dc run --rm -e PYTEST_OPTS="--create-db --tb=short -n auto --maxprocesses=4 --dist loadgroup" test'

traps:
  - "NEVER launch a second gate while one is running. The test DB is shared and there is no single-writer gate; two concurrent runs collide. Check before every run."
  - "Keep the default -n 4 on the fast gate. Do not serialise it 'to be safe' — a shared test DB with xdist is the established configuration."
  - "apps/search/tests/test_search_slo.py::…::test_search_at_seed_volume_meets_slo is a KNOWN wall-clock non-regression that fails under load. Not this block's. Do not chase it and do not 'fix' it."
  - "_TRANSPORT_SETTINGS has exactly SEVEN members. A session lifetime is not a transport setting. Adding an eighth breaks test_dev_and_test_share_the_transport_tuple and its own docstring."
  - "apps/core/tests/test_scheduler.py is NOT yours. It exact-==-pins HOURLY_COMMANDS at 9. Registering clearsessions breaks it in a phase-owned file outside this block's surface (G-10f)."
  - "test_env_allowlist_reverse.py fails any new env-var-backed setting. G-10d chose a literal precisely so this stays green and so no .env.*.example edit is needed."
  - "Never `git add -A`, `git add .`, `git add -A .`, `git checkout`, `git restore`, `git stash` or `git reset`. Stage per file with `git add <path>`. The working tree contains another agent's work: 19 tracked .ai/audit/** files show as deleted and several .ai/plans/*.md are modified. None of it is yours."
  - "Do not touch .ai/audit/** and do not edit .ai/plans/04-auth-login-remediation.md."
  - "No print(), no bare except, no new dependency."
  - "English only. Comments, docstrings, commit message."
  - "Do not add a .po edit, a gettext call, a {% trans %}, or any user-visible string."
  - "Do not let B-11's annotation land in this commit. B-10 declares; B-11 annotates. Merging them breaks the append-then-annotate handoff B-03 established."
  - "If a test goes red and the error names a symbol you did not touch, re-run before believing it: the known DeadlockDetected / unique-key shard collisions are test-DB flakes. A full gate reporting '3 failed, 1944 passed, 651 errors' dominated by post_migrate duplicate-key is the stale-shard artefact, not a regression."

known_gaps_shipped:
  - "04-AUT-006 value half — 14 days, never a product decision. Owner: coordinator / product owner. OWED, not open: nothing blocks this block or B-11."
  - "04-AUT-006 HIGH residual — no per-request account-state gate, so a holder of the sessionid value has unattended access and a banned seller can relist. Owner: phase 15 15-AUTHZ-001. A janitor would NOT help; it cannot shorten a live session."
  - "clearsessions not registered. Owner: B-07's G-E re-filing -> phase 12 / db-retention.md."
  - "Anonymous session rows created pre-auth by the search path, up to 43,200/IP/day, retained for the full age. Owner: same as the janitor. This is rate-limiter-bounded, not age-bounded — no value of SESSION_COOKIE_AGE removes it."
  - "A seller mid-ad_edit at expiry loses unsubmitted form input. Accepted knowingly; UX friction, not data loss."

validation_notes: >
  A green suite is NOT closure (§F.1). Report what the block changed, what it deliberately
  did not change, and hand the disposition text above to the Validator. Do not describe
  04-AUT-006 as fixed.
```

---

#### Honest bottom line — what `B-10` delivers and what it leaves

**Delivers.** The session lifetime is **declared** rather than inherited, and so is the
refresh policy that actually governs it. The specification stops claiming an idle timeout
the code never implemented. Five tests make all of it machine-checked **without pinning a
number**, so the policy can be changed later by editing one line in `base.py`. The drift
the finding names — a lifetime nobody stated, in a codebase where every comparable bound
*is* stated — can no longer recur silently.

**Leaves, deliberately and by name.** The window is still 14 days, because no one has ever
decided what it should be and the tree contains nothing from which to decide it. The
HIGH residual — an unrevocable `sessionid` with no per-request account-state gate and no
logout-all — is **not** this block's to fix and is **not** shortened by anything shipped
here. `clearsessions` is still unregistered, so the anonymous rows the search path creates
keep accumulating for the full age. The spec edit can be lost to a phase-06 conflict, in
which case the obligation is named rather than done.

**Verdict on the finding: WEAKENED, not closed, and the Validator owns the re-banding.**
The declaration half is closed. The value half was never a code defect — it is an undecided
product question, recorded as known-gap #1 with an owner. The severity `04-VAL-002`
assigned — **LOW / SPEC-DEVIATION / P2** — **stands**, re-worded: the finding's premise
(*"falls back to the 14-day Django default"*) is no longer true, and the residual is a
deliberate, documented 14-day policy plus phase 15's missing gate. **Do not close it as
FIXED.** §F.2 row 7 (*"the premise is inverted and the plan documents a behaviour the code
does not have"*) is discharged by `C-B10-1`: the source plan's option (c) is dropped and
the honest edit ships instead.

---

### B-11 — Auth/session settings annotation (`04-VAL-002`, comment half) — one file only

| | |
|---|---|
| **Findings owned** | `04-VAL-002` (comment half + tracker half) |
| **Depends on** | `B-02`, `B-08`, `B-10` — it annotates the **final** state, so it is last |
| **Blocks** | nothing |
| **Priority** | P2 · **Risk LOW** |

**Objective.** Annotate the auth/session settings this phase changed with an accurate
record of the final state, and produce the tracker-key decision record. **Nothing else.**

**The audit-id sweep is REMOVED from this phase — it is not this phase's to run.**
`.ai/plans/03-db-concurrency-remediation.md` §5.2 item 3, under the heading *"The convention
phases 04–15 must adopt (decided — `Q14`, first half)"*, states: *"**Phases 04–15 must not
start BLOCK 11-style legacy sweeps of their own.** One sweep, in BLOCK 11, under the
coordinator's chosen option — otherwise twelve phases rewrite the same 26 files differently
and the convention is unenforceable."* Item 2 of the same list: *"A bare `DB-00N` /
`CFG-00N` in a comment or docstring is unresolvable and must not be written by a new
phase. New cross-references use the cycle-scoped form."* Phase 09's plan records the same
reservation independently. **The source plan's BLOCK 9 comment sweep is therefore
forbidden.**

Two further facts make the removal correct rather than merely permitted:

- **The sweep's rationale was false.** `X-8`: none of the 15 `AUT-00N` references points
  at code phase 01 moved. The only two that concern phase 04 at all — `login_token.py`'s
  docstring and `docs/99-agent/architecture.md`'s boundary paragraph — are the pair the
  source plan says must **not** be touched, and `B-04` rewrites them because their
  content becomes **false**, which is a correctness fix, not a sweep.
- **`U-10`: naive qualification produces nine factually wrong references.** Of the 15
  references, nine carry **other phases'** IDs (`AUT-001` ×3 for FSM backfill and template
  UX, `AUT-002` for the already-closed withdraw flush, `AUT-003` ×3 for middleware
  registration, `AUT-009` ×2). `04-VAL-002` demands phase-qualified keys; qualifying
  those nine would attribute another cycle's work to this one, and would touch bot and
  template files this phase has no claim on. **The only comments this phase may
  phase-qualify are its own two `AUT-007` references — and those belong to `B-04`.**

**What remains in scope — exactly two items.**

1. **An annotated `SESSION_*` / `AUTH_*` policy block in `config/settings/base.py`** — one
   comment per setting stating what it is and why it is or is not configured, placed
   adjacent to the existing `# Security settings (TLS/SSL ready)` block. This includes the
   settings `B-02` (`AUTH_PASSWORD_VALIDATORS`), `B-08` (the trusted-proxy setting) and
   `B-10` (`SESSION_COOKIE_AGE`) introduced — **so this block runs last, after they land.**
2. **The `04-VAL-002` tracker half as a decision record.** Phase 04 introduces **no** new
   bare `AUT-00N` references. Every new cross-reference uses the cycle-scoped `NN-<PREFIX>-00N`
   form. The phase-qualified keys the source plan §8.1 asks for are a **process
   deliverable** — recorded here, no code.

**Out of scope.** Every file outside `config/settings/base.py` · the 15 `AUT-00N`
references (`X-6`, `X-7`) · `apps/moderation/admin_actions.py`,
`apps/users/admin.py` and `apps/core/tests/test_admin_pii_containment.py` — **none of the
three contains any `AUT-00N` reference** (`X-7`), so the source plan's declaration that
they do is simply wrong · `telegram_bot/**` and template files · `ALLOWED_ENV_VARS`,
`read_env()`, the secret guards and `LOCK_TIMEOUT_SECONDS` (phase 02) · `LOG_MASK_KEY`
(phase 06).

**Tests required.** **The full fast gate.** A comment-only diff that fails any test means
something executable changed — that is the entire guard. Plus `ruff` and `basedpyright`
clean on `config/settings/base.py`, and `test_settings_defaults.py`,
`test_env_allowlist_reverse.py` and `test_env_allowlist.py` green (this block sits in the
file those three read).

**Gates.** `G-11` — closed by the boundary, not by a decision: **no sweep, no
qualification.** Recorded here so the implementor does not "helpfully" restore one.

**Agents.** Implementor **yes** · Planner **yes** — **deviation from the source plan,
justified:** the source plan assigned Implementor only because it assumed the block carried
mechanical comment edits. After the re-scope the block carries a **decision**
(`G-11`: whether any phase-04 comment may be phase-qualified), whose failure mode is nine
factually wrong references across bot and template files this phase has no claim on. A
Planner is required for that decision and for the §D item 14 reservation itself ·
Auditor **no**, Researcher **no**, Validator **no** — **deviation, justified:** the block
changes no behaviour, its file surface is one settings module, and the guard is the fast
gate itself.

**Risks.** A comment-only diff that quietly reorders a setting another phase annotated
(mitigated: append-only, §C) · an annotation that is wrong by the time the next block
lands (mitigated: this block runs last) · a well-meaning implementor restoring the sweep
(mitigated: stated as a reservation in the brief).

**Rollback.** Revert the comment block. Nothing executable.

**Definition of done.** Fast gate green · `git diff --stat` shows **one** file changed
(`config/settings/base.py`) · `ALLOWED_ENV_VARS`, `read_env()` and the secret guards
byte-unchanged · the tracker decision record exists and cites §D item 14 · `ruff` and
`basedpyright` clean.

**Implementor brief.**

```yaml
id: 04-b11-settings-annotation
title: Annotate the final auth/session settings state and record the tracker decision
priority: low
depends_on: [04-b02, 04-b08, 04-b10]
source_reference: .ai/plans/04-auth-login-remediation.md
source_section: BLOCK 9 — annotation and audit-id comment hygiene
source_blocks: ["BLOCK 9", "04-VAL-002"]
description: >
  Add an annotated SESSION_* / AUTH_* policy block to config/settings/base.py describing
  the final state of every auth/session setting this phase changed, and record that phase
  04 introduces no new bare AUT-00N references.
goals:
  - "every auth/session setting this phase touched has an accurate comment"
  - "exactly one file changes"
  - "no marker sweep is performed"
extra_context: "All binding constraints for this block are stated in the prose above (Verified starting state / Corrections applied / Out of scope). Read them before editing."
files:
  - path: src/backend/config/settings/base.py
    targets:
      - type: comment
        name: "the existing '# Security settings (TLS/SSL ready)' block"
      - type: setting
        name: SESSION_COOKIE_SECURE
        note: "reference anchor - do not move"
      - type: setting
        name: AUTH_PASSWORD_VALIDATORS
        note: "annotated if B-02 introduced it"
      - type: setting
        name: SESSION_COOKIE_AGE
        note: "annotated if B-10 introduced it"
changes:
  - action: modify_doc
    description: >
      Add one comment per auth/session setting stating what it is and why it is or is not
      configured, adjacent to the existing security-settings block. Append-only.
acceptance_criteria:
  - "git diff --stat shows exactly one changed file: config/settings/base.py"
  - "ALLOWED_ENV_VARS, read_env() and the secret guards byte-unchanged"
  - "the tracker decision record cites the phase-03 section 5.2 reservation"
  - "the full fast gate is green"
tests_to_run:
  - src/backend/config/settings/tests/
```

---

## §C · Dependency graph and execution order

### C.1 Serial order

**`G-3` is resolved first** — it is a Planner decision about ordering, not about code, and
neither `B-01` nor `B-05` may start without it.

**Scenario alpha — `G-3` = (i) (`B-05` first, or `G-5a` removes the field):**
`B-05 → B-01 → B-02 → B-03 → B-04 → B-07 → B-08 → B-09 → B-06 → B-10 → B-11`

**Scenario beta — `G-3` = (ii) or (iii), or `G-3` unresolved (fallback = (ii)):
`B-01 → B-05 → B-02 → B-03 → B-04 → B-07 → B-08 → B-09 → B-06 → B-10 → B-11`**

`B-05` precedes `B-03` in **both** scenarios: both may add a migration to
`src/backend/apps/users/migrations/`, and `B-05`'s is the smaller and better-understood
one, so it takes `0003_`.

### C.2 Edges, and why each exists

| Edge | Kind | Why |
|---|---|---|
| `G-3` → `B-01`, `G-3` → `B-05` | gate | the `is_active` ordering decision (`U-4`); the source plan sequenced `B-01 → B-05` with no edge covering it |
| `B-01 → B-02` | **hard, `04-VAL-004`** | the admin field contract must land **before** the password policy, so "who may set an admin password" is settled before "what a valid password is" |
| `B-05 → B-03` | **hard, shared artefact** | both may write `apps/users/migrations/0003_*`; whoever runs second must re-derive the number |
| `B-03 → B-04` | **hard, and the source plan did not name it** | at issue time a `LoginToken` row has `telegram_id = NULL`; "prior tokens for the same browser" is identifiable only through the binding `B-03` introduces. Invalidation is *not* independently implementable |
| `B-03 → B-07` | hard, shared file | `B-03` edits `login_status`; `B-07` may add a `logout()` in `consent_decline`. One file, one change at a time |
| `B-05 → B-07` | soft, shared file | `B-05` edits `login_status`'s guard; `B-07` does not, but both are in `consent.py` |
| `B-08 → B-09` | **hard** | the trusted-proxy set must exist in Django before the header is changed, or the two halves ship in the wrong order and the header change has nothing to be trusted against |
| `B-08 → B-11`, `B-10 → B-11`, `B-02 → B-11` | soft | `B-11` annotates the **final** state of the settings `B-02`/`B-08`/`B-10` introduce; it runs last |
| `B-02 → B-06` | soft | `B-06` option (c)'s runbook documents the `ADMIN_PASSWORD` bootstrap path that `B-02` constrains |
| `B-03 → B-10` | **hard, and they must never merge** | both alter session semantics; landing them together makes neither reviewable |
| `B-08 → ` phase 09 `API-005` | **hard, outbound** | phase 09's media limiter must compose with the helper `B-08` creates, or a fourth copy appears. **Phase 09 is told about `B-08`'s landing** |
| `B-09` → phase 09 BLOCKS 10/11/12 | **hard, outbound, currently conflicting** | phase 09 reserves `docker/nginx/nginx.conf` and states *"No other phase claims them"* (`G-9a`) |
| `B-06 →` phase 12 | soft, outbound | phase 12 owns `docs/ops/` runbooks; `B-06` corrects claims in one and adds a procedure in another |

**No edge** between `B-06` and `B-08`, between `B-06` and `B-10`, or between `B-07` and
`B-10`. The one-Implementor rule serialises them; the dependency does not exist.

### C.3 Shared artefacts and reservation rules

| Artefact | Blocks | Rule |
|---|---|---|
| **`src/backend/config/settings/base.py`** | `B-02` (`AUTH_PASSWORD_VALIDATORS`), `B-08` (trusted-proxy setting), `B-10` (`SESSION_COOKIE_AGE`), `B-11` (annotation) — **four blocks** | One at a time. **Append-only**: never reorder a setting another phase annotated. Phase 02 owns `ALLOWED_ENV_VARS`, `read_env()`, the secret guards and `LOCK_TIMEOUT_SECONDS`; phase 06 owns `LOG_MASK_KEY`; phase 09 is read-only here. `MIDDLEWARE` (15 entries, `DbLockTimeoutMiddleware` at position 6) is **read-only for this entire phase** — `04-VAL-001` |
| **`src/backend/apps/users/views/consent.py`** | `B-03` (`login_issue`, `login_status`), `B-05` (`login_status` guard), `B-07` (`consent_decline`) — **three blocks** | Strictly serial. Never two open branches against this file |
| **`src/backend/apps/users/admin.py`** | `B-01` (field contract), `B-05` (`is_active` only, and only if the field is removed) | `B-01`'s `fieldsets` must be built on the post-`B-05` field set when `G-3` = (i). **`list_filter` needs no edit** (verified: `is_active` is not listed) |
| **`src/backend/apps/users/models.py` + `src/backend/apps/users/migrations/`** | `B-03` (option A′/A″ `AddField`), `B-05` (option B `RemoveField`) | **Re-check rule:** the highest existing migration in `src/backend/apps/users/migrations/` is `0002_alter_consentrecord_ip_address.py`, so the next is `0003_` — **re-verify immediately before generating; do not assume.** Never renumber or edit an existing migration. Phase 06 (erasure columns) and phase 15 (role fields) also touch this directory |
| **`docker/nginx/nginx.conf`** | **nobody in this phase** (`G-9a` closed 2026-10-02: `B-09` takes no config edit) | **Read-only for phase 04 — `B-09`'s deferral is the reason.** Was *"Currently reserved by phase 09 for its BLOCKS 10/11/12 — `G-9a` must close first"*; `G-9a` closed **by non-claiming**, so phase 09's reservation is intact and unopposed. **Bind-mounted read-only** in both `docker-compose.yml::nginx` and `docker-compose.prod.yml::nginx`, and **not delivered or rolled back by `deploy.yml`** (`G-9b`). `nginx.dev.conf` is the same: **no block in this phase may edit it.** A new tripwire (`G-9d`) reads both files and must fail if either is edited to weaken the trust model |
| **`src/backend/tests/test_nginx_config.py`** | `B-09`; phase 09 BLOCKS 10/11/12 | The established structural-test home. Extend `_location_block`; do not write a new parser. **`B-09`'s use of it (2026-10-02): extend the `_location_block` helper and add three new tests, leaving the four pre-existing tests byte-for-byte unchanged.** `G-9d` |
| **`src/backend/apps/users/services/login_token.py`** | `B-03`, `B-04` | Two commits, never one. `B-04`'s invalidation `UPDATE` must live here — the view is forbidden `"UPDATE login_tokens"` **and** the `secrets` import |
| **`src/backend/apps/users/tests/{test_login,test_consent,test_login_token}.py`** | `B-03`, `B-04`, `B-08` | One commit each; the production change and its test change land together (§E) |
| **`docs/ops/docker-deployment.md`** | `B-06` (three claims), `B-08` (trust model), `B-09` (rollout step) | Phase 01, 02, 08 and 09 have all edited it; **phase 12 owns the runbook**. Re-read immediately before editing; **stop and report on a concurrent change** |
| **`docs/01-spec/technical-specification.md`** | `B-10` (`G-10e`, the §H *Session* bullet, **second commit**) | **Phase 06 holds the reservation and explicitly carves `B-10` out** — `06-pii-consent-remediation.md` §5.1: *"Phase 04 edits only under its BLOCK 8 option (c), and only after checking for a concurrent edit."* Re-read the file immediately before editing; `git status`/`git diff` it; **stop and report on a concurrent change** — never merge, never regenerate. On a concurrent edit, `B-10` ships the `base.py` declaration alone and records the spec edit as a **named deferred obligation** with the replacement text, owned by the coordinator |
| **`docs/02-database/db-schema.md`** | `B-03` (a new `LoginToken` column) | Must land in the same commit as the migration |
| **`src/backend/conftest.py`** | **nobody in this phase** | The most contended file in the repository. If a block appears to need a fixture, that is a signal the test is over-fitted. `B-03`'s binding tests build their own tokens; the bot conftest's async redefinition must not be touched |
| **`.po` files** | **nobody — read-only** | Modified in the working tree by another agent (§A.2). i18n work reports and stops |

---

## §D · Cross-phase boundaries

Each row states what **this phase must not do** and **how a violation is detected**.

### D.1 Phase 15 — authorization

| # | Phase-15 item | This phase must not | Detection |
|---|---|---|---|
| 1 | `15-AUTHZ-001` per-request account-state gate | ship any middleware, decorator or per-request gate; **never edit `MIDDLEWARE`** | `git diff` on `base.py::MIDDLEWARE` is empty and still shows **15** entries with `DbLockTimeoutMiddleware` at position 6; `apps/core/middleware/` gains no module |
| 2 | `15-AUTHZ-003` admin role | widen or narrow `UserAdmin.has_add_permission` / `has_change_permission` / `has_delete_permission` / `has_view_permission`. `B-01` owns the **field set**; phase 15 owns the **predicate** | those four bodies are byte-unchanged in `B-01`'s diff |
| 3 | `15-AUTHZ-004` CSRF / `@require_POST` on `login_issue` | change `login_issue`'s decorator set or its method handling | `login_issue` still carries `@never_cache` only; `apps/core/tests/test_login_issue_template.py` and `apps/users/tests/test_login_issue_template.py` green unchanged |
| 4 | `15-AUTHZ-005` queryset visibility predicate | touch `can_publish_ad` or the queryset visibility predicate | `account_state.py::can_publish_ad` body unchanged |
| 5 | `telegram_bot/middlewares/permissions.py` refactor | `B-05` option (D) edits it — **only** under an explicitly recorded cross-phase decision, with a bot-side test | `git diff telegram_bot/middlewares/permissions.py` is empty unless `G-5a` = (D) was recorded with the phase-15 coordination |

**Recorded residual scope of `B-01` (shipped, `a19a0ee` + `83622e0`) — the phase report
must not overstate the closure.** `B-01`'s goal *"consent and account-state booleans
read-only in admin"* is **true of the `User` change form and FALSE of the admin as a
whole.** `is_banned` **remains admin-writable from the `Ad` changelist** via
`AdAdmin.action_ban_user` → `moderation/admin_actions.py::bulk_ban_users`, which writes
`User.objects.filter(id__in=user_ids).update(is_banned=True)` directly, for the ordinary
user. Detection: `B-01`'s diff touches **no** `has_*_permission` body and **no**
`moderation/admin_actions.py`; `AdAdmin.actions` still carries `action_ban_user`. **Phase
15's `15-AUTHZ-003` still owns the predicate** — `B-01` changed the field set only, and
`bulk_ban_users` is deliberately left without a `select_for_update` (phase 03 `DB-003`).

### D.2 Phase 06 — PII / consent

| # | Phase-06 item | This phase must not | Detection |
|---|---|---|---|
| 6 | **`PII-103`** — merged into `04-AUT-005` | ship a second `fieldsets` declaration | exactly **one** field-contract declaration on `UserAdmin` at phase exit |
| 7 | **`PII-105`** decline reversibility | **ship the decline-path `logout()` before `PII-105` is decided** — `G-7b` | `B-07`'s commit body names the `PII-105` decision; without it, `consent_decline` is untouched |
| 8 | **`PII-107`** the `ConsentRecord` write | change `withdraw_consent`'s write of a `ConsentRecord`, or `UserAdmin.withdraw_consent_action` | `users/services/deletion.py` diff is empty for `B-07`; `withdraw_consent_action` body unchanged |
| 9 | **`PII-113`** doc conflict | edit `docs/01-spec/spec-index.md` or `technical-specification.md` without re-reading | the file is re-read immediately before editing; `git status` shows no other phase's content clobbered |
| 10 | **`PII-112`** `mask_telegram_id` | assert a mask's **length or shape** in any phase-04 test | no numeric assertion adjacent to `mask_telegram_id` in the phase-04 test diffs |

**Recorded for phase 06 — `PII-107`: the writer/trigger asymmetry (MEDIUM).** After
`a19a0ee` there is **no operator-reachable `withdraw_consent` trigger on the `User` admin
at all**, because `UserAdmin` declares no `actions` and never did (see `B-07`'s
"Correction applied — `withdraw_consent_action` is unreachable, and always was"). What
phase 06 must take from this, and **what this plan does not do**:

1. **The data-subject path is unaffected** — `apps/users/views/consent.py::consent_withdraw`
   still calls `withdraw_consent(user)` and then `logout(request)`. GDPR withdrawal by
   the subject still works; `B-01` did not touch it.
2. **A `PII-107` closure sentence of the form *"every consent-state transition goes
   through the audited service"* is true of the WRITERS but there is no audited
   OPERATOR path to trigger it.** Record the asymmetry explicitly. Do not write a closure
   statement that implies an operator path exists.
3. **No compensating capability was silently lost.** `B-01` retired the (unaudited) form
   write for `is_deleted` / `is_declined` as a **recorded decision** in its
   operator-capability table — not as an omission, and not in reliance on the changelist
   action existing. Those form writes bypassed `withdraw_consent`'s
   `transaction.atomic()`, the PII nulling, the `LoginToken` deletion and the
   `bump_search_cache_version` on commit, so removing them is correct on their own terms.
4. **This is a record only.** **No phase-06 artefact is edited from this plan.** The
   decision is `B-07`'s `G-7` sub-decision (`B-07`'s section records both branches); this
   phase does not pre-empt it, and phase 06 is not required to wait on it to proceed on
   anything else.

### D.3 Phase 03 — DB / concurrency

| # | Phase-03 item | This phase must not | Detection |
|---|---|---|---|
| 11 | **`DB-002`** transaction boundary | add, move or nest an `atomic()` in `apps/users/services/login_token.py`; make `claim_token`'s `now` optional or computed inside | `grep -c "transaction.atomic" apps/users/services/login_token.py` is unchanged; `claim_token`'s signature unchanged; the docstring's "the caller owns the transaction" statement survives |
| 12 | **`DB-010` / `DB-003`** moderation locks | add `select_for_update` to `bulk_ban_users` | `apps/moderation/tests/test_admin_actions.py::test_bulk_ban_users_not_locked` green **unchanged** |
| 13 | **`DB-004`** audit-row durability | move `record_consent_action` relative to `logout()` in `consent_decline` | the call order in `consent_decline`'s body is unchanged |
| 14 | **§5.2 item 3 — the marker sweep** | **perform any `EXT-`/`AUT-`/`SRH-` marker sweep.** *"Phases 04–15 must not start BLOCK 11-style legacy sweeps of their own. One sweep, in BLOCK 11, under the coordinator's chosen option"* | `B-11`'s diff touches **one** file, `config/settings/base.py` |
| 15 | **§5.2 item 2 — tracker keys** | write a bare `AUT-00N` in any new comment or docstring | no new unqualified `AUT-00N` appears; new cross-references use `NN-<PREFIX>-00N` |
| 16 | `conftest.py` | edit either conftest | the phase-04 diff contains no `conftest.py` |

### D.4 Phase 02 — config / secrets

| # | Phase-02 item | This phase must not | Detection |
|---|---|---|---|
| 17 | **`CFG-003`** `ADMIN_PASSWORD` env | change how `ADMIN_PASSWORD` is read, or edit `docker/entrypoint-create-admin.sh` | `create_admin_user.py`'s resolution expression is unchanged; `entrypoint-create-admin.sh` is not in any phase-04 diff |
| 18 | **`CFG-004`** `EMAIL_*` | touch the `EMAIL_HOST` guard **expression** or the `EMAIL_BACKEND` pin. `B-06` touches **comments only** | `prod.py`'s `EMAIL_HOST = env(...)` and `EMAIL_BACKEND = env(...)` lines are byte-unchanged |
| 19 | **`test_env_allowlist_reverse.py`** — **the new gate** | add any env-var-backed setting anywhere in the tree **without** an `ALLOWED_ENV_VARS` entry **and** matching `.env.example` / `.env.dev.example` / `.env.prod.example` / `.env.test.example` updates **in the same commit**. The gate AST-scans the **whole tree** (`test_env_scan_covers_more_than_the_settings_package`) | `config/settings/tests/test_env_allowlist_reverse.py::test_consumed_env_vars_are_allowlisted` green. **Binds `B-08`'s trusted-proxy setting and `B-02`'s validator length if either is env-driven** |

### D.5 Phase 09 — external API

| # | Phase-09 item | This phase must not | Detection |
|---|---|---|---|
| 20 | `docker/nginx/nginx.conf` + `nginx.dev.conf` reserved for BLOCKS 10/11/12 — *"No other phase claims them"* | edit either file before `G-9a` closes | `G-9a` recorded; no phase-04 commit touches those files until it does |
| 21 | `09-API-005`'s `media_limit` zone and `media_gate` | change nginx's `limit_req_zone $binary_remote_addr` keys; add a `media_limit` zone; edit `media_gate` | `grep -c limit_req_zone docker/nginx/nginx.conf` unchanged by `B-09` |
| 22 | Phase 09 BLOCK 10 defers the client-IP **policy** to phase 04/08 | let phase 09's media limiter land on the **old** trusting helper, creating a fourth copy | phase 09 is notified when `B-08` lands; `B-08`'s commit body states the helper's location so phase 09 can compose with it |

### D.6 Phase 15 `15-AUTHZ-004` and the `AUT-007` CSRF half

`04-AUT-007`'s second half — **"the token endpoint should be CSRF-protected and
POST-only"** — is explicitly phase 15's and is **not** in scope here. `B-03` and `B-04`
must leave `login_issue`'s method handling exactly as it is.

---

## §E · Test-ownership ledger

**Governing rule: a test change lands in the SAME COMMIT as the production change it
follows.** If a block's production diff and its test diff are in different commits, the
block is incomplete.

### E.1 The **sixteen** `B-03` rewrite sites — CORRECTED 2026-10-01 by the B-03 Planner

**Governing rule, restated because this list is the block's second-largest deliverable: a
test change lands in the SAME COMMIT as the production change it follows.** If `B-03`'s
production diff and any of these sixteen test diffs are in different commits, the block is
incomplete.

**The count moved twice, and the current number is sixteen.** The source plan said **seven**;
the code context said **nine** (correct at `f93e7fb`); the Researcher said **twelve**
(correct after `B-05`'s three additions); and **four more live in `test_login_token.py`,
which none of those counts searched** — they hide behind its `_make_token` helper, and they
break only because `G-1a` decided that a directly-created (unbound) row is **refused**
rather than accepted. `apps/users/tests/test_login.py` holds the classes `TestLoginIssue`,
`TestLoginStatus`, `TestLoginTokenSecurity`, `TestLoginPreferredCitySync`,
`TestLoginRateLimitCheck` (plus module-level `_clear_cache`, `_claim_login`,
`podgorica_city`, `budva_city`); `apps/users/tests/test_consent.py::TestLoginStatusNoPii`
exists; `apps/users/tests/test_login_token.py` holds `TestIssueToken`, `TestClaimToken`,
`TestConsumeToken`, `TestClaimConsumeAgreement`, `TestLoginHandshakeOwnership` (plus
module-level `_make_token` and `_claim`). **Re-derive before editing** — the command is in
the brief. **Do not trust any count in this document, including this one.**

| # | Site | What it asserts today | What it must become under `G-1` | Why |
|---|---|---|---|---|
| 1 | `apps/users/tests/test_login.py::TestLoginStatus::test_login_status_204_pending` | direct `LoginToken.objects.create`, unclaimed and unexpired → **204** | issue via `client.get("/login/issue/")`, keep `response.context["raw_token"]`, poll → still **204** | the cheapest rewrite; the binding matches because it came from the issuing path |
| 2 | `…::TestLoginStatus::test_login_status_410_expired` | expired row → **410** | issue through the path, then force `expires_at` back with an `UPDATE` → **410** | **must still prove expiry.** Do not let it degenerate into an absence test |
| 3 | `…::TestLoginStatus::test_login_status_410_already_consumed` | consumed row → **410** | issue through the path, then set `consumed_at` with an `UPDATE` → **410** | same — otherwise it silently stops testing reuse |
| 4 | `…::TestLoginStatus::test_login_status_200_claimed_and_user_exists` | claimed row → **200** plus a session | issue → `claim_token(...)` → **200** plus a session | the binding gate sits between the claim and the login; closest analogue to the block's own `test_same_browser_redeems_end_to_end` |
| 5 | `…::TestLoginStatus::test_login_status_410_user_banned` | claimed row, `can_login` false → **410** | issue, claim, then ban → **410** | two blocks touch it; serial (`B-05 → B-03`), each in its own commit |
| 6 | `…::TestLoginStatus::test_login_status_refuses_a_disabled_account` (**`B-05`'s**, `e106e0b`) | `is_active=False` → **410** and no session cookie | issue, claim, `is_active=False` → **410** and no session cookie | preserve the exact semantics that commit body asserts |
| 7 | `…::TestLoginStatus::test_login_status_burns_the_token_for_a_disabled_account` (**`B-05`'s**) | asserts `consumed_at is not None` after the POST, then a replay **410** | same shape, but the hash comes from `issue_token`'s return, held across the two requests | **the trickiest of the twelve in `test_login.py`**: going through the issuing path means carrying the hash rather than recomputing it locally |
| 8 | `…::TestLoginStatus::test_login_status_200_and_session_for_an_enabled_account` (**`B-05`'s anti-over-reach guard**) | positive control → **200** and `_auth_user_id` in the session | same, issued through the path | **the positive control must survive.** A blanket refusal would pass 6 and 7 and must fail here |
| 9 | `…::TestLoginTokenSecurity::test_consumed_token_cannot_be_reused` | first poll **200**, second **410** | issue through the path; the two-poll shape survives unchanged | the second poll's expected status gains no new dependence — the row is bound |
| 10 | `…::TestLoginTokenSecurity::test_bot_phase_claim_completes_when_user_exists` | claimed, unconsumed row → **200** and `consumed_at` set | issue through the path, claim → **200** and `consumed_at` set | **doubles as the bot-unchanged test**: the bot supplies no binding and `claim_token`'s `WHERE` does not reference one |
| 11 | `…::test_login.py::_claim_login` *(module-level helper, asserts **200**)* | builds a claimed row, posts, asserts **200** | **change once**: issue through the path, then claim | it takes the pytest-django `client` fixture, which already holds the browser-id cookie, so its **three `TestLoginPreferredCitySync` dependents change transitively with no body edits** |
| 12 | `apps/users/tests/test_consent.py::TestLoginStatusNoPii::test_login_consume_no_raw_telegram_id` | asserts **200**; no raw telegram id in the logs; `"tg_"` present | issue through the path so the row is bound and the expected status stays **200**; both `caplog` assertions stay | **the single most likely place for a PII regression.** `mask_telegram_id()` returns `tg_` + 8 hex chars, so `"tg_" in caplog.text` is satisfied only by the CONSUMED-path line; the new `UNBOUND` line must carry **no** `telegram_id` and **no** binding value |
| 13 | `apps/users/tests/test_login_token.py::_make_token` *(module-level helper)* | builds a `LoginToken` row for a known raw token | gain a module-level `_BROWSER_ID` and write `browser_binding=_hash_browser_id(_BROWSER_ID)` | **newly in scope, and the reason the count is sixteen.** Under `G-1a`'s fail-closed policy every row it builds is unbound, so `consume_token` on one returns `UNBOUND`, not `CONSUMED` |
| 14 | `…::TestConsumeToken::test_claimed_token_consumed` | `CONSUMED`, `telegram_id` set, `consumed_at` stamped | `consume_token(raw, browser_id=_BROWSER_ID)` — all three assertions unchanged | production code is king: the **test** changes, not the predicate |
| 15 | `…::TestClaimConsumeAgreement::test_b_consumed_token_not_claimable_by_anyone` | `consume_token(raw).value == "consumed"`, then no one may claim | `consume_token(raw, browser_id=_BROWSER_ID)` — the phase-separation assertion unchanged | same |
| 16 | `…::TestClaimConsumeAgreement::test_c_consumed_binds_to_the_claiming_user` | `CONSUMED` bound to the claimer, `consumed_at` stamped | `consume_token(raw, browser_id=_BROWSER_ID)` — all assertions unchanged | same; **do not weaken the `telegram_id` identity-binding assertion** — a browser-binding column must never be mistaken for an identity binding |

**The two `test_login_token.py` tests that must NOT change, and why** — this is the check
that the rewrite did not over-reach into the phase's structural guards:
`TestConsumeToken::test_unclaimed_live_token_pending` and
`TestClaimConsumeAgreement::test_d_never_claimed_is_pending` both expect `PENDING`, and
`G-1a` places the binding gate **after** the `PENDING` step. **That ordering choice exists
for these two tests**; a later implementor who moves the gate earlier breaks them, and the
breakage is a test failure that looks unrelated to the cause.

**Affected but NOT changed** — these must stay green untouched, and they are the check
that the rewrite did not over-reach:

| Test | Why it is unaffected |
|---|---|
| `…::TestLoginStatus::test_login_status_410_no_token` | no `LoginToken` row at all |
| `…::TestLoginStatus::test_login_status_410_nonexistent_token` | no row |
| `…::TestLoginStatus::test_login_status_405_on_get` | method check only — and `login_status`'s decorators are untouched (`G-1e`) |
| `…::TestLoginTokenSecurity::test_token_hash_mismatch_returns_410`, `test_stored_hash_is_sha256_not_raw`, `test_token_hash_length_is_64_hex` | hash-shape assertions, no direct row |
| `apps/users/tests/test_consent.py::TestConsentWithdrawIdempotency::test_consent_withdraw_idempotent_on_deleted_user` | the **only** `LoginToken.objects.create` that does **not** POST to `/login/status/`; it asserts the row **survives** `withdraw_consent`. **Do not over-count it** |
| `apps/users/tests/test_consent.py::TestLoginStatusNoPii::test_login_consume_does_not_set_session_cookie_on_failure` | no row |
| **`src/telegram_bot/tests/conftest.py::login_token_factory`** | builds a row with no binding — **unaffected under every option**, because the bot never supplies a binding and `claim_token`'s `WHERE` clause does not reference one. **This is also why `browser_binding` must be nullable**: a `NOT NULL` column would raise `IntegrityError` here |
| **`src/telegram_bot/tests/test_login.py::TestTokenRejection::test_reject_expired_token` / `test_reject_consumed_token`** | same. Their continued passing **is** the proof that `src/telegram_bot/` needs no change — the reason the brief's proof is source-level rather than an added bot-side test |
| `apps/core/tests/test_login_issue_template.py` (all three tests) | pure file-level assertions on `users/login_issue.html`, which this block does not touch. **Note the correct path — the plan's `§D.1` cites a non-existent `apps/users/tests/test_login_issue_template.py`; see `B-03`'s `F-9` row** |
| `apps/core/tests/test_privacy.py::TestPrivacyPage` | `privacy.html` is not touched in this block; the deferred row is a separate, later commit (`G-1g`) |
| `apps/ads/tests/test_auth_nav.py`, `apps/cabinet/tests/test_cabinet_sections.py`, `apps/users/tests/test_logout.py` | they assert `response.url.startswith("/login/issue/")` on a `login_required` redirect — they never reach the view. `test_auth_nav.py`'s one real `GET /login/issue/?lang=ru` checks only the language, so the extra cookie is invisible to it |
| `apps/core/tests/test_contact_rate_limit.py` (`/login/issue/` **429** case) | a `429` response issues no token and therefore sets no binding cookie |
| `apps/users/tests/test_admin_pii_containment.py::test_login_token_list_display_masks_telegram_id` | asserts only on `LoginTokenAdmin.list_display`; the new column reaches no admin surface because `has_add_permission` and `has_change_permission` are both `False` (`C-12`) |

### E.2 The one other test this phase changes

**CORRECTED 2026-10-01 by the `B-08` Planner — the characterisation was wrong, and the
correction changes the work.**

| Test | What it *says* | What it *asserts* | Block | Why |
|---|---|---|---|---|
| `apps/core/tests/test_contact_rate_limit.py::test_x_forwarded_for_takes_precedence` | docstring: *"X-Forwarded-For (nginx) is preferred over REMOTE_ADDR"* — sets `REMOTE_ADDR = "10.0.0.1"`, `HTTP_X_FORWARDED_FOR = "203.0.113.5"` | **one assertion:** `check_deep_link_render_rate_limit(request) is True` — which holds because the key is a **fresh counter**, whatever IP was resolved | **`B-08`** | **A fresh-counter assertion wearing a precedence claim.** The plan recorded it as "asserts the header wins" and as a test that must be *replaced*, which implies an assertion goes red. **It does not. It passes unchanged under every trust model this block could have chosen** — the key merely becomes `telegram_dl_rl:10.0.0.1`, which is also fresh. **Rewrite cost is 1 rewritten, 12 passing unchanged, 0 to fix.** The rewrite is a **documentation act**: rename it to the untrusted-peer form, make the resolved **key** the subject instead of a boolean that is true either way, and keep the old rule visible in the docstring so the history stays. **Not deleted** — the record of the old behaviour is the point |

### E.3 Structural tripwires that must pass **unchanged**

| Tripwire | What it enforces | Consequence for this phase |
|---|---|---|
| `apps/users/tests/test_login_token.py::TestLoginHandshakeOwnership::test_consent_view_has_no_token_logic` | reads `apps/users/views/consent.py` and asserts **none** of `hashlib`, **`secrets`**, `LoginToken`, `"UPDATE login_tokens"`, `".update(consumed_at="` appears in it | **The `secrets` clause is an extra constraint the source plan never mentioned**, and `B-03` is the block it constrains hardest. Three consequences, all settled in `B-03`: (a) **`B-04`'s invalidation `UPDATE` must live in `login_token.py`, never in the view**; (b) **`B-03`'s browser-id mint must live in the service too** — `login_token.py` already imports `secrets` and already calls `secrets.token_urlsafe`, so the mint is a natural extension and the view only ever calls `response.set_cookie(...)`; (c) **the view must never import the `LoginToken` *model*** — that would put the substring `LoginToken` in the file. Importing from `apps.users.services.login_token` is **safe**: that path is lowercase, so the forbidden substring does not occur in it. **The test is UNCHANGED and UNEDITED** |
| `apps/moderation/tests/test_admin_actions.py::test_bulk_ban_users_not_locked` | `inspect.getsource(bulk_ban_users)`: `"select_for_update" not in src`, `"transaction.atomic" in src` | phase 03 `DB-003`. `B-07` must not add a row lock to `bulk_ban_users`, and must not remove the `atomic()` |
| `apps/moderation/tests/test_moderation_views.py::TestModerationReviewLocking::test_ban_user_uses_select_for_update_and_atomic` **(ADDED 2026-10-02 by the `B-07` Planner — `E.6`)** | `inspect.getsource(review.ban_user)` contains `"transaction.atomic"` and `"select_for_update"` | **This is a substring check, so it would NOT notice a wrong-target `logout(request)` added to `ban_user`** — a session flush leaves both substrings intact. Together with `TestBanUserView`'s four tests that makes **five** tests blind to the `ban_user` wrong-target trap (`G-D`), which is why `B-07`'s known-gap test 2 exists. **Tripwire, not an obstacle** |
| `apps/core/tests/test_scheduler.py::TestSchedulerConstants::test_hourly_commands_match_spec` | an **exact `==` list assertion** on `HOURLY_COMMANDS` | **The entry count must stay exactly 9**: `archive_sweep, delete_sweep, consent_hard_delete, sweep_drafts, sweep_orphaned_media, cleanup_login_tokens, purge_failed_ads, purge_rejected_ads, purge_deleted_ads`. **No block may add a scheduler entry** — including a hypothetical `B-04` janitor. *(The code context names this test `test_scheduler_uses_canonical_hohourly_list`; that name does not exist — see §A.5. Verified live.)* |
| `…::TestSchedulerConstants::test_daily_commands_include_send_alerts` | exact `== ["send_alerts", "rollup_daily_metrics"]` | unchanged |
| `…::TestSchedulerConstants::test_all_hourly_commands_are_distinct` | no duplicate command names | unchanged |
| `src/backend/tests/test_nginx_config.py::test_nginx_metrics_has_proxy_headers` | the **substring** `"proxy_set_header X-Forwarded-For"` inside the `= /metrics` block | **Satisfied by both `$proxy_add_x_forwarded_for` and `$remote_addr`** — the **value is never inspected**, so rewriting the value leaves it **GREEN** (corrected 2026-10-02 by the `B-09` Planner: an earlier reading in this phase's prose overstated it as turning red on any rewrite). It turns red only on removing/renaming the directive, or on changing the `location = /metrics` key. Under the chosen outcome (`G-9c`: no directive change) it is a **pure anti-regression guard**, and it must pass **unchanged** |
| `src/backend/tests/test_nginx_config.py` — the other three pre-existing tests | `test_nginx_config_exists` (path exists) · `test_nginx_metrics_has_proxy_pass` (`proxy_pass` substring in the block) · `test_nginx_metrics_restricted_to_localhost` (`allow 127.0.0.1` **and** `deny all`) | All three are scoped to the `= /metrics` block or the file's existence and are **unaffected** by `G-9c`'s outcome, which touches no directive. **All four must pass byte-for-byte unchanged** — the Implementor adds tests to this module and edits none of the existing four |
| **`src/backend/tests/test_nginx_config.py` — three tests ADDED 2026-10-02 by the `B-09` Planner (`G-9d`)** | the trust-model **invariant**, over **both** `.conf` files: (1) every `proxy_pass` location sets `proxy_set_header X-Real-IP $remote_addr;` **exactly** · (2) no `proxy_set_header` line takes its value from a client-echo `$http_*` variable · (3) any `set_real_ip_from` present is **never a wildcard** and is paired with an explicit `real_ip_header` | **These are the block's only code deliverable.** They are **green today** (9/9 and 6/6 sites satisfy (1); no `$http_*` in any `proxy_set_header`; `real_ip` absent) and turn red **only** on the three silent failures that would silently invalidate `B-08`'s design. They assert the **invariant, never the current value**, so a future legitimate `$remote_addr` switch does **not** trip them. **Deliberately NOT asserted:** the `X-Forwarded-For` *value* (pinning today's appending form as an invariant is the `G-B` mistake), and the `limit_req_zone` keys (phase 09 BLOCK 10's surface, which explicitly forbids changing them here) |
| `apps/users/tests/test_account_state.py::TestCanLogin` | six assertions incl. `deleted → True`, `ads_auto_publish=False → True` | `B-05` must not change `can_login`'s existing terms; under option (A) a term is **added**. **`B-07` (`G-7b`): the `is_declined → False` term — pinned by `test_declined_user_cannot_login` **and** `test_banned_and_declined_cannot_login` — is what makes a decline-path `logout()` a permanent one-way door, because `is_declined` can only be cleared by an authenticated `consent_accept`** |
| `apps/users/tests/test_consent.py::TestConsentWithdrawIdempotency` | `withdraw_consent` is idempotent, and **no `LoginToken` deletion happens on the no-op path** | an extra constraint the source plan did not name; `B-07` must not change `withdraw_consent`'s transaction shape |
| `apps/users/tests/test_consent.py::TestConsentBannerGuard` | a soft-deleted user's dashboard returns **200**, and an active non-consenting user's returns **200** with the banner | **A tripwire today and phase 15's migration (`G-F`) — its assertion is the defect.** `test_banner_hidden_for_deleted_user` sets `is_deleted=True` in the fixture, so no transition runs and `B-07`'s cost is zero; a **per-request gate turns it red**, and `15-AUTHZ-001` must budget the rewrite. **Do not read its eventual redness as a `B-03`/`B-04` regression** |
| `apps/users/tests/test_admin_pii_containment.py` (five module-level tests) | admin surfaces do not render a raw telegram id | `B-01` **adds**; all five stay unchanged and green |

---

### E.4 `B-08` — the full test ledger, and the `D-6` correction

**`D-6` was overstated and is corrected here.** The plan says an env-backed setting "needs an
`ALLOWED_ENV_VARS` entry **and four `.env.*.example` updates in the same commit**, or the fast
gate fails". Verified against the live tests:

| Test | Direction it asserts | Consequence for `B-08` |
|---|---|---|
| `test_env_allowlist.py::test_example_keys_in_allowlist` | `example keys ⊆ ALLOWED_ENV_VARS` — template ⇒ allowlist, **not** the reverse | a template entry requires an allowlist entry; an allowlist entry requires **no** template edit |
| `test_env_allowlist.py::test_python_consumed_vars_in_allowlist` | a **hardcoded 8-name subset** (`DATABASE_URL`, `POSTGRES_PORT`, `DJANGO_BUILD`, `DJANGO_ONESHOT`, `DJANGO_SETTINGS_MODULE`, `EMAIL_BACKEND`, `BOT_HEALTH_STALE_SECONDS`, `SCHEDULER_COMMAND_TIMEOUT`) — a subset assertion, **not** an equality | adding a ninth consumed var does **not** break it |
| `test_env_allowlist_reverse.py::test_consumed_env_vars_are_allowlisted` | `consumed ⊆ ALLOWED_ENV_VARS` — read ⇒ allowlist, **not** the reverse. Its own docstring states the reverse is *"false by construction"* (12 of 49 entries have no Python read) | an env read requires an allowlist entry; **that is the only gate cost** |

**Corrected: the four template edits are not gate-binding.** `G-8c` chose a literal tuple on
the merits — chiefly because no compose file declares `networks:`, so there is no stable value
an operator could put in it — **not** because the templates are contended. If a later block
makes the tuple env-driven, the cost is **one line in `base.py::ALLOWED_ENV_VARS`**, and the
`# env-contract:` opt-out remains unavailable (it is documented for *"not a deployment
variable"*, and this **is** one).

**`B-08`'s complete test ledger — 1 rewritten, 12 unchanged, 10 new.**

| Test | Status | Note |
|---|---|---|
| `apps/core/tests/test_contact_rate_limit.py::test_x_forwarded_for_takes_precedence` | **REWRITTEN** | `§E.2` |
| `apps/core/tests/test_contact_rate_limit.py` — `test_allows_under_limit`, `test_blocks_after_threshold`, `test_independent_per_ip`, `test_rate_limit_check_handles_cache_incr_value_error` | unchanged | bare `HttpRequest` + item assignment; a loopback peer with no header, so the key is unchanged |
| `apps/core/tests/test_contact_rate_limit.py::TestDeepLinkRenderRateLimitView` — **all 5** | unchanged | they pre-fill `cache.set("telegram_dl_rl:127.0.0.1", 60)`; the test client is `127.0.0.1`, a loopback peer with **no** header, so the resolved key is `127.0.0.1` **by the gate path, not by luck**. **These 5 were the only tests at risk under a literal-IP trusted set, and the chosen design removes that risk** |
| `apps/users/tests/test_login.py::TestLoginRateLimitCheck` — `test_login_rate_limit_check`, `test_login_rate_limit_check_handles_cache_incr_value_error` | unchanged | whole-dict `request.META = {"REMOTE_ADDR": "127.0.0.1"}`; asserts `cache.get("login_rl:127.0.0.1")` |
| `apps/search/tests/test_autocomplete.py::TestRateLimitService::test_rate_limit_blocks_after_threshold` | unchanged | item assignment, no header |
| `apps/users/tests/test_consent_records.py::TestAnonymizeIp` — 3 tests | unchanged | call `_anonymize_ip` **directly**; its body is not touched (`G-8a`) |
| `apps/users/tests/test_consent_records.py::TestConsentRecording::test_ip_is_anonymized_and_ua_truncated` | unchanged | **permissive by design** — accepts `None` **or** any value ending in `.0`. The helper returns `127.0.0.1` → `_anonymize_ip` → `127.0.0.0` → ends in `.0` |
| `apps/core/tests/test_client_ip.py` — tests 2, 3, 4, 6, 7, 8, 10 | **NEW** | the gate, the precedence, the walk, the malformed fallback, the empty-`META` default, the IPv6 key stability, the configuration-independence |
| cross-consumer agreement — test 9 | **NEW** | the three limiters **and** `record_consent_action` on one request object |

**Baseline arithmetic.** 2627 collected before this block; **one** pre-existing failure in
`apps/search/tests/test_search_slo.py` (a wall-clock SLO test) is **not** this block's. Exit
condition: the fast gate green on `--create-db` after any test-DB restart. The known
`DeadlockDetected` / unique-key shard collisions are a **test-DB flake, not a code
regression** — if an error names a symbol this block did not touch, re-run before believing it.

---

### E.5 `B-04` — the re-derived test ledger (2026-10-02, `B-04` Planner)

**`B-03`'s sixteen-site count does not carry over, and no count in this document should be
trusted without re-derivation.** `B-04` touches **no test that constructs a `LoginToken`
directly.** Its entire blast radius is the **issue path**, and exactly **one** shipped test
pins the opposite invariant.

**Re-derive command (semantic, not positional):**

```
Select-String -Path src/backend/apps/users/tests/test_login.py,
                         src/backend/apps/users/tests/test_login_token.py `
              -Pattern 'issue_token|client\.get\("/login/issue/"\)|_make_token|LoginToken\.objects\.create'
```

**Full inventory of `LoginToken` construction and issuance, verified at `a0bd928` — 1 rewritten, 2 changed-file-but-untouched controls, 5 new, 0 deletions.**

| # | Site | How it touches the token | Disposition under `G-4b` |
|---|---|---|---|
| 1 | `apps/users/tests/test_login.py::TestLoginTokenBinding::test_repeat_issue_does_not_invalidate_the_binding` | issues **twice from one browser**, claims **both** with the same `telegram_id`, then redeems the **first** and asserts `200` | **REWRITTEN.** The *only* rewritten test. Its name asserts the invariant `G-4b` reverses. Becomes: the binding is still reused (the `B-03` re-mint guard is **kept as an assertion**, not dropped), the second issue supersedes the first, the second redeems `200`. **Deleting it instead would silently drop `B-03`'s regression guard** |
| 2 | `apps/users/tests/test_login.py::TestLoginTokenBinding::test_repeat_issue_reuses_the_same_browser_binding` | issues twice from browser A and once from browser B, then compares stored `browser_binding` values | **UNCHANGED and green.** It reads the binding off both rows; a burn does not delete. **This is the control proving the blast radius is one test, not two** |
| 3 | `apps/users/tests/test_login_token.py::TestIssueToken::test_two_issues_differ` | calls `issue_token()` twice **with no `browser_id`** → two different bindings | **UNCHANGED and green** (`C-15` corrects `C-14`: it asserts nothing about accumulation). **It is the phase's textbook "test that passes for the wrong reason" — it would pass with or without the mechanism and must not be cited as evidence** |
| 4 | `apps/users/tests/test_login_token.py::TestClaimToken::test_claim_token_returning_matches_model_fields` | calls `issue_token(browser_id=_BROWSER_ID)` once, then claims and asserts the binding round-trips | **UNCHANGED and green.** `RETURNING_COLUMNS` is unchanged because no column is added |
| 5 | `apps/users/tests/test_login_token.py::TestIssueToken` — the other five (`test_stores_sha256_of_raw`, `test_leaves_telegram_id_and_consumed_at_null`, `test_expires_in_5_minutes`, `test_raw_never_persisted`, `test_raw_token_is_urlsafe_and_matches_pattern`) | each calls `issue_token()` once **with no `browser_id`** | **UNCHANGED and green** — with no presented cookie a fresh id is minted, so a single issue can never supersede anything |
| 6 | `apps/users/tests/test_login.py::TestLoginIssue` (5 tests) · `TestLoginStatus` (11) · `TestLoginTokenSecurity` (5) · `test_login.py::_claim_login` (module-level helper) and its three `TestLoginPreferredCitySync` dependents | each issues **once** (or twice where the 2nd is a `429`) | **UNCHANGED and green.** `test_login_issue_returns_429_on_rate_limit` is the only double-`GET`, and the 2nd is refused by `login_rate_limit_check` before `issue_token`, so no token is issued |
| 7 | `apps/users/tests/test_deletion.py` — 6 direct `LoginToken.objects.create` sites (`test_withdraw_deletes_user_login_tokens` ×2, the unclaimed-token no-op case, `test_decline_preserves_login_tokens`, the rollback case, `test_withdraw_idempotent`) | writes rows **directly**, never through `issue_token`, never redeems | **UNCHANGED.** A supersession scoped to `browser_binding` cannot match these rows — they carry `browser_binding = NULL` (`G-4g`), and even a bound one would be unreachable without an `issue_token` call |
| 8 | `apps/users/tests/test_consent.py::TestConsentWithdrawIdempotency::test_consent_withdraw_idempotent_on_deleted_user` | one direct `create`; asserts the row **survives** `withdraw_consent` | **UNCHANGED.** B-04 does not touch `withdraw_consent`, and the row's `NULL` binding is out of scope by `G-4g` |
| 9 | `apps/core/tests/test_sweep_login_tokens.py::TestCleanupLoginTokens::_make_token` — 6 call sites | writes rows **directly** with `expires_at` in the past or future and asserts the janitor's counts | **UNCHANGED.** A supersession does not delete, and `cleanup_login_tokens` filters on `expires_at`/`consumed_at`, neither of which B-04 alters |
| 10 | `src/telegram_bot/tests/conftest.py::login_token_factory` and the two direct `LoginToken.objects.create` sites in `src/telegram_bot/tests/test_login.py` | bot-side rows with **no binding**, claimed via `claim_token` | **UNCHANGED and the whole package must stay byte-unchanged.** `git diff --stat -- src/telegram_bot` must be empty. Their continued passing **is** the proof that the bot needs no change — which is why no bot-side test is added |
| 11 | `apps/users/tests/test_login_token.py::TestConsumeToken` (6) · `TestClaimConsumeAgreement` (4) · `_make_token` (13 call sites) | writes rows **directly**, bound to `_BROWSER_ID`; never calls `issue_token` | **UNCHANGED and green.** None of them can be affected by an issue-path write |
| 12 | `apps/users/tests/test_consent.py::TestLoginStatusNoPii::test_login_consume_no_raw_telegram_id` | asserts `"tg_" in caplog.text` and no raw `telegram_id` in the logs | **UNCHANGED — but it is the tripwire for the new log line.** `issue_token`'s supersession log must carry **no `telegram_id`, no raw token and no raw browser id**; a binding-digest prefix and the `token_hash` prefix only, matching the module's existing discipline. This test does not run `issue_token`, so it will not catch a violation — the Implementor must self-check |
| 13 | `apps/users/tests/test_login_token.py::TestLoginHandshakeOwnership::test_consent_view_has_no_token_logic` · `test_bot_handler_has_no_raw_sql` | structural: `consent.py` contains none of `hashlib`, `secrets`, `LoginToken`, `UPDATE login_tokens`, `.update(consumed_at=` | **UNCHANGED and UNEDITED.** It is the constraint that forces the write into `login_token.py`. **Read this before writing the ORM call:** the supersession is spelled `.update(consumed_at=…)`, which contains one of the five forbidden literals verbatim — legal in `login_token.py`, forbidden in `consent.py`. Do not "tidy" the write into the view, and do not add a `LoginToken` model import there |
| 14 | `apps/core/tests/test_login_issue_template.py` (3) · `apps/users/tests/test_admin_pii_containment.py` · `apps/ads/tests/test_auth_nav.py` · `apps/cabinet/tests/test_cabinet_sections.py` · `apps/core/tests/test_contact_rate_limit.py` | render / redirect / rate-limit / admin-list assertions; none issues twice expecting liveness | **UNCHANGED and green.** No template is touched, so `djlint` is not required |
| 15 | `apps/core/tests/test_scheduler.py::TestSchedulerConstants::test_hourly_commands_match_spec` | exact `==` list assertion on `HOURLY_COMMANDS` | **UNCHANGED.** B-04 adds no management command and no scheduler entry; the count stays exactly 9 |

**The five new tests**, all in `apps/users/tests/test_login_token.py` (a new sibling class next
to `TestIssueToken`, or inside `TestIssueToken` — either is fine, but **one** of them must be
reachable without HTTP so it cannot pass for the wrong reason):

| New test | Red if… |
|---|---|
| `test_second_issue_supersedes_the_first` | the supersession is removed **or** narrowed (asserted through **both** `claim_token` and `consume_token`, never a raw SQL count) |
| `test_second_token_stays_claimable_and_consumable` | the write is placed **after** the `create` (`G-4e`) — this is the only test that catches the ordering error |
| `test_issue_does_not_supersede_another_browser` | the predicate loses its `browser_binding` conjunct |
| `test_supersession_does_not_touch_a_claimed_token` | `telegram_id__isnull=True` is dropped (`G-4d`) |
| `test_supersession_ignores_null_bindings` | an `OR browser_binding IS NULL` disjunct creeps in (`G-4g`) |

**Baseline, recorded so a regression is distinguishable from the starting state:** at `a0bd928`,
`test_login_token.py` + `test_login.py` + `test_deletion.py` +
`test_sweep_login_tokens.py` + `test_consent.py` = **114 passed in 92.74 s**. That run used
`PYTEST_OPTS`, which **replaces** the xdist defaults, so it was single-process. **The fast gate
keeps `-n 4`.**

### E.6 `B-07` — the test ledger (2026-10-02, `B-07` Planner): **6 new, 0 changed, 0 deleted**

**`B-07` breaks this section's governing rule in form only, and the break is deliberate.**
Every other block's ledger is a list of *rewrites* — a production change and the test edits
that follow it, in one commit. **`B-07` has no production change, so its ledger is 6 tests
that assert the current, DEFECTIVE behaviour on purpose.** They are **red-to-green
specifications for phase 15's `15-AUTHZ-001`**, not regression guards, and each must be
written so it goes **red** the moment someone fixes the gap. **A known-gap test written to
keep passing after a fix has destroyed its only purpose.**

**A named known-gap test has three mandatory properties. Missing any one is a defect:**

1. It asserts the **defective** behaviour, not the desired one.
2. Its **docstring names the gap, the owner (`15-AUTHZ-001`) and the gate** (`G-A`/`G-7b`/
   `G-D`/`G-E`) that produced the decision — so a reader six months from now knows it is a
   record, not an oversight.
3. It is **not vacuous**: `client.force_login()` creates a real `django_session` row, and it
   does so **after** the fixture has set account state. Log in **first**, mutate the flag
   **second**, and assert the session was genuinely live before asserting it survived.

**The inventory.**

| # | Test | Module | Gap pinned | Red when |
|---|---|---|---|---|
| 1 | `test_ban_leaves_the_banned_sellers_session_usable` | `apps/moderation/tests/test_moderation_views.py` (new `TestBanUserSessionKnownGap`) | `G-A`/`G-D` | a session-revocation mechanism lands |
| 2 | `test_ban_does_not_log_out_the_moderator` | same class | `G-D` — the wrong-target trap | someone adds `logout(request)` to `ban_user` |
| 3 | `test_banned_seller_can_still_reach_the_dashboard` | same class | `G-A` | phase 15's gate lands |
| 4 | `test_banned_seller_can_archive_and_reactivate_an_ad` | `apps/ads/tests/test_edit.py` (new `TestBannedSellerRelistKnownGap`) | `G-A` — **the concrete harm** | `ad_edit`/`ad_reactivate` gain a state check, **or** `auto_moderate` starts reading `is_banned` |
| 5 | `test_consent_decline_keeps_the_session_and_is_reversible` | `apps/users/tests/test_consent.py` (new `TestConsentDeclineSessionKnownGap`) | `G-7b` — the one-way door | a decline logout is added |
| 6 | `test_withdraw_consent_leaves_other_sessions_intact` | `apps/users/tests/test_deletion.py` | `G-A` — `consent_withdraw` flushes only the current session; the other keeps ≤50 raw search queries | multi-session revocation lands |

**Test 4 is the block's highest-value deliverable and the only one that changes a confidence
level.** The Researcher's claim — *a banned seller can archive an ad, re-post it, and
auto-moderation can return it to `PUBLISHED`* — was MEDIUM confidence because **it was never
executed end to end**. Test 4 executes it: real `ad_archive`, real `ad_reactivate`, **real
(unmocked) `auto_moderate`**, on a `PUBLISHED` ad owned by a seller with `is_banned=True`. The
whole value of the test is that `auto_moderate` is not mocked and does not read `is_banned`.
Assert on the ad's **final status**, never on moderation internals.

**`B-07`'s tests that must NOT be written** — recorded so the omission is traceable and not
re-derived as an oversight: `test_consent_decline_flushes_the_session` and
`test_anonymous_decline_is_unaffected` (both `G-7b` = (a) only); and
`test_withdraw_consent_action_is_registered` (`G-B` = do-not-register). **Nor may any test
assert the *absence* of `withdraw_consent_action`** — that pins a decision as an invariant and
would have to be deleted the moment phase 06 reverses `G-B`.

**`B-07`'s tripwires — unchanged, unedited, green (5).** Four are already in `E.3`
(`test_bulk_ban_users_not_locked`, `TestConsentWithdrawIdempotency`, `TestCanLogin`,
`TestConsentBannerGuard`). **`E.6` adds the fifth, and it is the one that matters most here:**

| Tripwire | What it enforces | Why it is `B-07`-specific |
|---|---|---|
| `apps/moderation/tests/test_moderation_views.py::TestModerationReviewLocking::test_ban_user_uses_select_for_update_and_atomic` | `inspect.getsource(review.ban_user)` contains `"transaction.atomic"` and `"select_for_update"` | **it is a substring check, so it would NOT notice a wrong-target `logout(request)` added to `ban_user`.** Together with `TestBanUserView`'s four tests that makes **five** tests blind to the trap — which is why known-gap test 2 exists. Add this row to `E.3`; it was not previously listed |

**`B-07` changes no existing test, and this is the ledger's other half:** the entire
`B-07` diff is **additive test code plus plan text**. `git diff --stat -- src/` must list
**only** test files.

**`G-F`'s forward-declared migration, for `E.5`'s and `E.1`'s authors to note:**
`test_banner_hidden_for_deleted_user` is currently in `E.3` as a tripwire. **It is a tripwire
today and a migration for phase 15** — its assertion (`GET /dashboard/` → `200` for a
soft-deleted user) is the defect. `B-07` leaves it green; `15-AUTHZ-001` rewrites it in its
own commit. **Do not treat its eventual redness as a `B-03`/`B-04` regression.**

**Baseline at `9ef5151`:** the six files above = **136 tests**; `test_consent.py` alone is
**exit 0**. Two runs of the full set at the same HEAD with no code change between them gave
**2 failures then 0** — `TestLoginStatusNoPii::test_login_consume_no_raw_telegram_id` and
`::test_login_unbound_refusal_logs_no_pii`, both `assert None is not None` at the
`claim_token(...)` call. **That is the `E.4` test-DB flake, not a code regression** — nothing
in `B-07`'s diff touches `claim_token`, `login_issue` or `issue_token`, and the file is green
in isolation. **`test_search_at_seed_volume_meets_slo` is a wall-clock SLO test and is not a
finding. Keep `-n 4` on the fast gate.**

### E.7 `B-06` — the test ledger (2026-10-02, `B-06` Planner): **3 new, 0 changed, 0 deleted**

| File | Tests | Status | Why it is here |
|---|---|---|---|
| `src/backend/config/settings/tests/test_password_recovery.py` | `test_documented_password_change_procedure_works`, `test_documented_procedure_refuses_a_policy_violating_password` | **new module** | **These two are the block's entire evidence base.** Test 1 *executes* the documented procedure against a real user through `call_command("changepassword", …)` with `getpass.getpass` patched in the command module, then asserts `check_password(new, user.password)` and that the stored hash changed — the procedure is run, never pattern-matched. Test 2 supplies a value failing `AUTH_PASSWORD_VALIDATORS` and asserts `CommandError` **plus** a byte-identical hash, which is what pins `G-6g`'s tightening claim: `changepassword` refuses values the old raw-`set_password` recipe accepted |
| `src/backend/config/settings/tests/test_settings_secrets.py` | `test_prod_requires_email_host` | **new** | The anti-vacuity gate for the `prod.py` comment correction. **It does not exist today and must go in this file, not in `test_settings_defaults.py`** (a plan correction): the file already owns the `_prod_env_overrides` helper and the subprocess-import harness, and `test_redis_url_required_in_production` *sets* `EMAIL_HOST="smtp.example.com"` merely to get past the guard. **It must set only `EMAIL_HOST=""` with every other guard satisfied, and assert stderr names `EMAIL_HOST`** — a bare `ImproperlyConfigured` is satisfiable by the `SITE_URL` guard and is not a test |

**Changed: 0. Deleted: 0.** Verified: grepping `src/` for `Reset password|Set password|\.\./password/|auth_user_password_change|password_change`
returns only `has_usable_password` and `make_password(None)` — **no existing test encodes the dead-button
state**, so no design required weakening or deleting a test.

**Tripwires — unchanged, unedited, green (4):**

| Tripwire | What it protects for `B-06` |
|---|---|
| `apps/users/tests/test_admin_change_form.py::test_add_view_stores_a_hashed_password` | **must not be affected by any change** — `B-06` adds no admin URL, no form and no `get_urls`, so the add view is untouched. Its siblings (all six, incl. the two moderator-cannot-escalate tests) are the standing proof that `B-01`'s field contract is intact |
| `apps/ads/tests/test_i18n_completeness.py` | the i18n gates (`test_template_extraction_coverage`, `test_no_empty_msgstr`). `B-06` introduces **no** msgid and edits **no** `.po`; it also writes no project template under `src/backend/templates` (the gate's only scan root, with `admin/` excluded), so Django's shipped password templates stay invisible to it |
| `apps/core/tests/test_create_admin_user.py` | pins the **idempotent skip before any password write** — the very behaviour that makes the runbook's old "re-run `create_admin_user`" alternative a verified no-op. It is the reason `G-6b` can answer YES |
| `config/settings/tests/test_settings_defaults.py` | unchanged; **moved off the `B-06` surface** by correction 5 — `EMAIL_HOST` lives in `prod.py` and its guard harness is `test_settings_secrets.py` |

**`B-06`'s `src/` diff is not test-only, and the difference from `B-07` is deliberate:** it is
`apps/users/admin.py` **docstring only** (`G-6i`). No behaviour, no URL, no form, no template. The
Validator's §F.1 check therefore has a different shape for `B-06` than for `B-07`: there is no
red-to-green gap test to write, because **asserting the button's 404 would pin a decision as an
invariant** — the very anti-pattern §E.6 forbids. The gap's record is the runbook sentence plus the
docstring plus the known-gaps table, all three owned by phase 15 `15-AUTHZ-003`.

**Superseded by this row, and not edited (outside this Planner's surface):** §F.2 row 13 and §G.1's
`B-06` row still read *"test 1 green … i18n green if option (a)"*. With `G-6` closed as (c)+(b) and
(a) deferred, **the authoritative statement is `### B-06` + this row.** `apps/search/tests/test_search_slo.py::…::test_search_at_seed_volume_meets_slo`
remains a known wall-clock non-regression, and the fast gate keeps `-n 4`.

### E.8 `B-10` — the test ledger (2026-10-02, `B-10` Planner): **5 new, 0 changed, 0 deleted**

**Governing rule, unchanged and binding: the production diff and all five test diffs land in
the SAME commit.** The spec edit is a **separate, second** commit — it follows no test.

**Re-derive before editing. Do not trust any count in this document, including this one:**

```
Select-String -Path src/backend/config/settings/tests/*.py,
                         src/backend/apps/users/tests/*.py,
                         src/backend/apps/core/tests/*.py,
                         src/backend/apps/search/tests/*.py
             -Pattern 'SESSION_COOKIE_AGE|SESSION_SAVE_EVERY_REQUEST|set_expiry'
```

Expect **zero** hits. `B-10` claims no existing test, because it modifies no existing
behaviour — and `C-B10-2` is *why* that is knowable in advance rather than discovered.

| File | Tests | Status | Why it is here |
|---|---|---|---|
| `src/backend/config/settings/tests/test_session_policy.py` | `test_session_lifetime_is_declared_in_base`, `test_declared_age_bounds_a_real_sessions_expiry`, `test_authenticated_session_is_written_once_at_login_and_never_refreshed`, `test_anonymous_session_is_refreshed_by_each_recorded_search`, `test_no_per_session_expiry_override_exists` | **new module** | **The block's entire evidence base.** A **new module in `config/settings/tests/`**, not an extension of `test_settings_defaults.py` (which owns the transport-tuple and staticfiles harnesses — a different subject) and not in `apps/users/tests/` (two of the five are settings-declaration tests and the production diff is a settings diff). Same precedent as `B-06`'s two new modules in the same directory. **The `_THEME_STATICFILES_BACKEND` shape is the template for test 1: assert the resolved value, not the absence of the dead key, because absence passes on a build where the setting silently reverted to the default** — here, `getattr(config.settings.base, "SESSION_COOKIE_AGE")` **is** the "declared, not inherited" claim, because a Django default is not an attribute of the project's own settings module |

**Changed: 0. Deleted: 0.** Three verifications, all run live, that make this knowable
rather than hoped for — each of them is a trap this block would otherwise fall into:

| Check | Result | What it forecloses |
|---|---|---|
| `assertNumQueries` / `django_assert_num_queries` | **zero** call sites in `src/` — the only two matches in the repository are inside the *docstring* of `src/telegram_bot/tests/test_bot_query_count.py`, which states it deliberately does **not** use them | A write-amplification change could not trip a query-count assertion. Moot under `G-10b`, but it is the check that **withdraws** the plan's *"(b) breaks every `force_login`-based test"* claim |
| `SessionInterrupted` | **zero** occurrences in `src/`, and **no test deletes a `django_session` row** and reuses the same client's cookie within a request | The one real mechanism under `SESSION_SAVE_EVERY_REQUEST = True` is not reachable from the suite |
| assertions on the 14-day default | **zero** | **Nothing pins the defect as expected state**, so no design required weakening or deleting a test — and, per `G-10h`, **no new test may pin it either** |

**`B-07`'s six known-gap tests are the standing proof that the authenticated half is
untouched.** They use `force_login` and assert session survival; under `G-10a`'s declaration
(django's own default) and `G-10b` (no flag), **cost 0**. If they ever go red after this
block, that is a real regression, not the declared lifetime — and that is precisely the
signal the block needed: with a declaration in place, "the age changed" becomes
distinguishable from "the age was always this".

**Tripwires — unchanged, unedited, green (7):**

| Tripwire | What it protects for `B-10` |
|---|---|
| `config/settings/tests/test_settings_defaults.py::test_dev_and_test_share_the_transport_tuple` | **`_TRANSPORT_SETTINGS` must stay at exactly SEVEN members.** A session lifetime is **not** a transport setting; the tuple is a `==`-compared dev/test parity contract over TLS controls, and `SESSION_COOKIE_AGE` is a literal that is identical in dev, test and prod by construction. The file is **byte-unchanged** by this block |
| `config/settings/tests/test_env_allowlist_reverse.py::test_consumed_env_vars_are_allowlisted` | `consumed ⊆ ALLOWED_ENV_VARS`. **This is the test `G-10d`'s literal decision keeps green.** Env-driving the age would fail it without an `ALLOWED_ENV_VARS` entry, and would then require up to four `.env.*.example` edits in the same commit, outside this block's surface |
| `config/settings/tests/test_env_allowlist.py::test_example_keys_in_allowlist` | `example keys ⊆ ALLOWED_ENV_VARS`. Unchanged and green — no template edited. (`E.4`'s correction stands: these four template edits are **not** gate-binding, and the literal was chosen on the precedent, not on contention) |
| `apps/core/tests/test_scheduler.py::TestSchedulerConstants::test_hourly_commands_match_spec` | **`HOURLY_COMMANDS` stays at exactly 9.** `G-10f` declines the janitor, so `clearsessions` is **not** registered. **This file is NOT `B-10`'s** — registering the janitor here would break an exact-`==` assertion in a phase-owned file outside the block's surface. `test_daily_commands_include_send_alerts` and `test_all_hourly_commands_are_distinct` likewise |
| `apps/core/tests/test_sweep_lock_structure.py` | Would **not** break either way: the sweep set is pinned to its own explicit expected set and `clearsessions` takes no lock. Recorded so a future editor does not re-derive it — and so nobody uses this as a reason the janitor is free |
| `apps/users/tests/test_login_token.py::TestLoginHandshakeOwnership` (all) | The 300 s `TOKEN_TTL_SECONDS` handshake, end to end, unchanged. **These tests, plus `B-03`'s `test_same_browser_redeems_end_to_end`, are the named regression guard** for `B-10` — the commit body must name them rather than assume the handshake is covered. They are also `E.1`'s structural `test_consent_view_has_no_token_logic` tripwire (`secrets` clause), which `B-10` cannot touch |
| `apps/ads/tests/test_i18n_completeness.py` | The i18n gates (`test_template_extraction_coverage`, `test_no_empty_msgstr`). **`B-10` introduces no msgid and edits no `.po`**, and writes no template — a **positive** finding from `G-10e` condition 4, and one fewer blocker than the plan assumed |

**`src/telegram_bot/` must stay byte-unchanged** — `git diff --stat -- src/telegram_bot`
empty. There is no bot-side session state: the bot's FSM lives in `Ad` rows, and the bot
never touches the web session. Its continued passing is the proof, which is why no bot-side
test is added.

**Baseline.** `B-10` expects **0 changed, 0 deleted, 5 new**.
`apps/search/tests/test_search_slo.py::…::test_search_at_seed_volume_meets_slo` remains a
known wall-clock non-regression and is **not** this block's. The fast gate keeps **`-n 4`**
— the test DB is shared and there is **no single-writer gate**, so **never launch a second
gate while one is running**; that is an execution hazard, not a style note.

---

## §F · Risks for the plan as a whole

### F.1 Standing hazards

| Hazard | Severity | Mitigation |
|---|---|---|
| **Open questions decided in flight.** An Implementor reads a block, finds its gate open, and picks an option from the table because the table is right there | **HIGH** | every option table in §B and §H is headed **"recorded, NOT chosen."** Every block's **Gates** line and its brief's `depends_on` name the gate. §H opens with: *a block with an open gate does not start.* The Implementor has no authority to close a gate |
| **Two phases fixing one defect.** `04-AUT-007` is split in half; phase 15 owns the CSRF half | **MEDIUM** | §D.6 states the phase-15 half explicitly; `B-04`'s scope says "CSRF/GET-writes half (phase 15)" |
| **Lost updates on shared artefacts.** `base.py` has four claimants across this phase and three other phases | **HIGH** | §C.3: one at a time, append-only, never reorder a setting another phase annotated. **Re-read the file immediately before editing and stop on a concurrent change** |
| **A partial block silently counted as complete** | **HIGH** | every block's DoD lists the **named tests** and, where applicable, the **known-gap test** for every reachable-but-unshipped path. `B-07` option (c) is *nothing shipped* and is a legitimate completion only if the record is executable. `B-09`'s deferral under `G-9a` = (ii) is likewise a legitimate completion |
| **A stale reused test DB producing phantom failures** — **new hazard, found by the Auditor** (`U-11`, `C-23`) | **HIGH** | the reused test DB volume had just come out of a PostgreSQL crash-recovery (`invalid record length`); a stale reused schema reported **33 phantom failures**, while the entire phase-04 surface passed **353/353 on `--create-db`**. **The exit condition for every block is the fast gate run with `--create-db` after any DB restart** (see §G). The implementor must not chase a phantom |
| **Stage another agent's work by accident** | MEDIUM | §A.2's rule: `git add <path>` per file, never `git add -A`/`git add .`/`.`, never `git checkout`/`restore`/`stash`/`reset` |
| **A green suite over a non-fix.** The dominant failure mode of `B-03` | **HIGH** | test 1 asserts the *rejection*; `G-1` refuses option A; the phase exit condition requires the `RETURNING` contract to be a **test** |

### F.2 Phase-level risk register

| # | Risk | Type | Sev | Mitigation | Residual |
|---|---|---|---|---|---|
| 1 | A browser-binding design ships green and binds nothing | Security | **High** | `G-1` refuses the non-viable option; test 1 asserts cross-browser rejection **and** that the issuer can still redeem | Low |
| 2 | A wrong nginx directive takes the site down at container start with **no** gate able to detect it | Availability | **High** | the structural test in `test_nginx_config.py`; `nginx -t` if runnable; `G-9b` names the mechanism | Med |
| 3 | A "fixed" `X-Forwarded-For` ships and does not take effect (bind mount, no forced recreate, no reload) | Rollout | **High** | `G-9b`; the commit body names the operator action | Med |
| 4 | Self-inflicted DoS from an empty or wrong trusted-proxy set | Availability | **High** | the peer gate trusts loopback/private **before** the tuple, so an empty or mis-set set collapses rather than bypasses (the tuple is only additive); pinned by `test_public_peer_ignores_x_forwarded_for`, `test_public_peer_ignores_x_real_ip`, `test_public_peer_stays_untrusted_with_trusted_networks_set`, and `TestTrustedNetworksCannotNarrowPeerTrust::test_trusted_networks_cannot_narrow_the_private_peer_trust`, all landing **before** the change | Low |
| 5 | A second authorization gate ships (`B-07`) | Design | **High** | `04-VAL-001`; the Validator's explicit `MIDDLEWARE`/decorator diff check | Low |
| 6 | `04-AUT-004` keeps a HIGH severity after its premise is refuted | Process | **High** | the **Validator** re-bands; the Implementor may not | Low |
| 7 | `04-AUT-006`'s premise is inverted and the plan documents a behaviour the code does not have | Documentation | **High** | **✅ DISCHARGED 2026-10-02 by the `B-10` Planner.** The source plan's option (c) is **dropped** (`C-B10-1`); the expiry is **write-triggered, not sliding**, and **absolute from login for authenticated users**; the honest spec edit ships in `G-10e` stating the number and the population split. The related risk lines are corrected too: *"(b) breaks every `force_login`-based test"* is **withdrawn** (`C-B10-2` — zero `assertNumQueries` call sites, zero `SessionInterrupted` occurrences, no test deletes a `django_session` row) and the `~14,400 rows/IP/day` figure is **separated** into the rejected-`B-03`-options cost and the production **search-path** vector of ≤43,200/IP/day (`C-B10-3`). **The finding is WEAKENED, not closed** (`G-10j`) — a green suite is not closure | Low |
| 8 | A migration-number collision in `apps/users/migrations/` | Migration | **High** | `B-05 → B-03` ordering; the re-check rule in §C.3; never renumber | Low |
| 9 | A comment-only diff is loaded with production changes | Process | Med | `B-11`'s DoD: `git diff --stat` shows exactly one file | Low |
| 10 | Phase-qualifying another phase's audit id produces nine factually wrong references | Documentation | **High** | **removed from the phase entirely** — §D item 14, phase 03 reserves the sweep | **None** |
| 11 | `B-02` leaves the environment with no admin user | Availability | **High** | `G-5` sets the minimum deliberately; the commit body states the number; the rollback names the recovery command | Med |
| 12 | `docker/nginx/nginx.conf` is edited while phase 09 holds the reservation | Conflict | **High** | `G-9a` must close first | Low |
| 13 | An operator rotates a key believing password-reset links expired | Operational | **High** | `B-06`'s DoD requires a **tree-wide search** for surviving claims, not a doc review | Low |
| 14 | An HTMX fragment in the same page turns a new decline test into a 400 | Test | Med | test 1 uses a real navigation, because `consent_decline` ends in `redirect("ads:dashboard")` | Low |

---

## §G · Definition of done

### G.0 The test command every block runs (non-negotiable)

```powershell
$dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'
```

- **After any DB restart — the mandatory form** (the reused volume had just come out of a
  PostgreSQL crash-recovery; a stale reused schema reports ~33 **phantom** failures, and
  the entire phase-04 surface passes **353/353** on a fresh schema — `U-11`, `C-23`):

  ```powershell
  $dc run --rm -e PYTEST_OPTS="--create-db --tb=short -n auto --maxprocesses=4 --dist loadgroup" test
  ```

- **Stale xdist worker shards — not a code regression (2026-10-01, §G execution rule).**
  Shards `test_mko_bazuna_gw0`…`gw3` can survive a crashed run and then collide with
  freshly created permission rows. The signature is a full gate reporting **`3 failed,
  1944 passed, 651 errors`**, dominated by
  `post_migrate → create_permissions → duplicate key … auth_permission_content_type_id_codename_01ab375a_uniq`.
  **Remedy:** drop the stale shards, then re-run with **`--create-db`** once the DB reports
  healthy. Both the Implementor and the Validator hit this **independently** — treat the
  signature as a known artefact, not a code regression, and do not chase it.


- Ordinary iteration when no DB restart occurred:
  `$dc run --rm --env PYTEST_SKIP_MARKERS=seed test`
- Targeted: add `-e PYTEST_OPTS="-k test_name"`. **Setting `PYTEST_OPTS` REPLACES the
  defaults** — it loses `--reuse-db` and xdist parallelism. Never use
  `--override-ini=addopts=`; it strips `--import-mode=importlib`.
- Lint `uv run ruff check <path>` (with `--fix`, which also sorts imports) · typecheck
  `uv run basedpyright <path>` · templates `uv run djlint src/backend/templates/`.
- `uv run pytest` on the host **always fails** — there is no DB on `localhost:5432`.

### G.1 Per-block exit conditions

| Block | Exit condition |
|---|---|
| `B-01` | tests 1–4 green · the four `has_*_permission` bodies and `withdraw_consent_action` byte-unchanged · exactly **one** `fieldsets` declaration on `UserAdmin` at phase exit · `G-4` recorded |
| `B-02` | tests 1–5 green · `test_settings_defaults.py`, `test_env_allowlist_reverse.py`, `test_env_allowlist.py` green · the `ADMIN_PASSWORD` resolution expression and `entrypoint-create-admin.sh` unchanged · `04-VAL-004` recorded |
| `B-03` | tests 1–8 green · `claim_token`'s `RETURNING` matches the model field set **exactly**, asserted by test 8 · the view contains no `secrets`/`hashlib`/`LoginToken`/`"UPDATE login_tokens"` · the bot package byte-unchanged · `LoginToken` still has exactly two deleters · `G-1`, `G-1a`, `G-1b` recorded with authors |
| `B-04` | tests 1–7 green · `test_two_issues_differ` **unchanged** and green · the two `04-AUT-007` paragraphs rewritten in this commit · `LoginToken` still exactly two deleters · `HOURLY_COMMANDS` still exactly 9 · `G-4b` recorded stating whether `04-AUT-007` is **closed** or **weakened with a reason** |
| `B-05` | only the recorded `G-5a` option implemented · `TestCanLogin`'s six tests unchanged and green · `makemigrations --check` clean if the model was touched · `MIDDLEWARE` unchanged at 15 entries · **the Validator recorded a re-banded severity for `04-AUT-004`** |
| `B-06` | test 1 green · **a tree-wide search finds no surviving password-reset claim the code does not support** · the `EMAIL_HOST` guard expression byte-unchanged · i18n green if option (a) · `G-6` recorded |
| `B-07` | the chosen option's tests green and every reachable-but-unshipped path has a **named known-gap test** · `MIDDLEWARE` byte-unchanged at 15 entries · no new decorator in `apps/users` or `apps/moderation` · `test_bulk_ban_users_not_locked` and `TestConsentWithdrawIdempotency` unchanged and green · `withdraw_consent_action` and `bulk_ban_users` **bodies** unchanged — the `G-7` sub-decision on registering the admin action is recorded either way · `G-7`, `G-7b` recorded |
| `B-08` | tests 1–6 green · **exactly one** client-IP implementation exists — verify by searching for `_get_client_ip` and `HTTP_X_FORWARDED_FOR` across `apps/` · **no public peer is trusted unless an operator lists a network containing it** (the tuple is `()` in `base.py`/`dev.py`/`test.py`, undeclared in `prod.py`) · `dev.py` and `test.py` explicit · `test_env_allowlist_reverse.py` green · `G-8a`…`G-8d` recorded |
| `B-09` | the new structural assertion green · the four pre-existing `test_nginx_config.py` tests **unchanged** and green · every `B-08` test still green · `limit_req_zone` keys unchanged · the commit body names the validation actually performed and the `G-9b` mechanism · **if `G-9a` = (ii), the deferral is recorded and the block is closed** |
| `B-10` | tests **1–5** green in the one new module `config/settings/tests/test_session_policy.py`, with **both** the authenticated half (test 3) and the anonymous half (test 4) present · **zero** existing test files modified · tests 2 and 3 assert through a **real request cycle** against the **persisted** `django_session` row · **no test hardcodes 14 days or any literal age** · the two settings are **declared** in `base.py` immediately after `SESSION_COOKIE_SAMESITE` with a comment stating the write-triggered semantics and the population split, and citing `04-AUT-006` cycle-scoped · `git diff` on `base.py` shows **additions only** — nothing pre-existing moved · `_TRANSPORT_SETTINGS` still **seven** and `test_settings_defaults.py` **byte-unchanged** · `HOURLY_COMMANDS` still exactly **9** and `test_scheduler.py` **byte-unchanged** (`clearsessions` NOT registered) · `db-retention.md`, `ALLOWED_ENV_VARS`, `read_env()`, the secret guards, `MIDDLEWARE` (15), `SESSION_ENGINE`, `SESSION_EXPIRE_AT_BROWSER_CLOSE` and every `CSRF_*` setting **byte-unchanged** · `src/telegram_bot/` **byte-unchanged** · **no `.po` and no template touched** · the `B-03` handshake tests re-run and **named in the commit body** · the spec edit is a **separate commit** on a freshly re-read file with no phase-06 content clobbered (**or** the deferred obligation named with its replacement text) · the commit body carries the verbatim *"no behaviour change"*, the `G-10f` `clearsessions` hand-off note and the `G-10i` ingress arithmetic · `G-10a`…`G-10j` recorded with decisions and author |
| `B-11` | the fast gate green · `git diff --stat` shows **exactly one** file · `ALLOWED_ENV_VARS`, `read_env()` and the secret guards byte-unchanged · the tracker decision record cites §D item 14 |

### G.2 Phase-level exit conditions

- [ ] **Every gate in §H is closed or explicitly deferred with a recorded reason.**
- [ ] `04-AUT-001` is **closed with a mechanism**, or recorded as **not closed** with the
      reason. A green test suite is not closure.
- [ ] **`claim_token`'s `RETURNING` list matches `LoginToken`'s field set exactly — asserted
      by a test, not by a comment.** `test_claim_token_returning_matches_model_fields` is
      green.
- [ ] **Exactly one client-IP logic copy exists.** Verify by searching for `_get_client_ip`
      and `HTTP_X_FORWARDED_FOR` across `src/backend/apps/` — not by trusting this document.
- [ ] **`LoginToken` still has exactly two deleters** —
      `users/services/deletion.py::withdraw_consent` and
      `core/management/commands/cleanup_login_tokens.py`. Verify by searching for
      `LoginToken.objects…delete()` and `LoginToken.objects.filter(…).delete()`.
- [ ] **The scheduler entry count is unchanged.** `HOURLY_COMMANDS` has exactly **9**
      entries — `archive_sweep, delete_sweep, consent_hard_delete, sweep_drafts,
      sweep_orphaned_media, cleanup_login_tokens, purge_failed_ads, purge_rejected_ads,
      purge_deleted_ads` — pinned by the exact-list assertion
      `apps/core/tests/test_scheduler.py::TestSchedulerConstants::test_hourly_commands_match_spec`.
      `DAILY_COMMANDS` still `["send_alerts", "rollup_daily_metrics"]`. **No fourth scheduler
      entry was added**, even though free `AdvisoryLockId` members now exist.
- [ ] `TestLoginHandshakeOwnership::test_consent_view_has_no_token_logic` green **and
      unedited**, including its `secrets` clause.
- [ ] `apps/moderation/tests/test_admin_actions.py::test_bulk_ban_users_not_locked` green
      **and unedited**.
- [ ] `config/settings/base.py::MIDDLEWARE` has exactly **15** entries with
      `DbLockTimeoutMiddleware` at position 6.
- [ ] The migration invariant holds: **no existing migration in
      `src/backend/apps/users/migrations/` was edited or renumbered.**
      `0003_logintoken_browser_binding.py` now exists (created by `B-03` as
      required); the next free number is `0004_*`.
- [ ] All **nine** `/login/status/` direct-row tests in §E were re-derived, confirmed
      against the tree, and their changes landed in the **same commit** as `B-03`'s
      production change.
- [ ] No bare `AUT-00N` was written. No marker sweep was performed (§D item 14).
      *(True **by correction**, not by construction: commit `97c86dc` wrote three new bare
      `AUT-007` identifiers at `login_token.py` lines 65, 282 and 295. This closure pass
      phase-qualified all three to `04-AUT-007`, so the condition now holds.)*
- [ ] `ruff` and `basedpyright` clean on every changed Python path; `djlint` clean if any
      template changed; `test_i18n_completeness.py` green with non-empty `ru` and `bs`
      msgstr on every new string.
- [ ] The fast gate was run **with `--create-db`** after any DB restart, and its result
      recorded as such in the phase report.
- [ ] `git status --short .ai` shows no new modifications beyond this plan's own file, the
      pre-existing `.ai/audit/**` deletions and `.ai/tmp/`.
- [ ] Nothing was committed without an explicit user request. No `git reset`, `git
      checkout`, `git restore` or `git stash` was run. No history was rewritten.

---

## §H · Open questions register

> ## A BLOCK WITH AN OPEN GATE DOES NOT START.
> The Implementor has no authority to close a gate. If a block's gate is open, stop and
> report. Every option set below is **recorded, NOT chosen**.

`Q*` = the source plan's questions. `U-*` = the code context's open unknowns. `X-*` = the
code context's contradictions that re-priced an option. Merged and renumbered as `G-*`.

| Gate | Merges | Owning block | Route | If not closed |
|---|---|---|---|---|
| **`G-1`** the login-token binding design | `Q1`, `U-1` | **`B-03`** | ~~Researcher + Planner pre-step.~~ | ~~`B-03` does not start.~~ **✅ CLOSED by the B-03 Planner (2026-10-01) — option `A′`**: a `LoginToken.browser_binding` column (SHA-256 digest) plus a first-party `login_browser_id` **session** cookie, mint delegated to the service. **`A″` and `B` are dominated** — both write a session row on an unauthenticated endpoint bounded at 10/min/IP, i.e. **~14,400 rows/IP/day retained 14 days with no `clearsessions` janitor**, for **zero** extra security because `django.contrib.auth.login` already rotates the key before writing `_auth_user_id`; `A″` additionally pays `A′`'s full migration + `RETURNING` cost and is destroyed by the very `flush()` its own redeem step triggers. **`C` is WITHDRAWN**, not carried as a fallback: it leaves `04-AUT-001` open behind a green suite, which §F.1 names as the block's dominant failure mode. Full rationale in **`### B-03`** |
| **`G-1a`** the absence/legacy policy for a `NULL` binding | `U-2`, `04-VAL-003`, `04-VAL-007` | **`B-03`** | ~~part of `G-1`~~ | ~~the §E tests cannot be rewritten~~ **✅ CLOSED by the B-03 Planner (2026-10-01) — FAIL CLOSED.** A `NULL` binding is **never** redeemable; the refusal is the new `ConsumeOutcome.UNBOUND`, mapped to HTTP **`410`** with a distinct log reason. **The HTTP code does not change** because `users/login_issue.html`'s polling loop branches on exactly `200`/`204`/`410` and does nothing for any other status — so a new status would silently spin the loop to expiry. `410` needs no template change and no new translatable string, and the existing copy (*"invalid, expired, or already used"*) is already honest for a browser-refused binding. **Adding a member to `ConsumeOutcome` is verified safe**: `test_login_token.py` references four members by `is` plus one `.value`, and **no assertion enumerates the members or counts them.** Fail-**open** (and the hybrid "open only for legacy rows") is **rejected** — it restores the exact bypass the block removes, and its only benefit is sparing three `test_login_token.py` assertions, which project rule 2 settles in the other direction |
| **`G-1b`** is the binding durable across the 300 s handshake | — | **`B-03`** | ~~part of `G-1`~~ | ~~`B-04`'s invalidation semantics undefined~~ **✅ CLOSED by the B-03 Planner (2026-10-01) — a session cookie** (`httponly=True`, `samesite="Lax"`, `secure=True`, `path="/"`, **no `max_age`**). Durable for the **entire** 300 s window and unaffected by `auth_login`'s `cycle_key()`/`flush()` (those rotate the *session id*, not the cookie jar). **Deliberately not durable longer**: the bound row lives ≤300 s, so a longer cookie is pure retention with no security value, and `B-04`'s "prior outstanding tokens" also live ≤300 s, so the `B-03 → B-04` edge is fully served. **No clearing on decline** — the cookie is `HttpOnly` essential security state, so `B-03` contains **no `delete_cookie()` call at all** |
| **`G-1c`** preventing a **silent** stale `RETURNING` | — (new; corrects `C-2` and the source plan) | **`B-03`** | **Planner, mandatory for the Implementor** | **✅ CLOSED by the B-03 Planner (2026-10-01).** The plan's risk line is **inverted** and is replaced: `Model.__init__` (`django/db/models/base.py`) pops each **model** field attname in a `try` and falls back to `field.get_default()` on `KeyError`, so a stale `RETURNING` yields a **default-valued attribute and no error** — and a new column never *adds* a `RETURNING` name, so the **bot path silently loses the binding on every claim with a green suite**. `TypeError` fires only in the opposite direction. `strict=True` is vacuous; order divergence is a **consistency** requirement, not correctness. Mechanism: the service exports `RETURNING_COLUMNS` **and builds the SQL from it** (a constant merely declared *beside* a literal would pass the test while the SQL stayed stale), and `TestClaimToken::test_claim_token_returning_matches_model_fields` asserts **set** equality (the silent case) **+ tuple** equality (the order contract, labelled a consistency obligation) **+ a live round trip** whose binding is not `None` |
| **`G-1d`** the test-ownership count | — | **`B-03`** | ~~Planner~~ | **✅ CLOSED by the B-03 Planner (2026-10-01) — SIXTEEN rewrite sites, all in this commit.** Nine was right at `f93e7fb`; `B-05` added three (twelve across `test_login.py` + `test_consent.py`); **four more hide behind `test_login_token.py::_make_token`** and break only because `G-1a` refuses unbound rows. `§E.1`'s governing rule holds: production diff and all sixteen test diffs in **one** commit |
| **`G-1e`** the boundary against phase 15 `15-AUTHZ-004` | — | **`B-03`** | ~~Planner~~ | **✅ CLOSED by the B-03 Planner (2026-10-01).** `B-03` **may** change the **body** of `login_issue` (the `issue_token` call, and binding `render()`'s result so `set_cookie` can run) and the **body** of `login_status` (the `consume_token` call plus one `UNBOUND` branch), and **may** add one import line. It **must not** touch `login_issue`'s decorators, add `@require_POST`, add any `request.method` branch or `HttpResponseNotAllowed` path, change the route/URL name, change `users/login_issue.html`, or add a form. Disjoint regions of the file, so a concurrent phase-15 landing is a textual conflict at worst |
| **`G-1f`** can a cookie-refusing client complete login today? | — (new; the Researcher's precondition for `G-1a`) | **`B-03`** | **verified live against Django 5.2.17** | **✅ CLOSED — and the answer is NO, which is why `G-1a` is fail-closed.** `CsrfViewMiddleware` is in `MIDDLEWARE`; `_check_token` → `_get_secret` raises `InvalidTokenFormat` → `RejectRequest(REASON_NO_CSRF_COOKIE)` → **403**, so a client refusing **all** cookies cannot poll. But CSRF is satisfied by the `csrftoken` cookie **plus** the `X-CSRFToken` header, so a client can accept `csrftoken` while **selectively** refusing or losing a **newly introduced** cookie name (per-cookie enterprise policy, Safari ITP eviction, cookie-jar eviction under storage pressure). **The `NULL`-binding population is therefore NOT purely legacy — it contains live users**, which is precisely why fail-open was rejected |
| **`G-1g`** the `privacy.html` cookie-disclosure obligation | — | **`B-03`** | ~~Planner~~ | **✅ CLOSED PARTIAL by the B-03 Planner (2026-10-01).** Two surfaces ship **in** `B-03`: `docs/02-database/db-schema.md` (the new column — already required by §C.3) and `docs/02-database/db-enums.md` (the `CookieCategory` section's *"(sessionid, csrftoken)"* essential-cookie list). **One surface is deferred**: `templates/privacy.html` needs a `{% trans %}` description → one new msgid → non-empty `ru` and `bs` msgstr → **the three `.po` files are owned by another agent right now**, so the row cannot land. **The work is written out step by step in `B-03`'s `G-1g` and in the brief's `deferred_obligations`, and the obligation is named in the `B-03` commit body** — because **nothing in the repository fails if it is forgotten**: `test_privacy_page_lists_cookies` asserts a hard-coded 5-name **allowlist**, not completeness, and already omits two cookies the table *does* list. **No template and no `.po` file was edited by this Planner** |
| **`G-1h`** re-banding `04-AUT-001`'s stated rationale | — (new) | **`B-03` → `Validator`** | **NOT a gate — an owed action** | **Closed by DECISION (2026-10-01): `G-1` closes on the security argument as it stands; the re-banding is owed, not a precondition.** `F-4` removes **one of three** stated rationales (`Referer`: the token is never in a URL, `login_status` is `@require_POST`, `Referrer-Policy` is set at three nginx locations per file, Django's default `SECURE_REFERRER_POLICY` is `same-origin`) — it does not remove the defect. The raw token is a bearer credential rendered into the page, redeemable by whoever presents it; `login_issue` is a **GET that creates state** and is therefore prefetchable; the live vectors are a **shared device** and a **stolen raw value**. **The remedy is identical under every re-banding that keeps the finding open at MEDIUM or above**, and gating a P0 fix on one sentence's accuracy would trade a closed HIGH for an open one indefinitely — the exact inversion §F.2 row 1 exists to prevent |
| **`G-3`** the `B-01` ↔ `B-05` ordering | `U-4` | **`B-01`, `B-05`** | **Planner pre-step, first thing in the phase** | neither starts. **Fallback if not explicitly resolved:** `B-01` first, `is_active` in `readonly_fields` |
| **`G-4`** the `UserAdmin` form design | the source plan's un-numbered BLOCK-1 question | `B-01` | **Researcher + Planner** | `B-01` does not start |
| **`G-4b`** the invalidation semantics | the plan's own `G-4b`; `C-15`…`C-19` are this Planner's corrections | **`B-04`** | ~~decision gate~~ | ~~`B-04` does not start~~ **✅ CLOSED by the B-04 Planner (2026-10-02) — option (a.2): supersede at issue time, `UPDATE` before `create`, unclaimed only.** (Letters are the plan's: (a) issue-time invalidation, (b) refuse-to-issue, (c) time-bounded, (d) close-on-TTL. The three semantic candidates costed below the block are labelled **b′ / c′ / d′** there.) The **per-user** reading is **withdrawn as non-viable at issue time** (`telegram_id IS NULL`); **(b′) invalidate at redeem time** is **withdrawn as structurally inert** (`claim_token` binds a token to the *claimer*, so a per-user filter never matches an attacker's stolen token); **(c′) account-state transition is already provided** (`withdraw_consent` deletes; ban and decline are refused *and burned* at redeem) and its residual is handed to `B-07` via `G-4j`; **(d′) the TTL argument** is rejected on §F.1's dominant failure mode. Full argument, both sides weighed, in **`### B-04`** |
| **`G-4c`** the verb: burn or delete | — (new) | **`B-04`** | ~~Planner~~ | ~~a third deleter appears~~ **✅ CLOSED — `UPDATE … SET consumed_at`, never `DELETE`.** Reuses an existing column (so no migration), and both `claim_token`'s `WHERE` and `consume_token`'s read guard already refuse a burned row as `GONE`. `LoginToken` keeps **exactly two** deleters |
| **`G-4d`** are claimed tokens superseded too? | — (new; the plan left this "an explicit decision") | **`B-04`** | ~~Planner~~ | ~~an attacker-triggerable kill of an in-flight login~~ **✅ CLOSED — NO. `telegram_id__isnull=True` is required.** A claimed token is mid-handshake (bot claim done, browser polling); burning it kills a login the user already started, and same-site prefetch would then be able to trigger it. This is `B-03`'s `UNBOUND` non-burning rule applied to supersession. Guarded by `test_supersession_does_not_touch_a_claimed_token` |
| **`G-4e`** statement order and the transaction | — (new; `C-19`) | **`B-04`** | ~~Planner~~ | ~~a concurrent issue burns the token being handed out~~ **✅ CLOSED — `UPDATE` **before** `CREATE`; no `atomic()`, and the module must never import `transaction`.** The new row does not exist when the `UPDATE` runs, so it is structurally excluded and no `token_hash !=` clause is needed. `DB-002` holds: `login_token.py` imports `connection` only |
| **`G-4f`** migration / index / `RETURNING` | the plan's "B-04 may add a `db_index`" note | **`B-04`** | ~~Planner~~ | ~~a second migration in a contended tree~~ **✅ CLOSED — NONE of the three.** The write stamps the existing `consumed_at`, so **no migration** (next free number re-verified as `0004_*`; B-04 claims none); **no index** (`EXPLAIN ANALYZE` on the live schema: `Seq Scan`, 0.097 ms, 1 buffer — and the hourly janitor deletes every token >5 min old, so the table holds ~1 h of issuance; verified 0 rows); **`RETURNING_COLUMNS` unchanged**, so `test_claim_token_returning_matches_model_fields` is unedited and `src/telegram_bot/` stays byte-unchanged |
| **`G-4g`** the `NULL`-binding population | `U-2`'s population, from `B-03` | **`B-04`** | ~~Planner~~ | ~~a `NULL` row is wrongly burned, or one browser's issue reaches another's rows~~ **✅ CLOSED — EXCLUDE, deliberately. No `OR browser_binding IS NULL`.** Verified: `browser_binding = <digest>` never matches `NULL` (three-valued logic). A `NULL` row is already never redeemable (`G-1a` → `UNBOUND`), so exclusion loses no control; the disjunct would make one browser's supersession reach across bindings. Bot-factory and pre-`B-03` rows stay the janitor's to reclaim |
| **`G-4h`** `04-AUT-007`'s final band: **closed or weakened?** | — (owed; `C-15` narrows the finding) | **`B-04` → `Validator`** | **NOT a gate on the Implementor — an owed action** | Ship proceeds. The commit body must state the residual verbatim: *a raw token leaked from the same browser profile stays redeemable by a holder of that profile's cookie for the remainder of the 300 s TTL.* `R-16` should be re-run against the shipped predicate. **The Planner does not set the finding's status** |
| **`G-4i`** the prefetch consequence, as product behaviour | — (new; the MEDIUM risk in `B-04`'s table) | **coordinator** | **product acceptance, not a code gate** | Ship proceeds under the Planner's recommendation (**accept**): a prefetched issue supersedes the visible tab's token, that tab gets the existing `410` and one recovery click; a plain reload is unaffected; a cross-site forced `GET` is not a DoS because `SameSite=Lax` withholds the cookie, a fresh binding is minted, and nothing matches. Options, **recorded and none chosen by the Implementor**: (i) accept, (ii) reject and drop the block to option (d), (iii) reject and add a client-visible hint |
| **`G-4j`** proactive deletion of a banned user's pending tokens | the (c) residual | **`B-04` → `B-07`** | **hand-off** | nothing blocks `B-04`. Verified not needed for safety: the redeem-side `can_login` gate already refuses **and burns** every token on the ban and decline paths. `B-04` must not build it |
| **`G-5`** the validator set and the literal-vs-env length | the source plan's BLOCK-2 decision | `B-02` | **Planner**, one recorded line | `B-02` does not start |
| **`G-6`** the credential-recovery option (a)/(b)/(c) | `Q5` | `B-06` | **Planner** | ~~`B-06` does not start~~ **✅ CLOSED by the `B-06` Planner (2026-10-02) — option **(c) + (b) ship; option (a) DEFERRED to phase 15 `15-AUTHZ-003`**. Note the letter collision: §I.4's (a) is *self-service email reset*; the Researcher's (a) is the *admin password-change URL*. **Self-service reset is refused outright** — its eligible population is provably empty (`PasswordResetForm.get_users()` needs `is_active and has_usable_password()`, every seeded user has `make_password(None)`, `withdraw_consent` blanks `email` and nulls `username`), it has no key (`email` is never populated in production and is read-only since `B-01`), it can only ever reach a staff account (`AdminSite.login` is the sole password-consuming entry point, gated by `is_active and is_staff`), and it is untestable with no SMTP. **The admin password-change URL is deferred because it would be the most dangerous surface in the phase shipped by the block with the least authority to review it**: `B-06`'s exit criterion is a documentation criterion, and `15-AUTHZ-003` — which requires a five-identity registry contract test — would inherit an unaudited credential write endpoint. **The dead "Reset password" button therefore survives, by decision, named and owned.** Full argument, the costed phase-15 handoff and the honest bottom line in **`### B-06`** |
| **`G-6b`** does `changepassword` alone satisfy option (c)? | `U-5` | `B-06` | **Researcher** | ~~no runbook may be written; option (c) becomes (c′)~~ **✅ CLOSED by the `B-06` Planner (2026-10-02) — YES, and no `(c′)` is needed.** `changepassword <username>` is positional-username only, has **no `--password` flag**, reads via `getpass.getpass` (so the secret never reaches argv — cleaner than the `ADMIN_PASSWORD` alternative this block had recorded), calls `validate_password(p2, u)` against the **persisted** user, then `set_password` + `save`. No project override exists. **One limitation to document, not code around:** it selects on `USERNAME_FIELD = "username"`, so a row whose `username` was nulled by `withdraw_consent` is unreachable — and such a row has no usable password and no `telegram_id`, so it cannot authenticate anyway. **Trap for the Implementor:** the command is interactive, so the documented `docker compose run --rm web …` must **keep the TTY (no `-T`)** and should use `/opt/venv/bin/python`, not `uv run` (a one-shot `run` container can fail with a read-only `/opt/venv`) |
| **`G-6c`** (new) = `G-1` — who may use the admin password-change view, if (a) ever ships? | the moderator→superuser takeover | **`B-06` → phase 15 `15-AUTHZ-003`** | ~~Planner~~ | ~~phase 15 re-derives the gate under time pressure~~ **✅ CLOSED by the `B-06` Planner (2026-10-02) — option (i), DEFER, which is precisely why (a) is not in this block.** Answered in advance so phase 15 cannot ship it ungated: option (iii) — reuse `has_change_permission` unchanged — is **rejected outright** (a plain `is_staff` moderator POSTing a valid password onto a superuser's row returns `302` and the credential changes; `B-01` exists to deny privilege writes on `UserAdmin`). If phase 15 overrides and ships (a), the gate is option (ii): `request.user.is_superuser`, **in one named predicate method, not inline** — because `ModelAdmin.get_urls()` has **no `permissions` hook**, so a view-body guard is invisible to `get_permissions`. **Residual of (ii), stated honestly:** it is a fifth local predicate that `15-AUTHZ-003`'s registry contract test must discover and reconcile. Full record in **`### B-06`** |
| **`G-6d`** (new) = `G-2` — ship `set_unusable_password`? | the non-staff reach of (a) | **`B-06` → phase 15 `15-AUTHZ-003`** | **Planner**, one recorded line | nothing blocks `B-06`; binding on phase 15. **KEEP it — no form subclass.** It is granted free by `AdminPasswordChangeForm` via `usable_password=false`, and the reach is bounded: `create_admin_user` is the only production writer of `is_staff=True`, so a credential on a non-staff row grants **no** admin access. The residual harm is **revoking a staff credential without the old password** — a legitimate incident-response action and the only in-UI credential-revocation primitive. Removing it costs a form class (rules 4/7) and buys nothing. The `G-6c` superuser-only gate is what makes it safe |
| **`G-6e`** (new) = `G-3` — repair the 404 or remove the button? | the dead rendered control | **`B-06` → phase 15 `15-AUTHZ-003`** | **Planner**, one recorded line | nothing blocks `B-06`. **NEITHER, and this is a decision, not a deferral of the question.** Repairing *is* option (a) — deferred. Removing it means forking Django's `auth/widgets/read_only_password_hash.html` into project templates purely to delete a link (it would not even trip the i18n gate, since the override carries no `{% trans %}`, but it would rot silently against Django upgrades) and would delete the very control phase 15 needs working. **`B-06` touches neither the widget, the form, nor the template** |
| **`G-6f`** (new) = `G-4` — the doc scope | the false claims | `B-06` | **Planner** | **✅ CLOSED — SIX statements in FOUR files, not five in three:** `config/settings/prod.py` ×2 (`EMAIL_HOST` guard comment; `EMAIL_BACKEND` pin comment, phase 02's surface — **reword in place, never moved**), `docs/ops/docker-deployment.md` ×3 (the `DJANGO_SECRET_KEY` env-table row, § *Rotating Secrets* step 4, the fail-fast table's closing paragraph), and `docs/ops/rollback.md` ×1 — **the row the audit missed**. Plus the broken § *Password Change* recipe. Honest replacement in all six: **"all signed tokens (sessions and CSRF tokens)"** — a Telegram `LoginToken` is a DB row with a `token_hash`, not a signed token. `docs/99-agent/architecture.md` was checked and needs **no** edit |
| **`G-6g`** (new) = `G-5` — replace the recipe with `changepassword`? | the operator's runbook | `B-06` | **Planner**, one recorded line | **YES — and the two wrong alternatives are deleted, not supplemented.** Delete the `make shell` block (bash, not a Django shell) and delete the re-run-`create_admin_user` alternative (a verified no-op: `create_admin_user` returns before any password write when `telegram_id` exists). **What this means for an operator who already set a password under the old raw-`set_password` recipe: that recipe bypassed `AUTH_PASSWORD_VALIDATORS`, so the stored credential may be too short, a common password, or built from the username. `changepassword` will REFUSE until a policy-compliant value is supplied — the intended tightening — and a weak credential already in the database stays weak until the next change.** The runbook must say exactly that, or the refusal reads as a broken command. Test 2/3 pin it |
| **`G-6h`** (new) — the i18n posture for a future (a) | the latent `.po` gate failure | **`B-06` → phase 15** | **Planner**, one recorded line | nothing blocks `B-06`; **binding on phase 15**. **Plain English literals, no `gettext`, in a ported view.** No gate scans Python for `gettext` today, but a future `makemessages` extracts the new msgids into the project catalogs with empty `ru`/`bs` msgstr and `test_no_empty_msgstr` then fails on `.po` files this phase must not touch. Correction to the Researcher's finding 10: the shipped catalogs are **per-app** (`contrib/admin/locale`, `contrib/auth/locale`), and coverage is **partial** — `Password changed successfully.`, `Password-based authentication was disabled.` and `Conflicting form data submitted…` are absent in **both** `ru` and `bs`, and `Reset password`/`Set password` are absent in `bs`. **Still zero project `.po` edits and zero gate breaks.** `gettext` without `.po` entries is exactly the latent failure this avoids |
| **`G-6i`** (new) = `G-7` — the `UserAdmin` docstring | the class's own record | `B-06` | **Planner**, one recorded line | nothing blocks `B-06`. **Update it in the same change — docstring only.** Append that `ReadOnlyPasswordHashWidget` renders "Reset password" → `../password/`, which 404s because `password_url` is injected only by `django.contrib.auth.admin.UserAdmin.render_change_form` and this class declares no `get_urls()`; that the button **did not exist before `B-01`**; and that the gap is owned by phase 15 `15-AUTHZ-003`. **Correction to the Researcher's finding 3:** the "destructive illusion" framing describes the **pre-`B-01`** writable `CharField` (plaintext written verbatim, `has_usable_password() == True` yet permanently unloggable) — **the dead button is a new artifact `B-01` introduced**, the only new harm it caused, and an independent reason to treat it as more than cosmetic. Severity stays **LOW** |
| **`G-7`** the session-revocation option (a)/(b)/(c) | `Q7` | **`B-07`** | ~~decision gate~~ | ~~`B-07` does not start~~ **✅ CLOSED by the B-07 Planner (2026-10-02) — option (b), re-scoped to ZERO production code.** Options (b) and (c) collapse into one shape once the reachability correction lands: there is no path where adding a `logout()` is correct. **The reachability count is 1 of 5 open paths, not 3** — the plan's 2026-10-01 `C-17` correction was itself wrong: `moderation/views/review.py::ban_user` does have a `request`, but it is `@staff_required` so `request.user` is **the moderator**, and the changed identity is `ad.user`; `django.contrib.auth.logout(request)` has **no target-user parameter**. So "has a `request`" is satisfied and the change is still impossible. Full argument, the five gates this opened, and the resulting zero-code scope in **`### B-07`** |
| **`G-7b`** `Q8` — the decline-path logout | `Q8` | **`B-07`** | ~~HARD gate on the decline path only~~ | ~~`consent_decline` is untouched~~ **✅ CLOSED by the B-07 Planner (2026-10-02) — option (b): `consent_decline` is left untouched, and NOT merely deferred.** The plan and the code context both recorded only the weak reason (*"it pre-empts phase 06 `PII-105`"*). **The decisive reason is stronger and code-verified: decline + `logout()` is a PERMANENT ONE-WAY DOOR.** `can_login(is_declined=True) is False` (pinned by `TestCanLogin::test_declined_user_cannot_login` **and** `::test_banned_and_declined_cannot_login`); the only production writer of `is_declined = False` is `give_consent`, reachable only from an **authenticated** `consent_accept`; `consent_accept` is anonymous-accessible and an anonymous POST performs **no DB mutation**. So after decline+logout the user cannot log in and cannot clear the decline. The harm it would buy is near-zero — a declined user is **self-restricting** (`decline_consent` already sets `ads_auto_publish=False`, and listings already filter `user__is_declined=False` live). **Revisit only if `PII-105` makes DECLINE reversible AND restores web login for a declined user** |
| **`G-A`** (new) is the decode-scan revocation service in or out? | — | **`B-07` → `15-AUTHZ-001`** | ~~Planner~~ | ~~the ban path ships unrecorded~~ **✅ CLOSED by the B-07 Planner (2026-10-02) — OUT, with a loud named known-gap and a named owner (phase 15 `15-AUTHZ-001`).** The only two mechanisms that could revoke a *banned* user's sessions are an O(live sessions) decode scan and a per-request account-state check, and **both are owned by other blocks**: the scan would run inside `ban_user`'s already-locked window (phase 03 `DB-004`), duplicates phase 15's `15-AUTHZ-001` mechanism, and has no index to make it cheap — `ConsentRecord.session_key` is unindexed **and semantically wrong**, because `auth_login` calls `cycle_key()` on the anonymous→authenticated transition. The per-request check is forbidden here by `04-VAL-001` and is phase 15's by design. **Honest consequence, stated in the finding's own terms: a banned seller keeps a working session and can relist — `ad_edit` and `ad_reactivate` have no account-state check, `ad_reactivate` calls `auto_moderate(ad)` inline, and `auto_moderate` never reads `is_banned`. A ban that lets the seller relist is not a ban.** Severity HIGH, knowingly accepted, `04-AUT-002` **NOT closed** |
| **`G-B`** (new) register `withdraw_consent_action`, or not? | — (closes `G-7`'s mandatory sub-decision) | **`B-07` → phase 06 `PII-107`** | ~~Planner~~ | ~~the operator-erasure decision goes unrecorded~~ **✅ CLOSED by the B-07 Planner (2026-10-02) — DO NOT REGISTER. `src/backend/apps/users/admin.py` is not touched at all, and no test is written.** Reason 1 (the plan's): it is a **new, irreversible** operator capability — PII nulling, user *and* ad soft-delete, `LoginToken` deletion, no inverse — and `has_change_permission` is `is_staff` and ignores `obj`, so both `actions = (...)` **and** `permissions=["change"]` would be mandatory. **Reason 2 (new, and decisive): registering it while `G-A` is out would *increase* `04-AUT-002`'s residual** — the action is moderator-invoked about other users in a `queryset`, so it has the **identical wrong-target problem** as `ban_user`, and it is the one path that erases PII. The real choice is *capability* vs. *capability-plus-a-new-reachable-session-gap*. **Do not assert the action's absence** — that would pin a decision as an invariant. `PII-107` keeps its MEDIUM band and must cite **the decision, not the absence** |
| **`G-D`** (new) where is the `ban_user` wrong-target trap recorded? | — | **`B-07`** | ~~Planner~~ | ~~the trap is left to the next editor~~ **✅ CLOSED by the B-07 Planner (2026-10-02) — as a NAMED KNOWN-GAP TEST in `apps/moderation/tests/test_moderation_views.py`, not handed to the next editor.** A hand-off note is insufficient here because the plan's *existing brief* named that exact `logout(request)` edit in its `changes` block and its `acceptance_criteria` did not exclude it. **The trap is worse than the plan assumed: FIVE tests would stay green, not four** — `TestBanUserView`'s four (each `force_login(staff_user)`, asserting only `status_code == 302` and `seller.is_banned`) **plus `TestModerationReviewLocking::test_ban_user_uses_select_for_update_and_atomic`**, which is an `inspect.getsource` **substring** check and is entirely indifferent to an added statement. This is a **plan correction** (the `ban_user` reachability premise is refuted), not a second mechanism — `04-VAL-001` forbids filing the same mechanism twice |
| **`G-E`** (new) is the missing session janitor re-filed? | — | **`B-07` → phase 12 / `db-retention.md`** | ~~Planner~~ | ~~the janitor is neither shipped nor recorded~~ **✅ CLOSED by the B-07 Planner (2026-10-02) — RE-FILED as a retention/ops finding against `docs/02-database/db-retention.md`; explicitly NOT `04-AUT-002`'s scope.** Mechanism, not convenience: `clearsessions` is discoverable (`django.contrib.sessions` is in `INSTALLED_APPS` and `SessionMiddleware` is in `MIDDLEWARE`, so it needs no new file, no `AdvisoryLockId` and no migration) **but `clear_expired()` deletes only rows past `expire_date`, so it cannot shorten a live session and does nothing for `04-AUT-002`.** And the cost is not zero: `HOURLY_COMMANDS` 9→10 breaks `TestSchedulerConstants::test_hourly_commands_match_spec` and `DAILY_COMMANDS` 2→3 breaks `::test_daily_commands_include_send_alerts` — **both exact-`==`-pinned, in a phase-owned file `B-07` does not own.** `db-retention.md` has **no session row** and would need one |
| **`G-F`** (new) the `test_banner_hidden_for_deleted_user` handoff | — | **`B-07` → `15-AUTHZ-001`** | ~~Planner~~ | ~~phase 15 discovers the rewrite itself, unbudgeted~~ **✅ CLOSED by the B-07 Planner (2026-10-02) — phase 15's migration, named and budgeted.** `apps/users/tests/test_consent.py::TestConsentBannerGuard::test_banner_hidden_for_deleted_user` **encodes the defect**: the `deleted_user` fixture sets `is_deleted=True` **at creation**, then `force_login` + `GET /dashboard/` → **asserts 200**, under a class docstring saying soft-deleted users *"never see the consent banner, even when they briefly pass through a view before any redirect."* **"Briefly pass through a view" is the defect, asserted as expected.** `B-07`'s migration cost is **zero** (no transition ever runs); **a per-request gate turns it red.** `15-AUTHZ-001` must budget the rewrite in its own commit; it is a rewrite, not a deletion, and `test_banner_shown_for_active_user` stays green |
| **`G-8`** the client-IP trust-model shape | — | `B-08` | ~~Researcher + Planner~~ | ~~`B-08` does not start~~ **✅ CLOSED by the B-08 Planner (2026-10-01).** Superseded by `G-8b`…`G-8g`, which answer the same question with the Researcher's verified topology. The plan's own option list was written before `C-6` was established and none of its three options survive it unchanged |
| **`G-8a`** is `consent_record.py`'s fourth client-IP read in scope? | `U-8`, `C-4` | `B-08` | ~~Planner~~ | ~~the phase would ship **two** inconsistent client-IP policies~~ **✅ CLOSED — IN SCOPE.** `record_consent_action` routes its IP through the same helper. **Cost is 0 test rewrites**: `TestAnonymizeIp`'s three tests call `_anonymize_ip` directly and are untouched, and `test_ip_is_anonymized_and_ua_truncated` is **permissive by design** (accepts `None` or any value ending in `.0`; `127.0.0.1` → `127.0.0.0`). **Gain: the latent `AddressValueError` → HTTP 500 is fixed**, because the helper validates before the value reaches `ipaddress.IPv6Address` inside `_anonymize_ip` — a value with no `.` that is not valid IPv6 is currently a 500. **Citation corrected (`B-8e`): the owner is phase 06's `06-PII-107` BLOCK 6 (`Q-D7`), whose file surface names `record_consent_action` and `_anonymize_ip` — NOT `PII-104`, which is the unrelated alert-audience finding.** BLOCK 6 binding constraint 5 (*"`_anonymize_ip`'s behaviour is unchanged"*) is **satisfied by design**: only its input changes, never its body. Blast radius: one function body, one import line, no model change, no migration, no template, no `.po` |
| **`G-8b`** trust model: trusted set / boolean flag / none | `Q2` (**answered** by `C-6`) | `B-08` | ~~Researcher + Planner~~ | ~~`B-08` does not start~~ **✅ CLOSED — PEER-GATED `X-Real-IP`, with a rightmost-untrusted `X-Forwarded-For` fallback.** The gate is **mandatory and load-bearing**: `X-Real-IP` is read, but **only** when `REMOTE_ADDR` is loopback/private (or inside `TRUSTED_PROXY_NETWORKS`). **Trusting `X-Real-IP` unconditionally is the one variant strictly worse than the status quo** — it would replace an attacker-controlled *prefix* (`XFF[0]`) with an attacker-controlled *whole value*, and that is a regression, not a refinement. The gate is what makes (c) safe: `docker-compose.dev.override.yml` publishes `web` on `8000:8000` with nginx behind `profiles: ["use-nginx"]`, so in the **default dev stack Django takes the connection directly** and a direct client can set `X-Real-IP` itself. Through nginx it is unforgeable — `proxy_set_header X-Real-IP $remote_addr` **overwrites** at 9 of 9 sites in `nginx.conf` and 6 of 6 in `nginx.dev.conf`, and **verified: `web` is not published in production** (`docker-compose.yml` publishes only nginx; `docker-compose.prod.yml` adds only `db`). **(a) alone is rejected**: no compose file declares `networks:`, so a literal trusted IP is not operable — and critically, the plan's feared failure mode (an unset set collapsing every client into one bucket) **does not apply here**, because the private-peer half of the gate stays operative when the set is empty, so an empty set **collapses rather than bypasses**. **(b) alone is rejected** as a resolver: a Docker sibling (`bot`, `scheduler`) is also private and is a different principal; (b) is kept as the **gate**. **Failure direction is recorded as a feature**: a future CDN/LB collapses every client onto the CDN's address — a self-inflicted DoS that is immediately visible, i.e. the safe direction. **Known cost, recorded not hidden: in the default dev stack the gate is always open, so dev never exercises the untrusted branch** — unit tests only, and the docs subsection must say so |
| **`G-8c`** env-driven or literal | `D-6` | `B-08` | ~~Planner~~ | ~~if env-driven and unset, `test_env_allowlist_reverse.py` fails~~ **✅ CLOSED — LITERAL `tuple[str, ...]` of CIDRs, default `()`.** Decided on the merits, and the merits changed once `B-8d` was verified: **the four `.env.*.example` edits were never gate-binding** (both allowlist tests are one-directional subset assertions; `test_python_consumed_vars_in_allowlist` is a hardcoded 8-name subset), so the contention argument the plan leaned on **does not exist**. The real reason is that **there is no correct value to put in an env var**: no compose file declares `networks:`, so nginx's bridge subnet is per-deployment, and shipping an operator-facing knob whose correct value cannot be determined from inside the repository is shipping a trap **with a config surface** — and a mis-set value is the self-inflicted DoS the plan itself identifies. Secondary: the `# env-contract:` opt-out is documented for *"not a deployment variable"* and this **is** one, so using it violates the contract in spirit. Tertiary: the invariant that matters — **no public peer is trusted unless an operator lists a network containing it** — is **additive-only** (`()` in `base.py`, `dev.py` and `test.py`, undeclared in `prod.py`, so the shipped gate is exactly `is_loopback or is_private`), so a setting that cannot narrow it is documentation, and documentation belongs in a comment and in `docs/`. **Promotion path named so it is not lost**: env-backing is a follow-up gated on a compose `networks:` declaration giving nginx a stable address |
| **`G-8d`** the setting's name and type | — | `B-08` | ~~Researcher, against installed Django 5.2~~ | ~~a name may shadow a real Django setting~~ **✅ CLOSED — `TRUSTED_PROXY_NETWORKS: tuple[str, ...] = ()`, in `base.py`, `dev.py` and `test.py`.** Verified against installed Django 5.2.17: **no** Django setting concerns client IP, `SECURE_PROXY_SSL_HEADER` governs **scheme** not identity, and nothing in Django reads `X-Forwarded-For` — so the name shadows nothing. The `TRUSTED_PROXY_*` prefix follows the nearest in-repo trust-naming precedent, `CSRF_TRUSTED_ORIGINS`, and deliberately avoids a `SECURE_`/`CSRF_` prefix that would be mistaken for a Django global. **Type is networks, not IPs** (`tuple[str, ...]` of CIDR strings), annotated to match the only annotated settings in `base.py` (`LOCK_TIMEOUT_SECONDS: int`, `_MAX_LOCK_TIMEOUT_SECONDS: int`); membership is `ipaddress.ip_address(peer) in ipaddress.ip_network(cidr)` per request over a 0–2 element tuple — no import-time parsing, no `lru_cache`, no new abstraction (rule 5). **No `StrEnum`**, with the reason recorded: `apps/core/enums.py` holds named *value sets* and a member per network would be absurd; the three limiters use `Final` for keys and caps, and this is one tuple. The trust *mode* has two branches but they are **the algorithm, not a setting**, and a mode that is not configurable must not be presented as if it were. **`_TRANSPORT_SETTINGS` is deliberately NOT extended** — it is a six-member `==`-compared transport-security contract, and a trust-network list is not a transport setting |
| **`G-8e`** (new) where the helper lives | `C-21` (re-derived) | `B-08` | **Planner** — the plan's justification was false | ~~`apps/core/services/` on `site_config.py`'s docstring~~ **✅ CLOSED — `src/backend/apps/core/utils/client_ip.py`.** `B-8c` removed the stated reason: `site_config.py`'s docstring reads *"Used by the web context processor (sync) and the Telegram bot (async)"* and says **nothing** about hosting cross-app shared services. Decided on structure: the helper is a **pure function** (`META` in, `str` out) touching no cache, connection or model, and `apps/core/utils/` has **zero model imports**; `sanitize.py` is the structural template (pure transform over untrusted input, same `Final` + `Args:`/`Returns:` style, same security rationale). `apps/core/services/` holds writers — `contact.py`, `analytics.py`, cached `site_config.py`, and `contact_rate_limit.py` itself. The dependency direction passes either way (`telegram_bot` imports **from** `apps.*`, never the reverse). **`apps/core/utils/__init__.py` is a bare comment with no re-exports**, so there is no re-export decision to make. `apps/core/middleware/` remains a false lead (`MIDDLEWARE` is a pinned 15-entry list, `04-VAL-001`). `apps/users/services/` inverts the dependency. **This path is part of the outbound contract to phase 09's `API-005`** |
| **`G-8f`** (new) is the return value validated? | — | `B-08` | **Planner** — it changes the cache key and must not be implicit | ~~undocumented key-shape change~~ **✅ CLOSED — YES, for well-formedness only.** The chosen value is parsed with `ipaddress` and returned **canonically**, so two spellings of one IPv6 address share a bucket; unparseable ⇒ fall back to the socket peer; socket peer unparseable ⇒ `"unknown"`. The helper **never returns header text verbatim and never raises**. **Canonicalisation changes the key for IPv6 only**, and the three key-asserting tests all use `127.0.0.1`, which canonicalises to itself — so they survive **by luck, not by design**, which is why an explicit IPv6 key-stability test (test 8) is mandatory. **The validator does NOT reject private or reserved addresses**: that is the **gate's** job and it is a trust decision, not a syntax one; rejecting here would make the dev/test path (peer `127.0.0.1` → resolved `127.0.0.1`) fall through and change every key. One place decides trust, one place decides syntax |
| **`G-8g`** (new) is `B-09` mandatory for `B-08`? | — | `B-08` → `B-09` | **Planner** — corrects §C's `B-08 → B-09` hard edge | ~~`B-08` waits for `B-09`~~ **✅ CLOSED — NO. `B-08` is complete and correct on its own.** With the peer gate, the `X-Real-IP` preference and the right-to-left walk, Django is correct against today's `$proxy_add_x_forwarded_for` with **no nginx edit at all**; §C's hard `B-08 → B-09` edge is **superseded by this row**. The reverse was never true: `B-09` landing alone changes nothing, since no Python code reads the header today. `B-09` is **optional hardening**. **And `B-09` cannot currently be delivered, validated or rolled back by this repository's pipeline** — `deploy.yml` never `git pull`s, the nginx config is a **bind mount** so `docker compose up -d` will not recreate an unchanged service, the health gate runs **inside the web container bypassing nginx**, and rollback (`up -d --force-recreate web bot`) **excludes nginx**. No `nginx -t`, no reload path, no `docker compose config` gate exists. That is `B-09`'s problem to solve, **not a reason to delay `B-08`** |
| **`G-9a`** the nginx file reservation vs phase 09 | `U-7` | `B-09` | ~~Planner~~ | ~~`B-09` does not start~~ **✅ CLOSED by the `B-09` Planner (2026-10-02) — `B-09` TAKES **NO** NGINX CONFIG EDIT. The conflict is resolved by NON-CLAIMING, not by negotiation.** Phase 09 keeps both `.conf` files and its BLOCKS 10/11/12, which are the blocks that already carry the `nginx -t`-before-rolling discipline (`09-external-api-remediation.md` §4.4 item 7, rollout gate §8.4). Phase 04 takes only `src/backend/tests/test_nginx_config.py`. Options (i) *"take the header lines"* and (iii) *"phase 09 lands first"* are both **withdrawn**: (i) buys a change that cannot be delivered (see `G-9b`) and changes nothing observable (see `G-9c`), and (iii) requires coordinating with a phase this block does not own. **Recorded, because the deferral is a decision and not an omission:** the two files are **unmodified by phase 04**, and `docs/ops/docker-deployment.md::Client IP Trust Model` stays accurate as written because `$proxy_add_x_forwarded_for` genuinely is still used at all 15 sites |
| **`G-9b`** the rollout mechanism | `U-6` | `B-09` | ~~Researcher + Planner~~ | ~~`B-09` does not start~~ **✅ CLOSED by the `B-09` Planner (2026-10-02) — NO REPO-VERIFIABLE MECHANISM EXISTS, AND THIS IS WHY THE BLOCK DEFERS. All four delivery defects are CONFIRMED, re-verified at `8ecdaba`, and the first is worse than recorded.** (1) **`deploy.yml` cannot deliver the file at all.** `actions/checkout@v4` runs on `runs-on: ubuntu-latest` — an **ephemeral GitHub-hosted runner**, discarded at job end. The production tree is only ever touched by the `appleboy/ssh-action` script, and that script contains **no `git` command of any kind** (verified: no `git`/`fetch`/`checkout`/`pull`/`rsync`/`rclone` anywhere in `deploy.yml`'s script body). So `/app/docker/nginx/nginx.conf` on the host is whatever an operator last placed there. **A committed `.conf` change does not reach production at all — not "may not take effect", but cannot.** (2) **It is a `:ro` bind mount** (`docker-compose.yml::nginx` and `docker-compose.prod.yml::nginx`), so even a host-side file change is invisible to the running container until nginx re-reads it, and `up -d` **will not recreate an unchanged service**. (3) **The health gate cannot see it:** `deploy.yml` runs `docker compose exec -T web curl -sf http://localhost:8000/health/ready/`, i.e. port 8000 **inside the web container, bypassing nginx**. (4) **Rollback excludes nginx:** `up -d --force-recreate --remove-orphans web bot`. **No `nginx -t`, no reload path and no `docker compose config` gate exists anywhere in the repository.** Option (i) *"forced nginx recreate in the deploy path"* is **REFUSED** — `deploy.yml` and `rollback.md` are **not this phase's file surface** and would claim phase 12's. **Chosen: the operator runbook** (mandatory manual steps written out in `### B-09`) **plus a rejection of the `docker compose config` gate** on the established-precedent ground recorded in `G-9e` |
| **`G-9c`** which directive | `Q9` (**answered**) | `B-09` | ~~Researcher + Planner~~ | ~~`B-09` does not start~~ **✅ CLOSED by the `B-09` Planner (2026-10-02) — **NO DIRECTIVE CHANGES**, and the three candidate edits fail for three different reasons. `real_ip` is **verified absent** from both configs and `from docker/nginx/` tree-wide. **(a) `$remote_addr` (`G-9c` a) — REFUSED, it changes nothing observable.** `proxy_set_header X-Real-IP $remote_addr;` is present at **9/9** prod sites and **6/6** dev sites, and `B-08`'s resolver **prefers `X-Real-IP` and returns on it**. Therefore in production **Django never reaches the `X-Forwarded-For` branch at all** — the header this option would change is **dead data on the resolution path**. It would only remove a footgun for a hypothetical future reader, at the price of a 15-location edit with no syntax gate. **(b) the `real_ip` module (option ii) — REFUSED AS ACTIVELY HARMFUL, and this is the strongest single finding in the block.** nginx **is** the first hop (`C-6`: no CDN, no LB, nothing in front of it), so there is **no upstream proxy to trust** and `set_real_ip_from` has **no legitimate value to name** — the only expressible settings are inert or catastrophic. `real_ip_header` alone is inert (nginx's realip module replaces `$remote_addr` only for peers matched by a `set_real_ip_from` entry). `set_real_ip_from 0.0.0.0/0` is **catastrophic and not defence in depth**: it makes every client a "trusted proxy", so `$remote_addr` becomes the client's own `X-Real-IP`/`X-Forwarded-For` value — which **also destroys `limit_req_zone $binary_remote_addr`**, the one control `B-08` declared unforgeable and which **no test in the repository covers**. `set_real_ip_from` with the default `real_ip_header X-Real-IP` is the same catastrophe. **(c) keep `$proxy_add_x_forwarded_for` (option b) — ADOPTED, unchanged.** `B-08`'s right-to-left walk already makes the appending form safe, and the unforgeable header is the one already in place. **`G-8g`'s hazard is therefore recorded as NOT an outstanding risk but as a closed question:** the `real_ip` module is not merely absent, it is now **deliberately absent** and guarded by test `G-9d` #3 |
| **`G-9d`** (new) the executable trust-model gate | `X-14`, `C-7`, `I.10` pt 3 | `B-09` | **Planner** — it is the only deliverable the block has left | ~~the shipped Python half depends on an nginx line no gate can see~~ **✅ CLOSED (2026-10-02) — THREE TEXTUAL TESTS in `src/backend/tests/test_nginx_config.py`, over BOTH `.conf` files, asserting the INVARIANT and never the current value.** This is the block's only code deliverable and it is the inverse of the original plan: the plan wanted an assertion that no location uses `$proxy_add_x_forwarded_for`, which would have to assert the **opposite** of today's config and would therefore **pin the forgeable-but-defended state as an invariant** — the mistake `B-07`'s `G-B` explicitly forbade (*"Do not assert the action's absence — that would pin a decision as an invariant"*). The gate instead pins what makes `B-08` correct. Full design, the three silent failures each test catches, and why a **fourth** test on `limit_req_zone` is deliberately **not** written, are in **`### B-09`** |
| **`G-9e`** (new) a `docker compose config` gate? | `C-7` | `B-09` | **Planner** | ~~a new gate class is needed~~ **✅ CLOSED (2026-10-02) — NO. REJECTED on the repository's own recorded precedent, and because it would catch none of the four defects.** `src/backend/tests/test_compose_contract.py`'s module docstring records a **deliberate** decision to parse each compose file independently with `ruamel.yaml` (*"`ruamel.yaml` performs no Compose merge, so the contract is asserted per file … rather than via a merged `docker compose config` view"*). A shell-out gate would contradict that decision, require a compose binary inside the `test` service, and add runtime for no coverage gain. **Decisively: a merged compose view cannot observe any of `G-9b`'s four defects** — the host tree not being updated from git, the bind mount, the container-internal health gate and the rollback's service list are all invisible to `docker compose config`. The defect lives in the `.conf` **file**, so the gate that earns its keep is textual over the `.conf`. **`ruamel.yaml>=0.19.1,<0.20` is already a declared dependency** (`pyproject.toml`), so the textual gate adds **no new dependency** |
| **`G-10`** the session lifetime | `Q6`, `U-9`, `X-11` | **`B-10`** | **Researcher (COMPLETE) + Planner (COMPLETE)** | ~~`B-10` does not start~~ **✅ CLOSED by the B-10 Planner (2026-10-02) — as `G-10a`…`G-10i`, all nine below.** `U-9` is answered: the project's own documents state **no number anywhere**. The shipped shape is (a) + (c): **declare `SESSION_COOKIE_AGE` and `SESSION_SAVE_EVERY_REQUEST` literally, and correct the spec paragraph** — no behaviour change, no idle window, no janitor, no env var. **`X-11` is refuted as written** (`C-B10-1`): the expiry is **write-triggered, not sliding**, and for authenticated users that means **absolute from login**. The plan's *"(b) breaks every `force_login`-based test"* line is **withdrawn** (`C-B10-2`). The plan's *`~14,400 rows/IP/day on `login_issue`* arithmetic is **refuted and re-attributed to the search path at ≤43,200/IP/day** (`C-B10-3`). Full reasoning, both halves of the population, the five tests, the file surface, the Implementor brief and the honest bottom line in **`### B-10`** |
| **`G-10a`** the lifetime value | `U-9`, `X-11` | **`B-10`** | **Planner** | ~~the block cannot implement a value~~ **✅ CLOSED (2026-10-02) — declare the status quo `1209600` (14 d); the *value* is a named, owned product question, not a code decision.** Options (ii) 7 d and (iii) 24 h are **refused on the costs, not on taste**: re-auth is a **Telegram round trip** for both sellers and staff; a sporadic seller is **not** timed out by 14 days, so a shorter age **creates** friction where none exists; nothing durable is lost (everything is a DB row or a long-lived cookie, and `B-03`'s `login_browser_id` has **no `max_age`**, so it is independent of the age); and **no number is derivable from the tree**, so choosing one would be inventing a product requirement in a code commit. The **declaration is deliverable at any value** and ships now. Owner of the value question: **coordinator / product owner** — known-gap #1, **owed, not open** |
| **`G-10b`** absolute or idle | — | **`B-10`** | **Planner** | **✅ CLOSED (2026-10-02) — option (i): declare the age AND the refresh policy. No idle window.** `SESSION_SAVE_EVERY_REQUEST` is declared `False` deliberately, which makes "a seller is never timed out" machine-checkable. **Option (ii) is refused for a reason stronger than cost: it *increases* exposure.** A login-once seller is identical (idle ⇒ window never moves), while a seller who keeps browsing is **worse** off (every read re-stamps, so the window never closes while active) — and it is exactly the long-lived users whose exposure grows. The genuine anti-theft benefit is a function of the **age**, not the flag. Avoided cost: +1 `django_session` `UPDATE` per non-empty-session response on `/dashboard/`, `/cabinet/`, `/admin/`, `/moderation/**`, plus `SessionInterrupted` |
| **`G-10c`** global flag or targeted `set_expiry` | — | **`B-10`** | **Planner** | **✅ CLOSED (2026-10-02) — NOT APPLICABLE: `G-10b` introduces no idle window, so there is no mechanism to choose between.** Recorded so the question is not reopened silently. Option (iii) is separately refused: **nothing in the tree calls `set_expiry`** (verified), so `_session_expiry` is never set; adding one would itself write into the session dict (a new write at that point) and would introduce a **per-session override silently diverging** from the declared global policy. **Its one live consequence is promoted into the test list:** test 5 pins both facts, so a future targeted `set_expiry` trips a test instead of shipping undeclared |
| **`G-10d`** literal or env-driven | `D-6` | **`B-10`** | **Planner** | **✅ CLOSED (2026-10-02) — LITERAL, in `base.py`.** Decided on the merits. Every comparable bound in the tree is a literal module constant — `TOKEN_TTL_SECONDS: Final[int] = 300`, `RATE_LIMIT_REQUESTS`/`RATE_LIMIT_PERIOD` = 10/60, 30/60 and 60/600 in three services, `_MAX_HISTORY: int = 50`, `DAILY_HOUR_UTC: int = 8`, `LOCK_TIMEOUT_SECONDS`, `SECURE_HSTS_SECONDS = 3600` — and `docs/02-database/db-retention.md` states the rule in the project's own words: *"it is the number that bounds the production lock hold, **so it must not be operator-variable**."* **Env-driving would be the exception, and there is no correct value to put in an env var** because none is derivable from the repository. Gate cost, for the record and **not** the reason: `test_env_allowlist_reverse.py::test_consumed_env_vars_are_allowlisted` (`consumed ⊆ ALLOWED_ENV_VARS`) fails an env read without an allowlist entry, and `test_env_allowlist.py::test_example_keys_in_allowlist` needs a template entry too — **one `ALLOWED_ENV_VARS` line + up to four `.env.*.example` edits in the same commit, all outside `B-10`'s surface**. The `# env-contract:` opt-out is documented for *"not a deployment variable"* and this **is** one. **Promotion path, named so it is not lost:** env-backing becomes defensible only when a product owner supplies a value **and** states the condition under which a shorter one is correct (e.g. staff vs seller) — not a mechanical follow-up. **`_TRANSPORT_SETTINGS` keeps exactly SEVEN members:** a lifetime is not a transport setting |
| **`G-10e`** the specification sentence | `X-11` | **`B-10`** | **Planner** (coordinating with phase 06) | ~~the SPEC-DEVIATION ships with the code half done~~ **✅ CLOSED (2026-10-02) — EDIT § *H. Telegram login behavior (US-S1)*, in this block, in a SECOND commit, with a recorded fallback.** The documentation half is the other half of the defect: leaving *"long idle"* in place leaves the same SPEC-DEVIATION after a green suite, which is §F.1's dominant failure mode in costume. **The contention is real but is not a block, and phase 06's own plan says so** — `06-pii-consent-remediation.md` §5.1 reserves the file and then carves this block out: *"Phase 04 edits only under its BLOCK 8 option (c), and only after checking for a concurrent edit."* `PII-113` targets `spec-index.md` (its BLOCK 2) and phase 06's BLOCKS 4/11/14; the §H *Session* bullet is a different region. Conditions: **separate commit** · **re-read the file immediately before editing and `git status`/`git diff` it** · **stop and report on a concurrent change** — do not merge, do not regenerate · the commit body names the paragraph and the reason. **The source plan's option (c) — "correct the spec to say 14 days of inactivity" — is DROPPED**: the code does not do that. **Fallback, so it cannot be silently dropped:** if a concurrent phase-06 edit is present, ship the `base.py` declaration alone and record the spec edit as a **named deferred obligation** with the replacement text written out, owned by the coordinator. **No `.po` edit under any part of this block** — nothing translatable is added, so `makemessages` extracts nothing and `test_i18n_completeness.py` cannot be affected (a **positive** finding: one fewer blocker than the plan assumed) |
| **`G-10f`** the missing session janitor | `G-E` (`B-07`'s re-filing) | **`B-10` → phase 12 / `db-retention.md`** | **Planner** | **✅ CLOSED (2026-10-02) — DECLINE the re-filing here; it stays where `G-E` put it. The two are independent controls.** `SESSION_COOKIE_AGE` decides when a *live* session dies; `SessionStore.clear_expired()` deletes only rows with `expire_date < now` (verified in `backends/db.py`), so it **cannot shorten a live session** and does nothing for `04-AUT-002` or `04-AUT-006`. Cost of absorbing it is **not** zero: `HOURLY_COMMANDS` **9 → 10** breaks the **exact-`==`**-pinned `apps/core/tests/test_scheduler.py::TestSchedulerConstants::test_hourly_commands_match_spec` — **a phase-owned file outside `B-10`'s surface** — and `docs/02-database/db-retention.md` would need a `django_session` row it does not have. The upside is real but must be claimed honestly: `django.contrib.sessions` is already in `INSTALLED_APPS`, so `clearsessions` is discoverable via `get_commands()` with **no new command module, no `AdvisoryLockId` member, no migration**. **MANDATORY commit-body hand-off note:** the re-filing currently exists **only in the execution plan** — `db-retention.md`'s only three `session` matches are `session-scoped` **advisory locks**, so it has **no `django_session` row** and the re-filing evaporates unless the row and the registration land in one change |
| **`G-10g`** the `B-10` → `B-11` order | — | **`B-10` → `B-11`** | **Planner**, one recorded line | **✅ CLOSED (2026-10-02) — SERIAL, DO NOT MERGE.** `B-11` declares `B-10` a hard dependency (*"annotates the **final** state, so it runs last"*), and an annotation pass that omitted the age would document an **incomplete** policy — the same class of defect `04-AUT-006` is about. `B-03`'s `LOGIN_BROWSER_ID_COOKIE_HOST_PREFIX` is the working append-then-annotate precedent. **`base.py` rule, binding on the Implementor: APPEND-ONLY across `B-02`, `B-03`, `B-08`, `B-10` and `B-11`** — never reorder, move or re-wrap a setting another block annotated; `B-10`'s two lines go **immediately after `SESSION_COOKIE_SAMESITE`**, inside the existing `# Security settings (TLS/SSL ready)` block, so no new heading is created and no existing line moves; re-read the file immediately before editing and **stop on a concurrent change**. `B-11` annotates afterwards and does not move what `B-10` placed |
| **`G-10h`** the test design | — | **`B-10`** | **Planner** | ~~one test that exercises only the anonymous path~~ **✅ CLOSED (2026-10-02) — assert the SEMANTICS (both populations) and the DECLARATION without pinning a number. Three rules.** (1) **Both halves or the test is theatre:** the plan's single `test_session_lifetime_matches_the_declared_policy` would pass without ever touching an authenticated session — the population the finding is about. Test 3 = the authenticated half (`expire_date` unchanged across read-only requests ⇒ absolute from login); test 4 = the anonymous half (`expire_date` strictly later after a second recorded search ⇒ refreshed). (2) **No test may pin 14 days.** Test 1 asserts the setting is declared **in `config.settings.base`** — a Django default is not an attribute of that module, so *presence is the claim* (the `_THEME_STATICFILES_BACKEND` shape). Test 2 satisfies `04-VAL-002`'s required gap with `override_settings` and a small value, so it is number-independent. **The declared value is never written in a test**, so answering `G-10a` later changes one line in `base.py` and no test goes red. (3) **The semantics are asserted through the PERSISTED `django_session` row**, not a session-dict value in memory — which is only *possible* because `C-B10-2` established that no `force_login` test can detect an age change. Plus test 5, `G-10c`'s structural tripwire |
| **`G-10i`** why the janitor is still required | `C-B10-3` | **`B-10` → phase 12** | **Planner**, one recorded line | **✅ CLOSED (2026-10-02) — recorded, with the two ingress numbers SEPARATED.** **`login_issue` creates zero `django_session` rows today** (it only calls `response.set_cookie(...)` for the `login_browser_id` binding; nothing marks the session modified, so `process_response` skips `save()`). The plan's `~14,400/IP/day` is therefore **upheld for what it measured** — the cost the **rejected `B-03` options `A″`/`B`** would have incurred on that endpoint at `login_rate_limit.RATE_LIMIT_REQUESTS = 10` / `RATE_LIMIT_PERIOD = 60` — and **§H.1`'s `B-03` dominance argument stands unchanged**. The number describing **`B-10`'s actual production vector** is different and larger: the **search path**, `apps/search/views/search.py::search` → `record_search_history(..., session=request.session)` on the `user_id is None` branch, at `search/services/rate_limit.RATE_LIMIT_REQUESTS = 30` / `RATE_LIMIT_PERIOD = 60` per IP and only for a non-empty `?q=` ⇒ **ceiling 30 × 60 × 24 = 43,200 anonymous rows per IP per day**, up to ~604,800 resident per IP at steady state from a cookie-refusing client. **The conclusion is what keeps `G-10f`'s re-filing alive: the vector is PRE-authentication and rate-limiter-bounded, not age-bounded, so no value of `SESSION_COOKIE_AGE` removes it** — a shorter age reduces the residue proportionally and is a mitigation, not a substitute |
| **`G-10j`** (new) the `04-AUT-006` disposition | — (owed) | **`B-10` → `Validator`** | **NOT a gate — an owed action** | Ship proceeds. **The disposition text is written out in `### B-10` so the Validator acts on a record:** **`04-AUT-006` → WEAKENED, not closed.** The *declaration* half is closed (the age and the refresh policy are declared and documented; the spec states the number and the population split). The *value* half was never a code defect — it is the undecided product question in known-gap #1. Severity **LOW / SPEC-DEVIATION / P2 stands**, re-worded: the premise *"falls back to the 14-day Django default"* is no longer true. **Do not close it as FIXED** — the exposure window is unchanged and a green suite is not closure (§F.1). The HIGH residual (no per-request account-state gate, no logout-all, a banned seller who can relist) is **phase 15 `15-AUTHZ-001`'s** and is **not** shortened by anything in this block; **a janitor would not help either** — it cannot shorten a live session |
| **`G-11`** the audit-id qualification rule | `U-10` | `B-11` | **CLOSED BY BOUNDARY** — §D item 14, phase 03 reserves the sweep. **No sweep, no qualification.** | nothing; recorded so it is not "helpfully" reopened |
| **`G-12`** / `U-11` — `--create-db` after a DB restart | `U-11`, `C-23` | **every block** | **not a gate — an execution rule** (§G.0) | the implementor chases ~33 phantom failures and reports a green block as broken, or vice versa |
| `Q4` — is `04-AUT-004`'s premise wrong? | `Q4`, `U-3`, `C-22` | `B-05` | **ANSWERED BY THE AUDIT.** Django enforces `is_active` on every authenticated request; the only unmediated path is `login_status` returning 200 plus a session cookie | nothing — but the severity must still be re-banded by the **Validator** |
| `Q2` — which address does Django actually see? | `Q2`, `C-6` | `B-08` | **ANSWERED BY THE AUDIT** — nginx is the first hop | nothing |
| `Q9` — is there a syntax gate? | `Q9`, `C-7`, `X-14` | `B-09` | **ANSWERED BY THE AUDIT, RE-VERIFIED AND SHARPENED by the `B-09` Planner (2026-10-02)** — there is **no** `nginx -t` gate and the deploy health check bypasses nginx, **but** `src/backend/tests/test_nginx_config.py` is a real fast-gate content gate. **Correction to a claim repeated in the block's own prose, and it matters because it was overstated in the block's favour-of-shipping framing:** `test_nginx_metrics_has_proxy_headers` asserts the **directive name as a substring inside the `= /metrics` block** and **never inspects the value**, so `$proxy_add_x_forwarded_for` → `$remote_addr` leaves it **GREEN**. It turns red only on **removing or renaming** the directive, or on changing/renaming the `location = /metrics` key itself. **So it was never a constraint on *which* directive to choose — only on *whether* the header stays.** The four assertions in the module are inventoried per-test in `### B-09`; all four are green today and all four stay green under the chosen outcome | nothing — `Q9` is closed; `G-9d` is the action it produced |
| **`G-3`** — the `B-01` ↔ `B-05` ordering | `U-4` | **`B-05`, then `B-01`** | **✅ CLOSED by the B-01 Planner (2026-10-01) — option (i), `B-05` first.** The old fallback ("`B-01` first, `is_active` in `readonly_fields`") is **withdrawn as unsafe**: `get_form()` derives its field list from `flatten_fieldsets(get_fieldsets(...))`, never from `get_fields()`, so a `fieldsets` entry naming a field the model no longer has raises `FieldError` at form-construction time and **500s every add and every change request** — and `readonly_fields` **does not** protect against that. Choosing (i) makes `B-05` option (B) `RemoveField is_active` safe, so **it stays on the table**. Full resolution, the constraint it imposes on `B-01`'s derivation, and the `is_active` disposition table keyed on `G-5a` are recorded in **`### B-01`**. **Coordinator follow-ups:** §C.1's serial order becomes scenario alpha; §C.3's `admin.py` row becomes unconditional; §G.1's `B-01` row's "exactly one `fieldsets`" wording needs updating for `add_fieldsets` |
| **`G-4`** — the `UserAdmin` form design | the source plan's un-numbered BLOCK-1 question | `B-01` | **✅ CLOSED by the B-01 Planner (2026-10-01) — option A** (`form = django.contrib.auth.forms.UserChangeForm` + explicit `fieldsets`), **plus the add view** via `add_form` / `add_fieldsets` / `get_form()` / `get_fieldsets()` mirroring `django.contrib.auth.admin.UserAdmin`. **Option B withdrawn** on the raw-hash-disclosure ground; **option C withdrawn** as functionally identical to A | nothing — full rationale, the add-view decision, the operator-capability record and the `../password/` 404 decision are in **`### B-01`** |
| **`G-5a`** — the `is_active` option | `Q3` | **`B-05`** | **✅ CLOSED by the B-05 Planner (2026-10-01) — option (A), variant A′: a dedicated `is_active` guard inside `login_status`**, placed strictly after the `User` lookup and strictly before `auth_login` (the view's first session write). **NOT** a new term inside `can_login` — that predicate is publicly re-exported, is a §E.3 tripwire, and a DENY-looking term there would assert a control the project does not own. **Option (B) `RemoveField` recorded as PERMANENTLY UNAVAILABLE** (three blockers: no supported way to `RemoveField` an inherited `AbstractUser` field; `user_can_authenticate`'s `getattr(user, "is_active", True)` would **fail open**; direct attribute access in `ModelBackend`/`PermissionsMixin`/`AdminSite.has_permission` would **500 every `/admin/**` view**). **Option (C) rejected** (honest floor, but leaves an unmediated 200+cookie path permanently documented); **option (D) rejected** (`NamedTuple` shape change, zero bot behaviour change, collides with phase 15's `permissions.py` refactor). **The field is KEPT** — so `G-3` = (i) leaves `B-01`'s `fieldsets` derivation intact and `B-05` creates **no migration**, leaving `0003_*` free for `B-03`. **Honest wording, mandatory in the commit message:** *"no session cookie is issued on a disabled account; the token is still burned, exactly as on the ban and decline paths, so the two-phase handshake must restart"* — **not** *"the account is now protected"*, because `ModelBackend` already 302s on the next request. (**Corrected 2026-10-01 by the Validator:** the original wording's "and no token is consumed" clause was **false** — `consume_token` commits `consumed_at` earlier in the same `atomic()` block, so the token **is** burned. See `### B-05`.) **Phase 15's `is_active` carve-out is SUPPORTED for a corrected reason** (Django-owned, one layer *below* phase 15's gate) and phase 15 needs **no** change. Full decision, the phase-15 decision record, the final test list and the final brief are in **`### B-05`** | nothing |

### H.1 Two gates the code context materially re-priced — read these before planning `B-03` or `B-09`

**`G-1` — RESOLVED 2026-10-01: BLOCK 3 option A was non-viable, and the corrected set is
`A′` / `A″` / `B` / `C`, of which only `A′` survives.** The source plan priced option A as
*session-free* and option B as *session-writing*. The tree refutes that split:
`login_issue` is anonymous, the only backend session write
(`LanguagePreMiddleware._apply_lang_param`) is gated on `request.user.is_authenticated`, and
`SessionBase.session_key` returns `None` until `save()`/`cycle_key()`. **The binding value
for option A is `None` for every anonymous visitor**, so A is **eliminated**, not re-costed.
Among the survivors, `A″` and `B` are **dominated** on a quantified growth vector
(**~14,400 `django_session` rows per IP per day, 14-day retention, no `clearsessions`
janitor, on an endpoint needing no credential — for zero extra security, because
`django.contrib.auth.login` already rotates the key before writing `_auth_user_id`**) and
`C` is **withdrawn** because it leaves `04-AUT-001` open behind a green suite.
**That figure is the cost those options *would* have incurred, and it is UPHELD unchanged
by the `B-10` Planner (2026-10-02, `C-B10-3`): it is bounded by
`login_rate_limit.RATE_LIMIT_REQUESTS = 10` / `RATE_LIMIT_PERIOD = 60` per IP. Note the
distinction, because conflating it is the error this row once invited — `login_issue`
**creates no `django_session` row today**, so this is a hypothetical cost of a rejected
design, not a description of production. The production anonymous row vector is the
**search** path and is **larger** (≤43,200/IP/day); see `G-10i`.
**`G-1` is CLOSED on `A′`.** Full reasoning, the `G-1a`–`G-1h` sub-decisions, the field and
migration shape, and the Implementor brief are in **`### B-03`**.

**`G-9` — BLOCK 7 option (c), "defer the nginx half", is now the *default* outcome rather
than a fallback.** The source plan's option (a) was "ship the Python change with the
correct trust model; the nginx half waits". That is no longer a choice between alternatives:
`G-9a` records a live reservation conflict that phase 09's plan states as *"No other phase
claims them"*, and `G-9b` records a rollout path the deploy workflow does not have.
**If coordination does not close `G-9a`, `B-09` defers and the phase ships the Python half
alone — which is a correct and complete outcome, because `B-08`'s rightmost-untrusted rule
makes Django correct against the current, still-forgeable header.**

---

## §I · Implementation path alternatives

**Nothing below is chosen.** Each table states the trade-offs an Implementor must not
weigh for themselves. Where the code context makes an option non-viable, that is stated
and the option is withdrawn.

### I.1 `B-01` — the `UserAdmin` form contract

| Option | Maintainability | Future evolution | Project convention |
|---|---|---|---|
| **A** — explicit `UserCreationForm` + `UserChangeForm` (or `ReadOnlyPasswordHashField`) | most code; `password` is **removed from `form.base_fields`** under `ReadOnlyPasswordHashField` | fieldsets still freeze the visible set | Django's documented pattern; mirrors what `B-02` will add |
| **B** — `readonly_fields` only | least code; `password` **stays** in the form but readonly | `readonly_fields` grows a `searchable_fields` coupling — **a known Django trap** that this project does not use today | smallest diff; fits `readonly_fields` already being declared |
| **C** — both a custom form and explicit `fieldsets` | most code | the most explicit contract; still freezes the field set | Django's documented pattern |

Common to all three: the **test shape differs**. Under A, test 1's absence assertion holds;
under B it does not, and only the behavioural test (2) is option-independent. **The
Implementor must implement whichever option is recorded and must not write a test whose
shape presumes a different option.**

### I.2 `B-03` / `B-04` — the binding mechanism

**`G-1` is CLOSED on `A′` (B-03 Planner, 2026-10-01).** The row marked **CHOSEN** is the
decision; the rest are recorded so no later implementor re-weighs them. The full argument is
in **`### B-03`**; the two trade-off columns the earlier version left as prose are filled in
below from live measurements.

| Option | Status | Maintainability | Future evolution | Project convention |
|---|---|---|---|---|
| **A** | **WITHDRAWN — non-viable** (`X-13`) | — | — | `login_issue` is anonymous ⇒ `request.session.session_key` is `None` for every visitor |
| **A′** — `LoginToken.browser_binding` column (SHA-256 digest) + a `login_browser_id` **session** cookie, mint delegated to the service | **CHOSEN** | one additive nullable column; one `AddField` migration; one `RETURNING` edit; one `ConsumeOutcome` member; one new predicate in the consume `UPDATE`; **sixteen** test rewrite sites; two doc surfaces; **one deferred** `privacy.html` row (`G-1g`) | survives session flushes and session-key rotation; a future multi-device story can filter on `browser_binding` and add its own index | `LoginToken` already models one handshake; `LoginTokenAdmin` renders **no form** (`has_add_permission`/`has_change_permission` both `False`), so no admin surface appears; the cookie name is exported by its owner and imported by the view, exactly as `consent.py` imports `PREFERRED_CITY_COOKIE_NAME`; the raw-never-stored invariant in `db-schema.md` stays **uniform across the whole table** |
| **A″** — `LoginToken` column + a server-minted session at issue | **REJECTED — strictly dominated** | pays **`A′`'s entire cost** (migration, `RETURNING`, schema contract, `db-schema.md`) **and adds** the session-growth vector | **worse than "not durable longer": destroyed by the very `flush()` its own redeem step triggers** — `login_status` calls `auth_login`, which rotates the key. A binding the redeem step deletes is not a binding | combining `A″` with `B` is meaningless: if a session is written anyway, `B` is simpler |
| **B** — session store (no migration) | **REJECTED — dominated** | smallest diff: it saves the migration and the `RETURNING` edit, and pays **~14,400 `django_session` rows per IP per day** for them. Ingress is bounded at `login_rate_limit_check`'s `RATE_LIMIT_REQUESTS = 10` / `RATE_LIMIT_PERIOD = 60` **per IP** on an endpoint that needs **no credential**; retention is the 14-day default (`SESSION_ENGINE` and `SESSION_COOKIE_AGE` are **unset** in every settings module); `clearsessions` appears **nowhere** in the repository | same flush fragility as `A″`, and the rows accumulate unboundedly | the smallest diff — and the only option that makes `django_session` the largest table in the system |
| **C** — accept absence | **WITHDRAWN — not carried as a fallback** | zero code | leaves `04-AUT-001` **open** | §F.1 names *"a green suite over a non-fix"* as **the dominant failure mode of `B-03`**, and §F.2 row 1 rates it **High**. `C` is admissible **only** as an explicit, loud "not closed" record with a Validator re-banding to *accepted-risk* — **and no such re-banding exists** |

**The single argument that decides `A′` over both session options.** Both `A″` and `B` buy
**no additional security**, because `django.contrib.auth.login` **already** rotates the
session key before writing `_auth_user_id` — `flush()` when a `SESSION_KEY` is present,
`cycle_key()` otherwise. Classic identity session-fixation is therefore **not** introduced
by a pre-login session, so the session row buys nothing a cookie does not, while costing a
janitor-less, unauthenticated, per-IP-bounded write path of **~14,400 rows/day**.

For the invalidation half (`B-04`, still undecided — `G-4b` owns it): **(a)** prior-token
invalidation matches the finding text and is cheapest; **(b)** refuse-to-issue is **WITHDRAWN
— non-viable** (only the hash is stored, so the raw value cannot be re-issued); **(c)**
time-bounding does not deliver "one live token per browser"; **(d)** close by the
`TOKEN_TTL_SECONDS = 300` + hourly janitor argument is the honest floor if (a) is expensive
under `A′`. `B-04`'s invalidation `UPDATE` **must** live inside
`login_token.py` — the view is forbidden `"UPDATE login_tokens"` **and** the `secrets`
import — and `B-04` may add a `db_index` on `browser_binding` if its `UPDATE` filters on it,
in which case `RETURNING_COLUMNS` grows and test 8 must be updated in `B-04`'s own commit.

### I.3 `B-05` — `is_active`

| Option | Maintainability | Future evolution | Project convention |
|---|---|---|---|
| **A** — guard `login_status` | one expression; `can_login` stays a named predicate | the bot's vocabulary still cannot see `is_active` | fits `can_login`'s existing purpose |
| **B** — remove the field | removes a dead concept | forecloses the escape hatch for a compromised moderator account | one migration + 2 write sites; `list_filter` needs no edit |
| **C** — record inert | zero code | leaves the `login_status` residual named, not fixed | honest floor |
| **D** — extend `AccountState` | changes a `NamedTuple` consumed by 2 bot call sites | one vocabulary for both tiers | **conflicts with phase 15's `permissions.py` refactor** |

### I.4 `B-06` — credential recovery

**`G-6`, `G-6b`, `G-6c`…`G-6i` are CLOSED on 2026-10-02 by the `B-06` Planner. The row marked CHOSEN is
the decision; the rest are recorded so no later implementor re-weighs them. The full argument, the
corrections and the phase-15 handoff are in **`### B-06`; the ledger is `E.7`.**

**Read this first: two letterings collide.** §I.4's (a) below is *self-service email reset*. The
Researcher's (a) — the **admin password-change URL** — is a **fourth** option this Planner adds, called
**(a′)** below, and it is the one that was actually on the table as a *build*. Everything in the
`B-06` section after 2026-10-02 uses the Researcher's letters.

| Option | Maintainability | Future evolution | Project convention | Disposition |
|---|---|---|---|---|
| **(a′)** admin password-change URL (`get_urls()` + `user_change_password`) | ~55 lines, 0 templates, 0 URLs to write, 0 msgids; 5 tests | makes the already-rendered button truthful and adds in-UI recovery | **`B-01`'s single field contract stays intact** (the view builds its own `fieldsets`), but it is a **new privilege-granting credential surface** in a **non-authorization phase**, with a **verified** moderator→superuser takeover unless gated, and `get_urls()` has **no `permissions` hook** | **DEFERRED to phase 15 `15-AUTHZ-003`** — costed, gated (`G-6c`) and handed over. Not rejected on merit |
| **(a)** build the reset flow | the largest block in the phase | the capability "actually exists" — for a population that does not exist | **worse than the source plan states**: `EMAIL_BACKEND` is pinned in prod and `EMAIL_*` are phase 02's `CFG-004` surface, so the mail path needs a cross-phase decision first; i18n applies in full; a `config/urls.py` route collides with phase 15 `15-AUTHZ-004` | **REFUSED** — eligible population provably empty, no key, untestable with no SMTP, and it adds a takeover of the admin desk |
| **(b)** correct the claim | comment- and sentence-only | the claim stays correct as the code changes | exactly what `04-VAL-005` asks for | **CHOSEN** |
| **(c)** document the operator procedure | a small `docs/ops/` addition | survives | superseded: it is `changepassword`, **not** `ADMIN_PASSWORD`-based, and because it prompts it satisfies `D-2`/`D-3` **more** cleanly than the recorded alternative; needs `G-6b` (**YES**, closed) | **CHOSEN** |

**What the CHOSEN rows leave broken, in one line:** the rendered "Reset password" button keeps 404ing,
so credential recovery stays CLI-only — named, owned by `15-AUTHZ-003`, and costed, not hidden.

### I.5 `B-07` — session revocation

**`G-7`, `G-7b`, `G-A`, `G-B`, `G-D`, `G-E` and `G-F` are CLOSED on 2026-10-02 by the `B-07`
Planner. The row marked CHOSEN is the decision; the rest are recorded so no later implementor
re-weighs them. The full argument is in **`### B-07`**; the corrections are in `§H` and
`E.6`. The one thing to read before the table: **`B-07` ships ZERO production code, and that
is the decision, not an omission.**

| Option | Status | Why |
|---|---|---|
| **(a)** ship every reachable `logout()` | **REJECTED** | After the reachability correction — **1 of 5 open paths, not 3** — the only reachable path is `ban_user`, whose `request.user` is the **moderator**. `logout(request)` has no target-user parameter. **There is nothing correct to ship** |
| **(b)** ship what the request already identifies | **CHOSEN, re-scoped to zero code** | `consent_withdraw` was already done. `ban_user` is the wrong target. `consent_decline` is reachable but `G-7b` rejects the fix as a **verified permanent one-way door** (`can_login` refuses a declined user, and `is_declined` can only be cleared by an **authenticated** `consent_accept`). Everything else is recorded as a named known-gap test with an owner |
| **(c)** record only | **SUPERSEDED by (b)** | (b) and (c) are the same shape once nothing ships. The distinction that survives is **whether the record is executable** — and it is: 6 tests, each with an owner-naming docstring, each red when the gap closes |
| **Decode-scan revocation service** *(new — the option the plan never costed)* | **REJECTED — `G-A`** | O(live sessions) with a zlib decompress + HMAC verify per row, inside a window that already holds `Ad.objects.select_for_update()`. No index changes the asymptotics, and `ConsentRecord.session_key` is **wrong**, not slow (`auth_login`'s `cycle_key()` invalidates it). It also **duplicates phase 15's `15-AUTHZ-001` mechanism** — the same window, closed permanently and for free per request. A decode scan is a *worst-case* version of a fix phase 15 will make *unconditionally* |
| **A per-request account-state check** | **REJECTED — forbidden here** | `04-VAL-001`; `MIDDLEWARE` is a pinned 15-entry list; and it is phase 15's `15-AUTHZ-001` by design. **This is the mechanism that actually closes the harm**, which is precisely why handing it to its owner is correct rather than lazy |
| **Register `withdraw_consent_action`** *(the mandatory sub-decision)* | **REJECTED — `G-B`** | A **new, irreversible** operator capability (PII nulling, user *and* ad soft-delete, `LoginToken` deletion, no inverse) that `has_change_permission` — `is_staff`, ignores `obj` — would hand to every staff holder without a `permissions=["change"]` amendment. **And decisively: registering it while `G-A` is out would *add* a reachable session gap on the one path that erases PII**, because the request is the moderator's. The real choice is *capability* vs. *capability-plus-a-new-reachable-gap* |
| **Ship the decline-path `logout()`** | **REJECTED — `G-7b`** | **A permanent one-way door**, link by link. And the harm it buys is near-zero: a declined user is self-restricting — `decline_consent` sets `ads_auto_publish=False` and listings already filter `user__is_declined=False` live. It would close the wrong thing at the cost of a data-loss-class bug |
| **A `StrEnum` revocation reason code** | **REJECTED** | No consumer, no column, no reader. `ModeratorActionType` exists because `ModeratorActionLog.action_type` **is** a stored column; a reason code with neither is an abstraction without justification (rule 5). Warranted only if a **persisted revocation record** is introduced — a migration and a far larger design |
| **A `User.session_epoch` column** | **REJECTED — forbidden here** | Correct, and phase 15's: a migration plus a middleware comparison, i.e. a second gate |
| **Ship the `clearsessions` janitor** | **REJECTED — `G-E`, re-filed** | `clear_expired()` deletes only rows **past** `expire_date`, so it **cannot shorten a live session and does nothing for `04-AUT-002`**. It is a retention control with a different owner. Shipping it would break two **exact-`==`-pinned** scheduler tests in a file `B-07` does not own. Re-filed against `docs/02-database/db-retention.md` (which has no session row) with its cost measured |

**The `on_commit` recommendation, recorded for the phase that does ship a session `DELETE`:**
the repo already does exactly this for the same class of irreversible side effect —
`decline_consent` uses `transaction.on_commit(bump_search_cache_version)`, and
`withdraw_consent`'s media deletion runs through `on_commit` under the comment *"A rollback
must never remove files for rows that remain in the DB."* A session `DELETE` is the same
class. Inside the transaction it would widen an already-locked window (`ban_user_for_ad`
holds `SELECT … FOR UPDATE`; `bulk_ban_users` holds one `atomic()` across every
`log_ban_account` insert — exactly what `03-DB-004` pushed back on). The `on_commit` window
is microseconds, in-process and before the response. **Under `B-07`'s chosen scope this is
moot** — no new session write is introduced — so it is recorded here rather than decided.

### I.6 `B-08` — the trust model

**`G-8a` … `G-8g` are CLOSED on 2026-10-01 by the `B-08` Planner.** The row marked **CHOSEN**
is the decision; the rest are recorded so no later implementor re-weighs them. The full
algorithm, the corrected facts and the Implementor brief are in **`### B-08`**.

**The decisive topology facts, verified at `65efb3a`** — every option below is priced
against these four and no others:

1. `proxy_set_header X-Real-IP $remote_addr;` appears at **9 of 9** sites in
   `docker/nginx/nginx.conf` and **6 of 6** in `docker/nginx/nginx.dev.conf`. It
   **overwrites**, so a client cannot influence it through nginx. **No Python code reads
   `HTTP_X_REAL_IP` today.** The clean header already exists.
2. **`web` is not published in production** — `docker-compose.yml` publishes only nginx
   (`80:80`/`443:443`); `docker-compose.prod.yml` adds only `db` (`6432:6432`) and volumes.
   This is what makes (1) unforgeable in production.
3. **All 15 `X-Forwarded-For` sites use `$proxy_add_x_forwarded_for`, which APPENDS.** A
   client sending `XFF: 1.2.3.4` produces `1.2.3.4, <real client>`, so **`XFF[0]` is
   attacker-controlled end to end** and `split(",")[0]` returns the attacker's value.
4. **No compose file declares a `networks:` key**, so nginx sits on a Docker-allocated
   per-deployment subnet. A literal trusted-proxy IP is **not operable** without a compose
   change outside **both** blocks' file lists.

| Option | Status | Maintainability | Failure mode | Project convention |
|---|---|---|---|---|
| **(a) a configured trusted-proxy set, rightmost-untrusted resolution** | **PARTIALLY CHOSEN** — the *resolution rule* is adopted; the *set as the only trust mechanism* is **rejected** | one setting, one rule; correct for any future hop count | **the plan's stated fear does not apply to this design**: with the peer gate still operative, an empty set collapses onto nginx's address — **unspoofable, immediately visible** — rather than bypassing. A *literal* set is still not operable, per fact 4 | `env.list(...)` is already used for `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS`; a tuple literal is closer still |
| **(b) a boolean "behind a proxy" flag** | **REJECTED as a resolver; ADOPTED as the gate** | simplest possible setting | the flag is not the problem — the problem is *whose* address the flag trusts. A Docker sibling (`bot`, `scheduler`) is private and is a different principal, so a boolean cannot distinguish | loopback/private membership needs no configuration at all, so it cannot drift |
| **(c) trust nginx's overwritten `X-Real-IP`** | **CHOSEN, but ONLY peer-gated** | close to a Python-only change; the header already exists | **UNCONDITIONAL is the one variant strictly worse than the status quo**: it replaces an attacker-controlled *prefix* with an attacker-controlled *whole value*. In the **default dev stack** `web` **is** published on `8000:8000` with nginx behind `profiles: ["use-nginx"]`, so Django takes the connection **directly** and a direct client sets `X-Real-IP` itself. **The gate is what makes (c) safe, and it is not optional** | `SECURE_PROXY_SSL_HEADER` already establishes the repo's habit of a *scheme* header; this adds the identity counterpart, with the identity check the scheme header has no equivalent of |
| **(c-unconditional)** | **REJECTED — strictly a regression** | — | a silent, complete bypass on every directly-reachable deployment | — |
| **no setting at all; always return `REMOTE_ADDR`** | **REJECTED** | nothing to configure, nothing to drift | correct, and permanently blind: in production every client is nginx's address, so all four keys collapse and the login limiter becomes a global lockout. A functional site with per-IP limits that do not exist | the most honest and the least useful |
| **the plan's original shape — trust `XFF` when the peer is a configured proxy** | **SUPERSEDED** | — | correct in principle and **unoperable in production** (fact 4), and it builds on `XFF[0]`, which fact 3 shows is attacker-controlled. The design here reads the *overwritten* header first and keeps the `XFF` walk only as a fallback | — |

**The single argument that decides it.** `X-Real-IP` is the only header in the system that is
**both present and unforgeable through nginx** (fact 1) **and** in a topology where Django is
**not directly reachable in production** (fact 2). That is a narrow, verified window — and it
is closed by a *predicate*, not by a value, so it cannot go stale. A predicate also **degrades
in the safe direction**: a future CDN or load balancer makes every client collapse onto the
CDN's address, a self-inflicted DoS that is visible within seconds. The current defect is the
opposite — a silent bypass nobody sees.

**The cost, accepted and recorded.** In the default dev stack the gate is **always open** (the
peer is the developer on loopback), so **dev never exercises the untrusted branch**. That
branch is covered by unit tests only. This is a property of the topology, not of the code, and
it must be stated in the docs subsection and in the commit body — a reader must not conclude
the dev stack proves the gate works.

**`G-8c` — env-driven versus literal.** Decided **literal**, and the deciding reason is not
the one the plan gave. `D-6`'s four-template cost was **verified false** (§E.4: both allowlist
tests are one-directional subset assertions, and `test_python_consumed_vars_in_allowlist` is a
hardcoded 8-name subset), so contention was never a factor. The real reason is that **there is
no correct value to put in an env var** — fact 4 — and an operator-facing knob whose value
cannot be determined from inside the repository is a trap with a config surface. Secondary:
`# env-contract:` is documented for *"not a deployment variable"* and this **is** one. Tertiary
and decisive: the invariant that matters — **no public peer is trusted unless an
operator lists a network containing it** — is **additive-only** (`()` in `base.py`,
`dev.py` and `test.py`, undeclared in `prod.py`, so the shipped gate is exactly
`is_loopback or is_private`), so a setting that cannot narrow it is documentation, and
documentation belongs in a comment and in `docs/`. Promotion path named: env-backing is a
follow-up gated on a compose `networks:` declaration.

**`G-8d` — name, type, and no `StrEnum`.** `TRUSTED_PROXY_NETWORKS: tuple[str, ...] = ()`.
Networks, not IPs, per fact 4. Verified that Django 5.2.17 has **no** client-IP setting and that
`SECURE_PROXY_SSL_HEADER` governs scheme only, so the name shadows nothing; the `TRUSTED_*`
prefix follows `CSRF_TRUSTED_ORIGINS`, the nearest in-repo trust-naming precedent. **No
`StrEnum`**: `apps/core/enums.py` holds named *value sets* and a member per network would be
absurd, and the trust *mode*'s two branches are **the algorithm, not a setting** — a mode that
is not configurable must not be presented as if it were. `_TRANSPORT_SETTINGS` is
**deliberately not extended**: it is a six-member `==`-compared transport-security contract.

**`G-8e` — the home, and the plan's reason for it was false.** `apps/core/services/` was
justified by "site_config.py's docstring says so". It does not — that docstring reads *"Used by
the web context processor (sync) and the Telegram bot (async)."* The helper moves to
**`apps/core/utils/client_ip.py`**: it is a **pure function** with no model imports, and
`sanitize.py` — a pure transform over untrusted input, same `Final` + `Args:`/`Returns:`
style, same security rationale — is the structural template. `apps/core/utils/__init__.py` is
a bare comment with **no** re-exports, so there is no re-export decision to make.

**`G-8f` — validation, decided explicitly because it changes the key.** The value is parsed and
returned **canonically**, so two spellings of one IPv6 address share a bucket; unparseable
falls back to the socket peer, and an unparseable peer to `"unknown"`. The helper **never
returns header text verbatim and never raises**. The three existing key assertions use
`127.0.0.1`, which canonicalises to itself, so they survive **by luck, not by design** — hence
the mandatory IPv6 key-stability test. **The validator does not reject private or reserved
addresses**: that is the **gate's** job and it is a trust decision, not a syntax one; rejecting
here would make the dev and test path fall through and change every key. One place decides
trust, one place decides syntax.


### I.7 `B-09` — the directive

**CHOSEN 2026-10-02 by the `B-09` Planner: NO DIRECTIVE CHANGES. `G-9a`…`G-9e` are closed.
The table now carries a third candidate — the `real_ip` module — because the option set
changed once it was established that `real_ip` is absent and that nginx is the first hop.
Nothing below is left for the Implementor to weigh; it exists so the trade-offs are on the
record and are not re-derived by the next editor.**

| Option | Maintainability | Future evolution | Project convention | Verdict |
|---|---|---|---|---|
| **`$remote_addr`** for `X-Forwarded-For` (`G-9c` a) | removes the attacker-controlled prefix **at the source**; correct given `C-6` | correct as long as nginx is the first hop; if a CDN is ever added, the trust model must be revisited | consistent with nginx's own `$binary_remote_addr` keying | **REFUSED — it changes nothing observable.** `proxy_set_header X-Real-IP $remote_addr;` is set at **9/9** prod and **6/6** dev sites and `B-08` **returns on `X-Real-IP`**, so the `X-Forwarded-For` branch is **unreachable in production**. For legitimate traffic the output is **byte-identical**; under attack it differs only in a header **nothing reads**. Its entire value is as a footgun-removal for a *hypothetical future reader* — bought with a 15-location edit, no syntax gate, and no delivery path |
| **keep `$proxy_add_x_forwarded_for`** (`G-9c` b) | **zero** nginx change | correct only while `B-08`'s rightmost-untrusted rule is in place | the Python half already defends it | **CHOSEN** — unchanged at all 15 sites. Combined with the `X-Real-IP` preference, `B-08` makes Django correct against the current, still-appendable header |
| **`real_ip` module** — `set_real_ip_from` + `real_ip_header X-Forwarded-For` (option ii) | would make `REMOTE_ADDR` the true client IP, which `B-08`'s consumers would then prefer | **necessary only if a CDN/LB is ever put in front** — and then it becomes mandatory, not optional | nothing in the tree; and it would reach `$binary_remote_addr`, which the plan puts out of scope | **REFUSED AS ACTIVELY HARMFUL — the strongest finding in the block.** nginx **is** the first hop, so there is **no upstream proxy to trust** and `set_real_ip_from` has **no legitimate value to name**. `real_ip_header` alone is **inert** (nginx replaces `$remote_addr` only for peers matched by a `set_real_ip_from` entry, so it looks like hardening and is not). `set_real_ip_from 0.0.0.0/0` (or `::/0`) makes **every client a trusted proxy**, so `$remote_addr` becomes client-chosen — and because `limit_req_zone` keys on `$binary_remote_addr`, it **destroys the nginx-side rate limiting `B-08` declared unforgeable**, which **no test covers**. Shipping hardening that removes a control is a net loss |
| **clear `X-Forwarded-For`** (`proxy_set_header X-Forwarded-For "";`) | `XFF[0]` stops being attacker-controlled, same benefit as the first row | destroys the chain entirely; a future CDN's hop information would be lost with no compensating gain | — | **REFUSED — dominated.** It buys the same thing as `$remote_addr` (an unread header in production), pays the same delivery cost, **additionally** discards real chain data, and unlike `$remote_addr` it cannot later become useful. Note it would leave `test_nginx_metrics_has_proxy_headers` **green** — the directive *name* is what it asserts (`B-9a`) — so the existing gate would not have caught the information loss |

**The invariant that actually replaced the option list** (`G-9d`): the value of
`X-Forwarded-For` is unasserted, and the two things that make `B-08` correct **are**
asserted — `X-Real-IP` is overwritten from `$remote_addr` at every proxied location in both
files, and no `proxy_set_header` is sourced from a client-echo `$http_*` variable. **The
`X-Forwarded-For` value is not asserted, and neither is the absence of `set_real_ip_from`** —
asserting absence would pin a decision as an invariant (`B-07`'s `G-B`), and test 3 is
written as a safety assertion over a conditional precisely so it catches the **dangerous**
addition without forbidding the **harmless** one.

### I.8 `B-10` — session lifetime

**CHOSEN 2026-10-02 by the `B-10` Planner: options (a) + (c), both in their corrected form.
`G-10a`…`G-10i` are closed. Nothing below is left for the Implementor to weigh — this table
exists so the trade-offs are on the record and are not re-derived by the next editor.**

| Option | Maintainability | Future evolution | Project convention | Verdict |
|---|---|---|---|---|
| **(a)** declare the age **and** the refresh policy | two literal lines plus a comment; **no behaviour change** | the drift the finding describes stops recurring, and a later product decision is a one-line edit that no test resists (`G-10h`) | every comparable bound in the tree is a literal module constant — `TOKEN_TTL_SECONDS`, `RATE_LIMIT_REQUESTS`/`RATE_LIMIT_PERIOD`, `_MAX_HISTORY`, `DAILY_HOUR_UTC`, `LOCK_TIMEOUT_SECONDS`, `SECURE_HSTS_SECONDS`; `db-retention.md` says a bounding number *"must not be operator-variable"* | **CHOSEN** — `G-10a`, `G-10b`, `G-10d` |
| **(b)** `SESSION_SAVE_EVERY_REQUEST = True` | a **global** behaviour change: one extra `django_session` `UPDATE` per response carrying a non-empty session, on `/dashboard/`, `/cabinet/`, `/admin/`, `/moderation/**` | makes the window idle-based — **and the plan's justification for it is wrong for this population** | consistent with nothing, and `set_expiry` appears nowhere in the tree | **REFUSED** — `G-10b`. Not on cost: it **strictly increases** exposure for every actively-browsing authenticated user and delivers **nothing** to a sporadic one, because both are governed by activity the flag does not change for the first case and does not help for the second |
| **(c)** correct the specification | one bullet in §H, a separate commit | stops the doc drifting away from the code; phase 06's own plan explicitly carves this block out of its reservation | phase 06 §5.1: *"Phase 04 edits only under its BLOCK 8 option (c), and only after checking for a concurrent edit"* | **CHOSEN** — `G-10e`, with a named fallback if a concurrent phase-06 edit is present |
| **(c')** the source plan's *"correct the spec to say 14 days of inactivity"* | one bullet | documents a behaviour the code does not have | — | **DROPPED** — `C-B10-1`. An authenticated session is written once, at login, so it is 14 days **absolute from login**, not 14 days of inactivity. Writing "inactivity" would have re-created the SPEC-DEVIATION in the very sentence meant to close it |
| **(d)** re-band the premise, zero code | zero code | leaves the *undeclared* default in place, which **is** the defect | — | **REFUSED as the whole answer** (it leaves the undeclared state), **ADOPTED as the severity verdict** — `04-AUT-006` is WEAKENED, not closed (`G-10j`) |
| **(e)** env-driven `env.int("SESSION_COOKIE_AGE", …)` | an operator knob, plus an `ALLOWED_ENV_VARS` line and up to four `.env.*.example` edits **in the same commit**, all outside `B-10`'s surface | ships a knob whose **correct value cannot be determined from inside the repository** — the same trap `G-8c` identified for `TRUSTED_PROXY_NETWORKS` | the `# env-contract:` opt-out is documented for *"not a deployment variable"*, and this **is** one | **REFUSED** — `G-10d`. Promotion path named in the gate: a product owner supplies a value **and** states the condition under which a shorter one is correct |
| **(f)** absorb the `clearsessions` janitor | no new command module, no `AdvisoryLockId` member, no migration — `django.contrib.sessions` is already in `INSTALLED_APPS` | — | `HOURLY_COMMANDS` **9 → 10** breaks an exact-`==` assertion in a phase-owned file outside this block | **REFUSED** — `G-10f`. And it would not help even if it shipped: `clear_expired()` deletes only rows past `expire_date`, so it **cannot shorten a live session**. Stays as `B-07`'s `G-E` re-filing, with a mandatory hand-off note because it currently lives only in the plan |

**The two questions the table above cannot answer, and where they are recorded instead:**

1. **What should the value be?** No number exists in `docs/`, `src/` or `.env*`, so it is a
   **product decision**, not an engineering derivation. Recorded as known-gap #1 with the
   coordinator / product owner as owner — **owed, not open**; nothing blocks `B-10` or
   `B-11`. `TOKEN_TTL_SECONDS = 300` is a **one-time handshake handoff token** and is
   **not** a lifetime precedent; using it as one is a category error.
2. **What is the residual?** An attacker holding the `sessionid` value has unattended,
   unrevocable access for the remainder of the age, and **no amount of age reduction
   addresses the cause** — the cause is the missing per-request account-state gate, which is
   phase 15's `15-AUTHZ-001` and which `04-VAL-001` forbids this phase from shipping.
   Recorded as known-gap #2.

### I.9 `B-09` overall — ship or defer

**CHOSEN 2026-10-02 by the `B-09` Planner: option (ii) — DEFER the config edit — and the
deferral is not bare.** It ships the executable trust-model gate (`G-9d`) and the operator
runbook (`G-9b`), so the block ends with a **delivered artefact**, not an omission.

**The case FOR shipping a config change, argued at its strongest.**

1. It is a one-token edit in 15 places, trivially reviewable, semantically inert for
   legitimate traffic.
2. It removes an attacker-controlled value from a header **at the source**, which is the
   textbook place to remove it — defence in depth is worth having even when the current
   reader is safe, precisely because readers change.
3. The live test gate does **not** forbid it: `test_nginx_metrics_has_proxy_headers`
   asserts the directive **name** as a substring and never the value (`B-9a`), so both
   variants stay green.
4. Deferring leaves the edge formally weaker for as long as the deferral lasts, and the
   phase is explicitly a remediation phase — not shipping the fix is itself a choice with a
   cost.
5. A named residual can rot. A committed change, even a currently-undeliverable one, is at
   least visible in the history.

**The case AGAINST, which is stronger here, and the four reasons.**

1. **It cannot be delivered — this is not "may not take effect", it is *cannot*.**
   `actions/checkout@v4` runs on an **ephemeral GitHub-hosted runner**; the production host
   is touched only by the SSH script, which contains **no `git` command of any kind**. The
   bind-mount source is the host's own `/app/docker/nginx/nginx.conf`. A committed config
   change **does not reach production**. It would be reviewed, merged, and **inert** — and a
   commit that claims to fix something and does not is **worse than a named residual**,
   because it converts an honest gap into a false claim. §F.1's dominant failure mode is
   precisely "a partial block silently counted as complete", and this would *manufacture*
   that failure rather than avoid it.
2. **It cannot be rolled back either.** `deploy.yml`'s rollback recreates `web bot` only,
   and `docs/ops/rollback.md` has no nginx step. So the *revert* would also be manual — while
   the *change* would look automatic. That asymmetry is worse than shipping nothing.
3. **There is no syntax gate, and the failure is a production outage the pipeline cannot
   see.** `nginx -t` is not runnable in CI, and the deploy health gate curls port 8000
   **inside the web container**, bypassing nginx — so a config that fails to start nginx
   presents as a **green deploy** and a **down site**.
4. **It buys nothing observable.** `X-Real-IP` is set at every proxied location and `B-08`
   returns on it, so **`X-Forwarded-For` is never read in production**. The edit would change
   no resolution, no key, no log line, and no response. The residual it removes is currently
   **inert by construction**, not by luck.

Add the cross-phase conflict (`U-7`: phase 09 states *"No other phase claims them"*, and its
BLOCKS 10–12 already carry the `nginx -t`-before-rolling discipline) and the picture is
complete.

**Why (ii) is a *safe* outcome, not a broken one — and this is the load-bearing sentence.**
`B-08`'s peer gate, its `X-Real-IP` preference and its right-to-left walk make Django correct
against the current, still-appendable header, and the peer gate is **always open in
production** precisely because nginx's container IP is private — so the design's correctness
rests on nginx overwriting `X-Real-IP`, which it does at **9/9** prod and **6/6** dev sites.
Nothing is left undefended by deferring. What deferring leaves undefended is the *possibility*
that someone later writes a naive `XFF[0]` reader — and that is exactly what `G-9d` now
addresses, executably.

**Scope judgement, stated plainly (the prompt's third question).** This phase has been
surgical and honest about what it does not ship (`B-06`, `B-07`, `B-10` all ended as
declarations or documentation), and that pattern is **correct here** rather than merely
conservative. Adding an nginx directive the pipeline cannot deliver or roll back, cannot
syntax-check, and whose benefit is provably zero against the shipped code, would be the one
change in the phase that **looks like remediation while being an unverifiable claim**. The
honest move is to name the gap, pin the invariant that makes the shipped half correct, and
give the file's real owner the runbook. **I believe deferral is right, and I would still
believe it if `nginx -t` were runnable in CI** — because the delivery defect and the
zero-benefit finding are each independently sufficient.

**What would reverse it** (recorded so the decision is revisitable, not frozen): a change to
either trigger in the residual's owner table — `deploy.yml` gaining a `git pull` + `nginx -t`
+ `reload` step **with** nginx in the rollback, **or** the config being baked into the image
so an ordinary image deploy carries it. Either converts this from *impossible to deliver* to
*an ordinary change*, at which point `$remote_addr` becomes worth doing and this deferral
should be revisited **as part of that work, not before it**.

### I.10 `B-08` → `B-09` — the outbound interface contract

**`G-8g` makes `B-09` optional.** This subsection exists because the contract is what makes it
*safe* to be optional, and because `B-08` is the block that discovers what `B-09` must not
break. The full table is in **`### B-08` → *The `B-09` interface contract***; the four points
`B-09` cannot afford to miss:

1. **`X-Real-IP` is already correct in nginx and must stay that way.** `proxy_set_header
   X-Real-IP $remote_addr;` overwrites, so it is unforgeable — and it is now **read** by
   Python. Changing or removing it does not restore the old behaviour; it silently changes
   which branch of the resolver runs, and the fallback is weaker.
2. **`web` must not be published in production.** If anyone ever publishes it, the peer gate
   is the only thing still holding — and a public peer is **refused**, so the site degrades to
   per-peer buckets rather than to a bypass. That is the safe direction, and it will look like
   "the rate limiter stopped working per client", not like a security event.
3. **The `real_ip` module must not rewrite `$remote_addr` without a matching
   `set_real_ip_from`.** Verified absent today. This is the **single** nginx change that could
   silently invalidate the whole design, and nothing in the test suite would catch it.
4. **`src/backend/tests/test_nginx_config.py::test_nginx_metrics_has_proxy_headers` is a live
   tripwire on the `= /metrics` block** — it asserts the substring `proxy_set_header
   X-Forwarded-For` is present. It is satisfied by both `$proxy_add_x_forwarded_for` and
   `$remote_addr`, so either directive leaves it green, but **it belongs in `B-09`'s file
   list** and must pass **unchanged**.

**And the deployment reality, recorded so `B-08`'s DoD is honest:** `B-09` **cannot currently
be delivered, validated or rolled back** by this repository's pipeline — `deploy.yml` never
`git pull`s; the nginx config is a **bind mount**, so `docker compose up -d` will not recreate
an unchanged service; the health gate runs **inside the web container, bypassing nginx**; and
the rollback (`up -d --force-recreate web bot`) **excludes nginx**. There is no `nginx -t`, no
reload path and no `docker compose config` gate anywhere. **That is `B-09`'s problem, and it is
not a reason to delay `B-08`.**

**Cross-reference added 2026-10-02 by the `B-09` Planner — `B-08`'s conclusions are unchanged;
one word in point 3 above is corrected, and nothing else in this subsection is.** Point 3 calls
the `real_ip` module the *"single"* nginx change that could silently invalidate the design.
It would, and it is now **REFUSED rather than outstanding** (`G-9c`, `§I.7`: nginx is the
first hop, so `set_real_ip_from` has no legitimate value to name, and `set_real_ip_from
0.0.0.0/0` would additionally destroy `limit_req_zone $binary_remote_addr`). But it is **not
the only such change**: `proxy_set_header X-Real-IP $remote_addr;` is **equally load-bearing
and far likelier to be touched**, because it is the branch `get_client_ip` returns on — its
absence silently reroutes every production request onto the weaker `X-Forwarded-For` walk,
and a "pass the header through" edit substituting `$http_x_real_ip` would swap a
client-controlled **prefix** for a client-controlled **whole value**. That vector is what
`B-09`'s tests 1–2 now guard, and it was **uncovered until this block**. `G-9g`'s verdict —
"`B-08` is complete and correct on its own; `B-09` is optional hardening" — is **confirmed as
final**, and `docker-deployment.md::Client IP Trust Model` needs **no correction**, because
`$proxy_add_x_forwarded_for` genuinely is still in use at all 15 sites.

