---
plan_id: "06-pii-consent-remediation"
phase: "06"
phase_name: "PII Protection & Consent Compliance"
source_report: ".ai/audit/99-validation/06-pii-consent-validated-findings.md"
source_findings: ".ai/audit/06-pii-consent/findings.md"
date: "2026-09-29"
planner: "Planner (subagent)"
anchor_commit: "aa2a6b0"
report_anchor_commit: "9e96b84"
status: "planned"
findings_in_scope: 14
findings_implemented: 14
findings_merged_away: 1
findings_rejected: 1
blocks: 17
---

# Execution Plan — Phase 06 Remediation (PII Protection & Consent Compliance)

## 0. Header, provenance and scope statement

### 0.1 Provenance

| Item | Value |
|---|---|
| Source report | `.ai/audit/99-validation/06-pii-consent-validated-findings.md` (validated, 2024 lines) |
| Source findings file | `.ai/audit/06-pii-consent/findings.md` — **deleted from the working tree** (tracked deletion). Recorded for traceability only; **not** an input. |
| Report anchor commit | `9e96b84` (drifted; the tree is authority) |
| Code-context document | `.ai/tmp/code-context-phase06.md` (1116 lines, Auditor) |
| **Working anchor commit for this plan** | **`aa2a6b0`** (`git rev-parse --short HEAD`, taken before writing) |
| Date | 2026-09-29 |
| Findings in scope | 16 filed; **14 phase-06-owned** · 1 merged away (`PII-103` → `04-AUT-005`) · 1 rejected (`PII-115`) |
| Validated severity split | 1 CRITICAL (`PII-101`) · 3 HIGH (`PII-102`, `PII-103`*, `PII-104`) · 7 MEDIUM · 3 LOW |
| State at the anchor | **0 already fixed · 0 partially fixed · 14 still open** |
| Non-finding work items | 1 published decision (BLOCK 1) + 1 architectural prerequisite (BLOCK 3, the report's *Required Fix 1*) |
| Execution blocks | 17 |
| Implementor concurrency | 1, strictly sequential (project rule: only one implementor at a time) |

**Naming convention.** This plan cites its own items cycle-scoped as **`06-PII-1xx`**
(per phase 03's `VAL-001` convention and this report's `VAL-011`, which records that
bare `PII-1xx` already collides with shipped in-source markers referencing a *prior*
audit cycle). Where the source report writes `PII-101`, this plan writes `06-PII-101`
in code comments, docstrings, tracker entries and commit messages.

### 0.2 Evidence basis — read this before executing any block

The validated report is the only narrative source. This Planner re-derived the
load-bearing claims against the working tree at `aa2a6b0`. **Where the report and the
tree disagree, the tree wins and the correction is listed here.**

| # | Claim | Report says | **Tree at `aa2a6b0` says** | Consequence for this plan |
|---|---|---|---|---|
| C-1 | `SupportTicket.chat_id` / `.telegram_id` are non-nullable | non-nullable `BigIntegerField` | **Confirmed.** `apps/core/models.py::SupportTicket`: `chat_id` and `telegram_id` are `BigIntegerField` with no `null=True`; `username` is `CharField(max_length=255, null=True, blank=True)`; `user` is `ForeignKey(..., on_delete=SET_NULL, null=True, blank=True)` | `06-PII-101` needs a `core`-app schema migration before any code can null the columns |
| C-2 | `HOURLY_COMMANDS` has nine entries, none purging `consent_records` | nine | **Confirmed.** Exactly nine, in the listed order; `DAILY_COMMANDS = ["send_alerts", "rollup_daily_metrics"]` | `06-PII-116` appends a tenth; the scheduler's `_validate_commands` requires discoverability via `get_commands()` |
| C-3 | `AdvisoryLockId` has 18 members, ID 10 reserved, next free is 13 | 18 (phase 03's plan) | **Corrected.** The enum now has **19** members: a concurrent phase-02 agent added `REPAIR_BOT_USERNAME = 13`. The next free integer is **14**; ID 10 remains reserved | The sweep lock in `06-PII-116` is **no longer free**. See §5.3 and BLOCK 15's gate |
| C-4 | `test_sanitize.py` pins the mask `length == 13` | 13 | **Corrected.** The docstring says 13, the **assertion is `len(result) == 11`** (`"tg_"` + 8 hex). Pre-existing docstring/assertion mismatch | `06-PII-112` must rewrite the test to assert the *property*; do not chase "13" |
| C-5 | `VAL-009` — a scrub must re-derive the FTS vectors or it creates a new leak | binding hazard | **Materially overstated.** `apps/ads/migrations/0001_initial.py` installs `CREATE TRIGGER ads_search_vector_update BEFORE INSERT OR UPDATE ON ads FOR EACH ROW EXECUTE FUNCTION ads_search_vector_fn()`. A row-level `BEFORE UPDATE` trigger fires for **every** UPDATE regardless of how it is issued, including `QuerySet.update()` and a `RunSQL` data migration | `06-PII-109` must **verify with one assertion** in `apps/ads/tests/test_setup_search_triggers.py` and must **not** build a re-derivation mechanism |
| C-6 | PII-108's documentation half is the naming collision between "third-party Plausible" and the `analytics` consent key | remediation item | **Narrowed.** Both public surfaces already scope "Analytics" to Plausible (`components/consent_banner.html` bullet, `privacy.html` §2 + cookie table + third-party list). The collision survives in three internal names only: `CookieCategory.ANALYTICS`, the `consent_analytics` cookie, the `consent_analytics` context key | The doc-only half has almost no audience left. `06-PII-108`'s substantive half is `SearchHistory.query_normalized` |
| C-7 | `PII-101`'s orphaned row is "unfindable" | refuted by the validator | **Refuted, confirmed refuted.** The FK's `SET_NULL` keeps the row; `SupportTicket.objects.filter(user_id__isnull=True)` finds it in one query | The finding survives on **retention**, not discoverability. BLOCK 13's acceptance criteria are worded accordingly |
| C-8 | `record_consent_action` is request-aware, which forces the audit write to live in the view | refuted by the validator | **Confirmed refuted.** `apps/users/services/consent_record.py::record_consent_action(user, choice, categories, request: HttpRequest \| None = None, consent_version=...)` already accepts `None` | `06-PII-107`'s precondition already exists and shrinks the diff. Neither precondition closes its finding |
| C-9 | The four alert recipient-selection sites filter on `is_active=True` only | four sites | **Confirmed, plus a fifth `if not user.chat_id` soft gate.** `send_alerts.py` (two `SavedSearch.objects.filter(is_active=True)` sites and one `if not user.chat_id`), `alert_query.py::find_matching_ads` (`Ad.objects.filter(status=AdStatus.PUBLISHED)` at two call sites) and `find_matching_saved_searches`, `immediate_alerts.py` (`_build_payload`'s `if not user.chat_id` and the verbatim `"chat_id": user.chat_id`) | `06-PII-104`'s acceptance criteria must cover all four selection sites plus the two soft gates |
| C-10 | `immediate_alerts` has two unmasked `logger.warning` sites; the fix is "mask the two log sites" | two sites | **Confirmed**, and the fix site is **narrower than "mask the value" implies.** `apps/search/tests/test_immediate_alerts.py` asserts on the **send** argument (`kwargs["chat_id"]` is the real integer) | **A `06-PII-102` fix that masks inside `_build_payload` breaks delivery.** The payload must keep the real `chat_id`; only the value passed to the log formatter is masked. See BLOCK 5 |
| C-11 | `test_support_admin.py` pins the leaky configuration | not named | **Confirmed and unnamed by the report.** `test_support_ticket_admin_list_display`, `..._search_fields`, `..._readonly_fields` assert the exact lists, including raw `chat_id`/`telegram_id` and `text` | `06-PII-106` **must** update this module. The report's rollout row names only `test_admin_pii_containment.py`, which is the wrong file for the assertion change and the right file for the new guard |
| C-12 | `test_consent_context.py::test_declined_user_hides_banner` will break | not named | **Confirmed and unnamed.** `apps/users/tests/test_consent_context.py::TestAuthenticatedState::test_declined_user_hides_banner` asserts `ctx["consent_shown"] is True` for a declined user | Any `06-PII-105` fix that stops hiding the banner breaks it. Project rule 2: fix the test, not the code |
| C-13 | `test_account_state.py` pins `can_login(is_declined=True) is False` | named, correctly | **Confirmed, and broader than stated.** `test_declined_user_cannot_login` **and** `test_banned_and_declined_cannot_login` both pin it. Separately `test_declined_user_can_publish` pins that a declined user **can** publish — which option (a) must preserve | `06-PII-105` option (a) rewrites two assertions and must leave the third green |
| C-14 | `mask_telegram_id` is `sha256(id)[:8]` with a "Non-reversible" docstring | confirmed | **Confirmed verbatim.** No `LOG_MASK_KEY` exists anywhere in `config/settings/`. `config/settings/secret_validation.py` exists (phase 02) with `is_placeholder`, `is_valid_bot_username`, `validate_bot_username` — **the pattern a `LOG_MASK_KEY` guard must follow** | `06-PII-112` adds a secret to a **phase-02-guarded** surface and is gated by `config/settings/tests/test_env_allowlist.py` |
| C-15 | `SellerVerification.phone_number` has no writer | confirmed | **Confirmed.** No `admin.py` in `apps/trust/`; grep over `src/` returns four hits (model field, `0001_initial`, two unrelated test assertions) | `06-PII-111` is a `RemoveField` in the `trust` app, not an erasure-scope change |
| C-16 | `privacy.html` §6/§7 over-promise | confirmed | **Confirmed verbatim.** §6: *"All personal data is permanently erased within **30 days** of withdrawal. Consent state is otherwise retained for 12 months…"*; §7: *"You can revisit and change your consent choices at any time."*; §8 contains a bare `<li>{% trans "Data portability." %}</li>` with **no mechanism anywhere in `src/`** | `06-PII-110`/BLOCK 9 owns §6/§7. The `Data portability.` bullet has no implementation — see §0.5 Q-D11 and §5.6 |
| C-17 | `ConsentRecord.session_key` is in `list_display` and `search_fields` | confirmed | **Confirmed.** `ConsentRecordAdmin.search_fields == ["session_key"]`; `CONSENT_REPROMPT_DAYS = 365` is the natural TTL anchor | `06-PII-116` is gated on a **legal/business** TTL number, not on engineering |
| C-18 | `IMMEDIATE_ALERTS_ENABLED` is `False` by default and in all four env templates | confirmed | **Confirmed.** `base.py` line 362: `IMMEDIATE_ALERTS_ENABLED = env.bool("IMMEDIATE_ALERTS_ENABLED", default=False)`; it **is** already in `ALLOWED_ENV_VARS`. Gated in `apps/moderation/signals.py` | The `06-PII-102` severity argument holds. A live deployment's `.env` is not in the repository — see §0.2.1 |
| C-19 | `purely static, no runtime verification` | — | **This Planner ran no database, no test suite and no migration.** Every claim above is a static read of the tree | §0.2.1 lists what a block must re-verify at runtime before relying on it |

**The tree is a moving target.** The Auditor observed a concurrent phase-02 agent
adding files to the working tree *underneath a static `HEAD`*. **Every file in a
block's surface table must be re-read immediately before editing**, and `AdvisoryLockId`
and `HOURLY_COMMANDS` must be re-checked at that moment rather than trusted from this
snapshot.

#### 0.2.1 Runtime re-verification required before a block relies on a claim

These are cheap and belong to the block's Auditor pre-step, not to the Implementor:

1. `withdraw_consent()` + `consent_hard_delete` really do leave a `SupportTicket` with
   `user_id = NULL` and all raw identifiers intact (`06-PII-101`).
2. The four alert selection sites really do return declined / withdrawn / banned owners
   (`06-PII-104`).
3. An anonymous `POST /consent/accept/` is a silent no-op that still sets the
   `consent_given=accepted` cookie (`06-PII-105`).
4. `UserAdmin.get_form()` field introspection, as superuser and as a plain `is_staff`
   user — **re-derive the field list; do not hard-code "22"** (`04-AUT-005` owns the
   fix; phase 06's BLOCK 10 depends on it landing).
5. **One assertion**: in the Docker test schema, a `QuerySet.update()` on `Ad.title`
   re-derives `search_vector_ru` through `ads_search_vector_update` (C-5). This is the
   single claim whose outcome changes a block's scope.
6. Appending a tenth `HOURLY_COMMANDS` entry does not break `test_scheduler_wiring.py`
   / `test_sweep_lock_structure.py` (`06-PII-116`).
7. `VAL-010`: `config/settings/test.py` hardcodes the connection name, so pytest-django
   always uses the single `test_mko_bazuna`. **Any red gate captured while other phase
   agents are running must be re-run serially before it is reported as a defect.**

### 0.3 Scope statement (explicit)

**In scope — 14 phase-06-owned findings.** `06-PII-101`, `102`, `104`, `105`, `106`,
`107`, `108`, `109`, `110`, `111`, `112`, `113`, `114`, `116`. Plus the two non-finding
work items the report's *Required Fixes* and *Cross-Finding Analysis* demand: the
declarative PII inventory (**Required Fix 1**, BLOCK 3) and the published
DECLINE-reversibility decision (BLOCK 1).

**Not in scope — 2 findings.**

- **`06-PII-103` is merged away to `04-AUT-005` (phase 04, BLOCK 1).** The tree confirms
  `UserAdmin` still declares no `fields`, no `fieldsets`, no `form`, and that
  `withdraw_consent_action` is still decorated `@admin.action` and still **not** assigned
  to `actions` (so still unreachable from the admin UI). **Phase 06 must not patch
  `UserAdmin` again.** Two obligations remain and are carried here: (i) make the
  `is_declined` / `is_deleted` / `ads_auto_publish` **removal** requirement explicit to
  phase 04 so the merged content is not silently dropped (§5.4); (ii) BLOCK 10
  (`06-PII-107`) is **sequenced to depend** on that fix landing.
- **`06-PII-115` is rejected and closed.** The tree confirms the rejection: a bootstrap
  command with an operator-supplied `--username` and `--telegram-id` defaulting to `-1`,
  masking `telegram_id` at all four output paths. **No remediation.**

**Two preconditions already exist and shrink a diff; neither finding is closed.**
`record_consent_action` already accepts `request=None` (C-8) and 12 call sites already
mask (re-verified exactly: `telegram_bot/handlers/login.py` ×1,
`apps/users/views/consent.py::login_status` ×4, `apps/users/admin.py::LoginTokenAdmin.telegram_id_display`,
`apps/core/services/contact.py` ×1, `apps/moderation/admin_actions.py` ×1,
`apps/core/management/commands/create_admin_user.py` ×4). `06-PII-107` and `06-PII-102`
remain **open**.

**One hard rollout gate this plan does not lift.** `IMMEDIATE_ALERTS_ENABLED` must not be
enabled in any environment until `06-PII-102` **and** `06-PII-104` have both landed,
because the immediate path additionally ships a **working deep link** (`build_alert_message`
renders `ad.get_absolute_url()`) to an ad a declined seller's audience may not see, and
because the log leak is derivative of the audience gate.

**Irreducible hazard statement.** `06-PII-101`, `06-PII-109` and `06-PII-116` **destroy
data irreversibly.** There is no soft path and no recovery: a scrubbed `SupportTicket`
identifier, a scrubbed ad body and a purged `ConsentRecord` do not come back. Each is a
separate commit, each has a `--dry-run` or an idempotent precondition where one is
possible, and each is preceded by the one assertion that proves the surrounding mechanism
still works.

### 0.4 Severity corrections

The report's own movement is upheld in full and is **not** re-litigated here:

| ID | Movement | This plan's position |
|---|---|---|
| `06-PII-102` | CRITICAL → **HIGH** | **Upheld.** Default-off flag, failure branches only, recipient's own identifier into an operator log, two-line fix |
| `06-PII-111` | MEDIUM → **LOW** | **Upheld.** The premise (that the product collects the field) is refuted by the tree (C-15) |
| `06-PII-105` | HIGH → **MEDIUM**, reclassified to `DOC-UPDATE + BEST-PRACTICE` | **Upheld.** Ad-hiding and login-blocking are both specified; the residual defect is a broken affordance and a false policy promise |
| `06-PII-108` | reclassified to `DOC-UPDATE + BEST-PRACTICE` | **Upheld, and further narrowed by C-6.** The documentation half is de-scoped (§6.1); the `query_normalized` half is the work |
| `06-PII-113` | reclassified to `DOC-UPDATE`, merged with `04-VAL-005` | **Upheld.** Phase 06 is the finding of record; phase 04 does not edit `spec-index.md` |

**Corrections this Planner makes to the report's supporting detail** (none change a
finding's status):

- **C-4** — the mask-width pin is `11`, not `13`. Do not chase "13".
- **C-5** — `VAL-009` is **overstated**. Treat it as *verify with one assertion*, not as
  *build a mechanism*. This is the single largest scope reduction available in the phase.
- **C-3** — the advisory-lock table is 19 members, not 18; ID 13 is taken. **The sweep
  lock `06-PII-116` would need is no longer free.**
- **C-6** — `06-PII-108`'s documentation half has almost no remaining audience.
- **C-7** — `06-PII-101`'s impact is retention, not discoverability. Acceptance criteria
  must not assert "the row cannot be found".
- **C-11 / C-12 / C-10** — three test blockers the report does not name
  (`test_support_admin.py`, `test_consent_context.py::test_declined_user_hides_banner`,
  and the `test_immediate_alerts.py` **send**-argument coupling).
- **`VAL-005` (rubric defect) is upheld** as an audit-input defect, but this plan does
  **not** action it in code; it is routed to the coordinator (§5.7).

### 0.5 Open technical questions — resolved here, or explicitly gated in their block

**This plan does not choose where technical uncertainty exists.** Each question below
produces either a pre-block step (Researcher / Planner) or a labelled
**decision required before implementation** gate inside the named block, with the options
and their consequences. Silence is not an acceptable outcome for any of them.

| ID | Question | Block | Who decides | Status |
|---|---|---|---|---|
| **Q-D1** | **Is DECLINE reversible?** Option (a) drop `is_declined` from `can_login`, keep it in `can_publish_ad` and the bot publish gate; option (b) intentionally one-way, with corrected `privacy.html` §7 and a warning before live listings disappear | **BLOCK 1** | **Owner (product)**, published by Planner; Researcher supplies the consequences; Auditor verifies the code/spec correspondence | **GATED — the first scheduled decision in this plan.** Phase 04's BLOCK 6 is hard-gated on it |
| **Q-D2** | **`06-PII-101`: what replaces the ticket's identity as a support lookup key, and which storage shape?** Nullable columns + sentinel backfill vs. a `0` sentinel vs. deleting the row | **BLOCK 13** | **Owner (product)** — this is a product decision, not an engineering one; Planner publishes the options | **GATED** |
| **Q-D3** | **`06-PII-109`: scrub the ad text, or correct the spec's "anonymized" wording?** | **BLOCK 11** | Owner (product) for the scope question; Researcher for the placeholder shape | **GATED** |
| **Q-D4** | **`06-PII-116`: the `ConsentRecord` TTL number, and the sweep's lock** — reuse an existing id with a written rationale, or allocate a new one (now `14`+) | **BLOCK 15** | TTL: **business/legal**. Lock: Planner + **coordinator** (three-file one-commit change) | **GATED** |
| **Q-D5** | **`06-PII-108`: redact `query_normalized`, or store a keyed digest?** The anonymous **session** store (`_record_session_history`) has the same raw/redacted split and needs the same treatment | **BLOCK 14** | Researcher + Planner | **GATED** |
| **Q-D6** | **`VAL-003`: who owns the queryset-level account-state predicate, and what is its exact shape?** Phase 15 owns the framework; phase 06 owns the semantics. A **default-manager filter is forbidden** | **BLOCK 6** | Researcher + Planner, **confirmed with the coordinator** so phase 15 does not fork it | **GATED** |
| **Q-D7** | **`06-PII-107`: wire or remove `UserAdmin.withdraw_consent_action`**, and what is the shape of the consent context object | **BLOCK 10** | Planner (wire-or-remove) + Researcher (context shape) | **GATED** |
| **Q-D8** | **`06-PII-112`: `LOG_MASK_KEY` provenance (same source as `SECRET_KEY` or independent?), required-in-production or defaulted, and the rotation policy** | **BLOCK 4** | Owner (security) + Planner; Researcher on the `prod.py` guard shape | **GATED** |
| **Q-D9** | **Required Fix 1: what is the PII inventory's exact shape** — a `StrEnum`/`dataclass` registry, model annotations, or keep the hand-maintained list plus a guard test | **BLOCK 3** | Researcher + Planner | **GATED** |
| **Q-D10** | **`06-PII-110`: does nulling `preferred_city` on DECLINE survive `_reconcile_preferred_city_on_login`?** | **BLOCK 9** | Researcher + Planner | **GATED** |
| **Q-D11** | **Is data-subject access in scope at all?** No export/DSAR path exists anywhere in `src/`; `privacy.html`'s *"Data portability."* is a bare bullet | — (no block) | **Owner (product) + coordinator** | **ROUTED, not planned.** Export is a **new capability**, not a remediation. See §5.6 and §6.1 |
| **Q-D12** | **`VAL-007`: the exact shape of the "declared set of data-subject identity columns"** — a blanket registry walk false-positives on `SupportContactAdmin` | **BLOCK 12** | Researcher + Planner | **GATED** |
| **Q-D13** | **`VAL-004` / `VAL-005`: correcting the phase-06 audit rubric** (it contradicts the authoritative spec and over-rates log sinks) | — (no block) | **Coordinator** | **ROUTED.** The audit-input tree is not phase 06's to edit. See §5.7 and §6.1 |

---

## 1. Environment and command contract for the implementor

**This environment is Windows 11 / PowerShell 7.** `make` requires WSL or GNU Make; use
`.\Makefile.ps1 <target>`. `head` / `tail` are unavailable in PowerShell.

### 1.1 Tests are Docker-only — `uv run pytest` on the host always fails

There is no PostgreSQL on `localhost:5432`. Every test run goes through the `test`
service of the `mko-bazuna-test` Compose project.

```powershell
# Fast gate (skips the nightly `seed` suite) - the default iteration command
$dc run --rm --env PYTEST_SKIP_MARKERS=seed test

# Targeted run
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="-k test_name" test
$dc run --rm -e PYTEST_OPTS="src/backend/apps/users/tests/test_deletion.py --tb=short" test

# Full suite (only when the change touches seeding or images)
$dc run --rm test

# Fresh schema - MANDATORY after any migration lands in this plan
$dc run --rm --env PYTEST_OPTS="--create-db --tb=short -n auto --maxprocesses=4 --dist loadgroup" test
```

with, copied once per session:

```powershell
$dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'
```

**Two caveats that will silently produce a wrong result if ignored:**

- `--env-file .env.test` is **required**. Without it compose aborts on `${POSTGRES_*?}`
  interpolation. Never substitute the `mko-bazuna-dev` project name.
- Setting `PYTEST_OPTS` **replaces** the defaults
  (`--reuse-db --tb=short --durations=10 -n auto --maxprocesses=4 --dist loadgroup`), so a
  targeted run loses xdist parallelism and DB reuse. Never use
  `--override-ini=addopts=` — it strips `--import-mode=importlib`, which `pyproject.toml`
  requires.
- **`VAL-010`:** concurrent runs collide on the single `test_mko_bazuna` database. If a
  gate goes red while other phase agents are running, **re-run it serially** before
  reporting it as a defect. Teardown races surface as
  `FATAL: database "test_mko_bazuna" does not exist` and `relation "..." does not exist`,
  not as product failures.

Canonical wrappers `.\Makefile.ps1 up | test | test-all | test-recreate | test-down`
manage the project name and env file for you. Prefer them.

### 1.2 Lint, typecheck, i18n

```powershell
uv run ruff check <path>            # lint
uv run ruff check --fix <path>      # auto-fix, including import sorting (I001)
uv run basedpyright <path>          # typecheck
uv run djlint src/backend/templates/   # only if a template changes
```

**i18n is part of DoD.** Every user-visible string is wrapped in `{% trans %}` /
`{% blocktrans %}` (templates) or `gettext` / `gettext_lazy` (Python). `msgstr` must be
**non-empty** for `ru` and `bs`; `en` may be empty (the msgid is English). `.mo` files are
gitignored and compiled at image build, at container start, and in the CI `i18n` job.
`make makemessages` / `make compilemessages` **do not work** on Windows + Docker Desktop;
use the lightweight `--no-deps --entrypoint ""` form in `.kilo/rules/commands.md` if a
`.po` actually has to change. Run `apps/ads/tests/test_i18n_completeness.py` after any
string change.

**BLOCK 8 is the block that trips this gate** (`VAL-006`). Its i18n failure is a
**consequence of the fix, not a regression from it**, and must not be triaged as one.
Sequence: `.po` updates in the **same commit** as the template change. **Append** to the
locale files; never run a wholesale `makemessages` that would discard a concurrent phase
(14 owns the runtime i18n tree).

**A known-good Python 3.14 idiom that is not a bug.**
`apps/users/context_processors.py::_is_expired` uses `except TypeError, ValueError:`
**without parentheses** (PEP 758). It is valid. **Do not "fix" it**, and do not let a
formatter configured for an older Python rewrite it.

### 1.3 Git contract — one implementor, sequential, one commit per block

- **One Implementor at a time.** Never two. Never a background implementor.
- If a block is stopped mid-way, **resume the existing session**; do not launch a new agent.
- Each block is committed separately, explicitly staged: `git add <specific files>` —
  never `git add -A`, never `git add .`.
- Message form, matching the repo style:
  `"{type}({scope}): {description}"`, e.g.
  `feat(users): declare the PII erasure inventory (06-PII-101)`,
  `fix(search): mask the alert failure logs (06-PII-102)`,
  `docs(spec): resolve the DECLINE-semantics conflict (06-PII-113)`.
  Every new citation is **cycle-scoped** (`06-PII-1xx`), never bare `PII-1xx`.
- **Never** `git reset`, `git checkout`, `git restore`, `git stash`, `--amend`,
  `--no-verify`, or any other history mutation. Never force-push.
- **Other agents are working in parallel.** Files you did not change appearing in
  `git status` is normal. **Never** revert, stash or `git checkout` a file you did not
  write. If a file you are about to edit already has uncommitted changes from another
  agent, **stop and report it** rather than clobbering it.
- Do not commit unless the block's instructions say to.

### 1.4 Standing project rules (restated for every block)

- **English only** — comments, logs, docstrings, error messages, docs.
- **No `print()`.** `logger = logging.getLogger(__name__)` with lazy `%s` formatting.
- Stack: Python 3.14 · Django 5.2 LTS (`>=5.2.16,<6.0`) · PostgreSQL 18 · aiogram 3.x ·
  native PostgreSQL FTS. **Two processes, one DB:** web (gunicorn sync WSGI, HTMX MPA)
  and bot (aiogram, `django.setup()` + shared ORM). **Migrations run exactly once** before
  both start — a migration that must run in only one process is a defect.
- The bot FSM has no built-in PG storage: the ad dialog is persisted as an `Ad` row in
  `DRAFT` via the ORM.
- **Django ORM is the persistence layer.** Pydantic v2 is used **only** at system
  boundaries (bot input, settings schemas). Do not introduce Pydantic DTOs into the
  view/service path. (`apps/moderation/schemas.py` already owns the moderation
  boundary DTO — follow it, do not copy it inward.)
- **All schema changes via Django migrations.** No hand-written DDL. Migration numbers are
  sequential **per app**; **never renumber or edit an existing migration.** Check the
  directory immediately before generating.
- **Fixed values via `StrEnum`** (project rule 10) — never plain strings, dicts or lists.
  Existing in-repo precedent: `login_token.ConsumeOutcome`, `CookieCategory`,
  `SupportTicketStatus`.
- **All schema changes** are mirrored in `docs/02-database/db-schema.md`.
- Small, focused modules and functions. **Composition over inheritance.** Follow existing
  patterns; **no new abstraction without strong justification**; no speculative
  redesign; no scope creep. Prefer the simple, obvious solution (project rule 5).
- **Production code is king.** If a test conflicts with the architecture or the business
  logic, **fix the test** — and say which change and why in the commit body. This plan
  slates **nine** test assertions for exactly that treatment (BLOCK 4 ×1, BLOCK 8 ×3,
  BLOCK 12 ×3, BLOCK 15 ×2); each block names the test and the
  justification.
- **The hard-deletion path must keep working.** `consent_hard_delete` (hourly, under
  `AdvisoryLockId.CONSENT_HARD_DELETE == 3`) deletes a user's rows 30 days after
  withdrawal and is pinned by `test_sweep_consent.py`, including the crash-rollback
  test. Any scrub added to it must be **inside the same `transaction.atomic()`**, or the
  rollback guarantee breaks.

### 1.5 Test authoring standard for every block

Tests verify **logic and component interaction**, not implementation trivia. No test that
asserts a literal private name, a line number, a template-string substring, a column
count, or the mere presence of a symbol. Assert on **absence of danger** and on
**observable behaviour**, never on a count the report produced by introspection.

Good targets for this phase:

- after `withdraw_consent()`, a ticket belonging to that seller no longer carries a raw
  `chat_id`, `telegram_id` or `username` — **and a ticket belonging to a different seller
  is untouched**;
- a `SavedSearch` owned by a withdrawn / declined / banned user never appears in
  `send_alerts._collect_alerts`, in `_dry_run_check`, in
  `find_matching_saved_searches`, or in `find_matching_ads`;
- the same four call sites are driven by **one** declaration — proven by a test that a
  single change to that declaration moves all four;
- a `SearchHistory` row written by a search containing a phone number and an e-mail
  address does not contain either in **any** column, in the database **and** in the
  session store;
- the two `immediate_alerts` failure branches emit a log record whose formatted message
  does not contain the raw `chat_id`, **while a captured send still receives the real
  integer**;
- `purge_consent_records --dry-run` deletes nothing; a real run deletes a row past the TTL
  and **keeps** a row inside it.

Fixtures are canonical in `src/backend/conftest.py`: `seller` (900000001), `user`
(900000002), `category`, `city`, and
`create_test_ad(user, category, city, *, status=AdStatus.PUBLISHED, **kwargs)`.
`src/telegram_bot/tests/conftest.py` redefines these as an **async** `user`; bot tests
cannot import the backend conftest.

**Never use a line number as a task target.** Every target is a file plus a **semantic**
anchor: a class, a method, a module-level constant, a named attribute, a function call,
a URL route name, a template block.

### 1.6 Task shape for every block

Each block's implementor task follows `.ai\tasks\templates\task_template.yaml`: semantic
`targets` with `type` / `name`, `semantic_anchors`, `changes`, `acceptance_criteria`,
`source_reference` / `source_section` / `source_blocks`, and an `extra_context` block
carrying the block's binding constraints verbatim. Verification is **inline** for
low/medium-risk blocks (the Implementor runs `tests_to_run` and checks
`acceptance_criteria`); a **separate Validator task** is required for every **HIGH** or
**CRITICAL** block, and for every block whose acceptance depends on a decision the
Implementor was told not to make.

---

## 2. Scope decisions table (acceptance contract for execution)

| ID | Disposition | Block | Final severity | One-line reason |
|---|---|---|---|---|
| `06-PII-101` | **implement — but blocked on a product decision (Q-D2).** Storage shape and the replacement correlation key are **not** decided by this plan | BLOCK 13 | **CRITICAL** | The only confirmed CRITICAL. A provable, silent breach of the published 30-day erasure promise; needs a `core`-app nullable migration + data migration, and destroys support's only correlation key |
| `06-PII-102` | **implement — two log sites only.** Masking `_build_payload` is **forbidden** (C-10) | BLOCK 5 | HIGH | Real spec violation, two-line fix, no data risk. The payload must keep the real `chat_id` or delivery breaks |
| `06-PII-103` | **merged away — no work item here.** Two obligations routed to §5.4 and BLOCK 10's dependency | — | HIGH (absorbed) | Same root cause, byte for byte, as `04-AUT-005`. Two patches to the same class would each be partial. Phase 06 must not touch `UserAdmin`'s field contract |
| `06-PII-104` | **implement — split in two.** The shared predicate is one block; the four call sites are another | BLOCK 6 (predicate) + BLOCK 7 (call sites) | HIGH | The only audit path that is **live today** (daily, ungated). A default-manager filter is forbidden; one declaration must drive all four sites |
| `06-PII-105` | **implement — decision first (Q-D1, BLOCK 1), then BLOCK 8.** A session-independent recovery path, a discoverable affordance and a non-silent anonymous Accept are required **under either option** | BLOCK 1 (decision) + BLOCK 8 (code) | MEDIUM | The advertised consequence is operator-recoverable and the behaviour is spec-sanctioned; the residual defect is a dead-end UI plus a false policy statement. Option (a) changes the auth predicate |
| `06-PII-106` | **implement** — masked `list_display`, drop `text` from `search_fields`, declared data-subject-column guard | BLOCK 12 | MEDIUM | The model's own `readonly_fields` already marks these read-only on the change form; the changelist and the search index were never brought under the rule `LoginTokenAdmin` already follows. **Must update `test_support_admin.py`** (C-11) |
| `06-PII-107` | **implement — gated on `04-AUT-005` landing and on a wire-or-remove decision (Q-D7)** | BLOCK 10 | MEDIUM | The audit write lives in the view, outside `withdraw_consent()`'s transaction. `technical-specification.md` §F explicitly promises a row for every accept/decline/withdraw, so this is a spec deviation, not merely a structural gap. The precondition already exists (C-8) |
| `06-PII-108` | **implement the substantive half only** — `query_normalized` in the database **and** in the session store. The documentation half is **de-scoped** (§6.1) | BLOCK 14 | MEDIUM | The doc half has almost no audience left (C-6): both public surfaces already scope "Analytics" to Plausible. The un-redacted key is a real retention defect inside the same tables |
| `06-PII-109` | **implement — gated on a scope decision (Q-D3)** | BLOCK 11 | MEDIUM | The spec's "anonymized" is ambiguous. Scrubbing destroys user content irreversibly, so the choice is a product one. **`VAL-009` is not a constraint** (C-5): verify with one assertion, build nothing |
| `06-PII-110` | **implement the kept half** — clear `preferred_city` on DECLINE and on withdrawal, delete `SearchHistory` on withdrawal, and make `privacy.html` §6 enumerate what is erased and what is retained-and-why. The `ConsentRecord` half is **absorbed by `06-PII-116`** | BLOCK 9 | MEDIUM | `chat_id` is retained **deliberately** — `AccountStateMiddleware` resolves on it so withdrawn identities stay blocked. Nulling it is forbidden. The defect is the un-reconciled retention and the cookie/column asymmetry |
| `06-PII-111` | **implement** — `RemoveField` migration in the `trust` app | BLOCK 17 | LOW | Nothing writes it and the `trust` app has no `admin.py`; the column is vestigial, permanently `NULL` and undisclosed. Dropping it is strictly simpler than adding it to an erasure scope |
| `06-PII-112` | **implement — one unit with `06-PII-102`**, shipped as two ordered commits. Gated on Q-D8 | BLOCK 4 | MEDIUM | A 32-bit truncated unsalted digest over a ~2^34 input domain is invertible by enumeration; the spec's "non-reversible" claim is false. Adds a secret to a **phase-02-guarded** surface |
| `06-PII-113` | **implement — docs only**, one owner (phase 06), plus the rubric correction **routed to the coordinator** | BLOCK 2 | MEDIUM | The code matches `technical-specification.md`; the stale `spec-index.md` line is the defect. Leaving a document asserting a behaviour the code does not have is worse than either state alone |
| `06-PII-114` | **implement** — write-time redaction of `ModeratorActionLog.reason` and `Ad.rejected_reason` | BLOCK 16 | LOW | Staff-authored free text can contain the subject's data, in a row erasure can no longer associate with. `redact_search_query` never lengthens, so applying it is column-safe (confirm at implementation) |
| `06-PII-115` | **rejected — no work item** | — | — | Factually wrong privacy claim: the command creates a *local* bootstrap admin with an operator-chosen username and a placeholder `telegram_id=-1`, and masks `telegram_id` at every occurrence |
| `06-PII-116` | **implement — gated on a legal TTL (Q-D4) and on a lock decision that is no longer free (C-3)** | BLOCK 15 | LOW | Unbounded retention of a live `session_key` plus browser-fingerprint-grade data, with no stated period. The sweep is destructive and must be ordered so it can never delete a row still needed for an Art. 7(1) demonstration |
| **Required Fix 1** | **implement — gated on a shape decision (Q-D9)** | BLOCK 3 | — (architectural) | Five findings in this phase share one root cause: the erasure contract is a hand-maintained `update_fields` list on one model. A single registry turns each individual fix into a lookup. **Must be justified against the simpler "keep the list, add a guard test" alternative** (project rule 5) |
| `VAL-003` | **binding constraint** — one queryset-level predicate, owned by `apps/users`, consumed by all four alert call sites; **a default-manager filter is forbidden** | BLOCK 6 (gate) | HIGH (cross-phase) | A hand-written copy in `apps/search` is a second place to forget the next flag. This phase already found three flags missing from one call site |
| `VAL-007` | **binding constraint** — the containment guard must be an explicit declared set of **data-subject** identity columns | BLOCK 12 | MEDIUM | A blanket registry walk false-positives on `SupportContactAdmin`, whose `telegram_id` is a configured support-channel id, not a data subject's |
| `VAL-008` | **binding constraint** — the spec line and the function docstring move in the same commit as the construction | BLOCK 4 | LOW | Shipping the fix without them leaves a false security claim in the codebase; shipping neither makes the claim itself the finding |
| `VAL-009` | **overstated — verify, do not engineer.** One assertion in `test_setup_search_triggers.py` | BLOCK 11 | — | The vectors are maintained by a row-level `BEFORE INSERT OR UPDATE ... FOR EACH ROW` trigger, so any UPDATE re-derives them for free (C-5) |
| `VAL-010` | **process constraint, not code** — re-run a red gate serially before reporting it | §1.1 | — | Concurrent validators share one `test_mko_bazuna`; teardown races manufacture red gates |
| `VAL-011` | **convention** — all citations are cycle-scoped `06-PII-1xx` | §0.1, plan-wide | LOW | Bare `PII-1xx` already collides with shipped in-source markers from a prior cycle |
| `VAL-012` | **process constraint, not code** — a probe must override the connection before the first ORM call | §0.2.1 | — | `config/settings/test.py` hardcodes `mko_bazuna`, a phantom database (39 tables, no `django_migrations`) |
| **Required Fix 2** (the `PII-101` cluster's architectural prerequisite) | see **Required Fix 1** above | BLOCK 3 | — | Same registry; it is the mechanism that makes BLOCK 13's decision a lookup instead of a fresh audit |
| **Q-D11** (data-subject access) | **ROUTED, not planned** | — | — | No export/DSAR path exists anywhere in `src/`; `privacy.html`'s *"Data portability."* is a bare bullet. Export is a **new capability**, not a remediation. §5.6, §6.1 |
| **Q-D13** (audit-rubric correction) | **ROUTED to the coordinator** | — | — | `.kilo/commands/audit/phases/06-audit-pii-consent.md` is audit-input territory. §5.7, §6.1 |

---

## 3. Execution blocks

Seventeen blocks. Three are **decision or architecture** blocks that ship no
production behaviour (BLOCK 1, BLOCK 3) or ship documentation only (BLOCK 2); fourteen
are implementation blocks. **One Implementor, strictly sequential, one commit per block**
(§1.3).

Two blocks (**3** and **4**) have no dependency on anything in this plan and can be
prepared in parallel by the Auditor/Researcher while BLOCK 1's decision is being made —
but the **serial execution order is still 1 → 17** (§4.1), because BLOCK 1 is what
unblocks another phase.

### BLOCK 1 — Publish the DECLINE-reversibility decision (06-PII-105, decision half)

| | |
|---|---|
| **Findings owned** | `06-PII-105` (decision half), `VAL-001` (adjudication input) |
| **Depends on** | **nothing** — the entry point of the plan and of the phase |
| **Blocks** | BLOCK 2, BLOCK 8, and **phase 04's BLOCK 6** (external, hard) |
| **Priority** | **P0** — the only block whose output is consumed by another phase |
| **Risk level** | **Process** (no code, no data, no migration) |
| **Required agents** | **Auditor · Researcher · Planner** (all three). **Implementor not required** — this block ships no code. **Validator required** to confirm the decision is published, uncontradicted, and cited by the tracker |

**Why this is first.** `.ai/plans/04-auth-login-remediation.md` §5.4 states verbatim:
*"BLOCK 6 must not ship the decline-path logout before `PII-105` is decided. **Neither
report records this dependency.**"* Phase 04's Q8 is therefore blocked on this phase.
**If phase 06 stays silent, phase 04 stalls.** This block is therefore scheduled first and
has no prerequisites of its own.

**What this block is.** A **written decision**, published in this plan file and in the
tracker, between two named options. It is explicitly **not** a code change and it is
explicitly **not** this Planner's to make. The spec itself sanctions a silent, effectively
irreversible takedown of live listings as a side effect of clicking a cookie banner; that
is a product decision.

**Decision required before implementation — Q-D1**

| Option | What it is | Consequences the owner is choosing between |
|---|---|---|
| **(a)** | DECLINE is **reversible by design**: remove `is_declined` from `can_login()`, keep it in `can_publish_ad()` and in the bot's publish gate | **Gains:** a first-class escape hatch; the session-lifetime dependency disappears; the "silent permanent loss of ad visibility" failure mode is removed. **Costs:** one spec edit (`technical-specification.md` §F/§K, `spec-index.md`); a declined user regains **web login** and can reach `/dashboard/` — a change to the **auth predicate** that needs its own security review; `test_account_state.py::test_declined_user_cannot_login` and `::test_banned_and_declined_cannot_login` must be rewritten (project rule 2), while `::test_declined_user_can_publish` must stay green; must be coordinated with `04-AUT-002`, which touches the same predicate |
| **(b)** | DECLINE is **intentionally one-way** | **Gains:** no change to the auth predicate; no security review of a regained login. **Costs:** it must not silently un-publish existing ads without warning, and `privacy.html` §7 must be corrected to say the choice is final for seller features; the recoverability question ("`pending_erasure` state" — the report's advisory 5) becomes a design item rather than a courtesy |

**Required under either option** (these are not optional and are BLOCK 8's scope):
a first-class, **session-independent** recovery path; a discoverable affordance that does
not depend on `?ref=preferences`; and a **non-silent** anonymous Accept. The distinction
between the options is only what happens to `can_login()` and to the copy.

**Evidence the Auditor must assemble for the decision** (not decided here):

1. Re-verify that `can_login()` still returns `False` for `is_declined` and that
   `consent_accept` still calls `give_consent()` only under `if user is not None` — the
   silent no-op.
2. Re-verify that `consent_decline` still does **not** flush the session, and that
   `consent_state` still sets `consent_shown = True` whenever `user.is_declined`, with
   `?ref=preferences` as the only override.
3. State the **blast radius of option (a)** precisely: which views a declined user could
   newly reach, and whether `can_publish_ad` (which must stay `True`) already lets them
   publish without a session.
4. Re-verify the `technical-specification.md` §K wording that both options must be
   consistent with, and that the code matches it today (the report's V-04/V-05 basis).

**Deliverables**

- The decision, the options as stated above, the owner's reasoning, and the date, recorded
  in a new section of this plan file (or a decision record beside it).
- An entry under `06-PII-105` in the coordinator's tracker stating option (a) or (b).
- A one-line cross-reference recorded for phase 04's BLOCK 6, unblocking it.
- A statement of whether option (a) or (b) changes the **BLOCK 8** scope.

**Implementor task** — *none.* This block is a Planner/Researcher deliverable. The
follow-on BLOCK 8 carries the implementor task.

**Risk and rollback**

- *Risk:* the decision is made implicitly by whoever implements first. Mitigation: BLOCK 8
  may not start until this block's record exists, and BLOCK 8's task YAML carries
  "decision reference required".
- *Rollback:* none needed; nothing is shipped.
- *Cross-phase:* **this is the single highest-value output of the phase.** Phase 04 is
  waiting on it.

---

### BLOCK 2 — Adjudicate the DECLINE documentation conflict (06-PII-113, VAL-001, VAL-004)

| | |
|---|---|
| **Findings owned** | `06-PII-113`, `VAL-001` (phase 06 is the finding of record), `VAL-004` (routed, §5.7) |
| **Depends on** | BLOCK 1 (the reversibility sentence is written **once**, with the decision) |
| **Blocks** | BLOCK 8 (its copy edits must not race this block's) |
| **Priority** | P1 — documentation only, zero code risk, but it is the direct cause of a mis-rated finding |
| **Risk level** | **LOW** (docs only) |
| **Required agents** | **Auditor · Planner**. **Researcher not required** (the adjudication is already made: the code matches the technical specification). **Validator required** — a second reader must confirm the three sources no longer disagree |

**Why this is a block and not a line edit.** Three current sources give two — arguably
three — different answers to the single most consequential consent decision in the
product. The validator adjudicated: the code matches `technical-specification.md`; the
condensed index and the audit rubric are wrong. **Phase 06 owns this edit** (phase 04's
§5.6 confirms phase 04 does not touch `spec-index.md` for this). The same edit is also the
place to record BLOCK 1's reversibility answer, which is why the edge to BLOCK 1 exists.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `docs/01-spec/spec-index.md` | the decision-**K** bullet, currently *"DECLINE blocks seller login only (no erasure, contact still works)"* | The stale line. Rewrite to match `technical-specification.md` §F/§K, and state whether DECLINE is reversible, referencing the BLOCK 1 decision record. **Do not touch `technical-specification.md` §F/§K** — it is the most precise of the three |
| `.kilo/commands/audit/phases/06-audit-pii-consent.md` | the runtime-verification step asserting *"existing ads remain public/searchable"* | **CONDITIONAL — see the gate below** |
| `.ai/audit/99-validation/06-pii-consent-validated-findings.md`, `.ai/plans/04-auth-login-remediation.md` | cross-references | **Do not edit** the validated report (audit tree, unmodifiable). Record the `04-VAL-005` cross-reference **in this plan**, not in phase 04's file |

**Gate — coordinator authorisation required before touching the audit rubric.** The
validator asks that the phase-06 handbook be corrected so a future run does not re-derive
`06-PII-113` and re-file a mis-rated `06-PII-105`. The handbook is **audit-input
territory**, not product documentation, and this plan's mandate does not extend to it.
**This block must ask the coordinator first.** If authorisation is not granted, the block
ships the `spec-index.md` edit alone and the rubric correction is recorded as an open
coordinator deliverable (§5.7). Do not edit the rubric unilaterally.

**Implementor task**

```yaml
id: task_06_b02_decline_docs
title: "Resolve the DECLINE-semantics documentation conflict (06-PII-113)"
priority: medium
depends_on: [task_06_b01_decline_decision]
source_reference: ".ai/plans/06-pii-consent-remediation.md"
source_section: "BLOCK 2 - Adjudicate the DECLINE documentation conflict"
source_blocks: ["BLOCK 2"]
description: >
  Three sources disagree on what DECLINE does to already-published ads. The code
  matches docs/01-spec/technical-specification.md (sections F and K), which states
  that DECLINE blocks seller login/actions AND hides the user's PUBLISHED ads from
  public search/listings, direct URL access and the media gate. The condensed index
  line in docs/01-spec/spec-index.md is stale, and this phase's own audit rubric
  asserts a third answer. Phase 06 is the finding of record; phase 04's 04-VAL-005
  is a cross-reference. The same edit must record the BLOCK 1 reversibility decision.
goals:
  - "make all product documentation state one behaviour, the one the code implements"
  - "record whether DECLINE is reversible, per the BLOCK 1 decision"
  - "leave technical-specification.md sections F and K unchanged"
files:
  - path: "docs/01-spec/spec-index.md"
    targets:
      - type: document_section
        name: "decision K bullet"
    semantic_anchors:
      replace_text_containing:
        type: literal
        value: "DECLINE blocks seller login only"
  - path: ".kilo/commands/audit/phases/06-audit-pii-consent.md"
    targets:
      - type: document_section
        name: "runtime verification step"
    semantic_anchors:
      replace_text_containing:
        type: literal
        value: "existing ads remain public"
changes:
  - action: doc_update
    description: >
      Rewrite the spec-index decision-K bullet to state that DECLINE blocks seller
      login/actions AND hides the user's PUBLISHED ads from public search, listings
      and direct URL access. Add one sentence recording the BLOCK 1 reversibility
      decision and cross-referencing its record. Edit the audit rubric ONLY if the
      coordinator has authorised it in writing.
    code_hint: |
      # Do not paraphrase the technical specification - mirror its wording so the
      # two documents can be diffed against each other later.
acceptance_criteria:
  - "no current source states that DECLINE leaves existing ads public/searchable"
  - "the reversibility answer from BLOCK 1 appears verbatim in spec-index.md"
  - "technical-specification.md sections F and K are byte-identical to before"
  - "the audit rubric is unmodified unless coordinator authorisation is recorded in the commit body"
tests_to_run: []
```

**Tests required** — none. `apps/core/tests/test_privacy.py` does **not** assert the §6/§7
wording, and nothing asserts `spec-index.md`. The block's gate is a second reader, not a
test. If a doc-lint exists in CI, run it.

**Risk and rollback**

- *Risk:* editing `technical-specification.md` by mistake, which phase 04 also touches under
  its BLOCK 8 option (c). Mitigation: the acceptance criterion forbids it and the block's
  file list omits it.
- *Risk:* a concurrent phase edits `spec-index.md`. Mitigation: §1.3 staging rule; re-read
  immediately before editing.
- *Rollback:* a straight revert. No data.

---

### BLOCK 3 — One declarative PII erasure inventory (Required Fix 1)

| | |
|---|---|
| **Findings owned** | The report's **Required Fix 1** (no finding ID of its own; it is the shared root cause of `06-PII-101`, `109`, `110`, `111`, `114`) |
| **Depends on** | **nothing** |
| **Blocks** | BLOCK 9, BLOCK 13 (they become lookups instead of fresh audits) |
| **Priority** | **P0** — it is the architectural prerequisite, and five findings become one-line changes once it exists |
| **Risk level** | **MEDIUM** — a new module in the erasure path, with a real over-engineering risk that must be argued, not assumed |
| **Required agents** | **Auditor · Researcher · Planner · Validator** (all four — the block creates a new abstraction in a destructive path, and the project rule 5 objection must be answered in writing) |

**Why it is a block and not an instruction.** The erasure contract is a hand-maintained
`update_fields` list on one model. Any table that denormalises identity
(`support_tickets`, `ads.*text`, `seller_verifications`, `moderation_action_logs.reason`,
`chat_id`, `preferred_city`) falls out of scope the moment it is added, and **no check
enforces membership**. Without a registry, the sixth such column appears with the next
model. With one, BLOCK 13's `SupportTicket` decision becomes a registry entry rather than
a bespoke code path.

**Decision required before implementation — Q-D9 (shape)**

| Option | What it is | Maintainability | Future evolution | Project-convention fit |
|---|---|---|---|---|
| **A** | A module-level registry in `apps/users/services/` — a frozen mapping (or a `StrEnum`-keyed structure) of *model → identity column → erasure action*, consumed by `withdraw_consent()`, `consent_hard_delete` and the data migration | **Highest.** One declaration, three consumers, impossible to drift between the service and the migration | A new identity column is a **one-line registry addition**; the guard test makes the omission loud | **Best.** Plain module-level data + a `StrEnum` for actions (project rule 10); no new base class, no metaclass, no app-wide machinery |
| **B** | Model-level metadata — an attribute or `Meta` entry on each model declaring its identity columns | Medium: keeps the declaration next to the column, but the erasure code must import and reflect over five apps, and Django `Meta` is not a natural home for policy | Good locality, but introduces cross-app import direction (`users` → `core`, `ads`, `trust`, `moderation`) | Weak: `Meta` is schema metadata; policy in it is a category error |
| **C** | **No registry.** Keep the hand-maintained list and add a **guard test** that walks the user-adjacent models and fails when a new identity-looking column is not enumerated | Lowest code, lowest risk, fastest | The test is the enforcement; adding a column still requires editing the list — but the *omission becomes impossible to ship silently*, which was the actual defect | **Best by rule 5** (avoid overengineering) |

**This plan does not choose.** The strong prior is **A or C**, and the Researcher must
argue it: A is the durable fix the report asks for; C is a strictly smaller change that
converts a silent omission into a loud test failure. **A third path the Researcher should
consider: A's registry *plus* C's guard** — the declaration and the tripwire, which is what
phase 03's BLOCK 11 sweep argues for as a general pattern. The decision, the argument, and
the rejected alternative are recorded in the commit message.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/users/services/pii_inventory.py` (new) or an existing `services/` module | the registry declaration | Location is the Researcher's call; `apps/users/services/` already owns `deletion.py`, `account_state.py`, `consent_record.py` |
| `src/backend/apps/users/services/__init__.py` | the re-export surface | Only if the registry is re-exported; `deletion.py` currently imports only `apps.ads.models`, `apps.core.enums.AdStatus`, `apps.search.services.cache`, `apps.users.models` — **watch the import direction** |
| `src/backend/apps/users/services/deletion.py` | `withdraw_consent` — consume the registry instead of the inline list | **BLOCK 3 only declares the registry.** Consumption is BLOCK 9's and BLOCK 13's edit to the same function, and the serial edge exists for exactly that reason |
| `src/backend/apps/users/tests/test_pii_inventory.py` (new) | the guard / registry-membership test | New module. If option C is chosen, this is a **migration-completeness** test instead |

**Binding constraints**

1. The registry is **data**, not behaviour. No base class, no metaclass, no app registry
   hook, no import-time side effect.
2. The erasure actions are an **`StrEnum`** (project rule 10): at minimum `CLEAR`,
   `NULL`, `DELETE_ROW`, and — for BLOCK 13's `chat_id` — a documented `RETAIN` with a
   stated reason. **`RETAIN` must exist**, because `User.chat_id` is a legitimate
   retention that a naive "everything is cleared" registry would silently violate.
3. The registry must be **importable without a database connection** so a data migration
   can consume it in a `RunPython`.
4. It must not be imported by the bot process in a way that changes bot behaviour —
   `apps.*` must never import `telegram_bot.*`.

**Implementor task**

```yaml
id: task_06_b03_pii_inventory
title: "Declare the PII erasure inventory (Required Fix 1)"
priority: high
depends_on: []
source_reference: ".ai/plans/06-pii-consent-remediation.md"
source_section: "BLOCK 3 - One declarative PII erasure inventory"
source_blocks: ["BLOCK 3"]
description: >
  The erasure contract is a hand-maintained update_fields list on one model, and
  five findings in this phase are symptoms of that. Declare one inventory of
  model -> identity column -> erasure action, plus the guard that makes a new
  identity column impossible to ship silently. Do NOT change withdraw_consent's
  behaviour in this block; consumption belongs to BLOCK 9 and BLOCK 13.
goals:
  - "give the erasure contract one declaration with a documented RETAIN escape"
  - "make an omitted identity column a loud test failure rather than a silent leak"
  - "keep the declaration importable without a database connection"
files:
  - path: "src/backend/apps/users/services/pii_inventory.py"
    targets:
      - type: module
        name: pii_inventory
  - path: "src/backend/apps/users/tests/test_pii_inventory.py"
    targets:
      - type: module
        name: test_pii_inventory
changes:
  - action: add_code
    description: >
      Declare the per-model identity columns for User, SupportTicket, Ad,
      SellerVerification and ModeratorActionLog, with an erasure action per entry
      and a documented reason for every RETAIN. Add the guard test.
    code_hint: |
      class ErasureAction(StrEnum):
          CLEAR = "clear"      # overwrite with an empty/placeholder value
          NULL = "null"        # set to NULL
          DELETE_ROW = "delete_row"
          RETAIN = "retain"    # deliberate, with a stated reason - e.g. User.chat_id
acceptance_criteria:
  - "every identity column named by 06-PII-101/109/110/111/114 has an entry"
  - "every RETAIN entry carries a written reason naming the mechanism that needs it"
  - "the declaration imports with no database connection open"
  - "the guard test fails when a new identity-looking column is added to a listed model and no entry is added"
  - "no production behaviour changed in this block"
tests_to_run:
  - "src/backend/apps/users/tests/test_pii_inventory.py"
  - "src/backend/apps/users/tests/test_deletion.py"
```

**Tests required**

1. **Registry-completeness guard** — the shipped guard, demonstrated **red** by adding a
   temporary identity column to a listed model and then reverted.
2. **`RETAIN` is explicit** — a test that asserts `User.chat_id` is present with a
   non-empty reason, so the retention is a declared decision rather than an omission.
3. **No behaviour change** — `apps/users/tests/test_deletion.py` passes **unchanged** in
   this block. If it does not, the block has done BLOCK 9's work early and must be split.

**Risk and rollback**

- *Risk (the real one):* this is the one block in the plan that could be an
  **over-engineering** failure. Project rule 5 says prefer the simple, obvious solution.
  Mitigation: the block is **gated on Q-D9** and option C (list + guard test, no new
  abstraction) is on the table with a written case. The Validator must be able to reject
  an unjustified registry.
- *Risk:* the registry creates a `users` → `core` / `ads` / `trust` / `moderation` import
  direction that the module boundaries do not currently have. Mitigation: prefer a
  **declarative** form (lazy model references, or per-app declaration modules imported by
  a neutral aggregator) and keep the erasure code's imports unchanged.
- *Rollback:* a straight revert. The declaration has no consumer yet, so reverting
  changes nothing observable.
- *Cross-phase:* BLOCK 9 and BLOCK 13 re-read this block's output. If BLOCK 3 chose option
  C, both must consume the guard rather than the registry.

---

### BLOCK 4 — Fix the mask before relying on it: keyed `LOG_MASK_KEY` (06-PII-112, VAL-008)

| | |
|---|---|
| **Findings owned** | `06-PII-112`, `VAL-008` |
| **Depends on** | **nothing** |
| **Blocks** | BLOCK 5 (hard — masking into a reversible digest buys nothing), BLOCK 12 (the containment guard and the masked display helpers reuse the new construction) |
| **Priority** | **P0/P1** — becomes P0 the moment `IMMEDIATE_ALERTS_ENABLED` is considered |
| **Risk level** | **HIGH** — it adds a **secret** to a **phase-02-guarded** surface, touches the repo's most contended settings file, and changes every derived masked value in every existing log line and changelist |
| **Required agents** | **Auditor · Researcher · Planner · Validator** (all four) |

**Why this is separate from BLOCK 5.** The report is explicit: *"Do not mask into a
reversible digest. Ship the keyed construction first (or in the same commit); then the two
call sites."* Splitting them into two ordered commits is strictly better for review and
revert: a revert of the two log lines must not also un-provision a secret, and a revert of
a secret-adding change must not silently un-mask a log. The **hard edge 4 → 5** preserves
the ordering the report demands.

**Decision required before implementation — Q-D8 (secret provenance and rotation)**

| Question the owner must answer | Options and consequences |
|---|---|
| Where does `LOG_MASK_KEY` come from? | (i) **Derived** from `SECRET_KEY` (e.g. an HMAC subkey label) — no new secret to provision, no new allowlist entry, but rotating `SECRET_KEY` invalidates all mask correlation at once. (ii) **Independent** secret — a clean rotation boundary, but a new value every environment must be given, a new `ALLOWED_ENV_VARS` entry, four new `.env.*.example` lines, and a new `prod.py` guard. The phase-02 precedent is (ii) — `BOT_USERNAME` is an independent var with its own guard and a `secret_validation.py` helper |
| Required in production, or defaulted? | (i) **Fail-fast in `prod.py`** — matches the existing pattern (`_validate_production_secret` plus the `_SKIP_SECRET_VALIDATION` block, now **eight** guards after phase 02, and `secret_validation.py`'s `validate_bot_username`). (ii) **Defaulted** — simpler, but **the default is public**, and a published key makes the mask reversible again, i.e. the fix ships a false security property. Option (ii) is only acceptable if the default is a per-process random value, which forfeits cross-process correlation |
| Rotation policy | Rotation invalidates correlation across old log lines. The spec edit must say so. The choice between "rotate rarely, document the cost" and "rotate on a schedule and accept broken correlation" is an owner decision; **this plan does not choose** |

**What the fix is, and what it is not.** The mask is currently exactly
`sha256(str(tid))[:8]` — a 32-bit truncated, unsalted digest over a ~2^34 input domain.
Any deterministic function of that domain is invertible by exhaustive enumeration
**regardless of output width**, so **lengthening the hex prefix does not fix this**. A
keyed HMAC defeats the enumeration because without the key an attacker can enumerate
guesses but cannot verify any of them. The validated recommendation is
`hmac.new(settings.LOG_MASK_KEY, str(tid).encode(), sha256).hexdigest()[:12]`, keeping the
`tg_` prefix so existing log greps and the `test_admin_pii_containment.py` delegation
assertion keep working.

**Explicitly NOT built (the report's declined advisory):** a global `logging.Filter` that
"refuses any record argument named `chat_id`/`telegram_id`". It is a naming-convention
guard, not a type system — it cannot see `user.chat_id` passed positionally — and it adds
a global logging behaviour change to close two call sites. Negative ROI at this project
scale. If the invariant is ever wanted, the durable form is a typed `Identity` value
object, not a filter.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/core/utils/sanitize.py` | `mask_telegram_id` | Construction + **docstring** (`VAL-008`: it currently asserts "Non-reversible", which is false) |
| `src/backend/config/settings/base.py` | `ALLOWED_ENV_VARS`, and the new `LOG_MASK_KEY` setting beside `SECRET_KEY` | **Most contended settings file in the repo** (phases 02 and 04). Append; never reorder another phase's annotated setting |
| `src/backend/config/settings/prod.py` | a `LOG_MASK_KEY` guard, following the phase-02 pattern | Use `secret_validation.py`; do **not** invent a new mechanism |
| `src/backend/config/settings/secret_validation.py` | a `validate_log_mask_key` helper | Phase-02 module. **Re-read it immediately before editing** — it may have changed |
| `.env.example`, `.env.dev.example`, `.env.prod.example`, `.env.test.example` | a `LOG_MASK_KEY=` line in **each** | Both directions of `config/settings/tests/test_env_allowlist.py` fail without them. `.env.example` carried a UTF-8 BOM that phase 02 removes — **do not re-add it** |
| `docs/01-spec/technical-specification.md` | §F's log-masking line | **Phase 06 holds the reservation** on this file. Replace "non-reversible" with the actual construction and document the rotation trade-off (`VAL-008`) |
| `src/backend/apps/core/tests/test_sanitize.py` | `TestMaskTelegramId::test_mask_telegram_id_masks_int` | **Ships green today and will fail** — the assertion is `len(result) == 11` (C-4). Rewrite to assert the **property**, not the width |

**Binding constraints**

1. The spec line and the docstring move **in the same commit** as the construction
   (`VAL-008`). A commit that changes the mask without them leaves a false security claim
   in the codebase; a commit that changes neither makes the false claim the finding.
2. **Do not chase the "13".** The test's docstring says 13, its assertion says 11. The
   rewrite asserts properties: the `tg_` prefix, the raw ID absent, the same input giving
   the same output, a *different* input giving a different output, and the raw value not
   recoverable by a small candidate sweep **without** the key.
3. The `test_admin_pii_containment.py` delegation assertion (that the helper calls
   `mask_telegram_id`) **survives unchanged**. Assert on the delegation, never on the shape.
4. `LOG_MASK_KEY` must be **fail-fast in `prod.py`**, not defaulted to a public value.
5. Any env var added must land **with** its `ALLOWED_ENV_VARS` entry and its four template
   updates **in one commit**, and must satisfy phase 02's reverse-direction
   consumed↔allowlist test when that lands.

**Implementor task**

```yaml
id: task_06_b04_keyed_mask
title: "Replace the reversible Telegram-ID mask with a keyed HMAC (06-PII-112)"
priority: high
depends_on: []
source_reference: ".ai/plans/06-pii-consent-remediation.md"
source_section: "BLOCK 4 - Fix the mask before relying on it"
source_blocks: ["BLOCK 4"]
description: >
  mask_telegram_id returns the first 8 hex chars of an unsalted SHA-256 over a
  ~2^34 input domain, so it is reversible by exhaustive enumeration in seconds; the
  function docstring and the technical specification both assert the opposite.
  Replace it with a keyed HMAC-SHA256 truncation behind a new LOG_MASK_KEY, and correct
  the docstring and the spec line in the same commit.
goals:
  - "make the mask non-verifiable without the server key"
  - "provision LOG_MASK_KEY across settings, the env allowlist and all four templates"
  - "correct both places that document the mask as non-reversible"
files:
  - path: "src/backend/apps/core/utils/sanitize.py"
    targets:
      - type: function
        name: mask_telegram_id
  - path: "src/backend/config/settings/base.py"
    targets:
      - type: constant
        name: ALLOWED_ENV_VARS
  - path: "src/backend/config/settings/secret_validation.py"
    targets:
      - type: function
        name: validate_log_mask_key
  - path: "src/backend/config/settings/prod.py"
    targets:
      - type: module
        name: prod
  - path: "src/backend/apps/core/tests/test_sanitize.py"
    targets:
      - type: class
        name: TestMaskTelegramId
  - path: "docs/01-spec/technical-specification.md"
    targets:
      - type: document_section
        name: "log masking rule"
    semantic_anchors:
      replace_text_containing:
        type: literal
        value: "non-reversible"
changes:
  - action: add_code
    description: >
      Add the LOG_MASK_KEY setting, its ALLOWED_ENV_VARS entry, the four template
      lines, the prod fail-fast guard following the phase-02 secret_validation.py
      pattern, and the HMAC-based mask with a corrected docstring.
    code_hint: |
      hmac.new(
          settings.LOG_MASK_KEY.encode(),
          str(telegram_id).encode(),
          hashlib.sha256,
      ).hexdigest()[:12]
acceptance_criteria:
  - "the mask is not reproducible without LOG_MASK_KEY, even for a small candidate sweep"
  - "the tg_ prefix is preserved and the same input still gives the same output"
  - "the docstring and the technical-specification line describe the actual construction"
  - "test_env_allowlist.py passes in both directions"
  - "test_admin_pii_containment.py passes unchanged"
tests_to_run:
  - "src/backend/apps/core/tests/test_sanitize.py"
  - "src/backend/apps/users/tests/test_admin_pii_containment.py"
  - "src/backend/config/settings/tests/"
```

**Tests required** (logic and interaction, not implementation trivia)

1. **Property, not width.** The rewritten `test_mask_telegram_id_masks_int` asserts
   prefix, stability, injectivity on two inputs, and raw-value absence. **It must not
   assert a length.**
2. **The security property, as a test.** Given a mask and a candidate list, an attacker
   without the key cannot confirm a match; with the key they can. Written as a *behaviour*
   assertion on the helper, not as a commentary about cryptography.
3. **The secret-guard test.** A production settings module with a placeholder or missing
   `LOG_MASK_KEY` raises. This is the phase-02 pattern; the test must be in the same
   commit as the guard.
4. **Regression.** `test_admin_pii_containment.py` green unchanged; `test_login.py`'s
   "raw value absent" assertions green (they do not pin a shape).

**Risk and rollback**

- *Rollout:* **every** derived masked value in every historical log line, changelist and
  stored value changes. Old and new lines are no longer correlatable. This is the
  documented rotation trade-off, and it is why the spec edit is mandatory.
- *Regression risk:* the exact-width pin fails by design; it is rewritten here, not
  elsewhere. `test_admin_pii_containment.py` must **not** be touched to accommodate it.
- *Process risk (high):* `base.py`, `prod.py` and four env templates are phase-02's
  surface and the repo's most contended files. Re-read each immediately before editing;
  stage explicitly; never `git add .`; never revert a concurrent change (§1.3, §5.3).
- *Rollback:* a straight revert restores the old construction. **But** any environment
  that has already been provisioned with `LOG_MASK_KEY` keeps an unused secret — harmless
  and documented, not a reason to avoid the rollback.
- *Cross-phase:* BLOCK 5 and BLOCK 12 both depend on this. Phase 04's tests must not
  assert on a mask's length or shape (§5.5).

---

### BLOCK 5 — Mask the two alert failure log sites (06-PII-102)

| | |
|---|---|
| **Findings owned** | `06-PII-102` |
| **Depends on** | **BLOCK 4** (hard) |
| **Blocks** | the `IMMEDIATE_ALERTS_ENABLED` rollout gate (with BLOCK 7) |
| **Priority** | P1 — **P0 if `IMMEDIATE_ALERTS_ENABLED` is ever enabled** |
| **Risk level** | **MEDIUM** — the diff is two lines, but the *wrong* two lines silently break delivery |
| **Required agents** | **Auditor · Planner · Validator**. **Researcher not required.** **Validator required** — the delivery-preservation claim must be independently confirmed against a captured send argument |

**The hard constraint the report understates (C-10).**
`apps/search/tests/test_immediate_alerts.py` asserts on the **send** argument, not the log
argument — for example `TestGatherIsolation::test_permanent_failure_does_not_cancel_siblings`
collects `kwargs["chat_id"]` from a fake `send_message` and asserts
`sorted(attempted) == [1, 2, 3]`. **A "fix" that masks inside `_build_payload` — i.e.
replaces the payload's `chat_id` with a mask — breaks that test *and* breaks delivery.**
The payload dictionary must keep the **real** `chat_id`; only the value handed to the log
formatter is masked.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/search/services/immediate_alerts.py` | `_send_payloads` — the two `logger.warning` calls (the `TelegramBadRequest` / `TelegramForbiddenError` branch and the post-retry `AiogramError` branch) | The only production file. `_build_payload` is a **read-only reference**: read it, do not change it |
| `src/backend/apps/search/tests/test_immediate_alerts.py` | add assertions to the existing failure-branch tests | **Existing module.** Do **not** weaken the `kwargs["chat_id"]` assertions — they are the delivery tripwire |

**Binding constraints**

1. **The payload keeps the real `chat_id`.** Only the formatter argument changes.
2. Use lazy `%s` formatting with `mask_telegram_id(...)` passed as the argument — do not
   f-string the mask into the format string.
3. **Do not add the declined logging `Filter`** (§BLOCK 4, declined advisory).
4. Do not change the retry, backoff, dead-letter or sibling-isolation behaviour. Phase 03
   BLOCK 9 owns delivery-state serialisation in these same two files and must re-read
   after this block (§5.3).

**Implementor task**

```yaml
id: task_06_b05_alert_log_masking
title: "Mask the raw chat_id in the immediate-alert failure logs (06-PII-102)"
priority: medium
depends_on: [task_06_b04_keyed_mask]
source_reference: ".ai/plans/06-pii-consent-remediation.md"
source_section: "BLOCK 5 - Mask the two alert failure log sites"
source_blocks: ["BLOCK 5"]
description: >
  _build_payload copies user.chat_id verbatim into the payload and both failure
  branches in _send_payloads interpolate payload["chat_id"] into a logger.warning
  with no masking, violating the log-masking rule in the technical specification.
  Mask the two log arguments only. The payload must keep the real chat_id.
goals:
  - "stop writing a raw Telegram identifier to WARNING logs on send failure"
  - "preserve delivery exactly - a captured send still receives the real integer"
files:
  - path: "src/backend/apps/search/services/immediate_alerts.py"
    targets:
      - type: function
        name: _send_payloads
  - path: "src/backend/apps/search/tests/test_immediate_alerts.py"
    targets:
      - type: class
        name: TestGatherIsolation
changes:
  - action: modify_code
    description: >
      Pass mask_telegram_id(payload["chat_id"]) as the log argument at both failure
      branches. Do not touch _build_payload. Add an assertion per branch that the
      emitted record does not contain the raw chat_id, alongside the existing
      assertion that the send received the real one.
    code_hint: |
      logger.warning(
          "Immediate alert delivery permanently failed for chat %s: %s",
          mask_telegram_id(payload["chat_id"]),
          exc,
      )
acceptance_criteria:
  - "neither failure branch's formatted message contains the raw chat_id"
  - "a captured send_message call still receives the real integer chat_id"
  - "no change to retry, backoff, dead-letter or sibling-isolation behaviour"
  - "_build_payload is unchanged"
tests_to_run:
  - "src/backend/apps/search/tests/test_immediate_alerts.py"
  - "src/backend/apps/search/tests/test_alert_query.py"
```

**Tests required**

1. **Per branch** — the `TelegramBadRequest` / `TelegramForbiddenError` branch and the
   post-retry `AiogramError` branch each assert that the captured log record's formatted
   message does not contain the raw `chat_id`, **and** that the payload handed to the
   sender still contains the real one. One test, both assertions, per branch: the second
   assertion is the whole point of the block.
2. **Regression** — the module's existing `kwargs["chat_id"]` assertions, retry-after and
   capped-backoff tests, session-close tests and sibling-isolation tests all pass
   **unchanged**.

**Risk and rollback**

- *The one real risk:* masking in the payload. Mitigation: binding constraint 1 plus test
  assertion 1's second half; the pre-existing tests would also catch it.
- *Rollout:* any log parser keyed on the raw `chat_id` breaks. Documented, accepted.
- *Rollback:* a straight revert. No data, no schema.
- *Note:* this block closes a real spec violation but **does not** lift the
  `IMMEDIATE_ALERTS_ENABLED` gate on its own — BLOCK 7 must land too.

---

### BLOCK 6 — One queryset-level account-state predicate (06-PII-104a, VAL-003)

| | |
|---|---|
| **Findings owned** | `06-PII-104` (declaration half), `VAL-003` |
| **Depends on** | **the Q-D6 ownership decision** (Researcher + Planner, confirmed with the coordinator) |
| **Blocks** | BLOCK 7 |
| **Priority** | **P0** — the live daily path is unguarded today |
| **Risk level** | **MEDIUM** — one declaration, no call-site change, but a wrong definition propagates to four sites and to a second phase |
| **Required agents** | **Auditor · Researcher · Planner · Validator** (all four — the shape and the owner are both open, and the declaration becomes a cross-phase contract) |

**Decision required before implementation — Q-D6 (ownership and shape)**

**Ownership.** Per the report, phase 15 owns "the framework that enforces the predicate
consistently across both processes" while phase 06 owns "the semantics". The ownership
question is genuinely open, not a formality. **This block must record the decision and
have it confirmed with the coordinator** so phase 15 does not fork it (§5.6).

**Shape options:**

| Option | What it is | Maintainability | Future evolution | Convention fit |
|---|---|---|---|---|
| **A** | A `UserQuerySet` method (e.g. `eligible_for_outbound()`) on a custom manager added to `User` | High — call sites read as a named intent, and it composes into existing chains | A fifth flag is a one-line change in one place | Good; a `QuerySet` subclass is idiomatic Django and does **not** change default behaviour |
| **B** | A module-level helper in `apps/users/services/account_state.py` returning a `Q` object (e.g. `account_state_q()`), consumed as `SavedSearch.objects.filter(account_state_q(), is_active=True)` | Medium — no model change, no manager, and the predicate sits next to the instance-level `get_account_state()` it mirrors | Same one-line property; but the name must be a real API, not a private helper | Good; no new model surface |
| **C** | **Forbidden** — a default-manager filter | — | — | It would silently change **every** `User.objects` query in the codebase, including the bot's `AccountStateMiddleware._resolve_user` (`User.objects.get(chat_id=chat_id)`) whose `_check_user_state(chat_id)` signature is documented **load-bearing** and pinned by bot tests. This is a hard prohibition, not a preference |

**Also forbidden:** implementing PII-104 by **nulling `chat_id`**. `AccountStateMiddleware`
resolves users by `chat_id` precisely so a withdrawn identity stays *blocked*; nulling it
re-opens a different hole and breaks `test_backfill_uses_stable_chat_id`.

**What the predicate must express.** The instance-level `get_account_state(user)` already
knows the rule; the queryset form must be the **same** rule, not a second copy. The
flags the report found unguarded at the alert sites are `is_deleted`, `is_declined`,
`is_banned` and `consent_revoked_at`. Whether `is_banned` belongs in a *consent* predicate
is itself a judgement call — the validator weakened the banned half of `PII-104` ("a ban is
a moderation action, not a consent action") while keeping the filter. **The Researcher
must state the intended membership of the predicate and its rationale, and BLOCK 7
consumes it unchanged.**

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/users/models.py` | `User` — a `QuerySet` subclass + manager (**only if** option A) | A declared manager, **not** a default filter. `User` currently declares no custom manager |
| `src/backend/apps/users/services/account_state.py` | the predicate declaration (**option B**), alongside `get_account_state`, `can_publish_ad`, `can_login` | This module already owns the instance-level rule; a queryset-level sibling is the smallest coherent change |
| `src/backend/apps/users/services/__init__.py` | the re-export surface | Only if re-exported |
| `src/backend/apps/users/tests/test_account_state.py` | new queryset-level tests | Existing module; the instance-level matrix must stay green **unchanged** |

**Binding constraints**

1. **No default-manager filter.** Ever. If a design appears to need one, that is evidence
   the declaration is in the wrong place.
2. The predicate must be **testable without a request and without a `User` instance**.
3. It must live in `apps/users` and be importable by `apps/search` **without** creating a
   circular import. `apps/search` already imports from `apps.users`; the reverse must not
   be introduced.
4. `get_account_state(user)` and the queryset predicate must be **provably the same rule**.
   A test that constructs a user in every state and asserts the queryset agrees with
   `get_account_state` is the only thing that prevents the drift this finding exists to
   stop.
5. **This block does not change any call site.** BLOCK 7 does that. If
   `alert_query.py` or `immediate_alerts.py` is edited here, the block has run ahead.

**Implementor task**

```yaml
id: task_06_b06_account_state_predicate
title: "Declare the queryset-level account-state predicate (06-PII-104a / VAL-003)"
priority: high
depends_on: []
source_reference: ".ai/plans/06-pii-consent-remediation.md"
source_section: "BLOCK 6 - One queryset-level account-state predicate"
source_blocks: ["BLOCK 6"]
description: >
  apps/search needs a queryset-level consent predicate; the only rule that exists is
  the instance-level get_account_state(user), which cannot be used from a filter.
  Declare one queryset-level predicate owned by apps/users, per the recorded Q-D6
  decision, without a default-manager filter and without changing any call site.
goals:
  - "give the alert paths one reusable eligibility declaration"
  - "guarantee the queryset predicate and get_account_state are the same rule"
files:
  - path: "src/backend/apps/users/services/account_state.py"
    targets:
      - type: module
        name: account_state
    semantic_anchors:
      insert_after:
        type: function
        name: get_account_state
  - path: "src/backend/apps/users/tests/test_account_state.py"
    targets:
      - type: module
        name: test_account_state
changes:
  - action: add_code
    description: >
      Add the queryset-level predicate per the Q-D6 decision (a named QuerySet method
      or a Q-returning helper). Add a cross-check test asserting the queryset result
      agrees with get_account_state for every account state.
    code_hint: |
      def account_state_q() -> Q:
          """Q predicate mirroring get_account_state() - the single consent rule."""
acceptance_criteria:
  - "the predicate is a named declaration, not a copy at a call site"
  - "no default manager filter was introduced on User"
  - "for every account state the queryset agrees with get_account_state"
  - "no alert call site was changed in this block"
tests_to_run:
  - "src/backend/apps/users/tests/test_account_state.py"
  - "src/backend/apps/search/tests/test_alert_query.py"
```

**Tests required**

1. **Cross-check test** — for each state (active, declined, withdrawn, banned, deleted,
   combinations), the queryset filter and `get_account_state(user)` agree. This is the
   anti-drift tripwire and the most valuable test in the block.
2. **Composition** — the predicate composes into an existing chain without changing that
   chain's meaning (`SavedSearch.objects.filter(is_active=True).select_related(...)`).
3. **No request, no instance** — the predicate is exercised with no `HttpRequest` and no
   `User` in scope.
4. **Regression** — `test_account_state.py`'s existing `can_login` / `can_publish_ad` /
   `get_state_badge` matrices pass **unchanged**, including
   `test_declined_user_can_publish` (which BLOCK 8 option (a) must preserve).

**Risk and rollback**

- *Risk:* a default filter sneaks in as "simplification". Mitigation: binding constraint 1
  and an acceptance criterion; the bot's middleware is the named casualty.
- *Risk:* the predicate's membership drifts from `get_account_state`. Mitigation: test 1.
- *Rollback:* a straight revert; no call site consumes it yet.
- *Cross-phase:* the **single most contested declaration in the plan**. Phase 15's
  `AUTHZ-005` shares this predicate's semantics. §5.6 states the handoff.

---

### BLOCK 7 — Gate both alert paths on consent state (06-PII-104b)

| | |
|---|---|
| **Findings owned** | `06-PII-104` (call-site half) |
| **Depends on** | **BLOCK 6** (hard) |
| **Blocks** | the `IMMEDIATE_ALERTS_ENABLED` rollout gate (with BLOCK 5) |
| **Priority** | **P0** — live on the **daily, ungated** path today |
| **Risk level** | **HIGH** — four call sites, two of them in files another phase is also editing, and a wrong filter silently stops legitimate digests |
| **Required agents** | **Auditor · Researcher · Planner · Validator** (all four) |

**Why HIGH and not "four filter edits".** This is the only finding in the phase that is
**live in the shipped configuration**: `send_alerts` runs daily at 08:00 UTC and is not
feature-gated, and `_format_digest` renders a declined seller's ad **title and price** to
every matching subscriber. The immediate path is off by default but is *worse* when on,
because `build_alert_message` renders `ad.get_absolute_url()` — a **working deep link** to
an ad the site refuses to show. Wrongly narrowing the filter is a service regression; failing
to narrow it is the finding.

**The four recipient-selection sites (C-9) — all must consume BLOCK 6's declaration**

| Site | Current filter | Symbol |
|---|---|---|
| 1 | `SavedSearch.objects.filter(is_active=True)` | `send_alerts.Command._collect_alerts` |
| 2 | `SavedSearch.objects.filter(is_active=True).select_related(...)` | `send_alerts.Command._dry_run_check` |
| 3 | `Ad.objects.filter(status=AdStatus.PUBLISHED)` | `alert_query.find_matching_ads` (two call sites) |
| 4 | `SavedSearch.objects.filter(is_active=True).select_related(...)` | `alert_query.find_matching_saved_searches` |

Plus two soft gates that are **not** consent gates and must not be mistaken for them:
`if not user.chat_id` in `send_alerts._send_user_digests` and in `immediate_alerts._build_payload`.
They are retained; the consent predicate is added alongside.

**Second half: hidden content must not fan out even to an eligible subscriber.** Exclude
ads whose owner is DECLINED from `find_matching_ads` and `find_matching_saved_searches`.
This is the `06-PII-109` overlap the report flagged, and it is cheap here because the
visibility rule already exists downstream (`ListingsQuery` applies a live
`user__is_declined=False` filter). **Do not** reuse `ListingsQuery` itself — the alert path
has different ranking and cap semantics — but the predicate must be the same rule.

**File surface (semantic units)**

| File | Symbol / target | Contention |
|---|---|---|
| `src/backend/apps/search/management/commands/send_alerts.py` | `Command._collect_alerts`, `Command._dry_run_check` | Phase 01 shipped the daily idempotency/durable marker here. **Re-read before editing; do not regress it** |
| `src/backend/apps/search/services/alert_query.py` | `find_matching_ads`, `find_matching_saved_searches` | **Phase 03 BLOCK 9 boundary file.** Phase 03 owns the *delivery-state* contract (what has already been sent); phase 06 owns *who is eligible*. If this block edits it, phase 03 BLOCK 9 must re-read |
| `src/backend/apps/search/services/immediate_alerts.py` | `deliver_immediate_alerts` (the call into `find_matching_saved_searches`) | Also phase 03's. BLOCK 5 just edited this file — **re-read** |
| `src/backend/apps/search/tests/test_alert_query.py`, `test_send_alerts.py`, `test_send_alerts_daily.py`, `test_immediate_alerts.py` | new per-state tests | Existing modules |

**Binding constraints**

1. All four sites consume **one** declaration from BLOCK 6. No site re-states the rule.
2. **Do not add a default-manager filter** and **do not null `chat_id`**.
3. The immediate path's behaviour with `IMMEDIATE_ALERTS_ENABLED=False` must remain
   *nothing happens* — the gate is not weakened.
4. `send_alerts` collects under `AdvisoryLockId.ALERT_DELIVERY_TASK` for collection only;
   the network send happens outside both the lock and the transaction. **This block must
   not move the collection across the lock or transaction boundary.**
5. Phase 03 BLOCK 9's delivery-state de-duplication is not this block's to change.
6. `test_alert_query.py::TestFindMatchingSavedSearches` and `::TestSendAlertsCommand`
   pin today's selection semantics. They must be **updated deliberately** (project rule 2)
   where the new eligibility rule is the correct behaviour — and the update must be
   named in the commit body.

**Implementor task**

```yaml
id: task_06_b07_alert_audience_gate
title: "Gate both alert paths on the account-state predicate (06-PII-104b)"
priority: high
depends_on: [task_06_b06_account_state_predicate]
source_reference: ".ai/plans/06-pii-consent-remediation.md"
source_section: "BLOCK 7 - Gate both alert paths on consent state"
source_blocks: ["BLOCK 7"]
description: >
  Both alert paths select their audience by SavedSearch.is_active alone, so a user
  who withdrew consent keeps receiving daily digests for the full 30-day window and
  a declined seller's hidden ad fans out with its title and price to every matching
  subscriber. Apply the BLOCK 6 predicate at all four recipient-selection sites and
  exclude declined-owner ads from the matching queries.
goals:
  - "stop outbound alerts to withdrawn, declined and banned accounts"
  - "stop content that is hidden on the site from fanning out to any subscriber"
  - "keep all four sites driven by one declaration"
files:
  - path: "src/backend/apps/search/management/commands/send_alerts.py"
    targets:
      - type: class
        name: Command
      - type: method
        name: _collect_alerts
      - type: method
        name: _dry_run_check
  - path: "src/backend/apps/search/services/alert_query.py"
    targets:
      - type: function
        name: find_matching_ads
      - type: function
        name: find_matching_saved_searches
  - path: "src/backend/apps/search/tests/test_alert_query.py"
    targets:
      - type: module
        name: test_alert_query
changes:
  - action: modify_code
    description: >
      Compose the BLOCK 6 predicate into each of the four selection sites and add the
      declined-owner exclusion to the ad matchers. Add one test per state per path.
    code_hint: |
      SavedSearch.objects.filter(is_active=True).filter(account_state_q())
acceptance_criteria:
  - "a SavedSearch owned by a withdrawn, declined or banned user appears in none of the four sites"
  - "an ad owned by a declined seller matches no saved search on either path"
  - "an eligible user's digest still delivers, and the daily dry-run count is unchanged for eligible users"
  - "all four sites reference the BLOCK 6 declaration and no site restates the rule"
  - "IMMEDIATE_ALERTS_ENABLED=False still results in no immediate delivery"
tests_to_run:
  - "src/backend/apps/search/tests/test_alert_query.py"
  - "src/backend/apps/search/tests/test_send_alerts.py"
  - "src/backend/apps/search/tests/test_send_alerts_daily.py"
  - "src/backend/apps/search/tests/test_immediate_alerts.py"
```

**Tests required** (one per state, per path — the report's rollout table asks for this and
it is the block's whole value)

1. **`send_alerts._collect_alerts`** — a saved search owned by each of withdrawn /
   declined / banned / deleted / eligible produces the expected membership.
2. **`send_alerts._dry_run_check`** — the reported counts reflect the same rule, so an
   operator's dry-run does not promise messages that will not be sent.
3. **`find_matching_saved_searches`** — a declined seller's ad matches no eligible search.
4. **`find_matching_ads`** — the same, from the ad side.
5. **Delivery is preserved** — an eligible user still receives the digest, with the
   existing title/price formatting unchanged.
6. **Gate** — `IMMEDIATE_ALERTS_ENABLED=False` still delivers nothing on publish.

**Risk and rollback**

- *Risk (data-adjacent):* an over-narrow filter silently stops legitimate digests for
  eligible users. Mitigation: test 5 asserts the positive case explicitly, not just the
  exclusions.
- *Risk (contention):* `alert_query.py` and `immediate_alerts.py` are phase 03 BLOCK 9's
  files. Mitigation: §5.3; the block's commit body must state that recipient **selection**
  changed and delivery **state** did not.
- *Performance:* a new join on `SavedSearch.user` changes the plan for
  `IX_saved_searches_user_active`; phase 13 owns performance and must be told (§5.6).
- *Rollback:* a straight revert. No schema, no data. Rollback restores a known consent
  leak, which is acceptable only as an incident response.

---

### BLOCK 8 — DECLINE recovery: session-independent path, discoverable affordance, non-silent Accept (06-PII-105 implementation)

| | |
|---|---|
| **Findings owned** | `06-PII-105` (implementation half) |
| **Depends on** | **BLOCK 1** (the decision), **BLOCK 2** (the docs) |
| **Blocks** | nothing in this plan; it is phase 04's BLOCK 6 evidence |
| **Priority** | P1 — depends on the owner's decision, not on engineering |
| **Risk level** | **HIGH under option (a)** (it changes the auth predicate) / **MEDIUM under option (b)**. Treated as **HIGH either way** because the mechanism and the copy both change |
| **Required agents** | **Auditor · Researcher · Planner · Validator** (all four) |

**The defect, in the tree's own words.** `consent_accept` computes
`user = request.user if request.user.is_authenticated else None` and calls `give_consent()`
only under `if user is not None`. For an anonymous POST it still runs
`_set_consent_cookies(..., ConsentChoice.ACCEPTED, ...)` and still calls
`record_consent_action(user=None, ...)`. A logged-out declined seller who follows
`privacy.html` §7's link therefore receives **HTTP 302, no error, a
`consent_given=accepted` cookie that makes the banner disappear, and no DB mutation** —
and their ads stay hidden indefinitely. `consent_state` compounds it by setting
`consent_shown = True` whenever `user.is_declined`, so the only re-entry is the
`?ref=preferences` override. `can_login()` returns `False` for `is_declined` with no
service-layer reversal path, and `consent_decline` does not flush the session.

**Required under either option from BLOCK 1** — these are the block's contract:

1. A **first-class, session-independent** recovery path that does not depend on a live
   session (e.g. a `POST /consent/resume/` reachable from the bot and from the public page
   that re-authenticates *only* enough to flip `is_declined`, with an explicit
   `ConsentRecord`).
2. A **discoverable** affordance: either stop hiding the banner from a declined user, or
   add a persistent, session-independent "review your consent choices" surface on the
   dashboard that does not require `?ref=preferences`.
3. A **non-silent** anonymous Accept: either mutate the row, or return an explanatory
   page. Silently setting an `accepted` cookie while changing nothing is the bug.
4. `privacy.html` §7 corrected to match BLOCK 1's answer.

**Decision required before implementation — mechanism shape (Researcher + Planner)**

How is the "enough identity" for a session-independent resume established, given that
`withdraw_consent` nulls `telegram_id` and keeps `chat_id` deliberately (§0.3)?
Candidate shapes, all of which have trust consequences the Researcher must weigh and the
Planner must not pre-decide: (i) the resume link is itself the proof (a signed,
single-use token issued at decline time and stored on the withdrawal record);
(ii) the user re-authenticates through the existing bot `LoginToken` handshake; (iii) the
user re-authenticates with a credential the product does not currently collect — which
would be a **new capability**, and therefore a product decision. **Note the constraint:**
option (iii) opens a new data category, which is exactly the class of decision
`06-PII-111` was filed about.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/users/views/consent.py` | `consent_accept`, `consent_decline`, and a new `consent_resume` view | Phase 01 already slimmed this module to the three consent views + the login half; keep it slim |
| `src/backend/apps/users/urls.py` | the consent route names (`consent:accept`, `consent:decline`, `consent:withdraw`); a new route lands here | |
| `src/backend/apps/users/context_processors.py` | `consent_state` — the `consent_shown` derivation and the `?ref=preferences` override | Also the home of `CONSENT_REPROMPT_DAYS` (BLOCK 15 reads it, this block must not move it) |
| `src/backend/apps/users/services/account_state.py` | `can_login` — **only if BLOCK 1 chose option (a)** | Phase 04's `04-AUT-002` also touches this predicate |
| `src/backend/apps/users/services/deletion.py` | `decline_consent` / `give_consent` — only the minimal state change the chosen mechanism needs | **`deletion.py` is `withdraw_consent`'s home and is BLOCK 9's next edit.** The edge exists so the two do not collide |
| `src/backend/templates/components/consent_banner.html` | the banner render condition and its copy | |
| `src/backend/templates/privacy.html` | §7 copy | **Not §6** — §6 is BLOCK 9's |
| `src/backend/locale/{ru,bs,en}/LC_MESSAGES/django.po` | the new/changed strings | **Append; never regenerate wholesale** (phase 14 owns the runtime i18n tree) |

**Binding constraints**

1. **Do not change `can_login()` unless BLOCK 1 chose option (a).** The record must
   exist and be cited.
2. **Two shipped tests will break and are corrected, not worked around** (project rule 2):
   `test_account_state.py::TestCanLogin::test_declined_user_cannot_login` and
   `::test_banned_and_declined_cannot_login` (option (a) only), and
   `test_consent_context.py::TestAuthenticatedState::test_declined_user_hides_banner`
   (any "stop hiding the banner" variant).
   `test_deleted_user_hides_banner` pins the **separate** `is_deleted` branch and must keep
   passing. `test_declined_user_can_publish` must keep passing under option (a).
3. **i18n is part of DoD** (`VAL-006`). `ru` and `bs` `msgstr` must both be non-empty in
   the **same commit**. An i18n-gate failure here is a **consequence of the fix**, not a
   regression.
4. `no SESSION_COOKIE_AGE` exists anywhere in `src/backend/` — Django's 14-day **absolute**
   default applies. That is `04-AUT-006` / phase 04 BLOCK 8's territory. **This block must
   not set it**; the recovery path must be session-independent precisely *because* it is
   not in this phase's control.
5. Do not add a per-request account-state middleware — phase 15's `15-AUTHZ-001` owns it.
6. `deletion.py` edits in this block must be **minimal** and must not restructure
   `withdraw_consent`; BLOCK 9 rewrites its erasure scope.

**Implementor task**

```yaml
id: task_06_b08_decline_recovery
title: "Make DECLINE recovery session-independent and discoverable (06-PII-105)"
priority: high
depends_on: [task_06_b01_decline_decision, task_06_b02_decline_docs]
source_reference: ".ai/plans/06-pii-consent-remediation.md"
source_section: "BLOCK 8 - DECLINE recovery"
source_blocks: ["BLOCK 8"]
description: >
  A logged-out declined seller who follows the privacy policy's own link gets HTTP
  302, no error, an "accepted" cookie and no state change. Implement the BLOCK 1
  decision: a session-independent recovery path, a discoverable affordance, and a
  non-silent anonymous Accept, with ru/bs translations in the same commit.
goals:
  - "make the recovery path work without a live session"
  - "make the affordance discoverable without ?ref=preferences"
  - "stop the anonymous Accept from being a silent no-op"
files:
  - path: "src/backend/apps/users/views/consent.py"
    targets:
      - type: function
        name: consent_accept
      - type: function
        name: consent_decline
  - path: "src/backend/apps/users/urls.py"
    targets:
      - type: module
        name: urls
  - path: "src/backend/apps/users/context_processors.py"
    targets:
      - type: function
        name: consent_state
  - path: "src/backend/templates/components/consent_banner.html"
    targets:
      - type: template
        name: consent_banner
  - path: "src/backend/locale/ru/LC_MESSAGES/django.po"
    targets:
      - type: locale
        name: ru
changes:
  - action: add_code
    description: >
      Implement the recorded BLOCK 1 decision. Add the recovery route, the explicit
      ConsentRecord write, the affordance, and the non-silent anonymous response.
      Adjust can_login only if option (a) was chosen.
    code_hint: |
      # The non-silent anonymous Accept: mutate nothing and SAY so, or mutate the
      # row. Setting a consent_given=accepted cookie while changing nothing is the bug.
acceptance_criteria:
  - "a logged-out declined user can reverse the decline and is told what happened"
  - "no path sets an accepted cookie while leaving the row unchanged without an explanation"
  - "the affordance is reachable without the ?ref=preferences override"
  - "an explicit ConsentRecord is written for every consent state transition, including the new one"
  - "ru and bs msgstr are non-empty for every new or changed string"
  - "test_deleted_user_hides_banner and test_declined_user_can_publish still pass"
tests_to_run:
  - "src/backend/apps/users/tests/test_consent.py"
  - "src/backend/apps/users/tests/test_consent_context.py"
  - "src/backend/apps/users/tests/test_consent_records.py"
  - "src/backend/apps/users/tests/test_account_state.py"
  - "src/backend/apps/ads/tests/test_i18n_completeness.py"
```

**Tests required**

1. **The silent no-op is dead** — an anonymous `POST /consent/accept/` (i) does not set an
   `accepted` cookie while leaving the row unchanged, and (ii) returns an explanatory
   response. Assert the **behaviour**, not the status code alone.
2. **Session-independent recovery** — with no session cookie, the recovery path flips
   `is_declined` back, restores `can_login` (option (a)) and writes a `ConsentRecord`.
   This is the test that proves the defect is closed and it was **red** before the fix.
3. **The affordance is discoverable** — a declined user can find the recovery surface
   without the `?ref=preferences` query parameter.
4. **Corrected tests, named in the commit body** — the two `can_login` assertions (option
   (a)) and `test_declined_user_hides_banner`.
5. **i18n** — `test_i18n_completeness.py` green; the new `ru`/`bs` strings rendered in a
   test that activates a non-English locale.

**Risk and rollback**

- *Risk (security, option (a)):* a declined user regains web login. **A security review of
  the regained surface is mandatory**, and the Validator must enumerate what a declined
  user can newly reach. This is why the block carries all four agents regardless of option.
- *Risk (security, the recovery mechanism):* a session-independent path is a
  re-authentication path. The Researcher must state the threat model for whichever shape is
  chosen, and a shape that accepts a bare `chat_id` is **not acceptable** — `chat_id` is
  public to anyone who has ever messaged the bot.
- *Risk (i18n):* the gate fails on `ru`/`bs`. Per `VAL-006` that is expected, not a
  regression.
- *Rollback:* a straight revert. If the mechanism introduced a stored token, the rollback
  must also state that the token table is left in place (a `RemoveField` is a separate,
  later decision — do not fold a destructive migration into a revert).

---

### BLOCK 9 — Withdraw-time teardown, `preferred_city`, and the §6 retention promise (06-PII-110 kept half)

| | |
|---|---|
| **Findings owned** | `06-PII-110` (kept half). The `ConsentRecord.session_key` / `.user_agent` half is **absorbed by `06-PII-116`** (BLOCK 15) |
| **Depends on** | **BLOCK 3** (the inventory, if option A) and **BLOCK 7** (the eligibility rule this teardown mirrors) |
| **Blocks** | BLOCK 10, BLOCK 13, BLOCK 14 (all edit `deletion.py` or the same retention story) |
| **Priority** | P1 |
| **Risk level** | **MEDIUM** — changes the withdrawal transaction and the published policy text |
| **Required agents** | **Auditor · Researcher · Planner · Validator** (all four — it is the first edit to the erasure transaction and the question below is open) |

**What is in scope here, and what is not.** `withdraw_consent`'s `update_fields` list is
exactly nine columns (`consent_revoked_at`, `is_deleted`, `deleted_at`, `consent_given_at`,
`telegram_id`, `username`, `first_name`, `last_name`, `email`). This block adds the
**withdrawal-time teardown of subscriber state** and the `preferred_city` clearing, and it
rewrites `privacy.html` §6. The `ConsentRecord` fingerprint retention is **not** here — it
is BLOCK 15's, so that one sweep and one TTL close both.

**`chat_id` is retained, deliberately, and the block must say so in the copy.** The tree
documents it: `User.chat_id.help_text` reads *"Stable Telegram chat ID; set on first bot
contact, never nullified"*, and `AccountStateMiddleware._resolve_user` does
`User.objects.get(chat_id=chat_id)` with a docstring stating the reason — *"so that
withdrawn/deleted users (whose telegram_id is nulled by GDPR erasure) are still found."*
**Nulling `chat_id` is forbidden.** The defect is that the retention is unreconciled
against the published promise, and that it is the mechanical reason BLOCK 7 was needed.

**The four things this block changes**

1. `SavedSearch.objects.filter(user=user).update(is_active=False)` in the withdrawal
   transaction — revocation actively tears down subscriber state rather than relying on a
   future filter.
2. Delete the user's `SearchHistory` rows in the same transaction (they are `CASCADE`-only
   today, so they survive DECLINE indefinitely and WITHDRAW for the full 30 days). This
   discharges part of `06-PII-108`'s retention question; BLOCK 14 fixes the *write* path.
3. Clear `preferred_city` on DECLINE and on withdrawal. **The asymmetry is the defect**:
   `_set_consent_cookies` already deletes the matching `preferred_city` **cookie** whenever
   preferences consent is false, while the DB column is untouched.
4. Rewrite `privacy.html` §6 to enumerate what is erased, what is retained and **why**,
   citing the bot-block requirement — instead of the current blanket *"All personal data is
   permanently erased within 30 days of withdrawal."*

**Decision required before implementation — Q-D10 (`preferred_city` vs. login reconciliation)**

`_reconcile_preferred_city_on_login` backfills the `preferred_city` **column** from the
cookie at login when the column is empty. On the decline path the cookie is deleted, so
the backfill is empty too and the nulling should hold — **but** a user who later re-accepts
preferences gets a fresh cookie and therefore a fresh column value. The Researcher must
state the intended end state: is a re-accepted preference a *new* consent (column restored
is correct), or is the column's clearing terminal? **This plan does not choose**, because
the answer is a product statement about re-consent, and `test_preferred_city.py` and
`test_preferred_city_readback.py` pin the cookie lifecycle and the explicit "clear" action
against the current behaviour.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/users/services/deletion.py` | `withdraw_consent`, `decline_consent` | **The first edit to the erasure transaction in this plan.** `Soft_delete_user_ads` is BLOCK 11's; the `ConsentRecord` write is BLOCK 10's; the ticket scrub is BLOCK 13's. All four serialise on this file |
| `src/backend/apps/users/services/pii_inventory.py` (or the BLOCK 3 equivalent) | the `preferred_city` entry | Only if option A was chosen |
| `src/backend/apps/users/services/account_state.py` | read-only reference | `can_login` is BLOCK 8's under option (a) |
| `src/backend/templates/privacy.html` | §6 | **Only §6.** §7 is BLOCK 8's; §2 is untouched; §8's `Data portability.` bullet is §5.6's problem, not this block's |
| `src/backend/locale/{ru,bs,en}/LC_MESSAGES/django.po` | the §6 strings | `§6` is a `{% blocktrans %}` string; `ru`/`bs` must be non-empty |
| `src/backend/apps/users/tests/test_preferred_city.py`, `test_deletion.py` | new tests | Existing modules; the cookie-lifecycle tests must stay green |

**Binding constraints**

1. **Never null `chat_id`.** Any registry entry for it is `RETAIN` with a reason.
2. All three state changes happen **inside `withdraw_consent`'s existing
   `transaction.atomic()` block**, so state and evidence commit or roll back together. The
   existing atomicity-rollback test in `test_deletion.py` is the tripwire.
3. The erasures must go through the BLOCK 3 inventory if it exists, not through a second
   hand-maintained list. **If BLOCK 3 chose option C** (list + guard test), this block edits
   the list and the guard covers the omission.
4. `SavedSearch.is_active` is set with `.update()`, not a loop of `.save()` — it is a bulk
   teardown, and per-row saves would fire signals nobody wants inside a withdrawal.
5. Do **not** introduce a per-request account-state middleware (phase 15). Do **not** touch
   `AccountStateMiddleware` (phase 04/15).
6. §6's rewrite must be **true**. Do not over-promise and do not under-promise; if the copy
   cannot be made true by BLOCK 13 and BLOCK 15, say so in the commit body rather than
   shipping a promise the code does not keep.

**Implementor task**

```yaml
id: task_06_b09_withdraw_teardown
title: "Tear down subscriber state on withdrawal and correct the retention promise (06-PII-110)"
priority: medium
depends_on: [task_06_b03_pii_inventory, task_06_b07_alert_audience_gate]
source_reference: ".ai/plans/06-pii-consent-remediation.md"
source_section: "BLOCK 9 - Withdraw-time teardown, preferred_city, and the section 6 promise"
source_blocks: ["BLOCK 9"]
description: >
  withdrawal leaves SavedSearch rows active for the full 30-day window, leaves
  SearchHistory rows until a cascade that only fires at hard delete, and leaves
  preferred_city set while the matching cookie is deleted. Tear all three down inside
  withdraw_consent's existing transaction and rewrite privacy.html section 6 to say
  what is erased and what is retained, and why. chat_id is retained deliberately and
  must not be nulled.
goals:
  - "make revocation actively tear down subscriber state"
  - "close the cookie/column asymmetry for preferred_city"
  - "make the published 30-day promise true"
files:
  - path: "src/backend/apps/users/services/deletion.py"
    targets:
      - type: function
        name: withdraw_consent
      - type: function
        name: decline_consent
  - path: "src/backend/templates/privacy.html"
    targets:
      - type: template_section
        name: "section 6"
  - path: "src/backend/apps/users/tests/test_deletion.py"
    targets:
      - type: module
        name: test_deletion
changes:
  - action: modify_code
    description: >
      Inside the existing transaction.atomic() block: deactivate the user's
      SavedSearch rows with a bulk update, delete their SearchHistory rows, and clear
      preferred_city on withdrawal and on decline. Rewrite privacy.html section 6 to
      enumerate erased vs retained data with reasons. Fill ru/bs in the same commit.
    code_hint: |
      SavedSearch.objects.filter(user=user).update(is_active=False)
      SearchHistory.objects.filter(user=user).delete()
acceptance_criteria:
  - "after withdrawal the user has no active SavedSearch and no SearchHistory rows"
  - "preferred_city is null on the DB row after a decline and after a withdrawal"
  - "chat_id is unchanged and its registry entry is RETAIN with a reason"
  - "the existing atomicity-rollback test in test_deletion.py passes unchanged"
  - "privacy.html section 6 names the retained data and the reason it is retained"
  - "ru and bs msgstr are non-empty for the changed strings"
tests_to_run:
  - "src/backend/apps/users/tests/test_deletion.py"
  - "src/backend/apps/users/tests/test_preferred_city.py"
  - "src/backend/apps/users/tests/test_preferred_city_readback.py"
  - "src/backend/apps/core/tests/test_privacy.py"
  - "src/backend/apps/ads/tests/test_i18n_completeness.py"
```

**Tests required**

1. **Teardown is real** — after `withdraw_consent`, `SavedSearch.objects.filter(user=...).is_active` is empty and no `SearchHistory` row survives; a **different** user's saved searches are untouched.
2. **The cookie/column asymmetry is closed** — a decline nulls the column as well as the cookie; the explicit "clear" action still works; the login readback still behaves per the recorded Q-D10 decision.
3. **`chat_id` survives** — a test asserting the value is unchanged, so a future refactor cannot quietly "clean it up".
4. **Rollback** — a failure inside the withdrawal transaction leaves **all** the new state changes rolled back. The existing `test_deletion.py` atomicity test is the tripwire; extend it to cover the new writes rather than writing a parallel one.
5. **`privacy.html` renders** in `ru` and `bs` and states the retained-data reason.

**Risk and rollback**

- *Risk:* deleting `SearchHistory` rows surprises a legitimate-interest argument. Mitigation:
  the spec already sanctions first-party `AnalyticsEvent` rows under legitimate interest
  (`technical-specification.md` §F) — but `SearchHistory` is the user's own typed queries
  and its deletion is a **strengthening**, not a conflict. State the reasoning in the
  commit body.
- *Risk:* a bulk `.update()` on `SavedSearch` bypasses `updated_at` maintenance that a
  `.save()` would have done. Mitigation: name the intended semantics in the commit body;
  if `updated_at` matters for the daily cap, the Researcher says so at Q-D10 time.
- *Rollback:* a straight revert. **The deleted rows do not come back** — this is the first
  block in the plan with a one-way data effect. `--dry-run` is not available on a service
  call; the compensating control is that the change is inside a transaction and the
  withdrawal itself is a user-initiated, already-irreversible action.
- *Cross-phase:* BLOCK 10, BLOCK 11 and BLOCK 13 all re-read `deletion.py` after this
  block lands.

---

### BLOCK 10 — Make consent revocation self-auditing (06-PII-107)

| | |
|---|---|
| **Findings owned** | `06-PII-107` |
| **Depends on** | **BLOCK 9** (`deletion.py` serial), and **externally** on phase 04's `04-AUT-005` BLOCK 1 landing |
| **Blocks** | BLOCK 11, BLOCK 13, BLOCK 15 (all re-read `deletion.py`) |
| **Priority** | P1 — raised from the report's framing by the spec promise the Auditor found (`technical-specification.md` §F: *"all accept/decline/withdraw actions are inserted as a new row in the `consent_records` table (never updated)"*) |
| **Risk level** | **HIGH** — it moves a write across the view/service boundary, changes the order relative to `logout()`, and interacts with two other phases' transaction decisions |
| **Required agents** | **Auditor · Researcher · Planner · Validator** (all four) |

**The defect.** The Art. 7(1) audit row for a withdrawal is written by the **view**,
*after* the service call returns, in a separate statement outside `withdraw_consent()`'s
`transaction.atomic()` block. Any non-view caller revokes consent with no audit trail. The
only such caller in production is `UserAdmin.withdraw_consent_action`, which loops the
queryset and calls `withdraw_consent(user)` directly — and the tree confirms it is
**unreachable**, because `UserAdmin` never assigns `actions` (V-03, re-verified).

**The precondition already exists (C-8).** `record_consent_action(user, choice, categories,
request: HttpRequest \| None = None, consent_version=...)` already accepts `None` and its
docstring already documents `None` as the bot `/start` entry point. **No signature change
is required.** The report's stated root cause ("`record_consent_action` is request-aware")
is wrong; the real root cause is that the consent **state** mutation lives in
`deletion.py` and the consent **audit** write lives in `views/consent.py`, and nobody
noticed because the only caller exercising both was a view.

**Decision required before implementation — Q-D7 (wire-or-remove, and the context shape)**

1. **`UserAdmin.withdraw_consent_action`: wire it or remove it.** The report's dead-code
   policy makes this a deliberate decision, not a delete recommendation. **Phase 06 is
   the only phase that may touch it** — phase 04 §5.4 forbids BLOCK 1 from touching it and
   BLOCK 6 from changing the `ConsentRecord` write. If it is **wired**, it needs a
   superuser gate (a bare `is_staff` moderator revoking a seller's consent is a new
   capability, not a bug fix) and the `ConsentRecord` write must be in place first — which
   is why the wire/remove choice sits *after* the audit move in the same block.
2. **The context value object's shape and location.** The recommendation is a small typed
   object carrying `ip_address`, `user_agent`, `session_key`, rather than passing
   `HttpRequest` into the domain layer (project rule 3, separation of concerns). Options:
   (i) a frozen dataclass / `NamedTuple` in `apps/users/services/consent_record.py`; (ii)
   explicit keyword arguments on `withdraw_consent` / `decline_consent` / `give_consent`;
   (iii) passing `request` through and accepting the layering compromise. **(iii) is
   weakest and this plan does not choose** — the Researcher must argue the shape and the
   import direction it implies (`deletion.py` currently imports only `apps.ads.models`,
   `apps.core.enums.AdStatus`, `apps.search.services.cache`, `apps.users.models`).

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/users/services/deletion.py` | `withdraw_consent`, and `give_consent` / `decline_consent` for symmetry | **The order in the file is load-bearing for BLOCK 9 and BLOCK 13.** Keep the transaction boundary where it is |
| `src/backend/apps/users/services/consent_record.py` | the context object declaration (**if** option i), `record_consent_action`, `_anonymize_ip` | `_anonymize_ip` already zeroes the IPv4 last octet and masks IPv6 to a /64 — the report's characterisation is accurate; do not change it |
| `src/backend/apps/users/services/__init__.py` | the re-export surface, **if** a new public symbol is added | |
| `src/backend/apps/users/views/consent.py` | `consent_accept`, `consent_decline`, `consent_withdraw` — pass the context instead of writing the row | The view keeps the request-derived data; the service keeps the write. **Separation of concerns, not a move of responsibility** |
| `src/backend/apps/users/admin.py` | `UserAdmin.withdraw_consent_action` — **wire or remove only**; **the field contract is not this block's** | Phase 04 BLOCK 1 owns `fieldsets` / `form`. §5.4 |
| `src/backend/apps/users/tests/test_deletion.py`, `test_consent_records.py` | new service-level assertion | `test_consent.py`'s `before + 1` delta assertions are scoped to the view and must stay green |

**Binding constraints**

1. The `ConsentRecord` write happens **inside `withdraw_consent`'s existing
   `transaction.atomic()` block**, so state and evidence commit or roll back together.
2. **Do not change when `record_consent_action` runs relative to `logout()`**, except by
   the move this block exists to make. Phase 03's `DB-004` and phase 04's BLOCK 6 both
   depend on that ordering being deliberate; the commit body must state the new order.
3. `ConsentRecord` is **append-only** — "never updated" is a deliberate Art. 7(1) property.
   No `update()` anywhere.
4. Do **not** touch `UserAdmin`'s `fields`, `fieldsets`, `form` or permission predicates.
   Phase 04 BLOCK 1 owns that. This block may only wire or remove the one action, and only
   under the recorded Q-D7 decision.
5. `_anonymize_ip`'s behaviour is unchanged.
6. If the action is **wired**, `actions` must be an explicit declaration consistent with
   project rule 10, and the `test_consent.py`-style view-level assertions must not be
   relied on for the admin path.

**Implementor task**

```yaml
id: task_06_b10_consent_audit_in_service
title: "Move the ConsentRecord write into withdraw_consent and wire-or-remove the admin action (06-PII-107)"
priority: high
depends_on: [task_06_b09_withdraw_teardown, phase04_block1]
source_reference: ".ai/plans/06-pii-consent-remediation.md"
source_section: "BLOCK 10 - Make consent revocation self-auditing"
source_blocks: ["BLOCK 10"]
description: >
  The Art. 7(1) audit row for a withdrawal is written by the view, outside the
  service's transaction, so a non-view caller revokes consent with no evidence. Move
  the write into withdraw_consent behind an explicit context object per the Q-D7
  decision, and wire or remove UserAdmin.withdraw_consent_action.
goals:
  - "make the service that performs the erasure also own the evidence that it happened"
  - "remove or gate the unwired admin action"
files:
  - path: "src/backend/apps/users/services/deletion.py"
    targets:
      - type: function
        name: withdraw_consent
      - type: function
        name: give_consent
      - type: function
        name: decline_consent
  - path: "src/backend/apps/users/services/consent_record.py"
    targets:
      - type: function
        name: record_consent_action
  - path: "src/backend/apps/users/views/consent.py"
    targets:
      - type: function
        name: consent_withdraw
  - path: "src/backend/apps/users/admin.py"
    targets:
      - type: method
        name: withdraw_consent_action
  - path: "src/backend/apps/users/tests/test_deletion.py"
    targets:
      - type: module
        name: test_deletion
changes:
  - action: modify_code
    description: >
      Accept an explicit consent context on the service functions and write the
      ConsentRecord inside the existing atomic block. Update the views to pass the
      context rather than write the row. Wire or remove the admin action per Q-D7.
    code_hint: |
      # Not HttpRequest in the domain layer (project rule 3). A small typed
      # context object carrying ip_address / user_agent / session_key.
acceptance_criteria:
  - "a withdrawal through the SERVICE (no view, no request) writes a WITHDRAWN ConsentRecord"
  - "the audit row and the state change commit or roll back together"
  - "ConsentRecord remains append-only"
  - "withdraw_consent_action is either removed or gated on is_superuser and wired"
  - "UserAdmin's field contract, form and permission predicates are untouched"
  - "test_consent.py's view-scoped ConsentRecord deltas pass unchanged"
tests_to_run:
  - "src/backend/apps/users/tests/test_deletion.py"
  - "src/backend/apps/users/tests/test_consent_records.py"
  - "src/backend/apps/users/tests/test_consent.py"
  - "src/backend/apps/users/tests/test_admin_pii_containment.py"
```

**Tests required**

1. **Service-level audit row** — call `withdraw_consent(user)` with no view and no request
   and assert a `choice='WITHDRAWN'` `ConsentRecord` exists. This is the test the report
   asks for and it is **red** before this block.
2. **Transaction coupling** — a failure after the audit write rolls the audit row back with
   the state change. The existing `test_deletion.py` atomicity test is the tripwire to
   extend.
3. **Symmetry** — `give_consent` / `decline_consent` produce their rows through the service
   as well, if the Q-D7 shape covers them.
4. **Wire/remove** — if wired, a superuser can revoke through the admin **and** a plain
   `is_staff` user cannot, **and** the row is audited; if removed, no `actions` entry
   references it.
5. **Regression** — `test_consent_records.py`'s existing matrix (anonymous row has
   `user_id IS NULL`, `ip_address` anonymised, `user_agent` truncated) green unchanged.

**Risk and rollback**

- *Risk (transaction ordering):* moving the write into the service changes when it happens
  relative to `logout()`. Mitigation: binding constraint 2 and a named commit-body note;
  phase 03's `DB-004` and phase 04's BLOCK 6 must be told.
- *Risk (phase 04's file):* `users/admin.py` is phase 04 BLOCK 1's file. This block may
  touch **only** `withdraw_consent_action`. §5.3. If phase 04's BLOCK 1 has not landed, this
  block **waits** — its dependency is not ceremonial: making the flags non-editable is what
  guarantees every consent-state transition goes through the service that writes the row.
- *Risk (wiring the action):* turning a dead code path into a live capability is a scope
  expansion, not a fix. The wire/remove decision must be recorded explicitly.
- *Rollback:* a straight revert. The extra `ConsentRecord` rows already written are
  append-only and are **not** removed by the revert — that is correct (an audit ledger
  keeps what it recorded) and must be stated.

---

### BLOCK 11 — Ad-text scrub on withdrawal, or the spec correction (06-PII-109, Q-D3)

| | |
|---|---|
| **Findings owned** | `06-PII-109`, `VAL-009` (**as a verification, not a work item**) |
| **Depends on** | **BLOCK 10** (`deletion.py` serial) |
| **Blocks** | BLOCK 13 |
| **Priority** | P1 |
| **Risk level** | **HIGH** — it destroys user content **irreversibly** and is user-visible |
| **Required agents** | **Auditor · Researcher · Planner · Validator** (all four) |

**The defect.** `soft_delete_user_ads(user)` collects `AdImage.storage_keys()` for the
user's `DRAFT` ads, then iterates `Ad.objects.filter(user=user)` and calls
`ad.transition_to(AdStatus.DELETED)` per ad — deliberately **not** a bulk
`QuerySet.update()`, so the `post_save` signal (search-cache bump) fires and `updated_at`
refreshes. **Nothing touches `title`, `title_bs`, `title_en`, `description`,
`description_bs`, `description_en` or `rejected_reason`.** `AdAdmin` lists `title`, has
`search_fields = ["title", "description"]` and **no default status filter**, so a staff
account can list and full-text-search a withdrawn seller's body for the full 30-day
window. On a classifieds board the description is the most likely place for a seller to
have typed their own name, a phone number, or a "call me at…" line.

**`VAL-009` is overstated and must not become a work item (C-5).** The report treats
"scrub the text without re-deriving the FTS vectors" as a new-leak hazard. The tree
disposes of it: `apps/ads/migrations/0001_initial.py` installs
`CREATE TRIGGER ads_search_vector_update BEFORE INSERT OR UPDATE ON ads FOR EACH ROW
EXECUTE FUNCTION ads_search_vector_fn()`, and `setup_search_triggers` re-installs it
idempotently. A PostgreSQL **row-level** `BEFORE UPDATE` trigger fires for every row a
statement touches, **regardless of how the statement was issued** — including
`QuerySet.update()` and a `RunSQL` data migration. **Any scrub written as an UPDATE
re-derives the vectors for free.** The obligation is **one assertion** in
`apps/ads/tests/test_setup_search_triggers.py`, not a re-derivation mechanism. Building
one would be a speculative abstraction and a silent change to the search index (phase 08's
surface).

**Decision required before implementation — Q-D3 (scrub, or correct the spec)**

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | **Implement the bounded scrub** — overwrite `title*` with a neutral placeholder, `description*` with empty, `rejected_reason` with empty, for the same ad set, inside the withdrawal transaction | **Gains:** closes a real PII retention path and makes the spec's "anonymized" true. **Costs:** **irreversibly destroys seller content**; the ads become unsearchable and untitled; the placeholder is user-visible in the staff changelist; existing deletion tests assert ad **status** only and need a content assertion added; a backfill question arises for ads already in the 30-day window |
| **(b)** | **Correct the spec** — change `technical-specification.md` §F's "Anonymized ads" to "ads are soft-deleted (`status=DELETED`) and retain their original text for 30 days", and record the deviation in `docs/00-overview/doc-maintenance-rules.md` | **Gains:** zero data destruction; the seller keeps their content for the window, which is arguably the friendlier outcome. **Costs:** a PII retention path stays open and the published policy must change to describe it; a data-subject-access request touching a withdrawn seller still surfaces the body; it does not close the finding, it re-describes it |

**The plan does not choose.** Both are defensible; (a) is what the report recommends and
(b) is what the report offers as the escape if (a) is judged too destructive. The owner
must pick, and the pick must be recorded.

**Whatever is chosen, these are not optional**

- A regression test asserting that **no** ad of a withdrawn user retains a seller marker
  string in **any** `title*` / `description*` column — for (b), asserting the *stated*
  behaviour instead, and the test is named as documenting the deviation.
- If (a): the placeholder text is **not** user-visible copy, but if it is rendered
  anywhere it enters the i18n gate. The Researcher must state which.
- If (a): a **backfill** for ads already inside the 30-day window, ordered so it cannot
  run before the schema and the trigger exist.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/users/services/deletion.py` | `soft_delete_user_ads` | **Serialised behind BLOCK 10.** Preserve the per-ad `transition_to` loop for the **status** change and the `post_save` signal; the scrub is a separate write, and the Researcher must state whether it is a per-ad `save(update_fields=...)` or a bulk `update()` — the answer determines whether the FTS trigger and the cache bump behave as expected |
| `src/backend/apps/ads/admin.py` | `AdAdmin.search_fields` / `list_display` — **only if the scrub is waived** | Not touched under option (a) |
| `src/backend/apps/ads/tests/test_setup_search_triggers.py` | the `VAL-009` verification assertion | Existing module, the natural home |
| `docs/01-spec/technical-specification.md` | §F's anonymization wording — **only if option (b)** | Phase 06 holds the reservation; BLOCK 2 and BLOCK 4 also touch this file, and all three serialise |
| `docs/00-overview/doc-maintenance-rules.md` | the deviation record — **only if option (b)** | |
| `src/backend/apps/users/tests/test_deletion.py` | the content assertion | Existing module |

**Binding constraints**

1. The scrub runs **inside `withdraw_consent`'s transaction**, so a failure rolls back both
   the status transition and the scrub.
2. **One assertion** proves the FTS vectors follow the scrub. **No re-derivation
   mechanism**, no `--backfill` job, no change to the trigger.
3. If the scrub is a bulk `QuerySet.update()`, confirm that the search-cache version still
   bumps (the existing per-ad `transition_to` is what fires the signal today). If it does
   not, use per-ad saves or bump explicitly — and say which in the commit body.
4. Do **not** touch `Ad.transition_to`, `ALLOWED_TRANSITIONS` or the DELETED semantics.
   Phase 05 (ad lifecycle) owns the transition.
5. `rejected_reason` is rendered by `AdAdmin` through a display helper that truncates to
   100 chars; the scrub is a **data** change, not a display change.

**Implementor task**

```yaml
id: task_06_b11_ad_text_scrub
title: "Scrub withdrawn ads' user-authored text, or record the spec deviation (06-PII-109)"
priority: high
depends_on: [task_06_b10_consent_audit_in_service]
source_reference: ".ai/plans/06-pii-consent-remediation.md"
source_section: "BLOCK 11 - Ad-text scrub on withdrawal"
source_blocks: ["BLOCK 11"]
description: >
  soft_delete_user_ads transitions status only and leaves every user-authored text
  column byte-for-byte intact for 30 days, while AdAdmin lists and full-text-searches
  those columns with no default status filter. Implement the Q-D3 decision - the
  bounded scrub, or the spec correction - and add the regression assertion. Verify
  the FTS trigger re-derives vectors with one assertion; do not build a mechanism.
goals:
  - "close or re-describe the withdrawn-ad retention path, per the recorded decision"
  - "prove with one assertion that the search vectors follow the scrub"
files:
  - path: "src/backend/apps/users/services/deletion.py"
    targets:
      - type: function
        name: soft_delete_user_ads
  - path: "src/backend/apps/ads/tests/test_setup_search_triggers.py"
    targets:
      - type: module
        name: test_setup_search_triggers
  - path: "src/backend/apps/users/tests/test_deletion.py"
    targets:
      - type: class
        name: TestSoftDeleteUserAds
changes:
  - action: modify_code
    description: >
      Under option (a): overwrite title* / description* / rejected_reason inside the
      withdrawal transaction. Under option (b): leave the data alone and correct the
      spec wording. Either way add the FTS-consistency assertion and the regression
      assertion.
    code_hint: |
      # A PostgreSQL row-level BEFORE UPDATE trigger re-derives the vectors for any
      # UPDATE. Verify it. Do not add a re-derivation path.
acceptance_criteria:
  - "the chosen option is recorded in the commit body with its consequences"
  - "one assertion proves search_vector_ru follows a title update through the trigger"
  - "no re-derivation mechanism, backfill job or trigger change was added"
  - "the status transition and the scrub commit or roll back together"
  - "Ad.transition_to and ALLOWED_TRANSITIONS are unchanged"
tests_to_run:
  - "src/backend/apps/users/tests/test_deletion.py"
  - "src/backend/apps/ads/tests/test_setup_search_triggers.py"
  - "src/backend/apps/ads/tests/test_ads_admin.py"
```

**Tests required**

1. **The FTS assertion (C-5)** — in the test schema, update an ad's `title` and assert
   `search_vector_ru` no longer contains the old token. This single assertion is the entire
   `VAL-009` obligation and it must be **run before the scrub is written**.
2. **Content regression** — no ad of a withdrawn user retains a seller marker string in any
   `title*` / `description*` column (option a), or the test names and documents the
   deviation (option b).
3. **Other users are unaffected** — a different seller's ads are unchanged.
4. **Rollback** — a failure after the scrub leaves the ad at its prior status with intact
   text.
5. **Regression** — the existing deletion tests (status assertions, `updated_at` refresh,
   DRAFT `storage_keys` return, skip-if-already-`DELETED`) pass unchanged.

**Risk and rollback**

- *Irreversible.* Option (a) destroys seller content with no recovery. This is stated in
  the decision record, and the backfill for the existing 30-day window is part of the block
  rather than an afterthought.
- *Risk (search):* if the Researcher chooses a bulk `.update()`, the `post_save` cache
  bump does not fire. Mitigation: binding constraint 3.
- *Rollback:* under option (a) a code revert **cannot restore the destroyed text**. The
  rollback plan is "stop the scrub from running for new withdrawals" plus a documented note
  that already-scrubbed ads are not recoverable. **This must be stated before the block
  runs, not after.**
- *Cross-phase:* phase 08 owns the vector mechanism; phase 05 owns the DELETED transition;
  phase 12's backup/restore interacts with an unrecoverable scrub (§5.6).

---

### BLOCK 12 — Support-ticket admin containment and the declared identity-column guard (06-PII-106, VAL-007)

| | |
|---|---|
| **Findings owned** | `06-PII-106`, `VAL-007` |
| **Depends on** | **BLOCK 4** (the masked display helpers reuse the new `mask_telegram_id`) |
| **Blocks** | nothing; BLOCK 13 re-reads the helper shape |
| **Priority** | P1 — it is a **live staff-visible exposure** today |
| **Risk level** | **LOW-MEDIUM** — display and search configuration only, but three shipped tests pin the current configuration and one is written to produce a false positive |
| **Required agents** | **Auditor · Researcher · Planner · Validator**. **Researcher is required** for Q-D12; **Validator is required** because the new guard must be shown to be red before the fix and green after, and must be shown *not* to false-positive on `SupportContactAdmin` |

**The defect.** `SupportTicketAdmin.list_display` includes raw `chat_id` and `telegram_id`;
`search_fields` includes `text`, making the entire unbounded ticket body a full-text search
target for any `is_staff` account. The model's own `readonly_fields` **already** marks
these columns read-only on the *change* form — the changelist and the search index were
simply never brought under the containment rule `LoginTokenAdmin` already follows. One
changelist screenshot, CSV export or support bundle is a bulk PII disclosure of the
requester's numeric Telegram ID, in the one admin surface the product designed to prevent
exactly that.

**Three shipped tests pin the current configuration and **must** be updated (C-11).**
`apps/core/tests/test_support_admin.py::test_support_ticket_admin_list_display`,
`::test_support_ticket_admin_search_fields` and `::test_support_ticket_admin_readonly_fields`
assert the exact lists, **including** the raw `chat_id`/`telegram_id` and `text`. The
report's rollout row names only `test_admin_pii_containment.py`, which is the **wrong file
for the assertion change** and the **right file for the new guard**. Both statements are
correct and both matter.

**Decision required before implementation — Q-D12 (the shape of the guard)**

`VAL-007`, confirmed against the tree: `SupportContactAdmin` is registered for
`SupportContact`, declares `list_display = ["label", "channel_type", "email", "telegram_id",
"is_active", "ordering"]` with `list_editable`, `search_fields = ["label", "email",
"telegram_id"]`, and has **no `readonly_fields` and no permission override** — because its
`telegram_id` is a *configured support-channel* identifier, not a data subject's, and
channels are meant to be staff-editable. **A blanket "no raw identity column in any
`list_display`" walk over the admin registry will false-positive here, exactly as the
validator predicted.** Options:

| Option | What it is | Trade-off |
|---|---|---|
| **A** | An **explicit declared set of data-subject identity columns**, keyed by model, in the test module; the guard walks the registry and asserts none of those columns appears in a `list_display` without a masking helper | Precise, no false positives, and the declaration is the tripwire for the next user-adjacent model. Cost: a hand-maintained set in a test module — which is the same "forgot to add it" risk the guard is meant to remove, moved rather than solved |
| **B** | A declared set of **exempt** admins (models whose identity columns are operational, not personal) and a blanket deny otherwise | Broader coverage with a small exemption list. Risk: a new admin is denied by default, so a legitimate one needs an exemption added — friction that is arguably correct |
| **C** | Assert only on the named models in scope today (`SupportTicketAdmin`), generalised later | Cheapest, weakest; does not stop the next regression |

**This plan does not choose.** The strong prior is **A or B**; the Researcher must argue
which keeps the false-positive out without creating a maintenance burden worse than the
defect, and must state the trap in the commit body so a future maintainer does not
"simplify" the guard into a blanket ban.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/core/admin.py` | `SupportTicketAdmin` — `list_display`, `search_fields` | Reuse the `LoginTokenAdmin.telegram_id_display` precedent (masking display methods named in `list_display`, not in `readonly_fields`) |
| `src/backend/apps/core/tests/test_support_admin.py` | `test_support_ticket_admin_list_display`, `..._search_fields`, `..._readonly_fields` | **Update deliberately** (project rule 2) and say why in the commit body. `..._list_filter`, `..._add_permission_false`, `..._delete_permission_false` and every `SupportContactAdmin` test must stay **unchanged** |
| `src/backend/apps/users/tests/test_admin_pii_containment.py` | extend with the declared identity-column guard | Existing module; already owns admin-surface PII assertions |
| `src/backend/apps/core/tests/test_sanitize.py` | read-only reference | The new display helpers must go through `mask_telegram_id`, not a second construction |

**Binding constraints**

1. `SupportContactAdmin` is **not** a violation. Its `telegram_id` is a configured channel
   id and it legitimately has no `readonly_fields` or permission override. The guard must
   not red-flag it.
2. The `list_display` entries become **named masking methods** (the `LoginTokenAdmin`
   precedent), not a formatting filter.
3. `text` is dropped from `search_fields`; `ticket_ref`, `telegram_id` and `username` stay
   for genuine support lookups. The Researcher must state whether searching by the raw
   `telegram_id` is itself an exposure and, if so, what replaces it — support agents look
   up by ID, and removing the field removes their only lookup.
4. The helpers must be **`None`-tolerant**, because BLOCK 13 will make `chat_id` and
   `telegram_id` nullable. Writing them twice is worse than writing them once here.
5. Do not add a `readonly_fields` entry or a permission override to `SupportContactAdmin`.
6. The new guard must be demonstrated **red against the pre-fix code** before it goes green.

**Implementor task**

```yaml
id: task_06_b12_support_admin_containment
title: "Mask support-ticket identifiers in the admin and guard data-subject identity columns (06-PII-106)"
priority: medium
depends_on: [task_06_b04_keyed_mask]
source_reference: ".ai/plans/06-pii-consent-remediation.md"
source_section: "BLOCK 12 - Support-ticket admin containment"
source_blocks: ["BLOCK 12"]
description: >
  SupportTicketAdmin renders raw chat_id and telegram_id in the changelist and
  full-text-searches the unbounded ticket body. Replace the two columns with masked
  display methods following the LoginTokenAdmin precedent, drop text from
  search_fields, and add a containment guard built on an explicitly declared set of
  data-subject identity columns that does not false-positive on SupportContactAdmin.
goals:
  - "stop a staff changelist or CSV export from bulk-disclosing a requester's Telegram ID"
  - "stop the whole ticket corpus from being a free-text search target"
  - "make the next user-adjacent model fail loudly instead of silently"
files:
  - path: "src/backend/apps/core/admin.py"
    targets:
      - type: class
        name: SupportTicketAdmin
  - path: "src/backend/apps/core/tests/test_support_admin.py"
    targets:
      - type: function
        name: test_support_ticket_admin_list_display
      - type: function
        name: test_support_ticket_admin_search_fields
  - path: "src/backend/apps/users/tests/test_admin_pii_containment.py"
    targets:
      - type: module
        name: test_admin_pii_containment
changes:
  - action: modify_code
    description: >
      Add None-tolerant masked display methods delegating to mask_telegram_id, put
      them in list_display, drop text from search_fields, and add the declared
      data-subject identity-column guard.
    code_hint: |
      @admin.display(description="Telegram ID")
      def telegram_id_display(self, obj: SupportTicket) -> str:
          return mask_telegram_id(obj.telegram_id)
acceptance_criteria:
  - "no raw identity column of a data-subject model appears in a list_display without a masking helper"
  - "SupportContactAdmin does not trip the guard"
  - "text is no longer a search target"
  - "the masking helpers return a usable value for None, because BLOCK 13 makes the columns nullable"
  - "the three updated tests name in their docstring why the configuration changed"
tests_to_run:
  - "src/backend/apps/core/tests/test_support_admin.py"
  - "src/backend/apps/users/tests/test_admin_pii_containment.py"
  - "src/backend/apps/core/tests/test_support_models.py"
```

**Tests required**

1. **The guard, demonstrated red first.** Add it, run it against the pre-fix
   `SupportTicketAdmin`, record the failure, then fix and re-run.
2. **The guard's negative case.** `SupportContactAdmin` is in the registry and the guard
   passes. This test exists to stop a future "simplification".
3. **No raw value in the changelist.** Rendering a ticket's changelist row (or calling the
   display methods) does not produce the raw `chat_id` or `telegram_id` — the same shape of
   assertion the module's four existing helper tests use.
4. **`None` tolerance** — a ticket with `chat_id = None` renders a sensible value, proving
   BLOCK 13 will not need a second implementation.
5. **Regression** — every `SupportContactAdmin` test and
   `..._list_filter` / `..._add_permission_false` / `..._delete_permission_false` passes
   **unchanged**.

**Risk and rollback**

- *Risk:* removing `telegram_id` from `search_fields` removes support's only lookup. The
  block keeps it; the Researcher must state whether searching by raw `telegram_id` is
  itself an exposure and what replaces it if so. Do not remove a lookup without an answer.
- *Risk (the trap):* a later maintainer replaces the declared set with a blanket ban and
  the guard red-flags `SupportContactAdmin`. Mitigation: the trap is named in the module
  docstring and in the commit body.
- *Rollback:* a straight revert. No data, no schema.

---

### BLOCK 13 — Scrub `SupportTicket` identity on erasure (06-PII-101, CRITICAL)

| | |
|---|---|
| **Findings owned** | `06-PII-101` — **the only CRITICAL in the phase** |
| **Depends on** | **BLOCK 3** (the inventory), **BLOCK 10** (`deletion.py` serial), **BLOCK 12** (the helper shape), **BLOCK 11** (last `deletion.py` edit before the sweep half), the **Q-D2 product decision**, and **phase 03's `consent_hard_delete` logging change** having landed |
| **Blocks** | nothing in this plan; it is the phase's headline deliverable |
| **Priority** | **P0** |
| **Risk level** | **CRITICAL** — schema migration + data migration + an irreversible content destruction that removes support's only correlation key |
| **Required agents** | **Auditor · Researcher · Planner · Validator** (all four) |

**The defect (C-1, C-7).** `SupportTicket` denormalises identity into its own columns:
`chat_id` and `telegram_id` are **non-nullable** `BigIntegerField`s, `username` is
`CharField(max_length=255, null=True, blank=True)`, all copied verbatim from the Telegram
sender. The account link is a nullable `ForeignKey(..., on_delete=SET_NULL, null=True,
blank=True, related_name="support_tickets")`. `withdraw_consent()` never touches
`support_tickets`. `consent_hard_delete` NULLs exactly two references —
`AnalyticsEvent.user_id` and `ModeratorActionLog.user_id` — and then calls
`queryset.delete()`. Django's collector honours the ticket FK's `SET_NULL`, so the ticket
row is **updated to `user_id = NULL` and kept**, with every raw identifier byte-for-byte
intact and no remaining link to any account. The published `privacy.html` §6 promises
*"All personal data is permanently erased within 30 days of withdrawal"* — a direct,
provable breach.

**The impact wording is corrected (C-7).** The row is **not** unfindable:
`SupportTicket.objects.filter(user_id__isnull=True)` finds it in one query. The defect is
**retention**, and it is silent and self-concealing because `SET_NULL` removes the only
user-scoped handle a future purge would have used. **No acceptance criterion in this block
asserts that the row cannot be found.**

**Decision required before implementation — Q-D2 (product decision, not engineering)**

Three coupled questions, all owner-level:

1. **What replaces the ticket's identity as a support lookup key?** The raw
   `chat_id` / `telegram_id` / `username` are the only human-readable correlation a
   support agent has. A keyed hash? A redacted handle (e.g. `tg_…` + last two)? Nothing?
   **If nothing, how does support answer a question about an erased account?** This is a
   product decision and the report is explicit that it is not the Planner's to make.
2. **Storage shape:** nullable columns + a sentinel backfill for pre-existing rows (the
   report's preference), or a `0` sentinel with no schema change. `0` is migration-free
   but leaves an ambiguous row that every later query must special-case; nullable is a
   two-column `AlterField` on `core` plus a sentinel backfill.
3. **Scrub or delete the row?** The report assumes scrub. Deleting is simpler and destroys
   the audit trail `SupportTicketAdmin`'s own docstring ("read-only audit trail") exists
   to preserve.

**This plan does not choose any of the three.** The block ships a decision record plus the
implementation of the chosen shape.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/core/models.py` | `SupportTicket` — `chat_id`, `telegram_id` nullability | **`core` app, not `users`.** Migration numbers are sequential **per app**; check the directory immediately before generating |
| `src/backend/apps/core/migrations/<next>_*.py` | `AlterField` (nullability) + a `RunPython` data migration | Two migrations or one — the Researcher's call, and `makemigrations --check` must be clean |
| `src/backend/apps/users/services/deletion.py` | `withdraw_consent` — clear `telegram_id`, `chat_id`, `username` for the user's tickets, **inside the existing `transaction.atomic()`** | The fourth and last `deletion.py` edit in this plan |
| `src/backend/apps/core/management/commands/consent_hard_delete.py` | `Command.handle` — the same scrub for `user_id__in=user_ids`, **before** `queryset.delete()`, **inside the same `transaction.atomic()`** | **Sequenced against phase 03's logging change to this same command** (§5.3) |
| `docs/02-database/db-schema.md` | the `support_tickets` table notes | Required by project rule 14 |
| `src/backend/apps/core/tests/test_sweep_consent.py` | extend — the sweep contract | Existing module; the crash-rollback test is the tripwire |
| `src/backend/apps/core/tests/test_support_models.py`, `test_support_admin.py` | extend | BLOCK 12's `None`-tolerant helpers are relied on here |

**The data migration must cover three populations**, and the third is the one that is easy
to forget: rows whose `user_id` still points at a **withdrawn** user, rows already
**orphaned** (`user_id IS NULL`) before this change, and rows that **predate** the schema
change. The validator's evidence shows the second population already exists in the wild.
The migration must be idempotent (`RunPython(forward, reverse_or_none)`) and must **not**
delete rows.

**Binding constraints**

1. **Both halves are required.** `withdraw_consent` alone leaves the 30-day path
   self-insufficient if the row was never touched at withdrawal; the sweep alone leaves
   the 30-day window in breach. `privacy.html` §6's promise covers **30 days**, so the
   withdrawal-time scrub is the one that must be right.
2. The sweep's scrub must be **inside the same `transaction.atomic()`** as the null-updates
   and the `delete()`. `test_sweep_consent.py` already pins a crash between those steps
   rolls everything back; **that test is the guard for this block's placement.**
3. `AdvisoryLockId.CONSENT_HARD_DELETE == 3` **must not be renumbered**, and the command's
   `--lock-id` stays `CONSENT_HARD_DELETE` (pinned by
   `test_sweep_consent.py::test_lock_id_is_consent_hard_delete`).
4. The command's summary log must keep reporting the **user count** and must keep the
   words `"cascaded"` and `"rows incl. ads/images"` — phase 03's logging block depends on
   that field set.
5. The migration **scrubs; it never deletes.** A `RunPython` that drops rows is
   unrecoverable and out of scope for a backfill.
6. If the Q-D2 answer is "delete the row", that is a **different** migration with a
   different risk profile and must be re-scoped before it is written, not improvised inside
   this one.
7. `SupportTicket.save()` generates `ticket_ref` and is `editable=False`; the scrub must
   not disturb it — `ticket_ref` is the **retained** correlation key under the most likely
   Q-D2 answer, and it is already non-personal.
8. **No `core` migration number may be assumed.** Check `src/backend/apps/core/migrations/`
   immediately before generating; phase 02 claimed `core/0006_*` under its own option.

**Implementor task**

```yaml
id: task_06_b13_support_ticket_scrub
title: "Scrub support-ticket identity on erasure (06-PII-101)"
priority: high
depends_on: [task_06_b03_pii_inventory, task_06_b10_consent_audit_in_service, task_06_b11_ad_text_scrub, task_06_b12_support_admin_containment, q_d2_decision]
source_reference: ".ai/plans/06-pii-consent-remediation.md"
source_section: "BLOCK 13 - Scrub SupportTicket identity on erasure"
source_blocks: ["BLOCK 13"]
description: >
  SupportTicket.chat_id and .telegram_id are non-nullable copies of the sender's
  Telegram identity, and the SET_NULL user FK means they survive both the withdrawal
  and the 30-day hard delete with every identifier intact. Implement the recorded Q-D2
  decision: the core-app nullability migration, the idempotent data migration covering
  withdrawn, already-orphaned and pre-existing rows, the withdrawal-time scrub, and the
  sweep-time scrub before queryset.delete() inside the same transaction.
goals:
  - "make the published 30-day erasure promise true for support history"
  - "keep the support correlation key that the Q-D2 decision chose to retain"
files:
  - path: "src/backend/apps/core/models.py"
    targets:
      - type: class
        name: SupportTicket
  - path: "src/backend/apps/users/services/deletion.py"
    targets:
      - type: function
        name: withdraw_consent
  - path: "src/backend/apps/core/management/commands/consent_hard_delete.py"
    targets:
      - type: class
        name: Command
      - type: method
        name: handle
  - path: "src/backend/apps/core/tests/test_sweep_consent.py"
    targets:
      - type: module
        name: test_sweep_consent
  - path: "docs/02-database/db-schema.md"
    targets:
      - type: document_section
        name: "support_tickets table"
changes:
  - action: add_migration
    description: >
      AlterField for the chosen nullability shape plus an idempotent RunPython data
      migration covering withdrawn, already-orphaned and pre-existing rows. The
      migration scrubs; it never deletes.
  - action: modify_code
    description: >
      Clear the identity columns for the user's tickets inside withdraw_consent's
      existing atomic block, and again in consent_hard_delete for user_id__in=user_ids
      before queryset.delete(), inside the same transaction.
    code_hint: |
      SupportTicket.objects.filter(user=user).update(
          telegram_id=None, chat_id=None, username=None,
      )
acceptance_criteria:
  - "no ticket of a withdrawn user retains a raw chat_id, telegram_id or username in any state"
  - "the data migration is idempotent and covers already-orphaned rows"
  - "a crash between the scrub and queryset.delete() rolls everything back"
  - "AdvisoryLockId.CONSENT_HARD_DELETE is still 3 and the sweep's lock-id test passes"
  - "the sweep's summary log still reports the user count and keeps its existing words"
  - "ticket_ref is unchanged on every row"
  - "makemigrations --check is clean"
tests_to_run:
  - "src/backend/apps/core/tests/test_sweep_consent.py"
  - "src/backend/apps/core/tests/test_support_models.py"
  - "src/backend/apps/core/tests/test_support_admin.py"
  - "src/backend/apps/users/tests/test_deletion.py"
```

**Tests required**

1. **Withdrawal-time scrub** — after `withdraw_consent(seller)`, a ticket belonging to that
   seller carries no raw identifier; a ticket belonging to a **different** seller is
   untouched. The second half is what stops an over-broad filter from shipping.
2. **Sweep-time scrub** — after `consent_hard_delete` for a row past the grace window, the
   ticket carries no raw identifier **and** the user is gone.
3. **Backfill** — a pre-existing **orphaned** row (`user_id IS NULL`, full identifiers) is
   scrubbed by the data migration, and running the migration twice is a no-op.
4. **Rollback** — the existing crash-between-steps test still passes **unchanged**, proving
   the scrub is inside the transaction. **If it has to be modified to pass, the block is
   wrong.**
5. **Retention is explicit** — the correlation key the Q-D2 decision chose to keep (almost
   certainly `ticket_ref`) is still present on a scrubbed ticket, and the reason it is
   retained is documented in the model or the admin docstring.
6. **Fresh schema** — `.\Makefile.ps1 test-recreate` (or the equivalent `--create-db` run)
   must pass **after** the migration lands. This is mandatory, not optional.

**Risk and rollback**

- *Irreversible data destruction.* Scrubbing a ticket identifier cannot be undone. The
  compensating control is the decision record: the owner chose to destroy it, with the
  support consequence stated.
- *Migration risk.* Two `AlterField`s on a `core` table plus a `RunPython`. Risk is low
  (`SET NULL` on a bigint), but the numbering collision with phase 02's claimed
  `core/0006_*` is real. Check the directory; never renumber.
- *Rollout risk (the report's own High rating):* historical ticket rows lose their lookup
  key. Support agents lose a way to correlate a ticket with a now-erased account. **This
  is the trade the owner is making in Q-D2**, and the block must not ship without the
  record.
- *Rollback:* the **code** reverts cleanly. The **data** does not come back, and the data
  migration's `reverse` must be a deliberate `RunPython.noop` with a comment saying so —
  never a data-restoring reverse, which would re-create the leak.
- *Cross-phase:* **phase 03's `consent_hard_delete` logging block must land first** and
  this block must re-read the command. The two diffs touch the same method and must be
  **sequenced, not parallel** (§5.3).

---

### BLOCK 14 — `SearchHistory.query_normalized` keeps un-redacted PII (06-PII-108)

| | |
|---|---|
| **Findings owned** | `06-PII-108` (substantive half) |
| **Depends on** | **BLOCK 9** (the withdrawal teardown defines the retention story this block completes) and the **Q-D5 decision** |
| **Blocks** | nothing |
| **Priority** | P1 |
| **Risk level** | **MEDIUM** — it changes a stored value and a dedup key, and the anonymous session store has the same split |
| **Required agents** | **Auditor · Researcher · Planner · Validator** (all four) |

**The defect, narrowed by the tree (C-6).** `record_search_history` computes
`normalized = query.strip().lower()` from the **raw** query, computes
`redacted = redact_search_query(query)`, then
`SearchHistory.objects.create(user_id=…, query=redacted, query_normalized=normalized)`. It
dedupes on `query_normalized` and prunes to `_MAX_HISTORY = 50` rows per user. The report's
original claim that the *full query text* is stored is imprecise — `query` **is** redacted.
What is true, and what the auditor missed, is that **`query_normalized` keeps the raw,
lower-cased, un-redacted query** as the dedup key: phones, e-mail addresses and personal
names that `redact_search_query` deliberately strips from `query` survive verbatim. And
`_record_session_history` has **the same split** — the anonymous session store
(`_SESSION_KEY = "search_history"`) receives the raw `normalized` as its key and the
redacted string as its value. So the defect exists in **both** stores, not only the table.
`SearchHistory.user` is `CASCADE`; BLOCK 9 now deletes these rows on withdrawal.

**The documentation half is de-scoped.** Both public surfaces **already** scope "Analytics"
to Plausible: the `components/consent_banner.html` bullet reads *"Analytics — anonymized
traffic analytics via Plausible"*, and `privacy.html` §2 reads *"Traffic analytics via
Plausible (anonymized) — legal basis: your consent (analytics category)"* with a
`consent_analytics` cookie-table row and a third-party list entry. The naming collision
survives only in three internal names. Correcting correct copy has no audience (§6.1).

**Decision required before implementation — Q-D5 (redact or key-digest)**

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | Store `redact_search_query(normalized)` as the dedup key | **Gains:** no new secret; the key is human-readable and stays debuggable; the session store gets the same treatment with no key management. **Costs:** two differently-formatted PII-bearing queries collapse into one dedup bucket, so `"my phone is 123"` and `"123"` merge; the redaction must be applied to the *normalised* string, and the helper never lengthens (a safe invariant for the `max_length=200` columns) |
| **(b)** | Store a keyed digest of the normalised query as the key, keeping the redacted text as the value | **Gains:** deduplication semantics preserved exactly; no PII at all in the key. **Costs:** **a second secret dependency** on top of `LOG_MASK_KEY` (or a third); the key is opaque; the session store needs the key too, and a session payload that cannot be read across a key rotation; the secret's rotation story doubles |
| **(c)** | Both — redact for the column, digest for the key | **Gains:** no PII in either. **Costs:** the most machinery for the smallest defect, and the report's own note is that the column value is the *reason* the row exists at all |

**The plan does not choose.** The Researcher must weigh the dedup-semantics loss against
the second secret, and the Planner must state the answer. Note the interaction: BLOCK 4
introduces `LOG_MASK_KEY`. Reusing it here is tempting and **wrong** if the two have
different rotation needs — a mask rotation is cheap, a dedup-key rotation orphans every
stored key and every session payload at once.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/search/services/search_history.py` | `record_search_history`, `_record_session_history`, `_MAX_HISTORY`, `_SESSION_KEY` | **Both stores are in one module** — that is the module's single responsibility boundary and it must be respected |
| `src/backend/apps/search/tests/test_redact_search_query.py` | read-only reference | The helper's own matrix, including a phone case |
| `src/backend/apps/search/tests/` | new tests for the key and for the session store | New or existing module; do not bloat the redaction-helper test module |
| `docs/01-spec/technical-specification.md` | §F's search-history line, **only if the written retention statement needs it** | Phase 06 holds the reservation; BLOCKS 2, 4 and 11 also touch this file and all serialise |

**Binding constraints**

1. **Both stores are fixed or neither is.** A fix that leaves
   `_record_session_history` raw keeps the same PII in the same request.
2. `redact_search_query` **never lengthens** — a deliberate invariant so the
   `max_length=200` caps on `SearchHistory.query` and `PopularSearch.query` stay safe.
   Any new key derivation must preserve that, or the column caps must be re-checked.
3. `redact_search_query` is documented as being designed for **search queries**. If it is
   applied to a normalised dedup key, that is a use consistent with its design; if a
   general-purpose redactor were needed, it would be a new abstraction and is out of scope.
4. Do **not** change the consent **enforcement** behaviour. The spec already sanctions
   first-party `AnalyticsEvent` rows under legitimate interest; there is no violated gate
   and none is introduced here.
5. `SearchHistory.user` remains `CASCADE`. BLOCK 9's explicit deletion on withdrawal is the
   retention bound; this block is the *write* path.
6. Do not rename `CookieCategory.ANALYTICS`, the `consent_analytics` cookie or the
   `consent_analytics` context key — the documentation half is de-scoped (§6.1).

**Implementor task**

```yaml
id: task_06_b14_search_history_key
title: "Stop storing the un-redacted query as the search-history dedup key (06-PII-108)"
priority: medium
depends_on: [task_06_b09_withdraw_teardown, q_d5_decision]
source_reference: ".ai/plans/06-pii-consent-remediation.md"
source_section: "BLOCK 14 - SearchHistory.query_normalized"
source_blocks: ["BLOCK 14"]
description: >
  record_search_history stores the redacted query in `query` but the raw normalised
  query in `query_normalized`, so phones, e-mail addresses and personal names survive
  in the dedup key. The anonymous session store has the same split. Implement the
  recorded Q-D5 decision in both stores.
goals:
  - "keep PII out of the dedup key in the database and in the session"
  - "preserve or explicitly accept the deduplication semantics, per the decision"
files:
  - path: "src/backend/apps/search/services/search_history.py"
    targets:
      - type: function
        name: record_search_history
      - type: function
        name: _record_session_history
  - path: "src/backend/apps/search/tests/test_redact_search_query.py"
    targets:
      - type: module
        name: test_redact_search_query
changes:
  - action: modify_code
    description: >
      Apply the Q-D5 key derivation in both the ORM and the session store, and add
      tests asserting no phone, e-mail or personal name survives in the key.
    code_hint: |
      # The session store and the table must receive the same treatment.
acceptance_criteria:
  - "no phone number, e-mail address or personal name survives in query_normalized"
  - "the anonymous session store carries the same guarantee"
  - "redact_search_query's never-lengthen invariant is preserved"
  - "the consent enforcement behaviour is unchanged"
  - "the deduplication outcome matches the recorded Q-D5 decision"
tests_to_run:
  - "src/backend/apps/search/tests/test_redact_search_query.py"
  - "src/backend/apps/search/tests/"
```

**Tests required**

1. **The leak is closed, in the table** — a search containing a phone number, an e-mail
   address and a multi-word capitalised name produces a `SearchHistory` row in which
   **none** of the three survives in **any** column.
2. **The leak is closed, in the session** — the same search through the anonymous path
   produces a session payload with the same guarantee. **This half is the reason the block
   exists; a test that covers only the table is incomplete.**
3. **Deduplication still behaves as the decision states** — two searches that should merge
   merge, and two that should not do not.
4. **Column caps** — a long query still fits `max_length=200`.
5. **Regression** — `test_redact_search_query.py`'s full matrix passes **unchanged**; the
   `_MAX_HISTORY = 50` pruning behaviour is unchanged.

**Risk and rollback**

- *Risk:* a keyed digest that depends on a secret makes the session payload unreadable and
  breaks across a rotation. Mitigation: binding constraint 1 plus the Q-D5 decision, which
  must address rotation explicitly if option (b) is chosen.
- *Risk:* a dedup regression silently changes "recent searches" for sellers. Mitigation:
  test 3.
- *Rollback:* a straight revert for the code. **Stored rows already written keep their
  old keys**; a backfill to re-derive existing keys is a separate decision, and this plan
  does not schedule one (the rows are bounded by `_MAX_HISTORY` per user and by BLOCK 9's
  withdrawal deletion). Record that as a known residue in the commit body.

---

### BLOCK 15 — `ConsentRecord` retention sweep and changelist exposure (06-PII-116, Q-D4)

| | |
|---|---|
| **Findings owned** | `06-PII-116`, and the `ConsentRecord.session_key` / `.user_agent` half of `06-PII-110` (**absorbed**) |
| **Depends on** | **BLOCK 10** (the sweep must be ordered so it can never delete a record the audit path still needs), and the **Q-D4 decision** |
| **Blocks** | nothing |
| **Priority** | P2 |
| **Risk level** | **HIGH** — a new destructive command in `HOURLY_COMMANDS`, a lock that is **no longer free** (C-3), and a TTL that is a **legal/business** number |
| **Required agents** | **Auditor · Researcher · Planner · Validator** (all four) |

**The defect.** `ConsentRecord` grows without bound. Every row carries a `session_key`
(a live Django session identifier, `CharField(max_length=40, null=True, blank=True)`), the
full 500-char `user_agent` and a partially-masked `ip_address`. `user` is `on_delete=SET_NULL`,
so these rows **outlive** the user by construction. `scheduler.HOURLY_COMMANDS` lists
exactly nine commands and **none** purges `consent_records` (C-2). And
`ConsentRecordAdmin.list_display` includes `session_key` with `search_fields == ["session_key"]`,
so any staff user can enumerate live session identifiers.

**Honest severity framing.** A `session_key` alone is not a cookie; exploiting it still
requires the cookie value. This is an **exposure-reduction** argument, not a standalone
hijack. The Validator should say so rather than overstate it.

**Decision required before implementation — Q-D4 (two coupled decisions)**

1. **The TTL number — a business/legal decision, not engineering.** The anchor is
   `CONSENT_REPROMPT_DAYS = 365` in `apps/users/context_processors.py`, which is also the
   number `views/consent.py::CONSENT_COOKIE_MAX_AGE` encodes as `365 * 24 * 60 * 60`. The
   report explicitly declines to recommend a number and so does this plan. **Shipping a
   sweep without an agreed TTL would delete Art. 7(1) evidence on an invented schedule.**
2. **The advisory lock — it is no longer free (C-3).** `AdvisoryLockId` is an `IntEnum`
   with **19** members (IDs 1–9, 11, 12, **13**, 100–104, 110, 111); ID 10 is reserved.
   A concurrent phase-02 agent took **13** (`REPAIR_BOT_USERNAME`) mid-pass, so
   `.ai/plans/03-db-concurrency-remediation.md`'s "18 members, next free is 13" is **stale**
   and the next free integer is **14**. Options: (i) **reuse an existing id** with a
   written rationale — the precedent is phase 03, which reused `ARCHIVE_SWEEP`,
   `RECOMPUTE_NORMALIZED_PRICES` and `ALERT_DELIVERY_TASK` rather than allocating; (ii)
   **allocate a new id**, which requires `apps/core/enums.py`, the lock-allocation table in
   `advisory_lock.py`'s module docstring, and `apps/core/tests/test_advisory_lock_ids.py`
   to change **in one commit**, **and the coordinator to be told first** (§5.3). The
   Researcher must state which and justify it; the Planner records it.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/users/management/commands/purge_consent_records.py` | **new** — a `--dry-run`-capable sweep | Does not exist today. Model it on `consent_hard_delete` / the existing `purge_*` commands |
| `src/backend/apps/core/utils/scheduler.py` | `HOURLY_COMMANDS` | **A tenth entry.** `run_scheduler` calls `_validate_commands(HOURLY_COMMANDS + DAILY_COMMANDS)` before the loop, so the command **must** be discoverable via `django.core.management.get_commands()` or the scheduler refuses to start |
| `src/backend/apps/core/enums.py`, `apps/core/utils/advisory_lock.py`, `apps/core/tests/test_advisory_lock_ids.py` | **only if** option (ii) is chosen | **Three files, one commit, coordinator notified first** |
| `src/backend/apps/users/admin.py` | `ConsentRecordAdmin.list_display` — drop `session_key` | `search_fields` **keeps** `session_key` for support lookups. Do not touch `readonly_fields` or the permission predicates (phase 04's file) |
| `src/backend/apps/users/tests/` | new tests for the sweep and the changelist | |
| `src/backend/templates/privacy.html` | §6 — the retention period | **A third editor of §6** (after BLOCK 9). Re-read; §6 must state one period, not two |
| `docs/02-database/db-retention.md` | the `consent_records` retention row | Also a shared file (phase 03) — §5.3 |

**Binding constraints**

1. **`--dry-run` is mandatory**, following `consent_hard_delete`.
2. **The sweep must never delete a record still needed to demonstrate consent.** Rows
   inside the TTL are Art. 7(1) evidence and are kept, full stop. For rows **past** the
   TTL whose `user` is still set, **null `session_key`** (and consider the same for
   `user_agent`) rather than deleting the row outright — a superuser-only
   `has_delete_permission` currently exists and suggests deletion is considered
   appropriate, which is exactly the decision the TTL answers.
3. `HOURLY_COMMANDS` insertion point and the `_stop_aware_dispatch` contract: a skipped
   command returns `0` and that `0` is load-bearing in the **daily** gate. The new
   hourly entry must not change the daily marker's behaviour.
4. `AdvisoryLockId.CONSENT_HARD_DELETE == 3` is **not** this command's lock and must not
   be renumbered.
5. If a new lock id is allocated, the three files change in **one** commit and the
   coordinator is notified **before**, not after.
6. `privacy.html` §6 must state **one** retention period. If BLOCK 9 and this block both
   rewrite §6, the second editor re-reads the first's text and does not reintroduce a
   superseded sentence.

**Implementor task**

```yaml
id: task_06_b15_consent_record_sweep
title: "Add a ConsentRecord retention sweep and remove session_key from the changelist (06-PII-116)"
priority: medium
depends_on: [task_06_b10_consent_audit_in_service, q_d4_decision]
source_reference: ".ai/plans/06-pii-consent-remediation.md"
source_section: "BLOCK 15 - ConsentRecord retention sweep"
source_blocks: ["BLOCK 15"]
description: >
  ConsentRecord grows without bound, carries a live session_key and a 500-char
  user_agent, outlives the user by construction, and appears in the staff changelist
  and search index. Add a purge_consent_records command to HOURLY_COMMANDS with a
  --dry-run, per the agreed TTL and the recorded lock decision, and drop session_key
  from ConsentRecordAdmin.list_display.
goals:
  - "bound the retention of the consent audit ledger at an agreed period"
  - "stop a live session identifier being enumerable in the staff changelist"
files:
  - path: "src/backend/apps/users/management/commands/purge_consent_records.py"
    targets:
      - type: class
        name: Command
  - path: "src/backend/apps/core/utils/scheduler.py"
    targets:
      - type: constant
        name: HOURLY_COMMANDS
  - path: "src/backend/apps/users/admin.py"
    targets:
      - type: class
        name: ConsentRecordAdmin
  - path: "src/backend/templates/privacy.html"
    targets:
      - type: template_section
        name: "section 6"
changes:
  - action: add_code
    description: >
      New hourly sweep: delete rows past the TTL, null session_key (and user_agent per
      the decision) on rows whose user is still set, keep every row inside the TTL, and
      support --dry-run. Append it to HOURLY_COMMANDS. Remove session_key from
      ConsentRecordAdmin.list_display but keep it in search_fields.
    code_hint: |
      # Rows inside the TTL are Art. 7(1) evidence. Never delete them.
acceptance_criteria:
  - "--dry-run deletes nothing and reports what a real run would do"
  - "a row inside the TTL survives with its session_key intact"
  - "a row past the TTL is deleted, or its session_key is nulled, per the decision"
  - "the scheduler still starts: _validate_commands resolves the new entry"
  - "the daily marker behaviour is unchanged"
  - "session_key no longer appears in ConsentRecordAdmin.list_display and still appears in search_fields"
  - "privacy.html section 6 states one retention period"
tests_to_run:
  - "src/backend/apps/core/tests/test_scheduler_wiring.py"
  - "src/backend/apps/core/tests/test_sweep_lock_structure.py"
  - "src/backend/apps/core/tests/test_advisory_lock_ids.py"
  - "src/backend/apps/users/tests/"
```

**Tests required**

1. **`--dry-run` deletes nothing** — the count is unchanged and the summary names the same
   numbers a real run would.
2. **The TTL boundary** — a row **inside** the TTL survives with its `session_key` intact
   (this is the Art. 7(1) guarantee and the block's most important assertion); a row past
   it is deleted or nulled per the decision.
3. **The sweep is idempotent** — a second run reports nothing to do.
4. **The scheduler still starts** — `run_scheduler`'s `_validate_commands` resolves
   `purge_consent_records` via `get_commands()`. Adding a tenth entry changes
   `test_scheduler_wiring.py` / `test_sweep_lock_structure.py`; update them deliberately
   and name why in the commit body.
5. **The lock is correct** — if a new id was allocated, the three-file change is in the
   same commit and `test_advisory_lock_ids.py` covers it; if an existing id was reused, the
   test shows the reuse is deliberate.
6. **The changelist** — `session_key` is absent from `list_display` and present in
   `search_fields`, asserted as two separate facts.

**Risk and rollback**

- *Irreversible.* Deleting a `ConsentRecord` destroys the Art. 7(1) evidence. Mitigation:
  the TTL is a recorded business decision, `--dry-run` is mandatory, and test 2 pins the
  in-TTL guarantee.
- *Risk (lock):* allocating an id that another phase is about to allocate. Mitigation: the
  coordinator is told **before**; the enum, the docstring table and the guard test change
  together; and the numbers are re-read at implementation time because **13 was taken
  mid-pass**.
- *Risk (scheduler):* a tenth entry changes several scheduler tests and the
  `_stop_aware_dispatch` contract. Mitigation: binding constraints 3 and 4.
- *Rollback:* the code reverts cleanly. **Purged rows do not come back** — the rollback for
  a wrong TTL is "correct the TTL forward", not "restore the data". State this before the
  block runs.
- *Cross-phase:* phase 12's backup/restore interacts with a purge (§5.6).

---

### BLOCK 16 — Redact moderator and ad-rejection free text at write time (06-PII-114)

| | |
|---|---|
| **Findings owned** | `06-PII-114` |
| **Depends on** | **nothing** in this plan (BLOCK 3's registry is a *nice-to-have* consumer, not a prerequisite) |
| **Blocks** | nothing |
| **Priority** | P2 |
| **Risk level** | **MEDIUM** — it changes what staff-authored text looks like after the fact, and the helper's contract was written for a different input class |
| **Required agents** | **Auditor · Researcher · Planner · Validator** (all four — the helper-contract question is a genuine design question, not a mechanical application) |

**The defect.** `ModeratorActionLog.reason` is an **unbounded** `TextField` documented
*"Moderation reason (INTERNAL ONLY - never shown to seller)"*, with `ad` and `user` both
`on_delete=SET_NULL` — so the row survives user erasure as an orphan. **No write site
redacts it:** every `ModeratorActionLog.objects.create(..., reason=reason, ...)` in
`apps/moderation/services/moderation_log.py` passes `reason` straight through
(`log_auto_moderation_failure`, `log_rejection`, `log_auto_published`, `log_manual_publish`,
`log_ban_account`, `log_soft_delete`, `set_moderation_failed`, `set_rejected`), and
`apps/moderation/admin_actions.py` forwards its `reason: str` argument unchanged from
`reject_ad`, `ban_user_for_ad`, `soft_delete_ad`, `bulk_reject`, `bulk_ban_users` and
`bulk_delete`. `apps/moderation/views/api_bulk.py` reads `payload.reason` from a Pydantic
schema (`apps/moderation/schemas.py`: `reason: str = ""`) and forwards it.
`Ad.rejected_reason` is the same shape and is rendered in `AdAdmin.list_display` through a
helper that truncates to 100 chars at render time only.

Low in practice, because the fields are staff-authored — but a moderator quoting a seller's
message (*"user said: call me on +382 69 000 123"*) persists that PII **indefinitely**, in a
row erasure can no longer associate with and therefore can no longer clean up. Combined with
`06-PII-101` this is a **second orphan-PII channel**.

**Decision required before implementation — is `redact_search_query` the right helper?**

The report's recommendation is to run `reason` and `rejected_reason` through
`redact_search_query()` at write time, and its own caveat stands: that helper is documented
as being designed for **search queries**. The Researcher must state whether applying it to
moderator prose is (a) a use consistent with its contract, (b) a case for a **new**
general-purpose redactor, or (c) a case for a cheaper, narrower rule. The tree gives two
facts that bear on this: the helper **never lengthens** (so it is column-safe on an
unbounded `TextField` and on `Ad.rejected_reason`), and it truncates to
`_MAX_QUERY_LENGTH = 100` — which on a moderator reason field would **silently discard
most of the operator's text**. That truncation is the strongest argument in the block and it
must be resolved explicitly, not noticed afterwards.

The alternatives the Researcher must weigh: redact only the high-value patterns
(phone / e-mail / handle) with a small dedicated helper and no truncation; cap the field
length instead; or add a moderation-UI help-text note telling moderators not to paste
seller details (the report's "optionally", which is a mitigation, not a fix).

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/moderation/services/moderation_log.py` | every `ModeratorActionLog.objects.create` call site (eight writers) | One choke point if the redaction is applied inside a single helper — the Researcher must choose between a helper and per-call-site redaction and say why |
| `src/backend/apps/moderation/admin_actions.py` | `reject_ad`, `ban_user_for_ad`, `soft_delete_ad`, `bulk_reject`, `bulk_ban_users`, `bulk_delete` | **Phase 03's file** (lock behaviour) and phase 05's (ad lifecycle); phase 04 touches it **comments only** (§5.3) |
| `src/backend/apps/moderation/models.py` | `ModeratorActionLog.reason` — `help_text` and a field note | The help-text note is the cheapest part of the recommendation and should ship regardless |
| `apps/ads/` — the `Ad.rejected_reason` write site | the reject path | Under `apps/ads/` or `apps/moderation/` — locate by symbol, not by assumption |
| `src/backend/apps/moderation/tests/` | new tests | |

**Binding constraints**

1. Redaction happens **at write time**, not at render time. A render-time filter leaves
   the PII in the database and does not survive an export.
2. Fixed literals (`"Bulk rejection via admin action"`, `"Bulk ban via admin action"`,
   `"Bulk deletion via admin action"`, `log_auto_moderation_failure`'s literal) must pass
   through **unchanged**. A test must prove the fixed literals are not mangled — this is
   the most likely regression in the block.
3. **Do not change `on_delete`, the permission predicates or the "INTERNAL ONLY" contract.**
   Only the stored value changes.
4. Do not add a per-row save loop where a write-time helper suffices.
5. `apps/moderation/admin_actions.py` is contended by three phases. Stage explicitly; never
   revert a concurrent change (§1.3, §5.3).

**Implementor task**

```yaml
id: task_06_b16_moderation_text_redaction
title: "Redact moderator and ad-rejection free text at write time (06-PII-114)"
priority: low
depends_on: []
source_reference: ".ai/plans/06-pii-consent-remediation.md"
source_section: "BLOCK 16 - Redact moderator and ad-rejection free text"
source_blocks: ["BLOCK 16"]
description: >
  ModeratorActionLog.reason and Ad.rejected_reason are unbounded free text that
  survives user erasure as an orphan, and no write site redacts it. Apply the recorded
  redaction decision at write time, update the field help text, and prove the fixed
  literals are unchanged.
goals:
  - "stop a moderator quoting a seller's contact details from persisting them forever"
  - "do it at write time, so no export and no backup carries the value"
files:
  - path: "src/backend/apps/moderation/services/moderation_log.py"
    targets:
      - type: module
        name: moderation_log
  - path: "src/backend/apps/moderation/admin_actions.py"
    targets:
      - type: function
        name: bulk_reject
  - path: "src/backend/apps/moderation/models.py"
    targets:
      - type: class
        name: ModeratorActionLog
changes:
  - action: modify_code
    description: >
      Apply the recorded redaction decision at every write site, update the reason
      field help text with an explicit instruction, and add the fixed-literal
      regression assertion.
    code_hint: |
      # redact_search_query truncates to 100 chars. On a moderator reason field that
      # silently discards operator text. Resolve that before applying it.
acceptance_criteria:
  - "a reason containing a phone number, e-mail address or handle stores none of them"
  - "the fixed literals pass through byte-identical"
  - "redaction happens before the row is written, not at render time"
  - "on_delete, permission predicates and the INTERNAL ONLY contract are unchanged"
  - "the field help text tells moderators not to paste seller details"
tests_to_run:
  - "src/backend/apps/moderation/tests/"
  - "src/backend/apps/ads/tests/"
```

**Tests required**

1. **Redaction at write time** — a `reason` containing a phone number, an e-mail address
   and a `@handle` produces a stored row with none of them; assert on the **stored
   value**, not on the admin rendering.
2. **The fixed literals survive** — every literal reason the writers use is stored
   byte-identical. This is the block's main regression risk.
3. **`Ad.rejected_reason` too** — the same guarantee on the ad's rejection field.
4. **Operators can still work** — a reason with no PII is stored unchanged, so the feature
   is not silently destroying legitimate text.
5. **Regression** — the existing moderation action tests pass **unchanged**, including
   phase 03's `test_bulk_ban_users_not_locked` tripwire.

**Risk and rollback**

- *Risk:* silently truncating moderator text (the `100`-char cap). Mitigation: the
  decision must resolve it explicitly; test 4 makes the loss visible.
- *Risk (process):* `admin_actions.py` is contended by phases 03, 04 and 05. Mitigation:
  §5.3; the commit body names the file.
- *Rollback:* a straight revert. **Already-written rows keep their un-redacted values** —
  a backfill is a separate decision and is not scheduled here. State that residue.

---

### BLOCK 17 — Drop the vestigial personal column (06-PII-111)

| | |
|---|---|
| **Findings owned** | `06-PII-111` |
| **Depends on** | **nothing** |
| **Blocks** | nothing |
| **Priority** | P2 — the lowest-severity item in the plan |
| **Risk level** | **LOW** — a `RemoveField` on a column nothing reads or writes |
| **Required agents** | **Auditor · Implementor**. **Researcher, Planner and Validator not required** — the decision is already made by the validator (drop the column) and the plan does not reopen it. The Auditor must re-verify the zero-writer claim (C-15) before the change, because that claim is the whole justification |

**The defect, with its premise refuted.** `SellerVerification` declares
`phone_number = models.CharField(max_length=20, blank=True, null=True)`, a category of
personal data the project has explicitly declared it does not hold
(`technical-specification.md`: *"Collect minimum: `telegram_id`, optional `username` …
nothing beyond Telegram login is stored"*). The auditor's runtime evidence
(`phone_number still present = +38269000001`) was **the probe's own insert**, not
application behaviour. What survives validation is a much smaller defect: an **undeclared,
permanently-`NULL`, non-reachable** PII column in the schema, absent from `privacy.html` §2
and from the spec's data list. `apps/trust/` has **no `admin.py`**, so the model is not even
staff-reachable, and the trust badge reads `verified_by_admin` + `SellerTrustScore`
(`apps/trust/templatetags/trust_tags.py`, `apps/trust/services/trust_calculator.py`) —
never `phone_number`.

**The recommendation is inverted from the original finding.** Because nothing writes the
column, adding it to `withdraw_consent()`'s null set is pointless. The correct primary
action is the one the auditor listed second: **drop the column**. That is strictly simpler
and permanently removes the undocumented-category problem.

**The alternative the plan does not silently discard.** If the field is genuinely required
for a future manual-verification workflow, it must (a) be added to the withdrawal null set,
(b) be disclosed in `privacy.html` §2 and `technical-specification.md`, and (c) be masked in
any admin `list_display`. **Pick one branch deliberately; do not leave it as a dormant,
undocumented column.** The Auditor's re-verification of the zero-writer claim is what
selects the branch — if a writer appears between the report and this block, the block
becomes a disclosure task instead of a schema task, and the Planner must be told.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/trust/models.py` | `SellerVerification` — remove the `phone_number` field | **`trust` app, not `users`.** Check `src/backend/apps/trust/migrations/` immediately before generating |
| `src/backend/apps/trust/migrations/<next>_*.py` | `RemoveField` | `makemigrations --check` must be clean afterwards |
| `docs/02-database/db-schema.md` | the `seller_verifications` table notes | Project rule 14 |
| `docs/01-spec/technical-specification.md`, `src/backend/templates/privacy.html` | **only if the disclosure branch is taken** | Phase 06 holds the spec reservation; the doc blocks serialise |

**Binding constraints**

1. Re-verify the zero-writer claim **immediately before** the change, with a grep over
   `src/` and a `ModelAdmin` registry check. Two of the four grep hits are unrelated test
   assertions (`tests/test_json_logging.py`, `apps/search/tests/test_redact_search_query.py`)
   — do not mistake them for writers.
2. The migration is a plain `RemoveField`. **No data migration, no backfill, no sentinel.**
3. Do **not** touch `verified_by_admin`, `verified_at`, the `OneToOneField` to `User`, the
   trust-score calculation or any `trust_tags` template logic.
4. `makemigrations --check` clean, and the fresh-schema run passes (§8.2).

**Implementor task**

```yaml
id: task_06_b17_drop_phone_number
title: "Drop the vestigial SellerVerification.phone_number column (06-PII-111)"
priority: low
depends_on: []
source_reference: ".ai/plans/06-pii-consent-remediation.md"
source_section: "BLOCK 17 - Drop the vestigial personal column"
source_blocks: ["BLOCK 17"]
description: >
  SellerVerification.phone_number is a permanently-NULL, staff-unreachable, undisclosed
  personal-data column that nothing in src/ writes. Remove it via a RemoveField
  migration in the trust app, after re-verifying the zero-writer claim.
goals:
  - "remove an undocumented personal-data category from the schema permanently"
files:
  - path: "src/backend/apps/trust/models.py"
    targets:
      - type: class
        name: SellerVerification
  - path: "docs/02-database/db-schema.md"
    targets:
      - type: document_section
        name: "seller_verifications table"
changes:
  - action: add_migration
    description: >
      RemoveField for phone_number, generated with makemigrations in the trust app.
  - action: modify_code
    description: >
      Delete the field declaration and update the schema documentation.
acceptance_criteria:
  - "the zero-writer claim was re-verified immediately before the change and is recorded in the commit body"
  - "makemigrations --check is clean and the fresh-schema run passes"
  - "verified_by_admin, verified_at, the User one-to-one and the trust badge are unchanged"
  - "no data migration and no backfill were written"
tests_to_run:
  - "src/backend/apps/trust/tests/"
```

**Tests required** — none new. The report is right that a removal needs no behavioural
test, and `makemigrations --check` plus a fresh-schema run cover the schema. The existing
trust tests must pass **unchanged**.

**Risk and rollback**

- *Risk:* a writer appears between the report and this block. Mitigation: binding
  constraint 1 — re-verify immediately before changing, and stop and report if it fails.
- *Rollout:* the column is empty in every environment (the validator's probe found 0 rows),
  so the `RemoveField` drops an empty column. A non-empty column in a real deployment would
  make this a data-losing migration; **if a deployment check shows rows, stop and escalate
  rather than dropping them.**
- *Rollback:* re-adding the field is possible but would resurrect an undocumented data
  category. A revert is therefore a last resort, and the commit body says so.

---

## 4. Dependency graph

### 4.1 Execution order (the safe serial order)

One Implementor, strictly sequential. Every block is one commit (§1.3).

| # | Block | Findings | Depends on (in-plan) | External gate | Risk |
|---|---|---|---|---|---|
| 1 | DECLINE-reversibility decision | `06-PII-105` (half), `VAL-001` | — | — | process |
| 2 | DECLINE doc adjudication | `06-PII-113`, `VAL-001`, `VAL-004` | 1 | coordinator authorisation for the rubric | LOW |
| 3 | PII erasure inventory | Required Fix 1 | — | — | MEDIUM |
| 4 | Keyed `LOG_MASK_KEY` mask | `06-PII-112`, `VAL-008` | — | — | **HIGH** |
| 5 | Mask the alert failure logs | `06-PII-102` | 4 | — | MEDIUM |
| 6 | Account-state predicate | `06-PII-104a`, `VAL-003` | — | Q-D6 ownership confirmation | MEDIUM |
| 7 | Gate the alert paths | `06-PII-104b` | 6 | — | **HIGH** |
| 8 | DECLINE recovery implementation | `06-PII-105` (half) | 1, 2 | mechanism decision | **HIGH** |
| 9 | Withdraw teardown + `preferred_city` + §6 | `06-PII-110` (kept half) | 3, 7 | Q-D10 | MEDIUM |
| 10 | Consent audit in the domain layer | `06-PII-107` | 9 | **`04-AUT-005` (phase 04 BLOCK 1) landed**; Q-D7 | **HIGH** |
| 11 | Ad-text scrub / spec correction | `06-PII-109`, `VAL-009` | 10 | Q-D3 | **HIGH** |
| 12 | Support-ticket admin containment | `06-PII-106`, `VAL-007` | 4 | Q-D12 | LOW-MEDIUM |
| 13 | `SupportTicket` identity scrub | `06-PII-101` | 3, 10, 11, 12 | **Q-D2 (product)**; **phase 03's `consent_hard_delete` logging landed** | **CRITICAL** |
| 14 | `SearchHistory` dedup key | `06-PII-108` | 9 | Q-D5 | MEDIUM |
| 15 | `ConsentRecord` retention sweep | `06-PII-116` | 10 | Q-D4 (legal TTL + lock) | **HIGH** |
| 16 | Moderator free-text redaction | `06-PII-114` | — | helper-contract decision | MEDIUM |
| 17 | Drop the vestigial column | `06-PII-111` | — | zero-writer re-verification | LOW |

### 4.2 The DAG and why each edge exists

```
                 [1 DECLINE decision]
                    |            \
                    v             v
              [2 doc adjudication]  (none)
                                       \
        (none)                          v
           |                       [8 DECLINE recovery]
      [3 PII inventory]                |
           |                           |
           |                           v
           |                  [6 predicate]  <-- Q-D6 gate
           |                           |
           |                           v
           |                  [7 alert gating]
           |                           |
           +------------+--------------v
                        v
              [9 withdraw teardown]  <-- Q-D10
                        |
                        v
              [10 consent audit in service]  <-- 04-AUT-005 (external) + Q-D7
                        |
          +-------------+-------------+------------------+
          v             v             v                  v
      [11 ad scrub] [15 record sweep]  ...          (14 joins here)
          |            <-- Q-D4
          |
      [3] + [10] + [12] + [11] + Q-D2 + phase 03
                        |
                        v
            [13 SupportTicket scrub]  (CRITICAL)

  [4 keyed mask] --> [5 log masking]
        |
        +----------> [12 support admin containment]  <-- Q-D12

  (none) --> [16 moderator redaction]
  (none) --> [17 drop vestigial column]
```

**Each edge, with the reason it exists:**

| Edge | Why it exists |
|---|---|
| **1 → 2** | The doc edit must state whether DECLINE is reversible. Writing the sentence before the decision exists means writing it twice, and `spec-index.md` is phase 06's single-owner file. |
| **1 → 8** | BLOCK 8's scope depends entirely on the answer. Under option (a) it edits `can_login` (an auth-predicate change requiring its own security review); under option (b) it does not. Implementing before the decision means implementing the wrong thing. |
| **3 → 9** | BLOCK 9 is the first edit to the erasure transaction. It should extend one declaration rather than add a second hand-maintained list. |
| **3 → 13** | `SupportTicket` is a new identity-denormalising table. If the registry exists, the scrub is a registry entry; if it does not, the scrub is a bespoke path and the sixth such column arrives next time. |
| **4 → 5** | The report's hard rule: *"Do not mask into a reversible digest. Landing the two call sites before the construction buys nothing."* Two ordered commits, never the reverse order. |
| **4 → 12** | BLOCK 12's masked display helpers call `mask_telegram_id`. Building them on the old construction means writing them twice, once per construction. |
| **6 → 7** | BLOCK 7 must consume one declaration. If the call sites are edited first, there is no declaration to consume and the rule is written inline at four places — the exact defect `VAL-003` exists to prevent. |
| **7 → 9** | BLOCK 9's `SavedSearch` deactivation mirrors the eligibility rule BLOCK 7 declares. Deactivating on the wrong rule leaves an active saved search for an account that is no longer eligible. |
| **9 → 10** | Both rewrite `withdraw_consent`'s transaction. One implementor, one commit each, serialised — never merged. |
| **9 → 14** | BLOCK 14 bounds what is *stored*; BLOCK 9 bounds what is *retained after withdrawal*. Shipping the retention bound without the storage fix leaves live PII in every surviving row, and shipping the storage fix without the retention bound leaves the storage growing unbounded. |
| **10 → 11** | `soft_delete_user_ads` lives in the same module `withdraw_consent` does. Serialised on the file. |
| **10 → 13** | Same file, same function, and the ticket scrub must land on a `withdraw_consent` whose transaction boundary is final (BLOCK 10 is the block that moves the audit write into it). |
| **10 → 15** | The report's ordering constraint: *"the `ConsentRecord` sweep must be ordered so it can never delete a record still needed for an Art. 7(1) demonstration."* BLOCK 10 is what makes every consent transition write a row; the sweep's TTL must be reasoned about against the post-BLOCK-10 write rate, not the pre-block one. |
| **11 → 13** | Both are irreversible content destruction in the same transaction. They are sequential so that a crash, a revert and an incident review each have a single blast radius. |
| **12 → 13** | BLOCK 12's display helpers are written **`None`-tolerant** on purpose so BLOCK 13 does not have to rewrite them when the columns become nullable. The edge is a *shape* dependency, not a logic one: if BLOCK 12's helpers turn out not to be `None`-tolerant, this edge becomes a hard one and BLOCK 13 must re-read them. |
| **1 → 2, 1 → 8** | See above. |
| **10 → (external `04-AUT-005`)** | Making `is_declined` / `is_deleted` / `ads_auto_publish` non-editable in the admin is what *guarantees* every consent-state transition goes through the service that writes the audit row. Wiring the admin action before that would create a live path with no audit row — the exact defect BLOCK 10 closes. **This edge is external and phase 06 does not control it.** |
| **13 → (external phase 03)** | Phase 03's block changes `consent_hard_delete`'s logging; BLOCK 13 adds a column scrub inside the same `transaction.atomic()` in the same method. **Sequenced, never parallel.** |
| **15 → (external coordinator)** | A new `AdvisoryLockId` requires three files in one commit with the coordinator told **first** (C-3: the free id is **14**, not 13). |

### 4.3 Where there is deliberately no edge, and why

| Pair with no edge | Why |
|---|---|
| **2 ↔ 3, 2 ↔ 4** | `spec-index.md` and `technical-specification.md` are different files. BLOCK 2 edits only the former; BLOCK 4 (and conditionally 11, 14) edit only the latter. Disjoint regions. With one Implementor they run in series anyway. |
| **5 ↔ 7 ↔ 11** | `immediate_alerts.py` and `alert_query.py` are shared with **phase 03 BLOCK 9**, not with each other. Phase 03 owns the *delivery-state* contract; phase 06 owns *eligibility*. Neither phase 06 block needs the other's change to be correct. If the coordinator serialises phases 03 and 06, that is a **cross-phase** edge (§5.3), not an in-phase one. |
| **7 ↔ 8** | Different domains: `apps/search` audience selection vs. the `apps/users` consent state machine. No shared file, no shared decision. |
| **13 ↔ 14** | `SupportTicket` erasure vs. `SearchHistory` write-path redaction. Disjoint models, disjoint modules. |
| **16 ↔ 17** | `apps/moderation` + `apps/ads` free text vs. an `apps/trust` schema column. No shared file, no shared decision, no shared migration. They stay separate for **independent reviewability**, not because an edge forbids merging. |
| **16 → 3** | BLOCK 3's registry is an *erasure* inventory. `ModeratorActionLog.reason` is a **write-time redaction** concern, not an erasure-scope one — adding it to the registry would be a category error. If BLOCK 3 chose option A and the Researcher concludes the registry should also carry write-time redaction rules, that is a **scope expansion** and must be argued, not slipped in. |
| **3 → 4, 3 → 5, 3 → 6** | BLOCK 3 is architectural and self-contained. It has no call-site consumers until BLOCK 9. Running it early is safe; making it depend on anything else would delay the phase's architectural fix for no reason. |

### 4.4 The three orders that are unsafe

1. **BLOCK 5 before BLOCK 4** — masking into a 32-bit unsalted digest. The two call sites
   would look fixed and provide no pseudonymisation at all.
2. **BLOCK 13 before BLOCK 11** — two irreversible content destructions in the same
   transaction, landed as one review unit. A revert then cannot separate them.
3. **BLOCK 15 with an invented TTL** — a destructive sweep on a schedule nobody agreed to
   would delete Art. 7(1) evidence. This is not an ordering hazard; it is a **gate**, and
   the gate is the TTL decision (Q-D4), not a predecessor.

### 4.5 What the DAG does *not* decide

The DAG orders blocks. It does **not** resolve Q-D1 … Q-D10, Q-D12. Each of those is a
**gate inside a block**, recorded in that block's `extra_context`, and §8.1 checks that a
written answer exists for each. A block whose gate is unanswered does not start.

---

## 5. Cross-phase coordination

Phases 01 and 02 are executed or in flight; phases 03 and 04 are `planned`; phases
05–15 are being planned in parallel right now by other Planner agents. This section is
the boundary contract. It is deliberately **one-directional**: phase 06 states what it
owns, what it will not touch, and where its boundaries lie. It does **not** attempt to
contact or negotiate with the other agents.

### 5.1 What phase 06 already owns and must not re-ship

| Phase 06 artefact | What phase 06 must not do | Boundary |
|---|---|---|
| **`06-PII-113` / `VAL-001` — the DECLINE doc conflict.** Phase 06 is the **finding of record**; `04-VAL-005` becomes a cross-reference | Phase 06 must not edit `.ai/audit/**` to record the cross-reference, and must not edit phase 04's plan file. The cross-reference is recorded **in this plan** (§5.4) | Phase 04 §5.6: *"Phase 04 does not edit `spec-index.md` or `technical-specification.md` for this."* Phase 06's BLOCK 2 is the single owner of the `spec-index.md` edit. |
| **`06-PII-103` → `04-AUT-005` (merged).** One `fieldsets` declaration closes the credential half and the consent half | **Phase 06 must not patch `UserAdmin`'s field contract again.** `UserAdmin` declares no `fields`, no `fieldsets`, no `form`, and `withdraw_consent_action` is still unwired | Phase 04 BLOCK 1 owns it. Phase 06's BLOCK 10 touches **only** `withdraw_consent_action` and only under a recorded wire-or-remove decision. |
| **`technical-specification.md`** — phase 06 holds the reservation | Phase 06 edits it in **four** places (BLOCKS 2 is `spec-index.md`; BLOCKS 4, 11, 14 touch the technical spec). All serialise. Phase 04 edits only under its BLOCK 8 option (c), and only after checking for a concurrent edit | §5.3. One editor at a time; never a wholesale regeneration. |
| **`06-PII-116` absorbs the `ConsentRecord.session_key` / `.user_agent` half of `06-PII-110`** | Phase 06 must not ship a second `ConsentRecord` TTL | One sweep, one TTL, one decision (BLOCK 15). BLOCK 9 touches `privacy.html` §6 but **not** the `ConsentRecord` retention sentence. |
| **The alert recipient-selection rule** | Phase 06 owns **who is eligible**; phase 03 owns **the delivery-state contract** (what has already been sent) | Phase 03's own §5.2 says: *"BLOCK 9 must **not** change the recipient-selection logic… Phase 06 owns who is eligible."* `find_matching_saved_searches` is the boundary file. |

### 5.2 What phase 06 must not do, for other phases' sake

| Other phase | What phase 06 must not do | Boundary |
|---|---|---|
| **Phase 03 — `DB-007` (alert delivery serialisation)** | BLOCK 7 must **not** change delivery-state de-duplication, the notification-recording contract, or move collection across the `ALERT_DELIVERY_TASK` lock or the transaction boundary. BLOCKS 5 and 7 both edit `immediate_alerts.py` and `alert_query.py`, which are phase 03 BLOCK 9's files | **Sequenced, not parallelised.** Phase 03's `consent_hard_delete` **logging** block and phase 06's BLOCK 13 **scrub** touch the same method of the same command — one lands, then the other re-reads. |
| **Phase 03 — `AdvisoryLockId`** | BLOCK 15 must not allocate a new id without the coordinator being told **first**, and then `enums.py`, `advisory_lock.py`'s lock-allocation docstring and `test_advisory_lock_ids.py` must change **in one commit** | **C-3: the free id is `14`, not `13`.** A concurrent agent took `13` mid-pass and phase 03's plan still says 18 members. Re-read the enum at implementation time. `CONSENT_HARD_DELETE == 3` must never be renumbered. |
| **Phase 04 — `04-AUT-002` / `04-AUT-006`** | BLOCK 8 must not change `can_login()` **unless** BLOCK 1 chose option (a), and then must coordinate with `04-AUT-002`, which touches the same predicate. No block may set `SESSION_COOKIE_AGE` / `SESSION_SAVE_EVERY_REQUEST` / `SESSION_EXPIRE_AT_BROWSER_CLOSE` — that is `04-AUT-006` | The session-lifetime dependency is exactly **why** BLOCK 8's recovery path must be session-independent. |
| **Phase 04 — BLOCK 6's decline-path `logout()`** | Phase 06 must not ship BLOCK 8's implementation before BLOCK 1 publishes the decision, and must publish the decision **as early as possible** | **This is the hard gate.** §5.5. |
| **Phase 04 — the `ConsentRecord` write** | Phase 04 BLOCK 6 must not change the `ConsentRecord` write; **phase 06 is the only phase that may** | BLOCK 10 is that change. §5.4. |
| **Phase 04 / 15 — the bot's `AccountStateMiddleware`** | **No block may touch it.** Its `_resolve_user` does `User.objects.get(chat_id=chat_id)` and its `_check_user_state(chat_id)` signature is documented **load-bearing** and pinned by bot tests (`TestCheckUserStateMessages`, `TestCrossPredicateAgreement`, `test_backfill_uses_stable_chat_id`) | This is the mechanical reason `chat_id` must survive (`06-PII-110`), and the reason BLOCK 6's **default-manager filter is forbidden**: it would hide withdrawn users from the middleware and re-open a hole. |
| **Phase 15 — `15-AUTHZ-001` (per-request account-state middleware)** | Phase 06 must **not** add one. BLOCKS 7 and 8 stop consent state at the delivery and consent boundaries | `04-VAL-001`'s hard rule: both phases must not file the same middleware. |
| **Phase 15 — `AUTHZ-003`** | Phase 06 must not touch `UserAdmin`'s permission predicates. `has_change_permission` returning `request.user.is_staff` — where `is_staff` **is** the moderator role, because `User.role` maps `is_staff` / `is_superuser` to `ADMIN` and no separate moderator role exists — is phase 15's territory (`VAL-002`) | The *field set* and the *root cause* were phase 06's; the *permission* half is phase 15's. §5.4. |
| **Phase 15 — `AUTHZ-005` (the predicate framework)** | Phase 06 owns the **semantics** of the account-state predicate (BLOCK 6); phase 15 owns the **framework** that enforces it across both processes | `VAL-003`. §5.6. |
| **Phase 05 — ad lifecycle** | BLOCK 11 must **not** change `Ad.transition_to`, `ALLOWED_TRANSITIONS` or the DELETED semantics. The scrub is a data change inside a transaction that already routes through `transition_to` | Phase 05 owns the transition; phase 06 owns what the withdrawn ad's text becomes. |
| **Phase 08 — search FTS** | BLOCK 11 must **not** modify the trigger, add a re-derivation mechanism, or change `setup_search_triggers` | `VAL-009` is **overstated** (C-5). One assertion, no mechanism. |
| **Phase 11 — test coverage** | The test rewrites in BLOCKS 4, 5, 8 and 12 are **incidental rewrites required by a behaviour change**, not coverage improvements. Phase 06 must not expand them into new coverage while rewriting them | A rewrite that grows into new coverage raises the regression risk of the block. |
| **Phase 12 — production ops** | Backup/restore interacts with three irreversible operations: the ticket scrub (BLOCK 13), the ad scrub (BLOCK 11) and the record purge (BLOCK 15). A restore can resurrect scrubbed or purged data | Phase 06 must state each block's rollback story (the data does not come back) so phase 12 can write a runbook that is honest about it. |
| **Phase 13 — performance** | BLOCK 7 adds a join on `SavedSearch.user` to four queries, which changes the plan for `IX_saved_searches_user_active` | Phase 13 must be told; phase 06 does not add an index speculatively. |
| **Phase 14 — i18n** | BLOCK 8 (and BLOCKS 9, 15) add user-visible strings. `src/backend/locale/*/LC_MESSAGES/django.po` is **shared** | **Append; never regenerate wholesale.** `ru` and `bs` `msgstr` must both be non-empty. An i18n-gate failure in BLOCK 8 is a **consequence of the fix** (`VAL-006`), not a regression. |

### 5.3 Shared-artefact reservations

| Artefact | Claimed by | Risk and rule |
|---|---|---|
| **`src/backend/apps/users/services/deletion.py`** | **Phase 06: BLOCKS 9, 10, 11, 13** (four edits, one file, strictly serial) | The most contended file in **this** phase. `withdraw_consent`, `soft_delete_user_ads`, `give_consent` and `decline_consent` all live here. One Implementor, one block at a time, and each block re-reads the previous one's diff. **Do not merge two of these into one commit** even when they look adjacent. |
| **`src/backend/config/settings/base.py`** | **Phase 06: BLOCK 4** (`LOG_MASK_KEY`, `ALLOWED_ENV_VARS`) | Concurrent with phase 02 (`CFG-*`) and phase 04 (BLOCKS 2, 7, 8, 9) — the repo's most contended settings file after `conftest.py`. Append-only; never reorder a setting another phase annotated. Re-read immediately before editing. |
| **`src/backend/config/settings/prod.py` + `secret_validation.py`** | **Phase 06: BLOCK 4** | Phase 02 raised the guard count to **eight** and owns the mechanism. BLOCK 4 must **reuse** `secret_validation.py` and must not invent a new guard shape. If phase 02's tree has changed since, re-read. |
| **`.env.example`, `.env.dev.example`, `.env.prod.example`, `.env.test.example`** | **Phase 06: BLOCK 4** (one `LOG_MASK_KEY=` line each) | Gated in **both** directions by `config/settings/tests/test_env_allowlist.py`. `.env.example` carried a UTF-8 BOM that phase 02 removes — **do not re-add it**. |
| **`src/backend/apps/users/admin.py`** | **Phase 06: BLOCK 10** (`withdraw_consent_action` only), **BLOCK 15** (`ConsentRecordAdmin.list_display` only) | **Phase 04 BLOCK 1 owns the field contract and must not be clobbered.** Phase 15 audits the permission predicate. Phase 06's two edits are in **different classes** of the same file and must both re-read `UserAdmin` before touching it. |
| **`src/backend/apps/search/services/alert_query.py`, `immediate_alerts.py`** | **Phase 06: BLOCKS 5, 7** · **Phase 03: BLOCK 9** | Named as **excluded** from each other's scope. Phase 03 owns delivery state; phase 06 owns eligibility. **If phase 06 edits them, phase 03 BLOCK 9 must re-read** — and the coordinator must sequence the two phases. |
| **`src/backend/apps/moderation/admin_actions.py`** | **Phase 06: BLOCK 16** (reason redaction) | Phase 03 owns the lock behaviour, phase 05 the ad lifecycle, phase 04 **comments only**. Phase 06 touches the `reason` argument flow only — **no behaviour change to the actions themselves.** |
| **`src/backend/apps/core/utils/scheduler.py`** (`HOURLY_COMMANDS`) | **Phase 06: BLOCK 15** (a tenth entry) | Any other phase appending an entry changes `test_scheduler_wiring.py` / `test_sweep_lock_structure.py` too. Check the list at implementation time. |
| **`src/backend/apps/core/enums.py` + `advisory_lock.py` docstring + `test_advisory_lock_ids.py`** | **Phase 06: BLOCK 15, only if a new lock id is allocated** | **Three files, one commit, coordinator told first.** 19 members today; ID 10 reserved; **`13` is taken**; the next free integer is **14**. Phase 03's plan asserts 18 and is **stale**. |
| **`consent_hard_delete`** | **Phase 03** (log field) + **Phase 06: BLOCK 13** (column scrub) | Phase 03's change is **logging** and must preserve every other log field including `len(user_ids)`, the **user count**, and the words `"cascaded"` / `"rows incl. ads/images"`. Phase 06's scrub goes **inside the same `transaction.atomic()`**, before `queryset.delete()`. **Sequenced, not parallelised.** |
| **`src/backend/apps/users/models.py` + `apps/users/migrations/`** | **Phase 04** (BLOCK 3 option A, BLOCK 4 option B), **Phase 15** (role fields), **Phase 06** (BLOCK 3 / BLOCK 6 if option A adds a manager) | Migration numbers are sequential **per app**. **Never renumber or edit an existing migration.** If another phase has landed one, the next number is theirs + 1 — **re-check, do not assume `0003_`.** |
| **`src/backend/apps/core/migrations/`** | **Phase 06: BLOCK 13** (`AlterField` + `RunPython`) · **Phase 02** claimed `core/0006_*` under its own option | `SupportTicket` lives in **`core`**, not `users`. **Check the directory immediately before generating.** |
| **`src/backend/apps/trust/migrations/`** | **Phase 06: BLOCK 17** | A `RemoveField`. Check the directory; the column is in `0001_initial`. |
| **`docs/01-spec/technical-specification.md`** | **Phase 06: BLOCKS 4, 11, 14** · Phase 04 (BLOCK 8 option (c)) | **Phase 06 holds the reservation.** Phase 04 edits only under BLOCK 8 option (c) and only after checking for a concurrent edit. **Consolidate:** BLOCK 4's mask correction, BLOCK 11's anonymization wording and BLOCK 14's retention line are one file, one phase, serialised. |
| **`docs/01-spec/spec-index.md`** | **Phase 06: BLOCK 2** (sole owner) | Phase 04 does not edit it for the DECLINE conflict. |
| **`src/backend/templates/privacy.html`** | **Phase 06: BLOCKS 2 (no — §7 is BLOCK 8), 8 (§7), 9 (§6), 15 (§6)** | **§6 has two editors (BLOCKS 9 and 15) and §7 has one (BLOCK 8).** The second §6 editor re-reads the first's text and does not reintroduce a superseded sentence. §2 and §8 are untouched by this plan. |
| **`src/backend/locale/*/LC_MESSAGES/django.po`** | **Phase 06: BLOCKS 8, 9, 15** | Shared with phase 14 and phase 03. **Append; never regenerate wholesale.** `ru` and `bs` both non-empty. |
| **`docs/02-database/db-schema.md`** | **Phase 06: BLOCKS 13, 17** | One commit each, different tables, disjoint regions. |
| **`docs/02-database/db-retention.md`** | **Phase 06: BLOCK 15** · **Phase 03: BLOCK 5** | Different rows; re-read before editing. |
| **`src/backend/conftest.py`** | **Nobody in this plan** | The most contended file in the repository. **No block in this plan may edit it.** If a block appears to need a new fixture, that is a signal the test is over-fitted. |
| **`.ai/audit/**`** | **Nobody.** Unmodifiable by mandate | Tracked deletions exist in the working tree. `git status --short .ai` must show **no new modifications** beyond the pre-existing deletions and this plan's own file. |
| **`.ai/plans/**`** | Each Planner owns its own plan file | This plan may not edit `01-…` through `05-…`. Cross-references go in **this** file. |

### 5.4 The `06-PII-103` → `04-AUT-005` handoff (and phase 15's dependency)

**Recorded here so it is not lost.** Phase 06's validator merged `06-PII-103` into
`04-AUT-005` because the root cause is identical: `UserAdmin` declares no `fields`, no
`fieldsets` and no `form`, so Django's `ModelAdmin.get_form()` auto-builds a `ModelForm`
over every editable `User` field. Phase 04's validator discovered this independently and
obtained the same field list. **One declaration, one commit, phase 04 owns it. Phase 06
must not patch `UserAdmin` again.**

**What phase 06 owes phase 04, and nobody else knows:**

1. **The consent half of the merged content.** The same `fieldsets` must additionally put
   `telegram_id`, `chat_id`, `username`, `first_name`, `last_name`, `email` in a
   **read-only identity section**, and must **remove** `is_declined`, `is_deleted` and
   `ads_auto_publish` from the form **entirely** — not merely mark them read-only — so that
   every consent-state transition is forced through the service that also writes the audit
   row (BLOCK 10) and bumps the search-cache version (BLOCK 8's area).
   **Why it matters:** a moderator flipping `is_declined` back to `False` today produces a
   public ad set with **no** `consent_given_at`, **no** `ConsentRecord` and **no**
   cache-version bump.
2. **`withdraw_consent_action` is not phase 04's.** Phase 04 §5.4: BLOCK 1 must not touch
   it, and BLOCK 6 must not change the `ConsentRecord` write. **Phase 06 BLOCK 10 is the
   only phase that may touch either**, and it does so under a recorded wire-or-remove
   decision (Q-D7).
3. **The dependency direction.** Phase 06's BLOCK 10 is **sequenced to depend on phase 04
   BLOCK 1 having landed**. Making the flags non-editable is what guarantees every
   consent-state transition goes through the auditing service. If BLOCK 1 has not landed,
   BLOCK 10 waits.

**And what phase 15 needs from this:** phase 15's `AUTHZ-003` cites `04-AUT-005` as a
**hard prerequisite**. If phase 06 re-patched `UserAdmin`, the two fixes would diverge or
one would be dropped, and phase 15's citation would resolve to the wrong commit. Phase 15
should audit the **permission predicate only** (`has_change_permission` returning
`request.user.is_staff`, where `is_staff` is the moderator role) and must cite `04-AUT-005`
rather than re-report the form surface (`VAL-002`).

### 5.5 The phase-04 `PII-105` gate — the highest-value output of this phase

`.ai/plans/04-auth-login-remediation.md` §5.4 states verbatim: *"BLOCK 6 must not ship the
decline-path logout before `PII-105` is decided. **Neither report records this
dependency.**"* Phase 04's Q8 is therefore blocked on phase 06.

**Consequences, stated plainly:**

- **BLOCK 1 is the first scheduled item in this plan** and has no prerequisites, for
  exactly this reason.
- Until BLOCK 1 publishes an answer, **phase 04's BLOCK 6 is stalled.** Silence from
  phase 06 is not neutral; it is a stall.
- The answer phase 04 needs is narrow: **is DECLINE reversible?** Under option (a) a
  declined seller regains web login, which changes what a session-revocation on the
  decline path is even protecting. Under option (b) the decline path's `logout()` is
  permanent and a "recover your account" flow would contradict it.
- The session-independent recovery path and the non-silent anonymous Accept are required
  **under either option** and are BLOCK 8's work. They do not depend on the answer, so
  BLOCK 8's scope is not at risk if the answer takes time — but BLOCK 8 **may not start
  before** BLOCK 1 publishes, because under option (a) it edits `can_login`.

### 5.6 Forward dependencies other phases should plan around

| Phase | Depends on phase 06 for | Risk if phase 06 is silent |
|---|---|---|
| **15 authorization** | `AUTHZ-003` depends on `04-AUT-005`, which `06-PII-103` merged into; `AUTHZ-005` shares the predicate semantics of `VAL-003`; phase 15 owns the per-request gate phase 06 must not duplicate | Phase 15 re-files the whole admin form under RBAC, or ships a gate that re-derives the consent predicate — two divergent copies of the same rule |
| **12 production-ops** | Retention, backup and restore interact with the erasure sweep, the ad scrub (BLOCK 11), the ticket scrub (BLOCK 13) and the record purge (BLOCK 15) | A backup/restore that resurrects a scrubbed ad body or a purged `ConsentRecord` silently undoes the erasure. Each block states that **its data does not come back**; phase 12's runbook must say so |
| **08 search-fts** | BLOCK 11's scrub and the FTS-vector consistency question | A search-index change that re-derives vectors from columns phase 06 believed scrubbed. Note the trigger is **`BEFORE INSERT OR UPDATE ... FOR EACH ROW`**, so any UPDATE re-derives (C-5) |
| **14 i18n** | BLOCK 8's copy changes are a **consequence of the fix**, not a regression (`VAL-006`) | The i18n gate failure gets triaged as a regression instead of an expected consequence |
| **05 ad-lifecycle** | `soft_delete_user_ads` routes through `Ad.transition_to`; the scrub is inside the same transaction | A lifecycle change to the DELETED transition collides with the scrub |
| **13 performance** | A queryset-level consent predicate on `SavedSearch` changes the `IX_saved_searches_user_active` plan | A filter that makes the alert queries sequential-scan |

**Data-subject access / export is a separate product question (Q-D11).** A full grep for
`dsar`, `data_export`, `subject_access`, `portability` and `def export` across
`src/backend/` returns **no implementation**. The only hit is the bare string
`"Data portability."` in `privacy.html` §8 — a bullet with no described mechanism and no
corresponding code path. **There is no export path for `06-PII-101`, `06-PII-110` or
`06-PII-116` to be consistent with, and no export work for this plan to schedule.** If
data-subject access is in scope for the product, that is a **new capability** requiring
its own scoping, a product decision on its scope, and a Researcher — not a remediation of
an existing one. Routed to the coordinator (§6.1, §6.2).

### 5.7 Audit-pipeline artefacts — recorded, routed, not actioned

Two of this phase's `VAL-` findings are defects in the **audit input**, not in the product:

- **`VAL-004`** — `.kilo/commands/audit/phases/06-audit-pii-consent.md` asserts that DECLINE
  keeps *"existing ads remain public/searchable"*, contradicting the authoritative spec.
  Correcting it stops a future run of phase 06 from re-deriving `06-PII-113` and re-filing
  a mis-rated `06-PII-105`. **BLOCK 2 may make this edit only with the coordinator's
  explicit authorisation** (§5.2, and BLOCK 2's gate). Without it, the block ships the
  `spec-index.md` edit alone and the rubric correction is recorded as an open coordinator
  deliverable.
- **`VAL-005`** — the rubric rates any raw identifier in any log as blanket CRITICAL, with
  no weighting for sink, branch or blast radius. That rule is why `06-PII-102` was
  over-rated on filed and had to be corrected. The rubric should distinguish sinks (event
  store / third party / operator log / staff UI) so the one genuinely CRITICAL item in this
  phase keeps its signal. **Routed to the coordinator; no phase-06 code change.**

Neither is a remediation item. Both are recorded here so the final report and the next
audit run can act on them centrally rather than eleven times across blocks.

---

## 6. Out of scope for this plan

Every de-scoping below is **routed**, not dropped. A de-scoped item with no destination is
a re-filed finding.

### 6.1 De-scoped by ownership (routed, not dropped)

| Item | Routed to | Why |
|---|---|---|
| **`06-PII-103`** — `UserAdmin`'s auto-built form over 22 editable fields, including `password`, `is_superuser`, `user_permissions`, `is_declined`, `is_deleted`, `ads_auto_publish` | **Phase 04, `04-AUT-005` (BLOCK 1)** | Byte-identical root cause. Phase 06's own validator merged it. **Phase 06 must not patch `UserAdmin` again.** The merged content phase 04 could not know is stated in §5.4. |
| **The `UserAdmin` permission half** — `has_change_permission` returning `request.user.is_staff`, where `is_staff` **is** the moderator role | **Phase 15** (`15-audit-authorization.md:126`, "admin protection"), tracked as `VAL-002` | The *field set* and the *root cause* are not authorization; the *permission* predicate is. |
| **`04-VAL-005` cross-reference** | **This plan**, §5.1 | Phase 06 is the finding of record for the DECLINE conflict; `04-VAL-005` is a cross-reference. Recording it in phase 04's plan file would mean editing another Planner's deliverable. |
| **`VAL-004` / `VAL-005`** — the phase-06 audit rubric contradicts the authoritative spec and over-rates log sinks | **Coordinator**, §5.7 | Audit-input defects. No phase should fix the audit handbook unilaterally. BLOCK 2 may only edit the rubric with explicit authorisation. |
| **Data-subject access / export (Q-D11)** — no DSAR path exists anywhere in `src/` | **Owner (product) + coordinator**, §5.6 | A **new capability**, not a remediation. `privacy.html`'s *"Data portability."* is a bare bullet with no mechanism. |
| **The declined-buyer half of `06-PII-104`** — messaging a browse-only *visitor* | **Struck** | Struck by the validator: `technical-specification.md:101` says nothing about suppressing Telegram messages to a browse-only visitor, and the banner copy is about cookies, not contact. **Not a de-scoping; a correction.** |
| **The banned-user half of `06-PII-104` as a *consent* breach** | **Kept as a filter, reclassified** | The validator weakened it: a ban is a moderation action, not a consent action. The filter stays; it is no longer cited as a consent breach. Whether `is_banned` belongs in the predicate is a **Q-D6** input. |
| **A global logging `Filter`** for identity arguments | **Declined** | The report's own advisory declines it: a naming-convention guard, not a type system; it cannot see `user.chat_id` passed positionally; negative ROI at this project scale (rule 5). If the invariant is ever wanted, the durable form is a typed `Identity` value object. |
| **Generalising the admin-containment guard beyond a declared set (blanket ban)** | **Declined as written** | `VAL-007`: it false-positives on `SupportContactAdmin`, whose `telegram_id` is a configured support-channel id. BLOCK 12 implements the **declared-set** form. |
| **Re-deriving the FTS vectors in the ad scrub (`VAL-009`)** | **Declined as a work item** | **Overstated** (C-5): the vectors are maintained by a `BEFORE INSERT OR UPDATE ... FOR EACH ROW` trigger, so any UPDATE re-derives them free. One assertion replaces the mechanism. |

### 6.2 De-scoped by design (deliberately not done here)

| Item | Why |
|---|---|
| **The `06-PII-108` documentation half** | Both public surfaces **already** scope "Analytics" to Plausible — the `consent_banner.html` bullet and `privacy.html` §2 + cookie table + third-party list (C-6). The naming collision survives in three internal names only (`CookieCategory.ANALYTICS`, the `consent_analytics` cookie, the `consent_analytics` context key). A doc-only change aimed at `privacy.html` §2 would be correcting text that is already correct. Renaming the internal keys is a cookie-name compatibility change and is not this finding. |
| **A general-purpose PII redactor** | BLOCK 14 may apply `redact_search_query` if the Researcher judges that use consistent with its contract; BLOCK 16 may need a narrower rule. Building a *new* general-purpose redactor is a new abstraction and would be used in exactly two places. Rule 5 applies. |
| **Nulling `chat_id` to "fix" the alert channel** | Explicitly forbidden. `AccountStateMiddleware._resolve_user` resolves users by `chat_id` precisely so withdrawn identities stay *blocked*; nulling it re-opens a different hole and breaks `test_backfill_uses_stable_chat_id`. `06-PII-110`'s remedy is to **document** the retention and **gate delivery** (BLOCKS 7 and 9). |
| **A default-manager filter on `User`** | Explicitly forbidden (`VAL-003`). It would silently change every `User.objects` query in the codebase, including the bot middleware's. |
| **Suppressing first-party `AnalyticsEvent` writes** | `technical-specification.md` §F sanctions them under legitimate interest. There is no violated gate to enforce, and inventing one would change seller-dashboard numbers and `rollup_daily_metrics`. |
| **A session-lifetime setting** | No `SESSION_COOKIE_AGE` / `SESSION_SAVE_EVERY_REQUEST` / `SESSION_EXPIRE_AT_BROWSER_CLOSE` exists in `src/backend/`, so Django's 14-day **absolute** default applies. That is `04-AUT-006` / phase 04 BLOCK 8. BLOCK 8's recovery path is session-independent *because* this is not phase 06's to fix. |
| **A per-request account-state middleware** | Phase 15's `15-AUTHZ-001`. `04-VAL-001`'s hard rule: both phases must not file the same middleware. |
| **A backfill for `SearchHistory.query_normalized` re-derivation** | The rows already written keep their old keys. The set is bounded by `_MAX_HISTORY = 50` per user and, after BLOCK 9, deleted on withdrawal. A backfill is a separate decision; BLOCK 14 records the residue in its commit body. |
| **Restoring data after a revert** | BLOCKS 11, 13 and 15 destroy data irreversibly. The rollback story is "stop it running for new operations" plus a documented statement that the destroyed data does not return — never a reverse migration that re-creates the leak. |
| **Enabling `IMMEDIATE_ALERTS_ENABLED`** | Not a remediation. The rollout gate is BLOCKS 5 **and** 7 landing; enabling the flag is an operational decision outside this plan, and a live deployment's `.env` is not in the repository. |

### 6.3 Explicitly forbidden while implementing

1. Patching `UserAdmin`'s `fields` / `fieldsets` / `form` / permission predicates.
2. Adding a default-manager filter to `User`, or a global logging `Filter`.
3. Nulling `User.chat_id` or `AdvisoryLockId.CONSENT_HARD_DELETE`.
4. Touching `AccountStateMiddleware` (bot), `can_publish_ad`, or any `Ad` transition table.
5. Renumbering or editing an existing migration in any app.
6. Editing `.ai/audit/**`, another phase's plan file, `src/backend/conftest.py`, or the
   audit rubric without coordinator authorisation.
7. `git reset` / `git checkout` / `git restore` / `git stash` / `--amend` / force-push, or
   reverting a file another agent changed.
8. Committing without an explicit instruction; committing more than one block in one
   commit; `git add -A` or `git add .`.
9. Writing a test that asserts a line number, a column count produced by introspection, a
   literal private name, or the mere presence of a symbol.
10. Building a re-derivation mechanism for the FTS vectors, or any other speculative
    abstraction the finding does not require.

---

## 7. Per-block risk register

Severity here is **this Planner's assessment of execution risk for the change**, not the
finding's severity. "Migration" covers DDL, backfill and rollback. "Irreversible" covers
operations whose data effect cannot be undone by a revert. "Lock" covers advisory-lock
allocation. "Transaction" covers `atomic()` nesting and savepoint depth. "Contention"
covers shared files.

| Block | Risk | Kind | Likelihood | Impact | Mitigation / detection | Residual |
|---|---|---|---|---|---|---|
| **All** | An implementor runs `git add -A` and commits the pre-existing `.ai/audit/**` deletions or another phase's uncommitted work, and the next block clobbers it | Process | Med | **High** | §1.3's hard staging rule; `git status --short` immediately before **every** commit; the audit tree is unmodifiable by mandate; §5.3 names the contended files. | Very low |
| **All** | A block runs with its gate unanswered, or the Implementor silently picks an option | Process | Med | **High** | Every gate is a labelled block in §3 and a row in §0.5, repeated in the task YAML's `extra_context`; §8.1 checks a written answer exists for each. | Low |
| **All** | A block's tests are **asserted** rather than **run**, or run on the host where there is no database | Process | Med | **High** | Every block names its exact Docker gate command; tests run **only** through the `test` service (§1.1). | Low |
| **All** | A red gate is captured while another phase's validator is running, and a teardown race is reported as a product defect | Process | High | Med | `VAL-010` (§1.1, §0.2.1 item 7): re-run serially before reporting. The symptom to recognise is `test_mko_bazuna does not exist` / `relation "..." does not exist`. | Low |
| **All** | A **shipped green test** that encodes a defect is "fixed" by changing production code instead | Correctness | Med | **High** | Project rule 2 is restated in §1.4. Six tests are explicitly slated for rewrite (BLOCK 4 ×1, BLOCK 5 constrained, BLOCK 8 ×2, BLOCK 10 ×3, BLOCK 12 ×3, BLOCK 15 ×2) and **each block names the test and the justification**. §8.3 checks them. | Low |
| **All** | A new user-visible string ships without non-empty `ru` **and** `bs` | i18n | Med | Med | Only BLOCKS 8, 9 and 15 add strings; each names the locale files, and §5.3 forbids a wholesale regeneration that would clobber phase 14. | Low |
| **All** | A `privacy.html` sentence is edited twice and a superseded claim survives | Documentation | Med | Med | §6 has three editors (BLOCKS 8 §7, 9 §6, 15 §6); each re-reads and each must not reintroduce a sentence the previous block retired. `test_privacy.py` does not assert the wording — **the second reader is the control.** | Low |
| **1** | The DECLINE decision is made implicitly by whoever implements first, and phase 04 acts on a guess | Process | Med | **High** | BLOCK 8 may not start before BLOCK 1's record exists; BLOCK 8's task YAML carries "decision reference required"; §5.5 states the stall. | Very low |
| **1** | The decision is published but with no stated consequence set, so phase 04 cannot act on it | Process | Low | **High** | BLOCK 1's deliverables require the option, the reasoning, the date and the BLOCK 8 scope impact. | Very low |
| **2** | `technical-specification.md` is edited by mistake (phase 04 also touches it) | Contention | Low | Med | The block's file list omits it and an acceptance criterion forbids it. | Very low |
| **2** | The audit rubric is edited without authorisation | Process | Low | Med | The block's gate requires coordinator authorisation **before**; without it the rubric is untouched and the correction is recorded as an open deliverable. | Very low |
| **3** | The registry becomes an **over-engineering** failure — a new abstraction with two consumers, in a destructive path | Design | **Med** | Med | The block is gated on Q-D9 and option **C** ("keep the list, add a guard test") is a fully argued alternative. The Validator must be able to reject an unjustified registry. | Med — accepted |
| **3** | The registry creates a `users` → `core` / `ads` / `trust` / `moderation` import direction the module boundaries do not have | Design | Med | Med | Prefer a declarative form with lazy model references; keep `deletion.py`'s existing imports unchanged. | Low |
| **3** | A registry entry is **omitted** for a new identity column — reproducing the very defect the block fixes | Correctness | Med | **High** | The guard test (or, under option C, the membership test) is the block's deliverable and must be demonstrated **red** before green. | Low |
| **3** | A naive registry clears `User.chat_id` | **Irreversible** | Low | **High** | `RETAIN` is a first-class action and a test asserts `chat_id` has a `RETAIN` entry with a non-empty reason. | Very low |
| **3** | The block runs ahead and changes `withdraw_consent`'s behaviour | Scope | Med | Med | An acceptance criterion requires `test_deletion.py` to pass **unchanged**; if it does not, the block has done BLOCK 9's work. | Very low |
| **4** | A placeholder or missing `LOG_MASK_KEY` in production is **defaulted** rather than fail-fast, so the mask is reversible with a public key | Correctness | Low | **High** | Binding constraint 4; a guard test in the same commit, following `secret_validation.py`'s `validate_bot_username` pattern. | Very low |
| **4** | `base.py` / `prod.py` / the four env templates are edited on a stale read and a phase-02 change is clobbered | Contention | **High** | Med | §1.3 staging rule; §5.3 names these as the repo's most contended files; re-read immediately before editing. | Med — accepted |
| **4** | The mask width changes and a log parser or a dashboard keyed on the old value breaks | Regression | Med | Med | Documented in the spec edit as the rotation trade-off; it is the accepted cost of the fix. | Low |
| **4** | A test written against the report's "length == 13" fails | Correctness | Med | Low | C-4 forbids chasing "13"; the rewrite asserts properties, not widths. | Very low |
| **4** | `LOG_MASK_KEY` is reused later for `query_normalized` (BLOCK 14), coupling two rotation timelines | Design | Med | Med | BLOCK 14's Q-D5 explicitly separates them: a mask rotation is cheap, a dedup-key rotation orphans every stored key and session payload at once. | Low |
| **5** | The mask is applied in `_build_payload`, so the **send** receives a masked `chat_id` and delivery breaks while the tests still look superficially green | Correctness | Med | **High** | Binding constraint 1; the existing `test_immediate_alerts.py` `kwargs["chat_id"]` assertions are the tripwire; the block's own test asserts both halves. | Very low |
| **5** | `immediate_alerts.py` is edited while phase 03 BLOCK 9 is mid-change to the same file | Contention | Med | Med | §5.3; re-read; the commit body names the file and states that only the log arguments changed. | Low |
| **6** | A **default-manager filter** is introduced as a "simplification", hiding withdrawn users from `AccountStateMiddleware` | Correctness | Med | **High** | Binding constraint 1, an acceptance criterion, and the named casualty. The bot's `_check_user_state(chat_id)` tests are the tripwire. | Very low |
| **6** | The queryset predicate drifts from `get_account_state`, producing the second-copy defect `VAL-003` describes | Correctness | Med | **High** | The cross-check test (every state, queryset vs. instance) is the block's most valuable test. | Low |
| **6** | Phase 15 forks the predicate because the Q-D6 ownership confirmation never arrives | Process | Med | **High** | BLOCK 6 is **gated** on the confirmation; the decision record names phase 15's `AUTHZ-005` as the counterpart. | Low |
| **7** | An over-narrow filter silently stops legitimate digests for eligible users | Regression | Med | Med | The positive case is asserted explicitly, not only the exclusions. | Low |
| **7** | A bulk filter changes the `IX_saved_searches_user_active` plan and the daily job slows | Performance | Low | Med | Phase 13 owns performance; phase 06 adds no speculative index. | Low |
| **7** | Collection is moved across the `ALERT_DELIVERY_TASK` lock or the transaction boundary | Concurrency | Low | **High** | Binding constraint 4; phase 03 owns the boundary. | Very low |
| **7** | `test_alert_query.py`'s selection-semantics tests are changed without the change being deliberate | Correctness | Med | Med | Binding constraint 6; the commit body must name each updated test and why. | Low |
| **8** | Option (a) ships without a security review of the surface a declined user regains | Security | Med | **High** | All four agents are required **under either option**; the Validator must enumerate the newly reachable views. | Low |
| **8** | The recovery mechanism accepts a bare `chat_id` as identity | Security | Low | **High** | Binding: `chat_id` is public to anyone who has ever messaged the bot. The Researcher's threat model is a required deliverable. | Very low |
| **8** | The recovery mechanism introduces a new stored token and the "rollback" is written as a plain revert, leaving the token table behind | Data | Med | Med | The block's rollback section requires the residue to be stated rather than folded into a revert. | Low |
| **8** | The i18n gate fails on `ru` / `bs` and it is triaged as a regression | i18n | **High** | Low | `VAL-006`: it is a consequence of the fix. Sequence `.po` updates in the same commit. | Very low |
| **8** | `SESSION_COOKIE_AGE` is set to "fix" the session dependency | Design | Low | Med | Binding constraint 4: that is `04-AUT-006`. The recovery path must be session-independent instead. | Very low |
| **9** | Deleting `SearchHistory` rows conflicts with a legitimate-interest argument | Product | Low | Med | The spec sanctions first-party `AnalyticsEvent` rows, but `SearchHistory` is the user's own typed queries; the reasoning is stated in the commit body. | Very low |
| **9** | A bulk `.update()` on `SavedSearch` bypasses `updated_at` maintenance the daily cap may depend on | Correctness | Med | Med | The Researcher states the intended semantics at Q-D10 time; binding constraint 4. | Low |
| **9** | The rewritten `privacy.html` §6 still over-promises because BLOCK 13 and BLOCK 15 have not run | Documentation | **High** | Med | The block must say so in the commit body rather than ship a promise the code does not keep. §5.3's "second editor re-reads" rule. | Med — accepted |
| **10** | Moving the audit write into the service changes when it runs relative to `logout()` and collides with phase 03 `DB-004` / phase 04 BLOCK 6 | Transaction | Med | **High** | Binding constraint 2; the new order is stated in the commit body; both phases must be told. | Low |
| **10** | Phase 04's BLOCK 1 has not landed, so the admin form still allows bypassing the auditing service | Process | Med | **High** | The external gate is explicit: BLOCK 10 **waits**. This is not ceremonial — see §5.4. | Very low |
| **10** | `withdraw_consent_action` is wired as a capability expansion rather than a fix | Scope | Med | Med | Q-D7 is a recorded decision, and a superuser gate plus an audit-row assertion are required if it is wired. | Low |
| **10** | The revert is expected to remove the extra `ConsentRecord` rows and is wrongly "completed" by deleting them | Data | Low | Med | The rollback section states that an append-only ledger keeps what it recorded. | Very low |
| **11** | Option (a) destroys seller content and the block ships without the recorded decision | **Irreversible** | Low | **High** | Q-D3 is a hard gate; the block may not start unanswered. | Very low |
| **11** | The scrub is a bulk `.update()`, so the `post_save` search-cache bump does not fire | Correctness | Med | Med | Binding constraint 3; the Researcher must state which write shape is used. | Low |
| **11** | A re-derivation mechanism is built for the FTS vectors "to be safe" | Design | Med | Med | `VAL-009` is overstated (C-5); binding constraint 2; one assertion replaces the mechanism. | Very low |
| **11** | An already-scrubbed ad is believed recoverable by a revert | **Irreversible** | Med | Med | The rollback section requires this to be stated **before** the block runs, not after. | Low |
| **12** | The guard is "simplified" into a blanket ban and red-flags `SupportContactAdmin` | Correctness | Med | Med | The trap is named in the module docstring, in an acceptance criterion and in the commit body; the negative-case test exists to stop it. | Low |
| **12** | Dropping `telegram_id` from `search_fields` removes support's only lookup with no replacement | Product | Med | Med | Binding constraint 3: the field stays; the Researcher must answer whether searching by raw `telegram_id` is itself an exposure. | Low |
| **12** | The masking helpers are written `None`-intolerant, and BLOCK 13 must rewrite them | Correctness | Med | Low | Binding constraint 4, plus a `None`-tolerance test. The BLOCK 12 → 13 edge is a *shape* dependency for exactly this. | Very low |
| **12** | `test_support_admin.py` is updated without the change being deliberate | Correctness | Med | Med | Binding constraint: the three updated tests must say in their docstring why the configuration changed; every `SupportContactAdmin` test stays unchanged. | Low |
| **13** | The migration is generated with a number another phase has taken | Migration | **Med** | Med | `core` vs `users` vs `trust` are different apps; check the directory immediately before generating; never renumber (phase 02 claimed `core/0006_*`). | Low |
| **13** | The scrub is placed **outside** the sweep's `transaction.atomic()`, so a crash between the scrub and `delete()` leaves a half-erased state | Transaction | Med | **High** | Binding constraint 2; `test_sweep_consent.py`'s existing crash-rollback test is the tripwire — **if it has to be modified to pass, the block is wrong.** | Very low |
| **13** | The data migration's `reverse` restores the identifiers, re-creating the leak during a rollback | **Irreversible** | Low | **High** | Binding constraint: the reverse is a deliberate `noop` with a comment. | Very low |
| **13** | The data migration misses the **already-orphaned** population | Correctness | Med | **High** | A test creates an orphaned row with full identifiers and runs the migration twice. | Very low |
| **13** | Phase 03's `consent_hard_delete` logging change lands concurrently with this block's scrub | Contention | Med | **High** | **Sequenced, not parallel** (§5.3). Re-read the command; the user count, `len(user_ids)` and the words `"cascaded"` / `"rows incl. ads/images"` must survive. | Low |
| **13** | Q-D2 is never answered and the block is implemented "provisionally" | Process | Med | **High** | The block is gated; the acceptance criteria require the decision in the commit body. | Very low |
| **14** | A keyed digest is used for the dedup key, so a `LOG_MASK_KEY` rotation orphans every stored key and every session payload | Design | Med | Med | Q-D5 must address rotation explicitly; the two secrets' rotation timelines are explicitly **not** shared. | Low |
| **14** | A dedup regression silently changes "recent searches" for sellers | Regression | Med | Med | The dedup test asserts both the merge and the non-merge cases. | Low |
| **14** | Only the table is fixed and the anonymous **session** store keeps the raw key | Correctness | Med | **High** | Binding constraint 1, and the session half is an explicit required test. | Low |
| **15** | A lock id is allocated that another phase is about to allocate | Lock | Med | Med | Coordinator told **before**; the three files change in **one** commit; the numbers are re-read at implementation time because **13 was taken mid-pass** (C-3). | Low |
| **15** | The sweep is shipped on an **invented** TTL and destroys Art. 7(1) evidence | **Irreversible** | Low | **High** | Q-D4 is a hard gate; `--dry-run` is mandatory; the in-TTL survival test is the control. | Very low |
| **15** | A tenth `HOURLY_COMMANDS` entry breaks the scheduler's `_validate_commands` or the daily marker's `0` contract | Correctness | Med | Med | Binding constraints 3 and 4; the scheduler-start test and the unchanged daily-marker assertion. | Low |
| **15** | A second `privacy.html` §6 editor reintroduces a superseded retention sentence | Documentation | Med | Med | §5.3's "second editor re-reads" rule; the block must not touch BLOCK 9's text beyond the retention period. | Low |
| **16** | `redact_search_query`'s 100-char truncation **silently discards** most of a moderator's reason | Correctness | **High** | Med | The decision must resolve the truncation explicitly; the "operator text is preserved" test makes the loss visible. | Med — accepted |
| **16** | The fixed literals are mangled, and moderation history becomes unreadable | Regression | Med | Med | A dedicated regression test asserts every literal reason is stored byte-identical. | Low |
| **16** | `admin_actions.py` is edited while phases 03 / 04 / 05 hold it | Contention | Med | Med | §5.3; phase 06 touches the `reason` flow only, with no behaviour change to the actions. | Low |
| **17** | A writer for `phone_number` appeared since the report, and the column is removed with a live data path | Data | Low | **High** | Binding constraint 1: re-verify the zero-writer claim **immediately** before the change and stop and report if it fails. | Very low |
| **17** | A deployment holds rows in the column, and the `RemoveField` drops data | **Irreversible** | Low | Med | The validator's probe found 0 rows; if a deployment check shows rows, stop and escalate rather than dropping them. | Very low |

---

## 8. Definition of done for the whole plan

Phase 06 is complete when **all** of the following hold.

### 8.1 Scope

- [ ] All 16 filed findings have a recorded disposition: **14 implemented** (`06-PII-101`,
      `102`, `104`, `105`, `106`, `107`, `108`, `109`, `110`, `111`, `112`, `113`, `114`,
      `116` — noting `105` and `110` are each split across a decision block and an
      implementation block, and `110`'s `ConsentRecord` half is absorbed by `116`),
      **1 merged away** (`06-PII-103` → `04-AUT-005`), **1 rejected**
      (`06-PII-115`, restated so it is not silently re-filed).
- [ ] Both non-finding work items shipped: the **published DECLINE-reversibility decision**
      (BLOCK 1) and the **PII erasure inventory** (BLOCK 3).
- [ ] Every gated block (**1, 3, 4, 6, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17**) has a
      **written** decision for its open question, naming the option chosen and the
      consequences accepted. **Silence is not an acceptable outcome for any of them.**
- [ ] Each of Q-D1 … Q-D10 and Q-D12 is either answered with a record or explicitly
      re-routed with a named destination. Q-D11 and Q-D13 are recorded as routed, not
      planned.
- [ ] The `06-PII-103` → `04-AUT-005` handoff (§5.4) was communicated to the coordinator
      with the merged content phase 04 could not know — **not** silently dropped.
- [ ] Every de-scoping in §6 has a named destination.

### 8.2 Gates — all green

- [ ] `uv run ruff check src/` → exit 0.
- [ ] `uv run basedpyright src/` → **0 errors**.
- [ ] `.\Makefile.ps1 test` → full suite green (seed marker skipped).
- [ ] `.\Makefile.ps1 test-recreate` executed at least **once after BLOCK 13's migration**
      and **once after BLOCK 17's migration**.
- [ ] `uv run basedpyright` / `ruff` re-run after every block, not only at the end.
- [ ] `apps/ads/tests/test_i18n_completeness.py` green after BLOCKS 8, 9 and 15.
- [ ] `config/settings/tests/test_env_allowlist.py` green after BLOCK 4 — **in both
      directions**.
- [ ] `makemigrations --check` clean after BLOCKS 13 and 17.
- [ ] Every block's exact gate command from §3 was run and green, **not** the full suite
      alone.
- [ ] `git status --short .ai` shows **no new modifications** beyond the pre-existing
      `.ai/audit/**` deletions and this plan's own file.
- [ ] Every red-gate observation was **re-run serially** before being reported as a defect
      (`VAL-010`).
- [ ] No commit was made without an explicit user request; no `git reset`, `git checkout`,
      `git restore` or `git stash` was run at any point.

### 8.3 Per-finding behavioural confirmation

- [ ] **`06-PII-101`** — after `withdraw_consent(seller)`, no ticket of that seller retains a
      raw `chat_id`, `telegram_id` or `username`; a different seller's ticket is untouched.
      After `consent_hard_delete` past the grace window, the ticket is scrubbed and the user
      is gone. A pre-existing **orphaned** row is scrubbed by the data migration, and
      running it twice is a no-op. `ticket_ref` is intact and its retention is documented.
      **No assertion that the row is unfindable** — that wording is corrected (C-7).
- [ ] **`06-PII-102`** — neither failure branch's formatted message contains the raw
      `chat_id`, **and** a captured `send_message` still receives the real integer. The
      payload keeps the real `chat_id`. `_build_payload` is unchanged.
- [ ] **`06-PII-104`** — a `SavedSearch` owned by a withdrawn / declined / banned / deleted
      user appears in **none** of `send_alerts._collect_alerts`,
      `send_alerts._dry_run_check`, `find_matching_saved_searches` or `find_matching_ads`;
      an ad owned by a declined seller matches no saved search; an eligible user still
      receives the digest; all four sites reference **one** declaration; the queryset
      predicate agrees with `get_account_state` for every state; no default-manager filter
      was added.
- [ ] **`06-PII-105`** — a logged-out declined user can reverse the decline and is told
      what happened; no path sets an `accepted` cookie while leaving the row unchanged
      without an explanation; the affordance is reachable without `?ref=preferences`; an
      explicit `ConsentRecord` is written for the new transition; `ru` and `bs` are
      non-empty. The BLOCK 1 decision is cited in the commit body and in the spec.
- [ ] **`06-PII-106`** — no raw identity column of a data-subject model appears in a
      `list_display` without a masking helper; `SupportContactAdmin` does **not** trip the
      guard; `text` is no longer a search target; the helpers are `None`-tolerant.
- [ ] **`06-PII-107`** — a withdrawal through the **service** (no view, no request) writes a
      `choice='WITHDRAWN'` `ConsentRecord`; the audit row and the state change commit or
      roll back together; `ConsentRecord` remains append-only; `withdraw_consent_action` is
      removed or superuser-gated and wired; `UserAdmin`'s field contract is untouched.
- [ ] **`06-PII-108`** — a search containing a phone number, an e-mail address and a
      personal name produces a `SearchHistory` row in which none of them survives in **any**
      column, **and** the anonymous session store carries the same guarantee; the
      never-lengthen invariant holds; deduplication behaves as the recorded decision states.
- [ ] **`06-PII-109`** — the recorded Q-D3 option is implemented and named in the commit
      body; one assertion proves `search_vector_ru` follows a title update through the
      trigger; **no** re-derivation mechanism exists; the status transition and the scrub
      commit or roll back together; `Ad.transition_to` is unchanged.
- [ ] **`06-PII-110`** — after withdrawal there is no active `SavedSearch` and no
      `SearchHistory` row; `preferred_city` is null on the row after a decline and after a
      withdrawal; **`chat_id` is unchanged** and carries a `RETAIN` entry with a reason;
      `privacy.html` §6 names the retained data and why.
- [ ] **`06-PII-111`** — the zero-writer claim was re-verified immediately before the
      change; `makemigrations --check` is clean; `verified_by_admin`, `verified_at`, the
      `User` one-to-one and the trust badge are unchanged; no data migration was written.
- [ ] **`06-PII-112`** — the mask is not reproducible without the key even for a small
      candidate sweep; the `tg_` prefix is preserved and the same input gives the same
      output; the docstring and the spec line describe the **actual** construction;
      `test_env_allowlist.py` passes both ways; `test_admin_pii_containment.py` passes
      **unchanged**; the test asserts **properties, not a width**.
- [ ] **`06-PII-113`** — no current source states that DECLINE leaves existing ads
      public/searchable; the reversibility answer appears verbatim in `spec-index.md`;
      `technical-specification.md` §F/§K is **byte-identical** to before; the audit rubric
      is unmodified unless coordinator authorisation is recorded in the commit body.
- [ ] **`06-PII-114`** — a `reason` containing a phone number, an e-mail address or a
      handle stores none of them; every fixed literal is stored byte-identical; redaction
      happens **before** the write; `on_delete` and the permission predicates are
      unchanged.
- [ ] **`06-PII-116`** — `--dry-run` deletes nothing; a row **inside** the TTL survives with
      its `session_key` intact; a row past it is deleted or nulled per the decision; the
      sweep is idempotent; the scheduler still starts; the daily marker is unchanged;
      `session_key` is absent from `list_display` and present in `search_fields`;
      `privacy.html` §6 states **one** retention period.

### 8.4 Cross-phase integrity

- [ ] `UserAdmin`'s field contract was **not** touched by any phase-06 block; `04-AUT-005`
      remains the single owner (§5.4).
- [ ] `AccountStateMiddleware` (bot) is unchanged; `test_backfill_uses_stable_chat_id` and
      the `_check_user_state(chat_id)` bot tests pass **unchanged**.
- [ ] `User.chat_id` is **not** nulled anywhere, and no default-manager filter was added.
- [ ] `AdvisoryLockId.CONSENT_HARD_DELETE == 3` was not renumbered; the enum gained a new
      member **only** if a lock decision required one, in which case `enums.py`,
      `advisory_lock.py`'s docstring and `test_advisory_lock_ids.py` changed in **one**
      commit and the coordinator was notified **before**.
- [ ] Phase 03's delivery-state contract in `alert_query.py` / `immediate_alerts.py` was not
      changed; only recipient **eligibility** was (§5.1).
- [ ] Phase 03's `consent_hard_delete` **log fields** are intact: the user count,
      `len(user_ids)`, and the words `"cascaded"` / `"rows incl. ads/images"`.
- [ ] `Ad.transition_to` / `ALLOWED_TRANSITIONS` are unchanged; the FTS trigger and
      `setup_search_triggers` are unchanged.
- [ ] Phase 05's `copy_ad` storage-key reuse and `delete_adimage_files_on_delete` are
      unchanged; phase 03's `test_bulk_ban_users_not_locked` passes.
- [ ] `src/backend/conftest.py` is **unmodified**.
- [ ] Migration numbers were checked against their directories **immediately before**
      generation; no existing migration was renumbered or edited.
- [ ] `docs/01-spec/technical-specification.md` was edited by phase 06 only, in BLOCKS 4,
      11 and 14, serially; `spec-index.md` only in BLOCK 2.
- [ ] `docs/02-database/db-schema.md` and `db-retention.md` match the shipped schema and
      the shipped retention periods.
- [ ] Locale files were **appended** to, never regenerated wholesale; `ru` and `bs` are
      non-empty for every new or changed string.
- [ ] The audit tree shows no new modifications; no other phase's plan file was edited.
- [ ] `06-PII-115` is restated in the final report so it is not silently re-filed.
- [ ] `IMMEDIATE_ALERTS_ENABLED` was **not** enabled anywhere as part of this plan, and the
      rollout gate (BLOCKS 5 **and** 7) is recorded as satisfied or still open.

### 8.5 Project conventions

- [ ] Every new constant is a named module-level constant or a `StrEnum` / `IntEnum`
      member, never an inline literal or a dict-of-strings (project rule 10).
- [ ] No `print()`; `logger = logging.getLogger(__name__)` with lazy `%s` formatting.
- [ ] All comments, docstrings, log messages, error messages and docs are in **English**.
- [ ] Pydantic v2 appears only at a system boundary; none was added to a view or a service
      path.
- [ ] Every schema change is a Django migration and is mirrored in
      `docs/02-database/db-schema.md`.
- [ ] Business logic lives in `services/`; no new logic was added to a view or a handler
      beyond the thin boundary change its block requires.
- [ ] Every non-trivial behaviour change has a test that verifies **logic and component
      interaction** — not a variable's absence, not a log string, not a line count, not an
      introspected field count. (This is why BLOCKS 1, 2 and 17 add **no** behavioural
      tests.)
- [ ] Filesystem side effects happen only **after** commit, via `transaction.on_commit()`.
- [ ] No task target is a line number; every target is a file plus a semantic symbol.
- [ ] `uv run ruff check --fix src/` was run if imports were reordered (`ruff format` is
      **not** the project convention).
- [ ] New test code is bandit-clean (list-form `subprocess.run([sys.executable, ...])`, no
      literal `/tmp`) so a future `VAL-006` fix does not redden the `security` job.
- [ ] Every new finding citation is cycle-scoped `06-PII-1xx`; no bare `PII-1xx` was
      written into a comment, a docstring or a commit message.

### 8.6 Deliverables

- [ ] The BLOCK 1 decision record is published and its phase-04 cross-reference was
      communicated to the coordinator — **not** silently decided.
- [ ] The `06-PII-103` → `04-AUT-005` handoff (§5.4) was communicated, including the
      `is_declined` / `is_deleted` / `ads_auto_publish` **removal** requirement.
- [ ] Q-D11 (data-subject access / export) and Q-D13 (the audit-rubric correction) are
      recorded as **routed to the coordinator**, with the evidence that no export path
      exists anywhere in `src/`.
- [ ] Every irreversible block's commit body states that the destroyed data does not
      return on a revert.
- [ ] This plan file is updated to mark each block's completion, so the phase coordinator
      has a single status surface.
- [ ] No commit was made without an explicit user request.
