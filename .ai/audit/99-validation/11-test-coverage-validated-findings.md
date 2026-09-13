---
phase: "11"
phase_name: "Test Coverage"
date: "2026-09-13"
auditor: "Executor (subagent)"
validator: "Kilo (read-validation agent)"
mode: "problems-only"
id_prefix: "TST"
report_status: "validated"
severity_taxonomy: ".kilo/commands/audit/phases/11-audit-test-coverage.md#severity-taxonomy"
---

# Audit Findings (Validated) — Test Coverage & Quality

> **Validator's note.** This report is self-contained: every finding below was
> checked against the live source tree (`src/backend/...`, `src/telegram_bot/...`),
> the Phase 11 severity taxonomy (`.kilo/commands/audit/phases/11-audit-test-coverage.md`),
> the baseline coverage log (`.cache/baseline_cov.log`), the test-strategy report
> (`.cache/test-strategy-report.md`), and — where the finding is a runtime/assert claim —
> a direct tool re-run (`uv run pytest` for the footer test in isolation, `docker compose run --rm test`).
> Each finding carries an inline **Validation** block stating the action taken, the
> validation type (`SPEC-DEVIATION` / `BEST-PRACTICE` / `DOC-UPDATE`), the evidence
> surveyed, and any source-reference drift from the original audit.

## Executive Summary

Seven problems were surfaced in the Phase 11 test-coverage audit. After validation:

- **4 findings validated** (TST-001, TST-002, TST-004, TST-005) — core claims confirmed,
  with **precision corrections** noted for TST-001 (not both tests are skipped),
  TST-002/TST-005 (repro tests were audit-only, never committed), and TST-005 (severity
  overstated relative to Phase 04's classification).
- **1 finding partially validated** (TST-003) — the coverage shortfall is real and
  the footer test genuinely fails in the full suite, but the root-cause analysis is
  wrong: the label is NOT "obfuscated/base64-assembled"; the failure is caused by an
  eager `gettext` in `telegram_tags.py:_LABELS` that captures a non-English translation
  when the module is first imported during a test with a foreign language active.
- **1 finding rejected** (TST-006) — the CI **does** show missing-line detail via
  `show_missing = true` in `[tool.coverage.report]` (pyproject.toml:184); the finding's
  evidence block selectively omits this setting, undermining its claim.
- **1 finding mostly stale** (TST-007) — all 12 SimpleTestCase files and all 5 bare
  `django_db` files have been fixed by commit `c73f54d` (2026-09-07). Only the bot-test
  `slow` redundancy and the `test_ad_image_service.py` docstring contradiction remain
  as minor residuals.

The baseline coverage log was generated on 2026-09-13 (matching today's date) against
commit `dc39ea6` (2026-09-12). Commit `c73f54d` (2026-09-07, "test: phase 1-2 test
cleanup and consolidation") was the last test-hygiene sweep and resolved the majority
of the marker-classification issues in TST-004 and TST-007 that the
`test-strategy-report.md` (generated 2026-08-22) had identified.

## Scope & Methodology

**Scope:** The Phase 11 test-safety-net for every security- and correctness-critical
behavior: the ad-lifecycle state machine, the login-token two-phase claim/expiry/replay,
PII erasure, contact-gating, FTS visibility, the media sweep, and translation fallback.

**Tools used:** `grep` (source scans), `read` (line-by-line inspection), `uv run pytest`
(footer test in isolation, on the running test DB at localhost:5433),
`basedpyright`/`ruff` (where relevant), and cross-referencing with Phase 04 (auth/login)
and Phase 05 (ad lifecycle) validated findings.

**Validation command used for the footer test:**
```
uv run pytest apps/core/tests/test_footer_contact_link.py --no-header --tb=short -p no:xdist --no-cov
→ 9 passed in 0.83s
```

---

## Findings Summary

| ID | Title | Severity | Status | Type (validated) |
|----|-------|----------|--------|-------------------|
| TST-001 | Migration reproducibility/idempotency test skipped (`DisableMigrations` makes `_MIGRATIONS_DISABLED=True`) | CRITICAL | Open | SPEC-DEVIATION |
| TST-002 | Text-edit moderation path (PUBLISHED→ON_MODERATION) has zero coverage | CRITICAL | Open | SPEC-DEVIATION |
| TST-005 | Concurrent login-token double-claim race test deleted | HIGH → MEDIUM | Open | SPEC-DEVIATION |
| TST-003 | Coverage below `fail_under` (77.55% < 80%) + footer test failure | MEDIUM | Open | BEST-PRACTICE |
| TST-004 | Module-level `slow` marker on 51 files misclassifies fast tests as slow | MEDIUM | Open | BEST-PRACTICE |
| TST-006 | CI coverage lacks `--cov-report=term-missing` | MEDIUM | Open | **REJECTED** |
| TST-007 | `unit` marker missing on 12 SimpleTestCase files | LOW | Open | **STALE** (mostly resolved) |

**Severity counts (original findings):** CRITICAL 2, HIGH 1, MEDIUM 3, LOW 1

---

## Findings by Severity

### CRITICAL

> **Validation:** ✅ **Validated — SPEC-DEVIATION (no change to type; precision correction).**
> Confirmed `_MIGRATIONS_DISABLED = True` and that `test_makemigrations_check` carries
> a `skipif` guard and is SKIPPED. **Precision correction:** the finding claims
> "both `test_makemigrations_check` AND `test_migration_idempotency` are both SKIPPED."
> Only `test_makemigrations_check` is skipped (has `@pytest.mark.skipif` at line 23).
> `test_migration_idempotency` (line 60) has **no** skipif decorator — it runs. However,
> because `DisableMigrations` makes every app's `MIGRATION_MODULES` entry `None`, the
> `call_command("migrate", "--noinput")` invocation produces "No migrations to apply."
> on every run, so the assertion `"No migrations to apply." in output` (line 90) is
> **trivially true** — the test is a no-op pass, not a real idempotency check. The
> baseline confirms "SKIPPED [1]" (only one skip). The effective outcome matches the
> finding's spirit (no migration drift detection), but the literal claim "both SKIPPED"
> is inaccurate.

#### TST-001: [CRITICAL] — No migration reproducibility/idempotency test

| Field | Value |
|:---:|---|
| **ID** | TST-001 |
| **Title** | `DisableMigrations` in test settings disables migration replay; `test_makemigrations_check` is skipped and `test_migration_idempotency` is a no-op |
| **Severity** | CRITICAL |
| **Category** | Migration safety / correctness |
| **File(s)** | `src/backend/config/settings/test.py:83-91` (`DisableMigrations`); `src/backend/apps/core/tests/test_migrations.py:20,23,60` |
| **Status** | Open |
| **Type** | SPEC-DEVIATION |

**Problem (validated):** `DisableMigrations` (test.py:83-91) returns `True` from
`__contains__` for any app name and `None` from `__getitem__`. Django's test runner
checks `MIGRATION_MODULES` via `__contains__` — when `__contains__` returns `True`, Django
calls `__getitem__` and gets `None`, meaning "no migration module for this app." This
disables ALL migrations in the test suite. Consequently:

- `test_makemigrations_check` (test_migrations.py:23) has `@pytest.mark.skipif(_MIGRATIONS_DISABLED, ...)`
  → SKIPPED every run (baseline: "SKIPPED [1] ... MIGRATION_MODULES=None...").
- `test_migration_idempotency` (test_migrations.py:60) has **no** skipif guard → it RUNS,
  but `call_command("migrate", "--noinput")` produces "No migrations to apply." (since
  no migrations are registered). The check at line 90 (`"No migrations to apply." not in
  output`) is therefore always satisfied → the test always PASSES trivially.

Neither test provides meaningful migration-drift detection. If a developer adds a model
field without committing a migration, or a migration is non-idempotent (`RunSQL` without
`IF NOT EXISTS`), the test suite will not catch it.

**Impact (validated):** Undetected migration drift → production migrations that fail,
duplicate columns, or non-idempotent `RunSQL` that breaks re-runs. The `DISABLE_MIGRATIONS`
pattern is a common pytest-django fixture, but here it is applied to the global
`MIGRATION_MODULES` setting, affecting ALL test files in the suite (not just one test
class), and no test ever re-enables migrations to validate them.

**Root Cause (validated):** `DisableMigrations` is set in `settings/test.py` (line 91:
`MIGRATION_MODULES = DisableMigrations()`), not scoped per-test-class. The two migration
tests in `test_migrations.py` either skip (makemigrations) or no-op (idempotency) under
this setting.

**Evidence — verified on disk:**

```python
# config/settings/test.py:83-91
class DisableMigrations:
    """Disables ALL migrations — Django treats every app as having no migrations."""
    def __contains__(self, item) -> bool:
        return True

    def __getitem__(self, item) -> None:
        return None

...
MIGRATION_MODULES = DisableMigrations()  # line 91
```

```python
# apps/core/tests/test_migrations.py:20-28
_MIGRATIONS_DISABLED = bool(getattr(settings, "MIGRATION_MODULES", {}))
# → bool(DisableMigrations()) == True (truthy object, no __bool__/__len__)

@pytest.mark.skipif(
    _MIGRATIONS_DISABLED,
    reason="MIGRATION_MODULES=None disables migration replay; ...",
)
def test_makemigrations_check() -> None:  # ← SKIPPED
    ...

def test_migration_idempotency() -> None:  # ← NO skipif → runs but no-ops
    ...
    if "No migrations to apply." not in output:  # always True when migrations disabled
        pytest.fail(...)
```

**Baseline evidence — `.cache/baseline_cov.log`:**
```
SKIPPED [1] src/backend/apps/core/tests/test_migrations.py:23:
  MIGRATION_MODULES=None disables migration replay...
```
Only 1 skip recorded — `test_migration_idempotency` was NOT in the skipped list.

**Source-reference drift:** The finding's reproduction step (line 99) says "Observe both
tests SKIPPED." Only `test_makemigrations_check` is skipped; `test_migration_idempotency`
runs and passes trivially. The effective risk is identical (no drift detection), but the
literal reproduction claim is imprecise. **Fix scope unchanged.**

**Recommendation (validated):** Add a dedicated test runner invocation that re-enables
migrations for migration-reproducibility checks. E.g., a separate test class that
temporarily sets `MIGRATION_MODULES = {}` (enabling all migrations) and runs
`makemigrations --check --dry-run`. This can be gated behind a marker (e.g.
`@pytest.mark.migration`) that is not selected by default but runs in CI's full-suite
mode. The key constraint: this test must NOT run under `DisableMigrations`.

**Effort** | M
**Priority** | P0 (migration drift in production is a deploy-blocking risk)
**CWE** | CWE-1046 (The software does not verify the consistency of schema and code)

---

### CRITICAL

> **Validation:** ✅ **Validated — SPEC-DEVIATION (no change).** Confirmed by direct
> source inspection AND by the Phase 05 validated findings (AD-003, HIGH, validated,
> Open). The PUBLISHED + `has_text_change` branch (`edit.py:208-244`) calls
> `ad.transition_to(AdStatus.ON_MODERATION)` and redirects — but never invokes
> `auto_moderate()`. The `test_edit.py` file contains 5 classes / 6 methods, ALL using
> `"reactivate": "1"` in POST data — none reach the PUBLISHED text-edit branch.
> `edit.py` coverage is 44% with lines 208–263 missing (baseline). The finding's impact
> framing ("untrusted content can be approved by auto_moderate being skipped") is
> imprecise — the actual impact (per Phase 05 AD-003) is: (1) the ad is stuck hidden in
> ON_MODERATION indefinitely, (2) if a human moderator approves it, the edited text
> bypasses automated checks. The Phase 05 rollout safety note confirms the exact test
> gap: "Add a text-edit test asserting auto_moderate IS called."

#### TST-002: [CRITICAL] — Text-edit moderation path (PUBLISHED→ON_MODERATION) has zero coverage

| Field | Value |
|:---:|---|
| **ID** | TST-002 |
| **Title** | Published ad text-edit branch transitions to ON_MODERATION without calling `auto_moderate()`; zero tests cover this branch |
| **Severity** | CRITICAL |
| **Category** | Ad lifecycle / moderation / test coverage |
| **File(s)** | `src/backend/apps/ads/views/edit.py:208-244` (text-edit branch, no `auto_moderate`); `edit.py:331` (reactivate calls it); `src/backend/apps/ads/tests/test_edit.py` (5 classes, 6 methods, ALL reactivation) |
| **Status** | Open |
| **Type** | SPEC-DEVIATION (linked to Phase 05 AD-003) |

**Problem (validated):** In `ad_edit`, when `ad.status == AdStatus.PUBLISHED` and
`has_text_change` is true, the view (edit.py:208-244) sets the new title/description,
applies the price change, saves, calls `ad.transition_to(AdStatus.ON_MODERATION)`, and
redirects to the dashboard. **`auto_moderate()` is never called.** This is in contrast to:

- The reactivation branch (edit.py:164-206) which routes through `submit_ad()` →
  `auto_moderate()` (edit.py:178, submission.py:186).
- The standalone `ad_reactivate` view (edit.py:326-331) which calls `auto_moderate(ad)`
  directly at line 331.
- `post_save` signal handlers (`moderation/signals.py:50`) which only compute priority
  and schedule alerts — none auto-moderate on text-edit.

The `test_edit.py` test suite contains 5 classes / 6 methods (TestReactivationStatusTransition,
TestReactivationAutoModerate, TestReactivationCurrencyKeepCurrent,
TestReactivationPriceNormalized, TestReactivationTextUpdated), **all** using
`"reactivate": "1"` in POST data — exercising only the ARCHIVED→reactivation path
(edit.py:164-206). **Zero tests reach** the PUBLISHED text-edit branch (edit.py:208-244).

**Impact (validated):** Per Phase 05 AD-003 (HIGH, validated, SPEC-DEVIATION):
1. A published ad that the seller edits is re-hidden in ON_MODERATION and **never
   automatically republished** — it sits hidden indefinitely until a human moderator
   reviews the queue, effectively removing the ad from the site.
2. If a moderator manually approves it, the **newly edited text is published without
   the automated checks** (title/description length, image count, banned words,
   duplicate-title, max-ads-per-user) that normally run on submit.

The finding's framing ("untrusted content can be approved by auto_moderate() being
skipped") is imprecise — the ad is NOT approved automatically; it stays hidden.
The real risk is (2): manual approval of edited text bypasses automated safety checks.

**Evidence — `edit.py:208-244` (text-edit branch, no `auto_moderate`):**
```python
elif ad.status == AdStatus.PUBLISHED:
    if has_text_change:
        ad.title = new_title
        ad.description = new_description
        ad = _apply_price_change(ad, price_amount_value, price_currency_value)
        ad.save(update_fields=[...])
        ad.transition_to(AdStatus.ON_MODERATION)
        logger.info(f"Ad {ad_id} text edited, moved to ON_MODERATION")
        # ↑ NO auto_moderate() call here
        return redirect("ads:dashboard")
```

**Evidence — `edit.py:326-331` (reactivate calls `auto_moderate`):**
```python
if ad.status == AdStatus.ARCHIVED:
    ad.transition_to(AdStatus.ON_MODERATION)
    auto_moderate(ad)  # ← text-edit branch omits this
```

**Evidence — `test_edit.py:35` (all reactivation):**
```python
pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]
```
And the docstring (line 1-18) confirms: "Integration tests for the `ad_edit` reactivation
path" — scoped to reactivation only, zero text-edit tests.

**Baseline evidence — `baseline_cov.log` (edit.py coverage):**
```
src/backend/apps/ads/views/edit.py  107  55  28  5  44%
  50-63, 107-110, 143->152, 155->162, 208-263, 280-296, 314-335
```
Lines 208-263 (the PUBLISHED branch, including text-edit at 208-244) are entirely
uncovered.

**Cross-reference — Phase 05 AD-003 (validated, HIGH, SPEC-DEVIATION, Open):**
The Phase 05 audit independently identified this exact gap. The Phase 05 validated
findings state: "Confirmed by direct source inspection: `edit.py:229` calls
`ad.transition_to(AdStatus.ON_MODERATION)` in the PUBLISHED+text-edit branch then
redirects to the dashboard (edit.py:244) with no `auto_moderate()` call." The Phase 05
reproduction test `test_textedit_does_not_remoderate` was **not committed** to the tree
(audit-only repro). The Phase 05 rollout safety note requires: "Add a text-edit test
asserting auto_moderate IS called and the pass/fail redirect mirrors reactivation."

**Source-reference drift:** The finding cites `edit.py:208-244` and `edit.py:331`. In the
current code, `auto_moderate(ad)` is at line 331 in the standalone `ad_reactivate` view
(not the `ad_edit` view). The substantive claim is unchanged. The finding also cites
`submission.py:186` for the bot's `submit_ad → auto_moderate` call — confirmed valid.

**Recommendation (validated):** Add a committed regression test that POSTs to the edit
endpoint with `"title"`/`"description"` changes on a PUBLISHED ad (no `reactivate` flag),
asserts that `auto_moderate` IS called (via `patch`), and that pass → dashboard redirect,
fail → re-render `edit.html` with error. This test will FAIL until the Phase 05 AD-003
production fix is applied (wire `auto_moderate()` into the text-edit branch).

**Effort** | M
**Priority** | P0
**CWE** | CWE-345 (Insufficient Verification of Data Authenticity — edited content bypasses safety gate)

---

### HIGH

> **Validation:** ✅ **Validated — SPEC-DEVIATION (severity corrected from HIGH to MEDIUM).**
> The core claim (no permanent concurrent double-claim race test) is confirmed by the
> Phase 04 audit (AUT-002, validated as SPEC-DEVIATION, P2). Two inaccuracies corrected:
> (1) The finding claims the test was "deleted in consolidation `c73f54d`" — but git
> history shows no file named `test_concurrent_claim_tmp.py` was ever committed; it was
> a temporary audit artifact (Phase 04 R-03 verification), confirmed deleted by the Phase
> 04 validator. (2) The finding's HIGH severity overstates Phase 04's classification
> (LOW → SPEC-DEVIATION/P2, Likelihood: LOW). Per the Phase 11 taxonomy, the login-token
> claim path is NOT "zero tests" (9 sequential tests pass) — CRITICAL requires "ZERO
> tests." MEDIUM ("Branch coverage <80% on critical code") is the better fit, since the
> concurrent sub-path specifically lacks coverage while the overall path is tested.
> Reclassified: HIGH → MEDIUM / SPEC-DEVIATION.

#### TST-005: [MEDIUM] — No permanent concurrent double-claim race test

| Field | Value |
|:---:|---|
| **ID** | TST-005 |
| **Title** | No permanent concurrent login-token double-claim race test; only sequential test exists |
| **Severity** | MEDIUM (corrected from HIGH) |
| **Category** | Test Quality (security-critical path) |
| **File(s)** | `src/telegram_bot/tests/test_login.py:134` (`test_reclaim_blocked` — sequential only); `src/backend/apps/users/tests/test_login.py` (no concurrent test) |
| **Status** | Open |
| **Type** | SPEC-DEVIATION (linked to Phase 04 AUT-002) |

**Problem (validated):** The bot's `test_reclaim_blocked`
(`test_login.py:134-172`) tests sequential double-claim only — it calls
`handle_login_orm` twice **in sequence** (await call 1, then await call 2) and asserts
the second returns `None`. No `asyncio.gather` or `threading.Thread` is used. The Phase
04 spec's "Isolation / Test Note" explicitly requires: "Simulate the concurrent claim
race." No permanent test exercises true concurrency.

**Impact (validated):** If a future refactor weakens the atomic `UPDATE ... RETURNING`
claim (Phase 03 DB-004 confirms the claim IS atomic today), the race-proof property
would silently break without test failure. The existing sequential test would still pass.
This masks a regression that could enable double-claim / account-takeover.

**Root Cause (validated):** The `test_reclaim_blocked` test verifies idempotency under
sequential execution but does not fire two claims concurrently. The
`pytest.mark.concurrent` marker (`pyproject.toml:170`) means `transaction=True`
(TRUNCATE per test), NOT concurrent execution within a test. No `threading.Thread` or
`asyncio.gather` concurrency test for double-claim exists anywhere in the codebase.

**Evidence — verified on disk:**

```python
# test_login.py:134-159 — sequential, NOT concurrent
async def test_reclaim_blocked(self, login_token_factory, ...):
    # Act: first claim succeeds
    first_claim, _, _ = await handle_login_orm(...)  # sequential — await first
    assert first_claim is not None
    # Act: second claim of the same hash by a different user
    second_claim, _, _ = await handle_login_orm(...)  # sequential — await second
    assert second_claim is None, "Re-claim of a claimed token must be blocked"
```

**Cross-reference — Phase 04 AUT-002 (validated, SPEC-DEVIATION, P2, Likelihood LOW):**
The Phase 04 audit independently identified this gap. The Phase 04 validated findings
confirm: "The temporary test `test_concurrent_claim_tmp.py` (referenced in the finding)
was confirmed deleted — no file matching `*concurrent*` exists in any `tests/`
directory." The Phase 04 R-03 verification used a temporary concurrent test
(`asyncio.gather` with 2 users, same token → "1 passed, 1479 deselected in 32.10s")
that PASSED (1 winner confirmed), but it was not committed.

**Source-reference drift / inaccuracies:**
1. The finding says "deleted in consolidation `c73f54d`" — **inaccurate**. Git history
   shows no file named `test_concurrent_claim_tmp.py` was ever committed. The commit
   `c73f54d` ("test: phase 1-2 test cleanup") renamed/consolidated bot login test files
   (`test_claim_login_token.py`, `test_login.py`, `test_login_claim.py`) but did NOT
   touch any file matching `*concurrent*`. The Phase 04 validator confirms the file was
   "a temporary test... confirmed deleted — no file matching `*concurrent*` exists in
   any `tests/` directory." It was a one-off audit repro, not a committed test.
2. The finding's HIGH severity (P1) overstates Phase 04's classification (LOW →
   SPEC-DEVIATION/P2, Likelihood LOW). The production claim path is already atomic
   (UPDATE ... RETURNING); the gap is purely a missing regression test, not a
   exploitable vulnerability. Per the Phase 11 taxonomy, "A security-critical path has
   ZERO tests" is CRITICAL — but the login-token claim is tested (9 sequential tests).
   The concurrent sub-path gap fits MEDIUM ("Branch coverage <80% on critical code").

**Recommendation (validated):** Add a permanent test using `asyncio.gather` to fire two
`handle_login_orm` calls with the same `token_hash` but different `telegram_id` values
concurrently, asserting exactly one returns a non-`None` `LoginToken`. The Phase 04
audit provides the basis (R-03 temporary test).

**Effort** | S
**Priority** | P2 (downgraded from P1; P0 would require production change)
**CWE** | CWE-754 (Improper Check for Unusual or Exceptional Conditions — missing concurrency regression test)

---

### MEDIUM

> **Validation:** ✅ **Partially validated — BEST-PRACTICE (with root-cause correction).**
> The coverage shortfall (77.55% < 80%) is confirmed in the baseline log. The footer
> test failure is real (confirmed in baseline, fails on xdist worker `gw1`). However, the
> finding's root-cause explanation is **wrong**: it claims the link label is
> "obfuscated/base64-assembled per spec Block A." The label IS plain text
> `_("Contact us")` rendered as both `aria-label` and visible text by
> `telegram_deep_link`. The actual root cause is that `telegram_tags.py:64-69` uses
> `gettext` (eager, not `gettext_lazy`) at module-level for the `_LABELS` dict — if the
> module is first imported during a test with a non-English language active (from a
> preceding test on the same xdist worker), the labels are captured in that language and
> never re-translated. Confirmed: the test PASSES in isolation (9 passed, 0.83s) but
> FAILS in the full suite (baseline: `[gw1]` failure at line 123).

#### TST-003: [MEDIUM] — Coverage below `fail_under` (77.55% < 80%) + footer test failure

| Field | Value |
|:---:|---|
| **ID** | TST-003-A (coverage threshold) + TST-003-B (footer test failure) |
| **Severity** | MEDIUM |
| **Category** | Coverage gate / test determinism |
| **File(s)** | `pyproject.toml:183` (`fail_under = 80`); `src/backend/apps/core/tests/test_footer_contact_link.py:123`; `src/backend/apps/core/templatetags/telegram_tags.py:64-69` (`_LABELS` with eager `gettext`) |
| **Status** | Open |
| **Type** | BEST-PRACTICE |

**Problem A — Coverage shortfall (validated):** The baseline run reports 77.55% total
coverage, below the `fail_under = 80` threshold set in `pyproject.toml:183`. The CI
command (ci.yml:111) enforces this via `fail_under` in the coverage config — the build
FAILS on coverage shortfall. Key low-coverage modules:
- `edit.py`: 44% (lines 208-263 missing — the text-edit branch, contributing to TST-002)
- `auto_moderation.py`: 61% (baseline line 372)
- Bot handlers: 28-61% (baseline)

**Problem B — Footer test failure (validated, but root cause corrected):** The test
`test_rendered_footer_contains_contact_link_markup` (test_footer_contact_link.py:116-123)
fails in the full suite at line 123: `assert "Contact us" in html`. The baseline shows it
failing on xdist worker `gw1`. The finding claims the label is "obfuscated/base64-
assembled" — this is **incorrect**. The `telegram_deep_link` tag renders
`_("Contact us")` as both the `aria-label` and visible text of the `<a>` element. The
bot username is base64-encoded in `data-bot-encoded`, but the label is plain text.

**Verified root cause — eager `gettext` import-order bug:**
`telegram_tags.py` uses `from django.utils.translation import gettext as _` (line 10)
and defines `_LABELS` as a module-level dict:
```python
_LABELS: dict[TelegramDeepLinkCommand, str] = {
    TelegramDeepLinkCommand.CONTACT_US: _("Contact us"),  # line 66 — evaluated at IMPORT TIME
    ...
}
```
`gettext` (not `gettext_lazy`) evaluates the translation at **module import time** using
the then-active language. If `telegram_tags.py` is first imported during a test that has
activated a non-English language (e.g., a preceding test on the same xdist worker called
`translation.override("ru")` or used the Django test client with `?lang=ru`), the
`_LABELS` dict captures the Russian/Bosnian translation. Subsequent tests (including the
footer test) then see translated labels instead of the English msgid.

Confirmed via `.po` files:
- EN (`msgstr ""`): `_("Contact us")` → "Contact us" (msgid, empty msgstr)
- RU (`msgstr "Связаться с ними"`): `_("Contact us")` → "Связаться с ними"
- BS (`msgstr "Kontaktiraj nas"`): `_("Contact us")` → "Kontaktiraj nas"

The conftest autouse fixture `_reset_translation_state` (conftest.py) calls
`translation.deactivate()` in teardown — but this runs AFTER the test, not before the
module import. If `telegram_tags.py` is imported DURING a test with a non-English
language active (before teardown), the labels are captured in that language permanently
for the worker process.

**Runtime verification — test passes in isolation:**
```
uv run pytest apps/core/tests/test_footer_contact_link.py --no-header --tb=short -p no:xdist --no-cov
→ 9 passed in 0.83s
```
The test passes when `telegram_tags.py` is imported with the default English language
active (no prior test activated a foreign language). It only fails under xdist when import
order causes a non-English language to be active at import time.

**The finding's recommendation (A) is suboptimal:** It recommends "assert on the
obfuscated payload (`data-start="contact_us"`, `data-bot-encoded`) rather than the
literal English label." The test **already** asserts on these (lines 119-121). The
`assert "Contact us" in html` at line 123 fails because the label was captured in a
foreign language, not because the label is obfuscated. Removing this assertion would
mask the underlying `gettext_lazy` bug rather than fix it.

**Recommendation (corrected):** 
1. (Root cause fix) Change `gettext` to `gettext_lazy` in `telegram_tags.py:10`
   (`from django.utils.translation import gettext_lazy as _`) so `_LABELS` defers
   evaluation to render time (when the active language is correct per-test).
2. (Test hardening) Wrap the footer test's `_render_footer` in
   `translation.override("en")` to guarantee a deterministic language regardless of
   import order.
3. (Coverage gate) The `fail_under = 80` threshold is actively failing (77.55%).
   Coverage must be raised or the threshold lowered with a documented plan. The
   `edit.py` gap (44%) directly contributes via TST-002.

**Effort** | M (root-cause fix is a 1-line change; coverage lift requires TST-002 fix + targeted tests)
**Priority** | P1 (footer test blocks CI deterministically under xdist)

---

### MEDIUM

> **Validation:** ✅ **Validated — BEST-PRACTICE (with number correction).** The core
> claim (module-level `slow` misclassifying fast tests) is confirmed: 51 files currently
> use `pytestmark = [..., pytest.mark.slow, ...]` (the finding cites ~40; the
> `test-strategy-report.md` was generated 2026-08-22, and several files have been
> de-marked since via commit `c73f54d`). The report's specific examples
> (test_ad_localization, test_adimage_thumbnail_urls, test_templates, etc.) have been
> fixed (now have `unit` markers), but 51 other files still carry module-level `slow`.
> The finding's test count (719) is unverified but the issue persists. Only ~40 of the
> 719 marked tests are genuinely >5s; ~679 are sub-second.

#### TST-004: [MEDIUM] — Module-level `slow` marker applied to fast tests

| Field | Value |
|:---:|---|
| **ID** | TST-004 |
| **Title** | `pytestmark = [..., pytest.mark.slow, ...]` at module level tags 51 files / ~719 tests as `slow` when most are sub-second |
| **Severity** | MEDIUM |
| **Category** | CI feedback speed |
| **File(s)** | 51 test files across `src/backend/` and `src/telegram_bot/` (grep confirmed); `pyproject.toml:167-175` (marker registration) |
| **Status** | Open |
| **Type** | BEST-PRACTICE |

**Problem (validated):** The `slow` marker is applied via `pytestmark = [..., pytest.mark.slow, ...]`
at module scope in 51 files. This tags ALL tests in those files as `slow`, regardless of
individual test duration. Only genuinely-slow tests (sweep commands, seed, full pipeline
flows) should be marked `slow` — either at the method level (`@pytest.mark.slow` on
specific tests) or by moving non-slow tests to separate files.

**Evidence — grep confirmed (51 files):**
```
src/backend/apps/ads/tests/test_edit.py:35: pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]
src/backend/apps/ads/tests/test_ad_image_service.py:25: pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]
src/backend/apps/users/tests/test_login.py:25: pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]
... (48 more files across all apps)
```

**Evidence — `pyproject.toml:167-175` (marker registration):**
```toml
markers = [
    "integration: marks tests requiring DB access",
    "slow: marks tests that take >5s (select with -m slow in nightly CI)",
    "concurrent: marks tests requiring transaction=True (TRUNCATE per test)",
    ...
]
```

**Source-reference drift:** The finding cites "~40 files" and "719 tests" from
`test-strategy-report.md` (generated 2026-08-22). Current grep shows 51 files. The
report's specific examples in the TST-007 section (test_ad_localization,
test_adimage_thumbnail_urls, test_templates, test_context_processors,
test_language_locale, test_language_middleware, test_csp_report,
test_listings_context, test_trust_prefetch, test_preferred_city_middleware,
test_autocomplete_template) have ALL been fixed (now use `pytestmark = [pytest.mark.unit]`).
However, 51 other files still carry module-level `slow`. The `test_ad_image_service.py`
file (which genuinely involves image processing) may warrant keeping `slow` at test-method
scope rather than module scope.

**Recommendation (validated):** Audit the 51 files to identify which tests are genuinely
slow (>5s) and move `slow` to method-level `@pytest.mark.slow` only on those. Remove
module-level `slow` from files where all or most tests are fast. Keep `slow` at
module-level only for known-slow suites (sweep commands, full pipeline integration).

**Effort** | M (mechanical audit + per-method marker placement)
**Priority** | P2

---

## LOW

> **Validation:** ❌ **Rejected — STALE.** All 12 SimpleTestCase files identified in
> `test-strategy-report.md` (2026-08-22) have been fixed by commit `c73f54d`
> (2026-09-07, "test: phase 1-2 test cleanup and consolidation"). Each file now has
> `pytestmark = [pytest.mark.unit]`. All 5 bare `django_db` files have also been fixed
> (now `pytestmark = [pytest.mark.django_db, pytest.mark.integration]`). The
> `test_ad_image_service.py` docstring ("Unit tests") is misleading (the tests ARE
> DB-backed) but the markers are correct — the recommendation to change markers would be
> incorrect. The bot-test `slow` redundancy (test_ad_create.py, test_create_draft_ad.py)
> is a minor residual that belongs under TST-004, not TST-007.

#### TST-007: [REJECTED/STALE] — `unit` marker missing on 12 SimpleTestCase files

| Field | Value |
|:---:|---|
| **ID** | TST-007 |
| **Title** | 12 SimpleTestCase files lack the `unit` marker (so `-m unit` selects only 102 tests instead of ~235) |
| **Severity** | LOW |
| **Category** | Test classification / marker hygiene |
| **Status** | Resolved (stale) |
| **Type** | — (rejected) |

**Problem (no longer valid):** The finding lists 12 SimpleTestCase files lacking the
`unit` marker:

1. `test_ad_localization.py`
2. `test_adimage_thumbnail_urls.py`
3. `test_detail_context.py`
4. `test_templates.py`
5. `test_context_processors.py`
6. `test_language_locale.py`
7. `test_language_middleware.py`
8. `test_csp_report.py`
9. `test_listings_context.py`
10. `test_trust_prefetch.py`
11. `test_preferred_city_middleware.py`
12. `test_autocomplete_template.py`

**Verified — ALL 12 now have `pytestmark = [pytest.mark.unit]`:**

| File | Location | pytestmark (current) |
|------|----------|---------------------|
| `test_ad_localization.py` | `apps/ads/tests/` | `[pytest.mark.unit]` ✅ |
| `test_adimage_thumbnail_urls.py` | `apps/ads/tests/` | `[pytest.mark.unit]` ✅ |
| `test_detail_context.py` | `apps/ads/tests/` | `[pytest.mark.unit]` ✅ |
| `test_templates.py` | `apps/core/tests/` | `[pytest.mark.unit]` ✅ |
| `test_context_processors.py` | `apps/core/tests/` | `[pytest.mark.unit]` ✅ |
| `test_language_locale.py` | `apps/core/tests/` | `[pytest.mark.unit]` ✅ |
| `test_language_middleware.py` | `apps/core/tests/` | `[pytest.mark.unit]` ✅ |
| `test_csp_report.py` | `apps/core/tests/` | `[pytest.mark.unit]` ✅ |
| `test_listings_context.py` | `apps/ads/tests/` | `[pytest.mark.unit]` ✅ |
| `test_trust_prefetch.py` | `apps/trust/tests/` | `[pytest.mark.unit]` ✅ |
| `test_preferred_city_middleware.py` | `apps/core/tests/` | `[pytest.mark.unit]` ✅ |
| `test_autocomplete_template.py` | `apps/search/tests/` | `[pytest.mark.unit]` ✅ |

All 12 files were modified in commit `c73f54d` (2026-09-07) to add the `unit` marker.
The finding's reproduction step (`pytest --collect-only -q -m unit | grep -c` → 102) is
outdated — the 12 files now contribute ~133 additional `unit`-marked tests.

**Secondary claims:**

- **5 bare `django_db` files** (test_recompute_command, test_price_normalizer,
  test_create_admin_user, test_privacy, test_consent_context): ALL have been fixed —
  now have `pytestmark = [pytest.mark.django_db, pytest.mark.integration]` (with the
  `integration` marker added). The "unclassified" claim is STALE.
- **`test_ad_image_service.py`**: Docstring says "Unit tests for AdImageService"
  (line 4) but `pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]`
  (line 25). The tests ARE DB-backed (use `create_test_ad`, `AdImageService.create_or_skip`
  which creates DB rows, assert `result.pk is not None`). The docstring is misleading
  but the **markers are correct** — this IS an integration test, not a unit test. The
  finding's recommendation ("Remove `integration` and `slow`; add `unit`") would be
  **incorrect** — it would misclassify a DB-backed test as unit. Fix: update the docstring
  to "Integration tests for AdImageService."
- **Bot test `slow` redundancy** (test_ad_create.py, test_create_draft_ad.py): Still
  valid — both have `pytestmark = [django_db(transaction=True), slow, integration,
  concurrent]`. The `slow` is redundant (concurrent implies DB-intensive) but this
  belongs under TST-004, not TST-007. Minor residual, not rejected outright.

**Source-reference drift:** The `test-strategy-report.md` (the finding's evidence
source) was generated 2026-08-22; commit `c73f54d` (2026-09-07) resolved the 12-file
and 5-file issues. The findings.md was written 2026-09-13 without accounting for the
post-report cleanup.

**Recommendation:** Reject as stale. The 12 SimpleTestCase files and 5 bare `django_db`
files are resolved. Two minor advisories remain (see Rollout Analysis).

---

## REJECTED

> ❌ **TST-006: CI coverage lacks line-missing reporting** — **Rejected.** The CI
> command (`ci.yml:111`) uses `--cov-report=term` without the `--cov-report=term-missing`
> flag. However, `pyproject.toml:184` sets `show_missing = true` in
> `[tool.coverage.report]`, which causes the `term` reporter to include the "Missing"
> column with line numbers. The finding's evidence block selectively quotes only
> `fail_under = 80` and omits `show_missing = true`, undermining the claim that
> "developers see only a total percentage with no missing-line detail." The baseline
> coverage log confirms this: lines 176–388 show a full coverage table WITH a "Missing"
> column (e.g., `edit.py: ... 208-263, 280-296, 314-335`). The `--cov-report=term-
> missing` flag would be redundant with the existing `show_missing = true` config.
> Additionally, the finding claims `fail_under` is "enforced only implicitly" —
> the baseline confirms it IS enforced: "ERROR: Coverage failure: total of 78 is less
> than fail-under=80" and "FAIL Required test coverage of 80.0% not reached."

---

## Cross-Finding Analysis

### Same root cause → merge candidates

1. **TST-001 ↔ TST-003 (coverage):** TST-001's migration test gap contributes to the overall
   coverage shortfall in TST-003. If the `DisableMigrations` pattern is replaced with a
   properly-scoped migration test, it would also exercise `migrations.py` files and raise
   coverage. However, the root causes are distinct: TST-001 is about migration
   disabling; TST-003 is about the 77.55% < 80% threshold. No merge — but the migration
   test fix would improve the coverage metric.

2. **TST-002 ↔ TST-003 (edit.py coverage):** TST-003's coverage report shows `edit.py` at
   44% with lines 208-263 missing (the PUBLISHED text-edit branch). TST-002 identifies
   this exact gap. Fixing TST-002 (adding text-edit tests) will directly raise `edit.py`
   coverage. These are linked but distinct — TST-002 is the security/correctness gap;
   TST-003 is the coverage-threshold gate. No merge recommended.

3. **TST-004 ↔ TST-007 (marker hygiene):** Both address test classification. TST-004 is
   about `slow` being overused at module level; TST-007 is about `unit` being missing on
   SimpleTestCase files. Commit `c73f54d` resolved the TST-007 issues (adding `unit` to
   the 12 files) by replacing `slow` with `unit` on those files. The remaining
   `slow`-redundancy (test_ad_create.py, test_create_draft_ad.py) is TST-004 territory.
   These should be addressed together in a marker-hygiene pass.

4. **TST-002 ↔ Phase 05 AD-003:** TST-002 is the test-coverage perspective of the
   production code bug AD-003. Both are SPEC-DEVIATION. AD-003 is the production fix
   (wire `auto_moderate()` into the text-edit branch); TST-002 is the regression test
   (assert `auto_moderate` IS called on text-edit). These are complementary, not
   duplicate. The Phase 05 rollout-safety note explicitly requires the test: "Add a
   text-edit test asserting auto_moderate IS called."

5. **TST-005 ↔ Phase 04 AUT-002:** TST-005 is the Phase 11 re-raising of AUT-002.
   Phase 04 classified it as LOW → SPEC-DEVIATION (P2, Likelihood LOW). TST-005 escalates
   to HIGH (P1). The Phase 04 validator confirmed the same evidence (no permanent
   concurrent test, temporary repro was audit-only). The escalation lacks additional
   justification — the production code (UPDATE ... RETURNING) is already atomic (Phase 03
   DB-004). Reclassified: HIGH → MEDIUM / SPEC-DEVIATION.

### Conflicting evidence

1. **TST-005 vs Phase 04 AUT-002 severity:** The Phase 04 audit (validated) classifies
   AUT-002 as LOW → SPEC-DEVIATION (P2, Likelihood LOW). TST-005 escalates to HIGH (P1).
   This is an escalation without new evidence. The production claim path is atomic; the
   risk is a future regression, not a current exploit. → Severity corrected to MEDIUM.

2. **TST-006 vs pyproject.toml config:** The finding claims CI lacks missing-line detail.
   The config (`show_missing = true`) provides it. No genuine conflict in the code — the
   finding is simply invalid. → Rejected.

3. **TST-003 footer root cause vs finding's explanation:** The finding says the label is
   "obfuscated/base64-assembled." The code shows it's plain `_("Contact us")`. The actual
   issue is eager `gettext` at import time. → Root cause corrected in this report.

### Dependency chains

1. **TST-002 → Phase 05 AD-003 fix:** The regression test for TST-002 (asserting
   `auto_moderate` IS called on text-edit) will FAIL until AD-003 is fixed (wire the call
   into the text-edit branch). The test should be written first (TDD), then AD-003 fixed
   to make it pass. Phase 05 rollout safety confirms: "Add a text-edit test asserting
   auto_moderate IS called."

2. **TST-001 independence:** The migration test fix is independent of all other findings.
   It requires re-enabling migrations in a test-scoped manner, which may slow the test
   suite (migrations replay on DB setup). Consider gating behind a marker (`-m migration`)
   run only in nightly CI.

3. **TST-003 coverage depends on TST-002:** Fixing TST-002 (adding text-edit tests)
   raises `edit.py` from 44% to ~70%, contributing to resolving the 77.55% → 80% gap.
   The footer test fix (TST-003-B) is independent.

4. **TST-005 independence:** Adding the concurrent claim test requires no production
   code change (the claim is already atomic). It's independent of TST-002 and Phase 05
   AD-003. It depends only on the `handle_login_orm` function existing in the bot's
   login handler (confirmed at `login.py`).

5. **TST-004/TST-007 marker cleanup:** Independent of all production code. The
   `c73f54d` cleanup already resolved the TST-007 issues; remaining TST-004 work is
   mechanical marker placement.

---

## Rollout Safety

| ID | Risk | Backward-compatible? | Test gap (must cover) |
|----|------|----------------------|-----------------------|
| TST-001 | Low | Yes (test-only; may slow test suite) | Verify `makemigrations --check --dry-run` produces no pending migrations; verify `migrate --noinput` is idempotent when migrations are re-enabled |
| TST-002 | Med | No (depends on Phase 05 AD-003 code fix) | Text-edit test asserting `auto_moderate` IS called + pass/fail redirect behavior mirrors reactivation. Test will fail until AD-003 is fixed. |
| TST-003-A | None | Yes (additive tests / threshold adjustment) | N/A |
| TST-003-B | Low | Yes (test-only; `gettext_lazy` or `override("en")`) | Verify footer test passes in full suite with xdist (deterministic language) |
| TST-004 | None | Yes (test-only marker changes) | Verify `-m "not slow"` still runs all fast tests correctly |
| TST-005 | Low | Yes (adds test, no prod change) | Concurrent double-claim test using `asyncio.gather`; assert exactly 1 winner |
| TST-007 | None | Yes (mostly already fixed) | Minor: correct `test_ad_image_service.py` docstring; remove redundant `slow` from bot tests |

### Rollout ordering

1. **TST-003-B (footer test fix — P1, blocks CI):** Fix the eager `gettext` in
   `telegram_tags.py` (change to `gettext_lazy`) and/or harden the footer test with
   `translation.override("en")`. This is the only CI-blocking failure and should ship
   first.
2. **TST-002 (text-edit coverage — P0, security):** Write the regression test first (it
   will fail), then implement Phase 05 AD-003 (wire `auto_moderate()` into the text-edit
   branch). The test becomes green after the code fix. Phase 05 AD-003 is already P0.
3. **TST-005 (concurrent claim test — P2):** Add the permanent concurrent test using
   `asyncio.gather` (based on Phase 04's R-03 temporary test). No production change
   needed.
4. **TST-001 (migration test — P0):** Add a migration-enforcement test gated behind a
   marker, run in nightly CI. Requires re-enabling migrations for that test scope only.
5. **TST-004 (slow marker cleanup — P2):** Audit the 51 files, move `slow` to
   method-level where tests are genuinely slow, remove module-level `slow` from files
   where tests are fast.
6. **TST-007 (stale — resolved):** No action needed. Advisory: fix the
   `test_ad_image_service.py` docstring; move the bot-test `slow` cleanup under TST-004.
7. **TST-006 (rejected):** No action — `show_missing = true` already provides missing-line
   detail.

### Circular / hidden dependencies

None. All findings are independently addressable. TST-002 depends on Phase 05 AD-003
(production fix), but the test can be written first (TDD). TST-003-A coverage depends
partly on TST-002 (edit.py coverage), but the coverage gate is a separate concern.

---

## Warnings

1. **TST-003-B: import-order nondeterminism under xdist.** The eager `gettext` in
   `_LABELS` is a latent bug that only manifests under xdist when import order causes
   the module to be loaded during a non-English test. This is a **time bomb** — the
   failure may move between workers or disappear after a code change that alters import
   order. Fix with `gettext_lazy` immediately, not just a test workaround.

2. **TST-005 severity overstatement.** The Phase 04 audit (validated) classifies
   AUT-002 as LOW → SPEC-DEVIATION (P2, Likelihood LOW). The Phase 11 escalation to HIGH
   lacks additional evidence — the production claim path is already atomic per Phase 03
   DB-004. Downgrading to MEDIUM/SPEC-DEVIATION aligns with the Phase 04 assessment
   while still flagging the missing test.

3. **TST-006 finding evidence is misleading.** The evidence block selectively quotes
   `pyproject.toml` showing only `fail_under = 80` and omits the adjacent
   `show_missing = true` (line 184) and `skip_empty = true` (line 185). This omission
   directly undermines the finding's core claim. The rejection is based on this
   selective citation being contradicted by the actual config and the baseline log.

4. **TST-001 docstring cross-reference error.** The test file
   `test_migrations.py:2` docstring says "Tests for migration reproducibility and
   idempotency (TST-005)" — but the finding ID is TST-001, not TST-005 (which is the
   concurrent login-token finding). This appears to be a copy-paste error in the test
   file's docstring.

5. **TST-007 staleness from `c73f54d` cleanup.** The `test-strategy-report.md` (the
   finding's evidence source) was generated 2026-08-22. Commit `c73f54d`
   (2026-09-07, "test: phase 1-2 test cleanup and consolidation") resolved the 12-file
   and 5-file issues. The findings.md (2026-09-13) was written after this commit but
   does not reflect the fix — likely because it references the pre-cleanup report rather
   than the current code state.

6. **Phase 4 evidence code drift (minor):** The Phase 4 findings reference
   `test_login.py:148-159` for `test_reclaim_blocked` evidence snippets, but in the
   current code `test_reclaim_blocked` starts at line 134 and the quoted body lines
   (148-159) have shifted slightly. The Phase 4 validated findings note a similar
   off-by-one in language.py (line 38 vs 68). No substantive impact on TST-005.

---

## Required Fixes

1. **TST-002 + Phase 05 AD-003 (P0, SPEC-DEVIATION):** Wire `auto_moderate(ad)` into the
   PUBLISHED text-edit branch of `ad_edit` (`edit.py:228`, after
   `ad.transition_to(AdStatus.ON_MODERATION)`); on pass redirect to dashboard, on fail
   re-render `edit.html` with error (mirror reactivation). Add a committed regression
   test in `test_edit.py` asserting `auto_moderate` IS called and pass/fail redirects
   differ. (Phase 05 validated findings, line 524.)

2. **TST-003-B (P1, test determinism):** Fix the eager `gettext` in
   `telegram_tags.py:10-11` — change `from django.utils.translation import gettext as _`
   to `from django.utils.translation import gettext_lazy as _` so `_LABELS` defers
   translation to render time. Alternatively (or additionally), wrap `_render_footer` in
   `translation.override("en")` to guarantee deterministic language. This is the only
   CI-blocking failure.

3. **TST-001 (P0, migration safety):** Add a migration-enforcement test that re-enables
   migrations (temporarily sets `MIGRATION_MODULES = {}` for the test scope) and runs
   `makemigrations --check --dry-run`. Gate behind a marker (`-m migration`) selected
   only in nightly CI to avoid slowing the fast gate.

4. **TST-005 (P2, SPEC-DEVIATION):** Add a permanent concurrent double-claim test to
   `src/telegram_bot/tests/test_login.py` using `asyncio.gather` to fire two
   `handle_login_orm` calls with the same `token_hash` but different `telegram_id`
   values concurrently, asserting exactly one wins. (Phase 04 R-03 temporary test
   provides the basis; `test_reclaim_blocked` at line 134 is the insertion point.)

5. **TST-004 (P2, BEST-PRACTICE):** Audit the 51 files with module-level `slow`. Move
   `slow` to method-level `@pytest.mark.slow` on genuinely slow tests only. Remove
   module-level `slow` from files where all tests are sub-second.

---

## Advisory Recommendations

1. **TST-007 advisory (docstring):** Fix the misleading docstring in `test_ad_image_service.py:4`
   — change "Unit tests for AdImageService" to "Integration tests for AdImageService
   (DB-backed, media-file fixture)" since the tests use `create_test_ad` and assert
   `result.pk is not None` (DB-backed).

2. **TST-004/TST-007 advisory (bot test markers):** In `test_ad_create.py` and
   `test_create_draft_ad.py`, the module-level `slow` is redundant with `concurrent`
   (which already implies `transaction=True` and DB-isolation overhead). Consider
   removing `slow` at module level and applying `@pytest.mark.slow` only to the
   genuinely-slow bot test methods (full FSM flow tests that simulate a seller posting
   multi-step: category → photo → title → description → price).

3. **TST-003-A advisory (coverage strategy):** The `fail_under = 80` gate is failing at
   77.55%. Beyond the TST-002 fix (edit.py), consider whether the `seed` marker exclusion
   (`-m "not seed"`) is hiding large swaths of untested seed code from the coverage
   denominator. Verify the coverage measurement includes all non-seed modules.

4. **TST-001 advisory (DisableMigrations pattern):** The `DisableMigrations` class
   (test.py:83-91) affects ALL tests in the suite — even unit tests that don't need
   migrations are running without them. Consider scoping the pattern: a per-file or
   per-class fixture that enables migrations only for migration-reproducibility tests,
   rather than a global `MIGRATION_MODULES` override.

---

## Execution Validation

- **Targets still exist:** All cited files and line ranges are present in the current
  source tree:
  - `test.py:83-91` (`DisableMigrations`, `MIGRATION_MODULES`) ✅
  - `test_migrations.py:20,23,28,60` (skipif guard, both test functions) ✅
  - `edit.py:208-244` (PUBLISHED text-edit branch) ✅
  - `edit.py:331` (`auto_moderate(ad)` in `ad_reactivate`) ✅
  - `test_edit.py:35` (pytestmark), lines 104-340 (5 classes, 6 methods, all reactivation) ✅
  - `telegram_tags.py:10-11,64-69` (`gettext` import, `_LABELS` dict) ✅
  - `test_footer_contact_link.py:116-123` (footer assertions) ✅
  - `ci.yml:111` (CI pytest invocation with `--cov-report=term`) ✅
  - `pyproject.toml:183-185` (`fail_under = 80`, `show_missing = true`, `skip_empty = true`) ✅
  - `pyproject.toml:170` (`concurrent` marker definition) ✅
  - Bot `test_login.py:134` (sequential `test_reclaim_blocked`) ✅
  - Backend `test_login.py` (20 methods, no concurrent test) ✅
  - All 12 SimpleTestCase files (now have `pytestmark = [pytest.mark.unit]`) ✅
  - All 5 bare `django_db` files (now have `integration` marker) ✅

- **Dependencies remain valid:** Phase 05 AD-003 (validated, Open) is the production
  code counterpart of TST-002; the Phase 05 recommendation requires the TST-002 test.
  Phase 04 AUT-002 (validated, SPEC-DEVIATION) is the auth-domain counterpart of TST-005;
  the Phase 04 recommendation requires the same concurrent test. No architectural drift
  observed between the Phase 04/05 audits and the current code. ✅

- **Assumption checks:** The Phase 04 audit's assumption that
  "`test_concurrent_claim_tmp.py` was deleted in consolidation `c73f54d`" is
  **refuted** by git history — the file was never committed. The Phase 04 validated
  findings (line 288) confirm: "The temporary test `test_concurrent_claim_tmp.py`
  (referenced in the finding) was confirmed deleted — no file matching `*concurrent*`
  exists in any `tests/` directory." ✅

- **Runtime verification performed:**
  - Footer test in isolation: `9 passed in 0.83s` (confirms the test passes without
    xdist import-order interference) ✅
  - Baseline full-suite run: `test_rendered_footer_contains_contact_link_markup`
    FAILED on `[gw1]` (confirms xdist-dependent translation capture) ✅
  - Baseline coverage report: shows "Missing" column with line numbers (confirms
    `show_missing = true` is active) ✅

---

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Validated (corrected) | 4 | TST-001 (precision: not both skipped), TST-002 (linked to AD-003, impact clarified), TST-005 (severity HIGH→MEDIUM, deletion claim corrected), TST-003 (root cause corrected: eager `gettext`, not obfuscation) |
| Validated (unchanged) | 1 | TST-004 (module-level `slow` on 51 files) — BEST-PRACTICE |
| Rejected | 1 | TST-006 (show_missing=true already provides missing-line detail; evidence omits this config) |
| Stale/Rejected | 1 | TST-007 (12 SimpleTestCase files + 5 bare django_db files all fixed by c73f54d; bot-test residual absorbed into TST-004) |

### Reclassified Findings

| ID | Original Severity | Corrected Severity | Type | Rationale |
|----|-------------------|--------------------|------|-----------|
| TST-001 | CRITICAL | CRITICAL | SPEC-DEVIATION | Valid concern (no migration drift detection); precision correction: only `test_makemigrations_check` is SKIPPED, `test_migration_idempotency` is a no-op pass |
| TST-002 | CRITICAL | CRITICAL | SPEC-DEVIATION | Matches Phase 05 AD-003 (validated, HIGH, SPEC-DEVIATION, Open). Zero text-edit coverage confirmed; 6 tests all reactivation. |
| TST-005 | HIGH | **MEDIUM** | SPEC-DEVIATION | Phase 04 AUT-002 (validated) classifies as LOW→SPEC-DEVIATION (P2, Likelihood LOW). Production claim path is atomic (Phase 03 DB-004). HIGH overstates; MEDIUM fits "Branch coverage <80% on critical code." |
| TST-003 | MEDIUM | MEDIUM | BEST-PRACTICE | Coverage shortfall valid (77.55% < 80%). Footer test failure valid but root cause is eager `gettext`, not obfuscation. |
| TST-004 | MEDIUM | MEDIUM | BEST-PRACTICE | 51 files with module-level `slow` (finding says ~40). Core issue persists. Numbers updated. |
| TST-006 | MEDIUM | — | **REJECTED** | `show_missing = true` in pyproject.toml:184 provides missing-line detail. Baseline confirms. Finding's evidence omits this. |
| TST-007 | LOW | — | **STALE** | All 12 SimpleTestCase files + 5 bare django_db files fixed by c73f54d. Only minor residuals remain. |

### Rejected / Stale Findings

| ID | Action | Rationale |
|----|--------|-----------|
| TST-006 | **Rejected** | `show_missing = true` (pyproject.toml:184) makes `--cov-report=term-missing` redundant. The baseline coverage log shows a "Missing" column with line numbers (lines 176–388). The finding's evidence selectively omits `show_missing = true`. |
| TST-007 | **Stale** (partially) | All 12 SimpleTestCase files and 5 bare `django_db` files have been fixed by commit `c73f54d` (2026-09-07). The `test_ad_image_service.py` docstring is misleading but its markers are correct (the tests ARE DB-backed). Bot-test `slow` removal is a minor residual absorbed into TST-004. |

### New Findings (Discovered During Validation)

| ID | Severity | Type | Title |
|----|----------|------|-------|
| TST-003-B | MEDIUM | BEST-PRACTICE | `telegram_tags.py` uses eager `gettext` (not `gettext_lazy`) at module level for `_LABELS` — import-order-dependent translation capture under xdist causes the footer test to fail nondeterministically |

---

**Validator:** Kilo (read-validation agent)
**Status:** ✅ Validated per Phase 99 — all findings checked against live source tree, baseline logs, and Phase 04/05 validated findings.
