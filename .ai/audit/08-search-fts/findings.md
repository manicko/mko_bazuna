---
# Report metadata — fill once per phase report.
phase: "08"
phase_name: "search-fts"
date: "2026-09-28"
auditor: "Executor (subagent)"
validator: ""  # Phase 99 only — omit/blank for raw phase findings
mode: "problems-only"
# Correct prefix per phase: 01-ENT, 02-CFG, 03-DB, 04-AUT, 05-AD, 06-PII, 07-MED, 08-SRH, 09-EXT, 10-QLT, 11-TST, 12-OPS, 13-PERF, 14-I18N
id_prefix: "SRCH-"
# report_status = lifecycle of the report document (draft → validated)
# per-finding Status (in Findings Summary + field table below) = lifecycle of the individual finding (Open → Validated/Rejected/Merged/Reclassified/Deferred)
report_status: "draft"
severity_taxonomy: ".kilo/commands/audit/phases/08-audit-search-fts.md#severity-taxonomy"
---

# Audit Findings — SEARCH-08 (Search & Full-Text Search)

> **Finding-ID prefix note.** `.kilo/commands/audit/phases/08-audit-search-fts.md` §10
> and `templates/audit-findings.md` both specify `SRH-` / `08-SRH`. The executing
> task instruction overrode this with `SRCH-`. `SRCH-` is used throughout.
> Phase 99 must preserve these IDs verbatim; do not renumber to `SRH-NNN`.
>
> **Pre-existing in-source markers.** The search surface already carries hard-coded
> `SRH-001`…`SRH-007` comments (from an earlier audit cycle) in
> `views/search.py:42`, `services/search_history.py:64`,
> `services/category_fuzzy.py:2`, `services/popular_search.py:39`,
> `tests/test_search_view.py:254` and `tests/test_search_translation_outage.py:2`.
> Those markers are *not* finding IDs from this report and do not collide with the
> `SRCH-` prefix used here.

## Executive Summary

The core of the search feature is built well. Search input cannot inject SQL, only
genuinely published listings are ever returned, the full-text index is rebuilt
automatically on every relevant change, category trees expand correctly, results are
paginated and relevance-ranked, and buyers search in their own language with no
per-query translation cost. All of that was confirmed against the real database.

The problems sit at the edges of that core. **A single anonymous visitor can take the
entire shared database offline** by putting a long list of filter values in the address
bar, and **a second anonymous request can crash the public search page** with a
one-character payload. Beyond availability, **anything a visitor types into the search
box — including their own phone number — is copied verbatim into the production log
files**, and the Telegram alert path searches a *different* set of ads than the website
does, so listings the site deliberately hides can still be pushed to subscribers.
**Fifteen issues: 2 critical, 5 high, 5 medium, 3 low.** Two of the critical ones are
availability or data-exposure defects reachable by an unauthenticated visitor; both are
small, localised code changes.

## Scope & Methodology

**Scope:** `src/backend/apps/search` (views `search`/`autocomplete`/`save_search`,
services `cache`/`rate_limit`/`search_history`/`popular_search`/`entity_suggestions`/
`category_fuzzy`/`alert_query`/`immediate_alerts`, `signals.py`, `models.py`,
`schemas.py`, `urls.py`, `management/commands/send_alerts.py`, the whole
`apps/search/tests/` suite), plus the shared surfaces search depends on and mutates:
`apps/ads/services/listings_query.py` (the single visibility predicate),
`apps/ads/services/submission.py` (publish path), `apps/ads/views/listings.py`,
`apps/ads/models.py` (`search_vector*` + GIN), `apps/ads/management/commands/setup_search_triggers.py`,
`apps/users/services/{deletion,account_state}.py`, `apps/moderation/admin_actions.py`,
`apps/core/utils/{sanitize,swr_cache,json_logging}.py`, `apps/core/enums.py`
(`LanguageLocale`), `docker/nginx/nginx.conf`, and the search sections of
`docs/01-spec/{search-patterns,technical-specification,i18n-spec}.md` +
`docs/02-database/{db-indexes,db-schema}.md`.

### Runtime Verification

| R# | Check | Method | Result |
|----|-------|--------|--------|
| R-01 | Only `PUBLISHED` ads are returned by a FTS query (all 7 statuses seeded, one per status) | probe `probe_srh.py::test_visibility_matrix` (`?q=велосипед&lang=ru`) | PASS — `statuses_found: ["published"]` |
| R-02 | Same matrix via the browse path (no `q`) | probe `test_visibility_matrix_no_query` | PASS — `["published"]` |
| R-03 | A **banned** seller's PUBLISHED ad is hidden | probe `test_banned_seller_visible` (`/search/?q=`, `/search/`, `/<id>/`) | **FAIL** → SRCH-008 (`search_contains_banned_ad: true`, detail 200, listings `true`) |
| R-04 | Alert FTS path applies the same visibility predicate as the web path | probe `test_alert_path_ignores_declined` | **FAIL** → SRCH-004 (`alert_matched_declined_ad: true` vs `web_contains_declined_ad: false`) |
| R-05 | Alert FTS path applies the active-category filter | probe `test_alert_path_ignores_inactive_category` | **FAIL** → SRCH-004 (`alert_matched_inactive_cat_ad: true` vs `web_contains_inactive_cat_ad: false`) |
| R-06 | 12 SQL-injection / unicode / oversized payloads never 500 and never mutate the DB | probe `test_injection_payloads` | PASS — all `200`, `ads_table_intact: 1` |
| R-07 | A NUL byte in `q` is handled safely | probe `test_nul_byte_query_500` on `/search/` **and** `/api/search/autocomplete` | **FAIL** → SRCH-006 (`psycopg.DataError: … cannot contain NUL (0x00) bytes`, unhandled) |
| R-08 | The FTS predicate is a bound parameter, never interpolated SQL | probe `test_fts_sql_is_parameterized` (`sql_with_params()`) | PASS — `interpolated: false`, `params: ["russian", "велосипед'; DROP TABLE ads; --"]` |
| R-09 | `?features=` list is bounded | probe `test_unbounded_features_list` (0/5/20/40/60) + `test_pydantic_no_bound` (500) | **FAIL** → SRCH-001 (SQL 524 → 1 389 → 3 559 → 6 459 → 9 431 B; 500 features ⇒ 76 771 B / 502 JOINs) |
| R-10 | A long `?features=` list degrades gracefully | isolated probe `dos.py` (120 features, own container run) | **FAIL** → SRCH-001 (30.11 s, then `OperationalError: server closed the connection unexpectedly`; DB entered `FATAL: the database system is in recovery mode`) |
| R-11 | The same bomb reaches the `/` browse page (shared builder) | probe `probe3.py::test_listings_shares_the_features_bomb` | **FAIL** → SRCH-001 (10/40/100/300 features ⇒ 3 577/7 867/16 759/46 759 B, 302 `features` references) |
| R-12 | Parent-category query returns the whole subtree, wrong branch excluded, count correct | probe `test_category_tree` | PASS — root `true`, child `true`, `other_branch: false`, `total_count: 2` |
| R-13 | A plain multi-word query is not narrowed by the fuzzy-category path | probe `test_fuzzy_category_cross_branch` | PASS — `two_word_match: true`, `one_word_match: true` |
| R-14 | A single word that *fuzzy-matches* a category does not hide matches in other branches | probe `test_fuzzy_similar_word_hides_other_branch` | **FAIL** → SRCH-009 (`bikes_branch: true`, `electronics_branch: false` for an identical title) |
| R-15 | Each locale hits its own vector + config; no query-time translation | probe `test_per_language_vectors` | PASS — `ru.hits: true`, `ru_vector_matches: true`, `en_vector_matches: true`, `bs_vector_is_empty: true` (degraded cross-language recall, not a 500) |
| R-16 | Raw query text does not reach the logs / is redacted by the prod formatter | probe `test_pii_in_logs` (captures the real record, renders it through `RedactingJsonFormatter`) | **FAIL** → SRCH-002 (message contains `Иван Петров +38269123456 ivan@example.com` verbatim) |
| R-17 | Persisted `SearchHistory` / `PopularSearch` never keep un-redacted PII | probe `test_history_and_popular_store_raw` | **FAIL** — but owned by **PII-108**; recorded here as cross-reference only, not re-filed |
| R-18 | `PopularSearch.query_normalized` is unique, so `get_or_create` cannot fan out | probe `test_popular_search_duplicate_rows` + `test_popular_search_constraint_present` (live `pg_index` introspection) | **FAIL** → SRCH-003 (`MultipleObjectsReturned: … it returned 2!`, unhandled; only `popular_searches_pkey` is unique) |
| R-19 | Per-IP rate limit cannot be bypassed | probe `test_ratelimit_xff_spoof` (60 rotating `X-Forwarded-For` vs 40 fixed-IP) | **FAIL** → SRCH-010 (`xff_rotating_429s: 0/60` vs `fixed_ip_429s: 10/40`) |
| R-20 | Restoring consent makes the seller's ads findable again through the view | probe `test_cache_stale_after_consent_restore` | **FAIL** → SRCH-005 (`visible_after_give_consent: false`, `search_version` unchanged) |
| R-21 | A bulk `User.objects.update(...)` that hides ads invalidates cached results | probe `test_cache_stale_after_bulk_user_update` | PASS — `bumped: false` but `still_visible: false`; the cache-hit path re-applies the live `user__is_declined=False` predicate, so the stale ID list cannot leak a hidden ad |
| R-22 | The search content version is monotonic | probe `probe2.py::test_version_reissued` | **FAIL** → SRCH-007 (`key_reused: true`, `cache_hit_cycle2: [2]` — a result set from the *previous* cycle is served again) |
| R-23 | `SavedSearch.query` is length-bounded | probe `probe2.py::test_saved_search_query_unbounded` | **FAIL** → SRCH-011 (50 000 chars submitted and stored verbatim) |
| R-24 | Empty / whitespace / stop-word-only / punctuation-only queries are safe | probe `test_empty_and_stopword_queries` | PASS — all `200` (`total` 1/1/0/0) |
| R-25 | `page`, `sort`, `min_price`, `category`, `city` are coerced, never 500 | probe `test_page_and_sort_bounds` (7 hostile values) | PASS — all `200` |
| R-26 | Publishing an ad cannot desynchronise the FTS index (promote before `transaction.atomic()`) | `read` `apps/ads/services/submission.py:161-169` + `setup_search_triggers.py` DDL | PASS — the trigger is `BEFORE INSERT OR UPDATE … FOR EACH ROW` and derives the vectors only from `title*`/`description*`/`categories.name`, none of which the status transition touches; the promote is the same autocommit statement as its `post_save`, so the cache bump is adjacent, not deferred |
| R-27 | Search quality gates | `uv run ruff check src/backend/apps/search/ …` + `uv run basedpyright src/backend/apps/search/`; `pytest src/backend/apps/search src/backend/apps/ads/tests/test_setup_search_triggers.py` (248 tests, `--reuse-db`) | PASS (0 lint errors, 0 type errors, 248 passed) |

> PASS results prove the audit was thorough; they are METHODOLOGY evidence, NOT findings.

**Tools used:** `docker compose … run` inside `mko-bazuna-test` (PostgreSQL 18 on host :5433);
three throwaway probe modules plus one isolated DoS reproduction under `.ai/tmp/srh/`
(all deleted at the end — **no scratch database was created**; every check ran inside
pytest-django's own `test_mko_bazuna`); Django test `Client` against the real URLconf,
middleware and views with `DEBUG=False`; live `pg_index` / `pg_trigger` introspection;
`RedactingJsonFormatter`; `ruff`, `basedpyright`, `pytest`.

**Assumptions:**
1. The `mko-bazuna-dev` web/bot containers are crash-looping (CFG-006), so no live reverse
   proxy was available. All HTTP evidence comes from Django's test client against the real
   URLconf, middleware and views. nginx behaviour was assessed by reading
   `docker/nginx/nginx.conf`, not by issuing requests through it.
2. PostgreSQL 18, Django 5.2, `config.settings.test`, `MIGRATION_MODULES` disabled, and
   the `ads_search_vector_update` trigger installed by the conftest session fixture
   (the same three steps as the production `migrate` one-shot).
3. **Test-DB prerequisite discovered during this audit:** a probe or test module placed
   *outside* `src/backend/` does not inherit the root `conftest.py` autouse session fixture
   `_restore_test_schema_post_db_setup`, so the search-vector trigger is **not** installed
   and every FTS assertion silently reports "0 hits" instead of failing loudly. A first pass
   of this probe was invalidated by exactly that. All reported results come from runs where
   the trigger was confirmed present (`pg_trigger` → `ads_search_vector_update`, `tgenabled = O`).
4. The phase-13 (performance) agent owns latency/query-plan grading. This report records
   SQL *size* and *shape* only as a security/availability signal, and defers all
   latency/throughput interpretation.

## Findings Summary

| ID | Title | Severity | Status | Category |
|----|-------|----------|--------|----------|
| SRCH-001 | `?features=` list is unbounded — one anonymous request joins 120+ tables and kills the PostgreSQL backend, dropping the whole shared DB into crash recovery | CRITICAL | Open | Availability / Denial of service |
| SRCH-002 | The raw search string — phone numbers, e-mails and personal names included — is written verbatim to production JSON logs | CRITICAL | Open | Privacy / log hygiene (CWE-532) |
| SRCH-003 | `PopularSearch.query_normalized` has no UNIQUE constraint, so concurrent searches create duplicates and the *next* search raises an unhandled `MultipleObjectsReturned` → HTTP 500 | HIGH | Open | Reliability / Data integrity |
| SRCH-004 | The alert FTS read path uses a weaker visibility predicate than the web search path, so ads hidden on the site are still fanned out to Telegram subscribers | HIGH | Open | Correctness / Privacy / Architecture |
| SRCH-005 | `give_consent()` does not bump the search content version, so a seller who re-accepts consent stays invisible in search for up to 360 s | HIGH | Open | Correctness |
| SRCH-006 | A NUL byte in `q` raises an unhandled `psycopg.DataError` → HTTP 500 on `/search/` and `/api/search/autocomplete` | HIGH | Open | Availability / Input validation |
| SRCH-007 | The search content-version counter inherits the 300 s default cache TTL, so it expires and the next bump re-issues an already-used version, resurrecting a stale result set | HIGH | Open | Correctness / Caching |
| SRCH-008 | Banned sellers' ads stay publicly searchable, listed and directly reachable — the visibility predicate has no `is_banned` term | MEDIUM | Open | Visibility gating / Authorization |
| SRCH-009 | A single-word query that fuzzy-matches a category name is silently restricted to that category's subtree, hiding textually identical ads in other branches | MEDIUM | Open | Relevance / Correctness |
| SRCH-010 | The app-level per-IP rate limit is bypassable by spoofing `X-Forwarded-For` (third verbatim copy of the client-IP helper) | MEDIUM | Open | Security hardening (CWE-290) / Duplication |
| SRCH-011 | `SavedSearch.query` is an unbounded `TextField` fed straight from the POST body and later fed to `SearchQuery` on the alert path | MEDIUM | Open | Input validation / Availability |
| SRCH-012 | This phase's own rubric requires DECLINE **not** to hide PUBLISHED ads; the shipped spec and code do the opposite — the rubric is the outlier | MEDIUM | Open | Documentation / Spec conflict |
| SRCH-013 | `/search/` and `/` use two unrelated rate limiters (30/min vs 60/10 min) with no documented rationale | LOW | Open | Consistency |
| SRCH-014 | `cache.py` claims the stale entry "is refreshed in the background"; the SWR helper recomputes **inline** on the stale-hit path | LOW | Open | Documentation / Maintainability |
| SRCH-015 | On the cache-hit path `has_results` comes from the cached ID count while `page_obj` is re-filtered by the live predicate, so the page can report N results and render none | LOW | Open | Correctness / UX |

## Distribution

**Severity counts**

| CRITICAL | HIGH | MEDIUM | LOW |
|----------|------|--------|-----|
| 2 | 5 | 5 | 3 |

**Status counts**

| Status | Count |
|--------|-------|
| Open | 15 |

> Note: Status is `Open` for all findings in raw phase reports. Phase 99 validation mutates Status to `Validated` / `Reclassified` / `Merged` / `Rejected` / `Deferred`. Values `Fixed` / `Verified` are forbidden here — they belong to a remediation tracker, not the audit report.

### Severity-mapping notes (for Phase 99)

* **SRCH-001 is escalated to CRITICAL** beyond the rubric's literal CRITICAL list. Its nearest
  taxonomy anchor is HIGH ("No pagination/limit enabling DoS" / "Unbounded query latency"),
  but a *single unauthenticated request* terminates the PostgreSQL backend and forces
  crash-recovery of the single DB shared by web, bot and scheduler — i.e. it is a total
  outage of the whole product, not a slow query. A validator may legitimately reclassify
  it to HIGH.
* **SRCH-002 sits inside the rubric's literal CRITICAL band** ("PII leaks in search logs or
  analytics query strings") and directly contradicts the phase's own named evidence claim
  (§4.7 presents `sanitize_query_for_log` as the PII control — it is not one).
* **SRCH-003/005/006/007** are HIGH: an unavailable page, a wrong audience, or a result set
  the user is not yet entitled to see. None is a confidentiality breach on its own, so none
  meets the CRITICAL band as written.
* **SRCH-012 overlaps PII-105 / PII-113** (phase 06 filed the authoritative version of the
  DECLINE documentation conflict). It is kept here only because this phase's own acceptance
  criteria (§2, §4.1, §5a, §8) depend on it, and a reader of this report must not conclude
  that phase 08 silently skipped the check. It carries no independent recommendation.

## Findings by Severity

### CRITICAL

#### SRCH-001: [CRITICAL] — `?features=` list is unbounded — one anonymous request joins 120+ tables and kills the PostgreSQL backend, dropping the whole shared DB into crash recovery

| Field | Value |
|---|---|
| **ID** | SRCH-001 |
| **Title** | `?features=` list is unbounded — one anonymous request joins 120+ tables and kills the PostgreSQL backend, dropping the whole shared DB into crash recovery |
| **Severity** | CRITICAL |
| **Category** | Availability / Denial of service |
| **File(s)** | `src/backend/apps/ads/services/listings_query.py:57`, `src/backend/apps/ads/services/listings_query.py:183-186`, `src/backend/apps/search/views/search.py:101`, `src/backend/apps/ads/views/listings.py:249` |
| **Status** | Open |
| **Problem** | `ListingsQueryParams.feature_slugs` is a bare `list[str]` with no length bound and no validator, and `ListingsQuery.build_queryset` adds **one `features__slug=` JOIN per element** in a Python loop. The value comes straight from `request.GET.getlist("features")` on two *unauthenticated* endpoints (`/search/` and `/`, the highest-traffic page on the site). A client therefore dictates the join count of the SQL that PostgreSQL is asked to plan and execute. |
| **Impact** | One anonymous GET to `/search/?q=велосипед&lang=ru&features=f0&…&features=f119` produced a 30.11 s query after which PostgreSQL **terminated the backend mid-request** (`consuming input failed: server closed the connection unexpectedly`) and the database entered `FATAL: the database system is in recovery mode`. Because web, bot and scheduler share one PostgreSQL 18 instance, one visitor's URL takes the entire product offline — every page, every Telegram flow, the login flow, the scheduler cycle — for the duration of crash recovery. The same bomb is reachable on `/` (browse) because both views call the same builder. At a smaller size the query merely occupies a worker for ~9 s (60 features ⇒ 9 431 B of SQL) and scales linearly: 500 features ⇒ 76 771 B of SQL and 502 `features` references. No login, no CSRF token, no special header required. |
| **Root Cause** | The Pydantic DTO that is supposed to be this view's input boundary (`ListingsQueryParams`) validates the *scalars* carefully — `_coerce_int_or_none`, `_coerce_sort`, `_coerce_page` all exist precisely because unbounded scalars caused earlier 500s — but the one list-typed filter was left unbounded. Nothing between the raw query string and the SQL builder constrains it. The written spec's boundedness story covers `q` (200 chars) and `page`/`per_page` but says nothing about multi-select filters, so this is a missing rule rather than a deviation from one. |
| **Recommendation** | Bound the list at the boundary where the other inputs are already bounded: add a `max_length` to `ListingsQueryParams.feature_slugs` (using a module-level `Final[int]`, e.g. `MAX_FEATURE_FILTERS`, per the project's "no magic constants" rule — the UI never needs more than one category's resolved feature set) and truncate in `ListingsQuery.build_queryset` so a caller that bypasses Pydantic is still safe. Add a regression test asserting that 500 `?features=` parameters produce at most `MAX_FEATURE_FILTERS` joins and return HTTP 200. Truncating (rather than rejecting with 400) keeps the failure mode graceful. |
| **Effort** | S |
| **Priority** | P0 |

| Field | Value |
|---|---|
| **Reproduction Steps** | 1. Start the documented Docker stack (or the `mko-bazuna-test` project). 2. As an anonymous client, `GET /search/?q=велосипед&lang=ru` with 120 `features=` parameters (`features=f0&features=f1&…&features=f119`). 3. Observe a ~30 s response followed by `OperationalError: consuming input failed: server closed the connection unexpectedly`; the next DB connection returns `FATAL: the database system is in recovery mode`. |
| **Related Findings** | — |

**Evidence — `src/backend/apps/ads/services/listings_query.py:57,183-186`** *(supports: "one `features__slug=` JOIN per element, driven by an unbounded list in the input DTO")*:
```python
    feature_slugs: list[str] = Field(default_factory=list)   # :57 — no max_length, no validator
    ...
    if params.feature_slugs:                                  # :183
        for slug in params.feature_slugs:                     # :184
            ads = ads.filter(features__slug=slug)             # :185  → one JOIN per element
        ads = ads.distinct()                                  # :186
```

**Evidence — `src/backend/apps/search/views/search.py:101`, `src/backend/apps/ads/views/listings.py:249`** *(supports: "the unbounded list arrives straight from the raw query string on two unauthenticated endpoints")*:
```python
    feature_slugs=request.GET.getlist("features"),   # search.py:101  (public, no login)
    feature_slugs=request.GET.getlist("features"),   # listings.py:249 (public, no login)
```

**Evidence — `probe3.py::test_listings_shares_the_features_bomb` / `probe_srh.py::test_pydantic_no_bound`** *(supports: "SQL size grows linearly and without limit; 500 filters ⇒ 76 771 B and 502 `features` references")*:
```text
[P3] {"features": 10,  "sql_len": 3577,  "features_mentions": 12}
[P3] {"features": 40,  "sql_len": 7867,  "features_mentions": 42}
[P3] {"features": 100, "sql_len": 16759, "features_mentions": 102}
[P3] {"features": 300, "sql_len": 46759, "features_mentions": 302}
[R7b] {"accepted": 500, "sql_len": 76771, "feature_joins": 502}
```

**Evidence — isolated reproduction `dos.py` (own container invocation, 120 features)** *(supports: "a single anonymous request terminates the PostgreSQL backend and the shared database enters crash recovery")*:
```text
[DOS] {"n": 120, "elapsed_s": 30.11,
 "exception": "OperationalError: consuming input failed: server closed the connection unexpectedly
               This probably means the server terminated abnormally before or while processing the request."}
# then, on the next connection:
# FATAL:  the database system is in recovery mode
```

**Evidence — `docker/nginx/nginx.conf:121-128`** *(supports: "the outer nginx limiter does not prevent this — it caps request *rate*, not query *complexity*")*:
```nginx
        location /search/ {
            limit_req zone=search_limit burst=40 nodelay;   # 20r/s per $binary_remote_addr
            proxy_pass http://web:8000;
        }
```

---

#### SRCH-002: [CRITICAL] — The raw search string — phone numbers, e-mails and personal names included — is written verbatim to production JSON logs

| Field | Value |
|---|---|
| **ID** | SRCH-002 |
| **Title** | The raw search string — phone numbers, e-mails and personal names included — is written verbatim to production JSON logs |
| **Severity** | CRITICAL |
| **Category** | Privacy / log hygiene (CWE-532: Insertion of Sensitive Information into Log File) |
| **File(s)** | `src/backend/apps/search/views/search.py:191-194`, `src/backend/apps/core/utils/sanitize.py:108-124`, `src/backend/apps/core/utils/json_logging.py:29-32,63-65`, `src/backend/apps/core/utils/sanitize.py:86-105` |
| **Status** | Open |
| **Problem** | When a search returns nothing, the view writes the **raw, user-supplied `q`** to an `INFO` log record: `logger.info("Empty search results for query '%s'", sanitize_query_for_log(query))`. `sanitize_query_for_log` only strips control characters and truncates to 100 chars — it performs **no** PII redaction. The production formatter `RedactingJsonFormatter` is also not a defence here: its only string rule is `redact_string()`, which rewrites credential-shaped `key=value` pairs (`password=`, `token=`, …). A search string has no `=` after a sensitive key, so it passes through byte-for-byte. The correct redactor for this payload, `redact_search_query()`, already exists in the same module and is used on the *persistence* path — it is simply not applied on the *logging* path. |
| **Impact** | On a classifieds board the single most natural thing a buyer types into a search box is their **own phone number** (to find the ad they posted), a name, or an e-mail address. Every such query that returns no hits is written verbatim into the JSONL log stream that ships to the log aggregator, where it is retained on the aggregator's schedule and is outside the reach of `withdraw_consent()` — the user has no mechanism to delete it. This is a GDPR Art. 4(1) personal-data exposure that the audit rubric explicitly lists as CRITICAL, and the phase's own §4.7 names `sanitize_query_for_log` as the control that prevents it; that assumption is false. The exposure is unbounded in volume: the endpoint is unauthenticated and the line fires on every zero-result query. |
| **Root Cause** | Two similarly-named helpers with different contracts live side by side in `apps.core.utils.sanitize`. `sanitize_query_for_log` is a *log-injection* control (control chars, truncation) and is named in a way that invites use as a privacy control; `redact_search_query` is the *privacy* control. The view picked the first for a privacy-relevant field, and no test asserts that a PII-shaped query is absent from the emitted log record — the existing redaction test (`test_redact_search_query.py`) only covers the persistence path. |
| **Recommendation** | Compose the two, do not choose between them: in `search.py:191-194` pass `redact_search_query(sanitize_query_for_log(query))` (or add a single `sanitize_and_redact_for_log()` helper in `sanitize.py` and use it at every log call site that receives user text). Then add a regression test that captures the record with `caplog`, renders it through `RedactingJsonFormatter`, and asserts the phone/e-mail/name fragments are absent. As defence in depth, consider dropping the query text from the `INFO` line altogether and logging the SHA-256 prefix instead — the log's operational value is "an empty search happened", not "what was typed". |
| **Effort** | S |
| **Priority** | P0 |

| Field | Value |
|---|---|
| **Reproduction Steps** | 1. Warm the search endpoint. 2. As an anonymous client `GET /search/?q=<URL-encoded "Иван Петров +38269123456 ivan@example.com">&lang=ru` (no matching ads). 3. Capture the `apps.search.views.search` INFO record and format it with `apps.core.utils.json_logging.RedactingJsonFormatter`. 4. Observe the message field containing all three PII values verbatim. |
| **Related Findings** | PII-102, PII-112, PII-114 (same root cause class: per-call-site masking instead of a single logging policy) |

**Evidence — `src/backend/apps/search/views/search.py:191-194`** *(supports: "the raw user-supplied query reaches an INFO log record through a helper that does not redact")*:
```python
    if query and not has_results:
        logger.info(
            "Empty search results for query '%s'", sanitize_query_for_log(query)
        )
```

**Evidence — `src/backend/apps/core/utils/sanitize.py:108-124` vs `:86-105`** *(supports: "`sanitize_query_for_log` is a log-injection control, not a privacy control; the privacy control exists in the same module and is not used here")*:
```python
def sanitize_query_for_log(query: str | None) -> str:
    if not query:
        return ""
    cleaned = _CONTROL_CHAR_PATTERN.sub("", query)     # control chars only
    return cleaned[:_MAX_QUERY_LENGTH]                 # truncation only

def redact_search_query(query: str) -> str:            # the privacy control — NOT called here
    redacted = _EMAIL_PATTERN.sub(_mask_email, query)
    redacted = _PHONE_PATTERN.sub(_mask_phone, redacted)
    redacted = _NAME_PATTERN.sub(_mask_name, redacted)
    return redacted[:_MAX_QUERY_LENGTH]
```

**Evidence — `src/backend/apps/core/utils/json_logging.py:29-32,63-65`** *(supports: "`RedactingJsonFormatter` only rewrites credential-shaped key=value pairs, so a search string passes through unchanged")*:
```python
_REDACT_STRING_PATTERN = re.compile(
    r"(password|token|secret|api[_-]?key|authorization|key)\s*[:=]\s*\S+", re.IGNORECASE
)
def redact_string(text: str) -> str:
    return _REDACT_STRING_PATTERN.sub(r"\1=REDACTED", text)   # no "phone"/"e-mail" rule
```

**Evidence — `probe_srh.py::test_pii_in_logs`** *(supports: "the production JSON formatter emits the PII verbatim")*:
```text
[R11] {"pii_query": "Иван Петров +38269123456 ivan@example.com",
       "sanitize_keeps_phone": true, "sanitize_keeps_email": true, "sanitize_keeps_name": true,
       "log_lines": ["{\"timestamp\": \"2026-09-28 03:38:19,063\", \"level\": \"INFO\",
        \"message\": \"Empty search results for query 'Иван Петров +38269123456 ivan@example.com'\",
        \"logger\": \"apps.search.views.search\", \"stack_info\": null}"]}
```

### HIGH

#### SRCH-003: [HIGH] — `PopularSearch.query_normalized` has no UNIQUE constraint, so concurrent searches create duplicates and the *next* search raises an unhandled `MultipleObjectsReturned` → HTTP 500

| Field | Value |
|---|---|
| **ID** | SRCH-003 |
| **Title** | `PopularSearch.query_normalized` has no UNIQUE constraint, so concurrent searches create duplicates and the *next* search raises an unhandled `MultipleObjectsReturned` → HTTP 500 |
| **Severity** | HIGH |
| **Category** | Reliability / Data integrity |
| **File(s)** | `src/backend/apps/search/services/popular_search.py:44-52`, `src/backend/apps/search/models.py:17-18,33-34` |
| **Status** | Open |
| **Problem** | `increment_popular_search()` uses `PopularSearch.objects.get_or_create(query_normalized=normalized, …)` on every single search — a hot, unauthenticated, cache-independent write. `query_normalized` carries only `db_index=True`; the model's `Meta` declares no `UniqueConstraint` and no migration adds one. Django's `get_or_create` is only race-safe when the lookup column carries a unique index: it catches `IntegrityError` and re-reads, but with no unique index two concurrent `SELECT`-miss → `INSERT` pairs both commit. From that point on, the *next* search for the same query raises `MultipleObjectsReturned`, which the view does not catch. |
| **Impact** | Reproduced end-to-end: with two `popular_searches` rows for the same `query_normalized`, the next `GET /search/?q=велосипед&lang=ru` raised `django.core.exceptions.MultipleObjectsReturned: get() returned more than one PopularSearch -- it returned 2!` straight through the view → HTTP 500 on the primary public search page. A popular query is exactly the query that gets typed concurrently, so this is not a theoretical race: any burst of simultaneous first-time searches on a trending term plants the duplicate, and the 500 then persists for every subsequent search on that term until somebody cleans the table. It also breaks the autocomplete popularity ranking (`get_popular_suggestions` would return the same text several times, though dedup masks that). |
| **Root Cause** | `get_or_create` was chosen as "the atomic way" (the docstring says "Uses `get_or_create` for the initial insert and an `F()` expression for a race-safe increment") without the accompanying invariant that makes it safe. The follow-up `filter(pk=…).update(hit_count=F("hit_count") + 1)` is genuinely race-safe; the `get_or_create` in front of it is not, because the model's natural key is not declared unique. Nothing in the test suite creates two rows for the same key, so the failure cannot be reached by a unit test as written. |
| **Recommendation** | Add the invariant the code already assumes: a migration adding `UniqueConstraint(fields=["query_normalized"], name="uq_popular_searches_query_normalized")` (or `unique=True` on the column), with a preceding de-duplication step that merges duplicate rows by summing `hit_count` and keeping the newest `last_seen`. That converts the race into a single `INSERT … ON CONFLICT` that Django's `get_or_create` already knows how to recover from, and it also gives the table a real natural key. Add a regression test that seeds two rows and asserts `increment_popular_search` no longer raises (it will fail on the constraint until the migration lands). Independently, consider wrapping the whole increment in a `try/except MultipleObjectsReturned` fallback or moving it out of the request path, so a data-quality problem can never take the search page down. |
| **Effort** | S |
| **Priority** | P0 |

| Field | Value |
|---|---|
| **Reproduction Steps** | 1. `PopularSearch.objects.create(query_normalized="велосипед", query="велосипед", hit_count=1)` twice (which is what two concurrent first searches do in production). 2. `GET /search/?q=велосипед&lang=ru`. 3. Observe `MultipleObjectsReturned` propagating out of the view → HTTP 500. |
| **Related Findings** | — |

**Evidence — `src/backend/apps/search/services/popular_search.py:44-52`** *(supports: "`get_or_create` is the only guard and it depends on a uniqueness the schema does not provide")*:
```python
    obj, created = PopularSearch.objects.get_or_create(
        query_normalized=normalized,
        defaults={"query": redacted, "hit_count": 1},
    )
    if not created:
        PopularSearch.objects.filter(pk=obj.pk).update(
            hit_count=F("hit_count") + 1,
            query=redacted,
        )
```

**Evidence — `src/backend/apps/search/models.py:17-18,33-34`** *(supports: "the natural key is indexed but not unique, and Meta declares no constraint")*:
```python
    query = models.CharField(max_length=200, db_index=True)
    query_normalized = models.CharField(max_length=200, db_index=True)   # db_index, NOT unique
    ...
    class Meta:
        db_table = "popular_searches"          # no UniqueConstraint anywhere
```

**Evidence — live `pg_index` introspection (`probe_srh.py::test_popular_search_constraint_present`)** *(supports: "the only unique index on the table is the primary key")*:
```text
[R13b] {"indexes": [["popular_searches","popular_searches_pkey",true],
                    ["popular_searches","popular_searches_query_591d8f7d",false],
                    ["popular_searches","popular_searches_query_591d8f7d_like",false],
                    ["popular_searches","popular_searches_query_normalized_c335c338",false],
                    ["popular_searches","popular_searches_query_normalized_c335c338_like",false],
                    ["popular_searches","popular_searches_source_5986d82c",false],
                    ["popular_searches","popular_searches_source_5986d82c_like",false]]}
```

**Evidence — `probe_srh.py::test_popular_search_duplicate_rows`** *(supports: "the next search on a duplicated key is an unhandled 500")*:
```text
[R13] {"second_search_code": "EXC MultipleObjectsReturned: get() returned more than one PopularSearch -- it returned 2!",
       "rows": 2}
```

---

#### SRCH-004: [HIGH] — The alert FTS read path uses a weaker visibility predicate than the web search path, so ads hidden on the site are still fanned out to Telegram subscribers

| Field | Value |
|---|---|
| **ID** | SRCH-004 |
| **Title** | The alert FTS read path uses a weaker visibility predicate than the web search path, so ads hidden on the site are still fanned out to Telegram subscribers |
| **Severity** | HIGH |
| **Category** | Correctness / Privacy / Architecture |
| **File(s)** | `src/backend/apps/search/services/alert_query.py:43-45`, `src/backend/apps/ads/services/listings_query.py:134-139` |
| **Status** | Open |
| **Problem** | There are two independent full-text read paths over the same `search_vector_*` columns with **two different visibility predicates**. The web path goes through `ListingsQuery.build_queryset`, which applies `status=PUBLISHED`, `user__is_declined=False` and a null-safe active-category filter. The alert path (`find_matching_ads`, used by the daily `send_alerts` command) starts from `Ad.objects.filter(status=AdStatus.PUBLISHED)` and nothing else — it does not join the user's account state and does not check `category.is_active`. |
| **Impact** | Verified: an ad owned by a **consent-declined** seller — whose listing is deliberately removed from `/search/`, from `/` and from its own detail page — is still matched by `find_matching_ads` (`alert_matched_declined_ad: true` while `web_contains_declined_ad: false` in the same probe run). The same is true for ads in a **deactivated** category (`alert_matched_inactive_cat_ad: true` vs `web_contains_inactive_cat_ad: false`). Those ads are then pushed to subscribers as Telegram messages containing title, city, price and a "View ad" deep link whose target 404s. The user is told their listing is hidden while third parties are still being told about it — and the alert is a much more durable channel than a web page, since it survives in the subscriber's chat history after the ad is corrected. |
| **Root Cause** | `ListingsQuery` is documented as "the single source of truth" for the public visibility predicate, but the alert path lives in a different app's service and was written against the raw `Ad` manager. There is no querysets-level equivalent of `get_account_state()` to reuse — that helper is instance-level and takes a `User` — so writing the account-state filter inside `apps/search` would have produced a second, drift-prone copy. That is the ownership decision the phase brief calls out, and it was evidently resolved by *not* duplicating the predicate, which leaves the alert path simply weaker. |
| **Recommendation** | Decide ownership once, in one place, and have both paths call it. Concretely: (a) promote the public-visibility predicate out of `build_queryset` into a reusable querysets-level helper in the app that owns ad visibility (e.g. `AdQuerySets.public_visible()` or a module-level `apply_visibility(queryset)` in `apps/ads/services/listings_query.py`) that encodes `status=PUBLISHED`, `user__is_declined=False`, `user__is_banned=False` (see SRCH-008) and the null-safe active-category filter; (b) have `ListingsQuery.build_queryset` and `find_matching_ads` both start from it. That gives genuine reuse instead of a fourth copy, and it makes the predicate unit-testable in one place. If the predicate is not ready to be shared immediately, the minimum safe change is to add `user__is_declined=False` and the active-category filter to `find_matching_ads` with a comment naming `ListingsQuery` as the reference — but treat that as a stopgap, not the fix. |
| **Effort** | M |
| **Priority** | P0 |

| Field | Value |
|---|---|
| **Reproduction Steps** | 1. Create a PUBLISHED ad for a seller. 2. Create an active `SavedSearch` with `query` matching the ad title, `language="ru"`. 3. Set `seller.is_declined = True` and save. 4. Call `find_matching_ads(saved_search)` → the ad is returned. 5. `GET /search/?q=<same term>&lang=ru` → the ad is absent. |
| **Related Findings** | PII-104 (its recommendation already asked that hidden ads not be fanned out), SRCH-008 |

**Evidence — `src/backend/apps/search/services/alert_query.py:43-45`** *(supports: "the alert path filters on status only")*:
```python
    queryset: QuerySet[Ad] = Ad.objects.filter(
        status=AdStatus.PUBLISHED
    ).select_related("category", "city")
    # no user__is_declined, no user__is_banned, no category__is_active
```

**Evidence — `src/backend/apps/ads/services/listings_query.py:134-139`** *(supports: "the web path applies three visibility terms the alert path omits")*:
```python
        ads = (
            Ad.objects.filter(status=AdStatus.PUBLISHED, user__is_declined=False)
            .filter(Q(category__isnull=True) | Q(category__is_active=True))
            .select_related("category", "city", "user")
            .prefetch_related("features", "user__trust_score", "images")
        )
```

**Evidence — `probe_srh.py::test_alert_path_ignores_declined` / `::test_alert_path_ignores_inactive_category`** *(supports: "the two paths disagree on the same data, in the same probe run")*:
```text
[R3] {"alert_matched_declined_ad": true,     "web_contains_declined_ad": false}
[R4] {"alert_matched_inactive_cat_ad": true, "web_contains_inactive_cat_ad": false}
```

#### SRCH-005: [HIGH] — `give_consent()` does not bump the search content version, so a seller who re-accepts consent stays invisible in search for up to 360 s

| Field | Value |
|---|---|
| **ID** | SRCH-005 |
| **Title** | `give_consent()` does not bump the search content version, so a seller who re-accepts consent stays invisible in search for up to 360 s |
| **Severity** | HIGH |
| **Category** | Correctness |
| **File(s)** | `src/backend/apps/users/services/deletion.py:272-289`, `src/backend/apps/users/services/deletion.py:63`, `src/backend/apps/search/services/cache.py:44-46,84-96` |
| **Status** | Open |
| **Problem** | Search results are cached as an ordered **ID list** under a key that embeds a content version; the version is bumped on any `Ad` post_save and on a feature M2M change. Account-state changes can move ads in and out of the result set *without touching any `Ad` row*, so they need an explicit bump. `decline_consent()` does exactly that (`transaction.on_commit(bump_search_cache_version)`, with a comment explaining that cached results would otherwise keep serving the newly hidden ads). `give_consent()` — the mirror operation, which clears `is_declined` and therefore *restores* the ads to the predicate — performs no bump at all. The result is asymmetric: hiding is instant, restoring is not. |
| **Impact** | Reproduced: after `give_consent(seller)` clears `is_declined`, the seller's PUBLISHED ad is still **not returned by `/search/`**, and the content version is unchanged. Because a stale entry is served for `SEARCH_CACHE_TTL + SEARCH_CACHE_STALE_TTL` = 300 s + 60 s, a seller who re-accepts consent after a decline can spend up to six minutes believing their listings are still hidden, and any buyer searching for their item during that window sees nothing. For a marketplace whose DECLINE path deliberately hides listings, this is a self-inflicted availability incident on the seller's own inventory. The existing test `test_give_consent_restores_declined_ads_to_queryset` documents the gap but asserts only at the `ListingsQuery` queryset level, so the view-level staleness is untested. |
| **Root Cause** | The invalidation contract is "every mutation that can change a buyer-visible result set must bump the version", and it is enforced by convention (a `post_save` receiver on `Ad` plus hand-written `on_commit` hooks) rather than by anything structural. The one hook that was added was added for the privacy direction, and the symmetric restore path was overlooked. |
| **Recommendation** | Add `transaction.on_commit(bump_search_cache_version)` to `give_consent()` immediately after the `save()`, mirroring `decline_consent()` and with a matching comment. Because `give_consent` is a pure read-side restoration, a stale cache is never a privacy problem here — only a correctness/liveness one — so an unconditional bump is safe and cheap. Extend the existing view-level test so it asserts the *cached view* result, not just the queryset, otherwise this regression can silently return. Longer term, the durable fix is to have the account-state mutations emit the invalidation through a single `post_save` receiver on `User` (any change to `is_declined` / `is_banned` / `consent_revoked_at` / `is_deleted`) instead of relying on each service remembering to call it — that also closes the bulk-`QuerySet.update()` hole permanently. |
| **Effort** | S |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **Reproduction Steps** | 1. Create a PUBLISHED ad; `GET /search/?q=<term>&lang=ru` to warm the cache. 2. Set `seller.is_declined = True`, save, then call `bump_search_cache_version()` to make the hide visible. 3. `GET /search/` again → ad absent. 4. Call `give_consent(seller)`. 5. `GET /search/?q=<term>&lang=ru` again → ad still absent, and `get_search_version()` is unchanged. |
| **Related Findings** | SRCH-007 (same invalidation mechanism, second defect), SRCH-008 |

**Evidence — `src/backend/apps/users/services/deletion.py:63` vs `:272-289`** *(supports: "the hide path bumps the version, the restore path does not")*:
```python
def decline_consent(user: User) -> None:
    ...
    # No Ad.save() fires here (ads are not mutated), so the post_save signal
    # would not bump the search cache. Invalidate explicitly ...
    transaction.on_commit(bump_search_cache_version)          # :63  ← present

def give_consent(user: User) -> None:
    user.consent_given_at = timezone.now()
    user.is_declined = False                                   # :274  ads become visible again
    user.ads_auto_publish = True
    user.consent_revoked_at = None
    user.save(update_fields=[...])                             # :280  ← NO bump_search_cache_version
```

**Evidence — `src/backend/apps/search/services/cache.py:44-46`** *(supports: "how long the stale result set can be served")*:
```python
SEARCH_CACHE_TTL: Final[int] = 300
SEARCH_CACHE_STALE_TTL: Final[int] = 60
SEARCH_CACHE_LOCK_TTL: Final[int] = 30
```

**Evidence — `probe_srh.py::test_cache_stale_after_consent_restore`** *(supports: "the ad stays invisible after consent is restored, with the version unchanged")*:
```text
[R15] {"first_hit": true, "hidden_after_decline": true,
       "is_declined_cleared": true,
       "visible_after_give_consent": false,     ← the defect
       "search_version": 2}
```

---

#### SRCH-006: [HIGH] — A NUL byte in `q` raises an unhandled `psycopg.DataError` → HTTP 500 on `/search/` and `/api/search/autocomplete`

| Field | Value |
|---|---|
| **ID** | SRCH-006 |
| **Title** | A NUL byte in `q` raises an unhandled `psycopg.DataError` → HTTP 500 on `/search/` and `/api/search/autocomplete` |
| **Severity** | HIGH |
| **Category** | Availability / Input validation |
| **File(s)** | `src/backend/apps/search/views/search.py:67`, `src/backend/apps/search/services/popular_search.py:44-52`, `src/backend/apps/search/services/search_history.py:79-83`, `src/backend/apps/core/utils/sanitize.py:127-131` |
| **Status** | Open |
| **Problem** | The search view bounds the query with `MAX_SEARCH_QUERY_LENGTH` (200) but never strips or rejects control characters, and the bounded string is then written to a `CharField` (`popular_searches.query`, `search_history.query`) on **every** search. PostgreSQL text columns cannot contain `0x00`, so psycopg raises `DataError` before the statement is sent. Neither `increment_popular_search()` nor `record_search_history()` catches it, and the view has no try/except, so it propagates as a 500. The autocomplete endpoint is affected too: `sanitize_autocomplete_query` strips only `;'"\` and lets `\x00` through. |
| **Impact** | Reproduced on both public endpoints: `GET /search/?q=велосипед%00abc` and `GET /api/search/autocomplete?q=ab%00cd` both raise `psycopg.DataError: PostgreSQL text fields cannot contain NUL (0x00) bytes` and return HTTP 500 instead of a result page. A one-character payload from an anonymous visitor takes down the two most important public endpoints. Because the failure happens in the write path that runs on *every* search (the analytics/popularity/history writes are deliberately cache-independent), there is no code path that avoids it — the only requirement is a `%00` in the query string. |
| **Root Cause** | `MAX_SEARCH_QUERY_LENGTH` was added to stop a `DataError` from an over-long query hitting `CharField(max_length=200)` — the comment at `search.py:40-42` says exactly that. The same class of `DataError` is reachable through a *content* constraint rather than a *length* one, and only the length constraint was addressed. The project already owns the right control for this (`_CONTROL_CHAR_PATTERN` in `sanitize.py`), but it is applied only on the logging path. |
| **Recommendation** | Sanitize at the single input edge, once, so every consumer benefits: extend `search.py:67` to strip control characters (reuse `_CONTROL_CHAR_PATTERN` via a small public helper in `apps.core.utils.sanitize`, e.g. `strip_control_chars()`) before applying the length bound, and do the same inside `sanitize_autocomplete_query` so the JSON endpoint is covered by the same rule. Belt-and-braces: wrap the two write calls in `_record_search_analytics` so a data-quality failure in an analytics side-effect can never take the results page down — analytics should never be able to fail a search. Add a regression test for `%00` on both endpoints, alongside the existing over-length and injection tests in `test_search_view.py::TestSearchViewInputRobustness`. |
| **Effort** | S |
| **Priority** | P0 |

| Field | Value |
|---|---|
| **Reproduction Steps** | 1. Warm `/search/`. 2. `GET /search/?q=%D0%B2%D0%B5%D0%BB%D0%BE%D1%81%D0%B8%D0%BF%D0%B5%D0%B4%00abc&lang=ru` → HTTP 500. 3. `GET /api/search/autocomplete?q=ab%00cd` → HTTP 500. |
| **Related Findings** | SRCH-002 (same input value is also logged unredacted) |

**Evidence — `src/backend/apps/search/views/search.py:40-43,67`** *(supports: "only length is bounded; control characters pass through to a text column")*:
```python
# Maximum accepted length of a search query string. Truncating at the input edge
# prevents a DataError when the value is persisted into CharField(max_length=200)
# via increment_popular_search / record_search_history (SRH-001).
MAX_SEARCH_QUERY_LENGTH: Final[int] = 200
...
    query = (request.GET.get("q") or "").strip()[:MAX_SEARCH_QUERY_LENGTH]   # :67 — no char filter
```

**Evidence — `src/backend/apps/core/utils/sanitize.py:127-131`** *(supports: "the autocomplete sanitiser removes quotes and backslash but not NUL")*:
```python
def sanitize_autocomplete_query(query: str) -> str:
    if not query or len(query) < 2 or len(query) > 100:
        return ""
    return re.sub(r"[;'\"\\]", "", query.strip())   # no \x00
```

**Evidence — `probe_srh.py::test_nul_byte_query_500`** *(supports: "both public endpoints return an unhandled DataError for a NUL byte")*:
```text
[R5b] {"nul":            "EXC DataError: PostgreSQL text fields cannot contain NUL (0x00) bytes",
       "bell":           200,
       "nul_alone":      "EXC DataError: PostgreSQL text fields cannot contain NUL (0x00) bytes",
       "autocomplete_nul":"EXC DataError: PostgreSQL text fields cannot contain NUL (0x00) bytes"}
```

---

#### SRCH-007: [HIGH] — The search content-version counter inherits the 300 s default cache TTL, so it expires and the next bump re-issues an already-used version, resurrecting a stale result set

| Field | Value |
|---|---|
| **ID** | SRCH-007 |
| **Title** | The search content-version counter inherits the 300 s default cache TTL, so it expires and the next bump re-issues an already-used version, resurrecting a stale result set |
| **Severity** | HIGH |
| **Category** | Correctness / Caching |
| **File(s)** | `src/backend/apps/search/services/cache.py:84-96`, `src/backend/apps/search/services/cache.py:68-73`, `src/backend/apps/search/services/cache.py:124-141`, `src/backend/config/settings/base.py` (`CACHES`) |
| **Status** | Open |
| **Problem** | The invalidation mechanism is a monotonically increasing counter stored in the cache and embedded in every search key. `bump_search_version()` calls `cache.incr(SEARCH_CONTENT_VERSION_KEY)` and, on the very first call, `cache.set(SEARCH_CONTENT_VERSION_KEY, 1)` — **with no `timeout` argument**, so the key inherits Django's `DEFAULT_TIMEOUT` of 300 s. `incr` does not extend a TTL, and nothing ever re-seeds the key on a schedule. When the key expires, `get_search_version()` falls back to `0`, and the next bump takes the `ValueError` branch and `set`s it back to `1` — a version number that was already in use. Every cache entry is written with a backend TTL of `SEARCH_CACHE_TTL + SEARCH_CACHE_STALE_TTL` = 360 s, which is *longer* than the counter's 300 s lifetime, so a version-1 entry written just before expiry is still alive when version 1 is re-issued. |
| **Impact** | Verified: after the counter key is removed (which is what expiry does), the next bump produces a key **identical** to one already in use, and the previously cached ID list is served again (`key_reused: true`, `cache_hit_cycle2: [2]`). The counter is therefore not monotonic, and the entire "version bump makes stale entries unreachable without a prefix wipe" property in the module docstring holds only for the first cycle. In production this means a window of roughly 60 s in every 300 s during which a search result set computed *before* a publish, edit, archive or status change can be handed back to buyers. The live `user__is_declined` re-filter limits the blast radius (see R-21), but a resurrected list can still expose an ad that was archived, deleted, or re-categorised, and it can show a stale `total_count` and stale relevance order. |
| **Root Cause** | The counter was written as if the cache were durable storage. The same pattern (`cache.incr` + `cache.set` with no timeout, described in the code as "mirrors the `bump_tree_version` pattern from `apps.categories.cache`") exists in the categories app, so this is a copied idiom rather than a one-off slip — the fix should probably be applied to both, but the search one is in scope here. |
| **Recommendation** | Make the counter a non-expiring key: pass `timeout=None` to both the `cache.set` in the `ValueError` branch and, defensively, re-seed with `timeout=None` whenever it is read as `0` while entries may still be in flight. In Django, `timeout=None` means "cache forever", which is the correct semantic for a monotonic counter. Add a regression test that (a) writes an entry at version *N*, (b) simulates expiry, (c) bumps, and (d) asserts the resulting key differs from the one at step (a) and that the stale entry is not served. Longer term, consider deriving the version from something that is already durable (a `SearchCacheVersion` row, or a monotonic timestamp) rather than from a TTL-bearing cache key. |
| **Effort** | S |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **Reproduction Steps** | 1. `GET /search/?q=велосипед&lang=ru` to populate the cache and note `get_search_version()`. 2. `cache.delete(SEARCH_CONTENT_VERSION_KEY)` (this is exactly the state the 300 s expiry produces). 3. Call `bump_search_version()`. 4. `build_search_cache_key(...)` now returns a key that is byte-identical to the one from step 1, and `get_cached_search_ids` returns the old list. |
| **Related Findings** | SRCH-005 (same invalidation mechanism, missing bump) |

**Evidence — `src/backend/apps/search/services/cache.py:84-96`** *(supports: "the counter is written with the default 300 s TTL, so it expires")*:
```python
def bump_search_version() -> None:
    try:
        cache.incr(SEARCH_CONTENT_VERSION_KEY)
    except ValueError:
        cache.set(SEARCH_CONTENT_VERSION_KEY, 1)     # ← no timeout → DEFAULT_TIMEOUT (300 s)
        logger.debug("Initialized search content version to 1")
```

**Evidence — `src/backend/config/settings/base.py` (`CACHES`)** *(supports: "there is no TIMEOUT override, so the 300 s Django default applies in production Redis as well")*:
```python
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
    }
}   # no "TIMEOUT" key → Django DEFAULT_TIMEOUT = 300 s
```

**Evidence — `src/backend/apps/search/services/cache.py:177-205` (`swr_cache._store`)** *(supports: "entries outlive the counter: 360 s backend TTL vs 300 s counter lifetime")*:
```python
SEARCH_CACHE_TTL = 300        # fresh window
SEARCH_CACHE_STALE_TTL = 60   # stale window
...
    entry = _CacheEntry(value, time.time()).as_dict()
    cache.set(key, entry, timeout=ttl + stale_ttl)   # 360 s > 300 s counter TTL
```

**Evidence — `probe2.py::test_version_reissued`** *(supports: "the version is re-issued and a previously cached result set is served again")*:
```text
[P1c] {"v_before_expiry": "1", "v_after_expiry": 0, "v_after_next_bump": "1",
       "key_reused": true,
       "cache_hit_cycle1": [2],
       "cache_hit_cycle2": [2]}      ← the SAME stale id list, from the previous cycle
```

### MEDIUM

#### SRCH-008: [MEDIUM] — Banned sellers' ads stay publicly searchable, listed and directly reachable — the visibility predicate has no `is_banned` term

| Field | Value |
|---|---|
| **ID** | SRCH-008 |
| **Title** | Banned sellers' ads stay publicly searchable, listed and directly reachable — the visibility predicate has no `is_banned` term |
| **Severity** | MEDIUM |
| **Category** | Visibility gating / Authorization |
| **File(s)** | `src/backend/apps/ads/services/listings_query.py:135`, `src/backend/apps/ads/views/listings.py:65,203`, `src/backend/apps/users/services/account_state.py:26-48`, `src/backend/apps/moderation/admin_actions.py:78-111` |
| **Status** | Open |
| **Problem** | The public visibility predicate is `status=PUBLISHED AND user__is_declined=False` plus a null-safe active-category filter. It has **no `is_banned` term**, and neither does the `ad_detail` queryset nor the `media_gate` non-staff filter. `AccountState` treats `is_banned` as a first-class restriction (`can_publish_ad` and `can_login` both refuse a banned user, and `core/services/contact.py` refuses to route a contact deep link to one), but no read path for public inventory consults it. `ban_user_for_ad()` — the moderator action that bans a user *because of the ad they posted* — flips the flag and leaves every one of that seller's other ads `PUBLISHED`. |
| **Impact** | Verified: after `seller.is_banned = True`, the seller's PUBLISHED ad is still returned by `GET /search/?q=…` (`search_contains_banned_ad: true`), still listed on `GET /search/` and `GET /` (`listings_contains_banned_ad: true`), and its detail page still renders 200. A moderator who bans a spammer or a scammer has to find and hide every ad individually; the bulk-ban path (`User.objects.filter(id__in=…).update(is_banned=True)`) additionally bypasses the `post_save` receiver, so even a future version-based cache invalidation would miss it. Rated MEDIUM rather than HIGH because the shipped spec never states that a ban hides inventory, and "ban blocks the account, ads are handled by separate moderation actions" is a defensible product reading — the defect is that the code, the account-state service and the moderation UI all disagree and nothing records which reading is intended. |
| **Root Cause** | Account state is enforced at the *interaction* boundary (the bot middleware, the login/consent views, the contact gate) and at the *write* boundary (`can_publish_ad`), but there is no querysets-level account-state predicate, so every read path has to re-decide which flags matter. Each read path has made that decision independently, and three of them chose differently. |
| **Recommendation** | Decide the product answer and write it down, then encode it once. The recommended answer is that a ban hides inventory — a banned seller is a moderation action, and leaving their ads live while their contact button is disabled is incoherent. Encode it as part of the shared predicate proposed in SRCH-004 (`user__is_banned=False`), which makes `search`, `listings`, `ad_detail`, `media_gate` and the alert path change together instead of one at a time. Independently, route the bulk-ban admin action through a `User` `post_save`/bulk-update hook that invalidates the search content version, so a future ban filter is not defeated by a stale cache. Whichever semantic is chosen, add it to `docs/02-database/db-schema.md:63`, which today documents only `is_declined`. |
| **Effort** | S (filter) / M (with the shared predicate) |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **Reproduction Steps** | 1. Create a PUBLISHED ad. 2. `GET /search/?q=<term>&lang=ru` → found. 3. Set `seller.is_banned = True; seller.save(update_fields=["is_banned"])`. 4. Repeat step 2 and `GET /<ad_id>/` → still found, 200. |
| **Related Findings** | SRCH-004 (shared predicate), PII-104 |

**Evidence — `src/backend/apps/ads/services/listings_query.py:134-136`** *(supports: "the predicate has a declined term but no banned term")*:
```python
        ads = (
            Ad.objects.filter(status=AdStatus.PUBLISHED, user__is_declined=False)
            # no user__is_banned=False, although AccountState treats a ban as a restriction
```

**Evidence — `src/backend/apps/users/services/account_state.py:66-80,98-106`** *(supports: "the account-state service refuses a banned user everywhere else")*:
```python
    if state.is_banned:
        logger.info("User %s cannot publish: banned", user.id)
        return False
...
    if state.is_banned:
        logger.info("User %s cannot login: banned", user.id)
        return False
```

**Evidence — `src/backend/apps/moderation/admin_actions.py:98-106`** *(supports: "the ban action flips the flag and touches no ads")*:
```python
        if not user.is_banned:
            user.is_banned = True
            user.save(update_fields=["is_banned"])
            log_ban_account(user_id=user.id, moderator_id=moderator_id, reason=reason)
```

**Evidence — `probe_srh.py::test_banned_seller_visible`** *(supports: "a banned seller's ad is still returned by search, by browse and by its detail page")*:
```text
[R2] {"search_status": 200, "search_contains_banned_ad": true,
      "detail_url": "/54/", "detail_status": 200,
      "listings_contains_banned_ad": true}
```

---

#### SRCH-009: [MEDIUM] — A single-word query that fuzzy-matches a category name is silently restricted to that category's subtree, hiding textually identical ads in other branches

| Field | Value |
|---|---|
| **ID** | SRCH-009 |
| **Title** | A single-word query that fuzzy-matches a category name is silently restricted to that category's subtree, hiding textually identical ads in other branches |
| **Severity** | MEDIUM |
| **Category** | Relevance / Correctness |
| **File(s)** | `src/backend/apps/search/views/search.py:248-255`, `src/backend/apps/search/views/search.py:365-413` |
| **Status** | Open |
| **Problem** | For a single-word query, `_apply_fts_filtering` calls `_fuzzy_category_match()`, and if that returns a category it **narrows** the queryset with `category_id__in=<that category's subtree>` *in addition to* the FTS predicate. `_fuzzy_match_by_name` runs `difflib.get_close_matches(query, all_category_names, n=1, cutoff=0.8)` — a similarity guess with no requirement that the word actually be a category name. The narrowing is applied globally (the whole site), and it is **silently** applied: the view reports the filtered count as `total_count` with no indication that a category interpretation was chosen, and the template has no way to show it. |
| **Impact** | Verified with two ads carrying the *identical* title `Велосипед Stels`, one in a `Велосипеды` category and one in `Электроника`: the single-word query `велосипед` returns only the first (`bikes_branch: true`, `electronics_branch: false`). A buyer typing one word gets a silently category-scoped result set and never learns that a matching ad in another branch was suppressed. In a real catalogue this is the common case: `велосипед` (bike) is close to `Велосипеды`, but the same word also appears in `Велосипедный тренажёр`, spare parts and forum posts; every one of those becomes invisible. It also makes the two-word query and the one-word query return different result sets for the same intent, which is the kind of inconsistency users report as "search is broken". |
| **Root Cause** | The fuzzy match is treated as a *hint*, but it is applied as a *hard filter* and never surfaced. The cutoff of 0.8 on a `SequenceMatcher` ratio is permissive enough that many ordinary nouns land inside it, and `n=1` guarantees a match whenever any category name is at all similar. The spec calls for "app-level fuzzy detect … applies an explicit `category_id` filter when the query is a single word similar to a category name" (`technical-specification.md:66`), so the code matches the letter of the spec; the defect is that the spec does not say the filter must be *visible* or *reversible*. |
| **Recommendation** | Three small changes, in order of value. (1) Surface the interpretation: when a fuzzy category match fires, pass it into the template context as `matched_category` and render it as an active, removable filter chip (the context already carries `breadcrumb_category`, `current_category` and `suggested_category`, so the plumbing exists). (2) Make the explicit choice win: if the request already carries `?category=`, skip the fuzzy detection entirely. (3) Tighten the trigger: require the ratio to be high (e.g. `cutoff=0.9`) **or** an exact slug/name match before narrowing — `Велосипед` vs `Велосипеды` at 0.947 would still work, while marginal guesses stop silently deleting results. Finally, add a test that asserts a single-word query matching ads in two branches returns both, so the behaviour is pinned deliberately rather than by accident. |
| **Effort** | S |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **Reproduction Steps** | 1. Create two active categories, `Велосипеды` and `Электроника`. 2. Create one PUBLISHED ad titled `Велосипед Stels` in each. 3. `GET /search/?q=велосипед&lang=ru` → only the `Велосипеды` ad is returned. 4. `GET /search/?q=велосипед+stels&lang=ru` (two words, fuzzy path skipped) → both are returned. |
| **Related Findings** | — |

**Evidence — `src/backend/apps/search/views/search.py:248-255,405-408`** *(supports: "a similarity guess becomes a hard, silent, site-wide filter")*:
```python
    # One-word queries: apply fuzzy category detection (locale-aware)
    if _is_single_word(query):
        category_filter = _fuzzy_category_match(query, locale)
        if category_filter:
            descendant_ids = category_filter.get_descendants(
                include_self=True
            ).values_list("id", flat=True)
            queryset = queryset.filter(category_id__in=descendant_ids)   # silent hard filter
...
    matches = get_close_matches(query, all_names, n=1, cutoff=0.8)       # n=1, permissive cutoff
```

**Evidence — `probe_srh.py::test_fuzzy_similar_word_hides_other_branch` / `::test_fuzzy_category_cross_branch`** *(supports: "identical titles in two branches; the one-word query returns only one")*:
```text
[R9b] {"bikes_branch": true, "electronics_branch": false}
[R9]  {"two_word_match": true, "one_word_match": true}   # control: without a nearby category name, no narrowing
```

---

#### SRCH-010: [MEDIUM] — The app-level per-IP rate limit is bypassable by spoofing `X-Forwarded-For` (third verbatim copy of the client-IP helper)

| Field | Value |
|---|---|
| **ID** | SRCH-010 |
| **Title** | The app-level per-IP rate limit is bypassable by spoofing `X-Forwarded-For` (third verbatim copy of the client-IP helper) |
| **Severity** | MEDIUM |
| **Category** | Security hardening (CWE-290: Authentication Bypass by Spoofing) / Duplication |
| **File(s)** | `src/backend/apps/search/services/rate_limit.py:69-85`, `src/backend/apps/search/services/rate_limit.py:49-50`, `src/backend/apps/users/services/login_rate_limit.py:64-80`, `src/backend/apps/core/services/contact_rate_limit.py:24-30`, `docker/nginx/nginx.conf:116,126,176` |
| **Status** | Open |
| **Problem** | `rate_limit_check()` keys its counter on `_get_client_ip(request)`, which trusts `HTTP_X_FORWARDED_FOR` and returns **element 0** of the comma-separated list. nginx sets the header with `$proxy_add_x_forwarded_for`, which *appends* `$remote_addr` to whatever the client already sent — so the header arriving at Django is `<client-supplied>, <real client IP>` and element 0 is attacker-controlled. A caller who sends `X-Forwarded-For: 10.0.0.7` on every request gets a fresh bucket each time. This is the **third** byte-identical copy of the helper (the others are in `login_rate_limit.py` and `contact_rate_limit.py`), so a fix has to be applied in three places or, better, once. |
| **Impact** | Verified: 60 requests with a rotating `X-Forwarded-For` produced **zero** 429s, while 40 requests from a fixed address produced 10 (the limiter correctly engages at 30/60 s). Severity is MEDIUM rather than HIGH because the authoritative control is not this one: nginx applies `limit_req zone=search_limit rate=20r/s burst=40` and `limit_req zone=browse_limit …` on `$binary_remote_addr`, which cannot be spoofed, and only nginx publishes ports (80/443) — the Django container is not directly reachable. What the bypass actually removes is the *application* layer: the 30-per-minute cap that is supposed to bound FTS work per client, so an attacker behind nginx can drive the 20 r/s + burst 40 ceiling against PostgreSQL on both `/search/` and `/api/search/autocomplete` instead of the intended 0.5 r/s. |
| **Root Cause** | The helper implements a proxy-trust policy implicitly and inconsistently: it assumes it is the *only* proxy (so "leftmost" and "the client IP" coincide) and encodes no notion of trusted-proxy count. nginx's `proxy_add_x_forwarded_for` breaks the leftmost assumption. The three copies mean the same wrong assumption is repeated in the login limiter — which is the one place where it matters most. |
| **Recommendation** | Read the **rightmost** address that the trusted proxy added, not the leftmost one the client supplied. The minimal, behaviour-preserving fix is to use `request.META["REMOTE_ADDR"]` when the deployment always places the app behind exactly one trusted proxy (nginx sets `REMOTE_ADDR` to the real peer for proxied requests), or to take the last element of `X-Forwarded-For` and document the single-proxy assumption explicitly. Better: delete the three copies, put one `get_client_ip(request)` in a shared module, and unit-test it against `X-Forwarded-For: 1.1.1.1, 2.2.2.2` (must return `2.2.2.2`), a bare `X-Forwarded-For`, and a request with neither header. Note for phase 10: the duplication itself is a code-quality finding, and consolidating it here removes both at once. |
| **Effort** | S |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **Reproduction Steps** | 1. `GET /search/?q=велосипед&lang=ru` 60 times, varying `X-Forwarded-For` (e.g. `10.0.0.1` … `10.0.0.60`). 2. Observe 60 × HTTP 200. 3. Repeat 40 times with a constant `X-Forwarded-For` (or a constant `REMOTE_ADDR` and no header). 4. Observe HTTP 429 from request 31 onward. |
| **Related Findings** | SRCH-013 (same subsystem, inconsistent policy) |

**Evidence — `src/backend/apps/search/services/rate_limit.py:82-85`** *(supports: "the leftmost, client-supplied address is used as the bucket key")*:
```python
    x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded:
        return x_forwarded.split(",")[0].strip()   # ← element 0 is client-controlled behind nginx
    return request.META.get("REMOTE_ADDR", "unknown")
```

**Evidence — `docker/nginx/nginx.conf:126,176`** *(supports: "nginx appends the real peer to the client-supplied header, so element 0 is not the real client")*:
```nginx
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;   # <client-supplied>, $remote_addr
```

**Evidence — `probe_srh.py::test_ratelimit_xff_spoof`** *(supports: "rotating the header defeats the limiter; a fixed address does not")*:
```text
[R14] {"xff_rotating_429s": 0, "xff_total": 60,
       "fixed_ip_429s": 10, "fixed_ip_total": 40}
```

---

#### SRCH-011: [MEDIUM] — `SavedSearch.query` is an unbounded `TextField` fed straight from the POST body and later fed to `SearchQuery` on the alert path

| Field | Value |
|---|---|
| **ID** | SRCH-011 |
| **Title** | `SavedSearch.query` is an unbounded `TextField` fed straight from the POST body and later fed to `SearchQuery` on the alert path |
| **Severity** | MEDIUM |
| **Category** | Input validation / Availability |
| **File(s)** | `src/backend/apps/search/views/save_search.py:37,48-57`, `src/backend/apps/search/models.py:73-80`, `src/backend/apps/search/services/alert_query.py:56-60,220-224` |
| **Status** | Open |
| **Problem** | `save_search()` takes `request.POST["query"]`, strips it, and writes it to `SavedSearch.query` — a `TextField` with **no length bound and no Pydantic DTO**, unlike every other input on the search surface. The stored string is later handed verbatim to `SearchQuery(..., search_type="websearch", config=...)` on both the daily digest path and the near-real-time publish path, where it becomes the lexeme set of an FTS query run against every saved search. Note the contrast with `/search/`, where the same value *is* bounded (200) and stripped of nothing. |
| **Impact** | Verified: a single authenticated POST stores 50 000 characters verbatim (`submitted_chars: 50000, stored_chars: 50000`). The immediate cost is unbounded row growth in a table that has no retention sweep, and a pathological FTS query the scheduler will re-evaluate on every cycle for as long as the saved search stays active — `websearch_to_tsquery` on a 50 000-character input is orders of magnitude more expensive than the ad-table side of the same query, and it runs outside the `/search/` rate limiter entirely. Rated MEDIUM because it requires an authenticated seller (unlike SRCH-001/006) and the alert path already caps work per saved search at 10 results; it is nonetheless an unbounded-input path in a subsystem the public search depends on. |
| **Root Cause** | The save-search view predates the Pydantic input-DTO pattern that `ListingsQueryParams` established, and nobody revisited it. The `MAX_SEARCH_QUERY_LENGTH` constant already exists in the same app (`search.py:43`) and simply is not imported here — the same class of omission as SRCH-006, on a different endpoint. |
| **Recommendation** | Reuse the existing bound rather than inventing a second one: cap `query` at `MAX_SEARCH_QUERY_LENGTH` in `save_search()` (import it from `apps.search.views.search`, or — better — move it to a shared `apps/search/constants`-style module so the view and the model agree), and ideally accept a small Pydantic DTO so the coercion lives in one place like it does for listings. Add a test posting an oversized `query` and asserting the stored length. Separately, decide whether `SavedSearch.query` should be `max_length=200` to match `PopularSearch.query_normalized` — if the two are meant to hold the same thing, they should not have different limits. |
| **Effort** | S |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **Reproduction Steps** | 1. Authenticate as any seller. 2. `POST /search/save/` with `query` = 50 000 characters (plus a CSRF token). 3. `SELECT length(query) FROM saved_searches` → 50 000. 4. `GET /search/save/` is unaffected, but the daily `send_alerts` command will build an FTS query from that string for every cycle while the search is active. |
| **Related Findings** | SRCH-006 (same missing-bound class on the anonymous path) |

**Evidence — `src/backend/apps/search/views/save_search.py:37,48-57`** *(supports: "the POST body value is stored with no length check and no DTO")*:
```python
    query = (request.POST.get("query") or "").strip()      # :37  no length cap
    ...
    saved_search = SavedSearch.objects.create(
        user=request.user,
        query=query or None,                              # :50  TextField, unbounded
        ...
    )
```

**Evidence — `src/backend/apps/search/models.py:73-80`** *(supports: "the column has no `max_length`, unlike `PopularSearch.query_normalized`")*:
```python
    query = models.TextField(          # ← no max_length; PopularSearch.query_normalized is max_length=200
        blank=True, null=True,
        help_text=("FTS query string stored in the user's language; matched against "
                   "the per-language search vector (no query-time translation)"),
    )
```

**Evidence — `probe2.py::test_saved_search_query_unbounded`** *(supports: "50 000 characters are accepted and stored verbatim")*:
```text
[P2] {"submitted_chars": 50000, "stored_chars": 50000}
```

---

#### SRCH-012: [MEDIUM] — This phase's own rubric requires DECLINE **not** to hide PUBLISHED ads; the shipped spec and code do the opposite — the rubric is the outlier

| Field | Value |
|---|---|
| **ID** | SRCH-012 |
| **Title** | This phase's own rubric requires DECLINE **not** to hide PUBLISHED ads; the shipped spec and code do the opposite — the rubric is the outlier |
| **Severity** | MEDIUM |
| **Category** | Documentation / Spec conflict |
| **File(s)** | `.kilo/commands/audit/phases/08-audit-search-fts.md:24,40,53,118`, `docs/01-spec/technical-specification.md:85,96,101`, `docs/02-database/db-schema.md:63`, `src/backend/apps/ads/services/listings_query.py:135` |
| **Status** | Open |
| **Problem** | This phase's rubric states in four separate places that a DECLINEd seller's PUBLISHED ads **must remain searchable** ("DECLINE must NOT hide a seller's PUBLISHED ads from search", §5a; "search must not filter on consent state directly", §4.1; listed as a HIGH-severity failure, §8). The shipped system does the exact opposite, and three independent project documents agree with the code: `technical-specification.md:85,96,101` ("DECLINE … also hides the user's PUBLISHED ads from public search/listings"), `db-schema.md:63` ("PUBLISHED ads excluded from public search/listings and direct URL access"), and `technical-specification.md:96` naming the precise live filter (`user__is_declined=False` in `ListingsQuery`). The implementation is deliberate, documented, covered by `test_search_view.py::TestSearchViewDeclinedConsent`, and the invalidation is even handled (`decline_consent` bumps the cache version via `on_commit`). The stale artefact is the audit rubric, which predates or ignores the decision. |
| **Impact** | No runtime impact today — the shipped behaviour is consistent and intentional. The cost is audit and governance: three future phases (05 ad lifecycle, 06 consent, 14 authorization) each inherit a rubric clause asserting the opposite of the product, so each will re-derive the same conflict from scratch, and a validator comparing code against the rubric will see a false HIGH. The decision itself also has a real open question attached — phase 06 already recorded that there is no discoverable, session-independent way for a DECLINEd user to reverse the hide (PII-105) — which is an availability problem worth an owner decision, but is not this finding. |
| **Root Cause** | The rubric was written from an architecture-level description ("DECLINE = browse-only ⇒ ad status unchanged ⇒ ads stay visible") and never reconciled against the later product decision that a declined consent also withdraws the basis for publishing. The decision *is* recorded in the spec; only the audit rubric is stale. |
| **Recommendation** | Documentation-only; do not change code. Update `.kilo/commands/audit/phases/08-audit-search-fts.md` §2 (Visibility Filter), §4.1, §5(a) and §8 to state the shipped semantics — DECLINE sets `is_declined`, which the single public-visibility predicate excludes, and the search cache version is bumped so the change is immediate; WITHDRAW is what changes ad status to `DELETED`. Then align the cross-references in the phase-05 and phase-06 rubrics, and close the loop with the authoritative version already filed as **PII-113** (spec-index vs technical-specification) so there is exactly one place that carries the decision. |
| **Effort** | S |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **Reproduction Steps** | *(documentation finding — no runnable steps. Evidence: read the two documents side by side; the runtime behaviour was separately verified as the shipped semantics.)* |
| **Related Findings** | PII-105, PII-113 (authoritative), SRCH-005 (the consent-restore cache gap) |

**Evidence — `.kilo/commands/audit/phases/08-audit-search-fts.md:24,53`** *(supports: "the rubric asserts the opposite of the shipped behaviour, in its own Visibility Filter and gating checks")*:
```text
| **Visibility Filter** | PUBLISHED only; DECLINE (browse-only) does not alter ad status so a
  seller's PUBLISHED ads remain searchable; ...
### (a) Visibility gating — CRITICAL
Only PUBLISHED ads returned. ... DECLINE must NOT hide a seller's PUBLISHED ads.
```

**Evidence — `docs/01-spec/technical-specification.md:101` / `docs/02-database/db-schema.md:63`** *(supports: "the shipped spec and the code agree with each other and disagree with the rubric")*:
```text
technical-specification.md:101
- **DECLINE = browse-only:** blocks seller login/actions AND hides the user's PUBLISHED ads
  from public search/listings, direct URL access (`ad_detail`), and the `media_gate` non-staff
  filter (live `user__is_declined=False` filter in `ListingsQuery` + ...).

db-schema.md:63
is_declined (BOOL, default False)  # user declined consent (browse-only); PUBLISHED ads excluded
                                   # from public search/listings and direct URL access —
                                   # `user__is_declined=False` in ListingsQuery, ...
```

**Evidence — `src/backend/apps/ads/services/listings_query.py:135`** *(supports: "the code implements the spec, and the shipped test suite pins the behaviour")*:
```python
            Ad.objects.filter(status=AdStatus.PUBLISHED, user__is_declined=False)
```

### LOW

#### SRCH-013: [LOW] — `/search/` and `/` use two unrelated rate limiters (30/min vs 60/10 min) with no documented rationale

| Field | Value |
|---|---|
| **ID** | SRCH-013 |
| **Title** | `/search/` and `/` use two unrelated rate limiters (30/min vs 60/10 min) with no documented rationale |
| **Severity** | LOW |
| **Category** | Consistency |
| **File(s)** | `src/backend/apps/search/services/rate_limit.py:18-21`, `src/backend/apps/core/services/contact_rate_limit.py:17-21`, `src/backend/apps/search/views/search.py:64-65`, `src/backend/apps/ads/views/listings.py:229-231` |
| **Status** | Open |
| **Problem** | The two adjacent public pages a buyer moves between use two independent limiters with different budgets, different key prefixes and different error shapes: `/search/` uses `apps.search.services.rate_limit` (30 requests / 60 s, key `search_rl:<ip>`, returns `JsonResponse({"error": "rate_limit"}, status=429)`), while `/` and `/<ad_id>/` use `apps.core.services.contact_rate_limit` (60 requests / 600 s, key `telegram_dl_rl:<ip>`, returns a bare `HttpResponse(status=429)`). Neither constant is documented with a rationale, and the comment in `search/services/rate_limit.py:7-8` explains the *namespace split between autocomplete and search* but not why search is on a different budget from browse. |
| **Impact** | No security consequence today — nginx is the authoritative outer limiter. The cost is operational and cognitive: a buyer who searches 30 times a minute is refused a rendered results page (and gets a JSON body from an HTML route), while the same visitor browsing normally gets 60 per 10 minutes; the two responses are not interchangeable for the frontend, which is the kind of small inconsistency that produces a class of frontend workarounds. It also means the effective search budget is effectively coupled to whatever nginx allows, so the app-level numbers read as security controls but are not (see SRCH-010). |
| **Root Cause** | Each limiter was added next to the view that needed it, in the app that owned that view, with no shared policy. The same fragmentation as SRCH-010, one layer up. |
| **Recommendation** | Either document the two budgets in `docs/01-spec/search-patterns.md` (stating that nginx is authoritative and the app-level limits are a secondary guard), or unify them behind one shared limiter with a per-endpoint budget parameter. Do not change the numbers without a decision — the cheapest correct change is a comment plus a doc line, and it removes the "is this a security control?" question for the next reader. |
| **Effort** | S |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **Reproduction Steps** | 1. `GET /search/?q=велосипед&lang=ru` 31 times → HTTP 429 with a JSON body. 2. In a fresh client, `GET /` 31 times → all HTTP 200; 61st → HTTP 429 with an empty body. |
| **Related Findings** | SRCH-010 |

**Evidence — `src/backend/apps/search/services/rate_limit.py:18-25` vs `src/backend/apps/core/services/contact_rate_limit.py:17-21`** *(supports: "two unrelated budgets, windows and key namespaces")*:
```python
# apps/search/services/rate_limit.py
RATE_LIMIT_REQUESTS: Final[int] = 30
RATE_LIMIT_PERIOD: Final[int] = 60
_RATE_LIMIT_KEY_PATTERN: Final[str] = "{namespace}_rl:{ip}"     # -> "search_rl:<ip>"

# apps/core/services/contact_rate_limit.py
RATE_LIMIT_REQUESTS: Final[int] = 60
RATE_LIMIT_PERIOD: Final[int] = 600  # 10 minutes
_RATE_LIMIT_KEY_PATTERN: Final[str] = "telegram_dl_rl:{ip}"      # -> "telegram_dl_rl:<ip>"
```

---

#### SRCH-014: [LOW] — `cache.py` claims the stale entry "is refreshed in the background"; the SWR helper recomputes **inline** on the stale-hit path

| Field | Value |
|---|---|
| **ID** | SRCH-014 |
| **Title** | `cache.py` claims the stale entry "is refreshed in the background"; the SWR helper recomputes **inline** on the stale-hit path |
| **Severity** | LOW |
| **Category** | Documentation / Maintainability |
| **File(s)** | `src/backend/apps/search/services/cache.py:9-18,147-153`, `src/backend/apps/core/utils/swr_cache.py:107-112,153-174` |
| **Status** | Open |
| **Problem** | `get_cached_search_ids` documents the stale-hit branch as "stale value is refreshed **in the background** by the single-flight winner", and the module docstring repeats "prevents cache stampedes (thundering-herd) when popular queries are requested concurrently". `get_with_stale_revalidate` does not refresh in the background: on a stale hit the winning worker calls `_recompute_and_store(key, producer, …)` **inline, before returning**, so that request pays the full FTS latency even though it has a perfectly good stale result in hand. Only the *losing* workers get the free stale serve — which is the opposite of the stated benefit for the worker that most needs it. |
| **Impact** | No correctness effect; the comment in `swr_cache.py:160-165` is accurate ("the winning worker recomputes … SYNCHRONOUSLY (blocking its own response)"), so the inaccuracy is confined to the search-side docstring. The operational impact is that a reader sizing the SLO for `/search/` will believe stale hits are free when one in every `SEARCH_CACHE_TTL` window per key is a full FTS query on the request path. Phase 13 owns the latency grading; this finding records only the documentation/behaviour mismatch so the two are not reconciled on the assumption that the doc is right. |
| **Root Cause** | The SWR helper was factored out of the search app (`apps.core.utils.swr_cache`, shared with the categories submenu cache) and its semantics documented at the call site rather than at the definition. When the behaviour was made explicit in the helper, the call-site docstring was not updated. |
| **Recommendation** | Fix the docstring (cheapest, zero risk): change "refreshed in the background by the single-flight winner" to "recomputed inline by the single-flight winner; losers serve the stale value immediately", and drop the thundering-herd claim where it implies a background refresh. If background revalidation is actually wanted, that is a behaviour change (a thread or a scheduled warmer) and should be scheduled as its own piece of work with phase 13, not smuggled into a comment fix. |
| **Effort** | S |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **Reproduction Steps** | *(documentation/behaviour mismatch — verified by reading `swr_cache.py:107-112`; no separate run required.)* |
| **Related Findings** | — |

**Evidence — `src/backend/apps/search/services/cache.py:150-152` vs `src/backend/apps/core/utils/swr_cache.py:107-112`** *(supports: "the call site promises a background refresh; the helper recomputes inline")*:
```python
# apps/search/services/cache.py:150-152  (the promise)
- **Fresh/stale cache hit**: return cached IDs (stale value is refreshed
  in the background by the single-flight winner).

# apps/core/utils/swr_cache.py:107-112  (the behaviour)
        if age < ttl + stale_ttl:
            if cache.add(lock_key, "1", lock_ttl):
                _recompute_and_store(key, producer, ttl, stale_ttl, max_size_bytes)  # inline
            return entry.value
```

---

#### SRCH-015: [LOW] — On the cache-hit path `has_results` comes from the cached ID count while `page_obj` is re-filtered by the live predicate, so the page can report N results and render none

| Field | Value |
|---|---|
| **ID** | SRCH-015 |
| **Title** | On the cache-hit path `has_results` comes from the cached ID count while `page_obj` is re-filtered by the live predicate, so the page can report N results and render none |
| **Severity** | LOW |
| **Category** | Correctness / UX |
| **File(s)** | `src/backend/apps/search/views/search.py:161-163,190-194`, `src/backend/apps/search/views/search.py:284-321` |
| **Status** | Open |
| **Problem** | On a cache hit the display count is taken from the cached list (`return len(cached_ids), False`) and `has_results = total_count > 0` is derived from it. The rendered page, however, is `Paginator(ads, …)` over a queryset re-filtered by the *live* `ListingsQuery` predicate (`ads.filter(pk__in=cached_ids)`), which is the correct and desirable defence (it is what makes SRCH-007 and the bulk-update path safe). The two values are computed from different data, so in the window where a cached list contains only now-invisible ads, the page reports a non-zero `total_count` and `has_results=True` while `page_obj` is empty. |
| **Impact** | A buyer sees a results page that claims matches exist and displays none — most likely the "no results for X" empty state is suppressed, so the page renders as a blank result list. Self-healing within the TTL, and it requires an invalidation gap (SRCH-005 or SRCH-007) to occur at the same time as a hot cached query, so it is rare. The architecture is right; only the counter is trusted too far. |
| **Root Cause** | `_resolve_search_count` was deliberately optimised (SRH-002) to avoid a second FTS evaluation, trading an exact count for one that is free. The trade is sound, but the function's contract is "how many matches exist" while its callers use it as "how many rows will be rendered" — and after SRH-002 those are only equal on the non-truncated path. |
| **Recommendation** | On the cache-hit path, derive the *displayed* count from the queryset the page actually renders (`Paginator.count`, which is a cheap `pk__in` count and not a full FTS evaluation) and keep the cached length only for the "results found" headline. Alternatively clamp: if `not page_obj` and `paginator.num_pages == 1`, treat the result as empty. Add a test that seeds a cached list, hides every ad in it without bumping the version, and asserts the rendered page and `has_results` agree. |
| **Effort** | S |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **Reproduction Steps** | 1. Create a PUBLISHED ad; `GET /search/?q=<term>&lang=ru` to warm the cache. 2. Hide the ad **without** bumping the search version (e.g. `User.objects.filter(pk=…).update(is_declined=True)`). 3. `GET /search/?q=<term>&lang=ru` again → `page_obj` is empty while `total_count` is still 1 and `has_results` is True. |
| **Related Findings** | SRCH-005, SRCH-007 |

**Evidence — `src/backend/apps/search/views/search.py:136-144,161-163,190`** *(supports: "the count comes from the cached list while the page comes from the re-filtered queryset")*:
```python
            if cached_ids:
                # Cache hit (fresh or stale-served): filter base queryset to
                # cached IDs and restore FTS rank order via Case/When.
                ads = ads.filter(pk__in=cached_ids).order_by(...)   # :138  live predicate re-applied
    ...
        total_count, results_truncated = _resolve_search_count(
            cached_ids, ads, query, params, request
        )                                                        # :161  ← len(cached_ids), not the page
    ...
    has_results = total_count > 0                               # :190  ← disagrees with page_obj
```

**Evidence — `src/backend/apps/search/views/search.py:307-309`** *(supports: "the count is deliberately the cached length, not the rendered count")*:
```python
    if cached_ids is not None and len(cached_ids) < SEARCH_CACHE_MAX_HITS:
        # Common non-truncated hot path: the cached ID list is authoritative.
        return len(cached_ids), False
```

## Cross-Finding Analysis

- **Merge candidates:**
  - **SRCH-001 + SRCH-011** share one root cause: the search *input boundary is enforced
    ad hoc at each call site instead of in one DTO*. `?features=` is unbounded in
    `ListingsQueryParams`; `SavedSearch.query` has no bound at all. A validator may
    reasonably merge them into one "search input bounds are not modelled" finding. They are
    kept separate because one is anonymous and takes the database down, the other requires a
    login and costs scheduler time.
  - **SRCH-010 + SRCH-013** share one root cause: the rate-limiting policy for the public
    browse/search surface is fragmented across three modules, each with its own client-IP
    helper, budget and key namespace, and none of them is authoritative. One consolidation
    closes both.
  - **SRCH-002 + PII-102 + PII-112 + PII-114** (cross-phase) share the "masking applied per
    call site instead of through a single logging policy" root cause. Phase 06 has already
    named it; SRCH-002 is the search-specific instance and adds the observation that two
    similarly-named sanitizers with different contracts sit in the same module, which is
    what made the wrong one get used.
- **Conflicting evidence:** none between findings in this report. One apparent conflict
  worth recording: R-21 shows the cache-hit path *re-applies* the live visibility predicate,
  which appears to contradict SRCH-005 and SRCH-007 (stale results). It does not — the
  re-filtering correctly hides ads that became invisible, but it cannot restore ads that
  became *visible* (SRCH-005), and it cannot notice that the cached *ordering*, *total_count*
  and *truncation flag* were computed against a different ad set (SRCH-007, SRCH-015). The
  re-filter is a confidentiality control, not a freshness control; findings are scoped
  accordingly.
- **Dependency chains:**
  1. **SRCH-004 → SRCH-008.** Both are fixed by the same shared visibility predicate
     (SRCH-004's recommendation). Doing SRCH-008 as a one-line `user__is_banned=False` in
     `build_queryset` before the predicate is extracted would have to be repeated in
     `alert_query.py`, `ad_detail` and `media_gate`; extracting the predicate first is
     strictly less work. **Fix SRCH-004's predicate before SRCH-008's filter.**
  2. **SRCH-005 + SRCH-007 → SRCH-015.** SRCH-015 can only be observed when a cache
     invalidation gap exists; fixing 005 and 007 first makes 015 a theoretical concern.
     Fix 015 last.
  3. **SRCH-006 → SRCH-002.** The two share an input value (`q`) and an input edge
     (`search.py:67`). A single sanitising step at that edge can carry the control-character
     strip (006) and, downstream of it, the redaction for the log line (002). Doing 006
     first makes 002 a one-line change on top.

## Remediation Roadmap

| Order | ID | Severity | Effort | Priority | Recommendation (summary) |
|-------|----|----------|--------|----------|--------------------------|
| 1 | SRCH-001 | CRITICAL | S | P0 | `max_length` on `ListingsQueryParams.feature_slugs` + truncate in `build_queryset`; regression test at 500 params |
| 2 | SRCH-006 | HIGH | S | P0 | Strip control chars at the single `q` input edge (search + autocomplete); make analytics writes non-fatal to the page |
| 3 | SRCH-002 | CRITICAL | S | P0 | Pass `redact_search_query(sanitize_query_for_log(q))` to the empty-results log line; assert absence via `caplog` + `RedactingJsonFormatter` |
| 4 | SRCH-003 | HIGH | S | P0 | Migration: de-dup then `UniqueConstraint` on `popular_searches.query_normalized`; make the increment failure-tolerant |
| 5 | SRCH-004 | HIGH | M | P0 | Extract one querysets-level public-visibility predicate; call it from `ListingsQuery.build_queryset` **and** `find_matching_ads` |
| 6 | SRCH-005 | HIGH | S | P1 | `transaction.on_commit(bump_search_cache_version)` in `give_consent()`; extend the test to the view, not just the queryset |
| 7 | SRCH-007 | HIGH | S | P1 | `timeout=None` on the content-version `cache.set`; test the expire-then-bump re-issue |
| 8 | SRCH-008 | MEDIUM | S/M | P1 | Decide the ban semantics, then add `user__is_banned=False` **inside the shared predicate from #5**; record it in `db-schema.md:63` |
| 9 | SRCH-010 | MEDIUM | S | P1 | One shared `get_client_ip()` that reads the proxy-appended address; unit-test the multi-hop header |
| 10 | SRCH-009 | MEDIUM | S | P1 | Surface the fuzzy category match as a removable filter chip; skip detection when `?category=` is present; raise the cutoff |
| 11 | SRCH-011 | MEDIUM | S | P1 | Cap `save_search()`'s `query` at the shared `MAX_SEARCH_QUERY_LENGTH`; align `SavedSearch.query` with `PopularSearch.query_normalized` |
| 12 | SRCH-013 | LOW | S | P2 | Document both app-level budgets and state that nginx is authoritative |
| 13 | SRCH-014 | LOW | S | P2 | Correct the `cache.py` docstring to match the SWR helper's inline recompute |
| 14 | SRCH-015 | LOW | S | P2 | Derive the displayed count from the rendered queryset; add the cached-vs-live test |
| 15 | SRCH-012 | MEDIUM | S | P2 | Documentation only — update the phase-08 rubric (and the 05/06 cross-refs) to the shipped DECLINE semantics; close via PII-113 |

## Rollout Safety

| ID | Risk | Backward-compatible? | Test gap (must cover) |
|----|------|----------------------|-----------------------|
| SRCH-001 | Med — a legitimate client sending more filters than the new cap silently gets a broader result set. Pick the cap above the UI's real maximum so no real user hits it, and log when truncation occurs. | Yes (the cap is above every UI-produced request) | New test: 500 `?features=` ⇒ ≤ cap joins, HTTP 200. No existing test sends more than a handful of features. |
| SRCH-006 | Low — stripping control characters cannot change a legitimate query. Rejecting (400) instead would be visible; strip-and-continue is not. | Yes | New test for `%00` on both endpoints; extend `TestSearchViewInputRobustness`. |
| SRCH-002 | Low — log content only. If any downstream log-based alerting matches on the query text, the message changes; nothing in-repo does. | Yes | New test asserting the PII fragments are absent from the formatted record. `test_redact_search_query.py` is unaffected (persistence path unchanged). |
| SRCH-003 | **Med** — the migration must de-duplicate first or it will fail on existing duplicate rows; and `get_or_create` semantics change once duplicates are impossible. Any code that relied on duplicates (nothing should) breaks. | Yes, after the de-dup step | New test: seeding duplicates then incrementing must not raise. Run the de-dup as a separate, idempotent management command or in the migration with a documented `RunPython`. |
| SRCH-004 | **Med** — adding `user__is_declined=False` to the alert path means already-subscribed users stop receiving ads from declined sellers. That is the intent, but it will look like "alerts stopped working" to a few users and will change daily digest counts. `test_alert_query.py` and `test_send_alerts.py` assert on match sets and will need updating. | Yes (behaviour change only for hidden inventory) | Existing `test_alert_query.py` / `test_send_alerts.py` must be extended with a declined-seller case; there is currently none. |
| SRCH-005 | Low — one extra `cache.incr` per consent acceptance. | Yes | Extend `test_give_consent_restores_declined_ads_to_queryset` to assert the cached **view** result, which is the gap that let this through. |
| SRCH-007 | Low — a non-expiring cache key. Slightly higher Redis memory (one integer) and one less source of accidental reset; note that a Redis flush now also resets the version, which is correct behaviour for a flush. | Yes | New test for the expire-then-bump key-reuse case (currently unasserted anywhere). |
| SRCH-008 | **Med** — hiding banned sellers' inventory is user-visible and reverses a moderator's visible effect; the moderator UI currently implies the ban is enough. Requires the product answer in the recommendation, plus a note in the moderation changelog. | No (deliberate behaviour change) | New test: banned seller's ad absent from search, listings, `ad_detail` and `media_gate`. Extend the bulk-ban admin-action test to assert the cache version is bumped. |
| SRCH-010 | Low — rate-limit keys change, so existing counters are discarded once. Brute-force protection is unaffected because nginx is authoritative. | Yes | New unit test for the multi-hop `X-Forwarded-For` case; the existing `test_search_view.py::TestSearchViewRateLimit` must be updated if it relies on the current header semantics. |
| SRCH-009 | Med — surfacing the fuzzy match as a chip changes the rendered results page and the filter-summary block. Raising the cutoff changes which single-word queries are category-scoped, so some users will see *more* results than before. | Yes | New test: one word, matches in two branches ⇒ both returned. Existing `test_search_fuzzy.py` pins the current narrowing behaviour and must be reviewed. |
| SRCH-011 | Low — long saved searches are truncated; no legitimate user creates one. | Yes | New test posting an oversized `query`. |
| SRCH-013 | Low — comment/doc only. | Yes | n/a |
| SRCH-014 | Low — docstring only. | Yes | n/a |
| SRCH-015 | Med — the displayed total becomes the rendered count, so it will differ from the cached length on the capped path. That is the point, but `test_search_query_count.py` pins the current `total_count` semantics and will need a careful review before being changed. | Yes for the user, No for `total_count`-based assertions | Existing `test_search_query_count.py` (at-cap and cold-miss-loser cases) must be reviewed; a new test must pin the cached-vs-live disagreement. |
| SRCH-012 | Low — audit documentation only. | Yes | n/a |

## Appendices

### Appendix A — Full probe output (one run, trigger verified present)

Every `[Rxx]` line below is the raw stdout of a single `probe_srh.py` run inside the
`mko-bazuna-test` Compose project, with `ads_search_vector_update` installed (confirmed via
`pg_trigger`) so that FTS results are real. Deleted along with the probe scripts.

```text
[R1]  {"status": 200, "statuses_found": ["published"]}
[R1b] {"status": 200, "statuses_found": ["published"]}
[R2]  {"search_status": 200, "search_contains_banned_ad": true, "detail_url": "/54/", "detail_status": 200,
       "listings_contains_banned_ad": true}
[R3]  {"alert_matched_declined_ad": true, "web_contains_declined_ad": false}
[R4]  {"alert_matched_inactive_cat_ad": true, "web_contains_inactive_cat_ad": false}
[R5]  {"codes": {"'; DROP TABLE ads; --": 200, "1 OR 1=1": 200, "%' UNION SELECT telegram_id,": 200,
                 "велосипед'; UPDATE ads SET s": 200, "\\'; DELETE FROM ads WHERE '1": 200,
                 "велосипед\x00\x01\x02": 200, "aaaa…(500)": 200, "велосипед ×200": 200,
                 "(){}[]|\\<>@#$%^&*": 200, "𝑣𝑒𝑙𝑜𝑠𝑖𝑝𝑒𝑑": 200, "велосипед<U+200B>": 200,
                 "велосипе́д": 200}, "ads_table_intact": 1}
[R5b] {"nul": "EXC DataError: PostgreSQL text fields cannot contain NUL (0x00) bytes", "bell": 200,
       "nul_alone": "EXC DataError: …", "autocomplete_nul": "EXC DataError: …"}
[R6]  {"interpolated": false, "params": ["russian", "велосипед'; DROP TABLE ads; --"],
       "sql_head": "SELECT \"ads\".\"id\", \"ads\".\"user_id\", \"ads\".\"title\", …"}
[R7]  {"0": {"code": 200, "sql_len": 524,   "selects": 23},
       "5": {"code": 200, "sql_len": 1389,  "selects": 15},
       "20":{"code": 200, "sql_len": 3559,  "selects": 15},
       "40":{"code": 200, "sql_len": 6459,  "selects": 15},
       "60":{"code": 200, "sql_len": 9431,  "selects": 15}}
[R7b] {"accepted": 500, "sql_len": 76771, "feature_joins": 502}
[R8]  {"root": true, "child": true, "other_branch": false, "total_count": 2}
[R9]  {"two_word_match": true, "one_word_match": true}
[R9b] {"bikes_branch": true, "electronics_branch": false}
[R10] {"ru": {"code": 200, "hits": true}, "bs": {"code": 200, "hits": false}, "en": {"code": 200, "hits": false},
       "en_vector_matches": true, "ru_vector_matches": true, "bs_vector_is_empty": true}
[R11] {"pii_query": "Иван Петров +38269123456 ivan@example.com",
       "sanitize_query_for_log": "Иван Петров +38269123456 ivan@example.com",
       "sanitize_keeps_phone": true, "sanitize_keeps_email": true, "sanitize_keeps_name": true,
       "log_lines": ["{\"timestamp\": \"2026-09-28 03:38:19,063\", \"level\": \"INFO\",
        \"message\": \"Empty search results for query 'Иван Петров +38269123456 ivan@example.com'\",
        \"logger\": \"apps.search.views.search\", \"stack_info\": null}"]}
[R12] {"history_query": "И*** П***** +3********** iv**@example.com",
       "history_normalized": "иван петров +38269123456 ivan@example.com",
       "popular_query": "И*** П***** +3********** iv**@example.com",
       "popular_normalized": "иван петров +38269123456 ivan@example.com"}
[R13] {"second_search_code": "EXC MultipleObjectsReturned: get() returned more than one PopularSearch -- it returned 2!",
       "rows": 2}
[R13b]{"indexes": [["popular_searches","popular_searches_pkey",true], … 6 non-unique indexes …]}
[R14] {"xff_rotating_429s": 0, "xff_total": 60, "fixed_ip_429s": 10, "fixed_ip_total": 40}
[R15] {"first_hit": true, "hidden_after_decline": true, "is_declined_cleared": true,
       "visible_after_give_consent": false, "search_version": 2}
[R16] {"version_before": 1, "version_after": 1, "bumped": false, "still_visible": false}
[R18] {"empty": {"code":200,"total":1}, "spaces": {"code":200,"total":1},
       "stopwords_ru": {"code":200,"total":0}, "punct": {"code":200,"total":0}}
[R19] {"page_0":200,"page_neg":200,"page_huge":200,"sort_bogus":200,"min_price_bogus":200,
       "cat_bogus":200,"city_bogus":200}
```

*(supports the claims: "the visibility matrix is correct", "the alert path disagrees with the
web path", "no SQL injection", "the features list is unbounded", "raw PII reaches the log
record and the production formatter", "duplicate `popular_searches` rows 500 the search page",
"`X-Forwarded-For` spoofing defeats the app-level limiter", "consent restore does not
invalidate the cache", "hostile scalars are coerced")*

### Appendix B — Second probe run (cache version, saved search, features surface)

```text
# probe2.py
[P1]  {"version": 2, "search_cache_ttl": 300, "stale_ttl": 60, "total_entry_lifetime_s": 360,
       "bump_search_version_passes_timeout": false}
[P1b] {"first_hit": true, "version_before": "1", "version_after_expiry": "0", "key_reused": false,
       "cache_hit_before": [3], "cache_hit_after": []}
[P1c] {"v_before_expiry": "1", "v_after_expiry": 0, "v_after_next_bump": "1",
       "key_reused": true, "cache_hit_cycle1": [2], "cache_hit_cycle2": [2]}
[P2]  {"submitted_chars": 50000, "stored_chars": 50000}

# probe3.py
[P3]  {"features": 10,  "sql_len": 3577,  "features_mentions": 12}
[P3]  {"features": 40,  "sql_len": 7867,  "features_mentions": 42}
[P3]  {"features": 100, "sql_len": 16759, "features_mentions": 102}
[P3]  {"features": 300, "sql_len": 46759, "features_mentions": 302}
[P4]  {"sql_len": 2212}       # category-subtree filter stays small (MPTT range) — no equivalent bomb
```

*(supports the claims: "the content version is re-issued and a stale result set is resurrected",
"`SavedSearch.query` is unbounded", "the `features` JOIN count grows without limit")*

### Appendix C — Search trigger DDL (read from `setup_search_triggers.py` / `ads/migrations/0001_initial.py`)

```sql
CREATE OR REPLACE FUNCTION ads_search_vector_fn() RETURNS TRIGGER AS $$
DECLARE
  v_cat TEXT; v_name_bs TEXT; v_name_en TEXT;
BEGIN
  SELECT name, name_i18n->>'bs', name_i18n->>'en'
    INTO v_cat, v_name_bs, v_name_en
    FROM categories WHERE id = NEW.category_id;
  NEW.category_name := v_cat;
  NEW.search_vector_ru :=
    setweight(to_tsvector('russian',  coalesce(NEW.title,'')),       'A') ||
    setweight(to_tsvector('russian',  coalesce(NEW.description,'')),  'B') ||
    setweight(to_tsvector('russian',  coalesce(v_cat,'')),             'C');
  NEW.search_vector_bs := … 'simple'  … ;
  NEW.search_vector_en := … 'english' … ;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;

CREATE TRIGGER ads_search_vector_update
  BEFORE INSERT OR UPDATE ON ads
  FOR EACH ROW EXECUTE FUNCTION ads_search_vector_fn();
```

*(supports the claims: "the vectors are row-level and maintained on every insert/update, so the
promote-before-`atomic()` window in `submission.py:166` cannot desynchronise them — the trigger
derives its inputs only from `title*`/`description*`/`categories.name`, none of which a status
transition touches (R-26)"; and, for phase 03/05, "this DDL is created by a management command,
not by a migration, so a database that is not bootstrapped by `migrate_locked` silently has no
search index at all — a condition this audit hit directly, see Assumption 3")*

