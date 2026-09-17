All 5 agents have completed. Let me now review the findings and select the best approach before implementing.

Let me summarize the findings from all 5 agents:

Auditor 1 (Bot Test Infrastructure):
The bot conftest has an autouse _reset_moderation_criteria fixture that does DB read at setup and DB write at teardown
Three bot unit tests are affected: test_multi_lang_translation.py (19 tests), test_site_name_greeting.py (2 tests), test_update_id_dedup.py (3 tests) — 24 total
The backend moderation conftest has the same autouse fixture and also breaks test_decorators.py (11 tests)
ModerationCriteria is NOT seeded by migrations — it's created on-demand via get_or_create(pk=1)
The fixture is functionally a no-op for bot tests (snapshot is always {} because no test creates the row), but the setup SELECT still fails
The testing/moderation_fixtures.py docstring is stale (claims dual registration, only backend conftest registers it)
test_ad_lifecycle.py has a bug: it requests permissive_criteria/banning_criteria without local definitions and the plugin isn't registered for the bot tree
Auditor 2 (Backend Test Infrastructure):
Backend root conftest keeps per-test autouse fixtures DB-free; the DB-touching autouse fixture is directory-scoped to moderation tests only
The backend's approach: opt-in DB fixtures + directory-scoped autouse
test_decorators.py is misplaced under the moderation tests directory (it's a unit test but the directory has an autouse DB fixture)
test_ad_lifecycle.py errors with fixture 'permissive_criteria' not found because the plugin isn't registered in the bot tree
ModerationCriteria is never seeded — created lazily by get_singleton() → get_or_create(pk=1)
Two patterns exist: Pattern A (monkeypatch at service layer, DB-free) and Pattern B (save-and-restore DB row, requires DB)
Researcher 1 (pytest-django Mixed Tests):
Key patterns: (a) guard with django_db_blocker, (b) conditional autouse using request.fixturenames check (like _live_server_helper), (c) opt-in markers, (d) separate directories/conftests
django_db_blocker.unblock() is the standard pattern for session-scoped DB setup
pytest_collection_modifyitems hook can auto-inject django_db from integration markers
The _live_server_helper pattern: check if "live_server" not in request.fixturenames: return early
Researcher 2 (Singleton Save-and-Restore):
update() + save-and-restore is REDUNDANT under pytest-django — both default (rollback) and transaction=True (TRUNCATE) modes restore the DB
The essential step is cache.clear() because LocMemCache survives transaction boundaries
Save-and-restore via update() only matters when operating outside test transactions via django_db_blocker.unblock() (session-scoped seeding)
When the test uses default @pytest.mark.django_db (TestCase rollback), the save-and-restore is redundant — the DB row is already rolled back
When using transaction=True (TransactionTestCase TRUNCATE), TRUNCATE also restores — but with the caveat that the ModerationCriteria row might be TRUNCATE'd entirely (it would be deleted)
Actually wait — with transaction=True, the TRUNCATE at teardown wipes the table, so the save-and-restore restore via update() would be against a table that was TRUNCATE'd... that doesn't work. Let me think again.
Actually, TransactionTestCase._post_teardown() does call_command("flush") which does TRUNCATE ... CASCADE. But the order matters: pytest-django runs the test body, then _post_teardown (TRUNCATE), then the fixture teardown (save-and-restore update()). So:
Test modifies ModerationCriteria (changes banned_words, etc.)
TransactionTestCase._post_teardown() TRUNCATEs all tables — the ModerationCriteria row is gone
_reset_moderation_criteria teardown: cache.clear() runs, then if snapshot: — but snapshot was {} (empty, because the row was TRUNCATE'd), so update() is skipped
Next test: if it calls get_singleton(), it creates a new row via get_or_create(pk=1) with default values
So under transaction=True, the save-and-restore is indeed redundant — the TRUNCATE does the cleanup. The cache.clear() is the essential part (because cache survives TRUNCATE).

Under default @pytest.mark.django_db (TestCase rollback), the save-and-restore is also redundant — the savepoint rollback undoes all DB changes including the ModerationCriteria modifications. Again, cache.clear() is the essential part.

So the researcher conclusion: update() restore is redundant; cache.clear() is the only essential operation.

But wait — there's a subtlety. With transaction=True, the snapshot is taken at setup (before the test modifies things). If no prior test created the row, snapshot = {}. But if the session fixture or a prior test created the row, snapshot would have values. Then TRUNCATE wipes the row, and the if snapshot: guard would be False (snapshot is {}), so update() is skipped. The row is gone after TRUNCATE. This means subsequent tests that call get_singleton() create a fresh row with defaults. This is fine.

But what if a test does NOT use transaction=True? The bot conftest's _reset_moderation_criteria is autouse for ALL tests, even default django_db tests. Under default django_db (TestCase), the savepoint rollback undoes changes. But the TRUNCATE doesn't happen (TestCase doesn't TRUNCATE). So the update() restore would be... redundant again because rollback handles it. And cache.clear() handles the cache.

OK so the conclusion stands: the update() restore is redundant under pytest-django, and cache.clear() is the only essential part.

But this raises a question: why was _reset_moderation_criteria created in the first place? It was probably written before the --reuse-db optimization, or for when tests run outside transaction wrappers.

Actually, wait. Let me reconsider. With --reuse-db, the test database is NOT recreated between test runs — it's reused. And with transaction=True, TransactionTestCase does TRUNCATE after each test. But without transaction=True (default django_db), TestCase does savepoint rollback.

The key question: does --reuse-db mean that data persisted from a previous test run could affect a new test? No — TestCase rollback and TransactionTestCase TRUNCATE both happen per-test within the same run. --reuse-db only affects whether the DB schema is recreated between test runs (not between tests within a run).

So the save-and-restore pattern is indeed redundant when tests use @pytest.mark.django_db (either mode). The cache.clear() is the essential part.

Researcher 3 (pytest-xdist):
Comprehensive analysis of the connection-leak problem, advisory locks, and TRUNCATE deadlocks
The connection_created signal tracking pattern is the recognized best practice
Advisory lock for session-scoped DDL is correct (more robust than FileLock in containers)
transaction=True is necessary for async handler tests with sync_to_async cross-thread DB access
Now, let me synthesize all this into a coherent architectural decision.

The Problem (Restated)
The autouse _reset_moderation_criteria fixture in the bot conftest does DB access (SELECT at setup) for ALL tests, including unit tests without @pytest.mark.django_db. This causes RuntimeError.

The same issue exists in the backend moderation tests conftest, affecting test_decorators.py.

Possible Solutions
Let me enumerate the viable approaches:

Option A: Make _reset_moderation_criteria only do cache.clear() (drop the DB save-and-restore)
Since the researchers confirmed that the DB update() restore is redundant under pytest-django (both TestCase rollback and TransactionTestCase TRUNCATE handle DB state), and the essential part is just cache.clear(), we could:

Remove the ModerationCriteria.objects.filter(pk=1)...first() snapshot and .update() restore
Keep only cache.clear()
This makes the fixture DB-free, so it's safe for unit tests
But wait — this would mean the ModerationCriteria row is TRUNCATE'd after each transaction=True test, and not restored. Tests that need the row would need to recreate it. With transaction=True, the row is TRUNCATE'd, so get_singleton() would get_or_create a fresh one. This is fine because the defaults are model field defaults.

Actually, there's a subtlety: under transaction=True (TransactionTestCase), the TRUNCATE happens in _fixture_teardown() which is called by _post_teardown(), which is called by pytest-django's _django_db_helper AFTER the test body but BEFORE fixture teardowns. So the order is:

Test body runs (modifies ModerationCriteria)
_post_teardown() → TRUNCATE (wipes ModerationCriteria row)
_reset_moderation_criteria teardown → cache.clear() + update() (no-op since row was TRUNCATE'd, snapshot is {} or stale)
Hmm, actually the snapshot is taken BEFORE the test body. If the row existed before the test, snapshot has values. After TRUNCATE, the row is gone. The if snapshot: guard checks the snapshot dict, not the DB — so if snapshot is non-empty (row existed before), update() would try to update pk=1 which no longer exists after TRUNCATE... but filter(pk=1).update(...) would silently do nothing (0 rows affected) because the row was TRUNCATE'd. So it's a no-op.

Wait, but under transaction=True, TRUNCATE happens in _fixture_teardown which is called in TransactionTestCase._post_teardown(). And pytest-django's fixture teardown happens after that. So yes, the row is already TRUNCATE'd when _reset_moderation_criteria teardown runs.

Under default django_db (TestCase), savepoint rollback happens — the row's modifications are rolled back. The row still exists (not TRUNCATE'd), but with original values. Then _reset_moderation_criteria teardown does update() to restore (redundant since rollback already did it) and cache.clear() (essential).

So the conclusion: cache.clear() is essential, update() is redundant. But we still need to handle the cache correctly.

Option B: Guard the DB access in _reset_moderation_criteria with django_db_blocker
Wrap the fixture's DB access in with django_db_blocker.unblock(): — but this would unblock DB access for unit tests, which defeats the purpose of marking them as unit tests (no DB dependency). Also, for unit tests, the ModerationCriteria row might not exist, making the fixture pointless.

Option C: Make _reset_moderation_criteria conditional on DB access
Check if django_db_blocker.is_active or request.node.get_closest_marker("django_db") — only do DB access for tests that have the django_db marker. This is more complex but precise.

Wait, but the researcher said is_active returns True when any block/unblock cycle is open, not whether it's currently blocked. Let me think about the actual API.

Actually, the _django_db_marker autouse fixture from pytest-django wraps the test in a with block that unblocks the DB. The django_db_blocker fixture is a DjangoDbBlocker instance. The .unblock() method sets an internal flag.

The key insight from the researcher: the _live_server_helper pattern checks if "live_server" not in request.fixturenames: return early. This is a pattern where an autouse fixture skips itself if a specific fixture isn't requested.

We could adapt this: check if the test has the django_db marker, and if not, only do cache.clear() (which is DB-free). But the challenge is that cache.clear() on LocMemCache is already DB-free, so the fixture could just always do cache.clear() and conditionally do the DB snapshot/restore.

Option D: Remove _reset_moderation_criteria from the bot conftest entirely, and replace with cache.clear() only
Since the save-and-restore is redundant (per researcher findings) and the only essential part is cache.clear(), we could replace the entire fixture with a DB-free cache-clearing fixture. But this ignores the case where ModerationCriteria might be modified by a test under default django_db (TestCase rollback) — actually, under TestCase rollback, the DB changes are already rolled back, so the cache.clear() is the only thing needed.

But wait — is there a case where ModerationCriteria changes are NOT rolled back? Only if the test uses @pytest.mark.django_db (TestCase) — but then savepoint rollback handles DB, and cache.clear() handles cache. Or if the test uses transaction=True — then TRUNCATE handles DB, and cache.clear() handles cache. Or if the test has no django_db marker — then no DB changes are possible (blocked), so cache.clear() handles any cache changes.

So cache.clear() alone is sufficient in ALL cases. The save-and-restore via update() is truly redundant.

Option E: Separate unit tests from DB tests by directory structure
Move pure unit tests to a tests/unit/ directory with a minimal conftest that doesn't have the autouse DB fixture. This is a bigger refactor.

Option F: Use pytest_collection_modifyitems to auto-apply django_db for integration tests
Not directly relevant to the autouse fixture problem.

Let me think about what the BEST architectural solution is, considering all the constraints:

The bot test tree has both unit tests (no DB) and integration tests (with django_db(transaction=True))
The _reset_moderation_criteria fixture is autouse and does DB access — this is the core problem
The save-and-restore update() is redundant under pytest-django's transaction management
cache.clear() is the only essential operation and is DB-free
Best approach: Replace the DB-touching save-and-restore in _reset_moderation_criteria with a DB-free cache.clear()-only approach, since the save-and-restore is redundant.

But wait — I need to consider: does any test rely on the save-and-restore behavior (i.e., does any test modify ModerationCriteria and expect it to be restored for a subsequent test without transaction=True or TRUNCATE)?

Under default django_db (TestCase), savepoint rollback handles DB restoration. The cache.clear() handles cache. No save-and-restore needed.

Under transaction=True, TRUNCATE handles DB restoration. The cache.clear() handles cache. No save-and-restore needed.

Under no django_db (unit tests), no DB changes are possible. cache.clear() handles cache (though unit tests don't typically touch the cache).

So removing the save-and-restore and keeping only cache.clear() is safe in ALL cases.

But actually, there's a deeper question: is _reset_moderation_criteria even needed at all? Looking at the bot tests:

Unit tests (test_multi_lang_translation.py, test_site_name_greeting.py, test_update_id_dedup.py) — don't touch ModerationCriteria. cache.clear() is unnecessary for them too.
Integration tests — they use transaction=True (TRUNCATE) which handles DB. They monkeypatch service-layer criteria (permissive_criteria/banning_criteria) rather than touching the DB row. So the DB row is never modified by bot tests. The cache.clear() is for the cache LocMem backend — but do bot tests modify the cache in a way that needs clearing?
Looking at _clear_cache_between_tests in the backend conftest (which the bot conftest can't inherit): it clears cache before and after each test. The bot conftest's _reset_moderation_criteria only clears cache in teardown (after yield), not setup.

Hmm, let me think about this differently. What is the ACTUAL purpose of _reset_moderation_criteria in the bot conftest?

Based on the auditor's finding: "the fixture is functionally a no-op for bot tests, yet still mandatory-DB." No bot test creates the ModerationCriteria pk=1 row. So the snapshot is always {}, and the restore is always skipped. The only thing that actually does something is cache.clear().

So the fixture is essentially just cache.clear() — but wrapped in a DB-accessing shell that breaks unit tests.

The cleanest architectural fix:

Replace _reset_moderation_criteria with a DB-free cache-clearing autouse fixture. Since the update() restore is redundant (per pytest-django transaction semantics) and the DB read for snapshot is the thing that breaks unit tests, we should:
Remove the ModerationCriteria.objects.filter(pk=1)...first() snapshot read
Remove the .update(**snapshot) restore
Keep only cache.clear()
Make the fixture name reflect what it does (e.g., _clear_cache_after_bot_test or keep the name but change behavior)
Apply the same fix to the backend moderation tests conftest — the same redundant save-and-restore is there and breaks test_decorators.py.
But wait — the researcher said the update() restore could matter in specific cases. Let me re-read: "The update() restore is only genuinely necessary when operating outside any test transaction via django_db_blocker.unblock() (session-scoped seeding), and even then idempotency is preferred over snapshot/restore."

The _restore_test_schema_post_db_setup session fixture seeds data but doesn't touch ModerationCriteria. And no test modifies ModerationCriteria at the DB level in the bot tree (they all monkeypatch the service layer). So the update() restore is truly redundant.

However, I want to be careful. Let me consider: what if a future test modifies ModerationCriteria at the DB level under default django_db (TestCase)? The savepoint rollback would handle it. What about under transaction=True? TRUNCATE would handle it. So no future test needs the save-and-restore either.

But there's an edge case: what if a test uses @pytest.mark.django_db (TestCase, savepoint rollback) and modifies the ModerationCriteria row AND caches it (via cache.set)? The savepoint rollback restores the DB but not the cache. The cache.clear() handles the cache. So this is fine.

OK, I'm now confident in the approach. But let me also consider the broader architectural question the user asked: "Наша цель сделать корректную правильную архитектуру" (Our goal is to make a correct, proper architecture that is easy to develop and maintain).

Let me think about the ideal architecture:

Problem: The bot test tree mixes unit tests (no DB) and integration tests (with DB) in the same directory. An autouse fixture that does DB access is applied to all tests, breaking unit tests.

Possible architectures:

Single conftest with DB-safe autouse fixtures — The autouse fixture does only DB-free operations (cache.clear()). DB-dependent cleanup is handled by pytest-django's transaction/TRUNCATE. This is the simplest fix.
Separate directories for unit vs. integration tests — Move unit tests to tests/unit/ with a minimal conftest, and keep integration tests in tests/ with the full conftest. This is cleaner separation but more disruptive.
Conditional autouse fixture — The fixture checks whether DB is available (via request.node.get_closest_marker("django_db") or django_db_blocker) and only does DB access for DB-enabled tests. For unit tests, it does only cache.clear().
Given the project's existing conventions and the principle of "minimal yet complete" change, I think the best approach is a combination:

Primary fix: Make _reset_moderation_criteria DB-safe by removing the redundant DB save-and-restore (which is confirmed redundant by the researchers) and keeping only the essential cache.clear(). This:

Fixes all unit tests (no DB access in the fixture)
Maintains cache isolation for integration tests
Is simpler (removes the _CRITERIA_FIELDS tuple, the snapshot logic, the update logic)
Doesn't require changing the directory structure or any test files
Follows the project's existing pattern of DB-free autouse fixtures (like the backend root conftest's _clear_cache_between_tests)
Secondary fix: Apply the same to the backend moderation tests conftest (fix test_decorators.py).

But wait — the user said "Запусти Validator, чтобы выбрать правильное решение" (Launch Validator to choose the right solution). So I should present the options and let the Validator choose.

Actually, looking at the instructions more carefully, the user wants me to:

✅ Launch 2 Auditors — DONE
✅ Launch 3 Researchers — DONE
Launch Validator to choose the right solution
Launch Implementor to implement
Launch Validator to check implementation
Launch Implementor to refine
Commit
But wait, the user's instructions also say "НЕЛЬЗЯ МЕНЯТЬ КОД" for the audit, research, and validation phases. The Implementor phase is where I change code.

Let me also re-read the auditor findings. The auditor found additional issues:

test_ad_lifecycle.py has fixture 'permissive_criteria' not found — the plugin isn't registered for the bot tree
The testing/moderation_fixtures.py docstring is stale
test_decorators.py (backend moderation) also breaks
These are related but separate issues. The user's main complaint is about the _reset_moderation_criteria autouse fixture breaking unit tests. But a proper architectural fix should address all related issues.

Let me think about what the Validator should evaluate. The Validator should choose between:

Option A: DB-free cache.clear() only (remove save-and-restore)

Pros: Simplest, removes redundant code, fixes all unit tests, follows existing pattern
Cons: Loses the "safety net" of restoring ModerationCriteria state (but it's redundant per research)
Option B: Conditional autouse (check django_db_blocker or marker)

Pros: Preserves save-and-restore for DB tests, skips for unit tests
Cons: More complex, still carries the redundant save-and-restore logic, the research says it's redundant anyway
Option C: Separate unit vs. integration test directories

Pros: Cleanest separation, each directory has appropriate fixtures
Cons: Big refactor, moves files around, may break imports
Option D: Make save-and-restore respect django_db_blocker.unblock()

This would allow the fixture to access DB even for unit tests by unblocking
Cons: Defeats the purpose of unit tests (no DB dependency), and the research says the save-and-restore is redundant anyway
I think Option A is the clear winner based on the research findings. But let me also consider the test_ad_lifecycle.py fixture-not-found issue — that's a separate problem that should be addressed too.

Actually, let me re-read the user's request: "The 37 errors are all in test_multi_lang_translation.py (B1's test file)." The user mentions 37 errors in that one file, but the auditor found 19 tests + 2 (site_name) + 3 (update_id_dedup) + maybe more. The discrepancy might be because the user ran a different command or there are parametrized tests making the count higher. Also, test_login_rate_limit.py was mentioned by Auditor 2 as another unit test.

Wait, Auditor 1 mentioned test_login_rate_limit.py as a unit test. Let me check — it wasn't in my original grep results. Let me verify what unit tests exist in the bot tree.

Actually, looking at the grep results earlier, I don't see test_login_rate_limit.py. Auditor 2 mentioned it. Let me check.

Hmm, the grep for pytestmark.*unit returned these bot test files:

test_multi_lang_translation.py
test_site_name_greeting.py
test_update_id_dedup.py
Auditor 2 mentioned test_login_rate_limit.py as having pytestmark = [pytest.mark.unit] but I didn't find it in the grep. Maybe it was added by Auditor 2 or maybe it's in a different location. Let me check.

Actually, Auditor 2 might have been hallucinating or the file was added by another agent. But I should verify.

Let me also think about the full scope. The user said "37 errors are all in test_multi_lang_translation.py". But the auditor found 19 tests in that file. With parametrization, 19 tests could expand to 37 test items. Let me check.

Looking at the test file: test_narrowed_except_catches_httpx_family has @pytest.mark.parametrize with 4 params, and there are 19 test methods. With parametrization, that's 19 + 3 (extra parametrize instances) = 22... hmm, that's not 37.

Actually, the test file has these test methods:

test_returns_dict_with_all_locale_codes
test_translation_non_empty_for_valid_input
test_translates_each_locale_independently
test_timeout_fallback_returns_original_text
test_partial_failure_falls_back_per_locale
test_empty_string_input
test_single_locale
test_circuit_breaker_open_short_circuits
test_timeout_fallback_returns_original
test_empty_string_returns_empty
test_gather_return_exceptions_isolates_failure
test_narrowed_except_catches_httpx_family (parametrized ×4)
test_non_family_error_propagates
test_retry_succeeds_after_transient_failure
test_too_many_requests_retried_then_fallback
test_non_retryable_http_error_not_retried
That's 16 methods + 3 extra from parametrization = 19 test items. Not 37. Unless there's another file or the count includes other bot tests.

The user said "37 errors" — maybe they ran the full bot test suite and 37 tests errored. The 24 (19+2+3) from the 3 unit test files... but that's not 37 either. Maybe test_login_rate_limit.py was also included. Or maybe the count includes some backend tests too.

Actually, the user said "The 37 errors are all in test_multi_lang_translation.py (B1's test file)" — so they're saying all 37 errors are in that one file. But the auditor found only 19 test methods (22 with parametrization).

Hmm, maybe there's a discrepancy because the auditor ran with -p no:xdist and the user ran differently. Or maybe the file was modified. Or maybe the 37 count is approximately right and the exact count doesn't matter.

Regardless, the architectural problem is clear and I have enough information. Let me proceed.

Let me now think about the complete solution:

Complete Solution
The core issue has multiple facets:

Primary bug: _reset_moderation_criteria autouse fixture does DB access → breaks unit tests
Same bug in backend: moderation tests conftest has the same autouse fixture → breaks test_decorators.py
Plugin registration: testing/moderation_fixtures.py plugin is not registered for the bot tree → test_ad_lifecycle.py fails with fixture not found
Stale docstring: testing/moderation_fixtures.py docstring claims dual registration
Redundant save-and-restore: The update() restore is redundant under pytest-django
The best architectural solution:

A. Fix _reset_moderation_criteria in both conftests:

Replace the DB-touching save-and-restore with DB-free cache.clear() only
Since save-and-restore is redundant (per researcher findings: TestCase rollback and TransactionTestCase TRUNCATE both handle DB state), the update() restore adds no value
The cache.clear() is the only essential operation (cache survives transaction boundaries)
This makes the fixture safe for unit tests
Wait, but I need to be more careful. Let me reconsider. The researcher said the save-and-restore is redundant under pytest-django's normal transaction management. But what if ModerationCriteria is NOT managed by pytest-django's transaction wrapper?

In the bot conftest, _reset_moderation_criteria is autouse — it runs for ALL tests, including those with @pytest.mark.django_db and those without. For tests WITH @pytest.mark.django_db, the transaction/rollback handles DB. For tests WITHOUT, the DB is blocked, so no changes happen. So in all cases, cache.clear() is sufficient and the save-and-restore is redundant.

But there's a deeper question: what about the case where a test modifies ModerationCriteria at the DB level using @pytest.mark.django_db (default, TestCase mode)? The savepoint rollback handles the DB. What about using @pytest.mark.django_db(transaction=True)? TRUNCATE handles the DB. So yes, save-and-restore is redundant in all cases under pytest-django.

B. Register pytest_plugins in the bot conftest:

Add pytest_plugins = ("testing.moderation_fixtures",) to the bot conftest
Fix the stale docstring in testing/moderation_fixtures.py
Wait, but Auditor 1 said this is currently fragile — when running the bot tree in isolation, the plugin isn't available. Adding pytest_plugins to the bot conftest would fix this. But the docstring says it's already registered from the bot conftest (which is false). Let me verify — does adding pytest_plugins to the bot conftest work?

The issue is that pytest_plugins in a conftest.py must be in the root conftest (or top-level conftest) for pytest to recognize it. Actually, pytest allows pytest_plugins in conftest.py files at any level, BUT only at the top-level conftest.py (as per pytest docs). Non-top-level conftest files with pytest_plugins are deprecated and may cause warnings/errors.

Actually, looking at the pyproject.toml: pythonpath = ["src", "src/backend"]. The backend root conftest is at src/backend/conftest.py. The bot tests are at src/telegram_bot/tests/conftest.py.

The pytest docs say: pytest_plugins in conftest.py should only be used in the root conftest.py (or the top-level conftest). Using it in non-root conftest files is deprecated and will eventually raise an error.

So the correct fix would be to register pytest_plugins in a root-level conftest (at the project root or at src/ level). But there's no root conftest.py.

Actually, let me re-check. The pytest docs say:

pytest_plugins in non-top-level conftest.py files is deprecated.

But the project already does it in src/backend/conftest.py. This works because when the full suite is collected (testpaths = ["src/backend", "src/telegram_bot"]), the backend conftest is one of the conftest files in scope, and its pytest_plugins is processed during initial conftest loading.

But for the bot tree alone, the backend conftest is not in the discovery chain. So the plugin isn't registered.

The proper fix: create a root-level conftest.py that registers pytest_plugins, or add the permissive_criteria/banning_criteria fixtures to the bot conftest directly.

But actually, looking at the Auditor 1 findings more carefully:

test_ad_create.py has a LOCAL permissive_criteria fixture (lines 48-76) with a comment acknowledging the issue
test_ad_lifecycle.py does NOT have a local copy and fails with fixture not found
So the fix for test_ad_lifecycle.py is either:

Add permissive_criteria/banning_criteria to the bot conftest
Add them locally to test_ad_lifecycle.py
Register pytest_plugins in a root conftest that covers both trees
I think the cleanest approach is to create a root-level conftest.py (at the project root) that registers pytest_plugins = ("testing.moderation_fixtures",). This would make the plugin available to both trees. But wait — the backend conftest already has pytest_plugins. Having it in both would cause a conflict (pytest will raise an error about duplicate plugin registration).

Hmm, actually, pytest allows the same plugin to be registered only once. If both the root conftest and the backend conftest declare pytest_plugins = ("testing.moderation_fixtures",), pytest might raise an error.

The safest approach:

Move pytest_plugins to the project root conftest.py (new file)
Remove it from src/backend/conftest.py
This makes the plugin available to both the backend and bot trees
But wait — there's a subtlety. The backend root conftest at src/backend/conftest.py has pythonpath set to include src/backend. The testing.moderation_fixtures module is at src/backend/testing/moderation_fixtures.py. For the bot tree to import it, src/backend needs to be on pythonpath — which it is (from pyproject.toml: pythonpath = ["src", "src/backend"]).

Actually, let me reconsider the scope. The user's primary complaint is the _reset_moderation_criteria autouse fixture breaking unit tests. The test_ad_lifecycle.py fixture-not-found issue is a related but separate problem that the Auditor discovered. The user might not be aware of it.

Let me focus on the primary issue first and consider the secondary issues as part of the architectural fix.

Let me now launch the Validator to choose the right approach. I'll present the options based on the research findings.

Actually, wait. Looking at the agent types available, the validator agent description says: "Rigorous validator focused on architectural integrity, reliability, long-term maintainability, and implementation correctness."

The user wants me to launch a Validator to "choose the right solution." So I should present the options and have the Validator evaluate them.

But actually, I should first consolidate all the findings myself, present the options, and then launch the Validator. Or I can launch the Validator with all the research findings already provided.

Let me think about the best architecture decision:

The Core Decision
What to do with _reset_moderation_criteria (autouse, DB-accessing)?

Option A: Replace with DB-free cache.clear() only. Remove the save-and-restore (confirmed redundant by research). The fixture becomes just cache.clear() before/after each test. This is DB-free, safe for unit tests, and follows the backend root conftest's pattern (_clear_cache_between_tests).

Option B: Make it conditional on DB access. Guard the DB operations with django_db_blocker or marker checks. For unit tests, skip the DB access and only do cache.clear(). This preserves the save-and-restore for DB tests but adds complexity.

Option C: Remove the fixture entirely from the bot conftest. Rely on pytest-django's transaction/TRUNCATE for DB state and an existing cache-clearing fixture for cache state. But there's no existing cache-clearing autouse in the bot conftest.

My recommendation: Option A. It's the simplest, follows existing patterns, and the research confirms the save-and-restore is redundant. The cache.clear() is the only essential operation. This reduces the fixture from 28 lines of code (with the _CRITERIA_FIELDS tuple) to 4 lines.

But I also need to address:

The test_ad_lifecycle.py fixture-not-found issue (register plugin for bot tree)
The duplicate _reset_moderation_criteria in the backend moderation conftest (fixes test_decorators.py)
The stale docstring
Let me now launch the Validator with all this context.

Actually, I realize I should check if there's a test_login_rate_limit.py file that Auditor 2 mentioned.