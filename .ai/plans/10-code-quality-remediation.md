---
plan_id: "10-code-quality-remediation"
phase: "10"
phase_name: "Code Quality"
source_report: ".ai/audit/99-validation/10-code-quality-validated-findings.md"
date: "2026-09-29"
planner: "Planner (subagent)"
anchor_commit: "6413df5"
report_anchor_commit: "aa2a6b0"
status: "planned"
findings_in_scope: 19
findings_fully_open: 17
findings_partial: 1
findings_already_fixed: 1
findings_rejected: 0
blocks: 16
---

# Execution Plan — Phase 10 Remediation (Code Quality)

## 0. Header, provenance and scope statement

### 0.1 Provenance

| Item | Value |
|---|---|
| Source report | `.ai/audit/99-validation/10-code-quality-validated-findings.md` (validated, 1170 lines) — the **only** surviving phase-10 input |
| Source findings file | `.ai/audit/10-code-quality/findings.md` — **does not exist in the working tree** (verified). Recorded for traceability only; **not** an input, and **not** a problem to fix. No block may restore it |
| Report anchor commit | `aa2a6b0` (recorded in the report metadata) |
| Code-context document | `.ai/tmp/code-context-phase10.md` (684 lines, Auditor) |
| **Working anchor commit for this plan** | **`6413df5`** (`git rev-parse --short HEAD`, taken before writing) |
| Date | 2026-09-29 |
| Findings in scope | 19 (`CQ-001` … `CQ-019`) |
| State at the anchor | **17 still exist · 0 rejected · 0 fully resolved · 1 split (`CQ-002`: the login half is already shipped) · 6 with stale measurements** |
| Validated severity split | **0 CRITICAL · 0 HIGH · 12 MEDIUM · 7 LOW** |
| Static gates at the anchor | `uv run ruff check .` → **All checks passed!**; `uv run basedpyright src/` → **0 errors, 0 warnings, 0 notes** |
| Execution blocks | **16** — 8 `mechanical`, 8 `behavioural` (§2 carries the classification per finding) |
| Implementor concurrency | **1**, strictly sequential (project rule: one implementor at a time) |
| Migration | **none.** No block ships a schema change. `CQ-004` is boundary validation, not a model change |

**This phase's central job is serialisation, not redesign.** Phases 01–08 are already
planned and are editing the same modules; phases 11–15 are being planned in parallel right
now. Every block below is classified `mechanical` (safe to batch, low review cost) or
`behavioural` (needs individual review and its own test decision), and the serial order is
chosen so that **a symbol is owned by exactly one phase at a time** (§4, §5).

**Naming convention.** Every citation of this phase's own findings is cycle-scoped
**`10-CQ-0NN`**, never a bare `CQ-0NN`, wherever it must survive into a comment, a
docstring, a tracker entry or a commit message. A second, pre-existing vocabulary —
`QLT-###` tags in `apps/ads/views/edit.py`, `apps/media/schemas.py` and
`telegram_bot/handlers/ad_create/submit.py` — exists in the shipped source for the same
report. That collision is **Q11** and is routed to the coordinator; this plan writes no new
`QLT-` marker and does not sweep the existing ones (phase 03 BLOCK 11 reserves that sweep).

---

### 0.2 Evidence basis — read this before executing any block

The validated report is the narrative source; the Auditor's code context re-measured it
against the tree at `aa2a6b0`; this Planner re-verified the load-bearing claims against the
tree at `6413df5`. **The tree is the authority.** Where the report and the tree disagree,
the correction is here and the plan is built on the tree's answer.

#### 0.2.1 Corrections — the tree wins

| # | Claim | Report says | **Tree at `6413df5` says** (Planner-verified where marked ✔) | Consequence |
|---|---|---|---|---|
| **C-1** | `CQ-005`: "7 template lines + 2 Python lines = 9 sites" | 2 Python sites (`review.py:120,153`) | Those two lines are the **`/admin/` redirect URLs**, which the report files under `CQ-018` as well — a double count. ✔ A whole-tree grep for quoted status strings in production Python returns **zero** `AdStatus` literals; every Python site uses `AdStatus.X`. The real scope is **10 template lines / ~14 literal occurrences across 4 templates**, and `ads/edit.html` (archived-status banner) was missed entirely | `CQ-005` is **template-only, 0 Python sites**. The remedy is the existing `core/context_processors.py::price_step` pattern, **not** a Python enum reference and **not** a template-tag library. `DQ10` decides the mechanism |
| **C-2** | `CQ-011`: unify into `apps/categories/services/fuzzy.py` with a 3-tier ladder | new module under `categories` | ✔ **`apps/search/services/category_fuzzy.py` already exists** and owns `get_active_category_names`; `search.py` already imports it at module level. A `categories → search` edge would invert the existing `search → categories` graph. There are **three** fuzzy sites (the report found two) plus a fourth unfiled one: `search.py::_fuzzy_category_match` (3 tiers, `cutoff=0.8`), `search.py::_fuzzy_match_by_name` (`0.8`), `listings.py::_suggest_category` (`0.6`, no exact tier), `locations/services/city_suggestions.py::suggest_city` (`_CUTOFF = 0.6`, different entity). ✔ `test_search_fuzzy.py::TestFuzzyEquivalence` **re-computes `cutoff=0.8` inside the test** | The report's target is architecturally wrong. `Q1` (home), `Q6` (cutoff) and `Q7` (does `suggest_city` join) are **decision gates**, not implementation details. BLOCK 15 does not start until all three are written down |
| **C-3** | `CQ-002`: create `telegram_bot/services/{login,alerts,contact,support}.py` | 4 new modules | ✔ The **login half is already shipped**: `telegram_bot/handlers/login.py::_claim_login_token` is a four-line delegation to `apps.users.services.login_token.claim_token` (phase 01 `ENT-005`, executed exactly as the report's merge instruction demanded). ✔ `contact.py`'s deferred import is `from apps.core.services.contact import (...)` — an **existing** service, so that half is a hoist to module scope, not a new module. ✔ `support.py`'s three deferrals are two model imports and a nested `User` import | **Do not create `telegram_bot/services/login.py`.** Only the **`alerts`** half is a real extraction; `contact` is a one-line hoist and `support` is a two-line hoist. BLOCK 11 is correspondingly smaller than the report |
| **C-4** | `CQ-010`: 92 deferred imports; "enable `PLC0415` in CI" | a CI edit | ✔ **[tool.ruff.lint] select = `["E","F","I","B","UP","G"]` — there is no `PLC`.** Enabling `PLC0415` is a **`pyproject.toml`** edit, and it would fire on **96** sites today. ✔ `[tool.ruff] fix = false` is set ("do NOT auto-fix by default"), so a stray `ruff check --fix` in any block is a rule violation. ✔ `[tool.mypy]` carries `disallow_any_generics` but **basedpyright does not read it** and mypy is **not in CI** | BLOCK 13 is a `pyproject.toml` edit with a **mandatory** `per-file-ignores` list, split out of the file move (BLOCK 12) so a red-on-arrival gate is isolated in its own revertible commit. `CQ-012` is **unenforced by any gate** and must be described as a readability change, not a compliance fix |
| **C-5** | `CQ-018`: 9 inline `request.method` checks; 6 views use `@require_POST`; 5 hardcoded `/admin/` URLs | 9 / 6 / 5 | **10** inline comparisons — the tenth is `ad_edit`'s `if request.method == "GET":` **dispatch** branch, not a method guard, and it is inside the most contended function in the plan set. **11** `@require_POST` applications in 7 modules. **6** hardcoded `/admin/` URLs, one of them the CQ-005 template site. ✔ `test_reject_requires_post` ("GET to reject_ad redirects rather than rejecting") and `test_ban_requires_post` assert the **302**; their sibling `test_approve_requires_post` asserts **405** | The finding splits three ways: the **7** behaviour-preserving 405 guards (BLOCK 6, mechanical), the **2** review.py guards (BLOCK 7, **behavioural**, 302 → 405, `Q4`), and the URL half (BLOCK 5, shared with `CQ-005`). `ad_edit`'s dispatch branch is **BLOCK 16's**, not BLOCK 6's |
| **C-6** | `CQ-001`: collision surface is `AUTHZ-002` + `AUTHZ-007` | two phase-15 items | **Wider.** phase 03 **BLOCK 5** (`SET LOCAL lock_timeout` inside `ad_edit`), phase 05 **BLOCKs 2 / 8 / 12** and phase 07 **BLOCK 10** all edit `ad_edit`. ✔ `test_edit_views_locking.py::TestEditViewsLocking` asserts on `inspect.getsource(edit.ad_edit)` — `test_ad_edit_uses_select_for_update_and_atomic` (both tokens present) and `test_ad_edit_get_path_not_locked` (**`source.count("select_for_update") == 1`**, verified: `ad_edit` has exactly one, at the locked POST re-fetch; `ad_archive` and `ad_reactivate` are separate functions later in the same file). The report's §A item 3 also lists **three** unlocked re-fetch sites; the tree has **two** (the `passed is False` error branches) | **Any CQ-001 extraction turns three shipped tests red.** That is the detector, which is good — but only if the reordering is done knowingly. BLOCK 16 is one commit, one owner, four agents, and it lands **after** phase 03 BLOCK 5 and phase 05 BLOCKs 2/8 |
| **C-7** | `CQ-017.3`: reorder `AdvisoryLockId` (19 members, `1…9, 100…104, 11, 12, 110, 111`) | a cosmetic reorder | ✔ **`REPAIR_BOT_USERNAME = 13` exists** in the tree (concurrent phase-02 work). The report's table is stale by one member. `AdvisoryLockId` is an `IntEnum`; member order has **no** functional or serialisation effect | **De-scoped to §6.** The reorder would edit a file that phases 02/03/05/06/07 all list as contended, for zero behavioural gain. Phase 10 allocates **no** lock id and must not renumber the enum |
| **C-8** | Brief: plan `09-external-api-remediation.md` exists | phase 09 is a live cross-phase partner | ✔ **It was absent from `.ai/plans/` when this plan was written and appeared, untracked, while it was being written** — the same concurrent-agent drift the anchor rule exists for. It is now readable and is anchored at `6413df5` too | Phase 09 is a **real** partner, not an unverifiable one, and it creates two new reservations: **`telegram_bot/handlers/contact.py`** (a rate-limiter block editing `handle_contact` / `handle_contact_us_start`, which overlaps BLOCK 11's import hoist) and **`apps/core/utils/cache.py`** (`09-VAL-008` names it the shared home for a cache-failure contract, which overlaps BLOCK 2's docstring trim and BLOCK 9's two return types). Both are recorded in §5.2 and §5.3 |
| **C-9** | `CQ-013`: "no shared constants module for cookie names exists" | a new module is needed | ✔ A **pattern** exists: `PREFERRED_CITY_COOKIE_NAME` / `_MAX_AGE` live in `apps/core/middleware/preferred_city.py` and are imported by both `consent.py` and `search/views/preferred_city.py` | The remedy is a **relocation**, not a new abstraction — but *which* existing module becomes the home is a real choice with two defensible answers. `Q13` |
| **C-10** | `CQ-012`: add `PriorityScore`; "low risk" | small | `PriorityService.calculate_and_save` passes the return value **straight** into `AdModerationPriority.objects.update_or_create(defaults=data)` and then reads `data["base_score"]`. `test_priority.py` has **~30** cases asserting the **dict** shape (`result["score"]`, `result["flags"]`, `result["priority_level"]`, `result["confidence_score"]`) | Converting to a Pydantic model breaks every one of those unless it keeps mapping access, **or** `priority.py` changes in the same commit. `Q14`. Largest test blast radius of the four "cheap" MEDIUM findings |
| **C-11** | Report-wide measurements | 27,275 lines · 1,387 comment lines (5.1 %) · 92 deferred imports · 713 functions | ✔ 28,574 lines · **1,526** comment-only lines (**5.3 %**) · **96** deferred imports across 47 files · 300 production files | Every number in a block instruction is **re-measured before it is trusted**. The findings' *conclusions* are unchanged; their *counts* are not |
| **C-12** | `CQ-004`: `min_price=-1` → `IntegrityError` → HTTP 500 | a crash | ✔ Refuted and upheld as refuted: `PositiveIntegerField` defines no `check()` and no DB constraint; `apps/search/migrations/0001_initial.py` has no `CheckConstraint`. `min_price=-1` is **silently persisted** | The gate is real (a mandated Pydantic boundary is absent) but the impact framing is wrong. The reproduction must be **rewritten** before it enters a tracker; BLOCK 4 ships a **validation error path**, which is a *new response shape* nobody has decided yet — `Q12` |

#### 0.2.2 The four hazards that constrain how any block may be implemented

1. **`edit.py` and `submission.py` are the two hottest files in the whole plan set.** Not
   "one of". `ad_edit` has **three** other phases' blocks pointed at it plus phase 15's two
   AUTHZ items; `submission.py` carries **eight** claims. BLOCK 16 is the only block in this
   plan that may touch either, and it is a single commit with a single owner.
2. **`admin_actions.py` is held by five phases** (03, 04, 05, 06, 07) and is the subject of
   a *move*. Highest value-per-diff in the report, highest coordination cost. BLOCK 12 is
   one commit, three importer updates, coordinator told.
3. **`core/enums.py` is held by five phases** and already carries uncommitted phase-02 work.
   Exactly **one** block in this plan may edit it (BLOCK 3, `LanguageLocale`), and it must
   re-read the file immediately before editing. **No phase-10 block allocates an
   `AdvisoryLockId`.**
4. **Source-inspection tests are the highest-risk class in this phase** — they go red on a
   *move* that changes no behaviour. Four clusters: `test_edit_views_locking.py` (5 tests
   over `ad_edit` / `submit_ad`, including an `index()` ordering assertion that **errors**
   with `ValueError` rather than failing cleanly), `test_unsubscribe.py::TestResolveOwnedLocking`
   (2 tests over `alerts._resolve_owned`), `test_moderation_views.py::TestModerationReviewLocking`
   (3 tests, survives a decorator swap, dies on a restructure), and phase 05's
   `TestBulkLockingStructure` over `api_bulk.py`. Every block that moves code names the test
   it must re-point, in the same commit.

#### 0.2.3 Runtime re-verification required before a block relies on a claim

Cheap, and part of each block's **Auditor** pre-step — never the Implementor's to discover
mid-edit. **No test suite was run for the audit, for the code context, or for this plan.**

| # | Claim to re-verify | Block | How |
|---|---|---|---|
| 1 | `AdEditInput.title` / `.description` are still `""`-defaulted and an omitted key still blanks a live ad | 16 | Static read is sufficient and done; runtime confirmation via `$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/ads/tests/test_edit.py --tb=short" test` with a **new** omitted-key case asserting **red** first |
| 2 | An uncaught Pydantic `ValidationError` in `ad_edit` surfaces as **500** (Q3) | 16 | Force `AdEditInput.model_validate` to fail inside the `transaction.atomic()` and assert the response status before the fix |
| 3 | `POST /save-search/` with `min_price=-1` persists `-1` silently | 4 | One targeted test asserting the row exists with `-1` **before** the fix |
| 4 | `reject_ad` and `ban_user` return **302** on GET; `approve_ad` returns **405** | 12 | The two shipped assertions already pin it; read them rather than re-deriving |
| 5 | `test_search_fuzzy.py::TestFuzzyEquivalence` re-derives `cutoff=0.8` in-test (Q6) | 15 | **RESOLVED 2026-10-03 — the unified cutoff is 0.8, which is the value the test already asserts, so the test is read and left UNCHANGED.** The contingency that required a project-rule-2 rewrite under a 0.6 outcome is **moot**; if the block changes this test, stop and report — rewriting it reverses the Product Owner decision |
| 6 | `cmd_alerts`'s prompt string is the only place `/alerts` promises a toggle | 10 | Read `alerts.py`'s three router entry points; no test covers the listing or the prompt |
| 7 | `PLC0415` would fire on **96** sites, and `ruff check src/` is green today | 13 | Run `uv run ruff check src/` before, add the rule with its exclusion list, run again. **A red gate on arrival is a missing exclusion, not a defect to suppress** |
| 8 | `AdvisoryLockId`'s membership, re-read at that moment | — | **No block allocates one.** If BLOCK 3 must edit the same file, re-read `core/enums.py` first (C-7) |
| 9 | The four `type: ignore[type-arg]` suppressions are still the only ones in production code, and all in `lookup_resolution.py` | 9 | One grep. `[tool.mypy]` is not run by any gate (C-4), so "0 errors from basedpyright" is **not** evidence for this finding |
| 10 | `RESOLVED_*_PREFIX` have no importer **outside this repository** (Q5) | 8 | Whole-repo grep is in-repo only. The in-repo half is done; the external half is a one-question ask to the coordinator |

---

### 0.3 Scope statement (explicit)

**In scope — 18 open finding-units.** 17 whole findings still exist
(`CQ-001`, `CQ-003`…`CQ-019`) plus the three open halves of `CQ-002`
(`alerts`, `contact`, `support`). Mapped onto 16 blocks in §2.

**In scope as *findings*, but narrowed by this plan's corrections** (each narrowing is
argued, not silent):

- `CQ-005` → **template-only**, 10 template lines, 0 Python sites (C-1).
- `CQ-002` → **`alerts` only** is an extraction; `contact` and `support` are import hoists;
  the `login` half is **already shipped** and is not re-filed (C-3).
- `CQ-010` → split into a **file move** (BLOCK 12) and a **`pyproject.toml` gate** (BLOCK 13).
- `CQ-018` → split into **mechanical decorators** (BLOCK 6), the **URL half shared with
  `CQ-005`** (BLOCK 5), and the **behavioural `review.py` half** (BLOCK 7, merged with
  `CQ-003` because both land on `reject_ad`'s request boundary).
- `CQ-017` → only sub-claims 1 and 2 ship; sub-claim 3 is de-scoped (C-7).
- `CQ-019` → **folded into `CQ-007`** (both are documentation-density trims in
  `core/utils/cache.py`). No tree-wide comment census: that is phase 03 BLOCK 11's, and its
  rule is *"Phases 04–15 must not start BLOCK 11-style legacy sweeps of their own."*

**Not in scope — see §6.** Six items the report proposed or implied and this plan refuses:
the numeric `/alerts` toggle, `PreferredCityInput`, `CacheEntry` + the five cache modules,
`apps/core/services/locales.py`, the two AST architecture tests and the custom
`scripts/lint_no_deferred_imports.py`, the `ErrorPage` enum and `_build_submit_input`
helper, `require_http_methods` adoption, and the `AdvisoryLockId` reorder. Every one has a
named destination or a stated rationale; none is dropped silently.

**One finding must not be revived under any name.** `can_publish_ad` is **phase 15's
`AUTHZ-005`**, whose validator *rejected* the dead-code label. It is test-referenced 13×
in `test_account_state.py`. `CQ-016` correctly omits it and so does this plan.

**No new architectural layer, base class, manager class, registry, plugin mechanism or
service locator is proposed by any block in this plan.** The net new surface is: 1 module
(`apps/ads/services/edit_ad.py`), 1 module (`telegram_bot/services/alerts.py`), 1 DTO module
or class location for `SavedSearchInput` (Q12), 1 typed DTO (`PriorityScore`), 1 extracted
function (`build_listings_context`, if Q8 goes that way), 1 empty `__init__.py`, and 1 file
move. The report's own proportionality judgement — **PROPORTIONATE**, with six of sixteen
artifacts rejected — is upheld and tightened further by the four de-scopings in §6.

---

### 0.4 Severity corrections

The report's own movement is upheld in full and is **not** re-litigated:

| ID | Movement | This plan's position |
|---|---|---|
| `CQ-001`, `CQ-002`, `CQ-008` | HIGH → **MEDIUM** | **Upheld.** All three are maintainability concerns with no availability, security or data-integrity consequence. Phase 01 set the precedent by downgrading `ENT-005` for the same reason. What the downgrade does **not** do is make the work optional: the collision in C-6 is a *sequencing* problem, not a severity problem, and BLOCK 16 remains the highest-coordination block in the plan |
| `CQ-007`, `CQ-010` | MEDIUM → **LOW** | **Upheld.** `cache.py`'s keys and TTLs are already single-sourced as `Final` default arguments, so a key change is a one-line edit; and 96 deferrals are mostly legitimate `AppConfig.ready()` / bootstrap / signal-module deferrals. The residual is a docstring trim and a file move |
| `CQ-004` | MEDIUM, `BEST-PRACTICE` | **Upheld**, with the impact corrected (C-12). The gate is real; the 500 is not |

**Corrections this Planner makes to the *executed* risk, without re-grading the findings:**

- **`CQ-005` executes as a LOW-risk change.** After the scope correction (C-1) there are
  **zero** Python sites, and because `AdStatus` is a `StrEnum` the substitution is
  *semantically neutral* — `status == 'published'` is already `True`. The real content is
  the one template line where the literal sits **inside a hardcoded URL**. This does not
  change the Validator's MEDIUM; it changes how the block is reviewed.
- **`CQ-011` is not a user-facing recall defect, and the report's framing is wrong.** ✔ On
  `/search/?category=<slug>` the category is resolved by the **breadcrumb** path
  (`Category.objects.get(slug=…))`) and a typo merely echoes the raw string — the fuzzy
  ladder is reached only from the **`?q=`** path. The finding survives as a **consistency
  and maintainability** defect (two divergent ladders, two divergent cutoffs, one name list
  already shared). Block 15 is still behavioural, still gated on three questions, and still
  one commit — but nobody should argue for it as a recall fix.
- **`CQ-012` is unenforced by any gate** (C-4). `basedpyright` is in `standard` mode and
  does not flag bare generics; `[tool.mypy]`, which carries `disallow_any_generics`, is
  **not in CI** and is **not read by basedpyright**. "Type errors went from N to 0" is not
  available as evidence for this finding, and BLOCK 9's acceptance criteria must not claim
  it. The four `type: ignore[type-arg]` suppressions are removable because they are **noise**,
  not because a gate objects to them.
- **`CQ-019` is not a defect at all** at 5.3 % on 28,574 lines of production Python whose
  comments are predominantly non-obvious design rationale. Folded into `CQ-007` as a
  documentation trim, and the tree-wide sweep is phase 03's.
- **`CQ-014` executes as LOW** once the toggle is de-scoped: the remainder is one prompt
  sentence and one dead-state deletion. The finding's MEDIUM rating described the *dead end*,
  which is real; the fix is a docstring-level correction plus a `states.py` deletion.

---

### 0.5 Open technical questions — resolved here, or explicitly gated in their block

**This plan does not choose where technical uncertainty exists.** All **fourteen** questions
are carried forward from the code context, plus two this Planner adds. Each produces either
a labelled **decision required before implementation** gate inside its block, with the
options and their consequences, or a named routing to the coordinator. **Silence is not an
acceptable outcome for any of them.**

| ID | Question | Block | Who decides | Status |
|---|---|---|---|---|
| **Q1** | Where does the shared category-fuzzy ladder live, given `apps/search/services/category_fuzzy.py` already owns the cached name list and `categories → search` inverts the graph? (a) ladder in `apps/categories/services/fuzzy.py` with the name list **injected**; (b) ladder in `apps/search/services/` and `ads/views/listings.py` imports from `search` (a new `ads → search` edge); (c) leave both sites alone and only align the cutoff constant | **15** | Planner + Researcher; **check with phase 08**, which owns `category_fuzzy.py`'s neighbourhood (BLOCK 6) | **GATED.** Changes the block's file set, its dependency-direction consequences and its test blast radius |
| **Q2** | What should an **invalid** `reason_category` do in `reject_ad` — 400, re-render the review page, or coerce to empty? Today **any** client string is concatenated into `ModeratorActionLog.reason` | **7** | **Product Owner** (routed from phase 15's `Q11`, which owns the moderation surfaces) — answered 2026-10-03 | **RESOLVED 2026-10-03 (Product Owner) — option (b): RE-RENDER the review page with an error and PRESERVE the moderator's input.** The gate row's former clause — *"`staff_required` + `transaction.atomic()` make a 400 the least surprising but not obviously right"* — is **superseded**: the 400 reading is **DECLINED**. **Nothing is coerced to empty**, and **no arbitrary client string reaches `ModeratorActionLog.reason`**. BLOCK 7 ships the re-render **plus a new user-visible error string ⇒ non-empty `ru` and `bs`**. **Still routed to phase 15**, which now owns it under its own `Q11` — the ruling is applied here, the moderation UX is phase 15's |
| **Q3** | For `CQ-009`, what does `ad_edit` return on a Pydantic `ValidationError`? Today `AdEditInput.model_validate` raises inside `transaction.atomic()` with **no handler** → 500. 400 vs a re-render of `ads/edit.html` with a new i18n string | **16** | Planner (the `ads/edit.html` error slot already exists as the `"error"` context key) | **GATED.** The single riskiest part of `CQ-009`; the report does not mention it |
| **Q4** | For `CQ-018`'s `review.py` half: is a GET on `reject_ad` / `ban_user` supposed to be a **302** to the admin change page (today) or a **405** (after `@require_POST`)? Two shipped tests assert 302; the sibling `approve_ad` already returns 405 | **7** | Owner / phase 15 | **GATED.** A behaviour decision, not a code decision |
| **Q5** | Do the three `RESOLVED_*_PREFIX` aliases have any **external** importer? Their source comment claims backward compatibility "with any external callers", and the repo has zero | **8** | Coordinator (one question) | **GATED, narrow.** In-repo half is proven; the external half is not. Project rule 2 says the code is king over the comment, but only after this is asked |
| **Q6** | Should the unified fuzzy cutoff be **0.6** or **0.8**? `test_search_fuzzy.py::TestFuzzyEquivalence` re-computes 0.8 inside the test over 10 `(locale, query)` pairs | **15** | **Product Owner** (how forgiving should "did you mean" be?) — answered 2026-10-03 | **RESOLVED 2026-10-03 (Product Owner) — the unified cutoff is 0.8.** Consequences: **`TestFuzzyEquivalence` stays GREEN AND UNCHANGED** — it already asserts 0.8 in-test, so **project rule 2 is NOT invoked and no test rewrite is permitted**; the **0.6 site** (`ads/views/listings.py::_suggest_category`) **aligns to the shared 0.8 constant**; BLOCK 15's risk row is **downgraded from "tests rewritten under project rule 2" to "tests unchanged"**. See §0.7 |
| **Q7** | Does `suggest_city` (`locations/services/city_suggestions.py`, `_CUTOFF = 0.6`) join the unification, or stay a separate entity's policy? | **15** | **Planner — UNCHANGED. Q7 is a technical gate, not a Product Owner decision, and the 2026-10-03 ruling did not touch it** | **STILL GATED.** Decides whether BLOCK 15 touches 2, 3 or 4 modules. **But the Q6 ruling sets the bar Q7 must clear:** if `suggest_city` stays separate, its surviving **0.6 must be justified against the 0.8 product decision** in the commit body, as a deliberate entity-specific divergence. That justification is an **acceptance criterion**, so Q7 can no longer be answered by leaving the value in place and saying nothing |
| **Q8** | Is `build_listings_context()` a **service** (new module) or a **shared helper** beside `ListingsQuery` in `apps/ads/services/listings_query.py`? Phase 08 **BLOCK 1** holds that file | **14** | Planner + phase 08 | **GATED.** A new module versus one more function in another phase's file |
| **Q9** | For `CQ-006`, do `LanguageLocale.fts_config` / `.fts_vector_field` become `match` arms or `Final` class-level mappings? Either keeps the pairings `test_search_triggers.py` pins | **3** | Planner | **GATED.** Stylistically cheap, but it sets a precedent for every future enum in the repo |
| **Q10** | For `CQ-005` (and `CQ-018`'s template URL): is the enum exposure a **context processor** in `core/context_processors.py` (next to `price_step`) or a **per-view context key** (next to `dashboard.py`'s `status_labels`)? | **5** (and **7** reuses it) | Planner | **GATED.** A context processor adds a key to *every* template; a per-view key is narrower. Also decides the mechanism for `CQ-003` |
| **Q11** | Are the `QLT-###` provenance tags in `ads/views/edit.py`, `apps/media/schemas.py` and `telegram_bot/handlers/ad_create/submit.py` reconciled with `10-CQ-0NN`, or does the coordinator keep two vocabularies? | — | Coordinator | **ROUTED.** Phase 03 BLOCK 11 reserves the in-source ID sweep. No phase-10 block writes or sweeps a marker |
| **Q12** | *New.* For `CQ-004`: where does `SavedSearchInput` live — a new `apps/search/schemas.py` (matching `apps/media/schemas.py`, `apps/users/schemas.py`, `telegram_bot/schemas/`), or an existing module — and what is the **error response shape** for a rejected POST: a 400, or a re-render of the save-search modal? | **4** | Planner (shape) + Owner (modal vs 400) | **GATED.** A new response shape nobody has decided, and phase 08 owns `apps/search/models.py` and the next `search/migrations/0003` |
| **Q13** | *New.* For `CQ-013`: do the four `CONSENT_*` names move **into** `apps/core/middleware/preferred_city.py` (the established home of `PREFERRED_CITY_COOKIE_*`), or does a new `apps/core/cookies.py` own all cookie constants? | **1** | Planner | **GATED.** Option (a) is a relocation with zero new artifacts; option (b) is a new module with one consumer pair, which project rule 5 may not justify |
| **Q14** | *New.* For `CQ-012`: does `PriorityScore` keep **mapping compatibility** (`__getitem__` / `**`-expansion into `update_or_create(defaults=...)`), or does `priority.py` change in the same commit to use attribute access — accepting a rewrite of ~30 assertions in `test_priority.py`? | **9** | Planner | **GATED.** Determines whether BLOCK 9 is a one-file change with an adapter or a two-file change with a test rewrite |

**Resolved in this plan, with the reasoning stated** (these are not open questions; they are
rulings so a block does not re-derive them):

- **The class taxonomy for every block.** `mechanical` = no observable behaviour change,
  no decision gate that changes an outcome, safe to batch. `behavioural` = changes an
  observable response, touches a shared contract, breaks a shipped test, or is gated on an
  open question. The classification is in §2 and is repeated in each block's header.
- **The order principle.** Blocks are numbered so that **one file is written by one phase-10
  block per run**, and the first writer of a contended file is the mechanical one. Where a
  file needs a structural change, the structural block comes *after* every mechanical one
  (`review.py`: 5 → 7 → 12 → 13; `alerts.py`: 10 → 11; `consent.py`: 1 → 8;
  `submission.py`: 16 only).
- **`CQ-001` and `CQ-008` ship in one block with `CQ-009`.** Splitting them is precisely the
  failure the report's §A describes: each of the three relocates code the other two's fix
  depends on.

---

## 1. Environment and command contract for the implementor

**This environment is Windows 11 / PowerShell 7.** `make` requires WSL or GNU Make; use
`.\Makefile.ps1 <target>`. `head` / `tail` are unavailable in PowerShell.

### 1.1 Tests are Docker-only — `uv run pytest` on the host always fails

There is no PostgreSQL on `localhost:5432`. Every test run goes through the `test` service
of the `mko-bazuna-test` Compose project. `docker/entrypoint-test.sh` performs **no**
database setup: pytest-django provisions `test_mko_bazuna`, and the session-autouse fixture
in `src/backend/conftest.py` restores reference data under advisory lock 111.

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
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/ads/tests/test_edit.py --tb=short" test

# Full suite (only when the change touches seeding or images)
$dc run --rm test

# Fresh schema (no phase-10 block ships a migration; use only if a migration appears
# that phase 10 did not write)
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
  while another phase agent is running, **re-run it serially** before reporting it as a
  defect. Teardown races surface as `FATAL: database "test_mko_bazuna" does not exist` and
  `relation "..." does not exist`, not as product failures.

Prefer `.\Makefile.ps1 up | test | test-all | test-recreate | test-down` — they manage the
project name and env file for you.

### 1.2 Lint, typecheck, i18n

```powershell
uv run ruff check <path>            # lint
uv run ruff check --fix <path>      # auto-fix, INCLUDING import sorting (I001)
uv run basedpyright <path>          # typecheck
uv run djlint src/backend/templates/   # only if a template changes
```

**`[tool.ruff] fix = false` is set in `pyproject.toml` with the comment "IMPORTANT: do NOT
auto-fix by default."** A blanket `ruff check --fix src/` across a block's whole file set
would reorder imports that another phase's uncommitted work depends on. Reorder imports
**only** in the files the block actually edits, and only when the block introduced the
unsorted import. `ruff format` is **not** the project convention (`.\Makefile.ps1 format`
runs `ruff check --fix src/`, not `ruff format`).

**CI scope, verified in the tree:** `.github/workflows/ci.yml` runs
`uv run ruff check src/`, `uv run basedpyright src/` and `uv run djlint templates/`.
Phase 01 (`ENT-004`) scoped lint and typecheck to `src/`, so the **bot process is inside
both gates** — `ENT-004` is a **satisfied precondition**, not a blocker, and BLOCK 11 may
start without it. mypy is **not** in CI and `[tool.mypy]` is **not** read by basedpyright
(C-4).

**i18n is part of DoD.** Every user-visible string is wrapped in `{% trans %}` /
`{% blocktrans %}` (templates) or `gettext` / `gettext_lazy` (Python). `LOCALE_PATHS` is
`[BASE_DIR / "backend" / "locale"]` — **one** catalogue serves web and bot, so a bot string
and a web string land in the same `src/backend/locale/*/LC_MESSAGES/django.po`. `msgstr`
must be **non-empty** for `ru` and `bs`; `en` may be empty (the msgid is English). `.mo`
files are gitignored and compiled at image build, at container start and in the CI `i18n`
job. `make makemessages` / `make compilemessages` **do not work** on Windows + Docker
Desktop; use the lightweight `--no-deps --entrypoint ""` form in `.kilo/rules/commands.md`
if a `.po` must change. **Append; never regenerate wholesale** — the catalogues are shared
with phases 03/05/06/07/11/14.

Only **two** blocks may touch a user-visible string: BLOCK 10 (the `/alerts` prompt, if
Q-gated option (b) is taken) and BLOCK 16 (the `ad_edit` error message, if Q3's re-render
option is taken). Both append to the locale files **in the same commit** as the code change.

### 1.3 Git contract — one implementor, sequential, one commit per block

- **One Implementor at a time.** Never two. Never a background implementor.
- If a block is stopped mid-way, **resume the existing session**; do not launch a new agent.
- Each block is committed separately, explicitly staged: `git add <specific files>` —
  never `git add -A`, never `git add .`.
- Message form, matching the repo style: `"{type}({scope}): {description}"`, e.g.
  `refactor(core): relocate the consent cookie constants (10-CQ-013)`,
  `refactor(moderation): move admin_actions into services (10-CQ-010)`,
  `refactor(ads): extract ad_edit and submit_ad orchestration (10-CQ-001, 10-CQ-008)`.
  Every new citation is **cycle-scoped** `10-CQ-0NN`, never a bare `CQ-0NN` and never a
  `QLT-0NN` (Q11).
- **Never** `git reset`, `git checkout`, `git restore`, `git stash`, `--amend`,
  `--no-verify`, or any other history mutation. Never force-push.
- **Other agents are working in parallel**, and several are editing the same files. Files
  you did not change appearing in `git status` is normal. **Never** revert, stash or
  `git checkout` a file you did not write. If a file you are about to edit already has
  uncommitted changes from another agent, **stop and report it** rather than clobbering it.
  This is the normal case for `core/enums.py`, `ads/views/edit.py`, `submission.py`,
  `admin_actions.py` and `handlers/alerts.py`.
- Do not commit unless the block's instructions say to.

### 1.4 Standing project rules (restated for every block)

- **English only** — comments, logs, docstrings, error messages, documentation.
- **No `print()`.** `logger = logging.getLogger(__name__)` with lazy `%s` formatting.
- Stack: **Python 3.14 · Django 5.2 LTS (`>=5.2.16,<6.0`) · PostgreSQL 18 · aiogram 3.x ·
  native PostgreSQL FTS.** **Two processes, one DB:** web (gunicorn sync WSGI, HTMX MPA)
  and bot (aiogram, `django.setup()` + shared ORM). **Migrations run exactly once** before
  both start — a migration that must run in only one process is a defect.
- **Django ORM is the persistence layer.** **Pydantic v2 only at system boundaries** (bot
  input, settings schemas, DTOs that belong at a request edge). Business logic lives in
  `services/`; views stay thin adapters. This plan adds **one** DTO (`SavedSearchInput`,
  BLOCK 4) and **one** typed model (`PriorityScore`, BLOCK 9) — no framework around either.
- **All schema changes via Django migrations.** **This plan ships no migration.** Never
  renumber or edit an applied migration.
- **Fixed values via `StrEnum` / `Enum`** (project rule 10) — never plain strings, dicts or
  lists. In-repo precedent: `LanguageLocale`, `AdStatus`, `AdSort`, `AdvisoryLockId`,
  `CategoryRejectReason`, `LookupGroupCode`.
- **Small, focused modules and functions. Composition over inheritance.** Follow existing
  patterns; **no new abstraction without strong justification**; no speculative redesign;
  **no scope creep**; prefer the simple, obvious solution. Every remedy the code context
  flags as a speculative redesign is in §6 with a rationale, not in a block.
- **Production code is king.** If a test conflicts with the architecture or the business
  logic, **fix the test** — and say which change and why in the commit body. This plan
  slates **two** tests for that treatment (BLOCK 15's `TestFuzzyEquivalence` under Q6 option
  (b), and BLOCK 9's ~30 `test_priority.py` cases under Q14 option (b)) and **re-points
  four source-inspection tests** (BLOCK 11's two, BLOCK 16's two). Each is named in its
  block and justified in its commit body.
- **No blanket `except Exception`** around DB calls (`BLE001`). `submit_ad`'s existing
  thumbnail swallow is pre-existing and out of scope; BLOCK 16 must not add a second one.
- **Do not add a template-tag library.** `core/context_processors.py::price_step` is the
  existing pattern for exposing a value to templates; BLOCK 5 copies it, BLOCK 7 reuses it.
- **Do not edit `src/backend/conftest.py`.** It is among the most contended files in the
  repository. If a block appears to need a new fixture, that is a signal the test is
  over-fitted.
- Docs in `docs/` stay in sync. BLOCK 2 and BLOCK 5 amend module docstrings and template
  comments; no `docs/` file is a phase-10 target.

### 1.5 Test authoring standard for every block

Tests verify **logic and component interaction**, not implementation trivia. No test asserts
a line number, a column count from introspection, a literal private name, a template-string
substring, or the mere presence of a symbol. Assert on **observable behaviour** and on the
**absence of danger**.

Good targets for this phase:

- a negative `min_price` is **refused** at the boundary and nothing is stored, while every
  positive value round-trips as an `int` and the saved search still matches ads;
- an invalid `reason_category` is **refused**, while all eight enum members still persist
  and the `"<category>: <text>"` shape of `ModeratorActionLog.reason` is unchanged;
- a POST that omits `title` is **refused** and the live ad's title is **byte-identical**
  afterwards, while a POST with a changed title still saves;
- the same suggestion is produced for one category query through **both** `/` and `/search/`,
  and an exact slug match on `/` now resolves (it does not today);
- an exact `CategoryRejectReason` member and an arbitrary client string produce
  **distinguishable** stored audit rows;
- a GET to `reject_ad` returns the status the chosen Q4 option requires, and the ad is
  **not** moderated either way;
- a moderation action issued through the moved service behaves identically to one issued
  through the old module path.

**Never use a line number as a task target.** Every target is a file plus a **semantic**
anchor: a class, a method, a module-level `Final` constant, a named attribute, a function
call, a URL route name, a template block, a `.po` msgid.

Fixtures are canonical in `src/backend/conftest.py`: `seller` (900000001), `user`
(900000002), `category`, `city`, and
`create_test_ad(user, category, city, *, status=AdStatus.PUBLISHED, **kwargs)`.
`src/telegram_bot/tests/conftest.py` redefines these as an **async** `user`; bot tests
cannot import the backend conftest.

**The four source-inspection clusters are a known hazard, not a licence.** When a block
moves a function out of a module that a test inspects by `inspect.getsource`, the test is
**re-pointed at the new owner in the same commit** and its assertions are reviewed for
still expressing the *intent* (lock taken inside the transaction; the fetch inside the
transaction). Do not delete such a test to make a block green — that removes the only
shipped guard on the locking structure.

### 1.6 Task shape for every block

Each block's implementor task follows `.ai\tasks\templates\task_template.yaml`: semantic
`targets` with `type` / `name`, `semantic_anchors`, `changes`, `acceptance_criteria`,
`source_reference` / `source_section` / `source_blocks`, and an `extra_context` block
carrying the block's binding constraints **verbatim**. Verification is **inline** for
`mechanical` blocks (the Implementor runs `tests_to_run` and checks `acceptance_criteria`);
a **separate Validator task is required** for every `behavioural` block, for every block
whose acceptance depends on a decision the Implementor was told not to make, and for
BLOCK 16 (all four agents). Required agents are stated per block in §3.

### 1.7 Product Owner gate rulings — 2026-10-03

**Authority.** Product Owner decisions, dated `2026-10-03`, recorded here so that no Implementor
can re-derive a settled question. **Three rulings map to this plan.** Two of them **reduce risk**
(a test no longer needs rewriting) or **remove an option**; one **creates an i18n obligation**
and one **creates a tracked backlog item**.

| Gate | Ruling (2026-10-03, Product Owner) | Chosen option | Block-level consequence |
|---|---|---|---|
| **Q6** — the unified fuzzy cutoff | **The unified fuzzy cutoff is 0.8** | **0.8** | **BLOCK 15 — and the plan's test-rewrite contingency is MOOT.** `test_search_fuzzy.py::TestFuzzyEquivalence` re-derives **0.8 in-test**, so the product decision and the shipped test now agree: the test stays **GREEN AND UNCHANGED**, **project rule 2 is never invoked**, and a rewrite is a *reversal of a Product Owner decision*. The **0.6 site** — `ads/views/listings.py::_suggest_category` — **aligns to the shared 0.8 constant** and loses its local literal. Binding constraint 4 now names the value. **BLOCK 15's risk row is downgraded** from *"tests rewritten under project rule 2"* to *"tests unchanged"* |
| **Q2** — an invalid `reason_category` | **Re-render the review page with an error and preserve the moderator's input.** Nothing is coerced to empty; no arbitrary client string reaches `ModeratorActionLog.reason` | **(b)** | **BLOCK 7.** The gate row's former clause — *"`staff_required` + `transaction.atomic()` make a 400 the least surprising but not obviously right"* — is **superseded**: the **400 is DECLINED** and the coercion option is declined. Binding constraint 3 is **rewritten in place** to carry the three invariants. **Two new obligations, both with acceptance criteria: a new user-visible error string with non-empty `ru` and `bs` in the same commit, and a preserved-input assertion** — a re-render that silently discards the moderator's typed `comment` would be a worse defect than the one being fixed. Option (d)'s "other" member was **not** chosen, so the vocabulary **stays at 8** and `db-enums.md` is not edited |
| **`CQ-014`** — the `/alerts` numeric toggle | **Fix the prompt to match implemented behaviour and delete the dead state; the feature is NOT built in this programme** | option (a) only | **BLOCK 10** delivers the prompt correction; **BLOCK 8** delivers the `SavedSearchState` deletion. **No new FSM, no new router entry point, and no new i18n strings are in scope** — the three new strings the report contemplated are **explicitly out of scope**. The un-built toggle is recorded in §6.1 as a **feature request with a named owner** (the bot's seller-facing-flows owner). BLOCK 10's risk row *"the prompt is fixed but the toggle still does nothing"* **SURVIVES** and now cites that owner |

**`Q7` is deliberately untouched.** Whether `suggest_city`'s `_CUTOFF = 0.6` joins the
unification is a **Planner gate, not a Product Owner decision**, and the 2026-10-03 ruling did
not touch it. **What the ruling did change is the bar Q7 must clear:** if `suggest_city` stays
separate, **its surviving 0.6 must be justified against the 0.8 product decision** in the commit
body, as a deliberate entity-specific divergence rather than an oversight. That justification is
now an **acceptance criterion**, so Q7 can no longer be answered by leaving the value in place and
saying nothing.

**Cross-plan propagation obligations created by these rulings.**

- **Phase 15 — `Q11`.** Q2 originated as phase 15's `Q11` and the moderation UX is phase 15's.
  Phase 15 must record the same answer so it does not re-open the question.
- **Phase 15 — the moderation UX.** BLOCK 7 applies the re-render because the code lands here;
  the moderator-facing template and context key are a shared surface with BLOCK 5. Re-read
  before editing.
- **Bot seller-facing-flows owner.** The `/alerts` toggle is a declined feature with a named
  owner (§6.1). BLOCK 11 must run before any future toggle work, because the handlers would land
  in the file its extraction moves.

**Technical gates that are NOT Product Owner decisions and remain exactly as they are.**
**Q1**, **Q3**, **Q4**, **Q5**, **Q7**, **Q8**, **Q9**, **Q10**, **Q11**, **Q12**, **Q13** and
**Q14** all keep their existing state. **Q4 in particular is untouched**, though its premise is
narrowed by a sibling 2026-10-03 ruling held outside this plan — see the note in BLOCK 7. No
module placement, commit sequencing or migration numbering was changed by any 2026-10-03 ruling.

---

## 2. Scope decisions table (acceptance contract for execution)

`mechanical` = no observable behaviour change, no outcome-changing decision gate, safe to
batch or run without a Validator. `behavioural` = changes an observable response, touches a
shared contract, breaks a shipped test, or is gated on an open question.

| ID | Class | Disposition | Block | Severity | One-line reason |
|---|---|---|---|---|---|
| `CQ-001` | **behavioural** | **implement — one coordinated change set.** Extract `ad_edit` into `apps/ads/services/edit_ad.py`, and land it in the **same commit** as `CQ-008`, `CQ-009`, and — outside this plan — `AUTHZ-007` and `AUTHZ-002`. Build the hoisted `SubmitAdInput` with `user_id=request.user.id`, **never** `ad.user_id` | **16** | MEDIUM (execution risk **HIGH**) | Largest function in the repository (193 lines, verified) with no demonstrated defect, but it is the single most contended symbol in the plan set: phase 03 BLOCK 5, phase 05 BLOCKs 2/8/12, phase 07 BLOCK 10, and phase 15's two AUTHZ items all point at it. **Three shipped source-inspection tests, one of them a hard `count("select_for_update") == 1`, are the detector** (C-6) |
| `CQ-002` | **behavioural** | **implement the `alerts` half only.** `telegram_bot/services/alerts.py` for `get_user_saved_searches` / `resolve_unsubscribe` / `resolve_reenable` / `_resolve_owned`; `contact.py` and `support.py` become **module-level imports**, not new modules. **The `login` half is already shipped and is not re-filed** | **11** | MEDIUM | Layering inconsistency with no defect. The report's own merge instruction and target correction were executed by phase 01 `ENT-005`; re-filing them would ship the same code twice at a different severity (C-3). Two source-inspection tests in `test_unsubscribe.py` must be re-pointed |
| `CQ-003` | **behavioural** | **implement — Q2 RESOLVED 2026-10-03: option (b).** Expose the enum through the Q10 mechanism, delete the eight hardcoded `<option>`s, and validate `reason_category` at the boundary **before** the `reason` string is constructed. On an invalid value **re-render the review page with an error and preserve the moderator's typed comment** — **not** a 400, **not** coerced to empty, and **no audit row written**. New user-visible error string ⇒ **non-empty `ru` and `bs`** | **7** | MEDIUM | Zero production call sites today; any client string is concatenated into `ModeratorActionLog.reason`. The "unqueryable" half is a **documented design decision** (the enum's own docstring says it is not a DB column), so what survives is the *unvalidated vocabulary* — narrower and sharper than reported. Five existing reject tests post a valid member, so the change is additive for them. **The owner declined the 400**, which is why the deliverable now carries an i18n obligation |
| `CQ-004` | **behavioural** | **implement `SavedSearchInput` only — gated on Q12.** Two byte-identical `_int_or_none` closures deleted; `ge=0` price bounds; the `save_search` **view name** and the `request.LANGUAGE_CODE or "bs"` fallback preserved. **`PreferredCityInput` de-scoped** (§6) | **4** | MEDIUM | A mandated Pydantic boundary is genuinely absent and the two closures are byte-identical — but the report's crash is refuted: `min_price=-1` is **silently persisted** (C-12). Fixing it introduces a **new response shape**, which is Q12 |
| `CQ-005` | **mechanical** | **implement — template-only.** 10 template lines / ~14 literal occurrences across 4 templates, through the existing `price_step` context pattern. **`ads/edit.html` included** (unfiled by the report) | **5** | MEDIUM → executes LOW | **Zero Python sites** (C-1). `AdStatus` is a `StrEnum`, so the substitution is semantically neutral; the one real site is the literal **inside a hardcoded `/admin/` URL** in `analytics/moderation_dashboard.html`, which is why BLOCK 5 carries `CQ-018`'s URL half too |
| `CQ-006` | **mechanical** | **implement in place — gated on Q9.** `LanguageLocale.X.value` substitution at 10 file-sites, plus the two raw dicts inside `LanguageLocale` itself, plus the false invariant sentence in the module docstring. **No `locales.py`** (§6) | **3** | MEDIUM | Highest closed-literal count per diff line in the report. `LanguageLocale` already exposes `.values()`, `.from_code()`, `.fts_config` and `.fts_vector_field`; a wrapper module is a hop with no consumer. The bot submit path's six `.get("ru"/"bs"/"en")` calls are the largest cluster. `test_search_triggers.py` pins the FTS pairings and must stay green |
| `CQ-007` | **mechanical** | **implement — documentation only.** Trim the boilerplate docstrings on the 12 one-line wrappers and fix the stale module docstring ("ModerationCriteria" — it now covers four caches). **No `CacheEntry`** (§6) | **2** | LOW | Every key and TTL is already a module-level `Final` used as a **default argument**, so a key change is a one-line edit and the report's "12 places" impact is false. What survives is a real rule breach: `python-code-standards.md:19` — *"comment only non-trivial logic"* |
| `CQ-008` | **behavioural** | **implement — same commit as `CQ-001`.** Split `submit_ad`'s orchestration into the app's own `services/`, keeping the locked fetch inside the transaction | **16** | MEDIUM (execution risk **HIGH**) | 124 lines, six responsibilities, no defect. It cannot be split independently of `CQ-001` because `ad_edit` branches on its return value, and because `SubmitAdInput.user_id` — the field `AUTHZ-002` guards — is declared and never read. **A split that moves the fetch into a helper makes `test_submit_ad_fetches_inside_atomic` raise `ValueError`, not fail cleanly** |
| `CQ-009` | **behavioural** | **implement — gated on Q3, same commit as `CQ-001`/`CQ-008`.** `title` / `description` required with `min_length=1` | **16** | MEDIUM | A POST omitting `title` persists `""` over a live ad's title. **No test covers the omitted-key case**, so the change is unopposed — but the risk is the *response*: an uncaught `ValidationError` inside `transaction.atomic()` is a **500** today, and the report does not mention it |
| `CQ-010` | **mechanical** (move) | **implement as two commits.** BLOCK 12: move `admin_actions.py` → `apps/moderation/services/admin_actions.py`, three importers, one commit. BLOCK 13: enable `PLC0415` in `pyproject.toml` **with** a `per-file-ignores` list. **No custom lint script** (§6) | **12**, **13** | LOW | Highest value-per-diff in the report (the move deletes three arbitrary deferred imports as a side effect, and the module's own docstring already calls it a service) and its highest coordination cost: **five phases hold the file**. The count is **96**, not 92; the rule is a `pyproject.toml` edit, not a CI edit; and `PLC0415` on today would fire 96 times (C-4) |
| `CQ-011` | **behavioural** | **implement — Q6 RESOLVED 2026-10-03 (cutoff 0.8); still gated on Q1 + Q7, both written down first.** The report's target module is **wrong**; the ladder's home, the cutoff and the scope are decisions, not implementation details | **15** | MEDIUM (consistency, **not** a recall defect) | Two divergent ladders and two divergent cutoffs over **one already-shared** name list. The report's user-visible framing is wrong: on `/search/?category=…` the slug is resolved by the **breadcrumb**, and the ladder is only reached from `?q=` (§0.4). `test_search_fuzzy.py::TestFuzzyEquivalence` re-computes `cutoff=0.8` in-test and turns red on any change (C-2) |
| `CQ-012` | **behavioural** (for the test suite) | **implement as one commit — gated on Q14.** `PriorityScore` + annotated `CategoryLookupResolver` + the 4 `type: ignore[type-arg]` dropped + the 2 bare generics in `cache.py` + the 2 untyped signatures in `context_processors.py`, in the same commit because the suppressions and the annotations are inseparable | **9** | MEDIUM | The four suppressions are the only ones of their kind in production code. **No gate enforces this** (C-4): basedpyright is in `standard` mode, `[tool.mypy]` is not read by it and is not in CI. Largest test blast radius of the "cheap" MEDIUM findings: ~30 assertions in `test_priority.py` plus a `defaults=data` consumer (C-10) |
| `CQ-013` | **mechanical** | **implement — gated on Q13.** Relocate the four `CONSENT_*` names; update five raw read sites. Values and names byte-identical | **1** | LOW | Cheapest fix-to-risk ratio in the report: ~40 assertions across 5 test files pin the cookie names and values, and a pure relocation changes none of them. A rename would silently break anonymous consent state for every returning visitor |
| `CQ-014` | **behavioural** | **RULING 2026-10-03 (Product Owner) — fix the prompt to match implemented behaviour and delete the dead state; the feature is NOT built in this programme.** **BLOCK 10** delivers the `/alerts` prompt correction; **BLOCK 8** delivers the `SavedSearchState` deletion. **No new FSM, no new router entry point, and no new i18n strings are in scope** — the three new strings the report contemplated are **explicitly out of scope** under this ruling. Recorded as a **feature request with a named owner** (§0.7) | **10** (prompt) · **8** (dead state) | MEDIUM → executes LOW | A live user-facing dead end: three router entry points, no numeric handler, and a prompt that promises one. Implementing the toggle is a **new feature** — FSM states, a new router entry point, input parsing, error paths and 3 new i18n strings — wildly out of proportion to a code-quality finding, and **the owner has now declined it for this programme**. **No test covers `cmd_alerts`' listing or prompt**, so the correction is unopposed. The surviving risk — *"the prompt is fixed but the toggle still does nothing"* — is **accepted by decision** and the feature request carries a named owner |
| `CQ-015` | **behavioural** | **implement — gated on Q8.** One `build_listings_context()` serving both views; 20 shared keys on both, 6 search-only keys stay search-only | **14** | MEDIUM (execution risk MEDIUM) | The 11-field DTO build and the 20-key context are verified duplicates, and `listings.py`'s context is a **strict subset** of `search.py`'s — one template contract expressed twice. Zero intended behaviour change, the largest mechanical diff in the report, and ~10 test files pin the contract from both sides. One-key-per-line reformatting of the context is a **consequence**, not a finding |
| `CQ-016` | **mechanical** | **implement — deletion only, gated on Q5.** 6 named symbols + the 3 `RESOLVED_*_PREFIX` aliases + the empty `apps/api/` tree + the vestigial `if TYPE_CHECKING: pass` | **8** | LOW | Safest batchable item in the report: every symbol is single-occurrence across the whole repo. The one caveat is Q5 — the aliases carry an explicit "external callers" comment, and project rule 2 says the code is king over the comment **only after** that is asked. `can_publish_ad` is **phase 15's `AUTHZ-005`** and is not touched |
| `CQ-017` | **mechanical** | **implement sub-claims 1 and 2.** Add `apps/ads/services/__init__.py`; drop `"_get_ad_status"` from `orm.py`'s `__all__`. **Sub-claim 3 (the `AdvisoryLockId` reorder) is de-scoped** (§6) | **2** | LOW | The missing `__init__.py` is the one app in the repo with an implicit namespace `services/`, and **BLOCK 16 adds a module into that package** — so this sub-claim must land before BLOCK 16. The private name in a public export list is a naming contradiction, not dead code: `_get_ad_status` is live |
| `CQ-018` | **split** | **implement all three parts in three different blocks.** BLOCK 5: the URL half (5 `redirect()`s + the template URL) · BLOCK 6: the 7 behaviour-preserving 405 guards → `@require_POST` · BLOCK 7: the `review.py` half (**302 → 405**, gated on Q4), merged with `CQ-003` because both land on `reject_ad`'s request boundary | **5**, **6**, **7** | LOW (LOW / LOW / **MEDIUM** at execution) | Standardise on the **existing** `@require_POST`; do **not** introduce `require_http_methods` (§6). Everything except `reject_ad` / `ban_user` is behaviour-preserving, which is why those two are reviewed individually rather than batched. The **10th** inline method check is `ad_edit`'s GET **dispatch** branch, not a guard — it belongs to BLOCK 16, not BLOCK 6 (C-5) |
| `CQ-019` | **mechanical** | **fold into `CQ-007` (BLOCK 2).** `cache.py` docstrings only. **No tree-wide comment census** (§6) | **2** | LOW | 1,526 comment-only lines of 28,574 (5.3 %) is not a defect, and the comments are overwhelmingly non-obvious design rationale. A tree-wide census is a legacy sweep, which **phase 03 BLOCK 11 explicitly reserves to itself**: *"Phases 04–15 must not start BLOCK 11-style legacy sweeps of their own"* |
| `CQ-002` **login half** | — | **already fixed — not re-filed, not re-shipped** | — | — | Phase 01 `ENT-005` executed the report's own merge instruction and target correction: `_claim_login_token` delegates to `apps.users.services.login_token.claim_token`. **`telegram_bot/services/login.py` must not be created** (C-3) |
| `Q1` / `Q7` | — | **GATED** — Planner + Researcher, with phase 08 consulted for Q1 | **15** | — | Two of the phase's questions sit on one block. A single unresolved answer stops BLOCK 15 from starting. **Q6 is no longer among them — see the next row** |
| `Q6` | — | **RESOLVED 2026-10-03 (Product Owner) — the unified cutoff is 0.8** | **15** | — | Was bundled with Q1/Q7 above. Split out because the ruling is made and its consequence is a **reduction** in risk: `TestFuzzyEquivalence` already asserts 0.8 in-test, so it stays **green unchanged** and **project rule 2 is never invoked**. The 0.6 site (`listings.py::_suggest_category`) aligns to the shared constant. **Q7 remains a Planner gate**, but a surviving `suggest_city` 0.6 must now be **justified against this 0.8 decision** in the commit body |
| `Q2` | — | **RESOLVED 2026-10-03 (Product Owner) — option (b): re-render and preserve the moderator's input** | **7** | — | Routed from phase 15's `Q11`, which owns the moderation surfaces; BLOCK 7 applies the ruling. **The 400 reading is declined**, nothing is coerced to empty, no arbitrary client string reaches `ModeratorActionLog.reason`, and a new user-visible error string requires **non-empty `ru` and `bs`** |
| `Q8` | — | **GATED** — Planner + phase 08, which holds `listings_query.py` | **14** | — | A new module versus one more function in another phase's file |
| `Q4` | — | **GATED** — owner / phase 15 (moderation surfaces). **⚠ Its premise is narrowed by a sibling 2026-10-03 ruling held outside this plan** (GET renders a 200 confirmation page; the action runs only on POST), which supersedes both of its options. This plan does not re-decide it — see BLOCK 7 constraint 12 | **7** | — | Q4 decides what a GET on `reject_ad` / `ban_user` returns. **Check phase 15's `Q8`/`Q12` before treating 302 or 405 as current options** |
| `Q3` | — | **GATED** — Planner; the `ads/edit.html` error slot already exists as the `"error"` context key | **16** | — | 500 versus 400 versus a re-render, with a new i18n string in two of the three options |
| `Q5` | — | **GATED, narrow** — coordinator | **8** | — | One question: does an external consumer import the deprecated aliases? |
| `Q9` / `Q10` / `Q12` / `Q13` / `Q14` | — | **GATED** — Planner, with an owner input for Q12's response shape | **3**, **5**, **4**, **1**, **9** | — | Style, mechanism, module placement and compatibility questions. Each is cheap, but each sets a precedent, and a precedent set silently by an implementor is a precedent nobody reviewed |
| `Q11` | — | **ROUTED** — coordinator | — | — | The `QLT-###` ↔ `10-CQ-0NN` vocabulary collision in three shipped files. Phase 03 BLOCK 11 reserves the in-source ID sweep; phase 10 writes no marker and sweeps none |

**Block classification summary:** `mechanical` = **1, 2, 3, 5, 6, 8, 12, 13** ·
`behavioural` = **4, 7, 9, 10, 11, 14, 15, 16**.

---

## 3. Execution blocks

Sixteen blocks. **One Implementor, strictly sequential, one commit per block** (§1.3).
The numbering *is* the serial order, and the order is chosen so that **each contended file
is written by exactly one phase-10 block per run**, mechanical first and structural last:

```
consent.py      1 ──▶ 8            review.py     5 ──▶ 7 ──▶ 12 (import line only)
context_proc.   1 ──▶ 9            review.html   5 ──▶ 7
cache.py        2 ──▶ 9            alerts.py    10 ──▶ 11
save_search.py  3 ──▶ 4            enums.py      3 only
ads/services/   2(__init__) ──▶ 16(edit_ad.py)   submission.py  16 only
```

Twelve blocks carry a labelled **decision required before implementation** gate or an
external gate. **A gated block does not start until the answer is written down; the
Implementor is forbidden from choosing an option** (§1.3, §8.1).

---

### BLOCK 1 — Relocate the consent-cookie constants (CQ-013)

| | |
|---|---|
| **Findings owned** | `CQ-013` (LOW, `DOC-UPDATE`) |
| **Class** | **mechanical** — a pure relocation; names and values byte-identical |
| **Depends on** | nothing in-plan |
| **Blocks** | BLOCK 8 (`is_consent_given` deletion from the same file), BLOCK 9 (`context_processors.py` annotation) |
| **Priority** | P2 — cheapest fix-to-risk ratio in the report; do it first to prove the serial contract |
| **Risk level** | **LOW** execution risk; ~40 pinned assertions across 5 test files |
| **Required agents** | **Auditor · Planner.** Researcher not required. No separate Validator (mechanical), but the fast gate must be green |

**Decision required before implementation — Q13: where do the four `CONSENT_*` names live?**

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | Move them **into** `apps/core/middleware/preferred_city.py`, beside `PREFERRED_CITY_COOKIE_NAME` / `_MAX_AGE` | **Gains:** zero new artifacts — it is literally the relocation the report calls for, and `consent.py` + `preferred_city.py` already import from that module, so the import graph does not change. **Costs:** the module's subject becomes "cookie constants" rather than "the preferred-city middleware", and the file grows a second responsibility |
| **(b)** | Create `apps/core/cookies.py` and move **all** cookie-name and max-age constants there, including the two `PREFERRED_CITY_*` names | **Gains:** one honest home for cookie constants; a future cookie does not have to be added to a middleware. **Costs:** a **new module** for six constants and one consumer pair — project rule 5 ("avoid overengineering", "no new abstractions without strong justification") argues against it at this size, and it touches `preferred_city.py`'s own import surface |
| **(c)** | Leave the constants in `consent.py` and import them from there at the read sites | **Gains:** smallest diff. **Costs:** inverts the dependency — `context_processors.py` and `search/views/preferred_city.py` would import from a **view** module. The report's whole point is that the definition site is wrong |

**The Implementor may not choose.** BLOCK 1 is the first block in the plan and the cheapest
place to establish that a gate is respected.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/core/middleware/preferred_city.py` | `PREFERRED_CITY_COOKIE_NAME`, `PREFERRED_CITY_COOKIE_MAX_AGE` | Read-only unless Q13 option (a) or (b) is chosen |
| `src/backend/apps/users/views/consent.py` | the `CONSENT_COOKIE_NAME` / `CONSENT_ANALYTICS_COOKIE` / `CONSENT_PREFERENCES_COOKIE` / `CONSENT_TIMESTAMP_COOKIE` / `CONSENT_COOKIE_MAX_AGE` declarations | **The definitions move or are re-exported; the values do not change** |
| `src/backend/apps/users/context_processors.py` | `consent_state`, `consent_version`, `_ACTED_COOKIE_VALUES` | The four raw reads become named imports |
| `src/backend/apps/search/views/preferred_city.py` | `set_preferred_city` | The single raw `"consent_preferences"` read becomes a named import |

**Binding constraints**

1. **Cookie names and max-ages are byte-identical.** A rename silently breaks anonymous
   consent state for every returning visitor and is invisible until users re-consent.
2. **No cookie is renamed, re-pathed, re-aged or re-attributed.** This block is a
   relocation, nothing else. If a name looks wrong, that is a separate decision.
3. **Do not add a cookie-constants framework, a `StrEnum` for cookie names, or a
   request/response helper.** One home for the names is the finding; the rest is §6.
4. **`consent_state` and `consent_version` must keep returning the same booleans.**
   `test_consent_context.py` asserts the processor's output for every cookie combination.
5. **This file has a second owner in this plan** (BLOCK 8 deletes `is_consent_given` from
   it). Re-read it immediately before editing; if another agent has uncommitted changes
   here, **stop and report**.

**Implementor task**

```yaml
id: task_10_b01_consent_cookie_constants
title: "Relocate the consent cookie constants (10-CQ-013)"
priority: medium
depends_on: []
source_reference: ".ai/plans/10-code-quality-remediation.md"
source_section: "BLOCK 1 - Relocate the consent-cookie constants"
source_blocks: ["BLOCK 1"]
description: >
  Four CONSENT_* cookie names are declared in apps/users/views/consent.py and read back as
  raw string literals in four places in apps/users/context_processors.py and once in
  apps/search/views/preferred_city.py. A rename of any of them would silently break
  anonymous consent state. The repository already has the remedy pattern: the two
  PREFERRED_CITY_COOKIE_* constants live in apps/core/middleware/preferred_city.py and are
  imported by both consumers. Move the four names to the Q13 destination and import them at
  every read site. Values and names are unchanged by contract.
goals:
  - "remove every raw consent cookie-name literal from the read sites"
  - "keep every cookie name, value and max-age byte-identical"
  - "introduce no new abstraction beyond the single relocation the Q13 option names"
files:
  - path: "src/backend/apps/core/middleware/preferred_city.py"
    targets:
      - type: module
        name: preferred_city
      - type: assignment
        name: PREFERRED_CITY_COOKIE_NAME
  - path: "src/backend/apps/users/views/consent.py"
    targets:
      - type: function
        name: consent_view
    semantic_anchors:
      insert_before:
        type: assignment
        value: CONSENT_COOKIE_NAME
  - path: "src/backend/apps/users/context_processors.py"
    targets:
      - type: function
        name: consent_state
      - type: function
        name: consent_version
  - path: "src/backend/apps/search/views/preferred_city.py"
    targets:
      - type: function
        name: set_preferred_city
changes:
  - action: modify_code
    description: >
      Move (or re-export, per the Q13 option) the four CONSENT_* declarations to the chosen
      home and replace all five raw read sites with named imports. Do not rename, re-age or
      re-attribute any cookie. Record the Q13 option in the commit body.
acceptance_criteria:
  - "no raw 'consent_given' / 'consent_analytics' / 'consent_preferences' / 'consent_timestamp' literal remains at any read site"
  - "the same cookie names and max-ages are produced as before, verified by the existing consent and preferred-city test suites"
  - "apps/users/tests/test_consent_context.py, test_consent.py and apps/search/tests/test_preferred_city*.py are green UNCHANGED"
  - "apps/users/views/consent.py is otherwise untouched, including the is_consent_given symbol BLOCK 8 will delete"
  - "the commit body names the Q13 option and the destination module"
tests_to_run:
  - "src/backend/apps/users/tests/test_consent_context.py"
  - "src/backend/apps/users/tests/test_consent.py"
  - "src/backend/apps/search/tests/test_preferred_city.py"
  - "src/backend/apps/search/tests/test_preferred_city_readback.py"
```

**Tests required** — none new. This block adds a relocation and inherits the strongest
existing coverage in the report (~40 assertions pinning names and values across five files).
The only new assertion permitted is a negative one: a grep-level check is not a test, so do
not write one.

**Risk and rollback**
- *Implementation risk:* Q13 is answered implicitly. Mitigation: the gate; the commit body
  must name the option.
- *Rollout risk:* none — no response, cookie attribute or path changes.
- *Regression risk:* a stale re-export keeps the definition duplicated. Mitigation: binding
  constraint 3 — one home, not two.
- *Cross-phase:* phase 01 (`ENT-005`) owns `consent.py`'s size; phase 06 BLOCKS 9/10/11/13
  own the **service** layer, not these constants. Neither is a collision, but both mean
  `consent.py` is not quiet.
- *Rollback:* a straight revert. Zero data, zero schema, zero user-visible effect.

---

### BLOCK 2 — Packaging, export and docstring hygiene (CQ-017.1, CQ-017.2, CQ-007, CQ-019)

| | |
|---|---|
| **Findings owned** | `CQ-017.1`, `CQ-017.2` (LOW, `SPEC-DEVIATION`); `CQ-007` (LOW); `CQ-019` (folded in, LOW) |
| **Class** | **mechanical** — an empty file, one list entry, and docstrings |
| **Depends on** | nothing in-plan |
| **Blocks** | **BLOCK 16** adds `edit_ad.py` into the package that gets its `__init__.py` here |
| **Priority** | P2 |
| **Risk level** | **LOW** |
| **Required agents** | **Auditor · Planner.** No separate Validator |

**Why one block.** The three edits share a single property — *no behaviour changes, one
commit, one reviewer, no decision gate* — and `CQ-019` has no home of its own. Folding them
is exactly the "avoid unnecessary task fragmentation" instruction; splitting them would buy
three reviews of three trivial diffs.

**File surface (semantic units)**

| File | Symbol / target | Change |
|---|---|---|
| `src/backend/apps/ads/services/__init__.py` **(new, empty)** | — | Add it. The package has five modules and no `__init__.py`, the only app in the repo with an implicit namespace `services/` |
| `src/telegram_bot/services/ad_data/orm.py` | the `__all__` list, entry `"_get_ad_status"` | Remove the entry. **Do not rename or remove `_get_ad_status`** — it is live, re-exported at `ad_data/__init__.py` and imported by `handlers/ad_create/entry.py` |
| `src/backend/apps/core/utils/cache.py` | the module docstring and the 12 one-line `cache.get` / `cache.set` / `cache.delete` wrappers (`get_cached_criteria`, `set_cached_criteria`, `invalidate_cached_criteria`, `_site_config`, `_bot_username`, `_support_contacts`, the `anon_language` trio) | Trim docstrings that restate the signature; fix the stale module docstring (it says "ModerationCriteria" and now covers four caches). **Function names, keys, TTLs and bodies are unchanged** |
| `src/backend/apps/core/enums.py` | `AdvisoryLockId` | **Not touched** — sub-claim 3 is de-scoped (§6, C-7) |

**Binding constraints**

1. **No `CacheEntry`, no cache-service class, no key parameterisation.** Every key and TTL is
   already a module-level `Final` used as a default argument; the duplication is docstring
   boilerplate, not logic. A helper class over 12 one-line wrappers is pure indirection.
2. **No logger is added to `cache.py`.** Three of the seven modules in `apps/core/utils/`
   have none, and a get/set/delete wrapper does not need one.
3. **`_get_ad_status` stays.** Only the `__all__` entry goes.
4. **No tree-wide comment census and no docstring sweep outside `cache.py`.** Phase 03
   BLOCK 11 reserves the in-source sweep and forbids other phases from starting it.
5. **`ruff check --fix` is scoped to the files this block edits** (§1.2). Reordering an
   untouched file's imports because a blanket `--fix` ran over `src/` is a rule violation.

**Implementor task**

```yaml
id: task_10_b02_packaging_hygiene
title: "Package, export and docstring hygiene (10-CQ-017, 10-CQ-007, 10-CQ-019)"
priority: medium
depends_on: []
source_reference: ".ai/plans/10-code-quality-remediation.md"
source_section: "BLOCK 2 - Packaging, export and docstring hygiene"
source_blocks: ["BLOCK 2"]
description: >
  apps/ads/services/ is the only app-level services package in the repository with no
  __init__.py, and a new module is about to land in it. telegram_bot/services/ad_data/orm.py
  declares __all__ containing the private name "_get_ad_status" while that function is live
  and re-exported. apps/core/utils/cache.py wraps 12 one-line django.core.cache calls under
  8-line docstrings that restate the signature, under a module docstring that still describes
  one of four caches. Fix all three. No behaviour change, no new abstraction, no comment
  census outside this file.
goals:
  - "make apps/ads/services a real package before BLOCK 16 adds a module to it"
  - "remove the private name from the public export list without removing the function"
  - "trim redundant docstrings and correct the stale cache module docstring"
files:
  - path: "src/backend/apps/ads/services/__init__.py"
    targets:
      - type: module
        name: __init__
  - path: "src/telegram_bot/services/ad_data/orm.py"
    targets:
      - type: assignment
        name: __all__
  - path: "src/backend/apps/core/utils/cache.py"
    targets:
      - type: function
        name: get_cached_criteria
      - type: function
        name: invalidate_cached_criteria
      - type: module
        name: cache
changes:
  - action: add_file
    description: "Create the empty apps/ads/services/__init__.py. Re-export nothing."
  - action: modify_code
    description: >
      Drop the "_get_ad_status" entry from orm.py's __all__. Leave the function, its
      decorator and its re-export in ad_data/__init__.py untouched.
  - action: modify_code
    description: >
      Trim the boilerplate docstrings on the 12 one-line cache wrappers to one line or less
      where the signature is self-describing, and correct the module docstring so it
      describes all four caches. No signature, body, key or TTL changes.
acceptance_criteria:
  - "apps/ads/services imports as a regular package and every existing module in it still imports"
  - "_get_ad_status is still importable from ad_data and is still used by handlers/ad_create/entry.py"
  - "no cache.py function signature, cache key, TTL or body changed"
  - "the cache module docstring names all four caches it provides"
  - "no file outside this block's list was modified, and AdvisoryLockId was NOT reordered"
  - "uv run ruff check src/ and uv run basedpyright src/ are green"
tests_to_run:
  - "src/backend/apps/core/tests"
  - "src/backend/apps/ads/tests"
  - "src/telegram_bot/tests"
```

**Tests required** — none new. Every `cache.py` wrapper is exercised indirectly through
`ModerationCriteria.get_singleton()`, `site_config`, the `repair_bot_username` command and
the bot's language middleware; the package's consumers are exercised by the ads and bot
suites. A test asserting the *absence of a docstring* is trivia and is forbidden (§1.5).

**Risk and rollback**
- *Implementation risk:* "cleanup" expanding into a cache-service refactor. Binding
  constraints 1 and 2; `CacheEntry` is §6.
- *Regression risk:* the new `__init__.py` accidentally re-exporting something and creating an
  import cycle. Keep it empty — that is why it is a separate, explicit instruction.
- *Contention:* `core/enums.py` is **not** edited here, which is the point (C-7).
- *Rollback:* a straight revert, twice if needed (delete the file, revert the two edits).

---

### BLOCK 3 — Locale literals in place, and the false invariant they contradict (CQ-006)

| | |
|---|---|
| **Findings owned** | `CQ-006` (MEDIUM, `SPEC-DEVIATION`) |
| **Class** | **mechanical** — `LanguageLocale.X.value` substitution; the values on the wire are unchanged |
| **Depends on** | nothing in-plan |
| **Blocks** | nothing; but it is the **only** block in this plan permitted to edit `core/enums.py` |
| **Priority** | P1 — highest closed-literal count per diff line in the report |
| **Risk level** | **LOW–MEDIUM** — the widest file count (10) and the FTS pairings are pinned by tests |
| **Required agents** | **Auditor · Researcher · Planner · Validator.** The Researcher re-measures the literal census; the Validator confirms the FTS pairings and the bot translation path |

**Decision required before implementation — Q9: how do `fts_config` and `fts_vector_field` stop being raw dicts?**

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | `match self: case …: return "russian"` arms | **Gains:** no mapping object, no import, exhaustiveness is visible to the reader and a new member forces an editor to think. **Costs:** two `match` statements in an enum body; a value that is not one of the arms raises nothing at type-check time |
| **(b)** | `Final` class-level mappings on `LanguageLocale` | **Gains:** a single declarative table, easy to diff. **Costs:** `StrEnum` members are defined in the same class body, so a class-level dict referencing those members needs a forward reference or a post-class assignment — a real construction-order trap, and the *same* kind of raw-string-keyed structure the finding is about |
| **(c)** | Leave the two properties alone and correct only the module docstring | **Gains:** smallest diff. **Costs:** leaves **6 of the ~16 literals** in place and leaves the module's own docstring still contradicted by its own body. This is a real partial option, not a strawman |

**The Implementor may not choose**, because the choice becomes the precedent for every enum
in the repository.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/core/enums.py` | the module docstring, `LanguageLocale.fts_config`, `LanguageLocale.fts_vector_field` | **Only block in this plan that may edit this file.** Re-read immediately before editing — it carries uncommitted phase-02 work (`REPAIR_BOT_USERNAME = 13`) |
| `src/backend/apps/categories/models.py` · `apps/locations/models.py` · `apps/lookups/models.py` | each `get_name` | The identical `if "ru" in name_i18n:` triplication, three times |
| `src/backend/apps/search/services/entity_suggestions.py` | the locale→name call | |
| `src/backend/apps/search/models.py` | `SavedSearch.language` (`default="bs"`, `help_text` already names `LanguageLocale`) | **A `default=` change is a migration surface — see binding constraint 3** |
| `src/backend/apps/search/views/save_search.py` | the `request.LANGUAGE_CODE or "bs"` fallback | BLOCK 4 re-reads this file |
| `src/backend/apps/categories/views.py` | the submenu cache key `… or 'ru'` | **Missed by the report** |
| `src/backend/apps/ads/management/commands/backfill_translations.py` | the four raw literals | Phase 03 owns bootstrap legacy sweeps; this is a four-token substitution, not a sweep |
| `src/telegram_bot/handlers/ad_create/submit.py` | the six `.get("ru"/"bs"/"en")` calls building `SubmitAdInput` translations | The largest cluster, on the bot's publish path. Phase 02 (in flight), phase 05 BLOCK 11 and phase 07 BLOCKS 7/12 also name this file |

**Binding constraints**

1. **Every wire value is unchanged.** The database still stores `"ru"`, `"bs"`, `"en"`. The
   FTS config↔column pairings (`ru→russian`/`search_vector_ru`, `bs→simple`/`search_vector_bs`,
   `en→english`/`search_vector_en`) are pinned by `test_search_triggers.py` and
   `test_setup_search_triggers.py` and must remain exactly so.
2. **No `apps/core/services/locales.py`.** `LanguageLocale` already exposes `.values()`,
   `.from_code()`, `.fts_config` and `.fts_vector_field`. A wrapper module is a hop with no
   consumer.
3. **`SavedSearch.language`'s `default` must not become a migration.** If option (a)/(b) makes
   the default reference a member, confirm `makemigrations --check` is clean afterwards; if it
   is not, use `LanguageLocale.BOSNIAN.value` (or the correct member) as the default **without**
   a model change, or escalate. **This plan ships no migration.**
4. **The module docstring must be corrected in the same commit.** "No inline string literals
   for constants anywhere in the codebase" is false, and it is false **inside the same file**.
5. **Re-read `core/enums.py` immediately before editing.** If another agent's uncommitted
   change is present, **stop and report**. Never stage by directory.
6. **No lock id is allocated and `AdvisoryLockId` is not reordered** (C-7, §6).

**Implementor task**

```yaml
id: task_10_b03_locale_literals
title: "Replace raw locale literals with LanguageLocale members (10-CQ-006)"
priority: high
depends_on: []
source_reference: ".ai/plans/10-code-quality-remediation.md"
source_section: "BLOCK 3 - Locale literals in place"
source_blocks: ["BLOCK 3"]
description: >
  LanguageLocale exists to prevent exactly this and is ignored at 10 file-sites. Replace
  every raw "ru" / "bs" / "en" literal with the enum member or its .value, replace the two
  raw-string-keyed dicts inside LanguageLocale itself according to the recorded Q9 option,
  and correct the module docstring that claims the codebase has no inline constants. Every
  persisted and transmitted value must be byte-identical.
goals:
  - "close every raw locale literal named in the finding, including the two sites the report missed"
  - "keep every stored, rendered and transmitted locale value byte-identical"
  - "fix the two raw dicts inside the enum that exists to prevent them"
files:
  - path: "src/backend/apps/core/enums.py"
    targets:
      - type: class
        name: LanguageLocale
      - type: property
        name: fts_config
      - type: property
        name: fts_vector_field
  - path: "src/backend/apps/categories/models.py"
    targets: [{type: method, name: get_name}]
  - path: "src/backend/apps/locations/models.py"
    targets: [{type: method, name: get_name}]
  - path: "src/backend/apps/lookups/models.py"
    targets: [{type: method, name: get_name}]
  - path: "src/backend/apps/categories/views.py"
    targets: [{type: module, name: views}]
  - path: "src/backend/apps/search/models.py"
    targets: [{type: class, name: SavedSearch}]
  - path: "src/backend/apps/search/services/entity_suggestions.py"
    targets: [{type: module, name: entity_suggestions}]
  - path: "src/backend/apps/search/views/save_search.py"
    targets: [{type: function, name: save_search}]
  - path: "src/backend/apps/ads/management/commands/backfill_translations.py"
    targets: [{type: module, name: backfill_translations}]
  - path: "src/telegram_bot/handlers/ad_create/submit.py"
    targets: [{type: module, name: submit}]
changes:
  - action: modify_code
    description: >
      Substitute LanguageLocale member references (or .value where a string is required) at
      every named site, rewrite fts_config and fts_vector_field per the Q9 option, and
      correct the enums.py module docstring. Record the Q9 option in the commit body.
acceptance_criteria:
  - "no raw 'ru' / 'bs' / 'en' literal remains at any of the 10 named file-sites"
  - "apps/ads/tests/test_search_triggers.py and test_setup_search_triggers.py are green UNCHANGED - the three config-to-column pairings are identical"
  - "apps/categories/tests/test_submenu.py, test_submenu_swr.py and apps/ads/tests/test_i18n_category_city.py are green UNCHANGED"
  - "src/telegram_bot/tests/test_multi_lang_translation.py and test_ad_data_locale.py are green UNCHANGED"
  - "makemigrations --check reports no changes; no migration was created"
  - "AdvisoryLockId is byte-identical and no lock id was allocated"
  - "the commit body names the Q9 option"
tests_to_run:
  - "src/backend/apps/ads/tests/test_search_triggers.py"
  - "src/backend/apps/ads/tests/test_setup_search_triggers.py"
  - "src/backend/apps/categories/tests"
  - "src/backend/apps/search/tests/test_autocomplete.py"
  - "src/backend/apps/ads/tests/test_i18n_category_city.py"
  - "src/telegram_bot/tests/test_multi_lang_translation.py"
  - "src/telegram_bot/tests/test_ad_data_locale.py"
```

**Tests required**
1. **The positive control** — a category, city and lookup with a three-locale `name_i18n`
   still resolve their Russian, Bosnian and English names identically, through all three
   `get_name` implementations.
2. **The bot path** — a submitted ad's three translation fields are populated exactly as
   before, and a missing key still yields the same fallback (this is the behaviour a
   `.get("ru")` chain encodes, and a naive "index it" rewrite would break it).
3. **The cache key** — the submenu cache key built with the `'ru'` fallback is byte-identical
   for a request whose `LANGUAGE_CODE` is empty, and distinct from a `bs` request.
4. **The FTS pairings** — the existing trigger tests are the assertion; no new one is needed
   and a new one asserting a literal dict is trivia.

**Risk and rollback**
- *Implementation risk:* an aggressive rewrite that turns `.get("ru")` into indexing and
  raises on a missing key. Mitigation: binding constraint 2 plus test 2.
- *Regression risk:* `SavedSearch.language`'s default changing behaviour. Mitigation:
  constraint 3 plus `makemigrations --check`.
- *Contention:* `core/enums.py` (5 phases), `telegram_bot/handlers/ad_create/submit.py`
  (phases 02/05/07), `search/views/save_search.py` (BLOCK 4 next). Re-read before each.
- *Rollback:* a straight revert. No data movement, no migration.

---

### BLOCK 4 — One Pydantic boundary for the saved-search POST (CQ-004)

| | |
|---|---|
| **Findings owned** | `CQ-004` (MEDIUM, `BEST-PRACTICE`), `CQ-004`'s reproduction rewritten |
| **Class** | **behavioural** — introduces a response shape nobody has decided |
| **Depends on** | BLOCK 3 (same file, `save_search.py`) |
| **Blocks** | nothing in-plan |
| **Priority** | P1 |
| **Risk level** | **MEDIUM** — a new failure path on a user-facing POST; phase 08 owns `apps/search/models.py` and the next `search/migrations/0003` |
| **Required agents** | **Auditor · Researcher · Planner · Validator** |

**Decision required before implementation — Q12: where does `SavedSearchInput` live, and what
does a rejected POST return?**

*Placement*

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | New `src/backend/apps/search/schemas.py`, matching `apps/media/schemas.py`, `apps/users/schemas.py` and `telegram_bot/schemas/` | **Gains:** the repo convention; a second DTO can join it without inventing a home. **Costs:** one new file for one class today |
| **(b)** | Add it to `apps/core/schemas.py` beside `BaseInputModel` | **Gains:** no new file. **Costs:** `apps/core` is not where a search-app DTO belongs, and it puts app-specific fields in the shared base module |
| **(c)** | Keep it local to `apps/search/views/save_search.py` | **Gains:** smallest diff; the cabinet view would import from another view. **Costs:** reintroduces exactly the duplication the finding is about |

*Response shape*

| Option | What it is | Consequences |
|---|---|---|
| **(i)** | **400** on a validation error | **Gains:** least surprising, consistent with `set_preferred_city`, no new template slot, no new i18n string. **Costs:** the save-search UI is a modal on the search page — a bare 400 loses the user's query and filters with no way back |
| **(ii)** | Re-render the save-search modal with an error message | **Gains:** the user keeps their query. **Costs:** a new user-visible string (non-empty `ru` **and** `bs`), a new context key, and a decision about which template owns the error — the modal is shared with the search page, which is phase 08's surface |
| **(iii)** | Clamp/ignore the invalid value and store the rest | **Gains:** no new response shape. **Costs:** silently accepts a malformed filter — the exact class of defect `CQ-004` is filed for |

**The Implementor may not choose.** Option (i) is the cheapest and the most defensible;
option (ii) is the most user-respecting and the most expensive; option (iii) is a
regression dressed as a fix.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/search/schemas.py` **(new, if Q12(a))** | `SavedSearchInput` | `BaseInputModel` subclass — the established base, carrying `extra="forbid"` (the same convention `test_listings_query_params_rejects_unknown_key` pins) |
| `src/backend/apps/search/views/save_search.py` | `save_search`, the `_int_or_none` closure, the inline method guard | **Delete the closure.** Keep the view function **named `save_search`** — `test_save_search_url_resolves` asserts `resolve(url).func.__name__ == "save_search"` |
| `src/backend/apps/cabinet/views/saved_searches.py` | `_apply_filters`, the byte-identical `_int_or_none` closure, `saved_search_edit` | **Delete the second copy.** Its inline POST guard is BLOCK 6's, not this block's |
| `src/backend/apps/search/tests/test_saved_search_create.py` | existing cases | Must stay green: int coercion of prices, `language == "en"` from `request.LANGUAGE_CODE`, login required |
| `src/backend/apps/cabinet/tests/` | a new negative case | **No test exists today for the cabinet path or for a negative price** |

**Binding constraints**

1. **The reproduction in the tracker must be rewritten before the fix lands.** There is no
   `IntegrityError` and no 500; `min_price=-1` is silently persisted (C-12). A commit
   justified by a bug that does not exist is a review failure.
2. **Positive behaviour is byte-identical:** prices land as `int`, `language` still uses the
   `request.LANGUAGE_CODE or "bs"` fallback, and the view name stays `save_search`.
3. **`PreferredCityInput` is NOT built** (§6). `set_preferred_city` already validates with an
   explicit existence query, already returns 400 with a documented reason, already has
   `@require_POST`, and already owns its cookie constants. A Pydantic wrapper there is a
   layer with no defect behind it.
4. **No migration.** `ge=0` lives on the DTO, not on the model. Do not add a
   `CheckConstraint`, a `MinValueValidator` or an `AlterField`.
5. **Both copies of `_int_or_none` go in the same commit.** A fix that leaves one is not a fix.
6. **No AST architecture test.** A rule that must first be made true cannot be enforced
   before it is true, and the `request.POST` + `save()` delegate pattern in
   `moderation/views/review.py` would fail it anyway (§6).
7. **No new i18n string unless Q12(ii) is chosen.** If it is, `ru` and `bs` `msgstr` are
   non-empty and the catalogue is **appended**, never regenerated.

**Implementor task**

```yaml
id: task_10_b04_saved_search_dto
title: "Put one Pydantic boundary in front of the saved-search POST (10-CQ-004)"
priority: high
depends_on: [task_10_b03_locale_literals]
source_reference: ".ai/plans/10-code-quality-remediation.md"
source_section: "BLOCK 4 - One Pydantic boundary for the saved-search POST"
source_blocks: ["BLOCK 4"]
description: >
  save_search and saved_searches._apply_filters each carry a byte-identical _int_or_none
  closure and write the result straight into SavedSearch.objects.create. There is no
  PositiveIntegerField DB check constraint, so min_price=-1 is silently persisted - the row
  is created and can never match. Add a SavedSearchInput DTO at the request edge with
  non-negative price bounds, delete both closures, and return the Q12-recorded response on
  a validation error. The view function name must stay save_search.
goals:
  - "reject a negative price at the boundary instead of persisting it"
  - "delete both byte-identical _int_or_none copies in one commit"
  - "keep every positive-value path byte-identical, including the language fallback"
  - "ship no migration and no PreferredCityInput DTO"
files:
  - path: "src/backend/apps/search/views/save_search.py"
    targets: [{type: function, name: save_search}]
  - path: "src/backend/apps/cabinet/views/saved_searches.py"
    targets: [{type: function, name: _apply_filters}]
  - path: "src/backend/apps/search/schemas.py"
    targets: [{type: class, name: SavedSearchInput}]
changes:
  - action: add_code
    description: >
      SavedSearchInput(BaseInputModel) with ge=0 bounds on min_price and max_price, int
      coercion preserved, and the language field defaulting from request.LANGUAGE_CODE.
  - action: modify_code
    description: >
      Validate the POST through the DTO in both views; delete both _int_or_none closures;
      return the Q12 response shape on failure. Keep the view named save_search.
acceptance_criteria:
  - "a POST with min_price=-1 or max_price=-1 is refused and NOTHING is created"
  - "a POST with positive prices stores ints and the saved search still matches the same ads"
  - "test_saved_search_url_resolves still passes - the view function is still named save_search"
  - "the language still comes from request.LANGUAGE_CODE with the documented fallback"
  - "no _int_or_none closure remains in either view"
  - "makemigrations --check is clean; no migration was created; no CheckConstraint was added"
  - "PreferredCityInput was NOT added"
  - "the commit body names the Q12 placement and response options"
tests_to_run:
  - "src/backend/apps/search/tests/test_saved_search_create.py"
  - "src/backend/apps/cabinet/tests"
```

**Tests required**
1. **The refused case** — a negative bound on either end creates no row at all, asserted
   through the **view**, not through the DTO alone. Assert on the absence of danger.
2. **The positive control** — a valid POST stores `int` prices, and a saved search built from
   them still returns the same ads through the alert and the search view.
3. **The cabinet path** — the same bound applies to the **edit** form, which has no test today.
   Without it, one of the two deleted closures could have been behaviourally load-bearing.
4. **The unknown-key case** — a POST carrying a key the DTO does not declare is refused under
   `extra="forbid"`, matching the `ListingsQueryParams` convention.

**Risk and rollback**
- *Implementation risk:* a DTO that rejects something the old hand-rolled parser accepted
  (a blank price, a `Decimal`-formatted string). Mitigation: tests 2 and 4, and the
  `test_saved_search_create.py` suite is already the positive control.
- *Rollout risk:* Q12(i) returns a bare 400 from a modal-driven UI. That is the accepted
  cost of the cheapest option and must be named in the commit body.
- *Compatibility:* positive values are unchanged; no stored row is rewritten.
- *Cross-phase:* phase 06 owns `SavedSearch` **retention and erasure** semantics; phase 08
  BLOCKS 5/8 own `apps/search/models.py` and `SavedSearch.query`'s bound. This block edits
  **neither** the model nor the query field.
- *Rollback:* a straight revert. Previously-persisted negative values are untouched by the
  revert and remain a data-quality question, not a code one — say so in the commit body.

---

### BLOCK 5 — `AdStatus` out of templates, and the hardcoded admin URL (CQ-005 + CQ-018's URL half)

| | |
|---|---|
| **Findings owned** | `CQ-005` (MEDIUM, `SPEC-DEVIATION`); `CQ-018`'s URL half |
| **Class** | **mechanical** — 0 Python `AdStatus` sites; the substitution is semantically neutral under `StrEnum` |
| **Depends on** | nothing in-plan (Q10 must be answered first) |
| **Blocks** | BLOCK 7 reuses the same mechanism and the same `review.html` file |
| **Priority** | P1 |
| **Risk level** | **LOW–MEDIUM** — a template surface plus a context key; `djlint templates/` is a CI gate |
| **Required agents** | **Auditor · Planner · Validator** — the Validator confirms each template renders byte-identically |

**Why these two findings are one block.** `analytics/moderation_dashboard.html` contains
**one line that is both a `CQ-005` status literal and a `CQ-018` hardcoded `/admin/` URL**
(`?status__exact=on_moderation` inside a literal path). The report files it twice and
under-counts both. Fixing them separately means editing the same template line in two
commits, and the second one has to understand the first one's change.

**Decision required before implementation — Q10: how is the value exposed to templates?**

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | A key in `apps/core/context_processors.py`, beside `price_step` | **Gains:** exactly the pattern the repo already ships (`price_step` returns the `PriceStep.DEFAULT` **member** so templates write `step="{{ price_step.value }}"`), and its sibling `consent_version` docstring names the pattern explicitly. One key serves `AdStatus` **and** the CQ-018 admin URL **and** CQ-003's enum options. **Costs:** the key is present in **every** template's context; a per-page key is narrower |
| **(b)** | A per-view context key (`ads/views/dashboard.py` already builds `status_labels`; `analytics`' moderation dashboard is the other consumer) | **Gains:** narrower blast radius; `status_labels` is the existing, correct reference model for badge text. **Costs:** two views to wire, and the admin URL still needs a *third* mechanism for `review.py`'s five `redirect()`s — which are Python and are fixed with `reverse()`, not with a context key |
| **(c)** | A template tag or filter | **Gains:** nothing the two above do not. **Costs:** a new template-tag library, forbidden by §1.4 |

**The Implementor may not choose.** Option (a) is the only one that also covers CQ-003
cleanly, which is why it is listed first — not because it is decided.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/templates/analytics/moderation_dashboard.html` | the hardcoded admin link with `?status__exact=on_moderation` | **The strongest single site in the finding**: the literal is *inside a URL* and cannot be fixed with `reverse()` in the view |
| `src/backend/templates/ads/dashboard.html` | the published/archive-button block, the archived/reactivate-button block, the "action required" block, the pending-review block, and the five-term empty-state condition (9 occurrences) | `status` in the loop is already the `AdStatus` **member** — the literals are redundant, not broken |
| `src/backend/templates/admin/moderation/review.html` | the status-badge block, the publish-gate block, the "fail" branch (6 occurrences) | **Also BLOCK 7's file.** Re-read before BLOCK 7 |
| `src/backend/templates/ads/edit.html` | the archived-status banner (1 occurrence) | **Missed entirely by the report.** Phase 07 BLOCK 10 is docstrings only and does not reach this template |
| `src/backend/apps/core/context_processors.py` | the `price_step` pattern, beside which the new key sits | Read-only unless Q10(a) |
| `src/backend/apps/ads/views/dashboard.py` | `ads_by_status`, `status_labels` | Read-only unless Q10(b) |
| `src/backend/apps/moderation/views/review.py` | the five `redirect(f"/admin/ads/ad/…")` calls | `reverse("admin:ads_ad_change", …)` and `reverse("admin:ads_ad_changelist")` + a query string. **Also BLOCKs 7, 12 and 13's file** |
| `src/backend/apps/analytics/` moderation dashboard view | its render context | Name it before editing; the block's file surface must be semantic |

**Binding constraints**

1. **Every template renders byte-identically.** `test_dashboard_stats.py`, `test_auth_nav.py`,
   `test_moderation_views.py::TestModerationReviewView::test_staff_can_view_review_page` and
   `::test_review_renders_localized_category_name` must be green **unchanged**.
2. **No template tag library and no new template filter** (binding constraint, §1.4).
3. **The admin URL must become a real reverse, not a string.** The `moderation_dashboard.html`
   site cannot use `reverse()` in the template; it takes the URL from the Q10 mechanism.
4. **`admin/moderation/review.html`'s forms must keep submitting to the same endpoints.**
   BLOCK 7 changes the *response* of a GET on two of them; BLOCK 5 changes no endpoint.
5. **`ads/edit.html` is in scope despite being unfiled.** A fix that leaves one status literal
   behind in a template BLOCK 16's function renders is a half-fix.
6. **This block must not touch `edit.py`.** The tenth inline `request.method` comparison is
   `ad_edit`'s GET dispatch branch and belongs to BLOCK 16 (C-5).
7. **`uv run djlint src/backend/templates/` must stay clean** — the CI job uses
   `ignore = "D018,H019,H021,H023,H030"`. A reformat that trips an un-ignored rule is a
   regression, not a cleanup.

**Implementor task**

```yaml
id: task_10_b05_status_templates
title: "Take AdStatus literals and the hardcoded admin URL out of templates (10-CQ-005, 10-CQ-018)"
priority: high
depends_on: []
source_reference: ".ai/plans/10-code-quality-remediation.md"
source_section: "BLOCK 5 - AdStatus out of templates, and the hardcoded admin URL"
source_blocks: ["BLOCK 5"]
description: >
  There are zero AdStatus literals in production Python - every Python site already uses
  AdStatus.X. The 10 real sites are template lines across four templates, and the one in
  analytics/moderation_dashboard.html is inside a hardcoded /admin/ URL. Expose the value
  through the existing core/context_processors.py price_step pattern (Q10) and replace every
  literal, including the archived-status banner in ads/edit.html that the report missed.
  reverse() the five /admin/ redirect() calls in moderation/views/review.py in the same
  commit.
goals:
  - "remove all 10 template status-literal sites, including the one inside a URL"
  - "replace the five hardcoded /admin/ redirect targets with real reverses"
  - "keep every template rendering byte-identical"
files:
  - path: "src/backend/templates/analytics/moderation_dashboard.html"
    targets: [{type: module, name: moderation_dashboard}]
  - path: "src/backend/templates/ads/dashboard.html"
    targets: [{type: module, name: dashboard}]
  - path: "src/backend/templates/ads/edit.html"
    targets: [{type: module, name: edit}]
  - path: "src/backend/templates/admin/moderation/review.html"
    targets: [{type: module, name: review}]
  - path: "src/backend/apps/core/context_processors.py"
    targets: [{type: function, name: price_step}]
  - path: "src/backend/apps/moderation/views/review.py"
    targets: [{type: function, name: approve_ad}]
changes:
  - action: add_code
    description: >
      Expose the AdStatus value and the moderation changelist URL through the Q10 mechanism.
      price_step is the reference pattern: return the enum member, render {{ x.value }}.
  - action: modify_code
    description: >
      Replace every status literal in the four templates and reverse() the five /admin/
      redirect targets. Record the Q10 option in the commit body.
acceptance_criteria:
  - "no quoted AdStatus value remains in any template under src/backend/templates/"
  - "analytics/moderation_dashboard.html's moderation link resolves through the context, not a literal path"
  - "the five /admin/ redirect() targets in moderation/views/review.py are reverse() results"
  - "test_dashboard_stats.py, test_auth_nav.py and TestModerationReviewView are green UNCHANGED"
  - "uv run djlint src/backend/templates/ is clean under the project's ignore list"
  - "no template tag or filter was added, and apps/ads/views/edit.py was NOT touched"
  - "the commit body names the Q10 option"
tests_to_run:
  - "src/backend/apps/ads/tests/test_dashboard_stats.py"
  - "src/backend/apps/ads/tests/test_auth_nav.py"
  - "src/backend/apps/moderation/tests/test_moderation_views.py"
```

**Tests required**
1. **The render equality** — the four templates render with the same content as before for a
   published, an archived, an on-moderation and a pending ad. Assert on the rendered output
   through the **view**, not on a template substring.
2. **The admin link** — the moderation-dashboard link points at the moderation changelist and
   still filters to `on_moderation`; the review view's redirects land on the same two admin
   pages as before.
3. **The negative control** — a status with no badge case still renders the same fallback
   (this is what catches a substitution that silently changes the empty-state condition).

**Risk and rollback**
- *Implementation risk:* the five-term empty-state condition in `ads/dashboard.html` is the
  easiest thing in the block to get wrong, and its failure mode is a **silently empty
  dashboard**. Mitigation: test 3.
- *Rollout risk:* low. `AdStatus` is a `StrEnum`, so the substitution is semantically neutral.
- *Contention:* `review.py` and `review.html` are written by BLOCKs 7, 12 and 13 after this
  one. Re-read before each.
- *Rollback:* a straight revert.

---

### BLOCK 6 — One way to say "POST only" (CQ-018, mechanical half)

| | |
|---|---|
| **Findings owned** | `CQ-018` (LOW) — the 7 behaviour-preserving inline guards |
| **Class** | **mechanical** — every one of the 7 already returns 405 for a non-POST |
| **Depends on** | nothing in-plan |
| **Blocks** | nothing; BLOCK 7 is the behavioural remainder and is independent |
| **Priority** | P2 |
| **Risk level** | **LOW** — a behaviour-preserving swap, but it touches 5 modules |
| **Required agents** | **Auditor · Planner.** No separate Validator |

**File surface (semantic units)** — the 7 guards, by their enclosing function:

| File | Enclosing view | Note |
|---|---|---|
| `src/backend/apps/cabinet/views/saved_searches.py` | the three inline `request.method` guards in the saved-search cabinet views | The same file is BLOCK 4's; re-read |
| `src/backend/apps/cabinet/views/search_history.py` | the inline guard | |
| `src/backend/apps/core/views.py` | the inline guard | |
| `src/backend/apps/moderation/views/decorators.py` | the guard inside the decorator module | This one is a **helper** — check whether `require_POST` applies cleanly to the function it decorates before swapping |
| `src/backend/apps/search/views/save_search.py` | the inline guard | BLOCK 4's file; re-read |

**Explicitly NOT in this block:**

- `apps/moderation/views/review.py::reject_ad` and `::ban_user` → **BLOCK 7** (302 → 405,
  gated on Q4, merged with `CQ-003`).
- `apps/ads/views/edit.py::ad_edit`'s `if request.method == "GET":` **dispatch** branch → this
  is a two-way branch returning the form, not a method guard, and it is inside the most
  contended function in the plan set. **BLOCK 16's**, and it must not be converted to
  `@require_POST` by an implementor working from the report's list.
- `require_http_methods` → **rejected** (§6). It is used **zero** times. Standardise on the
  existing `@require_POST`; do not add a second idiom.

**Binding constraints**

1. **The 7 swaps are behaviour-preserving and must stay so.** Every one already returns
   `HttpResponse(status=405)` for a non-POST. `test_logout.py` and `test_favorites.py`
   document 405s elsewhere; keep them green.
2. **No response-shape change.** `@require_POST` returns Django's own 405; the inline guards
   return a bare 405. If a test asserts on the *body*, that is a change and BLOCK 7's
   territory.
3. **Do not touch `moderation/views/review.py` or `apps/ads/views/edit.py` in this block.**
4. **No template or form change.** A form whose only method is POST is unaffected; a form that
   could submit GET was already broken and is a separate finding.

**Implementor task**

```yaml
id: task_10_b06_require_post
title: "Standardise the POST-only guards on @require_POST (10-CQ-018)"
priority: low
depends_on: []
source_reference: ".ai/plans/10-code-quality-remediation.md"
source_section: "BLOCK 6 - One way to say POST only"
source_blocks: ["BLOCK 6"]
description: >
  Seven views carry an inline `if request.method != "POST": return HttpResponse(status=405)`
  guard that duplicates the existing @require_POST decorator, already applied at 11 sites in
  7 modules. Swap the seven. Do not touch moderation/views/review.py (BLOCK 7 changes a 302
  into a 405 there and needs its own decision) and do not touch apps/ads/views/edit.py
  (BLOCK 16 owns ad_edit). Do not introduce require_http_methods - it is used zero times.
goals:
  - "one decorator expresses POST-only instead of two idioms"
  - "keep every non-POST response at 405"
  - "leave the review.py and ad_edit guards to the blocks that own them"
files:
  - path: "src/backend/apps/cabinet/views/saved_searches.py"
    targets: [{type: module, name: saved_searches}]
  - path: "src/backend/apps/cabinet/views/search_history.py"
    targets: [{type: module, name: search_history}]
  - path: "src/backend/apps/core/views.py"
    targets: [{type: module, name: views}]
  - path: "src/backend/apps/moderation/views/decorators.py"
    targets: [{type: module, name: decorators}]
  - path: "src/backend/apps/search/views/save_search.py"
    targets: [{type: function, name: save_search}]
changes:
  - action: modify_code
    description: >
      Apply @require_POST and delete the inline method guard in each of the seven views.
      The decorator must be imported from django.views.decorators.http.
acceptance_criteria:
  - "a non-POST request to each of the seven views still returns 405"
  - "no inline request.method guard remains in those five modules"
  - "moderation/views/review.py and apps/ads/views/edit.py are byte-identical to before this block"
  - "require_http_methods is still used zero times"
  - "the existing 405 tests are green UNCHANGED"
tests_to_run:
  - "src/backend/apps/cabinet/tests"
  - "src/backend/apps/moderation/tests/test_moderation_views.py"
  - "src/backend/apps/search/tests/test_saved_search_create.py"
```

**Tests required** — none new. Each of the seven already has, or is covered by, a suite that
exercises the POST path; the 405 path is the assertion. A test asserting the presence of a
decorator is trivia and is forbidden (§1.5). If a block's guard turns out **not** to be
  behaviour-preserving, **stop and report** — that is a BLOCK 7-class finding, not a
mechanical swap.

**Risk and rollback**
- *Implementation risk:* a guard that is a **dispatch** rather than a check. The Report
  counts 9 checks; the tree has 10 comparisons and one of them is a dispatch. Mitigation:
  binding constraint 3; the Implementor must name the enclosing function of each swap.
- *Rollout risk:* none if the swaps are genuinely equivalent; the tripwire is the 405 tests.
- *Rollback:* a straight revert.

---

### BLOCK 7 — Make the reject-reason vocabulary a real boundary (CQ-003)

| | |
|---|---|
| **Findings owned** | `CQ-003` (MEDIUM, `SPEC-DEVIATION`); `CQ-018`'s `review.py` half (the 302→405 decision) |
| **Class** | **behavioural** — defines what an invalid POST does, and turns a 302 into a 405 |
| **Depends on** | BLOCK 5 (Q10's mechanism, same `review.html`) |
| **Blocks** | BLOCK 12, whose `review.py` diff is then import-only |
| **Priority** | P1 |
| **Risk level** | **MEDIUM** — changes what a moderator can submit, and what a GET returns |
| **Required agents** | **Auditor · Researcher · Planner · Validator** |

**This block also owns `CQ-018`'s `review.py` remainder.** The two decisions are merged here
deliberately: `reject_ad` is the *same function* that must validate the category (Q2) and
standardise its method guard (Q4), both are moderator-facing, and both are asserted by the
same test class. Two blocks editing one function's request boundary would be a second
serialisation the DAG would have to defend; one block with two gates is simpler and is the
shape plan 08 already uses.

**Q2 RESOLVED 2026-10-03 (Product Owner) — re-render, preserve the input, coerce nothing**

**The ruling is option (b).** An invalid `reason_category` **re-renders the review page with an
error and preserves the moderator's input**. **Nothing is coerced to empty**, and **no arbitrary
client string reaches `ModeratorActionLog.reason`**. The options are retained for traceability;
the Implementor may **not** re-choose, and **option (a) — the 400 — is DECLINED**.

| Option | What it is | Status |
|---|---|---|
| ~~**(a)**~~ | **400** on a value outside the 8 members | **DECLINED 2026-10-03.** The gate row's *"least surprising but not obviously right"* clause is superseded: a bare 400 to a moderator holding a stale page loses their work, and the vocabulary is closed by **validation**, not by a rejection status |
| **(b) — CHOSEN 2026-10-03** | Re-render the review page with an error next to the dropdown, **preserving the text the moderator typed** | **Adopted.** The moderator keeps the ad and their text; the audit row can never contain a category outside the 8 members. **Costs, accepted:** a new user-visible string (**non-empty `ru` and `bs`**), a new context key, and the review page is also BLOCK 5's and **phase 15's** surface |
| ~~**(c)**~~ | Coerce to empty and store the free text only | **DECLINED.** Silently discarding the category is the exact failure the finding is filed for |
| ~~**(d)**~~ | Validate, and on failure fall back to a named "other" member | **NOT CHOSEN.** It would require **adding a member to `CategoryRejectReason`**, a change to the documented 8-value vocabulary in `docs/02-database/db-enums.md` — a data-vocabulary decision the owner did not make. **The vocabulary stays at 8**, and the committee must not widen it in this block |

**Two obligations this ruling creates for BLOCK 7**, both with acceptance criteria below: a
**new user-visible error string** with non-empty `ru` and `bs` in the same commit, and a
**preserved-input assertion** — the re-render must carry the moderator's typed `comment` back
into the form, because a re-render that silently discards it would be a worse defect than the
one being fixed.

**Routing.** The question originated as phase 15's `Q11` and the moderation UX is **phase 15's**;
the ruling is applied here because the code change lands in BLOCK 7. **Propagation obligation on
phase 15**: its `Q11` must be updated to record the same answer, so the moderation-surface owner
does not re-open it.

**Decision required before implementation — Q4: 302 or 405 for a GET on `reject_ad` and
`ban_user`?**

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | `@require_POST` on both; a GET returns **405** | **Gains:** one idiom for all three siblings — `approve_ad` already returns 405 today, so the "intent" is already split. **Costs:** a moderator following a stale bookmarked GET URL gets a 405 instead of the ad's change page. **Two shipped tests change** (`test_reject_requires_post`, `test_ban_requires_post`); project rule 2 applies — the test is updated because the behaviour was **decided**, and the commit body must say so |
| **(b)** | Leave both at 302 and record the asymmetry as accepted | **Gains:** nothing. **Costs:** the finding stays open and the inconsistency stays undocumented |
| **(c)** | Keep the 302 but route it through one shared helper | **Gains:** uniform behaviour, no test churn. **Costs:** a new helper to preserve a behaviour two tests describe as *"redirects rather than rejecting"*, and it leaves the finding open. **A second decorator idiom is forbidden** (§6) |

**The Implementor may not choose.** The evidence is genuinely split: two tests assert a
redirect and their docstrings say *"redirects rather than rejecting"*; the sibling asserts
405 on the same page.

**What survives from the report, and what does not.** The report's "structurally unqueryable"
half is **a documented design decision** — the enum's own docstring now says it is *not*
stored as a DB column and that `ModeratorActionLog.reason` stays TEXT. Phase 10 does not
build a column, a lookup table or a migration. What survives is narrower and sharper: **the
POST value is never validated against the vocabulary**, so any client string is concatenated
into the audit row.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/moderation/views/review.py` | `reject_ad` — the `reason_category` read and the `reason = f"{reason_category}"` / `f"{reason_category}: {reason_text}"` construction; `ban_user` — its inline `request.method` guard; the two `redirect(f"/admin/…")` calls on GET | **Also BLOCKs 5 and 12.** The stored shape `"<category>: <text>"` must not change |
| `src/backend/apps/moderation/tests/test_moderation_views.py` | `TestRejectAdView` (5 cases), `TestBanUserView::test_ban_requires_post`, `TestApproveAdView::test_approve_requires_post` | Green unchanged except, under Q4(a), the two GET assertions |
| `src/backend/templates/admin/moderation/review.html` | the 8 hardcoded `<option>`s, in the enum's declaration order | Delete them; render from the context. **Also BLOCK 5's file** |
| `src/backend/apps/core/enums.py` | `CategoryRejectReason` | **Read-only unless Q2(d)** — and if (d) is chosen, this becomes a **five-phase** contended edit and the coordinator must be told first |
| `src/backend/apps/core/__init__.py` | the `CategoryRejectReason` re-export | **Keep it.** It is the mechanism that makes the enum reachable from a view; removing it is a separate change |
| `docs/02-database/db-enums.md` | the `CategoryRejectReason` table | **Only under Q2(d)**, same commit |

**Binding constraints**

1. **The stored `reason` shape is unchanged.** Every one of the 8 members must still persist
   and `reason_category` alone must still produce a category-only string. The five existing
   `TestRejectAdView` cases post `reason_category="spam_scam"` and must be green unchanged.
2. **`reason_text` handling is unchanged**, including the no-`reason_text` case.
3. **The invalid-value path is the Q2 ruling, and the vocabulary is closed.** *(rewritten in
   place 2026-10-03 — Product Owner, option (b). This constraint previously said only that the
   template must not hardcode the vocabulary; it now carries the ruling's three invariants, and
   no parallel rule is added beside it.)* An invalid `reason_category` **re-renders the review
   page with an error and preserves the moderator's typed `comment`**; it is **not** a 400, and
   it is **not** coerced to empty. **No arbitrary client string reaches
   `ModeratorActionLog.reason`** — validation runs before the `f"{reason_category}"` /
   `f"{reason_category}: {reason_text}"` construction, and **no audit row is written**. The 8
   `<option>`s are deleted, not re-listed: a `for` loop over the enum's members, in declaration
   order, is the point, and the **vocabulary stays at 8 members** — option (d)'s "other" member
   was **not** chosen, so `db-enums.md` is not edited.
4. **No migration, no new column, no lookup model.**
5. **Do not remove the `apps/core/__init__.py` re-export.**
6. **`approve_ad`, `ban_user` and `reject_ad` are not restructured.**
   `TestModerationReviewLocking` source-inspects all three for `select_for_update` and
   `transaction.atomic`. **A decorator swap is safe; moving a fetch into a helper is not.**
7. **The ad is never moderated or banned on a GET**, under either Q2 or Q4 option. That is
   the invariant both decisions share and the one the existing tests actually care about.
8. **The `staff_required` check and the transaction boundary are untouched.**
9. **The two test updates, if Q4(a), are in the same commit**, and the commit body states that
   the behaviour change was **decided**, not discovered.
10. **`review.py`'s `redirect()` targets are BLOCK 5's** — they are already `reverse()`d by
    then. This block does not re-edit them, and BLOCK 12's move touches only the import line.
11. **No template change is permitted** beyond the option list. If a form turns out to submit
    by GET, that is a separate defect: stop and report.
12. **⚠ A sibling ruling narrows Q4's premise, and this plan does not re-decide it.** *(recorded
    2026-10-03; appended as 12 so that no existing constraint number shifts)* A Product Owner
    decision taken **outside this plan** settles that a GET on a state-changing moderation route
    **renders a confirmation page (200)** and the action executes **only on POST** — which
    **supersedes both of Q4's options as they stand** (a 302 redirect and a bare 405). **This plan
    does not choose between them and does not rewrite Q4.** What it records is that Q4's *premise*
    is affected: the **two shipped tests asserting 302** will need their expectations changed **in
    the same commit as the shape change, with the justification recorded**, and that change belongs
    to **phase 15**, which owns the moderation routes. **Propagation obligation on phase 15.** An
    Implementor must not treat "302" or "405" as still-current options without checking phase 15's
    `Q8`/`Q12` first.

**Implementor task**

```yaml
id: task_10_b07_reject_reason_boundary
title: "Close the reject-reason boundary and standardise the moderation guards (10-CQ-003, 10-CQ-018)"
priority: high
depends_on: [task_10_b05_status_templates]
source_reference: ".ai/plans/10-code-quality-remediation.md"
source_section: "BLOCK 7 - Make the reject-reason vocabulary a real boundary"
source_blocks: ["BLOCK 7"]
description: >
  Two decisions land on one function here. Q2 is RESOLVED 2026-10-03 by the Product Owner:
  an invalid reason_category RE-RENDERS the review page with an error and preserves the
  moderator's typed comment; it is NOT a 400, NOT coerced to empty, and no arbitrary client
  string reaches ModeratorActionLog.reason. The 8-value vocabulary is closed and no 'other'
  member is added. reject_ad reads request.POST.get("reason_category", ""), does not
  strip it, does not validate it, and concatenates it
  into ModeratorActionLog.reason - a TEXT column - so any client string is accepted; expose
  the enum to review.html via the Q10 mechanism and delete the eight hardcoded
  options. Q4: reject_ad and ban_user redirect a GET to the admin change page
  (302) while their sibling approve_ad already returns 405 via @require_POST; apply the
  recorded option, and under option (a) update the two GET assertions in this commit. The]
  stored "<category>: <text>" shape must not change, and no view may be restructured -
  TestModerationReviewLocking source-inspects all three.
goals:
  - "close the 8-value vocabulary so an arbitrary client string can never reach the audit row"
  - "delete the duplicated hardcoded option list from the template"
  - "make POST-only mean one thing across the three moderation siblings"
  - "never moderate or ban an ad on a GET, under either option"
files:
  - path: "src/backend/apps/moderation/views/review.py"
    targets:
      - type: function
        name: reject_ad
      - type: function
        name: ban_user
      - type: function
        name: approve_ad
  - path: "src/backend/templates/admin/moderation/review.html"
    targets: [{type: module, name: review}]
  - path: "src/backend/apps/core/enums.py"
    targets: [{type: class, name: CategoryRejectReason}]
  - path: "src/backend/apps/moderation/tests/test_moderation_views.py"
    targets:
      - type: class
        name: TestRejectAdView
      - type: class
        name: TestBanUserView
changes:
  - action: modify_code
    description: >
      Validate reason_category against the enum in reject_ad BEFORE the reason string is
      constructed. Q2 is RESOLVED 2026-10-03 as option (b): on failure RE-RENDER the review page
      with an error and preserve the moderator's typed comment. Do NOT return a 400, do NOT
      coerce to empty, and do NOT write a ModeratorActionLog row. Keep the reason string
      construction exactly as it is. Under Q4(a) apply @require_POST to reject_ad and ban_user,
      delete their inline method guards, and update the two GET assertions to expect 405.
  - action: modify_code
    description: >
      Render the dropdown options from the enum in declaration order via the Q10 mechanism
      and delete the eight hardcoded option elements. Add the new invalid-category error string
      to ru and bs.
acceptance_criteria:
  - "a POST with a reason_category outside the enum re-renders the review page with an error and NO ModeratorActionLog row is written"
  - "the re-render PRESERVES the moderator's typed comment - a re-render that discards it would be a worse defect than the one being fixed"
  - "the invalid value is NOT coerced to empty and does NOT become a 400"
  - "no arbitrary client string reaches ModeratorActionLog.reason"
  - "all eight enum members still produce a stored reason, and the '<category>: <text>' shape is unchanged"
  - "the review template contains no hardcoded reject-reason option value"
  - "CategoryRejectReason still has exactly 8 members; no 'other' member was added and db-enums.md was not edited"
  - "the new error string has non-empty ru and bs msgstr; en may be empty"
  - "a GET to reject_ad or ban_user never moderates or bans the ad, under either Q4 option"
  - "TestModerationReviewLocking is green UNCHANGED for all three views"
  - "TestRejectAdView is green UNCHANGED apart from the two Q4(a) GET assertions"
  - "under Q4(a) both GET assertions expect 405; under Q4(b) the code is unchanged and the commit body records the accepted asymmetry"
  - "the /admin/ redirect targets were not re-edited - BLOCK 5 owns them"
  - "apps/core/__init__.py's re-export is untouched; no migration was created"
  - "the commit body names both the Q2 and the Q4 options"
tests_to_run:
  - "src/backend/apps/moderation/tests/test_moderation_views.py"
```

**Tests required**
1. **The refusal** — an arbitrary category string creates **no** audit row and does not
   moderate the ad. Assert on the absence of danger, not on a status code alone.
2. **The round-trip** — all 8 members are accepted, and the stored reason for each is
   distinguishable from the others. This is what makes the vocabulary real; a test that only
   checks one member proves nothing.
3. **The template is generated from the enum** — an option is rendered for every member of
   `CategoryRejectReason`, which fails today and is the assertion that the duplication is
   really gone.
4. **The GET invariant** — a GET to `reject_ad` or `ban_user` leaves the ad's status and the
   `ModeratorActionLog` untouched. This holds whichever way Q2 and Q4 go, and it is the
   assertion that actually encodes the risk.
5. **Under Q4(a)** — a GET returns 405 on both views, matching `test_approve_requires_post`,
   and a POST still moderates exactly as before.
6. **The positive control** — the existing `TestRejectAdView` and ban cases are green
   unchanged apart from the two status assertions.

**Risk and rollback**
- *Implementation risk:* the `"<category>: <text>"` format is only implicitly pinned today.
  A rewrite that stores the category and the text in separate columns is a migration and is
  forbidden. Mitigation: binding constraint 1 and test 2.
- *Implementation risk:* a "consistency" fix that also moves a lock or a transaction.
  Binding constraint 6; `TestModerationReviewLocking` is the tripwire.
- *Rollout risk:* Q2(a) returns a bare 400 and Q4(a) a 405 to a moderator with a stale page.
  Both are accepted costs of the cheapest options; state them in the commit body.
- *Contention:* `review.py` (3 phase-10 blocks), `review.html` (2 blocks), `enums.py`
  (5 phases).
- *Rollback:* a straight revert, including any test assertions. Rows already written with
  arbitrary strings are untouched — a data question, not a code one, and it must be said in
  the commit body.

---

### BLOCK 8 — Delete what nothing references (CQ-016)

| | |
|---|---|
| **Findings owned** | `CQ-016` (LOW, `BEST-PRACTICE`) |
| **Class** | **mechanical** — deletion only |
| **Depends on** | BLOCK 1 (`consent.py` is BLOCK 1's first, BLOCK 8's second) |
| **Blocks** | BLOCK 9 (the same `lookup_resolution.py` methods are annotated there) |
| **Priority** | P2 |
| **Risk level** | **LOW** — every symbol is single-occurrence in-repo; one external question (Q5) |
| **Required agents** | **Auditor · Researcher · Planner · Validator.** The Researcher answers Q5's external half |

**Decision required before implementation — Q5: do the `RESOLVED_*_PREFIX` aliases have an
external importer?**

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | The coordinator confirms there is **no** external consumer | **Gains:** the in-repo evidence (zero references across `src`, `docs`, `templates`, `.ai`) becomes sufficient. Project rule 2 — production code is king over a comment — then applies cleanly. **Costs:** none |
| **(b)** | An external consumer exists, or cannot be ruled out | **Gains:** the comment is a live promise and is honoured. **Costs:** the three aliases stay, and the finding's tenth symbol is recorded as "retained, not dead" rather than deleted. `is_consent_given`, the two `get_resolved_*_codes` methods and `invalidate_group` are still deleted — they carry no such claim |

**The Implementor may not choose**, and may not infer "no external consumer" from an in-repo
grep.

**File surface (semantic units)**

| File | Symbol / target | Evidence |
|---|---|---|
| `src/backend/apps/users/views/consent.py` | `is_consent_given` | 0 references repo-wide. **Also BLOCK 1's file** |
| `src/backend/apps/categories/services/lookup_resolution.py` | `CategoryLookupResolver.get_resolved_purpose_codes`, `get_resolved_condition_codes`, the `RESOLVED_PURPOSES_PREFIX` / `RESOLVED_FEATURES_PREFIX` / `RESOLVED_CONDITIONS_PREFIX` constants, and the vestigial `if TYPE_CHECKING: pass` | 0 references each. The aliases are documented as *"kept for backward compatibility with any external callers"* — that is Q5. **Also BLOCK 9's file** |
| `src/backend/apps/lookups/services/cache_service.py` | `invalidate_group` | 0 references |
| `src/telegram_bot/states.py` | `SavedSearchState` (5 members) | 0 references. **Also BLOCK 10's concern** — delete it here, once |
| `src/backend/apps/api/` | the empty `serializers/` and `views/` directories | Verified: **0 files**, no `__init__.py`, not in git. Removing empty untracked directories is not a tracked change |
| `src/backend/apps/core/__init__.py` | the `CategoryRejectReason` re-export | **Do NOT remove it** — it is BLOCK 7's mechanism. The re-export is *why* a naive grep reports 0 call sites; that is a finding about grep ergonomics, not dead code |

**Binding constraints**

1. **`can_publish_ad` is NOT touched.** It is phase 15's `AUTHZ-005`, whose validator
   *rejected* the dead-code label, and it is test-referenced 13× in `test_account_state.py`.
   Reviving it as dead code is a rule violation.
2. **Nothing is deleted on the strength of a comment.** Only the three aliases are
   comment-protected, and only Q5 decides them.
3. **`SavedSearchState` is deleted here and nowhere else.** BLOCK 10 references its absence;
   it must not also delete it.
4. **No import cleanup "while you are here".** Removing a now-unused import is in scope;
   removing a module, a re-export or a directory that is not in the table is not.
5. **`docs/02-database/db-enums.md` is not edited** — `CategoryRejectReason` keeps its
   documentation and is BLOCK 7's enum.

**Implementor task**

```yaml
id: task_10_b08_dead_code
title: "Delete the symbols nothing references (10-CQ-016)"
priority: low
depends_on: [task_10_b01_consent_cookie_constants]
source_reference: ".ai/plans/10-code-quality-remediation.md"
source_section: "BLOCK 8 - Delete what nothing references"
source_blocks: ["BLOCK 8"]
description: >
  Six named symbols plus three RESOLVED_*_PREFIX aliases plus a vestigial `if TYPE_CHECKING:
  pass` and an empty apps/api/ tree have exactly one occurrence each across the whole
  repository: their own definition. Delete them. The three aliases carry an explicit
  "backward compatibility with any external callers" comment and are governed by the
  recorded Q5 answer; the other six are not. can_publish_ad belongs to phase 15's AUTHZ-005
  and must not be touched.
goals:
  - "remove every symbol proven to have zero references"
  - "delete nothing on the strength of a comment"
  - "leave can_publish_ad and the CategoryRejectReason re-export alone"
files:
  - path: "src/backend/apps/users/views/consent.py"
    targets: [{type: function, name: is_consent_given}]
  - path: "src/backend/apps/categories/services/lookup_resolution.py"
    targets:
      - type: method
        name: get_resolved_purpose_codes
      - type: method
        name: get_resolved_condition_codes
  - path: "src/backend/apps/lookups/services/cache_service.py"
    targets: [{type: function, name: invalidate_group}]
  - path: "src/telegram_bot/states.py"
    targets: [{type: class, name: SavedSearchState}]
changes:
  - action: delete_code
    description: >
      Delete the six zero-reference symbols and the vestigial TYPE_CHECKING guard. Delete
      the three RESOLVED_*_PREFIX aliases only if the Q5 answer is (a); otherwise retain them
      and record that outcome in the commit body.
acceptance_criteria:
  - "can_publish_ad is byte-identical to before this block"
  - "apps/core/__init__.py still re-exports CategoryRejectReason"
  - "the lookup resolver's used get_resolved_purposes / _features / _conditions and the *_SEGMENT constants are untouched"
  - "test_account_state.py is green UNCHANGED"
  - "the commit body records the Q5 answer and, if (b), names the three retained aliases"
  - "no module, re-export or tracked directory was deleted beyond the table"
tests_to_run:
  - "src/backend/apps/categories/tests"
  - "src/backend/apps/lookups/tests"
  - "src/backend/apps/users/tests/test_account_state.py"
  - "src/telegram_bot/tests"
```

**Tests required** — none new. This block adds a deletion; the fast gate is the assertion,
and a test asserting the absence of a symbol is trivia and is forbidden (§1.5). The one
worth adding is **indirectly**: if removing `SavedSearchState` breaks an import in the bot,
the suite will say so.

**Risk and rollback**
- *Implementation risk:* deleting a symbol that a **string** references — a template
  `{% include %}`, a `settings.py` `INSTALLED_APPS` entry, a `makemessages` msgid. Mitigation:
  a whole-repo grep across `src`, `docs`, `templates` **and** `.ai` before deleting, which is
  what the finding already did.
- *Regression risk:* an external importer (Q5). That is the whole gate.
- *Rollback:* a straight revert restores every symbol and its docstring.

---

### BLOCK 9 — Typed service boundaries, and the four suppressions they make removable (CQ-012)

| | |
|---|---|
| **Findings owned** | `CQ-012` (MEDIUM, `SPEC-DEVIATION`) |
| **Class** | **behavioural** for the test suite — ~30 assertions in `test_priority.py` break unless Q14 is answered |
| **Depends on** | BLOCK 2 (`cache.py` is BLOCK 2's first, BLOCK 9's second), BLOCK 8 (`lookup_resolution.py`), BLOCK 1 (`context_processors.py`) |
| **Blocks** | nothing in-plan |
| **Priority** | P1 |
| **Risk level** | **MEDIUM** — largest test blast radius of the "cheap" findings; **no gate enforces it** |
| **Required agents** | **Auditor · Researcher · Planner · Validator** |

**Decision required before implementation — Q14: does `PriorityScore` keep mapping
compatibility, or does the consumer change?**

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | `PriorityScore` exposes `__getitem__` (and any other mapping affordance `**`-expansion and `defaults=data` need), so `priority.py` is unchanged | **Gains:** ~30 `test_priority.py` assertions stay green; one file changes; the DTO is a drop-in. **Costs:** a Pydantic model with a hand-written mapping shim is exactly the kind of hybrid the project rules dislike, and it is a *new* abstraction justified only by backwards compatibility |
| **(b)** | A clean Pydantic model; `PriorityService.calculate_and_save` uses attribute access and `model_dump()`; `test_priority.py` is updated to the object API | **Gains:** the honest model, one obvious way to read it, and the test file finally describes the contract rather than a dict literal. **Costs:** ~30 assertions change **in the same commit**, under project rule 2 — the commit body must state that the tests were updated to the decided contract, not weakened |
| **(c)** | A `TypedDict` instead of a Pydantic model | **Gains:** `**`-expansion, subscripting and `defaults=data` all keep working with **zero** compatibility shim and zero test churn. **Costs:** it is not runtime-validated and does not satisfy the report's "Pydantic v2" framing — but nothing here needs runtime validation, because `calculate_priority` is an internal producer, not a system boundary. Project rule 11 puts Pydantic **at boundaries**, and this is not one |

**The Implementor may not choose.** Option (c) is listed because it is the cheapest
*and* the most rule-consistent, which is precisely why it is a decision and not a default.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/moderation/services/priority_calculator.py` | `PriorityCalculator.calculate_priority` (bare `dict` return, 5-key literal), `_calculate_content_score`, `_calculate_user_score` (both bare `dict`), and the three `flags: list[str]` holding the closed vocabulary `"banned_word"` / `"repeat_offender"` | The producer |
| `src/backend/apps/moderation/services/priority.py` | `PriorityService.calculate_and_save` — `defaults=data` and `data["base_score"]` | **The consumer that constrains the DTO** (C-10). Unchanged under Q14(a), edited under (b) |
| `src/backend/apps/moderation/tests/test_priority.py` | ~30 cases asserting `result["score"]`, `result["flags"]`, `result["priority_level"]`, `result["confidence_score"]` | The blast radius. Its docstring says it goes *"via the **public** `calculate_priority`"* — the public surface is what the DTO must keep |
| `src/backend/apps/categories/services/lookup_resolution.py` | `CategoryLookupResolver.get_resolved_purposes` / `get_resolved_features` / `get_resolved_conditions` / `_resolve` (unannotated `category`, bare `list`, `# type: ignore[type-arg]`), and `_get_through_model` (unannotated, no ignore) | **Four** suppressions, not three |
| `src/backend/apps/core/utils/cache.py` | `get_cached_criteria` / `get_cached_support_contacts` | The two bare-generic returns the code context added |
| `src/backend/apps/users/context_processors.py` | `consent_state` (unannotated `request`), `consent_version` (bare `dict` return) | The two signatures the code context added |

**Binding constraints**

1. **The four `# type: ignore[type-arg]` suppressions go in the same commit as the
   annotations.** A suppression removed while the parameter stays unannotated trades one
   lie for another.
2. **No gate will confirm this.** `basedpyright` is in `standard` mode and does not flag bare
   generics; `[tool.mypy]` carries `disallow_any_generics`, is **not read by basedpyright**,
   and mypy is **not in CI** (C-4). The acceptance criterion is the test suite and the four
   vanishings, **not** a typecheck delta. Do not claim "type errors went to zero".
3. **`PriorityFlags(StrEnum)` is NOT built** (§6). The vocabulary is two strings. An enum for
   two values is defensible under rule 10 but is not load-bearing, and the finding's
   rule-backed part is the typed DTO, not the flag enum.
4. **The 5-key shape and the key names do not change.** `base_score`, `priority_level`,
   `flags`, `confidence_score`, `escalation_required` are read by `priority.py` and asserted
   by the suite. Only the *type* changes.
5. **No migration.** `PriorityScore` is a value object, not a model. It must not become a
   Django model and must not be persisted.
6. **`_get_through_model` is annotated too.** The report missed it; a block that annotates
   three of four leaves the file looking done when it is not.
7. **No new field is added to the score.** This block is a type change, not a scoring change.

**Implementor task**

```yaml
id: task_10_b09_typed_boundaries
title: "Type the service boundaries and drop the four suppressions (10-CQ-012)"
priority: high
depends_on: [task_10_b02_packaging_hygiene, task_10_b08_dead_code, task_10_b01_consent_cookie_constants]
source_reference: ".ai/plans/10-code-quality-remediation.md"
source_section: "BLOCK 9 - Typed service boundaries"
source_blocks: ["BLOCK 9"]
description: >
  calculate_priority returns a bare dict with a 5-key literal, its two private scorers
  return bare dicts, and CategoryLookupResolver carries four `# type: ignore[type-arg]`
  suppressions - the only ones of their kind in production code. Replace the score with the
  Q14-recorded type, annotate all four resolver methods plus _get_through_model, drop the
  four suppressions, and type the two bare generics in cache.py and the two untyped
  signatures in users/context_processors.py - all in one commit, because the suppressions
  and the annotations are inseparable. No gate enforces any of this: report that honestly.
goals:
  - "give the score a named type without changing its shape or its key names"
  - "remove all four type-arg suppressions from production code"
  - "annotate every boundary the finding names, including the one it missed"
files:
  - path: "src/backend/apps/moderation/services/priority_calculator.py"
    targets:
      - type: method
        name: calculate_priority
      - type: method
        name: _calculate_content_score
  - path: "src/backend/apps/moderation/services/priority.py"
    targets: [{type: method, name: calculate_and_save}]
  - path: "src/backend/apps/categories/services/lookup_resolution.py"
    targets:
      - type: method
        name: get_resolved_purposes
      - type: method
        name: _get_through_model
  - path: "src/backend/apps/core/utils/cache.py"
    targets: [{type: function, name: get_cached_criteria}]
  - path: "src/backend/apps/users/context_processors.py"
    targets: [{type: function, name: consent_state}]
  - path: "src/backend/apps/moderation/tests/test_priority.py"
    targets: [{type: module, name: test_priority}]
changes:
  - action: add_code
    description: "Introduce the Q14-recorded score type with the same five keys."
  - action: modify_code
    description: >
      Return it from calculate_priority and the two private scorers; annotate the four
      resolver methods and _get_through_model; delete the four `# type: ignore[type-arg]`
      comments; type the cache and context-processor signatures. Under Q14(b) update
      priority.py and test_priority.py in this same commit.
acceptance_criteria:
  - "no '# type: ignore[type-arg]' remains anywhere in production code"
  - "the score's five keys and their names are unchanged and update_or_create still receives them"
  - "test_priority.py is green - UNCHANGED under Q14(a)/(c), updated under Q14(b) with the reason stated in the commit body"
  - "PriorityFlags(StrEnum) was NOT added and no new score field was added"
  - "no migration was created; PriorityScore is not a Django model"
  - "the commit body names the Q14 option and states plainly that no static gate enforces this change"
tests_to_run:
  - "src/backend/apps/moderation/tests/test_priority.py"
  - "src/backend/apps/moderation/tests/test_priority_service.py"
  - "src/backend/apps/categories/tests"
  - "src/backend/apps/users/tests/test_consent_context.py"
```

**Tests required**
1. **The round-trip that matters** — `PriorityService.calculate_and_save` still writes the
   same five columns with the same values for a given ad, asserted through the **persisted
   row**, not through the intermediate object. This is the control that catches a DTO whose
   `model_dump()` drops or renames a key.
2. **The score's discriminators** — a `flags` list containing a moderation reason survives
   the round trip and is persisted; an empty `flags` list does not become `None`.
3. **Under Q14(b) only** — the updated `test_priority.py` asserts the **object** contract
   (keys via the decided accessor) and still fails when a key is dropped. A test that was
   mechanically string-replaced so it cannot fail is worse than no test.

**Risk and rollback**
- *Implementation risk:* a DTO that looks equivalent but drops a key on `model_dump()`.
  Mitigation: test 1, through the persistence layer.
- *Review risk:* the change is presented as a compliance fix when it is a readability fix.
  Mitigation: binding constraint 2, and the commit body must say so.
- *Regression risk:* `# type: ignore` removal is invisible to the runtime — nothing catches a
  wrongly-removed suppression. Mitigation: a *basedpyright* run **is** required, because
  basedpyright may flag what mypy's ignore was hiding. That is a real check, not a formality.
- *Rollback:* a straight revert. No data movement.

---

### BLOCK 10 — Stop promising a toggle the bot does not have (CQ-014)

| | |
|---|---|
| **Findings owned** | `CQ-014` (MEDIUM, `BEST-PRACTICE`) — prompt half |
| **Class** | **behavioural** — a user-visible string changes |
| **Depends on** | nothing in-plan. `SavedSearchState` was deleted in BLOCK 8 |
| **Blocks** | BLOCK 11 (`alerts.py` is BLOCK 10's first, BLOCK 11's second) |
| **Priority** | P2 |
| **Risk level** | **LOW** — one sentence, plus an i18n catalogue append if the string is reworded |
| **Required agents** | **Auditor · Planner · Validator** — the Validator confirms `ru` and `bs` |

**Why the toggle is de-scoped — DECIDED 2026-10-03 (Product Owner), not merely deferred.**
Implementing it is a **new user-facing feature**: an FSM state machine for the list, a new router
entry point, numeric input parsing, error paths, and **three new i18n strings** with non-empty
`ru` **and** `bs` in a catalogue shared with six other phases. That is not a MEDIUM code-quality
remediation; it is a feature belonging to whoever owns the bot's seller-facing flows. The
**Product Owner has now ruled the feature OUT of this programme**: the deliverable is the
**prompt correction plus the dead-state deletion, and nothing else**. **No new FSM, no new router
entry point, and no new i18n strings are in scope** — the three strings the report contemplated
are explicitly excluded. The **defect** is real and narrower than the feature: *a shipped prompt
promises an interaction the code does not implement*, and a seller who follows it falls through
to the unhandled-message path.

| Option | What ships | Consequence |
|---|---|---|
| **(a) — CHOSEN, ruling 2026-10-03** | **Correct the prompt** to describe what `/alerts` actually does (list saved searches with their unsubscribe links, then stop) | The promise is withdrawn, the dead end closes, and the block is one sentence plus an i18n append for the **reworded existing** string. **The Product Owner adopted this and declined the feature** |
| ~~**(b)**~~ | Implement the numeric toggle | **DECLINED for this programme (2026-10-03).** §6; recorded as a **feature request with a named owner**. Not this plan |

**The Implementor may not choose (b)** — it is no longer a choice, it is a **declined option**.
The un-built toggle is a **feature request**, and the owner of that request is recorded in §0.7
and §6. **BLOCK 11 should still run before any future toggle work**, because the toggle's
handlers would land in the same file the extraction moves.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/telegram_bot/handlers/alerts.py` | `cmd_alerts` — the `lines.append(_("\nReply with number to toggle, or /cancel to exit."))` line and the module's three router entry points (`Command("alerts")`, `F.data.startswith(UNSUB)`, `F.data.startswith(UNSUB_ON)`) | **Also BLOCK 11's file.** Re-read immediately before editing |
| `src/backend/locale/{ru,bs,en}/LC_MESSAGES/django.po` | the msgid for that sentence | **Append; never regenerate.** The catalogue is shared with phases 03/05/06/07/11/14. `ru` and `bs` must be non-empty; `en` may be empty |

**Binding constraints**

1. **No new router entry point, no FSM state, no numeric parsing, no `/cancel` handler in
   `/alerts`.** Those are the de-scoped feature.
2. **`SavedSearchState` is already deleted** (BLOCK 8). This block must not delete it again
   and must not reintroduce it.
3. **The three existing entry points are unchanged** — `Command("alerts")`, the unsubscribe
   callback and the re-enable callback. The deep-link parser `handle_unsubscribe_start` is
   not a router entry point and is not in scope.
4. **The i18n append is in the same commit as the code change**, `ru` and `bs` non-empty.
5. **The corrected prompt must describe only what the handler does.** If the replacement text
   promises anything new, it is a bug of the same class.
6. **`alerts.py` must not be restructured in this block** — the data-access extraction is
   BLOCK 11's, and `test_unsubscribe.py` source-inspects `_resolve_owned`.

**Implementor task**

```yaml
id: task_10_b10_alerts_prompt
title: "Correct the /alerts prompt (10-CQ-014)"
priority: medium
depends_on: []
source_reference: ".ai/plans/10-code-quality-remediation.md"
source_section: "BLOCK 10 - Stop promising a toggle the bot does not have"
source_blocks: ["BLOCK 10"]
description: >
  cmd_alerts ends its listing with "Reply with number to toggle, or /cancel to exit." The
  module registers three entry points and none of them accepts a number; there is no
  /cancel handler in /alerts. A seller who follows the instruction falls through to the
  unhandled-message path. Correct the prompt so it describes what the handler actually
  offers - the saved-search list with its unsubscribe and re-enable links. The numeric
  toggle is a feature and is out of scope.
goals:
  - "close the user-facing dead end by making the prompt match the behaviour"
  - "introduce no new handler, no FSM state and no parsing"
  - "keep ru and bs translations non-empty"
files:
  - path: "src/telegram_bot/handlers/alerts.py"
    targets: [{type: function, name: cmd_alerts}]
  - path: "src/backend/locale/ru/LC_MESSAGES/django.po"
    targets: [{type: module, name: django}]
changes:
  - action: modify_code
    description: >
      Replace the misleading trailing prompt with text that describes the links the listing
      already renders. Translate the new string into ru and bs; en may stay empty.
acceptance_criteria:
  - "the /alerts reply promises no numeric toggle and no /cancel step"
  - "the three existing router entry points and the deep-link parser are unchanged"
  - "no new handler, FSM state or numeric parsing was added"
  - "SavedSearchState is still absent and was not reintroduced"
  - "ru and bs msgstr are non-empty for the new string; en may be empty"
  - "test_alerts.py and test_unsubscribe.py are green"
  - "_resolve_owned was not moved by this block"
tests_to_run:
  - "src/telegram_bot/tests/test_alerts.py"
  - "src/telegram_bot/tests/test_unsubscribe.py"
  - "src/backend/apps/ads/tests/test_i18n_completeness.py"
```

**Tests required** — one new case, and it is worth it: **the `/alerts` reply text contains no
instruction to reply with a number and no `/cancel` step**, asserted on the rendered reply
the handler produces. That is a user-facing contract, not a string-substring assertion, and
it is the only thing that stops the promise from creeping back. The existing callback and
deep-link suites must be green unchanged.

**Risk and rollback**
- *Implementation risk:* scope creep into a half-implemented toggle. Binding constraints 1
  and 2; the withdrawal of the promise is the whole fix.
- *i18n risk:* an untranslated string in a two-locale project. `test_i18n_completeness.py` is
  in `tests_to_run`; an i18n failure here is a **consequence** of the change, not a
  regression, and is fixed in the same commit.
- *Contention:* `handlers/alerts.py` is also phase 03 BLOCK 5's (`SET LOCAL lock_timeout`) and
  phase 09's cross-reference. Re-read before editing.
- *Rollback:* a straight revert. No state, no schema, no user data.

---

### BLOCK 11 — Move the bot's alert data access out of the handler (CQ-002, `alerts` half)

| | |
|---|---|
| **Findings owned** | `CQ-002` (MEDIUM, `BEST-PRACTICE`) — `alerts` extraction + `contact` / `support` import hoists |
| **Class** | **behavioural** — moves four functions and re-points two source-inspection tests |
| **Depends on** | BLOCK 10 (`alerts.py` is BLOCK 10's first, BLOCK 11's second). **External gate: phase 03 BLOCK 5** |
| **Blocks** | nothing in-plan |
| **Priority** | P2 |
| **Risk level** | **MEDIUM** — two shipped tests inspect the moved function's source; a `ValueError`, not a clean failure, is the failure mode |
| **Required agents** | **Auditor · Researcher · Planner · Validator** |

**External gate.** Phase 03 **BLOCK 5** (`SET LOCAL lock_timeout`) names
`telegram_bot/handlers/alerts.py` explicitly and is adding statements inside the same
`transaction.atomic()` that `_resolve_owned` owns. **BLOCK 11 lands after phase 03 BLOCK 5
or is folded into it — never concurrently.** Phase 04 BLOCK 9 (comments only) and phase 09's
API-009 / API-010 (the alert *rate-limit* path, not `_resolve_owned`) are read-only
neighbours, not blockers. **Phase 09's `contact.py` rate-limiter block does share a file with
this block's `contact.py` import hoist** — different regions, so the rule is *sequential with
a re-read*, and the plan for phase 09 appeared while this one was being written (C-8).

**Decision required before implementation — the shape of the move.** The report proposes
three new modules; the tree says one.

| Part | What the report proposes | What the tree supports | Consequence |
|---|---|---|---|
| `alerts` | `telegram_bot/services/alerts.py` | ✔ A real extraction. `get_user_saved_searches`, `resolve_unsubscribe`, `resolve_reenable` and `_resolve_owned` are the handler's whole data-access layer, and `SavedSearch` is already imported at **module** level, proving there is no import-time constraint | **One new module.** Handlers keep their signatures and delegate |
| `contact` | `telegram_bot/services/contact.py` | ✔ The deferred import is `from apps.core.services.contact import (...)` — the service **already exists** | **No new module.** Promote the import to module level |
| `support` | `telegram_bot/services/support.py` | ✔ The three deferrals are `SupportTicketStatus`, `SupportTicket` and a nested `User` import | **No new module.** Promote to module level |
| `login` | `telegram_bot/services/login.py` | ✔ **Already shipped** by phase 01 `ENT-005` | **Never create it** (C-3) |

**The Implementor may not "finish the job"** by adding the two modules the report named.
A service that already exists must be imported, not re-wrapped.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/telegram_bot/services/alerts.py` **(new)** | `get_user_saved_searches`, `resolve_unsubscribe`, `resolve_reenable`, `_resolve_owned` | The four moved symbols, verbatim. `telegram_bot/services/` already holds `rate_limit.py`, `support_delivery_email.py`, `support_delivery_telegram.py` and `ad_data/` — the precedent package |
| `src/telegram_bot/handlers/alerts.py` | `cmd_alerts`, `handle_unsubscribe_callback`, `handle_reenable_callback`, `handle_unsubscribe_start` | **Signatures and behaviour unchanged**; the data access delegates |
| `src/telegram_bot/handlers/contact.py` | the function-local `from apps.core.services.contact import (...)` | Promoted to module level. Phase 04 BLOCK 9 touches this file for comments only |
| `src/telegram_bot/handlers/support.py` | the three function-local imports | Promoted to module level |
| `src/telegram_bot/tests/test_unsubscribe.py` | `TestResolveOwnedLocking` — two tests over `inspect.getsource(alerts._resolve_owned)`, one asserting `sfu_idx > atomic_idx` | **Re-pointed at `telegram_bot.services.alerts._resolve_owned` in the same commit** |
| `src/telegram_bot/tests/test_alerts.py` | `TestHandleUnsubscribeCallback`, `TestHandleReenableCallback` | Must be green unchanged |

**Binding constraints**

1. **The handler's public surface is unchanged.** Every bot answer must be byte-identical
   before and after. `handle_login_orm`'s 12 pinned call sites are the precedent for how
   strictly this is taken.
2. **Two source-inspection tests are re-pointed, never deleted.** They are the only shipped
   guard on the locked-read-inside-the-transaction structure. Their assertions are reviewed
   for still expressing the intent.
3. **The move does not change the locking.** `select_for_update()` and `transaction.atomic()`
   move together, inside one function. Splitting them across a module boundary is the defect,
   not the fix.
4. **No new module for `contact` or `support`.** `apps.core.services.contact` already exists.
5. **No deferred import is added anywhere.** The point is that the deferral was arbitrary.
6. **The bot stays inside the lint and typecheck gates.** `ci.yml` runs
   `uv run ruff check src/` and `uv run basedpyright src/` (C-4), so the new module is gated
   from its first commit. `ENT-004` is a **satisfied precondition**, not a blocker.
7. **Do not touch `telegram_bot/handlers/login.py`.** It is phase 01's shipped work and
   phase 03 BLOCK 5's file.

**Implementor task**

```yaml
id: task_10_b11_bot_alerts_service
title: "Move the bot alert data access into telegram_bot/services (10-CQ-002)"
priority: medium
depends_on: [task_10_b10_alerts_prompt]
source_reference: ".ai/plans/10-code-quality-remediation.md"
source_section: "BLOCK 11 - Move the bot's alert data access out of the handler"
source_blocks: ["BLOCK 11"]
description: >
  telegram_bot/handlers/alerts.py owns four data-access functions - get_user_saved_searches,
  resolve_unsubscribe, resolve_reenable and the locked _resolve_owned - and imports
  apps.search.models at module level, so no import-time constraint forces them to live
  there. Move them verbatim into a new telegram_bot/services/alerts.py and leave the handler
  signatures and every rendered answer byte-identical. Separately, promote the deferred
  apps.* imports in handlers/contact.py (the service already exists) and handlers/support.py
  (two model imports) to module level. Do NOT create telegram_bot/services/login.py - that
  extraction is already shipped - and do NOT create contact.py or support.py service modules.
goals:
  - "move four data-access functions behind a service boundary with no behaviour change"
  - "remove the three arbitrary deferred imports"
  - "re-point the two source-inspection tests at the new owner, not delete them"
files:
  - path: "src/telegram_bot/services/alerts.py"
    targets:
      - type: function
        name: get_user_saved_searches
      - type: function
        name: _resolve_owned
  - path: "src/telegram_bot/handlers/alerts.py"
    targets:
      - type: function
        name: cmd_alerts
      - type: function
        name: handle_unsubscribe_callback
  - path: "src/telegram_bot/handlers/contact.py"
    targets: [{type: module, name: contact}]
  - path: "src/telegram_bot/handlers/support.py"
    targets: [{type: module, name: support}]
  - path: "src/telegram_bot/tests/test_unsubscribe.py"
    targets: [{type: class, name: TestResolveOwnedLocking}]
changes:
  - action: add_code
    description: >
      Create telegram_bot/services/alerts.py with the four functions moved verbatim, keeping
      the @sync_to_async wrappers, the transaction.atomic() block, the select_for_update()
      call and the ownership check together and in the same order.
  - action: modify_code
    description: >
      Make the handlers delegate. Promote the deferred apps.* imports in contact.py and
      support.py to module level. Re-point TestResolveOwnedLocking at the moved function.
acceptance_criteria:
  - "every bot answer for /alerts, the unsubscribe callback and the re-enable callback is byte-identical before and after"
  - "telegram_bot/services/login.py does not exist; handlers/login.py is unchanged"
  - "no telegram_bot/services/contact.py or support.py was created"
  - "no function-local import of apps.* remains in handlers/alerts.py, contact.py or support.py"
  - "TestResolveOwnedLocking is green and now inspects telegram_bot.services.alerts._resolve_owned"
  - "test_alerts.py, test_unsubscribe.py and test_login.py are green"
  - "uv run ruff check src/ and uv run basedpyright src/ are green"
tests_to_run:
  - "src/telegram_bot/tests/test_unsubscribe.py"
  - "src/telegram_bot/tests/test_alerts.py"
  - "src/telegram_bot/tests/test_login.py"
```

**Tests required**
1. **The concurrency control that already exists** —
   `TestResolveOwnedConcurrency::test_concurrent_toggle_no_lost_update` is the strongest
   shipped guard on the locked read; it must pass unchanged against the moved function.
2. **The re-pointed structural tests** — `select_for_update` and `transaction.atomic` are
   present in the moved function and the fetch is inside the transaction. Re-point, do not
   delete, and do not weaken the ordering assertion.
3. **The answer-equality control** — the unsubscribe and re-enable callbacks produce the same
   text and the same keyboard for the same stored search before and after. A move that
   changes a button callback payload is a regression the structural tests cannot see.

**Risk and rollback**
- *Implementation risk:* a move that splits `transaction.atomic()` from
  `select_for_update()`. Mitigation: binding constraint 3; the ordering assertion is the
  tripwire.
- *Regression risk:* a handler signature drift breaks the bot router's registration.
  Mitigation: the handler functions keep their names and signatures; test 3.
- *Contention:* phase 03 BLOCK 5 (a **gate** for BLOCK 11), phase 04 BLOCK 9 (comments), and
  **phase 09**, whose rate-limiter block edits `handlers/contact.py` — a different region, but
  the same file, so the two are **sequenced with a re-read**, not parallelised (C-8).
- *Rollback:* a straight revert. The new module is deleted and the functions return.

---

### BLOCK 12 — Move `admin_actions.py` into `services/`, one commit, three importers (CQ-010, move half)

| | |
|---|---|
| **Findings owned** | `CQ-010` (LOW) — the file-move half |
| **Class** | **mechanical** — a path change and three import lines; zero behaviour change |
| **Depends on** | BLOCK 7 (so `review.py`'s body is settled before its import line moves) |
| **Blocks** | BLOCK 13 (the lint gate is enabled after the last arbitrary deferral is gone) |
| **Priority** | P1 — **highest value-per-diff in the report, highest coordination cost** |
| **Risk level** | **MEDIUM** — the diff is trivial; the coordination is not. **Five phases hold this file** |
| **Required agents** | **Auditor · Researcher · Planner · Validator** |

**Why this block exists and is separate from BLOCK 13.** The move is the finding's one
zero-new-abstraction action: `apps/moderation/admin_actions.py` imports nothing from
`apps/moderation/views/*`, so there is **no cycle to break** — and the decisive evidence is
that `apps/moderation/views/api_bulk.py` imports *the same module at module level*, in the
same package, in the same process. Moving it deletes all three deferred imports in
`review.py` as a side effect, and the module's own docstring already calls it a *"Admin
moderation actions **service**"* while it sits at the app root.

It is separate from BLOCK 13 because mixing a five-phase file move with a CI-gate change
makes the most contended commit in the plan also the one that turns a job red, and the two
failures need independent reverts.

**File surface (semantic units)**

| File | Symbol / target | Change |
|---|---|---|
| `src/backend/apps/moderation/admin_actions.py` → `src/backend/apps/moderation/services/admin_actions.py` | `approve_ad`, `reject_ad`, `ban_user`, `bulk_approve`, `bulk_ban_users`, `bulk_reject`, `bulk_delete` | **The move.** `git mv` semantics; the module body is byte-identical |
| `src/backend/apps/moderation/services/__init__.py` | — | **Unchanged, and must stay empty of new re-exports** unless it already exports service symbols — verify before adding |
| `src/backend/apps/ads/admin.py` | the module-level import of `bulk_approve`, `bulk_ban_users`, `bulk_delete`, `bulk_reject` | One import line |
| `src/backend/apps/moderation/views/api_bulk.py` | the module-level import of the same module | One import line. **Do not restructure the module** — phase 05's `TestBulkLockingStructure` inspects it |
| `src/backend/apps/moderation/views/review.py` | three **function-local** imports inside `approve_ad`, `reject_ad`, `ban_user` | Promoted to module scope, pointing at the new path. **Also BLOCKs 5 and 7's file** |
| `src/backend/apps/moderation/tests/test_admin_actions.py`, `test_moderation_views.py::TestModerationReviewLocking` | the module path they import | **Green unchanged** — the move must be invisible to them |

**Binding constraints**

1. **One commit, three importers, explicit `git add` of the named paths.** A half-moved
   module is an import error in one of the two processes.
2. **The module body is byte-identical.** No rename, no signature change, no docstring
   rewrite, no `logger` added, no reformatting. The move is the whole change.
3. **`apps/ads/admin.py` importing `apps.moderation.*` is a layering inversion** (an `ads`
   admin depending on moderation internals). **Phase 10 records it and does not redesign
   it** — that is a phase-09-shaped question, and phase 09's plan (which appeared while this
   one was written, C-8) is the natural reader of it.
4. **Do not touch `apps/moderation/apps.py` or `apps/moderation/admin.py`.** The move is
   *from* the app root, not of the app's `admin.py`.
5. **The three deferred imports become module-level** — that is the point, and BLOCK 13's
   gate depends on it. Do not replace them with another function-local import.
6. **No behaviour change is permitted.** Every moderation action must reach the database
   exactly as before; `test_admin_actions.py` and `TestModerationReviewLocking` are the
   assertion.
7. **External gate:** phase 05 **BLOCK 3** (`bulk_approve`'s filter, `approve_ad`'s guard) and
   phase 06 **BLOCK 16** (reason redaction) hold this file. The coordinator sequences; the
   move lands before or after both, **never during**.

**Implementor task**

```yaml
id: task_10_b12_admin_actions_move
title: "Move admin_actions into moderation/services (10-CQ-010)"
priority: high
depends_on: [task_10_b07_reject_reason_boundary]
source_reference: ".ai/plans/10-code-quality-remediation.md"
source_section: "BLOCK 12 - Move admin_actions.py into services/"
source_blocks: ["BLOCK 12"]
description: >
  apps/moderation/admin_actions.py sits at the app root, imports nothing from
  apps/moderation/views/* - so there is no import cycle to break - and its own docstring
  already calls it a service, while views/api_bulk.py imports the same module at module
  level. Move it to apps/moderation/services/admin_actions.py, update exactly three
  importers in one commit (apps/ads/admin.py, apps/moderation/views/api_bulk.py, and the
  three function-local imports in apps/moderation/views/review.py, which become module
  level), and change nothing else. The apps -> moderation import in the ads admin is a
  layering inversion: record it, do not redesign it.
goals:
  - "put the module where its own docstring says it belongs"
  - "delete the three arbitrary deferred imports as a side effect"
  - "change no behaviour and no module body"
files:
  - path: "src/backend/apps/moderation/services/admin_actions.py"
    targets:
      - type: function
        name: approve_ad
      - type: function
        name: bulk_approve
  - path: "src/backend/apps/moderation/views/review.py"
    targets:
      - type: function
        name: approve_ad
      - type: function
        name: reject_ad
      - type: function
        name: ban_user
  - path: "src/backend/apps/moderation/views/api_bulk.py"
    targets: [{type: module, name: api_bulk}]
  - path: "src/backend/apps/ads/admin.py"
    targets: [{type: module, name: admin}]
changes:
  - action: move_file
    description: >
      git mv apps/moderation/admin_actions.py to apps/moderation/services/admin_actions.py
      with a byte-identical body, then update the three importers to the new path and
      promote review.py's three function-local imports to module level.
acceptance_criteria:
  - "apps/moderation/admin_actions.py no longer exists and the services path does"
  - "apps/ads/admin.py, apps/moderation/views/api_bulk.py and review.py all import the new path"
  - "no function-local import of admin_actions remains in review.py"
  - "the moved module body is byte-identical - no rename, reformat or docstring rewrite"
  - "test_admin_actions.py and TestModerationReviewLocking are green UNCHANGED"
  - "apps/moderation/apps.py and apps/moderation/admin.py are untouched"
  - "the commit body records the ads -> moderation layering inversion it did not fix"
tests_to_run:
  - "src/backend/apps/moderation/tests/test_admin_actions.py"
  - "src/backend/apps/moderation/tests/test_moderation_views.py"
  - "src/backend/apps/ads/tests/test_auth_nav.py"
```

**Tests required** — none new. A move that changes no behaviour is verified by the suites
that already exercise every action: `test_admin_actions.py` (the four bulk actions and the
three single-ad actions), `TestModerationReviewLocking` (which source-inspects the three
**views**, not the service — so a mistake in the move shows up as an import error, not a
silent pass), and `test_auth_nav.py` (the `ads` admin page that imports the bulk actions).

**Risk and rollback**

- *Implementation risk:* a half-moved module. Mitigation: binding constraint 1, and both
  processes import at start-up, so `django check` in either compose project is the smoke test.
- *Coordination risk:* **five phases hold this file** (03, 04 BLOCK 9, 05 BLOCK 3,
  06 BLOCK 16, 07 BLOCK 11). The coordinator sequences; the Implementor re-reads the file
  immediately before editing and **stops and reports** if it carries another agent's
  uncommitted change.
- *Regression risk:* a restructured `api_bulk.py` "while we are here". Binding constraint —
  one import line, nothing else; phase 05's `TestBulkLockingStructure` is the tripwire.
- *Rollback:* a straight revert of a move plus three import lines. No data, no schema.

---

### BLOCK 13 — Turn on the deferred-import rule, with the exclusions it needs (CQ-010, lint half)

| | |
|---|---|
| **Findings owned** | `CQ-010` (LOW) — the gate half |
| **Class** | **mechanical** — one config file, one rule, one exclusion list |
| **Depends on** | BLOCK 12 (so the three arbitrary deferrals in `review.py` are already gone and the rule's own value is demonstrable) |
| **Blocks** | nothing; this is the plan's last config edit |
| **Priority** | P2 |
| **Risk level** | **LOW** in isolation — **HIGH if the exclusion list is wrong**, because a red-on-arrival gate gets disabled within a week |
| **Required agents** | **Auditor · Researcher · Planner · Validator.** The Researcher produces the exclusion list; the Validator confirms the gate is green **and** that a genuine new deferral is caught |

**Why this is not part of BLOCK 12.** BLOCK 12 is a file move with a five-phase
coordination problem. Folding a lint gate into it would make the most contended commit in
the plan also the one that turns a CI job red — and the two failures are unrelated and need
independent reverts. Splitting them costs one commit and buys a clean revert path.

**File surface (semantic units)**

| File | Symbol / target | Change |
|---|---|---|
| `pyproject.toml` | `[tool.ruff.lint] select` (currently `["E","F","I","B","UP","G"]`) | Add `"PLC0415"` |
| `pyproject.toml` | `[tool.ruff.lint.per-file-ignores]` (**does not exist yet**) | Create it with the measured exclusion list |

**The exclusion list must be measured, not guessed.** ✔ Re-measured at the anchor: **96
function-local imports across 47 production files.** The legitimate clusters are:

| Pattern | Where | Why it must be excluded |
|---|---|---|
| `AppConfig.ready()` signal registration | `**/apps.py` | Django **mandates** the deferred import to avoid `AppRegistryNotReady`. ~7 sites |
| CLI / bootstrap load-order control | `migrate_locked`, the scheduler, `backfill_translations`, the seed service, the catalog builder | Deliberate ordering for migration and lock acquisition. ~21 sites |
| Signal-handler modules | `categories/signals.py`, `moderation/signals.py`, `lookups/signals.py` | Conventional for Django signal modules |
| Model-load deferral inside `Ad.save()` | `apps/ads/models.py` | **Genuinely unnecessary** — but deleting it is a different change, and the finding's own judgement is that it is not one of the "big" clusters |
| `handlers/login.py`'s two deferrals | **Documented as load-bearing** for `handle_login_orm`'s closure shape | Phase 01 shipped that documentation deliberately |

**Binding constraints**

1. **`ruff check src/` must be green after the change.** A red gate on arrival means a
   missing exclusion, **not** a defect to suppress by adding `noqa` at 96 sites.
2. **No `# noqa: PLC0415` is added anywhere.** The exclusions are file-scoped
   `per-file-ignores`, and the only legitimate per-line need is one the Researcher
   justifies in the commit body.
3. **No `scripts/lint_no_deferred_imports.py`.** `ruff`'s built-in rule does this and `ruff`
   is already a dependency. A custom script is a second implementation of a check the
   project already has.
4. **No deferred import is fixed in this block.** The `Ad.save()` deferral and any other
   genuine offender are a separate change; enabling the gate and cleaning the tree in one
   commit makes the gate untrustworthy.
5. **`fix = false` at `[tool.ruff]` is not touched.** "do NOT auto-fix by default" is a
   deliberate project setting.
6. **The commit must show the before/after counts** — the finding, not the report's number.

**Implementor task**

```yaml
id: task_10_b13_plc0415
title: "Enable ruff PLC0415 with a measured exclusion list (10-CQ-010)"
priority: low
depends_on: [task_10_b12_admin_actions_move]
source_reference: ".ai/plans/10-code-quality-remediation.md"
source_section: "BLOCK 13 - Turn on the deferred-import rule"
source_blocks: ["BLOCK 13"]
description: >
  There are 96 function-local imports across 47 production files, and the vast majority are
  correct engineering: AppConfig.ready() signal registration, CLI/bootstrap load-order
  control, and Django signal modules. Enabling PLC0415 without exclusions fires on all of
  them and the gate gets disabled within a week. Add PLC0415 to the ruff select list and
  create a per-file-ignores list covering the measured legitimate patterns. Fix no deferred
  import in this commit, add no noqa, and do not write a custom lint script.
goals:
  - "make an arbitrary function-local apps.* import visible to review"
  - "keep the gate green on arrival with file-scoped exclusions, not noqa comments"
  - "change no deferred import"
files:
  - path: "pyproject.toml"
    targets:
      - type: assignment
        name: "tool.ruff.lint.select"
      - type: table
        name: "tool.ruff.lint.per-file-ignores"
changes:
  - action: modify_code
    description: >
      Add "PLC0415" to [tool.ruff.lint].select and create [tool.ruff.lint.per-file-ignores]
      with entries for the AppConfig apps.py files, the CLI/bootstrap command modules and
      the signal modules, each with a one-line reason in the commit body.
acceptance_criteria:
  - "uv run ruff check src/ exits 0 with PLC0415 enabled"
  - "no '# noqa: PLC0415' exists anywhere in the repository"
  - "every exclusion entry is justified in the commit body by a pattern, not a file count"
  - "no deferred import was added or removed in this commit"
  - "the commit body states the re-measured deferred-import count and the file count"
  - "no custom lint script was created and [tool.ruff] fix = false is unchanged"
tests_to_run: []
```

**Tests required** — none. This is a lint-configuration change; its "test" is that
`uv run ruff check src/` and `uv run basedpyright src/` are green, plus **one positive
control the Validator runs manually**: add a deliberate function-local import in a scratch
file under a non-excluded path, confirm `PLC0415` fires, then remove it. A gate that has
never been seen to fire is not a gate.

**Risk and rollback**
- *Implementation risk:* the gate is red on arrival and someone "fixes" it with 96 `noqa`
  comments. Binding constraints 1 and 2 make that a review rejection.
- *Rollout risk:* a future legitimate deferral now needs an exclusion entry, which is the
  intended friction. Say so in the commit body.
- *Rollback:* a straight revert of two lines in one file. No code depends on it.

---

### BLOCK 14 — One listings-context builder, two views (CQ-015)

| | |
|---|---|
| **Findings owned** | `CQ-015` (MEDIUM, `SPEC-DEVIATION`) |
| **Class** | **behavioural** — zero intended behaviour change, the largest mechanical diff in the report, and ~10 test files pin the contract |
| **Depends on** | nothing in-plan (Q8 must be answered first). **External: phase 08 BLOCK 1** holds `listings_query.py` |
| **Blocks** | nothing in-plan |
| **Priority** | P1 |
| **Risk level** | **MEDIUM** — wide surface, no intended behaviour change, so every failure is a surprise |
| **Required agents** | **Auditor · Researcher · Planner · Validator.** The Researcher enumerates the 20 shared keys and the 6 search-only keys; the Validator confirms both views render the same contract |

**Decision required before implementation — Q8: is `build_listings_context()` a service or a
helper beside `ListingsQuery`?**

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | A **service function** in a new `apps/ads/services/listings_context.py` | **Gains:** a named home next to `ListingsQuery`; the two views import it symmetrically; room for the 20-key contract to be documented in one docstring. **Costs:** a new module whose only content is one function, and a decision about which app owns it (`ads` because `listings.py` is the smaller consumer) |
| **(b)** | One more function in `apps/ads/services/listings_query.py`, beside `ListingsQueryParams` and `ListingsQuery` | **Gains:** **zero new modules**, and the context builder sits beside the DTO it consumes — the two halves of the same input contract. **Costs:** **phase 08 BLOCK 1 holds that file** for the `feature_slugs` bound, so this is a cross-phase ordering, not a free choice. `ListingsQuery` is already the "build the query for these params" service; the context is the adjacent half |
| **(c)** | Duplicate the function into `apps/search/services/` and import it from both | **Gains:** neither app owns it. **Costs:** a shared module with no owning app, imported by two apps — the shape of a service locator in miniature. **Rejected** |

**The Implementor may not choose**, and under option (b) must not edit `listings_query.py`
while phase 08 BLOCK 1 holds it.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/ads/views/listings.py` | `listings`, `_suggest_category` | The 11-field DTO build and the 20-key context. **Also BLOCK 15's file** |
| `src/backend/apps/search/views/search.py` | `search`, the 11-field DTO build and the **26**-key context | 20 keys shared; **6 are search-only and must stay search-only** |
| `src/backend/apps/ads/services/listings_context.py` **(new, if Q8(a))** or `apps/ads/services/listings_query.py` **(if Q8(b))** | `build_listings_context(...)` | One function, one docstring stating the 20-key contract |
| `src/backend/apps/ads/tests/test_listings_context.py` | the 7 canonical keys, the param mapping, the breadcrumb/`suggested_category` cases, the template render, and `test_listings_query_params_rejects_unknown_key` | **Must be green.** The last one is why the DTO is not in scope here |
| `src/backend/apps/search/tests/` and `src/backend/apps/ads/tests/` | `test_search_view.py`, `test_search_query_count.py`, `test_search_slo.py`, `test_sort_on_search_results.py`, `test_listings_sort.py`, `test_filter_search_combine.py`, `test_filter_url_reset.py`, `test_features_filter.py`, `test_breadcrumbs_render.py` | ~10 files pin the two templates and the DTO **from both sides** |

**Binding constraints**

1. **All 20 shared keys are present on both views; the 6 search-only keys stay on `search`
   only.** A shared key that silently disappears from `/` is invisible until a template
   renders empty.
2. **The DTO build is not changed.** The 11 `ListingsQueryParams` arguments map 1:1 from the
   same `request.GET` expressions; `search.py` hoists them into locals first and
   `listings.py` does not. That cosmetic difference is **not** the finding and may be
   normalised as a consequence of the extraction — or left alone. Either is acceptable;
   changing the *mapping* is not.
3. **`ListingsQueryParams` is untouched.** `extra="forbid"` and its validators are phase 08
   BLOCK 1's surface, and `test_listings_query_params_rejects_unknown_key` pins them.
4. **The context is reformatted to one key per line** as a natural consequence of the
   extraction. That is **not** filed as a finding and must not be used to justify unrelated
   reformatting of the same files.
5. **`_suggest_category` is BLOCK 15's.** This block must not touch it.
6. **`ListingsQuery.build_queryset` is read-only.** Its visibility terms are phase 06 /
   phase 08's surface.
7. **Query counts and the SLO must not move.** `test_search_query_count.py` and
   `test_search_slo.py` are the tripwires, and a "harmless" context change that adds a query
   is a regression.

**Implementor task**

```yaml
id: task_10_b14_listings_context
title: "Extract one build_listings_context for both views (10-CQ-015)"
priority: high
depends_on: []
source_reference: ".ai/plans/10-code-quality-remediation.md"
source_section: "BLOCK 14 - One listings-context builder, two views"
source_blocks: ["BLOCK 14"]
description: >
  apps/ads/views/listings.py and apps/search/views/search.py build the same 11-field
  ListingsQueryParams from the same request.GET expressions and then build template contexts
  of which 20 keys are identical - listings.py's entire context is a strict subset of
  search.py's - for the same two templates. Extract one build_listings_context() per the
  Q8-recorded option, use it from both views, keep the 6 search-only keys on search, and
  leave ListingsQueryParams and ListingsQuery.build_queryset untouched. Reformat the context
  to one key per line as a consequence, not as a change.
goals:
  - "express one template contract once instead of twice"
  - "keep all 20 shared keys on both views and the 6 search-only keys on search"
  - "change no query, no query count and no sort or filter behaviour"
files:
  - path: "src/backend/apps/ads/views/listings.py"
    targets: [{type: function, name: listings}]
  - path: "src/backend/apps/search/views/search.py"
    targets: [{type: function, name: search}]
  - path: "src/backend/apps/ads/services/listings_query.py"
    targets: [{type: class, name: ListingsQuery}]
changes:
  - action: add_code
    description: >
      build_listings_context(...) returning the 20 shared keys, per the Q8 option, with a
      docstring that states the contract and names the search-only keys as not-shared.
  - action: modify_code
    description: >
      Replace both inline context dicts with the call; on search, merge the 6 search-only
      keys on top. Reformat the shared context one key per line.
acceptance_criteria:
  - "all 20 shared keys are present in the context of BOTH / and /search/"
  - "the 6 search-only keys are present on /search/ only"
  - "test_listings_context.py is green UNCHANGED, including test_listings_query_params_rejects_unknown_key"
  - "test_search_query_count.py and test_search_slo.py are green - no query was added or removed"
  - "the sort, filter and breadcrumb suites from both sides are green"
  - "ListingsQueryParams and ListingsQuery.build_queryset are unchanged"
  - "the commit body names the Q8 option"
tests_to_run:
  - "src/backend/apps/ads/tests/test_listings_context.py"
  - "src/backend/apps/search/tests/test_search_view.py"
  - "src/backend/apps/search/tests/test_search_query_count.py"
  - "src/backend/apps/search/tests/test_search_slo.py"
  - "src/backend/apps/ads/tests/test_sort_on_search_results.py"
  - "src/backend/apps/ads/tests/test_filter_search_combine.py"
  - "src/backend/apps/ads/tests/test_breadcrumbs_render.py"
```

**Tests required**
1. **The contract assertion this block exists to make true** — render `/` and `/search/` with
   the same query parameters and assert the **same 20 keys** reach the template context on
   both, and that the 6 search-only keys are absent from `/`. That is the test the report
   asks for and the one that would have caught the duplication being real.
2. **The positive control** — a filter, a sort and a breadcrumb survive the extraction
   identically on both views, including the `None` cases
   (`test_breadcrumb_category_none_without_resolved_category`).
3. **The unchanged suites** — the ~10 files that already pin the two templates must be green
   **without modification**. If one of them needs an edit, the extraction changed something.

**Risk and rollback**
- *Implementation risk:* a key that exists on `search` and is silently absent from the shared
  builder. Mitigation: test 1 asserts the key set, not the values.
- *Performance risk:* an extra query smuggled into the "context builder". Mitigation:
  `test_search_query_count.py` and `test_search_slo.py` are in `tests_to_run` for exactly
  this.
- *Cross-phase:* Q8(b) touches `listings_query.py`, which **phase 08 BLOCK 1** holds. Under
  (b), BLOCK 14 lands after phase 08 BLOCK 1 and re-reads the file.
- *Rollback:* a straight revert. No data, no schema.

---

### BLOCK 15 — One fuzzy ladder, one cutoff (CQ-011)

| | |
|---|---|
| **Findings owned** | `CQ-011` (MEDIUM, `SPEC-DEVIATION`) |
| **Class** | **behavioural** — a user-visible suggestion can change, and a shipped test re-derives the constant in-test |
| **Depends on** | BLOCK 14 (`ads/views/listings.py` is BLOCK 14's first, BLOCK 15's second) |
| **Blocks** | nothing in-plan |
| **Priority** | P1 — but **last of the medium blocks**: it is the only one whose scope is still undetermined |
| **Risk level** | **MEDIUM**, and it rises to HIGH if Q1 is answered as option (b) — a new `ads → search` edge |
| **Required agents** | **Auditor · Researcher · Planner · Validator — all four.** Three open questions gate it |

**Three decision gates. All three must be written down before this block starts.**

**Q1 — where does the shared ladder live?** (see §0.5; the full options are in the block's
gate record)

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | The **tier ladder only** in `apps/categories/services/fuzzy.py`, with the name list **injected by the caller** | **Gains:** `categories` never imports `search`, so no dependency is inverted; the taxonomy owns its matching policy. **Costs:** the tier code is split from the name list it needs, so the caller must pass a list it got from `apps/search/services/category_fuzzy.py` — and `ads → search` still appears at the call site in `listings.py` |
| **(b)** | The whole thing in `apps/search/services/`, and `ads/views/listings.py` imports it | **Gains:** one owner, one file, the name list and the ladder stay together; the warm-cache zero-SELECT property is trivially preserved. **Costs:** a **new `ads → search` cross-app edge** on a file phase 05 §5.2 and phase 15 also touch; `apps/ads` imports nothing from `apps.search` today |
| **(c)** | Align the cutoff constant only; leave the two ladders in place | **Gains:** the smallest change that removes the *divergence* while accepting the structural duplication. **Costs:** the "user types an exact slug and `/` does not resolve it" asymmetry survives; the finding is only half closed. **A real option, not a strawman** |

**Q6 RESOLVED 2026-10-03 (Product Owner) — the unified cutoff is 0.8** | **Q7 — does
`suggest_city` join? — STILL A PLANNER RULING**

**Q6 is answered: 0.8.** `test_search_fuzzy.py::TestFuzzyEquivalence` **stays green and
unchanged** — it re-computes `cutoff=0.8` in-test, so the product decision and the shipped test
now agree and **project rule 2 is not invoked at all**. The **0.6 site** —
`ads/views/listings.py::_suggest_category`, which runs fuzzy against raw slugs at `cutoff=0.6`
with no exact tier — **aligns to 0.8**. The Implementor may **not** re-choose.

**What the ruling removes.** The plan's contingency for a 0.6 outcome — *"the test is corrected
because the behaviour was decided, and the commit body must say which side of rule 2 it invoked
and why"* — is **moot and must not be exercised**. There is **no test rewrite in this block**, and
a commit that rewrites `TestFuzzyEquivalence` is reverting a Product Owner decision.

**Q7 is NOT a Product Owner decision and is unchanged.** Whether `suggest_city`
(`locations/services/city_suggestions.py`, with its own `_CUTOFF: Final[float] = 0.6` and its own
shipped test) joins the unification stays a **Planner ruling**: joining it expands BLOCK 15 to a
fourth module; not joining it is defensible on the grounds that a city is not a category and
"share one policy" is a category of its own. **But the ruling sets the bar Q7 must clear:** if
`suggest_city` stays separate, **its surviving 0.6 must be justified against this 0.8 product
decision in the commit body** — stated as a deliberate, entity-specific divergence, not as an
oversight. That justification is now an **acceptance criterion**, so Q7 can no longer be
answered by leaving the value in place and saying nothing.

**What this block is not.** It is **not** a recall fix. On `/search/?category=<slug>` the
category is resolved by the **breadcrumb** path and a typo merely echoes the raw string; the
fuzzy ladder is reached from the **`?q=`** path only (§0.4). The finding survives as
*two divergent ladders over one already-shared name list* — a consistency and
maintainability defect, which is exactly what its MEDIUM severity supports.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/search/services/category_fuzzy.py` | `get_active_category_names`, `_fuzzy_names_cache_key`, `FUZZY_NAMES_CACHE_TTL` | **An existing asset — do not duplicate and do not re-implement the name list.** Phase 08 BLOCK 6 region |
| `src/backend/apps/search/views/search.py` | `_fuzzy_category_match` (3 tiers: slug exact, locale-name exact, fuzzy), `_fuzzy_match_by_name` (`cutoff=0.8`) | **Also BLOCK 14's file** |
| `src/backend/apps/ads/views/listings.py` | `_suggest_category` (fuzzy against raw slugs, `cutoff=0.6` → **aligns to the shared 0.8 constant** per the Q6 ruling, **no exact tier**) | **Also BLOCK 14's file.** The local `0.6` literal is removed in favour of the shared constant — the point of the block |
| `src/backend/apps/categories/services/fuzzy.py` **(new, if Q1(a))** | the tier ladder | Name the list parameter; the caller supplies it |
| `src/backend/apps/locations/services/city_suggestions.py` | `suggest_city`, `_CUTOFF` | **Only if Q7 says join** |
| `src/backend/apps/search/tests/test_search_fuzzy.py` | `TestFuzzyEquivalence` (10 pairs), `TestFuzzyQueryCount` (2), `TestFuzzyCategoryMatch` (2), `TestFuzzyInvalidation` (2) | `TestFuzzyQueryCount` is the one that forbids re-implementing the name list |
| `src/backend/apps/ads/tests/test_listings_context.py` | `test_breadcrumb_category_none_without_resolved_category` | Safe today only because the taxonomy is empty in that test |

**Binding constraints**

1. **The shared module keeps using `get_active_category_names`.** Re-implementing the name
   list turns `TestFuzzyQueryCount` red (cold cache = one SELECT, warm cache = zero) — and
   that test is the shipped guard on the caching contract.
2. **The exact tiers are preserved.** `TestFuzzyCategoryMatch::test_slug_match` and
   `::test_exact_name_match_uses_cached_list` pin the first two tiers of `search.py`'s
   ladder. Unification must not remove them, and — the actual point of the finding — should
   give them to `listings.py` as well under Q1(a) or (b).
3. **`apps/categories` must not import `apps.search` under Q1(a).** That is the whole reason
   the name list is injected. A grep-level check belongs in the review, not a test.
4. **The cutoff is a single named constant, valued 0.8** *(Q6 resolved 2026-10-03)*, not two
   literals — and **not** a per-call-site literal. `listings.py::_suggest_category`'s 0.6 aligns
   to the same constant; it does not keep a local literal.
5. **Under Q1(b)**, the new `ads → search` edge is recorded in the commit body and in §5.3,
   because `apps/ads` imports nothing from `apps/search` today and that is a structural
   change made by a code-quality block.
6. **The fuzzy suggestion must not become slower.** The cold/warm query-count tests are the
   tripwires, and an exact tier added to `listings.py` must not add a query per request.
7. **`_suggest_category`'s existing contract is preserved**: an unresolvable slug still
   yields `None`.

**Implementor task**

```yaml
id: task_10_b15_fuzzy_ladder
title: "Unify the category fuzzy ladder and its cutoff (10-CQ-011)"
priority: high
depends_on: [task_10_b14_listings_context]
source_reference: ".ai/plans/10-code-quality-remediation.md"
source_section: "BLOCK 15 - One fuzzy ladder, one cutoff"
source_blocks: ["BLOCK 15"]
description: >
  search.py::_fuzzy_category_match runs a three-tier ladder - slug exact, locale-name exact
  over the cached active-category list, then difflib at cutoff 0.8. listings.py::_suggest_category
  runs fuzzy against raw slugs at cutoff 0.6 - which ALIGNS TO 0.8 per the Q6 ruling of
  2026-10-03 - with no exact tier at all, using the same name
  list. The report proposes apps/categories/services/fuzzy.py, which would require a
  categories -> search import; that is rejected. Record the Q1, Q6 and Q7 answers, then ship
  one ladder and one named cutoff, keeping the cold/warm query-count properties. The
  equivalence test re-derives 0.8 in-test and must be left UNCHANGED - it now matches the
  decided cutoff, so no project-rule-2 rewrite is invoked.
goals:
  - "express the category fuzzy ladder once, with one named cutoff valued 0.8"
  - "keep the cached name list as the single source of the candidate names"
  - "give the browse path the exact-match tiers it is missing"
files:
  - path: "src/backend/apps/search/views/search.py"
    targets:
      - type: function
        name: _fuzzy_category_match
      - type: function
        name: _fuzzy_match_by_name
  - path: "src/backend/apps/ads/views/listings.py"
    targets: [{type: function, name: _suggest_category}]
  - path: "src/backend/apps/search/services/category_fuzzy.py"
    targets: [{type: function, name: get_active_category_names}]
  - path: "src/backend/apps/categories/services/fuzzy.py"
    targets: [{type: module, name: fuzzy}]
  - path: "src/backend/apps/search/tests/test_search_fuzzy.py"
    targets:
      - type: class
        name: TestFuzzyEquivalence
      - type: class
        name: TestFuzzyQueryCount
changes:
  - action: add_code
    description: >
      Per Q1(a): the tier ladder in apps/categories/services/fuzzy.py with the candidate name
      list injected by the caller. Per Q1(b): the ladder beside get_active_category_names in
      apps/search/services/. One named cutoff constant, valued 0.8 per the Q6 ruling of 2026-10-03.
  - action: modify_code
    description: >
      Route both call sites through the shared ladder. Align listings.py::_suggest_category's
      0.6 to the shared 0.8 constant. DO NOT update TestFuzzyEquivalence's in-test cutoff - Q6
      resolved as 0.8, the test already asserts 0.8, and it must be green UNCHANGED. No
      project-rule-2 rewrite is invoked anywhere in this block.
acceptance_criteria:
  - "one ladder and one named cutoff serve both / and /search/, and the cutoff is 0.8"
  - "an exact category slug on / resolves to that category - it does not today"
  - "TestFuzzyQueryCount is green UNCHANGED: one category SELECT cold, zero warm"
  - "TestFuzzyCategoryMatch is green UNCHANGED - both exact tiers survive"
  - "TestFuzzyEquivalence is green UNCHANGED - it was NOT rewritten, and the commit body states that project rule 2 was not invoked"
  - "listings.py::_suggest_category no longer carries a local 0.6 literal; it uses the shared 0.8 constant"
  - "if Q7 kept suggest_city separate, its surviving 0.6 is justified in the commit body against this 0.8 product decision, as an entity-specific divergence rather than an oversight"
  - "apps/categories imports nothing from apps/search"
  - "an unresolvable slug still yields suggested_category None"
  - "the commit body records Q1, Q6 (with its date 2026-10-03) and Q7"
tests_to_run:
  - "src/backend/apps/search/tests/test_search_fuzzy.py"
  - "src/backend/apps/ads/tests/test_listings_context.py"
  - "src/backend/apps/locations/tests/test_city_suggestions.py"
  - "src/backend/apps/search/tests/test_search_query_count.py"
```

**Tests required**
1. **The equivalence that makes unification meaningful** — one `(locale, query)` case table
   drives **both** `/` and `/search/` and asserts the same resolution. Today they differ, and
   that difference *is* the finding.
2. **The exact-tier gain** — an exact slug and an exact localised name both resolve on `/`,
   and a near-miss still resolves through the fuzzy tier. This is the user-visible
   improvement and the only one.
3. **The cache control** — cold: exactly one category SELECT; warm: zero. If a new exact
   tier adds a query, this is what catches it.
4. **The negative control** — an unresolvable slug still yields `None` on both paths, and
   `test_breadcrumb_category_none_without_resolved_category` stays green.
5. **Under Q7 = join**, `suggest_city` keeps its own behaviour and its own test is green
   unchanged.

**Risk and rollback**
- *Implementation risk:* **Q1(b) creates a new cross-app dependency** from a code-quality
  block. That is the single most consequential decision in this plan after BLOCK 16, and it
  is why Q1 is a gate with three argued options rather than a note.
- *Regression risk:* a cutoff change alters suggestions for borderline queries. Mitigation:
  the equivalence case table; the change is deliberate, not incidental.
- *Test risk:* rewriting `TestFuzzyEquivalence` to match the code instead of the decision.
  Mitigation: the table is derived from Q6 and the commit body must state it.
- *Rollback:* a straight revert. `suggest_city` and the taxonomy are untouched.

---

### BLOCK 16 — The coordinated change set: `ad_edit`, `submit_ad`, `AdEditInput` (CQ-001, CQ-008, CQ-009)

| | |
|---|---|
| **Findings owned** | `CQ-001`, `CQ-008` (MEDIUM each), `CQ-009` (MEDIUM) |
| **Class** | **behavioural** — a data-loss fix, a 500→400 change, and two structural extractions |
| **Depends on** | **External, and non-negotiable:** `AUTHZ-007` → `AUTHZ-002` (phase 15) · **phase 03 BLOCK 5** · **phase 05 BLOCKs 2 and 8**. In-plan: BLOCK 2 (`apps/ads/services/__init__.py` must exist first) |
| **Blocks** | nothing in-plan. **Everything else in phases 03/05/07/15 that touches `edit.py` or `submission.py`** |
| **Priority** | P1 by severity, **last by order** |
| **Risk level** | **HIGH** — the most contended three-file change in the entire plan set |
| **Required agents** | **Auditor · Researcher · Planner · Validator — all four** |

**This is one commit, one owner, one review, three files:**
`apps/ads/views/edit.py` · `apps/ads/services/submission.py` · `apps/ads/services/edit_ad.py`
(new). Splitting it is precisely the failure the report's §A describes: each of the three
findings relocates code the other two's fix depends on, and a split ships the TOCTOU window
*into* the new module where it is harder to see.

**External ordering, which is stricter than the report's §A**

The report says: `AUTHZ-007 → AUTHZ-002 → CQ-001 → CQ-008`, as one change set. That was
correct when it was written. It is **now insufficient**, because four more parties hold
`ad_edit`:

| Order | Owner | What it owns here |
|---|---|---|
| 1 | **phase 03 BLOCK 5** | adds a `SET LOCAL lock_timeout` statement inside `ad_edit`'s `atomic()` block |
| 2 | **phase 05 BLOCK 2** | the price/photo `elif` arm inside `ad_edit` |
| 3 | **phase 05 BLOCK 8** | the catch-all `else` arm inside `ad_edit` |
| 4 | **phase 15 `AUTHZ-007`** | the ownership assertion on the locked instance inside `atomic()` |
| 5 | **phase 15 `AUTHZ-002`** | `submit_ad`'s `user_id` guard (**HIGH**) |
| 6 | **phase 10** | **this block** |

**If phase 03 BLOCK 5 or phase 05 BLOCKs 2/8 have not landed, BLOCK 16 does not start.**
If the coordinator judges the serialisation too expensive, the only alternative is to **fold
BLOCK 16 into that change set** — never to run them in parallel. Two source-inspection
tests plus one hard-count test mean a wrong order produces a red gate rather than a silent
defect, which is good, but only if the ordering was deliberate.

**Decision required before implementation — Q3: what does `ad_edit` return on a Pydantic
`ValidationError`?**

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | **400** | **Gains:** least surprising, no new string, no template change. **Costs:** a seller who submitted a malformed edit loses the form's other values unless the view re-renders; the form is a full page, not a modal |
| **(b)** | Re-render `ads/edit.html` with an error message in the **existing** `"error"` context key | **Gains:** the seller keeps the form and the error is visible; the error slot already exists, so the template change is small. **Costs:** a new user-visible string (non-empty `ru` **and** `bs`), and the re-render must not lose the form's current values |
| **(c)** | Leave the uncaught `ValidationError` to become a 500 | **Costs:** **not an option.** A 500 on a seller-submitted form is a defect, not a design |

**The Implementor may not choose**, and the current behaviour — an uncaught
`ValidationError` inside `transaction.atomic()` surfacing as a 500 — is the single riskiest
part of `CQ-009` and is **not** mentioned in the report.

**What this commit must contain, exactly**

1. **`edit_ad` in `apps/ads/services/edit_ad.py`**, following the pattern already in the same
   package: `submission.py` holds `SubmitAdInput`, `AdEditInput` and `submit_ad` as the
   shared bot↔web seam, and `edit.py` imports it at module level. `edit_ad` sits next to it.
2. **The ownership assertion on the locked instance inside the transaction**, copying the
   shape `ad_archive` and `ad_reactivate` already use (locked fetch → assert inside
   `atomic()`). This satisfies `AUTHZ-007` **by construction** rather than by a follow-up
   patch.
3. **The hoisted `SubmitAdInput` built with `user_id=request.user.id` — never
   `ad.user_id`.** Copying `ad.user_id` verbatim makes `AUTHZ-002`'s guard permanently
   tautological on the web path *and* makes it look load-bearing because both branches now
   share it. Phase 15's regression test ("the web caller now passes `request.user.id`,
   asserted explicitly") is the only thing that catches it.
4. **The single authorized locked instance used everywhere** — including the reactivation
   branch and the error branches, which currently re-fetch unlocked (**two** sites, not the
   three the report lists — C-6).
5. **`AdEditInput.title` / `.description` required with `min_length=1`**, and the Q3 response.
6. **`submit_ad` split** so the file/medium orchestration separates, **with
   `AUTHZ-002`'s guard landing in the same commit** so it is never relocated twice.
7. **No `ErrorPage` enum. No `_build_submit_input` helper** (§6). The two branches share one
   local `command` variable; that is two lines and no new name.

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/ads/views/edit.py` | `ad_edit`, `_apply_price_change` (imported by `test_edit.py::TestApplyPriceChangeDelegation` — **keep it importable from here or re-point the test**), `_text_fields_changed`, `ad_archive`, `ad_reactivate`, and the GET dispatch branch | The most contended function in the plan set |
| `src/backend/apps/ads/services/submission.py` | `SubmitAdInput`, `AdEditInput`, `submit_ad` | "The single most contested file across the whole plan set" (phase 07 §5.3); eight claims |
| `src/backend/apps/ads/services/edit_ad.py` **(new)** | `edit_ad` | Lands in the package that got its `__init__.py` in **BLOCK 2** |
| `src/backend/apps/ads/tests/test_edit.py` | `TestReactivationStatusTransition`, `TestReactivationAutoModerate` (pass **and** fail), `TestReactivationCurrencyKeepCurrent`, `TestReactivationPriceNormalized`, `TestReactivationTextUpdated`, `TestPublishedTextEdit` (7), `TestApplyPriceChangeDelegation`, `TestEditAuthorization`, `TestEditGetPath`, `TestAdArchive`, `TestAdArchiveGetRejected`, `TestAdReactivateDirect`, `TestEditOtherStatusDirectSave` | **Every branch is covered. No test omits `title` — that gap is this block's to fill** |
| `src/backend/apps/ads/tests/test_edit_views_locking.py` | `TestEditViewsLocking` — `test_ad_edit_uses_select_for_update_and_atomic`, `test_ad_edit_get_path_not_locked` (`count("select_for_update") == 1`), `test_submit_ad_uses_select_for_update_and_atomic`, `test_submit_ad_fetches_inside_atomic` | **Re-pointed or re-shaped in the same commit. Never deleted** |
| `src/backend/apps/ads/tests/test_submission.py` | `test_ad_edit_input_rejects_unknown_key`, `test_ad_edit_input_accepts_declared_fields_only`, the `SubmitAdInput` currency coercion cases, `test_submit_ad_rolls_back_when_auto_moderate_raises` | Phase 05 BLOCK 5 option (i) renames one of these — coordinate |

**Binding constraints**

1. **Four source-inspection tests are the detector, and they must be dealt with honestly.**
   `test_ad_edit_get_path_not_locked` asserts `source.count("select_for_update") == 1` **on
   `ad_edit`'s own source**; moving the locked fetch into `edit_ad` makes it red. The fix is
   to re-point the assertion at the function that now owns the lock **and keep its intent**
   (one lock, on the POST path, not the GET). Deleting the test removes the only shipped
   guard on the DB-003 locking structure. `test_submit_ad_fetches_inside_atomic` asserts
   `index("select_for_update") > index("transaction.atomic")` and a split that moves the
   fetch into a helper makes it raise **`ValueError`**, not fail — the worst kind of
   detector failure.
2. **`AdEditInput` with an omitted `title` must be **refused**, and the live ad's title must
   be byte-identical afterwards.** A POST with an empty `title` still saves — the
   clear-vs-blank ambiguity is a separate decision, and the DTO docstring already records it.
3. **A failed validation writes nothing.** No partial `update_fields` write, no image row, no
   `ModeratorActionLog`.
4. **`_apply_price_change` stays reachable for `TestApplyPriceChangeDelegation`.** Either
   keep it in `edit.py` or re-point that test in the same commit; do not break it silently.
5. **The three-way status branch and the field-driven price/photo sub-branch are preserved
   exactly.** The report's "four-way FSM" is three status branches plus one field-driven
   sub-branch (C-6).
6. **The GET path stays unlocked and stays prefetched** — that is what
   `test_ad_edit_get_path_not_locked` protects.
7. **No `print()`, no blanket `except`, no new abstraction** beyond `edit_ad` itself.
8. **The commit body must name:** that `AUTHZ-007` and `AUTHZ-002` are satisfied by
   construction, that the hoisted command passes `request.user.id` and not `ad.user_id`, the
   Q3 option, and which four source-inspection tests were re-pointed and why.

**Implementor task**

```yaml
id: task_10_b16_ad_edit_coordinated
title: "Extract ad_edit and split submit_ad in one coordinated change set (10-CQ-001, 10-CQ-008, 10-CQ-009)"
priority: critical
depends_on: [task_10_b02_packaging_hygiene]
source_reference: ".ai/plans/10-code-quality-remediation.md"
source_section: "BLOCK 16 - The coordinated change set"
source_blocks: ["BLOCK 16"]
description: >
  ad_edit is 193 lines and the largest function in the repository; submit_ad is 124 lines and
  mixes six responsibilities; AdEditInput defaults title and description to "" so a POST
  omitting title blanks a live ad. They must ship as ONE commit, one owner, three files, and
  only after phase 03 BLOCK 5, phase 05 BLOCKs 2 and 8, and phase 15's AUTHZ-007 and
  AUTHZ-002. Move ad_edit into apps/ads/services/edit_ad.py beside submission.py; assert
  ownership on the locked instance inside the transaction using the ad_archive pattern; build
  the hoisted SubmitAdInput with user_id=request.user.id and never ad.user_id; make
  AdEditInput.title/.description required with min_length=1 and return the Q3 response; split
  submit_ad with AUTHZ-002's guard landing in the same commit. Re-point - never delete - the
  four source-inspection tests, keeping their intent.
goals:
  - "put the web edit path behind a service boundary without changing a single rendered outcome"
  - "make an omitted title a refused request instead of silent data loss"
  - "satisfy AUTHZ-007 and AUTHZ-002 by construction rather than by a follow-up patch"
  - "keep the locking structure detectable by the four shipped source-inspection tests"
files:
  - path: "src/backend/apps/ads/views/edit.py"
    targets:
      - type: function
        name: ad_edit
      - type: function
        name: ad_archive
      - type: function
        name: ad_reactivate
      - type: function
        name: _apply_price_change
  - path: "src/backend/apps/ads/services/submission.py"
    targets:
      - type: class
        name: AdEditInput
      - type: function
        name: submit_ad
  - path: "src/backend/apps/ads/services/edit_ad.py"
    targets: [{type: function, name: edit_ad}]
  - path: "src/backend/apps/ads/tests/test_edit_views_locking.py"
    targets: [{type: class, name: TestEditViewsLocking}]
  - path: "src/backend/apps/ads/tests/test_edit.py"
    targets: [{type: class, name: TestEditAuthorization}]
changes:
  - action: add_code
    description: >
      edit_ad in apps/ads/services/edit_ad.py, holding the branch structure, the
      transaction.atomic() block, the locked fetch, the ownership assertion and the
      hand-written ORM write paths. It returns the existing HttpResponseForbidden /
      HttpResponse(status=400) directly - no ErrorPage enum.
  - action: modify_code
    description: >
      ad_edit becomes a thin adapter. The hoisted SubmitAdInput is built once with
      user_id=request.user.id. AdEditInput.title/.description become required with
      min_length=1, and the Q3 response is returned on a validation error. submit_ad is split
      with the user_id guard in the same commit. _apply_price_change stays reachable for
      TestApplyPriceChangeDelegation.
  - action: modify_code
    description: >
      Re-point the four source-inspection tests at the functions that now own the lock and
      the transaction, keeping their intent - one lock, on the POST path, fetch inside the
      transaction. Do not delete any of them.
acceptance_criteria:
  - "owner GET renders 200, owner POST saves, non-owner GET and POST both 403"
  - "the ownership assertion runs on the LOCKED instance inside the transaction"
  - "the hoisted SubmitAdInput passes user_id=request.user.id, asserted explicitly, and never ad.user_id"
  - "the reactivation branch and both error branches use the authorized locked instance and never re-fetch unlocked"
  - "a POST omitting title is refused and the live ad's title is byte-identical afterwards; a POST with an empty title still saves"
  - "a failed validation writes nothing - no partial update_fields write, no image row, no log row"
  - "all of test_edit.py's branch suites are green UNCHANGED, including TestApplyPriceChangeDelegation"
  - "all four TestEditViewsLocking tests are green and still assert the locking intent"
  - "the GET path still performs no lock and still prefetches"
  - "the commit body names AUTHZ-007 and AUTHZ-002 as satisfied by construction, the Q3 option, and each re-pointed test"
tests_to_run:
  - "src/backend/apps/ads/tests/test_edit.py"
  - "src/backend/apps/ads/tests/test_edit_views_locking.py"
  - "src/backend/apps/ads/tests/test_submission.py"
  - "src/backend/apps/ads/tests/test_image_service.py"
```

**Tests required**

1. **The data-loss regression, added first and asserted red before the fix** — a POST
   omitting `title` currently persists `""`; after the fix the ad's title is byte-identical
   and the response is the Q3 status. This is the only genuinely new test in the block and
   it is the reason `CQ-009` was filed.
2. **The authorization matrix** — owner/non-owner × GET/POST, with the non-owner POST
   asserted **403 and no write**. This is `AUTHZ-007`'s acceptance criterion and it is
   satisfied by construction; the test proves it.
3. **The actor identity** — the persisted moderation/submission record names
   `request.user.id` as the actor for a web edit, asserted explicitly. This is
   `AUTHZ-002`'s test gap and the only thing that catches a tautological guard.
4. **Every existing branch suite green unchanged** — reactivation (pass and fail),
   currency keep-current, price normalization, text update, the seven published-edit cases,
   archive, direct reactivate and the other-status direct save. These are the control: if
   one of them needs an edit, the extraction changed behaviour.
5. **The locking structure** — the four re-pointed source-inspection tests, plus a
   concurrency case that a concurrent delete during an edit does not resurrect a deleted ad
   (the suite already has that shape for archive, reactivate and delete).

**Risk and rollback**

- *Implementation risk:* **extracting the lock and forgetting to move the assertion with it.**
  Mitigation: the authorization matrix and the re-pointed structural tests, both in the same
  commit.
- *Implementation risk:* the tautological-actor bug — the one failure that is **invisible**,
  because the guard then always passes and both branches share one value. Mitigation: test 3
  and the explicit commit-body statement. This is the single highest-consequence defect this
  plan can introduce.
- *Rollout risk:* a malformed POST now returns 400 (or a re-render) instead of 500 or silent
  blanking. Both are improvements; the 400 is a visible change and must be stated.
- *Regression risk:* a `submit_ad` split that moves the `auto_moderate` delegation whose
  return value `ad_edit` branches on. Workable, but only in this commit.
- *Rollout/revert:* reverting this commit **must not** revert `AUTHZ-002`'s guard or
  `AUTHZ-007`'s assertion on their own. If the coordinator needs a partial revert, revert
  phase 15's items separately, not by checking this commit out.
- *Cross-phase:* if phase 03 BLOCK 5 or phase 05 BLOCKs 2/8 land **after** this commit, the
  ordering has been violated and the red gate is the evidence. Fix the order, do not relax
  the test.

---

## 4. Dependency graph

### 4.1 Execution order (the safe serial order)

One Implementor, strictly sequential. Every block is one commit (§1.3). The numbering *is*
the order, and the order is chosen so that one contended file is written by one block per run.

| # | Block | Findings | Class | Depends on (in-plan) | External gate | Risk |
|---|---|---|---|---|---|---|
| 1 | Consent-cookie constants | `CQ-013` | M | — | — | **LOW** |
| 2 | Packaging / export / docstrings | `CQ-017.1`, `.2`, `CQ-007`, `CQ-019` | M | — | — | **LOW** |
| 3 | Locale literals in place | `CQ-006` | M | — | — | LOW–MED |
| 4 | Saved-search Pydantic boundary | `CQ-004` | B | 3 | **Q12** | **MED** |
| 5 | Templates: `AdStatus` + admin URL | `CQ-005`, `CQ-018` (URL) | M | — | **Q10** | LOW–MED |
| 6 | `@require_POST` standardisation | `CQ-018` (7 guards) | M | — | — | **LOW** |
| 7 | Reject-reason boundary **+ `reject_ad`/`ban_user` 405** | `CQ-003`, `CQ-018` (`review.py`) | B | 5 (Q10's mechanism) | **Q2**, **Q4** | **MED** |
| 8 | Dead-code deletion | `CQ-016` | M | 1 | **Q5** | **LOW** |
| 9 | Typed service boundaries | `CQ-012` | B | 2, 8, 1 | **Q14** | **MED** |
| 10 | `/alerts` prompt | `CQ-014` | B | — | — | **LOW** |
| 11 | Bot alert data access → service | `CQ-002` | B | 10 | **phase 03 BLOCK 5** | **MED** |
| 12 | `admin_actions.py` → `services/` | `CQ-010` (move) | M | 7 | **phase 05 BLOCK 3, phase 06 BLOCK 16** | **MED** |
| 13 | `PLC0415` + exclusions | `CQ-010` (gate) | M | 12 | — | **LOW** / HIGH if wrong |
| 14 | `build_listings_context()` | `CQ-015` | B | — | **Q8**, phase 08 BLOCK 1 | **MED** |
| 15 | One fuzzy ladder, one cutoff | `CQ-011` | B | 14 | **Q1, Q6, Q7**, phase 08 | **MED** (HIGH under Q1(b)) |
| 16 | The coordinated change set | `CQ-001`, `CQ-008`, `CQ-009` | B | 2 | **phase 03 BLOCK 5, phase 05 BLOCKs 2/8, `AUTHZ-007`, `AUTHZ-002`, Q3** | **HIGH** |

`M` = mechanical · `B` = behavioural.

### 4.2 The DAG and why each edge exists

```
 (none) --> [1 consent cookies] --> [8 dead code] --> [9 typed boundaries] --Q14
                |                     |
                +---------------------+  (consent.py: 1 then 8; context_processors.py: 1 then 9)

 (none) --> [2 packaging] --------> [9 typed boundaries]      (cache.py: 2 then 9)
                |
                +--> [16 coordinated change set]  <-- Q3  (apps/ads/services/__init__.py must exist first)
                      ^  ^  ^
      phase 03 B5 ----/  |  \---- phase 05 B2/B8
                          |
                 AUTHZ-007 -> AUTHZ-002

 (none) --> [3 locales] --> [4 saved-search DTO]  <-- Q12
                |               (save_search.py)
                +--> (enums.py: this block only)

 (none) --> [5 templates] --> [7 reject reason + 405] --> [12 admin_actions move] --> [13 PLC0415]
              (Q10)             (Q2, Q4)                 (5-phase coordination)

 (none) --> [10 alerts prompt] --> [11 bot service]  <-- phase 03 BLOCK 5
 (none) --> [14 listings ctx] --> [15 fuzzy ladder]  <-- Q8 / Q1,Q6,Q7
```

**Each edge, with the reason it exists:**

| Edge | Why it exists |
|---|---|
| **1 → 8** (hard, file) | `is_consent_given` is deleted from `apps/users/views/consent.py` by BLOCK 8, and BLOCK 1 relocates the constants out of the same file. Running 8 first means the deletion is reviewed against the *old* layout; running 1 first means BLOCK 8's diff is a deletion in a file whose constants have already moved — smaller, and it cannot reintroduce them |
| **1 → 9** (hard, file) | `consent_state` / `consent_version` are BLOCK 1's import change and BLOCK 9's annotation change. Two edits to the same two functions in one run is a review that can see both |
| **2 → 9** (hard, file) | `cache.py`'s two bare-generic returns are in functions whose docstrings BLOCK 2 just trimmed. Same reasoning |
| **2 → 16** (hard, prerequisite) | `apps/ads/services/` is an **implicit namespace package** today. BLOCK 16 adds `edit_ad.py` to it. Adding a module to a package that has no `__init__.py` works on CPython 3 but leaves the repo's one inconsistency in the one package that now holds the most important service. BLOCK 2 removes it first |
| **3 → 4** (hard, file) | `save_search.py` carries a raw locale literal (BLOCK 3) and the `_int_or_none` closure (BLOCK 4). One file, one run, one review |
| **5 → 7** (hard, mechanism) | BLOCK 7 exposes `CategoryRejectReason` to `review.html` **through Q10's mechanism**. If BLOCK 7 landed first it would have to invent that mechanism, and BLOCK 5 would then have to adopt a mechanism chosen by a different block. Q10 is answered once and both blocks use it |
| **7 → 12** (hard, file) | Both touch `apps/moderation/views/review.py`. BLOCK 7 settles the two behavioural decisions in `reject_ad` and `ban_user`; BLOCK 12's only change to that file is the `admin_actions` import line. Running 12 first means the move's diff lands on a body that two more blocks are about to rewrite, and the review of a *trivial* import change would have to re-read code that is about to change |
| **12 → 13** (soft, ordering) | BLOCK 13 turns on `PLC0415`. BLOCK 12 is the block that removes the last of the three arbitrary deferrals the rule exists to catch (`review.py` → `admin_actions`). Enabling the rule before they are gone would put a legitimate exception into the exclusion list, and a rule with a carve-out for the thing it was added to catch is a rule that gets turned off. **Soft** because BLOCK 13 would still be *correct* with those three deferrals present — it is a sequencing preference, not a correctness dependency |
| **10 → 11** (hard, file) | BLOCK 10 edits `cmd_alerts`'s prompt; BLOCK 11 moves four functions out of the same handler. Structural last |
| **14 → 15** (hard, file) | `ads/views/listings.py::_suggest_category` is BLOCK 15's subject and BLOCK 14's context-builder call site. BLOCK 14's extraction reads that file; running 15 first means the extraction is written against a file another phase-10 block just restructured |
| **1, 2, 8 → 9** (hard, file) | `cache.py`, `context_processors.py` and `lookup_resolution.py` each have two phase-10 owners. This edge is the reason BLOCK 9 is where it is in the order rather than earlier |
| **all → 16** (external, hard) | `AUTHZ-007 → AUTHZ-002 → CQ-001 → CQ-008`, **plus** phase 03 BLOCK 5 and phase 05 BLOCKs 2/8. The report's §A ordering is necessary but **not sufficient** at this anchor (C-6) |

### 4.3 Where there is deliberately **no** edge, and why

| Pair with no edge | Why |
|---|---|
| **5 ↔ 6** | Different files, different mechanisms: one exposes values to templates and reverses five URLs; the other swaps seven inline guards for a decorator. Merging them would couple a template change to a 405 change in five unrelated modules, and would make the harder one (Q4 territory) wait on the easier one for no reason |
| **6 ↔ 7** | Both are `CQ-018`'s decorator work, and the split is the point. BLOCK 6 is behaviour-preserving and batchable; BLOCK 7 turns a 302 into a 405 and is gated. Merging them would put a decision-gated change inside an ungated commit, and would couple five unrelated modules to the moderation page |
| **7 ↔ 12** | Both write `review.py`, so there is an edge (above) — but the *reasons* are unrelated: one is about what a POST may contain, the other is about where a module lives. The only shared constraint is the one-Implementor rule, which is not a dependency |
| **11 ↔ 12** | Both are "the last structural change to a contested file" — but `telegram_bot/handlers/alerts.py` and `apps/moderation/admin_actions.py` are different files in different processes, and the two have no interaction. With one Implementor they run in series anyway |
| **13 ↔ 14** | A config change and a two-view extraction. The only relationship is that both are "large diff, low novelty", which is an argument for them **not** sharing a commit |
| **3 ↔ everything** | `core/enums.py` is the one file BLOCK 3 alone may edit. Making it a hub would turn a ten-site substitution into a serialisation bottleneck for the whole phase |
| **BLOCK 12 ↔ phase 05 / phase 06** | The move is **not** an in-plan edge; it is an **external** ordering against phase 05 BLOCK 3 and phase 06 BLOCK 16, which the coordinator sequences (§5.1, hot spot 3) |

### 4.4 The orders that are unsafe

1. **BLOCK 16 before phase 03 BLOCK 5, phase 05 BLOCK 2 or phase 05 BLOCK 8.** The
   extraction moves the `atomic()` block that all three edit. Applied independently, one
   silently reverts the other — this is the report's §A failure mode, and phase 03/05 were
   not on the page when it was written.
2. **BLOCK 16's three findings split across commits.** The hoisted `SubmitAdInput` freezes
   whatever `user_id` value it was given into **one** place; if that value is `ad.user_id`,
   `AUTHZ-002`'s guard becomes tautological on the web path and now *looks* load-bearing
   because both branches share it.
3. **BLOCK 5 after BLOCK 7.** BLOCK 7 deletes the eight hardcoded `<option>`s and BLOCK 5
   rewrites the status-literal blocks in the same template; the second edit would be written
   against markup the first no longer produces.
4. **BLOCK 13 before BLOCK 12.** The gate goes on with `review.py`'s three arbitrary
   deferrals still present, and the exclusion list acquires a carve-out for the exact
   pattern the rule was added to catch.
5. **BLOCK 9 before BLOCK 2 and BLOCK 8.** `cache.py` and `lookup_resolution.py` would each
   get two phase-10 owners in the same run.
6. **BLOCK 12's move racing phase 05 BLOCK 3 or phase 06 BLOCK 16.** Both hold
   `admin_actions.py` for a behavioural change; a move landing between them splits one
   function's diff across two unrelated commits.
7. **Any block enabling a feature flag or shipping a migration** — not applicable: this plan
   has no flag, no migration and no data movement. **Its one rollout gate is BLOCK 16's
   external ordering**, and that is a *code* gate, not a deployment one (§4.5).
8. **Any block restoring `.ai/audit/10-code-quality/findings.md`.** It is deleted; the
   validated report preserves the corrected evidence inline.

### 4.5 What the DAG does *not* decide

The DAG orders blocks. It does **not** resolve Q1 … Q14. Each is a gate inside a block,
recorded in that block's `extra_context` and in §0.5, and §8.1 checks that a **written**
answer exists for each. **A block whose gate is unanswered does not start, and the
Implementor is forbidden from choosing the option.**

The DAG also does not sequence phase 10 against the other phases. §5 does, from phase 10's
side only: it names the owning block in every other plan and the ordering rule. **Phase 10
does not contact, negotiate with, or wait on any other agent** — the coordinator sequences
the cross-phase gates.

---

## 5. Cross-phase coordination

Plans `.ai/plans/01-…` through `.ai/plans/09-external-api-remediation.md` exist; phases 10–15
are `planned` or are being planned in parallel right now by other Planner agents. (Phase 09's
plan appeared **during** this plan's writing — C-8 — and its two reservations against phase 10
are recorded below.) This section is the boundary contract and is deliberately
**one-directional**: phase 10 states what it owns, what it will not touch, and where its
boundaries lie. It does **not** attempt to contact the other agents.

### 5.1 The cross-phase collision map

Every hot spot, the exact owning block in the other plan, and the ordering rule.

#### Hot spot 1 — `src/backend/apps/ads/views/edit.py` ★ the most contended file for phase 10

| Owner | Block | What it owns there | Ordering rule |
|---|---|---|---|
| Phase 03 | **BLOCK 5** (Option B, `SET LOCAL lock_timeout`) | a statement inside `ad_edit`'s `atomic()` block | **Before BLOCK 16.** Hard |
| Phase 05 | **BLOCK 2** | the price/photo `elif` arm inside `ad_edit` | **Before BLOCK 16.** Hard |
| Phase 05 | **BLOCK 8** | the catch-all `else` arm inside `ad_edit` | **Before BLOCK 16.** Hard |
| Phase 05 | **BLOCK 12** | both `submit_ad` branches, "read-mostly" | **Before BLOCK 16.** Soft — read-only for phase 10 |
| Phase 07 | **BLOCK 10** | two docstrings in the same file | **Before BLOCK 16.** Soft — docstrings only |
| Phase 15 | `AUTHZ-007` | the ownership assertion on the locked instance inside `atomic()` | **Before BLOCK 16.** Hard — BLOCK 16 satisfies it by construction |
| Phase 15 | `AUTHZ-002` (**HIGH**) | `submit_ad`'s `user_id` guard | **Before BLOCK 16.** Hard — the guard lands in the same commit |
| **Phase 10** | **BLOCK 16** | the extraction, the hoisted command, `AdEditInput` | **Last.** One owner, one review, three files |

**The rule:** `phase 03 BLOCK 5 → phase 05 BLOCK 2 → phase 05 BLOCK 8 → AUTHZ-007 →
AUTHZ-002 → phase 10 BLOCK 16`. If the coordinator judges six owners too many for one
function, the only acceptable alternative is to **fold BLOCK 16 into one of them**. Running
them in parallel is never acceptable.

#### Hot spot 2 — `src/backend/apps/ads/services/submission.py` (8 claims)

Phase 03 **BLOCKS 3, 5, 6, 8**; phase 05 **BLOCKS 5, 12, 13**; phase 07 **BLOCKS 1, 3** —
phase 07 calls it *"the single most contested file across the whole plan set"* and phase 05
§5.3 lists **five** claims on it. `CQ-008`'s split and `CQ-009`'s DTO change both land in
phase 10's **BLOCK 16**, and nothing else in this plan touches the file.

**The rule:** BLOCK 16 is a single commit covering `edit.py` + `submission.py` +
`edit_ad.py`. Phase 10's `submit_ad` split is **not** an independent change that can be
deferred; and phase 05 BLOCK 5 option (i)'s rename of `test_submit_ad_rolls_back_when_auto_moderate_raises`
must be sequenced either side of it, never inside it.

#### Hot spot 3 — `src/backend/apps/moderation/admin_actions.py` (5 phases)

Phase 03 (lock behaviour), phase 04 (**BLOCK 9**, comments only), phase 05 (**BLOCK 3** —
`bulk_approve`'s filter and `approve_ad`'s guard), phase 06 (**BLOCK 16** — reason
redaction), phase 07 (**BLOCK 11**, conditional). Phase 05's `TestBulkLockingStructure`
source-inspection guard and phase 04's `test_bulk_ban_users_not_locked` both constrain the
module's shape.

**Phase 10's claim is the `admin_actions.py` → `apps/moderation/services/admin_actions.py`
move, in **BLOCK 12**, one commit, three importers:**

| Importer | Import form | Phase 10's change |
|---|---|---|
| `src/backend/apps/ads/admin.py` | **module-level** | One import line. Note: this is the **layering inversion** the report flags as advisory — an `ads` admin depending on moderation internals. **Phase 10 does not redesign it**; it moves the target and records the inversion |
| `src/backend/apps/moderation/views/api_bulk.py` | **module-level** | One import line. Do **not** restructure the module (phase 05's `TestBulkLockingStructure` inspects it) |
| `src/backend/apps/moderation/views/review.py` | **three function-local** imports | One import line each, promoted to module scope — the move deletes all three deferrals as a side effect |

**The rule:** the move is **one commit**, after phase 05 BLOCK 3 and phase 06 BLOCK 16 have
landed, or before either starts. It must never race them. The coordinator is told first,
because it is the highest-value-per-diff and highest-coordination item in the phase.

#### Hot spot 4 — `src/backend/apps/core/enums.py` (5 phases)

Phase 02 added `REPAIR_BOT_USERNAME = 13`; phases 03 §5.3, 05 §5.1, 06 §5.3 and 07 §5.3 all
list `enums.py` + `advisory_lock.py`'s allocation docstring + `test_advisory_lock_ids.py` as
a **three-files-one-commit** unit for whoever allocates an id.

**Phase 10 allocates no id and does not reorder the enum** (C-7, §6). Its only edit is
**BLOCK 3's** `LanguageLocale.fts_config` / `.fts_vector_field` / module docstring, under
Q9. **The rule:** re-read `enums.py` immediately before BLOCK 3; if it has uncommitted
changes from another agent, **stop and report**; never stage by directory; and under Q9
option (a) or (b) the `SavedSearch.language` default must be checked with
`makemigrations --check` (BLOCK 3, binding constraint 3).

#### Hot spot 5 — `telegram_bot/handlers/alerts.py`

Phase 03 **BLOCK 5** names it explicitly for `SET LOCAL lock_timeout`; phase 09's API-009 /
API-010 are cross-references only (and **unverifiable**, C-8); `test_unsubscribe.py`
source-inspects `_resolve_owned`.

**The rule:** phase 03 BLOCK 5 lands **before** phase 10 **BLOCK 11**, or BLOCK 11 is folded
into it. Phase 10's **BLOCK 10** (the prompt) may run before phase 03 BLOCK 5 — it touches
`cmd_alerts`, not the transaction — but BLOCK 11 may not.

#### Hot spot 6 — the search / listings seam, vs phase 08

Phase 08 owns `apps/search/models.py` + the next `search/migrations/0003`,
`apps/ads/services/listings_query.py` (**BLOCK 1**), `apps/search/services/*` (**BLOCK 6**
cache writers, which includes `category_fuzzy.py`'s neighbourhood) and `alert_query.py`
(none for phase 08).

**The rule:** **Q8** must be answered with phase 08 in view. Under Q8(b) — `build_listings_context`
as a function in `listings_query.py` — phase 10's **BLOCK 14** lands **after** phase 08
**BLOCK 1**. Under Q8(a) — a new module — BLOCK 14 is free of that dependency. **Q1** must
likewise be answered with phase 08 BLOCK 6 in view, because option (b) puts the shared
ladder next to `category_fuzzy.py`.

#### Hot spot 7 — `src/backend/apps/moderation/views/review.py` (three phase-10 owners)

| Phase-10 block | What it does to this file |
|---|---|
| **BLOCK 5** | `reverse()` the five `/admin/` redirect targets |
| **BLOCK 7** | validate `reason_category` at the boundary, and apply the Q4 decorator decision to `reject_ad` and `ban_user` |
| **BLOCK 12** | the `admin_actions` import line, promoted to module scope — nothing else |

**The rule:** that is the order, in one run, one block at a time, re-reading the file before
each. The move's import-line change is last so that the other two diffs are settled against
a stable body.

### 5.2 What phase 10 must **not** do, for other phases' sake

| Other phase | What phase 10 must not do | Boundary |
|---|---|---|
| **Phase 01** | Must not create `telegram_bot/services/login.py`; must not touch `handle_login_orm`'s closure shape; must not sweep in-source `ENT-` markers | `ENT-005` **shipped** `_claim_login_token`'s delegation and documented two deferrals in `handlers/login.py` as load-bearing. Re-filing would ship the same code twice |
| **Phase 02** | Must not edit `config/settings/**`, `.env*`, or `secret_validation.py`; must not allocate a lock id | Phase 02's uncommitted `enums.py` work is read-only for BLOCK 3 |
| **Phase 03** | Must not add a `statement_timeout` / `lock_timeout`, must not take a `AdvisoryLockId`, must not start the **BLOCK 11 in-source marker sweep** | BLOCK 11's rule is explicit: *"Phases 04–15 must not start BLOCK 11-style legacy sweeps of their own."* Phase 10's `CQ-019` and `CQ-016` are therefore both narrowed to named files |
| **Phase 04** | Must not ship a second `_get_client_ip`; must not restructure `handlers/contact.py` beyond the import hoist | BLOCK 11 touches `contact.py` for one import. Phase 04 BLOCK 9 is comments only and is compatible |
| **Phase 05** | Must not touch `Ad.transition_to`, `ALLOWED_TRANSITIONS`, the `search_vector*` columns, the `ads_search_vector_update` trigger or `setup_search_triggers`; must not add a `lock_timeout` statement to a view | Phase 05 §5.2 states this for phase 10. BLOCK 16 is **read-only** on the transition matrix; the four `AdImage` paths in `submit_ad` are the subject of phase 07 BLOCK 1 |
| **Phase 06** | Must not edit `apps/search/services/alert_query.py`, must not change `SavedSearch` retention or erasure semantics, must not add a `User`-side consent predicate, must not touch `users/services/deletion.py` | `SavedSearch` is a phase 06 PII surface. BLOCK 4 adds a DTO at the **request edge**; it does not change what is stored or for how long. Phase 06 **BLOCK 16** must land before the `admin_actions.py` move (hot spot 3) |
| **Phase 07** | Must not touch the media pipeline, `MEDIA_ROOT` staging, thumbnail generation or `sweep_orphaned_media`; must not edit `telegram_bot/services/ad_data/media.py` | BLOCK 16 moves the file/medium orchestration inside `submit_ad`; the thumbnail write path stays byte-identical. **This is the sharpest edge in BLOCK 16** — the file-IO half of `submit_ad` is phase 07 BLOCK 1's subject |
| **Phase 08** | Must not edit `ListingsQueryParams`, `ListingsQuery.build_queryset`, `search_vector*`, `search/migrations/`, or the FTS trigger; must not enable a search feature flag | BLOCK 3 touches `search/models.py`'s `language` **default** only, with `makemigrations --check` as the gate. BLOCK 14 reads the DTO. Q1/Q8 are answered **with** phase 08 |
| **Phase 09** | Must not add a contact rate limiter, must not change `classify_contact_deep_link` or `ContactDeepLinkKind`, must not touch `api_bulk.py`, must not build a cache-failure policy, and must not use `parse_mode="HTML"` with unescaped seller text | Phase 09's plan appeared during this plan's writing (C-8) and is anchored at the same commit. It edits `telegram_bot/handlers/contact.py` (BLOCK 11's import hoist — **different region, sequential, re-read**) and names `apps/core/utils/cache.py` the shared home for a cache-failure contract (`09-VAL-008` — BLOCK 2's docstrings and BLOCK 9's two return types, **compatible but a three-way reservation** with phase 08 BLOCK 6). `classify_contact_deep_link` and `ContactDeepLinkKind` are pinned by `test_account_state_middleware.py` and are **phase 09's alone** |
| **Phase 11** | Must not expand a required test rewrite into new coverage | BLOCK 9's ~30 `test_priority.py` assertions and BLOCK 15's equivalence table are **incidental rewrites required by a decided change**. Growing them raises the regression risk of the block |
| **Phase 12** | Must not write runbooks or change deployment configuration | Nothing in this plan changes an operator-visible surface except BLOCK 4's new error response |
| **Phase 13** | Must not make latency or index claims, and must not `EXPLAIN` anything | BLOCK 14's `test_search_query_count.py` / `test_search_slo.py` guards are tripwires, not measurements to grade |
| **Phase 14** | Must not regenerate locale files | Only BLOCKS 10 and 16 may add a string, both **appended** in the same commit, `ru` and `bs` non-empty |
| **Phase 15** | Must not build a per-request authorization gate, must not add a `User` or `Ad` default-manager filter, must not revive `can_publish_ad` as dead code | `AUTHZ-005`'s validator *rejected* the dead-code label. Phase 10's BLOCK 8 excludes it explicitly |
| **Any phase — the audit input** | Must not edit `.ai/audit/**` or another phase's plan or handbook | 19 tracked `.ai/audit/**` deletions exist in the tree. `git status --short .ai` must show **no new modifications** beyond them and this plan's own file |

### 5.3 Shared-artefact reservations

| Artefact | Phase 10 claim | Conflict and rule |
|---|---|---|
| `src/backend/apps/ads/views/edit.py` | **BLOCK 16 only** | **Six-way.** Phase 03 BLOCK 5, phase 05 BLOCKs 2/8/12, phase 07 BLOCK 10, phase 15 AUTHZ-002/007. Ordering in hot spot 1 |
| `src/backend/apps/ads/services/submission.py` | **BLOCK 16 only** | **Eight-way.** Phase 03 BLOCKS 3/5/6/8, phase 05 BLOCKS 5/12/13, phase 07 BLOCKS 1/3 |
| `src/backend/apps/ads/services/__init__.py` | **BLOCK 2** (creates it) | Phase 05 BLOCKs 2/10/12 and phase 07 add modules to the same package. **An empty `__init__.py` re-exporting nothing** cannot conflict |
| `src/backend/apps/moderation/admin_actions.py` | **BLOCK 12** (moves it) | **Five-way.** Phase 03, phase 04 BLOCK 9, phase 05 BLOCK 3, phase 06 BLOCK 16, phase 07 BLOCK 11. One commit, three importers, coordinator told |
| `src/backend/apps/moderation/views/review.py` | **BLOCKS 5, 7, 12** | Phase 03 BLOCK 5; phase 15 audits the moderation surfaces. **Three phase-10 edits in one run, in that order** (hot spot 7) |
| `src/backend/apps/core/enums.py` | **BLOCK 3 only** | **Five-way** plus phase 02's uncommitted `REPAIR_BOT_USERNAME = 13`. Re-read before editing. No lock id is allocated; `AdvisoryLockId` is not reordered |
| `src/backend/apps/ads/services/listings_query.py` | **BLOCK 14** (read, unless Q8(b)) | Phase 08 **BLOCK 1** holds it. Under Q8(b), BLOCK 14 lands after phase 08 BLOCK 1 |
| `src/backend/apps/search/services/category_fuzzy.py` | **BLOCK 15** (read-only) | Phase 08 **BLOCK 6** is in its neighbourhood as one of the cache writers. **Phase 10 must not change a cache key or TTL here** |
| `src/backend/apps/ads/views/listings.py` | **BLOCKS 14, 15** | Phase 05 §5.2 and phase 15 read it. Two phase-10 blocks, in that order |
| `src/backend/apps/search/views/search.py` | **BLOCKS 14, 15** | Phase 08 owns the search module's semantics. BLOCK 14 extracts a context builder; BLOCK 15 unifies the fuzzy ladder. Neither touches the FTS filter or the query builder |
| `src/telegram_bot/handlers/alerts.py` | **BLOCKS 10, 11** | Phase 03 **BLOCK 5** is a **gate** for BLOCK 11. Phase 09's `API-009` / `API-010` touch the alert *rate-limit* path, not `_resolve_owned`; re-check against the now-readable plan (C-8) |
| `telegram_bot/handlers/{contact,support}.py` | **BLOCK 11** (import hoist only) | **Phase 09** edits `contact.py` (rate limiter, a different region) and phase 04 BLOCK 9 touches it for comments. Two import lines each; no restructure; re-read before editing. `support.py` has no other claim |
| `src/backend/apps/core/utils/cache.py` | **BLOCKS 2 and 9** | **Three-way.** Phase 08 BLOCK 6 owns the cache-key contract; phase 09 `09-VAL-008` names this module the shared home for a cache-failure policy. Phase 10 ships **docstrings (BLOCK 2) and two return types (BLOCK 9)** — no key, no TTL, no contract. 2 then 9, one run |
| `src/backend/apps/moderation/services/priority_{calculator,}.py` | **BLOCK 9** | Phase 05 reads them (queue surfaces); phase 12. Type change only, no scoring change |
| `src/backend/apps/categories/services/lookup_resolution.py` | **BLOCKS 8, 9** | Phase 08 BLOCK 6 is one of the cache writers. 8 then 9, one run |
| `pyproject.toml` `[tool.ruff.lint]` | **BLOCK 13** | **No phase holds this block.** Phase 02/03/06/07 hold `base.py` and `.env.*`, not the ruff config. This is phase 10's quietest reservation |
| `src/backend/locale/*/LC_MESSAGES/django.po` | **BLOCKS 10, 16 only** | Shared with phases 03/05/06/07/11/14. **Append; never regenerate** |
| `src/backend/conftest.py` | **Nobody in this plan** | The most contended file in the repository. If a block appears to need a fixture, the test is over-fitted |
| `.ai/audit/**` | **Nobody.** Unmodifiable by mandate | 19 tracked deletions exist. `git status --short .ai` must show no new modifications beyond them and this plan's own file |
| `docs/**` | **Nobody in this plan** | Every documentation item this plan touches is a module docstring or a template comment. No `docs/` file is a phase-10 target, which also keeps phase 06's `technical-specification.md` and `db-schema.md` reservations intact |

### 5.4 What phase 10 needs from other phases (forward dependencies)

1. **Phase 03 BLOCK 5** and **phase 05 BLOCKs 2 and 8** landed, or phase 10 BLOCK 16 folded
   into one of them. Without this, BLOCK 16 does not start.
2. **Phase 15 `AUTHZ-007` and `AUTHZ-002`** decided and, ideally, landed. BLOCK 16
   satisfies both by construction; if either has already changed the code, BLOCK 16's
   re-read is mandatory and its commit body must say which shape it found.
3. **Phase 05 BLOCK 3** and **phase 06 BLOCK 16** settled before the `admin_actions.py` move.
4. **Phase 08 BLOCK 1 and BLOCK 6** consulted for **Q8** and **Q1**.
5. **The coordinator's answer to Q5** (external importers of the `RESOLVED_*_PREFIX`
   aliases) — one question, cheap, and BLOCK 8's only external dependency.
6. **The coordinator's ruling on Q11** (`QLT-###` vs `10-CQ-0NN`) — phase 10 writes no
   marker either way and sweeps none.

---

## 6. Out of scope for this plan

Every de-scoping below is **routed**, not dropped. A de-scoped item with no destination is a
re-filed finding.

### 6.1 De-scoped by design (deliberately not done here, with the rationale)

| Item | Why |
|---|---|
| **`CQ-014`'s numeric `/alerts` toggle** | **FEATURE REQUEST — DECLINED for this programme by the Product Owner on 2026-10-03. Named owner: the bot's seller-facing-flows owner (the same owner BLOCK 10's original text identified).** A **new user-facing feature**, not a code-quality remediation: an FSM for the list, a new router entry point, `str.isdigit()` input parsing, error paths, and **three new i18n strings** with non-empty `ru` and `bs` in a catalogue shared with six other phases. The *defect* is a shipped prompt promising an interaction the code does not implement; the proportionate fix is the prompt (BLOCK 10) plus the dead-state deletion (BLOCK 8), and **the owner has ruled that is the whole deliverable**. **Explicitly out of scope under the ruling: the FSM, the router entry point, numeric parsing, and all three new strings.** If the feature is later picked up, BLOCK 11 must already have run — the handlers would land in the same file its extraction moves |
| **`CQ-004`'s `PreferredCityInput`** | `set_preferred_city` already validates with an explicit existence query, already returns 400 with a documented reason, already has `@require_POST`, and already owns its cookie constants. Wrapping it in a Pydantic model adds a layer with **no defect behind it** — a direct violation of project rules 5 and 7 |
| **`CQ-007`'s `CacheEntry` class and the five proposed cache modules** | 12 one-line wrappers over `django.core.cache`, whose keys and TTLs are **already** single-sourced as `Final` default arguments. The report's "a key change means 12 edits" impact is false. A class over one-line wrappers is pure indirection |
| **`CQ-006`'s `apps/core/services/locales.py`** | `LanguageLocale` already exposes `.values()`, `.from_code()`, `.fts_config` and `.fts_vector_field`. A wrapper module is a hop with no consumer. The fix is in-place substitution, and the two raw dicts move **onto the enum itself** (BLOCK 3) |
| **`CQ-010`'s `scripts/lint_no_deferred_imports.py`** | `ruff`'s built-in `PLC0415` does this and `ruff` is already a dependency. A custom script is a second implementation of a check the project already has. The **exclusion list** ships instead (BLOCK 13) |
| **The two AST architecture tests** (`CQ-002`, `CQ-004`) | A rule that must first be made true cannot be enforced before it is true. Both would fail on ~26 legitimate `AppConfig.ready()` / bootstrap deferrals, and the AST test for POST views would fail on the `request.POST` + `save()` delegate pattern in `moderation/views/review.py`. Phase 11 owns test-quality findings |
| **`CQ-001`'s `ErrorPage` enum and `_build_submit_input` helper** | `HttpResponseForbidden` and `HttpResponse(status=400)` are self-describing. Hoisting the duplicated block into one local `command` variable costs two lines and creates no new name. Both already rejected by the validator; rejected again here |
| **`CQ-018`'s `require_http_methods` adoption** | Used **zero** times in the codebase. Standardise on the existing `@require_POST`; do not add a second idiom. Adding it would create the inconsistency the finding is about |
| **`CQ-017.3` — the `AdvisoryLockId` member reorder** | An `IntEnum`; member order has **no** functional, serialisation or query effect. The finding is **stale by one member** (`REPAIR_BOT_USERNAME = 13` arrived from concurrent phase-02 work, C-7), the file is contended by **five** phases, and the re-read-before-edit rule would apply to a change worth nothing. **Phase 10 allocates no lock id and reorders nothing** |
| **`CQ-019` as a standalone finding** | 1,526 comment-only lines of 28,574 (5.3 %) is not a defect, and the comments are predominantly non-obvious design rationale. A tree-wide comment census is a **legacy sweep**, which **phase 03 BLOCK 11 reserves to itself** and forbids other phases from starting. Folded into `CQ-007` as a `cache.py` docstring trim |
| **`CQ-012`'s `PriorityFlags(StrEnum)`** | The vocabulary is two strings (`"banned_word"`, `"repeat_offender"`). An enum for two values is defensible under project rule 10 but is **not load-bearing**, and the finding's rule-backed part is the typed DTO, not the flag vocabulary. It may be added **only** if the Planner records that decision in BLOCK 9's commit body |
| **`CQ-002`'s `telegram_bot/services/login.py`** | **Already shipped** by phase 01 `ENT-005`, at the location the report's own target correction named. Creating it would re-split a cross-process protocol and ship the same code twice. **Never create it** (C-3) |
| **A column, a lookup table, or a migration for `ModeratorActionLog.reason`** | The enum's docstring records that the category is *deliberately* not a DB column. Phase 10 honours that decision and enforces the **vocabulary at the boundary** (BLOCK 7) instead |
| **A generic "enum in template" mechanism** | BLOCK 7 exposes one enum to one template through the mechanism Q10 chooses — the existing `core/context_processors.py::price_step` pattern. A framework serving it is a new abstraction with one consumer |
| **Redesigning the `ads → moderation` layering inversion** in `apps/ads/admin.py` | Real, recorded as advisory by the report, and **not** this phase's to fix: the move in BLOCK 12 relocates the target and the commit body records the inversion. The redesign is a phase-09-shaped question |
| **The `QLT-###` ↔ `10-CQ-0NN` reconciliation** in `apps/ads/views/edit.py`, `apps/media/schemas.py` and `telegram_bot/handlers/ad_create/submit.py` | **Q11 → the coordinator.** Two vocabularies for one report is a documentation defect, but the in-source ID sweep is **phase 03 BLOCK 11's**, and phase 03's rule forbids other phases from starting it. Phase 10 writes **no** new marker and sweeps **none** |
| **`can_publish_ad` as dead code** | **Phase 15's `AUTHZ-005`**, whose validator *rejected* the dead-code label (the behaviour is specified in `technical-specification.md:101`, making it a missing integration) and which is test-referenced 13× in `test_account_state.py`. Phase 10 must not revive it under any name (BLOCK 8, binding constraint 1) |

### 6.2 Rostered elsewhere, not dropped

| Item | Owner | Note |
|---|---|---|
| `AUTHZ-002`, `AUTHZ-007` | Phase 15 | BLOCK 16 satisfies both **by construction**; it does not re-file either |
| `ENT-004` | Phase 01 | **Satisfied** — `ci.yml` runs `ruff check src/` and `basedpyright src/`, so the bot is inside both gates. Not a blocker for BLOCK 11 |
| `ENT-005` | Phase 01 | **Shipped.** See §6.1 |
| `DB-001` | Phase 03 | `telegram_bot/services/ad_data/orm.py` is the precedent module for BLOCK 11, not its subject |
| `API-009` / `API-010` | Phase 09 (**plan appeared during this plan's writing**, C-8) | Phase 09's rate-limiter block edits `handlers/contact.py`; phase 10's BLOCK 11 touches a different region of the same file. Sequential, re-read, no overlap |
| `09-VAL-008` (the cache module as a policy home) | Phase 09 | Phase 10's BLOCKS 2 and 9 touch `apps/core/utils/cache.py` for docstrings and two return types. **No key, no TTL, no contract** — the finding that names the cache contract is phase 08 BLOCK 6's |
| `04-AUT-003` | Phase 04 | Unrelated to this phase's cookie and locale work; no overlap |

### 6.3 Explicitly forbidden while implementing

1. Creating `telegram_bot/services/login.py`, `telegram_bot/services/contact.py` or
   `telegram_bot/services/support.py` (C-3, BLOCK 11).
2. Creating `apps/categories/services/fuzzy.py` **unless Q1(a) is the recorded option**, and
   in that case with the name list **injected** so `categories` never imports `search` (BLOCK 15).
3. Adding an `AdvisoryLockId` member, renumbering an existing one, or reordering the enum (C-7).
4. Writing a migration, editing an applied migration, or adding a `CheckConstraint` /
   `MinValueValidator` to `SavedSearch` (BLOCK 4).
5. Adding a `# noqa: PLC0415`, or a `per-file-ignores` entry that is not justified by a
   pattern (BLOCK 13).
6. `ruff check --fix` over anything other than the files the current block edits; `ruff
   format` (not the project convention); any import reordering in a file the block did not
   touch.
7. Enabling `IMMEDIATE_ALERTS_ENABLED`, pinning `CACHES["default"]["TIMEOUT"]`, or touching
   `config/settings/**` or `.env*` (phase 02 / 06 / 08 territory).
8. Touching `ads_search_vector_fn`, `ads_search_vector_update`, `on_category_name_update`,
   `setup_search_triggers`, or any `search_vector*` column.
9. Adding a `User` or `Ad` default-manager filter, adding a contact rate limiter, touching
   `classify_contact_deep_link` / `ContactDeepLinkKind`, or sending unescaped seller text
   with `parse_mode="HTML"` — the last three are phase 09's (C-8).
10. Editing `.ai/audit/**`, another phase's plan file, another phase's audit handbook, or
    `src/backend/conftest.py`.
11. Restoring `.ai/audit/10-code-quality/findings.md`.
12. `git reset` / `git checkout` / `git restore` / `git stash` / `--amend` / force-push, or
    reverting a file another agent changed.
13. Committing without an explicit instruction; committing more than one block in one commit;
    `git add -A` or `git add .`.
14. Writing a test that asserts a line number, an introspected column count, a literal private
    name, a template-string substring, or the mere presence of a symbol (§1.5).
15. Deleting a source-inspection test to make a block green.
16. Running a test on the host (`uv run pytest` always fails — §1.1).
17. Deleting a `RESOLVED_*_PREFIX` alias without the Q5 answer recorded.

---

## 7. Per-block risk register

Severity here is **this Planner's assessment of execution risk for the change**, not the
finding's severity. "Contention" covers shared files. "Behaviour" covers observable response
changes. "Corpus" covers global or cross-cutting edits.

| Block | Risk | Kind | Likelihood | Impact | Mitigation / detection | Residual |
|---|---|---|---|---|---|---|
| **All** | An implementor works from the **report's** file list and builds a `telegram_bot/services/login.py`, an `apps/categories/services/fuzzy.py`, or an `AdvisoryLockId` reorder | Process | Med | **High** | C-3, C-7, §6.1 and §6.3 are in §0.2, §1.4 and every affected block's binding constraints | Very low |
| **All** | A block runs with its gate unanswered, or the Implementor silently picks an option | Process | Med | **High** | Every gate is a labelled block in §3 and a row in §0.5, repeated in the task YAML's `extra_context`; §8.1 checks a written answer exists for each | Low |
| **All** | A block's tests are **asserted** rather than **run**, or run on the host where there is no database | Process | Med | **High** | Every block names its exact Docker gate command; tests run **only** through the `test` service (§1.1) | Low |
| **All** | A red gate is captured while another phase agent runs and a teardown race is reported as a product defect | Process | **High** | Med | Concurrent runs collide on one `test_mko_bazuna`. Re-run serially before reporting. The symptom is `test_mko_bazuna does not exist` / `relation "..." does not exist` | Low |
| **All** | A blanket `ruff check --fix src/` reorders imports another phase's uncommitted work depends on | Process | Med | Med | `[tool.ruff] fix = false` is set deliberately; §1.2 and §6.3 scope `--fix` to the block's own files | Low |
| **All** | A source-inspection test is **deleted** to make a move green, removing the only guard on a locking structure | Correctness | Med | **High** | §1.5, §6.3 item 15, and every moving block names the test it must re-point, in the same commit | Low |
| **All** | A shipped green test that **encodes a defect** is "fixed" by changing production code | Correctness | Med | **High** | Project rule 2, restated per block. Two test rewrites are pre-authorised (BLOCK 9 under Q14(b), BLOCK 15 under Q6) and each must state the reason in its commit body | Low |
| **All** | A new user-visible string ships without non-empty `ru` **and** `bs` | i18n | Low | Med | Only BLOCK 10 and BLOCK 16 add a string, and only under their gates' string-bearing options. Append-only; the catalogue is shared with six phases | Very low |
| **1** | Q13 is answered implicitly and a new `apps/core/cookies.py` appears "because it is cleaner" | Design | Med | Med | The gate; the commit body names the option. Option (b) is one new module for six constants — rule 5 is the tie-breaker | Very low |
| **1** | A cookie constant is renamed "while we are here" | Regression | Low | **High** | Binding constraint 1; ~40 assertions across 5 files pin names and values | Very low |
| **2** | "Cleanup" expands into a cache-service refactor or a `CacheEntry` class | Design | Med | Med | Binding constraints 1 and 2; `CacheEntry` is §6.1 | Very low |
| **2** | The new `apps/ads/services/__init__.py` re-exports something and creates an import cycle | Correctness | Low | Med | Keep it empty — an explicit instruction, and it is why BLOCK 2 must precede BLOCK 16 | Very low |
| **2** | A docstring change is "improved" into a behaviour change | Behaviour | Low | Med | Binding constraints; the module's key/TTL/body contract is unchanged and the ads/core/bot suites are the tripwire | Very low |
| **3** | The FTS config↔column pairings drift and every search silently changes language | Correctness | Low | **High** | `test_search_triggers.py` and `test_setup_search_triggers.py` are in `tests_to_run` and must be green **unchanged** | Very low |
| **3** | An aggressive rewrite turns `.get("ru")` into indexing and raises on a missing translation key | Regression | Med | Med | The bot translation suites are the tripwire; binding constraint 2 and test 2 | Low |
| **3** | `SavedSearch.language`'s default changes and a migration appears | Migration | Low | Med | Binding constraint 3; `makemigrations --check` after the change. **This plan ships no migration** | Very low |
| **3** | `core/enums.py` is edited on a stale read and phase 02's uncommitted `REPAIR_BOT_USERNAME = 13` is clobbered | Contention | **High** | Med | Re-read immediately before editing; stop and report on a concurrent change; never stage by directory | Med — accepted |
| **4** | Q12's response shape is chosen by the implementor and a bare 400 lands on a modal-driven UI | Product | Med | Med | The gate, with the consequence of the cheapest option stated in its own row | Low |
| **4** | A DTO rejects something the hand-rolled parser accepted (a blank price, a decimal string) | Regression | Med | Med | `test_saved_search_create.py` is the positive control and must be green **unchanged**; the new tests cover the refused and the cabinet paths | Low |
| **4** | A `PreferredCityInput` or a `CheckConstraint` is added "while we are here" | Scope | Med | Low | Binding constraints 3 and 4; §6.1 | Very low |
| **4** | The fix is justified by the report's refuted 500 reproduction | Process | Med | Med | C-12 is in §0.2 and in the block's description; the commit body must describe the **silent persistence**, not a crash | Low |
| **5** | The five-term empty-state condition in `ads/dashboard.html` is broken and the dashboard silently empties | Behaviour | Med | **High** | Test 3 is the negative control; `test_dashboard_stats.py` and `test_auth_nav.py` must be green unchanged | Low |
| **5** | A template tag or filter library is added | Design | Med | Med | §1.4 and §6.3; the `price_step` pattern is the mechanism | Very low |
| **5** | `reverse()` produces a different admin URL than the literal (e.g. a missing `next`) | Behaviour | Low | Med | Test 2 asserts the redirect lands on the same two admin pages; the moderation link must still filter to `on_moderation` | Low |
| **5 / 7** | `review.html` is rewritten by BLOCK 5 and then by BLOCK 7 against stale markup | Contention | Med | Med | The 5 → 7 edge exists for this reason; re-read before each | Low |
| **6** | A guard that is a **dispatch** rather than a check is converted to `@require_POST`, changing a GET's meaning | Behaviour | Med | Med | Binding constraint 3; the Implementor names the enclosing function of each swap; `ad_edit` is explicitly BLOCK 16's | Low |
| **7** | Q4 is answered implicitly and a 405 ships without anyone deciding it | Process | Med | **High** | The gate; the commit body must name the option and state that the two test assertions changed because the behaviour was **decided** | Low |
| **7** | The `"<category>: <text>"` format is rewritten into two columns | Migration | Low | **High** | Binding constraint 1 and 4; test 2. A migration in this block is an automatic rejection | Very low |
| **7** | The `review.py` body changes and `TestModerationReviewLocking` fails, and the fix is to drop the assertion | Correctness | Med | **High** | Binding constraint 6; a decorator swap is safe, a fetch-moving restructure is not, and the test is never deleted | Low |
| **8** | An external consumer imports a `RESOLVED_*_PREFIX` alias | Compatibility | Low | Med | **Q5** is the gate; the commit body records the answer or the retention | Low |
| **8** | A deleted symbol is referenced by a string (a template include, an `INSTALLED_APPS` entry, a msgid) | Correctness | Low | Med | Whole-repo grep across `src`, `docs`, `templates` **and** `.ai` before deleting | Very low |
| **8** | `can_publish_ad` is deleted as "dead code" | Correctness | Med | **High** | Binding constraint 1; it is phase 15's `AUTHZ-005`, test-referenced 13× | Very low |
| **9** | Q14(b) is taken and ~30 assertions are mechanically string-replaced so they cannot fail | Correctness | Med | **High** | Test 3 explicitly requires the rewritten test to still fail when a key is dropped; the commit body must invoke project rule 2 and its justification | Low |
| **9** | A DTO looks equivalent but drops a key on `model_dump()` and `update_or_create` writes `None` | Correctness | Med | **High** | Test 1 asserts through the **persisted row**, not the intermediate object | Low |
| **9** | The change is presented as a typecheck-compliance fix | Review | Med | Med | C-4: basedpyright is in `standard` mode, `[tool.mypy]` is not read by it and is not in CI. The commit body must say this is a readability change | Low |
| **9** | A `# type: ignore` is removed and hides a real typing problem from basedpyright | Correctness | Med | Med | A basedpyright run **is** required — it may flag what mypy's ignore was hiding | Low |
| **10** | Scope creep into a half-implemented numeric toggle | Scope | Med | Med | Binding constraints 1 and 2; the withdrawal of the promise is the whole fix. **The feature was DECLINED on 2026-10-03**, so a half-built toggle is a scope violation against a decision, not a judgement call | Very low |
| **10** | The prompt is fixed but the toggle still does nothing, and the feature request is lost | Product | **High** | Low | **This risk SURVIVES the ruling and is accepted by decision** — the Product Owner declined the feature for this programme. It is now tracked as a **feature request with a named owner** (§0.7, §6), so it is a scheduled backlog item rather than an undocumented gap. The commit body should point at that request | Med — accepted, by decision |
| **10** | The locale file is regenerated instead of appended, discarding another phase's strings | i18n | Low | **High** | §1.2; append-only, `ru` and `bs` non-empty, `test_i18n_completeness.py` in `tests_to_run` | Very low |
| **11** | A move splits `transaction.atomic()` from `select_for_update()` | Correctness | Med | **High** | Binding constraint 3; `TestResolveOwnedConcurrency` and the re-pointed ordering assertion are the tripwires | Low |
| **11** | The two source-inspection tests are deleted rather than re-pointed | Correctness | Med | **High** | Binding constraint 2; §6.3 item 15 | Low |
| **11** | Phase 09's `contact.py` rate-limiter block collides with BLOCK 11's import hoist | Contention | Med | Med | C-8; the two edits are in different regions of one file, so the rule is sequential-with-a-re-read, not parallel | Low |
| **12** | A half-moved module | Correctness | Med | **High** | One commit, explicit path staging; both processes import at start-up, so `django check` is the smoke test | Low |
| **12** | The move lands between phase 05 BLOCK 3 and phase 06 BLOCK 16, splitting one function's diff across two unrelated commits | Contention | Med | Med | Binding constraint 7; the coordinator sequences, and the block re-reads the file before editing | Low |
| **12** | `api_bulk.py` is "tidied" and phase 05's `TestBulkLockingStructure` fails | Contention | Med | Med | One import line, nothing else | Very low |
| **13** | The gate is red on arrival and someone adds 96 `noqa` comments | Process | Med | **High** | Binding constraints 1 and 2 make that a review rejection | Low |
| **13** | The gate is green and has never been seen to fire | Quality | **High** | Med | The Validator adds a deliberate deferred import in a non-excluded path, confirms `PLC0415` fires, then removes it | Low |
| **14** | A shared key exists on `/search/` and is silently absent from the shared builder | Correctness | Med | **High** | Test 1 asserts the **key set** on both views, not the values | Low |
| **14** | The "context builder" adds a query and quietly breaks the SLO | Performance | Med | Med | `test_search_query_count.py` and `test_search_slo.py` are in `tests_to_run` | Low |
| **14** | Q8(b) is taken and `listings_query.py` is edited while phase 08 BLOCK 1 holds it | Contention | Med | Med | The Q8 gate names phase 08; §5.1 hot spot 6 fixes the order | Low |
| **15** | **Q1(b) creates a new `ads → search` cross-app edge from a code-quality block** | Architecture | Med | **High** | Q1 is a three-option gate with the dependency consequence in each; the commit body records the new edge and §5.3 is updated | Med — accepted, by decision |
| **15** | ~~`TestFuzzyEquivalence` is rewritten to match the code instead of the decision~~ — **CLOSED 2026-10-03** | — | — | — | **Q6 resolved as 0.8**, the value the test already asserts, so the rewrite contingency is **moot**: the test is **green unchanged** and project rule 2 is **not invoked**. Replaced by the two rows below | Closed |
| **15** | An Implementor rewrites `TestFuzzyEquivalence` "because the shared cutoff is now a constant" | Correctness | Low | **High** | The test re-derives 0.8 **in-test** and is now a **positive control for the Product Owner decision**. Rewriting it reverts the ruling; binding constraint 4 and an acceptance criterion forbid it | Very low |
| **15** | `suggest_city`'s 0.6 survives unjustified, so the "one cutoff" claim is false | Review | **Med** | Med | **New obligation created by the Q6 ruling:** a surviving 0.6 must be justified **against the 0.8 product decision** in the commit body, as an entity-specific divergence. Acceptance criterion — Q7 can no longer be answered by silence | Low |
| **15** | The name list is re-implemented, breaking the cold/warm query-count contract | Performance | Med | **High** | `TestFuzzyQueryCount` is the tripwire; binding constraint 1 | Low |
| **15** | The finding is argued as a recall fix | Review | Med | Med | §0.4 records that on `/search/?category=` the slug is resolved by the **breadcrumb** and the ladder is reached only from `?q=`. The commit must not claim a recall improvement it cannot evidence | Low |
| **16** | **The hoisted `SubmitAdInput` passes `ad.user_id` and `AUTHZ-002`'s guard becomes permanently tautological** | Security | Med | **High** | Binding constraint 3, test 3 (the actor is asserted explicitly as `request.user.id`) and the commit-body requirement. **The single highest-consequence defect this plan can introduce** | Low |
| **16** | The extraction moves the lock but not the ownership assertion with it | Security | Med | **High** | The authorization matrix (test 2) and the re-pointed structural tests, in the same commit | Low |
| **16** | The `submit_ad` split makes `test_submit_ad_fetches_inside_atomic` raise `ValueError` instead of failing | Correctness | **High** | **High** | It is a `source.index()` assertion: moving the fetch into a helper makes the token absent and the call raises. The block must keep both tokens in `submit_ad` or re-point the test with its intent intact | Low |
| **16** | BLOCK 16 lands before phase 03 BLOCK 5 or phase 05 BLOCKs 2/8, and one silently reverts the other | Contention | Med | **High** | The external ordering in §5.1 hot spot 1, the red gate as detector, and §4.4 item 1 | Low |
| **16** | Reverting BLOCK 16 also reverts `AUTHZ-002`'s guard or `AUTHZ-007`'s assertion | Rollout | Low | **High** | The commit body states that a partial revert must revert phase 15's items separately | Low |
| **16** | The `submit_ad` split moves the file-IO half that phase 07 BLOCK 1 owns | Contention | Med | Med | BLOCK 16 touches the orchestration only; the thumbnail write path stays byte-identical (§5.2) | Low |

---

## 8. Definition of done for the whole plan

Phase 10 is complete when **all** of the following hold.

### 8.1 Scope

- [ ] All 19 findings have a recorded disposition: **18 implemented** (17 whole findings
      plus `CQ-002`'s `alerts` / `contact` / `support` halves), **1 already fixed**
      (`CQ-002`'s login half, shipped by phase 01 `ENT-005` — restated so it is not silently
      re-filed), **0 rejected**, **0 dropped without a destination**.
- [ ] Every gated block (**1, 3, 4, 5, 7, 8, 9, 11, 12, 14, 15, 16**) has a **written**
      answer for each of its open questions, naming the option chosen and the consequences
      accepted. **Silence is not an acceptable outcome for any of them.**
- [ ] Each of Q1 … Q14 is either answered with a record, or explicitly re-routed with a
      named destination. **Q1 and Q5 are coordinator/Planner rulings**; Q2 and Q4 are owner
      decisions routed through phase 15's moderation surfaces; Q3, Q9, Q10, Q12, Q13, Q14 are
      Planner decisions; Q6, Q7, Q8 are Planner with a product or phase-08 input; Q11 is
      routed.
- [ ] The `CQ-002` → `ENT-005` merge was honoured: `telegram_bot/services/login.py` does not
      exist and `handlers/login.py::_claim_login_token` still delegates to
      `apps.users.services.login_token.claim_token`.
- [ ] Every de-scoping in §6 has a named destination or a stated rationale.

### 8.2 Gates — all green

- [ ] `uv run ruff check src/` → exit 0, **with `PLC0415` enabled** (BLOCK 13) and a
      `per-file-ignores` list in which every entry is justified by a pattern.
- [ ] `uv run basedpyright src/` → **0 errors**.
- [ ] `uv run djlint src/backend/templates/` → clean under the project's ignore list, after
      BLOCKS 5 and 7.
- [ ] `.\Makefile.ps1 test` → fast gate green (`seed` marker skipped), run **after every
      block**, not only at the end.
- [ ] `makemigrations --check` → **no changes** after BLOCK 3 and BLOCK 4. **This plan ships
      no migration.**
- [ ] `apps/ads/tests/test_i18n_completeness.py` green after BLOCK 10 and — if a string was
      added — BLOCK 16.
- [ ] Every red-gate observation was **re-run serially** before being reported as a defect
      (§1.1).
- [ ] `git status --short .ai` shows **no new modifications** beyond the pre-existing
      `.ai/audit/**` deletions and this plan's own file.
- [ ] No commit was made without an explicit user request; no `git reset`, `git checkout`,
      `git restore` or `git stash` was run at any point.

### 8.3 Per-item behavioural confirmation

- [ ] **`CQ-013`** — no raw consent cookie-name literal remains at any read site; every
      cookie name, value and max-age is byte-identical; `test_consent_context.py`,
      `test_consent.py` and `test_preferred_city*.py` are green **unchanged**; the commit
      body names the Q13 option.
- [ ] **`CQ-017.1` / `.2` / `CQ-007` / `CQ-019`** — `apps/ads/services` is a regular package;
      `_get_ad_status` is still live and imported by `handlers/ad_create/entry.py` but no
      longer in `__all__`; no `cache.py` signature, key, TTL or body changed and its module
      docstring names all four caches; **`AdvisoryLockId` is byte-identical**; no file
      outside the block's list was touched; no tree-wide comment sweep happened.
- [ ] **`CQ-006`** — no raw `ru` / `bs` / `en` literal remains at the 10 named file-sites
      (including the two the report missed); the three FTS config↔column pairings are
      identical and `test_search_triggers.py` / `test_setup_search_triggers.py` are green
      **unchanged**; the three `get_name` triplications and the bot submit path resolve all
      three locales identically; the submenu cache key is byte-identical; the `enums.py`
      module docstring no longer claims a codebase-wide invariant it contradicts; the commit
      body names the Q9 option.
- [ ] **`CQ-004`** — a negative bound on either price is **refused** and nothing is created,
      through the view, on both the create and the cabinet-edit path; positive prices store
      `int`s and still match the same ads; `test_saved_search_url_resolves` still passes
      (the view is still named `save_search`); the language fallback is unchanged; no
      `_int_or_none` closure remains; **no `PreferredCityInput`, no constraint, no migration**;
      the commit body names the Q12 placement and response.
- [ ] **`CQ-005` + `CQ-018`'s URL half** — no quoted `AdStatus` value remains in any template;
      all four templates — including the unfiled `ads/edit.html` — render byte-identically;
      the moderation link resolves through the context and still filters to `on_moderation`;
      the five `redirect()` targets are `reverse()` results; no template tag library exists;
      `apps/ads/views/edit.py` is untouched.
- [ ] **`CQ-018`'s mechanical half** — all 7 guards are `@require_POST`; a non-POST still
      returns 405 on each; `review.py` and `edit.py` were not touched by that block;
      `require_http_methods` is still used zero times.
- [ ] **`CQ-003` + `CQ-018`'s `review.py` half** — an out-of-vocabulary `reason_category` is
      refused and **no** `ModeratorActionLog` row is written; all 8 members persist and the
      `"<category>: <text>"` shape is unchanged; an option is rendered for every enum member
      and none is hardcoded; **a GET never moderates or bans an ad** under either Q4 option;
      `TestModerationReviewLocking` is green **unchanged**; the commit body names both the Q2
      and the Q4 options.
- [ ] **`CQ-016`** — the 6 zero-reference symbols, the vestigial `TYPE_CHECKING` guard and
      (under Q5(a)) the 3 `RESOLVED_*_PREFIX` aliases are gone; **`can_publish_ad` is
      byte-identical**; `apps/core/__init__.py` still re-exports `CategoryRejectReason`;
      `test_account_state.py` is green unchanged; the commit body records the Q5 answer.
- [ ] **`CQ-012`** — no `# type: ignore[type-arg]` remains in production code; the score's
      five keys and names are unchanged and `update_or_create` still receives them; the
      persisted row carries the same values; `test_priority.py` is green — **unchanged**
      under Q14(a)/(c) or **explicitly rewritten with a stated justification** under
      Q14(b); `PriorityFlags` was **not** added; no model, no migration; the commit body
      states that no static gate enforces this change.
- [ ] **`CQ-014`** — the `/alerts` reply promises no numeric toggle and no `/cancel` step; the
      three existing entry points and the deep-link parser are unchanged; no handler, FSM
      state or parsing was added; `SavedSearchState` is still absent; `ru` and `bs` are
      non-empty for the new string; `_resolve_owned` was not moved.
- [ ] **`CQ-002`** — every `/alerts`, unsubscribe and re-enable answer is byte-identical
      before and after; `telegram_bot/services/alerts.py` holds the four functions with their
      `atomic()` and `select_for_update()` intact; **no** `login.py`, `contact.py` or
      `support.py` service module was created; no function-local `apps.*` import remains in
      the three handlers; `TestResolveOwnedLocking` is green and now inspects
      `telegram_bot.services.alerts._resolve_owned`; `test_alerts.py`, `test_unsubscribe.py`
      and `test_login.py` are green.
- [ ] **`CQ-010`** — `admin_actions.py` exists only at
      `apps/moderation/services/admin_actions.py` with a **byte-identical** body; all three
      importers point at the new path; `review.py` has no function-local import of it;
      `test_admin_actions.py`, `TestModerationReviewLocking` and `test_auth_nav.py` are green
      **unchanged**; `apps/moderation/apps.py` and `admin.py` are untouched; `ruff check src/`
      is green with `PLC0415` and a pattern-justified exclusion list; **no** `noqa` and no
      custom script; the Validator saw the rule fire on a deliberate deferral.
- [ ] **`CQ-015`** — all 20 shared keys reach the template context on **both** `/` and
      `/search/`; the 6 search-only keys are on `/search/` only;
      `test_listings_context.py` is green **unchanged**, including
      `test_listings_query_params_rejects_unknown_key`; `test_search_query_count.py` and
      `test_search_slo.py` are green (no query added or removed); `ListingsQueryParams` and
      `ListingsQuery.build_queryset` are unchanged; `_suggest_category` was untouched by this
      block; the commit body names the Q8 option.
- [ ] **`CQ-011`** — one ladder and one named cutoff serve both `/` and `/search/`; an exact
      slug and an exact localised name now resolve on `/`; `TestFuzzyQueryCount` is green
      **unchanged** (one SELECT cold, zero warm); `TestFuzzyCategoryMatch` is green
      **unchanged** (both exact tiers survive); `TestFuzzyEquivalence` is green — if it
      changed, the commit body states the Q6 option and that the test was updated to the
      decided behaviour; `apps/categories` imports nothing from `apps.search`; an
      unresolvable slug still yields `None`; the commit body records Q1, Q6 and Q7.
- [ ] **`CQ-001` / `CQ-008` / `CQ-009`** — owner GET 200, owner POST saves, non-owner GET and
      POST both 403; **the ownership assertion runs on the locked instance inside the
      transaction**; the hoisted `SubmitAdInput` passes `user_id=request.user.id`, asserted
      explicitly, and **never `ad.user_id`**; the reactivation and both error branches use
      the authorized locked instance and never re-fetch unlocked; a POST omitting `title` is
      refused and the live ad's title is byte-identical, while an empty `title` still saves;
      a failed validation writes nothing; every branch suite in `test_edit.py` is green
      **unchanged**; all four `TestEditViewsLocking` tests are green and still assert the
      locking intent; the GET path still performs no lock and still prefetches; the commit
      body names `AUTHZ-007` and `AUTHZ-002` as satisfied by construction, the Q3 option and
      each re-pointed test.

### 8.4 Cross-phase integrity

- [ ] `apps/ads/views/edit.py` was edited by **BLOCK 16 only**, after phase 03 BLOCK 5, phase
      05 BLOCKs 2 and 8, and phase 15's `AUTHZ-007` and `AUTHZ-002`.
- [ ] `apps/ads/services/submission.py` was edited by **BLOCK 16 only**.
- [ ] `apps/moderation/admin_actions.py` was moved **once**, by BLOCK 12, after or before —
      never during — phase 05 BLOCK 3 and phase 06 BLOCK 16. Its body is byte-identical.
- [ ] `apps/core/enums.py` was edited by **BLOCK 3 only**; `AdvisoryLockId` is byte-identical;
      **no lock id was allocated**; no other phase's uncommitted `enums.py` work was
      reverted.
- [ ] `apps/search/models.py` gained no bound, no constraint and no migration; `ListingsQueryParams`
      and `ListingsQuery.build_queryset` are unchanged; `category_fuzzy.py` is unchanged.
- [ ] The FTS trigger, `ads_search_vector_fn`, `on_category_name_update`, `setup_search_triggers`
      and every `RunSQL` block are byte-identical.
- [ ] `handlers/login.py` is unchanged; `apps/users/services/login_token.py` is unchanged.
- [ ] `config/settings/**`, `.env*`, `docker-compose*.yml` and `docker/nginx/**` are
      unchanged by every phase-10 block.
- [ ] `src/backend/conftest.py` is **unmodified**. No `docs/` file is modified.
- [ ] Locale files were **appended** to, never regenerated; `ru` and `bs` are non-empty for
      every new string.
- [ ] No `.ai/audit/**` file was created, restored or modified; no other phase's plan or
      handbook was edited; the in-source ID sweep was **not** started.
- [ ] The coordinator was told of: the BLOCK 12 move's five-phase reservation, the BLOCK 16
      external ordering, the Q5 answer, the Q11 routing, and (under Q1(b)) the new
      `ads → search` edge.

### 8.5 Project conventions

- [ ] Every new constant is a named module-level constant or a `StrEnum` member — never an
      inline literal or a dict-of-strings (project rule 10). The single exception is the
      Q9-recorded `fts_config` / `fts_vector_field` shape, if option (b) was chosen.
- [ ] No `print()`; `logger = logging.getLogger(__name__)` with lazy `%s` formatting.
- [ ] All comments, docstrings, log messages, error messages and docs are in **English**.
- [ ] **Django ORM is the persistence layer; Pydantic v2 only at a system boundary.** Two
      DTOs were added (`SavedSearchInput` at the POST edge, `PriorityScore` as an internal
      typed value); **neither became a model, and neither is a framework.**
- [ ] No migration was created; no applied migration was renumbered or edited.
- [ ] Business logic lives in `services/`; no new logic was added to a view or a handler
      beyond the thin boundary change its block requires.
- [ ] Small, focused modules. The one new module (`edit_ad`) does one thing; the one new
      service module (`alerts.py`) moves four functions and adds nothing.
- [ ] Composition over inheritance; no base class, manager class, registry or service
      locator was introduced.
- [ ] No speculative redesign: every §6.1 de-scoping was respected, and no block
      "restored" one as a side effect.
- [ ] Every non-trivial behaviour change has a test that verifies **logic and component
      interaction**. **BLOCKS 2, 6, 8, 12 and 13 add no behavioural test**, and that absence
      is deliberate and recorded here.
- [ ] The four source-inspection tests were **re-pointed, never deleted**, and each
      re-pointing is named in its commit body.
- [ ] No task target is a line number; every target is a file plus a semantic symbol.
- [ ] `ruff check --fix` was scoped to the files the block edited; `ruff format` was not run.
- [ ] Every new finding citation is cycle-scoped `10-CQ-0NN`; no bare `CQ-0NN` and no
      `QLT-0NN` was written into a comment, a docstring or a commit message.

### 8.6 Deliverables

- [ ] The BLOCK 12 move's five-phase reservation was communicated to the coordinator before
      the move ran.
- [ ] The BLOCK 16 external ordering (phase 03 BLOCK 5 → phase 05 BLOCKs 2/8 → `AUTHZ-007` →
      `AUTHZ-002`) was communicated, and the alternative of **folding** BLOCK 16 into one of
      them was offered explicitly.
- [ ] Q5 (`RESOLVED_*_PREFIX` external importers) was put to the coordinator, and the answer
      is recorded in BLOCK 8 and in its commit body.
- [ ] Q11 (`QLT-###` vs `10-CQ-0NN`) was routed to the coordinator.
- [ ] Q1 and Q8 were put to phase 08, and the phase-08 view is recorded in BLOCKs 14 and 15
      and in their commit bodies.
- [ ] Q2 and Q4 were put to the owner / phase 15's moderation surfaces. **Q2 is ANSWERED —
      2026-10-03, Product Owner, option (b): re-render, preserve the moderator's input.** Q4's
      option is named in BLOCK 7's commit body.
- [ ] **Q2's ruling was communicated to phase 15**, whose own `Q11` covers the same question and
      must not re-open it (§0.7, §5.4).
- [ ] **Q6 was put to the owner and ANSWERED — 2026-10-03, Product Owner: the unified fuzzy
      cutoff is 0.8.** BLOCK 15's commit body names it and states that project rule 2 was **not**
      invoked, because `TestFuzzyEquivalence` is green unchanged. If Q7 kept `suggest_city`
      separate, its surviving 0.6 is justified against that decision.
- [ ] **`CQ-014`'s declined toggle is recorded as a feature request with a named owner** (§6.1,
      §0.7), so the surviving "prompt fixed, toggle still absent" risk is a tracked backlog item
      and not an undocumented gap.
- [ ] The §6.2 routings (phase 15's `AUTHZ-002`/`AUTHZ-007`/`AUTHZ-005`, phase 01's `ENT-004`
      / `ENT-005`, phase 03's `DB-001`, phase 09's `API-009`/`API-010`, phase 07 BLOCK 11's
      legacy sweep) are recorded as **routed**, with evidence that phase 10 did not silently
      drop them.
- [ ] This plan file is updated to mark each block's completion, so the phase coordinator has
      a single status surface.
- [ ] No commit was made without an explicit user request.

Phase 10 is complete when the last unchecked box above is checked, the BLOCK 12 and BLOCK 16
reservations are with the coordinator, and every gate in §0.5 has a written answer.