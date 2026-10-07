---
plan_id: "08-search-fts-remediation"
phase: "08"
phase_name: "Search & Full-Text Search"
source_report: ".ai/audit/99-validation/08-search-fts-validated-findings.md"
date: "2026-09-29"
planner: "Planner (subagent)"
anchor_commit: "aa2a6b0"
report_anchor_commit: "9e96b84"
status: "done"
findings_in_scope: 21
blocks: 14
---

# Execution Plan — Phase 08 Remediation (Search & Full-Text Search)

## 0. Header, provenance and scope statement

### 0.1 Provenance

| Item | Value |
|---|---|
| Source report | `.ai/audit/99-validation/08-search-fts-validated-findings.md` (validated, 1406 lines) — the **only** surviving phase-08 source |
| Source findings file | `.ai/audit/08-search-fts/findings.md` — **deleted from the working tree** (tracked deletion). Recorded for traceability only; **not** an input |
| Report anchor commit | `9e96b84` — **stale** |
| Code-context document | `.ai/tmp/code-context-phase08.md` (730 lines, Auditor) |
| **Working anchor commit for this plan** | **`aa2a6b0`** (`git rev-parse --short HEAD`, taken before writing) |
| Date | 2026-09-29 |
| Items in scope | 21 (15 `SRCH-` + 6 `VAL-`): **17 still open · 1 partial · 2 process-only · 1 already fixed · 0 rejected** |
| Validated severity split (of the open set) | 1 CRITICAL (`SRCH-001`) · 5 HIGH (`SRCH-002`, `003`, `005`, `006`, `007`) · 4 MEDIUM (`SRCH-008`, `009`, `010`, `011`) · 4 LOW (`SRCH-013`, `014`, `015` half, `VAL-005`) · `VAL-001` HIGH (rollout risk), `VAL-003` MEDIUM, `VAL-006` MEDIUM |
| State at the anchor | **0 fixed by phases 01–06.** Nothing in those phases touched a search FTS surface (C-13) |
| Execution blocks | 14 (12 implementation + 1 documentation + 1 decision/handoff) |
| Implementor concurrency | 1, strictly sequential (project rule: only one implementor at a time) |

**Naming convention.** This plan cites its own items as **`SRCH-nnn`** / **`08-VAL-nnn`**
where a citation must survive into code comments, docstrings or commit messages.
**Do not grep `SRH-` in this repository** — the shipped source carries hard-coded
`SRH-001 … SRH-007` markers from an unrelated in-code convention in eleven places,
and the phase-08 handbook still mandates that prefix (`VAL-005`, BLOCK 13). The
legacy-marker sweep is **phase 03's**; this plan does not start it (§5.2).

### 0.2 Evidence basis — read this before executing any block

The validated report is the narrative source. This Planner re-derived the load-bearing
claims against the working tree at `aa2a6b0` using the Auditor's code context.
**Where the report and the tree disagree, the tree wins and the correction is listed
here.** Two of these corrections send a planner working from the report's file list to
**files that do not exist**.

| # | Claim | Report says | **Tree at `aa2a6b0` says** | Consequence for this plan |
|---|---|---|---|---|
| **C-1** | The ad-side cache-invalidation receivers live in `apps/ads/signals.py`; the `User` receiver belongs in `apps/users/signals.py`; the logging policy lives in `docs/08-features/i18n.md` | three real file paths | **`apps/ads/signals.py` does not exist.** The `post_save`/`m2m_changed` receivers are in `src/backend/apps/search/signals.py` (`bump_search_cache_on_ad_change`, `bump_search_cache_on_feature_change`). **`apps/users/signals.py` does not exist either.** There is **no** `docs/08-features/` directory; the i18n document is `docs/01-spec/i18n-spec.md` and it contains **no logging policy to amend** | `SRCH-005`'s receiver must be created or placed in `apps/search/signals.py`; `SRCH-002`'s policy recommendation has **no existing document** — the point fix is the whole of phase 08's half, and the policy declaration is routed to phase 06 |
| **C-2** | nginx has two different edge budgets: `rate=10r/s` burst 50 on `/search/`, `rate=20r/s` burst 40 on browse | two budgets | **One budget.** `search_limit` and `browse_limit` are both `rate=20r/s`, `burst=40`. `login_limit` is 10 r/s burst 20 on `/login/` | The "two different edge budgets" framing is wrong. The **application** budgets still differ (60/600 s vs 30/60 s) — do not conflate the layers |
| **C-3** | `sanitize_query_for_log` truncates to 200 characters | 200 | **`_MAX_QUERY_LENGTH = 100`.** It strips `[\x00-\x1f\x7f-\x9f]` and truncates to 100 | Any test or note that says "200" is wrong. **This collides directly with the documented 200-char `q` contract** — see Q4 |
| **C-4** | Delete the misleading index comment at `models.py:56-58` claiming `get_or_create` merges duplicates | a model comment | **There is no such comment.** `PopularSearch` carries a one-line docstring; `Meta` declares `db_table` only | The misleading documentation has moved to `docs/02-database/db-schema.md` (which records `query_normalized (VARCHAR(200), db_index=True)` with no uniqueness note). Edit the **doc**, not a comment that does not exist |
| **C-5** | Reject NUL "in the shared `sanitize_query_for_log`/`sanitize_autocomplete_query` path **both views already call**" | a swap | **`search()` does not call `sanitize_query_for_log` at the boundary** — only on the zero-result log line, which runs *after* the failure. `autocomplete()` does call `sanitize_autocomplete_query`, but that function strips only `[;'"\`]`, **not control characters** | This is **not** a "swap the function" edit. `SRCH-006` needs a new call site on the search input edge. See Q4 |
| **C-6** | `save_search` has a DTO that declares no constraint | a missing constraint | **There is no DTO at all.** `save_search` is `@login_required`, reads `request.POST` directly, and coerces with a local `_int_or_none` | `SRCH-011`'s "prefer the DTO constraint plus a migration" requires **introducing a DTO where none exists** — a larger change than the report implies. Bounded explicitly in BLOCK 8 |
| **C-7** | `/search/`'s 429 body is `{"error": "rate_limited"}` at `search.py:210-212` | transposed string, wrong site | The literal is **`{"error": "rate_limit"}`**, produced inside `search()` immediately after `rate_limit_check` returns `False`. `listings()` emits a bare empty `HttpResponse(status=429)` | A shared-response-shape refactor must use the real literal |
| **C-8** | The user-visible symptom of `SRCH-015` is "3 results next to 0 cards" | symptom | **`total_count` is never rendered in any template** (grep over `src/backend/templates` → no hits). The only count UI is the `results_truncated` banner. The real symptom is a **blank results area with no empty state** | The report's one-line fix is still right and now **simpler** (the only consumer of `total_count` in the UI is `has_results`). **Adding a count display would be scope creep** — see §6.2 |
| **C-9** | `VAL-003`'s first-hit ambiguity is in `_fuzzy_match_by_name` (the fuzzy path) | one path | **The exact-name path has the same defect.** `_fuzzy_category_match` returns `Category.objects.get(id=entry["id"])` on the **first** exact-name hit, identically to `_fuzzy_match_by_name` | The name→ids resolution must close **both** paths, or the exact path keeps returning an arbitrary branch |
| **C-10** | `SRCH-007` is four `cache.set(KEY, 1)` calls in four modules | four writers | Four writers **plus a fifth consumer**: `category_fuzzy.get_active_category_names` builds `category:fuzzy_names:{get_tree_version()}:{locale}` and inherits the eviction without owning the key. **And `docs/architecture/cache-strategy.md` prints the defective snippet as *the* project pattern** | Fixing only the four writers leaves a stale-category-list consumer live, and **a code-only fix leaves the doc teaching the defect**. BLOCK 6 owns all six surfaces |
| **C-11** | `SRCH-012` needs a four-line handbook edit; `VAL-002` is a live process defect | open | **Already fixed, differently.** All fifteen handbooks were rewritten on 2026-09-28 (16:47–20:22). `08-audit-search-fts.md` now contains **zero** occurrences of `DECLINE` or `is_declined`; so do `04-…` and `06-…` | `SRCH-012` is **closed** with no work item. `VAL-002`'s remaining half is a *convention* to encode, not a file edit — routed (§6.1) |
| **C-12** | `SRCH-004` is a phase-08 defect to fix | fix here | `06-PII-104` validated recommendation item 2 reads **verbatim**: *"Also exclude ads whose owner is DECLINED from `find_matching_ads()` and `find_matching_saved_searches()`"* | **`SRCH-004` is owned by phase 06. Phase 08 must not edit `apps/search/services/alert_query.py`.** BLOCK 14 is a decision/handoff block only |
| **C-13** | — | — | Nothing in phases 01–06 touched a search FTS surface. Their work landed in `settings/base.py`, `settings/prod.py`, `core/enums.py`, `docs/01-spec/contact-us.md`, `docs/ops/docker-deployment.md` and the auth/consent services | Confirms 17/17 still open. Also means `settings/base.py` and `docs/ops/docker-deployment.md` are **contended** when BLOCK 2 runs |
| **C-14** | `sanitize_autocomplete_query` enforces length 2–100 and strips injection characters | — | Confirmed, and it does **not** strip control characters, so NUL passes through to the `LIKE` parameter in `get_popular_suggestions` | The two endpoints fail at **different** call sites; one fix must cover both without merging their length contracts |
| **C-15** | Every runtime claim was reproduced by the validator | reproduced | **All 15 runtime-only claims are unverified in this pass.** This Planner ran no database, no test suite and no migration | §0.2.1 lists what each block must re-verify, with the Docker commands |

#### 0.2.1 Runtime re-verification required before a block relies on a claim

Cheap, and part of the block's **Auditor** pre-step — never the Implementor's to
discover mid-edit. All tests are Docker-only (§1.1); no test was run for this plan.

| # | Claim to re-verify | Block | How (Docker-only unless stated) |
|---|---|---|---|
| 1 | `?features=` really is unbounded: `ListingsQueryParams.feature_slugs` is a bare `list[str]` with no count bound, validator, or whitelist; `build_queryset` emits one `features__slug=` filter per element | 1 | Static read is sufficient and already done (C-15 note 1). Runtime: the join-count curve needs a **private** container — see row 5 |
| 2 | The `feature_slugs` join loop is unchanged and the shipped UI cannot emit more than the resolved feature set | 1 | Count `LookupItem(LISTING_FEATURE, is_active=True)` at seed volume in the test DB. Static evidence: `ad_list.html` re-emits only `current_features`, so the UI ceiling is catalogue-bound, not user-bound |
| 3 | `SHOW statement_timeout` and `SHOW lock_timeout` both return `0` on a live connection | 1 | `$dc run --rm --no-deps --entrypoint "" test psql -c "SHOW statement_timeout; SHOW lock_timeout;"` against the DB on port 5433. Expected `0`, `0` |
| 4 | `popular_searches` has no unique index beyond the primary key | 5 | `SELECT indexname FROM pg_indexes WHERE tablename = 'popular_searches';` in the test DB |
| 5 | The crash curve (20 → 1.31 s, 40 → 7.88 s, 60 → 19.90 s → `signal 9` → cluster crash recovery) | 1 | **Never** on `mko-bazuna-test` (VAL-004). A throwaway `postgres:18-alpine` on its own port, schema built by `migrate --run-syncdb` + `setup_search_triggers`, then time `ListingsQuery.build_queryset(params).count()` for N ∈ {0, 10, 20, 40, 60}. **If this is not reproducible, the ceiling in Q2 must be re-derived, not copied** |
| 6 | A NUL byte in `q` raises `DataError` on `/search/` **and** on `/api/search/autocomplete`, while `\x07` returns 200 | 3 | Add the regression test first, then `$dc run --rm -e PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/search/tests/test_search_view.py --tb=short" test`. Assert **red** before the fix |
| 7 | The version counter evicts at `DEFAULT_TIMEOUT` and the next bump re-issues `1`, making an earlier key byte-identical | 6 | **Do not sleep 300 s.** Patch the clock / assert on the stored expiry with a `LocMemCache`-shaped test; then compare `build_search_cache_key` output across the boundary |
| 8 | A DECLINED seller's ad and an INACTIVE-category ad are selected by `find_matching_ads` and rejected by `ListingsQuery.build_queryset` | 14 (handoff only) | **Phase 06's to add.** Phase 08 records the requirement; it does not write the test (C-12) |
| 9 | Two active categories sharing a localised display name scope a single-word search to one branch, possibly an empty one | 10 | Seed two active categories with the same `name_i18n['ru']`, one ad each, then `GET /search/?q=<name>` and assert `total_count`. **Wipe all rows first and re-assert `ads_search_vector_update` is present** — the report's own false-refutation came from a stale-data artefact |
| 10 | A rotating `X-Forwarded-For` defeats the application limiter while a fixed value does not | 9 | Target the limiter with `RequestFactory` and a patched `HTTP_X_FORWARDED_FOR`; 40 iterations per case. nginx's own limits are keyed on `$binary_remote_addr` and are **not** spoofable — the claim is about the *application* policy only |
| 11 | A 50 000-character `query` round-trips through `POST /save-search/` | 8 | `client.post("/save-search/", {"query": "x" * 50000})`, then assert the stored value |
| 12 | The production `RedactingJsonFormatter` output contains the phone, e-mail and name | 4 | Capture a real `LogRecord` through the formatter in a targeted test. `redact_string`'s pattern only matches `key=value`, so a bare quoted value is not touched — assert **red** before the fix |
| 13 | `total_count > 0` with an empty `page_obj` yields neither cards nor an empty state | 12 | The template half is now statically confirmed (C-8); the symptom needs a warm cache plus a bulk `.update()` that bypasses the version bump |

**The Method trap is still live.** An out-of-tree probe module does not inherit the root
`conftest.py` autouse session fixture, so `ads_search_vector_update` is **absent** and
every FTS check silently reports "0 hits". **Any** FTS-dependent verification must first
assert `trigger_present` from `pg_trigger` (`tgenabled = 'O'`,
`tgname = 'ads_search_vector_update'`) **and** run a positive control query that MUST
match. No FTS result in this plan may rest on a "0 hits" observation.

**`VAL-009` is settled and closed.** `ads_search_vector_update` is a
`BEFORE INSERT OR UPDATE ON ads FOR EACH ROW` trigger, duplicated in
`apps/migrations/0001_initial.py` and `setup_search_triggers.py`, pinned by
`test_search_triggers.py::test_title_update_refreshes_all_search_vectors` and
`::test_category_name_i18n_edit_cascades_reindex`. A category rename re-derives the
vectors because `categories_name_propagate` issues a real `UPDATE ads`, which re-fires
the trigger. **Phase 06's ruling that `VAL-009` is overstated is correct. No block in
this plan builds a re-derivation mechanism, and no block touches the FTS DDL, the
trigger, or `setup_search_triggers`** (§6.3).

### 0.3 Scope statement (explicit)

**In scope — 17 open items + the `SRCH-015` remainder.**

`SRCH-001`, `002`, `003`, `005`, `006`, `007`, `009`, `010`, `011`, `013`, `014`,
`015` (partial), `VAL-001`, `VAL-003`, `VAL-005`, `VAL-006`, and `VAL-004` as a
**binding verification constraint** (private-instance discipline, no code change).

**Handled, no implementation work in phase 08:**

- **`SRCH-004`** — owned **verbatim** by `06-PII-104` rec. 2. Phase 08 **must not edit
  `apps/search/services/alert_query.py`**. BLOCK 14 publishes the handoff and the
  acceptance criteria phase 06 must satisfy.
- **`SRCH-008`** — an **owner product decision** (phase 06 ruled a ban is a moderation
  action, not a consent action). BLOCK 14 publishes the two options; **neither option
  is implemented by this plan**, and the change must not be bundled into a commit
  justified as "fixing a consent violation".
- **`SRCH-012`** — already fixed by the 2026-09-28 wholesale handbook rewrite (C-11).
  Closed, restated in §8.1 so it is not silently re-filed.
- **`VAL-002`** — largely resolved by the same rewrite. The surviving half is a
  *convention* ("an assertion about product behaviour must be re-derived from the
  current spec; an FTS/predicate assertion must carry a positive control"), routed to
  the coordinator (§6.1). No file edit.

**Not in scope — the report's own de-scopings, upheld:**

- The alert-path **latency** measurement and every GIN / trigram effectiveness claim.
  Phase 13's, and the report deliberately makes no latency claim.
- The legacy `search_vector` column and `IX_ads_search_gin` removal candidate. Phase 13's
  index-grading scope. Flagged in §5.6, **not** actioned.
- `03-DB-004` (`statement_timeout`). Phase 03's code; phase 08 records it as a **rollout
  gate** on BLOCK 1 (§4.4) and must not edit `config/settings/base.py` to add it.

**One hard rollout gate this plan does not lift.** `IMMEDIATE_ALERTS_ENABLED` must stay
`False` in every environment until **both** the ad predicate (phase 06's `06-PII-104`)
and the audience predicate (`06-VAL-003`) exist, because the immediate path ships a
**working deep link** to an ad a declined seller's audience may not see. The daily
digest (`send_alerts`, first hourly tick ≥ 08:00 UTC) is **not** feature-gated and is
**live today** — which is exactly why `SRCH-004` is a HIGH and not a MEDIUM.

**Irreducible hazard statement.** BLOCK 5's data migration **destroys rows**
irreversibly. There is no soft path: the deduplicated `popular_searches` rows do not come
back on `migrate back`, and the reverse operation must therefore be a deliberate
`RunPython.noop`. Every other block is a straight revert.

### 0.4 Severity corrections

The report's own movement is upheld in full and is **not** re-litigated here:

| ID | Movement | This plan's position |
|---|---|---|
| `SRCH-002` | CRITICAL → **HIGH** | **Upheld.** Operator JSONL sink, zero-result branch only, the data subject's own typed query. It is a P0 at HIGH because it is always-on, unbounded in volume, and a third party can cause a specific person's phone number to be logged by getting them to click a link |
| `SRCH-012` | MEDIUM → **LOW**, reclassified DOC-UPDATE | **Upheld, and now moot** — the four occurrences no longer exist (C-11) |
| `SRCH-004` | reclassified SPEC-DEVIATION | **Upheld, and removed from phase 08's implementation scope** (C-12) |
| `SRCH-007` | reclassified to a structural, project-wide contract | **Upheld and widened** — five consumers, not four writers, plus the canonising doc (C-10) |
| `SRCH-003` | reclassified to DATA-INTEGRITY | **Upheld.** A schema-invariant violation, not a race. Remediation leads with a migration, not with locking |
| `VAL-001` | HIGH (rollout risk) | **Upheld.** The 1 GB cgroup is the shipped **production** default; `DB_MEM_LIMIT` is absent from every `.env*` file including `.env.prod.example` |

**Corrections this Planner makes to the report's supporting detail** (none change a
finding's status):

- **C-1** — two of the report's cited files **do not exist**. `apps/ads/signals.py` and
  `apps/users/signals.py`; `docs/08-features/i18n.md` is `docs/01-spec/i18n-spec.md`
  and has no logging policy to amend. A planner working from the report's file list
  blocks immediately; the Implementor must not go looking for them.
- **C-2** — one nginx edge budget, not two. The two *application* budgets differ.
- **C-3** — the log sanitiser truncates to **100**, not 200. This is the collision in Q4.
- **C-4** — the misleading `models.py` comment does not exist; the misleading doc is
  `db-schema.md`.
- **C-5** — `search()` has **no** boundary call to `sanitize_query_for_log`; the SRCH-006
  fix is not a one-line substitution.
- **C-6** — `save_search` has **no DTO**. Introducing one is the honest scope of BLOCK 8.
- **C-7** — the 429 literal is `rate_limit`, not `rate_limited`, and it is produced inside
  `search()`.
- **C-8** — `total_count` is never rendered. The symptom is a blank results area, and
  **no count display may be added**.
- **C-9** — the ambiguous-name defect is on the **exact** path as well as the fuzzy one.
- **C-15** — all 15 runtime claims are unverified; §0.2.1 carries the commands.

### 0.5 Open technical questions — resolved here, or explicitly gated in their block

**This plan does not choose where technical uncertainty exists.** Each question below
produces either a pre-block step (Auditor / Researcher / Planner) or a labelled
**decision required before implementation** gate inside the named block, with the options
and their consequences. **Silence is not an acceptable outcome for any of them.**

| ID | Question | Block | Who decides | Status |
|---|---|---|---|---|
| **Q1** | **Who owns the cache-version-key lifetime after the 2026-09-28 handbook rewrite?** The report assigns the 300 s-counter-vs-360 s-entry inequality wholly to phase 08. The rewritten phase-08 handbook **block 10** assigns *"a freshness/version token's lifetime against the lifetime of the data it retires"* to **phase 13**, leaving 08 the *stale-read* half. This decides whether `SRCH-007` is a phase-08 item at all | **6** | **Coordinator** ruling, with Researcher input on what "phase 08 owns the cached result-set" still covers | **GATED — the highest-consequence open question in the plan.** BLOCK 6 carries both readings with their consequences | **OPEN — COORDINATOR RULING (not an agent decision).** The evidence half is now answered and the mechanism is RECOMMENDED: option (a), a durable `timeout=None` version key across all four writers. Phase 13's own text states the split as settled and hard-depends on BLOCK 6. Four sub-rulings are listed in §0.6.2. See §0.6 |
| **Q2** | **What is the correct `features` ceiling?** The report says 10 and warns any bound "must sit far below 20" (20 already costs 1.31 s; 40 costs 7.9 s; 60 kills the backend). But 10 is a *guess*, the resolved feature set is catalogue-driven, and **the UI cap must not land first** — if the shipped UI can already emit more than the cap, that is a separate UI defect | **1** | Researcher (measure the catalogue) + **Owner (product)** (state the ceiling) | **GATED.** A cap that lands before a UI cap is a rollout regression, not a fix | **RESOLVED 2026-10-03 (Product Owner) — option (b): NO hard-coded `?features=` ceiling. The bound is the catalogue invariant "the resolved feature set for any category", measured at seed volume, plus stated headroom, enforced by a guard test that keeps the ceiling honest as the catalogue grows.** BLOCK 1a's correlated subquery remains the real cost control, so the ceiling is a secondary parameter-list guard. The UI-cap-before-server-cap ordering constraint is **unchanged** and still binding. See §0.6 and §0.7 |
| **Q3** | **Does a catalogue-membership whitelist on `feature_slugs` cost more queries than it saves, and does it break `_QUERY_BOUND`?** `test_search_query_count.py::test_search_view_query_count_bounded` pins a total captured-SQL bound **and** explicitly forbids a hot-path FTS `COUNT(*)`; `test_search_slo.py` pins 2 s | **1** | Researcher + Planner | **GATED.** A per-slug membership query would fail the bound. Amend the test **explicitly in the commit body** if the bound must move — never silently | **RESOLVED 2026-10-01 — option (d): the spec's correlated subquery over `AdFeature`, AND-semantics made explicit, NO whitelist.** BLOCK 1 owns a live spec deviation, not an invention. The bound-test premise is moot. See §0.6 |
| **Q4** | **Is the NUL fix a strip, a rejection, or a shared normaliser — and what happens to the 200-vs-100 truncation contract?** `sanitize_query_for_log` already strips control characters but truncates to **100** (C-3); the documented `q` contract is **200**. Reusing it wholesale silently shortens `q` and would change `test_query_exceeding_max_length_returns_200` | **3** | Researcher (shape) + **Owner (product)** (whether a mutated query is acceptable) | **GATED.** All three shapes are argued in BLOCK 3 | **RESOLVED 2026-10-03 (Product Owner) — strip invisible/control characters at the input edge and search the CLEANED query.** Option (a)'s shape, with one hard constraint the block must honour: **`sanitize_query_for_log` must NOT be reused wholesale**, because it truncates to 100 while the view/column contract is 200. The **200-char contract and `test_query_exceeding_max_length_returns_200` are preserved**. **Positive control: a legal query returns byte-identical ads.** See §0.6 and §0.7 |
| **Q5** | **Does `SavedSearch.query` need redaction as well as a length bound?** `PopularSearch.query` / `SearchHistory.query` store the **redacted** form; `SavedSearch.query` is stored **raw** and is fed straight to `websearch_to_tsquery` on both alert paths. A bound fixes `SRCH-011`/`VAL-006`; redaction is a different question that `06-PII-108` may or may not have considered for this table | **8** | **Phase 06 (owner of the PII policy)** + Planner | **GATED.** Do not assume. If phase 06 owns it, BLOCK 8 ships the bound only and records the redaction question in its commit body | **RESOLVED 2026-10-03 (Product Owner) — `SavedSearch.query` is stored REDACTED via `redact_search_query()`, and `query_normalized` is keyed on the redacted form. One rule for all query-persistence paths; redaction happens at write, and the stored redacted value is what feeds `websearch_to_tsquery`.** The question is **CLOSED, not deferred.** In this plan BLOCK 8's length bound **ships as planned**; the redaction call and its test are **phase 09's** `09-API-012` and the storage-layer `09-VAL-002`. **Propagation obligation on phase 06** (PII policy owner, `06-PII-108`). See §0.7 |
| **Q6** | **Where does the ad-visibility predicate live, and does `06-VAL-003`'s shape constrain it?** A named function in `apps/ads`, **not** a default manager — a default manager would hide withdrawn users from the bot's `AccountStateMiddleware`. `IMMEDIATE_ALERTS_ENABLED` is sensitive to any queryset-level change | **14** | Phase 06 (predicate owner) + **coordinator** (sequencing against phase 03 BLOCK 9) | **GATED and largely answered by phase 06's own plan.** BLOCK 14 records the constraint; it does not write the predicate |
| **Q7** | **Does a ban hide inventory?** `db-schema.md:61` says "account block (US-A4)"; `:77` expands it to login/publish enforcement only. Phase 06's validation: *"nothing in the spec says a banned account must be excluded from the market"* | **14** | **Owner (product)** | **GATED.** Two fully argued options in BLOCK 14; **neither is implemented here** | **RESOLVED 2026-10-03 (Product Owner) — option (a): A BAN HIDES INVENTORY.** A banned seller's ads are excluded from the public ad-visibility predicate **across search, category, detail and the media gate**. It must be argued as a **moderation** decision and must **never** be bundled into a commit justified as fixing a consent violation. The `db-schema.md:61` amendment is **phase 06's file** — propagation obligation recorded. See §0.7 |
| **Q7′** *(new, from the 2026-10-03 Product Owner rulings)* | **Does ban enforcement also cover creating and publishing a new ad?** The answer changes the scope of `SRCH-008` from a visibility term alone to a **write** boundary, and it closes a known gap recorded elsewhere in the plan set | **14** | **Owner (product)** | **RESOLVED 2026-10-03 (Product Owner) — a banned seller CANNOT create or publish a new ad.** Ban enforcement covers **relisting**, not only login. Where any plan records *"a banned seller can still relist"* as an accepted known gap, that gap is **now closed** and the known-gap test becomes a **positive control asserting the block**. The predicate work stays phase 06's; the publish/create gate is named in BLOCK 14 and in §5.5. See §0.7 |
| **Q8** | **Does the single-word narrowing stay a hard filter?** `technical-specification.md:66` documents it verbatim, so the current behaviour is **specified**, not a regression. The finding is that the spec chose recall-reducing behaviour with no UI signal | **11** | **Owner (product)** | **GATED.** If the owner accepts the narrowing as intended, `SRCH-009` drops to LOW and resolves to a documentation change plus BLOCK 10's ambiguity fix | **RESOLVED 2026-10-03 (Product Owner) — the single-word narrowing STAYS a hard filter, AND the UI must signal it.** Option (a)'s disjunctive-branch fix is **NOT chosen**. BLOCK 11 ships the narrowing plus a results-page control reading *"showing results for &lt;Category&gt; only — search all categories"*, plus BLOCK 10's ambiguity fix. **`SRCH-009` therefore STAYS MEDIUM** and becomes an **implementation**, not a documentation change. **A new user-visible string is required → non-empty `ru` and `bs`.** See §0.7 |
| **Q9** | **What is the rollback story for the `popular_searches` dedup?** Deduplication destroys rows; `migrate back` cannot restore them | **5** | Researcher (reverse shape) + Planner | **GATED, narrow.** A `RunPython.noop` reverse plus a documented pre-count, or a mandatory pre-migration dump. `docs/ops/restore.md` / `rollback.md` are phase 12's | **RESOLVED 2026-10-01 — `RunPython.noop` reverse using `0004_backfill_delivered_at`'s hazard framing; set-based dedup; pre/post counts in the migration log.** `rollback.md`/`restore.md` already exist, so no runbook is needed. Migration is `0005`. See §0.6 |
| **Q10** | **Is `test_give_consent_restores_declined_ads_to_queryset` the only test encoding the cache-bypass workaround?** If others adopt the same "bypass the view because the cache is stale" pattern, BLOCK 7's blast radius is larger than one test | **7** | Auditor (search) | **Pre-block step, not a gate** — a grep over `apps/search/tests/` and `apps/ads/tests/` for the pattern, reported before the block starts | **ANSWERED 2026-10-01 — exactly ONE test** (`test_give_consent_restores_declined_ads_to_queryset`). BLOCK 7's blast radius is one function. See §0.6 |

---

### 0.6 Gate resolutions — 2026-10-01 (Auditor → Researcher pass)

**Scope.** The Auditor overturned several load-bearing premises, including one that reframes
BLOCK 1 from an invention into a conformance task. The Researcher closed Q3, Q9 and Q10 and
**recommended** the BLOCK 6 mechanism.

**Still open:** **Q1** is a **coordinator ruling**, not an agent decision — §0.6.2 lists the
four sub-rulings needed. **Q6** is phase 06's predicate ownership plus coordinator sequencing.

**Closed by the Product Owner on 2026-10-03 (§0.7):** **Q2** (catalogue-invariant ceiling),
**Q4** (strip at the input edge, 200-char contract preserved), **Q5** (`SavedSearch.query`
stored redacted; `query_normalized` keyed on the redacted form), **Q7** and **Q7′** (a ban
hides inventory, and a banned seller cannot create or publish), **Q8** (the narrowing stays and
the UI signals it). **No owner decision remains open in this plan.**

#### 0.6.1 Resolved decisions

| Gate | Decision | Why the alternatives lost |
|---|---|---|
| **Q3** | **Option (d) — implement the shape the spec already prescribes**, AND made explicit, **with no catalogue whitelist**. `ListingsQuery.build_queryset` replaces the per-slug chain + `.distinct()` with a counted subquery over `AdFeature`: `AdFeature.objects.filter(feature__slug__in=slugs).values("ad_id").annotate(n=Count("feature_id")).filter(n=len(distinct_slugs)).values("ad_id")`, then `ads.filter(pk__in=…)`. Cost becomes **2 joins + 1 subquery, O(1) in N**. `AdFeature.Meta.unique_together = [("ad","feature")]` makes `Count("feature_id")` already distinct; `feature__slug__in` means **zero** slug-resolution queries. | **The plan missed that `docs/01-spec/search-patterns.md` already prescribes this shape** — a correlated subquery over `AdFeature` with an `IN` clause, *"not a chaining `.filter()` per feature"* — while `build_queryset` does exactly the forbidden chain. **BLOCK 1 owns a live spec deviation, not an invention**, which makes it cheaper than the plan estimated. Rejected: (a) count cap alone leaves the N-join blowup intact and was the plan's default; (b) per-slug `exists()` is the same order problem; (c) a single `values_list` whitelist costs a query, a cache-lifetime question that collides with BLOCK 6, **and converts the spec's "match nothing" into a 400** — a spec change disguised as a fix. The naive reading of (d) — plain `EXISTS(... IN ...)` — yields **OR**; that is the spec's ambiguity, and the doc edit must replace "an ad must match *all* of" with a countable `COUNT(feature_id) = <number of distinct selected slugs>`. **Unknown slugs already "match nothing" for free**, because they are absent from `AdFeature` so `COUNT < N` — no whitelist needed. |
| **Q9** | **`RunPython.noop` reverse**, using `0004_backfill_delivered_at`'s *hazard* framing rather than merely "no data to restore". Migration is **`0005`** (BLOCK 8 shifts to `0006`). Dedup rule — the plan states none of this, so it is decided here: **survivor** = greatest `hit_count`, tie → greatest `last_seen`, tie → lowest `pk` (determinism is required for re-entry safety); **`hit_count = Sum`** (the column's whole purpose); **`last_seen = Max`**; **`query` and `source` keep the survivor's own values, untouched** — `query` is the redacted display form that `increment_popular_search` keeps consistent with the key on every write, so borrowing another row's would re-introduce a display/key mismatch, and `source` is provenance, not an aggregate. Pre/post counts emitted by the migration's own log line. **Also constrain `SeedService._seed_popular_searches` to `source=SEED`** in the same block. | The runbook prerequisite is **already satisfied**: `docs/ops/rollback.md` §3 exists with the decision tree *and* a "Data backfill requirement" subsection stating reversing "cannot restore the data" — so Q9(b)'s "needs a phase-12 runbook step" is moot; option (a) plus migration-emitted counts is a strict subset with nothing routed. Rejected: a Python row loop — `0004` establishes the set-based idiom explicitly (*"no row loop, no per-row Python, safe at any table size"*) and the table is unbounded. `last_seen` is `auto_now=True`, a `pre_save` hook, so a set-based `MAX` update writes verbatim and is not silently overridden. **Seed scope is not optional:** `_clean` deletes only `source=SEED` rows, so an unconstrained `update_or_create` matches a user's real production row, **flips its `source` to `SEED`**, and the next `_clean` deletes it. The `UniqueConstraint` does not create this — it converts a duplicate into a **silent steal**. |
| **Q10 / BLOCK 7** | **A `User` `post_save` receiver in `apps/search/signals.py`**, keyed on `{"is_declined"}` only, bumping via `transaction.on_commit(bump_search_cache_version)`. `deletion.py` gets a **zero-line diff**. Answer: **exactly one test** encodes the bypass. | `apps/search/signals.py` already owns the invalidation contract and its wiring is proven live; a new `apps/users/signals.py` would need a `UserConfig.ready()` import or an import *from* `apps/search/signals.py` — i.e. a users-owned module wired by search, which is worse than putting the third receiver beside the two it must be read against. **The two existing field sets are NOT reusable:** `update_fields is None` consults `_SEARCH_RESULT_AFFECTING_STATUSES` and the `else` branch consults `_SEARCH_RELEVANT_FIELDS` — different branches — and the `User` receiver needs **neither**, because `ListingsQuery.build_queryset` contains exactly **one** `User` predicate: `user__is_declined=False`. Keying on `ads_auto_publish`/`consent_*`/`is_deleted` would be unjustified over-bumping. Note the deliberate **asymmetry**: the two `Ad` receivers bump *inline, inside* the transaction; this one must use `on_commit`, because retiring cache keys against an uncommitted predicate is exactly wrong for a consent transition. **`deletion.py` needs no change:** `withdraw_consent` never writes `is_declined`, so there is no double-bump there and the per-ad `transition_to(DELETED)` bumps still cover visibility. `decline_consent` **does** double-bump (receiver + its existing explicit `on_commit`) — harmless on a monotonic counter, and **left untouched** to respect the binding constraint that `deletion.py` is phase 06's most contended file. |

#### 0.6.2 Q1 — the coordinator ruling, and what BLOCK 6 should do

**Q1 is NOT closed and must not be treated as closed.** It is an ownership ruling routed
through the coordinator. The evidence half is answered; the mechanism is **recommended**:
**option (a)**, a durable `timeout=None` version key adopted by all four writers in one
commit, which is the only non-forking choice — phase 13's plan states the split as settled
in three independent places and makes BLOCK 6 a **hard external dependency**
(*"phase 08 owns the contract, phase 13 owns the relationship between the token's lifetime
and the entries it retires"*; *"`docs/architecture/cache-strategy.md` is phase 08 BLOCK 6's
sole owner. Same commit or strictly after; never in parallel."*). Option (b) renegotiates a
settled split; option (c) is this plan's own *"not recommended and not offered as
acceptable"*.

**The four sub-rulings the coordinator must make:**
1. Whether the handbook rewrite's *"phase 13 owns … a freshness token's lifetime against the
   data it retires"* excludes the counter's **durability**. Phase 13 reads it the other way.
   If the coordinator sides with phase 13's literal reading, BLOCK 6 shrinks to a doc
   statement, `SRCH-007` is not a phase-08 implementation item, and the hard `6 → 7` edge
   disappears.
2. That `docs/architecture/cache-strategy.md` is unclaimed in the window — phase 13 says it
   waits, but that must be asserted, not assumed.
3. Whether a new shared helper module in `apps/core` is accepted. It is unreserved. Phase 09
   owns cache-failure policy in `apps/core/utils/cache.py`, so the coordinator must either
   accept the new file, relocate the helper there, or rule for the interim — legitimate
   **only** if all four writers land in one commit.
4. Whether `apps/categories/cache.py::bump_tree_version` sits in phase 07's or phase 09's
   contention window. BLOCK 6 must edit it; leaving three writers behind is forbidden.

**Two facts that make option (a) safe to assert:** no `maxmemory-policy` and no `maxmemory`
appears anywhere in the compose files, so Redis runs the default **`noeviction`** and a
TTL-less integer key is not evicted — four tiny keys, negligible. Name `noeviction`
explicitly as the assumption in the helper's docstring, because that is the statement that
will go stale. And **the fifth consumer needs no code change**: `category_fuzzy.get_active_category_names`
keys on `category:fuzzy_names:{get_tree_version()}:{locale}` and therefore *inherits*
`bump_tree_version` — once that writer is durable the counter never resets to `1`, so a
retired fuzzy key can never become byte-identical again. **The consumer is fixed by the
writer fix**; it becomes a test plus a doc statement, and should be marked read-only in the
task YAML rather than listed as a code target.

#### 0.6.3 BLOCK 1 must split into two commits

- **1a — the queryset rewrite** (the actual `SRCH-001` remedy, closing the spec deviation).
  No gate. Verifiable against `test_features_filter.py` alone. Ships first.
- **1b — the input bound, the 400 mapping, and the doc edit.** Gated on **Q2**'s ceiling —
  **now RESOLVED (2026-10-03, option b: the catalogue invariant plus a guard test)**. The split
  is unchanged; 1b is simply no longer waiting on a decision.

**Q2's evidence is void once 1a lands.** The 20 → 1.31 s / 40 → 7.88 s / 60 → 19.90 s curve
was measured on the **chained** shape. After 1a the join count is O(1) in N, so "any bound
must sit far below 20" no longer binds query cost. Either re-measure against the new shape,
or state the cap as a **secondary parameter-list guard** with that reframing recorded.
**Shipping the cap without 1a fixes nothing structural.** §1's one-commit-per-block rule
must be amended for BLOCK 1.

**Where a DTO `ValidationError` becomes a 4xx.** Only the count cap raises, and **neither
`search()` nor `listings()` catches it today** — so the current behaviour is a **500**, and
the plan's acceptance criterion *"rejection is a 4xx on `/search/` and `/` — not a 500"* is
not achievable without a view-side change the plan's file surface does not mention. Chosen:
add the minimal mapping to both views — `except ValidationError` → bare
`HttpResponseBadRequest`. Not coercion or truncation, which silently change result
semantics. **A bare 400 carries no body, so no new i18n surface** — no `{% trans %}`, no
`ru`/`bs` `msgstr`. Both view files must therefore join BLOCK 1's file surface.

**The `[""]` case, closed by the same validator.** A **bare** `?features=` yields `[""]`,
which is truthy, so today's chain emits `features__slug=''` and returns zero results — while
an **absent** `?features=` correctly short-circuits. One `mode="before"` `field_validator`
that strips empty strings and dedupes, applied before `max_length`, closes both that and
`?features=a&features=a` (which today returns matching ads but would fail an `n=2` count).
The validator must **strip and dedupe only, never filter to a whitelist** — filtering would
change `filters_hash` and break `TestSearchCacheKey::test_feature_slugs_are_order_independent`
and `::test_different_features_produce_different_keys`.

**BLOCK 7's test spec also needs correcting.** The exposure is **directional only**: the
cache stores a serialized `list[int]`, and on a hit the view re-filters over the **live**
queryset, so a newly-*hidden* ad is still excluded by the live predicate. **Only the
"must show" direction is broken**, and `total_count`/`has_results` ride on `len(cached_ids)`
so they are stale in the same direction. The rewritten test therefore needs exactly one
assertion — decline (hidden) → warm the cache → assert absent → `give_consent` → a second
request with **no manual cache clear and no manual bump** → assert present. Warmth must be
**proven**, not assumed: the autouse `_clear_cache_between_tests` fixture guarantees a cold
LocMem cache per test. And the plan's "negative" test is wrong as written — a **bare**
`user.save()` **must** bump under the conservative `None` branch; only a **targeted**
`update_fields` save on an unrelated field is a valid negative.

#### 0.6.4 Corrections to this plan's prose (tree wins)

| # | Correction |
|---|---|
| 1 | **Next free migration is `0005`, not `0003`.** `0003_add_delivered_at` and `0004_backfill_delivered_at` are phase-03 `03-DB-007` and equally off-limits; BLOCK 8 shifts to `0006`. Keep "re-read the directory immediately before generating" — the untracked `apps/users/migrations/0003_logintoken_browser_binding.py` proves the number space moves. |
| 2 | **The column is `last_seen`, not `last_searched_at`.** Every dedup arithmetic rule, `code_hint` and acceptance criterion using that name is wrong. |
| 3 | **`ListingsQuery` is in `apps/ads/services/listings_query.py`** — there is no `apps/search/services/listings_query.py`. (Phase 13's plan asserts a non-existent `apps/categories/services/cache.py`; the real module is `apps/categories/cache.py`.) |
| 4 | **BLOCK 1 closes a spec deviation, not an invention** — `docs/01-spec/search-patterns.md` already prescribes the subquery-over-`AdFeature` shape, and `build_queryset` does the forbidden chain. The spec doc edit is mandatory. |
| 5 | **Q3's bound-test premise is moot.** `test_search_query_count.py` sends `"?q=товар&lang=ru"` — **no `?features=`** — so `feature_slugs == []`, the `if` is False, and any check gated on non-emptiness adds **exactly zero** queries. `_QUERY_BOUND` needs **no amendment** under any candidate shape. |
| 6 | **`TestSearchCacheKey` pins 17 tests, not 14**, plus the `invalidate_search_cache` alias assertion. |
| 7 | **`docs/ops/rollback.md` and `restore.md` already exist** — phase-12-**owned**, not phase-12-pending. `rollback.md` §3 already carries a "Data backfill requirement" subsection. |
| 8 | **The two field sets are used in different branches**: `update_fields is None` → `_SEARCH_RESULT_AFFECTING_STATUSES`; `else` → `_SEARCH_RELEVANT_FIELDS`. The plan's framing ("both in the first branch") is wrong, and BLOCK 7's "do not copy across" must be stated as *different branches, neither set reusable*. |
| 9 | **The `apps/search/signals.py` docstring's "signals fire after commit" claim is false** for `post_save` — both receivers call `bump_search_version()` directly, **inside** the transaction. LOW impact (a rolled-back transaction still bumps a monotonic counter), but BLOCK 6 must not rely on the sentence and BLOCK 7's deliberate `on_commit` makes it actively misleading. Correct it in BLOCK 6's change. |
| 10 | **`docs/02-database/db-indexes.md::Indexes — popular_searches` is missing from BLOCK 5's file surface.** It records the two `db_index=True` columns with no uniqueness note, alongside `db-schema.md::popular_searches`. |
| 11 | **There is no documented 200-char `q` contract.** 200 exists only in `search.py::MAX_SEARCH_QUERY_LENGTH` and two `max_length=200` columns; the only documented contract is autocomplete's (stripped, `;'"\` removed, rejected when <2 or >100). The real collision is **100 (log/redact) vs 100 (autocomplete) vs 200 (view + columns)**. `test_query_exceeding_max_length_returns_200` asserts **only** `status_code == 200`, so a silent 200 → 100 would not be noticed. |
| 12 | **`feature_slugs` needs no whitelist** — unknown slugs already "match nothing" under the counted subquery, for free, by construction. |
| 13 | **BLOCK 1's file surface must add `apps/search/views/search.py` and `apps/ads/views/listings.py`** for the `ValidationError` → bare 400 mapping. |
| 14 | **BLOCK 1 splits into 1a / 1b**; §1's one-commit-per-block rule needs amending for it. |
| 15 | **Q2's latency curve is void after 1a** — it was measured on the chained shape. Re-measure or reclassify the ceiling as a secondary parameter-list guard. |
| 16 | **The dedup's `query`/`source` disposition was never stated** and is now decided (§0.6.1): both keep the survivor's own values. |
| 17 | **BLOCK 5 must add `apps/seed/services/seed_service.py::_seed_popular_searches`**, scoped to `source=SEED` — otherwise a real user's production row is flipped to `SEED` and deleted by the next `_clean`. |
| 18 | **The seed row-count residue is closed** — zero matches for `PopularSearch`/`popular` across `src/backend/apps/seed/tests/`. Remove the flag. |
| 19 | **BLOCK 6's task YAML should not list `category_fuzzy.get_active_category_names` as a code target** — it needs no change; it inherits `bump_tree_version`. Mark read-only/reference. |
| 20 | **BLOCK 7's negative test is mis-specified** — a bare `user.save()` must bump; only a targeted `update_fields` save on an unrelated field is a valid negative. |
| 21 | **BLOCK 7's file surface should drop `give_consent`/`decline_consent`** — under this design `deletion.py` has a **zero-line diff**. Record the phase-06 follow-up instead. |
| 22 | **`cache-strategy.md`'s "Bump function" row contains a typo** (`bump_search_version()` calling `bump_search_version`; should name `bump_search_cache_version`). BLOCK 6 amends that file, so it should be fixed there. |

#### 0.6.5 New findings filed by this pass

- **`08-NEW-01`** — nothing prunes `popular_searches`, and `increment_popular_search` fires
  on **every** `?q=` search including zero-result ones. Routed to the coordinator: pruning
  long-tail rows and stopping zero-result recording has both a product dimension (what
  belongs on the anonymous suggestion surface) and an index dimension (a trigram index is
  phase 13's grading scope). **Not built in BLOCK 5.**
- **`08-NEW-02`** — the dedup **can add rows to the anonymous suggestion surface**, because
  `get_popular_suggestions` is global and cross-user on an unauthenticated endpoint and
  `Sum` can push a merged group across `_MIN_HIT_COUNT = 10` (4+4+4 → one row at 12).
  This is a false negative being fixed rather than a regression, so the floor is **not**
  retuned — but it must be documented, with one test covering both the 9 (still hidden) and
  12 (now eligible) edges. Record the free win too: merging rows narrows the
  `LIKE 'x%'` scan the autocomplete runs on every keystroke.
- **`08-NEW-03`** — `search.py::TestSearchViewInputRobustness::test_homoglyph_and_control_chars_query_returns_200`
  asserts 200 for a URL containing a literal `u200B`, but Django does not decode it — so the
  control character the test claims to exercise never reaches the view. The control-character
  coverage BLOCK 3 adds must not repeat this.

---

### 0.7 Product Owner gate rulings — 2026-10-03

**Authority.** These are Product Owner decisions, dated `2026-10-03`, recorded here so that no
Implementor can re-derive a settled question or re-choose an option. **Every `GATED` row in
§0.5 that maps to a ruling below is now closed.** Where a ruling changed a block's premise, the
block section carries the change; where a ruling created work, it appears in the block's scope
with an acceptance criterion.

| Gate | Ruling (2026-10-03, Product Owner) | Chosen option | Block-level consequence |
|---|---|---|---|
| **Q2** — the `?features=` ceiling | **No hard-coded ceiling.** The bound is the **catalogue invariant** — *"the resolved feature set for any category"*, measured at seed volume, **plus stated headroom** — enforced by a **guard test** that keeps the ceiling honest as the catalogue grows | **(b)** | **BLOCK 1** ships 1a (the correlated subquery) **and** 1b (the invariant + guard test). `MAX_FEATURE_FILTER_SLUGS` is **not** a hard-coded literal; it is derived, or asserted against the catalogue. **Changed premise:** §0.6.3's *"re-measure or reclassify"* is discharged — the ceiling is **reclassified** as a secondary parameter-list guard, and BLOCK 1a's subquery is the real cost control. **Unchanged:** the UI-cap-before-server-cap ordering constraint (BLOCK 1 binding constraint 4) and *"the commit body names the measurement"*. **New obligation:** the guard test |
| **Q4** — NUL / control characters | **Strip invisible/control characters at the input edge and search the cleaned query.** Constraint: **must NOT reuse `sanitize_query_for_log` wholesale** (it truncates to 100 while the view/column contract is 200) | **(a)**, narrowed by the Product Owner | **BLOCK 3** ships a strip at the input edge on **both** endpoints. The **200-char contract and `test_query_exceeding_max_length_returns_200` are preserved** — a binding acceptance criterion, not a preference. **Positive control: a legal query returns byte-identical ads.** C-3 stands (there is no documented 200-char contract) and BLOCK 3's binding constraint 2 is unchanged |
| **Q5** — `SavedSearch.query` redaction | **`SavedSearch.query` is stored REDACTED via `redact_search_query()`, and `query_normalized` is keyed on the redacted form.** One rule for **all** query-persistence paths. Redaction happens **at write**; the stored redacted value is what feeds `websearch_to_tsquery` | **the product rule**, not a plan option | **BLOCK 8's length bound ships exactly as planned** and the redaction question is **CLOSED, not deferred** — BLOCK 8 no longer carries an unanswered question in its commit body. The redaction call itself is **not** phase 08's: it is **phase 09's `09-API-012`** (`save_search`) and the storage-layer `09-VAL-002`. **Propagation obligation on phase 06** (`06-PII-108`, PII policy owner) for the one-rule statement |
| **Q7** — does a ban hide inventory? | **A ban hides inventory.** A banned seller's ads are excluded from the public ad-visibility predicate **across search, category, detail and the media gate** | **(a)** | **BLOCK 14** is no longer a two-option publication: it publishes the **ruling** and the phase-06 handoff. `SRCH-008` moves from *"owner product decision"* to *"owner product decision **taken**"*. **The change must be argued as a moderation decision and must NEVER be bundled into a commit justified as fixing a consent violation** — now a binding constraint, not a warning. **Propagation obligation on phase 06**: the `db-schema.md:61` amendment (phase 06 owns `db-schema.md`, BLOCKS 13/17) |
| **Q7′** — does a ban cover creating/publishing? | **A banned seller cannot create or publish a new ad.** Ban enforcement covers **relisting**, not only login. Any plan recording *"a banned seller can still relist"* as an accepted known gap has that gap **closed**, and the known-gap test becomes a **positive control asserting the block** | **the product rule** | **BLOCK 14** names the write boundary alongside the read boundary, and §5.5 records it as a phase-06 obligation. `SRCH-008`'s scope widens from a visibility term to a **write** boundary; that does **not** give phase 08 the predicate |
| **Q8** — does the single-word narrowing stay a hard filter? | **The narrowing stays a hard filter AND the UI must signal it.** The disjunctive-branch fix is **NOT** chosen. The results page renders a *"showing results for &lt;Category&gt; only — search all categories"* control, plus BLOCK 10's ambiguity fix | **(b)+(c) combined**, explicitly **not** (a) | **BLOCK 11** changes class: it ships **production code** (template + string) plus BLOCK 10's fix, and **no predicate change**. **`SRCH-009` STAYS MEDIUM** — it does **not** drop to LOW and the block is **not** cancelled. **New i18n deliverable**: a new user-visible string with **non-empty `ru` and `bs`**, in the same commit. The hard filter itself is unchanged, so the two `TestSearchViewDescendantCategories` tests **stay green unchanged** — the pinned narrowing is now the specified behaviour |

**Rulings that do not change phase 08's work, recorded so they are not re-litigated.**

- **A truncated result set displays `<SEARCH_CACHE_MAX_HITS>+`.** The true total is never
  claimed when it cannot be computed. **Effect on this plan: none** — phase 08 renders no
  result count at all (`total_count` is never displayed; §6.2). Recorded because BLOCK 12's
  `has_results` derivation, and any future count display, must not contradict it.
- **A new draft replaces the current one** (a Product Owner decision, not a plan default).
  Recorded here only so that no phase-08 finding is re-opened on the grounds that the previous
  behaviour was unspecified. **No phase-08 file records the old behaviour.**

**Technical gates that are NOT Product Owner decisions and therefore remain exactly as they
are.** **Q1** (cache-version-key ownership — a coordinator ruling, §0.6.2), **Q3** (resolved
2026-10-01, option (d)), **Q6** (predicate location — phase 06's), **Q9** (resolved
2026-10-01), **Q10** (answered 2026-10-01). No migration numbering, module placement, commit
sequencing or cache-TTL arithmetic was changed by any 2026-10-03 ruling.

---

## 1. Environment and command contract for the implementor

**This environment is Windows 11 / PowerShell 7.** `make` requires WSL or GNU Make; use
`.\Makefile.ps1 <target>`. `head` / `tail` are unavailable in PowerShell.

### 1.1 Tests are Docker-only — `uv run pytest` on the host always fails

There is no PostgreSQL on `localhost:5432`. Every test run goes through the `test`
service of the `mko-bazuna-test` Compose project. `docker/entrypoint-test.sh` performs
**no** database setup: pytest-django provisions `test_mko_bazuna`, and the
session-autouse fixture in `src/backend/conftest.py` restores the reference data under
advisory lock 111.

```powershell
# Alias, copied once per session
$dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'

# Start the DB if it is not already up
docker ps --filter "name=mko-bazuna-test-db-"
$dc up -d db

# Fast gate (skips the nightly `seed` suite) - the default iteration command
$dc run --rm --env PYTEST_SKIP_MARKERS=seed test

# Targeted run
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="-k test_name" test
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/search/tests/test_search_view.py --tb=short" test

# Full suite (only when the change touches seeding or images)
$dc run --rm test

# Fresh schema - MANDATORY after BLOCK 5's and BLOCK 8's migrations land
$dc run --rm --env PYTEST_OPTS="--create-db --tb=short -n auto --maxprocesses=4 --dist loadgroup" test
```

**Three caveats that will silently produce a wrong result if ignored:**

- `--env-file .env.test` is **required**; without it compose aborts on `${POSTGRES_*?}`
  interpolation. **Never** substitute the `mko-bazuna-dev` project name.
- Setting `PYTEST_OPTS` **replaces** the defaults
  (`--reuse-db --tb=short --durations=10 -n auto --maxprocesses=4 --dist loadgroup`), so a
  targeted run loses xdist parallelism and DB reuse. `PYTEST_OPTS` is also **unquoted** in
  the entrypoint, so each token is word-split: `-k test_name` and bare paths work, quoted
  multi-token values do not. Never use `--override-ini=addopts=` — it strips
  `--import-mode=importlib`, which `pyproject.toml` requires.
- **Concurrent runs collide on the single `test_mko_bazuna` database.** If a gate goes red
  while other phase agents are running, **re-run it serially** before reporting it as a
  defect. Teardown races surface as `FATAL: database "test_mko_bazuna" does not exist`
  and `relation "..." does not exist`, not as product failures.

**`VAL-004` is a binding constraint on this phase's verification work, not a code change.**
Any destructive or DoS-shaped probe — specifically BLOCK 1's crash reproduction
(§0.2.1 row 5) — **must** run on a private `postgres:18-alpine` container on its own
port, with the schema built by `migrate --run-syncdb` + `load_exchange_rates` +
`setup_search_triggers`. **Never** run a DoS-shaped probe against the shared
`mko-bazuna-test` database: taking it into crash recovery while other phases' validators
run makes every concurrently captured red/green result suspect. Prefer
`.\Makefile.ps1 up | test | test-all | test-recreate | test-down` — they manage the project
name and env file for you.

### 1.2 Lint, typecheck, i18n

```powershell
uv run ruff check <path>            # lint
uv run ruff check --fix <path>      # auto-fix, including import sorting (I001)
uv run basedpyright <path>          # typecheck
uv run djlint src/backend/templates/   # only if a template changes
```

**i18n is part of DoD.** Every user-visible string is wrapped in `{% trans %}` /
`{% blocktrans %}` (templates) or `gettext` / `gettext_lazy` (Python). `msgstr` must be
**non-empty** for `ru` and `bs`; `en` may be empty (the msgid is English). `.mo` files
are gitignored and compiled at image build, at container start, and in the CI `i18n` job.
`make makemessages` / `make compilemessages` **do not work** on Windows + Docker Desktop;
use the lightweight `--no-deps --entrypoint ""` form in `.kilo/rules/commands.md` if a
`.po` actually has to change. Run `apps/ads/tests/test_i18n_completeness.py` after any
string change.

**Only BLOCK 11 may add a user-visible string** (and only under option (b) of Q8). If it
does, `src/backend/locale/*/LC_MESSAGES/django.po` is **shared** with phase 14 and phase
03: **append** to the locale files in the same commit as the template change; never run a
wholesale `makemessages` that would discard a concurrent phase's work. An i18n-gate
failure in BLOCK 11 is a **consequence of the fix**, not a regression, and must not be
triaged as one.

### 1.3 Git contract — one implementor, sequential, one commit per block

- **One Implementor at a time.** Never two. Never a background implementor.
- If a block is stopped mid-way, **resume the existing session**; do not launch a new agent.
- Each block is committed separately, explicitly staged: `git add <specific files>` —
  never `git add -A`, never `git add .`.
- Message form, matching the repo style: `"{type}({scope}): {description}"`, e.g.
  `fix(search): bound the features filter list (08-SRCH-001)`,
  `fix(search): make the content version durable (08-SRCH-007)`,
  `docs(architecture): correct the SWR stale-read description (08-SRCH-014)`.
  Every new citation is **cycle-scoped** (`08-SRCH-nnn`), never a bare `SRH-nnn`.
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
  **native PostgreSQL FTS** (no Elasticsearch). **Two processes, one DB:** web (gunicorn
  sync WSGI, HTMX MPA) and bot (aiogram, `django.setup()` + shared ORM).
  **Migrations run exactly once** before both start — a migration that must run in only
  one process is a defect.
- The bot FSM has no built-in PG storage: the ad dialog is persisted as an `Ad` row in
  `DRAFT` via the ORM.
- **Django ORM is the persistence layer.** Pydantic v2 is used **only** at system
  boundaries (bot input, settings schemas, DTOs that already exist at a request edge).
  Business logic lives in `services/`; views stay thin adapters.
- **All schema changes via Django migrations**, including `RunSQL` for FTS DDL (which this
  plan does **not** add — the FTS DDL is already complete). Migration numbers are
  sequential **per app**; **never renumber or edit an existing migration**. Check the
  directory immediately before generating.
- **Fixed values via `StrEnum`** (project rule 10) — never plain strings, dicts or lists.
  In-repo precedent: `LanguageLocale`, `AdSort`, `AdStatus`, `LookupGroupCode`,
  `SearchSuggestionSource`, `AnalyticsEventType`, `AdvisoryLockId`, `SearchCacheKey.V1`.
- **All schema changes** are mirrored in `docs/02-database/db-schema.md`.
- i18n: every user-visible string wrapped; `ru` and `bs` `msgstr` non-empty.
- Small, focused modules and functions. **Composition over inheritance.** Follow existing
  patterns; **no new abstraction without strong justification**; no speculative redesign;
  no scope creep. Prefer the simple, obvious solution (project rule 5).
- **Production code is king.** If a test conflicts with the architecture or the business
  logic, **fix the test** — and say which change and why in the commit body. This plan
  slates **one** test for that treatment (BLOCK 7, `test_give_consent_restores_declined_ads_to_queryset`)
  and **constrains** four more; each block names the test and the justification.
- **Bleaching lint rules forbid blanket `except Exception` around DB calls** (`BLE001`).
  BLOCK 3 must not "fix" the NUL `DataError` by wrapping the analytics call in a blanket
  guard: that converts a correct, loud input-rejection failure into a silent one.
- **Do not pin `CACHES["default"]["TIMEOUT"]`.** Raising or removing the default would
  silently extend the lifetime of *every* cache entry in the system. The defect is that a
  version key is wrongly treated as a cache entry, not that the default is wrong.
- Docs in `docs/` stay in sync.

### 1.5 Test authoring standard for every block

Tests verify **logic and component interaction**, not implementation trivia. No test that
asserts a literal private name, a line number, a template-string substring, a column
count, or the mere presence of a symbol. Assert on **absence of danger** and on
**observable behaviour**.

Good targets for this phase:

- a `?features=` list longer than the ceiling is rejected at the boundary, and a list of
  the same length containing a nonexistent slug is rejected **without** emitting a join
  for it — while AND-semantics over a legal set is unchanged;
- a NUL byte in `q` returns HTTP 200 on `/search/` **and** on `/api/search/autocomplete`,
  while `\x07` and a homoglyph payload still return 200 and a legal query still matches
  the same ads;
- the rendered log line for a zero-result search containing a phone number, an e-mail
  address and a personal name contains **none** of them, and the formatters' output for
  the same record contains none either;
- two active categories sharing a localised display name scope a single-word search to
  **no** branch, rather than to an arbitrary one, while an **unambiguous** name still
  matches;
- a version key written through the shared helper survives past `DEFAULT_TIMEOUT`, and a
  cache key built before the eviction window is **not** byte-identical to one built after;
- a declined seller, a DECLINE restored by `give_consent`, and a seller in an inactive
  category each appear / do not appear identically through the **view** and through the
  queryset, with the cache warm;
- a rotating `X-Forwarded-For` reaches the **same** limiter key as a fixed value, and a
  request with no forwarded headers falls back to `REMOTE_ADDR`;
- a 50 000-character saved-search query is refused, and a 200-character one round-trips
  unchanged.

**Never use a line number as a task target.** Every target is a file plus a **semantic**
anchor: a class, a method, a module-level constant, a named attribute, a function call, a
URL route name, a template block.

Fixtures are canonical in `src/backend/conftest.py`: `seller` (900000001), `user`
(900000002), `category`, `city`, and
`create_test_ad(user, category, city, *, status=AdStatus.PUBLISHED, **kwargs)`.
`src/telegram_bot/tests/conftest.py` redefines these as an **async** `user`; bot tests
cannot import the backend conftest.

**Do not edit `src/backend/conftest.py`.** It is the most contended file in the repository.
If a block appears to need a new fixture, that is a signal the test is over-fitted.

### 1.6 Task shape for every block

Each block's implementor task follows `.ai\tasks\templates\task_template.yaml`: semantic
`targets` with `type` / `name`, `semantic_anchors`, `changes`, `acceptance_criteria`,
`source_reference` / `source_section` / `source_blocks`, and an `extra_context` block
carrying the block's binding constraints verbatim. Verification is **inline** for
low/medium-risk blocks (the Implementor runs `tests_to_run` and checks
`acceptance_criteria`); a **separate Validator task** is required for every **HIGH** or
**CRITICAL** block, for every block that ships a migration, and for every block whose
acceptance depends on a decision the Implementor was told not to make.

---

## 2. Scope decisions table (acceptance contract for execution)

| ID | Disposition | Block | Final severity | One-line reason |
|---|---|---|---|---|
| `SRCH-001` | **implement — Q3 RESOLVED (option d, no whitelist) and Q2 RESOLVED 2026-10-03 (option b).** BLOCK 1 splits 1a/1b. 1b's bound is the **catalogue invariant** — the resolved feature set for any category at seed volume, plus stated headroom — enforced by a guard test, **not** a hard-coded literal. `ListingsQuery.build_queryset` is the real cost control | **1** | **CRITICAL** | Unauthenticated cluster-kill, reproduced end to end. `mem_limit: ${DB_MEM_LIMIT:-1g}` is the shipped **production** cap and no `statement_timeout` exists, so the memory limit is precisely what converts an expensive query into a cluster-wide outage. **Changed premise (2026-10-03):** "any bound must sit far below 20" no longer binds query cost once 1a's correlated subquery makes the join count O(1) in N. **The UI-cap-before-server-cap constraint is unchanged and still binding** |
| `VAL-001` | **implement the documentation half only.** The `statement_timeout` half is `03-DB-004` and belongs to phase 03 | **2** | HIGH (rollout risk) | `DB_MEM_LIMIT` is unset in **every** `.env*` file including `.env.prod.example`, so 1 GB is the shipped default. It is a load-bearing safety parameter, not a tuning knob. `.env.prod.example` is **phase 02's and phase 06's** surface — this block is contention-gated |
| `SRCH-006` | **implement — Q4 RESOLVED 2026-10-03: strip invisible/control characters at the input edge and search the cleaned query, on both endpoints.** **`sanitize_query_for_log` must NOT be reused wholesale**; the 200-char contract and `test_query_exceeding_max_length_returns_200` are preserved. **Not** a blanket `try/except` around the analytics call | **3** | HIGH | Reachable with zero matching ads, unauthenticated and cacheable, and it burns the full query cost before failing. `\x07` returns 200, so the defect is NUL specifically. **The report's "both views already call the sanitiser at the boundary" is false for `search()` (C-5)** |
| `SRCH-002` | **implement the code half only** — one call site. The **policy** half is routed to phase 06 | **4** | HIGH | `redact_search_query` exists, works, and is already called on both **persistence** paths; it is simply not called on the **log** path, and `RedactingJsonFormatter.redact_string` only matches `key=value`, so it cannot rescue a bare quoted value. **The report's cited `docs/08-features/i18n.md` does not exist and has no logging policy to amend (C-1)** |
| `SRCH-003` | **implement — migration first.** Dedup + `UniqueConstraint` in a new `apps/search/migrations/0003_*`, plus the `db-schema.md` correction. Gated on Q9 (reverse shape) | **5** | HIGH | A schema-invariant violation, not a race: `get_or_create`'s atomicity protects the `IntegrityError` path, and with no unique index there is nothing to catch. The report's "misleading `models.py` comment" does not exist (C-4) |
| `SRCH-007` | **implement — gated on Q1.** Declare the contract in `apps/core`, migrate **five** surfaces (four writers + `category_fuzzy`'s inherited consumer), and **amend `docs/architecture/cache-strategy.md` in the same change** | **6** | HIGH | The counter is a correctness mechanism wearing a cache entry's 300 s TTL while the entries it retires live 360 s. **Wider than filed (C-10): five consumers, and the canonical doc prints the defective snippet** |
| `SRCH-005` | **implement — hard dependency on BLOCK 6.** Ship the `post_save` receiver; the `give_consent()` call-site patch is the **fallback, not the destination**. Gated on Q10 (blast radius of the test rewrite) | **7** | HIGH | `give_consent` sets `is_declined=False` and saves; that is its entire invalidation story. **The report's `apps/ads/signals.py` and `apps/users/signals.py` do not exist (C-1)** — the receiver must be created or placed in `apps/search/signals.py` |
| `SRCH-011` + `VAL-006` | **implement — Q5 RESOLVED 2026-10-03: the length bound ships as planned.** Bound at the **model** and at the view edge. `save_search` has **no** DTO today (C-6), so the "DTO constraint" is a boundary that must be created. **The redaction question is CLOSED, not deferred**: `SavedSearch.query` is stored redacted and `query_normalized` is keyed on the redacted form — but the redaction **call** is phase 09's `09-API-012` + `09-VAL-002`, and phase 06 owns the policy | **8** | MEDIUM | The field is unbounded and is fed to `websearch_to_tsquery` on **every** alert evaluation, once per active saved search, on an **ungated** daily job. A view-only cap is the convention-based contract that produced `SRCH-005` |
| `SRCH-010` + `SRCH-013` | **implement as one unit.** One `get_client_ip` in `apps/core` reading `X-Real-IP` → `XFF[-1]` → `REMOTE_ADDR`; one budget table as a `StrEnum`; one 429 shape. Also closes `04-AUT-003` | **9** | MEDIUM | nginx **appends** the peer as the rightmost element, so `split(",")[0]` is attacker-controlled end to end. `X-Real-IP` is overwritten by `proxy_set_header` and cannot be influenced. Two byte-identical copies remain in `users/` and `core/` |
| `VAL-003` | **implement — no decision gate.** Resolve a matched display name to **ids**; an ambiguous name is "no guess". Must close the **exact** path as well as the fuzzy one | **10** | MEDIUM | A first-hit resolution over a non-unique key turns a recall-reducing heuristic into a recall-**destroying** one, invisibly. `Category.name` has no unique constraint and `name_i18n` is free-form JSONB. **The report cited only the fuzzy path (C-9)** |
| `SRCH-009` | **implement — Q8 RESOLVED 2026-10-03: the single-word narrowing STAYS a hard filter and the UI must signal it.** The disjunctive branch (option a) is **NOT** chosen and the hard filter is unchanged. BLOCK 11 ships the *"showing results for &lt;Category&gt; only — search all categories"* control plus BLOCK 10's ambiguity fix, with a **new i18n string (`ru` and `bs` non-empty)**. **Severity stays MEDIUM** — it does not drop to LOW, and the block is not cancelled | **11** | MEDIUM (unchanged) | The behaviour is **specified** (`technical-specification.md:66`), so this is a design question, not a regression. The template renders no "guessed category" signal, and `test_search_view.py::TestSearchViewDescendantCategories` pins the narrowing — **which, after the ruling, those tests are correctly pinning** |
| `SRCH-015` | **implement — the remaining half only.** Derive `has_results` from the rendered rows. **No count display may be added** (C-8) | **12** | LOW (partial) | The count/rows disagreement survives, but `total_count` is never rendered, so the symptom is a blank results area with no empty state. The report's reproduction shape needs the same stale-cache window BLOCKS 6 and 7 close |
| `SRCH-014` + `VAL-005` | **implement — documentation only, one commit.** The three-line SWR docstring; the phase-08 handbook's finding-ID prefix line. The legacy in-source `SRH-` sweep is **phase 03's** and is forbidden here | **13** | LOW | The claim is about **latency on the search hot path**: a reader sizing the cache layer budgets for a non-blocking refresh that does not exist. Do not change the helper — a background task would need a worker this deployment does not run |
| `SRCH-004` | **no implementation in phase 08 — handed to `06-PII-104`.** BLOCK 14 records the handoff, the acceptance criteria and the rollout gate | **14** | HIGH (absorbed) | `06-PII-104` rec. 2 is **verbatim** this finding (C-12). Two commits would create two predicates. The daily digest is live and ungated today |
| `SRCH-008` | **no implementation in phase 08 — owner product decision Q7/Q7′ TAKEN 2026-10-03: a ban hides inventory, and a banned seller cannot create or publish.** BLOCK 14 publishes the ruling, the moderation framing, the write boundary and the documentation obligation | **14** | MEDIUM (absorbed) | Phase 06 ruled a ban is a **moderation** action, not a consent action. Adding `user__is_banned=False` is an owner decision and **must never** be bundled into a commit justified as "fixing a consent violation". **The decision is now taken:** option (a), across search / category / detail / media gate, plus a relist-and-create block. **Propagation obligation: phase 06 owns the `db-schema.md:61` amendment** (BLOCKS 13/17) |
| `SRCH-012` | **closed — no work item.** Restated so it is not silently re-filed | — | LOW (closed) | The four DECLINE assertions were removed by the 2026-09-28 wholesale handbook rewrite (C-11) |
| `VAL-002` | **routed to the coordinator** — a convention to encode, not a file edit | — | MEDIUM (process) | Largely resolved by the same rewrite. What survives is "re-derive product-behaviour assertions from the current spec, and carry a positive control on any FTS/predicate assertion". §6.1 |
| `VAL-004` | **binding constraint on verification, not a code change** | §1.1, §0.2.1 | MEDIUM (process) | The shared `mko-bazuna-test` database is the hazard. BLOCK 1's crash reproduction must run on a private container; a crash mid-validation makes every concurrent red/green result suspect |
| **`Q1` (cache-version-key ownership)** | **GATED** — a coordinator ruling, not a Planner's choice | **6** | — | The 2026-09-28 handbook rewrite moved a freshness token's lifetime against the lifetime of the data it retires to **phase 13**, keeping the stale-read half in phase 08. This decides whether `SRCH-007` is a phase-08 item at all |
| **`Q2` (features ceiling)** | **RESOLVED 2026-10-03 (Product Owner) — option (b): the catalogue invariant, not a hard-coded number** | **1** | — | The ceiling is *"the resolved feature set for any category"* at seed volume plus stated headroom, kept honest by a guard test. BLOCK 1a's correlated subquery is the real cost control; the UI-cap-before-server-cap constraint is unchanged |
| **`Q3` (whitelist query cost)** | **RESOLVED 2026-10-01 — option (d), the spec's correlated subquery, no whitelist** | **1** | — | See §0.6.1. The bound-test premise is moot |
| **`Q5` (`SavedSearch.query` redaction)** | **RESOLVED 2026-10-03 (Product Owner) — stored REDACTED; `query_normalized` keyed on the redacted form. CLOSED, not deferred** | **8** | — | BLOCK 8 ships the bound as planned. The redaction call is phase 09's `09-API-012`/`09-VAL-002`; the policy statement is phase 06's (`06-PII-108`). One rule for all query-persistence paths |
| **`Q8` (does the narrowing stay a hard filter?)** | **RESOLVED 2026-10-03 (Product Owner) — the narrowing stays AND the UI signals it. Option (a) is NOT chosen** | **11** | — | BLOCK 11 ships a new user-visible control with `ru`/`bs` non-empty, plus BLOCK 10's ambiguity fix. **`SRCH-009` stays MEDIUM** |
| **`Q7` / `Q7′` (ban scope)** | **RESOLVED 2026-10-03 (Product Owner) — a ban hides inventory, and a banned seller cannot create or publish a new ad** | **14** | — | BLOCK 14 publishes the ruling and the moderation framing; phase 06 owns the predicate and the `db-schema.md:61` amendment |
| **`Q9` (dedup rollback)** | **GATED, narrow** | **5** | — | Deduplication destroys rows. A `RunPython.noop` reverse plus a documented pre-count, or a mandatory pre-migration dump. Phase 12 owns the runbook |
| **Required Fix 3 (a project-wide input-bounds framework on `BaseInputModel`)** | **declined as a work item** | — | — | `SRCH-001`, `006` and `011` share a cause, but the shared surface is three bounded edits, not a framework. `BaseInputModel` carries only `extra="forbid"`; a general bounds framework is a speculative abstraction with three consumers. Rule 5 applies. §6.2 |

---

## 3. Execution blocks

Fourteen blocks: **twelve implementation blocks, one documentation block (13) and one
decision/handoff block (14) that ships no production behaviour.** **One Implementor,
strictly sequential, one commit per block** (§1.3).

Six blocks (**1**, **3**, **6**, **7**, **8**, **11**) carried a labelled **decision required
before implementation** gate. **The Product Owner closed four of them on 2026-10-03** — Q2
(BLOCK 1), Q4 (BLOCK 3), Q5 (BLOCK 8) and Q8 (BLOCK 11); each block now carries its **resolved**
ruling and an Implementor may **not** re-choose. **The only gate still unanswered is BLOCK 6's
Q1**, a **coordinator** ruling (§0.6.2) — not an owner decision, and not an Implementor's.
BLOCK 7's Q10 was answered 2026-10-01 and its residual is a pre-block grep step, not a gate.

BLOCK 1, BLOCK 5 and BLOCK 7 are prepared in parallel by the Auditor/Researcher while
other blocks run, but the **serial execution order is 1 → 14** (§4.1), because BLOCK 1
is P0 and BLOCK 5's migration numbering constrains BLOCK 8.

### BLOCK 1 — Bound `?features=` at the input boundary (SRCH-001)

| | |
|---|---|
| **Findings owned** | `SRCH-001` (CRITICAL) |
| **Depends on** | **nothing in-plan.** External rollout gate: `03-DB-004` (`statement_timeout`) — §4.4 |
| **Blocks** | the phase-08 rollout; **phase 13's latency grading must assume this landed** |
| **Priority** | **P0 — blocks rollout** |
| **Risk level** | **CRITICAL** — availability defect; behaviour change for any existing consumer |
| **Required agents** | **Auditor · Researcher · Planner · Validator (all four).** The Researcher measures the catalogue and the join curve on a **private** container; the Planner publishes the ceiling; the Validator confirms the bound test and the SLO |

**Why this is first.** It is the only CRITICAL in the phase, it is unauthenticated, and
it is already live. Nothing else in this plan has a curve measured in seconds-to-OOM.

**Decision required before implementation — Q2: the ceiling — RESOLVED 2026-10-03 (Product
Owner)**

**The ruling is option (b): there is NO hard-coded `?features=` ceiling.** The bound is a
**catalogue invariant** — *"the resolved feature set for any category"*, measured at seed
volume, **plus stated headroom** — enforced by a **guard test** that keeps the ceiling honest
as the catalogue grows. The options are retained below for traceability; the Implementor may
**not** re-choose.

| Option | What it is | Consequences |
|---|---|---|
| ~~**(a)**~~ | Adopt the report's **10** | **REJECTED 2026-10-03.** A magic number that drifts as the catalogue grows, and unverified against a real catalogue |
| **(b) — CHOSEN** | Derive the ceiling as a **catalogue invariant** — "the resolved feature set for any category", measured at seed volume, plus headroom | **Gains:** cannot break a legal query; states the bound as a rule rather than a magic number. **Costs:** needs a measurement (Auditor), a stated policy, and a **guard test** so the invariant is enforced rather than merely documented — that guard test is a new, required deliverable of 1b |
| ~~**(c)**~~ | Adopt (a) **and** land a UI cap in the same cycle | **NOT CHOSEN.** Expanding the block into a template change and an i18n string, and the UI is not where the defect is. The UI-cap ordering constraint survives anyway (see below) |

**What the ruling changed in this block.** `MAX_FEATURE_FILTER_SLUGS` is **not** a hard-coded
literal. The constant is either derived from the catalogue at seed volume or asserted against
it, the headroom over the measured maximum is **stated**, and **a guard test** fails if a
category ever resolves more features than the invariant allows. The commit body must record
the measured maximum, the headroom and the invariant.

**What the ruling did NOT change.** BLOCK 1 splits 1a/1b exactly as §0.6.3 requires, BLOCK 1a's
correlated subquery remains the **real cost control** (the join count is O(1) in N once it
lands), and **the UI-cap-before-server-cap ordering constraint is unchanged and still binding**
— if the shipped UI can already emit more than the invariant permits, the block **stops and
reports** (binding constraint 4). "Any bound must sit far below 20" no longer binds *query
cost*; it remains the reason the correlated subquery ships first.

**Decision required before implementation — Q3: does the whitelist break `_QUERY_BOUND`?**

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | Count cap only, no membership check | **Gains:** zero added queries, so `_QUERY_BOUND` and the 2 s SLO are untouched. **Costs:** the report rejects this — any 10 nonexistent slugs is still a 23-join query returning zero rows. It bounds the count, not the cost of nonsense |
| **(b)** | Count cap **plus** a per-slug membership query | **Gains:** full rejection of nonexistent slugs. **Costs:** one query per slug on the hot path; `test_search_query_count.py::test_search_view_query_count_bounded` pins a total captured-SQL bound and will fail. The bound must be amended **explicitly**, in the commit body, with the delta stated — never silently |
| **(c)** | Count cap **plus** a **single** resolved-feature lookup (one query, or a cached `LookupItem` slug set) reused for the membership test | **Gains:** nonexistent slugs are rejected with **no per-slug query growth**. **Costs:** must be proven to cost at most one query, and the cached-slug-set lifetime is a cache question that interacts with BLOCK 6. The most likely answer, but it is a design choice, not a detail |

**The Implementor may not choose.** A 4-agent block with a Validator that must be able to
reject a solution that breaks `_QUERY_BOUND` or the 2 s SLO.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/ads/services/listings_query.py` | `ListingsQueryParams` (the `feature_slugs` field declaration) and `ListingsQuery.build_queryset` (the per-slug filter loop) | The DTO is the **durable** fix; the builder loop is a **read-only reference** unless the whitelist forces a change there |
| `src/backend/apps/ads/tests/test_features_filter.py` | `TestFeaturesFilter` — AND-semantics tests | **Must stay green unchanged.** The bound must not change AND-semantics for a legal set |
| `src/backend/apps/search/tests/test_search_view.py` | `TestSearchViewPublishesFilter` (new cases for the bound) | Existing module |
| `src/backend/apps/ads/tests/` or `apps/search/tests/` (new module if cleaner) | the bound's own regression tests | Do **not** add to `conftest.py` |
| `docs/01-spec/search-patterns.md` | the features AND-semantics section — state the cardinality bound | The spec documents the semantics and **no** limit, which is why the report could not grade this as a deviation. `technical-specification.md` is **phase 06's**; do not edit it for this |

**Binding constraints**

1. **The cap is a boundary declaration, not a per-view convention.** It must be enforceable
   by the DTO so a new endpoint cannot reintroduce an unbounded path. Do **not** introduce
   a general input-bounds framework on `BaseInputModel` (§6.2).
2. **AND-semantics are unchanged.** Selecting N features still requires an ad to carry
   all N.
3. **The ceiling is a catalogue invariant, not a number** (Q2 resolved 2026-10-03). It is
   measured at seed volume, the headroom is **stated**, and a guard test keeps it honest. Do
   not ship a bare `10` or a bare `120`. Once 1a lands the join count is O(1) in N, so the
   cap is a **secondary parameter-list guard** — which is why 1a, not 1b, is the fix.
4. **The UI cap must not land after this one.** This constraint is **unchanged by the
   2026-10-03 ruling.** If the Auditor finds the shipped UI can already emit more than the
   invariant permits, **stop and report** — the cap would expose a separate UI defect and must
   land with or after it.
5. **Do not pin `CACHES["default"]["TIMEOUT"]`, do not set `statement_timeout`** (phase 03),
   and **do not change `DB_MEM_LIMIT`** (BLOCK 2 documents it; changing it is a capacity
   decision).
6. **No DoS-shaped probe on the shared test database** (`VAL-004`). The crash reproduction
   runs on a private container.

**Implementor task**

```yaml
id: task_08_b01_features_bound
title: "Bound the ?features= list at the input boundary (08-SRCH-001)"
priority: critical
depends_on: []
source_reference: ".ai/plans/08-search-fts-remediation.md"
source_section: "BLOCK 1 - Bound ?features= at the input boundary"
source_blocks: ["BLOCK 1"]
description: >
  ListingsQueryParams.feature_slugs is a bare list[str] on a BaseInputModel whose
  only config is extra="forbid", and ListingsQuery.build_queryset emits one
  features__slug=<slug> filter per element - exactly 2N+3 joins. A 60-element list
  costs 19.90 s and the PostgreSQL backend is OOM-killed (cgroup mem_limit
  DB_MEM_LIMIT:-1g, unset in every env file, so 1 GB is the shipped production
  default), taking the whole cluster into crash recovery. There is no
  statement_timeout anywhere in src/ or docker/. Bound the list at the DTO with a
  count cap AND a catalogue-membership check; a count cap alone still lets any N
  nonexistent slugs build an N-join query that returns nothing.
goals:
  - "make an unauthenticated ?features= list unable to exceed a measured-safe query cost"
  - "state the ceiling as a catalogue invariant with stated headroom, kept honest by a guard test"
  - "leave AND-semantics for a legal feature set byte-identical"
  - "stay inside test_search_query_count.py _QUERY_BOUND and the 2 s search SLO"
files:
  - path: "src/backend/apps/ads/services/listings_query.py"
    targets:
      - type: class
        name: ListingsQueryParams
      - type: method
        name: build_queryset
  - path: "src/backend/apps/ads/tests/test_features_filter.py"
    targets:
      - type: module
        name: test_features_filter
  - path: "src/backend/apps/search/tests/test_search_view.py"
    targets:
      - type: class
        name: TestSearchViewPublishesFilter
  - path: "docs/01-spec/search-patterns.md"
    targets:
      - type: module
        name: search_patterns
changes:
  - action: modify_code
    description: >
      Declare a count cap on feature_slugs at the DTO boundary. Q2 is RESOLVED 2026-10-03 as
      option (b): the cap is the CATALOGUE INVARIANT (the resolved feature set for any
      category, measured at seed volume, plus stated headroom) - not a hard-coded literal.
      Q3 is RESOLVED 2026-10-01 as option (d): the spec's correlated subquery over AdFeature
      with AND-semantics and NO catalogue-membership whitelist, so this block adds no
      membership query and _QUERY_BOUND needs no amendment. Add the guard test that keeps the
      invariant honest as the catalogue grows.
    code_hint: |
      # Q2 option (b), RESOLVED 2026-10-03 - the ceiling is an INVARIANT, not a magic number.
      # The value is measured at seed volume and the headroom is stated; the guard test
      # below is what keeps it honest as the catalogue grows.
      MAX_FEATURE_FEATURES_HEADROOM: Final[int] = 4
      MAX_FEATURE_FILTER_SLUGS: Final[int] = <measured max + headroom>  # never a bare guess

      feature_slugs: Annotated[
          list[str], PydanticField(max_length=MAX_FEATURE_FILTER_SLUGS)
      ] = Field(default_factory=list)
acceptance_criteria:
  - "a features list longer than the invariant permits is rejected at the boundary, and the rejection is a 4xx on /search/ and / - not a 500"
  - "the ceiling is derived from the catalogue at seed volume, NOT a hard-coded literal, and the stated headroom over the measured maximum is recorded in the commit body"
  - "a guard test fails if any category's resolved feature set exceeds the ceiling - and that failure is demonstrated"
  - "a list at the ceiling containing a slug that is not in the catalogue is rejected, and no join is emitted for the rejected slug"
  - "a legal feature set of size <= the ceiling returns exactly the ads that carried every selected feature (AND-semantics unchanged)"
  - "test_features_filter.py passes UNCHANGED"
  - "test_search_query_count.py::test_search_view_query_count_bounded passes unchanged - Q3 option (d) adds no query, so no amendment is expected"
  - "test_search_slo.py::test_search_at_seed_volume_meets_slo passes"
  - "the commit body names the Q2 option (b) and the measured catalogue maximum, and the Q3 option (d)"
  - "the UI-cap check was performed and its result recorded in the commit body"
  - "no statement_timeout, no DB_MEM_LIMIT change, no CACHES TIMEOUT change"
tests_to_run:
  - "src/backend/apps/ads/tests/test_features_filter.py"
  - "src/backend/apps/search/tests/test_search_view.py"
  - "src/backend/apps/search/tests/test_search_query_count.py"
  - "src/backend/apps/search/tests/test_search_slo.py"
```

**Tests required**

1. **The bound** — a list one over the invariant is rejected; a list far over it is
   rejected. Assert on the **response**, not on the count of emitted SQL.
2. **The invariant guard** — the guard test asserts every category's resolved feature set is
   within the ceiling at seed volume, and **its failure is demonstrated** by temporarily
   lowering the ceiling. A guard that has never been seen red is not a guard.
3. **The membership check** — a list at the ceiling containing one nonexistent slug is
   rejected, and the number of captured queries does **not** grow by one per rejected slug.
   Under the resolved Q3 option (d) no membership query exists at all, so this asserts the
   free behaviour the counted subquery already provides.
4. **The positive control** — a legal list of size 3 returns exactly the ads carrying all
   three features; a single feature matches. `test_features_filter.py`'s existing cases
   must be untouched.
5. **The SLO** — the seed-volume timing guard stays green; the new bound is a
   pre-database check by construction, so this should be free.

**Risk and rollback**

- *Implementation risk:* **shipping a bare literal instead of the invariant.** Mitigation: Q2
  is **resolved** — the acceptance criteria require the derived value, the stated headroom and
  a guard test that has been demonstrated red. The Implementor may not re-choose.
- *Rollout risk:* **behaviour change for a legal consumer.** Mitigation: binding
  constraint 4 — unchanged by the ruling — the UI-cap check precedes the change, and the block
  stops and reports if the UI can already exceed the invariant.
- *Catalogue growth:* an invariant measured once drifts. Mitigation: the guard test; a category
  that grows past the ceiling fails CI with a named failure, not a 400 at runtime.
- *Performance regression:* a per-slug membership check. Mitigation: Q3 is **resolved as
  option (d)** — the correlated subquery — so no membership query ships at all;
  `test_search_query_count.py` and `test_search_slo.py` are the tripwires and the Validator may
  reject a solution that misses them.
- *Rollback:* a straight revert restores the unbounded path, which re-opens the CRITICAL.
  State that plainly in the commit body; the revert is a mitigation of a *worse* incident,
  not a fix.
- *Cross-phase:* phase 13 grades GIN/trigram effectiveness **at legitimate volume** and
  must assume this fix landed, or it re-measures a phase-08-owned defect.

---

### BLOCK 2 — Declare `DB_MEM_LIMIT` as a load-bearing capacity parameter (VAL-001)

| | |
|---|---|
| **Findings owned** | `VAL-001` (documentation half) |
| **Depends on** | **nothing in-plan.** External contention gate: phase 02 (`CFG-*`) and phase 06 (BLOCK 4) both own `.env*.example` |
| **Blocks** | BLOCK 1's rollout story (the memory cap is the mechanism) |
| **Priority** | P0 — the cap is what converts an expensive query into a cluster-wide outage |
| **Risk level** | **LOW** — documentation and one env line, but the files are the repo's most contended |
| **Required agents** | **Auditor · Planner · Validator.** Researcher not required. Validator required only to confirm no other phase's env work was clobbered |

**What this block is.** Not a knob. The report's mechanism correction is the whole point:
`mem_limit: ${DB_MEM_LIMIT:-1g}` in `docker-compose.yml` is what turned an expensive query
into a cluster kill. A host-tuned PostgreSQL without the cap would have degraded to a slow
request. `DB_MEM_LIMIT` is **unset in every `.env*` file** — `.env.prod`, `.env.dev`,
`.env.test` and all four `.example` files — so **1 GB is the shipped production default**.

**Scope, precisely.** The `statement_timeout` half is `03-DB-004` and is **phase 03's**:
phase 08 must not edit `config/settings/base.py` to add it. This block states the value
the profile expects, names it as a capacity decision, and records the dependency.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `.env.prod.example` | the `DB_MEM_LIMIT` line (new) | **Phase 02 BLOCK 6 and phase 06 BLOCK 4 both touch this file.** Re-read immediately before editing; stop and report on a concurrent change |
| `docs/ops/docker-deployment.md` | the database resource / capacity section | Has **unstaged edits from another agent** in the working tree. Re-read; do not revert |
| `docker-compose.yml` | the `db:` service `mem_limit` and `cpus` entries | **Read-only reference.** Do not change the default |
| `docs/02-database/db-schema.md` or the ops runbook | the timeout dependency note | Phase 12 owns runbooks — record the dependency, do not write the runbook |

**Binding constraints**

1. **Do not change the `${DB_MEM_LIMIT:-1g}` default**, and do not add the variable to
   `ALLOWED_ENV_VARS` or to `secret_validation.py`'s guard count — that is phase 02's
   and phase 06's surface.
2. **Do not add `statement_timeout`.** Record it as `03-DB-004` and as BLOCK 1's rollout
   gate.
3. **Any statement about the memory budget is a capacity statement.** If the block cannot
   state what the profile *expects* without inventing a number, say so in the doc rather
   than guessing.
4. One commit, docs + one env line. No Python, no template, no migration.

**Implementor task**

```yaml
id: task_08_b02_db_mem_limit
title: "Declare DB_MEM_LIMIT as a load-bearing capacity parameter (08-VAL-001)"
priority: high
depends_on: []
source_reference: ".ai/plans/08-search-fts-remediation.md"
source_section: "BLOCK 2 - Declare DB_MEM_LIMIT as a load-bearing capacity parameter"
source_blocks: ["BLOCK 2"]
description: >
  docker-compose.yml bounds the db service with mem_limit: ${DB_MEM_LIMIT:-1g}.
  DB_MEM_LIMIT appears in no .env file, including .env.prod.example, so 1 GB is
  the shipped production default - and it is that cgroup limit, not a planner
  stack overflow, that turned an expensive ?features= query into a backend SIGKILL
  and a cluster crash-recovery. Document it as a safety parameter and a capacity
  decision, and record that statement_timeout (03-DB-004) is the other half.
goals:
  - "make the shipped database memory budget visible and explicit in the production env template"
  - "record that changing it is a capacity decision, not a tuning knob"
  - "record statement_timeout as a phase-03 dependency, without adding it"
files:
  - path: ".env.prod.example"
    targets:
      - type: module
        name: env_prod_example
  - path: "docs/ops/docker-deployment.md"
    targets:
      - type: module
        name: docker_deployment
changes:
  - action: add_docs
    description: >
      Add a DB_MEM_LIMIT entry stating the value the production profile expects and
      that any change to it is a capacity decision. Record the dependency on
      03-DB-004 (statement_timeout) as the bound that protects the residual
      attacker-chosen cost between 1 and the BLOCK 1 ceiling. Do not change the
      compose default and do not add the variable to ALLOWED_ENV_VARS.
acceptance_criteria:
  - ".env.prod.example states the DB memory budget the profile expects"
  - "the text says plainly that changing it is a capacity decision"
  - "the statement_timeout dependency is named as 03-DB-004 and phase 03's"
  - "docker-compose.yml is unchanged"
  - "config/settings/base.py is unchanged"
  - "no other phase's env-template or settings work was reverted"
tests_to_run: []
```

**Tests required** — none. This block ships documentation and one env comment; §8.5
records that blocks 2, 13 and 14 add **no** behavioural tests, and that the absence is
deliberate.

**Risk and rollback**

- *Process risk (medium):* `.env.prod.example` is phase 02's and phase 06's surface, and
  `.env.prod.example` is gated in both directions by
  `config/settings/tests/test_env_allowlist.py`. Re-read immediately before editing; stage
  explicitly; never `git add .`; if the file already has another agent's uncommitted
  changes, **stop and report**.
- *Documentation risk:* a stated number that is not the real one. Mitigation: if the
  profile's expected value cannot be derived from the repository, the block says so rather
  than inventing it.
- *Rollback:* a straight revert. No data, no schema.
- *Cross-phase:* phase 12 owns the **runbook** framing ("what happens on a crash recovery,
  what is the DB memory budget"). This block states the parameter; it does not write the
  runbook.

---

### BLOCK 3 — Reject NUL and control characters at both search input edges (SRCH-006)

| | |
|---|---|
| **Findings owned** | `SRCH-006` (HIGH) |
| **Depends on** | **nothing in-plan.** Soft edge **3 → 4** (log sink consumes the normalised value) |
| **Blocks** | BLOCK 4 (the log line must not normalise differently from the analysed value) |
| **Priority** | **P0** |
| **Risk level** | **HIGH** — two endpoints, two different failing call sites, and a collision with an existing length contract |
| **Required agents** | **Auditor · Researcher · Planner · Validator (all four).** The shape decision is Q4; the Validator confirms both endpoints and the surviving siblings |

**What actually happens, and what the report got wrong about the fix (C-5).**

| | `/search/` | `/api/search/autocomplete` |
|---|---|---|
| Read | `query = (request.GET.get("q") or "").strip()[:200]` — slicing does not remove `\x00` | `query = sanitize_autocomplete_query(request.GET.get("q", ""))` — strips only `[;'"\`]`, **not** control characters |
| First parameterised use | `SearchQuery(query, search_type="websearch")` inside the cache `producer()` | `PopularSearch.query_normalized__startswith` → a `LIKE` with a NUL-bound parameter |
| Raiser | `increment_popular_search` → `get_or_create(query_normalized=…)`, **unguarded** | `get_popular_suggestions` → the `LIKE`, unguarded |

`_record_search_analytics` is called **unconditionally** inside `if query:`, **before**
`_resolve_search_count`, so the 500 is reachable with zero matching ads and it burns the
full query cost first. `record_event` is already guarded inside the analytics service —
the raiser is the **second** call site.

**Decision required before implementation — Q4: strip, reject, or normalise — RESOLVED
2026-10-03 (Product Owner)**

**The ruling: strip invisible/control characters at the input edge and search the CLEANED
query.** The options are retained below for traceability; the Implementor may **not** re-choose.

| Option | What it is | Consequences |
|---|---|---|
| **(a) — CHOSEN, with a Product-Owner constraint** | **Strip** control characters at the input edge | **Adopted.** A legal query still returns results; `\x07` already returns 200, so stripping is consistent with the existing loose control-char contract. **The Product Owner's constraint: `sanitize_query_for_log` must NOT be reused wholesale** — it truncates to 100 while the view/column contract is 200 |
| ~~**(b)**~~ | **Reject** — a control-character query is treated as empty | **NOT CHOSEN.** The owner accepts a mutated query, so the existing `test_homoglyph_and_control_chars_query_returns_200` shape survives |
| ~~**(c)**~~ | **New shared normaliser** that does not truncate | **NOT CHOSEN as the product decision, but its *shape* is what (a) requires here.** Option (a) is only safe because it does not drag `_MAX_QUERY_LENGTH` in with it |

**The 200-vs-100 collision is now closed by ruling, not by argument.** The **200-character
`q` contract and `test_query_exceeding_max_length_returns_200` are preserved** — the strip
must not shorten a legal query. Reusing `sanitize_query_for_log` end-to-end is therefore
**forbidden by the ruling**, and binding constraint 2 stands. C-3 also stands: there is **no
documented 200-char contract** — 200 lives only in `MAX_SEARCH_QUERY_LENGTH` and two columns —
so the acceptance criteria assert it as a **contract** rather than inherit it as documentation.

**The positive control is mandatory.** A legal query must return **byte-identical ads** before
and after the change. That assertion is what distinguishes a strip from a bug.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/core/utils/sanitize.py` | `sanitize_query_for_log` (`_CONTROL_CHAR_PATTERN`, `_MAX_QUERY_LENGTH`), `sanitize_autocomplete_query` | Shared helper home. **Do not change `_MAX_QUERY_LENGTH`** — BLOCK 4 depends on the log path's 100-char truncation, and changing it is a separate decision |
| `src/backend/apps/search/views/search.py` | `search` — the `q` read and the boundary before `if query:` | **A new boundary call is required here; there is none today (C-5)** |
| `src/backend/apps/search/views/autocomplete.py` | `autocomplete` — the `q` read via `sanitize_autocomplete_query` | The existing call gains control-character handling |
| `src/backend/apps/search/tests/test_search_view.py` | `TestSearchViewInputRobustness` | The sibling guards (`test_sql_injection_query_returns_200`, `test_query_exceeding_max_length_returns_200`, `test_homoglyph_and_control_chars_query_returns_200`) must stay green, or the rewrite must be justified in the commit body |

**Binding constraints**

1. **Do not wrap `_record_search_analytics` in a blanket `try/except`.** That converts a
   correct, loud input-rejection failure into a silent one, and `BLE001` exists to stop
   exactly that shape. The fix belongs at the input edge.
2. **Do not change the 200-char `q` contract** and do not change `_MAX_QUERY_LENGTH`. **This is
   the Product Owner's explicit constraint** (2026-10-03): `sanitize_query_for_log` must not be
   reused wholesale, because its 100-character truncation would shorten `q`.
3. **Both endpoints must be covered.** A fix on `/search/` alone leaves the
   `LIKE`-parameter path reachable.
4. `\x07` must continue to return 200 (it does today) — this is the control.
5. `MAX_SEARCH_QUERY_LENGTH`'s comment already records that a previous instance of this
   class of bug was fixed by **length, not charset**. The block must not rely on length
   alone.

**Implementor task**

```yaml
id: task_08_b03_nul_rejection
title: "Reject NUL and control characters at both search input edges (08-SRCH-006)"
priority: high
depends_on: []
source_reference: ".ai/plans/08-search-fts-remediation.md"
source_section: "BLOCK 3 - Reject NUL and control characters at both search input edges"
source_blocks: ["BLOCK 3"]
description: >
  A NUL byte in q reaches psycopg unencoded and raises DataError: PostgreSQL text
  fields cannot contain NUL (0x00) bytes. It is reachable on /search/ (via
  increment_popular_search, the SECOND call site - record_event is already guarded
  inside the analytics service) and on /api/search/autocomplete (via the
  query_normalized__startswith LIKE). _record_search_analytics runs
  unconditionally before _resolve_search_count, so the 500 needs no matching ads
  and burns the full query cost first. Control character 0x07 returns 200 today,
  so the defect is NUL specifically. Note that search() does NOT currently call
  sanitize_query_for_log at the boundary - it calls it only on the zero-result log
  line, after the failure - so a new call site is required.
goals:
  - "make a control character in q impossible to reach the driver on either endpoint"
  - "keep the 200-char q contract and the 100-char log-sanitiser contract intact and separate"
  - "search the cleaned query, and prove a legal query's results are byte-identical"
  - "keep the loudness of an input-rejection failure"
files:
  - path: "src/backend/apps/core/utils/sanitize.py"
    targets:
      - type: function
        name: sanitize_query_for_log
      - type: function
        name: sanitize_autocomplete_query
  - path: "src/backend/apps/search/views/search.py"
    targets:
      - type: function
        name: search
  - path: "src/backend/apps/search/views/autocomplete.py"
    targets:
      - type: function
        name: autocomplete
  - path: "src/backend/apps/search/tests/test_search_view.py"
    targets:
      - type: class
        name: TestSearchViewInputRobustness
changes:
  - action: modify_code
    description: >
      Q4 is RESOLVED 2026-10-03: STRIP invisible/control characters at the input edge and
      search the cleaned query, on BOTH endpoints. Do NOT reuse sanitize_query_for_log
      wholesale - it truncates to 100 while the view/column contract is 200; reuse its
      control-character pattern or add a small focused helper that does not truncate. Call it
      from search() before `if query:` and from autocomplete()'s existing read. Do NOT wrap
      the analytics call in try/except, and do NOT change _MAX_QUERY_LENGTH.
acceptance_criteria:
  - "GET /search/?q=<NUL> returns 200 with no DataError and with no analytics row written from the NUL value"
  - "GET /api/search/autocomplete?q=ab<NUL>cd returns 200 with no DataError"
  - "GET /search/?q=<0x07>abc still returns 200"
  - "a legal query returns byte-identical ads before and after the change - this is the Product Owner's mandated positive control"
  - "the 200-character q contract is preserved: a q longer than MAX_SEARCH_QUERY_LENGTH is still truncated to the same length, and the log line is still truncated at 100"
  - "sanitize_query_for_log is NOT reused wholesale on the search input edge - its 100-character truncation is not allowed to reach q"
  - "test_sql_injection_query_returns_200, test_query_exceeding_max_length_returns_200 and test_homoglyph_and_control_chars_query_returns_200 are green UNCHANGED - the ruling is designed so no test rewrite is required, and a rewrite must be justified in the commit body under production-code-is-king"
  - "no blanket try/except was added around any DB call"
tests_to_run:
  - "src/backend/apps/search/tests/test_search_view.py"
  - "src/backend/apps/search/tests/test_search_query_count.py"
```

**Tests required**

1. **Per endpoint** — a NUL-bearing `q` returns 200 and writes no `DataError`. Two tests,
   one per endpoint, because the two paths fail at different call sites.
2. **The control** — `\x07` still returns 200, and the homoglyph/script payload still
   returns 200.
3. **The legal query** — an ordinary query returns the same result set as before the
   change. This is the assertion that catches option (a)'s silent mutation.
4. **The two length contracts** — `q` truncation at `MAX_SEARCH_QUERY_LENGTH` and log
   truncation at `_MAX_QUERY_LENGTH` are asserted **separately**, because conflating them
   is the trap (C-3).

**Risk and rollback**

- *The real risk:* an implementer "simplifies" by wrapping `_record_search_analytics` in
  `try/except`. That converts a loud input rejection into a silent one and the analytics
  silently stops recording. Binding constraint 1, and `BLE001` is the tripwire.
- *Regression risk:* the strip changes what the user searched for. **This is accepted by
  ruling** (Q4, 2026-10-03). Test 3 — a legal query returns byte-identical ads — is the
  control that keeps it honest; if it fails, the implementation is wrong and the block
  returns rather than amending the ruling.
- *Regression risk:* reusing `sanitize_query_for_log` wholesale shortens `q` from 200 to
  100. **Forbidden by the Product Owner's ruling**, not merely discouraged. Binding
  constraint 2; `test_query_exceeding_max_length_returns_200` is the tripwire.
- *Rollback:* a straight revert. No schema, no data.
- *Cross-phase:* none blocking. `sanitize.py` is a shared `apps/core` helper — no other
  phase claims it, but re-read it, since phase 06 BLOCK 5 touches the masking helpers
  nearby (§5.3).

---

### BLOCK 4 — Redact the search log line (SRCH-002, code half only)

| | |
|---|---|
| **Findings owned** | `SRCH-002` (HIGH) — the **code** half only |
| **Depends on** | **BLOCK 3** (soft, correctness) — see the edge rationale in §4.2 |
| **Blocks** | nothing in-plan; the **policy** half is routed to phase 06 (§5.6) |
| **Priority** | **P0** |
| **Risk level** | **MEDIUM** — a one-site change, but the wrong helper is a silent behaviour change |
| **Required agents** | **Auditor · Planner · Validator.** Researcher not required. Validator required to confirm the formatted production line, not just the call |

**What is confirmed and what is not.**

- `search()` logs, on the zero-result branch only:
  `logger.info("Empty search results for query '%s'", sanitize_query_for_log(query))`.
- `sanitize_query_for_log` strips `[\x00-\x1f\x7f-\x9f]` and truncates to **100** (C-3).
  **It is not a redactor.**
- `redact_search_query` masks phone, e-mail and multi-word capitalised names, is
  **length-preserving by design** (a documented invariant: never lengthen, so the
  `max_length=200` columns stay safe), and truncates to the same 100. It **is** called on
  the two **persistence** paths (`increment_popular_search`, `record_search_history`).
  It is **not** called on the log path.
- `RedactingJsonFormatter.format` builds `{timestamp, level, message, logger}` and applies
  `redact_string`, whose pattern only matches
  `(password|token|secret|api[_-]?key|authorization|key)\s*[:=]\s*\S+`. **A bare quoted
  value inside a message is not touched** — the formatter is not a mitigation for this
  sink.
- **The report's call-site sweep is a one-site change, not a sweep:** there is exactly one
  `sanitize_query_for_log` call site in the repository, and it is this line.

**Why HIGH and not CRITICAL, and why still P0.** The sink is an operator JSONL log, not an
event store and not an unauthorised reader — the same reasoning that correctly de-rated
phase 06's `PII-102`. It is P0 at HIGH for three aggravating factors: it is **always-on**;
its volume is unbounded and attacker-influenced; and **a third party can cause a specific
person's phone number to be written into a durable log** by getting them to click
`/search/?q=%2B382…`. No `withdraw_consent()` path reaches a log line.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/search/views/search.py` | `search` — the `logger.info` on the zero-result branch | The **only** production change |
| `src/backend/apps/core/utils/sanitize.py` | `redact_search_query`, `sanitize_query_for_log` | **Read-only reference.** Confirm the never-lengthen invariant still holds for the log path; do not change `_MAX_QUERY_LENGTH` (BLOCK 3 depends on it) |
| `src/backend/apps/core/utils/json_logging.py` | `RedactingJsonFormatter.redact_string` | **Read-only reference.** Records *why* the formatter is not a control here |
| `src/backend/apps/search/tests/test_search_view.py` or a new `apps/search/tests/` module | the log-sink regression test | `test_redact_search_query.py` covers the **persistence** paths only; it does **not** cover the log sink |
| `docs/01-spec/i18n-spec.md` | — | **The report's `docs/08-features/i18n.md` does not exist and this document has no logging policy to amend (C-1).** Not a target |

**Binding constraints**

1. **Call `redact_search_query` on the log argument only.** Do not replace the value used
   for the search, the cache key, the analytics, or `SearchQuery`.
2. Lazy `%s` formatting — pass the redacted value as the argument, never f-string it into
   the format string.
3. **Do not add a global logging `Filter`.** A naming-convention guard cannot see a value
   passed positionally, and its negative ROI at this scale is exactly the report's
   declined advisory. The project-level *policy* belongs to phase 06 (§6.2).
4. **Do not change `redact_search_query`** — only the call site. The two persistence call
   sites and `test_redact_search_query.py` must be untouched.
5. No new user-visible string; no i18n work in this block.

**Implementor task**

```yaml
id: task_08_b04_search_log_redaction
title: "Redact the search query on the zero-result log line (08-SRCH-002)"
priority: high
depends_on: [task_08_b03_nul_rejection]
source_reference: ".ai/plans/08-search-fts-remediation.md"
source_section: "BLOCK 4 - Redact the search log line"
source_blocks: ["BLOCK 4"]
description: >
  search() logs "Empty search results for query '%s'" with
  sanitize_query_for_log(query), which strips control characters and truncates to
  100 but does NOT redact. A phone number, an e-mail address and a personal name
  therefore reach the production JSONL sink. redact_search_query already exists,
  is length-preserving by design and is already called on both persistence paths;
  it is simply not called here. RedactingJsonFormatter cannot rescue this: its
  redact_string pattern only matches key=value pairs, not a bare quoted value.
  This call site is the only sanitize_query_for_log call site in the repository.
goals:
  - "stop writing raw search input to the production log"
  - "change the log argument only - not the search, the cache key, the analytics or the tsquery"
  - "leave the two persistence redaction call sites and redact_search_query itself untouched"
files:
  - path: "src/backend/apps/search/views/search.py"
    targets:
      - type: function
        name: search
  - path: "src/backend/apps/search/tests/test_search_view.py"
    targets:
      - type: module
        name: test_search_view
changes:
  - action: modify_code
    description: >
      Pass redact_search_query(query) instead of sanitize_query_for_log(query) as
      the %s argument of the zero-result logger.info, keeping lazy formatting. Add
      one regression test that captures the LogRecord and asserts the formatted
      message contains neither a phone number nor an e-mail address nor a
      multi-word capitalised name.
    code_hint: |
      logger.info(
          "Empty search results for query '%s'",
          redact_search_query(query),
      )
acceptance_criteria:
  - "the formatted log message for a zero-result search containing a phone number contains no digits of that number"
  - "the same is true for an e-mail address and for a multi-word capitalised personal name"
  - "a search containing none of those still logs the query, so triage is not silently lost"
  - "the search result set, the cache key, the analytics rows and the tsquery are byte-identical to before the change"
  - "increment_popular_search and record_search_history still call redact_search_query and are unchanged"
  - "sanitize.py, _MAX_QUERY_LENGTH and json_logging.py are unchanged"
  - "no logging Filter and no print() were added"
tests_to_run:
  - "src/backend/apps/search/tests/test_search_view.py"
  - "src/backend/apps/search/tests/test_redact_search_query.py"
```

**Tests required**

1. **The sink** — a zero-result search with a phone number, an e-mail and a name in `q`:
   capture the `LogRecord`, render it through `RedactingJsonFormatter`, and assert none
   of the three survives. Rendering through the real formatter is the point — asserting on
   the call argument alone would not have caught the defect.
2. **The negative case** — a query with no identifiers still logs. A blanket "log nothing"
   change would pass test 1 and destroy triage capability.
3. **The persistence paths are untouched** — `test_redact_search_query.py` green unchanged.

**Risk and rollback**

- *Regression risk:* an implementer redacts the value **before** it is used for the
  search, changing what is searched and what is cached. Binding constraint 1; the
  result-set assertion is the tripwire.
- *Observability risk:* the report's advisory notes `sanitize_query_for_log` iterates
  `char.isalpha()` and drops non-alphabetic characters, so Cyrillic and Montenegrin input
  collapses to its letters. **Replacing the helper changes what operators see.** That
  trade is the accepted cost of the fix and must be stated in the commit body; the
  character-handling question itself is **phase 14's** (§5.6).
- *Rollback:* a straight revert. No data, no schema.
- *Cross-phase:* the **policy** half — "never log raw user input; log a normalised,
  redacted, truncated form", enforced by a shared formatter or filter — is the **third**
  instance of phase 06's "no declared logging policy" root cause and belongs to **phase 06**
  (`06-PII-102` validated rec. 5). A point fix in `apps/search` alone will not close the
  class, and phase 08 must not build the filter (§6.2).

---

### BLOCK 5 — Make `popular_searches.query_normalized` unique (SRCH-003)

| | |
|---|---|
| **Findings owned** | `SRCH-003` (HIGH) |
| **Depends on** | **nothing in-plan.** Serialisation edge **5 → 8** (migration numbering) |
| **Blocks** | BLOCK 8 (it allocates the next migration number) |
| **Priority** | **P0** |
| **Risk level** | **HIGH** — a data migration that destroys rows, not reversible by `migrate back` |
| **Required agents** | **Auditor · Researcher · Planner · Validator (all four).** The Researcher settles the reverse shape (Q9); the Validator confirms the migration, the dedup arithmetic and the post-migration `IntegrityError` |

**Why a migration leads.** This is a **schema-invariant violation**, not a race.
`get_or_create`'s atomicity protects the `IntegrityError` path; with no unique index
there is nothing for it to catch, so two concurrent writers both succeed and the table is
permanently corrupted. Once a duplicate exists, `get_or_create`'s internal `.get()`
re-raises `MultipleObjectsReturned`, and the raise is not caught — so `GET /search/?q=…`
returns a hard 500 on an unauthenticated endpoint. Remediation must **lead** with a
migration, not with locking.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/search/models.py` | `PopularSearch` — `query_normalized` and `Meta` | `Meta` declares `db_table` only today. Add the constraint; **do not** add the "misleading index comment" the report asks for — **it does not exist (C-4)** |
| `src/backend/apps/search/migrations/0003_*.py` | the new migration: a data migration that deduplicates, then `AddConstraint` with `name="uq_popular_search_query_normalized"` | **The next free number is `0003`** — re-check the directory immediately before generating (phase 06 BLOCK 7 may have taken it) |
| `docs/02-database/db-schema.md` | the `popular_searches.query_normalized` row — state the uniqueness | **Phase 06 owns this file (BLOCKS 13, 17).** Route or re-read; do not clobber |
| `src/backend/apps/search/tests/` | a new `IntegrityError` guard test | The report names this as a real gap and the cheapest guard against regression |

**Decision required before implementation — Q9: the reverse shape**

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | `RunPython` forward dedup + `AddConstraint`; reverse = `RunPython.noop` with a comment | **Gains:** a `migrate back` cannot resurrect the removed duplicates and pretend the operation was reversible. **Costs:** the data is gone with no recovery path from the migration itself |
| **(b)** | (a) **plus** a documented pre-migration count the operator must record | **Gains:** an operator has the numbers to reason about a restore before committing. **Costs:** requires a runbook step, which is **phase 12's** to write. This block states the requirement; it does not write the runbook |
| **(c)** | (a) **plus** a mandatory pre-migration dump | **Gains:** full recoverability. **Costs:** an operational precondition the test and CI path cannot satisfy; it will be skipped everywhere it is not enforced, which is the worst outcome |

**The Implementor may not choose** between (a) and whether (b)/(c) is *required*; (a) is
mandatory in all three. The block is **irreversible by design** and its commit body must
say so before the block runs, not after.

**Dedup semantics, stated so the Implementor does not invent them:** group by
`query_normalized`; keep the row with the **greatest** `hit_count`; the survivor's
`hit_count` becomes the **sum** over its group so no popularity is lost; `last_searched_at`
becomes the **maximum** over its group. Log the pre- and post-dedup row counts through
`logger = logging.getLogger(__name__)` — **never `print()`**.

**Binding constraints**

1. **Never edit or renumber `0001` or `0002`.** They are applied.
2. **Dedup inside the same migration, before the constraint.** The constraint cannot be
   created otherwise.
3. **The reverse is a deliberate `noop`** with a comment stating that the data is gone.
4. **No `print()`.** Log the counts.
5. `db-schema.md` is **phase 06's** file. If a concurrent edit is present, stop and report.
6. The migration must be **idempotent in effect** when run twice (it will not be, because
   `AddConstraint` is one-shot — but the data step must not corrupt anything if re-entered).

**Implementor task**

```yaml
id: task_08_b03_popular_search_unique
title: "Enforce uniqueness on popular_searches.query_normalized (08-SRCH-003)"
priority: high
depends_on: []
source_reference: ".ai/plans/08-search-fts-remediation.md"
source_section: "BLOCK 5 - Make popular_searches.query_normalized unique"
source_blocks: ["BLOCK 5"]
description: >
  PopularSearch.query_normalized is CharField(max_length=200, db_index=True) with
  no unique constraint; Meta declares db_table only, and pg_indexes shows
  popular_searches_pkey as the only unique index. increment_popular_search uses
  get_or_create, whose internal .get() re-raises MultipleObjectsReturned as soon as
  a duplicate exists, and the raise is unguarded on the anonymous search path. This
  is a schema-invariant violation, not a race. Add a data migration that
  deduplicates (keep the greatest hit_count, sum hit_count, take the maximum
  last_searched_at per group) and then add
  UniqueConstraint(fields=["query_normalized"], name="uq_popular_search_query_normalized").
  The reverse is a deliberate noop because dedup destroys rows.
goals:
  - "make the database enforce the invariant the code already assumes"
  - "lose no hit_count and no recency when merging duplicate groups"
  - "keep the migration honest about being irreversible"
files:
  - path: "src/backend/apps/search/models.py"
    targets:
      - type: class
        name: PopularSearch
  - path: "src/backend/apps/search/migrations/0003_*.py"
    targets:
      - type: module
        name: "0003_deduplicate_and_unique_popular_search"
  - path: "src/backend/apps/search/tests/"
    targets:
      - type: module
        name: test_popular_search_integrity
  - path: "docs/02-database/db-schema.md"
    targets:
      - type: module
        name: db_schema
changes:
  - action: add_migration
    description: >
      One migration: RunPython(forward=dedup, reverse=noop) then AddConstraint with
      name "uq_popular_search_query_normalized". The forward step groups by
      query_normalized, keeps the row with the greatest hit_count, sets the
      survivor's hit_count to the sum over its group and last_searched_at to the
      maximum, then deletes the rest. Log the pre- and post-dedup counts via
      logging.getLogger(__name__). The reverse is RunPython.noop with a comment
      stating that the merged rows do not return.
acceptance_criteria:
  - "0001 and 0002 are byte-identical to before"
  - "after the migration, no two PopularSearch rows share query_normalized"
  - "merging two rows with hit_count 3 and 5 yields one row with hit_count 8"
  - "merging two rows keeps the later last_searched_at"
  - "inserting two rows with the same query_normalized raises IntegrityError"
  - "migrate back runs cleanly and does not recreate the removed rows"
  - "makemigrations --check is clean after the model change"
  - "the commit body states the pre- and post-dedup row counts and that the data is not recoverable by a revert"
tests_to_run:
  - "src/backend/apps/search/tests/test_popular_search_integrity.py"
  - "src/backend/apps/search/tests/test_search_view.py"
```

**Tests required**

1. **The invariant** — two rows with the same `query_normalized` raise `IntegrityError`.
   This is the guard the report names and the suite has never had.
2. **The dedup arithmetic** — a group of 3 duplicates merges to `sum(hit_count)` and
   `max(last_searched_at)`. Assert on the values, not on the row count alone.
3. **The path** — after two concurrent `increment_popular_search` calls with the same
   normalised query, `GET /search/?q=…` returns 200 rather than 500. This is the
   user-visible outcome and it is worth one test.
4. **Post-migration** — `--create-db` runs the migration on an empty table without error.

**Risk and rollback**

- ***Irreversible* (the block's defining risk):*** dedup destroys rows. Mitigation: the
  commit body states the counts and the irreversibility **before** the block is run; the
  reverse is a `noop` by design; the Validator independently recounts.
- *Migration risk:* the number `0003` is taken by phase 06 BLOCK 7. Re-check the
  directory immediately before generating; never renumber.
- *Correctness risk:* a naive `MAX(hit_count)` merge silently loses popularity. The
  arithmetic is stated in the task and asserted in test 2.
- *Rollback:* a revert restores the **code**, not the data. Say so.
- *Cross-phase:* `db-schema.md` is phase 06's (§5.3); `apps/search/migrations/` is shared
  with phase 06 BLOCK 7 and phase 08's own BLOCK 8.

---

### BLOCK 6 — One durable cache-version contract (SRCH-007)

| | |
|---|---|
| **Findings owned** | `SRCH-007` (HIGH) |
| **Depends on** | **nothing in-plan.** Hard edge **6 → 7** (BLOCK 7 must ship with it) |
| **Blocks** | BLOCK 7, BLOCK 12; the **`IMMEDIATE_ALERTS_ENABLED` and stale-read** story |
| **Priority** | **P0** — without it, every version bump in the system is silently undone after 300 s |
| **Risk level** | **HIGH** — the widest surface in the plan, and its ownership is contested |
| **Required agents** | **Auditor · Researcher · Planner · Validator (all four).** The Researcher re-derives the consumer set; the Validator confirms the durability regression test and that the doc no longer teaches the defect |

**The defect, precisely.** `CACHES["default"]` declares no `TIMEOUT`, so a `cache.set`
without an explicit timeout inherits `DEFAULT_TIMEOUT = 300`. All four version writers
have the identical shape — `try: cache.incr(KEY) / except ValueError: cache.set(KEY, 1)` —
so the counter self-evicts at 300 s, the next bump re-issues `1`, and any key built with
`:1:` in it becomes **byte-identical** to a key built an hour earlier. The entries the
counter retires are written by the SWR helper with `timeout = ttl + stale_ttl = 300 + 60 =
360`: **the counter evicts first and the data outlives it.**

**Wider than filed (C-10) — five surfaces, not four writers, plus a canonising doc.**

| Surface | Role | What happens today |
|---|---|---|
| `apps/search/services/cache.py::bump_search_version` (`search:content_version`) | writer | `cache.set(KEY, 1)`, no timeout |
| `apps/categories/cache.py::bump_tree_version` (`category:tree_version`) | writer | `cache.set(KEY, 1)`, no timeout |
| `apps/categories/services/lookup_resolution.py::bump_lookup_resolve_version` (`lookup:resolve_version`) | writer | `cache.set(KEY, 1)`, no timeout |
| `apps/lookups/services/cache_service.py::bump_lookup_version` (`lookup:content_version`) | writer | `cache.set(KEY, 1)`, no timeout |
| `apps/search/services/category_fuzzy.py::get_active_category_names` | **consumer** | Builds `category:fuzzy_names:{get_tree_version()}:{locale}` and inherits the eviction **without owning the key**. On a counter reset the fuzzy-name list becomes reachable again with a **stale category list** — the same failure class that produced the validator's own false refutation of `SRCH-009` |
| `docs/architecture/cache-strategy.md` — "Version-Bump Mechanism" | **documentation** | Prints the defective snippet as **the project pattern**. A code-only fix leaves the doc teaching the defect |

**Decision required before implementation — Q1: who owns the version key's lifetime**

The 2026-09-28 handbook rewrite changed this. The validated report assigns the
counter-vs-data lifetime inequality wholly to phase 08. The rewritten phase-08 handbook
**block 10** now says: *"Phase 08 owns the cached result-set itself: staleness, whether a
stored entry may still serve a buyer-facing result set, and whether a content change
propagates to every stored form. **Phase 13 owns the key's composition and lifetime** …
and **a freshness/version token's lifetime against the lifetime of the data it retires**."*
**This is a coordinator ruling, not a Planner's choice, and it decides the block's shape.**

| Option | What phase 08 ships | Consequences |
|---|---|---|
| **(a)** | **The stale-read half only.** Declare the "durable monotonic version key" contract in `apps/core` with `timeout=None`, migrate all four writers, fix the fifth consumer's key composition, and amend `cache-strategy.md`. The **lifetime inequality** (`entry 360` vs `counter 300`) is recorded as **phase 13 block 10's** | **Gains:** matches the current handbook verbatim; phase 13 can then grade key composition with the contract already declared. **Costs:** a version key that no longer self-evicts makes the 360 s entry lifetime *more* wrong, not less — the entry outlives its token forever until a bump, which is fine, but phase 13 must own the tuning. `SRCH-005`'s exploitability is fixed, because the counter no longer resets to `1` |
| **(b)** | **Both halves.** The contract, the four writers, the fifth consumer, the doc **and** the entry-vs-counter lifetime relation (a `statement` about `SEARCH_CACHE_TTL` + `SEARCH_CACHE_STALE_TTL` vs the version key) | **Gains:** the incoherence is closed inside the phase that found it. **Costs:** it edges into phase 13's grading scope, and the report explicitly made **no** latency claim. Risk of a phase-13 fork |
| **(c)** | **The contract and the four writers only.** The fifth consumer and the doc amendment are deferred | **Gains:** the smallest correct change. **Costs:** a code-only fix leaves `docs/architecture/cache-strategy.md` teaching the defect, and leaves `category_fuzzy` inheriting an eviction that is now *harder* to notice. **Not recommended and not offered as acceptable** |

**The Implementor may not choose.** Q1 is a coordinator ruling; the block's task YAML
carries `decision reference required` and the chosen option must be named in the commit
body.

**Binding constraints**

1. **Declare the contract once**, in `apps/core`, and adopt it at all four writers. The
   report's fallback — four `timeout=None` edits with a comment — is a legitimate
   **interim** shape *only if* all four land in the same commit. Leaving three behind is
   forbidden.
2. **Do not pin `CACHES["default"]["TIMEOUT"]`.** That would silently extend the lifetime
   of *every* cache entry in the system.
3. **`docs/architecture/cache-strategy.md` is phase 08's to edit** and must be amended
   **in the same change**. Its "Existing Patterns" 1–3 enumerate the four keys.
4. **The fifth consumer must be reasoned about explicitly.** Fixing only the four writers
   is not sufficient; the block states in its commit body what the fuzzy-name key does
   under each Q1 option.
5. **Do not change the cache key's shape.** `test_search_cache.py::TestSearchCacheKey` pins
   14 tests including `test_key_has_versioned_prefix` (`search:v1`, a `StrEnum` member
   `SearchCacheKey.V1`) and `test_key_embeds_content_version`. A key-shape change is a
   **breaking** change to all 14.
6. **Do not delete `invalidate_search_cache`** — `test_search_cache.py` asserts the alias.
7. `apps/search/signals.py` is BLOCK 7's destination; this block may re-read it but must
   not add a `User` receiver.

**Implementor task**

```yaml
id: task_08_b06_cache_version_contract
title: "Declare and adopt one durable cache-version key contract (08-SRCH-007)"
priority: high
depends_on: []
source_reference: ".ai/plans/08-search-fts-remediation.md"
source_section: "BLOCK 6 - One durable cache-version contract"
source_blocks: ["BLOCK 6"]
description: >
  CACHES["default"] declares no TIMEOUT, so a cache.set without an explicit timeout
  inherits Django's DEFAULT_TIMEOUT of 300. All four version writers use
  try: cache.incr(KEY) / except ValueError: cache.set(KEY, 1), so every version
  counter self-evicts after 300 s and the next bump re-issues 1 - making an earlier
  cache key byte-identical to a later one. The entries the counter retires are
  written with timeout = SEARCH_CACHE_TTL + SEARCH_CACHE_STALE_TTL = 360, so the
  counter evicts first and the data outlives it. A fifth consumer,
  category_fuzzy.get_active_category_names, inherits the eviction through
  get_tree_version() without owning the key, and
  docs/architecture/cache-strategy.md prints the defective snippet as the project
  pattern.
goals:
  - "make a version key a declared invariant rather than a per-call-site convention"
  - "adopt the contract at all four writers in one change - never leave three behind"
  - "stop the documentation teaching the defect"
  - "not change the cache key's shape"
files:
  - path: "src/backend/apps/core/"
    targets:
      - type: module
        name: cache_version
  - path: "src/backend/apps/search/services/cache.py"
    targets:
      - type: function
        name: bump_search_version
  - path: "src/backend/apps/categories/cache.py"
    targets:
      - type: function
        name: bump_tree_version
  - path: "src/backend/apps/categories/services/lookup_resolution.py"
    targets:
      - type: function
        name: bump_lookup_resolve_version
  - path: "src/backend/apps/lookups/services/cache_service.py"
    targets:
      - type: function
        name: bump_lookup_version
  - path: "src/backend/apps/search/services/category_fuzzy.py"
    targets:
      - type: function
        name: get_active_category_names
  - path: "docs/architecture/cache-strategy.md"
    targets:
      - type: module
        name: cache_strategy
changes:
  - action: add_code
    description: >
      Add one small focused helper in apps/core that implements the declared
      contract - "a cache-version key is durable, not a cache entry" - and set the
      fallback write with timeout=None. Migrate all four writers to it in the SAME
      commit. The helper must document the invariant, and the module docstring must
      say why the key must not be treated as a cache entry. Do NOT pin
      CACHES["default"]["TIMEOUT"]. Do NOT change the cache key shape. Amend
      docs/architecture/cache-strategy.md so its Version-Bump Mechanism section shows
      the new contract and its "Existing Patterns" 1-3 list the four keys correctly.
    code_hint: |
      def bump_version_key(key: str) -> None:
          """Increment a durable monotonic cache-version key.

          A version key is a correctness mechanism, not a cache entry: it must
          outlive the entries it retires, so it is written with timeout=None. A
          bounded TTL makes the counter reset to 1 and silently resurrects a
          byte-identical cache key.
          """
          try:
              cache.incr(key)
          except ValueError:
              cache.set(key, 1, timeout=None)
acceptance_criteria:
  - "a version key written through the helper survives past DEFAULT_TIMEOUT and is still readable afterwards"
  - "a cache key built before an eviction window is NOT byte-identical to one built after a bump"
  - "all four writers use the helper - a grep finds no remaining bare cache.set(KEY, 1) without a timeout"
  - "CACHES[\"default\"] has no TIMEOUT key added or changed"
  - "test_search_cache.py passes UNCHANGED, including all 14 TestSearchCacheKey cases and the invalidate_search_cache alias assertion"
  - "the commit body states the Q1 option chosen and what the fifth consumer does under it"
  - "docs/architecture/cache-strategy.md no longer shows the unbounded cache.set(KEY, 1) snippet as the pattern"
  - "no latency claim is made and no index or query-plan work was done"
tests_to_run:
  - "src/backend/apps/search/tests/test_search_cache.py"
  - "src/backend/apps/core/tests/test_sweep_archive.py"
  - "src/backend/apps/search/tests/test_search_fuzzy.py"
  - "src/backend/apps/search/tests/test_search_view.py"
```

**Tests required**

1. **The durability invariant** — write a version key through the helper, advance the
   clock past `DEFAULT_TIMEOUT`, and assert the key is still readable. **Patch the clock
   or assert on the stored expiry; never sleep 300 s in the suite.** This test **fails
   today** and is the block's most important deliverable — the report names it explicitly
   because the existing suite uses `LocMemCache` and would otherwise pass unchanged.
2. **The key-identity property** — a key built before the eviction window differs from one
   built after a bump. This is the *user-visible* property: a stale result list must not
   be served against a post-change predicate.
3. **The regression set** — `test_search_cache.py` green **unchanged**, including the SWR
   state machine, single-flight, max-size guard, and the publish/edit/archive/withdrawal
   bump tests; `test_sweep_archive.py`'s version assertion green; `test_search_fuzzy.py`
   green.
4. **All four writers** — one assertion per writer that its key does not carry a bounded
   TTL. This is what makes "never leave three behind" testable rather than a promise.

**Risk and rollback**

- *Ownership risk (the block's defining risk):* shipping phase 13's work, or declining
  phase 08's. Mitigation: Q1 is a labelled coordinator gate; the commit body names the
  option.
- *Scope risk:* the helper becomes a speculative abstraction. Mitigation: four call sites
  and a fifth consumer is a de-duplication, not a new concept (project rule 5); the block
  adds exactly one function and no framework.
- *Regression risk:* a key-shape change breaks 14 tests. Binding constraint 5; the tests
  are the tripwire.
- *Performance risk:* a durable key never evicts, so the cache backend accumulates four
  long-lived keys. Negligible at this cardinality; stated, not optimised.
- *Rollback:* a straight revert. **Note that the revert restores the defect**, and a
  reverted deployment then behaves as it does today.
- *Cross-phase:* phase 13 grades key composition and the token-vs-data lifetime relation
  (handbook block 10). Phase 12 owns cache-related runbook content.

---

### BLOCK 7 — Account-state changes invalidate the search cache (SRCH-005)

| | |
|---|---|
| **Findings owned** | `SRCH-005` (HIGH) |
| **Depends on** | **BLOCK 6** (hard) — see §4.2 |
| **Blocks** | BLOCK 12; the restored-ad visibility contract |
| **Priority** | **P0** |
| **Risk level** | **HIGH** — it must rewrite a test that currently documents the defect as intended |
| **Required agents** | **Auditor · Researcher · Planner · Validator (all four).** Researcher answers Q10; the Validator confirms the rewritten test goes through the view and that the production behaviour is unchanged elsewhere |

**Why BLOCK 6 is a hard predecessor.** The report's own correction is the key: the missing
bump at the call site is real, but **the reason it is exploitable is `SRCH-007`.** The
counter evicts at 300 s, re-issues `1`, and a stale key is served — so fixing the call site
alone leaves a second, independent path to the same user-visible outcome. **Ship together
or the restoration bug survives in a harder-to-reproduce form.**

**What the tree actually has (C-1).**

- `decline_consent` sets `is_declined=True`, saves with `update_fields`, then
  `transaction.on_commit(bump_search_cache_version)`. **Correct.**
- `give_consent` sets `consent_given_at`, `is_declined=False`, `ads_auto_publish=True`,
  `consent_revoked_at=None` and saves with `update_fields`. **No bump, no comment
  acknowledging the omission.** Its entire invalidation story is that one `save()`.
- `apps/search/signals.py` registers `post_save` on **`Ad`** and `m2m_changed` on
  `Ad.features.through`. **There is no `post_save` receiver on `User` anywhere in the
  repository, and `apps/users/signals.py` does not exist.**

**The two test facts that constrain this block.**

1. `test_search_view.py::TestSearchViewDeclinedConsent::test_give_consent_restores_declined_ads_to_queryset`
   **documents the defect as intended.** Its docstring says: *"give_consent intentionally
   does not bump the search cache, so a warm cache entry persists until TTL expiry"*, and
   it asserts against `ListingsQuery.build_queryset` **directly**, deliberately bypassing
   the view and the cache. **It must be rewritten to go through the view.** Project rule:
   production code is king — fix the test, and say why in the commit body.
2. `test_search_cache.py::TestSearchCacheInvalidationOnWithdrawal::test_withdrawal_hides_ads_and_bumps_version`
   is the correct comparison case and the template for the new test.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/search/signals.py` | add a `post_save` receiver on `User` for the search-affecting fields | **The module that owns the invalidation contract.** The report's destination modules (`apps/ads/signals.py`, `apps/users/signals.py`) **do not exist** |
| `src/backend/apps/users/services/deletion.py` | `give_consent` and `decline_consent` | **Fallback shape only** (see the decision below). `decline_consent` is the pattern to follow |
| `src/backend/apps/search/tests/test_search_view.py` | `TestSearchViewDeclinedConsent::test_give_consent_restores_declined_ads_to_queryset` | **Rewrite, do not delete.** The `withdraw_consent` sibling is the positive control |
| `src/backend/apps/search/tests/test_search_cache.py` | `TestSearchCacheInvalidationOnWithdrawal` (add the `give_consent` case) | Existing module |
| `src/backend/apps/users/tests/test_deletion.py` | the `decline_consent` version-bump test | The template the new test follows |

**Decision required before implementation — the receiver's destination and shape**

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | **One `post_save` receiver on `User`** in `apps/search/signals.py` (or a new `apps/users/signals.py` that `apps/search` imports), keyed on the consent fields | **Gains:** converts "user account state changed, the search cache is now stale" from a **per-call-site convention** into a **declared invariant** — the same structural move that makes `06-VAL-003`'s predicate reusable. This is the report's preferred shape. **Costs:** the receiver's `update_fields` shape differs from `bump_search_cache_on_ad_change`'s, which inspects `kwargs["update_fields"]` against `_SEARCH_RELEVANT_FIELDS` and, on a full save, checks `instance.status` membership in `_SEARCH_RESULT_AFFECTING_STATUSES`. It **cannot** be copy-pasted from the `Ad` receiver. A new module also needs a wiring check: who imports `apps/users/signals.py`? If nothing does, the receiver silently never runs — that is the single most likely failure of this option |
| **(b)** | **Add `transaction.on_commit(bump_search_cache_version)` to `give_consent()`**, next to the one in `decline_consent` | **Gains:** the smallest correct change; exactly the shape already proven in the same function; no wiring risk. **Costs:** leaves the class of defect open — a third call site added next year forgets again. The report is explicit that this is "the fallback, not the destination" |
| **(c)** | Both: the receiver **and** the explicit call | **Gains:** belt and braces. **Costs:** two bumps for one transition, which is harmless for a monotonic counter but is duplicated intent and a second thing to maintain. Not recommended under rule 5 |

**The Implementor may not choose** between (a) and (b). The report names (a) as the
destination and (b) as the fallback; if the Implementor selects (a), the wiring
(`apps/users/signals.py` import path or `AppConfig.ready`) **must** be part of the same
commit and must be proven by a test that the receiver actually fires.

**Pre-block step, not a gate — Q10.** The Auditor greps `apps/search/tests/` and
`apps/ads/tests/` for any other test that adopts the same "bypass the view because the
cache is stale" pattern and reports the count before the block starts. If there are more
than the one named test, the block's test-rewrite scope grows and the Validator must see
every one of them.

**Binding constraints**

1. **The new test must go through the view**, not through `build_queryset`. The whole
   defect is invisible to a queryset-level assertion.
2. **Do not bend the production behaviour to the old test.** Project rule 2. The
   docstring asserting "intentionally does not bump the search cache" is the defect, not
   a specification.
3. **`on_commit`, not an inline bump.** The predicate must not change before the row
   commits.
4. **Do not touch `AccountStateMiddleware`, `can_login` or `can_publish_ad`.** A
   queryset-level or manager-level change here is phase 06 / phase 15's, and the bot's
   `_resolve_user` resolves on `chat_id`.
5. **No default-manager filter.** Forbidden by phase 06 and fatal to the bot middleware.
6. **Do not add a re-derivation mechanism for the FTS vectors** (`VAL-009` is overstated;
   §0.2.1). Nothing in this block writes `Ad` columns.
7. `deletion.py` is phase 06's most contended file (its BLOCKS 9, 10, 11, 13 all edit it).
   Re-read before touching it; under option (b) the diff is three lines.

**Implementor task**

```yaml
id: task_08_b05_consent_restoration_invalidation
title: "Invalidate the search cache when a user's consent state is restored (08-SRCH-005)"
priority: high
depends_on: [task_08_b06_cache_version_contract]
source_reference: ".ai/plans/08-search-fts-remediation.md"
source_section: "BLOCK 7 - Account-state changes invalidate the search cache"
source_blocks: ["BLOCK 7"]
description: >
  decline_consent sets is_declined=True and calls
  transaction.on_commit(bump_search_cache_version). give_consent sets is_declined=False
  and saves - with no bump, no receiver and no comment. A restored seller is
  therefore still invisible to the cached search path until the version counter
  happens to move. The ad-side receivers live in apps/search/signals.py; the
  report's cited apps/ads/signals.py and apps/users/signals.py do NOT exist, and
  there is no post_save receiver on User anywhere in the repository. The existing
  test test_give_consent_restores_declined_ads_to_queryset documents the defect as
  intended and asserts against ListingsQuery.build_queryset directly, bypassing the
  view and the cache; it must be rewritten to go through the view.
goals:
  - "make a consent restoration visible through the search view without a manual bump"
  - "turn per-call-site convention into a declared invariant where the chosen option allows"
  - "keep the fix invisible to every other test"
files:
  - path: "src/backend/apps/search/signals.py"
    targets:
      - type: function
        name: bump_search_cache_on_ad_change
  - path: "src/backend/apps/users/services/deletion.py"
    targets:
      - type: function
        name: give_consent
  - path: "src/backend/apps/search/tests/test_search_view.py"
    targets:
      - type: class
        name: TestSearchViewDeclinedConsent
  - path: "src/backend/apps/search/tests/test_search_cache.py"
    targets:
      - type: class
        name: TestSearchCacheInvalidationOnWithdrawal
changes:
  - action: modify_code
    description: >
      Apply the decision option the Planner recorded. Under option (a), add a
      post_save receiver on User for the consent-affecting fields that calls
      transaction.on_commit(bump_search_cache_version), place it in
      apps/search/signals.py (or create apps/users/signals.py and prove its wiring
      in the same commit), and state the invariant in the module docstring. Under
      option (b), add the on_commit bump to give_consent() next to the existing one
      in decline_consent(). The receiver's update_fields handling is NOT the Ad
      receiver's shape - do not copy _SEARCH_RESULT_AFFECTING_STATUSES logic across.
    code_hint: |
      @receiver(post_save, sender=User)
      def bump_search_cache_on_account_state_change(sender, instance, update_fields=None, **kwargs):
          """A user's account state changed; the cached search result set is now stale.

          This is a declared invariant, not a per-call-site convention: without it,
          a consent restoration leaves the seller's ads invisible to the cached
          search path.
          """
          if update_fields is not None and not ({"is_declined", "ads_auto_publish", "consent_given_at"} & set(update_fields)):
              return
          transaction.on_commit(bump_search_cache_version)
  - action: modify_test
    description: >
      Rewrite test_give_consent_restores_declined_ads_to_queryset so it drives the
      VIEW with a warm cache: decline, load the search page (populating the cache),
      give consent back, and assert the ad is visible with no manual bump. Remove
      the docstring claim that give_consent intentionally does not bump the search
      cache, and state in the new docstring why the assertion moved from the
      queryset to the view.
acceptance_criteria:
  - "after decline -> load the search page -> give_consent, the ad is visible through the view on the next request, with the cache warm and no manual bump"
  - "the rewritten test no longer asserts against ListingsQuery.build_queryset directly, and its docstring no longer claims the omission is intentional"
  - "get_search_version() increases across a give_consent transition"
  - "withdraw_consent still bumps (the existing sibling test is green unchanged)"
  - "decline_consent is unchanged and still bumps"
  - "the new receiver, if option (a), actually fires - proven by a test, not by inspection of the wiring"
  - "AccountStateMiddleware, can_login, can_publish_ad and every User queryset are unchanged; no default-manager filter was added"
  - "no FTS trigger, vector column or setup_search_triggers change"
tests_to_run:
  - "src/backend/apps/search/tests/test_search_view.py"
  - "src/backend/apps/search/tests/test_search_cache.py"
  - "src/backend/apps/users/tests/test_deletion.py"
  - "src/backend/apps/users/tests/test_account_state.py"
```

**Tests required**

1. **The restoration** — the four-step sequence above, driven through the **view**. This is
   the test the report asks for and the one that fails today.
2. **The counter** — `get_search_version()` strictly increases across the transition. It
   is the cheap assertion that catches a receiver that never fires (the most likely
   failure of option (a)).
3. **The negative** — a `User.save()` that touches a field unrelated to search state does
   **not** bump. Without this, the receiver is a performance regression on every user
   save.
4. **The regression set** — `test_search_cache.py` green unchanged; the decline path
   green unchanged; `test_deletion.py` green; `test_account_state.py` green, because a
   declined user still cannot log in and can still publish.

**Risk and rollback**

- *The defining risk:* a receiver that is **wired but never imported** — the fix looks
  present and the defect survives. Test 2 is the control; the Validator must confirm the
  receiver fires, not that it exists.
- *Correctness risk:* over-bumping on every `User.save()`. Test 3 is the control.
- *Process risk:* the test rewrite is mistaken for "changing the test to fit the code".
  Mitigation: binding constraint 2, the commit body must name the test and state that the
  old docstring documented the defect; §8.3 checks it.
- *Contention risk:* `deletion.py` is phase 06's most contended file; `signals.py` is
  phase 06's BLOCK 5/7 neighbourhood. Re-read before editing; never revert a concurrent
  change.
- *Rollback:* a straight revert, which restores today's behaviour. The rewritten test
  reverts with it.
- *Cross-phase:* phase 06 BLOCK 5 edits the same `signals.py` neighbourhood for the
  immediate-alert log masking; coordinate via the coordinator (§5.3).

---

### BLOCK 8 — Bound `SavedSearch.query` at the model and the boundary (SRCH-011, VAL-006)

| | |
|---|---|
| **Findings owned** | `SRCH-011` (MEDIUM) + `VAL-006` (MEDIUM) |
| **Depends on** | **BLOCK 5** (hard) — migration numbering in `apps/search/migrations/` |
| **Blocks** | nothing in-plan; bounds the daily alert job's input surface |
| **Priority** | **P1** |
| **Risk level** | **MEDIUM** — a schema change plus a boundary that does not exist yet (C-6) |
| **Required agents** | **Auditor · Researcher · Planner · Validator.** Validator required because a **migration** ships. **Q5 is answered (2026-10-03) — no Researcher input is owed to this block any more** |

**Why the model bound, not just the view.** `SavedSearch.query` is
`models.TextField(blank=True, null=True)` with no `max_length`, and the view reads
`request.POST` directly. A view-only cap is exactly the convention-based contract that
produced `SRCH-005`. `send_alerts._collect_alerts` iterates **every**
`SavedSearch(is_active=True)` on an **ungated** schedule and builds one `SearchQuery(...,
search_type="websearch")` per row — so the bound must hold for the **bot, the admin, a
management command and any future API**, not only for the POST handler. Per-search and
per-user caps already exist (`[:10]`, `_DIGEST_AD_LIMIT`), so **count** is not the exposure;
**unbounded query text evaluated N times on a schedule** is.

**The bound's reference points already in the schema:** `PopularSearch.query_normalized`
and `SearchHistory.query_normalized` are both `max_length=200`. Note the asymmetry the
Implementor must respect: `query_normalized` is the **dedup key** and holds the
*un-redacted* normalised string while `query` holds the redacted one — the redaction
helper's **never-lengthen** invariant is what keeps 200 safe. `SavedSearch.query` is
user-supplied and, today, un-redacted at write time.

**Q5 RESOLVED 2026-10-03 (Product Owner) — redaction as well as a bound**

**The ruling: `SavedSearch.query` is stored REDACTED via `redact_search_query()`, and
`query_normalized` is keyed on the redacted form.** One rule for **all** query-persistence
paths. Redaction happens **at write**, and the stored redacted value is what feeds
`websearch_to_tsquery`. **The question is CLOSED, not deferred** — BLOCK 8 no longer carries
an unanswered question in its commit body, and the Implementor may **not** re-choose.

**What this block ships, unchanged.** The **length bound at the model and at the view edge**,
exactly as planned. BLOCK 8's scope is **not** widened.

**What this block does NOT ship, and why.** The **redaction call** is **phase 09's
`09-API-012`** — the `save_search` view write path, which is in phase 09's BLOCK 13 — plus the
storage-layer `09-VAL-002` for `query_normalized`. The **policy statement** ("one rule for all
query-persistence paths") is **phase 06's** (`06-PII-108`, the PII policy owner). Both are
recorded as propagation obligations (§5.5).

**The interaction BLOCK 8 must respect.** Under the ruling, a redacted saved-search query can
differ from what the seller typed, so a saved search whose text contained a digit run may match
differently after phase 09/06 land. BLOCK 8's bound is orthogonal and must not encode any
expectation about redaction; its tests assert the **bound**, not the stored content's shape.
Phase 08 BLOCK 8 and phase 09 BLOCK 13 both touch `apps/search/views/save_search.py` — that
file must be **re-read immediately before either block edits it** (§5.3).

The options are retained below for traceability.

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | **Bound only.** `max_length` on the model plus a boundary check in the view | **What BLOCK 8 ships.** The redaction is owned by phase 09 / phase 06 under the ruling |
| **(b)** | Bound **and** redact `SavedSearch.query` at write time | **Adopted by the Product Owner — and assigned to phase 09's `09-API-012`**, not to phase 08. Changing what a saved search matches, and a data change on existing rows, are real costs; they are now decided, not deferred |
| **(c)** | Bound now; redaction is a **phase 06** work item | **Superseded.** The decision is made; the work is routed to a named owner rather than left open |

**The Implementor may not choose** whether to redact, and may not add the redaction call to this
block. BLOCK 8's floor is the bound, and the bound ships either way.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/search/models.py` | `SavedSearch.query` | The **model** bound. `apps/search/models.py` is also BLOCK 5's file — BLOCK 5 lands first |
| `src/backend/apps/search/views/save_search.py` | `save_search` — the `query` read and the `SavedSearch.objects.create` call | **There is no DTO today (C-6).** Under this block's minimal shape the bound is a boundary check at the read, and a DTO is *not* required — creating one is a scope decision the Implementor may not take alone |
| `src/backend/apps/search/migrations/0004_*.py` (or the next free number) | the `max_length` alteration | **After BLOCK 5's `0003`.** Re-check the directory; phase 06 BLOCK 7 may have taken a number |
| `src/backend/apps/search/tests/test_saved_search_create.py` | the negative (over-cap) case | The happy path must stay green unchanged |
| `docs/02-database/db-schema.md` | the `saved_searches.query` row | **Phase 06's file.** Re-read or route |

**Binding constraints**

1. **The bound is at the model as well as the view.** A view-only cap is the convention
   that produced `SRCH-005`.
2. **Over-cap behaviour must be a 4xx, not a 500 and not a silent truncation.** Decide
   which and state it; a silent truncation would create a saved search the seller did not
   ask for.
3. **Do not introduce a DTO on this path without a recorded decision** (C-6). The minimal
   shape is a bound at the read plus the model field. If the Implementor believes a DTO is
   required, that is a scope expansion and must return to the Planner.
4. **Do not change `find_matching_ads` or `send_alerts`.** `alert_query.py` is phase 06
   BLOCKS 5/7 and phase 03 BLOCK 9 (§5.3).
5. **Do not make a latency claim.** Quantifying the alert-path cost is **phase 13's**
   scope; the report makes none and neither may this block.
6. **The 200-character reference is a reference, not a decision.** If the Implementor
   chooses a different number, the commit body must give the reason.

**Implementor task**

```yaml
id: task_08_b08_saved_search_query_bound
title: "Bound SavedSearch.query at the model and the save-search boundary (08-SRCH-011, 08-VAL-006)"
priority: medium
depends_on: [task_08_b03_popular_search_unique]
source_reference: ".ai/plans/08-search-fts-remediation.md"
source_section: "BLOCK 8 - Bound SavedSearch.query at the model and the boundary"
source_blocks: ["BLOCK 8"]
description: >
  SavedSearch.query is an unbounded TextField and save_search reads request.POST
  directly - there is no DTO on this path at all. A 50,000-character query
  round-trips intact, and send_alerts._collect_alerts iterates every active
  SavedSearch on an ungated daily schedule, building one websearch_to_tsquery per
  row. Bound the field at the MODEL as well as at the view boundary so the scheduler
  cannot be reached with an unbounded value regardless of which writer populated
  it.
goals:
  - "make SavedSearch.query bounded on every writer, including the bot, the admin and management commands"
  - "refuse an over-cap query loudly rather than truncating or 500-ing"
  - "make no latency claim about the alert path"
files:
  - path: "src/backend/apps/search/models.py"
    targets:
      - type: class
        name: SavedSearch
  - path: "src/backend/apps/search/views/save_search.py"
    targets:
      - type: function
        name: save_search
  - path: "src/backend/apps/search/migrations/0004_*.py"
    targets:
      - type: module
        name: "0004_bound_saved_search_query"
  - path: "src/backend/apps/search/tests/test_saved_search_create.py"
    targets:
      - type: module
        name: test_saved_search_create
changes:
  - action: add_migration
    description: >
      Add max_length to SavedSearch.query, with a migration after BLOCK 5's 0003
      (re-check the directory - phase 06 BLOCK 7 may have taken a number). Add the
      matching boundary check at the read in save_search, returning a 4xx on an
      over-cap query. Do not introduce a Pydantic DTO on this path without a
      recorded decision. Do NOT add redact_search_query() here: Q5 was resolved on
      2026-10-03 (stored redacted), and the redaction call is phase 09's 09-API-012
      plus phase 06's 06-PII-108. Do not change find_matching_ads or send_alerts.
acceptance_criteria:
  - "a query at the cap round-trips through POST /save-search/ and is stored byte-identical"
  - "a query one over the cap is refused with a 4xx and nothing is stored"
  - "a 50,000-character query cannot be stored through the view"
  - "the model field itself refuses an over-cap value for a non-view writer, e.g. a management command or the admin"
  - "test_saved_search_create.py's existing happy path is green unchanged"
  - "find_matching_ads.py and send_alerts.py are unchanged"
  - "no redact_search_query() call was added to save_search by this block - that is phase 09's 09-API-012 and phase 06's 06-PII-108 under the 2026-10-03 Q5 ruling"
  - "no timing measurement, EXPLAIN or index work was done"
  - "makemigrations --check is clean after the model change"
tests_to_run:
  - "src/backend/apps/search/tests/test_saved_search_create.py"
  - "src/backend/apps/search/tests/test_alert_query.py"
```

**Tests required**

1. **The cap** — at the cap, stored byte-identical; one over the cap, refused with a 4xx
   and **nothing written**. Assert on absence, not on the status code alone.
2. **The non-view writer** — a `SavedSearch` created through the ORM with an over-cap
   value is rejected by the model. This is the assertion that distinguishes a **model**
   bound from a view-only cap, and it is the whole point of the block.
3. **The alert job's surface** — an over-cap value cannot reach `send_alerts._collect_alerts`.
   No timing; only reachability.
4. **The regression set** — `test_alert_query.py` green unchanged, including
   `TestImmediateAlertsGate` (the gate stays off) and the 10-ad cap.

**Risk and rollback**

- *Migration risk:* the number after `0003` is contested. Re-check the directory
  immediately before generating; never renumber.
- *Behaviour risk:* an existing saved search already holds an over-cap value and the
  migration fails on it. Mitigation: the migration must **inspect and handle** the existing
  population, and the commit body must state what it did with it. A bare `AlterField` that
  fails in production is not a ship.
- *Scope risk:* the Implementor introduces a DTO (C-6) or measures latency. Binding
  constraints 3 and 5.
- *Product risk:* truncation would silently change what a saved search matches. Binding
  constraint 2 forbids it.
- *Product risk (was: "the block is redaction without phase 06's answer, Q5").* **CLOSED
  2026-10-03.** The owner ruled that `SavedSearch.query` is stored redacted and
  `query_normalized` is keyed on the redacted form, so the "which side" question no longer
  exists. The residual risk is now the opposite: **an Implementor adds the redaction call here
  "because the ruling says redact"** and lands phase 09's / phase 06's work in phase 08. The
  acceptance criterion above forbids it.
- *Cross-block risk:* phase 08 BLOCK 8 and phase 09 BLOCK 13 both edit
  `apps/search/views/save_search.py`. Re-read immediately before editing; stop and report on a
  concurrent change (§5.3).
- *Rollback:* a straight revert restores the unbounded field; **any rows the migration
  truncated or the boundary refused do not come back**, and the commit body must say so if
  the migration is destructive.
- *Cross-phase:* `SavedSearch` is a **phase 06 PII surface** — `06-PII-104` owns the
  retention policy and `06-PII-108` owns `SearchHistory.query_normalized`. **Q5 is no longer
  their open question: it was answered on 2026-10-03.** Phase 06 now owes the *policy
  statement* ("one rule for all query-persistence paths") and phase 09 owes the `save_search`
  redaction call; BLOCK 8 ships the bound and nothing else.

---

### BLOCK 9 — One `get_client_ip`, one budget table, one 429 shape (SRCH-010, SRCH-013)

| | |
|---|---|
| **Findings owned** | `SRCH-010` (MEDIUM) + `SRCH-013` (LOW). Also closes `04-AUT-003` |
| **Depends on** | **nothing in-plan** |
| **Blocks** | nothing in-plan; **closes phase 04's `04-AUT-003`** |
| **Priority** | **P1** |
| **Risk level** | **MEDIUM** — three call sites, a new module, and a behaviour change to two live limits |
| **Required agents** | **Auditor · Planner · Validator.** Researcher not required. Validator required — the limiter behaviour change is security-relevant |

**The mechanism, from the proxy config.** `docker/nginx/nginx.conf` sets
`proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for`, and `$proxy_add_x_forwarded_for`
is `"$http_x_forwarded_for, $remote_addr"` — nginx **appends** the peer as the
**rightmost** element, so the client's value is **leftmost**. All three `_get_client_ip`
copies take `split(",")[0]`, which is therefore attacker-controlled end to end. It also
sets `proxy_set_header X-Real-IP $remote_addr`, which nginx **overwrites**: a caller cannot
influence that header at all. So the correct read is **`X-Real-IP` → `XFF[-1]` →
`REMOTE_ADDR`**, in that order.

**The three copies, byte-identical today:** `apps/search/services/rate_limit.py`,
`apps/users/services/login_rate_limit.py`, `apps/core/services/contact_rate_limit.py`.
One shared helper in `apps/core` closes `SRCH-010`, `04-AUT-003` and the header half of
`SRCH-013` in one commit.

**The two budgets and the two 429 bodies (C-7).**

| Route | Module | Budget | 429 body |
|---|---|---|---|
| `/search/` | `search.services.rate_limit.rate_limit_check` | 30 / 60 s | `JsonResponse({"error": "rate_limit"}, 429)` — **the literal is `rate_limit`, not `rate_limited`** |
| `/` | `core.services.contact_rate_limit.check_deep_link_render_rate_limit` | 60 / 600 s | bare `HttpResponse(status=429)`, **empty body** |

Both budgets are bare `Final[int]` pairs, and the second module's docstring says only that
it "mirrors" the first — the *mechanism*, not the *budget*. That is how two different
numbers ended up documented as if one were authoritative. **The response-shape
inconsistency is not covered by `SRCH-010`** and would be silently dropped by merging them
blindly, which is why the report kept them separate.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/core/services/client_ip.py` (new) | `get_client_ip` | One small function, one responsibility. **Not** a framework |
| `src/backend/apps/search/services/rate_limit.py` | `_get_client_ip` (delete), `RATE_LIMIT_REQUESTS`, `RATE_LIMIT_PERIOD`, `_RATE_LIMIT_KEY_PATTERN`, `rate_limit_check` | The key pattern is `{namespace}_rl:{ip}`; **namespace isolation is pinned by a test** |
| `src/backend/apps/core/services/contact_rate_limit.py` | `_get_client_ip` (delete), `RATE_LIMIT_REQUESTS`, `RATE_LIMIT_PERIOD`, `check_deep_link_render_rate_limit` | Its key shape is `telegram_dl_rl:{ip}` — **different**, so merging is a genuine refactor, not a rename |
| `src/backend/apps/users/services/login_rate_limit.py` | `_get_client_ip` (delete) | **Phase 04's `04-AUT-003` is the same defect in this file.** One helper closes both; phase 04 must be told |
| `src/backend/apps/core/enums.py` (or the rate-limit module) | the per-endpoint budget table as a **`StrEnum`** | Project rule 10. The current `Final[int]` pairs are the reason the numbers drifted |
| `src/backend/apps/search/views/search.py`, `apps/ads/views/listings.py` | the two 429 responses | One shared shape for both |
| `src/backend/apps/search/tests/test_search_view.py` | `TestSearchViewRateLimit` | **Both existing tests must stay green unchanged** — especially `test_search_and_autocomplete_use_independent_counters`, which pins namespace separation |
| `docker/nginx/nginx.conf` | — | **Read-only reference.** No change needed and none is proposed |

**Binding constraints**

1. **One shared `get_client_ip`, in `apps/core`.** Three byte-identical copies are a
   de-duplication, not a new abstraction.
2. **Read order: `X-Real-IP` → `XFF[-1]` → `REMOTE_ADDR`.** Never `XFF[0]` again.
3. **Budgets are a `StrEnum` table**, and the **rationale** for 30/60 s and 60/600 s is
   recorded — or the number is changed with a stated reason. Two undocumented numbers on
   adjacent anonymous HTML routes is the defect.
4. **Namespace isolation is preserved.** `search` and `autocomplete` must keep independent
   counters.
5. **One 429 response shape for both routes**, using the real literal `rate_limit`.
6. **Do not change nginx.** Its limits key on `$binary_remote_addr` and are not spoofable;
   they bound the *edge*, not the application policy this block is about.
7. **Do not change the budgets' semantics** (a fixed window with an atomic increment).
   Only the key derivation, the table shape and the refusal body are in scope.

**Implementor task**

```yaml
id: task_08_b09_client_ip_and_budgets
title: "One trusted client-IP helper and one rate-limit budget table (08-SRCH-010, 08-SRCH-013)"
priority: medium
depends_on: []
source_reference: ".ai/plans/08-search-fts-remediation.md"
source_section: "BLOCK 9 - One get_client_ip, one budget table, one 429 shape"
source_blocks: ["BLOCK 9"]
description: >
  Three byte-identical _get_client_ip implementations all read
  HTTP_X_FORWARDED_FOR.split(",")[0]. nginx sets
  proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for, which APPENDS the
  peer as the rightmost element, so the leftmost element is client-controlled end
  to end and the application rate limiter is spoofable. nginx also sets
  proxy_set_header X-Real-IP $remote_addr, which it overwrites and a caller cannot
  influence. Read X-Real-IP, then XFF[-1], then REMOTE_ADDR. Separately, /search/
  and / are adjacent anonymous HTML routes with unrelated budgets (30/60 s vs
  60/600 s) and two different 429 body shapes (JSON vs empty).
goals:
  - "make the application rate-limit key unforgeable by the client"
  - "make the two budgets a declared StrEnum table with a written rationale"
  - "give both routes one 429 response shape"
  - "close 04-AUT-003 in the same change"
files:
  - path: "src/backend/apps/core/services/client_ip.py"
    targets:
      - type: function
        name: get_client_ip
  - path: "src/backend/apps/search/services/rate_limit.py"
    targets:
      - type: function
        name: _get_client_ip
      - type: function
        name: rate_limit_check
  - path: "src/backend/apps/core/services/contact_rate_limit.py"
    targets:
      - type: function
        name: _get_client_ip
      - type: function
        name: check_deep_link_render_rate_limit
  - path: "src/backend/apps/users/services/login_rate_limit.py"
    targets:
      - type: function
        name: _get_client_ip
  - path: "src/backend/apps/search/tests/test_search_view.py"
    targets:
      - type: class
        name: TestSearchViewRateLimit
changes:
  - action: add_code
    description: >
      Add one get_client_ip in apps/core/services that reads X-Real-IP, then the
      LAST element of X-Forwarded-For, then REMOTE_ADDR, with a docstring stating
      why the leftmost element is not trusted under $proxy_add_x_forwarded_for.
      Delete the three local copies and call the shared helper. Add a StrEnum
      budget table keyed per endpoint with the rationale for each budget in the
      docstring. Use one 429 response shape for both /search/ and /, with the
      literal {"error": "rate_limit"}.
    code_hint: |
      class RateLimitBudget(StrEnum):
          """Per-endpoint application rate-limit budgets and their rationale.

          SEARCH_PAGE: 30 requests / 60 s. Anonymous HTML search rendering; the
              page is a buyer-facing hot path.
          DEEP_LINK_RENDER: 60 requests / 600 s. Anonymous browse with a
              deep-link render side effect.
          """

          SEARCH_PAGE = "search_page"
          DEEP_LINK_RENDER = "deep_link_render"
acceptance_criteria:
  - "a request with a rotating X-Forwarded-For reaches the SAME limiter key as one with a fixed value"
  - "a request with no forwarded headers falls back to REMOTE_ADDR"
  - "X-Real-IP wins over X-Forwarded-For when both are present"
  - "60 requests with a rotating XFF produce rate-limit refusals in the same proportion as 40 with a fixed value"
  - "/search/ and / return the same 429 body shape"
  - "test_search_returns_429_after_threshold and test_search_and_autocomplete_use_independent_counters are green UNCHANGED"
  - "no _get_client_ip definition remains outside apps/core"
  - "the budgets are a StrEnum, not a Final[int] pair, and each has a written rationale"
  - "docker/nginx/nginx.conf is unchanged"
tests_to_run:
  - "src/backend/apps/search/tests/test_search_view.py"
  - "src/backend/apps/users/tests/test_login_rate_limit.py"
```

**Tests required**

1. **The spoof** — the same client identity under a rotating and a fixed `X-Forwarded-For`
   maps to one key. This is the test the report names as the one that would have caught
   the defect, and it is the block's most important assertion.
2. **The fallbacks** — `X-Real-IP` preferred; `XFF[-1]` when `X-Real-IP` is absent;
   `REMOTE_ADDR` when neither is present. Three cases, because getting the precedence
   backwards reintroduces the defect on a different deployment shape.
3. **The budget table** — each endpoint's limiter refuses at its declared budget, and the
   refusal bodies on `/search/` and `/` are identical.
4. **Namespace isolation** — `search` and `autocomplete` keep independent counters. This
   test already exists and must not be weakened.
5. **The regression set** — the login limiter's existing tests stay green; the deep-link
   limiter's stay green.

**Risk and rollback**

- *Security risk (the defining risk):* an implementer reads `X-Real-IP` **or** `XFF[0]`
  and the defect survives with a different shape. Test 1 is the tripwire; the Validator
  may reject the block.
- *Regression risk:* the key-namespace refactor merges two differently-shaped key patterns
  (`{namespace}_rl:{ip}` and `telegram_dl_rl:{ip}`) and one limiter's counters start
  contaminating the other. `test_search_and_autocomplete_use_independent_counters` is the
  tripwire.
- *Behaviour risk:* a shared 429 shape changes what an existing consumer sees on `/`,
  which currently returns an empty body. That is the point, and it is a visible change;
  state it in the commit body.
- *Rollback:* a straight revert restores the spoofable key derivation.
- *Cross-phase:* `04-AUT-003` is phase 04's, and **one commit closes both** — phase 04
  must be told so it does not ship a second, divergent fix. Phase 02 owns whether the
  **edge** limits are configured and enforced; that boundary is confirmed non-overlapping
  and this block does   not touch nginx or the env plumbing.

---

### BLOCK 10 — An ambiguous category display name scopes to no branch (VAL-003)

| | |
|---|---|
| **Findings owned** | `VAL-003` (MEDIUM) |
| **Depends on** | **nothing in-plan.** Hard edge **10 → 11** |
| **Blocks** | BLOCK 11 |
| **Priority** | **P1** |
| **Risk level** | **MEDIUM** — the fix is small, but it must preserve a cache property a test pins |
| **Required agents** | **Auditor · Planner · Validator.** Researcher not required |

**The defect, and it is on two paths (C-9).** Both resolution paths return on the **first**
entry whose display name matches:

```
_fuzzy_category_match:  for entry in get_active_category_names(locale):
                            if str(entry["name"]).lower() == query.lower():
                                return Category.objects.get(id=entry["id"])

_fuzzy_match_by_name:   for entry in entries:
                            if str(entry["name"]) == matched_name:
                                return Category.objects.get(id=entry["id"])
```

`Category.name` is a `CharField` with **no** `unique=True` and no `UniqueConstraint` in
`Meta` (only `slug` is unique). `name_i18n` is free-form `JSONField` and
`Category.get_name(locale)` falls back `locale → "ru" → name`, so a translated name can
collide even when the base `name` does not. **Two active categories sharing a localised
display name scope a single-word search to an arbitrary branch, and that branch can hold
no matching ads at all** — the query returns zero where matches exist.

**Why this is a correctness fix and not a design question.** The report's own reproduction
is the evidence: a validator's stale second category sharing the display name "Велосипеды"
made a **correct** finding look refuted, because the query was scoped to the stale
category. The failure class is: *a first-hit resolution over a non-unique key turns a
recall-reducing heuristic into a recall-destroying one, and the failure is invisible in
both cases.* `SRCH-009`'s narrowing is the design question (BLOCK 11); this is the bug
underneath it, and it holds whichever way Q8 is decided.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/search/views/search.py` | `_fuzzy_category_match` (the **exact** path) and `_fuzzy_match_by_name` (the fuzzy path) | **Both.** The report cited only the fuzzy one |
| `src/backend/apps/search/services/category_fuzzy.py` | `get_active_category_names`, `_fuzzy_names_cache_key` | **Read-only for behaviour;** the cached candidate list is the data the fix reads. Its **zero-SELECT property is pinned** |
| `src/backend/apps/search/tests/test_search_fuzzy.py` | the byte-identical-to-`difflib` test and the zero-SELECT test | **Must stay green.** The second one constrains the name→ids index design |
| `src/backend/apps/search/tests/test_search_view.py` | a new ambiguous-name case | Existing module |
| `src/backend/apps/categories/models.py` | `Category.name` / `name_i18n` / `get_name` | **Read-only reference.** This block does **not** add a unique constraint on `name` — that is a catalogue decision with an i18n migration, out of scope |

**Binding constraints**

1. **Ambiguous ⇒ no guess**, on **both** paths. Fixing only `_fuzzy_match_by_name` leaves
   the exact path returning an arbitrary branch.
2. **A slug match stays unambiguous.** `slug` is `unique=True`, so tier 1 is not a
   first-hit resolution and must not be made "ambiguous-aware" in a way that breaks it.
3. **Preserve the zero-category-SELECT property on a warm cache.** A name→ids index
   computed from the cached candidate list costs **zero** queries; resolving to
   `Category` objects per candidate would break `test_search_fuzzy.py`.
4. **Do not add a unique constraint on `Category.name`.** It would require an i18n
   migration and a catalogue decision, and translated names can legitimately collide.
5. **Do not change `Category.get_name` or the cache key composition** — the latter is
   BLOCK 6's territory under the Q1 decision.
6. **If the match becomes ambiguous, the search must still return FTS results for the
   whole tree**, not zero results. "No guess" means no narrowing, not no results.

**Implementor task**

```yaml
id: task_08_b10_ambiguous_category_name
title: "Treat an ambiguous category display name as no guess (08-VAL-003)"
priority: medium
depends_on: []
source_reference: ".ai/plans/08-search-fts-remediation.md"
source_section: "BLOCK 10 - An ambiguous category display name scopes to no branch"
source_blocks: ["BLOCK 10"]
description: >
  Both _fuzzy_category_match (the exact-name path) and _fuzzy_match_by_name (the
  fuzzy path) resolve a matched display name by returning the FIRST entry whose name
  matches. Category.name has no unique constraint and name_i18n is free-form JSONB, so
  two active categories can share a localised display name - which scopes a
  single-word search to an arbitrary branch that may hold no matching ads at all.
  Resolve a matched name to the set of ids from the cached candidate list; if more
  than one id matches, return no guess so the search is not narrowed.
files:
  - path: "src/backend/apps/search/views/search.py"
    targets:
      - type: function
        name: _fuzzy_category_match
      - type: function
        name: _fuzzy_match_by_name
  - path: "src/backend/apps/search/tests/test_search_fuzzy.py"
    targets:
      - type: module
        name: test_search_fuzzy
  - path: "src/backend/apps/search/tests/test_search_view.py"
    targets:
      - type: module
        name: test_search_view
changes:
  - action: modify_code
    description: >
      Change both resolution paths to collect every candidate id whose localised
      display name matches, from get_active_category_names(locale) (which costs zero
      category SELECTs on a warm cache). Return the match only when exactly one id
      matches; when two or more match, return None so no category filter is applied.
      Keep the slug tier unambiguous. Do not add a unique constraint on Category.name.
    code_hint: |
      def _ids_for_exact_name(name: str, locale: LanguageLocale) -> list[int]:
          """Every active category id whose localised display name equals `name`.

          Ambiguity is expected: Category.name carries no uniqueness constraint and
          name_i18n is free-form. Returning the first hit would scope the search to
          an arbitrary branch.
          """
          target = name.casefold()
          return [
              int(entry["id"])
              for entry in get_active_category_names(locale)
              if str(entry["name"]).casefold() == target
          ]
acceptance_criteria:
  - "two active categories sharing a localised display name cause a single-word search to return NO category narrowing, and the ad in the other branch is visible"
  - "an unambiguous display name still scopes the search to its subtree, on both the exact and the fuzzy path"
  - "a slug match still scopes, and is unaffected by the ambiguity rule"
  - "the warm-cache path still performs zero category SELECTs"
  - "test_search_fuzzy.py passes UNCHANGED, including the byte-identical-to-difflib and zero-SELECT assertions"
  - "Category.name still has no unique constraint and Category.get_name is unchanged"
  - "the cache key composition is unchanged"
tests_to_run:
  - "src/backend/apps/search/tests/test_search_fuzzy.py"
  - "src/backend/apps/search/tests/test_search_view.py"
```

**Tests required**

1. **The ambiguity** — two active categories with the same `name_i18n['ru']`, one ad each;
   a single-word search returns **both** ads (no narrowing), not one and not zero.
2. **The unambiguous control** — the same fixture with distinct names still narrows to the
   matching subtree. This is the assertion that stops an over-correction ("always no
   guess") from passing test 1.
3. **Both paths** — the ambiguity case is asserted once through the **exact** path and once
   through the **fuzzy** path, because the report cited only the fuzzy one (C-9) and this
   is the block's whole point.
4. **The zero-SELECT property** — the existing test is the tripwire; it must stay green
   unchanged.

**Risk and rollback**

- *Regression risk:* "ambiguous ⇒ no guess" is over-applied and the narrowing stops working
  for every query. Test 2 is the control.
- *Performance risk:* a name→ids index computed per request instead of from the cached
  candidate list. `test_search_fuzzy.py`'s zero-SELECT test is the tripwire.
- *Scope risk:* the Implementer "fixes" this by adding a unique constraint on
  `Category.name`. Binding constraint 4 forbids it; that is a catalogue decision with an
  i18n migration.
- *Method risk:* the reproduction needs a **clean schema** and an asserted
  `ads_search_vector_update` trigger, or a stale-data artefact will make a correct fix
  look broken (§0.2.1). Wipe the rows and re-assert the trigger before asserting.
- *Rollback:* a straight revert; the arbitrary-branch behaviour returns.

---

### BLOCK 11 — Single-word narrowing: the owner decision, then the change (SRCH-009)

| | |
|---|---|
| **Findings owned** | `SRCH-009` (MEDIUM — **unchanged after the 2026-10-03 ruling**) |
| **Depends on** | **BLOCK 10** (hard) — the control must render on the ambiguity-fixed branch |
| **Blocks** | nothing in-plan |
| **Priority** | P2 — the behaviour is **specified and now decided**; the work is the signal |
| **Risk level** | **MEDIUM** — a template + i18n change on the search results page; the narrowing stays, so the recall exposure is a **decided, not discovered**, property |
| **Required agents** | **Auditor · Planner · Validator.** Q8 is answered (2026-10-03) — the Researcher is no longer owed a consequence analysis, because there is no predicate change to analyse. **Validator required** to confirm `ru`/`bs` and that the two pinning tests are green **unchanged** |

**This is a design question, not a bug.** `docs/01-spec/technical-specification.md:66`
documents the behaviour verbatim — *"app-level fuzzy detect (`difflib`) sets `category_id`
filter for single-word queries"* — so the current narrowing is **specified**, not a
regression. The finding is that the specification chose recall-reducing behaviour with no
UI signal, and the buyer cannot see, express or undo the guess.

**The current code.** In `_apply_fts_filtering`, for a single-word query a fuzzy category
match is applied as a **hard** AND-narrow *before* the FTS predicate:
`queryset.filter(category_id__in=descendant_ids)`. There is no disjunctive alternative and
the template renders no indication that a guess was made. A one-word query returns 1
result; the same search with one extra word returns 2.

**Decision required before implementation — Q8 — RESOLVED 2026-10-03 (Product Owner)**

**The ruling: the single-word narrowing STAYS a hard filter, AND the UI must signal it.** The
disjunctive-branch fix is **NOT chosen**. The results page renders a
*"showing results for &lt;Category&gt; only — search all categories"* control, plus BLOCK 10's
ambiguity fix. **`SRCH-009` therefore stays MEDIUM** and becomes an **implementation**, not a
documentation change. The options are retained below for traceability; the Implementor may
**not** re-choose.

| Option | What it is | Consequences |
|---|---|---|
| ~~**(a)**~~ | **Disjunctive branch** — a guess widens recall | **REJECTED 2026-10-03.** The owner accepted the recall-reducing behaviour as intended. **No predicate change ships**, so `_fuzzy_category_match` and `_apply_fts_filtering` are untouched, `_QUERY_BOUND` and the 2 s SLO are unaffected, and the two `TestSearchViewDescendantCategories` tests **stay green unchanged** |
| **(b) — CHOSEN** | **Accept the narrowing as intended** | **Adopted.** The hard filter remains, `is_declined`-style narrowing semantics are unchanged, and the recall trade-off is now a deliberate, documented product choice rather than an undocumented default |
| **(c) — CHOSEN (combined with b)** | Add the **UI signal** — tell the buyer a category was guessed, and offer an undo | **Adopted, and it is the whole of this block's production change.** The control is an *undo* ("search all categories"), not merely a notice — which is what makes the retained narrowing defensible |

**What this block is now.** A **template + i18n change plus BLOCK 10's ambiguity fix**. It is
**not** a hot-path predicate change. Two consequences the Implementor must not undo:

1. **The narrowing is a feature now, not a defect.** The two tests that pin it are *correct*.
   Under project rule 2, they are **production code's** specification and **must not be
   rewritten or weakened** to make a change pass. A PR that alters
   `test_category_match_expands_to_descendants` or
   `test_single_word_category_match_rejects_non_published_descendants` is reversing a Product
   Owner decision and needs the owner, not a justification.
2. **A new user-visible string is an i18n deliverable in the same commit**, with **non-empty
   `ru` and `bs`**. `en` may be empty (the msgid is English).

**The visibility guarantee is unchanged and still binding.** Whatever the control does, a
non-PUBLISHED descendant or an ad in an inactive category stays excluded. The undo control
changes the *scope of the query*, not *who may see what*.

**File surface (semantic units)** — *post-ruling: this block touches no Python predicate*

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/templates/ads/partials/ad_list.html`, `ads/list.html` | the narrowing-signal + undo control | **The block's only production file.** `ad_list.html` branches on `page_obj` / `has_results` and re-emits filter query strings by hand; a template change needs `uv run djlint`. The control reads *"showing results for &lt;Category&gt; only — search all categories"* and its link clears the category narrowing |
| `src/backend/apps/search/views/search.py` | `_apply_fts_filtering`, `_is_single_word` | **Read-only under the ruling.** Option (a) was rejected, so the predicate and the single-word test are untouched |
| `src/backend/apps/search/tests/test_search_view.py` | `TestSearchViewDescendantCategories` (2 tests pin the narrowing) | **Green UNCHANGED and must stay that way** — they now encode a Product Owner decision. Under project rule 2, weakening either is forbidden |
| `src/backend/locale/*/LC_MESSAGES/django.po` | the new string | **Append only.** `ru` **and** `bs` non-empty. Run `test_i18n_completeness.py` |
| `docs/01-spec/search-patterns.md` | the fuzzy-narrowing description | `technical-specification.md:66` is **phase 06's** — do not edit it for this. `search-patterns.md` is unclaimed |

**Binding constraints**

1. **The Q8 ruling is recorded before implementation** — option **(b)+(c)**, not (a) — and named
   in the commit body.
2. **The hard filter stays.** `_apply_fts_filtering`'s `category_id__in=descendant_ids`
   narrow for a single-word query is **unchanged**. The block adds a *signal and an undo*, not a
   different filter.
3. **The visibility guarantee must survive.** Non-PUBLISHED descendants and ads in an inactive
   category stay excluded, and the undo control must not widen that.
4. **A new user-visible string is an i18n deliverable in the same commit**, `ru` **and** `bs`
   non-empty.
5. **Do not add a category filter on a multi-word query**, and do not change
   `_is_single_word`.
6. **No query-count or SLO regression.** `_QUERY_BOUND` and the 2 s SLO apply. Because no
   predicate changes, this is expected to be free — **verify it, do not assume it**, and report
   the measurement in the commit body.
7. **Do not weaken or rewrite the two `TestSearchViewDescendantCategories` tests.** They are the
   specification of a Product Owner decision, not obstacles to it.

**Implementor task**

```yaml
id: task_08_b11_single_word_narrowing
title: "Resolve the single-word category narrowing decision and implement it (08-SRCH-009)"
priority: medium
depends_on: [task_08_b10_ambiguous_category_name]
source_reference: ".ai/plans/08-search-fts-remediation.md"
source_section: "BLOCK 11 - Single-word narrowing: the owner decision, then the change"
source_blocks: ["BLOCK 11"]
description: >
  _apply_fts_filtering applies a fuzzy category match as a hard AND-narrow
  (category_id__in=<subtree>) on any single-word query, before the FTS predicate,
  with no disjunctive alternative and no template signal. A one-word query returns
  one branch where a two-word query returns both. technical-specification.md:66
  documents this behaviour, so it is specified rather than a regression - the
  finding is the recall-reducing choice with no UI signal. Q8 was RESOLVED on 2026-10-03:
  the narrowing stays a hard filter and the UI signals it with an undo control. Implement
  that; do not implement the rejected disjunctive branch.
goals:
  - "keep the category narrowing as a hard filter and make it visible and undoable in the UI"
  - "preserve the visibility guarantee: non-PUBLISHED descendants and inactive categories stay excluded"
  - "stay inside _QUERY_BOUND and the 2 s search SLO"
files:
  - path: "src/backend/templates/ads/partials/ad_list.html"
    targets:
      - type: module
        name: ad_list
  - path: "src/backend/locale/ru/LC_MESSAGES/django.po"
    targets:
      - type: module
        name: django
changes:
  - action: modify_code
    description: >
      Q8 is RESOLVED 2026-10-03 as (b)+(c): the narrowing stays a hard filter and the UI signals
      it. Add the "showing results for <Category> only - search all categories" control to the
      results partial, with a link that clears the category narrowing, and translate the new
      string into ru and bs. Do NOT change _apply_fts_filtering or _is_single_word, and do NOT
      rewrite TestSearchViewDescendantCategories - those two tests now encode the Product Owner's
      decision. BLOCK 10's ambiguity fix ships in the same block.
acceptance_criteria:
  - "the commit body names the Q8 ruling (options b + c, option a explicitly rejected) and the date 2026-10-03"
  - "a one-word query still narrows to the guessed branch - the hard filter is unchanged"
  - "the results page renders a control naming the category and offering to search all categories, and the link clears the narrowing"
  - "the new string has non-empty ru and bs msgstr; en may be empty"
  - "a non-PUBLISHED ad in a descendant category is still excluded, and an ad in an inactive category is still excluded, with the narrowing control rendered"
  - "TestSearchViewDescendantCategories is green UNCHANGED - both tests, neither rewritten nor weakened"
  - "_apply_fts_filtering and _is_single_word are byte-identical"
  - "a multi-word query is unchanged"
  - "test_search_query_count.py and test_search_slo.py are green, and the measurement is recorded"
  - "test_i18n_completeness.py is green"
  - "technical-specification.md is unchanged"
tests_to_run:
  - "src/backend/apps/search/tests/test_search_view.py"
  - "src/backend/apps/search/tests/test_search_fuzzy.py"
  - "src/backend/apps/search/tests/test_search_query_count.py"
  - "src/backend/apps/search/tests/test_search_slo.py"
  - "src/backend/apps/ads/tests/test_i18n_completeness.py"
```

**Tests required**

1. **The control renders and works** — a one-word query that triggers a category narrowing
   renders the *"showing results for &lt;Category&gt; only"* control, and following its link
   returns results from the **whole** tree. This is the assertion that distinguishes a signal
   with an undo from a notice.
2. **The visibility control** — a non-PUBLISHED ad in a descendant category is still
   excluded, and an ad in an inactive category is still excluded, **with the control rendered**.
   The undo widens the *query*, never the *audience*; that distinction is the whole risk here.
3. **The multi-word control** — a two-word query is byte-identical to before and renders no
   control.
4. **The narrowing still narrows** — the two `TestSearchViewDescendantCategories` tests are the
   control and must be green unchanged. If this block made one fail, the implementation changed
   a Product Owner decision.
5. **The cost** — `_QUERY_BOUND` and the 2 s SLO. Expected to be free because no predicate
   changed; **verify it and record the measurement** rather than asserting it.
6. **i18n** — `test_i18n_completeness.py` green with `ru` and `bs` non-empty for the new string.

**Risk and rollback**

- *Product risk:* an Implementor "improves" recall by replacing the narrowing with the rejected
  disjunctive branch. Mitigation: the ruling is recorded above, the file surface no longer
  lists `search.py`, and acceptance criterion 2 requires the two pinning tests to be green
  **unchanged**.
- *UI regression:* the control renders on a page where it should not, or its link drops other
  active filters. Test 1 and 3 are the controls; `ad_list.html`'s hand-rolled query strings are
  the hazard.
- *Visibility regression:* an implementer wires the undo as a category filter that bypasses the
  visibility predicate. Test 2 is the non-negotiable control and it must be asserted **with**
  the control rendered, not instead of it.
- *i18n risk:* a new user-visible string ships without non-empty `ru` and `bs`. The locale
  files are shared; append, never regenerate. An i18n-gate failure here is a **consequence** of
  the fix, not a regression.
- *Process risk:* Q8 answered implicitly, or answered as option (a). The block's commit body
  must name the ruling and the date.
- *Rollback:* a straight revert removes the control and its strings and restores the
  undocumented-narrowing state. The narrowing itself is untouched by a revert, which is
  correct — it is the decided behaviour.

---

### BLOCK 12 — `has_results` must come from the rendered rows (SRCH-015)

| | |
|---|---|
| **Findings owned** | `SRCH-015` (LOW, partial) |
| **Depends on** | **BLOCK 7** (soft) — the stale-cache window this reproduces is BLOCKS 6/7's subject |
| **Blocks** | nothing in-plan |
| **Priority** | **P2** |
| **Risk level** | **LOW** — a one-line derivation, but three tests assert on `total_count` |
| **Required agents** | **Auditor · Planner.** Implementor + inline verification. Validator not required |

**What still holds.** `has_results = total_count > 0`, and on the hot path
`total_count, results_truncated = _resolve_search_count(cached_ids, ads, …)` returns
`len(cached_ids)` on a cache hit. The rendered cards come from
`paginator.get_page(params.page)` over `ads`, which on a cache hit is
`ads.filter(pk__in=cached_ids)` — re-filtered against the **live** `build_queryset`
predicate. An ad that stopped matching between the cache write and the read drops out of
`page_obj` while `total_count` still counts it. `ad_list.html` then branches
`{% if page_obj %} … {% elif has_results is False and query %} … {% endif %}`: with
`total_count > 0` and an empty `page_obj`, **neither branch fires** — zero cards, no empty
state, HTTP 200.

**What is stale in the report (C-8), and the scope consequence.** `total_count` is
**never rendered in any template** — a grep over `src/backend/templates` returns no hits.
The only count-bearing UI is the `results_truncated` banner. So the user-visible symptom
is a **blank results area**, not "3 results next to 0 cards". The report's one-line fix is
still right and is now **simpler**, because `has_results` is the only UI consumer of
`total_count`. **Adding a count display is scope creep** and is forbidden (§6.2).

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/search/views/search.py` | the `has_results` assignment in `search`; `_resolve_search_count` is a **read-only reference** | One derivation. **Do not change `_resolve_search_count`'s return values** — three tests assert on them |
| `src/backend/apps/search/tests/test_search_view.py` | `TestSearchViewTotalCount` (3 tests) | **Must stay green unchanged.** They pin `total_count`, the exact `COUNT(*)` at the 1000 cap, `results_truncated` and the cold-miss-loser path |
| `src/backend/templates/ads/partials/ad_list.html` | the `has_results is False and query` branch | **Read-only unless the empty-state copy needs a correction**; the block must not redesign the empty state |

**Binding constraints**

1. **Derive `has_results` from the same evaluation as the rendered rows.** The
   handbook's block 11 criterion is exactly this: "the total, the contents and the empty
   state come from one evaluation or several".
2. **Do not change `total_count` or `results_truncated`.** `TestSearchViewTotalCount`
   asserts on the context; they are correct for their purpose.
3. **Do not add a count display to any template** (C-8).
4. **No second count query.** The advisory "add a `_meta` introspection path so the fix is a
   read, not a second count" is a **de-scoped design change** (§6.2); the one-line
   derivation is the scope.
5. **The block lands after BLOCK 7** so the next caching change does not revert it — the
   report's explicit instruction.

**Implementor task**

```yaml
id: task_08_b12_has_results_derivation
title: "Derive has_results from the same evaluation as the rendered rows (08-SRCH-015)"
priority: low
depends_on: [task_08_b05_consent_restoration_invalidation]
source_reference: ".ai/plans/08-search-fts-remediation.md"
source_section: "BLOCK 12 - has_results must come from the rendered rows"
source_blocks: ["BLOCK 12"]
description: >
  has_results is total_count > 0, and on a cache hit total_count is len(cached_ids),
  while the rendered cards come from paginator.get_page over the re-filtered ads.
  An ad that stopped matching between the cache write and the read drops out of
  page_obj while total_count still counts it, so ad_list.html renders neither cards
  nor the empty state - a blank results area at HTTP 200. total_count is never
  rendered in any template, so the only UI consumer of total_count is has_results.
  Derive has_results from the same evaluation as the rendered rows.
goals:
  - "make the results area and the empty state come from one evaluation"
  - "leave total_count and results_truncated exactly as they are"
  - "add no count display"
files:
  - path: "src/backend/apps/search/views/search.py"
    targets:
      - type: function
        name: search
      - type: function
        name: _resolve_search_count
  - path: "src/backend/apps/search/tests/test_search_view.py"
    targets:
      - type: class
        name: TestSearchViewTotalCount
changes:
  - action: modify_code
    description: >
      Change the has_results assignment in search() to reflect whether the page
      being rendered has rows, rather than the cached id count. Leave
      _resolve_search_count, total_count and results_truncated untouched. Do not add
      a second count query and do not add a count display to any template.
acceptance_criteria:
  - "with a warm cache and an ad that no longer matches the live predicate, the page renders the empty state instead of a blank results area"
  - "the response is still 200"
  - "TestSearchViewTotalCount passes UNCHANGED - all three tests, including the exact COUNT(*) at the 1000 cap and the cold-miss-loser path"
  - "total_count and results_truncated are unchanged in the context"
  - "no template gained a count display and no second count query was added"
  - "the results_truncated banner behaviour is unchanged"
tests_to_run:
  - "src/backend/apps/search/tests/test_search_view.py"
```

**Tests required**

1. **The disagreement** — a warm cache, then a bulk `.update()` that stops an ad matching
   **without** bumping the version (the exact stale-cache window `SRCH-005`/`SRCH-007`
   create), then re-read: the page renders the **empty state**, and the response is 200.
2. **The healthy path** — a normal warm-cache search still renders cards and still reports
   the same `total_count` in the context.
3. **The truncation banner** — a result set over the cap still shows the banner and still
   reports `results_truncated`. `TestSearchViewTotalCount` covers this and must be
   unchanged.

**Risk and rollback**

- *Regression risk:* deriving from `page_obj` makes `has_results` false for a legitimate
  page that is empty **because the requested page number is past the end** — a distinct
  case. The derivation must distinguish "no results at all" from "page out of range".
- *Regression risk:* the implementer "simplifies" by changing `_resolve_search_count`.
  Binding constraint 2; `TestSearchViewTotalCount` is the tripwire.
- *Scope risk:* adding a result-count display. Binding constraint 3.
- *Rollback:* a straight revert; the blank-area symptom returns.

---

### BLOCK 13 — Correct the SWR description and the finding-ID prefix (SRCH-014, VAL-005)

| | |
|---|---|
| **Findings owned** | `SRCH-014` (LOW) + `VAL-005` (LOW) |
| **Depends on** | **nothing in-plan** |
| **Blocks** | nothing |
| **Priority** | **P2** |
| **Risk level** | **LOW** — documentation only, no runtime behaviour |
| **Required agents** | **Auditor · Planner.** Implementor + inline verification. Validator not required — there is no behaviour to confirm |

**`SRCH-014`, and what is *not* wrong.** `search/services/cache.py::get_cached_search_ids`
says the stale value is returned immediately and the entry is *"refreshed in the background
by the single-flight winner"*. The code shows the opposite:
`_recompute_and_store` is called **synchronously** at the top of the stale branch and its
own docstring says it *"recomputes `producer()` SYNCHRONOUSLY (blocking its own
response)"*; the cold-miss winner carries the inline comment *"Winner: recompute
synchronously — the caller needs a result."* **The winner blocks its own response; the
losers return the stale value immediately.**

The `swr_cache` module docstring and its state-2 description are *imprecise* rather than
false. **Only the search call-site docstring is wrong.** This matters more than a normal
docstring because the claim is about **latency on the search hot path** — a reader sizing
the cache layer would budget a non-blocking refresh that does not exist. **Do not change
the helper**: inline recompute on the stale-winner path is a defensible design, and the
alternative needs a worker this deployment does not run.

**`VAL-005`, both halves.** The rewritten phase-08 handbook still mandates
`Finding-ID prefix: SRH-` in its report-output section while the executed cycle used
`SRCH-`. Separately, the shipped source carries hard-coded `SRH-001 … SRH-007` markers in
**eleven** places that refer to an unrelated in-code convention. Keep `SRCH-` — it is
unambiguous — and record the collision so no automation greps `SRH-` in this repository.
**The legacy in-source marker sweep is phase 03's**, and phase 03's plan explicitly
reserves it and forbids other phases from starting it (§5.2).

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/search/services/cache.py` | `get_cached_search_ids` — the docstring only | **No behaviour change.** The existing SWR tests must pass untouched |
| `.kilo/commands/audit/phases/08-audit-search-fts.md` | the "Finding-ID prefix" line | **Phase 08's own rubric** — phase 08 owns it. This is the one handbook edit this plan makes, and it is not a rubric-semantics edit |
| `docs/architecture/cache-strategy.md` | — | **BLOCK 6's file.** Do not edit it here |

**Binding constraints**

1. **Docstring only in `cache.py`.** No behaviour, no signature, no timing.
2. **Do not change `swr_cache.py`.**
3. **The handbook edit is the prefix line only** — not a rubric-semantics change. The
   DECLINE-semantics correction is already done (C-11) and is phase 06's / the
   coordinator's, not this block's.
4. **Do not start the `SRH-` in-source sweep.** Phase 03 reserved it.

**Implementor task**

```yaml
id: task_08_b13_swr_docstring_and_prefix
title: "Correct the SWR stale-read description and the phase-08 finding-ID prefix (08-SRCH-014, 08-VAL-005)"
priority: low
depends_on: []
source_reference: ".ai/plans/08-search-fts-remediation.md"
source_section: "BLOCK 13 - Correct the SWR description and the finding-ID prefix"
source_blocks: ["BLOCK 13"]
description: >
  get_cached_search_ids claims the stale value is "refreshed in the background by the
  single-flight winner", but swr_cache._recompute_and_store is called SYNCHRONOUSLY at
  the top of the stale branch and blocks its own response. A reader sizing the cache
  layer would budget a non-blocking refresh that does not exist. Correct the
  three-line docstring; do not change the helper - a background task would need a
  worker this deployment does not run. Separately, the phase-08 handbook still
  mandates the SRH- finding-ID prefix while the executed cycle used SRCH-; correct
  the prefix line and record the collision hazard.
files:
  - path: "src/backend/apps/search/services/cache.py"
    targets:
      - type: function
        name: get_cached_search_ids
  - path: ".kilo/commands/audit/phases/08-audit-search-fts.md"
    targets:
      - type: module
        name: "08-audit-search-fts"
changes:
  - action: modify_docs
    description: >
      Rewrite the stale-hit paragraph of get_cached_search_ids to state what the
      code does: losers receive the stale value immediately, the single-flight
      winner recomputes SYNCHRONOUSLY and blocks its own response, and callers
      should budget accordingly. Change the handbook's finding-ID prefix from SRH-
      to SRCH-, and note that SRH- already appears as an unrelated in-code
      convention in the shipped source so no automation may grep it.
acceptance_criteria:
  - "get_cached_search_ids' docstring matches what swr_cache._recompute_and_store does"
  - "swr_cache.py is byte-identical to before"
  - "test_search_cache.py passes UNCHANGED, including the 12 SWR state-machine tests"
  - "the phase-08 handbook's finding-ID prefix is SRCH- and mentions the SRH- collision"
  - "no in-source SRH- marker was changed and no source file outside cache.py was edited"
  - "the handbook's rubric semantics were not altered"
tests_to_run:
  - "src/backend/apps/search/tests/test_search_cache.py"
```

**Tests required** — none new. The **existing** `test_search_cache.py` SWR suite passing
unchanged is the control that the block changed documentation and not behaviour. §8.5
records that BLOCKS 2, 13 and 14 add **no** behavioural tests, deliberately.

**Risk and rollback**

- *Process risk:* a docstring edit is mistaken for a behaviour fix and "improved" in the
  same commit. Binding constraint 1; the unchanged SWR suite is the control.
- *Contention risk:* the handbook is audit-input territory. Phase 06's plan routes rubric
  corrections to the coordinator. **This block edits only its own phase's prefix line**;
  if a coordinator instruction broadens it, stop and report.
- *Rollback:* a straight revert.

---

### BLOCK 14 — Publish the ad-visibility predicate decision and the phase-06 handoff (SRCH-004, SRCH-008)

| | |
|---|---|
| **Findings owned** | `SRCH-004` (HIGH, **absorbed by `06-PII-104`**) + `SRCH-008` (MEDIUM — **owner decision TAKEN 2026-10-03**, option (a)) |
| **Depends on** | **nothing in-plan** |
| **Blocks** | the `IMMEDIATE_ALERTS_ENABLED` rollout gate; phase 06's `06-PII-104` acceptance |
| **Priority** | **P0** — the ruling is published and the handoff is owed; the code is phase 06's |
| **Risk level** | **Process** — no production behaviour ships. The cost of getting it wrong is a *second* predicate, or a moderation change mislabelled as a consent fix |
| **Required agents** | **Auditor · Researcher · Planner.** **Implementor not required** — this block ships no code. **Validator required** to confirm the ruling is published, uncontradicted, and cited by the tracker. Q7 and Q7′ are **answered**; the block's remaining job is publication and handoff |

**Why this block exists at all.** `SRCH-004` is already owned by phase 06 **verbatim**, and
phase 08 must not edit `alert_query.py`. But the finding will not be *closed* by silence: it
is live today on an **ungated** daily job. This block publishes the phase-06 handoff and, since
**2026-10-03**, the **Product Owner's ruling on `SRCH-008`** — option (a), a ban hides
inventory, plus the Q7′ write boundary. **It is placed late in the serial order only
because it needs no Implementor**; the Planner/Researcher may run it at any time, and
running it early is encouraged.

**The two predicates — do not conflate them.**

| | **(A) Ad-visibility predicate** | **(B) Audience / account-state predicate** |
|---|---|---|
| Question | *which ads are public?* | *which users / saved searches are eligible for proactive delivery?* |
| De-facto owner today | `apps/ads` — `ListingsQuery.build_queryset` | **nowhere**; `get_account_state()` is **instance-level** (`User → NamedTuple`) |
| Carried by | **`SRCH-004` + `SRCH-008`** | **`06-VAL-003` / `06-PII-104`** (phase 06) |
| Predicates on | `Ad` | `User` / `SavedSearch` |

They share the **enabling gap** — an instance-level function cannot be called from a
queryset filter, so nothing reusable exists, which is precisely why the rule was never
applied. **That is why both must be extracted together and land in one change.** But they
are not the same predicate, and a fix that satisfies one does not satisfy the other.
**One commit closes both; two commits would create two predicates.**

**The divergence, confirmed in the tree.**

| | Web (`/search/`, `/`) | Alert (`find_matching_ads`) |
|---|---|---|
| `status=PUBLISHED` | yes | yes |
| `user__is_declined=False` | **yes** | **no** |
| null-safe `Q(category__isnull=True) \| Q(category__is_active=True)` | **yes** | **no** |
| `user__is_banned=False` | **no — `SRCH-008`, ruled REQUIRED 2026-10-03** | **no — same ruling** |

`find_matching_ads` is literally `Ad.objects.filter(status=AdStatus.PUBLISHED)`, and the
alert path ships the result as a Telegram digest line (title + formatted price) — a
**wider** disclosure than any web surface, because it leaves the site.

**A recorded contradiction between this block's text and the 2026-10-03 Product Owner rulings.**
This block cites `technical-specification.md:101` — DECLINE *"hides the user's PUBLISHED ads
from public search/listings, direct URL access (`ad_detail`), and the `media_gate` non-staff
filter"* — as the reason an outbound digest to every matching subscriber is *"a deviation from
that statement"*. **The Product Owner ruled on 2026-10-03 that DECLINE is REVERSIBLE and that
already-published ads stay live until the seller acts** (`DECLINE` blocks publishing and
messaging; the login is regained; consent may be restored at any time), and that
**`technical-specification.md:101` and `docs/01-spec/spec-index.md:74` are superseded by that
product rule and must be corrected by their owning phase**. The spec line this block relies on
is therefore **no longer the rule**, and handoff item 1 below cannot be executed as written
until phase 06 reconciles it. This is **recorded, not resolved here** — phase 06 owns
`technical-specification.md` (BLOCKS 4/11/14) and `spec-index.md`. **The obligation is named in
§5.5.** The critical consequence the Owner attached: **with DECLINE reversible, the publish gate
is the ONLY control keeping a declined seller from posting**, so the missing `is_declined` term
on the *publish* path is the whole control rather than a partial one.

**Q7 RESOLVED 2026-10-03 (Product Owner) — does a ban hide inventory?**

**The ruling: option (a). A BAN HIDES INVENTORY.** A banned seller's ads are excluded from the
public ad-visibility predicate **across search, category, detail and the media gate**. The
options are retained below for traceability; **the decision is made** and no Implementor may
re-choose it.

**Two binding rules ride on this ruling, and both are about how the change is argued.**

1. **It must be argued as a MODERATION decision.** A ban is a seller-relationship sanction;
   removing inventory is part of that sanction, not a consent matter.
2. **It must NEVER be bundled into a commit justified as fixing a consent violation.** Doing
   so mislabels the change, makes it materially harder to review, and hides a moderation
   policy change inside a PII fix. The commit body must say *"moderation: a ban hides
   inventory"* in those words.

**Q7′ RESOLVED 2026-10-03 (Product Owner) — ban enforcement also covers creating and
publishing.** **A banned seller cannot create or publish a new ad.** Ban enforcement covers
**relisting**, not only login. Anywhere in the plan set the phrase *"a banned seller can still
relist"* is recorded as an accepted known gap, that gap is **now closed**, and the test that
documented it becomes a **positive control asserting the block**. `SRCH-008`'s scope therefore
covers a **read** boundary (visibility) **and** a **write** boundary (create/publish) — both
are phase 06's code.

| Option | What it is | Consequences |
|---|---|---|
| **(a) — CHOSEN 2026-10-03** | **Ban hides inventory.** Add `user__is_banned=False` to the shared predicate **and** to `ad_detail` / `media_gate`, and amend `db-schema.md:61` to state the scope explicitly | **Adopted.** A banned seller can no longer reach buyers through ads they can no longer manage; the four surfaces stop disagreeing. The `db-schema.md:61` amendment is **phase 06's file** and is a **propagation obligation**, not a phase-08 edit |
| ~~**(b)**~~ | **Ban does not hide inventory.** Document that takedown is performed by transitioning the ads through the moderation path | **REJECTED.** The operational burden of manual takedown is accepted by the owner. Recorded here so that the reasoning is not re-derived |

**Either way the answer belongs in `db-schema.md:61` and in the one predicate's docstring — and
now the answer is known.** Note `db-schema.md` is **phase 06's file** (its BLOCKS 13 and 17
edit the same lines) — the amendment is routed, not made here (§5.3).

**Decision required — Q6: where the ad predicate lives**

- It must be a **named querysets-level function owned by `apps/ads`** — the report's
  remedy, and the answer to why nothing was ever reusable.
- It must **not** be a default manager. Phase 06 forbids that explicitly for the audience
  predicate, and the mechanical reason is the bot's `AccountStateMiddleware._resolve_user`,
  which resolves users by `chat_id`: a manager-level filter would hide withdrawn users
  from the middleware and re-open a hole.
- It must be **confirmed against phase 06's BLOCK 6/7 output** before it is written, so
  the two predicates do not fork. That confirmation is **phase 06's to give**; this block
  records the requirement.

**What phase 06 must satisfy for `SRCH-004` to close (this block's handoff content)**

1. `find_matching_ads` applies the **same** ad-visibility terms as
   `ListingsQuery.build_queryset`: `user__is_declined=False` and the null-safe active
   category clause. **⚠ Premise changed 2026-10-03 — see the contradiction recorded above.**
   The `user__is_declined=False` term is derived from `technical-specification.md:101`, which
   the Product Owner's reversibility ruling **supersedes**: DECLINE no longer hides an
   already-published ad. **Phase 06 must reconcile this term against the corrected spec before
   the predicate is written**, and its decision must be recorded in the predicate docstring.
   Phase 08 does not choose; it records the conflict.
2. `user__is_banned=False` is applied **on all four public surfaces** — search, category
   listing, ad detail and the media gate — per the Q7 ruling. **Argued as moderation.**
3. A banned seller **cannot create or publish a new ad** (Q7′). Where phase 15 or phase 16
   records *"a banned seller can still relist"* as an accepted known gap, that gap is closed
   and the test becomes a **positive control asserting the block**.
4. A test asserts a DECLINED seller's ad and an INACTIVE-category ad are **excluded** from
   `find_matching_ads`, **and** that an eligible seller's ad is still included — the
   positive case matters as much as the exclusions. **With the reversibility ruling, the
   DECLINED-seller assertion is only valid for the *publish* path, not the visibility path** —
   phase 06 settles the exact shape.
5. `IMMEDIATE_ALERTS_ENABLED` stays `False` until **both** predicates exist. The immediate
   path additionally ships a **working deep link** to a hidden ad via `build_alert_message`,
   which is strictly worse than the digest's title + price.
6. The daily digest is **not** feature-gated and is live; the fix is required regardless of
   the immediate-path flag.

**Implementor task** — *none.* This block is a Planner/Researcher deliverable. No commit.

**Risk and rollback**

- *Risk:* the decision is made implicitly by whoever implements first, and phase 06 forks
  the predicate. Mitigation: this block is the published record; the tracker entry names
  the option; phase 06's `06-PII-104` acceptance criteria are written here so they cannot
  drift.
- *Risk:* a planner working from the report's file list tries to edit `alert_query.py` and
  collides with phase 06 BLOCKS 5/7 **and** phase 03 BLOCK 9 — a three-way contention on
  one file. Mitigation: binding constraint 1; §5.3 names the reservation.
- *Rollback:* none — nothing ships.
- *Cross-phase:* **this block's output is consumed by phase 06**, and it is the only
  phase-08 output another phase is waiting on.

---

## 4. Dependency graph

### 4.1 Execution order (the safe serial order)

One Implementor, strictly sequential. Every implementation block is one commit (§1.3).

| # | Block | Findings | Depends on (in-plan) | External gate | Risk |
|---|---|---|---|---|---|
| 1 | Bound `?features=` | `SRCH-001` | — | **Q2** (ceiling), **Q3** (whitelist cost); rollout gate `03-DB-004` | **CRITICAL** |
| 2 | `DB_MEM_LIMIT` declared | `VAL-001` | — | phase 02 / phase 06 own `.env*.example` | LOW |
| 3 | NUL rejection at both edges | `SRCH-006` | — | **Q4** (strip / reject / normalise) | HIGH |
| 4 | Redact the search log line | `SRCH-002` | 3 (soft) | — | MEDIUM |
| 5 | `popular_searches` unique | `SRCH-003` | — | **Q9** (reverse shape) | **HIGH** (migration) |
| 6 | Durable cache-version contract | `SRCH-007` | — | **Q1** (coordinator ruling) | **HIGH** |
| 7 | Consent-restoration invalidation | `SRCH-005` | 6 | **Q10** (test blast radius, pre-block) | **HIGH** |
| 8 | Bound `SavedSearch.query` | `SRCH-011`, `VAL-006` | 5 | **Q5** (redaction — phase 06) | MEDIUM (migration) |
| 9 | `get_client_ip` + budget table | `SRCH-010`, `SRCH-013` | — | — (also closes `04-AUT-003`) | MEDIUM |
| 10 | Ambiguous category name | `VAL-003` | — | — | MEDIUM |
| 11 | Single-word narrowing | `SRCH-009` | 10 | **Q8** (owner product) | MEDIUM |
| 12 | `has_results` derivation | `SRCH-015` | 7 (soft) | — | LOW |
| 13 | SWR docstring + ID prefix | `SRCH-014`, `VAL-005` | — | — | LOW |
| 14 | Predicate decision + handoff | `SRCH-004`, `SRCH-008` | — | **Q6**, **Q7** | process |

### 4.2 The DAG and why each edge exists

```
                       (none)                       (none)
                          |                            |
                          v                            v
                  [1 features bound]           [3 NUL rejection]  <-- Q2,Q3   <-- Q4
                          |                            |
                          |                            v
                          |                     [4 log redaction]
                          |
      (none) -----> [6 cache-version contract]  <-- Q1
                          |
                          v
                  [7 consent restoration]  <-- Q10
                          |            \
                          |             \ (soft)
                          |              v
      (none) -----> [5 popular_searches unique] <-- Q9
                          |            [12 has_results]
                          v
                  [8 SavedSearch bound] <-- Q5
                                                   (none)
       (none) -----> [9 client IP + budgets]        |
                                                   v
       (none) -----> [10 ambiguous name] ------> [11 narrowing] <-- Q8

       (none) -----> [13 docs]
       (none) -----> [14 predicate decision + handoff]  <-- Q6, Q7
```

**Each edge, with the reason it exists:**

| Edge | Why it exists |
|---|---|
| **3 → 4** (soft, correctness) | BLOCK 3 decides how a control character is handled **at the input edge**; BLOCK 4 changes what is **logged**. If BLOCK 4 lands first and BLOCK 3 then introduces a second normaliser, the logged value and the analysed value can normalise differently — an operator investigating a query sees something the search did not run. Under Q4 option (c) the two blocks share one function, which makes the edge a **shape** dependency as well as a correctness one. It is soft only in the sense that neither block fails to compile without the other |
| **5 → 8** (hard) | Both ship a migration in the **`apps/search` app**. Migration numbers are sequential per app, and phase 06 BLOCK 7 may also be allocating one. Landing 8 first forces it to take `0003` and pushes 5 to `0004` — workable, but it means the destructive dedup and the cheap bound land in an order nobody chose, and the §5.3 reservation list is wrong. **Sequence deliberately: the destructive migration first, while the blast radius is being reasoned about** |
| **6 → 7** (hard) | The report's rollout rule, verbatim: *"SRCH-005 and SRCH-007 must ship together or the restoration bug survives in a harder-to-reproduce form."* BLOCK 7's bump is correct but **unload-bearing only once the counter no longer resets to `1`**. Shipping 7 alone leaves the same user-visible outcome reachable by a second path; shipping 6 alone leaves the call site undeclared |
| **7 → 12** (soft) | BLOCK 12's reproduction **is** BLOCKS 6/7's stale-cache window. The report instructs that the fix "belongs with the cache-coherency work so it is not reverted by the next caching change". Placing 12 last means the next caching change sees it already fixed and cannot silently undo it |
| **10 → 11** (hard) | Under the **2026-10-03 Q8 ruling** the guess stays a single narrowed branch and BLOCK 11 adds a *control* rather than a *branch*. The edge survives on a different ground: **the control must render only for an unambiguous branch**, so BLOCK 11 cannot ship before BLOCK 10's ambiguity fix — otherwise it advertises a "search all categories" escape from an arbitrarily-guessed branch, which **widens recall to the wrong subtree** and is invisible. That is strictly worse than the hard filter and is exactly the defect `VAL-003` is filed for |
| **1 → (external `03-DB-004`)** | The report is explicit that `statement_timeout` is a **prerequisite** for `SRCH-001`'s remediation, not a duplicate of it: with zero repo hits and `SHOW statement_timeout → 0`, there is no server-side bound of any kind, so input validation alone leaves an unstated band of attacker-chosen query cost between 1 and the ceiling that still runs unbounded. **The commit may land; the rollout may not** (§4.4) |
| **9 → (external `04-AUT-003`)** | The identical mechanism in `login_rate_limit.py` is already filed as `04-AUT-003`, and phase 04's validator annotated it "search copy was missing from File(s)". One shared `get_client_ip` closes both. Phase 04 must be told so it does not ship a second, divergent fix — **this edge is external and phase 08 does not control it** |
| **8 → (external phase 09)** | **New edge, created 2026-10-03.** BLOCK 8 edits `save_search`'s `query` read (the bound) and phase 09's `09-API-012` edits the same read (the `redact_search_query()` call the Q5 ruling requires). **Sequenced, not parallelised**; the same file, two owners, two different concerns. §5.3 names the reservation |
| **8 → (external phase 06)** | `SavedSearch` is a phase 06 PII surface (`06-PII-104` retention, `06-PII-108` the sibling `query_normalized`). **Q5 is closed (2026-10-03):** the rule is "one rule for all query-persistence paths, keyed on the redacted form", and phase 06 owns writing it down. **Sequenced, not parallelised** |
| **14 → (external phase 06)** | BLOCK 14 publishes the acceptance criteria `06-PII-104` must satisfy and the `IMMEDIATE_ALERTS_ENABLED` gate. Phase 06's BLOCK 7 is the consumer. The coordinator sequences this, not the agents |

### 4.3 Where there is deliberately no edge, and why

| Pair with no edge | Why |
|---|---|
| **1 ↔ 3, 1 ↔ 8** | Three input bounds, three different fields (`feature_slugs`, `q`, `SavedSearch.query`), three different models. They share a **cause** (`BaseInputModel` carries only `extra="forbid"`) and were deliberately **not** given a shared abstraction (§6.2). With one Implementor they run in series anyway |
| **2 ↔ everything** | `VAL-001` is documentation and one env line. It touches no Python, no template and no migration, so it cannot break another block's gate. It is placed second only because it is the same rollout story as BLOCK 1 and reads better next to it |
| **3 ↔ 8** | Different endpoints (`/search/` and `/api/search/autocomplete` vs `POST /save-search/`), different models, different lengths. BLOCK 3 must not truncate `q` at 100 (C-3) and BLOCK 8 must not truncate `SavedSearch.query` at all — the two truncation contracts must stay separate, which is an argument **for** no edge |
| **6 ↔ 10** | BLOCK 6 changes the **lifetime** of `category:tree_version`; BLOCK 10 changes the **resolution logic** in `search.py` using the candidate list that key guards. BLOCK 6's commit body must state what the fuzzy-name key does under each Q1 option, and that is a *documentation* obligation, not a code edge. If BLOCK 10's implementation turns out to need a key change, the edge becomes real and BLOCK 6 must be re-read first |
| **9 ↔ 13** | A rate-limiter refactor and a docstring correction in different files with no shared symbol. They stay separate for **independent reviewability** |
| **11 ↔ 12** | A relevance change and a template-data-contract change. BLOCK 11 changes which rows match; BLOCK 12 changes how the rendered rows are described. Neither needs the other. Both touch `search.py`, which the one-Implementor rule serialises without a dependency edge |
| **13 ↔ 14** | One is a docstring in `cache.py` plus a handbook prefix line; the other is a decision record. No shared file, no shared decision, no shared risk |
| **14 → any implementation block** | BLOCK 14 ships no code. Its output is a **decision and a handoff**, and no block in this plan consumes either. Running it earlier would be fine and is encouraged (§3) |
| **BLOCK 1 ↔ the FTS trigger / `setup_search_triggers`** | There is no edge because this plan **must not** touch them. `ads_search_vector_update` is a `BEFORE INSERT OR UPDATE ON ads FOR EACH ROW` trigger pinned by `test_search_triggers.py`; phase 06 BLOCK 11 is explicitly barred from it and **no phase-08 block is added to that list** (§0.2.1, §6.3) |

### 4.4 The orders that are unsafe, and the one rollout gate

1. **BLOCK 7 before BLOCK 6** — the restoration bug is fixed on paper while a second,
   independent path to the same outcome stays open for 300 s after every reset. The report
   calls this "harder-to-reproduce"; it is also the case a test will not catch, because
   a test that waits 300 s does not exist.
2. **BLOCK 11 before BLOCK 10** — a disjunctive branch built on a first-hit resolution
   widens recall to an *arbitrary* branch. Strictly worse than the hard filter, and
   invisible, because the result set is still non-empty.
3. **BLOCK 8 before BLOCK 5** — the cheap bound takes `0003` and the destructive dedup
   takes `0004`, so the irreversible migration lands second with a different blast radius
   than the one this plan reasoned about.
4. **The UI feature cap after BLOCK 1's server cap** — if the shipped UI can already emit
   more than the chosen ceiling, the cap exposes a **separate UI defect** and breaks a
   legal query. The report is explicit: the cap must land **with or after** a UI cap,
   never before. BLOCK 1's binding constraint 4 makes this a stop-and-report, not a
   silent cap.
5. **The `?features=` cap rolled out before `03-DB-004` lands** — **this is the rollout
   gate, not a code gate.** The commit may merge; the deployment may not. With no
   `statement_timeout`, a legitimate-but-large filter set is still unbounded, and the
   report's own words are that the cap is *"currently the only thing between an attacker
   and a full outage."* §8.4 records the gate as open or satisfied.
6. **Any block enabling `IMMEDIATE_ALERTS_ENABLED`** — forbidden in every environment
   until both predicates exist. The daily digest is live and ungated today; the immediate
   path additionally ships a **working deep link** to a hidden ad.

### 4.5 What the DAG does *not* decide

The DAG orders blocks. It does **not** resolve Q1 … Q10. Each is a **gate inside a
block**, recorded in that block's `extra_context` and in §0.5, and §8.1 checks that a
written answer exists for each. **A block whose gate is unanswered does not start.**

---

## 5. Cross-phase coordination

Plans `.ai/plans/01-…` through `.ai/plans/07-media-remediation.md` exist; phases 06–15
are `planned` or are being planned in parallel right now by other Planner agents. This
section is the boundary contract. It is deliberately **one-directional**: phase 08 states
what it owns, what it will not touch, and where its boundaries lie. It does **not** attempt
to contact or negotiate with the other agents.

### 5.1 What phase 08 already owns and must not re-ship

| Phase 08 artefact | What phase 08 must not do | Boundary |
|---|---|---|
| **`SRCH-004` ≡ `06-PII-104` rec. 2, verbatim.** *"Also exclude ads whose owner is DECLINED from `find_matching_ads()` and `find_matching_saved_searches()`"* | **Phase 08 must not edit `apps/search/services/alert_query.py`.** Not the queryset, not the tests, not a "small interim filter" | Phase 06's BLOCK 7 is the single owner. BLOCK 14 publishes the handoff and the acceptance criteria. `alert_query.py` is a **three-way** reservation: phase 06 BLOCKS 5/7, phase 03 BLOCK 9, phase 08 **none** |
| **The ad-visibility predicate's *semantics*** | Phase 08 must not write the predicate, and must not fork it from phase 06's audience predicate | Phase 15's own handbook says predicate **semantics** are owned by phases 05/08 while phase 15 owns the **framework**. Phase 06 owns the audience half. Q6 records the constraint; BLOCK 14 routes the confirmation |
| **`docs/architecture/cache-strategy.md`** | Phase 08 must not edit it in any block other than BLOCK 6, and BLOCK 6 must edit it **in the same change** as the code | **No other phase claims it.** It currently prints the defective `cache.set(KEY, 1)` snippet as the canonical pattern — **phase 08 owns the fix**, and a code-only fix would leave the doc teaching the defect |
| **`SavedSearch.query`'s bound** | Phase 08 must not extend the block into a redaction change without phase 06's answer (Q5), and must not change the retention or erasure policy | `SavedSearch` is `CASCADE`-deleted 30 days after a consent withdrawal by design (`06-PII-104`). The **bound** is phase 08's; the **content** is phase 06's |
| **The `SRH-` / `SRCH-` convention** | Phase 08 must not start the legacy in-source marker sweep | Phase 03's plan **explicitly reserves** that sweep to itself and forbids other phases from starting it. Phase 08's own handbook prefix line is phase 08's (BLOCK 13); the eleven in-source `SRH-` markers are phase 03's |

### 5.2 What phase 08 must not do, for other phases' sake

| Other phase | What phase 08 must not do | Boundary |
|---|---|---|
| **Phase 03 — `DB-004` (`statement_timeout`), `DB-007` (alert delivery state)** | Phase 08 must not add `statement_timeout`, must not touch `config/settings/base.py`'s `DATABASES`, and must not change delivery state, the notification contract, or the `ALERT_DELIVERY_TASK` transaction boundary | `03-DB-004` is BLOCK 1's **rollout** gate (§4.4) and phase 03's code. `base.py` is the repo's most contended settings file; phase 08's only `base.py` interaction is reading `CACHES` and `IMMEDIATE_ALERTS_ENABLED` |
| **Phase 04 — `04-AUT-003`, `04-AUT-005`** | Phase 08 must not ship a second `_get_client_ip` fix and must not touch `UserAdmin`'s field contract | BLOCK 9's one shared helper **closes** `04-AUT-003`; phase 04 must be told so it does not fork it. `04-AUT-005` (`UserAdmin.fields/fieldsets`) is phase 04's alone — and note its interaction with BLOCK 7: making `is_declined` non-editable in the admin is what **guarantees** every consent transition goes through `give_consent`, which is the path BLOCK 7 makes self-invalidating |
| **Phase 05 — ad lifecycle** | Phase 08 must not touch `Ad.transition_to`, `ALLOWED_TRANSITIONS`, `search_vector*` columns, the `ads_search_vector_update` trigger, or the `setup_search_triggers` DDL | Phase 05's `§5.2` states this for phase 08. The trigger is a `BEFORE INSERT OR UPDATE ON ads FOR EACH ROW` trigger pinned by `test_search_triggers.py::test_title_update_refreshes_all_search_vectors` and `::test_category_name_i18n_edit_cascades_reindex`; **`VAL-009` is overstated** and **no phase-08 block builds a re-derivation mechanism** |
| **Phase 06 — `06-PII-104`, `06-VAL-003`, `06-PII-102`, `06-PII-108`** | Phase 08 must not edit `alert_query.py`, must not add a `User`-side consent predicate, must not add a **default-manager filter**, and must not build the logging-policy `Filter` | A default-manager filter would hide withdrawn users from the bot's `AccountStateMiddleware._resolve_user`, which resolves on `chat_id`. BLOCK 4 ships the **one call site**; the "one logging policy, enforced" root cause is phase 06's (`06-PII-102` validated rec. 5) and `SRCH-002` is its **third** instance |
| **Phase 12 — production ops** | Phase 08 must not write runbooks | BLOCK 2 states the parameter; phase 12 writes "what the DB memory budget is, what a crash recovery looks like, what happens on a 429". Phase 12 must also own the **rollback** framing for BLOCK 5's destructive dedup, and be told that a revert does not restore the data |
| **Phase 13 — performance** | Phase 08 must not make latency claims, add indexes speculatively, or `EXPLAIN` anything | Phase 13 grades GIN/trigram effectiveness **at legitimate volume**; phase 08 owns **attacker-chosen input volume** (handbook block: "bounded result sets to prevent DoS"). **Phase 13 must assume BLOCK 1 landed**, or it re-measures a phase-08-owned defect. The cache-version **lifetime** question is also phase 13's under handbook block 10 (Q1) |
| **Phase 14 — i18n** | Phase 08 must not regenerate locale files | `sanitize_query_for_log`'s `char.isalpha()` handling — which collapses Cyrillic and loses Serbian Latin characters and digits — degrades log triage and is **phase 14's** classification, recorded inside `SRCH-002` and routed (§5.6). BLOCK 11's new string, if any, is **appended**, never regenerated |
| **Phase 15 — authorization** | Phase 08 must not build a per-request authorization gate, and must not let predicate semantics be re-filed | `15-audit-authorization.md:132` is explicit: *"The 'what is public' predicate semantics are owned by Phase 05/08; Phase 15 verifies that non-public objects are not reachable through authorization failures."* Two of 15's risk rows will re-observe the same three-line problem from the enforcement side; they are **not** new findings |
| **Phase 11 — test coverage** | Phase 08 must not expand a required test rewrite into new coverage | BLOCK 7's rewrite of `test_give_consent_restores_declined_ads_to_queryset` is an **incidental rewrite required by a behaviour change**. Growing it raises the regression risk of the block |
| **Any phase — the audit input** | Phase 08 must not edit another phase's audit handbook or any `.ai/audit/**` file | The **one** exception is BLOCK 13's finding-ID prefix line in **phase 08's own** handbook. The DECLINE-semantics conflict is already resolved (C-11) and the general taxonomy defect is the coordinator's |

### 5.3 Shared-artefact reservations (the coordinator must sequence these)

| Artefact | Phase 08 claim | Conflict and rule |
|---|---|---|
| **`src/backend/apps/search/services/alert_query.py`, `immediate_alerts.py`** | **None.** | **Three-way.** Phase 06 BLOCKS 5/7 (eligibility), phase 03 BLOCK 9 (delivery state), phase 08 **none**. If either has landed, `SRCH-004`'s file must be **re-read, not assumed** |
| **`src/backend/apps/search/services/rate_limit.py`**, `apps/core/services/contact_rate_limit.py`, `apps/users/services/login_rate_limit.py` | **Phase 08: BLOCK 9** (all three) | Phase 04 holds `login_rate_limit.py` for `04-AUT-003`; phase 02 holds the **edge** limits (`CFG-*`, env plumbing). The three are compatible: BLOCK 9 changes the app policy's trust and table, phase 02 changes whether the edge limit is configured, and they are confirmed non-overlapping. **Re-read `login_rate_limit.py` before editing** |
| **`src/backend/apps/search/services/signals.py`** | **Phase 08: BLOCK 7** (adds a `User` receiver) | Phase 06 BLOCK 5 edits the same module for the immediate-alert log masking. **Sequenced, not parallelised.** Phase 06 BLOCK 7 is also nearby |
| **`src/backend/apps/users/services/deletion.py`** | **Phase 08: BLOCK 7** (option (b) only — three lines) | **Phase 06's most contended file**: its BLOCKS 9, 10, 11 and 13 all edit it, and `give_consent` / `decline_consent` / `withdraw_consent` / `soft_delete_user_ads` all live there. Under option (a) this block does not touch the file at all — **which is one more reason option (a) is preferable** |
| **`src/backend/apps/search/models.py` + `apps/search/migrations/`** | **Phase 08: BLOCKS 5, 8** | **The next free number is `0003`** — re-check the directory immediately before generating. **Phase 06 BLOCK 7 may add a `SavedSearch` migration.** Never renumber or edit an applied migration. BLOCK 5 before BLOCK 8 (§4.3) |
| **`src/backend/apps/search/views/save_search.py`** | **Phase 08: BLOCK 8** (the `query` length bound) | **New two-way reservation, created 2026-10-03 by the Q5 ruling.** Phase 09's `09-API-012` edits the same read to add the `redact_search_query()` call, and phase 06's `06-PII-108` owns the policy statement. Two owners, two concerns, **one file**. Sequenced, never parallelised; re-read immediately before editing and stop on a concurrent change |
| **`src/backend/apps/ads/services/listings_query.py`** | **Phase 08: BLOCK 1** (`feature_slugs`) | Phase 05 holds `apps/ads/models.py` and the next `ads/migrations/0008_*`; phase 15 audits permission predicates. BLOCK 1 touches the DTO field and reads the builder — it must not restructure `build_queryset`'s visibility terms, which are `SRCH-004`/`SRCH-008`'s surface |
| **`src/backend/apps/core/utils/sanitize.py`, `json_logging.py`** | **Phase 08: BLOCKS 3, 4** (shared helper neighbourhood) | Phase 06 BLOCK 5 touches the masking helpers nearby. `redact_search_query` and its never-lengthen invariant are **shared**: BLOCK 4 must not change it, and BLOCK 3 must not change `_MAX_QUERY_LENGTH` |
| **`src/backend/apps/categories/cache.py`, `categories/services/lookup_resolution.py`, `apps/lookups/services/cache_service.py`** | **Phase 08: BLOCK 6** (three of the four writers) | No other phase claims them. **Phase 13** claims key composition and lifetime as a grading concern; BLOCK 6 declares the contract, phase 13 grades it |
| **`docs/architecture/cache-strategy.md`** | **Phase 08: BLOCK 6** (sole owner) | No other phase claims it. Must change in the **same commit** as the code |
| **`docs/02-database/db-schema.md`** | **Phase 08: BLOCKS 5, 8** (the `popular_searches` and `saved_searches` rows) | **Phase 06 owns this file** (BLOCKS 13, 17 — the same lines `SRCH-008` wants to amend at `:61`). One commit each, different tables, disjoint regions; **re-read before editing**, and if a concurrent edit is present, stop and report |
| **`.env.prod.example` (and the other `.env*.example` files)** | **Phase 08: BLOCK 2** (one `DB_MEM_LIMIT` line) | **Phase 02 BLOCK 6 and phase 06 BLOCK 4** both own these files. Gated in **both** directions by `config/settings/tests/test_env_allowlist.py`. `docs/ops/docker-deployment.md` has **unstaged edits from another agent** in the working tree |
| **`docs/01-spec/technical-specification.md`** | **Phase 08: none, by design** | Phase 06 holds the reservation (BLOCKS 4, 11, 14). The advisory "state the `features` cardinality in the spec" is routed, not done — BLOCK 1 uses `docs/01-spec/search-patterns.md` instead, which no phase claims |
| **`src/backend/locale/*/LC_MESSAGES/django.po`** | **Phase 08: BLOCK 11** (a string is now added **unconditionally** — the 2026-10-03 Q8 ruling chose (b)+(c)) | Shared with phase 14 and phase 03. **Append; never regenerate.** `ru` and `bs` both non-empty |
| **`src/backend/conftest.py`** | **Nobody in this plan** | The most contended file in the repository. **No phase-08 block may edit it.** If a block appears to need a new fixture, that is a signal the test is over-fitted |
| **`.ai/audit/**`** | **Nobody.** Unmodifiable by mandate | 19 tracked deletions exist in the working tree. `git status --short .ai` must show **no new modifications** beyond the pre-existing deletions and this plan's own file |

### 5.4 The `SRCH-004` → `06-PII-104` handoff (and the `IMMEDIATE_ALERTS_ENABLED` gate)

**Recorded here so it is not lost, and so no one implements it twice.**

1. **`SRCH-004` is not phase 08's to fix.** `06-PII-104`'s validated recommendation item 2
   is verbatim. The two predicates are different (Ad vs User) and have different owners
   (`apps/ads` vs `apps/users`), but they share the enabling gap — `get_account_state()`
   is **instance-level** (`User → NamedTuple`), so no queryset filter can call it, and
   there is nothing to reuse, which is exactly why the rule was never applied. **That is
   why both must be extracted together and land in one change.** Phase 08's BLOCK 14
   publishes what `06-PII-104` must satisfy; phase 08's contribution is **one decision
   record and zero code**.
2. **What phase 06 must add that phase 08 deliberately does not** — a test that a DECLINED
   seller's ad and an INACTIVE-category ad are excluded from `find_matching_ads`, **and**
   that an eligible seller's ad is still included. The suite has **no** test on the alert
   path's visibility terms; the whole defect is invisible to it. Phase 08 writing that test
   today would **pin the defect** (it would be red) or require the code fix (which phase 08
   must not make). BLOCK 14 states the requirement instead.
3. **The gate.** `IMMEDIATE_ALERTS_ENABLED` defaults to `False`
   (`config/settings/base.py`, `env.bool(..., default=False)`, already in
   `ALLOWED_ENV_VARS`). It must stay `False` until **both** predicates exist. The daily
   digest is **not** feature-gated and is **live today** — which is why `SRCH-004` is HIGH
   and not MEDIUM. The immediate path additionally ships a **working deep link** to a
   hidden ad via `build_alert_message`, strictly worse than the digest's title + price.
   **Phase 08 does not enable it and does not change the flag.**
4. **What phase 15 must not re-file.** `15-audit-authorization.md:132` is explicit that
   predicate semantics are owned by phases 05/08 and 15 owns the framework. Two of 15's
   risk rows will re-observe this; they are the same three-line problem seen from the
   enforcement side, not new findings.

### 5.5 What phase 08 needs from other phases (forward dependencies)

| Phase | Phase 08 depends on it for | Risk if phase 08 is silent |
|---|---|---|
| **03 — `03-DB-004`** | `statement_timeout` on the `default` alias | The `?features=` cap becomes the **only** bound in the system, and any legitimate large filter set is still unbounded. Phase 08's BLOCK 1 commits; the **rollout** waits |
| **03 — the legacy `SRH-` sweep** | Removing the eleven in-source `SRH-` markers | Phase 03's plan reserves it; phase 08 must not start it. Until it lands, any grep for `SRH-` in this repo returns false matches |
| **06 — Q5** *(CLOSED 2026-10-03 — replaced by the propagation obligations below)* | ~~Whether `SavedSearch.query` needs redaction~~ — **answered: yes** | The question no longer exists. BLOCK 8 ships the bound; the redaction call is phase 09's and the policy statement is phase 06's |
| **06 — the PII policy statement (`06-PII-108`)** | **PROPAGATION OBLIGATION, 2026-10-03.** Record and own the rule that **every query-persistence path stores the redacted form, and `query_normalized` is keyed on the redacted form** — one rule, no exceptions. Owns `docs/01-spec/technical-specification.md`'s and the privacy page's search-query wording | BLOCK 8 and phase 09's `09-API-012` implement the rule; if phase 06 does not write it down, the third path added later stores raw queries again — which is exactly how this defect reached three writers |
| **06 — `06-PII-105` / `06-PII-113`** | **PROPAGATION OBLIGATION, 2026-10-03.** Correct `docs/01-spec/spec-index.md:74` and `docs/01-spec/technical-specification.md:101`, and make the **publish gate** the control it is now required to be | Both spec lines are **superseded** by the reversibility ruling. With DECLINE reversible, the publish gate is the **only** control keeping a declined seller from posting, so the missing `is_declined` term on that gate is the whole control, not a partial one. BLOCK 14 records the conflict; phase 06 owns the resolution |
| **06 — `db-schema.md:61`** | **PROPAGATION OBLIGATION, 2026-10-03.** Amend the `is_banned` row to state the ban's scope explicitly: the ads are excluded from search, category, detail and the media gate | Phase 06 owns `db-schema.md` (BLOCKS 13/17 edit the same lines). The asymmetry with the `is_declined` row at `:63` **was** the defect; the decision now exists, only the documentation does not |
| **06 — the ad-visibility predicate (`06-PII-104`)** | **PROPAGATION OBLIGATION, 2026-10-03.** `user__is_banned=False` on all four public surfaces, **argued as moderation**; and a banned seller **cannot create or publish a new ad** (relisting) | `SRCH-008` is decided but unimplemented. Phase 08 publishes it and ships no code. The commit must never be justified as fixing a consent violation |
| **06 — the predicate shape** | Confirmation of the audience predicate's shape before the ad predicate is written (Q6) | Two predicates fork, and the drift `VAL-003` exists to remove comes straight back |
| **12 — the runbooks** | Crash recovery, the memory budget, the 429 behaviour, the dedup rollback | An operator's first encounter with each is unguided. Phase 08 states the parameters; phase 12 writes the procedure |
| **13 — the `SRH-` / performance baseline** | A latency grading that assumes BLOCK 1 landed, and a ruling on Q1's lifetime half | Phase 13 re-measures an 08-owned defect as a 13 finding, and the key-lifetime question has no owner |
| **14 — `sanitize_query_for_log`'s character handling** | The `isalpha()` collapse of Cyrillic and the loss of Serbian Latin characters and digits | Incident triage stays degraded for two of three locales after BLOCK 4 replaces the helper. Recorded inside `SRCH-002`; classification is 14's |
| **Coordinator — `VAL-002`, `VAL-005`, Q1** | The audit-convention pass and the coordinator's ruling on the cache-version-key ownership | The convention is re-derived per phase, and `SRCH-007` is implemented by whichever phase claims it first |

### 5.6 Audit-pipeline artefacts — recorded, routed, not actioned

Two of this phase's `VAL-` findings are defects in the **audit input**, not in the product:

- **`VAL-002`** — the DECLINE-semantics conflict that once existed in three handbooks has
  been **resolved** by the 2026-09-28 wholesale rewrite (C-11). What survives is the
  *method* recommendation, now a convention rather than a file edit: **an assertion about
  product behaviour must be re-derived from the current spec, and an FTS or predicate
  assertion must carry a positive control rather than a "0 hits" observation.** BLOCK 14's
  verification rules already apply that convention to phase 08's own work (§0.2.1).
  **Routed to the coordinator**; no phase-08 file edit.
- **`VAL-005`** — the phase-08 handbook still mandates the `SRH-` finding-ID prefix while
  the executed cycle used `SRCH-`, and the shipped source carries eleven `SRH-NNN` markers
  from an unrelated convention. BLOCK 13 fixes **phase 08's own prefix line** and records
  the collision. **The in-source sweep is phase 03's** and is forbidden here. The
  remainder — any future tool keyed on `SRH-` — is **routed to the coordinator**.

Neither is a remediation item. Both are recorded so the final report and the next audit
run can act on them centrally rather than in every phase.

---

## 6. Out of scope for this plan

Every de-scoping below is **routed**, not dropped. A de-scoped item with no destination is
a re-filed finding.

### 6.1 De-scoped by ownership (routed, not dropped)

| Item | Routed to | Why |
|---|---|---|
| **`SRCH-004`** — the alert path's weaker visibility predicate | **Phase 06, `06-PII-104` (BLOCK 7)**, with phase 03 BLOCK 9 sequenced against it | Verbatim the same finding (C-12). `alert_query.py` is a three-way reservation and phase 08 must not touch it. BLOCK 14 publishes the handoff and the acceptance criteria (§5.4) |
| **`SRCH-008`** — no `is_banned` term in the public-visibility predicate | **Phase 06** — the predicate commit (`06-PII-104`) and the `db-schema.md:61` amendment (BLOCKS 13, 17) | **Q7 and Q7′ were DECIDED on 2026-10-03** (Product Owner): a ban hides inventory across search / category / detail / media gate, and a banned seller cannot create or publish a new ad. **Not implemented by this plan**; BLOCK 14 publishes the ruling, the moderation framing and the read + write boundaries (§5.5). The code change must never be bundled into a consent-fix commit |
| **The audience / account-state predicate** (`06-VAL-003`) | **Phase 06 (BLOCK 6)** | A different predicate on a different model, owned by `apps/users`. Phase 08 must not add it, and must not add a default-manager filter |
| **The project-level logging policy** — *"never log raw user input; log a normalised, redacted, truncated form"*, enforced by a shared formatter or filter | **Phase 06** (`06-PII-102` validated rec. 5) | `SRCH-002` is the **third** instance of the same "no declared logging policy" root cause. A point fix in `apps/search` closes this instance, not the class. Phase 08 ships the one call site and records the class |
| **`sanitize_query_for_log`'s `isalpha()` character handling** | **Phase 14** | It collapses Cyrillic and Montenegrin input to its letters and loses Serbian Latin characters and digits entirely, degrading log triage for two of three locales. Recorded inside `SRCH-002`; classification is deliberately deferred to avoid duplicating |
| **`statement_timeout` / `lock_timeout`** | **Phase 03, `03-DB-004`** | Zero repo hits in `src/` and `docker/`; `SHOW statement_timeout → 0` operationally. It is a **prerequisite** for `SRCH-001`'s remediation, not a duplicate — BLOCK 1's **rollout** gate |
| **The legacy `search_vector` column and `IX_ads_search_gin`** | **Phase 13** (Q8 in the code context) | `technical-specification.md` calls it "retained for backward compatibility only" and "a candidate for removal in a future migration". **No read path uses it**, but the trigger still maintains it and the GIN index still costs write amplification. Phase 13's index-grading scope. **Flagged, not actioned** |
| **`VAL-002`** — the audit-input convention ("re-derive product-behaviour assertions from the current spec; carry a positive control on any FTS/predicate assertion") | **Coordinator** (§5.6) | Largely resolved by the 2026-09-28 rewrite (C-11). What survives is a convention, not a file edit. Phase 08 applies it to its own work in §0.2.1 |
| **The `SRH-` → `SRCH-` legacy in-source marker sweep** (eleven places) | **Phase 03** | Phase 03's plan explicitly reserves the sweep and forbids other phases from starting it. Phase 08 fixes only **its own** handbook's prefix line (BLOCK 13) |
| **`VAL-004`** — the shared-test-database DoS hazard | **A standing constraint on this plan's verification** (§1.1), plus the coordinator for the repo-wide discipline | No code change is available. The repo encodes no private-instance discipline. This plan honours it by running BLOCK 1's crash reproduction on a private container |

### 6.2 De-scoped by design (deliberately not done here)

| Item | Why |
|---|---|
| **Required Fix 3 — a project-wide input-bounds framework on `BaseInputModel`** | `SRCH-001`, `SRCH-006` and `SRCH-011` share one cause: `BaseInputModel` carries only `extra="forbid"` and imposes no length, count or charset constraint, so every bound is a per-view convention that can be forgotten — and one already is (`SRCH-006`). The report asks for the boundary layer to declare bounds "once". **Declined**: the shared surface is three bounded edits, not a framework. A general bounds framework on the shared DTO base is a new abstraction with three consumers, would have to encode per-field policies it cannot know, and would change validation behaviour for every endpoint that already extends `BaseInputModel` — a blast radius far larger than the three findings. Project rule 5 applies. **What ships instead:** three explicit, individually-revertable bounds, plus one guard test per bound that asserts the bound exists (BLOCKs 1, 3, 8) |
| **A global logging `Filter` for raw user input** | The report's own advisory declines it: a naming-convention guard cannot see a value passed positionally, and its negative ROI at this project scale is high. The durable form — a typed identity value object — is a **new capability**, not a remediation. Phase 06 owns the policy question; phase 08 ships the one call site (BLOCK 4) |
| **A `_meta` introspection path on the search cache** (advisory 2) | It would turn `SRCH-015`'s fix into a read and give cache hit-rate work a single round trip. It is a **cache-shape redesign** with its own invalidation semantics, it interacts with BLOCK 6's Q1 decision, and it is not required by the finding. BLOCK 12 uses the one-line derivation, which is the whole of the remaining defect |
| **A `SELECT … FOR UPDATE` on the submission path** (advisory 1) | A cheap guard against two concurrent publishes interleaving a double `update(status=PUBLISHED)`. It is a mitigation for a risk **no finding owns** and it is in the bot's publish path, not the search path. Adopt deliberately or record the decision not to — it is not phase 08's work |
| **Stating the `features` cardinality in `technical-specification.md`** (advisory 4) | It would turn `SRCH-001` into a checkable rule. **`technical-specification.md` is phase 06's reservation** (§5.3). BLOCK 1 states the bound in `docs/01-spec/search-patterns.md`, which no phase claims, and the spec edit is routed to the coordinator |
| **A `pipeline`-level contract test for the rate limiters** (advisory 5) | Asserting that `get_client_ip` agrees with `$binary_remote_addr` under a hostile `X-Forwarded-For` is **exactly BLOCK 9's required test 1**, written at the unit level against the shared helper. A full pipeline test additionally requires a running nginx in the test environment, which the Compose test project does not provide. The unit-level assertion is the one that would have caught the defect |
| **Adding a result-count display to the search page** | The report's finding text implies a "N results" symptom. **`total_count` is never rendered in any template** (C-8), so there is nothing to fix there and a count display would be a **new UI decision** this phase's handbook does not cover. BLOCK 12 changes the derivation and adds no UI |
| **Pinning `CACHES["default"]["TIMEOUT"]`** | Explicitly forbidden. Raising or removing the default would silently extend the lifetime of **every** cache entry in the system. The defect is that a version key is treated as a cache entry, not that the default is wrong (BLOCK 6, binding constraint 2) |
| **Changing the nginx `limit_req` zones** | They key on `$binary_remote_addr` and are **not** spoofable, and the report confirms they are not bypassable. They bound the *edge*; BLOCK 9 is about whether the edge limit is the *only* limit and whether the app policy is trustworthy. Phase 02 owns edge configuration |
| **Measuring the alert path or the search path** | `VAL-006` and `SRCH-011` deliberately make **no** latency claim. Quantifying the cost of an unbounded `SavedSearch.query` evaluated N times on a schedule is **phase 13's** scope under handbook block 7/10. BLOCK 8 asserts **reachability**, not cost |

### 6.3 Explicitly forbidden while implementing

1. Editing `apps_search/services/alert_query.py`, `immediate_alerts.py`, or any other
   part of `06-PII-104` / `03-DB-007` / `06-PII-102` territory. `SRCH-004` is phase 06's.
2. Touching `ads_search_vector_fn`, `ads_search_vector_update`,
   `on_category_name_update`, `setup_search_triggers`, the `RunSQL` FTS DDL in
   `ads/migrations/0001_initial.py`, or any `search_vector*` column. **`VAL-009` is
   overstated — verify with one assertion, build nothing.**
3. Adding a `post_save` receiver on `Ad` that duplicates
   `bump_search_cache_on_ad_change`, or copying its `_SEARCH_RELEVANT_FIELDS` /
   `_SEARCH_RESULT_AFFECTING_STATUSES` shape into a `User` receiver. The field-set shape
   differs per model.
4. Adding a **default-manager filter** to `User` or `Ad`, or touching
   `AccountStateMiddleware` (bot), `can_login`, or `can_publish_ad`.
5. Enabling `IMMEDIATE_ALERTS_ENABLED` anywhere, or removing it from
   `ALLOWED_ENV_VARS`.
6. Renumbering or editing an applied migration in any app; generating a migration without
   re-reading the target directory.
7. Editing `.ai/audit/**`, another phase's plan file, `.kilo/commands/audit/phases/` for
   any phase other than **08's own prefix line**, or `src/backend/conftest.py`.
8. Starting the legacy `SRH-` in-source marker sweep.
9. `git reset` / `git checkout` / `git restore` / `git stash` / `--amend` / force-push, or
   reverting a file another agent changed.
10. Committing without an explicit instruction; committing more than one block in one
    commit; `git add -A` or `git add .`.
11. Writing a test that asserts a line number, a column count produced by introspection, a
    literal private name, a template-string substring, or the mere presence of a symbol.
12. Wrapping a database call in a blanket `try/except` to "fix" an input-rejection failure
    (`BLE001`).
13. Sleeping 300 s in a test to observe a TTL. Patch the clock or assert on the stored
    expiry.
14. Running a DoS-shaped probe against the shared `mko-bazuna-test` database (`VAL-004`).
15. Making an FTS-dependent assertion without first asserting `ads_search_vector_update`
    is present **and** running a positive control that must match.

---

## 7. Per-block risk register

Severity here is **this Planner's assessment of execution risk for the change**, not the
finding's severity. "Migration" covers DDL, data movement and rollback. "Irreversible"
covers operations whose data effect cannot be undone by a revert. "Contention" covers
shared files. "SLO" covers query-count, latency and cache behaviour. "Security" covers
trust boundaries and rate limits.

| Block | Risk | Kind | Likelihood | Impact | Mitigation / detection | Residual |
|---|---|---|---|---|---|---|
| **All** | An implementor works from the **report's** file list and blocks on `apps/ads/signals.py`, `apps/users/signals.py` or `docs/08-features/i18n.md` — none of which exist | Process | **High** | Med | C-1 is stated in §0.2, §1.4 and each affected block's file surface. The Auditor pre-step in §0.2.1 re-derives the true paths before BLOCK 7 starts | Very low |
| **All** | A block runs with its gate unanswered, or the Implementor silently picks an option | Process | Med | **High** | Every gate is a labelled block in §3 and a row in §0.5, repeated verbatim in the task YAML's `extra_context`; §8.1 checks a written answer exists for each | Low |
| **All** | A block's tests are **asserted** rather than **run**, or run on the host where there is no database | Process | Med | **High** | Every block names its exact Docker gate command; tests run **only** through the `test` service (§1.1) | Low |
| **All** | A red gate is captured while another phase's validator runs, and a teardown race is reported as a product defect | Process | **High** | Med | Concurrent runs collide on one `test_mko_bazuna`. Re-run serially before reporting. The symptom to recognise is `test_mko_bazuna does not exist` / `relation "..." does not exist` (§1.1) | Low |
| **All** | A shipped green test that **encodes a defect** is "fixed" by changing production code instead | Correctness | Med | **High** | Project rule 2 restated in §1.4. BLOCK 7's rewrite of `test_give_consent_restores_declined_ads_to_queryset` is the only unconditional rewrite, and its commit body must name the test and state that the old docstring documented the defect. BLOCK 3 and BLOCK 11 **constrain** four more and each justification is in its commit body | Low |
| **All** | A red gate captured during BLOCK 1's crash reproduction is reported as a product defect, or a probe takes the shared test DB into crash recovery | Process | Med | **High** | `VAL-004` is binding: BLOCK 1's reproduction runs on a **private** `postgres:18-alpine` on its own port. §1.1 and BLOCK 1's binding constraint 6 | Very low |
| **All** | An FTS-dependent test passes with **0 hits** because the probe did not inherit the session fixture that re-asserts `ads_search_vector_update` | Correctness | **High** | **High** | §0.2.1's Method-trap rule: assert `trigger_present` from `pg_trigger` **and** run a positive control that must match. No FTS result may rest on a "0 hits" observation. This trap already produced one near-miss false refutation in this phase's own evidence | Low |
| **All** | A new user-visible string ships without non-empty `ru` **and** `bs` | i18n | **High** | Med | BLOCK 11 adds a string — **now unconditionally**, because the 2026-10-03 Q8 ruling chose (b)+(c) rather than (b)-only. Append-only; the locale files are shared with phase 14 | Very low |
| **All** | A ruling is re-chosen by an Implementor, or a settled question is reported as still open | Process | Med | **High** | §0.7 records every 2026-10-03 ruling with its date, owner and chosen option. The Implementor is forbidden from choosing; the block's commit body names the ruling | Very low |
| **All** | An implementor "improves" production code to keep a test green rather than fixing the test | Correctness | Med | **High** | §1.4's production-code-is-king rule, restated per block. The three tests that constrain BLOCKs 3 and 11 are named explicitly so a change to any of them is deliberate and visible | Low |
| **1** | The ceiling ships as a bare literal, or the UI cap lands after the server cap | Rollout | Med | **High** | Q2 is **resolved** (option b): the bound is the catalogue invariant with stated headroom and a guard test whose failure is demonstrated. **Binding constraint 4 is unchanged** — the UI-cap finding is still a **stop and report** | Low |
| **1** | A per-slug membership query breaks `_QUERY_BOUND` and is "fixed" by raising the bound silently | SLO | **Low** (was Med) | **High** | Q3 is **resolved** as option (d) — the spec's correlated subquery, **no whitelist**, so no membership query ships at all. `test_search_query_count.py` and `test_search_slo.py` remain the tripwires | Very low |
| **1** | The catalogue grows past a ceiling measured once, and a legal query starts 400-ing | Regression | Med | Med | **This is the cost of the ruling and it is paid deliberately:** the guard test is the mitigation, and a category that outgrows the invariant fails CI with a named failure rather than a runtime 400 | Low |
| **1** | The cap is rolled out before `03-DB-004` | Availability | Med | **High** | A **rollout** gate, not a code gate (§4.4 item 5). §8.4 records it as satisfied or open. The commit body must say the cap is not the only bound | Low |
| **1** | The membership check is implemented as a per-request `LookupItem` queryset, making the fix worse than the defect on the hot path | SLO | Med | Med | Q3 option (c) is the single-lookup form; BLOCK 9's cache work is the precedent for reusing a cached slug set | Low |
| **2** | `.env.prod.example` or `docs/ops/docker-deployment.md` is edited on a stale read and a concurrent agent's work is clobbered | Contention | **High** | Med | §1.3's staging rule; both files are phase 02's / phase 06's surface and the ops doc already has uncommitted changes from another agent. Re-read immediately before editing; stop and report on a concurrent change | Med — accepted |
| **2** | The block invents a "expected" memory budget the profile does not actually use | Documentation | Med | Med | Binding constraint 3: if the value cannot be derived from the repository, the doc says so rather than guessing | Very low |
| **3** | The implementer wraps `_record_search_analytics` in a blanket `try/except`, converting a loud input rejection into a silent one | Correctness | Med | **High** | Binding constraint 1; `BLE001` is the tripwire; BLOCK 4's test also fails (the analytics no longer records) | Very low |
| **3** | `sanitize_query_for_log` is reused wholesale, silently truncating `q` from 200 to 100 | Regression | **High** | Med | C-3; binding constraint 2; `test_query_exceeding_max_length_returns_200` is the tripwire | Very low |
| **3** | Only `/search/` is fixed, leaving the `LIKE`-parameter path on the autocomplete endpoint reachable | Correctness | Med | **High** | Binding constraint 3; the block requires one test per endpoint because the two fail at different call sites | Low |
| **3** | The strip mutates a legal query's results, and the "positive control" is skipped | Product | **Med** | Med | **The mutation is now a decided behaviour (Q4, 2026-10-03)**, so the risk is that it goes unverified. The byte-identical-ads control is a mandatory acceptance criterion, not an optional test | Low |
| **4** | The Implementor redacts the value **before** the search, changing what is searched and what is cached | Correctness | Med | **High** | Binding constraint 1; the result-set, cache-key and analytics assertions are the tripwires | Very low |
| **4** | A blanket "log nothing" change passes the redaction test and destroys triage capability | Observability | Low | Med | Test 2 is the negative case: a query with no identifiers still logs | Very low |
| **4** | A global logging `Filter` is built "to be safe" | Design | Med | Med | Binding constraint 3; §6.2 records the decline and routes the policy to phase 06 | Very low |
| **5** | The dedup is applied and the migration is not reversible; a revert is believed to restore the data | **Irreversible** | Med | **High** | The commit body must state the pre- and post-dedup counts and the irreversibility **before** the block runs; the reverse is a `noop` by design; the Validator recounts independently (Q9) | Low |
| **5** | A naive `MAX(hit_count)` merge silently loses all popularity in a merged group | **Irreversible** | Med | Med | The arithmetic is stated in the task and asserted in test 2 (`3 + 5 → 8`) | Low |
| **5** | The migration number `0003` was taken by phase 06 BLOCK 7 | Migration | Med | Med | Re-check `apps/search/migrations/` immediately before generating; never renumber (§5.3) | Low |
| **5** | An existing duplicate pair already in a deployment makes the constraint fail at apply time | Migration | Med | Med | The dedup runs **before** the constraint **in the same migration**, so it cannot. If the dedup's grouping misses a case (e.g. case or whitespace differences), the `AddConstraint` fails loudly rather than corrupting — and the Validator runs `--create-db` | Low |
| **6** | Phase 08 ships phase 13's work, or declines phase 08's | Process | **High** | **High** | Q1 is a labelled **coordinator** gate with three options and their consequences; the commit body names the chosen option | Low |
| **6** | The helper is built but only two of the four writers are migrated, leaving two live self-evictions | Correctness | Med | **High** | Binding constraint 1 — "never leave three behind" — and the block requires one assertion per writer that its key carries no bounded TTL | Low |
| **6** | A cache-key **shape** change breaks 14 pinned tests | Regression | Med | Med | Binding constraint 5; `TestSearchCacheKey` is the tripwire; `invalidate_search_cache` must not be deleted (it is asserted) | Low |
| **6** | `CACHES["default"]["TIMEOUT"]` is pinned as a "cleaner" fix, silently extending every cache entry's lifetime | Regression | Low | Med | Binding constraint 2, stated explicitly in §1.4. This is the one wrong fix that looks obviously right | Very low |
| **6** | The doc is updated in a separate commit and never happens | Documentation | Med | Med | Binding constraint 3 — the doc amendment is in the **same** change; §8.4 checks the doc no longer prints the defective snippet | Low |
| **7** | The receiver is **wired but never imported**, so the fix looks present and the defect survives | Correctness | **High** | **High** | Test 2 asserts `get_search_version()` strictly increases across the transition; a test that fires, not an inspection of the wiring; the Validator must confirm it fires. Option (b) has no wiring risk, which is part of the trade | Low |
| **7** | The receiver over-bumps on every `User.save()` | Performance | Med | Med | Test 3 asserts an unrelated-field save does **not** bump | Low |
| **7** | The `User` receiver is copy-pasted from the `Ad` receiver and inherits its `update_fields` / `_SEARCH_RESULT_AFFECTING_STATUSES` shape | Correctness | Med | Med | Binding constraint 3; the binding constraint names the two `Ad` symbols that must **not** be copied | Low |
| **7** | `deletion.py` is edited on a stale read and phase 06's `give_consent` / `decline_consent` work is clobbered | Contention | Med | **High** | Phase 06's most contended file (§5.3). Re-read before editing; under option (a) the file is not touched at all | Low |
| **8** | An existing saved search already holds an over-cap value and the `AlterField` fails in production | Migration | Med | **High** | The migration must inspect and handle the existing population, and the commit body states what it did with it. A bare `AlterField` that fails in production is not a ship | Low |
| **8** | The boundary **truncates** instead of refusing, silently changing what a saved search matches | Product | Med | Med | Binding constraint 2 forbids truncation; test 1 asserts a refusal with nothing stored | Low |
| **8** | A DTO is introduced on `save_search` "while we are there" (C-6) | Scope | Med | Low | Binding constraint 3: a DTO is a scope expansion and must return to the Planner | Very low |
| **8** | ~~The block is redaction without phase 06's answer (Q5)~~ — **CLOSED 2026-10-03** | — | — | — | Q5 is **resolved**: `SavedSearch.query` is stored redacted and `query_normalized` is keyed on the redacted form. Replaced below by the real residual risk | Closed |
| **8** | The Implementor adds the `redact_search_query()` call here "because the ruling says redact", landing phase 09's and phase 06's work in phase 08 | Scope | **Med** | Med | Acceptance criterion: no redaction call in `save_search` by this block. `09-API-012` + `09-VAL-002` own it; §5.5 names both | Very low |
| **8** | Phase 08 BLOCK 8 and phase 09 BLOCK 13 collide on `save_search.py` | Contention | Med | Med | §5.3 names the shared file; re-read immediately before editing and stop on a concurrent change | Low |
| **8** | The block makes a latency claim about the alert path | Scope | Med | Low | Binding constraint 5; `VAL-006` and `SRCH-011` deliberately make none. Phase 13 owns it | Very low |
| **9** | The Implementer reads `XFF[0]` and the defect survives with a different shape | Security | Med | **High** | Binding constraint 2; test 1 (rotating vs fixed XFF maps to one key) is the tripwire, and the Validator may reject the block | Very low |
| **9** | The key-namespace refactor merges `{namespace}_rl:{ip}` and `telegram_dl_rl:{ip}` and one limiter's counters contaminate the other | Correctness | Med | Med | `test_search_and_autocomplete_use_independent_counters` is the tripwire and must not be weakened | Low |
| **9** | The shared 429 shape changes what `/` returns, breaking a consumer that expects an empty body | Behaviour | Med | Low | The point of the change; state it in the commit body | Very low |
| **9** | Phase 04 ships its own `_get_client_ip` fix and the two diverge | Process | Med | Med | §5.2 and §5.4: one commit closes `04-AUT-003` and phase 04 must be told. The coordinator sequences, not the agents | Low |
| **10** | "Ambiguous ⇒ no guess" is over-applied and the narrowing stops working for every query | Regression | Med | Med | Test 2 (an unambiguous name still narrows) is the control | Low |
| **10** | The name→ids index is computed per request instead of from the cached candidate list, breaking the zero-SELECT property | Performance | Med | Med | `test_search_fuzzy.py`'s zero-SELECT test is the tripwire; binding constraint 3 | Low |
| **10** | The Implementer "fixes" this by adding a unique constraint on `Category.name` | Scope | Low | Med | Binding constraint 4 forbids it: it needs an i18n migration and a catalogue decision, and translated names can legitimately collide | Very low |
| **10** | The reproduction runs on a stale schema and a correct fix looks broken | Method | Med | Med | §0.2.1 row 9: wipe the rows, re-assert the trigger, then assert. This exact artefact produced a false refutation in the phase's own evidence | Low |
| **10** | Only the fuzzy path is fixed and the exact path keeps returning an arbitrary branch (C-9) | Correctness | Med | **High** | Binding constraint 1; the block requires the ambiguity case asserted through **both** paths | Very low |
| **11** | Q8 answered implicitly, or answered as the rejected disjunctive branch (option (a)) | Process | Med | **High** | **Q8 is resolved 2026-10-03** as (b)+(c). The block's file surface no longer lists `search.py`; the two pinning tests must be green **unchanged**. A PR that rewrites either test is reversing an owner decision and needs the owner | Very low |
| **11** | The undo control is wired as a category filter that bypasses the visibility predicate, and a non-PUBLISHED ad in a descendant becomes visible | Correctness | Med | **High** | Test 2 must be asserted **with the control rendered**, not instead of it. `test_single_word_category_match_rejects_non_published_descendants` is the existing tripwire and is now also the specification | Low |
| **11** | The heavier predicate breaks `_QUERY_BOUND` or the 2 s SLO | SLO | **Low** (was Med) | Med | **No predicate changes under the ruling**, so this is expected to be free — but both gates stay in `tests_to_run` and the measurement is recorded rather than assumed | Very low |
| **11** | The i18n gate fails on `ru` / `bs` and it is triaged as a regression | i18n | **High** | Low | A **consequence** of the fix (§1.2). The `.po` update is in the same commit as the template change | Very low |
| **12** | "No results" and "page out of range" are conflated, so a valid page number renders the empty state | Regression | Med | Med | The derivation must distinguish the two; the out-of-range case is the test that distinguishes them | Low |
| **12** | The implementer "simplifies" by changing `_resolve_search_count` or adding a second count | Correctness | Med | Med | Binding constraints 2 and 4; `TestSearchViewTotalCount`'s three tests, including the exact `COUNT(*)` at the cap, are the tripwire | Low |
| **12** | A result-count display is added as a "fix" | Scope | Med | Low | C-8 and binding constraint 3; §6.2 records the decline | Very low |
| **13** | A docstring change is "improved" into a behaviour change (e.g. an actual background refresh) | Design | Med | Med | Binding constraints 1 and 2; the 12-test SWR suite is the control, and a background task would need a worker this deployment does not run | Very low |
| **13** | The handbook edit is broadened into a rubric-semantics change | Process | Low | Med | Binding constraint 3: the prefix line only. Phase 06's plan routes rubric corrections to the coordinator | Very low |
| **14** | ~~The decision is made implicitly by whoever implements first~~ — **CLOSED 2026-10-03**; Q7 and Q7′ are decided | — | — | — | Replaced by the two rows below | Closed |
| **14** | `is_banned` is added and the commit is justified as "fixing a consent violation" | Product / Review | Med | **High** | **Now a binding constraint, not a warning** (ruling 2026-10-03): the change must be argued as a **moderation** decision and must never ship inside a consent-fix commit. The commit body must say so in those words | Very low |
| **14** | Phase 06 writes the predicate against the **superseded** DECLINE semantics while reconciling the spec, and ships `user__is_declined=False` on the visibility path against the reversibility ruling | Process | Med | **High** | Recorded as an explicit contradiction in the block; §5.5 names phase 06's obligation for `spec-index.md:74` and `technical-specification.md:101`, and `06-PII-105` / `06-PII-113` for the publish gate. Phase 08 chooses nothing | Low |
| **14** | The Q7′ write boundary (create/publish) is read as a visibility term and no publish gate is written | Correctness | Med | **High** | Handoff items 2 and 3 state the read boundary **and** the write boundary separately; where a plan records *"a banned seller can still relist"* as an accepted gap, the known-gap test becomes a **positive control asserting the block** | Low |
| **14** | A planner working from the report's file list edits `alert_query.py` and collides with phase 06 **and** phase 03 | Contention | Med | **High** | §4.3's "no edge" table, §5.1 and §5.3 name the three-way reservation; the block's own file surface is documentation only | Very low |
| **14** | `is_banned` is added and the commit is justified as "fixing a consent violation" (historical row, retained for traceability) | Product / Review | Med | Med | **Superseded by the row above** — the option-(b) alternative was rejected on 2026-10-03, and the moderation framing is now mandatory | Very low |

---

## 8. Definition of done for the whole plan

Phase 08 is complete when **all** of the following hold.

### 8.1 Scope

- [ ] All 21 items have a recorded disposition: **17 implemented** (`SRCH-001`, `002`,
      `003`, `005`, `006`, `007`, `009`, `010`, `011`, `013`, `014`, `015`,
      `VAL-001`, `VAL-003`, `VAL-005`, `VAL-006`) — plus the `SRCH-015` remainder,
      **1 absorbed by another phase** (`SRCH-004` → `06-PII-104`), **2 routed to owners
      or phases** (`SRCH-008` → **ruled 2026-10-03, implemented by phase 06**; the
      logging-policy class → phase 06),
      **1 already fixed** (`SRCH-012`, restated so it is not silently re-filed),
      **2 process-only** (`VAL-002` routed to the coordinator, `VAL-004` honoured as a
      verification constraint), **0 rejected**.
- [ ] Every gate-bearing block (**1, 3, 6, 7, 8, 11**) has a **written** decision for its open
      question, naming the option chosen and the consequences accepted. **Silence is not
      an acceptable outcome for any of them.** **As of 2026-10-03 this is satisfied for
      BLOCKS 1, 3, 8 and 11 by §0.7; BLOCK 6's Q1 remains a coordinator ruling and BLOCK 7's
      Q10 was answered 2026-10-01.**
- [ ] Each of Q1 … Q10 (and **Q7′**) is either answered with a record, or explicitly re-routed
      with a named destination. **Q1 is a coordinator ruling.** Q2, Q4, Q5, Q7, Q7′ and Q8 were
      **owner decisions, all taken on 2026-10-03** (§0.7); Q3, Q6, Q9 and Q10 are
      engineering/Researcher steps, and **Q6 remains phase 06's predicate ownership**.
- [ ] The four **propagation obligations owed to phase 06** by the 2026-10-03 rulings are
      named in §5.5 and communicated to the coordinator: the `06-PII-108` one-rule policy
      statement; the `06-PII-105` / `06-PII-113` corrections to `spec-index.md:74` and
      `technical-specification.md:101` and the publish gate; the `db-schema.md:61` `is_banned`
      amendment; and the `SRCH-008` predicate including the **relist** write boundary.
- [ ] The `SRCH-004` → `06-PII-104` handoff (§5.4) was communicated to the coordinator,
      including the two acceptance criteria phase 06 must satisfy and the
      `IMMEDIATE_ALERTS_ENABLED` gate.
- [ ] The `SRCH-010` → `04-AUT-003` closure was communicated, so phase 04 does not ship a
      second, divergent fix.
- [ ] Every de-scoping in §6 has a named destination.

### 8.2 Gates — all green

- [ ] `uv run ruff check src/` → exit 0.
- [ ] `uv run basedpyright src/` → **0 errors**.
- [ ] `.\Makefile.ps1 test` → full suite green (seed marker skipped).
- [ ] `.\Makefile.ps1 test-recreate` executed **once after BLOCK 5's migration** and
      **once after BLOCK 8's migration**.
- [ ] `makemigrations --check` clean after BLOCKS 5 and 8.
- [ ] `config/settings/tests/test_env_allowlist.py` green after BLOCK 2 — **in both
      directions**.
- [ ] `apps/ads/tests/test_i18n_completeness.py` green after BLOCK 11 (if a string was
      added).
- [ ] Every block's exact gate command from §3 was run and green, **not** the full suite
      alone; `ruff` / `basedpyright` re-run after every block, not only at the end.
- [ ] `git status --short .ai` shows **no new modifications** beyond the pre-existing
      `.ai/audit/**` deletions and this plan's own file.
- [ ] Every red-gate observation was **re-run serially** before being reported as a defect
      (§1.1).
- [ ] BLOCK 1's crash reproduction, if performed, ran on a **private** `postgres:18-alpine`
      container on its own port — never on `mko-bazuna-test` (`VAL-004`).
- [ ] No commit was made without an explicit user request; no `git reset`, `git checkout`,
      `git restore` or `git stash` was run at any point.

### 8.3 Per-item behavioural confirmation

- [ ] `SRCH-001` — a `?features` list one over the invariant is rejected with a 4xx on
      `/search/` **and** `/`; the ceiling is derived from the catalogue at seed volume with
      **stated headroom**, not a hard-coded literal; the invariant guard test has been
      **demonstrated red**; a list at the ceiling containing a nonexistent slug is
      rejected and no join is emitted for it; a legal list of size 3 returns exactly the
      ads carrying all three features. `test_features_filter.py` passes **unchanged**;
      `_QUERY_BOUND` and the 2 s SLO pass. The Q2 option (b) and Q3 option (d) are named
      in the commit body together with the measured catalogue maximum, and the UI-cap
      check is recorded.
- [ ] **`VAL-001`** — `.env.prod.example` states the memory budget the profile expects and
      that changing it is a capacity decision; `statement_timeout` is named as `03-DB-004`;
      `docker-compose.yml` and `config/settings/base.py` are unchanged.
- [ ] **`SRCH-006`** — a NUL byte in `q` returns 200 on `/search/` **and** on
      `/api/search/autocomplete` with no `DataError`; `\x07` and the homoglyph payload
      still return 200; **a legal query returns byte-identical ads before and after the
      change** (the Product Owner's mandated positive control); the 200-char `q` contract and
      the 100-char log contract are asserted **separately**, and `sanitize_query_for_log`
      was **not** reused wholesale on the search input edge; no blanket `try/except` was
      added around any DB call.
- [ ] **`SRCH-002`** — the rendered production line for a zero-result search containing a
      phone number, an e-mail address and a multi-word capitalised name contains **none**
      of the three; a query with no identifiers still logs; the result set, cache key,
      analytics rows and tsquery are byte-identical to before;
      `increment_popular_search` and `record_search_history` are unchanged;
      `test_redact_search_query.py` is green unchanged.
- [ ] **`SRCH-003`** — no two `PopularSearch` rows share `query_normalized`; merging a
      group of 3 and 5 yields one row with 8; the later `last_searched_at` survives;
      inserting a duplicate raises `IntegrityError`; `GET /search/?q=…` returns 200 after a
      duplicate pair is attempted; `migrate back` runs cleanly and does not recreate the
      removed rows; `0001` and `0002` are byte-identical.
- [ ] **`SRCH-007`** — a version key written through the helper survives past
      `DEFAULT_TIMEOUT`; a key built before the window is **not** byte-identical to one
      built after a bump; **all four** writers use the helper and a grep finds no
      remaining bounded-TTL `cache.set(KEY, 1)`; `CACHES["default"]` gained no `TIMEOUT`;
      `test_search_cache.py` passes **unchanged** (all 14 `TestSearchCacheKey` cases and
      the `invalidate_search_cache` alias);
      `docs/architecture/cache-strategy.md` no longer prints the defective snippet as the
      pattern; the Q1 option and the fifth consumer's behaviour are named in the commit
      body.
- [ ] **`SRCH-005`** — decline → load the search page → `give_consent` makes the ad
      visible through the **view** with the cache warm and no manual bump;
      `get_search_version()` strictly increases across the transition; an unrelated-field
      `User.save()` does **not** bump; `withdraw_consent` and `decline_consent` are green
      unchanged; the rewritten test no longer asserts against
      `ListingsQuery.build_queryset` and its docstring no longer claims the omission is
      intentional; `AccountStateMiddleware`, `can_login` and `can_publish_ad` are
      unchanged and no default-manager filter was added.
- [ ] **`SRCH-011` / `VAL-006`** — a query at the cap round-trips byte-identical; one over
      the cap is refused with a 4xx and nothing is stored; **a non-view writer is rejected
      by the model**, which is what distinguishes a model bound from a view-only cap; an
      over-cap value cannot reach `send_alerts._collect_alerts`; `test_alert_query.py` is
      green unchanged; **no timing measurement, `EXPLAIN` or index work** was done; **no
      `redact_search_query()` call was added by this block** — the redaction is phase 09's
      `09-API-012` / `09-VAL-002` and phase 06's `06-PII-108` under the 2026-10-03 Q5 ruling,
      and the commit body names that ruling rather than recording an open question.
- [ ] **`SRCH-010` / `SRCH-013`** — a rotating and a fixed `X-Forwarded-For` reach the
      same limiter key; `X-Real-IP` wins over `XFF`; `REMOTE_ADDR` is the last fallback;
      refusals occur in the same proportion under a rotating header; `/search/` and `/`
      return the same 429 body; both `TestSearchViewRateLimit` tests are green
      **unchanged**; the budgets are a `StrEnum` with a written rationale; no
      `_get_client_ip` remains outside `apps/core`; `nginx.conf` is unchanged.
- [ ] **`VAL-003`** — two active categories sharing a localised display name cause a
      single-word search to return **no** category narrowing, and the ad in the other
      branch is visible; an unambiguous name still narrows; a slug match still scopes; the
      warm-cache path still performs **zero** category SELECTs; `test_search_fuzzy.py`
      passes **unchanged**; `Category.name` still has no unique constraint.
- [ ] **`SRCH-009`** — the Q8 ruling **(b)+(c), dated 2026-10-03, with option (a) explicitly
      rejected** is named in the commit body; the one-word narrowing **still narrows**
      (`_apply_fts_filtering` and `_is_single_word` byte-identical); the results page renders
      the *"showing results for &lt;Category&gt; only — search all categories"* control and its
      link widens the query to the whole tree; `ru` **and** `bs` are non-empty; non-PUBLISHED
      descendants and inactive categories stay **excluded with the control rendered**;
      `TestSearchViewDescendantCategories` is green **unchanged** — neither test rewritten nor
      weakened; a multi-word query is unchanged; `_QUERY_BOUND` and the 2 s SLO are green with
      the measurement recorded; `technical-specification.md` is unchanged.
- [ ] **`SRCH-015`** — with a warm cache and an ad that no longer matches the live
      predicate, the page renders the **empty state** (not a blank area) at HTTP 200;
      `TestSearchViewTotalCount` passes **unchanged** (all three, including the exact
      `COUNT(*)` at the cap and the cold-miss-loser path); `total_count` and
      `results_truncated` are unchanged; **no count display was added** and no second
      count query exists.
- [ ] **`SRCH-014` / `VAL-005`** — the `get_cached_search_ids` docstring matches what
      `_recompute_and_store` does; `swr_cache.py` is byte-identical;
      `test_search_cache.py` passes **unchanged**; the handbook's prefix is `SRCH-` and
      records the `SRH-` collision; **no in-source `SRH-` marker was changed** and the
      rubric's semantics were not altered.
- [ ] **`SRCH-004` / `SRCH-008`** — the record names the **2026-10-03 Product Owner rulings**:
      Q7 (**a ban hides inventory**, across search / category / detail / media gate, argued as
      a **moderation** decision and never bundled into a consent-fix commit) and Q7′ (**a banned
      seller cannot create or publish a new ad**); the **read** boundary and the **write**
      boundary are stated separately; the contradiction between this block's DECLINE premise and
      the reversibility ruling is recorded with the phase-06 obligation it creates; Q6's
      predicate-ownership constraint is recorded; phase 06's acceptance criteria for the alert
      path are published; `IMMEDIATE_ALERTS_ENABLED` was **not** enabled anywhere;
      `apps/search/services/alert_query.py` is **byte-identical** to before.

### 8.4 Cross-phase integrity

- [ ] `apps/search/services/alert_query.py` and `immediate_alerts.py` are **unchanged**
      by every phase-08 block. `SRCH-004` remains `06-PII-104`'s alone.
- [ ] No `User` or `Ad` default-manager filter was added; `AccountStateMiddleware` (bot)
      is unchanged; its `test_backfill_uses_stable_chat_id` and `_check_user_state(chat_id)`
      tests pass **unchanged**.
- [ ] `IMMEDIATE_ALERTS_ENABLED` is still `False` by default and still in
      `ALLOWED_ENV_VARS`; `find_matching_ads` still starts from
      `Ad.objects.filter(status=AdStatus.PUBLISHED)` (phase 06's to change).
- [ ] The FTS trigger, `ads_search_vector_fn`, `on_category_name_update`,
      `setup_search_triggers` and every `RunSQL` block in `ads/migrations/0001_initial.py`
      are **byte-identical**; `test_search_triggers.py` and `test_setup_search_triggers.py`
      pass **unchanged**. **No re-derivation mechanism was built.**
- [ ] `config/settings/base.py` gained no `statement_timeout` and no
      `CACHES["default"]["TIMEOUT"]`; `CACHES` is unchanged.
- [ ] `docker-compose.yml` is unchanged; the `SRCH-001` **rollout** gate
      (`03-DB-004`) is recorded as satisfied or still open, with its state named.
- [ ] `docker/nginx/nginx.conf` is unchanged.
- [ ] `apps/search/models.py` and `apps/search/migrations/` were edited only in BLOCKS 5
      and 8, in that order; no applied migration was renumbered or edited; the migration
      numbers were checked against the directory **immediately before** generation.
- [ ] `src/backend/conftest.py` is **unmodified**.
- [ ] `docs/01-spec/technical-specification.md` is **unmodified** by this plan.
- [ ] `docs/02-database/db-schema.md` was touched only in BLOCKS 5 and 8, in disjoint
      regions, and re-read first; `docs/architecture/cache-strategy.md` was touched only
      in BLOCK 6 and only in the same commit as the code.
- [ ] `.env*.example` was touched only in BLOCK 2, one line, after a re-read; no other
      phase's env work was reverted.
- [ ] Locale files were **appended** to, never regenerated wholesale; `ru` and `bs` are
      non-empty for every new or changed string.
- [ ] `.kilo/commands/audit/phases/08-audit-search-fts.md` was touched only at its
      finding-ID prefix line; **no other phase's handbook was edited.**
- [ ] The `SRH-` in-source marker sweep was **not** started.
- [ ] The audit tree shows no new modifications; no other phase's plan file was edited.

### 8.5 Project conventions

- [ ] Every new constant is a named module-level constant or a `StrEnum` member, never an
      inline literal or a dict-of-strings (project rule 10).
- [ ] No `print()`; `logger = logging.getLogger(__name__)` with lazy `%s` formatting. The
      dedup migration logs its row counts this way.
- [ ] All comments, docstrings, log messages, error messages and docs are in **English**.
- [ ] Pydantic v2 appears only where it already does, at a boundary. **No DTO was added to
      the view/service path**, and none was invented for `save_search` (C-6).
- [ ] Every schema change is a Django migration and is mirrored in
      `docs/02-database/db-schema.md`. No hand-written DDL anywhere.
- [ ] Business logic lives in `services/`; no new logic was added to a view or a handler
      beyond the thin boundary change its block requires.
- [ ] Small, focused modules. `get_client_ip` and the cache-version helper each do one
      thing; neither became a framework.
- [ ] Every non-trivial behaviour change has a test that verifies **logic and component
      interaction** — not a variable's absence, not a log string, not a line count, not an
      introspected field count. **BLOCKS 2, 13 and 14 add no behavioural tests**, and that
      absence is deliberate and recorded here.
- [ ] No test sleeps 300 s; TTL durability is proven by a patched clock or an assertion on
      the stored expiry.
- [ ] Every FTS-dependent assertion carries a `trigger_present` check and a **positive
      control** (the Method trap).
- [ ] Filesystem side effects happen only **after** commit, via `transaction.on_commit()`
      — BLOCK 7's bump and receiver both.
- [ ] No task target is a line number; every target is a file plus a semantic symbol.
- [ ] `uv run ruff check --fix src/` was run if imports were reordered (`ruff format` is
      **not** the project convention).
- [ ] Every new finding citation is cycle-scoped `SRCH-nnn` / `08-VAL-nnn`; no bare
      `SRH-nnn` was written into a comment, a docstring or a commit message, and the
      existing `SRH-` markers are phase 03's to sweep.

### 8.6 Deliverables

- [ ] The `SRCH-004` → `06-PII-104` handoff (§5.4) was communicated to the coordinator,
      including the two acceptance criteria and the `IMMEDIATE_ALARTS_ENABLED` gate.
- [ ] The `SRCH-010` → `04-AUT-003` closure was communicated, so phase 04 does not ship a
      second, divergent `_get_client_ip`.
- [ ] Q1 (cache-version-key ownership) was answered by the coordinator, and the answer is
      recorded in BLOCK 6 and in its commit body. If it is unanswered, BLOCK 6 does not
      start.
- [ ] Q5 (`SavedSearch.query` redaction) was put to phase 06, and BLOCK 8's commit body
      records the answer — or records that phase 08 shipped the bound only.
- [ ] Q7 (does a ban hide inventory?) was put to the owner, and BLOCK 14 records the
      options and the outcome. **Phase 08 implements neither option.**
- [ ] Q2 and Q8 (the `features` ceiling and the narrowing decision) were put to the owner,
      and the chosen options are named in BLOCKs 1 and 11's commit bodies.
- [ ] The advisory items routed in §6.1 (the logging-policy class → phase 06; the i18n
      character handling → phase 14; the `search_vector` removal candidate → phase 13; the
      `SRH-` sweep → phase 03; the `VAL-002` convention → the coordinator) are recorded as
      **routed**, with the evidence that phase 08 did not silently drop them.
- [ ] BLOCK 5's commit body states the pre- and post-dedup row counts and that the data is
      **not recoverable by a revert**.
- [ ] This plan file is updated to mark each block's completion, so the phase coordinator
      has a single status surface.
- [ ] No commit was made without an explicit user request.

Phase 08 is complete when the last unchecked box above is checked, the two handoffs named in §8.6 are with the coordinator, and every gate in §0.5 has a written answer.
