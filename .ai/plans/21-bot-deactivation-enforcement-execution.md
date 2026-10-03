# Plan 21 — Bot-Tier Enforcement of Account Deactivation (Execution Plan)

**Status:** ready to execute · **Numbering:** 21 (18 is the operator kill-switch; renumbered from 19 after another phase claimed 19) · **Created:** 2026-10-03
**Origin:** plan 18's `B-3` probe found the Telegram bot does **not** enforce `is_active`.
**Closes:** plan 18 `D-2` · a named piece of `04-AUT-002`.

---

## 0. Provenance and drift control

Every citation below was re-derived against the working tree at commit `f2fd392` on 2026-10-03.
Re-verify before implementing and record the commit you verified against (plan 18's validator found
its §0 drift record missing — do not repeat that).

**Sources:** plan 18 `§1`, `§5 D-2`, and its permanent probe test
`src/telegram_bot/tests/test_account_state_deactivation_probe.py` ·
`apps/users/services/account_state.py` · `telegram_bot/middlewares/permissions.py` ·
`telegram_bot/handlers/support.py` · `telegram_bot/handlers/login.py`.

---

## 1. The divergence this closes

There are **two** account-state rules in the repo, and they disagree:

| Rule | Contains `is_active`? | Used by |
|---|---|---|
| `account_state_q()` — the **queryset** rule (`account_state.py:69-94`) | **Yes** — `f"{prefix}is_active": True` at line 92 | `send_alerts`, `alert_query`, `immediate_alerts`, `search/views/preferred_city.py:80` |
| `get_account_state()` — the **Python predicate** (`:44-66`) | **No** | `permissions.py` (the bot gate), `can_login`, `can_publish_ad`, `get_state_badge` |

The divergence is **documented in the source** (`account_state.py:80-84`: *"Mirrors
`get_account_state()` except for `is_active`"*) and was introduced with finding `06-PII-104`.

Consequence today:

- **Alert emails are already correct** — `account_state_q()` suppresses them for a deactivated user.
- **The web is already correct** — `ModelBackend.user_can_authenticate()` re-checks per request
  (plan 18 §1).
- **The bot is not** — `permissions.py:228` calls `get_account_state()`, which cannot see
  `is_active`. A deactivated user passes every bot gate.

And the middleware's own class docstring (`permissions.py:28-30`) claims it *"Delegates flag
evaluation to the shared `get_account_state` predicate so that bot and web dashboard share a
single source of truth for account-state flags."* **That claim is currently false.** Fixing the
predicate is what makes it true.

---

## 2. Product decisions (owner answered 2026-10-03)

> **ID convention after renumbering.** This plan was created as `19-…` and renumbered to `21-…`
> on 2026-10-03 when another phase claimed 19. The **decision IDs `19-D1`..`19-D6` are kept
> unchanged** because they are cited from production docstrings (`account_state.py`,
> `permissions.py`, `admin.py`). The **block IDs `B-1`..`B-5` and gate IDs `19-G1`..`19-G5`** are
> plan-local and were renumbered to `21-G1`..`21-G5`. Cite "plan 21" for the document and `19-Dn`
> for a decision — that is not an inconsistency.

| # | Question | **Decision** | Consequence |
|---|---|---|---|
| **19-D1** | Where to fix — the shared predicate, or the bot middleware only? | **Fix the shared predicate.** Add `is_active` to `AccountState` / `get_account_state()`. | Closes the divergence permanently. `permissions.py` needs **no new gate logic** — it already reads the shared predicate. Touches `can_login` and `get_state_badge`; both handled explicitly in `B-1`. |
| **19-D2** | Block scope for a deactivated user in the bot? | **Ad creation is blocked. The support button stays reachable**, so the user can request restoration. | **This is a new third category**, not `is_banned` and not `is_declined`. See §3 — the carve-out is the hard part. |
| **19-D3** | Rejection message? | **A separate message.** | New translatable string (`B-4`). Distinct from the `is_banned` "restricted" message. |
| **19-D4** | In-flight FSM state? | **Leave it.** | A deactivated user mid-ad-creation resumes on reactivation. FSM has its own Redis TTL. No shared-FSM mutation. |
| **19-D5** | Scope — `is_active` only, or also fix `is_banned`/`is_deleted`/`is_declined`? | **`is_active` only.** | The other three keep exactly their current behaviour. `04-AUT-002` stays **NOT closed**; see §8. |
| **19-D6** | Should `/start` **with an argument** (e.g. a stale `login_<token>`) also render the greeting for a deactivated user? | **No.** Owner answered 2026-10-03. | Only the **no-argument** greeting is allowed. A `login_<token>` deep-link cannot succeed anyway — `login_status` refuses `is_active=False` with a `410` (`consent.py:526-530`) — so rendering its keyboard is pointless, and allowing it would widen the carve-out for no benefit. **Enforce the no-argument form explicitly**; do not allow `/start` wholesale. |

---

## 3. The access-control matrix — read this before implementing

`21-D2` makes this non-trivial. **A blocked user never sees the keyboard that carries the support
button.**

The `/start` greeting keyboard (`handlers/login.py:74-95`) carries three buttons: 🌐 Language,
*Contact us* (`contact_us`), and **Contact support** (`BotCallbackPrefix.SUPPORT_START`).

The middleware evaluates every update (`permissions.py:117-122`) and replies with a rejection
before any handler runs. So:

```
deactivated user sends /start
  -> text="/start", callback_data=None
  -> classify_contact_deep_link(...) is None            # NOT a contact link
  -> _evaluate_user_state(user, is_contact_link=False)  # must NOT hard-block
  -> handler renders the greeting + keyboard
deactivated user taps "Contact support"
  -> callback_data == SUPPORT_START                     # NOT a contact link either
  -> _evaluate_user_state(...)                          # must allow
  -> handle_support_start -> FSM -> AWAITING_MESSAGE
deactivated user writes free text  <-- the crux
  -> callback_data=None, no deep link
  -> _evaluate_user_state(...)                          # must ALSO allow
  -> handle_support_message -> SupportTicket created
```

**The carve-out cannot be an allowlist of event types.** The third step is ordinary free text, and
it must reach the handler while the user is in the intake FSM. So the rule is **state-based**, not
event-based:

> A deactivated user may pass the gate **iff** they are in the support-intake FSM, or the update is
> the no-argument `/start` greeting, or its `callback_data` is `SUPPORT_START`.

Everything else — every other command, every ad-creation step, every callback — is blocked.

| Bot path | `is_active=True` | `is_active=False` (after this plan) |
|---|---|---|
| `/start` greeting (no args) | allowed | **allowed** — carries the support button. **`21-D6`: `/start <anything>` stays blocked.** |
| `SUPPORT_START` callback | allowed | **allowed** — the restoration channel |
| Support-intake FSM free text | allowed | **allowed** — completes the ticket |
| `contact_us` / `contact_<id>` deep-links | allowed | **blocked** — `21-D2` says ad creation and seller contact stop |
| Ad creation (`/post` and the whole FSM) | allowed | **blocked** |
| Any other command or callback | allowed | **blocked** |

> **Resolved — `21-D6`.** Only the **no-argument** `/start` greeting is allowed for a deactivated
> user. `/start <anything>` stays blocked. See `21-D6` in §2.

> **Required — the intake carve-out is free-text-only.** The support-intake clause must admit
> **ordinary text messages only**: `callback_data is None`, the text non-empty, and the text **not a
> command** (must not start with `/`). Without this, the state-based clause admits **any** update
> while the user sits in the support FSM — notably `/post`, which would otherwise clear the
> interaction gate and then pass the publish gate (`_evaluate_publish_permission` checks only
> `ads_auto_publish`, **not** `is_active`), re-opening ad creation for a deactivated user. A command
> or a non-Support callback typed in the intake state stays blocked. Pinned by
> `test_deactivated_user_cannot_smuggle_a_command_through_the_support_fsm`.

### Pre-existing bug found while scoping this

`handlers/support.py:10-12` claims:

> *"anonymous + DECLINE users may reach support; banned/deleted/consent-revoked users are blocked"*

**The DECLINE half is false.** `SUPPORT_START` is not a contact deep-link, so a DECLINE user's
`/start` greeting is rejected by `_evaluate_user_state` (`permissions.py:239-248`) and they never
see the keyboard. The anonymous half is correct — `_resolve_user` returns `None` and
`_evaluate_user_state` fails open (`:225-226`).

`B-3` must **correct the docstring to match the tree** and add a test that pins the DECLINE
behaviour as-is. Fixing DECLINE reachability is **out of scope** (`21-D5`); this plan records the
behaviour, it does not change it.

---

## 4. Execution blocks

Serial: `B-1 → B-2 → B-3 → B-4 → B-5`.

### B-1 — `AccountState.is_active` and the shared predicate

**File** `src/backend/apps/users/services/account_state.py`

1. Add `is_active: bool` to the `AccountState` NamedTuple (`:34-41`) — **first field**, matching the
   queryset rule's ordering intent (`account_state_q()` lists `is_active` last, but the Python rule
   reads naturally with the access-control flags first; document the choice).
2. Populate it in `get_account_state()` (`:60-66`) from `user.is_active`.
3. **Rewrite the `account_state_q()` docstring** (`:80-84`). It currently says the queryset rule
   *"Mirrors `get_account_state()` except for `is_active` — see the honest limit documented on the
   queryset-level tests."* After this block there is **no exception** — both rules carry all six
   flags. That "honest limit" note must go, and `test_account_state.py`'s corresponding tests
   (around `:255-283`, `:358-433`) updated.
4. **`can_login()` (`:129-152`) — decide and record.** Adding `is_active` makes it return `False`
   for a deactivated user. **This interacts with an explicit check**: `users/views/consent.py:526-530`
   returns a `410` for `is_active=False`, and `:514`/`:525` call `can_login`. **Verify the ordering
   is unchanged** so an inactive user still gets the `410`, not the `can_login` rejection message.
   If the order would change, that is a **regression** — report it, do not paper over it.
5. **`get_state_badge()` (`:155-180`) — decide and record.** It composes hardcoded English badge
   fragments. An `is_active` badge would be shown only to staff (`UserAdmin.list_display` does not
   use `get_state_badge`), and a deactivated user cannot reach their own dashboard
   (`ModelBackend`). **Recommendation: add no badge**, and say why in a comment. If the implementer
   adds one, it must be justified — do not add it silently.

**Gate `21-G1`:** `AccountState` has six fields; `get_account_state()` populates all six;
`account_state_q()`'s "except for `is_active`" note is gone; `consent.py`'s `410` ordering is
unchanged; the `get_state_badge` decision is recorded in a comment.

> **Wording correction.** `account_state_q()` mirrors only **five** of the predicate's **six**
> fields — it deliberately omits `ads_auto_publish` (a publishing restriction orthogonal to whether
> an account may receive messages, rule 5). The divergence this plan closes is **`is_active` only**;
> `ads_auto_publish` remains a deliberate, documented omission. Any wording that says "both rules
> carry all six flags" is wrong.

### B-2 — The bot gate and the support carve-out

**File** `src/telegram_bot/middlewares/permissions.py`

1. Add an `is_active` branch to `_evaluate_user_state` (`:204-253`). **Position matters:** evaluate
   it **before** the other flags, so a deactivated-but-also-banned user gets one clear answer, and
   the support carve-out is not reachable for an erased account.
2. **Apply the §3 matrix.** Read the FSM state (`data.get("state")`) to decide whether the user is
   in the support-intake flow. Note the structural constraint at `:42-50`: the middleware already
   resolves the user **once** and every consumer shares that instance — the carve-out must not
   re-query.
3. New rejection message per `21-D3`, via `gettext` (`_()`), distinct from the `is_banned` and
   `is_declined` messages. It must **point the user at support** — they have a restoration channel
   and the message should say so.
4. **Update the class docstring** (`:24-51`). Its "Enforces four independent account flags" list
   (actually five) is now six, and its "single source of truth" claim becomes true rather than
   aspirational. Note the support carve-out explicitly.

**Gate `21-G2`:** the §3 matrix holds for all six paths; `is_active` is evaluated first; the message
is distinct and names support; the docstring matches the code.

### B-3 — Correct `support.py`'s docstring and pin DECLINE behaviour

**File** `src/telegram_bot/handlers/support.py:10-12`

Correct the false DECLINE claim (§3). **No behaviour change** — this block is a comment fix plus the
test that records the current behaviour. If the implementor believes DECLINE reachability should be
fixed, that is **out of scope** (`21-D5`) — record it in §8 and do not implement it.

**Gate `21-G3`:** the docstring is true of the tree; a test pins the DECLINE-is-blocked behaviour with
a comment naming the owner.

### B-4 — i18n and documentation

| File | Change |
|---|---|
| `src/backend/locale/{ru,bs}/LC_MESSAGES/django.po` | Translate the new rejection message. **`en` may stay empty** (msgid is English). |
| `docs/99-agent/architecture.md` | Update the bot-tier residual: `is_active` is now enforced in the bot **with a support carve-out**; record the three-flag remainder as still open. Correct the `04-AUT-002` section added by plan 18 (`B-4`). |
| `docs/ops/docker-deployment.md` | Update the deactivation row: the bot enforces it, with the support channel as the restoration path. |
| `.ai/plans/18-account-deactivation-execution.md` | Mark `D-2` **closed**; update `§1`'s bot-tier row and the operator-message status: `WEB_ONLY_ENFORCEMENT` is renamed to `DEACTIVATION_ENFORCEMENT_NOTE` and reworded to both-tier enforcement + Support carve-out (its pinning test renamed too). |

**i18n — do NOT run `makemessages` naively on this tree.** The lightweight Docker form (see §7)
runs, but its output is **destructive**: several bot modules import ``gettext_lazy as _lazy``
(e.g. ``telegram_bot/handlers/ad_create/submit.py``), and xgettext's keyword set does **not**
include ``_lazy``. Extraction therefore marks those strings' hand-maintained catalog entries
obsolete (``#~``), **deletes** their ``ru``/``bs`` translations, and inflates the ``.po`` diff by
~800 lines — which turns ``test_lock_timeout_boundary.py`` red. **Sanctioned method instead:**

1. Revert all three ``django.po`` files to HEAD (byte-identical; verify ``git diff --stat`` is
   empty).
2. Hand-add **only** the new rejection msgid to ``ru``, ``bs`` and ``en``, in the correct sorted
   position (adjacent to the ``is_banned`` message), with the correct ``ru``/``bs`` translation and
   **no ``fuzzy`` flag**. A hand-added entry with a wrong plural form or a ``fuzzy`` flag fails the
   completeness gate, so keep it a singular msgid with no flags.
3. Let the test container recompile ``.mo`` at startup.

Shipped state: ``+3`` lines per locale (one msgid entry each); ``test_i18n_completeness.py`` green
and ``test_lock_timeout_boundary.py`` green. (The one incidental ``ru``/``bs`` gap the first
extraction surfaced — ``Password does not meet the password policy: %(errors)s``, plan 18 ``D-9``
— is **not** shipped: reverting to HEAD drops it. It remains a pre-existing, unextracted gap.)

**Gate `21-G4`:** `ru` and `bs` have non-empty `msgstr`; no doc claims the bot ignores `is_active`.

### B-5 — Amendments owed

Record in the commit body; do not edit the target files in this block.

| Target | Amendment |
|---|---|
| `.ai/plans/15-authorization-remediation.md` | `GATE Q1` and BLOCK 6: `is_active` now has a **bot-tier** gate too, not only the web's `ModelBackend`. Its exclusion from the DENY set is now correct on **both** tiers. |
| `04-AUT-002` record | The bot-tier residual is narrowed to `is_banned` / `is_deleted` / `is_declined`. `04-AUT-002` stays **NOT closed**. |
| `src/backend/apps/users/admin.py` operator toast | `WEB_ONLY_ENFORCEMENT` renamed to `DEACTIVATION_ENFORCEMENT_NOTE` and reworded: the change is immediate on the website **and** enforced in the Telegram bot, with Support as the restoration path. The old claim ("NOT enforced in the Telegram bot") is deleted. `_deactivation_message`'s docstring and `services/deactivation.py`'s module docstring corrected. Pin test renamed to `test_operator_message_states_the_bot_tier_and_the_support_carve_out`. |

---

## 5. Test ownership

**Modify** `src/telegram_bot/tests/test_account_state_deactivation_probe.py` — plan 18 created it as
a **permanent** test that asserts `can_interact is True` for a deactivated user. **That assertion is
now wrong and must be inverted** with a comment naming plan 18, `D-2`, and this plan. Inverting a
known-gap test is the correct resolution, not deleting it.

**Modify** `src/backend/apps/users/tests/test_account_state.py` — `AccountState` gained a field;
update every construction and the "except for `is_active`" tests (`:255-283`, `:358-433`).

**New** `src/telegram_bot/tests/test_bot_deactivation_matrix.py` — the §3 matrix, one test per row,
plus:

| Test | Asserts |
|---|---|
| `test_deactivated_user_sees_the_start_greeting` | `/start` no-args is **not** blocked. |
| `test_deactivated_user_can_tap_contact_support` | `SUPPORT_START` passes the gate. |
| `test_deactivated_user_can_complete_the_support_ticket` | Free text while in the intake FSM passes, and a `SupportTicket` is created. **The most important test in the plan** — it is the step an event-type allowlist would break. |
| `test_deactivated_user_cannot_create_an_ad` | `/post` and the ad FSM are blocked. |
| `test_deactivated_user_cannot_use_contact_deep_link` | `contact_us` / `contact_<id>` blocked (`21-D2`). |
| `test_deactivated_and_banned_user_is_not_granted_the_carve_out` | `is_active` is evaluated **first**, so the carve-out is unreachable for a banned/erased account. |
| `test_deactivated_user_is_blocked_after_leaving_the_support_fsm` | Once out of the intake state, the user is blocked again. |
| `test_rejection_message_differs_from_the_banned_message` | `21-D3`. |
| `test_rejection_message_points_at_support` | The message names the restoration channel. |
| `test_decline_user_cannot_reach_support` | Pins the **pre-existing** behaviour (§3). |
| `test_web_session_still_revoked` | Regression: `ModelBackend` still revokes the web session — `21-D5` must not touch it. |

**Must stay green:** `test_account_state_middleware.py` (its `TestCrossPredicateAgreement` pins
middleware/predicate agreement — the most likely thing to break) ·
`test_account_state_deactivation_probe.py` after inversion · `users/tests/test_login.py` (the
`consent.py` ordering) · `search/tests/test_alert_audience_gate.py` (`account_state_q`) ·
`test_admin_deactivate_user.py`.

**Do not touch:** `apps/moderation/admin_actions.py`, `apps/ads/admin.py`,
`test_admin_change_form.py`, `test_admin_pii_containment.py`.

---

## 6. Risks

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| R-1 | The carve-out is implemented as an **event-type allowlist** and the free-text FSM step breaks — the user can tap the button but cannot complete the ticket, and never finds out. | **High** | §3's state-based rule; `test_deactivated_user_can_complete_the_support_ticket` is the canary. |
| R-2 | `can_login()` gaining `is_active` changes the **web** rejection from `410` to a different message/status. | **High** | `B-1` step 4 requires verifying `consent.py:514-530` ordering and reporting a regression rather than papering over it. |
| R-3 | The carve-out is too wide and a deactivated user keeps reaching ad creation or seller contact. | **High** | §3's matrix is normative; four matrix rows have tests. |
| R-4 | Plan 18's permanent probe is deleted instead of inverted, losing the audit trail. | Medium | `B-5`/§5 require inversion **with a comment naming plan 18 and `D-2`**. |
| R-5 | `AccountState` field count is pinned somewhere (exact-`==` test, `len()` assertion). | Medium | Grep for `AccountState(` and `len(` on the tuple before `B-1`; `apps/core/tests/test_scheduler.py` shows this repo *does* pin exact counts. |
| R-6 | The `get_state_badge` decision is made silently. | Low | `B-1` step 5 requires a recorded reason either way. |
| R-7 | A deactivated user spams the support channel to farm restoration requests. | Medium | **Already mitigated** — `SUPPORT_MESSAGE_RATE_LIMIT_REQUESTS = 5` per `600 s` (`telegram_bot/services/rate_limit.py:125-129`). Verify it applies on this path and cite it in the docstring; do **not** add a second limiter. |
| R-8 | New message not translated in `ru`/`bs` → the completeness gate fails at the end. | Low | `B-4` gate; run the i18n test before committing. |

---

## 7. Definition of done

**Per block:** `21-G1`..`21-G4` closure text in its commit body; `21-G5` for `B-5`'s amendments.

**Phase-level**

1. Every test in §5 exists and passes.
2. `uv run ruff check src/backend/apps/users/ src/telegram_bot/` — clean.
3. `uv run basedpyright` on changed Python files — clean, no new suppression.
4. `uv run djlint src/backend/templates/` — no template change, trivially clean.
5. **i18n:** `ru` and `bs` have non-empty `msgstr` for the new message; `.\Makefile.ps1 test` green.
   Extraction uses the lightweight form — `--no-deps --entrypoint ""` (see `.kilo/rules/commands.md`);
   `make makemessages` does **not** work on Win 11 + Docker Desktop.
6. **No admin/locale collateral:** `git diff --name-only` shows only plan-21 files.
7. `docs/02-database/db-retention.md` **byte-unchanged** — phase-04 exit condition.
8. `.ai/audit/**` untouched.
9. `apps/moderation/**` and `apps/ads/admin.py` untouched.

**Full gate:** `.\Makefile.ps1 test` (fast, skips `seed`).

---

## 8. What this does NOT close

| # | Work | Owner |
|---|---|---|
| D-1 | **`is_banned` / `is_deleted` / `is_declined` still have no bot-tier gate.** `get_account_state` will now carry `is_active`, but the other three are unchanged and `04-AUT-002` remains **NOT closed**. | `15-AUTHZ-001` |
| D-2 | A deactivated user's **existing ads stay live** — deactivation does not unpublish. They are blocked from *creating* new ones and from contact, but listings persist. | product + `15-AUTHZ-001` |
| D-3 | **DECLINE users cannot reach support** (§3) — a pre-existing bug, recorded not fixed. | product |
| D-4 | `django_session` rows are still never deleted; still owned by `15-AUTHZ-001`. | `15-AUTHZ-001` |
| D-5 | The moderator contract and `has_deactivate_permission` remain phase 15 BLOCK 9's. | `15-AUTHZ-003` |

---

## 9. Rejected alternatives

| Option | Verdict | Why |
|---|---|---|
| Fix `is_active` in `permissions.py` only | Rejected | Leaves the documented divergence, keeps the middleware docstring's "single source of truth" claim false, and leaves `can_login`/`can_publish_ad` inconsistent with `account_state_q()`. `21-D1`. |
| Block everything like `is_banned` | Rejected | `21-D2`: the user then has **no** restoration channel — web is revoked by `ModelBackend`, bot fully blocked. Operator-only undo. |
| Allow contact deep-links like `is_declined` | Rejected | `21-D2`: a deactivated seller would keep receiving buyer leads on ads that are still live. |
| Clear the FSM on deactivation | Rejected | `21-D4`: touches shared Redis FSM state for marginal benefit; the user resumes on reactivation. |
| Add a second support rate limiter | Rejected | `R-7`: one already exists (5 per 600 s). |
| Fix `is_banned`/`is_deleted`/`is_declined` here too | Rejected | `21-D5`: separate phase, separate risk, separate owner. |
