# Phase 08 — Search & FTS: Validated Findings

> Self-contained validation report. Every claim was re-derived from the working
> tree and from a fresh runtime probe. No source file was modified. The reader
> needs nothing beyond this document.

**Under audit:** `.ai/audit/08-search-fts/findings.md` (15 findings, prefix `SRCH-`)
**Validator scope:** findings only (`problems_only = true`)
**Shared state at validation time:** `mko-bazuna-test` had a live test run and
phase 09/10/13 validators were active, so **all runtime work was executed against a
throwaway `postgres:18-alpine` container on its own port, with the schema built by
`migrate --run-syncdb` + `load_exchange_rates` + `setup_search_triggers`.** That
container has been destroyed. Nothing was written to the phantom `mko_bazuna`
database, and no probe artefact remains in `.ai/tmp/`.

### Method-trap guard (mandatory before trusting any FTS result)

The phase-08 auditor documented that out-of-tree probe modules do not inherit the
root `conftest.py` autouse session fixture, so `ads_search_vector_update` is absent
and every FTS check silently reports "0 hits". The validator reproduced that
condition deliberately and then closed it before making any assertion:

```
V-00  {"trigger_present": 1}     # pg_trigger, tgenabled='O', tgname='ads_search_vector_update'
V-01  {"code": 200, "total": 3}  # control: a Russian query MUST match
C-00  {"trigger_present": true}  # re-asserted on the clean-slate probe
N-00/C-00                       # re-asserted on every subsequent probe
```

Every FTS-dependent result below is downstream of a passing `trigger_present`
assertion plus a **positive** control query. **No FTS result in this report rests
on a "0 hits" observation.**

---

## Validation Verdict Table

| ID | Title (short) | Auditor sev. | Verdict | Validated sev. | One-line justification |
|----|---------------|--------------|---------|----------------|------------------------|
| SRCH-001 | Unbounded `?features=` → 243+ joins, 19.9 s, PostgreSQL backend SIGKILLed, cluster crash-recovery | CRITICAL | **CONFIRMED** (threshold corrected) | **CRITICAL** | Reproduced end-to-end on an isolated PG 18: 20→1.31 s, 40→7.88 s, 60→19.90 s then `signal 9: Killed` → `all server processes terminated; reinitializing`; the 1 GB `DB_MEM_LIMIT` default is the shipped production cap and no `statement_timeout` exists. |
| SRCH-002 | Raw search string (phone/e-mail/name) written verbatim to production JSON logs | CRITICAL | **ADJUSTED** (scope widened, severity cut) | **HIGH** | Real and unconditional, and PII-102's `DEFAULT-OFF` and "own ID" mitigations do **not** apply here — but the sink is an operator JSONL log, not an event store or unauthorised reader, so the rubric's blanket CRITICAL band is wrong. |
| SRCH-003 | No UNIQUE on `popular_searches.query_normalized` → `MultipleObjectsReturned` 500 | HIGH | **CONFIRMED** | **HIGH** | Reproduced through the view (HTTP 500); `pg_indexes` shows `popular_searches_pkey` as the only unique index, so the `get_or_create` race is a schema-invariant violation, not a transient. |
| SRCH-004 | Alert FTS path uses a weaker visibility predicate than the web path | HIGH | **CONFIRMED** (type reclassified) | **HIGH** | `find_matching_ads` matched a DECLINED seller's ad and an INACTIVE-category ad that the web path correctly hides; alert SQL contains no `is_declined` term. **Spec deviation, not a code bug** — and it is already owned by 06-PII-104 rec. 2. |
| SRCH-005 | `give_consent()` never bumps the search content version → restored ads stay invisible | HIGH | **CONFIRMED** (mechanism corrected) | **HIGH** | Reproduced: after `give_consent()` the ad is still absent while `get_search_version()` is unchanged. The trigger is the **300 s implicit TTL on the version counter**, not the call site — `decline_consent` is the only correct writer today. |
| SRCH-006 | NUL byte in `q` → unhandled `DataError` 500 on two endpoints | HIGH | **CONFIRMED** | **HIGH** | Reproduced on `/search/` and `/api/search/autocomplete`; the 500 escapes the view with a full traceback. Control `\x07` returns 200, so the defect is the NUL byte specifically, not control characters in general. |
| SRCH-007 | Content-version counter inherits Django's 300 s default cache TTL | HIGH | **CONFIRMED** (root cause widened) | **HIGH** | Reproduced: version `1 → 0 → 1`, key byte-identical. The same defective idiom exists in **four** modules, so the root cause is a project-wide cache-version contract, not one `cache.set` call. |
| SRCH-008 | No `is_banned` term in the public-visibility predicate | MEDIUM | **CONFIRMED** (justification corrected) | **MEDIUM** | Reproduced: a banned seller's ad still appears in search, browse **and** detail. But 06's validation ruled a ban is *a moderation action, not a consent action* — so this is an **owner product decision**, not a spec violation. |
| SRCH-009 | Single-word fuzzy category match silently narrows to one branch | MEDIUM | **CONFIRMED** | **MEDIUM** | Reproduced in a clean schema: `?q=велосипед` → total 1 (electronics hidden); `?q=велосипед+stels` → total 2. Validator also found a **worse** sub-case the auditor missed (duplicate display names → arbitrary branch). |
| SRCH-010 | `X-Forwarded-For` element 0 is client-controlled → app rate limiter spoofable | MEDIUM | **CONFIRMED** | **MEDIUM** | Reproduced: 0/60 rotating XFF got a 429, 10/40 with a fixed XFF did. Defeats the rate limit and the `f:{lang}` rate-limit key namespace. Identical to 04-AUT-003's mechanism. |
| SRCH-011 | `SavedSearch.query` is an unbounded `TextField`, no length cap | MEDIUM | **CONFIRMED** | **MEDIUM** | A 50 000-character query round-tripped intact. The same `TextField` becomes a raw tsquery on the alert path, and `send_alerts._collect_alerts` loops over every active saved search. |
| SRCH-012 | Phase-08 rubric asserts DECLINE must not hide PUBLISHED ads — contradicts shipped spec + code | MEDIUM | **ADJUSTED** | **LOW** | Conflict verified verbatim and **already adjudicated** by 06-PII-113 / 04-VAL-005; the marginal remaining action is one handbook file edit. Type → **DOC-UPDATE** (audit-input defect). |
| SRCH-013 | Two unrelated rate-limit budgets on adjacent public HTML routes | LOW | **CONFIRMED** (kept separate) | **LOW** | Verified, but the **JSON-429 vs empty-429 response-body inconsistency** is not covered by SRCH-010, so merging would drop content. |
| SRCH-014 | SWR docstring claims background refresh; the helper refreshes inline | LOW | **CONFIRMED** | **LOW** | `search/services/cache.py:150-152` vs `core/utils/swr_cache.py:107-112` — a stale docstring on the search hot path. |
| SRCH-015 | "N results" and the empty state are computed from different sources | LOW | **CONFIRMED** | **LOW** | Reproduced: `total_count=3`, `has_results=True`, **0 rows rendered**, HTTP 200. |

**Severity movement:** 2 CRITICAL · 5 HIGH · 5 MEDIUM · 3 LOW
→ **1 CRITICAL · 6 HIGH · 4 MEDIUM · 4 LOW**
**Verdicts:** 13 CONFIRMED · 2 ADJUSTED · 0 REJECTED · 0 MERGED.
**Deviation from the auditor's draft:** 0 escalations, 2 de-escalations
(SRCH-002, SRCH-012), 3 reclassifications (SRCH-004 spec-deviation,
SRCH-012 doc-update, SRCH-007 root-cause widening), 4 claim corrections
(SRCH-001 threshold, SRCH-005 mechanism, SRCH-008 justification, SRCH-013 split).

**The auditor's Method trap did not contaminate any of these results.** The
phase-08 report was re-run against a trigger-verified probe, and the two
places where the auditor's *own* probe could have masked a defect (SRCH-009's
"fuzzy match did not fire" and a first reproduction attempt that appeared to
refute it) were resolved by isolating the cause — see SRCH-009.

---

## Detailed Findings

### SRCH-001 — Unbounded `?features=` list is an unauthenticated cluster-kill

| Field | Value |
|---|---|
| **ID** | SRCH-001 |
| **Type** | SPEC-DEVIATION → **reclassified to UNAUTHENTICATED AVAILABILITY DEFECT** (the spec never bounds the list; §8 "No pagination/limit enabling DoS" is the rule being broken) |
| **Severity** | **CRITICAL** (held) |
| **Category** | Availability / input bounding |
| **File(s)** | `src/backend/apps/ads/services/listings_query.py:57,183-186`; `src/backend/apps/search/views/search.py:101`; `src/backend/apps/ads/views/listings.py:250`; `docker/nginx/nginx.conf:21,44`; `docker-compose.yml:15` |
| **Status** | Open — P0, blocks rollout |

**Unbounded input (confirmed).** `ListingsQueryParams.feature_slugs` is a bare
`list[str]` on a `BaseInputModel` whose only config is `extra="forbid"`
(`apps/core/schemas.py:19`). The builder then emits **one `JOIN` per element**:

```python
# listings_query.py:183-186
for slug in params.feature_slugs:
    if slug:
        ads = ads.filter(features__slug=slug)
```

Measured SQL growth (isolated probe, `V-02a`):

| `features` | `JOIN` count | SQL bytes |
|---|---|---|
| 0 | 3 | 2 120 |
| 5 | 13 | 2 861 |
| 20 | 43 | 4 991 |
| 40 | 83 | 7 831 |
| 60 | 123 | 10 743 |
| 120 | 243 | 19 623 |

Exactly `2N + 3` joins (m2m through-table + `lookup_items` per slug). Pydantic
accepted **500** slugs with no error (`V-02b`), and the same builder serves
`GET /` — 40 features returned HTTP 200 (`V-02c`).

**The availability claim (reproduced, threshold corrected).** Executing
`qs.count()` through the real ORM against PostgreSQL 18:

```
T-01 {"n":  0, "count_s":  0.003, "result": true}
T-01 {"n": 20, "count_s":  1.313, "result": true}
T-01 {"n": 40, "count_s":  7.879, "result": true}
T-01 {"n": 60, "count_s": 19.899, "result": "OperationalError: consuming input
        failed: server closed the connection unexpectedly"}
T-01 {"n":100,"count_s":  0.019, "result": "OperationalError: the connection is closed"}
T-01 {"n":150,"count_s":  0.012, "result": "OperationalError: the connection is closed"}
T-01 {"n":200,"count_s":  0.025, "result": "OperationalError: the connection is closed"}
```

PostgreSQL log from the same instance:

```
LOG:  client backend (PID 106) was terminated by signal 9: Killed
LOG:  terminating any other active server processes
LOG:  all server processes terminated; reinitializing
LOG:  database system was interrupted; last known up at ...
LOG:  database system was not properly shut down; automatic recovery in progress
LOG:  database system is ready to accept connections     (+1.6 s later)
```

**Correction to the auditor's evidence.** The auditor's report anchors on
"120 features ⇒ 30.11 s". My curve is superlinear and the crash landed at
**60** features, 19.9 s in. The number 120 is not a threshold; the shape is:

> **20 features already costs 1.3 s. 40 costs 7.9 s. 60 kills the backend.**

The auditor's 30.11 s at 120 is consistent with the same curve, but framing the
fix as "cap at 120" would be dangerously wrong. Any bound must sit far below 20.

**Mechanism (corrected, and it makes the finding worse).** The crash is
`signal 9` from the **cgroup OOM killer**, not a planner stack overflow. The
container that was OOM-killed is bounded by
`mem_limit: ${DB_MEM_LIMIT:-1g}` (`docker-compose.yml:15`), and
`DB_MEM_LIMIT` is **unset in `.env.prod`, `.env.dev` and `.env.test`** — so
**1 GB is the shipped default cap for production too.** A host-tuned
PostgreSQL without that cap would have degraded to a slow query instead of a
crash; as shipped, the memory cap is precisely what converts an expensive
query into a cluster-wide outage. Availability grading must be read against
the configuration that actually ships.

**Interaction with phase 03's DB-004 — confirmed, and it raises this finding.**
A repo-wide search for `statement_timeout|lock_timeout|idle_in_transaction_session_timeout`
returns **zero** hits in `src/` and `docker/`, and a live connection confirms it
operationally:

```
SHOW statement_timeout  ->  0      (disabled)
SHOW lock_timeout       ->  0      (disabled)
```

So there is **no server-side bound of any kind**. Nothing stops the query except
(a) gunicorn's 60 s worker timeout, which fires long after the backend is dead,
and (b) the 1 GB cgroup. Phase 03's DB-004 is therefore not an independent
hygiene item — it is a *prerequisite* for SRCH-001's remediation. Input
validation alone leaves a wide, unstated band of attacker-chosen query cost
between 1 and 60 features that still runs unbounded.

**The two existing mitigations, weighed honestly.**

1. **Application rate limiting — does not help.** `rate_limit_check` is
   30 requests / 60 s per key (`search/services/rate_limit.py:17-19`). It
   bounds *request count*, not *per-request cost*. One request is sufficient;
   the auditor is right that this is not a mitigation.
2. **nginx `limit_req` — does not help.** `limit_req_zone … rate=20r/s`
   (browse) and `rate=10r/s` (`/search/`), burst 40/50
   (`nginx.conf:19-22,40-45`). Rate again, not complexity. Also confirmed
   **not** bypassable: `limit_req` and the search limiter key on
   `$binary_remote_addr` and on the `HTTP_X_REAL_IP` that
   `proxy_set_header` overwrites (`nginx.conf:69,71,85`) — a caller cannot
   influence either.

**Both mitigations are orthogonal to the defect.** The verdict is CRITICAL, and
the rating survives the closest adversarial reading.

**Recommended (validated).** Ship all three, in this order:
1. **Bound the input at the boundary** — the durable fix is a Pydantic
   `conlist`/`Field(max_length=…)` on `feature_slugs` *plus* a deduplicating
   whitelist membership check against the catalogue. A plain `max_length` alone
   is insufficient: any 15-element list of nonexistent slugs is a 33-join query
   that still returns 0 rows. **Ceiling: 10.**
2. **`statement_timeout`** on the `default` alias (phase 03 / DB-004) — this is
   the only control that bounds the residual cost of a legitimate-but-large
   filter set, and it protects every other query path, not just this one.
3. Keep the rate limiters; they are correct as defence in depth.

**Rollout safety.** A `max_length=10` cap is a behaviour change for any existing
consumer that sends more than 10 features. Audit the four frontend filter
templates first; if the UI can already emit >10, that is a **separate UI
defect** the cap would expose, and the cap must land with or after it, not
before.

**Cross-phase.** Not duplicated in phase 13. Phase 13 grades GIN/trigram
effectiveness and index usage *at legitimate volume*; this is attacker-chosen
*input* volume, owned by phase 08 per
`08-audit-search-fts.md:26` ("Ranking / Pagination — Relevance ranking + bounded
result sets to prevent DoS") and `:116-117`. Phase 13's latency grading must
assume the fix landed; otherwise it will re-measure a defect phase 08 owns.

---

### SRCH-002 — Raw search string reaches production logs unredacted

| Field | Value |
|---|---|
| **ID** | SRCH-002 |
| **Type** | SPEC-DEVIATION (i18n/PII governance) |
| **Severity** | **CRITICAL → ADJUSTED to HIGH** (scope widened) |
| **Category** | PII / logging |
| **File(s)** | `src/backend/apps/search/views/search.py:191-194`; `src/backend/apps/core/utils/sanitize.py:6,25-33`; `src/backend/apps/core/utils/json_logging.py:49-71`; `config/settings/prod.py:20-35`; `docs/08-features/i18n.md:92` |
| **Status** | Open — P0 |

**Reproduced.** Captured the real `LogRecord` and rendered it through the
production formatter:

```
V-03 {"code": 200, "records": 1,
      "sanitize_keeps_phone": true, "sanitize_keeps_email": true, "sanitize_keeps_name": true,
      "redact_masks_phone": true,
      "formatted_contains_phone": true, "formatted_contains_email": true,
      "formatted_line": "{\"timestamp\": \"...\", \"level\": \"INFO\",
        \"message\": \"Empty search results for query '\\u0418\\u0432\u0430\u043d
        \\u041f\\u0435\\u0442\\u0440\\u043e\u0432 +38269123456
        ivan08675378@example.com'\", \"logger\": \"apps.search.views.search\"}"}
```

`\u0418\u0432\u0430\u043d \u041f\u0435\u0442\u0440\u043e\u0432` decodes to the name,
so **all three identifiers reach the record**. `sanitize_query_for_log` only
truncates to 200 chars and strips control characters — it is not a redactor, and
`RedactingJsonFormatter.redact_string` (`json_logging.py:49-71`) only rewrites
`key=value` pairs inside the message, so it cannot touch a bare quoted value.
`redact_search_query` in the same module masks all three correctly — the correct
control exists and is simply not called on this line.

**Sink / branch / blast radius — judged honestly, against the phase-06 precedent.**

| Factor | SRCH-002 | 06-PII-102 (re-rated CRITICAL→HIGH) | Verdict |
|---|---|---|---|
| Feature enabled | **unconditional** | behind default-off `IMMEDIATE_ALERTS_ENABLED` | **Aggravating** — PII-102's mitigation does not apply |
| Branch | empty-result path only | send-failure path only | Comparable (both are partial branches) |
| Volume | **every zero-result query from an unauthenticated endpoint** | one integer per failed send | **Aggravating** |
| Whose value | the searcher's own query — **but a third party can cause another person's phone number to be logged** by sending them a crafted `/search/?q=%2B382…` link | the recipient's own ID | **Aggravating** |
| Sink | operator JSONL on stdout, collected by a log aggregator | same | Comparable |
| Erasure | **none** — `withdraw_consent()` cannot reach a log line | same | Comparable |

**Why HIGH and not CRITICAL.** The sink is an operator log, not an event store
and not an unauthorised reader. The data subject's own typed query is not
"exposed to a party that should not see it" in the sense phase 06 held CRITICAL
for PII-101 (rows persisting in a searchable admin table with a written erasure
promise attached). The rubric's literal band —
`08-audit-search-fts.md:110` "PII leaks in search logs or analytics query
strings" — is exactly the blanket band 06's validation already recorded as
defective for ignoring sink and blast radius. Repeating it here would
reintroduce the inconsistency that was explicitly corrected.

**Why it is nevertheless a P0 at HIGH.** Three aggravating factors that PII-102
did *not* have put it above an ordinary logging defect: it is always-on; its
volume is unbounded and attacker-influenced; and a third party can deliberately
cause a specific person's phone number to be written into a durable log by
getting them to click a link. There is no `withdraw_consent()` path that
reaches it.

**Recommended (validated).** Split the fix; do not pick one.

- *Code, phase 08:* call `redact_search_query` on the search view's logging
  path, and audit every other `sanitize_query_for_log` call site for the same
  substitution. This is small and belongs in the search app.
- *Policy, phase 06:* this is the **third** instance of the "no declared logging
  policy" root cause that 06's validation named when it re-rated PII-102
  (validated rec. 5: "One logging policy, enforced — EMAIL templates, search
  queries, support …"). It is also the concrete proof of 06's severity-taxonomy
  defect **06-VAL-005** ("raw identifier in logs" graded CRITICAL regardless of
  sink) — this instance fails that bucket, because its sink *is* an operator
  log. One rule — *never log raw user input; log a normalised, redacted,
  truncated form* — enforced by a shared formatter or a logging filter, closes
  this and the next instance. A point fix in `apps/search` alone will not.
- *Advisory, phase 14:* `sanitize_query_for_log` iterates
  `char.isalpha()` and drops every non-alphabetic character, so Cyrillic and
  Montenegrin input collapses to its letters while Serbian Latin characters
  (`č`, `ć`, `š`, `đ`, `ž`) and digits are lost entirely. That degrades
  incident triage for two of the three supported locales. Classification
  belongs to phase 14; recorded here so it is not lost.

---

### SRCH-003 — Missing UNIQUE on `popular_searches.query_normalized`

| Field | Value |
|---|---|
| **ID** | SRCH-003 |
| **Type** | BEST-PRACTICE (schema-invariant violation) → **DATA-INTEGRITY** |
| **Severity** | **HIGH** (held) |
| **Category** | Reliability / schema |
| **File(s)** | `src/backend/apps/search/models.py:18,53-58`; `src/backend/apps/search/services/popular_search.py:41-60`; `src/backend/apps/search/migrations/0001_initial.py:32`; `0002_redact_search_queries.py` |
| **Status** | Open |

**Reproduced.** `query_normalized` is declared `db_index=True` with no unique
constraint (`models.py:18`) and `Meta` declares no `UniqueConstraint`
(`models.py:53-58`); the only unique index on the table is the primary key:

```
V-04b {"unique_indexes": ["popular_searches_pkey"]}
```

Two rows with the same normalised value, then the normal call path:

```
V-04  {"increment_result": "MultipleObjectsReturned: get() returned more than
        one PopularSearch -- it returned 2!"}
V-04c {"view_exc": "MultipleObjectsReturned: ..."}      # propagates out of the view
```

`get_or_create` calls `.get()` internally, so it re-raises `MultipleObjectsReturned`
— a hard 500 — the moment a duplicate exists. The raise is also **not** caught:
`_record_search_analytics` (`search.py:153`) has no guard, so the response is a
500, not a degraded one.

**Why HIGH is right, and why the auditor's framing is slightly off.** The
auditor framed this as a data race. It is not a race in the ordinary sense —
it is a *schema-invariant violation*. `get_or_create`'s atomicity only protects
the `IntegrityError` path; with no unique index there is nothing for it to
catch, so two concurrent writers both succeed and the table is permanently
corrupted. The defect is that the database does not enforce the invariant the
code assumes. That is why remediation must lead with a migration, not with
locking.

**Recommended (validated).**
1. **Migration first, as a data migration, not a plain `AlterField`:** add
   `UniqueConstraint(fields=["query_normalized"], name="uq_popular_search_query_normalized")`.
   Because `0002` is already applied, `0001` must not be edited — add `0003`.
2. Deduplicate inside the same migration (keep `MAX(hit_count)` per group,
   sum `last_searched_at`), otherwise the constraint cannot be created.
3. **Delete the misleading index comment** at `models.py:56-58`. It claims
   "multiple searches of the same normalized string are merged (get_or_create)".
   That is a *correctness* property with no database enforcement — the comment
   is what made this look handled.
4. **Consider an integrity test:** insert two rows with the same
   `query_normalized` and assert `IntegrityError`. This is a real gap in
   `apps/search/tests/` and the cheapest guard against a future regression.

**Severity note.** The 500 is a availability impact on `GET /search/`, i.e. the
same anonymous surface as SRCH-001, but the trigger requires a duplicate to
exist first, which the system creates itself under concurrency. It is not
independently exploitable, hence HIGH rather than CRITICAL.

---

### SRCH-004 — The alert FTS path uses a weaker visibility predicate than the web path

| Field | Value |
|---|---|
| **ID** | SRCH-004 |
| **Type** | **SPEC-DEVIATION** (visibility predicate divergence) — reclassified; the auditor filed it as a code-quality/consistency issue, which understates it |
| **Severity** | **HIGH** (held) |
| **Category** | Correctness / visibility |
| **File(s)** | `src/backend/apps/search/services/alert_query.py:43-45`; vs `src/backend/apps/ads/services/listings_query.py:131-136` |
| **Status** | Open — **blocked on the owner decision in 06-VAL-003** |

**Reproduced.** The two paths were compared against the same fixture data on
the same request:

| | Web (`/search/`) | Alert (`find_matching_ads`) |
|---|---|---|
| `status=PUBLISHED` | yes | yes |
| `user__is_declined=False` | **yes** (`:134`) | **no** |
| null-safe `category__is_active` | **yes** (`:135`) | **no** |

```
V-05  {"alert_matched_declined_ad": true, "web_contains_declined_ad": false}
V-05b {"alert_base_where_has_is_declined": false}
V-05c {"alert_matched_inactive_cat_ad": true, "web_contains_inactive_cat_ad": false}
```

The alert path selected **two ads the web path correctly hides** — one belonging
to a DECLINED seller, one in a deactivated category. `alert_query.py:43-45` is
literally `Ad.objects.filter(status=AdStatus.PUBLISHED)`.

**Why SPEC-DEVIATION, and why that changes the priority.** `technical-specification.md:101`
states that DECLINE "hides the user's PUBLISHED ads from public search/listings,
direct URL access (`ad_detail`), and the `media_gate` non-staff filter". An
outbound Telegram message is a wider disclosure than any of those three surfaces
— it delivers title and price, and via `build_alert_message` a working deep
link. Shipping a hidden ad to every matching subscriber is therefore a
deviation from a spec statement that exists and is unambiguous, not a
house-style inconsistency. `08-audit-search-fts.md:89` names the rule directly:
"Visibility predicate must be the single source of truth shared with public
listing. Search must not re-implement divergent gating."

**This is a decision, not a patch — and it is already owned elsewhere.**
`get_account_state()` (`users/services/account_state.py:26-48`) is
**instance-level** (`User → NamedTuple`), so there is nothing a queryset filter
can call. Any one-line fix writes a second, drift-prone copy of the rule. The
fix requires promoting a querysets-level predicate into a named owner. That is
precisely what **06-VAL-003** records, and the ad-side half is **already
carried by 06-PII-104** — whose validated recommendation item 2 reads, verbatim:
"Also exclude ads whose owner is DECLINED from `find_matching_ads()` and
`find_matching_saved_searches()`". See **Cross-Phase Reconciliation** below for
the exact relationship and for why SRCH-004 and 06-VAL-003 are *not* the same
predicate.

**Recommended (validated).** Do not action this as a second, separate fix.
Land it inside the single owner decision that closes 06-VAL-003 and 06-PII-104:
one querysets-level ad-visibility predicate owned by `apps/ads`, consumed by
`ListingsQuery.build_queryset`, `find_matching_ads`, `ad_detail` and
`media_gate`. Phase 08 owns the *ad* predicate; phase 06 owns the *audience*
predicate. They belong in one change, not two.

**Ordering constraint.** The audience filter must land **before**
`IMMEDIATE_ALERTS_ENABLED` is ever set to `True`. It is currently `False`
(`config/settings/base.py:349`) and must stay that way until both predicates
exist. The daily digest path (`send_alerts`, 08:00 UTC) is **not** feature-gated
and is live today.

---

### SRCH-005 — `give_consent()` never bumps the search content version

| Field | Value |
|---|---|
| **ID** | SRCH-005 |
| **Type** | SPEC-DEVIATION (contract violation) |
| **Severity** | **HIGH** (held) |
| **Category** | Correctness / cache invalidation |
| **File(s)** | `src/backend/apps/users/services/deletion.py:234-289`; `src/backend/apps/search/services/cache.py:42-46,84-97`; `src/backend/apps/ads/signals.py` |
| **Status** | Open — must ship with or after SRCH-007 |

**Reproduced.**

```
V-06 {"declined_visible_before": false,
      "hidden_after_decline": true,
      "is_declined_cleared": true,
      "visible_after_give_consent": false,     <-- restore is invisible
      "version_before": 1, "version_after": 1}
```

`give_consent()` (`deletion.py:265-289`) sets `is_declined=False` and saves, and
that is its entire invalidation story. Every other user and ad write path in the
codebase does bump — via `on_commit` in `decline_consent`/`withdraw_consent`,
via `Ad.save`/`Ad.transition_to`/`Ad.delete` in `apps/ads/signals.py`, and via
`User.save` for the ad-affecting fields. `is_declined` is a user field, so its
`on_commit`/`post_save` receiver skips it. The contract is maintained by
convention, and this is the one call site that forgot.

**Correction to the auditor's stated mechanism.** The auditor attributes the bug
to the missing call at the call site. Both call sites and the `post_save`
receiver are real contributors and the fix does belong in `give_consent()` — but
**the reason it is exploitable is SRCH-007.** The audit itself recorded that
"today only `decline_consent()` bumps correctly and `give_consent()` is the only
path that does not" — and that is only a defect *because* the version counter
evicts itself after 300 s. Fixing the missing `on_commit` while the counter is
still self-evicting leaves a second, independent failure path to the same
user-visible outcome. **SRCH-005 and SRCH-007 must ship together or the
restoration bug survives in a harder-to-reproduce form.**

**Correcting one auditor claim explicitly.** The report lists "R-26
`submission.py:161-169` promotes staging→permanent before `transaction.atomic()`
at `:169`" as a *related* risk. It is a genuine concern, but it is a
**transaction-boundary** question owned by phase 05, not a cache-version
question, and it does not weaken this finding. It is recorded here only so the
linkage is not mistaken for evidence.

**Recommended (validated).**
1. Add the `on_commit` bump to `give_consent()`, next to the existing one in
   `decline_consent` (`deletion.py:250`).
2. **Or, better:** the durable fix is one `post_save` receiver on
   `User.is_declined` in `apps/users/signals.py`. That converts the whole class
   of "user account state changed, the search cache is now stale" from a
   per-call-site convention into a declared invariant — and it is the same
   structural move that makes 06-VAL-003's predicate reusable. Prefer it; the
   `give_consent()` patch is the fallback, not the destination.
3. Add a regression test that declines, loads the search page (populating the
   cache), re-accepts, and asserts the ad is visible **without** a manual bump.

---

### SRCH-006 — NUL byte in `q` produces an unhandled `DataError` 500

| Field | Value |
|---|---|
| **ID** | SRCH-006 |
| **Type** | BEST-PRACTICE (unhandled input at a system boundary) |
| **Severity** | **HIGH** (held) |
| **Category** | Reliability / input validation |
| **File(s)** | `src/backend/apps/search/views/search.py:191-194,221-247`; `src/backend/apps/search/views/autocomplete.py:29-35`; `src/backend/apps/search/services/popular_search.py:29-38` |
| **Status** | Open |

**Reproduced on both endpoints, with a control.**

```
V-07  {"nul_in_query": "EXC DataError: PostgreSQL text fields cannot contain
        NUL (0x00) bytes"}                     # /search/?q=велосипед%00abc
V-07  {"nul_alone":    "EXC DataError: ..."}    # /search/?q=%00
V-07  {"bell": 200}                             # control: 0x07 is fine
V-07b {"autocomplete_nul": "EXC DataError: ..."}# /api/search/autocomplete?q=ab%00cd
```

The control matters: this is **not** "control characters break search". `\x07`
is accepted. NUL is unique in that PostgreSQL rejects it inside *text* columns
and `psycopg` refuses to encode it, so it fails at the driver, not in the
query.

**Blast radius — larger than the auditor states.** The auditor called this
"an unhandled 500 on two endpoints". That understates it:

- `_record_search_analytics` (`search.py:153`) is called **unconditionally** on
  every search, so the exception is reachable with **no matching ads needed** —
  my `q=%00` probe returned 0 results and still 500'd.
- It is **unauthenticated and cacheable** as a cheap 500.
- `_record_search_analytics` runs *after* `_resolve_search_count`, so a NUL
  request burns the full query cost before failing — it is a free CPU amplifier
  on top of SRCH-001's surface.
- Django's `DataError` is a database-driver exception, so `DEBUG=False`
  production responses carry **no detail**, but `logger.exception` still writes
  the full traceback with the offending value. Minor PII interaction with
  SRCH-002: the *query string* appears in a traceback, not just a message.

**A counting control the auditor did not record.** `record_event(...)` is
wrapped in `try/except` inside the analytics service (06-DB-002), so it is
*not* the raiser. The raiser is `increment_popular_search` (`popular_search.py:41-60`),
called **after** `record_event` at `search.py:197-198`, and that call has no
guard. The fix therefore belongs at the *second* call site, not the first.

**Recommended (validated).** Reject NUL at the boundary, once, in the shared
`sanitize_query_for_log`/`sanitize_autocomplete_query` path both views already
call — a control character, not just NUL, is the right predicate. Do **not**
wrap `_record_search_analytics` in a blanket `try/except`: that would convert a
correct, loud input-rejection failure into a silent one, and DB-002's lint rule
(`BLE001`) exists to stop exactly that shape. Add a regression test for
`\x00` on both endpoints.

---

### SRCH-007 — The search content-version counter inherits Django's 300 s default TTL

| Field | Value |
|---|---|
| **ID** | SRCH-007 |
| **Type** | BEST-PRACTICE (missing cache contract) → **STRUCTURAL: missing project-wide cache-version contract** |
| **Severity** | **HIGH** (held) |
| **Category** | Correctness / cache invalidation |
| **File(s)** | `src/backend/apps/search/services/cache.py:42-46,84-97`; `config/settings/base.py:369-377`; `src/backend/apps/categories/cache.py:44`; `src/backend/apps/categories/services/lookup_resolution.py:84`; `src/backend/apps/lookups/services/cache_service.py:78` |
| **Status** | Open — must ship with SRCH-005 |

**Reproduced.**

```
V-08  {"ttl": 300, "stale_ttl": 60, "entry_lifetime": 360,
        "v_before": 1, "v_after_delete": 0, "v_after_next_bump": 1,
        "key_reused": true}
```

- `CACHES` declares **no `TIMEOUT`** (`base.py:369-377`), so `cache.set` without
  a timeout inherits Django's `DEFAULT_TIMEOUT = 300` — confirmed at runtime
  (`V-08b`).
- The cached ID list is written by the SWR helper with
  `timeout = ttl + stale_ttl = 360` (`swr_cache.py:205`) — **longer than the
  counter that is supposed to invalidate it.**
- The counter therefore evicts at 300 s, the next bump re-issues the value
  `1`, and a search key built 60 s earlier is byte-identical again. Any
  60-second window straddling the eviction serves a pre-change result list
  against a post-change predicate.

**Root cause widened — this is the important correction.** The auditor treated
this as one `cache.set` in one module. It is a **project-wide idiom**, and the
defect is in all four instances:

| Module | Key | Fallback |
|---|---|---|
| `apps/search/services/cache.py:95` | `search:content_version` | `cache.set(key, 1)` — **no timeout** |
| `apps/categories/cache.py:44` | `category:tree_version` | `cache.set(key, 1)` — **no timeout** |
| `apps/categories/services/lookup_resolution.py:84` | `lookup:resolve_version` | `cache.set(key, 1)` — **no timeout** |
| `apps/lookups/services/cache_service.py:78` | `lookup:content_version` | `cache.set(key, 1)` — **no timeout** |

All four have the same shape: `try: cache.incr(KEY) / except ValueError:
cache.set(KEY, 1)`. The counter is a correctness mechanism wearing a cache
entry's TTL, and nothing in the codebase says a version key must be durable.
That is a **missing contract**, not four independent typos — so the fix must be
declared once, not applied four times.

**Recommended (validated).**
1. **Declare the contract in `apps/core`:** one helper for "durable monotonic
   cache-version key" that sets `timeout=None`, with the invariant documented.
   Migrate all four call sites to it.
2. Short-term, if the helper is too large a change to land first: add
   `timeout=None` to all four `cache.set` calls *in the same commit*. Four
   one-line changes and one comment beat one correct helper and three live bugs.
3. **Test the invariant, not the implementation:** a regression test that
   populates a cached entry, advances past `DEFAULT_TIMEOUT`, bumps, and asserts
   the key changed. That test fails today and must pass before the four sites
   are considered fixed.
4. Do **not** pin `CACHES["default"]["TIMEOUT"]`. Raising or removing the
   default would silently extend the lifetime of *every* cache entry in the
   system; the defect is that the version key is wrongly treated as a cache
   entry, not that the default is wrong.

---

### SRCH-008 — No `is_banned` term in the public-visibility predicate

| Field | Value |
|---|---|
| **ID** | SRCH-008 |
| **File(s)** | `src/backend/apps/ads/services/listings_query.py:131-136`; `src/backend/apps/ads/views/listings.py:61-71,203`; `src/backend/apps/users/services/account_state.py:66-106`; `docs/02-database/db-schema.md:61,77` |
| **Type** | **OWNER DECISION** (not a spec violation) — reclassified by this validation |
| **Severity** | **MEDIUM** (held) |
| **Category** | Authorization semantics |
| **Status** | Open — **folds into SRCH-004**; one commit, one predicate |

**Reproduced.** Banning a seller and re-querying all three public surfaces:

```
V-09 {"search_contains_before": true,
      "search_contains_after_ban": true,     # search still lists it
      "browse_contains_after_ban": true,     # browse still lists it
      "detail_code": 200}                    # detail still serves it
```

`is_banned` is consulted by `can_login` and `can_publish_ad` and by the bot's
`AccountStateMiddleware` — i.e. at the **interaction** boundary — and by **no
public read path anywhere**. `db-schema.md:61` describes the column as
"account block (US-A4)"; line 77 expands it only to login/publish enforcement.

**Correction to the auditor's justification — this matters for how the fix is
argued.** The report frames the missing `user__is_banned=False` as a
"visibility-predicate hole" and recommends adding the term. Phase 06's
validation reached the opposite conclusion on the identical term, and its
reasoning is better: *"nothing in the spec says a banned account must be
excluded from the market, and a ban is a moderation action, not a consent
action."* 06 therefore *kept* the filter in its recommendation but **stopped
citing it as a consent breach** (see the `PII-104` validation note). I adopt
that position.

Consequence: **adding the term is an owner product decision, not a bug fix.** It
must be decided and documented as such, and it must not be bundled into a commit
justified as "fixing a consent violation" — that mislabels the change and makes
it much harder to review. `db-schema.md:61` is already misleading here (its
`is_declined` note documents the search predicate; its `is_banned` note implies
an enforcement scope the code does not have) and should be corrected in the same
change.

**Recommended (validated).** Resolve inside the single predicate decision
(06-VAL-003 / SRCH-004), not separately. Two defensible options:

- **Ban hides inventory** — add `user__is_banned=False` to the shared predicate
  *and* to `ad_detail`/`media_gate`, and amend `db-schema.md:61` to state the
  scope explicitly. Consistent, and stops a banned seller reaching buyers
  through ads they can no longer manage.
- **Ban does not hide inventory** — document that a ban is a
  seller-relationship sanction and that takedown is performed by transitioning
  the ads (`ARCHIVED`/`DELETED`) through the moderation path. Also defensible,
  and cheaper.

Either way the answer belongs in `db-schema.md:61` and in the one predicate's
docstring. Leaving it undocumented while three surfaces disagree is the defect.

---

### SRCH-009 — A single-word fuzzy category match silently narrows results to one branch

| Field | Value |
|---|---|
| **ID** | SRCH-009 |
| **Type** | BEST-PRACTICE (silent scope reduction) |
| **Severity** | **MEDIUM** (held) |
| **Category** | Relevance / correctness |
| **File(s)** | `src/backend/apps/search/views/search.py:249-255,311-314,432-450`; `src/backend/apps/search/services/category_fuzzy.py`; `docs/01-spec/technical-specification.md:66` |
| **Status** | Open |

**Reproduced in a clean schema** (all rows wiped first, trigger re-asserted, so
no stale cache or duplicate-category artefact could interfere). Two categories,
one ad in each, matching text:

```
C-02 {"active_names": ["Велосипеды", "Электроника"]}
C-03 {"fuzzy_match_id": 10, "expected": 10}          # "велосипед" -> Велосипеды
C-04 {"one_word_service_ids": [47], "expected_both": [47, 48]}
C-05 {"one_word_total": 1, "bikes_visible": true, "elec_visible": false}   # /search/
C-06 {"two_word_total": 2, "bikes_visible": true, "elec_visible": true}    # +stels
```

A one-word query returns **1** result; the same search with one extra word
returns **2**. The electronics ad is not hidden by any filter the buyer can see,
express, or undo — the guessed category is applied as a hard
`category_id__in=<subtree>` (`search.py:253-255`), and the template renders no
indication that a guess was made.

**A method note, because this finding nearly refuted itself.** A first
reproduction attempt showed *no* narrowing and appeared to contradict the
finding. The cause was a probe artefact, not product behaviour: an earlier run
had left a second active category also named "Велосипеды", and
`_fuzzy_match_by_name` returns the **first** entry whose name equals the matched
name (`search.py:437-444`), so the query was scoped to the stale category. The
auditor's own probe reused the same display name across cases, so its
`active_names` output and its end-to-end assertion were built on different
datasets. Recorded because a validator who stopped at the first result would
have **rejected a correct finding** — the same silent-failure class the phase
handbook warns about, one level up.

**A worse sub-case the auditor missed (validator addition, same root cause).**
Because the match resolves by display *name* and takes the first hit, **two
active categories sharing a display name make single-word search return nothing
at all** — the query is scoped to a branch that holds no matching ads.
Display-name collisions are routine after i18n and catalogue work (`name_i18n`
is free-form JSONB; `db-schema.md` records no uniqueness constraint on `name`).
SRCH-009 is therefore worse than filed: the scope reduction is silent *and* can
be silently wrong. Resolve the match to `id`s from a name→ids index and treat an
ambiguous name as "no guess".

**Recommended (validated).** Add a *disjunctive branch* to the FTS predicate
instead of a hard filter, so a category guess widens recall rather than
narrowing it, and fix the ambiguity resolution above. A pure-guess path may
remain as an opt-in refinement for the category page, but it must never be
applied silently to a free-text search.

**Note for the record — not a violation.** `technical-specification.md:66`
documents the behaviour verbatim ("app-level fuzzy detect (`difflib`) sets
`category_id` filter for single-word queries"), so the current narrowing is
**specified**, not a regression. The finding is that the specification itself
chose recall-reducing behaviour with no UI signal — a design question, not an
implementation defect, which is why it is MEDIUM and not HIGH. If the owner
accepts the narrowing as intended, SRCH-009 drops to LOW and resolves to a
documentation change plus the ambiguity fix.

---

### SRCH-010 — `X-Forwarded-For` element 0 is client-controlled, so the app rate limiter is spoofable

| Field | Value |
|---|---|
| **ID** | SRCH-010 |
| **Type** | BEST-PRACTICE (proxy-header trust) |
| **Severity** | **MEDIUM** (held) |
| **Category** | Security / rate limiting |
| **File(s)** | `src/backend/apps/search/services/rate_limit.py:82-84,92`; `src/backend/apps/users/services/login_rate_limit.py:76-78`; `src/backend/apps/core/services/contact_rate_limit.py:26-29`; `docker/nginx/nginx.conf:1,23,69,71,85,100,106,111,118,140,143,147,150` |
| **Status** | Open |

**Reproduced.**

```
V-11 {"xff_rotating_429s": 0,  "xff_total": 60,
      "fixed_429s": 10,          "fixed_total": 40}
```

60 requests with a rotating `X-Forwarded-For`: **zero** rate-limited. 40 requests
with a fixed value: 10 × HTTP 429, i.e. the 30/60 s cap firing exactly as
configured. Rotating the header bypasses both the rate limit **and** the
`f:{lang}` key namespace that scopes it to one filter value.

**The three copies, and the correction to the remediation.** `_get_client_ip`
is byte-identical in `search/services/rate_limit.py:82`, `users/services/login_rate_limit.py:76`
and `core/services/contact_rate_limit.py:26`; all three take `split(",")[0]` —
the **leftmost** element, which is the value a client writes. That is the
conventional anti-spoofing choice *only when the proxy appends to the header*.
nginx here sets `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for`
(`nginx.conf:71`, line 1) and `$proxy_add_x_forwarded_for` is
`"$http_x_forwarded_for, $remote_addr"` — nginx **appends** the peer as the
**rightmost** element. So the leftmost element is attacker-controlled end to end,
and the correct read under this proxy configuration is the **last** element.

The auditor recommended "read `X-Real-IP` … or read the last element of
`XFF`". The first is already correct and better: `nginx.conf:69` sets
`proxy_set_header X-Real-IP $remote_addr`, which is a single value nginx
**overwrites**, so a caller cannot influence it at all. Prefer `X-Real-IP`,
fall back to `XFF[-1]`, and only then to `REMOTE_ADDR`.

**One mitigation confirmed, and it is not enough.** nginx's own limits key on
`$binary_remote_addr` and the search limiter keys on the `X-Real-IP` that nginx
overwrites, so neither is spoofable. But the nginx ceiling is 10 r/s burst 50 on
`/search/` and 20 r/s burst 40 on browse — an order of magnitude above the
app-level 30/60 s policy the audit is about. Spoofing does not remove the edge
limit; it removes the *application* policy, which is the one with the SLO
intent.

**Cross-phase.** The identical mechanism in the **login** limiter is already
recorded as **04-AUT-003** (which phase 04's validator explicitly annotated as
"search copy was missing from File(s)"). Do not re-file. One shared
`get_client_ip` in `apps/core` consumed by all three sites closes AUT-003,
SRCH-010 and, with SRCH-013, the policy fragmentation — **one commit**.

---

### SRCH-011 — `SavedSearch.query` is an unbounded `TextField` with no length cap

| Field | Value |
|---|---|
| **ID** | SRCH-011 |
| **Type** | BEST-PRACTICE (missing input bound) |
| **Severity** | **MEDIUM** (held) |
| **Category** | Reliability / resource bounds |
| **File(s)** | `src/backend/apps/search/models.py:79`; `src/backend/apps/search/views/save_search.py:37,48`; `src/backend/apps/search/services/alert_query.py:91-99`; `src/backend/apps/search/management/commands/send_alerts.py:112-115` |
| **Status** | Open |

**Reproduced.**

```
V-12 {"submitted": 50000, "stored": 50000}
```

`SavedSearch.query` is `models.TextField(null=True)` and the DTO declares no
constraint (`save_search.py:37`), so 50 000 characters round-trip intact through
the save endpoint.

**Blast radius, and why MEDIUM rather than a lower band.** A stored saved-search
query is not just inert text. It is:
- handed to `websearch_to_tsquery` on every alert evaluation
  (`alert_query.py:91-99`) — an attacker-chosen tsquery against the FTS index,
  evaluated by `send_alerts` on a schedule;
- iterated **once per active saved search** by `send_alerts._collect_alerts`
  (`send_alerts.py:112-115`), so N oversized saved searches multiply the cost of
  the daily job;
- never bounded, never deleted, and `SavedSearch` is `CASCADE`-deleted only 30
  days after a consent withdrawal, so the row outlives the erasure window by
  design (`06-PII-104`).

No timing evidence is offered here — **quantifying the alert-path cost is phase
13's scope**, and this validation deliberately makes no latency claims. What is
established is that the input is unbounded and reaches a recurring job.

**Recommended (validated).** A cap at the boundary (e.g. 200 characters,
matching `PopularSearch.query_normalized` and `SearchHistory.query_normalized`,
both `max_length=200`) **and** at the model. Prefer the DTO constraint plus a
migration, so the bound is enforced on every writer including management
commands — a view-only cap is the same convention-based contract that produced
SRCH-005. Add a test asserting the cap.

**Not merged into SRCH-001, deliberately.** The auditor offered them as merge
candidates. They are kept separate because the exposures are categorically
different: SRCH-001 is **anonymous, one request, whole-cluster impact**;
SRCH-011 requires an authenticated seller and degrades a scheduled job. They
share a root cause — *input bounds are not modelled as part of the DTO contract*
— so they belong to one work item, but they must not share a commit or a
priority.

---

### SRCH-012 — The phase-08 rubric contradicts the shipped spec and the code on DECLINE

| Field | Value |
|---|---|
| **ID** | SRCH-012 |
| **Type** | DOC-UPDATE (audit-input defect) — reclassified |
| **Severity** | **MEDIUM → LOW** |
| **Category** | Documentation / audit-input integrity |
| **File(s)** | `.kilo/commands/audit/phases/08-audit-search-fts.md:24,40,53,118`; vs `docs/01-spec/technical-specification.md:85,96,101`; `docs/02-database/db-schema.md:63` |
| **Status** | Open — one-line-per-occurrence handbook edit |

**Verified verbatim, in four places in the phase-08 handbook:**

- `:24` — "DECLINE (browse-only) does not alter ad status so a seller's PUBLISHED
  ads remain searchable"
- `:40` — "**DECLINE a seller** → their PUBLISHED ads MUST still be found
  (search must not filter on consent state directly)"
- `:53` — "DECLINE must NOT hide a seller's PUBLISHED ads"
- `:118` — "DECLINE incorrectly hides a seller's PUBLISHED ads from search"
  (listed under **HIGH**, i.e. the rubric's expected-failure column)

The shipped spec states the opposite, three times: `technical-specification.md:85`
("DECLINE … **also hides the user's PUBLISHED ads from public search/listings**"),
`:96` ("the listing/search queryset filters out `user__is_declined=True`"), and
`:101` ("**hides the user's PUBLISHED ads** from public search/listings, direct
URL access (`ad_detail`), and the `media_gate` non-staff filter"). The code
matches the spec — `listings_query.py:134`. **The rubric is the outlier, and
the code is correct.**

**Severity moved to LOW, and the reason is that this is already adjudicated.**
Phase 06's validation settled the identical three-way conflict and recorded the
authoritative ruling under `PII-113` (merged there with `04-VAL-005`): code +
`technical-specification.md` win, the stale statement is the rubric. Phase 08
re-introduced the same stale assertion in a *different handbook file*, and 06's
validator had flagged the taxonomy defect generally as `06-VAL-004` ("the
audit-input classification is itself defective").

The marginal value of SRCH-012 is therefore **one handbook file**, not one
architectural decision. It has no runtime impact, and its substance is already
carried by a validated finding. That is a documentation task, not a MEDIUM
defect.

**Recommended (validated).** Fix the four occurrences in
`08-audit-search-fts.md` to match the spec, and fold them into the same
handbook-remediation pass that fixes `04-audit-auth-login.md` and
`06-audit-pii-consent.md`. One owner, three files, one decision.

---

### SRCH-013 — Two unrelated rate-limit budgets on adjacent public HTML routes

| Field | Value |
|---|---|
| **ID** | SRCH-013 |
| **Type** | BEST-PRACTICE (policy fragmentation) |
| **Severity** | **LOW** (held) |
| **Category** | Rate limiting / observability |
| **File(s)** | `src/backend/apps/search/services/rate_limit.py:17-19,30-32,96-98`; `src/backend/apps/core/services/contact_rate_limit.py:17-21,32-38,50-53`; `src/backend/apps/ads/views/listings.py:229`; `src/backend/apps/search/views/search.py:210-212` |
| **Status** | Open — same work item as SRCH-010 |

**Verified.** `/search/` and `/` are adjacent, both anonymous, both
HTML-rendering, both rate-limited — and neither budget has a documented
rationale:

| Route | Module | Budget | 429 shape |
|---|---|---|---|
| `/search/` | `search.services.rate_limit` | 30 / 60 s | `JsonResponse({"error": "rate_limited"})` (`:96-98`) |
| `/` | `core.services.contact_rate_limit` | 60 / 600 s | bare `HttpResponse(status=429)`, empty body (`:50-53`) |

The second limiter's docstring (`contact_rate_limit.py:34-39`) says only that it
"mirrors `apps.search.services.rate_limit.rate_limit_check`" — the *mechanism*,
not the *budget* — which is how two different numbers ended up documented as if
one were authoritative.

**Kept separate from SRCH-010 rather than merged — the auditor's own framing was
partly right but not entirely.** SRCH-010's defect is *header trust*; SRCH-013's
is *policy fragmentation*. The overlap is only the **response shape**: a buyer
who trips the search limit gets a JSON body from an HTML page, and gets an
**empty** body from `/`. Neither is a security boundary, and neither is covered
by SRCH-010's fix (correcting `_get_client_ip` does not make the two budgets
agree, and does not change a 429 body). Merging would silently drop that half.

**Recommended (validated).** Land with SRCH-010 in one commit: one
`get_client_ip` in `apps/core`, one rate-limit module with a
per-endpoint budget table as a `StrEnum` (project rule 10 — these are constants,
and the current bare `Final[int]` pairs in two modules are the reason the
numbers drifted), and one 429 response shape used by both. Then record the
rationale for 30/60 s and 60/600 s in the docstring, or justify a change.

---

### SRCH-014 — The SWR docstring claims background refresh; the helper refreshes inline

| Field | Value |
|---|---|
| **ID** | SRCH-014 |
| **Type** | DOC-UPDATE |
| **Severity** | **LOW** (held) |
| **Category** | Documentation accuracy |
| **File(s)** | `src/backend/apps/search/services/cache.py:150-152`; `src/backend/apps/core/utils/swr_cache.py:8,16-19,107-112,153-175` |
| **Status** | Open — one-line fix |

**Verified by reading both sides.** `search/services/cache.py:150-152` says the
stale value is returned immediately and the entry is "refreshed in the
background by the single-flight winner". `swr_cache.py:107-112` shows what
actually happens: the winner calls `_recompute_and_store` **synchronously,
before returning**, so it blocks its own response:

> "Winner: recompute synchronously — the caller needs a result."
> — `swr_cache.py:139`

The module docstring at `swr_cache.py:8` ("prevent cache stampedes") and lines
16-19 are accurate; only the search call-site docstring is stale. This matters
more than a normal docstring because the claim is about **latency on the search
hot path** — a reader sizing the cache layer would budget for a non-blocking
refresh that does not exist.

**Recommended (validated).** Correct the three-line docstring in
`search/services/cache.py`. Do not change the helper: inline recompute on the
stale-winner path is a defensible design, and the alternative (a background
task) would need a worker this deployment does not run. If the inline cost
matters, that is a phase-13 latency question, not a documentation fix.

---

### SRCH-015 — "N results" and the empty state are computed from different sources

| Field | Value |
|---|---|
| **ID** | SRCH-015 |
| **Type** | BEST-PRACTICE (template data contract) |
| **Severity** | **LOW** (held) |
| **Category** | UX / correctness |
| **File(s)** | `src/backend/apps/search/views/search.py:159-190,228-229,301-310`; `src/backend/templates/ads/list.html` |
| **Status** | Open |

**Reproduced.** Every ad in the result set was archived via a bulk `.update()`
— deliberately *without* bumping the content version, which is exactly the
SRCH-005/SRCH-007 window — and the page re-read with a warm cache:

```
V-13 {"total_count": 3, "has_results": true, "rendered": 0, "code": 200}
```

The page reports **3 results**, sets `has_results=True`, renders **zero** cards,
returns HTTP 200, and shows no empty state — because `total_count` and
`has_results` come from the cached ID list (`_resolve_search_count` returns
`len(cached_ids)` on a cache hit, `:307-309`) while the cards come from the
re-filtered `page_obj`.

The auditor's claim that this "cannot be hit under normal operation" is
**correct and worth preserving**: it requires a stale cache, and SRCH-005 and
SRCH-007 both create stale-cache windows on their own. It is reachable by the
system's own behaviour, not only by a contrived test.

**Recommended (validated).** Derive `has_results` from the same source as the
rendered rows, not from a separate count. A one-line change in the view; the
fix belongs with the cache-coherency work so it is not reverted by the next
caching change.

---

## Cross-Phase Reconciliation

### The central question: is SRCH-004 the same decision as 06-VAL-003, and does SRCH-008 fold in?

**Short answer.** They share **one root cause and one change**, but they are
**two different predicates with two different owners**. SRCH-008 folds into
SRCH-004 completely. Treating the three as one finding would produce a fix in
the wrong app.

**There are two predicates, not one.**

| | **(A) Ad-visibility predicate** | **(B) Audience / account-state predicate** |
|---|---|---|
| Question answered | *which ads are public?* | *which users / saved searches are eligible for proactive delivery?* |
| De-facto owner today | `apps/ads` — `ListingsQuery.build_queryset` (`listings_query.py:131-136`) | **nowhere**; `get_account_state()` is instance-level (`account_state.py:26-48`) |
| Consumers | `build_queryset`, `find_matching_ads` (`alert_query.py:43-45`), `ad_detail` (`listings.py:61-71`), `media_gate` (`listings.py:203`) | `send_alerts._collect_alerts` (`:80,:112`), `find_matching_saved_searches` (`alert_query.py:134`) |
| Carried by | **SRCH-004 + SRCH-008** (phase 08) | **06-VAL-003 / 06-PII-104** (phase 06) |
| Predicates on | `Ad` | `User` / `SavedSearch` |

- **06-VAL-003 is (B).** Its own words: "a queryset-level predicate owned by
  `apps/users` and consumed by both alert paths … not a default-manager filter".
  It is about `User` state, and its owner is `apps/users`.
- **SRCH-004 is (A).** Its recommended remedy is "a querysets-level helper in
  the app that owns ad visibility … in `apps/ads/services/listings_query.py`".
  It is about `Ad` state, and its owner is `apps/ads`.

They share the enabling gap — `get_account_state()` takes a `User` and returns
a `NamedTuple`, so a queryset filter cannot call it, and there is nothing to
reuse, which is precisely why the rule was never applied. **That is why the
auditor is right that "both must be extracted together" and why the two
declarations should land in one change.** But they are not interchangeable
terms, and a fix that satisfies one does not satisfy the other.

**SRCH-004 is already owned by phase 06 — do not fix it twice.** 06-PII-104's
*validated* recommendation item 2 reads verbatim: "Also exclude ads whose owner
is DECLINED from `find_matching_ads()` and `find_matching_saved_searches()`".
That is SRCH-004. The phase-08 finding is the same defect observed from the
search side. **One commit closes both; two commits would create two
predicates.**

**SRCH-008 folds into SRCH-004 — fully.** Same predicate, same consumers, one
more term, one more doc line (`db-schema.md:61`). The only reason it keeps an ID
is to preserve the audit trail for the `is_banned` question, which — per 06's
reasoning and adopted here — is a **product decision**, not a consent fix, and
must be argued as one. Merging it as a term into a commit labelled "consent
propagation" would be the wrong argument for a right change.

**Phase 15 must not re-file any of this.**
`15-audit-authorization.md:132` is explicit: *"The 'what is public' predicate
semantics are owned by Phase 05/08; Phase 15 verifies that non-public objects
are not reachable through authorization failures."* So predicate **semantics**
stay in 08 (which is where SRCH-004/008 belong), and 15 owns the **framework**.
Two of 15's stated risk rows — "duplicated predicates that fall out of sync"
and "a missing identity filter on one resource type" — will be re-observed here.
They are not new findings; they are the same three-line problem seen from the
enforcement side.

**Ordering, and the gate that must not be opened early.**

```
06-VAL-003  (B) audience predicate  ──┐
                                     ├──► then and only then: IMMEDIATE_ALERTS_ENABLED
SRCH-004+008 (A) ad predicate      ──┘                                  = True
```

The daily digest (`send_alerts`, 08:00 UTC) is **not** feature-gated and is live
**today**. `IMMEDIATE_ALERTS_ENABLED` defaults to `False`
(`config/settings/base.py:349`) and must stay `False` until **both** predicates
exist — the immediate path additionally ships a working deep link to the hidden
ad via `build_alert_message`, which is strictly worse than the digest's
title+price.

### Other cross-phase overlaps — checked, and deliberately not duplicated

| Phase | Overlap | Boundary |
|---|---|---|
| **13 — performance / query plans** | SRCH-001 | 13 grades GIN/trigram effectiveness and index usage **at legitimate volume**; 08 owns **attacker-chosen input volume**. No latency claim is made in this report. 13 must assume SRCH-001's fix landed, or it will re-measure an 08-owned defect. |
| **03 — db/concurrency** | SRCH-001 ↔ DB-004 | **Interacts, does not duplicate.** DB-004 (no `statement_timeout`) is independently confirmed here — zero repo hits, and `SHOW statement_timeout → 0` on a live connection. It is a **prerequisite** for SRCH-001's remediation, not a duplicate of it. |
| **02 — rate-limit config plumbing** | SRCH-010, SRCH-013 | 02 owns *"are the limits configurable and enforced at the edge"* (nginx `limit_req`, `*_RATE_LIMIT_*` env plumbing). 08 owns *"is the edge limit the only limit, and is the app limit trustworthy"*. Confirmed non-overlapping: nginx's own limits are keyed on `$binary_remote_addr` and the `X-Real-IP` it overwrites, so 02's scope is sound. |
| **04 — auth/login** | SRCH-010 | Identical mechanism in the login limiter is already filed as **04-AUT-003** (annotated there: "search copy was missing from File(s)"). Do not re-file; one shared `get_client_ip` closes both. |
| **06 — PII/consent** | SRCH-002, SRCH-004, SRCH-009 | SRCH-002 is the search instance of 06's "**one logging policy, enforced**" root cause (06-PII-102 validated rec. 5), and it is the concrete case that proves 06's severity-taxonomy defect (**06-VAL-005**: "raw identifier in logs" graded CRITICAL regardless of sink) — see its split recommendation. SRCH-004 ≡ PII-104 rec. 2. SRCH-009's raw `query_normalized` storage is **already covered** by 06-PII-108 (recorded there: "`query_normalized` keeps un-redacted PII") — confirmed, no new finding. |
| **09 — external API / translation** | — | **No overlap.** I made no translation assertion; translation degradation is 09's scope and the handbook is explicit that it is not on the search critical path (`:14`, `:91`). |
| **14 — i18n** | SRCH-002 (sub-note) | `sanitize_query_for_log`'s `isalpha()` collapse of Cyrillic and loss of Serbian Latin characters and digits degrades log triage. Recorded inside SRCH-002; **classification deferred to 14** to avoid duplicating. |
| **15 — authorization** | SRCH-004, SRCH-008 | See above — semantics stay in 08 by 15's own handbook. |

### Audit-input integrity (the phase-08 handbook is the third leg of a known defect)

The DECLINE conflict now exists in **three** audit-input files, not one:

| File | Line(s) | Asserts |
|---|---|---|
| `04-audit-auth-login.md` | — | recorded as 04-VAL-005 |
| `06-audit-pii-consent.md` | — | recorded as 06-VAL-004 / PII-113 |
| `08-audit-search-fts.md` | `24, 40, 53, 118` | **SRCH-012** |

The code and `technical-specification.md` are correct in all three cases; the
rubrics are stale. **One owner, one decision, three file edits** — and the
general defect is the audit-input severity taxonomy itself, which phase 06
already named. See **VAL-002**.

---

## Findings Requiring Architectural or Structural Change

These are not patches. Each needs an owner decision or a structural extraction;
ordering matters.

### 1. One querysets-level ad-visibility predicate — SRCH-004 + SRCH-008
**The single most important decision in this phase.** The public-visibility rule
is de-facto owned by `apps/ads/services/listings_query.py:131-136` and is
*re-implemented differently* by `find_matching_ads`, so the alert path
demonstrably ships ads that the web path hides. `get_account_state()` is
instance-level, so nothing reusable exists. **Requires:** promote a named
querysets-level predicate in `apps/ads`, declare its terms (including the
`is_banned` decision), consume it from all four sites, and land it together with
06-VAL-003's `apps/users` audience predicate. **Blocked on an owner decision**
that has now been open across two phases.

### 2. A project-wide cache-version contract — SRCH-007 (and SRCH-005)
Four modules share `try: cache.incr(KEY) / except ValueError: cache.set(KEY, 1)`
with **no timeout**, so four independent counters self-evict after 300 s while
the entries they invalidate live 360 s. Fixing `give_consent()` alone (SRCH-005)
leaves the same user-visible failure reachable by a second path. **Requires:** a
declared "durable monotonic cache-version key" contract in `apps/core`, adopted
by all four sites — plus, ideally, one `post_save` receiver on
`User.is_declined` so account-state → search-cache invalidation stops being a
per-call-site convention.

### 3. Input bounds modelled as part of the DTO contract — SRCH-001, SRCH-006, SRCH-011
Three findings, one cause: `BaseInputModel` carries only `extra="forbid"` and
imposes **no** length, count, or charset constraints, so every bound is a
per-view convention that can be forgotten — and one of them already is
(SRCH-006). **Requires:** the boundary layer declares bounds (count, length,
charset) once, enforced by both DTO and model, so a new endpoint cannot
reintroduce an unbounded path.

### 4. One shared `get_client_ip` + one rate-limit module — SRCH-010, SRCH-013
Three byte-identical copies of a header-trust function, two undocumented
budgets, two 429 body shapes, and a scheme that `nginx.conf:71`'s append
semantics makes spoofable. **Requires:** a single helper in `apps/core` and one
limiter with a `StrEnum` budget table. Also closes 04-AUT-003.

### 5. A database-level invariant for the popularity counter — SRCH-003
`get_or_create`'s atomicity is a no-op without a unique index, so the invariant
is currently held only by luck. **Requires:** a data migration that deduplicates
and then adds `UniqueConstraint`, plus removal of the misleading index comment
that made this look handled.

### 6. A declared logging policy — SRCH-002
`redact_search_query` exists and works; it is simply not called. **Requires** a
project-level rule enforced by the formatter or a logging filter, not a
per-call-site substitution — otherwise the next raw-input log line repeats this.
Phase 06 already owns the root cause; phase 08 contributes the search instance.

### Not structural (patches or documentation)
SRCH-009 (predicate change + ambiguity fix — but a design decision first),
SRCH-012, SRCH-014, SRCH-015.

---

## VAL Findings (new — raised by this validation, not by the auditor)

### VAL-001 — SRCH-001's crash threshold is a cgroup memory limit, and it is a *production* setting
**Severity: HIGH (as a durability/rollout risk on SRCH-001) · Type: MISCONFIGURED-BY-DEFAULT**

The auditor's report describes "the PostgreSQL backend being killed mid-request"
without identifying the mechanism, and its remediation is input validation alone.
Both are incomplete. The kill is `signal 9` from the cgroup OOM killer, and the
cap is `mem_limit: ${DB_MEM_LIMIT:-1g}` (`docker-compose.yml:15`). `DB_MEM_LIMIT`
is **unset in `.env.prod`, `.env.dev` and `.env.test`** — verified — so **1 GB
is the shipped default for production**, not a local artefact. The memory cap is
what converts "an expensive query" into "a cluster-wide outage"; on a
host-tuned PostgreSQL the same request would have degraded to a slow query.

**Required:** treat `DB_MEM_LIMIT` as a **load-bearing safety parameter** —
document it in `.env.prod.example`, state the value the profile expects, and
treat any change to it as a capacity decision. And ship `statement_timeout`
(03-DB-004) with the input cap, because the cap is currently the *only* thing
between an attacker and a full outage.

### VAL-002 — The audit-input DECLINE conflict is now in three handbooks, and the taxonomy defect is the root cause
**Severity: MEDIUM · Type: AUDIT-INPUT DEFECT**

SRCH-012 is the *third* occurrence (04-VAL-005, 06-VAL-004, 08-SRCH-012) of one
stale assertion surviving in the audit instructions after two validators already
ruled on it. Phase 06's own validation had already logged this as a
cross-phase duplicate (**06-VAL-001**: "the DECLINE doc conflict is filed in two
phases") and separately as an audit-input defect (**06-VAL-004**). It is now in
three. That is a process failure, not three typos: the phase-08 handbook was
written from an understanding of DECLINE that the code and spec contradict, and
nothing in the audit process re-derives handbook claims from the current spec.
**Required:** one pass over all fifteen phase handbooks to reconcile their
semantic claims against `technical-specification.md` and the code, owned once.
Until that pass exists, expect further rubric-driven false findings — this
phase produced one (SRCH-012), phase 04 produced one (04-VAL-005), phase 06
produced one (06-VAL-004), and 06 already predicted the pattern.

### VAL-003 — `_fuzzy_match_by_name` resolves a category by display name, so duplicate names silently return nothing
**Severity: MEDIUM · Type: BEST-PRACTICE (validator addition; folds into SRCH-009)**

Not in the auditor's report. `search.py:437-444` maps the matched display name
back to a `Category` by taking the **first** entry with that name. Two active
categories sharing a display name therefore scope a single-word search to an
arbitrary branch and can return **zero** results where matches exist.
Display-name collisions are routine after i18n/catalogue work (`name_i18n` is
free-form JSONB; no uniqueness constraint is recorded on `name` in
`db-schema.md`). This was discovered *by* this validation when a probe artefact
created exactly that collision and made a correct finding look refuted. Resolve
the match to `id`s from a name→ids index and treat an ambiguous name as "no
guess".

### VAL-004 — An audit DoS reproduction can crash the shared test database mid-validation
**Severity: MEDIUM · Type: PROCESS / ROLLOUT SAFETY**

The phase-08 auditor's reproduction took the shared `mko-bazuna-test`
PostgreSQL into crash recovery, and phase 09/10/13 validators were running
against it at the time. Any red/green evidence captured concurrently is
suspect — this is the same hazard 06-VAL-010 recorded for concurrent runs, with
a worse failure mode. **Required:** any destructive or DoS-shaped probe must run
on a private instance. This validation did so throughout (a throwaway
`postgres:18-alpine` on its own port, destroyed afterwards), and it is the
reason every result here is trustworthy while concurrent runs are not.

### VAL-005 — Phase-handbook prefix (`SRH-`) disagrees with the executed prefix (`SRCH-`)
**Severity: LOW · Type: NAMING / TOOLING**

`08-audit-search-fts.md:137` mandates `SRH-`; the executed task specified
`SRCH-`. Separately, the search source already carries hard-coded `SRH-001`…
`SRH-007` markers in `cache.py`, `category_fuzzy.py`, `search.py`,
`autocomplete.py` and `save_search.py` docstrings that refer to an unrelated
in-code convention. Remediation trackers keyed on `SRCH-NNN` will not collide,
but any tool or grep keyed on `SRH-` will produce false matches against the
codebase. Phase 04's validator raised the same class of issue for `AUT-`.
**Required:** keep `SRCH-` (it is unambiguous) and record the collision hazard
so no automation greps `SRH-` in this repo.

### VAL-006 — The daily alert job is a second, ungated consumer of unbounded user input
**Severity: MEDIUM · Type: BEST-PRACTICE (rollout-safety note on SRCH-011)**

`send_alerts._collect_alerts` iterates **every** `SavedSearch(is_active=True)`
and issues one `websearch_to_tsquery` query per entry (`send_alerts.py:112-115`),
against a `TextField` that accepts 50 000 characters. Unlike the search path,
this is **not** feature-gated and runs on a schedule whether or not anyone is
looking. I make **no timing claim** — quantifying the alert-path cost is phase
13's scope — but the input bound must land for the job, not only for the view.
Bound `SavedSearch.query` at the model as well as the DTO so the scheduler
cannot be reached with an unbounded value.

---

## Rollout Analysis

| Risk | Assessment |
|---|---|
| **Two findings must ship as a pair** | SRCH-005 + SRCH-007. Fixing only the missing `on_commit` leaves the same invisible-ad outcome reachable via the 300 s counter reset; fixing only the counter leaves the call site undeclared. Ship together or the restoration bug survives in a harder-to-reproduce form. |
| **Three findings must ship as one commit** | SRCH-004 + SRCH-008 + 06-VAL-003. Two predicates, two apps, one change. Splitting them reproduces the drift the decision exists to remove. |
| **SRCH-001's cap is a behaviour change** | A `max_length=10` feature cap can break any existing consumer sending more. Audit the four filter templates first; if the UI can already emit >10, that is a **separate UI defect** the cap would expose — the cap must land with or after it, never before. |
| **`IMMEDIATE_ALERTS_ENABLED` must stay `False`** | Until both predicates exist. It defaults to `False` (`base.py:349`); the daily digest is **live and ungated** today, and the immediate path additionally ships a working deep link to a hidden ad. |
| **No rollback path for the OOM** | Crash recovery is PostgreSQL's, and it took ~1.6 s here — but a second crashing request restarts the cycle. There is no backoff, no circuit breaker, and no `statement_timeout`. Until one exists, the cap is the only control. |
| **SRCH-003's migration is not reversible by `migrate back`** | Deduplication destroys rows. Take a backup and verify the dedup SELECT's row counts before applying. |
| **SRCH-012/014 are doc-only** | No runtime risk, but they touch files other validators and agents read. Land them as one documentation commit, separate from code. |

**Execution readiness.** Targets verified to exist in the working tree: all
cited file:line anchors were re-read during this validation, and every runtime
claim was reproduced against code at HEAD `9e96b84`. **12 of 15 findings are
immediately actionable.** The three that are not — SRCH-004, SRCH-008, and
SRCH-009's scope question — are blocked on owner decisions, not on missing
information.

---

## Required Fixes

Ordered by dependency, not by severity.

**P0 — ship before rollout**

1. **SRCH-001** — bound `feature_slugs` at the boundary. Pydantic
   `conlist`/count cap **plus** a catalogue-membership whitelist.
   **Ceiling 10, not 120** — 20 already costs 1.3 s, 40 costs 7.9 s.
2. **VAL-001 + 03-DB-004** — set `statement_timeout` on the `default` alias.
   Without it, the input cap is the only bound in the system, and any legitimate
   large filter set is still unbounded.
3. **VAL-001** — document `DB_MEM_LIMIT` in `.env.prod.example`; treat the 1 GB
   default as a load-bearing safety parameter, not an incidental tuning knob.
4. **SRCH-003** — data migration: deduplicate `popular_searches` on
   `query_normalized`, then add `UNIQUE` in a **new** `0003` (do not edit the
   already-applied `0001`/`0002`). Delete the misleading index comment at
   `models.py:56-58`.
5. **SRCH-006** — reject NUL (and other control characters) in the shared
   sanitiser both views already call. Fix the **second** call site
   (`increment_popular_search`), not the first (`record_event` is already
   guarded). Do not wrap the whole call in `try/except`.
6. **SRCH-002** — call `redact_search_query` on the search logging path; audit
   every other `sanitize_query_for_log` call site for the same substitution.
7. **SRCH-004 + SRCH-008 + 06-VAL-003** — one change: two declared predicates.
   Keep `IMMEDIATE_ALERTS_ENABLED=False` until both land.

**P1 — ship in the same cycle**

8. **SRCH-007 + SRCH-005** — one change: the cache-version contract in
   `apps/core` (durable, `timeout=None`) adopted by all four version keys, plus
   one `post_save` receiver on `User.is_declined`. If the shared helper cannot
   land immediately, add `timeout=None` to all four `cache.set` calls in the
   same commit — do not leave three of them behind.
9. **SRCH-010 + SRCH-013** — one `get_client_ip` in `apps/core` reading
   `X-Real-IP` (nginx overwrites it) → `XFF[-1]` → `REMOTE_ADDR`; one limiter
   with a `StrEnum` budget table; one 429 body shape. Closes 04-AUT-003.
10. **SRCH-011 + VAL-006** — cap `SavedSearch.query` at the **model** as well as
    the DTO, so the scheduler cannot be reached with an unbounded value.
11. **SRCH-015** — derive `has_results` from the rendered rows, not a second
    count. Ship with the cache-coherency work.

**P2 — design and documentation**

12. **SRCH-009 + VAL-003** — owner decision on the narrowing, then: disjunctive
    FTS branch instead of a hard filter, and name→ids resolution with
    "ambiguous ⇒ no guess".
13. **SRCH-012 + VAL-002** — reconcile the DECLINE assertion across all fifteen
    phase handbooks. One pass, one owner.
14. **SRCH-014** — correct the three-line SWR docstring. Doc-only commit.
15. **VAL-005** — record the `SRH-` / `SRCH-` collision hazard so no automation
    greps `SRH-` in this repository.

---

## Advisory Recommendations

Not required to close any finding. Each is a durability improvement that
prevents a class of the defects above from recurring.

1. **A `SELECT … FOR UPDATE` on the submission path.** A cheap, named guard
   against two concurrent publishes interleaving a double
   `update(status=PUBLISHED)`. It is a mitigation for a risk no finding owns;
   adopt it deliberately or record the decision not to.
2. **Give the search cache a `_meta` introspection path.** A deliberate
   `cache.get(key)` returning `{"ids": [...]}` already carries the count, the
   truncation flag and the version. SRCH-015's fix is then a read, not a second
   count — and cache hit-rate work gains a single round trip.
3. **Promote the "an FTS assertion needs a positive control" rule from this
   report into the audit handbook.** The Method trap is real and general: a
   `0 hits` result is indistinguishable from a missing trigger. Encoding "assert
   the trigger, then assert a *positive* match" in the handbook prevents the next
   phase from repeating it — and VAL-003 shows the same class of failure one
   level up, in a *positive* assertion.
4. **A single `features` bound, stated in the spec.** The spec documents AND
   semantics for `?features=` but no cardinality limit, which is why SRCH-001
   could not be graded as a deviation. Adding the bound to
   `technical-specification.md` (alongside `:228`) turns it into a checkable rule.
5. **A `pipeline`-level contract test for the rate limiters.** Assert that
   `/_get_client_ip` agrees with `$binary_remote_addr` for a request carrying a
   hostile `X-Forwarded-For`. This is the only test that would have caught
   SRCH-010, and it is cheap.

---

## Closing Assessment

The phase-08 report is **technically strong**. It found the two most serious
defects in the app — an unauthenticated cluster-kill and a PII leak on an
always-on path — and it got the architecture right on the visibility predicate,
correctly identifying that `find_matching_ads` bypasses the app's own gate and
that the instance-level `get_account_state()` is why nobody fixed it. It also
disciplined itself on the things that usually go wrong: it recorded the FTS
Method trap instead of trusting its own "0 hits", it left translation to phase
09 and latency to phase 13, and it kept the spec/handbook conflict as a finding
rather than quietly grading code against a wrong rubric.

Its weaknesses are consistent and narrow: **mechanism** (it described *that*
the backend dies without saying the memory cap is what kills it, and treated
input validation as a complete fix for SRCH-001), and **harmonisation across
phases** (it re-raised a decision phase 06 had already filed, and re-introduced
a stale rubric assertion phase 06 had already ruled on). Neither is a
correctness failure in the findings themselves.

Of the 15 findings: **0 rejected, 13 confirmed, 2 adjusted down.** Six require
architectural or structural change; the two owner-blocked items (SRCH-004,
SRCH-008) have been open across two phases and are now the critical path for
phase 06 as well. The critical finding is real, reproducible, and cheaper to fix
than it looks — but only if the fix is bounded properly, and only if
`statement_timeout` lands with it.













