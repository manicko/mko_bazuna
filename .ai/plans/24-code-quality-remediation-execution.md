# Plan 24 — Phase 10 Code-Quality Remediation (Re-Scoped Execution Plan)

## 0. Header, provenance, drift control

### 0.1 Identity

| Item | Value |
|---|---|
| Plan id | `24-code-quality-remediation-execution` |
| Numbering | 24 |
| Phase | 10 — Code Quality |
| Date | 2026-10-05 |
| Planner | Planner (subagent) |
| **Source plan** | `.ai/plans/10-code-quality-remediation.md` (3586 lines), anchor **`6413df5`** — **16 blocks, unexecuted** |
| **Code-context audit** | `.ai/tmp/code-context-phase10-r2.md` (round 2, 145 lines), audited at **`7f43e535`** |
| **Validated report (narrative source, inherited)** | `.ai/audit/99-validation/10-code-quality-validated-findings.md`, report anchor `aa2a6b0` |
| Findings in scope | 19 (`CQ-001` … `CQ-019`), re-triaged by the audit into **surviving / moot / re-scoped** |
| **Blocks in this plan** | **13** (`B-1` … `B-13`). Of these: **1 conditional** (`B-4`, subject verified live by this Planner), **1 blocked** (`B-13`), **1 decision-only with no expected code change** (`B-10`) |
| **Blocks retired without replacement** | **5** original blocks (`6`, `12`, `13`, and the `CQ-018` half of `7`, the `CQ-019`/docstring half of `2`, the `CQ-005` half of `5`) plus the dead DTO half of `4` |
| Migration | **none.** No block ships a schema change, a data movement, or a `makemigrations` |
| Implementor concurrency | **1**, strictly sequential. One commit per block. `"{type}({scope}): {description}"` |
| Execution order | **not** the source plan's numbering — see §3 and §7 |
| Citation rule | **semantic anchors only.** Files, modules, classes, functions, enum members, `Final` constants, test node IDs. **No line number is a target anywhere in this plan or in any task derived from it** (inherited verbatim from plan 19's citation rule) |

### 0.2 Why this plan exists

The source plan is anchored at `6413df5`. The audit read the tree at `7f43e535`. In that
window **two vocabularies shipped 18 commits of the same report's refactor programme under
`10-QLT-###`, and zero commits under the source plan's `10-CQ-###`.** Six of the source
plan's sixteen blocks are now moot, one is dropped on proportionality grounds, and the
highest-risk block's own blocking precondition is unmet on two of five prerequisites.

**This plan replaces the source plan for execution.** The source plan is **not** edited and
remains the narrative record of *why* the findings were filed. Where this plan and the source
plan disagree, **this plan wins**, because it is written against the tree and the audit is the
tree's authority.

### 0.3 Evidence basis

| Source | Role |
|---|---|
| `.ai/tmp/code-context-phase10-r2.md` | **Primary.** Re-measured block table, gate status, risk register, test clusters, `PLC0415` count |
| `.ai/plans/10-code-quality-remediation.md` | Narrative source for *why* each block existed, its severity, and its rejected alternatives. Read-only |
| `git log --all` (`10-CQ-` / `10-QLT-`) | Shipped-vocabulary evidence. Read-only |
| This Planner's own spot checks (5 reads, 4 greps, 1 `git log`) | The three corrections in §1.3, and the `10-QLT-###` inventory in §2. Each is quoted with evidence |
| `.kilo/rules/project.md`, `.kilo/rules/commands.md`, `AGENTS.md` | Repo rules and the Windows/Docker command contract |
| `.ai/plans/19-moderation-privilege-guard-execution.md` | Cross-phase owner of `apps/moderation/admin_actions.py` and of `review.ban_user`. Read-only reference |

**No test suite was run, no `makemessages`/`compilemessages` was run, and no file outside this
one was written.** Every count in this plan is either quoted from the audit with its method, or
re-derived here with the command shown.

### 0.4 The four hazards that constrain any implementor

Carried forward from the source plan §0.2.2, restated against the tree. **Unchanged.**

1. **`ads/views/edit.py` is the hottest file in the plan set.** `ad_edit` is pointed at by
   phase 03 BLOCK 5, phase 05 BLOCKs 2/8/12, phase 07 BLOCK 10, phase 15's `AUTHZ-002`/`AUTHZ-007`
   — **and** by shipped `10-QLT-004` (`db01a73f`, which made `ad_edit` delegate its text-edit to
   `submit_ad`). One block, one commit, last in the order.
2. **`apps/moderation/admin_actions.py` is held by plan 19**, which chose *"Option A — extend in
   place"* for the `is_banned` guard (`19-Q1` RESOLVED). **Phase 10 has no block on this file.**
3. **`apps/core/enums.py` is the most-churned shared file in the repo** (audit: seven post-anchor
   commits, plus shipped `3eab60d8`/`4e26669a` under `10-QLT-002`, which added `ConsentVersion`).
   Exactly one block (`B-2`) may edit it, and it must re-read the file immediately before editing.
   **No phase-10 block allocates an `AdvisoryLockId` and none renumbers the enum.**
4. **Source-inspection tests are the highest-risk class in this phase.** Four clusters are live
   (§6.2). Every block that moves a function names the test it must **re-point**, in the same commit.

### 0.5 Verdict summary

```
16 original blocks
  ├─ 13 blocks survive   (B-1 … B-13)   ← of which B-4 conditional, B-10 decision-only, B-13 blocked
  ├─  5 blocks retired without replacement
  │     · 6  — shipped as 09-API-010
  │     · 12 — the move already happened, to a third path, and plan 19 now owns the file
  │     · 13 — PLC0415 at 869 sites: dropped on proportionality, routed as a tooling-policy gate
  │     · 7  — the CQ-018 half shipped as 09-API-010; the CQ-003 half survives as B-4
  │     · 5  — the CQ-005 half has no referent; the URL half survives as B-3
  └─  4 halves retired inside surviving blocks (2's cache.py docstring, 4's DTO, 8's api/ tree, 16's CQ-009)
```

---

## 0.6 Execution status log (appended by the Tech Lead, 2026-10-05; completed 2026-10-06)

**This plan is complete for every executable block.** Eleven of thirteen blocks are committed
(`B-10` ships nothing by design; `B-13` remains `blocked`). The table below is the authoritative
final status; it was re-derived with `git log --all --oneline | Select-String "10-CQ-"` on
2026-10-06.

| Block | Finding | Status | Commit |
|---|---|---|---|
| `B-1` | `CQ-017.1/.2`, `CQ-007` residue | **COMMITTED** | `72599594` (`10-CQ-017`) |
| `B-2` | `CQ-006` | **COMMITTED** | `7b2662a6` (`10-CQ-006`) |
| `B-3` | `CQ-018` (URL half) | **COMMITTED** | `cdbdbb75` (`10-CQ-018`) |
| `B-4` | `CQ-003` | **COMMITTED** | `6d37b5db` (`10-CQ-003`) |
| `B-5` | `CQ-013` | **COMMITTED** | `65f2e783` (`10-CQ-013`) |
| `B-6` | `CQ-016` | **COMMITTED** | `6236f7d0` (`10-CQ-016`) |
| `B-7` | `CQ-004` | **COMMITTED** | `4f81711e` (`10-CQ-004`) |
| `B-8` | `CQ-014` | **COMMITTED** | `c6c98518` (`10-CQ-014`) |
| `B-9` | `CQ-002` (alerts half) | **COMMITTED** | `29a1db94` (`10-CQ-002`) |
| `B-10` | `CQ-012` | **CLOSED** — decision-only, zero commits (see §3 B-10 RESULT) | — |
| `B-11` | `CQ-015` | **COMMITTED** | `f2ffb39e` (`10-CQ-015`) |
| `B-12` | `CQ-011` | **COMMITTED** | `910b66d4` (`10-CQ-011`) |
| `B-13` | `CQ-001` | **BLOCKED** — four unmet preconditions | — |

**No executable block remains.** `B-13` does not start until phase 03 BLOCK 5 and phase 15
`AUTHZ-007` land. `B-10` ships nothing. New findings discovered during execution are recorded in
§0.6.3.

### 0.6.1 Audit corrections for the remaining blocks (Auditor, 2026-10-05)

Five corrections to the block text below, each independently verified against HEAD. **The
corrections win over the block prose where they disagree; the binding constraints and acceptance
criteria of each block are unchanged.**

1. **`B-3` anchor imprecision — the `/change/` redirect is in `approve_ad`, not
   `moderation_review`.** `moderation_review` returns `render(...)` only and has **no redirect at
   all**. The hardcoded `/admin/ads/ad/{ad_id}/change/` redirect lives inside `approve_ad`, which
   the block already lists as a *read-only reference* — it is now also a **target**. The three
   edit targets are therefore `approve_ad`, `reject_ad`, `ban_user` in
   `apps/moderation/views/review.py`, plus the changelist `href` in
   `templates/analytics/moderation_dashboard.html`. `reverse` is **not** currently imported;
   add `from django.urls import reverse`. Both `admin:ads_ad_change` and `admin:ads_ad_changelist`
   **resolve at HEAD** (verified via the dev Django shell). **Plan 19 `B-2` has landed and has not
   touched `review.py` or `review.html` since this plan was written** — the external ordering
   dependency is satisfied and the `B-4` template-collision risk is dormant.
2. **`B-4` — the defect is verbatim live; `TestModerationReviewLocking` asserts token presence,
   not a count** (`"transaction.atomic" in source` and `"select_for_update" in source` for
   `reject_ad` and `ban_user`). `moderation_review`'s context is a **single key** (`{"ad": ad}`);
   `G-4a`(a) extracts that one-key contract. `answer`/the four reject tests post
   `reason_category="spam_scam"` (a valid member). The template has **not** been touched by plan
   19. `CategoryRejectReason` has exactly the 8 members the block lists, values matching the
   template's 8 `<option>` literals byte-for-byte.
3. **`B-9` — a second source-inspection class must be re-pointed: `TestResolveOwnedConcurrency`.**
   Plan §5.1 names only `TestResolveOwnedLocking`, but `TestResolveOwnedConcurrency` (same test
   module) also imports `_resolve_owned` **from the handler** and turns red if the function moves
   without it. Both classes are re-pointed at `telegram_bot/services/alerts.py` in the same commit.
   Exactly **two** ORM sites exist (`get_user_saved_searches`, `_resolve_owned`); `select_for_update()`
   is the first statement **inside** `with transaction.atomic():`. The plan's claim that phase 01
   `ENT-005` "shipped `login.py`" is inaccurate — `services/login.py` does not exist — but the
   binding constraint ("do not create it") still holds. `SET LOCAL lock_timeout` remains absent;
   **option (c) — byte-preserved lock shape — is the resolution** per §4.1.
4. **`B-12` — `Q1` must reconcile slug-matching vs localized-name-matching, not only a cutoff.**
   `ads/views/listings.py::_suggest_category` matches **category slugs** via a direct
   `Category.objects.filter(...).values_list("slug")` query, whereas `search/views/search.py`'s
   ladder matches **localized names** from `category_fuzzy.get_active_category_names`. The shared
   "one name list" premise does not hold as-is for the ads site. Current graph:
   `search → categories`, `search → ads` (the latter introduced by B-11 `f2ffb39e`), and **no**
   `ads → search` edge (which `Q1`(b) would create). Post-B-2, the fuzzy neighbourhood holds no
   bare locale literal. `TestFuzzyEquivalence` re-derives `0.8` and must stay **byte-unchanged**.
5. **`test_i18n_completeness.py` path correction.** Several `tests_to_run` lists name
   `src/backend/tests/test_i18n_completeness.py`; the file actually lives at
   **`src/backend/apps/ads/tests/test_i18n_completeness.py`**. The fast gate still exercises it.

### 0.6.2 Gate rulings applied to the remaining blocks

Per §4.0 (standing instruction: take the recommended option; stop interrupting the owner), the
remaining technical gates are decided as follows and are binding on the Implementor:

| Gate | Block | Ruling applied |
|---|---|---|
| `G-4a` | `B-4` | **Option (a)** — extract `moderation_review`'s one-key context into a module-private helper; `reject_ad` re-renders with the error and the preserved `reason_category`/`reason_text`. |
| `Q1` | `B-12` | **Option (a)** — ladder in `apps/categories/services/fuzzy.py` with the name list **injected**; no new `ads → search` edge. `_suggest_category` injects its slug list; the search ladder injects `get_active_category_names`. |
| `Q7` | `B-12` | **Option (b)** — `suggest_city` stays separate; its surviving `0.6` **must be justified in the commit body** as an entity-specific divergence from the ruled `0.8`. |

### 0.6.3 Execution result and new findings (Tech Lead, 2026-10-06)

**Result.** `B-3` → `B-4` → `B-9` → `B-12` all landed, one commit per block, in the ruled order
(`cdbdbb75`, `6d37b5db`, `29a1db94`, `910b66d4`). The final fast gate is green
(`.\Makefile.ps1 test`: 3448 passed, `seed` skipped). No migration was written; no
`AdvisoryLockId` member was touched; no `type: ignore` was added, removed or narrowed; no
source-inspection test was deleted or relaxed; `TestFuzzyEquivalence` is byte-unchanged and
green (project rule 2 invoked zero times). `B-13` remains blocked.

**Deviations from the block prose, recorded (all within the blocks' binding constraints):**

1. **`B-4` — the reject-modal `<option>` list stays hardcoded markup.** `G-4a`(a)'s mechanism is
   the shared `_review_context` builder; sourcing the option list from the enum would require
   editing the read-only `apps/core/enums.py` (a `B-2`-only file) or adding a labels API, and
   binding constraint 5 forbids a generic enum-in-template mechanism. The vocabulary is still
   enforced at the boundary. An invalid category cannot match any option by construction, so the
   select resets to its prompt; the raw value is preserved in the context and the typed comment
   is repopulated in the textarea. One new msgid (not two), per §5.1's i18n obligation.
2. **`B-9` — a third `_resolve_owned` test site was re-pointed.**
   `test_lock_timeout_boundary.py::TestResolveOwnedLockTimeout` both imports `_resolve_owned`
   from the handler and patches the handler's `SavedSearch` reference; it is re-pointed at
   `telegram_bot/services/alerts.py` in the same commit with its assertion unchanged. §0.6.1
   item 3 named only the two `test_unsubscribe.py` classes.
3. **`B-12` — the new module is `apps/categories/services/fuzzy.py`** per the `Q1`(a) ruling,
   holding `match_category(query, candidates)` (exact tier + fuzzy tier) and
   `CATEGORY_FUZZY_CUTOFF = 0.8`. The listings did-you-mean gains the exact-match tier; the
   search side still loads its one cached name list from `get_active_category_names`.

**New findings discovered during execution — recorded, NOT fixed (each is outside every block's
closed file surface):**

| # | Finding | Evidence | Suggested routing |
|---|---|---|---|
| NF-1 | `templates/admin/moderation/review.html`'s relative form actions are off by one level under the trailing-slash URL: from `/moderation/review/<id>/`, `../approve/<id>/` resolves to `/moderation/review/approve/<id>/` (404), `../` to `/moderation/review/`, etc. The queue links to the admin change page, not the review page, so the broken surface is currently unreachable from the UI. | RFC 3986 resolution verified with `urljoin`; `apps/moderation/urls.py` serves `review/<int:ad_id>/`; no template or view references `moderation:review`. | New block: fix the four form actions + back link (`../../…`) or re-point them at `{% url %}`. |
| NF-2 | A fourth fuzzy site: `telegram_bot/handlers/ad_create/city.py` calls `difflib.get_close_matches(..., cutoff=0.6)` inline for city names. `Q7`(b) ruled only the web `suggest_city`; this bot site is a different tier and was outside `B-12`'s surface. | Source read; absent from every block's file list. | New finding: decide whether bot city matching joins a shared city-fuzzy helper or stays entity-specific with a named constant. |
| NF-3 | The checked-in locale catalogs are stale: a full `makemessages` extraction surfaces an unrelated untranslated msgid (`Password does not meet the password policy: %(errors)s`, from `create_admin_user.py`) with empty `ru`/`bs` `msgstr`. `B-4` hand-inserted only its new msgid to keep the diff scoped; the i18n gate is green. | Reproducible `makemessages` run during `B-4`. | Phase 25 / i18n owner: full catalog refresh and fill the missing translations. |
| NF-4 | `apps/search/tests/test_search_slo.py::TestSearchResponseSLORegression` is a single-sample 2000 ms wall-clock bound and is load-flaky on this Windows/Docker host (2.7 s–6.2 s under load; passes when idle; unrelated to phase-10 changes). | Three independent runs, including with all phase-10 changes stashed. | Phase 11 / test-quality owner: mark it environment-sensitive or convert it to a load-run percentile. |
| NF-5 | `uv run djlint` fails with `ModuleNotFoundError: djlint_custom_rules` (the module exists at `src/backend/djlint_custom_rules.py` and is declared in `pyproject.toml` but is not importable in the uv env); `PYTHONPATH=src/backend uv run djlint …` is clean. | Reproduced during `B-3`/`B-4`. | Tooling owner: fix the editable-install exposure or document the workaround in `.kilo/rules/commands.md`. |

---

## 1. Reconciliation — all 16 original blocks

### 1.1 The table

| Orig | Finding(s) | Audit verdict | **This plan's verdict** | Where it lands |
|---|---|---|---|---|
| **1** | `CQ-013` consent-cookie constants | **Yes** — symbols, path and lines all match; zero drift | **still needed** | **B-5** |
| **2** | `CQ-017.1`, `CQ-017.2`, `CQ-007`, `CQ-019` | **Partly** — 2 of 3 premises rotted; the docstring was rewritten by `09-API-001`/`09-API-002`/`08-SRCH-007`; "12 wrappers" is now 15 triads + 3 primitives | **re-scope to B-1.** Two halves survive: the absent `ads/services/__init__.py`, and the private name in `orm.py`'s `__all__`. The **module** docstring trim is **moot**; the three *per-function* docstrings that still misname their subject survive; the 12-wrapper boilerplate trim is **declined** (§8) | **B-1** |
| **3** | `CQ-006` locale literals | **Yes** — defect confirmed verbatim; `10-QLT-002` fixed call-site defaults only, not the two dicts | **still needed** | **B-2** |
| **4** | `CQ-004` saved-search Pydantic boundary | **Re-scoped** — `SavedSearchInput` does not exist; `save_search.py` moved to `apps/search/views/`; the duplicated closure is verbatim | **re-scope to B-7** — the **DTO-as-named is dead** (never existed, so nothing is re-filed); the **duplicated closure is live** | **B-7** |
| **5** | `CQ-005` + `CQ-018` URL half | **Half** — no `AdStatus.` token in any template; three hardcoded admin URLs live | **split.** AdStatus-in-templates: **moot**, no referent. URL half: **still needed** → **B-3**. Note one further live URL site the audit did not list: `analytics/moderation_dashboard.html`'s `href` to the admin ad changelist | **B-3** |
| **6** | `CQ-018` mechanical half | **No — already shipped** as `09-API-010`; `@require_POST` on 13 views incl. `review.py`'s three | **moot.** No block, not a shrunken one | — |
| **7** | `CQ-003` + `CQ-018` (`review.py`) | **No — premise rot**: `reject_ad` is `@require_POST` + `@staff_required`; "302 on GET" is false. **Q4 has no subject** | **split, and this is where this plan departs from the audit's row.** The `CQ-018` 405 half is **moot** (shipped as `09-API-010`). The **`CQ-003` half is live** — verified by this Planner, see §1.3 item 1 — and a Product Owner ruling already commits to its delivery | **B-4** |
| **8** | `CQ-016` delete unreferenced code | **Yes** — `RESOLVED_*_PREFIX` still defined, **0 importers**; the `apps/api/` tree premise is **stale** (already gone) | **re-scope to B-6** — deletion-only, on the surviving dead symbols. This Planner additionally confirms two further zero-importer symbols the audit did not enumerate (§1.3 item 2) | **B-6** |
| **9** | `CQ-012` typed boundaries + ignores | **Yes, re-measured** — `type: ignore` on **83 lines**, not 4 (**~20× stale**) | **re-scope to B-10 — decision-only.** The named scope ("4 suppressions") cannot be executed; a repo-wide suppression sweep is a legacy sweep that phase 03 BLOCK 11 reserves. The deliverable is an **inventory + routing decision**, not a diff | **B-10** |
| **10** | `CQ-014` `/alerts` prompt | **Yes — fully live**, **zero drift**; all three router entry points unchanged | **still needed**, plus the dead-state deletion the Product Owner's `CQ-014` ruling assigned to the source plan's dead-code block | **B-8** |
| **11** | `CQ-002` `alerts` half | **Yes** — live, and the surface is **larger** (5 candidates, not 2) | **still needed** | **B-9** |
| **12** | `CQ-010` move half | **No — already moved elsewhere.** The file is at the package **root**, not `views/`, not `services/`; the old path has **no git history** | **moot.** A move to a third path is not this plan's move. Plan 19 now owns the file's contents and chose to extend it in place | — |
| **13** | `CQ-010` lint half | **Yes, 9.1× under-scoped** — `PLC0415` absent from `select`; **869** sites, not 96 | **DROPPED on proportionality.** Not justified at 869 sites. Routed as a tooling-policy gate for the coordinator, not an implementor choice (§4.2, `G-9`) | — |
| **14** | `CQ-015` listings-context builder | **Re-shaped** — `ListingsQueryParams` is now a Pydantic `BaseInputModel`; the "20-kwarg build" is gone; the two independent constructor calls remain | **re-scope to B-11.** The duplication is real but is now *two constructor calls + two service calls per view*, not a 20-key literal | **B-11** |
| **15** | `CQ-011` fuzzy ladder / cutoff | **Yes, exact** — `0.6` in one view, `0.8` in another, `0.8` re-derived in-test; **zero drift** | **still needed.** `Q6` is RESOLVED (`0.8`) **but the ruling has not been applied to the tree** | **B-12** |
| **16** | `CQ-001`, `CQ-008`, `CQ-009` | **Yes — and riskier.** **R0:** 3 of 5 external prerequisites landed, **2 did not** | **re-scope to B-13 and BLOCK it.** This Planner's reading of the shipped `10-QLT-###` stream (§1.3 item 3) reduces this from a three-finding coordinated change set to **one single-symbol extraction** — which does *not* make it executable, because the unmet `AUTHZ-007` precondition is exactly the hole the extraction closes | **B-13** (last, blocked) |

### 1.2 The moot verdicts, stated explicitly

Five blocks and six halves of the source plan are dead — **six verdicts**, listed with the
evidence that retired them. **None gets a replacement block, and none is "re-scoped to something
smaller" simply to keep a slot filled.**

| # | What is moot | Why, in one sentence | What would revive it |
|---|---|---|---|
| **1** | **BLOCK 6** — the 7 inline `request.method` guards → `@require_POST` | Shipped as **`09-API-010`**; the decorator is present on 13 views including all three `review.py` views, and `test_moderation_views.py`'s own docstrings name the commit | Nothing. It is done. |
| **2** | **BLOCK 12** — move `admin_actions.py` into `services/` | The file is already at `apps/moderation/admin_actions.py`; the plan's target path has never existed and the old path has no git history. Plan 19 (`19-Q1` RESOLVED, Option A) now extends the module in place | Nothing in this phase. A *fourth* relocation would undo plan 19's decision |
| **3** | **BLOCK 13** — enable `PLC0415` | `869` sites, not 96. The exclusion list would be a 869-line carve-out for a rule whose fix is 869 mechanical edits — and `moderation/views/review.py`'s deferred import of `admin_actions` is **load-bearing view→service indirection**, which plan 19 and phase 09 both rely on. A bulk `# noqa` sweep is forbidden by the source plan's own §6.3 and is not a fix | A **tooling-policy decision** by the coordinator (`G-9`), which must choose a per-file/per-directory exclusion *strategy* before any code block could exist |
| **4** | **BLOCK 7's `CQ-018` half** — `reject_ad`/`ban_user` 302→405 | `reject_ad` and `ban_user` already stack `@require_POST` on `@staff_required`. **Q4 has no subject left** | Nothing |
| **5** | **BLOCK 5's `CQ-005` half** — `AdStatus` out of templates | **Zero `AdStatus.` tokens exist under `templates/**`.** Either it was resolved elsewhere or the claim was wrong at `6413df5`; either way there is nothing to remove | A new template that compares against a bare status literal |
| **6** | **BLOCK 2's `cache.py` module docstring** — the stale `ModerationCriteria` claim | Rewritten by `09-API-001`, `09-API-002` and `08-SRCH-007`; the docstring now declares the cache-failure and version-key contracts and names the triads | Nothing |

Plus two halves retired inside surviving blocks:

- **BLOCK 4's `SavedSearchInput` DTO as a named artifact** — it has never existed anywhere in
  the tree, so there is nothing to re-file and no prior art to preserve. Its *duplicated
  closure* is live and becomes `B-6`.
- **BLOCK 16's `CQ-009`** — shipped as **`10-QLT-004`** (`db01a73f`), with `AdEditInput` in
  `apps/services/submission.py` and wired in the edit view. See §1.3 item 3.

### 1.3 Corrections to the audit — three items, each with evidence

The audit is authoritative on measurement. It is **not** fully authoritative on adjudication:
it re-measured, and three of its conclusions need narrowing. Each correction below is
independently verified by this Planner.

#### Item 1 — BLOCK 7 is **not** wholly moot. `CQ-003` is live, and a Product Owner ruling is already attached to it.

The audit's block-7 row adjudicates the block by its `CQ-018` premise and returns "No —
premise rot". Its own risk R4 says the block *"should be re-scoped to whatever the actual
remaining defect is"*, but it does not identify one. This Planner did, and the defect is
unambiguous:

| Evidence | Reading |
|---|---|
| `apps/moderation/views/review.py` → `reject_ad` | `reason_category = request.POST.get("reason_category", "") or ""` is read from the POST **with no membership check**, then interpolated into the audit-log reason string (`reason = f"{reason_category}"`, and `reason = f"{reason_category}: {reason_text}"` when a comment is present). **Any client string reaches `ModeratorActionLog.reason`.** |
| `apps/core/enums.py` → `class CategoryRejectReason(StrEnum)` | Exists with exactly 8 members (`ADULT_CONTENT`, `VIOLENCE_GORE`, `DRUGS_WEAPONS`, `HATE_SPEECH`, `COUNTERFEIT_GOODS`, `ILLEGAL_GOODS`, `SPAM_SCAM`, `OFF_TOPIC`), and is re-exported from `apps.core`. **The vocabulary exists; only the boundary enforcement is missing.** |
| `templates/admin/moderation/review.html` → the reject modal's `select[name="reason_category"]` | **8 hardcoded `<option value="…">` literals**, one per enum member. The vocabulary is duplicated a second time, in markup. |
| `apps/moderation/tests/test_moderation_views.py` | Four existing reject tests post `reason_category="spam_scam"`, a **valid** member. The change is therefore **additive for them** — they are expected to stay green unmodified. |
| Source plan `Q2` | **RESOLVED 2026-10-03 by the Product Owner: re-render the review page with an error and preserve the moderator's typed input.** The 400 reading is **declined**; nothing is coerced to empty; no arbitrary client string may reach the audit row. |

**Consequence.** Deleting `CQ-003` as moot would silently discard a Product Owner ruling that
was made *after* the source plan's anchor, for a defect that is demonstrably still in the
tree. `CQ-003` therefore survives as **`B-4`**, carrying `Q2`'s ruling as a *decided*
constraint and exactly one *new* mechanism gate (§4.1, `G-4a`). **The `CQ-018` half of the
source plan's BLOCK 7 stays dead.**

#### Item 2 — BLOCK 8's dead-symbol list is **wider** than the audit's three.

The audit verified only the `RESOLVED_*_PREFIX` aliases. Two further zero-importer symbols in
the same class were confirmed by this Planner and join `B-6`:

| Symbol | File | Reference count |
|---|---|---|
| `is_consent_given(request)` | `apps/users/views/consent.py` | Definition only. Zero `.py` importers repo-wide |
| `SavedSearchState(StrEnum)` | `telegram_bot/states.py` | Definition only. Zero `.py` importers repo-wide — the audit's own block-10 evidence confirms `CQ-014`'s report finding that it has 0 call sites |
| the module-level `if TYPE_CHECKING: pass` guard and its now-orphaned `from typing import TYPE_CHECKING` | `apps/categories/services/lookup_resolution.py` | The guard's body is `pass`; `TYPE_CHECKING` is imported **only** to feed it, so deleting the guard must delete the import or `ruff` `F401` fires |

`SavedSearchState` is assigned to **`B-8`**, not `B-6`: it is half of the Product Owner's
`CQ-014` ruling, and it lands in the same commit as the prompt correction that ruling names.

#### Item 3 — BLOCK 16 is **one** extraction, not a coordinated three-finding change set. Its `CQ-001` label in the audit is a mislabel.

The audit's block-16 row states *"CQ-001 is done"* **and** that `apps/ads/services/edit_ad.py`
does not exist. Both cannot be true. The shipped `10-QLT-###` stream resolves it:

| `CQ` | Status | Evidence |
|---|---|---|
| `CQ-008` — split `submit_ad`'s orchestration into `services/` | **SHIPPED** | `apps/ads/services/submission.py` exists and is described by its own test module as *"Tests for the `submit_ad` shared submission service (QLT-001 Stage 1)"*. `db01a73f` then made `ad_edit`'s text-edit **delegate** to it |
| `CQ-009` — an input DTO at the ad-edit boundary | **SHIPPED** | `apps/ads/services/submission.py` → `class AdEditInput(BaseInputModel)`, docstring *"DTO validating ad-edit POST data before any ORM write (QLT-004)"*; the edit view's validation call carries the in-source marker *"Validate POST data via DTO before any ad.save() call (QLT-004)"*; `apps/ads/tests/test_submission.py` pins `extra=forbid` |
| `CQ-001` — extract `ad_edit` into `apps/ads/services/edit_ad.py` | **NOT SHIPPED** | The module does not exist. `ad_edit` is still a view function |

**So the audit's "CQ-001 is done" is a mislabel for `CQ-008` + `CQ-009`.** The correct reading
is that **`CQ-001` alone survives**. This is good news for scope and bad news for risk:

- **Scope shrinks** from three coupled findings to one single-symbol extraction.
- **Risk does not shrink.** The audit's R0 finding stands in full: `ad_edit` performs its
  ownership assertion **outside** the `transaction.atomic()` block, on the *unlocked* instance,
  whereas sibling `ad_archive` and `ad_reactivate` assert ownership **inside** the locked block.
  That is precisely the hole the extraction exists to close, which is why it cannot be
  reordered ahead of phase 15's `AUTHZ-007`.
- One clause of `CQ-009` is **unverified** and is explicitly *not* claimed as shipped: whether
  `AdEditInput`'s `title` / `description` carry `min_length=1`. `B-13`'s Auditor pre-step
  settles it; if unapplied, that clause joins `B-13` (it is one field declaration, not a new
  finding).

---

## 2. Vocabulary ruling — `Q11`

> **This section is a recommendation to the coordinator, not a decision.** It is `Q11`, the
> question the source plan routed to the coordinator and never resolved. The Implementor is
> **forbidden** from choosing a scheme. Every task YAML in §3 carries
> `pending-ratification: Q11` and cites its finding as `10-CQ-0NN` **provisionally**, on the
> explicit assumption that this plan's recommendation is ratified. If the coordinator picks a
> different scheme, only the commit-message token changes — **no code, no test, no file in §3
> is affected.**

### 2.1 The facts

```
$ git log --all | Select-String "10-CQ-"     →  0 matches
$ git log --all | Select-String "10-QLT-"    →  18 matches
```

All 18 shipped `10-QLT-###` commits, with the ones that touch this plan's blocks marked:

| Commit | Subject | Tag | Touches |
|---|---|---|---|
| `39d42de4` | extract `normalize_price_to_eur` shared utility | `10-QLT-001` | phase 05 territory |
| `b9b16af3` | delegate price normalization to shared utility | `10-QLT-001` | — |
| `97b0ec02` | add price-normalization parity tests | `10-QLT-001` | — |
| `7f3f40f6` | remove dead currency coercion in `submit_ad` | `10-QLT-001` | **`CQ-008` subject** |
| `3eab60d8` | add `ConsentVersion` StrEnum | `10-QLT-002` | **`apps/core/enums.py`** |
| `4e26669a` | replace raw `consent_version` `'1.0'` with the enum | `10-QLT-002` | **`B-5`'s file** |
| `176dd0bf` | replace bare `'ru'` defaults with `LanguageLocale.RUSSIAN` | `10-QLT-002` | **`B-2` — partial** |
| `6a9da6b7` | project `CurrencyCode` enum in keyboard callbacks | `10-QLT-003` | — |
| `b155db59` | split entry/submit handlers + update patches | `10-QLT-003` | **`B-13`'s bot half** |
| `6025f594` | split `process_photos` into photos module | `10-QLT-003` | — |
| `54ead6e5` | split `ad_create` handler groups B11–B14 | `10-QLT-003` | — |
| `75313716` | split `ad_create` formatters into preview module | `10-QLT-003` | — |
| `db01a73f` | delegate `ad_edit` text-edit to `submit_ad` | `10-QLT-004` | **`B-13` — `CQ-008`/`CQ-009`** |
| `f09512b5` | relocate `annotate_favorites` to service layer | `10-QLT-005` | **precedent for `B-8`** |
| `9e11ebad` | split `ad_data.py` into 5 submodules | `10-QLT-006` | — |
| `bf6f5675` | update stale `ad_data.py` references | `10-QLT-006` | — |
| `381fa402` | add `SubmittedPhoto` Pydantic model at photo boundary | `10-QLT-008` | `apps/media/schemas.py` |
| `5c374a76` | add None-guard in immediate-alerts test | `10-QLT-009` | — |

Four structural facts fall out of that table, and they are what the ruling has to weigh:

1. **`QLT-###` is not a unique work-item ID.** `10-QLT-003` labels **five** unrelated commits,
   `10-QLT-001` and `10-QLT-002` three each, `10-QLT-006` two. It is a *thread* tag, not an item.
2. **`QLT-###` is already untraceable in one direction.** `apps/ads/services/images.py` and
   `apps/ads/tests/test_ad_image_service.py` carry the in-source marker **`QLT-012`**, and **no
   commit in the repository is tagged `10-QLT-012`.** A grep for `QLT-012` in source returns a
   reference with no history behind it.
3. **`10-QLT-###` is not the findings vocabulary.** Its commits are *refactors* — split
   modules, extract utilities, project enums. They map loosely, if at all, onto `CQ-0NN`
   (`10-QLT-004`'s `AdEditInput` is `CQ-009`; `10-QLT-005`'s `annotate_favorites` relocation is
   `CQ-002`'s *pattern* but not its subject). **It is a parallel work stream on the same files,
   not a second naming of the same work items.**
4. **`10-CQ-###` maps 1:1 onto a surviving artifact.** The validated report
   `.ai/audit/99-validation/10-code-quality-validated-findings.md` numbers its findings
   `CQ-001` … `CQ-019` and is the record of what was filed, at what severity, with what
   evidence. A `10-CQ-006` citation in a commit body resolves to a section of a file that still
   exists.

### 2.2 The options, with the risk of each

| | Scheme | Gains | Risks / costs |
|---|---|---|---|
| **A** | **`10-CQ-0NN` for every new commit** (recommended) | Traces 1:1 to the validated report; the token is unique per work item; `git log --grep "10-CQ-"` returns exactly this plan's work and nothing else | For ~12 new commits the repo carries two schemes in history. A reader must be told which stream to grep. Mitigated by the mandatory `xref:` body line (§2.3) |
| **B** | **Continue `10-QLT-###`** | Zero new vocabulary; matches the 18 already shipped | `QLT-###` is **not unique** (fact 1) and is **already dangling** in one direction (fact 2), so the scheme is being extended in a state the coordinator has not accepted. Adopting it *ratifies* ID reuse as the convention. It also loses the report link entirely — `10-QLT-010` would name nothing a reader can look up |
| **C** | **Both in the subject line** — `refactor(ads): … (10-CQ-006 / 10-QLT)` | Maximum discoverability from either grep | Two IDs per commit, forever. The `QLT-` half has no item-level meaning (fact 1), so it is noise that looks like information. Diffs badly in `git log --oneline` |
| **D** | **Cite the plan, not a phase token** — `(plan 24 · CQ-006)` | No second vocabulary in the repo at all; the citation points at the executable plan | Not machine-greppable by ID alone, and it makes the **commit** the dependent artefact — a reader in six months cannot find the commit from the finding without also finding plan 24 |

### 2.3 Recommendation, and the one mitigation that makes it safe

**Recommend option A**, with a mandatory second body line on any commit that overlaps shipped
`QLT` work:

```
refactor(core): key the FTS locale maps on LanguageLocale members (10-CQ-006)

xf: 176dd0bf (10-QLT-002) replaced bare call-site defaults only; the two dict
    properties on LanguageLocale still key on bare "ru"/"bs"/"en".
```

Blocks whose overlap is known and that **must** carry the `xref` line: `B-2`
(`176dd0bf`, `3eab60d8`, `4e26669a`), `B-5` (`4e26669a`), `B-9` (`f09512b5` as the shipped
precedent for the same pattern), `B-13` (`db01a73f`, `b155db59`, `7f3f40f6`).

**Two things this plan does not do, under any option:**

- It writes **no new in-source `QLT-` or `CQ-` marker**. A provenance comment inside a
  production file is the pattern the source plan's §6.3 and phase 03 BLOCK 11's reservation
  both exist to prevent.
- It **sweeps none**. The in-source `QLT-###` sweep in `ad_create/*`, `ad_data/*`,
  `ads/services/{submission,favorites,images}.py`, `media/schemas.py` and four test modules is
  **phase 03 BLOCK 11's**, whose rule forbids other phases from starting it.

**Decision owner: coordinator.** Until it rules, `Q11` is open and the provisional citation in
every task YAML stands.

---

## 3. Execution blocks

**One Implementor, strictly sequential, one commit per block.** §7 states the order and the
edges; the numbering below **is** that order. Each block is written so that it can be handed
to an Implementor with no further reading.

**Standing rules for every block** (source plan §1 and §6.3, carried):

- Tests are **Docker-only**. The gate is `.\Makefile.ps1 test` (fast, skips the nightly `seed`
  suite). **`uv run pytest` on the host always fails** — there is no PostgreSQL on
  `localhost:5432`. Never run it, never quote it as evidence.
- Lint `uv run ruff check <the files this block edits>`; typecheck
  `uv run basedpyright <the files this block edits>`. **`[tool.ruff] fix = false`** is set in
  this repo — `ruff check --fix` is permitted **only** over the files the current block edits,
  and `ruff format` is **not** the project convention.
- `makemessages` / `compilemessages` do **not** work via `make` on Windows 11 + Docker Desktop.
  Use the `--no-deps --entrypoint ""` one-liner recorded in `.kilo/rules/commands.md`. Only
  `B-4` and `B-8` have an i18n obligation.
- **No line number is a task target.** Every target in every YAML below is a module, class,
  function, enum member, `Final` constant, or test node ID.
- **Never** `git add -A`, `git add .`, `git reset`, `git checkout`, `git restore`, `git stash`,
  `--amend`, force-push, or a commit without an explicit instruction. **Never** edit
  `.ai/audit/**`, another phase's plan, or `src/backend/conftest.py`.
- **Never delete a source-inspection test to make a block green.** Re-point it, in the same
  commit, and say so in the commit body.
- **No new architectural layer, base class, registry, plugin mechanism or service locator.**
  The entire net-new surface of this plan is: **2 empty `__init__.py`-class module markers, 1
  new service module, 1 new Pydantic input DTO, 1 extracted context builder, and 1
  extraction into a service module.** Nothing else.

### Execution order at a glance

```
  B-1 packaging ──────────────────────────────────────────────► B-13 (blocked)
  B-2 locales ──► B-7 saved-search ──┐
              └──► B-12 fuzzy ───────┤ (also needs B-11)
  B-3 admin URLs ──► B-4 reject reason
  B-5 consent ──► B-6 dead code ──► B-7 saved-search, B-10 suppressions
  B-8 alerts prompt ──► B-9 alerts service
  B-11 listings context ──► B-12 fuzzy
  B-13 ad_edit extraction  (last; blocked on phase 03 BLOCK 5 + AUTHZ-007)
```

---

### B-1 — Packaging and export hygiene

| | |
|---|---|
| **Findings owned** | `CQ-017.1`, `CQ-017.2` (LOW, `SPEC-DEVIATION`); the surviving `CQ-007`/`CQ-019` residue (the three misnamed per-function docstrings) |
| **Class** | **mechanical** — one new empty module, one list entry, three docstring corrections |
| **Depends on** | nothing in-plan |
| **Blocks** | `B-13` (the `ads/services/` package must be a real package before a module is added to it) |
| **Priority** | P1 — first in the run; smallest diff; proves the serial contract |
| **Risk level** | **LOW** |
| **Required agents** | **Auditor** (pre-step only). No Researcher, no Validator. Fast gate must be green |

**Why this is not the source plan's BLOCK 2.** Two of its three premises rotted (audit R3).
The `core/utils/cache.py` **module** docstring was rewritten by `09-API-001`, `09-API-002` and
`08-SRCH-007` and now correctly declares the cache-failure and version-key contracts — that
half is **moot**. The "12 one-line wrappers" figure is now **15 wrappers** (five
getter/setter/invalidate triads: criteria, site config, bot username, support contacts, anon
language) plus **three new shared primitives** (`cache_get_or_none`, `bump_rate_limit_window`,
`bump_version_key`). Trimming boilerplate off 15 trivial one-line wrappers is **declined** with
rationale (§8), because their keys and TTLs are already single-sourced as `Final` default
arguments and the module-level docstring a reader actually consults is now correct.

**What survives is the two real defects, plus the three docstrings that are not a style
preference but an inaccuracy.**

**File surface (semantic units)**

| File | Symbol / target | Change |
|---|---|---|
| `src/backend/apps/ads/services/__init__.py` | **the module itself (does not exist)** | Create it, empty (or a single-line package docstring matching the sibling `services/__init__.py` files in the repo). `git ls-files` shows six modules under `ads/services/` and no `__init__.py` — the only implicit namespace package in the repo |
| `src/telegram_bot/services/ad_data/orm.py` | the module-level `__all__` list; the private function `_get_ad_status` | Remove the `"_get_ad_status"` **entry from `__all__` only**. The function **stays** — it has real importers (see constraint 3) |
| `src/backend/apps/core/utils/cache.py` | the **three per-function docstrings that still name `ModerationCriteria`** | Correct each to name what the function actually does. The Auditor pre-step **names the three functions**; this plan does not guess them |

**Binding constraints**

1. **`_get_ad_status` is live and must not be deleted, renamed, or made private-again.** It is
   imported by `telegram_bot/handlers/ad_create/entry.py` and re-exported from
   `telegram_bot/services/ad_data/__init__.py`. The source plan's framing ("an unused private
   in `__all__`") was **wrong at the anchor and is wrong now**; only the export-list entry is
   dead. Removing the entry is safe **only** because nothing does a wildcard import of that
   module — the Auditor pre-step proves that.
2. **The new `__init__.py` must not re-export anything.** An `__init__.py` that re-exports the
   six `ads/services/` modules creates an import cycle hazard of the kind
   `apps/users/services/account_state.py` already documents, and plan 19's `19-Q1` analysis
   turns on the same hazard.
3. **Only the three docstrings that misname their subject are touched.** No other docstring in
   `cache.py` changes. No wrapper is renamed, merged, or given a different return type.
4. **Re-read `cache.py` immediately before editing.** Phase 09 (`09-VAL-008`) and phase 08
   (`08-SRCH-007`) both wrote to it after the source plan's anchor.

**Implementor task**

```yaml
id: task_24_b01_packaging_and_export_hygiene
title: "Add the ads services package marker and drop the private name from orm __all__ (10-CQ-017)"
priority: medium
depends_on: []
source_reference: ".ai/plans/24-code-quality-remediation-execution.md"
source_section: "B-1 - Packaging and export hygiene"
source_blocks: ["B-1", "orig BLOCK 2 (CQ-017.1/.2, CQ-007 residue)"]
description: >
  Three defects, all mechanical. (1) src/backend/apps/ads/services/ has no __init__.py and is
  the repo's only implicit namespace package; a later block in this plan adds a service module
  to it. (2) telegram_bot/services/ad_data/orm.py exports the private name "_get_ad_status"
  in __all__ -- a naming contradiction -- but the function itself is live, imported by the bot's
  ad_create entry handler and re-exported from the package __init__, so only the __all__ entry
  is removed. (3) Three per-function docstrings in apps/core/utils/cache.py still describe their
  functions using the retired "ModerationCriteria" name; the module docstring itself was already
  rewritten by 09-API-001/002 and 08-SRCH-007 and must not be touched.
goals:
  - "make apps/ads/services/ a real package with an empty __init__.py"
  - "remove the private _get_ad_status entry from orm.py's __all__ while keeping the function and every importer working"
  - "correct only the three per-function cache.py docstrings that misname their subject"
  - "change no behaviour, no cache key, no TTL, no signature"
files:
  - path: "src/backend/apps/ads/services/__init__.py"
    targets:
      - type: module
        name: "__init__"          # NEW, empty or one-line package docstring
  - path: "src/telegram_bot/services/ad_data/orm.py"
    targets:
      - type: module
        name: orm
      - type: assignment
        name: "__all__"
    semantic_anchors:
      replace_value:
        type: list_entry
        value: "_get_ad_status"
  - path: "src/backend/apps/core/utils/cache.py"
    targets:
      - type: module
        name: cache
      # the three docstrings are named by the Auditor pre-step, not by this plan
changes:
  - action: add_code
    description: >
      Create src/backend/apps/ads/services/__init__.py. Empty, or a single-line docstring
      matching the sibling services/__init__.py files. It must re-export nothing.
  - action: modify_code
    description: >
      Remove only the "_get_ad_status" entry from orm.py's __all__. Do not touch the function,
      its body, its decorators, or any importer in telegram_bot/.
  - action: modify_code
    description: >
      In apps/core/utils/cache.py, correct the docstring of each function whose docstring still
      names "ModerationCriteria" so that it describes the cache that function actually covers.
      Record the three function names in the commit body.
acceptance_criteria:
  - "apps/ads/services/__init__.py exists, contains no import and no re-export"
  - "'_get_ad_status' no longer appears in orm.py's __all__, and the function and its bot-side importers are unchanged and still resolve"
  - "no wildcard import of telegram_bot.services.ad_data.orm exists anywhere (Auditor pre-step, quoted in the commit body)"
  - "cache.py's MODULE docstring is byte-unchanged"
  - "cache.py's function set, signatures, return types, keys and TTLs are unchanged"
  - "uv run ruff check src/backend/apps/ads/services/ src/telegram_bot/services/ad_data/ src/backend/apps/core/utils/cache.py is clean"
  - ".\\Makefile.ps1 test is green"
tests_to_run:
  - "src/telegram_bot/tests/test_ad_data_locale.py"
  - "src/backend/apps/categories/tests/"   # cache consumers
```

**Tests required** — none new. The block adds a package marker, removes a dead export entry,
and corrects three docstrings; there is no behaviour to pin. The only permitted new artefact is
the commit body's record of the three docstring targets. **A test asserting `__all__`'s
contents is forbidden** (source plan §6.3 item 14: no test may assert the mere presence of a
symbol, a literal private name, or an introspected count).

**Risk and rollback**

- *Implementation risk:* the `__all__` removal breaks a wildcard importer that the source plan
  did not know about. Mitigation: constraint 1 + the Auditor pre-step. Detection: the fast gate.
- *Regression risk:* an over-eager `__init__.py` re-export cycle. Mitigation: constraint 2.
- *Rollout risk:* none — no response, no cache key, no query changes.
- *Cross-phase:* `cache.py` — phase 09 `09-VAL-008` and phase 08 `08-SRCH-007`. `ads/services/`
  is now also phase 10 `B-13`'s target package.
- *Rollback:* straight revert. Zero data, zero schema, zero user-visible effect.

---

### B-2 — Locale literals, in place

| | |
|---|---|
| **Findings owned** | `CQ-006` (MEDIUM) |
| **Class** | **mechanical** — literal substitution at the call sites; one gated style decision on the two properties |
| **Depends on** | nothing in-plan |
| **Blocks** | `B-7` (`search/views/save_search.py` carries a bare locale literal) and `B-12` (the fuzzy/name-list neighbourhood) |
| **Priority** | P1 |
| **Risk level** | LOW–MEDIUM — `apps/core/enums.py` is the most-churned shared file in the repo |
| **Required agents** | **Auditor** (pre-step: re-enumerate the surviving bare literals), **Planner** (owns `Q9`). No Researcher, no Validator |

**Decision required before implementation — `Q9`: how do `LanguageLocale.fts_config` and
`.fts_vector_field` stop being raw dicts keyed on bare `"ru"` / `"bs"` / `"en"`?**

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | Replace the dict literals with `Final` class-level mappings **keyed by the enum members** (`{LanguageLocale.RUSSIAN: "russian", …}`), read via `LanguageLocale.X.value` at the consumer | **Gains:** one representation; `KeyError`-free for a valid member, which is strictly better than a silent `KeyError` today; the pairing `test_search_triggers.py` pins is unchanged. **Costs:** the mappings become part of the enum's public surface, and adding a locale forces a decision about both maps |
| **(b)** | Turn both properties into `match`/`dict`-returning classmethods that switch on the member | **Gains:** exhaustiveness is visible; an unmapped member fails loudly at the property call. **Costs:** two more methods on an enum that already exposes `values()`, `from_code()`, `fts_config` and `fts_vector_field`; more surface for the same pairing |
| **(c)** | Leave the two properties alone; fix only the false module docstring | **Gains:** smallest diff. **Costs:** **does not fix the finding.** These two dicts *are* the bare-keyed locale literals the finding is about; `176dd0bf (10-QLT-002)` fixed call-site defaults and left them. Option (c) ships the docstring half of `Q-006` and none of its substance |

**The Implementor may not choose.** `Q9` is a precedent question: it decides how *every future
enum* in this repo expresses a mapping, and a precedent set silently by an implementor is a
precedent nobody reviewed.

**File surface (semantic units)**

| File | Symbol / target | Change |
|---|---|---|
| `src/backend/apps/core/enums.py` | the **module docstring**'s invariant sentence | It currently asserts *"No inline string literals for constants anywhere in the codebase"* — **false**, and `B-2`'s own two dicts are the counter-example. Restate it as the invariant this block actually establishes |
| `src/backend/apps/core/enums.py` | `class LanguageLocale`, properties `fts_config` and `fts_vector_field` | The two raw dict literals keyed on bare `"ru"` / `"bs"` / `"en"` become enum-keyed per `Q9`. **The pairings themselves must not change** — `test_search_triggers.py` pins them |
| `src/backend/apps/core/enums.py` | `class LanguageLocale` members `RUSSIAN`, `BOSNIAN`, `ENGLISH` | Read-only. `LanguageLocale.values()` and `.from_code()` are read-only |
| `src/backend/apps/core/enums.py` | `class AdvisoryLockId`, member `REPAIR_BOT_USERNAME` | **READ-ONLY — do not touch, do not renumber, do not add.** The source plan de-scoped the enum reorder; that decision stands |
| bare `"ru"` / `"bs"` / `"en"` at remaining call sites | **Auditor-enumerated set** | `176dd0bf (10-QLT-002)` already replaced the call-site *defaults*. The Auditor's pre-step re-enumerates what is left; the block fixes exactly that set and nothing wider. `telegram_bot/services/ad_data/translation.py` is a known locale-literal site |

**Binding constraints**

1. **The FTS pairings are immutable.** `fts_config` must keep mapping each locale to the same
   Postgres text-search configuration name, and `fts_vector_field` to the same generated-column
   name. `test_search_triggers.py` is the detector. A "cleanup" that changes a value is a
   production incident, not a refactor.
2. **No `apps/core/services/locales.py`.** `LanguageLocale` already exposes `values()`,
   `from_code()` and both properties. A wrapper module is a hop with no consumer — declined,
   rationale in §8.
3. **No `AdvisoryLockId` change of any kind.** No member added, none renumbered, no reorder.
4. **Re-read `apps/core/enums.py` immediately before editing.** Seven post-anchor commits
   touched it, plus `3eab60d8`/`4e26669a` which added `ConsentVersion` under `10-QLT-002`.
   If the file has changed since this plan was written, the block stops and reports.
5. **Do not touch `telegram_bot/handlers/lifecycle.py`'s per-locale `Уведомления` literal.** It
   is a **documented EC-3 decision against gettext**, not a locale-literal defect. It is not in
   this block's scope and "fixing" it would reverse a recorded decision.

**Implementor task**

```yaml
id: task_24_b02_locale_literals
title: "Key the FTS locale maps on LanguageLocale members and restate the enums invariant (10-CQ-006)"
priority: high
depends_on: []
source_reference: ".ai/plans/24-code-quality-remediation-execution.md"
source_section: "B-2 - Locale literals, in place"
source_blocks: ["B-2", "orig BLOCK 3 (CQ-006)"]
description: >
  apps/core/enums.py claims in its module docstring that there are no inline string literals for
  constants anywhere in the codebase. That invariant is false, and LanguageLocale itself is a
  counter-example: the properties fts_config and fts_vector_field return raw dict literals keyed
  on bare "ru" / "bs" / "en". Commit 176dd0bf (10-QLT-002) already replaced bare locale DEFAULTS
  at the call sites; it did not touch these two dicts. Fix both properties per the recorded Q9
  option, restate the false invariant as the one this block actually establishes, and substitute
  LanguageLocale members for the bare literals the Auditor pre-step enumerates.
goals:
  - "no bare \"ru\" / \"bs\" / \"en\" literal remains in LanguageLocale's own mappings"
  - "the FTS configuration-name and vector-field-name pairings are byte-identical to today"
  - "the enums module docstring asserts only an invariant this repository actually satisfies"
  - "allocate, renumber or reorder no AdvisoryLockId member"
files:
  - path: "src/backend/apps/core/enums.py"
    targets:
      - type: class
        name: LanguageLocale
      - type: method
        name: fts_config
      - type: method
        name: fts_vector_field
      - type: module
        name: enums          # module docstring only
    semantic_anchors:
      insert_after:
        type: class
        value: LanguageLocale
  # call sites: the Auditor pre-step names the exact set; no line numbers
changes:
  - action: modify_code
    description: >
      Replace the two raw dict literals inside LanguageLocale.fts_config and
      LanguageLocale.fts_vector_field with the Q9-recorded form keyed on the enum members. The
      values ("russian"/"simple"/"english" and the search_vector_* column names) must be
      character-identical to today.
  - action: modify_code
    description: >
      Rewrite the module docstring's invariant sentence so it describes the rule this repository
      actually follows. Do not weaken it into vagueness.
  - action: modify_code
    description: >
      At each call site the Auditor pre-step enumerates, replace the bare locale literal with the
      LanguageLocale member. Record the enumerated set in the commit body.
acceptance_criteria:
  - "LanguageLocale.fts_config and .fts_vector_field contain no bare \"ru\"/\"bs\"/\"en\" key"
  - "test_search_triggers.py is green UNCHANGED -- the pairings are unaltered"
  - "LanguageLocale.values() and .from_code() are unchanged"
  - "AdvisoryLockId is byte-unchanged, including its member order and REPAIR_BOT_USERNAME's value"
  - "telegram_bot/handlers/lifecycle.py is byte-unchanged"
  - "the commit body lists the Q9 option, the call-site set, and an xref line for 176dd0bf / 3eab60d8 / 4e26669a"
  - "uv run ruff check and uv run basedpyright are clean on every edited file"
  - ".\\Makefile.ps1 test is green"
tests_to_run:
  - "src/backend/apps/search/tests/test_search_triggers.py"
  - "src/telegram_bot/tests/test_ad_data_locale.py"
  - "src/telegram_bot/tests/test_callbacks.py"
```

**Tests required** — none new. The pairings are pinned by `test_search_triggers.py` and the
locale enums by `test_ad_data_locale.py`; both are expected green **unchanged**. The false
docstring has no test and must not get one (a test asserting a docstring is forbidden by
source plan §6.3 item 14).

**Risk and rollback**

- *Implementation risk:* a pairing value is altered by accident. Mitigation: constraint 1;
  detection is `test_search_triggers.py` going red in a way that is unambiguous.
- *Regression risk:* the rewording of the module docstring becomes an unverifiable promise in a
  file five other phases hold. Mitigation: constraint 4 — re-read before edit, stop if moved.
- *Corpus risk:* the block grows from "two dicts plus a docstring" into a tree-wide locale
  sweep. Mitigation: the pre-step enumerates, the block fixes exactly that set, and the commit
  body publishes the set. A growth beyond it is a new finding, not a bigger block.
- *Rollback:* straight revert. A wrong pairing is a revert, not a hotfix, because search
  behaviour would be silently wrong rather than broken.

---

### B-3 — Reverse the hardcoded admin URLs

| | |
|---|---|
| **Findings owned** | `CQ-018`, URL half only (LOW) |
| **Class** | **mechanical** — four string literals become `reverse()` calls. No behaviour change |
| **Depends on** | nothing in-plan. **External, hard: plan 19 `B-2` must have landed** (it edits the same `review.py` view that owns one of the three redirects) |
| **Blocks** | `B-4` (both write `apps/moderation/views/review.py`; structural and behavioural work goes last) |
| **Priority** | P2 |
| **Risk level** | **LOW** execution risk / **MEDIUM** coordination risk |
| **Required agents** | **Auditor** (pre-step: confirm the admin URL names resolve). No Researcher, no Validator |

**Why this block is not the source plan's BLOCK 5.** That block carried `CQ-005` (expose
`AdStatus` to templates) **plus** `CQ-018`'s URL half. **The `CQ-005` half is moot** — there is
no `AdStatus.` token anywhere under `templates/**`, so there is nothing to remove — and with
it dies gate `Q10` (context processor versus per-view key), which existed only to serve it.
**No context key is added by this plan.**

**This Planner found one live URL site the audit did not list:** the `href` on the admin-ad
changelist link inside `src/backend/templates/analytics/moderation_dashboard.html`. It is the
same class of defect (a hardcoded admin URL that breaks if the model's admin registration
changes) and it is the only one of the four that lives in a template. It is **in** scope, and it
is why `uv run djlint` appears in this block's commands.

**File surface (semantic units)**

| File | Symbol / target | Change |
|---|---|---|
| `src/backend/apps/moderation/views/review.py` | the success `redirect(...)` returned by **`moderation_review`** | `redirect(f"/admin/ads/ad/{ad_id}/change/")` → `redirect(reverse("admin:ads_ad_change", args=[ad_id]))` |
| `src/backend/apps/moderation/views/review.py` | the success `redirect(...)` returned by **`reject_ad`** | → `reverse("admin:ads_ad_changelist")` plus the `status__exact=on_moderation` query string |
| `src/backend/apps/moderation/views/review.py` | the success `redirect(...)` returned by **`ban_user`** | Same as `reject_ad`. **This is plan 19 `B-2`'s view — see constraint 1** |
| `src/backend/templates/analytics/moderation_dashboard.html` | the anchor whose `href` targets the admin ad changelist | → `{% url 'admin:ads_ad_changelist' %}?status__exact=on_moderation` |
| `src/backend/apps/moderation/views/review.py` | `approve_ad` | **READ-ONLY reference.** The Auditor pre-step records how it reports its outcome, so the three rewrites match the module's existing idiom rather than inventing one |

**Binding constraints**

1. **Plan 19 `B-2` must have landed first.** `ban_user` is plan 19's surface (`19-Q4` RESOLVED:
   it surfaces a refusal through `django.contrib.messages` against the admin changelist). If
   this block lands first, plan 19's `B-2` reviews its diff against a `redirect` target this
   block has just changed, and one function's diff is split across two plans. **This is an
   ordering constraint the coordinator sequences, not something the Implementor can satisfy.**
   Confirm with `git log` that `ban_user`'s current body is the one plan 19 left behind.
2. **The redirect target and status code must not change.** `moderation_review` keeps
   redirecting to the ad's admin change page; `reject_ad` and `ban_user` keep redirecting to the
   admin ad changelist filtered to `status__exact=on_moderation`. This block reverses four URL
   strings and nothing else.
3. **`moderation_review` is part of a GET confirmation-page flow ruled outside this plan.** A
   sibling ruling holds that GET renders a 200 confirmation page and the action runs only on
   POST. **This plan does not re-decide that ruling**, and `B-3` does not change the GET
   response — only how the redirect URL is produced.
4. **No `AdStatus`, no `CategoryRejectReason`, no context key.** The template change touches
   the `href` and nothing else in that file.
5. **The admin URL names must be confirmed, not assumed.** `reverse("admin:ads_ad_change")` and
   `reverse("admin:ads_ad_changelist")` are the names the source plan recorded at `6413df5`;
   the Auditor pre-step proves both resolve **at HEAD**, and quotes the proof in the commit body.
   If either does not resolve, **stop and report** — do not substitute a literal.

**Implementor task**

```yaml
id: task_24_b03_reverse_admin_urls
title: "Replace the hardcoded /admin/ads/ad URLs with reverse() lookups (10-CQ-018)"
priority: medium
depends_on: []
source_reference: ".ai/plans/24-code-quality-remediation-execution.md"
source_section: "B-3 - Reverse the hardcoded admin URLs"
source_blocks: ["B-3", "orig BLOCK 5 URL half"]
description: >
  Three view redirects and one template link build their target by string concatenation into
  /admin/ads/ad/... . They break silently if Ad's admin registration changes. Replace them with
  reverse() / {% url %}. Three of the four sites are in apps/moderation/views/review.py
  (moderation_review, reject_ad, ban_user) and one is the admin-ad-changelist href in
  templates/analytics/moderation_dashboard.html. The redirect target, the status code and the
  status__exact=on_moderation query string are unchanged by contract.
goals:
  - "no hardcoded /admin/ads/ad URL remains in review.py or moderation_dashboard.html"
  - "every redirect target and status code is byte-for-byte equivalent in behaviour"
  - "add no context key and expose no enum to any template"
files:
  - path: "src/backend/apps/moderation/views/review.py"
    targets:
      - type: function
        name: moderation_review
      - type: function
        name: reject_ad
      - type: function
        name: ban_user
      - type: function
        name: approve_ad            # read-only reference
    semantic_anchors:
      replace_in_body:
        type: string_literal
        value: "/admin/ads/ad/?status__exact=on_moderation"
  - path: "src/backend/templates/analytics/moderation_dashboard.html"
    targets:
      - type: template_attribute
        name: href       # the anchor targeting the admin ad changelist
    semantic_anchors:
      replace_value:
        type: attribute_value
        value: "/admin/ads/ad/?status__exact=on_moderation"
changes:
  - action: modify_code
    description: >
      In moderation_review, reject_ad and ban_user, replace the hardcoded admin URL with
      reverse(). Preserve the status__exact=on_moderation query string on the changelist
      redirects. Import reverse at module scope if it is not already imported.
  - action: modify_code
    description: >
      In moderation_dashboard.html, replace the href with {% url 'admin:ads_ad_changelist' %}
      plus the same query string. Change no other attribute, text or block in that template.
acceptance_criteria:
  - "grep for a hardcoded /admin/ads/ad returns nothing in review.py and moderation_dashboard.html"
  - "moderation_review, reject_ad and ban_user return the same redirect target and status code as before"
  - "the four existing reject/ban moderation view tests are green UNCHANGED"
  - "reverse('admin:ads_ad_change') and reverse('admin:ads_ad_changelist') both resolve (Auditor pre-step, quoted in the commit body)"
  - "plan 19 B-2's ban_user body is the one this block edited (confirmed with git log, quoted in the commit body)"
  - "no context key, no enum exposure and no AdStatus token is introduced anywhere"
  - "uv run ruff check, uv run basedpyright and uv run djlint src/backend/templates/ are clean"
  - ".\\Makefile.ps1 test is green"
tests_to_run:
  - "src/backend/apps/moderation/tests/test_moderation_views.py"
  - "src/backend/apps/analytics/tests/"      # the dashboard view's suite
```

**Tests required** — none new. All four sites change *how a URL is built*, not *what it is*.
The moderation view suite already asserts the redirect targets. **A test asserting a resolved
URL string is permitted here** — unlike the other blocks — because the URL **is** the observable
contract of this block, and the existing suite already pins it. `TestModerationReviewLocking` is
expected green unmodified: it inspects locking shape, not redirect construction.

**Risk and rollback**

- *Implementation risk:* `reverse()` raises `NoReverseMatch` at request time if a name is wrong,
  turning a working page into a 500. Mitigation: constraint 5 — the Auditor pre-step resolves
  both names **before** the edit, and stops the block if either fails.
- *Coordination risk (the real one):* colliding with plan 19 `B-2` on `ban_user`. Mitigation:
  constraint 1; the coordinator sequences it.
- *Regression risk:* a template edit that reformats or re-indents the file. Mitigation:
  constraint 4 — the `href` only; `djlint` is a check, not a formatter, here.
- *Rollback:* straight revert.

---

### B-4 — Make the reject-reason vocabulary a real boundary

| | |
|---|---|
| **Findings owned** | `CQ-003` (MEDIUM) — **the source plan's BLOCK 7, minus its `CQ-018` half** |
| **Class** | **behavioural** — changes an observable response and writes a new user-visible string |
| **Depends on** | `B-3` (same file: `apps/moderation/views/review.py`. Mechanical first, structural/behavioural last) |
| **Blocks** | nothing in-plan |
| **Priority** | P3 — deliberately late in the moderation pair, and after every other `review.py` writer in this plan |
| **Risk level** | **MEDIUM** |
| **Required agents** | **Auditor** (pre-step: verify the defect is still live), **Researcher** (owns the mechanism gate `G-4a`), **Planner** (owns the context-builder shape), **Validator** (mandatory — new response shape, new i18n string, four existing tests must stay green unmodified) |

> **Conditional block.** If the Auditor pre-step finds that `reject_ad` no longer accepts an
> arbitrary `reason_category`, the block is **cancelled and recorded as cancelled** — no shrunken
> version, no commit. As of this Planner's own reading of the tree it **is** live (§1.3 item 1),
> so the pre-step is a confirmation, not a search.

**Already decided — carry this as a constraint, not a question.** `Q2` was **RESOLVED
2026-10-03 by the Product Owner**: on an invalid `reason_category`, **re-render the review page
with an error and preserve the moderator's typed input.** The 400 reading is **DECLINED**.
**Nothing is coerced to empty. No arbitrary client string may reach `ModeratorActionLog.reason`.
No audit row is written for a rejected request.** A new user-visible error string therefore
ships, and per project rule 16 its `ru` and `bs` `msgstr` must both be non-empty.

**Decision required before implementation — `G-4a` (new; this plan's own): how does `reject_ad`
re-render the review page without duplicating `moderation_review`'s context?**

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | Extract `moderation_review`'s context construction into a module-private helper in `review.py`; `moderation_review` renders it and `reject_ad` re-renders it on the invalid path, adding the error and the preserved `reason_category` / `reason_text` | **Gains:** one context contract, which is exactly the class of duplication `B-11` removes on the listings side — the two blocks then agree on a pattern. **Costs:** a structural change to the most contested file in the plan set; `TestModerationReviewLocking` inspects this module and must survive it; the template must render the preserved values and the error, so it gains markup and two translated strings |
| **(b)** | `reject_ad` posts a `django.contrib.messages` error and redirects to `moderation_review`, carrying the moderator's typed text through the query string or the session | **Gains:** no template change, no shared context helper, smallest structural diff; plan 19's `19-D5` established that `messages` genuinely renders on this surface (Django's own admin chrome renders `{% block messages %}`, and no project template overrides it). **Costs:** **it does not satisfy `Q2`'s ruling** — the moderator's typed comment is lost or must be round-tripped through the URL, and a comment in a query string is both ugly and unbounded. Option (b) is admissible **only** if `G-4a` also records how the typed input survives |
| **(c)** | Return a 400 with the error | **DECLINED by the Product Owner.** Listed here only so the Implementor does not "discover" it as a third way. It is not on the table |

**The Implementor may not choose.** `G-4a` is a real mechanism decision with a shipped precedent
on one side (plan 19) and a Product Owner constraint on the other, and it decides whether
`review.html` gains markup.

**File surface (semantic units)**

| File | Symbol / target | Change |
|---|---|---|
| `src/backend/apps/core/enums.py` | `class CategoryRejectReason(StrEnum)` | **READ-ONLY.** Its 8 members and their values are the vocabulary. No member is added, renamed or removed |
| `src/backend/apps/moderation/views/review.py` | **`reject_ad`** | Validate `reason_category` against the enum **before** the reason string is constructed. On an invalid value, take the `Q2` path: re-render with an error, preserve the typed input, **write no audit row**. The decorators `@require_POST` + `@staff_required` stay exactly as they are |
| `src/backend/apps/moderation/views/review.py` | **`moderation_review`** | Depending on `G-4a`: either unchanged (option b) or its context construction extracted to a module-private helper (option a). The Auditor/Researcher pre-step records the current context keys and template name |
| `src/backend/apps/moderation/views/review.py` | the module's admin-URL helpers as they exist after `B-3` | Read-only. `B-3` runs first precisely so this block's diff sits on a settled file |
| `src/backend/templates/admin/moderation/review.html` | the reject modal's `select[name="reason_category"]` and its **8 hardcoded `<option>` literals** | Options: the enum's members become the single source of the option list **if** `G-4a`(a) is chosen and a mechanism exists; plus — under either option — an error notice and, under (a), the preserved `reason_category` / `reason_text` values |
| `src/backend/apps/moderation/services/moderation_log.py` | the audit writer `reject_ad` calls | **READ-ONLY, and it must not be reached** on the invalid path |

**Binding constraints**

1. **Validation happens before the reason string is built.** The check is on the raw POST value
   against `CategoryRejectReason`, at the view boundary. Nothing downstream may receive an
   unvalidated string.
2. **`Q2`'s ruling is binding.** Re-render with an error; preserve the typed input; no
   coercion to empty; no audit row; **not a 400**.
3. **The four existing reject tests post `reason_category="spam_scam"`, a valid member, and
   must stay green UNCHANGED.** This is the block's most important regression detector.
   `test_moderation_views.py::TestModerationReviewLocking` must also survive — it inspects
   locking shape, and the invalid path must not add a `select_for_update` or an `atomic()`.
4. **A column, a lookup table, or a migration for `ModeratorActionLog.reason` is out of scope.**
   The enum's own docstring records that the category is deliberately not a DB column, and
   `docs/02-database/db-schema.md` is the record of that decision. Phase 10 enforces the
   vocabulary at the boundary and changes nothing else.
5. **No generic "enum in template" mechanism.** One enum, one template, one mechanism chosen by
   `G-4a`. A framework serving one consumer is a new abstraction with one user.
6. **Plan 19 collision.** `B-2` may add a refusal notice to the same template. If
   `templates/admin/moderation/review.html` has changed since this plan was written, re-read and
   reconcile before editing; if the two surfaces collide, **stop and report to the coordinator.**
7. **i18n is part of the definition of done.** The new error string needs non-empty `ru` and
   `bs` `msgstr`. `en` may stay empty. Regenerate the catalogues with the Docker one-liner from
   `.kilo/rules/commands.md` — **never** `make makemessages` (broken on Win 11 + Docker
   Desktop). `test_i18n_completeness.py` is the detector.

**Implementor task**

```yaml
id: task_24_b04_reject_reason_boundary
title: "Validate reason_category against CategoryRejectReason at the reject_ad boundary (10-CQ-003)"
priority: high
depends_on: [task_24_b03_reverse_admin_urls]
source_reference: ".ai/plans/24-code-quality-remediation-execution.md"
source_section: "B-4 - Make the reject-reason vocabulary a real boundary"
source_blocks: ["B-4", "orig BLOCK 7 (CQ-003 half only)"]
description: >
  review.reject_ad reads reason_category straight from request.POST with no membership check and
  then interpolates it into the ModeratorActionLog reason string, so any client string reaches
  the audit row. apps/core/enums.py already defines CategoryRejectReason with 8 members, and
  templates/admin/moderation/review.html duplicates the same 8 values as hardcoded <option>
  literals. Validate the POST value against the enum before the reason string is constructed.
  On an invalid value the Product Owner's 2026-10-03 ruling applies: re-render the review page
  with an error and preserve the moderator's typed input; nothing is coerced to empty; no audit
  row is written; it is NOT a 400. The mechanism for re-rendering with the typed input preserved
  is the recorded G-4a option.
goals:
  - "no arbitrary client string can reach ModeratorActionLog.reason"
  - "an invalid reason_category re-renders the review page with an error and preserves the moderator's typed category and comment"
  - "no audit row is written for a rejected request"
  - "keep the reason vocabulary in exactly one place in Python"
files:
  - path: "src/backend/apps/moderation/views/review.py"
    targets:
      - type: function
        name: reject_ad
      - type: function
        name: moderation_review
      - type: class
        name: CategoryRejectReason      # imported from apps.core.enums
    semantic_anchors:
      insert_before:
        type: assignment
        value: reason            # the reason string construction inside reject_ad
  - path: "src/backend/templates/admin/moderation/review.html"
    targets:
      - type: template_block
        name: rejectModal        # the select[name=reason_category] and its 8 <option> literals
changes:
  - action: add_code
    description: >
      Validate the raw POST reason_category against CategoryRejectReason at the top of
      reject_ad, before the reason string is built. On failure take the G-4a path: re-render the
      review page with a translated error, preserve the submitted reason_category and
      reason_text, return without writing an audit row.
  - action: modify_code
    description: >
      Per the G-4a option, either (a) extract moderation_review's context construction into a
      module-private helper both functions call, or (b) post a django.contrib.messages error and
      redirect. Keep the @require_POST + @staff_required decorator stack on reject_ad exactly
      as it is.
  - action: modify_code
    description: >
      In review.html, remove the duplicated hardcoded <option> values if G-4a(a) makes the enum
      the single source; and render the error notice plus the preserved reason_category and
      reason_text values.
  - action: modify_code
    description: >
      Regenerate locale catalogues via the Docker makemessages one-liner from
      .kilo/rules/commands.md. ru and bs msgstr must be non-empty for the new error string; en
      may remain empty.
acceptance_criteria:
  - "posting an arbitrary reason_category produces no ModeratorActionLog row"
  - "posting an invalid reason_category re-renders the review page, preserves the typed category and comment, and shows a translated error"
  - "the response is NOT 400 -- the Product Owner declined that reading"
  - "the four existing reject tests (reason_category='spam_scam') are green UNCHANGED"
  - "test_moderation_views.py::TestModerationReviewLocking is green UNCHANGED -- no new select_for_update and no new atomic() on the invalid path"
  - "no migration, no column, no lookup table for ModeratorActionLog.reason"
  - "ru and bs msgstr for the new error string are non-empty; test_i18n_completeness.py is green"
  - "the commit body names the G-4a option and carries an xref line for the Q2 ruling date"
  - ".\\Makefile.ps1 test is green"
tests_to_run:
  - "src/backend/apps/moderation/tests/test_moderation_views.py"
  - "src/backend/apps/moderation/tests/test_moderation_log.py"
  - "src/backend/tests/test_i18n_completeness.py"
new_tests:
  - "src/backend/apps/moderation/tests/test_moderation_views.py -- an invalid reason_category: no audit row, review page re-rendered, typed input preserved"
  - "src/backend/apps/moderation/tests/test_moderation_views.py -- every CategoryRejectReason member is accepted (one parametrised case per member)"
```

**Risk and rollback**

- *Behavioural risk:* the invalid path writes an audit row or returns 400 anyway. Mitigation:
  acceptance criteria 1–3 are the detector; a **Validator** is mandatory.
- *Regression risk (high):* the four existing reject tests turn red because the enum's values
  and the template's option values have drifted. Mitigation: constraint 3, and the new
  parametrised member-acceptance case catches drift *before* the template is edited.
- *Structural risk:* `G-4a`(a) changes `moderation_review`'s shape and could disturb
  `TestModerationReviewLocking`. Mitigation: the class is explicitly in `tests_to_run` and must
  be green unmodified.
- *Cross-phase:* plan 19 `B-2` may own a notice in the same template. Constraint 6.
- *i18n risk:* a new msgid with empty `ru`/`bs`. Mitigation: constraint 7; the completeness gate
  is in the fast gate.
- *Rollback:* a straight revert restores today's permissive behaviour. **There is no partial
  rollback**: if the enum validation lands but the re-render does not, the block has created a
  new failure mode. Land both halves in the one commit or neither.

---

### B-5 — Relocate the consent-cookie constants

| | |
|---|---|
| **Findings owned** | `CQ-013` (LOW, `DOC-UPDATE`) |
| **Class** | **mechanical** — a pure relocation; names and values byte-identical |
| **Depends on** | nothing in-plan |
| **Blocks** | `B-6` (`is_consent_given` is deleted from the same file by the dead-symbol block; running `B-5` first means `B-6`'s diff is a deletion in a file whose constants have already moved, so it cannot reintroduce them) |
| **Priority** | P2 |
| **Risk level** | **LOW** execution risk; ~40 pinned assertions across five test files |
| **Required agents** | **Auditor** (pre-step: re-enumerate the raw read sites). **Planner** owns `Q13`. No Researcher, no Validator |

**Decision required before implementation — `Q13`: where do the four `CONSENT_*` names live?**

The premise is intact and verified: `CONSENT_COOKIE_NAME`, `CONSENT_ANALYTICS_COOKIE`,
`CONSENT_PREFERENCES_COOKIE`, `CONSENT_TIMESTAMP_COOKIE` and `CONSENT_COOKIE_MAX_AGE` are
module-level constants in `src/backend/apps/users/views/consent.py`, and their values are read
back as **raw string literals** elsewhere. The remedy pattern already exists in the repo:
`PREFERRED_CITY_COOKIE_NAME` / `PREFERRED_CITY_COOKIE_MAX_AGE` live in
`apps/core/middleware/preferred_city.py` and are imported by both their consumers.

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | Move the five names **into** `apps/core/middleware/preferred_city.py`, beside the two `PREFERRED_CITY_*` names | **Gains:** zero new artifacts — literally the relocation the finding calls for; `consent.py` and `preferred_city.py` already import from that module, so the import graph does not change. **Costs:** the module's subject becomes "cookie constants" as well as "the preferred-city middleware"; a second responsibility |
| **(b)** | Create `apps/core/cookies.py` and move **all** cookie-name and max-age constants there, `PREFERRED_CITY_*` included | **Gains:** one honest home; the next cookie does not have to be added to a middleware. **Costs:** a **new module** for seven constants and one consumer pair — project rule 5 argues against it at this size; it touches `preferred_city.py`'s own import surface |
| **(c)** | Leave the constants in `consent.py` and import them from there at the read sites | **Gains:** smallest diff. **Costs:** **inverts the dependency** — a context processor and a search view would import from a **view** module. The finding's whole point is that the definition site is wrong |

**The Implementor may not choose.**

**File surface (semantic units)**

| File | Symbol / target | Notes |
|---|---|---|
| `src/backend/apps/core/middleware/preferred_city.py` | `PREFERRED_CITY_COOKIE_NAME`, `PREFERRED_CITY_COOKIE_MAX_AGE` | Read-only unless option (a) or (b) is chosen, in which case the `CONSENT_*` names are added beside them |
| `src/backend/apps/users/views/consent.py` | the module-level `CONSENT_*` constant declarations | **The definitions move or are re-exported; the values do not change.** Also the site of the `is_consent_given` helper that `B-6` deletes — constraint 4 |
| `src/backend/apps/users/context_processors.py` | `consent_state`, `consent_version`, `_ACTED_COOKIE_VALUES` | The raw cookie-name reads become named imports. Note `10-QLT-002`'s `4e26669a` already replaced the raw `consent_version` value — the **cookie name** reads are what remain |
| `src/backend/apps/search/views/preferred_city.py` | `set_preferred_city` | Its single raw `"consent_preferences"` read becomes a named import |

**Binding constraints**

1. **Cookie names and max-ages are byte-identical.** A rename silently breaks anonymous consent
   state for every returning visitor and is invisible until users re-consent again.
2. **No cookie is renamed, re-pathed, re-aged or re-attributed.** This block is a relocation
   and nothing else. If a name looks wrong, that is a separate decision with a separate
   decision-maker.
3. **No cookie-constants framework, no `StrEnum` for cookie names, no request/response
   helper.** One home for the names is the finding; the rest is refused (§8).
4. **This file has a second owner in this plan.** `B-6` deletes `is_consent_given` from
   `consent.py`. Re-read the file immediately before editing; if another agent has uncommitted
   changes there, **stop and report**.
5. **`consent_state` and `consent_version` must keep returning the same booleans.**
   `test_consent_context.py` asserts the processor's output for every cookie combination, and
   it must stay green unmodified.
6. **Do not touch `ConsentVersion`.** It was added by `3eab60d8` (`10-QLT-002`) and wired by
   `4e26669a`. It is a different concept from the cookie names and is not in this block's scope.

**Implementor task**

```yaml
id: task_24_b05_consent_cookie_constants
title: "Relocate the four CONSENT_* cookie names to their shared home (10-CQ-013)"
priority: low
depends_on: []
source_reference: ".ai/plans/24-code-quality-remediation-execution.md"
source_section: "B-5 - Relocate the consent-cookie constants"
source_blocks: ["B-5", "orig BLOCK 1 (CQ-013)"]
description: >
  Five cookie constants are declared in apps/users/views/consent.py and read back as raw string
  literals in apps/users/context_processors.py and once in apps/search/views/preferred_city.py.
  Renaming any of them would silently break anonymous consent state for every returning visitor.
  The repository already has the remedy: PREFERRED_CITY_COOKIE_NAME and PREFERRED_CITY_COOKIE_MAX_AGE
  live in apps/core/middleware/preferred_city.py and are imported by both consumers. Move the five
  CONSENT_* names to the Q13 destination and import them at every read site. Names and values are
  unchanged by contract.
goals:
  - "no raw consent cookie-name literal remains at any read site"
  - "every cookie name, value and max-age is byte-identical to today"
  - "introduce no abstraction beyond the single relocation the Q13 option names"
files:
  - path: "src/backend/apps/core/middleware/preferred_city.py"
    targets:
      - type: module
        name: preferred_city
      - type: assignment
        name: PREFERRED_CITY_COOKIE_NAME
      - type: assignment
        name: PREFERRED_CITY_COOKIE_MAX_AGE
  - path: "src/backend/apps/users/views/consent.py"
    targets:
      - type: module
        name: consent
      - type: assignment
        name: CONSENT_COOKIE_NAME
      - type: assignment
        name: CONSENT_ANALYTICS_COOKIE
      - type: assignment
        name: CONSENT_PREFERENCES_COOKIE
      - type: assignment
        name: CONSENT_TIMESTAMP_COOKIE
      - type: assignment
        name: CONSENT_COOKIE_MAX_AGE
      - type: function
        name: is_consent_given     # NOT deleted here -- B-6 deletes it
  - path: "src/backend/apps/users/context_processors.py"
    targets:
      - type: function
        name: consent_state
      - type: function
        name: consent_version
      - type: assignment
        name: _ACTED_COOKIE_VALUES
  - path: "src/backend/apps/search/views/preferred_city.py"
    targets:
      - type: function
        name: set_preferred_city
changes:
  - action: modify_code
    description: >
      Move (or re-export, per the recorded Q13 option) the five CONSENT_* declarations to the
      chosen home and replace every raw read site with a named import. Do not rename, re-age or
      re-attribute any cookie. Record the Q13 option and the destination module in the commit
      body, with an xref line for 4e26669a (10-QLT-002).
acceptance_criteria:
  - "no raw 'consent_given' / 'consent_analytics' / 'consent_preferences' / 'consent_timestamp' literal remains at any read site"
  - "the same cookie names, values and max-ages are produced as before"
  - "apps/users/tests/test_consent_context.py, test_consent.py and the preferred-city suites are green UNCHANGED"
  - "consent_state and consent_version return the same booleans for every cookie combination"
  - "is_consent_given is still present -- B-6 deletes it, this block must not"
  - "ConsentVersion is untouched"
  - "the commit body names the Q13 option and the destination module"
  - ".\\Makefile.ps1 test is green"
tests_to_run:
  - "src/backend/apps/users/tests/test_consent_context.py"
  - "src/backend/apps/users/tests/test_consent.py"
  - "src/backend/apps/search/tests/test_preferred_city.py"
  - "src/backend/apps/search/tests/test_preferred_city_readback.py"
```

**Tests required** — none new. This block adds a relocation and inherits the strongest existing
coverage in the report: roughly 40 assertions across five files pin the cookie names and
values. A pure relocation changes none of them. **The only new artefact permitted is the commit
body's record of the option and destination** — a grep-level check is not a test.

**Risk and rollback**

- *Implementation risk:* `Q13` answered implicitly by the Implementor. Mitigation: the gate; the
  commit body must name the option.
- *Regression risk:* a stale re-export leaves two homes for the same name. Mitigation: one home,
  not two (constraint 3). If the original declaration survives as an alias, that is a failed
  block, not a style choice.
- *Rollout risk:* none — no response, cookie attribute or path changes.
- *Cross-phase:* phase 01 (`ENT-005`) owns `consent.py`'s size; phase 06 owns the **service**
  layer, not these constants; `10-QLT-002` owns `ConsentVersion`. None is a collision, but the
  file is not quiet.
- *Rollback:* a straight revert. Zero data, zero schema, zero user-visible effect.

---

### B-6 — Delete what nothing references

| | |
|---|---|
| **Findings owned** | `CQ-016` (LOW) — deletion only. The `CQ-004` DTO-as-named half is dead and is **not** re-filed here |
| **Class** | **mechanical** — deletions |
| **Depends on** | `B-5` (file edge on `apps/users/views/consent.py`) |
| **Blocks** | `B-10` (`lookup_resolution.py` is on `B-10`'s inventory) |
| **Priority** | P3 |
| **Risk level** | **LOW**, conditional on one coordinator answer |
| **Required agents** | **Auditor** (pre-step: prove zero references, including templates and package `__init__` re-exports). No Researcher. **Validator** (only because the block deletes public-looking names that a comment claims are for external callers) |

**Decision required before implementation — `Q5` (narrow): do the three `RESOLVED_*_PREFIX`
aliases have any importer outside this repository?**

Their own comment claims they are *"kept for backward compatibility with any external callers"*.
The repo has zero. This is **one question to the coordinator**, and project rule 2 (production
code is king) only permits deleting them **after** it is asked.

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | **No external importer exists** (the expected answer) | Delete all three aliases and their comment. Zero in-repo risk |
| **(b)** | An external importer exists | Keep the three aliases. The rest of the block proceeds. **Do not** deprecate-and-remove, do not add a shim, do not add a `# deprecated` note — a deprecation path is a new artefact with no requested destination |

**The Implementor may not choose, and may not proceed past `Q5` for the three aliases.**

**File surface (semantic units)**

| File | Symbol / target | Change |
|---|---|---|
| `src/backend/apps/categories/services/lookup_resolution.py` | `RESOLVED_PURPOSES_PREFIX`, `RESOLVED_FEATURES_PREFIX`, `RESOLVED_CONDITIONS_PREFIX` | Delete the three aliases **and the comment above them**, per the `Q5` answer. The `*_SEGMENT` constants they alias stay — they are live |
| `src/backend/apps/categories/services/lookup_resolution.py` | the module-level `if TYPE_CHECKING: pass` guard, and `from typing import TYPE_CHECKING` | Delete the vestigial guard **and** the now-orphaned import, or `ruff` `F401` fires. This Planner verified the import exists solely to feed the guard |
| `src/backend/apps/users/views/consent.py` | `is_consent_given(request)` | Delete. Zero `.py` importers repo-wide (verified). The Auditor pre-step confirms no template and no package `__init__` reference |
| *`src/backend/apps/api/`* | **the directory** | **NOTHING TO DO.** The source plan's "empty `apps/api/` tree" premise is stale — no such tree exists in `git ls-files`. This is one of the audit's rotted premises and it is recorded as moot, not as a deletion |

**Binding constraints**

1. **`can_publish_ad` is not touched.** It is phase 15's `AUTHZ-005`, whose validator **rejected**
   the dead-code label (the behaviour is specified in `technical-specification.md`), and it is
   test-referenced many times. **Do not revive it under any name, in any block of this plan.**
2. **No symbol is deleted on the strength of a `.py` grep alone.** The Auditor pre-step must
   also check templates, `__all__` lists, package `__init__.py` re-exports, settings, and the
   `apps/seed/` tree, and quote the result in the commit body. Zero-reference claims are cheap
   to make and expensive to get wrong.
3. **The three aliases wait for `Q5`.** The other deletions in this block do not — they are
   proven dead in-repo and carry no external-caller claim.
4. **`lookup_resolution.py` is also the anchor of the source plan's stale `type: ignore` claim.**
   `B-10` inventories it. Do not touch a suppression in this block, even an obviously wrong one;
   note it in the commit body and let `B-10` classify it.
5. **No replacement is written for anything deleted.** No wrapper, no re-export, no
   deprecation shim, no comment pointing at a future home.

**Implementor task**

```yaml
id: task_24_b06_delete_dead_symbols
title: "Delete the unreferenced prefix aliases and the vestigial TYPE_CHECKING guard (10-CQ-016)"
priority: low
depends_on: [task_24_b05_consent_cookie_constants]
source_reference: ".ai/plans/24-code-quality-remediation-execution.md"
source_section: "B-6 - Delete what nothing references"
source_blocks: ["B-6", "orig BLOCK 8 (CQ-016)"]
description: >
  Three module-level prefix aliases in apps/categories/services/lookup_resolution.py have zero
  in-repo importers and a comment claiming they exist for external callers; their deletion waits
  on the coordinator's answer to Q5. A module-level "if TYPE_CHECKING: pass" guard in the same
  file feeds nothing, and the typing import that exists only to feed it must go with it or ruff
  F401 fires. is_consent_given in apps/users/views/consent.py has zero importers repo-wide. Delete
  all of them; write no replacement, re-export or shim. The source plan's separate "empty
  apps/api/ tree" item is stale and there is nothing to delete.
goals:
  - "delete only symbols proven to have zero references across py, templates, __all__, package __init__ and settings"
  - "delete no symbol that any test references"
  - "write no replacement, shim or deprecation note"
files:
  - path: "src/backend/apps/categories/services/lookup_resolution.py"
    targets:
      - type: assignment
        name: RESOLVED_PURPOSES_PREFIX
      - type: assignment
        name: RESOLVED_FEATURES_PREFIX
      - type: assignment
        name: RESOLVED_CONDITIONS_PREFIX
      - type: module
        name: lookup_resolution     # the TYPE_CHECKING guard and its import
      - type: import
        name: TYPE_CHECKING
    semantic_anchors:
      delete_in_body:
        type: statement
        value: "if TYPE_CHECKING:"
  - path: "src/backend/apps/users/views/consent.py"
    targets:
      - type: function
        name: is_consent_given
changes:
  - action: delete_code
    description: >
      Delete RESOLVED_PURPOSES_PREFIX, RESOLVED_FEATURES_PREFIX and RESOLVED_CONDITIONS_PREFIX
      and the comment above them, ONLY if the recorded Q5 answer is "no external importer". Keep
      the RESOLVED_*_SEGMENT constants.
  - action: delete_code
    description: >
      Delete the module-level "if TYPE_CHECKING: pass" guard and the "from typing import
      TYPE_CHECKING" import in the same module.
  - action: delete_code
    description: >
      Delete is_consent_given from apps/users/views/consent.py.
acceptance_criteria:
  - "the Q5 answer is recorded in the commit body before the three aliases are deleted"
  - "the Auditor pre-step's zero-reference evidence (py + templates + __all__ + package __init__ + settings + seed) is quoted in the commit body"
  - "RESOLVED_PURPOSES_SEGMENT and its two siblings are unchanged"
  - "no test anywhere referenced any deleted symbol (the fast gate proves it)"
  - "can_publish_ad is byte-unchanged"
  - "no type: ignore comment was added, removed or edited in this block"
  - "no replacement, shim or deprecation note was written"
  - "uv run ruff check on both edited files is clean (proves no orphaned import)"
  - ".\\Makefile.ps1 test is green"
tests_to_run:
  - "src/backend/apps/categories/tests/"
  - "src/backend/apps/users/tests/"
```

**Tests required** — none new, and none deleted. **Deleting a symbol that a test references makes
the fast gate red; that is the detector, and the correct response is to stop, not to edit the
test.** No test may be added to assert that a symbol is *absent* — absence is not an observable
contract and such a test forbids the symbol's future return (source plan §6.3 item 14).

**Risk and rollback**

- *The real risk:* the `Q5` answer is wrong and an external consumer breaks. Mitigation: the
  gate. This is the only deletion in the plan with a stated external surface, and it is the only
  one that waits.
- *Regression risk:* a zero-reference claim that misses a dynamic reference. Mitigation:
  constraint 2's expanded search; detection is the fast gate for imports and the Auditor's
  report for `settings`/config strings.
- *Process risk:* the block becomes a general dead-code sweep. Mitigation: the file surface is a
  closed list of five symbols. Anything else is a new finding.
- *Rollback:* a straight revert. Zero data, zero schema.

---

### B-7 — One Pydantic boundary for the saved-search POST

| | |
|---|---|
| **Findings owned** | `CQ-004` (MEDIUM, `BEST-PRACTICE`), **re-scoped**. The named DTO never existed; the duplicated coercion closure is the live defect |
| **Class** | **behavioural** — introduces a validation boundary and, depending on `Q12`, a new response shape |
| **Depends on** | `B-2` (file edge: `search/views/save_search.py` carries a bare locale literal that `B-2` fixes), `B-6` (`consent.py` adjacency is irrelevant; the real edge is one-implementor serialisation) |
| **Blocks** | nothing in-plan |
| **Priority** | P2 |
| **Risk level** | **MEDIUM** |
| **Required agents** | **Auditor** (pre-step: re-measure both call sites), **Planner** (owns the DTO home), **Owner** (owns the response shape, per `Q12`), **Validator** (mandatory — new validation path) |

**What the re-scoping changes.** The source plan's block named two artefacts. **Neither exists:**
`SavedSearchInput` has zero matches repo-wide, and `save_search.py` lives at
`apps/search/views/save_search.py`, not `ads/services/`. What **is** real and verbatim-duplicated
is a module-private coercion closure — `def _int_or_none(name: str) -> int | None` — declared
once inside the `save_search` view and once inside `saved_searches._apply_filters`, with the
same four call sites each (`city_id`, `category_id`, `min_price`, `max_price`).

**The house pattern already exists and is the precedent to follow:** `BaseInputModel`, introduced
by `33345c96 feat(schemas): enforce extra=forbid on input DTOs via BaseInputModel`, used by
`AdEditInput` and `SubmitAdInput` in `apps/ads/services/submission.py`. A DTO here is not a new
abstraction; it is the third instance of the existing one.

**Decision required before implementation — `Q12`: where does the input DTO live, and what is
the error response shape?**

Two questions in one gate because they are one decision: the location determines who may
construct it, and the error shape determines whether this is a view-level concern or a boundary
concern.

| Part | Options | Consequences |
|---|---|---|
| **Home** | **(a)** a new `src/backend/apps/search/schemas.py`, matching `apps/media/schemas.py`, `apps/users/schemas.py` and `telegram_bot/schemas/` | **Gains:** follows the established layout; the DTO is importable by both views without either owning it. **Costs:** one new module. Phase 08 owns `apps/search/models.py` and the next search migration — this is not that, but the app is not quiet |
| | **(b)** a new class in `apps/search/services/…` | **Gains:** nothing the layout does not already give. **Costs:** a validation DTO is not a service; putting it in `services/` is a layer error. **Not recommended** |
| | **(c)** a shared coercion helper only, **no** Pydantic model | **Gains:** kills the duplication with the smallest possible surface; no new response shape, so no `Q12`-style owner decision is needed. **Costs:** leaves the *boundary validation* half of `CQ-004` unaddressed — `min_price=-1` is still silently persisted. Honest description: this is `CQ-004`'s **duplication** finding, not its **validation** finding |
| **Error shape** | **(i)** HTTP 400 with a translated message | **Gains:** simplest; no template change. **Costs:** the moderator/member sees a bare 400 page; the modal's state is lost |
| | **(ii)** re-render the saved-search surface with an error and the submitted values preserved | **Gains:** consistent with `Q2`'s ruling on the sibling moderation boundary and with what a user actually expects from a form. **Costs:** a template change and **two new translated strings** (`ru` + `bs` non-empty) |

**The Implementor may not choose either part.** Under option **(c)** the block is honest and
small — and if the coordinator prefers (c), `CQ-004`'s validation half must be **re-filed with a
named destination**, not silently dropped.

**File surface (semantic units)**

| File | Symbol / target | Change |
|---|---|---|
| `src/backend/apps/search/views/save_search.py` | the view function **`save_search`**, its nested closure **`_int_or_none`** | Validate the POST through the DTO; delete the closure. **Keep the view function named `save_search`** — `test_save_search_url_resolves` asserts the resolved view's `__name__` is `save_search`, and that test must stay green unmodified |
| `src/backend/apps/search/views/save_search.py` | the `request.LANGUAGE_CODE or "bs"` fallback | **Preserved verbatim.** `B-2` may already have replaced the bare `"bs"` with `LanguageLocale.BOSNIAN`; whichever form is present stays |
| `src/backend/apps/cabinet/views/saved_searches.py` | **`_apply_filters`** and its nested closure **`_int_or_none`**, and **`saved_search_edit`** | Validate through the same DTO; delete the second copy. **Both copies go in the same commit** — a fix that leaves one is not a fix |
| `src/backend/apps/search/schemas.py` | **`SavedSearchInput`** — **NEW**, or the `Q12`(a) location | The DTO. `BaseInputModel` subclass, `extra="forbid"`, the four coerced fields with `ge=0` on the price bounds |
| `src/backend/apps/search/models.py` | `SavedSearch` | **READ-ONLY. No field, no constraint, no validator, no migration.** Project rule 13 is satisfied by *not* touching it |

**Binding constraints**

1. **No migration, no `CheckConstraint`, no `MinValueValidator` on `SavedSearch`.** The gate is
   boundary validation. The source plan's crash framing was **refuted** — `PositiveIntegerField`
   defines no `check()` and the migration has no `CheckConstraint`, so `min_price=-1` is
   *silently persisted today*, not a 500. The commit body must state this correctly; do not
   propagate a false reproduction.
2. **Both `_int_or_none` copies die in one commit.** Half a fix leaves the duplication that is
   the finding.
3. **The view names do not change.** `save_search` and `saved_search_edit` stay exactly as they
   are; `test_save_search_url_resolves` is a tripwire.
4. **`ge=0` on the price bounds is the validation content.** It is a boundary rule, not a schema
   change, and it requires no migration because it is enforced by the DTO.
5. **`PreferredCityInput` is out of scope and stays out.** `set_preferred_city` already
   validates with an explicit existence query, already returns a 400 with a documented reason,
   already has `@require_POST`, and already owns its cookie constants. A Pydantic wrapper there
   adds a layer with no defect behind it — a direct violation of project rules 5 and 7 (§8).
6. **Phase 08 owns `apps/search/models.py` and the next search migration.** This block edits
   neither. If the Auditor pre-step finds a search migration in flight, **stop and report.**

**Implementor task**

```yaml
id: task_24_b07_saved_search_input_boundary
title: "Give the saved-search POST one Pydantic boundary and delete both coercion closures (10-CQ-004)"
priority: high
depends_on: [task_24_b02_locale_literals]
source_reference: ".ai/plans/24-code-quality-remediation-execution.md"
source_section: "B-7 - One Pydantic boundary for the saved-search POST"
source_blocks: ["B-7", "orig BLOCK 4 (CQ-004, re-scoped)"]
description: >
  Two views coerce the same four POST fields through byte-identical module-private closures,
  "def _int_or_none(name: str) -> int | None": the save_search view in apps/search/views/save_search.py
  and _apply_filters in apps/cabinet/views/saved_searches.py. The repo already has the DTO pattern
  to follow -- BaseInputModel, enforced with extra=forbid, used by AdEditInput and SubmitAdInput in
  apps/ads/services/submission.py. Introduce SavedSearchInput at the recorded Q12 location, validate
  both POSTs through it, delete both closures, and add ge=0 on the price bounds. The view names do not
  change. No migration: Django's PositiveIntegerField emits no check constraint, so min_price=-1 is
  silently persisted today rather than crashing -- the commit body must say so.
goals:
  - "both saved-search POSTs are validated through one shared input DTO"
  - "no _int_or_none closure remains in either view"
  - "min_price / max_price below zero are rejected at the boundary without a migration"
  - "change no model field, no constraint, no view name"
files:
  - path: "src/backend/apps/search/schemas.py"
    targets:
      - type: class
        name: SavedSearchInput          # NEW (or the Q12 location), BaseInputModel subclass
  - path: "src/backend/apps/search/views/save_search.py"
    targets:
      - type: function
        name: save_search
      - type: function
        name: _int_or_none              # deleted
    semantic_anchors:
      delete_in_body:
        type: function
        value: _int_or_none
  - path: "src/backend/apps/cabinet/views/saved_searches.py"
    targets:
      - type: function
        name: _apply_filters
      - type: function
        name: _int_or_none              # deleted
      - type: function
        name: saved_search_edit
  - path: "src/backend/apps/search/models.py"
    targets:
      - type: class
        name: SavedSearch               # READ-ONLY
changes:
  - action: add_code
    description: >
      Add SavedSearchInput at the recorded Q12 location: a BaseInputModel subclass with extra=forbid
      and the four fields the two views coerce today (city_id, category_id, min_price, max_price),
      the prices bounded ge=0. Follow the coercion semantics the two closures implement exactly.
  - action: modify_code
    description: >
      Validate the POST in save_search through the DTO and delete its _int_or_none closure.
      Preserve the view name, its URL name, the LoginRequired behaviour and the
      request.LANGUAGE_CODE fallback verbatim.
  - action: modify_code
    description: >
      Validate the POST in saved_searches._apply_filters through the same DTO and delete the
      second _int_or_none closure. Keep saved_search_edit as it is otherwise.
  - action: modify_code
    description: >
      If Q12(ii) was chosen, render the recorded error response with the submitted values
      preserved, and regenerate locale catalogues with non-empty ru and bs msgstr for the new
      strings via the Docker makemessages one-liner.
acceptance_criteria:
  - "no _int_or_none closure remains in either view"
  - "the save_search view function is still named save_search and test_save_search_url_resolves is green UNCHANGED"
  - "the four existing saved-search tests are green UNCHANGED"
  - "a POST with min_price=-1 is rejected at the boundary and no SavedSearch row is created"
  - "SavedSearch has no new field, no constraint and no validator; makemigrations --check reports no new migration"
  - "the request.LANGUAGE_CODE fallback is preserved verbatim"
  - "set_preferred_city is byte-unchanged -- PreferredCityInput was refused"
  - "the commit body records the Q12 option and states the corrected min_price=-1 behaviour"
  - "uv run ruff check, uv run basedpyright are clean; .\\Makefile.ps1 test is green"
tests_to_run:
  - "src/backend/apps/search/tests/"
  - "src/backend/apps/cabinet/tests/"
new_tests:
  - "one case per DTO field asserting a malformed value is rejected (component interaction: coercion semantics preserved)"
  - "one case asserting the rejected POST creates no SavedSearch row"
  - "one case asserting a valid POST persists exactly as before (no regression on the happy path)"
```

**Risk and rollback**

- *Behavioural risk:* the DTO rejects something a real user sends today and the block breaks a
  working form. Mitigation: the coercion semantics are the closures' semantics, copied exactly;
  the happy-path case is explicit; the four existing tests are the net.
- *Scope risk:* the block grows a template, a second DTO, or a `PreferredCityInput`. Mitigation:
  constraints 1 and 5.
- *Cross-phase:* phase 08 owns `search/models.py` and the next search migration. Constraint 6.
- *Rollback:* a straight revert. The boundary is new, so reverting restores the old permissive
  coercion with no data-shape consequence.

---

### B-8 — Stop promising a toggle the bot does not have

| | |
|---|---|
| **Findings owned** | `CQ-014` (MEDIUM → executes **LOW**) — **both halves**: the prompt correction and the dead-state deletion |
| **Class** | **behavioural**, LOW — a user-visible string changes and a public enum member disappears |
| **Depends on** | nothing in-plan |
| **Blocks** | `B-9` (same file: `B-8` edits `cmd_alerts`'s prompt; `B-9` moves four functions out of the same handler. Structural last) |
| **Priority** | P1 |
| **Risk level** | **LOW** |
| **Required agents** | **Auditor** (pre-step: confirm the three router entry points and the zero-reference claim), **Validator** (i18n obligation ⇒ a new msgid with two non-empty translations) |

**Ruling already made — carry it as a constraint.** The Product Owner **declined the numeric
`/alerts` toggle for this programme**. The finding's *defect* is a shipped prompt promising an
interaction the code does not implement; the proportionate fix is **the prompt plus the
dead-state deletion**, and that is the whole deliverable. **Explicitly out of scope under the
ruling: the FSM, a new router entry point, numeric input parsing, and every new string beyond
the corrected prompt.**

**The audit reports zero drift on this block.** The prompt literal is exactly where the source
plan said it is, inside `cmd_alerts`, and all three router entry points are unchanged. The only
shape drift is that the callback prefixes are now `BotCallbackPrefix.*` enum members rather than
bare names — which is itself the result of `10-QLT-002`'s work and is not this block's subject.

**File surface (semantic units)**

| File | Symbol / target | Change |
|---|---|---|
| `src/telegram_bot/handlers/alerts.py` | **`cmd_alerts`** — the prompt line that appends the "reply with number to toggle" sentence to the listing | Correct the sentence so it describes what the code actually does: the listing is a subscription summary with unsubscribe / re-enable actions, and **there is no per-number toggle**. The replacement must contain **no** promise of a numeric reply and must still mention `/cancel` if `/cancel` is handled |
| `src/telegram_bot/handlers/alerts.py` | the three router registrations — `Command("alerts")`, and the two handlers matching `BotCallbackPrefix.UNSUB` and `BotCallbackPrefix.UNSUB_ON` | **UNCHANGED.** The Auditor pre-step confirms all three, and the commit body records them. This is the block's tripwire: a numeric handler must not be added |
| `src/telegram_bot/states.py` | `class SavedSearchState(StrEnum)` | **Delete.** Zero `.py` importers repo-wide (verified by this Planner and by the audit's own `CQ-014` evidence) |
| `src/backend/locale/{ru,bs,en}/LC_MESSAGES/django.po` | the msgid for the old prompt sentence | The old msgid disappears; the new one needs **non-empty `ru` and `bs`** `msgstr`. `en` may stay empty because the msgid is English |

**Binding constraints**

1. **No new router entry point, no FSM state, no numeric parsing.** Three times now: this is the
   whole reason the block is cheap. Adding a toggle is a **new feature**, ruled out.
2. **`telegram_bot/handlers/lifecycle.py` is not touched.** Its per-locale `Уведомления` literal
   is a **documented EC-3 decision against gettext**, not part of this finding. "Fixing" it would
   reverse a recorded decision.
3. **The corrected prompt must not over-promise in the other direction.** It may not claim a
   toggle, and it may not invent a capability that does not exist either. Read the handler
   before writing the sentence.
4. **`SavedSearchState` deletion waits on nothing but a re-confirmed zero-reference check** that
   covers the whole bot tree and the backend tree (`B-9`'s new module must not import it — record
   that check).
5. **i18n is part of the definition of done.** One msgid changes. `ru` and `bs` non-empty;
   regenerate via the Docker one-liner from `.kilo/rules/commands.md`, never `make makemessages`.
6. **Do not delete or weaken any test to accommodate the string change.** No test covers
   `cmd_alerts`'s listing or prompt today, which is why the correction is unopposed — and also
   why this block must not grow one that re-derives the prompt text (that would re-pin the exact
   thing being corrected).

**Implementor task**

```yaml
id: task_24_b08_alerts_prompt
title: "Correct the /alerts prompt and delete the dead SavedSearchState (10-CQ-014)"
priority: medium
depends_on: []
source_reference: ".ai/plans/24-code-quality-remediation-execution.md"
source_section: "B-8 - Stop promising a toggle the bot does not have"
source_blocks: ["B-8", "orig BLOCK 10 (CQ-014) + orig BLOCK 8's dead-state half"]
description: >
  cmd_alerts ends its subscription listing with a sentence telling the user to reply with a number
  to toggle. No numeric handler exists: the module registers only /alerts, an UNSUB callback handler
  and an UNSUB_ON callback handler. The sentence is a live user-facing dead end. The Product Owner
  declined the toggle feature for this programme, so the deliverable is the corrected prompt plus
  the deletion of the zero-reference SavedSearchState StrEnum in telegram_bot/states.py. No FSM, no
  new router entry point, no numeric parsing, and no new string beyond the corrected prompt.
goals:
  - "the /alerts prompt describes only behaviour the bot actually implements"
  - "no user-facing string promises a numeric toggle"
  - "delete the zero-reference SavedSearchState enum"
  - "add no handler, no state and no parsing"
files:
  - path: "src/telegram_bot/handlers/alerts.py"
    targets:
      - type: function
        name: cmd_alerts
      # the three router registrations are read-only and are the block's tripwire
    semantic_anchors:
      replace_in_body:
        type: string_literal
        value: "\\nReply with number to toggle, or /cancel to exit."
  - path: "src/telegram_bot/states.py"
    targets:
      - type: class
        name: SavedSearchState          # deleted
  - path: "src/backend/locale/ru/LC_MESSAGES/django.po"
    targets:
      - type: module
        name: django
  - path: "src/backend/locale/bs/LC_MESSAGES/django.po"
    targets:
      - type: module
        name: django
changes:
  - action: modify_code
    description: >
      Rewrite the prompt line in cmd_alerts so it describes the listing and the available
      actions truthfully. No numeric reply may be promised.
  - action: delete_code
    description: >
      Delete class SavedSearchState from telegram_bot/states.py. Delete no other state; the module
      may hold states other blocks depend on.
  - action: modify_code
    description: >
      Regenerate locale catalogues with the Docker makemessages one-liner from
      .kilo/rules/commands.md. Provide non-empty ru and bs msgstr for the new prompt sentence.
      en may remain empty.
acceptance_criteria:
  - "the /alerts prompt contains no numeric-toggle promise"
  - "all three router registrations (Command(\"alerts\"), BotCallbackPrefix.UNSUB, BotCallbackPrefix.UNSUB_ON) are unchanged -- quoted in the commit body"
  - "no new handler, state, or numeric parsing was added"
  - "SavedSearchState is gone and nothing imports it"
  - "telegram_bot/handlers/lifecycle.py is byte-unchanged"
  - "ru and bs msgstr for the new prompt sentence are non-empty; test_i18n_completeness.py is green"
  - "no test was added that re-derives or asserts the prompt text"
  - ".\\Makefile.ps1 test is green"
tests_to_run:
  - "src/telegram_bot/tests/test_unsubscribe.py"
  - "src/backend/tests/test_i18n_completeness.py"
```

**Tests required** — none new. **No test asserts the prompt text, and this block must not add
one** (it would re-pin the exact string being corrected). The zero-reference claim for
`SavedSearchState` is discharged by the Auditor pre-step, not by a test.

**Risk and rollback**

- *Product risk:* the corrected sentence is less inviting and a user reads the listing as less
  capable. **Accepted by decision** — the previous sentence described a capability that does not
  exist, which is the defect. If the owner wants a different phrasing, that is an owner decision
  against a recorded ruling, not an implementor choice.
- *i18n risk:* an empty `ru`/`bs` msgstr ships a machine-translated screen. Mitigation:
  constraint 5; the completeness gate is inside the fast gate.
- *Regression risk:* deleting an enum member that a `State` filter somewhere still names.
  Mitigation: the pre-step's whole-tree check; the fast gate.
- *Rollback:* a straight revert. Reverting restores a promise the code does not keep — which is
  the defect, so a rollback is a deliberate acceptance, not a safety measure.

---

### B-9 — Move the bot's alert data access out of the handler

| | |
|---|---|
| **Findings owned** | `CQ-002`, `alerts` half (MEDIUM) |
| **Class** | **behavioural** — a module boundary moves; two source-inspection tests must be re-pointed |
| **Depends on** | `B-8` (same file: `B-8` edits `cmd_alerts`'s prompt, `B-9` moves four functions out of the same handler. Structural last) |
| **Blocks** | nothing in-plan |
| **Priority** | P2 |
| **Risk level** | **MEDIUM** |
| **Required agents** | **Auditor** (pre-step: enumerate every caller of the five functions and the locking shape of `_resolve_owned`), **Researcher** (owns the lock-timeout policy question below), **Validator** (mandatory — two source-inspection tests must be re-pointed, not deleted) |

**The surface is larger than at the anchor.** The source plan named two candidates; the audit
found **five**, all still live in the handler layer:

| Symbol | File | Role |
|---|---|---|
| `get_user_saved_searches(user_id)` | `src/telegram_bot/handlers/alerts.py` | Sync ORM read of the member's saved searches, called from the handler |
| `resolve_unsubscribe(...)` | same | Sync mutation behind the `UNSUB` callback |
| `resolve_reenable(...)` | same | Sync mutation behind the `UNSUB_ON` callback |
| `_resolve_owned(...)` | same | **Ownership + row-locked resolution.** Covered by a source-inspection test |
| the module's remaining direct ORM access | same | The Auditor pre-step enumerates it |

**The asymmetry this block must account for:** the backend side of the same feature already has
services — `apps/search/services/alert_query.py`, `apps/search/services/immediate_alerts.py`,
`apps/search/services/notification_delivery.py`. The bot tier reaching straight into the ORM
where the web tier does not is the inconsistency. The shipped precedent for the *pattern* is
`f09512b5 (10-QLT-005)`, which relocated `annotate_favorites` out of a view into
`apps/ads/services/favorites.py`; the commit body must cite it.

**Decision required before implementation — external: what is the lock-timeout policy for a
bot-side row lock in an extracted service?**

The source plan listed "phase 03 BLOCK 5" as this block's external gate. Measured at HEAD, that
gate is **half-met**: `apps/core/utils/db_lock_timeout.py` contains only `is_lock_timeout(exc)`
— the **error-boundary** half shipped as `42d0edd8 (03-DB-004 timeout half B)`, consumed where the
view catches the exception — and **no `SET LOCAL lock_timeout` statement exists anywhere.** The
policy half of phase 03 BLOCK 5 has not landed.

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | The extracted service owns its own lock handling, mirroring whatever the source plan's sibling views do today | **Gains:** the block proceeds without waiting for phase 03. **Costs:** if phase 03's policy lands later, the new service is one more caller to revisit — and `_resolve_owned` already holds a row lock, so this is not hypothetical |
| **(b)** | The block waits for phase 03 BLOCK 5's policy | **Gains:** the service is written once against the settled policy. **Costs:** the block is externally blocked with no known landing date, for a change that is a *relocation* rather than a lock-semantics change |
| **(c)** | The relocation lands with the lock shape **byte-preserved**, and the timeout question is explicitly recorded as out of scope and routed to phase 03 | **Gains:** no behaviour change at all in this block; the open policy question is named rather than silently inherited. **Costs:** one recorded follow-up |

**The Implementor may not choose.** This is a coordinator/coordinator-with-phase-03 decision, and
it is the reason this block is `MEDIUM` and not `LOW`.

**File surface (semantic units)**

| File | Symbol / target | Change |
|---|---|---|
| `src/telegram_bot/services/alerts.py` | **NEW module** — `get_user_saved_searches`, `resolve_unsubscribe`, `resolve_reenable`, `_resolve_owned` | The four functions move here **with their query and locking shape unchanged**. `_resolve_owned`'s `select_for_update` stays; it is not "cleaned up" in a relocation commit |
| `src/telegram_bot/handlers/alerts.py` | the four moved symbols, and their call sites in `cmd_alerts` and the two callback handlers | Become module-scope imports plus call-site updates. The handler keeps its aiogram wiring, its i18n and its message building — **only data access moves** |
| `src/telegram_bot/handlers/alerts.py` | `cmd_alerts` and the two callback handlers | Their observable behaviour is unchanged: same keyboards, same callback payloads, same text, same `BotCallbackPrefix.*` values |
| `src/backend/apps/search/services/{alert_query,immediate_alerts,notification_delivery}.py` | — | **READ-ONLY.** These are the backend's equivalents and are the model to mirror, not the target |
| `src/backend/apps/cabinet/tests/`-adjacent backend fixtures | — | **READ-ONLY.** The bot tier may not import the backend's test `conftest` |

**Binding constraints**

1. **Locking shape is byte-preserved.** `telegram_bot/tests/test_unsubscribe.py::TestResolveOwnedLocking`
   inspects the function's source. A relocation that "tidies" the query, renames the variable or
   changes the lock's position turns that class red for a change that was supposed to be a move.
2. **Two source-inspection tests are re-pointed, never deleted.**
   `test_unsubscribe.py::TestResolveOwnedLocking` is re-pointed at the new module. The audit
   confirms the second cluster, `moderation/tests/test_moderation_views.py::TestModerationReviewLocking`,
   is **not** touched by this block (different file, different app).
3. **Three modules are forbidden**, exactly as the source plan's §6.3 recorded:
   no `telegram_bot/services/login.py` (already shipped by phase 01 `ENT-005` — creating it would
   re-split a cross-process protocol), no `services/contact.py`, no `services/support.py`. Their
   handler-side deferrals are **import hoists**, not extractions, and belong to phase 09.
4. **No new abstraction beyond the one module.** No repository class, no base service, no
   registry. The four functions and the module are the entire surface.
5. **The bot tier may not import the backend's `conftest`** — `src/telegram_bot/tests/conftest.py`
   redefines the fixtures for exactly this reason. If a needed fixture appears missing, it is a
   module-local fixture, not a backend import.
6. **The `B-8` prompt change stays visible.** A reviewer of this diff must be able to see that
   the corrected prompt survived the move.

**Implementor task**

```yaml
id: task_24_b09_bot_alerts_service
title: "Move the bot alerts handler's data access into telegram_bot/services/alerts.py (10-CQ-002)"
priority: high
depends_on: [task_24_b08_alerts_prompt]
source_reference: ".ai/plans/24-code-quality-remediation-execution.md"
source_section: "B-9 - Move the bot's alert data access out of the handler"
source_blocks: ["B-9", "orig BLOCK 11 (CQ-002 alerts half)"]
description: >
  telegram_bot/handlers/alerts.py performs its saved-search reads and mutations directly in the
  handler layer: get_user_saved_searches, resolve_unsubscribe, resolve_reenable and _resolve_owned.
  The backend tier already owns the same feature as services (apps/search/services/alert_query.py,
  immediate_alerts.py, notification_delivery.py), so the asymmetry is a layering inconsistency with
  no user-visible defect. Move the four functions into a new telegram_bot/services/alerts.py with
  their query and locking shape byte-preserved, and leave the handler owning only aiogram wiring,
  i18n and message building. f09512b5 (10-QLT-005) is the shipped precedent for the same pattern.
goals:
  - "no ORM access remains in the bot alerts handler"
  - "_resolve_owned's row-lock shape is byte-preserved"
  - "re-point the source-inspection test; delete nothing"
  - "create exactly one new module and no base class, registry or repository"
files:
  - path: "src/telegram_bot/services/alerts.py"
    targets:
      - type: module
        name: alerts            # NEW
      - type: function
        name: get_user_saved_searches
      - type: function
        name: resolve_unsubscribe
      - type: function
        name: resolve_reenable
      - type: function
        name: _resolve_owned
  - path: "src/telegram_bot/handlers/alerts.py"
    targets:
      - type: function
        name: cmd_alerts
      - type: module
        name: alerts             # the four symbols leave; the wiring stays
  - path: "src/telegram_bot/tests/test_unsubscribe.py"
    targets:
      - type: class
        name: TestResolveOwnedLocking    # RE-POINTED at the new module, never deleted
    semantic_anchors:
      replace_value:
        type: imported_symbol
        value: "_resolve_owned"
changes:
  - action: add_code
    description: >
      Create telegram_bot/services/alerts.py and move get_user_saved_searches,
      resolve_unsubscribe, resolve_reenable and _resolve_owned into it unchanged. Preserve the
      query construction and the select_for_update position in _resolve_owned exactly.
  - action: modify_code
    description: >
      Update handlers/alerts.py to import those four symbols at module scope and call them. Keep
      every router registration, keyboard, callback payload, BotCallbackPrefix value and
      translated string exactly as they are, including the corrected prompt from B-8.
  - action: modify_code
    description: >
      Re-point TestResolveOwnedLocking's inspected symbol to the new module. Do not weaken, skip or
      delete the assertion, and do not change its count-based expectations.
acceptance_criteria:
  - "handlers/alerts.py contains no ORM access"
  - "telegram_bot/services/alerts.py is the only new module; no repository/base/registry abstraction exists"
  - "TestResolveOwnedLocking is green and still asserts the same locking shape, re-pointed at the new module"
  - "no test was deleted or weakened"
  - "no telegram_bot/services/login.py, contact.py or support.py was created"
  - "the bot tier imports nothing from the backend's conftest"
  - "the B-8 prompt correction is present and unchanged in the moved handler"
  - "the commit body cites f09512b5 as the precedent and records the lock-timeout policy decision"
  - ".\\Makefile.ps1 test is green"
tests_to_run:
  - "src/telegram_bot/tests/test_unsubscribe.py"
  - "src/telegram_bot/tests/test_immediate_alerts.py"
  - "src/backend/apps/search/tests/"
```

**Risk and rollback**

- *Regression risk (highest of the "cheap" blocks):* a moved function's query or lock shape
  drifts, and only a source-inspection test notices. Mitigation: constraints 1 and 2; the
  re-pointed class is the detector and a **Validator** is mandatory.
- *Coordination risk:* phase 09's rate-limiter block edits `handlers/contact.py`, a different
  region of the same tier. Not an overlap, but sequential and re-read.
- *Scope risk:* the block absorbs the `contact`/`support` import hoists. Mitigation: constraint 3.
- *Rollback:* a straight revert. The four functions return to the handler with no data
  consequence.

---

### B-10 — `type: ignore` inventory and routing (decision-only)

| | |
|---|---|
| **Findings owned** | `CQ-012` (MEDIUM), **re-scoped to a decision**. The source plan's scope ("4 suppressions") cannot be executed against 83 |
| **Class** | **decision / triage.** No code change is expected. **Zero commits** unless the routing decision produces a code change, and it must not be taken here |
| **Depends on** | `B-6` (`lookup_resolution.py` is edited by `B-6`, so its suppression state must be read after, not before) |
| **Blocks** | nothing in-plan |
| **Priority** | P2 — run early enough that its conclusion can de-scope later blocks |
| **Risk level** | **LOW** as an inventory; **HIGH** if anyone treats it as "delete 83 suppressions" |
| **Required agents** | **Auditor** (owns the inventory), **Researcher** (classifies each), **Planner** (writes the routing decision). **No Implementor. No Validator** |

**Why this block ships no code.** Three reasons, in order of weight:

1. **The stated scope is wrong by ~20×.** The audit measured `type: ignore` on **83 lines** across
   `src/**/*.py`. The source plan's "4 `type: ignore[type-arg]` suppressions, all in
   `lookup_resolution.py`" would, executed literally, pick the wrong four out of 83.
2. **No gate enforces this.** `[tool.mypy]` carries `disallow_any_generics`, but basedpyright does
   not read it, and mypy is not in CI. **"Type errors went from N to 0" is therefore not
   available as evidence** for anything in this block, and no acceptance criterion may claim it.
3. **A repo-wide suppression sweep is a legacy sweep, and it is not phase 10's.**
   Phase 03 BLOCK 11 reserves exactly that class of sweep to itself and forbids other phases from
   starting one. 83 suppressions across 300 production files *is* one.

**The block's deliverable is therefore a classification and a routing decision**, which is what
the finding actually needs in order to become executable by anyone.

**File surface (semantic units)**

| Unit | Role |
|---|---|
| Every `type: ignore` / `type: ignore[...]` site under `src/**/*.py` (83 lines at the audit's measurement) | **READ-ONLY.** The inventory. No site is edited |
| `pyproject.toml` → `[tool.basedpyright]`, `[tool.mypy]`, `[tool.ruff]` | **READ-ONLY.** The Auditor records exactly which configuration is enforced by CI (`ci.yml` runs `ruff check src/` and `basedpyright src/`) |
| `src/backend/apps/categories/services/lookup_resolution.py` | Read the suppression state **after** `B-6`, and record it |

**Binding constraints**

1. **No suppression is deleted, added, narrowed or widened by this block.** The deliverable is a
   table, not a diff.
2. **Each suppression is classified into exactly one bucket**, with the reason recorded:
   `(i) load-bearing` — removing it would fail `basedpyright`; `(ii) justified` — suppressing a
   third-party or framework gap, with the reason; `(iii) removable` — the type is now expressible;
   `(iv) belongs to another phase's sweep` — phase 03 BLOCK 11's reservation, or a specific
   phase's finding.
3. **Only buckets (i) and (ii) may be "corrected" later**, and only in a follow-up block that
   names its owner. **A bucket-(iii) removal may not be bundled into another block's commit.**
4. **No claim of type-safety improvement.** `basedpyright` in standard mode does not flag bare
   generics, and mypy is not in CI (constraint 2 above). Any commit message that says "typed
   boundaries now enforced" is false and must be corrected.
5. **If the triage concludes that no suppression change is worth making**, the block's output is
   that conclusion, recorded — and `CQ-012` is closed as *examined and declined*, with the
   measurements as evidence. That is a legitimate result.

**Auditor/Researcher deliverable (this block has no Implementor task)**

| Field | Content |
|---|---|
| `inventory` | One row per suppression: file (semantic path), enclosing class/function, the suppressed error code, and the bucket from constraint 2 |
| `counts` | Bucket totals; must sum to the re-measured total |
| `in_scope` | Which suppressions, if any, sit in the files this plan's own blocks touch (`consent.py`, `context_processors.py`, `cache.py`, `lookup_resolution.py`, `enums.py`, `review.py`, `alerts.py`, `save_search.py`, `saved_searches.py`, `listings_query.py`, `submission.py`) |
| `routing` | One named destination per non-(i)/(ii) bucket: phase 03 BLOCK 11, phase 08, phase 15, or "no destination — declined with rationale" |
| `decision` | A single sentence: *is any suppression change worth shipping in phase 10?* with the evidence |

**Tests required** — none. A block with no diff has no test surface. The inventory is evidence,
not a test.

**Risk and rollback**

- *The real risk:* the inventory is read as a to-do list and 83 suppressions get deleted over the
  following months by whoever picks it up. Mitigation: constraint 4; and the routing column must
  name an owner for every non-(i)/(ii) row rather than leaving it open.
- *Scope risk:* the block becomes a typing project. Mitigation: constraint 1.
- *Rollback:* nothing to roll back. Zero commits is the expected outcome.

---

### B-10 RESULT — CLOSED as *examined and declined* · **zero commits** (2026-10-05)

**`CQ-012` is closed.** Evidence: `.ai/tmp/b10-suppression-inventory.md` (697 rows, re-measured in place).
**No suppression change is worth shipping in phase 10.**

| Bucket | Rows | Destination |
|---|---|---|
| (i) load-bearing | 0 (measured, not assumed) | — |
| (ii) justified — framework gap | **107** | protected; a correction needs a **named** follow-up block |
| (iii) removable | 0 | — |
| (iv) another phase's sweep | 70 | **phase 03 BLOCK 11** (its reservation) |
| **total** | **177** | sums to the re-measured total |

**The scope was wrong by more than 2×, not 20×.** The audit measured `type: ignore` on 83 lines;
the real total is **177** — **80 `# type: ignore`** plus **97 `# pyright: ignore`** across **84
modules** of 656. The 97 pyright-form rows were never counted. Any execution scoped to "the 4
`type-arg` suppressions" would have picked the wrong four out of 177.

**`(i)` and `(iii)` being empty is the finding.** Method: `src/` was copied verbatim and a second
copy with all 177 comments stripped was type-checked **outside the repo tree**; stripping produced
**202 new diagnostics across 656 files, 0 unmatched** — every one lands on a suppression line. So
**all 107 honoured suppressions are load-bearing**, and none became unnecessary because a type became
expressible. The 107 are 96 × django-stubs `transaction.atomic()` `Atomic`, 8 × Django admin
`short_description`, 3 × `ModelAdmin` hook override. The 70 inert rows are inert only because their
checker or diagnostic category is absent from CI (53 mypy-only codes, 2 unflagged framework APIs, 15
rows that exist solely because seven diagnostic categories are globally disabled).

**CI configuration — the plan's assertion was correct.** `ci.yml` runs `ruff check src/` and
`basedpyright src/` (`PYTHONPATH=src:src/backend`). **mypy is in no workflow and is not a dev
dependency**, so `[tool.mypy]`'s `disallow_any_generics` is unenforced and *"type errors went from N
to 0"* is unavailable as evidence. **Correction to the earlier audit: the typecheck gate covers both
`src/backend` and `src/telegram_bot`.**

**`in_scope` — 10 rows.** `lookup_resolution.py` carries 4 × `type-arg` (read *after* `6236f7d0`,
which touched no suppression); `consent.py` carries **one load-bearing** `transaction.atomic()`
suppression — the single highest accidental-deletion risk in this programme, and **not** to be
touched by any consent block. `review.py` (3), `submission.py`, `alerts.py` carry the same
load-bearing django-stubs gap. `context_processors.py`, `cache.py`, `enums.py`, `save_search.py`,
`saved_searches.py`, `listings_query.py`: **zero suppressions**.

**Standing prohibition, now measured rather than assumed:** no phase-10 block may delete a
suppression. Buckets (i) and (ii) are protected; bucket (iv) belongs to phase 03 BLOCK 11.

**Two caveats carried to final validation:**
1. mypy cannot be run here, so whether the 5 `no-redef` rows in `categories/catalog/builder.py` are
   stale is **unverified**.
2. **`basedpyright src/` is red on this working tree — 3 errors, all in test files outside both
   phases' surface**: `search/tests/test_immediate_alerts.py` (1 × `reportOptionalMemberAccess`) and
   `users/tests/test_login.py` (2 × `reportIndexIssue`). Verified independently at the coordinator.
   **No production file is red.** A green baseline must be re-established before any future
   suppression change.

---

### B-11 — One listings-context builder for the two views

| | |
|---|---|
| **Findings owned** | `CQ-015` (MEDIUM, execution risk MEDIUM) — **re-scoped to the shape the tree actually has** |
| **Class** | **behavioural** — one template contract expressed once instead of twice; ~10 test files pin it from both sides |
| **Depends on** | nothing in-plan. **External: phase 08 BLOCK 1 holds `apps/ads/services/listings_query.py`** |
| **Blocks** | `B-12` (`ads/views/listings.py` is both this block's call site and `B-12`'s subject) |
| **Priority** | P2 |
| **Risk level** | **MEDIUM** |
| **Required agents** | **Auditor** (pre-step: enumerate every context key each view publishes — the source plan's "20 shared keys" is stale), **Planner** (owns `Q8`), **Validator** (mandatory — the largest diff in the plan with a near-zero intended behaviour change) |

**The re-scoping matters.** The source plan's premise was a duplicated **20-key raw context
build**. That literal is **gone**: `ListingsQueryParams` in `apps/ads/services/listings_query.py`
is now a **Pydantic `BaseInputModel`** with four field validators, so there is nothing to
de-duplicate at the kwargs level. What is duplicated today is narrower and sharper:

1. Two **independent constructor calls** for the same DTO — one in each view.
2. Two **independent calls** into the same service to obtain the same derived data:
   `ListingsQuery.resolve_filter_options` and `ListingsQuery.active_price_range` are each called
   per view.

And the context has genuinely **shrunk** since the anchor: `dda8af23 (13-PERF-008)` removed a
redundant `cities` query from the request context, and `search.py` now documents that
`header_context` already publishes it. **No key count from the source plan may be quoted.**

**Decision required before implementation — `Q8`: is the shared builder a service module or a
helper beside `ListingsQuery`?**

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | A module-private function in the same `listings_query.py`, beside `ListingsQuery` | **Gains:** zero new artifacts; the builder and the query object it builds live together; the existing service already owns `resolve_filter_options` and `active_price_range`, so nothing new crosses a boundary. **Costs:** it adds one more name to a file **phase 08 owns**, and that file has grown a Pydantic DTO, four validators and six service methods |
| **(b)** | A new module — a context-builder service | **Gains:** a clean owner for the *context* concern, distinct from the *query* concern; a natural home if a third consumer ever appears. **Costs:** a new module for one function with two consumers; it also creates the decision of what it may import, and an import edge between two new-ish service modules |
| **(c)** | No builder — extract only the **DTO construction** into a shared factory and leave each view to publish its own context keys | **Gains:** kills the duplication that is provably identical and leaves the genuinely different keys (the search-only ones) where they are. **Costs:** the *contract duplication* the finding is about — the same template keys assembled in two places — survives |

**The Implementor may not choose.** `Q8` decides whether this block adds a file to another
phase's module or creates one of its own; the source plan recorded it as gated for exactly that
reason.

**File surface (semantic units)**

| File | Symbol / target | Change |
|---|---|---|
| `src/backend/apps/ads/services/listings_query.py` | `class ListingsQueryParams` (a `BaseInputModel`), `class ListingsQuery`, its `PER_PAGE`, `build_queryset`, `_apply_sort`, `active_price_range`, `resolve_filter_options` | Per `Q8`, either gains the shared builder beside them or is read-only and the builder lands in the `Q8`(b) module. **Its four field validators are read-only** |
| `src/backend/apps/ads/views/listings.py` | the view function that constructs `ListingsQueryParams` — **the Auditor pre-step names it** — and the view's context dictionary | Build through the shared entry point. Its context is a **strict subset** of the search view's |
| `src/backend/apps/search/views/search.py` | the view function that constructs `ListingsQueryParams` — **the Auditor pre-step names it** — plus its calls to `resolve_filter_options` and `active_price_range`, and its `header_context` usage | Build through the shared entry point. **The search-only context keys stay search-only** |
| `src/backend/templates/` — the listings and search templates | the blocks that consume the shared keys | **READ-ONLY unless `Q8` forces a rename.** One key-per-line reformatting of a context dictionary is a *consequence* of the change, not a finding, and is not a licence to restyle |
| `src/backend/apps/moderation/views/review.py` | `moderation_review`'s context build | **READ-ONLY reference only.** `B-4`'s `G-4a`(a) may extract the same class of helper there; the two blocks must end up describing one pattern, not two |

**Binding constraints**

1. **Zero intended behaviour change.** Every template key that exists today must exist after,
   with the same name and a compatible value. The tests that pin the contract from both sides are
   the detector.
2. **Search-only keys stay search-only.** Do not publish a key the search template needs on the
   listings view, and do not delete a listings-only key.
3. **Do not resurrect the removed `cities` query.** `13-PERF-008` deleted it on purpose and
   `header_context` already carries it. Re-adding it is a regression.
4. **Phase 08 BLOCK 1 holds `listings_query.py`.** If the file has moved since this plan was
   written, re-read it; if phase 08 has an in-flight edit there, **stop and report.**
5. **One key per line, and no reformatting beyond what the change forces.** The source plan
   recorded this as a consequence; it is not a licence to reformat the file.
6. **No template rename, no template logic.** The builder is Python-side. If a template needs to
   change to accommodate it, `Q8` was answered wrongly — stop and report.

**Implementor task**

```yaml
id: task_24_b11_listings_context_builder
title: "Build the listings and search template context through one shared entry point (10-CQ-015)"
priority: high
depends_on: []
source_reference: ".ai/plans/24-code-quality-remediation-execution.md"
source_section: "B-11 - One listings-context builder for the two views"
source_blocks: ["B-11", "orig BLOCK 14 (CQ-015, re-shaped)"]
description: >
  Two views independently construct the same Pydantic ListingsQueryParams and each independently
  call ListingsQuery.resolve_filter_options and active_price_range, then assemble an overlapping
  template context in two places. ListingsQueryParams is no longer a raw 20-kwarg literal -- it is a
  BaseInputModel with four validators -- so the duplication to remove is the construction call and
  the two service calls per view, plus the shared-key assembly. Build both views' contexts through
  one shared entry point at the recorded Q8 location. Search-only keys stay search-only. The removed
  cities query must not come back.
goals:
  - "both views obtain the DTO and its derived data through one shared entry point"
  - "every template key that exists today still exists, with the same name"
  - "change no key's value semantics and add no key to the listings view that only search uses"
files:
  - path: "src/backend/apps/ads/services/listings_query.py"
    targets:
      - type: class
        name: ListingsQueryParams
      - type: class
        name: ListingsQuery
      - type: method
        name: resolve_filter_options
      - type: method
        name: active_price_range
      - type: method
        name: build_queryset
  - path: "src/backend/apps/ads/views/listings.py"
    targets:
      - type: function
        name: listings          # Auditor pre-step confirms the exact view function name
      - type: module
        name: listings
  - path: "src/backend/apps/search/views/search.py"
    targets:
      - type: function
        name: search            # Auditor pre-step confirms the exact view function name
      - type: module
        name: search
changes:
  - action: add_code
    description: >
      Add the shared context entry point at the recorded Q8 location. It takes the same inputs the
      two views assemble today and returns the shared keys plus the derived data both views already
      compute. Each view then adds its own view-specific keys.
  - action: modify_code
    description: >
      Route both views through the shared entry point. Delete the duplicated ListingsQueryParams
      construction and the duplicated resolve_filter_options / active_price_range calls from the
      views. Keep ListingsQueryParams' four field validators untouched.
  - action: modify_code
    description: >
      Do not re-add the cities query to the listings context. 13-PERF-008 removed it and
      header_context already publishes it.
acceptance_criteria:
  - "neither view constructs ListingsQueryParams independently any more"
  - "every template key present before the change is present after, with the same name and a compatible value"
  - "the listings view gains no search-only key and the search view loses none"
  - "the ~10 existing listing and search template tests are green UNCHANGED"
  - "no cities query is re-added to either context"
  - "no template file needed a change; if one did, the block stops and reports instead"
  - "the commit body records the Q8 option, the enumerated shared-key set, and that no source-plan key count was used"
  - "uv run ruff check, uv run basedpyright are clean; .\\Makefile.ps1 test is green"
tests_to_run:
  - "src/backend/apps/ads/tests/"
  - "src/backend/apps/search/tests/"
```

**Risk and rollback**

- *Contract risk (the real one):* a shared key's value differs subtly between the two views today,
  and unifying it changes what one of them renders. Mitigation: constraint 1; the Validator runs
  both template suites, not just the one being edited.
- *Scope risk:* the diff becomes a reformatting of two large context dictionaries. Mitigation:
  constraint 5.
- *Coordination risk:* phase 08 holds `listings_query.py`. Constraint 4.
- *Rollback:* a straight revert. No migration, no data, no persisted state.

---

### B-12 — One fuzzy ladder, one cutoff

| | |
|---|---|
| **Findings owned** | `CQ-011` (MEDIUM — **a consistency defect, not a recall defect**) |
| **Class** | **behavioural** — changes matching behaviour for a subset of queries |
| **Depends on** | `B-11` (file edge: `ads/views/listings.py` is both `B-11`'s call site and this block's subject), `B-2` (file edge: bare locale literals in the same neighbourhood) |
| **Blocks** | nothing in-plan |
| **Priority** | P2 |
| **Risk level** | **MEDIUM** |
| **Required agents** | **Auditor** (pre-step: re-enumerate every fuzzy site), **Researcher** (owns `Q1`; phase 08 consulted), **Planner** (owns `Q7`), **Validator** (mandatory — a shipped test re-derives the cutoff in-test) |

**Ruling already made — carry it as a constraint.** `Q6` was **RESOLVED 2026-10-03 by the
Product Owner: the unified cutoff is 0.8.** Its consequence is a *reduction* in risk, and the
tree has not yet been told:

- **`test_search_fuzzy.py::TestFuzzyEquivalence` re-derives `0.8` in-test** over its
  `(locale, query)` pairs. Because the ruling *is* 0.8, that test **stays green and stays
  UNCHANGED**, and **project rule 2 is never invoked**. If this block changes that test, **stop and
  report** — rewriting it would reverse a Product Owner decision.
- **The `0.6` site aligns to the shared constant.** That is the entire code change.

**Three fuzzy sites are live, and the report found two.** The audit's re-measurement confirms
three divergent cutoffs across **three** modules: `0.6` in `ads/views/listings.py`'s
`_suggest_category`, `0.8` in `search/views/search.py`, and `0.8` re-derived in
`test_search_fuzzy.py`. Plus `locations/services/city_suggestions.py::suggest_city`, which carries
its own `_CUTOFF = 0.6` for a **different entity**.

**This is not a user-facing recall defect, and the block must not be argued as one.** On
`/search/?category=<slug>` the category is resolved by the **breadcrumb** path and a typo merely
echoes the raw string; the fuzzy ladder is reached only from the **`?q=`** path. The finding
survives as a *consistency and maintainability* defect: two divergent ladders over one
already-shared name list.

**Decision required before implementation — `Q1`: where does the shared ladder live?**

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | Ladder in `apps/categories/services/fuzzy.py`, with the name list **injected** | **Gains:** `categories` owns category resolution, so the ladder belongs there; injecting the list means `categories` never imports `search`. **Costs:** a new module; the injection parameter is an API a caller can get wrong (pass the wrong list) |
| **(b)** | Ladder in `apps/search/services/`, and `ads/views/listings.py` imports from `search` | **Gains:** the ladder sits beside `category_fuzzy.get_active_category_names`, which already owns the cached list it needs — one fewer parameter. **Costs:** **a new `ads → search` edge.** `search` already imports `categories`; this inverts that direction and creates the possibility of a cycle |
| **(c)** | Leave both ladder sites alone; align only the cutoff constant to the `Q6` ruling | **Gains:** the smallest change that satisfies the one decided question; no new module, no new edge. **Costs:** two divergent ladder *shapes* survive — one has an exact-match tier, the other does not — so the inconsistency is halved, not closed |

**Decision required before implementation — `Q7`: does `suggest_city` join the unification?**

`Q7` is **a technical gate, not an owner question**, and the `Q6` ruling sets the bar it must
clear. `suggest_city` matches **cities**, not categories — a different entity, a different
normalisation, and its own `_CUTOFF`. Three outcomes, and **two are acceptable**:

- **(a) it joins** — its `_CUTOFF` becomes the shared 0.8 constant. Cost: city matching changes
  behaviour for every locale.
- **(b) it stays separate** — **and its surviving 0.6 must be justified against the 0.8 product
  decision in the commit body**, as a deliberate entity-specific divergence. **Leaving the value
  in place and saying nothing is not an acceptable outcome**; it is an acceptance criterion.
- **(c) the whole question is deferred** with a named owner. Acceptable only if the commit body
  records the deferral and who owns it.

**File surface (semantic units)**

| File | Symbol / target | Change |
|---|---|---|
| `src/backend/apps/ads/views/listings.py` | **`_suggest_category`**, its `get_close_matches(...)` call carrying `cutoff=0.6` | Align to the shared constant per `Q6`. The **shape** change (an exact-match tier) follows `Q1` |
| `src/backend/apps/search/views/search.py` | **`_fuzzy_category_match`** and **`_fuzzy_match_by_name`**, and the `get_close_matches(...)` call carrying `cutoff=0.8` | The reference implementation. Its ladder shape is what the other site aligns to, per `Q1` |
| `src/backend/apps/search/services/category_fuzzy.py` | **`get_active_category_names`** | **READ-ONLY.** It already owns the shared name list. Per `Q1`(b) the ladder joins it; per `Q1`(a) the list is injected from here |
| `src/backend/apps/locations/services/city_suggestions.py` | **`suggest_city`** and its module-level `_CUTOFF` | Per `Q7`. May end up untouched — with the justification recorded |
| `src/backend/apps/search/tests/test_search_fuzzy.py` | **`TestFuzzyEquivalence`** and the `cutoff=0.8` it re-derives | **UNCHANGED. Non-negotiable.** This is the `Q6` ruling's detector |

**Binding constraints**

1. **The shared name list must stay shared.** Two modules already consume
   `category_fuzzy.get_active_category_names`. Whatever `Q1` decides, one list is loaded, not two.
2. **`categories` must not import `search`.** The existing graph is `search → categories`.
   `Q1`(a) respects it by injection; `Q1`(b) inverts it with a new `ads → search` edge and the
   commit body must state that inversion explicitly, because it is the lasting consequence.
3. **`TestFuzzyEquivalence` is not touched.** Green, unchanged. Project rule 2 is **not** invoked.
4. **A surviving `suggest_city` at 0.6 is only acceptable with the recorded justification.**
   `Q7` may not be answered by silence.
5. **The cutoff is a named constant, not a literal, at every site it survives.** The finding is
   two divergent cutoffs; leaving a literal behind recreates it.
6. **Do not change the name list's contents, its caching, or its normalisation.** This block is
   about the ladder and the cutoff.

**Implementor task**

```yaml
id: task_24_b12_fuzzy_ladder_cutoff
title: "Unify the category fuzzy ladder and apply the 0.8 cutoff ruling (10-CQ-011)"
priority: high
depends_on: [task_24_b11_listings_context_builder, task_24_b02_locale_literals]
source_reference: ".ai/plans/24-code-quality-remediation-execution.md"
source_section: "B-12 - One fuzzy ladder, one cutoff"
source_blocks: ["B-12", "orig BLOCK 15 (CQ-011)"]
description: >
  Two category-fuzzy call sites disagree: ads/views/listings.py's _suggest_category uses cutoff=0.6
  and search/views/search.py uses cutoff=0.8, over one already-shared name list. The Product Owner
  ruled on 2026-10-03 that the unified cutoff is 0.8 -- a ruling that has not yet been applied to
  the tree. Build one ladder at the recorded Q1 location and align both call sites to the shared
  constant. locations/services/city_suggestions.py::suggest_city matches a different entity and is
  governed by the Q7 decision: if it stays at 0.6, the divergence must be justified in the commit
  body. This is a consistency defect, not a recall defect -- do not present it as one.
goals:
  - "both category-fuzzy call sites share one ladder and one named cutoff constant"
  - "the 0.6 site aligns to the ruled 0.8"
  - "the shared name list is still loaded once, from get_active_category_names"
  - "touch TestFuzzyEquivalence not at all"
files:
  - path: "src/backend/apps/ads/views/listings.py"
    targets:
      - type: function
        name: _suggest_category
      - type: function_call
        name: get_close_matches
  - path: "src/backend/apps/search/views/search.py"
    targets:
      - type: function
        name: _fuzzy_category_match
      - type: function
        name: _fuzzy_match_by_name
  - path: "src/backend/apps/search/services/category_fuzzy.py"
    targets:
      - type: function
        name: get_active_category_names
  - path: "src/backend/apps/locations/services/city_suggestions.py"
    targets:
      - type: function
        name: suggest_city
      - type: assignment
        name: _CUTOFF
  - path: "src/backend/apps/search/tests/test_search_fuzzy.py"
    targets:
      - type: class
        name: TestFuzzyEquivalence     # UNCHANGED -- non-negotiable
changes:
  - action: add_code
    description: >
      Create the shared ladder at the recorded Q1 location with the shared cutoff as a named
      module-level constant set to 0.8. Inject the name list if Q1(a) was chosen; consume
      get_active_category_names directly if Q1(b) was chosen.
  - action: modify_code
    description: >
      Point both _suggest_category and the search view's fuzzy helpers at the shared ladder and
      the shared constant. Remove the 0.6 literal and the duplicated ladder shape.
  - action: modify_code
    description: >
      Apply the Q7 decision to suggest_city. If it stays at 0.6, record in the commit body why an
      entity-specific divergence from the ruled 0.8 is correct.
acceptance_criteria:
  - "no category-fuzzy call site carries a bare cutoff literal"
  - "_suggest_category now matches at the ruled 0.8"
  - "get_active_category_names is still the single source of the name list and is still called once per request path"
  - "test_search_fuzzy.py is byte-UNCHANGED and TestFuzzyEquivalence is green -- project rule 2 is not invoked"
  - "if suggest_city keeps 0.6, the commit body justifies the divergence against the 0.8 ruling"
  - "the commit body names the Q1 option and states any dependency-direction change it introduces"
  - "the commit body does not claim a recall or user-facing accuracy improvement"
  - ".\\Makefile.ps1 test is green"
tests_to_run:
  - "src/backend/apps/search/tests/test_search_fuzzy.py"
  - "src/backend/apps/ads/tests/"
  - "src/backend/apps/locations/tests/"
new_tests:
  - "one case proving both call sites resolve the same cutoff from the shared constant (component interaction, not a literal assertion)"
```

**Risk and rollback**

- *Behaviour risk:* raising 0.6 to 0.8 changes which "did you mean" suggestions appear on the
  listings page. That is the **ruled** change, and it is why the ruling was asked for. Mitigation:
  the new case pins that both sites resolve one constant.
- *Test risk:* touching `TestFuzzyEquivalence`. Mitigation: constraint 3 — **stop and report**,
  do not rewrite. A rewrite reverses the Product Owner's decision.
- *Graph risk:* `Q1`(b) introduces an `ads → search` edge where the graph is currently
  `search → categories`. Mitigation: constraint 2 — the inversion is recorded in the commit body
  so a future reader is not surprised.
- *Rollback:* a straight revert. Matching behaviour returns to today's two divergent values.

---

### B-13 — Extract `ad_edit` into the ads service layer

> ## ⛔ THIS BLOCK IS BLOCKED. IT DOES NOT START.
>
> The source plan's own rule: *"If phase 03 BLOCK 5 or phase 05 BLOCKs 2/8 have not landed, BLOCK
> 16 does not start."* Measured at HEAD, **two of five prerequisites are unmet**, and one of the
> two is **exactly the defect the extraction exists to close**. Running it now would encode the
> hole into the new module and make the later fix a second, harder change.

| | |
|---|---|
| **Findings owned** | `CQ-001` **only** (MEDIUM, execution risk **HIGH**). `CQ-008` and `CQ-009` shipped as `10-QLT-001`/`10-QLT-004` — see §1.3 item 3 |
| **Class** | **behavioural**, HIGH |
| **Depends on** | `B-1` (the `ads/services/` package must be a real package first). **Plus two unmet external prerequisites** |
| **Blocks** | nothing in-plan — it is the end of the chain |
| **Priority** | P3, **last**, and only once unblocked |
| **Risk level** | **HIGH** |
| **Required agents** | **Auditor** (pre-step: confirm the unmet preconditions are still unmet *today*), **Researcher** (owns the extraction boundary), **Validator** (mandatory — a source-inspection test with a hard count is the detector) |

**The two unmet prerequisites, precisely**

| Prerequisite | State | Evidence |
|---|---|---|
| **phase 03 BLOCK 5** — `SET LOCAL lock_timeout` inside `ad_edit`'s `atomic()` | **NOT LANDED** | `apps/core/utils/db_lock_timeout.py` contains one symbol, `is_lock_timeout(exc)`. **No `SET LOCAL` statement exists.** What shipped is the *error-boundary* half (`42d0edd8`, `03-DB-004` timeout half B), consumed where the view catches the exception |
| **phase 15 `AUTHZ-007`** — ownership assertion on the **locked** instance, inside `atomic()` | **NOT LANDED for `ad_edit`** | `ad_edit`'s ownership check runs **before** the `transaction.atomic()` block — on the **unlocked** instance. Siblings `ad_archive` and `ad_reactivate` assert ownership **inside** the locked block. **`ad_edit` is the odd one out**, and this is precisely the hole the extraction closes |

The three that **did** land: phase 05 BLOCK 8 (`9adafe35`, an explicit status allow-list replaced
the catch-all), phase 05 BLOCK 2 (`63937ca8`, the publish clock restarts on a price edit), and
`AUTHZ-002`'s target — though the Auditor must confirm `AUTHZ-002`, since `submit_ad` no longer
lives in the web view module at all after the `10-QLT-001`/`004` split.

**What must be true before this block may start** (all four, checked by the Auditor pre-step, all
quoted in the commit body):

1. Phase 03 BLOCK 5's `SET LOCAL lock_timeout` has landed and `ad_edit` uses it.
2. Phase 15 `AUTHZ-007` has landed for `ad_edit` — **the ownership assertion is inside the locked
   block**, matching `ad_archive` and `ad_reactivate`.
3. Phase 05 BLOCKs 2, 8 and 12 are landed and quiescent.
4. The coordinator has sequenced the block against phases 03, 05, 07 and 15.

**The trap the pre-step exists to catch.** `test_edit_views_locking.py::TestEditViewsLocking`
asserts `source.count("select_for_update") == 1` on `ad_edit`'s **own source**. That assertion
passes today *because* the ownership check sits outside the locked block. **Moving the ownership
assertion inside `atomic()` must not introduce a second `select_for_update`.** Any implementor who
adds one will make that test fail in a way that looks like a refactor bug and is actually the
shipped detector working. The bot-side sibling assertion on `submit_ad` is the same shape and must
also survive.

**File surface (semantic units)**

| File | Symbol / target | Change |
|---|---|---|
| `src/backend/apps/ads/views/edit.py` | **`ad_edit`** | Becomes a thin view: parse the request, build the DTO, call the service, translate the service's result into the existing response. Its `ad_archive` and `ad_reactivate` siblings are **not** touched |
| `src/backend/apps/ads/services/edit_ad.py` | **NEW module** | Holds the extracted orchestration: the status allow-list check, the `transaction.atomic()` block, the **single** `select_for_update()` re-fetch, the ownership assertion **inside** the lock, the `AdEditInput` validation and its `ValidationError` handling, and the price/photo `elif` arm. **`apps/ads/services/__init__.py` must exist — that is `B-1`'s output** |
| `src/backend/apps/ads/services/submission.py` | `class AdEditInput`, `class SubmitAdInput` | **READ-ONLY.** Both shipped. `AdEditInput`'s `title`/`description` field constraints are verified by the pre-step, not changed here |
| `src/backend/apps/ads/views/edit.py` | the GET **dispatch** branch inside `ad_edit` | **Not a method guard.** This is the one inline `request.method` check that is a dispatch, not a guard — it is why the source plan assigned it here and not to the retired `CQ-018` mechanical block |
| `src/backend/apps/ads/tests/test_edit_views_locking.py` | **`TestEditViewsLocking`**, its `ad_edit` source-inspection assertions, and the `submit_ad` sibling assertion | **Re-pointed** at the new module, **assertions unchanged** |
| `src/telegram_bot/handlers/ad_create/submit.py` | `submit_ad` | **READ-ONLY.** Already extracted into the shared service by `10-QLT-001`. This block does not touch the bot tier |

**Binding constraints**

1. **Exactly one `select_for_update()` survives, inside the `atomic()` block, in the new module.**
   The count is not negotiable and the re-pointed test is the proof.
2. **The ownership assertion moves inside the lock and nowhere else.** This block does not
   *introduce* that fix — it is prerequisite 2 above, and it must already be landed. If the
   pre-step finds it not landed, **the block is cancelled, not reshaped.**
3. **`AdEditInput.model_validate` gains an explicit `ValidationError` handler** whose behaviour is
   the open gate `Q3` below. Today the exception escapes from inside `transaction.atomic()` with
   no handler.
4. **`SubmitAdInput.user_id` is `request.user.id`, never `ad.user_id`.** `AUTHZ-002` guards that
   field. If it is ever built from `ad.user_id`, the guard becomes tautological on the web path
   *and looks load-bearing* because both branches share it.
5. **No `ErrorPage` enum, no `_build_submit_input` helper.** Both were proposed by the report and
   rejected twice. `HttpResponseForbidden` and `HttpResponse(status=400)` are self-describing.
6. **`ad_edit`'s response contract does not change**, apart from the `Q3` decision. The existing
   edit-view tests pin it.
7. **One commit.** `CQ-001` is a single extraction into a single new module. It is not bundled
   with the `Q3` handler, with any `min_length` clause, or with any cleanup: if the commit needs a
   second subject, the second subject is a separate block.

**Decision required before implementation — `Q3`: what does the edit endpoint return on a Pydantic
`ValidationError`?**

Today `AdEditInput.model_validate` raises inside `transaction.atomic()` with **no handler**, so
the response is a **500**. The report does not mention this. Three options:

| Option | What it is | Consequences |
|---|---|---|
| **(a)** | **400** with a translated message | **Gains:** correct by REST convention; no template change; cheapest. **Costs:** a bare 400 page where the seller was mid-edit loses everything they typed |
| **(b)** | Re-render `ads/edit.html` with the error, preserving the submitted values — the `ads/edit.html` error slot already exists as the `"error"` context key | **Gains:** consistent with `Q2`'s ruling on the sibling moderation boundary and with what a seller expects from a form. **Costs:** the largest option; the form's values must survive the round trip; two new translated strings |
| **(c)** | Keep the 500 | **Gains:** nothing. **Costs:** a malformed POST is a server error. Listed only so the Implementor does not treat "no change" as neutral — while this block is blocked, the 500 **stays live**, and that exposure is a coordinator acceptance, not a neutral default |

**The Implementor may not choose.** This plan does not pick: all three are defensible, and the
choice is a response-shape decision.

**Implementor task**

```yaml
id: task_24_b13_ad_edit_service_extraction
title: "Extract ad_edit into apps/ads/services/edit_ad.py (10-CQ-001)"
priority: low
status: blocked            # four unmet preconditions -- see the block header
depends_on: [task_24_b01_packaging_and_export_hygiene]
blocked_by_external:
  - "phase 03 BLOCK 5 -- SET LOCAL lock_timeout inside ad_edit's atomic()"
  - "phase 15 AUTHZ-007 -- ownership assertion on the locked instance, inside atomic()"
  - "phase 05 BLOCKs 2, 8, 12 landed and quiescent"
  - "coordinator sequencing against phases 03, 05, 07, 15"
source_reference: ".ai/plans/24-code-quality-remediation-execution.md"
source_section: "B-13 - Extract ad_edit into the ads service layer"
source_blocks: ["B-13", "orig BLOCK 16 (CQ-001 only)"]
description: >
  ad_edit is the most contended function in the repository: phases 03, 05, 07 and 15 all point at
  it, and shipped commits 10-QLT-001 and 10-QLT-004 already moved submit_ad's orchestration into
  apps/ads/services/submission.py and made ad_edit delegate its text-edit to it. What remains is
  ad_edit itself: extract it into apps/ads/services/edit_ad.py, keeping exactly one
  select_for_update() inside the transaction.atomic() block, keeping the ownership assertion inside
  the lock, and giving AdEditInput.model_validate the explicit ValidationError handler the Q3
  decision requires. This block is BLOCKED until phase 03 BLOCK 5 and phase 15 AUTHZ-007 have
  landed; the unmet ownership assertion is precisely the hole this extraction closes.
goals:
  - "move ad_edit's orchestration out of the view into apps/ads/services/edit_ad.py"
  - "keep exactly one select_for_update(), inside the atomic() block"
  - "keep the ownership assertion inside the locked block"
  - "handle AdEditInput ValidationError per the recorded Q3 decision"
  - "change no response contract beyond that decision"
files:
  - path: "src/backend/apps/ads/services/edit_ad.py"
    targets:
      - type: module
        name: edit_ad            # NEW
  - path: "src/backend/apps/ads/views/edit.py"
    targets:
      - type: function
        name: ad_edit
      - type: function
        name: ad_archive          # READ-ONLY
      - type: function
        name: ad_reactivate       # READ-ONLY
  - path: "src/backend/apps/ads/services/submission.py"
    targets:
      - type: class
        name: AdEditInput         # READ-ONLY
      - type: class
        name: SubmitAdInput       # READ-ONLY
  - path: "src/backend/apps/ads/tests/test_edit_views_locking.py"
    targets:
      - type: class
        name: TestEditViewsLocking   # RE-POINTED; assertions unchanged
changes:
  - action: add_code
    description: >
      Create apps/ads/services/edit_ad.py holding ad_edit's orchestration: the status allow-list
      check, the transaction.atomic() block, the single select_for_update() re-fetch, the ownership
      assertion INSIDE the lock, the AdEditInput validation, and the price/photo elif arm.
  - action: modify_code
    description: >
      Reduce ad_edit in the view module to request parsing, DTO construction (SubmitAdInput.user_id
      is request.user.id, never ad.user_id), the service call, and response translation.
  - action: modify_code
    description: >
      Add the explicit ValidationError handler for AdEditInput.model_validate per the recorded Q3
      option, so a malformed POST produces the decided response instead of a 500.
  - action: modify_code
    description: >
      Re-point TestEditViewsLocking at the new module. Keep the select_for_update count assertion
      and the submit_ad sibling assertion exactly as they are.
acceptance_criteria:
  - "all four external preconditions are confirmed landed, and each is quoted in the commit body with its commit sha"
  - "exactly one select_for_update() exists in the extracted function, inside the atomic() block"
  - "the ownership assertion is inside the locked block, matching ad_archive and ad_reactivate"
  - "TestEditViewsLocking is green with its assertions unchanged, re-pointed at the new module"
  - "the bot-side submit_ad source-inspection assertion is green and untouched"
  - "an invalid AdEditInput POST produces the Q3-decided response, not a 500"
  - "SubmitAdInput.user_id is request.user.id"
  - "ad_archive and ad_reactivate are byte-unchanged"
  - "no ErrorPage enum and no _build_submit_input helper exist"
  - "no migration; the edit-view suite is green UNCHANGED apart from the re-pointed class"
  - ".\\Makefile.ps1 test is green"
tests_to_run:
  - "src/backend/apps/ads/tests/test_edit.py"
  - "src/backend/apps/ads/tests/test_submission.py"
  - "src/backend/apps/ads/tests/test_edit_views_locking.py"
```

**Tests required** — one class re-pointed, **no assertion changed, no test deleted**:
`TestEditViewsLocking` inspects `ad_edit`'s source. A relocation changes the source, so the class
must follow the function to its new module with its `select_for_update` presence/count and its
`atomic()` assertions intact. The bot-side `submit_ad` assertion is **not** re-pointed (that
function did not move) and must be green unchanged. One new case is warranted and only one: the
`Q3` response for a malformed POST, asserting the **status**, not the traceback.

**Risk and rollback**

- *The blocking risk:* running this block before its preconditions land would **move the
  pre-lock ownership check into a service module**, which reads as a fix and is not one. The
  header's four preconditions exist to make that impossible.
- *Detector risk:* a second `select_for_update` turns `TestEditViewsLocking` red in a way that
  looks like a refactor defect. **That is the shipped detector working.** The correct response is
  to re-read the count constraint, never to relax the assertion.
- *Behaviour risk:* the extraction changes a response. Mitigation: `Q3` is gated and the
  edit-view suite is the net.
- *Rollback:* a straight revert — **and this is the one block where a partial revert is
  meaningless.** The extraction is one commit or nothing; a half-moved `ad_edit` leaves the
  locked instance and the view's call site disagreeing about who owns the transaction.

---

## 4. Gates

**Fourteen gates existed at the source plan's anchor. Eleven are open or routed here, two are
already resolved and have become block constraints, and three are moot.** Every open gate is
labelled *decision required before implementation*, carries its options and consequences, and
names who decides. **This plan chooses no option anywhere technical uncertainty exists.**

### 4.0 RULINGS — recorded 2026-10-05 · **all gates below are CLOSED**

**Product Owner, 2026-10-05.** One owner gate and three coordinator gates are now decided. The
remaining open gates are decided by the Planner during execution, and the Planner takes the
**recommended option** on each: a standing instruction was given to stop interrupting the owner
and to decide technical gates on the recommendation. **A gate may still be escalated only when the
recommended option is genuinely unsafe, not merely inconvenient.**

| Gate | **RULING** | Binding consequence |
|---|---|---|
| **`Q12`** response shape | **OPTION (b) — re-render the save-search surface with an error and preserve the user's submitted values.** The bare `400` (option i/a) is **DECLINED**; the clamp-and-store option is **DECLINED** as a regression. | `B-7` re-renders. The user's query and filters survive a rejected price. **Cost accepted:** a new user-visible error string with **non-empty `ru` AND `bs` `msgstr`**, and a new context key on a template phase 08 owns. **Consistency:** this is the *same* treatment the Product Owner ruled for the moderation form on 2026-10-03 (`Q2`), so every form in the product now fails the same way |
| **`Q12`** placement *(technical)* | **OPTION (a) — a new `src/backend/apps/search/schemas.py`**, matching `apps/media/schemas.py`, `apps/users/schemas.py` and `telegram_bot/schemas/`. `apps/core/schemas.py` is rejected: a search-app DTO does not belong in the shared base module | `B-7` adds exactly one new file. Follows the established house pattern (`BaseInputModel`, commit `33345c96`) |
| **`Q11`** vocabulary | **OPTION (A) — `10-CQ-0NN` for every new commit**, plus a mandatory `xref:` line in each commit body naming the superseding `10-QLT-###` work where it applies | Affects **commit messages only**. For ~12 new commits the repo carries two schemes; the `xref:` line is what makes the relationship machine-readable. §2.3's `xref` requirement is now **mandatory, not advisory** |
| **`Q5`** external importer | **NO external importer exists.** This is a private single-repo product with no published package surface and no consumer outside this repository. The in-repo half is already proven (zero importers) | `B-6` **deletes** the three `RESOLVED_*_PREFIX` aliases. The source comment claiming "external callers" is **stale and is deleted with them** — project rule 2 (code is king over a comment) applies because the question has now been asked |
| **`G-9`** `PLC0415` | **CONFIRMED DROPPED.** `PLC0415` stays out of `select` for this programme. At **869** sites the exclusion list *is* the change | No block. If it is ever revisited it must arrive with a **baseline file** (`ruff-linter` baseline or equivalent), never an inline `# noqa` sweep and never a hand-written `per-file-ignores` list of 869 entries |

**Still open, decided by the Planner during execution — recommended option stands:**
`Q9` (enum mapping style), `G-4a` (reject-form re-render mechanism), `Q13` (cookie-constant
destination), `Q1` (fuzzy-ladder home), `Q7` (`suggest_city` cutoff), `Q8` (listings context
builder shape), `Q3` (`ad_edit` validation response).

**`Q3` is the exception that must stay open even after `B-13` unblocks**: it is a response-shape
decision on a user-facing endpoint, and the fix for the live 500 must not be chosen by whoever
happens to unblock it.

### 4.1 Open gates — carried, one per block

| ID | Gate | Block | Who decides | Why it cannot be an Implementor choice |
|---|---|---|---|---|
| **`Q9`** | Do `LanguageLocale.fts_config` / `.fts_vector_field` become enum-keyed `Final` mappings, `match` arms, or stay as-is? | `B-2` | **RULED 2026-10-05 — option (a), see §4.0** | Resolved. One representation, and `KeyError`-free for a valid member, which is strictly better than today's silent `KeyError` |

**Additional rulings recorded 2026-10-05** (standing instruction: take the recommended option):

| Gate | **RULING** | Binding consequence |
|---|---|---|
| **`Q9`** enum mapping style | **OPTION (a)** — `Final` mappings keyed on the enum members (`{LanguageLocale.RUSSIAN: "russian", …}`), read via `LanguageLocale.X.value` at the consumer. Option (b)'s extra enum methods are **DECLINED** (more surface for the same pairing); option (c) is **DECLINED** (it ships the docstring half of `CQ-006` and none of its substance) | **`B-2`.** **Implement as post-class `Final` assignments, NOT dicts inside the class body** — `StrEnum` members are defined in that same body, so an in-class dict referencing them is a construction-order trap (flagged by the source plan's option (b) cost). The properties keep their names and stay read-only. **The pairings are immutable** — `test_search_triggers.py` is the detector |
| **`Q13`** cookie-constant destination | **OPTION (a)** — move the `CONSENT_*` names **into** `apps/core/middleware/preferred_city.py`, beside `PREFERRED_CITY_COOKIE_NAME` / `_MAX_AGE`. Option (b)'s new `apps/core/cookies.py` is **DECLINED** (a new module for seven constants, against project rule 5); option (c) is **DECLINED** (it inverts the dependency — views and context processors would import from a *view* module, which is the defect being fixed) | **`B-5`.** Zero new artifacts, and `consent.py` plus `preferred_city.py` already share that module, so the import graph does not change. **Still one home, not two** — no re-export left behind |
| **`G-4a`** reject-form mechanism | **OPTION (a)** — a shared context builder that re-renders the review page with the moderator's typed input preserved | **`B-4`.** Consistent with the `Q2` ruling's requirement that the typed input survive. **Blocked until plan 19 lands**, which owns the same template |
| **`Q5`** | Do the three `RESOLVED_*_PREFIX` aliases have an **external** importer? | `B-6` | **RULED 2026-10-05 — see §4.0: NO external importer exists** | Answered. `B-6` deletes the aliases *and* the stale "external callers" comment |
| **`G-4a`** *(new)* | How does `reject_ad` re-render the review page **with the moderator's typed input preserved** — a shared context builder, or `messages` + redirect with the input carried? | `B-4` | **Planner**, with **plan 19's owner** consulted (the template collision) | A shipped precedent exists on one side (plan 19 established `messages` renders on this surface) and a Product Owner constraint on the other (the typed input must survive). Both cannot simply be combined by an implementor, and the answer decides whether `review.html` gains markup |
| **`Q13`** | Do the `CONSENT_*` names move into `preferred_city.py`, into a new `apps/core/cookies.py`, or stay put with imports from the view? | `B-5` | **Planner** | Zero-artifact relocation versus a new module for seven constants. Project rule 5 cuts both ways and someone other than the implementor has to weigh it |
| **`Q12`** | Where does the saved-search input DTO live, and what is the error response shape — 400, or a re-render with submitted values preserved? | `B-7` | **RULED 2026-10-05 — see §4.0.** Response shape = **(b) re-render with values preserved**; placement = **(a) `apps/search/schemas.py`** | Resolved. The 400 reading and the clamp-and-store option are both declined. New user-visible string, so `ru` **and** `bs` `msgstr` must be non-empty in the same commit |
| **`Q1`** | Where does the shared category-fuzzy ladder live, given `category_fuzzy.get_active_category_names` already owns the cached list and `search → categories` is the existing direction? | `B-12` | **Planner + Researcher**, with **phase 08** consulted (it owns that neighbourhood) | It decides the block's file set, its dependency-direction consequences and its test blast radius. Option (b) inverts a graph edge |
| **`Q7`** | Does `suggest_city` (a different entity, its own `_CUTOFF = 0.6`) join the unification, or stay separate? | `B-12` | **Planner** | `Q7` is a technical gate, not an owner question, and the `Q6` ruling set the bar it must clear. **It may not be answered by leaving the value in place and saying nothing** |
| **`Q8`** | Is the listings context builder a helper beside `ListingsQuery`, or a new service module? | `B-11` | **Planner**, with **phase 08** (it holds `listings_query.py`) | One more function in another phase's file versus a new module of this plan's own |
| **`Q3`** | What does the ad-edit endpoint return on a Pydantic `ValidationError` — 400, re-render, or keep the 500? | `B-13` | **Planner** (the edit template's `"error"` context slot already exists, which is what makes option (b) cheap) | It is a response-shape decision, and the report never raised it. While `B-13` stays blocked, the 500 stays live — an exposure the coordinator accepts knowingly, not a neutral default |

### 4.2 Open gates with no block — routed, not implemented

| ID | Gate | Who decides | Why there is no block |
|---|---|---|---|
| **`Q11`** | Which citation scheme does phase 10 use, given `10-QLT-###` already exists in 18 shipped commits and 30 in-source markers? | **RULED 2026-10-05 — §4.0: option (A), `10-CQ-0NN` + mandatory `xref:` body line** | Affects **commit messages only**. §4.0 makes the `xref` requirement **mandatory** |
| **`G-9`** *(new)* | If `PLC0415` is ever enabled, what is the **exclusion strategy**? | **RULED 2026-10-05 — §4.0: CONFIRMED DROPPED** for this programme; if revisited it requires a **baseline file**, never a 869-entry `per-file-ignores` list and never an inline `# noqa` sweep | At **869** sites the exclusion list is the entire change. This plan ships **no** `PLC0415` block |
| — | The lock-timeout policy for a bot-side row lock in an extracted service (phase 03 BLOCK 5's `SET LOCAL` half has not landed) | **Coordinator**, with **phase 03** | Gates `B-9` as an external ordering. The *code* half is in `B-9`; only the policy decision is external |
| — | Ordering against **plan 19 `B-2`**, which owns `review.ban_user` and may own a notice in the same template | **Coordinator** | Gates `B-3` (file edge) and constrains `B-4` (template edge). Neither phase may negotiate it directly |

### 4.3 Resolved gates — now block **constraints**, not questions

| ID | Ruling | Where it binds |
|---|---|---|
| **`Q2`** | **Product Owner, 2026-10-03.** On an invalid `reason_category`: **re-render the review page with an error and preserve the moderator's typed input.** The 400 reading is **declined**; nothing is coerced to empty; no arbitrary client string reaches `ModeratorActionLog.reason`; no audit row for a rejected request | `B-4`, binding constraint 2 |
| **`Q6`** | **Product Owner, 2026-10-03.** The unified fuzzy cutoff is **0.8**. Consequences: `TestFuzzyEquivalence` stays **green and unchanged**; project rule 2 is **never invoked**; the `0.6` site aligns to the shared constant | `B-12`, binding constraints 3–4. **The ruling has not yet been applied to the tree — applying it is `B-12`'s code change** |

### 4.4 Gates dropped as moot

| ID | Why it is gone |
|---|---|
| **`Q4`** | Its subject no longer exists. `reject_ad` and `ban_user` already stack `@require_POST` on `@staff_required`, so the "302 on GET versus 405" question has no referent. Shipped as `09-API-010` |
| **`Q10`** | Its subject no longer exists. `Q10` chose between a context processor and a per-view context key **to expose `AdStatus` to templates** — and there is no `AdStatus.` token in any template. With the `CQ-005` half moot, `Q10` is moot, and **this plan adds no context key at all** |
| **`Q14`** | Its subject no longer exists. `Q14` chose whether `PriorityScore` keeps mapping compatibility — and `PriorityScore` was never in scope for this re-scoped `B-10`, which ships **no code**. There is nothing left for `Q14` to decide |

---

## 5. Required tests

**No block adds a test where there is no behaviour to pin.** The rules the source plan set, and
this plan keeps:

- A test may not assert a **line number**, an introspected count that is not a documented
  invariant, a literal private name, a template-string substring, or the **mere presence of a
  symbol**. Absence in particular is never a contract.
- A **source-inspection test is re-pointed, never deleted**, and its assertion is not relaxed
  when it goes red — a red structural assertion is the detector working.
- **Project rule 2 (production code is king) is invoked exactly once in this whole plan**, and
  not at all: `B-12`'s cutoff alignment is the *ruled* change, so `TestFuzzyEquivalence` stays
  green and no test is rewritten.

### 5.1 Per-block test matrix

| Block | New tests | Existing tests that must stay **green unmodified** | Tests to **re-point** (same commit) | i18n obligation |
|---|---|---|---|---|
| `B-1` | **none** | `test_ad_data_locale.py`; the `cache.py` consumers under `apps/categories/tests/` | none | no |
| `B-2` | **none** | `test_search_triggers.py` (**pins the FTS pairings**); `test_ad_data_locale.py`; `test_callbacks.py` | none | no |
| `B-3` | **none** | `test_moderation_views.py` (**already pins the redirect targets**); the analytics dashboard suite | none | no |
| `B-4` | (a) an invalid `reason_category` writes **no** audit row, re-renders the page, preserves the typed category and comment; (b) one parametrised case **per `CategoryRejectReason` member** is accepted — the drift detector between the enum and the template's option values | the **four** existing reject tests, which post `reason_category="spam_scam"`; `TestModerationReviewLocking`; `test_moderation_log.py` | none — but `TestModerationReviewLocking` **must survive** any `G-4a`(a) restructuring | **yes** — one new error string, non-empty `ru` + `bs` |
| `B-5` | **none** | `test_consent_context.py` (**asserts the processor's output for every cookie combination**); `test_consent.py`; both preferred-city suites | none | no |
| `B-6` | **none** — and none deleted | every suite that could reference a deleted symbol; the fast gate is the detector | none | no |
| `B-7` | (a) one case per DTO field — a malformed value is rejected **and** the coercion semantics of the old closures are preserved; (b) a rejected POST creates **no** `SavedSearch` row; (c) a valid POST persists exactly as before | the four existing saved-search tests; **`test_save_search_url_resolves`** (asserts the resolved view's `__name__` is `save_search`) | none | **only if** `Q12`(ii) — two new strings, non-empty `ru` + `bs` |
| `B-8` | **none** — and explicitly **no test asserting the prompt text**, which would re-pin the string being corrected | `test_unsubscribe.py`; `test_i18n_completeness.py` | none | **yes** — one msgid changes, non-empty `ru` + `bs` |
| `B-9` | **none** | `test_unsubscribe.py::TestResolveOwnedLocking`'s **assertions**; the immediate-alerts and `apps/search` suites | **`test_unsubscribe.py::TestResolveOwnedLocking`** — the inspected symbol moves to `telegram_bot/services/alerts.py`; count-based expectations unchanged | no |
| `B-10` | **none** — a block with no diff has no test surface | n/a | n/a | no |
| `B-11` | **none** | **~10 listing and search template test files**, pinning the context contract from both sides. The Validator runs **both** suites, not only the edited one | none | no |
| `B-12` | (a) both fuzzy call sites resolve the **same shared constant** — a component-interaction case, not a literal assertion | **`test_search_fuzzy.py::TestFuzzyEquivalence`** — byte-unchanged, green; the listings and locations suites | none | no |
| `B-13` | (a) one case asserting the **status** of the `Q3`-decided response for a malformed `AdEditInput` POST — the status, never the traceback | `test_edit.py`; `test_submission.py` (`extra=forbid` cases) | **`test_edit_views_locking.py::TestEditViewsLocking`** — the inspected function moves to `apps/ads/services/edit_ad.py`; the `select_for_update` presence/count and `atomic()` assertions **unchanged**. The bot-side `submit_ad` assertion is **not** re-pointed and must be green as-is | **only if** `Q3`(b) |

### 5.2 The four live source-inspection clusters

All four are confirmed live by the audit. **Every block that moves a function names the cluster it
must re-point, in its own commit.**

| Cluster | Re-pointed by | Asserts | The failure mode to recognise |
|---|---|---|---|
| `apps/ads/tests/test_edit_views_locking.py::TestEditViewsLocking` | `B-13` | `select_for_update` **present** in `ad_edit`, its **count is exactly 1**, and `atomic()` present; a sibling assertion on `submit_ad` | A second `select_for_update` fails it. That is the detector, not a refactor defect |
| `telegram_bot/tests/test_unsubscribe.py::TestResolveOwnedLocking` | `B-9` | `_resolve_owned`'s locking shape | A "tidied" query or a moved lock fails it on a commit that changed no behaviour |
| `apps/moderation/tests/test_moderation_views.py::TestModerationReviewLocking` | **nobody** — it survives `B-3` and `B-4` unmodified | `reject_ad` / `ban_user` locking shape | Survives a decorator swap; **dies on a restructure**. If `B-4`'s `G-4a`(a) restructures `moderation_review`, this class is the tripwire |
| **`TestBulkLockingStructure`** | **nobody in this plan** | `select_for_update` + `order_by` + `pk` + `transaction.atomic` in the bulk moderation actions | **The source plan names the wrong module** — it says `api_bulk.py`. It lives in `apps/moderation/tests/test_admin_actions.py` and inspects `apps/moderation/admin_actions.py`. That file is **plan 19's** (`B-1` chose *extend in place*). **Phase 10 has no block on it** |

---

## 6. Risks and rollback

Severity here is **this Planner's assessment of execution risk for the change**, not the
finding's severity. *Contention* = shared files. *Behaviour* = observable response change.
*Corpus* = global or cross-cutting edit. *Process* = the plan is executed wrongly.

### 6.1 Per-block risk register

| Block | Risk | Kind | Likelihood | Impact | Containment / detection | Rollback |
|---|---|---|---|---|---|---|
| **All** | An implementor works from the **source plan's** file list and builds a `telegram_bot/services/login.py`, an `apps/categories/services/fuzzy.py`, an `AdvisoryLockId` reorder, or the `admin_actions.py` move | Process | **Med** | **High** | §1.2 lists all five as moot with the evidence; §8 lists them as forbidden; every affected block's binding constraints repeat the prohibition. `login.py` shipped as phase 01 `ENT-005`; the move happened to a *third* path | straight revert |
| **All** | A block starts with its gate unanswered, or the implementor picks an option | Process | Med | **High** | §4 carries 11 open/routed gates, each with a named decider; every task YAML names its gate; §9.1 checks a **written** answer exists before each block starts | block does not start |
| **All** | The wrong module is cited because the source plan is followed instead of the tree | Process | **High** | Med | Every file surface in §3 is a re-derived path; the audit's block table is quoted in §1.1 so a mismatch is visible at review | straight revert |
| `B-1` | Removing the `__all__` entry breaks a wildcard importer | Behaviour | Low | Med | Constraint 1 + the Auditor's wildcard-import proof; the fast gate detects | straight revert |
| `B-1` | The new `__init__.py` re-exports and creates an import cycle | Contention | Low | **High** | Constraint 2 — empty or a one-line docstring, nothing else | straight revert |
| `B-2` | An FTS pairing value is altered by accident | Behaviour | Low | **High** | Constraint 1; `test_search_triggers.py` fails unambiguously and cannot be mistaken for a style change | **revert, not hotfix** — a wrong pairing degrades search silently |
| `B-2` | `apps/core/enums.py` moved under the implementor | Contention | Med | Med | Constraint 4 — re-read before editing, stop if changed. Seven post-anchor commits plus `10-QLT-002`'s `ConsentVersion` | straight revert |
| `B-2` | The block grows into a tree-wide locale sweep | Corpus | Med | Low | The pre-step enumerates the set; the commit body publishes it; growth is a new finding, not a bigger block | straight revert |
| `B-3` | `reverse()` raises `NoReverseMatch` at request time | Behaviour | Low | Med | Constraint 5 — both admin URL names are resolved **before** the edit; the block stops if either fails | straight revert |
| `B-3` | Collides with **plan 19 `B-2`** on `ban_user` | Contention | **High** | Med | Constraint 1 — external ordering, coordinator-sequenced; the pre-step confirms which `ban_user` body is present | straight revert; re-sequence |
| `B-4` | The invalid path writes an audit row, or returns 400 | Behaviour | Low | **High** | Acceptance criteria 1–3 are the detector; a **Validator is mandatory** | **no partial rollback** — half of this block is worse than none |
| `B-4` | `G-4a`(a) restructures `moderation_review` and disturbs `TestModerationReviewLocking` | Behaviour | Med | **High** | The class is in `tests_to_run` and must be green **unmodified**; a red class means `G-4a`(a) was wrong — re-decide the gate | re-decide `G-4a`, revert |
| `B-4` | A new msgid ships with empty `ru`/`bs` | Behaviour | Med | Med | Constraint 7; `test_i18n_completeness.py` is inside the fast gate | straight revert |
| `B-5` | A cookie name changes and anonymous consent breaks silently | Behaviour | Low | **High** | Constraint 1 — byte-identical by contract; ~40 assertions across five files pin the names and values | straight revert |
| `B-5` | A stale re-export leaves two homes for the same name | Process | Med | Low | Constraint 3 — one home, not two | straight revert |
| `B-6` | The `Q5` answer is wrong and an external consumer breaks | Behaviour | Low | **High** | The gate. **The only deletion in the plan with a stated external surface, and the only one that waits** | straight revert |
| `B-6` | A zero-reference claim misses a dynamic reference | Behaviour | Low | Med | Constraint 2's expanded search (templates, `__all__`, package `__init__`, settings, seed) | straight revert |
| `B-6` | The block becomes a general dead-code sweep | Corpus | Med | Low | A closed list of five symbols. Anything else is a new finding | straight revert |
| `B-7` | The DTO rejects something a real user sends today | Behaviour | Med | **High** | The DTO's coercion semantics are the closures' semantics, copied exactly; the happy-path case is explicit; the four existing tests are the net | straight revert |
| `B-7` | A template, a second DTO, or a `PreferredCityInput` creeps in | Corpus | Med | Low | Constraints 1 and 5 | straight revert |
| `B-9` | A moved function's query or lock shape drifts | Behaviour | Med | **High** | Constraints 1–2; the re-pointed `TestResolveOwnedLocking` is the detector; **Validator mandatory** | straight revert |
| `B-9` | The block absorbs the `contact`/`support` import hoists | Corpus | Med | Low | Constraint 3 — both are phase 09's | straight revert |
| `B-10` | The inventory is read as a to-do list and 83 suppressions get deleted piecemeal | Process | **High** | Med | Constraint 4 — every non-(i)/(ii) row must name an **owner**; "no claim of type-safety improvement" is forbidden in any commit message | nothing to roll back |
| `B-10` | The block becomes a typing project | Corpus | Med | Med | Constraint 1 — no suppression is edited; the deliverable is a table | nothing to roll back |
| `B-11` | A shared key's value differs subtly between the views and unifying it changes one rendering | Behaviour | Med | **High** | Constraint 1; the **Validator runs both** template suites | straight revert |
| `B-11` | The diff becomes a reformatting of two large context dicts | Corpus | **High** | Low | Constraint 5 — one key per line, nothing beyond what the change forces | straight revert |
| `B-11` | Collides with **phase 08** on `listings_query.py` | Contention | Med | Med | Constraint 4 — re-read, stop if phase 08 has an in-flight edit | straight revert; re-sequence |
| `B-12` | `TestFuzzyEquivalence` is edited | Process | Low | **High** | Constraint 3 — **stop and report**. A rewrite reverses a Product Owner decision | **do not revert silently — escalate** |
| `B-12` | `Q1`(b) introduces an `ads → search` edge where `search → categories` exists | Contention | Med | Med | Constraint 2 — the inversion is recorded in the commit body so the next reader is not surprised | straight revert |
| `B-12` | Raising `0.6` → `0.8` changes visible "did you mean" suggestions | Behaviour | **Certain** | Low | **This is the ruled change.** The ruling was asked for precisely to authorise it | straight revert |
| `B-13` | It runs before its preconditions and **moves the pre-lock ownership check into a service module**, which reads as a fix and is not one | Behaviour | Med | **HIGH** | The four preconditions, all verified by the Auditor pre-step and quoted with shas in the commit body. **If precondition 2 is unmet the block is cancelled, not reshaped** | straight revert |
| `B-13` | A second `select_for_update` turns `TestEditViewsLocking` red and looks like a refactor bug | Behaviour | Med | Med | Recognise it as the shipped detector. **Re-read the count constraint; never relax the assertion** | straight revert |
| `B-13` | The extraction changes an ad-edit response | Behaviour | Med | **High** | `Q3` is gated; the edit-view suite is the net; one commit, no bundled subjects | straight revert — and a partial revert is meaningless here |

### 6.2 Top-level sequenced risk list, in the order the risks actually bite

1. **`R0' — `B-13` executes against an unmet precondition.** *The single highest-value finding in
   this re-plan.* `ad_edit`'s ownership assertion sits **outside** the `transaction.atomic()`
   block, on the unlocked instance, while `ad_archive` and `ad_reactivate` assert ownership
   **inside** the lock. Phase 15's `AUTHZ-007` has not landed for `ad_edit`, and phase 03 BLOCK 5's
   `SET LOCAL lock_timeout` has not landed at all. **Mitigation: the block is `status: blocked`
   with four named preconditions, and it is last.** *Residual: while blocked, the ownership hole
   and the 500-on-invalid-POST are both live — a coordinator acceptance, recorded in §4.1 `Q3`.*
2. **`R1' — `PLC0415` is enabled as written and reds the lint gate.** *Closed by deletion, not by
   planning.* 869 sites against a plan written for 96. The load-bearing deferral in
   `moderation/views/review.py` (the view→service indirection plan 19 and phase 09 both rely on)
   is one of the 869, and a bulk `# noqa` sweep is not a fix. **Mitigation: no block; routed as
   `G-9`, where the exclusion strategy is a coordinator tooling decision.** *Residual: the debt
   is real and unowned until `G-9` is answered.*
3. **`R2' — a re-scoping is read as "the audit was wrong" and the moot verdicts get re-litigated.**
   *Mitigation:* §1.2 states each moot verdict with its evidence, and §1.3 states the three places
   this plan **corrects** the audit rather than merely accepting it. §1.3 item 1 is the load-bearing
   one: `CQ-003` is live and carries a Product Owner ruling, so retiring it as "premise rot" would
   discard a decision made after the anchor.
4. **`R3' — cross-phase collision on `review.py`.** Three plans now touch it: this one (`B-3`,
   `B-4`), plan 19 (`B-2` owns `ban_user`), and — for the template — plan 19's notice surface.
   *Mitigation:* hard external edges, coordinator-sequenced; `B-3` before `B-4`; both after plan 19
   `B-2`; `B-4` stops and reports if the template has moved.
5. **`R4' — a source-inspection test is deleted to make a block green.** The single most tempting
   shortcut in this plan, because three of the four clusters are the only detector. *Mitigation:*
   §5's rules; a red structural assertion is a finding, not an obstacle.
6. **`R5' — scope creep back into the source plan's shape.** Every re-scoped block is an
   invitation to restore the original scope. *Mitigation:* each block's file surface is a closed
   list; growth is a new finding with a new block.
7. **`R6' — the vocabulary question is answered implicitly.** 13 commits landing under a scheme the
   coordinator never ratified. *Mitigation:* §2's recommendation plus the `xref` mitigation;
   **because the scheme touches commit messages only, a wrong choice costs nothing but a reword.**
8. **`R7' — a gate is answered by leaving the code alone and saying nothing.** The likeliest
   failure of `Q7`, and the reason it is called out in its own acceptance criterion.

---

## 7. Execution order and cross-phase coordination

### 7.1 The safe serial order

**One Implementor, strictly sequential, one commit per block.** The numbering **is** the order.

| # | Block | Findings | Class | Depends on (in-plan) | External gate | Risk |
|---|---|---|---|---|---|---|
| 1 | `B-1` Packaging / export hygiene | `CQ-017.1`, `.2`, `CQ-007` residue | M | — | — | **LOW** |
| 2 | `B-2` Locale literals | `CQ-006` | M | — | — | LOW–MED |
| 3 | `B-3` Hardcoded admin URLs | `CQ-018` (URL half) | M | — | **plan 19 `B-2`** | LOW / MED coord |
| 4 | `B-4` Reject-reason boundary | `CQ-003` | **B** | `B-3` | **`G-4a`**, plan 19 (template) | MED |
| 5 | `B-5` Consent-cookie constants | `CQ-013` | M | — | `Q13` | **LOW** |
| 6 | `B-6` Delete dead symbols | `CQ-016` | M | `B-5` | **`Q5`** (coordinator) | **LOW** |
| 7 | `B-7` Saved-search POST boundary | `CQ-004` | **B** | `B-2` | `Q12` | MED |
| 8 | `B-8` `/alerts` prompt + dead state | `CQ-014` | **B** | — | — | **LOW** |
| 9 | `B-9` Bot alerts data access → service | `CQ-002` | **B** | `B-8` | lock-timeout policy | MED |
| 10 | `B-10` `type: ignore` inventory | `CQ-012` | **decision** | `B-6` | — | LOW / HIGH if misused |
| 11 | `B-11` Listings context builder | `CQ-015` | **B** | — | `Q8`, phase 08 | MED |
| 12 | `B-12` Fuzzy ladder + cutoff | `CQ-011` | **B** | `B-11`, `B-2` | `Q1`, `Q7`; phase 08 | MED |
| 13 | `B-13` `ad_edit` extraction | `CQ-001` | **B** | `B-1` | **4 preconditions — BLOCKED** | **HIGH** |

`M` = mechanical · `B` = behavioural.

### 7.2 Every edge, with its reason

| Edge | Why it exists |
|---|---|
| **`B-5` → `B-6`** (file) | `is_consent_given` is deleted from `consent.py` by `B-6`, and `B-5` relocates the constants out of the same file. Running `B-5` first means `B-6`'s diff is a deletion in a settled file, and `B-6` cannot reintroduce a constant that has moved |
| **`B-2` → `B-7`** (file) | `search/views/save_search.py` carries a bare locale literal that `B-2` fixes, and the saved-search coercion closure `B-7` deletes. One file, one run, one review — and `B-7` preserves the `request.LANGUAGE_CODE or "bs"` fallback *whichever form `B-2` left it in* |
| **`B-3` → `B-4`** (file + mechanism) | Both write `review.py`. `B-3` is mechanical URL reversal; `B-4` is a behavioural change to `reject_ad`'s request boundary. Mechanical first, behavioural last, so the harder diff sits on a settled file |
| **`B-8` → `B-9`** (file) | `B-8` edits `cmd_alerts`'s prompt; `B-9` moves four functions out of the same handler. Structural last — and `B-9`'s constraint 6 makes the prompt change visible in the move's review |
| **`B-6` → `B-10`** (file) | `B-10` inventories `lookup_resolution.py`'s suppression state. Reading it before `B-6` edits the file would record a state that no longer exists |
| **`B-11` → `B-12`** (file) | `ads/views/listings.py` is both `B-11`'s call site and `B-12`'s subject. Running `B-12` first means `B-11`'s extraction is written against a file another phase-10 block just restructured |
| **`B-2` → `B-12`** (file) | Bare locale literals survive in the fuzzy neighbourhood. `B-12` is written against the post-`B-2` form |
| **`B-1` → `B-13`** (prerequisite) | `ads/services/` is an **implicit namespace package** today. `B-13` adds `edit_ad.py` to it. `B-1` makes it a real package first |

### 7.3 Where there is deliberately **no** edge

| Pair | Why not |
|---|---|
| `B-1` ↔ `B-2` | Different files, unrelated concerns: a package marker and an export list versus locale literals. One implementor runs them in series anyway |
| `B-3` ↔ `B-5`, `B-7`, `B-8` | No shared file, no shared mechanism. Coupling them would make the coordination-gated block (`B-3`, waiting on plan 19) hold up four unrelated commits |
| `B-4` ↔ `B-6` | The only thing they share is `ModeratorActionLog`, and `B-4` must not reach it. No file, no edge |
| `B-7` ↔ `B-11` | Both introduce a Pydantic/service boundary, and both follow `BaseInputModel`. **The shared pattern is the reason to cross-read them, not to order them** — different apps, different gates, different owners |
| `B-10` ↔ everything | It ships no diff. Making it a hub would turn a triage task into a serialisation bottleneck |
| `B-12` ↔ `B-13` | Different subsystems (`search`/`ads` listings versus `edit.py`). No shared file |

### 7.4 Cross-phase coordination

**Phase 10 does not contact, negotiate with, or wait on any other agent. The coordinator
sequences every external edge.** This section is the boundary contract from phase 10's side.

| Counterparty | What phase 10 needs | What phase 10 must not do |
|---|---|---|
| **Plan 19** (`B-1`, `B-2` live) | `B-2` landed before `B-3` (both own `review.ban_user`); `B-2`'s template surface settled before `B-4` | Touch `admin_actions.py`. Plan 19 chose *extend in place*; phase 10 has **no block** on that file |
| **Phase 03** | `BLOCK 5`'s `SET LOCAL lock_timeout` policy, for `B-9`'s external gate and `B-13`'s precondition | Reorder or renumber `AdvisoryLockId`; start the legacy sweep `BLOCK 11` reserves |
| **Phase 05** | `BLOCK 2` and `BLOCK 8` landed and quiescent before `B-13` | Re-open `ad_edit`'s status allow-list or its publish-clock arm |
| **Phase 07** | `BLOCK 10` quiescent before `B-13` | — |
| **Phase 08** | Its view of `listings_query.py` and `category_fuzzy.py` for `Q8` and `Q1` | Edit `search/models.py`, add a search migration, or change the cached name list |
| **Phase 09** | Its rate-limiter block's relation to `B-9`'s tier | Create `services/contact.py` or `services/support.py` — those deferrals are **phase 09's** |
| **Phase 15** | `AUTHZ-002` / `AUTHZ-007` state, which `B-13` depends on | Revive `can_publish_ad` under any name, or implement `AUTHZ-007` inside `B-13` — it is a **precondition**, not this block's work |
| **Phase 06** | Its consent **service** layer, distinct from `B-5`'s cookie constants | — |

### 7.5 The orders that are unsafe

1. **`B-13` before phase 03 BLOCK 5 or phase 15 `AUTHZ-007`.** The extraction moves the block
   those items edit. Applied independently, one silently reverts the other — and the ownership
   hole gets *relocated* instead of closed.
2. **`B-4` before `B-3`.** `B-3` settles three redirect targets in the same module; `B-4` then
   rewrites `reject_ad`'s boundary against a settled file.
3. **`B-3` before plan 19 `B-2`.** Two plans, one function's diff.
4. **`B-9` before `B-8`.** `B-9`'s move would be reviewed against a prompt sentence `B-8` is
   changing in the same run.
5. **`B-12` before `B-11`.** `B-11` restructures `listings.py`, `B-12`'s subject.
6. **Any block editing a file that has changed since this plan was written**, without re-reading
   it first and stopping if it moved. This plan's own `B-13` exists because the source plan's
   target files churned by eight commits after its anchor.
7. **Any block restoring `.ai/audit/10-code-quality/findings.md`** — it is deleted; §1.2 carries the
   corrected evidence inline.
8. **`B-13` split across commits.** A half-moved `ad_edit` leaves the locked instance and the
   view's call site disagreeing about who owns the transaction.

---

## 8. Out of scope

**Every refusal below is routed or justified. A refusal with neither is a re-filed finding.**

### 8.1 Retired by drift — with the evidence that retired it

| Item | Why it is out of this plan |
|---|---|
| The `@require_POST` mechanical standardisation (source BLOCK 6) | **Shipped as `09-API-010`.** The decorator is present on 13 views including all three in `review.py`, and `test_moderation_views.py`'s docstrings name the commit. Nothing to do |
| The `admin_actions.py` move into `services/` (source BLOCK 12) | **Already moved, to a third path** — the package root, not `views/` and not `services/`. The old path has no git history. Plan 19's `19-Q1` then chose to extend the module **in place**. A fourth relocation would undo a decision made after the source plan's anchor |
| Enabling `PLC0415` (source BLOCK 13) | **869 sites, not 96.** The exclusion list would be a 869-line carve-out for a rule whose remedy is 869 mechanical edits; one of the 869 is a **load-bearing** view→service deferral that plan 19 and phase 09 both depend on; and `[tool.ruff] fix = false` means no auto-fix path. **Destination:** `G-9`, a coordinator tooling-policy decision on the exclusion *strategy*. It has no block here because the strategy *is* the change |
| `reject_ad` / `ban_user` 302 → 405 (source BLOCK 7's `CQ-018` half) | **Shipped as `09-API-010`.** `Q4` has no subject left |
| Removing `AdStatus` from templates (source BLOCK 5's `CQ-005` half) | **Zero `AdStatus.` tokens exist under `templates/**`.** Nothing to remove. Destination for a *future* status literal in a template: the `price_step` context-processor pattern, when one appears |
| The `core/utils/cache.py` module docstring trim | **Rewritten** by `09-API-001`, `09-API-002` and `08-SRCH-007`; it now declares the cache-failure and version-key contracts correctly. The three *per-function* docstrings that misname their subject survive in `B-1` |
| Restoring `SavedSearchInput` "as named" | **It never existed.** Zero matches repo-wide, so there is nothing to re-file and no prior art to preserve. Its duplicated coercion closure is live and becomes `B-7` |
| The empty `src/backend/apps/api/` tree | **Already gone** — `git ls-files` shows no such tree. One of the source plan's rotted premises |
| Deleting the `CQ-017.3` `AdvisoryLockId` reorder | Carried forward unchanged: an `IntEnum` member order has no functional, serialisation or query effect; the file is contended by five phases; and the finding was stale by one member before the anchor. **Phase 10 allocates no lock id and reorders nothing** |

### 8.2 Declined by design — with the rationale, and no destination needed

| Item | Why this plan refuses it |
|---|---|
| **The 15-wrapper boilerplate-docstring trim in `core/utils/cache.py`** | The module docstring a reader actually consults is now correct. Every key and TTL is already a module-level `Final` used as a **default argument**, so a key change is a one-line edit and no reader needs a docstring to find it. Trimming 15 trivial one-line wrappers is documentation churn on a file phases 08 and 09 both write to — project rule 5, and it puts churn on a contended file for zero reader benefit. **The three docstrings that are simply *wrong* are fixed in `B-1`**; the rest is a style preference, not a defect |
| `CQ-014`'s numeric `/alerts` toggle | **FEATURE REQUEST — DECLINED for this programme by the Product Owner, 2026-10-03.** A new user-facing feature, not a remediation: an FSM, a router entry point, numeric parsing, error paths and three new i18n strings. The *defect* is the shipped prompt; `B-8` fixes the prompt and deletes the dead state, and **that is the whole deliverable**. **Explicitly out of scope under the ruling: the FSM, the router entry point, the parsing, and every string beyond the corrected prompt.** If it is picked up later, `B-9` must have run first — the handlers would land in the file `B-9`'s extraction empties |
| `CQ-004`'s `PreferredCityInput` | `set_preferred_city` already validates with an explicit existence query, already returns a 400 with a documented reason, already has `@require_POST`, and already owns its cookie constants. A Pydantic wrapper adds a layer with **no defect behind it** — project rules 5 and 7 |
| `CQ-007`'s `CacheEntry` class and the five proposed cache modules | One-line wrappers over `django.core.cache` whose keys and TTLs are already single-sourced as `Final` default arguments. A class over one-line wrappers is pure indirection |
| `CQ-006`'s `apps/core/services/locales.py` | `LanguageLocale` already exposes `values()`, `from_code()`, `fts_config` and `fts_vector_field`. A wrapper module is a hop with no consumer; the fix is in-place, and the two raw dicts stay **on the enum** |
| `CQ-010`'s `scripts/lint_no_deferred_imports.py` | `ruff`'s built-in `PLC0415` does this and `ruff` is already a dependency. A custom script is a second implementation of a check the project already has |
| The two AST architecture tests (`CQ-002`, `CQ-004`) | A rule that must first be made true cannot be enforced before it is true. Both would fail on the legitimate `AppConfig.ready()` / bootstrap deferrals, and the POST-view test would fail on the `request.POST` + `save()` delegate pattern in `review.py`. **Phase 11 owns test-quality findings** |
| `CQ-001`'s `ErrorPage` enum and `_build_submit_input` helper | `HttpResponseForbidden` and `HttpResponse(status=400)` are self-describing. Hoisting a duplicated block into one local `command` variable costs two lines and creates no new name. Rejected by the validator; rejected again here |
| `CQ-018`'s `require_http_methods` adoption | Used **zero** times in the codebase. Standardise on the existing `@require_POST`; adding a second idiom would create the inconsistency the finding is about |
| `CQ-019` as a standalone comment-density finding | 5.3 % comment-only lines is not a defect, and the comments are predominantly non-obvious design rationale. A tree-wide census is a legacy sweep that **phase 03 BLOCK 11 reserves to itself**. The only residue is `B-1`'s three incorrect docstrings |
| `CQ-012`'s `PriorityScore`, `PriorityFlags(StrEnum)`, and the annotated-boundary work | **No longer a code change.** `B-10` ships an inventory and a routing decision; the `PriorityScore` mapping-compatibility question (`Q14`) is moot because nothing is built. A 30-assertion rewrite in `test_priority.py` for a change with no defect behind it is not proportionate |
| A column, a lookup table, or a migration for `ModeratorActionLog.reason` | The enum's own docstring records that the category is deliberately **not** a DB column, and `docs/02-database/db-schema.md` is the record of that decision. Phase 10 enforces the vocabulary **at the boundary** and changes nothing else |
| A generic "enum in template" mechanism | One enum, one template, one mechanism chosen by `G-4a`. A framework serving one consumer is a new abstraction with one user |
| `can_publish_ad` as dead code | **Phase 15's `AUTHZ-005`**, whose validator **rejected** the dead-code label — the behaviour is specified in `technical-specification.md`, making this a missing integration, not dead code. **Phase 10 must not revive it under any name, in any block** |
| The in-source `QLT-###` → `10-CQ-###` marker sweep | **Phase 03 BLOCK 11's**, whose rule forbids other phases from starting it. This plan writes **no** new provenance marker in any source file |
| Restoring `.ai/audit/10-code-quality/findings.md` | It is deleted. §1 and §1.3 carry the corrected evidence inline |

### 8.3 Explicitly forbidden while implementing

1. Deleting, renaming or re-exporting `_get_ad_status`; creating a wildcard import of
   `telegram_bot/services/ad_data/orm.py`; re-exporting anything from a new `__init__.py`.
2. Adding, renumbering or reordering any `AdvisoryLockId` member; touching `REPAIR_BOT_USERNAME`.
3. Touching `telegram_bot/handlers/lifecycle.py`'s per-locale literal — a documented EC-3 decision.
4. Changing any FTS configuration name or `search_vector_*` column name; touching
   `ads_search_vector_fn`, `ads_search_vector_update`, `on_category_name_update` or
   `setup_search_triggers`.
5. Adding a `# noqa: PLC0415`, or any `per-file-ignores` entry. **Enabling `PLC0415` is `G-9`,
   and this plan has no block for it.**
6. Writing a migration, editing an applied migration, or adding a `CheckConstraint` /
   `MinValueValidator` to `SavedSearch`.
7. Editing `.ai/audit/**`, another phase's plan, another phase's audit handbook, or
   `src/backend/conftest.py`.
8. `git add -A`, `git add .`, `git reset`, `git checkout`, `git restore`, `git stash`, `--amend`,
   force-push, or committing without an explicit instruction.
9. Committing more than one block in one commit, or bundling `B-13`'s extraction with its `Q3`
   handler or any `min_length` clause.
10. A test that asserts a line number, an introspected count that is not a documented invariant, a
    literal private name, a template-string substring, the mere presence of a symbol, or the
    **absence** of one.
11. Deleting a source-inspection test to make a block green, or relaxing one of its assertions.
12. Running a test on the host (`uv run pytest` always fails), or `make makemessages` /
    `make compilemessages` on Win 11 + Docker Desktop.
13. Deleting a `RESOLVED_*_PREFIX` alias without the recorded `Q5` answer.
14. Invoking project rule 2 anywhere in this plan. **It is invoked zero times** — `B-12`'s cutoff
    change is the ruled change, so its test stays green and no test is rewritten.

---

## 9. Definition of done

### 9.1 Per block

A block is done when **all** of the following hold:

1. Its **gate** (if any) has a **written** answer recorded before the first edit, naming the
   decider. **Silence is not an acceptable outcome for any gate in §4.**
2. Its **file surface** is exactly the closed list in its §3 entry. Anything extra is a new
   finding, not a bigger block.
3. Exactly **one commit**, message `"{type}({scope}): {description}"`, carrying the finding
   citation (§2's provisional scheme, pending `Q11`) and, where §2.3 requires it, the `xref`
   line.
4. Its **binding constraints** are all satisfied, and any that bit is named in the commit body.
5. `uv run ruff check` and `uv run basedpyright` are clean on every edited file;
   `uv run djlint` clean if a template was touched.
6. **`.\Makefile.ps1 test` is green** — the fast gate, in Docker, `seed` skipped. Never
   `uv run pytest` on the host.
7. Its **tests** are as §5.1 specifies: the named suites green, the named tests re-pointed and
   not deleted, no assertion relaxed.
8. Its **i18n obligation**, where present, is met — non-empty `ru` and `bs` — and
   `test_i18n_completeness.py` is green.
9. No file outside its surface changed. `git status` shows nothing unexpected, and nothing
   another agent was working on has been reverted.

### 9.2 For the plan

- **12 of 13 blocks committed** (`B-10` commits nothing; `B-13` remains `blocked` unless and until
  its four preconditions are met), or each unstarted block carries a recorded reason.
- Every one of the 11 open/routed gates in §4 is **answered in writing** by its named decider, or
  its block is recorded as not started for that reason.
- `Q11` is answered, and the 13 commits carry the ratified scheme — **or** the discrepancy is
  recorded and the commits are mechanically reworded, which costs nothing because the scheme
  touches commit messages only.
- **Zero migrations**, and `makemigrations --check` reports none.
- No `type: ignore` added, removed or narrowed outside `B-10`'s inventory.
- No `AdvisoryLockId` member added, renumbered or reordered.
- No source-inspection test deleted, and no assertion relaxed anywhere in the plan.
- Every refusal in §8 either has a named destination or a stated rationale — and none was made
  silently.
- The source plan, the audit, and every other phase's plan and audit file are **byte-unchanged**.

### 9.3 What this plan deliberately does not deliver

Stated plainly, so no reader mistakes a smaller plan for an unfinished one:

- **Six of the source plan's sixteen blocks are retired**, five without replacement, because the
  work shipped (`09-API-010`), already happened to a different path, or is not justified at its
  real size (`PLC0415` at 869).
- **`CQ-001`'s extraction is not delivered.** It is blocked on two external prerequisites, one of
  which is the very defect it would close. That is a correct outcome, not an omission.
- **`CQ-012`'s typing work is not delivered.** It becomes an inventory and a routing decision,
  because the named scope was 20× off and no gate enforces it.
- **`CQ-004`'s validation half may not be delivered** if `Q12` is answered (c). Then the
  duplicated-closure fix still ships, and the validation half is **re-filed with a named
  destination** — never silently dropped.

