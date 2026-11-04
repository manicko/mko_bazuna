---
id: architecture-correction-plan
domain: planning
tags: [architecture, agent-development, simplification]
related: [architecture, rules, architecture-structure]
---

# Architecture correction plan

Review date: 2026-11-04. Lead: Tech Lead Architect. Review roles: Auditor, Researcher, Validator, Planner.

## Purpose

Make LLM-assisted development easier to navigate, implement, verify, and maintain. Evaluate the implemented migration against that goal, independently of API completeness. This document authorizes no implementation during this review.

**Recommended direction:** retain useful service extractions, deterministic ordering, and test-infrastructure improvements; correct the edit/lifecycle regressions; retire the added parity HTTP surface and its maintenance machinery after checking deployed consumers and preserving unique business tests. Keep the existing product interfaces.

The attached [migration plan](api-parity-migration-plan.md) is historical input. Its “frozen,” “ratified,” and “do not re-litigate” statements describe that migration; they do not constrain this requested reassessment.

## 1. Scope, evidence, and limitations

- **Before:** `57966ea0`, immediately before `388b3e4a` introduced the Agent-First/API-parity rules and `5c0733ef` overturned the single-consumer API contract.
- **After:** `22dd26be` (`HEAD`, `main` at review), ending with `verify_parity`. Use these SHAs for comparison, not as rollback targets.
- **Observed delta:** 132 tracked files; 20,378 inserted / 833 deleted lines. A read-only AST count found a net 479 additional `test_*` functions in changed test modules, not 479 collected tests: parametrization changes the collected count. These totals include interleaved test-performance work.
- **Static grouping:** 41 files selected by API adapter/route path grouping add 5,497 lines (including API package files and `api_auth.py`); 50 changed test files add 10,252 / delete 8 lines. Grouping is by paths, not a runtime or productivity measurement. Other helpers, documentation, and verification machinery add further cost.
- **Already present before migration:** shared ORM/services, Pydantic boundary DTOs, Django `Client()` tests, FTS/cache logic, bot FSM, and operational CLI commands. The migration did not introduce browserless testing.
- **Actual rollout differs from the proposal:** service and endpoint stages plus S5.1 are in history. S5.3/S5.5 close-out is not established: `api-surface.md` still mixes skeleton/planned text with shipped rows, and no workflow invokes `verify_parity`. Do not assume the proposal's exit gates ran.
- **Review verification:** Git comparisons, call-site/source inspection, AST counts, and a read-only import-signature experiment. The test DB container was inspected and was healthy. No pytest run, migration, server request, benchmark, database write, or implementation edit was performed.
- **Evidence limit:** repository searches found no product consumer of the new endpoints; they cannot establish whether deployed/external consumers exist. No controlled LLM task-completion benchmark or production endpoint-usage telemetry was available. Benefits below are demonstrated capabilities and reasoned development-cost assessments, not measured speedups.
- **Existing working tree:** `.kilo/commands/debug/bugfix.md` and `.kilo/rules/project.md` were already modified; `.ai/audit/`, migration/performance plans, `.ai/problems/`, and logo assets were untracked. Preserve all pre-existing work. This review writes only this plan.

Evidence paths below are repository-relative, rooted at `C:/py_dev/mko_bazuna`; line numbers refer to reviewed HEAD unless a baseline is specified. Symbols and commits are the durable anchors.

## 2. Before, after, and proposed architecture

| Aspect | Before | Implemented migration | Proposed correction |
|---|---|---|---|
| Product boundaries | Django/HTMX pages; Telegram bot; selected JSON endpoints; admin/CLI | Same boundaries plus per-app `/api/v1/` mirrors | Original product boundaries; new HTTP interface only for a demonstrated consumer |
| Business logic | Many shared services; FTS helpers/edit/lifecycle/dashboard partly view-local | Six extractions, plus large API orchestration and serialization modules | Retain useful callable seams; repair contracts/transaction ownership |
| Functional verification | Services/ORM and `Client()` with status/context/DB assertions | Original suites plus JSON/parity/auth/serialization suites | One thorough service behavior matrix plus thin HTML/bot boundary tests |
| Discoverability | App-local code and project docs | URL registry, mirror-pair table, exceptions, 1,074-line API inventory, metadata CLI | Short task-to-service/test map in existing agent docs; pytest/JUnit for machine-readable results |
| Credentials | Telegram-mediated sessions; existing staff gate; CSRF | Same credentials; no autonomous login bootstrap | Preserve existing auth; no new token scheme merely for development |
| Operations/data | Web + bot + scheduler, shared PostgreSQL/Redis | No new tables, runtime dependency, middleware, or settings required | No data rollback or deployment topology change |

Target call paths:

```text
HTML/HTMX views ------> app-local services ------> Django ORM/PostgreSQL
Telegram handlers ---> existing shared services + bot-specific dialog
Admin / existing JSON / management commands ---> existing application seams
pytest ---> services + real HTML/bot boundaries ---> assertions + optional JUnit
```

Some request-specific behavior belongs in views: cookies, sessions, CSRF, locale middleware, redirects, HTMX fragments. Test those boundaries with `Client()`; do not extract every HTTP behavior into a service. Single-caller extraction is justified when it isolates substantial logic for direct tests, not simply because another layer is possible.

The material regression is architectural, not just size: the new edit adapter globally patches a service function at runtime to recover discarded outcomes. Retaining an endpoint cannot justify weakening the underlying service contract.

## 3. Decision framework

YES/YES or NO/YES means KEEP; NO/NO means REMOVE; YES/NO requires investigation. SIMPLIFY preserves demonstrated benefits with less complexity. “NO” for an adapter means no **incremental benefit demonstrated for this project's development workflows**, not that JSON can never help an agent. Retained components need evidence of useful behavior or maintainability, not a parity requirement.

The inventory below separates business extractions, transport adapters, verification machinery, and collateral changes so that removal does not become a range-wide revert.

## 4. Change inventory and final decisions

Abbreviations: paths beginning `apps/` are under `src/backend/`; LLM = incremental agent-development benefit; Arch = architecture/maintenance benefit. Conditional removals describe the target after the last real consumer is removed. Until then, their auth, limits, and contract tests remain necessary.

| ID / change | LLM benefit | Architecture benefit | Final decision | Repository evidence and reason |
|---|---|---|---|---|
| D01 Parity mandate and multi-consumer framing | NO | NO | **REMOVE mandate; SIMPLIFY policy** | `388b3e4a`, `5c0733ef`; `.kilo/rules/project.md:56` already contains an uncommitted narrower Agent-First formulation. Preserve that user work; reconcile docs with deterministic verification rather than one HTTP mirror per action. |
| D02 Deterministic listing ordering | YES | YES | **KEEP** | `a5023e27`; `apps/ads/services/listings_query.py::_apply_sort` adds `-id` to every branch; existing HTML pagination benefits. Retain null-price/tie/page tests. |
| D03 FTS extraction | YES | YES | **KEEP** | `99ef21cb`; `apps/search/services/fts.py` takes explicit locale, isolates filtering/count/rank/fuzzy logic; actual HTML caller is `views/search.py`. Keep existing cache cap and `alert_query.py` divergence. |
| D04 Favorites list/toggle extraction | YES | YES | **KEEP** | `497b4a15`; `apps/ads/services/favorites.py::{favorites_queryset,toggle_favorite}` used by cabinet HTML and heart toggle. Preserve the pre-existing `annotate_favorites`. |
| D05 Dashboard grouping | YES, modest | YES, modest | **KEEP** | `0e577441`; `dashboard_query.py::ads_by_status`, used by `ads/views/dashboard.py:71`; tests added to `test_dashboard_stats.py`. A 63-line direct query module is a useful test seam without a new framework. |
| D06 Saved-search mutators | YES | YES | **KEEP** | `8922ab55`; `search/services/saved_searches.py`; modal create and cabinet HTML use it. Ownership, query handling, token stability can be asserted directly. Bot unsubscribe/token workflow stays distinct. |
| D07 Edit-flow extraction/result | YES in principle; currently unreliable | YES after correction | **SIMPLIFY / FIX** | `c3c604b2`; `edit_flow.py::_submit_like/apply_edit_payload` lose refused outcomes; HTML caller changed behavior. Preserve full typed success/refusal information (§5 R03). |
| D08 Lifecycle extraction | YES | YES after correction | **SIMPLIFY / FIX** | `5b894a44`; `lifecycle.py::_fetch_owned_ad/assert_lifecycle_owner`; HTML archive/reactivate release the first lock before mutation. Restore one transaction and remove duplicate precheck/fetch (§5 R04). |
| D09 Public listings JSON | NO demonstrated incremental gain | NO demonstrated consumer benefit | **REMOVE**, consumer gate | `e0733201`; `ads/views/api/listings.py` (146 lines); baseline HTML tests already assert structured context. Preserve its business matrix, not the additional transport. |
| D10 Search JSON | NO demonstrated incremental gain | NO; duplicate orchestration | **REMOVE**, consumer gate | `76cb0081`; `search/views/api/search.py` (382 lines) repeats normalization, cache producer, pagination and tracking orchestration despite shared FTS helpers. |
| D11 Detail JSON | NO demonstrated incremental gain | NO demonstrated consumer benefit | **REMOVE**, consumer gate | `2b42c6c8`; `ads/views/api/detail.py`; extra serializer/visibility tests; successful GET records `AD_VIEWED` at line 91. |
| D12 Categories/cities JSON | NO demonstrated incremental gain | NO demonstrated consumer benefit | **REMOVE**, consumer gate | `1faa0c96`; `categories/api_tree.py`, `locations/api_cities.py`; no product callers found. Existing ORM queries/header paths remain. |
| D13 Private dashboard/favorites/saved-search/history reads | NO demonstrated incremental gain | NO demonstrated consumer benefit | **REMOVE**, consumer gate | `b0c45d9f`, `dcb64aa0`, `10aac929`; `ads/views/api/dashboard.py`, `cabinet/views/api/`; keep underlying services and HTML consent/ownership behavior. |
| D14 Moderation/trust reads | NO demonstrated incremental gain | NO demonstrated consumer benefit | **REMOVE**, consumer gate | `98049d91`, `20c5581c`; `moderation/views/api/{queue,review}.py`, `analytics/views/api/`; existing staff HTML/service/admin paths cover operations. |
| D15 Favorites/saved-search/history JSON writes | NO demonstrated incremental gain | NO demonstrated consumer benefit | **REMOVE**, consumer gate | `ce5fc6c2`, `076ebc1d`, `c9cec0cf`; transport-specific DTO/status/serializer code; HTML service callers remain. |
| D16 Consent/logout JSON writes | NO demonstrated incremental gain | NO demonstrated consumer benefit | **REMOVE**, consumer gate | `641bb763`; `users/views/api/{consent,logout}.py`; sessions/CSRF/bootstrap unchanged; keep real HTML cookie/logout/audit behavior. |
| D17 Lifecycle/copy JSON writes | NO demonstrated incremental gain | NO demonstrated consumer benefit | **REMOVE**, consumer gate | `13a152de`, `75309691`; API lifecycle adapter is 474 lines; copy service already served the bot. Keep services and original copy tests. |
| D18 Edit JSON write | NO; adds fragile indirection | NO | **REMOVE**, consumer gate | `1f71bef4`; `ads/views/api/edit.py::_apply/_capturing` patches global `edit_flow.submit_ad` via `unittest.mock.patch`. If temporarily retained, use the corrected typed result instead. |
| D19 Submit JSON and draft inventory | NO demonstrated workflow need | NO independent benefit | **REMOVE**, consumer gate | `d2f6df33`; 608-line `ads/views/api/submit.py` adapts an already-persisted draft; does not replace bot dialog/photo staging. Readiness/dry-run checks are not a reason to retain an entire HTTP surface. |
| D20 API URL aggregation/per-app route modules | NO after retiring mirrors | NO after retiring mirrors | **REMOVE after routes retire** | `728e456c`; `apps/api/urls.py`, per-app API URL modules, `config/urls.py` mount. Keep normal app namespaces and old JSON routes. |
| D21 Problem renderer/session/staff variants | YES while API is live; NO afterward | YES for live API; NO afterward | **REMOVE after last caller** | `67181c2c`, `e4a7a262`; `core/utils/{problem,api_auth}.py`, 188 + 181 lines. Do not remove protection before endpoints. Preserve old moderation decorators and sanitizer. |
| D22 API rate budgets | YES while API is live; NO afterward | YES for live API; NO afterward | **REMOVE after last caller** | `16646a26`; only `API_PUBLIC_READ` and `API_WRITE` members/property entries in `core/enums.py` and their dedicated test cases. Preserve all original budgets/enforcement. |
| D23 API-only shared submission additions | NO after submit removal | NO independent caller | **REMOVE targeted additions** | `d2f6df33`; `submission.media_caps()`, `SubmittedPhoto.sha256`, digest-precedence branch. Preserve existing `AdImage.sha256`, hashing/deduplication/staging/promotion. |
| D24 Mirror-import-subset harness | NO; table/exception upkeep | NO behavioral or cycle guarantee | **REMOVE** | `apps/api/tests/test_import_rule.py` (367 lines); direct import sets plus growing allowlist; couples independent refactors. See R02. |
| D25 `verify_parity` | NO demonstrated behavior-verification gain | NO at this complexity | **REMOVE** | `22dd26be`; command 846 lines + tests 409; seven metadata checks, no service replay, no CI caller. See R02. |
| D26 Service and business-invariant tests | YES | YES | **KEEP / RELOCATE** | FTS/edit/lifecycle/saved-search suites; mixed favorites/dashboard/copy tests; filter/sort/page/locale/cache/visibility cases currently inside API suites. Retain coverage before deletion. |
| D27 API envelope/auth/parity-only tests | YES while API is live; NO afterward | YES for live contract; NO afterward | **REMOVE with endpoint** | Drop obsolete API serialization/taxonomy comparisons after transferring unique domain/security assertions. Never delete mixed test files wholesale. |
| D28 Listing matrix repetition | NO | NO | **SIMPLIFY** | `test_listings_api.py::test_filter_sort_page_cross_product` parametrizes unused `page` and loops all three pages in its body. Keep each page assertion once per sort. |
| D29 Fast/full/nightly tiers and tier parity guard | YES | YES | **KEEP** | `3d3c8a55`, `50661114`, `a1db6be0`, `e01cf78e`, `e56321d2`, `94aab776`; Makefiles/entrypoint/CI/`test_docs_ci_parity.py`. Documented faster pytest feedback, retained slow coverage; not an API benefit. |
| D30 Bot xdist grouping | YES | YES | **KEEP** | `9f6e4cb9`; additional `bot_concurrent` marks and serial nightly control preserve reliable concurrent testing. |
| D31 Media rate-limit test pre-seeding | YES | YES | **KEEP** | `5445a453`; `test_media_security.py` exercises over-budget behavior without repeatedly invoking expensive media path. Preserve real enforcement assertions. |
| D32 API i18n batches | NO after source removal | NO for unused strings | **SIMPLIFY catalogs selectively** | `babd3210`, `7b123781`, `c2f130dd`, `82742908`; remove only unreferenced API msgids. `c2f130dd` also fixes Bosnian mixed script: preserve that repair and shared strings. |
| D33 API inventory/spec/agent docs | YES if concise/current | YES if accurate | **SIMPLIFY** | `api-surface.md` is 1,074 lines, includes cumulative stage history and stale `verify_parity` receipt claims at lines 84/202; update README/spec-index/architecture/commands together. |
| D34 Deleted stale structure snapshot | YES | YES | **KEEP deletion** | `388b3e4a` deletes `docs/STRUCT.md`; restore neither obsolete file tree nor duplicate architecture documentation. |
| D35 Dependencies/schema/config restraints | YES | YES | **KEEP** | No `pyproject.toml`/`uv.lock` or migration delta in comparison; no new runtime framework/auth/middleware. No dependency/data rollback is required. Unused `django-filter` predates this work and is outside correction scope. |

Final set: KEEP D02–D06, retained behavior/security tests, D29–D31, D34–D35; SIMPLIFY D01/D07/D08/D28/D32/D33; REMOVE added transport and its exclusive support D09–D25/D27 under the stated gates. No architectural INVESTIGATE decision remains unresolved; deployed-consumer discovery is a prerequisite for execution, not evidence that an unused interface merits permanent retention.

## 5. Research findings and independent validation

### R01 — Is structured JSON worth keeping, including public reads alone?

**Initial dispute:** JSON is easier for remote tools to inspect than HTML. Could retaining only listings/search/detail/catalog reads offer enough LLM benefit to justify their maintenance?

**Evidence:** baseline `apps/ads/tests/test_listings_sort.py` already uses `Client().get('/')` and `response.context['page_obj']`; current `test_search_api.py` compares JSON with that same structured context. Searches across product Python, templates, static assets, bot, benchmark, scripts, and workflows found route declarations/documentation but no product caller of the new endpoints. No separate credential bootstrap was added. Search/detail API GETs perform analytics/history writes, so repeated live polling is not a side-effect-free verification method.

[Official Django 5.2 testing documentation](https://docs.djangoproject.com/en/5.2/topics/testing/tools/#the-test-client) confirms that `Client()` needs no running server, supports template-context inspection during tests, and disables CSRF by default unless `enforce_csrf_checks=True` is supplied. Template-context instrumentation is a test-environment capability, not a general remote HTTP capability.

**Resolution: REMOVE all unused mirrors, including public reads.** The structured verification capability already exists within this project's development environment. Keeping only public reads still retains parsing, serializers, route/auth/limiter contracts, localized errors, duplicated search orchestration, and tests. Retain an actual externally consumed subset temporarily if P2 finds one; do not infer there are no external callers from repository silence. This resolves a development-architecture decision; it does not reject future product APIs.

### R02 — Do the import harness and CLI earn their cost?

**Initial dispute:** cheap, deterministic machine-readable checks may improve agent confidence.

**Evidence:** `test_import_rule.py::test_pairing_table_rows_satisfy_import_rule` compares direct imported module names with mirror imports plus an allowlist. The Researcher's in-memory experiment replaced the `listings_view` body with `return None`: all 10 import signatures stayed unchanged. No file was changed. This illustrates the check's limited property; functional tests would catch such a break. The harness cannot establish service reuse, behavior equivalence, transaction safety, or acyclic transitive imports.

`verify_parity.py::run_checks` invokes seven route/pairing/Markdown consistency checks. It does not execute a business service or HTTP request and does not read notification receipts. `_calls_module` checks imports, not actual invocation. Its source/docstrings disagree about reading versus importing test constants; actual code parses source via AST. It couples production management code to test-table literals and human Markdown formatting. No workflow invokes it, contrary to the migration's intended CI gate. Metadata consistency has limited value, but this is 846 command lines plus 409 test lines protecting another redundant registry.

**Resolution: REMOVE both.** Preserve ordinary URL smoke/security tests for maintained interfaces. Use pytest's existing exit status and optional JUnit XML; do not replace the command with another agent framework or generated registry. A green metadata check was never proof of functional correctness.

### R03 — Is the edit extraction safe to keep?

**Evidence:** `edit_flow.py::_submit_like` returns `moderation_failed=False` for `CONSENT_REQUIRED`, `DRAFT_GONE`, `PHOTO_UNAVAILABLE`, and `INVALID_TRANSITION`. `apply_edit_payload` then discards those errors and returns a successful `REACTIVATED`/`RESUBMITTED` branch. HTML `views/edit.py::ad_edit` redirects for that result. Baseline `57966ea0` redirected only when `SubmitAdOutcome.PUBLISHED`; other outcomes rendered an error. This is a source-confirmed behavior regression, not a new test result.

The API compensates with `unittest.mock.patch` of global `edit_flow.submit_ad` in `_apply`, plus `_capturing` to observe a consent refusal. That is unnecessary runtime mutation caused by the lossy result contract. Possible interference in threaded execution is a risk, not a demonstrated production failure; current sync gunicorn reduces that exposure.

**Resolution: SIMPLIFY/FIX the service, REMOVE the workaround.** Carry `SubmitAdOutcome | None` or equivalent explicit success/refusal in `EditResult`, including errors; keep the edit branch and submission outcome distinct. Derive the branch from ad status/text/reactivate rather than asking a caller to label a submission result successful via `outcome_prefix`. Preserve existing price-only/direct-save semantics. Update HTML and any temporarily retained API caller together. Only successful submission redirects; every refusal renders the appropriate existing error path.

Also remove unused `can_edit_ad_by_service` after confirming no caller, and remove the duplicate HTML `_apply_price_change` kept for a test patch point. Patch the actual service dependency in tests; do not keep duplicate production logic to satisfy a private test import. Preserve affordance versus direct-save status sets and public re-exports still used by dashboard/tests.

### R04 — Is the lifecycle extraction safe to keep?

**Evidence:** current HTML `ad_archive`/`ad_reactivate` finish the ownership/consent transaction before `archive_ad`/`reactivate_ad` opens another. Baseline kept checks and transition/moderation under one outer transaction. `assert_lifecycle_owner`'s docstring overstates lock lifetime. The service still checks ownership, so there is no demonstrated authorization bypass: late archive `PermissionDenied` becomes a generic 403; reactivation's broad exception handler could misreport it as moderation failure.

**Resolution: SIMPLIFY/FIX.** First keep the existing outer atomic block open through the action. Then adopt one clear convention: the HTML boundary fetches/locks the ad, checks ownership then consent, and invokes a small lifecycle state operation on that locked instance inside the same transaction. Delete remains consent-free. Eliminate `assert_lifecycle_owner` and the second ownership fetch when callers have moved. Keep useful outcome values and moderation rollback behavior. A single ad-row transaction does not, by itself, solve all concurrent account-consent changes; retain existing shared predicates and do not claim broader race prevention.

### R05 — Are submission/media additions independent improvements?

`submission.media_caps()` reads private moderation tuple indices 5/6 solely for API readiness checks. The API submit adapter alone populates optional `SubmittedPhoto.sha256` to resubmit permanent draft photos; the bot uses staged uploads and HTML edit supplies `photos=[]`. This supports a path introduced by the API, not a demonstrated improvement to existing bot submission.

**Resolution: REMOVE these targeted additions after submit retirement.** Restore the earlier staged-digest computation, preserving existing image SHA-256 fields, `FileHashService`, `AdImageService.create_or_skip`, staging cleanup, promotion, and commit callbacks. Do not remove pre-existing image deduplication or revert the entire modules.

### R06 — Should the performance/CI changes survive?

**Resolution: KEEP independently.** `docs/99-agent/rules.md` records pytest time falling from 581.6 to 370.7 seconds after tiering, with the 240-second target unmet; those are historical reported timings, not reproduced here or attributable to the API. Preserve slower-tier coverage, bot grouping, and marker consistency. Full-tier CI runs on long-lived branch pushes; it is not a mandatory pre-merge PR signal. Correct that wording.

Current `docker/entrypoint-test.sh:70` appends fixed `PYTEST_DEFAULTS` **after** `PYTEST_OPTS`. The migration plan and `.kilo/rules/commands.md` incorrectly say the options replace defaults. Correct the maintained command docs; do not change working infrastructure to match stale prose. Bare test paths are safe. Do not send `-p no:xdist` through this entrypoint or pass shell-quoted multiword marker expressions through its unquoted `PYTEST_OPTS` expansion.

### Independent verification and final lead decision

The Auditor identified costs and regressions; the Researcher independently resolved public-read retention, metadata tooling, and API-only media changes; the Validator rechecked the outcome regression, transaction gap, runtime patch, unused page parameter, metadata-only checks, surviving callers, and consumer caveat. The Planner then ordered corrections and checked deletion/test/doc dependencies.

The Validator rejected stronger unsupported claims: repository silence proves no external callers; the lock gap proves unauthorized success; global patching has caused a production concurrency failure; fewer tests prove faster LLM development. None is adopted here. The lead approves the final target and roadmap below; implementation remains future work. Every retained change has a concrete behavior/testability benefit. No retained component is justified solely by API parity.

## 6. Safe rollback and simplification strategy

Use **targeted removal and incremental refactoring**, each in a small reviewable corrective commit. Do not reset to baseline or revert the entire migration range. Even single endpoint commits modify shared modules, mixed tests, and catalogs; inspect each hunk before choosing a selective revert. Use `git show <sha> -- <path>` as evidence, not a command to overwrite current files.

The safest order is correctness repairs → consumer inventory and coverage transfer → endpoint retirement → exclusive-support cleanup → retained-seam cleanup → documentation/catalog close-out → full verification. Commit code deletion and its affected route/docs/obsolete-test changes coherently; do not leave a deployable intermediate revision with live routes but missing protection.

If an actual consumer is found, identify its required endpoint subset and migration owner. Keep that subset's helpers, budgets, contract/security tests, and short current documentation until migration/deprecation completes. Reassess only that concrete interface; do not revive whole-project parity. If consumer data cannot be obtained, finish the repairs/test consolidation but leave endpoint retirement pending rather than treating missing telemetry as zero use.

Rollback of a corrective package means reverting that package's coherent commit, with its associated routes/helpers/tests/docs, while retaining earlier correctness fixes. No database restore, reverse migration, image cleanup, scheduler change, or lockfile restoration is indicated. Preserve real ads, drafts, images, consent records, favorites, saved searches, and analytics.

### Retirement manifest

Root for this manifest is `src/backend/`. Delete only after P2/P3 gates; recheck no new callers have appeared since reviewed HEAD. Brace expressions below are concise file notation, not PowerShell commands.

| Area | Exact retirement scope |
|---|---|
| API adapters | Newly added `apps/{ads,analytics,cabinet,moderation,search,users}/views/api/` directories and their `__init__.py` files |
| One-module adapters | `apps/categories/api_tree.py`; `apps/locations/api_cities.py` |
| Route modules | `apps/{ads,analytics,cabinet,categories,locations,moderation,search,users}/api_urls.py`; `apps/ads/api_dashboard_urls.py`; remove only new `path('api/v1/', include('apps.api.urls'))` from `config/urls.py` |
| Aggregator/harness | Newly added `apps/api/` package, including `urls.py`, `tests/test_urls.py`, `tests/test_import_rule.py` and package files; the baseline's empty placeholder directories need not be recreated |
| Exclusive helpers/CLI | `apps/core/utils/{api_auth,problem}.py`; `apps/core/management/commands/verify_parity.py`; `apps/core/tests/{test_api_auth,test_problem_response,test_verify_parity}.py` |
| Ads API test modules | `apps/ads/tests/{test_ad_detail_api,test_dashboard_api,test_edit_route_api,test_favorites_toggle_api,test_lifecycle_api,test_listings_api,test_submit_route_api}.py` |
| Cabinet API test modules | `apps/cabinet/tests/{test_favorites_list_api,test_saved_search_write_api,test_saved_searches_api,test_search_history_clear_api}.py` |
| Other API test modules | `apps/analytics/tests/test_analytics_api.py`; `apps/categories/tests/test_categories_api.py`; `apps/locations/tests/test_cities_api.py`; `apps/moderation/tests/{test_moderation_api_actions,test_moderation_api_reads}.py`; `apps/search/tests/test_search_api.py`; `apps/users/tests/test_consent_api.py` |
| Mixed-test surgery | In `apps/ads/tests/test_copy_ad.py`, remove API helper/fixture/import additions and `TestCopyEndpoint*` classes after retaining unique copy invariants. Keep original service tests. Keep service additions in `test_favorites.py` and `test_dashboard_stats.py`. |
| Shared-code surgery | Only API budget members/property entries and dedicated tests; `submission.media_caps`, optional `SubmittedPhoto.sha256`, and new supplied-digest precedence. Preserve all pre-existing behavior described in R05. |

Never delete `apps/moderation/views/api_bulk.py`. Its product URL is **`/moderation/api/v1/bulk-action/`**, outside the new root mount. Also preserve `/api/search/autocomplete`, `/api/preferred-city/`, `/login/issue/`, `/login/status/`, HTML consent/logout, health/readiness, metrics gates, admin, media delivery, and all bot dialogs/commands.

### Coverage transfer ledger required before deletion

For every test class in a retiring module, record in the corrective change description: source class → retained destination/test name, already-covered test, or transport-only reason for deletion. This is a temporary review checklist, not a new production registry. Port meaningful missing assertions rather than copying every test.

| Source tests | Retained destination and required behavior |
|---|---|
| `test_listings_api.py::TestExhaustiveFilterSortPageMatrix` and audience tests | Existing listing suites or a focused `apps/ads/tests/test_listings_query.py`: category descendants, city, normalized price, purpose/condition/features AND, every sort, page union/no duplicates, hidden sellers. Remove the unused outer `page` parametrization; run each three-page loop once per sort. |
| `test_search_api.py` | `test_fts_service.py`, `test_search_view.py`, cache/rank/fuzzy suites: locale vectors, narrowing/opt-out, cold/warm/stale/fallback paths, cap/truncation and ordered page membership. HTML requests record analytics/history once; direct query verification does not create such events. |
| Detail/favorites/dashboard API suites | `test_detail_context.py`, `test_detail_render.py`, media/contact tests, favorites tests, `test_dashboard_stats.py` and consent gate tests: audience exclusion, favorite ownership/counts, grouped statuses/time ranges, media/contact visibility. Keep only actual product behavior, not obsolete JSON shape assertions. |
| Edit/lifecycle API suites | `test_edit_flow_service.py`, `test_edit.py`, `test_edit_views_locking.py`, `test_ad_lifecycle.py`, `test_lifecycle_service.py`, `test_ad_consent_gate.py`: full status/outcome/refusal matrix; unchanged state on refusal; gate-free delete; ownership/consent ordering; rollback and lock timeout; price clock reset/one save. |
| Submit/copy API suites and mixed copy tests | `test_submission.py`, media/image-service tests, original `test_copy_ad.py`, bot submit/copy tests: staged photos, deduplication, commit callbacks, copy replacing old draft, ownership, copied fields/features. API-only dry-run inventory/permanent-photo resubmission is not a retained product requirement. |
| Saved-search API suites | `test_saved_search_service.py`, `test_saved_search_create.py`, cabinet HTML suites: cross-owner refusal, filter validation, resulting DB state, token stability. Preserve current create/update semantics; do not silently unify different query handling or bot token flows. |
| Consent/logout/history API suites | Existing users/cabinet integration suites: audit records, timestamps, browse-only/withdrawn state, session flush, history owner scoping/idempotent clear. Keep meaningful CSRF checks on actual surviving write routes. |
| Moderation/analytics API suites | Existing `admin_actions`, HTML moderation/priority, and analytics service tests: staff authorization, approve/reject/ban effects and refusal states, moderation side effects, trust/stat totals. Preserve bulk JSON contract tests. |

Preserve `test_fts_service.py`, `test_saved_search_service.py`, `test_edit_flow_service.py`, `test_lifecycle_service.py`, mixed favorites/dashboard service cases, and sort/relevance/null regression tests. The goal is lower redundant setup and context cost without losing a business invariant.

## 7. Executable correction roadmap

Each row is a future implementation package. P0/P1 fix existing product behavior and can ship independently of endpoint retirement. Run focused tests for each package and the canonical fast gate at deployable boundaries; collect expensive final evidence once the relevant changes settle.

| Package / dependencies | Exact work | Acceptance and main risk |
|---|---|---|
| **P0 — Repair edit results** / none | Update `ads/services/edit_flow.py::EditResult/_submit_like/apply_edit_payload` and HTML `views/edit.py`. Preserve actual submission result/errors, distinguish branch from success, remove caller-selected misleading outcome labels. Update API edit to consume that result directly; delete `patch`, `SUBMIT_AD_PATH`, `_capturing`, and now-unused imports. | Service + HTML tests cover PUBLISHED, MODERATION_FAILED, CONSENT_REQUIRED, DRAFT_GONE, PHOTO_UNAVAILABLE, INVALID_TRANSITION. Only PUBLISHED redirects after submission. Every refusal retains error feedback; price-only/direct-save behavior stays intact. Temporary API maps each result honestly. Risk: silently changing error/rendering behavior. |
| **P1 — Restore lifecycle atomicity** / none, preferably after P0 | In HTML archive/reactivate, keep outer transaction open through service call; correct lock-lifetime documentation. Preserve missing/wrong-owner/consent refusal ordering and explicit PermissionDenied handling. Leave signature simplification to P6 while API callers still exist. | Focused tests against actual HTML path verify action occurs inside original transaction, row lock persists, moderation exception rolls back, failed moderation commits hidden state, delete remains consent-free, lock-timeout handling survives. Risk: deadlocks, broadened exception catches, changed error mapping. |
| **P2 — Verify consumers** / none; mandatory before P4 | Inventory repository plus approved deployed access telemetry/integration contracts. Record route, actual caller, ownership, use, compatibility obligations, and evidence period. Distinguish bots/scanners/probes from integrations. | No known consumer has an unresolved break. If telemetry/owner knowledge is unavailable, do not close this gate. If used, retire only unused routes and schedule the used subset's transition. Risk: breaking an external integration. |
| **P3 — Transfer business tests** / P0/P1; before P4 | Complete coverage ledger above. Move useful cases to service/HTML/bot tests and fix duplicate page parametrization. Preserve mixed test files. Keep meaningful `Client(enforce_csrf_checks=True)` tests on surviving write paths. | Every unique retained invariant has a named passing test; API status/envelope assertions are not treated as product requirements. Risk: accidental security/behavior coverage loss hidden by lower test count. |
| **P4 — Retire unused endpoints** / P2 + P3 | Apply adapter/route/test manifest; remove root mount; retain ordinary URL tests for actual product routes. Delete metadata CLI/harness coherently because their assertions require the retired registry. Update endpoint/command documentation in the same deployable revision. | Removed paths are absent; retained product routes resolve with previous contracts. No executable import of deleted modules. Keep all support used by any temporary consumer subset. Risk: deleting similarly named legacy JSON endpoints. |
| **P5 — Remove exclusive support** / P4 | Remove unused problem/auth variants, API budgets and dedicated tests, API-only submission/media additions. Remove obsolete references/patch targets. Check caller reachability before each deletion. | Original image hashing/dedup/staging/promotions and legacy auth/429 helpers stay unchanged. No schema, settings/env, middleware, dependencies, or lockfile changes. Risk: broad hash/catalog cleanup harming unrelated paths. |
| **P6 — Simplify retained services** / P0 + P1 + P4 | Adopt single locked-ad lifecycle convention in R04; update HTML/tests, remove redundant precheck/refetch/HTTP exception machinery when no caller needs it. Remove unused `can_edit_ad_by_service` and duplicate HTML `_apply_price_change`; update tests to real dependency seams. Shorten proposal-era commentary. | One operation implementation and one clear transaction owner. Keep all six useful seams, status distinctions, shared consent predicates, and `-id`. Public FTS helper renaming is optional coordinated cleanup, not required for success. Risk: unnecessary signature churn or conflating bot/web semantics. |
| **P7 — Finish docs/catalogs** / P4 + P5, alongside P6 | Complete documentation/config checklist below; prune only msgids no longer referenced by any retained source. Preserve Bosnian repair. | Current docs describe maintained interfaces and actual verification; catalogs/source agree; no false metadata/CI claims. Risk: removing shared strings or overwriting user edits. |
| **P8 — Verify and measure** / all | Run §8 gates; review collected-test/invariant delta, timing, full diff/status. Record commands, SHA, counts, failures, and actual elapsed times. | No unexplained behavior/coverage loss. Report measured test results and limitations; do not claim a measured LLM throughput gain. Risk: accepting faster runs achieved by missing coverage. |

### Documentation, configuration, and dependency checklist for P4–P7

- Preserve the current user-edited Agent-First rule; reconcile duplicate rule number 18. State that browserless deterministic verification is required, while HTTP parity requires a real consumer. Scope error-format guidance to maintained APIs rather than retrofitting frozen legacy shapes during this correction.
- Update `README.md`, `docs/01-spec/{architecture-structure,spec-index}.md`, and `config/urls.py` contract comments together. Preserve accurate documentation of old JSON/login/media/ops interfaces. Do not recreate `docs/STRUCT.md`.
- Replace the cumulative `docs/01-spec/api-surface.md` stage ledger with a short current interface inventory, moving/retaining any unique legacy-contract facts at their authoritative location. Remove dead endpoint examples, parity compliance claims, and `verify_parity` receipt assertions. If the file is deleted instead, repair every incoming link.
- Add a compact task → service → tests map to existing `docs/99-agent/architecture.md`; do not add another registry/framework. Cover browse/FTS/edit/lifecycle/favorites/dashboard/saved searches and actual Docker test invocation. Remove obsolete migration-stage commentary in retained service docs.
- Remove `.kilo/rules/commands.md`'s `verify_parity` section and correct `PYTEST_OPTS` semantics; correct other maintained command docs with the same stale claim, including `.ai/context/test-command-patterns.md` if applicable. Preserve user edits in `.kilo/rules/project.md` and `.kilo/commands/debug/bugfix.md`.
- Keep Makefiles, `docker/entrypoint-test.sh`, fast/full/nightly workflows, marker guard, and bot grouping. Correct “pre-merge” prose where the full CI tier actually runs after a branch push; do not redesign CI in this correction.
- Follow `.kilo/rules/commands.md`'s **whole-tree scratch extraction** procedure for i18n. Never run catalog extraction in the tracked tree for measurement. Remove only verified source-unreferenced API entries from ru/bs/en; preserve shared strings and `c2f130dd`'s Bosnian fix; compile/check catalogs normally during execution.
- No runtime/dev dependency addition or removal is required. Do not add DRF, Ninja, OpenAPI generation, Playwright, auth tokens, feature flags, generic serializers, or an agent CLI for this correction. Existing unused `django-filter` can be a separately scoped dependency decision, not a reason to modify the lockfile here.

## 8. Verification gates and acceptance criteria

These are **future execution commands**, not tests run during this read-only review. Run from the repository root in PowerShell. Use the Docker test service, not local `uv run pytest`; do not stop/reset a shared DB or recreate its schema merely for this code-only correction.

```powershell
# Inspect/start the test DB if needed; --env-file is required for interpolation.
docker ps --filter "name=mko-bazuna-test-db-"
docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml up -d db

# P0/P1: run before API deletion, including any temporarily retained adapters.
docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml run --rm -e "PYTEST_OPTS=src/backend/apps/ads/tests/test_edit.py src/backend/apps/ads/tests/test_edit_views_locking.py src/backend/apps/ads/tests/test_edit_flow_service.py src/backend/apps/ads/tests/test_ad_lifecycle.py src/backend/apps/ads/tests/test_lifecycle_service.py src/backend/apps/ads/tests/test_ad_consent_gate.py src/backend/apps/ads/tests/test_edit_route_api.py src/backend/apps/ads/tests/test_lifecycle_api.py" test

# P3/P5/P6: retained shared behavior; include newly relocated test files as created.
docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml run --rm -e "PYTEST_OPTS=src/backend/apps/ads/tests/test_submission.py src/backend/apps/ads/tests/test_copy_ad.py src/backend/apps/ads/tests/test_favorites.py src/backend/apps/ads/tests/test_dashboard_stats.py src/backend/apps/ads/tests/test_ad_image_service.py src/backend/apps/search/tests/test_fts_service.py src/backend/apps/search/tests/test_saved_search_service.py" test

# Retained boundary suites, including legacy JSON/CSRF/auth/media contracts.
docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml run --rm -e "PYTEST_OPTS=src/backend/apps/cabinet/tests src/backend/apps/users/tests src/backend/apps/moderation/tests src/backend/apps/analytics/tests src/backend/apps/search/tests src/telegram_bot/tests" test

# Static checks and canonical fast gate.
uv run ruff check src/
uv run basedpyright src/
.\Makefile.ps1 test

# Final comprehensive gate once, because submission/media/i18n paths are affected.
.\Makefile.ps1 test-all

# No schema delta expected; dev service/env, no dependency boot chain.
docker compose --project-name mko-bazuna-dev --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.override.yml run --rm --no-deps --entrypoint "" web python src/backend/manage.py makemigrations --check --dry-run

git diff --check
git diff --stat
git status --short
```

`test-all` includes the full pre-merge marker set plus seed coverage; do not repeat a separate full-tier run if this succeeds on the same revision. For an intermediate full non-seed check, use the same Compose command with `--env PYTEST_SKIP_MARKERS=seed test`. The entrypoint retains `--reuse-db`, four-worker/loadgroup defaults, and importlib configuration. A serial bot control, if a failure requires it, must bypass the test entrypoint using the documented container recipe. Preserve existing grouping rather than globally serializing the suite.

| Gate | Required evidence |
|---|---|
| G0 Consumer compatibility | P2 evidence recorded; any real consumer has retained endpoint coverage and a transition plan. Unknown usage blocks retirement, not the independent correctness repairs. |
| G1 Edit correctness | Parametrized service + actual HTML tests for every `SubmitAdOutcome` above, error preservation, no successful redirect on refusal; price-only single-save/clock and direct-save invariants pass. No production `unittest.mock.patch` workaround. |
| G2 Lifecycle atomicity | A regression test observes the actual HTML action within its original atomic block; a focused DB lock/concurrency test proves lock continuity. Ownership-before-consent, missing/wrong-owner responses, no-op states, delete without consent, moderation false/exception, and timeout behavior pass. |
| G3 Search/listing behavior | Full filter/sort/page matrix retained once, fixed-data total ordering, null-price behavior, locale FTS/fuzzy/cap/warm-cache behavior pass. Do not promise snapshot-stable pagination during concurrent writes. |
| G4 Existing product contracts | HTML/HTMX status/context/fragments, bot FSM, staging/photos, copy draft replacement, consent audit/session effects, owner scoping, media/contact gates, bulk moderation, autocomplete, preferred city, token bootstrap/status, and ops gates retain protection. Explicit CSRF tests run on surviving writes. |
| G5 Removal consistency | Search `src/`, scripts, benchmarks, and workflows for removed module imports, reverse names, new budget members, `verify_parity`, runtime patch targets, and `/api/v1/`. No executable stale references; the old `/moderation/api/v1/` path is expected. Ordinary URL tests verify removed routes are absent and legacy routes still work. |
| G6 Static/docs/i18n | Ruff/typecheck pass; catalog completeness/pipeline tests (included in the full suite) pass after normal compilation; changed Markdown links/frontmatter are valid; no active parity mandate, false receipt check, wrong test-options claim, or claimed pre-merge CI guarantee remains. Historical proposal references can remain explicitly historical. |
| G7 No infrastructure/data rollback | No new migration, schema/model-field change, settings/env/middleware change, dependency/lockfile change, scheduler set change, or deletion of real media/data. Diff review confirms only targeted submission DTO logic changed. |
| G8 Coverage and measured feedback | Coverage ledger has no unexplained loss. Record collected counts and elapsed times for comparable retained scenarios under the same environment, warm/cold DB/cache state, and worker setup. Compare total suite cost separately because intended transport-test deletion changes selection. Never equate fewer tests with maintained coverage. |

To evaluate agent efficiency later, use repeatable representative tasks (add a listing filter, alter an edit refusal, diagnose a search-cache case). Record files touched, commands needed, context consumed, errors/retries, and passing behavior gates before/after correction. This is optional evidence collection using existing tooling, not an acceptance requirement to invent a benchmark system. Until measured, claim simpler call paths and less duplicated maintenance, not a percentage LLM speedup.

## 9. Risks, dependencies, and stopping conditions

| Risk / dependency | Mitigation and stop condition |
|---|---|
| External integrations absent from Git | P2 is required before retiring a route. Retain a needed subset; missing operational evidence does not imply no use. |
| Dropping valuable API-era regression coverage | Complete P3 ledger first; preserve mixed files/service tests. Stop deletion if an invariant lacks a retained test destination. |
| Fixing extraction while changing product semantics | Compare P0/P1 against `57966ea0`, retain status/consent/ownership ordering and web/bot differences, test error/refusal paths rather than only happy paths. |
| Lock lifetime/deadlock/error handling | Keep transaction ownership explicit; test actual HTML locks and rollback. Do not broaden catches to convert DB errors/authorization into apparent success. |
| Hash/staging loss | Remove only optional API-supplied digest support after its last caller; retain pre-existing staged hashing/dedup and on-commit lifecycle. Stop on an image/storage regression. |
| Deleting old JSON by matching `api` broadly | Use the manifest/root mount, not name-based deletion. Explicitly verify bulk moderation, autocomplete, preferred city and token protocol. |
| Translation collateral changes | Whole-tree scratch extraction and per-msgid source check; preserve shared strings and Bosnian fix. Never restore a whole catalog from baseline. |
| Test speed masking reduced reliability | Keep slower tiers and xdist groups, inspect invariant/test-selection ledger, compare equivalent workloads. Full CI on branch pushes does not supply a PR pre-merge guarantee. |
| User work/ongoing changes | Re-read status/diff and current callers before execution; merge corrections around existing modifications. Stop any package whose assumed baseline changed materially and re-audit that package. |
| New schema/dependency/auth requirement appears | Outside approved target: investigate the concrete need instead of expanding the correction into another migration. |

Completion means the correctness defects are fixed, every retained operation has direct behavior protection, unused parity surface/support is retired only after compatibility checks, and current docs/tests/config agree. If a live consumer must remain, report that explicit deferred endpoint scope; do not claim full retirement or leave an undocumented partial rollback.
