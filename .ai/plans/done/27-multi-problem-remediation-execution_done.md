---
title: Multi-Problem Remediation Execution — NF-1…NF-5 / N-6 / N-7 / N-8
slug: 27-multi-problem-remediation-execution
phase: 27
status: shipped
created: 2026-10-06
source_plan: multiple
verified_head: 846480dd
language: en
block_count: 9
---

# §A.0 Execution result (recorded 2026-10-06)

**All 9 blocks (B-01 … B-09) executed and validated.** Executed against a tree whose HEAD advanced
past `verified_head` (`846480dd`); the §A.1 drift rule required each Implementor to stop-and-report
rather than adapt silently — no block hit the drift stop (the committed blocks are incremental
descendants of the head of record). Commit map:

| Block | Finding | Commit | Subject |
|---|---|---|---|
| B-01 | NF-1 | `ae2fd6cc` | `fix(moderation): use named URLs in the review form actions` |
| B-02 | NF-5 | `e9c8f205` | `docs(tooling): canonicalize the PYTHONPATH djlint invocation` |
| B-02b | NF-5 (in-pass) | `4b713109` | `style(templates): satisfy H901 in login_issue comments` |
| B-03 | NF-2 | `f4e3903f` | `refactor(locations): share the city fuzzy matcher across bot and web` |
| B-04 | NF-4 | `adc9ffff` | `test(search): make the search SLO guard robust with warm-up and a median` |
| B-05 | N-7 | `737954a9` | `fix(test-infra): require recovery completion before the test DB is healthy` |
| B-06 | NF-3 | `d7f018ad` | `i18n(catalogs): fill the two forward-gap msgids (password policy, consent)` |
| B-07 | N-6 | `2a82f39e` | `i18n(bot): de-alias gettext_lazy so non-content replies are extracted` |
| B-08 | N-8 | `caea8e0c` | `docs(i18n): document the safe scratch extraction recipe for makemessages` |
| B-09 | pass-wide | _(this commit)_ | `docs(plan): record the plan-27 execution result and the plan-25 gate hand-off` |

**B-03 / B-04 / B-05 were IMPLEMENTED in this pass** by product ruling Q1 (§A.0), **not** deferred —
they are full Researcher → Implementor → Validator blocks, recorded here as executed.

**In-pass discovery B-02b.** B-02's whole-tree `lint-templates` run surfaced a **pre-existing,
out-of-scope H901 violation** in `src/backend/templates/users/login_issue.html` (multi-line `{# … #}`
comments), which CI's exact djlint command already flagged. B-02's acceptance criterion could not hold
until it was fixed, so it was remediated as the minimal separate commit `4b713109` (B-02b) rather than
a ninth problem doc. See **D-B02-1** in §A.4.

**B-06 vs B-07 extraction boundary.** The two catalog-touching blocks split the single isolated
extraction diff by direction: **B-06 owns the `ADDED` side** (fill the two forward-gap msgids; its
acceptance is `ADDED=0`, with the residual `REMOVED=3` — the `_lazy` set — deliberately left for
B-07), and **B-07 owns the `REMOVED` side** (de-alias, keep the three `_NON_CONTENT_REPLIES` msgids,
retire the exemption). Only after both is a fresh extraction a full `ADDED=0 AND REMOVED=0` no-op.
They ran **strictly serial** as the §C.4 cluster (B-06 → B-07 → B-08), never concurrently.

**Residual N-7 teardown race (documented, not silently dropped).** The A+C readiness fix makes
test-DB readiness imply recovery completion, but it does **not** fully serialise teardown between
`--reuse-db` + `-n auto --maxprocesses=4` runs (`database … is being accessed by other users`).
The escalation path is recorded in `.ai/plans/27-b05-decision-note.md` §9: if races persist after
A+C, escalate to a **bounded teardown retry** (documented, not silently skipped) — **do not** drop
tests or the xdist parallelism.

**No competing freshness gate was created in this pass.** The durable source-freshness CI gate is
**FOLDED into plan 25 BLOCK 11** (§F.5); plan 27 made it addable by closing the gap but did not add
it. CI carries no `makemessages` step (verified: `Select-String -Path .github/workflows/ci.yml
-Pattern 'makemessages'` → no matches). The pass-wide record is in
`docs/99-agent/architecture.md` §"Extraction-Gap Closure and the Source-Freshness Gate Hand-Off".

---

# §A Provenance, drift control, and corrections

## A.0 Product-owner rulings (2026-10-06, before execution)

| # | Question | Ruling |
|---|---|---|
| Q1 | Scope of NF-2 / NF-4 / N-7 | **Implement all three in this pass** — each becomes a full Researcher → Implementor → Validator block. B-03/B-04/B-05 are **no longer decision-only**; they are promoted to implementation blocks (see §B and §F.2 revision). |
| Q2 | NF-1 moderation review page | **Keep and fix the URLs** (named `{% url %}`); the page stays unlinked from the queue. No retire, no new queue link. |
| Q3 | NF-3 second msgid (C-03-1) | **Translate both msgids** (password-policy + consent) — as already recorded in §A.4 WIDEN. |
| Q4 | NF-4 guard strength | **Robust in-repo guard** (warm-up + median of N samples); the CI load-test p95 job stays as the secondary instrument. |
| Q5 | NF-5 packaging | **Document the `PYTHONPATH` workaround + add a `Makefile.ps1` target**; packaging Option A stays rejected. |

These rulings are binding on every block. §F.1 and §F.2 are superseded accordingly.

## A.1 Provenance

Eight residual findings, recorded across the plan-24 and plan-25 execution runs, are audited against
the live tree at HEAD and decomposed here into executable, dependency-safe blocks. This document is
the **execution plan for the remediation work only**. It re-plans nothing that already shipped.

| Source | Path | Verified at | In scope here |
|---|---|---|---|
| NF-1 | `.ai/audit/problems/01-moderation-review-relative-form-actions.md` | `550d8ce4` | full |
| NF-2 | `.ai/audit/problems/02-bot-city-fuzzy-cutoff.md` | `550d8ce4` | full |
| NF-3 | `.ai/audit/problems/03-stale-locale-catalogs.md` | `550d8ce4` | full, **widened by C-03-1** |
| NF-4 | `.ai/audit/problems/04-slo-test-flakiness.md` | `550d8ce4` | full |
| NF-5 | `.ai/audit/problems/05-djlint-custom-rules-import.md` | `550d8ce4` | full |
| N-6 | `.ai/audit/problems/06-lazy-alias-extraction-gap.md` | `302b5343` | full |
| N-7 | `.ai/audit/problems/07-test-db-readiness-flakiness.md` | `302b5343` | full |
| N-8 | `.ai/audit/problems/08-makemessages-mutates-tracked-catalogs.md` | `302b5343` | full |

**Head of record:** `846480dd` (`846480dd3c46e8e0a617ea3f93f368d28b78c5a1`, 2026-10-06 19:52:49 +0200).
The **Stage-0 audit note** `.ai/audit/99-validation/stage0-code-context.md` is the `{code_context}`
for this plan and **overrides the problem docs wherever they conflict**. Any Implementor whose
`git rev-parse HEAD` differs from `846480dd` must stop and report rather than adapt silently — every
verified starting state in §B is HEAD-relative.

## A.2 Working-tree state owned by other agents

| Path | State at plan time | Rule for this plan |
|---|---|---|
| `.ai/plans/24-…`, `.ai/plans/25-…`, `.ai/plans/26-…` | staged-deleted (` D`), moved to `.ai/plans/done/` | do not touch, do not restore |
| `.ai/audit/**` (including this pass's `problems/` and `99-validation/`) | untracked audit material | do not touch; never modify `.ai/audit/` |
| `.ai/tasks/task_14_b11_stale_entry_gate.yaml`, `.ai/tasks/task_14_b12_i18n_spec.yaml` | untracked plan-25 briefs | do not touch |
| `src/backend/locale/{ru,bs,en}/LC_MESSAGES/django.po` | clean at HEAD | B-06, B-07 mutate via the **isolated-copy** recipe only (B-08); never extract in place |

**Hard git rule, binding on every Implementor in this plan:**

```
git add <explicit path> [<explicit path> ...]      # only
```

Never `git add -A`, `git add .`, `git add <dir>`. Never `git reset`, `git checkout`, `git stash`.
Stage only the paths a block names. If an extraction ever dirties the tracked `.po` files, that is a
**stop-and-report**, not a `git checkout` — recovery is by reverting the offending step, and the
prohibition on `git checkout`/`git restore` stands as a safety rule (the plan-25 auditors used
`git checkout --` under incident conditions; in normal execution no agent may).

## A.3 Ordering principle

One Implementor at a time. Serial execution. **Contended artefacts first** (so a reservation is
claimed before a cheaper block can touch it), then **highest risk**, then **cheapest-confirmation
last**. The catalog/extraction-touching blocks (NF-3, N-6, N-8) form a **serialized cluster** because
they share the `.po` surface and the extraction recipe; the cluster is placed *after* the two
contended-doc blocks (NF-5, N-8 both touch `.kilo/rules/commands.md` and `Makefile.ps1`) so the doc
reservation is held by one editor at a time. See §C.3 for the reservation table and §C.4 for the
cluster rationale.

## A.4 CORRECTIONS table

Disposition values: `CORRECT THE PLAN` (block scope must use the tree truth, not the problem doc's
claim) · `WIDEN` (the source finding is under-scoped; do more) · `CONFIRM` (the tree agrees; proceed)
· `REJECT` (a proposed remedy would do harm) · `FOLD` (durable work belongs in plan 25's gate design).

| # | Source claim | Tree truth at `846480dd` | Disposition |
|---|---|---|---|
| **C-03-1** 🔴 | NF-3 §2, §3.4, §10 state the extraction surfaces **one** stale entry (the `create_admin_user` password-policy msgid) and budget for "the one known entry" | The isolated full extraction proves the **forward gap is TWO msgids**. Besides `"Password does not meet the password policy: %(errors)s"`, the bare string `"Please accept the personal data storage consent first."` (from `apps/ads/services/submission.py:229`, also at `apps/ads/views/edit.py:153` and `telegram_bot/handlers/ad_create/submit.py:188`) is **absent from all three catalogs**. The catalog holds only the *different* strings `"To manage ads, please accept the personal data storage consent first."` and the `"To contact support…"` / `"To post an ad…"` variants. The gate comment at `test_i18n_completeness.py:1697-1700` names "the `submission.py` consent msgid" but the string it names is not the catalog entry it appears to match. **A fix filling only the password-policy msgid still produces a non-empty extraction diff and a red `test_no_empty_msgstr`.** | **WIDEN** — B-06 is budgeted for **both** msgids. The second msgid is **in scope**: NF-3's own AC1 ("a fresh extraction is a no-op") is unreachable otherwise. This is a **correction-bearing widening**, not a new product gate — the string is already a live, user-facing consent message with `gettext_lazy` at three call sites. No new gate is created; the ruling is recorded here and enumerated in the B-06 brief. |
| **DRIFT-1** | NF-3 §6 and N-8 §3.1 quote the documented Extract command as `… makemessages -l ru -l bs -l en --no-location` | At HEAD `.kilo/rules/commands.md` and `Makefile:190` carry `--no-location --no-obsolete` (added by plan-25 BLOCK 10, commit `26a1032d`; confirmed in `.ai/plans/done/25-…_done.md`). Plan-25 BLOCK 10: *"adds `--no-obsolete` **alongside** `--no-location`, never instead of it."* | **CORRECT THE PLAN** — every NF-3 (B-06), N-6 (B-07) and N-8 (B-08) brief uses **both** flags. A one-flag extraction is a different, non-authoritative contract. |
| **C-08-1** 🔴 | N-8 §5 attributes the failed write redirect to "the post-`django.setup()` override is inert … `makemessages` resolves `LOCALE_PATHS` at command setup" | Django 5.2 `makemessages` `handle()` builds `self.locale_paths`, but `build_potfiles()` **inserts every discovered directory named `locale` at index 0** (the directory walk). Because the tree contains `src/backend/locale`, that in-tree dir becomes `self.default_locale_path` **independent of `settings.LOCALE_PATHS`**. Neither a post- nor a pre-`setup()` `LOCALE_PATHS` assignment redirects the write. | **CORRECT THE PLAN** — B-08 documents the **whole-source-tree scratch copy** (N-8 Option A), and **must NOT** propose a naive helper that merely sets `LOCALE_PATHS`. A scratch `LOCALE_PATHS` alone is insufficient. |
| **N-6↔NF-3 coupling** | NF-3 and N-6 are presented as independent findings | The **same isolated extraction** shows the three `_lazy` `_NON_CONTENT_REPLIES` strings in the **REMOVED** set; the catalog surface is shared by NF-3, N-6 and N-8 | **CORRECT THE PLAN** — B-06, B-07, B-08 run as a **serialized cluster**; they must never run concurrently. Ordering matters: N-6's root-cause fix changes what a fresh extraction keeps; NF-3 fills the gap; N-8 documents the safe recipe. See §C.4. |
| **N-8 scope** | N-8 §6 recommends Option A (document the recipe) "optionally B (helper) as the ergonomic form and C coordinated with NF-3's freshness gate" | The hazard is live for every future extraction; the safe pattern is undocumented; no `docs/**` or `.kilo/**` hit for "isolated copy / scratch tree" | **CORRECT THE PLAN** — B-08 delivers **Option A only** (documentation + a `Makefile.ps1` target mirroring the documented recipe). Option B (a non-mutating helper) is **out of scope** unless it beats the directory-walk discovery (C-08-1) — a naive `LOCALE_PATHS` helper is **forbidden**. Option C (a durable guard) is **FOLD**ed into plan 25 BLOCK 11, not landed here. |
| **NF-3 Option B / N-6 / N-8 gate** | NF-3 §6 Option B, N-6 §5, N-8 §6 Option C all gesture at a durable freshness/guard gate | Plan 25 owns the catalog gate design and its exemption sets (BLOCK 11, `f7d1ff73`); the source-freshness gate cannot be added until the gap is resolved | **FOLD** — no competing gate is created in this pass. Any durable source-freshness gate is folded into **plan 25's BLOCK 11** design (B-09's final doc pass records the hand-off). This pass fixes the gap so the gate *becomes* addable; it does not add it. |
| **NF-5 scope note** | NF-5 §3.6 notes the H901 proof was on a scratch template; §2 lists `pyproject.toml` false claim and the `Makefile.ps1` gap | H901 fires for templates **inside** the project template tree only (`.djlint_rules.yaml` is resolved relative to the project templates); a temp-dir file does **not** fire it | **CONFIRM** — B-02's validation keeps the negative control **inside the project template tree** (scratch file removed afterward). |
| **NF-2 precondition** | NF-2 §6 Option A asks the Auditor to confirm bot→backend service imports | The bot tier already imports backend modules pervasively, including `apps.locations` and `apps.categories.services`; a shared `apps/locations/services/city_fuzzy.py` adds no new cross-tier edge | **CONFIRM** — Option A is architecturally consistent. It remains a genuine A-vs-B design choice for the **Researcher** (B-03). |
| **N-7 measurement** | N-7 §3.2 quotes a ~50 s/80 s recovery window from plan-25 | The Stage-0 audit could **not** re-measure the window (a healthy shared DB was correctly preserved); the structural cause (10 s `start_period` < recovery; `pg_isready` is liveness-only) is confirmed | **CORRECT THE PLAN** — B-05's validation needs a **forced-recreate measurement**; this is a recorded validation cost, and the numeric window must be re-derived, never copied. |

**Cross-cutting note:** all eight findings were re-verified at `846480dd`; the Stage-0 disposition
table records NF-3 as *partially* reproduced (C-03-1) and N-7 as *structurally* reproduced.

**Execution discovery D-B02-1 (2026-10-06):** B-02's whole-tree `lint-templates` run surfaced a
**pre-existing, out-of-scope H901 violation**: `src/backend/templates/users/login_issue.html` carries
multi-line `{# … #}` comments (the file header at line 1 and the recovery-link comment at lines 25-30).
The file is unchanged since `846480dd` and CI's exact djlint command produces the identical
`38 files, found 1 error` — so B-02's new target is CI-parity correct and the non-zero exit is the
shared template defect, not a B-02 bug. Because B-02's acceptance criterion ("the documented command
succeeds") cannot hold until this is fixed, it is remediated as a minimal separate commit **B-02b**
(convert the two multi-line comments to single-line `{# #}` / `{% comment %}`), recorded here as an
in-pass discovery rather than a ninth problem doc. No other template violates the rule.

---

# §B Execution blocks

Nine blocks, **B-01 … B-09**, executed strictly in the order given by §C.2. Every block is
independently reviewable; **every block now names a single Implementor** — B-03, B-04 and B-05 were
**promoted from design gates to full implementation blocks by ruling Q1** (§A.0, §F.2): each runs
Researcher (resolve/record the option) → Implementor (land it) → Validator (independent review). The
pass therefore holds **nine Implementors in one serial line**. `AUD`/`RES`/`PLN`/`IMP`/`VAL` columns
below are repeated per block.

> **Agent legend.** **Auditor** — re-verifies claims against the tree and enumerates the full fact
> base. **Researcher** — resolves a genuine multi-option design choice. **Planner** — produces the
> implementor-ready decision/task artifact. **Implementor** — the single code/doc writer.
> **Validator** — independent review of high/critical-risk blocks.
> **Test-engineer** — test-infrastructure quality decision (available for NF-4/N-7).
> **Docs-specialist** — doc-only portions (NF-5, N-8) and the final doc pass.

---

## B-01 — NF-1: moderation review page — named URL tags

| Field | Value |
|---|---|
| Source | `.ai/audit/problems/01-moderation-review-relative-form-actions.md` (NF-1) |
| Priority | **P1** |
| Risk | **Low** — template-only; no view/url/model/migration |
| Depends on | — |
| Blocks | — |
| Auditor | **no** — every §2/§3 claim reproduced at HEAD; the sweep and urlconf are established |
| Researcher | **no** — the keep-vs-link-vs-retire question is a product decision, **defaulted to Option A** (see below); no comparative analysis remains |
| Planner | **no** — folded into the implementor brief (the fix is mechanical) |
| Implementor | **yes** |
| Validator | **no** — low-risk single-template edit; the new regression test *is* the verification |

### Objective

Replace the five **relative** references in `review.html` (1 back link + 4 form actions) with
**named** `{% url %}` tags so they resolve correctly from `/moderation/review/<id>/` **and** from the
B-4 invalid-reason re-render origin `/moderation/reject/<id>/`.

### Product decision (defaulted, recorded)

NF-1's keep-vs-link-vs-retire question (retire = delete template + views + urls + tests) is a
**product decision**. It is **unresolved at plan time**; per instruction, the plan **defaults to
Option A** (named `{% url %}`), which is origin-independent, matches plan-24 B-3's direction
(named lookups instead of hardcoded paths), and keeps the page. **Do not retire the page in this
pass.** Retiring requires an explicit product ruling; see §F.1.

### Verified starting state

- `src/backend/templates/admin/moderation/review.html` carries **exactly five** relative references:
  a back link `href="../"`, two approve forms `action="../approve/{{ ad.id }}/"` (in the
  `on_moderation` and `on_moderation_failed` blocks), a reject modal `action="../reject/{{ ad.id }}/"`,
  and a ban modal `action="../ban/{{ ad.id }}/"`.
- `apps/moderation/urls.py` (`app_name = "moderation"`) defines `queue/`, `review/<int:ad_id>/`,
  `approve/<int:ad_id>/`, `reject/<int:ad_id>/`, `ban/<int:ad_id>/`, `api/v1/bulk-action/`.
  **There is no `/moderation/` root route**; `config/urls.py` mounts the app at `moderation/`.
- `queue.html` links to `{% url 'admin:ads_ad_change' ad.id %}` (the admin change page), **not** the
  review page; a repo-wide search for `moderation:review` matches only
  `apps/moderation/tests/test_moderation_views.py`. The page is currently unreachable from the UI.
- `apps/moderation/tests/test_moderation_views.py` GETs the page and POSTs absolute URLs; **no test
  asserts the rendered `action=`/`href=` values**.
- The `admin/` template subtree is excluded from the visible-text/i18n scans → **no i18n work**.

### Scope (closed file surface)

| Semantic unit | Change |
|---|---|
| `src/backend/templates/admin/moderation/review.html` — the back link | `href="../"` → `{% url 'moderation:queue' %}` |
| `src/backend/templates/admin/moderation/review.html` — approve form (`on_moderation` block) | `action="../approve/{{ ad.id }}/"` → `{% url 'moderation:approve' ad.id %}` |
| `src/backend/templates/admin/moderation/review.html` — approve form (`on_moderation_failed` block) | `action="../approve/{{ ad.id }}/"` → `{% url 'moderation:approve' ad.id %}` |
| `src/backend/templates/admin/moderation/review.html` — reject modal form | `action="../reject/{{ ad.id }}/"` → `{% url 'moderation:reject' ad.id %}` |
| `src/backend/templates/admin/moderation/review.html` — ban modal form | `action="../ban/{{ ad.id }}/"` → `{% url 'moderation:ban' ad.id %}` |
| `src/backend/apps/moderation/tests/test_moderation_views.py` | add the regression test (below) |

### Binding constraints

1. **Template + test only.** No view, URLconf, model, migration, or settings change.
2. **Build expectations with `reverse()`.** The new test must not hardcode `/moderation/...` strings.
3. **Do not modify existing tests or assertions** — add a new test method only.
4. **Do not retire the page** (see the product decision above).
5. **Assertion level:** `response.content` string match on the `action="…"`/`href="…"` attributes —
   this is a URL contract, so a string assertion is correct (unlike cosmetic markup).
6. `djlint` clean on the touched template, using the **NF-5 workaround**
   (`PYTHONPATH=src/backend`; see B-02) — the bare command fails until B-02 lands.

### Acceptance criteria

1. From `/moderation/review/<id>/`: the two approve forms carry
   `action == reverse("moderation:approve", args=[id])`; the reject modal carries
   `reverse("moderation:reject", args=[id])`; the ban modal carries
   `reverse("moderation:ban", args=[id])`; the back link carries `reverse("moderation:queue")`.
2. From the B-4 re-render origin `/moderation/reject/<id>/` (POST an invalid `reason_category`): the
   same five absolute targets are rendered.
3. No `action="../` or `href="../` reference remains in `review.html`.
4. The recursive template sweep still finds no relative/root-absolute form actions **outside**
   `review.html`.
5. Existing moderation tests unchanged and green; the new test uses `reverse()`.
6. Fast gate green; `djlint` clean on the touched template (NF-5 workaround).
7. No view, URLconf, model or migration change.

### Test contract

Add to `apps/moderation/tests/test_moderation_views.py`:

- GET the review page for an `on_moderation` ad and an `on_moderation_failed` ad; assert the two
  approve `action`s, the reject `action`, the ban `action` and the back link using `reverse()`.
- POST an invalid `reason_category` (the B-4 boundary path) and assert the same five absolute
  targets in the re-rendered response.

### Rollback

Single-file (template) revert plus removal of the added test method. No data, no schema.

### DoD

- [ ] All five references converted to `{% url %}`; AC1–AC7 met.
- [ ] **Verify, do not assume:** (i) the route names `moderation:queue/:approve/:reject/:ban` exist
      at this HEAD (read `apps/moderation/urls.py`); (ii) that the sweep finds no sibling template.
- [ ] `git add src/backend/templates/admin/moderation/review.html src/backend/apps/moderation/tests/test_moderation_views.py`
      — explicit paths only.

---

## B-02 — NF-5: `uv run djlint` importability (canonicalize the workaround)

| Field | Value |
|---|---|
| Source | `.ai/audit/problems/05-djlint-custom-rules-import.md` (NF-5) |
| Priority | **P1** — the documented command is broken **now** |
| Risk | **Low–Medium** — a shared developer entry point (`Makefile.ps1`) and a shared doc file; Option A (packaging) is **rejected** as in-pass |
| Depends on | — |
| Blocks | B-08 (contended files), B-01's djlint check uses the workaround until this lands |
| Auditor | **no** — all §3 rows reproduced; the invocation table is established |
| Researcher | **no** — Option B is recommended and cheap; Option A (packaging) is **explicitly out of scope** (§F.3) |
| Planner | **no** — folded into the implementor brief |
| Implementor | **yes** (Docs-specialist for the doc portion) |
| Validator | **no** — low-risk tooling; the manual verification commands *are* the contract |

### Objective

Canonicalize the working `PYTHONPATH=src/backend` invocation (NF-5 Option B): update the documented
local command in `.kilo/rules/commands.md`, add a `lint-templates` target to `Makefile.ps1` that
mirrors the existing `Makefile` Docker target, and correct the **false** editable-install claim in the
`pyproject.toml` comment.

### Verified starting state

- `uv run djlint src/backend/templates/` → `ModuleNotFoundError: No module named 'djlint_custom_rules'`;
  "This is not a clean run."
- `$env:PYTHONPATH='src/backend'; uv run djlint …` → clean.
- **No `[build-system]`** in `pyproject.toml`; `uv pip list` shows no `mko-bazuna` package; `[tool.uv]`
  has only `default-groups = []`. The comment at `pyproject.toml` lines ~82-93 claims an editable
  install that **does not exist**.
- `Makefile.ps1` has **no** djlint target (`Makefile:135` has `lint-templates:` via Docker).
- CI (`ci.yml:236-247`) runs `uv run djlint templates/` with `working-directory: src/backend`,
  `env: PYTHONPATH: .`; `docker/Dockerfile` sets `ENV PYTHONPATH=/app/src:/app/src/backend`.
- **H901** (multi-line `{# … #}`) fires for templates **inside** the project template tree, under the
  workaround; a temp-dir file does **not** fire it (`.djlint_rules.yaml` resolves relative to the
  project templates).

### Scope (closed file surface)

| Semantic unit | Change |
|---|---|
| `.kilo/rules/commands.md` — "Lint templates" row | replace the bare `uv run djlint src/backend/templates/` with the `PYTHONPATH=src/backend` form (or point at the new target), matching CI's actual mechanism |
| `Makefile.ps1` — new `lint-templates` function + `switch` arm + `Show-Help` line | mirrors `Makefile`'s Docker target **or** runs djlint with `PYTHONPATH=src/backend`, following the existing env-override/host-side idioms |
| `pyproject.toml` — the editable-install comment block | corrected to describe the **PYTHONPATH** mechanism, or removed |

### Binding constraints

1. **Option B only.** Do **not** add `[build-system]`; do **not** change the packaging model; do
   **not** touch pytest `pythonpath`/`--import-mode=importlib` roots or Docker's `--no-install-project`.
   Option A is **REJECTED** for this pass (§F.3).
2. **Never "fix" the failure by removing the custom rule** from `.djlint_rules.yaml`. H901 must stay
   enforced.
3. **CI and Docker are correct and green** — do not change `ci.yml` or `docker/Dockerfile`.
4. `pyproject.toml` edit is **comment-only** unless the comment is deleted; no dependency, no
   `[build-system]`, no `py-modules` value change.
5. `Makefile.ps1` formatting follows the existing `Write-Host "  <target>       <description>"` shape;
   use the established host-side-script idiom (`Invoke-SeedPhotosValidate`) and the env-override idiom
   (`Invoke-Profile`).
6. Preserve line-ending reality where practical; a mixed-endings edit is a diff hazard.

### Acceptance criteria

1. The documented local command(s) succeed from the repo root on Windows **without a traceback**.
2. `.kilo/rules/commands.md`, `Makefile.ps1` (if a target is added), `Makefile` and CI are
   **consistent** — one documented way to lint templates locally, matching CI's mechanism.
3. The **H901 custom rule is still enforced** under the chosen invocation: linting a scratch template
   **inside the project template tree** containing a multi-line `{# … #}` comment produces the H901
   diagnostic (demonstrated in the validation note; scratch file removed afterward).
4. No `.djlint_rules.yaml` semantic change; no template changes; CI and Docker paths unchanged.
5. The `pyproject.toml` comment no longer asserts a non-existent editable install.

### Test contract

Manual verification commands (quoted in the validation note) are the contract: the documented command
succeeds; the H901 negative control fires **inside the template tree**. If a `Makefile.ps1` target is
added, validation runs that target on Windows and quotes the result. **No new pytest test.**

### Rollback

Revert the doc/target/comment edits. No product, DB, or i18n surface.

### DoD

- [ ] Documented command fixed; target added; false comment corrected; H901 still fires.
- [ ] **Verify, do not assume:** (i) H901 still fires **inside** the template tree (the outside-tree
      non-firing is a fact, not a bug); (ii) no existing `Makefile.ps1` arm shadows the new target.
- [ ] `git add .kilo/rules/commands.md Makefile.ps1 pyproject.toml` — explicit paths only.

---

## B-03 — NF-2: shared city fuzzy helper (`CITY_FUZZY_CUTOFF = 0.6`) ⚑ IMPLEMENTED

| Field | Value |
|---|---|
| Source | `.ai/audit/problems/02-bot-city-fuzzy-cutoff.md` (NF-2) |
| Priority | **P2** — shape/consistency finding; no user-visible defect today |
| Risk | **Medium** — the change touches a bot runtime path and introduces a shared backend service module |
| Depends on | — |
| Blocks | — |
| Auditor | **no** — the four-site inventory and the import precedents are established by the Stage-0 note |
| Researcher | **yes** — resolves **A (shared helper) vs B (named constant only)** first and records a short decision note (why A over B) |
| Planner | **no** — folded into the implementor brief |
| Implementor | **yes** — lands the chosen option (Option A: the shared helper) |
| Validator | **yes** — independent review: behavior preserved, no cutoff drift, candidate injection correct |
| Test-engineer | **no** — not a test-infrastructure decision |

### Objective

Implement the shared city-fuzzy helper so the fourth fuzzy site stops carrying a bare literal. Create
`src/backend/apps/locations/services/city_fuzzy.py` mirroring `apps/categories/services/fuzzy.py`
(`CITY_FUZZY_CUTOFF: Final[float] = 0.6`, injected-candidate `match_city`), and route **both** city
call sites through it. The Researcher resolves A-vs-B first (recording why A over B); the pass lands the
chosen option; an independent Validator reviews.

### Verified starting state

- `telegram_bot/handlers/ad_create/city.py::process_city` uses
  `difflib.get_close_matches(city_name, [c.get_name(get_language()) for c in all_cities], n=3, cutoff=0.6)`,
  using only `close_matches[0]`; the matched localized name is fed back through `get_city_by_name`.
- `apps/locations/services/city_suggestions.py::suggest_city` uses a **named** `_CUTOFF: Final[float] = 0.6`, `n=1`, over **slugs**.
- Reference shape: `apps/categories/services/fuzzy.py` — `CATEGORY_FUZZY_CUTOFF: Final[float] = 0.8`, injected `match_category(query, candidates)`.
- Exactly **four** production `get_close_matches` sites; the bot city step is the only one with a bare literal.
- **Option A precondition confirmed:** the bot tier already imports backend services, `apps.locations`
  and `apps.categories.services`; a shared `apps/locations/services/city_fuzzy.py` adds **no** new
  cross-tier edge (the bot→backend direction already exists).
- Existing test ratios: `Podgoric/Podgorica = 0.9412`, `budav/budva = 0.8` — **neither distinguishes 0.6 from 0.8**.

### Scope (closed file surface)

| Semantic unit | Change |
|---|---|
| `src/backend/apps/locations/services/city_fuzzy.py` — new module | `CITY_FUZZY_CUTOFF: Final[float] = 0.6`; `match_city(query, candidates, *, n=… )` with an injected-candidate ladder; stdlib + Django-free only |
| `telegram_bot/handlers/ad_create/city.py` — `process_city` | remove the inline `cutoff=0.6`; call `match_city` with the injected localized-name list; keep the `get_city_by_name` re-lookup; decide/document the bot's `n` |
| `apps/locations/services/city_suggestions.py` — `suggest_city`, `_CUTOFF` | remove the local `_CUTOFF`; call `match_city` with the injected slug list; keep `n=1` |
| `apps/locations/tests/test_city_suggestions.py` | add the web-city **boundary** test (behavior, not the literal 0.6) |
| `telegram_bot/tests/test_city.py` — `TestProcessCity` | add the bot-handler **boundary** test (behavior, not the literal 0.6) |

### Binding constraints

1. **Implement the chosen option (Option A).** The Researcher resolves A-vs-B first; the pass lands it. Do not stop at a decision record.
2. **Keep 0.6.** `CITY_FUZZY_CUTOFF = 0.6` (the `Q7`(b)-ruled value) — do **not** change the number.
3. **Candidate injection is mandatory** (the `match_category` pattern) — the bot matches localized **names**, the web matches **slugs**; the helper never assumes one list.
4. **`n` is an injected parameter** of the helper, defaulting per caller (bot keeps its `n=3`/single-best precedent or reduces to `n=1`; the web keeps `n=1`) — the `n=3`-vs-`n=1` decision is documented.
5. **Behavior preserved:** bot keeps its `get_city_by_name` re-lookup; the web keeps the same suggestion for the same input.
6. **Cross-tier import stated:** the bot tier already imports backend services incl. `apps.locations`; the shared module adds no new edge.
7. **Boundary test through behavior** — a below-cutoff query is rejected, an above-cutoff query resolves; never assert the literal `0.6`. Add a case with ratio strictly in (0.6, 0.8).
8. **No i18n extraction** — no user-visible string change; `test_bot_no_hardcoded_messages` stays green.

### Acceptance criteria

1. The Researcher's short decision note is recorded and names Option A over Option B with rationale.
2. `apps/locations/services/city_fuzzy.py` exists with `CITY_FUZZY_CUTOFF = 0.6` (unchanged) and an injected-candidate `match_city(query, candidates, *, n=…)`.
3. Both call sites route through the helper; no bare `cutoff=0.6` literal remains at either city site.
4. Behavior is unchanged (web slug path identical; bot resolves the same city for the same input).
5. A boundary test proves rejection below cutoff and resolution above cutoff for **both** the web service and the bot handler, asserted through behavior.
6. A ratio-in-(0.6, 0.8) case is present; existing city tests remain green; the fast gate is green; no i18n extraction.
7. No new `ads ↔ search` edge; the helper imports stdlib + Django-free code only.

### Test contract

- Behavior-level boundary tests (below-cutoff rejected / above-cutoff resolved) for `test_city_suggestions.py` (web) and `test_city.py::TestProcessCity` (bot).
- Existing `test_city_suggestions.py` / `test_city.py` unchanged and green; `test_bot_no_hardcoded_messages` green.
- `uv run ruff check …` on the touched paths; `uv run basedpyright …` on the touched helpers/handler; `.\Makefile.ps1 test`.

### Rollback

Single-commit revert: delete the new module, restore the inline `cutoff=0.6` in `city.py` and the local
`_CUTOFF` in `city_suggestions.py`, remove the two added test methods. No DB, no schema, no i18n.

### DoD

- [ ] Researcher's A-over-B decision note recorded; Option A landed; both sites refactored; 0.6 unchanged.
- [ ] Boundary test present for both bot and web; behavior preserved; no i18n extraction.
- [ ] **Verify, do not assume:** (i) the four-site `get_close_matches` census at this HEAD; (ii) the bot's `apps.locations` import precedent; (iii) the new boundary case ratio is strictly in (0.6, 0.8).
- [ ] `git add src/backend/apps/locations/services/city_fuzzy.py src/backend/apps/locations/services/city_suggestions.py src/telegram_bot/handlers/ad_create/city.py src/backend/apps/locations/tests/test_city_suggestions.py src/telegram_bot/tests/test_city.py` — explicit paths only.

---

## B-04 — NF-4: robust in-repo SLO guard (warm-up + median of N) ⚑ IMPLEMENTED

| Field | Value |
|---|---|
| Source | `.ai/audit/problems/04-slo-test-flakiness.md` (NF-4) |
| Priority | **P1** — the fast gate's reliability is compromised at HEAD |
| Risk | **Medium–High** — the change defines what happens to the **only** in-repo latency guard |
| Depends on | — |
| Blocks | — |
| Auditor | **no** — flakiness is LIVE at HEAD (2986 ms / 2547 ms) and the CI touchpoints are inventoried |
| Researcher | **yes** — records the robust-guard shape + derivation first (resolves A-vs-B); short decision note |
| Planner | **no** — folded into the implementor brief |
| Implementor | **yes** — lands the robust guard |
| Validator | **yes** — runs the test ≥ 3 times under load; verifies the SLO intent and no CI/p95 duplication |
| Test-engineer | **yes** — owns the guard-vs-instrument split (Q4) |

### Objective

Replace the single-sample 2000 ms wall-clock bound in
`apps/search/tests/test_search_slo.py::TestSearchResponseSLORegression::test_search_at_seed_volume_meets_slo`
with a **robust in-repo guard** (Q4): warm-up request(s) (untimed) + **median of N ≥ 5** timed samples;
assert the median ≤ `PerformanceSLO.SEARCH_SLO_MS` (2000 ms). The CI load-test p95 job stays the
**sole percentile instrument**.

### Verified starting state

- The test seeds 60 PUBLISHED ads and times **one** `/search/?q=товар&lang=ru` request with
  `time.monotonic()`, asserting `elapsed_ms <= PerformanceSLO.SEARCH_SLO_MS` (`= 2000`, p99 spec).
- **Flakiness is LIVE at HEAD:** fresh isolated runs fail at **2986 ms** and **2547 ms**; the docstring
  calls it a "single-sample wall-clock bound, not a percentile measurement".
- Three CI touchpoints: main job (`ci.yml:157`, `-m "not seed"`); dedicated step (`ci.yml:164-169`,
  `-k TestSearchResponseSLORegression`); `load-test` job (`ci.yml:402+`) with the **Locust p95** hook
  (`ci.yml:510-548`) — the percentile instrument.

### Scope (closed file surface)

| Semantic unit | Change |
|---|---|
| `apps/search/tests/test_search_slo.py` — `test_search_at_seed_volume_meets_slo` | replace the single timed request with warm-up + median of N ≥ 5; assert median ≤ `SEARCH_SLO_MS`; update the docstring (robust guard, not a percentile instrument; point at the load-test p95 job) |
| `.github/workflows/ci.yml` | **not edited by default** — only if the chosen shape genuinely requires it, and then only by **B-05** (single ci.yml owner, §C.3); the load-test p95 job stays intact |

### Binding constraints

1. **Robust in-repo guard (Q4).** Warm-up + **median of N ≥ 5** (e.g. 7) samples; assert the **median** ≤ `SEARCH_SLO_MS`.
2. **Keep the CI load-test p95 job as the sole percentile instrument** — do **not** remove it, do **not** duplicate the p95 gate in the unit suite, do **not** modify `ci.yml`.
3. **No raise / delete / blind `xfail`** (forbidden). Any bound change carries its **derivation** (warm-up + median + host tolerance) in the docstring and decision note.
4. Prefer **not** changing `SEARCH_SLO_MS`; if the Researcher's derivation demands it, record the derivation.
5. The three CI touchpoints must stay **consistent** with the new shape (no step references a removed assertion).
6. The modified test must reliably pass under load (Validator runs it ≥ 3 times).

### Acceptance criteria

1. The test uses warm-up request(s) + median of N ≥ 5 timed samples; asserts the median ≤ `SEARCH_SLO_MS`.
2. The docstring states it is a robust guard, not a percentile instrument, and references the load-test p95 job.
3. The seed volume (60 ads) and the real `/search/` path are preserved.
4. No raise/delete/blind-`xfail`; a changed bound carries its derivation (otherwise `SEARCH_SLO_MS` is unchanged).
5. `ci.yml` is unchanged (no p95-gate duplication, load-test job intact).
6. The modified test passes ≥ 3 consecutive isolated runs under load; the fast gate is green.

### Test contract

- Run `apps/search/tests/test_search_slo.py` in isolation ≥ 3 times as the reliability proof; run the fast gate.
- The dedicated CI step (`-k TestSearchResponseSLORegression`) must remain consistent (no CI edit expected).
- `uv run ruff check …` / `uv run basedpyright …` on the test file.

### Rollback

Single-file revert: restore `test_search_slo.py` to its single-sample form. No product code, DB, or i18n surface.

### DoD

- [ ] Warm-up + median-of-N guard landed; median asserted ≤ `SEARCH_SLO_MS`; docstring updated.
- [ ] The SLO test passes ≥ 3 consecutive isolated runs under load; `ci.yml` untouched; p95 job intact.
- [ ] **Verify, do not assume:** (i) the live flakiness at HEAD (2986 ms / 2547 ms) by re-running the isolated test; (ii) the load-test p95 job is healthy and remains the sole percentile instrument; (iii) the three CI touchpoints.
- [ ] `git add src/backend/apps/search/tests/test_search_slo.py` — explicit paths only.

---

## B-05 — N-7: test-DB recovery-aware readiness ⚑ IMPLEMENTED

| Field | Value |
|---|---|
| Source | `.ai/audit/problems/07-test-db-readiness-flakiness.md` (N-7) |
| Priority | **P1** — the per-block "fast gate green" DoD is unreliable at HEAD |
| Risk | **High** — the healthcheck/wait strategy is shared test infrastructure; the fix's validation needs a **forced-recreate measurement** |
| Depends on | — |
| Blocks | — |
| Auditor | **no** — the structural cause is confirmed (10 s `start_period` < recovery; liveness-only probe) |
| Researcher | **yes** — chooses **A (recovery-aware healthcheck / raised `start_period`) vs B (serialize/pre-warm) vs C (retry-tolerant wait)** and records the decision note + re-derived recovery window |
| Planner | **no** — folded into the implementor brief |
| Implementor | **yes** — lands the chosen strategy |
| Validator | **yes** — forced-recreate measurement (N ≥ 3 consecutive fast-gate runs); no test weakened |
| Test-engineer | **yes** — test-infrastructure quality decision |

### Objective

Make test-DB readiness imply **recovery completion** (not mere liveness) so the per-block "fast gate
green" criterion is reliable. Apply the Researcher-chosen strategy (A/B/C) to the test `db` healthcheck
and/or `docker/entrypoint.sh::wait_for_db()`, with bounded retries and a clear error on exhaustion, and
address CI parity explicitly. **B-05 is the sole owner of the exact, enumerated `ci.yml` healthcheck
change (if one is needed).**

### Verified starting state

- `docker-compose.test.yml` `db` healthcheck: `pg_isready -U postgres -d mko_bazuna`, `interval: 5s`, `timeout: 5s`, `retries: 5`, **`start_period: 10s`**.
- Base `docker-compose.yml` `db`: **`start_period: 30s`**, with the inline comment about "a healthy-but-recovering server".
- `docker/entrypoint.sh` `wait_for_db()` retries `psycopg.connect(...)` 30×1s; it does **not** classify `database system is starting up`.
- `pg_isready` is a **liveness** probe — it does not wait for crash recovery (WAL replay) — **confirmed**.
- CI healthchecks (`ci.yml:89-92`, `:261-264`, `:413-416`) use the same `pg_isready` shape (`--health-retries 5 --health-interval 5s`).
- **Structural cause confirmed**; the recovery window was **not** re-measured (a healthy shared DB was preserved) — it must be **re-derived** here, never copied from plan 25.
- The test DB container is currently Up (healthy); the Validator may recreate it (test DB, not dev data), but must stop-and-report if recreation fails.

### Scope (closed file surface)

| Semantic unit | Change |
|---|---|
| `docker-compose.test.yml` — `db` service healthcheck | raise `start_period` toward/at the base (`30s`+) and/or strengthen the probe (`pg_isready` PLUS a successful `SELECT 1` against `mko_bazuna`) so `healthy` implies recovery completion |
| `docker/entrypoint.sh` — `wait_for_db()` | if the chosen strategy includes it, retry `database system is starting up` for a **bounded** period with a clear error on exhaustion |
| `.github/workflows/ci.yml` — test-job healthchecks (`:89-92`, `:261-264`, `:413-416`) | **CONDITIONAL and B-05-only** — bring CI into parity only if the chosen strategy requires it; enumerate the exact change; keep it minimal |
| `docker-compose.yml` — base `db` | **REFERENCE ONLY** (`start_period: 30s`) — do not weaken; touch only for parity if required |

### Binding constraints

1. The chosen strategy must make readiness imply **recovery completion**, not mere liveness.
2. **Bounded retries** with a clear error on exhaustion — an **unbounded retry is forbidden**.
3. **Do not weaken, skip, or delete any test** to "fix" this (the NF-4 trap).
4. **CI parity** addressed explicitly; `ci.yml` **may be edited by this block only** (minimal, enumerated) — no other block edits `ci.yml` (§C.3).
5. The **forced-recreate measurement** (N ≥ 3 consecutive fast-gate runs) is the validation contract; the recovery window is **re-derived**, never copied.
6. No application/migration/settings behaviour change; no product surface touched.

### Acceptance criteria

1. The Researcher's decision note records the chosen strategy (A/B/C), the re-derived recovery window, and the CI-parity disposition.
2. Readiness implies recovery completion: a connection during the former recovery window succeeds, or the wait retries until it does (bounded).
3. Recreating the test DB and running the fast gate **N ≥ 3** consecutive times produces **zero** spurious failures on untouched modules (quoted).
4. The numeric recovery window is re-derived from measurement.
5. CI healthcheck settings stay consistent with the compose change (or CI is shown explicitly unaffected).
6. No test bound/assertion/module weakened or deleted; no product surface touched.

### Test contract

- The contract is the **forced-recreate measurement**: recreate the test DB container so crash recovery is exercised, then run the fast gate **N ≥ 3** consecutive times and quote the result.
- Re-derive the recovery window from container logs during recreate (never copy plan 25's figures).
- No new pytest test (infrastructure); the existing suite is the subject.

### Rollback

Revert `docker-compose.test.yml` (and `docker/entrypoint.sh`, and `ci.yml` only if changed). No schema, no data, no product code.

### DoD

- [ ] Strategy chosen + recovery window re-derived; landed with bounded retries; clear error on exhaustion.
- [ ] Forced-recreate measurement done: N ≥ 3 consecutive fast-gate runs, zero spurious failures (quoted).
- [ ] CI parity addressed explicitly; B-05 is the sole `ci.yml` owner for this pass.
- [ ] **Verify, do not assume:** (i) the current `start_period` values in both compose files; (ii) the `entrypoint.sh` wait shape; (iii) CI healthcheck settings at `ci.yml:89-92`/`:261-264`/`:413-416`.
- [ ] `git add docker-compose.test.yml docker/entrypoint.sh` — explicit paths only (plus `.github/workflows/ci.yml` only if the enumerated CI-parity change is required).

---

## B-06 — NF-3: fill the two forward-gap msgids ⚑ CLUSTER 1/3

| Field | Value |
|---|---|
| Source | `.ai/audit/problems/03-stale-locale-catalogs.md` (NF-3), **widened by C-03-1** |
| Priority | **P0** — blocks a future CI freshness gate; ends the `B-4` hand-insert workaround |
| Risk | **High** — the catalog is the source of truth; the extraction must not run in place; the diff must be fully enumerated |
| Depends on | **B-08 conceptually precedes** (the safe extraction recipe), but B-08's *documentation* lands after; B-06 uses the recipe the Stage-0 audit already established — see B-08 |
| Blocks | B-07, B-08 (serialized cluster) |
| Auditor | **yes** — the full extraction diff must be re-enumerated (C-03-1) |
| Researcher | **no** — the direction is recorded (fill the gap) |
| Planner | **no** — folded into the implementor brief from the enumerated diff |
| Implementor | **yes** |
| Validator | **yes** — must re-run the extraction and prove the diff is empty; verify both msgids and translations |
| Docs-specialist | **yes** — the `architecture.md` deferral record is updated |

### Objective

Fill the **two** forward-gap msgids in all three catalogs (`ru`/`bs` non-empty, `en` empty per
convention) using a **whole-source-tree scratch extraction**, so a fresh full extraction is a clean
no-op.

### Verified starting state

- The isolated full extraction (Stage-0 audit, `--no-location --no-obsolete`) proves the forward gap is
  **two** msgids in each of `ru`/`bs`/`en` (`tracked=438 extracted=437 ADDED=2 REMOVED=3`):
  - **`+ 'Password does not meet the password policy: %(errors)s'`** — `create_admin_user.py`, `gettext_lazy as _`.
  - **`+ 'Please accept the personal data storage consent first.'`** — from `apps/ads/services/submission.py:229`,
    also at `apps/ads/views/edit.py:153` and `telegram_bot/handlers/ad_create/submit.py:188`. The catalogs
    today hold only the **different** `"To manage ads, please accept the personal data storage consent first."`
    and the `"To contact support…"` / `"To post an ad…"` variants.
  - **REMOVED = 3** — the `_lazy` strings (owned by **B-07**); see the cluster ordering (§C.4).
- The `create_admin_user` deferral is recorded at `docs/99-agent/architecture.md`
  §"Deferred: Untranslated `create_admin_user` Password-Policy Msgid (04-AUT-005)".
- `test_no_empty_msgstr` requires non-empty `ru`/`bs` msgstr for every msgid **present in a catalog**;
  `test_extraction_completeness` compares catalogs to each other (parity); neither is a source→catalog
  check. `test_i18n_completeness.py` returns 30 passed at HEAD.
- `base.py`: `LOCALE_PATHS = [BASE_DIR / "backend" / "locale"]`. `POT-Creation-Date` must stay synced
  across the three catalogs (`test_pot_creation_date_sync`).
- The second msgid is named in **no** problem doc, gate exemption, or `architecture.md` (C-03-1).

### Scope (closed file surface)

| Semantic unit | Change |
|---|---|
| `src/backend/locale/ru/LC_MESSAGES/django.po` | add **both** msgids; non-empty `ru` msgstr |
| `src/backend/locale/bs/LC_MESSAGES/django.po` | add **both** msgids; non-empty `bs` msgstr |
| `src/backend/locale/en/LC_MESSAGES/django.po` | add **both** msgids; `en` msgstr empty (convention) |
| `docs/99-agent/architecture.md` — the `04-AUT-005` deferral section | mark **resolved** with the commit pointer; note the second msgid was not previously recorded |
| `.ai/plans/27-…` (this plan) status | mark B-06 shipped with the commit ref |

### Binding constraints

1. **Extract into a whole-source-tree scratch copy, never in place (C-08-1).** A scratch
   `LOCALE_PATHS` alone does **not** redirect the write. Apply only the enumerated, targeted diff to
   the tracked catalogs by hand — never the raw scratch output verbatim if it contains the `_lazy`
   REMOVED set (that is B-07's concern; do not delete the `_lazy` entries here).
2. **Both msgids are in scope (C-03-1).** The brief enumerates the full extraction diff; a fix
   filling only the password-policy msgid is **incomplete** and leaves `test_no_empty_msgstr` red.
3. **Use `--no-location --no-obsolete` (DRIFT-1)** for every extraction.
4. **`.po`-only change.** No source-code change (both call sites already use `gettext_lazy`).
5. **`POT-Creation-Date` must stay byte-identical across the three catalogs** — one invocation with all
   three locales.
6. **No `--no-obsolete` prune of unrelated entries** here; the `_lazy` entries must survive B-06
   (B-07 decides their fate).
7. **Do not create a second freshness gate** — any durable gate is folded into plan 25 BLOCK 11 (§F.5).
8. **Never modify `.ai/audit/**`.**

### Acceptance criteria

1. **Both** msgids exist in **all three** catalogs; `ru`/`bs` non-empty; `en` empty per convention.
2. **B-06 extraction check = `ADDED=0`** (the forward gap is closed). A fresh full extraction on the
   CURRENT tree still yields `REMOVED=3` (the `_lazy` set) until **B-07** de-aliases — this residual is
   **expected and owned by B-07**, and B-06 must NOT prune those entries. The *full* clean no-op
   (`ADDED=0 AND REMOVED=0`, only `POT-Creation-Date` churn) is **B-07's** acceptance criterion, not
   B-06's. (Boundary established by the B-06 audit note `C-B06-*`.)
3. `test_i18n_completeness.py` and `test_i18n_pipeline.py` are green; the fast gate is green.
4. `docs/99-agent/architecture.md`'s deferral section is marked **resolved** with the commit pointer.
5. No catalog change beyond the enumerated extraction diff (no unrelated re-ordering).
6. No source-code change.

### Test contract

- Existing gates are the contract: `test_no_empty_msgstr`, `test_extraction_completeness`,
  `test_pot_creation_date_sync`, `test_i18n_pipeline.py`.
- **Validator check:** re-run the extraction against a fresh whole-tree scratch copy and prove
  `ADDED=0` **and** that the three `_lazy` entries SURVIVE (the residual `REMOVED=3` is expected pre-B-07).
  Only `POT-Creation-Date` may differ, and it must be equal across the
  three). Quote the command and the empty diff.

### Rollback

Revert the three catalog files (text; no schema) and the `architecture.md` deferral edit. The commit
is one concern; revert by explicit path.

### DoD

- [ ] Both msgids filled in all three catalogs; extraction is a no-op; deferral marked resolved.
- [ ] **Verify, do not assume:** (i) the full extraction diff at this HEAD — re-enumerate it, do not
      trust the Stage-0 snapshot; (ii) that the `_lazy` entries are **not** removed by this block;
      (iii) that `test_pot_creation_date_sync` still passes.
- [ ] `git add src/backend/locale/ru/LC_MESSAGES/django.po src/backend/locale/bs/LC_MESSAGES/django.po src/backend/locale/en/LC_MESSAGES/django.po docs/99-agent/architecture.md`
      — explicit paths only.

---

## B-07 — N-6: `_lazy` alias extraction gap ⚑ CLUSTER 2/3

| Field | Value |
|---|---|
| Source | `.ai/audit/problems/06-lazy-alias-extraction-gap.md` (N-6) |
| Priority | **P0** — removes the root cause the reverse gate currently exempts |
| Risk | **High** — the module is runtime-live; the catalog surface is shared with B-06; the choice (keyword vs de-alias) changes a bot module |
| Depends on | **B-06** (the catalog must be stable before the `_lazy` decision lands) |
| Blocks | B-08 |
| Auditor | **yes** — the aliased-callee inventory must be re-established (`submit.py` is the only one) |
| Researcher | **no** — the direction is recorded; Option B (de-alias) is the smallest root-cause fix and the reference shape (`contact.py`/`support.py`/`permissions.py` use un-aliased `gettext_lazy`) is established |
| Planner | **no** — folded into the implementor brief |
| Implementor | **yes** |
| Validator | **yes** — must run a fresh extraction proving the three msgids are extracted and the lock-timeout tests are green |
| Docs-specialist | **no** — no doc edit beyond the gate comment if the exemption is retired |

### Objective

Apply the ruled fix for the `gettext_lazy as _lazy` alias in
`telegram_bot/handlers/ad_create/submit.py` so the three `_NON_CONTENT_REPLIES` strings are
**extractable**; retire the corresponding extraction-gap exemption.

### Design ruling (recorded; not open)

The problem doc recommends **Option B (de-alias)** — replace
`from django.utils.translation import gettext as _, gettext_lazy as _lazy` with
`from django.utils.translation import gettext as _, gettext_lazy` and replace the three `_lazy(...)`
calls with `gettext_lazy(...)`, matching `contact.py`/`support.py`/`permissions.py`. This is the
smallest fix and removes the root cause. **Option A (`--keyword=_lazy`) is a belt-and-braces
alternative** that must reach xgettext through both the `Makefile` target and `.kilo/rules/commands.md`
and stay in sync — it is **not** the primary fix here. **Option C (permanent exemption) is REJECTED**
without an explicit standardisation ruling. If the Implementor finds the de-alias would break a
runtime path, they must **stop and report** rather than switch to A silently.

### Verified starting state

- `submit.py:20`: `from django.utils.translation import gettext as _, gettext_lazy as _lazy`; call
  sites `:66`, `:70`, `:74` in `_NON_CONTENT_REPLIES` (DRAFT_GONE, INVALID_TRANSITION, PHOTO_UNAVAILABLE).
- `_lazy` appears **only** in `submit.py`; no other module aliases a gettext callee under a non-keyword name.
- xgettext (in-image): `-k_` extracts 6 msgids from `submit.py`; `-k_ -k_lazy` extracts 9 (+3). The alias
  is extraction-blind.
- The three msgids **are present** in all three catalogs today (added pre-rename) and appear in the
  isolated extraction's **REMOVED** set.
- The gate exemption `_EXTRACTION_GAP_MSGIDS` (`test_i18n_completeness.py`) names the three; the gate's
  in-process `_PY_GETTEXT_KEYWORDS` deliberately omits `_lazy` to mirror xgettext; `reverse_orphans`
  exempts them.
- `telegram_bot/tests/test_lock_timeout_boundary.py` renders the DRAFT_GONE reply in `ru`/`bs` — it fails
  if the catalog entry is removed.

### Scope (closed file surface)

| Semantic unit | Change |
|---|---|
| `src/telegram_bot/handlers/ad_create/submit.py` — the import line | de-alias: import un-aliased `gettext_lazy` |
| `src/telegram_bot/handlers/ad_create/submit.py` — `_NON_CONTENT_REPLIES` call sites | `_lazy(...)` → `gettext_lazy(...)` |
| `src/backend/apps/ads/tests/test_i18n_completeness.py` — `_EXTRACTION_GAP_MSGIDS` | retire the three-msgid exemption (or retain with a pointer if the ruling says so); align the comment |
| `.ai/plans/27-…` (this plan) status | mark B-07 shipped with the commit ref |

### Binding constraints

1. **De-alias, do not add a keyword** (the ruling above). No `--keyword=_lazy` plumbing in this pass.
2. **No catalog content change beyond what the de-alias requires.** The three msgids must remain
   present with non-empty `ru`/`bs` msgstr.
3. **Do not remove the three msgids from any catalog.** Removing them breaks the lock-timeout tests.
4. **Retire the exemption** only if a fresh extraction proves the three are extracted without it; if the
   exemption must be retained, record why.
5. **Runtime-live module** — run the bot/lock-timeout tests.
6. **`POT-Creation-Date` stays synced** across the three catalogs.
7. **Do not create a second freshness gate** — plan 25 BLOCK 11 owns the durable one.
8. **Extract into a scratch whole-tree copy only (C-08-1); `--no-location --no-obsolete` (DRIFT-1).**

### Acceptance criteria

1. A fresh full extraction **keeps** the three `_NON_CONTENT_REPLIES` msgids (no removal).
2. `telegram_bot/tests/test_lock_timeout_boundary.py` is green (the three replies render in `ru`/`bs`).
3. The three msgids remain present in all three catalogs with non-empty `ru`/`bs` msgstr.
4. `_EXTRACTION_GAP_MSGIDS` is retired (or retained with a pointer to the ruling); the reverse gate
   stays green.
5. No `gettext_lazy as _lazy` alias remains anywhere in `src/`.
6. i18n gates (`test_i18n_completeness.py`, `test_i18n_pipeline.py`, `test_i18n_category_city.py`) and
   the fast gate are green; ruff/basedpyright clean on the touched module.
7. `POT-Creation-Date` stays synced across the three catalogs.

### Test contract

- The existing `TestProcessPreviewLocalisedErrors` (lock-timeout) tests are the runtime contract.
- A fresh extraction (scratch copy) must show the three msgids **extracted** (not removed).
- The reverse stale-entry gate must pass **without** the exemption (Option B).
- **Do not add a second freshness gate** — plan 25 BLOCK 11 owns the durable one.

### Rollback

Revert `submit.py`, the gate exemption edit, and any catalog touch. No schema, no DB.

### DoD

- [ ] Alias removed; three msgids extractable; exemption retired; lock-timeout tests green.
- [ ] **Verify, do not assume:** (i) that `submit.py` is still the **only** aliased gettext callee
      (re-run the sweep); (ii) the current `_EXTRACTION_GAP_MSGIDS` shape at this HEAD.
- [ ] `git add src/telegram_bot/handlers/ad_create/submit.py src/backend/apps/ads/tests/test_i18n_completeness.py`
      — explicit paths only (plus any catalog path if B-06 left it unchanged and B-07 does not).

---

## B-08 — N-8: `makemessages` guardrail — document the scratch recipe ⚑ CLUSTER 3/3

| Field | Value |
|---|---|
| Source | `.ai/audit/problems/08-makemessages-mutates-tracked-catalogs.md` (N-8), **root cause refined by C-08-1** |
| Priority | **P1** — the hazard is live for every future extraction |
| Risk | **Medium** — documentation + one `Makefile.ps1` target; the real hazard is a helper that *pretends* to redirect the write |
| Depends on | **B-06**, **B-07** (the recipe is documented once the catalog is stable) |
| Blocks | — |
| Auditor | **no** — the C-08-1 mechanism is established; the post-`setup()` override inertness is reproduced |
| Researcher | **no** — the practice is known (isolated whole-tree copy) |
| Planner | **no** — folded into the implementor brief |
| Implementor | **yes** (Docs-specialist for the `.kilo/rules/commands.md` portion) |
| Validator | **yes** — must run the documented recipe and assert `git status --short -- src/backend/locale` stays empty |
| Docs-specialist | **yes** |

### Objective

Document the **safe extraction recipe** (N-8 Option A): copy the **whole source tree** to a scratch
directory outside the working tree, run `makemessages` there, diff against the tracked `.po`, then
apply an enumerated targeted change. Mark the in-place command as "mutates tracked files". Optionally
add a `Makefile.ps1` target that performs the scratch-copy form.

### Verified starting state

- `LOCALE_PATHS = src/backend/locale/{ru,bs,en}/LC_MESSAGES/django.po`; the documented extraction
  command writes there.
- **C-08-1:** assigning `settings.LOCALE_PATHS` (post- **or** pre-`django.setup()`) does **not** redirect
  the write — `makemessages`'s directory walk inserts every discovered `locale/` dir at index 0, so the
  in-tree `src/backend/locale` becomes `default_locale_path`. **Only a whole-tree copy is safe.**
- The isolated-copy pattern is **undocumented** (zero hits for "isolated copy / scratch tree / never in
  place" across `.kilo/**` and `docs/**`).
- CI runs **no** `makemessages`; `.mo` are gitignored.

### Scope (closed file surface)

| Semantic unit | Change |
|---|---|
| `.kilo/rules/commands.md` — the "Extract" section | add the scratch recipe; annotate the in-place command as mutating tracked files |
| `.kilo/rules/commands.md` — the "Lint templates"/commands surface | **read-only here** (B-02 owns it — serialized) |
| `Makefile.ps1` — new scratch-extract target (optional) | performs the whole-tree copy + extraction outside the working tree; follows existing idioms |
| `.ai/plans/27-…` (this plan) status | mark B-08 shipped with the commit ref |

### Binding constraints

1. **The recipe is a whole-source-tree copy (C-08-1).** Do **not** document a naive helper that merely
   sets `LOCALE_PATHS`; it does not redirect the write.
2. **Option A only.** Option B (a non-mutating helper) is **out of scope** unless it beats the
   directory-walk discovery — do not implement a `LOCALE_PATHS`-based helper.
3. **Option C (a durable guard) is FOLDed into plan 25 BLOCK 11** — do not add a competing gate.
4. **Use `--no-location --no-obsolete` (DRIFT-1)** in the documented recipe.
5. **Do not `gitignore` the catalogs** and do not remove the extraction workflow — the catalogs are the
   source of truth.
6. **Serialize `.kilo/rules/commands.md` behind B-02** — one editor at a time on that file.
7. **Never modify `.ai/audit/**`.**

### Acceptance criteria

1. After following the documented recipe, `git status --short -- src/backend/locale` is **empty**.
2. The safe recipe (whole-tree scratch → extract → diff → enumerated targeted change) is written in
   `.kilo/rules/commands.md` (and/or a wrapper), replacing or clearly annotating the in-place command.
3. The recipe uses `--no-location --no-obsolete`.
4. No catalog content change is introduced by this documentation commit.
5. If a `Makefile.ps1` target is added, validation runs it on Windows and quotes the clean-tree result.
6. i18n gates remain green.

### Test contract

- The contract is the **clean-tree proof**: run the documented recipe and assert
  `git status --short -- src/backend/locale` is empty (quoted in the validation note).
- No new pytest test; this is tooling/documentation.

### Rollback

Revert the doc edit and any `Makefile.ps1` target. No code path, no data, no schema.

### DoD

- [ ] Recipe documented (whole-tree copy, C-08-1 mechanism stated); clean-tree proof recorded.
- [ ] **Verify, do not assume:** that the documented recipe actually leaves the tracked tree clean
      (run it; do not trust the note).
- [ ] `git add .kilo/rules/commands.md Makefile.ps1` — explicit paths only (only if a target is added).

---

## B-09 — Final doc pass + fold the freshness gate into plan 25 BLOCK 11

| Field | Value |
|---|---|
| Source | NF-3 §6 Option B, N-6 §5, N-8 §6 Option C (gate folding); pass-wide doc currency |
| Priority | **P2** |
| Risk | **Low–Medium** — documentation; the real risk is *creating a competing gate* |
| Depends on | **B-06**, **B-07** (the gap must be closed before the gate is addable); **B-08** |
| Blocks | — |
| Auditor | **no** |
| Researcher | **no** |
| Planner | **no** — the fold target is named |
| Implementor | **yes** (Docs-specialist) |
| Validator | **no** — a doc-only block; the failure mode (a competing gate) is checkable by reading the diff |

### Objective

Record the pass-wide documentation currency: note that (a) the catalog surface is now stable
(B-06/B-07), (b) the scratch recipe is documented (B-08), and (c) **any durable source-freshness gate
is folded into plan 25 BLOCK 11** — **not** created here. Close the eight problem docs' status where
the pass fixes them, and record **B-03/B-04/B-05 as implemented blocks** (Q1 — no longer design gates).

### Verified starting state

- Plan 25 is shipped (`.ai/plans/done/25-i18n-remediation-execution_done.md`); its BLOCK 11 (commit
  `f7d1ff73`) added the reverse stale-entry gate and `_EXTRACTION_GAP_MSGIDS`.
- The eight problem docs live in `.ai/audit/problems/` and are **untracked audit material** — this
  block does **not** edit them (audit immutability).
- The `13-…`/`27-…` plan-currency surface is this plan file and `docs/99-agent/architecture.md`.

### Scope (closed file surface)

| Semantic unit | Change |
|---|---|
| `docs/99-agent/architecture.md` — the i18n freshness / deferral area | a dated note: gap closed (B-06/B-07), recipe documented (B-08), durable gate **folded into plan 25 BLOCK 11** |
| `.ai/plans/27-…` (this plan) | status header updated; run history recorded |
| any pass-wide doc named by a block's DoD | only as each block requires |

### Binding constraints

1. 🔴 **Do not create a competing freshness gate.** The durable gate belongs to plan 25 BLOCK 11. This
   block **records the hand-off**, it does not build the gate.
2. **`en` stays empty** per convention; no new user-visible strings (no i18n extraction needed).
3. **Do not edit `.ai/audit/**`** — audit material is immutable.
4. Documentation only; no `.py`, no `.po`, no compose, no CI change.
5. If a block took a HOLD or a documented variant, record it here.

### Acceptance criteria

1. `docs/99-agent/architecture.md` records the gap closure and the recipe, with commit pointers.
2. The durable-gate hand-off to plan 25 BLOCK 11 is stated explicitly; **no** new gate exists in this
   pass.
3. This plan's status header reflects the executed blocks.
4. `git diff` shows documentation only — no `.py`/`.po`/compose/CI file touched.
5. No `.ai/audit/**` file is modified.

### Test contract

- The existing i18n gates (`test_i18n_completeness.py`, `test_i18n_pipeline.py`) remain green — this
  block changes no code and no catalog.

### Rollback

Revert the documentation edit. Nothing depends on it at runtime.

### DoD

- [ ] Gap closure + recipe + gate hand-off recorded; no competing gate; audit material untouched.
- [ ] **Verify, do not assume:** that no freshness gate was added anywhere in this pass (grep for a
      new `makemessages`-in-CI step) before recording the hand-off.
- [ ] `git add docs/99-agent/architecture.md .ai/plans/27-multi-problem-remediation-execution.md`
      — explicit paths only.

---

# §C Dependency graph, serial order, and shared-artefact reservations

## C.1 Dependency graph

```
   B-01  NF-1 moderation template (template-only)          [independent]
        │  (uses the NF-5 djlint workaround until B-02)

   B-02  NF-5 djlint importability  ── owns .kilo/rules/commands.md + Makefile.ps1
        │
        v
   B-08  N-8 scratch recipe  ── ALSO needs .kilo/rules/commands.md + Makefile.ps1
        ▲
        │ serialized behind B-02

   ┌── B-03 … B-05 are now IMPLEMENTATION blocks (Q1, §A.0 / §F.2) ───────────────────┐
   │  Each runs Researcher → Implementor → Validator and consumes one Implementor slot.│
   │  They are file-disjoint from the cluster:                                         │
   │                                                                                   │
   │  B-03 NF-2  shared city-fuzzy helper    ── city.py + apps/locations/services/*     │
   │  B-04 NF-4  robust in-repo SLO guard    ── apps/search/tests/test_search_slo.py    │
   │  B-05 N-7   recovery-aware readiness    ── docker-compose.test.yml + entrypoint.sh │
   │        │                                     (+ the SOLE ci.yml edit, if required) │
   └───────────────────────────────────────────────────────────────────────────────────┘
        (each is independent in-pass — no predecessor, no successor)

   ╔═ CLUSTER (serialized): catalog / extraction surface (.po) ══════════╗
   ║  B-06 NF-3 fill both msgids                                         ║
   ║        │                                                            ║
   ║        v                                                            ║
   ║  B-07 N-6  _lazy de-alias + exemption retirement                    ║
   ║        │                                                            ║
   ║        v                                                            ║
   ║  B-08 N-8  scratch recipe (doc)                                     ║
   ╚═════════════════════════════════════════════════════════════════════╝
        │
        v
   B-09  Final doc pass + fold gate into plan 25 BLOCK 11   [doc-only]
```

Edges: `B-02 → B-08` (contended files); `B-06 → B-07 → B-08 → B-09` (cluster); `B-01 → B-02` is a
soft dependency (B-01's djlint check uses the workaround until B-02 lands — it does **not** block
starting B-01). **`B-03`, `B-04` and `B-05` have no in-pass predecessor and no in-pass successor
(they carry no dependents);** the only coupling into the line is the shared serial Implementor slot
(§C.2). The one shared artefact is `.github/workflows/ci.yml`, whose **sole owner is B-05** (§C.3).

**File-disjointness (no order dependency):** B-03 touches
`telegram_bot/handlers/ad_create/city.py` + `apps/locations/services/*`; B-04 touches
`apps/search/tests/test_search_slo.py`; B-05 touches `docker-compose.test.yml` + `docker/entrypoint.sh`
(+ possibly `ci.yml`). No two overlap except the `ci.yml` reservation, owned by B-05 alone.

## C.2 Serial order

| # | Block | Implementor | Why here |
|---|---|---|---|
| 1 | **B-01** | yes | lowest-risk, template-only; confirms the pass's basic machinery (fast gate, djlint) before riskier work |
| 2 | **B-02** | yes | the shared-doc reservation (`.kilo/rules/commands.md`, `Makefile.ps1`) is claimed **before** B-08 needs it; the documented djlint command is broken now |
| 3 | **B-03** | yes | first promoted implementation block; **file-disjoint** from the ci.yml owner (B-05) and from the cluster, so it runs before them and clears the medium-risk bot-path change while the ci.yml reservation is unclaimed |
| 4 | **B-04** | yes | robust SLO guard is a closed single-test edit; runs before the ci.yml owner (B-05) so the test shape is final before any CI-touchpoint discussion |
| 5 | **B-05** | yes | **owns the sole `ci.yml` edit** (if needed) — placed **after** B-04 so the SLO shape is settled first; its CI-parity change then lands last among the ci.yml-adjacent blocks |
| 6 | **B-06** | yes | **cluster start** — the catalog must be stable and complete (both msgids) first |
| 7 | **B-07** | yes | **cluster middle** — the `_lazy` fix changes what a fresh extraction keeps; must follow B-06 |
| 8 | **B-08** | yes | **cluster end** — the scratch recipe is documented once the catalog is stable; consumes the doc surface released by B-02 |
| 9 | **B-09** | yes | final doc-only pass; depends on the cluster outcome; records the plan-25 gate hand-off |

**One Implementor at a time, no exceptions.** B-03, B-04 and B-05 now each carry an Implementor and
consume a slot in the single serial line — they are no longer research-only asides. Their A-vs-B/vs-C
options are resolved **inside** each block by its Researcher (recorded as an internal decision note) so
the decision never stalls the serial line. B-03/B-04/B-05 are file-disjoint (§C.1) but still serialize
because only one Implementor runs at a time; B-05 is the single `ci.yml` owner, so any CI edit it makes
cannot race another block.

## C.3 Shared-artefact reservation table

| File / artefact | Blocks touching it | Single owner | Ordering rule |
|---|---|---|---|
| `src/backend/templates/admin/moderation/review.html` | **B-01** (only) | **B-01** | No contention. Template + its test only. |
| `.kilo/rules/commands.md` | **B-02** (Lint templates), **B-08** (Extract) | **B-02** (first write), then **B-08** | **Strictly serial: B-02 → B-08.** Different sections, but one editor at a time on the file. |
| `Makefile.ps1` | **B-02** (`lint-templates`), **B-08** (optional scratch-extract target) | **B-02** (first write), then **B-08** | **Strictly serial: B-02 → B-08.** Each adds one target; preserve line-ending reality. |
| `pyproject.toml` | **B-02** (comment only) | **B-02** | Comment-only; no build-system. |
| `src/backend/locale/{ru,bs,en}/LC_MESSAGES/django.po` | **B-06**, **B-07** | **B-06** (first write), then **B-07** | **CLUSTER — never concurrent.** B-06 adds the two forward-gap msgids; B-07 must not delete the `_lazy` entries or the three orphaned strings. Extraction is scratch-only (C-08-1). |
| `src/backend/apps/ads/tests/test_i18n_completeness.py` | **B-07** (exemption), maybe **B-09** (read-only) | **B-07** | B-07 retires/retains `_EXTRACTION_GAP_MSGIDS`; B-09 does not add a gate. |
| `telegram_bot/handlers/ad_create/city.py`, `apps/locations/services/city_suggestions.py`, `apps/locations/services/city_fuzzy.py`, `apps/locations/tests/test_city_suggestions.py`, `telegram_bot/tests/test_city.py` | **B-03** (only) | **B-03** | No contention — file-disjoint from every other block. |
| `src/backend/apps/search/tests/test_search_slo.py` | **B-04** (only) | **B-04** | No contention — single-test file. |
| `.github/workflows/ci.yml` | **B-05** (sole owner, only if CI parity requires it) | **B-05** | **Single owner.** B-04 must NOT edit `ci.yml` (no p95-gate duplication); if B-05 makes a CI edit it is minimal and enumerated. No two blocks touch `ci.yml`. |
| `docker-compose.test.yml`, `docker/entrypoint.sh`, `docker-compose.yml` (reference) | **B-05** (only) | **B-05** | No contention — N-7 surface. Base `docker-compose.yml` is reference-only unless parity requires it. |
| `docs/99-agent/architecture.md` | **B-06** (deferral), **B-09** (final note) | **B-06** (first write), then **B-09** | Serial: B-06 → B-09. |
| `.ai/audit/**` | **nobody** | — | **Immutable.** No block reads-or-writes audit material as a deliverable; never modified. |

## C.4 NF-3 / N-6 / N-8 serialized-cluster rationale

NF-3, N-6 and N-8 all operate on the **same physical surface** — the tracked `.po` catalogs and the
extraction that regenerates them — so they cannot run concurrently and their order is load-bearing.
The single isolated extraction taken by the Stage-0 audit (C-03-1) shows the coupling directly:
`ADDED=2` (NF-3's two msgids) and `REMOVED=3` (N-6's three `_lazy` strings) in the **same** diff, and
N-8 establishes that any in-place extraction **mutates** the very files all three depend on.

The order **B-06 → B-07 → B-08** is chosen because each step's *post-condition* is the next step's
*precondition*:

1. **B-06 (NF-3) first** — the catalog must be **complete** (both forward-gap msgids present) and the
   tree **clean** before any extraction is used as an authority. If B-07 ran first, its extraction-based
   proof would still be contaminated by B-06's unresolved gap, and its "no-removal" claim would be
   measured against an incomplete baseline.
2. **B-07 (N-6) second** — the root-cause fix (de-alias) changes **what a fresh extraction keeps**: once
   `gettext_lazy` is un-aliased, the three `_NON_CONTENT_REPLIES` strings stop appearing in the REMOVED
   set and the exemption can be retired. This step necessarily follows B-06 because a fresh extraction
   is its verification instrument, and that instrument is only authoritative once the catalog is
   complete.
3. **B-08 (N-8) last** — documenting the scratch recipe is only meaningful once the catalog is stable,
   because the recipe's whole purpose is to measure *future* extraction diffs against a *clean, complete*
   baseline. B-08 also consumes the `.kilo/rules/commands.md` + `Makefile.ps1` reservation, which B-02
   releases first. Placing B-08 last also means the documented recipe is validated against a tree that
   B-06/B-07 just proved extract-clean.

Running them out of order — e.g. B-07 before B-06, or B-06/B-07 concurrently — would produce a
non-authoritative extraction diff and risk deleting the runtime-live `_lazy` entries (a `ru`/`bs`
seller-visible regression).

---

# §D Risks, ranked, with containment

| Rank | Risk | Where | Containment |
|---|---|---|---|
| 1 | 🔴 **An extraction mutates the tracked `.po` files in place** (`makemessages` has no dry-run) | B-06, B-07 | **Whole-source-tree scratch copy only** (C-08-1); the post-/pre-`setup()` `LOCALE_PATHS` override is inert and is **forbidden** as a redirect; B-08 documents the safe recipe; Validator asserts `git status --short -- src/backend/locale` empty |
| 2 | 🔴 **B-06 fills only the password-policy msgid**, producing a still-non-empty extraction diff and a red `test_no_empty_msgstr` | B-06 | **C-03-1** widens B-06 to **both** msgids; the brief enumerates the full diff; AC2 requires the extraction to be a clean no-op |
| 3 | 🔴 **B-07 deletes the runtime-live `_lazy` entries** (or the `ru`/`bs` seller-visible regression) | B-07 | De-alias (not keyword) is the ruled fix; the three msgids must stay present; lock-timeout tests are the runtime contract; Validator runs a fresh extraction |
| 4 | 🔴 **A competing freshness gate is created** instead of folding into plan 25 BLOCK 11 | B-06, B-07, B-08, B-09 | §A.4 **FOLD**; every block restates "do not create a second gate"; B-09 records the hand-off; DoD greps for a new CI `makemessages` step |
| 5 | 🔴 **NF-4's wrong fix** — raise the bound / delete / blind `xfail` removes the only in-repo latency guard | B-04 | B-04 now **implements** the Q4 robust guard (warm-up + median of N ≥ 5); the raise/delete/`xfail` "wrong fix" stays **forbidden**; any bound change carries its derivation; the load-test p95 job stays the sole percentile instrument and `ci.yml` is not duplicated |
| 6 | 🔴 **N-7's fix masks a genuinely dead DB** with an unbounded retry, or the recovery window is copied from plan 25 rather than re-measured | B-05 | B-05 now **implements** the recovery-aware readiness fix: **bounded** retries with a clear error on exhaustion; the **forced-recreate measurement** (N ≥ 3) is the validation contract and the window must be **re-derived**, never copied |
| 7 | 🔴 **NF-2's shared helper regresses bot city UX** — a mixed-up or assumed candidate list (localized names vs slugs), a changed `0.6`, or a lost `get_city_by_name` re-lookup | B-03 | Candidate injection is **mandatory** (names at the bot call site, slugs at the web); `CITY_FUZZY_CUTOFF = 0.6` must not change; the bot's re-lookup is preserved; a behavior-level boundary test guards it |
| 8 | **NF-5 Option A (packaging) is adopted**, disturbing pytest import roots / Docker `--no-install-project` | B-02 | Option A is **REJECTED** for this pass (§F.3); B-02 is Option B only; the `pyproject.toml` edit is comment-only |
| 9 | **A naive `LOCALE_PATHS` helper is documented as safe** | B-08 | C-08-1 names the mechanism; B-08 constraint 1 forbids it; only a whole-tree copy is documented |
| 10 | **`.kilo/rules/commands.md` / `Makefile.ps1` edited by two blocks concurrently** (B-02, B-08) | B-02, B-08 | Reservation table C.3: **B-02 → B-08 strictly serial** |
| 11 | **`ci.yml` edited by two blocks, or the p95 gate duplicated/removed** | B-04, B-05 | Reservation table C.3: **B-05 is the sole `ci.yml` owner**; B-04 must not edit `ci.yml`; the load-test p95 job stays the percentile instrument |
| 12 | **NF-1's keep-vs-retire decision is taken by an Implementor** | B-01 | Defaulted to Option A in §B-01; retiring is an explicit product ruling (§F.1); constraint 4 forbids retirement |
| 13 | **Line endings mixed into `Makefile.ps1`** | B-02, B-08 | Constraint in both blocks; check `git diff --stat` for a whole-file rewrite |
| 14 | **A stale fact from §A/§B is copied verbatim into production docs** | all | Every DoD carries a "verify, do not assume" list naming the facts to re-derive |
| 15 | **Over-agenting** — research cycles spent where uncertainty was already resolved in §A.4 | all | `Auditor/Planner = no` with a one-line reason in most blocks; the Researcher is scoped to resolving the option inside its own block (B-03 A-vs-B, B-04 shape/derivation, B-05 A/B/C), not to emitting a standalone artifact |
| 16 | **A promoted implementation block is (mis)treated as decision-only and emits a record instead of landing the fix** | B-03, B-04, B-05 | §A.0 Q1 and §F.2 record the promotion; each block is `type: implementation` with an Implementor, Validator and `files`/`changes`/acceptance criteria; a Validator reviews each |

---

# §E Whole-set Definition of done

Applies to the pass as a whole, not to any single block.

1. **All 9 blocks are B-01 … B-09, executed in §C.2 order, one Implementor at a time.**
2. **The NF-3/N-6/N-8 cluster ran strictly B-06 → B-07 → B-08, never concurrently.**
3. **No `makemessages` ran against the tracked working tree.** Every extraction used a whole-source-tree
   scratch copy; `git status --short -- src/backend/locale` is empty after B-06, B-07 and B-08.
4. **Both forward-gap msgids are in all three catalogs** (`ru`/`bs` non-empty, `en` empty), and a fresh
   full extraction is a clean no-op (only `POT-Creation-Date`, kept synced).
5. **No `gettext_lazy as _lazy` alias remains in `src/`**, the three `_NON_CONTENT_REPLIES` strings are
   extractable, and the `_EXTRACTION_GAP_MSGIDS` exemption is retired or retained with a pointer.
6. **The scratch extraction recipe is documented** in `.kilo/rules/commands.md` (and/or a wrapper),
   stating the C-08-1 mechanism.
7. **No competing freshness gate was created**; the hand-off to plan 25 BLOCK 11 is recorded.
8. **NF-1's five references are named `{% url %}` tags** and a regression test asserts them from both
   render origins using `reverse()`.
9. **The documented djlint command succeeds and H901 still fires** for a multi-line `{# … #}` inside the
   project template tree.
10. **NF-2, NF-4 and N-7 are remediated in this pass** (Q1): B-03 lands the shared city-fuzzy helper
    (B-04) lands the robust in-repo SLO guard (warm-up + median of N ≥ 5, `ci.yml` untouched), and
    (B-05) lands the recovery-aware test-DB readiness fix (bounded retries; `ci.yml` edited only if
    parity requires it, by B-05 alone). Each block ran Researcher → Implementor → Validator.
11. **Git hygiene:** every commit used `git add <explicit paths>`. No `-A`, no `.`, no `<dir>`, no
    `git reset`, `git checkout` or `git stash`.
12. **Every "verify, do not assume" item** was either verified or reported as unverified.
13. **Fast test gate green** (`.\Makefile.ps1 test`) for every block touching Python/i18n; lint clean on
    every touched Python path; the i18n gates green.
14. **No `.ai/audit/**` file was modified**, and no existing plan/task file under `.ai/plans/done/` or
    `.ai/tasks/` was touched.

---

# §F Deferred / not executable in this pass

Each entry names the reason and the **re-entry condition**. Nothing here is silently dropped.

## F.1 NF-1 — retire/link the moderation review page

| Field | Value |
|---|---|
| Item | NF-1 Option C (retire: delete template + views + urls + tests) or "keep and link" from the queue |
| Status | **RESOLVED by Q2 — keep the page, fix the URLs (Option A). No retire; no new queue link.** |
| Reason | Product ruling Q2 (2026-10-06): the page is kept and its references are fixed with named `{% url %}` tags. Linking the queue to the page was declined. |
| Re-entry condition | A future product ruling to retire or link the page authorises the wider surface (template + views + urls + tests). |

## F.2 NF-2 / NF-4 / N-7 — implementation blocks (promoted from design gates)

| Field | Value |
|---|---|
| Item | The implementation of the NF-2 (B-03), NF-4 (B-04) and N-7 (B-05) decisions |
| Status | **IN SCOPE (Q1) — no longer deferred.** B-03/B-04/B-05 are promoted from decision-only records to full implementation blocks: each runs Researcher (resolve the option) → Implementor → Validator. |
| Reason | Product ruling Q1 (2026-10-06): the pass must remediate all eight findings, not emit decision records for three of them. The Researcher still resolves the A-vs-B (vs C) choice inside each block; the Implementor then lands the chosen option. |
| Re-entry condition | n/a for this pass — these blocks carry an Implementor. The design choice remains the Researcher's, recorded as a decision note that the Implementor executes. |

## F.3 NF-5 — Option A (packaging / `[build-system]`)

| Field | Value |
|---|---|
| Item | Making `djlint_custom_rules` importable without `PYTHONPATH` by adding a `[build-system]` / editable install |
| Status | **Rejected for this pass** |
| Reason | It changes the packaging model for every tool: pytest's `--import-mode=importlib` roots (`pythonpath = ["src", "src/backend"]`) and Docker's `--no-install-project` model must be re-validated first. NF-5 itself recommends B now and A only if a Researcher proves it safe. |
| Re-entry condition | A dedicated packaging plan that prices the split-layout risk and proves pytest import roots and the Docker non-install model are unaffected. |

## F.4 N-8 — Option B (non-mutating helper) and Option C (durable guard)

| Field | Value |
|---|---|
| Item | A `makemessages` helper that redirects the write, and a durable guard against a dirty tree |
| Status | **Option B out of scope; Option C folded into plan 25 BLOCK 11** |
| Reason | Option B requires a mechanism that beats the directory-walk discovery (C-08-1); the naive `LOCALE_PATHS` override is inert and would be a false safety. Option C is a durable freshness gate — plan 25 owns the catalog-gate design and its exemption sets; a second gate would compete. |
| Re-entry condition | For B: a proven redirect mechanism (a management-command wrapper or a whole-tree copy enforced in code). For C: land in plan 25's BLOCK 11 series, not here. |

## F.5 NF-3/N-6/N-8 — the durable source-freshness CI gate

| Field | Value |
|---|---|
| Item | A CI step that extracts in a scratch copy and fails on a non-empty diff |
| Status | **Folded into plan 25 BLOCK 11 — not created here** |
| Reason | Plan 25 owns the catalog-gate design, its exemption sets and its ordering. NF-3's own Option B says to fold it there; adding a competing gate in this pass would fracture that ownership. This pass **makes the gate addable** by closing the extraction gap; it does not add the gate. |
| Re-entry condition | The plan-25 owner extends BLOCK 11 to include a source-freshness check, safe under C-08-1, referencing the recipe documented in B-08. |

---

**End of plan.** 9 blocks · one Implementor at a time · **all nine blocks carry an Implementor**
(B-03/B-04/B-05 promoted from design gates to implementation blocks by Q1, §A.0 / §F.2) · 1 serialized
catalog/extraction cluster (B-06 → B-07 → B-08, justified in §C.4) · 1 product decision left open
(NF-1, §F.1) · options resolved inside each block by its Researcher (NF-2 A-vs-B, NF-4 robust-guard
shape, N-7 A-vs-B-vs-C, §F.2) · corrections C-03-1 / C-08-1 / DRIFT-1 folded into §A.4 · the durable
freshness gate folded into plan 25 BLOCK 11 (§F.5).
