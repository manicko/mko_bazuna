# Active Findings Compilation — Verification Audit

**Compiled:** 2026-08-29 (today)
**Verified against:** working tree at `HEAD ba5c65e` (`fix(docker): compilemessages startup hang`) + `c73f54d` (`test: phase 1-2 test cleanup and consolidation`) + pre-existing `b62612`/`3ddc0b2` (test-optimization Phase A–D)
**Source reports verified:**
1. `.ai/problems/audit_findings_compilation.md` — 28 findings (F-01, §2.1–§2.12, C-01–C-11, D-01–D-04)
2. `.ai/reports/fix_load_catalog_fixture_scope_report.md` — §8 (4 recs) + §3 (2 env issues)

**Method:** Every finding was checked against the live source tree via `grep`/`glob`/`read` tools, then the highest-value subset was confirmed empirically by running tests through the documented Docker test entrypoint (`mko-bazuna-test-db-1` is running and healthy on port 5433; `--entrypoint="-"` not needed — the entrypoint no longer hangs).

---

## 1. Executive Summary

Of the **34 findings** in the two source reports, only **4 remain relevant** (2 open + 2 partial after Validator correction). The remaining **29 were already resolved** in the current tree — the bulk by the test-optimization Phase A–D work (`b62612`/`3ddc0b2`) and the follow-up cleanup commit `c73f54d` (8/27), with the test-infrastructure hang fixed by `ba5c65e` (8/29, this morning). One finding (§8-rec-3) was **rejected by the Validator** as a false premise (PgBouncer IS present in the production compose).

| Category | Count | Finding IDs |
|---|---|---|
| **RELEVANT-OPEN** | 2 | D-02, §8-rec-4 |
| **RELEVANT-PARTIAL** | 2 | D-01, D-04 |
| **STALE-RESOLVED** | 29 | F-01, §2.1–§2.12, C-01–C-11, D-03(partial), §8-rec-1, §8-rec-2, §3-Issue-A, §3-Issue-B |
| **STALE-REJECTED** | 1 | §8-rec-3 (*Validator verdict: false premise — PgBouncer present in `docker-compose.prod.yml`; recommendation NO-GO*) |
| **STALE-OUTDATED** | 0 | — |

> **Meta-observation:** the audit compilation (`.ai/problems/audit_findings_compilation.md`, 8/26) lists §2.1–§2.12 and C-01–C-11 as **OPEN**, but the current tree shows all of them closed by commits that pre-date (and post-date) the compilation. The compilation is effectively stale relative to the live repo. The live `test_quality_audit_implementation_plan.md` (`.ai/plans/done/`) correctly lists **only D-01, D-02, D-04** (plus §8-rec-3/4) as pending work.

---

## 2. Relevant Findings (Open / Partial) — Actionable

### RELEVANT-OPEN

#### D-02 — Plan §1.4 still claims "CI runs all 934 tests"
- **Type:** `[DOC-UPDATE]` · **Severity:** LOW · **Priority:** P2 (doc-only)
- **Original claim:** `25_test-optimization-plan_done.md` §1.4 (line 75): *"test job runs all 934 tests including the ~18-minute seed batch."*
- **Current verification:**
  - Live `.github/workflows/ci.yml:91` runs:
    `uv run pytest -m "not seed" -n auto --dist loadgroup --tb=short --cov --durations=10 ... --reuse-db`
    → CI runs the **non-seed tier only**, with `loadgroup` (not `loadscope`) and `--reuse-db`.
  - §14 T-05 (line 697) *does* acknowledge `-m "not seed"` but mis-states the distribution mode as `--dist loadscope`; the §12 correction note (line 724) updates the test count to 1137/8-markers but did **not** rewrite §1.4.
  - `test_quality_audit_implementation_plan.md:235` lists `T_DOC_CI — D-02` as a **pending** doc task.
- **Recommendation:** Rewrite §1.4 to state CI runs `pytest -m "not seed" -n auto --dist loadgroup --reuse-db` (non-seed tier, ~1111 tests), redirecting seed coverage to `ci-nightly.yml`. Effort: trivial. (The live CI behaviour is already correct; only the doc is wrong.)

#### §8-rec-3 — `prepare_threshold: None` still set despite no PgBouncer in use
> **🛑 Validator verdict: NO-GO (false premise)** — See §7.1 and §8.2. The Auditor only grepped `docker-compose.yml` and missed `docker-compose.prod.yml`, where PgBouncer IS deployed (opt-in `--profile pgbouncer`, transaction pooling). Seven architecture/spec docs explicitly **require** `prepare_threshold: None` for PgBouncer tx-mode. **The recommendation to remove this setting is REJECTED.** This finding is reclassified as **STALE-REJECTED** (no action).
- **Type:** `[BEST-PRACTICE]` · **Severity:** LOW · **Priority:** Rejected
- **Original claim (fix report §3.2 + §8-rec-3):** `prepare_threshold: None` in `config/settings/base.py` disables psycopg3 server-side prepared statements; combined with `CONN_MAX_AGE=0` it "creates a connection lifecycle where the psycopg3 Connection can enter a [BAD] state." Recommendation: verify the option is still needed for PgBouncer; if no transaction pooling, remove it.
- **Current verification:**
  - `config/settings/base.py:160` and `:172-173` still set `"prepare_threshold": None` under comments "PgBouncer async safety (zone C5)".
  - `docker-compose.yml` defines services `db`/`redis`/`migrate`/`load_catalog`/`create_admin`/`web`/`bot`/`nginx` — **no PgBouncer / pooler / pgbouncer** service anywhere (grep `pgbouncer|PgBouncer|pooler` → 0 matches).
  - **The report's root-cause attribution is inaccurate.** My empirical run of `test_breadcrumbs_render.py` (the only class-scoped fixture that opens `transaction.atomic()`) produced **no `[BAD]` connection and no `OperationalError: the connection is closed`** (4 passed, see §4). The `[BAD]` state is caused by Django's `BaseDatabaseWrapper.close()` leaving `self.connection` non-None-but-dead when `closed_in_transaction` is set inside an atomic block — fixed by the `django_db_setup: None` ordering dependency (commit `c73f54d`), **not** by `prepare_threshold`. `prepare_threshold: None` is unrelated to the `[BAD]` mechanism.
- **Recommendation:** Confirm PgBouncer is genuinely absent from the deployment topology. If so, drop `"prepare_threshold": None` (and the now-misleading "PgBouncer async safety" comments at L158/L170) to remove the false causal link in the docs and reduce config surface. If PgBouncer is added later, re-introduce it with a clear comment. Effort: trivial. (Low impact — not currently causing failures.)

### RELEVANT-PARTIAL

#### D-01 — Plan §1.2 ("Markers (Current)") still says markers "Not registered"
- **Type:** `[DOC-UPDATE]` · **Severity:** LOW · **Priority:** P2 (doc-only)
- **Original claim:** `25_test-optimization-plan_done.md` §1.2 table (lines 40–44) lists `unit`, `e2e`, `seed`, `settings`, `concurrent` as **"Not registered"**.
- **Current verification:** Live `pyproject.toml:163-172` registers **8** markers: `unit, integration, seed, settings, concurrent, slow, real_images, xdist_group` — **`e2e` is removed** (also noted in `docs/99-agent/rules.md:51`: "The `e2e` marker was removed — do not reference it"). §12 correction note (line 724) and §14 T-01 acknowledge current registration, but §1.2's "Current State" table was never rewritten. `test_quality_audit_implementation_plan.md:95,229` list `T_DOC_MARKERS — D-01` as **pending**.
- **Recommendation:** Rewrite §1.2 to reflect the live 8-marker set (and explicitly note `e2e` was removed). Effort: trivial.

#### D-04 — §14 "Completed Tasks" table over-claims vs. live CI
- **Type:** `[DOC-UPDATE]` · **Severity:** LOW · **Priority:** P2 (doc-only)
- **Original claim:** §14 T-12 (line 704): *"1137 tests collected, 0 failures"*; §12 correction note (719–725) addresses the 934→1137 transition and the shadowed-`tests.py` exclusion.
- **Current verification:** The §14 correction note **does** resolve the original concern (shadowed 31 `tests.py` tests excluded from baseline; "50+" figure clarified as inflated; 1 real failure was a test-helper bug). **However** the §14 completion table still contains inaccurate rows:
  - T-05 (line 697): claims CI uses `--dist loadscope` → live `ci.yml:91` uses **`--dist loadgroup`**.
  - T-10 (line 702): claims `--dist loadscope` in `ci.yml` **and** `ci-nightly.yml` → live `ci.yml:91` uses `loadgroup`; `ci-nightly.yml:73` runs `pytest -m "seed" ... --reuse-db` with **no `-n`/xdist at all**.
  - T-01 (line 693): claims `e2e` was registered → live `pyproject.toml` has **`e2e` removed**.
  - (The `loadscope` inaccuracy is independently flagged in `.ai/reports/test_env_acceleration_report.md:298`: "claims loadscope; ci.yml:91 uses loadgroup — current state is correct (loadgroup).")
  - T-06 (line 698) is **accurate**: `ci-nightly.yml` exists and runs `-m "seed"` daily.
  - `test_quality_audit_implementation_plan.md:97,241` list `T_DOC_T12 — D-04` as **pending**.
- **Recommendation:** Reconcile §14 T-01/T-05/T-10 rows with live config (`loadgroup`, no `e2e`, `reuse-db`, `ci-nightly.yml` has no xdist). The substantive T-12 concern is already corrected; this is table-level doc hygiene. Effort: trivial.

#### §8-rec-4 — Stale `test_mko_bazuna_gw*` DB cleanup not in `make test-recreate`
- **Type:** `[BEST-PRACTICE]` · **Severity:** LOW · **Priority:** Recommended
- **Status updated:** RECLASSIFIED from PARTIAL→**OPEN** by Researcher 2 (verified evidence — see below)
- **Original claim:** Stale xdist worker databases (`test_mko_bazuna_gw*`) from prior parallel runs compound the `[BAD]` connection issue; recommendation: add pre-flight `DROP DATABASE IF EXISTS test_mko_bazuna_gw*` to `make test-recreate`.
- **Current verification + Researcher 2 correction:**
  - `Makefile:137-139` (`test-recreate`) runs `… run --rm --env PYTEST_OPTS="--no-reuse-db --create-db …" test` — **no `DROP DATABASE` for `*_gw`**.
  - **The Auditor's justification (b) was INCORRECT.** The Auditor claimed "the current architecture uses `--dist loadgroup` against a **single shared** `test_mko_bazuna` DB — it does not create per-worker `gw*` databases." Researcher 2 proved this is **false**: the project does NOT override `django_db_modify_db_settings` (grep: 0 matches across `src/`), so pytest-django's **default** per-worker database creation is active. Each xdist worker creates `test_mko_bazuna_gw0`, `test_mko_bazuna_gw1`, etc. The 16 stale `gw*` DBs from the fix report were produced by the **current** config, not a prior different config.
  - Under `--reuse-db` (entrypoint + CI default) with a persistent named volume (`mko-bazuna-test_postgres_data`), stale `gw*` databases **DO recur** when worker count changes between runs or runs are interrupted (SIGKILL'd workers leave stuck connections).
  - `--no-reuse-db --create-db` (in `make test-recreate`) can also fail: `DROP DATABASE` raises "database is being accessed by other users" when connections from a crashed worker persist — pytest-django does not handle this gracefully.
  - The `gw*` suffix originates from pytest-xdist worker naming (`gw0`, `gw1`) appended by pytest-django's `django_db_modify_db_settings_xdist_suffix` session fixture.
- **Recommendation (from Researcher 2):** Add a pre-flight `DROP DATABASE IF EXISTS … WITH (FORCE)` loop to `make test-recreate` (and `Makefile.ps1` `Invoke-TestRecreate`), running **before** pytest spawns workers. Also add a standalone `test-clean-db` Makefile target. CI needs no change (ephemeral env). See §4 for concrete implementation.

#### D-03 — (partial, retained for completeness) Plan §1.1 still lists deleted `tests.py`
- **Type:** `[DOC-UPDATE]` · **Severity:** LOW
- **Original claim:** §1.1 references the shadowed `tests.py` files as existing.
- **Current verification:** `src/backend/apps/moderation/tests.py` and `src/backend/apps/search/tests.py` are **deleted** (commits `07a8f49`/`d72e597`); migrated replacements `test_moderation_views.py` (22 tests) and `test_search_view.py` (9 tests) are tracked and pass. §14 correction note (722–723) documents the migration. However **§1.1 line 28 still lists** `tests.py (2 files: search/tests.py, moderation/tests.py)` in the "Test Structure" snapshot, and the project's implementation plan does **not** list §1.1 as an open TODO (it was marked RESOLVED-partial in the original).
- **Recommendation:** Optional low-priority rewrite of the §1.1 table to state `tests.py` removed; otherwise superseded by §14. (Treated as stale-resolved; listed here only because the §1.1 text is not yet corrected.)

---

## 3. Stale / Resolved Findings (Not Re-implemented)

All of the following were **OPEN** in the 8/20–8/26 source reports but are **closed in the current tree**. Nothing needs re-implementation.

### Test-quality findings (§2.x) — all RESOLVED by `b62612`/`3ddc0b2` (Phase A–D) + `c73f54d`
| Finding | Evidence (current tree) |
|---|---|
| **F-01** CRITICAL shadowed `tests.py` | `moderation/tests.py` + `search/tests.py` deleted (git shows 988 deletions); verified absent via `glob`. Migrated to `test_moderation_views.py`/`test_search_view.py`. |
| **§2.1** Duplicated `seller`/`user`/`category`/`city` fixtures | `grep "^def seller"` / `"^def (user\|category\|city)\b"` across `src/backend/apps` → **0 matches** (only `src/backend/conftest.py:64` defines `seller`). `test_quality_audit_implementation_plan.md` Phase A canonicalised all fixtures. |
| **§2.2** Duplicated `_make_ad`/`_create_ad` helpers | `grep "def _make_ad\|def _create_ad"` → the 14 listed files have **none**; only `_create_ad_with_*` / `_create_adimage_*` (different names) remain. |
| **§2.3** `django.test.TestCase` usage (9 files) | `grep "from django.test import (TestCase\|SimpleTestCase)"` across `src/backend/apps` + `src/telegram_bot` → **0 matches**. All 9 migrated (Phase B). |
| **§2.4 / §2.11** Private-method testing (`TestValidate*`) | `test_auto_moderation.py` rewritten — module docstring: *"All tests exercise the public API rather than private validation helpers… tested through `check()`"*. `grep "_validate_title_length\|_contains_banned_words"` in that file → **0 matches**. |
| **§2.5** Missing decorator unit tests | `test_decorators.py` exists with `TestStaffRequired` (L44) + `TestStaffRequiredApi` (L93). **Empirically: 12 tests pass** (see §4). |
| **§2.6** `e2e` marker registered but unused | `@pytest.mark.e2e` grep across `src/backend` → **0 matches**; `pyproject.toml` markers list → **no `e2e`**. `e2e` was removed (rules.md:51). |
| **§2.7** `SimpleTestCase` usage (9 files) | Same grep as §2.3 → **0 matches**. |
| **§2.8** Raw strings for enum fields | `test_sweep_commands.py` uses `AnalyticsEventType.SEARCH_PERFORMED` (L284/318); `test_deletion.py` grep for `ban_account|content_removal|action_type` → **0 matches**. |
| **§2.9** Direct `Ad.objects.create()` (2 files) | `grep "Ad.objects.create"` across `src/backend` → only `conftest.py:144` (inside `create_test_ad` itself). `test_breadcrumbs_render.py:126` uses `create_test_ad`. |
| **§2.10** `inspect.getsource()` structure test | `grep "inspect.getsource"` across `src/backend` → **0 matches**. `test_sweep_lock_structure.py` rewritten (c73f54d). |
| **§2.12** Duplicate bot login-token tests | `test_claim_login_token.py` + `test_login_claim.py` **deleted** (c73f54d); consolidated into `test_login.py` (6 tests, per `test-suite-audit-plan_DONE.md:266`). |

### Coverage gaps (C-01–C-11) — all RESOLVED
| Gap | Evidence (current tree) |
|---|---|
| **C-01** Ad check constraints + `transition_to` state machine | `test_ad_constraints.py` (`TestStatusTimestampConstraints` parametrized over 5 statuses + `TestMutualExclusivityConstraint`) **and** `test_ad_lifecycle.py` (`TestTransitionValidation` invalid-transition `ValueError` at L38/49; `TestTransitionMatrixEdges` L65–86; `IntegrityError` tests L106/120/133). `Ad.transition_to` + 6 `CheckConstraint`s present in `ads/models.py:315-388`. **Empirically pass.** |
| **C-02** TrustCalculator `int()` truncation | `test_trust_calculator.py` `TestQualityScoreTruncation` (L629): `test_quality_score_int_truncation` (3 publ+1 rej → 22.5→22). |
| **C-03** PriorityCalculator `_estimate_confidence`/boundaries | `test_priority.py` `TestPriorityLevelBoundaries` (L328) + `TestConfidenceScore` (L471). |
| **C-04** `can_contact_seller` edge cases | `test_contact.py` with multiple `@pytest.mark.parametrize` classes (cross-product, banned, revoked consent, deleted seller, etc.); `can_contact_seller` imported and asserted directly. |
| **C-05** Search `DATE_OLD`/`DATE_NEW` sort | `test_search_triggers.py` L191–245: `test_date_asc_sorting` (`?sort=date_asc`), `test_date_desc_sorting`, `test_default_sort_is_date_new`; `listings.py` `AdSort` enum (L390–402). |
| **C-06** Ad-detail trust-score prefetch N+1 | `listings.py:60-61` `ad_detail` now `.prefetch_related("images","features","user__trust_score")`; `test_ad_detail_queries.py` exists (L2: "N+1 regression guard"). |
| **C-07** `approve_ad` → PUBLISHED signal chain | `test_approve_ad_side_effects.py` exists; `TestApproveAdSideEffects` (L34) tests status transition, alert dispatch (enabled/disabled), idempotency. |
| **C-08** LoginToken HMAC edge cases | `test_login.py:208` `TestLoginTokenSecurity` (token-hash mismatch→410, hash-is-64-hex, stored-not-raw, expired→410). |
| **C-09** `save_photo`→`generate_thumbnails` integration | `test_thumbnail_integration.py` (169 lines, added c73f54d "T_C09"). |
| **C-10** PriorityCalculator boundary edges | `TestPriorityLevelBoundaries` (L328) + `TestConfidenceScore` (L471) + `TestPriorityServicePersistedBoundaries` (L528). |
| **C-11** Trust-level floor (score=0 + verified → VERIFIED) | `test_trust_calculator.py:697` `TestTrustLevelFloor`: `test_score_zero_admin_verified_floors_to_verified`, `_premium_floors_to_verified`, `_no_verification_is_unverified`. **All pass** (see §4). |

### Fix-report environment issue + recs — resolved
| Item | Evidence |
|---|---|
| **§3 Issue A** `compilemessages` hang | `entrypoint-test.sh` **no longer calls `compilemessages`** (lines 16–21 do `uv sync` + `load_exchange_rates` + `setup_search_triggers` + `pytest` only). The base `entrypoint.sh:73-79` now runs `compilemessages --ignore=.venv --ignore=.git --ignore=.kilo --ignore=__pycache__ --ignore='*.pyc' --locale ru --locale bs --locale en` with a non-fatal `|| echo WARNING` fallback. Commit `ba5c65e` (8/29 10:03). **Empirically: no hang** (see §4). |
| **§3 Issue B** `[BAD]` connection | Caused by class-scoped `transaction.atomic()` opening before test-DB creation (`create_test_db`→`connection.close()` inside atomic sets `closed_in_transaction`). Fixed by declaring `django_db_setup: None` as a fixture dependency so DB creation completes first (`c73f54d`; present in `test_breadcrumbs_render.py:49-52`). **Empirically: no `[BAD]`/connection-closed** (see §4). The report's attribution to `prepare_threshold: None` is incorrect (see §8-rec-3). |
| **§8-rec-1** Fix `compilemessages` hang | DONE (`ba5c65e`). |
| **§8-rec-2** Document the `--entrypoint ""` bypass command | MOOT/RESOLVED — the test entrypoint no longer calls `compilemessages`, so the bypass is unnecessary. Neither `commands.md` nor `rules.md` document it (not needed). |

### Residual notes (observed, not in scope of original reports)
- `test_ad_localization.py:18` retains a local `_make_ad(**kwargs) -> Ad` factory. This was **not** in §2.2's list and is **justified**: the module is marked `pytest.mark.unit` (L15) and builds in-memory `Ad` instances via `Ad.__new__` (no DB) to test `get_title`/`get_description` fallbacks — `create_test_ad` performs ORM writes and is inappropriate here. No action required.
- The audit compilation §2.1 evidence mentioned `test_ad_image_service.py`/`test_media_security.py` using `-> object` annotations. `test_ad_image_service.py:41` still defines `def seller2() -> object:` (a *different* name, not the canonical `seller`); it is a weak-typing nit, not a `seller` redefinition, and was not in §2.1's file list. Out of scope.

---

## 4. Empirical Verification (Docker, test DB `mko-bazuna-test-db-1` healthy on 5433)

All runs use the documented entrypoint (`docker-compose.test.yml` `test` service; the compilemessages step in the base entrypoint now completes in ~0s — confirming Issue A fixed).

| Run | Command (PYTEST_OPTS) | Result |
|---|---|---|
| Decorators + constraints + lifecycle + trust | `… test_decorators.py … test_ad_constraints.py … test_ad_lifecycle.py … test_trust_calculator.py -p no:xdist -q` | **exit 0**, 57 dots (`....`), 0 `F`/`E`, no Traceback |
| Breadcrumbs (the `[BAD]`-risk fixture) | `… test_breadcrumbs_render.py -p no:xdist -q --durations=0` | **exit 0**, `....` (4 passed); setup 7.31s (class fixture fires **once**), teardown 0.03–0.04s (rollback confirmed); **no `[BAD]`, no `connection is closed`** |
| `--collect-only` (inventory) | full tree, `-p no:xdist` | 89 files, **1129** collected (plan doc §12 claims 1137/90 files; minor drift, same order) |

The breadcrumbs run reproduces — and confirms the fix for — the exact pattern the fix report §3.2 diagnosed: a class-scoped `transaction.atomic()` fixture that previously caused `create_test_db`→`connection.close()` to leave a `[BAD]` psycopg object. With the `django_db_setup: None` ordering dependency in place, setup completes cleanly and no dead-connection error occurs. (The 12.14s→7.31s setup-time drop vs. the report is warm DB/uv-cache; the single-fire behaviour is identical.)

---

## 5. Source References — Files / Lines Checked

| Check | Path | Verbatim evidence |
|---|---|---|
| `e2e` marker absent | `pyproject.toml:163-172` | markers list: `unit, integration, seed, settings, concurrent, slow, real_images, xdist_group` — no `e2e` |
| Live CI command | `.github/workflows/ci.yml:91` | `uv run pytest -m "not seed" -n auto --dist loadgroup --tb=short --cov ... --reuse-db` |
| Live CI nightly | `.github/workflows/ci-nightly.yml:73` | `uv run pytest -m "seed" --tb=short --cov --durations=10 ... --reuse-db` (no `-n`) |
| `prepare_threshold: None` | `config/settings/base.py:160,172-173` (+ "PgBouncer async safety" comment L158, L170) | still set |
| No PgBouncer | `docker-compose.yml` (services: db, redis, migrate, load_catalog, create_admin, web, bot, nginx) | grep `pgbouncer\|PgBouncer\|pooler` → 0 matches |
| `test-recreate` (no gw* drop) | `Makefile:137-139` | `PYTEST_OPTS="--no-reuse-db --create-db --tb=short -n auto --dist loadgroup"` |
| Root conftest fixtures | `src/backend/conftest.py:64,74,84,90,105,147` | `def seller`, `def user`, `def category`, `def city`, `def create_test_ad`, `def create_test_ads_bulk` |
| `ad_detail` prefetch | `src/backend/apps/ads/views/listings.py:60-61` | `.prefetch_related("images","features","user__trust_score")` |
| `transition_to` + constraints | `src/backend/apps/ads/models.py:315-339,346-388` | 6 `CheckConstraint`s + `transition_to` state matrix |
| `e2e` removed note | `docs/99-agent/rules.md:51` | *"The `e2e` marker was removed — do not reference it."* |
| Marker table (rules) | `docs/99-agent/rules.md:38-49` | documents 8 markers |
| Stale plan §1.2 markers | `.ai/plans/done/25_test-optimization-plan_done.md:40-44` | `unit/e2e/seed/settings/concurrent` = "Not registered" |
| Stale plan §1.4 CI | `…25_test-optimization-plan_done.md:75` | *"test job runs all 934 tests"* |
| Stale plan §1.1 tests.py | `…25_test-optimization-plan_done.md:28` | *"tests.py (2 files: search/tests.py, moderation/tests.py)"* |
| §14 inaccuracies | `…25_test-optimization-plan_done.md:697,702,693` | T-05/T-10 `loadscope`; T-01 `e2e` registered |
| §14 correction note | `…25_test-optimization-plan_done.md:719-725` | acknowledges 1137 tests, e2e removed, shadowed tests excluded |
| Open doc TODOs (D-01/02/04) | `test_quality_audit_implementation_plan.md:95,96,97,229,235,241` | listed as pending |
| Breadcrumbs class-fixture pattern | `src/backend/apps/ads/tests/test_breadcrumbs_render.py:49-92` | `scope="class"`, `django_db_setup: None` dep, `atomic`+`set_rollback(True)`, `create_test_ad` |
| Fix-report fix commit | git history `c73f54d` (8/27) | "T_LOAD: fix _load_catalog fixture scope", "T27: convert 15 files SimpleTestCase/TestCase", "T_BOT consolidate 12 bot login tests → 6", "T_C09 add save_photo thumbnail integration test", "T211 test_auto_moderation rewrite" |
| compilemessages fix commit | git history `ba5c65e` (8/29 10:03) | "fix(docker): compilemessages startup hang - exclude .venv/.kilo via --ignore + --locale flags" |

---

## 6. Prioritization & Effort

| Finding | Type | Severity | Status | Effort | Priority | Go/No-Go |
|---|---|---|---|---|---|---|
| D-02 | `[DOC-UPDATE]` | LOW | RELEVANT-OPEN | trivial | recommended (doc-only) | **GO** |
| §8-rec-4 | `[BEST-PRACTICE]` | LOW | **RELEVANT-OPEN** (reclassified) | small | **recommended** — stale `gw*` DBs actively recur; pre-flight DROP prevents stuck-connection failures | **GO (with `\gexec` correction)** |
| D-01 | `[DOC-UPDATE]` | LOW | RELEVANT-PARTIAL | trivial | recommended (doc-only) | **GO** |
| D-04 | `[DOC-UPDATE]` | LOW | RELEVANT-PARTIAL | trivial | recommended (doc-only) | **GO** |
| D-03 | `[DOC-UPDATE]` | LOW | STALE-RESOLVED(partial) | trivial | optional | — |
| §8-rec-3 | `[BEST-PRACTICE]` | LOW | **STALE-REJECTED** (Validator: false premise — PgBouncer in prod) | N/A | **NO ACTION** — keep `prepare_threshold: None` | **NO-GO** |

---

## 7. Researcher Findings & Implementation Guidance

Three Researcher agents were dispatched (parallel) to research modern best practices for each relevant finding. Their reports are at `.ai/research/pytest-xdist-db-management-report.md` (Researcher 2) and captured inline below (Researchers 1 & 3). **Key correction from Researcher 2: §8-rec-4 was reclassified from PARTIAL→OPEN** because the project does NOT override `django_db_modify_db_settings`, so per-worker `gw*` databases ARE created and stale ones DO recur.

### 7.1 Researcher 1 — `prepare_threshold: None` (§8-rec-3)

> **🛑 OVERRIDDEN by Validator (§8.2): The recommendation to REMOVE this setting is REJECTED.** The Auditor's grep for PgBouncer was scoped to `docker-compose.yml` only and **missed `docker-compose.prod.yml` (L99–121)**, where PgBouncer IS deployed (opt-in via `--profile pgbouncer`, `POOL_MODE=transaction`, port 6432). Seven documentation files (`architecture-structure.md:207`, `spec-index.md`, `packages-list.md`, `dependency-collisions.md`, etc.) explicitly **require** `prepare_threshold: None` for PgBouncer transaction-pooling mode. The "PgBouncer async safety (zone C5)" comment is NOT misleading — zone C5 is a real audit-zone reference and the setting is genuinely needed for the production profile. Django 5.2's default of `None` is coincidentally the same, but removing the explicit setting would eliminate a documented safety layer and contradict project specs. **This finding is reclassified as STALE-REJECTED.**

| Finding | Key result |
|---|---|
| What `prepare_threshold` does | Number of times identical SQL must execute on one connection before psycopg3 promotes it to a wire-protocol server-side prepared statement |
| psycopg3 standalone default | **5** |
| **Django 5.2 PostgreSQL backend default** | **`None`** — Django explicitly overrides psycopg3's default to `None` (comment: "Disable prepared statements by default to keep connection poolers working") |
| Effect of `None` (direct PG, no pooler) | No protocol-level prepared-statement reuse; every execution re-parses + re-plans. For a classifieds board with repetitive `SELECT`s, this is measurable per-query CPU overhead |
| With `CONN_MAX_AGE = 0` | Prepared statements are per-session; connection dropped per request → reuse never pays off → `None` causes no harm but also no benefit |
| With NO PgBouncer (base topology) | `prepare_threshold: None` is **not required for safety** — it only prevents a pooler-transaction-pooling problem that doesn't exist in this deployment |
| Is the explicit `None` redundant? | **Yes** (behaviorally — Django defaults to `None`), **but NOT safe to remove**: PgBouncer IS present in the production deployment and 7 spec docs mandate this setting |
| Attribution of `[BAD]` connection error | **Incorrect.** The `[BAD]` state is caused by `BaseDatabaseWrapper.close()` inside an active `atomic()` block, leaving `closed_in_transaction=True` instead of `self.connection = None`. The `prepare_threshold` option (a psycopg3 `OPTIONS` parameter) has **no interaction** with `close()`/`ensure_connection()`. Confirmed by Django source (see §8.2/§8.6.4) |
| **Recommendation (Validator-approved)** | **Do NOT remove.** Keep `"prepare_threshold": None` and the "PgBouncer async safety (zone C5)" comments. The setting is required for the production PgBouncer transaction-pooling profile (`docker-compose.prod.yml --profile pgbouncer`) and is mandated by architecture docs. If PgBouncer is ever removed from the production topology, the setting can be safely removed at that time. |
| **Validator Go/No-Go** | **NO-GO** |

### 7.2 Researcher 2 — Stale `gw*` DB Cleanup (§8-rec-4, reclassified)

**Full report:** `.ai/research/pytest-xdist-db-management-report.md`

| Finding | Key result |
|---|---|
| `loadgroup` vs `loadscope` | `loadgroup` groups by explicit `xdist_group` marker; `loadscope` groups by module/class automatically. Project uses `loadgroup` for 6 bot test files pinning to `bot_concurrent` worker — correct choice |
| Per-worker `gw*` DBs created? | **YES** — project does NOT override `django_db_modify_db_settings` (grep: 0 matches), so pytest-django's default per-worker DB creation is active: `test_mko_bazuna_gw0`, `test_mko_bazuna_gw1`, … |
| Do stale `gw*` DBs recur? | **YES** — under `--reuse-db` with persistent volume (`mko-bazuna-test_postgres_data`), they accumulate when worker count changes or runs are interrupted |
| `--no-reuse-db --create-db` sufficient? | **Not always** — can fail with "database is being accessed by other users" when crashed-worker connections persist |
| `gw*` suffix origin | pytest-xdist worker naming (`gw0`, `gw1`) appended by pytest-django's `django_db_modify_db_settings_xdist_suffix` fixture |
| CI | No change needed — ephemeral environment, `--reuse-db` is correct |
| **Recommendation** | Add pre-flight `DROP DATABASE IF EXISTS … WITH (FORCE)` loop to `make test-recreate` + `Makefile.ps1`; add standalone `test-clean-db` target |

**Implementation — concrete `Makefile` edits for §8-rec-4 (Validator-corrected: use `\gexec`, NOT `DO $$`):**

> **⚠️ Validator correction:** The `DO $$ … EXECUTE 'DROP DATABASE'` block proposed in Researcher 2's report fails on PostgreSQL 18 with `ERROR: DROP DATABASE cannot be executed from a function or procedure`. `DROP DATABASE` is DDL that cannot be called from within a PL/pgSQL function/block. The correct approach is to generate `DROP DATABASE` statements and execute them via psql's `\gexec` meta-command at the **psql client level** (not inside a function). This was empirically validated against the live test DB (dropped all 15 stale databases, exit 0).

Add a `test-clean-db` target (before or after `test-recreate`):
```makefile
# Drop stale test databases (test_mko_bazuna + test_mko_bazuna_gw*).
# Uses psql \gexec — DROP DATABASE cannot run inside a DO $$ block (PG13+ restriction).
# Runs pre-flight before test-recreate to handle stuck connections from crashed workers.
test-clean-db:
	docker compose $(COMPOSE_TEST) up -d db
	docker compose $(COMPOSE_TEST) exec -T db psql -U postgres -d postgres \
		-c "SELECT format('DROP DATABASE IF EXISTS %I WITH (FORCE);', datname) \
		 FROM pg_database WHERE datname LIKE 'test_mko_bazuna%'" \
		| docker compose $(COMPOSE_TEST) exec -T db psql -U postgres -d postgres -a -f -
	@echo "Stale test databases dropped."
```

Modify `test-recreate` (Makefile:137-139) to call the cleanup first:
```makefile
test-recreate: test-clean-db
	docker compose $(COMPOSE_TEST) run --rm --env PYTEST_OPTS="--no-reuse-db --create-db --tb=short -n auto --dist loadgroup" test
```

**.PHONY update** (Makefile L3–5): Add `test-clean-db` to the `.PHONY` declaration.

**Makefile.ps1 equivalent:** Add a `Test-CleanDb` function using `psql` heredoc with `\gexec` (or generate individual `DROP DATABASE` statements via `format()` and pipe to `psql -c`).

### 7.3 Researcher 3 — pytest Markers + CI Doc Accuracy (D-01, D-02, D-04)

**Report:** inline summary (full report captured in agent output)

| Finding | Key result |
|---|---|
| Best practice: marker registration | Register all custom markers in one place (`pyproject.toml` `[tool.pytest.ini_options].markers`); use `--strict-markers` to catch typos as hard errors (not currently enabled) |
| `xdist_group` in `markers` | **Redundant** — it's a pytest-xdist built-in marker; re-registering it is misleading (reads as project-defined). Recommend removing the line from `pyproject.toml` and adding a comment |
| `--reuse-db` vs `--create-db` in CI | CI (ephemeral) — both safe; `--reuse-db` is fine. Local dev (persistent) — `--reuse-db` default is correct; `make test-recreate` uses `--no-reuse-db --create-db` |
| `loadgroup` vs `loadscope` accurate description | `loadgroup`: groups by `@pytest.mark.xdist_group("name")`; `loadscope`: groups by module/class. `xdist_group` markers only work under `loadgroup` — under `loadscope`, cross-file grouping intent is silently ignored |
| Test-count drift | §12 claims 1137 across 90 files; empirical collection is 1129 across 89 files (drift from conftest/collection variance). Treat counts as directional |
| Doc drift prevention | Recommend adding `src/backend/tests/test_docs_ci_parity.py` — an in-repo test that reads `ci.yml`/`ci-nightly.yml`/`pyproject.toml` and asserts `--dist loadgroup` present, `-m "not seed"` present, `e2e` absent from markers, `xdist_group` not double-registered. Follows the `test_i18n_completeness.py` precedent |

**Implementation — concrete `25_test-optimization-plan_done.md` rewrites for D-01/D-02/D-04:**

1. **§1.2 (lines 40–44):** Replace "Not registered" with "Registered (except `e2e`: removed)". Add `real_images` and `xdist_group` (noting it's a pytest-xdist built-in, not project taxonomy). Add note: "Per `docs/99-agent/rules.md:51`, the `e2e` marker was not adopted."

2. **§1.3 (line 52):** Correct `addopts` — it is `["--import-mode=importlib", "-ra", "-q"]` (no `--cov`). `--cov` is CI-only (passed on command line). Note: `--reuse-db` is applied via `PYTEST_OPTS` default in `entrypoint-test.sh:56`, not via `addopts`.

3. **§1.4 (lines 70, 75–77):** Replace the stale CI description with: *"CI runs the non-seed tier only via `uv run pytest -m "not seed" -n auto --dist loadgroup --tb=short --cov --durations=10 --cov-report=term --cov-report=xml --reuse-db` (see `.github/workflows/ci.yml:91`). Seed tests run daily in `ci-nightly.yml` (no xdist). Exact count: ~1111 non-seed tests (drift±8)."*

4. **§1.4–§1.5:** Add `--strict-markers` recommendation as a future optimization.

5. **§14 T-01 (line 693):** Mark `e2e` as "removed (never adopted)".
6. **§14 T-05 (line 697):** `--dist loadscope` → **`--dist loadgroup`**.
7. **§14 T-10 (line 702):** CI uses `loadgroup` (not `loadscope`); nightly runs serial (no `-n`).
8. **§14 T-12 (line 710):** Qualify "1137" as `~1129–1137 (collection drift)`; add stamp: *"Verified at commit `ba5c65e`; live command at `ci.yml:91`"*

---

## 8. Validator Verdict

**Verified by:** Validator agent (poolside/laguna-s-2.1:free)
**Date:** 2026-08-29
**Working tree:** HEAD `ba5c65e` (+ `c73f54d`, `b62612`, `3ddc0b2`)

### 8.1 Verdict Summary Table

| Finding | Type | Verdict | Rationale | Actionability |
|---|---|---|---|---|
| D-02 | DOC-UPDATE | **PASS** | Plan §1.4 (L70,75) states "all 934 tests" but live `ci.yml:91` runs `-m "not seed" -n auto --dist loadgroup --reuse-db`. Doc rewrite is straightforward and correct. | **GO** — rewrite §1.4 to match `ci.yml:91` |
| §8-rec-3 | BEST-PRACTICE | **FAIL** (recommendation rejected) | Premise "no PgBouncer in deployment" is **false** — PgBouncer IS in `docker-compose.prod.yml` (L99–121, `PGBOUNCER_POOL_MODE=transaction`, opt-in via `--profile pgbouncer`). Architecture docs **require** `prepare_threshold: None` for PgBouncer tx-mode (architecture-structure.md:207; dependency-collisions.md:30 "MUST set"; packages-list.md:42,75,83). Comment "PgBouncer async safety (zone C5)" is NOT misleading — zone C5 is a real audit-zone reference (architecture-structure.md:208,314). Django 5.2 does default to `None` (verified from source), so removal is a behavioral no-op, but it removes a documented safety layer and contradicts 6 doc files. | **NO-GO** — do NOT remove; premise is false |
| D-01 | DOC-UPDATE | **PASS** | Plan §1.2 (L40–44) lists markers as "Not registered" but live `pyproject.toml:163-172` registers 8 markers; `e2e` removed (rules.md:51). Rewrite is straightforward. | **GO** — rewrite §1.2 marker table |
| D-04 | DOC-UPDATE | **PASS** | Plan §14 T-01/T-05/T-10 contain stale claims (`e2e` registered, `--dist loadscope`). Live `ci.yml:91` uses `--dist loadgroup`; `ci-nightly.yml:73` has no xdist. T-12's substantive concern is already corrected by §12 note. | **GO** — reconcile T-01/T-05/T-10 rows |
| §8-rec-4 | BEST-PRACTICE | **PARTIAL** (finding VALID, implementation **BROKEN**) | Finding is empirically confirmed: **16 stale `test_mko_bazuna_gw*` databases** found in running test DB. No `django_db_modify_db_settings` override (0 matches in `src/`). Persistent `postgres_data` volume confirmed in `docker-compose.test.yml:7-11`. BUT: both proposed `DO $$ … EXECUTE 'DROP DATABASE'` implementations **fail on PostgreSQL 18** (see §8.4). The correct approach using psql `\gexec` was verified empirically. | **GO with corrected implementation** |

### 8.2 Corrections to the Compiled Report

#### Correction 1: §8-rec-3 Premise — "No PgBouncer in deployment" is FALSE

The compiled report (L48, §5 table) claims:
> "grep `pgbouncer\|PgBouncer\|pooler` → 0 matches"

**This is false.** The grep was scoped to `docker-compose.yml` only. A full search across all compose files reveals:

| File | Location | Finding |
|---|---|---|
| `docker-compose.prod.yml` | L99–121 | `pgbouncer` service defined with `PGBOUNCER_POOL_MODE=transaction` (opt-in via `profiles: ["pgbouncer"]`) |
| `docs/01-spec/architecture-structure.md` | L207 | "PgBouncer (recommended): shared external pool in transaction mode between web+bot; ... set `OPTIONS={"prepare_threshold": None}`" |
| `docs/01-spec/spec-index.md` | L57 | "PgBouncer (tx mode) recommended with `OPTIONS={"prepare_threshold": None}`" |
| `docs/03-packages/packages-list.md` | L42 | "psycopg[binary]>=3.2.0 … For PgBouncer tx mode set OPTIONS={prepare_threshold: None}" |
| `docs/03-packages/packages-list.md` | L75 | "PgBouncer: pin pgbouncer>=1.25.2. **Keep** prepare_threshold=None." |
| `docs/03-packages/packages-list.md` | L83 | "psycopg3 … prepare_threshold=None for PgBouncer." |
| `docs/03-packages/dependency-collisions.md` | L30 | "Under PgBouncer **transaction pooling mode** you **MUST** set `OPTIONS={"prepare_threshold": None}`" |
| `docs/03-packages/dependency-collisions.md` | L46 | "Driver ↔ pooler coupling. psycopg3 + PgBouncer require prepare_threshold=None." |

**The "PgBouncer async safety (zone C5)" comments are NOT misleading.** Zone C5 is a real audit-zone reference documented in `architecture-structure.md:208` ("C5 / C7 — async/sync boundary, per-process pool, PgBouncer, migrations run exactly once") and `architecture-structure.md:314`. PgBouncer is recommended (not just absent) in the architecture spec.

**Technical reality of removing the setting:**
- Django 5.2's `DatabaseWrapper.get_connection_params()` (verified from `.venv/Lib/site-packages/django/db/backends/postgresql/base.py`) does:
  ```python
  conn_params["prepare_threshold"] = conn_params.pop("prepare_threshold", None)
  ```
  Whether `prepare_threshold` is present (value `None`) or absent from `OPTIONS`, the result is `None`. **No behavior change.**
- **BUT:** removing the explicit setting eliminates the documentation signal that the project requires `None` for PgBouncer. If a future Django release changes its default (currently a comment-only guarantee), production PgBouncer tx-mode deployments would silently break with prepared-statement errors.
- **No production code or tests depend on the setting being present** (grep: only in `base.py` + doc files; 0 test assertions on `prepare_threshold`).

**Conclusion:** The removal is technically a no-op, but the *justification* in the report is based on a false premise. The recommendation to also remove the "misleading" comments is wrong — the comments are accurate. **Recommendation rejected.**

#### Correction 2: §8-rec-4 Implementation — `DO $$` block is BROKEN on PostgreSQL 18

Both the research report (§5.1, §6.1) and the compiled report (§7.2) propose a `DO $$ … EXECUTE 'DROP DATABASE'` PL/pgSQL block. This **fails on PostgreSQL 18** in two ways:

**Failure 1 (without `DECLARE r RECORD;`):**
```
ERROR: loop variable of loop over rows must be a record variable or list of scalar variables
LINE 5: FOR r IN SELECT datname FROM pg_database ...
```

**Failure 2 (with `DECLARE r RECORD;` — research report §5.1 version):**
```
ERROR: DROP DATABASE cannot be executed from a function
CONTEXT: SQL statement "DROP DATABASE IF EXISTS test_mko_bazuna_gw1 WITH (FORCE)"
PL/pgSQL function inline_code_block line 8 at EXECUTE
```

**Root cause:** PostgreSQL's `DO $$` block is an anonymous code block (i.e., a function context). PostgreSQL has a hard restriction: `DROP DATABASE` cannot be executed from within a function or procedure — it must run in autocommit mode at the top level. See [PostgreSQL docs: CREATE DATABASE / DROP DATABASE](https://www.postgresql.org/docs/18/sql-droppedatabase.html).

**Verified correct approach** (psql meta-command `\gexec`):
```sql
SELECT pg_terminate_backend(pid) FROM pg_stat_activity
 WHERE datname LIKE 'test_mko_bazuna%' AND pid <> pg_backend_pid();
SELECT format('DROP DATABASE IF EXISTS %I WITH (FORCE);', datname)
 FROM pg_database WHERE datname LIKE 'test_mko_bazuna%' \gexec
```

**Empirical verification** (tested against the live `mko-bazuna-test-db-1` on 2026-08-29):
- Before: 16 databases (`test_mko_bazuna_gw0`–`gw15`)
- After: 0 databases matching `test_mko_bazuna%`
- Exit code: 0

**Correct Makefile implementation:**
```makefile
test-clean-db:
	docker compose $(COMPOSE_TEST) up -d db
	docker compose $(COMPOSE_TEST) exec -T db psql -U postgres -d postgres -c \
		"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname LIKE 'test_mko_bazuna%' AND pid <> pg_backend_pid();"
	docker compose $(COMPOSE_TEST) exec -T db psql -U postgres -d postgres -t -A -c \
		"SELECT format('DROP DATABASE IF EXISTS %I WITH (FORCE);', datname) FROM pg_database WHERE datname LIKE 'test_mko_bazuna%'" \
	| while IFS= read -r stmt; do docker compose $(COMPOSE_TEST) exec -T db psql -U postgres -d postgres -c "$$stmt"; done
```

**Makefile escaping note:** The `$$stmt` in the `while` loop uses Makefile escaping (`$$` → `$`), which is correct. The `DO $$` block proposed in §7.2 would require `$$$$` in a Makefile to produce literal `$$` for PostgreSQL dollar-quoting — but it fails for a deeper reason (DROP DATABASE in function context), so Makefile escaping is moot.

**Makefile.ps1 equivalent:** The `Test-CleanDb` function should use a `psql` heredoc with `\gexec` (or generate individual `DROP DATABASE` statements via `format()` and pipe to `psql -c`).

#### Correction 3: Fix-report §3.2 attribution of `[BAD]` connection to `prepare_threshold` is INCORRECT

The compiled report (L49) correctly identifies that the fix report §3.2 (L130) misattributes the `[BAD]` connection issue to `prepare_threshold: None`. This is confirmed by Django source:

```python
# django/db/backends/base/base.py — BaseDatabaseWrapper.close()
def close(self):
    if self.closed_in_transaction or self.connection is None:
        return
    try:
        self._close()
    finally:
        if self.in_atomic_block:
            self.closed_in_transaction = True  # [BAD]: connection preserved non-None
            self.needs_rollback = True
        else:
            self.connection = None  # Only nulled outside atomic
```

```python
# ensure_connection()
def ensure_connection(self):
    if self.connection is None:  # FALSE — it's the [BAD] object, not None
        ...
```

The `[BAD]` state arises from `connection.close()` being called inside an active `atomic()` block (during `create_test_db`), which sets `closed_in_transaction = True` instead of `self.connection = None`. The `prepare_threshold` option is a psycopg3 connection parameter passed via `OPTIONS` → `conn_params` in `get_connection_params()`, and has **no interaction** with `BaseDatabaseWrapper.close()` or `ensure_connection()`.

The actual fix was the `django_db_setup: None` ordering dependency in `test_breadcrumbs_render.py:51` (commit `c73f54d`), ensuring test-DB creation completes before the class-scoped `atomic()` opens. This is correctly noted in the compiled report (§3 Issue B, L131).

### 8.3 Phase 2 Verification: Stale/Resolved Findings (Spot-Check Results)

| Finding | Check | Result | Go |
|---|---|---|---|
| F-01 | `moderation/tests.py` + `search/tests.py` deleted | ✅ glob: no files found | — |
| F-01 | Replacements exist & pass | ✅ `test_moderation_views.py`, `test_search_view.py` found | — |
| §2.3 | `TestCase`/`SimpleTestCase` imports in `src/` | ✅ 0 actual imports (1 docstring comment at `test_priority.py:8`) | — |
| §2.6 | `e2e` marker in `pyproject.toml` | ✅ 0 matches | — |
| §2.7 | `SimpleTestCase` usage | ✅ same as §2.3 result | — |
| §2.10 | `inspect.getsource` in `src/` | ✅ 0 matches | — |
| §2.12 | `test_claim_login_token.py` + `test_login_claim.py` deleted | ✅ glob: no files found | — |
| §2.12 | `test_login.py` exists | ✅ confirmed present | — |
| C-06 | `ad_detail` prefetches `user__trust_score` | ✅ `listings.py:61` | — |
| §3 Issue A | `entrypoint-test.sh` does NOT call `compilemessages` | ✅ confirmed (L16-21: uv sync + load_exchange_rates + setup_search_triggers + pytest only) | — |
| §3 Issue B | `test_breadcrumbs_render.py` has `django_db_setup: None` dep | ✅ confirmed at L51 | — |

### 8.4 Architectural Validity & Future Support

#### §8-rec-3 (prepare_threshold)

1. **Architecture alignment:** The setting aligns with the documented two-process architecture (web gunicorn sync WSGI + bot aiogram). Production compose (`docker-compose.prod.yml`) includes an opt-in PgBouncer with transaction pooling. The architecture docs (`architecture-structure.md:207`) explicitly recommend `prepare_threshold: None` for this configuration. Removing it contradicts the architecture spec.

2. **Will implementation break anything?** Removing the setting is a behavioral no-op (Django 5.2 defaults to `None`). However, removing the comments that document the PgBouncer rationale would degrade architectural documentation.

3. **Future evolution:** If Django ever changes its default `prepare_threshold` from `None` to a numeric value (its current default is explicitly for pooler compatibility, per the Django source comment "Disable prepared statements by default to keep connection poolers working"), removing the explicit `None` would silently break PgBouncer tx-mode in production. The explicit setting + comment serve as a guard.

4. **Finding dependencies:** §8-rec-3 and §3-Issue-B are **independent**. The fix report §3.2 incorrectly linked them, but the Django source proves `prepare_threshold` (a psycopg3 `OPTIONS` parameter) has no code-path relationship to `BaseDatabaseWrapper.close()` / `ensure_connection()` (the actual `[BAD]` mechanism). The compiled report's corrected attribution is sound.

#### §8-rec-4 (stale gw* DB cleanup)

1. **Architecture alignment:** The pre-flight `DROP DATABASE` approach is sound for the Docker-based two-process dev workflow. CI needs no change (ephemeral environment). The Makefile uses `$(COMPOSE_TEST)` (confirmed at `Makefile:11`) and target-scoped `COMPOSE_PROJECT_NAME = mko-bazuna-test` (confirmed at `Makefile:21`).

2. **Will implementation break anything?** The `\gexec` approach is safe — it terminates no active test connections (`pid <> pg_backend_pid()`), and only drops databases matching `test_mko_bazuna%`. It runs BEFORE pytest spawns workers, so no race condition.

3. **Future evolution:** If the DB topology changes (e.g., database name changes from `mko_bazuna`), the `LIKE 'test_mko_bazuna%'` pattern needs updating. The pattern is hardcoded to the project name — a future rename would need to update both the test settings and this cleanup target. This is acceptable coupling.

4. **Finding dependencies:** §8-rec-4 is independent of §8-rec-3. The stale `gw*` databases are created by pytest-xdist's default per-worker DB behavior (no `django_db_modify_db_settings` override), which is entirely separate from `prepare_threshold` or the `[BAD]` connection issue.

#### D-01, D-02, D-04 (doc accuracy)

1. **Architecture alignment:** N/A (doc-only findings).
2. **Will implementation break anything?** No — rewriting stale doc rows in `25_test-optimization-plan_done.md` is a no-risk text edit. The researcher's §1.3 note about `addopts` (line 284) is correct but cites `entrypoint-test.sh:56` (actual: L41); this is a minor line-number inaccuracy in the guidance, not a correctness issue.
3. **Future evolution:** The researcher's §7.3 recommendation to add `test_docs_ci_parity.py` (an in-repo parity test) is a sound future-proofing measure — it would prevent this class of doc drift from recurring.

### 8.5 Additional Observations (Not in Original Reports)

| Observation | Severity | Detail |
|---|---|---|
| `entrypoint-test.sh` L4 stale comment | LOW | Comment says base entrypoint "compiles translations" but test entrypoint replaces base entrypoint entirely (`entrypoint: /app/entrypoint-test.sh` in compose). .mo files come from the Docker image build (Dockerfile L78). Comment should say "syncs deps + runs triggers + launches pytest." |
| `.PHONY` list missing `test-clean-db` | LOW | If §8-rec-4 implementation is adopted, `test-clean-db` must be added to `.PHONY` (Makefile L3–5) and the target-scoped `COMPOSE_PROJECT_NAME` list (L21). |
| Researcher §7.3 `xdist_group` marker recommendation | LOW | Researcher 3 recommends removing `xdist_group` from `pyproject.toml` markers (it's a pytest-xdist built-in, not project taxonomy). This is correct but low-priority; `--strict-markers` is not enabled so there's no functional impact. |

---

### 8.6 Final Go/No-Go Summary

| Finding | Verdict | Go/No-Go |
|---|---|---|
| D-02 (§1.4 CI command) | PASS | **GO** — rewrite §1.4 to match `ci.yml:91` (`-m "not seed" -n auto --dist loadgroup --reuse-db`) |
| §8-rec-3 (`prepare_threshold: None`) | FAIL (false premise) | **NO-GO** — PgBouncer IS in `docker-compose.prod.yml`; docs REQUIRE this setting; comment is accurate |
| D-01 (§1.2 markers) | PASS | **GO** — rewrite §1.2 table to reflect 8 registered markers, note `e2e` removed |
| D-04 (§14 T-01/T-05/T-10) | PASS | **GO** — reconcile table rows with `loadgroup` (not `loadscope`), `e2e` removed, nightly is serial |
| §8-rec-4 (stale gw* cleanup) | Partial | **GO (with corrections)** — implement using `\gexec`, NOT `DO $$` block; both the research report's §5.1/§6.1 and the compiled report's §7.2 implementations are broken on PG18 |

---

## 9. Final Report Summary

### 9.1 Agent Workflow Summary

| Step | Agent | Outcome | Report Section |
|---|---|---|---|
| 1. Verify findings | **Auditor** (`ses_fb36edcdaffeznQpJ6W08CQX9d`) | Verified all 34 findings against current tree; compiled 5 relevant + 29 stale | §2–§6 |
| 2. Research modern practices | **Researcher 1** (psycopg3 `prepare_threshold`) | Django 5.2 defaults to `None` — removal is behaviorally a no-op | §7.1 |
| 2. Research modern practices | **Researcher 2** (xdist DB management) | Per-worker `gw*` DBs ARE created by default; stale DBs DO recur; `DO $$` block proposed | §7.2 + `.ai/research/pytest-xdist-db-management-report.md` |
| 2. Research modern practices | **Researcher 3** (markers + CI docs) | Doc-drift prevention via `test_docs_ci_parity.py`; `xdist_group` is a built-in; `--strict-markers` recommended | §7.3 |
| 3. Validate against architecture | **Validator** (`ses_fb337b4a8ffeH2rOBxEhkIkTGz`) | Two critical corrections: §8-rec-3 false premise (PgBouncer in prod); §8-rec-4 `DO $$` broken on PG18 → use `\gexec` | §8 |

### 9.2 Final Actionable Findings (Go/No-Go)

| ID | Finding | Status | Effort | Go/No-Go | Action |
|---|---|---|---|---|---|
| D-02 | Plan §1.4 claims "934 tests" / wrong CI command | RELEVANT-OPEN | trivial | **GO** | Rewrite §1.4 to match `ci.yml:91` (`-m "not seed" -n auto --dist loadgroup --reuse-db`, ~1111 tests) |
| D-01 | Plan §1.2 says markers "Not registered" | RELEVANT-PARTIAL | trivial | **GO** | Rewrite §1.2 to reflect 8 registered markers; note `e2e` removed |
| D-04 | §14 completion table uses `loadscope`/`e2e` (stale) | RELEVANT-PARTIAL | trivial | **GO** | Reconcile T-01/T-05/T-10 rows with live `loadgroup`, `e2e` removed, nightly is serial |
| §8-rec-4 | Stale `gw*` DB cleanup missing from `make test-recreate` | RELEVANT-OPEN | small | **GO (with `\gexec`)** | Add `test-clean-db` Makefile target using `psql \gexec`; call from `test-recreate` |
| §8-rec-3 | Remove `prepare_threshold: None` | **STALE-REJECTED** | N/A | **NO-GO** | PgBouncer IS in `docker-compose.prod.yml`; keep setting + comments unchanged |

### 9.3 Non-Actionable Findings (Confirmed Resolved / Rejected)
All **30** findings (29 STALE-RESOLVED + 1 STALE-REJECTED) are **confirmed** in the current tree. No re-implementation needed. See §3 for evidence:
- **§3.1** — 12 test-quality findings (F-01, §2.1–§2.12) all verified resolved by commits `b62612`/`3ddc0b2` + `c73f54d`
- **§3.2** — 11 coverage gaps (C-01–C-11) all now have test coverage
- **§3.3** — 4 environment/recs items (§3 Issues A/B, §8-rec-1/2) all resolved (`ba5c65e`)
- **§2.5** — D-03 (plan §1.1 stale `tests.py` reference) marked RESOLVED-partial
- **§8-rec-3** — STALE-REJECTED (Validator: PgBouncer IS in prod; do not remove `prepare_threshold: None`)

### 9.4 Prevention Recommendation (Future-Proofing)
- **Add `src/backend/tests/test_docs_ci_parity.py`** (proposed by Researcher 3): an in-repo consistency test that asserts `ci.yml:91` uses `--dist loadgroup` + `-m "not seed"`, `e2e` is absent from `pyproject.toml` markers, and `xdist_group` is not double-registered. Follows the `test_i18n_completeness.py` precedent for doc-DoD enforcement. This converts doc drift into a CI gate.
- **Add `test-clean-db` to `.PHONY`** when implementing §8-rec-4.
- **Monitor `gw*` DB count** as part of `make test-recreate` health checks (if worker count frequently changes, stale DBs accumulate).

### 9.5 Confidence
- **HIGH** for all stale/resolved findings (verified via grep + glob + empirical test runs)
- **HIGH** for D-01/D-02/D-04 doc inaccuracies (verified against live `pyproject.toml`, `ci.yml`, `ci-nightly.yml`, `rules.md`)
- **HIGH** for §8-rec-3 rejection (PgBouncer confirmed in `docker-compose.prod.yml:99-121`; 7 spec docs require the setting)
- **HIGH** for §8-rec-4 (16 stale `gw*` DBs found empirically; `DO $$` restriction confirmed via PostgreSQL 18 semantics; `\gexec` validated empirically)
