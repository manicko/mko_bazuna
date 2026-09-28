---
phase: "06"
phase_name: "PII Protection & Consent Compliance"
source_findings: ".ai/audit/06-pii-consent/findings.md"
date: "2026-09-28"
auditor: "Executor (subagent)"
validator: "Reviewer (subagent)"
mode: "problems-only"
id_prefix: "PII"
evidence_anchor: "9e96b84"
report_status: "validated"
---

# Validated Findings — PII Protection & Consent Compliance

> Self-contained validation report. Every claim below was re-derived from the
> working tree and from a fresh runtime probe in the `mko-bazuna-test` image.
> No source file was modified. The reader needs nothing beyond this document.

## Validation Verdict Table

| ID | Title (short) | Auditor severity | Verdict | Validated severity | One-line justification |
|----|---------------|------------------|---------|--------------------|------------------------|
| PII-101 | Support tickets keep raw Telegram ID/handle after the 30-day erasure | CRITICAL | **CONFIRMED** (impact wording corrected) | **CRITICAL** | Reproduced: the row survives with `user_id=NULL` and every raw identifier intact; the auditor's "no sweep can ever find it" is refuted, the retention breach is not. |
| PII-102 | Raw `chat_id` written unredacted to WARNING logs | CRITICAL | **ADJUSTED** | **HIGH** | Real and spec-violating, but the path is behind the default-off `IMMEDIATE_ALERTS_ENABLED` flag, fires only on send failure, and writes one integer to an operator-controlled log — not a rollout blocker. |
| PII-103 | `UserAdmin` auto-built form exposes identity + consent fields to any staff | HIGH | **MERGED** → `04-AUT-005` | HIGH *(absorbed)* | Same root cause as phase 04's AUT-005/VAL-004 (no `fields`/`fieldsets`/`form` declared); one fix, one commit, one test. |
| PII-104 | Outbound alert channel ignores consent/account state | HIGH | **CONFIRMED / NARROWED** | **HIGH** | Reproduced: revoked, declined, banned and active subscribers all match a declined seller's hidden ad. The declined-buyer half is spec-consistent and is struck. |
| PII-105 | DECLINE is a one-way door | HIGH | **ADJUSTED + RECLASSIFIED** | **MEDIUM** | Hiding ads and blocking login are both explicitly spec-sanctioned; the real defect is a broken, undiscoverable recovery affordance plus a false policy promise. |
| PII-106 | `SupportTicketAdmin` renders raw IDs and full-text-searches ticket bodies | MEDIUM | **CONFIRMED** (recommendation narrowed) | **MEDIUM** | `list_display`/`search_fields` verified; but the proposed blanket registry-wide test would produce a false positive on `SupportContactAdmin`. |
| PII-107 | `withdraw_consent()` writes no `ConsentRecord` | MEDIUM | **CONFIRMED** (root-cause rationale corrected) | **MEDIUM** | Verified: the audit write lives only in the three web views; the stated reason ("`record_consent_action` is request-aware") is wrong — it already accepts `request=None`. |
| PII-108 | `AnalyticsEvent`/`SearchHistory` not gated on analytics consent | MEDIUM | **ADJUSTED + RECLASSIFIED** | **MEDIUM** | The spec already decided this (legitimate interest); the residual defect is a consent-taxonomy naming collision, not a violated gate. Strengthened: `query_normalized` keeps un-redacted PII. |
| PII-109 | "Anonymized ads after withdrawal" is not implemented | MEDIUM | **CONFIRMED** | **MEDIUM** | `soft_delete_user_ads()` transitions status only; `AdAdmin.search_fields` exposes the retained body. |
| PII-110 | `chat_id`, `session_key`/`user_agent`, `preferred_city` never erased | MEDIUM | **CONFIRMED / SPLIT** | **MEDIUM** | All four fields verified absent from the `update_fields` list; `privacy.html` §6 over-promises. Split out so the `ConsentRecord` TTL can ship separately. |
| PII-111 | `SellerVerification.phone_number` undisclosed | MEDIUM | **ADJUSTED** (premise refuted) | **LOW** | Zero writers exist anywhere in `src/` — the product does not collect it; the auditor's runtime evidence was the probe's own insert. Real defect is a vestigial, undisclosed column. |
| PII-112 | `mask_telegram_id()` is brute-forceable | MEDIUM | **CONFIRMED** | **MEDIUM** | Verified: exactly `sha256(id)[:8]`, and a 2^20 sweep recovered the original ID in 1.39 s; the spec's "non-reversible" claim is false. |
| PII-113 | Doc conflict on DECLINE semantics | MEDIUM | **CONFIRMED** (→ DOC-UPDATE, merged with `04-VAL-005`) | **MEDIUM** | Both statements verified verbatim; `spec-index.md:74` is the stale one. Duplicate of a conflict phase 04 already filed. |
| PII-114 | `ModeratorActionLog.reason` free text survives erasure | LOW | **CONFIRMED** | **LOW** | `reason` is an unbounded `TextField` with `SET_NULL` on both FKs; no redaction at any write site. |
| PII-115 | `create_admin_user` writes raw `username` to stdout | LOW | **REJECTED** | — | The claim is factually wrong: this command creates a *local admin* with an operator-chosen username and a placeholder `telegram_id=-1`; it never touches a seller's Telegram handle, and the spec rule it is judged against covers `telegram_id` only. |
| PII-116 | `ConsentRecord` has no retention; `session_key` in the changelist | LOW | **CONFIRMED** | **LOW** | Verified: no purge in `HOURLY_COMMANDS`, `session_key` in `list_display` and `search_fields`. |

**Severity movement:** 2 CRITICAL · 3 HIGH · 8 MEDIUM · 3 LOW
→ **1 CRITICAL · 3 HIGH · 7 MEDIUM · 3 LOW** + 1 rejected + 1 merged into phase 04.

**Findings requiring architectural or structural change** (not a patch):

1. **Declarative PII inventory** — PII-101, PII-109, PII-110, PII-111, PII-114 share one
   root cause: the erasure contract is a hand-maintained `update_fields` list on one
   model. A single registry (model → identity column → erasure action) consumed by
   both `withdraw_consent()` and the backfill migration is the durable fix.
2. **`UserAdmin` field contract** — PII-103 (merged into 04-AUT-005): explicit
   `fieldsets` plus a purpose-built form. Highest consequence, smallest diff.
3. **One queryset-level account-state predicate** — PII-104 + VAL-003: the consent
   predicate that `apps/search` needs does not exist in queryset form, and
   `get_account_state()` is instance-level, so a naive fix writes a second,
   drift-prone copy. Requires an ownership decision (VAL-003).
4. **Consent audit in the domain layer** — PII-107: move the `ConsentRecord` write
   into `withdraw_consent()` with an explicit context object rather than a
   `HttpRequest`.
5. **Masking key management** — PII-112: a new `LOG_MASK_KEY` secret, its
   `ALLOWED_ENV_VARS` registration, `.env.*.example` entries and a rotation policy.
6. **Retention sweep** — PII-116: a new destructive command in `HOURLY_COMMANDS`,
   ordered so it can never delete an Art. 7(1) record still needed.

## Scope & Method

**In scope:** the identity/PII zone (`apps/users` models + `account_state`,
`deletion`, `consent_record`, `login_rate_limit`), the consent state machine
(`views/consent.py`, `context_processors.consent_state`), the erasure sweep
(`consent_hard_delete`, `scheduler.HOURLY_COMMANDS`), the admin surfaces of every
consent/PII model, the outbound alert fan-out (`send_alerts`, `alert_query`,
`immediate_alerts`), `sanitize.py`, the trust/moderation models that denormalise
identity, and the published privacy policy.

**Verification performed by the validator** (all read-only against a throwaway
database `val06_probe`, created and dropped inside the probe; the phantom
`mko_bazuna` database was never opened):

| V# | Check | Result |
|----|-------|--------|
| V-01 | Source re-read of all 16 findings' cited files | 15/16 claims reproduce verbatim; 1 premise refuted (PII-111), 1 impact statement refuted (PII-101) |
| V-02 | `SupportTicket` across `withdraw_consent()` + `consent_hard_delete` | ticket survives with `user_id=None`, all identifiers intact — **confirmed**; `user_id__isnull=True` finds it in 1 query — **auditor's "unfindable" claim refuted** |
| V-03 | `UserAdmin.get_form()` introspection as superuser and as moderator | 22 editable fields; `password` = `CharField(AdminTextInputWidget) required=True`; `telegram_id`/`chat_id`/`username`/`is_declined`/`is_deleted`/`is_banned`/`ads_auto_publish` all writable; `has_change_permission(moderator)=True`; `UserAdmin.actions == ()` — **confirmed, and identical to 04-VAL-004** |
| V-04 | Alert audience: 4 saved searches (active / declined / withdrawn / banned) vs a declined seller's ad | all four match; `find_matching_saved_searches` returns all five; the ad is invisible via `ListingsQuery` — **confirmed** |
| V-05 | DECLINE reversal via the Django test client | authenticated `/?ref=preferences` → Accept → `is_declined=False`, `can_login=True`, 302; **anonymous** `/?ref=preferences` → Accept → 302 to `/`, `is_declined` **unchanged**, `can_login` **unchanged** — silent no-op confirmed |
| V-06 | `SellerVerification.phone_number` writers across `src/` | none — grep for `phone_number` returns only the model field, its migration, and an unrelated JSON-logging test; probe DB row count 0 — **premise refuted** |
| V-07 | `mask_telegram_id` reversal | `sha256(b"630000001").hexdigest()[:8]` equals the mask; a 2^20 candidate sweep recovered the original ID in **1.39 s** — **confirmed** |
| V-08 | `SUPPORT` — `src/backend/apps/users/tests` (139 tests) on `--reuse-db` | exit 0, no failure/error markers in the pytest progress line — **baseline green** |
| V-09 | Session-lifetime claim (`SESSION_COOKIE_AGE` unset anywhere in `src/`) | no occurrence of `SESSION_COOKIE_AGE`, `SESSION_SAVE_EVERY_REQUEST` or `SESSION_EXPIRE_AT_BROWSER_CLOSE` in `src/backend/` — Django's 14-day absolute default applies, and this phase correctly borrows it as a dependency from 04-AUT-006 rather than re-filing it |

**Cleanup performed:** scratch database `val06_probe` dropped (verified absent in
`pg_database`); probe script removed from `.ai/tmp/`. The pre-existing
`probe_run*.py` / `probe_setup.py` scripts and the `audit05v_probe` database
belong to another owner and were left untouched.

## Checkpoint 1 — Auditor analysis

- **Stage:** Auditor analysis
- **Findings in scope:** 16 (CRITICAL 2, HIGH 3, MEDIUM 8, LOW 3)
- **Evidence anchor:** `.ai/audit/06-pii-consent/findings.md`; 12 runtime checks
  (R-01…R-12) against a scratch `audit06_probe` database, plus registered-`ModelAdmin`
  form introspection and a full-source AST scan of every `logger.*` / `stdout.write`
- **Dependencies / blockers:** phantom `mko_bazuna` database (39 tables, no
  `django_migrations`) requires every probe to override the connection; `mko-bazuna-dev`
  web and bot containers are crash-looping, so no live HTTP round-trip is possible
- **Checkpoint status:** closed

## Checkpoint 2 — Researcher verification

- **Stage:** Researcher verification
- **Findings in scope:** 16
- **Cross-phase conflicts:** 2 (VAL-001 DECLINE doc conflict already filed as
  04-VAL-005; VAL-004 the phase-06 rubric contradicts the authoritative spec)
- **Merge candidates:** 3 (PII-103→04-AUT-005; PII-113→04-VAL-005; the
  PII-101/109/110/111/114 erasure-scope cluster, retained separate for rollout
  ordering but sharing one architectural fix)
- **Evidence anchor:** this document
- **Checkpoint status:** closed

## Checkpoint 3 — Per-finding validation

- **Decisions:** Validated unchanged 9 (PII-101, PII-106, PII-109, PII-112,
  PII-114, PII-116, PII-110, PII-107, PII-104 — the last two with narrowed scope)
  · Severity-adjusted 2 (PII-102 CRITICAL→HIGH, PII-111 MEDIUM→LOW)
  · Reclassified 2 (PII-105 HIGH→MEDIUM + type change; PII-108 type change)
  · Merged 2 (PII-103→04-AUT-005, PII-113→04-VAL-005) · Rejected 1 (PII-115)
- **Evidence anchor:** this document; every line reference verified against
  commit `9e96b84`
- **Checkpoint status:** closed

## Checkpoint 4 — Final audit

- **Stage:** Final audit
- **Findings in scope:** 16 (1 CRITICAL, 3 HIGH, 7 MEDIUM, 3 LOW, 1 rejected, 1 merged away)
- **Pipeline integrity:** OK. Every finding carries an explicit verdict; every
  rejection carries a reason; every cross-phase overlap names its counterpart and
  the owning fix; no finding depends on a live source read to be understood.
- **Dependencies / blockers:** VAL-003 (account-state predicate ownership) must be
  settled before PII-104 is implemented. VAL-001 must be settled before either
  PII-105 or 04-AUT-002 changes `can_login()`.
- **Checkpoint status:** closed

---

## Findings by Severity

### CRITICAL

#### PII-101 — [CRITICAL] — CONFIRMED — Support tickets keep the raw Telegram ID and handle after the full 30-day erasure

> **Validation Note:**
> - **Action:** confirmed (severity held; one impact statement struck)
> - **Detail:** The defect reproduces exactly. The auditor's *load-bearing*
>   sub-claim — "no future sweep can ever find it" — is **refuted**: the orphaned
>   row is trivially discoverable via `SupportTicket.objects.filter(user_id__isnull=True)`
>   and via a raw-value scan (V-02). What is true is narrower and still CRITICAL:
>   no sweep *exists* that covers `support_tickets`, and the `SET_NULL` FK removes
>   the only user-scoped handle a future purge would have used, so the defect is
>   silent and self-concealing. Correct the impact wording, keep the severity.
> - **Also added:** `chat_id`/`telegram_id` are **non-nullable** `BigIntegerField`s,
>   so the auditor's "set them to `None`" recommendation requires a migration; the
>   zero-sentinel alternative leaves a `chat_id=0` row that any later sweep must
>   special-case. Prefer nullable columns plus a sentinel for pre-existing rows.
> - **See also:** PII-110, PII-111, PII-114, VAL-011.

| Field | Value |
|---|---|
| **ID** | PII-101 |
| **Type** | SPEC-DEVIATION (privacy / GDPR Art. 17) |
| **Severity** | CRITICAL |
| **Category** | Privacy / right to erasure |
| **File(s)** | `src/backend/apps/core/models.py:115-140` (model), `src/backend/apps/users/services/deletion.py:72-161` (`withdraw_consent`), `src/backend/apps/core/management/commands/consent_hard_delete.py:66-86` (sweep) |
| **Status** | Open |

**Problem.** `SupportTicket` denormalises identity into its own columns:
`chat_id = BigIntegerField(...)` (non-null), `telegram_id = BigIntegerField(...)`
(non-null), `username = CharField(null=True)`, all copied verbatim from the
Telegram sender. The account link is a nullable FK
`user = ForeignKey(AUTH_USER_MODEL, on_delete=SET_NULL, null=True)`.

The erasure contract is expressed as an `update_fields` list on the **`users`**
row only. `withdraw_consent()` never touches `support_tickets`.
`consent_hard_delete` NULLs exactly two references —
`AnalyticsEvent.user_id` and `ModeratorActionLog.user_id` — and then calls
`queryset.delete()`. Django's collector honours the ticket FK's `SET_NULL`, so
the ticket row is **updated to `user_id = NULL` and kept**, with every raw
identifier byte-for-byte intact and no remaining link to any account.

**Impact.** A seller who exercised Art. 17 still has their Telegram numeric ID
and public handle stored in cleartext, indefinitely, in a row that no account
owns. The published policy (`src/backend/templates/privacy.html` §6) promises
"All personal data is permanently erased within 30 days of withdrawal" — this is
a direct, provable breach of that promise and of the erasure clause in
`docs/01-spec/technical-specification.md:86-90`. Every future data-subject-access
or deletion request that touches support history is answered incompletely, and
because the row is orphaned the incompleteness is invisible to any query scoped
through the user.

**Root cause.** The erasure contract is a hand-maintained column list on one
model, with no registry of "tables that copy identity columns". Any table that
denormalises identity falls out of scope the moment it is added, and no test or
check enforces membership. This is the same root cause as PII-109, PII-110,
PII-111 and PII-114 — see **Required Fix 1**.

**Recommendation (validated).**
1. Make `SupportTicket.chat_id` and `.telegram_id` **nullable** (migration) and
   clear `telegram_id`, `chat_id` and `username` for the withdrawing user's
   tickets inside `withdraw_consent()`'s existing `transaction.atomic()` block.
2. In `consent_hard_delete`, clear the same columns for `user_id__in=user_ids`
   **before** `queryset.delete()` so the 30-day path is self-sufficient even if
   the row was never touched at withdrawal time.
3. Add a data migration that scrubs existing rows, including rows already
   orphaned (`user_id IS NULL`) and rows that predate the schema change.
4. Introduce one declarative constant (model → identity columns → erasure action)
   so the service and the migration cannot drift — **Required Fix 1**.

**Effort** M (the nullable migration + data migration, not S as filed) ·
**Priority** P0

| Field | Value |
|---|---|
| **CWE** | CWE-459 (Incomplete Cleanup) |
| **Likelihood** | HIGH |
| **Related** | PII-110, PII-111, PII-114, VAL-011 |

**Runtime evidence (V-02, scratch DB `val06_probe`):**

```text
before sweep  ticket.user_id=1 telegram_id=630000001 chat_id=630000001 username='probe_630000001'
after  withdraw ticket.user_id=1 telegram_id=630000001 chat_id=630000001 username='probe_630000001'
after  withdraw user.telegram_id=None chat_id=630000001 preferred_city=None is_deleted=True
after  sweep   ticket EXISTS=True user_id=None telegram_id=630000001 chat_id=630000001 username='probe_630000001'
after  sweep   user rows=0 ads=0
findable via user_id__isnull=True : 1 row(s) -> [(630000001, 'probe_630000001')]
findable by raw-value scan       : 1 row(s)
```

The last two lines are the correction: the orphan is *not* unfindable. The
finding survives on the retention breach, not on discoverability.

---

### HIGH

#### PII-102 — [CRITICAL] → [HIGH] — ADJUSTED — Raw `chat_id` is written unredacted to WARNING logs on alert-send failure

> **Validation Note:**
> - **Action:** reclassified and severity-adjusted (CRITICAL → **HIGH**)
> - **Detail:** The leak is real, the spec violation is real, and the fix is two
>   lines. What the auditor did not establish is the *blast radius*, and three
>   facts materially reduce it:
>   (a) **The path cannot fire in the shipped configuration.**
>   `config/settings/base.py:349` sets
>   `IMMEDIATE_ALERTS_ENABLED = env.bool("IMMEDIATE_ALERTS_ENABLED", default=False)`,
>   and all four env templates (`.env.example:60`, `.env.dev.example:68`,
>   `.env.prod.example:62`, `.env.test.example:60`) ship `false`. The publish-time
>   fan-out is gated off at `src/backend/apps/moderation/signals.py:66`; the daily
>   `send_alerts` path, which *is* live, logs only `user_id` (a primary key) and
>   never the chat ID.
>   (b) **It fires only on the failure branches** — `TelegramBadRequest` /
>   `TelegramForbiddenError` (permanent, dead-lettered) and post-retry
>   `AiogramError`. The send path itself is clean.
>   (c) **The leaked value is the recipient's own Telegram ID**, landing in an
>   operator-controlled log sink — there is no third-party disclosure.
>   The auditor's most alarming framing ("a user who withdrew consent still has
>   their identifier land in logs after the erasure") is **derivative of PII-104**:
>   it only holds if withdrawn users keep being alerted. Once PII-104 is fixed the
>   framing evaporates, so the two must not be scored as independent CRITICALs.
>   The phase rubric's blanket CRITICAL for "raw identifier in logs" is recorded
>   as a taxonomy defect in **VAL-005**; this instance does not meet it.
> - **The "inconsistent omission" framing is confirmed:** 12 masked call sites
>   exist across 5 modules (`telegram_bot/handlers/login.py:116`;
>   `apps/users/views/consent.py:435,444,452,467`; `apps/users/admin.py:131`;
>   `apps/core/services/contact.py:134`; `apps/moderation/admin_actions.py:109`;
>   `apps/core/management/commands/create_admin_user.py:81,99,122,128`) against
>   these 2 unmasked ones.
> - **See also:** PII-112 (makes the surrounding mask worthless), PII-104,
>   PII-106, VAL-005.

| Field | Value |
|---|---|
| **ID** | PII-102 |
| **Type** | SPEC-DEVIATION (log hygiene) |
| **Severity** | HIGH *(downgraded from CRITICAL)* |
| **Category** | Privacy / log hygiene |
| **File(s)** | `src/backend/apps/search/services/immediate_alerts.py:176-180` (payload), `:210-216` (permanent-failure branch), `:235-240` (retry-failure branch); gate at `src/backend/apps/moderation/signals.py:66`; flag at `src/backend/config/settings/base.py:349` |
| **Status** | Open |

**Problem.** `_build_payload()` copies `user.chat_id` verbatim into the payload
dict, and both failure branches in `_send_payloads()` interpolate
`payload["chat_id"]` into a `logger.warning` call with no masking. The project
has a dedicated masker (`apps/core/utils/sanitize.py:134`), applies it at 12
other sites, and a written spec rule — `docs/01-spec/technical-specification.md:90`
— states "All `telegram_id` values in logger calls and `stdout.write` output are
masked … Raw telegram_id must never appear in logs." This is an omission, not a
policy choice.

**Impact (validated).** A transient or permanent Telegram failure writes an
unmasked Telegram user ID into WARNING-level logs while the immediate-alert
feature is enabled. WARNING logs are the most widely shipped and longest-retained
tier. No data subject's identifier is exposed to a third party, and the path is
dormant under the default configuration — which is why this is HIGH and not
CRITICAL. It must still be fixed before `IMMEDIATE_ALERTS_ENABLED` is turned on
in any environment.

**Root cause.** Masking is applied per-value, per-call-site. There is no shared
formatter or filter, so coverage is a matter of reviewer attention.

**Recommendation (validated).**
1. **Required:** mask at the two log sites with `mask_telegram_id(...)`. Two
   lines, no schema change, no data risk.
2. **Required as a rollout gate:** do not enable `IMMEDIATE_ALERTS_ENABLED`
   anywhere until (1) and PII-112 are both closed — the surrounding masker is
   reversible (PII-112), so masking into it buys nothing on its own.
3. **Advisory only — do NOT build the logging `Filter` proposed in the
   recommendation as filed.** A filter that "refuses any record argument named
   `chat_id`/`telegram_id`" is a naming-convention guard, not a type system: it
   cannot see `user.chat_id` passed positionally, and it adds a global logging
   behaviour change to close two call sites. Negative ROI at this project scale
   (project rule 5, *Avoid Overengineering*). If the team wants the invariant
   later, the durable form is a typed `Identity` value object, not a filter.

**Effort** S · **Priority** P1 (P0 only if `IMMEDIATE_ALERTS_ENABLED` is enabled)

| Field | Value |
|---|---|
| **CWE** | CWE-532 (Insertion of Sensitive Information into Log File) |
| **Likelihood** | MEDIUM (gated off by default) |
| **Related** | PII-112, PII-104, PII-106, VAL-005 |

---

#### PII-103 — [HIGH] — MERGED into `04-AUT-005` — `UserAdmin`'s auto-built form exposes identity and consent state to any staff user

> **Validation Note:**
> - **Action:** merged
> - **Merged into:** **`04-AUT-005`** (phase 04, *auth/login*), whose validation
>   already absorbed the identical evidence as `04-VAL-004`.
> - **Detail:** **Same root cause, byte for byte.** `src/backend/apps/users/admin.py:14-53`
>   declares no `fields`, no `fieldsets` and no `form`, so Django's
>   `ModelAdmin.get_form()` auto-builds a `ModelForm` over every editable model
>   field. Phase 04's validator discovered this independently and used form
>   introspection to prove the credential half: `password` bound as a
>   `CharField(AdminTextInputWidget)`, written verbatim by `save_model` →
>   `obj.save()` with no `pre_save` hasher. PII-103 is the same defect seen from
>   the PII angle — the identity and consent-flag half of the same 22-field form.
>   The validator reproduced both halves independently (V-03) and obtained the
>   identical 22-field list.
> - **Why merge rather than file twice:** they are one `fieldsets` declaration.
>   Two patches to the same class would be a partial fix at best. `04-AUT-005` is
>   already validated, already rated **HIGH**, and already sits at Required Fix #1
>   in that report — it is the correct absorbing finding.
> - **Merged content that `04-AUT-005` must now also carry** (this is the part
>   phase 04 could not know): the same `fieldsets` must additionally put
>   `telegram_id`, `chat_id`, `username`, `first_name`, `last_name`, `email` in a
>   read-only identity section, and must **remove** `is_declined`, `is_deleted` and
>   `ads_auto_publish` from the form entirely — not merely mark them read-only —
>   so that every consent-state transition is forced through the service that also
>   writes the audit row and bumps the search-cache version (PII-107, PII-105).
>   A moderator flipping `is_declined` back to `False` today produces a public
>   ad set with **no** `consent_given_at`, **no** `ConsentRecord` and **no**
>   cache-version bump.
> - **Ownership note:** the *permission* half (`has_change_permission` returns
>   `request.user.is_staff`, and `is_staff` **is** the moderator role —
>   `User.role` maps `is_staff`/`is_superuser` to `ADMIN` and no separate
>   moderator role exists) is Phase 15's territory per
>   `.kilo/commands/audit/phases/15-audit-authorization.md:126` ("admin
>   protection"). The *field set* and the *root cause* are not. Recorded as
>   **VAL-002**.
> - **Content preserved below for reference; not to be re-implemented from here.**

| Field | Value |
|---|---|
| **ID** | PII-103 |
| **Type** | SPEC-DEVIATION (improper access control) |
| **Severity** | HIGH *(absorbed into 04-AUT-005)* |
| **Category** | Privacy / access control |
| **File(s)** | `src/backend/apps/users/admin.py:14-53` |
| **Merged into** | `04-AUT-005` (+ `04-VAL-004`) |
| **Status** | Open (tracked as 04-AUT-005) |

**Problem.** `UserAdmin` (`src/backend/apps/users/admin.py:14-53`) declares
`list_display`, `list_filter`, `search_fields` and `readonly_fields` — the latter
covering only the three consent *timestamps* (`consent_given_at`,
`consent_revoked_at`, `deleted_at`) — and nothing else. With no `fields`,
`fieldsets` or `form`, Django auto-builds a `ModelForm` over the whole model.
`has_change_permission` returns `request.user.is_staff`, which is the only
moderator role in the product.

**Impact (two distinct consent-integrity failures).**
(a) A moderator can write a fresh `telegram_id`/`chat_id` into a soft-deleted,
consent-withdrawn account, re-attaching an identity whose PII was deliberately
erased — defeating the guarantee that `withdraw_consent()`'s `LoginToken`
invalidation exists to provide ("breaks chat linkage").
(b) A moderator can flip `is_declined` back to `False` without going through
`give_consent()`, which sets `consent_given_at`, `ads_auto_publish=True` and
clears `consent_revoked_at` in one `update_fields` save. Bypassing it produces
ads that are public again with no consent timestamp, no `ConsentRecord` row, and
no `transaction.on_commit(bump_search_cache_version)` — so cached result sets can
keep serving the pre-decline state.
Plus, from phase 04: a moderator can read a superuser's PBKDF2 hash as cleartext
and write an arbitrary string **unhashed**, permanently destroying that credential.

**Recommendation.** See **Required Fix 2** — a single `fieldsets` declaration plus
a purpose-built form, owned by `04-AUT-005`.

| Field | Value |
|---|---|
| **CWE** | CWE-284 (Improper Access Control) / CWE-640 (Weak Password Recovery) |
| **Likelihood** | MEDIUM |
| **Related** | 04-AUT-005, 04-VAL-004, PII-105, PII-107, VAL-002 |

**Runtime evidence (V-03, form introspection only, no rows written):**

```text
form class        : UserForm
editable fields (22): ['ads_auto_publish', 'chat_id', 'date_joined', 'email', 'first_name',
  'groups', 'is_active', 'is_banned', 'is_declined', 'is_deleted', 'is_staff', 'is_superuser',
  'last_login', 'last_name', 'password', 'preferred_city', 'source', 'telegram_id',
  'telegram_language', 'telegram_premium', 'user_permissions', 'username']
  password         CharField    required=True  widget=AdminTextInputWidget
  telegram_id      IntegerField required=False widget=AdminBigIntegerFieldWidget
  chat_id          IntegerField required=True  widget=AdminBigIntegerFieldWidget
  username         CharField    required=False widget=AdminTextInputWidget
  is_declined      BooleanField required=False widget=CheckboxInput
  is_deleted       BooleanField required=False widget=CheckboxInput
  is_banned        BooleanField required=False widget=CheckboxInput
  ads_auto_publish BooleanField required=False widget=CheckboxInput
declared fields/fieldsets/form : None None ModelForm
readonly_fields  : ['consent_given_at', 'consent_revoked_at', 'deleted_at']
has_change_permission(moderator) = True
UserAdmin.actions attr           = ()      # withdraw_consent_action is UNWIRED
```

The last line independently confirms the PII-107 correction: `withdraw_consent_action`
is decorated `@admin.action` but `UserAdmin` never assigns `actions`, so it is
not reachable from the admin UI today.

---

#### PII-104 — [HIGH] — CONFIRMED / NARROWED — The outbound Telegram alert channel ignores consent and account state

> **Validation Note:**
> - **Action:** confirmed; scope narrowed; dependency added
> - **Detail:** Reproduced exactly (V-04). Two narrowing corrections:
>   (a) **The declined-buyer half is struck.** `technical-specification.md:101`
>   defines DECLINE as "browse-only: blocks seller login/actions AND hides the
>   user's PUBLISHED ads" — it says nothing about suppressing Telegram messages to
>   a browse-only visitor, and the banner copy is about *cookies*, not contact.
>   Messaging a declined *buyer* is consistent with the spec, not a violation.
>   (b) **The banned-user half is weakened.** `is_banned` blocks login and
>   publishing; nothing in the spec says a banned account must be excluded from
>   the market, and a ban is a moderation action, not a consent action. Keep the
>   filter, but stop citing it as a consent breach.
>   What remains is genuinely HIGH and *is* a consent breach: a user who
>   **withdrew** consent keeps receiving daily digests derived from their own
>   saved-search history for the full 30-day window, and a **declined seller's
>   hidden ad** fans out with its title and price to every matching subscriber —
>   content the spec says is not publicly visible.
> - **Important condition the auditor omitted:** the leak is **live on the daily
>   path** and **latent on the immediate path**. `send_alerts` runs daily at
>   08:00 UTC (`scheduler.DAILY_COMMANDS`, `DAILY_HOUR_UTC = 8`) and is not feature-
>   gated. `deliver_immediate_alerts` is gated off by default (see PII-102) — and
>   it is the path that would additionally ship a **working deep link** to the
>   hidden ad (`build_alert_message` renders `ad.get_absolute_url()`), which is
>   worse than the digest's title+price. The audience filter must land **before**
>   `IMMEDIATE_ALERTS_ENABLED` is ever turned on.
> - **Cross-phase dependency (VAL-003):** the recommended fix is not a one-line
>   filter. `apps/users/services/account_state.get_account_state()` is an
>   **instance-level** helper; what `apps/search` needs is a **queryset-level**
>   predicate. Writing `SavedSearch.objects.filter(user__is_deleted=False, …)`
>   in the search app duplicates the rule and creates a second place to forget
>   the next flag. This needs an owner decision and one shared declarative
>   predicate, not a copy.
> - **See also:** PII-102, PII-110 (`chat_id` retention is the mechanical reason
>   the channel still works), PII-109, VAL-003.

| Field | Value |
|---|---|
| **ID** | PII-104 |
| **Type** | SPEC-DEVIATION (consent propagation) |
| **Severity** | HIGH *(held; scope reduced)* |
| **Category** | Privacy / consent propagation |
| **File(s)** | `src/backend/apps/search/management/commands/send_alerts.py:80,112,170-174`; `src/backend/apps/search/services/alert_query.py:43,153`; `src/backend/apps/search/services/immediate_alerts.py:93-113,164-180`; `src/backend/apps/search/models.py:67-71` (`SavedSearch.user` = `CASCADE`); `src/backend/apps/users/services/account_state.py:26-48` |
| **Status** | Open |

**Problem.** Both alert paths select their audience purely by
`SavedSearch.is_active=True`:
- `send_alerts._collect_alerts()` iterates `SavedSearch.objects.filter(is_active=True)`;
  `_send_user_digests()` then checks only `user.chat_id` before sending.
- `find_matching_saved_searches()` (publish-time fan-out) applies the same single
  filter; `find_matching_ads()` selects `Ad.objects.filter(status=PUBLISHED)` with
  no `user__is_declined=False` clause.

Neither path consults `is_deleted`, `is_declined`, `consent_revoked_at` or
`is_banned`. Because `withdraw_consent()` nulls `telegram_id` but deliberately
keeps `chat_id` ("never nullified" — `users/models.py:49-53`), and `SavedSearch`
is `CASCADE`-deleted only when the user row is finally removed 30 days later, the
delivery target survives the entire withdrawal window.

**Impact (validated).** A user who asked to be forgotten keeps receiving daily
Telegram digests derived from their own saved searches for up to 30 days — the
precise processing the withdrawal exists to stop. Separately, the ad content of a
DECLINED seller — which `technical-specification.md:101` says is hidden from
public search, listings, direct URL access and the media gate — is pushed to every
matching subscriber anyway, and the message body itself (`_format_digest`)
carries the title and price that the site refuses to show. Every one of these
sends is also the event that produces the unmasked log line in PII-102.

**Root cause.** Account state is enforced at the *interaction* boundary (the
bot's `AccountStateMiddleware`, the web views) but not at the *proactive delivery*
boundary. `send_alerts` and `immediate_alerts` treat `SavedSearch.user` as a
plain FK and never join the consent predicate. The instance-level helper
`get_account_state()` has no queryset-level counterpart, so there is nothing to
reuse — which is precisely why the rule was never applied here.

**Recommendation (validated).**
1. **Owner decision first (VAL-003):** add one **queryset-level** consent
   predicate owned by `apps/users` (e.g. a named `UserQuerySet` method or a
   documented `Meta`-free helper returning the filtered queryset) and consume it
   from both alert paths. Do **not** add a global default manager filter — that
   would silently change every `User.objects` query in the codebase. Do **not**
   "fix" this by nulling `chat_id`: `AccountStateMiddleware._get_user` resolves
   users by `chat_id` precisely so withdrawn identities stay blocked, and
   nulling it would re-open a different hole.
2. Also exclude ads whose owner is DECLINED from `find_matching_ads()` and
   `find_matching_saved_searches()`, so hidden content cannot fan out even if a
   subscriber is otherwise eligible (this is the PII-109 overlap).
3. Additionally, in `withdraw_consent()`, `SavedSearch.objects.filter(user=user)
   .update(is_active=False)` and delete the user's `SearchHistory` rows inside the
   same transaction, so revocation actively tears down subscriber state instead of
   relying on a future filter. (This also discharges part of PII-110.)
4. Gate the `IMMEDIATE_ALERTS_ENABLED` rollout on (1) and (2).

**Effort** S for the filter, M for the shared predicate + decision ·
**Priority** P0

| Field | Value |
|---|---|
| **CWE** | CWE-359 (Exposure of Private Personal Information) |
| **Likelihood** | HIGH (live on the daily path) |
| **Related** | PII-102, PII-105, PII-109, PII-110, VAL-003 |

**Runtime evidence (V-04, scratch DB `val06_probe`):**

```text
active     is_declined=False is_deleted=False is_banned=False revoked=False chat_id=630000005
declined   is_declined=True  is_deleted=False is_banned=False revoked=False chat_id=630000002
withdrawn  is_declined=False is_deleted=True  is_banned=False revoked=True  chat_id=630000003
banned     is_declined=False is_deleted=False is_banned=True  revoked=False chat_id=630000004
ad rows in DB: [(2, 'published', True)]          # status published, owner IS declined
  find_matching_ads(active    ) -> ['HIDDEN declined seller ad']
  find_matching_ads(declined  ) -> ['HIDDEN declined seller ad']
  find_matching_ads(withdrawn ) -> ['HIDDEN declined seller ad']
  find_matching_ads(banned    ) -> ['HIDDEN declined seller ad']
hidden (declined-seller) ad visible in public ListingsQuery: False
find_matching_saved_searches(hidden ad) -> [7, 4, 5, 6, 7]
```

---

#### PII-105 — [HIGH] → [MEDIUM] — ADJUSTED + RECLASSIFIED — DECLINE's recovery affordance is broken and undiscoverable

> **Validation Note:**
> - **Action:** reclassified; severity adjusted (HIGH → **MEDIUM**)
> - **Type changed:** `Consent semantics / availability` (implying a code defect)
>   → **DOC-UPDATE + BEST-PRACTICE** (the wrong artifacts are documents and
>   user-facing copy, not the consent state machine).
> - **Detail:** The finding bundles three claims. Two of them are **not defects**:
>   DECLINE hiding published ads, and DECLINE blocking login, are both *explicitly
>   specified* in `docs/01-spec/technical-specification.md:85, 96, 101` — the
>   authoritative document, which describes the implemented behaviour in
>   implementation detail ("live `user__is_declined=False` filter in
>   `ListingsQuery` + `ad_detail` queryset + `ad__user__is_declined=False` in
>   `media_gate`; search cache version bumped via `transaction.on_commit`"). The
>   code matches that spec (V-04, V-05). The one contradicting statement is a
>   condensed index line, `docs/01-spec/spec-index.md:74` — that is a **doc**
>   defect, tracked as **PII-113**, not a code defect.
>   The third claim is real and is the one worth keeping: **the recovery
>   affordance is broken and undiscoverable.** Verified end-to-end (V-05):
>   - With a live session: `/?ref=preferences` → banner renders → POST
>     `/consent/accept/` → `is_declined=False`, `can_login=True`, HTTP 302. Works.
>   - With no session (the state every user reaches after the 14-day default
>     session lifetime): `/?ref=preferences` → banner renders → POST
>     `/consent/accept/` → **HTTP 302 to `/`, `is_declined` unchanged,
>     `can_login` unchanged, no error message.** A **silent no-op**: the user is
>     told nothing, the banner disappears (the `consent_given` cookie is set to
>     `accepted`), and their ads stay hidden with no path back. The mechanism is
>     `consent_accept` only calling `give_consent()` when
>     `request.user.is_authenticated` (`views/consent.py:149-159`).
>   - The banner is additionally **hidden for a declined user by default**, because
>     `consent_state()` sets `consent_shown = True` whenever `user.is_declined`
>     (`context_processors.py:61-66`) and the template renders on
>     `{% if not consent_shown %}`. The only way back in is the
>     `?ref=preferences` link — which is the one thing `privacy.html` §7 tells
>     users to click, and it delivers a silent no-op once the session is gone.
> - **Severity rationale:** the advertised consequence ("permanent loss of ad
>   visibility") is real but *operator-recoverable* (one DB edit) and the
>   behaviour itself is spec-sanctioned; the residual defect is a false public
>   policy statement plus a dead-end UI, with an affected population of
>   sellers who both have published ads *and* click Decline. The 14-day figure is
>   correct but is **not this phase's to fix** — it is the unset
>   `SESSION_COOKIE_AGE`, already filed as `04-AUT-006`. Borrowing another
>   phase's unconfigured default as the load-bearing element of a HIGH was the
>   main over-rating.
> - **Owner decision required** (unchanged from the auditor, and it is the right
>   call): the *spec itself* sanctions a silent, effectively irreversible takedown
>   of live listings as a side effect of clicking a cookie banner. That is a
>   product decision, not an implementation bug, and it should be made
>   explicitly. **This phase does not pre-decide it.**
> - **See also:** PII-113, PII-103, PII-104, 04-AUT-002, 04-AUT-006, 04-VAL-005.

| Field | Value |
|---|---|
| **ID** | PII-105 |
| **Type** | **DOC-UPDATE + BEST-PRACTICE** (was: consent semantics / availability) |
| **Severity** | MEDIUM *(downgraded from HIGH)* |
| **Category** | Consent semantics / user-facing recovery affordance |
| **File(s)** | `src/backend/apps/users/views/consent.py:149-159` (`consent_accept` requires authentication), `:204-213` (`consent_decline` does not flush the session), `src/backend/apps/users/context_processors.py:61-66, 105-106` (banner hidden for a declined user; `?ref=preferences` override), `src/backend/apps/users/services/account_state.py:96-106` (`can_login` denies `is_declined`), `src/backend/templates/privacy.html` §7, `src/backend/templates/components/consent_banner.html:4` |
| **Status** | Open — **owner decision required before implementation** |

**Problem (validated).** `can_login()` returns `False` for any `is_declined`
user, with no reversal path in the service layer. `consent_decline` does not
flush the session, so the only route back to `give_consent()` is a `POST
/consent/accept/` from an *authenticated* session. No `SESSION_COOKIE_AGE`,
`SESSION_SAVE_EVERY_REQUEST` or `SESSION_EXPIRE_AT_BROWSER_CLOSE` is configured
anywhere in `src/backend/` (V-09), so Django's 14-day **absolute** default
applies and is **not** extended by activity. Meanwhile
`src/backend/templates/privacy.html` §7 states: *"You can revisit and change your
consent choices at any time"*, and points users at `?ref=preferences` — the exact
path that becomes a silent no-op once the session expires. For a declined user
the banner is hidden by default, so no other in-product affordance exists.

**Impact (validated).** A seller who clicks "Reject non-essential" has their
already-published advertisements removed from public listings, search, direct
URL access and the media gate within the same transaction. Inside the session
window they can undo it. After the window they click the link the privacy policy
tells them to click, receive HTTP 302 and no error, and their ads stay hidden
indefinitely. The published policy statement is therefore false, and the failure
is silent rather than reported. The state is recoverable only by a direct
database edit.

**Root cause.** `is_declined` serves as both a *visibility* switch and a *login*
switch; the login switch has no first-class escape hatch, so reversibility
depends on ambient session state that is neither documented nor surfaced. The
`consent_state` processor compounds it by hiding the only re-entry UI from the
very users who need it.

**Recommendation (validated).** Decide and document one coherent model, then
implement it.
- *Option (a), recommended — DECLINE is reversible by design:* remove
  `is_declined` from `can_login()` while keeping it in `can_publish_ad()` and the
  bot's publish gate. This costs one spec edit
  (`technical-specification.md:101`, `spec-index.md:74`) and removes a
  content-takedown failure mode. **It changes the auth predicate and will break
  `src/backend/apps/users/tests/test_account_state.py:160-168`, which asserts
  `can_login(is_declined=True) is False` — that test must be updated, not worked
  around (project rule 2).** Coordinate with `04-AUT-002`, which also touches the
  web-side account-state gate.
- *Option (b) — DECLINE is intentionally one-way:* then it must not silently
  un-publish existing ads without warning, and `privacy.html` §7 must be corrected
  to say the choice is final for seller features.
- **Required under either option:** a first-class, password-less recovery path
  that does not depend on a live session — e.g. a `POST /consent/resume/`
  reachable from the bot and from the public page that re-authenticates *only*
  enough to flip `is_declined`, with an explicit `ConsentRecord`. Today the
  equivalent action is a no-op when anonymous.
- **Required under either option:** stop hiding the banner from a declined user
  (`context_processors.py:61-66`), or add a persistent, discoverable "review your
  consent choices" affordance on the dashboard that does not require
  `?ref=preferences`.
- **Required:** make the anonymous "Accept" non-silent — either mutate the row or
  return an explanatory page.
- **Copy/i18n note:** every new or changed string must ship `ru` and `bs`
  translations or `test_i18n_completeness.py` fails. See **VAL-006**.

**Effort** M · **Priority** P1

| Field | Value |
|---|---|
| **CWE** | CWE-672 (Operation on a Resource after Expiration or Release) |
| **Likelihood** | MEDIUM |
| **Related** | PII-113, PII-103, PII-104, 04-AUT-002, 04-AUT-006, 04-VAL-005, VAL-001, VAL-006 |

**Runtime evidence (V-05, Django test client, scratch DB):**

```text
# authenticated path — WORKS
after POST decline    is_declined=True  can_login=False
ad visible in public listings : False
authenticated ?ref=preferences -> banner html present: True
after AUTHENTICATED accept  is_declined=False can_login=True  status=302

# logged-out path (the state after the default 14-day session) — SILENT NO-OP
session cookie present after decline: True
ANONYMOUS ?ref=preferences -> banner present: True
after ANONYMOUS accept  is_declined=True can_login=False  status=302 redirect=/
   -> DB state changed by the anonymous 'Accept'? False
```

---

### MEDIUM

> PII-106, 107, 108, 109, 110, 112 and 113 remain MEDIUM. **PII-111 is listed
> below under this heading only for continuity — it was adjusted down to LOW**;
> see its Validation Note. Do not count this section as eight MEDIUM findings.

#### PII-106 — [MEDIUM] — CONFIRMED — `SupportTicketAdmin` renders raw identifiers and full-text-searches ticket bodies

> **Validation Note:**
> - **Action:** confirmed; recommendation **narrowed** (one element rejected)
> - **Detail:** The defect reproduces exactly:
>   `src/backend/apps/core/admin.py:56-58` puts raw `chat_id` and `telegram_id`
>   in `list_display` and `["ticket_ref", "telegram_id", "username", "text"]` in
>   `search_fields`, while the project's own containment rule
>   (`LoginTokenAdmin.telegram_id_display` → `mask_telegram_id`) and its standing
>   regression test `src/backend/apps/users/tests/test_admin_pii_containment.py`
>   were never extended to `apps/core`.
> - **One recommendation element rejected.** The proposal to generalise
>   `test_admin_pii_containment.py` into a walk over **every** registered
>   `ModelAdmin` asserting "no `list_display` entry renders a raw identity
>   column" would produce a **false positive on `SupportContactAdmin`**
>   (`apps/core/admin.py:41`), whose `telegram_id` is a *configured support
>   channel* ID, not a data subject's — and that model legitimately has no
>   `readonly_fields`/`has_change_permission` override because channels are
>   meant to be staff-editable. A blanket registry-wide assertion is therefore
>   wrong as written. The test must enumerate an explicit allow/deny list of
>   *data-subject* identity columns, or be scoped to a declared set of
>   user-adjacent models. Recorded as **VAL-007**.

| Field | Value |
|---|---|
| **ID** | PII-106 |
| **Type** | SPEC-DEVIATION (admin PII containment) |
| **Severity** | MEDIUM *(held)* |
| **Category** | Privacy / admin surface |
| **File(s)** | `src/backend/apps/core/admin.py:47-75`; rule precedent `src/backend/apps/users/admin.py:128-131`; guard `src/backend/apps/users/tests/test_admin_pii_containment.py` |
| **Status** | Open |

**Problem.** `SupportTicketAdmin.list_display = ["ticket_ref", "status", "user",
"chat_id", "telegram_id", "created_at"]` renders both raw Telegram identifiers in
cleartext in the staff changelist, and `search_fields = ["ticket_ref",
"telegram_id", "username", "text"]` makes the entire unbounded ticket body a
full-text search target for any `is_staff` account. The ticket model's own
`readonly_fields` (`:59-67`) already marks these columns read-only on the *change*
form — the changelist and the search index were simply never brought under the
containment rule that `LoginTokenAdmin` already follows.

**Impact.** A single changelist screenshot, CSV export or support bundle is a bulk
PII disclosure of the requester's numeric Telegram ID, in the one admin surface the
product explicitly designed to prevent that. `text` in `search_fields` additionally
turns the whole support corpus into a free-text search target for the moderator
role.

**Root cause.** The admin PII-containment work was done per-model
(`users`, `ads`, `analytics`, `moderation`); `SupportTicket` lives in a different
app and was not part of the sweep, and the guard test hard-codes four named
helpers rather than deriving the rule.

**Recommendation (validated).**
1. Replace the two raw `list_display` columns with masked display methods reusing
   `mask_telegram_id` (as `LoginTokenAdmin` already does).
2. Drop `text` from `search_fields`; keep `ticket_ref` plus `telegram_id`/
   `username` for genuine support lookups.
3. Extend `test_admin_pii_containment.py` with an **explicit, declared set of
   data-subject identity columns** per registered admin (not a blanket
   "no raw `telegram_id` anywhere" rule — see VAL-007), so the next user-adjacent
   model cannot regress it.

**Effort** S · **Priority** P1

| Field | Value |
|---|---|
| **CWE** | CWE-200 (Exposure of Sensitive Information) |
| **Likelihood** | MEDIUM |
| **Related** | PII-101, PII-112, VAL-007 |

---

#### PII-107 — [MEDIUM] — CONFIRMED — `withdraw_consent()` writes no `ConsentRecord`

> **Validation Note:**
> - **Action:** confirmed; **root-cause rationale corrected**
> - **Detail:** The defect and the reachability correction are both confirmed.
>   `record_consent_action(...)` is called from exactly three places, all HTTP
>   views (`apps/users/views/consent.py:168, 221, 268`); `withdraw_consent()`
>   itself never touches `ConsentRecord`. The only non-view caller of
>   `withdraw_consent()` in production code is
>   `UserAdmin.withdraw_consent_action` (`apps/users/admin.py:63-64`) — and V-03
>   independently confirms `UserAdmin.actions == ()`, so
>   `get_actions(request)` returns only `delete_selected` and the action is
>   unreachable from the admin UI today. Correctly filed as a structural defect
>   rather than an active operator surface.
> - **Root cause as stated is wrong.** The finding claims "`record_consent_action`
>   is also `request`-aware, which makes it awkward to call from non-HTTP
>   contexts, encouraging the split." In fact `record_consent_action` already
>   takes `request: HttpRequest | None = None` and documents `None` as the
>   bot-entry-point case (`apps/users/services/consent_record.py:41, 48-52, 64-71`).
>   The service could call it today with no signature change. The real root cause
>   is simpler and stronger: the consent *state* mutation lives in
>   `deletion.py` and the consent *audit* write lives in `views/consent.py`, and
>   nobody noticed the two are in different layers because the only caller that
>   exercised both was a view.
> - **The auditor's own note that the bot writes no `ConsentRecord` is correct
>   and is not a gap:** `technical-specification.md:104` states the site banner
>   covers all PII processing "including the bot; no separate bot confirmation
>   required", and no bot consent action exists to record.

| Field | Value |
|---|---|
| **ID** | PII-107 |
| **Type** | SPEC-DEVIATION (Art. 7(1) accountability) |
| **Severity** | MEDIUM *(held)* |
| **Category** | Consent / accountability |
| **File(s)** | `src/backend/apps/users/services/deletion.py:72-161`; `src/backend/apps/users/services/consent_record.py:37-81`; `src/backend/apps/users/views/consent.py:168,221,268`; `src/backend/apps/users/admin.py:55-65` |
| **Status** | Open |

**Problem.** The Art. 7(1) audit row for a withdrawal is written by the **view**,
after the service call returns, in a separate statement outside
`withdraw_consent()`'s `transaction.atomic()` block. Any non-view caller revokes
consent with no audit trail. The only such caller is the staff action
`UserAdmin.withdraw_consent_action`, which loops the queryset and calls
`withdraw_consent(user)` directly — and which is, today, dead code (decorated
`@admin.action`, never assigned to `UserAdmin.actions`).

**Impact.** The operation that performs the erasure owns no evidence that it
happened. `consent_hard_delete` keys off `users.consent_revoked_at` for a row
that may have no corresponding `choice='WITHDRAWN'` record, so the erasure log
and the consent-audit log can disagree — which is precisely the state Art. 7(1)
exists to make demonstrable. The concrete exposure today is bounded (the action
is unwired), but the defect is structural: the first person to wire that action
inherits the gap silently.

**Root cause.** The consent *state* mutation and the consent *audit* write live
in two different layers and are only ever called together from an HTTP view.
`record_consent_action` already supports `request=None`, so the split is not
forced by the helper's signature.

**Recommendation (validated).**
1. Move the audit write into the service layer: give `withdraw_consent()` (and
   `decline_consent()` / `give_consent()` for symmetry) an explicit optional
   context — prefer a small typed value object over passing `HttpRequest` down
   into the domain layer (project rule 3, *Separation of Concerns*) carrying
   `ip_address`, `user_agent`, `session_key` — and write the `ConsentRecord`
   inside the same `transaction.atomic()` block, so state and evidence commit or
   roll back together.
2. Decide the intent of `withdraw_consent_action`: if moderator-initiated
   revocation is a real operator workflow, wire it (`actions = [...]`, gated on
   `is_superuser`) now that it is auditable; if not, delete it rather than leaving
   an unwired landmine. Per the dead-code policy this is a wire-or-remove decision,
   not a delete recommendation.
3. Add a test asserting a `choice='WITHDRAWN'` `ConsentRecord` exists after the
   **service** call, not only after the view.

**Effort** S · **Priority** P1

| Field | Value |
|---|---|
| **CWE** | CWE-778 (Insufficient Logging) |
| **Likelihood** | HIGH (structural) |
| **Related** | PII-103 (merged → 04-AUT-005), PII-101, PII-116, 06-PII-103 |
| **Depends on** | PII-103's `fieldsets` fix must land with or before this, so no admin path can mutate consent state without the audit row |

---

#### PII-108 — [MEDIUM] — ADJUSTED + RECLASSIFIED — First-party analytics/search-history writes and the recorded `analytics` consent flag disagree

> **Validation Note:**
> - **Action:** reclassified; framing corrected; one element **strengthened**
> - **Type changed:** `Privacy / consent enforcement` (implying a violated gate)
>   → **DOC-UPDATE + BEST-PRACTICE** (a consent-*taxonomy* collision).
> - **Detail:** The spec has already decided this question, and it decided it the
>   way the code behaves. `docs/01-spec/technical-specification.md:161` states
>   Plausible is "cookieless … no consent banner needed (legitimate interest)",
>   and `:163` states "Privacy: Plausible collects no PII; `user_id` references
>   already-collected `telegram_id`." So first-party `AnalyticsEvent` rows
>   carrying a `user_id` are documented and intentional. There is no violated
>   gate to enforce; the finding's own "decision required" framing concedes this.
>   What survives is narrower: the word `analytics` is used for **two different
>   things** — "third-party Plausible JS" (what the banner actually gates, and
>   what the banner copy says: "anonymized traffic analytics via Plausible") and
>   "the `analytics` key in `consent_records.categories`" (recorded as if it
>   covered all measurement). A reviewer reading `ConsentRecord.categories` cannot
>   tell which was granted. That is a documentation and naming defect.
> - **One element strengthened (a real defect the auditor missed).** The finding
>   says "full search-query text in `search_history`". That is imprecise and, read
>   literally, wrong: `record_search_history()` stores the **redacted** string in
>   `SearchHistory.query` via `redact_search_query()`
>   (`apps/search/services/search_history.py:65, 79-83`). But the same function
>   stores **`query_normalized` = the raw, lower-cased, un-redacted query** as the
>   dedup/lookup key (`:58, 81`). So phones, emails and personal names that
>   `redact_search_query` deliberately strips from `query` survive verbatim in
>   `query_normalized`, for as long as the row lives (`CASCADE` only — no
>   withdrawal-time purge, unlike `SavedSearch`). That is a concrete PII
>   retention defect inside the same tables and is now part of this finding.

| Field | Value |
|---|---|
| **ID** | PII-108 |
| **Type** | **DOC-UPDATE + BEST-PRACTICE** (was: privacy / consent enforcement) |
| **Severity** | MEDIUM *(held)* |
| **Category** | Privacy / consent taxonomy; search-history PII retention |
| **File(s)** | `src/backend/apps/search/views/search.py:336-339`; `src/backend/apps/search/services/search_history.py:43-94` (esp. `:58, 65, 79-83`); `src/backend/apps/ads/views/listings.py` (`ad_detail` → `record_event`); `src/backend/apps/core/services/analytics.py:19-60`; `src/backend/apps/users/context_processors.py:56-72`; `src/backend/apps/search/models.py:43-61`; spec `docs/01-spec/technical-specification.md:161,163` |
| **Status** | Open |

**Problem.** The system records a granular per-category `analytics` consent flag
(`ConsentRecord.categories`, the `consent_analytics` cookie, the `consent_state`
context processor), but that flag is consumed **only** by template
`{% if consent_analytics %}` guards around the Plausible snippet and the
GLightbox JS. No server-side write path consults it: `search.py:336` records
`SEARCH_PERFORMED` with `user_id=request.user.id` for any authenticated visitor,
`record_search_history()` persists a row for any authenticated visitor, and
`ad_detail` records `AD_VIEWED`. The spec sanctions this under legitimate
interest; the artefact name implies otherwise.

**Impact (validated).** A user who declined — for whom `consent_state` forces
`consent_analytics=False` and `consent_preferences=False`
(`context_processors.py:68-72`) — still accumulates `search_performed` rows under
their identity. That part is spec-permitted. The parts that are **not**:
(1) the recorded artefact is misleading as evidence of what was consented to;
(2) `SearchHistory.query_normalized` retains the **un-redacted** query, so
personal names, phone numbers and e-mail addresses that `redact_search_query`
strips from `query` are persisted verbatim and are `CASCADE`-only — they survive
DECLINE indefinitely and WITHDRAW for the full 30 days.

**Root cause.** The consent taxonomy has one name for two scopes, and the
redaction helper is applied to the display column but not to the index column
derived from the same input.

**Recommendation (validated).**
1. Rename or re-scope the recorded flag so the artefact and the enforcement point
   agree — e.g. keep `categories["analytics"]` but document it as
   *"third-party analytics scripts"* in `privacy.html` §2 and in
   `technical-specification.md` §D3/§F, matching the banner copy. This is
   documentation-only and is the recommended path.
2. **Fix `query_normalized`:** either store `redact_search_query(normalized)` as
   the dedup key (accepting that two differently-formatted PII-bearing queries
   collapse to one entry), or store a keyed digest of the normalised query as the
   key and keep the redacted text as the value. Add a regression test asserting
   no phone/e-mail/name survives in `query_normalized`.
3. Decide and document whether `SearchHistory` is purged on DECLINE (it is not
   today); if it is a legitimate-interest artefact, say so in `privacy.html` and
   bound its retention the way PII-116 proposes for `ConsentRecord`.

**Effort** M · **Priority** P1

| Field | Value |
|---|---|
| **CWE** | CWE-359 / CWE-459 |
| **Likelihood** | HIGH |
| **Related** | PII-104, PII-105, PII-110, PII-116 |

**Runtime evidence (auditor's V-probe, re-verified for the write path):**

```text
# auditor probe §R-08
  declined buyer analytics rows: ['search_performed']
# validator source read — the un-redacted key
  normalized = query.strip().lower()      # search_history.py:58  <- RAW
  redacted   = redact_search_query(query)  # search_history.py:65  <- REDACTED
  SearchHistory.objects.create(user_id=…, query=redacted, query_normalized=normalized)
```

---

#### PII-109 — [MEDIUM] — CONFIRMED — "Anonymized ads after withdrawal" is not implemented

> **Validation Note:**
> - **Action:** confirmed unchanged
> - **Detail:** Reproduces on every point. `docs/01-spec/technical-specification.md:89`
>   states "Anonymized ads (post-withdrawal, pre-hard-delete) persist for 30 days
>   only". `soft_delete_user_ads()` (`apps/users/services/deletion.py:211-228`)
>   routes every ad through `ad.transition_to(AdStatus.DELETED)` and nothing
>   else — `title`, `title_bs`, `title_en`, `description*` and `rejected_reason`
>   are untouched. `AdAdmin` has no default status filter and declares
>   `search_fields = ["title", "description"]` (`apps/ads/admin.py:80-100`), so the
>   retained body is listed and full-text searchable by any `is_staff` account.
>   The auditor's characterisation of the spec word ("anonymized" meaning "survives
>   without its owner") is a fair reading and the ambiguity is real.
> - **Dependency added (VAL-009):** the recommended scrub must keep the per-language
>   FTS vectors consistent, which is Phase 08's mechanism
>   (`ads_search_vector_fn` / `ads_search_vector_update` trigger, installed by
>   `setup_search_triggers`). Scrubbing `title`/`description` without re-deriving
>   the vectors would leave a searchable index pointing at removed text — i.e. the
>   fix would *create* a new PII leak in the search index.

| Field | Value |
|---|---|
| **ID** | PII-109 |
| **Type** | SPEC-DEVIATION (erasure completeness) |
| **Severity** | MEDIUM *(held)* |
| **Category** | Privacy / erasure completeness |
| **File(s)** | `src/backend/apps/users/services/deletion.py:164-231`; `src/backend/apps/ads/admin.py:80-100`; `src/backend/apps/ads/models.py`; spec `docs/01-spec/technical-specification.md:89` |
| **Status** | Open |

**Problem.** `soft_delete_user_ads()` performs no anonymisation: it transitions
status to `DELETED` and leaves every user-authored text field byte-for-byte
intact for the full 30-day window. `AdAdmin` lists `title` and full-text-searches
`["title", "description"]` with no default status filter, so the retained body is
reachable by any staff account.

**Impact.** On a classifieds board the ad description is the most likely place for
a seller to have typed their own name, a phone number or a "call me at…" line.
Those survive the withdrawal in cleartext, appear in a staff changelist, and are
discoverable by full-text search across the whole ad corpus for 30 days after the
seller asked to be forgotten. The spec's word "anonymized" is not an accurate
description of current behaviour, and anyone relying on it is misled.

**Root cause.** "Anonymize" in the spec means "the ad survives without its owner",
which the `status` transition plus the FK cascade already satisfy. The free-text
body was never in the implementation's scope.

**Recommendation (validated).** Either implement the scrub or correct the spec.
Recommended: implement a bounded scrub inside the withdrawal transaction — for
the same ad set, overwrite user-authored text with a neutral placeholder
(`title* = "[withdrawn]"`, `description* = ""`, `rejected_reason = ""`) — and
**re-derive the FTS vectors in the same operation** (VAL-009). Add a regression
test asserting no ad of a withdrawn user retains a seller marker string in any
`title*`/`description*` field. If the scrub is judged too destructive, change the
spec wording to "ads are soft-deleted (status=DELETED) and retain their original
text for 30 days" and record the deviation in
`docs/00-overview/doc-maintenance-rules.md`.

**Effort** S · **Priority** P1

| Field | Value |
|---|---|
| **CWE** | CWE-459 (Incomplete Cleanup) |
| **Likelihood** | MEDIUM |
| **Related** | PII-101, PII-104, PII-110, VAL-009 |

---

#### PII-110 — [MEDIUM] — CONFIRMED / SPLIT — Erasure scope gap: `chat_id`, `ConsentRecord` fingerprint fields and `preferred_city`

> **Validation Note:**
> - **Action:** confirmed; **split into two shippable units**
> - **Detail:** All four fields are verified absent from the erasure path. But the
>   bundle mixes two different urgencies and two different owners:
>   *Unit 1 (this finding, ship with PII-104):* `User.chat_id` is deliberately
>   retained — `users/models.py:49-53` documents it "never nullified", and
>   `AccountStateMiddleware._get_user` resolves users by `chat_id` precisely so a
>   withdrawn identity stays *blocked*. Nulling it would re-open a hole. The
>   defect is not retention; it is that the retention is **undocumented against
>   the published promise** and that it is the mechanical reason PII-104 keeps
>   working. Fix = document the trade-off in `privacy.html` §6 and gate every
>   delivery path on consent state.
>   *Unit 2 (split out, ships independently):* `ConsentRecord.session_key` and
>   `.user_agent` have no retention boundary and are the same class of issue as
>   PII-116. This half is moved into PII-116 so that a single
>   `ConsentRecord` retention sweep closes both, rather than two findings racing
>   to define the same TTL.
>   `User.preferred_city` stays here — it is a first-party behavioural preference
>   that DECLINE already promises to drop (`_set_consent_cookies` deletes the
>   `preferred_city` **cookie** when preferences consent is false,
>   `views/consent.py:99-102`) while the DB column is untouched. That asymmetry
>   between the cookie and the column is the sharpest form of the finding.

| Field | Value |
|---|---|
| **ID** | PII-110 |
| **Type** | SPEC-DEVIATION (retention policy) |
| **Severity** | MEDIUM *(held; scope split)* |
| **Category** | Privacy / retention policy |
| **File(s)** | `src/backend/apps/users/models.py:48-53` (`chat_id`), `:80-87` (`preferred_city`), `:229-274` (`ConsentRecord` FK + fingerprint fields); `src/backend/apps/users/services/deletion.py:140-152` (`update_fields` list); `src/backend/apps/users/views/consent.py:99-102`; `src/backend/templates/privacy.html` §6 |
| **Status** | Open |

**Problem.** `privacy.html` §6 promises "All personal data is permanently erased
within 30 days of withdrawal". `withdraw_consent()`'s `update_fields` list
(`deletion.py:140-152`) contains `consent_revoked_at, is_deleted, deleted_at,
consent_given_at, telegram_id, username, first_name, last_name, email` — and
nothing else. Four identity-bearing or identity-adjacent fields survive:
1. `User.chat_id` — the raw Telegram numeric ID, documented "never nullified".
2. `User.preferred_city` — a persisted behavioural preference, `SET_NULL` only on
   city removal, never cleared on DECLINE (which forces
   `consent_preferences=False`) nor on withdrawal, even though the matching
   **cookie** is deleted on decline.
3. `ConsentRecord.session_key` — a live Django session identifier, `SET_NULL` FK
   with no retention job.
4. `ConsentRecord.user_agent` — a 500-char browser fingerprint, same.

**Impact.** The published commitment is not met as written, and the residue is
exactly the re-identifying material a data-subject-access request would surface.
`chat_id` surviving is also the mechanical reason PII-104 keeps working: the one
column that should have been erased is the one column the delivery path needs.

**Root cause.** The 30-day contract is a hand-maintained column list on one model,
and the "never nullified" decision for `chat_id` was taken for the bot's benefit
without being reconciled against the erasure promise or against the
outbound-delivery paths that also read it. There is no per-table retention policy
anywhere.

**Recommendation (validated).**
1. **Keep `chat_id`** (the bot's soft-delete gate genuinely needs it) and amend
   `privacy.html` §6 to enumerate what is erased and what is retained-and-why,
   citing the bot-block requirement. Gate every delivery path on it — that is
   PII-104, not this finding.
2. Clear `User.preferred_city` on DECLINE and on withdrawal, alongside the cookie
   deletion that already happens.
3. Delete the user's `SearchHistory` rows on withdrawal (`CASCADE` only today) —
   this discharges part of PII-108's retention question.
4. `ConsentRecord.session_key` / `.user_agent` → **moved to PII-116**, to be
   handled by one retention sweep.
5. Feed all of the above into the shared PII inventory (**Required Fix 1**).

**Effort** M · **Priority** P1

| Field | Value |
|---|---|
| **CWE** | CWE-459 |
| **Likelihood** | HIGH |
| **Related** | PII-101, PII-104, PII-108, PII-116 (absorbs part), PII-111 |

**Runtime evidence (V-02, scratch DB):**

```text
after  withdraw user.telegram_id=None chat_id=630000001 preferred_city=None is_deleted=True
```

`chat_id` retains the raw Telegram ID after withdrawal, exactly as documented.

---

#### PII-111 — [MEDIUM] → [LOW] — ADJUSTED — `SellerVerification.phone_number`: a vestigial, undisclosed column (not collected data)

> **Validation Note:**
> - **Action:** severity adjusted (MEDIUM → **LOW**); **premise refuted**;
>   recommendation inverted
> - **Detail:** The finding's core claim — "The product **collects and retains**
>   a high-value identifier" — is **false**. A grep for `phone_number` across the
>   whole of `src/` returns exactly four hits: the model field declaration
>   (`apps/trust/models.py:46`), its migration
>   (`apps/trust/migrations/0001_initial.py:81`), and two unrelated test
>   assertions about *JSON log redaction* (`src/backend/tests/test_json_logging.py:62`,
>   `apps/search/tests/test_redact_search_query.py:34`). There is **no view, no
>   admin form, no service, no bot handler and no management command that writes
>   it**; `apps/trust/` has no `admin.py` at all, so the column is not even
> reachable from the staff UI. V-06 confirms 0 rows.
>   The auditor's runtime evidence — `SellerVerification.phone_number still
>   present = +38269000001` — was **the probe's own insert**, not application
>   behaviour. The auditor's own claim that "the trust system is driven by
>   activity metrics, not by a phone number" is correct and is precisely why the
>   column is empty.
> - **What survives** is a real but much smaller defect: an **undeclared,
>   permanently-NULL, non-reachable PII column in the schema** that contradicts
>   `technical-specification.md:82-83` ("Collect minimum: `telegram_id`, optional
>   `username` … nothing beyond Telegram login is stored") and is absent from
>   `privacy.html` §2. That is schema hygiene and documentation, not a live
>   privacy incident — hence LOW.
> - **Recommendation inverted.** Because nothing writes the column, the auditor's
>   option (a) "add it to `withdraw_consent()`'s null set" is pointless. The
>   correct primary action is the one the auditor listed second: **drop the
>   column** (a `RemoveField` migration). That is strictly simpler, removes the
>   undocumented-category problem permanently, and matches the trust badge logic,
>   which reads `verified_by_admin` + `SellerTrustScore`, not `phone_number`.

| Field | Value |
|---|---|
| **ID** | PII-111 |
| **Type** | BEST-PRACTICE (schema hygiene) — was: privacy / data minimisation |
| **Severity** | LOW *(downgraded from MEDIUM)* |
| **Category** | Privacy / data minimisation (declarative) |
| **File(s)** | `src/backend/apps/trust/models.py:38-51`; `src/backend/apps/trust/migrations/0001_initial.py:81`; `src/backend/apps/users/services/deletion.py:140-152`; spec `docs/01-spec/technical-specification.md:82-83`; `src/backend/templates/privacy.html` §2 |
| **Status** | Open (now: schema cleanup) |

**Problem.** `SellerVerification` declares
`phone_number = models.CharField(max_length=20, blank=True, null=True)`, a
category of personal data the project has explicitly declared it does not hold.
No code path in `src/` writes it; the `trust` app registers no `ModelAdmin`, so
it is not staff-reachable. The column is an artefact of the trust/verification
feature that was never removed, and it is disclosed in neither the spec's data
list nor the published privacy policy.

**Impact (validated).** Low. Because the column is always `NULL` there is no data
to breach, no data-subject-access export to answer incorrectly, and no withdrawal
path to fix. The cost is a schema/documentation inconsistency and an
undocumented-data-category risk if anyone ever wires the field up without
re-reading the spec.

**Root cause.** The field was added with the trust/verification feature and
treated as operational metadata rather than as personal data, and no cross-check
exists between "columns on user-adjacent models" and the documented data
categories.

**Recommendation (validated).**
1. **Preferred:** remove `phone_number` from `SellerVerification` via a
   `RemoveField` migration. Nothing reads it; the trust badge reads
   `verified_by_admin` + `SellerTrustScore`.
2. If the field is genuinely required for a future manual-verification workflow,
   it must be (a) added to the withdrawal null set, (b) added to `privacy.html` §2
   and to `technical-specification.md` §F, and (c) masked in any admin
   `list_display`. Pick one branch deliberately; do not leave it as a dormant,
   undocumented column.

**Effort** S · **Priority** P2

| Field | Value |
|---|---|
| **CWE** | CWE-359 (potential, not realised) |
| **Likelihood** | LOW |
| **Related** | PII-110, PII-101 |

**Runtime + static evidence (V-06):**

```text
column in schema : ['phone_number']
rows in DB       : 0
grep phone_number in src/  ->  apps/trust/models.py:46
                             apps/trust/migrations/0001_initial.py:81
                             tests/test_json_logging.py:62            (unrelated)
                             apps/search/tests/test_redact_search_query.py:34 (unrelated)
```

---

#### PII-112 — [MEDIUM] — CONFIRMED — `mask_telegram_id()` is a brute-forceable 32-bit truncated unsalted SHA-256

> **Validation Note:**
> - **Action:** confirmed unchanged; rollout dependency added
> - **Detail:** Verified independently (V-07) and **executed**, not merely
>   reasoned about. The mask is exactly `sha256(str(tid)).hexdigest()[:8]` — no
>   salt, no secret, no input-domain binding. A 2^20-wide candidate sweep
>   recovered the original identifier in **1.39 s**; a full sweep of the realistic
>   Telegram ID domain is ~2^34 hashes, i.e. minutes on commodity hardware. The
>   spec's assertion at `technical-specification.md:90` — "SHA-256 hash,
>   **non-reversible**" — is therefore factually false as written, and this is a
>   documentation falsehood as much as a code weakness.
> - **Rollout dependency added (VAL-008):** the spec line must be corrected in the
>   **same** change. Leaving a document asserting a security property the code does
>   not have is worse than either state alone.
> - **A note on why a keyed digest is the right fix, not a longer digest.** Any
>   *deterministic* function of a ~2^34-element input domain is invertible by
>   exhaustive enumeration regardless of output width — the attacker only needs to
>   try every candidate ID and compare. An HMAC keyed with a server secret defeats
>   precisely that: without the key the attacker can enumerate guesses but cannot
>   verify any of them. Lengthening the hex prefix alone would **not** fix this.

| Field | Value |
|---|---|
| **ID** | PII-112 |
| **Type** | SPEC-DEVIATION (pseudonymisation strength) |
| **Severity** | MEDIUM *(held)* |
| **Category** | Privacy / pseudonymisation strength |
| **File(s)** | `src/backend/apps/core/utils/sanitize.py:134-150`; spec `docs/01-spec/technical-specification.md:90`; guard `src/backend/apps/core/tests/test_sanitize.py:14-37` |
| **Status** | Open |

**Problem.** `mask_telegram_id` returns `f"tg_{hashlib.sha256(tid.encode()).hexdigest()[:8]}"`
— the first 8 hex characters of an unsalted SHA-256, a 32-bit truncated digest.
Telegram user IDs are small integers densely allocated over a ~2^34 domain, so the
candidate space is trivially enumerable. The whole log-hygiene guarantee of
`technical-specification.md:90` rests on this function, and the spec explicitly
claims non-reversibility.

**Impact.** The "masked" values in logs are pseudonyms, not anonymised data — they
remain personal data and are re-identifiable by anyone with log read access (an
operator, an aggregator, a support bundle, an exfiltrated archive). The stability
that makes the mask useful for correlation is exactly what makes it reversible.

**Root cause.** A truncated hash was chosen for short, greppable log output; the
truncation length was not reasoned about against the size of the input domain, and
no keyed construction was used.

**Recommendation (validated).**
1. Use a keyed digest so the mapping is not computable from the logs alone:
   `hmac.new(settings.LOG_MASK_KEY, str(tid).encode(), sha256).hexdigest()[:12]`,
   with `LOG_MASK_KEY` sourced from the same secret source as `SECRET_KEY`,
   registered in `ALLOWED_ENV_VARS` (`config/settings/base.py:21-31`) and added to
   all four `.env.*.example` templates. 12 hex chars (48 bits) stays readable in a
   log line.
2. Keep the `tg_` prefix so existing log greps and the
   `test_admin_pii_containment.py` assertion on `mask_telegram_id` continue to
   work.
3. **Correct `technical-specification.md:90` in the same commit** — replace
   "non-reversible" with the actual construction, and document the key-rotation
   trade-off (rotation invalidates correlation across old log lines).
4. **Required test updates:** `src/backend/apps/core/tests/test_sanitize.py:14-20`
   pins the mask `length == 13` (`tg_` + 8 hex) and will fail; update it to assert
   the *property* (raw ID absent, stable, prefix preserved) rather than the length.
   `src/backend/apps/users/tests/test_admin_pii_containment.py:57-64` only asserts
   that the helper delegates to `mask_telegram_id`, so it survives.
5. **Ordering:** land this with PII-102, not after — masking into a reversible
   function buys nothing on its own.

**Effort** S (code) + S (secret plumbing) · **Priority** P1

| Field | Value |
|---|---|
| **CWE** | CWE-328 (Use of Weak Hash) |
| **Likelihood** | MEDIUM |
| **Related** | PII-102, PII-106, VAL-008 |

**Runtime evidence (V-07):**

```text
100000001      -> tg_e0d3b72f
630000001      -> tg_bc4788ab
5000000000     -> tg_ab99f10b
7700000000     -> tg_6e068472
mask is exactly sha256(id)[:8], no key: True
brute force over 2^20 candidates found the original id back: [630000001]
elapsed: 0:00:01.390335
attacker with one (id, mask) pair but no LOG_MASK_KEY can only enumerate
guesses he cannot verify: True
```

---

#### PII-113 — [MEDIUM] — CONFIRMED → DOC-UPDATE — Unresolved doc conflict on DECLINE semantics

> **Validation Note:**
> - **Action:** confirmed; reclassified as **DOC-UPDATE**; merged with `04-VAL-005`
> - **Detail:** The conflict is real and both statements were re-read verbatim.
>   `docs/01-spec/spec-index.md:74` — "DECLINE blocks seller login **only** (no
>   erasure, contact still works)". `docs/01-spec/technical-specification.md:85`,
>   `:96`, `:101` — DECLINE "**also hides the user's PUBLISHED ads** from public
>   search/listings, direct URL access (`ad_detail`), and the `media_gate`
>   non-staff filter", with the search cache version bumped. A third answer sits in
>   this phase's own rubric: `.kilo/commands/audit/phases/06-audit-pii-consent.md:39`
>   asserts "existing ads remain public/searchable" and `:49` repeats it.
>   **Adjudication (which reading is correct):** the code matches
>   `technical-specification.md` (V-04: the declined seller's ad is invisible via
>   `ListingsQuery`; `decline_consent()` bumps the cache version via
>   `transaction.on_commit`). `technical-specification.md` is the detailed,
>   implementation-level source of truth; `spec-index.md` is a one-line condensed
>   index that was not updated when the decision was made. Per the validation
>   handbook's SPEC-DEVIATION rule — *code better than docs → reclassify as
>   DOC-UPDATE* — **the code is right and the docs are wrong.**
> - **This is the same conflict phase 04 already filed as `04-VAL-005`**, which
>   used it to feed AUT-002. It must be fixed once, in one place. PII-113 carries
>   the fuller statement; `04-VAL-005` becomes a cross-reference.
> - **Third conflict source is the audit rubric itself** — the phase handbook
>   asserts a behaviour the authoritative spec contradicts. Recorded as
>   **VAL-004** (audit-input defect).
> - **Not a code defect.** The auditor's own ruling is correct and this validation
>   endorses it. Nothing in the DECLINE hiding behaviour should be "fixed"; only
>   the documents should change.

| Field | Value |
|---|---|
| **ID** | PII-113 |
| **Type** | **DOC-UPDATE** |
| **Severity** | MEDIUM *(held)* |
| **Category** | Documentation |
| **File(s)** | `docs/01-spec/spec-index.md:74` (stale); `docs/01-spec/technical-specification.md:85, 96, 101` (authoritative, unchanged); `.kilo/commands/audit/phases/06-audit-pii-consent.md:39, 49` (audit rubric, wrong) |
| **Merged with** | `04-VAL-005` (phase 04) |
| **Status** | Open |

**Problem.** Three current sources give two — arguably three — different answers
to the single most consequential consent decision in the product: what does DECLINE
do to already-published ads? The two spec documents disagree with each other, and
the phase-06 audit rubric disagrees with both.

**Impact.** Any reviewer, support agent or future implementer who reads
`spec-index.md` will believe existing ads stay up; anyone who reads
`technical-specification.md` will believe they come down. The disagreement is what
caused this phase to file PII-105 as a HIGH *code* defect when the code is in fact
spec-conformant — the documentation ambiguity directly produced a mis-rated
finding, which is why it cannot be deferred as cosmetic.

**Root cause.** `spec-index.md` is a condensed index that was not regenerated when
the DECLINE-hides-ads decision was made and documented in detail in
`technical-specification.md`. The phase rubric was written from the pre-decision
mental model.

**Recommendation (validated).**
1. Rewrite `docs/01-spec/spec-index.md:74` to match
   `technical-specification.md`: "DECLINE blocks seller login/actions **and hides
   the user's PUBLISHED ads from public listings, search and direct URL**".
2. Correct `.kilo/commands/audit/phases/06-audit-pii-consent.md:39, 49` so the
   runtime-verification step asserts the actual intended behaviour.
3. Leave `technical-specification.md:85/96/101` unchanged — it is the most precise
   of the three.
4. In the same edit, state whether DECLINE is reversible, so `spec-index.md`
   resolves PII-105's owner decision (option (a) or (b)).

**Effort** S · **Priority** P1 (docs only, no code risk)

| Field | Value |
|---|---|
| **CWE** | CWE-1059 (Incomplete Documentation) |
| **Likelihood** | HIGH |
| **Related** | PII-105, PII-104, 04-VAL-005, 04-AUT-002, VAL-001, VAL-004 |

---

### LOW

#### PII-114 — [LOW] — CONFIRMED — `ModeratorActionLog.reason` is free text, never redacted, survives erasure as an orphan

> **Validation Note:**
> - **Action:** confirmed unchanged
> - **Detail:** Verified: `apps/moderation/models.py:89-119` declares `reason` as an
>   unbounded `TextField` documented "INTERNAL ONLY - never shown to seller", with
>   `ad` and `user` both `on_delete=SET_NULL`. No write path passes it through
>   `redact_search_query()` or any other redaction. `Ad.rejected_reason` is the
>   same shape and *is* rendered in `AdAdmin.list_display` via the `rejected_reason`
>   helper (`apps/ads/admin.py:89`). The auditor's characterisation of the impact
>   — staff-authored text that can nonetheless contain the *subject's* data, in a
>   row that erasure can no longer associate and therefore can no longer clean up —
>   is accurate.

| Field | Value |
|---|---|
| **ID** | PII-114 |
| **Type** | BEST-PRACTICE |
| **Severity** | LOW *(held)* |
| **Category** | Privacy / free-text storage |
| **File(s)** | `src/backend/apps/moderation/models.py:89-119`; `src/backend/apps/moderation/admin_actions.py`; `src/backend/apps/moderation/services/moderation_log.py`; `src/backend/apps/ads/models.py` (`rejected_reason`); `src/backend/apps/ads/admin.py:89` |
| **Status** | Open |

**Problem.** `reason` is free-form moderator text with no redaction, retained
forever on a row that deliberately survives user erasure with `user_id = NULL`.
`bulk_reject` writes a fixed literal, but moderators type arbitrary text.

**Impact.** Low in practice because the fields are staff-authored — but a
moderator quoting a seller's message ("user said: call me on +382 69 000 123")
persists that PII indefinitely, in a row that erasure can no longer associate
with and therefore can no longer clean up. Combined with PII-101 this is a
second orphan-PII channel.

**Root cause.** Free-text operator fields are treated as non-personal because the
*operator* writes them, not because the *subject's* data cannot end up in them.

**Recommendation (validated).** Run `reason` and `rejected_reason` through
`redact_search_query()` at write time in the moderation log writer and
`admin_actions.bulk_reject`, and add a help-text note in the moderation UI that
seller details must not be pasted in. Optionally cap the field length. Note that
`redact_search_query` is designed for *search queries* and preserves length; for a
moderator-reason field that is acceptable, but confirm the 500-char-class columns
are not length-constrained before applying it.

**Effort** S · **Priority** P2

| Field | Value |
|---|---|
| **CWE** | CWE-532 |
| **Likelihood** | LOW |
| **Related** | PII-101, PII-110 |

---

#### PII-115: ~~`create_admin_user` writes the raw public `username` to stdout while masking `telegram_id` in the same command~~ [REJECTED]

> **Rejection reason:** The finding's stated fact pattern is correct — the command
> masks `telegram_id` on four output paths and writes `username` raw on four
> others — but the privacy claim attached to it is **factually wrong**, and the
> spec rule it is judged against does not cover it. Three points:
> 1. **It is not a seller's Telegram handle.** `create_admin_user` creates a
>    *local bootstrap administrator* from operator-supplied `--username`, with a
>    placeholder `--telegram-id` defaulting to `-1`
>    (`apps/core/management/commands/create_admin_user.py:42-46`, `:108-115`).
>    There is no code path in this command by which a seller's `User.username`
>    (the public `@handle`) is ever printed. The auditor's "the seller's public
>    Telegram handle, i.e. the second PII field the spec names" is a misreading of
>    what the command writes.
> 2. **The spec rule does not apply.** `technical-specification.md:90` requires
>    masking for *"`telegram_id` values in logger calls and `stdout.write`
>    output"*. It says nothing about `username`, and the command masks
>    `telegram_id` at **every** occurrence. By the written rule the command is
>    compliant.
> 3. **There is no privacy exposure.** An operator-chosen local admin username
>    echoed to that operator's own terminal during bootstrap is not personal data
>    and not a leak. (The command also echoes the operator-supplied `--email`
>    raw at `:100`; the same reasoning applies.)
>
> The underlying observation — *masking is applied per-value per-call-site rather
> than through a shared formatter* — is legitimate, but it is a consistency
> observation about a non-PII field in a bootstrap command, with no consequence.
> It is already fully captured as an **advisory note inside PII-102** (whose
> recommendation this validation explicitly declines to escalate into a global
> logging filter). Recording it as a LOW finding would overstate it.

| Field | Value |
|---|---|
| **ID** | PII-115 |
| **Original severity** | LOW |
| **Verdict** | **REJECTED** |
| **Files reviewed** | `src/backend/apps/core/management/commands/create_admin_user.py:79-131` |
| **Status** | Closed — no remediation |

---

#### PII-116 — [LOW] — CONFIRMED — `ConsentRecord` has no retention policy and exposes a live `session_key` in the staff changelist

> **Validation Note:**
> - **Action:** confirmed; **absorbs the `ConsentRecord` half of PII-110**;
>   ordering constraint added
> - **Detail:** Verified. `apps/core/utils/scheduler.py:55-65` lists nine
>   `HOURLY_COMMANDS` and none of them purges `consent_records`.
>   `ConsentRecordAdmin.list_display` includes `session_key` and
>   `search_fields == ["session_key"]` (`apps/users/admin.py:74-83`), while
>   `has_delete_permission` is correctly restricted to superusers. The model is
>   append-only by design ("never updated", a deliberate Art. 7(1) property) but
>   nothing bounds it. The auditor's `ConsentRecord.ip_address` characterisation
>   (IPv4 last octet zeroed, IPv6 /64 prefix) was independently verified against
>   `apps/users/services/consent_record.py:20-34` and is accurate.
> - **Ordering constraint:** a `ConsentRecord` purge is *destructive* and must be
>   ordered so it can never delete a record still needed to demonstrate consent.
>   The 12-month figure the auditor proposes is a starting point, not a
>   recommendation this validation can make — it is a business/legal decision.
> - **Note on the "session hijack" impact claim.** A `session_key` alone is not a
>   session cookie; exploiting it still requires the cookie value. The claim is
>   therefore *weaker* than stated — this is an exposure-reduction argument (a
>   live session identifier should not be enumerable in a staff changelist), not a
>   standalone hijack. Severity LOW is correct.

| Field | Value |
|---|---|
| **ID** | PII-116 |
| **Type** | BEST-PRACTICE (retention policy) |
| **Severity** | LOW *(held)* |
| **Category** | Privacy / retention policy |
| **File(s)** | `src/backend/apps/users/models.py:217-277`; `src/backend/apps/users/admin.py:68-102`; `src/backend/apps/core/utils/scheduler.py:55-65`; `src/backend/apps/users/context_processors.py:28` (`CONSENT_REPROMPT_DAYS`) |
| **Absorbs** | the `ConsentRecord.session_key` / `.user_agent` portion of PII-110 |
| **Status** | Open |

**Problem.** `ConsentRecord` grows without bound. Every row carries a
`session_key` (a live Django session identifier), the full 500-char
`user_agent`, and a partially-masked `ip_address`. No purge command exists in
`HOURLY_COMMANDS`. `ConsentRecordAdmin` puts `session_key` in `list_display` and
`search_fields`, so any staff user can enumerate session identifiers.

**Impact.** (a) Unbounded retention of browser-fingerprint-grade data with no
stated period — a data-minimisation question the privacy policy does not address.
(b) A live session identifier is enumerable in a staff-visible, searchable
changelist. (A `session_key` alone is not a cookie, so this is an
exposure-reduction argument rather than a standalone hijack.)

**Root cause.** The model was designed purely as an append-only proof-of-consent
ledger with no complementary retention design, and `session_key` was added to
`list_display` for debugging convenience.

**Recommendation (validated).**
1. Agree an explicit TTL with the business (the existing
   `CONSENT_REPROMPT_DAYS = 365` re-prompt window is the natural starting point),
   then add a `purge_consent_records` command to `HOURLY_COMMANDS` with an
   explicit `--dry-run` and a TTL test.
2. In the sweep: delete rows past the TTL, and for rows whose `user` is still set,
   null `session_key` once the session has expired. Do **not** delete rows still
   inside the TTL — they are the Art. 7(1) evidence.
3. Remove `session_key` from `ConsentRecordAdmin.list_display` (keep it in
   `search_fields` for support lookups) and document the retention period in
   `privacy.html` §6.
4. This finding now also closes the `ConsentRecord` retention half of PII-110 —
   one sweep, one TTL, one decision.

**Effort** S · **Priority** P2

| Field | Value |
|---|---|
| **CWE** | CWE-459 |
| **Likelihood** | LOW |
| **Related** | PII-110 (partially absorbed), PII-107, PII-108 |

---

## Cross-Finding Analysis (revised)

### Merge candidates and how they resolve

| Cluster | Shared root cause | Resolution |
|---------|-------------------|------------|
| **PII-103 ≡ 04-AUT-005 / 04-VAL-004** | `UserAdmin` declares no `fields`/`fieldsets`/`form`, so Django auto-builds a `ModelForm` over every editable model field. PII-103 sees the identity/consent-flag half; 04-AUT-005 sees the credential half. Byte-identical root cause. | **MERGED into `04-AUT-005`**, which is already validated, already HIGH, and already Required Fix #1. PII-103's scope becomes a mandatory part of the same `fieldsets` declaration. Do not patch the class twice. |
| **PII-113 ≡ 04-VAL-005** | `spec-index.md:74` ("login only") vs `technical-specification.md:101` ("login/actions"), and both feed a code-behaviour verdict. | **One owner, one edit.** PII-113 carries the fuller statement; `04-VAL-005` becomes a cross-reference. See VAL-001. |
| **PII-101 + PII-109 + PII-110 + PII-111 + PII-114** | The erasure contract is a hand-maintained `update_fields` column list on one model. Any table that denormalises identity (`support_tickets`, `ads.*text`, `seller_verifications`, `moderation_action_logs.reason`, `chat_id`, `preferred_city`) or identity-adjacent data falls out of scope the moment it is added, and no check enforces membership. | **NOT merged** — the per-claim fixes, owners and urgencies genuinely differ (column scrub vs content scrub vs retention policy vs column removal vs write-time redaction), and PII-102's and PII-101's severities differ by an order of magnitude. But they share **one architectural prerequisite** (Required Fix 1: a declarative PII inventory) which should land first and turn each individual fix into a one-line change instead of a fresh audit of every table. |
| **PII-102 + PII-112** | Log hygiene is per-value/per-call-site, and the masker itself is reversible. | **NOT merged** — retained as a two-item unit with an explicit ordering: masking into a 32-bit unsalted digest buys nothing, so land PII-112's construction and PII-102's two call sites together. |
| **PII-110 (ConsentRecord half) + PII-116** | Two findings racing to define the same `ConsentRecord` TTL. | **PII-116 absorbs** the `session_key`/`user_agent` retention half of PII-110. One sweep, one TTL, one business decision. |
| **PII-101 + PII-102 (severity, not root cause)** | Both are "raw Telegram identifier survives where it should not". | **NOT merged** — the auditor's CRITICAL-both framing double-counts. PII-102's most alarming impact sentence ("a user who withdrew consent still has their identifier land in logs after the erasure") is *derivative of PII-104*: once the audience is gated on consent state, a withdrawn user is never messaged and that sentence is unreachable. Score them independently. |

### Conflicting evidence

- **VAL-001 — the DECLINE doc conflict is now filed three times** (this phase's
  PII-113, phase 04's `04-VAL-005`, and both spec documents against each other).
  Resolution: one owner (PII-113), one edit, two cross-references. Not CRITICAL —
  no finding's *verdict* is blocked by it, but it is the direct cause of a
  mis-rated HIGH (PII-105) and it must be closed before either this phase or
  phase 04 changes `can_login()`.
- **VAL-004 — the phase-06 audit rubric contradicts the authoritative spec.**
  `.kilo/commands/audit/phases/06-audit-pii-consent.md:39` asserts DECLINE keeps
  "existing ads remain public/searchable" and `:49` repeats it. This is an
  audit-*input* defect, not a product defect: the rubric was written from the
  pre-decision model. It should be corrected so a future run of this phase does not
  re-derive PII-113 and a mis-rated PII-105.

### Dependency chains (rollout ordering)

- **PII-101 → Required Fix 1 (PII inventory) → PII-109/110/111/114.** Establish the
  inventory declaration first; each individual column decision becomes a lookup.
- **PII-112 → PII-102.** Do not mask into a reversible digest. Ship the keyed
  construction first (or in the same commit); then the two call sites.
- **PII-102 + PII-104 → the `IMMEDIATE_ALERTS_ENABLED` rollout gate.** The immediate
  path is off by default; it must not be enabled before both are closed, because
  that path additionally ships a working deep link to a hidden ad.
- **PII-104 (merged → 04-AUT-005) → PII-107.** Making `is_declined`/`is_deleted`
  non-editable in the admin is what guarantees every consent-state transition
  goes through the service that writes the audit row.
- **PII-105 ← VAL-001.** The DECLINE-reversibility owner decision cannot be made
  until the doc conflict is adjudicated, and it must be coordinated with
  `04-AUT-002`, which also touches the web-side account-state gate.
- **PII-109 → VAL-009.** The ad-text scrub must re-derive FTS vectors (phase 08
  mechanism) or it creates a new leak in the search index.
- **PII-110 (kept half) → PII-104.** Do **not** "fix" PII-104 by nulling `chat_id`:
  `AccountStateMiddleware._get_user` resolves users by `chat_id` precisely so a
  withdrawn identity stays blocked. Nulling it would re-open a different hole.
- **PII-116 → PII-107.** The `ConsentRecord` sweep must be ordered so it can never
  delete a record still needed for an Art. 7(1) demonstration.

---

## VAL- Findings (validation-level: audit-input, cross-phase, rollout)

### VAL-001 — Cross-phase duplicate: the DECLINE doc conflict is filed in two phases

**Type:** cross-phase conflict (documentation) · **Severity:** Medium

`04-VAL-005` and `PII-113` describe the same contradiction between
`docs/01-spec/spec-index.md:74` and
`docs/01-spec/technical-specification.md:101`, and both use it to justify a code
verdict (04-AUT-002 and PII-105 respectively). Two owners, one edit. Resolution:
**PII-113 is the finding of record** (its statement is the more precise and it
names the third, wrong source — the phase rubric). `04-VAL-005` should be reduced
to a cross-reference. Whoever applies the fix must edit `spec-index.md:74` once and
annotate both reports.

### VAL-002 — Ownership split on the `UserAdmin` field contract

**Type:** cross-phase ownership conflict · **Severity:** Medium

`15-audit-authorization.md:126` assigns Phase 15 "admin protection". PII-103's
*root cause* (no `fieldsets`) and *field set* are not authorization; its
*permission* half — `has_change_permission` returning `request.user.is_staff`,
where `is_staff` **is** the moderator role — is. Risk if unresolved: Phase 15
re-files the whole admin form under RBAC and the two fixes diverge, or one of them
is dropped. Resolution: the field-set fix lands once, owned by `04-AUT-005`;
Phase 15 audits the permission predicate only and must cite `04-AUT-005` rather
than re-report the form surface.

### VAL-003 — The account-state predicate `apps/search` needs does not exist, and the existing one cannot be reused

**Type:** cross-phase dependency / ownership decision · **Severity:** High

PII-104's recommendation proposes a `SavedSearch.objects.filter(is_active=True,
user__is_deleted=False, user__is_declined=False, user__is_banned=False,
user__consent_revoked_at__isnull=True)` expression in the search app. That is
**not reuse** — it is a second, hand-written copy of the consent rule, in a
different app, at a different level of abstraction from
`apps/users/services/account_state.get_account_state()`, which is
**instance-level** and therefore unusable from a queryset filter. The rule will
drift the moment a fifth flag is added (this phase already found three flags
missing from one call site). Per
`15-audit-authorization.md:130`, Phase 15 owns "the framework that enforces the
predicate consistently across both processes" while Phase 06 owns the semantics —
so the ownership question is genuinely open, not a formality.

**This is a real cross-phase dependency, not a cosmetic one.** Resolution: an
explicit owner decision, then **one** queryset-level predicate owned by
`apps/users` and consumed by both alert paths. Constraints for whoever implements
it: (i) it must be a named `QuerySet` method or an explicit helper, **not** a
default manager filter — a global default filter would silently change every
`User.objects` query in the codebase; (ii) it must be testable without a request or
a `User` instance; (iii) `send_alerts._collect_alerts`, `_dry_run_check`,
`find_matching_saved_searches` and `find_matching_ads` must all consume the same
declaration, or the drift simply moves.

### VAL-004 — Audit-input defect: the phase-06 rubric contradicts the authoritative spec

**Type:** audit-input defect · **Severity:** Medium

`.kilo/commands/audit/phases/06-audit-pii-consent.md:39` and `:49` assert that
DECLINE keeps "existing ads remain public/searchable". This is false against both
`technical-specification.md:101` and the running code. It is the third leg of the
VAL-001 conflict and the direct cause of the auditor having to spend a finding
(PII-113) adjudicating its own rubric. Correct the handbook so a future run of
this phase does not re-derive the same conflict and re-file a mis-rated PII-105.

### VAL-005 — Severity-taxonomy defect: "raw identifier in logs" is CRITICAL regardless of sink

**Type:** audit-input defect · **Severity:** Medium

`.kilo/commands/audit/phases/06-audit-pii-consent.md:92` lists "PII leaked into
analytics events or logs (raw identifier/handle)" as blanket CRITICAL, with no
weighting for sink, branch or blast radius. That rating is right for an
`AnalyticsEvent` row or a third-party egress and wrong for a single integer written
to an operator-controlled log on a send-failure branch behind a default-off feature
flag. The rubric should distinguish sinks (event store / third party / operator log
/ staff UI) so that the one genuinely CRITICAL item in this phase (PII-101) keeps
its signal. This validation departed from the rubric on PII-102 explicitly rather
than deferring to it.

### VAL-006 — Remediation hazard: consent-copy changes trip the i18n completeness gate

**Type:** rollout-safety issue · **Severity:** Medium

PII-105's required changes — corrected `privacy.html` §6/§7 copy, a banner or
dashboard affordance, a new explanatory page for the anonymous-Accept no-op — all
introduce or change `{% trans %}` / `{% blocktrans %}` strings. `ru` and `bs`
`msgstr` must be non-empty or `test_i18n_completeness.py` fails. The i18n gate
failure is a **consequence of the fix, not a regression from it**, and must not be
triaged as one. Sequence: `.po` updates in the same commit as the template change
(`makemessages` → fill `ru`/`bs` → `compilemessages`). Phase 14 owns runtime i18n
correctness; this is a coordination note, not a duplication of its findings.

### VAL-007 — Rollout hazard: the proposed generalised admin-containment test would produce a false positive

**Type:** rollout-safety issue · **Severity:** Medium

PII-106's recommendation to generalise
`src/backend/apps/users/tests/test_admin_pii_containment.py` into a walk over
**every** registered `ModelAdmin` asserting "no `list_display` entry renders a raw
identity column" will fail on `SupportContactAdmin`
(`apps/core/admin.py:41`), whose `telegram_id` is a *configured support-channel*
identifier rather than a data subject's, and which legitimately has no
`readonly_fields` or permission override because channels are meant to be
staff-editable. The guard must be written against an explicit declared set of
**data-subject** identity columns, not a blanket token ban. Anyone implementing
PII-106 should read this first.

### VAL-008 — Documentation/comment coupling: `mask_telegram_id` is documented as non-reversible

**Type:** documentation inconsistency · **Severity:** Low

`docs/01-spec/technical-specification.md:90` and the function's own docstring
(`apps/core/utils/sanitize.py:137` — "Non-reversible SHA-256 hash") both assert a
security property the implementation does not provide. If PII-112 is fixed without
editing both, the codebase will carry a false claim about a privacy control. If
PII-112 is *not* fixed, the false claim is itself the finding. Either way the two
must move together.

### VAL-009 — Cross-phase dependency: an ad-text scrub must re-derive the FTS vectors

**Type:** cross-phase dependency · **Severity:** Medium

PII-109's recommended scrub overwrites `title*` / `description*`. Those columns
feed the per-language `search_vector_*` columns via
`ads_search_vector_fn` / the `ads_search_vector_update` trigger, installed by
`setup_search_triggers`. Scrubbing the base columns without re-deriving the
vectors would leave the search index holding text the row no longer has — turning
an erasure fix into a new PII leak in the index. The vector mechanism is Phase 08's
(per `08-audit-search-fts`), the erasure trigger is this phase's (per
`06-audit-pii-consent.md:6`). Do not let the consent fix silently change the search
index.

### VAL-010 — Shared-state hazard in the audit pipeline: concurrent test runs corrupt the gate signal

**Type:** rollout-safety issue (audit process) · **Severity:** Medium

`config/settings/test.py:28` hardcodes `DATABASES["default"]["NAME"] = "mko_bazuna"`,
so pytest-django always creates and reuses the **single** database
`test_mko_bazuna`. Multiple phase validators running the `test` compose service
concurrently therefore collide. Observed during this validation: a scoped run
(users + core + search) returned 6 ERRORs — `FATAL: database "test_mko_bazuna"
does not exist` and `relation "users" does not exist` — that were **not** product
failures but the teardown race with two other in-flight validator containers.
Re-running the same scope alone afterwards exited 0 with no failure markers.
**Any "red gate" evidence produced while other phase validators are running must be
re-run serially before it is reported as a defect.** This is a property of the
audit environment, not of the product; it should not be actioned as a remediation
item against the codebase, but it invalidates any red-gate claim captured in
parallel.

### VAL-011 — Finding-ID collision hazard: bare `PII-1xx` collides with in-source markers

**Type:** remediation-hazard · **Severity:** Low

Inherited from `04-VAL-002`. The token `PII-001` is already referenced in **shipped
source** — `apps/users/admin.py:130` (`"""Display the masked Telegram ID of the
token claimer (PII-001/VAL-001)."""`) and
`apps/users/tests/test_admin_pii_containment.py:5` — referring to a *prior* audit
cycle. This phase files `PII-101`…`PII-116`, so any tracker keyed on the bare ID
will eventually collide. Key on `06-PII-1xx`, exactly as phase 04 keys on
`04-AUT-00N`.

### VAL-012 — Method note: the phantom database is reachable and must be guarded against

**Type:** methodology / safety note · **Severity:** Low

`config/settings/test.py:28` hardcodes the connection name to `mko_bazuna`, a
**phantom** database (39 tables, `to_regclass('django_migrations') IS NULL`,
confirmed independently in phase 01 as ENT-008). Any probe that touches the ORM
before overriding the connection writes into it — which is what happened during the
phase-06 audit run. This validation's probe therefore pointed the connection at the
maintenance `postgres` database first, issued `CREATE DATABASE val06_probe` /
`DROP DATABASE` there, and only then redirected to the scratch database, so the
phantom was never opened. **The connection override must precede the first ORM
call in any future probe**, and `ENTRYPOINT`-level protection for this is worth
raising with the project (it is the same class of defect as the `DATABASE_URL`
hardcoding already noted in the `commands.md` rules).

---

## Rollout Safety (revised)

| ID | Risk | Backward-compatible? | Test gap (must cover) |
|----|------|----------------------|-----------------------|
| PII-101 | **High** — requires a nullable-column migration plus a data migration; historical ticket rows lose their lookup key, so support agents lose a way to correlate a ticket with a (now-erased) account. `chat_id`/`telegram_id` are currently `NOT NULL`, so a sentinel (`0`) is the only migration-free option and every later query must special-case it. | Migration + data change; no API change | No test asserts ticket identity is scrubbed at withdrawal or at the sweep. Add both, plus a backfill test on a pre-existing orphaned row. |
| PII-102 | Low — two call sites; any log parser keyed on the raw `chat_id` breaks. | Yes | No test asserts the log output of the `immediate_alerts` failure branches. Add one per branch. |
| PII-103 | **High** — removing `is_declined`/`is_deleted`/`ads_auto_publish` from the form breaks any operator workflow that used them; `chat_id` is `required=True` today, so a `readonly_fields`-only change still forces it into the form and a `fields`-only change still demands a value. | Yes (schema untouched) | No test asserts the admin form's field set. `test_admin_pii_containment.py` covers `list_display` helpers only. Add a form-introspection test (this is also `04-VAL-004`'s required test). |
| PII-104 | Medium — withdrawn/declined/banned users stop receiving alerts; some may perceive it as a service regression. Wrongly *not* "fixing" it by nulling `chat_id` would break `AccountStateMiddleware._get_user` and re-open withdrawn identities. | Yes | No test covers a revoked/declined/banned `SavedSearch` owner in `send_alerts` or `find_matching_saved_searches`. Add one per state, per path. |
| PII-105 | **High** — option (a) changes the auth predicate: a declined seller regains web login, and can then reach `/dashboard/`. Needs its own security review and an owner decision. | **No** — deliberately changes the auth predicate | `src/backend/apps/users/tests/test_account_state.py:160-168` asserts `can_login(is_declined=True) is False` and **will break**; per project rule 2 that test is updated, not worked around. Add a test for the logged-out recovery path. |
| PII-106 | Low — staff changelist columns and searchability change. | Yes | `test_admin_pii_containment.py` does not cover `SupportTicketAdmin`; see **VAL-007** before writing the generalised guard. |
| PII-107 | Low — adds a row to `consent_records` on the admin path. The `ConsentRecord` count assertions in `test_consent.py` use a `before + 1` delta scoped to the view, so they are unaffected. | Yes | No test covers the service-level audit row. Add one asserting `choice='WITHDRAWN'` after `withdraw_consent()` itself. |
| PII-108 | Medium — suppressing writes would change seller-dashboard numbers and `rollup_daily_metrics`; renaming the consent flag touches the `categories` JSON written on every consent action. | Yes (the doc-only path is fully compatible) | No test asserts `query_normalized` redaction, and none asserts behaviour for a DECLINED authenticated user. Add both. |
| PII-109 | **High** — scrubbing `title*`/`description*` makes the ad unsearchable unless the FTS vectors are re-derived (**VAL-009**), and the change is user-visible. | **No** — deliberately destroys user content | Existing deletion tests assert ad *status* only; add a content-scrub assertion **and** an FTS-consistency assertion. |
| PII-110 | Medium — clearing `preferred_city` changes dashboard default-city behaviour (the `preferred_city` **cookie** is already deleted on decline, so the asymmetry is itself the defect). | Yes | `test_preferred_city*.py` cover the cookie, not the DB column on withdrawal. |
| PII-111 | Low — dropping the column requires a migration; no operator workflow is keyed on it (nothing writes or reads it). | Yes | No test needed for the removal; a `makemigrations --check` gate covers the schema. |
| PII-112 | Medium — a keyed mask changes every derived value and adds a required secret. | Yes (if the key is provisioned) | `src/backend/apps/core/tests/test_sanitize.py:14-20` pins `length == 13` and **will fail**; `test_login.py` only asserts the raw value is absent, so it survives. Update the sanitize test to assert the *property*, not the length. |
| PII-113 | Low — docs only. | Yes | n/a |
| PII-114 | Low — moderation reason text becomes redacted; staff lose verbatim quotes. | Yes | No test asserts reason redaction. |
| PII-115 | n/a — **rejected**. | n/a | n/a |
| PII-116 | **Medium** — adds a destructive sweep; must be ordered so it can never delete a record still needed for an Art. 7(1) demonstration. | Yes | New sweep needs a `--dry-run` and an explicit TTL test, plus a test that rows inside the TTL survive. |

**Circular dependencies:** none. The only ordering constraints are the linear
chains listed under *Dependency chains* above.

**Hidden dependencies:** two. (1) PII-102's severity argument depends on
`IMMEDIATE_ALERTS_ENABLED` being `False` — verified in
`config/settings/base.py:349` and all four `.env.*.example` templates; if any
environment has flipped it, PII-102's justification changes but the finding does
not. (2) PII-109's correctness depends on the FTS trigger being installed; a
scrub on a schema without `ads_search_vector_update` would leave stale vectors
(**VAL-009**).

**Unsafe execution sequences:**
1. Enabling `IMMEDIATE_ALERTS_ENABLED` before PII-102 **and** PII-104 land.
2. Nulling `chat_id` as a "fix" for PII-104 — breaks `AccountStateMiddleware`.
3. Scrubbing ad text without re-deriving FTS vectors (PII-109 / VAL-009).
4. Shipping PII-112 without correcting the spec and the docstring (VAL-008).
5. Wiring `withdraw_consent_action` before PII-107 makes it auditable.
6. Building the generalised admin-containment test exactly as PII-106 recommends
   (VAL-007).

---

## Remediation Roadmap (revised order)

| Order | ID | Severity | Effort | Priority | Recommendation (summary) |
|-------|----|----------|--------|----------|--------------------------|
| 0 | **PII-103 → 04-AUT-005** | HIGH | S | **P0** | One `fieldsets` declaration on `UserAdmin` + a purpose-built form: identity columns and `password` read-only; `is_declined`/`is_deleted`/`ads_auto_publish` **removed** from the form. Closes the credential half (04) and the consent-integrity half (06) together. |
| 1 | **PII-101** | CRITICAL | M | **P0** | Make `SupportTicket.chat_id`/`telegram_id` nullable; clear `telegram_id`/`chat_id`/`username` in `withdraw_consent()` and again in `consent_hard_delete` before `queryset.delete()`; data migration for existing **and** already-orphaned rows. |
| 2 | **PII-112 → PII-102** | MEDIUM → HIGH | S + S | P0/P1 | Keyed HMAC mask (12 hex) + `LOG_MASK_KEY` plumbing + corrected spec/docstring; then mask `payload["chat_id"]` at the two `immediate_alerts` sites. Ship together. |
| 3 | **PII-104** (after **VAL-003**) | HIGH | M | **P0** | Owner decision, then one queryset-level account-state predicate in `apps/users`, consumed by `_collect_alerts`, `_dry_run_check`, `find_matching_saved_searches` and `find_matching_ads`; deactivate `SavedSearch` and delete `SearchHistory` in `withdraw_consent()`. |
| 4 | **Required Fix 1 — PII inventory** | — | M | **P0** | One declarative registry (model → identity column → erasure action) consumed by `withdraw_consent()`, `consent_hard_delete` and the backfill migration. Turns fixes 1, 5, 8, 9, 11 into one-line changes. |
| 5 | **PII-107** (with fix 0) | MEDIUM | S | P1 | Move the `ConsentRecord` write into `withdraw_consent()` behind an explicit context object; then wire-or-remove `withdraw_consent_action`. |
| 6 | **PII-105** (after **VAL-001**) | MEDIUM | M | P1 | Owner decision on DECLINE reversibility; either way, a session-independent recovery path, a discoverable affordance, and a non-silent anonymous Accept. Ships with ru/bs `.po` updates (VAL-006). |
| 7 | **PII-106** | MEDIUM | S | P1 | Masked `list_display` for `SupportTicketAdmin`; drop `text` from `search_fields`; extend the containment guard per **VAL-007** (explicit data-subject column set, not a blanket ban). |
| 8 | **PII-109** (with **VAL-009**) | MEDIUM | S | P1 | Scrub withdrawn ads' `title*`/`description*` **and** re-derive the FTS vectors, or correct the spec's "anonymized" wording. |
| 9 | **PII-110** (kept half) | MEDIUM | S | P1 | Document the `chat_id` retention trade-off in `privacy.html` §6; clear `preferred_city` on decline and withdrawal; delete `SearchHistory` on withdrawal. |
| 10 | **PII-108** | MEDIUM | M | P1 | Document `categories["analytics"]` as third-party scripts only; fix `query_normalized` so it never stores un-redacted PII. |
| 11 | **PII-116** (absorbs PII-110's `ConsentRecord` half) | LOW | S | P2 | Agree a TTL, add `purge_consent_records` to `HOURLY_COMMANDS` with `--dry-run`; drop `session_key` from `list_display`. |
| 12 | **PII-111** | LOW | S | P2 | `RemoveField` migration for `SellerVerification.phone_number` (nothing writes it). |
| 13 | **PII-114** | LOW | S | P2 | Redact `ModeratorActionLog.reason` / `Ad.rejected_reason` at write time. |
| 14 | **PII-113** (with **VAL-001**/**VAL-004**) | MEDIUM | S | P1 | One edit to `spec-index.md:74`; correct the phase-06 rubric; state DECLINE reversibility. Docs only — sequenced here because it gates step 6. |
| — | PII-115 | — | — | — | **Rejected — no remediation.** |

---

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (unchanged) | 6 | PII-101, PII-106, PII-109, PII-112, PII-114, PII-116 |
| Validated with narrowed/corrected scope (severity held) | 3 | PII-104, PII-107, PII-110 |
| Reclassified (type change) | 2 | PII-105 (→ DOC-UPDATE + BEST-PRACTICE), PII-108 (→ DOC-UPDATE + BEST-PRACTICE) |
| Severity-adjusted | 2 | PII-102 CRITICAL → HIGH; PII-111 MEDIUM → LOW |
| Merged | 2 | PII-103 → 04-AUT-005; PII-113 ↔ 04-VAL-005 |
| Rejected | 1 | PII-115 |
| VAL- (cross-phase / rollout / audit-input) | 12 | VAL-001 … VAL-012 |

**Severity after validation:** 1 CRITICAL · 3 HIGH · 7 MEDIUM · 3 LOW · 1 rejected.

Counting rule, so the totals are unambiguous: the 3 HIGH are PII-102 (adjusted),
PII-103 (merged away into phase 04 — listed here for continuity, **not** to be
tracked twice) and PII-104. The 7 MEDIUM are PII-106, 107, 108, 109, 110, 112,
113. The 3 LOW are PII-111 (adjusted down from MEDIUM), PII-114 and PII-116.
PII-115 is rejected and carries no severity. Total 16 = 1 + 3 + 7 + 3 + 1 + 1.

**Movement from the auditor's report:** 2 CRITICAL → 1; 8 MEDIUM → 7;
3 LOW → 3 (PII-111 moved down into LOW, PII-115 removed).

### Rejected Findings

| ID | Title | Reason |
|----|-------|--------|
| PII-115 | `create_admin_user` writes the raw `username` to stdout | The privacy claim is false. The command creates a *local bootstrap admin* from an operator-supplied `--username` with a placeholder `--telegram-id` (default `-1`); it never prints a seller's `@handle`, and `technical-specification.md:90` requires masking for `telegram_id` values only — which the command does at every occurrence. An operator-chosen local admin username echoed to that operator's own terminal is not a privacy exposure. The underlying "masking is per-call-site" observation is retained as an advisory note inside PII-102. |

### Merged Findings

| Original ID | Merged Into | Rationale |
|-------------|-------------|-----------|
| PII-103 | `04-AUT-005` (+ `04-VAL-004`), phase 04 | **Identical root cause**: `UserAdmin` declares no `fields`/`fieldsets`/`form`, so Django auto-builds a `ModelForm` over all 22 editable model fields. PII-103 is the identity/consent-flag view of the same 22-field form that 04-VAL-004 discovered as a plaintext-credential exposure. One `fieldsets` declaration closes both; two patches to the same class would each be partial. The merged content that 04-AUT-005 must additionally carry is PII-103's requirement that `is_declined`/`is_deleted`/`ads_auto_publish` be **removed** (not merely read-only) from the form, so every consent-state transition goes through the service that writes the audit row. |
| PII-113 | `04-VAL-005`, phase 04 | The same `spec-index.md:74` vs `technical-specification.md:101` contradiction, already filed by phase 04 and used there to feed AUT-002. PII-113 is the statement of record (it is more precise and it names a third, incorrect source — the phase-06 rubric); `04-VAL-005` becomes a cross-reference. See VAL-001. |

### Reclassified Findings

| ID | Original Type | New Type | Rationale |
|----|---------------|----------|-----------|
| PII-105 | Consent semantics / availability (implied code defect) | **DOC-UPDATE + BEST-PRACTICE** | Hiding published ads and blocking login on DECLINE are both explicitly specified in `technical-specification.md:85,96,101` and the code implements them. The contradicting statement is a stale condensed index line, not the code. What survives as a defect is a broken, undiscoverable, session-dependent recovery affordance plus a false statement in `privacy.html` §7 — an availability/UX problem requiring an owner decision, not a state-machine bug. |
| PII-108 | Privacy / consent enforcement (implied violated gate) | **DOC-UPDATE + BEST-PRACTICE** | `technical-specification.md:161,163` already sanctions first-party `AnalyticsEvent` rows carrying a `user_id` under legitimate interest, so there is no gate to enforce. The residual defect is a consent-*taxonomy* naming collision (one name, two scopes) plus — newly identified — `SearchHistory.query_normalized` storing the un-redacted query. |

### Severity Adjustments

| ID | From | To | Rationale |
|----|------|----|-----------|
| PII-102 | CRITICAL | **HIGH** | Real and a direct violation of `technical-specification.md:90`, but: the path is behind `IMMEDIATE_ALERTS_ENABLED`, which is `False` by default in `config/settings/base.py:349` and in all four `.env.*.example` templates; it fires only on the two send-failure branches, never on the send path; the leaked value is the recipient's own ID into an operator-controlled log, with no third-party disclosure; and the fix is two lines with no data risk. The phase rubric rates any raw identifier in any log as CRITICAL (VAL-005) — that blanket rule is the over-rating. The auditor's most alarming impact sentence is derivative of PII-104 and cannot be scored independently. |
| PII-111 | MEDIUM | **LOW** | The premise is refuted: grep for `phone_number` across `src/` returns only the model field, its migration, and two unrelated test assertions. No view, admin, service, bot handler or command writes it; `apps/trust/` registers no `ModelAdmin`; the probe DB held 0 rows. The auditor's runtime evidence was the probe's own insert. What remains is a vestigial, permanently-NULL, unreachable, undisclosed column — schema hygiene and documentation, not a live privacy incident. |

---

## Required Fixes

1. **Close the `UserAdmin` field contract once** (PII-103 → `04-AUT-005`).
   Declare explicit `fieldsets` and a purpose-built form: `password`,
   `telegram_id`, `chat_id`, `username`, `first_name`, `last_name`, `email` in a
   read-only identity section, and **remove** `is_declined`, `is_deleted` and
   `ads_auto_publish` from the form entirely. Any `is_staff` user can currently
   read a superuser's PBKDF2 hash in cleartext, write an arbitrary string
   unhashed and permanently destroy that credential, re-attach an erased Telegram
   identity to a withdrawn account, and flip `is_declined` off without an audit
   row or a cache bump. This is the highest-consequence defect in the phase.

2. **Scrub `SupportTicket` identity** (PII-101). Nullable columns + scrub in
   `withdraw_consent()` **and** `consent_hard_delete` + a data migration covering
   already-orphaned rows. This is the one confirmed CRITICAL: it is a provable
   breach of a published erasure promise, and it is silent.

3. **Fix the mask before you rely on it** (PII-112 then PII-102, one unit).
   Keyed HMAC-SHA256 with a provisioned `LOG_MASK_KEY`, a 12-hex prefix, the spec
   line and the docstring corrected in the same commit — then mask the two
   `immediate_alerts` call sites. Neither is safe alone.

4. **Decide and implement the alert-audience predicate** (PII-104, after VAL-003).
   One queryset-level consent predicate owned by `apps/users`, consumed by all
   four alert call sites, plus `SavedSearch` deactivation and `SearchHistory`
   deletion in `withdraw_consent()`. **Gate the `IMMEDIATE_ALERTS_ENABLED` rollout
   on this landing.**

5. **Build the PII inventory before the next identity column is added**
   (Required Fix 1). A single declarative registry consumed by
   `withdraw_consent()`, `consent_hard_delete` and the backfill migration. Five
   findings in this phase (PII-101, PII-109, PII-110, PII-111, PII-114) are
   separate symptoms of its absence; without it, the sixth will appear with the
   next model that denormalises identity.

6. **Resolve the DECLINE doc conflict and then the DECLINE design question**
   (PII-113 / VAL-001, then PII-105). One edit to `spec-index.md:74`; correct the
   phase-06 rubric; record whether DECLINE is reversible. Do not change
   `can_login()` before this lands — and coordinate with `04-AUT-002`, which
   touches the same predicate.

7. **Make consent revocation self-auditing** (PII-107), in the same change as
   fix 1, and then wire-or-remove `withdraw_consent_action`.

8. **Correct the two document falsehoods** (VAL-008: `mask_telegram_id` is not
   non-reversible; PII-110: `privacy.html` §6 over-promises what §7 also
   over-promises). A published policy that is not true is itself the defect for a
   consent-driven product.

---

## Advisory Recommendations (optional)

1. **A shared identity-logging filter — declined.** PII-102's recommendation
   proposes a `logging.Filter` that "refuses any record argument named
   `chat_id`/`telegram_id`". It is a naming-convention guard, not a type system:
   it cannot see `user.chat_id` passed positionally, and it adds a global logging
   behaviour change to close two call sites. Negative ROI at this project scale
   (project rule 5). If the invariant is wanted later, the durable form is a typed
   `Identity` value object, not a filter.
2. **Generalise the admin PII containment guard — with care.** Worth doing, but per
   VAL-007 it must be an explicit declared set of *data-subject* identity columns,
   not a blanket ban, or it will false-positive on `SupportContactAdmin`.
3. **A test that enumerates every registered `ModelAdmin`'s form field set.** This
   is the cheapest possible tripwire for the class of defect that `04-VAL-004` and
   PII-103 both hit, and it would have caught both automatically.
4. **Wire `purge_consent_records` next to the existing sweeps** (PII-116) rather
   than as a bespoke job, and give it a `--dry-run` like `consent_hard_delete`.
5. **Consider an explicit `pending_erasure` state** for DECLINE if option (b) is
   chosen in PII-105 — it would let the system warn the seller before live listings
   disappear, which is the actual harm the finding describes.
6. **Phase 06's own rubric should be corrected** (VAL-004) and its severity
   taxonomy refined (VAL-005) before this phase is re-run, so a future pass does not
   re-derive VAL-001 or re-rate PII-105.
7. **Serialise the audit test runs** (VAL-010) or give each validator its own
   database name; the current single `test_mko_bazuna` cannot support parallel
   validators and will manufacture red gates.

---

## Appendix A — Reproduction

All evidence in this report was produced by a single read-only probe executed in
the `mko-bazuna-test` image against a throwaway database. The probe was deleted and
the database dropped; the phantom `mko_bazuna` database was never opened (the
`CREATE`/`DROP DATABASE` statements were issued over the maintenance `postgres`
database instead).

```powershell
# Scratch schema in the throwaway DB (never mko_bazuna)
# 1. set connections["default"].settings_dict["NAME"] = "postgres"
# 2. CREATE DATABASE val06_probe  ->  redirect to val06_probe
# 3. call_command("migrate", "--run-syncdb"); load_exchange_rates; setup_search_triggers

docker compose --project-name mko-bazuna-test --env-file .env.test `
  -f docker-compose.yml -f docker-compose.test.yml `
  run --rm --no-deps --entrypoint "" -e DJANGO_SETTINGS_MODULE=config.settings.test `
  test python /app/.ai/tmp/val06_probe.py
```

Two environment notes for anyone re-running this:

- `config/settings/test.py:28` hardcodes the connection name, so **the connection
  override must happen before the first ORM call** (VAL-012).
- `django.test.Client` returns HTTP 400 for every request unless
  `ALLOWED_HOSTS` admits `testserver`. The pytest runner normally patches this via
  `setup_test_environment()`; a standalone probe must set it explicitly, or it will
  mis-report consent-view behaviour as a server fault.

Test baseline (V-08): `src/backend/apps/users/tests` — 139 tests, exit 0, no
failure or error markers in the pytest progress line, on `--reuse-db` with
`PYTEST_SKIP_MARKERS=seed`. A wider scope (users + core + search) run *in parallel
with other validators* returned 6 ERRORs that were the `test_mko_bazuna` teardown
race described in **VAL-010**, not product failures; re-running serially is
required before treating any red gate as a defect.

