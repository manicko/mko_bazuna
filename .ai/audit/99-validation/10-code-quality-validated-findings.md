---
type: doc
name: Phase 10 — Code Quality — Validated Findings
phase: 10-code-quality
findings_file: .ai/audit/10-code-quality/findings.md
date: 2026-09-28
auditor_findings: 19 (CRITICAL 0 · HIGH 3 · MEDIUM 12 · LOW 4)
validated_findings: 19 (CRITICAL 0 · HIGH 0 · MEDIUM 12 · LOW 7)
merged: 1 (partial — CQ-002 login half → ENT-005)
rejected: 0 whole findings · 7 sub-claims rejected
adjusted: 11
---

# Phase 10 — Code Quality — Validated Findings

Every measurement in this phase was reproduced from the working tree. Line
citations were checked individually; several were wrong and are corrected below.

> **Scope note.** `problems_only = TRUE` for this validation. Non-problems
> (confirmed working as documented, deliberate design, correct architecture) are
> recorded only in the **Cross-Phase Reconciliation** and **Refuted Evidence**
> sections. Nothing in this report is a clean bill of health for the codebase;
> it is a list of things that need changing.

## Final Counts

| Severity | Auditor | Validated |
|----------|---------|-----------|
| CRITICAL | 0 | 0 |
| HIGH | 3 | **0** |
| MEDIUM | 12 | **12** |
| LOW | 4 | **7** |
| **Total** | **19** | **19** |

All three HIGH findings were downgraded. None of the three is an availability,
security, or data-integrity defect; each is a structural/maintainability concern
whose real-world consequence is "a future change is more likely to be made
wrongly". For a code-quality phase that is MEDIUM by construction. Three MEDIUM
findings (CQ-007, CQ-010, plus the evidence corrections that did not move
severity) account for the LOW band being larger than the auditor's.

**Net movement:** 3 HIGH → 0 HIGH (all three moved to MEDIUM); 2 MEDIUM → LOW
(CQ-007, CQ-010); MEDIUM count held at 12 because three auditor-MEDIUM findings
were promoted into the band vacated by the HIGHs.

---

## Decision Table

| ID | Title (abbrev.) | Auditor sev. | **Verdict** | **Final sev.** | One-line justification |
|----|-----------------|--------------|-------------|----------------|------------------------|
| CQ-001 | `ad_edit` is a 193-line view | HIGH | **ADJUSTED** | **MEDIUM** | Measurement exact (73→265 = 193 lines; largest function in the repo; two byte-identical 14-line `SubmitAdInput` blocks at 160-173 / 203-216 confirmed). But it has no demonstrated defect, and the refactor collides with two security remediations on the same lines — see Cross-Phase Reconciliation §A. |
| CQ-002 | Bot handlers own the data access layer | HIGH | **ADJUSTED + PARTIAL MERGE** | **MEDIUM** | Code facts verified verbatim, but the `login.py` half re-files phase-01 `ENT-005` (already validated HIGH→MEDIUM / `BEST-PRACTICE`) and contradicts it on severity. Root-cause sentence "no `__init__.py` contract" is factually false. |
| CQ-003 | `CategoryRejectReason` never enforced | MEDIUM | **CONFIRMED** | MEDIUM | Enum has 0 production call sites (whole-corpus grep); `review.py:107-116` concatenates the raw POST value into a TEXT column; `review.html:149-156` mirrors all 8 members exactly, in order. |
| CQ-004 | Three POST views bypass Pydantic | MEDIUM | **ADJUSTED** | MEDIUM (`BEST-PRACTICE`) | The two `_int_or_none` closures are byte-identical (verified). **Reproduction step 3 is false** — Django's `PositiveIntegerField` emits no DB check constraint, so `-1` is silently stored, not a 500. The gap is real; the impact framing is wrong. |
| CQ-005 | Raw `AdStatus` string literals | MEDIUM | **ADJUSTED** | MEDIUM | All 7 cited template lines + 2 Python lines verified. Count is **9 sites, not 11** (the report's own evidence block sums to 9). |
| CQ-006 | Raw locale literals, `LanguageLocale` ignored | MEDIUM | **ADJUSTED** (strengthened) | MEDIUM | Verified. But the report **missed the largest cluster** — `telegram_bot/handlers/ad_create/submit.py:65-70`, six raw `.get("ru"/"bs"/"en")` calls in the bot's submit path. |
| CQ-007 | `cache.py` — 15 near-identical functions | MEDIUM | **ADJUSTED** (2 sub-claims rejected) | **LOW** | 245 lines / 15 functions / 12 in exact `cache.get/set/delete` form — all verified. But the key and TTL are already single-sourced via `Final` constants, so the claimed "12-place change" impact is false, and the proposed `CacheEntry` helper is pure indirection. |
| CQ-008 | `submit_ad` mixes six responsibilities | HIGH | **ADJUSTED** | **MEDIUM** | 124 lines (122→245) verified. No demonstrated defect; same class as CQ-001. |
| CQ-009 | `AdEditInput` defaults blank a live ad | MEDIUM | **CONFIRMED** | MEDIUM | `title: str = ""` / `description: str = ""` at `submission.py:87-88` verified. A POST omitting either key persists `""` over live content. Real correctness gap. |
| CQ-010 | 81 deferred imports | MEDIUM | **ADJUSTED** (mostly rejected) | **LOW** | The count is **92**, not 81 — and the sample shows most are legitimate (`AppConfig.ready()`, bootstrap/CLI, model-load deferral). The one actionable cluster (`review.py:69,96,135`) is a **file move**, not an abstraction. |
| CQ-011 | Divergent fuzzy thresholds | MEDIUM | **CONFIRMED** | MEDIUM | `search.py:407` `cutoff=0.8` (behind two exact tiers) vs `listings.py:281` `cutoff=0.6` (no tier) verified. The asymmetry is worse than reported. |
| CQ-012 | Untyped service boundaries | MEDIUM | **CONFIRMED** | MEDIUM | `priority_calculator.py:23` returns bare `dict` (plus 3 more); 3 methods in `lookup_resolution.py` carry `category` unannotated with `# type: ignore[type-arg]` — verified. |
| CQ-013 | Consent cookie names duplicated as literals | LOW | **CONFIRMED** | LOW | `consent.py:51-54` constants vs raw reads at `context_processors.py:54,86,87,96` and `preferred_city.py:90` — all verified. Note `PREFERRED_CITY_COOKIE_*` already establishes the pattern, so this is a relocation, not a new module. |
| CQ-014 | `/alerts` promises a toggle no handler serves | MEDIUM | **CONFIRMED** | MEDIUM | `alerts.py:88` "Reply with number to toggle" verified; `alerts.py` registers only `/alerts`, `unsub:`, `unsub_on:` — no numeric handler exists. `SavedSearchState` has 0 call sites repo-wide. |
| CQ-015 | `listings.py` / `search.py` duplicate the query + context build | MEDIUM | **ADJUSTED** (strengthened) | MEDIUM | 11-field `ListingsQueryParams` build verified in both. The context is **20 shared keys, not ~15** — `listings.py`'s entire context is a strict subset of `search.py`'s, and both render the same two templates. |
| CQ-016 | Dead code | LOW | **CONFIRMED** (+3 symbols) | LOW | All 6 named symbols confirmed to have exactly one occurrence (their definition) across the whole corpus. `apps/api/` contains 0 files. |
| CQ-017 | Packaging / enum hygiene | LOW | **CONFIRMED** | LOW | `apps/ads/services/` has no `__init__.py`; `orm.py:23` puts `"_get_ad_status"` in `__all__`; `AdvisoryLockId` ordering (1-9, 100-104, 11, 12, 110, 111) verified verbatim. |
| CQ-018 | `require_POST` inconsistency + hardcoded admin URLs | LOW | **ADJUSTED** (counts wrong) | LOW | 9 inline `request.method` checks verified exactly. But `@require_POST` is applied at **11 sites in 7 modules**, not 6, and there are **6** hardcoded `/admin/` URLs, not 5. |
| CQ-019 | 1387 comment-only lines / 14:1 ratio | LOW | **ADJUSTED** | LOW | Measured **1387** comment-only lines over 27,275 production Python lines (excluding tests/migrations) — the report's 1,474 is 6.3% high. |

**Type note.** The phase-10 handbook defines a *severity* taxonomy but no `Type`
vocabulary. Following phase 01's precedent, this report uses `SPEC-DEVIATION`
for violations of an explicit project rule, `BEST-PRACTICE` for structural
improvements with no demonstrated defect, and `DOC-UPDATE` for stale
documentation. Type assignments: `SPEC-DEVIATION` — CQ-003, CQ-005, CQ-006,
CQ-009, CQ-011, CQ-012, CQ-017; `BEST-PRACTICE` — CQ-001, CQ-002, CQ-004, CQ-008,
CQ-014, CQ-016; `DOC-UPDATE` — CQ-013, CQ-018, CQ-019.

---

## Checkpoint 1 — Auditor analysis

- **Stage:** Auditor analysis
- **Findings:** 19 (CRITICAL 0 · HIGH 3 · MEDIUM 12 · LOW 4), prefix `CQ-`
- **Reproduction attempts recorded:** 14 `R#` checks. **13 reproduced**,
  **1 partly refuted** (R-14 deferred-import census — 92 not 81), plus 6
  arithmetic slips in the prose (see Audit-Input Defects).
- **Structure:** file:line evidence throughout, per-finding effort/priority,
  remediation table, 3 deep-dive appendices. Evidence discipline was good.
- **Checkpoint status:** closed

---

## Checkpoint 2 — Researcher verification

- **Stage:** Researcher verification
- **Method:** independent AST + tokenizer census over `src/backend` and
  `src/telegram_bot` (production Python only — tests, `conftest.py` and
  `migrations/` excluded), whole-corpus symbol reference counting, Django
  source inspection for the CQ-004 reproduction, and direct reads of every
  cited file.
- **Measurements taken by the validator:**

| Measurement | Auditor | Validator | Agreement |
|---|---|---|---|
| Largest function in repo | `ad_edit` 193 lines | `ad_edit` 193 lines (`edit.py:73`→`:265`) | ✅ exact |
| 2nd largest | `search` 184 | `search` 184 (`search.py:46`) | ✅ exact |
| Functions >100 lines | 13 | **13** | ✅ exact |
| Functions >60 lines | 54 | **54** | ✅ exact |
| Total functions | 734 | 713 | ⚠️ count differs (definition of scope); immaterial — both headliners match exactly |
| `submit_ad` length | 124 | **124** (`submission.py:122`→`:245`) | ✅ exact |
| Byte-identical `SubmitAdInput` blocks | 2 × 14 lines | **2 × 14 lines**, byte-identical (`edit.py:160-173`, `:203-216`) | ✅ exact |
| `cache.py` size / function count | 245 / 15 | **245 / 15** | ✅ exact |
| Identical cache fns | 12 | **12** | ✅ exact |
| `get_close_matches` cutoffs | 0.8 / 0.6 | **0.8** (`search.py:407`) / **0.6** (`listings.py:281`) | ✅ exact |
| `ListingsQueryParams` fields | 11 | **11** in both | ✅ exact |
| Shared template context | ~15 keys | **20 shared keys** | ⚠️ understated |
| Deferred imports | 81 | **92** | ⚠️ count wrong |
| Raw `AdStatus` literal sites | 11 | **9** | ⚠️ count wrong |
| Raw locale literal sites | 9 | **10 file-sites / 16 literals** | ⚠️ missed one file |
| Comment-only lines | 1474 | **1387** | ⚠️ 6.3% high |
| Inline `request.method` checks | 9 | **9** | ✅ exact |
| `@require_POST` applications | "6 views" | **11 applications in 7 modules** | ⚠️ count wrong |
| Hardcoded `/admin/` URLs | 5 | **6** | ⚠️ missed one |
| `SavedSearchState` / `is_consent_given` / `invalidate_group` dead | 0 call sites | **0** | ✅ exact |
| `CategoryRejectReason` unenforced | 0 call sites | **0** | ✅ exact |
| `apps/api/` empty | 0 files | **0 files** | ✅ exact |

- **Merge candidates:** 1 hard partial merge (CQ-002 `login.py` half → ENT-005).
  2 soft relationships recorded (CQ-014 ↔ ENT-005 bot-side dead code; CQ-016 ↔
  AUTHZ-005).
- **Cross-phase conflicts:** **1** — CQ-002 vs ENT-005 on severity and on the
  target module path. See Cross-Phase Reconciliation §B.
- **Checkpoint status:** closed

---

## Checkpoint 3 — Per-finding validation

- **Stage:** Per-finding validation
- **Decisions:** Validated unchanged **8** (CQ-003, CQ-009, CQ-011, CQ-012,
  CQ-013, CQ-014, CQ-016, CQ-017) · Adjusted **11** (CQ-001, CQ-002, CQ-004,
  CQ-005, CQ-006, CQ-007, CQ-008, CQ-010, CQ-015, CQ-018, CQ-019) ·
  Merged 1 partial · Rejected 0 whole findings
- **Sub-claims rejected outright:** 7 (see Refuted Evidence below)
- **Runtime reproductions:** 0 — the audit is read-only and the `mko-bazuna-dev`
  stack is crash-looping; every check was static or library-source based. The one
  claim that needed a live DB (`CQ-004`'s `IntegrityError` → HTTP 500) was
  refuted by reading Django's `PositiveIntegerField` source instead.
- **Evidence anchor:** this document; every line reference verified against the
  working tree at the commit this validation ran against.
- **Checkpoint status:** closed

---

## Checkpoint 4 — Rollout safety

- **Stage:** Rollout safety
- **Findings reviewed:** 19
- **Risks:** 4 HIGH — the three remaining HIGH→MEDIUM downgrades' justification,
  the CQ-001 ↔ AUTHZ-002/AUTHZ-007 line collision, the CQ-002 ↔ ENT-005 double-fix,
  and CQ-010's `PLC0415` interaction with the existing `ruff` config.
- **Rollout:** no finding requires a migration. CQ-004 does *not* require one
  (the fix is validation at the boundary, not a schema change). CQ-017's file
  move touches `apps/ads/admin.py` and `apps/moderation/views/api_bulk.py`
  import sites and must land as one commit.
- **Dependency chains:** AUTHZ-007 → AUTHZ-002 → CQ-001; ENT-004 → CQ-002;
  CQ-010 → CQ-002 (the file move deletes the deferred imports CQ-010 asks to
  hoist).
- **Checkpoint status:** closed

---

## Validation Detail

### CQ-001 — [MEDIUM] — `ad_edit` is a 193-line view

**Verdict: ADJUSTED — HIGH → MEDIUM.**

**Measurement: exact.** `edit.py:73`→`:265` is 193 lines including a 17-line
docstring; 175 lines of body. The validator's own AST census places it first in
the repository (`search.py:46` `search` at 184 is second). The two
`SubmitAdInput` blocks at `edit.py:160-173` and `:203-216` are 14 lines each and
**byte-identical** — same indentation, same 11 keyword arguments in the same
order, including `user_id=ad.user_id` at `:170` and `:213`.

Every other cited anchor resolves: `:94-101` ownership check, `:117`
`select_for_update`, `:130-132` `AdEditInput` construction, `:136-141` currency
fallback, `:146` reactivation, `:190` PUBLISHED branch, `:235-243` and
`:250-262` the two hand-written ORM write paths, `:30-55` `_apply_price_change`
(which `apps/ads/tests/test_edit.py:30` does import).

**One imprecision.** The report calls the branch structure a "four-way `AdStatus`
FSM branching". It is a **three-way status branch** (`:146` reactivation /
`:190` PUBLISHED / `:248` everything else) containing a **field-driven**
sub-branch at `:233` (price/photo-only edit) that is not status-driven. Three
status branches, not four.

**Why HIGH is wrong.** The project charter for this phase is the rulebook.
Rulebook rules engaged: *"Keep modules small and focused on a single
responsibility"* and *"Avoid overengineering"*. A long function is neither a
rule violation with a runtime consequence nor a security issue. It has no
demonstrated defect: every existing test passes, and the view is internally
consistent. The correct severity for a maintainability finding with no measured
consequence is MEDIUM — and phase 01's validator set exactly this precedent when
it downgraded `ENT-005` (same class: structural concern, no defect).

**Rejected in the recommendation.** Two of the three proposed steps are
unjustified abstractions:
- *"`edit_ad` in `apps/ads/services/edit_ad.py`"* — **accepted**, this is the one
  genuinely structural change and it is a straight extraction of an existing
  function body into the app's own `services/` package (all 13 apps have one).
- *"an `ErrorPage` enum"* — **rejected.** `HttpResponseForbidden` /
  `HttpResponse(status=400)` are already self-describing; a bespoke enum adds a
  layer with no consumer.
- *"`_build_submit_input` helper"* — **rejected.** Hoisting the duplicated block
  into one local variable costs two lines and creates no new name.

**Required scoping amendment.** See Cross-Phase Reconciliation §A — this refactor
must not be applied independently of AUTHZ-007/AUTHZ-002.

---

### CQ-002 — [MEDIUM] — Bot handlers own the data access layer

**Verdict: ADJUSTED — HIGH → MEDIUM; the `login.py` half MERGED into ENT-005.**

**Measurements: exact.** `login.py:154` `_claim_login_token`, `:169-187` the
`UPDATE … RETURNING`, `:190` `handle_login_orm`, `:209-262` the inline
`@sync_to_async` closure; `alerts.py:92-99` `get_user_saved_searches`,
`:237` `_resolve_owned`, `:244-263` the `select_for_update()` + `save()` pair.
`telegram_bot/services/` contains exactly the 9 modules the report lists
(plus `services/__init__.py`, which the evidence block omits).

**Two errors in the report.**

1. **Root cause is factually wrong.** *"`telegram_bot/services/` has no
   `__init__.py` contract"* — `src/telegram_bot/services/__init__.py` **exists**.
2. **The claim about deferred imports is backwards as written.** The report
   presents `contact.py:269-271` / `support.py:159-160` as handlers
   "working around the missing service". `alerts.py:22` imports
   `from apps.search.models import SavedSearch` at **module** level, so there is
   no import-time constraint preventing `apps.*` at module scope in a handler.
   The deferral in `contact.py`/`support.py` is inconsistent, not necessary.

**Severity.** The `login.py` half is already owned by phase 01 as `ENT-005`,
validated at **MEDIUM / `BEST-PRACTICE`**, with phase 04 independently rating the
`UPDATE … RETURNING` mechanism **sound and zero-TOCTOU**. Filing the same code
at HIGH directly contradicts two completed validations. The
`alerts.py` / `contact.py` / `support.py` halves are genuinely new — no phase has
filed them — but they are layering consistency, with no defect, no security
impact, and no data risk. MEDIUM.

**Rejected in the recommendation.**
- *`telegram_bot/services/login.py`* — **rejected as the wrong location.**
  `ENT-005`'s already-validated target is `apps/users/services/login_token.py`,
  because the token lifecycle is a *cross-process* protocol shared with the web
  view. Placing it under `telegram_bot/` would re-create the split the fix is
  meant to remove.
- *the AST architecture test* — **rejected as speculative.** Phase 10 proposes
  three AST tests across CQ-002 and CQ-004; see Proportionality.

---

### CQ-003 — [MEDIUM] — `CategoryRejectReason` is never enforced

**Verdict: CONFIRMED.** Every element verified.

- `enums.py:167-182` — class at 167, docstring 168-173, 8 members 175-182.
- Whole-corpus grep: `CategoryRejectReason` occurs in `enums.py` (definition +
  `__all__`), `apps/core/__init__.py` (re-export) and `docs/02-database/db-enums.md`
  (documentation). **Zero production call sites.**
- `review.py:107-116` builds `reason = f"{reason_category}"` from a raw
  `request.POST.get("reason_category", "")` with **no validation whatsoever** —
  `reason_text` is stripped, `reason_category` is not even stripped.
- `review.html:149-156` contains exactly the 8 enum values, in the enum's
  declaration order. The template faithfully mirrors a Python enum that no Python
  code reads.

**Impact (corrected).** The stored value is `ModeratorActionLog.reason`, a TEXT
column. Because an arbitrary client string is concatenated into it, the category
is (a) unvalidated, so the 8-value vocabulary is advisory only, and (b)
structurally unqueryable — `reason LIKE 'adult_content'` and
`reason LIKE 'adult_content: …'` are different rows. That is a genuine
data-modelling defect, and the fix is cheap: expose the enum to the template
context and delete the duplicate hardcoded `<option>` list.

---

### CQ-004 — [MEDIUM] — Three POST views bypass Pydantic

**Verdict: ADJUSTED — mechanism confirmed, reproduction step 3 REFUTED,
reclassified `BEST-PRACTICE`.**

**Confirmed.** `save_search.py:39-46` and `cabinet/views/saved_searches.py:120-127`
are **byte-identical** 8-line `_int_or_none` closures (verified character by
character). `save_search.py:48-57` writes the result straight into
`SavedSearch.objects.create(...)`. `search/models.py:97` and `:102` are
`PositiveIntegerField`. Both views are POST-only with no other validation layer.

**Refuted — the headline reproduction.** The report states:

> *"Django's PostgreSQL backend adds `CHECK (min_price >= 0)` →
> `IntegrityError` → HTTP 500."*

This is **false**. Django's `PositiveIntegerField` (`PositiveIntegerRelDbTypeMixin`,
`IntegerField`) defines **no `check()` method and no DB constraint**. The only
positivity enforcement is `formfield(min_value=0)`, which applies to Django
forms — and neither view uses a form. Verified three ways:

1. `inspect.getsource(PositiveIntegerField)` returns only `get_internal_type()`
   and `formfield()`; no constraint logic.
2. `apps/search/migrations/0001_initial.py` creates `min_price`/`max_price` with
   no `CheckConstraint`.
3. A grep for `CheckConstraint|full_clean|MinValueValidator` across the whole
   `search` app returns **zero** hits.

So `POST /save-search/` with `min_price=-1` **succeeds** and persists `-1`.

**Corrected impact.** The defect is worse in one way and better in another than
reported: there is no crash and no error page — the row is created silently with
a negative price bound, so the saved search can never match. There is also no
`IntegrityError` class of failure to worry about. The boundary-validation gap is
still a real violation of *"Use Pydantic for all data models and validation"*
and of the convention `edit.py:124` documents ("Validate POST data via DTO
before any `ad.save()` call"), so MEDIUM stands — but the reproduction steps
must be rewritten before they go into a tracker.

**Rejected in the recommendation.** *The AST architecture test* — rejected as
speculative (see Proportionality). *`PreferredCityInput` DTO for
`preferred_city.py:42-99`* — accepted, but note that `preferred_city.py` already
imports `PREFERRED_CITY_COOKIE_MAX_AGE`/`PREFERRED_CITY_COOKIE_NAME` from
`apps.core.middleware.preferred_city` (`:17-18`), so the "one cookie helper"
ask is largely already satisfied there.

---

### CQ-005 — [MEDIUM] — Raw `AdStatus` string literals

**Verdict: ADJUSTED — count corrected 11 → 9.**

All cited lines verified: `dashboard.html:126,128,137`;
`admin/moderation/review.html:44,89,110`;
`analytics/moderation_dashboard.html:34`; `review.py:120,153`. That is **7
template lines + 2 Python lines = 9 sites**, which is exactly what the report's
own Appendix C block lists. The prose ("Eleven sites in total") and R-05 ("8
literals in 3 templates") both contradict it and each other.

**Additional fact the report under-uses.** `moderation_dashboard.html:34` is not
only a bare status literal — it is a bare status literal **inside a hardcoded
admin URL** (`/admin/ads/ad/?status__exact=on_moderation`). That single line is
the strongest case in the whole finding, because it shows the literal leaking
into the URL layer where `AdStatus.ON_MODERATION` cannot be interpolated in a
template. The recommended fix must therefore include a context-provided URL or a
template tag, not just the enum reference.

**Type:** `SPEC-DEVIATION` against *"Prefer `Enum` / `StrEnum` over raw strings
for fixed value sets"* (`python-code-standards.md:13`).

---

### CQ-006 — [MEDIUM] — Raw locale literals, `LanguageLocale` largely ignored

**Verdict: ADJUSTED — one site missed; finding strengthened.**

All 9 reported sites verified:
`categories/models.py:61-62`, `locations/models.py:53-54`,
`lookups/models.py:96-97` (all three the identical `if "ru" in name_i18n:`
triplication), `core/enums.py:231-244` (`fts_config` at 228-235,
`fts_vector_field` at 237-244 — both raw-string-keyed dicts *inside the enum
that exists to prevent exactly this*), `search/services/entity_suggestions.py:69`,
`search/models.py:115` (`default="bs"`, with `help_text` at `:116` naming
`LanguageLocale`), `search/views/save_search.py:55`,
`ads/management/commands/backfill_translations.py:20,21,39,106`.

**Missed.** `src/telegram_bot/handlers/ad_create/submit.py:65-70` — six raw
`.get("ru") / .get("bs") / .get("en")` calls building `SubmitAdInput`
translations. This is the **largest single cluster of raw locale literals in
production** and it sits on the bot's submit path. Corrected count: **10
file-sites, 16 literal occurrences.**

**The strongest confirmed claim.** `enums.py:5` states:

> *"No inline string literals for constants anywhere in the codebase."*

That is false, and it is false **inside the same 337-line file at lines 232-234
and 241-243**. A module-level claim of a codebase-wide invariant, contradicted
by the module itself, is a documentation defect as well as a rule deviation.

**Rejected in the recommendation.** *`apps/core/services/locales.py`* — rejected.
`LanguageLocale` already exists; a module wrapping it adds a hop without removing
any of the 16 literals. The correct fix is in-place: use
`LanguageLocale.RUSSIAN.value` at each site, and replace the two raw dicts with
`match` arms or `Final` class-level constants on the enum itself.

---

### CQ-007 — [LOW] — `cache.py` — 15 near-identical functions

**Verdict: ADJUSTED — MEDIUM → LOW; two sub-claims rejected.**

**Confirmed.** `cache.py` is 245 lines with **15** functions. Of those, **12**
(`get/set/invalidate_cached_criteria`, `_site_config`, `_bot_username`,
`_support_contacts`) are exactly the one-line `cache.get(key)` /
`cache.set(key, value, ttl)` / `cache.delete(key)` form — the count is precise.
The `anon_language` trio differs only by `.format(telegram_id=…)`.

**Rejected — the impact claim.** The report says *"a cache-key change or a switch
to `cache.get_or_set` must be applied in 12 places."* **False.** Each key is a
module-level `Final` (`CRITERIA_CACHE_KEY`, `SITE_CONFIG_CACHE_KEY`,
`BOT_USERNAME_CACHE_KEY`, `SUPPORT_CONTACTS_CACHE_KEY`,
`ANON_LANG_CACHE_KEY_PATTERN`) referenced as a **default argument** in each
function. Changing a cache key is a **one-line** edit. The parameterisation the
report recommends is already in place — the duplication is docstring boilerplate,
not logic.

**Rejected — the `CacheEntry` helper.** A `get_cached(key)` / `set_cached(key,
value, ttl)` class over 12 one-line wrappers is pure indirection and a direct
violation of *"Avoid overengineering"* and *"Prefer explicitness over
cleverness"*.

**Rejected — the logger sub-claim.** *"The module has no `logger` at all, unlike
every other module in `apps/core/utils/`."* Checked: of the 7 modules in
`apps/core/utils/`, **4 have no logger** (`cache.py`, `json_logging.py`,
`sanitize.py`, plus `__init__.py`). The claim is false, and a pure
cache-get/set/delete wrapper does not need one.

**What survives.** `python-code-standards.md:19` — *"Comment only non-trivial
logic; avoid obvious or redundant comments"* — is a real rule the module breaks
(`invalidate_criteria_cache` is 1 body line under an 8-line docstring restating
the signature). That is a documentation-density cleanup, not an architectural
defect. LOW, and the fix is deletion: trim the boilerplate docstrings.

---

### CQ-008 — [MEDIUM] — `submit_ad` mixes six responsibilities

**Verdict: ADJUSTED — HIGH → MEDIUM.**

`submission.py:122`→`:245` is **124 lines**, 7th largest in the repo. Every
responsibility the report enumerates is verifiable: filesystem I/O (141-159),
file promotion (166), transaction + lock (169-173), field mapping (176-215),
image row creation (218-227), FSM transition (230), delegation (239-241). The
`return False, ["Ad not found"]` on `Ad.DoesNotExist` (172-173) and the
`try/except Exception` thumbnail swallow (153-159) are both real.

**Why HIGH is wrong.** Same reasoning as CQ-001: the project rules
(*"Keep modules small and focused"*) are maintainability rules, and no rule, test
or runtime behaviour is violated today. Phase 01's `ENT-005` downgrade is the
direct precedent.

**The auditor's own sequencing claim is correct and is reinforced here.** It
argues `submit_ad` should be extracted *before* CQ-001, because it is the sole
bot↔web seam. That is right for maintainability reasons, but see
Cross-Phase Reconciliation §A — `submit_ad` is *also* where AUTHZ-002's guard
lands. The three changes are one change set, not a sequence of three.

**Deduplicated.** Its recommendation lands in the same
`apps/ads/services/edit_ad.py` as CQ-001's. Counted once.

---

### CQ-009 — [MEDIUM] — `AdEditInput` defaults blank a live ad

**Verdict: CONFIRMED.** `submission.py:87-88` is
`title: str = ""` / `description: str = ""`, with the validator at `:92-97`
turning `None` into `""`. The module's own docstring at `:82-84` acknowledges
the behaviour as known-but-deferred. A POST that omits `title` therefore persists
`""` over a published ad's title via `submit_ad` → `ad.title = input.title_ru`.
`tests/test_edit.py` has no case for an omitted title key.

The auditor is right that making the field required changes the response to
malformed POSTs (currently a silent blanking). Severity MEDIUM is appropriate:
it is a `SPEC-DEVIATION` against the Pydantic-boundary rule with a concrete
data-loss outcome, but it needs no emergency.

---

### CQ-010 — [LOW] — 81 deferred imports

**Verdict: ADJUSTED — MEDIUM → LOW; the count is wrong and the majority of the
phenomenon is legitimate.**

**Count corrected.** An AST scan of production Python (tests and migrations
excluded) finds **92** function-local imports, not 81. The report's own
accounting is internally inconsistent — the Problem text says "~14 are
legitimate" while the evidence block says "~26".

**Judged fairly, the sample shows most deferrals are correct engineering:**

| Pattern | Count | Verdict |
|---|---|---|
| `AppConfig.ready()` signal registration | 7 | **Required.** Django mandates deferred import in `ready()` to avoid `AppRegistryNotReady`. |
| CLI/bootstrap (`migrate_locked`, `scheduler`, `backfill_translations`, `seed_service`, `catalog/builder`) | ~21 | **Intentional.** Load-order control for migration/lock acquisition. |
| Signal handlers (`categories/signals.py`, `moderation/signals.py`, `lookups/signals.py`) | 6 | **Conventional** for Django signal modules. |
| Model-load deferral (`ads/models.py:665-666` inside `save()`) | 2 | **Genuinely wrong** — nothing about model loading requires deferral here. |
| `review.py:69,96,135` importing `apps.moderation.admin_actions` | 3 | **Genuinely arbitrary** — see below. |
| Everything else | remainder | Mixed. |

A blanket "deferred imports are bad" rule **is** the overgeneralisation the task
brief warned about, and the report half-commits to it. Seven of the largest
clusters are legitimate.

**The one clean, zero-abstraction fix.** `apps/moderation/admin_actions.py`
imports nothing from `apps.moderation/views/*` — there is **no cycle** to break.
The decisive evidence that the deferral is arbitrary:
`apps/moderation/views/api_bulk.py:16` imports the *same module at module level*,
in the same package, in the same process. Moving
`admin_actions.py` → `apps/moderation/services/admin_actions.py` deletes all three
deferred imports as a side effect, and the module's own docstring (`:1-5`) already
calls it a *service* while it sits at the app root.

**Rejected in the recommendation.** *A custom AST lint script
(`scripts/lint_no_deferred_imports.py`)* — rejected as overengineering;
`ruff`'s built-in `PLC0415` does this and is already a dependency. *Enabling
`PLC0415` in CI* — **accepted**, but with a measured exclusion list, otherwise the
gate fires ~26 times on legitimate `AppConfig.ready()` and bootstrap deferrals and
gets disabled within a week.

---

### CQ-011 — [MEDIUM] — Divergent fuzzy thresholds

**Verdict: CONFIRMED — the asymmetry is worse than reported.**

`search.py:391-413` `_fuzzy_match_by_name`, `cutoff=0.8` at `:407`;
`listings.py:276-282` `_suggest_category`, `cutoff=0.6` at `:281`.

The report says `listings.py` "skips the exact-match tier". Verified more
precisely — `search.py` has **three** tiers before fuzzy: slug exact match
(`:380-382`), locale-name exact match (`:385-387`), then fuzzy (`:388` →
`:407`). `listings.py` has **one**: fuzzy against raw slugs. So a user typing
the exact slug of an existing category gets no suggestion on `/`, but the correct
category on `/search/`. Unifying to a shared
`apps/categories/services/fuzzy.py` with a 3-tier ladder is a single
extraction of duplicated logic — proportionate, and it removes a user-visible
inconsistency.

---

### CQ-012 — [MEDIUM] — Untyped service boundaries

**Verdict: CONFIRMED.**

`priority_calculator.py:23` — `def calculate_priority(self, ad: Ad) -> dict:`,
returning an untyped 5-key literal at `:47-53`. Three more bare `dict`
signatures follow: `_calculate_content_score` (`:55`), `_calculate_user_score`
(`:70`), plus `flags: list[str]` at `:30`, `:58`, `:71` where the strings are a
closed vocabulary of moderation reasons.

`lookup_resolution.py` — three methods take an **unannotated** `category`
parameter and return bare `list` with `# type: ignore[type-arg]`:
`:110` (`get_resolved_purposes`), `:120` (`get_resolved_features`), `:186`
(`_resolve`). (A fourth, `_get_through_model` at `:175`, has no annotation and no
ignore — so the report's count of three is right but slightly under-inclusive.)

This is a clean `SPEC-DEVIATION` against *"Use static typing — type hints required
everywhere"* (`python-code-standards.md:10`) and against *"Use Pydantic for all
data models"* (`:12`), and the four `type: ignore[type-arg]` suppressions are the
only ones of this kind in production code — they are in production files, so they
are **not** the phase-01 `ENT-004` test-file typecheck debt. Keep.

---

### CQ-013 — [LOW] — Consent cookie names duplicated as literals

**Verdict: CONFIRMED.** `consent.py:51-54` defines four `CONSENT_*` constants;
`users/context_processors.py` reads all four as raw strings at `:54`, `:86`,
`:87`, `:96`; `search/views/preferred_city.py:90` reads `"consent_preferences"`
raw. A rename would silently break anonymous consent state.

**One correction to the fix, not the finding.** The report says *"No shared
constants module for cookie names or max-ages exists."* A **pattern** does exist:
`preferred_city.py:17-18` imports `PREFERRED_CITY_COOKIE_MAX_AGE` /
`PREFERRED_CITY_COOKIE_NAME` from `apps.core.middleware.preferred_city`, and
`consent.py:33` imports `PREFERRED_CITY_COOKIE_NAME` from the same place to delete
the cookie on withdrawal. So the remedy is to expose the four `CONSENT_*` names
alongside the existing cookie constants — **a relocation, not a new module.** This
removes one item from the new-abstraction count. `DOC-UPDATE` by type.

---

### CQ-014 — [MEDIUM] — `/alerts` promises a toggle no handler serves

**Verdict: CONFIRMED.** `alerts.py:88` appends
`_("\nReply with number to toggle, or /cancel to exit.")`. `alerts.py` (read in
full, 265 lines) registers exactly three entry points: `@router.message(Command("alerts"))`
at `:33`, `@router.callback_query(F.data.startswith(UNSUB))` at `:107`, and
`UNSUB_ON` at `:147`. There is **no** numeric-reply handler and no
`/cancel`-in-`alerts` handler. `SavedSearchState` (`states.py:26-34`, 5 members)
has **zero** occurrences anywhere outside its own definition.

This is a user-facing dead-end: a seller who follows the instruction types a
number and the bot falls through to the unhandled-message path. MEDIUM is right —
it is a shipped-but-dead UI contract, not a style issue.

---

### CQ-015 — [MEDIUM] — `listings.py` / `search.py` duplicate query + context build

**Verdict: ADJUSTED — corrected and strengthened.**

**`ListingsQueryParams`: confirmed.** `search.py:102-113` and
`listings.py:246-253` both build the DTO with the same **11** keyword arguments
mapped 1:1 from the same `request.GET` expressions. The only difference is
cosmetic: `search.py` hoists the `request.GET.get(...)` calls into locals first
(`:97-101`); `listings.py` inlines them.

**The context claim is wrong, and understating it weakens the finding.**
The report says "~15 keys". Actual:

- `search.py:196-224` — **26** keys.
- `listings.py:264-272` — **20** keys.
- **Shared: 20 keys — i.e. 100% of `listings.py`'s context.**

Both render the *same two templates* (`ads/list.html` and
`ads/partials/ad_list.html` — confirmed at `search.py:227-229` and
`listings.py:263`). So the two contexts are not merely similar, they are one
template contract expressed twice, with `listings.py` holding a strict subset.
A shared `build_listings_context()` is a one-function extraction that removes
the entire 20-key duplication. That is exactly the kind of "extract a function"
change the project rule does *not* require an architecture case for.

*(Side observation, not filed: both blocks are written at ~4 statements per line
— `listings.py:247-252` and `264-272`. That is a readability deviation from the
file's own convention, but no project rule names it.)*

---

### CQ-016 — [LOW] — Dead code

**Verdict: CONFIRMED, and under-counted.**

Whole-corpus reference counting (src + docs + templates + .ai) confirms exactly
**one** occurrence — the definition itself — for every named symbol:

| Symbol | Definition | Other production references |
|---|---|---|
| `is_consent_given` | `users/views/consent.py:278` | **0** |
| `get_resolved_purpose_codes` | `categories/services/lookup_resolution.py:130` | **0** |
| `get_resolved_condition_codes` | `categories/services/lookup_resolution.py` | **0** |
| `invalidate_group` | `lookups/services/cache_service.py` | **0** |
| `SavedSearchState` | `telegram_bot/states.py:26` | **0** |
| `CategoryRejectReason` | `core/enums.py:167` | **0** (only `__all__` + re-export + docs) |

**Three additional symbols the report missed**, each also single-occurrence:
`RESOLVED_PURPOSES_PREFIX`, `RESOLVED_FEATURES_PREFIX`,
`RESOLVED_CONDITIONS_PREFIX` in `lookup_resolution.py` — superseded by the
`*_SEGMENT` names still in use.

`apps/api/` verified: contains `serializers/` and `views/`, both empty, and no
`__init__.py`. **Zero files.**

**Correctly NOT re-filed:** `can_publish_ad`. It is owned by phase 15 as
**AUTHZ-005**, whose validator *rejected* the dead-code label (the behaviour is
specified in `technical-specification.md:101`, making it a missing integration /
`SPEC-DEVIATION`) and confirmed `can_publish_ad(declined)=True`. Phase 10's report
correctly omits it. Note it is *test-referenced* (13 occurrences in
`test_account_state.py`), so it is not strictly dead — consistent with phase 15's
verdict.

---

### CQ-017 — [LOW] — Packaging / enum hygiene

**Verdict: CONFIRMED — all three sub-claims verbatim.**

1. `apps/ads/services/` contains `copy_service.py`, `favorites.py`, `images.py`,
   `listings_query.py`, `submission.py` and **no `__init__.py`** — an implicit
   namespace package while every sibling ships one. (It works: Python 3 implicit
   namespace packages, and it is already on `PYTHONPATH`. Purely inconsistent.)
2. `telegram_bot/services/ad_data/orm.py:21-30` declares `__all__` and line 23 is
   `"_get_ad_status"` — a leading-underscore private name in an explicit public
   export list. `_get_ad_status` is live (re-exported at `ad_data/__init__.py`,
   imported by `handlers/ad_create/entry.py`), so this is a naming/export-list
   contradiction, not dead code.
3. `core/enums.py:23-43` `AdvisoryLockId` — verbatim order verified:
   `1…9`, then `100…104`, then **`PURGE_DELETED_ADS = 11`**,
   **`RECOMPUTE_NORMALIZED_PRICES = 12`**, then `110`, `111`. (Minor: the report
   says "1-8" for the first band; there are **nine** members, `ALERT_DELIVERY_TASK = 9`.)

**Rollout note.** Moving `admin_actions.py` under `services/` (CQ-010) updates
three importers: `apps/ads/admin.py:14`, `apps/moderation/views/api_bulk.py:16`,
`apps/moderation/views/review.py:69,96,135`. `apps/ads/admin.py` importing
`apps.moderation.admin_actions` is itself a layering inversion — an `ads` admin
depending on a moderation module — worth recording as an advisory.

---

### CQ-018 — [LOW] — `require_POST` inconsistency + hardcoded admin URLs

**Verdict: ADJUSTED — two counts wrong; substance confirmed.**

**Confirmed exactly:** 9 inline `request.method` checks —
`cabinet/views/saved_searches.py:44,63,93`; `cabinet/views/search_history.py:42`;
`core/views.py:156`; `moderation/views/decorators.py:55`;
`moderation/views/review.py:98,137`; `search/views/save_search.py:34`.
Also confirmed: `require_http_methods` is used **zero** times in the codebase.

**Count 1 wrong.** `@require_POST` is applied at **11 sites in 7 modules**, not
"6 views": `ads/views/delete.py:26`, `ads/views/edit.py:268` and `:305`,
`ads/views/favorite.py:27`, `moderation/views/review.py:51`,
`search/views/preferred_city.py:25`, `users/views/consent.py:125,182,236,379`,
`users/views/logout.py:15`.

**Count 2 wrong / incomplete.** There are **6** hardcoded `/admin/` URLs, not 5.
`review.py:81,99,120,138,153` are all confirmed — plus
`analytics/moderation_dashboard.html:34`, which the report files under CQ-005
instead. That template site cannot be fixed with `reverse()` in the view; it needs
a context-provided URL or a template tag. Both halves of the finding ("one
canonical decorator" + "use `reverse()`") are sound; the URL half is incomplete.

---

### CQ-019 — [LOW] — Comment density

**Verdict: ADJUSTED — measured count corrected 1,474 → 1,387.**

Tokenizing all production Python (tests and migrations excluded): **1,387**
comment-only lines out of **27,275** total lines = **5.1%**. The report's figure
is 6.3% high, most likely because it included a wider file set.

The rule is real — `python-code-standards.md:19` (*"Comment only non-trivial
logic; avoid obvious or redundant comments"*) — and `cache.py` (CQ-007) is the
clearest instance. But a 5.1% overall comment density across a codebase whose
comments are predominantly non-obvious design rationale (row-lock rationale,
PgBouncer async safety, consent-cookie attribute semantics, FTS cache
decoupling) is **not** a defect. The worst site is `edit.py:124`, which
reintroduces a `QLT-004` note **inside the `AdEditInput` docstring** — that
observation is valid and is carried forward as an advisory, not as part of this
finding.

---

## Refuted Evidence (sub-claims)

Kept here so the original report can be corrected rather than deleted.

| Sub-claim | Finding | Status |
|---|---|---|
| "Django adds `CHECK (min_price >= 0)` → `IntegrityError` → HTTP 500" | CQ-004 | **REFUTED** — `PositiveIntegerField` has no DB constraint; no `CheckConstraint` in the app's migrations; `-1` is silently persisted. |
| "`telegram_bot/services/` has no `__init__.py` contract" | CQ-002 | **REFUTED** — `src/telegram_bot/services/__init__.py` exists. |
| "a cache-key change must be applied in 12 places" | CQ-007 | **REFUTED** — each key is a `Final` constant used as a default argument; a key change is a one-line edit. |
| "no `logger` at all, unlike every other module in `apps/core/utils/`" | CQ-007 | **REFUTED** — 3 of the 7 sibling modules have no logger. |
| "Eleven sites" / "8 literals in 3 templates" | CQ-005 | **CORRECTED** — 7 template lines + 2 Python lines = 9. |
| "81 deferred imports"; "~14 are legitimate" vs "~26 are legitimate" | CQ-010 | **CORRECTED** — 92 imports; the report's own two counts disagree. |
| "1,474 comment-only lines" | CQ-019 | **CORRECTED** — 1,387 (5.1% of 27,275). |
| "6 views use `@require_POST`" | CQ-018 | **CORRECTED** — 11 applications in 7 modules. |
| "5 hardcoded `/admin/` URLs" | CQ-018 | **CORRECTED** — 6 (one is in a template). |
| "a ~15-key template context" | CQ-015 | **CORRECTED** — 20 shared keys; `listings.py`'s context is a strict subset of `search.py`'s. |
| "734 functions" | report-wide | **CORRECTED** — 713 under the validator's scope definition; the 13 (">100") and 54 (">60") figures match exactly, so the headline claims are unaffected. |
| "four-way `AdStatus` FSM branching" | CQ-001 | **CORRECTED** — three status branches plus one field-driven sub-branch. |
| "contact.py / support.py defer `apps.*` because of a missing service" | CQ-002 | **PARTLY REFUTED** — `alerts.py:22` imports `apps.search.models` at module level, so there is no import-time constraint; the deferral is inconsistent, not necessary. |

---

## Cross-Phase Reconciliation

### §A — CQ-001 collides with AUTHZ-002 / AUTHZ-007 on the same lines

**This is the most important section in this report.**

**Verified facts.**

| Fact | Location | Verified |
|---|---|---|
| `ad_edit` reads the row unlocked, then checks ownership | `edit.py:91` (`get_object_or_404(Ad, id=ad_id)`), `:94-101` | ✅ |
| `ad_edit` re-reads the row for POST | `edit.py:117` (`Ad.objects.select_for_update()`) | ✅ — note this read **is** locked; phase 15's "unlocked row" wording is imprecise, but the TOCTOU structure (check on snapshot A, mutate snapshot B) is real |
| Both `SubmitAdInput` blocks pass the ad's **own owner** as the actor | `edit.py:170` and `:213` — `user_id=ad.user_id` | ✅ byte-identical |
| `SubmitAdInput.user_id` is declared but **never read** | `submission.py:54` is the only occurrence in the file | ✅ |
| Phase 15's validator already recorded the tautology | `99-validation/15-authorization-validated-findings.md:45` — *"the recommended guard is a **tautology** for the web caller"*; test gap at `:935` requires *"**the web caller now passes `request.user.id`, asserted explicitly**"* | ✅ |
| The correct fix pattern already exists twice in the same file | `edit.py:284` (locked fetch) → `:287` (`if ad.user_id != request.user.id: return HttpResponseForbidden`) in `ad_archive`; and `:322` → `:327` in `ad_reactivate` | ✅ |
| CQ-001's recommendation touches those exact lines | "Hoist the duplicated `SubmitAdInput` construction into one local `command` variable used by both branches" | ✅ — `:170` and `:213` **are** the two duplicated blocks |

**The collision.** Three remediations land on `edit.py:91-117` and
`edit.py:160-216`:

1. **AUTHZ-007** (phase 15, MEDIUM) — move the ownership assertion inside
   `transaction.atomic()` and re-check on the locked instance, using the pattern
   already present at `:284-287`.
2. **AUTHZ-002** (phase 15, HIGH) — add `if ad.user_id != input.user_id: return
   False, [...]` inside `submit_ad`'s transaction (`submission.py:171-174`).
3. **CQ-001 / CQ-008** (this phase) — extract `ad_edit` into
   `apps/ads/services/edit_ad.py` and hoist the duplicated `SubmitAdInput` build.

**If they are applied independently, one silently reverts the other.**

- **CQ-001 first, then AUTHZ-007** → the TOCTOU check is relocated into a new
  module and AUTHZ-007's instruction ("add the check after line 117") points at
  code that no longer exists. The window survives the refactor, unfixed.
- **CQ-001 first with `user_id=ad.user_id` copied verbatim** → AUTHZ-002's guard
  becomes permanently tautological on the web path *and* is now used by both
  branches, so it looks load-bearing. Phase 15's AUTHZ-002 regression test
  ("the web caller now passes `request.user.id`, asserted explicitly") is the
  only thing that would catch it.
- **AUTHZ-002 first, then CQ-001** → same as above; the hoisted `command`
  variable would freeze the tautological value into one place.
- **CQ-008 first** (split `submit_ad` into orchestration helpers) → moves the
  `auto_moderate` delegation whose return value `ad_edit` branches on
  (`passed, errors` at `:174` / `:219`). Workable, but only in the same change set.

**Required ordering and scoping.**

> **AUTHZ-007 → AUTHZ-002 → CQ-001 → CQ-008, as ONE coordinated change set in
> `apps/ads/views/edit.py` + `apps/ads/services/submission.py` +
> `apps/ads/services/edit_ad.py`, reviewed by a single owner.**

Concretely, the CQ-001 implementation **must**:

1. Perform the ownership assertion on the locked instance inside the transaction,
   copying the existing `ad_archive`/`ad_reactivate` shape at `:284-287`, so
   AUTHZ-007 is satisfied by construction rather than by a follow-up patch.
2. Build the hoisted `SubmitAdInput` with `user_id=request.user.id` — **never**
   `ad.user_id` — so AUTHZ-002's guard is meaningful, and add phase 15's
   explicit assertion that the web caller passes `request.user.id`.
3. Use the single authorized locked instance in the reactivation branch and both
   error branches (currently `:178`, `:194`, `:225` re-fetch unlocked).
4. Land CQ-008's `submit_ad` split in the same commit, so AUTHZ-002's guard is
   never relocated twice.

**Do not close CQ-001 until AUTHZ-007 is verified closed against the extracted
module.**

### §B — CQ-002 re-files ENT-005, and the severities disagree

**Yes — CQ-002's `login.py` half is a re-file of phase-01 `ENT-005`.**

| | Phase 01 `ENT-005` | Phase 10 `CQ-002` (login half) |
|---|---|---|
| File(s) | `consent.py:381`, `consent.py:298`, **`login.py:154`, `login.py:190`** | **`login.py:154`, `login.py:190`** (+ the new alerts/contact/support sites) |
| Mechanism cited | hand-written `UPDATE login_tokens … RETURNING` at `login.py:169` | identical, at `login.py:169-187` |
| Auditor severity | HIGH | HIGH |
| **Validated severity** | **MEDIUM, reclassified `BEST-PRACTICE`** | — |
| Phase-04 verdict on the mechanism | *"the bot's single-statement claim … is sound"* (zero-TOCTOU) | not addressed |
| Recommended fix | extract `apps/users/services/login_token.py` | create `telegram_bot/services/login.py` |

**The severities disagree: CQ-002 says HIGH, ENT-005 was validated to MEDIUM.**

The already-validated verdict governs. Phase 01's validator downgraded ENT-005
precisely on grounds that phase 10 re-opens: it found ENT-005's stated root cause
(*"There is no `apps.users.services` counterpart"*) **factually false** — the
services layer exists in 13/13 apps — and held that the value of the finding is a
missing *service owner* plus an oversized view module, not a defect. Phase 04
independently rated the `UPDATE … RETURNING` claim as sound and zero-TOCTOU.

**Merge instruction.** Merge the `login.py` half of CQ-002 into `ENT-005`
(tracker `15-ent-ENT-005`, P1, already recorded as phase 01's advisory
recommendation #5). Keep CQ-002 only for `alerts.py`, `contact.py` and
`support.py`, at **MEDIUM**. Do not ship the login extraction twice.

**Target correction — this matters architecturally.** CQ-002 proposes
`telegram_bot/services/login.py`; ENT-005's validated fix is
`apps/users/services/login_token.py`. **ENT-005's location is correct.** The
login token is a *cross-process* protocol: the web view issues it, the bot claims
it, the web consumes it. Putting the claim in `telegram_bot/` would keep the
protocol split across two packages and re-create the problem the extraction
exists to solve. CQ-002's other three modules (`alerts`, `contact`, `support`)
are bot-local and belong in `telegram_bot/services/` where proposed.

### §C — Other cross-phase relationships

| Pair | Relationship | Disposition |
|---|---|---|
| CQ-014 (`SavedSearchState` dead) ↔ ENT-005 (bot entry-layer clean-up) | Same file neighbourhood, same class of bot-side dead code | **Soft.** Different symbols; retained and cross-referenced. |
| CQ-016 (dead code) ↔ **AUTHZ-005** (`can_publish_ad`) | Phase 15 explicitly *rejected* the dead-code label for it | **Not re-filed.** CQ-016 correctly omits it; phase 10 must not revive it. |
| CQ-012 (4 × `type: ignore[type-arg]`) ↔ **ENT-004** (CI typecheck scope) | ENT-004 owns the *gate*; phase 10 owns production-file suppressions | **Not a duplicate.** These are in production code, outside ENT-004's test-file set. Note ENT-004 must land first or the bot-side work is unverified. |
| CQ-004 (`_int_or_none`) ↔ phase 08 (`_coerce_int_or_none`) | Phase 08 cites a *different* symbol — the Pydantic validator in `listings_query.py:65` | **Not a duplicate.** Different function, different file, different mechanism. |
| CQ-002/CQ-010 (deferred `apps.*` in `contact.py`, `support.py`) ↔ phase 04 `AUT-003` | Both touch bot/web rate-limit code paths | **Not a duplicate.** AUT-003's `_get_client_ip` item is already resolved into three `services/` modules; the phase-10 observation is that the deferral itself is unnecessary. |
| CQ-017 (`apps/ads/admin.py:14` importing `apps.moderation.admin_actions`) ↔ phase 09 | Phase 09 owns the external API surface | **Advisory only.** Flagged, not filed. |

### §D — Pre-existing conditions respected

Per the brief, none of the following was re-filed: the CI `lint`/`typecheck`
scope gap and red gate (**ENT-004**); the `apps/*/services/` layer (exists,
13/13); `_get_client_ip` (already refactored into three `services/` modules by
phase 04 — the phase-04 file list is stale but the code is clean);
`CONN_MAX_AGE=0` + per-update `close()` (documented intentional design —
`base.py:260`, `apps/core/db/connection.py:1-16`); `consent.py`'s ~470 lines
(owned by **ENT-005**); `apps/ads/services/copy_service.py` (phase 15 confirmed
six passing tests + a shipped `/copy` route, so no media-layer abstraction is
proposed here).

---

## Findings Requiring Architectural or Structural Change

Per the task brief, only findings that genuinely need more than "extract a
function" or "delete dead code".

**Genuinely structural (4):**

| ID | What must change structurally |
|---|---|
| **CQ-001** (+ CQ-008) | `ad_edit`'s four responsibilities (auth, lock, currency rule, FSM, ORM writes) must cross a layer boundary into `apps/ads/services/`. This is the only finding that moves code between the UI and business layers. **Must be sequenced with AUTHZ-002/AUTHZ-007** (§A). |
| **CQ-002** (alerts/contact/support half) | Bot data access must move out of `handlers/` into `telegram_bot/services/`. A layer boundary, not a refactor. |
| **CQ-011** | Fuzzy category resolution must become one shared module used by both browse and search, with one ladder. |
| **CQ-004** | POST parsing must be centralised at a Pydantic boundary (`SavedSearchInput`) rather than hand-rolled per view. |

**One structural change that is a *move*, not an abstraction (1):**

| **CQ-010** | `admin_actions.py` → `apps/moderation/services/admin_actions.py`. Zero new names; deletes 3 deferred imports as a side effect. Highest value-per-diff in the report. |

**Everything else (14) is one of:** a typed DTO replacing a bare `dict`
(CQ-003, CQ-009, CQ-012), a constant/enum substitution at an existing site
(CQ-005, CQ-006), a single-function extraction of duplicated logic (CQ-015),
a file/dir hygiene fix (CQ-013, CQ-017, CQ-018), a deletion (CQ-016), or a
documentation trim (CQ-007, CQ-019).

---

## New-Abstraction Count and Proportionality

### Gross (as filed)

| # | Finding | Proposed new artifact | Kind |
|---|---|---|---|
| 1 | CQ-001 | `apps/ads/services/edit_ad.py::edit_ad` | module + function |
| 2 | CQ-001 | `ErrorPage` enum | enum (**reject**) |
| 3 | CQ-001 | `_build_submit_input` helper | function (**reject**) |
| 4 | CQ-002 | `telegram_bot/services/{login,alerts,contact,support}.py` | 4 modules (1 wrong location, merged) |
| 5 | CQ-002 | AST architecture test for `handlers/` | test (**reject**) |
| 6 | CQ-004 | `SavedSearchInput`, `PreferredCityInput` | 2 DTO classes |
| 7 | CQ-004 | `apps/search/schemas.py` | module (may not exist) |
| 8 | CQ-004 | AST architecture test for POST views | test (**reject**) |
| 9 | CQ-006 | `apps/core/services/locales.py` | module (**reject**) |
| 10 | CQ-007 | `CacheEntry` + 5 modules | class + 5 modules (**reject all**) |
| 11 | CQ-008 | `submit_ad` split (dedup with #1) | — (dedup) |
| 12 | CQ-010 | `scripts/lint_no_deferred_imports.py` | script (**reject**) |
| 13 | CQ-011 | `apps/categories/services/fuzzy.py` | module |
| 14 | CQ-012 | `PriorityScore` model + `PriorityFlags(StrEnum)` | 2 classes |
| 15 | CQ-015 | `build_listings_context()` | function |
| 16 | CQ-003 | template context processor | wiring (not an abstraction) |

**Gross total: 16 artifacts** across 19 findings.

### Net (after this validation's rejections, merges and de-duplication)

| Kept | Kind |
|---|---|
| `apps/ads/services/edit_ad.py::edit_ad` (CQ-001 + CQ-008, merged) | module + function |
| `telegram_bot/services/{alerts,contact,support}.py` (CQ-002; login → ENT-005) | 3 modules |
| `SavedSearchInput`, `PreferredCityInput` (CQ-004) | 2 DTO classes |
| `apps/categories/services/fuzzy.py` (CQ-011) | module |
| `PriorityScore`, `PriorityFlags` (CQ-012) | 2 classes |
| `build_listings_context()` (CQ-015) | function |
| `admin_actions.py` → `services/` (CQ-010) | **file move, 0 new abstractions** |

### **Net new abstractions: 10** (3 modules + 2 module-owned functions + 2 DTO
classes + 2 enum/model classes + 1 function), plus **1 file move**.

### Proportionality judgement: **PROPORTIONATE.**

Against 27,275 lines / 713 production functions and 13 MEDIUM + 6 LOW findings
(19 total), 10 new named artifacts is roughly **one artifact per two findings** —
and every one is one of four cheap kinds:

1. **Extraction of duplicated logic** (`fuzzy.py`, `build_listings_context`,
   `edit_ad`) — this is the category the project rule explicitly does *not*
   require an architecture case for.
2. **A typed DTO replacing a bare `dict`** at a boundary the rules already
   mandate (`PriorityScore`, `SavedSearchInput`).
3. **A module split along an existing package boundary** (`telegram_bot/services/`)
   where a precedent module (`ad_data/orm.py`) already exists.
4. **A file move** with no new name at all (CQ-010).

**Zero** findings propose a new architectural layer, a base class, a manager
class, a plugin/registry pattern, a generic framework, or a new cross-cutting
mechanism. Nothing here creates a dependency inversion or a service locator.

**Rejected as disproportionate (6 artifacts):** `ErrorPage`, `_build_submit_input`,
`CacheEntry` + 5 cache modules, `apps/core/services/locales.py`,
`scripts/lint_no_deferred_imports.py`, and 2 of the 3 proposed AST architecture
tests. Each either wraps something that already exists (`LanguageLocale`,
`django.core.cache`, `ruff`'s `PLC0415`) or encodes a rule that must first be
made true before it can be enforced (the two AST tests would fail on ~26
legitimate deferrals and on `request.POST` + `save()` in
`moderation/views/review.py`'s delegate pattern).

**Net verdict:** the report is *not* overengineered in aggregate. It is
over-specified at the margins — six of sixteen artifacts are unnecessary. That
is a proportionality **trim**, not a structural objection.

---

## Rollout Analysis

| ID | Risk | Backward-compatible? | Ordering constraint / must-cover test gap |
|---|---|---|---|
| CQ-001 | **High** — collides with two live security remediations on the same lines | Yes | **Do not start until AUTHZ-007 is closed.** Owner edit GET renders 200 and POST saves; non-owner GET and POST both 403; the DB-003 row lock is still taken; the reactivation and both error branches use the authorized locked row. **And: the web caller must pass `request.user.id`** (AUTHZ-002 test gap). See §A. |
| CQ-008 | **High** — same change set as CQ-001 | Yes | Lands in the same commit; `submit_ad` with a mismatched `user_id` leaves the row byte-identical and returns `(False, [...])`; the bot `/post` → `process_preview` path still publishes. |
| CQ-002 | **High** — 3 module extractions in the bot process, which is **outside the CI lint/typecheck scope** (ENT-004) | Yes, if the handler signatures are kept as re-exports | **ENT-004 must land first.** All bot answers byte-identical before/after. The login half is merged into ENT-005 and must not be built here. |
| CQ-004 | Medium — negative prices become a validation error instead of a silent write | Yes (positive values unchanged) | Owner POST with `min_price=-1` now returns a form error, not a 500 and not a silent `-1`. Three call sites keep working; `preferred_city` cookie behaviour byte-identical. |
| CQ-009 | Medium — a malformed POST now 400s instead of blanking the ad | No (error path only) | A POST omitting `title` is rejected; a POST with an empty `title` still saves (deliberate — the clear-vs-blank ambiguity is a separate decision, flagged in the DTO docstring at `:82-84`). |
| CQ-011 | Medium — a fuzzy suggestion may change for borderline slugs | Yes | Exact slug match on `/` still returns the correct category (it currently does not). `/search/` results unchanged for queries that already matched exactly. |
| CQ-015 | Low — one context builder replaces two | Yes | `ads/list.html` and `ads/partials/ad_list.html` render with an identical key set on both `/` and `/search/`; the 6 search-only keys stay search-only. |
| CQ-003 | Low | Yes | Every one of the 8 reject reasons still persists; the template renders from the enum, not from hardcoded `<option>`s. |
| CQ-006 | Low | Yes | `ru`/`bs`/`en` values unchanged everywhere; the FTS config and vector-field names are asserted in a test so the in-place enum edit cannot silently drift. |
| CQ-005 | Low | Yes | Every affected template renders identically; a smoke test over `ads/dashboard.html`, `admin/moderation/review.html` and `analytics/moderation_dashboard.html`. |
| CQ-010 | Low | Yes | `ruff check` stays clean; `PLC0415` enabled **with** an exclusion list for `AppConfig.ready()`, CLI/bootstrap and signal modules, otherwise the new gate fires ~26 times on legitimate deferrals. `apps/moderation/{apps,admin}.py` untouched by the move. |
| CQ-017 | Low | Yes | The `admin_actions.py` move updates 3 importers in one commit (`apps/ads/admin.py:14`, `apps/moderation/views/api_bulk.py:16`, `apps/moderation/views/review.py:69,96,135`); `.\Makefile.ps1 test` is the gate. |
| CQ-012 | Low | Yes | `PriorityScore` must serialize identically for `update_or_create` defaults; drop the 4 `type: ignore[type-arg]` in the same commit. |
| CQ-016 | Low | Yes | Delete-only; `.\Makefile.ps1 test` is the gate. |
| CQ-007 | Low | Yes | Documentation-only. |
| CQ-013 | Low | Yes | Cookie names/values unchanged; only the read sites change. |
| CQ-014 | Low | Yes | Implement the numeric toggle **or** correct the prompt — not both; delete `SavedSearchState` either way. |
| CQ-018 | Low | Yes | Every `@require_POST` site already returns 405 for non-POST, so the decorator swap is behaviour-preserving; the two inline redirect-on-GET branches in `review.py:98-99`/`137-138` **change** from a 302 to a 405 and must be verified against `admin/moderation/review.html`'s forms. |
| CQ-019 | Low | Yes | Documentation-only. |

**Rollback.** Every finding is a pure code change with no migration and no
schema touch. CQ-001/CQ-008 are the only ones where rollback interacts with a
security fix — reverting the refactor alone must not revert AUTHZ-002's guard or
AUTHZ-007's locked-row assertion.

---

## Audit-Input Defects

| ID | Sev | Detail |
|---|---|---|
| VAL-P10-01 | MEDIUM | **CQ-004's reproduction is factually wrong.** `PositiveIntegerField` creates no DB check constraint; the reproduction and Impact must be rewritten before they reach a tracker. |
| VAL-P10-02 | MEDIUM | **CQ-002 duplicates ENT-005 at a different severity.** Two completed validations (phase 01 → MEDIUM; phase 04 → mechanism sound) are contradicted by a fresh HIGH. |
| VAL-P10-03 | LOW | **Six arithmetic inconsistencies** in prose contradicted by the report's own evidence blocks: 11 vs 9 sites (CQ-005), 81 vs 92 imports (CQ-010), "~15" vs 20 shared context keys (CQ-015), "6 views" vs 11 applications (CQ-018), 5 vs 6 admin URLs (CQ-018), 1474 vs 1387 comment lines (CQ-019). |
| VAL-P10-04 | LOW | **CQ-002's stated root cause is false** — `telegram_bot/services/__init__.py` exists. |
| VAL-P10-05 | LOW | **CQ-007's logger claim is false** — 3 of 7 sibling modules have no logger. |
| VAL-P10-06 | LOW | **A site was missed twice**: `telegram_bot/handlers/ad_create/submit.py:65-70` (CQ-006) and `analytics/moderation_dashboard.html:34` as a hardcoded `/admin/` URL (CQ-018). |
| VAL-P10-07 | LOW | **The proposed `telegram_bot/services/login.py` contradicts ENT-005's validated `apps/users/services/login_token.py`** and would re-split a cross-process protocol. |

No file changed, no command with side effects was run.

---

## Validation Summary

| Action | Count | Details |
|-------|-------|---------|
| Validated (unchanged) | 8 | CQ-003, CQ-009, CQ-011, CQ-012, CQ-013, CQ-014, CQ-016, CQ-017 |
| Severity-adjusted | 11 | CQ-001, CQ-008 (HIGH→MEDIUM); CQ-002 (HIGH→MEDIUM + partial merge); CQ-007, CQ-010 (MEDIUM→LOW); CQ-004, CQ-005, CQ-006, CQ-015, CQ-018, CQ-019 (evidence corrected, severity held) |
| Merged | 1 partial | CQ-002 `login.py` half → ENT-005 |
| Rejected | 0 whole findings | 7 sub-claims rejected outright; 13 sub-claims corrected |
| Downstream blocks | — | **CQ-001 blocked on AUTHZ-007; CQ-002 blocked on ENT-004** |

### Rejected Findings

None. No finding was stale, already-implemented, or wholly duplicative. Every
one describes code that exists in the working tree.

### Reclassified Findings

| ID | Original | New | Rationale |
|---|---|---|---|
| CQ-001 | untyped (implied structural) | `BEST-PRACTICE` + MEDIUM | Maintainability rule with no demonstrated defect; same precedent as phase 01's `ENT-005` downgrade. |
| CQ-002 | untyped | `BEST-PRACTICE` + MEDIUM | Same class; login half merges into ENT-005. |
| CQ-004 | untyped | `BEST-PRACTICE` + MEDIUM | Boundary-validation gap is real; the 500-impact framing was wrong and the fix is not urgent-breaking. |
| CQ-003, CQ-005, CQ-006, CQ-009, CQ-011, CQ-012, CQ-017 | untyped | `SPEC-DEVIATION` | Each cites an explicit rule in `python-code-standards.md` and the violating code. |
| CQ-013, CQ-018, CQ-019 | untyped | `DOC-UPDATE` | Correctness-adjacent cleanups with no explicit rule violation; CQ-013's fix is a constant relocation, CQ-019 is comment density. |

### Severity-adjusted Findings

| ID | From | To | Rationale |
|---|---|---|---|
| CQ-001 | HIGH | MEDIUM | 193 lines is the largest function in the repo, but it is a maintainability metric; no defect, no rule violation with runtime consequence. Must be sequenced with AUTHZ-002/AUTHZ-007. |
| CQ-002 | HIGH | MEDIUM | Half of it duplicates ENT-005 (already MEDIUM); the other half is a layering inconsistency with no defect. |
| CQ-008 | HIGH | MEDIUM | 124 lines, six responsibilities, no defect; same precedent. |
| CQ-007 | MEDIUM | LOW | The claimed impact ("12 places") is false — keys are already single-sourced; the proposed `CacheEntry` is pure indirection. Residual is a docstring trim. |
| CQ-010 | MEDIUM | LOW | 92 deferrals, the majority legitimate (`AppConfig.ready()`, bootstrap, model load); the one real cluster is a file move. |

### Required Fixes (mandatory)

1. **CQ-001 / CQ-008 —** one coordinated change set with AUTHZ-007 and AUTHZ-002
   (§A). Move the ownership assertion onto the locked instance using the
   `ad_archive` pattern at `edit.py:284-287`; build the hoisted `SubmitAdInput`
   with `user_id=request.user.id`, **not** `ad.user_id`. Do not close before
   AUTHZ-007 is verified closed against the extracted module.
2. **CQ-002 —** build only `telegram_bot/services/{alerts,contact,support}.py`.
   Merge the `login.py` half into ENT-005 and use ENT-005's
   `apps/users/services/login_token.py` target. ENT-004 (CI scope) first.
3. **CQ-003 —** expose `CategoryRejectReason` to `review.html`, delete the 8
   hardcoded `<option>` values, validate `reason_category` at the boundary.
4. **CQ-009 —** make `AdEditInput.title`/`.description` required with
   `min_length=1`.
5. **CQ-004 —** add `SavedSearchInput(BaseInputModel)` with `ge=0` price bounds;
   delete both `_int_or_none` closures. **Rewrite the reproduction first** — the
   current one is wrong and would send a fix after a bug that does not exist.
6. **CQ-011 —** single `apps/categories/services/fuzzy.py` with a 3-tier ladder
   and one cutoff.
7. **CQ-014 —** implement the numeric toggle **or** correct the `/alerts` prompt;
   delete `SavedSearchState` either way.
8. **CQ-010 —** move `admin_actions.py` → `apps/moderation/services/admin_actions.py`
   in one commit (3 importers); enable `ruff` `PLC0415` **with** an exclusion
   list. Do **not** add a custom lint script.
9. **CQ-016 —** delete the 6 dead symbols plus the 3 unused `RESOLVED_*_PREFIX`
   constants and the empty `apps/api/` tree.
10. **CQ-012 —** add `PriorityScore` + `PriorityFlags(StrEnum)`; annotate
    `CategoryLookupResolver`; drop the 4 `type: ignore[type-arg]` in the same
    commit.
11. **CQ-005 / CQ-006 —** replace literals with `AdStatus` / `LanguageLocale`
    in place, including `telegram_bot/handlers/ad_create/submit.py:65-70`. **Do
    not** add `apps/core/services/locales.py`. Correct the false invariant claim
    at `enums.py:5`.
12. **CQ-015 —** one `build_listings_context()`; assert both views render the same
    20-key contract.
13. **CQ-013 / CQ-017 / CQ-018 —** relocate the `CONSENT_*` names beside the
    existing `PREFERRED_CITY_COOKIE_*`; add `apps/ads/services/__init__.py`;
    remove `"_get_ad_status"` from `orm.py`'s `__all__`; reorder `AdvisoryLockId`;
    standardise on `@require_POST` and `reverse()` (including the template URL).
14. **CQ-007 / CQ-019 —** trim redundant docstrings and comment density.

### Advisory Recommendations

- **CQ-001 —** the extracted `edit_ad` should return the existing
  `HttpResponseForbidden` / `HttpResponse(status=400)` directly. **No `ErrorPage`
  enum.**
- **CQ-010 —** `apps/ads/admin.py:14` importing `apps.moderation.admin_actions` is
  a layering inversion (an `ads` admin depending on moderation internals). Fold
  it into the `admin_actions.py` move or record it separately.
- **CQ-016 —** `can_publish_ad` is **owned by phase 15 as AUTHZ-005**, whose
  validator rejected the dead-code label (the behaviour is specified in
  `technical-specification.md:101`, making it a missing integration). Phase 10
  must not revive it as dead code.
- **CQ-012 —** the 4 `type: ignore[type-arg]` are the only such suppressions in
  production code and are a direct consequence of the untyped `category`
  parameters. Fixing them is also what makes ENT-004's widened gate meaningful.
- **CQ-019 —** `edit.py:124` re-introduces a `QLT-004` provenance note **inside
  the `AdEditInput` docstring**. Not filed here; consider folding it into the
  finding the note actually belongs to.
- **CQ-006 —** the `fts_config` / `fts_vector_field` raw dicts live *inside*
  `LanguageLocale` itself. Fixing them there removes 6 of the 16 literals.
- **Entire report —** the `QLT-###` provenance tags hard-coded in
  `ads/views/edit.py:124`, `apps/media/schemas.py:7` and
  `ad_create/submit.py:4` must be reconciled with the `CQ-###` IDs. Two
  vocabularies for the same report is a documentation defect in its own right.

---

## Validation Method & Reproducibility

All checks were static: an AST + tokenizer census over `src/backend` and
`src/telegram_bot` (production Python only — tests, `conftest.py` and
`migrations/` excluded); whole-corpus symbol reference counting across `src`,
`docs`, `templates` and `.ai`; direct reads of every cited file; Django source
inspection (`inspect.getsource`) for the CQ-004 reproduction; and cross-phase
reads of `.ai/audit/99-validation/{01-entry-architecture,04-auth-login,15-authorization}-validated-findings.md`.

**No test suite was run.** `.\Makefile.ps1 test` was not invoked: the audit is
read-only, no finding depends on runtime behaviour, and the `mko-bazuna-dev`
web/bot containers are crash-looping. The one reproduction that needed a live
database (`CQ-004`'s `IntegrityError`) was refuted by reading Django's field
source and the app's migrations instead — a stronger form of evidence than a
transient test run.

**No code, test, configuration, or documentation file was modified.** One
read-only probe script was written to `.ai/tmp/` and deleted before completion.
No container was started.

## Related Findings

- `ENT-004` (phase 01) — CI lint/typecheck scope excludes the bot process;
  gates CQ-002.
- `ENT-005` (phase 01, MEDIUM / `BEST-PRACTICE`) — two-phase login-claim
  protocol; **CQ-002's `login.py` half merges here.**
- `AUTHZ-002` (phase 15, HIGH) — `submit_ad` ignores `user_id`; **collides with
  CQ-001/CQ-008 at `edit.py:170,213` and `submission.py:171-174`.**
- `AUTHZ-007` (phase 15, MEDIUM) — `ad_edit` authorizes on an unlocked read;
  **blocks CQ-001 (§A).**
- `AUTHZ-005` (phase 15, MEDIUM) — `can_publish_ad`; **not re-filed by CQ-016.**
- `DB-001` (phase 03, CRITICAL) — `create_draft_ad` savepoint; `telegram_bot/services/ad_data/orm.py`
  is CQ-002's precedent module, not its subject.
- `API-009` / `API-010` (phase 09) — bot rate-limit and contact paths overlapping
  CQ-002's `contact.py` half; different mechanisms, cross-referenced only.
