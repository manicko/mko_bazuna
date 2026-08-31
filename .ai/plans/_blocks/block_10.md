# Block 10: Search History

## Block Summary

Verifies search-query persistence across authenticated (DB-backed `SearchHistory`) and anonymous (Django `db`-session) user journeys: recording on non-empty queries, display in the cabinet page with a clear action, click-to-rerun, autocomplete suggestions, and the popular-search hit-count gate. Two implementation gaps exist in the autocomplete user-history provider: suggestions are not prefix-filtered against the typed `q` and the spec-required `type` field is absent.

**Source:** `.ai/research/search-journeys-our-architecture.md:149-158`, `.ai/problems/01_search_patterns_test_verification_top_plan.md:210-225`, `.ai/problems/01_search_patterns_verification.md:266-275`
**Top plan:** `.ai/problems/01_search_patterns_test_verification_top_plan.md` — Block 10 (G13), lines 210–225

---

## Findings Table

| # | Variation | Implementation Location | Coverage | Existing Test (file:line) | Test-Engineer Task | Risk |
|---|-----------|------------------------|----------|---------------------------|-------------------|------|
| V1 | Recording trigger & dedup — `search()` calls `record_search_history` inside `if query:` (non-empty, regardless of FTS results). Auth path: delete-before-create dedup by `query_normalized`, prune to 50 (oldest-first). Anon path: session dedup + slice 50. | `search.py:158` (guard); `search.py:192-197` (call site); `search_history.py:42-64` (auth dedup+prune); `search_history.py:27-39` (session dedup+cap); `search_history.py:57` (normalize) | EXISTS | `test_autocomplete.py:328-412` (`TestSearchHistoryService` — 11 tests: create, anon-noop, session-scope, 50-cap, dedup, empty, recent, limit, pruning); `test_autocomplete.py:586-641` (`TestSearchViewRecordsAutocompleteData` — popular+auth+anon recording via view) | Confirmed: trigger on non-empty `q`, auth dedup, anon session scoping, 50-cap. **Gaps (see T1, T4, T5):** (1) no view-level test that `/search/?q=` or `/search/?q=%20%20` creates zero `SearchHistory`/`PopularSearch`; (2) no test for the `query.strip().lower()` normalization transform; (3) `test_history_pruning` (line 408) checks count==50 only, not which entries are pruned. | LOW |
| V2 | Session storage — anon history stored in Django `db` session backend under key `"search_history"` as list of `{query, query_normalized}` dicts (most-recent-first). `SESSION_ENGINE` not overridden in `base.py` → defaults to `django.contrib.sessions.backends.db`. NOT a cookie. | `search_history.py:24` (`_SESSION_KEY`); `search_history.py:34-39` (store/retrieve); `config/settings/base.py` (no `SESSION_ENGINE` override → default `db`) | EXISTS | `test_autocomplete.py:340-363` (session-scope, dedup, 50-cap); `test_autocomplete.py:621-641` (view-level session recording) | Key name + dict shape verified at test_autocomplete.py:352-353. **Gaps (see T2, T7):** (1) no direct unit test on private `_record_session_history`; (2) no explicit assertion that `_SESSION_KEY == "search_history"` as a constant. | LOW |
| V3 | History page — `/cabinet/search-history/` route, `@login_required`, ordered `-created_at` (most-recent-first), renders `created_at` timestamp. `SearchHistory` index on `["user_id", "-created_at"]`. | `cabinet/urls.py:46` (route); `cabinet/views/search_history.py:23-35` (list view); `cabinet/views/search_history.py:20` (`_HISTORY_LIMIT = 100`); `templates/cabinet/search_history.html:38-44` (render); `search/models.py:54-56` (index); `search/migrations/0001_initial.py:92-95` | EXISTS (partial) | `test_cabinet_sections.py:138-158` (`TestSearchHistorySection::test_lists_and_clears_history`) | List + clear happy path covered. **Gaps:** (1) no assertion that entries are most-recent-first in rendered HTML; (2) no test for the 100-row cap (`_HISTORY_LIMIT`); (3) no timestamp rendering assertion. | LOW |
| V4 | Click re-runs search — history entry links to `/search/?q={{ entry.query|urlencode }}`. | `templates/cabinet/search_history.html:40-42` | EXISTS (partial) | `test_cabinet_sections.py:148-152` (checks `"велосипед"` + `"самокат"` in content) | **Gap:** no assertion on the rendered `href` value — test checks text presence, not URL correctness. Add: parse response HTML, assert `href="/search/?q=<urlencoded-query>"` for each entry. | LOW |
| V5a | **Gap**: Autocomplete user-history NOT prefix-filtered — `get_user_search_history(user_id, session=request.session)` at `autocomplete.py:64` returns up to 5 most-recent queries (default limit `search_history.py:93`) with no filtering against the typed `q`. Entity (line 73) and popular (line 77) sources ARE prefix-filtered. | `autocomplete.py:63-69` (unfiltered call + loop); `autocomplete.py:64` (no prefix arg); `search_history.py:91-124` (no prefix param) | **GAP** | None | **Prerequisite implementation:** add `prefix: str | None = None` param to `get_user_search_history` (backward-compatible); filter DB queryset by `query_normalized__istartswith=prefix` and session list by normalized-prefix; pass the typed `q` from `autocomplete.py:64`. Then test: seed history with mixed prefixes (e.g. `авто-дром`, `велосипед`), request `?q=авто`, assert only matching entries appear in `user_history` suggestions. Verify anon session path filters too. | MEDIUM |
| V5b | **Gap**: Autocomplete user-history suggestions missing `type` field — dict at `autocomplete.py:67-68` has only `text`/`source`; spec (`search-patterns.md:302`) requires `type="user_history"`. Frontend works around via `s.type === section \|\| s.source === section` (`header_catalog.html:218`). | `autocomplete.py:66-69` (dict without `type`); `search-patterns.md:302` (spec: `type="user_history"`) | **GAP** | None | **Implementation:** add `"type": SearchSuggestionSource.USER_HISTORY.value` to the suggestion dict. Test: assert every `source="user_history"` suggestion has `type="user_history"`. **Scope note:** `popular_search.py:73-79` also omits `type` per spec (line 305) — confirm whether V5b should extend to popular or remain user_history-only. | LOW |
| V6 | Clear history — `POST /cabinet/search-history/clear/`, `@login_required`, POST-only (405 on GET), wipes all `SearchHistory` rows for `request.user`, 302 redirect. | `cabinet/urls.py:47-51` (route); `cabinet/views/search_history.py:38-45` (view: `@login_required` at 38, 405 at 41-42, delete at 43) | EXISTS (partial) | `test_cabinet_sections.py:138-158` (`test_lists_and_clears_history` — POST clear + redirect + re-render) | **Gaps:** (1) no 405-on-GET assertion; (2) no `@login_required` / anonymous-redirect test; (3) no cross-user isolation test. Add: `GET /cabinet/search-history/clear/` → 405; anonymous `GET /cabinet/search-history/` → 302 to `LOGIN_URL`; clear as buyer doesn't affect `other` user's rows. | LOW |
| V7 | Popular gate — `_MIN_HIT_COUNT = 10`; `get_popular_suggestions` filters `hit_count__gte=10`, prefix-matches `query_normalized__startswith`, orders `-hit_count`, limit 5. | `popular_search.py:19` (constant); `popular_search.py:68-71` (filter) | EXISTS | `test_autocomplete.py:287-317` (`TestPopularSearchService` — 5 tests: threshold, ordering, no-match, empty-prefix) | No action needed — all branches covered with precise assertions. | LOW |

---

## Test Coverage Gaps (Service & Unit)

| # | Gap | Target (file:line) | Status | Existing Test | Task | Risk |
|---|-----|-------------------|--------|---------------|------|------|
| T1 | Empty-query no-op at **view** level — `GET /search/?q=` or `?q=%20%20` must not create `SearchHistory` or increment `PopularSearch` | `search.py:53` (strip), `search.py:158` (`if query:` guard) | GAP | `test_autocomplete.py:372-376` (service-level only — tests `record_search_history(buyer.id, "")` directly) | Integration test: `Client().get("/search/?q=")` + `?q=%20%20` → assert `SearchHistory.objects.count() == 0` and `PopularSearch.objects.count() == 0`. Reuse `TestSearchViewRecordsAutocompleteData` fixture pattern. | LOW |
| T2 | Direct unit test for private `_record_session_history` — dedup + 50-cap + most-recent-first + dict shape | `search_history.py:27-39` | GAP | None (tested indirectly via `record_search_history` at test_autocomplete.py:340) | `pytest.mark.unit` (no `@django_db`): `from django.contrib.sessions.backends.db import SessionStore`; call `_record_session_history` directly; assert one deduped entry, `query_normalized` lowercased, `query` raw, list most-recent-first. | LOW |
| T3 | Session→DB boundary on login — anon session history NOT migrated into `SearchHistory` on login (no-merge contract, `search_history.py:10`) | `search_history.py:7-10` (docstring); `search_history.py:61-64` (anon branch) | GAP | None | Integration: anon `client.get("/search/?q=велосипед")` → session populated → `client.force_login(buyer)` → `client.get("/search/?q=самокат")` → assert `SearchHistory.objects.filter(user=buyer).count() == 1` (only post-login query, NOT "велосипед"). | LOW |
| T4 | `query_normalized` computation — `query.strip().lower()` at `search_history.py:57` | `search_history.py:57` | GAP | None | Service test: `record_search_history(buyer.id, "  Тест  ")` → assert `SearchHistory.query_normalized == "тест"` and `query == "  Тест  "` (raw preserved, normalized stripped+lowercased). | LOW |
| T5 | 50-cap pruning correctness — which entries are pruned (oldest-first, not newest) | `search_history.py:80-88` (`order_by("created_at")` ascending prune) | EXISTS (partial) | `test_autocomplete.py:408-412` (`test_history_pruning` — checks `count() == 50` only) | Extend: after 55 sequential inserts (query0–query54), assert `query0`–`query4` are deleted (oldest pruned) and `query50`–`query54` remain. Backdate via `QuerySet.update()` on `created_at` (auto_now_add ignores passed values). | LOW |
| T6 | `get_user_search_history` anon path | `search_history.py:112-116` | EXISTS | `test_autocomplete.py:387-400` (None+session paths, limit param) | No action needed — both anon branches (no session → `[]`; session → filtered list) + limit param covered. | LOW |
| T7 | Session key name constant — `_SESSION_KEY == "search_history"` | `search_history.py:24` | EXISTS (implicit) | `test_autocomplete.py:352` (`session["search_history"]` accessed inline) | `pytest.mark.unit`: `from apps.search.services.search_history import _SESSION_KEY`; `assert _SESSION_KEY == "search_history"`. Prevents silent key drift. | LOW |

---

## Priority: **MEDIUM**

Block 10 covers search query persistence across the core buyer journey (G13: S1.2–S1.3, S3, S4.2, S6.2). No production-breaking defects, but two variations carry elevated risk:

- **V5a (no prefix filter on user-history suggestions) — MEDIUM/HIGH:** A buyer typing "авто" sees their 5 most-recent queries regardless of whether they start with "авто", producing irrelevant autocomplete suggestions in the primary search entry path (US-B6). The fix requires a backward-compatible signature change to `get_user_search_history` and must preserve both the auth (DB) and anon (session) code paths. This is the highest-priority fix.
- **V5b (missing `type` field) — LOW:** The frontend already works around the absence (`header_catalog.html:218`), so this is correctness/spec-compliance debt, not a functional break. Should be fixed alongside V5a for response-shape consistency.

All other variations (V1, V2, V3, V4, V6, V7) are **implemented and largely tested** — the work is test-gap completion (T1–T5, T7) and defensive assertions (V3 ordering, V4 href, V6 405/login/isolation). These are LOW-risk quality guards.

**Priority ordering:** V5a/V5b (fix + test) → T1 (view-level empty-query) → T3/T4 (normalization + no-merge boundary) → T5 (prune correctness) → T2/T7 (unit tests) → V3/V4/V6 (defensive assertions).

---

## Dependencies (Blocks 2, 3 & 11)

| Depends On | Block / Surface | Rationale |
|---|---|---|
| **Block 2** (Autocomplete Suggestions) | `.ai/plans/_blocks/block_02.md` | V5a/V5b live in the autocomplete view's user-history section (`autocomplete.py:62-69`). Block 2 documents the autocomplete response-shape contract (`search-patterns.md:270-305`, `block_02.md:20`) and the frontend grouping logic (`header_catalog.html:217-232`) that consumes `source`/`type`/`text`. V5b's `type` field must be consistent with Block 2's documented autocomplete response shape. Block 2 V7 already asserts the user_history source path (`test_autocomplete.py:101-120`) — V5a's prefix filter must not break it. |
| **Block 3** (Search Submission & FTS Results) | `.ai/plans/_blocks/block_03.md` | V1's recording trigger fires from `search.py:192-197` inside the Block 3 FTS view (`search.py:158-197`). Block 3 variation 5c/5d verifies the recording side-effects; Block 10 verifies the persistence layer. T1's view-level empty-query no-op test depends on Block 3's `TestSearchViewRecordsAutocompleteData` fixture pattern (`test_autocomplete.py:583`). |
| **Block 11** (Saved Search Modal & Alerts) | `.ai/plans/_blocks/block_11.md` | Both `SavedSearch` and `SearchHistory` live in `apps/search/models.py` and share the `query`/`query_normalized` persistence concept. Block 11's V2 pre-fill captures `query` from the search context (`search.py:225`), which is the same value recorded into history (V1, `search.py:194`). The saved-search modal and search-history views both render within the cabinet section (`cabinet/urls.py`). V5a's `get_user_search_history` signature change must be backward-compatible for any Block 11 consumer. |

**V5a sequencing:** The `get_user_search_history` signature change (adding `prefix: str | None = None`) is backward-compatible (default `None` → no filter). The autocomplete view change (`autocomplete.py:64`) depends on it. Grep confirms only `autocomplete.py:64` calls it in production; test callers pass `limit`/positional args but not `prefix` — safe. V5a must land **before** V5b's `type` test (both touch `autocomplete.py:62-69`).

---

## Validator Recommendations

### V5a — Prefix-filtering for user-history suggestions (MEDIUM)

- **Deployment note (HTMX 2.0):** Under HTMX 2.0, the `htmx:afterRequest` event listener at `header_catalog.html:244` (which renders the autocomplete dropdown that consumes the V5a/V5b-fixed JSON response) continues to work unchanged — `addEventListener` fires both camelCase and kebab-case event forms in HTMX 2.0. No code change needed at the listener. The version tag bump (`@1.9.12`→`@2.0.x`) at `list.html:16` is transparent: V5a/V5b tests assert on the JSON response shape from `/api/search/autocomplete?q=...`, not on client-side event rendering or the version tag.

- **Implementation check:** `autocomplete.py:64` calls `get_user_search_history(user_id, session=request.session)` with no `limit` (uses default 5 at `search_history.py:93`) and no prefix. Confirm the only production caller is `autocomplete.py:64` (grep verified). Add `prefix: str | None = None` param; when set, filter the DB queryset (`query_normalized__istartswith=prefix`, case-insensitive since `query_normalized` is already lowercased) and the anon session list (compare `query_normalized` lowercased prefix). When `None`, behavior is unchanged (backward-compatible).
- **Test (after implementation):** Seed `SearchHistory` rows for `buyer` with `query_normalized` values `"авто-дром"`, `"автобус"`, `"велосипед"`. Request `/api/search/autocomplete?q=авто` → assert `user_history` suggestions contain `"авто-дром"` + `"автобус"` but NOT `"велосипед"`. For anon: seed session via `client.get("/search/?q=велосипед-сессия")` then request `?q=велосипед` → assert `"велосипед-сессия"` appears. Verify the 5-item cap is still respected after filtering.
- **Edge:** If prefix filtering reduces user_history below 5, entity/popular suggestions fill the remaining slots up to `_MAX_SUGGESTIONS=10` (`autocomplete.py:23,90`). Assert total suggestion count ≤ 10.

### V5b — `type` field on user-history suggestions (LOW)

- **Migration note (HTMX 2.0):** No change needed — the `type` field addition to `autocomplete.py:66-69` is server-side JSON, unaffected by HTMX client changes. The autocomplete dropdown is populated from the JSON API response, not from any HTMX event name.

- **Test (after implementation):** Request `/api/search/autocomplete?q=тест` as a user with `SearchHistory` rows. Assert every suggestion with `source == "user_history"` has `type == "user_history"` (matching `SearchSuggestionSource.USER_HISTORY.value` at `enums.py:181`). Verify the existing dedup test (`test_autocomplete.py:177-198`) still passes — dedup is by `"text"` (`autocomplete.py:84`), not `"type"`, so no collision risk.
- **Scope decision (flag to PO):** `popular_search.py:73-79` also omits `type` per spec (`search-patterns.md:305`: `text`, `source`, `type`). Confirm whether V5b should also patch `get_popular_suggestions` or remain user_history-only. The frontend's `s.type === section || s.source === section` fallback (`header_catalog.html:218`) works for both today.

### HTMX 2.0 Migration — No Block 10 Changes Required

HTMX 2.0 migration does not require any Block 10 test or implementation changes. All Block 10 assertions (V1–V7, T1–T7) operate at the Python/Django-view/JSON-API level. The only HTMX touchpoints in rendered Block-10-relevant pages are: (a) the version tag at `list.html:16` (transparent to tests), (b) the `htmx:afterRequest` listener at `header_catalog.html:244` (autocomplete dropdown population — fires identically in 2.0, no rename needed), (c) the `htmx:afterSwap` listener at `header_catalog.html:544` (category submenu — out of scope). B6 (`htmx.get` at `header_catalog.html:536`) is NOT resolved by migration — see Block 1.

### T1 — View-level empty-query no-op

- **Test:** `Client().get("/search/?q=")` and `Client().get("/search/?q=%20%20")` — assert `SearchHistory.objects.count() == 0` and `PopularSearch.objects.count() == 0` after each (the `if query:` guard at `search.py:158` should prevent both `increment_popular_search` and `record_search_history` from running). Reuse the `seller`/`category`/`city` fixtures + `create_test_ad` pattern from `TestSearchViewRecordsAutocompleteData` (`test_autocomplete.py:583-651`).
- **Note:** The service-level no-op (`test_autocomplete.py:372-376`) already covers `record_search_history(buyer.id, "")` directly; the view-level test verifies the `if query:` guard prevents the call entirely at `search.py:158`.

### T2/T7 — Session service unit tests (no DB)

- **HTMX 2.0 note:** These `pytest.mark.unit` tests are completely unaffected by the migration — no DB, no Docker, no HTMX. They exercise the in-memory session service layer directly.

- **T2:** `from django.contrib.sessions.backends.db import SessionStore` — note: `SessionStore()` in a unit test (no DB) works for in-memory attribute access; the `session.modified` flag is set but not persisted without `save()`. This is fine for testing the dedup logic. Call `_record_session_history(session, "тест", " Тест ")` twice; assert `session["search_history"]` has one entry, `query_normalized == "тест"`, `query == " Тест "`, list is most-recent-first with correct dict shape.
- **T7:** `from apps.search.services.search_history import _SESSION_KEY`; `assert _SESSION_KEY == "search_history"` — pure constant check, `pytest.mark.unit`.

### T3 — Session→DB no-merge on login

- **Test:** Anon `client.get("/search/?q=велосипед")` populates `session["search_history"]`. Then `client.force_login(buyer)` and `client.get("/search/?q=самокат")`. Assert `SearchHistory.objects.filter(user=buyer).count() == 1` (only "самокат", never "велосипед"). This validates the no-merge contract documented at `search_history.py:10` and `anonymous-history-research.md:36`.

### T5 — 50-cap pruning correctness

- **Test:** Insert 55 `SearchHistory` rows for `buyer` with staggered `created_at` (backdate via `SearchHistory.objects.filter(pk=...).update(created_at=...)` since `auto_now_add` ignores passed values). Assert `query0`–`query4` (oldest) are deleted and `query50`–`query54` (newest) remain. The prune logic at `search_history.py:83-88` uses `.order_by("created_at")[:excess]` (ascending = oldest first).

### V3 — History page ordering & cap

- **Ordering test:** Create 3 `SearchHistory` rows for `buyer` with staggered `created_at`; `Client` GET `/cabinet/search-history/`; assert response HTML lists them in reverse-chronological order (newest first) by checking text position.
- **Cap test:** Create 105 `SearchHistory` rows for `buyer`; GET `/cabinet/search-history/`; assert exactly 100 entries rendered (matches `_HISTORY_LIMIT = 100` at `cabinet/views/search_history.py:20`, slice at `cabinet/views/search_history.py:29`).

### V4 — History entry link href

- **Test:** Create 2 `SearchHistory` rows (`query="велосипед"`, `query="самокат"`); GET `/cabinet/search-history/`; parse `response.content`; assert `href="/search/?q=%D0%B2%D0%B5%D0%BB%D0%BE%D1%81%D0%B8%D0%BF%D0%B5%D0%B4"` (urlencoded "велосипед") and `href="/search/?q=%D1%81%D0%B0%D0%BC%D0%BE%D0%BA%D0%B0%D1%82"` appear in `search_history.html:40-42` rendered output.

### V6 — Clear-history defensive tests

- **405 on GET:** `client.get("/cabinet/search-history/clear/")` → 405 (view checks `request.method != "POST"` at `cabinet/views/search_history.py:41-42`).
- **Login required:** Anonymous `Client().get("/cabinet/search-history/")` → 302 to `/login/issue/` (`settings.LOGIN_URL` at `base.py:215`).
- **User isolation:** Create `SearchHistory` for `buyer` and `other`; `client` logged in as `buyer` POSTs clear; assert `SearchHistory.objects.filter(user=other).count()` unchanged.

### Environment & fixtures

- All integration tests run in Docker (PostgreSQL on port 5433); bare `uv run pytest` fails. Per-file run: `docker compose --project-name mko-bazuna-test -f docker-compose.yml -f docker-compose.test.yml run --rm -e PYTEST_OPTS="<opts>" test`.
- Unit tests (T2, T7) use `pytest.mark.unit` — no `@django_db`, no Docker.
- Reuse canonical fixtures from `conftest.py:63-116`: `seller` (900000001), `category` (conftest.py:84), `city` (conftest.py:90), `create_test_ad` (conftest.py:105). `buyer` is defined locally in each test module (e.g. `test_autocomplete.py:43-49`, `test_cabinet_sections.py:23-28`).
- i18n: No new translatable strings from Block 10 tests. `search_history.html` template strings are already wrapped (`{% trans %}"…"` at lines 10, 21, 24, 28, 50). Run `make test-i18n` if any test introduces user-visible strings.

---

*End of Block 10*
