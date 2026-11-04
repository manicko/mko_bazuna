# Raw per-block findings — Test Quality Audit 2026-11-01

Consumed by the auditor agent to synthesize `.ai/audit/tests/audit_report_1.md`.
Validation (Step 3) was intentionally SKIPPED — every item below carries the per-block
auditor's *preliminary* classification only. Treat all as UNVALIDATED.

Environment: PASS (`mko-bazuna-test-db-1` healthy, 0 collection errors).
Scale: 295 test files, ~3,718 test functions (4027 collected incl. parametrization).
Prior audit: `docs/99-agent/test-audit-master-report.md` (2026-09-17) — partly stale; each
block reports which prior items are already resolved.

---

## Block 1 — Core: scheduler, advisory locks & migrations

### RC-1 (low-med, 2 tests) — scheduler subprocess assertion never checks argv
- `apps/core/tests/test_scheduler.py:731-754` (`TestRunCommandSubprocess`), `test_scheduler_error_handling.py:75-217` patch `apps.core.utils.scheduler.subprocess.run`; `mock_run.assert_called_once()` never inspects `call_args[0][0]` (the argv). Production: `scheduler.py:192-216`.
- CLASS: TEST-UPDATE. Assert argv shape once; delete the duplicated exit-code passthrough tests.

### RC-2 (med, ~6 tests) — module-global `_stop_event` leakage under pytest-randomly
- `test_scheduler.py:511-521` is the only class with a `_reset_stop_event` autouse guard; `TestGracefulShutdown` (436-460), `test_scheduler_error_handling.py:668-706`, `744-822` set/clear the global manually. Production `scheduler.py:85`.
- CLASS: BEST-PRACTICE. Hoist the reset fixture into `apps/core/tests/conftest.py`.

### RC-3 (low, 3 tests) — substring assertions on `docker/entrypoint-scheduler.sh`
- `test_scheduler_wiring.py:30-45` asserts `"exec" in content` etc.; satisfied by a comment. Production contract = `exec /opt/venv/bin/python -m apps.core.utils.scheduler`.
- CLASS: TEST-UPDATE. Assert the exact launch line.

### RC-4 (low, 3 tests) — tautological/discoverability command tests
- `test_scheduler.py:659-667` `test_all_scheduled_commands_exist` passes the shipped lists back to `_validate_commands`. `test_partial_missing_raises_with_name` (694-701) is a weaker clone of `test_missing_command_raises` (679-686).
- CLASS: TEST-DELETE (`test_partial_missing_raises_with_name`); TEST-REWRITE (`test_all_scheduled_commands_exist` → assert lists non-empty and disjoint).

### RC-5 (med, 2 tests) — subprocess migration test conflates setup failure with migration drift
- `test_migrations.py:70-96,99-145`; failure surface opaque (import error → same "Migration idempotency check failed").
- CLASS: BEST-PRACTICE. Assert no `Traceback`/`ImproperlyConfigured` in stderr before interpreting exit code.

### RC-6 (med, missing assertion over 7 tests) — the documented "never call bootstrap_reference_data on the test path" deviation is unguarded
- Prose only: `conftest.py:118-132,148-156`, `docker/entrypoint-test.sh:18-20`, `bootstrap_reference_data.py:21-26`. No test asserts absence.
- CLASS: TEST-REWRITE (add static assertion).

### RC-7 (low, 4 tests) — migrate_locked step tuples pinned, `TestDefaultSettings` stubs `_build_steps`
- `test_migrate_locked.py:32-36,56-62,154-168`. Mostly acceptable.
- CLASS: BEST-PRACTICE (minor).

### RC-8 (low, 1 test) — squash renderer test counts `migrations.RunSQL` occurrences and exact indentation
- `test_squash_rehydrate_runsql.py:107-114` (`2 * len(DDL_STATEMENTS)`, `endswith("    ]")`). `ast.parse` already validates syntax.
- CLASS: TEST-UPDATE. Keep `repr(sql) in source` + `ast.parse`; drop count and indent checks.

### RC-9 (low, 2 comments) — stale "9 hourly / 2 daily" comments (now 10 hourly / 3 daily)
- `test_scheduler.py:327,637-638`; `test_scheduler_error_handling.py:245`.
- CLASS: DOC-UPDATE.

### Already resolved
- Prior A4 AST/regex lock-id parsing: now scoped (only 3 IDs pinned + enum alias cross-check at `test_advisory_lock_ids.py:87-117`; AST test is `slow`).
- Prior A3 cross-block imports: not present in Block 1.
- "Exact `==` pinned scheduler command counts": NOT found — all count assertions are relative.

### Missing coverage
| Behavior | Source | Why critical | Location |
|---|---|---|---|
| entrypoint-test/conftest must NOT invoke `bootstrap_reference_data` | `conftest.py:118-132`, `entrypoint-test.sh:18-20` | Unguarded deviation, silently seeds wrong DB | `test_bootstrap_reference_data.py` or `test_docs_ci_parity.py` |
| `run_scheduler` handles `read_last_daily()` failure → re-run (never skip) | `scheduler.py:512` | Loop-level invariant untested | `test_scheduler_daily_marker.py` |
| `SCHEDULER_HEALTH_STALE_SECONDS` staleness arithmetic vs liveness-file mtime | `scheduler.py:34-39`, `docs/ops/docker-deployment.md:861-869` | Only the compose env value is asserted | `test_scheduler_error_handling.py` |
| `migrate_locked.main()` runs all steps after a non-zero exit; returns FIRST code | `migrate_locked.py:74-77,94-115` | Only the timeout variant tested | `test_migrate_locked.py` |
| `squash_rehydrate_runsql` "Could not locate operations" path | `squash_rehydrate_runsql.py:94-99` | Untested error branch | `test_squash_rehydrate_runsql.py` |
| `_stop_aware_dispatch` pass-through exit code | `scheduler.py:430-436` | Only stopped path asserted | `test_scheduler_error_handling.py` |

### Duplicates
- `test_scheduler.py:762-799` `TestDispatchIsolation` ≡ `test_scheduler_error_handling.py:256-315` `TestDispatchIsolation` (keep the latter, delete the former).
- `test_scheduler_error_handling.py:145-168` ≡ `test_scheduler.py:731-754`.
- `test_scheduler.py:105-118` vs `126-142` (same `now.hour >= daily_hour_utc` predicate).
- `test_scheduler_wiring.py:30-33` vs `35-40`.

### Uncertain
- `test_migrations.py` execution reality not verified (slow-marked, not run).
- `_stop_event` leakage mechanism identified statically, not reproduced.

---

## Block 2 — Core: middleware, context processors & templatetags

### RC-1 (med, ~10) — `header_context` exposes `bot_username`; contract untested AND mis-documented
- `context_processors.py:107` returns `bot_username`; `docs/01-spec/architecture-structure.md:191` says it does NOT. `test_context_processors.py:69-72` asserts neither `bot_username` nor `catalog_js_labels`.
- CLASS: DOC-UPDATE + TEST-REWRITE.

### RC-2 (med, 1 test / 8 templates) — consent-banner guard test uses a stale hardcoded template list
- `test_templates.py:29-37,46` lists 7 templates; `privacy.html:167-169` already carries the guard but is absent → already unprotected by the test (PII-009 safety guard).
- CLASS: TEST-REWRITE. Derive the template set by globbing for the include.

### RC-3 (med, ~17) — source-text assertions on templates/CSS instead of behavior
- `test_rtl_obfuscation.py:211-216,219-232,240-280` (exact `rtl_count == 1`), `test_footer_contact_link.py:73-81` (index arithmetic). Prior audit A4 — still open.
- CLASS: TEST-REWRITE.

### RC-4 (med, 4 files) — middleware ORDER only asserted as membership, never position
- `test_db_lock_timeout_boundary.py:217-223` asserts `in settings.MIDDLEWARE`; language/preferred-city tests hand-simulate order (`test_language_middleware.py:33-44,440-441`). Real order: `config/settings/base.py:341-357`.
- CLASS: TEST-UPDATE. Assert `LanguagePreMiddleware` after `AuthenticationMiddleware`; `DbLockTimeoutMiddleware` before view dispatch.

### RC-5 (med, 2) — N+1 guard uses a SQL-text keyword heuristic; `<= 1` passes vacuously
- `test_header_child_queries.py:44-56,69,84`; production `context_processors.py:119-121` (inlined EXISTS → counter 0).
- CLASS: TEST-REWRITE. Assert exact constant (0) + keep the scaling comparison.

### RC-6 (low, ~6) — near-duplicate language-cookie cases
- `test_language_middleware.py:162-181` ⊂ `:184-200` (same table); `:83-88` ≡ `:141-146`.
- CLASS: TEST-DELETE (subset test).

### RC-7 (low, ~9) — `unit`-marked tests trigger a real DB read via `get_bot_username`
- `test_context_processors.py:18,63-72`; `context_processors.py:107`; fails open to `"bazuna_bot"`.
- CLASS: TEST-UPDATE (patch `get_bot_username`).

### RC-8 (low, 1) — dead `mock_city` return value in test helper
- `test_context_processors.py:63-72`.
- CLASS: BEST-PRACTICE.

### RC-9 (low, 1 docstring) — `test_footer_contact_link.py:4-20` still describes the removed `js_verified` gate
- CLASS: DOC-UPDATE.

### Already resolved
- Prior A1 (`can_contact`/`localized_content`/`dict_tags` zero coverage): now ~40 tests in `test_core_tags.py`.

### Missing coverage
| Behavior | Source | Why critical | Location |
|---|---|---|---|
| `header_context` exposes `bot_username` + `catalog_js_labels` | `context_processors.py:107,128-136` | Header CTA/JS break silently | `test_context_processors.py` |
| `LanguagePreMiddleware` position vs `AuthenticationMiddleware` | `config/settings/base.py:341-357` | Reorder reintroduces LocaleMiddleware-clobber class | `test_language_middleware.py` |
| `DbLockTimeoutMiddleware` position | `base.py:347`, `middleware/db_lock_timeout.py:9-15` | Only membership asserted | `test_db_lock_timeout_boundary.py` |
| `catalog_js_labels` JSON validity/escaping | `context_processors.py:128-136` | Malformed JSON breaks header JS | `test_context_processors.py` |
| Preferred-city cookie writer/reader consistency | `middleware/preferred_city.py:14-16,92-99` | Nothing verifies writer matches reader | `test_preferred_city_middleware.py` |
| `?lang`-less render under `js_verified=False` with no cookie | `telegram_tags.py:96`, `contact-us.md:187-188` | CR-11 end-to-end unverified | `test_js_execution.py` |

### Duplicates
- `test_cookie_non_canonical_resolves_to_supported_locale` ⊂ `test_cookie_membership_holds_for_every_case_in_table`.
- `test_lang_param_valid_values` ⟷ `test_cookie_valid_values`.
- `test_footer_contact_link.py:84-89` ⟷ `:144-165`.
- `test_rtl_obfuscation.py:54-64` ⟷ `67-76` ⟷ `79-86` (three views of one expression).

### Uncertain
- `_child_existence_queries` actual count not instrumented.
- RTL obfuscation IS a live requirement (`contact-us.md:104-109`) — not obsolete.

---

## Block 3 — Core: site config, cache, prompts & support

### RC-1 (HIGH, 2 claimed / 0 real) — support-contact cache read is unguarded → documented fail-open is FALSE
- `services/support.py:35` calls `get_cached_support_contacts()` outside the `try`; `utils/cache.py:290` returns `cache.get()` directly (not `cache_get_or_none`). Docstring `support.py:6,27` promises fail-open on DB **or cache** failure. `test_support_cache.py:145,246` only patch the DB path.
- Note: this is a candidate PRODUCTION defect surfaced by the audit — do not fix production during audit.
- CLASS: TEST-REWRITE (add cache-outage test) + DOC-UPDATE / production decision needed.

### RC-2 (med, ~6) — contact rate-limit tests hardcode 60/600s while the spec says 5/10min
- `test_contact_rate_limit.py:38-47`; production `apps/core/enums.py:70,83` (60/600); spec `docs/01-spec/contact-us.md:140` (5/10 min). Tests never reference `RateLimitBudget.DEEP_LINK_RENDER`.
- CLASS: TEST-UPDATE + DOC-UPDATE (spec/code reconciliation required).

### RC-3 (med, 3) — support cache tests assert key deletion and a mock-call instead of observable freshness
- `test_support_cache.py:185,204,223` (`is None`), `:134` (`mock_filter.assert_not_called()`).
- CLASS: BEST-PRACTICE.

### RC-4 (low-med, 8) — admin metadata exact-list equality; permission tests on bare `MagicMock` request
- `test_support_admin.py:53,60,67,74,114,121,152,177`; `:180-195`.
- CLASS: BEST-PRACTICE.

### RC-5 (low, 11) — `test_problem_response.py` is strong (asserts type/title/status/detail + content-type); minor redundancy
- `:69-70` redundant `isinstance`; `instance` correctly absent. `title is gettext_lazy` → locale-sensitive.
- CLASS: BEST-PRACTICE.

### RC-6 (low, 3-4) — RFC 9457 `title` translation half is unasserted (`type`-not-translated is pinned at `:145`)
- CLASS: BEST-PRACTICE + missing coverage.

### RC-7 (low, 3) — `test_login_issue_template.py` asserts minified-JS source substrings
- `:33-44,53-60`.
- CLASS: BEST-PRACTICE (assert rendered element state instead).

### RC-8 (low, 1) — `TestConsumerAgreement` reaches into 4 other apps and pins literal cache keys
- `test_client_ip.py:289-326` (`"login_rl:8.8.8.8"`). Proxy-trust contract itself well covered (`:59-83,115-126,390-407`).
- CLASS: BEST-PRACTICE.

### RC-9 (low, 3) — `transaction=True` analytics tests lack `xdist_group`; hardcoded ids
- `test_analytics_service.py:144,208,142,150`.
- CLASS: BEST-PRACTICE.

### RC-10 (low, 2) — `test_sanitize.py` "warns once" unasserted; module-global warning state not reset
- `test_sanitize.py:84-91`; production `utils/sanitize.py:222-258`.
- CLASS: TEST-REWRITE.

### Already resolved
- A1: `translate_text`/circuit breaker, async wrappers, `record_contact_initiated` now covered.
- A2 (contact-rate-limit vs login-template conflation): partially resolved.
- A2 (`TestCanContactSeller` ⊂ combinatorial): still present (see duplicates).

### Missing coverage
| Behavior | Source | Why critical | Location |
|---|---|---|---|
| Support cache-outage fail-open (R-SN-05) | `services/support.py:6,27`; `utils/cache.py:290` | Documented contract false today | `test_support_cache.py` |
| RFC 9457 `title` translates while `type` does not | `utils/problem.py:58-69,100-122` | Half the contract unpinned | `test_problem_response.py` |
| `mask_telegram_id` warns exactly once on empty key | `utils/sanitize.py:251-257` | Claimed, unasserted | `test_sanitize.py` |
| `bump_version_key` `timeout=None` durability invariant | `utils/cache.py:102-137` | No test in block | `test_cache_utils.py` |
| Contact 429 body shape (problem+json) | `views.py:82-84`, `rate_limit_response.py` | Only status asserted | `test_contact_rate_limit.py` |
| `repair_bot_username` advisory-lock idempotency | `repair_bot_username.py:79-80` | Lock never exercised | `test_repair_bot_username_command.py` |
| Web contact budget == spec (5/10min) | `contact-us.md:140` vs `enums.py:70,83` | Spec/code divergence | reconciliation |

### Duplicates
- `test_contact.py` triple-covers the same six R2 conditions (`TestCheckSellerContactable:78-139`, `TestContactCombinatorial:239-266`, `TestGetSellerForContactIntegration:142-190`).
- `test_site_config.py:69-89,130-159` ≡ `test_site_config_bot_username.py:48-68,97-127`; third copy in `test_site_config_cache_failure.py:157-170`.
- `test_contact_response.py:38-44` ⊂ `test_contact.py:67-75`.

### Uncertain
- xdist flake risk of `transaction=True` analytics counts: inferred.
- Which side of the 60/600 vs 5/10min divergence is authoritative: unknown.

---

## Block 4 — Core: admin entrypoints, sweeps & CI/observability

### RC-1 (HIGH, ~8 files) — destructive sweeps test the retention boundary only at wide margins
- e.g. `test_sweep_delete.py` -200d vs -30d around a 60d window; `purge_deleted_ads` -200/-30 around 120d; `sweep_drafts` -90min/-5min around 30min. Production predicates are strict `__lt` (`delete_sweep.py:46`, `purge_deleted_ads.py:43`, `sweep_drafts.py:46`).
- No test places a row at / ±1s around the cutoff → `__lt`→`__lte` regression is invisible.
- CLASS: TEST-UPDATE (parametrized boundary test per sweep).

### RC-2 (med, ~6) — no idempotency assertion on re-run for most sweeps
- Only `test_sweep_archive.py::test_idempotent_on_rerun` and `test_create_admin_user.py::test_idempotent_on_rerun`. Missing for delete_sweep, purge_deleted/failed/rejected, consent_hard_delete, cleanup_login_tokens.
- CLASS: TEST-UPDATE.

### RC-3 (med, ~10) — `test_ci_security.py` mixes parsed YAML checks with raw-substring checks
- Parsed helpers already exist (`_ci_document`, `_job_steps`, `_build_step`); but `:86-92,96,108`, and the pyproject greps use substring.
- CLASS: BEST-PRACTICE.

### RC-4 (low, 6) — `test_slo_constants.py` and `test_p95_gate.py` both pin `P95_SLO_MS == 500`
- CLASS: BEST-PRACTICE.

### RC-5 (low, 2) — `test_health_contract.py` vs `test_observability.py` nearly no overlap (hypothesis disproven); one thin `/metrics` overlap
- CLASS: no action.

### RC-6 (med, 6) — meta-tests about the test factory / enum, not production
- `test_ad_factory_contract.py` (AST guard on `create_test_ad(status=...)`) — defensible suite-integrity guard. `test_seedable_ad_statuses.py` duplicates `enums.py:162-164` frozenset.
- CLASS: TEST-DELETE (`test_seedable_ad_statuses.py`); keep `test_ad_factory_contract.py`.

### RC-7 (med, ~10) — per-sweep `test_collects_thumbnail_keys_for_media_cleanup` is a weaker subset of the parametrized exactly-once test
- `test_delete_photo_single_call.py::test_sweep_command_delete_photo_once_per_key` asserts exactly-once; the five per-sweep copies assert set equality (misses double-call).
- CLASS: TEST-DELETE (the five per-sweep copies).

### RC-8 (low, 1) — `test_draft_sweep_index_leads_on_updated_at` reads `pg_indexes` built by syncdb; migration not replayed
- `test_sweep_drafts.py:~195`.
- CLASS: TEST-UPDATE / DOC-UPDATE.

### RC-9 (low, 3) — `test_create_admin_entrypoint.py` splits behavioral (good) and static-text branches (documented)
- CLASS: BEST-PRACTICE (acceptable).

### RC-10 (low, 1) — `test_sweep_lock_structure.py` runtime spy is sound (count==16 + per-lock-id membership); minor per-command blind spot
- CLASS: no action.

### RC-11 (med, 3) — `apps/core/tests/test_deploy_workflow.py` is a YAML-string companion to the structural `src/backend/tests/test_deploy_workflow.py`
- Complementary, not duplicate.
- CLASS: BEST-PRACTICE.

### RC-12 (low) — `apps/core/tests/test_json_logging.py` DOES NOT EXIST (stale block entry)
- Only `src/backend/tests/test_json_logging.py` exists (other block).
- CLASS: DOC-UPDATE (block inventory).

### Duplicate-file analysis
- `test_json_logging.py` under `apps/core/tests/`: **ENOENT**.
- `test_deploy_workflow.py`: DIVERGED & complementary (apps/core = literal profile names; src/backend = derived sets + ruamel YAML).

### Already resolved
- A5 `test_sweep_commands.py` (1,046 lines) split into 9 per-command files.
- A4 `inspect.getsource` token assertions replaced by runtime spies (`test_sweep_lock_structure.py`).
- Archive per-batch commit (03-DB-008) RED-test added (`test_batches_commit_independently`).
- Drafts predicate flipped to `updated_at` (03-DB-003); both directions covered.
- Media reference check across all four key columns (07-MEDIA-001) covered.
- `send_alerts` digested without network in the lock-structure test.

### Missing coverage
| Behavior | Source | Why critical | Location |
|---|---|---|---|
| Exact cutoff ±1s for all 6 sweeps (`__lt` strict) | `delete_sweep.py:46` etc., `db-retention.md` | Off-by-one silently deletes an extra period | each sweep test file |
| Timezone handling of cutoff (`USE_TZ`) | each sweep `timezone.now() - timedelta` | Naive-datetime regression shifts window | sweep boundary tests |
| Re-run idempotency (second call → 0 rows, no error, lock re-acquired) | sweeps | Scheduler ticks hourly | each sweep file |
| `archive_sweep` keyset cursor across >`_BATCH_SIZE` rows | `archive_sweep.py::_batch` | Batch-seam skip/duplicate | `test_sweep_archive.py` |
| `consent_hard_delete` orphans already-null tickets | `consent_hard_delete.py:86-92` | Explicit correctness statement untested | `test_sweep_consent.py` |
| `cleanup_login_tokens` exact 24h / `expires_at == now()` edge | `cleanup_login_tokens.py:47-55` | Boundary untested | `test_sweep_login_tokens.py` |
| `create_admin_user` validation inside the `session=True` lock | `create_admin_user.py:92-160` | Lock scope regression untested | `test_create_admin_user.py` |

### Duplicates
1. Five per-sweep `test_collects_thumbnail_keys_for_media_cleanup` ⊂ `test_delete_photo_single_call.py` (RC-7).
2. `test_slo_constants::test_p95_slo_ms` ⟷ `test_p95_gate::test_threshold_is_the_shared_slo_constant`.
3. `test_sweep_delete` cascade tests ⟷ `test_ad_image_delete_signal.py` (partial).
4. `test_sweep_consent::test_collects_thumbnail_keys_for_media_cleanup` ⟷ `test_delete_photo_single_call::test_consent_hard_delete_delete_photo_once_per_key`.
5. `apps/core` vs `src/backend` `test_deploy_workflow.py` (complementary).

### Uncertain
- Whether `ads/0008_*` index migration is replayed anywhere.
- `purge_consent_records` / `purge_media_deletion_errors` behavioural coverage lives in other blocks.
- `_MIN_SCANNED_FILES = 250` floor satisfaction not measured (slow-marked).

---

## Block 5 — Ads: lifecycle, constraints, submission & copy

### RC-1 (HIGH, 1 + missing edges) — `ALLOWED_TRANSITIONS` pinned by a hand-copied literal; `any → DELETED` untested as a matrix row
- `test_ad_lifecycle.py:32-50` (`test_module_constant_matches_shipped_matrix`). Production `models.py:27-41` + `transition_to` (`:457-474`) treats DELETED as a universal sink NOT in the dict. Only ~7/13 allowed pairs and 2 forbidden pairs sampled.
- CLASS: TEST-REWRITE (parametrize from `ALLOWED_TRANSITIONS` + DELETED sink).

### RC-2 (HIGH, ~4) — `test_submission.py` mocks `auto_moderate`, so the real publish path and its side effects are never verified
- `test_submission.py:107-131` (`test_submit_ad_commit_when_auto_moderate_passes`) patches `auto_moderation.auto_moderate` → asserts `ON_MODERATION` while calling it "success"; real path sets `PUBLISHED` + writes `AD_PUBLISHED` + `MODERATION_APPROVED` + `ModeratorActionLog` (`auto_moderation.py:258-278`). Same at `:865-879`.
- CLASS: TEST-REWRITE (add un-patched success test asserting status/timestamps/audit/2 events).

### RC-3 (med, ~5) — consent gate composition (`can_create_ad` = `can_publish_ad AND can_store_personal_data`) untested
- `test_ad_consent_gate.py` uses real states but never pins the composition; `test_submission.py:798-879` uses real states but not the refusal reason.
- CLASS: TEST-UPDATE (truth table + refusal reason).

### RC-4 (med, 3) — `test_delete.py` asserts only status/redirect; no visibility or soft-delete side effects
- `test_delete.py:43-60`; no assertion the ad leaves listings/search/detail, no `AdImage` retention check.
- CLASS: TEST-UPDATE.

### RC-5 (med, 4) — `test_copy_ad.py` misses documented cascade/shared-key/retry branches; one duplicate test
- `test_copy_ad.py:82-111`; `copy_service.py:98-139` (draft replacement cascade, `pre_delete`/`on_commit` shared-key protection, savepoint retry). `test_copy_ad_features_m2m_copied:208-219` duplicates `:165-168`.
- CLASS: TEST-UPDATE + TEST-DELETE (duplicate).

### RC-6 (low, 6) — backfill couples to the `translated == text` fallback signal; partial-population boundary untested
- `test_backfill_translations.py:38-42,118-162`; `backfill_translations.py:88-92` (OR query).
- CLASS: TEST-UPDATE.

### RC-7 (med, ~14) — admin form: forged read-only-field POST unasserted; MaxAdsExceeded test only asserts `status_code in (200, 302)`
- `test_admin_change_form.py:356-379,417-438`; `admin.py:250-268`.
- CLASS: TEST-UPDATE.

### RC-8 (low, ~5) — `copy_ad` drops `sha256` silently; no test pins whether intended
- `copy_service.py:130-139`; `models.py:648-654`.
- CLASS: TEST-UPDATE + DOC-UPDATE (decide & document).

### Already resolved
- B2 (redundant constraint tests in `test_ad_lifecycle.py`): resolved — constraints centralized in `test_ad_constraints.py`.
- B3 (`copy_ad` coverage): resolved — `test_copy_ad.py` added.
- C1 (misplaced backend integration tests in bot tree): resolved for this block.
- `TestBannedSellerRelistKnownGap`: replaced by `TestBannedSellerRelistNowRefused` in `test_edit.py:1361`.

### Missing coverage
| Behavior | Source | Why critical | Location |
|---|---|---|---|
| Exhaustive `transition_to` incl. `any → DELETED` | `models.py:27-41,457-474` | Core lifecycle contract sampled only | `test_ad_lifecycle.py` |
| Real submit → `PUBLISHED` with full side effects | `submission.py:414-458`, `auto_moderation.py:258-278` | Success path only tested via stub | `test_submission.py` |
| `can_create_ad` truth table | `account_state.py:274-308` | Dropped conjunct passes green | `test_ad_consent_gate.py` |
| Delete: hidden from listings/search/detail; images retained (soft delete 120d) | `views/delete.py:42-60`, `db-retention.md:44-47` | US-S6 user-visible guarantee | `test_delete.py` |
| `copy_ad` cascade + shared-key + savepoint retry | `copy_service.py:98-139` | Documented safety guarantees | `test_copy_ad.py` |
| `uq_ads_single_draft_per_user` fires on a second DRAFT | `models.py:378-382` | Partial unique index invariant | `test_ad_constraints.py` |
| Backfill OR-query partial population | `backfill_translations.py:88-92` | Recoverability contract | `test_backfill_translations.py` |
| Admin: forged POST to `readonly_fields` ignored | `admin.py:250-268` | Audit-trail/readonly guarantee | `test_admin_change_form.py` |

### Duplicates
- `test_copy_ad.py:208-219` ⊂ `:165-168`.
- `test_ad_lifecycle.py:128-131` vacuous vs `:133-138`.
- `test_ad_constraints.py:197-215` restates `:87-109` positives.

### Uncertain
- Whether `purpose_item`/`feature_items` fixtures duplicate a shared ads conftest fixture.
- `test_backfill_translations::test_limit_bounds_the_run` ordering determinism.
- Staff fixtures on the `9300001xx` band vs xdist collisions (not run).

---

## Block 6 — Ads: edit, locking & dashboard

### RC-1 (med, 9) — `callable()`-only "lock sentinel" tests assert nothing about locking
- `test_edit_views_locking.py:39-141` — six/seven tests reduce to `assert callable(edit.ad_edit)`.
- CLASS: TEST-DELETE.

### RC-2 (HIGH, 3 params) — the `select_for_update` concurrency test never invokes the views it names
- `test_edit_views_locking.py:171-245`: helper does its own `Ad.objects.select_for_update()`; `view` param used only in prose. Dropping the lock in `edit.py:219,431,482` leaves it green.
- CLASS: TEST-REWRITE (drive the real view POST in a thread).

### RC-3 (med, 1) — `_apply_price_change` "delegation" test asserts a mock call, not the DRY invariant
- `test_edit.py:704-723` patches `apps.ads.views.edit.normalize_price_to_eur`.
- CLASS: TEST-DELETE (behavior covered by `TestReactivationPriceNormalized:260-291`).

### RC-4 (med, 2) — dashboard HTML assertions pin Tailwind class strings
- `test_dashboard_stats.py:242-250` (`'text-2xl font-bold text-blue-600">3</p>'`); third stat cell never asserted.
- CLASS: TEST-REWRITE.

### RC-5 (med, 2) — dashboard "HTML rendering" tests assert Russian translation literals and plural forms
- `test_dashboard_stats.py:252-259` (`"За всё время"`), `:261-269` (`"1 контакт"`).
- CLASS: TEST-DELETE (behavior covered by `TestDashboardTimeRange:184-206`).

### RC-6 (med, 1) — `ads_by_status` asserts Django-private queryset attributes
- `test_dashboard_stats.py:362-378` (`_prefetch_related_lookups`, `query.select_related`); production `dashboard_query.py:44-62`.
- CLASS: TEST-REWRITE (use `CaptureQueriesContext`).

### RC-7 (low-med, ~5) — mocked `auto_moderate` weakens transition assertions + near-duplicates
- `test_edit.py:92-133,144-166,169-209,363-407,533-578,580-615,649-685`.
- CLASS: BEST-PRACTICE (consolidate; keep `permissive_criteria`/`banning_criteria` real-path tests).

### RC-8 (med, 1) — `test_favorites.py::test_excludes_non_published_and_blocked_sellers` is self-defeating
- `test_favorites.py:296-310`: all three ads owned by the seller that is then banned → cannot distinguish the two clauses; duplicates `apps/cabinet/tests/test_favorites_visibility.py`.
- CLASS: TEST-REWRITE.

### RC-9 (med, missing) — favorite unique-constraint race path untested
- `favorites.py:98,110-115`; `models.py:846-849`.
- CLASS: BEST-PRACTICE (add).

### RC-10 (med, missing) — banned owner on `ad_edit` GET+POST unasserted
- `edit.py:125-136,195-196`; covered only for archive/reactivate (`test_edit.py:1376-1397`).
- CLASS: BEST-PRACTICE (add).

### RC-11 (low, ~6) — redundant near-duplicate transition tests
- "status becomes ON_MODERATION" repeated at `test_edit.py:131,206,401,571,613-615,681-683`; "dashboard" redirect in ≥10.
- CLASS: BEST-PRACTICE.

### RC-12 (low-med, 3 files) — markup/substring coupling in `test_breadcrumbs_render.py:36-43,109-144`, `test_auth_nav.py:127-140,180-200`
- CLASS: BEST-PRACTICE.

### Already resolved
- F4-analogue (bare-numeric dashboard false positives) partially addressed but replaced with equally brittle class strings (RC-4).
- `TestBannedSellerRelistKnownGap` → `TestBannedSellerRelistNowRefused` (403).
- A4 moderation mock target now `apps.moderation.services.auto_moderation.auto_moderate`.
- `inspect.getsource` lock assertions removed (residual is RC-1/RC-2).

### Missing coverage
| Behavior | Source | Why critical | Location |
|---|---|---|---|
| Duplicate favorite rejected by `uq_user_ad_favorite` | `models.py:846-849`; `favorites.py:98` | Race-safety claim unverified | `test_favorites.py` |
| Banned/deleted owner refused on `ad_edit` GET+POST | `edit.py:195-196` | Gate removal passes today | `test_edit.py` |
| Partial-update data loss (title-only edit preserves other fields) | `edit.py:364-377` (`update_fields`) | Silent data loss | `test_edit.py` |
| `ad_edit` lock-timeout re-render branch | `edit.py:398-412` | 03-DB-004 boundary | `test_edit_views_locking.py` |
| Real concurrent-edit serialization through the views | `edit.py:218-219,430-431,481-482` | RC-2 | `test_edit_views_locking.py` |
| Dashboard N+1 budget | `dashboard.py:60-71` | No query budget | `test_dashboard_stats.py` |

### Duplicates
- `TestEditOtherStatusDirectSave:1043-1168` ⟷ `TestEditStatusAllowListEnumeration:1176-1265`.
- `test_edit.py:409` ⟷ `:1241`.
- Cross-block: `apps/ads/tests/test_favorites.py:296` ⟷ `apps/cabinet/tests/test_favorites_visibility.py:67-140`.
- Cross-block: `test_auth_nav.py:180-200` ⟷ `apps/cabinet/tests/test_favorites_badge.py`.
- Cross-block: `test_favorites_toggle_api.py:167-214` ⟷ `test_favorites.py:321-339`.

### Uncertain
- Ownership of `test_listings_context.py` (overlaps the listings block); it also holds a `/search/` test (`:203-238`).
- `TestEditViewsRowLockConcurrency` marked `flaky(reruns=1)` with fixed sleeps.

---

## Block 7 — Ads: listings, filters, sorting & price

### RC-1 (HIGH, 2) — Free-ad price-sort direction CONTRADICTS the spec; test entrenches the code
- `test_fts_sort_order.py:96-125` asserts Free (0) sorts FIRST ascending. Spec `docs/01-spec/search-patterns.md:183-185,223-224` says Free ads sort LAST. Production `listings_query.py:297-304`, `fts.py:99-108` use `price_normalized_eur` (0) with `nulls_last=True`.
- CLASS: TEST-REWRITE pending an owner decision (spec vs code) + DOC-UPDATE.

### RC-2 (med, 1 param x4, 2 vacuous) — API sort matrix asserts no ordering for date sorts
- `test_listings_api.py:209-226` only asserts membership for `DATE_NEW`/`DATE_OLD`.
- CLASS: TEST-REWRITE.

### RC-3 (med, ~10) — URL-state tests assert template-source strings/CSS classes, not the documented preservation rules
- `test_filter_url_reset.py:577-693`, `:176-217,238-252`; spec `url-state-preservation.md:152-160`, `filter-ui.md:460-484`.
- CLASS: TEST-REWRITE.

### RC-4 (med, 4) — price sort tests use EUR-only data; NULL (`nulls_last`) ordering never covered
- `test_price_sort.py:17-83`.
- CLASS: TEST-REWRITE.

### RC-5 (low, ~5) — FTS ranking tests DO use real vectors (good) but duplicate `test_relevance_tiebreaker.py`
- `test_fts_sort_order.py:127-164,166-204` ≈ `test_relevance_tiebreaker.py:20-45,60-96`.
- CLASS: TEST-DELETE (dedupe, keep `test_relevance_tiebreaker.py`).

### RC-6 (low, 12) — filter×sort×page cross-product is order-blind
- `test_listings_api.py:237-270`.
- CLASS: TEST-REWRITE.

### Already resolved
- B7b `test_price_format.py` now `integration`-marked.
- B4/P9 magic `count("hx-get=")==10` replaced by parity count.
- E4 feature-filter isolation via a control ad.
- E2 "mocked FTS" not present in this block.

### Missing coverage
| Behavior | Source | Why critical | Location |
|---|---|---|---|
| Free ads sort LAST (`search-patterns.md:183-185,223`) | `listings_query.py:297-306` | Test asserts the opposite | `test_price_sort.py` |
| NULL `price_normalized_eur` sorts last | `listings_query.py:299,303` | Untested deliberate clause | `test_price_sort.py` |
| Mixed-currency EUR-normalized ordering | `price_normalizer.py` | Sort could ignore normalization | `test_price_sort.py` |
| Pagination URL preserves lang/purpose/condition/features | `ad_list.html:181-208`, `filter-ui.md:460-484` | Core documented rule | `test_filter_url_reset.py` |
| Category/breadcrumb links preserve sort/purpose/features/price | `header_catalog.html`, `breadcrumb.html` | Composed URLs unasserted | `test_filter_url_reset.py` |
| `min_price=0` includes Free | `listings_query.py:231-234` | Boundary untested | `test_listings_api.py` |
| Unknown single-select slug matches nothing | `listings_query.py:221-242` | Only unknown category/sort tested | `test_listings_api.py` |
| Empty-result listings | `views/listings.py:333-342` | No zero-result test | `test_listings_api.py` |
| API `per_page` clamp boundaries | `views/api/listings.py:80` | API-only param unconstrained | `test_listings_api.py` |

### Duplicates
- `test_filter_url_reset.py:238-252` ≡ `:254-265`.
- `test_fts_sort_order.py` pairs ⟷ `test_relevance_tiebreaker.py` pairs.
- `test_features_filter.py:44-92` HTML AND-semantics covered 3× (plus API).
- `test_listings_sort.py:55-81` ⟷ vacuous API date branches.

### Uncertain
- `?condition=` vs spec's `listing_condition` — spec may be stale; NOT a test defect.
- `_CHIP_RE` on `bg-orange-100` may be spec-anchored (`filter-ui.md:386`).

---

## Block 8 — Ads: detail, gallery, media & search triggers

### RC-1 (med, 12) — `test_media_security.py` duplicates EXIF/delete-photo coverage owned by `apps/media/tests/test_filesystem.py`
- `test_media_security.py:360-484` vs `test_filesystem.py:221-446` (media versions stronger).
- CLASS: TEST-DELETE.

### RC-2 (med, ~20) — gallery/detail/script-gating tests couple to markup IDs, classes and attribute strings
- `test_gallery_markup.py:106-131,142-148,196-203`; `test_detail_render.py:45,68-71`; `assert "aspect-" in content` (`:124`) is vacuous.
- CLASS: TEST-REWRITE.

### RC-3 (low-med, 5) — template-source guards in `test_detail_context.py:181-183,201-202,242,254-258`
- Keep the cleartext-bot-username leak guard; convert the `{% if %}`/`|last` spacing-sensitive ones.
- CLASS: TEST-REWRITE.

### RC-4 (low-med, 2) — `test_ad_detail_queries.py` exact `_QUERY_BOUND = 19` total query budget
- `:28-47,69`. Per-table trust-score count at `:87-94` is the robust part.
- CLASS: TEST-UPDATE (delta guard).

### RC-5 (HIGH, gap over ~50) — media-security file never asserts the upload boundaries it is named for
- No size 2MB ±1 pair, no extension/content-type mismatch, no 1–5 count boundary. Production gate `views/listings.py:245-271` never inspects bytes; `_serve_image` hardcodes `image/jpeg`.
- CLASS: BEST-PRACTICE + missing coverage.

### RC-6 (low, 8) — `test_adimage_storage_keys.py` re-tests the KEY_COLUMNS↔model invariant owned by `apps/media/tests/test_references.py`
- `:96-113`.
- CLASS: TEST-DELETE (one test).

### RC-7 (low, 3 files) — stale/misleading docstrings; two orphaned string literals acting as class docstrings
- `test_detail_context.py:1-13`; `test_media_security.py:147,559`; `test_ad_detail_queries.py:5-11`.
- CLASS: DOC-UPDATE.

### RC-8 (low-med, 14) — FTS trigger tests are behavioral (good) but have no trigger-absence skip guard
- `test_search_triggers.py:57-182`; trigger DDL lives outside migrations.
- CLASS: BEST-PRACTICE (add `pg_trigger` guard + skip).

### RC-9 (low, 2) — `test_ad_detail_api.py:55` blanket `startswith("application/")` in the helper
- CLASS: TEST-UPDATE.

### Overlap with apps/media block
| This block | Canonical home |
|---|---|
| `test_media_security.py:360-421` EXIF (6) | `test_filesystem.py::TestStripPhotoExif:359-446` |
| `test_media_security.py:423-484` delete (5) | `test_filesystem.py::TestDeletePhoto:221-351` |
| `test_adimage_storage_keys.py:96-113` | `test_references.py::TestKeyColumnsAntiDrift:21-109` |
| `test_ad_image_removal.py:190-297` shared-key | `test_references.py::TestUnreferencedKeys:112-158` |

### Already resolved
- B5 over-mocking in `test_detail_context.py` — now real `published_ad` fixture.
- F9/P3 `strip_photo_exif`/`assert_storage_key_contained` units — now in media block.
- 09-API-005 media-gate rate-limit response-shape — resolved (`:940-1054`).

### Missing coverage
| Behavior | Source | Why critical | Location |
|---|---|---|---|
| 2 MB boundary pair (== and +1) | `filesystem.py:238` | Off-by-one at cap | `apps/media/tests/test_filesystem.py` |
| Non-image payload under a `.jpg` key | `views/listings.py:245-271` | Classic upload bypass | `test_media_security.py` |
| 1–5 photo count at the DB/ads layer | bot `photos.py:53,56,83` | Not blocked below the bot | bot block (cross) |
| Banned/deleted seller on the media gate | `listings.py:266-271` (`account_state_q`) | Only declined covered (`:308-327`) | `test_media_security.py` |
| `contact_url` for banned vs missing-`telegram_id` seller | `views/api/detail.py:140-158` | Branches untested | `test_ad_detail_api.py` |
| Concurrent `remove_ad_image` | `ad_image_removal.py:92-95` | Lock shape docstring-only | `test_ad_image_removal.py` |
| Trigger-absence skip | `setup_search_triggers.py:34-103` | Fails instead of skipping | `test_search_triggers.py` |

### Duplicates
- `test_detail_context.py:73-107` ≈ `test_ad_detail_queries.py:71-94`.
- `test_gallery_markup.py:265-281` ≈ `test_script_gating.py:57-63`; `:86-97` ≈ `:65-75`.
- `test_gallery_markup.py:177-186` ⊂ `:99-131`.
- `test_media_security.py:426-436` ≈ `:473-484`.

### Uncertain
- `_QUERY_BOUND = 19` headroom not measured.
- Whether the dotdot gate rejects pre-DB or via row lookup — both yield 404.

---

## Block 9 — Ads: i18n

### RC-1 (HIGH, 1) — plural-form test cannot prove form selection (bs forms are textually identical)
- `test_i18n_completeness.py:857-862` asserts `rendered[2] != rendered[5]`; bs `msgstr[1]`/`msgstr[2]` are both `"%(counter)s pregleda"` (`locale/bs/.../django.po:741-742`) — they differ only by the interpolated counter.
- CLASS: TEST-REWRITE.

### RC-2 (med, 4) — `test_i18n_pipeline.py` duplicates catalogue-shape guards owned by `test_i18n_completeness.py`; private `_po_files()` re-declared
- `test_i18n_pipeline.py:27,36-40,119` vs `test_i18n_completeness.py:108,482,504,604`.
- CLASS: BEST-PRACTICE (share the helper).

### RC-3 (low-med, ~8) — `test_ad_localization.py` hand-built `Ad.__new__` unit mirror with redundancy
- `:19-39,55,64-69,77-82,87,119-121` — `None` and `""` cases are identical under the truthiness guard.
- CLASS: TEST-DELETE (collapse None/"" pairs into one parametrized truthiness test per field).

### RC-4 (med, 1) — `test_detail_defaults_to_en` pins a TEST-settings artifact (`LANGUAGE_CODE="en"`) as the product default
- `test_i18n_category_city.py:104-124`; production `base.py:166` (`"ru"`); `config/settings/test.py:15`.
- CLASS: TEST-UPDATE (assert `LanguageLocale(settings.LANGUAGE_CODE)`).

### RC-5 (low, 1) — `test_ad_get_title` only asserts `isinstance(str)`
- `test_i18n_category_city.py:330-349`; fixture sets only the base title.
- CLASS: TEST-REWRITE.

### RC-6 (med, missing) — localized_content filters and API locale path untested
- `apps/core/templatetags/localized_content.py:21-109`; API calls `get_title()` with no locale (`api/detail.py:110-111`, `listings.py:127`, `dashboard.py:130`).
- CLASS: TEST-ADD + DOC-UPDATE (state the API locale contract).

### Already resolved
- B6 duplicate `_parse_po_entries`: resolved (both import `testing.i18n_helpers`).

### Missing coverage
| Behavior | Source | Why critical | Location |
|---|---|---|---|
| `localized_content` filter `None` guard | `localized_content.py:87-89,107-109` | Sole template boundary | new `test_localized_content_filters.py` |
| `Ad.get_title`/`get_description` per-locale from a real DB row | `models.py:542-565` | All getter tests are in-memory | `test_ad_localization.py` |
| API locale behaviour | `api/detail.py:110-111` | Silently Russian, unstated | API tests |
| `component_tag`/`get_lookup_name` `name_i18n=None` terminal | `lookups/models.py:90-99` | Filter path untested | `test_i18n_pipeline.py` |

### Duplicates
- `test_ad_localization.py:64` ≡ `:69` ≡ `:119`; same triplicate on description and base rung.
- `test_i18n_pipeline.py:40` partially duplicates `test_i18n_completeness.py:604`.
- Cross-block: category/city fallback chain asserted 3× (ads i18n, `categories/tests/test_categories.py:319-346`, `test_categories_api.py:130-145`).

### Uncertain
- API locale contract (intended Russian-only?) — unstated in spec.
- `test_mo_compiled` cannot pass outside the Docker image (.mo gitignored) — not executed.
- `test_bs_msgstr_exemptions...:1303` pins a full multi-line msgid literal → breaks on any source-text change.

---

## Block 10 — Media app

### RC-1 (HIGH, 7) — path-traversal containment missing Windows backslash, URL-encoded, empty-string and bare `".."` cases
- `test_filesystem.py:454-504` (NUL, leading `/`, `..`, nested, valid, subdir, symlink escape present). Production `filesystem.py:187-204`.
- CLASS: TEST-UPDATE.

### RC-2 (med, 1) — size boundary is one-sided: no "exactly 2 MB accepted"
- `test_filesystem.py:107` only tests `2MB+1` reject; production `filesystem.py:238` is strict `>`.
- CLASS: TEST-UPDATE.

### RC-3 (low, doc) — `real_images` marker is SEED-scoped, not "needs Pillow"; no misuse in this block
- `pyproject.toml:179`; `apps/seed/tests/conftest.py:50`. Block 10 correctly omits it.
- CLASS: DOC-UPDATE (clarify the marker's meaning).

### RC-4 (med, 3) — `validate_photo` size test uses a non-decodable blob; cannot prove rejection happens at the size gate
- `test_filesystem.py:107-121`.
- CLASS: TEST-REWRITE.

### RC-5 (low, 4) — `test_adimage_sha256.py` uses placeholder bytes (contract-correct; benign)
- `:44,110,137`.
- CLASS: BEST-PRACTICE (optional realism).

### RC-6 (med, ~6) — `test_references.py` is predicate-only; no file-level survival+deletion pair
- `:136`; production `references.py:52-91` vs `signals.py:62-68`.
- CLASS: TEST-UPDATE (or confirm the ads-block removal tests cover both directions).

### RC-7 (low, ~4) — orphan-sweep report-orphan path and `--check` negative path thin
- `test_sweep_orphaned_media.py:358-377`; production `sweep_orphaned_media.py:147-162`. The dangerous "referenced file kept" direction IS covered (`:70`).
- CLASS: TEST-UPDATE.

### RC-8 (low, hygiene) — `test_helpers.py` is a live helper module (0 tests) imported by pytest because it matches `test_*.py`
- `test_helpers.py:22,44,69,96`; `pyproject.toml:166`. Callers: `test_thumbnail_integration.py:40`, `test_save_photo_exif.py:19`.
- CLASS: BEST-PRACTICE (rename to `media_test_helpers.py`).

### RC-9 (low, ~5) — thumbnail file duplicates + cross-block storage-key duplicate
- `test_thumbnails.py:341` ⊂ `:218`; `:99` ≈ `:218`.
- CLASS: TEST-DELETE (one method).

### Block hygiene
- `test_helpers.py`: live helper, not dead, not miscollected as tests.
- Marker misuse: none. `unit` used correctly in `test_filesystem.py:40`, `test_hash_service.py:21`, `test_stored_jpeg_quality.py:25`, `test_media_config.py:6`. `test_purge_media_deletion_errors.py:22` has `django_db` without `integration`/`unit` (minor).
- Size: `test_filesystem.py` (838 lines), `test_sweep_orphaned_media.py` (470) — cohesive, not gratuitous.

### Already resolved
- F8 (manual EXIF bytes, `SimpleNamespace` settings) — now Pillow `Image.Exif()` + `override_settings`.
- F9 (missing `assert_storage_key_contained`/`strip_photo_exif`/`validate_jpeg_bytes`/signal-registration units) — all present.
- F9 (`move_staging_to_permanent`) — replaced by `plan_staging_promotion`/`promote_media_files`/`reclaim_staged_keys` contract tests.
- F5 (media-error side-effect) — deletion-error row asserted (`:299-325`).
- F7 (cross-block coupling) — imports only `apps.media.*`, `apps.ads.models.AdImage`, `apps.core.enums`.

### Missing coverage
| Behavior | Source | Why critical | Location |
|---|---|---|---|
| Exact-2 MB accepted | `filesystem.py:238` | Off-by-one at cap | `test_filesystem.py` |
| Windows backslash traversal key | `filesystem.py:193,199` | CWE-22 on the deployed OS | `test_filesystem.py` |
| Empty-string / bare `".."` key | `filesystem.py:187-204,286` | `realpath(root/"")==root` passes | `test_filesystem.py` |
| URL-encoded `%2e%2e` | `filesystem.py:193` | Encoded traversal | `test_filesystem.py` |
| In-root symlink target allowed | `filesystem.py:198-204` | Only escape direction tested | `test_filesystem.py` |
| `--check` reports orphaned on-disk file | `sweep_orphaned_media.py:147-162` | Cron observability | `test_sweep_orphaned_media.py` |
| Decodable >2 MB JPEG rejected at size gate | `filesystem.py:234-255` | Proves gate ordering | `test_filesystem.py` |
| `promote_media_files` EXDEV fallback success | `filesystem.py:126-133` | Only failure branch | `test_filesystem.py` |
| No-upscale in thumbnail generation | `thumbnails.py:136` | Unasserted | `test_thumbnails.py` |

### Duplicates
- `test_thumbnails.py:341` ⊂ `:218`; `:99` ≈ `:218`.
- Cross-block: `test_references.py:33` ≈ `apps/ads/tests/test_adimage_storage_keys.py:41`.
- Cross-block: `test_filesystem.py::TestStripPhotoExif`/`TestDeletePhoto` ⊃ the ads copies.

### Uncertain
- Feasibility of constructing a real >2 MB JPEG.
- Whether the ads-block removal tests cover both survival and deletion.
- `test_media_admin.py:153` `has_view_permission` → `True` on a `MagicMock` (framework delegation).
- `test_backfill_thumbnails.py:39` redefines `isolated_media_root` although conftest says the duplication was removed.

---

## Block 11 — Moderation

### RC-1 (med, ~6) — no single test asserts the FULL approve side-effect set
- `test_admin_actions.py:120-131` (status/timestamp/log count/`AD_PUBLISHED`) misses `original_published_at`, audit actor/reason, `MODERATION_APPROVED`. `test_approve_ad_side_effects.py:47-50` misses audit+analytics. `test_auto_moderation.py:476-478` uses `auto_moderate` directly.
- CLASS: TEST-UPDATE (consolidate one full-set test).

### RC-2 (low, ~5) — `test_approve_ad_side_effects.py` ≈ `test_moderation_side_effects.py`
- CLASS: TEST-DELETE (merge).

### RC-3 (med, 3) — alert-gate tests replace `transaction.on_commit` with a synchronous shim
- `test_approve_ad_side_effects.py:63,82,116` (`side_effect=lambda fn: fn()`); contract is commit-gating (`signals.py:56-77`).
- CLASS: TEST-REWRITE (`django_capture_on_commit_callbacks`).

### RC-4 (med, ~2) — the outer `except Exception → ON_MODERATION_FAILED` safety net is untested; cap test patches a lazy-import seam
- `auto_moderation.py:170-172`; `test_auto_moderation.py:635-671,696-698` patch `moderation_log.set_published` (function-local import).
- CLASS: TEST-UPDATE.

### RC-5 (low, 11) — `test_decorators.py` marked `unit` but fabricates `user.role` on a `MagicMock`; real `User.role` untested through the decorator
- `:6-8,22,42-55`.
- CLASS: TEST-UPDATE.

### RC-6 (med, ~3) — `price_required` and `duplicate_title` criteria have ZERO boundary tests; race test carries `flaky(reruns=1)`
- `auto_moderation.py:140-142,160,224-238`; `test_auto_moderation.py:748-829`.
- CLASS: TEST-UPDATE.

### RC-7 (low, ~10) — queue-view assertions decode raw HTML/Russian literals, duplicating structured parity tests
- `test_priority_service.py:373-379,396-416,510-522` vs `test_moderation_api_reads.py:162-233`.
- CLASS: TEST-REWRITE (assert context).

### RC-8 (low, ~6) — `inspect.getsource` tripwires; `"pk" in src` is vacuous
- `test_admin_actions.py:318-325`; `test_admin_ban_privilege_guard.py:559-603`.
- CLASS: BEST-PRACTICE.

### RC-9 (low, ~5) — `test_moderation_log.py::TestSetPublishedCapGuard` duplicated in `test_auto_moderation.py::TestMaxAdsTOCTOUFix`
- CLASS: TEST-DELETE (reduce to the integration seam).

### Prior-audit re-check
- **D1** (mock `Ad.objects.filter` false positive): RESOLVED — no queryset mocks remain.
- **D2** (criteria cache vs direct-DB disagreement): STILL OPEN — `auto_moderation.py:31-79` (cached) vs `priority_calculator.py:57` (direct); no test.
- **D3** (missing side effects): MOSTLY RESOLVED — `set_moderation_failed`/`set_rejected`/analytics now covered; residue folded into RC-1.
- **D4** (helper duplication / misleading names): PARTIALLY resolved; `test_decorators.py` + `test_priority_service.py` naming oversell scope.
- **D5** (TOCTOU with mocked counters): RESOLVED on substance; residual `flaky` on the race test (RC-6).
- **D6** (DISPUTED trust/min_responses claim): CONFIRMED still inaccurate — no `min_responses` in `trust_calculator.py:165`; no `test_ban_user_soft_deletes_ads`. Prior "⚠️ Disputed" verdict is correct.

### Missing coverage
| Behavior | Source | Why critical | Location |
|---|---|---|---|
| Full approve side-effect set in one call | `models.py:480-490`, `auto_moderation.py:258-278` | Partial assertions hide regressions | `test_moderation_side_effects.py` |
| `auto_moderate` outer `except` → `ON_MODERATION_FAILED` | `auto_moderation.py:170-172` | Safety net untested | `test_auto_moderation.py` |
| `price_required` (None, 0) | `auto_moderation.py:140-142` | Documented rule untested | `test_auto_moderation.py` |
| `duplicate_title` at threshold | `auto_moderation.py:160,224-238` | Documented rule untested | `test_auto_moderation.py` |
| Criteria-cache vs direct-DB consistency mid-TTL | D2 | Two readers can disagree | `test_moderation_side_effects.py` |
| FTS visibility after approve/reject | `models.py:238-255` | User-facing outcome of moderation | `test_moderation_side_effects.py` |
| `api_bulk` BAN parity question | `views/api_bulk.py:114-135` | Rule 18 parity | pending decision |

### Duplicates
- Priority-signal-on-ON_MODERATION: `test_moderation_side_effects.py`, `test_approve_ad_side_effects.py`, `test_priority_service.py:313-321` (3 copies).
- `test_moderation_log.py:52-124` ⟷ `test_auto_moderation.py:586-633`.
- `test_priority_service.py:396-416` ⟷ `test_moderation_api_reads.py:162-233`.
- `test_priority.py:100-cap` ⟷ `:score_100` ⟷ `TestPriorityServiceBoundaries` (boundaries re-derived 3×).

### Uncertain
- `test_approve_ad_no_alerts_when_immediate_alerts_disabled` relies on the ambient default rather than `override_settings`.
- Whether `flaky(reruns=1)` currently masks a real failure.
- `api_bulk` BAN absence may be intentional.

---

## Block 12 — Config, docs/CI parity, deploy & ops

### RC-1 (med, ~35) — raw-text YAML scanning where a parsed path exists in the same block
- `test_compose_hardening.py` uses `_compose_helpers._service_block` regex, while `test_compose_contract.py:47-67` uses `ruamel.yaml`; `test_compose_hardening.py:280-286,222-259`; `test_ci_image_coordinate.py:172-182` hand-rolls a block extractor.
- CLASS: BEST-PRACTICE (keep raw-text only for nginx).

### RC-2 (low, 2 files) — `test_env_allowlist.py` hand-maintained list duplicates the reverse-scan superset
- `test_env_allowlist.py:75-86,89-93` ⊂ `test_env_allowlist_reverse.py::test_consumed_env_vars_are_allowlisted`. The forward/reverse split itself is justified.
- CLASS: TEST-DELETE (the expected-set test).

### RC-3 (med, ~6) — doc-as-test prose assertions
- `test_readiness_doc_claims.py` (phrases in `docs/ops/rollback.md`, `docker-deployment.md`); `test_ops_detection_floor.py` (`"PLANNED"`/`"NOT DEPLOYED"`/`"unclosed"/"residual gap"`). The executable invariant (`BOT_HEALTH_CHECK_ENABLED is False` at `:45-47`) is already asserted.
- CLASS: TEST-UPDATE (keep executable invariants; drop/narrow prose).

### RC-4 (med, gap) — NO coverage of `.github/workflows/ci-nightly.yml`
- `test_docs_ci_parity.py:89-90` defines only `_CI_YML`/`_CI_SEED_YML`. The nightly tier (no marker exclusion, serial `-p no:xdist`, `cancel-in-progress`) is the suite's only serial backstop.
- CLASS: TEST-UPDATE (add `_CI_NIGHTLY_YML`).

### RC-5 (low, 4) — hardcoded third-party image tags in an allowlist
- `test_compose_hardening.py:632-638,780-820`; `test_compose_contract.py` docs-table check. Intentional pins; churn cost.
- CLASS: BEST-PRACTICE (acceptable).

### RC-6 (low, 1) — `test_csrf_trusted_origins._prod_env:29-70` re-implements `conftest._prod_env_overrides`
- CLASS: TEST-REWRITE.

### RC-7 (low, 3) — `apps/core/tests/test_deploy_workflow.py` (other block) is a weaker subset of `src/backend/tests/test_deploy_workflow.py`
- CLASS: TEST-DELETE (out of block).

### RC-8 (low, ~10) — negative-only assertions without a positive counterpart
- `test_nginx_config.py:158-166` (`"/0" not in line`); `test_deploy_workflow.py::test_deploy_retains_manual_environment_approval` (`"workflow_run" not in triggers`). The block's own `12-VAL-003` docstring names this hazard.
- CLASS: BEST-PRACTICE.

### RC-9 (low) — subprocess settings-import tests assert REAL prod-security invariants — highest value in the block
- `test_settings_secrets.py` (SECRET_KEY/BOT_TOKEN/TRANSLATE key/REDIS_URL/CSRF_ORIGINS/BOT_TOKEN_REQUIRED fail-closed matrix); `test_settings_defaults.py`; `test_deploy_check_env_parity.py` (prod imports under ci.yml's deploy-check env).
- CLASS: BEST-PRACTICE (keep verbatim).

### RC-10 (low) — `test_cache_version_durability.py` reads LocMem `_expire_info` and pins a hypothetical defect (documented "RED-proof")
- CLASS: BEST-PRACTICE (acceptable).

### Assertion-style inventory (summary)
- Structural/parsed: `test_compose_contract.py` (ruamel), `test_deploy_workflow.py` (ruamel for triggers), `test_deploy_check_env_parity.py`, `test_settings_*`, `test_env_allowlist_reverse.py` (AST), `test_session_policy.py` (AST), `test_cache_version_durability.py` (AST).
- Raw-text: `test_docs_ci_parity.py` (all YAML as text, by design), `test_ci_image_coordinate.py`, `test_compose_hardening.py` (`_service_block`), `test_restore_test_workflow.py`, `test_readiness_doc_claims.py`, `test_ops_detection_floor.py` prose.
- Subprocess: `test_settings_defaults.py`, `test_settings_secrets.py`, `test_log_mask_key_validation.py`, `test_oneshot_settings.py`, `test_prod_logging.py`, `test_csrf_trusted_origins.py`, `test_bot_username_validation.py`, `test_deploy_check_env_parity.py`, `test_ops_detection_floor.py` (healthcheck script).

### Already resolved
- G4 positional `.PHONY` parsing → now collects all `.PHONY` lines (`test_docs_ci_parity.py:320-335`).
- G7 prod-config guards → extensive `config/settings/tests/*`.
- Magic number `8` → derived (`_app_service_count_with_image_tag`).
- Duplicated `_service_block` → extracted to `_compose_helpers.py`.
- Duplicated `_run_in_subprocess`/prod-env builder → `config/settings/tests/conftest.py` (residual: `test_csrf_trusted_origins._prod_env`).
- G6 `config/settings/test_migrations.py` still matches `test_*.py` — observation only.

### Missing coverage
| Behavior | Source | Why critical | Location |
|---|---|---|---|
| `ci-nightly.yml` contract (no marker exclusion, serial `-p no:xdist`, `cancel-in-progress`) | `.github/workflows/ci-nightly.yml` | Only serial backstop, currently untracked + unasserted | `test_docs_ci_parity.py` |
| `ci.yml` `test-full` marker exclusion `not (seed)` | `ci.yml` `test-full` | Pre-merge tier unpinned | `test_docs_ci_parity.py` |
| `deploy-check` job runs `check --deploy --fail-level WARNING` | `ci.yml` `deploy-check` | Only the env block is parity-checked | `test_deploy_check_env_parity.py` |
| gunicorn `graceful_timeout` vs `stop_grace_period` arithmetic | `gunicorn.conf.py`, `docker-compose.prod.yml` | Only `>= 30` asserted | `test_deploy_workflow.py` |
| `docs/ops/VERIFY_TESTS_INSTRUCTIONS.md` correctness | that file | Operator docs can drift from the pinned tiers | `test_docs_ci_parity.py` |

### Duplicates
- `test_env_allowlist.py:75-93` ⊂ `test_env_allowlist_reverse.py`.
- `test_compose_hardening.py:280-286` ⊂ `test_compose_contract.py::test_every_declared_capacity_limit_is_paired_and_env_substituted`.
- `test_compose_hardening.py:222-259` ≈ `::test_no_shipped_compose_file_uses_a_floating_image_tag`.
- `test_ops_detection_floor.py::test_both_signals_have_a_healthcheck_declared` ≈ `test_compose_contract.py::test_prod_backup_declares_a_freshness_healthcheck`.
- `apps/core/tests/test_deploy_workflow.py` ⊂ `src/backend/tests/test_deploy_workflow.py` (cross-block, out of scope).
- `test_csrf_trusted_origins._prod_env` ≈ `conftest._prod_env_overrides`.

### Uncertain
- Block run status not measured (Docker/bash restrictions in that window).
- Subprocess count / fast-gate cost not measured.
- `_DOCS_OPS.glob("*.md")` postgres-tag ban currently holds — not verified.

---

## Block 13 — Search: FTS, cache, query construction, autocomplete & preferred city

### RC-1 (HIGH, 3) — rate-limit tests patch the guard OFF instead of exercising the counter
- `test_search_api.py:299-312` monkeypatches `rate_limit_check → False` then asserts 429. `test_autocomplete.py:157-174` asserts against `RateLimitBudget.SEARCH_PAGE.requests` inside an autocomplete test (both are 30 today → vacuous the moment they diverge). No per-IP key-isolation test (`rate_limit.py:54-56`, `client_ip.py`).
- CLASS: TEST-REWRITE.

### RC-2 (med, ~8) — search-cache tests read LocMemCache internals
- `test_search_cache.py:46-82` (`_connections`, `_cache`, `":1:"` prefix stripping) used at `:706,802,821,886`. `:745-782` asserts a patched producer's call count.
- CLASS: TEST-REWRITE (assert via `build_search_cache_key` + `cache.get`).

### RC-3 (med, 2) — SLO wall-clock test + (healthy) query-count budget
- `test_search_slo.py:89-146` (median ≤ 2000 ms, N=7) — inherently host-load dependent. `test_search_query_count.py:65` `_QUERY_BOUND = 72` is justified/documented (healthy).
- CLASS: BEST-PRACTICE (SLO → `slow`/nightly).

### RC-4 (low, ~5) — redaction coverage duplicated across `test_redact_search_query.py` and `test_search_query_key.py`
- `:49-58` ≈ `:156-173`; `:155-167` ≈ `:165-173`; `:84-87` ≈ `:103-106`. Genuine privacy contract otherwise covered (`test_search_view.py:1567-1604` real `RedactingJsonFormatter`).
- CLASS: TEST-DELETE (dedupe).

### RC-5 (med, ~20-30) — `test_autocomplete_template.py` greps SVG paths, JS identifiers, Tailwind classes, SRI hashes, and other apps' templates
- `:55-347` (e.g. `:255` `d="M5 9l7 7 7-7"`, `:293` `classList.add('rotate-180')`, `:204,209`). Prior E2/E8 still present. File lives in `search/tests` but asserts `ads/list.html`, `ads/detail.html`, `cabinet/*`.
- CLASS: TEST-REWRITE / TEST-DELETE (keep `hx-get`/`hx-target`/dropdown id).

### RC-6 (low, 3) — fuzzy "equivalence" test re-derives difflib by construction; stale FTS-trigger comment
- `test_search_fuzzy.py:77-99`; `test_autocomplete.py:737-739` ("no search_vector trigger" — false).
- CLASS: BEST-PRACTICE / DOC-UPDATE.

### Prior-audit re-check
- **E1** (status-only assertions): PARTIALLY RESOLVED (`test_nul_byte...`, `test_legal_query_result_ids_unchanged...` added); autocomplete structure-only assertion remains (`test_autocomplete.py:99-139`).
- **E2** (brittle template assertions): NOT RESOLVED (RC-5).
- **E3** (`User.DoesNotExist = Exception`): OUT OF BLOCK (`test_send_alerts.py`, Block 14).
- **E4** (FTS/category conflation): RESOLVED (`test_search_view.py:566-624` uses matching text; `:473-539`).
- **E5** (redundant fixtures): PARTIAL — 3 near-identical `cache.clear()` fixtures remain (`test_autocomplete.py:89-97,304-307`, `test_search_view.py:1947-1955`).
- **E6** (inefficient per-ad loops): NOT RESOLVED (still loop-built at `test_search_view.py:1203-1210,1230-1237,1257-1264,1925-1932,1100-1109`).
- **E7** (stale comments): PARTIAL (one stale comment remains, RC-6).
- **E8** (misplaced tests): STILL PRESENT (RC-5 cross-app template assertions).
- **E9** (coverage gaps): partially closed; see table.

### Missing coverage
| Behavior | Source | Why critical | Location |
|---|---|---|---|
| Per-IP key extraction / X-Forwarded-For for search+autocomplete limits | `client_ip.py`, `rate_limit.py:54-56` | Abuse protection claim | `test_autocomplete.py` |
| Autocomplete budget uses `AUTOCOMPLETE.requests` | `enums.py:56-82` | Wrong constant masked | `test_autocomplete.py:157` |
| `SEARCH_CACHE_MAX_ENTRY_BYTES` real 512 KiB ceiling | `cache.py:56` | Only 1-byte monkeypatch tested | `test_search_cache.py` |
| `_rank_cache_hit_page` out-of-range page on warm cache | `fts.py:170-174` | Branch untested | `test_search_rank_page.py` |
| Relevance ranking asserted (order, not membership) | `fts.py:92-94,111-112` | DATE_NEW = relevance-first unverified | new `test_search_rank.py` |
| `?sort=price_high`/`date_old` FTS ordering | `fts.py:99-112` | Only `PRICE_LOW`/default exercised | `test_search_view.py` |
| Search-cache read fail-open on outage | `cache.py:181-192` | Only rate-limit fail-open asserted | `test_search_cache.py` |
| `all_categories` in cache key → narrowed/whole isolation e2e | `cache.py:143` | Key-level only | `test_search_view.py` |
| Entity-suggestion dedupe on city/category text collision | `entity_suggestions.py` | Single generic text tested | `test_autocomplete.py` |

### Duplicates
- `test_autocomplete.py:451-455` ≈ `test_search_query_key.py:205-210`; `:408-413` ≈ `:191-196`; `:421-428` ≈ `:212-217`.
- `test_autocomplete.py:316-322` ≈ `test_redact_search_query.py:110-118`; `:330-347` ≈ `:120-132`.
- `test_search_fuzzy.py:77-107,180-199` ≈ `test_fts_service.py:199-235`.
- `test_search_cache.py:95-112` ≈ `:609-625`; `:285-309` ≈ `:627-632`.

### Uncertain
- "Never lengthens" redaction invariant may be sample-dependent.
- `test_search_slo.py` actual flake probability.
- `_get_cache_keys` Redis-portability not exercised.

---

## Block 14 — Search: saved searches & alert delivery

### RC-1 (HIGH, ~3) — the `uq_saved_search_ad` unique constraint is never asserted; idempotency tests pass without it
- `test_alert_query.py::test_ignore_conflicts_skips_duplicates` asserts `count == 1` where `record_notifications` returns `len(ads)` unconditionally (`alert_query.py:146`). No `IntegrityError` test against `models.py:216-221` — unlike the sibling constraint proven at `test_popular_search_integrity.py:97,175`.
- CLASS: TEST-REWRITE.

### RC-2 (med, ~6) — `test_send_alerts.py` unit tests assert mock-call orchestration
- `:48-83,85-120,123-164,167-199,202-240,304-335` (`cmd._format_digest = MagicMock`, `mock_sleep.assert_awaited_once_with(2.0)`, `User.objects.aget` patched). Retry/backoff is better covered end-to-end in `test_send_alerts_daily.py`.
- CLASS: TEST-UPDATE.

### RC-3 (med, 1) — counter-leak-on-`submit`-failure branch untested
- `immediate_alerts.py:190-197` (`except BaseException: _in_flight_batches -= 1; raise`). Drop path IS covered (`test_immediate_alerts_backpressure.py:22-69`).
- CLASS: TEST-REWRITE (add).

### RC-4 (low, 2) — `test_records_notification_idempotently` ≈ `test_republish_submits_nothing_on_second_call`
- `test_alert_query.py:762-817` vs `:892-932` (second is a strict subset).
- CLASS: TEST-DELETE.

### RC-5 (low, cross-module) — `_SyncExecutor` defined in `test_alert_query.py:70-113`, imported by `test_immediate_alerts.py:25`
- CLASS: BEST-PRACTICE (move to conftest).

### Already resolved
- Audience gate now real user states (`test_alert_audience_gate.py:60-63,289-380`).
- Immediate path "records then drops" (`test_alert_query.py:828-890`).
- Daily path marks delivered (`test_send_alerts_daily.py:127-198`).
- `_run_send` exception narrowing + retrievable dispatch failure.
- Digest per-user cap (`test_send_alerts_daily.py:45-124`).
- Hostile markup escaped (`test_send_alerts.py::TestHostileMarkupEscaped`).

### Missing coverage
| Behavior | Source | Why critical | Location |
|---|---|---|---|
| `uq_saved_search_ad` enforced | `models.py:216-221` | `ignore_conflicts` is a silent no-op without it | `test_alert_delivery.py` |
| Counter-leak guard when `submit` raises | `immediate_alerts.py:190-197` | Permanent in-flight leak | `test_immediate_alerts_backpressure.py` |
| "New since last run" date-window boundary | `send_alerts.py:318-414` | Spec wording; unasserted | `test_send_alerts_daily.py` |
| `last_notified_at` written by the immediate path | `immediate_alerts.py:168-169` | Product-visible state | `test_alert_query.py` |
| `_select_digest_ads` dedupe across overlapping searches | `send_alerts.py:182-198` | Double-counting | `test_send_alerts_daily.py` |
| Grouping must not merge across languages | `send_alerts.py:125-137,372-385` | Only same-query/diff-category tested | `test_send_alerts_daily.py` |
| `SEARCH_ALERT_MATCHED` analytics per contributing search | `send_alerts.py:407-438` | Stated telemetry contract | `test_send_alerts_daily.py` |
| `mark_delivered` → False when no row | `notification_delivery.py:59-74` | Unasserted | `test_alert_delivery.py` |

### Duplicates
- `test_alert_query.py:762-817` ≈ `:892-932`.
- `test_send_alerts.py:48` ≈ `test_immediate_alerts.py::TestRetryAfterBackoff::test_429_retry_after_honored`; `:85` ≈ `::test_transient_error_uses_capped_backoff` (legitimate parallel coverage).

### Uncertain
- A "User model patched / DoesNotExist" test attributed to this file was not found (may live elsewhere).

---

## Block 15 — Users: auth, login tokens, consent & PII

### RC-1 (HIGH, ~11) — `account_state` seam not a truth table; `account_state_q` ↔ `get_account_state` equivalence not derived
- `test_account_state.py:303-374` hand-writes one case per conjunct and re-checks flags by hand. Production `account_state.py:71-109`. Adding a 7th flag turns nothing red (`is_active` already had to be patched once).
- CLASS: TEST-REWRITE (parametrized truth table + new-flag tripwire).

### RC-2 (HIGH, 1 fn) — `can_store_personal_data` has NO direct test
- Only referenced in comments (`test_account_state.py:552,575`); production `account_state.py:230-270` (deliberate `is_active` omission + `consent_given_at` term). Its two distinguishing behaviours are unreachable via `can_create_ad`.
- CLASS: TEST-UPDATE.

### RC-3 (HIGH, 2 files) — PII erasure asserted against a hand-picked subset; erasure↔inventory parity untested
- `test_deletion.py:271-283` asserts 5 fields; `pii_inventory.py:75-201` declares `preferred_city` (NULL) and `password` (CLEAR, "NOT implemented today"); `test_pii_inventory.py:288` only proves columns are declared, not erased.
- CLASS: TEST-UPDATE (derive expected set from `PII_ERASURE_ENTRIES`).

### RC-4 (med, ~9 pairs) — consent view/record/API triplication; API "parity" compares booleans only
- `test_consent_api.py:170` (`test_state_equals_html_flow`), `:137` vs `test_consent.py:63` vs `test_consent_records.py:27`.
- CLASS: TEST-REWRITE.

### RC-5 (low, 1) — `test_login.py:369` asserts `session_key is not None` instead of `"_auth_user_id" in session`
- CLASS: BEST-PRACTICE.

### RC-6 (low, ~6) — source-substring ownership tripwires dominate the assertion style
- `test_login_token.py:599,613-664`; `test_admin_deactivate_user.py:439-478`; `test_account_state.py:528`.
- CLASS: BEST-PRACTICE (labels only).

### File ownership map (consent)
| File | Owns | Overlaps |
|---|---|---|
| `test_consent.py` | HTML view layer: cookies, redirects, 405, auth-required withdraw, banner, DTO | state mutations; delete-row effects |
| `test_consent_records.py` | audit rows: choice, categories, anonymized IP, truncated UA, session_key; `_anonymize_ip` | state mutations |
| `test_consent_api.py` | `/api/v1/consent/*`, `/api/v1/auth/logout/`: 401 matrix, 405, 429, session flush | state parity |
| `test_consent_context.py` | context processor: derivation, legacy cookie, 12-month reprompt, `?ref=` | — (clean) |
| `test_consent_actor.py` | actor/action_source, admin forgery, legal_hold, ledger survives deletion, actor-window sweep | purge actor window |
| `test_purge_consent_records.py` | command boundaries, never-delete, dry-run, legal hold, ordering | actor window |

### Already resolved
- F2 (duplicate nonexistent-token→410): resolved (distinct no-row vs wrong-hash).
- F3 (duplicated `_make_user`): resolved (root `make_user`).
- F4 (weak assertions / dead `if IP is not None`): resolved for `test_deletion.py:536-558`; residue at `test_consent_records.py:140-141`.
- F5 (consent cookie side effects): resolved (values + `secure` flags + city expiry).

### Missing coverage
| Behavior | Source | Why critical | Location |
|---|---|---|---|
| `account_state_q` ≡ `get_account_state` over the flag space | `account_state.py:71-109` | Silent seam drift | `test_account_state.py` |
| `can_store_personal_data` matrix incl. `is_active=False` carve-out | `account_state.py:230-270` | Bot support-intake + create gate | `test_account_state.py` |
| `preferred_city` NULL on withdraw; `chat_id` retained | `deletion.py:203`, `pii_inventory.py:133-147` | Declared erasure unasserted | `test_deletion.py` |
| Erasure-vs-inventory parity | `pii_inventory.py:75-201` | New PII column never caught | `test_deletion.py` / `test_pii_inventory.py` |
| LoginToken expiry ±1s boundary | `login_token.py:118,318,331,452,480` | `TOKEN_TTL_SECONDS=300` boundary untested | `test_login_token.py` |
| Real concurrent claim/consume (only a mocked `LOST_RACE`) | `login_token.py:381-391,476-486` | Zero-TOCTOU never driven on PG | `test_login_token.py` |

### Duplicates
- accept at 3 layers (`test_consent.py:63`, `test_consent_records.py:27`, `test_consent_api.py:137`); decline at 3 layers.
- `test_consent.py:432` ≈ `test_deletion.py:213`.
- deleted→403/no-record at 3 places (`test_consent.py:138,155`, `test_consent_records.py:38`).
- `test_consent_actor.py:291` ≈ `test_purge_consent_records.py::TestActorWindow`.

### Uncertain
- `test_consent_records.py:140` `if record.ip_address is not None` may be vacuous in-container (not run).
- `_DECISION_DAYS` bound not verified.

---

## Block 16 — Categories, lookups & locations

### RC-1 (HIGH, 4) — `load_catalog` tests assert only non-emptiness, never the YAML source-of-truth structure
- `test_load_catalog.py:62,83`; structural invariant lives outside the block (`apps/seed/tests/test_seed.py:1221` hardcoded 171 slog set; `search/tests/test_feature_catalogue_invariant.py:45`).
- CLASS: TEST-UPDATE (derive expected slugs + per-group counts from `categories.yaml`, like `test_load_cities.py:24` does from `cities.json`).

### RC-2 (HIGH, missing) — `load_catalog` idempotency / rename / re-run semantics untested
- Contrast `test_load_cities.py::test_idempotent_re_run_does_not_duplicate:72`. Builder is `update_or_create` (`builder.py:191,202,295,393`); `new_slug` → `_rewrite_yaml` rename path untested.
- CLASS: TEST-UPDATE (add).

### RC-3 (med, 2) — `--no-rewrite` vs rewrite path only partially exercised
- `test_load_catalog.py:46`; `load_catalog.py:38-74`; `builder.py:535` (`_rewrite_yaml` atomic replace).
- CLASS: TEST-UPDATE.

### RC-4 (low, 1) — `--config` test asserts count only, not the slug set
- `test_load_cities.py:116`.
- CLASS: BEST-PRACTICE.

### RC-5 (med, ~13) — SWR tests hand-build `_CacheEntry` dicts mirroring the private serialization
- `test_submenu_swr.py:43`; `test_lookup_cache_swr.py:61`; `swr_cache.py:56-77`. Also `"test:submenu_swr"` literal key never goes through the production key builder.
- CLASS: BEST-PRACTICE.

### RC-6 (low-med, 6) — `TestSubmenuSwr` provides near-zero submenu-specific coverage
- `test_submenu_swr.py:56-228`; only `TestSubmenuCacheIntegration:304-350` touches the endpoint.
- CLASS: TEST-DELETE / TEST-REWRITE.

### RC-7 (low, 2) — `caplog.text` substring assertions instead of behavior
- `test_categories.py:154,170`.
- CLASS: BEST-PRACTICE.

### RC-8 (med, 6) — lookup-signal tests pin an argument that has no behavioral effect
- `test_categories.py:227-289` (`invalidate_category(category_id)` ignores the arg — `lookup_resolution.py:134-146`).
- CLASS: TEST-REWRITE (assert version increment).

### RC-9 (med, missing) — `CategoryPath.clean()` self-reference and `unique_together` have ZERO coverage
- `models.py:102,109-116`.
- CLASS: TEST-UPDATE (add).

### RC-10 (med, missing) — multi-parent `CategoryPath` navigation from YAML untested
- `builder.py:_load_category_paths:464`; `category_paths:` section in `categories.yaml`.
- CLASS: TEST-UPDATE (add).

### RC-11 (low, 3) — `Category.get_name` happy path (direct locale hit) and `name_i18n=None` untested
- `test_categories.py:316-346`; `models.py:54-64`.
- CLASS: TEST-UPDATE.

### RC-12 (low, 2) — fuzzy cutoff constants and the ambiguity rule untested
- `test_fuzzy.py:26-40`; `fuzzy.py:22`; `fts.py:279-293` (ambiguous → no guess, 08-VAL-003).
- CLASS: TEST-UPDATE.

### RC-13 (low, 3) — Cyrillic names in `test_city_suggestions.py` imply name matching that never happens (slug-only)
- `test_city_suggestions.py:16`; `city_suggestions.py:30`.
- CLASS: BEST-PRACTICE.

### RC-14 (low-med, 1) — `city_fuzzy` Tier-2 passes the raw (un-casefolded) query while Tier-1 casefolds
- `city_fuzzy.py:42-46` vs the corrected `categories/fuzzy.py:44-45`. Not discriminatingly tested.
- CLASS: TEST-REWRITE (add a discriminating case) — possible production defect, flagged only.

### RC-15 (low, 2) — `test_submenu.py:45-78` ≈ `:80-100` (locale isolation)
- CLASS: TEST-DELETE (merge).

### Cache-key-convention relationship
- `src/backend/tests/test_cache_key_convention.py` is the STRONGER superset (exact-key equality, `%` check, numeric version segment, combined namespace, `teardown_method → cache.clear()`:54) and is the canonical cross-cutting (13-PERF-006) guard.
- `apps/lookups/tests/test_cache_key_convention.py` is a weaker subset (substring membership, `:122-155` overlaps) whose ONLY unique contributions are `test_resolved_lookup_key_version_segment_present:110` and `test_lookup_version_key_exists:152`. It has no `cache.clear()` of its own.
- Relationship: same block-boundary contract, two layers (cross-cutting vs per-app).

### Already resolved
- G1 (misapplied `unit` markers on DB tests): resolved.
- G2 (redundant city count test): resolved — single set-equality canary from `cities.json`.
- G4 (hardcoded 15 cities): resolved for cities (residual: the 171-slug set lives in `apps/seed/tests`).
- G7 (cache invalidation on tree bump): resolved (`test_categories.py::TestCategoryStructureInvalidatesTreeVersion`, `test_submenu_swr.py:328`).
- B19 items (submenu hard catalog coupling, duplicate `tree` fixture, localization fallback): resolved.

### Missing coverage
| Behavior | Source | Why critical | Location |
|---|---|---|---|
| Full catalog invariant vs `categories.yaml` | `categories.yaml`, `builder.py` | Truncated load passes | `test_load_catalog.py` |
| `load_catalog` idempotency + `new_slug` rename + `--no-rewrite` rewrite | `builder.py:295,152`, `load_catalog.py:34` | Runs every deploy | `test_load_catalog.py` |
| Multi-parent `CategoryPath` from YAML | `builder.py:464` | Headline feature | `test_categories.py` |
| `CategoryPath.clean()` self-reference + unique | `models.py:102,109-116` | Only self-loop guard | `test_categories.py` |
| `Category.get_name` direct hit / `name_i18n=None` | `models.py:54-64` | Happy path unasserted | `test_categories.py` |
| Fuzzy ambiguity → no guess (08-VAL-003) | `fts.py:279-293` | Correctness requirement | `test_fuzzy.py` |
| Cutoff constants pinned (0.8 / 0.6) | `fuzzy.py:22`, `city_fuzzy.py:22` | Ruled constants | `test_fuzzy.py` / `test_city_suggestions.py` |
| `city_fuzzy` Tier-2 case sensitivity | `city_fuzzy.py:46` | Ladder inconsistency | `test_city_suggestions.py` |
| Lookup-level cache-outage fail-open via signals | `lookups/signals.py:33` | Only the categories tree-version outage covered | `test_lookup_invalidation.py` |
| `LookupCacheService.invalidate_group`/`invalidate_all` | `cache_service.py:157-181` | Public API unverified | `test_lookup_cache_swr.py` |

### Duplicates
- `apps/lookups/tests/test_cache_key_convention.py` ⊂ `src/backend/tests/test_cache_key_convention.py`.
- Three copies of stale-hit (`test_submenu_swr.py:82`, `test_lookup_cache_swr.py:105,307`), cold-miss (`:183` ≈ `:169` ≈ `:355`), single-flight (`:249` ≈ `:618`), stale-to-all (`:108` ≈ `:674`).
- `test_categories.py:227-289` (four mock-argument tests) overlaps `test_lookup_cache_swr.py:540` and `test_lookup_invalidation.py`.
- `test_categories.py:291` ≈ `test_lookup_invalidation.py:144`.
- `test_lookup_cache_swr.py:507` ⊂ `test_lookup_invalidation.py:68`.

### Uncertain
- `city_fuzzy` Tier-2 divergence: confirmed in code, not run to prove outcome.
- Whether `test_load_catalog_fails_fast_on_empty_categories` hits the real guard or the empty-YAML early return (`builder.py:110-113`).
- All 119 tests pass; findings are quality/coverage, not failures.

---

## Block 17 — Cabinet, currencies, trust, analytics & API import rule

### RC-1 (HIGH, 2) — a "recompute lock" test never calls the command
- `test_recompute_command.py:338-432` (`TestRecomputeRowLockConcurrency`): neither thread calls `call_command`; the main thread hand-opens `select_for_update()` (`:395-399`) and writes the value itself (`:402`). `test_recompute_locks_batch_with_select_for_update` (`:113-135`) only asserts some `select_for_update` happened. Production `recompute_normalized_prices.py:117-127`.
- CLASS: TEST-REWRITE.

### RC-2 (HIGH, harness-wide) — import-rule harness cannot detect an unregistered `/api/v1/` route
- `apps/api/tests/test_import_rule.py::test_pairing_table_rows_satisfy_import_rule` iterates `PAIRING_TABLE` only; nothing reconciles the live resolver against it. `test_urls.py` checks 3 arbitrary 404s only.
- CLASS: TEST-UPDATE (resolver↔PAIRING_TABLE equality test).

### RC-3 (med, 1) — `test_urls.py` asserts a hand-copied route list
- `test_urls.py:36-38`; no assertion `/api/v1/dashboard/`, `/consent/accept/`, `/auth/logout/`, `/moderation/queue/` resolve.
- CLASS: TEST-UPDATE.

### RC-4 (med, ~9) — moderation dashboard view tests patch `get_moderation_stats` (prior F1 partially unresolved)
- `test_views.py:388-391,423-517`; only `test_moderation_dashboard_end_to_end:523` uses real rows.
- CLASS: TEST-REWRITE.

### RC-5 (med, ~20) — trust formula assertions partly self-referential / environment-coupled
- `test_trust_calculator.py` reproduces the formula in comments; the global `CONTACT_INITIATED` denominator (`trust_calculator.py:159-165`) makes boundary tests inject cross-user events; duplicate `make_user(990023001)` at `:291,318`.
- **Prior D6 `min_responses=5`: CONFIRMED non-existent** — `trust_calculator.py:165` has no gate.
- CLASS: TEST-UPDATE.

### RC-6 (med, 0) — rollup tests insert events directly; no real publish→event→rollup path; no dedup property
- `test_rollup_daily_metrics.py:33-55`, `test_ads_published.py`, `test_analytics_models.py`; production `auto_moderation.py:268-269`.
- CLASS: TEST-REWRITE.

### RC-7 (low, few) — `unit` + `django_db` contradiction still present; `flaky` stacking
- `test_analytics_models.py:30` (`pytestmark = [django_db, unit]`) — prior F6 still open. `test_recompute_command.py:333-337` stacks `slow`+`transaction`+`concurrent`+`xdist_group`+`flaky`.
- CLASS: BEST-PRACTICE.

### RC-8 (low, 3-4) — cabinet thin-view tests re-pin service semantics; `language == "en"` artifact assertion
- `test_cabinet_sections.py` (`test_create_disable_edit_delete_workflow`) vs `test_saved_search_write_api.py`.
- CLASS: TEST-DELETE (partial) / TEST-UPDATE.

### RC-9 (low, 6) — `auto_now` framework-field assertions; SeedExclusion simulates `_clean` by hand
- `test_analytics_models.py:~150-200`; `test_rollup_daily_metrics.py:~470-540`.
- CLASS: TEST-DELETE / TEST-REWRITE.

### API parity harness assessment
- **Works:** per-row AST import-subset enforcement (mirrors union + `ALLOWLIST` + stdlib/django), tuple-mirror support, duplicate-row guard.
- **Misses:** (1) completeness — unregistered route is unguarded (RC-2); (2) `ALLOWLIST` (7 entries) is per-endpoint additive with no cap/review trigger; two entries (`users.services.account_state`, `cabinet.views.api.saved_searches`) weaken the subset invariant; (3) one-directional (over-pruning an API import passes); (4) `_stdlib_and_django` exempts `django.*` only (correct, undocumented).
- Verdict: enforces the subset direction of rule 18 for registered modules only.

### Already resolved
- F2 (nonexistent-token→410 duplicates): not in block.
- F9 (analytics e2e): partially — `test_moderation_dashboard_end_to_end:523`, `TestSellerStatsCache`; still missing real publish→event + dedup.
- F6 (`unit` + `django_db`): STILL PRESENT.
- D6 (`min_responses`): confirmed non-issue.
- `TestBannedSellerRelistKnownGap`: removed.
- G7 (PriceNormalizer cache/invalidation/seed exclusion): resolved.

### Missing coverage
| Behavior | Source | Why critical | Location |
|---|---|---|---|
| `AD_PUBLISHED` from a real publish; no dup on re-publish | `auto_moderation.py:268-269` | Dedup + side effect unasserted | `test_ads_published.py` |
| Rollup over real action→event flow | `rollup_daily_metrics.py` | Hand-inserted events only | `test_rollup_daily_metrics.py` |
| Every live `/api/v1/` module is in `PAIRING_TABLE` | `apps/api/urls.py` | Rule 18 completeness | `test_import_rule.py` |
| Real row lock in `recompute_normalized_prices` | `recompute_normalized_prices.py:117-127` | Lost-update guard (RC-1) | `test_recompute_command.py` |
| Normalizer boundaries: 0, negative, >4dp rounding, HALF_UP tie | `price_normalizer.py:70-72` | Rounding contract | `test_price_normalizer.py` |
| `PriceNormalizer._rate_cache` instance-local precedence | `price_normalizer.py:110-120` | Docstring claims it | `test_price_normalizer.py` |
| Trust badge unsaved user (`pk is None`) + `request=None` | `trust_tags.py:70-72,100-106` | Guards untested | `test_trust_tags.py` |

### Duplicates
- `test_cabinet_sections.py` workflow ≈ `test_saved_search_write_api.py` happy paths.
- `test_favorites_badge.py` ≈ `test_favorites_list_api.py` counts ≈ `apps/ads/tests` favorites service.
- `test_trust_tags.py::_render` ≈ `test_trust_prefetch.py::_render`.
- `test_ads_published.py::seller_ads` ≈ `test_seller_stats.py::seller_with_ads`.
- Two scoring algorithms coexist (`calculate_seller_trust_score` vs `TrustCalculator`) — architectural hazard for docs.

### Uncertain
- Whether `AD_PUBLISHED` dedup is genuinely uncovered project-wide (moderation tests assert event presence).
- Whether `unit`+`django_db` is enforced-failing under `strict_config`.

---

## Block 18 — Seed app

### RC-1 (HIGH, 59) — `test_download_seed_photos.py` is an ops-script test misfiled under `apps/seed/tests/`
- Loads `scripts/download_seed_photos.py` via `importlib` (`:20-26`); docstring says it runs standalone. All HTTP mocked (pure unit, correctly fast-gate).
- CLASS: relocate + DOC-UPDATE.

### RC-2 (HIGH, ~14) — module-level `pytestmark` blanket-excludes non-seeding unit tests from the fast gate
- `test_seed.py:43` module `django_db`+`integration`; `TestSeedEnums:889-900` is pure unit; `TestUserGenerator:47`, `TestAdGenerator:143`, `TestAdGeneratorMultiLang:906` call generators directly. `pyproject.toml:175` defines `seed` narrowly.
- CLASS: TEST-UPDATE (split; the established pattern is `test_seed_generators_unit.py:4-11`).

### RC-3 (med, 4) — `TestCityFixtures:1599` does real DB seeding but carries NO `seed` marker (fast gate); inconsistent with `TestLeafCategoryFiltering:1558`
- CLASS: TEST-UPDATE (harmonize).

### RC-4 (med, 8) — class-scoped `seeded_test_data` + global `_clean()` is safe ONLY via `xdist_group`
- `test_seed.py:1747-1748`; `conftest.py:63-113`; `seed_service.py:181-207`.
- CLASS: BEST-PRACTICE + DOC-UPDATE (guard/assert).

### RC-5 (HIGH, ~12) — seed tests assert "rows exist", not generated-data invariants
- `test_seed.py:166-184` (DRAFT weight unasserted), `:729-743` (views_count > 0 only), `:805-817` (existence only). Timestamp↔status coupling (`ads.py:485-510`) and `_deduplicate_drafts` (`:555-610`) unasserted.
- CLASS: TEST-REWRITE.

### RC-6 (med, 12) — `test_measure_nginx_rate_limit_keys.py` misfiled AND pins a knowingly-stale attribution rule
- `:19-27,166`; the `$body_bytes_sent == 0` discriminator broke after commit `cb798afa`.
- CLASS: TEST-DELETE (relocate) + DOC-UPDATE.

### RC-7 (low, ~6) — Unsplash/Pexels client tests near-duplicate; backoff delays never asserted
- `test_download_seed_photos.py:120/246,139/255,160/264,200/274,322,339`.
- CLASS: TEST-DELETE (parametrize) + TEST-REWRITE (backoff).

### RC-8 (med, 4) — `TestImageGeneratorManifest::test_manifest_loading` asserts the test's own dict; dead scaffolding
- `test_seed_generators_unit.py:108-134,136,159,175`; unused `setup_method`/`teardown_method`/`temp_dir`.
- CLASS: TEST-REWRITE + TEST-DELETE.

### RC-9 (med, ~4) — hardcoded 205 categories / 171 leaf slugs / 15 cities
- `test_seed_generators_unit.py:75`; `test_seed.py:1584,1616,1223-1395`. Prior G4 not resolved.
- CLASS: TEST-UPDATE (or DOC).

### RC-10 (HIGH, 0 — missing) — no test asserts "seed must never run in production"
- `seed.py` has no settings guard; `prod.py:115,207` only documents compose wiring.
- CLASS: TEST-ADD.

### RC-11 (low, 2) — `TestSeedPopularSearchKeys:1867` docstring claims `_clean` ran (it did not)
- CLASS: DOC-UPDATE.

### RC-12 (low, 7) — `test_seed_load_test_ads_command.py` is the strongest file (real writes); missing FTS-trigger + batch-size assertions
- `seed_load_test_ads.py:187-193`.
- CLASS: TEST-ADD.

### Marker audit
| File | Total | `seed` | `slow` | `real_images` | Verdict |
|---|---|---|---|---|---|
| `test_seed.py` | 67 | 32 | 0 | 1 | over-marked (blanket) + `TestCityFixtures` under-marked |
| `test_seed_generators_unit.py` | 9 | 0 | 0 | 0 | correct (`unit`); one vacuous test |
| `test_seed_load_test_ads_command.py` | 7 | 0 | 0 | 0 | correct |
| `test_download_seed_photos.py` | 59 | 0 | 0 | 0 | marker correct; misfiled |
| `test_measure_nginx_rate_limit_keys.py` | 12 | 0 | 0 | 0 | marker correct; misfiled; stale contract |

### Already resolved
- G1 (`test_download_seed_photos` "should be nightly"): corrected — it is pure unit, belongs in the fast gate (residual: relocation).
- G2 (redundant city tests): resolved.
- G7 (prod config guards): NOT resolved for seed (RC-10).

### Missing coverage
| Behavior | Source | Why critical | Location |
|---|---|---|---|
| Status↔timestamp coupling per status | `ads.py:485-510`; `ck_ads_published_at_if_published` | Non-trivial logic unasserted | `test_seed.py::TestAdGenerator` |
| `_deduplicate_drafts` ≤1 DRAFT per user | `ads.py:555-610` | Partial unique index guard | `test_seed.py::TestAdGenerator` |
| Status-distribution weights (draft ~0.2) | `ads.py:_weighted_status` | DRAFT weight unchecked | `test_seed.py::TestAdGenerator` |
| `DailyAdMetrics` excludes non-PUBLISHED | `analytics.py:216-230` | Only events checked | `test_seed.py::TestAnalyticsGenerator` |
| View-count recency weighting | `analytics.py:99-102` | Decay contract unasserted | `test_seed.py::TestAnalyticsGenerator` |
| Seed never runs in production | `seed.py` (no guard) | Core invariant | `config/settings/tests/` or new |
| FTS trigger populates `search_vector` after `bulk_create` | `seed_load_test_ads.py:187-193` | The reason `bulk_create` is safe | `test_seed_load_test_ads_command.py` |
| `--batch-size` chunking | same command | Only positivity validated | same |
| `_safe_get` backoff delays | `scripts/download_seed_photos.py:_safe_get` | Retry math | `test_download_seed_photos.py` |

### Duplicates
- `test_seed.py:92` ≈ `:213` (weak bulk_create count tests); `TestImageGeneratorTruthfulness:385` ≈ `TestImageGenerator:229`.
- `test_download_seed_photos.py` Unsplash/Pexels pairs.
- `test_seed.py:1165` ⊂ `:1529`, overlaps `:819`.

### Uncertain
- Marker policy for SeedService fixture-loader tests.
- xdist corruption risk of `TestSeedFilterCoverage` without the pin (inferred, not run).
- Whether the attribution record mandates seed-tree placement for the nginx tool tests.

---

## Block 19 — Telegram bot: ad-create flow

### RC-1 (HIGH, ~14) — step handlers assert FSM state / mock calls, never the persisted value
- `test_text.py:46-63`; `test_city.py:42-67` (`city_id=10` from a `MagicMock`); `test_price.py:143-166`; `test_category.py:329-354,380-402,440-465`; `test_ad_copy.py:48-79`.
- CLASS: TEST-REWRITE (copy flow) / BEST-PRACTICE (FSM steps paired with RC-2).

### RC-2 (CRITICAL, missing) — no end-to-end FSM walk producing a real, fully-populated ad row
- `cmd_post` only tested for greeting (`test_site_name_greeting.py:21,42,59,83`); the only pipeline tests seed data directly into state (`test_ad_create.py:53-121`); `submit_ad` always patched (`test_ad_create_submit_outcome.py:167-171,274-280`).
- The step-key ↔ `submit.py:126-157` read-key contract is asserted nowhere.
- CLASS: TEST-ADD.

### RC-3 (HIGH, ~10) — over-mocking the service layer
- `test_ad_copy.py:72-79` patches `copy_ad` with a `MagicMock`; the real `copy_service.copy_ad` (`ad_copy.py:18,55`) never runs.
- CLASS: TEST-REWRITE + TEST-ADD.

### RC-4 (med, ~11) — bot `test_ad_lifecycle.py` duplicates backend lifecycle/moderation tests (prior C1)
- `test_ad_lifecycle.py:19,73-311` vs `apps/ads/tests/test_ad_lifecycle.py:121-215`; backend even labels the mirrors "AD-001 parity".
- CLASS: TEST-DELETE (from bot tree) / TEST-MOVE.

### RC-5 (med, ~60) — blanket `transaction=True` + `concurrent` + single `xdist_group("bot_concurrent")` on DB-free tests
- 11 files (`test_ad_create.py:26-31`, `test_category.py:21-26`, `test_text.py:19-24`, `test_ad_copy.py:21-26`, ...). The group serializes the entire block onto one worker.
- CLASS: TEST-UPDATE.

### RC-6 (med, ~6) — weak/tautological assertions
- `test_ad_create.py:818-821` (`_get_ad_status` positive branch untested); `test_create_draft_ad.py:76-85` (implied negatives); `test_price.py:125-141`, `test_text.py:30-43,91-103` (`answer.assert_awaited_once()` with no content).
- CLASS: TEST-REWRITE.

### RC-7 (med, ~8) — artificial sentinel data
- `test_ad_create_submit_outcome.py:298` (`ad_id=1` with `submit_ad` patched), `:61` (`ad_id=-1`); `test_ad_create.py:141,174,236` (`{}` as photo dicts); `test_city.py:48,100,114,170,184`.
- CLASS: TEST-UPDATE.

### RC-8 (low, 2) — `test_ad_create_heartbeat_coverage.py:110-164` AST source-shape test (documented exception)
- CLASS: BEST-PRACTICE.

### RC-9 (low, 3) — staging-budget refusal tests use `assert_not_awaited` as a proxy for "no bytes written"
- `test_ad_create_staging_budget.py:110-120,186-197,324-358`; only `:156-157` lists the dir.
- CLASS: BEST-PRACTICE.

### RC-10 (low, 4 files) — fragmented hardcoded telegram ids (prior C4)
- `test_ad_create.py:36`, `test_ad_create_staging_budget.py:25` re-declare `_TEST_SELLER_ID` instead of importing `bot_helpers.TEST_SELLER_ID`; `test_ad_copy.py:128` bare `950000999` instead of the `stranger` fixture.
- CLASS: BEST-PRACTICE.

### RC-11 (low, 2) — exact English reply pins in `test_ad_create_submit_outcome.py:42-53` (documented deliberate)
- CLASS: BEST-PRACTICE (acceptable).

### RC-12 (low, ~8) — hand-rolled `MagicMock` state instead of `bot_helpers.build_state`/`build_message`
- `test_text.py:35-39,50-53`, `test_city.py:30-34`, `test_category.py`, `test_price.py`.
- CLASS: BEST-PRACTICE.

### Prior-audit re-check
- **C1**: NOT RESOLVED (RC-4).
- **C2**: PARTIALLY RESOLVED (real JPEG/staging/thumbnail integration exists: `test_ad_create.py:303-367`, `test_save_photo_integration.py:64-568`); the handler→`submit_ad` photo seam remains mocked (RC-2).
- **C3**: RESOLVED for this block (all rate-limit awaits are real).
- **C4**: PARTIALLY RESOLVED (RC-10).
- **C5**: NOT RESOLVED (marker semantics loose, RC-5).
- **C6**: RESOLVED (`BotCallbackPrefix` used; one bare `"price_free"` at `test_price_payload.py:127`).
- **C7**: IMPROVED (`test_ad_data_locale.py`); translation-failure path in submit untested.
- **C8**: MITIGATED (coarse single group).
- **C9**: RESOLVED but in the wrong tree (`test_ad_lifecycle.py:280-311`).

### Missing coverage
| Behavior | Source | Why critical | Location |
|---|---|---|---|
| Full FSM walk → persisted fully-populated ad | `handlers/ad_create/*`, `orm.py` | Step-key ↔ submit-key contract unasserted | new `test_ad_create_flow_e2e.py` |
| `process_photos` → real `submit_ad` → real `AdImage` | `photos.py:132-144`, `submission.py:379-389` | Handler↔service photo seam | `test_save_photo_integration.py` |
| `cmd_post` happy path (draft created + state) | `entry.py:35-65` | Only greeting tested | `test_ad_create.py` |
| `cmd_post` not-logged-in branch | `entry.py:44-49` | Guard untested | same |
| `process_preview` lock-timeout (55P03) branch | `submit.py:159-169` | Transient-contention recovery | `test_ad_create_submit_outcome.py` |
| `process_preview` cancel/unknown-text branches | `submit.py:239-243` | Untested | same |
| `translate_all_languages` failure in submit | `submit.py:107-113` | `mock_translate` always succeeds | `test_ad_create.py` |
| `_get_ad_status` positive branch | `orm.py:87-96` | Only `None` asserted | `test_ad_create.py` |
| `create_draft_ad` consent gate from the bot side | `orm.py:40-76` | Gate not asserted here | `test_create_draft_ad.py` |
| `process_features` malformed `feature:` int cast | `category.py:305-323` | Unhandled `int()` | `test_category.py` |
| Photo `file_size == MAX_PHOTO_BYTES` boundary | `photos.py:99` | `==` vs `>` untested | `test_ad_create.py` |
| Photo count boundaries (1 done / 6 refused) | `photos.py:45-60,81-87` | Untested | `test_ad_create.py` |
| `delete_draft` with zero images | `orm.py:143-169` | Only the 4-key case | `test_ad_create.py` |

### Duplicates
- `test_ad_lifecycle.py:168-258` ⊂ `apps/ads/tests/test_ad_lifecycle.py:125-215`; `:73-165` ⊂ backend moderation/ads.
- `test_create_draft_ad.py:22-105` ≈ `test_ad_lifecycle.py:57-70`.
- `test_ad_create.py:255-272` ≈ `:274-301`.
- `test_ad_create_staging_budget.py:87-120` vs `:122-157` (only the second checks "no file").

### Uncertain
- Whether the backend tree already asserts the analytics/audit side effects that make deleting the bot lifecycle file safe.
- `PhotoCountPayload` cap value not opened.
- Whether `TestProcessPhotos`'s class-level `django_db(transaction=False)` overrides the module `transaction=True`.

---

## Block 20 — Telegram bot: middlewares, account-state, rate limits, support & language

### RC-1 (CRITICAL, ~10) — handler tests verify mock call-plumbing, not outcomes
- `test_language.py:38-49,51-73` (only `assert_awaited_once` + `reply_markup is not None`); `test_site_name_greeting.py:17-48`; `test_login.py` delegation tests (`mock_contact.assert_awaited_once()`).
- CLASS: TEST-REWRITE.

### RC-2 (HIGH, 2) — middleware ORDER only partially pinned
- `test_main.py:105-117` asserts only `lang_idx < account_idx`; `:89` membership-only for `UpdateIdDedupMiddleware`; `test_db_connection_middleware.py:135-150` membership-only for the outer layer. Production `main.py::configure_dispatcher`.
- CLASS: TEST-UPDATE (assert the full ordered list + dedup first + DB outer-most).

### RC-3 (HIGH, missing) — login deep-link handler has ZERO negative-account-state coverage
- `test_login.py` contains no `is_banned`/`is_deleted`/`is_active=False`.
- CLASS: TEST-ADD.

### RC-4 (HIGH, whole file) — update-id dedup verified only against a monkeypatched cache
- `test_update_id_dedup.py:27,30,42,54`; TTL literal `86400` (`:27`) duplicates `DEDUP_TTL_SECONDS`; no TTL boundary; real idempotency never demonstrated.
- CLASS: TEST-REWRITE.

### RC-5 (med, several) — verbatim i18n string assertions couple tests to `ru`/`bs` catalog text
- `test_language_middleware.py:54`; `test_multi_lang_translation.py`; `test_lock_timeout_boundary.py` (full ru/bs sentences); `test_contact_us.py` (`"службой поддержки"`, `"Связаться с нами"`, `"Покупатель"`); `test_unsubscribe.py` (`"отключены"`, `"недействительна"`).
- CLASS: TEST-UPDATE.

### RC-6 (med, first ~20) — the largest class tests `_check_user_state`, a test-only seam production never calls
- `test_account_state_middleware.py:129-217,221-357`; production `permissions.py::__call__` (~`150-230`).
- CLASS: TEST-REWRITE.

### RC-7 (med, many) — duplicate rate-limit / greeting / recipient coverage across files
- `test_rate_limit_service.py:24-56` ≈ `test_contact_us.py`; `test_login_rate_limit.py` ≈ `test_login.py::TestLoginRateLimit`; `test_contact_deep_link_rate_limit.py::TestDeclinedAccountCovered` ≈ `TestPerBuyerCap`.
- CLASS: TEST-DELETE (collapse).

### RC-8 (med, several) — missing side-effect assertions on support & alerts
- `test_support.py` never asserts `ticket.status == OPEN`; `test_alerts.py` never asserts the swapped keyboard content; `test_support_delivery_email.py` asserts only the outbox.
- CLASS: TEST-ADD / TEST-UPDATE.

### RC-9 (low, ~55) — file is not a coherent matrix; module-level magic ids (prior C4)
- `test_account_state_middleware.py:58` (`_BASE_CHAT_ID = 900000200`), `:214,830` (`999999999`).
- CLASS: TEST-REWRITE (parametrize flag × event-shape).

### RC-10 (low, 2 classes) — `test_lock_timeout_boundary.py` hosts ad-create `process_preview` cases (prior C1 residue)
- CLASS: relocate.

### RC-11 (low, 1) — `test_account_state_deactivation_probe.py` is a meta-test subsumed by the matrix (keep docstring for the audit trail)
- CLASS: DOC-UPDATE.

### Overlap map (account-state trio)
| File | Unique ownership | Overlap |
|---|---|---|
| `test_account_state_middleware.py` (~55) | flag→message matrix; `can_login` cross-predicate; `__call__` plumbing (non-Update, no-message, no-from_user, callback identity AUT-003, FSM backfill AUT-001, `/post` publish+consent gate, `classify_contact_deep_link`) | blocked-flag rows repeated by the other two |
| `test_bot_deactivation_matrix.py` | plan-19 §3 carve-outs for `is_active=False` (allowed `SUPPORT_START`/support free text → **real ticket**, command smuggling blocked, `/start <arg>` 19-D6), deactivation-message distinctness (19-D3), web `ModelBackend` revocation guard | blocked-deactivated rows duplicate the probe |
| `test_account_state_deactivation_probe.py` | nothing behavioural beyond `is_active=False → blocked` | fully overlapping |
Bottom line: one matrix split three ways; the matrix file is the substantive owner; the probe is redundant; **none** asserts middleware order.

### Already resolved
- C1: partially (RC-10 residue).
- C3 (async/sync boundary): RESOLVED.
- C4: PARTIALLY (RC-9).
- C5 (markers): RESOLVED/ACCEPTED.
- C6 (enums): RESOLVED.
- C7 (translation edge cases): RESOLVED.
- C8 (xdist flake): RESOLVED.
- C9 (side effects): PARTIALLY (RC-8).

### Missing coverage
| Behavior | Source | Why critical | Location |
|---|---|---|---|
| Login deep-link refusal for banned/deleted/deactivated | `handlers/login.py::handle_login_deep_link` | Handler-layer gate unverified | `test_login.py` |
| Token single-use for a blocked identity | `handlers/login.py`, `login_token.claim_token` | Single-use tested only for normal users | `test_login.py` |
| Same `update_id` twice → one effect (real) | `middlewares/update_id_dedup.py` | Core purpose never demonstrated | `test_update_id_dedup.py` |
| Dedup TTL boundary | `DEDUP_TTL_SECONDS` | Docstring calls it load-bearing | `test_update_id_dedup.py` |
| Full middleware order | `main.py::configure_dispatcher` | Silent reorder bug | `test_main.py` |
| Support ticket `status == OPEN` persisted; FSM reset | `handlers/support.py::handle_support_orm` | Side effect unverified | `test_support.py` |
| Alerts callback swapped keyboard content | `handlers/alerts.py` | Button content unverified | `test_alerts.py` |
| Ticket survives a delivery failure | `support_delivery_*.py` | End-to-end invariant | `test_support.py` |
| `can_store_personal_data` deactivated carve-out | `account_state.py` | Deliberate `is_active` omission | `test_bot_deactivation_matrix.py` |
| Anonymous `/language` → login reconcile e2e | `handlers/language.py`, `login.py` | Handler-level reconcile | `test_language.py` / `test_login.py` |

### Duplicates
- `test_login_rate_limit.py` ≈ `test_login.py::TestLoginRateLimit`.
- `test_rate_limit_service.py::TestContactStartRateLimit` ≈ `test_contact_us.py` cooldown + `test_support.py` bot-skip.
- `test_contact_deep_link_rate_limit.py::TestDeclinedAccountCovered` ≈ `TestPerBuyerCap`.
- Blocked-flag rows across the trio (see map).
- `test_support_delivery_telegram.py` re-declares `_make_ticket`/`_make_contact` despite conftest fixtures.

### Uncertain
- Whether the probe file must be retained for its audit-trail requirement.
- Whether `test_multi_lang_translation.py` belongs in the bot block (it tests `apps.core.services.translation`).
- Whether `test_lock_timeout_boundary.py`'s ad-create cases duplicate Block 19.

---

## Cross-block patterns (for the auditor)

1. **Mock-call / status-only verification standing in for business behavior** — Blocks 3, 5, 6, 13, 15, 17, 19, 20.
2. **Tests that assert source text (template/CSS/JS/YAML/shell/AST) instead of behavior** — Blocks 1, 2, 4, 6, 7, 8, 9, 11, 12, 19.
3. **Coverage gaps at exact boundaries (retention cutoffs, size caps, TTLs, ±1s)** — Blocks 4, 8, 10, 15, 16, 19, 20.
4. **Duplicated canonical homes (same contract owned twice)** — Blocks 4, 6, 8, 13, 16, 20, plus `test_json_logging` (nonexistent).
5. **PII/consent/account-state gates asserted via effects rather than the predicate seam** — Blocks 5, 11, 15, 20.
6. **Cross-app artifacts surfacing a possible production defect** (report as findings, do not fix) — Block 3 (support cache fail-open), Block 7 (Free-ad sort vs spec), Block 16 (`city_fuzzy` Tier-2 case), Block 17 (recompute lock), Block 19 (submit key contract).
7. **Marker/tier misclassification** — Blocks 13 (SLO wall-clock), 17 (`unit`+`django_db`), 18 (blanket `seed`, `TestCityFixtures`), 19 (blanket `transaction=True`).
8. **Stale inventory/docstrings** — Blocks 1, 3, 4, 6, 8, 9, 13, 18, 20.
