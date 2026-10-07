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
| **Q-D4** | **`06-PII-116`: the `ConsentRecord` TTL number, and the sweep's lock** — reuse an existing id with a written rationale, or allocate a new one (now `14`+) | **BLOCK 15** (fingerprint + decision windows) · **BLOCK 19** (`06-NEW-02`, the actor window) | TTL: **owner/product, on purpose-based grounds — NOT legal**. Lock: Planner + **coordinator** (three-file one-commit change) | **RESOLVED, then RE-GROUNDED 2026-10-04 — read §*Retention framing correction (owner ruling 2026-10-04)* before treating any number here as settled.** Lock `14` was ratified 2026-10-03. The TTLs are **owner-ratified project decisions**, not legal requirements. **R1 is RE-GROUNDED 2026-10-04 and its limitation-period justification is WITHDRAWN**; **R3 is unchanged and still out of scope**, and BLOCK 19 adds a third window |
| **Q-D5** | **`06-PII-108`: redact `query_normalized`, or store a keyed digest?** The anonymous **session** store (`_record_session_history`) has the same raw/redacted split and needs the same treatment | **BLOCK 14** | Researcher + Planner | **RESOLVED 2026-10-01 — redact-for-the-key, all three stores.** `search_query_key()` = redact-**then**-lower. See §0.6 |
| **Q-D6** | **`VAL-003`: who owns the queryset-level account-state predicate, and what is its exact shape?** Phase 15 owns the framework; phase 06 owns the semantics. A **default-manager filter is forbidden** | **BLOCK 6** | Researcher + Planner, **confirmed with the coordinator** so phase 15 does not fork it | **RESOLVED 2026-10-02 (Researcher) — Option B: one module-level `account_state_q(prefix: str = "") -> Q` in `apps/users/services/account_state.py`, five conjuncts, consumed from a `User` qs (`prefix=""`) and from `SavedSearch`/`Ad` via the owner (`prefix="user__"`). No manager, no `get_queryset()` override, no `models.py` edit. Default-manager filter prohibition restated with its fail-open mechanism. Import-cycle verified absent by static closure + a live injected-edge probe; the latent `apps/search/services/__init__.py` back-edge is frozen + test-pinned. **Still the coordinator's to ratify**; BLOCK 6 does not start until it is. See BLOCK 6 |
| **Q-D7** | **`06-PII-107`: wire or remove `UserAdmin.withdraw_consent_action`**, and what is the shape of the consent context object | **BLOCK 10** | Planner (wire-or-remove) + Researcher (context shape) | **RESOLVED 2026-10-01 — WIRE**, `permissions=["delete"]`, per-user `atomic()`, explicit kwargs (no context object). The phase-04 dependency is **discharged**. See §0.6 |
| **Q-D8** | **`06-PII-112`: `LOG_MASK_KEY` provenance (same source as `SECRET_KEY` or independent?), required-in-production or defaulted, and the rotation policy** | **BLOCK 4** | Owner (security) + Planner; Researcher on the `prod.py` guard shape | **RECOMMENDED 2026-10-02 — (ii) independent secret · (ii) required in production, fail-fast · rotate on compromise only, never on a schedule.** Researcher's evidence and full consequences are in BLOCK 4's *Decision recommendation*. **Still the owner's to ratify**; BLOCK 4 does not start until it is |
| **Q-D9** | **Required Fix 1: what is the PII inventory's exact shape** — a `StrEnum`/`dataclass` registry, model annotations, or keep the hand-maintained list plus a guard test | **BLOCK 3** | Researcher + Planner | **RESOLVED 2026-10-01 — Option C**: a declarative `StrEnum` + declared-list module with a guard test, lazy string model labels, and a documented promotion path to a registry. See §0.6 |
| **Q-D10** | **`06-PII-110`: does nulling `preferred_city` on DECLINE survive `_reconcile_preferred_city_on_login`?** | **BLOCK 9** | Researcher + Planner | **RESOLVED 2026-10-01 — NO, it does not, and the plan's premise is inverted.** Durability needs **four** coordinated changes; `preferred_city.py` joins BLOCK 9's surface. See §0.6 |
| **Q-D11** | **Is data-subject access in scope at all?** No export/DSAR path exists anywhere in `src/`; `privacy.html`'s *"Data portability."* is a bare bullet | — (no block) | **Owner (product) + coordinator** | **ROUTED, not planned.** Export is a **new capability**, not a remediation. See §5.6 and §6.1 |
| **Q-D12** | **`VAL-007`: the exact shape of the "declared set of data-subject identity columns"** — a blanket registry walk false-positives on `SupportContactAdmin` | **BLOCK 12** | Researcher + Planner | **RESOLVED 2026-10-01 — Option D**, the existing helper-enumeration precedent: two new entries in `test_admin_pii_containment.py`, no registry and no walk. See §0.6 |
| **Q-D13** | **`VAL-004` / `VAL-005`: correcting the phase-06 audit rubric** (it contradicts the authoritative spec and over-rates log sinks) | — (no block) | **Coordinator** | **ROUTED.** The audit-input tree is not phase 06's to edit. See §5.7 and §6.1 |

---

### 0.6 Gate resolutions — 2026-10-01 (Auditor → Researcher pass)

**Scope of this pass.** The Auditor re-verified the tree and overturned 18 of this plan's
statements, several of them load-bearing. The Researcher then closed the five gates that
are genuinely agent-resolvable (Q-D5, Q-D7, Q-D9, Q-D10, Q-D12).

**Still open and NOT closed by this pass:** Q-D1 (DECLINE reversibility), Q-D2 (ticket
identity), Q-D3 (ad-text scrub), Q-D4 (ConsentRecord TTL), Q-D8 (`LOG_MASK_KEY`
provenance), Q-D6 (predicate ownership — needs coordinator confirmation so phase 15 does
not fork it), Q-D11, Q-D13. Those are product/legal/owner decisions and no agent may
answer them.

**Two dependencies changed state.** BLOCK 10's phase-04 dependency is **discharged**
(`a19a0ee` landed the `UserAdmin` field contract). And §0.3's obligation to phase 04 —
remove `is_declined` / `is_deleted` / `ads_auto_publish` from the change form — is
**already satisfied** as *read-only*, which is functionally equivalent for the write
path, and is now test-pinned.

#### 0.6.1 Resolved decisions

| Gate | Decision | Why the alternatives lost |
|---|---|---|
| **Q-D5** | **Redact-for-the-key, one mechanism, all three stores.** New `search_query_key()` in `apps/core/utils/sanitize.py`: `redact_search_query(query).strip().lower()` — **redact first, then lower**, on the raw query. Applies to the `search_history` table, the `popular_searches` table and the session store, plus `SeedService._seed_popular_searches`. | **The plan's own option (a) is wrong as written.** `redact_search_query` is applied to the *normalised* (lowercased) string, where `_NAME_PATTERN` (`\b[А-ЯЁA-Z]`) matches nothing — so **personal names, the largest of the three classes, survive verbatim in the key**. The derivation order must be inverted. A keyed digest is **structurally incompatible** with `PopularSearch`, whose key is read with `__startswith` (`get_popular_suggestions`): a digest has no prefix structure, so popular autocomplete would return zero rows for every query. Splitting mechanisms per store means two derivations, one needing a secret with a rotation story, for zero privacy gain — and the prefix read makes redact-as-key the only coherent option. **This retires the plan's key-rotation risk outright: no secret, nothing to rotate.** |
| **Q-D7** | **WIRE** the action (do not remove it), with `actions = ["withdraw_consent_action"]` and `@admin.action(permissions=["delete"])`. Keep the service's per-user `atomic()`. Move the `ConsentRecord` write inside `withdraw_consent`'s existing atomic block via a new public `record_consent_action_with_context(...)`; `record_consent_action(request=…)` keeps its signature and delegates. No context object. Fix the over-reporting message. | **Wiring is stronger than removing.** With `is_declined`/`is_deleted`/`ads_auto_publish` now non-writable and `preferred_city` the only writable change-form field, the action becomes the **only** staff-side consent mutation — and BLOCK 8 wants an operator-recoverable path. `permissions=["delete"]` is **strictly stronger** than an in-body `is_superuser` check: Django dispatches it to `getattr(self, "has_%s_permission" % permission)`, i.e. `UserAdmin.has_delete_permission` (already superuser-only), which **removes the action from `get_actions()`** for an `is_staff` moderator — so it is absent from the dropdown *and* Django's own action-form validation refuses a forged POST. `@admin.action` without `permissions=` leaves `allowed_permissions` unset, so `_filter_actions_by_permissions` would append it **unconditionally**. Rejected: an outer `atomic()` (moves the transaction boundary into the admin layer — the layering this block exists to undo — and defers every `AdImage` `on_commit` FS callback to the end of a long transaction); a frozen dataclass (three optional scalars with no invariant to protect, no second construction site); passing `HttpRequest` into `deletion.py` (rule 3). |
| **Q-D9** | **Option C** — a declarative module `apps/users/services/pii_inventory.py` holding `ErasureAction(StrEnum)` (`CLEAR` / `NULL` / `DELETE_ROW` / `RETAIN`) plus a declared list of `(model_label: str, column: str, action, reason: str)`, with a guard test. **Lazy string model labels**, so the module imports no `apps.*` model and creates no `users → core.models` edge. | A registry has **zero consumers today** (BLOCK 11 and BLOCK 13 are product-gated), so it would ship an abstraction with no reader — rule 5 forbids that, and this plan's own acceptance criterion for BLOCK 3 is "no production behaviour changed". The registry also either drags in the new `users → core`/`ads`/`trust`/`moderation` import edges it claims to avoid, or degrades to untyped strings only a data migration could check. `Meta` metadata is a category error (schema metadata carrying erasure policy, spread across five apps). |
| **Q-D10** | **The nulling does not survive, and the plan's premise is inverted.** Durability needs **four** changes: (i) `_set_consent_cookies` must delete the `preferred_city` cookie whenever the choice is `DECLINED`, not only when `preferences` is falsy; (ii) **`apps/search/views/preferred_city.py` joins BLOCK 9's surface** — `set_preferred_city` gates the DB write on `is_declined`; (iii) the reconcile gains `if user.is_declined: return` **in `views/consent.py`, not in BLOCK 8's `login_status`**; (iv) the cookie deletion must use the hand-rolled `secure=True` expiry, not the plain `delete_cookie()`. `decline_consent` adds `preferred_city` to its existing `update_fields` — no new transaction. | The plan asserts the cookie is deleted on decline "so the nulling should hold". **It is not.** `consent_decline` computes `preferences = submission.preferences if submission and "preferences" in request.POST else True` — **the default is `True`** — and `_set_consent_cookies` deletes only `if not preferences`. So the *common* decline keeps the cookie for a year with `consent_preferences == "true"`, and the next login-claim restores the column. Independently, `set_preferred_city` writes the DB column **unconditionally** for authenticated users (gating only the cookie), so a declined user clicking a city in the header re-sets it with no reconcile involved. Third, `delete_cookie()` on `preferred_city` **cannot clear a `Secure` cookie over HTTPS** — Django 5.2 emits `Secure` only for `__Host-`/`__Secure-`/`samesite="none"` names, a defect the repo already documents and works around in `set_preferred_city`. |
| **Q-D12** | **Option D — extend the existing helper-enumeration precedent.** Add exactly two entries to `apps/users/tests/test_admin_pii_containment.py` (`SupportTicketAdmin.chat_id_display`, `.telegram_id_display`), asserting on the *rendering statement* — delegates to `mask_telegram_id`, references `obj.<col>` — exactly like the module's four current tests. | `test_admin_pii_containment.py` is **already the right shape**: it asserts `"str(obj.user.telegram_id)" not in source` rather than banning the token, *because docstrings legitimately name `telegram_id`*, and it already covers all four cross-model helpers. Option D has **no walk, therefore no `SupportContactAdmin` false-positive to defend against** — the trap the plan spends a paragraph engineering around does not exist. A declared set buys nothing D lacks and carries the same forgot-to-add-it residual; an exempt list (B) is deny-by-default friction for every future admin, to fix a false positive it invents; option C is D minus the four existing helpers, i.e. a coverage regression. **Cross-model rendering is owned by helper enumeration by construction** — `AdAdmin.user_link`, `AnalyticsEventAdmin.user_link` and `moderation.admin.log_user_link` all render `str(obj.user)`, another model's column, so **no per-model column set can ever reach them**. |

#### 0.6.2 What the guards can and cannot detect (state this, do not paper over it)

The Q-D9 guard is a **tripwire on known columns, not a classifier**. No column-name
heuristic is sound: `User.source`, `User.last_login`, `User.date_joined` and
`SupportContact.telegram_id` all *look* like identity and are not data-subject identity;
conversely `Ad.title`, `Ad.description`, `ModeratorActionLog.reason`,
`SupportTicket.text` and `SavedSearch.query` are data-subject free text that no name
heuristic can ever find. Free text is therefore handled by **declaration**, not detection —
each gets an explicit `RETAIN` entry whose reason names its owning block, so "deferred"
is visible and each becomes a one-line edit when its block lands.

Q-D12's helper enumeration has the mirror-image residual: it cannot catch a future admin
that renders a raw identity column **without** a helper. It enumerates masking helpers; it
does not classify models. That is the limitation `test_admin_pii_containment.py` already
documents for PII-001 and it belongs in the module docstring.

#### 0.6.3 Corrections to this plan's prose (tree wins)

| # | Correction |
|---|---|
| 1 | **BLOCK 10's phase-04 dependency is discharged.** `UserAdmin`'s field contract landed (`a19a0ee`); `is_declined` / `is_deleted` / `ads_auto_publish` are `readonly_fields` and pinned non-writable. §0.3's obligation to phase 04 is satisfied as *read-only*. `preferred_city` is now the **one** writable change-form field, pinned by `::test_change_form_keeps_preferred_city_writable` — any future proposal to make it read-only is test-blocked. |
| 2 | §0.2.1 item 4 ("re-derive the field list; do not hard-code 22") is **moot** — the list is declared. |
| 3 | **BLOCK 14's file surface omits two writers.** Add `apps/search/services/popular_search.py` (the **global cross-user** table) and `apps/seed/services/seed_service.py::SeedService._seed_popular_searches`. |
| 4 | **BLOCK 14's Q-D5 option (a) is wrong as written** — `redact_search_query(normalized)` applies the redactor to the lowercased string, where the name pattern matches nothing, so names survive verbatim. |
| 5 | **BLOCK 14's test claims are inverted.** `test_redact_search_query.py` **cannot** pass unchanged (4 assertions in 4 tests pin the raw key). `test_autocomplete.py` needs **no** edit under redact-as-key — its ~12 sites use benign values for which the derivation is the identity; they break only under a *digest*, which is an argument against the digest. |
| 6 | BLOCK 14 has no `SavedSearch.query` out-of-scope line (it is the FTS query string and **cannot** be redacted) and no `__startswith` compatibility analysis. Its "key backfill is a separate decision" text is wrong: the raw text exists nowhere else, so backfilling is **destruction**, and rewriting global `PopularSearch` keys would zero every accumulated `hit_count`. |
| 7 | **`Ad` has no `rejected_reason` column.** The free text lives in `ModeratorActionLog.reason`, rendered by `ads.admin.rejected_reason`. BLOCK 16's premise needs restating, and any inventory entry naming `Ad.rejected_reason` is a defect. |
| 8 | `SupportTicket` / `SupportContact` live in **`apps/core/models.py`**; `src/backend/apps/support/` does not exist. |
| 9 | **BLOCK 9's Q-D10 premise is inverted** and there are three independent defects, not one (see the table). Add `preferred_city.py` to the surface; keep the reconcile guard in `views/consent.py`. |
| 10 | **BLOCK 12's Q-D12 is understated and misses option D.** `SupportContactAdmin.telegram_id` / `.email` are field-name identical to `SupportTicket`'s data-subject columns, so options A/B/C all inherit the trap; D eliminates it by having no walk. |
| 11 | BLOCK 12 must scope out `ConsentRecord.session_key` (in **both** `list_display` and `search_fields`) as **BLOCK 15's**, and leave `telegram_id` in `SupportTicketAdmin.search_fields` (BLOCK 13 makes the columns nullable first; `UserAdmin` and `LoginTokenAdmin` also keep it, so a lone removal creates a new inconsistency). Route the `telegram_id`-search question to the coordinator. |
| 12 | **BLOCK 3's cost model is wrong** (the inventory has zero consumers). Add `User.password` as a declared `CLEAR` entry (unimplemented — it is not erased today and the plan never mentions it), `Ad` as declaration-only, and lazy string labels. |
| 13 | Q-D4's "three-file one-commit" is **over-strict**: `apps/core/tests/test_advisory_lock_ids.py` no longer asserts integers. Adding a member needs only `apps/core/enums.py` + the `advisory_lock.py` docstring table. (Nuance: `test_sweep_consent.py::test_lock_id_is_consent_hard_delete` **does** pin `CONSENT_HARD_DELETE == 3` — harmless when adding 14.) |
| 14 | §0.2 C-3's "concurrent phase-02 agent" framing is stale — `REPAIR_BOT_USERNAME = 13` is shipped; 19 members; id 10 reserved; next free **14**. |
| 15 | **The env-backed-setting commit surface is five files plus a test, not four:** `base.py`, `secret_validation.py`, `prod.py`, **`.github/workflows/ci.yml` (`jobs.deploy-check.env`, non-secret non-templated placeholder)**, and the four `.env.*.example` templates. **Two** allowlist tests bite (`test_env_allowlist.py::test_example_keys_in_allowlisted` and `test_env_allowlist_reverse.py::test_consumed_env_vars_are_allowlisted`, a whole-tree AST scan) plus `test_deploy_check_env_parity.py`. Exception **type** is part of that contract. |
| 16 | **`mask_telegram_id` has two unstated defects:** 32-bit truncation is **not injective** (distinct Telegram IDs collide; birthday collisions from ~77k distinct IDs, and log correlation degrades silently), and the unsalted truncated digest over a small, structurally regular ID domain is enumerable, so the "Non-reversible" docstring is false. Lengthening the prefix fixes collisions, **not** reversibility. |
| 17 | Frontmatter is stale: `findings_implemented: 14` / `findings_merged_away: 1` against `status: planned` and `anchor_commit: aa2a6b0`; the tree is now `83622e0`. |
| 18 | `IMMEDIATE_ALERTS_ENABLED` verified correct as written (default `False`, `false` in all four templates, already allowlisted, gated with `getattr(settings, …, False)`). Phase 06 must not lift it. |

#### 0.6.4 New findings filed by this pass

- **`06-NEW-01`** — `PreferredCityMiddleware.process_response` uses the same plain
  `delete_cookie()` that cannot clear a `Secure` cookie over HTTPS. A different defect from
  the one BLOCK 9 fixes (different lifetime, different trigger). Recorded here, routed
  elsewhere.
- **`06-NEW-02`** — `ConsentRecord` has **no actor column**, so a superuser-initiated
  revocation is evidenced as "the subject withdrew" without recording that a staff member
  did it. A schema change BLOCK 12/15 own; BLOCK 10 records the limitation.
- **`06-NEW-03`** — `User.password` (the hash) is an identity-bearing column that
  `withdraw_consent` never erases. Declared by BLOCK 3's inventory; not implemented.

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

## Retention framing correction (owner ruling 2026-10-04)

**This section governs every retention statement in this plan.** Where an earlier subsection, a
risk row or an execution block states a retention period, this section is the authority.

### What is withdrawn

This phase recommended a retention period for the consent ledger and anchored it to a **statutory
limitation period**. **That inference is withdrawn.** A limitation period governs the window in which
a *claim* may be brought; it says nothing about how long a controller must keep a record, and stating
it as the reason for a retention period was the error being undone. Every location that carried that
anchor has been corrected. **No document in this project now asserts a statutory, regulatory,
guideline or limitation-period anchor for any retention window.**

Specifically withdrawn: the "longest plausible limitation period for a consumer claim" basis for the
event-field window; the BiH general-limitation-period figure and its statute citation; the
FBiH-versus-RS entity split and its stated confidence rating; the claim-window comparison in the
fingerprint window's basis; and, in BLOCK 18, the reasoning that the actor field must be retained to
the event bound. **No substitute statute and no substitute number was written in their place.**

### The rule as ruled — retention is **per field**

| Field | Rule | Standing |
|---|---|---|
| `user` (the subject) | the general record retention — the existing **90-day fingerprint bound** | project decision, **unchanged** |
| `choice`, `categories`, `consent_version`, `consent_given_at` (the consent/revocation event and its timestamp) | the **event retention period** — **policy-based and justified by purpose** | project decision, **re-grounded 2026-10-04** |
| `initiated_by` (the actor) | **12 months from the action, then irreversibly anonymised**, subject to a documented legal hold | project decision, **new — BLOCK 19, `06-NEW-02`** |

The governing statement, in the form that replaces the figure:

> `ConsentRecord` retention is **policy-based and must be justified by purpose; no general
> five-year retention requirement for this record is imposed by law.** In need-based form:
> **retain while there is a necessity to prove consent/withdrawal and the lawfulness of the
> corresponding processing; after a justified period expires, delete or anonymise.**

The implemented event window is still the value the command carries
(`_DECISION_RETENTION_DAYS`). It is now a **project decision defended on purpose** and revisitable
by the rule above. **It is not a deletion boundary** — the decision fields are anonymised, never
deleted, at every age. No law requires that value, and no document may cite one that does.

### The actor window, and why twelve months — the owner's rationale

- **Full accountability is preserved across a year.** The whole point of the actor column is being
  able to say *who* performed an action; a year is long enough to serve every plausible internal
  accountability process.
- **It is substantially shorter than the contested 5 years.** The owner rejected that figure.
- **A year covers a complete operational/audit cycle**, so the bound does not cut a cycle in half.
- **Identifying a specific employee beyond that requires separate justification** — it is not
  available by default.
- **This is a chosen minimisation period, not a statutory term.** It must never be described,
  here or anywhere, as required by law.

The window is enforced as a second mutation stage in the same sweep, and a **documented
`legal_hold`** exempts a row from it. A hold is an exemption from **actor** erasure only: it never
restores what the 90-day fingerprint window already cleared, and it never extends the event fields.

### Two supporting facts, recorded so no reader re-derives them by inference

- **GDPR Art. 5(1)(e) requires storage limitation** — that personal data is kept no longer than
  necessary — and **prescribes no number.** Any document reading it as prescribing a duration is
  wrong. Art. 7(1), cited elsewhere in this plan for demonstrability, likewise states no duration.
  **5 years must nowhere be described as a requirement of Montenegrin data-protection law, nor
  anchored to any limitation period.**
- **Montenegro's Personal Data Protection Law №133/2026** entered into force **19 September 2026**,
  applies from **20 March 2027**, and sets **no** universal five-year period for a consent record.
  It is a **neighbouring regime, not this project's applicable law** — see the jurisdiction
  assumption below. It is recorded because it is the regime of the **launch market**, which is not
  the regime of the **data subject**, and a reader meeting the two in one document will otherwise
  conflate them.

### Jurisdiction — a documented, revisitable assumption

- The **launch market** is **Montenegro**; the **data subject** is in **Bosnia and Herzegovina**.
- The applicable law is therefore **not** the GDPR directly, and this project's documentation **does
  not establish** that Montenegrin data-protection law applies.
- **GDPR article numbers used in this plan are descriptive shorthand for substantive standards**
  (storage limitation, demonstrability, withdrawal), **not** citations of directly applicable EU
  law. That reading is what the retention analysis rests on.
- **Open for the DPO to confirm or overturn.** It is recorded as an assumption because this pass
  could not close it, and it deliberately names **no** BiH statute, gazette reference or article
  number — that citation could not be supported from the repository.

What depends on it:

| Depends on the assumption | If it is wrong |
|---|---|
| Every "GDPR Art. X" citation used as a substantive standard in this plan | each must be re-cited to the correct instrument, or dropped as unsupported |
| The need-based retention rule as the applicable test | must be re-derived against whatever instrument actually applies |
| **The retention windows themselves (90 d / 12 months / event)** | **not dependent** — they are project decisions justified on purpose. A different instrument changes the *legal floor*, not the *justification*; a lower floor could require **shortening** a window, never **lengthening** one on legal grounds |
| `privacy.html`'s statement of the retention period to the data subject | the period stated must match the window actually enforced |

### What did not change

The 90-day fingerprint window, the anonymise-never-delete design, the absence of any `DELETE` path in
the sweep, the `_DECISION_RETENTION_DAYS` literal, and the existing 30-day post-withdrawal user
erasure. **None of those was part of this ruling.**

**Mirror:** `docs/99-agent/pii-consent-remediation-record.md` carries the same ruling in prose under
the same heading. The two are kept in step deliberately; if they ever disagree, the owner's ruling
governs and both must be corrected.

---

## 3. Execution blocks

Nineteen blocks. Three are **decision or architecture** blocks that ship no
production behaviour (BLOCK 1, BLOCK 3) or ship documentation only (BLOCK 2); sixteen
are implementation blocks. **One Implementor, strictly sequential, one commit per block**
(§1.3). BLOCKS 18 and 19 are the `06-NEW-02` follow-ups and are owned separately from the
`06-PII-1xx` remediation sequence.

Two blocks (**3** and **4**) have no dependency on anything in this plan and can be
prepared in parallel by the Auditor/Researcher while BLOCK 1's decision is being made —
but the **serial execution order is still §4.1's**, because BLOCK 1 is what
unblocks another phase. (BLOCKS 18 and 19 are the `06-NEW-02` follow-ups: they are recorded
here and in §3, but they are **not** in §4.1's serial order — both have already shipped, and
adding them would misstate the order that was actually executed.)

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
| **Blocks** | **BLOCK 9** and **BLOCK 13** are the named consumers — each becomes a declared-entry edit rather than a fresh audit. **BLOCK 11** is a third, product-gated consumer (Q-D3) |
| **Priority** | **P0** — it is the architectural prerequisite, and five findings become one-line changes once it exists |
| **Risk level** | **MEDIUM** — a new module in the erasure path, with a real over-engineering risk that must be argued, not assumed |
| **Required agents** | **Auditor · Researcher · Planner · Validator** (all four). The project rule 5 objection was answered in the Q-D9 resolution; the **Validator's** remaining job is to reject any accessor, base class, metaclass, app-registry hook or model import that appears in the module (see *Risk and rollback*) |

**Why it is a block and not an instruction.** The erasure contract is a hand-maintained
`update_fields` list on one model. Any table that denormalises identity
(`support_tickets`, `ads.*text`, `seller_verifications`, `moderation_action_logs.reason`,
`chat_id`, `preferred_city`) falls out of scope the moment it is added, and **no check
enforces membership**. Without a declaration, the sixth such column appears with the next
model. With one, BLOCK 13's `SupportTicket` decision becomes a declared entry rather than a
bespoke code path, and the guard turns the next omission into a red test.

**Shape decision — Q-D9 — RESOLVED 2026-10-01: this block is Option C (§0.6.1).**

**The table below is the record of the choice that was made. It is superseded, and is kept
only so the rejected alternatives stay visible.** Do not re-open it.

> **Letter warning — read before quoting either table.** §0.6.1's "**Option C**" is this
> block's decision: a declarative module **plus** a guard test. That is *not* the same as
> row **C** below, which meant "keep the hand-maintained list inside `withdraw_consent`,
> add nothing". The adopted shape is **row A's declaration and row C's guard, together,
> with row A's consumers removed.** The registry *with* consumers is rejected.

| Option (as filed 2026-09-29) | What it was | Verdict 2026-10-01 |
|---|---|---|
| **A** | A module-level registry in `apps/users/services/`, **consumed** by `withdraw_consent()`, `consent_hard_delete` and the backfill migration | **Rejected as filed; its data survives.** A registry with consumers has **no consumer available today** — BLOCK 11 and BLOCK 13 are both product-gated — so it would ship an abstraction with no reader in a destructive path, in the one block whose acceptance criterion is "no production behaviour changed" (project rule 5). Its alternative encoding either creates the `users → core` / `ads` / `trust` / `moderation` import edges this block exists to avoid, or degrades to untyped strings only a data migration could check |
| **B** | Model-level metadata — a model attribute or `Meta` entry declaring each model's identity columns | **Rejected.** `Meta` is schema metadata; erasure policy in it is a category error, and it spreads the contract across five apps that the erasure code would then have to import and reflect over |
| **C** | No declaration at all — keep the hand-maintained list and add only a guard test | **Adopted in substance, extended.** The list survives but is **promoted from an inline literal to a named, documented declaration in its own module** with a `StrEnum` action vocabulary, so the `RETAIN` escape hatch is representable at all. The guard test survives and is now the tripwire for the declaration |

**Adopted shape.** `src/backend/apps/users/services/pii_inventory.py` (new): a
`class ErasureAction(StrEnum)`; a **declared list** of
`(model_label: str, column: str, action: ErasureAction, reason: str)`; a per-model list of
**reviewed non-identity columns**; **lazy string model labels**, so the module imports no
`apps.*` model; and a module docstring that states, in the module itself, what the guard can
and cannot detect (§0.6.2). Full rationale, including the rejected alternatives, is §0.6.1
— do not repeat it here.

**File surface (semantic units) — two new files and nothing else**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/users/services/pii_inventory.py` (**new**) | module docstring → `from enum import StrEnum` → `ErasureAction` → the declared entry list → the per-model reviewed-column lists | **Location is settled** (Q-D9), not "the Researcher's call" as an earlier draft of this block said. Imports the standard library and **nothing from `apps.*`**. No `django.db` call, no import-time side effect |
| `src/backend/apps/users/tests/test_pii_inventory.py` (**new**) | the guard test module | `pytestmark = [pytest.mark.unit]` — it needs no database, which is also how binding constraint 3 is proven |

**Two files earlier drafts of this block listed as in-surface that are now explicitly out
of it:**

| File | Why it is out of this block |
|---|---|
| `src/backend/apps/users/services/deletion.py` | Consumption is BLOCK 9's and BLOCK 13's edit to the same function — that is the whole reason the serial edge exists. This block's `update_fields` list stays **byte-identical**; `test_deletion.py` passing unchanged is the acceptance criterion that proves it |
| `src/backend/apps/users/services/__init__.py` | **No re-export.** The four existing re-exports are consumer-facing service functions. BLOCK 9 / 13 will import `apps.users.services.pii_inventory` by its full path; a fifth export would put a module with no consumer on the package's import path and would grow this block's surface from one new file to two touched ones |

**Consumers.** **BLOCK 9 and BLOCK 13 are the consumers** this plan's dependency table
names: BLOCK 9 turns the `users.User` entries into the withdrawal teardown; BLOCK 13 turns
the `core.SupportTicket` entries into the scrub plus its `core`-app migration. **BLOCK 11 is
a third consumer** (the `ads.Ad` entries) and is product-gated on Q-D3. No production code
reads this block's output in this block.

**Promotion path, if a consumer ever needs lookup rather than declaration.** When a real
consumer appears — BLOCK 13's data migration resolving entries inside a `RunPython`, or
`withdraw_consent` deriving its column set from the declaration — the promotion is **one
accessor function** over the *same* declared tuples, resolving models lazily with
`django.apps.apps.get_model` **at call time, never at import time**. The declared data does
not change, so the promotion diff is confined to that function and is written **in the
consuming block, not before**. Do not build it speculatively (project rule 5). The module
docstring states this path in the module itself.

**Binding constraints**

1. **The declaration is data, not behaviour.** No base class, no metaclass, no Django app
   registry hook, no `django.db` call, **no import-time side effect** of any kind.
2. **No `apps.*` model import.** Model identity is a **lazy string label**
   (`"users.User"`, `"users.ConsentRecord"`, `"users.LoginToken"`, `"core.SupportTicket"`,
   `"ads.Ad"`, `"trust.SellerVerification"`, `"moderation.ModeratorActionLog"`,
   `"search.SavedSearch"`). This is what keeps `users → core.models` / `ads` / `trust` /
   `moderation` **uncreated**: `deletion.py` today imports exactly `apps.ads.models`,
   `apps.core.enums.AdStatus`, `apps.search.services.cache` and `apps.users.models`, and
   this block leaves that set unchanged. `SupportTicket` is in **`apps/core/models.py`** —
   the label is `core.SupportTicket`; `src/backend/apps/support/` does not exist.
3. **Importable without a database connection**, so a future data migration can consume it
   inside a `RunPython`. Proven by the test module being `unit`-marked and by one assertion
   that touching the declaration opens no connection.
4. **`RETAIN` must exist and must be used.** `User.chat_id` is a `RETAIN` entry with a
   written reason: `telegram_bot/middlewares/permissions.py::AccountStateMiddleware._resolve_user`
   resolves the acting user on `chat_id` *because* withdrawn/deleted users have their
   `telegram_id` nulled, and `User.chat_id.help_text` reads *"never nullified"*. **Nulling
   `chat_id` is forbidden.** A naive "clear everything" list would silently violate it.
5. **The declaration must be honest.** Every reason string states whether the action is
   implemented today. `User.password` is a declared `CLEAR` that is **not** erased by
   `withdraw_consent` and that **no block in phase 06 implements** (06-NEW-03) — the reason
   says so in those words. `ads.Ad` is **declaration-only** in this block.
6. **No production behaviour changes in this block.** No migration, no template, no `.po`,
   no `deletion.py` edit, no re-export. `apps/users/tests/test_deletion.py` passes
   **unchanged**; if it does not, this block has done BLOCK 9's work early and must be
   split.
7. **The guard is a tripwire on declared columns, not a classifier** (§0.6.2). No
   column-name heuristic is sound — `User.source`, `User.last_login`, `User.date_joined`
   and `SupportContact.telegram_id` all *look* like identity and are not; `Ad.title`,
   `Ad.description`, `ModeratorActionLog.reason`, `SupportTicket.text` and
   `SavedSearch.query` are data-subject free text no name heuristic can ever find. The
   module docstring **must say this**, so the next reader does not believe the guard
   detects PII. Free text is handled by **declaration**, not detection.

**Scope correction carried into this block (§0.6.3 #7, #8, #12).** There is **no
`Ad.rejected_reason` column** — the moderation free text is `moderation.ModeratorActionLog.reason`,
and `apps/ads/admin.py::rejected_reason` is only a display helper that reads it. An entry
naming `Ad.rejected_reason` is a defect. `User.password`, the `ads.Ad` entries and the lazy
string labels are this block's additions, not the report's.

**Implementor task**

```yaml
id: task_06_b03_pii_inventory
title: "Declare the PII erasure inventory and its completeness guard (Required Fix 1)"
priority: high
depends_on: []
source_reference: ".ai/plans/06-pii-consent-remediation.md"
source_section: "BLOCK 3 - One declarative PII erasure inventory (Required Fix 1)"
source_blocks: ["BLOCK 3"]
description: >
  The erasure contract is a hand-maintained update_fields list on one model, and five
  findings in this phase (06-PII-101, 06-PII-109, 06-PII-110, 06-PII-111, 06-PII-114) are
  separate symptoms of its absence. Q-D9 is RESOLVED: ship a declarative module,
  src/backend/apps/users/services/pii_inventory.py, holding a StrEnum action vocabulary
  and a declared list of (model_label, column, action, reason) entries with LAZY STRING
  model labels, plus a guard test that turns the next undeclared column on a listed model
  into a red test. This block changes NO production behaviour: deletion.py is not touched,
  no migration is generated, no template or .po changes, and
  apps/users/tests/test_deletion.py must pass unchanged. BLOCK 9 and BLOCK 13 are the
  consumers; BLOCK 11 is a third, product-gated consumer (Q-D3).
goals:
  - "one declared, documented erasure contract for every data-subject identity column this phase touches"
  - "make an undeclared column on a listed model a loud test failure instead of a silent leak"
  - "represent deliberate retention (User.chat_id) and deferred work (free text) as data, not as omission"
  - "leave production behaviour byte-identical"
extra_context: |
  BINDING CONSTRAINTS - quoted verbatim from the plan's BLOCK 3. All of them hold.

  1. The declaration is data, not behaviour. No base class, no metaclass, no Django app
     registry hook, no django.db call, no import-time side effect of any kind.
  2. No apps.* model import. Model identity is a lazy string label ("users.User",
     "users.ConsentRecord", "users.LoginToken", "core.SupportTicket", "ads.Ad",
     "trust.SellerVerification", "moderation.ModeratorActionLog", "search.SavedSearch").
     This is what keeps users -> core.models / ads / trust / moderation UNCREATED:
     deletion.py today imports exactly apps.ads.models, apps.core.enums.AdStatus,
     apps.search.services.cache and apps.users.models, and this block leaves that set
     unchanged. SupportTicket is in apps/core/models.py - the label is core.SupportTicket;
     src/backend/apps/support/ does not exist.
  3. Importable without a database connection, so a future data migration can consume it
     inside a RunPython. Proven by the test module being unit-marked and by one assertion
     that touching the declaration opens no connection.
  4. RETAIN must exist and must be used. User.chat_id is a RETAIN entry with a written
     reason: telegram_bot/middlewares/permissions.py::AccountStateMiddleware._resolve_user
     resolves the acting user on chat_id because withdrawn/deleted users have their
     telegram_id nulled, and User.chat_id.help_text reads "never nullified". Nulling
     chat_id is forbidden. A naive "clear everything" list would silently violate it.
  5. The declaration must be honest. Every reason string states whether the action is
     implemented today. User.password is a declared CLEAR that is NOT erased by
     withdraw_consent and that no block in phase 06 implements (06-NEW-03) - the reason
     says so in those words. ads.Ad is declaration-only in this block.
  6. No production behaviour changes in this block. No migration, no template, no .po,
     no deletion.py edit, no re-export. apps/users/tests/test_deletion.py passes
     unchanged; if it does not, this block has done BLOCK 9's work early and must be
     split.
  7. The guard is a tripwire on declared columns, not a classifier. No column-name
     heuristic is sound - User.source, User.last_login, User.date_joined and
     SupportContact.telegram_id all LOOK like identity and are not; Ad.title, Ad.description,
     ModeratorActionLog.reason, SupportTicket.text and SavedSearch.query are data-subject
     free text no name heuristic can ever find. The module docstring MUST say this, so the
     next reader does not believe the guard detects PII. Free text is handled by
     declaration, not detection.

  CONSUMERS (verbatim): "BLOCK 9 and BLOCK 13 are the consumers this plan's dependency
  table names: BLOCK 9 turns the users.User entries into the withdrawal teardown; BLOCK 13
  turns the core.SupportTicket entries into the scrub plus its core-app migration. BLOCK 11
  is a third consumer (the ads.Ad entries) and is product-gated on Q-D3. No production code
  reads this block's output in this block."

  PROMOTION PATH (verbatim): "When a real consumer appears - BLOCK 13's data migration
  resolving entries inside a RunPython, or withdraw_consent deriving its column set from
  the declaration - the promotion is one accessor function over the SAME declared tuples,
  resolving models lazily with django.apps.apps.get_model at call time, never at import
  time. The declared data does not change, so the promotion diff is confined to that
  function and is written in the consuming block, not before. Do not build it
  speculatively (project rule 5). The module docstring states this path in the module
  itself."

  SCOPE CORRECTIONS CARRIED IN (verbatim): "There is NO Ad.rejected_reason column - the
  moderation free text is moderation.ModeratorActionLog.reason, and
  apps/ads/admin.py::rejected_reason is only a display helper that reads it. An entry
  naming Ad.rejected_reason is a defect."

  STANDING PROJECT RULES (plan section 1.4, restated): English only; no print() (use
  logger = logging.getLogger(__name__) with lazy %s); fixed values via StrEnum, never plain
  strings/dicts/lists; the Django ORM is the persistence layer - do NOT introduce Pydantic
  DTOs into a service path; all schema changes via Django migrations, sequential per app,
  never renumber an existing one (this block generates NO migration); small focused
  modules, composition over inheritance, no new abstraction without strong justification
  (project rule 5); production code is king.

  GIT (plan section 1.3): one Implementor at a time; stage specific files with
  `git add <file>` - never `git add -A` or `git add .`; never git reset / checkout /
  restore / stash / --amend / --no-verify; never revert, stash or checkout a file you did
  not write - if a file you are about to edit has uncommitted changes from another agent,
  stop and report it; every citation is cycle-scoped 06-PII-1xx, never bare PII-1xx.

  TEST ENVIRONMENT (plan section 1.1): tests are Docker-only; `uv run pytest` on the host
  always fails. Concurrent runs share one test_mko_bazuna - a mass ForeignKeyViolation on
  auth_permission / django_content_type, or "database test_mko_bazuna does not exist", is a
  contamination artefact, not a defect: re-run serially before reporting it.
required_entries:
  # The complete list, written out. `implemented` below is NOT a field of the declared
  # 4-tuple - it tells the Implementor what the REASON STRING must say. The declared
  # tuple is exactly (model_label, column, action, reason).
  - model_label: "users.User"
    column: telegram_id
    action: ErasureAction.NULL
    implemented: true
    reason_must_state: "Nulled by withdraw_consent inside its existing transaction.atomic(); breaks chat linkage so no re-link is possible. Declared so the column can never fall out of the erasure contract again (06-PII-110)."
  - model_label: "users.User"
    column: username
    action: ErasureAction.NULL
    implemented: true
    reason_must_state: "The public Telegram handle, nulled together with telegram_id. Re-identifying, and was never in scope on DECLINE (06-PII-110)."
  - model_label: "users.User"
    column: first_name
    action: ErasureAction.CLEAR
    implemented: true
    reason_must_state: "Emptied to the empty string - the column is NOT NULL, so the action is CLEAR, not NULL (06-PII-110)."
  - model_label: "users.User"
    column: last_name
    action: ErasureAction.CLEAR
    implemented: true
    reason_must_state: "Emptied to the empty string - NOT NULL, so CLEAR, not NULL (06-PII-110)."
  - model_label: "users.User"
    column: email
    action: ErasureAction.CLEAR
    implemented: true
    reason_must_state: "Emptied to the empty string - NOT NULL, so CLEAR, not NULL (06-PII-110)."
  - model_label: "users.User"
    column: password
    action: ErasureAction.CLEAR
    implemented: false
    reason_must_state: "Identity-bearing credential hash. withdraw_consent does NOT touch it today and NO block in phase 06 implements the clear - the declaration is honest about that so the omission is visible rather than invisible (06-NEW-03)."
  - model_label: "users.User"
    column: chat_id
    action: ErasureAction.RETAIN
    implemented: true
    reason_must_state: "Retained deliberately and permanently. AccountStateMiddleware._resolve_user resolves the acting user on chat_id precisely so withdrawn/deleted users, whose telegram_id is nulled, are still found and stay blocked; User.chat_id.help_text reads 'never nullified'. Nulling it is forbidden."
  - model_label: "users.User"
    column: preferred_city
    action: ErasureAction.NULL
    implemented: false
    reason_must_state: "Persisted behavioural preference. Owned by BLOCK 9 (06-PII-110), which clears it on DECLINE and on withdrawal alongside the cookie deletion; the cookie/column asymmetry is that block's defect. Declared here so the column is not forgotten by it."
  - model_label: "users.ConsentRecord"
    column: session_key
    action: ErasureAction.RETAIN
    implemented: false
    reason_must_state: "A live Django session identifier with no retention boundary. The ConsentRecord half of 06-PII-110 was absorbed into 06-PII-116; BLOCK 15 owns the TTL decision (Q-D4) and the sweep. Declared here so the deferral is visible."
  - model_label: "users.ConsentRecord"
    column: user_agent
    action: ErasureAction.RETAIN
    implemented: false
    reason_must_state: "Browser-fingerprint-grade text, same table and same retention class as session_key. BLOCK 15's sweep (06-PII-116) owns its boundary (Q-D4)."
  - model_label: "users.ConsentRecord"
    column: ip_address
    action: ErasureAction.RETAIN
    implemented: false
    reason_must_state: "Declared by BLOCK 3, not by any finding: same table and same retention class as session_key and user_agent, and an undeclared sibling in a table BLOCK 15 will sweep is exactly the omission this block exists to prevent. BLOCK 15 (06-PII-116) owns its boundary (Q-D4)."
  - model_label: "users.LoginToken"
    column: telegram_id
    action: ErasureAction.DELETE_ROW
    implemented: true
    reason_must_state: "Active login tokens are deleted BEFORE telegram_id is nulled, so a still-valid token cannot re-link a withdrawn identity. The whole row goes, including token_hash and browser_binding. Declared by BLOCK 3 to make the one already-implemented row erasure in the contract visible."
  - model_label: "core.SupportTicket"
    column: chat_id
    action: ErasureAction.NULL
    implemented: false
    reason_must_state: "Denormalised Telegram chat id copied verbatim from the sender, and currently NON-NULLABLE, so the clear requires BLOCK 13's core-app migration first. It survives withdrawal and the 30-day sweep byte-for-byte, on a row the FK SET_NULL has already orphaned (06-PII-101)."
  - model_label: "core.SupportTicket"
    column: telegram_id
    action: ErasureAction.NULL
    implemented: false
    reason_must_state: "Denormalised Telegram id copied verbatim from the sender, currently NON-NULLABLE, so BLOCK 13's core-app migration must land first. Survives withdrawal and the sweep as an orphan (06-PII-101)."
  - model_label: "core.SupportTicket"
    column: username
    action: ErasureAction.NULL
    implemented: false
    reason_must_state: "The public handle copied verbatim from the sender; already nullable. Survives as an orphan with no remaining account link (06-PII-101). BLOCK 13 owns the scrub."
  - model_label: "core.SupportTicket"
    column: text
    action: ErasureAction.RETAIN
    implemented: false
    reason_must_state: "The ticket BODY is the support record, not a denormalised identity column: 06-PII-101's scope is the three identity columns above. BLOCK 12 (06-PII-106) drops it from SupportTicketAdmin.search_fields and masks the changelist. No retention boundary for the body is decided in phase 06 - declared so the deferral is visible and a later block has a one-line edit."
  - model_label: "ads.Ad"
    column: title
    action: ErasureAction.CLEAR
    implemented: false
    reason_must_state: "User-authored free text, surviving the 30-day window byte-for-byte and listed and full-text searchable by any staff account. BLOCK 11 (06-PII-109) owns the scrub or the spec correction; the scope choice is the product's (Q-D3). DECLARATION-ONLY in this block."
  - model_label: "ads.Ad"
    column: title_en
    action: ErasureAction.CLEAR
    implemented: false
    reason_must_state: "Per-language variant of the ad title; same owner and same deferral as Ad.title (BLOCK 11, 06-PII-109, Q-D3). DECLARATION-ONLY in this block."
  - model_label: "ads.Ad"
    column: title_bs
    action: ErasureAction.CLEAR
    implemented: false
    reason_must_state: "Per-language variant of the ad title; same owner and same deferral as Ad.title (BLOCK 11, 06-PII-109, Q-D3). DECLARATION-ONLY in this block."
  - model_label: "ads.Ad"
    column: description
    action: ErasureAction.CLEAR
    implemented: false
    reason_must_state: "On a classifieds board the description is the most likely place for a seller to have typed a name, a phone number or a 'call me at' line. BLOCK 11 (06-PII-109) owns the scrub; Q-D3 decides scrub versus spec correction. DECLARATION-ONLY in this block."
  - model_label: "ads.Ad"
    column: description_en
    action: ErasureAction.CLEAR
    implemented: false
    reason_must_state: "Per-language variant of the ad description; same owner and same deferral as Ad.description (BLOCK 11, 06-PII-109, Q-D3). DECLARATION-ONLY in this block."
  - model_label: "ads.Ad"
    column: description_bs
    action: ErasureAction.CLEAR
    implemented: false
    reason_must_state: "Per-language variant of the ad description; same owner and same deferral as Ad.description (BLOCK 11, 06-PII-109, Q-D3). DECLARATION-ONLY in this block."
  - model_label: "trust.SellerVerification"
    column: phone_number
    action: ErasureAction.DROP_COLUMN
    implemented: false
    reason_must_state: "Nothing in src/ writes it - four tree-wide hits are the field itself, trust/migrations/0001_initial.py, and two unrelated test assertions - apps/trust/ has no admin.py, and the column is permanently NULL. The fix is schema removal, not a row erasure, so the action is DROP_COLUMN (06-PII-111, BLOCK 17). Declaring NULL or RETAIN here would be fiction."
  - model_label: "moderation.ModeratorActionLog"
    column: reason
    action: ErasureAction.RETAIN
    implemented: false
    reason_must_state: "Staff-authored free text, unbounded, on a row that deliberately survives user erasure with user_id = NULL; a moderator quoting a seller's message persists the subject's data indefinitely. BLOCK 16 (06-PII-114) redacts at WRITE TIME, which is not an erasure action - so the erasure action is RETAIN with the deferral declared. Adding a write-time redaction rule to this inventory would be a category error."
  - model_label: "search.SavedSearch"
    column: query
    action: ErasureAction.RETAIN
    implemented: false
    reason_must_state: "The FTS query string, stored in the user's language and matched against the per-language search vector - it cannot be redacted. BLOCK 14's redaction concerns SearchHistory.query_normalized, a different column in a different model. BLOCK 9 (06-PII-110) deactivates the row on withdrawal rather than editing the query."
files:
  - path: "src/backend/apps/users/services/pii_inventory.py"
    targets:
      - type: module
        name: pii_inventory
      - type: class
        name: ErasureAction
      - type: constant
        name: PII_ERASURE_ENTRIES
      - type: constant
        name: REVIEWED_NON_IDENTITY_COLUMNS
    semantic_anchors:
      # New file - no pre-existing anchor. The declaration order below is the contract;
      # no line number is a target.
      declaration_order:
        - "module docstring: what this module is, that it declares rather than enforces, that the guard is a tripwire on declared columns and NOT a classifier, the list of look-alike columns that are deliberately not entries, and the promotion path to a registry"
        - "imports: `from __future__ import annotations` and `from enum import StrEnum` - standard library only, nothing from apps.*, nothing from django.*"
        - "class ErasureAction(StrEnum)"
        - "the declared entry list (module-level constant of 4-tuples)"
        - "the per-model reviewed non-identity column list (module-level constant)"
  - path: "src/backend/apps/users/tests/test_pii_inventory.py"
    targets:
      - type: module
        name: test_pii_inventory
    semantic_anchors:
      declaration_order:
        - "module docstring stating the guard's scope and its stated limitation (not a classifier)"
        - "`pytestmark = [pytest.mark.unit]` - the guard needs no database, which is how binding constraint 3 is proven"
        - "the guard test functions"
changes:
  - action: add_code
    description: >
      Create src/backend/apps/users/services/pii_inventory.py: an ErasureAction StrEnum
      (CLEAR / NULL / DELETE_ROW / RETAIN / DROP_COLUMN), the declared entry list required
      by required_entries above with a written reason per entry, and a per-model reviewed
      non-identity column list so the guard has a complete review surface per listed model.
      Generate the reviewed-column lists mechanically from Model._meta (one-off
      introspection), never by hand-typing them.
    code_hint: |
      from __future__ import annotations

      from enum import StrEnum


      class ErasureAction(StrEnum):
          """What the erasure path must do with one data-subject column.

          The vocabulary is a StrEnum (project rule 10). CLEAR overwrites with an empty
          or placeholder value (for NOT NULL text columns); NULL sets the column to NULL;
          DELETE_ROW removes the owning row; RETAIN is a deliberate, reasoned decision to
          keep the column; DROP_COLUMN means the column is removed from the schema rather
          than from a row, which is what 06-PII-111's fix actually is.
          """

          CLEAR = "clear"
          NULL = "null"
          DELETE_ROW = "delete_row"
          RETAIN = "retain"
          DROP_COLUMN = "drop_column"


      # (model_label, column, action, reason). Model labels are LAZY STRINGS on purpose:
      # importing the models would create users -> core.models / ads / trust / moderation
      # import edges that the module boundaries do not have today.
      PII_ERASURE_ENTRIES: tuple[tuple[str, str, ErasureAction, str], ...] = (
          (
              "users.User",
              "chat_id",
              ErasureAction.RETAIN,
              "Retained deliberately: AccountStateMiddleware._resolve_user resolves the "
              "acting user on chat_id so withdrawn users stay blocked. Never null it.",
          ),
          (
              "trust.SellerVerification",
              "phone_number",
              ErasureAction.DROP_COLUMN,
              "Permanently NULL and never written; 06-PII-111 removes the column, so the "
              "erasure action is a schema removal, not a row write.",
          ),
          # ... every entry in required_entries, in model_label order
      )
  - action: add_code
    description: >
      Create src/backend/apps/users/tests/test_pii_inventory.py - the guard. It must fail
      when a listed model gains a concrete data column that has neither an entry nor a
      reviewed-column entry, and it must not attempt to classify columns by name.
    code_hint: |
      pytestmark = [pytest.mark.unit]


      def test_every_declared_entry_resolves_to_a_real_field() -> None:
          """A renamed or dropped column fails the declaration, not the erasure path."""
          for model_label, column, _action, _reason in PII_ERASURE_ENTRIES:
              model = apps.get_model(model_label)
              assert model is not None, f"unknown model label {model_label!r}"
              assert column in {f.name for f in model._meta.get_fields()}, (
                  f"{model_label}.{column} is declared but is not a field"
              )


      def test_listed_models_have_no_unreviewed_column() -> None:
          """The tripwire: a new data column on a listed model must be ruled on."""
          for model_label, reviewed in REVIEWED_NON_IDENTITY_COLUMNS.items():
              model = apps.get_model(model_label)
              undeclared = declared_or_reviewed(model_label) - _unruled_columns(model, reviewed)
              assert not undeclared, (
                  f"{model_label} gained column(s) with no erasure entry and no reviewed "
                  f"decision: {sorted(undeclared)}"
              )
tests_required:
  - id: registry_completeness_guard
    assertion: >
      A listed model gains a concrete, non-relational, non-timestamp column with no entry
      and no reviewed-column decision, and the guard fails with a message naming the model
      and the unreviewed column. DEMONSTRATE THIS RED before committing: add a temporary
      CharField identity column to one listed model (users.User is the natural choice), run
      the guard, capture the failure, then REVERT the temporary field. The failure output
      goes in the commit body; the temporary field must NOT be in the committed diff.
      Note: apps/core/tests/test_migrations.py runs `makemigrations --check --dry-run` in a
      subprocess, so the temporary field must be reverted and that module re-run green
      before the block is finished.
  - id: retain_is_a_declared_decision
    assertion: >
      User.chat_id resolves to an entry whose action is RETAIN and whose reason is
      non-empty and names the bot-side resolution that depends on it, so the retention is
      a declared decision rather than an omission.
  - id: no_behaviour_change
    assertion: >
      apps/users/tests/test_deletion.py passes UNCHANGED. If it does not, this block has
      done BLOCK 9's work early and must be split.
  - id: standard_compliance
    assertion: >
      Per plan section 1.5, no test asserts a literal private name, a line number, a
      template-string substring, a column count, or the mere presence of a symbol. Assert
      on resolution, on behaviour, and on the absence of danger. Do NOT test the module
      docstring.
acceptance_criteria:
  - "every entry in required_entries is present with its specified action, and each reason string is non-empty and states whether the action is implemented today"
  - "User.password is declared CLEAR and its reason says in plain words that withdraw_consent does not erase it today and that no phase-06 block implements it (06-NEW-03)"
  - "User.chat_id is declared RETAIN with a non-empty reason naming the resolution that depends on it; no entry anywhere sets chat_id to NULL or CLEAR"
  - "the free-text columns (Ad.title/title_en/title_bs/description/description_en/description_bs, ModeratorActionLog.reason, SupportTicket.text, SavedSearch.query) each have an explicit RETAIN entry whose reason names the owning block"
  - "the module imports nothing from apps.* and nothing from django.db; it opens no database connection and executes no query at import time"
  - "the module docstring states that the guard is a tripwire on declared columns, not a classifier, and lists the look-alike columns that are deliberately not entries"
  - "the guard fails when a listed model gains a concrete data column with no entry and no reviewed decision, and the red demonstration is recorded in the commit body"
  - "no entry names Ad.rejected_reason; the moderation free text is entered as moderation.ModeratorActionLog.reason"
  - "apps/users/tests/test_deletion.py passes unchanged; deletion.py, services/__init__.py, every migration, every template and every .po file are untouched"
  - "the commit stages exactly the two new files, explicitly by path"
tests_to_run:
  - "src/backend/apps/users/tests/test_pii_inventory.py"
  - "src/backend/apps/users/tests/test_deletion.py"
  - "src/backend/apps/core/tests/test_migrations.py"
commands:
  setup: "$dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'"
  test: "$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS=\"src/backend/apps/users/tests/test_pii_inventory.py src/backend/apps/users/tests/test_deletion.py --tb=short\" test"
  test_full_users: "$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS=\"src/backend/apps/users/tests --tb=short\" test"
  lint: "uv run ruff check src/backend/apps/users/services/pii_inventory.py src/backend/apps/users/tests/test_pii_inventory.py"
  typecheck: "uv run basedpyright src/backend/apps/users/services/pii_inventory.py"
  notes: >
    PYTEST_OPTS is unquoted in docker/entrypoint-test.sh, so each token is word-split on
    spaces, and setting it REPLACES the default pytest args (--reuse-db --tb=short
    --durations=10 -n auto --maxprocesses=4 --dist loadgroup) - a targeted run therefore
    loses xdist parallelism and DB reuse. Never use --override-ini=addopts=, which strips
    --import-mode=importlib. Concurrent runs share one test_mko_bazuna: a mass
    ForeignKeyViolation on auth_permission / django_content_type, or "database
    test_mko_bazuna does not exist", is a contamination artefact - re-run serially before
    reporting a defect.
commit:
  message: "feat(users): declare the PII erasure inventory (06-PII-101)"
  body_must_state:
    - "the Q-D9 Option C decision and that no registry with consumers was built, per project rule 5"
    - "the red demonstration of the guard, with the failure output"
    - "that no production behaviour changed and test_deletion.py is untouched"
    - "that adding a concrete data column to any of the eight listed models now requires an entry or a reviewed decision, so other phase agents are warned"
    - "every citation cycle-scoped as 06-PII-1xx, never bare PII-1xx"
```

**Tests required** (full specification is in the task YAML above)

1. **Guard, demonstrated red** — a listed model gains a concrete data column with no entry
   and no reviewed decision; the guard fails, naming the model and the column. Capture the
   failure, then **revert** the temporary field. The temporary field must not be in the
   committed diff, and `apps/core/tests/test_migrations.py` (which runs
   `makemigrations --check --dry-run`) must be re-run green after the revert.
2. **`RETAIN` is a declared decision** — `User.chat_id` resolves to a `RETAIN` entry with a
   non-empty reason naming the resolution that depends on it, so the retention cannot be
   mistaken for an omission.
3. **No behaviour change** — `apps/users/tests/test_deletion.py` passes **unchanged**. If it
   does not, this block has done BLOCK 9's work early and must be split.

**Risk and rollback**

- *Risk (the real one, now argued rather than gated):* this is the one block in the plan
  that could be an **over-engineering** failure. Project rule 5 says prefer the simple,
  obvious solution. Mitigation is the **Q-D9 resolution itself**: a registry with consumers
  was rejected because it has **no consumer available today** (BLOCK 11 and BLOCK 13 are
  product-gated), so the declaration carries zero production behaviour and a documented
  promotion path. The Validator's job is to reject any **accessor, base class, metaclass,
  app-registry hook or model import** that appears in the module.
- *Risk:* the module creates a `users` → `core` / `ads` / `trust` / `moderation` import
  direction the boundaries do not have. Mitigation: **lazy string model labels** (binding
  constraint 2) and `deletion.py` untouched.
- *Risk (new, and cross-phase):* the guard makes **eight models** a shared surface. Any
  other phase agent that adds a concrete data column to `users.User`, `users.ConsentRecord`,
  `users.LoginToken`, `core.SupportTicket`, `ads.Ad`, `trust.SellerVerification`,
  `moderation.ModeratorActionLog` or `search.SavedSearch` will now fail this test until the
  column is ruled on. This is the intended tripwire, and the commit body says so.
- *Rollback:* a straight revert. The declaration has no consumer, so reverting changes
  nothing observable.
- *Cross-phase:* BLOCK 9 and BLOCK 13 re-read this block's output and consume the entries.
  **Stale cross-references to fix when their blocks are planned:** BLOCK 9's
  "Depends on BLOCK 3 (the inventory, **if option A**)", its file-surface row "Only if
  option A was chosen", its binding constraint 3 "If BLOCK 3 chose option C (list + guard
  test)"; and BLOCK 16's dependency row "BLOCK 3's registry is a *nice-to-have* consumer".
  All of them predate the Q-D9 resolution and must be restated against the declaration
  when those blocks' tasks are written.

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

*Status: **recommended, pending owner ratification.** The recommendation below is the plan's
**working assumption** for BLOCK 4 — it is what the Implementor task encodes, and every
task-level artefact derived from this block inherits it. It is **not** a decision. BLOCK 4
does not start until the owner ratifies it; if the owner chooses otherwise, the task YAML
below is the only thing that changes, and the working-assumption section states exactly
which parts are affected by which alternative.*

| Question the owner must answer | Options and consequences |
|---|---|
| Where does `LOG_MASK_KEY` come from? | (i) **Derived** from `SECRET_KEY` (e.g. an HMAC subkey label) — no new secret to provision, no new allowlist entry, but rotating `SECRET_KEY` invalidates all mask correlation at once. (ii) **Independent** secret — a clean rotation boundary, but a new value every environment must be given, a new `ALLOWED_ENV_VARS` entry, four new `.env.*.example` lines, and a new `prod.py` guard. The phase-02 precedent is (ii) — `BOT_USERNAME` is an independent var with its own guard and a `secret_validation.py` helper |
| Required in production, or defaulted? | (i) **Fail-fast in `prod.py`** — matches the existing pattern (`_validate_production_secret` plus the `_SKIP_SECRET_VALIDATION` block, now **eight** guards after phase 02, and `secret_validation.py`'s `validate_bot_username`). (ii) **Defaulted** — simpler, but **the default is public**, and a published key makes the mask reversible again, i.e. the fix ships a false security property. Option (ii) is only acceptable if the default is a per-process random value, which forfeits cross-process correlation |
| Rotation policy | Rotation invalidates correlation across old log lines. The spec edit must say so. The choice between "rotate rarely, document the cost" and "rotate on a schedule and accept broken correlation" is an owner decision; **this plan does not choose** |

#### Decision recommendation (Researcher, 2026-10-02) — **Q-D8, recommended pending owner ratification**

**The one-line answer:** **(ii) an independent secret · (ii) required in production, fail-fast ·
rotate only on suspected compromise, never on a schedule.**

**Rationale.** A keyed mask needs a key it owns, or it inherits someone else's rotation
schedule and someone else's blast radius. Deriving `LOG_MASK_KEY` from `SECRET_KEY` fails both
tests, and it fails them against Django's *own* deployment checklist, which says of
`SECRET_KEY`: *"Make sure that the key used in production isn't used anywhere else"*. Under
derivation the mask key **is** the signing key's bits: a leak of one is a leak of the other, so
neither can be attributed or revoked in isolation, and every routine `SECRET_KEY` rotation —
including the temporary, `SECRET_KEY_FALLBACKS`-mediated rotation Django's documentation actively
recommends — silently re-keys the mask. Worse, the mask has **no verification path** (it is
written into logs and never checked against anything), so there is no `*_FALLBACKS` equivalent
and no graceful rotation is possible at all. An independent secret costs one env var, one
allowlist entry, four template lines and one guard — all of which BLOCK 4 was already going to
pay for under option (ii) anyway — and buys a rotation boundary, a scoped blast radius and
attributable compromise. It also matches phase 02's precedent exactly.

| Sub-decision | Options | Verdict and the decisive reason |
|---|---|---|
| **Provenance** | (i) derived from `SECRET_KEY` · (ii) independent secret | **(ii).** (i) is the only option that couples an unrelated, frequently-rotated key to log correlation. Django's deployment checklist forbids reusing `SECRET_KEY`; OWASP's Secrets Management Cheat Sheet records the failure mode — *"services share the same secrets, which makes identifying the source of compromise or leak challenging"*. Under (i) `DJANGO_SECRET_KEY`'s catastrophic blast radius (session/CSRF-cookie and signed-value forgery) is **inherited** by the mask key, and no scoped revocation exists. |
| **Required or defaulted** | (i) fail-fast in `prod.py` · (ii) public default · (iii) per-process random default | **(i).** (ii) ships a false security property and the plan already forbids it. (iii) is the real alternative and it is **not** needed — see the correlation finding below: the cross-process requirement is on the *log stream*, and there is nothing at rest for a per-process key to protect, so (iii) pays its cost for nothing. Empty default in non-production (`env("LOG_MASK_KEY", default="")`), non-empty and guard-enforced in production. |
| **Rotation** | (a) rotate rarely / on compromise · (b) rotate on a schedule | **(a).** A scheduled rotation has no upside this control needs — the threat it defends is *possession of the key*, and a schedule neither detects that nor shortens exposure materially — while its cost is total, permanent loss of correlation across the log history. WP216/AEPD: HMAC with a **retained** key is *pseudonymisation*; only **key destruction** reaches anonymisation. So the spec must say *pseudonymised*, never *anonymised* or *non-reversible*. |

#### Working assumption for the Implementor task (PENDING OWNER RATIFICATION)

**Assume, unless the owner says otherwise, all three of these — they travel together and any
one of them alone is worse than doing nothing:**

1. **`LOG_MASK_KEY` is an independent secret.** Not derived from `SECRET_KEY`, not an HMAC
   subkey of it, not a salt off it. A new value every environment must be provisioned with.
2. **Required in production, fail-fast in `prod.py`.** `env("LOG_MASK_KEY", default="")` in
   `base.py` — empty default in non-prod, guard-enforced non-empty in prod. **Never** a
   published default (that ships a false security property) and **never** a per-process random
   default (there is nothing at rest for it to protect — the correlation requirement is on the
   *log stream*).
3. **Rotate only on suspected compromise, never on a schedule.** An HMAC whose key is
   *retained* is **pseudonymisation**, not anonymisation (WP216 / AEAD, AEPD): the operator can
   re-derive any mask for any candidate ID. So the words "anonymised" and "non-reversible" must
   not appear in the rewritten docstring or spec line. A scheduled rotation would cost
   **permanent, total loss of correlation across the log history** while shortening no exposure
   window, because the threat is *possession of the key* and a schedule neither detects that nor
   revokes it.

**Width is not part of the ratification.** 12 hex (`hexdigest()[:12]`, 48 bits) is settled inside
this block and is not an owner decision: confidentiality comes from the key, correlation
fidelity comes from the width, and the only reason 12 is defensible against RFC 2104 §5's
80-bit floor is the sentence that **must** appear in both the docstring and the spec line —
*correlation identifier, never an authenticator*. If the owner ratifies (1)–(3) and that
sentence ships, the width question is closed; if the sentence does not ship, 12 hex is
indefensible and the block is not done.

**What a different ratification would change, precisely** (so the owner can see the blast
radius before choosing): choosing (i) *derived* removes the new env var, its allowlist entry,
the four template lines, the `ci.yml` entry and the guard — but then the `SECRET_KEY` blast
radius is inherited by log correlation, no scoped revocation exists, and there is no
`*_FALLBACKS` path because the mask has no verification step. Choosing (ii) *public default*
removes the guard only, and re-opens the exact enumeration the block exists to close. Choosing
(b) *scheduled rotation* changes nothing in the code and only the spec wording.

**The correlation requirement is real, and it is a log-stream requirement.** Verified across the
whole tree: `mask_telegram_id` has **14** call sites and **not one** assigns its result to a model
field, a session, a cache key or a Redis key. They are 9 `logger.*` calls, 4
`create_admin_user.py` `self.stdout.write` calls, and the `LoginTokenAdmin.telegram_id_display`
admin display method. **Consequence: BLOCK 4 is not a data migration, and a key rotation is not a
data migration.** What *is* real: `docker-compose.prod.yml` runs `web`, `bot` and `scheduler` as
separate services and `prod.py` sends JSONL to stdout "for log aggregation", and a single failed
login produces a bot-side `mask_telegram_id(message.from_user.id)` line
(`telegram_bot/handlers/login.py`) **and** a web-side `mask_telegram_id(telegram_id)` line
(`apps/users/views/consent.py`) for the same user. Those two are joinable only on the masked
value. A per-process random default would break exactly that join and nothing else — which is
precisely why it buys nothing: the thing at risk is log correlation, and the key has to be
*shared* to protect it.

**Output width: keep `hexdigest()[:12]` (48 bits).** The two widths serve two different purposes
and must be argued separately. *Confidentiality comes from the key, not the width*: without
`LOG_MASK_KEY` an attacker can enumerate all 2^34 candidate IDs but cannot verify a single one,
because they cannot compute `HMAC(K, m)` for any `m`. *Correlation fidelity comes from the width*,
via the birthday bound `P(collision) ≈ n²/2N`, verified numerically:

| Output | `N` | 50% collision at `n = 1.1774·√N` | at `n = 100 000` | at `n = 1 000 000` |
|---|---|---|---|---|
| 8 hex (today) | 2^32 | **77 163** distinct IDs | 68.8% | ≈100% |
| 12 hex (proposed) | 2^48 | **19 753 662** distinct IDs | 0.0018% | 0.177% |

12 hex is a 256× improvement and puts the 50% threshold three orders of magnitude above any
plausible user count for this board. **Honest caveat, to be recorded in the docstring:** RFC 2104
§5 recommends a truncated HMAC output be *"not less than half the length of the hash output … and
not less than 80 bits"*, i.e. 128 bits / 32 hex for HMAC-SHA-256. **48 bits is below that, and
deliberately so.** RFC 2104's rule exists to stop an attacker *forging a valid tag*; there is no
forgery surface here — no mask is ever accepted as an authenticator, and it must never become
one. The docstring and the spec line must therefore state plainly that the mask is a
**correlation identifier, never an authenticator**; that sentence is what makes 12 hex defensible
rather than merely convenient. If a future block ever needs the mask to *authenticate* anything,
12 hex is insufficient and the width must be raised then.

**Domain separation: not warranted (project rule 5).** There is exactly **one** keyed purpose
today, and BLOCK 14's second candidate was resolved *away* from a secret by Q-D5 (§0.6.1:
redact-for-the-key). HKDF subkeys would add a derivation module, a salt constant and a second
construction site to protect against a purpose that does not exist. Revisit only when a second
keyed purpose appears — and note the sequencing this argument depends on: the **independent**
secret is what makes that later change a one-line addition, whereas derivation from `SECRET_KEY`
would have made it retrofittable only by invalidating every mask already in the logs.

**Corrections the Implementor needs that the tables above do not carry** (all verified at
`7e800a3`; re-verify before editing):

- **Two hard-coded guard counts go stale.** `prod.py`'s own secret-bypass header comment says
  *"The eight secret guards below"*, and `config/settings/tests/test_deploy_check_env_parity.py`'s
  module docstring says *"Six guards raise `ImproperlyConfigured`, two … raise a bare
  `ValueError`"*. BLOCK 4 makes it the **ninth** skippable block and the **seventh**
  `ImproperlyConfigured`. Both comments must be corrected **in the same commit** as the guard —
  they are the only places in the repo that state the number, and a stale count is exactly the
  `VAL-008` failure mode this block exists to close.
- **`.github/workflows/ci.yml` `jobs.deploy-check.env` carries eleven variables today**, not
  twelve. `LOG_MASK_KEY` is the twelfth. It must be a non-empty, non-placeholder, non-`${{ }}`
  literal, or `test_deploy_check_env_parity.py` and the `deploy-check` job both go red.
- **`.env.test.example` must carry a non-placeholder value.** Unlike `DJANGO_SECRET_KEY` and
  `BOT_USERNAME`, which it already pins (`test-secret-key-for-testing-only`, `test-bot`), an empty
  or `<…>` `LOG_MASK_KEY` here would break every settings test that imports prod via the test
  environment. `.env.example` and `.env.prod.example` take the `<…>` placeholder shape (the guard
  rejects it, which is the point); `.env.dev.example` may be empty, as `BOT_TOKEN=` already is.
- **`sanitize.py` imports stdlib only today** — `hashlib`, `json`, `re`, `typing`. BLOCK 4 adds
  `hmac` and `from django.conf import settings`, making it Django-dependent for the first time.
  Module-level import follows the package's own precedent (`apps/core/utils/client_ip.py`,
  `migrate_locked.py`, `scheduler.py` all do it). **Zero occurrences of `LOG_MASK_KEY` exist
  anywhere in the repo today**, so this is net-new surface, not a modification.
- **The false claim has a fourth home the file table omits.** `test_sanitize.py`'s **module
  docstring** asserts "non-reversible SHA-256 hash" and cites **`PII-002`**, not `06-PII-112`. It
  must be rewritten with the test. `VAL-008` names only the spec line and the function docstring.

**Env-var contract acceptance criteria** (the settings tests enforce this in both directions;
enumerate, do not leave to the Implementor):

- `test_env_allowlist.py::test_example_keys_in_allowlist` — green for all four templates, so the
  `LOG_MASK_KEY` key must be in `ALLOWED_ENV_VARS`. *(Note: the test is named
  `test_example_keys_in_allowlist`; §0.6.3 item 15's `…in_allowlisted` is a typo.)*
- `test_env_allowlist_reverse.py::test_consumed_env_vars_are_allowlisted` — green; the new
  `env("LOG_MASK_KEY")` read in `base.py` is picked up by the whole-tree AST scan.
- `test_deploy_check_env_parity.py::test_deploy_check_env_block_imports_prod_settings` — green;
  the CI var must exist, be non-empty and be non-placeholder.
- `test_env_allowlist.py::test_bypass_flags_absent_from_env_templates` and
  `test_env_allowlist_reverse.py::test_env_example_points_at_the_tier_templates` — stay green;
  never place `DJANGO_BUILD`/`DJANGO_ONESHOT` near the new line, and **do not re-add a UTF-8 BOM**
  to `.env.example` (verified: all four templates currently start with `# E`, and that test
  asserts `not raw.startswith(codecs.BOM_UTF8)`).

**Rollback must remove the setting and the allowlist entry together.** A straight revert restores
the old construction and leaves `LOG_MASK_KEY` provisioned as an unused secret — harmless in
itself, but reverting only `base.py` while keeping the `ALLOWED_ENV_VARS` entry leaves a
hand-maintained contract with no reader, which is the anti-pattern
`test_env_allowlist_reverse.py`'s docstring exists to prevent.

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

**File surface (semantic units — the operation is named per file; never target a line number)**

| File | Operation | Symbol / target | Notes |
|---|---|---|---|
| `src/backend/apps/core/utils/sanitize.py` | **rewrite body + docstring, add two imports** | `mask_telegram_id`; the module import block | `hmac` + a module-level `from django.conf import settings` (precedent: `apps/core/utils/client_ip.py`, `migrate_locked.py`, `scheduler.py`). `VAL-008`: the docstring currently asserts "Non-reversible", which is false |
| `src/backend/config/settings/base.py` | **insert** after `SECRET_KEY`; **append** inside the `ALLOWED_ENV_VARS` frozenset's Python-consumed group | the new `LOG_MASK_KEY` setting; `ALLOWED_ENV_VARS` | **Most contended settings file in the repo** (phases 02 and 04). Append; never reorder another phase's annotated setting. Re-read immediately before editing — the file has grown a lot and this plan's line numbers are stale |
| `src/backend/config/settings/secret_validation.py` | **append** `validate_log_mask_key` after `validate_bot_username`; **amend** the module docstring | `validate_log_mask_key`; the module docstring | Phase-02 module; the docstring's classification note ("`BOT_USERNAME` is a public handle, not a secret") must gain a sentence saying `LOG_MASK_KEY` **is** a secret. **Re-read it immediately before editing** — it may have changed |
| `src/backend/config/settings/prod.py` | **append** a guard block after the `validate_bot_username` guard; **rewrite one count** in the bypass header comment | the new `LOG_MASK_KEY` guard; the `_SKIP_SECRET_VALIDATION` header comment ("The eight secret guards below") | Use `secret_validation.py`; do **not** invent a new mechanism. Exact `validate_bot_username` shape: `if not _SKIP_SECRET_VALIDATION:` / `validate_log_mask_key("LOG_MASK_KEY", LOG_MASK_KEY)  # noqa: F405` |
| `src/backend/config/settings/tests/test_log_mask_key_validation.py` | **new file** | the guard test | Shape of `test_bot_username_validation.py`; `_PROD_ENV_ALLOWLIST` + `_run_in_subprocess` from `test_prod_logging.py`. **Same commit as the guard** — a guard without its test is the finding, not the fix |
| `src/backend/config/settings/tests/test_deploy_check_env_parity.py` | **rewrite one sentence** in the module docstring | the "Six guards raise `ImproperlyConfigured`, two …" sentence | Becomes **seven** / **two**. Same commit as the guard |
| `.env.example`, `.env.dev.example`, `.env.prod.example`, `.env.test.example` | **insert** one `LOG_MASK_KEY=` line in **each** | one line per template | Both directions of `config/settings/tests/test_env_allowlist.py` fail without them. Per-template value shape is load-bearing — see the corrections list. **No BOM:** all four verified starting `# E` (bytes 35,32,46,101) |
| `.github/workflows/ci.yml` | **append** one key to the `deploy-check` job's `env:` block | `jobs.deploy-check.env` | **Eleven** vars today (`test_deploy_check_env_parity.py` imports prod with exactly this block); this is the twelfth. Never `DJANGO_BUILD` / `DJANGO_ONESHOT` here — either suppresses every guard and makes the job pass for no reason |
| `docs/01-spec/technical-specification.md` | **rewrite one parenthetical** in §F's PII-logging bullet | the `mask_telegram_id()` parenthetical `(SHA-256 hash, non-reversible, tg_ prefix)` | **Phase 06 holds the reservation** on this file. Replace "non-reversible" with the actual construction, say it is a correlation identifier and never an authenticator, and document the rotation trade-off (`VAL-008`). **Leave §F/§K's DECLINE wording alone** — that is BLOCK 2's surface and BLOCK 1's decision |
| `src/backend/apps/core/tests/test_sanitize.py` | **rewrite** the module docstring and `TestMaskTelegramId::test_mask_telegram_id_masks_int`; **add** the security-property test | the module docstring (cites `PII-002`); `test_mask_telegram_id_masks_int` | **Ships green today and fails by design** — docstring says length 13, the assertion says `len(result) == 11`. Rewrite asserts the **property**, never a width. The module docstring is a **fourth home** of the false claim that `VAL-008` does not name; it moves with the code |
| `src/backend/apps/users/tests/test_admin_pii_containment.py` | **no edit — read-only regression target** | its delegation assertion | Ten tests; four phase-04 `UserAdmin` form-contract tests. The delegation assertion (`"mask_telegram_id" in source`) survives unchanged. **Phase 04 owns part of this file. Do not touch it.** |

**Binding constraints**

1. The spec line and the docstring move **in the same commit** as the construction
   (`VAL-008`). A commit that changes the mask without them leaves a false security claim
   in the codebase; a commit that changes neither makes the false claim the finding. The
   **same rule covers `test_sanitize.py`'s module docstring**, which states the same false
   claim and cites `PII-002` rather than `06-PII-112`. All three move together.
2. **Do not chase the "13".** The test's docstring says 13, its assertion says 11. The
   rewrite asserts properties: the `tg_` prefix, the raw ID absent, the same input giving
   the same output, a *different* input giving a different output, and the raw value not
   recoverable by a small candidate sweep **without** the key. **Never assert a length.**
3. The `test_admin_pii_containment.py` delegation assertion (that the helper calls
   `mask_telegram_id`) **survives unchanged**. Assert on the delegation, never on the shape.
   **That file is not edited at all** — phase 04 owns part of it.
4. `LOG_MASK_KEY` must be **fail-fast in `prod.py`**, not defaulted to a public value.
5. Any env var added must land **with** its `ALLOWED_ENV_VARS` entry and its four template
   updates **in one commit**, and must satisfy phase 02's reverse-direction
   consumed↔allowlist test when that lands. The `ci.yml` `deploy-check.env` key lands in
   that same commit — it is the fifth half of the same contract, not a follow-up.
6. **The setting and its `ALLOWED_ENV_VARS` entry revert together.** Reverting `base.py`
   while keeping the allowlist entry leaves a hand-maintained contract with no reader —
   the exact anti-pattern `test_env_allowlist_reverse.py`'s docstring exists to prevent. If
   a rollback ever has to be partial, the **env templates and `ci.yml` revert first**.

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
  mask_telegram_id returns "tg_" plus the first 8 hex chars of an unsalted SHA-256 over
  str(telegram_id). The input domain is the ~2^34 space of Telegram IDs, so ANY deterministic
  function of it is invertible by exhaustive enumeration in seconds, at any output width, and
  the function docstring, the test module docstring and the technical specification all assert
  the opposite. Replace the construction with a keyed HMAC-SHA-256 truncated to 12 hex,
  provision an INDEPENDENT LOG_MASK_KEY behind a fail-fast prod.py guard, and correct every
  place that documents the mask in the same commit.
goals:
  - "make the mask unverifiable without the server key, so an enumeration of candidate IDs confirms nothing"
  - "keep the property the log stream depends on: same input -> same output, distinct inputs -> distinct outputs, tg_ prefix preserved"
  - "provision LOG_MASK_KEY across base.py, ALLOWED_ENV_VARS, all four .env templates and the ci.yml deploy-check block in ONE commit"
  - "correct all three false claims (function docstring, test module docstring, spec line) and state the rotation trade-off"
  - "ship the secret guard together with its test, so no placeholder key can reach production"
files:
  - path: "src/backend/apps/core/utils/sanitize.py"
    targets:
      - type: function
        name: mask_telegram_id
      - type: module
        name: sanitize
    semantic_anchors:
      replace_text_containing:
        type: literal
        value: 'f"tg_{hashlib.sha256(tid.encode()).hexdigest()[:8]}"'
      add_import:
        type: literal
        value: "import hmac"
      add_import:
        type: literal
        value: "from django.conf import settings"
  - path: "src/backend/config/settings/base.py"
    targets:
      - type: assignment
        name: SECRET_KEY
      - type: constant
        name: ALLOWED_ENV_VARS
    semantic_anchors:
      insert_after:
        type: assignment
        value: SECRET_KEY
      insert_into:
        type: frozenset_literal
        value: ALLOWED_ENV_VARS
        group_comment: "# --- Python-consumed"
  - path: "src/backend/config/settings/secret_validation.py"
    targets:
      - type: function
        name: validate_log_mask_key
    semantic_anchors:
      insert_after:
        type: function
        value: validate_bot_username
      replace_text_containing:
        type: literal
        value: "is a public Telegram handle, not a"
  - path: "src/backend/config/settings/prod.py"
    targets:
      - type: module
        name: prod
    semantic_anchors:
      insert_after:
        type: function_call
        value: validate_bot_username
      replace_text_containing:
        type: literal
        value: "The eight secret guards below"
  - path: "src/backend/config/settings/tests/test_log_mask_key_validation.py"
    targets:
      - type: module
        name: test_log_mask_key_validation
    semantic_anchors:
      new_file: true
      modelled_on: "src/backend/config/settings/tests/test_bot_username_validation.py"
  - path: "src/backend/config/settings/tests/test_deploy_check_env_parity.py"
    targets:
      - type: module
        name: test_deploy_check_env_parity
    semantic_anchors:
      replace_text_containing:
        type: literal
        value: "Six guards raise ``ImproperlyConfigured``"
  - path: ".env.example"
    targets:
      - type: file
        name: ".env.example"
    semantic_anchors:
      insert_after:
        type: line
        value: "BOT_USERNAME="
  - path: ".env.dev.example"
    targets:
      - type: file
        name: ".env.dev.example"
    semantic_anchors:
      insert_after:
        type: line
        value: "BOT_USERNAME="
  - path: ".env.prod.example"
    targets:
      - type: file
        name: ".env.prod.example"
    semantic_anchors:
      insert_after:
        type: line
        value: "BOT_USERNAME="
  - path: ".env.test.example"
    targets:
      - type: file
        name: ".env.test.example"
    semantic_anchors:
      insert_after:
        type: line
        value: "BOT_USERNAME="
  - path: ".github/workflows/ci.yml"
    targets:
      - type: mapping
        name: "jobs.deploy-check.env"
    semantic_anchors:
      insert_after:
        type: mapping_key
        value: "REDIS_URL:"
  - path: "src/backend/apps/core/tests/test_sanitize.py"
    targets:
      - type: module
        name: test_sanitize
      - type: class
        name: TestMaskTelegramId
    semantic_anchors:
      replace_text_containing:
        type: literal
        value: "Verifies that Telegram user IDs are masked with a non-reversible"
      replace_text_containing:
        type: literal
        value: "assert len(result) == 11"
  - path: "docs/01-spec/technical-specification.md"
    targets:
      - type: document_section
        name: "section F PII logging bullet"
    semantic_anchors:
      replace_text_containing:
        type: literal
        value: "(SHA-256 hash, non-reversible, `tg_` prefix)"
      edit_restricted_to:
        - "the mask parenthetical only - do NOT touch the DECLINE wording in section F or K (that is BLOCK 2's surface and BLOCK 1's decision)"
changes:
  - action: modify_code
    description: >
      Rewrite mask_telegram_id to a keyed HMAC-SHA-256 truncated to 12 hex, keeping the tg_
      prefix and the None -> "None" behaviour. Add `import hmac` and a module-level
      `from django.conf import settings`; the module is stdlib-only today, so this makes it
      Django-dependent for the first time (precedent: apps/core/utils/client_ip.py).
    code_hint: |
      import hashlib
      import hmac
      ...
      from django.conf import settings

      def mask_telegram_id(telegram_id: int | None) -> str:
          if telegram_id is None:
              return "None"
          tid = str(telegram_id)
          return f"tg_{hmac.new(settings.LOG_MASK_KEY.encode(), tid.encode(), hashlib.sha256).hexdigest()[:12]}"
  - action: modify_code
    description: >
      Rewrite mask_telegram_id's docstring (VAL-008). It must describe the ACTUAL
      construction, say the value is a correlation identifier and never an authenticator,
      justify 12 hex against RFC 2104 section 5's 80-bit floor, and state the rotation
      trade-off. The words "non-reversible" and "anonymised" must NOT appear.
    code_hint: |
      """Mask a Telegram user ID for safe logging.

      Keyed HMAC-SHA-256 over str(telegram_id), truncated to the first 12 hex
      characters, with a 'tg_' prefix. The KEY is what makes the value unusable to
      anyone who does not hold it: without LOG_MASK_KEY an attacker may enumerate
      candidate Telegram IDs but cannot confirm any of them.

      CORRELATION IDENTIFIER, NEVER AN AUTHENTICATOR. 12 hex is 48 bits, deliberately
      below RFC 2104 section 5's 80-bit floor for a truncated HMAC, because this mask
      is never accepted as proof of anything - it is written into logs and never
      checked against anything. If a future change needs it to authenticate, 48 bits is
      insufficient and the width must be raised then.

      Rotating LOG_MASK_KEY changes every value: old and new log lines stop being
      correlatable. Rotation is on suspected compromise, never on a schedule; a retained
      key means the value is pseudonymised, not anonymised.
      """
  - action: add_code
    description: >
      Insert the LOG_MASK_KEY setting in base.py immediately after SECRET_KEY with an empty
      non-prod default, and append "LOG_MASK_KEY" to the Python-consumed group of the
      ALLOWED_ENV_VARS frozenset. Empty default in non-prod is deliberate: a published
      default ships a false security property, and there is nothing at rest for a
      per-process random default to protect.
    code_hint: |
      # base.py, directly after `SECRET_KEY = env("DJANGO_SECRET_KEY")`
      # HMAC key for the Telegram-ID log mask (mask_telegram_id). Required in
      # production - guard-enforced in prod.py. Independent of SECRET_KEY on purpose:
      # reusing SECRET_KEY would give one leak two blast radii and no scoped revocation.
      LOG_MASK_KEY = env("LOG_MASK_KEY", default="")
  - action: add_code
    description: >
      Append validate_log_mask_key to secret_validation.py, reusing is_placeholder and adding
      a 32-byte length floor (RFC 2104 section 3's minimal recommended key length for
      SHA-256). Keep the messages value-free, and amend the module docstring: BOT_USERNAME
      is a public handle, LOG_MASK_KEY IS a secret.
    code_hint: |
      _MIN_LOG_MASK_KEY_BYTES: Final[int] = 32  # RFC 2104 section 3, SHA-256


      def validate_log_mask_key(var_name: str, value: str) -> None:
          """Fail fast when the log-mask key is missing, a template, or too short."""
          if not value:
              raise ImproperlyConfigured(
                  f"{var_name} must be set and non-empty in production. Generate one with "
                  "`python -c \"import secrets; print(secrets.token_hex(32))\"` and put the "
                  "real value in the .env.prod runtime file."
              )
          if is_placeholder(value):
              raise ImproperlyConfigured(
                  f"{var_name} appears to be a placeholder value from a .env template. "
                  "Replace it with the real value in .env.prod."
              )
          if len(value.encode()) < _MIN_LOG_MASK_KEY_BYTES:
              raise ImproperlyConfigured(
                  f"{var_name} must be at least {_MIN_LOG_MASK_KEY_BYTES} bytes (RFC 2104 "
                  "section 3). Generate one with "
                  "`python -c \"import secrets; print(secrets.token_hex(32))\"`."
              )
  - action: add_code
    description: >
      Append the prod.py guard in the exact validate_bot_username shape, and correct the
      bypass header comment's guard count in the same edit. Do NOT invent a new guard shape
      and do NOT reuse _validate_production_secret.
    code_hint: |
      # prod.py, after the BOT_USERNAME guard block
      if not _SKIP_SECRET_VALIDATION:
          validate_log_mask_key("LOG_MASK_KEY", LOG_MASK_KEY)  # noqa: F405
  - action: add_code
    description: >
      Insert one LOG_MASK_KEY= line into each of the four env templates, and append
      LOG_MASK_KEY: to the ci.yml deploy-check env block. The value SHAPE differs per file
      and is load-bearing. No BOM on any of the four (all currently start with "# E").
    code_hint: |
      .env.example        ->  LOG_MASK_KEY=<generate-a-random-32-byte-log-mask-key>   # guard rejects this
      .env.prod.example   ->  LOG_MASK_KEY=<generate-a-random-32-byte-log-mask-key>   # guard rejects this
      .env.dev.example    ->  LOG_MASK_KEY=                                            # may be empty, as BOT_TOKEN= is
      .env.test.example   ->  LOG_MASK_KEY=test-log-mask-key-for-testing-only-not-a-secret  # MUST be non-placeholder, >= 32 bytes
      .github/workflows/ci.yml jobs.deploy-check.env ->  LOG_MASK_KEY: ci-deploy-check-log-mask-key-not-for-production-use
  - action: modify_code
    description: >
      Rewrite test_sanitize.py's module docstring (it asserts "non-reversible SHA-256 hash" and
      cites PII-002), rewrite test_mask_telegram_id_masks_int to assert properties instead of
      a width, and add the security-property test.
    code_hint: |
      # module docstring
      """
      Unit tests for the mask_telegram_id sanitization utility.

      Verifies that Telegram user IDs are pseudonymised with a KEYED HMAC-SHA-256
      truncated to 12 hex before reaching log output (06-PII-112). The value is a
      correlation identifier, never an authenticator.
      """
  - action: modify_code
    description: >
      Rewrite the section F PII-logging parenthetical in docs/01-spec/technical-specification.md
      to describe the actual keyed construction, state that it is a correlation identifier and
      never an authenticator, and document the rotation trade-off. Edit that parenthetical only.
    code_hint: |
      - **PII logging:** All `telegram_id` values in logger calls and `stdout.write` output are
        masked via `mask_telegram_id()` (HMAC-SHA-256 keyed with `LOG_MASK_KEY`, truncated to the
        first 12 hex chars, `tg_` prefix) from `apps/core/utils/sanitize.py`. It is a
        **correlation identifier, never an authenticator** - it is written into logs and never
        verified against anything, so a lost `LOG_MASK_KEY` can re-derive a candidate ID from a
        mask. Rotating the key breaks correlation with all previously logged lines, so rotation
        is on suspected compromise only, never on a schedule. Raw telegram_id must never appear
        in logs.
  - action: add_code
    description: >
      Add src/backend/config/settings/tests/test_log_mask_key_validation.py, modelled on
      test_bot_username_validation.py, reusing _PROD_ENV_ALLOWLIST and _run_in_subprocess from
      test_prod_logging.py. A production settings module with a placeholder or missing
      LOG_MASK_KEY raises. Same commit as the guard.
    code_hint: |
      pytestmark = [pytest.mark.unit, pytest.mark.settings]

      # LOG_MASK_KEY is deliberately ABSENT from the allowlist, so no ambient value from
      # .env.test, os.environ or a developer's shell can reach the assertion.
      _PROD_ENV_ALLOWLIST = frozenset({...})  # same key set as test_bot_username_validation.py

      @pytest.mark.parametrize("value", ["", "<generate-a-random-32-byte-log-mask-key>", "short"])
      def test_log_mask_key_rejects_unusable_value_in_production(value: str) -> None:
          env = _prod_env(log_mask_key=value)
          result = _run_in_subprocess(env, _IMPORT_CODE)
          assert result.returncode != 0, (
              "an unusable LOG_MASK_KEY did not break the prod import - this test's "
              "harness cannot observe a failure, so the guard assertion is worthless"
          )
          assert "ImproperlyConfigured" in result.stderr
          assert "LOG_MASK_KEY" in result.stderr
acceptance_criteria:
  - "the mask is not reproducible without LOG_MASK_KEY, even for a small candidate sweep: with an empty or wrong key, no candidate ID's mask equals the real one"
  - "the tg_ prefix is preserved and the same input still gives the same output, and two distinct inputs still give distinct outputs"
  - "the docstring, the test module docstring and the spec line describe the ACTUAL construction, and the docstring and the spec line each say the value is a correlation identifier and NEVER an authenticator"
  - "no rewritten text asserts the mask is 'non-reversible' or 'anonymised'; the retained-key pseudonymisation semantics and the rotate-on-compromise-only policy are stated"
  - "all four env templates, the ALLOWED_ENV_VARS entry and the ci.yml deploy-check.env key move in the SAME commit as the setting"
  - "config/settings/tests/test_env_allowlist.py passes in both directions (test_example_keys_in_allowlist and test_python_consumed_vars_in_allowlist) and test_env_allowlist_reverse.py::test_consumed_env_vars_are_allowlisted passes"
  - "config/settings/tests/test_deploy_check_env_parity.py passes; the new ci.yml key is non-empty, non-placeholder and contains no ${{ }}"
  - "test_bypass_flags_absent_from_env_templates and test_env_example_points_at_the_tier_templates stay green; no UTF-8 BOM is re-added to any template"
  - "config.settings.prod raises ImproperlyConfigured for a missing, empty, placeholder or under-length LOG_MASK_KEY, and the new guard test ships in the same commit as the guard"
  - "the two hard-coded guard counts are corrected in the same commit: prod.py's bypass header comment and test_deploy_check_env_parity.py's module docstring"
  - "src/backend/apps/users/tests/test_admin_pii_containment.py passes UNCHANGED - the file is not edited, and its delegation assertion still holds"
  - "the settings setting and its ALLOWED_ENV_VARS entry are reverted TOGETHER on rollback, so the reverse-direction test's own anti-pattern (a hand-maintained allowlist entry with no reader) is never created; the commit body records the paired-revert order"
  - "the commit stages exactly the files named in `files`, explicitly by path - never `git add .`, never a revert of a concurrent phase's change"
tests_required:
  - id: mask_asserts_properties_not_width
    assertion: >
      test_sanitize.py::TestMaskTelegramId::test_mask_telegram_id_masks_int is rewritten to
      assert: the result starts with "tg_"; the raw decimal ID is absent from the result; the
      same input gives the same output; two distinct inputs give distinct outputs. It asserts
      NO length. The old assertion `len(result) == 11` and the "length == 13" docstring are
      both gone - do not "fix" the assertion to 15 and do not chase the 13.
  - id: mask_is_not_reproducible_without_the_key
    assertion: >
      A BEHAVIOUR assertion on the helper, not commentary about cryptography. Given a real
      mask and a small candidate list of Telegram IDs, and settings.LOG_MASK_KEY unset or
      replaced with a different value, no candidate's mask equals the real one; with the real
      key restored, the true candidate's mask matches and the others do not. This is the
      enumeration-defeat property the block exists for, and it is the test that would have
      failed on today's unsalted digest.
  - id: prod_guard_rejects_unusable_key
    assertion: >
      In src/backend/config/settings/tests/test_log_mask_key_validation.py, importing
      config.settings.prod with a missing, empty, <placeholder> or under-length LOG_MASK_KEY
      fails with ImproperlyConfigured and a value-free message naming the variable. The
      positive control (a well-formed key imports) must be present too, or a harness that
      cannot fail is indistinguishable from a passing one. Ships in the same commit as the
      guard.
  - id: no_regression_in_containment_and_login
    assertion: >
      apps/users/tests/test_admin_pii_containment.py passes UNCHANGED (all ten tests, file not
      edited) and apps/users/tests/test_login.py passes. test_login.py's raw-value-absence
      assertions plus its browser_binding length 64 / raw_token length 32 assertions are
      unrelated to the mask and must stay green untouched.
tests_to_run:
  - "src/backend/apps/core/tests/test_sanitize.py"
  - "src/backend/apps/users/tests/test_admin_pii_containment.py"
  - "src/backend/apps/users/tests/test_login.py"
  - "src/backend/config/settings/tests"
commands:
  setup: "$dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'"
  test: "$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS=\"src/backend/apps/core/tests/test_sanitize.py src/backend/apps/users/tests/test_admin_pii_containment.py src/backend/config/settings/tests --tb=short\" test"
  lint: "uv run ruff check src/backend/apps/core/utils/sanitize.py src/backend/config/settings/secret_validation.py"
  typecheck: "uv run basedpyright src/backend/apps/core/utils/sanitize.py"
  notes: >
    PYTEST_OPTS is unquoted in docker/entrypoint-test.sh, so each token is word-split on
    spaces, and setting it REPLACES the default pytest args (--reuse-db --tb=short
    --durations=10 -n auto --maxprocesses=4 --dist loadgroup) - a targeted run therefore
    loses xdist parallelism and DB reuse. Never use --override-ini=addopts=, which strips
    --import-mode=importlib. Never `uv run pytest` locally: there is no database on
    localhost:5432. Concurrent runs share one test_mko_bazuna: a mass
    ForeignKeyViolation on auth_permission / django_content_type, or "database
    test_mko_bazuna does not exist", is a contamination artefact - re-run serially before
    reporting a defect.
commit:
  message: "fix(core): pseudonymise the Telegram ID mask with a keyed HMAC (06-PII-112)"
  body_must_state:
    - "that Q-D8 is implemented as the Researcher's recommendation and is PENDING OWNER RATIFICATION: independent secret, fail-fast in prod, rotate on compromise only"
    - "that the mask is a correlation identifier and never an authenticator, and that 48 bits is deliberately below RFC 2104 section 5's floor for exactly that reason"
    - "that the value is pseudonymised, not anonymised, while the key is retained"
    - "that every derived masked value in existing log lines changes, and that old and new lines are no longer correlatable"
    - "that no mask value is stored anywhere - no model field, session, cache key or Redis key - so this is NOT a data migration and a key rotation is not one either"
    - "that the guard count in prod.py's header comment and in test_deploy_check_env_parity.py's docstring was corrected in this commit"
    - "that all four env templates, the ALLOWED_ENV_VARS entry and the ci.yml deploy-check.env key moved in the same commit, and that the setting and the allowlist entry revert together"
    - "that test_admin_pii_containment.py was not modified, and that the rewritten test asserts properties rather than a length"
    - "every citation cycle-scoped as 06-PII-1xx, never bare PII-1xx"
extra_context: |
  BINDING CONSTRAINTS (verbatim from the plan's BLOCK 4 section)

  1. The spec line and the docstring move **in the same commit** as the construction
     (`VAL-008`). A commit that changes the mask without them leaves a false security claim
     in the codebase; a commit that changes neither makes the false claim the finding. The
     **same rule covers `test_sanitize.py`'s module docstring**, which states the same false
     claim and cites `PII-002` rather than `06-PII-112`. All three move together.
  2. **Do not chase the "13".** The test's docstring says 13, its assertion says 11. The
     rewrite asserts properties: the `tg_` prefix, the raw ID absent, the same input giving
     the same output, a *different* input giving a different output, and the raw value not
     recoverable by a small candidate sweep **without** the key. **Never assert a length.**
  3. The `test_admin_pii_containment.py` delegation assertion (that the helper calls
     `mask_telegram_id`) **survives unchanged**. Assert on the delegation, never on the shape.
     **That file is not edited at all** — phase 04 owns part of it.
  4. `LOG_MASK_KEY` must be **fail-fast in `prod.py`**, not defaulted to a public value.
  5. Any env var added must land **with** its `ALLOWED_ENV_VARS` entry and its four template
     updates **in one commit**, and must satisfy phase 02's reverse-direction
     consumed↔allowlist test when that lands. The `ci.yml` `deploy-check.env` key lands in
     that same commit — it is the fifth half of the same contract, not a follow-up.
  6. **The setting and its `ALLOWED_ENV_VARS` entry revert together.** Reverting `base.py`
     while keeping the allowlist entry leaves a hand-maintained contract with no reader —
     the exact anti-pattern `test_env_allowlist_reverse.py`'s docstring exists to prevent. If
     a rollback ever has to be partial, the **env templates and `ci.yml` revert first**.

  WHAT IS NOT BUILT (the report's declined advisory)

  A global `logging.Filter` that "refuses any record argument named `chat_id`/`telegram_id`"
  is NOT built. It is a naming-convention guard, not a type system — it cannot see
  `user.chat_id` passed positionally — and it adds a global logging behaviour change to close
  two call sites. Negative ROI at this project scale. If the invariant is ever wanted, the
  durable form is a typed `Identity` value object, not a filter. BLOCK 5 is bound by this too.

  WHY THE KEY, NOT THE WIDTH

  The mask today is exactly `sha256(str(tid))[:8]` — a 32-bit truncated, unsalted digest over
  a ~2^34 input domain. Any deterministic function of that domain is invertible by exhaustive
  enumeration **regardless of output width**, so lengthening the hex prefix does not fix
  this. A keyed HMAC defeats the enumeration because without the key an attacker can
  enumerate guesses but cannot verify any of them. Collision maths, P(collision) ≈ n²/2N:
  8 hex (2^32) reaches 50% collision at ~77 163 distinct IDs (68.8% at 100 000, ≈100% at 1M);
  12 hex (2^48) at ~19 753 662 (0.0018% at 100 000, 0.177% at 1M). Keep the `tg_` prefix so
  existing log greps and the containment test's delegation assertion keep working.

  NO DOMAIN SEPARATION (project rule 5)

  There is exactly one keyed purpose today, and BLOCK 14's second candidate was resolved
  away from a secret by Q-D5 (redact-for-the-key). No HKDF, no subkeys, no salt constant -
  they would add a derivation module and a second construction site to protect against a
  purpose that does not exist. Revisit only when a second keyed purpose appears.

  FILE SURFACE DISCIPLINE

  Target semantic units, never line numbers. `base.py`, `prod.py`, the four env templates and
  `test_admin_pii_containment.py` are concurrent phases' surfaces: re-read each immediately
  before editing, stage explicitly, never `git add .`, never revert another phase's change
  (plan §1.3, §5.3). `secret_validation.py` and `test_deploy_check_env_parity.py` may have
  changed since the Researcher's pass; re-read them. docs/01-spec/technical-specification.md
  is reserved to phase 06 and BLOCKS 4/11/14 serialise on it - edit only the mask
  parenthetical, never section F's or K's DECLINE wording.
```

**Tests required** (logic and interaction, not implementation trivia; full assertions are in
the `tests_required` block of the task YAML above)

1. **Property, not width.** The rewritten `TestMaskTelegramId::test_mask_telegram_id_masks_int`
   in `src/backend/apps/core/tests/test_sanitize.py` asserts prefix, stability, injectivity on
   two distinct inputs, and raw-value absence. **It must not assert a length.** The old
   `len(result) == 11` and the "length == 13" docstring both go.
2. **The security property, as a test.** Given a mask and a candidate list, an attacker
   without the key cannot confirm a match; with the key they can. Written as a *behaviour*
   assertion on the helper, not as a commentary about cryptography — and it is the test that
   would have failed on today's unsalted digest.
3. **The secret-guard test.** A production settings module with a placeholder, empty, absent
   or under-length `LOG_MASK_KEY` raises `ImproperlyConfigured`, with a positive control so a
   harness that cannot fail is distinguishable from a passing one. New file
   `src/backend/config/settings/tests/test_log_mask_key_validation.py`, modelled on
   `test_bot_username_validation.py`. **Same commit as the guard.**
4. **Regression.** `test_admin_pii_containment.py` green **unchanged** (all ten tests, file not
   edited); `test_login.py` green — its raw-value-absence assertions and its `browser_binding`
   length 64 / `raw_token` length 32 assertions are unrelated to the mask and pin no shape.

**Risk and rollback**

- *Rollout:* **every** derived masked value in every historical log line, changelist and
  stored value changes. Old and new lines are no longer correlatable. This is the
  documented rotation trade-off, and it is why the spec edit is mandatory.
- *Regression risk:* the exact-width pin fails by design; it is rewritten here, not
  elsewhere. `test_admin_pii_containment.py` must **not** be touched to accommodate it.
- *Process risk (high):* `base.py`, `prod.py` and four env templates are phase-02's
  surface and the repo's most contended files. Re-read each immediately before editing;
  stage explicitly; never `git add .`; never revert a concurrent change (§1.3, §5.3).
- *Rollback:* a straight revert restores the old construction — and reverts the
  `base.py` setting **together with** its `ALLOWED_ENV_VARS` entry, because a surviving
  allowlist entry with no reader is the anti-pattern `test_env_allowlist_reverse.py` exists
  to prevent (binding constraint 6). If a partial revert is ever unavoidable, the four env
  templates and `ci.yml` go first. Any environment already provisioned with `LOG_MASK_KEY`
  then keeps an unused secret — harmless and documented, not a reason to avoid the rollback.
- *Not a migration, and this is the fact that makes the rollback cheap:* **not one** of the
  **14** call sites stores a masked value in a model field, a session, a cache key or a Redis
  key, so there is no data to backfill, no back-compat shim, and no dual-read window. The
  change is confined to log output and the settings surface.
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
| **Depends on** | the Q-D6 ownership decision — **recommended by the Researcher 2026-10-02 (option B, `account_state_q(prefix) -> Q` in `account_state.py`); coordinator to ratify, not to redesign** |
| **Blocks** | BLOCK 7 |
| **Priority** | **P0** — the live daily path is unguarded today |
| **Risk level** | **MEDIUM** — one declaration, no call-site change, but a wrong definition propagates to six sites and to a second phase |
| **Required agents** | **Auditor · Researcher · Planner · Validator** (all four — the shape and the owner are both open, and the declaration becomes a cross-phase contract) |

**Q-D6 — RESOLVED 2026-10-02 (Researcher). Ratify, do not re-open.**

**Recommendation in one paragraph.** Declare **one module-level factory that returns a
`Q`**, in `apps/users/services/account_state.py`, taking an optional relation prefix, and
consume it at all six sites. The decisive requirement is that the rule must be expressible
**once** and consumable from (a) a `User` queryset, (b) a `SavedSearch` queryset through its
`user` FK, and (c) an `Ad` queryset through **its owner's** `user` FK — because the
declined-seller half filters `Ad` by the *owner's* state, not the recipient's. A `Q` is the
only one of the three candidate shapes that serves all three **directly, from one
declaration, in one flag list**: `Q` is a *value*, `Q.__and__` returns a new `Q` (so it
composes with `is_active=True`, `status=PUBLISHED` and anything else), and a prefix argument
rewrites the same flag list into the right lookup for each relation — `is_deleted=False` from
`User`, `user__is_deleted=False` from `SavedSearch`/`Ad`. A `UserQuerySet` method can only
reach (b) and (c) through `user__in=`, which is a *different consumption route with its own
footgun* (a materialised list instead of the queryset is a silent N+1) and which cannot be
combined with the caller's own `Q` at all. The chosen shape is also the one that **cannot
degrade into a default-manager filter**: it is a pure function returning a value, is never
installed on a manager, and adds no `get_queryset()` override.

**Exact boolean expression (the whole rule — one dict literal, one function):**

```python
def account_state_q(prefix: str = "") -> Q:
    """The single account-state consent rule, as a filterable ``Q``.

    ``prefix`` is the ORM lookup prefix from the calling queryset to ``User``:
    ``""`` on a ``User`` queryset, ``"user__"`` on a model that reaches the owner
    through its ``user`` FK.
    """
    return Q(
        **{
            f"{prefix}is_deleted": False,
            f"{prefix}is_declined": False,
            f"{prefix}is_banned": False,
            f"{prefix}consent_revoked_at__isnull": True,
            f"{prefix}is_active": True,
        }
    )
```

Membership, conjunct by conjunct, and why:

| Conjunct | In? | Reasoning (evidence-based) |
|---|---|---|
| `is_deleted = False` | **yes** | Set by `withdraw_consent()` in the same `save()` as `consent_revoked_at`. `withdraw_consent()` no-ops when already set, so the pair is atomically consistent. The flag every existing account-state check reads (`get_account_state`, `AccountStateMiddleware`, the bot's `contact` docstrings). |
| `consent_revoked_at IS NULL` | **yes** | The finding names it separately, and `apps/core/services/contact.py::_check_seller_contactable` already filters on it. Currently redundant with `is_deleted` but **kept as the named consent signal**, not inferred from the soft-delete flag — that is what makes the predicate a *consent* rule rather than a soft-delete filter. |
| `is_declined = False` | **yes** | **Required by the ad-owner direction, which is why it is in the *recipient* predicate too.** The live site rule is exactly `user__is_declined=False` (`ListingsQuery`, `ads/views/listings.py` in both the detail and the media-gate paths), and BLOCK 7 must not let a declined seller's ad fan out. The validator struck the declined-*buyer* half as spec-consistent — that is a statement about **not citing it as a consent breach**, not a permission to keep messaging declined users; see the note below. |
| `is_banned = False` | **yes** | The validator weakened this to a **moderation** action and said "keep the filter". Kept, for three reasons: (i) `AccountStateMiddleware._evaluate_user_state` **denies every interaction** to a banned user, so leaving them in the alert audience makes the digest the one outbound channel that reaches an identity the bot itself blocks; (ii) one rule is simpler than two (project rule 5) — excluding it would force a second declaration and recreate the "second place to forget" that `VAL-003` exists to kill; (iii) it costs one conjunct on a boolean column. **Accepted cost, stated honestly:** in the **ad-owner** direction this also drops a *banned seller's* ad from digests while the site still shows it. That is a deliberate divergence in the safe direction and it must be named in the commit body, not discovered later. |
| `is_active = True` | **yes** | `User.is_active` (inherited from `AbstractUser`, indexed) is **never read or written** anywhere in non-test code — verified: the only `is_active` in production code is `SavedSearch.is_active` in the bot's alerts handler. It is included because it is the canonical Django deactivation switch, and omitting it would make the *first* future staff deactivation a leak of exactly this class. **This is the one conjunct with no current writer and it must be test-covered** so it is not mistaken for dead code. |
| `ads_auto_publish` | **NO — deliberately** | A *publishing* restriction, orthogonal to messaging. A consenting user with `ads_auto_publish=False` must still receive digests. Including it would also duplicate `is_declined` (which `decline_consent()` sets together with it) and would silently encode Q-D1's answer, which is a product decision. |
| `deleted_at` | **NO** | Redundant with `is_deleted`; one writer (`withdraw_consent`), one event. Two columns for one state is the drift risk this block removes. |
| `consent_given_at IS NOT NULL` | **NO — deliberately** | A *new* rule, not the same rule as `get_account_state`. It is not among the four flags the finding names, and it would shrink the audience by an amount this block cannot quantify before BLOCK 7 runs. Not this block's decision. |

**Note reconciling `is_declined` with the validator's narrowing.** The validator struck the
declined-**buyer** half because `technical-specification.md:101` does not forbid messaging a
browse-only visitor. That is a correction to the *characterisation* of the breach, not a
licence: BLOCK 7's acceptance criteria already require a declined recipient to appear at
none of the sites, and BLOCK 6 must not silently contradict BLOCK 7. The conjunct is
therefore present — required by the ad-owner direction regardless — and BLOCK 7 must **not**
describe declined-recipient suppression as a consent breach.

**Options, and why the rejected ones lose**

| Option | What it is | (a) `User` qs | (b) `SavedSearch` | (c) `Ad` by owner | Verdict |
|---|---|---|---|---|---|
| **A** | `UserQuerySet.eligible_for_outbound()` + a declared manager on `User`, consumed as `User.objects.<method>()` | ✅ direct | ⚠️ only via `user__in=<queryset>` | ⚠️ only via `user__in=<queryset>` | **Rejected.** Satisfies all three, but only by *indirection* — a second consumption route with a distinct footgun (passing `list(...)` instead of the queryset is a silent N+1 per call, and `find_matching_ads` is already called once per saved search). It also cannot be combined with the caller's own `Q`, so `SavedSearch.objects.filter(is_active=True, …)` becomes a two-step chain that reads worse than a single `Q`. It adds model surface (`User` currently declares **no** manager) for no capability the `Q` lacks. |
| **B** | `account_state_q(prefix="") -> Q` in `account_state.py` | ✅ `User.objects.filter(account_state_q())` | ✅ `filter(account_state_q("user__"))` | ✅ `filter(account_state_q("user__"))` | **SELECTED.** One declaration, one flag list, all three directions **directly**. `Q` is immutable and combinable (`q1 & q2`), which is precisely the property that lets one declaration serve both the recipient and the ad-owner direction. Matches the repo's existing idiom: a module-level `Q` consumed as a filter already ships in `currencies/management/commands/recompute_normalized_prices.py::_RECOMPUTE_PREDICATE`, and `Q` appears in production code in `listings_query.py`, `ads/views/listings.py`, `analytics/services/seller_stats.py` and others. Co-located with the instance-level `get_account_state()` it mirrors, which is what makes binding constraint 4 reviewable by eye. |
| **C** | **Forbidden** — a default-manager filter | — | — | — | **Hard prohibition.** See below. |

**Option C restated with its mechanism, because the plan's current wording names the
signature but not the failure.** `AccountStateMiddleware._resolve_user` does
`User.objects.get(chat_id=chat_id)` and returns `None` on `DoesNotExist`. A default-manager
filter would make that lookup miss for **every** withdrawn, declined, banned or deactivated
user, and `_evaluate_user_state` **fails open on `None`** — it returns `(True, "")`
("the handler's own gate rejects them"). The ban / deleted / consent-revoked gates would
therefore be silently **inverted from deny to allow**, for exactly the accounts they exist
to stop. That is a worse hole than the one this finding closes, and it is invisible to any
test that only exercises eligible users. `AccountStateMiddleware` must not be touched by this
block.

**Also forbidden:** implementing PII-104 by **nulling `chat_id`**. `AccountStateMiddleware`
resolves users by `chat_id` precisely so a withdrawn identity stays *blocked*; nulling it
re-opens a different hole and breaks `test_backfill_uses_stable_chat_id`.

**Semantics vs framework ownership (what phase 15 has to do).** Phase 06 owns the *flag list*
— what "consent-eligible" means. Phase 15 owns `AUTHZ-005`, the *framework* that enforces a
predicate across both processes. This shape leaves phase 15 room without a fork: the factory
is a pure value producer, so phase 15 adds `account_state_q() & authorisation_q(...)` at the
call site — no edit to `account_state.py`, no second flag list. Concretely, phase 15 must
(a) **not** re-declare the five flags anywhere, (b) **not** install a default filter (the
`_resolve_user` inversion above applies to it too), and (c) wrap, not replace, the
declaration. If phase 15 needs a *different* flag set for a *different* boundary, that is a
second named factory beside this one, not an edit to this one.

**Cross-phase fact to publish (one line):** a single declaration —
`apps.users.services.account_state.account_state_q(prefix)` — now drives **all six** alert
sites; changing it moves all six, and that is proven by a test that mutates the declaration
and observes every site change together.

**File surface (semantic units)** — option **B** selected; **`User` is NOT touched**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/users/services/account_state.py` | the `account_state_q(prefix="") -> Q` declaration, placed after `get_account_state` | The only production file this block edits. `from django.db.models import Q` is the only new import — the module's existing `apps.users.models` import is untouched, so its own import surface does not grow |
| `src/backend/apps/users/services/__init__.py` | add `account_state_q` to the re-export block and to `__all__`, **only if** BLOCK 7 imports it from the package | Prefer the fully-qualified `from apps.users.services.account_state import account_state_q` (the form `telegram_bot/middlewares/permissions.py` already uses). See binding constraint 4 |
| `src/backend/apps/users/tests/test_account_state.py` | new queryset-level tests | Existing module; the instance-level matrix must stay green **unchanged** |
| `src/backend/apps/users/tests/test_account_state.py` | a **fresh-interpreter import probe** for the `search → users` edge | New. Follows `_run_in_subprocess` from `config/settings/tests/test_prod_logging.py`, the repo's existing subprocess-import idiom. See binding constraint 3 |

**`src/backend/apps/users/models.py` is deliberately absent.** `User` declares no custom
manager and no `QuerySet` subclass today, and option **B** keeps it that way: no
`Meta.default_manager_name`, no `objects = UserManager.from_queryset(...)`, no
migration. If the implementor finds themselves editing `models.py`, the wrong option was
chosen.

**Binding constraints**

1. **No default-manager filter.** Ever. If a design appears to need one, that is evidence
   the declaration is in the wrong place. Concretely: no `get_queryset()` override, no
   `Meta.default_manager_name`, no custom manager on `User`. The chosen shape is a pure
   function returning a `Q` — it is never installed on anything, so it has no mechanism by
   which to become a default filter. The named casualty if this is ignored is
   `AccountStateMiddleware._resolve_user`, whose `None` path **fails open**.
2. The predicate must be **testable without a request and without a `User` instance**.
3. **Import-cycle constraint — the previous version of this constraint was factually
   inverted and is replaced.** It claimed *"`apps/search` already imports from `apps/users`"*.
   It does not. In `apps/search`'s **production** code the entire `apps.users` surface is
   **one function-local, deferred import** — `from apps.users.models import User` inside
   `send_alerts.Command._send_user_digests`. Every other `apps.users` reference under
   `apps/search/` is test-only. Consuming the predicate therefore creates a **new
   module-level `search → users` edge** in two files phase 03 also owns.
   **Verified, not assumed** (Researcher, 2026-10-02, two independent methods):
   - *Static closure over the whole source tree* (`ast`, module-scope imports, relative
     imports resolved, package `__init__`s included): the transitive closure of
     `apps.users.services.account_state` is **22 modules** and contains **none** of
     `apps.search.services.alert_query`, `…management.commands.send_alerts` or
     `…services.immediate_alerts`. A cycle requires the new node to be reachable from
     itself; it is not.
   - *Live*, in the running container, with the new import line **actually injected** into
     each of the three consumer modules (a source-patching loader, bytecode cache bypassed,
     `apps.users.admin` stubbed so `django.setup()` does not warm the chain first): all
     three import successfully, the chain is pulled in exactly as predicted, and **no
     consumer is re-entered mid-execution** — i.e. no partially-initialised-module
     failure.
   - **The back-edge that makes this fragile, and the real hazard:** the closure includes
     **`apps.search.services.cache`**, because `apps/users/services/__init__.py` re-exports
     `deletion`, which does `from apps.search.services.cache import bump_search_cache_version`.
     So there is already a **package-level `apps.search.services ← apps.users.services`
     edge**. It is survivable today only because `apps/search/services/__init__.py` contains
     nothing but `default_app_config`. **Constraint: `apps/search/services/__init__.py` must
     stay import-free.** If it ever gains a submodule import, the loop closes
     (`alert_query` → `users.services` → `deletion` → `search.services.cache` →
     `search.services.__init__` → `alert_query`) and the entire alert path fails to import.
     Test 3 below is the tripwire for exactly this.
4. The predicate must be **imported from the `account_state` module path**, not from the
   `apps.users.services` package, by `apps/search`. Importing the package executes
   `__init__.py` and drags `deletion` → `apps.search.services.cache` →
   `apps.ads.services.listings_query` (and its pydantic schemas, categories, locations,
   lookups, media and currencies) into the alert path's import graph. That chain is **already
   loaded in both processes today** — the web process via admin autodiscovery
   (`apps/users/admin.py` imports `withdraw_consent`), the bot via
   `telegram_bot/middlewares/permissions.py` — so the cost is zero at runtime, but the
   narrower import keeps the *declaration* honest and leaves the graph one refactor safer.
   `telegram_bot/middlewares/permissions.py` already uses the fully-qualified module form.
5. `get_account_state(user)` and the queryset predicate must be **provably the same rule**.
   A test that constructs a user in every state and asserts the queryset agrees with
   `get_account_state` is the only thing that prevents the drift this finding exists to
   stop. Note the honest limit: `get_account_state` has no `is_active` term, so the
   cross-check asserts agreement on **every state that `get_account_state` can express**,
   plus `is_active=False` as a predicate-only case with its own assertion.
6. **This block does not change any call site.** BLOCK 7 does that. If
   `alert_query.py`, `immediate_alerts.py` or `send_alerts.py` is edited here, the block has
   run ahead.
7. **Never pass `user__in=list(...)`.** If BLOCK 7 ever prefers the subquery route, it must
   pass the **queryset**. Both routes return identical rows here — `SavedSearch.user` and
   `Ad.user` are non-nullable FKs, so the `Q`-join's `INNER JOIN users` cannot drop anything —
   but a materialised list is a silent N+1 inside `find_matching_ads`, which already runs
   once per saved search.

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
  Declare ONE module-level factory account_state_q(prefix) -> Q in
  apps/users/services/account_state.py, per the Q-D6 decision recorded above (option B,
  recommended by the Researcher 2026-10-02, coordinator to ratify). No manager, no
  QuerySet subclass, no default filter, and no change to any call site.
goals:
  - "give the alert paths one reusable eligibility declaration"
  - "guarantee the queryset predicate and get_account_state are the same rule"
  - "leave the declaration consumable from a User queryset, a SavedSearch queryset and an Ad queryset via its owner's user FK"
files:
  - path: "src/backend/apps/users/services/account_state.py"
    targets:
      - type: module
        name: account_state
      - type: function
        name: get_account_state
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
      Add account_state_q(prefix: str = "") -> Q returning the five-conjunct rule
      documented in the decision above. Add a cross-check test asserting the queryset
      result agrees with get_account_state for every account state, a prefix test proving
      the same flag list resolves from a User queryset and from a SavedSearch queryset via
      its user FK, and the fresh-interpreter import probe for the search -> users edge.
    code_hint: |
      def account_state_q(prefix: str = "") -> Q:
          """The single account-state consent rule, as a filterable ``Q``.

          ``prefix`` is the ORM lookup prefix from the calling queryset to
          ``User``: ``""`` on a ``User`` queryset, ``"user__"`` on a model that
          reaches the owner through its ``user`` FK. Mirrors
          ``get_account_state()`` - see BLOCK 6 for the per-conjunct rationale.
          """
          return Q(
              **{
                  f"{prefix}is_deleted": False,
                  f"{prefix}is_declined": False,
                  f"{prefix}is_banned": False,
                  f"{prefix}consent_revoked_at__isnull": True,
                  f"{prefix}is_active": True,
              }
          )
acceptance_criteria:
  - "the predicate is a named declaration, not a copy at a call site"
  - "no default manager filter, custom manager or get_queryset override was introduced on User, and models.py was not edited"
  - "for every account state the queryset agrees with get_account_state"
  - "the same declaration resolves from a User queryset and from a SavedSearch/Ad queryset via the user__ prefix"
  - "a fresh-interpreter probe proves apps.search.services.alert_query still imports with the new search -> users module-level edge"
  - "no alert call site was changed in this block"
tests_to_run:
  - "src/backend/apps/users/tests/test_account_state.py"
  - "src/backend/apps/search/tests/test_alert_query.py"
  - "src/backend/apps/search/tests/test_send_alerts.py"
  - "src/backend/apps/search/tests/test_send_alerts_daily.py"
  - "src/backend/apps/search/tests/test_immediate_alerts.py"
  - "src/backend/apps/search/tests/test_alert_delivery.py"
  - "src/telegram_bot/tests/test_account_state_middleware.py"
```

**The six sites this declaration drives (BLOCK 7 consumes all of them; this block touches none)**

| # | Site | Current selection |
|---|---|---|
| 1 | `send_alerts.Command._collect_alerts` | `SavedSearch.objects.filter(is_active=True).select_related("user", "city", "category")` |
| 2 | `send_alerts.Command._dry_run_check` | `SavedSearch.objects.filter(is_active=True).select_related("user")` |
| 3 | `alert_query.find_matching_saved_searches` | `SavedSearch.objects.filter(is_active=True).select_related("user", "city", "category")` — its own docstring already pre-declares the gap and cites PII-104 / phase 06 |
| 4 | `alert_query.find_matching_ads` | bare `Ad.objects.filter(status=AdStatus.PUBLISHED)` — **no** `user__is_declined=False` |
| 5 | `send_alerts.Command._send_user_digests` | soft gate `if not user.chat_id:` → log and skip. **Retained** — a delivery precondition, not a consent gate |
| 6 | `immediate_alerts._build_payload` | soft gate `if not user.chat_id:` → return `None`, plus a verbatim `"chat_id": user.chat_id` in the payload (BLOCK 5's masking subject). **Retained** |

Sites 1–4 are the *recipient/ad-content selection* sites that consume the predicate
(`account_state_q("user__")` from `SavedSearch`/`Ad`). Sites 5–6 are **not** predicate
sites: they must keep the `chat_id` precondition and must **not** be mistaken for, or
rewritten into, consent gates.

**Tests required**

1. **Cross-check test** — for each state (active, declined, withdrawn, banned, deleted,
   combinations), `User.objects.filter(account_state_q())` and
   `get_account_state(user)` agree; plus a predicate-only case for `is_active=False`.
   This is the anti-drift tripwire and the most valuable test in the block.
2. **Prefix / composition** — the *same* declaration resolves from a `User` queryset and
   from a `SavedSearch` queryset through `user__`, and composes into an existing chain
   without changing that chain's meaning (`SavedSearch.objects.filter(is_active=True)` plus
   `.filter(account_state_q("user__")).select_related(...)`). Also assert
   `account_state_q() & Q(...)` composes, since that is the property phase 15 will rely on.
3. **Fresh-interpreter import probe** — using `_run_in_subprocess` from
   `config/settings/tests/test_prod_logging.py`, run `django.setup()` then
   `import apps.search.services.alert_query` in a **new process** and assert exit 0. A cycle
   only reproduces in a cold interpreter, so an in-process test cannot see it. This is the
   tripwire for binding constraint 3's `apps/search/services/__init__.py` freeze. Keep it
   cheap: one subprocess, one import.
4. **No request, no instance** — the predicate is exercised with no `HttpRequest` and no
   `User` in scope.
5. **Test-isolation note for BLOCK 7, carried forward:** per-state tests must create their
   **own** user, not mutate the shared `seller` / `user` / `buyer` fixtures. Those fixtures
   use `get_or_create` keyed on a fixed `telegram_id`, so they are shared across xdist
   workers and survive `--reuse-db`; a stale mutated row from an interrupted run would make
   a per-state test flaky in exactly the way this block cannot debug.
6. **Regression** — `test_account_state.py`'s existing `can_login` / `can_publish_ad` /
   `get_state_badge` matrices pass **unchanged**, including
   `test_declined_user_can_publish` (which BLOCK 8 option (a) must preserve), and the five
   alert modules in `tests_to_run` stay green (see the inventory below — none of them pins
   the unfiltered audience, so all five should pass untouched).

**Test-blocker inventory (Researcher, verified file-by-file — there are none)**

No existing test pins the unfiltered alert audience, so **BLOCK 7 needs no test rewrites**
and BLOCK 6's own regression surface is clean. Evidence:

- `test_alert_query.py` — every `TestFindMatchingAds`, `TestFindMatchingSavedSearches`,
  `TestSendAlertsCommand` and `TestDeliverImmediateAlerts` case builds its `Ad` from the
  `seller` fixture and its `SavedSearch` from the `buyer` fixture. Both fixtures are created
  by `User.objects.get_or_create(telegram_id=…)` with `defaults` that set **no** state flag,
  so every row carries the model defaults: `is_banned=False`, `is_deleted=False`,
  `is_declined=False`, `consent_revoked_at=None`, `is_active=True`. All five conjuncts
  evaluate true; the new filter is a no-op for them. The two
  `test_dry_run_excludes_inactive_searches` / `test_excludes_inactive_searches` cases pin
  `SavedSearch.is_active` semantics only and are unaffected.
- `test_send_alerts_daily.py` — same `seller` / `buyer` fixtures; `User.objects.aget` is
  patched to return `buyer`.
- `test_send_alerts.py` — `pytestmark = [pytest.mark.unit]`, and `_send_user_digests` is
  driven with `MagicMock` users (`_make_mock_user`). It never touches the recipient
  queryset, and it must keep doing so: if BLOCK 7 makes `_send_user_digests` query users
  through the predicate, these `MagicMock`-based cases break. **BLOCK 7 must leave
  `_send_user_digests`' user lookup alone** — the `chat_id` gate is sufficient there because
  collection is already gated upstream.
- `test_immediate_alerts.py` — exercises `_run_send` / `_build_payload` / `build_alert_message`
  with hand-built payload dicts and mocks; no recipient queryset.
- `test_alert_delivery.py` — `mark_delivered` / backfill; orthogonal.

The real blocker is **documentation, not tests**: `find_matching_saved_searches`'s docstring
currently asserts the opposite of the fix — *"The recipient predicate below (`is_active` +
city/price/category/FTS) is the audience definition and is NOT touched … (PII-104, phase
06)"*. BLOCK 7 must rewrite that docstring in the same commit; leaving it would make the
code and its own contract disagree.

**Risk and rollback**

- *Risk:* a default filter sneaks in as "simplification". Mitigation: binding constraint 1
  and 4, three acceptance criteria, and the named casualty — `_resolve_user` returning
  `None` makes `_evaluate_user_state` **fail open**, inverting the ban / delete / revoke
  gates from deny to allow.
- *Risk:* the predicate's membership drifts from `get_account_state`. Mitigation: test 1.
- *Risk (new, from the verification):* `apps/search/services/__init__.py` gains an import and
  closes the `search → users → search.services.cache` back-edge, breaking the alert path's
  import. Mitigation: binding constraint 3 + test 3. This is a **latent** hazard — verified
  absent today by two independent methods — and it is the one thing this shape costs.
- *Rollout:* none for this block; no call site consumes the declaration yet, so the recipient
  count does not move until BLOCK 7 lands. BLOCK 7 *is* the rollout: the audience shrinks by
  exactly the withdrawn / declined / banned / deactivated owners, and on a small board that
  can be visible. State the expected delta in the BLOCK 7 commit body rather than letting a
  smaller digest be read as a regression. Note also that `withdraw_consent()` does **not**
  deactivate `SavedSearch` rows today (audit recommendation 3 — `SavedSearch.objects
  .filter(user=user).update(is_active=False)` — is not in this plan), so the predicate is the
  *only* thing standing between a withdrawn user and 30 further days of digests.
- *Rollback:* a straight revert; no data, no schema, no migration.
- *Cross-phase:* the **single most contested declaration in the plan**. Phase 15's
  `AUTHZ-005` shares this predicate's semantics. §5.6 states the handoff; the semantics /
  framework split and what phase 15 must not do are stated in the Q-D6 resolution above.

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
| **Depends on** | **BLOCK 3** (landed — the inventory declares the `preferred_city` entry this block makes true), **BLOCK 7** (landed — the eligibility rule this teardown mirrors) and **BLOCK 8** (serial predecessor — it owns `views/consent.py` and may have edited `decline_consent`, so this block **re-reads both before editing**) |
| **Blocks** | BLOCK 10 (**the sole subsequent writer of `withdraw_consent`'s body**), BLOCK 11, BLOCK 13, BLOCK 14 |
| **Priority** | P1 |
| **Risk level** | **MEDIUM** — changes the withdrawal transaction and the published policy text |
| **Required agents** | **Auditor · Researcher · Planner · Validator** (all four — it is the first edit to the erasure transaction) |
| **Open decisions** | **None.** **Q-D10 is RESOLVED** (see below). Q-D1 (DECLINE reversibility) stays with the coordinator; nothing here depends on it |
| **Spec edit** | **Yes** — `docs/01-spec/technical-specification.md` **§F** (the "Post-withdrawal erasure" bullet list) and **§G** (the "Preferred city (Plans 17/23)" bullet). **Two bullets, nothing else**, in the same commit as the code. BLOCKS 4 / 11 / 14 take *other* bullets, so the file-level contention is settled by commit order, not by a lock |

**What is in scope here, and what is not.** `withdraw_consent`'s `update_fields` list is
exactly nine columns today (`consent_revoked_at`, `is_deleted`, `deleted_at`,
`consent_given_at`, `telegram_id`, `username`, `first_name`, `last_name`, `email`) and
`decline_consent`'s is three (`ads_auto_publish`, `is_declined`, `consent_given_at`) — both
re-verified 2026-10-02. This block adds the **withdrawal-time teardown of subscriber
state**, the `preferred_city` clearing on both states, the **three restore paths** that
make the clearing durable, and the rewrite of `privacy.html` §6. It **widens this block's
surface into a second app** (`apps/search/views/preferred_city.py`) and into
`apps/users/views/consent.py`; neither was in the block's original file list. The
`ConsentRecord` fingerprint retention is **not** here — it is BLOCK 15's, so that one sweep
and one TTL close both.

**`chat_id` is retained, deliberately, and the block must say so in the copy.** The tree
documents it: `User.chat_id.help_text` reads *"Stable Telegram chat ID; set on first bot
contact, never nullified"*, and `AccountStateMiddleware._resolve_user` does
`User.objects.get(chat_id=chat_id)` with a docstring stating the reason — *"so that
withdrawn/deleted users (whose telegram_id is nulled by GDPR erasure) are still found."*
**Nulling `chat_id` is forbidden.** The defect is that the retention is unreconciled
against the published promise, and that it is the mechanical reason BLOCK 7 was needed.

**Q-D10 — RESOLVED 2026-10-02 (Researcher). This plan's premise was inverted; the
nulling does not survive on its own.**

The text this block originally carried asserted that the `preferred_city` **cookie** is
deleted on decline, "so the nulling should hold". Every load-bearing claim in that
sentence was re-verified against the tree, and it is false in three independent ways:

1. `consent_decline` computes
   `preferences = submission.preferences if submission and "preferences" in request.POST else True`
   — **the default is `True`** — and `_set_consent_cookies` deletes the cookie only
   `if not preferences`. So the *common* decline keeps the `preferred_city` cookie for a
   year with `consent_preferences == "true"`, and the next login-claim restores the
   column. `tests/test_consent.py::TestConsentDeclineView::test_decline_sets_declined_cookie`
   pins exactly this (`assert response.cookies["consent_preferences"].value == "true"`,
   comment: *"Preferences remain available even on decline (PO-02)"*).
2. `apps/search/views/preferred_city.py::set_preferred_city` writes
   `User.preferred_city` **unconditionally** for an authenticated buyer — it gates only
   the *cookie* on `consent_preferences`. A declined user clicking a city in the header
   re-sets the column with no reconcile involved. **This is a second app's view, so it
   joins this block's surface.**
3. `delete_cookie()` **cannot clear a `Secure` cookie over HTTPS** in Django 5.2 —
   `Secure` is emitted only for `__Host-` / `__Secure-` prefixed names or
   `samesite="none"`, and `preferred_city` is neither. The repository already documents
   this defect and works around it in `set_preferred_city`'s clear branch by emitting an
   expired cookie directly.

**The resolved end state: the clearing is durable, and re-acceptance is a new consent.**
Clearing is *not* terminal — `give_consent` already sets `is_declined=False`, after which
the header write and the login reconcile may legitimately set the column again. So the
column must be cleared on decline and on withdrawal, and every path that could restore it
while consent is declined must be closed. `give_consent` needs **no** change.

**The four-change durability chain — all four are required; none is optional**

| # | Change | File / symbol |
|---|---|---|
| (i) | Delete the `preferred_city` **cookie** whenever the choice is `DECLINED`, not only when `preferences` is falsy — and do it with a **hand-rolled `secure=True` expiry**, not `delete_cookie()` | `apps/users/views/consent.py::_set_consent_cookies` |
| (ii) | Gate the **DB write** on `is_declined` (the cookie gate is not enough) | `apps/search/views/preferred_city.py::set_preferred_city` |
| (iii) | Reconcile guard `if user.is_declined: return` — **in `views/consent.py`, on `_reconcile_preferred_city_on_login`, not on `login_status`** | `apps/users/views/consent.py::_reconcile_preferred_city_on_login` |
| (iv) | `preferred_city` added to the **existing** `update_fields` of `decline_consent` and `withdraw_consent` — **no new transaction** | `apps/users/services/deletion.py` |

Change (iii) belongs on `_reconcile_preferred_city_on_login` — this is a *reconcile* rule,
not a login rule, and `login_status` is outside every block's declared surface here. Change
(ii) gates on the plain `is_declined` attribute, not on BLOCK 6's
`account_state_q()`: `set_preferred_city` is in the `search` app, and pulling
`users.services.account_state` into a view for a single boolean adds a cross-app import
and a second spelling of the account-state rule for no gain. `is_declined` is also the
exact term `test_deletion.py` and the listing filters already use.

**BLOCK 8 is this block's serial predecessor and shares two files.** BLOCK 8 owns
`apps/users/views/consent.py` (the three consent views plus a new `consent_resume`) and may
make "the minimal state change" to `deletion.py::decline_consent` / `give_consent` that its
mechanism needs, and it owns `privacy.html` **§7** — not §6, which is this block's. Therefore:
**re-read `apps/users/views/consent.py` and `deletion.py::decline_consent` immediately
before editing**, expect `decline_consent`'s `update_fields` to be **four** columns rather
than three, and **do not touch `privacy.html` §7**. If BLOCK 8 did not land, this block's
`_set_consent_cookies` edit is still safe, but BLOCK 8's own tests must be re-run after it
lands.

**The `preferred_city` cookie deletion must mirror the *write's* attributes, not the
request's.** `_set_consent_cookie` writes every consent cookie with
`secure=True` unconditionally (D-COOKIES), so the deletion must be `secure=True` too —
**not** `request.is_secure()`. Over plain HTTP the consent cookie was never stored, so
there is nothing to delete; mirroring the write is the only self-consistent choice.

**The kept half — the two changes that are the finding's own recommendation**

1. `SavedSearch.objects.filter(user=user).update(is_active=False)` inside the withdrawal
   transaction — revocation actively tears down subscriber state rather than relying on a
   future filter.
2. `SearchHistory.objects.filter(user=user).delete()` in the same transaction (rows are
   `CASCADE`-only today, so they survive DECLINE indefinitely and WITHDRAW for the full
   30 days). This discharges part of `06-PII-108`'s retention question; BLOCK 14 fixes the
   *write* path, which is a different concern.
3. `privacy.html` **§6** is rewritten to enumerate what is erased, what is retained and
   **why**, replacing the blanket *"All personal data is permanently erased within 30 days
   of withdrawal."*

**The import assessment — `users → search.models`. Answer: import the models directly.**

`deletion.py` would need `SavedSearch` and `SearchHistory`, which live in
`apps/search/models.py`. Four options were weighed against the tree:

| Option | Verdict |
|---|---|
| **(a) `from apps.search.models import SavedSearch, SearchHistory` in `deletion.py`** | **CHOSEN.** No cycle: `apps/search/models.py` imports only `secrets`, `django.db.models` and `apps.core.enums.AdSource` (verified — the module has no `apps.users` import), and it refers to its foreign keys as **lazy string labels** (`"users.User"`, `"locations.City"`, `"categories.Category"`), so there is **no** `apps.users` import for this edge to close through. At runtime the cost is **zero** — `apps.search` is an installed app, so `django.setup()` already imports `search.models` in both the web and bot processes before any consumer runs. It is the smallest, most obvious code (project rules 4 and 5), and it adds no new **app-level** dependency: `deletion.py` already imports `apps.search.services.cache`, so a package-level `apps.users.services ← apps.search.services` back-edge already exists, is documented, and is frozen by BLOCK 6's binding constraint 3 |
| (b) pass the querysets in as parameters | Rejected. It changes `withdraw_consent`'s signature, and BLOCKS 10, 11 and 13 all re-edit this function in sequence — signature churn handed to three downstream blocks to avoid one import line is the wrong trade |
| (c) a new `apps/search/services/*.py` teardown helper called from `deletion.py` | Rejected as the default: it creates a module whose only consumer is one call site, widens `deletion.py`'s dependency to two `search` modules, and needs its own test file. Permitted **only** as a documented deviation, and then the new module must be a plain submodule — **`apps/search/services/__init__.py` must stay import-free** (BLOCK 6 binding constraint 3, pinned by BLOCK 6's fresh-interpreter import probe) |
| (d) defer to BLOCK 14 | Rejected. BLOCK 14 owns the *write path* for `SearchHistory.query_normalized`; row deletion on withdrawal is `06-PII-110`'s own recommendation 3 and is named in this block's scope. Deferring leaves the rows surviving DECLINE indefinitely and WITHDRAW for the full 30 days — the finding itself |

**This block does not add `search.SearchHistory` to the inventory.** Adding the model to
`REVIEWED_NON_IDENTITY_COLUMNS` would put BLOCK 3's reviewed-column shape in conflict with
BLOCK 14, which is re-deriving exactly `SearchHistory.query_normalized`. **Route it:
BLOCK 14 adds `search.SearchHistory` to the inventory** with its post-redaction entries.
`search.SavedSearch` is already listed, and its `is_active` is already in
`REVIEWED_NON_IDENTITY_COLUMNS`, so the bulk teardown trips nothing.

**The inventory `implemented` flag — a reason-string question, not a data field.**
`PII_ERASURE_ENTRIES` is a tuple of `(model_label, column, action, reason)`; **there is
no `implemented` field, and BLOCK 3's own task text says so explicitly** ("`implemented`
below is NOT a field of the declared 4-tuple — it tells the Implementor what the REASON
STRING must say"). Re-verified against `apps/users/services/test_pii_inventory.py`: the
guard asserts on `action` plus **reason substrings**, and it asserts nothing about
`preferred_city`'s reason at all — `test_user_chat_id_is_a_declared_retain` covers
`chat_id` only, and `test_retained_free_text_entries_name_their_owning_block` does not
list `preferred_city`.

So: **keep the tuple shape, keep `ErasureAction.NULL`, and rewrite the `preferred_city`
reason** from *"NOT implemented today … owned by BLOCK 9"* to a statement that it is
implemented and by which change. **The tuple shape and the action must not change** — a
new field would be a second hand-maintained list (Q-D9's rejected option) and would break
the module's stdlib-only, `apps.*`-free import property. This is a strictly safe edit and
the guard stays green either way; state it in the commit body so the next reader does not
re-open the question.

**Function-body ownership with BLOCK 10 — one block owns the body.**
BLOCK 10 moves the `ConsentRecord` write **inside `withdraw_consent`'s existing
`atomic()` block**, so the two blocks touch the same function. The rule:

- **BLOCK 9 is the first and only writer of `withdraw_consent` in this plan.** Its commit
  establishes the teardown region, the ten-column `update_fields`, and the transaction
  order.
- **BLOCK 10 is the sole subsequent writer** and must **re-read `deletion.py` immediately
  before editing**. It inserts its `record_consent_action_with_context(...)` call *after*
  the teardown writes and *inside* the same `atomic()` — a **disjoint region** of the same
  function.
- **No parallel edit, ever.** `depends_on: [task_06_b09_withdraw_teardown]` already
  serialises them (plan §1.3: one Implementor, sequential). If a session finds BLOCK 10's
  changes already present in `deletion.py`, **stop and report** rather than layering on
  top (plan §1.3).
- The Validator for BLOCK 10 checks that BLOCK 9's teardown and `update_fields` survived
  intact, and that the `ConsentRecord` row is inside the transaction.

**Ordering with BLOCK 14 — BLOCK 9 first, and the edge is soft.**
They share **no file**: BLOCK 9 touches `deletion.py`, `views/consent.py`,
`views/preferred_city.py`, `privacy.html`, two `.po` files and the spec; BLOCK 14 touches
`core/utils/sanitize.py`, `search/services/search_history.py`,
`search/services/popular_search.py`, `seed_service.py` and migration `0005`. The shared
thing is the **`search_history` table**, i.e. **rows, not source**: deleting rows is not
editing the file that writes them.

**Required order: BLOCK 9, then BLOCK 14.** The correctness argument is nil in both
directions — BLOCK 9's delete is a row-scoped `.filter(user=user).delete()` that cannot
see another user's rows, and BLOCK 14's data migration rewrites whatever rows it finds.
The argument is **cost and predictability**: running BLOCK 14 first means its `RunPython`
redacts rows that BLOCK 9 is about to delete (pure waste, and one more full-table pass
inside a migration), and it makes BLOCK 9's `test_deletion.py` fixtures depend on whether
the migration has been applied. BLOCK 9 first keeps BLOCK 14's migration input stable and
its precondition assertions reproducible. **The coordinator may invert the edge if it
must, but must not run them concurrently** — a data migration and a withdrawal-time row
deletion are not independent.

**Explicitly out of scope: `UserAdmin`.** After BLOCK 3's and phase 04's landings,
`preferred_city` is the **one** writable field on the user change form, and
`test_admin_pii_containment.py::test_change_form_keeps_preferred_city_writable` pins it
writable. A moderator setting the field is a **staff** action, not the data subject's, and
the data subject's own three write paths are the ones this block closes. **Do not make it
read-only, do not add an exclusion to the change form, do not touch `apps/users/admin.py`.**

**What §6 must and must not say.** `privacy.html` has **seven** sections (1 Controller …
7 Manage Your Consent) and **there is no §8** — this plan's repeated "§8" citations are
wrong, and `{% trans "Data portability." %}` is a **§5 "Your Rights"** bullet. **Do not
create a §8, and do not renumber.** §6 must enumerate: erased immediately (account and
ads soft-deleted; `telegram_id` / `username` nulled; first name, last name and e-mail
emptied; login tokens invalidated; **saved searches deactivated; search history deleted;
preferred city cleared**), erased at the 30-day hard-delete sweep, and **retained with a
reason** — the Telegram chat identifier (the bot resolves the acting user on it so a
withdrawn identity **stays blocked**), the anonymised consent-action log, and moderator
and ad-text records. §6 must **not** claim ad text or the consent log's browser
fingerprint are erased: BLOCK 11 and BLOCK 15 own those, and if either lands later §6 is
*tightened* then. §7's *"You can revisit and change your consent choices at any time"*
remains true after this block and is **BLOCK 8's** to touch, not this block's.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/users/services/deletion.py` | `withdraw_consent`, `decline_consent` | **The first edit to the erasure transaction in this plan**, and the only place `SavedSearch` / `SearchHistory` are touched. `soft_delete_user_ads` is **untouched** — it is BLOCK 11's; the `ConsentRecord` write is BLOCK 10's; the ticket scrub is BLOCK 13's |
| `src/backend/apps/users/views/consent.py` | `_set_consent_cookies`, `_reconcile_preferred_city_on_login` | **New to this block's surface.** Changes (i) and (iii). Add one small module-level helper that emits the expired `preferred_city` cookie with the write's attributes |
| `src/backend/apps/search/views/preferred_city.py` | `set_preferred_city` — the authenticated DB-write branch only | **New to this block's surface.** Change (ii). The `action=clear` branch, the cookie branch and the 400/405 paths are **untouched** — they are pinned by `test_preferred_city.py::TestReset` |
| `src/backend/apps/users/services/pii_inventory.py` | the `("users.User", "preferred_city")` tuple — **its reason string only** | Change (iv)'s declaration half. The tuple shape and `ErasureAction.NULL` are **not** edited |
| `src/backend/templates/privacy.html` | **§6 "Erasure and Retention" only** | Seven sections exist; there is **no §8**. §7 is BLOCK 8's; §5's `Data portability.` bullet is §5.6's problem; §4's cookie table is pinned by `test_privacy.py` and is untouched |
| `src/backend/locale/{ru,bs,en}/LC_MESSAGES/django.po` | the §6 strings | **Three contended files.** Append-only — see the i18n contract below |
| `docs/01-spec/technical-specification.md` | **§F** "Post-withdrawal erasure" bullet list; **§G** "Preferred city (Plans 17/23)" bullet | Two bullets. Same commit as the code |
| `src/backend/apps/users/tests/test_deletion.py` | new teardown + rollback tests | Extend the existing `TestWithdrawConsentAtomicity::test_withdraw_is_atomic_rollback`; do not write a parallel atomicity test |
| `src/backend/apps/users/tests/test_consent.py` | new decline-clears-column + decline-expires-cookie tests | `TestConsentDeclineView` is the home; `test_decline_sets_declined_cookie` must pass **unchanged** |
| `src/backend/apps/users/tests/test_login.py` | new declined-reconcile test | `test_login_backfills_db_from_cookie` and `test_login_does_not_overwrite_existing_db_preference` are the tripwires and must pass **unchanged** |
| `src/backend/apps/search/tests/test_preferred_city.py` | new declined-buyer test | A **second app's** test module — the plan's old `tests_to_run` named a nonexistent `users` copy |
| `src/backend/apps/users/services/account_state.py` | **read-only reference** | Its `account_state_q` is BLOCK 6/7's. **Do not import it into `set_preferred_city`** |

**Binding constraints**

1. **Never null `chat_id`.** Any registry entry for it is `RETAIN` with a reason. This is
   the load-bearing safety property of the whole block: `AccountStateMiddleware` resolves
   the acting user on `chat_id` *precisely because* `telegram_id` is nulled, so a
   withdrawn identity stays **resolvable and therefore stays blocked**. Nulling it would
   re-open a different hole. **The `chat_id` value surviving is an acceptance criterion,
   not an accident** — assert it.
2. Both new writes happen **inside `withdraw_consent`'s existing
   `transaction.atomic()` block** (the `SavedSearch` deactivation and the `SearchHistory`
   delete), so state and evidence commit or roll back together. `decline_consent` opens no
   transaction today and this block **must not add one** — it extends the existing
   `update_fields` instead.
3. The erasures go through **BLOCK 3's inventory**, not a second hand-maintained list.
   Concretely: this block edits the `preferred_city` entry's **reason string only** and
   leaves the tuple shape and the action alone. It does **not** add `search.SearchHistory`
   to the inventory (that is BLOCK 14's).
4. `SavedSearch.is_active` is set with a bulk `.update()`, not a loop of `.save()` — per-row
   saves would fire signals nobody wants inside a withdrawal. `SavedSearch.updated_at` is
   `auto_now=True` and a `.update()` therefore does **not** refresh it; that is accepted and
   must be named in the commit body. **The daily alert cap reads `last_notified_at`, not
   `updated_at`**, so the teardown cannot corrupt notification throttling.
5. Do **not** introduce a per-request account-state middleware (phase 15). Do **not** touch
   `AccountStateMiddleware` (phase 04/15).
6. §6's rewrite must be **true**. Do not over-promise and do not under-promise; if the copy
   cannot be made true by BLOCK 13 and BLOCK 15, say so in the commit body rather than
   shipping a promise the code does not keep. **Do not create a §8 and do not renumber** —
   `privacy.html` has seven sections and `Data portability.` is a §5 bullet.
7. **Do not touch `apps/users/admin.py`.** `preferred_city` is the one writable field on
   the user change form and is pinned writable by
   `test_admin_pii_containment.py::test_change_form_keeps_preferred_city_writable`. A staff
   write is not the data subject's write.
8. **All four Q-D10 changes or none.** Shipping (i) without (iii) leaves the login claim
   restoring the column; shipping (iii) without (ii) leaves the header write restoring it.
   The four changes are one commit and one reviewable unit.
9. `apps/search/services/__init__.py` **must stay import-free** — BLOCK 6 binding
   constraint 3, pinned by BLOCK 6's fresh-interpreter import probe. This block imports
   `apps.search.models` directly and adds **no** `search.services` import.
10. `_set_consent_cookie`'s attributes are load-bearing. The `preferred_city` deletion must
    mirror the **write** (`httponly=True`, `samesite="Lax"`, `secure=True`, `path="/"`),
    because `_set_consent_cookies` writes with `secure=True` unconditionally. Using
    `request.is_secure()` would produce a non-matching deletion header over HTTPS.
11. **One writer at a time** (plan §1.3). `deletion.py` is this block's first write and
    BLOCK 10's second; see the ownership rule above. `views/consent.py` was last written
    by **BLOCK 8** (its serial predecessor). If either file already carries changes you did
    not write, **stop and report** — do not layer on top and do not `git checkout`.
12. Every user-visible string ships **non-empty `ru` and `bs`** in the **same commit**;
    `en` may be empty. Append to the three `.po` files — see the i18n contract below.

**Implementor task**

```yaml
id: task_06_b09_withdraw_teardown
title: "Tear down subscriber state on withdrawal and make the preferred_city clearing durable (06-PII-110)"
priority: medium
depends_on: [task_06_b03_pii_inventory, task_06_b07_alert_audience_gate, task_06_b08_decline_recovery]
source_reference: ".ai/plans/06-pii-consent-remediation.md"
source_section: "BLOCK 9 - Withdraw-time teardown, preferred_city, and the section 6 promise"
source_blocks: ["BLOCK 9"]
description: >
  Q-D10 is RESOLVED and this plan's premise was inverted: clearing User.preferred_city
  alone does not survive, because consent_decline defaults preferences to True (so the
  cookie survives a decline), set_preferred_city writes the DB column unconditionally
  for any authenticated buyer, the login reconcile restores it, and delete_cookie()
  cannot clear a Secure cookie over HTTPS. Four coordinated changes make the clearing
  durable, plus the kept half of the finding: withdraw_consent deactivates the user's
  SavedSearch rows and deletes their SearchHistory rows inside its existing
  transaction, privacy.html section 6 is rewritten to enumerate what is erased and what
  is retained and why, and the inventory's preferred_city reason is corrected. chat_id
  is retained deliberately and must not be nulled.
goals:
  - "make the preferred_city clearing durable across all four restore paths"
  - "make revocation actively tear down subscriber state instead of relying on a filter"
  - "make the published retention promise true and specific"
  - "keep chat_id resolvable so a withdrawn identity stays blocked"
files:
  - path: "src/backend/apps/users/services/deletion.py"
    targets:
      - type: function
        name: withdraw_consent
      - type: function
        name: decline_consent
    semantic_anchors:
      insert_after:
        type: function_call
        value: LoginToken.objects.filter(telegram_id=user_telegram_id).delete()
      insert_before:
        type: function_call
        value: storage_keys = soft_delete_user_ads(user)
  - path: "src/backend/apps/users/views/consent.py"
    targets:
      - type: function
        name: _set_consent_cookie
      - type: function
        name: _set_consent_cookies
      - type: function
        name: _reconcile_preferred_city_on_login
    semantic_anchors:
      insert_after:
        type: function
        name: _set_consent_cookie
      replace_in:
        type: function_call
        value: response.delete_cookie(PREFERRED_CITY_COOKIE_NAME)
      insert_before:
        type: return_statement
        value: "the `if user.preferred_city_id is not None:` early return"
  - path: "src/backend/apps/search/views/preferred_city.py"
    targets:
      - type: function
        name: set_preferred_city
    semantic_anchors:
      insert_before:
        type: assignment_statement
        value: city = City.objects.get(slug=slug)
  - path: "src/backend/apps/users/services/pii_inventory.py"
    targets:
      - type: module_constant
        name: PII_ERASURE_ENTRIES
    semantic_anchors:
      replace_in:
        type: tuple_element
        value: '"preferred_city"'
  - path: "src/backend/templates/privacy.html"
    targets:
      - type: template_section
        name: "6. Erasure and Retention"
    semantic_anchors:
      insert_after:
        type: template_tag
        value: '{% trans "6. Erasure and Retention" %}'
  - path: "docs/01-spec/technical-specification.md"
    targets:
      - type: document_section
        name: "Post-withdrawal erasure"
      - type: document_section
        name: "Preferred city (Plans 17/23)"
  - path: "src/backend/apps/users/tests/test_deletion.py"
    targets:
      - type: class
        name: TestWithdrawConsentAtomicity
  - path: "src/backend/apps/users/tests/test_consent.py"
    targets:
      - type: class
        name: TestConsentDeclineView
  - path: "src/backend/apps/users/tests/test_login.py"
    targets:
      - type: class
        name: TestLoginPreferredCitySync
  - path: "src/backend/apps/search/tests/test_preferred_city.py"
    targets:
      - type: class
        name: TestPreferredCityView
      - type: class
        name: TestReset
  - path: "src/backend/locale/ru/LC_MESSAGES/django.po"
    targets:
      - type: gettext_catalog
        name: django
  - path: "src/backend/locale/bs/LC_MESSAGES/django.po"
    targets:
      - type: gettext_catalog
        name: django
  - path: "src/backend/locale/en/LC_MESSAGES/django.po"
    targets:
      - type: gettext_catalog
        name: django
changes:
  - action: modify_code
    file: "src/backend/apps/users/services/deletion.py"
    symbol: withdraw_consent
    description: >
      Inside the EXISTING transaction.atomic() block, after the LoginToken delete and
      before soft_delete_user_ads: deactivate the user's SavedSearch rows with one bulk
      update and delete their SearchHistory rows. Add "preferred_city" to the existing
      nine-column update_fields (ten after this change) and set user.preferred_city = None
      beside the other PII writes. No new transaction.
    code_hint: |
      from apps.search.models import SavedSearch, SearchHistory
      ...
      SavedSearch.objects.filter(user=user).update(is_active=False)
      SearchHistory.objects.filter(user=user).delete()
      ...
      user.preferred_city = None
      user.save(update_fields=[..., "preferred_city"])   # now ten columns
  - action: modify_code
    file: "src/backend/apps/users/services/deletion.py"
    symbol: decline_consent
    description: >
      Set user.preferred_city = None and add "preferred_city" to the EXISTING
      update_fields list (currently ["ads_auto_publish", "is_declined",
      "consent_given_at"]). Open no transaction.
    code_hint: |
      user.preferred_city = None
      user.save(update_fields=["ads_auto_publish", "is_declined", "consent_given_at", "preferred_city"])
  - action: add_code
    file: "src/backend/apps/users/views/consent.py"
    symbol: _expire_preferred_city_cookie
    description: >
      A small module-level helper that emits the deletion Set-Cookie by hand, mirroring
      the WRITE's attributes (_set_consent_cookie uses secure=True unconditionally). Do
      NOT use response.delete_cookie(): Django 5.2 emits Secure only for __Host-/__Secure-
      names or samesite="none", so a plain delete_cookie() cannot clear a Secure cookie
      over HTTPS. set_preferred_city already works around exactly this defect.
    code_hint: |
      def _expire_preferred_city_cookie(response: HttpResponse) -> None:
          """Delete the preferred_city cookie, mirroring the secure WRITE attributes."""
          response.set_cookie(
              PREFERRED_CITY_COOKIE_NAME,
              max_age=0,
              expires="Thu, 01 Jan 1970 00:00:00 GMT",
              path="/",
              httponly=True,
              samesite="Lax",
              secure=True,
          )
  - action: modify_code
    file: "src/backend/apps/users/views/consent.py"
    symbol: _set_consent_cookies
    description: >
      Replace the `if not preferences:` cookie deletion with a deletion that fires
      whenever the choice is ConsentChoice.DECLINED OR preferences is falsy, and route
      it through the new helper. consent_preferences itself keeps its value - a decline
      still writes consent_preferences == "true" (PO-02) and
      test_consent.py::test_decline_sets_declined_cookie pins that.
    code_hint: |
      if choice is ConsentChoice.DECLINED or not preferences:
          _expire_preferred_city_cookie(response)
  - action: modify_code
    file: "src/backend/apps/users/views/consent.py"
    symbol: _reconcile_preferred_city_on_login
    description: >
      Add `if user.is_declined: return` before the existing preferred_city_id guard. This
      is a RECONCILE rule and belongs here - NOT in login_status, which is BLOCK 8's
      surface.
    code_hint: |
      if user.is_declined:
          return
      if user.preferred_city_id is not None:
          return
  - action: modify_code
    file: "src/backend/apps/search/views/preferred_city.py"
    symbol: set_preferred_city
    description: >
      Gate the authenticated DB write on `not request.user.is_declined`. Use the plain
      attribute, NOT account_state_q() - importing apps.users.services.account_state into
      this view would add a cross-app import and a second spelling of the rule. The
      action=clear branch, the cookie branch and the 400/405 paths are untouched.
    code_hint: |
      if request.user.is_authenticated and not request.user.is_declined:
          try:
              city = City.objects.get(slug=slug)
              request.user.preferred_city = city
              request.user.save(update_fields=["preferred_city"])
          except City.DoesNotExist:
              logger.warning("Preferred city %s disappeared during save", slug)
  - action: modify_code
    file: "src/backend/apps/users/services/pii_inventory.py"
    symbol: PII_ERASURE_ENTRIES
    description: >
      Rewrite ONLY the ("users.User", "preferred_city") entry's REASON STRING so it says
      the NULL is implemented and names the four changes that keep it durable. Do NOT
      add an `implemented` field - the declared tuple is exactly
      (model_label, column, action, reason) and adding one would be a second
      hand-maintained list. Do NOT change ErasureAction.NULL and do NOT add
      search.SearchHistory to REVIEWED_NON_IDENTITY_COLUMNS - that is BLOCK 14's, because
      BLOCK 14 re-derives SearchHistory.query_normalized.
  - action: modify_template
    file: "src/backend/templates/privacy.html"
    symbol: "section 6"
    description: >
      Rewrite section 6 "Erasure and Retention" to enumerate erased-immediately,
      erased-at-30-days and retained-with-a-reason. The retained list must cite the
      Telegram chat identifier and say WHY (the bot resolves the acting user on it so a
      withdrawn identity stays blocked). Do NOT claim ad text or the consent log's
      browser fingerprint are erased - BLOCK 11 and BLOCK 15 own those. Do NOT create a
      section 8 and do NOT renumber: the page has seven sections and "Data portability."
      is a section 5 bullet. Section 7 is BLOCK 8's and is untouched.
  - action: modify_docs
    file: "docs/01-spec/technical-specification.md"
    description: >
      Two bullets, nothing else. Section F's "Post-withdrawal erasure" list gains the
      SavedSearch deactivation, the SearchHistory deletion, the preferred_city NULL and
      the chat_id RETAIN-with-reason. Section G's "Preferred city (Plans 17/23)" bullet
      gains the declined-user exclusions on both the login reconcile and the DB write.
  - action: add_code
    file: "src/backend/locale/{ru,bs,en}/LC_MESSAGES/django.po"
    description: >
      Append the new section-6 msgids. ru and bs MUST carry non-empty msgstr; en may be
      empty (the msgid is English). APPEND ONLY - see extra_context.
acceptance_criteria:
  - "after withdraw_consent() the user has no active SavedSearch row and no SearchHistory row, AND another user's SavedSearch and SearchHistory rows are untouched"
  - "preferred_city_id is NULL on the DB row after a decline and after a withdrawal"
  - "a DECLINE response expires the preferred_city cookie over an HTTPS-style request (secure=True on the test client): empty value, max-age 0, Secure, SameSite=Lax, HttpOnly - and the response does NOT use delete_cookie()"
  - "the decline response still writes consent_preferences == 'true' (PO-02 is unchanged)"
  - "the login reconcile does not backfill preferred_city for a declined user, and still backfills for a non-declined user"
  - "a POST to /api/preferred-city/ with a valid slug does not set User.preferred_city for a declined authenticated buyer, and still does for a non-declined one"
  - "the explicit 'clear' action still nulls the FK and returns all cities for an authenticated buyer, and still deletes the cookie for an anonymous one (both TestReset tests pass UNCHANGED)"
  - "User.chat_id is unchanged after withdrawal and the user is still resolvable by chat_id - AccountStateMiddleware keeps finding them"
  - "the inventory's preferred_city entry keeps ErasureAction.NULL, keeps the 4-tuple shape, and its reason now states the clear is implemented; test_pii_inventory.py passes UNCHANGED"
  - "a failure inside the withdrawal transaction rolls back the SavedSearch deactivation AND the SearchHistory deletion together with the existing PII writes - extend TestWithdrawConsentAtomicity::test_withdraw_is_atomic_rollback, do not write a parallel test"
  - "privacy.html still has exactly seven numbered sections and still renders 200 with its cookie table and third-party disclosures (test_privacy.py passes UNCHANGED)"
  - "section 6 names every retained item and the reason it is retained, and makes no promise about ad text or the consent log's fingerprint"
  - "ru and bs msgstr are non-empty for every new msgid; en may be empty; test_i18n_completeness.py passes"
  - "apps/search/services/__init__.py is untouched and still contains only default_app_config"
tests_required:
  - "withdraw teardown removes only the withdrawing user's subscriber state (test_deletion.py)"
  - "rollback covers both new writes (test_deletion.py)"
  - "chat_id survives withdrawal and the user is still resolvable by chat_id (test_deletion.py)"
  - "a decline clears the column and expires the cookie over HTTPS, and the reconcile does not restore it (test_consent.py + test_login.py)"
  - "the header click does not re-set the column for a declined buyer (apps/search/tests/test_preferred_city.py)"
tests_to_run:
  - "src/backend/apps/users/tests/test_deletion.py"
  - "src/backend/apps/users/tests/test_consent.py"
  - "src/backend/apps/users/tests/test_login.py"
  - "src/backend/apps/users/tests/test_pii_inventory.py"
  - "src/backend/apps/users/tests/test_account_state.py"
  - "src/backend/apps/search/tests/test_preferred_city.py"
  - "src/backend/apps/search/tests/test_preferred_city_readback.py"
  - "src/backend/apps/core/tests/test_privacy.py"
  - "src/backend/apps/ads/tests/test_i18n_completeness.py"
commands:
  setup: "$dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'"
  test: "$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS=\"src/backend/apps/users/tests src/backend/apps/search/tests/test_preferred_city.py src/backend/apps/search/tests/test_preferred_city_readback.py --tb=short\" test"
  test_i18n: "$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS=\"src/backend/apps/ads/tests/test_i18n_completeness.py --tb=short\" test"
  lint: "uv run ruff check src/backend/apps/users/services/deletion.py src/backend/apps/search/views/preferred_city.py"
  typecheck: "uv run basedpyright src/backend/apps/users/services/deletion.py"
  lint_template: "uv run djlint src/backend/templates/privacy.html"
  i18n_extract: "$dev run --rm --no-deps --entrypoint \"\" web python src/backend/manage.py makemessages -l ru -l bs -l en --no-location"
  notes: >
    PYTEST_OPTS is unquoted in docker/entrypoint-test.sh, so each token is word-split on
    spaces, and setting it REPLACES the defaults (--reuse-db --tb=short --durations=10 -n
    auto --maxprocesses=4 --dist loadgroup) - a targeted run loses xdist parallelism and
    DB reuse. Never use --override-ini=addopts=, which strips --import-mode=importlib.
    Never run pytest on the host: there is no PostgreSQL on localhost:5432. VAL-010 is
    not a defect: concurrent runs share one test_mko_bazuna, and ForeignKeyViolation on
    auth_permission / django_content_type, "database test_mko_bazuna does not exist",
    "assert not self._finalizers" are contamination artefacts - re-run serially before
    reporting a failure.
commit:
  message: "fix(users): tear down subscriber state and the city preference on withdrawal (06-PII-110)"
  stage:
    - "src/backend/apps/users/services/deletion.py"
    - "src/backend/apps/users/services/pii_inventory.py"
    - "src/backend/apps/users/views/consent.py"
    - "src/backend/apps/search/views/preferred_city.py"
    - "src/backend/templates/privacy.html"
    - "docs/01-spec/technical-specification.md"
    - "src/backend/apps/users/tests/test_deletion.py"
    - "src/backend/apps/users/tests/test_consent.py"
    - "src/backend/apps/users/tests/test_login.py"
    - "src/backend/apps/search/tests/test_preferred_city.py"
    - "src/backend/locale/ru/LC_MESSAGES/django.po"
    - "src/backend/locale/bs/LC_MESSAGES/django.po"
    - "src/backend/locale/en/LC_MESSAGES/django.po"
  body_notes:
    - "SavedSearch.updated_at is auto_now and a bulk .update() does not refresh it; accepted, because the daily alert cap reads last_notified_at."
    - "Deleting SearchHistory is a strengthening of the published promise, not a conflict with it: the spec already sanctions first-party AnalyticsEvent rows under legitimate interest, and SearchHistory holds the subject's own typed queries."
    - "The inventory's preferred_city entry changed its REASON STRING only - the declared tuple is (model_label, column, action, reason) and has no implemented field. No search.SearchHistory entry is added here; BLOCK 14 owns that table's declaration."
    - "chat_id is retained deliberately and must never be nulled: AccountStateMiddleware resolves the acting user on it so a withdrawn identity stays resolvable and therefore stays blocked."
    - "This is the first and only writer of withdraw_consent in phase 06. BLOCK 10 is the sole subsequent writer and must re-read this file immediately before inserting the ConsentRecord write inside the same atomic() block."
extra_context: |
  Q-D10 is RESOLVED (Researcher, 2026-10-02). Do not re-open it. The plan's original
  premise was INVERTED: it claimed the preferred_city cookie is already deleted on
  decline, "so the nulling should hold". It is not, and there are three independent
  defects plus one implementation trap:

    1. consent_decline computes
         preferences = submission.preferences if submission and "preferences" in
         request.POST else True
       - the DEFAULT IS TRUE - and _set_consent_cookies deletes the cookie only
       `if not preferences`. So the common decline KEEPS the cookie for a year with
       consent_preferences == "true", and the next login-claim restores the column.
       tests/test_consent.py::test_decline_sets_declined_cookie pins exactly this.
    2. apps/search/views/preferred_city.py::set_preferred_city writes User.preferred_city
       UNCONDITIONALLY for an authenticated buyer - it gates only the COOKIE on
       consent_preferences. A declined user clicking a city in the header re-sets the
       column with no reconcile involved.
    3. delete_cookie() CANNOT clear a Secure cookie over HTTPS in Django 5.2: Secure is
       emitted only for __Host-/__Secure- prefixed names or samesite="none", and
       preferred_city is neither. The repo already documents and works around this in
       set_preferred_city's clear branch by emitting an expired cookie directly.
    4. The reconcile's early return today fires only when preferred_city_id is not None,
       which is exactly the state the clearing creates - so it would happily re-derive
       the column from the surviving cookie.

  RESOLVED END STATE: the clearing is durable, and it is NOT terminal. give_consent
  already sets is_declined=False, after which the header write and the login reconcile
  may legitimately set the column again. Re-acceptance is a NEW consent. give_consent
  therefore needs NO change. Ship all four changes or none - (i) without (iii) leaves the
  login claim restoring the column, and (iii) without (ii) leaves the header write
  restoring it.

  chat_id is FORBIDDEN to null. AccountStateMiddleware._resolve_user does
  User.objects.get(chat_id=chat_id) precisely because withdraw_consent nulls
  telegram_id; that is what keeps a withdrawn identity resolvable and therefore BLOCKED.
  Nulling chat_id re-opens a different hole. Assert that chat_id survives - that test is
  what stops a future "cleanup" from breaking the ban.

  The ConsentRecord retention half of 06-PII-110 is ABSORBED by 06-PII-116 / BLOCK 15.
  Do not touch ConsentRecord.session_key or .user_agent here.

  IMPORT DIRECTION: import SavedSearch and SearchHistory from apps.search.models
  directly. No cycle - search/models.py refers to its foreign keys as lazy string labels
  and imports nothing from apps.users. Zero runtime cost - apps.search is an installed
  app, so django.setup() already imports search.models in both processes. This is not a
  new APP-level dependency: deletion.py already imports apps.search.services.cache, and
  that back-edge is documented and frozen by BLOCK 6. Do NOT pass querysets in as
  parameters (BLOCKS 10, 11 and 13 all re-edit this function), and do NOT create a new
  apps/search/services helper unless you can justify it in the commit body. If you do,
  apps/search/services/__init__.py MUST stay import-free (BLOCK 6 binding constraint 3)
  - it currently contains nothing but default_app_config, and adding a submodule import
  closes a loop through alert_query and breaks the entire alert path.

  BLOCK 8 IS YOUR SERIAL PREDECESSOR AND SHARES TWO FILES. It owns
  apps/users/views/consent.py and may have made a "minimal state change" to
  deletion.py::decline_consent for its recovery mechanism; it owns privacy.html section 7,
  NOT section 6. Re-read views/consent.py and deletion.py::decline_consent immediately
  before editing and expect decline_consent's update_fields to be FOUR columns rather than
  three. Do not touch section 7. If BLOCK 8 has not landed, your _set_consent_cookies edit
  is still safe, but BLOCK 8's tests must be re-run after it does.

  OWNERSHIP: this block is the FIRST and only writer of withdraw_consent in phase 06.
  BLOCK 10 is the SOLE subsequent writer - it moves the ConsentRecord write inside the
  same existing atomic() block - and must re-read deletion.py immediately before
  editing. The two regions are disjoint (teardown vs. evidence write), but they are the
  same function and must never be edited in parallel. If deletion.py already has changes
  you did not write, STOP and report (plan section 1.3).

  ORDERING vs BLOCK 14: BLOCK 9 FIRST, BLOCK 14 second. They share no file - only the
  search_history table. The correctness argument is nil either way; the argument is cost
  and predictability, because running BLOCK 14 first means its data migration redacts
  rows BLOCK 9 is about to delete and makes BLOCK 9's fixtures depend on whether the
  migration ran. They must NOT run concurrently.

  SPEC EDIT: docs/01-spec/technical-specification.md is reserved to phase 06 and BLOCKS
  4, 11 and 14 serialise on it. This block takes exactly two bullets - section F's
  "Post-withdrawal erasure" list and section G's "Preferred city (Plans 17/23)" bullet -
  in this commit. No other section.

  i18n CONTRACT (this block trips the gate, and that is expected):
    - Every user-visible string you touch ships NON-EMPTY ru and bs msgstr in the SAME
      commit. en may be empty - the msgid is English.
    - The three locale/*/LC_MESSAGES/django.po files are CONTENDED. Phase 05 is
      committing into them right now, and phase 14 owns the runtime i18n tree. Re-read
      each file immediately before editing and stage ONLY the lines you add.
    - NEVER run a wholesale makemessages: it would discard a concurrent phase's tree.
      Append the new msgids by hand. `make makemessages` and `make compilemessages` do
      not work on Windows + Docker Desktop; the lightweight --no-deps --entrypoint ""
      form in .kilo/rules/commands.md is the only working extraction command, and
      compilemessages is rarely needed because .mo files are gitignored and compiled at
      image build, at container start and in the CI i18n job.
    - Run src/backend/apps/ads/tests/test_i18n_completeness.py afterwards. It asserts
      the new msgid exists in ALL THREE .po files and that ru/bs carry no empty msgstr.
    - BLOCK 8's separate, known VAL-006 i18n failure is NOT this block's problem. Do not
      conflate the two and do not "fix" it here.

  TEMPLATE: privacy.html has SEVEN sections (1 Controller ... 7 Manage Your Consent) and
  there is NO section 8. This plan's repeated "section 8" citations are wrong;
  {% trans "Data portability." %} is a bullet inside section 5 "Your Rights". Do not
  create a section 8 and do not renumber. Section 6 currently over-promises: "All
  personal data is permanently erased within 30 days of withdrawal. Consent state is
  otherwise retained for 12 months, after which you are re-prompted."

  privacy.html section 6 is PROSE. Per plan section 1.5 no test asserts template
  substrings - the gate on this copy is a second reader, not a test.

  VERIFY EVERY PATH BEFORE YOU NAME IT. The previous draft of this task named
  src/backend/apps/users/tests/test_preferred_city.py and
  src/backend/apps/users/tests/test_preferred_city_readback.py - neither exists. The real
  cookie-lifecycle tripwires live in the SEARCH app:
  apps/search/tests/test_preferred_city.py::TestReset::
      test_clear_deletes_cookie_and_returns_all_cities_anonymous
  apps/search/tests/test_preferred_city.py::TestReset::
      test_clear_nulls_fk_and_returns_all_cities_authenticated
  plus apps/search/tests/test_preferred_city_readback.py and
  apps/search/tests/test_preferred_city.py::TestReset::
      test_clear_deletion_cookie_mirrors_attributes_on_https, which is the template for
      the "over an HTTPS-style request" assertion this block needs.
```

**Tests required** (logic and component interaction — plan §1.5; no template substrings, no
line numbers, no counts, no presence-of-symbol assertions)

1. **Teardown is real and scoped.** After `withdraw_consent()` that user's `SavedSearch`
   rows are all `is_active=False` and their `SearchHistory` rows are gone — **and a
   different user's `SavedSearch` and `SearchHistory` rows are untouched**. Both halves:
   the teardown happened, and it did not over-reach. (`test_deletion.py`)
2. **Rollback covers both new writes.** Extend the existing
   `TestWithdrawConsentAtomicity::test_withdraw_is_atomic_rollback` so a failure inside the
   transaction leaves the `SavedSearch` deactivation **and** the `SearchHistory` deletion
   rolled back together with the existing `LoginToken` deletion and PII nulling. **Do not
   write a parallel atomicity test.** (`test_deletion.py`)
3. **`chat_id` survives — the safety property.** Assert `chat_id` is unchanged after
   withdrawal **and** that the withdrawn user is still resolvable by
   `User.objects.get(chat_id=...)`, i.e. exactly what
   `AccountStateMiddleware._resolve_user` does. This is the test that stops a future
   "cleanup" from silently un-blocking a withdrawn identity. (`test_deletion.py`)
4. **The clearing is durable on the decline path.** After a DECLINE: the **column** is
   `NULL`; the response's `preferred_city` cookie is expired with the hand-rolled secure
   attributes over an **HTTPS-style** request (`secure=True` on the test client) — empty
   value, `max-age 0`, `Secure`, `SameSite=Lax`, `HttpOnly` — modelled on
   `apps/search/tests/test_preferred_city.py::TestReset::test_clear_deletion_cookie_mirrors_attributes_on_https`;
   `consent_preferences` is still `"true"` (PO-02 unchanged); and the next login claim
   does **not** restore the column, while a **non-declined** user's is still backfilled by
   the cookie. (`test_consent.py` + `test_login.py`)
5. **The header click cannot re-set it.** A `POST /api/preferred-city/` with a valid slug
   by a **declined** authenticated buyer returns `200 {"ok": true}` but leaves
   `User.preferred_city` `NULL`; the same POST by a non-declined buyer still persists it.
   Assert the *behaviour*, not the guard's shape. (`apps/search/tests/test_preferred_city.py`)
6. **The cookie-lifecycle tripwires stay green.** Unchanged, in the **search** app:
   `TestReset::test_clear_deletes_cookie_and_returns_all_cities_anonymous`,
   `TestReset::test_clear_nulls_fk_and_returns_all_cities_authenticated`,
   `TestReset::test_clear_deletion_cookie_mirrors_attributes_on_https`, the whole of
   `test_preferred_city_readback.py`, and `TestPreferredCityView::
   test_post_with_valid_slug_persists_db_for_authenticated`.
7. **`privacy.html` §6 is prose.** Per plan §1.5 **no test asserts a template substring.**
   The gate is a second reader. The only mechanical checks are the ones that already exist
   and must stay green: `test_privacy.py` (200, cookie table, third-party list) and
   `test_i18n_completeness.py` (no hardcoded visible text, msgid present in all three
   catalogues, non-empty `ru`/`bs`).

**The i18n contract for this block**

This block **does** trip the gate, and that is expected — §6 is replaced, so new msgids
appear.

- **Every user-visible string ships non-empty `ru` and `bs`** in the **same commit** as the
  template. `en` may be empty — the msgid is English.
- **The three `locale/*/LC_MESSAGES/django.po` files are CONTENDED.** Phase 05 is committing
  into all three right now; phase 14 owns the runtime i18n tree. **Re-read each file
  immediately before editing and stage only the lines you add** — `git add <path>` on a
  whole file stages whatever phase 05 put there too, so if the file has concurrent changes
  this block does not own, **stop and report it** (plan §1.3).
- **Never run a wholesale `makemessages`.** It would discard a concurrent phase's runtime
  tree. Append the new msgids by hand.
- `make makemessages` / `make compilemessages` **do not work** on Windows + Docker Desktop.
  The working extraction form is in `.kilo/rules/commands.md`:
  `docker compose … run --rm --no-deps --entrypoint "" web python src/backend/manage.py makemessages -l ru -l bs -l en --no-location`.
  `compilemessages` is rarely needed: `.mo` files are gitignored and compiled at image
  build, at container start and in the CI `i18n` job.
- `src/backend/apps/ads/tests/test_i18n_completeness.py` must pass afterwards. It asserts
  the new msgid exists in **all three** catalogues (`test_template_extraction_coverage`)
  and that `ru`/`bs` carry no empty `msgstr` (`test_no_empty_msgstr`).
- **BLOCK 8's i18n failure is a separate, known `VAL-006` case** and is not triaged here.
  Do not conflate the two, and do not "fix" BLOCK 8's strings in this commit.

**Risk and rollback**

- *Risk:* deleting `SearchHistory` rows surprises a legitimate-interest argument.
  Mitigation: the spec already sanctions first-party `AnalyticsEvent` rows under legitimate
  interest, but `SearchHistory` holds the subject's own typed queries, so deletion is a
  **strengthening**, not a conflict. State the reasoning in the commit body.
- *Risk:* a bulk `.update()` on `SavedSearch` does not refresh `updated_at` (`auto_now`).
  Accepted and named in the commit body: **the daily alert cap reads `last_notified_at`**,
  not `updated_at`, so notification throttling cannot be corrupted by the teardown.
- *Risk:* the secure-cookie deletion is wrong in a way only HTTPS reveals. Mitigation: the
  test drives it with `secure=True` on the test client, mirroring production nginx TLS.
- *Rollback:* a straight revert of the code. **The deleted rows do not come back** — this
  is the first block in the plan with a one-way data effect, and there is no `--dry-run` on
  a service call. The compensating controls are that the change is inside the withdrawal
  transaction, and that withdrawal is already a user-initiated, already-irreversible action.
- *Cross-phase:* **BLOCK 10** is the sole subsequent writer of `deletion.py` (re-read
  first); **BLOCK 11**, **BLOCK 13** and **BLOCK 14** all re-read it, `privacy.html` or the
  same retention story after this block lands. BLOCK 14 must run **after** this block.

---

### BLOCK 10 — Make consent revocation self-auditing (06-PII-107)

| | |
|---|---|
| **Findings owned** | `06-PII-107` (confirmed; root-cause rationale corrected) · **records** `06-NEW-02`, it does not fix it |
| **Depends on** | **BLOCK 8** (06-PII-105, in flight) — the `deletion.py` / `consent_record.py` serial. **BLOCK 8 is the immediate predecessor and must have landed first.** BLOCK 9 (`474a68d`) and BLOCK 13 (`6631ff3`) are **both already landed** and this block is the **third** writer of `withdraw_consent`'s `atomic()` block. Nothing external. The `04-AUT-005` gate is **discharged** (§0.6.3 correction 1) |
| **Blocks** | BLOCK 11 (re-reads `deletion.py`). BLOCK 13 and BLOCK 15 have **already landed** |
| **Priority** | P1 — raised from the report's framing by the spec promise the Auditor found (`technical-specification.md` §F *Consent audit log*: *"all accept/decline/withdraw actions are inserted as a new row in the `consent_records` table (never updated)"*) |
| **Risk level** | **HIGH** — it moves a write across the view/service boundary, changes its order relative to `logout()`, and turns an unreachable code path into a live capability |
| **Required agents** | **Auditor · Researcher · Planner · Validator** (all four). §1.6: a separate Validator task is **required** for a HIGH-risk block *and* for any block whose acceptance depends on a decision the Implementor was told not to make — this one has both |
| **Q-D7** | **RESOLVED 2026-10-01 — WIRE**, superuser-gated by `permissions=["delete"]`, per-user `atomic()` kept, **explicit scalars** (no value object, no `HttpRequest` in the domain layer). Rejected alternatives recorded below. **Do not re-open.** |
| **Spec edit** | **NONE.** §F's *Consent audit log* bullet is the **oracle** this block makes true, not text it corrects. See *Docs* below |

**Corrections to this block's premise — verified against the tree, 2026-10-03.** Four of the
section's earlier statements were true when written and are **stale now**. An Implementor who
trusts them writes the wrong thing.

| # | Stale claim | Verified truth |
|---|---|---|
| **C-B10-1** | *"`UserAdmin` declares **no `actions` attribute at all**"* | **It does.** `UserAdmin.actions == ["deactivate_user", "reactivate_user"]` (plan 18, `f2fd392`). This block **EXTENDS** that list. Writing `actions = ["withdraw_consent_action"]` as a new statement would **silently delete the deactivate/reactivate actions** |
| **C-B10-2** | *nothing about a forbidding comment* | `admin.py` carries an explicit **`# DO NOT REGISTER THIS ACTION`** comment block immediately above the action, naming gate `G-B`, risk `R-1` and deferred work `D-8`. It is now **factually wrong** and this block **must rewrite it** — leaving it would leave a comment that forbids the code directly beneath it |
| **C-B10-3** | *`choice='WITHDRAWN'` in three acceptance criteria* | `ConsentChoice.WITHDRAWN == "withdrawn"` — **lowercase**. Assert against `ConsentChoice.WITHDRAWN`, never a hand-typed `'WITHDRAWN'` |
| **C-B10-4** | *the column belongs to BLOCK 15* | BLOCK 15 **closed** at `fd5201d` and did **not** add an actor column. The register (line ~272) says *"A schema change BLOCK 12/15 own"*; that routing is now **half-stale**. See *`06-NEW-02` routing* below |

**The defect, restated against the tree.** `withdraw_consent()` performs the erasure and
writes **no** `ConsentRecord`. The Art. 7(1) evidence is written by the **view**, after the
service call returns, in a statement outside `withdraw_consent()`'s
`transaction.atomic()` block. Two consequences: a non-view caller revokes consent with no
audit trail at all, and a crash between the service's commit and the view's insert leaves a
`consent_revoked_at` with no matching `choice=ConsentChoice.WITHDRAWN` row — precisely the
disagreement between the erasure log and the consent-audit log that Art. 7(1) exists to
make demonstrable, and the one `consent_hard_delete` keys off.

**The report's stated root cause is wrong.** It claims *"`record_consent_action` is
`request`-aware, which makes it awkward to call from non-HTTP contexts"*. It already takes
`request: HttpRequest | None = None` and its docstring already documents `None` as the bot
`/start` entry point. **No signature change to `record_consent_action` is required, and
none is made.** The real root cause is simpler and stronger: the consent **state** mutation
lives in `deletion.py` and the consent **audit** write lives in `views/consent.py`, and
nobody noticed the two are in different layers because the only caller exercising both was
a view.

**The reachability correction (C-8) — restated against the tree, 2026-10-03.**
`withdraw_consent_action` carries `@admin.action(description="Withdraw consent for selected
users")` with **no `permissions=`**, so `func.allowed_permissions` is never set and
`_filter_actions_by_permissions` hits its `if not hasattr(callable, "allowed_permissions"):
filtered_actions.append(action)` early-`continue` — the action would be appended
**unconditionally** to any `actions` list that named it. `UserAdmin.actions` today names only
`deactivate_user` and `reactivate_user`, so the action is unreachable from the admin UI; V-03's
`UserAdmin.actions == ()` is itself stale (plan 18 added the list) but the conclusion is
unchanged: **the name appears in no `actions` list, so the action is dead code today.**
**Wiring it therefore ships a live capability, and its gate must land in the same commit as the
wiring — never before it.** That is the report's unsafe sequence 5 (*"Wiring
`withdraw_consent_action` before PII-107 makes it auditable"*), and it is why the audit move
comes first inside this block.

**C-8, second half.** `record_consent_action(user, choice, categories, request: HttpRequest |
None = None, consent_version=...)` already accepts `None`. **Its signature is frozen in this
block** — a prior block's plan states so explicitly, and BLOCK 8 is editing its **body** (a
`request.session.create()` guard so an anonymous record is attributable) under that same
freeze. `record_consent_action_with_context` does **not** exist and `git log -S` across
`--all` returns nothing: this block creates it.

**Ownership of `withdraw_consent` — three writers, strictly serialised.** Verified 2026-10-03:

| Writer | Commit | What it added to the `atomic()` block |
|---|---|---|
| **BLOCK 9** (06-PII-110) | `474a68d` — **landed** | `LoginToken` delete; `SavedSearch.update(is_active=False)`; `SearchHistory.delete()`; `preferred_city` null; the ten-column `update_fields` |
| **BLOCK 13** (06-PII-101) | `6631ff3` — **landed** | `user.support_tickets.all().delete()`, placed **before** `soft_delete_user_ads(user)` so a later failure rolls it back |
| **BLOCK 8** (06-PII-105) | in flight | edits **`give_consent`** in the *same file* — a **different function**. It is this block's **immediate predecessor** |
| **BLOCK 10** (this block) | — | the audit write, **last** in the block |

- **Ordering rule: BLOCK 8 lands first, then BLOCK 10, never in parallel** (plan §1.3, one
  Implementor, sequential). `depends_on` names BLOCK 8.
- **Re-read `deletion.py`, `consent_record.py` and `views/consent.py` immediately before
  editing.** Expect BLOCK 9's teardown, BLOCK 13's ticket delete and — if BLOCK 8 has landed —
  its `give_consent` change. Those three are all **disjoint** from this block's single added
  statement.
- **The `give_consent` overlap is a same-file, different-function edit.** It is a merge hazard,
  not a semantic one. Do **not** reformat, reorder or "tidy" anything in `give_consent`; if the
  diff shows changes you did not write, **stop and report** — do not layer on top, do not
  `git checkout`, do not `git stash`.
- **Stop rule.** If `record_consent_action_with_context` is already present, or the audit write
  is already inside `withdraw_consent`, **stop and report** — that is another session's work.
- The Validator for BLOCK 10 checks that BLOCK 9's teardown, BLOCK 13's ticket delete and the
  ten-column `update_fields` all survived intact, **and** that the `ConsentRecord` row is
  **inside** the transaction.

#### Q-D7 — RESOLVED: **WIRE**, gated by `permissions=["delete"]`

**1. Wire it; do not remove it.** With `is_declined` / `is_deleted` / `ads_auto_publish`
now `readonly_fields` (phase 04's landed field contract) and `preferred_city` the **one**
writable change-form field — pinned by
`test_admin_pii_containment.py::test_change_form_keeps_preferred_city_writable` — this
action is the **only** staff-side consent mutation left, and BLOCK 8 wants an
operator-recoverable path. Removing it would leave **no** staff-side consent capability at
all. Two declarations, both on `UserAdmin` — **and note that `actions` already exists**:

```python
# EXTEND the existing list. It is today:
#     actions = ["deactivate_user", "reactivate_user"]
# Do NOT replace it with a fresh actions = [...] statement — that deletes the two
# already-shipped operator actions.
actions = ["deactivate_user", "reactivate_user", "withdraw_consent_action"]


@admin.action(
    description="Withdraw consent for selected users",
    permissions=["delete"],
)
def withdraw_consent_action(self, request, queryset):
    ...
```

The comment block immediately above the method — `admin.py`'s **`# DO NOT REGISTER THIS
ACTION`**, which cites gate `G-B`, risk `R-1` and deferred work `D-8` — is **resolved by this
block and must be replaced**, not left in place. Leaving it produces a file in which a comment
forbids the statement directly beneath it. The replacement states the Q-D7 decision, the
`permissions=["delete"]` gate, and the `06-NEW-02` actor-column gap. The companion comment on
the `actions` list (which warns that this exact list is *"the shape that could tempt a future
editor to also register `withdraw_consent_action`"*) must be rewritten in the same edit, since
it now names the wrong outcome. **Rewriting a comment is not touching the field contract.**

**2. Why `permissions=["delete"]` and not an in-body `is_superuser` check.** It is
**strictly stronger**, and it is the framework's own gate rather than a hand-written
second one. Django 5.2's `ModelAdmin._filter_actions_by_permissions`
(`django/contrib/admin/options.py`, verified verbatim against the installed source) does:

```python
def _filter_actions_by_permissions(self, request, actions):
    """Filter out any actions that the user doesn't have access to."""
    filtered_actions = []
    for action in actions:
        callable = action[0]
        if not hasattr(callable, "allowed_permissions"):
            filtered_actions.append(action)   # <-- today's state lands HERE
            continue
        permission_checks = (
            getattr(self, "has_%s_permission" % permission)
            for permission in callable.allowed_permissions
        )
        if any(has_permission(request) for has_permission in permission_checks):
            filtered_actions.append(action)
    return filtered_actions
```

and `@admin.action(function=None, *, permissions=None, description=None)` only sets
`func.allowed_permissions = permissions` **when `permissions is not None`** — so today's
decorator leaves the attribute unset and any `actions` list naming the method would append it
**unconditionally**. That early-`continue` is the landmine this block defuses by shipping
`permissions=` in the same commit as the `actions` entry.

`UserAdmin.has_delete_permission(request, obj=None)` is already `return
request.user.is_superuser` (phase 04). So the decorator buys **both** halves:

- **Absent from the dropdown.** `get_actions(request)` filters the action out, so a plain
  `is_staff` moderator never sees it and `get_action_choices()` never offers it.
- **Refused on a forged POST.** `response_action()` rebuilds
  `action_form.fields["action"].choices = self.get_action_choices(request)` **before**
  `action_form.is_valid()`, so a POST naming an action the requester may not take fails form
  validation, the function is never called, and the moderator gets the *"No action selected."*
  warning with **no user withdrawn**. An in-body check cannot do this: it guards a path the
  framework has already closed, and it is a second place a future edit can forget.

This is also **consistent with the two actions already shipped on this class**:
`deactivate_user` and `reactivate_user` are gated by `permissions=["deactivate"]` →
`UserAdmin.has_deactivate_permission`. This block adds the same mechanism with a different
named predicate; it introduces no new gate style.

Note for the test author: Django does **not** raise `PermissionDenied` here. Assert the
**observable** outcome — target untouched, no `ConsentRecord` written — never the internal.

**3. The service signature: three explicit scalars, no value object, no `HttpRequest`.**
`withdraw_consent` grows exactly the three keyword-only optional parameters the finding
names, and nothing more:

```python
def withdraw_consent(
    user: User,
    *,
    ip_address: str | None = None,
    user_agent: str | None = None,
    session_key: str | None = None,
) -> list[str]:
```

`consent_version` is **not** a parameter: today's withdraw row stores
`ConsentVersion.V1_0.value` because the view never passes one, and a parameter the only
real caller cannot supply is an unused knob. `categories` is **not** a parameter either —
withdrawing revokes every category, so it is a declared constant, not caller input.

**4. Two new public names in `apps/users/services/consent_record.py`** — one writer that
takes resolved values, one resolver that turns a request into one:

```python
WITHDRAWN_CATEGORIES: Final[dict[CookieCategory, bool]] = {
    CookieCategory.ANALYTICS: False,
    CookieCategory.PREFERENCES: False,
}


def record_consent_action_with_context(
    user: User | None,
    choice: ConsentChoice,
    categories: dict[CookieCategory, bool],
    *,
    ip_address: str | None = None,
    user_agent: str | None = None,
    session_key: str | None = None,
    consent_version: str = ConsentVersion.V1_0.value,
) -> ConsentRecord:
    """Create the record from already-resolved HTTP values.

    Anonymises and truncates unconditionally: ``_anonymize_ip`` and ``[:500]`` are
    idempotent, so a caller that pre-processed its values and one that did not store the
    same row. No ``HttpRequest`` ever reaches this function (project rule 3).
    """


def anonymized_client_ip(request: HttpRequest) -> str | None:
    """Resolve the trusted client IP from ``request`` and return it anonymized.

    Returns ``None`` when there is no usable peer: ``get_client_ip`` answers the literal
    ``"unknown"``, which ``_anonymize_ip`` cannot parse.
    """


def record_consent_action(
    user: User | None,
    choice: ConsentChoice,
    categories: dict[CookieCategory, bool],
    request: HttpRequest | None = None,
    consent_version: str = ConsentVersion.V1_0.value,
) -> ConsentRecord:
    # signature UNCHANGED - extracts from the request, then delegates
```

`anonymized_client_ip` exists so the `"unknown"` sentinel has **one** owner. Today it is
mapped to `None` inline in `record_consent_action`, because `_anonymize_ip("unknown")`
raises `ValueError` (`ipaddress.IPv6Address("unknown")`). Once the *view* must supply the
IP, that literal would otherwise be duplicated into `views/consent.py`. The helper keeps it
in one place **and** keeps `HttpRequest` out of `deletion.py`.

**Why the signature has no `HttpRequest`.** `deletion.py` is the **domain** layer. Handing it
a `django.http.HttpRequest` would make `apps.users.services.deletion` import `django.http`,
transitively drag the request/session/middleware graph into every caller that imports the
service — the bot, the management commands, `consent_hard_delete`, the admin — and make the
audit write untestable without a request. Three plain scalars are what the row actually
needs, they are trivially fakeable in a test, and the **only** thing that resolves them from a
request is the one function in the module whose entire job is HTTP context
(`anonymized_client_ip`) plus two attribute reads the **view** does. So the request stays in
the layer that is allowed to have one.

**Two hard constraints on `WITHDRAWN_CATEGORIES`.**

1. **Exactly the two keys the view writes today** — `{ANALYTICS: False, PREFERENCES: False}` —
   which serialise to `{"analytics": False, "preferences": False}`. That is literally what
   `test_consent_records.py::TestConsentRecords::test_withdraw_creates_record` asserts, and it
   is the same two-key shape `consent_accept` / `consent_decline` use. **Do not add
   `CookieCategory.ESSENTIAL`**, even though withdrawal arguably revokes it: adding a key
   turns an existing unchanged test red for no requirement, and `ESSENTIAL` is not part of this
   ledger's category vocabulary anywhere else.
2. It is a `Final` module constant, **not** a parameter and **not** a mutable default. Rule 10.
   The dict is serialised into `ConsentRecord.categories` at call time and is never mutated —
   do not hand a caller a reference it could mutate.

**BLOCK 8's in-flight edit to `record_consent_action`'s BODY must survive.** BLOCK 8 adds a
`request.session.create()` guard so an anonymous record is attributable when the client sent no
session cookie. When this block reduces `record_consent_action`'s body to extraction +
delegation, **carry that guard across into the delegating branch** — do not delete it as
collateral. If `record_consent_action_with_context` is already present when this block starts,
another session did this work: **stop and report** (plan §1.3).

**5. Placement — inside the existing `atomic()`, last, and only for a real withdrawal.**
The call sits **after `soft_delete_user_ads(user)`** and **inside** the same
`with transaction.atomic():` block that BLOCK 9 and BLOCK 13 also edited. Last-in-block is
deliberate: any earlier failure leaves no evidence, and the existing rollback tripwire
(`TestWithdrawConsentAtomicity::test_withdraw_is_atomic_rollback`, which monkeypatches
`soft_delete_user_ads` to raise) then proves the coupling instead of passing vacuously.
The `if user.is_deleted: return []` guard runs first, so a repeat withdrawal writes no
second row and `test_withdraw_idempotent` stays green.

**The exact statement order inside `atomic()` today, verified 2026-10-03.** Preserve every
one of these and append the audit write to the end:

```
if user.is_deleted: return []                     # idempotency guard
now = timezone.now()
LoginToken.objects.filter(telegram_id=...).delete()          # BLOCK 9
SavedSearch.objects.filter(user=user).update(is_active=False) # BLOCK 9
SearchHistory.objects.filter(user=user).delete()              # BLOCK 9
user.save(update_fields=[...ten columns...])                 # BLOCK 9
SupportTicket.objects.filter(user=user).delete()             # BLOCK 13
storage_keys = soft_delete_user_ads(user)
record_consent_action_with_context(...)                      # THIS BLOCK  <- append here
```

(The earlier revision of this section listed BLOCK 9's teardown *after* `user.save`; it is
before. Only the appended position matters, but a wrong map of the region is how a re-read
goes wrong.)

**6. Rejected alternatives.**

| Alternative | Why it lost |
|---|---|
| **Remove the action** | Leaves **no** staff-side consent capability at all, and BLOCK 8 wants an operator-recoverable path. The dead-code policy makes this a *recorded decision*, not a delete recommendation. |
| **An outer `atomic()`** in the action or the view | Moves the transaction boundary into the admin/HTTP layer — the exact layering this block exists to undo — and defers **every** `AdImage` `on_commit` filesystem callback to the end of a long transaction, holding row locks across the whole selection. `AdImage` already registers `on_commit` inside the service's own block, which is the correct TX-then-FS boundary. |
| **A frozen dataclass / `NamedTuple` context** | Three optional scalars with **no invariant to protect** (every combination is legal) and **no second construction site**. Rule 5 forbids the abstraction; a keyword-only signature says the same thing at zero cost. |
| **Passing `HttpRequest` into `deletion.py`** | Project rule 3, separation of concerns — the domain layer would import `django.http`. `consent_record.py` is the HTTP-aware module and stays that way. |
| **Adding the three scalars to `give_consent` / `decline_consent` too** | Their rows are already written correctly, exactly once, by their views, and `test_consent.py`'s `before + 1` delta is scoped to the accept view. Parameters no caller can supply on two more functions is dead code (rule 5). **Only the withdraw path is defective.** |
| **An in-body `if not request.user.is_superuser: return` gate** | Weaker than the decorator and a second place to forget. See mechanism 2. |
| **Adding `CookieCategory.ESSENTIAL` to `WITHDRAWN_CATEGORIES`** | Turns `test_withdraw_creates_record` red for a requirement nobody has written down, and `ESSENTIAL` appears in no other ledger row. Keep the two-key shape the view writes today. |

**7. The known limitation, recorded not fixed (`06-NEW-02`).** `ConsentRecord` has **no
actor column** — its fields are `user`, `session_key`, `consent_given_at`,
`consent_version`, `choice`, `categories`, `ip_address`, `user_agent`. So a
superuser-initiated revocation is evidenced as *"the subject withdrew"*, with nothing
recording that a staff member did it, and the admin-initiated row carries no IP and no
user agent either. **This block ships no migration and invents no column.** It records the
limitation where a reader of the code will hit it — the action's docstring and the
`withdraw_consent` docstring — and states it in the commit body.
BLOCK 10's criterion is that the limitation is **documented**, not that it is absent.

**`06-NEW-02` routing — corrected, because BLOCK 15 has closed.** The register (line ~272)
says *"A schema change BLOCK 12/15 own; BLOCK 10 records the limitation."* BLOCK 15 **landed**
at `fd5201d` and did **not** add an actor column, so half that routing is stale and the
column is currently **unowned**. The honest statement for this commit:

- The column belongs with whoever owns **identity columns on a consent-evidence model in an
  admin class**, which is **BLOCK 12** (`06-PII-106` / `VAL-007`, still open) — it is the only
  block left in this phase that governs which identity columns may render in an admin class,
  and an actor column is exactly such a column: it must land in `ConsentRecordAdmin`'s
  `readonly_fields` and in `pii_inventory`'s declared-column set, or the new column becomes
  the next containment gap.
- The **migration** itself must not be smuggled into BLOCK 12, whose risk level is LOW-MEDIUM
  and whose whole surface is display/search configuration. It is a **new work item** for the
  Tech Lead to schedule, and this block's commit body should say so verbatim rather than
  naming a block that has already closed.
- **Flagged for the coordinator:** the register line itself is outside this block's section
  and was not edited here.

**8. Fix the over-reporting message.** Today:
`f"Withdrew consent for {queryset.count()} user(s)."` reports the *size of the selection*,
not what happened — twenty already-withdrawn users are reported as twenty withdrawals, and
each of those calls was a silent no-op. The action must evaluate the selection **once**,
count what it skipped and what it withdrew, and report **both** in a single message.

**Reuse the vocabulary this module already ships.** `admin.py` already declares
`SKIPPED_ROWS_PREFIX = "Skipped:"` and `ALREADY_IN_STATE_CLAUSE = "already in the requested
state"`, used by `_deactivation_message` to make a partial selection readable. The withdrawal
toast must speak the **same** language — rule 7, follow existing patterns — so a moderator
does not have to learn two vocabularies in one dropdown. The existing tests pin **hard-coded
copies** of those substrings rather than the constants, and the new test must do the same: a
test that imports the constant it is asserting on is a tautology that stays green through any
reword.

**Ordering change the commit body must state.** The row now commits **before**
`logout(request)` runs; today the view writes it **after**, and `logout()` flushes the
session. `session_key` therefore moves from a post-flush value to the identifier that
actually authenticated the action — the unavoidable, and strictly better, consequence of
putting the evidence inside the transaction. Phase 03's `DB-004` and phase 04's BLOCK 6 both
depend on this ordering being deliberate, so **stating the new order in the commit body is not
optional.** The view must therefore read `request.session.session_key` **before** calling
`withdraw_consent`, in the same expression — do not capture it into a local after the call.

**Docs — this block takes no §F edit, and that is a decision not an omission.**
`docs/01-spec/technical-specification.md` is reserved to phase 06 and BLOCKS 4 / 9 / 11 / 14
serialise on it. The §F *Consent audit log* bullet (under `### F. PII & consent (US-A8)`) reads
*"all accept/decline/withdraw actions are inserted as a new row in the `consent_records` table
(never updated)"* and is the **oracle** this change is measured against: it is a promise the
code **breaks today** and **keeps after**. It names **no layer** — it says nothing about which
module writes the row — so moving the write from the view into the service falsifies no
sentence in it. Correcting that bullet would be correcting the target. **No §F edit, and no
`db-schema.md` edit** (nothing in the schema changes). Naming the actor gap in §F belongs with
whoever ships the actor column, in the same commit as the column — see the `06-NEW-02` routing
above; this block is not that commit.

**i18n — deliberately nothing to do, including `gettext_lazy` on the action description.**
The action's `description` is **not** wrapped in `gettext_lazy` today, and this block **does
not** add it. Three independent reasons, all verified:

1. **The gates do not cover the admin layer.** `apps/ads/tests/test_i18n_completeness.py`
   scans **templates only**: `_collect_template_files()` excludes `admin/` in its
   `exclude_subpaths`, and both `test_no_hardcoded_visible_text` and the JS-literal scan and
   `test_template_extraction_coverage` iterate that list. `test_extraction_completeness` is a
   **catalog-vs-catalog** check (every msgid in one `.po` must exist in the others) and
   `test_no_empty_msgstr` only inspects msgids that already exist. Adding no msgid trips
   nothing.
2. **The module has already recorded this decision in writing.** `admin.py` carries an
   explicit comment above `fieldsets` stating that the group headings are bare literals on a
   staff-only surface, that translating them requires `ru`/`bs` msgids, that the `.po`
   catalogs belong to the i18n phase, and that the completeness gate does not cover
   `apps/*/admin.py`. This block follows that decision rather than reopening it.
3. **The sibling actions set the pattern.** `deactivate_user` and `reactivate_user` both use
   bare `description="…"` literals. Wrapping only the withdrawal action would make the
   dropdown half-translated for no gain.

**If you disagree and add `gettext_lazy` anyway**, the obligation is real and expensive: append
the msgid **by hand** to **all three** `.po` files with non-empty `ru` and `bs` msgstr (`en` may
stay empty), and never run a wholesale `makemessages` — a prior Implementor did and it
destructively dropped the Telegram-bot translations (~800-line diff). Phase 05 and phase 14
contend for the same catalogs. **The expected answer is: do not add it.**

**BLOCK 15 composition — verified, and they compose cleanly.** `purge_consent_records`
(`fd5201d`) **anonymises, never deletes**, at a 90-day fingerprint window
(`_FINGERPRINT_RETENTION_DAYS = 90`): `user=None, session_key=None, ip_address=None,
user_agent=""` in **one** statement. The two compose for four reasons:

- **Disjoint trigger paths.** The sweep is a management command gated by
  `AdvisoryLockId.CONSENT_RECORD_SWEEP` (14) and keyed on `consent_given_at < cutoff`. This
  block's write is an `INSERT` on a user-initiated action. Neither touches the other's lock or
  clock.
- **Anonymisation preserves exactly the evidence this block writes to exist** —
  `choice`, `categories`, `consent_version` and `consent_given_at` survive at every age, which
  is the Art. 7(1) point of the ledger.
- **Rows this block writes with no HTTP context are already fingerprint-anonymous.**
  `withdraw_consent(user)` called with no scalars stores `ip_address=NULL` and
  `user_agent=""`, which the sweep's `.exclude(user__isnull=True, session_key__isnull=True,
  ip_address__isnull=True, user_agent="")` correctly skips — no wasted scan, no double-clear.
- **No transaction overlap.** The sweep never runs inside `withdraw_consent`'s `atomic()`, so
  this block adds no lock contention on the sweep and vice versa.

**Consequence to name in the commit body:** a withdrawal made by a **superuser through the
admin** carries `user=<subject>` and **no IP and no user agent** (there is no request to read
them from, and the admin operator's identity is not what the row records). At 90 days the
sweep clears `user` and `session_key` on that row, and what remains is a decision row with no
subject link — which is precisely the `06-NEW-02` gap, now with a concrete worked example.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/users/services/deletion.py` | `withdraw_consent` **only** — signature, the new call inside the existing `atomic()` | **`give_consent` and `decline_consent` are NOT this block's surface** — their rows are already written once by their views. The statement order inside the `atomic()` is load-bearing for BLOCK 9 and BLOCK 13: LoginToken delete → `user.save(update_fields=[…])` → BLOCK 9's teardown → `soft_delete_user_ads(user)` → **this block's audit write**. Keep the transaction boundary where it is |
| `src/backend/apps/users/services/consent_record.py` | **new** `record_consent_action_with_context`, **new** `anonymized_client_ip`, **new** `WITHDRAWN_CATEGORIES`; **modified** `record_consent_action` (delegates), `_anonymize_ip` (**unchanged**) | `_anonymize_ip` already zeroes the IPv4 last octet and masks IPv6 to a /64 — the report's characterisation is accurate; do not change it. Both applications of it are idempotent, so applying it inside the new writer is safe whether or not the caller pre-processed the value |
| `src/backend/apps/users/services/__init__.py` | the re-export list — add **`anonymized_client_ip` only** | The view imports from the package. **Do not** re-export `record_consent_action_with_context`: only `deletion.py` uses it, and it imports the module directly. Rule 5 — do not export what nothing imports |
| `src/backend/apps/users/views/consent.py` | `consent_withdraw` **only** — pass the three scalars, **delete** its `record_consent_action(...)` call | The view keeps the request-derived data; the service keeps the write. **Separation of concerns, not a move of responsibility.** `consent_accept` / `consent_decline` keep their own `record_consent_action(request=request)` calls untouched |
| `src/backend/apps/users/admin.py` | `UserAdmin` — **EXTEND** the existing `actions` list, **decorate** the action with `permissions=["delete"]`, **rewrite** its body + message + docstring, and **replace** the `# DO NOT REGISTER THIS ACTION` comment block and the `actions`-list comment. **The field contract is not this block's** | Phase 04 BLOCK 1 owns `fieldsets` / `add_fieldsets` / `form` / `add_form` / `readonly_fields` / `get_readonly_fields` / `get_fieldsets` / `get_form` / `list_display` / `list_filter` / `search_fields` / the four `has_*_permission` predicates; `f2fd392` added `deactivate_user` / `reactivate_user` to `actions` and `has_deactivate_permission`. §5.4. **Comments may be rewritten; declared attributes may not.** |
| `src/backend/apps/users/tests/test_deletion.py` | **extend** `TestWithdrawConsentAtomicity::test_withdraw_is_atomic_rollback`; add the service-level row assertion | Do **not** write a parallel atomicity test. `test_withdraw_is_atomic_rollback`, `test_withdraw_returns_storage_keys`, `test_withdraw_idempotent` and `test_soft_delete_user_ads_returns_keys_not_count` all live in that class and must pass **unchanged** apart from the one extension |
| `src/backend/apps/users/tests/test_consent_records.py` | **read-only regression target** — needs **no edit** | `TestConsentRecords::test_withdraw_creates_record` uses `ConsentRecord.objects.get()` — that is **already** the double-write tripwire, and it asserts `categories == {"analytics": False, "preferences": False}`, which pins the two-key `WITHDRAWN_CATEGORIES` shape. `TestAnonymizeIp` and `TestConsentRecordDegradedRemoteAddr` pin `_anonymize_ip` and the `"unknown" -> None` mapping through the public entry point |
| `src/backend/apps/users/tests/test_admin_consent_action.py` | **new module** — the wiring, the gate and the honest message | **New on purpose.** `test_admin_pii_containment.py` and `test_admin_change_form.py` are phase-04-owned shared files and must stay byte-unchanged. **Copy the structure of `test_admin_deactivate_user.py`** (module docstring, `pytestmark = [django_db, integration]`, `_post_action` / `_messages_text` helpers, module-local `staff_user` / `superuser` fixtures built with `get_or_create`, hard-coded message substrings). **Use the free telegram_id block `9300003xx`** — `9300000xx`, `9300001xx` and `9300002xx` are taken by the three admin test modules and `test_password_recovery.py`; `conftest.py` owns `900000001/2` |
| `src/backend/apps/users/services/pii_inventory.py` | **read-only reference** | Its `users.ConsentRecord.{session_key,user_agent,ip_address}` erasure entries already declare the columns this block writes, and its declared-column set already carries `consent_version` / `choice` / `categories`. **No entry is added or edited** and `test_pii_inventory.py` stays green |

**Binding constraints**

1. The `ConsentRecord` write happens **inside `withdraw_consent`'s existing
   `transaction.atomic()` block, after `soft_delete_user_ads(user)`**, so state and
   evidence commit or roll back together. **No new transaction is opened anywhere** — not
   in the service, not in the view, not in the action. An outer `atomic()` would defer every
   `AdImage` `on_commit` filesystem callback past the TX-then-FS boundary.
2. **No `HttpRequest` reaches `deletion.py`** (project rule 3). Three optional scalars, no
   context object, no dataclass, no `django.http` import in the domain layer.
3. **No double-write.** `views/consent.py::consent_withdraw` must **stop** calling
   `record_consent_action`. §F promises one row per action; two rows would falsify it.
   `consent_accept` and `consent_decline` keep theirs — and their `record_consent_action`
   import must survive in `views/consent.py`, since the same statement serves all three views
   and only the withdraw call is deleted.
4. `ConsentRecord` is **append-only** — "never updated" is a deliberate Art. 7(1) property.
   No `update()` anywhere.
5. **Do not touch `UserAdmin`'s `fieldsets`, `add_fieldsets`, `form`, `add_form`,
   `readonly_fields`, `get_readonly_fields`, `get_fieldsets`, `get_form`, `list_display`,
   `list_filter`, `search_fields` or any `has_*_permission`.** Phase 04 BLOCK 1 and plan 18 own
   those; six introspection tests in `test_admin_pii_containment.py` pin the change-form
   contract. This block extends `actions` and edits the one action.
6. `permissions=["delete"]` is the gate. **Never** add an in-body `is_superuser` check, and
   **never** ship the `actions` entry without the `permissions=` in the same commit.
7. `_anonymize_ip`'s behaviour is unchanged, and `"unknown"` is mapped to `None` in exactly
   one place — `anonymized_client_ip`.
8. **No migration.** `ConsentRecord` gains no column in this block (`06-NEW-02`).
9. **No `.po` edit, no `gettext_lazy`, and no `docs/01-spec/technical-specification.md` or
   `db-schema.md` edit** in this commit.
10. `test_admin_pii_containment.py`, `test_admin_change_form.py` and `test_consent_records.py`
    stay **byte-unchanged**.
11. **One writer at a time** (§1.3). BLOCK 8 is this block's immediate predecessor and edits
    `give_consent` in the same file; BLOCK 9 (`474a68d`) and BLOCK 13 (`6631ff3`) already
    landed. Re-read `deletion.py`, `consent_record.py` and `views/consent.py` immediately
    before editing. If any carries changes you did not write, or if
    `record_consent_action_with_context` already exists, **stop and report**.
12. **Assert `ConsentChoice.WITHDRAWN`, never the literal `'WITHDRAWN'`.** The enum value is
    `"withdrawn"` (lowercase); a hand-typed uppercase literal is a silently-false test.
13. **Every new `create_test_ad` / `create_test_ads_bulk` call passes `status=` explicitly.**
    `apps/core/tests/test_ad_factory_contract.py::test_no_factory_call_relies_on_a_silent_default`
    AST-walks `src/backend` **and** `src/telegram_bot` and fails the whole phase on any
    factory call that relies on a silent default.

**Implementor task**

```yaml
id: task_06_b10_consent_audit
title: "Write the consent audit row inside the withdrawal transaction and wire the superuser-gated admin action (06-PII-107)"
priority: high
depends_on:
  - task_06_b08_decline_recovery
source_reference: ".ai/plans/06-pii-consent-remediation.md"
source_section: "BLOCK 10 - Make consent revocation self-auditing"
source_blocks: ["BLOCK 10"]
description: >
  withdraw_consent() performs the erasure and writes no ConsentRecord: the Art. 7(1)
  evidence is inserted by the view, after the service returns, outside the service's
  transaction. A crash between the service's commit and the view's insert therefore leaves
  a consent_revoked_at with no matching ConsentChoice.WITHDRAWN row, and any non-view caller
  leaves no evidence at all. Move the write INSIDE withdraw_consent's existing atomic()
  block through a new public record_consent_action_with_context(...) that takes three
  explicit optional scalars instead of an HttpRequest, and register
  UserAdmin.withdraw_consent_action in the EXISTING UserAdmin.actions list under a
  permissions=["delete"] gate. Q-D7 is RESOLVED: wire, do not remove; no context object; no
  outer transaction; no HttpRequest in the domain layer; no migration; no gettext_lazy; no
  .po and no docs edit.
goals:
  - "make the service that performs the erasure also own the evidence, inside its own transaction"
  - "keep exactly one ConsentRecord per consent action (technical-specification.md section F)"
  - "turn the unregistered admin action into a gated, audited capability instead of a landmine"
  - "make the action's operator message report per-user truth instead of the selection size"
  - "record the 06-NEW-02 actor-column limitation without inventing the column"
files:
  - path: "src/backend/apps/users/services/consent_record.py"
    targets:
      - type: function
        name: record_consent_action
      - type: function
        name: record_consent_action_with_context
      - type: function
        name: anonymized_client_ip
      - type: module_constant
        name: WITHDRAWN_CATEGORIES
      - type: function
        name: _anonymize_ip
    semantic_anchors:
      insert_after:
        type: import_statement
        value: "from apps.users.models import ConsentRecord, User"
      replace_in:
        type: function
        name: record_consent_action
  - path: "src/backend/apps/users/services/deletion.py"
    targets:
      - type: function
        name: withdraw_consent
    semantic_anchors:
      insert_after:
        type: import_statement
        value: "from apps.users.models import LoginToken, User"
      replace_in:
        type: function_signature
        value: "def withdraw_consent(user: User) -> list[str]:"
      insert_after:
        type: function_call
        value: "soft_delete_user_ads(user)"
  - path: "src/backend/apps/users/views/consent.py"
    targets:
      - type: function
        name: consent_withdraw
    semantic_anchors:
      replace_in:
        type: function_call
        value: "withdraw_consent(user)"
      insert_before:
        type: function_call
        value: "logout(request)"
  - path: "src/backend/apps/users/services/__init__.py"
    targets:
      - type: module
        name: "__all__"
    semantic_anchors:
      replace_in:
        type: import_statement
        value: "from .consent_record import record_consent_action"
  - path: "src/backend/apps/users/admin.py"
    targets:
      - type: class
        name: UserAdmin
      - type: method
        name: withdraw_consent_action
    semantic_anchors:
      replace_in:
        type: assignment_statement
        value: 'actions = ["deactivate_user", "reactivate_user"]'
      replace_in:
        type: decorator
        value: '@admin.action(description="Withdraw consent for selected users")'
      delete_symbol:
        type: comment_block
        value: "# DO NOT REGISTER THIS ACTION"
  - path: "src/backend/apps/users/tests/test_deletion.py"
    targets:
      - type: class
        name: TestWithdrawConsentAtomicity
  - path: "src/backend/apps/users/tests/test_admin_consent_action.py"
    targets:
      - type: module
        name: test_admin_consent_action
  - path: "src/backend/apps/users/tests/test_consent_records.py"
    targets:
      - type: class
        name: TestConsentRecords
    semantic_anchors:
      replace_in:
        type: function
        name: test_withdraw_creates_record
changes:
  - action: add_code
    file: "src/backend/apps/users/services/consent_record.py"
    symbol: record_consent_action_with_context
    description: >
      A public writer that takes ALREADY-RESOLVED HTTP values instead of an HttpRequest, so
      the domain layer can own the audit write without importing django.http (project rule 3).
      It applies _anonymize_ip and the 500-character user-agent truncation unconditionally -
      both are idempotent, so a caller that pre-processed its values and one that did not store
      the same row, and a caller can never accidentally persist a raw client IP. Keep the
      create() call and the `user if user is not None and user.is_authenticated else None`
      anonymous rule exactly as they are today.
    code_hint: |
      def record_consent_action_with_context(
          user: User | None,
          choice: ConsentChoice,
          categories: dict[CookieCategory, bool],
          *,
          ip_address: str | None = None,
          user_agent: str | None = None,
          session_key: str | None = None,
          consent_version: str = ConsentVersion.V1_0.value,
      ) -> ConsentRecord:
          """Create the record from already-resolved HTTP values.

          No HttpRequest reaches this function (project rule 3). _anonymize_ip and the
          500-character truncation are idempotent, so a pre-processed caller and an
          unprocessed one store the same row.
          """
          return ConsentRecord.objects.create(
              user=user if user is not None and user.is_authenticated else None,
              session_key=session_key,
              consent_version=consent_version,
              choice=choice,
              categories=categories,
              ip_address=_anonymize_ip(ip_address),
              user_agent=(user_agent or "")[:500],
          )
  - action: add_code
    file: "src/backend/apps/users/services/consent_record.py"
    symbol: anonymized_client_ip
    description: >
      The single owner of get_client_ip's "unknown" sentinel. _anonymize_ip cannot parse the
      literal (ipaddress.IPv6Address("unknown") raises ValueError), so it must be mapped to
      None - today that mapping lives inline in record_consent_action, and once the VIEW has to
      supply the IP it would be duplicated into views/consent.py. This helper keeps it in one
      place and keeps HttpRequest out of deletion.py.
    code_hint: |
      def anonymized_client_ip(request: HttpRequest) -> str | None:
          """Resolve the trusted client IP and return it anonymized, or None if no peer."""
          resolved_ip = get_client_ip(request)
          return _anonymize_ip(None if resolved_ip == "unknown" else resolved_ip)
  - action: add_code
    file: "src/backend/apps/users/services/consent_record.py"
    symbol: WITHDRAWN_CATEGORIES
    description: >
      Withdrawing revokes every category, so the map is a declared constant, not caller input
      (project rule 10). It replaces the inline dict the view builds today. It is serialised into
      ConsentRecord.categories at call time and is never mutated. EXACTLY the two keys the
      view writes today - CookieCategory also defines ESSENTIAL, and adding it here turns the
      unchanged TestConsentRecords::test_withdraw_creates_record red for a requirement nobody
      has written down. Do not add ESSENTIAL.
    code_hint: |
      WITHDRAWN_CATEGORIES: Final[dict[CookieCategory, bool]] = {
          CookieCategory.ANALYTICS: False,
          CookieCategory.PREFERENCES: False,
      }
  - action: modify_code
    file: "src/backend/apps/users/services/consent_record.py"
    symbol: record_consent_action
    description: >
      Signature UNCHANGED - record_consent_action(request=...) must keep working for
      consent_accept and consent_decline and for the bot's None entry point, and BLOCK 8 has
      edited its BODY (a request.session.create() guard so an anonymous record is
      attributable) under that freeze. Reduce the body to request extraction plus delegation
      and CARRY BLOCK 8's guard across into the delegating branch - do not delete it as
      collateral. Route the "unknown" mapping through anonymized_client_ip so the sentinel is
      handled in exactly one place. Do NOT change _anonymize_ip. Re-read the function first:
      if record_consent_action_with_context already exists, stop and report.
    code_hint: |
      if request is None:
          return record_consent_action_with_context(
              user, choice, categories, consent_version=consent_version
          )
      return record_consent_action_with_context(
          user,
          choice,
          categories,
          ip_address=anonymized_client_ip(request),
          user_agent=request.META.get("HTTP_USER_AGENT"),
          session_key=request.session.session_key,
          consent_version=consent_version,
      )
  - action: modify_code
    file: "src/backend/apps/users/services/__init__.py"
    symbol: "__all__"
    description: >
      Re-export anonymized_client_ip ONLY - views/consent.py imports from the package. Do NOT
      re-export record_consent_action_with_context: only deletion.py uses it and it imports the
      module directly, which keeps the package import cycle-proof. Rule 5 - do not export what
      nothing imports.
  - action: modify_code
    file: "src/backend/apps/users/services/deletion.py"
    symbol: withdraw_consent
    description: >
      RE-READ THIS FILE IMMEDIATELY BEFORE EDITING. Three writers have already touched it in
      phase 06: BLOCK 9 (474a68d) added the SavedSearch deactivation, the SearchHistory
      deletion and the preferred_city null inside the same atomic() block; BLOCK 13 (6631ff3)
      added the SupportTicket delete; and BLOCK 8 (in flight, this block's predecessor) edits
      give_consent in the SAME FILE - a different function, but the same diff. Expect all
      three. Add the three keyword-only scalars to withdraw_consent's signature (no positional
      change, so every existing call site keeps working) and insert the audit write AFTER
      `storage_keys = soft_delete_user_ads(user)`, INSIDE the same
      `with transaction.atomic():`. Last-in-block is deliberate: an earlier failure leaves no
      evidence, and the existing rollback tripwire then proves the coupling instead of passing
      vacuously. Import from the MODULE (apps.users.services.consent_record), never from the
      package, so no new import edge is created. Open no new transaction and do not move the
      block's boundary. Do not touch give_consent or decline_consent - do not even reformat
      them. Update the withdraw_consent docstring to state that the row is written here, and
      that a staff-initiated revocation is evidenced as "the subject withdrew" because
      ConsentRecord has no actor column (06-NEW-02). That column is a NEW work item for the
      Tech Lead - BLOCK 15 closed at fd5201d without it - so the docstring names the gap, not
      an owning block that has already shipped.
    code_hint: |
      from apps.users.services.consent_record import (
          WITHDRAWN_CATEGORIES,
          record_consent_action_with_context,
      )
      ...
      def withdraw_consent(
          user: User,
          *,
          ip_address: str | None = None,
          user_agent: str | None = None,
          session_key: str | None = None,
      ) -> list[str]:
          ...
              storage_keys = soft_delete_user_ads(user)

              # Art. 7(1) evidence, inside the erasure transaction: a failure above
              # rolls the state change and this row back together.
              record_consent_action_with_context(
                  user=user,
                  choice=ConsentChoice.WITHDRAWN,
                  categories=WITHDRAWN_CATEGORIES,
                  ip_address=ip_address,
                  user_agent=user_agent,
                  session_key=session_key,
              )
  - action: modify_code
    file: "src/backend/apps/users/views/consent.py"
    symbol: consent_withdraw
    description: >
      Two changes and no others. (1) Pass the three request-derived scalars into
      withdraw_consent instead of calling it bare. (2) DELETE the view's
      record_consent_action(...) call - leaving it would write TWO rows per withdrawal and
      falsify the section F promise of one row per action. consent_accept and consent_decline
      keep their own record_consent_action(request=...) calls untouched. Note the ordering
      consequence for the commit body: the row now commits BEFORE logout(request) flushes the
      session, so session_key is the identifier that actually authenticated the action rather
      than a post-flush value.
    code_hint: |
      withdraw_consent(
          user,
          ip_address=anonymized_client_ip(request),
          user_agent=request.META.get("HTTP_USER_AGENT"),
          session_key=request.session.session_key,
      )
  - action: modify_code
    file: "src/backend/apps/users/admin.py"
    symbol: UserAdmin
    description: >
      EXTEND the actions list that plan 18 (f2fd392) already created - it reads
      actions = ["deactivate_user", "reactivate_user"] today. Q-D7 resolved: WIRE, so
      withdraw_consent_action joins it. Writing a fresh actions = [...] statement instead of
      editing the existing one SILENTLY DELETES the two already-shipped operator actions and
      their has_deactivate_permission gate. Edit the existing assignment; add the name to it.
      Touch NOTHING else on the class - fieldsets, add_fieldsets, form, add_form,
      readonly_fields, get_readonly_fields, get_fieldsets, get_form, list_display, list_filter,
      search_fields and the four has_*_permission predicates belong to phase 04 BLOCK 1 and
      plan 18, and are pinned by six introspection tests in test_admin_pii_containment.py.
    code_hint: |
      # The list already exists; EXTEND it, do not replace it.
      actions = ["deactivate_user", "reactivate_user", "withdraw_consent_action"]
  - action: modify_code
    file: "src/backend/apps/users/admin.py"
    symbol: UserAdmin
    description: >
      Rewrite the two comments that now state the opposite of the code. (1) The comment
      immediately above the action - the `# DO NOT REGISTER THIS ACTION` block, citing gate
      G-B, risk R-1 and deferred work D-8 - is resolved by Q-D7 and must be replaced with a
      statement of the decision, the permissions=["delete"] gate and the 06-NEW-02 actor-column
      gap. (2) The comment above the actions list, which warns that this exact list is "the
      shape that could tempt a future editor to also register withdraw_consent_action", now
      names the wrong outcome and must be rewritten to explain why the registration is safe
      (superuser-gated AND self-auditing). Rewriting a comment is not touching the field
      contract; leaving these two in place produces a file in which a comment forbids the
      statement directly beneath it.
  - action: modify_code
    file: "src/backend/apps/users/admin.py"
    symbol: withdraw_consent_action
    description: >
      Add permissions=["delete"] to the existing @admin.action decorator. This is the WHOLE
      gate: Django's _filter_actions_by_permissions dispatches it to
      getattr(self, "has_delete_permission"), which this class already defines as
      `request.user.is_superuser`. It removes the action from get_actions() for a plain is_staff
      moderator - absent from the dropdown - AND makes response_action's form validation
      refuse a forged POST, because response_action rebuilds
      action_form.fields["action"].choices from get_action_choices(request) before calling
      action_form.is_valid(). Do NOT add an in-body is_superuser check and do NOT ship the
      actions entry without the permissions= in the same commit. Do NOT wrap the description
      in gettext_lazy: the i18n gates scan templates and exclude admin/, admin.py already
      records an explicit English-only-staff-surface decision, and the two sibling actions use
      bare literals.
    code_hint: |
      @admin.action(
          description="Withdraw consent for selected users",
          permissions=["delete"],
      )
  - action: modify_code
    file: "src/backend/apps/users/admin.py"
    symbol: withdraw_consent_action
    description: >
      Fix the over-reporting message. It currently reports queryset.count() - the SIZE OF THE
      SELECTION - so twenty already-withdrawn users are reported as twenty withdrawals even
      though every call was a silent no-op. Evaluate the queryset once, count what was
      skipped (is_deleted already True) and what was withdrawn, and report BOTH in one message,
      reusing the module's existing SKIPPED_ROWS_PREFIX and ALREADY_IN_STATE_CLAUSE vocabulary
      so the withdrawal toast reads like the deactivate/reactivate toasts beside it.
      withdraw_consent() stays idempotent and keeps its own guard. Note the queryset is a
      User queryset over the whole table: materialising it with list() is correct here and
      needed twice, but do NOT wrap the loop in transaction.atomic() - withdraw_consent owns
      its own per-user transaction and an outer block would defer every AdImage on_commit
      filesystem callback to the end of the whole selection.
    code_hint: |
      targets = list(queryset)
      already = sum(1 for account in targets if account.is_deleted)
      withdrawn = 0
      for account in targets:
          if account.is_deleted:
              continue
          withdraw_consent(account)
          withdrawn += 1
      message = f"Withdrew consent for {withdrawn} user(s)."
      if already:
          message += f" {SKIPPED_ROWS_PREFIX} {already} {ALREADY_IN_STATE_CLAUSE}."
      self.message_user(request, message)
  - action: modify_code
    file: "src/backend/apps/users/admin.py"
    symbol: withdraw_consent_action
    description: >
      Rewrite the docstring: the action is superuser-gated through permissions=["delete"], and
      ConsentRecord has NO actor column, so a staff-initiated revocation is evidenced as
      "the subject withdrew" with nothing recording that a staff member did it, and the
      admin-initiated row carries no IP and no user agent (06-NEW-02). Record the limitation -
      do not invent the column, do not add a migration. The column is a new work item for the
      Tech Lead: BLOCK 15 closed at fd5201d without it, and BLOCK 12 is the only still-open
      block that governs identity columns on an admin class - so name the gap, not a block that
      has already shipped.
  - action: modify_code
    file: "src/backend/apps/users/tests/test_deletion.py"
    symbol: TestWithdrawConsentAtomicity
    description: >
      EXTEND test_withdraw_is_atomic_rollback - do NOT write a parallel atomicity test. Add
      the assertion that no ConsentChoice.WITHDRAWN row survives the rollback (the row is
      written after soft_delete_user_ads, which the existing monkeypatch makes raise, so the
      assertion is not vacuous). Add the service-level audit-row test: withdraw_consent(user)
      with no view and no request writes exactly one ConsentChoice.WITHDRAWN record for that
      user, with categories {analytics: False, preferences: False}, a null ip_address and an
      empty user_agent. Assert against ConsentChoice.WITHDRAWN - the stored value is
      "withdrawn", lowercase, and a hand-typed 'WITHDRAWN' literal is a silently-false test.
  - action: add_code
    file: "src/backend/apps/users/tests/test_admin_consent_action.py"
    description: >
      A NEW module - deliberately not added to test_admin_pii_containment.py or
      test_admin_change_form.py, which are phase-04-owned shared files that must stay
      byte-unchanged. Copy the STRUCTURE of test_admin_deactivate_user.py verbatim where it
      applies: a module docstring explaining the contract, pytestmark =
      [pytest.mark.django_db, pytest.mark.integration], _post_action / _messages_text helpers,
      module-local moderator and superuser fixtures built with get_or_create so --reuse-db
      works (conftest.py is contended), and message assertions against HARD-CODED substrings
      rather than the imported constants - a test that pins SKIPPED_ROWS_PREFIX by importing
      SKIPPED_ROWS_PREFIX is a tautology that survives any reword. Use the free telegram_id
      block 9300003xx; 9300000xx, 9300001xx and 9300002xx are taken by the three admin test
      modules and test_password_recovery.py.
      Cover: UserAdmin.actions names the action AND still names deactivate_user and
      reactivate_user (the anti-clobber guard); it is ABSENT from get_actions() for the
      moderator and PRESENT for the superuser; a forged POST to admin:users_user_changelist
      as the moderator leaves the target is_deleted False and writes NO ConsentRecord; the
      same POST as the superuser withdraws the target and writes exactly one
      ConsentChoice.WITHDRAWN row; and the message reports both counts for a mixed selection.
      Assert the observable outcome - Django does NOT raise PermissionDenied on a
      permission-filtered action, it returns the "No action selected." warning and never
      calls the function. Do NOT wrap any test in transaction.atomic().
acceptance_criteria:
  - "calling withdraw_consent(user) directly - no view, no request, no admin - writes exactly one ConsentRecord whose choice equals ConsentChoice.WITHDRAWN, whose categories are {analytics: False, preferences: False}, whose user_id is that user's, and whose ip_address is null with an empty user_agent"
  - "a failure inside the withdrawal transaction leaves neither the PII write nor the audit row - TestWithdrawConsentAtomicity::test_withdraw_is_atomic_rollback is EXTENDED with that assertion, not duplicated by a parallel test, and still passes"
  - "the row is written INSIDE withdraw_consent's existing atomic() block, after soft_delete_user_ads(user); no new transaction is opened in the service, the view or the action"
  - "POST /consent/withdraw/ still produces exactly ONE row whose choice is ConsentChoice.WITHDRAWN - TestConsentRecords::test_withdraw_creates_record (which reads through ConsentRecord.objects.get()) passes UNCHANGED, and is the double-write tripwire"
  - "the accept and decline views still write their own rows exactly once - test_consent.py's before + 1 delta and its ACCEPTED / DECLINED row assertions pass UNCHANGED"
  - "a second withdraw_consent(user) call on an already-withdrawn user writes no second row - test_withdraw_idempotent passes UNCHANGED"
  - "UserAdmin.actions names withdraw_consent_action and STILL names deactivate_user and reactivate_user; registering this action did not remove the two already-shipped operator actions"
  - "the action is ABSENT from get_actions(request) for a plain is_staff moderator and PRESENT for a superuser"
  - "a forged POST naming withdraw_consent_action as a plain is_staff moderator leaves the target user is_deleted False and writes NO ConsentRecord"
  - "the same POST as a superuser withdraws the target and writes exactly one ConsentRecord whose choice is ConsentChoice.WITHDRAWN"
  - "for a selection mixing withdrawn and live users the action's message reports both counts and does not claim a withdrawal for a user it skipped"
  - "test_admin_pii_containment.py, test_admin_change_form.py and test_consent_records.py pass UNCHANGED - they are shared with phase 04 and with the accept/decline paths, and are byte-identical after this commit"
  - "apps/users/services/deletion.py passes no HttpRequest, defines no context dataclass, and does not import django.http"
  - "no AdImage on_commit filesystem callback is deferred past the existing boundary - core/tests/test_delete_photo_single_call.py::test_withdraw_consent_delete_photo_once_per_key passes UNCHANGED"
  - "record_consent_action keeps its four-argument signature, still delegates, and still carries BLOCK 8's session-attributability guard: consent_accept, consent_decline and the anonymous/bot paths all behave as before"
  - "the 06-NEW-02 limitation is documented in the action's and the service's docstrings and in the commit body; no migration, no new ConsentRecord column, no actor value invented"
  - "no .po file, no gettext_lazy on the admin description, no technical-specification.md or db-schema.md edit and no template change in this commit"
  - "every create_test_ad / create_test_ads_bulk call introduced here passes status= explicitly - core/tests/test_ad_factory_contract.py::test_no_factory_call_relies_on_a_silent_default walks the whole tree and fails the phase otherwise"
tests_required:
  - "service-level audit row, no view and no request (test_deletion.py)"
  - "rollback coupling - EXTENDED existing atomicity test (test_deletion.py)"
  - "no double-write on the withdraw view; accept/decline and the anon/bot paths unchanged (test_consent_records.py + test_consent.py, both UNCHANGED)"
  - "admin wiring without clobbering the two existing actions (new test_admin_consent_action.py)"
  - "moderator exclusion, forged-POST refusal, superuser success (new test_admin_consent_action.py)"
  - "the action's message reports per-user truth for a mixed selection (new test_admin_consent_action.py)"
  - "phase-04 form-contract regression (test_admin_pii_containment.py + test_admin_change_form.py, UNCHANGED)"
tests_to_run:
  - "src/backend/apps/users/tests/test_deletion.py"
  - "src/backend/apps/users/tests/test_consent_records.py"
  - "src/backend/apps/users/tests/test_consent.py"
  - "src/backend/apps/users/tests/test_consent_context.py"
  - "src/backend/apps/users/tests/test_admin_consent_action.py"
  - "src/backend/apps/users/tests/test_admin_deactivate_user.py"
  - "src/backend/apps/users/tests/test_admin_pii_containment.py"
  - "src/backend/apps/users/tests/test_admin_change_form.py"
  - "src/backend/apps/users/tests/test_pii_inventory.py"
  - "src/backend/apps/users/tests/test_purge_consent_records.py"
  - "src/backend/apps/core/tests/test_delete_photo_single_call.py"
  - "src/backend/apps/core/tests/test_ad_factory_contract.py"
  - "src/backend/apps/search/tests/test_search_cache.py"
  - "src/backend/apps/ads/tests/test_media_security.py"
  - "src/backend/apps/ads/tests/test_i18n_completeness.py"
commands:
  setup: "$dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'"
  test: "$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS=\"src/backend/apps/users/tests --tb=short\" test"
  test_dependent_callers: "$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS=\"src/backend/apps/core/tests/test_delete_photo_single_call.py src/backend/apps/core/tests/test_ad_factory_contract.py src/backend/apps/search/tests/test_search_cache.py src/backend/apps/ads/tests/test_media_security.py src/backend/apps/ads/tests/test_i18n_completeness.py --tb=short\" test"
  test_fresh_schema: "$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS=\"--create-db --tb=short -n auto --maxprocesses=4 --dist loadgroup\" test"
  test_full_users_gate: "$dc run --rm --env PYTEST_SKIP_MARKERS=seed test"
  lint: "uv run ruff check src/backend/apps/users/"
  typecheck: "uv run basedpyright src/backend/apps/users/services/consent_record.py src/backend/apps/users/services/deletion.py"
  notes: >
    PYTEST_OPTS is unquoted in docker/entrypoint-test.sh, so each token is word-split on spaces,
    and setting it REPLACES the defaults (--reuse-db --tb=short --durations=10 -n auto
    --maxprocesses=4 --dist loadgroup) - a targeted run loses xdist parallelism and DB reuse. Never
    use --override-ini=addopts=, which strips --import-mode=importlib. Never run pytest on the host:
    there is no PostgreSQL on localhost:5432. VAL-010 is NOT a defect: concurrent runs share one
    test_mko_bazuna, and ForeignKeyViolation on auth_permission / django_content_type, "database
    test_mko_bazuna does not exist", DuplicateDatabase, ObjectInUse, a foreign-PID DeadlockDetected,
    "assert not self._finalizers" and "Cannot allocate memory" under -n auto are contamination
    artefacts - re-run SERIALLY before reporting a failure. No migration lands here, so
    --create-db is only needed if the local schema drifted; run it once at the end as the gate.
commit:
  message: "feat(users): write the consent audit row inside withdrawal (06-PII-107)"
  stage:
    - "src/backend/apps/users/services/consent_record.py"
    - "src/backend/apps/users/services/deletion.py"
    - "src/backend/apps/users/services/__init__.py"
    - "src/backend/apps/users/views/consent.py"
    - "src/backend/apps/users/admin.py"
    - "src/backend/apps/users/tests/test_deletion.py"
    - "src/backend/apps/users/tests/test_admin_consent_action.py"
  stage_only:
    - "src/backend/apps/users/services/consent_record.py"
    - "src/backend/apps/users/services/deletion.py"
    - "src/backend/apps/users/services/__init__.py"
    - "src/backend/apps/users/views/consent.py"
    - "src/backend/apps/users/admin.py"
    - "src/backend/apps/users/tests/test_deletion.py"
    - "src/backend/apps/users/tests/test_admin_consent_action.py"
  never_stage:
    - "docs/01-spec/technical-specification.md"
    - "docs/02-database/db-schema.md"
    - "src/backend/locale/ru/LC_MESSAGES/django.po"
    - "src/backend/locale/bs/LC_MESSAGES/django.po"
    - "src/backend/locale/en/LC_MESSAGES/django.po"
    - "src/backend/apps/users/tests/test_admin_pii_containment.py"
    - "src/backend/apps/users/tests/test_admin_change_form.py"
    - "src/backend/apps/users/tests/test_consent_records.py"
    - "src/backend/apps/users/tests/test_consent.py"
    - "src/backend/apps/users/tests/test_consent_context.py"
    - "src/backend/apps/users/tests/test_account_state.py"
    - "src/backend/apps/users/services/pii_inventory.py"
    - "src/backend/apps/users/models.py"
    - "src/backend/apps/users/migrations/**"
  body_notes:
    - "Q-D7 RESOLVED - WIRE, not remove. With is_declined / is_deleted / ads_auto_publish now readonly_fields and preferred_city the only writable change-form field, this action is the only staff-side consent mutation left, and BLOCK 8 wants an operator-recoverable path. Removing it would leave none."
    - "The gate is permissions=['delete'] on the decorator, which Django dispatches to UserAdmin.has_delete_permission - already superuser-only. It removes the action from get_actions() for a plain is_staff moderator AND makes response_action's form validation refuse a forged POST (response_action rebuilds action_form.fields['action'].choices from get_action_choices(request) before action_form.is_valid()). No in-body is_superuser check was added, deliberately."
    - "The existing UserAdmin.actions list (deactivate_user, reactivate_user, added by plan 18) was EXTENDED, not replaced. The '# DO NOT REGISTER THIS ACTION' comment that cited gate G-B and deferred work D-8 is resolved by Q-D7 and was replaced with the decision and its limits."
    - "ORDER CHANGED, deliberately: the ConsentRecord now commits BEFORE logout(request) flushes the session, so session_key is the identifier that actually authenticated the withdrawal rather than a post-flush value. This is the unavoidable consequence of putting the evidence inside the transaction. Phase 03's DB-004 and phase 04's BLOCK 6 depend on this ordering being deliberate - this is the note."
    - "The per-user atomic() is unchanged and no outer transaction was added - not in the service, not in the view, not around the admin loop. An outer atomic() would move the boundary into the admin/HTTP layer and defer every AdImage on_commit filesystem callback to the end of a long transaction."
    - "KNOWN LIMITATION (06-NEW-02), NOT FIXED: ConsentRecord has no actor column, so a superuser-initiated revocation is evidenced as 'the subject withdrew' with nothing recording that a staff member did it, and the admin-initiated row carries no IP and no user agent. No migration ships here. The register routed this column to 'BLOCK 12/15', but BLOCK 15 closed at fd5201d without it, so the column is currently unowned: it is a NEW work item for the Tech Lead, with BLOCK 12 (the only still-open block governing identity columns on an admin class) as the natural reviewer, because the column would have to land in ConsentRecordAdmin.readonly_fields and the pii_inventory declared-column set."
    - "Composes with BLOCK 15's purge_consent_records (fd5201d): that sweep anonymises rather than deletes at a 90-day window under advisory lock 14, keyed on consent_given_at, and preserves choice / categories / consent_version / consent_given_at - the decision fields this block exists to write. Trigger paths are disjoint and the two never share a transaction. A row written here with no HTTP context (ip_address NULL, user_agent '') is already fingerprint-anonymous and the sweep correctly skips it."
    - "The section F 'Consent audit log' bullet is now TRUE rather than corrected: it promises one row per accept/decline/withdraw, it names no layer, and the code keeps it. This commit takes NO technical-specification.md edit, no db-schema.md edit and no .po edit."
    - "No gettext_lazy was added to the action description: the i18n gates scan templates and exclude admin/, admin.py already records an explicit English-only staff-surface decision, and the two sibling actions use bare literals."
    - "record_consent_action keeps its signature and now delegates to record_consent_action_with_context; BLOCK 8's session-attributability guard was carried across. No context object was introduced (three optional scalars, no invariant, no second construction site)."
    - "BLOCK 9 (474a68d) and BLOCK 13 (6631ff3) had already written this same atomic() block; their SavedSearch deactivation, SearchHistory deletion, preferred_city null, SupportTicket deletion and the ten-column update_fields all survived this edit intact, and BLOCK 8's give_consent change is a different function in the same file."
    - "The action's message now reports what happened per user (withdrawn count plus an explicit skipped count, reusing the module's existing Skipped:/'already in the requested state' vocabulary) instead of the size of the selection."
extra_context: |
  Q-D7 IS RESOLVED. Do not re-open the wire-or-remove question, do not invent a context object, do
  not open an outer transaction, and do not pass HttpRequest into deletion.py.

  Q-D7 = WIRE, permissions=["delete"], per-user atomic() kept, explicit scalars. The full rationale
  and every rejected alternative are in the plan's BLOCK 10 section. The short version:

    - Removing the action loses. is_declined / is_deleted / ads_auto_publish are readonly_fields
      (phase 04's landed contract), preferred_city is the ONE writable change-form field and is
      pinned writable by test_admin_pii_containment.py::test_change_form_keeps_preferred_city_writable.
      So this action is the ONLY staff-side consent mutation, and BLOCK 8 wants an
      operator-recoverable path.
    - permissions=["delete"] beats an in-body is_superuser check. Django's
      _filter_actions_by_permissions builds getattr(self, "has_%s_permission" % permission) for each
      entry in callable.allowed_permissions; UserAdmin.has_delete_permission is already
      `return request.user.is_superuser`. Two halves follow: the action is filtered OUT of
      get_actions() for a plain is_staff moderator (absent from the dropdown), and response_action()
      rebuilds action_form.fields["action"].choices from get_action_choices(), so a forged POST
      naming it fails form validation and the function is never called. Today the decorator
      carries NO permissions=, so allowed_permissions is unset and the action would be appended
      UNCONDITIONALLY by any actions list that named it - that is the landmine.
    - A frozen dataclass loses: three optional scalars, every combination legal, no invariant to
      protect, no second construction site. Rule 5.
    - HttpRequest in deletion.py loses: project rule 3. consent_record.py is the HTTP-aware module;
      deletion.py imports three plain scalars from it.

  EXACTLY THREE NEW PARAMETERS on withdraw_consent: ip_address, user_agent, session_key - all
  keyword-only with None defaults, so every existing call site keeps working unchanged. Do NOT add
  consent_version (today's withdraw row stores ConsentVersion.V1_0.value because the view never
  passes one - a knob nobody can turn) and do NOT add categories (withdrawing revokes every
  category; it is the WITHDRAWN_CATEGORIES constant).

  THE WRITE GOES LAST INSIDE THE BLOCK, AFTER `storage_keys = soft_delete_user_ads(user)`. The
  existing test_withdraw_is_atomic_rollback monkeypatches soft_delete_user_ads to raise, so placing
  the write after it makes the rollback assertion real; placing it before would make the test pass
  vacuously. Do not move soft_delete_user_ads.

  GIVE_CONSENT AND DECLINE_CONSENT ARE NOT YOUR SURFACE. Their rows are already written exactly
  once by their views and test_consent.py's `before + 1` delta is scoped to the accept view.
  Adding the same three parameters there would be unused code on two more functions (rule 5). The
  finding's "for symmetry" recommendation is declined on the record.

  ANONYMIZATION MUST NOT BE BYPASSABLE. _anonymize_ip and the 500-character truncation are applied
  inside record_consent_action_with_context, not by the caller, so a future caller cannot persist a
  raw client IP. Both are idempotent (_anonymize_ip of an already-zeroed IPv4 is the same string; a
  masked /64 re-masks to itself; truncating 500 chars again changes nothing). get_client_ip's
  "unknown" sentinel must be mapped to None in exactly one place - anonymized_client_ip - because
  ipaddress.IPv6Address("unknown") raises ValueError.

  THE IMPORT DIRECTION. deletion.py imports from the MODULE:
      from apps.users.services.consent_record import WITHDRAWN_CATEGORIES, record_consent_action_with_context
  Never from the apps.users.services package, and never add an apps.search or apps.core.models edge.
  consent_record.py imports apps.core.enums, apps.core.utils.client_ip and apps.users.models - none
  of which import deletion, so there is no cycle. services/__init__.py imports .consent_record before
  .deletion today and must keep that order.

  PHASE 04's FILE, PLUS PLAN 18's. users/admin.py is phase 04 BLOCK 1's file and plan 18
  (f2fd392) added deactivate_user / reactivate_user plus has_deactivate_permission to it.
  EXTEND the existing `actions` list, change the decorator, rewrite the action's body,
  docstring and message, and replace the two comments that now contradict the code. Do NOT
  touch fieldsets, add_fieldsets, form, add_form, readonly_fields, get_readonly_fields,
  get_fieldsets, get_form, list_display, list_filter, search_fields, has_deactivate_permission
  or any has_*_permission. Six introspection tests in test_admin_pii_containment.py pin the
  change-form contract, and that whole file must stay byte-unchanged.
  consent_record.py's sibling ConsentRecordAdmin is NOT yours either - BLOCK 12 owns its
  list_display/search_fields and BLOCK 15 (landed) owns its TTL and session_key scope.

  THREE SHARED TEST MODULES STAY BYTE-UNCHANGED. test_admin_pii_containment.py and
  test_admin_change_form.py belong to phase 04, and test_consent_records.py belongs to the
  accept/decline paths this block does not touch - test_withdraw_creates_record is your
  double-write tripwire and must keep passing untouched. Your new tests go in
  test_admin_consent_action.py, with module-local moderator and superuser fixtures - the same
  pattern test_admin_deactivate_user.py already uses, because conftest.py is contended
  territory. USE THE FREE TELEGRAM_ID BLOCK 9300003xx; 9300000xx, 9300001xx and 9300002xx are
  already taken.

  WHAT A FORGED POST LOOKS LIKE (so the test drives the real thing):
      client.force_login(moderator)
      client.post(reverse("admin:users_user_changelist"), {
          "action": "withdraw_consent_action",
          "index": 0,
          "_selected_action": [str(target.pk)],
          "select_across": "0",
      })
  A moderator needs is_staff AND is_active to reach the admin at all; a superuser needs
  is_staff=True AND is_superuser=True. Assert the OUTCOME - target.is_deleted is False and
  ConsentRecord.objects.count() == 0 - not an exception: Django returns the "No action selected."
  warning, it does not raise PermissionDenied. Do NOT wrap the admin POST in
  transaction=True either - the action opens one transaction per user and a test-level
  transaction would hide whether the row actually commits.

  NO DOCS, NO i18n, NO MIGRATION IN THIS COMMIT.
    - docs/01-spec/technical-specification.md is reserved to phase 06 and BLOCKS 4, 9, 11 and 14
      serialise on it. This block takes none of it, and no db-schema.md edit either (nothing in
      the schema changes). The section F "Consent audit log" bullet is the ORACLE this change is
      measured against - it promises one row per accept/decline/withdraw, it names NO layer, and
      the code keeps the promise after this block. Naming the actor gap in section F belongs with
      whoever ships the actor column.
    - No new customer-facing string, and NO gettext_lazy on the action description. The i18n
      completeness gate scans TEMPLATES and excludes admin/ outright
      (apps/ads/tests/test_i18n_completeness.py::_collect_template_files); admin.py already
      records an explicit English-only staff-surface decision; and the two sibling actions use
      bare literals. Stage no .po file - BLOCK 9 stages all three, phase 05 and phase 14 contend
      for them, and an earlier Implementor's wholesale makemessages destroyed the Telegram-bot
      translations. If you add a msgid by hand anyway, it must be appended to ALL THREE .po files
      with non-empty ru and bs msgstr.
    - No migration. ConsentRecord gains no column (06-NEW-02).

  PII INVENTORY. Do not edit apps/users/services/pii_inventory.py. Its users.ConsentRecord
  session_key / user_agent / ip_address erasure entries (implemented by BLOCK 15's landed sweep)
  already declare the three columns this block writes, and its declared-column set already
  carries consent_version / choice / categories, so nothing is undeclared and
  test_pii_inventory.py must pass unchanged.

  BLOCK 15 COMPOSES, AND YOU SHOULD BE ABLE TO SAY WHY. purge_consent_records (fd5201d)
  anonymises - never deletes - ConsentRecord rows past a 90-day window, clearing user,
  session_key and ip_address to NULL and user_agent to "" in ONE statement, under advisory
  lock 14, keyed on consent_given_at. It preserves choice / categories / consent_version /
  consent_given_at at every age, which are precisely the decision fields this block exists to
  write. The trigger paths are disjoint and the two never share a transaction. A row this
  block writes with no HTTP context already carries ip_address NULL and user_agent "", so the
  sweep's exclusion clause correctly skips it.

  THE AD_FACTORY CONTRACT IS A WHOLE-TREE GATE. apps/core/tests/test_ad_factory_contract.py
  AST-walks src/backend AND src/telegram_bot and fails the entire phase on any create_test_ad /
  create_test_ads_bulk call that relies on a silent default. If you add ads to a test, pass
  status= explicitly. Your tests should not need ads at all.

  SERIAL ORDER AND THE STOP RULE. THREE blocks have already written this atomic() block -
  BLOCK 9 (474a68d), BLOCK 13 (6631ff3) and, if it has landed, BLOCK 8's give_consent in the
  same file. You are the NEXT writer, not the only one. Re-read deletion.py, consent_record.py
  and views/consent.py IMMEDIATELY before editing and expect BLOCK 9's SavedSearch deactivation,
  SearchHistory deletion and preferred_city null, BLOCK 13's SupportTicket deletion, and the
  ten-column update_fields. If any file carries changes you did not write, or if
  record_consent_action_with_context is already present, STOP AND REPORT - do not layer on top,
  do not git checkout, do not stash (plan section 1.3). Never implement this block in parallel
  with BLOCK 8.

  ASSERT THE ENUM, NOT A HAND-TYPED LITERAL. ConsentChoice.WITHDRAWN == "withdrawn", lowercase.
  An assertion written as choice='WITHDRAWN' is silently false against this codebase and would
  pass a broken implementation for the wrong reason. Same for ConsentVersion.V1_0.value.

  VERIFY EVERY PATH BEFORE YOU NAME IT. Every target in tests_to_run was confirmed to exist
  against the tree on 2026-10-03, including the three cross-app callers that invoke
  withdraw_consent: core/tests/test_delete_photo_single_call.py::
  test_withdraw_consent_delete_photo_once_per_key (the on_commit boundary),
  search/tests/test_search_cache.py and ads/tests/test_media_security.py. If you add a test
  file, put it in apps/users/tests/.
```

**Tests required** (logic and component interaction — plan §1.5; no line numbers, no counts of
private names, no presence-of-symbol assertions as *ends* in themselves)

1. **The service owns its evidence.** `withdraw_consent(user)` with no view, no request and no
   admin writes **exactly one** `ConsentRecord` whose `choice` equals `ConsentChoice.WITHDRAWN`,
   whose `user_id` is that user, whose `categories` is `{"analytics": False,
   "preferences": False}`, and whose `ip_address` is **null** with an empty `user_agent`. This
   is the test the report asks for and it is **red** before this block.
2. **Transaction coupling.** `TestWithdrawConsentAtomicity::test_withdraw_is_atomic_rollback`
   is **extended**, never duplicated: its monkeypatch makes `soft_delete_user_ads` raise
   *after* the audit write, so the added assertion that no withdrawn row survived is the
   proof that the row is inside the transaction. A **second** user whose withdrawal succeeds in
   the same test module proves the positive control.
3. **One row per action, no double-write.** `POST /consent/withdraw/` yields exactly one
   withdrawn row — `TestConsentRecords::test_withdraw_creates_record` already asserts this
   through `ConsentRecord.objects.get()` and needs **no edit**. The accept and decline paths
   keep writing their own rows; `test_consent.py`'s `before + 1` delta and its accepted /
   declined **zero-count** assertions pass unchanged.
4. **The gate, both halves.** `UserAdmin.actions` names the withdrawal action **and still
   names** `deactivate_user` / `reactivate_user`; the action is **absent** from
   `get_actions(request)` for a plain `is_staff` moderator and **present** for a superuser; a
   forged POST to `admin:users_user_changelist` as the moderator leaves the target
   `is_deleted is False` with **no** `ConsentRecord` written; the same POST as a superuser
   withdraws the target and writes exactly one row. The assertion is the **outcome** — Django
   returns the *"No action selected."* warning, it does not raise `PermissionDenied`.
5. **The message tells the truth.** A selection of one live user plus one already-withdrawn user
   produces a message naming both counts, in the module's existing `Skipped:` vocabulary, and
   the skipped user's `consent_revoked_at` is unchanged.
6. **Regressions, all unchanged.** `test_consent_records.py`'s matrix (anonymous row has
   `user_id IS NULL`, `ip_address` anonymised, `user_agent` truncated to 500),
   `test_admin_pii_containment.py` and `test_admin_change_form.py` (phase-04-owned,
   byte-unchanged), `test_admin_deactivate_user.py` (plan-18-owned — the anti-clobber guard),
   `test_pii_inventory.py`, `test_purge_consent_records.py` (BLOCK 15's composition check),
   `test_ad_factory_contract.py`, and the three cross-app `withdraw_consent` callers —
   `core/tests/test_delete_photo_single_call.py`, `search/tests/test_search_cache.py`,
   `ads/tests/test_media_security.py`.

**Risk and rollback**

- *Risk (transaction ordering):* the row now commits **before** `logout(request)`, so
  `session_key` moves from a post-flush value to the identifier that actually authenticated the
  withdrawal. This is inherent to the fix, not an accident. Mitigation: the named commit-body
  note above; phase 03's `DB-004` and phase 04's BLOCK 6 must be told.
- *Risk (shared function, three prior writers):* BLOCK 9, BLOCK 13 and — if it has landed —
  BLOCK 8 have all written this same `atomic()` block, and BLOCK 8 touched the same **file**.
  Mitigation: the serial ownership rule above, the mandatory re-read immediately before
  editing, the "do not reformat `give_consent`" instruction, the stop rule, and a Validator
  task.
- *Risk (clobbering the existing actions list):* writing `actions = [...]` as a new statement
  instead of editing the existing one silently deletes `deactivate_user` / `reactivate_user` and
  their `has_deactivate_permission` gate — an incident-response regression shipped as a GDPR
  fix. Mitigation: the anti-clobber acceptance criterion and an explicit test in the new module.
- *Risk (phase 04's file, plus plan 18's):* `users/admin.py` is phase 04 BLOCK 1's file and plan
  18 added the deactivate/reactivate pair to it. This block touches **only** the `actions` list,
  the one decorator, the one action, and two comments. §5.3. The external gate is **discharged**
  — the field contract landed (`a19a0ee`), which is what guarantees every consent-state
  transition now goes through the service that writes the row.
- *Risk (registering the action):* turning dead code into a live capability is a scope expansion.
  Mitigation: the recorded Q-D7 decision, the `permissions=["delete"]` superuser gate shipped
  in the **same commit** as the registration (the report's unsafe sequence 5, inverted), and the
  audit write landing in that same commit.
- *Known limitation, shipped not hidden:* `06-NEW-02` — no actor column. BLOCK 10's criterion is
  that it is **documented**, not that it is absent. The column is currently **unowned**: the
  register routed it to "BLOCK 12/15", BLOCK 15 closed at `fd5201d` without it, and it is a new
  work item for the Tech Lead with BLOCK 12 as the natural reviewer.
- *Rollback:* a straight revert. The extra `ConsentRecord` rows already written are
  append-only and are **not** removed by the revert — that is correct (an audit ledger keeps
  what it recorded) and must be stated.

---

### BLOCK 11 — Gate ad creation on storage consent, and correct the retention wording (06-PII-109, Q-D3)

| | |
|---|---|
| **Findings owned** | `06-PII-109` (**the real work is the create-time gate**), `VAL-009` (**already discharged — a verification, not a work item**) |
| **Depends on** | **BLOCK 10** (`deletion.py` serial — this block no longer writes `deletion.py`, so the edge is a *read*, not a write-order hazard), and BLOCK 13 (`can_store_personal_data` must exist) |
| **Blocks** | BLOCK 13 (the six `ads.Ad` inventory entries) |
| **Priority** | P1 — a **live** storage-consent hole on both tiers |
| **Risk level** | **MEDIUM** — no user content is destroyed (option (b), decided); the risk is **blast radius**: the gate touches shared fixtures and a service every ad test calls |
| **Required agents** | **Auditor · Planner · Validator**. **Q-D3 is RESOLVED by the Tech Lead — option (b). No Researcher gate remains on this block.** Validator is required: the new gate must be shown **red against the pre-fix code** before it goes green |

**Q-D3 is DECIDED — option (b): correct the specification. Do NOT scrub ad text.**
The 30-day `consent_hard_delete` sweep is the "warning" Q-D2 refers to. The evidence,
all verified against the tree:

- `apps/core/management/commands/consent_hard_delete.py` runs on the hourly scheduler
  (`apps/core/utils/scheduler.py` registers `consent_hard_delete`; advisory lock
  `AdvisoryLockId.CONSENT_HARD_DELETE`) over
  `User.objects.filter(consent_revoked_at__isnull=False, consent_revoked_at__lt=now−30d)`
  and finishes with `queryset.delete()`. `Ad.user` is
  `models.ForeignKey("users.User", on_delete=models.CASCADE, related_name="ads")`
  (`apps/ads/models.py`), so at day 30 the seller's `Ad` rows, their text and their
  `AdImage` rows are physically destroyed, and the `pre_delete` signal schedules the
  media-file removal via `transaction.on_commit`. **"Delete all their personal data" is
  already satisfied by shipped, tested code**
  (`apps/core/tests/test_sweep_consent.py`, `apps/core/tests/test_delete_photo_single_call.py`).
  This block is not closing a leak; it is **correcting a false sentence**.
- `privacy.html` §6 **already publishes exactly option (b)'s policy**, and it is already
  translated: under "Erased within 30 days" — *"The remaining account record and the
  advertisements and images still linked to it are permanently removed by the 30-day
  erasure sweep."* (`ru` and `bs` both carry non-empty `msgstr`) — and under
  "Retained, and why" — *"Moderation records and the text of advertisements already
  reviewed are retained for trust and safety and for the resolution of disputes."*
  So `technical-specification.md` §F's single word **"Anonymized"** is the **only**
  false sentence in either document. Option (a) would make a **published, translated**
  policy false — a compliance regression traded for the erasure.
- Option (a) was also rejected on its own evidence: it accelerates a scheduled
  destruction by 30 days, produces a **half-anonymised row** (text gone, while
  `AdImage` rows, `ModeratorActionLog` rows and `DailyAdMetrics` remain attached — a
  worse artefact for an auditor than either honest end state), and destroys
  dispute-resolution evidence that `privacy.html` promises stays reviewable.
- Option (c) — hard-delete the ads **at withdrawal** — was **rejected outright**.
  `AdImage`, `AdFeature` and `AdFavorite` are `on_delete=models.CASCADE` off `Ad`, and
  `DailyAdMetrics` (`apps/analytics/models.py`) and `SavedSearchNotification`
  (`apps/search/models.py`) cascade off `Ad` too. Deleting at withdrawal would destroy
  **buyers'** favourites, the seller's own statistics and other users' alert records in
  order to erase first-party data — to reach an endpoint that already exists at day 30.
  It is dominated by (b) on every axis.
  *(Correction to the audit's cascade list: there is **no** `AdModeratorPriority` model
  in this repository — do not cite one. `AnalyticsEvent.user_id` is `SET_NULL`, not
  cascade.)*

**The actual defect this block closes: the create-time gate does not exist.** Q-D3's
ratified rule is *"a user who has **not consented** to personal-data storage must not
be allowed to create an advertisement; on attempting, show a clear message that consent
is required."* No tier implements it:

- **`can_publish_ad` is dead code.** `apps/users/services/account_state.py::can_publish_ad`
  has **zero production call sites** — the only references in the tree are the re-export
  in `apps/users/services/__init__.py` and the flag matrix in
  `apps/users/tests/test_account_state.py::TestCanPublishAd`. It is the obvious predicate
  and nothing calls it. Its **disposition is decided in this block: use it, do not delete
  it** (see "Predicate" below).
- **Bot, entry point only.** `AccountStateMiddleware.__call__` reaches
  `_evaluate_publish_permission` **only** when `text.strip().lower() == "/post"`
  (`src/telegram_bot/middlewares/permissions.py`), and that method reads
  **`ads_auto_publish` only** — it never consults `consent_given_at`.
  `_evaluate_user_state` reads `is_active` / `is_banned` / `is_deleted` / `is_declined` /
  `consent_revoked` and also never reads `consent_given_at`. So a registered bot user
  with `consent_given_at IS NULL` walks straight into the FSM, and `cmd_post`
  (`telegram_bot/handlers/ad_create/entry.py`) immediately calls `create_draft_ad`.
- **Bot, persistence ungated.** `apps/ads/services/submission.py::submit_ad` is the one
  writer both tiers share, and it has no consent term. Every FSM step after `/post` —
  category, city, text, price, photos, preview — runs unguarded, so the entry-point check
  protects nothing once the dialog is open.
- **Web, entirely ungated.** `login_status`
  (`apps/users/views/consent.py::login_status`) calls `can_login(user)` only, and
  `can_login` deliberately omits `consent_given_at` — so a never-consented registered
  user receives a **full web session**. Every seller write view then gates on
  `@login_required` plus ownership alone: `ad_edit`, `ad_archive`, `ad_reactivate`
  (`apps/ads/views/edit.py`) and `dashboard` (`apps/ads/views/dashboard.py`). A user
  with `consent_given_at IS NULL` can rewrite a live ad's title and description over HTTP
  today. `ad_delete` is deliberately **not** gated: deleting one's own ad reduces stored
  data and can never work against the subject.

**`VAL-009` is ALREADY DISCHARGED — no new FTS assertion is required, and no
mechanism may be built.** `apps/ads/tests/test_search_triggers.py::TestSearchVectorTrigger::test_title_update_refreshes_all_search_vectors`
is **green today** and is exactly the assertion this plan misfiled into
`test_setup_search_triggers.py`. The trigger is `BEFORE INSERT OR UPDATE ... FOR EACH
ROW` (installed in `apps/ads/migrations/0001_initial.py` and re-installed idempotently by
`setup_search_triggers`), and it folds all six text columns into **all four** vectors on
every write. There is no `title_ru` column — the Russian base *is* `title` — so a stale
vector is structurally impossible. The only genuinely uncovered form is the bulk
`QuerySet.update()` statement; that would be worth **one** assertion in
`test_search_triggers.py` **if** this block wrote such an update. **Under option (b) it
writes none** — the block touches no ad column at all. The obligation is discharged.

*(Unrelated staleness found while verifying this, owned by BLOCK 13 — **not edited
here**: `docs/02-database/db-schema.md` still says "Legacy `search_vector` retained
during dual-write transition (to be dropped in Phase 3)". The transition is over; the
trigger writes all four vectors on every row.)*

**The decision, and the deviation record it obliges**

Option **(b)** is chosen, as recorded above. The obligations option (b) carries — and
this block discharges all of them:

1. **Correct the one false sentence** in `docs/01-spec/technical-specification.md` §F
   ("Post-withdrawal erasure"). Exact current text, quoted verbatim:

   > `Anonymized ads (post-withdrawal, pre-hard-delete) persist for 30 days only — NOT the 120-day purge_deleted_ads window`

   Replace that bullet with **exactly this wording** (keep the backticked identifiers and
   the em-dash rhythm of the surrounding bullets):

   > `Ads are soft-deleted (status=DELETED) on withdrawal and are hidden immediately from listings, search and direct URLs; they are NOT anonymised. The user-authored text and images are retained for the 30-day grace period so moderation records stay reviewable for dispute resolution, then hard-deleted by the consent_hard_delete sweep via Ad.user on_delete=CASCADE — NOT the 120-day purge_deleted_ads window, which never sees them.`

   This is **one bullet**, and it is **the only edit** this block makes to that file. The
   parent bullet already states the CASCADE deletion, and the adjacent bullets (the
   120-day `purge_deleted_ads` sweep and the moderation records) are already accurate.
   **No `privacy.html` edit and no i18n work under option (b)** — its claims are already
   true, and editing it would be rewriting a compliant published policy to match a bug.
2. **Record the deviation as a test, not as prose.** A test named as documenting the
   deviation asserts the *stated* behaviour: after `withdraw_consent`, the ad is
   `status=DELETED`, is absent from `ListingsQuery.build_queryset`, 404s from
   `ad_detail`, and **retains** its `title`/`description` byte-for-byte.
3. **`rejected_reason` is NOT a target of this block.** It is a module-level display
   helper at `apps/ads/admin.py::rejected_reason` that reads
   `obj.moderation_logs.filter(action_type=REJECT).last().reason[:100]` — there is no
   `Ad.rejected_reason` **column**. BLOCK 16 already made that content write-time
   redacted, `apps/users/tests/test_pii_inventory.py::test_no_entry_names_ad_rejected_reason`
   exists solely to forbid naming it, and
   `apps/moderation/tests/test_moderation_reason_redaction.py::test_rejected_reason_helper_does_not_rewrite`
   pins its behaviour. **This plan's earlier mention of scrubbing it was a plan defect;
   it is dropped.**
4. **The plan's `test_ads_admin.py` did not exist.** The real `AdAdmin` test modules are
   `apps/ads/tests/test_admin_change_form.py` (phase 05's, 13 tests) and
   `apps/moderation/tests/test_admin_ban_privilege_guard.py`. Under option (b) **no admin
   surface changes**, so `tests_to_run` names `test_admin_change_form.py` as a
   no-regression target and does **not** name the moderation module — it is unrelated to
   this block. This was a second plan defect; corrected.
5. **The validated audit's risk claim was false.** It said a scrub "**breaks**
   `test_deletion.py` ad-content assertions". `apps/users/tests/test_deletion.py`
   contains **zero** content assertions — every ad assertion is on `status`,
   `deleted_at`, `updated_at` or returned storage keys
   (`TestWithdrawConsentSoftDeletesAds`, `TestWithdrawConsentAtomicity`). Under option
   (b) **nothing in any test module breaks.** That module is run unchanged, as a
   regression, and must stay green.

**Predicate — the composition that resolves `can_publish_ad`**

`can_publish_ad` reads exactly three flags: `is_banned`, `is_deleted`,
`ads_auto_publish`. It does **not** read `is_declined`, `is_active`,
`consent_revoked_at` or `consent_given_at` — so it is *weaker* than
`can_store_personal_data` on the axis this block needs, and *stronger* on
`ads_auto_publish` (which `can_store_personal_data` deliberately omits: a publishing
restriction is orthogonal to whether data may be stored). Neither alone is the rule;
their conjunction is. **Disposition: USE it, do not delete it.**

- Add **one** exported predicate to `apps/users/services/account_state.py`, next to the
  other three, defined as the composition `can_publish_ad(user) and
  can_store_personal_data(user)`. That makes `can_publish_ad` live (its dead-code
  defect closes) and gives both tiers one shared authority, in the module that is
  already the declared home of every account predicate.
- **Do not mutate `can_publish_ad` itself, and do not mutate `can_store_personal_data`.**
  Folding the consent term into `can_publish_ad` would break
  `test_account_state.py::TestCanPublishAd::test_declined_user_can_publish`, which
  asserts `can_publish_ad(declined_user) is True`. Composition avoids that re-pin
  entirely (see "Rule-2"). **`account_state_q` is contract-frozen** — BLOCKS 6/7 are
  validated against its five conjuncts and BLOCK 7's test mutates it. Do not touch it.
- **Do not add `is_active`.** Neither `can_publish_ad` nor `can_store_personal_data`
  reads it, and that is correct: Django's `ModelBackend` revokes the web session for an
  inactive user (`@login_required` covers the web tier) and `_evaluate_user_state`
  refuses one on the bot tier. Adding it would silently re-close the plan-19 support
  carve-out, exactly as `can_store_personal_data`'s docstring warns.
- A declined user is refused by `can_store_personal_data` on both tiers, and on the bot
  is already refused earlier and more clearly by `_evaluate_user_state`. `give_consent`
  clears `is_declined` and restores `ads_auto_publish=True` (`deletion.py::give_consent`),
  so **re-consent restores posting with no special-casing** — which is also why
  `test_give_consent_after_decline_restores_publishing` keeps passing unchanged. The gap
  is specifically the **never-consented** user.

**Gate points — two refusals on the bot, four on the web (mirroring `support.py`)**

The precedent to copy is `src/telegram_bot/handlers/support.py`: a module-level
`gettext_lazy` constant (`SUPPORT_CONSENT_REQUIRED_MESSAGE`) gating **twice** — refuse at
the entry point, re-refuse at persistence, the latter returning `None` as the single
refusal signal, with the FSM reset on refusal. The ad path needs the same two-point
shape, because the entry point is the only thing a mid-FSM update bypasses.

| Tier | Gate point | Shape |
|---|---|---|
| Bot — entry | `AccountStateMiddleware._evaluate_publish_permission` | Keep the `ads_auto_publish` branch **first** (it carries its own message, and `test_post_backfill_uses_the_same_row_as_the_state_gate` asserts on that wording), then delegate the boolean to the shared predicate and answer the consent message |
| Bot — persistence | `apps/ads/services/submission.py::submit_ad` | New `SubmitAdOutcome` member carrying the message in `errors` (the existing refusal-signal convention — `errors` is already `gettext_lazy`-wrapped at the source and `str()`-ed by both callers). **Return before any write**, so the refusal costs nothing and no staged media is promoted |
| Bot — dialog | `telegram_bot/handlers/ad_create/submit.py::process_preview` | Answer the outcome's message and clear the FSM — the shape `handle_support_message` uses for `ticket is None` |
| Bot — *not* gated | `telegram_bot/services/ad_data/orm.py::create_draft_ad` | **Deliberately left open.** It writes an empty `DRAFT` row holding no user-authored text and no photos, and both refusals that matter already sit either side of it. Gating it would change a published async signature (`Ad` → `Ad | None`) at three call sites, for a row that contains no personal data |
| Web | `apps/ads/views/edit.py::ad_edit`, `::ad_archive`, `::ad_reactivate`, `apps/ads/views/dashboard.py::dashboard` | `HttpResponseForbidden` with a **distinct** clear message — the same shape the three views already use for the ownership refusal, and the same 403 precedent `consent_accept` / `consent_decline` use. There is no GET consent page to redirect to: `apps/users/urls.py` exposes only `consent/accept/`, `consent/decline/`, `consent/withdraw/` as POST endpoints |
| Web — *not* gated | `apps/ads/views/delete.py::ad_delete` | Deleting one's own ad reduces stored data; it can never work against the subject |

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/users/services/account_state.py` | new module-level predicate composed from `can_publish_ad` + `can_store_personal_data` | **Do not edit `can_publish_ad`, `can_store_personal_data`, `can_login`, `get_account_state` or `account_state_q`.** `account_state_q` is contract-frozen by BLOCKS 6/7. The new predicate is additive and re-exported from `apps/users/services/__init__.py` alongside the others |
| `src/backend/apps/ads/services/submission.py` | `submit_ad`, `SubmitAdOutcome`, `SubmitAdResult` | The persistence refusal. One new enum member + one early `return` **before** the staged-media plan, the thumbnail generation, and the `transaction.atomic()` block, so a refusal performs no filesystem work and promotes nothing |
| `src/telegram_bot/middlewares/permissions.py` | `AccountStateMiddleware._evaluate_publish_permission` | The entry refusal. Pure function, no DB access, no mutation — preserve both properties (docstring pins them) |
| `src/telegram_bot/handlers/ad_create/submit.py` | `process_preview` | Renders the new outcome's message and clears the FSM |
| `src/backend/apps/ads/views/edit.py` | `ad_edit`, `ad_archive`, `ad_reactivate` | Three guards, one distinct message. Preserve each view's existing ownership-`403` wording and its lock-timeout re-render path |
| `src/backend/apps/ads/views/dashboard.py` | `dashboard` | One guard. Note it is a **GET** page, so the refusal is a 403, not a redirect — see the gate table |
| `src/backend/apps/users/services/pii_inventory.py` | the six `ads.Ad` text entries | **Contended with BLOCK 13 — touch only those six entries.** Rewriting the four `core.SupportTicket` entries would break BLOCK 13's guard |
| `src/backend/conftest.py`, `src/telegram_bot/tests/conftest.py` | `seller` / `user` / `buyer` / `make_user`, and the bot `user` / `seller` fixtures | **Every one of these leaves `consent_given_at` NULL today.** See binding constraint 1 — this is the block's largest blast radius |
| `src/backend/locale/{ru,bs,en}/LC_MESSAGES/django.po` | the two new msgids | `ru` and `bs` `msgstr` must be non-empty (`test_no_empty_msgstr`); `en` may stay empty |
| `docs/01-spec/technical-specification.md` | §F's "Anonymized ads" bullet — **one bullet only** | Reserved to phase 06 and already edited by BLOCKS 4/9/14. Re-read the bullet before editing; take nothing else |
| `src/backend/apps/ads/tests/test_ad_consent_gate.py` | **new module** | The create-time gate and the deviation record. Placed in `ads/tests` because every assertion is about ad creation |
| `src/backend/apps/users/tests/test_pii_inventory.py` | **one new guard test** | Mirrors `test_support_ticket_entries_are_delete_row`. The rest of the module must pass unchanged |
| `src/backend/apps/users/tests/test_deletion.py` | **read only — no edit** | Run as a regression. It has zero content assertions and must stay byte-identical |
| `docs/02-database/db-schema.md` | **not edited — BLOCK 13's file** | Stale `search_vector` "dual-write transition" note is recorded above and left for that block |

**Binding constraints**

1. **The generic test fixtures must gain `consent_given_at`, and it must survive
   `--reuse-db`.** `seller` / `user` / `buyer` in `src/backend/conftest.py` and `user` /
   `seller` in `src/telegram_bot/tests/conftest.py` all use
   `get_or_create(telegram_id=…, defaults={…})`, so a row left over from a previous
   `--reuse-db` run **never receives a new default**. Set the value explicitly after the
   `get_or_create` when it is NULL (or require `--create-db`, which the command list
   includes). Without this, every existing test that posts to `ad_edit` or calls
   `submit_ad` starts failing on a consent refusal — not on a real defect. `make_user`
   should take the same default through its `**overrides` path so
   `test_deletion.py::test_give_consent_rejected_on_soft_deleted_user` (which compares
   `consent_given_at` for equality, not against `None`) still passes.
2. **Reuse `can_store_personal_data`; never re-derive the rule.** It already contains the
   `user.consent_given_at is not None` term. **Do not mutate `account_state_q`** (BLOCKS
   6/7 are validated against its five conjuncts) and **do not mutate `can_publish_ad` or
   `can_store_personal_data`** — compose them.
3. **`submit_ad` refuses before it writes.** The new outcome's `errors` entry is the
   user-facing message, `gettext_lazy`-wrapped at the source like its siblings, and both
   callers already `str()` it. Do not add a second, eager `gettext` at the call site.
4. **The bot's `ads_auto_publish` branch stays first** in `_evaluate_publish_permission`.
   `test_post_backfill_uses_the_same_row_as_the_state_gate` asserts the answer contains
   `"publishing"`, and reordering would also give a restricted user the wrong remedy.
5. **Two refusals, not one.** Refusing only at `/post` protects nothing once the dialog is
   open, which is the shape `support.py` already solved and the reason this block exists.
6. **`Ad.transition_to`, `ALLOWED_TRANSITIONS`, the DELETED semantics, `deletion.py` and
   `AdAdmin` are all untouched.** Phase 05 owns the transition; BLOCK 10 owns
   `deletion.py`. Under option (b) this block writes no migration, no data backfill, no
   ad column and no admin configuration.
7. **No new FTS assertion and no re-derivation mechanism** — `VAL-009` is discharged and
   this block writes no bulk `QuerySet.update()` on `ads`. Do not add one anyway "for
   safety": a speculative assertion in `test_setup_search_triggers.py` would be the exact
   misfiling this block is correcting.
8. **Do not widen to `privacy.html`, `db-schema.md` or `doc-maintenance-rules.md`.** The
   deviation is recorded as a named test (item 2 above), not as a new prose section; the
   policy page is already true.

**Implementor task**

```yaml
id: task_06_b11_ad_consent_gate
title: "Gate ad creation on storage consent and correct the retention wording (06-PII-109)"
priority: high
depends_on: [task_06_b10_consent_audit_in_service, task_06_b13_support_ticket_deletion]
source_reference: ".ai/plans/06-pii-consent-remediation.md"
source_section: "BLOCK 11 - Gate ad creation on storage consent and correct the retention wording"
source_blocks: ["BLOCK 11"]
description: >
  Q-D3 is decided: OPTION (b), correct the specification clause. Do NOT scrub ad
  text - consent_hard_delete already hard-deletes the Ad rows, their text and their
  photos at day 30 through Ad.user on_delete=CASCADE, and privacy.html already
  publishes that policy in ru/bs/en, so technical-specification.md's single word
  "Anonymized" is the only false sentence in either document. This block therefore
  (1) corrects that one bullet, (2) builds the create-time storage-consent gate that
  does not exist on either tier - a user with consent_given_at IS NULL may not
  create or rewrite an ad - reusing can_store_personal_data composed with the
  currently-dead can_publish_ad, and (3) re-declare the six ads.Ad text inventory
  entries from CLEAR to DELETE_ROW. VAL-009 is already discharged; no FTS assertion
  and no search-vector mechanism is part of this task.
goals:
  - "a never-consented user cannot create an ad on the bot or on the web, and gets a clear consent-required message"
  - "the bot refuses at /post AND re-refuses at submit_ad, so a mid-FSM update cannot slip through"
  - "correct the one false sentence in technical-specification.md section F"
  - "re-declare the six ads.Ad text inventory entries as DELETE_ROW with reasons citing 06-PII-109"
extra_context: |
  DETERMINATION (do not reopen): the 30-day consent_hard_delete sweep IS the Q-D2
  warning. Choose option (b); do NOT scrub ad text. Evidence, all verified:
  - consent_hard_delete runs hourly (apps/core/utils/scheduler.py registers it,
    advisory lock AdvisoryLockId.CONSENT_HARD_DELETE) over
    User.objects.filter(consent_revoked_at__lt=now-30d) and ends with
    queryset.delete(). Ad.user is on_delete=models.CASCADE
    (apps/ads/models.py). At day 30 the Ad rows, their text and their AdImage rows
    are physically destroyed; the pre_delete signal schedules the media removal via
    transaction.on_commit. Covered by apps/core/tests/test_sweep_consent.py.
  - privacy.html section 6 already publishes option (b)'s policy and is already
    translated in ru and bs ("The remaining account record and the advertisements
    and images still linked to it are permanently removed by the 30-day erasure
    sweep", plus a "Retained, and why" bullet about moderation records). Option (a)
    would make a published, translated policy false.
  - Option (a) accelerates a scheduled destruction by 30 days and leaves a
    half-anonymised row (text gone, AdImage rows, ModeratorActionLog rows and
    DailyAdMetrics still attached) - worse for an auditor than either honest end
    state - and destroys dispute-resolution evidence privacy.html promises.
  - Option (c) (hard-delete at withdrawal) is rejected outright: AdImage, AdFeature,
    AdFavorite, DailyAdMetrics and SavedSearchNotification all CASCADE off Ad, so it
    destroys buyers' favourites, the seller's own statistics and other users' alert
    records to erase first-party data, to reach an endpoint that already exists.
    There is NO AdModeratorPriority model in this repository; do not cite one.
  - VAL-009 is ALREADY DISCHARGED. test_search_triggers.py::
    TestSearchVectorTrigger::test_title_update_refreshes_all_search_vectors is green
    today and is the assertion the plan misfiled into test_setup_search_triggers.py.
    The trigger is BEFORE INSERT OR UPDATE ... FOR EACH ROW and folds all six text
    columns into all four vectors on every write (there is no title_ru; the Russian
    base IS title), so a stale vector is structurally impossible. The only uncovered
    form is a bulk QuerySet.update(), which this block does not write. State the
    obligation discharged; add NO FTS assertion.

  SPEC CLAUSE - replace this single bullet in docs/01-spec/technical-specification.md
  section F, verbatim as it stands today:
    "Anonymized ads (post-withdrawal, pre-hard-delete) persist for 30 days only - NOT
     the 120-day purge_deleted_ads window"
  with exactly:
    "Ads are soft-deleted (status=DELETED) on withdrawal and are hidden immediately from
     listings, search and direct URLs; they are NOT anonymised. The user-authored text and
     images are retained for the 30-day grace period so moderation records stay reviewable
     for dispute resolution, then hard-deleted by the consent_hard_delete sweep via Ad.user
     on_delete=CASCADE - NOT the 120-day purge_deleted_ads window, which never sees them."
  Preserve the file's backticked identifiers and em-dash rhythm. That file is reserved
  to phase 06 and BLOCKS 4/9/14 have edited it: take ONLY this bullet.
  NO privacy.html edit. NO i18n work for it. NO db-schema.md edit (BLOCK 13's file; its
  stale "Legacy search_vector retained during dual-write transition" note is recorded in
  the plan and left for that block). NO doc-maintenance-rules.md edit - the deviation is
  recorded as a NAMED TEST instead.

  PREDICATE - can_publish_ad is dead code (zero production call sites; only the
  re-export in apps/users/services/__init__.py and test_account_state.py::
  TestCanPublishAd reference it). DISPOSITION: USE IT, DO NOT DELETE IT. It reads
  is_banned / is_deleted / ads_auto_publish and NOT consent_given_at;
  can_store_personal_data reads the storage terms plus a granted consent_given_at and
  deliberately OMITS ads_auto_publish. Neither is the rule; their conjunction is. Add
  one additive module-level predicate to account_state.py that composes them, and use
  it at every gate point. Do NOT fold the consent term INTO can_publish_ad - that
  would break TestCanPublishAd::test_declined_user_can_publish, which asserts
  can_publish_ad(declined) is True. Do NOT mutate can_store_personal_data. Do NOT
  mutate account_state_q (contract-frozen by BLOCKS 6/7; BLOCK 7's test mutates it).
  Do NOT add is_active to any of them: Django's ModelBackend already revokes the web
  session for an inactive user and _evaluate_user_state refuses one on the bot, and
  re-adding it would silently re-close the plan-19 support carve-out.

  PREDECENT TO COPY - telegram_bot/handlers/support.py: a module-level gettext_lazy
  constant (SUPPORT_CONSENT_REQUIRED_MESSAGE) gating TWICE - refuse at the entry
  point, re-refuse at persistence, the latter returning None as the single refusal
  signal, FSM reset on refusal. That two-point shape is what the ad path needs,
  because today only the entry point is guarded and the FSM steps after it are not.

  RULE 2 - no existing test needs re-pinning, and that is a design requirement, not a
  convenience: keeping can_publish_ad's own semantics unchanged is what keeps
  TestCanPublishAd green. If you find yourself rewriting that module's assertions,
  you have mutated a predicate you were told to compose - stop and reconsider.

  BLAST RADIUS - the single biggest risk in this block. seller / user / buyer in
  src/backend/conftest.py and user / seller in src/telegram_bot/tests/conftest.py all
  leave consent_given_at NULL today. Every existing test that posts to ad_edit or
  calls submit_ad will start failing on a consent refusal unless the fixtures grant
  consent. They use get_or_create(telegram_id=..., defaults={...}), so a row left
  over from a previous --reuse-db run never receives a new default: set the value
  explicitly after get_or_create when it is NULL. --create-db is in the command list
  for exactly this reason.

  KNOWN-BASELINE CAVEAT: BLOCK 12's implementor reported
  test_ad_factory_contract.py::test_no_factory_call_relies_on_a_silent_default red on
  committed code (test_account_state.py, two create_test_ad calls). Re-establish the
  baseline before attributing any failure to this block, and do not "fix" it by
  weakening production code.
files:
  - path: "src/backend/apps/users/services/account_state.py"
    targets:
      - type: function
        name: "can_publish_ad"
      - type: function
        name: "can_store_personal_data"
    semantic_anchors:
      insert_after:
        type: function
        value: "can_store_personal_data"
      note: >
        The new composed predicate goes after can_store_personal_data, next to the
        other exported predicates. can_publish_ad itself is NOT an edit target.
  - path: "src/backend/apps/users/services/__init__.py"
    targets:
      - type: module
        name: "__all__"
    semantic_anchors:
      insert_after:
        type: import_name
        value: "can_publish_ad"
  - path: "src/backend/apps/ads/services/submission.py"
    targets:
      - type: enum
        name: "SubmitAdOutcome"
      - type: function
        name: "submit_ad"
    semantic_anchors:
      insert_before:
        type: comment
        value: "Capture each photo's staged key and read path BEFORE the plan rewrites the"
      note: >
        The refusal returns SubmitAdResult(NEW_MEMBER, [message]) before the staged
        media plan, the thumbnail generation and the transaction.atomic() block.
  - path: "src/telegram_bot/middlewares/permissions.py"
    targets:
      - type: method
        name: "AccountStateMiddleware._evaluate_publish_permission"
    semantic_anchors:
      insert_after:
        type: return_statement
        value: '"Your account has publishing restrictions. Contact support for assistance."'
      note: >
        The ads_auto_publish branch stays FIRST (its wording is asserted). The consent
        term goes after it and delegates the boolean to the shared predicate.
  - path: "src/telegram_bot/handlers/ad_create/submit.py"
    targets:
      - type: function
        name: "process_preview"
    semantic_anchors:
      insert_before:
        type: name
        value: "SubmitAdOutcome.MODERATION_FAILED"
  - path: "src/backend/apps/ads/views/edit.py"
    targets:
      - type: function
        name: "ad_edit"
      - type: function
        name: "ad_archive"
      - type: function
        name: "ad_reactivate"
    semantic_anchors:
      insert_after:
        type: decorator
        value: "login_required"
      note: >
        One shared helper in this module, called by all three views right after the
        ad is fetched. Preserve each view's existing ownership-403 wording and its
        lock-timeout re-render path.
  - path: "src/backend/apps/ads/views/dashboard.py"
    targets:
      - type: function
        name: "dashboard"
  - path: "src/backend/apps/users/services/pii_inventory.py"
    targets:
      - type: module
        name: "PII_ERASURE_ENTRIES"
    note: >
      CONTENDED with BLOCK 13. Touch ONLY the six ads.Ad entries
      (title, title_en, title_bs, description, description_en, description_bs).
      Do not touch the four core.SupportTicket entries or anything after them.
  - path: "src/backend/conftest.py"
    targets:
      - type: function
        name: "seller"
      - type: function
        name: "user"
      - type: function
        name: "buyer"
      - type: function
        name: "make_user"
  - path: "src/telegram_bot/tests/conftest.py"
    targets:
      - type: function
        name: "user"
      - type: function
        name: "seller"
  - path: "src/backend/apps/ads/tests/test_ad_consent_gate.py"
    targets:
      - type: module
        name: "test_ad_consent_gate"
    note: "NEW module."
  - path: "src/backend/apps/users/tests/test_pii_inventory.py"
    targets:
      - type: function
        name: "test_support_ticket_entries_are_delete_row"
    semantic_anchors:
      insert_after:
        type: function
        value: "test_support_ticket_entries_are_delete_row"
    note: "One new guard test mirroring the SupportTicket precedent. Nothing else in this module changes."
  - path: "docs/01-spec/technical-specification.md"
    targets:
      - type: text
        name: "section F, the 'Anonymized ads' bullet"
    note: "One bullet. Re-read before editing - BLOCKS 4/9/14 have edited this file."
changes:
  - action: add_code
    description: >
      Add ONE composed predicate to account_state.py and re-export it from the
      users services package. It closes can_publish_ad's dead-code defect and gives
      both tiers a single authority for "may this account create an ad".
    code_hint: |
      def can_create_ad(user: User) -> bool:
          """Whether the account may create or rewrite an ad (06-PII-109).

          A conjunction of the two rules that already exist, each answering a
          different question: ``can_publish_ad`` (the operator's publishing
          restriction: banned / deleted / ``ads_auto_publish=False``) and
          ``can_store_personal_data`` (the blocking flags plus a granted
          ``consent_given_at``). Neither alone is the rule - a never-consented user
          passes ``can_publish_ad``, and a publishing-restricted user passes
          ``can_store_personal_data``.

          ``is_active`` is deliberately absent, as in both operands: ``@login_required``
          already refuses an inactive user on the web and ``_evaluate_user_state``
          refuses one on the bot. ``account_state_q`` is untouched and contract-frozen.
          """
          return can_publish_ad(user) and can_store_personal_data(user)
  - action: add_code
    description: >
      Add the new SubmitAdOutcome member and refuse at the top of submit_ad, before
      any filesystem work and before the transaction. The refusal signal is the
      result, matching how the service already reports every other refusal.
    code_hint: |
      # In SubmitAdOutcome:
      CONSENT_REQUIRED = "consent_required"

      # First statement in submit_ad, before plan_staging_permanence promotion:
      if input.user_id is not None and not can_create_ad(User.objects.filter(pk=input.user_id).first() ...):
          return SubmitAdResult(
              SubmitAdOutcome.CONSENT_REQUIRED,
              [str(_("To create an advertisement, please accept the personal data storage consent first."))],
          )
      # Resolve the seller by pk; a missing user is DRAFT_GONE's business, not this gate's.
  - action: add_code
    description: >
      Bot entry refusal: keep the ads_auto_publish branch first (its wording is
      asserted by an existing test), then delegate the boolean to the shared predicate
      and answer the new module-level gettext_lazy constant.
    code_hint: |
      # New module-level constant in permissions.py, next to the existing strings:
      AD_CONSENT_REQUIRED_MESSAGE: Final = gettext_lazy(
          "To create an advertisement, please sign in and accept the personal data "
          "storage consent first."
      )

      # In _evaluate_publish_permission, after the ads_auto_publish branch:
      if not can_create_ad(user):
          return (False, AD_CONSENT_REQUIRED_MESSAGE)
  - action: add_code
    description: >
      Render the new outcome in process_preview: answer the outcome's own message and
      clear the FSM. The dialog cannot continue - this is not a recoverable content
      failure, it is "this account may not create ads".
    code_hint: |
      elif result.outcome is SubmitAdOutcome.CONSENT_REQUIRED:
          await message.answer(str(result.errors[0]) if result.errors else _("..."))
          await state.clear()
  - action: add_code
    description: >
      Web refusal on all four seller surfaces: one shared helper in edit.py, called by
      ad_edit / ad_archive / ad_reactivate and by dashboard. HttpResponseForbidden with
      a distinct message, the shape these views already use for the ownership refusal.
    code_hint: |
      # One module-level message in each views module, gettext_lazy:
      #   "You cannot manage advertisements until you accept the personal data
      #    storage consent."
      if not can_create_ad(request.user):
          logger.info("Refused ad write for user %s: no storage consent", request.user.id)
          return HttpResponseForbidden(_("You cannot manage advertisements until you accept the personal data storage consent."))
  - action: modify_code
    description: >
      Re-declare the six ads.Ad text entries from ErasureAction.CLEAR to
      ErasureAction.DELETE_ROW. Under option (b) the row genuinely IS deleted, by the
      sweep at its named bound, so DELETE_ROW is the honest declaration rather than a
      declaration-only CLEAR. Each rewritten reason MUST keep the literal substring
      "BLOCK" (test_retained_free_text_entries_name_their_owning_block asserts it),
      MUST cite 06-PII-109 (the new guard test asserts it), and MUST drop the Q-D3 /
      DECLARATION-ONLY deferral language.
    code_hint: |
      (
          "ads.Ad",
          "title",
          ErasureAction.DELETE_ROW,
          "Implemented today (BLOCK 11, 06-PII-109): the whole Ad row is DELETE_ROW. "
          "withdraw_consent soft-deletes the ad (status=DELETED, hidden from listings, "
          "search and ad_detail) and consent_hard_delete hard-deletes the User 30 days "
          "after consent_revoked_at; Ad.user is on_delete=CASCADE, so the row, its text "
          "and its photos are physically destroyed at that bound. The text is NOT "
          "anonymised during the window - privacy.html section 6 publishes that "
          "retention, so the specification was corrected rather than the data.",
      ),
  - action: modify_code
    description: >
      Grant storage consent in the generic fixtures, explicitly after get_or_create so
      a stale --reuse-db row is repaired too.
    code_hint: |
      if user.consent_given_at is None:
          user.consent_given_at = timezone.now()
          user.save(update_fields=["consent_given_at"])
  - action: modify_code
    description: >
      Replace the single "Anonymized ads (post-withdrawal, pre-hard-delete) persist for
      30 days only - NOT the 120-day purge_deleted_ads window" bullet in
      technical-specification.md section F with the wording given verbatim in
      extra_context. One bullet; nothing else in the file.
  - action: add_code
    description: >
      Add the two new msgids to all three .po catalogs. ru and bs msgstr must be
      non-empty (test_no_empty_msgstr); en may stay empty.
acceptance_criteria:
  - "technical-specification.md section F no longer contains the word 'Anonymized' for ads, and carries the specified replacement wording; no other bullet in that file changed"
  - "privacy.html, db-schema.md and doc-maintenance-rules.md are byte-identical"
  - "can_publish_ad now has at least one production call site, and its own signature and semantics are unchanged"
  - "can_publish_ad, can_store_personal_data, can_login, get_account_state and account_state_q are unchanged except for the new additive predicate"
  - "a user with consent_given_at IS NULL is refused on ad_edit, ad_archive, ad_reactivate and dashboard, with the consent message - and the refusal is provably the gate, not @login_required (ownership alone is not sufficient)"
  - "the bot refuses a never-consented user at /post AND submit_ad returns the consent outcome before any write, so an update that enters mid-FSM cannot publish"
  - "a user WITH consent creates an ad unchanged on both tiers"
  - "a DECLINED user is refused for publishing and a non-declined user is not, with no special-casing; give_consent still restores posting with no code change"
  - "the six ads.Ad inventory entries are ErasureAction.DELETE_ROW, each reason contains 'BLOCK' and cites '06-PII-109', and no reason retains Q-D3 or DECLARATION-ONLY"
  - "the four core.SupportTicket entries and every other inventory entry are unchanged"
  - "the remainder of test_pii_inventory.py passes unchanged"
  - "test_deletion.py passes unchanged and was not edited - it contains zero content assertions"
  - "no new search_vector assertion was added to test_search_triggers.py or test_setup_search_triggers.py, and no trigger, re-derivation mechanism or migration was touched"
  - "deletion.py, Ad.transition_to, ALLOWED_TRANSITIONS and AdAdmin are unchanged"
  - "the new msgids have non-empty ru and bs msgstr"
  - "the generic fixtures grant consent AND the repair-after-get_or_create path is proven by running with --reuse-db stale rows present"
tests_required:
  - "a never-consented user is refused on the bot at /post and again at submit_ad, and receives the consent message; the refusal at submit_ad is shown to precede any write"
  - "a user with consent creates an ad unchanged on both tiers"
  - "the web refuses a never-consented user on ad_edit, ad_archive, ad_reactivate and dashboard - and ownership alone is not sufficient, proved by asserting the refusal for an account that DOES own the ad, i.e. the gate is consulted rather than the ownership check firing"
  - "a declined user is refused for publishing and a non-declined user is not; state in the commit body that no existing assertion needed re-pinning and why"
  - "deviation record (option b): after withdraw_consent the ad is status=DELETED, is absent from ListingsQuery.build_queryset, 404s from ad_detail, and RETAINS its title and description byte-for-byte"
  - "test_deletion.py passes unchanged"
  - "the six inventory entries are DELETE_ROW with reasons citing 06-PII-109, mirroring test_support_ticket_entries_are_delete_row"
  - "logic and interaction only: no line-number, column-count, template-substring or symbol-presence assertions"
tests_to_run:
  - "src/backend/apps/ads/tests"
  - "src/backend/apps/ads/tests/test_admin_change_form.py"
  - "src/backend/apps/users/tests/test_pii_inventory.py"
  - "src/backend/apps/users/tests/test_deletion.py"
  - "src/backend/apps/users/tests/test_account_state.py"
  - "src/backend/apps/core/tests/test_sweep_consent.py"
  - "src/telegram_bot/tests/test_account_state_middleware.py"
  - "src/telegram_bot/tests/test_ad_create.py"
  - "src/telegram_bot/tests/test_ad_create_submit_outcome.py"
  - "src/telegram_bot/tests/test_support.py"
commands:
  - '$dc = ''docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'''
  - '$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/ads/tests src/backend/apps/users/tests/test_deletion.py src/backend/apps/users/tests/test_pii_inventory.py src/telegram_bot/tests/test_account_state_middleware.py src/telegram_bot/tests/test_ad_create.py src/telegram_bot/tests/test_ad_create_submit_outcome.py --tb=short" test'
  - '$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="--create-db --tb=short -n auto --maxprocesses=4 --dist loadgroup" test'
  - '$dc run --rm --env PYTEST_SKIP_MARKERS=seed test'
  - 'uv run ruff check src/backend/apps/ads/ src/backend/apps/users/ src/telegram_bot/'
  - 'uv run basedpyright src/backend/apps/ads/services/submission.py src/backend/apps/users/services/account_state.py'
  - 'uv run djlint src/backend/templates/'
  - '# i18n is part of DoD: the two new msgids need non-empty ru/bs msgstr.'
  - '$dev = ''docker compose --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.override.yml --project-name mko-bazuna-dev'''
  - '$dev run --rm --no-deps --entrypoint "" web python src/backend/manage.py makemessages -l ru -l bs -l en --no-location'
  - '$dev run --rm --no-deps --entrypoint "" web python src/backend/manage.py compilemessages --ignore=.venv --ignore=.git --ignore=__pycache__ --ignore=*.pyc --ignore=node_modules --locale ru --locale bs --locale en'
commit:
  message: "fix(ads): gate ad creation on storage consent and correct the retention wording (06-PII-109)"
  stage_only:
    - "src/backend/apps/users/services/account_state.py"
    - "src/backend/apps/users/services/__init__.py"
    - "src/backend/apps/ads/services/submission.py"
    - "src/backend/apps/ads/views/edit.py"
    - "src/backend/apps/ads/views/dashboard.py"
    - "src/backend/apps/ads/tests/test_ad_consent_gate.py"
    - "src/backend/apps/users/services/pii_inventory.py"
    - "src/backend/apps/users/tests/test_pii_inventory.py"
    - "src/backend/conftest.py"
    - "src/telegram_bot/middlewares/permissions.py"
    - "src/telegram_bot/handlers/ad_create/submit.py"
    - "src/telegram_bot/tests/conftest.py"
    - "src/telegram_bot/tests/test_ad_create_submit_outcome.py"
    - "src/backend/locale/ru/LC_MESSAGES/django.po"
    - "src/backend/locale/bs/LC_MESSAGES/django.po"
    - "src/backend/locale/en/LC_MESSAGES/django.po"
    - "docs/01-spec/technical-specification.md"
  note: >
    Stage by path, never `git add -A`: .ai/** is being edited concurrently by other
    agents, and apps/media/*, apps/ads/admin.py and users/services/deactivation.py
    may carry other actors' in-flight work.
```

**Tests required**

Per plan §1.5, these assert **logic and interaction** only — no line-number,
column-count, template-substring or symbol-presence assertions. The new module is
`src/backend/apps/ads/tests/test_ad_consent_gate.py`.

1. **The gate, both tiers.** A user with `consent_given_at IS NULL` cannot create an ad
   on the bot **or** the web and receives the clear consent-required message; a user
   **with** consent can, unchanged.
2. **The two-point bot refusal — the anti-regression that matters most.** The bot refuses
   at `/post` **and** re-refuses at `submit_ad`, so an update that enters mid-FSM cannot
   publish. Today only the entry point is guarded, which is why this is the assertion
   that earns its keep: drive a `process_preview` confirm for a draft whose owner has no
   consent and assert nothing was written and the ad is still a `DRAFT`.
3. **The web gate is consulted, not merely `@login_required`.** `ad_edit`, `ad_archive`,
   `ad_reactivate` and `dashboard` all refuse a never-consented user. Crucially the
   negative control is *ownership satisfied*: the refusing account **owns** the ad, so
   the ownership check cannot be what fired. A separate case proves a non-owner is
   still refused by the ownership path, so the two refusals are distinguishable.
4. **The declined rule.** A declined user is refused for publishing while a non-declined
   user is not. No special-casing: `give_consent` already clears `is_declined` and
   restores `ads_auto_publish`, so re-consent restores posting with no code change.
5. **The deviation record (option (b)).** Named as documenting the deviation: after
   `withdraw_consent`, the ad is `status=DELETED`, is absent from
   `ListingsQuery.build_queryset`, 404s from `ad_detail`, and **retains** its `title` and
   `description` byte-for-byte. `test_deletion.py` still passes unchanged alongside it.
6. **The inventory guard.** The six `ads.Ad` entries are `DELETE_ROW`, each reason cites
   `06-PII-109` and keeps `"BLOCK"` — one new test mirroring the green
   `test_support_ticket_entries_are_delete_row`.
7. **Other users are unaffected.** A second seller's ads and session are untouched by
   both a refusal and a withdrawal.
8. **Regression.** The existing suites pass unchanged: the deletion tests (status
   assertions, `updated_at` refresh, DRAFT `storage_keys` return, skip-if-already-
   `DELETED`), `TestCanPublishAd`, `TestCanLogin`, `TestCrossPredicateAgreement`, the
   `ads_auto_publish` publish-gate test, and the `sweep_consent` suite.
9. **Rule 2 — declare the outcome.** State in the commit body that **no existing
   assertion needed re-pinning**, and why: composing the predicates leaves
   `can_publish_ad`'s own semantics intact, so
   `TestCanPublishAd::test_declined_user_can_publish` (`can_publish_ad(declined) is True`)
   still describes the predicate it names. Had the consent term been folded *into*
   `can_publish_ad`, that test would have had to be re-pinned — which is the concrete
   reason the composition is specified.

**Risk and rollback**

- *No destruction.* Option (b) destroys nothing, so the old block's irreversible-scrub
  rollback problem is **gone**. A straight revert restores the previous behaviour with no
  data repair and no migration to undo. This is the single largest reduction in risk
  between the two options.
- *Risk (blast radius — the real one):* the gate touches a service every ad test calls and
  four seller views, and the generic fixtures currently grant no consent. Mitigation:
  binding constraint 1, the explicit repair after `get_or_create`, and `--create-db` in
  the command list. **Show the new gate red against the pre-fix code before it goes
  green** (Validator requirement).
- *Risk (predicate drift):* a bare boolean cannot render a message, so the bot keeps its
  own ordered branches while `can_publish_ad` + `can_store_personal_data` remain the
  boolean authority. Mitigation: the `ads_auto_publish` branch stays first, and the new
  branch delegates to the shared predicate rather than re-reading flags. One flag
  (`is_active`) is deliberately absent everywhere — documented above so nobody "fixes" it.
- *Risk (staff visibility):* unchanged and accepted. `AdAdmin` still lists and
  full-text-searches `title`/`description` for the 30-day window. That is what
  `privacy.html` §6 publishes and what dispute resolution needs; this block records the
  decision rather than closing the surface. If a future block wants to narrow it, that is
  a separate decision with its own spec edit.
- *Known baseline:* BLOCK 12's implementor reported
  `test_ad_factory_contract.py::test_no_factory_call_relies_on_a_silent_default` red on
  committed code. Re-establish the baseline before attributing any failure here.
- *Cross-phase:* phase 08 owns the vector mechanism (untouched — `VAL-009` discharged);
  phase 05 owns the DELETED transition (untouched); BLOCK 10 owns `deletion.py`
  (this block only reads it); BLOCK 13 owns the other half of `pii_inventory.py` and
  `db-schema.md`'s stale `search_vector` note.

---

### BLOCK 12 — Support-ticket admin containment and the declared identity-column guard (06-PII-106, VAL-007)

| | |
|---|---|
| **Findings owned** | `06-PII-106`, `VAL-007` |
| **Depends on** | **BLOCK 4** — a *shape* edge only (§4.2), and it is satisfied **by delegation**: both display methods call `mask_telegram_id`, so this block is correct on either construction and BLOCK 4's landing is a **no-op here**. **The Implementor must not wait for BLOCK 4 and must not hard-code any part of the mask's output shape.** |
| **Blocks** | nothing; BLOCK 13 re-reads the helper shape |
| **Priority** | P1 — it is a **live staff-visible exposure** today |
| **Risk level** | **LOW-MEDIUM** — display and search configuration only, but **three shipped tests pin the current configuration** and one of them must be rewritten |
| **Required agents** | **Auditor · Planner · Validator**. **Q-D12 is RESOLVED (§0.6.1, Option D) — no Researcher gate remains on this block.** **Validator is required**: the new guard must be shown **red against the pre-fix code** before it goes green, and `SupportContactAdmin` must be shown untouched |

**The defect.** `SupportTicketAdmin.list_display` includes raw `chat_id` and `telegram_id`;
`search_fields` includes `text`, making the entire unbounded ticket body a full-text search
target for any `is_staff` account. The model's own `readonly_fields` **already** marks
these columns read-only on the *change* form — the changelist and the search index were
simply never brought under the containment rule `LoginTokenAdmin` already follows. One
changelist screenshot, CSV export or support bundle is a bulk PII disclosure of the
requester's numeric Telegram ID, in the one admin surface the product designed to prevent
exactly that.

**Two test files change, and the report's rollout row conflated them (C-11).**

`src/backend/apps/core/tests/test_support_admin.py` is the file that **pins the leaky
configuration**, so it is where the **assertion change** belongs. Three of its tests assert
exact lists and all three are green today:

| Test | Today | After this block |
|---|---|---|
| `test_support_ticket_admin_list_display` | the exact six-name list, **including raw `chat_id` and `telegram_id`** | the same six positions, with the two masked display-method names |
| `test_support_ticket_admin_search_fields` | the exact four-name list, **including `text`** | `["ticket_ref", "telegram_id", "username"]` |
| `test_support_ticket_admin_readonly_fields` | the exact seven-name list | **unchanged** — `readonly_fields` is not in scope. Re-pinned deliberately, so a future edit to it is caught. The commit body says which two changed and why this one did not |

`src/backend/apps/users/tests/test_admin_pii_containment.py` is the **right file for the new
guard** and the **wrong file for the assertion change**. It is a second, separate edit. Every
`SupportContactAdmin` test in the first file, plus `test_support_ticket_admin_list_filter`,
`..._add_permission_false` and `..._delete_permission_false`, stay **unchanged**.

**Q-D12 — RESOLVED 2026-10-01: Option D, extend the helper-enumeration precedent.**

`VAL-007`, confirmed against the tree and then **dissolved** by the resolution. The trap is
real: `SupportContactAdmin` declares `list_display` containing `telegram_id` and
`search_fields` containing `telegram_id`, with **no `readonly_fields` and no permission
override**, because its `telegram_id` is a *configured support-channel* identifier, not a
data subject's, and channels are meant to be staff-editable. **Every registry walk inherits
that false positive**, which is why A, B and C were all rejected. **Option D has no walk**,
so there is nothing to false-positive.

**The decision, in the module's own idiom.** `test_admin_pii_containment.py` is *already* the
right shape and is *already* in the right file: it asserts
`"str(obj.user.telegram_id)" not in source` rather than banning the token `telegram_id`,
*because docstrings legitimately name `telegram_id` in prose*. This block adds **exactly two
entries** to it — `SupportTicketAdmin.chat_id_display` and `SupportTicketAdmin.telegram_id_display`
— each asserting on the **rendering statement** (delegates to `mask_telegram_id`, references
`obj.<column>`), exactly like the existing `test_login_token_list_display_masks_telegram_id`.
There is **no registry walk, no declared column set, no exempt list and no new test module**.

| Option | Verdict |
|---|---|
| **A** — declared set of data-subject identity columns + registry walk | Rejected. It carries the same forgot-to-add-it residual the guard exists to remove, and inherits the `SupportContactAdmin` false positive. |
| **B** — declared **exempt** admins + blanket deny | Rejected. Deny-by-default friction on every future admin, to fix a false positive Option D never creates. |
| **C** — assert on `SupportTicketAdmin` only | Rejected. D minus the four existing helper tests: a coverage regression. |
| **D** — extend helper enumeration | **Chosen.** No walk, no declaration, no false positive, no new mechanism, in a module that is already green and already owns this rule. |

**Two rationales that must survive into the commit body and the module docstring.**

1. *Why the assertion is on the rendering statement and not on a banned token:* the module
   asserts on what the helper **does**, not on the word `telegram_id`, because docstrings
   legitimately name the field. A banned token would either false-positive on prose or force
   the docstrings to be reworded.
2. *Why cross-model rendering needs no declaration:* `AdAdmin.user_link`,
   `AnalyticsEventAdmin.user_link` and `moderation.admin.log_user_link` all render
   `str(obj.user)` — **another model's** column. No per-model column set can ever reach
   them, so cross-model containment is owned by helper enumeration **by construction**.

**The residual, and where it is written down.** Helper enumeration cannot catch a future
admin that renders a raw identity column **without** a helper. It enumerates masking helpers;
it does not classify models. That limitation belongs in the module docstring — which already
documents the analogous limit for PII-001 — and is a **required edit** in this block.

**File surface (semantic units — the operation on each)**

| File | Symbol / target | Operation | Notes |
|---|---|---|---|
| `src/backend/apps/core/admin.py` | module import block | **REQUIRED** — add `mask_telegram_id` from `apps.core.utils.sanitize` | One import beside the existing `apps.core.models` import. No new production module. |
| `src/backend/apps/core/admin.py` | `SupportTicketAdmin` — new methods `chat_id_display`, `telegram_id_display` | **REQUIRED** — insert after `has_delete_permission` | Both **delegate** to `mask_telegram_id`. Neither carries a width, a length, a prefix or a hash shape. `None`-tolerance is inherited from the callee, not re-implemented. |
| `src/backend/apps/core/admin.py` | `SupportTicketAdmin.list_display` | **REQUIRED** — replace the raw `"chat_id"` and `"telegram_id"` entries with the two display-method names | Reuse the `LoginTokenAdmin.telegram_id_display` precedent: an `@admin.display` method named in `list_display` — **not** a `readonly_fields` entry, **not** a formatting filter. Keep the surrounding order unchanged. |
| `src/backend/apps/core/admin.py` | `SupportTicketAdmin.search_fields` | **REQUIRED** — drop `"text"`, leaving `["ticket_ref", "telegram_id", "username"]` | `telegram_id` **stays** (§0.6.3 #11). |
| `src/backend/apps/core/tests/test_support_admin.py` | `test_support_ticket_admin_list_display`, `test_support_ticket_admin_search_fields` | **REQUIRED — rewrite the assertion** (C-11) | Say which changed and why in the commit body (project rule 2: production code is king, the test moves). |
| `src/backend/apps/core/tests/test_support_admin.py` | `test_support_ticket_admin_readonly_fields` | **REQUIRED — re-pinned unchanged** | `readonly_fields` is **not** in scope for this block. Re-run it green and say in the commit body that it was deliberately not changed. |
| `src/backend/apps/core/tests/test_support_admin.py` | new test beside the existing `SupportTicketAdmin` tests | **REQUIRED** — the changelist **renders** the mask for a real row | Behaviour, not trivia (§1.5). No mask length, no column count, no symbol presence. |
| `src/backend/apps/users/tests/test_admin_pii_containment.py` | two new tests, inserted after `test_login_token_list_display_masks_telegram_id` | **REQUIRED** — the guard | Assert on the **rendering statement**. **Phase 04 owns the other half of this file** (the six `04-AUT-005` form-contract tests): add, never disturb, and re-read immediately before editing. |
| `src/backend/apps/users/tests/test_admin_pii_containment.py` | module docstring | **REQUIRED** — extend the stated limitation with the new residual | Append a paragraph; do not rewrite the existing one. |
| `src/backend/apps/core/utils/sanitize.py` | `mask_telegram_id` | **read-only** | Called, never re-implemented. Its construction is BLOCK 4's to change; this block must not depend on what it emits. |
| `src/backend/apps/core/tests/test_sanitize.py` | `mask_telegram_id` tests | **read-only** | Do not edit to accommodate this block. BLOCK 4 owns that file. |

**Binding constraints**

1. **Delegate; never hard-code the mask shape.** Both display methods **call**
   `mask_telegram_id`. No width, no length, no prefix, no hash shape anywhere in this
   block's diff — **production or tests**. BLOCK 4 changes that construction (keyed HMAC,
   `tg_` prefix preserved, width changing) and its decision (Q-D8) is still the owner's;
   delegation is exactly what makes this block correct on either construction, and a pinned
   mask would turn BLOCK 4's landing into a breaking change here.
2. **`None`-tolerant by construction.** `mask_telegram_id(None)` already returns a
   non-empty string, so the helpers **inherit** `None`-tolerance by delegating. Do **not**
   add a local `if obj.chat_id is None` branch and do not add a second construction. BLOCK 13
   makes both columns nullable and must not have to rewrite these methods (§4.2: the 12 → 13
   edge is a *shape* dependency, not a logic one).
3. **`SupportContactAdmin` is not a violation and must be left byte-identical.** Its
   `telegram_id` is a configured support-channel id, and channels are meant to be
   staff-editable. **Do not** add a `readonly_fields` entry, a permission override, a masking
   helper, a docstring change or any other edit to that class, and do not edit any
   `SupportContactAdmin` test.
4. **`telegram_id` stays in `search_fields`.** `text` goes; `ticket_ref`, `telegram_id` and
   `username` stay, for genuine support lookups (§0.6.3 #11). BLOCK 13 makes the columns
   nullable first, and `UserAdmin` and `LoginTokenAdmin` both keep the raw `telegram_id` in
   their own search — removing it here alone would create a **new** inconsistency. **Whether
   searching by a raw `telegram_id` is itself an exposure is routed to the coordinator**, not
   decided in this block.
5. **`ConsentRecord.session_key` is BLOCK 15's.** It appears in **both**
   `ConsentRecordAdmin.list_display` and `.search_fields` in `apps/users/admin.py`. Do not
   touch either, and do not add it to the guard.
6. **The guard asserts on the rendering statement, never on a banned token.** Assert that
   the helper's source contains `mask_telegram_id` and references `obj.<column>`. Do **not**
   assert `"telegram_id" not in source` — the module's own docstrings legitimately name the
   field. Follow the module's existing `_assert_no_raw_telegram_id` idiom.
7. **Two new entries only.** Exactly `chat_id_display` and `telegram_id_display`, both in
   `test_admin_pii_containment.py`. **No registry walk, no declared column set, no exempt
   list, no new test module, no new production module.** A future "simplification" into a
   blanket ban is the exact failure mode `VAL-007` names; the trap goes in the module
   docstring and in the commit body.
8. **The new guard must be demonstrated red against the pre-fix code** before it goes green,
   and the failure output goes in the commit body.
9. **`conftest.py` is off-limits** (§5.3). The changelist-rendering test needs a persisted
   staff actor: build it locally in the test module, the way
   `test_admin_pii_containment.py::_admin_request` / `staff_user` already do.
10. **No migration, no schema change, no template, no `.po` file.** `SupportTicket` stays in
    `apps/core/models.py` (`apps/support/` does not exist). Rollback is a straight revert.

**Out of scope for this block (named so they are not re-litigated)**

| Out of scope | Owner |
|---|---|
| `SupportContactAdmin` in its entirety — `list_display`, `search_fields`, `readonly_fields`, permissions | nobody; it is correct as written |
| `telegram_id` in `SupportTicketAdmin.search_fields` (whether raw-ID search is itself an exposure) | **coordinator** (§0.6.3 #11) |
| `ConsentRecordAdmin.list_display` and `.search_fields`, and `ConsentRecord.session_key` | **BLOCK 15** |
| `SupportTicket.chat_id` / `telegram_id` becoming nullable, and the replacement support-lookup key (Q-D2) | **BLOCK 13** |
| The `mask_telegram_id` construction, its key and its width | **BLOCK 4** (Q-D8, owner-ratified) |
| A retention boundary for `SupportTicket.text` | not decided in phase 06; the `RETAIN` reason in BLOCK 3's inventory names this block |
| Any registry walk / declared identity-column set / exempt-admin list | declined; Q-D12 Option D |

**Implementor task**

```yaml
id: task_06_b12_support_admin
title: "Mask support-ticket identifiers in the admin changelist and guard the helper (06-PII-106)"
priority: medium
depends_on: [task_06_b04_keyed_mask]
source_reference: ".ai/plans/06-pii-consent-remediation.md"
source_section: "BLOCK 12 - Support-ticket admin containment"
source_blocks: ["BLOCK 12"]
description: >
  SupportTicketAdmin.list_display renders the requester's raw Telegram chat_id and
  telegram_id in cleartext to every is_staff account, and search_fields full-text-searches
  the unbounded ticket body. Replace the two raw columns with masked @admin.display methods
  that delegate to mask_telegram_id (the LoginTokenAdmin.telegram_id_display precedent),
  drop "text" from search_fields, rewrite the two shipped assertions in test_support_admin.py
  that pin the leaky configuration, and add exactly two entries to
  test_admin_pii_containment.py asserting on the rendering statement. Q-D12 is resolved as
  Option D: no registry walk, no declared column set, no exempt list, no new test module.
goals:
  - "stop a changelist screenshot, CSV export or support bundle from bulk-disclosing a requester's Telegram ID"
  - "stop the whole ticket corpus from being a free-text search target for the moderator role"
  - "make the next user-adjacent admin fail loudly instead of silently"
  - "stay correct on either mask_telegram_id construction, so BLOCK 4's landing is a no-op here"
files:
  - path: "src/backend/apps/core/admin.py"
    targets:
      - type: class
        name: SupportTicketAdmin
      - type: class_attribute
        name: list_display
      - type: class_attribute
        name: search_fields
      - type: class_attribute
        name: readonly_fields
      - type: method
        name: has_delete_permission
      - type: method
        name: chat_id_display
      - type: method
        name: telegram_id_display
    semantic_anchors:
      replace_text_containing:
        - 'list_display = ["ticket_ref", "status", "user", "chat_id", "telegram_id", "created_at"]'
        - 'search_fields = ["ticket_ref", "telegram_id", "username", "text"]'
      insert_after:
        type: method
        value: has_delete_permission
      insert_import:
        module: apps.core.utils.sanitize
        name: mask_telegram_id
      never_touch:
        - class: SupportContactAdmin
        - class: SiteConfigAdmin
        - "class_attribute: SupportTicketAdmin.readonly_fields (re-pin only, never change)"
  - path: "src/backend/apps/core/tests/test_support_admin.py"
    targets:
      - type: function
        name: test_support_ticket_admin_list_display
      - type: function
        name: test_support_ticket_admin_search_fields
      - type: function
        name: test_support_ticket_admin_readonly_fields
      - type: function
        name: test_support_ticket_changelist_renders_masked_identifiers
    semantic_anchors:
      replace_text_containing:
        - 'expected = ["ticket_ref", "status", "user", "chat_id", "telegram_id", "created_at"]'
        - '"ticket_ref",\n        "telegram_id",\n        "username",\n        "text",'
      insert_after:
        type: function
        value: test_support_ticket_admin_readonly_fields
      never_touch:
        - function: test_support_contact_registered_in_admin
        - function: test_support_ticket_registered_in_admin
        - function: test_support_contact_admin_list_display
        - function: test_support_contact_admin_list_editable
        - function: test_support_contact_admin_list_filter
        - function: test_support_contact_admin_search_fields
        - function: test_support_contact_admin_add_enabled
        - function: test_support_contact_admin_delete_enabled
        - function: test_support_ticket_admin_list_filter
        - function: test_support_ticket_admin_add_permission_false
        - function: test_support_ticket_admin_delete_permission_false
  - path: "src/backend/apps/users/tests/test_admin_pii_containment.py"
    targets:
      - type: module
        name: test_admin_pii_containment
      - type: function
        name: test_login_token_list_display_masks_telegram_id
      - type: function
        name: test_support_ticket_chat_id_display_masks_identifier
      - type: function
        name: test_support_ticket_telegram_id_display_masks_identifier
      - type: helper
        name: _assert_no_raw_telegram_id
    semantic_anchors:
      insert_after:
        type: function
        value: test_login_token_list_display_masks_telegram_id
      insert_after_text_containing:
        - 'User-FK helpers; ``mask_telegram_id(...)`` for the standalone LoginToken).'
      never_touch:
        - "the six UserAdmin form-contract tests (04-AUT-005) - phase 04 owns them"
        - "helper: _assert_no_raw_telegram_id"
        - "helper: _admin_request"
        - "fixture: staff_user"
  - path: "src/backend/apps/core/utils/sanitize.py"
    targets:
      - type: function
        name: mask_telegram_id
    semantic_anchors:
      read_only: true
      note: >
        Called, never re-implemented. Its construction is BLOCK 4's to change; this block
        must not depend on what it emits.
changes:
  - action: add_import
    description: >
      Import mask_telegram_id from apps.core.utils.sanitize in core/admin.py, beside the
      existing apps.core.models import. One import; no new production module.
  - action: modify_code
    description: >
      Add the two masked display methods to SupportTicketAdmin and name them in list_display
      in place of the raw "chat_id" and "telegram_id" entries. Both delegate to
      mask_telegram_id; neither carries a width, a length, a prefix or a hash shape, and
      neither adds a local None branch - None-tolerance is inherited from the callee so
      BLOCK 13 does not have to rewrite them.
    code_hint: |
      @admin.display(description="Chat ID (masked)", ordering="chat_id")
      def chat_id_display(self, obj: SupportTicket) -> str:
          """Render the masked Telegram chat ID of the requester (06-PII-106)."""
          return mask_telegram_id(obj.chat_id)

      @admin.display(description="Telegram ID (masked)", ordering="telegram_id")
      def telegram_id_display(self, obj: SupportTicket) -> str:
          """Render the masked Telegram ID of the requester (06-PII-106)."""
          return mask_telegram_id(obj.telegram_id)
  - action: modify_code
    description: >
      In SupportTicketAdmin.list_display replace the two raw column names with
      "chat_id_display" and "telegram_id_display", keeping the surrounding order
      (ticket_ref, status, user, ..., created_at) unchanged.
  - action: modify_code
    description: >
      In SupportTicketAdmin.search_fields drop "text", leaving
      ["ticket_ref", "telegram_id", "username"]. telegram_id STAYS (0.6.3 #11).
  - action: modify_tests
    description: >
      Rewrite test_support_ticket_admin_list_display and test_support_ticket_admin_search_fields
      to the new lists. Re-pin test_support_ticket_admin_readonly_fields unchanged and say in
      its docstring that the block deliberately left readonly_fields alone. Add a new
      changelist-rendering test: a ticket belonging to a real data subject renders the mask
      and never the raw identifier. Build the staff actor locally - conftest.py is off-limits.
      No assertion on a mask length, a column count or the presence of a symbol.
  - action: modify_tests
    description: >
      Add exactly two tests to test_admin_pii_containment.py asserting on the rendering
      statement: the helper delegates to mask_telegram_id and references obj.<column>, and
      the raw column name is no longer what list_display names. Never assert a banned token.
      Add, do not disturb: phase 04's six UserAdmin form-contract tests and the four
      existing helper tests stay untouched.
  - action: modify_docs
    description: >
      Append one paragraph to the test_admin_pii_containment.py module docstring stating the
      new residual: helper enumeration cannot catch a future admin that renders a raw
      identity column WITHOUT a helper. Module docstring only - no user-visible string, so
      no .po change and no i18n gate.
acceptance_criteria:
  - "the SupportTicketAdmin changelist row for a ticket belonging to a real data subject renders the mask and never the raw chat_id or raw telegram_id"
  - "text is no longer a search target: SupportTicketAdmin.search_fields resolves to ticket_ref, telegram_id and username only"
  - "telegram_id REMAINS in search_fields - removing it is BLOCK 13's call, not this block's"
  - "SupportContactAdmin is byte-identical: no list_display, search_fields, readonly_fields, docstring or permission change, and every SupportContactAdmin test passes unchanged"
  - "src/backend/apps/core/tests/test_support_admin.py and src/backend/apps/users/tests/test_admin_pii_containment.py are green"
  - "no mask width, length, prefix or hash shape is hard-coded anywhere in this block's diff - production or tests; both helpers and every new assertion go through mask_telegram_id"
  - "both display methods appear in list_display and the raw chat_id / telegram_id entries do not"
  - "a ticket whose identifier column is None renders without raising, inherited from mask_telegram_id rather than a local branch"
  - "the two new guard entries assert on the rendering statement (mask_telegram_id delegation plus obj.<column>) and never on a banned token"
  - "the new guard was demonstrated red against the pre-fix SupportTicketAdmin before it went green, and the failure output is in the commit body"
  - "the test_admin_pii_containment.py docstring states the residual: a future admin rendering a raw identity column WITHOUT a helper is not caught"
  - "the commit body names which two of the three test_support_admin.py assertions changed and why, and that readonly_fields was deliberately re-pinned unchanged (project rule 2, C-11)"
  - "the six phase-04 UserAdmin form-contract tests, _assert_no_raw_telegram_id, _admin_request and staff_user are untouched"
  - "no migration, no schema change, no template, no .po file, no new production module, and src/backend/conftest.py is untouched"
tests_required:
  - id: guard_is_red_before_the_fix
    assertion: >
      Add the two new entries, run them against the pre-fix SupportTicketAdmin (raw
      list_display, no helper), capture the failure, then implement the helpers and re-run.
      The failure output goes in the commit body. The temporary pre-fix state must NOT be
      in the committed diff.
  - id: changelist_renders_the_mask
    assertion: >
      Behaviour, not trivia (plan section 1.5). With a persisted staff actor and a
      SupportTicket row whose chat_id and telegram_id are real, non-traceable values, the
      changelist response for SupportTicketAdmin contains the value mask_telegram_id
      produces for each column and contains neither raw identifier. Do NOT assert a mask
      length, a hash shape or a column count.
  - id: source_asserts_the_rendering_statement
    assertion: >
      The source-level companion: inspect.getsource on each new helper shows the
      mask_telegram_id delegation and the obj.<column> reference, following the module's
      existing idiom. Never assert the bare token telegram_id is absent - the docstrings
      legitimately name it.
  - id: text_is_not_searchable
    assertion: >
      A search for a term that appears only inside a ticket body returns no SupportTicket
      rows, while a search by ticket_ref still does. Behavioural proof that the corpus is
      no longer a free-text target, not a list-membership assertion.
  - id: telegram_id_remains_searchable
    assertion: >
      SupportTicketAdmin.search_fields still resolves telegram_id, and a search by the raw
      numeric telegram_id still finds the ticket. This is the anti-regression for support's
      only identifier lookup (0.6.3 #11).
  - id: support_contact_admin_untouched
    assertion: >
      Every SupportContactAdmin test passes unchanged and its list_display / search_fields
      are byte-identical to the pre-block values. The new guard does not flag it - there is
      no walk, so it could not.
  - id: no_mask_shape_pinned
    assertion: >
      Neither production nor the new tests contain a mask width, length, prefix or hash
      shape. This is what makes BLOCK 4's keyed-HMAC change land here as a no-op; review the
      diff for any literal that pins mask_telegram_id's output.
  - id: standard_compliance
    assertion: >
      Per plan section 1.5, no test asserts a literal private name, a line number, a
      template-string substring, a column count, or the mere presence of a symbol. Do NOT
      test the module docstring's text.
tests_to_run:
  - "src/backend/apps/core/tests/test_support_admin.py"
  - "src/backend/apps/users/tests/test_admin_pii_containment.py"
  - "src/backend/apps/core/tests"
commands:
  setup: "$dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'"
  test: "$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS=\"src/backend/apps/core/tests/test_support_admin.py src/backend/apps/users/tests/test_admin_pii_containment.py --tb=short\" test"
  test_apps: "$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS=\"src/backend/apps/core/tests src/backend/apps/users/tests/test_admin_pii_containment.py --tb=short\" test"
  lint: "uv run ruff check src/backend/apps/core/admin.py src/backend/apps/core/tests/test_support_admin.py src/backend/apps/users/tests/test_admin_pii_containment.py"
  typecheck: "uv run basedpyright src/backend/apps/core/admin.py"
  notes: >
    PYTEST_OPTS is unquoted in docker/entrypoint-test.sh, so each token is word-split on
    spaces, and setting it REPLACES the default pytest args (--reuse-db --tb=short
    --durations=10 -n auto --maxprocesses=4 --dist loadgroup) - a targeted run therefore
    loses xdist parallelism and DB reuse. Never use --override-ini=addopts=, which strips
    --import-mode=importlib. Never `uv run pytest` on the host: there is no database on
    localhost:5432. Concurrent runs share one test_mko_bazuna: a mass
    ForeignKeyViolation on auth_permission / django_content_type, or "database
    test_mko_bazuna does not exist", is a teardown artefact - re-run serially before
    reporting a defect. This block changes no migration, so test-recreate is not required.
commit:
  message: "fix(core): mask support-ticket identifiers in the admin changelist (06-PII-106)"
  body_must_state:
    - "that test_support_ticket_admin_list_display and test_support_ticket_admin_search_fields were rewritten to the new lists because production code is king and the configuration was the defect (project rule 2, C-11), and that test_support_ticket_admin_readonly_fields was deliberately re-pinned unchanged because readonly_fields is not in scope for this block"
    - "Q-D12 resolved as Option D: two entries in test_admin_pii_containment.py, no registry walk, no declared identity-column set, no exempt list - and WHY, so a future maintainer does not 'simplify' it into a blanket ban and red-flag SupportContactAdmin (VAL-007)"
    - "that SupportContactAdmin is byte-identical and was NOT touched: its telegram_id is a configured support-channel id, not a data subject's, and channels are meant to be staff-editable"
    - "the red demonstration of the new guard, with the failure output against the pre-fix SupportTicketAdmin"
    - "that both display methods DELEGATE to mask_telegram_id and that no mask width, length, prefix or hash shape is asserted anywhere, so BLOCK 4's keyed-HMAC change lands here as a no-op and the helpers stay valid on either construction"
    - "that telegram_id deliberately STAYS in search_fields (support's only identifier lookup) and the raw-ID-search question is routed to the coordinator; ConsentRecord.session_key is BLOCK 15's"
    - "that the helpers are None-tolerant by inheritance, so BLOCK 13's nullable migration does not require rewriting them"
    - "that no migration, no schema change, no template, no .po file, no new production module and no edit to conftest.py were made"
    - "that test_admin_pii_containment.py is shared with phase 04 and only the two new entries plus an appended docstring paragraph were added"
    - "every citation cycle-scoped as 06-PII-1xx, never bare PII-1xx"
extra_context: |
  BINDING CONSTRAINTS (verbatim from the plan's BLOCK 12 section)

  1. **Delegate; never hard-code the mask shape.** Both display methods **call**
     `mask_telegram_id`. No width, no length, no prefix, no hash shape anywhere in this
     block's diff — **production or tests**. BLOCK 4 changes that construction (keyed HMAC,
     `tg_` prefix preserved, width changing) and its decision (Q-D8) is still the owner's;
     delegation is exactly what makes this block correct on either construction, and a pinned
     mask would turn BLOCK 4's landing into a breaking change here.
  2. **`None`-tolerant by construction.** `mask_telegram_id(None)` already returns a
     non-empty string, so the helpers **inherit** `None`-tolerance by delegating. Do **not**
     add a local `if obj.chat_id is None` branch and do not add a second construction. BLOCK 13
     makes both columns nullable and must not have to rewrite these methods (§4.2: the 12 → 13
     edge is a *shape* dependency, not a logic one).
  3. **`SupportContactAdmin` is not a violation and must be left byte-identical.** Its
     `telegram_id` is a configured support-channel id, and channels are meant to be
     staff-editable. **Do not** add a `readonly_fields` entry, a permission override, a masking
     helper, a docstring change or any other edit to that class, and do not edit any
     `SupportContactAdmin` test.
  4. **`telegram_id` stays in `search_fields`.** `text` goes; `ticket_ref`, `telegram_id` and
     `username` stay, for genuine support lookups (§0.6.3 #11). BLOCK 13 makes the columns
     nullable first, and `UserAdmin` and `LoginTokenAdmin` both keep the raw `telegram_id` in
     their own search — removing it here alone would create a **new** inconsistency. **Whether
     searching by a raw `telegram_id` is itself an exposure is routed to the coordinator**, not
     decided in this block.
  5. **`ConsentRecord.session_key` is BLOCK 15's.** It appears in **both**
     `ConsentRecordAdmin.list_display` and `.search_fields` in `apps/users/admin.py`. Do not
     touch either, and do not add it to the guard.
  6. **The guard asserts on the rendering statement, never on a banned token.** Assert that
     the helper's source contains `mask_telegram_id` and references `obj.<column>`. Do **not**
     assert `"telegram_id" not in source` — the module's own docstrings legitimately name the
     field. Follow the module's existing `_assert_no_raw_telegram_id` idiom.
  7. **Two new entries only.** Exactly `chat_id_display` and `telegram_id_display`, both in
     `test_admin_pii_containment.py`. **No registry walk, no declared column set, no exempt
     list, no new test module, no new production module.** A future "simplification" into a
     blanket ban is the exact failure mode `VAL-007` names; the trap goes in the module
     docstring and in the commit body.
  8. **The new guard must be demonstrated red against the pre-fix code** before it goes green,
     and the failure output goes in the commit body.
  9. **`conftest.py` is off-limits** (§5.3). The changelist-rendering test needs a persisted
     staff actor: build it locally in the test module, the way
     `test_admin_pii_containment.py::_admin_request` / `staff_user` already do.
  10. **No migration, no schema change, no template, no `.po` file.** `SupportTicket` stays in
      `apps/core/models.py` (`apps/support/` does not exist). Rollback is a straight revert.

  Q-D12 — RESOLVED, and not to be reopened

  Option D, extend the helper-enumeration precedent. Add exactly two entries to
  `apps/users/tests/test_admin_pii_containment.py` (`SupportTicketAdmin.chat_id_display`,
  `.telegram_id_display`), asserting on the *rendering statement* — delegates to
  `mask_telegram_id`, references `obj.<col>` — exactly like the module's four original
  helper tests.

  There is **no registry walk**, so the `SupportContactAdmin` false-positive the older
  prose spends a paragraph engineering around **does not exist**. Two rationales must
  survive into the commit body:

  - *Why the assertion is on the rendering statement and not on a banned token:* the module
    asserts `"str(obj.user.telegram_id)" not in source` rather than banning the token,
    **because docstrings legitimately name `telegram_id` in prose**.
  - *Why cross-model rendering needs no declaration:* `AdAdmin.user_link`,
    `AnalyticsEventAdmin.user_link` and `moderation.admin.log_user_link` all render
    `str(obj.user)` — **another model's** column. No per-model column set can ever reach
    them, so cross-model containment is owned by helper enumeration **by construction**.

  The residual — it cannot catch a future admin that renders a raw identity column
  **without** a helper — belongs in the module docstring, which already documents a
  similar limit for PII-001. That docstring edit is a required part of this task.

  WHY THE MODULE HAS TEN TESTS, NOT FOUR

  `test_admin_pii_containment.py` now holds the four original helper-enumeration tests plus
  six phase-04 `UserAdmin` form-contract tests (`04-AUT-005`). **Phase 04 owns part of this
  file.** Add two entries; disturb nothing. Re-read the file immediately before editing.

  A COORDINATION NOTE ON BLOCK 4's OWN CONSTRAINT 3

  BLOCK 4's `extra_context` binding constraint 3 states that
  `test_admin_pii_containment.py` "is not edited at all". That constraint governs **BLOCK 4's
  commit** — BLOCK 4 must not touch the module. It is **not** a phase-wide freeze, and it
  does not bind this block: the two entries below are BLOCK 12's required edit and they are
  compatible, because the delegation assertion they make ("the helper calls
  `mask_telegram_id`") is exactly the assertion BLOCK 4 is written to keep true. If the two
  blocks are implemented in either order, both commits are valid. Do not resolve this by
  dropping the guard.

  WHAT IS NOT BUILT

  No registry walk. No declared identity-column set. No exempt-admin list. No new test
  module. No new production module. No `readonly_fields` change. No permission override. No
  removal of `telegram_id` from `search_fields`. No nulling, masking or migration of any
  `SupportTicket` column — that is BLOCK 13. No retention boundary for `SupportTicket.text` —
  not decided in phase 06; BLOCK 3's inventory carries the `RETAIN` entry whose reason names
  this block.
```

**Tests required** (full specification is in the task YAML above)

1. **The guard, demonstrated red first.** Add the two entries, run them against the
   pre-fix `SupportTicketAdmin` (raw `list_display`, no helper), capture the failure, then
   implement and re-run. The failure output goes in the commit body; the pre-fix state must
   not be in the committed diff.
2. **The changelist renders the mask.** A ticket belonging to a real data subject renders
   `mask_telegram_id(...)` in both identifier columns and **neither raw value**. This is the
   behaviour assertion; the source-level delegation assertion is its companion, not a
   substitute for it. **Never** assert a mask length, a hash shape or a column count.
3. **`text` is not searchable.** A term that appears only in a ticket body matches no
   `SupportTicket` row; a `ticket_ref` search still does.
4. **`telegram_id` is still searchable.** The raw numeric ID still finds the ticket. This is
   the anti-regression for support's only identifier lookup (§0.6.3 #11).
5. **No shape pinned.** Review the diff for any literal that fixes `mask_telegram_id`'s
   output — in production *or* in the tests. BLOCK 4's keyed-HMAC change must land here as a
   no-op.
6. **Regression** — every `SupportContactAdmin` test, plus `..._list_filter`,
   `..._add_permission_false` and `..._delete_permission_false`, passes **unchanged**, and the
   six phase-04 `UserAdmin` form-contract tests in the containment module are untouched.

**Risk and rollback**

- *Risk (the trap):* a later maintainer "simplifies" the guard into a blanket ban over the
  admin registry and it red-flags `SupportContactAdmin`, whose `telegram_id` is a configured
  support channel. Mitigation: Option D has no walk to simplify; the trap is named in the
  module docstring, in binding constraint 3 and in the commit body.
- *Risk (the lookup):* dropping `telegram_id` from `search_fields` would remove support's
  only identifier lookup. **The block keeps it.** Whether searching by a raw `telegram_id` is
  itself an exposure is a coordinator question (§0.6.3 #11), not a decision this block may
  take.
- *Risk (the coupling):* a test that pins the mask's current output would make BLOCK 4's
  construction change a breaking change here. Mitigation: binding constraint 1 and
  `tests_required.no_mask_shape_pinned`.
- *Risk (the shared file):* `test_admin_pii_containment.py` is contended with phase 04.
  Mitigation: add two entries and one appended docstring paragraph; touch nothing else; stage
  explicitly by path.
- *Rollback:* a straight revert. No data, no schema, no migration, no persisted side effect.

---

### BLOCK 13 — Gate support intake on consent and erase `SupportTicket` on erasure (06-PII-101, CRITICAL)
| **Findings owned** | `06-PII-101` - **the only CRITICAL in the phase** |
| **Depends on** | **BLOCK 3** (the inventory, landed), **BLOCK 9** (`withdraw_consent`, `474a68d`, landed), **BLOCK 12** (admin containment, landed), **BLOCK 6 / BLOCK 7** (`account_state_q`, `ae461da` + `b03c1a0` / `1257603`, landed). **BLOCK 10 and BLOCK 11 have NOT landed** - see constraint 11 |
| **Blocks** | nothing in this plan; it is the phase's headline deliverable |
| **Priority** | **P0** |
| **Risk level** | **CRITICAL** - a schema state change, an irreversible row destruction, and a behaviour-visible gate on the only support-intake surface |
| **Required agents** | **Planner - Implementor - Validator** (the Researcher's Q-D2 question is closed by the owner) |

---

**The owner's decision (Q-D2, RESOLVED).** This replaces every option the previous revision carried.

1. **A deleted user's `SupportTicket` rows are deleted with them.**
2. **A user who has not consented to personal-data storage, who tries to contact Support, is shown a clear notice that sending requires consent to storing personal data. Without that consent, no ticket is created.**
3. **An existing user who withdraws consent is shown a warning that their stored data will be deleted. On confirm, all their personal data is deleted, including their `SupportTicket` rows.**

The row is **deleted, not scrubbed**. There is no replacement lookup key to design, no nullable-column migration, and no idempotent backfill. The previous revision's three-option Q-D2 menu, its "decision record plus implementation of the chosen shape" framing, and its scrub-oriented data migration are all **obsolete**.

---

**The defect (C-1, C-7), re-verified.** `SupportTicket` denormalises identity into its own columns: `chat_id` and `telegram_id` are **non-nullable** `BigIntegerField`s copied verbatim from the Telegram sender, `username` is `CharField(max_length=255, null=True, blank=True)`, and the account link is `ForeignKey(..., on_delete=SET_NULL, null=True, blank=True, related_name="support_tickets")`. `withdraw_consent()` never touches `support_tickets`, and `consent_hard_delete` NULLs exactly two references (`AnalyticsEvent.user_id`, `ModeratorActionLog.user_id`) before `queryset.delete()`. Django's collector honours the ticket FK's `SET_NULL`, so the ticket row is **updated to `user_id = NULL` and kept**, with every raw identifier and the whole message body byte-for-byte intact. The published `privacy.html` section 6 promises *"All personal data is permanently erased within 30 days of withdrawal"* - a direct, provable breach.

**The impact wording is corrected (C-7).** The row is **not** unfindable: `SupportTicket.objects.filter(user_id__isnull=True)` finds it in one query. The defect is **retention**, and it is silent and self-concealing because `SET_NULL` removes the only user-scoped handle a future purge would have used.

**Surface - exactly one production writer.** `src/telegram_bot/handlers/support.py::handle_support_orm`. There is **no** HTTP contact route, **no** HTMX partial, **no** API endpoint, **no** seeder, **no** management command and **no** admin write path (`SupportTicketAdmin.has_add_permission` / `has_delete_permission` are both `False`). Every other "contact" surface is a Telegram deep-link: `templates/components/footer.html` and `templates/ads/detail.html` via `{% telegram_deep_link %}` -> `templates/privacy.html` -> `src/telegram_bot/handlers/contact.py`. **Do not confuse** `src/backend/apps/core/services/contact.py` (`can_contact_seller`, `record_contact_initiated`) - that is the buyer->seller relay writing an `AnalyticsEvent`, not a ticket.

**Identity provenance is clean.** `chat_id` / `telegram_id` / `username` come from the aiogram `Update` (Telegram-signed); the `user` FK comes from the server-side FSM `data["user_id"]`, backfilled by `AccountStateMiddleware` via `User.objects.get(chat_id=...)`. There is **no** client-supplied identity field and **no** spoofing surface. The previous revision's Q-D2 question 1 ("what replaces the identity as a support lookup key?") is therefore moot.

**`AccountStateMiddleware` gates before the handler.** `_evaluate_user_state(user, ...)` **fails open** on `user is None`; a withdrawn / banned / deleted user is hard-blocked; a **deactivated** user is admitted by `_deactivated_carve_out`; and `SUPPORT_START` is **not** a contact deep-link, so a DECLINE user is rejected at `/start` before they can tap it (pre-existing, documented).

---

**The owner's three cases mapped to the three edits.**

| Owner case | Edit |
|---|---|
| **1** - deleted user means tickets deleted | `SupportTicket.user` -> `on_delete=models.CASCADE` + an `AlterField` migration; plus the explicit `consent_hard_delete` sweep for the path where the row was orphaned first |
| **2** - no consent means notice, **no ticket** | New instance predicate `can_store_personal_data(user)`; gate in `handle_support_start` **and** `handle_support_message`; one module-level `gettext_lazy` notice |
| **3** - withdraw means warn, then delete everything incl. tickets | `withdraw_consent` deletes `user.support_tickets` inside its existing `atomic()`, **before** `soft_delete_user_ads(user)`; the dashboard `onclick` confirm string is extended to name support requests |

---

**Why deleting the row is conservation-correct.** `SupportTicket` is the **outlier** on the retained side: it holds no accountability record, no claim, no moderation decision and no aggregate function.

| Referencing row | `on_delete` | Side | Why |
|---|---|---|---|
| `ads.Ad` | `CASCADE` | delete | the ad cannot exist without its author |
| `ads.AdFavorite` | `CASCADE` | delete | meaningless without the user |
| `trust.SellerTrustScore`, `trust.SellerVerification` | `CASCADE` | delete | derived from the person's activity |
| `search.SavedSearch`, `search.SearchHistory` | `CASCADE` | delete | behavioural traces |
| `users.ConsentRecord` | `SET_NULL` | retain | **proof** that consent was given / declined |
| `analytics.AnalyticsEvent` | `SET_NULL` | retain | security + aggregate metrics |
| `moderation.ModeratorActionLog` | `SET_NULL` | retain | moderation accountability |
| `moderation.ModerationCriteria.updated_by` | `SET_NULL` | retain | who last edited the rules |
| `ads.Ad.published_by`, `ads.Ad.moderated_by` | `SET_NULL` | retain | publish / moderation accountability |
| `core.SupportTicket` | **`CASCADE` (was `SET_NULL`)** | **delete** | **nothing is derived from a ticket** |

**`LoginToken` has no `User` FK at all** - `telegram_id` is a plain nullable `BigIntegerField`, matched by value in `withdraw_consent`. The previous revision's belief otherwise was wrong.

---

**The three forks - decided by the Tech Lead. Implement; do not reopen.**

**Fork 1 - an unregistered / anonymous sender is REFUSED.** The Auditor proved the bot holds **no session and no cookies**, and `ConsentRecord.session_key` is keyed on the Django session the bot never touches, so a cookie-only anonymous consent predicate is **unverifiable from the bot**: trusting a web cookie it cannot see is not implementable. The gate therefore refuses a `chat_id` that resolves to no `User`, and the notice **directs the sender to sign in / accept consent first**. `apps/users/context_processors.py::consent_state`'s `consent_shown` means **"has acted"**, not "has accepted" (`_ACTID_COOKIE_VALUES = ("true","accepted","declined","withdrawn")`), so it is not the predicate either. **Consequence:** `contact_us` becomes registration-gated, and two bot tests are **re-pinned to assert NO ticket** - `src/telegram_bot/tests/test_support.py::TestSupportMessage::test_persists_and_delivers` (its `user304` is unregistered, i.e. exactly the no-consent case) and `::test_anonymous_user_has_null_user_fk`. The module docstring line *"Anonymous senders leave the `user` FK null"* becomes false and must be corrected. A **third** test, `::test_registered_user_is_attributed`, creates a `User` with **no** `consent_given_at` and a message whose `chat.id` does not match that user's `chat_id` - it must be re-pinned to set `consent_given_at` and align the chat id, or it fails on the new gate.

**Fork 2 - the deactivation carve-out gets NO exemption from the storage-consent gate, but the restoration channel stays open.** `src/telegram_bot/tests/test_bot_deactivation_matrix.py::test_deactivated_user_can_complete_the_support_ticket` creates a deactivated user **with no `consent_given_at`**, so a naive `consent_given_at IS NOT NULL` conjunct refuses them. The owner was explicit, so **do not exempt the carve-out**. Instead **re-pin that test** so a deactivated user **who has consented** still completes a ticket - which is the carve-out's real purpose - and add the complementary case: a deactivated user **without** consent is refused with the notice. That satisfies the owner's rule *and* keeps "contact support to restore your account" reachable for anyone who actually consented. `_make_deactivated` forwards `**overrides` to `make_user`, so `consent_given_at=timezone.now()` is available. **The old test must not stay green by accident** - assert the consent field explicitly rather than relying on a fixture default.

**Fork 3 - `ticket_ref` reuse: document, do not fix.** `SupportTicket.save()` computes `SUP-YYYYMM-NNN` as `count() + 1` over **live** same-month rows, so deleting a mid-month ticket makes the next ticket **reuse a reference a user has already quoted to the desk**. This block documents the collision window in `docs/02-database/db-schema.md` and records it as a known limitation with a follow-up. It **does not change the algorithm** - changing a user-visible identifier is a separate, behaviour-visible change. `src/backend/apps/core/tests/test_support_models.py::TestSupportTicketRef::test_ticket_ref_sequence_increments` pins the current behaviour and must stay green. **Say so explicitly so no implementor "helpfully" fixes it.**

---

**Binding constraints**

1. **Do NOT mutate `account_state_q`.** BLOCKS 6 and 7 are implemented and validated against its exact **five** conjuncts (`is_deleted=False`, `is_declined=False`, `is_banned=False`, `consent_revoked_at IS NULL`, `is_active=True`), and BLOCK 7's *"one declaration drives all four sites"* test mutates it. It deliberately omits `consent_given_at` because it answers *"may this account receive messages"*; a never-consented registered user passes all five. Add a **separate, dedicated predicate**.
2. **The bot gate evaluates the predicate against the server-resolved actor, not the FSM value alone.** Resolve the actor server-side from the signed `chat_id` - the same key `AccountStateMiddleware._resolve_user` uses (`User.objects.get(chat_id=...)`) - inside the single existing `sync_to_async` ORM call; a miss is a refusal. When the FSM `data["user_id"]` is present it is **cross-checked** against the resolved actor and a mismatch refuses (defence in depth against a stale FSM).
3. **The gate lives at the bot boundary, not the model.** `SupportTicket.user` stays nullable and `test_support_models.py::TestSupportTicketAnonymous` must keep passing - the model may still store an unattributed ticket; the *bot* refuses to create one.
4. **`chat_id` / `telegram_id` are non-nullable and STAY non-nullable.** The row is deleted, not scrubbed.
5. **`CASCADE` cannot fire at withdrawal.** `withdraw_consent` is a **soft** delete; a `User` row is hard-deleted in exactly two places - `consent_hard_delete.Command.handle` (step 7, `queryset.delete()`, inside its `transaction.atomic()` + `advisory_lock(CONSENT_HARD_DELETE)`) and the Django admin (`UserAdmin.has_delete_permission`, superuser only). The explicit `user.support_tickets...delete()` inside `withdraw_consent` is therefore **load-bearing**, not belt-and-braces.
6. **Place the withdrawal ticket delete BEFORE `soft_delete_user_ads(user)`** so the existing `test_withdraw_is_atomic_rollback` (which monkeypatches `soft_delete_user_ads` to raise) still exercises a full rollback - and extend its assertion list with the ticket.
7. **`SET_NULL` -> `CASCADE` is an `AlterField` with ZERO DDL.** Django dispatches `on_delete` in Python (`Collector.collect`) and the live FK has no `ON DELETE` clause, so **`sqlmigrate` is empty**. Acceptance is **behavioural**, never a SQL diff.
8. **The orphan sweep is a correctness statement, not a data fix.** The already-orphaned (`user_id IS NULL`) population is unreachable by any cascade and is **0 rows** in dev and test today. Delete it explicitly in `consent_hard_delete` and say so in the code comment - do **not** write it up as remediation of live data.
9. **The conservation axis is verify-only.** Verified: **no** trigger on `support_tickets` (contrast `ads_search_vector_update`), **no** GIN/tsvector/trigram index, **no** aggregate (`DailyAdMetrics` is ad-scoped; `contacts_count` is fed by the relay), **no** `AnalyticsEvent` type for tickets, **no** `last_notified`-style stamp (only `created_at`), **no** signal receiver (`apps/core/signals.py` handles only `SiteConfig` / `SupportContact`). So: **one** test proving no `AnalyticsEvent`, no `DailyAdMetrics` and no other row changes after a ticket delete.
10. **No migration may delete rows.** The irreversible destruction happens in the runtime paths (`withdraw_consent`, `consent_hard_delete`), never in `RunPython`. `makemigrations --check` must be clean.
11. **Ordering rule.** `withdraw_consent` has exactly **one** landed writer (BLOCK 9, `474a68d`). BLOCK 13 is its **next**. **BLOCK 10 and BLOCK 11 have not landed.** If either lands first, **re-read `withdraw_consent` immediately before editing** and re-apply against the then-current body - never merge by hand.
12. `AdvisoryLockId.CONSENT_HARD_DELETE == 3` **must not be renumbered**, and the command's summary log must keep reporting the **user count** and the words `"cascaded"` / `"rows incl. ads/images"`.
13. **No `core` migration number may be assumed.** Read `src/backend/apps/core/migrations/` immediately before generating - `0005_scheduler_daily_state` is today's tip and phase 02 claimed a `0006`. **Never renumber.**

---

**File surface (semantic units)**

| File | Symbol / target | Change |
|---|---|---|
| `src/backend/apps/core/models.py` | `SupportTicket.user` | `on_delete=models.CASCADE` |
| `src/backend/apps/core/migrations/<next>_supportticket_user_cascade.py` | **new** | `AlterField` only; **no DDL**, **no `RunPython`** |
| `src/backend/apps/users/services/account_state.py` | **new** `can_store_personal_data(user)` | Sits beside `account_state_q`; **composes** from the same fields **plus** `consent_given_at IS NOT NULL` |
| `src/backend/apps/users/services/deletion.py` | `withdraw_consent` | delete `user.support_tickets` inside the existing `atomic()` |
| `src/backend/apps/core/management/commands/consent_hard_delete.py` | `Command.handle` | ticket sweep + explicit orphan sweep, both **before** `queryset.delete()` |
| `src/backend/apps/core/admin.py` | `SupportTicketAdmin` **docstring only** | stop calling it an audit trail; permissions unchanged |
| `src/telegram_bot/handlers/support.py` | `handle_support_start`, `handle_support_message` | consent gate + one notice |
| `src/telegram_bot/handlers/support.py` | **new** `SUPPORT_CONSENT_REQUIRED_MESSAGE` | module-level `gettext_lazy` constant |
| `src/backend/apps/users/services/pii_inventory.py` | the **four** `core.SupportTicket` entries | -> `ErasureAction.DELETE_ROW`, reasons rewritten; `REVIEWED_NON_IDENTITY_COLUMNS["core.SupportTicket"]` stays `{"status","ticket_ref"}` |
| `src/backend/apps/users/tests/test_pii_inventory.py` | `test_retained_free_text_entries_name_their_owning_block` | **one** test - contended file, touch nothing else |
| `src/backend/templates/ads/dashboard.html` | the withdraw `onclick` confirm string | extended to name support requests; **button label unchanged** |
| `src/backend/templates/privacy.html` | section 6 "Erased immediately on withdrawal" | add a support-requests bullet |
| `docs/02-database/db-schema.md` | `user_id` row, the "read-only audit trail" sentence, the `ticket_ref` reuse note | all three become true again |
| `docs/99-agent/architecture.md` | "Bot Support Intake Flow" access-control paragraph | it currently says anonymous users may reach support |
| `src/backend/locale/{ru,bs,en}/LC_MESSAGES/django.po` | **3** msgid operations, hand-appended | see below |

**Choice of predicate - instance, not a second `Q`.** A **single instance-level `can_store_personal_data(user: User) -> bool`** is the implementation. Reasons: (a) `account_state_q` is contract-frozen by BLOCKS 6/7 (constraint 1); (b) **no consumer needs a queryset form** - the bot gate has one already-resolved instance, `withdraw_consent` has `user`, and `consent_hard_delete` filters *users to delete*, not *users who may store data*; (c) a second `Q` factory would be a speculative second declaration with zero constraining consumers (rule 5, avoid overengineering); (d) composing from `get_account_state(user)` plus the consent field keeps the two predicates visibly aligned without sharing a mutable declaration. **If** a queryset form proves necessary during implementation, give it its **own** name (e.g. `storable_personal_data_q`) - never extend `account_state_q`.

---

**i18n (this block trips the gate; it is expected)**

- Three msgid operations: the **new** bot notice, the **replaced** withdraw confirm string, the **new** privacy.html section 6 bullet.
- **The msgid must exist in ALL THREE `.po` files** (`test_extraction_completeness`) and **`ru`/`bs` msgstr must be non-empty** (`test_no_empty_msgstr`); `en` may be empty.
- **Append only, by hand.** Never a wholesale `makemessages` - it would discard phase 05's and phase 14's tree. `.mo` files are gitignored; never commit one.
- Retire the old withdraw msgid with a **`#~`** obsolete block; the shared parser ignores `#~` lines.
- The bot notice is covered by **`test_bot_no_hardcoded_messages`**, which AST-scans `src/telegram_bot/handlers/*.py` and requires `.answer()` / `.reply()` / `.edit_text()` / `.edit_caption()` / `.send_message()` / `button(text=...)` to wrap text in `_()` -> use a module-level `gettext_lazy` constant.
- The withdraw warning is a `gettext` string inside an **`onclick` attribute** on `templates/ads/dashboard.html`, which is why `test_no_hardcoded_js_strings` does not scan it. Keep it in the attribute, **not** in a `<script>` block. The `ru`/`bs` translations must avoid a raw apostrophe.
- `test_consent.py::test_withdraw_button_renders_on_dashboard` pins `action="/consent/withdraw/"` and the ru label **"Удалить данные"** - the **button label must not change**.

---

**Tests required**

1. A ticket whose `User` row is **hard-deleted** is deleted with it, **and** a ticket for a **different** user is untouched. The second half is what stops an over-broad filter from shipping.
2. After **`withdraw_consent()`** the ticket is gone while the **`User` row still exists** - the proof that `CASCADE` did **not** do the work.
3. A **rollback** inside `withdraw_consent` (monkeypatched `soft_delete_user_ads`) restores the ticket too - extend `test_withdraw_is_atomic_rollback`'s assertion list.
4. An **unregistered `chat_id`** produces **no** ticket and exactly **one** notice naming the consent requirement.
5. A **registered user with `consent_given_at`** gets a ticket.
6. A **registered user without it** does not.
7. A **deactivated user with consent** still completes one; a **deactivated user without consent** is refused with the notice.
8. The **withdraw confirm string names support requests**.
9. The **four** inventory entries are `DELETE_ROW`.
10. `db-schema.md` no longer calls the table a **"read-only audit trail"**.
11. **Deleting a ticket changes no other row** - no `AnalyticsEvent`, no `DailyAdMetrics`, nothing.
12. `test_sweep_consent.py::test_lock_id_is_consent_hard_delete` still asserts `== 3`.
13. `test_sweep_consent.py::test_crash_between_updates_and_delete_rolls_back` still passes - the new sweeps are inside `transaction.atomic()`.
14. **No SQL diff is asserted** - `sqlmigrate` is empty for this `AlterField` (constraint 7). A Validator reading an empty `sqlmigrate` must **not** call the block wrong.
15. `test_support_models.py::TestSupportTicketAnonymous` still passes - the model keeps accepting `user=None`.

**Tests to run (every path verified to exist)**

```
src/backend/apps/core/tests/test_support_models.py
src/backend/apps/core/tests/test_support_admin.py
src/backend/apps/core/tests/test_sweep_consent.py
src/backend/apps/users/tests/test_deletion.py
src/backend/apps/users/tests/test_consent.py
src/backend/apps/users/tests/test_pii_inventory.py
src/backend/apps/ads/tests/test_i18n_completeness.py
src/telegram_bot/tests/test_support.py
src/telegram_bot/tests/test_bot_deactivation_matrix.py
src/telegram_bot/tests/test_support_delivery_email.py
src/telegram_bot/tests/test_support_delivery_telegram.py
```

`test_pii_inventory.py` lives in **`apps/users/tests/`**, not `apps/core/tests/`.

---

**Risk and rollback**

| # | Risk | Sev | Mitigation |
|---|---|---|---|
| 1 | `contact_us` becomes registration-gated - an unregistered buyer can no longer reach the desk | **High** | Fork 1 is owner-mandated; the notice names the remedy (sign in / accept consent). A web form is a **separate** block, not a silent regression here |
| 2 | A deactivated user who never consented loses the restoration channel | Med | Fork 2 is owner-mandated; the carve-out still works for anyone who consented. Both halves are pinned |
| 3 | The `AlterField` looks like a no-op in a SQL diff | Med | Constraint 7 - acceptance is behavioural |
| 4 | Irreversible row destruction removes support's correlation key | Med | The owner's trade; `ticket_ref` reuse documented (Fork 3). `RunPython` never deletes (constraint 10) |
| 5 | `<next>` migration number is taken | Med | Constraint 13 - read the directory immediately before generating; never renumber |
| 6 | BLOCK 10 / BLOCK 11 land first and shift `withdraw_consent` | Med | Constraint 11 - re-read immediately before editing |
| 7 | `pii_inventory.py` and its test are contended (BLOCK 14 landed) | Med | Re-read immediately before editing; append/replace **only** the four entries and **one** test |
| 8 | `VAL-010` contention artefacts (`ForeignKeyViolation` cascade, `FATAL: database "test_mko_bazuna" does not exist`, `DuplicateDatabase`, `ObjectInUse`, foreign-PID `DeadlockDetected`, `assert not self._finalizers` cascade) | Med | **Contention, not a defect** - re-run serially |

**Rollback:** the **code** reverts cleanly. The **data does not come back** - that is inherent to the owner's decision, not to this block's implementation.

**Cross-phase:** `consent_records` (BLOCK 3) declares the same shape for a different table; keep the two inventories' wording consistent. `LoginToken` has no `User` FK, so its existing `DELETE_ROW` entry is unrelated to this block. (section 5.3)
---

### BLOCK 14 — `SearchHistory.query_normalized` keeps un-redacted PII (06-PII-108)

| | |
|---|---|
| **Findings owned** | `06-PII-108` (substantive half) |
| **Depends on** | **BLOCK 9** (the withdrawal teardown bounds what is retained). **Q-D5 is RESOLVED** (§0.6.1) — no Researcher gate remains |
| **Blocks** | nothing |
| **Priority** | P1 |
| **Risk level** | **MEDIUM** — it changes a stored value and a dedup key, it rewrites historical keys irreversibly, and the anonymous session store has the same split |
| **Required agents** | **Auditor · Planner · Validator.** The Researcher gate is **discharged** by §0.6.1. A Validator task **is** required, for one reason only: this block ships an irreversible data migration |

**The defect, re-verified against the tree (2026-10-02) — four writers, all wrong the same way.**

| # | Writer | Derivation today |
|---|---|---|
| 1 | `record_search_history` (`search_history.py`) → `SearchHistory.query_normalized` | `query.strip().lower()` |
| 2 | `record_search_history` → `_record_session_history(session, normalized, redacted)` — the **anonymous** store, `_SESSION_KEY = "search_history"` | the same `normalized`, passed straight through |
| 3 | `increment_popular_search` (`popular_search.py`) → `PopularSearch.query_normalized` — the **global, cross-user** table | `query.strip().lower()` |
| 4 | `SeedService._seed_popular_searches` (`seed_service.py`) → two `update_or_create` sites | `item["query"].strip().lower()` and `word.lower()` |

All four derive the key **before** `redact_search_query`, so phones, e-mail addresses
and personal names that the `query` column deliberately strips survive verbatim as the
dedup key — in the table, in the session, and globally. The report's original claim that
the *full query text* is stored is imprecise: `query` **is** redacted. What is true,
and what the auditor missed, is that `query_normalized` keeps the raw, lower-cased,
un-redacted query. `SearchHistory.user` is `CASCADE`; BLOCK 9 deletes these rows on
withdrawal.

**Writer 2 makes a partial fix meaningless** — the same request would carry the same PII
in the session and out of it. **Writer 3 is the sharpest half**: `popular_searches` has no
`user` FK, no `CASCADE` and no sweep, so BLOCK 9's withdrawal deletion does not bound it,
and without writer 3 the global table keeps every phone number and e-mail address any user
has ever typed, indefinitely. **Writer 4** is how a future reader concludes the derivation
is already handled.

**The documentation half is de-scoped.** Both public surfaces **already** scope "Analytics"
to Plausible: the `components/consent_banner.html` bullet reads *"Analytics — anonymized
traffic analytics via Plausible"*, and `privacy.html` §2 reads *"Traffic analytics via
Plausible (anonymized) — legal basis: your consent (analytics category)"* with a
`consent_analytics` cookie-table row and a third-party list entry. The naming collision
survives only in three internal names. Correcting correct copy has no audience (§6.1).

**Decision — Q-D5: RESOLVED 2026-10-01. Redact-for-the-key, one mechanism, all three stores.**
See §0.6.1. A new `search_query_key(query)` in `apps/core/utils/sanitize.py` computes

```python
redact_search_query(query).strip().lower()
```

— **redact first, then lower, on the RAW query.**

- **This plan's original option (a) was wrong as written** (§0.6.3 #4). Applying
  `redact_search_query` to the already-lowercased string matches nothing in
  `_NAME_PATTERN` (`\b[А-ЯЁA-Z]`), so **personal names — the largest of the three PII
  classes — survive verbatim in the key.** Redaction must see the original capitalisation.
- **The keyed digest is rejected, not merely deprioritised.** `get_popular_suggestions`
  reads `PopularSearch.query_normalized__startswith=prefix`. A digest has no prefix
  structure, so popular autocomplete would return **zero rows for every query** — the
  feature dies, it does not degrade. A digest would also re-introduce a secret whose
  rotation orphans every stored key and every session payload at once.
- **Splitting mechanisms per store is rejected**: two derivations, one needing a secret,
  for zero privacy gain, against a prefix read that makes redact-as-key the only
  coherent option.
- **The rotation risk is retired, not mitigated.** No secret, nothing to rotate. §7's
  BLOCK 14 "dedup-key rotation orphans every stored key and session payload" row is
  discharged by this decision.

**`__startswith` compatibility — the constraint the decision rests on.** After the change
`get_popular_suggestions` keeps matching `query_normalized__startswith=prefix.strip().lower()`
unchanged, and it still returns rows, because:

1. **The key stays a prefix-stable string over the same characters.** Every mask is
   length-preserving by construction — `_mask_email` keeps two characters of the local
   part plus asterisks of the remaining length, `_mask_phone` and `_mask_name` likewise —
   so no mask introduces, removes or reorders a character.
2. **Lowercasing runs *after* redaction**, so the key's character span is identical to
   today's and `startswith` semantics are unchanged.
3. **Every PII-free query is byte-identical**, so every existing autocomplete lookup is
   unaffected. Verified against the whole corpus: the five seeded config queries
   (`айфон`, `автомобиль`, `квартира`, `диван`, `велосипед`, from
   `apps/seed/config/seed.default.json`) and every value `test_autocomplete.py` uses
   (`тест`, `транспорт`, `телефоны`, `велосипед`, `веревка`, `вертолет`, `автомобиль`,
   `первый`, `второй`, `третий`, `Велосипед`, `query{i}`) map to identical keys.
   **`test_autocomplete.py` therefore needs no edit at all** (§0.6.3 #5) — it would break
   only under a digest, which is an argument *against* the digest.
4. **A PII-bearing query now matches on its masked text**, which is the intent: a
   phone-number query stops offering another user's phone number as a suggestion.

**File surface (semantic units) — four writers, one helper, one migration**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/core/utils/sanitize.py` | **new** `search_query_key(query: str) -> str` | The single derivation, beside `redact_search_query`. All three caller modules **already import this module**, so no new import edge |
| `src/backend/apps/search/services/search_history.py` | `record_search_history`, `_record_session_history`, `_MAX_HISTORY`, `_SESSION_KEY` | **Both stores are in one module** — that is the module's single-responsibility boundary and it must be respected |
| `src/backend/apps/search/services/popular_search.py` | `increment_popular_search` | The **global cross-user** table (writer 3, §0.6.3 #3) |
| `src/backend/apps/seed/services/seed_service.py` | `SeedService._seed_popular_searches` | Writer 4. **Three** sites: both `update_or_create` calls **and** the `existing` set comprehension that keeps the ad-title pass from re-upserting a config query — miss it and a re-seed double-writes |
| `src/backend/apps/search/migrations/0005_*.py` | **new** `RunPython` data migration | The leaf is `0004_backfill_delivered_at`; the next number is `0005`. See the backfill decision below |
| `src/backend/apps/search/tests/test_redact_search_query.py` | the **four** assertions named below | Rewritten under project rule 2. The helper's own unit matrix is **unchanged** and must keep passing untouched |
| `src/backend/apps/search/tests/` | a new module for the key, the four writers, the session store and the migration | Do not bloat `test_redact_search_query.py` |
| `src/backend/apps/seed/tests/test_seed.py` | one new assertion for writer 4 | Writer 4 has **no test at all** today — that absence is how it was missed |
| `docs/01-spec/technical-specification.md` | **no edit — decided** | §5.3's reservation is held but left unexercised (binding constraint 7) |

**The migration precedent to mirror — do not invent one.** `search/migrations/0002_redact_search_queries.py::redact_queries`
already did this kind of work and left three decisions on the table:

- it **inlines** the redaction — its own docstring says *"so the migration stays robust if
  the application module changes in the future"* — rather than importing
  `apps.core.utils.sanitize`;
- it rewrites **`query` only**, and **explicitly preserves `query_normalized`** as the
  meaningful key. `0005` inverts exactly that property;
- it uses `reverse_code=migrations.RunPython.noop`, so the unredacted originals are
  intentionally not retained and the operation is irreversible.

**Backfill decision — a migration SHIPS.** This supersedes §6.2's "a backfill is a
separate decision" text, which §0.6.3 #6 calls wrong. The raw lower-cased text exists
**nowhere else**, so rewriting historical keys is **destruction, not a backfill** — which
is an argument for shipping, not against it, because leaving it keeps the finding live:

- **`popular_searches` has no retention bound at all.** No `user` FK, no `CASCADE`, no
  sweep. Without a migration, every phone number and e-mail address ever typed into the
  search box survives **in the clear, globally, forever**.
- **`search_history` is bounded only by the user's own withdrawal** (BLOCK 9 deletes those
  rows; before BLOCK 9 they are `CASCADE`-only). A user who never withdraws keeps their
  PII indefinitely.

So `search/0005_*` re-derives `query_normalized` for **both** tables from each row's own
`query` column. That is sound precisely because **redaction is idempotent** —
`redact_search_query(redact_search_query(q)) == redact_search_query(q)` — so re-deriving
from the stored, already-redacted value yields exactly the key the write path will
produce. Verified over the `test_redact_search_query.py` matrix plus 200-character and
mask-edge inputs; **the implementor must pin that idempotence with a test**, because the
whole migration rests on it. Truncation agrees as well: the view caps input at
`MAX_SEARCH_QUERY_LENGTH = 200`, `redact_search_query` truncates to
`_MAX_QUERY_LENGTH = 100`, so both paths key on the same 100 characters.

- **`popular_searches`: `query_normalized` is NOT unique** (`db_index=True`, no
  `unique=True`). Two differently-formatted PII-bearing queries collapse onto one key, so a
  naive `UPDATE` would create **duplicate keys** — and `increment_popular_search`'s
  `get_or_create` would then raise `MultipleObjectsReturned` on `/search/`. The migration
  **groups by the new key, keeps one row and `Sum`s `hit_count`** across the group.
  - **The `hit_count` cost, stated plainly.** The *total* is preserved, and for a
    collapsed group it is better than before: the merged row keeps a high count and so
    stays above `_MIN_HIT_COUNT = 10`, meaning the autocomplete entry **survives**
    redaction instead of dropping out of suggestions. What is lost is the split of hits
    **between the two variants** — precisely the split the write path now discards going
    forward. Rows whose key does not change (every benign row, the overwhelming majority)
    are not touched and keep their counts exactly.
- **`search_history`: no `hit_count` to lose.** Dedup is delete-then-create by
  `(user_id, query_normalized)`, and re-derivation can collapse two of one user's rows
  onto one key, so the migration **deletes all but the newest row per `(user_id, new
  key)`** — matching the display order of `get_user_search_history` (`-created_at`).
- **Residue after the migration: none**, in either table. No third table stores this text
  (`SavedSearch.query` is a different column in a different model).
- **Cost accepted:** irreversible (`reverse_code=noop`, as in `0002`), and a `--create-db`
  fresh-schema run becomes **mandatory** (§1.1).
- **Rejected, and stated rather than deferred:** shipping no migration. Skipping it is one
  line of code and it is the whole difference between a real fix and a forward-looking one.

**Binding constraints**

1. **All four writers or none.** Moving only the table leaves the session store, the global
   popular table or the seeder writing raw PII keys — writers 3 and 4 are how the defect
   survives a partial fix.
2. **Redact, then lower.** Never `redact_search_query(query.strip().lower())` (§0.6.3 #4).
   The helper never lengthens and neither does `.strip().lower()`, so the
   `max_length=200` caps on `SearchHistory.query_normalized` and
   `PopularSearch.query_normalized` stay safe — and the new key is in fact bounded at 100
   by `redact_search_query`.
3. **`SavedSearch.query` is OUT OF SCOPE and must not be touched.** It is the FTS query
   string, stored in the user's language and matched against the per-language search
   vector; redacting it changes what the search *means*. `pii_inventory.py` already
   declares it `ErasureAction.RETAIN` with a reason naming BLOCK 14. Adding a write-time
   rule to that inventory would be a category error — the same one BLOCK 16's entry records.
4. **The migration inlines its redaction** and uses `reverse_code=noop`, exactly as
   `0002_redact_search_queries` does. It must **not** import `sanitize`.
5. **The migration must merge, never duplicate.** Group-and-sum on `popular_searches`;
   keep-the-newest on `search_history`.
6. Do **not** change consent **enforcement** behaviour. The spec sanctions first-party
   `AnalyticsEvent` rows under legitimate interest; there is no violated gate and none is
   introduced here. `CookieCategory.ANALYTICS`, the `consent_analytics` cookie and the
   `consent_analytics` context key are untouched (documentation half de-scoped, §6.1).
7. **`technical-specification.md` needs no edit — decided, not conditional.** Its only
   `SearchHistory` line describes "per-user search query tracking with deduplication and
   50-entry cap … both authenticated and anonymous users", all still true, and the spec
   carries **no** retention or redaction statement for this table. Phase 06 holds the §5.3
   reservation; BLOCK 14 leaves it unexercised, so BLOCKS 4 and 11 meet no conflict here.
8. `SearchHistory.user` remains `CASCADE`. BLOCK 9's explicit deletion on withdrawal is
   the retention bound; this block is the *write* path **and** the one-time destruction of
   the keys written before it.

**Implementor task**

```yaml
id: task_06_b14_search_query_key
title: "Derive the search key from the redacted query, in all four writers (06-PII-108)"
priority: medium
depends_on: [task_06_b09_withdraw_teardown]
source_reference: ".ai/plans/06-pii-consent-remediation.md"
source_section: "BLOCK 14 - SearchHistory.query_normalized"
source_blocks: ["BLOCK 14"]
description: >
  Four writers derive the SearchHistory / PopularSearch dedup key as `query.strip().lower()`
  from the RAW query, so phone numbers, e-mail addresses and personal names that
  `redact_search_query` strips out of the `query` column survive verbatim in
  `query_normalized` - in the SearchHistory table, in the anonymous session store, in the
  global cross-user popular_searches table and in the seeder. Q-D5 is RESOLVED (§0.6.1):
  add one `search_query_key()` helper computing
  `redact_search_query(query).strip().lower()` - redact FIRST, then lower, on the raw query -
  adopt it in all four writers, and ship a `search/0005_*` data migration that re-derives
  the historical keys.
goals:
  - "no phone number, e-mail address or personal name survives in query_normalized, in the database or in the session"
  - "one derivation, shared by all four writers"
  - "popular autocomplete keeps working through the query_normalized__startswith read"
  - "no historical key keeps raw PII after the migration"
files:
  - path: "src/backend/apps/core/utils/sanitize.py"
    targets:
      - type: function
        name: search_query_key
    semantic_anchors:
      insert_after:
        type: function
        value: redact_search_query
  - path: "src/backend/apps/search/services/search_history.py"
    targets:
      - type: function
        name: record_search_history
      - type: function
        name: _record_session_history
    semantic_anchors:
      insert_after:
        type: function_call
        value: redact_search_query
  - path: "src/backend/apps/search/services/popular_search.py"
    targets:
      - type: function
        name: increment_popular_search
    semantic_anchors:
      insert_after:
        type: function_call
        value: redact_search_query
  - path: "src/backend/apps/seed/services/seed_service.py"
    targets:
      - type: method
        name: SeedService._seed_popular_searches
    semantic_anchors:
      insert_after:
        type: method
        value: SeedService._seed_popular_searches
  - path: "src/backend/apps/search/migrations/0005_redact_search_query_keys.py"
    targets:
      - type: class
        name: Migration
    semantic_anchors:
      insert_before:
        type: class
        value: Migration
  - path: "src/backend/apps/search/tests/test_redact_search_query.py"
    targets:
      - type: class
        name: TestIncrementPopularSearchRedaction
      - type: class
        name: TestRecordSearchHistoryRedaction
    semantic_anchors:
      insert_after:
        type: class
        value: TestIncrementPopularSearchRedaction
  - path: "src/backend/apps/search/tests/test_search_query_key.py"
    targets:
      - type: module
        name: test_search_query_key
  - path: "src/backend/apps/seed/tests/test_seed.py"
    targets:
      - type: module
        name: test_seed
changes:
  - action: add_code
    description: >
      Add `search_query_key()` as the single key derivation, beside `redact_search_query`.
    code_hint: |
      def search_query_key(query: str) -> str:
          """Derive the persisted dedup key for a search query.

          Redaction runs FIRST, on the raw query, then strip and lower. The order is
          load-bearing: ``redact_search_query`` matches personal names on
          ``\\b[\u0410-\u042f\u0401A-Z]``, which matches nothing in an already-lowercased
          string, so lower-then-redact would leave every name in the key. The result keeps
          the prefix structure ``get_popular_suggestions`` reads with
          ``query_normalized__startswith``, and never lengthens the input.
          """
          return redact_search_query(query).strip().lower()
  - action: modify_code
    description: >
      All four writers derive their key through `search_query_key`, including the
      `_record_session_history(session, key, redacted)` call site and the seeder's
      `existing` set comprehension.
    code_hint: |
      # search_history.py - one derivation, both stores. The empty guard stays equivalent:
      # search_query_key is empty exactly when query.strip().lower() was empty.
      key = search_query_key(query)
      if not key:
          return
      redacted = redact_search_query(query)
      ...
              _record_session_history(session, key, redacted)
      ...
      SearchHistory.objects.filter(user_id=user_id, query_normalized=key).delete()
      SearchHistory.objects.create(user_id=user_id, query=redacted, query_normalized=key)

      # popular_search.py - the global cross-user table
      key = search_query_key(query)
      if not key:
          return
      redacted = redact_search_query(query)

      # seed_service.py - BOTH update_or_create sites AND the dedup set
      existing: set[str] = {search_query_key(item["query"]) for item in config_searches}
      PopularSearch.objects.update_or_create(
          query_normalized=search_query_key(item["query"]), ...
      )
      PopularSearch.objects.update_or_create(
          query_normalized=search_query_key(word), ...
      )
  - action: add_code
    description: >
      Add `search/0005_*`, a `RunPython` data migration mirroring
      `0002_redact_search_queries.py::redact_queries`: inline the redaction (no `sanitize`
      import), `reverse_code=migrations.RunPython.noop`, and
      `dependencies = [("search", "0004_backfill_delivered_at")]`. Re-derive
      `query_normalized` from each row's own `query` column for both tables. Group
      `popular_searches` by the new key, keep one row and `Sum` `hit_count`; keep only
      the newest row per `(user_id, new key)` in `search_history`.
    code_hint: |
      # Group-and-sum, never a naive UPDATE: query_normalized is not unique, and
      # increment_popular_search's get_or_create would raise MultipleObjectsReturned on
      # duplicate keys.
  - action: modify_test
    description: >
      Rewrite the four assertions in `test_redact_search_query.py` that pin the raw
      lower-cased key, under project rule 2. The helper's own unit matrix
      (`TestRedactSearchQuery`) is untouched and must keep passing.
    code_hint: |
      # Rule 2 - production code is king. Each rewrite looks the row up by
      # search_query_key(raw) instead of raw.lower(), because the key is now derived from
      # the redacted query. The intent of each test is unchanged; only the pinned literal
      # was wrong.
acceptance_criteria:
  - "the derivation is redact-then-lower on the RAW query: search_query_key(q) == redact_search_query(q).strip().lower(), and NO call site computes query.strip().lower() first"
  - "all four writers call search_query_key - record_search_history (table), the _record_session_history call site, increment_popular_search, and SeedService._seed_popular_searches (both update_or_create sites plus the existing-set comprehension)"
  - "a SearchHistory row written from a query containing a phone number, an e-mail address and a multi-word personal name contains NONE of the three in ANY column"
  - "the anonymous session store carries the same guarantee: session['search_history'][0]['query_normalized'] contains none of the three"
  - "increment_popular_search leaves no phone, e-mail or name in PopularSearch.query_normalized"
  - "benign queries are byte-identical under the new derivation: dedup merges what it merged and does not merge what it did not, _MAX_HISTORY pruning still caps at 50, and test_autocomplete.py passes with NO edit"
  - "get_popular_suggestions still returns rows via query_normalized__startswith after the change"
  - "redaction idempotence is pinned by a test: redact_search_query(redact_search_query(q)).strip().lower() == search_query_key(q) over the test_redact_search_query.py matrix plus a 200-character query"
  - "the four named assertions in test_redact_search_query.py are rewritten, each with the rule-2 justification recorded in the commit body"
  - "SavedSearch.query is untouched and NO entry is added to apps/users/services/pii_inventory.py"
  - "search/0005_* inlines its redaction, does not import sanitize, uses reverse_code=migrations.RunPython.noop, and depends on 0004_backfill_delivered_at"
  - "the migration merges colliding popular_searches keys (one surviving row, hit_count summed) so no duplicate query_normalized remains and increment_popular_search cannot raise MultipleObjectsReturned"
  - "the migration keeps only the newest row per (user_id, new key) in search_history"
  - "after the migration, no query_normalized in either table contains a phone number, an e-mail address or a personal name"
  - "consent enforcement is unchanged; CookieCategory.ANALYTICS, the consent_analytics cookie and the consent_analytics context key are untouched"
  - "docs/01-spec/technical-specification.md is not edited"
  - "no test asserts on a line number, a private name, a template-string substring or a count produced by introspection (§1.5)"
tests_required:
  - "the leak is closed in the table: phone + e-mail + name in one query, none survives in any column"
  - "the leak is closed in the session store - the same guarantee, and the reason the block exists"
  - "the leak is closed in the GLOBAL popular_searches table via increment_popular_search"
  - "the seeder writes the redacted key (writer 4 has no test today)"
  - "benign queries unchanged end to end: dedup and the 50-entry prune behave exactly as before"
  - "popular autocomplete still resolves through query_normalized__startswith"
  - "redaction idempotence, which the whole migration rests on"
  - "the migration: colliding popular_searches keys merge with hit_count summed, no duplicate query_normalized remains, and no raw PII survives in either table"
tests_to_run:
  - "src/backend/apps/search/tests/test_redact_search_query.py"
  - "src/backend/apps/search/tests/test_autocomplete.py"
  - "src/backend/apps/search/tests/"
  - "src/backend/apps/cabinet/tests/test_cabinet_sections.py"
  - "src/backend/apps/seed/tests/test_seed.py"
  - "src/backend/config/settings/tests/test_session_policy.py"
commands:
  - "$dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'"
  - "$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS=\"src/backend/apps/search/tests --tb=short\" test"
  - "$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS=\"src/backend/apps/cabinet/tests/test_cabinet_sections.py src/backend/apps/seed/tests/test_seed.py src/backend/config/settings/tests/test_session_policy.py --tb=short\" test"
  - "$dc run --rm --env PYTEST_OPTS=\"--create-db --tb=short -n auto --maxprocesses=4 --dist loadgroup\" test"
  - "$dc run --rm test"
  - "uv run ruff check src/backend/apps/core/utils/sanitize.py src/backend/apps/search/services/"
  - "uv run basedpyright src/backend/apps/core/utils/sanitize.py"
commit:
  message: "fix(search): derive the search key from the redacted query (06-PII-108)"
  stage_explicitly: true
  body: |
    Four writers (record_search_history table + session store, increment_popular_search,
    SeedService._seed_popular_searches) derived the dedup key as query.strip().lower()
    from the raw query, so phones, emails and personal names that redact_search_query
    strips from `query` survived verbatim in `query_normalized`.

    Q-D5 resolved (plan §0.6.1): one `search_query_key()` helper, redact-then-lower on the
    RAW query. Redaction must run first - `_NAME_PATTERN` matches on an uppercase first
    letter and would match nothing on an already-lowercased string, so the plan's
    original option (a) left every personal name in the key. A keyed digest was rejected
    because `get_popular_suggestions` reads `query_normalized__startswith`: a digest has no
    prefix structure and would return zero rows for every query. No secret is introduced
    and nothing needs rotating.

    Tests changed (project rule 2 - production code is king). Four assertions in
    test_redact_search_query.py pinned the raw lower-cased key and cannot pass unchanged;
    each looks its row up by the old key literal:
      - TestIncrementPopularSearchRedaction::test_stores_redacted_query
        (PopularSearch.objects.get(query_normalized=raw.lower()))
      - TestIncrementPopularSearchRedaction::test_updates_redacted_query_on_increment
        (PopularSearch.objects.get(query_normalized=raw.lower()))
      - TestRecordSearchHistoryRedaction::test_stores_redacted_query_db
        (SearchHistory.objects.get(..., query_normalized=raw.lower()))
      - TestRecordSearchHistoryRedaction::test_stores_redacted_query_session
        (session["search_history"][0]["query_normalized"] == the un-redacted lower-cased
        Cyrillic personal name as the session key)
    Each now derives the expected key with search_query_key(). The tests' intent is
    unchanged; only the pinned literal was wrong.
    test_autocomplete.py needs NO edit: its values are all PII-free, for which the new
    derivation is the identity.

    Data migration search/0005_* re-derives query_normalized for both tables from each
    row's own `query` column, which is exact because redact_search_query is idempotent.
    popular_searches keys are merged group-by-key with hit_count summed: query_normalized
    is not unique, and a naive UPDATE would make increment_popular_search's get_or_create
    raise MultipleObjectsReturned. search_history keeps only the newest row per
    (user_id, new key). reverse_code is noop - the un-redacted originals are the PII being
    removed and are intentionally not retained, mirroring 0002_redact_search_queries.
    Irreversible, like its precedent.
extra_context: |
  THE REQUIRED BEHAVIOURAL PROPERTY (plan §1.5): a SearchHistory row written by a search
  containing a phone number and an e-mail address contains NEITHER in any column, in the
  database AND in the session store.

  BINDING CONSTRAINTS (verbatim from BLOCK 14):
  1. All four writers or none. Moving only the table leaves the session store, the global
     popular table or the seeder writing raw PII keys - writers 3 and 4 are how the defect
     survives a partial fix.
  2. Redact, then lower. Never redact_search_query(query.strip().lower()). The helper
     never lengthens and neither does .strip().lower(), so the max_length=200 caps on
     SearchHistory.query_normalized and PopularSearch.query_normalized stay safe - and the
     new key is in fact bounded at 100 by redact_search_query.
  3. SavedSearch.query is OUT OF SCOPE and must not be touched. It is the FTS query
     string, stored in the user's language and matched against the per-language search
     vector; redacting it changes what the search means. pii_inventory.py already declares
     it ErasureAction.RETAIN with a reason naming BLOCK 14. Adding a write-time rule to
     that inventory would be a category error.
  4. The migration inlines its redaction and uses reverse_code=noop, exactly as
     0002_redact_search_queries does. It must NOT import sanitize.
  5. The migration must merge, never duplicate. Group-and-sum on popular_searches;
     keep-the-newest on search_history.
  6. Do NOT change consent enforcement behaviour. CookieCategory.ANALYTICS, the
     consent_analytics cookie and the consent_analytics context key are untouched.
  7. technical-specification.md needs no edit - its only SearchHistory line (dedup,
     50-entry cap, authenticated + anonymous) is still true and it carries no retention
     or redaction statement for this table.
  8. SearchHistory.user remains CASCADE. BLOCK 9's explicit deletion on withdrawal is the
     retention bound; this block is the write path AND the one-time destruction of the
     keys written before it.

  MIGRATION PRECEDENT to mirror, not reinvent:
  src/backend/apps/search/migrations/0002_redact_search_queries.py::redact_queries - it
  inlines the redaction ("so the migration stays robust"), rewrites `query` only,
  EXPLICITLY preserves query_normalized, and uses reverse_code=migrations.RunPython.noop.
  The search app's leaf is 0004_backfill_delivered_at, so the new number is 0005.

  COMMAND CONTRACT (§1.1, Windows 11 / PowerShell 7):
  - Tests are Docker-only. `uv run pytest` on the host always fails (no PostgreSQL on
    localhost:5432). Never use --override-ini=addopts= - it strips
    --import-mode=importlib.
  - Setting PYTEST_OPTS REPLACES the defaults
    (--reuse-db --tb=short --durations=10 -n auto --maxprocesses=4 --dist loadgroup),
    so a targeted run loses xdist parallelism and DB reuse. Values are word-split on
    spaces, so do not pass quoted multi-token values.
  - A migration lands in this block, so the --create-db fresh-schema run is MANDATORY.
  - The seeder is touched, so the full suite (including the nightly seed marker) must pass.

  VAL-010: concurrent validators share one `test_mko_bazuna`. A red gate captured while
  another agent is running is a teardown race, not a defect. Re-run SERIALLY before
  reporting. Artefacts to re-run rather than trust: ForeignKeyViolation cascade,
  'FATAL: database "test_mko_bazuna" does not exist', and 'assert not self._finalizers'.

  STANDING RULES (§1.4): English only; no print() (use logging); no Pydantic DTOs in the
  view/service path; StrEnum for constants; all schema changes via migrations, never
  renumber an existing one; docs/02-database/db-schema.md is mirrored only for SCHEMA
  changes (this block adds none); never git add -A or git add . - stage specific files.
```

**Tests required**

1. **The leak is closed, in the table** — a search containing a phone number, an e-mail
   address and a multi-word capitalised name produces a `SearchHistory` row in which
   **none** of the three survives in **any** column.
2. **The leak is closed, in the session** — the same search through the anonymous path
   produces a session payload with the same guarantee. **This half is the reason the block
   exists; a test that covers only the table is incomplete.**
3. **The leak is closed, in the global table** — the same search through
   `increment_popular_search` leaves none of the three in `PopularSearch.query_normalized`.
   This is the half with no retention bound.
4. **The seeder is covered** — writer 4 currently has no test at all, which is how it was
   missed. One assertion is enough.
5. **Deduplication still behaves** — two searches that should merge merge, and two that
   should not do not; `_MAX_HISTORY = 50` pruning still caps the history.
6. **Autocomplete is unaffected** — `get_popular_suggestions` still resolves through
   `query_normalized__startswith`, and benign queries are byte-identical.
7. **Idempotence** — `redact_search_query(redact_search_query(q)).strip().lower()` equals
   `search_query_key(q)` over the existing matrix plus a 200-character query. The
   migration is only correct because this holds.
8. **The migration** — colliding `popular_searches` keys merge with `hit_count` summed, no
   duplicate `query_normalized` survives, and neither table retains raw PII.
9. **Regression** — `TestRedactSearchQuery`'s full unit matrix passes **unchanged**.

**Test blockers — the four assertions that cannot pass unchanged**

Verified by re-running the derivation over every value each test uses. The plan's §0.6.3
#5 said "4 assertions in 4 tests"; that count is **confirmed** (the assignment brief
asserted five — there are four; no fifth site exists in `src/`):

| Test | Pinned today | Becomes |
|---|---|---|
| `TestIncrementPopularSearchRedaction::test_stores_redacted_query` | `PopularSearch.objects.get(query_normalized=raw.lower())` for `"куплю велосипед +79001234567 user@example.com"` | `…get(query_normalized=search_query_key(raw))` |
| `TestIncrementPopularSearchRedaction::test_updates_redacted_query_on_increment` | `PopularSearch.objects.get(query_normalized=raw.lower())` for `"велосипед user@example.com"` | same |
| `TestRecordSearchHistoryRedaction::test_stores_redacted_query_db` | `SearchHistory.objects.get(user=buyer, query_normalized=raw.lower())` for `"Иван Петров +79001234567"` | same |
| `TestRecordSearchHistoryRedaction::test_stores_redacted_query_session` | `assert session["search_history"][0]["query_normalized"] == "иван петров"` — the **un-redacted lower-cased Cyrillic personal name** as the session key | `== search_query_key("Иван Петров")` |

**These four are rewritten under project rule 2** (production code is king). Each test's
*intent* is unchanged and correct; only the pinned literal was wrong. The reason must be
recorded in the commit body. The other two assertions in the file
(`test_benign_query_stored_and_suggestible`, `test_benign_query_unchanged`) use `"велосипед"`,
for which the new derivation is the identity, and pass untouched — as does the whole of
`test_autocomplete.py` and `config/settings/tests/test_session_policy.py`.

**Risk and rollback**

- *Risk:* a dedup regression silently changes "recent searches" for sellers, because two
  differently-formatted PII-bearing queries now share one entry. Accepted by Q-D5 and
  mitigated by tests 5 and 6.
- *Risk:* the migration creates **duplicate** `popular_searches` keys, and
  `get_or_create` then raises `MultipleObjectsReturned` on `/search/`. Mitigated by
  binding constraint 5 (group-and-sum) and test 8.
- *Risk:* the migration is **irreversible**. Accepted, on `0002_redact_search_queries`'s
  own precedent — its docstring states the unredacted originals are the PII being removed
  and are intentionally not retained.
- *Rollback:* the **code** reverts with a straight revert. **The migration does not** —
  once the historical keys are destroyed there is nothing to restore, and a re-deploy of
  the old derivation would simply begin writing raw keys again on top of rows that are now
  clean. Record both facts in the commit body.

---

### BLOCK 15 — `ConsentRecord` retention sweep and changelist exposure (06-PII-116, Q-D4)

| | |
|---|---|
| **Findings owned** | `06-PII-116` **in full** — both halves: the unbounded ledger, **and** `session_key` in the staff changelist — plus the `ConsentRecord.session_key` / `.user_agent` half of `06-PII-110`, which `06-PII-116` absorbed |
| **Does NOT own** | `06-PII-115`. It is **rejected and closed** (§0.3, §2 scope table) and carries no work item. See C-B15-1 — the task brief attributed it to this block |
| **Depends on** | **BLOCK 10** (`06-PII-107`) — the sweep lands after the `ConsentRecord` write moves inside `withdraw_consent`'s transaction — and **Q-D4(b), which is RATIFICATION REQUIRED and not yet given** |
| **Blocks** | nothing |
| **Priority** | P2 |
| **Risk level** | **HIGH** — a destructive command on the Art. 7(1) ledger, an irreversible anonymisation, an `AdvisoryLockId` contended with phase 07 BLOCK 8, and a `DAILY_COMMANDS` entry whose exit code is load-bearing in the durable daily marker |
| **Required agents** | **Auditor · Researcher · Planner · Validator** (all four). The Researcher's legal half is delivered below; it is a **recommendation**, not a ratification |
| **Q-D4** | **(a) technical half RESOLVED 2026-10-03 — `AdvisoryLockId.CONSENT_RECORD_SWEEP = 14`, verified free, two files.** **(b) legal half GATED — the TTL numbers below are RATIFICATION REQUIRED** |

#### Corrections to this block's premise — C-B15-1 … C-B15-6

Each was verified against the tree and against
`.ai/audit/99-validation/06-pii-consent-validated-findings.md` (READ-ONLY) immediately
before this section was written. **Three of them change what the block ships.**

**C-B15-1 — `06-PII-115` is not this block's finding. The task brief misattributed it.**
`06-PII-115` is `create_admin_user` writing the raw `username` to stdout; the Validator
**REJECTED** it (*"the privacy claim is factually wrong… it never prints a seller's
`@handle`"*), §0.3 records it as closed with no remediation, and §2 marks it **"rejected —
no work item"**. The defect the brief describes — *"`ConsentRecord` rows accumulate forever
with no expiry and no cleanup path"* — is **the first half of `06-PII-116`**, verbatim from
that finding's *Problem* statement: *"`ConsentRecord` grows without bound… No purge command
exists in `HOURLY_COMMANDS`."* **BLOCK 15 owns `06-PII-116` whole. It does not own, and
must not claim, `06-PII-115`.**

**C-B15-2 — "nothing implements the 12 months and the re-prompt never fires" is half wrong.
The re-prompt fires.** Two independent mechanisms are live today and neither is missing:
`context_processors.py::consent_state` sets `consent_shown = False` once
`timezone.now() - consent_given_at >= timedelta(days=CONSENT_REPROMPT_DAYS)`
(`CONSENT_REPROMPT_DAYS = 365`), and `views/consent.py::CONSENT_COOKIE_MAX_AGE =
365 * 24 * 60 * 60` expires the cookie browser-side; `test_consent_context.py::TestRePrompt`
pins the server-side half. **What is unimplemented is the one thing that is a defect here:
nothing bounds the stored ledger, and no row is ever removed or anonymised.** The premise
is restated as **"unbounded retention of the consent ledger"**, and the design turns on the
difference — the re-prompt boundary is exactly where the fingerprint fields stop being
necessary (*The consequence of the re-prompt*, below).

**C-B15-3 — the `privacy.html` sentence the brief quotes is already gone.** BLOCK 9
(`474a68d`) rewrote §6 and **removed** *"Consent state is otherwise retained for 12 months,
after which you are re-prompted."* It survives only as a **stale msgid** in the `ru`/`bs`/`en`
`django.po` files. §6 today states the consent log's **purpose and no period at all**. So
this block is not "correct a wrong number" — it **adds** the period, once. The stale msgids
are a `makemessages` artefact; **do not hand-edit them**, and
`test_i18n_completeness.py` is the gate.

**C-B15-4 — the sweep precedents the brief names do not exist.** There is no
`sweep_expired_consents` and no `sweep_purge_rejected` command and no test module of either
name. The real names are **`consent_hard_delete`** (the consent-related sweep, lock 3) and
**`purge_rejected_ads`** (lock 7), tested by `test_sweep_consent.py` and
`test_sweep_purge_rejected.py`. `archive_sweep` (lock 1) is the batching precedent;
`cleanup_login_tokens` is the closest single-transaction analogue (a TTL filter, a dry run,
a count, a delete). **Mirror those; do not go looking for the brief's two names.**

**C-B15-5 — the command belongs in `apps/core/management/commands/`.** This block's old
file surface named `src/backend/apps/users/management/commands/purge_consent_records.py`;
**that directory does not exist** (the `users` app holds `migrations/`, `services/`,
`tests/`, `views/` and nothing else), so the old path means creating a management-command
package with an `__init__.py` for one module. Every existing sweep lives in
`apps/core/management/commands/`, `consent_hard_delete.py` **already** imports
`from apps.users.models import User` so the `core → users` model edge is established rather
than new, and `test_sweep_lock_structure.py::_LOCK_TARGET_MODULES` is written entirely in
`apps.<app>.management.commands.*` dotted form. Rules 5 and 7 point the same way.

**C-B15-6 — the guard test does not need an edit.** A Validator established that
`test_advisory_lock_ids.py` no longer asserts specific integers (its own module docstring:
*"The specific integer values … are no longer asserted directly"*). Re-verified: it asserts
three named members exist (`TEST_SCHEMA_SETUP`, `SWEEP_ORPHANED_MEDIA`, `CATALOG_LOAD`),
that every `AdvisoryLockId.*` reference across `src/` resolves to a member, and that every
member name is an identifier. **Adding `CONSENT_RECORD_SWEEP = 14` costs `enums.py` plus
the `advisory_lock.py` docstring row — nothing else.** §0.6.3 correction 13 already recorded
this; phase 07 BLOCK 8's surface row still claims three files and is **stale on this point**.
The unchanged test must still be **run**, and the commit body records that editing it was
considered and declined.

**Honest severity framing (unchanged).** A `session_key` alone is not a cookie; exploiting
it still requires the cookie value. This is an **exposure-reduction** argument, not a
standalone hijack, and LOW is the validated severity. This block does not raise it: the
irreversible hazard here is on the **erasure** side, not the exposure side.

#### Q-D4 — the technical half is RESOLVED; the legal half is RATIFICATION REQUIRED

**Q-D4(a) — the advisory lock: `AdvisoryLockId.CONSENT_RECORD_SWEEP = 14`. RESOLVED
2026-10-03. Verified in the tree; no coordinator gate remains.**

`apps/core/enums.py` re-read immediately before this section was written: **19 members**,
values `1–9`, `11`, `12`, `13`, `100–104`, `110`, `111`. **The highest allocated integer
below 100 is `13` (`REPAIR_BOT_USERNAME`), so `14` is genuinely free.** The tree agrees
independently: `advisory_lock.py`'s allocation docstring records *"ID 10 is
intentionally unused/reserved… **IDs 14-99 are reserved for future scheduled jobs**"* — a
consent-retention sweep is exactly that. Phase 03's plan is **stale** at "18 members, next
free is 13" (C-3; §0.6.3 correction 14).

**Reusing an existing id is rejected.** The phase-03 reuse precedent
(`ARCHIVE_SWEEP`, `RECOMPUTE_NORMALIZED_PRICES`, `ALERT_DELIVERY_TASK`) exists because those
ids were folded into operations that already owned one. This is a distinct destructive
operation on a distinct table. Two commands sharing an id serialise each other silently and
**nothing in the suite catches it** — phase 07 BLOCK 8 calls that "a human rule, not an
automated one", which is exactly right.

**Cost: two files in one commit.** `apps/core/enums.py` (the member) and
`apps/core/utils/advisory_lock.py` (one row in the transaction-scoped allocation table).
Not three files — see C-B15-6. `AdvisoryLockId.CONSENT_HARD_DELETE == 3` is **not** this
command's lock and must not be renumbered.

**One live collision risk, and it is not theoretical.** **Phase 07 BLOCK 8
(`sweep_media_deletion_errors`) claims `14` as its own allocation and names this block as
its external dependency** — its own text: *"Phase 06 also appends to `HOURLY_COMMANDS` and
also allocates a lock id. Two phases computing 'the next free integer' concurrently is the
single most likely cross-phase collision in this plan set."* Phase 12's Q13 says the same
about itself. **Therefore: re-read `apps/core/enums.py` immediately before editing; if `14`
has been taken, take `15` and record which id was used in the commit body.** The coordinator
is *told* which id was used. That is a reporting obligation, not a permission gate, and it
is the last thing Q-D4(a) owes.

**Q-D4(b) — the TTL. RATIFICATION REQUIRED. BLOCK 15 does not start until the owner sets the
numbers.** Everything under *The legal/privacy question* is the Researcher's
recommendation. **No agent sets a legal period.**

#### The legal/privacy question — Researcher's recommendation. **RATIFICATION REQUIRED**

> **Everything in this subsection is a recommendation to the owner. No agent sets a legal
> period.** The block does not start until the numbers below are ratified. Everything after
> this subsection is technical and needs no ratification.

**The honest starting point: no data protection authority publishes a numeric
consent-evidence retention period for a first-party marketplace consent ledger.** I looked
for one and it is not there. What authorities *do* publish falls into two categories, and
conflating them is the most common error in this area:

| Category | What it is | Examples found |
|---|---|---|
| **Re-ask / consent-refresh intervals** | how often you must ask again | **6 months** (CNIL, cookies), **13 months** (CNIL, exempt audience-measurement cookie lifetime), **6 months** (ICO, cookies), **12 months** (Cal. Civ. Code § 1798.135(d)(4) + 11 CCR § 7026(k)), **"every two years – but you may be able to justify a longer period"** (ICO, general) |
| **Evidence-retention rules** | how long you keep the *proof* | **no number anywhere.** Only a two-part rule (below) |

**Anyone quoting "6 months" or "12 months" as a consent-log retention period is quoting a
re-ask interval.** This project's `CONSENT_REPROMPT_DAYS = 365` is exactly such an interval.
It is **not** evidence of a retention decision, and reusing it as one would be the error.

##### 1. The storage-limitation vs. demonstrability tension, and how EU guidance actually resolves it

**The two obligations, verbatim.** GDPR Art. 5(1)(e) (storage limitation): *"personal data
shall be kept in a form permitting personal data to be identified for no longer than is
necessary for the purposes for which the personal data are processed."* GDPR Art. 7(1):
*"the controller shall be able to demonstrate that the data subject has consented."*
Source: Regulation (EU) 2016/679, EUR-Lex `32016R0679`.

They are in tension only if you insist that "the data" means the whole row forever. They are
**not** in tension if the row is split, because Art. 5(1)(e) says "**in a form permitting
personal data to be identified**" — the limitation attaches to the *identifiable* form, not
to the fact of the record. An anonymised record is not personal data in the GDPR sense, so it
falls outside Art. 5(1)(e) and outside the erasure obligation, while still satisfying
Art. 7(1). **That is the whole resolution, and it is the project's existing policy:**
`db-retention.md` §3 item 4 already records that `AnalyticsEvent.user_id` and
`ModeratorActionLog.user_id` are **SET NULL** during the hard-delete — *"aggregates and audit
trail preserved without PII linkage."* `ConsentRecord` needs the same treatment, and
`ConsentRecord.user` is **already** `on_delete=SET_NULL`, so the shape is established.

**What the DPAs actually say about active vs. ended relationships.** This is the
highest-value finding of the review, and it is a single sentence:

> **EDPB, Guidelines 05/2020 on consent under Regulation 2016/679, v2.1 (adopted 4 May
> 2020), §107:** *"As long as a data processing activity in question lasts, the obligation
> to demonstrate consent exists. After the processing activity ends, proof of consent should
> be kept no longer then strictly necessary for compliance with a legal obligation or for
> the establishment, exercise or defence of legal claims, in accordance with Article 17(3)(b)
> and (e)."* (the "then" is the original's)

The same document, §106, adds the constraint that decides the field split:

> *"the duty to demonstrate [consent] … should not in itself lead to excessive amounts of
> additional data processing … controllers should have enough data to show a link to the
> processing … but they shouldn't be collecting any more information than necessary."*

And §108 confirms session information is legitimate evidence in the first place: *"a
controller could retain information on the session in which consent was expressed."*

The ICO's guidance is the same rule in plain English and adds the operative verb:

> **ICO, "How should we obtain, record and manage consent?":** *"You should keep this
> evidence for as long as you are still processing based on the consent, so that you can
> demonstrate your compliance."*
> **ICO, storage-limitation guidance:** *"If you do not need to identify individuals, you
> should anonymise the data so that identification is no longer possible"* … *"You can keep
> it as long as one of those purposes still applies, but you should not keep data
> indefinitely 'just in case'."*
> **ICO, direct-marketing guidance:** *"If you no longer need the information for your direct
> marketing purposes, you must **delete or anonymise it** (ie so it is no longer in a form
> that allows someone to be identified)."*

**So: while the processing runs, keep the whole record. When the processing stops, keep only
what proves the decision, for as long as a claim is possible.** That is a *conditional*
rule, and it is why this project's answer is a **split** rather than one number.

The CNIL adds a useful operational floor in the same direction (Délibération n° 2020-092 du
9 octobre 2020, *cookies et autres traceurs*): controllers *"doivent être en mesure de
démontrer, à tout moment, que les utilisateurs ont donné leur consentement"* — **at any
moment** — which is the strongest demonstrability formulation in any EU material, and a
direct argument against deleting anything on a bare calendar.

##### 2. The trap specific to this project — stated plainly

**Deleting the consent record makes it impossible to demonstrate that consent *was* given.
That is the exact opposite failure from the one `06-PII-116` reports, and a sweep that
commits it converts an unbounded-retention finding into a *destroyed-evidence* finding.**

Concretely, in this codebase:

- `technical-specification.md` §F is the oracle: *"all accept/decline/withdraw actions are
  inserted as a new row in the `consent_records` table (never updated)."* An append-only
  ledger whose rows can be deleted is no longer a ledger.
- `privacy.html` §6 **already tells the data subject** that the consent log exists *so we
  can demonstrate compliance*. Deleting rows silently contradicts a published promise.
- BLOCK 10 is landing right now and will make `withdraw_consent` write a
  `choice='WITHDRAWN'` row **inside** the withdrawal transaction, specifically so that a
  crash cannot leave a `consent_revoked_at` with no matching audit row. A sweep that deletes
  rows reintroduces exactly that state — this time on a schedule rather than on a crash.
- `Ad.status` / `views_count` / `analytics_enabled` continue to rest on a consent that was
  given. After a deletion there is no artefact of *which* consent authorised *which* ads.

**Therefore: anonymise, never delete.** Not as a compromise — because it is the only action
that satisfies both obligations at once, and because it is what the fields' purpose supports.

##### 3. The consequence of the re-prompt firing — and why it argues for anonymising

**Yes, the old record must survive the re-prompt, and this is the strongest single argument
for anonymisation over deletion.** (Correcting the brief: the re-prompt *does* fire today —
C-B15-2.)

- At `CONSENT_REPROMPT_DAYS`, `consent_state` sets `consent_shown = False`, so the banner
  returns and `consent_analytics` / `consent_preferences` are recomputed from scratch.
- **After** that moment the *previously given* consent is **no longer the operative basis**
  for processing — so under EDPB §107 the "as long as the processing activity lasts" limb has
  **ended** for that record. That is precisely when the fingerprint fields stop being
  necessary, and precisely when they must go.
- **But** the record is not worthless at that moment: it is the evidence for the *interval
  that just ended* — the ads published, the analytics counted, the `ad_visibility='all'`
  decisions made under it. Deleting it there would leave the controller unable to answer a
  claim about the period it was actually processing in.
- Worse in the decline branch: if the re-prompt fires, the user declines, and the sweep has
  deleted the earlier accepted row, the ledger then holds a *declined* record and **no record
  of the accepted one** — the worst evidentiary state, because it looks like the controller
  was processing on a consent it cannot show.

**Anonymisation survives that moment intact; deletion does not.** So the sweep's action is
triggered *by* the re-prompt boundary and its action is *not* deletion.

##### 4. The field split — recommended, and it is what the fields' purposes support

The three fields are not one class, and the tree already says so. `ConsentRecord`'s own
docstring: *"anonymous consent is identified by `session_key` instead of a user account"* —
which makes `session_key` **the sole identifier of an anonymous record**, and
`ip_address` is **already anonymised at write** (`_client_ip_mask` zeroes the IPv4 last octet
and truncates IPv6 to a /64). `pii_inventory.py` independently lists `consent_version`,
`choice` and `categories` in `REVIEWED_NON_IDENTITY_COLUMNS` — the project has **already
declared the decision fields non-identifying**.

| Field | Purpose in the evidence | Action at the **fingerprint TTL** | Action at the **decision TTL** |
|---|---|---|---|
| `user` (FK, `on_delete=SET_NULL`) | the link to the subject | **set NULL** — in the *same statement* as `session_key` | already NULL; row survives |
| `session_key` (`CharField(max_length=40, null=True, blank=True)`) | **the only identifier an anonymous record has** | **set NULL** | already NULL |
| `user_agent` (`TextField(blank=True, max_length=500)`, **not nullable**) | HTTP context; **not** needed for any Art. 7(1) proof — EDPB §106 forbids retaining more than necessary, and the ICO names "session ID" but **not** user-agent as acceptable evidence | **cleared to `""`** (`blank=True`, non-nullable → `CLEAR`, not `NULL`) | already `""` |
| `ip_address` (`GenericIPAddressField(null=True, blank=True)`) | already masked; **not** needed for the proof | **set NULL** | already NULL |
| `choice` | the decision | **retained** | **retained** |
| `categories` | the decision scope | **retained** | **retained** |
| `consent_version` | which banner version was accepted | **retained** | **retained** |
| `consent_given_at` | when (also the sweep's own anchor; in `test_pii_inventory.py::_TIMESTAMP_NAMES`, so the inventory guard skips it) | **retained** | **retained — the row is never deleted** |

**Two stages, two clocks, and they clear `user` and `session_key` together.** The
co-clearing is not a detail: nulling `user` while keeping `session_key` would leave the
**anonymous** record re-identifiable through `django_session`, creating a new live link the
inventory does not declare. That is the one outcome strictly worse than doing nothing, and
the test list pins it.

**The fingerprint TTL has a hard floor: the Django session lifetime.** Nulling
`session_key` on a row whose session is still live destroys evidence a support investigation
can still use. `SESSION_COOKIE_AGE` is declared as **1 209 600 s = 14 days** (phase 16
`B-10`'s recorded decision, `G-10a`). **Any fingerprint TTL below 14 days loses live-session
evidence.** That is a floor derived from the tree, not from guidance.

##### 5. What I would defend — **RATIFICATION REQUIRED**

| # | Item | Value I would defend | Basis |
|---|---|---|---|
| **R1** | **Event-field retention** (`choice`, `categories`, `consent_version`, `consent_given_at`) — the rows are **anonymised, never deleted** | the **event retention period** — **policy-based and justified by purpose**. The implemented literal is `_DECISION_RETENTION_DAYS`; it is **not a deletion boundary**, because the row is never deleted at any age | **RE-GROUNDED 2026-10-04.** Need-based: *retain while there is a necessity to prove consent/withdrawal and the lawfulness of the corresponding processing; after a justified period expires, delete or anonymise.* **The 2026-10-03 figure survives only as an implemented project value. Its statutory-limitation-period justification is WITHDRAWN** — a limitation period governs the window in which a *claim* may be brought; it says nothing about how long a record must be kept, and stating it as the reason for a retention period was the error being undone. **No statute, article, jurisdiction split or confidence rating is asserted here, because none could be supported from this repository.** See §*Retention framing correction (owner ruling 2026-10-04)* |
| **R2** | **Fingerprint-field retention** (`session_key`, `user_agent`, `ip_address`, plus the `user` link) | **90 days** — **unchanged by the 2026-10-04 ruling** | **A project decision, defended on necessity, not on any statutory or limitation-period ground.** These fields are needed only while the session that produced them can still be investigated, and 90 d sits well above the 14-day session floor derived from the tree. No authority is cited for the number and none is implied: an earlier draft rested this row partly on a claim-window comparison, and **that framing is withdrawn** — a claim window is not a retention justification. **The 14-day floor is hard, and so is the R1 ceiling**; 90 d is the value chosen inside that band, and it remains the number most likely to be argued down to 30 d without loss of anything |
| **R3** | Re-ask interval | **unchanged — `CONSENT_REPROMPT_DAYS = 365`** | Out of scope. Do **not** reuse it as a retention number (the trap in the header table above). California's 12-month and the CNIL's 6-month are the same *kind* of number and neither outranks this project's existing value |

**Constraints that bind R1 and R2 regardless of the values chosen — the three-bound form, as
implemented by BLOCK 19:**
`0 < fingerprint TTL ≤ actor TTL ≤ event TTL` (a longer fingerprint TTL than the actor TTL, or an
actor TTL longer than the event TTL, makes a stage a silent no-op), and `fingerprint TTL ≥ 14 days`
(the session-lifetime floor, which applies to the fingerprint bound **only** — the actor is an
account FK, not live-session evidence). The command asserts this ordering itself, **before**
`transaction.atomic()` is entered, so a mis-ordering fails loudly rather than silently skipping a
stage.

**What would move R1 — stated as a project decision, with no statutory anchor:**
- **Shorter**, on a necessity argument: if the owner accepts that proving the consent event needs a
  materially shorter period than the implemented literal. A different applicable instrument could
  also require this — but see the jurisdiction note below, which records that such an instrument can
  only ever force a window **shorter**, never justify a longer one on legal grounds.
- **Longer**, only on a purpose argument the owner accepts in writing. **A limitation period, a
  contract clause or an entity-level rule is not such an argument**, and no such period is asserted
  anywhere in this plan.
- **Either way**, if the owner decides the *rows* should be deleted rather than anonymised,
  R1 becomes a **destruction** decision rather than a **de-identification** one and needs
  its own review. My recommendation is against it (§2 above).

**What would move R2 off 90 days:** a documented support or fraud-investigation workflow
that needs `session_key` / `user_agent` / `ip_address` beyond 90 days — in which case raise
R2 toward R1, but do **not** raise it above R1, and do not raise it by making the fields
permanent. If no such workflow exists (and I found none in the tree), **30 days** is
equally defensible and strictly better for the data subject.

**Jurisdiction — a documented, revisitable assumption. This replaces a citation that could not be
supported.** An earlier draft of this subsection named a specific BiH statute, its gazette reference
and three of its articles as the operative instrument. **All of that is removed.** The citation could
not be verified from this repository, and naming an unverifiable instrument is worse than recording
the gap. The assumption now stands in its place:

- The **launch market** is **Montenegro**; the **data subject** this ledger records consent for is
  in **Bosnia and Herzegovina**. Those are two different questions and the difference changes the
  analysis.
- The applicable law is therefore **not** the GDPR directly, and this project's documentation **does
  not establish** that Montenegrin data-protection law applies.
- Every "GDPR Art. X" citation in this plan — Art. 5(1)(e), Art. 7(1), Art. 21 — is read as
  **descriptive shorthand for the substantive standard** it stands for (storage limitation,
  demonstrability, withdrawal), **not** as a citation of directly applicable EU law. The same reading
  applies to the EDPB and ICO quotations above: they state the standards, they do not bind here.
  **This reading is what the whole retention analysis rests on.**
- **This assumption must be confirmed with the DPO, and is revisitable.** It is recorded as an
  assumption precisely because this pass could not close it. The authoritative statement and its
  dependents are in §*Retention framing correction (owner ruling 2026-10-04)* and in
  `docs/99-agent/pii-consent-remediation-record.md`.
- **What is *not* dependent on it: the retention windows themselves.** They are project decisions
  justified on purpose. A different applicable instrument changes the *legal floor*, not the
  *justification*, and a lower floor could require **shortening** a window — it could never justify
  lengthening one on legal grounds.

**What I could not establish, and am not asserting:** any authority-mandated number for
consent-evidence retention in any jurisdiction; any industry survey giving a median
consent-log retention period (secondary vendor blogs repeat each other and trace back to
ICO/CNIL re-ask intervals, not to retention practice); and any data-protection authority guidance
document on consent-log retention — **no number was found, and no instrument is named as the source
of one.** **This is an ambiguity in the guidance, not a gap that can be closed by choosing a
number.**

##### 6. What the sweep does to BLOCK 3's `RETAIN` entries — **yes, all three change**

| Entry | From | To | The reason string must now say |
|---|---|---|---|
| `users.ConsentRecord.session_key` | `RETAIN` | **`NULL`** | "Implemented by BLOCK 15's `purge_consent_records` (lock 14) at `R2`. Nulled in the **same** `UPDATE` as `user_id`, because an anonymous consent record is identified by `session_key`; clearing one without the other would leave a live re-identification path through `django_session` that this inventory does not declare." |
| `users.ConsentRecord.user_agent` | `RETAIN` | **`CLEAR`** | "Implemented by BLOCK 15's `purge_consent_records` (lock 14) at `R2`. `CLEAR`, not `NULL`: the column is `blank=True` and **not** nullable. Not required for any Art. 7(1) proof — EDPB 05/2020 §106." |
| `users.ConsentRecord.ip_address` | `RETAIN` | **`NULL`** | "Implemented by BLOCK 15's `purge_consent_records` (lock 14) at `R2`. Nullable, already masked at write by `_client_ip_mask`, and not required for the proof." |

- **No entry is added for `user`.** It is relational, the guard
  (`test_pii_inventory.py::test_listed_models_have_no_unreviewed_column`) skips relational
  fields, and BLOCK 3 declared its review surface as *"concrete, non-relational,
  non-timestamp columns"*. Adding one would be a category error. **Say this in the commit
  body so a later editor does not "helpfully" add it.**
- **No entry is needed for `consent_given_at`** — it is in `_TIMESTAMP_NAMES`, so the guard
  skips it.
- **Add no new column.** A `purged_at` / `anonymised_at` stamp would be a new concrete
  non-timestamp column on a listed model and would turn
  `test_listed_models_have_no_unreviewed_column` **red**. **Do not add one.** Operator-visible
  proof that the sweep ran belongs in the log line, not in the row.
- `test_pii_inventory.py::test_retained_free_text_entries_name_their_owning_block` enumerates
  a fixed set that does **not** include `ConsentRecord.user_agent`, so no test edit is forced
  by the action change. All three reasons must still contain `"BLOCK"` — they already do.

**File surface (semantic units)** — corrected against the tree

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/core/management/commands/purge_consent_records.py` | **new** — `Command`, two module constants, `--dry-run` | **Moved from `apps/users/management/` — C-B15-5.** Every existing sweep lives here; `consent_hard_delete.py` already imports `apps.users.models` |
| `src/backend/apps/core/enums.py` | `AdvisoryLockId.CONSENT_RECORD_SWEEP` | New member, value **14** (re-verify; take 15 if taken). **Q-D4(a) RESOLVED** |
| `src/backend/apps/core/utils/advisory_lock.py` | the transaction-scoped allocation table in the module docstring | One row, `session=False`, alongside `consent_hard_delete`'s row |
| `src/backend/apps/core/tests/test_advisory_lock_ids.py` | — | **Deliberately NOT edited.** The test no longer asserts integers (C-B15-6). Run it; record the decision |
| `src/backend/apps/core/utils/scheduler.py` | **`DAILY_COMMANDS`**, not `HOURLY_COMMANDS` | **A third entry in the daily tier** — the tier's rationale is below. `run_scheduler` calls `_validate_commands(HOURLY_COMMANDS + DAILY_COMMANDS)`, so the command **must** be discoverable via `get_commands()` or the scheduler refuses to start |
| `src/backend/apps/core/tests/test_scheduler.py` | `test_daily_commands_include_send_alerts` (exact-`==`) | **Must be edited.** `HOURLY_COMMANDS` is asserted exactly too but is **not** touched by this block |
| `src/backend/apps/core/tests/test_sweep_lock_structure.py` | `SWEEP_COMMANDS`, `EXPECTED_SWEEP_COMMANDS`, `_LOCK_TARGET_MODULES` | Three places, one commit |
| `src/backend/apps/users/migrations/0004_consentrecord_sweep_index.py` | **new** — `AddIndex` on `consent_given_at` | **The sweep filters on an unindexed column.** See *Rollout and the index* below. Check the directory immediately before generating — current head is `0003_logintoken_browser_binding` |
| `src/backend/apps/users/services/pii_inventory.py` | the three `users.ConsentRecord` entries | `RETAIN` → `NULL` / `CLEAR` / `NULL`, with the reasons above |
| `src/backend/apps/users/admin.py` | `ConsentRecordAdmin.list_display` | Drop `session_key`. **Keep** it in `search_fields` and in `readonly_fields` (BLOCK 12's §0.6.3 correction 11). Do not touch the permission predicates (phase 04's file) |
| `src/backend/apps/users/tests/test_purge_consent_records.py` | **new** | The sweep's own suite |
| `src/backend/templates/privacy.html` | §6 — add the period | **BLOCK 15 is §6's third editor** (after BLOCK 9 and phase 04). Re-read immediately before editing; §6 states **one** period. New translatable strings ⇒ `makemessages` + non-empty `ru`/`bs` |
| `docs/02-database/db-retention.md` | the "Other sweeps" table + the "Configuration" sentence | Shared with phase 03 BLOCK 5 (§5.3) — re-read immediately before editing |
| `docs/02-database/db-schema.md` | the `consent_records` index list | §1.4 requires every schema change mirrored |

**Not in this block's surface, deliberately:** `apps/users/services/deletion.py` (BLOCK 9
landed, BLOCK 10 is next), `apps/users/views/consent.py`, `apps/search/**` (BLOCK 14 owns
`SearchHistory.query_normalized`; BLOCK 9 owns `SearchHistory` deletion), any `.po` file by
hand, `apps/users/models.py` (**no new column** — see the inventory note), and
`apps/media/**`.

#### The technical design — decided here, no ratification needed

**Command name and location.** **`purge_consent_records`**, in
`src/backend/apps/core/management/commands/purge_consent_records.py`. C-B15-5 gives the
location argument; the name keeps the `purge_*` verb the "Other sweeps" table in
`db-retention.md` already uses for retention sweeps (`purge_deleted_ads`, `purge_failed_ads`,
`purge_rejected_ads`, `purge_deleted_ads`), so the new row reads as one of them.

**Tier: the existing `DAILY_COMMANDS`, not a new tier and not `HOURLY_COMMANDS`.**
`DAILY_COMMANDS` is `["send_alerts", "rollup_daily_metrics"]` at 08:00 UTC — **the brief's
"already carries `sweep_expired_consents` and `send_alerts`" is wrong on both counts**; there
is no such command (C-B15-4). Justified against the cadence the TTL implies:

- **The TTL is measured in months to years (R1/R2/R1-actor).** Against a multi-year boundary, an
  hourly re-derivation of the eligible set is 24 identical evaluations a day for 24 hours of pure
  work. **No boundary here is a legal deadline**, so nothing turns on a row being purged at 08:00
  today rather than 08:00 tomorrow; the imprecision is bounded by 24 h against a period measured in
  months.
- **The table is small by construction.** `ConsentRecord` grows by consent *actions*, not by
  requests. It is orders of magnitude below `ads`, so the hourly tier's cost model — sized
  for `archive_sweep` over the ads table — does not apply.
- **The daily tier's own precedent.** Phase 07 BLOCK 8 puts its retention command
  (`sweep_media_deletion_errors`) in `DAILY_COMMANDS` and calls out the exact-list
  assertion. *Retention → daily* is the direction the plan set is already moving, so this
  block follows it rather than inventing a rule.
- **The counter-argument, stated honestly, because it is the real cost.** `_run_daily`
  records `scheduler_daily_state` **only when every daily command exits 0**
  (`daily_errors == 0`). A daily command that persistently fails therefore leaves the marker
  unrecorded, and `_record_daily_state` then clears `hourly_marker` — so the whole daily set
  re-runs on the next hourly tick, up to ~16 times a day. `send_alerts` is
  **non-idempotent**. **Mitigation, and it is binding: `purge_consent_records` returns 0 on
  every non-exceptional outcome — nothing eligible, nothing to anonymise, `--dry-run` — and
  raises only on a genuine error**, mirroring `consent_hard_delete`, which logs and returns
  rather than raising. A zero-eligible run must never be a failure.
- **Rejected: a new tier.** A third `*_COMMANDS` list is a scheduler, marker, `_stop_aware_dispatch`
  and test change for no behavioural gain. **Rejected: `HOURLY_COMMANDS`.** See above, and
  note it would be a **tenth** hourly entry, enlarging the surface that can make the
  container report unhealthy, against a boundary that does not need it.

**Constants — two, hardcoded, no CLI flag.** `_FINGERPRINT_RETENTION_DAYS` and
`_DECISION_RETENTION_DAYS`, both module-level, both from R1/R2.
`db-retention.md` is explicit: *"All retention values are hardcoded in the respective
management command source files. No environment variables or CLI arguments (beyond
`--dry-run`) are read for retention durations."* **Do not add `--older-than`** — three
sibling commands (`consent_hard_delete`, `archive_sweep`, `cleanup_login_tokens`) all take
their TTL from a constant, and a flag would let `privacy.html`, `db-retention.md` and the
command drift apart silently. The command asserts the invariant
`0 < _FINGERPRINT_RETENTION_DAYS <= _DECISION_RETENTION_DAYS` itself, so a mis-ordering fails
loudly at run time instead of making the fingerprint stage a silent no-op.

**Advisory-lock discipline.** One
`with transaction.atomic(): with advisory_lock(AdvisoryLockId.CONSENT_RECORD_SWEEP):`
around the whole operation — **transaction-scoped**, `session=False`, which is the shape
every entry in `test_sweep_lock_structure.py::SWEEP_COMMANDS` uses and the only one
`db-retention.md` calls *"PgBouncer-safe"*. The lock is taken **before** any row is touched
and released on commit. `LOCK_TIMEOUT_SECONDS` (10 s, a connection setting) bounds the wait;
a contending run is retried on the next daily tick.

**Batching — default OFF, with the threshold that flips it stated.** Follow
`consent_hard_delete` / `purge_rejected_ads` / `cleanup_login_tokens`: one `atomic()`, one
lock, a filtered `UPDATE`, a count logged **after** the lock. **If** the eligible set can
exceed ~10⁵ rows, adopt `archive_sweep`'s shape verbatim — frozen cutoff above the loop,
keyset `(consent_given_at, pk)` cursor (`consent_given_at` is **not** unique, so `pk` is a
required tiebreaker), `_BATCH_SIZE = 500`, per-batch `atomic()` + `select_for_update()`,
`session=True`, and the abort log naming the cursor. Note that a session-scoped lock is
**not** safe under PgBouncer transaction-mode pooling, which is exactly why it is the
non-default. Decide from the table's real cardinality at implementation time and record the
number in the commit body.

**Structured logging and metrics.** `logger = logging.getLogger(__name__)`; a final
`logger.info` naming the two reported counts and the dry-run flag. **The convention this
repo actually has is the log, not a metric** — `test_sweep_consent.py::test_log_reports_user_count_not_cascade_total`
pins that `consent_hard_delete` logs the **entity** count and not the cascade total. **Ship
no Prometheus counter.** `django-prometheus` is wired only into the **web** process
(middleware order + `/metrics`); `PROMETHEUS_MULTIPROC_DIR` and the
`/tmp/prometheus_multiproc` tmpfs are configured on `web` **only**, so a counter written by
the scheduler subprocess would never be reaped or scraped. Phase 07's `Q07-8` reached the
same conclusion from the other direction (*"the value is not merely unreaped, it is invisible
to the scraped directory"*). Match `consent_hard_delete`: two counts, one line, `hold_ms`
omitted unless batching is adopted (`archive_sweep` logs it).

**Interaction with `withdraw_consent` — BLOCK 15 writes neither BLOCK 9's nor BLOCK 10's
code.**

| Owner | Function | What it owns | Relationship |
|---|---|---|---|
| **BLOCK 9** (landed, `474a68d`) | `users/services/deletion.py::withdraw_consent` | The teardown region **inside the existing `atomic()`**: `LoginToken.objects.filter(user=user).delete()`, `SavedSearch.objects.filter(user=user).update(is_active=False)`, `SearchHistory.objects.filter(user=user).delete()` | **Untouched.** BLOCK 15 does not edit `deletion.py` |
| **BLOCK 10** (next writer) | the same function | Inserts the `ConsentRecord` write inside that same `atomic()`, after the teardown | **Untouched.** BLOCK 15 lands **after** BLOCK 10 and re-reads `deletion.py` immediately before doing anything that could interact with it |
| **BLOCK 15** | the new command only | Retention of `ConsentRecord` rows past the ratified windows | One table, one sweep, one owner |

**Why BLOCK 15 must not touch `deletion.py`, stated as a rule rather than caution:** a
sweep that also anonymised inside `withdraw_consent` would be a **second, differently-triggered
write path for the same table** — the divergence failure this plan files repeatedly. Two
triggers, two sets of preconditions, one table.

**Why the ordering is safe, and what actually happens to a withdrawn user's consent rows.**
`withdraw_consent` sets `consent_revoked_at`; 30 days later `consent_hard_delete` (lock 3)
deletes the `User` row. Because `ConsentRecord.user` is `on_delete=SET_NULL`, that hard-delete
**cascades nothing** — the consent rows are **orphaned, not destroyed**. That is correct and
must stay correct, and it is exactly what EDPB §107 wants: the evidence outlives the
identification. The orphan is then the row this sweep later anonymises. **So the two sweeps
compose in the right order and neither destroys the other's work.**

**No double-delete and no deadlock — the actual mechanism, not an assurance.** The two sweeps
touch **disjoint tables** (`consent_hard_delete` → `users` + `ads` + `moderation` +
`analytics`; this sweep → `consent_records`) and hold **different advisory locks** (3 and 14).
PostgreSQL advisory locks and row locks are independent lock spaces, so there is no
lock-ordering cycle between them and no shared row, hence no double-delete. Each sweep takes
its advisory lock **before** touching any row, which is the `delete_sweep` /
`consent_hard_delete` discipline and the reason no cycle can form. **One shared resource
exists and it is deliberate:** nulling `user_id` is an `UPDATE` on an indexed FK column, so
each anonymised row costs one index maintenance — once, at anonymisation. Re-examination on
later runs is a read, not a write. If batching is adopted, that write is what the batch size
bounds.

**One thing this sweep must NOT absorb:** `SearchHistory`. BLOCK 14 owns
`SearchHistory.query_normalized` and BLOCK 9 owns its deletion. A consent-retention sweep
that also reaped search history would be the second-TTL-for-one-table drift the plan already
files against `DRAFT`.

**Rollout and the index — a migration IS in scope, and here is why.**

**Verified: `consent_records` has no index on `consent_given_at`.** `users/migrations/0001_initial.py`
creates the model with **no** `AddIndex` and **no** `db_index=True` on that column.
`Meta.ordering = ["-consent_given_at"]` **does not create an index** in Django or PostgreSQL.
The only indexes on the table are the primary key and Django's automatic FK index on
`user_id`. So a sweep filtering `consent_given_at < cutoff` **seq-scans**.

**The repo's own precedent says index it, and says how:**

| Precedent | Index | Shape |
|---|---|---|
| `users/0001_initial.py` | `AddIndex(model_name="user", fields=["consent_revoked_at"], name="IX_users_erasure_sweep")` | **One column, one sweep, same app.** The closest precedent in the repository |
| `archive_sweep` | `IX_ads_archive_sweep` | Its docstring: *"`published_at` is the batch key because it is the only key PostgreSQL can turn into an `Index Cond`"* |
| `search/0001_initial.py` | `AddIndex(model_name="searchhistory", fields=["user_id", "-created_at"], name="search_hist_user_id_3ea0ad_idx")` | A composite whose **leading** column is the one BLOCK 9's `SearchHistory.objects.filter(user=user).delete()` filters on |

The repo's rule, read off all three: **the sweep/erasure column is the leading column of a
real index.** `consent_given_at` gets its own single-column index on that logic.

**Decision: `src/backend/apps/users/migrations/0004_consentrecord_sweep_index.py`, a single
`AddIndex(model_name="consentrecord", index=models.Index(fields=["consent_given_at"], name="IX_consent_records_sweep"))`.
In scope for this block.** It is **not** a data migration: it is reversible by dropping the
index and re-addable, so the plan's "migrations run exactly once before both start"
constraint is unaffected, and the phase-07 line *"No phase ships a migration unless the
adoption question makes one unavoidable"* is satisfied by the seq-scan evidence above.
Check the directory immediately before generating — the current head is
`0003_logintoken_browser_binding` — and **never renumber or edit an existing migration**.
**Honest cost:** the index is not free at the row level; every new consent insert maintains
it. That is the right trade at this volume and it is the trade `IX_users_erasure_sweep`
already made.

**Index name = `IX_consent_records_sweep`** (Django's 30-character limit on index names; the
identifier convention in `db-retention.md`'s `Index` column). Mirror it in
`docs/02-database/db-schema.md` per §1.4.

**Testability — what makes "the sweep did not delete a fresh record" a real assertion.**
Plan §1.5 forbids asserting a literal private name, a line number, a template substring, a
column count or a symbol's presence. Under those rules:

- **A count is not an assertion.** `assertEqual(ConsentRecord.objects.count(), 1)` passes for
  a sweep that deletes *everything except one row*. **The in-TTL guarantee is real only when
  the test asserts the re-read row's own field values**: create a row, run the command, then
  re-read it and assert `choice`, `categories`, `consent_version` **and** `session_key` are
  what was written. That fails if the sweep deletes inside the window, **and** if it
  anonymises inside the window — which a count cannot distinguish.
- **The construction detail that makes it possible:** `consent_given_at` is
  `auto_now_add=True`, so `create()` **overwrites** any explicit value. A row at a chosen age
  must be written with `create()` and then aged with
  `ConsentRecord.objects.filter(pk=…).update(consent_given_at=…)` — a bulk `update` bypasses
  `auto_now_add`. This is the standard in-repo technique and the Implementor must use it; a
  test that silently fails to age its row asserts nothing.
- **The two-stage boundary is proven by three rows at three ages** driven through the real
  command — inside the fingerprint window, between the windows, past the decision window —
  asserting the **field-level** outcome of each. **The middle row is the one that
  distinguishes "anonymise" from "delete",** and it is the only row whose continued
  existence proves the design.
- **`user` and `session_key` are cleared together or not at all.** The middle row must show
  **both** cleared. A sweep that nulls `user_id` one statement earlier than `session_key`
  leaves a live re-identification path through `django_session`, and this is the assertion
  that catches it. (The cheapest implementation detail that prevents the bug is a single
  `.update(user=None, session_key=None, …)` — one statement cannot be half-applied.)
- **The re-prompt coupling** — one boundary, one source of truth. A row older than
  `CONSENT_REPROMPT_DAYS` (the test **imports the constant**; it does not restate 365)
  survives with its decision fields intact, **and** `consent_state()` for a user past that
  window reports `consent_shown is False`. Two behaviours, one boundary. This is the "does
  the old record survive the re-prompt" question answered by a test rather than by prose.
- **Interaction, not trivia.** With a `SavedSearch` belonging to the same user in place, run
  the command and assert the `SavedSearch` is **still present and still active** — the
  "cannot double-delete" claim expressed as absence-of-damage. Add a **control row** for a
  second user outside every window and assert it is untouched, so a sweep that deleted the
  whole table goes red.
- **`--dry-run`.** Against a table holding one eligible and one ineligible row, a dry run
  leaves the eligible row's fields **still populated** — not "the count is the same" — and
  the log line names the same numbers a real run would log. `consent_hard_delete`'s shape.
- **Idempotence.** A second run performs no further change and reports zero work, asserted as
  *absence of state change plus the reported number*, never against a private counter's value.
- **The lock.** Covered by adding the command to `test_sweep_lock_structure.py`'s three
  constants — a runtime spy asserting the correct `AdvisoryLockId` member is acquired **while
  a transaction is active**. That is behaviour. **Do not** write a test asserting
  `AdvisoryLockId.CONSENT_RECORD_SWEEP == 14`; phase 16's `B-10` explicitly refused to assert
  `SESSION_COOKIE_AGE`'s integer for exactly this reason, and `test_advisory_lock_ids.py` no
  longer asserts integers (C-B15-6).
- **The changelist** — two separate facts: `"session_key" not in ConsentRecordAdmin.list_display`
  **and** `"session_key" in ConsentRecordAdmin.search_fields`. **Residual, recorded not
  closed:** `search_fields == ["session_key"]` means a staff user with the changelist
  permission can still **probe** a session key they already hold and learn whether a row
  exists. That is materially weaker than enumerating every key from the list page, and BLOCK
  15 does not close it. Named owner, not silently dropped.
- **`privacy.html` §6** — prose is not test-gated (BLOCK 9 makes the same point); the gate is
  a second reader.

**Binding constraints**

1. **`--dry-run` is mandatory**, following `consent_hard_delete`.
2. **The sweep never deletes a `ConsentRecord` row.** Rows inside the windows are Art. 7(1)
   evidence. Past the fingerprint window, **anonymise**: clear `user` and `session_key` in
   the same statement, clear `user_agent` to `""` and `ip_address` to `NULL`, and **retain**
   `choice`, `categories`, `consent_version`, `consent_given_at`.
3. **The command returns 0 on every non-exceptional outcome**, including "nothing eligible"
   and `--dry-run`. This is what keeps the durable daily marker intact (see the tier
   rationale). Raise only on a genuine error.
4. **`AdvisoryLockId.CONSENT_HARD_DELETE == 3` is not this command's lock** and must not be
   renumbered. The new member is **14**, re-verified immediately before editing; take **15**
   if phase 07 BLOCK 8 has landed first, and record which id was used.
5. **No new column on `ConsentRecord`** — a stamp column turns
   `test_pii_inventory.py::test_listed_models_have_no_unreviewed_column` red. Proof that the
   sweep ran belongs in the log.
6. **Add no entry to `pii_inventory.py` for `user`** — it is relational and the guard skips
   relational fields.
7. **`privacy.html` §6 states one period.** BLOCK 15 is the third editor; re-read and do not
   reintroduce a sentence a previous editor superseded. **No `.po` file is hand-edited** —
   `makemessages`, then non-empty `ru` and `bs`.
8. **`deletion.py` is not in this block's surface.** Neither is `apps/search/**`.

**Implementor task**

```yaml
id: task_06_b15_consent_record_sweep
title: "Anonymise aged ConsentRecord rows on a ratified schedule and drop session_key from the changelist (06-PII-116)"
priority: medium
depends_on: [task_06_b10_consent_audit_in_service]
source_reference: ".ai/plans/06-pii-consent-remediation.md"
source_section: "BLOCK 15 - ConsentRecord retention sweep"
source_blocks: ["BLOCK 15"]
description: >
  ConsentRecord grows without bound, carries a live session_key, a 500-char user_agent and
  a masked ip_address, outlives the user by construction (user is on_delete=SET_NULL), and
  session_key appears in the staff changelist. Add a purge_consent_records command to
  DAILY_COMMANDS that ANONYMISES rows past the ratified windows and never deletes them,
  taking AdvisoryLockId 14, with a mandatory --dry-run; drop session_key from
  ConsentRecordAdmin.list_display; add the index the sweep filters on; and record the
  periods in privacy.html section 6 and db-retention.md. The TTLs are OWNER-RATIFIED
  literals (_FINGERPRINT_RETENTION_DAYS, _DECISION_RETENTION_DAYS) - the Implementor does
  not choose them and does not add a CLI flag for them. RATIFIED AS PROJECT DECISIONS: the
  owner ruling of 2026-10-04 re-grounded R1 on purpose and WITHDREW the limitation-period
  justification it was originally ratified with - see section "Retention framing correction
  (owner ruling 2026-10-04)". BLOCK 19 (06-NEW-02) later added the third literal,
  _ACTOR_RETENTION_DAYS, inside this same command.
goals:
  - "bound the consent ledger by de-identifying aged rows instead of deleting them"
  - "stop a live session identifier being enumerable in the staff changelist"
  - "keep the Art. 7(1) evidence intact across the re-prompt boundary"
files:
  - path: "src/backend/apps/core/management/commands/purge_consent_records.py"
    targets:
      - type: class
        name: Command
  - path: "src/backend/apps/core/enums.py"
    targets:
      - type: constant
        name: AdvisoryLockId
  - path: "src/backend/apps/core/utils/advisory_lock.py"
    targets:
      - type: module_docstring
        name: "advisory lock allocation table"
  - path: "src/backend/apps/core/utils/scheduler.py"
    targets:
      - type: constant
        name: DAILY_COMMANDS
  - path: "src/backend/apps/core/tests/test_scheduler.py"
    targets:
      - type: class
        name: TestSchedulerConstants
  - path: "src/backend/apps/core/tests/test_sweep_lock_structure.py"
    targets:
      - type: constant
        name: SWEEP_COMMANDS
  - path: "src/backend/apps/users/migrations/0004_consentrecord_sweep_index.py"
    targets:
      - type: class
        name: Migration
  - path: "src/backend/apps/users/services/pii_inventory.py"
    targets:
      - type: constant
        name: PII_ERASURE_ENTRIES
  - path: "src/backend/apps/users/admin.py"
    targets:
      - type: class
        name: ConsentRecordAdmin
  - path: "src/backend/apps/users/tests/test_purge_consent_records.py"
    targets:
      - type: class
        name: TestPurgeConsentRecords
  - path: "src/backend/templates/privacy.html"
    targets:
      - type: template_section
        name: "section 6"
  - path: "docs/02-database/db-retention.md"
    targets:
      - type: doc_section
        name: "Other sweeps"
  - path: "docs/02-database/db-schema.md"
    targets:
      - type: doc_section
        name: "consent_records"
changes:
  - action: add_code
    description: >
      New daily sweep. Under one transaction-scoped advisory lock (id 14), anonymise rows
      whose consent_given_at is older than _FINGERPRINT_RETENTION_DAYS by clearing user and
      session_key in the SAME statement plus user_agent and ip_address, retaining choice,
      categories, consent_version and consent_given_at. Never delete a row. Support a
      mandatory --dry-run that reports the same two counts and mutates nothing. Return 0 on
      every non-exceptional outcome including an empty eligible set. Append it to
      DAILY_COMMANDS. Remove session_key from ConsentRecordAdmin.list_display but keep it
      in search_fields and readonly_fields.
    code_hint: |
      # Anonymise, never delete: the row IS the Art. 7(1) evidence.
      # One statement - user and session_key must never be half-cleared.
      # An anonymous record is identified by session_key (see the model docstring),
      # so clearing user alone would leave a live re-identification path.
  - action: add_code
    description: >
      AddIndex on consent_given_at, named IX_consent_records_sweep. The sweep filters on a
      column that today has no index; Meta.ordering does not create one. Same shape as
      IX_users_erasure_sweep in this app's own 0001_initial.
  - action: modify
    description: >
      pii_inventory.py: users.ConsentRecord.session_key RETAIN -> NULL,
      .user_agent RETAIN -> CLEAR (the column is blank=True and not nullable),
      .ip_address RETAIN -> NULL. Each reason names BLOCK 15, the lock id, the ratified
      constant and why the action is what it is. No entry is added for user (relational,
      skipped by the guard) and no new column is added to the model.
  - action: modify
    description: >
      docs: privacy.html section 6 states one period; db-retention.md gains an Other sweeps
      row and its Configuration sentence gains the two new hardcoded values; db-schema.md
      mirrors the new index.
acceptance_criteria:
  - "--dry-run mutates nothing: the eligible row's fingerprint fields are still populated afterwards"
  - "a row inside the fingerprint window is untouched field for field, not merely still present"
  - "a row between the windows keeps choice, categories, consent_version and consent_given_at, and has user and session_key cleared in the same state"
  - "no ConsentRecord row is ever deleted, at any age"
  - "the command returns 0 when nothing is eligible, so the durable daily marker is unaffected"
  - "the scheduler still starts: _validate_commands resolves the new entry via get_commands()"
  - "session_key is absent from ConsentRecordAdmin.list_display and present in search_fields"
  - "pii_inventory.py declares NULL/CLEAR/NULL for the three ConsentRecord entries and adds no entry for user"
  - "privacy.html section 6 states one retention period"
tests_to_run:
  - "src/backend/apps/core/tests/test_scheduler.py"
  - "src/backend/apps/core/tests/test_sweep_lock_structure.py"
  - "src/backend/apps/core/tests/test_advisory_lock_ids.py"
  - "src/backend/apps/core/tests/test_sweep_consent.py"
  - "src/backend/apps/core/tests/test_privacy.py"
  - "src/backend/apps/users/tests/test_pii_inventory.py"
  - "src/backend/apps/users/tests/test_consent_records.py"
  - "src/backend/apps/users/tests/test_consent_context.py"
  - "src/backend/apps/users/tests/test_deletion.py"
  - "src/backend/apps/users/tests/test_purge_consent_records.py"
```

**Tests required** — logic and interaction, not implementation trivia (§1.5). The full
assertion specification is in *Testability* above; this is the list of what must be proven.
**Every one of these is a behavioural assertion on a row the test created.**

1. **The in-window row is untouched, field for field** — not "still present". After a run, the
   re-read row's `choice`, `categories`, `consent_version` and `session_key` equal what was
   written. This is the block's most important assertion and the one a count cannot make.
2. **The two-stage boundary** — three rows at three ages through the real command: inside the
   fingerprint window ⇒ untouched; between the windows ⇒ identity cleared, **decision fields
   intact, row still present**; past the decision window ⇒ identity cleared, decision fields
   intact, **row still present**. The middle row is what distinguishes anonymise from delete.
3. **`user` and `session_key` are cleared together** — on the middle row, both or neither.
   Never one without the other.
4. **No row is ever deleted, at any age** — including past the decision window. This is the
   standing guarantee and it is the direct answer to `06-PII-116`'s own trap.
5. **The re-prompt coupling** — a row older than `CONSENT_REPROMPT_DAYS` (the test imports
   the constant; it does not restate 365) keeps its decision fields, **and** `consent_state()`
   for a user past that window reports `consent_shown is False`. One boundary, one source of
   truth, two behaviours.
6. **`--dry-run` mutates nothing** — the eligible row's fingerprint fields are **still
   populated** afterwards (not "the count is the same"), and the log line names the same two
   numbers a real run logs.
7. **An empty eligible set is a success** — the command returns 0. This is what protects the
   durable daily marker, and it is asserted as an exit status, not as prose.
8. **Idempotence** — a second run changes nothing further and reports zero work, asserted as
   absence-of-state-change plus the reported number.
9. **No interaction with BLOCK 9's teardown** — with a `SavedSearch` for the same user in
   place, the command leaves it **present and active**; a control row for a second user
   outside every window is untouched.
10. **The lock** — the command is added to `test_sweep_lock_structure.py`'s
    `SWEEP_COMMANDS`, `EXPECTED_SWEEP_COMMANDS` and `_LOCK_TARGET_MODULES`, which pins the
    correct member acquired **while a transaction is active**. **No test asserts the integer
    14**, and `test_advisory_lock_ids.py` is run but not edited.
11. **The inventory declarations** — `pii_inventory.py` declares `NULL` / `CLEAR` / `NULL` for
    the three `ConsentRecord` entries, declares no entry for `user`, and
    `test_pii_inventory.py`'s model-wide guard stays green (which also proves **no column was
    added**).
12. **The changelist** — `session_key` absent from `list_display` and present in
    `search_fields`, asserted as two separate facts.

**Verified to exist** — every `tests_to_run` target above was confirmed present in the tree
before this section was written. `test_scheduler.py` (not `test_scheduler_wiring.py`, which
touches neither command list) is the file carrying the exact-equality `DAILY_COMMANDS`
assertion and therefore **must** be edited; the old list named the wrong file for that job.

**Risk and rollback**

- *Irreversible — but only the identification, never the evidence.* This block anonymises
  rather than deletes, so the Art. 7(1) evidence survives every run and **rollback is not a
  data-recovery problem**. Clearing `session_key`, `user_agent` and `ip_address` cannot be
  undone by re-running anything; the only remedy is the subject consenting again. That is
  the intended trade and the owner should know it is one-directional. Mitigation: the two
  windows are ratified numbers, `--dry-run` is mandatory, and test 1 pins the in-window
  guarantee.
- *Risk (the numbers are unratified):* shipping on an invented TTL is the one way this block
  can cause harm, which is why binding constraint 3 plus test 7 exist and why Q-D4(b) blocks
  the start. **The block does not begin until R1 and R2 are ratified.**
- *Risk (lock):* `14` was verified free at `b7ba213`, but **phase 07 BLOCK 8 claims the same
  integer** and names this block as its external dependency. Mitigation: re-read
  `apps/core/enums.py` immediately before editing; take `15` if `14` is gone; **tell** the
  coordinator which id was used. The guard test cannot catch a reuse — that is a human rule.
- *Risk (scheduler):* the new daily entry's exit code is load-bearing in the durable daily
  marker, and a persistently failing entry would re-run `send_alerts` (non-idempotent) up to
  ~16 times a day. Mitigation: binding constraint 3 and test 7.
- *Risk (first run over a large table):* the sweep filters on `consent_given_at`, which has no
  index today, so the **first** run seq-scans before the migration lands. Mitigation: **ship
  the migration in the same commit**, and run `--dry-run` once before the first mutating run.
- *Rollback:* the code reverts cleanly and, because nothing is deleted, **nothing is lost**.
  For a wrong-but-ratified number the remedy is "correct the number forward", and the rows
  anonymised under the old number are simply not restored — stated here so the block does not
  claim a reversibility it does not have.
- *Cross-phase:* phase 12's backup/restore interacts with a purge (§5.6); phase 07 BLOCK 8
  contends for the lock id and for `db-retention.md`'s tables; phase 03 BLOCK 5 shares
  `db-retention.md`.
- *Adjacent gap, recorded not owned:* `db-retention.md` §3 step 1 still lists the withdrawal
  teardown **without** BLOCK 9's landed `SavedSearch` deactivation and `SearchHistory`
  deletion. This block edits the same file and will see it. **It is BLOCK 9's
  documentation, not BLOCK 15's deliverable** — record the discrepancy in this block's commit
  body and do not silently absorb the fix.

---

### BLOCK 16 — Redact moderator free text at write time (06-PII-114)

| | |
|---|---|
| **Findings owned** | `06-PII-114` |
| **Depends on** | **nothing** in this plan. BLOCK 3's inventory is a *reader* of this block's decision, not a prerequisite — but the task declares `depends_on: [task_06_b03_pii_inventory]` so the two never race on the same reasoning |
| **Blocks** | nothing. Phase 10 BLOCK 12's `admin_actions.py` move is **not** ordered behind this block, because this block does not edit that file (§5.3) |
| **Priority** | P2 |
| **Risk level** | **MEDIUM at implementation**, LOW as a finding. The severity is LOW; the change is not, because it rewrites a value staff rely on for audit, and because `sanitize.py` is shared with three other blocks |
| **Required agents** | **Auditor · Planner · Validator.** The Researcher question the plan originally left open is **closed below by measurement** — there is no design question left for a Researcher, so requiring one would be ceremony |

**The defect, and three corrections to this block's own premise (C-17).**

`ModeratorActionLog.reason` is an **unbounded** `TextField` documented *"Moderation reason
(INTERNAL ONLY - never shown to seller)"*, with `ad` and `user` both `on_delete=SET_NULL` — so
the row survives user erasure as an orphan, and after erasure the free text is no longer
associated with anyone and simply stays. A moderator quoting a seller's message (*"user said:
call me on +382 69 000 123"*) persists the data subject's data **indefinitely**. Combined
with `06-PII-101` this is a **second orphan-PII channel**. That much stands.

Three statements this block previously made are **wrong** and are corrected here:

1. **`Ad` has no `rejected_reason` column.** `src/backend/apps/ads/admin.py::rejected_reason`
   is a **display helper** listed in `AdAdmin.list_display`: it reads
   `obj.moderation_logs.filter(action_type=REJECT).last()` and returns `log.reason[:100]`.
   There is exactly **one** free-text column in this finding — `ModeratorActionLog.reason`.
   Any inventory entry or task target naming `Ad.rejected_reason` is a **defect**.
2. **The writer inventory was wrong.** The names `log_auto_moderation_failure`,
   `log_rejection` and `log_auto_published` **do not exist anywhere in the repository.** The
   module's real surface is `log_auto_fail`, `log_manual_reject`, `log_auto_publish`,
   `log_manual_publish`, `log_ban_account`, `log_soft_delete`, driven by `set_moderation_failed`,
   `set_rejected` and `set_published`.
3. **`set_moderation_failed`'s `reason` parameter is dead.** It is declared
   (`reason: str = "Auto-moderation failed"`) and **never used** — the body calls
   `log_auto_fail(ad_id=ad.id, user_id=ad.user_id)`, and `log_auto_fail` hard-codes its own
   literal. A caller passing a custom reason loses it silently. This is a **pre-existing
   latent bug**, it is **not** this finding's defect, and it is **out of scope**: fixing it
   would *widen* what can reach the column. The Implementor must not repair it silently.

**The writer inventory, verified against the tree.** Every `ModeratorActionLog.objects.create(...)`
in `src/` — **all seven production sites** — lives in
`src/backend/apps/moderation/services/moderation_log.py`. The only other occurrences are
**four in test code** (`apps/analytics/tests/test_moderation_analytics.py`,
`apps/core/tests/test_sweep_consent.py`, `apps/core/tests/test_sweep_purge_rejected.py`),
which build rows directly through the manager. `ModeratorActionLogAdmin` is fully read-only
(`has_add_permission`, `has_change_permission` and `has_delete_permission` all `False`), so
there is **no admin write path** for `reason` at all.

| Writer | `reason` argument | Redaction needed |
|---|---|---|
| `log_auto_fail` | fixed literal `"Auto-moderation failed"` | no — constant |
| `log_auto_publish` | fixed literal `"Auto-published"` | no — constant |
| `log_manual_publish` | fixed literal `"Manually published by moderator"` | no — constant |
| `log_manual_reject` | free text from the caller | **yes** |
| `log_ban_account` | free text from the caller | **yes** |
| `log_soft_delete` | free text from the caller | **yes** |
| `log_photo_removed` | free text from the caller | **yes** (already redacted by BLOCK 10) |

The plan's earlier claim that the fixed literals were `"Bulk rejection via admin action"`,
`"Bulk ban via admin action"` and `"Bulk deletion via admin action"` is **also wrong** — those
strings appear **nowhere** in the repository. `bulk_reject`, `bulk_ban_users` and `bulk_delete`
pass the caller's `reason` through verbatim. The three fixed literals that do exist are the
three in the table above.

**The chokepoint already exists — the plan's "per-site vs one chokepoint" question is settled
by the tree, not by taste.** `moderation_log.py` **is** the chokepoint by construction, and the
repository already asserts the invariant: `apps/ads/admin.py`'s `AdAdmin` docstring states a
form-driven status change routes "through the existing moderation services so the audit row
has exactly one writer". So this block is **not** "build a chokepoint" — it is "name the
redaction once, inside the module that already is the chokepoint".

**Chosen.** One non-truncating redactor call, applied at the **four free-text `create`
sites** (`log_manual_reject`, `log_ban_account`, `log_soft_delete`, and
`log_photo_removed`, the last already redacted by BLOCK 10). Three call sites
were new in BLOCK 16; one rule, no new class, no manager, no `QuerySet` override, no new
module, no new file.

**Rejected — per-site inline `redact_search_query(...)`.** It looks cheaper (there is nothing
new to name) but it is the exact failure mode this phase keeps filing: the
`withdraw_consent` `update_fields` list, the analytics consent gate, the erasure inventory —
  each was correct at its sites and correct nowhere else. `moderation_log.py`'s seven writers are
  stable today (the seventh, `log_photo_removed`, was added in BLOCK 10), and three copies of one
expression is three places to forget. A **named** helper is one place to forget.

**Rejected — a `ModeratorActionLogManager` or custom `QuerySet.create` override.** It would be
truly unbypassable, and it is still wrong here. It hides the redaction from the reader of the
writer; it makes a security-relevant write depend on a manager swap that a later refactor can
remove silently; no other model in the repository uses the idiom (rules 5 and 7); and four
test modules build rows through the manager today, so an override would silently start
rewriting their fixtures — scope this block does not own.

**The `set_*` drivers need no edit of their own.** `set_rejected` forwards `reason` straight
to `log_manual_reject`. The whole inbound chain is:
`views/review.reject_ad` → `admin_actions.reject_ad` → `set_rejected` → `log_manual_reject`;
`views/review.ban_user`, `admin_actions.ban_user_for_ad` and `bulk_ban_users` →
`log_ban_account`; `admin_actions.soft_delete_ad` and `bulk_delete` → `log_soft_delete`;
`views/api_bulk.bulk_moderation_action` reads `payload.reason` from the Pydantic boundary DTO
(`schemas.py`: `reason: str = ""`) and calls `reject_ad`. **Redaction at the three `create`
sites therefore covers every free-text entry point in the application.**
`set_moderation_failed` forwards nothing (dead parameter, above) and `set_published` writes
only the two fixed literals.

**The redaction primitive — the plan's claim is verified, with one correction.**

`redact_search_query` (`apps/core/utils/sanitize.py`) is the in-repo redactor. It applies the
same three masks `_EMAIL_PATTERN`, `_PHONE_PATTERN`, `_NAME_PATTERN` with `_mask_email`,
`_mask_phone`, `_mask_name`, then truncates. Measured against the module as it stands:

- **"Never lengthens" — verified TRUE.** 200 000 randomised PII-heavy strings, plus a
  systematic sweep over 225 token pairs × 4 separators: **maximum positive length delta 0** in
  both. `_mask_email` and `_mask_phone` are exactly length-preserving by construction; the
  100-char truncation only shortens.
- **It is non-expanding, not exactly length-preserving.** `_mask_name` rebuilds its match with
  `" ".join(...)`, which collapses a multi-character whitespace run to one space. Measured:
  `"Ivan  Petrov  double spaces"` (27 chars) → 26 chars. Harmless for an unbounded
  `TextField`, but it means a "byte-identical" claim must be scoped to text containing **no**
  mask trigger at all (see *Tests required*).
- **It truncates to `_MAX_QUERY_LENGTH = 100`.** A 210-character clean sentence becomes 100,
  cut mid-word. **Applying `redact_search_query` to `reason` would silently destroy the
  moderator's text** — and would destroy it most often in exactly the case this finding is
  about, because the reason that needs redacting is the one that quotes a seller. **This is
  the decision the plan left open, and the answer is: do not call `redact_search_query` here.**

**Chosen — add one sibling, `redact_free_text(text: str) -> str`, to
`src/backend/apps/core/utils/sanitize.py`.** The same three patterns and the same three masks,
**no truncation**. Measured on the same 200 000 randomised strings: **0 growth events**, and
**idempotent** — `redact_free_text(redact_free_text(x)) == redact_free_text(x)` on every case
tried, including the phone, e-mail, Cyrillic and all-caps-prose masks. Idempotence is
structural, not lucky: each mask leaves a run of `*`, `*` is in none of the three character
classes and cannot itself form a match, so a second pass is a no-op and a placeholder can never
be corrupted by double redaction.

**Rejected — duplicating the three regexes and three masks into the moderation app.** It leaves
`sanitize.py` untouched but creates a second copy of security logic; when one copy is later
tuned — and BLOCK 14 and phase 08 both live in this neighbourhood — the other silently stops
matching and one of the two paths leaks. Reuse in the module that owns the patterns.
**Rejected — a keyword-only truncation opt-out on `redact_search_query`.** Smallest diff, but it
edits the one function phase 08 BLOCK 4 explicitly forbids changing, whose never-lengthen
invariant is declared shared. A **sibling** is purely additive: it touches neither
`redact_search_query` nor `_MAX_QUERY_LENGTH`, so phase 06 BLOCK 4, phase 08 BLOCKS 3/4 and
phase 09 BLOCK 16 are unaffected.

**Column safety and reversibility.** `reason` is an unbounded `TextField` — no `max_length`, no
database cap — so the verified non-expanding property cannot overflow it. The only
width-sensitive consumer is `apps/ads/admin.py::rejected_reason`, which truncates to 100 **at
render time**; because redaction never lengthens, the rendered width is unchanged or shorter.
**Redaction is irreversible**: the original phone, e-mail address and name are not recoverable
from the stored row, by design. **It applies to new writes only.** No backfill is proposed and
none should be — rewriting an existing audit row would destroy evidence already relied on,
`get_rejection_reasons` buckets by the stored text so historical counts would shift under an
operator reading them, and no severity justifies retroactively altering a compliance record.
**Rows written before this change keep their original text, and no read-time rewriting is
added to any display path** — a render-time filter would leave the value in the database and in
every backup, which binding constraint 1 forbids.

**One consequence to state rather than discover.** `_NAME_PATTERN` matches two or more
consecutive capitalised words, so **title-case prose is masked**: measured,
`"Photos Are Blurry And The Price Is Wrong"` → `"P***** A** B***** A** T** P**** I* W****"`,
and `"REFUND REQUESTED FOR ORDER 1234567890"` has its order number masked as a phone number.
That is the phase's recorded Path A decision (a first+last-name shape), it is privacy-positive,
and the result stays legible to a moderator — but it must be stated in the field's `help_text`,
not found in production. Note the `CategoryRejectReason` prefixes the review view composes
(`spam_scam: …`, all snake_case) are **unaffected**. Also measured: an e-mail with a one- or
two-character local part (`a@b.co`) is deliberately left untouched, because `_mask_email`
preserves a local part of two or fewer characters — so a test must use a realistic local part.

**Documentation.** `docs/01-spec/technical-specification.md` **§A "Moderation model"** gets one
sentence. §A already owns this contract — it carries the adjacent rule *"Seller rejection path:
bot replies 'ad failed moderation' + rules link; **no specific reason disclosed**"* — and phase
06 holds the reservation on the file, while BLOCKS 2, 4 and 11 all target **§F/§K**, so §A is a
disjoint region and §1.3's one-implementor-sequential rule covers the ordering. Rejected:
**`db-retention.md`** (its `ModeratorActionLog.user_id` SET-NULL sentence stays true — this
block changes no retention — and it is the most contended document in the phase, claimed by
BLOCK 15 *and* phase 03 BLOCK 5); **`admin-stories.md` US-A11** (a user-story document contended
by phase 05, and the moderator-facing instruction belongs where a moderator actually meets it —
the field's `help_text`, which the Implementor amends in `models.py`); **a new moderation
document** (there is no second home, and one sentence does not justify a document). **No schema
change**, so `db-schema.md` needs no edit.

**i18n.** No user-visible string is added or changed. `apps/ads/admin.py::rejected_reason`
renders *stored* text, not a translatable string; the review template is untouched;
`ModeratorActionLog.reason.help_text` is a plain Django literal today and **stays** one —
wrapping the amended text in `gettext_lazy` would create an i18n obligation this block must not
take on. **No `.po` change, no `makemessages`, no `compilemessages`, no `djlint`.**

**The BLOCK 3 inventory — deliberately no edit.** The shipped entry in
`src/backend/apps/users/services/pii_inventory.py` (`moderation.ModeratorActionLog` /
`reason` / `ErasureAction.RETAIN`) already reads, in the present tense: *"BLOCK 16 (06-PII-114)
redacts at WRITE TIME, which is not an erasure action — adding a write-time rule to this
inventory would be a category error."* That sentence is **not stale** once this block lands; it
becomes true rather than aspirational, and it names no pending state. Its leading *"NOT
implemented today (retention)"* also stays exactly true: nothing here erases a row and the
row's retention is unchanged. BLOCK 3's guard
(`test_retained_free_text_entries_name_their_owning_block`) asserts only that the reason names
its owning block and that the action is `RETAIN` — both unaffected. **The Implementor must not
edit `pii_inventory.py`.** The action stays `RETAIN`; a write-time rule there would be the very
category error BLOCK 3's reason names.

**File surface (semantic units)**

| File | Symbol / target | Operation |
|---|---|---|
| `src/backend/apps/core/utils/sanitize.py` | one **new** module-level function beside `redact_search_query`, reusing `_EMAIL_PATTERN`, `_PHONE_PATTERN`, `_NAME_PATTERN`, `_mask_email`, `_mask_phone`, `_mask_name` | **additive only.** Do not modify `redact_search_query`, `_MAX_QUERY_LENGTH`, `mask_telegram_id`, `sanitize_query_for_log` or `sanitize_autocomplete_query`. Contended by phase 06 BLOCK 4 and phase 08 BLOCKS 3/4 — re-read immediately before editing |
| `src/backend/apps/moderation/services/moderation_log.py` | the `reason=` argument of the `ModeratorActionLog.objects.create(...)` call inside `log_manual_reject`, `log_ban_account` and `log_soft_delete` — **`log_photo_removed` (added in BLOCK 10) already calls `redact_free_text(reason)` and needs no edit** | **the whole production change.** `log_auto_fail`, `log_auto_publish`, `log_manual_publish`, `log_photo_removed`, `set_moderation_failed`, `set_rejected` and `set_published` are **not** edited |
| `src/backend/apps/moderation/models.py` | `ModeratorActionLog.reason` — `help_text` | amend. **No migration**: `help_text` is not a database column |
| `src/backend/apps/moderation/tests/test_moderation_reason_redaction.py` | new module | new tests |
| `docs/01-spec/technical-specification.md` | §A "Moderation model" | one sentence. **Do not touch §F or §K** (BLOCKS 2, 4, 11) |
| `src/backend/apps/moderation/admin_actions.py` | — | **no edit.** All seven of its functions reach a `create` site; verify, do not modify (§5.3) |
| `src/backend/apps/ads/admin.py` `rejected_reason` | — | **read-only.** Do not add a render-time filter |
| `src/backend/apps/users/services/pii_inventory.py` | — | **no edit.** BLOCK 3's entry is already correct |
| `src/backend/apps/core/tests/test_sanitize.py` | — | **read-only.** Phase 06 BLOCK 4 owns it; do not add tests there |

**Binding constraints**

1. Redaction happens **at write time**, inside the four `ModeratorActionLog.objects.create(...)`
   calls in `apps/moderation/services/moderation_log.py` (`log_manual_reject`,
   `log_ban_account`, `log_soft_delete` and `log_photo_removed`, the last already redacted by
   BLOCK 10). **No render-time or read-time filter
   anywhere** — `apps/ads/admin.py::rejected_reason` must not be touched.
2. **`redact_search_query` must not be called on `reason`.** It truncates to
   `_MAX_QUERY_LENGTH = 100` and would silently discard the moderator's text. Add and call the
   non-truncating sibling `redact_free_text`.
3. **New writes only.** No migration, no data migration, no backfill, no read-time rewriting.
   Rows written before this change keep their original text.
4. **Clean text must pass through unchanged.** `redact_free_text` returns text containing no
   phone, no e-mail and no two-or-more-consecutive-capitalised-words sequence **byte-for-byte
   identical** to the input. The three fixed literals (`"Auto-moderation failed"`,
   `"Auto-published"`, `"Manually published by moderator"`) must be asserted byte-identical,
   and the three `create` sites that use them are **not** edited.
5. **`redact_free_text` is additive.** Do not modify `redact_search_query`,
   `_MAX_QUERY_LENGTH`, `mask_telegram_id`, `sanitize_query_for_log` or
   `sanitize_autocomplete_query`, and do not edit `apps/core/tests/test_sanitize.py` (phase 06
   BLOCK 4 and phase 08 BLOCKS 3/4 own them).
6. **Do not change `on_delete`, the permission predicates, the "INTERNAL ONLY" contract, or
   `set_moderation_failed`'s dead `reason` parameter.** Only the stored value of `reason`
   changes.
7. `apps/moderation/admin_actions.py` is contended by phases 03, 04, 05 and 10. **This block
   does not edit it.** If a change there appears necessary, stop and report it rather than
   making it (§1.3, §5.3).
8. **No user-visible string.** No `.po` change, no `makemessages`, no `compilemessages`, no
   `djlint`. `help_text` stays a plain literal — do **not** wrap it in `gettext_lazy`.
9. **No migration.** `help_text` is not a database column, so nothing in
   `apps/moderation/migrations/` changes and `docs/02-database/db-schema.md` needs no edit.
10. Do **not** edit `src/backend/apps/users/services/pii_inventory.py`. Its
    `moderation.ModeratorActionLog.reason` entry is `ErasureAction.RETAIN` and stays `RETAIN`;
    a write-time rule there is the category error BLOCK 3's reason names.
11. Tests are **Docker-only** (§1.1). `PYTEST_OPTS` is unquoted in
    `docker/entrypoint-test.sh` and **replaces** the pytest defaults; never use
    `--override-ini=addopts=`. A mass `ForeignKeyViolation` on
    `auth_permission`/`django_content_type`, a `FATAL: database "test_mko_bazuna" does not
    exist`, or an `assert not self._finalizers` cascade at fixture setup is a **concurrent-run
    teardown artefact** (`VAL-010`, verified this pass) — confirm no other run is in flight,
    re-run alone, and only then report it as a defect.

**Implementor task**

```yaml
id: task_06_b16_moderation_reason_redaction
title: "Redact moderator free text at write time (06-PII-114)"
priority: medium
depends_on:
  - task_06_b03_pii_inventory
source_reference: ".ai/plans/06-pii-consent-remediation.md"
source_section: "BLOCK 16 - Redact moderator free text at write time"
source_blocks: ["BLOCK 16"]
description: >
  ModeratorActionLog.reason is unbounded staff-authored free text on a row that
  deliberately survives user erasure with user_id = NULL, and no write site redacts it.
  Add a non-truncating redactor beside redact_search_query and apply it at the four
  free-text ModeratorActionLog.objects.create sites, which is every production writer in
  the repository. Amend the field help text and record the rule in the technical
  specification. Ad has no rejected_reason column: apps/ads/admin.py::rejected_reason is a
  render-time display helper over ModeratorActionLog.reason and must not be filtered.
goals:
  - "stop a moderator quoting a seller's contact details from persisting them forever"
  - "redact before the INSERT, so no export and no backup carries the value"
  - "keep every clean moderator reason byte-identical and untruncated"
  - "cover every free-text writer, so the next writer cannot forget"
files:
  - path: "src/backend/apps/core/utils/sanitize.py"
    targets:
      - type: function
        name: redact_search_query
      - type: constant
        name: _MAX_QUERY_LENGTH
    semantic_anchors:
      insert_after:
        type: function
        value: redact_search_query
      reuse_only:
        - "_EMAIL_PATTERN"
        - "_PHONE_PATTERN"
        - "_NAME_PATTERN"
        - "_mask_email"
        - "_mask_phone"
        - "_mask_name"
      do_not_modify:
        - "redact_search_query"
        - "_MAX_QUERY_LENGTH"
        - "mask_telegram_id"
        - "sanitize_query_for_log"
        - "sanitize_autocomplete_query"
  - path: "src/backend/apps/moderation/services/moderation_log.py"
    targets:
      - type: function
        name: log_manual_reject
      - type: function
        name: log_ban_account
      - type: function
        name: log_soft_delete
    semantic_anchors:
      edit_in_body:
        target: log_manual_reject
        type: keyword_argument
        value: "reason="
      edit_in_body:
        target: log_ban_account
        type: keyword_argument
        value: "reason="
      edit_in_body:
        target: log_soft_delete
        type: keyword_argument
        value: "reason="
      do_not_modify:
        - "log_auto_fail"
        - "log_auto_publish"
        - "log_manual_publish"
        - "log_photo_removed"
        - "set_moderation_failed"
        - "set_rejected"
        - "set_published"
  - path: "src/backend/apps/moderation/models.py"
    targets:
      - type: attribute
        name: ModeratorActionLog.reason
  - path: "src/backend/apps/moderation/tests/test_moderation_reason_redaction.py"
    targets:
      - type: module
        name: test_moderation_reason_redaction
  - path: "docs/01-spec/technical-specification.md"
    targets:
      - type: section
        name: "A. Moderation model"
    semantic_anchors:
      do_not_modify:
        - "F."
        - "K."
changes:
  - action: add_code
    description: >
      Add one module-level `redact_free_text(text: str) -> str` to
      apps/core/utils/sanitize.py, beside redact_search_query. It applies the module's
      existing _EMAIL_PATTERN, _PHONE_PATTERN and _NAME_PATTERN with _mask_email,
      _mask_phone and _mask_name, in that order, and does NOT truncate. It returns the
      input unchanged when falsy, mirroring redact_search_query's early return. Its
      docstring states the two properties that were measured: it never lengthens its
      input, and it is idempotent, because each mask leaves a run of "*" and "*" is in
      none of the three character classes. Do not refactor redact_search_query to call
      it - that edits a function phase 08 BLOCK 4 forbids changing.
    code_hint: |
      # In apps/core/utils/sanitize.py, immediately after redact_search_query.
      # Additive only: _MAX_QUERY_LENGTH and redact_search_query are untouched.

      def redact_free_text(text: str) -> str:
          """Redact PII from staff-authored free text before it is persisted.

          Masks phone numbers, e-mail addresses and multi-word personal names using
          the same patterns and masks as ``redact_search_query``, but unlike that
          helper it does NOT truncate: the caller is storing moderator prose in an
          unbounded ``TextField``, where a 100-character cap would silently discard
          the operator's own words.

          Two measured properties this contract depends on:

          * It never lengthens its input, so an unbounded column cannot overflow and a
            render-time truncation cannot grow.
          * It is idempotent. Each mask leaves a run of ``*``; ``*`` is in none of the
            three character classes and cannot form a match, so a second pass is a no-op
            and a placeholder is never corrupted by double redaction.

          Args:
              text: The raw staff-authored text.

          Returns:
              The redacted text, untruncated.
          """
          if not text:
              return text
          redacted = _EMAIL_PATTERN.sub(_mask_email, text)
          redacted = _PHONE_PATTERN.sub(_mask_phone, redacted)
          return _NAME_PATTERN.sub(_mask_name, redacted)
  - action: modify_code
    description: >
      In apps/moderation/services/moderation_log.py, pass `redact_free_text(reason)`
      instead of `reason` as the `reason=` keyword argument to the four
      ModeratorActionLog.objects.create(...) calls, in log_manual_reject,
      log_ban_account, log_soft_delete and log_photo_removed (the last already
      redacted by BLOCK 10; included so the surface is named completely).
      Add the import. Do not touch log_auto_fail, log_auto_publish, log_manual_publish or
      any of the three set_* drivers: set_rejected forwards its reason to
      log_manual_reject and is covered by this edit for free, and set_published writes only
      fixed literals. The redaction is applied to the value handed to create(), so it
      happens inside the caller's existing transaction and cannot be bypassed by the
      admin, the review views or the bulk JSON API.
    code_hint: |
      # apps/moderation/services/moderation_log.py

      from apps.core.utils.sanitize import redact_free_text

      def log_manual_reject(ad_id, user_id, moderator_id, reason):
          log = ModeratorActionLog.objects.create(
              ad_id=ad_id,
              user_id=user_id,
              action_type=ModeratorActionType.REJECT,
              reason=redact_free_text(reason),   # <- the only change in this function
          )

      # Identical one-line change to the `reason=` argument inside log_ban_account
      # and log_soft_delete. The three fixed-literal writers are left alone.
  - action: modify_code
    description: >
      Amend the help_text of ModeratorActionLog.reason in
      apps/moderation/models.py to tell a moderator not to paste a seller's contact
      details, and that phone numbers, e-mail addresses and personal names are masked
      when the row is written, irreversibly, and that the text is never shortened. Keep
      it a plain literal - do not wrap it in gettext_lazy, which would create an i18n
      obligation this block must not take on. No migration: help_text is not a database
      column.
    code_hint: |
      # apps/moderation/models.py
      reason = models.TextField(
          help_text=(
              "Moderation reason (INTERNAL ONLY - never shown to seller). "
              "Do not paste a seller's contact details: phone numbers, e-mail "
              "addresses and personal names are masked when this row is written, "
              "and the masking is irreversible. The text is never shortened."
          ),
      )
  - action: add_code
    description: >
      Add one sentence to section "A. Moderation model" in
      docs/01-spec/technical-specification.md recording that
      ModeratorActionLog.reason is redacted at write time, that the row survives erasure
      with user_id = NULL, and that redaction does not shorten the text. Do not touch
      sections F or K.
    code_hint: |
      # docs/01-spec/technical-specification.md, section "A. Moderation model"
      # - **`ModeratorActionLog.reason` is redacted at write time** (phone numbers,
      #   e-mail addresses, multi-word personal names, via
      #   `redact_free_text()`; never truncated). The row survives user erasure with
      #   `user_id = NULL`, so the redaction - not erasure - is what keeps a moderator's
      #   verbatim quote from persisting the data subject's contact details. The masking
      #   is irreversible and applies to new writes only.
  - action: add_code
    description: >
      Add src/backend/apps/moderation/tests/test_moderation_reason_redaction.py covering
      the five required behaviours. Assert on the STORED value read back from the
      database, never on a helper's return value alone and never on an expected masked
      string. Use the canonical fixtures from src/backend/conftest.py (seller, category,
      city, create_test_ad, moderation_criteria). Do not assert a column count, a line
      number, the mere presence of a symbol, or a literal private name.
    code_hint: |
      # src/backend/apps/moderation/tests/test_moderation_reason_redaction.py
      #
      # 1. every free-text writer: parametrise over log_manual_reject / log_ban_account /
      #    log_soft_delete / log_photo_removed. Reason carries a phone number and an e-mail address with a
      #    realistic local part ("ana.markovic@example.com" - a two-character local part
      #    such as "a@b.co" is deliberately preserved by _mask_email and would make the
      #    test pass for the wrong reason). Assert neither survives in the stored row.
      #    A test that covers one writer proves nothing about the chokepoint.
      # 2. byte-identical: a reason with no phone, no e-mail and no two-or-more
      #    consecutive capitalised words ("Photos are blurry and the price is wrong")
      #    is stored exactly as given; plus the three fixed literals.
      # 3. idempotence: assert redact_free_text(redact_free_text(x)) ==
      #    redact_free_text(x), or the stored-value equivalent - never an expected
      #    masked string, which would pin the placeholder format.
      # 4. no backfill: a row created directly through ModeratorActionLog.objects.create
      #    before the write is re-read and still holds its original text; and
      #    apps.ads.admin.rejected_reason(ad) returns that original text, proving no
      #    read-time rewriting was added.
      # 5. not truncated: a clean reason longer than 100 characters is stored in full.
      #    This is the regression the plan's open question was about.
acceptance_criteria:
  - "a reason containing a phone number and an e-mail address stores neither, for each of log_manual_reject, log_ban_account, log_soft_delete and log_photo_removed"
  - "a clean reason and each of the three fixed literals are stored byte-identical"
  - "a clean reason longer than 100 characters is stored in full - nothing is truncated"
  - "redaction is idempotent: an already-redacted reason is not corrupted and does not accumulate asterisks"
  - "a row written before the change keeps its original text in the database and in apps.ads.admin.rejected_reason"
  - "redaction happens before the INSERT - there is no render-time or read-time filter anywhere"
  - "redact_search_query, _MAX_QUERY_LENGTH, mask_telegram_id, sanitize_query_for_log and sanitize_autocomplete_query are byte-unchanged"
  - "apps/moderation/admin_actions.py, apps/ads/admin.py and apps/users/services/pii_inventory.py are byte-unchanged"
  - "no migration was added and makemigrations --check is clean"
  - "the reason help_text states that contact details are masked at write time and irreversibly"
  - "technical-specification.md section A records the rule and sections F and K are byte-identical to before"
  - "on_delete, the permission predicates and the INTERNAL ONLY contract are unchanged"
tests_required:
  - id: every_free_text_writer_is_redacted
    assertion: >
      A reason carrying a phone number and an e-mail address reaches the database with
      neither present, driven separately through log_manual_reject, log_ban_account,
      log_soft_delete and log_photo_removed. Assert on the value read back from the stored row. Use an e-mail
      with a local part longer than two characters, because _mask_email preserves a
      local part of two or fewer characters and would let the test pass for the wrong
      reason. This is the test that proves the chokepoint holds for the next writer.
  - id: clean_text_is_byte_identical
    assertion: >
      A reason with no phone, no e-mail and no two-or-more consecutive capitalised words
      is stored exactly as supplied, and so are the three fixed literals "Auto-moderation
      failed", "Auto-published" and "Manually published by moderator". The negative case
      matters as much as the positive one: an unconditional rewrite that reformats clean
      moderator text would be a regression.
  - id: redaction_is_idempotent
    assertion: >
      Assert redact_free_text(redact_free_text(x)) == redact_free_text(x), or the
      equivalent stored-value property. Assert the PROPERTY - never an expected masked
      string, which would pin the placeholder format and turn a tuning change into a
      red test.
  - id: no_backfill_and_no_read_time_rewriting
    assertion: >
      A row inserted directly through ModeratorActionLog.objects.create before the write
      still holds its original text when re-read, and apps.ads.admin.rejected_reason(ad)
      returns that original text.
  - id: not_truncated
    assertion: >
      A clean reason longer than 100 characters is stored in full. This is the
      regression that would follow if redact_search_query were used instead of a
      non-truncating sibling.
  - id: regression
    assertion: >
      src/backend/apps/moderation/tests/test_moderation_side_effects.py stays green
      unchanged - it already asserts stored reasons - as does the phase-03 tripwire
      test_bulk_ban_users_not_locked in test_admin_actions.py, and
      src/backend/apps/core/tests/test_sanitize.py's full redaction matrix.
tests_to_run:
  - "src/backend/apps/moderation/tests/test_moderation_reason_redaction.py"
  - "src/backend/apps/moderation/tests/"
  - "src/backend/apps/users/tests/test_pii_inventory.py"
  - "src/backend/apps/core/tests/test_sanitize.py"
  - "src/backend/apps/core/tests/test_sweep_consent.py"
  - "src/backend/apps/core/tests/test_sweep_purge_rejected.py"
  - "src/backend/apps/analytics/tests/test_moderation_analytics.py"
commands:
  setup: "$dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'"
  test: "$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS=\"src/backend/apps/moderation/tests src/backend/apps/users/tests/test_pii_inventory.py src/backend/apps/core/tests/test_sanitize.py src/backend/apps/core/tests/test_sweep_consent.py src/backend/apps/core/tests/test_sweep_purge_rejected.py src/backend/apps/analytics/tests/test_moderation_analytics.py --tb=short\" test"
  lint: "uv run ruff check src/backend/apps/core/utils/sanitize.py src/backend/apps/moderation/"
  typecheck: "uv run basedpyright src/backend/apps/core/utils/sanitize.py src/backend/apps/moderation/"
  migrations: "uv run python src/backend/manage.py makemigrations --check --dry-run"
  notes: >
    Every path in tests_to_run was verified to exist in the tree. PYTEST_OPTS is
    unquoted in docker/entrypoint-test.sh, so each token is word-split on spaces and
    setting it REPLACES the default pytest args (--reuse-db --tb=short --durations=10
    -n auto --maxprocesses=4 --dist loadgroup); a targeted run loses xdist parallelism
    and DB reuse. Never use --override-ini=addopts=, which strips --import-mode=importlib.
    If the gate goes red with a mass ForeignKeyViolation on auth_permission /
    django_content_type, or FATAL: database "test_mko_bazuna" does not exist, or an
    "assert not self._finalizers" cascade at fixture setup, another agent is running the
    same database: confirm nothing else is in flight, re-run alone, and only then treat
    it as a defect.
commit:
  message: "fix(moderation): redact moderator free text at write time (06-PII-114)"
  stage:
    - "src/backend/apps/core/utils/sanitize.py"
    - "src/backend/apps/moderation/services/moderation_log.py"
    - "src/backend/apps/moderation/models.py"
    - "src/backend/apps/moderation/tests/test_moderation_reason_redaction.py"
    - "docs/01-spec/technical-specification.md"
  body_notes:
     - "Name the four redacted write sites (log_manual_reject, log_ban_account, log_soft_delete
       and log_photo_removed — the last already redacted by BLOCK 10) and state that they are the
       only production ModeratorActionLog writers in the repository."
    - "State that redact_search_query was rejected for this column because it truncates to _MAX_QUERY_LENGTH = 100, and that redact_free_text is additive so redact_search_query and _MAX_QUERY_LENGTH are unchanged."
    - "State that redaction is irreversible and applies to new writes only: rows written before this commit keep their original text, and no backfill is proposed."
    - "Record the residue - set_moderation_failed's `reason` parameter is dead (declared, never used) and was deliberately left alone as a pre-existing bug out of scope."
    - "Note that the name mask also masks title-case prose, and that the help_text says so."
extra_context: |
  BINDING CONSTRAINTS — verbatim, not to be summarised.

  1. Redaction happens at write time, inside the four
     ModeratorActionLog.objects.create(...) calls in
     apps/moderation/services/moderation_log.py. No render-time or read-time filter
     anywhere — apps/ads/admin.py::rejected_reason must not be touched.
  2. redact_search_query must not be called on `reason`. It truncates to
     _MAX_QUERY_LENGTH = 100 and would silently discard the moderator's text. Add and
     call the non-truncating sibling redact_free_text.
  3. New writes only. No migration, no data migration, no backfill, no read-time
     rewriting. Rows written before this change keep their original text.
  4. Clean text must pass through unchanged. redact_free_text returns text containing no
     phone, no e-mail and no two-or-more-consecutive-capitalised-words sequence
     byte-for-byte identical to the input. The three fixed literals ("Auto-moderation
     failed", "Auto-published", "Manually published by moderator") must be asserted
     byte-identical, and the three create sites that use them are NOT edited.
  5. redact_free_text is additive. Do not modify redact_search_query, _MAX_QUERY_LENGTH,
     mask_telegram_id, sanitize_query_for_log or sanitize_autocomplete_query, and do not
     edit apps/core/tests/test_sanitize.py (phase 06 BLOCK 4 and phase 08 BLOCKS 3/4 own
     them).
  6. Do not change on_delete, the permission predicates, the "INTERNAL ONLY" contract, or
     set_moderation_failed's dead `reason` parameter. Only the stored value of `reason`
     changes.
  7. apps/moderation/admin_actions.py is contended by phases 03, 04, 05 and 10. This block
     does not edit it. If a change there appears necessary, stop and report it rather than
     making it.
  8. No user-visible string. No .po change, no makemessages, no compilemessages, no
     djlint. help_text stays a plain literal — do NOT wrap it in gettext_lazy.
  9. No migration. help_text is not a database column, so nothing in
     apps/moderation/migrations/ changes and docs/02-database/db-schema.md needs no edit.
 10. Do NOT edit src/backend/apps/users/services/pii_inventory.py. Its
     moderation.ModeratorActionLog.reason entry is ErasureAction.RETAIN and stays
     RETAIN; a write-time rule there is the category error BLOCK 3's reason names.
 11. Tests are Docker-only. PYTEST_OPTS is unquoted in docker/entrypoint-test.sh and
     REPLACES the pytest defaults; never use --override-ini=addopts=. A mass
     ForeignKeyViolation on auth_permission/django_content_type, a FATAL: database
     "test_mko_bazuna" does not exist, or an "assert not self._finalizers" cascade at
     fixture setup is a concurrent-run teardown artefact (VAL-010) — confirm no other run
     is in flight, re-run alone, and only then report it as a defect.

  FACTS ESTABLISHED BY THE PLANNER — verified against the tree, do not re-derive and
  do not contradict:

  - `Ad` has NO `rejected_reason` column. apps/ads/admin.py::rejected_reason is a
    render-time display helper in AdAdmin.list_display that reads
    obj.moderation_logs.filter(action_type=REJECT).last() and returns log.reason[:100].
    Any target naming `Ad.rejected_reason` is a defect.
  - All SEVEN production ModeratorActionLog.objects.create sites are in
    moderation_log.py. The other four occurrences in src/ are in test code. There is no
    admin write path: ModeratorActionLogAdmin returns False from has_add_permission,
    has_change_permission and has_delete_permission.
  - Four writers take free text (log_manual_reject, log_ban_account, log_soft_delete,
    log_photo_removed — added in BLOCK 10); three pass fixed literals (log_auto_fail,
    log_auto_publish, log_manual_publish).
  - redact_search_query never lengthens its input: measured over 200000 randomised
    PII-heavy strings and a systematic token-pair sweep, the maximum positive length
    delta was 0. It CAN shorten by one character when a masked multi-word name contains a
    multi-character whitespace run, because _mask_name rejoins words with a single space.
  - redact_search_query DOES truncate to 100 characters, which is why it is not used here.
  - The three patterns and three masks are module-private to
    apps/core/utils/sanitize.py. Reusing them from a new function IN THAT MODULE is not a
    private-name violation. Do NOT copy the regexes into the moderation app: two copies
    of security logic drift, and the silent drift leaks.
  - redact_free_text is idempotent, and structurally so: each mask leaves a run of "*",
    "*" is in none of the three character classes, so a second pass cannot match.
  - The e-mail mask preserves a local part of two or fewer characters, so "a@b.co" is
    left untouched by design. Tests must use a realistic local part.
  - The review view composes "<category>: <text>", and every CategoryRejectReason value
    is snake_case ("spam_scam"), so the category prefix is unaffected by the name mask.
```

**Tests required**

1. **Every free-text writer is covered** — a reason containing a phone number and an
   e-mail address reaches the database with neither present, driven separately through
   **each** of `log_manual_reject`, `log_ban_account`, `log_soft_delete` and
   `log_photo_removed`. A test that covers one writer proves nothing about the
   chokepoint; this one is what proves the rule survives the next writer being added.
2. **Clean text is stored byte-identical** — a reason with no phone, no e-mail and no
   consecutive capitalised words is stored exactly as given, and the three fixed literals
   are asserted byte-identical. An unconditional rewrite that reformats legitimate audit
   content is a regression.
3. **Applied once, not twice** — redaction is idempotent: an already-redacted reason is
   unchanged by a second pass and the stored value does not accumulate asterisks. Assert
   the property, never an expected masked string, which would pin the placeholder format.
4. **Existing rows are untouched** — a row written directly through the manager before the
   change keeps its original text when re-read, and `apps.ads.admin.rejected_reason(ad)`
   returns that original text. That is the no-backfill, no-read-time-rewriting guarantee.
5. **Not truncated** — a clean reason longer than 100 characters is stored in full. This is
   the regression that follows if `redact_search_query` is used instead of a
   non-truncating sibling, and the plan's original open question.

**Risk and rollback**

- *Risk:* the `_NAME_PATTERN` masks title-case prose, so a moderator writing in title case
  sees masked words. Measured and stated rather than discovered; mitigation is binding
  constraint 4 plus the amended `help_text`.
- *Risk:* `apps/core/utils/sanitize.py` is contended by phase 06 BLOCK 4 and phase 08
  BLOCKS 3/4. Mitigation: §5.3, and binding constraint 5 keeps the change additive.
- *Risk (analytics):* `get_rejection_reasons` buckets by the stored text, so the
  rejection-reason breakdown keys change for redacted rows. Expected; the category prefix
  is unaffected.
- *Rollback:* a straight revert. Already-written rows keep their **redacted** values and
  cannot be restored — redaction is irreversible and there is no inverse. Rows written
  before the change keep their original text. State both residues in the commit body.
- *No backfill, no migration, no display-side change.* Nothing outside the write path
  moves, so the rollback is the revert.

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

### BLOCK 18 — Record **who** acted: the actor column and the mechanism on `ConsentRecord` (`06-NEW-02`)

| | |
|---|---|
| **Findings owned** | `06-NEW-02` |
| **Depends on** | **nothing in this plan.** BLOCKS 10, 12 and 15 are all landed and are **read**, not reopened |
| **Blocks** | nothing |
| **Priority** | P2 — an owned follow-up to a record that was orphaned, not a new remediation |
| **Risk level** | **MEDIUM** — a schema change on the audit ledger, plus a fifth edit to `withdraw_consent` |
| **Required agents** | **Implementor · Validator.** §1.6 requires a Validator for any block whose acceptance turns on a decision the Implementor was told not to make, and the actor-retention bound below is exactly that |

**The owner ruling (2026-10-04) — implement against this; do not reopen it.** `06-NEW-02` is
reopened as an owned Phase-06 follow-up. **BLOCKS 12 and 15 are NOT reopened.** It was previously
routed to "BLOCK 12/15" and both closed without it, leaving it orphaned.

**The reason it is not cosmetic.** `ConsentRecord` cannot distinguish *subject withdrew / staff
revoked / system revoked*. The **audit meaning** of the record is incomplete. That is a data-model
and accountability defect, so it needs its own owner and follow-up. The shape the owner named: an
**actor / `revoked_by`** plus a **clear definition of who counts as the actor of the action**.

**What already exists — verified against the tree at planning time, not assumed.**

- `ConsentRecord` (`src/backend/apps/users/models.py`) fields: `user` (FK `users.User`, `SET_NULL`,
  nullable — the **subject**), `session_key`, `consent_given_at`, `consent_version`, `choice`
  (`ConsentChoice` StrEnum), `categories` (JSONField), `ip_address`, `user_agent`.
  **No actor column.**
- `apps/users/migrations/` is at **`0004_consentrecord_sweep_index`** → this block's migration is
  **`0005`**. `apps/core/migrations/` is at `0006_supportticket_user_cascade` (untouched here).
- BLOCK 10 (`749bbfc`) added `record_consent_action_with_context(user, choice, categories, *,
  ip_address, user_agent, session_key, consent_version)` — **no `HttpRequest`** — and it is the
  function `withdraw_consent` calls inside its existing `atomic()`.
  `record_consent_action(user, choice, categories, request=None, consent_version=…)` keeps its
  signature and delegates.
- `withdraw_consent` in `apps/users/services/deletion.py` has **four** landed writers — BLOCK 9
  `474a68d` (body + `atomic()`), BLOCK 13 `6631ff3` (`SupportTicket` deletion), BLOCK 8 `8dba351`,
  BLOCK 10 `749bbfc` (the audit write, **last** inside the block) — and now takes three
  keyword-only params. **This block is the FIFTH writer.** Re-read `deletion.py` immediately
  before editing; the ordering rule is in §BLOCK 18 below.
- `UserAdmin.withdraw_consent_action` (`apps/users/admin.py`) is the **superuser-gated** admin
  action (BLOCK 10), `@admin.action(permissions=["delete"])`, iterating a `queryset` of `User`s and
  calling `withdraw_consent(account)` **bare**. **This is the path that currently produces a
  "subject withdrew" record for what is actually a staff revocation** — the exact ambiguity.
- BLOCK 15 (`fd5201d`) added `apps/core/management/commands/purge_consent_records.py` under
  **advisory lock 14**, anonymising — **never deleting** — rows past the 90-day fingerprint window:
  `user=NULL`, `session_key=NULL`, `ip_address=NULL`, `user_agent=""` in **one** statement. The
  decision fields follow the event retention period (a policy decision justified by purpose —
  see "Retention framing correction (owner ruling 2026-10-04)"), and BLOCK 19 (06-NEW-02) adds a
  third, separate window that anonymises the actor field 12 months from the action, subject to a
  documented legal hold.
  **Verified: the sweep writes no `ConsentRecord`.** It only `.update()`s existing rows
  (`purge_consent_records.py` is the only command that names `ConsentRecord`; `consent_hard_delete`
  names `User`, `AnalyticsEvent`, `ModeratorActionLog`, `SupportTicket`).
- **Verified: there is no Telegram-bot caller.** A repo-wide search for `record_consent_action`
  returns hits only in `apps/users/views/consent.py` (2), `apps/users/services/deletion.py` (1),
  `apps/users/services/consent_record.py` (definitions) and three test files. The module docstring's
  *"e.g. from the Telegram bot /start entry point"* is **aspirational** — that path does not exist.
  Do not build a writer for it.
- `apps/users/services/pii_inventory.py` declares `users.ConsentRecord` entries; its guard
  (`apps/users/tests/test_pii_inventory.py::test_listed_models_have_no_unreviewed_column`) walks each
  listed model's **concrete, non-relational, non-timestamp** columns and fails if one has neither an
  erasure entry nor a reviewed decision. **What the new columns do to that guard is worked out
  below, exactly.**

#### 1. The column design, and the actor definition — which is the substance

**Decision: BOTH columns.** They answer different questions and neither substitutes for the other.

| Column | Answers | Type |
|---|---|---|
| `initiated_by` | **Who** — the account that performed the action | FK → `users.User`, `null=True`, `blank=True`, `on_delete=SET_NULL`, `related_name="+"` |
| `action_source` | **By what mechanism** — the closed vocabulary of *how* the action was initiated | `CharField(max_length=20, choices=[…ConsentActionSource…], default=ConsentActionSource.UNKNOWN.value, blank=True, db_index=True)` |

**A system-initiated action has no `User` actor, so the FK alone cannot express "system revoked" —
one of the three cases the owner named.** That is the whole argument for the enum, and it is the
reason the two columns are not interchangeable.

**The actor definition, stated once so it can be cited from three places** (the model docstring, the
writer docstring and `docs/02-database/db-schema.md`):

> **The actor is the account that performed the action, and it is recorded only when that account is
> NOT the subject.** `user` already names the subject, so a self-action would store the same account
> twice. `initiated_by` therefore holds an account **only** for a third-party action; the invariant
> is `initiated_by IS NOT NULL ⟹ initiated_by is a different row from user`. Read the pair, never
> one column alone: `action_source` is authoritative for *which case* the row is, `initiated_by`
> names the account when one exists. A null `initiated_by` means **"no acting account distinct from
> the subject"** — which covers a self-service action, an anonymous visitor and a system action, and
> `action_source` is what tells those three apart.

**Why the subject's own action leaves `initiated_by` null rather than populating it with the
subject.** Two reasons, the second is decisive:

1. *Semantics.* Populating it would make the column uniform, at the cost of storing the subject's
   link twice. Uniformity is bought with a redundant copy of the very link the ledger is supposed to
   bound.
2. *The sweep.* BLOCK 15 clears `user_id` at 90 days precisely so an aged decision cannot be walked
   back to a person. If a self-service row also carried `initiated_by = <subject>`, that copy would
   **survive the clear** and become the only remaining link from an anonymous decision to a live
   account — re-opening, from inside this block, the exact re-identification path BLOCK 15 exists to
   close. Populating the subject would force a second, conditional statement into BLOCK 15's sweep.
   Leaving it null makes the design need **zero** change to BLOCK 15's command and **zero** change
   to BLOCK 15's tests.

**All four cases, as stored.** `U` = subject, `S` = acting staff account, `—` = `NULL`.

| Case | `user` (subject) | `initiated_by` | `action_source` | How it is written |
|---|---|---|---|---|
| **Subject withdrew / accepted / declined** (authenticated web) | `U` | `—` | `self_service` | `record_consent_action` derives it from `user is None`; `withdraw_consent`'s default |
| **Anonymous visitor accepted / declined** (no account at all) | `—` | `—` | `anonymous_web` | derived from `user is None` in `record_consent_action` |
| **Staff revoked** (admin changelist action) | `V` (target) | **`S`** | `admin_staff` | `UserAdmin.withdraw_consent_action` passes `initiated_by=request.user` |
| **System** (automated, non-human) | `V` | `—` | `system` | **no live writer today** — see the residual note below |
| **Row predating this block** | unchanged | `—` | `unknown` | the `AddField` default |

**The `system` member is required by the ruling, not by a caller.** No production path writes it
today (verified above: no bot caller, no system writer; the sweep writes no rows). It exists because
the owner named "system revoked" as one of the three cases that must be distinguishable, and because a
**closed** vocabulary is what stops a future writer from inventing a fourth spelling. The
audit-meaning test must prove the case is **storable and distinguishable** by driving the real writer
with an explicit `ConsentActionSource.SYSTEM`, while recording plainly that no production path emits
it.

**The anonymous case — the awkward one, and how it is represented.** An anonymous visitor has no
account, so there is nothing to put in an actor column and nothing to infer. It is represented
**positively, not by a null**: `action_source = anonymous_web` states the mechanism outright, and the
row is still attributable through `session_key`, which BLOCK 8's guard already guarantees is
non-null on this path. So "no account acted" is a **recorded fact**, not a gap a reader has to infer
from three nulls. The anonymous row is distinguishable from a system row with no subject
(`anonymous_web` vs `system`) and from a self-service row (`user` null vs set) with no join.

**Retention interaction — the hard part. Recommendation, and it needs owner/DPO sign-off.**

- The **self-attributed** case records **nothing** in `initiated_by`, so there is no subject-side
  actor to bound. BLOCK 15 needs **no change**: the actor column is never named in the sweep's
  `.update(...)`, so it is untouched, and it holds nothing that points at the subject.
- The **staff-attributed** case is accountability data about a **third party** — an employee — not
  about the subject. **SUPERSEDED POSITION (recorded, not deleted):** this block originally
  recommended retaining the actor "to the decision bound (5 years); do NOT clear it at the
  90-day fingerprint window", reasoning that the row exists as Art. 7(1) evidence so stripping
  *who* at 90 days while keeping *what* re-creates the incompleteness. **The owner ruled on
  2026-10-04 that this recommendation is withdrawn**, and BLOCK 19 replaced it: the actor field is
  **irreversibly anonymised 12 months from the action, subject to a documented legal hold.** The
  reasoning that is *retained* is the part that still holds — the actor column is not a
  re-identification path **for the subject** (the surviving link points at the operator, not at the
  erased data subject, and a reader who knows "S revoked V" already knows V), and the row is
  retained so accountability survives at all.
- **The counter-argument, stated because it is real — and it is why the 12-month bound exists:** a
  superuser identifier retained indefinitely on consent rows is itself personal data about an
  employee, and it yields a durable per-operator behavioural record (*which operator revoked whose
  consent, and how often*) that the product does not otherwise have and has not declared, with **no
  erasure path** — an employee who leaves cannot have it cleared, because clearing it is exactly
  what destroys the accountability. Data minimisation and accountability pull in opposite directions
  here. **The 12-month bound resolves that tension by putting an end to it**, and it does so as a
  **chosen minimisation period justified by purpose, not as a statutory term.**
- **This block no longer defers the bound.** It originally shipped with the retention recommendation
  implemented and the *bound* flagged as an owner/DPO decision the Implementor must not settle, on
  the reasoning that the reversal would be one cheap line. **That flag is discharged: the owner has
  now ruled (2026-10-04), and BLOCK 19 implements the ruled bound.** The implementor of this block
  must not re-raise it.
  *Constraint that makes the recommendation safe to ship now:* the population is bounded to
  superusers (`permissions=["delete"]` dispatches to `UserAdmin.has_delete_permission`, which is
  `request.user.is_superuser`) and the event is rare, so the exposure is small while the decision is
  open.

**`SET_NULL`, never `CASCADE`.** Verified what `User` deletion does today: `consent_hard_delete`
runs `User.objects.filter(consent_revoked_at__lt=cutoff).delete()` (a real collector delete, 30 days
after withdrawal) and `apps/seed/services/seed_service.py` runs
`User.objects.filter(source=AdSource.SEED).delete()`. A `CASCADE` actor FK would therefore **delete
`ConsentRecord` rows** through the collector when a staff account is removed — destroying Art. 7(1)
evidence. `SET_NULL` nulls the pointer and leaves the row, which is the behaviour
`ConsentRecord.user` already relies on. `related_name="+"` avoids adding a second reverse accessor on
`User` alongside `consent_records`.

#### 2. The write paths that must populate it — established from the code, not assumed

| Caller (verified) | Case | `user` (subject) | `initiated_by` | `action_source` | Change needed |
|---|---|---|---|---|---|
| `consent_accept`, authenticated (`views/consent.py`) | self-service | `U` | `—` | `self_service` | **none** — derived |
| `consent_accept`, anonymous | anonymous visitor | `—` | `—` | `anonymous_web` | **none** — derived |
| `consent_decline`, authenticated | self-service | `U` | `—` | `self_service` | **none** — derived |
| `consent_decline`, anonymous | anonymous visitor | `—` | `—` | `anonymous_web` | **none** — derived |
| `consent_withdraw` → `withdraw_consent` | self-service | `U` | `—` | `self_service` | **none** — `withdraw_consent`'s default |
| `UserAdmin.withdraw_consent_action` | **staff** | `V` | **`S`** | **`admin_staff`** | **THE FIX** — pass both |
| `purge_consent_records` (BLOCK 15) | **writes no records** | — | — | — | **none** (verified) |
| `consent_hard_delete` | **writes no records** | — | — | — | **none** (verified) |
| Telegram bot `/start` | **no caller exists** | — | — | — | **none** (verified) |
| any future automated path | system | `V` | `—` | `system` | pass `action_source` explicitly |

**Signature changes — three, in dependency order.**

1. **`record_consent_action_with_context(user, choice, categories, *, ip_address=None,
   user_agent=None, session_key=None, consent_version=…, action_source: ConsentActionSource,
   initiated_by: User | None = None)`** — `action_source` is **required keyword-only, no default**,
   so a new caller cannot forget to classify itself. `initiated_by` defaults to `None`. The actor
   normalisation described in §1 lives **here**, in the one insertion path, next to the existing
   `_anonymize_ip` sanitisation, so a future writer cannot bypass it.
2. **`record_consent_action(user, choice, categories, request=None, consent_version=…,
   *, action_source: ConsentActionSource | None = None)`** — one **optional** keyword-only
   parameter, defaulting to `None`, which resolves to `ANONYMOUS_WEB` when `user is None` and
   `SELF_SERVICE` otherwise. **The frozen signature is preserved**: the four-argument positional
   shape, the `request=None` default, the `consent_version` default and the delegation all stand, so
   **every existing call site keeps working byte-for-byte** — `consent_accept`, `consent_decline`
   (BLOCK 8's surface, deliberately **not** edited), and the three test modules. The derivation is
   correct *because* the only callers of this function are the two self-service web views; it is
   documented in the docstring, and the explicit override exists for the first caller that is not
   one. **BLOCK 8 and BLOCK 10 both relied on that freeze — it is not broken here.**
3. **`withdraw_consent(user, *, ip_address=None, user_agent=None, session_key=None,
   action_source=ConsentActionSource.SELF_SERVICE, initiated_by: User | None = None)`** — two
   keyword-only params **appended after `session_key`**. Both are defaulted, so the six existing bare
   `withdraw_consent(user)` call sites in `apps/users/tests/test_deletion.py` keep working and keep
   meaning *"the subject withdrew"*, which is the correct reading of a bare domain call. The default
   is stated in the docstring as a **contract with a warning**: the default is `SELF_SERVICE` because
   the only non-staff caller is the subject's own web withdrawal; **any third-party initiator MUST
   pass `ADMIN_STAFF`.**

**Ordering rule for `withdraw_consent` — this block is the FIFTH writer. Re-read
`apps/users/services/deletion.py` immediately before editing and assert this before writing:**

1. Do **not** reorder, move or remove the existing `record_consent_action_with_context(...)` call.
   It stays **last** inside `transaction.atomic()`, after `SupportTicket.objects.filter(...).delete()`
   and `soft_delete_user_ads(user)`. BLOCK 10's rollback guarantee is load-bearing: a raise from
   `soft_delete_user_ads` (exercised by `test_withdraw_is_atomic_rollback`) must roll the audit row
   back, and that only holds because the write is last.
2. Do **not** open, move or close the `atomic()` block, and do **not** add a second transaction.
3. Extend the **signature only** — append the two keyword-only parameters after `session_key` — and
   forward them on the existing call, adding **no** statement to the body.
4. If the file's docstring no longer matches the code you found (another writer landed between
   planning and execution), **stop and report** rather than layering on top.

**Documented residual, NOT actioned here.** Two pre-existing facts this block touches but must not
change: (a) the admin-initiated row still carries **no** `ip_address` and **no** `user_agent` — the
admin request *is* available and could supply them, but that is BLOCK 10's shipped behaviour and its
test, and the ruling scoped this block to actor/mechanism; (b) `record_consent_action`'s
`request is None` branch drops `consent_version` when delegating — a pre-existing defect, out of
scope here, but that line **must** be edited to forward `action_source`, so record it in the commit
body rather than fixing it silently. Both residuals go in the new docstrings.

#### 3. The audit-meaning test

The owner's complaint is that the record's **meaning** is incomplete, so the test asserts on values
**re-read from the database**, never on a settings or source check, and never on a symbol's presence.

1. **Self-service vs staff are distinguishable from stored values alone.** Drive a subject's own
   withdrawal and a superuser's changelist revocation of a *different* subject. Re-read both rows:
   the self-service row names the subject and records the self-service mechanism with **no separate
   acting account**; the staff row names the target as the subject, names the **superuser** as the
   acting account, and records the staff mechanism. The staff row must **not** read as a subject
   withdrawal.
2. **System is distinguishable.** Drive the real recording service with an explicit
   `ConsentActionSource.SYSTEM`; the re-read row carries no acting account and the system mechanism,
   and differs from both rows above on stored values with no join.
3. **The anonymous case is positively represented.** POST the consent form with no authenticated
   user; the re-read row has no subject, no acting account, the anonymous mechanism, **and a
   non-null session key** — so "an unidentified visitor acted" is recorded, and the row remains
   attributable without an account. Add the control: that row differs from the system row and from
   the authenticated rows on stored values.
4. **No live writer leaves the unknown mechanism.** Assert the mechanism of a row written through
   each of the three real write paths is a *specific* member, never the unknown default. This is the
   tripwire that keeps a future fourth writer from silently landing in the legacy bucket.
5. **The ledger survives the actor's account deletion.** Create a staff-revocation row, delete the
   acting staff user's row the way `consent_hard_delete` does, and assert the `ConsentRecord` still
   exists, its subject and decision fields are intact, and only the acting-account pointer reads
   empty. Add the control: a self-attributed subject's own hard delete leaves its consent rows too.
6. **The sweep behaves per the retention decision.** Age a staff-revocation row past the fingerprint
   window and run the real command: subject, session key, IP and user agent are cleared, **the row
   still exists**, and **the acting staff account is still readable on it**. Add the control: an aged
   self-service row has no acting account to preserve.
7. **A superuser cannot forge accountability.** Through the admin change form, an attempt to alter an
   existing row's acting account or mechanism does not change either value on re-read, and the
   changelist can be filtered by mechanism.
8. **Legacy rows read honestly.** A row that predates this change carries the unknown mechanism and
   no acting account, and is therefore distinguishable from every row written after it — while
   **no** row written through the recording service carries the unknown mechanism.

#### 4. The migration

`apps/users/migrations/` is at `0004_consentrecord_sweep_index` → this migration is
**`0005_consentrecord_initiated_by_action_source.py`**. Generate with `makemigrations` (no
hand-written DDL); verify the directory immediately before generating — other blocks have landed
migrations in this app.

- `AddField` `ConsentRecord.initiated_by`: `null=True`, `blank=True`,
  `on_delete=models.SET_NULL`, `related_name="+"`.
- `AddField` `ConsentRecord.action_source`: the choices list, the `ConsentActionSource.UNKNOWN.value`
  default, `blank=True`, `db_index=True`.
- **No data migration, no `RunPython`, no backfill.** There is nothing to backfill: the ledger never
  recorded the actor or the mechanism, so no value can be *derived* for an existing row. Inferring
  "no IP and no user agent therefore staff" would be a guess, and it would be **wrong** for every
  bot- or command-written row. **Record the gap honestly instead.**
- **What existing rows then mean.** `AddField` writes the field default to every existing row, so
  every pre-existing row reads `action_source = "unknown"` with `initiated_by = NULL`.
  **The reading convention, to be written into the field `help_text`, the model docstring and
  `db-schema.md`:** the unknown mechanism means *"this row was written before the actor was recorded;
  the mechanism was never captured and is not recoverable"*. On such a row a null `initiated_by`
  carries **no** inference at all about who acted — including for rows that were in fact staff
  revocations, which is precisely the ambiguity this block stops creating from the day it lands and
  cannot repair retroactively.
- **Reversibility: yes.** Both operations are `AddField` on nullable/defaulted columns, so
  `migrate users 0004` reverses cleanly. The reversal is **lossy**: it destroys every actor and
  mechanism value the block wrote, and re-applying re-stamps pre-existing rows as unknown. Say so in
  the commit body.

**`ConsentRecordAdmin`, respecting the two owners.** BLOCK 12 owns `list_display` and `search_fields`;
BLOCK 15 owns the TTL and the `session_key` scope. Therefore:

- **`readonly_fields`: both new fields MUST be added.** `ConsentRecordAdmin` declares no `fieldsets`,
  so Django auto-builds the change form from the editable fields — adding the two columns without
  adding them here would make the **actor and the mechanism writable by a superuser**, i.e. forgeable
  accountability evidence. This is the one admin edit that is mandatory rather than discretionary.
- **`list_filter`: add `action_source`.** Low-cardinality closed vocabulary, exposes no identity, and
  it is how an auditor separates the three cases on the changelist. `list_filter` is owned by neither
  BLOCK 12 nor BLOCK 15.
- **`list_display` and `search_fields`: leave byte-identical.** They are BLOCK 12's, and BLOCK 15's
  residual note about `session_key` still living in `search_fields` is BLOCK 15's to close.

#### 5. The inventory interaction

**Must change in `apps/users/services/pii_inventory.py`:**

- **One new erasure entry** for `("users.ConsentRecord", "initiated_by", ErasureAction.RETAIN, …)`.
  `RETAIN`, not `NULL`: no erasure path nulls it, and declaring `NULL` would describe a scrub that
  does not happen. The **reason string names BLOCK 18 and cites `06-NEW-02`**, and must state the
  three facts a reader needs: the column never holds the subject (the `user` link is the subject's);
  it is retained to the decision bound, not the fingerprint bound, because clearing it would destroy
  the accountability the owner asked for; and it is emptied only by `SET_NULL` when the **acting
  account's own** row is hard-deleted. Declaring it at all is the point — a staff-identifier
  retention decision with no declaration is exactly the invisible omission this inventory exists to
  prevent (cf. the `User.password` entry).
- **One reviewed-non-identity decision:** add `"action_source"` to
  `REVIEWED_NON_IDENTITY_COLUMNS["users.ConsentRecord"]`. The guard's `_is_review_candidate` skips
  relational fields, so a **non-relational** column like this one is **not** skipped and turns the
  guard red until it is decided. It is a closed mechanism vocabulary carrying no personal data.
  A `REVIEWED_NON_IDENTITY_COLUMNS` entry is a bare name with **no reason field**, so the reason goes
  in the module docstring — extend its "look-alike columns are deliberately excluded" list with
  `ConsentRecord.action_source` and the `06-NEW-02` citation.
- **One minimal docstring amendment.** The module docstring currently states that relational fields
  "are excluded by the guard's own field filter and are **not recorded here**". A declared relational
  entry contradicts that sentence. Amend **only that clause** to say relational fields are skipped
  *by the guard* but **may** be declared to record an accountability-retention decision. Change
  nothing else in the docstring.

**What must NOT change in the inventory:** `ErasureAction`, the 4-tuple shape, all existing entries,
`REVIEWED_NON_IDENTITY_COLUMNS` for every other model, the lazy-string import boundary, and the
stdlib-only import rule — `test_importing_the_declaration_pulls_in_no_apps_model` wraps
`builtins.__import__` and fails on **any** `apps.*` request, so importing `ConsentActionSource` at
module scope from `apps.core.enums` would be a violation. Import the enum **inside the reason-string
construction path only if unavoidable**; the clean answer is to write the reason as a plain string and
not import the enum at all.

**Must change in `apps/users/tests/test_pii_inventory.py`:** one new test asserting the actor entry is
declared, is `RETAIN`, and its reason cites `06-NEW-02` and names BLOCK 18; and that
`action_source` is in the reviewed set for `users.ConsentRecord`. The **positive** pin matters:
`test_listed_models_have_no_unreviewed_column` already fails if the reviewed decision is *missing*,
but nothing stops a later hand from deleting it.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/core/enums.py` | new `ConsentActionSource` StrEnum next to `ConsentChoice`; add to `__all__` | Rule 10. Five members, `UNKNOWN` is the default |
| `src/backend/apps/users/models.py` | `ConsentRecord` — add the two fields + rewrite the docstring's actor definition | `user`'s existing `help_text` says "User who acted" — correct it to name the **subject** |
| `src/backend/apps/users/migrations/0005_consentrecord_initiated_by_action_source.py` | **new** — two `AddField`s | Verify the directory immediately before generating |
| `src/backend/apps/users/services/consent_record.py` | `record_consent_action`, `record_consent_action_with_context` | Actor normalisation goes in the `_with_context` writer |
| `src/backend/apps/users/services/deletion.py` | `withdraw_consent` — signature only | **Fifth writer.** Re-read first; audit write stays last in the block |
| `src/backend/apps/users/admin.py` | `UserAdmin.withdraw_consent_action`; `ConsentRecordAdmin.readonly_fields` / `list_filter` | Fix the staff path; rewrite the two stale "Limitation (`06-NEW-02`)" docstring paragraphs |
| `src/backend/apps/users/services/pii_inventory.py` | `PII_ERASURE_ENTRIES`, `REVIEWED_NON_IDENTITY_COLUMNS`, module docstring | See §5 |
| `src/backend/apps/users/tests/test_consent_actor.py` | **new** | The eight behavioural assertions of §3 |
| `src/backend/apps/users/tests/test_admin_consent_action.py` | `test_forged_post_as_superuser_withdraws_and_writes_one_record` | **Add** actor/mechanism assertions. **Keep** the existing "no HTTP context" assertions — still true |
| `src/backend/apps/users/tests/test_purge_consent_records.py` | new test for the actor-retention decision | **Production command unchanged** |
| `src/backend/apps/users/tests/test_pii_inventory.py` | one new declaration test | Existing tests unchanged |
| `docs/02-database/db-schema.md` | the `consent_records` column list; the "Known limitation — no actor column" paragraph | Rule 14 |
| `docs/02-database/db-enums.md` | new `ConsentActionSource` section | Rule 14 |
| `docs/99-agent/pii-consent-remediation-record.md` | the `06-NEW-02` "Open and unowned" row | Reassigned to BLOCK 18 by the ruling |

**Binding constraints**

1. **Re-read `apps/users/services/deletion.py` immediately before editing** and follow the fifth-writer
   ordering rule above. The `atomic()` boundary, the position of the audit write, and
   `test_withdraw_is_atomic_rollback`'s guarantee are all load-bearing and **unchanged**.
2. **`record_consent_action`'s frozen signature is preserved.** The new parameter is optional and
   keyword-only; `consent_accept`, `consent_decline` and every existing test call site keep working
   unchanged. **Do not edit `apps/users/views/consent.py`** — BLOCK 8 owns it and the derivation makes
   the edit unnecessary.
3. **`apps/core/management/commands/purge_consent_records.py` is NOT modified.** Not its windows, not
   its lock 14, not its one-statement clear, not its never-delete invariant, not its dry-run.
4. **`ConsentRecordAdmin.list_display` and `search_fields` are not touched** (BLOCK 12). BLOCK 15's
   `session_key` residual is BLOCK 15's to close.
5. **The actor-retention bound is OWNER-RULED, not the Implementor's to settle, and not open.**
   The original text of this constraint said *"Implement the 5-year recommendation, record the DPO
   question in the commit body, and do not silently choose 90 days."* **That is superseded.** The
   owner ruled on **2026-10-04**: the actor field is retained **12 months from the action and then
   irreversibly anonymised**, subject to a documented legal hold, as a **chosen minimisation period
   justified by purpose and explicitly not a statutory term**. BLOCK 19 implements it. An
   Implementor working this block must not implement the 5-year recommendation, must not treat the
   bound as open, and must not re-derive it from a limitation period.
6. **No `CASCADE`, ever.** `SET_NULL` on the actor FK; `consent_hard_delete`'s collector delete and
   `seed_service`'s bulk delete both pass through it.
7. **No data migration and no backfill.** The unknown mechanism is the honest reading of a
   pre-existing row.
8. **No `.po` / i18n change.** Model `help_text` and enum values are not a translatable surface (the
   gate scans templates; every other field on this model already carries English `help_text`), and no
   new user-visible string is introduced.
9. **`--create-db` is mandatory** — a migration lands (§1.1).
10. **`VAL-010` artefacts are contention, not defects.** Re-run a red gate serially before reporting it.

**Risk and rollback**

- *Risk:* the actor FK invites a future author to null-means-*nothing* reading. Mitigation: the
  invariant is written in three places (model docstring, writer docstring, `db-schema.md`) and pinned
  by the audit-meaning tests.
- *Risk:* a superuser forges accountability by editing the changelist row. Mitigation: both new
  fields in `readonly_fields`, pinned by acceptance criterion 7.
- *Rollback:* the migration reverses (lossy — actor and mechanism values are destroyed). Reverting
  the code without reversing the migration is also safe: the columns become unused.
- *Escalate, do not improvise,* if: the migration directory is not at `0004` when you generate;
  `deletion.py` no longer matches the shape this block was planned against; or a **new** writer of
  `record_consent_action*` or `withdraw_consent` appears that is not in the §2 table.

**Implementor task**

```yaml
id: task_06_b18_consent_actor
title: "Record who initiated each consent action and by what mechanism (06-NEW-02)"
priority: medium
depends_on: []
source_reference: ".ai/plans/06-pii-consent-remediation.md"
source_section: "BLOCK 18 - Record who acted: the actor column and the mechanism on ConsentRecord"
source_blocks: ["BLOCK 18"]
description: >
  ConsentRecord cannot distinguish "subject withdrew" from "staff revoked" from "system
  revoked", so the audit meaning of the ledger is incomplete (06-NEW-02, reopened by owner
  ruling 2026-10-04 as an owned follow-up; BLOCKS 12 and 15 are NOT reopened). Add a
  relational actor column plus a non-relational mechanism column, and populate them from
  every existing write path so the three cases are distinguishable in stored data.
goals:
  - "make subject-initiated, staff-initiated and system-initiated consent actions distinguishable from stored values alone"
  - "stop the admin revocation from reading as a subject withdrawal"
  - "keep the actor column out of BLOCK 15's fingerprint clear so the 90-day sweep's invariant is untouched"
  - "record the actor-retention bound honestly, including the open DPO question"
files:
  - path: "src/backend/apps/core/enums.py"
    targets:
      - type: class
        name: ConsentActionSource
      - type: module_attribute
        name: __all__
    semantic_anchors:
      insert_after:
        type: class
        value: ConsentChoice
  - path: "src/backend/apps/users/models.py"
    targets:
      - type: class
        name: ConsentRecord
    semantic_anchors:
      insert_after:
        type: field
        value: user_agent
  - path: "src/backend/apps/users/migrations/0005_consentrecord_initiated_by_action_source.py"
    targets:
      - type: migration
        name: "AddField initiated_by / AddField action_source"
  - path: "src/backend/apps/users/services/consent_record.py"
    targets:
      - type: function
        name: record_consent_action
      - type: function
        name: record_consent_action_with_context
    semantic_anchors:
      insert_before:
        type: return_statement
        value: "ConsentRecord.objects.create"
  - path: "src/backend/apps/users/services/deletion.py"
    targets:
      - type: function
        name: withdraw_consent
    semantic_anchors:
      insert_after:
        type: function_call
        value: record_consent_action_with_context
  - path: "src/backend/apps/users/admin.py"
    targets:
      - type: method
        name: UserAdmin.withdraw_consent_action
      - type: class
        name: ConsentRecordAdmin
    semantic_anchors:
      insert_after:
        type: function_call
        value: withdraw_consent
  - path: "src/backend/apps/users/services/pii_inventory.py"
    targets:
      - type: module_attribute
        name: PII_ERASURE_ENTRIES
      - type: module_attribute
        name: REVIEWED_NON_IDENTITY_COLUMNS
  - path: "src/backend/apps/users/tests/test_consent_actor.py"
    targets:
      - type: module
        name: test_consent_actor
  - path: "src/backend/apps/users/tests/test_admin_consent_action.py"
    targets:
      - type: function
        name: test_forged_post_as_superuser_withdraws_and_writes_one_record
  - path: "src/backend/apps/users/tests/test_purge_consent_records.py"
    targets:
      - type: module
        name: test_purge_consent_records
  - path: "src/backend/apps/users/tests/test_pii_inventory.py"
    targets:
      - type: module
        name: test_pii_inventory
  - path: "docs/02-database/db-schema.md"
    targets:
      - type: document_section
        name: "consent_records (zone F / Plan 21)"
  - path: "docs/02-database/db-enums.md"
    targets:
      - type: document_section
        name: ConsentActionSource
  - path: "docs/99-agent/pii-consent-remediation-record.md"
    targets:
      - type: document_section
        name: "Open work"
changes:
  - action: add_code
    description: >
      Add the ConsentActionSource StrEnum (rule 10) to apps/core/enums.py next to
      ConsentChoice, and add the name to __all__. Five members, and the mechanism vocabulary
      is closed on purpose so a future writer cannot invent a fourth spelling.
    code_hint: |
      class ConsentActionSource(StrEnum):
          """Mechanism by which a consent action was initiated (06-NEW-02).

          Answers "by what mechanism", never "who" - that is initiated_by. Read the two
          together: action_source is authoritative for which case a row is, and
          initiated_by names the acting account when one exists and is not the subject.
          """

          SELF_SERVICE = "self_service"      # the subject acted, from their own session
          ANONYMOUS_WEB = "anonymous_web"    # an unidentified visitor acted; no account at all
          ADMIN_STAFF = "admin_staff"        # a staff account acted via the Django admin
          SYSTEM = "system"                  # no human actor; an automated process acted
          UNKNOWN = "unknown"                # DEFAULT - row predates 06-NEW-02; not recoverable
  - action: add_code
    description: >
      Add two columns to ConsentRecord and rewrite the class docstring to carry the actor
      definition. Correct ConsentRecord.user's help_text, which currently says "User who
      acted" - it names the SUBJECT, which is the ambiguity this block removes.
    code_hint: |
      initiated_by = models.ForeignKey(
          "users.User",
          null=True,
          blank=True,
          on_delete=models.SET_NULL,
          related_name="+",
          help_text=(
              "Acting account, recorded ONLY when it is not the subject (06-NEW-02). NULL "
              "means no acting account distinct from the subject - a self-service action, "
              "an anonymous visitor, or a system action; action_source tells those apart. "
              "Never CASCADE: consent_hard_delete deletes User rows and a cascade would "
              "destroy the Art. 7(1) ledger. The acting account is irreversibly anonymised "
              "12 months after the action (BLOCK 19, 06-NEW-02) - a chosen minimisation "
              "period justified by purpose, NOT a statutory term, and deliberately shorter "
              "than the event bound, which governs the decision fields only. A documented "
              "legal_hold suspends this actor erasure."
          ),
      )
      action_source = models.CharField(
          max_length=20,
          choices=[(s.value, s.value) for s in ConsentActionSource],
          default=ConsentActionSource.UNKNOWN.value,
          blank=True,
          db_index=True,
          help_text=(
              "Mechanism that initiated the action (06-NEW-02). UNKNOWN is the default and "
              "means the row predates this column: the mechanism was never captured and is "
              "not recoverable. No row written through the recording service carries UNKNOWN."
          ),
      )
  - action: add_migration
    description: >
      Two AddField operations in the users app. Verify the directory is still at
      0004_consentrecord_sweep_index immediately before generating. No RunPython, no
      backfill: the ledger never recorded the actor, so nothing is derivable.
  - action: modify_code
    description: >
      record_consent_action_with_context gains a REQUIRED keyword-only action_source and an
      optional keyword-only initiated_by. Put the actor normalisation in this one insertion
      path, beside the existing _anonymize_ip sanitisation, so no future writer bypasses it.
    code_hint: |
      # Actor normalisation (06-NEW-02): the actor is recorded only when it is NOT the
      # subject. Storing the subject twice would duplicate the very link BLOCK 15 clears at
      # 90 days, and that surviving copy would be the only remaining link from an anonymous
      # decision to a live account. Invariant: initiated_by is not null only when it is a
      # different row from user.
      actor = (
          initiated_by
          if initiated_by is not None
          and (user is None or initiated_by.pk != user.pk)
          else None
      )
      return ConsentRecord.objects.create(
          user=user if user is not None and user.is_authenticated else None,
          ...,
          action_source=action_source,
          initiated_by=actor,
      )
  - action: modify_code
    description: >
      record_consent_action gains ONE optional keyword-only action_source parameter that
      resolves to ANONYMOUS_WEB when user is None and SELF_SERVICE otherwise, and forwards it
      on BOTH delegation paths. This is what preserves the frozen signature: the
      four-argument positional shape, the request=None default, the consent_version default
      and the delegation all stand, so consent_accept, consent_decline and every existing test
      call site keep working unchanged. Document the derivation and the explicit override.
    code_hint: |
      resolved_source = action_source or (
          ConsentActionSource.ANONYMOUS_WEB
          if user is None
          else ConsentActionSource.SELF_SERVICE
      )
  - action: modify_code
    description: >
      withdraw_consent: signature only. Append two keyword-only parameters after
      session_key - action_source defaulting to SELF_SERVICE and initiated_by defaulting to
      None - and forward them on the existing record_consent_action_with_context call. Add NO
      statement to the body, do NOT move the audit write, do NOT touch the atomic() block.
      Re-read the file immediately before editing: this is the FIFTH writer.
  - action: modify_code
    description: >
      UserAdmin.withdraw_consent_action passes action_source=ADMIN_STAFF and
      initiated_by=request.user. This is the path that currently produces a "subject
      withdrew" record for what is actually a staff revocation. Do NOT add ip_address or
      user_agent - BLOCK 10's shipped behaviour and its test stay as they are.
    code_hint: |
      withdraw_consent(
          user,
          action_source=ConsentActionSource.ADMIN_STAFF,
          initiated_by=request.user,
      )
  - action: modify_code
    description: >
      ConsentRecordAdmin: add both new fields to readonly_fields (MANDATORY - the class
      declares no fieldsets, so without them a superuser could edit the actor and the
      mechanism, forging accountability evidence) and add action_source to list_filter.
      Leave list_display and search_fields byte-identical - BLOCK 12 owns them, and BLOCK
      15's session_key residual is BLOCK 15's to close.
  - action: modify_code
    description: >
      pii_inventory: one new erasure entry ("users.ConsentRecord", "initiated_by",
      ErasureAction.RETAIN, reason) whose reason names BLOCK 18 and cites 06-NEW-02; add
      "action_source" to REVIEWED_NON_IDENTITY_COLUMNS["users.ConsentRecord"]; and amend
      ONLY the module docstring's clause about relational fields so a declared relational
      entry is permitted. Do NOT import ConsentActionSource at module scope - the
      no-apps-import probe wraps builtins.__import__ and fails on any apps.* request.
  - action: add_test
    description: >
      New test_consent_actor.py carrying the eight behavioural assertions: the three cases
      distinguishable from stored values; the staff admin revocation no longer reading as a
      subject withdrawal; the anonymous row positively marked and still carrying its session
      key; no live writer emitting the unknown mechanism; the ledger surviving the actor
      account's deletion; the sweep leaving a staff actor readable; the admin refusing to
      forge actor or mechanism; and the legacy row's honest reading.
  - action: modify_test
    description: >
      Extend test_forged_post_as_superuser_withdraws_and_writes_one_record with the actor and
      mechanism assertions (additive only - keep the existing no-IP / no-user-agent
      assertions, they remain true). Add the staff-actor retention test to
      test_purge_consent_records.py (production command unchanged). Add one declaration test
      to test_pii_inventory.py.
  - action: modify_docs
    description: >
      db-schema.md: add the two columns to the consent_records list and REPLACE the "Known
      limitation - no actor column (06-NEW-02, open and unowned)" paragraph with the actor
      definition and the retention decision. db-enums.md: add a ConsentActionSource section.
      pii-consent-remediation-record.md: move the 06-NEW-02 row out of "Open work" to BLOCK 18.
acceptance_criteria:
  - "a subject's own web withdrawal and a superuser's admin revocation of a different subject, re-read from the database, differ on stored values alone: the first names the subject and carries no separate acting account, the second names the target as subject, names the superuser as the acting account, and records a different mechanism - so the staff revocation no longer reads as a subject withdrawal"
  - "an action recorded with the system mechanism carries no acting account and is distinguishable from both the self-service and the staff rows from stored values, with no join"
  - "a consent row written by an anonymous visitor carries no subject, no acting account, the anonymous mechanism, and a non-null session key, and is distinguishable from the system row and from the authenticated rows on stored values"
  - "deleting the acting staff account's user row the way consent_hard_delete does leaves every consent row it acted on in place with its subject and decision fields intact, and only the acting-account pointer reads empty"
  - "a consent row that predates this change carries the unknown mechanism and no acting account and is distinguishable from every row written after it, while no row written through the consent-recording service carries the unknown mechanism"
  - "running the consent-record retention sweep over an aged staff-revocation row clears the subject, session key, IP address and user agent, leaves the row itself in place, and leaves the acting staff account readable on it"
  - "a superuser cannot alter the acting account or the mechanism of an existing consent row through the admin change form, and the consent changelist can be filtered by mechanism"
  - "the consent withdrawal, admin consent action, retention sweep, consent recording service and erasure inventory suites pass with no assertion removed other than the ones this block deliberately replaces"
  - "the fresh-schema run with --create-db passes and makemigrations --check is clean"
tests_required:
  - "src/backend/apps/users/tests/test_consent_actor.py (new - all eight assertions)"
  - "src/backend/apps/users/tests/test_admin_consent_action.py (extended staff-case assertions, existing ones kept)"
  - "src/backend/apps/users/tests/test_purge_consent_records.py (new staff-actor retention test; command unchanged)"
  - "src/backend/apps/users/tests/test_pii_inventory.py (new declaration test)"
tests_to_run:
  - "src/backend/apps/users/tests/test_consent_actor.py"
  - "src/backend/apps/users/tests/test_admin_consent_action.py"
  - "src/backend/apps/users/tests/test_purge_consent_records.py"
  - "src/backend/apps/users/tests/test_pii_inventory.py"
  - "src/backend/apps/users/tests/test_consent_records.py"
  - "src/backend/apps/users/tests/test_consent.py"
  - "src/backend/apps/users/tests/test_deletion.py"
  - "src/backend/apps/users/tests/test_admin_pii_containment.py"
  - "src/backend/apps/core/tests/test_client_ip.py"
commands:
  - "docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS=\"src/backend/apps/users/tests src/backend/apps/users/tests/test_purge_consent_records.py --tb=short\" test"
  - "docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS=\"--create-db --tb=short -n auto --maxprocesses=4 --dist loadgroup\" test"
  - "docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml run --rm --env PYTEST_SKIP_MARKERS=seed test"
  - "uv run ruff check src/backend/apps/users/"
  - "uv run basedpyright src/backend/apps/users/services/consent_record.py src/backend/apps/users/models.py"
command_notes: |
  Copy the alias once per session:
    $dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'
  and run the container commands as `$dc run --rm ... test`.
  --env-file .env.test is REQUIRED (compose aborts on ${POSTGRES_*?} without it). Never use
  the mko-bazuna-dev project name. A migration lands, so the --create-db run is MANDATORY.
  PYTEST_OPTS is unquoted in docker/entrypoint-test.sh and REPLACES the defaults, so a
  targeted run loses xdist and --reuse-db. Never --override-ini=addopts= (it strips
  --import-mode=importlib). Never run uv run pytest on the host - there is no local
  PostgreSQL. VAL-010 teardown races are contention, not defects: re-run a red gate serially.
  CORRECTION to the brief: the retention-sweep suite lives at
  src/backend/apps/users/tests/test_purge_consent_records.py, NOT under apps/core/tests/ -
  verified. apps/core/tests/test_sweep_consent.py covers consent_hard_delete and is
  unaffected. src/backend/apps/users/tests/test_purge_consent_records.py is already inside
  the users/tests directory target above; listing it separately is harmless but redundant.
commit:
  message: "feat(users): record who initiated each consent action (06-NEW-02)"
  stage_only:
    - "src/backend/apps/core/enums.py"
    - "src/backend/apps/users/models.py"
    - "src/backend/apps/users/migrations/0005_consentrecord_initiated_by_action_source.py"
    - "src/backend/apps/users/services/consent_record.py"
    - "src/backend/apps/users/services/deletion.py"
    - "src/backend/apps/users/admin.py"
    - "src/backend/apps/users/services/pii_inventory.py"
    - "src/backend/apps/users/tests/test_consent_actor.py"
    - "src/backend/apps/users/tests/test_admin_consent_action.py"
    - "src/backend/apps/users/tests/test_purge_consent_records.py"
    - "src/backend/apps/users/tests/test_pii_inventory.py"
    - "docs/02-database/db-schema.md"
    - "docs/02-database/db-enums.md"
    - "docs/99-agent/pii-consent-remediation-record.md"
extra_context: |
  OWNER RULING (2026-10-04) - implement against it, do not reopen. 06-NEW-02 is reopened as
  an owned Phase-06 follow-up. BLOCKS 12 and 15 are NOT reopened. It was previously routed to
  "BLOCK 12/15" and both closed without it, leaving it orphaned. Reason it is not cosmetic:
  ConsentRecord cannot distinguish subject withdrew / staff revoked / system revoked, so the
  AUDIT MEANING of the record is incomplete - a data-model and accountability defect. Shape the
  owner named: an actor / revoked_by with a clear definition of who counts as the actor.

  1. ACTOR DEFINITION (write this down where a reader will find it - model docstring, field
     help_text, writer docstring, db-schema.md):
     The actor is the account that performed the action, and it is recorded ONLY when that
     account is NOT the subject. user already names the subject, so a self-action would store
     the same account twice. Invariant: initiated_by IS NOT NULL only when initiated_by is a
     different row from user. Read the pair, never one column alone - action_source is
     authoritative for which case the row is; initiated_by names the account when one exists.
     A null initiated_by means "no acting account distinct from the subject", covering a
     self-service action, an anonymous visitor and a system action; action_source tells those
     three apart.
     Both columns are required. A system action has NO User actor, so the FK alone cannot
     express "system revoked" - one of the three cases the owner named.

  2. THE THREE CASES AS STORED (U = subject, S = acting staff, "-" = NULL):
     subject acted        -> user=U, initiated_by=-, action_source=self_service
     anonymous visitor    -> user=-, initiated_by=-, action_source=anonymous_web  (+ non-null session_key)
     staff revoked        -> user=V, initiated_by=S, action_source=admin_staff
     system               -> user=V, initiated_by=-, action_source=system
     predates this block  -> unchanged, initiated_by=-, action_source=unknown

  3. RETENTION - IMPLEMENT THE RULED BOUND; DO NOT RE-DERIVE IT. SUPERSEDED: this step
     originally read "Retain the staff actor to the DECISION bound (5 years); do NOT clear it
     at the 90-day fingerprint window ... This is an owner/DPO proportionality decision ...
     do not silently choose 90 days", and concluded that
     apps/core/management/commands/purge_consent_records.py was NOT MODIFIED by this block.
     All of that is withdrawn by the owner ruling of 2026-10-04. The staff actor is now
     irreversibly anonymised 12 MONTHS from the action, subject to a documented legal_hold
     (BLOCK 19, 06-NEW-02). The data-minimisation concern that made the original deferral
     necessary is real and is now answered by a bounded period rather than by an open question:
     a superuser identifier kept indefinitely yields a per-operator behavioural record with no
     erasure path. This step's own scope is UNCHANGED - BLOCK 18 still does not modify
     purge_consent_records.py - but the reason is now scope, not an open legal question, and
     the actor column is no longer "never named in its .update(...)" by design: it is cleared
     by BLOCK 19, which is the successor to this step, not a contradiction of it.

  4. FIFTH-WRITER ORDERING RULE for withdraw_consent (apps/users/services/deletion.py).
     Re-read the file immediately before editing and assert this. Landed writers so far:
     BLOCK 9 474a68d (body + atomic), BLOCK 13 6631ff3 (SupportTicket deletion),
     BLOCK 8 8dba351, BLOCK 10 749bbfc (audit write, LAST inside the block). This block is the
     FIFTH. (a) Do not reorder, move or remove the existing
     record_consent_action_with_context call - it stays last inside transaction.atomic(),
     after the SupportTicket delete and soft_delete_user_ads, because
     test_withdraw_is_atomic_rollback depends on that raise rolling the audit row back.
     (b) Do not open, move or close the atomic() block; add no second transaction.
     (c) Extend the SIGNATURE only - append the two keyword-only parameters after session_key -
     and forward them on the existing call, adding no statement to the body.
     (d) If the file no longer matches this shape, STOP AND REPORT rather than layering on top.

  5. FROZEN SIGNATURE. record_consent_action(user, choice, categories, request=None,
     consent_version=...) keeps its four-argument positional shape, its request=None default,
     its consent_version default and its delegation. The new action_source parameter is OPTIONAL
     and KEYWORD-ONLY, so every existing call site keeps working unchanged - BLOCK 8 and
     BLOCK 10 both relied on that freeze and it is NOT broken here. record_consent_action's
     action_source resolves to ANONYMOUS_WEB when user is None and SELF_SERVICE otherwise; the
     derivation is correct because the only callers are the two self-service web views, and it
     is documented with an explicit override for the first caller that is not one.
     record_consent_action_with_context's action_source is REQUIRED keyword-only with NO
     default, so a new caller cannot forget to classify itself.
     DO NOT EDIT apps/users/views/consent.py - BLOCK 8 owns it and the derivation makes the edit
     unnecessary.

  6. MIGRATION. apps/users/migrations/ was verified at 0004_consentrecord_sweep_index, so this
     is 0005_consentrecord_initiated_by_action_source.py with two AddFields (initiated_by:
     null=True, blank=True, on_delete=SET_NULL, related_name="+"; action_source: choices,
     default=ConsentActionSource.UNKNOWN.value, blank=True, db_index=True). Verify the
     directory immediately before generating - other blocks have landed migrations in this app.
     NO data migration, NO RunPython, NO backfill: the ledger never recorded the actor, so
     nothing is derivable, and inferring "no IP and no user agent therefore staff" would be
     wrong for every bot- or command-written row. AddField writes the default to existing rows,
     so every pre-existing row reads action_source="unknown". Reading convention: unknown means
     "written before the actor was recorded; the mechanism was never captured and is not
     recoverable", and a null initiated_by on such a row carries NO inference about who acted,
     including for rows that were in fact staff revocations. Record that gap honestly.
     Reversible: yes (AddField on nullable/defaulted columns). The reversal is LOSSY - it
     destroys every actor and mechanism value written, and re-applying re-stamps pre-existing
     rows as unknown. Say so in the commit body.

  7. INVENTORY. In apps/users/services/pii_inventory.py: add ONE erasure entry
     ("users.ConsentRecord", "initiated_by", ErasureAction.RETAIN, reason) whose reason names
     BLOCK 18 and cites 06-NEW-02, and states that the column never holds the subject, is
     retained to the decision bound rather than the fingerprint bound, and is emptied only by
     SET_NULL when the ACTING ACCOUNT's own row is hard-deleted. RETAIN, not NULL - no erasure
     path nulls it. Add "action_source" to REVIEWED_NON_IDENTITY_COLUMNS["users.ConsentRecord"]:
     the guard's _is_review_candidate skips relational fields, so a non-relational column like
     this one is NOT skipped and turns the guard red until it is decided. That reviewed set is a
     bare frozenset with NO reason field, so the reason goes in the module docstring's
     look-alike list, citing 06-NEW-02. Amend ONLY the docstring clause that says relational
     fields "are not recorded here", because a declared relational entry contradicts it.
     MUST NOT change: ErasureAction, the 4-tuple shape, every existing entry,
     REVIEWED_NON_IDENTITY_COLUMNS for every other model, the lazy-string import boundary, and
     the stdlib-only rule. Do NOT import ConsentActionSource at module scope -
     test_importing_the_declaration_pulls_in_no_apps_model wraps builtins.__import__ and fails
     on ANY apps.* request. Write the reason as a plain string.

  8. ConsentRecordAdmin - RESPECT BLOCK 12's AND BLOCK 15's OWNERSHIP. readonly_fields: add
     BOTH new fields, MANDATORY - the class declares no fieldsets, so Django auto-builds the
     form from editable fields and a superuser would otherwise be able to edit the actor and
     the mechanism, forging accountability evidence. list_filter: add action_source (low
     cardinality, no identity exposure, and it is how the three cases are separated on the
     changelist; unowned by both blocks). list_display and search_fields: leave BYTE-IDENTICAL -
     BLOCK 12 owns them, and BLOCK 15's session_key residual is BLOCK 15's to close.

  9. VERIFIED FACTS THIS BLOCK RELIES ON (re-verify before editing; do not assume).
     - No Telegram-bot caller of record_consent_action exists. A repo-wide search returns hits
       only in apps/users/views/consent.py (2 call sites), apps/users/services/deletion.py (1),
       consent_record.py (definitions) and three test modules. The module docstring's "e.g.
       from the Telegram bot /start entry point" is ASPIRATIONAL - that path does not exist. Do
       not build a writer for it.
     - purge_consent_records writes NO ConsentRecord rows; it only .update()s existing ones. It
       is the only command naming ConsentRecord. consent_hard_delete names User,
       AnalyticsEvent, ModeratorActionLog and SupportTicket only.
     - User deletion today: consent_hard_delete runs
       User.objects.filter(consent_revoked_at__lt=cutoff).delete() (a real collector delete, 30
       days after withdrawal) and apps/seed/services/seed_service.py runs
       User.objects.filter(source=AdSource.SEED).delete(). A CASCADE actor FK would therefore
       DELETE ConsentRecord rows through the collector and destroy Art. 7(1) evidence.
       SET_NULL only.
     - ConsentActionSource.SYSTEM has no production writer today and that is expected. It exists
       because the owner named "system revoked" as one of the three cases and because a closed
       vocabulary is what stops a future writer inventing a fourth spelling. The
       audit-meaning test proves it is STORABLE and distinguishable by driving the real writer;
       record plainly in the commit body that no production path emits it.

  10. DOCUMENTED RESIDUALS - record, do NOT fix. (a) The admin-initiated row still carries NO
      ip_address and NO user_agent. The admin request IS available and could supply them, but
      that is BLOCK 10's shipped behaviour and its test, and the ruling scoped this block to
      actor and mechanism. (b) record_consent_action's "request is None" branch drops
      consent_version when delegating - a pre-existing defect, out of scope, but that line MUST
      be edited to forward action_source, so note it in the commit body rather than fixing it
      silently.

  11. NO i18n / .po CHANGE. Model help_text and enum values are not a translatable surface (the
      gate scans templates; every other field on this model already carries English help_text),
      and no new user-visible string is introduced.

  12. MANDATORY --create-db run (a migration lands). VAL-010 artefacts are contention, not
      defects - re-run a red gate serially before reporting it. One Implementor at a time, one
      commit per block, stage_only list only, never git add -A.
```

---

### BLOCK 19 — Separate the 12-month actor window from the event bound (`06-NEW-02`)

| | |
|---|---|
| **Findings owned** | `06-NEW-02` (retention half). BLOCK 18 owns the column; this block owns its **bound** |
| **Depends on** | **BLOCK 18** (`initiated_by`, `action_source` exist) and **BLOCK 15** (`purge_consent_records`, lock 14) |
| **Blocks** | nothing |
| **Priority** | P1 — closes the owner's 2026-10-04 retention ruling |
| **Risk level** | **MEDIUM** — a second mutation stage on the audit ledger and one migration |
| **Required agents** | **Implementor · Validator** |
| **Status** | **SHIPPED** as `2ae74fb`. This section records what was built |

**The owner ruling (2026-10-04) — implemented, not reopened.** Retention is **per field**. Twelve
months is a **chosen minimisation period justified by purpose** — one full operational/audit cycle —
and **explicitly not a statutory term**. The state this block changed was actor-retained to the
5-year event bound; **BLOCK 18's recorded reasoning for that is superseded** (see that section).

#### 1. The three windows, as implemented

| Window | Literal | Applies to | Action |
|---|---|---|---|
| **fingerprint** | `_FINGERPRINT_RETENTION_DAYS = 90` | `user`, `session_key`, `ip_address`, `user_agent` | one `UPDATE`: `user=None, session_key=None, ip_address=None, user_agent=""` |
| **actor** (`06-NEW-02`) | `_ACTOR_RETENTION_DAYS = 365` | `initiated_by` | second, independent `UPDATE`: `initiated_by=None`, unless `legal_hold` |
| **event** | `_DECISION_RETENTION_DAYS = 365 * 5` | `choice`, `categories`, `consent_version`, `consent_given_at` | **count-only** — the row is retained at every age and **never deleted** |

The event window is **not** a deletion boundary, and **no boundary here is a legal deadline.** The
actor stage is **not** symmetric with the others: the fingerprint and actor windows mutate, the
event window only counts, because deleting the ledger row is the failure mode this sweep exists to
avoid.

**The actor stage is a second mutation stage inside the same `atomic()` and the same advisory lock
14** — not a new command, not a new lock, not a new scheduler entry. A failure in the actor stage
rolls the fingerprint clear back with it. It is deliberately **not** folded into the fingerprint
`UPDATE`: that queryset excludes already-cleared rows, and the actor rule is independent of it.
Excluding a null `initiated_by` keeps the stage idempotent.

#### 2. The clock, and why no new column exists

The anchor is **`consent_given_at`** — the sole production writer is
`record_consent_action_with_context`'s `objects.create`, synchronous with the action. It already
leads `IX_consent_records_sweep`, so the actor cutoff is an **Index Cond**. **No `action_at` column
was added**: a dedicated action clock is a second clock that can only drift, and it would require an
unrecoverable backfill. **No `actor_anonymised_at` marker column was added either** — the state is
derivable from `action_source` plus the row's age, and a second concrete non-timestamp column would
have widened the inventory guard's review surface for nothing.

#### 3. `legal_hold` and migration `users/0006_consentrecord_legal_hold.py`

`legal_hold = BooleanField(default=False)` — a **superuser-settable exemption from actor erasure
only**. The migration is `AddField` plus a **`help_text`-only `AlterField`** on `initiated_by`. The
default leaves **every existing row un-held, so no backfill is needed.**

**A hold never restores what the 90-day fingerprint window already cleared, and never extends the
event fields.** It suspends one stage only.

**The deliberate admin asymmetry — `legal_hold` is absent from `ConsentRecordAdmin.readonly_fields`
while both actor columns remain non-editable.** This is intentional and must not be "fixed":

- `initiated_by` and `action_source` **are the evidence**, so a superuser able to edit them could
  **forge** accountability. They stay in `readonly_fields`.
- `legal_hold` is an **exemption from erasure, not evidence**, so it must be settable — a superuser
  has to be able to *find* held rows (hence it was added to `list_filter`) and clear the hold.
- Both effects are superuser-only already: `has_change_permission` gates the whole change form on
  `is_superuser`, so no extra check is needed.

#### 4. The ordering guard

The command asserts `0 < fingerprint ≤ actor ≤ event` **itself, before `transaction.atomic()` is
entered** (`_assert_retention_ordering`), raising `ValueError` otherwise, so a mis-ordered set fails
loudly instead of making a stage a silent no-op. The fingerprint TTL is additionally floored at the
declared Django session lifetime (`SESSION_COOKIE_AGE`) so a still-live session's support evidence
is not destroyed. **That floor applies to the fingerprint bound only** — the actor is an account FK,
not live-session evidence.

#### 5. Inventory, and the five-case reading

`initiated_by` is re-declared **`ErasureAction.NULL`** (BLOCK 18 declared it `RETAIN`, which claimed
a scrub that did not happen). `legal_hold` joins **`REVIEWED_NON_IDENTITY_COLUMNS`** — a hold carries
no subject data and no erasure path touches it, so it has no erasure-contract entry.

**`initiated_by IS NULL` now covers five situations, and `action_source` alone still separates them
completely, without a join:** self-service, anonymous web, system, legacy `unknown`, and an
`admin_staff` attribution whose 12-month window expired or whose acting account was hard-deleted.
That last case is why `action_source` remains authoritative for *which case* a row is:
`admin_staff` is written **only** when a staff account acted. The write-time invariant is unchanged —
the actor FK never holds the subject.

#### 6. Confirmed unchanged

- **No production writer emits `action_source = SYSTEM`.** The member exists because the owner named
  "system revoked" as a case that must be distinguishable; no live path writes it, and that is
  recorded rather than engineered.
- **`SET_NULL`, never `CASCADE`**, on the actor FK; `consent_hard_delete`'s collector delete and
  `seed_service`'s bulk delete both pass through it.
- **Anonymise, never delete** for the decision fields, and **no `DELETE` path** in the sweep.
- **No configuration surface.** The three literals are hardcoded module constants; `--dry-run`
  remains the **only** argument, matching `db-retention.md`'s explicit rule.
- **`withdraw_consent`'s signature and body are untouched** by this block.
- **`views/consent.py` is untouched** by this block.
- **`AdvisoryLockId` is unchanged** — lock 14 is reused, no new member.

**Flagged, not acted on:** the event-retention wording could be read as implying a five-year
deletion boundary. **The shipped rule is anonymise-never-delete**, and the wording is corrected in
§*Retention framing correction (owner ruling 2026-10-04)* rather than in code.

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
