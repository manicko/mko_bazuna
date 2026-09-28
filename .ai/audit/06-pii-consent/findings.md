---
phase: "06"
phase_name: "PII Protection & Consent Compliance"
date: "2026-09-28"
auditor: "Executor (subagent)"
validator: ""
mode: "problems-only"
id_prefix: "PII"
report_status: "draft"
severity_taxonomy: ".kilo/commands/audit/phases/06-audit-pii-consent.md#severity-taxonomy"
---

# Audit Findings — PII Protection & Consent Compliance

## Executive Summary

The site's consent machinery works for the common case: declining blocks a seller's
login, withdrawing soft-deletes the account and hides its ads, the 30-day erasure job
removes the identity and its ads, and the anonymous contact button is correctly
withheld in all 16 revoked/banned/deleted combinations. However, three serious gaps
remain. First, a user's raw Telegram identifier and public handle survive the full
30-day erasure inside support tickets, orphaned so that no future job can ever find
them. Second, the raw Telegram identifier is written unredacted to application logs,
and the log "mask" the spec relies on is only a 32-bit hash that can be brute-forced
back to the real ID. Third, the staff admin form lets any moderator type a fresh
Telegram ID into a withdrawn account, undoing the erasure guarantee, and the
outbound Telegram alert channel keeps messaging users who already withdrew consent.
The practical business impact is that a seller who withdraws consent is not actually
forgotten, and a seller who merely declines consent can permanently lose the
visibility of their already-published ads with no way to get them back.

## Scope & Methodology

**Scope:** The identity/PII zone (`apps/users` — `User`, `LoginToken`, `ConsentRecord`,
`account_state`, `consent_record`, `deletion`), the consent state machine
(`views/consent.py`, `context_processors.consent_state`), the contact-gating layer
(`apps/core/services/contact.py`, `contact_tags`, `telegram_tags`,
`telegram_bot/handlers/contact.py`), the erasure sweep
(`core/management/commands/consent_hard_delete.py`), bot-side consent enforcement
(`telegram_bot/middlewares/permissions.py`, `handlers/login.py`), the registered
`ModelAdmin` surfaces for every consent/PII model, the analytics/search/saved-search
consumers of identity data, and the published privacy policy.

### Runtime Verification

| R# | Check | Method | Result |
|----|-------|--------|--------|
| R-01 | DECLINE sets no revocation ts, nulls no PII, does not delete ads; but ads become invisible and `can_login` flips to False | `.ai/tmp/audit06_probe.py` in `mko-bazuna-test` image, `decline_consent()` + `ListingsQuery.build_queryset()` | **FAIL** (partial — see PII-105, PII-113) |
| R-02 | WITHDRAW sets `consent_revoked_at`, soft-deletes, nulls `telegram_id`/`username`/name components; writes a `ConsentRecord` | same probe, `withdraw_consent()` + `ConsentRecord.objects.count()` | **FAIL** (PII-107: `ConsentRecord` count = 0) |
| R-03 | Contact deep-link blocked for unpublished / null-identifier / soft-deleted / banned / revoked — identically on web and bot | same probe, 16-combination matrix over `can_contact_seller()` and `get_seller_for_contact()` | PASS |
| R-04 | 30-day sweep removes the identity + ads + images, NULLs (not cascades) analytics/audit refs, idempotent on re-run | same probe, backdated `consent_revoked_at` + `call_command("consent_hard_delete")` twice | **FAIL** (PII-101: ticket row keeps raw IDs) |
| R-05 | No raw `telegram_id`/`username` in any log call | AST-window scan of every `logger.*` / `stdout.write` / `print(` in `src/` (non-test) | **FAIL** (PII-102, PII-115) |
| R-06 | Outbound alert audience honours consent/account state; hidden ads are not fanned out | `.ai/tmp/audit06_probe2.py`, `find_matching_ads()` / `find_matching_saved_searches()` over active/declined/withdrawn/banned saved searches | **FAIL** (PII-104, PII-109) |
| R-07 | Erased identity's analytics/audit rows survive with NULL refs, free-text moderator reason retained | probe 2, `AnalyticsEvent` / `ModeratorActionLog` after sweep | PASS (with LOW caveat PII-114) |
| R-08 | First-party `AnalyticsEvent` rows are not written for an authenticated user who declined | probe 2, `record_event(SEARCH_PERFORMED)` for `is_declined=True` user | **FAIL** (PII-108) |
| R-09 | Registered `ModelAdmin` form fields for `User` / `ConsentRecord` / `LoginToken` / `SupportTicket` do not expose editable PII or consent state | `.ai/tmp/audit06_admin_probe.py` — `ModelAdmin.get_form()` introspection (no rows written) | **FAIL** (PII-103, PII-106) |
| R-10 | 30-day window boundary is computed in UTC with `USE_TZ` | `grep USE_TZ` (absent → Django 5.2 default `True`), `timezone.now()` in `deletion.py:119` / `consent_hard_delete.py:49`, `timestamptz` columns | PASS |
| R-11 | Admin consent-withdrawal action produces an Art. 7(1) audit row | `inspect.getsource(UserAdmin.withdraw_consent_action)` + `withdraw_consent` | **FAIL** (PII-107) |
| R-12 | Existing consent/PII suites stay green | `PYTEST_SKIP_MARKERS=seed pytest src/backend/apps/users/tests src/telegram_bot/tests/test_account_state_middleware.py` | PASS (190 passed) |

> PASS results prove the audit was thorough; they are METHODOLOGY evidence, NOT findings.

**Tools used:** `Select-String` / `grep` (source), `python -c ast.parse` (syntax),
`docker compose … run --rm test` (Django probe scripts, `manage.py migrate --run-syncdb`,
`call_command`), `psql` (DB state), `uv run ruff check`, `uv run basedpyright`,
`inspect.getsource` (admin/audit introspection).

**Assumptions:** "Erasure" means the zone-R3 contract in
`docs/01-spec/technical-specification.md:86-90` (NULL identifier + handle, SET NULL
analytics/audit refs, delete ads+images after 30 days) as restated in
`privacy.html` §6. "Staff" means `User.is_staff` (the only moderator role that exists —
`User.role` maps `is_staff`/`is_superuser` to `ADMIN`, `users/models.py:157-172`).
Test settings disable migrations (`MIGRATION_MODULES = DisableMigrations()`), so probe
schemas were built with `connection.creation.create_test_db()`; `config.settings.test`
hardcodes `DATABASES["default"]["NAME"] = "mko_bazuna"`, so every probe overrode the
connection to the throwaway `audit06_probe` database and never touched the phantom DB.

<!-- PHASE 99 ADDS a Methodology Cross-Check here. -->

## Findings Summary

| ID | Title | Severity | Status | Category |
|----|-------|----------|--------|----------|
| PII-101 | Support tickets keep the raw Telegram ID and handle after the full 30-day erasure, orphaned so no sweep can ever find them | CRITICAL | Open | Privacy / GDPR Art. 17 |
| PII-102 | Raw `chat_id` (the Telegram identifier) is written unredacted to WARNING logs on alert-send failure | CRITICAL | Open | Privacy / log hygiene |
| PII-103 | `UserAdmin`'s auto-built ModelForm exposes `telegram_id`/`chat_id`/`is_deleted`/`is_declined` as editable to any staff user | HIGH | Open | Privacy / access control |
| PII-104 | The outbound Telegram alert channel ignores consent and account state, so withdrawn/declined/banned users keep being messaged | HIGH | Open | Privacy / consent propagation |
| PII-105 | DECLINE is a one-way door: a declined seller's published ads are hidden permanently with no path to restore them | HIGH | Open | Consent semantics / availability |
| PII-106 | `SupportTicketAdmin` renders the raw `chat_id` and `telegram_id` in the staff changelist and full-text-searches ticket bodies | MEDIUM | Open | Privacy / admin surface |
| PII-107 | `withdraw_consent()` writes no `ConsentRecord`, so any non-view revocation path is unauditable under Art. 7(1) | MEDIUM | Open | Consent / accountability |
| PII-108 | First-party `AnalyticsEvent` and `SearchHistory` writes are not gated on the recorded analytics/preferences consent | MEDIUM | Open | Privacy / consent enforcement |
| PII-109 | "Anonymized ads after withdrawal" is not implemented — the ad body is retained and staff-searchable for 30 days | MEDIUM | Open | Privacy / erasure completeness |
| PII-110 | Erasure scope gap: `chat_id`, `ConsentRecord.session_key`/`user_agent` and `preferred_city` are never erased, contradicting `privacy.html` §6 | MEDIUM | Open | Privacy / retention policy |
| PII-111 | `SellerVerification.phone_number` sits outside the withdrawal path and is undisclosed in the privacy policy | MEDIUM | Open | Privacy / data minimisation |
| PII-112 | `mask_telegram_id()` is a 32-bit truncated unsalted SHA-256 and is brute-forceable back to the real identifier | MEDIUM | Open | Privacy / pseudonymisation strength |
| PII-113 | Unresolved doc conflict on DECLINE semantics across `spec-index.md`, `technical-specification.md` and this phase's own rubric | MEDIUM | Open | Documentation |
| PII-114 | `ModeratorActionLog.reason` is free text, never redacted, and survives erasure as an orphan row | LOW | Open | Privacy / free-text storage |
| PII-115 | `create_admin_user` writes the raw public `username` to stdout while masking `telegram_id` in the same command | LOW | Open | Privacy / log hygiene |
| PII-116 | `ConsentRecord` has no retention policy and exposes a live `session_key` in the staff changelist | LOW | Open | Privacy / retention policy |

## Distribution

**Severity counts**

| CRITICAL | 2 |
|----------|---|
| HIGH | 3 |
| MEDIUM | 8 |
| LOW | 3 |

**Status counts**

| Status | Count |
|--------|-------|
| Open | 16 |

## Findings by Severity

### CRITICAL

#### PII-101: [CRITICAL] — Support tickets keep the raw Telegram ID and handle after the full 30-day erasure, orphaned so no sweep can ever find them

| Field | Value |
|---|---|
| **ID** | PII-101 |
| **Title** | Support tickets keep the raw Telegram ID and handle after the full 30-day erasure, orphaned so no sweep can ever find them |
| **Severity** | CRITICAL |
| **Category** | Privacy / GDPR Art. 17 (right to erasure) |
| **File(s)** | `src/backend/apps/core/models.py:126-140`, `src/backend/apps/users/services/deletion.py:128-152`, `src/backend/apps/core/management/commands/consent_hard_delete.py:77-86` |
| **Status** | Open |
| **Problem** | `SupportTicket` stores `chat_id` and `telegram_id` as non-nullable `BigIntegerField`s plus a `username` string, all copied verbatim from the Telegram sender. `withdraw_consent()` nulls only the *`User` row's* `telegram_id`/`username`; it never touches `support_tickets`. `consent_hard_delete` NULLs only `analytics_events.user_id` and `moderation_action_logs.user_id`, then deletes the user — and because the ticket's `user` FK is `on_delete=models.SET_NULL`, the ticket row survives with `user_id = NULL` **and its raw identifiers intact, forever**. |
| **Impact** | A seller who exercised their Art. 17 right to erasure still has their Telegram numeric ID and public handle stored in cleartext indefinitely, in a row that is no longer attached to any account. Because the identifying link is gone, no future sweep, retention job, or export filter can ever find or purge it — the record is permanently undiscoverable *and* permanently retained. Every future data-subject-access or deletion request that touches support history will be answered incompletely. |
| **Root Cause** | The erasure contract is expressed as a column list on `users` plus two explicit `UPDATE ... SET user_id = NULL` statements, with no registry of "tables that copy identity columns". Any table that denormalises identity drifts out of scope the moment it is added. |
| **Recommendation** | (1) In `withdraw_consent()`, also clear the ticket identity columns for the withdrawing user inside the same transaction: `SupportTicket.objects.filter(user=user).update(telegram_id=0, chat_id=0, username="")` — or better, make `telegram_id`/`chat_id` nullable and set them to `None`. (2) In `consent_hard_delete()`, before `queryset.delete()`, null the same columns for all `user_id__in=user_ids` so the 30-day path is self-sufficient. (3) Add a data migration to scrub existing rows. (4) Introduce a single declarative constant listing the identity columns per model so the erasure path and the migration cannot drift again. |
| **Effort** | S |
| **Priority** | P0 |

| Field | Value |
|---|---|
| **CWE** | CWE-459 (Incomplete Cleanup) |
| **Likelihood** | HIGH |

| Field | Value |
|---|---|
| **Related Findings** | PII-110, PII-111 |

**Evidence — `src/backend/apps/core/models.py:115-140`** *(supports: "the ticket row denormalises the raw Telegram identifier and handle, and `user` is the only link back to the account")*:
```python
class SupportTicket(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, ...
    )
    chat_id = models.BigIntegerField(help_text="Telegram chat_id for anonymous attribution")
    telegram_id = models.BigIntegerField(help_text="User's Telegram ID")
    username = models.CharField(max_length=255, null=True, blank=True, ...)
    text = models.TextField(help_text="Ticket body / message text")
```

**Evidence — `src/backend/apps/core/management/commands/consent_hard_delete.py:77-86`** *(supports: "the sweep nulls only two user references, then deletes the user, which SET-NULLs the ticket link and orphans the row")*:
```python
AnalyticsEvent.objects.filter(user_id__in=user_ids).update(user_id=None)
ModeratorActionLog.objects.filter(user_id__in=user_ids).update(user_id=None)
# Delete users - CASCADE will handle their ads (and ad_images via ORM)
deleted_count, _ = queryset.delete()
```

**Evidence — runtime, `.ai/tmp/audit06_probe.py` R-04** *(supports: "after the sweep the identity, its ads and its images are gone, the analytics row survives with `user_id = NULL` — and the ticket keeps every raw identifier")*:
```text
  before sweep: user rows = 1 | ads = 1 | images = 1
  after  sweep: user rows = 0 | ads = 0 | images = 0
  AnalyticsEvent row survived with user_id = None
  ModeratorActionLog rows for victim      = 0
  SupportTicket after sweep: user_id=None telegram_id=730000001 chat_id=730000001 username='probe_victim'
  re-run sweep completed, user rows still = 0
```

---

### CRITICAL

#### PII-102: [CRITICAL] — Raw `chat_id` (the Telegram identifier) is written unredacted to WARNING logs on alert-send failure

| Field | Value |
|---|---|
| **ID** | PII-102 |
| **Title** | Raw `chat_id` (the Telegram identifier) is written unredacted to WARNING logs on alert-send failure |
| **Severity** | CRITICAL |
| **Category** | Privacy / log hygiene |
| **File(s)** | `src/backend/apps/search/services/immediate_alerts.py:210-216`, `src/backend/apps/search/services/immediate_alerts.py:235-240`, `src/backend/apps/search/services/immediate_alerts.py:164-177` |
| **Status** | Open |
| **Problem** | `_send_payloads()` logs `payload["chat_id"]` in cleartext on both the permanent-failure and the retry-failure branches. `chat_id` is populated from `user.chat_id`, which is the seller's/buyer's raw Telegram numeric ID — `User.chat_id` is explicitly documented as "never nullified", so this value identifies a real person for the whole lifetime of the account, including the 30 days after consent withdrawal. The same file has a documented masking helper (`apps.core.utils.sanitize.mask_telegram_id`) and the codebase has regression tests asserting masked output elsewhere, so this path is an inconsistent omission, not a deliberate choice. |
| **Impact** | Every transient Telegram API hiccup writes an unmasked Telegram user ID into WARNING-level logs, which are the most aggressively retained and most widely shipped (aggregators, stdout capture, support bundles). A user who withdrew consent still has their identifier land in logs after the erasure, and a log reader can trivially map `chat_id` to a Telegram account. |
| **Root Cause** | The `chat_id` key is assembled in a plain `dict` payload that crosses the service boundary; nothing at the logging site normalises it, and the audit marker `mask_telegram_id` was applied ad-hoc per call site rather than through a shared formatter. |
| **Recommendation** | Mask at the two log sites: `logger.warning("Permanent immediate alert failure to chat %s: %s", mask_telegram_id(payload["chat_id"]), exc)`, and the same for the retry branch. Longer term, register a logging `Filter`/`Formatter` that refuses any record argument named `chat_id`/`telegram_id` unless it is already `tg_`-prefixed, so this class of leak cannot be reintroduced. |
| **Effort** | S |
| **Priority** | P0 |

| Field | Value |
|---|---|
| **CWE** | CWE-532 (Insertion of Sensitive Information into Log File) |
| **Likelihood** | HIGH |

| Field | Value |
|---|---|
| **Related Findings** | PII-112, PII-115 |

**Evidence — `src/backend/apps/search/services/immediate_alerts.py:176-180, 210-216, 235-240`** *(supports: "the payload carries `user.chat_id` verbatim and both failure branches log it raw")*:
```python
    return {
        "chat_id": user.chat_id,          # <- raw Telegram user ID
        "text": text,
        "reply_markup": reply_markup,
    }
...
                except (TelegramBadRequest, TelegramForbiddenError) as exc:
                    # Permanent failures — dead-letter (no retry).
                    logger.warning(
                        "Permanent immediate alert failure to chat %s: %s",
                        payload["chat_id"],        # <- UNMASKED
                        exc,
                    )
...
                    except AiogramError as retry_exc:
                        logger.warning(
                            "Immediate alert retry failed to chat %s: %s",
                            payload["chat_id"],    # <- UNMASKED
                            retry_exc,
                        )
```

**Evidence — AST scan of every `logger.*` / `stdout.write` / `print(` window in `src/` (non-test)** *(supports: "masking is applied at 8 other sites, so this is an inconsistent omission rather than a policy")*:
```text
src/backend/apps/moderation/admin_actions.py:107   MASKED
src/backend/apps/users/views/consent.py:432        MASKED
src/backend/apps/users/views/consent.py:442        MASKED
src/backend/apps/users/views/consent.py:450        MASKED
src/backend/apps/users/views/consent.py:464        MASKED
src/backend/apps/core/services/contact.py:133       MASKED
src/backend/apps/core/management/.../create_admin_user.py:79/95/119/124  MASKED
src/telegram_bot/handlers/login.py:114             MASKED
src/backend/apps/search/services/immediate_alerts.py:212  *** UNMASKED ***
src/backend/apps/search/services/immediate_alerts.py:236  *** UNMASKED ***
src/backend/apps/core/management/.../create_admin_user.py:87  *** UNMASKED (username) ***
```

---

### HIGH

#### PII-103: [HIGH] — `UserAdmin`'s auto-built ModelForm exposes `telegram_id`/`chat_id`/`is_deleted`/`is_declined` as editable to any staff user

| Field | Value |
|---|---|
| **ID** | PII-103 |
| **Title** | `UserAdmin`'s auto-built ModelForm exposes `telegram_id`/`chat_id`/`is_deleted`/`is_declined` as editable to any staff user |
| **Severity** | HIGH |
| **Category** | Privacy / access control |
| **File(s)** | `src/backend/apps/users/admin.py:14-53` |
| **Status** | Open |
| **Problem** | `UserAdmin` declares no `fields`, `fieldsets`, or `form`, so Django builds a `ModelForm` from the whole model. Introspection of the registered `ModelAdmin.get_form()` shows 22 editable fields, including `telegram_id` (`IntegerField`, not read-only), `chat_id` (`IntegerField`, `required=True`), `username`, `first_name`, `last_name`, `email`, and the four consent/account-state flags `is_deleted`, `is_declined`, `is_banned`, `ads_auto_publish`. `readonly_fields` covers only the three consent *timestamps*. `has_change_permission` returns `request.user.is_staff`, and `is_staff` is the only moderator role in the product (`User.role` maps `is_staff`/`is_superuser` to `ADMIN`). |
| **Impact** | Two distinct consent-integrity failures. (a) A moderator can write a fresh `telegram_id`/`chat_id` into a soft-deleted, consent-withdrawn account, re-attaching an identity whose PII was deliberately erased and defeating the `withdraw_consent` guarantee that "prevents re-linking" (the same re-link the `LoginToken` invalidation is there to block). (b) A moderator can flip `is_declined` back to `False` without going through `give_consent()`, which means the seller's ads reappear in public listings/search with **no** `consent_given_at`, **no** `ConsentRecord` row, and **no** search-cache-version bump — an inconsistent state where ads are public, the consent banner is hidden, and analytics consent is silently off. |
| **Root Cause** | The admin was written as a thin flag/timestamp view and relies on Django's implicit "expose the model" behaviour. Because `readonly_fields` lists only the timestamps, everything else — including the two columns that *are* the PII — is treated as operator-editable. |
| **Recommendation** | Declare explicit `fieldsets` on `UserAdmin` that put `telegram_id`, `chat_id`, `username`, `first_name`, `last_name`, `email` and `password` in a "Sensitive identity (read-only)" section, add them to `readonly_fields`, and expose only `is_banned` / `ads_auto_publish` as operator-editable state. Remove `is_declined`, `is_deleted` and `ads_auto_publish` from the form entirely: `is_declined` should only move through `decline_consent()`/`give_consent()` (so the cache bump and audit row always fire), and `is_deleted` only through `withdraw_consent()`. Gate `has_change_permission` on `is_superuser` for the identity fields. Note: this finding deliberately does **not** re-report the plaintext-`password` exposure already filed by Phase 04. |
| **Effort** | S |
| **Priority** | P0 |

| Field | Value |
|---|---|
| **CWE** | CWE-284 (Improper Access Control) |
| **Likelihood** | MEDIUM |

| Field | Value |
|---|---|
| **Related Findings** | PII-105, PII-107, PII-101 |

**Evidence — `src/backend/apps/users/admin.py:14-53`** *(supports: "no `fields`/`fieldsets`/`form` is declared, so the auto form exposes every model field; `readonly_fields` covers only the timestamps")*:
```python
@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ["is_banned", "is_deleted", "ads_auto_publish",
                   "consent_given_at", "consent_revoked_at"]
    list_filter = ["is_banned", "is_deleted", "ads_auto_publish", "is_staff", "is_superuser"]
    search_fields = ["telegram_id"]
    readonly_fields = ["consent_given_at", "consent_revoked_at", "deleted_at"]
    # <-- no `fields`, no `fieldsets`, no `form`
    def has_change_permission(self, request, obj=None) -> bool:
        return request.user.is_staff
```

**Evidence — runtime, `.ai/tmp/audit06_admin_probe.py` (`ModelAdmin.get_form()` introspection, no rows written)** *(supports: "`telegram_id`, `chat_id`, `username` and all four consent flags are editable fields, and change permission is granted to staff")*:
```text
ModelAdmin: users.User  ->  UserAdmin
  form fields (auto-built ModelForm):
    - ads_auto_publish       BooleanField       required=False readonly=False
    - chat_id                IntegerField       required=True  readonly=False
    - email                  EmailField         required=False readonly=False
    - first_name             CharField          required=False readonly=False
    - is_active              BooleanField       required=False readonly=False
    - is_banned              BooleanField       required=False readonly=False
    - is_declined            BooleanField       required=False readonly=False
    - is_deleted             BooleanField       required=False readonly=False
    - is_staff               BooleanField       required=False readonly=False
    - is_superuser           BooleanField       required=False readonly=False
    - password               CharField          required=True  readonly=False
    - telegram_id            IntegerField       required=False readonly=False
    - username               CharField          required=False readonly=False
  readonly_fields   : ['consent_given_at', 'consent_revoked_at', 'deleted_at']
  declared fields/fieldsets/form : None None <class 'django.forms.models.ModelForm'>
  has_change_perm(staff) : True
```

---

#### PII-104: [HIGH] — The outbound Telegram alert channel ignores consent and account state, so withdrawn/declined/banned users keep being messaged

| Field | Value |
|---|---|
| **ID** | PII-104 |
| **Title** | The outbound Telegram alert channel ignores consent and account state, so withdrawn/declined/banned users keep being messaged |
| **Severity** | HIGH |
| **Category** | Privacy / consent propagation |
| **File(s)** | `src/backend/apps/search/management/commands/send_alerts.py:80-136`, `src/backend/apps/search/services/alert_query.py:153`, `src/backend/apps/search/services/immediate_alerts.py:93-113`, `src/backend/apps/users/models.py:48-53` |
| **Status** | Open |
| **Problem** | Both alert delivery paths select their audience purely by `SavedSearch.is_active=True`. `send_alerts._collect_alerts()` iterates every active saved search; `_send_user_digests()` then only checks `user.chat_id` before sending. `find_matching_saved_searches()` (publish-time fan-out) applies the same single filter. No path consults `is_deleted`, `is_declined`, `consent_revoked_at` or `is_banned`. Because `withdraw_consent()` nulls `telegram_id` but deliberately keeps `chat_id` ("never nullified"), and `SavedSearch` is only `CASCADE`-deleted when the user row is finally removed 30 days later, the delivery target survives the entire withdrawal window. |
| **Impact** | A user who withdrew consent is still pushed daily saved-search digests derived from their own saved-search history for up to 30 days after they asked to be forgotten — the exact processing the withdrawal was meant to stop. A user who merely *declined* (browse-only, `consent_analytics=False`, `consent_preferences=False`) is messaged indefinitely. A *banned* account — which the product treats as fully restricted — still receives outbound traffic. Every one of these sends is also the event that produces the unmasked log line in PII-102. |
| **Root Cause** | Account state is enforced at the *interaction* boundary (the bot's `AccountStateMiddleware`, the web views) but not at the *proactive delivery* boundary. `send_alerts`/`immediate_alerts` treat `SavedSearch.user` as a plain FK and never join the consent predicate; the shared `get_account_state()` helper has no caller in the search app. |
| **Recommendation** | Add one shared, reusable audience filter and use it in both paths — e.g. `SavedSearch.objects.filter(is_active=True, user__is_deleted=False, user__is_declined=False, user__is_banned=False, user__consent_revoked_at__isnull=True)` in `send_alerts._collect_alerts`/`_dry_run_check` and in `find_matching_saved_searches`. Additionally, `withdraw_consent()` should `SavedSearch.objects.filter(user=user).update(is_active=False)` (and `SearchHistory.objects.filter(user=user).delete()`) inside the same transaction, so revocation actively tears down the subscriber state rather than relying on a future filter. The same filter should also exclude ads whose owner is declined so hidden ads are not fanned out (see PII-109). |
| **Effort** | S |
| **Priority** | P0 |

| Field | Value |
|---|---|
| **CWE** | CWE-359 (Exposure of Private Personal Information to an Unauthorized Actor) |
| **Likelihood** | HIGH |

| Field | Value |
|---|---|
| **Related Findings** | PII-102, PII-105, PII-109, PII-110 |

**Evidence — `src/backend/apps/search/management/commands/send_alerts.py:112-114, 170-175`** *(supports: "the audience is `is_active=True` only, and the only per-user gate before sending is `chat_id`")*:
```python
        for saved_search in SavedSearch.objects.filter(is_active=True).select_related(
            "user", "city", "category"
        ):
            matching_ads = find_matching_ads(saved_search)
...
                if not user.chat_id:            # the ONLY account-state check
                    logger.warning("User %d has no chat_id - cannot send alert", user_id)
                    continue
                ...
                await bot.send_message(chat_id=user.chat_id, text=message, parse_mode="HTML")
```

**Evidence — runtime, `.ai/tmp/audit06_probe2.py` R-06** *(supports: "active, DECLINED, consent-WITHDRAWN and BANNED saved searches all match the same ad, and the ad itself is hidden from the public site")*:
```text
  active           user_id=1 is_declined=False is_deleted=False is_banned=False consent_revoked_at=NULL
  declined         user_id=2 is_declined=True  is_deleted=False is_banned=False consent_revoked_at=NULL
  withdrawn_soft   user_id=3 is_declined=False is_deleted=True  is_banned=False consent_revoked_at=set
  banned           user_id=4 is_declined=False is_deleted=False is_banned=True  consent_revoked_at=NULL

  Ad from a DECLINED seller: status = published | hidden from site listings (user__is_declined=False)
  find_matching_ads(active          ) -> 1 ad(s): ['Велосипед скрытый']
  find_matching_ads(declined        ) -> 1 ad(s): ['Велосипед скрытый']
  find_matching_ads(withdrawn_soft  ) -> 1 ad(s): ['Велосипед скрытый']
  find_matching_ads(banned          ) -> 1 ad(s): ['Велосипед скрытый']
  same ad visible on the public site? False
  find_matching_saved_searches(hidden_ad) returns 4 saved search(es)
```

---

#### PII-105: [HIGH] — DECLINE is a one-way door: a declined seller's published ads are hidden permanently with no path to restore them

| Field | Value |
|---|---|
| **ID** | PII-105 |
| **Title** | DECLINE is a one-way door: a declined seller's published ads are hidden permanently with no path to restore them |
| **Severity** | HIGH |
| **Category** | Consent semantics / availability |
| **File(s)** | `src/backend/apps/users/services/account_state.py:96-106`, `src/backend/apps/users/views/consent.py:204-232`, `src/backend/apps/ads/services/listings_query.py:135`, `src/backend/apps/ads/views/listings.py:65,203` |
| **Status** | Open |
| **Problem** | `decline_consent()` sets `is_declined=True` + `ads_auto_publish=False`, and the live `user__is_declined=False` filter immediately removes the seller's PUBLISHED ads from listings, search, direct-URL detail access and the media gate. Simultaneously `can_login()` denies any `is_declined` user. `consent_decline` does **not** flush the session, so the only way to undo DECLINE is to re-POST `/consent/accept/` from an *authenticated* session — `consent_accept` only mutates the `User` row when `request.user.is_authenticated`. `SESSION_COOKIE_AGE` is not configured anywhere, so Django's 14-day absolute default applies and `SESSION_SAVE_EVERY_REQUEST` is left at `False`: the recovery window is at most 14 days, is not extended by activity, and the bot blocks every command for a declined user except contact deep-links. There is no other re-entry path. |
| **Impact** | A seller who clicks "Decline" has their already-published advertisements pulled off the public site immediately — a functional takedown of live listings that buyers can see — and if they do not re-accept inside the 14-day session window the takedown is **permanent from the seller's point of view**: they can no longer log in, the bot blocks them, and only a direct database edit by an operator can restore the account. The privacy policy (`privacy.html` §7) explicitly promises "You can revisit and change your consent choices at any time", and this design makes that untrue after 14 days. |
| **Root Cause** | Two independent decisions collide: `is_declined` was chosen as both a *visibility* switch and a *login* switch, and the login switch has no escape hatch. Because the reversal path depends on ambient session state rather than on a first-class "resume" action, the irreversibility is invisible at the point of decision. |
| **Recommendation** | Decide and document one of two coherent models, then implement it. (a) *DECLINE is reversible by design* — remove `is_declined` from `can_login()` (keep it in `can_publish_ad()` and the bot's publish gate), so a declined seller can still log in and re-accept; the spec's "blocks seller login/actions" would then need updating in `technical-specification.md:101` and `spec-index.md:74`. (b) *DECLINE is a one-way door by design* — then it must not silently un-publish existing ads, and the banner copy plus `privacy.html` §7 must say so. Recommended: (a), because it removes a permanent-content-takedown failure mode at the cost of one spec edit. Whichever is chosen, add a `password`-less `POST /consent/resume/` (or simply keep the current session valid) so the state is escapable without an operator. |
| **Effort** | M |
| **Priority** | P0 |

| Field | Value |
|---|---|
| **CWE** | CWE-672 (Operation on a Resource after Expiration or Release) |
| **Likelihood** | MEDIUM |

| Field | Value |
|---|---|
| **Related Findings** | PII-103, PII-113, PII-104 |

**Evidence — `src/backend/apps/users/services/account_state.py:96-106`** *(supports: "`can_login()` permanently denies a declined identity, so the only reversal is a still-live session")*:
```python
def can_login(user: User) -> bool:
    state = get_account_state(user)
    if state.is_banned:
        logger.info("User %s cannot login: banned", user.id)
        return False
    if state.is_declined:                       # <- no reversal path
        logger.info("User %s cannot login: declined consent", user.id)
        return False
    return True
```

**Evidence — `src/backend/apps/users/views/consent.py:204-213`** *(supports: "DECLINE does not flush the session, and re-accept only mutates the row when authenticated")*:
```python
    if user is not None and user.is_deleted:
        logger.warning("Soft-deleted user %s attempted consent decline -- rejected ...", user.id)
        return HttpResponseForbidden()

    if user is not None:
        decline_consent(user)
        target = "ads:dashboard"
    else:
        target = "/"          # anonymous: cookies only, NO DB mutation
```

**Evidence — runtime, `.ai/tmp/audit06_probe.py` R-01** *(supports: "after DECLINE the ad disappears from public listings, PII is intact, and `can_login` is False")*:
```text
after  decline  id=1 is_declined=True is_deleted=False ads_auto_publish=False consent_given_at=NULL
                consent_revoked_at=NULL telegram_id=700000001 username='probe_seller'
  ad_pub visible in public ListingsQuery after DECLINE = False
  can_login(after)   = False
  contact still allowed (can_contact_seller)          = True
```

**Evidence — `src/backend/templates/privacy.html` §7** *(supports: "the published policy promises the choice is revisable at any time")*:
```html
{% trans "7. Manage Your Consent" %}
{% trans "You can revisit and change your consent choices at any time. Use the" %}
```

---

### MEDIUM

#### PII-106: [MEDIUM] — `SupportTicketAdmin` renders the raw `chat_id` and `telegram_id` in the staff changelist and full-text-searches ticket bodies

| Field | Value |
|---|---|
| **ID** | PII-106 |
| **Title** | `SupportTicketAdmin` renders the raw `chat_id` and `telegram_id` in the staff changelist and full-text-searches ticket bodies |
| **Severity** | MEDIUM |
| **Category** | Privacy / admin surface |
| **File(s)** | `src/backend/apps/core/admin.py:47-48` |
| **Status** | Open |
| **Problem** | `SupportTicketAdmin.list_display` includes the raw `chat_id` and `telegram_id` columns, and `search_fields` includes `telegram_id`, `username` and the unbounded free-text `text` body. This is inconsistent with the product's own established containment rule: `LoginTokenAdmin.telegram_id_display` deliberately renders `mask_telegram_id(obj.telegram_id)`, and `apps/users/tests/test_admin_pii_containment.py` is a standing regression test that forbids raw-`telegram_id` rendering in every admin `list_display` helper. The `SupportTicket` surface was never brought under that rule. |
| **Impact** | Every ticket appears in the staff changelist with the requester's numeric Telegram ID in cleartext, so a single changelist screenshot or export is a bulk PII disclosure that the equivalent `LoginToken` surface is explicitly designed to prevent. In addition, `text` in `search_fields` turns the whole support corpus into a free-text search target for any staff account, which is a privilege the ticket model was not intended to grant. |
| **Root Cause** | The admin PII-containment work was done per-model (`users`, `ads`, `analytics`, `moderation`) and `SupportTicket` — registered in a different app — was not included in the sweep or in `test_admin_pii_containment.py`. |
| **Recommendation** | Replace the two raw columns with masked display methods (reuse `mask_telegram_id`), and drop `text` from `search_fields` (keep `ticket_ref` + masked/partial `telegram_id` if lookup is genuinely needed). Extend `test_admin_pii_containment.py` so it walks **every** registered `ModelAdmin` in `admin.site._registry` and asserts no `list_display` entry or display helper renders a raw identity column — that generalises the existing rule so the next model cannot regress it. |
| **Effort** | S |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **CWE** | CWE-200 (Exposure of Sensitive Information) |
| **Likelihood** | MEDIUM |

| Field | Value |
|---|---|
| **Related Findings** | PII-101, PII-112 |

**Evidence — `src/backend/apps/core/admin.py:47-48`** *(supports: "the changelist renders the raw identifier columns and searches the ticket body")*:
```python
@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    """Support Ticket admin (read-only audit trail)."""
```

**Evidence — runtime, `.ai/tmp/audit06_admin_probe.py` (registered `ModelAdmin` introspection)** *(supports: "raw `chat_id` and `telegram_id` are in `list_display`, and `text` is searchable — the opposite of `LoginTokenAdmin`")*:
```text
ModelAdmin: core.SupportTicket  ->  SupportTicketAdmin
  list_display      : ['ticket_ref', 'status', 'user', 'chat_id', 'telegram_id', 'created_at']
  search_fields     : ['ticket_ref', 'telegram_id', 'username', 'text']
  form fields (auto-built ModelForm):
    - status                 TypedChoiceField   required=True readonly=False

ModelAdmin: users.LoginToken  ->  LoginTokenAdmin
  list_display      : ['id', 'telegram_id_display', 'created_at', 'expires_at', 'consumed_at']
```

---

#### PII-107: [MEDIUM] — `withdraw_consent()` writes no `ConsentRecord`, so any non-view revocation path is unauditable under Art. 7(1)

| Field | Value |
|---|---|
| **ID** | PII-107 |
| **Title** | `withdraw_consent()` writes no `ConsentRecord`, so any non-view revocation path is unauditable under Art. 7(1) |
| **Severity** | MEDIUM |
| **Category** | Consent / accountability |
| **File(s)** | `src/backend/apps/users/services/deletion.py:72-161`, `src/backend/apps/users/admin.py:55-65`, `src/backend/apps/users/views/consent.py:268-273` |
| **Status** | Open |
| **Problem** | The `ConsentRecord` audit row for a withdrawal is written by the **view** (`consent_withdraw` calls `record_consent_action(...)` after `withdraw_consent()`), not by the service. `withdraw_consent()` itself never touches `ConsentRecord` — its docstring only mentions the model to explain that *none* is persisted. Any other caller of the service therefore revokes consent with no audit trail. The only such caller in the tree is the staff action `UserAdmin.withdraw_consent_action`, which loops over the queryset and calls `withdraw_consent(user)` directly; note that this action is decorated with `@admin.action` but is **never added to `UserAdmin.actions`**, so runtime introspection shows `UserAdmin.get_actions(request) == ['delete_selected']` and the action is not reachable from the admin changelist UI today. |
| **Impact** | The service that owns the consent state machine is unauditable by construction: GDPR Art. 7(1) obliges the controller to demonstrate consent, and the erasure side of that obligation lives entirely outside the operation that performs the erasure. The concrete exposure today is bounded — the only non-view caller is an unwired admin action, so no moderator can currently produce a silent unlogged revocation through the UI — but the defect is structural rather than incidental: the 30-day sweep keys off `users.consent_revoked_at` for a row that may have no corresponding `choice='WITHDRAWN'` entry, so the audit log and the erasure log can disagree, and the first person to wire up that action (which is clearly the intent) inherits the gap silently. |
| **Root Cause** | The consent-audit side effect was attached to the HTTP entry point instead of the domain operation, so it only exists on the path the author happened to be looking at. `record_consent_action` is also `request`-aware, which makes it awkward to call from non-HTTP contexts, encouraging the split. |
| **Recommendation** | Move the audit write into the service layer: give `withdraw_consent()` (and `decline_consent()`/`give_consent()` for symmetry) an optional `record` / `actor` parameter and write the `ConsentRecord` inside the same `transaction.atomic()` block, so the audit row and the state change commit or roll back together. Keep the view's call only for the HTTP-layer context (`ip_address`, `user_agent`, `session_key`) — or pass the `request` through. Then decide the intent of `withdraw_consent_action`: if moderator-initiated revocation is a real operator workflow, wire it (`actions = ["withdraw_consent_action"]`, restricted to superusers) now that it is auditable; if it is not, remove the dead action rather than leaving a landmine. Add a test asserting `choice='WITHDRAWN'` exists after the service call, not only after the view. |
| **Effort** | S |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **CWE** | CWE-778 (Insufficient Logging) |
| **Likelihood** | HIGH |

| Field | Value |
|---|---|
| **Related Findings** | PII-103, PII-101, PII-116 |

**Evidence — `src/backend/apps/users/admin.py:55-65`** *(supports: "the staff revocation path calls the service directly and never records a `ConsentRecord`")*:
```python
    @admin.action(description="Withdraw consent for selected users")
    def withdraw_consent_action(self, request, queryset):
        for user in queryset:
            withdraw_consent(user)          # <- no record_consent_action() anywhere
        self.message_user(request, f"Withdrew consent for {queryset.count()} user(s).")
```

**Evidence — runtime, `.ai/tmp/audit06_admin_probe.py` + `.ai/tmp/audit06_probe.py` R-02** *(supports: "the service never writes an audit row, and calling it directly leaves the table empty")*:
```text
withdraw_consent() source mentions ConsentRecord?: False
deletion.py module mentions ConsentRecord?: True      # docstring mention only

R-02  WITHDRAW path
  after  withdraw  id=2 is_deleted=True consent_revoked_at=set telegram_id=None username=None
  draft storage keys returned: []
  ConsentRecord rows        : 0                       # <- no Art. 7(1) proof
```

---

#### PII-108: [MEDIUM] — First-party `AnalyticsEvent` and `SearchHistory` writes are not gated on the recorded analytics/preferences consent

| Field | Value |
|---|---|
| **ID** | PII-108 |
| **Title** | First-party `AnalyticsEvent` and `SearchHistory` writes are not gated on the recorded analytics/preferences consent |
| **Severity** | MEDIUM |
| **Category** | Privacy / consent enforcement |
| **File(s)** | `src/backend/apps/search/views/search.py:336-339`, `src/backend/apps/search/services/search_history.py:65-83`, `src/backend/apps/ads/views/listings.py:72-76`, `src/backend/apps/core/services/analytics.py:19-60`, `src/backend/apps/users/context_processors.py:68-80` |
| **Status** | Open |
| **Problem** | The system records, stores and displays a granular per-category `analytics` consent flag (`ConsentRecord.categories`, the `consent_analytics` cookie, and the `consent_state` context processor). But `consent_analytics` is consumed **only** by template `{% if consent_analytics %}` guards around the Plausible snippet and the GLightbox JS. No server-side write path consults it: `search.py:336` records `SEARCH_PERFORMED` with `user_id=request.user.id` for any authenticated visitor; `record_search_history()` persists a `SearchHistory` row for any authenticated visitor; `ad_detail` records `AD_VIEWED`; and anonymous visitors who have never touched the banner still get `SEARCH_PERFORMED` rows written. |
| **Impact** | The product tells a visitor "analytics off" and then writes a per-identity behavioural record anyway. A user who clicked Decline — for whom `consent_state` forces `consent_analytics=False` and `consent_preferences=False` — still accumulates `search_performed` rows in `analytics_events` and full search-query text in `search_history`, and since DECLINE never triggers erasure (`SearchHistory` is `CASCADE` only) that history is retained indefinitely. The mismatch also makes the `ConsentRecord.categories` analytics flag misleading as evidence. |
| **Root Cause** | The spec scopes `consent_analytics` narrowly to *third-party script loading* (D7), and no one revisited that scoping when the first-party `AnalyticsEvent`/`SearchHistory` tables were added. There is a single context-processor flag but no service-layer consent predicate that write paths can call. |
| **Recommendation** | First make the product decision explicit in the spec — either (a) declare first-party `AnalyticsEvent`/`SearchHistory` to be on a legitimate-interest basis (the spec already takes this line for Plausible at `technical-specification.md:161`) and therefore not consent-gated, or (b) treat them as the `analytics` category. If (b), thread a `request`-level consent check into the three write sites (`search.py`, `search_history.record_search_history`, `listings.ad_detail`) and skip the write when `consent_analytics` is false. If (a), rename the flag to something like `consent_third_party_scripts` so the recorded artefact and the enforcement point stop disagreeing. Either way, add a test asserting the chosen behaviour for a DECLINED authenticated user. |
| **Effort** | M |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **CWE** | CWE-359 |
| **Likelihood** | HIGH |

| Field | Value |
|---|---|
| **Related Findings** | PII-104, PII-105, PII-110 |

**Evidence — `src/backend/apps/search/views/search.py:336-339`** *(supports: "an authenticated search writes a per-identity analytics row with no consent check")*:
```python
    record_event(
        AnalyticsEventType.SEARCH_PERFORMED,
        user_id=request.user.id if request.user.is_authenticated else None,
    )
```

**Evidence — runtime, `.ai/tmp/audit06_probe2.py` R-08** *(supports: "a user who has declined consent still gets analytics rows written under their identity")*:
```text
R-08  AnalyticsEvent for a DECLINED authenticated buyer
  declined buyer analytics rows: ['search_performed']
```

**Evidence — `src/backend/apps/users/context_processors.py:68-72`** *(supports: "the product's own consent processor reports analytics as OFF for that same user")*:
```python
        if user.is_declined or user.consent_revoked_at is not None:
            # Consent is a one-way gate: once declined or withdrawn, analytics
            # and preferences are permanently disabled for this request.
            consent_analytics = False
            consent_preferences = False
```

---

#### PII-109: [MEDIUM] — "Anonymized ads after withdrawal" is not implemented — the ad body is retained and staff-searchable for 30 days

| Field | Value |
|---|---|
| **ID** | PII-109 |
| **Title** | "Anonymized ads after withdrawal" is not implemented — the ad body is retained and staff-searchable for 30 days |
| **Severity** | MEDIUM |
| **Category** | Privacy / erasure completeness |
| **File(s)** | `src/backend/apps/users/services/deletion.py:164-231`, `docs/01-spec/technical-specification.md:89`, `src/backend/apps/ads/admin.py:80-108` |
| **Status** | Open |
| **Problem** | `technical-specification.md:89` states "Anonymized ads (post-withdrawal, pre-hard-delete) persist for 30 days only". `soft_delete_user_ads()` performs no anonymisation at all: it only routes each ad through `transition_to(AdStatus.DELETED)`, leaving `title`, `title_bs`, `title_en`, `description*` and `rejected_reason` byte-for-byte intact for the full 30-day window. `AdAdmin` has no default status filter, puts `title` in `list_display`, and declares `search_fields = ["title", "description"]`, so the retained body is listed and full-text searched by any staff user. |
| **Impact** | On a classifieds board the ad description is the most likely place for a seller to have typed their own name, a phone number, or a "call me at…" line. Those survive the withdrawal in cleartext, are exposed in a staff changelist, and are discoverable by full-text search over the whole ad corpus for 30 days after the seller asked to be forgotten. The spec's word "anonymized" is therefore not an accurate description of the current behaviour, and anyone relying on it (a DPO, a support agent, an auditor) is misled. |
| **Root Cause** | "Anonymize" in the spec means "the ad survives without its owner", which is satisfied by the `status` transition plus the FK cascade — the free-text body was never in scope of the implementation. |
| **Recommendation** | Either implement the scrub or correct the spec; recommend implementing a bounded version. In `soft_delete_user_ads()`, for the same ad set, overwrite the user-authored text fields with a neutral placeholder (e.g. `title="[withdrawn]"`, `description=""`, `rejected_reason=""`) inside the withdrawal transaction, and keep the FTS columns consistent by re-running the vector update. Then add a regression test asserting no ad of a withdrawn user retains the seller's marker string in any `title*`/`description*` field. If the scrub is judged too destructive, change the spec wording to "ads are soft-deleted (status=DELETED) and retain their original text for 30 days", and record the decision in `docs/00-overview/doc-maintenance-rules.md` so the deviation is deliberate. |
| **Effort** | S |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **CWE** | CWE-459 |
| **Likelihood** | MEDIUM |

| Field | Value |
|---|---|
| **Related Findings** | PII-101, PII-104, PII-110 |

**Evidence — `src/backend/apps/users/services/deletion.py:216-231`** *(supports: "soft deletion only transitions status; no field on the ad is scrubbed")*:
```python
    ads_deleted = 0
    for ad in Ad.objects.filter(user=user):
        try:
            ad.transition_to(AdStatus.DELETED)     # <- status only, no content scrub
        except (ValueError, Ad.DoesNotExist):
            logger.warning("Could not soft-delete ad %s for user %s ...", ad.id, user.id, exc_info=True)
            continue
        ads_deleted += 1
```

**Evidence — `docs/01-spec/technical-specification.md:89`** *(supports: "the spec claims the retained ads are 'anonymized'")*:
```markdown
   - Anonymized ads (post-withdrawal, pre-hard-delete) persist for 30 days only — NOT the 120-day `purge_deleted_ads` window
```

**Evidence — `src/backend/apps/ads/admin.py:80-100`** *(supports: "the retained body is listed and full-text searched by staff")*:
```python
    list_display = ["id", "title", "status", "category", "city", ...]
    list_filter = ["status", "category", "city", ...]
    search_fields = ["title", "description"]      # <- full-text over the whole corpus
```

---

#### PII-110: [MEDIUM] — Erasure scope gap: `chat_id`, `ConsentRecord.session_key`/`user_agent` and `preferred_city` are never erased, contradicting `privacy.html` §6

| Field | Value |
|---|---|
| **ID** | PII-110 |
| **Title** | Erasure scope gap: `chat_id`, `ConsentRecord.session_key`/`user_agent` and `preferred_city` are never erased, contradicting `privacy.html` §6 |
| **Severity** | MEDIUM |
| **Category** | Privacy / retention policy |
| **File(s)** | `src/backend/apps/users/models.py:48-53,80-87`, `src/backend/apps/users/services/deletion.py:128-152`, `src/backend/apps/users/models.py:237-270`, `src/backend/templates/privacy.html` §6 |
| **Status** | Open |
| **Problem** | `privacy.html` §6 promises "**All personal data is permanently erased within 30 days of withdrawal**". The erasure path nulls only `telegram_id`, `username`, `first_name`, `last_name`, `email` and `consent_given_at`. Four identity-bearing fields survive: (1) `User.chat_id` — documented as "never nullified", and it *is* the raw Telegram numeric ID, so the only protection is the 30-day `CASCADE`; (2) `User.preferred_city` — a persisted behavioural preference, `SET_NULL` only on city removal, never cleared on DECLINE (which forces `consent_preferences=False`) or on withdrawal; (3) `ConsentRecord.session_key` — a live Django session identifier, kept forever because `ConsentRecord` is `SET_NULL` and no retention job exists; (4) `ConsentRecord.user_agent` — a full 500-char browser fingerprint, likewise kept forever. |
| **Impact** | The published privacy commitment is not met as written, and the residue is exactly the kind of re-identifying material a data-subject-access request would surface: a raw Telegram ID in `chat_id`, and a session key + user-agent pair that together can single out and correlate a browser session indefinitely. `chat_id` surviving is also the mechanical reason PII-104 keeps working — the alert channel can still address a withdrawn user because the one column that should have been erased is the one column the delivery path needs. |
| **Root Cause** | The 30-day contract is a hand-maintained list of column names on one model, and the "never nullified" decision for `chat_id` was taken for the bot's benefit without reconciling it against the erasure promise or against the outbound-delivery paths that also read it. There is no per-table retention policy. |
| **Recommendation** | (1) Keep `chat_id` (the bot's soft-delete gate genuinely needs it) but add a documented retention rule and cite the trade-off in the spec — and gate every delivery path on it (PII-104). (2) In `withdraw_consent()`, clear `preferred_city` and delete the user's `SearchHistory` rows. (3) Give `ConsentRecord` a real retention policy: add a `retention_expires_at` (or reuse `consent_given_at` with a documented TTL) and a scheduled purge that deletes rows older than the chosen period, or at minimum null `session_key` and blank `user_agent` when the linked user is erased. (4) Amend `privacy.html` §6 to enumerate what is erased and what is retained-and-why (legal obligation vs. legitimate interest), so the public commitment matches the code. |
| **Effort** | M |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **CWE** | CWE-459 |
| **Likelihood** | HIGH |

| Field | Value |
|---|---|
| **Related Findings** | PII-101, PII-104, PII-116, PII-111 |

**Evidence — `src/backend/apps/users/models.py:48-53, 237-270`** *(supports: "`chat_id` is the raw Telegram ID and is never nullified; `ConsentRecord` keeps a session key and a 500-char user agent forever")*:
```python
    chat_id = models.BigIntegerField(
        unique=True, db_index=True,
        help_text="Stable Telegram chat ID; set on first bot contact, never nullified",
    )
...
    session_key = models.CharField(
        max_length=40, null=True, blank=True,
        help_text="Session key identifying an anonymous consent action",
    )
    user_agent = models.TextField(
        blank=True, max_length=500,
        help_text="Truncated User-Agent header from the consent request",
    )
```

**Evidence — `src/backend/apps/users/services/deletion.py:140-152`** *(supports: "the erasure `update_fields` list omits `chat_id` and `preferred_city`")*:
```python
        user.save(
            update_fields=[
                "consent_revoked_at", "is_deleted", "deleted_at", "consent_given_at",
                "telegram_id", "username", "first_name", "last_name", "email",
                # <- chat_id and preferred_city deliberately absent
            ]
        )
```

**Evidence — `src/backend/templates/privacy.html` §6** *(supports: "the public policy promises complete erasure within 30 days")*:
```html
{% blocktrans %}When you withdraw consent, your account and its advertisements are soft-deleted
immediately. All personal data is permanently erased within 30 days of withdrawal.
Consent state is otherwise retained for 12 months, after which you are re-prompted.{% endblocktrans %}
```

---

#### PII-111: [MEDIUM] — `SellerVerification.phone_number` sits outside the withdrawal path and is undisclosed in the privacy policy

| Field | Value |
|---|---|
| **ID** | PII-111 |
| **Title** | `SellerVerification.phone_number` sits outside the withdrawal path and is undisclosed in the privacy policy |
| **Severity** | MEDIUM |
| **Category** | Privacy / data minimisation |
| **File(s)** | `src/backend/apps/trust/models.py:38-51`, `src/backend/apps/users/services/deletion.py:128-152`, `docs/01-spec/technical-specification.md:82-83`, `src/backend/templates/privacy.html` §2 |
| **Status** | Open |
| **Problem** | `SellerVerification` carries a `phone_number` column, but the project's own data-minimisation rule is "Collect minimum: `telegram_id`, optional `username`. Users are maximally anonymous; **nothing beyond Telegram login is stored**" (`technical-specification.md:82-83`). A phone number is a *stronger* identifier than everything else the system holds, is the one field that re-identifies a person across platforms, and `withdraw_consent()` never touches it — the row only disappears via the 30-day `CASCADE`, and it survives **forever** for a user who only ever DECLINED (DECLINE triggers no erasure at all). The privacy policy's "Processing Purposes" section (§2) lists service delivery, contact relay, traffic analytics, personalization and language normalization, and never mentions a phone number. |
| **Impact** | The product collects and retains a high-value identifier it does not document, does not need (the trust system is driven by activity metrics, not by a phone number — `TrustCalculator` reads ad counts and response rates), and does not erase on the consent path a user would most expect it to. It is also the single most damaging field to leave behind in a breach or a data-subject-access export, and it is currently unmentioned in both the spec's data list and the published policy. |
| **Root Cause** | The field was added with the trust/verification feature and treated as operational metadata rather than as personal data; no cross-check exists between "columns on user-adjacent models" and the documented data categories. |
| **Recommendation** | Decide first whether the product needs it. Recommended: **remove `phone_number` from `SellerVerification`** (a migration with a data migration that nulls existing values) and rely on `verified_by_admin` + the trust score, which is what the badge logic actually reads. If the phone number is genuinely required for manual verification, then (a) add it to `withdraw_consent()`'s null set, (b) add a "Seller verification (admin) — phone number" row to `privacy.html` §2 and to `technical-specification.md` §F, and (c) mask it in any admin `list_display`. |
| **Effort** | S (removal) / S (documentation + null-on-withdraw) |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **CWE** | CWE-359 |
| **Likelihood** | MEDIUM |

| Field | Value |
|---|---|
| **Related Findings** | PII-110, PII-101 |

**Evidence — `src/backend/apps/trust/models.py:38-51`** *(supports: "a phone number is stored on a user-adjacent model")*:
```python
class SellerVerification(models.Model):
    """Seller verification status (admin and phone)."""
    user = models.OneToOneField("users.User", on_delete=models.CASCADE, related_name="verification")
    phone_number = models.CharField(max_length=20, blank=True, null=True)   # <- never nulled on withdraw
    verified_by_admin = models.BooleanField(default=False)
    verified_at = models.DateTimeField(blank=True, null=True)
```

**Evidence — runtime, `.ai/tmp/audit06_probe.py` R-01** *(supports: "the value is present and reachable after a consent action on the account")*:
```text
  SellerVerification.phone_number still present       = +38269000001
```

**Evidence — `docs/01-spec/technical-specification.md:82-83`** *(supports: "the documented data set excludes a phone number")*:
```markdown
- Jurisdiction: Montenegro (GDPR-equivalent). Collect minimum: `telegram_id`, optional `username`.
- Users are maximally anonymous; nothing beyond Telegram login is stored.
```

---

#### PII-112: [MEDIUM] — `mask_telegram_id()` is a 32-bit truncated unsalted SHA-256 and is brute-forceable back to the real identifier

| Field | Value |
|---|---|
| **ID** | PII-112 |
| **Title** | `mask_telegram_id()` is a 32-bit truncated unsalted SHA-256 and is brute-forceable back to the real identifier |
| **Severity** | MEDIUM |
| **Category** | Privacy / pseudonymisation strength |
| **File(s)** | `src/backend/apps/core/utils/sanitize.py:134-150`, `docs/01-spec/technical-specification.md:90` |
| **Status** | Open |
| **Problem** | `mask_telegram_id` returns `f"tg_{sha256(str(tid)).hexdigest()[:8]}"` — the first 8 hex characters of an unsalted SHA-256, i.e. a 32-bit truncated digest. The spec describes this as a "SHA-256 hash, **non-reversible**, `tg_` prefix" and states "Raw telegram_id must never appear in logs", so the whole log-hygiene guarantee of zone F rests on this function. A Telegram user ID is a small integer (public accounts are typically < 2^34, and the values are densely allocated), so the candidate space is trivially enumerable: a 32-bit digest can be inverted by brute force in well under a second on commodity hardware, and once a single `(id, tg_xxx)` pair is observed the whole log can be cross-referenced and reverse-looked-up. |
| **Impact** | The "masked" values in logs are pseudonyms, not anonymised data — they remain personal data under GDPR and are trivially re-identifiable. Anyone with read access to the logs (an operator, a log aggregator, a support bundle, an exfiltrated archive) can recover the exact Telegram IDs of every user the logs mention, which is precisely the leak the masking was introduced to prevent. The stability that makes the mask useful for correlation is exactly what makes it reversible. |
| **Root Cause** | A truncated hash was chosen for short, greppable log output; the truncation length (8 hex chars) was not reasoned about against the size of the input domain, and no keyed construction (HMAC with a secret) was used. |
| **Recommendation** | Use a keyed digest so the mapping is not computable from the logs alone: `hmac.new(settings.LOG_MASK_KEY, str(tid).encode(), sha256).hexdigest()[:12]`, with `LOG_MASK_KEY` sourced from the same secret source as `SECRET_KEY` and generated in `create_admin_user`/`.env.*.example`. 12 hex chars (48 bits) is still short enough to read in a log line and large enough to resist enumeration. Keep the `tg_` prefix so existing log greps and the PII-001/VAL-001 regression tests continue to work. Note that a key rotation invalidates old log correlation, which is an acceptable trade — document it. |
| **Effort** | S |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **CWE** | CWE-328 (Use of Weak Hash) |
| **Likelihood** | MEDIUM |

| Field | Value |
|---|---|
| **Related Findings** | PII-102, PII-106, PII-115 |

**Evidence — `src/backend/apps/core/utils/sanitize.py:134-150`** *(supports: "the mask is an 8-hex-char (32-bit) unsalted truncated SHA-256 with no secret input")*:
```python
def mask_telegram_id(telegram_id: int | None) -> str:
    """Mask a Telegram user ID for safe logging.

    Non-reversible SHA-256 hash (first 8 hex chars) with 'tg_' prefix.
    """
    if telegram_id is None:
        return "None"
    tid = str(telegram_id)
    return f"tg_{hashlib.sha256(tid.encode()).hexdigest()[:8]}"   # <- 32 bits, no key
```

**Evidence — `docs/01-spec/technical-specification.md:90`** *(supports: "the spec asserts non-reversibility, which the construction does not provide")*:
```markdown
- **PII logging:** All `telegram_id` values in logger calls and `stdout.write` output are masked via
  `mask_telegram_id()` (SHA-256 hash, non-reversible, `tg_` prefix) from `apps/core/utils/sanitize.py`.
  Raw telegram_id must never appear in logs.
```

---

#### PII-113: [MEDIUM] — Unresolved doc conflict on DECLINE semantics across `spec-index.md`, `technical-specification.md` and this phase's own rubric

| Field | Value |
|---|---|
| **ID** | PII-113 |
| **Title** | Unresolved doc conflict on DECLINE semantics across `spec-index.md`, `technical-specification.md` and this phase's own rubric |
| **Severity** | MEDIUM |
| **Category** | Documentation |
| **File(s)** | `docs/01-spec/spec-index.md:74`, `docs/01-spec/technical-specification.md:85,96,101`, `.kilo/commands/audit/phases/06-audit-pii-consent.md:39,49` |
| **Status** | Open |
| **Problem** | Three sources give two different answers for the same question, "what does DECLINE do to already-published ads?". (a) `spec-index.md:74` — decline "blocks seller login **only**". (b) `technical-specification.md:85`, `:96` and `:101` — DECLINE "**also hides the user's PUBLISHED ads from public search/listings**, direct URL access, and the `media_gate` non-staff filter", with the search cache version bumped. (c) This phase's own §4.1 verification step asserts "**existing ads remain public/searchable**". The code implements (b): the `user__is_declined=False` filter is live in `ListingsQuery.build_queryset`, `ad_detail` and `media_gate`, and `decline_consent()` bumps the search cache version on commit. |
| **Impact** | The DECLINE contract is the single most consequential consent decision in the product (it determines whether a seller's live listings are taken down), and it is stated two different ways in the two documents that are supposed to be the source of truth. Any reviewer, support agent, or future implementer who reads `spec-index.md` will believe existing ads stay up; anyone who reads `technical-specification.md` will believe they come down. The disagreement also masks the real defect in PII-105, because "browse-only" reads as harmless while "silently unpublishes live listings, permanently" does not. |
| **Root Cause** | `spec-index.md` is a condensed index that was not updated when the DECLINE-hides-ads decision was made and documented in detail in `technical-specification.md`; the phase rubric was written from the pre-decision mental model. |
| **Recommendation** | Adjudicate in favour of the code + `technical-specification.md` and fix the docs, in this order: (1) rewrite `spec-index.md:74` to "blocks seller login/actions **and hides the user's PUBLISHED ads from public listings, search and direct URL**"; (2) correct `.kilo/commands/audit/phases/06-audit-pii-consent.md:39,49` so the rubric's runtime-verification step asserts the actual intended behaviour; (3) leave `technical-specification.md:85/96/101` unchanged — it is the most precise of the three. Additionally, resolve the PII-105 design question in the same edit so `spec-index.md` states whether DECLINE is reversible. |
| **Effort** | S |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **CWE** | CWE-1059 (Incomplete Documentation) |
| **Likelihood** | HIGH |

| Field | Value |
|---|---|
| **Related Findings** | PII-105, PII-104 |

**Evidence — the three conflicting statements** *(supports: "the same question is answered two ways in the source-of-truth docs, and a third way in the audit rubric")*:
```markdown
docs/01-spec/spec-index.md:74
  ... a decline "blocks seller login only" ...

docs/01-spec/technical-specification.md:85
  - **Two distinct consent states (zone R3, decision K):** DECLINE (browse-only, no erasure;
    also hides the user's PUBLISHED ads from public search/listings and invalidates the search cache)
    != WITHDRAW ...

docs/01-spec/technical-specification.md:101
  - **DECLINE = browse-only:** blocks seller login/actions AND hides the user's PUBLISHED ads from
    public search/listings, direct URL access (`ad_detail`), and the `media_gate` non-staff filter

.kilo/commands/audit/phases/06-audit-pii-consent.md:39
  ... existing ads remain public/searchable ...
```

**Evidence — runtime, `.ai/tmp/audit06_probe.py` R-01** *(supports: "the running code implements the `technical-specification.md` reading, not the `spec-index.md` one")*:
```text
  ad_pub visible in public ListingsQuery after DECLINE = False
```

---

### LOW

#### PII-114: [LOW] — `ModeratorActionLog.reason` is free text, never redacted, and survives erasure as an orphan row

| Field | Value |
|---|---|
| **ID** | PII-114 |
| **Title** | `ModeratorActionLog.reason` is free text, never redacted, and survives erasure as an orphan row |
| **Severity** | LOW |
| **Category** | Privacy / free-text storage |
| **File(s)** | `src/backend/apps/moderation/models.py:88-95`, `src/backend/apps/moderation/admin_actions.py`, `src/backend/apps/ads/models.py` (`rejected_reason`) |
| **Status** | Open |
| **Problem** | `ModeratorActionLog.reason` is an unbounded `TextField` described as "INTERNAL ONLY - never shown to seller", populated free-form by moderators (and by `bulk_reject`, which writes the literal "Bulk rejection via admin action"). Nothing passes it through `redact_search_query()` or any other redaction, and the row deliberately survives user erasure with `user_id = NULL`. The same applies to `Ad.rejected_reason`, which is also shown in `AdAdmin.list_display`. |
| **Impact** | Low in practice because the fields are staff-authored, but a moderator quoting a seller's message ("user said: call me on +382 69 000 123") persists that PII indefinitely, in a row that erasure can no longer associate with — and therefore can no longer clean up. Combined with PII-101 it is a second orphan-PII channel. |
| **Root Cause** | Free-text operator fields are treated as non-personal because the *operator* writes them, not because the *subject's* data cannot end up in them. |
| **Recommendation** | Run `reason` and `rejected_reason` through `redact_search_query()` (already available in `apps.core.utils.sanitize`) at write time in `moderation_log.py` and `admin_actions.bulk_reject`, and add a note in the moderation UI help text that seller details must not be pasted in. Optionally cap the field length. |
| **Effort** | S |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **CWE** | CWE-532 |
| **Likelihood** | LOW |

| Field | Value |
|---|---|
| **Related Findings** | PII-101, PII-110 |

**Evidence — runtime, `.ai/tmp/audit06_probe2.py` R-07** *(supports: "the moderation row survives the sweep with its free-text reason intact and both references NULLed")*:
```text
  ModeratorActionLog row exists    : True | user_id = None | ad_id = None | reason = 'r'
```

---

#### PII-115: [LOW] — `create_admin_user` writes the raw public `username` to stdout while masking `telegram_id` in the same command

| Field | Value |
|---|---|
| **ID** | PII-115 |
| **Title** | `create_admin_user` writes the raw public `username` to stdout while masking `telegram_id` in the same command |
| **Severity** | LOW |
| **Category** | Privacy / log hygiene |
| **File(s)** | `src/backend/apps/core/management/commands/create_admin_user.py:87,95,119,124` |
| **Status** | Open |
| **Problem** | The command masks `telegram_id` on all four of its output paths (lines 79, 95, 119, 124) but writes `username` — the seller's public Telegram handle, i.e. the second PII field the spec names — in cleartext on lines 87, 95, 119 and 124 (`f"  username: {username}\n"`, `f"User with username='{username}' already exists, skipping"`). The masking is applied per-value rather than through a shared helper, so the coverage is inconsistent inside a single command. |
| **Impact** | Low: the command runs once at bootstrap from an operator terminal, and the admin's own handle is not the highest-value identifier. But the stdout is captured into container logs by the Compose `create_admin` service, so the inconsistency is visible in shipped logs and sets a precedent that the next command will copy. |
| **Root Cause** | Value-by-value masking calls rather than a formatter/filter that normalises any identity-typed argument (see PII-102's recommendation). |
| **Recommendation** | Apply the same treatment to `username` as to `telegram_id` on all output paths, or — better, and consistent with PII-102 — add the logging filter that rejects unmasked identity arguments so this class of inconsistency stops recurring. |
| **Effort** | S |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **CWE** | CWE-532 |
| **Likelihood** | LOW |

| Field | Value |
|---|---|
| **Related Findings** | PII-102, PII-112 |

**Evidence — `src/backend/apps/core/management/commands/create_admin_user.py:86-89`** *(supports: "`telegram_id` is masked one branch above, but `username` is written raw")*:
```python
                self.stdout.write(
                    self.style.WARNING(
                        f"User with username='{username}' already exists, skipping"   # <- raw handle
                    )
                )
```

---

#### PII-116: [LOW] — `ConsentRecord` has no retention policy and exposes a live `session_key` in the staff changelist

| Field | Value |
|---|---|
| **ID** | PII-116 |
| **Title** | `ConsentRecord` has no retention policy and exposes a live `session_key` in the staff changelist |
| **Severity** | LOW |
| **Category** | Privacy / retention policy |
| **File(s)** | `src/backend/apps/users/models.py:272-277`, `src/backend/apps/users/admin.py:68-102`, `src/backend/apps/core/management/commands/` (no consent-record sweep exists) |
| **Status** | Open |
| **Problem** | `ConsentRecord` is append-only by design ("never updated", a deliberate Art. 7(1) property), but nothing ever bounds it. The table grows without limit, and every row carries `session_key` (a live Django session identifier), the full `user_agent`, and an `ip_address` that is only last-octet-zeroed for IPv4 and /64-prefixed for IPv6. `ConsentRecordAdmin` puts `session_key` in `list_display` and in `search_fields`, so any staff user can enumerate and look up active session identifiers. `has_delete_permission` is correctly restricted to superusers, but there is no purge command in the `HOURLY_COMMANDS` list. |
| **Impact** | Two small but real issues. (a) Unbounded retention of browser-fingerprint-grade data (`user_agent` + partial IP + session key) with no stated period, which is a data-minimisation question the privacy policy does not address. (b) A `session_key` in a staff-visible, searchable changelist is a session-identifier exposure — anyone who obtains it plus the session cookie value can hijack that session, and the record outlives the session by an unbounded margin. |
| **Root Cause** | The model was designed purely as an append-only proof-of-consent ledger with no complementary retention design, and the admin was given `session_key` in `list_display` for debugging convenience. |
| **Recommendation** | Add a `consent_records` retention sweep to `HOURLY_COMMANDS` (e.g. `purge_consent_records`) with an explicit, documented TTL agreed with the business (a 12-month TTL aligns with the existing `CONSENT_REPROMPT_DAYS` re-prompt window). In the sweep, delete rows past the TTL and, for rows whose `user` is still set, null `session_key` once the session has expired. Meanwhile remove `session_key` from `ConsentRecordAdmin.list_display` (keep it in `search_fields` for support lookups) and document the retention period in `privacy.html` §6. |
| **Effort** | S |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **CWE** | CWE-459 |
| **Likelihood** | LOW |

| Field | Value |
|---|---|
| **Related Findings** | PII-110, PII-107 |

**Evidence — `src/backend/apps/users/models.py:272-277` + `src/backend/apps/users/admin.py:74-83`** *(supports: "no retention boundary on the model, and `session_key` is listed and searchable in the staff admin")*:
```python
    class Meta:
        db_table = "consent_records"
        ordering = ["-consent_given_at"]      # <- no retention marker, no purge index
```
```python
    list_display = ["id", "consent_given_at", "user", "session_key", "choice", "consent_version"]
    search_fields = ["session_key"]
```

**Evidence — `src/backend/apps/core/utils/scheduler.py` `HOURLY_COMMANDS`** *(supports: "no consent-record purge is scheduled alongside the other eight sweeps")*:
```python
HOURLY_COMMANDS: list[str] = [
    "archive_sweep", "delete_sweep", "consent_hard_delete", "sweep_drafts",
    "sweep_orphaned_media", "cleanup_login_tokens", "purge_failed_ads",
    "purge_rejected_ads", "purge_deleted_ads",
]
```

---

## Cross-Finding Analysis

- **Merge candidates:**
  - **PII-101 + PII-110 + PII-111 + PII-114** all share one root cause: *the erasure contract is a hand-maintained list of column names on `users`*, so every table that denormalises identity (`support_tickets`, `seller_verifications`, `moderation_action_logs.reason`, `ads.*text`) or identity-adjacent data (`chat_id`, `preferred_city`, `ConsentRecord`) falls out of scope. A validator may reasonably merge these four into a single "PII inventory is not modelled" finding. They are kept separate here because the fixes, owners and severities differ (immediate column scrub vs. new sweep vs. column removal vs. write-time redaction).
  - **PII-102 + PII-112 + PII-115** share one root cause: *masking is applied per-value per-call-site instead of through a shared formatter/filter*, so coverage is inconsistent and the mask itself is weak. A single logging-hardening change (keyed HMAC mask + a `Filter` that rejects unmasked identity arguments) closes all three.
- **Conflicting evidence:**
  - **PII-105 vs. PII-113.** The phase rubric (§4.1/§5a) states DECLINE "keeps all data + contact" and existing ads "remain public/searchable", which would make the hiding behaviour a defect on its own. `technical-specification.md:85/96/101` and the running code both say the opposite. This audit adjudicates in favour of the code + the technical spec (see PII-113) and therefore files the *reversibility* gap (PII-105) rather than a "DECLINE unpublishes ads" defect. A validator that reads the rubric literally may reclassify.
  - **PII-108.** `technical-specification.md:161` takes a legitimate-interest line for Plausible ("no consent banner needed"), which is consistent with not gating first-party `AnalyticsEvent`. The same document's §D3/§F records a per-category `analytics` consent flag, which implies the opposite. Filed as a decision-required MEDIUM, not as a hard violation.
- **Dependency chains:**
  - **PII-105 must be decided (PII-113) before it is fixed** — the fix (allow `is_declined` to log in vs. stop hiding ads) depends on which document is authoritative.
  - **PII-104 depends on PII-110's `chat_id` decision.** If `chat_id` is eventually nullified on withdrawal, PII-104 partly resolves itself; if it is kept (recommended, for the bot gate), the audience filter in PII-104 becomes mandatory. Do not "fix" PII-104 by nulling `chat_id` — that would break `AccountStateMiddleware._get_user`, which resolves users by `chat_id` precisely so withdrawn identities stay blocked.
  - **PII-103 should land before or with PII-107.** Making `is_declined`/`is_deleted` non-editable in the admin (PII-103) is what guarantees every consent-state transition goes through the service that writes the audit row (PII-107).
  - **PII-101 + PII-110 + PII-111 want one shared "PII inventory" declaration**; establishing it first makes each individual fix a one-line change rather than a fresh audit of every table.

## Remediation Roadmap

| Order | ID | Severity | Effort | Priority | Recommendation (summary) |
|-------|----|----------|--------|----------|--------------------------|
| 1 | PII-101 | CRITICAL | S | P0 | Null `SupportTicket.telegram_id`/`chat_id`/`username` in `withdraw_consent()` and in `consent_hard_delete`; add a data migration for existing rows |
| 2 | PII-102 | CRITICAL | S | P0 | Mask `payload["chat_id"]` at both `immediate_alerts` WARNING sites |
| 3 | PII-104 | HIGH | S | P0 | Filter the alert audience by account state in `send_alerts` + `find_matching_saved_searches`; deactivate saved searches on withdrawal |
| 4 | PII-103 | HIGH | S | P0 | Declare explicit `fieldsets` on `UserAdmin`; make `telegram_id`/`chat_id`/`username`/consent flags read-only or non-editable |
| 5 | PII-105 | HIGH | M | P0 | Decide DECLINE reversibility (PII-113) and give a declined seller a first-class re-accept path |
| 6 | PII-107 | MEDIUM | S | P1 | Move the `ConsentRecord` write into `withdraw_consent()` so the admin path is auditable |
| 7 | PII-108 | MEDIUM | M | P1 | Decide whether first-party analytics is consent-gated; then enforce it in the three write sites or rename the flag |
| 8 | PII-109 | MEDIUM | S | P1 | Scrub withdrawn ads' `title*`/`description*` (or correct the spec's "anonymized" wording) |
| 9 | PII-111 | MEDIUM | S | P1 | Remove `SellerVerification.phone_number`, or null it on withdrawal and disclose it in `privacy.html` §2 |
| 10 | PII-110 | MEDIUM | M | P1 | Declare a per-table retention/erasure policy; clear `preferred_city`; align `privacy.html` §6 with the code |
| 11 | PII-106 | MEDIUM | S | P1 | Mask raw `chat_id`/`telegram_id` in `SupportTicketAdmin.list_display`; drop `text` from `search_fields`; generalise `test_admin_pii_containment.py` |
| 12 | PII-112 | MEDIUM | S | P1 | Switch `mask_telegram_id` to a keyed HMAC-SHA256 with a 12-hex-char prefix |
| 13 | PII-113 | MEDIUM | S | P1 | Fix `spec-index.md:74` and the phase rubric to match `technical-specification.md`; record the DECLINE decision |
| 14 | PII-114 | LOW | S | P2 | Redact `ModeratorActionLog.reason` / `Ad.rejected_reason` at write time |
| 15 | PII-116 | LOW | S | P2 | Add a `purge_consent_records` retention sweep; drop `session_key` from `list_display` |
| 16 | PII-115 | LOW | S | P2 | Mask `username` on the `create_admin_user` output paths |

## Rollout Safety

| ID | Risk | Backward-compatible? | Test gap (must cover) |
|----|------|----------------------|-----------------------|
| PII-101 | Med — historical ticket rows lose their identifiers; support agents lose a lookup key | Yes (data only; no code API change) | No test asserts ticket identity is scrubbed on withdrawal or on the sweep |
| PII-102 | Low — log format changes; any log parser keyed on the raw `chat_id` breaks | Yes | `immediate_alerts` failure branches have no log-assertion test at all |
| PII-103 | **High** — removing `is_declined`/`is_deleted`/`ads_auto_publish` from the admin form breaks any operator workflow that used them; `chat_id` is `required=True` today so a `readonly_fields` change alone still forces it into the form | Yes (schema untouched) | No test asserts the admin form's field set; `test_admin_pii_containment.py` only covers `list_display` helpers |
| PII-104 | Med — withdrawn/declined users stop receiving alerts; some may perceive it as a service regression | Yes | No test covers a declined/withdrawn/banned `SavedSearch` owner in `send_alerts` or `find_matching_saved_searches` |
| PII-105 | **High** — if `is_declined` is removed from `can_login()`, a declined seller regains web login; that is a behaviour change that needs its own security review (and a decision on whether they can then reach `/dashboard/`) | No — deliberately changes the auth predicate | `test_account_state.py:160-168` asserts `can_login(is_declined=True) is False` and will break |
| PII-106 | Low — staff changelist columns change | Yes | `test_admin_pii_containment.py` does not cover `SupportTicketAdmin` |
| PII-107 | Low — adds a row to `consent_records` on the admin path; the `ConsentRecord` count assertions in `test_consent.py` use a `before + 1` delta and are scoped to the view, so they are unaffected | Yes | No test covers the admin action's audit row |
| PII-108 | Med — suppressing `SearchHistory`/`AnalyticsEvent` writes changes seller-dashboard numbers and `rollup_daily_metrics` output | Yes | No test asserts analytics writes for a DECLINED user |
| PII-109 | Med — scrubbing `title*`/`description*` breaks `test_deletion.py` ad-content assertions and makes the ad unsearchable in `AdAdmin` | No | Existing deletion tests assert ad *status* only; a new test must assert content scrubbing |
| PII-110 | Med — clearing `preferred_city` changes dashboard default-city behaviour; the `preferred_city` cookie is already deleted on decline | Yes | `test_preferred_city*.py` cover the cookie, not the DB column on withdrawal |
| PII-111 | Med — removing the column requires a migration plus a data migration, and any operator verification workflow keyed on it must be retired | No | No test asserts `phone_number` nulling |
| PII-112 | Med — a keyed mask changes every historical `tg_` value's derivability but also breaks any test that asserts a *specific* mask output; `test_login.py:593` only asserts the raw value is absent, so it survives | Yes | `test_sanitize.py` pins behaviour of the current function and will need updating |
| PII-113 | Low — docs only | Yes | n/a |
| PII-114 | Low — moderation reason text becomes masked; staff lose verbatim quotes | Yes | No test asserts reason redaction |
| PII-115 | Low | Yes | `create_admin_user` has no output-assertion test |
| PII-116 | Low — adds a destructive sweep; must be ordered so it cannot delete rows still needed for an Art. 7(1) demonstration | Yes | New sweep needs a `--dry-run` and a TTL test |

## Appendices

### Appendix A — `R-01` / `R-02` DECLINE and WITHDRAW state snapshots

*(supports PII-105, PII-107, PII-109, PII-111, PII-113)*

```text
==============================================================================
R-01  DECLINE path — assert no revocation, no PII nulling, ads untouched
==============================================================================
before decline  id=1 is_declined=False is_deleted=False ads_auto_publish=True
                consent_given_at=set consent_revoked_at=NULL telegram_id=700000001
                username='probe_seller' chat_id=700000001 first_name='Probe' last_name='Seller'
  ad_pub.status      = published | ad_draft.status = draft
  can_login(before)  = True
after  decline  id=1 is_declined=True is_deleted=False ads_auto_publish=False
                consent_given_at=NULL consent_revoked_at=NULL telegram_id=700000001
                username='probe_seller' chat_id=700000001 first_name='Probe' last_name='Seller'
  ad_pub visible in public ListingsQuery after DECLINE = False
  can_login(after)   = False
  contact still allowed (can_contact_seller)          = True
  SellerVerification.phone_number still present       = +38269000001

==============================================================================
R-02  WITHDRAW path — revocation ts, soft-delete, PII nulling
==============================================================================
after  withdraw  id=2 is_declined=False is_deleted=True ads_auto_publish=True
                consent_given_at=NULL consent_revoked_at=set telegram_id=None
                username=None chat_id=700000002 first_name='' last_name=''
  draft storage keys returned: []
  ConsentRecord rows        : 0
```

Reading: DECLINE does **not** null PII and does **not** set `consent_revoked_at` (correct),
but it does remove the ad from public listings and does flip `can_login` to `False`
(PII-105, PII-113). WITHDRAW nulls every identity column **except `chat_id`**
(PII-110) and writes no `ConsentRecord` when called from the service (PII-107).

### Appendix B — `R-03` contact deep-link gating matrix (16/16 correct)

*(supports: the contact-gating dimension of this phase is clean)*

```text
  banned=False deleted=False revoked=False null_tid=False -> web=True  bot=True
  banned=False deleted=False revoked=False null_tid=True  -> web=False bot=False
  banned=False deleted=False revoked=True  null_tid=False -> web=False bot=False
  banned=False deleted=False revoked=True  null_tid=True  -> web=False bot=False
  banned=False deleted=True  revoked=False null_tid=False -> web=False bot=False
  banned=False deleted=True  revoked=False null_tid=True  -> web=False bot=False
  banned=False deleted=True  revoked=True  null_tid=False -> web=False bot=False
  banned=False deleted=True  revoked=True  null_tid=True  -> web=False bot=False
  banned=True  deleted=False revoked=False null_tid=False -> web=False bot=False
  banned=True  deleted=False revoked=False null_tid=True  -> web=False bot=False
  banned=True  deleted=False revoked=True  null_tid=False -> web=False bot=False
  banned=True  deleted=False revoked=True  null_tid=True  -> web=False bot=False
  banned=True  deleted=True  revoked=False null_tid=False -> web=False bot=False
  banned=True  deleted=True  revoked=False null_tid=True  -> web=False bot=False
  banned=True  deleted=True  revoked=True  null_tid=False -> web=False bot=False
  banned=True  deleted=True  revoked=True  null_tid=True  -> web=False bot=False
```

`web` = `can_contact_seller(ad)` (the `|can_contact` template filter used by
`ads/detail.html:168`); `bot` = `get_seller_for_contact(ad_id)[0]`, the predicate
`telegram_bot/handlers/contact.py` uses before it will message a seller. Both go
through the single `_check_seller_contactable()` chain in
`apps/core/services/contact.py:27-45`, so they cannot drift. The bot additionally
short-circuits a `TelegramForbiddenError`/`TelegramBadRequest` on send rather than
leaking the seller's identity into the buyer's chat.

### Appendix C — `R-09` registered `ModelAdmin` surface inventory

*(supports PII-103, PII-106)*

```text
ModelAdmin: users.User  ->  UserAdmin
  form fields (auto-built ModelForm):   22 editable fields (see PII-103 evidence)
  list_display      : ['is_banned', 'is_deleted', 'ads_auto_publish',
                       'consent_given_at', 'consent_revoked_at']
  search_fields     : ['telegram_id']
  readonly_fields   : ['consent_given_at', 'consent_revoked_at', 'deleted_at']
  declared fields/fieldsets/form : None None <class 'django.forms.models.ModelForm'>
  has_change_perm(staff) : True
  has_delete_perm(staff) : False
  actions               : ()

ModelAdmin: users.ConsentRecord  ->  ConsentRecordAdmin
  form fields (auto-built ModelForm):   (none — all readonly)
  list_display      : ['id', 'consent_given_at', 'user', 'session_key', 'choice', 'consent_version']
  search_fields     : ['session_key']
  has_change_perm(staff) : False
  has_delete_perm(staff) : False

ModelAdmin: users.LoginToken  ->  LoginTokenAdmin
  form fields (auto-built ModelForm):   (none — all readonly)
  list_display      : ['id', 'telegram_id_display', 'created_at', 'expires_at', 'consumed_at']
  has_change_perm(staff) : False
  has_delete_perm(staff) : False

ModelAdmin: core.SupportTicket  ->  SupportTicketAdmin
  form fields (auto-built ModelForm):
    - status                 TypedChoiceField   required=True readonly=False
  list_display      : ['ticket_ref', 'status', 'user', 'chat_id', 'telegram_id', 'created_at']
  search_fields     : ['ticket_ref', 'telegram_id', 'username', 'text']
  has_change_perm(staff) : True
  has_delete_perm(staff) : False
```

Note: `UserAdmin.actions` introspects as `()` and `UserAdmin.get_actions(request)`
returns only `['delete_selected']`, so `withdraw_consent_action` — although decorated
with `@admin.action` — is **not registered** and is unreachable from the admin
changelist UI. It is therefore live-but-dead code, not an active operator surface.
Per the dead-code policy this is raised inside PII-107 as a decision to make
(wire it now that it is auditable, or remove it), not as a delete recommendation.
It does not change any other finding in this report.

```python
# .ai/tmp/audit06_actions.py — verified against the registered ModelAdmin
ma = admin.site._registry[get_user_model()]
print("UserAdmin.actions attr ->", ma.actions)          # ()  — never assigned
print("UserAdmin.get_actions  ->", sorted(ma.get_actions(R())))
# -> ('delete_selected',)   # withdraw_consent_action is ABSENT
```

### Appendix D — probe methodology and cleanup

*(supports: every runtime claim is reproducible and the environment was left clean)*

- Probes ran as `docker compose --project-name mko-bazuna-test --env-file .env.test
  -f docker-compose.yml -f docker-compose.test.yml run --rm --no-deps --entrypoint ""
  -e DJANGO_SETTINGS_MODULE=config.settings.test test python /app/.ai/tmp/<probe>.py`.
- `config/settings/test.py` hardcodes `DATABASES["default"]["NAME"] = "mko_bazuna"`, so
  every probe overrode `settings.DATABASES["default"]["NAME"]` and
  `connections["default"].settings_dict["NAME"]` to the throwaway database **before**
  any ORM call, and built the schema with `connection.creation.create_test_db()`
  (test settings set `MIGRATION_MODULES = DisableMigrations()`, so `migrate` is a
  no-op). This avoids the phantom `mko_bazuna` DB.
- One early probe run before that guard was in place wrote rows into the phantom
  `mko_bazuna` database. All 19 probe users and 3 probe ads were removed afterwards in
  a single ordered transaction, leaving the database at 9 pre-existing users / 2 ads /
  39 tables / `to_regclass('django_migrations') IS NULL` — i.e. byte-identical table
  inventory to the state documented for this environment. No schema change was made.
- All identity values used in the probes are synthetic (`7000xxxxx`, `7100xxxxx`,
  `7200xxxxx`, `7300xxxxx`, `7600xxxxx`, `7700xxxxx`, `7800xxxxx`, `8800xxxxx`).
  No real Telegram identifier was read, and no real secret was read or quoted.
- The scratch database `audit06_probe` and the probe scripts under `.ai/tmp/` were
  dropped/removed at the end of the phase.
- Test gate: `PYTEST_SKIP_MARKERS=seed` over
  `src/backend/apps/users/tests` + `src/telegram_bot/tests/test_account_state_middleware.py`
  → **190 passed**, 61 s. `uv run ruff check` on the users app + `contact.py` +
  `permissions.py` → clean. `uv run basedpyright` on the users app + `contact.py` →
  **0 errors, 0 warnings, 0 notes**.
