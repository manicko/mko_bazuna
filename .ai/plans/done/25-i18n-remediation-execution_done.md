---
plan_id: "25-i18n-remediation-execution"
phase: "14"
phase_name: "i18n / Internationalization"
title: "Phase 14 remediation — re-scoped execution plan"
date: "2026-10-05"
planner: "Planner (subagent)"
status: "planned"
supersedes_for_execution: ".ai/plans/14-i18n-remediation.md (anchor d42f778) — this document, NOT the source plan, is the execution contract"
source_plan: ".ai/plans/14-i18n-remediation.md"
source_plan_anchor_commit: "d42f778"
source_audit: ".ai/tmp/code-context-phase14-r2.md"
audit_head_commit: "7f43e535"
drift_span: "3410-line source plan written at d42f778; tree measured at 7f43e535 after every phase 03/04/05/06/07/08/09/10/12/13 block"
findings_in_scope: 23
findings_source_validated: 19
findings_new_from_planner: 4
phase14_blocks_shipped: 0
blocks_live: 12
blocks_cancelled: 1
migration: "none"
implementor_concurrency: 1
---

# Execution Plan — Phase 14 Remediation (i18n) · RE-SCOPED

## 0. Header, provenance and scope statement

### 0.1 Provenance

| Item | Value |
|---|---|
| **Source plan** | `.ai/plans/14-i18n-remediation.md` — 3410 lines, written at anchor `d42f778`. Consulted for block detail (findings owned, constraints, symbol maps, gate option sets). **Not amended.** |
| **This document** | The execution contract. Where this document and the source plan disagree on a *measured value*, **this document wins**. Where they disagree on a *gate*, **the gate is neither closed nor re-opened here** |
| **Source audit** | `.ai/tmp/code-context-phase14-r2.md` — re-measurement round 2, static inspection + read-only `.po` parsing at `7f43e535`. No test run, no `makemessages`/`compilemessages`, no git mutation |
| **Audit HEAD** | `7f43e535` — `docs(perf): describe what the profiler now does and the sweep's cost (13-PERF-015)` |
| **Date** | 2026-10-05 |
| **Phase-14 blocks shipped** | **ZERO.** No `14-I18N-0NN` commit exists in `--all`. Every one of the 12 live blocks is unstarted |
| **BLOCK 13** | **CANCELLED** 2026-10-03 (`Q2` → Option A). No commit, no branch, no worktree residue. **BLOCK 12 is the sole home of `14-I18N-013`** |
| **Findings in scope** | **23 units**: the 19 validated units of the source plan (15 `14-I18N-001`…`-015` + 4 `VAL-001`…`-004`) plus 4 Planner-new (`N-1`…`N-4`) |
| **Execution blocks** | **12 live** — 3 `mechanical`, 5 `behavioural`, 2 `structural`, 1 `conditional`, 1 mixed (`behavioural` + `mechanical`); plus 1 `CANCELLED` |
| **Implementor concurrency** | **1**, strictly sequential (`.kilo/rules/commands.md`: *only 1 implementor agent is allowed at a time*). One commit per block. Commit form: `"{type}({scope}): {description}"` |
| **Migration** | **none.** No block ships a schema change and no block allocates an `AdvisoryLockId` |
| **Blocks that WRITE `.po`** | **3**: BLOCK 9 (`bs` only), BLOCK 10 (all three), BLOCK 4 (**conditional** — only if the `blocktrans`→`trans` change alters an extracted msgid). **`.po`-READING but not writing: BLOCKS 7 and 11.** BLOCK 13, the cancelled limb, is excluded |
| **Naming convention** | Every citation of this phase's own findings is cycle-scoped **`14-I18N-0NN`**, never a bare `I18N-0NN`, wherever it survives into a comment, docstring, test name, tracker entry or commit message |
| **Task targets** | **Semantic only** — file path plus class / function / method / template block / make target / markdown section / msgid. **A line number is never a target in this plan.** `N-4`'s rot is ~105 lines on the document BLOCK 12 edits, so positional targets are not merely stale, they are wrong by two orders of magnitude |

**The headline is unchanged by this re-scope.** This is not a bulk-translation project. The real
measurable Bosnian debt is **3 strings** and it is gated. Everything else is engineering: one
middleware branch, a type boundary at **18** signatures, one formatting helper, one settings line,
one parser return type, three collectors, one template interpolation, one cookie call, one
docstring, one `.po` prune, two gate assertions, one document.

**What actually drifted between the source plan and the audit HEAD is five measured numbers, one
under-counted surface, one under-stated severity, and one class of stale citation.** §2 disposes
of each block against that drift; §3 re-states the catalogue baseline. No new work is invented here
because a measurement moved.

### 0.2 Command contract (binding on every block)

| Situation | The working command |
|---|---|
| Tests — **always Docker, never `uv run pytest` on this host** | `.\Makefile.ps1 test` (fast gate, skips the nightly `seed` suite) · `.\Makefile.ps1 test-all` · `.\Makefile.ps1 test-down` |
| Targeted run | `$dc run --rm -e PYTEST_OPTS="-k some_test_name" test`. **`PYTEST_OPTS` is unquoted** in `docker/entrypoint-test.sh`, so only **bare file paths and single-token flags** work. A quoted multi-token value (`-k "a b"`) does not. Setting `PYTEST_OPTS` also *replaces* the defaults, losing xdist parallelism and `--reuse-db` |
| `make makemessages` / `make compilemessages` | **DO NOT WORK** on this Windows host + Docker Desktop. Use the one-shot form: `$dev run --rm --no-deps --entrypoint "" web python src/backend/manage.py makemessages -l ru -l bs -l en --no-location` (BLOCK 10 adds `--no-obsolete`) |
| Lint / typecheck / template lint | `uv run ruff check <path>` · `uv run basedpyright <path>` · `uv run djlint src/backend/templates/` |
| Git | **Read-only.** No `add`, `commit`, `reset`, `checkout`, `stash`, `restore`. Stage **by path**, never by directory — `config/settings/base.py` and the three `.po` files are contended |

### 0.3 Hard prohibitions, every block

- **Never edit `src/backend/conftest.py`.**
- **Never edit a `.mo` file, and never `git add` one.** `.mo` is gitignored; it is compiled at image
  build, at container start and in the CI `i18n` job.
- **Never add `LocaleMiddleware`, a `set_language` view, or `i18n_patterns`.** The module docstring
  in `LanguagePreMiddleware` explains why `LocaleMiddleware` is intentionally absent.
- **Never add a `Vary` header.** `14-I18N-012` exists because the code is already correct.
- **Never hard-code a file count, a template count, a msgid count or a catalogue count** in any
  assertion. The source plan's own numbers (38 templates, 408/445 empty `msgstr`, 6/6/0 obsolete,
  ~192 model-metadata entries) are all stale. Every guard derives its expectation.
- **Never choose a gate option.** §5 is the decider's list, not the Implementor's.
- **Never write Bosnian text.** Machine output, translation APIs and "approximating" are all
  forbidden by the 2026-10-03 ruling (`Q1`) and by project rule 1.
- **No `print()`** — `logger = logging.getLogger(__name__)`. English only, everywhere.

---

## 1. Reconciliation against the audit

Twelve live blocks. **All twelve are still needed.** What changed is not *whether* but *what exactly*,
in four cases. Four blocks are **re-scoped** (correct deliverable, corrected surface or severity),
and three carry a **binding constraint that was factually false at the source plan's anchor and is
false now** — those are rewritten verbatim in §1.2 and carried into the owning block.

| # | Block | Class | Disposition | Re-scoped as |
|---|---|---|---|---|
| 1 | One locale resolver (`14-I18N-001` limb 1, `-015`, `-002`) | behavioural | **still needed** | Premises reproduce byte-for-byte: raw cookie read in `process_request`, unvalidated `_set_language_code`, `split(",")[0]` in `_parse_accept_language`, raw request attribute in `category_submenu`'s cache key. One addition: the stray double blank line inside the class body is pre-existing lint rot this block will inherit and be blamed for — clear it in passing |
| 2 | `LanguageLocale` at the accessors and filters (`14-I18N-001` limb 2) | structural | **still needed + RE-SCOPED · premise false** | Surface is **18 signatures, not 10**, and there is a **second anti-pattern the source plan never names**. §1.2 constraint **BC-1** |
| 3 | Price formatting + `bs` grouping (`14-I18N-003`, `VAL-004`) | behavioural | **still needed** | `_format_amount` still builds `format(rounded, "f")` and passes a `str` to `intcomma`; Django's bundled `bs/formats.py` still leaves `NUMBER_GROUPING` commented out; no project `FORMATS` override exists. `Q3` untouched by any phase. Premises verified — no correction |
| 4 | Active-price filter chip (`14-I18N-010`) | mechanical | **still needed + RE-SCOPED** | Defect unchanged: the chip interpolates raw `Decimal`s through `{% blocktrans %}`. **Citation rot only** — the source plan's *"fourteen lines below"* is now ~97 lines. The semantic target (the in-file purpose-chip pattern) is unambiguous and unchanged; the citation is dropped, not copied |
| 5 | `TIME_ZONE` + four display date patterns (`14-I18N-004`) | mechanical | **still needed** | **Fully verified, unblocked.** `TIME_ZONE`/`USE_TZ` absent from every settings module; `TIME_ZONE` not in `ALLOWED_ENV_VARS`; the `\|date:` inventory is exactly 6 — 2 correct ISO `datetime=` attributes and 4 defective display patterns. `Q4` still holds. **The only block that needs no correction** |
| 6 | `lang_pref` one writer + hardened flags (`14-I18N-009`/`-011`/`-012`) | behavioural | **still needed** | `set_cookie` still supplies no `secure`/`samesite`/`httponly`; the switcher's inline JS still writes inside `{% if consent_preferences %}` with a hard-coded `SameSite=Lax`. The two writers still disagree. `Q5` still open, phase-06 boundary |
| 7 | Plural-aware `.po` parser (`14-I18N-005`) | behavioural | **still needed + RE-SCOPED** | Defect byte-identical: last-form-only accumulation while the docstring claims "first". 🔴 **The source plan's severity label "Latent" is wrong — it is LIVE.** `en` ships 2 plural entries with **both forms blank** and **2** forms where `ru`/`bs` have **3**. Severity raised; deliverable and ordering unchanged |
| 8 | Collector widening + `hreflang` include (`14-I18N-006`/`-007`/`-008`) | behavioural | **still needed + RE-SCOPED** | Premise holds: `lifecycle.py` still holds 12 non-gettext `BotCommand` literals and `exclude_subpaths` is unchanged (load-bearing). **The gate module has grown to 1099 lines** and already carries `test_no_hardcoded_js_strings`, `test_hreflang_present` with its `x-default` assertion, and eight other tests the source plan does not enumerate — the change table must be **re-derived against the current file**. `Q9`'s widened run was never executed |
| 9 | `msgstr` script gate + three `bs` strings (`N-1`) | conditional | **still needed (reduced deliverable)** | All three strings unchanged; `bs` still holds exactly one Cyrillic-bearing `msgstr`. `Q1` stays `OPEN-PENDING-REVIEWER`. Detection half ships; the string half does not |
| 10 | `--no-obsolete` + one-shot prune (`14-I18N-014` limb 1, `N-2`) | mechanical | **still needed + RE-SCOPED · premise false** | `Makefile`'s `makemessages` invocation still omits `--no-obsolete`. 🔴 Its constraint *"en has 0 obsolete entries today"* is **already false — `en` has 1**. §1.2 constraint **BC-2** |
| 11 | Reverse stale-entry gate + obsolete symmetry (`14-I18N-014` limb 2, `N-2`) | mechanical | **still needed + RE-SCOPED · premise false** | Only `POT-Creation-Date` is gated today. 🔴 The invariant is **`7/7/1`, not `6/6/0`**, and the *shape* changed. §1.2 constraint **BC-3** |
| 12 | `i18n-spec.md` back in line (`N-3`, `N-4`, `14-I18N-013` Option A) | mechanical | **still needed** | 3 dead link targets still referenced 5×; the whole `docs/96-researches/` directory still absent; line rot now ~105 lines and worse; the model-metadata exemption is still unwritten. 🟡 `docs/99-agent/` has grown 5 → 9 files, so `Q11` option (b)'s pricing changed — **the option set is unchanged, its cost is not** |
| ~~13~~ | `14-I18N-013` Option B | — | **CANCELLED 2026-10-03** | Does not run. No task, no commit, no file. `Q2` resolved to Option A; BLOCK 12 is the sole home of `14-I18N-013`. Option B is **declined**, not deferred |

### 1.1 Departures from the source plan, and why

| # | Departure | Reason |
|---|---|---|
| D-1 | **BLOCK 7's severity rises from "latent" to live.** | Measured: `en` has 2 plural entries with both forms blank and 2 forms where `ru`/`bs` have 3. The "last form only" parser therefore reads a blank final form and reports an untranslated-by-convention entry as if it were the only form, while silently discarding forms 0 and 1 for `ru`/`bs`. The deliverable does not change; the label does, and BLOCK 11's ordering edge becomes load-bearing rather than tidy |
| D-2 | **All four proposed *new* test modules are folded into existing per-finding modules.** | The source plan opens `test_i18n_helpers_unit.py`, `test_i18n_bot_scope_unit.py`, `test_i18n_msgstr_script_unit.py` and `test_i18n_stale_entry_unit.py`. Four new files for four findings fragments the gate and buries each guard next to a module nobody opens. `testing/i18n_helpers.py` has exactly **two** callers today — `test_i18n_completeness.py` and `test_i18n_pipeline.py` — so both existing modules already import it. Destinations: parser unit → `test_i18n_pipeline.py`; collector + script-rule + synthetic-orphan guards → `test_i18n_completeness.py`. **No new test module is created, and `conftest.py` is never touched** |
| D-3 | **BLOCK 8's change table is re-derived, not inherited.** | The gate module grew to 1099 lines and now contains `test_no_hardcoded_js_strings`, `test_hreflang_present` (with its `x-default` assertion), `test_bot_no_hardcoded_messages`, `test_no_cyrillic_msgids`, `test_bot_no_raw_model_field_access`, `test_title_tags_translated`, `test_plural_forms`, `test_plural_forms_runtime`, `test_locale_switch_re_render` — none enumerated by the source plan. The Implementor re-reads the module and re-derives insertion points before editing |
| D-4 | **The source plan's numeric claims are quoted as numbers-never-to-hard-code, and their corrected values are carried in §3 only.** | `en` empty-`msgstr` moved 408 → 445 singular; obsolete 6/6/0 → 7/7/1; templates 43 → 38. Every one of them is a documentation artefact, not an assertion input. Repeating a measured catalogue number into prose is how the next reader inherits rot |
| D-5 | **BLOCK 2 keeps its `Q6` gate rather than absorbing option (a).** | The widened surface (27 filter-arg call sites; 20+ `&lang={{ LANGUAGE_CODE }}` URL renders) makes option (a)'s consequences materially larger than when the options were priced. Choosing now would be choosing on stale prices. §5 states the enlarged consequence set; the decision stays with the decider |

### 1.2 The three false binding constraints, rewritten

Each of these is quoted from the source plan at `d42f778` and is **factually false at `7f43e535`**.
An Implementor following the original text either reports a false pre-existing violation, skips the
deletion the block exists to perform, or encodes the wrong invariant. **The corrected text below is
binding and replaces the original.**

---

#### BC-1 — BLOCK 2's surface is 18 signatures, not 10, and there is a second unnamed anti-pattern

> **Source plan (false):** *"All ten are currently typed `locale: str = LanguageLocale.RUSSIAN`."*
> File surface lists 5 model accessors + 5 template filters and nothing else.

**Corrected, binding:**

- The surface is **18 Python signatures across 11 files**, not 10 across 6.
- The **plan's ten** are `Category.get_name`, `City.get_name`, `LookupItem.get_name`,
  `Ad.get_title`, `Ad.get_description`, and the five `localized_content` template filters
  (`get_title`, `get_description`, `get_lookup_name`, `get_category_name`, `get_city_name`).
- The **eight the plan omits** carry the *same* `locale: str = LanguageLocale.RUSSIAN` signature:
  three in `telegram_bot/services/ad_data/keyboards.py`, one in
  `telegram_bot/services/ad_data/feature_helpers.py`, two in
  `search/services/entity_suggestions.py`, one in `search/services/immediate_alerts.py`, one in
  `search/management/commands/send_alerts.py`.
- 🔴 **Second anti-pattern, unnamed by the plan:** `immediate_alerts.py` and `send_alerts.py` default
  their `locale` parameter to **`LanguageLocale.RUSSIAN.value`** — a bare `str` — not to the enum
  member the other sixteen use. Tightening ten of eighteen while leaving these two produces a
  boundary that is **stricter in the templates and looser in the bot and alert services.** Those two
  are in scope.
- **Template consequence, also unnamed by the plan:** `context_processors.language` is registered once
  in `config/settings/base.py`. Its output key `LANGUAGE_CODE` is consumed **55 times across 16
  templates** — **27** of them as filter arguments (`|get_title:LANGUAGE_CODE`,
  `|get_city_name:LANGUAGE_CODE`, `|get_lookup_name:LANGUAGE_CODE`, …), and **20 or more** as
  `&lang={{ LANGUAGE_CODE }}` appended to `hx-get` / `href` / `hx-push-url` URLs in the shared ad-list
  partial, plus one echoed into the switcher. **There are zero Python consumers of the processor's
  output.** Under option (a) the processor emits `LanguageLocale`, and those URL renders go through
  `str()` on the enum — a silent surface the plan never lists. `language_switcher.html`'s own doc
  comment claims it reads the value from the processor, so it is in scope for re-reading.

---

#### BC-2 — BLOCK 10: `en` has **1** obsolete entry, and `--no-obsolete` does not delete

> **Source plan (false), stated twice at `d42f778`:** *"`en` has 0 obsolete entries today and must
> still have 0 after. The end state is obsolete-free in all three; the asymmetry is what this block
> resolves."*

**Corrected, binding:**

- The measured obsolete counts are **`ru` 7 / `bs` 7 / `en` 1**. `en` is **not** at 0, so "must still
  have 0 after" is **already violated at block entry** and the "already 0 → must stay 0" framing
  mis-describes the flag.
- 🔴 **`--no-obsolete` is preventive, not a deleter.** It stops `makemessages` from *writing* new
  `#~` blocks; it does **not** remove pre-existing ones. The `en` entry — and the seven in `ru`/`bs` —
  are removed by the **explicit one-shot prune** this block performs, which is a separate action from
  the flag edit. The two must be reported as two things.
- **The end state is unchanged and is still correct: zero `#~` obsolete entries in all three
  catalogues.** Only the starting point was wrong.
- **The `ru` and `bs` obsolete sets are identical** (same seven msgids). The `en` entry is a **member
  of that set**, with an **empty `msgstr`** as every `en` entry has. So the asymmetry to resolve is
  **`ru`/`bs` (7 each) vs `en` (1)** — a count gap of 6, not a 7-vs-0 gap, and not a set-disjointness
  gap.
- **The en-with-empty-msgstr fact has one hard consequence:** an assertion of the shape *"obsolete
  entries must be translated"* would fail on `en` for a reason that has nothing to do with staleness.
  BLOCK 11 must not write that assertion, and this block's pre-prune enumeration must record which
  class each disappearing entry is without judging its `msgstr`.

---

#### BC-3 — BLOCK 11's obsolete-symmetry invariant is `7/7/1`, and the shape changed

> **Source plan (false):** obsolete **6 (`ru`) / 6 (`bs`) / 0 (`en`)**, described as a symmetry
> violation in which `en` "disagrees about its own history"; the acceptance criteria assume `en` is
> the odd one out at zero.

**Corrected, binding:**

- The measured invariant is **`7` / `7` / `1`** — not `6` / `6` / `0`.
- 🔴 **The axis changed, not just the count.** The `ru`/`bs` pair is now **itself symmetric**. The
  `en` entry is a **member** of the `ru`/`bs` set, not a disjoint one, and its `msgstr` is **empty**
  (as every `en` `msgstr` is, by convention). So the assertion's subject is: **all three catalogues
  must agree on the obsolete set**, and the *pre-prune* state of that agreement is
  `{ru, bs} = 7`, `en = 1`.
- **BLOCK 10 must land first** (strict ordering) so the tree is clean before the assertion arrives.
  BLOCK 11's assertion is written against the **post-prune** invariant — **zero `#~` in all three** —
  and must not encode `7/7/1` as the target. `7/7/1` is the *measurement that justifies* the block,
  not the invariant it asserts.
- **The assertion must not conflate staleness with translation.** It reads the obsolete dimension
  only. It must not require an obsolete `msgstr` to be non-empty (that would fail on `en` for the
  reason BC-2 names), and it must not fail merely because `en` legitimately carries empty `msgstr`s.
- **Consequence for the demonstration:** the synthetic-obsolete guard must be shown failing for a
  **`#~` block in each of the three locales**, not only in `ru`/`bs`. Proving it only on the two that
  already failed is a demonstration of the half that was already true.

---

## 2. Corrected catalogue baseline and the `.po` write contract

### 2.1 Baseline at `7f43e535`

Re-measured from `src/backend/locale/{ru,bs,en}/LC_MESSAGES/django.po`. Locales are exactly
`ru`, `bs`, `en` — no fourth directory. **The source plan's numbers for obsolete entries and for
`en`'s empty `msgstr`s are wrong and are corrected here.**

| Metric | ru | bs | en | Source plan claimed | Status |
|---|---|---|---|---|---|
| Active entries | 448 | 448 | 448 | not stated | — |
| Fuzzy entries | 0 | 0 | 0 | 0/0/0 | ✔ |
| `msgctxt` entries | 0 | 0 | 0 | 0/0/0 | ✔ |
| Empty `msgstr`, **singular** entries | **0** | **0** | **445** | 0 / 0 / **408** | 🔴 **en +37** |
| **Obsolete `#~` entries** | **7** | **7** | **1** | 6 / 6 / 0 | 🔴 **BC-2, BC-3** |
| Plural entries | 2 | 2 | 2 | 2/2/2 | ✔ |
| Plural **forms** | 3 | 3 | **2** | not stated | 🟡 new fact |
| Plural **form completeness** | complete (3/3) | complete (3/3) | **both forms blank** | not stated | 🔴 BLOCK 7 severity |

**Active msgid sets are identical across all three locales** — `ru − bs = 0`, `bs − ru = 0`,
`ru − en = 0`, `en − ru = 0`, `bs − en = 0`, `en − bs = 0`. **Extraction is fully in sync.**
`test_extraction_completeness` and `test_template_extraction_coverage` have nothing to catch today.

**The ru/bs obsolete set (7, identical in both):** `Decline` · `Login successful! Browse-only mode is
active: …` · `Login to Mko Bazuna` · `Mko Bazuna` · `User not found. Please try logging in again.` ·
`We need your consent to process the Telegram name and username you provided …` ·
`Withdrawing consent permanently erases your Telegram ID, all ads, and prevents re-login. Are you
sure?`
**`en` (1):** a member of that set — the `Withdrawing consent permanently erases …` entry — with an
**empty `msgstr`**.

**Reading the plural rows correctly.** The two `ru`/`bs` "empty `msgstr`" hits a naive parser reports
are exactly the two plural entries (`%(counter)s view`, `%(counter)s contact`), whose value lives in
`msgstr[N]`, not `msgstr`. **The real singular-empty count in `ru`/`bs` is 0.** Any gate that reads
`msgstr` and asks "is it blank?" gets a false positive on every plural entry — which is `14-I18N-005`
made concrete, and is exactly why BLOCK 7 must land before any guard reads the catalogue.

**The three real `bs` strings (`N-1`), all still live:**

| String | `bs` `msgstr` state | Template site |
|---|---|---|
| Support greeting (multi-line msgid) | Latin frame carrying a **Cyrillic `а`** inside `oglasa` and the **Russian verb** `користи` | — |
| `Moderator #%(mid)s` | byte-identical copy-through | `analytics/moderation_dashboard.html`, as a `{% blocktrans with mid=… %}` body — **already in `exclude_subpaths`** |
| `Admin` | byte-identical copy-through | `components/header.html`, `components/header_auth_entry.html` — **in scan scope**; two further occurrences in `admin/moderation/review.html` are inside the excluded subtree |

**`bs` has exactly one Cyrillic-bearing `msgstr`** — the support greeting. `ru` = `Модератор #%(mid)s`
and `Админ`, so both copy-throughs are genuinely untranslated in `bs`.

**The nine `bs` copy-through entries** split into **six legitimate** (`ID`, `Telegram ID:`, `Pro`,
`Telegram`, `Google Translate`, `Plausible Analytics` — brand and product names correctly identical
in Bosnian) and the **three real ones above**. `Start` is a **fourth** copy-through and is one of the
`14-I18N-014` orphans BLOCK 10 prunes — BLOCK 9 must not "fix" a string that is about to be deleted.

### 2.2 The `.po` write contract — binding on BLOCKS 4 (conditional), 9 and 10

These three files are the most contended i18n artefact in the repository; six other phases append to
them. This contract is not advisory.

1. **Re-read all three `.po` files immediately before any `makemessages` invocation, and again
   immediately before `git add`.** Twice, not once. The window between the two is where a concurrent
   phase's append lands unnoticed.
2. **Append, never regenerate.** A targeted entry edit, addressed **by msgid**, only. A wholesale
   regeneration is a `git diff` of thousands of lines that no reviewer can read, and it silently
   reorders and re-writes entries another phase owns. There is no exception to this rule.
3. **Never `git add` a `.mo` file.** `.mo` is gitignored; it is compiled at image build, at container
   start and in the CI `i18n` job. If one appears in the diff, the commit is wrong.
4. **`ru` and `bs` `msgstr` values land in the same commit as the msgid they belong to.** If any block
   introduces or alters an extracted msgid, the non-empty `ru` **and** `bs` translations are in *that*
   commit — never a follow-up. The i18n gate goes red otherwise, and a red gate is how a `.po` race
   gets noticed.
5. **Every new msgid is English.** Project rule 1. `msgid` is the English source string; `ru`/`bs`
   `msgstr` are translations. `en`'s `msgstr` stays **empty** — 445 singular entries are empty by
   convention and filling them is a diff that changes nothing at runtime.
6. **`--no-location` stays on.** Without it, location comments churn across every entry in every
   catalogue and the diff becomes unreadable. BLOCK 10 adds `--no-obsolete` **alongside**
   `--no-location`, never instead of it.
7. **Stage by path.** `git add src/backend/locale/ru/LC_MESSAGES/django.po` — never `git add
   src/backend/locale`. The directory form silently captures another phase's append.
8. **`POT-Creation-Date` stays byte-identical across all three catalogues.**
   `test_pot_creation_date_sync` asserts it, and a mismatch sends the next reader to the wrong
   conclusion about a race.
9. **The gate is never committed red.** If a change would leave the i18n gate red with no recorded
   exemption, that commit is not made — re-apply the previous content and report.

### 2.3 The three locale authorities — do not conflate

| Authority | Carrier | What it governs | In this phase |
|---|---|---|---|
| Per-request web locale | `request.LANGUAGE_CODE`, set by `LanguagePreMiddleware` | Every DB-backed string on every page | **BLOCK 1 (limb 1), BLOCK 2 (limb 2)** |
| Per-user Telegram locale | `User.telegram_language`, defaulting to `ru`; activated by the bot's own `language.py` middleware | Bot message text | **OUT OF SCOPE.** BLOCK 2 must not touch the bot's language middleware |
| Saved-search locale | `SavedSearch.language` | **Which FTS vector** a saved search matches — not message text | **OUT OF SCOPE.** Neither BLOCK 1 nor BLOCK 2 alters it |

Conflating these three is the easiest way to write a wrong fix, and the source plan records it as the
single most common shape of error in this finding.

### 2.4 `VAL-003` — the false-green constraint, restated because it binds tests in 6 blocks

`config/settings/base.py` sets `LANGUAGE_CODE = "ru"`; `config/settings/test.py` sets `"en"`. Django's
`DjangoTranslation._add_fallback` adds `settings.LANGUAGE_CODE` as a catalogue fallback for any
activated language that is not `en*`. So **the identical request renders Russian gettext chrome in
production and English chrome under test**, while the **DB accessors behave identically in both**.

**The binding rule: assert on the accessor result — the default-independent surface — or pin
`LANGUAGE_CODE` explicitly with `override_settings`. Never assert on chrome text for a locale the
catalogue does not support.** A chrome assertion there is not merely weak, it is **false-green**: it
passes in CI while production renders a wholly Russian page. This is the single most likely way this
phase ships its headline fix wrong.

---

## 3. Execution blocks

Twelve blocks. **One Implementor, strictly sequential, one commit per block.** The numbering *is* the
serial order, chosen so the contended files are written as few times as possible and no block depends
on an answer nobody has written down:

```
apps/core/middleware/language.py     1 → 6          (the file BLOCK 5 must not touch)
apps/ads/templatetags/price_tags.py  3 → 4          (the chip reuses the corrected helper)
testing/i18n_helpers.py              7 → 10 → 11   (the parser every catalogue-reading guard needs)
test_i18n_completeness.py            8 → 9 → 11    (collectors, then the script gate, then the reverse gate)
locale/{ru,bs,en}/…/django.po        10 → 9 → 11  (prune first, then the strings, then the assertions)
config/settings/base.py              3(opt a) → 5  (both six-way contended; both re-read before editing)
docs/01-spec/i18n-spec.md            12 only       (the spec is written once, after the behaviour)
```

**Six blocks carry a labelled gate (§5): Q3 on BLOCK 3, Q5 on BLOCK 6, Q6 on BLOCK 2, Q9 as a
pre-block step on BLOCK 8, Q11 on BLOCK 12, and Q1 `OPEN-PENDING-REVIEWER` on BLOCK 9.** A gated
block does not start until its answer is written down. **No Implementor chooses an option.**

---

### BLOCK 1 — One locale resolver for all three sources

| | |
|---|---|
| **Findings owned** | `14-I18N-001` (HIGH, first limb), `14-I18N-015` (LOW), `14-I18N-002` (LOW, defence-in-depth) |
| **Class** | **behavioural** |
| **Depends on** | nothing in-plan |
| **Blocks** | BLOCK 2, BLOCK 6, BLOCK 12 |
| **Priority** | **P0.** First, because every other locale finding is either weaker without it or depends on it |
| **Risk level** | **HIGH** — the phase's headline fix, and the one whose test can silently be wrong |
| **Blast radius** | `LanguagePreMiddleware` is the **sole locale authority** in the stack. Every DB-backed string on every page flows through it |
| **Required agents** | **Auditor · Researcher · Planner · Validator — all four.** A false-green regression test here ships the phase's most important fix wrong, and nothing else in the repository would catch it |

**Why one block, not three.** The three findings share one root cause and one seam: one resolver, one
sink, one enum. Splitting them yields three commits each leaving the resolver half-built, and a
Validator cannot tell which state the tree is in.

**The single mechanism this block must establish.** All three sources — the `?lang=` query parameter,
the `lang_pref` cookie, and the `Accept-Language` header — pass through **one** resolver that yields a
`LanguageLocale` member, and **that member** is what reaches `translation.activate()` and
`request.LANGUAGE_CODE`. **There is no fourth path.**

**File surface (semantic units)**

| File | Symbol | Change |
|---|---|---|
| `src/backend/apps/core/middleware/language.py` | `LanguagePreMiddleware.process_request` | The raw-cookie branch stops passing the unvalidated cookie string onward |
| `src/backend/apps/core/middleware/language.py` | `LanguagePreMiddleware._set_language_code` | Becomes the single sink every source routes through, and normalises there |
| `src/backend/apps/core/middleware/language.py` | `LanguagePreMiddleware._parse_accept_language` | `split(",")[0]` → a `(tag, q)` scan that drops `q=0`, sorts descending, returns the first tag mapping to a configured locale, then falls back |
| `src/backend/apps/core/middleware/language.py` | the module docstring | Records the priority chain and the normalisation guarantee it currently *claims* but the cookie branch does not honour. Clear the stray double blank line inside the class body in passing — it is pre-existing lint rot, not this block's finding |
| `src/backend/apps/categories/views.py` | `category_submenu` — the `category:submenu:<tree_version>:<slug>:<locale>` key | Build the locale segment through `LanguageLocale.from_code(...)` instead of the raw request attribute (`14-I18N-002`, defence-in-depth) |
| `src/backend/apps/core/tests/test_language_middleware.py` | `test_cookie_valid_values` and the priority table | Grows from canonical-only to the non-canonical cookie cases that are absent today |
| `docs/01-spec/i18n-spec.md` | — | **READ ONLY here.** BLOCK 12 writes it |

**Binding constraints**

1. **✔ `VAL-003` — assert on accessors, never on chrome.** See §2.4. The new cookie cases assert on
   `Category.get_name` / `City.get_name` / `Ad.get_title`, or pin `LANGUAGE_CODE` with
   `override_settings`. **Never chrome.** This is the block's highest-probability wrong delivery.
2. **Do not add `LocaleMiddleware`, a `set_language` view, or `i18n_patterns`.** The module docstring
   explains why `LocaleMiddleware` is intentionally absent: it would re-derive the language from the
   never-set `django_language` cookie plus `Accept-Language`, clobbering the resolved value and
   ignoring both `?lang=` and `lang_pref`.
3. **Three distinct locale authorities; this block touches only the first.** See §2.3.
   `User.telegram_language` and `SavedSearch.language` are out of scope.
4. **`request.LANGUAGE_CODE` is a member of `settings.LANGUAGES` after this block** — assertable for
   every input in the priority table, **including the hostile ones**.
5. **The cookie's write path is BLOCK 6's, not this block's.** `_apply_lang_param` continues to
   persist only the resolved canonical code. **Do not add, remove or change `set_cookie` here.**
6. **Do not touch the model accessors or the `localized_content` filters.** That is BLOCK 2, whose
   surface is **18 signatures** (BC-1), not 10.
7. **The `<time datetime="…">` ISO attributes and every `Vary` header are untouched** — BLOCKS 5 and 6.
8. **Re-read `language.py` immediately before editing.** No other phase claims it, but this repository
   shows concurrent-agent drift is routine and this is the phase's most important file.
9. **Run the full i18n gate including `test_i18n_category_city.py` before starting.** Those DB-backed
   tests were never run during the audit and are the only DB-backed i18n evidence in the phase.
   Record the observed per-locale symptom table in the commit body, **before and after**.
10. **No msgid changes. No `.po` write.** If the gate suggests otherwise, that is a BLOCK 12 claim,
    not a new msgid.

**Implementor task**

```yaml
id: task_14_b01_locale_resolver
title: "Route all three locale sources through one normalising resolver (14-I18N-001, 14-I18N-015, 14-I18N-002)"
priority: high
depends_on: []
source_reference: ".ai/plans/25-i18n-remediation-execution.md"
source_section: "BLOCK 1 - One locale resolver for all three sources"
source_blocks: ["BLOCK 1"]
description: >
  LanguagePreMiddleware is the only locale authority in the stack. It normalises the ?lang= query
  parameter and the Accept-Language header, but the lang_pref cookie branch passes the raw cookie
  string straight to _set_language_code and on to translation.activate(), which neither consults
  settings.LANGUAGES nor normalises. Any cookie whose to_language() form is not exactly ru/bs/en -
  which is the overwhelming majority of real BCP-47 tags - drives every DB-backed string through the
  locale -> ru -> name chain to Russian, site-wide. Separately, _parse_accept_language inspects only
  the first tag, so a supported lower-ranked tag is skipped, and the submenu cache key is built from
  the raw request attribute rather than from a value that passed through the LanguageLocale enum.
goals:
  - "one resolver yields a LanguageLocale member from all three sources; request.LANGUAGE_CODE is always a member of settings.LANGUAGES"
  - "Accept-Language honours descending q-values, drops q=0, and picks the first supported tag before falling back"
  - "the submenu cache-key locale segment is built through LanguageLocale.from_code"
  - "add the non-canonical cookie regression cases that are absent from the priority table today"
extra_context: |
  BINDING CONSTRAINTS (from section 3 BLOCK 1; none corrected - this block's premises reproduced
  byte-for-byte at 7f43e535)
  1. VAL-003 - ASSERT ON ACCESSORS, NEVER ON CHROME. base.py sets LANGUAGE_CODE="ru"; test.py
     sets "en". Django's _add_fallback adds settings.LANGUAGE_CODE as a catalogue fallback for any
     activated language that is not en*, so the identical request renders Russian chrome in
     production and English chrome under test while the DB accessors behave identically in both. A
     chrome assertion for an unsupported cookie locale is FALSE-GREEN: it passes in CI and
     production is still wrong. Assert on Category.get_name / City.get_name / Ad.get_title, or
     pin LANGUAGE_CODE explicitly with override_settings.
  2. Do not add LocaleMiddleware, a set_language view, or i18n_patterns.
  3. Three distinct locale authorities - see section 2.3. This block touches ONLY the per-request
     web locale. Do not touch src/telegram_bot/middlewares/language.py. SavedSearch.language
     selects which FTS vector a saved search matches and does not affect message text.
  4. request.LANGUAGE_CODE must be a member of settings.LANGUAGES for every input, hostile ones
     included.
  5. The cookie WRITE path is BLOCK 6's. Do not add, remove or change set_cookie here.
  6. Do not touch the model accessors or the localized_content filters - BLOCK 2, and its surface
     is 18 signatures, not 10.
  7. The two <time datetime="...|date:'Y-m-d'"> attributes and every Vary header are untouched.
  8. Re-read language.py immediately before editing.
  9. Run the full i18n gate INCLUDING test_i18n_category_city.py before starting, and record the
     before/after per-locale symptom table in the commit body.
  10. No msgid changes and no .po write by this block.
  VERIFIED SYMBOL MAP (re-derived at 7f43e535; use symbols, never line numbers)
  - src/backend/apps/core/middleware/language.py -> class LanguagePreMiddleware; methods
    process_request, process_response, _apply_lang_param, _set_language_code,
    _parse_accept_language; module constants LANGUAGE_COOKIE_NAME, LANGUAGE_COOKIE_MAX_AGE
  - the raw cookie read is inside process_request via request.COOKIES
  - _parse_accept_language does accept_language.split(",")[0] and returns
    LanguageLocale.from_code(first_tag, fallback=LanguageLocale.BOSNIAN).value immediately
  - src/backend/apps/categories/views.py -> view category_submenu; the key is
    f"category:submenu:{get_tree_version()}:{category.slug}:{request.LANGUAGE_CODE or 'ru'}"
  - src/backend/apps/core/enums.py -> LanguageLocale (StrEnum: RUSSIAN="ru", BOSNIAN="bs",
    ENGLISH="en") with .from_code, .values, .fts_config, .fts_vector_field
  - src/backend/apps/core/tests/test_language_middleware.py -> test_cookie_valid_values and the
    priority table; today it exercises only ("ru", "bs", "en") for the cookie
  - HOUSEKEEPING: the class body carries a stray double blank line. Clear it in passing so this
    commit is not blamed for pre-existing lint rot.
  FORBIDDEN: editing src/backend/conftest.py; editing any .po or .mo file; adding
  LocaleMiddleware; changing set_cookie; touching the model accessors or template filters; adding a
  Vary header; editing a template.
files:
  - path: src/backend/apps/core/middleware/language.py
    targets:
      - type: class
        name: LanguagePreMiddleware
      - type: method
        name: process_request
      - type: method
        name: _set_language_code
      - type: method
        name: _parse_accept_language
    semantic_anchors:
      insert_before:
        type: function_call
        value: translation.activate
  - path: src/backend/apps/categories/views.py
    targets:
      - type: function
        name: category_submenu
    semantic_anchors:
      insert_after:
        type: yaml_key
        value: cache_key
  - path: src/backend/apps/core/tests/test_language_middleware.py
    targets:
      - type: function
        name: test_cookie_valid_values
    changes: []   # extend the table; do not weaken any existing assertion
  - path: docs/01-spec/i18n-spec.md
    targets: []
    changes: []   # READ ONLY in this block. BLOCK 12 writes it.
changes:
  - action: add_code
    description: >
      Add one resolver on LanguagePreMiddleware that every locale source routes through: ?lang=,
      the lang_pref cookie and Accept-Language all yield a LanguageLocale member, and that member
      is what reaches translation.activate() and request.LANGUAGE_CODE. The cookie branch currently
      passes the raw cookie string.
  - action: add_code
    description: >
      Replace split(",")[0] in _parse_accept_language with a (tag, q) scan: parse each
      comma-separated member with its q parameter, drop q=0, sort by descending q, and return the
      first tag that maps to a configured locale, only then falling back.
  - action: add_code
    description: >
      Build the submenu cache-key locale segment through
      LanguageLocale.from_code(request.LANGUAGE_CODE, fallback=LanguageLocale.RUSSIAN).value
      instead of the raw request attribute.
  - action: add_test
    description: >
      Add non-canonical cookie cases to test_language_middleware.py - at minimum en-US, EN, en_US,
      de-DE, ru-RU and a nonsense tag - each asserting the resolved locale is a member of
      settings.LANGUAGES AND that a model accessor returns THAT locale's value, not the ru
      fallback. Add q-valued Accept-Language cases including "de-DE,ru;q=0.8,bs;q=0.6" and a
      q=0 exclusion case. Existing canonical cases must keep passing unchanged.
acceptance_criteria:
  - "for every cookie value in the table, including the non-canonical ones, request.LANGUAGE_CODE is a member of settings.LANGUAGES"
  - "the non-canonical cookie cases assert on Category.get_name / City.get_name / Ad.get_title, never on rendered chrome (VAL-003)"
  - "Accept-Language 'de-DE,ru;q=0.8,bs;q=0.6' resolves to ru, not bs"
  - "an Accept-Language member with q=0 is not selected"
  - "the submenu cache key's locale segment is one of ru/bs/en for every request in the table"
  - "every pre-existing test in test_language_middleware.py still passes unchanged"
  - "no LocaleMiddleware, set_language view or i18n_patterns was added"
  - "no .po or .mo file was touched by this block"
  - "the commit body records the before-and-after per-locale symptom table and names the specific
     assertion strategy used to avoid the VAL-003 false green"
```

---

### BLOCK 2 — The type boundary: `LanguageLocale` at 18 signatures

| | |
|---|---|
| **Findings owned** | `14-I18N-001` (HIGH, second limb) |
| **Class** | **structural** — the phase's only type-boundary change |
| **Depends on** | **BLOCK 1** (strict — normalisation must exist first), **Q6 pre-block step** |
| **Blocks** | BLOCK 12 |
| **Priority** | **P0**, immediately after BLOCK 1 |
| **Risk level** | **HIGH** — the widest call-graph change in the phase, and `Q6` may widen it further |
| **Blast radius** | 18 Python signatures across 11 files, plus `apps/core/context_processors.py` under `Q6` option (a), plus 55 template reads of `LANGUAGE_CODE` |
| **Required agents** | **Auditor · Researcher · Planner · Validator — all four.** The surface is graph-shaped and the typing choice is reversible in one direction only |

**🔴 `Q6` — PRE-BLOCK STEP (measurement, not preference), then a decision. See §5.3.** The Auditor
enumerates every consumer of `context_processors.language` and of the five `localized_content`
filters before the block starts. **The audit's round-2 enumeration is in §1.2 / BC-1 and is the
enumeration** — 18 signatures, 55 template occurrences across 16 files, 27 of them filter arguments,
20 or more URL renders, zero Python consumers of the processor output. **Q6's option selection remains
the decider's call and is not made here.**

**The runtime argument, which the plan states as its strongest and which the audit confirms:** all
eighteen defaults are already *effectively* `LanguageLocale` — sixteen default to the enum member,
two default to `LanguageLocale.RUSSIAN.value`, which is the same object under `StrEnum`. So
tightening the annotation describes what the code already does rather than changing it. **That is an
argument for option (a); it is not a decision, and the two `str`-defaulting sites make option (b)'s
"narrow surface" narrower than the plan priced it.**

**File surface (semantic units) — 18 signatures, 11 files**

| File | Symbol | Signature today |
|---|---|---|
| `src/backend/apps/categories/models.py` | `Category.get_name` | `locale: str = LanguageLocale.RUSSIAN` |
| `src/backend/apps/locations/models.py` | `City.get_name` | same |
| `src/backend/apps/lookups/models.py` | `LookupItem.get_name` | same — **and this is the one that terminates at `slug`, not `name`** |
| `src/backend/apps/ads/models.py` | `Ad.get_title` | same |
| `src/backend/apps/ads/models.py` | `Ad.get_description` | same |
| `src/backend/apps/core/templatetags/localized_content.py` | `get_title`, `get_description`, `get_lookup_name`, `get_category_name`, `get_city_name` | same ×5 |
| `src/telegram_bot/services/ad_data/keyboards.py` | three functions | same ×3 — **outside the source plan's surface** |
| `src/telegram_bot/services/ad_data/feature_helpers.py` | one function | same — **outside the source plan's surface** |
| `src/backend/apps/search/services/entity_suggestions.py` | two functions | same ×2 — **outside the source plan's surface** |
| `src/backend/apps/search/services/immediate_alerts.py` | one function | 🔴 `locale: str = LanguageLocale.RUSSIAN.value` — **str-defaulting** |
| `src/backend/apps/search/management/commands/send_alerts.py` | one function | 🔴 `locale: str = LanguageLocale.RUSSIAN.value` — **str-defaulting** |
| `src/backend/apps/core/context_processors.py` | `language` | returns `{"LANGUAGE_CODE": getattr(request, "LANGUAGE_CODE", settings.LANGUAGE_CODE)}` — **a `str`. In scope only under `Q6` option (a)** |
| `src/backend/apps/ads/tests/test_i18n_category_city.py` | — | the DB-backed home for the new assertions |

**Binding constraints**

1. **🔴 CORRECTED — the surface is 18 signatures, not 10, and the two `str`-defaulting sites are in
   scope.** See **BC-1** in §1.2 for the full corrected text and the enumeration. **Do not tighten ten
   of eighteen**; that leaves the boundary stricter in templates and looser in the bot and alert
   services.
2. **Preserve the fallback chain exactly**: `locale → ru → name` for `Category`, `City` and `Ad`;
   `locale → ru → slug` for `LookupItem`. Tightening the type must not reorder or remove a rung.
3. **Do not change the accessors' behaviour.** A bad locale must still degrade to Russian —
   deliberately, by a route the type system documents rather than by accident. What changes is the
   *source* of the value, not the fallback.
4. **`LookupItem.get_name` terminates at `slug`, not `name`.** It is the one accessor with a different
   terminal rung. A "uniformity" edit that makes it fall back to `name` is a regression.
5. **The default parameter stays `LanguageLocale.RUSSIAN`** — except where it is currently
   `LanguageLocale.RUSSIAN.value`, and those two sites are the ones the `Q6` option decides. Do not
   "improve" any default to `None` or to a thread-derived guess.
6. **No template may be edited to work around the typing.** Templates call
   `|get_city_name:LANGUAGE_CODE`; if the type changes, the **context processor** changes, not the
   templates. 55 call sites across 16 files is the wrong surface.
7. **The 20-plus `&lang={{ LANGUAGE_CODE }}` URL renders are part of the surface under option (a).**
   An enum rendered into a query string goes through `str()`. Re-read
   `components/language_switcher.html` — its own doc comment claims it reads the value from the
   processor. **Re-reading is required; editing those templates is not, unless the decider's option
   makes it necessary and the Implementor reports that as a new surface rather than silently widening.**
8. **Do not touch `src/telegram_bot/middlewares/language.py`.** The bot's per-user locale is a
   different authority (§2.3).
9. **`basedpyright` must reach 0 errors on every changed path.** A type change that leaves the
   typechecker reporting errors is not finished.
10. **`VAL-003` still binds the new tests** (§2.4): assert on the accessor's returned value, never
    on chrome.
11. **DB-backed assertions go in `test_i18n_category_city.py`**, which exists for exactly this surface.
    **No new test module. Never `conftest.py`.**
12. **Do not touch the middleware** — BLOCK 1 owns it.

**Implementor task**

```yaml
id: task_14_b02_accessor_typing
title: "Tighten the 18 locale signatures and the localized_content filters to LanguageLocale (14-I18N-001 limb 2)"
priority: high
depends_on: [task_14_b01_locale_resolver]
source_reference: ".ai/plans/25-i18n-remediation-execution.md"
source_section: "BLOCK 2 - The type boundary at 18 signatures"
source_blocks: ["BLOCK 2"]
description: >
  Normalising the locale in the middleware (BLOCK 1) stops the bad value at the source, but 18
  signatures still accept an arbitrary str and do an exact dict-key test against it, with the ru
  rung next. Tightening them to LanguageLocale makes a bad locale degrade to Russian deliberately
  and makes the typechecker flag every call site that can still deliver a raw string. The surface
  is EIGHTEEN signatures across ELEVEN files, not ten across six, and two of them
  (immediate_alerts.py and send_alerts.py) default to LanguageLocale.RUSSIAN.value - a bare str -
  which is a second anti-pattern the source plan never names. Q6 remains open and may add
  apps/core/context_processors.py plus the &lang={{ LANGUAGE_CODE }} URL renders to the surface.
goals:
  - "all 18 locale signatures and all 5 localized_content filters accept the Q6-chosen type"
  - "the locale -> ru -> name chain, and LookupItem's locale -> ru -> slug, are preserved exactly"
  - "every call site typechecks and basedpyright reports 0 errors on the changed paths"
extra_context: |
  Q6 GATE - pre-block enumeration is DONE (see BC-1 in section 1.2 for the full text): 18
  signatures across 11 files, 55 LANGUAGE_CODE occurrences across 16 templates, 27 of them filter
  arguments, 20 or more &lang={{ LANGUAGE_CODE }} URL renders, and ZERO Python consumers of the
  processor's output. Option (a): the context processor emits LanguageLocale and the filters take
  LanguageLocale. Option (b): the accessors accept str | LanguageLocale and normalise internally.
  THE OPTION IS NOT CHOSEN HERE. Record the chosen option and the reason in the commit body.
  BINDING CONSTRAINTS (from section 3 BLOCK 2; BC-1 is the corrected one)
  1. CORRECTED: the surface is 18 signatures across 11 files, not 10 across 6. The eight the
     source plan omits - three in telegram_bot/services/ad_data/keyboards.py, one in
     ad_data/feature_helpers.py, two in search/services/entity_suggestions.py, one in
     search/services/immediate_alerts.py, one in search/management/commands/send_alerts.py -
     carry the SAME signature and ARE IN SCOPE. Do not tighten ten of eighteen.
  2. immediate_alerts.py and send_alerts.py default to LanguageLocale.RUSSIAN.value - a bare str.
     This is a SECOND anti-pattern the source plan never names. They are in scope under whichever
     option is chosen; if the option cannot cover them, REPORT that rather than leaving them.
  3. Under option (a), the 20-plus &lang={{ LANGUAGE_CODE }} URL renders in the shared ad-list
     partial put the enum through str(). Re-read components/language_switcher.html - its doc
     comment claims it reads the value from the processor. Re-reading is required; editing those
     templates is not, unless the chosen option makes it necessary AND you report it as new
     surface rather than widening silently.
  4. Preserve the fallback chain exactly: locale -> ru -> name for Category, City and Ad;
     locale -> ru -> slug for LookupItem.
  5. Do not change the accessors' behaviour. A bad locale must still degrade to Russian.
  6. LookupItem.get_name ends at slug. A uniformity edit making it fall back to name is a
     regression.
  7. The default parameter stays LanguageLocale.RUSSIAN (or, at the two str-defaulting sites,
     whatever the Q6 option specifies). Never None, never a thread-derived guess.
  8. No template may be edited to work around the typing. If the type changes the CONTEXT
     PROCESSOR changes, not the 55 template call sites.
  9. Do not touch src/telegram_bot/middlewares/language.py - the bot's per-user locale is a
     different authority. SavedSearch.language is a third authority and is out of scope.
  10. basedpyright must reach 0 errors on every changed path.
  11. VAL-003 still binds the tests: assert on the accessor's returned value, never on chrome.
  12. DB-backed assertions go in test_i18n_category_city.py. No new test module; never
     src/backend/conftest.py.
  13. Do not touch LanguagePreMiddleware - BLOCK 1 owns it. No .po or .mo write.
  VERIFIED SYMBOL MAP (re-derived at 7f43e535; use symbols, never line numbers)
  - 16 sites: locale: str = LanguageLocale.RUSSIAN
  - 2 sites: locale: str = LanguageLocale.RUSSIAN.value  <- the second anti-pattern
  - apps/core/context_processors.py -> function language, returning
    {"LANGUAGE_CODE": getattr(request, "LANGUAGE_CODE", settings.LANGUAGE_CODE)} - a str
  - config/settings/base.py -> the single registration of
    "apps.core.context_processors.language" in the template context processors
  - docs/01-spec/i18n-spec.md, "Stored catalogue data" section, documents the four-layer surface
    and the fallback chain. BLOCK 12 updates the prose; this block does not.
  FORBIDDEN: editing src/backend/conftest.py; editing any template; editing any .po or .mo file;
  editing LanguagePreMiddleware; adding a fallback rung; creating a new test module.
files:
  - path: src/backend/apps/categories/models.py
    targets: [{ type: method, name: get_name }]
  - path: src/backend/apps/locations/models.py
    targets: [{ type: method, name: get_name }]
  - path: src/backend/apps/lookups/models.py
    targets: [{ type: method, name: get_name }]
  - path: src/backend/apps/ads/models.py
    targets:
      - { type: method, name: get_title }
      - { type: method, name: get_description }
  - path: src/backend/apps/core/templatetags/localized_content.py
    targets:
      - { type: function, name: get_title }
      - { type: function, name: get_description }
      - { type: function, name: get_lookup_name }
      - { type: function, name: get_category_name }
      - { type: function, name: get_city_name }
  - path: src/telegram_bot/services/ad_data/keyboards.py
    targets: []
    changes: []   # three locale signatures; re-read and locate by signature, not by position
  - path: src/telegram_bot/services/ad_data/feature_helpers.py
    targets: []
    changes: []   # one locale signature
  - path: src/backend/apps/search/services/entity_suggestions.py
    targets: []
    changes: []   # two locale signatures
  - path: src/backend/apps/search/services/immediate_alerts.py
    targets: []
    changes: []   # str-defaulting signature - BC-1
  - path: src/backend/apps/search/management/commands/send_alerts.py
    targets: []
    changes: []   # str-defaulting signature - BC-1
  - path: src/backend/apps/core/context_processors.py
    targets: [{ type: function, name: language }]
    changes: []   # in scope ONLY under Q6 option (a); otherwise a report, not a silent edit
  - path: src/backend/apps/ads/tests/test_i18n_category_city.py
    targets: []
    changes: []   # add cases to the existing module; do not weaken existing assertions
changes:
  - action: change_signature
    description: >
      Change the locale parameter of the 18 signatures and the 5 template filters from str to the
      Q6-chosen type, keeping the documented default and every fallback rung in its current order.
      The two str-defaulting sites (immediate_alerts.py, send_alerts.py) are included.
  - action: add_test
    description: >
      Add DB-backed cases to test_i18n_category_city.py asserting each accessor returns the
      requested locale's value for every LanguageLocale.values() member - never bare string
      literals - and that a value the enum cannot represent degrades to the ru rung without raising.
acceptance_criteria:
  - "all 18 signatures and all 5 filters carry the Q6-chosen locale type, including the two
     str-defaulting sites, or the omission is reported in the commit body"
  - "the default remains LanguageLocale.RUSSIAN (or the Q6-chosen equivalent at the two
     str-defaulting sites)"
  - "LookupItem still terminates at slug"
  - "the locale -> ru fallback still fires for an unmapped locale, and the test asserts that
     rather than an exception"
  - "multi-language cases are driven from LanguageLocale.values(), never from bare literals"
  - "uv run basedpyright reports 0 errors on every changed path"
  - "existing assertions in test_i18n_category_city.py still pass unchanged; no new test module; conftest.py untouched"
  - "no template and no .po or .mo file was modified by this block"
  - "the commit body names the Q6 option chosen, the reason, and whether the URL-render surface
     had to change"
```

---

### BLOCK 3 — Price formatting: the `Decimal` argument and the `bs` grouping decision

| | |
|---|---|
| **Findings owned** | `14-I18N-003` (HIGH), `VAL-004` (LOW advisory, folded in) |
| **Class** | **behavioural** — changes every rendered price in `ru` and `bs` |
| **Depends on** | nothing in-plan · **Gated on `Q3`** (§5.1) |
| **Blocks** | BLOCK 4 |
| **Priority** | **P0** |
| **Risk level** | **HIGH** — because the obvious fix is *demonstrably incomplete* and will read as finished |
| **Blast radius** | Every ad card, ad detail page, search-result row, and the Telegram alert messages that reuse the same helper |
| **Required agents** | **Auditor · Researcher · Planner · Validator — all four.** The incompleteness is invisible without a runtime probe, and the gate is a genuine technical choice |

**The root cause, narrow.** `_format_amount` builds a plain string and passes a **`str`** to
`intcomma`. Django's `humanize.intcomma` localises only `float`/`Decimal`; for a `str` it attempts
`int(value)`, which raises `ValueError` on any fractional amount, and the `except` branch recurses
with `use_l10n=False` — hard-coding `,` as the grouping separator and leaving the `.` decimal mark
untouched. **Integer amounts survive the `int()` and take the localising path, which is exactly why
round prices look correct and hide the bug.**

**🔴 `Q3` — DECISION REQUIRED BEFORE IMPLEMENTATION.** The one-argument fix restores the decimal mark
for `ru` and `bs` but **`bs` thousands grouping remains structurally impossible**: Django's bundled
`bs` locale leaves `NUMBER_GROUPING` commented out, and `django/utils/numberformat.py` gates on
`use_grouping and grouping != 0`, which hard-disables grouping **even under `force_grouping=True`**.
**Whatever is chosen, the grouping decision ships in the same change as the argument fix** — a commit
that changes only the argument is a half-fix a reviewer will sign off on. Options, consequences and
the decider: **§5.1.**

**File surface (semantic units)**

| File | Symbol | Change |
|---|---|---|
| `src/backend/apps/ads/templatetags/price_tags.py` | `_format_amount` | Pass the `Decimal` to `intcomma` — or call `number_format` directly — after trimming the exponent **on the `Decimal`**, not on the rendered string |
| `src/backend/apps/ads/templatetags/price_tags.py` | `format_price_value`, `format_price` | Unchanged in shape. **BLOCK 4 reuses `format_price_value`** |
| `src/backend/apps/ads/tests/test_price_format.py` | `test_format_price_value_uses_intcomma` | Its docstring asserts locale-aware grouping while its body asserts only that a 5-digit integer is ungrouped — which never exercises the fractional branch. **Production code is king: the test follows the corrected behaviour** |
| `src/backend/config/settings/base.py` | `FORMATS` | **Only under `Q3` option (a).** Six-way contended — re-read immediately before editing and stop on a concurrent change |
| `src/backend/config/settings/tests/test_settings_defaults.py` | a new `NUMBER_GROUPING` assertion | **Only under `Q3` option (a).** The natural home; a concurrent phase-02 edit was landing there, so re-read first |

**Binding constraints**

1. **`test_format_price_value_uses_intcomma` is a docstring/behaviour mismatch, not a regression to
   preserve.** Update its assertions to the corrected behaviour. **Do not weaken them** to accommodate
   the old output, and **do not bend `_format_amount` back** to satisfy them.
2. **Assert exact per-locale output**, not "a separator appeared". For **each** of `ru`/`bs`/`en`: a
   fractional amount (exercises the defect), a round integer amount (proves no regression), and a
   **≥7-digit** amount — a 5-digit number has at most one group and **cannot prove grouping works**.
3. **The separator facts are verified, not assumed.** `ru`: `THOUSAND_SEPARATOR` is **U+00A0**
   (non-breaking space), `DECIMAL_SEPARATOR` is `,`. `bs`: `THOUSAND_SEPARATOR` is `.`,
   `DECIMAL_SEPARATOR` is `,`. **Assert on the real code points**, not on a hard-coded rendered
   string that drifts with the Django version.
4. **Under `Q3` option (a), the settings change and its test ship in the same commit**, and `base.py`
   is re-read immediately before editing. Stage by path, never by directory.
5. **Django's bundled `bs` locale data must not be edited.** It is a third-party package in `.venv`;
   an edit there is not a repository change and vanishes on the next image build.
6. **Do not change the price round-trip.** The `Decimal("0.01")` / `ROUND_HALF_UP` quantisation and
   the trailing-zero trim are the storage contract and are not part of this finding.
7. **Parametrise with `LanguageLocale.values()`**, never bare locale strings.
8. **BLOCK 4 reuses whatever helper this block lands.** No second formatting entry point for the
   chip's benefit.
9. **No `.po` write.** No msgid changes.

**Implementor task**

```yaml
id: task_14_b03_price_format
title: "Pass the Decimal to the price formatter and ship the bs grouping decision (14-I18N-003, VAL-004)"
priority: high
depends_on: []
source_reference: ".ai/plans/25-i18n-remediation-execution.md"
source_section: "BLOCK 3 - Price formatting"
source_blocks: ["BLOCK 3"]
description: >
  _format_amount in price_tags.py stringifies the Decimal and passes a str to intcomma. intcomma
  localises only float/Decimal; for a str it attempts int(value), which raises ValueError on any
  fractional amount, and the except branch recurses with use_l10n=False - hard-coding a comma as the
  grouping separator and leaving the ASCII decimal point. Integer amounts survive, so round prices
  hide the defect. The one-argument fix restores the decimal mark for ru and bs but NOT bs thousands
  grouping, because Django's bundled bs locale leaves NUMBER_GROUPING commented out and
  numberformat.py gates on grouping != 0 - grouping is unreachable even under force_grouping=True.
  The grouping decision must ship in the same change as the argument fix.
goals:
  - "fractional prices localise correctly in all three locales"
  - "the bs grouping decision (Q3) is implemented and covered by a test, in the same commit"
  - "the existing test that documented the wrong behaviour is corrected, not weakened"
extra_context: |
  Q3 GATE - DECISION REQUIRED BEFORE IMPLEMENTATION. The block does not start until the option is
  written down. Option (a): a project-level FORMATS override supplying NUMBER_GROUPING = 3 for bs in
  config/settings/base.py, with its own settings test, in the same commit. Option (b): a
  project-owned formatting helper bypassing numberformat.py's grouping gate - accepted only with a
  written justification for accepting a second formatting path. Option (c): accept ungrouped bs
  prices as a documented limitation, and say plainly in the commit body that 14-I18N-003 is only
  half closed. See section 5.1 for consequences and for who decides. DO NOT CHOOSE.
  BINDING CONSTRAINTS (from section 3 BLOCK 3; none corrected - premises reproduced at 7f43e535)
  1. test_format_price_value_uses_intcomma is a docstring/behaviour mismatch, not a regression to
     preserve. Update the assertions; do not weaken them and do not bend _format_amount back.
  2. Assert exact per-locale output. For each of ru/bs/en: a fractional amount, a round integer
     amount, and a >=7-digit amount. A 5-digit number cannot prove grouping works.
  3. Verified separator facts: ru THOUSAND_SEPARATOR is U+00A0 and DECIMAL_SEPARATOR is ","; bs
     THOUSAND_SEPARATOR is "." and DECIMAL_SEPARATOR is ",". Assert on the real code points via
     django.conf.locale formats, not on hard-coded rendered strings.
  4. Under Q3 option (a) the settings change and its test ship in the same commit, and base.py is
     re-read immediately before editing. Stop and report a concurrent change. Stage by path.
  5. Django's bundled bs locale data must NOT be edited - it is a third-party package in .venv and
     the edit vanishes on the next image build.
  6. Do not change the price round-trip: the Decimal("0.01") / ROUND_HALF_UP quantisation and the
     trailing-zero trim are the storage contract.
  7. Parametrise with LanguageLocale.values(), never bare locale strings.
  8. BLOCK 4 reuses whatever helper this block lands. No second formatting entry point.
  9. No .po write and no msgid change.
  VERIFIED SYMBOL MAP (re-derived at 7f43e535; use symbols, never line numbers)
  - src/backend/apps/ads/templatetags/price_tags.py -> function _format_amount, which builds
    format(rounded, "f"), trims trailing zeros, and returns intcomma(formatted)
  - the same module -> format_price_value and format_price, the latter the |format_price filter
  - src/backend/apps/ads/tests/test_price_format.py -> test_format_price_value_uses_intcomma
  - django/conf/locale/bs/formats.py sets DECIMAL_SEPARATOR and THOUSAND_SEPARATOR and leaves
    "# NUMBER_GROUPING =" commented out; ru/formats.py sets all three
  - no project-level FORMATS override exists in config/settings/
  FORBIDDEN: editing any .po or .mo file; editing price formatting in the bot; editing the
  quantisation; editing Django's bundled locale data; choosing the Q3 option.
files:
  - path: src/backend/apps/ads/templatetags/price_tags.py
    targets: [{ type: function, name: _format_amount }]
  - path: src/backend/apps/ads/tests/test_price_format.py
    targets: [{ type: function, name: test_format_price_value_uses_intcomma }]
    changes: []   # correct the assertions; do not weaken any
  - path: src/backend/config/settings/base.py
    targets: []
    changes: []   # ONLY under Q3 option (a); re-read immediately before editing
  - path: src/backend/config/settings/tests/test_settings_defaults.py
    targets: []
    changes: []   # ONLY under Q3 option (a); a concurrent phase-02 edit was landing here
changes:
  - action: change_code
    description: >
      Pass the Decimal to intcomma (or call number_format directly) after trimming the exponent on
      the Decimal rather than on the rendered string, so the localising path is taken for fractional
      amounts as well as integer ones.
  - action: add_code
    description: >
      Implement the Q3 decision as written down. Under option (a), add the bs NUMBER_GROUPING
      form ofats override in config/settings/base.py beside the other locale configuration.
  - action: change_test
    description: >
      Rewrite test_format_price_value_uses_intcomma to assert exact per-locale output for a
      fractional amount, a round integer amount and a >=7-digit amount, and to assert the real
      separator code points.
acceptance_criteria:
  - "a fractional amount renders with the locale's decimal separator in ru, bs and en"
  - "a >=7-digit amount renders grouped in every locale the chosen Q3 option covers, and the test
     states explicitly which locales it does NOT cover under option (c)"
  - "a round integer amount renders identically to before this block"
  - "no test asserts only that a separator is present; every price assertion is exact-output"
  - "multi-language cases are parametrised from LanguageLocale.values()"
  - "Django's bundled locale data under .venv is byte-identical to its shipped state"
  - "uv run basedpyright reports 0 errors on the changed paths"
  - "the commit body names the Q3 option chosen, the reason, and - under option (c) - that
     14-I18N-003 is only half closed"
```

---

### BLOCK 4 — The active-price filter chip uses the corrected helper

| | |
|---|---|
| **Findings owned** | `14-I18N-010` (MEDIUM) |
| **Class** | **mechanical** |
| **Depends on** | **BLOCK 3** (strict — the chip must use the corrected formatting) |
| **Blocks** | nothing |
| **Priority** | **P1** |
| **Risk level** | **MEDIUM** — a small edit, but it inherits `14-I18N-003`'s `bs` caveat |
| **Blast radius** | One template block, rendered by two routes (`ads/views/listings.py` and `search/views/search.py`, both of which supply both bounds) |
| **Required agents** | **Auditor · Planner · Validator** — the surface is one template block plus two context keys. **No Researcher needed** |

**The defect.** The chip interpolates raw `Decimal` bounds through `{% blocktrans %}`, whose
placeholders apply **no filter chain** — so Django stringifies a `Decimal` with an ASCII decimal point,
no grouping and no currency code, **directly above correctly formatted card prices in the same
response**. No gate catches it: the text *is* wrapped; only the interpolation is unformatted.

**The remedy already exists in the same file.** The purpose chip uses a `{% trans "Purpose:" %}`
label plus a pre-computed value passed through `|get_lookup_name`. **This block applies an existing
in-file pattern and introduces no new one** — which is why it is `mechanical` and not `structural`.
🟡 **Citation rot, corrected:** the source plan calls this "fourteen lines below the defect"; it is now
~97 lines below. **The semantic target — the in-file purpose-chip pattern — is unambiguous and
unchanged. The citation is dropped, not copied.**

**File surface (semantic units)**

| File | Symbol / element | Change |
|---|---|---|
| `src/backend/templates/ads/partials/ad_list.html` | the active-price `{% blocktrans %}` chip | Replaced with a `{% trans "Price:" %}` label plus the pre-formatted bounds, applying the file's own purpose-chip pattern |
| `src/backend/apps/ads/views/listings.py` | the context supplying `active_price_min` / `active_price_max` | Supplies **formatted** bounds via the BLOCK 3 helper. **Verified: both routes already supply both keys — this is a value-shape change, not a missing key** |
| `src/backend/apps/search/views/search.py` | the same two context keys | The same change, so the two routes stay consistent |
| `src/backend/apps/ads/services/listings_query.py` | `ListingsQuery.active_price_range`, returning `tuple[Decimal \| None, Decimal \| None]` | **UNCHANGED.** The query layer returns `Decimal`s; formatting belongs at the view boundary |
| `src/backend/locale/ru/LC_MESSAGES/django.po`, `…/bs/…/django.po` | the chip's msgid | **CONDITIONAL** — only if the `blocktrans`→`trans` change alters an extracted msgid. §2.2 applies in full |

**Binding constraints**

1. **Format in the view, not in the template and not in the query.**
   `ListingsQuery.active_price_range` returns `Decimal`s and must keep doing so — a `Decimal` in a
   price range is the correct type at that layer.
2. **Use the BLOCK 3 helper exactly.** A second formatting call in the view is a second formatting
   path. Under `Q3` option (c) the chip inherits the ungrouped `bs` output — **state that inheritance
   in the commit body; do not let it be discovered later.**
3. **Both routes change in the same commit.** `listings.py` and `search.py` feed the same partial;
   updating one leaves a locale-dependent inconsistency between the listings and search views of the
   same page.
4. **A `None` bound must render exactly as today.** The current chip interpolates `None` when one side
   is open. Preserve the current unbounded rendering — **no new placeholder, no new translatable
   string invented to cover it.**
5. **`ru` and `bs` land in the same commit as any msgid change.** If the `blocktrans`→`trans` change
   alters the extracted msgid, the new msgid must carry a non-empty `msgstr` in **`ru` *and* `bs` in
   this commit**, or the i18n gate goes red. **Report the msgid delta explicitly.** Every new msgid
   is English.
6. **Do not touch the `<time datetime="…">` display in the same partial.** The ISO attribute is
   BLOCK 5's must-not-touch item and the adjacent display pattern is BLOCK 5's change. Separate
   commits keep a date regression attributable.
7. **Full §2.2 applies** if any `.po` is written: re-read all three immediately before `git add`,
   append never regenerate, never add a `.mo`, `--no-location` stays.
8. **No `.po` write is expected.** If one turns out to be required, that is a finding worth reporting,
   not a routine step.

**Implementor task**

```yaml
id: task_14_b04_price_chip
title: "Render the active-price filter chip through the corrected formatter (14-I18N-010)"
priority: medium
depends_on: [task_14_b03_price_format]
source_reference: ".ai/plans/25-i18n-remediation-execution.md"
source_section: "BLOCK 4 - The active-price filter chip"
source_blocks: ["BLOCK 4"]
description: >
  The active-price filter chip in the shared ad_list partial interpolates raw Decimal bounds through
  blocktrans, which applies no filter chain, so the summary shows 1000.50 with an ASCII point, no
  grouping and no currency code - directly above correctly formatted card prices in the same
  response. The remedy is the pattern already present in the same file: a trans label plus a
  pre-computed value passed through a filter. No new pattern is introduced.
goals:
  - "the chip renders the same grouped, localised, currency-suffixed price the cards do"
  - "both routes - listings and search - render identically, since they feed the same partial"
  - "introduce no new pattern and no new formatting entry point"
extra_context: |
  CITATION ROT, CORRECTED. The source plan says the in-file precedent is "fourteen lines below the
  defect". It is now ~97 lines below. THE SEMANTIC TARGET IS UNCHANGED AND UNAMBIGUOUS: the
  purpose chip's {% trans "Purpose:" %} label plus a pre-computed value passed through
  |get_lookup_name, in the same template. Locate it by that pattern. Do NOT carry the line-number
  citation forward.
  BINDING CONSTRAINTS (from section 3 BLOCK 4; none corrected - defect unchanged at 7f43e535)
  1. Format in the VIEW, not in the template and not in the query. ListingsQuery.active_price_range
     returns tuple[Decimal | None, Decimal | None] and must keep doing so.
  2. Use the BLOCK 3 helper exactly - no second formatting call in the view. Under Q3 option (c) the
     chip inherits the ungrouped bs output; state that inheritance in the commit body.
  3. Both routes in the same commit. Both were verified to supply both bounds, so this is a
     value-shape change, not a missing key.
  4. A None bound must render exactly as it does today. No new placeholder, no new translatable
     string.
  5. If the blocktrans -> trans change ALTERS the extracted msgid, the new msgid must carry a
     non-empty msgstr in ru AND bs in the SAME commit. Report the msgid delta explicitly. Every new
     msgid is English; en stays empty by convention.
  6. Do not touch the <time datetime="...|date:'Y-m-d'"> attribute or the display beside it in the
     same partial - both are BLOCK 5's.
  7. Section 2.2 in full if any .po is written: re-read all three immediately before git add; append
     never regenerate; never add a .mo; stage by path; --no-location stays.
  8. No .po write is expected. If one is required, report it.
  VERIFIED SYMBOL MAP (re-derived at 7f43e535; use symbols, never line numbers)
  - src/backend/templates/ads/partials/ad_list.html -> the active-price blocktrans chip, and the
    in-file precedent {% trans "Purpose:" %} {{ p|get_lookup_name:LANGUAGE_CODE }}
  - src/backend/apps/ads/views/listings.py -> supplies active_price_min and active_price_max
  - src/backend/apps/search/views/search.py -> supplies the same two keys
  - src/backend/apps/ads/services/listings_query.py -> ListingsQuery.active_price_range
  - the active catalogue entry is the python-format msgid "Price: %(min)s-%(max)s"
  - the same template also carries BLOCK 5's ISO datetime attribute and its defective display
    pattern - both untouched here
  FORBIDDEN: editing ListingsQuery; adding a second formatter; touching the date patterns;
  regenerating a catalogue wholesale; editing the BLOCK 5 display in this commit.
files:
  - path: src/backend/templates/ads/partials/ad_list.html
    targets: [{ type: template_block, name: active_price_filter_chip }]
  - path: src/backend/apps/ads/views/listings.py
    targets: [{ type: function, name: ads_listings_view }]
    semantic_anchors:
      insert_before:
        type: yaml_key
        value: active_price_max
  - path: src/backend/apps/search/views/search.py
    targets: [{ type: function, name: search_view }]
    semantic_anchors:
      insert_before:
        type: yaml_key
        value: active_price_max
  - path: src/backend/apps/ads/tests/test_price_format.py
    targets: []
    changes: []   # the chip rendering cases belong here, alongside the helper's other cases
  - path: src/backend/locale/ru/LC_MESSAGES/django.po
    targets: []
    changes: []   # ONLY if the msgid delta requires it; re-read immediately before git add
  - path: src/backend/locale/bs/LC_MESSAGES/django.po
    targets: []
    changes: []   # ONLY if the msgid delta requires it; non-empty msgstr required
changes:
  - action: change_code
    description: >
      Replace the blocktrans chip with a trans "Price:" label plus the pre-formatted bounds,
      applying the same pattern the purpose chip in the same file already uses.
  - action: change_code
    description: >
      Format both bounds in the view with the BLOCK 3 helper before they reach the template
      context, on both the listings and the search route.
  - action: add_test
    description: >
      Add cases to the existing price-format module that render the chip under
      translation.override for every LanguageLocale.values() member and assert the decimal separator
      matches the locale's - not merely that a separator is present - and that a None bound renders
      as it does today.
acceptance_criteria:
  - "the chip's rendered output uses the same separator and grouping as the card price in the same response, for all three locales"
  - "the listings and search routes render byte-identical chips for the same bounds"
  - "a None bound renders exactly as it did before this block"
  - "the test asserts an exact separator, not the presence of a separator"
  - "the cases live in the existing price-format module; no new test module and conftest.py untouched"
  - "if the extracted msgid changed, ru and bs carry a non-empty msgstr for it in this same commit"
  - "no .po file was regenerated wholesale; any .po edit is a targeted entry edit with a re-read
     immediately before git add, and no .mo appears in the diff"
  - "the commit body reports the msgid delta and, under Q3 option (c), the inherited bs grouping limitation"
```

---

### BLOCK 5 — `TIME_ZONE` and the four display date patterns

| | |
|---|---|
| **Findings owned** | `14-I18N-004` (MEDIUM, was HIGH) |
| **Class** | **mechanical** |
| **Depends on** | nothing in-plan |
| **Blocks** | BLOCK 12 |
| **Priority** | **P1** |
| **Risk level** | **MEDIUM.** The only change in the phase that is not backward-compatible — but the allowlist half of that risk is gone, because the value is hard-coded |
| **Blast radius** | Ad-card freshness timestamps, the ad detail page, search history, the seller dashboard's metric dates |
| **Required agents** | **Auditor · Researcher · Planner · Validator — all four.** Every rendered timestamp moves and the settings file is contended |

**`Q4` — ✅ RESOLVED 2026-10-03 (Product Owner). Both sub-answers are given; this block starts
unblocked and the Implementor chooses nothing.**

> 1. **The value:** `TIME_ZONE = "Europe/Podgorica"`.
> 2. **Env-overridability:** **NO. Hard-coded and NOT env-overridable.**
>
> Consequences, so no Implementor re-opens them:
> - **There is NO `ALLOWED_ENV_VARS` entry and NO `.env*.example` lines.** The allowlist collision
>   disappears entirely; those two file-surface rows are **not applicable — do not create.**
> - **No other phase's allowlist work is triggered.** `test_example_keys_in_allowlist` and the reverse
>   scanner have nothing new to check in either direction.
> - **The env-overridability branch is CLOSED.** Do not create the env surface "for operator
>   convenience".
> - `Europe/Belgrade` and `Europe/Sarajevo` are **declined** — they share today's offset, would
>   diverge if a jurisdiction changes, and the operating region is Montenegro.
> - The commit body records the ruling's date and that the zone was **ruled, not defaulted**.

**The defect.** `TIME_ZONE` is **absent from every module in the settings package**, so Django's
`America/Chicago` default (UTC−5/−6) applies to a Balkan marketplace. Separately, all four
user-visible date renderings hard-code en-US patterns. `USE_TZ` is `True` (Django 5's global
default), so this is **presentation only** — the naive/aware mismatch class does not exist here, which
is why the severity was reduced. **For an ad published between 00:00 and 07:00 local, the calendar day
itself is wrong, and a day-old ad can read as published today.**

**File surface (semantic units)**

| File | Element | Change |
|---|---|---|
| `src/backend/config/settings/base.py` | the i18n / locale block, beside `LANGUAGE_CODE` | Add `TIME_ZONE = "Europe/Podgorica"` as a **hard-coded literal — NOT read through `env()`**. Six-way contended: re-read immediately before editing and stop on a concurrent change |
| `src/backend/config/settings/base.py` | `ALLOWED_ENV_VARS` | 🚫 **NOT APPLICABLE — do not create.** `Q4` ruled the value non-env-overridable |
| `.env.dev.example`, `.env.test.example`, `.env.prod.example`, and the fourth template | a `TIME_ZONE=` line | 🚫 **NOT APPLICABLE — do not create.** No env line, so the allowlist has nothing new to check |
| `src/backend/templates/ads/detail.html` | the `{% trans "Published:" %}` display pattern | `'M d, Y'` → the locale `DATE_FORMAT`. **The adjacent `<time datetime="…">` ISO attribute is correct and must not change** |
| `src/backend/templates/ads/partials/ad_list.html` | the ad-card date display | `'M d'` → the locale `SHORT_DATE_FORMAT`. Same file as BLOCK 4 — the two ISO attributes must not change |
| `src/backend/templates/cabinet/search_history.html` | the search-history timestamp | `'M d, H:i'` → the locale `DATETIME_FORMAT` |
| `src/backend/templates/analytics/seller_dashboard.html` | the metric date | `'M d, Y'` → the locale `DATE_FORMAT` |
| `src/backend/config/settings/tests/test_settings_defaults.py` | a new `settings.TIME_ZONE` assertion | The natural home. It currently has **no** `TIME_ZONE` and **no** `LANGUAGE_*` assertion at all, and a concurrent phase-02 edit was landing in it — **re-read before adding one** |

**Binding constraints**

1. **The `|date:` inventory is complete and re-verified: exactly six occurrences in the whole
   template tree.** Two are the correct ISO `datetime=` attributes on `<time>` elements — **must not
   be swept into this change**. The other four are the defective display patterns. **There is nothing
   else to find, and nothing to "improve" while you are in there.**
2. **This block adds no msgid.** The `Published:`, `Date:` and `Time:` labels already exist in all
   three catalogues. **This is a `.po`-free block.** If a `makemessages` run is used to prove it,
   `git diff -- src/backend/locale` must come back empty.
3. **Use the locale format *names*, not new pattern strings.** `'DATE_FORMAT'`,
   `'SHORT_DATE_FORMAT'`, `'DATETIME_FORMAT'` are Django format names; the current `'M d, Y'`
   literals are the defect. A new per-locale pattern string reimplements the locale data in templates.
4. **The change is not backward-compatible and is not claimed to be.** Every rendered timestamp moves.
   That is the fix. **Record the before/after for one known instant in the commit body.**
5. **`base.py` is six-way contended.** Re-read immediately before editing. Stage by path, never by
   directory. The contention is now purely additive: one literal line.
6. **`TIME_ZONE` is a literal — do not use the file's `env()` idiom for this one setting.** That idiom
   is correct everywhere else in `base.py` and is unchanged; this one setting simply is not read from
   the environment, because `Q4` closed that branch.
7. **Do not touch `apps/core/utils/sanitize.py`, the bot's time handling, or any analytics query.**
   The change is display-timezone only; stored values are already aware and stay unchanged.
8. **The `<time datetime>` attributes are the machine-readable contract** — a screen reader, a crawler
   or a future JS enhancement reads them. Converting them to a locale format would break a consumer to
   make a human-facing string prettier.
9. **No `ALLOWED_ENV_VARS` entry, no `.env*.example` line, no other phase's allowlist work.**

**Implementor task**

```yaml
id: task_14_b05_timezone_and_dates
title: "Set TIME_ZONE and replace the four hardcoded en-US display date patterns (14-I18N-004)"
priority: medium
depends_on: []
source_reference: ".ai/plans/25-i18n-remediation-execution.md"
source_section: "BLOCK 5 - TIME_ZONE and the display date patterns"
source_blocks: ["BLOCK 5"]
description: >
  TIME_ZONE is absent from every module in the settings package, so Django's America/Chicago default
  applies to a Balkan marketplace, and all four user-visible date renderings hardcode en-US patterns
  ('M d, Y', 'M d', 'M d, H:i'). USE_TZ is True - Django 5's global default - so this is
  presentation only and no naive/aware integrity class exists, but for an ad published between
  00:00 and 07:00 local the calendar day itself is wrong. Six |date: uses exist in the whole
  template tree; two are correct ISO 8601 datetime attributes that must not change, and four are the
  defective display patterns.
goals:
  - "settings.TIME_ZONE is the ruled value Europe/Podgorica, hard-coded, and every rendered timestamp reflects it"
  - "the four display patterns use Django locale format names and the two ISO attributes are byte-identical"
  - "no msgid changes, so the catalogue diff is empty"
extra_context: |
  Q4 IS RESOLVED - 2026-10-03, Product Owner. BOTH sub-answers are given. (1) The value is
  Europe/Podgorica. (2) It is HARDCODED and NOT ENV-OVERRIDABLE. THEREFORE: NO ALLOWED_ENV_VARS
  entry and NO .env*.example lines. The allowlist collision disappears entirely and NO OTHER
  PHASE'S ALLOWLIST WORK IS TRIGGERED. The env-overridability branch is CLOSED - do not create the
  env surface for operator convenience. Europe/Belgrade and Europe/Sarajevo are DECLINED.
  THIS IS THE ONLY BLOCK THAT NEEDED NO RE-SCORING: every premise reproduced exactly at 7f43e535.
  BINDING CONSTRAINTS (from section 3 BLOCK 5; none corrected)
  1. The |date: inventory is complete and re-verified: six occurrences in the whole template tree.
     The two <time datetime="{{ ...|date:'Y-m-d' }}"> attributes in ads/detail.html and
     ads/partials/ad_list.html are correct ISO 8601 machine-readable values and MUST NOT change.
     The other four are the defective display patterns. Nothing else to find; nothing to improve.
  2. This block adds no msgid - the Published:, Date: and Time: labels already exist in all three
     catalogues. It is a .po-FREE block. If a makemessages run is used to prove it,
     "git diff -- src/backend/locale" must come back empty.
  3. Use the locale format NAMES ('DATE_FORMAT', 'SHORT_DATE_FORMAT', 'DATETIME_FORMAT'), not new
     pattern strings.
  4. This change is not backward-compatible and is not claimed to be: every rendered timestamp moves.
     Record the before/after for one known UTC instant in the commit body.
  5. config/settings/base.py is six-way contended (phases 02, 04, 06, 07, 08, 12). Re-read
     immediately before editing; stop and report a concurrent change; stage by path.
  6. TIME_ZONE IS A HARDCODED LITERAL - do NOT use the file's env() idiom for this one setting.
  7. Do not touch apps/core/utils/sanitize.py, the bot's time handling, or any analytics query.
     Stored values are already aware and do not change.
  8. The two datetime attributes are the machine-readable contract.
  9. No ALLOWED_ENV_VARS entry, no .env*.example line, no other phase's allowlist work.
  VERIFIED SYMBOL MAP (re-derived at 7f43e535; use symbols, never line numbers)
  - config/settings/base.py -> LANGUAGE_CODE = "ru", the LANGUAGES tuple, the env() helper,
    ALLOWED_ENV_VARS. TIME_ZONE and USE_TZ are absent from EVERY module in the settings package.
  - templates/ads/detail.html -> the "Published:" display beside a <time datetime="Y-m-d">
  - templates/ads/partials/ad_list.html -> the ad-card date display beside a
    <time datetime="Y-m-d">. Also BLOCK 4's file; re-read before editing.
  - templates/cabinet/search_history.html -> the search-history timestamp
  - templates/analytics/seller_dashboard.html -> the metric date
  - config/settings/tests/test_settings_defaults.py -> currently has NO TIME_ZONE and NO LANGUAGE_*
    assertion; a concurrent phase-02 edit was landing in it. Re-read before adding one.
  FORBIDDEN: editing the two ISO datetime attributes; editing a .po or .mo file; editing
  LanguagePreMiddleware; editing any stored-value or query-time conversion; adding an
  ALLOWED_ENV_VARS entry; editing any .env*.example.
files:
  - path: src/backend/config/settings/base.py
    targets: []
    semantic_anchors:
      insert_after:
        type: assignment
        value: LANGUAGE_CODE
  - path: src/backend/templates/ads/detail.html
    targets: [{ type: template_block, name: published_at_display }]
  - path: src/backend/templates/ads/partials/ad_list.html
    targets: [{ type: template_block, name: published_at_display }]
  - path: src/backend/templates/cabinet/search_history.html
    targets: [{ type: template_block, name: search_history_timestamp }]
  - path: src/backend/templates/analytics/seller_dashboard.html
    targets: [{ type: template_block, name: metric_date_display }]
  - path: src/backend/config/settings/tests/test_settings_defaults.py
    targets: []
    changes: []   # add a TIME_ZONE assertion; re-read first, a concurrent edit was landing
changes:
  - action: add_code
    description: >
      Add TIME_ZONE = "Europe/Podgorica" beside LANGUAGE_CODE as a hard-coded literal, NOT read
      through env(). No ALLOWED_ENV_VARS entry and no .env*.example lines - Q4 ruled the value
      non-env-overridable on 2026-10-03.
  - action: change_code
    description: >
      Replace the four defective display date patterns with the corresponding Django locale format
      names, leaving the two <time datetime="...|date:'Y-m-d'"> attributes untouched.
  - action: add_test
    description: >
      Assert settings.TIME_ZONE equals "Europe/Podgorica", that one known UTC instant renders to the
      expected local wall time under every LanguageLocale.values() member, and that the two ISO
      datetime attributes are byte-identical to their current values.
acceptance_criteria:
  - "settings.TIME_ZONE is the literal Europe/Podgorica, is NOT read from the environment, and a known UTC instant renders to the expected local wall time"
  - "ALLOWED_ENV_VARS is byte-unchanged and no .env*.example file gained a TIME_ZONE line; the allowlist test is green in both directions with nothing new to check"
  - "the four display patterns use locale format names; no per-locale pattern string is written in a template"
  - "the two <time datetime=\"...|date:'Y-m-d'\"> attributes are byte-identical to their pre-block state"
  - "git diff -- src/backend/locale is empty; this block adds no msgid"
  - "uv run djlint src/backend/templates/ reports no new finding"
  - "the commit body names the Q4 ruling (Product Owner, 2026-10-03), the chosen zone, that it was ruled and not defaulted, and a before/after rendering of one known instant"
```

---

### BLOCK 6 — `lang_pref`: one writer, hardened flags, honest cache contract

| | |
|---|---|
| **Findings owned** | `14-I18N-009` (MEDIUM), `14-I18N-011` (LOW), `14-I18N-012` (LOW, documentation only) |
| **Class** | **behavioural** |
| **Depends on** | **BLOCK 1** (the resolver must exist before the cookie's write path is touched) · **Gated on `Q5`** (§5.2) |
| **Blocks** | BLOCK 12 |
| **Priority** | **P1** |
| **Risk level** | **HIGH** — `Q5` is a **phase-06 boundary**, and the change removes a client-side code path |
| **Blast radius** | Every language switch on the site. `httponly` is a one-way door in practice: a JS writer that can no longer read or write the cookie breaks the switcher |
| **Required agents** | **Auditor · Researcher · Planner · Validator — all four.** This crosses a phase boundary and `httponly` is irreversible in practice |

**🔴 `Q5` — DECISION REQUIRED BEFORE IMPLEMENTATION, and it is a phase-06 decision, not a phase-14
one.** Phase 06 owns consent state (`ConsentRecord`, the `consent_preferences` context processor).
**The two writers still disagree and still disagree on attributes**: the middleware's
`set_cookie` supplies no `secure`, no `samesite` and no `httponly`, and it writes unconditionally
whenever `?lang=` is present; the switcher's inline JS writes the same cookie inside
`{% if consent_preferences %}` with a **hard-coded `SameSite=Lax`**. **Neither site references the
other.** Options, consequences and the decider: **§5.2.**

**Under every option, the two findings that are not in question ship:**

- **`14-I18N-011`** — pass `secure=settings.SESSION_COOKIE_SECURE`,
  `samesite=settings.SESSION_COOKIE_SAMESITE` and `httponly=True` to `set_cookie`. Both settings
  exist and are correct today; **this is a call-site change, not a settings change.**
  **`httponly=True` is only safe under option (a).**
- **`14-I18N-012`** — **correct the docstring, and nothing else.**

**✔ `14-I18N-012` — the header is not the defect, and this block is forbidden from changing it.**
The finding was reclassified to `DOC-UPDATE` **because the code is already correct**:
`CsrfViewMiddleware` adds `Vary: Cookie` on any response whose template called `get_token()`, and
every page does — so the emitted `Vary` in the real stack is `Cookie, Accept-Language` and a
`Vary`-honouring cache **already** keys on the cookie. The original probe drove
`LanguagePreMiddleware` in isolation through `RequestFactory`, bypassing `SessionMiddleware` and
`CsrfViewMiddleware` — **it measured the wrong stack.** What genuinely remains is that the docstring
misdescribes the contract and that the property is **incidental**: two HTMX fragments render no CSRF
token, so a fragment can lose `Vary: Cookie` without notice. **Do not add a `Vary: Cookie` header —
that is the specific wrong fix this finding warns about.**

**File surface (semantic units)**

| File | Symbol / element | Change |
|---|---|---|
| `src/backend/apps/core/middleware/language.py` | `LanguagePreMiddleware.process_response` — the `response.set_cookie(...)` call | Add the `secure` / `samesite` / `httponly` arguments. **No other cookie behaviour changes** |
| `src/backend/apps/core/middleware/language.py` | the module docstring's cache-contract paragraph | State that cookie-driven locale is covered by `Vary: Cookie` **via `CsrfViewMiddleware`**, that this is **incidental**, and what must be made deliberate when a shared cache is introduced |
| `src/backend/apps/core/middleware/language.py` | the docstring's cookie-write paragraph | Record which writer is authoritative, per `Q5` |
| `src/backend/templates/components/language_switcher.html` | the local `setCookie` helper and the `{% if consent_preferences %}`-gated click handler | **Only under `Q5` option (a)** — the gated branch is deleted. **The helper itself is only removed if nothing else uses it** |
| `src/backend/apps/core/tests/test_language_middleware.py` | the cookie-persistence tests | Assert the emitted cookie's `secure`, `samesite` and `httponly` attributes |
| `docs/01-spec/technical-specification.md` | the `lang_pref` cookie entry | 🚫 **DEFERRED — phase 06 holds the reservation.** Record the desired edit and route it. **Do not touch it here** |

**Binding constraints**

1. **✔ Do not add a `Vary` header.** Fix the docstring. `14-I18N-012` exists because the code is
   already correct; adding a header would be a redundant, undeclared change to a contract that
   already holds.
2. **`httponly=True` only under `Q5` option (a).** Under (b) and (c), ship `secure` and `samesite` and
   **withhold `httponly` with a comment saying why.**
3. **Do not change the cookie's `max_age`, its name, or the value written.** `_apply_lang_param`
   persists the **resolved canonical code**, and BLOCK 1 did not change that.
4. **`SESSION_COOKIE_*` is the source of truth, not literals.** Read `secure` and `samesite` from
   settings so `prod.py`'s strictness and `dev.py`/`test.py`'s relaxation keep working.
   **Do not edit `prod.py` or `dev.py`** — `prod.py` is phase 02's file.
5. **Under `Q5` option (a), verify the switcher works end-to-end with `httponly`.** Assert that
   `?lang=bs` still sets `lang_pref` **with no consent context present** — the case current tests do
   not cover.
6. **Deleting the JS branch must not delete a shared helper.** Read the whole `<script>` block first;
   if the local `setCookie` helper is used by another handler, **keep it** and remove only the gated
   call.
7. **Any new JS-visible string follows the `catalog_js_labels` pattern** —
   `apps/core/context_processors.py` → `header_context` → `catalog_js_labels`, consumed via
   `{{ catalog_js_labels|escapejs }}`. **A raw literal in a `<script>` block bypasses both
   `makemessages` and the gate.**
8. **Do not edit `docs/01-spec/technical-specification.md`.** Phase 06 holds the reservation.
9. **No `.po` write.**

**Implementor task**

```yaml
id: task_14_b06_lang_pref_cookie
title: "One writer for lang_pref, hardened cookie attributes, and a truthful cache contract (14-I18N-009, 14-I18N-011, 14-I18N-012)"
priority: medium
depends_on: [task_14_b01_locale_resolver]
source_reference: ".ai/plans/25-i18n-remediation-execution.md"
source_section: "BLOCK 6 - lang_pref: one writer, hardened flags, honest cache contract"
source_blocks: ["BLOCK 6"]
description: >
  The language switcher's inline JS writes lang_pref only inside a consent gate while the middleware
  writes the same cookie unconditionally whenever ?lang= was supplied; neither site references the
  other, and the client helper sets SameSite=Lax while the server sets none, so the two writers
  disagree on more than the gate and the weaker one lands last. Separately, lang_pref is the only
  cookie the project issues that opts out of all six SESSION_COOKIE_*/CSRF_COOKIE_* attributes the
  project sets elsewhere. And the middleware docstring presents
  patch_vary_headers(Accept-Language) as the complete cache contract when CsrfViewMiddleware is
  already adding Vary: Cookie on every full page - an incidental CSRF side effect, not a declared
  invariant.
goals:
  - "exactly one writer persists lang_pref, and the middleware docstring says which"
  - "the cookie carries the project's own secure / samesite / httponly policy, read from settings"
  - "the cache-contract docstring is true, and the Vary header itself is unchanged"
extra_context: |
  Q5 GATE - phase-06 boundary. DECISION REQUIRED BEFORE IMPLEMENTATION. The block does not start
  until the answer is written down and phase 06 has acknowledged it. Option (a): the server write is
  authoritative; delete the consent-guarded JS branch and say so in the middleware docstring.
  Option (b): the consent gate is real; move it into process_response and coordinate with phase 06,
  which owns ConsentRecord and the consent_preferences context processor. Option (c): defer; record
  the contradiction and ship only the unambiguous parts. httponly=True is safe ONLY under (a). See
  section 5.2 for consequences and for who decides. DO NOT CHOOSE.
  ALSO GATED: naming lang_pref in the technical specification's cookie list requires phase 06's
  clearance on docs/01-spec/technical-specification.md. That limb is DEFERRED, not skipped, unless
  phase 06 clears it.
  BINDING CONSTRAINTS (from section 3 BLOCK 6; none corrected - premises reproduced at 7f43e535)
  1. DO NOT ADD A Vary HEADER. Fix the docstring. 14-I18N-012 was reclassified to DOC-UPDATE
     because the code is ALREADY correct: CsrfViewMiddleware adds Vary: Cookie on any response
     whose template called get_token(), and every page does, so a Vary-honouring cache already keys
     on the cookie. The original probe drove LanguagePreMiddleware in isolation through
     RequestFactory and measured the wrong stack. What remains is that the property is
     INCIDENTAL - ads/partials/ad_list.html and categories/partials/mega_submenu.html render no
     csrf_token - so make the docstring say so, and record what must be made deliberate when a
     shared cache is introduced.
  2. httponly=True only under Q5 option (a). Under (b) and (c), ship secure and samesite and
     withhold httponly with a comment saying why.
  3. Do not change the cookie's max_age, its name, or the value written.
  4. Read secure and samesite from SESSION_COOKIE_SECURE and SESSION_COOKIE_SAMESITE - do not write
     literals. Do NOT edit prod.py or dev.py.
  5. Under Q5 option (a), verify the switcher end-to-end with httponly and add the case the
     current tests do not cover: ?lang=bs sets lang_pref with NO consent context present.
  6. Deleting the JS branch must not delete a shared helper. Read the whole script block first; if
     the local setCookie helper is used elsewhere, keep it and remove only the gated call.
  7. Any new JS-visible string follows the catalog_js_labels pattern -
     apps/core/context_processors.py -> header_context -> catalog_js_labels, consumed via
     {{ catalog_js_labels|escapejs }}. A raw literal in a <script> block bypasses both
     makemessages and the gate.
  8. Do not edit docs/01-spec/technical-specification.md - phase 06 holds the reservation.
  9. No .po write.
  VERIFIED SYMBOL MAP (re-derived at 7f43e535; use symbols, never line numbers)
  - src/backend/apps/core/middleware/language.py -> LanguagePreMiddleware.process_response calls
    response.set_cookie(LANGUAGE_COOKIE_NAME, cookie_value, max_age=LANGUAGE_COOKIE_MAX_AGE) with
    no secure, samesite or httponly, then patch_vary_headers(response, ("Accept-Language",)), then
    response.headers.setdefault("Content-Language", translation.get_language())
  - config/settings/base.py -> SESSION_COOKIE_SECURE / HTTPONLY / SAMESITE and the CSRF_COOKIE_*
    equivalents; config/settings/prod.py re-asserts the two _SECURE flags; dev.py and test.py relax
    them for local HTTP
  - src/backend/templates/components/language_switcher.html -> the local setCookie helper building
    ['max-age=...', 'path=...', 'SameSite=Lax'] and the {% if consent_preferences %} gated click
    handler
  FORBIDDEN: adding a Vary header; editing prod.py or dev.py; changing the cookie's name, max_age or
  value; editing docs/01-spec/technical-specification.md; editing a .po or .mo file.
files:
  - path: src/backend/apps/core/middleware/language.py
    targets:
      - type: method
        name: process_response
    semantic_anchors:
      insert_after:
        type: function_call
        value: response.set_cookie
  - path: src/backend/templates/components/language_switcher.html
    targets: [{ type: template_block, name: language_switcher_script }]
    changes: []   # ONLY under Q5 option (a); otherwise READ ONLY in this block
  - path: src/backend/apps/core/tests/test_language_middleware.py
    targets: [{ type: function, name: test_cookie_persists_canonical_code }]
    changes: []   # add attribute assertions; do not weaken existing ones
changes:
  - action: change_code
    description: >
      Pass secure=settings.SESSION_COOKIE_SECURE, samesite=settings.SESSION_COOKIE_SAMESITE and -
      only under Q5 option (a) - httponly=True to the lang_pref set_cookie call.
  - action: change_docstring
    description: >
      Correct the middleware's cache-contract docstring to state that cookie-driven locale is
      covered by Vary: Cookie via CsrfViewMiddleware, that this is incidental rather than declared,
      and what must be made deliberate when a shared cache is introduced.
  - action: change_docstring
    description: >
      Record in the cookie-write docstring which writer is authoritative, per the Q5 answer.
  - action: change_code
    description: >
      Under Q5 option (a) only: remove the consent-gated JS write from language_switcher.html,
      keeping the shared setCookie helper if anything else uses it.
  - action: add_test
    description: >
      Assert the emitted lang_pref cookie's secure, samesite and httponly attributes, and - under
      option (a) - that ?lang=bs sets the cookie with no consent context present.
acceptance_criteria:
  - "the lang_pref cookie carries the project's own secure and samesite values, read from settings rather than written as literals"
  - "httponly is True under Q5 option (a); under (b) or (c) it is absent and a comment states why"
  - "the response's Vary header is byte-identical to its pre-block state - this block adds no header"
  - "the middleware docstring no longer presents patch_vary_headers(Accept-Language) as the complete cache contract"
  - "the docstring names Vary: Cookie via CsrfViewMiddleware and states that the coverage is incidental"
  - "the cookie's name, max_age and written value are unchanged"
  - "config/settings/prod.py and dev.py are untouched"
  - "under Q5 option (a), the language switcher works end-to-end with httponly set"
  - "the commit body names the Q5 option chosen, the reason, whether phase 06 cleared the
     technical-specification limb, and the deferral if it was not cleared"
```

---

### BLOCK 7 — A plural-aware `.po` parser

| | |
|---|---|
| **Findings owned** | `14-I18N-005` (MEDIUM) |
| **Class** | **behavioural** |
| **Depends on** | nothing in-plan |
| **Blocks** | **BLOCK 11 (strict)** — a credible stale-entry gate needs this parser. Also a prerequisite of BLOCKS 9 and 10 |
| **Priority** | **P1** — do it before any block that reads a catalogue |
| **Risk level** | **MEDIUM** — a shared helper with two call sites, but a small one |
| **Blast radius** | Every `.po`-reading test in the phase. BLOCKS 9, 10 and 11 all sit on top of it |
| **Required agents** | **Auditor · Planner · Validator.** The change is one return type and one function body; **the ordering it enables is the real risk** |

**The defect.** `_parse_po_entries` reassigns its accumulator on **every** `msgstr`-prefixed line,
**including `msgstr[N]`**, discarding all but the last plural form. Both copies of
`test_no_empty_msgstr` then ask "is any `msgstr` blank?", which for a plural entry is only ever a
question about the **last** form. **The docstring claims the parser shares "the first `msgstr` value
encountered"; the implementation keeps the last.**

**🔴 RE-SCOPED — the source plan's severity label "Latent" is wrong. It is LIVE.** Measured at
`7f43e535`: `ru` and `bs` have 2 plural entries with 3 forms each, complete; **`en` has 2 plural
entries with only 2 forms and BOTH forms blank.** So the bug is not merely losing information:

- for `ru`/`bs` it **silently discards forms 0 and 1**;
- for `en` it reads a **blank final form** and reports a legitimately-untranslated-by-convention entry
  **as if it were the only form** — which is precisely the false green that a completeness gate must
  not produce.

**Any BLOCK 11 gate built on this parser inherits that blind spot. BLOCK 7 therefore precedes
BLOCK 11 strictly, and the ordering is now load-bearing rather than tidy.**

**File surface (semantic units)**

| File | Symbol | Change |
|---|---|---|
| `src/backend/testing/i18n_helpers.py` | `_parse_po_entries` | Return `list[tuple[str, list[str]]]` — the msgid and **all** its `msgstr` forms — instead of `list[tuple[str, str]]`. Accumulate `msgstr[N]` forms instead of overwriting, and **rewrite the docstring to match the behaviour** |
| `src/backend/apps/ads/tests/test_i18n_completeness.py` | `test_no_empty_msgstr` | Flatten: **any** blank form is a violation, not only a blank final form |
| `src/backend/apps/ads/tests/test_i18n_pipeline.py` | `test_no_empty_msgstr` — the second copy | The same change. **The two copies are functionally equivalent and both carry the blind spot** |
| `src/backend/apps/ads/tests/test_i18n_pipeline.py` | a new parser unit case | Feed the parser a **synthetic** plural entry with a blank `msgstr[0]` and assert the blank form is reported. **D-2: this goes in the existing module, not a new file** |

**Binding constraints**

1. **Correct the docstring.** It currently describes behaviour the implementation does not have. **A
   docstring that lies is the class of defect this block exists to remove.**
2. **The `en` skip stays exactly as it is, in both call sites.** `en` may have empty `msgstr`s — that
   is the documented convention, and filling them is a 445-entry diff that changes nothing at runtime.
   **The `en` plural entries being blank is correct and must not be "fixed".**
3. **Do not reorder or renumber plural forms.** `msgstr[0..2]` for `ru`/`bs` and `msgstr[0..1]` for
   `en` are **CLDR-correct**. The two `bs` plural entries that share `msgstr[1]` and `msgstr[2]` are
   **correct for `bs`** — do not "fix" them.
4. **A parser test never observed failing is unverified.** **Demonstrate the blank `msgstr[0]` case
   failing before the fix and passing after**, in the same session.
5. **Both call sites change in the same commit.** A half-migrated return type is a type error, and the
   two `test_no_empty_msgstr` copies are why the phase has two of them.
6. **Enumerate every other caller of `_parse_po_entries` before committing** — including
   `test_no_cyrillic_msgids` and `test_extraction_completeness` — **do not discover them from a red
   run.**
7. **No catalogue file is edited.** The parser changes; the `.po` files do not.

**Implementor task**

```yaml
id: task_14_b07_plural_parser
title: "Make the shared .po parser plural-aware so any blank msgstr form is reported (14-I18N-005)"
priority: medium
depends_on: []
source_reference: ".ai/plans/25-i18n-remediation-execution.md"
source_section: "BLOCK 7 - A plural-aware .po parser"
source_blocks: ["BLOCK 7"]
description: >
  _parse_po_entries reassigns its accumulator on every msgstr-prefixed line including msgstr[N],
  keeping only the last plural form, and its docstring claims it keeps the first. Both copies of
  test_no_empty_msgstr then ask a question that is only ever about the last form. RE-SCOPED: the
  source plan called this latent; it is LIVE. en ships 2 plural entries with BOTH forms blank and 2
  forms where ru/bs have 3, so the bug silently discards forms 0 and 1 for ru/bs and reports an
  untranslated-by-convention en entry as if it were the only form. BLOCK 11's stale-entry gate needs
  this parser, because one of the orphans is a wrapped multi-line msgid that a line-anchored regex
  misses, and because a parser that cannot see a blank non-final form cannot gate anything about
  plural entries.
goals:
  - "the parser returns every msgstr form, so a blank non-final form is detectable"
  - "both copies of test_no_empty_msgstr fail on any blank form"
  - "the parser docstring describes what the code does"
extra_context: |
  RE-SCOPING NOTE. The source plan says: "It is latent, not live. Measured: ru 2 plural entries, 0
  with any empty form; bs 2, 0; en 2, 2 empty (the documented en exemption)." The first two halves
  reproduce. THE THIRD IS MISREAD: en's 2 blank plural entries are not the documented en exemption at
  work - the exemption is about SINGLE-form entries. The en plural entries also have only 2 FORMS where
  ru/bs have 3. The bug is therefore live, not latent, and the severity label is raised. The
  deliverable and the ordering do not change.
  BINDING CONSTRAINTS (from section 3 BLOCK 7)
  1. Correct the docstring. It currently describes behaviour the implementation does not have.
  2. The `en` skip stays EXACTLY as it is, in BOTH call sites. en may have empty msgstrs - the
     documented convention. Filling them is a 445-entry diff that changes nothing at runtime.
  3. Do not reorder or renumber plural forms. msgstr[0..2] for ru/bs and msgstr[0..1] for en are
     CLDR-correct. The two bs plural entries sharing msgstr[1] and msgstr[2] are CORRECT for bs.
  4. Demonstrate the blank-msgstr[0] case failing before the fix and passing after. A parser test
     never observed failing is unverified.
  5. Both call sites change in the same commit.
  6. Enumerate every other caller of _parse_po_entries before committing - including
     test_no_cyrillic_msgids and test_extraction_completeness - do not discover them from a red run.
  7. No catalogue file is edited by this block.
  VERIFIED SYMBOL MAP (re-derived at 7f43e535; use symbols, never line numbers)
  - src/backend/testing/i18n_helpers.py -> _parse_po_entries(text: str) -> list[tuple[str, str]],
    whose docstring claims it shares the FIRST msgstr value encountered while the body keeps the
    LAST
  - src/backend/apps/ads/tests/test_i18n_completeness.py -> test_no_empty_msgstr, which skips `en`
    by continue
  - src/backend/apps/ads/tests/test_i18n_pipeline.py -> test_no_empty_msgstr, the second copy, which
    skips `en` by continue AFTER computing the list - functionally equivalent, same blind spot
  - both use the identical expression
    empty = [msgid for msgid, msgstr in entries if msgid and not msgstr.strip()]
  - testing/i18n_helpers.py has exactly TWO callers: test_i18n_completeness.py and
    test_i18n_pipeline.py. The parser unit case therefore belongs in test_i18n_pipeline.py (D-2),
    not in a new module.
  - catalogue facts: the two plural entries are "%(counter)s view" and "%(counter)s contact";
    ru/bs carry 3 forms each and are complete; en carries 2 forms and both are blank.
  FORBIDDEN: editing any .po or .mo file; filling en msgstrs; "fixing" the shared bs plural forms;
  splitting the change across two commits; creating a new test module; editing conftest.py.
files:
  - path: src/backend/testing/i18n_helpers.py
    targets: [{ type: function, name: _parse_po_entries }]
  - path: src/backend/apps/ads/tests/test_i18n_completeness.py
    targets: [{ type: function, name: test_no_empty_msgstr }]
  - path: src/backend/apps/ads/tests/test_i18n_pipeline.py
    targets: [{ type: function, name: test_no_empty_msgstr }]
    changes: []   # also the home for the new parser unit case (D-2)
changes:
  - action: change_signature
    description: >
      Return list[tuple[str, list[str]]] from _parse_po_entries so each entry carries every msgstr
      form, accumulating msgstr[N] lines rather than overwriting the accumulator, and rewrite the
      docstring to match the implementation exactly.
  - action: change_code
    description: >
      Flatten in both test_no_empty_msgstr copies: any blank form is a violation, not only a blank
      final form.
  - action: add_test
    description: >
      Add a parser unit case to test_i18n_pipeline.py that feeds _parse_po_entries a SYNTHETIC plural
      entry with a blank msgstr[0] and asserts the blank form is reported as a violation. The
      synthetic entry is the test's own literal - do not read it from a catalogue, because the
      catalogues' plural entries are correct.
acceptance_criteria:
  - "a synthetic plural entry with a blank msgstr[0] is reported as a violation by both test_no_empty_msgstr copies"
  - "the failure was demonstrated before the fix and the pass after it, in the same session"
  - "the `en` skip is byte-identical in both call sites"
  - "every existing caller of _parse_po_entries still compiles and passes"
  - "the parser docstring describes the actual behaviour, first-vs-last discrepancy resolved"
  - "the plural form counts for ru/bs (3) and en (2) are unchanged; no form was renumbered"
  - "the new case lives in test_i18n_pipeline.py; no new test module and conftest.py untouched"
  - "no .po or .mo file was modified by this block"
```

---

### BLOCK 8 — Collector widening and the `hreflang` include assertion

| | |
|---|---|
| **Findings owned** | `14-I18N-006` (MEDIUM), `14-I18N-007` (MEDIUM), `14-I18N-008` (MEDIUM) |
| **Class** | **behavioural** — every assertion here can turn the currently-green gate red on arrival |
| **Depends on** | **Q9 pre-block step** (measurement, then a decision — §5.4) |
| **Blocks** | BLOCK 9 (the widened bot collector defines the exemption set BLOCK 9 needs), BLOCK 11 |
| **Priority** | **P1** |
| **Risk level** | **MEDIUM-HIGH** — a widened scanner is exactly the change that turns a green gate red on arrival |
| **Blast radius** | The whole i18n completeness gate, which every phase depends on |
| **Required agents** | **Auditor · Researcher · Planner · Validator — all four.** The widened collector's first run is a **prediction that has never been executed** |

**🟡 RE-SCOPED — the change table must be re-derived, not inherited.** The gate module has grown to
**1099 lines** and already contains `test_no_hardcoded_js_strings`, `test_hreflang_present` (with its
`x-default` assertion), `test_bot_no_hardcoded_messages`, `test_no_cyrillic_msgids`,
`test_bot_no_raw_model_field_access`, `test_title_tags_translated`, `test_plural_forms`,
`test_plural_forms_runtime` and `test_locale_switch_re_render` — **none of them enumerated by the
source plan**. The Implementor **re-reads the module and re-derives the insertion points** before
editing (D-3). What did **not** change and is load-bearing: `exclude_subpaths` is still exactly
`("admin/", "analytics/moderation_dashboard.html", "components/feature_tag.html")`, and no newer
phase has touched it.

**Q9 is a pre-block Auditor step, not a preference gate.** The Auditor must run each widened collector
against the current tree and report **exactly which files fail and why**. **The premise holds and the
run has not been performed** (`7f43e535`): `lifecycle.py`'s `_COMMANDS` still holds **twelve**
non-gettext `BotCommand(command=…, description=…)` literals — four per language across `ru`/`bs`/`en` —
with a module comment explaining they are deliberately not msgids, because an eager `_()` would freeze
the string at import time. **Four of their strings are the `14-I18N-014` orphans.** 🟡 **The collector
has no committed, reviewable harness** — the scratch probe in `.ai/tmp/` is untracked and was never
executed. **Build the widened collector as part of this block; do not rely on `.ai/tmp/`.**

**File surface (semantic units)**

| File | Symbol | Change |
|---|---|---|
| `src/backend/apps/ads/tests/test_i18n_completeness.py` | `_collect_bot_handler_files` | Widen to `src/telegram_bot` minus `tests/` |
| `src/backend/apps/ads/tests/test_i18n_completeness.py` | `_collect_bot_source_files` | Same root, same exclusion |
| `src/backend/apps/ads/tests/test_i18n_completeness.py` | `_collect_template_files` (and `_template_source`, which shares the limitation) | Widen to `TEMPLATES["DIRS"]` ∪ each installed app's `path`/`templates`, with `exclude_subpaths` applied **relative to each root** |
| `src/backend/apps/ads/tests/test_i18n_completeness.py` | `test_hreflang_present` | It renders the partial **in isolation** and never inspects a page template. Add the source-level assertion over non-partial templates that each contains the `locale_head.html` include, excluding the partial itself and reconciling with the exclusion list |
| `src/backend/apps/ads/tests/test_i18n_completeness.py` | the new named exemption set | **One** module-level definition the collectors, the `hreflang` assertion, BLOCK 9 and BLOCK 11 all read |
| `src/backend/apps/ads/tests/test_i18n_completeness.py` | a new collector case | Prove the widened set reaches modules that were previously invisible (D-2: same module, no new file) |
| `docs/99-agent/rules.md` | the scan-scope bullet | **Read before writing** — phase 12 holds a conditional claim. Records the new exemption |

**Binding constraints**

1. **Collect by walking, not by listing.** `rglob("*.py")` over `src/telegram_bot` minus `tests/`;
   app-template roots from each installed app's `path` unioned with `TEMPLATES["DIRS"]`. **Never a
   hard-coded module list** — `handlers/ad_create.py` is a **nine-module package**, and a hard-coded
   list would silently lose all nine.
2. **One named, documented exemption set, four consumers.** The `lifecycle.py` command-menu literals
   are its **first** member, and BLOCKS 9 and 11 read it. One definition, four readers, no divergent
   list.
3. **The existing exclusion tuple is preserved as-is** — `admin/`,
   `analytics/moderation_dashboard.html`, `components/feature_tag.html` — and stays in sync with the
   exemption list in `docs/99-agent/rules.md`.
4. **The `hreflang` assertion must exclude the partial itself and must reconcile with the exclusion
   list.** Two templates are **both** excluded from `_collect_template_files` **and** both include the
   partial. **Reconciling that is part of the work, not an edge case.**
5. **Never hard-code a file count.** Any guard derives its expectation from the collector.
6. **Add a positive assertion that at least one app-level template root is discovered** once one
   exists — otherwise a refactor that moves every template into apps silently reduces the gate to
   nothing and the guard stays green.
7. **The two HTMX fragments render no `csrf_token`. Do NOT "fix" that here.** It is the incidental-`Vary`
   fragility `14-I18N-012` records and BLOCK 6 documents. Adding a CSRF token to a fragment changes
   cache semantics for a reason outside this finding.
8. **Every new assertion must be demonstrated failing** before the commit. A widened collector that has
   never been seen red is an unverified claim that the widening was necessary.
9. **No catalogue file is edited.** No `.mo` is edited or added. `conftest.py` is never touched.
10. **Re-read the gate module before editing (D-3)** and report any concurrent change rather than
    clobbering it.
11. **Read `docs/99-agent/rules.md` before writing to it** — phase 12 holds a conditional claim.

**Implementor task**

```yaml
id: task_14_b08_gate_collectors
title: "Widen the bot and template collectors and assert every page template includes the locale partial (14-I18N-006, 14-I18N-007, 14-I18N-008)"
priority: medium
depends_on: []
source_reference: ".ai/plans/25-i18n-remediation-execution.md"
source_section: "BLOCK 8 - Collector widening and the hreflang include assertion"
source_blocks: ["BLOCK 8"]
description: >
  The i18n gate's bot collectors hard-code handlers/ and services/ instead of walking
  src/telegram_bot and excluding only tests/, and its template collector iterates
  TEMPLATES["DIRS"] while APP_DIRS is True. The unscanned bot set includes __init__.py, lifecycle.py,
  main.py, retry.py, states.py, the middlewares package - including the module that activates the
  locale for every update - and the schemas package. test_hreflang_present renders
  components/locale_head.html in isolation and never inspects a page template, while its docstring
  claims the partial is included by every page template. Every page template does include it today -
  this is a coverage gap, not a live defect - and the gate reads as if the site-wide property were
  enforced.
goals:
  - "every bot module except tests/ is scanned, with a named and documented exemption set"
  - "app-level template directories are scanned, and the gate fails if it discovers no root"
  - "the site-wide hreflang include property is asserted, not just the partial's own rendering"
extra_context: |
  Q9 PRE-BLOCK STEP - the Auditor runs each widened collector against the current tree BEFORE the
  block starts and reports exactly which files fail and why. THE PREMISE HOLDS AND THE RUN HAS NOT
  BEEN PERFORMED at 7f43e535: src/telegram_bot/lifecycle.py -> _COMMANDS holds twelve non-gettext
  BotCommand literals, four per language, with a module comment explaining they are deliberately not
  msgids. FOUR OF THEIR STRINGS ARE THE 14-I18N-014 ORPHANS (Start, Language, Post ad, Alerts). This
  block does not assume the outcome. There is NO COMMITTED HARNESS for the widened run - the probe in
  .ai/tmp/ is untracked scratch and was never executed - so BUILD THE COLLECTOR AS PART OF THIS BLOCK
  rather than relying on .ai/tmp/.
  RE-SCOPING NOTE (D-3). The gate module is now 1099 lines and already contains
  test_no_hardcoded_js_strings, test_hreflang_present (with its x-default assertion),
  test_bot_no_hardcoded_messages, test_no_cyrillic_msgids, test_bot_no_raw_model_field_access,
  test_title_tags_translated, test_plural_forms, test_plural_forms_runtime and
  test_locale_switch_re_render. The source plan's change table was written against a smaller file.
  RE-READ THE MODULE AND RE-DERIVE THE INSERTION POINTS before editing. exclude_subpaths is UNCHANGED
  and remains load-bearing.
  BINDING CONSTRAINTS (from section 3 BLOCK 8; none corrected)
  1. Collect by WALKING, not by listing. rglob("*.py") over src/telegram_bot minus tests/;
     app-template roots from each installed app's path unioned with TEMPLATES["DIRS"]. Never a
     hard-coded module list - handlers/ad_create.py is a NINE-MODULE PACKAGE and a hard-coded list
     would silently lose all nine.
  2. The exclusion list is a named, documented set with ONE definition, read by the collectors, the
     hreflang assertion, BLOCK 9 and BLOCK 11. The lifecycle.py command-menu literals are the first
     named exemption.
  3. The existing exclusion tuple is preserved as-is - admin/,
     analytics/moderation_dashboard.html, components/feature_tag.html - and stays in sync with the
     exemption list in docs/99-agent/rules.md.
  4. The hreflang include assertion must EXCLUDE the partial itself and must reconcile with the
     exclusion list: two templates are BOTH excluded from _collect_template_files AND both include
     the partial.
  5. NEVER HARD-CODE A FILE COUNT. The report's "43 templates" is stale and so is the plan's "38". Any
     guard derives its expectation from the collector.
  6. Add a positive assertion that at least one root was discovered, so a collector that silently
     matches nothing fails.
  7. ads/partials/ad_list.html and categories/partials/mega_submenu.html render no csrf_token. Do
     NOT "fix" this here by adding one - it is the incidental-Vary fragility 14-I18N-012 records and
     BLOCK 6 documents it.
  8. Demonstrate every new assertion failing at least once before the commit.
  9. No catalogue file is edited, and no .mo is edited or added.
  10. Re-read the gate module before editing (D-3) and report any concurrent change.
  11. Read docs/99-agent/rules.md before writing to it - phase 12 holds a CONDITIONAL claim.
  12. All new cases go in test_i18n_completeness.py itself (D-2). NO new test module; never conftest.py.
  VERIFIED SYMBOL MAP (re-derived at 7f43e535; use symbols, never line numbers)
  - src/backend/apps/ads/tests/test_i18n_completeness.py -> _collect_bot_handler_files,
    _collect_bot_source_files, _collect_template_files, _template_source, test_hreflang_present,
    and the exclude_subpaths tuple
  - _collect_template_files walks tmpl_cfg.get("DIRS", []) and never reads APP_DIRS
  - config/settings/base.py -> TEMPLATES sets DIRS to the project template root and APP_DIRS to True
  - src/backend/templates holds only .html files; no apps/*/templates directory exists, so the
    APP_DIRS gap is latent today
  - components/locale_head.html is referenced by the page templates plus the partial's own header
    comment - DERIVE the count from the collector, never hard-code it
  FORBIDDEN: editing a .po or .mo file; adding a csrf_token to a fragment; hard-coding a template or
  module count; editing src/backend/conftest.py; creating a new test module.
files:
  - path: src/backend/apps/ads/tests/test_i18n_completeness.py
    targets:
      - type: function
        name: _collect_bot_handler_files
      - type: function
        name: _collect_bot_source_files
      - type: function
        name: _collect_template_files
      - type: function
        name: _template_source
      - type: function
        name: test_hreflang_present
  - path: docs/99-agent/rules.md
    targets: []
    changes: []   # read-before-write; phase 12 holds a conditional claim
changes:
  - action: change_code
    description: >
      Widen both bot collectors to rglob over src/telegram_bot excluding tests/, and widen the
      template collector to TEMPLATES["DIRS"] unioned with each installed app's path/templates with
      exclude_subpaths applied relative to each root.
  - action: add_code
    description: >
      Introduce ONE named, documented exemption set - starting with the lifecycle.py command-menu
      literals - and have every consumer read it.
  - action: add_test
    description: >
      Add a source-level assertion that every non-partial page template contains the
      components/locale_head.html include, excluding the partial itself and reconciling with the
      documented exclusion list.
  - action: add_test
    description: >
      Add a positive assertion that at least one root was discovered, so a collector that silently
      matches nothing fails.
  - action: add_test
    description: >
      Add collector cases proving the widened bot set reaches previously invisible modules - the
      middleware package, the retry/state modules and the nine-module handlers/ad_create package.
acceptance_criteria:
  - "the widened bot collector reaches retry.py, states.py, the middlewares package and the nine-module handlers/ad_create package"
  - "the widened template collector discovers app-level template directories when they exist, and fails if it discovers no root at all"
  - "the lifecycle.py exemption is named once and read by every consumer, with the reason recorded next to it"
  - "the hreflang assertion covers every page template, excludes components/locale_head.html itself, and does not fail on the two templates that are both excluded and inclusive"
  - "no assertion anywhere hard-codes a template, module or file count"
  - "every new assertion was demonstrated failing at least once before the commit"
  - "the two csrf_token-free fragments are unchanged"
  - "all new cases live in test_i18n_completeness.py; no new test module and conftest.py untouched"
  - "no .po or .mo file was modified by this block"
  - "the gate is green on arrival with the documented exemptions in place; if it is not, that is the
     Q9 answer and it is REPORTED, not suppressed"
```

---

### BLOCK 9 — A `msgstr` script gate, and the three real `bs` strings

| | |
|---|---|
| **Findings owned** | **`N-1`** (new, MEDIUM) — the detection rule, and conditionally the three `bs` strings |
| **Class** | **conditional** — ships the **reduced deliverable** (detection rule + named commented exemptions) while `Q1` is `OPEN-PENDING-REVIEWER` |
| **Status** | 🚧 **`Q1` = `OPEN-PENDING-REVIEWER` as of 2026-10-03 — NOT closed.** The *who* is ruled (a native, preferably Montenegrin reviewer; machine output and translation APIs are **not** acceptable); the *sign-off* does not exist. **This block is runnable now and ships its reduced deliverable.** It is not blocked and it is not settled |
| **Depends on** | **BLOCK 7** (the parser) and **BLOCK 8** (the exemption set this block's gate reuses) |
| **Blocks** | BLOCK 11, BLOCK 12 |
| **Priority** | **P1** |
| **Risk level** | **MEDIUM** — small catalogue edits, but this is the block where a machine would be tempted to invent a translation |
| **Blast radius** | One `.po` file (`bs`) and one gate |
| **Required agents** | **Auditor · Planner · Validator.** **No translation is written by anyone; `Q1` is an owner/linguist decision** |

**The detection rule is engineering and ships unconditionally.** The gate's own docstring declares the
blind spot in writing: `test_no_cyrillic_msgids` says *"msgstr values for ru/bs are naturally
Cyrillic and exempt"* and inspects `msgid` only. **That reasoning is right for `ru` and wrong for
`bs`, where Cyrillic is contamination by construction.**

**✔ This plan writes none of the three strings, and the Implementor is forbidden from writing,
guessing, machine-translating or "approximating" any of them.** Phase 09's outbound Google-Translate
client is explicitly **not** a catalogue tool, and project rule 1 makes every `msgid` English. **The
2026-10-03 ruling reinforces this: machine output and translation APIs are not acceptable, so "there
is no reviewer yet" is the *only* reason the strings ship as-is — it is not a licence to produce them
another way.**

**`Q2` does not gate this block, and its 2026-10-03 answer does not change that.** The code context
claims Option A for `14-I18N-013` would remove two of the three strings from scope. **The tree does
not support it**: `14-I18N-013` is about *model metadata* (`verbose_name` / `help_text`) — a different
surface from a template that is **already** in the gate's `exclude_subpaths` tuple. **`Q1` and `Q2` are
independent**, and the fact that `Q2` resolved while `Q1` stayed open is the proof.

**Block outcomes — the `Q1` gate is `OPEN-PENDING-REVIEWER`, so the first row is the current one**

| `Q1` outcome | What ships |
|---|---|
| 🚧 **Current state — no reviewer sign-off yet (2026-10-03)** | **The detection rule plus a named, commented exemption for all three**, and the commit body says the gate is **`OPEN-PENDING-REVIEWER`**, not closed. **When the sign-off arrives, a follow-up commit supplies the three values and removes the exemptions; the gate closes then** |
| A linguist supplies all three | The detection rule **and** the three corrected `msgstr` values, in one commit. The gate goes green having been red in the tree, and its failure is demonstrated in the same session |
| A linguist supplies some | The detection rule, the corrected ones, and a **named, commented exemption** for each string knowingly shipped as-is — with the commit body stating plainly the finding is **not closed** for those |
| **Gate red on arrival with no exemption recorded** | 🚫 **This commit must not be made.** Re-apply the previous `bs` content and re-plan. **The gate is never committed red** |

**File surface (semantic units)**

| File | Symbol / element | Change |
|---|---|---|
| `src/backend/apps/ads/tests/test_i18n_completeness.py` | `test_no_cyrillic_msgids` | **Add a sibling assertion; do not weaken the existing one.** A Cyrillic code point in a **`bs` `msgstr`** is a violation; a Cyrillic code point in a **`ru` `msgstr`** is correct and stays exempt. **The rule is locale-scoped**, which is why the existing blanket `msgstr` exemption can be narrowed without breaking `ru` |
| `src/backend/apps/ads/tests/test_i18n_completeness.py` | a new sibling case | Proves the rule is **not** "no Cyrillic anywhere", which would be wrong for `ru` (D-2: same module) |
| `src/backend/locale/bs/LC_MESSAGES/django.po` | the three `msgstr` values, addressed **by msgid** | **Targeted entry edits only. Never regenerated.** §2.2 in full |
| `src/backend/locale/{ru,en}/LC_MESSAGES/django.po` | — | **UNTOUCHED.** `ru`'s Cyrillic `msgstr`s are correct; `en` is empty by convention |

**Binding constraints**

1. **The `msgid` never changes.** These are `msgstr`-only corrections. Changing a `msgid` re-extracts
   the key and orphans the entry.
2. **No machine translation. No invented `bs`.** The three values come from the `Q1` reviewer or they
   are exempted. **This is the block's single hardest rule.**
3. **The new assertion is locale-scoped.** `ru` legitimately contains hundreds of Cyrillic `msgstr`s;
   a blanket "no Cyrillic in `msgstr`" rule would fail immediately and be disabled. The rule is:
   **Cyrillic in a `bs` `msgstr` is a violation; Cyrillic in a `ru` `msgstr` is correct.**
4. **The rule is about script, not language quality.** It catches the Cyrillic `а` inside `oglasa` and
   the Russian verb. **It cannot tell a fluent wrong-language translation from a right one, and it
   does not pretend to.** A general quality gate is out of scope and would be a
   machine-translation judgement.
5. **The `Start` copy-through is NOT corrected here.** It is one of the `14-I18N-014` orphans and
   **BLOCK 10 prunes it.** Fixing a string that is about to be deleted is wasted work.
6. **The six legitimate copy-through entries are not corrected**: `ID`, `Telegram ID:`, `Pro`,
   `Telegram`, `Google Translate`, `Plausible Analytics`. Brand and product names, correctly identical
   in Bosnian.
7. **The two `bs` plural entries that share `msgstr[1]`/`msgstr[2]` are CORRECT** for `bs` CLDR. Do not
   "correct" them.
8. **Any exemption is a named, commented entry with a reason and an owner — not a `pytest.skip`.** An
   exemption without a reason is how the next string opts out silently.
9. **§2.2 in full**: re-read all three `.po` files immediately before any extraction and again
   immediately before `git add`; append never regenerate; stage by path; never add a `.mo`.
10. **If the gate would be red on arrival with no exemption recorded, this commit must not be made.**

**Implementor task**

```yaml
id: task_14_b09_bs_script_gate
title: "Add a bs-scoped msgstr script gate and record the linguist-pending exemptions (N-1)"
priority: medium
depends_on: [task_14_b07_plural_parser, task_14_b08_gate_collectors]
source_reference: ".ai/plans/25-i18n-remediation-execution.md"
source_section: "BLOCK 9 - A msgstr script gate, and the three real bs strings"
source_blocks: ["BLOCK 9"]
description: >
  One bs msgstr ends "Za kreiranje oglasa<cyrillic a> kooristi<cyrillic> /post." - a
  Croatian/Bosnian frame carrying the Russian verb and a Cyrillic character inside a Latin word. It
  is the only Cyrillic-bearing line in the bs catalogue and it renders to every Bosnian user. No gate
  catches it, and the reason is written into the gate itself: test_no_cyrillic_msgids declares msgstr
  values exempt because "msgstr values for ru/bs are naturally Cyrillic" - which is right for ru and
  wrong for bs, where Cyrillic is contamination by construction. The detection rule is engineering.
  The three corrected values are a human deliverable.
goals:
  - "a bs-scoped msgstr script rule exists and is demonstrated failing on the contaminated string"
  - "the three bs values are either corrected by a native reviewer or recorded as named, reasoned exemptions"
  - "ru's legitimate Cyrillic msgstrs stay correct and the gate stays green for them"
extra_context: |
  Q1 IS RULED but the GATE IS OPEN-PENDING-REVIEWER - 2026-10-03, Product Owner. Who signs off is
  decided: a native Bosnian reviewer, preferably Montenegrin. Machine output and translation APIs
  are NOT acceptable. NO SIGN-OFF EXISTS YET, so THIS BLOCK SHIPS ITS REDUCED DELIVERABLE NOW: the
  detection rule plus a named, commented exemption for all three strings, with the commit body
  recording the gate as OPEN-PENDING-REVIEWER rather than closed. THIS PLAN DOES NOT WRITE THEM AND
  THE IMPLEMENTOR IS FORBIDDEN FROM WRITING, GUESSING, MACHINE-TRANSLATING OR APPROXIMATING THEM.
  Phase 09's outbound Google-Translate client is explicitly NOT a catalogue tool. Project rule 1
  makes every msgid English; the replacement is a bs value only a speaker can produce.
  Q2 DOES NOT GATE THIS BLOCK. The code context claims Option A for 14-I18N-013 would remove two of
  the three strings from scope; the tree does not support it. 14-I18N-013 is about MODEL METADATA, a
  different surface from a template already in the gate's exclude_subpaths tuple. Q1 and Q2 are
  independent - and Q2 resolving while Q1 stayed open is the proof.
  BINDING CONSTRAINTS (from section 3 BLOCK 9; none corrected - all three strings unchanged at
  7f43e535)
  1. The msgid NEVER changes. These are msgstr-only corrections; changing a msgid re-extracts the
     key and orphans the entry.
  2. No machine translation, no invented bs.
  3. The new assertion is LOCALE-SCOPED. ru legitimately contains hundreds of Cyrillic msgstrs; a
     blanket "no Cyrillic in msgstr" rule would fail immediately and be disabled. The rule is:
     Cyrillic in a bs msgstr is a violation; Cyrillic in a ru msgstr is correct.
  4. The rule is about SCRIPT, not language quality. It cannot judge fluency and does not pretend to.
     A general quality gate is out of scope.
  5. The `Start` copy-through is NOT corrected here - it is one of the 14-I18N-014 orphans and BLOCK
     10 PRUNES it.
  6. The six legitimate copy-throughs are not corrected: ID, Telegram ID:, Pro, Telegram,
     Google Translate, Plausible Analytics.
  7. The two bs plural entries sharing msgstr[1] and msgstr[2] are CORRECT for bs CLDR.
  8. Any exemption is a named, commented entry with a reason and an owner - never a pytest.skip.
  9. Section 2.2 in full: re-read all three .po files immediately before any makemessages invocation
     and again immediately before git add; append never regenerate wholesale; stage by path; never
     add a .mo.
  10. If the gate would be red on arrival with no exemption recorded, THIS COMMIT MUST NOT BE MADE.
     Re-apply the previous bs content and re-plan.
  VERIFIED SYMBOL MAP (re-derived at 7f43e535; use symbols, never line numbers)
  - src/backend/apps/ads/tests/test_i18n_completeness.py -> test_no_cyrillic_msgids, whose docstring
    states msgstr values for ru/bs are naturally Cyrillic and exempt, and which iterates
    _parse_po_entries inspecting the msgid only
  - the three bs entries, addressed BY MSGID: the multi-line support-greeting msgid ending "To
    create an ad, use /post."; "Moderator #%(mid)s"; "Admin"
  - "Admin" is in scan scope - components/header.html and components/header_auth_entry.html. Two
    further occurrences live in admin/moderation/review.html, inside the excluded subtree.
  - "Moderator #%(mid)s" is in analytics/moderation_dashboard.html as a
    {% blocktrans with mid=mod.moderator_id %} body, NOT as a {% trans "..." %} literal, and that
    template IS in exclude_subpaths. A literal-substring or {% trans "-shaped source scan MISSES this
    site entirely - both sides must be parsed.
  - bs has exactly 9 copy-through entries; 6 are legitimate, 3 are real, and "Start" is a fourth and
    is an orphan pruned by BLOCK 10
  FORBIDDEN: editing a msgid; editing ru or en; filling en msgstrs; writing any bs text without the
  Q1 reviewer; correcting the shared bs plural forms; regenerating a catalogue; adding a .mo; creating
  a new test module; editing conftest.py.
files:
  - path: src/backend/apps/ads/tests/test_i18n_completeness.py
    targets:
      - type: function
        name: test_no_cyrillic_msgids
    changes: []   # ADD a sibling assertion; do not weaken the existing msgid-only rule. Also the
                  # home for the ru-exempt / bs-contaminated distinction case (D-2)
  - path: src/backend/locale/bs/LC_MESSAGES/django.po
    targets: []
    changes: []   # targeted msgstr-only edits by msgid; re-read immediately before git add
changes:
  - action: add_test
    description: >
      Add a locale-scoped assertion that a Cyrillic code point in a bs msgstr fails, while a
      Cyrillic code point in a ru msgstr is correct and stays exempt. Keep the existing msgid-only
      rule unchanged.
  - action: add_test
    description: >
      Add a case proving the rule distinguishes ru from bs, so a blanket no-Cyrillic rule cannot be
      substituted for it.
  - action: change_code
    description: >
      Record a named, commented exemption with a reason and an owner for each of the three strings
      knowingly shipped as-is. Apply the Q1 reviewer-supplied msgstr values by msgid ONLY if a
      sign-off exists at commit time; with no sign-off, the exemptions are the deliverable.
acceptance_criteria:
  - "a Cyrillic code point in a bs msgstr fails the gate, and the failure was demonstrated on the current catalogue before the fix"
  - "a Cyrillic code point in a ru msgstr passes, and that pass was demonstrated too"
  - "the existing msgid-only Cyrillic rule is byte-identical to its pre-block state"
  - "every changed value came from the Q1 reviewer, or is a named exemption with a reason and an owner - no value was invented, guessed or machine-translated"
  - "the commit body records the Q1 gate as OPEN-PENDING-REVIEWER dated 2026-10-03, NOT as closed, and names the required reviewer (native Bosnian, preferably Montenegrin)"
  - "no msgid changed, and Start was left alone for BLOCK 10 to prune"
  - "the six legitimate copy-through entries and the two shared-form plural entries are untouched"
  - "ru and en catalogues are byte-identical to their pre-block state; no .mo appears in the diff"
  - "the new cases live in test_i18n_completeness.py; no new test module and conftest.py untouched"
  - "the commit body states the Q1 outcome, and for every exempted string that the finding is NOT closed for it"
```

---

### BLOCK 10 — `--no-obsolete` and the one-shot prune

| | |
|---|---|
| **Findings owned** | `14-I18N-014` (LOW, first limb), **`N-2`** (new, LOW) |
| **Class** | **mechanical** — and **the single most dangerous operation in the phase** |
| **Depends on** | **BLOCK 7** (the plural-aware parser must exist before a catalogue is rewritten) |
| **Blocks** | BLOCK 11 |
| **Priority** | **P2** — placed after the gate work deliberately: the prune is the destructive half, the gate is the durable half |
| **Risk level** | **HIGH** — `--no-obsolete` deletes entries by design, six other phases are appending to the same three files, and **a wrong prune is indistinguishable from a concurrent-phase conflict** until somebody notices a missing string |
| **Blast radius** | `src/backend/locale/{ru,bs,en}/LC_MESSAGES/django.po` — the most contended i18n artefact in the repository |
| **Required agents** | **Auditor · Planner · Validator.** **A Validator must witness the before/after entry sets.** This is the one block where a silent deletion is the default failure mode |

**🔴 RE-SCOPED — one binding constraint in this block was already false at the source plan's anchor and
is false now.** The plan asserts twice that *"`en` has 0 obsolete entries today and must still have 0
after."* **Measured: `ru` 7 / `bs` 7 / `en` 1.** An Implementor following the original text either
reports a false pre-existing violation or skips the deletion this block exists to perform.
**`--no-obsolete` is also mis-described**: it is **preventive** — it stops `makemessages` writing new
`#~` blocks; it does **not** remove pre-existing ones. **The full corrected text is `BC-2` in §1.2 and
it replaces the original constraint verbatim.**

**The defect.** Six msgids are present as **active** entries in all three catalogues and absent from
extraction: `Start`, `Language`, `Post ad`, `Alerts` — superseded by the per-language `_COMMANDS`
literals in `lifecycle.py` — plus two reworded strings, one of which is a **wrapped multi-line
`msgid`**. `makemessages` without `--no-obsolete` marks entries `#~` rather than removing them, and no
gate compares the catalogue against the source in the **removed** direction.

**The method constraint that makes this hard.** One orphan is a **wrapped multi-line `msgid ""` plus
continuation lines** in all three files, so a line-anchored regex silently misses it. A
literal-substring scan of the source over-reports heavily — multi-line `{% blocktrans %}` bodies and
implicitly-concatenated Python literals whose rendered form differs from the source literal.
**This block must parse, not regex, and must enumerate the entry set programmatically** — which is
exactly why it depends on BLOCK 7's parser.

**File surface (semantic units)**

| File | Element | Change |
|---|---|---|
| `Makefile` | the `makemessages` target's invocation | Add `--no-obsolete` alongside the existing `--no-location`. **The `Makefile` form does not run on this Windows host — the *flag contract* is what is being cited, not a runnable command** (§0.2) |
| `.kilo/rules/commands.md` | the "Extract" section's invocation | The same flag. **Both documented surfaces change in the same commit, or they disagree** |
| `src/backend/locale/{ru,bs,en}/LC_MESSAGES/django.po` | the obsolete entries and the orphan entries | The one-shot prune. **§2.2 in full** |

**Binding constraints**

1. **Before the extraction, enumerate — with the BLOCK 7 parser — the exact set of entries that will
   disappear. Do not eyeball a `git diff`.** For each, record which class it is: (a) a reworded string
   whose replacement is already present, or (b) a genuine orphan. **A third class — a string another
   phase added in the last hour — must not appear. If it does, stop and report.**
2. **Re-read all three `.po` files immediately before the extraction and again immediately before
   `git add`** (§2.2). Six phases append to these files.
3. **`POT-Creation-Date` must stay byte-identical across the three catalogues.**
   `test_pot_creation_date_sync` asserts it, and a mismatch sends the next reader to the wrong
   conclusion about a race.
4. **🔴 CORRECTED — see `BC-2`.** The obsolete counts are **`ru` 7 / `bs` 7 / `en` 1**, *not* `6/6/0`.
   **The end state is still zero `#~` in all three — that part was right.** The flag edit and the
   prune are **two separate actions** and are reported as two. **Do not judge an entry's `msgstr` in
   the pre-prune enumeration** — the `en` obsolete entry legitimately has an empty `msgstr`, as every
   `en` entry does.
5. **The `lifecycle.py` command-menu strings are removed, not translated.** `Start`, `Language`,
   `Post ad` and `Alerts` are the residue of twelve deliberate non-gettext `BotCommand` literals.
   Deleting them is correct; translating them would be wasted work on strings that never render.
6. **The seven existing `#~` entries in `ru`/`bs` are the phase-04/06 consent-and-login strings** that
   were reworded in source. Their replacements are present; the `#~` blocks are history. Removing them
   changes nothing at runtime. **The `en` entry is a member of that same set.**
7. **Never regenerate wholesale and never add a `.mo`.** `.mo` is gitignored and is compiled at image
   build, at container start and in the CI `i18n` job.
8. **This block adds no msgid and no gate.** BLOCK 11 is the durable half. **Do not describe this
   block as closing `14-I18N-014`.**
9. **Do not edit `src/telegram_bot/lifecycle.py`.** The `BotCommand` literals are deliberate and are
   documented as such in the module. **The orphans are the residue, not the cause.**
10. **Keep `--no-location`.** Add `--no-obsolete` **alongside** it, never instead of it.

**Implementor task**

```yaml
id: task_14_b10_po_prune
title: "Add --no-obsolete to both documented extractions and run the one-shot prune (14-I18N-014, N-2)"
priority: low
depends_on: [task_14_b07_plural_parser]
source_reference: ".ai/plans/25-i18n-remediation-execution.md"
source_section: "BLOCK 10 - --no-obsolete and the one-shot prune"
source_blocks: ["BLOCK 10"]
description: >
  Six msgids are present as active entries in all three catalogues and absent from extraction, one of
  them a wrapped multi-line msgid. ru and bs additionally carry seven #~ obsolete entries each and
  en carries one, and the documented extraction omits --no-obsolete in both places it is written
  down. Runtime impact is nil; the cost is that translators spend time on strings that never render
  and a reviewer grepping a .po can be misled into believing a code path is translated. This is the
  one-shot half only - BLOCK 11 adds the durable gate.
goals:
  - "both documented extraction invocations carry --no-obsolete alongside --no-location"
  - "all three catalogues are obsolete-free and orphan-free after the prune"
  - "no string another phase added is deleted, and the entry-set change is enumerated before it is committed"
extra_context: |
  CORRECTED BINDING CONSTRAINT - BC-2 in section 1.2 replaces the source plan's text verbatim. The
  source plan asserts, twice, "en has 0 obsolete entries today and must have 0 after." THAT IS
  FALSE. Measured at 7f43e535: ru 7, bs 7, en 1. FOLLOWING THE ORIGINAL TEXT EITHER REPORTS A FALSE
  PRE-EXISTING VIOLATION OR SKIPS THE DELETION THIS BLOCK EXISTS TO PERFORM. --no-obsolete is also
  mis-described: it is PREVENTIVE - it stops makemessages writing new #~ blocks and does NOT remove
  pre-existing ones. The flag edit and the prune are TWO separate actions and are reported as two.
  The end state is still zero #~ in all three; only the starting point was wrong.
  BINDING CONSTRAINTS (from section 3 BLOCK 10; BC-2 above is the corrected one)
  1. BEFORE the extraction, enumerate with the BLOCK 7 parser the EXACT set of entries that will
     disappear. Do not eyeball a git diff. For each, record whether it is (a) a reworded string
     whose replacement is present, or (b) a genuine orphan. A THIRD class - a string another phase
     added in the last hour - must not appear. If it does, STOP AND REPORT.
  2. Re-read all three .po files immediately before the extraction and again immediately before git
     add. Phases 03, 05, 06, 07, 08 and 10 all append to these files.
  3. POT-Creation-Date must stay IDENTICAL across the three catalogues.
  4. The obsolete counts are ru 7 / bs 7 / en 1, NOT 6/6/0. The end state is zero #~ in all three.
     Do NOT judge any entry's msgstr in the pre-prune enumeration - the en obsolete entry
     legitimately has an empty msgstr, as every en entry does.
  5. The lifecycle.py command-menu strings are REMOVED, not translated. Start, Language, Post ad
     and Alerts are the residue of twelve deliberate non-gettext BotCommand literals.
  6. The seven existing #~ entries in ru/bs are the phase-04/06 consent-and-login strings that were
     reworded in source; their replacements are present. The single en entry is a member of that
     same set.
  7. Never regenerate wholesale; never add a .mo file.
  8. This block adds no msgid and no gate. BLOCK 11 is the durable half. Do NOT describe this block
     as closing 14-I18N-014.
  9. Do not edit src/telegram_bot/lifecycle.py - the BotCommand literals are deliberate and
     documented; the orphans are the residue, not the cause.
  10. --no-location STAYS. Add --no-obsolete alongside it, never instead of it.
  METHOD CONSTRAINT - one orphan is a WRAPPED MULTI-LINE msgid "" + continuation lines in all three
  files, so a line-anchored regex silently misses it, and a literal-substring scan of the source
  over-reports from multi-line blocktrans bodies and implicitly-concatenated Python literals. PARSE,
  do not regex.
  VERIFIED SYMBOL MAP (re-derived at 7f43e535; use symbols, never line numbers)
  - Makefile -> the `makemessages` target, currently
    "... makemessages -l ru -l bs -l en --no-location". THE MAKEFORM DOES NOT RUN ON THIS HOST - the
    working one-shot is in section 0.2. Cite the flag contract, not a runnable make command.
  - .kilo/rules/commands.md -> the "Extract" section, the same flags via the mko-bazuna-dev
    one-shot. BOTH surfaces change in the same commit or they disagree.
  - obsolete entries: ru 7, bs 7 (identical sets), en 1 (a member of that set, with an empty
    msgstr). The seven are the phase-04/06 consent-and-login strings.
  - the six active orphans are present 3/3: Start, Language, Post ad, Alerts, plus two reworded
    strings, one of which is the wrapped Cannot-approve msgid.
  FORBIDDEN: editing src/telegram_bot/lifecycle.py; editing the Makefile's compilemessages target;
  removing --no-location; adding a .mo; describing this block as closing the finding; regenerating
  a catalogue wholesale.
files:
  - path: Makefile
    targets: [{ type: make_target, name: makemessages }]
    semantic_anchors:
      insert_after:
        type: shell_flag
        value: --no-location
  - path: .kilo/rules/commands.md
    targets: [{ type: markdown_section, name: Extract }]
  - path: src/backend/locale/ru/LC_MESSAGES/django.po
    targets: []
    changes: []   # targeted prune only; re-read immediately before git add
  - path: src/backend/locale/bs/LC_MESSAGES/django.po
    targets: []
    changes: []   # targeted prune only; re-read immediately before git add
  - path: src/backend/locale/en/LC_MESSAGES/django.po
    targets: []
    changes: []   # targeted prune only; re-read immediately before git add
changes:
  - action: change_code
    description: >
      Add --no-obsolete to the makemessages invocation in the Makefile and in
      .kilo/rules/commands.md, in the same commit, keeping --no-location.
  - action: change_code
    description: >
      Run the one-shot prune once using the working Windows one-shot form from section 0.2, AFTER
      enumerating the disappearing entry set with the BLOCK 7 parser and recording it in the commit
      body. The prune is a separate action from the flag edit and is reported as such.
acceptance_criteria:
  - "the disappearing entry set is enumerated programmatically and recorded in the commit body, each item classified as reworded or orphan"
  - "the enumeration's starting counts match the corrected baseline - ru 7 / bs 7 / en 1 obsolete - and any other figure is STOP-AND-REPORT, not a silent adjustment"
  - "no entry's msgstr was judged during the enumeration; the en obsolete entry's empty msgstr was recorded, not treated as a violation"
  - "no string added by another phase appears in the removal set; had one appeared, the block would have stopped and reported"
  - "all three catalogues have zero #~ obsolete entries and zero orphan msgids after the prune"
  - "POT-Creation-Date is byte-identical across the three catalogues"
  - "the msgid sets of the three catalogues remain identical to each other"
  - "ru and bs still have 0 fuzzy entries, 0 empty single-form msgstrs and 0 blank plural forms"
  - "en still has its documented empty msgstrs and was not filled"
  - "--no-location is still present in both documented invocations"
  - "no .mo file appears in the diff"
  - "the commit body states that the durable gate is BLOCK 11 and that 14-I18N-014 is not closed by this commit"
```

---

### BLOCK 11 — The reverse stale-entry gate and the obsolete-symmetry assertion

| | |
|---|---|
| **Findings owned** | `14-I18N-014` (LOW, second limb), **`N-2`** (new, LOW, durable half) |
| **Class** | **mechanical** |
| **Depends on** | **BLOCK 7** (strict — needs the plural-aware parser), **BLOCK 8** (the named exemption set), **BLOCK 10** (strict — the tree must be clean before the gate arrives, or it is red on arrival) |
| **Blocks** | BLOCK 12 |
| **Priority** | **P2** |
| **Risk level** | **MEDIUM** |
| **Blast radius** | The i18n completeness gate every phase depends on |
| **Required agents** | **Auditor · Planner · Validator.** **No Researcher needed** — the parsing approach is settled by BLOCK 7 |

**This is the durable half, and the source report says so explicitly**: *"pruning once is a one-shot
cleanup; the durable fix is the gate."* Only the **"added"** direction is currently gated.
**There is no reverse assertion**, so a msgid that leaves the source stays in all three catalogues
forever.

**🔴 RE-SCOPED — the obsolete-symmetry invariant is `7/7/1`, not `6/6/0`, and its shape changed.**
**The full corrected text is `BC-3` in §1.2 and it replaces the original invariant verbatim.** The
short form: the `ru`/`bs` pair is now **itself symmetric**; the `en` entry is a **member** of that
set, **not a disjoint one**, with an **empty `msgstr`**; and the assertion's subject is that **all
three catalogues agree on the obsolete set**, whose post-prune value is **zero**. **`7/7/1` is the
measurement that justifies the block, not the invariant it asserts.**

**The two assertions are one block.** They read the same files and fail for the same root cause — a
missing reverse assertion. Splitting them yields two commits touching the same module for one idea.
**`Q8` is resolved: the obsolete-asymmetry assertion belongs to `14-I18N-014`, not to a separate
item.**

**File surface (semantic units)**

| File | Symbol | Change |
|---|---|---|
| `src/backend/apps/ads/tests/test_i18n_completeness.py` | a new stale-entry assertion | Parse the catalogue msgid set with the BLOCK 7 parser and assert every entry is present in a **real extraction** of the source. **BLOCK 8's documented exemption set is read here** — the four `lifecycle.py` command-menu strings are its first member |
| `src/backend/apps/ads/tests/test_i18n_pipeline.py` | a new obsolete-symmetry assertion | Assert **no** `#~` obsolete block exists in **any** of the three catalogues. This is the durable form of BLOCK 10's prune. It sits beside `test_pot_creation_date_sync`, the only header comparison today |
| `src/backend/apps/ads/tests/test_i18n_completeness.py` | a fixture-driven case (D-2: same module) | Feed the gate a **synthetic** orphan — **including a wrapped multi-line msgid** — and assert it fails. **A line-anchored regex misses the wrapped case; the test must prove the parse does not** |

**Binding constraints**

1. **Parse, never regex.** One orphan is a wrapped multi-line `msgid ""`; a `^msgid "…"$` regex
   silently misses it, and a literal-substring source comparison over-reports. **The gate parses the
   catalogue with BLOCK 7's parser and compares against a real extraction, not a substring search.**
2. **The exemption set is read from BLOCK 8's single definition**, with its reason attached. **No
   second, divergent list.**
3. **The obsolete assertion covers all three catalogues, not just `ru` and `bs`.** The asymmetry *is*
   the finding; an assertion checking only two locales lets `en` drift the other way.
4. **🔴 CORRECTED — `BC-3` governs the invariant.** It is **not** `6/6/0`. The assertion targets
   **agreement across all three** with a post-prune value of **zero `#~`**. It must **not** require an
   obsolete `msgstr` to be non-empty — the `en` obsolete entry has an empty `msgstr` legitimately, and
   an "obsolete entries must be translated" assertion would fail for a reason unrelated to staleness.
5. **Every new guard is demonstrated failing before the commit** — once with a synthetic orphan and
   once with a synthetic obsolete block, **and the obsolete demonstration covers all three locales**
   (`BC-3`: proving it only on `ru`/`bs` demonstrates the half that was already true).
6. **Never hard-code a msgid count, a catalogue count or a template count.**
7. **`--no-location` stays on.**
8. **This block adds no msgid and edits no catalogue.** If it needs a catalogue change to pass, BLOCK
   10 did not finish — **fix the cause, not the assertion.**
9. **Do not extend the assertion into a translation-quality gate.** A stale-entry gate is catalogue
   hygiene. Quality is BLOCK 9's script rule and `Q1`'s linguist, nothing more.

**Implementor task**

```yaml
id: task_14_b11_stale_entry_gate
title: "Add the reverse stale-entry assertion and the obsolete-symmetry assertion (14-I18N-014, N-2)"
priority: low
depends_on: [task_14_b07_plural_parser, task_14_b08_gate_collectors, task_14_b10_po_prune]
source_reference: ".ai/plans/25-i18n-remediation-execution.md"
source_section: "BLOCK 11 - The reverse stale-entry gate and the obsolete-symmetry assertion"
source_blocks: ["BLOCK 11"]
description: >
  Only the "added" direction of the catalogue is gated today: test_extraction_completeness computes
  all_msgids minus msgids, and test_template_extraction_coverage checks that template msgids exist in
  every catalogue. Nothing compares the catalogue against the source in the removed direction, so a
  msgid that leaves the source stays in all three catalogues forever. Separately, ru and bs carried
  seven #~ obsolete entries each while en carried one, and no gate checks that dimension. BLOCK 10
  resolved both once; this block makes them permanent.
goals:
  - "a msgid present in a catalogue but absent from a real extraction fails the gate"
  - "a #~ obsolete block in ANY of the three catalogues fails the gate"
  - "the wrapped multi-line msgid case is proven, not assumed"
extra_context: |
  CORRECTED INVARIANT - BC-3 in section 1.2 replaces the source plan's text verbatim. The source plan
  builds this block on obsolete 6 (ru) / 6 (bs) / 0 (en). THAT IS WRONG. Measured at 7f43e535:
  ru 7 / bs 7 / en 1, and THE SHAPE CHANGED. The ru/bs pair is now ITSELF SYMMETRIC; the en entry is
  a MEMBER of that set, not a disjoint one, and its msgstr is EMPTY as every en entry's is. So: the
  assertion's subject is that ALL THREE catalogues AGREE on the obsolete set, and the post-prune
  value is ZERO in all three. 7/7/1 is the measurement that JUSTIFIES the block, not the invariant it
  ASSERTS - do not encode it as the target.
  BINDING CONSTRAINTS (from section 3 BLOCK 11; BC-3 above is the corrected one)
  1. PARSE, NEVER REGEX. One orphan is a wrapped multi-line msgid "" + continuation lines; a
     ^msgid "..."$ regex silently misses it, and a literal-substring source comparison over-reports.
     The gate parses the catalogue with the BLOCK 7 parser and compares against a REAL EXTRACTION.
  2. The exemption set is read from BLOCK 8's single named definition, with its reason attached. No
     second, divergent list.
  3. The obsolete assertion covers ALL THREE catalogues, not just ru and bs. The asymmetry IS the
     finding; an assertion checking two locales lets en drift the other way.
  4. Do NOT assert that an obsolete entry's msgstr is non-empty. The en obsolete entry has an empty
     msgstr legitimately, and such an assertion fails for a reason unrelated to staleness. This
     assertion reads the OBSOLETE dimension only.
  5. Demonstrate every new guard failing before the commit - once with a synthetic orphan and once
     with a synthetic obsolete block IN EACH OF ru, bs AND en. Proving it only on ru/bs demonstrates
     the half that was already true.
  6. NEVER hard-code a msgid count, a catalogue count or a template count.
  7. --no-location stays on.
  8. This block adds no msgid and edits no catalogue. If it needs a catalogue change to pass, BLOCK
     10 did not finish - fix the cause, not the assertion.
  9. Do not extend the assertion into a translation-quality gate.
  10. New cases go in the existing gate modules (D-2): the stale-entry assertion and its synthetic
      orphan case in test_i18n_completeness.py; the obsolete-symmetry assertion and its
      demonstration in test_i18n_pipeline.py. NO new test module; never conftest.py.
  VERIFIED SYMBOL MAP (re-derived at 7f43e535; use symbols, never line numbers)
  - src/backend/apps/ads/tests/test_i18n_completeness.py -> test_extraction_completeness,
    test_template_extraction_coverage, the exemption set introduced by BLOCK 8
  - src/backend/apps/ads/tests/test_i18n_pipeline.py -> test_pot_creation_date_sync, which compares
    only the POT-Creation-Date header, and the natural home for the obsolete-symmetry assertion
  - src/backend/testing/i18n_helpers.py -> _parse_po_entries as changed by BLOCK 7
  - the BLOCK 8 exemption set's first member is the four lifecycle.py command-menu msgids
  - corrected pre-prune baseline: ru 7 / bs 7 / en 1 obsolete; en's entry has an empty msgstr
  FORBIDDEN: editing a .po or .mo file; regex-based msgid matching; hard-coding counts; asserting
  non-emptiness of an obsolete msgstr; adding a quality judgement to a hygiene assertion; creating a
  new test module; editing conftest.py.
files:
  - path: src/backend/apps/ads/tests/test_i18n_completeness.py
    targets: []
    changes: []   # new stale-entry assertion + synthetic-orphan cases (incl. wrapped msgid); do
                  # not weaken existing assertions
  - path: src/backend/apps/ads/tests/test_i18n_pipeline.py
    targets: []
    changes: []   # new obsolete-symmetry assertion + its per-locale demonstration
changes:
  - action: add_test
    description: >
      Add an assertion that every msgid in every catalogue is present in a real extraction of the
      source, reading BLOCK 8's named exemption set. Parse the catalogue; never regex it.
  - action: add_test
    description: >
      Add an assertion that no #~ obsolete block exists in ANY of the three catalogues - the durable
      form of BLOCK 10's one-shot prune. It reads the obsolete dimension only and does not inspect
      msgstr content.
  - action: add_test
    description: >
      Add a fixture-driven case that feeds the stale-entry gate a SYNTHETIC orphan, including a
      wrapped multi-line msgid, and asserts it fails - proving the parse catches the case a regex
      misses. Also a synthetic #~ block per locale proving the obsolete assertion fires in all three.
acceptance_criteria:
  - "a synthetic orphan msgid fails the gate, demonstrated before the commit"
  - "a synthetic WRAPPED MULTI-LINE orphan msgid also fails, and that case is explicitly covered by a test"
  - "a synthetic #~ block in EACH of ru, bs and en fails the obsolete assertion, demonstrated before the commit"
  - "no assertion requires an obsolete entry's msgstr to be non-empty"
  - "the exemption set is read from BLOCK 8's single definition, with its reason attached"
  - "no regex-based msgid matching anywhere in the new assertions"
  - "no msgid count, catalogue count or template count is hard-coded"
  - "new cases live in test_i18n_completeness.py and test_i18n_pipeline.py; no new test module and conftest.py untouched"
  - "the full i18n gate is green on arrival, including test_i18n_category_city.py"
  - "no .po or .mo file was modified by this block"
  - "the commit body states that this, with BLOCK 10, is what closes 14-I18N-014"
```

---

### BLOCK 12 — `i18n-spec.md` brought back in line

| | |
|---|---|
| **Findings owned** | `14-I18N-001`, `-002`, `-004`, `-012`, `-015` (documentation limbs), **`N-3`** (new), **`N-4`** (new), **`14-I18N-013`** — **the SOLE home of `14-I18N-013`** (Option A, ruled 2026-10-03) |
| **Class** | **mechanical** — no behaviour change at all |
| **Depends on** | **BLOCKS 1, 5, 6, 9** (the document describes the behaviour those blocks establish; writing it earlier would institutionalise a claim the code does not yet make) · **Gated on `Q11`** (§5.5) |
| **Blocks** | nothing — the former BLOCK 13 is **CANCELLED** |
| **Priority** | **P2**, and deliberately **last among the code blocks** |
| **Risk level** | **LOW** for behaviour · **MEDIUM** for contention — phase 12 holds a conditional claim on `docs/99-agent/rules.md` |
| **Blast radius** | The phase's authoritative document, plus the agent-rules file four other phases read |
| **Required agents** | **Auditor · Planner · Validator.** **The Validator's job is to check every claim against the tree, not to read for prose quality** |

**Gated on `Q11` (the three dead links). The Option A limb is UNCONDITIONAL**: `Q2` was resolved on
2026-10-03 (Option A), so the model-metadata exemption is written here as a matter of course and this
block is the **only** place `14-I18N-013` is delivered. **The Implementor may not choose a `Q11`
option** (§5.5).

**🔴 The `N-4` rot is now an order of magnitude worse than recorded.** The settings block is cited as
one contiguous span that is now **~105 lines** away from where it actually is; `Ad.get_title` and
`Ad.get_description` are cited as **one span** but are **two distinct methods**; and the accessor
citations for three other models are each off by a small margin. **This is precisely why no task in
either plan uses a line number as a target.** **Locate every cited symbol by name and cite it by name
in the correction.**

**File surface (semantic units)**

| File | Section / element | Change |
|---|---|---|
| `docs/01-spec/i18n-spec.md` | "Runtime Language Resolution (Web UI)" | The normalisation claim, the `Accept-Language` q-value rule, the priority table |
| `docs/01-spec/i18n-spec.md` | "Submenu Cache Localization" | The `<locale>` segment's contract |
| `docs/01-spec/i18n-spec.md` | the timezone / date-format section (add if absent) | `TIME_ZONE` and the four display formats; the two ISO attributes are documented as **machine-readable and locale-independent** |
| `docs/01-spec/i18n-spec.md` | the cache / `Vary` section | Point at the middleware docstring BLOCK 6 corrected. **Do not restate a contract the middleware no longer claims** |
| `docs/01-spec/i18n-spec.md` | the i18n coverage / exemptions section | **Option A only:** name **model metadata** as an explicit exemption alongside the three existing template exclusions, so the coverage claim is accurate |
| `docs/01-spec/i18n-spec.md` | the whole document | **`N-3`** dead links and **`N-4`** stale line citations |
| `docs/99-agent/rules.md` | the scan-scope bullet and the i18n DoD section | **Read before writing — phase 12 holds a conditional claim.** Records the BLOCK 8 exemption set and, under Option A, the model-metadata exemption |
| `docs/01-spec/technical-specification.md`, `docs/01-spec/spec-index.md` | — | 🚫 **UNTOUCHED.** Phase 06 holds both |

**Binding constraints**

1. **The spec describes what the code does — never what the code should do.** Every claim is checked
   against the tree at commit time, **not against the source report or the source plan**. A
   documentation edit that outruns the code is the same defect class as `14-I18N-001`.
2. **No line numbers as citations — anywhere.** Cite a file path plus a symbol, or a section heading.
   **This is a standing project rule, not only a plan rule**, and `N-4` is why.
3. **Do not "correct" the `Makefile` or `.kilo/rules/commands.md` extraction forms again** — BLOCK 10
   owns them — and **do not restate them in the spec as runnable commands on a platform where they do
   not run.**
4. **The model-metadata exemption MUST be written in this block.** `Q2` resolved Option A on
   2026-10-03: the exemption names model metadata explicitly and sits alongside the three existing
   exclusions. **Option B was declined and BLOCK 13 is CANCELLED**, so there is no Option-B limb to
   skip and **no second place `14-I18N-013` may be documented. No catalogue entry is added here** —
   Option A costs nothing at runtime, and the admin tests asserting English field text **stay
   unchanged** because no `gettext_lazy` wrapping happened.
5. **Do not touch `docs/01-spec/technical-specification.md`** (phase 06's) or
   `docs/01-spec/spec-index.md` (phase 06's sole file). If `lang_pref` needs naming in the technical
   specification, that is BLOCK 6's deferred limb.
6. **Do not restore, recreate or reconstruct the three missing research documents.** They were never
   committed; **inventing them would be fabrication.**
7. **A correction states what is true now, not what was wrong before.** A reader needs the contract,
   not the changelog.
8. **Read `docs/99-agent/rules.md` before writing to it.** Re-read and report a concurrent change
   rather than clobbering it.
9. **No code file, no `.po`, no `.mo`.**

**Implementor task**

```yaml
id: task_14_b12_i18n_spec
title: "Bring i18n-spec.md and the agent rules back in line with the code (14-I18N-001/-002/-004/-012/-015 doc limbs, N-3, N-4, 14-I18N-013 Option A)"
priority: low
depends_on: [task_14_b01_locale_resolver, task_14_b05_timezone_and_dates, task_14_b06_lang_pref_cookie, task_14_b09_bs_script_gate]
source_reference: ".ai/plans/25-i18n-remediation-execution.md"
source_section: "BLOCK 12 - i18n-spec.md brought back in line"
source_blocks: ["BLOCK 12"]
description: >
  docs/01-spec/i18n-spec.md is phase 14's authoritative document and it currently (a) states
  unconditionally that the resolved code is normalized by LanguageLocale.from_code(), which was false
  for the cookie branch; (b) is silent on Accept-Language q-values; (c) is silent on TIME_ZONE and the
  date patterns; (d) points at three documents that do not exist, five times in total, including the
  entire docs/96-researches/ directory; and (e) carries stale line citations. Under 14-I18N-013
  Option A it must also name model metadata as an explicit exemption so the coverage claim is
  accurate.
goals:
  - "every claim in the spec matches the code at commit time, verified against the tree"
  - "the three dead link targets are resolved per the Q11 answer, without inventing documents"
  - "no line number is used as a citation anywhere in the corrected sections"
extra_context: |
  GATES. Q11 (the three dead links) must be answered first: option (a) delete the references and fold
  the content into i18n-spec.md; option (b) re-point at the nearest live documents, which asserts
  those documents contain content they may not contain; option (c) a non-link pointer. See section
  5.5 for consequences and for who decides. DO NOT CHOOSE. NOTE THE RE-PRICING: docs/99-agent/ has
  grown from 5 files to 9 since the anchor, so option (b)'s "nearest live document" set is different
  from the one the options were priced against - none of the new files is a semantic match either, but
  the decider must be told the price changed.
  Q2 decided the 14-I18N-013 Option A limb and that limb is UNCONDITIONAL. Option B is DECLINED and
  BLOCK 13 IS CANCELLED; do not write an Option-B limb and do not re-open the option.
  RE-SCOPING NOTE. N-4's rot is worse than the source plan recorded. The settings block is cited as
  one span that is now ~105 lines from where it is; Ad.get_title and Ad.get_description are cited as
  ONE span but are TWO distinct methods; three other accessor citations are each off by a small
  margin. LOCATE EVERY CITED SYMBOL BY NAME. Do not carry any source-plan line anchor forward.
  BINDING CONSTRAINTS (from section 3 BLOCK 12)
  1. The spec describes what the code DOES, never what it should do. Every claim is checked against
     the tree at commit time, not against the report or the source plan. Documentation that outruns
     the code is the same defect class as 14-I18N-001.
  2. NO LINE NUMBERS as citations. Cite a file path plus a symbol, or a section heading.
  3. Do not "correct" the Makefile or .kilo/rules/commands.md extraction forms again - BLOCK 10 owns
     them - and do not restate them in the spec as runnable commands on a platform where they do not run.
  4. Under Q2 Option A, name MODEL METADATA as an explicit exemption alongside the three existing
     template exclusions. There is no Option-B limb.
  5. Do NOT touch docs/01-spec/technical-specification.md (phase 06 holds it) or
     docs/01-spec/spec-index.md (phase 06's sole file).
  6. Do NOT restore, recreate or reconstruct the three missing research documents. They were never
     committed; inventing them would be fabrication.
  7. A correction states what is TRUE NOW, not what was wrong before.
  8. Read docs/99-agent/rules.md before writing to it - phase 12 holds a CONDITIONAL claim.
  9. No code file, no .po, no .mo.
  VERIFIED DEAD TARGETS (re-verified at 7f43e535; still dead, still 5 references)
  - ../99-agent/i18n-translation-pipeline-gap-analysis.md - referenced 3x, file absent
  - ../99-agent/i18n-definition-of-done-research.md - referenced 1x, file absent
  - ../96-researches/i18n-translation-egress.md - referenced 1x, and the whole docs/96-researches
    directory does not exist
  - docs/99-agent/ has GROWN from 5 to 9 files since the anchor (new: ad-lifecycle-remediation-record,
    pii-consent-remediation-record, test-audit-block-findings and one more). None of the three
    replacements is a semantic match.
  - the surviving relative links in i18n-spec.md that ARE live must stay live: the ../02-database/
    and ../99-agent/architecture.md targets
  FORBIDDEN: editing any code file; editing a .po or .mo file; creating a missing research document;
  citing a line number; touching technical-specification.md or spec-index.md; choosing the Q11 option.
files:
  - path: docs/01-spec/i18n-spec.md
    targets:
      - type: markdown_section
        name: Runtime Language Resolution (Web UI)
      - type: markdown_section
        name: Submenu Cache Localization
  - path: docs/99-agent/rules.md
    targets: []
    changes: []   # read-before-write; phase 12 holds a conditional claim
changes:
  - action: change_doc
    description: >
      Correct the unconditional normalisation claim to describe the actual three-source priority
      chain and its normalisation guarantee, and state the Accept-Language q-value rule either way.
  - action: change_doc
    description: >
      Document TIME_ZONE and the four display formats, and state explicitly that the two
      <time datetime="...|date:'Y-m-d'"> attributes are machine-readable ISO values that are
      locale-independent by design.
  - action: change_doc
    description: >
      Resolve the three dead link targets per the Q11 answer and remove every stale line citation,
      replacing them with symbol or section references.
  - action: change_doc
    description: >
      Name model metadata as an explicit exemption in the i18n coverage section, alongside the three
      existing template exclusions. This is the sole delivery point for 14-I18N-013.
acceptance_criteria:
  - "every claim in the corrected sections was verified against the tree, not against the report or the source plan"
  - "no line number appears as a citation in any corrected section"
  - "no link in the document points at a non-existent file, and no missing research document was invented"
  - "the links that were already live are still live"
  - "the Accept-Language q-value rule and the TIME_ZONE value are stated explicitly"
  - "the two ISO datetime attributes are documented as locale-independent machine-readable values"
  - "model metadata is named as an explicit exemption; no Option-B text is present"
  - "no catalogue entry was added by this block, and the admin tests asserting English field text are unchanged"
  - "docs/01-spec/technical-specification.md and docs/01-spec/spec-index.md are untouched"
  - "docs/99-agent/rules.md was re-read before editing and no concurrent change was clobbered"
  - "the commit body records the Q11 option chosen, the reason, and that the docs/99-agent file set
     changed since the options were priced"
```

---

## 4. The cancelled block, and the serial order

### BLOCK 13 — `14-I18N-013` Option B: translate the model metadata — ❌ **CANCELLED 2026-10-03**

> ## 🚫 THIS BLOCK IS CANCELLED. IT DOES NOT RUN. THERE IS NO COMMIT, NO TASK AND NO FILE.

**No Implementor opens it. No agent is dispatched for it. `14-I18N-013` is delivered by BLOCK 12,
Option A, and only there.** The cancellation is confirmed three ways: the source plan's scope row for
`14-I18N-013` records `12` only with `13 CANCELLED`; the `Q2` row records the Product Owner's
2026-10-03 choice of Option A with Option B **declined**; and `git log` holds **zero** `14-I18N-`
commits — so no residue of a partially-run BLOCK 13 exists anywhere.

**Why it must not be revived by an Implementor.** Option A is not a deferral dressed as a
resolution: the Product Owner chose it *on the merits*, after seeing Option B's cost (≈192 entries
to wrap in `gettext_lazy`, catalogue growth by the same, and admin tests asserting English field text
that would need re-review). **The Implementor may not re-open a closed option.** If a future phase
believes Option B is warranted, that is a **new Product Owner decision**, not an implementor judgement.

### Serial execution order

One Implementor, strictly sequential. **The order is not alphabetical and not by severity** — it is
chosen so contended files are written as few times as possible and no block depends on an answer
nobody has written down.

| Seq | Block | Class | Gate before it starts | Risk | Agents |
|---|---|---|---|---|---|
| 1 | **BLOCK 1** — one locale resolver | behavioural | none | HIGH | Auditor · Researcher · Planner · Validator |
| 2 | **BLOCK 2** — type boundary, 18 signatures | structural | **`Q6`** (enumeration done; option not chosen) | HIGH | Auditor · Researcher · Planner · Validator |
| 3 | **BLOCK 3** — price formatting | behavioural | **`Q3`** | HIGH | Auditor · Researcher · Planner · Validator |
| 4 | **BLOCK 4** — price chip | mechanical | BLOCK 3 landed | MEDIUM | Auditor · Planner · Validator |
| 5 | **BLOCK 5** — `TIME_ZONE` + date patterns | mechanical | none (`Q4` resolved) | MEDIUM | Auditor · Researcher · Planner · Validator |
| 6 | **BLOCK 6** — `lang_pref` cookie | behavioural | **`Q5`** (phase-06 boundary) | HIGH | Auditor · Researcher · Planner · Validator |
| 7 | **BLOCK 7** — plural-aware parser | behavioural | none | MEDIUM | Auditor · Planner · Validator |
| 8 | **BLOCK 8** — collectors + `hreflang` | behavioural | **`Q9`** pre-block step | MEDIUM-HIGH | Auditor · Researcher · Planner · Validator |
| 9 | **BLOCK 9** — `bs` script gate | conditional | BLOCKS 7 + 8 landed; `Q1` `OPEN-PENDING-REVIEWER` | MEDIUM | Auditor · Planner · Validator |
| 10 | **BLOCK 10** — `--no-obsolete` + prune | mechanical | BLOCK 7 landed | **HIGH** | Auditor · Planner · Validator |
| 11 | **BLOCK 11** — stale-entry + symmetry gates | mechanical | BLOCKS 7, 8, 10 landed | MEDIUM | Auditor · Planner · Validator |
| 12 | **BLOCK 12** — `i18n-spec.md` | mechanical | BLOCKS 1, 5, 6, 9 landed · **`Q11`** | LOW / MEDIUM | Auditor · Planner · Validator |
| — | ~~BLOCK 13~~ | — | — | — | **CANCELLED — no agent dispatched** |

**The two ordering edges that are load-bearing, not tidy:**

- **BLOCK 7 → BLOCK 11 (strict).** The parser fix is what makes BLOCK 11's plural assertion
  meaningful. A stale-entry gate built on a parser that reads only the **last** plural form cannot see
  a blank non-final form — and `en` currently ships exactly that. **BLOCK 11 must not precede BLOCK 7.**
- **BLOCK 10 → BLOCK 11 (strict).** The tree must be obsolete-free before the assertion arrives, or
  the gate is **red on arrival**. BLOCK 10 is the destructive one-shot; BLOCK 11 is the durable half.
  Doing them in the other order ships a red gate and tempts a future implementor to "fix" it by
  deleting the assertion.

---

## 5. Gates — decision required before implementation

Five gates are genuinely open and one is open-pending-sign-off. **Every one of them is somebody
else's decision. This plan chooses none of them, and no Implementor may choose one** — an Implementor
that finds itself reaching for an option is looking at a block that must not start.

**Product/owner decisions vs technical decisions** are labelled on each gate. The distinction matters
for routing: a technical gate is closed by the **Planner** on engineering grounds, and an owner gate
needs a human with authority over what the product does.

### 5.0 RULINGS — recorded 2026-10-05 · **all blocking gates are CLOSED**

**Product Owner, 2026-10-05.** The three blocking gates and the reviewer gate are now decided.
A standing instruction was given to stop interrupting the owner: **the Planner takes the
recommended option on every remaining technical gate.** A gate may still be escalated only when the
recommended option is genuinely unsafe, not merely inconvenient.

| Gate | **RULING** | Binding consequence |
|---|---|---|
| **`Q3`** `bs` grouping | **OPTION (a) — a project-level `FORMATS` override supplying `NUMBER_GROUPING = 3` for `bs`.** Option (b)'s bespoke formatter is **DECLINED** (a second formatting path that drifts); option (c)'s documented limitation is **DECLINED** (it leaves the `ru`/`bs` inconsistency the fix exists to close) | **BLOCK 3.** One declaration; every `number_format` / `intcomma` call in the project — card, chip, detail page and the bot's alert messages — gets correct `bs` grouping without knowing about it. **Cost accepted:** touches the six-way-contended `config/settings/base.py` **and needs its own settings test in the same commit.** The grouping declaration ships in the **same commit** as the one-argument fix — an argument-only change is a half-fix |
| **`Q5`** `lang_pref` writer | **OPTION (a) — the server write is authoritative; the consent-guarded JS branch is deleted.** Option (b) is **DECLINED**; option (c) "defer" is **DECLINED** | **BLOCK 6.** The middleware's `set_cookie` becomes the single writer and states in its docstring that it sets `lang_pref`. This is the only path on which **`httponly=True` is safe**, so `14-I18N-011` closes **fully** rather than partially. **Cost accepted and acknowledged: it removes a consent gate from a cookie write — a privacy-posture statement.** Phase 06 owns consent state, so **BLOCK 6 must not start until phase 06 acknowledges this ruling.** `docs/01-spec/technical-specification.md`'s cookie list stays **DEFERRED** until phase 06 clears that file separately |
| **`Q1`** the three real `bs` strings | **OPTION (b) — no native reviewer is available; `bs` ships as-is and the finding is recorded as ACCEPTED.** | **BLOCK 9, reduced deliverable.** The **engineering half ships**: a `msgstr`-level script rule that catches Cyrillic (or any non-Latin-script) contamination inside a Latin-script `msgstr`, closing the gap `test_no_cyrillic_msgids` cannot see because it inspects `msgid` only. The **string half does not ship.** The three strings sit under a **named, commented exemption** in the gate module so the gate stays green **and the debt stays visible**. **The exemption must name this ruling and its date, and must not be a bare `# noqa`** |
| **`Q6`** accessor typing | **Recommended option stands** — propagate `LanguageLocale` at all **18** signatures across 11 files, and treat the 20+ `&lang={{ LANGUAGE_CODE }}` URL renders as a `str(LanguageLocale)` surface | **BLOCK 2.** Enumeration is already complete; only the mechanism is chosen. If the propagation turns out to be materially worse than priced at 18 sites, escalate rather than silently narrowing |
| **`Q9`** widened collector run | **Must be executed** as BLOCK 8's pre-block step. It is a measurement, not a judgement | If the widened collectors find new violations, they are **BLOCK 8's work**, not a scope expansion into BLOCK 12 |
| **`Q11`** three dead links | **Recommended option (b) stands** — re-point all three dead targets to the files that actually exist, in `BLOCK 12` | Pricing changed (`docs/99-agent/` grew 5→9), so re-verify each target before writing the link |

**Standing constraints reaffirmed:** no gate option may be chosen by an Implementor; no
`makemessages`/`compilemessages` in this programme; `bs` is a human language and its catalogue is
never machine-generated.

### 5.1 `Q3` — `bs` number grouping · ✅ **RULED 2026-10-05 — option (a), see §5.0** · **BLOCK 3**

**Why it is open.** The one-argument fix restores the decimal mark for `ru` and `bs` but **`bs`
thousands grouping is structurally unreachable**: Django's bundled `bs` locale leaves
`NUMBER_GROUPING` commented out and `django/utils/numberformat.py` gates on
`use_grouping and grouping != 0`, which hard-disables grouping **even under `force_grouping=True`**.
The premise reproduced exactly at `7f43e535`: `_format_amount` still builds `format(rounded, "f")`
and passes a `str` to `intcomma`; no project-level `FORMATS` override exists; the bundled `bs`
locale file is unchanged.

| Option | Change | Consequence if chosen |
|---|---|---|
| **(a)** | A project-level `FORMATS` override supplying `NUMBER_GROUPING = 3` for `bs`, in settings | **One declaration**; every `number_format` and `intcomma` call in the project — including the bot's alert messages — gets correct `bs` grouping without knowing about it. **Cost:** touches the six-way-contended `config/settings/base.py` and needs its own settings test, in the same commit. Re-read `base.py` immediately before editing; stop on a concurrent change |
| **(b)** | A project-owned formatting helper that bypasses `numberformat.py`'s grouping gate | Total control, no dependence on third-party locale data that could change. **Cost:** creates a **second formatting path that can drift from `number_format`**, and it must then be used by the card, the chip, the detail page *and* the bot, or the inconsistency returns. Against the project rule *avoid overengineering, follow existing patterns* — a bespoke number formatter is the opposite |
| **(c)** | Accept ungrouped `bs` prices and document the limitation | **Zero cost, honest documentation.** **Cost:** leaves the `ru`/`bs` inconsistency the fix was meant to close — `1234,56` beside `1 234,56`. **That is `14-I18N-003`'s impact, half-fixed and now described as a decision.** The commit body must say so plainly |

**Whatever is chosen, the grouping decision ships in the same change as the argument fix.** A commit
that changes only the argument is a half-fix a reviewer will sign off on. **Options (a) and (b) both
change the `bs` rendering for the whole product; (c) does not.**

### 5.2 `Q5` — server write vs consent gate for `lang_pref` · ✅ **RULED 2026-10-05 — option (a), see §5.0** · **BLOCK 6 · BLOCKED on phase-06 acknowledgement**

**Type: PRODUCT / OWNER — and specifically a phase-06 boundary. RULED 2026-10-05: option (a).** The Product Owner has decided; **phase 06 must still acknowledge before BLOCK 6 starts** (see §5.0). Phase 06 owns consent state (`ConsentRecord`, the `consent_preferences` context processor); the ruling removes a consent gate from a cookie write, and that remains phase 06's call to accept.

**Why it is open.** The contradiction reproduced exactly at `7f43e535`: the middleware's `set_cookie`
supplies no `secure`, no `samesite` and no `httponly` and writes **unconditionally** whenever `?lang=`
is present; the switcher's inline JS writes the same cookie **inside `{% if consent_preferences %}`**
with a **hard-coded `SameSite=Lax`**. **Neither site references the other, and the weaker writer lands
last.**

| Option | Change | Consequence if chosen |
|---|---|---|
| **(a)** *(the report's recommendation)* | **The server write is authoritative.** Delete the consent-guarded JS branch; state in the middleware docstring that it sets `lang_pref` | Correct and honest — the server write is the only one that runs on a plain `?lang=` link, so it already happens for everyone. It also makes **`httponly=True` safe**, which is the only way `14-I18N-011` fully closes. **Cost: it removes a consent gate from a cookie write — a privacy-posture statement that is phase 06's call** |
| **(b)** | **The consent gate is real.** Move it into `process_response` and coordinate with phase 06 | The gate becomes a real server-side condition, and it changes what the switcher does for a visitor who has not consented. **It may make `httponly=True` unnecessary** (a cookie only written after consent) — but the middleware would then need access to consent state, which is phase 06's model |
| **(c)** | **Defer.** Record the contradiction, ship only the unambiguous parts | The two writers keep disagreeing and the two `SameSite` values keep disagreeing. `14-I18N-011` can still ship `secure` and `samesite`; **`httponly` must be withheld** because a client-side writer may still need the cookie |

**Also gated on the same block, separately:** naming `lang_pref` in
`docs/01-spec/technical-specification.md`'s cookie list requires **phase 06's clearance** on that
file. **That limb is DEFERRED unless phase 06 clears it — deferred, not skipped.**

### 5.3 `Q6` — accessor typing propagation · ✅ **RULED 2026-10-05 — recommended option stands, see §5.0** · **BLOCK 2**

**The recommended option stands (§5.0): the accessors take `LanguageLocale` and the 20+ `&lang={{ LANGUAGE_CODE }}` URL renders are treated as a `str(LanguageLocale)` surface.** This plan does not choose the mechanism, and D-5 explains why the re-scope deliberately leaves that open rather than absorbing it.

**The enumeration is DONE** — the audit's round-2 sweep *is* the Q6 enumeration and is reproduced in
full in **BC-1** (§1.2): 18 signatures across 11 files; 27 filter-argument template calls and 20-plus
URL renders of `LANGUAGE_CODE` across 16 templates; **zero** Python consumers of the processor's
output; and **two** sites defaulting to `LanguageLocale.RUSSIAN.value`.

| Option | Change | Consequence if chosen |
|---|---|---|
| **(a)** | The context processor emits a `LanguageLocale`; the filters take `LanguageLocale` | **Strongest**: a bad locale becomes impossible at the boundary and `basedpyright` flags every call site. Aligns with project rules 9 and 10. **Cost — and it grew since the options were priced:** the 20-plus `&lang={{ LANGUAGE_CODE }}` URL renders put the enum through `str()`, and the 27 filter-arg call sites all become type-dependent on the context value. **The strongest argument for (a) also strengthened:** all eighteen defaults are already effectively `LanguageLocale`, so the annotation describes existing runtime behaviour |
| **(b)** | The accessors accept `str \| LanguageLocale` and normalise internally | **Narrowest surface**, no template churn, no `context_processors` edit. **Cost:** re-implements normalisation at a second site — **exactly the `14-I18N-001` root cause in miniature** — and keeps the "any `str` may reach the catalogue" shape alive. **And it is narrower only on paper: it cannot be applied to the two `str`-defaulting sites without deciding what they default to** |

**Neither option is chosen here.** The chosen option and its reason go in the commit body.

### 5.4 `Q9` — does the widened bot collector pass? · ✅ **RULED 2026-10-05 — the run must happen, see §5.0** · **BLOCK 8 pre-block step**

**Type: MEASUREMENT FIRST, then a TECHNICAL decision.** **Who runs the step: the Auditor.** **Who
decides the consequence: the Planner.**

**The premise holds; the run has not been performed.** At `7f43e535`, `lifecycle.py`'s `_COMMANDS`
still holds **twelve** non-gettext `BotCommand` literals, with a module comment explaining they are
deliberately not msgids because an eager `_()` would freeze the string at import time. **Four of their
strings are the `14-I18N-014` orphans.** 🟡 **There is no committed harness for the widened run** — the
probe in `.ai/tmp/` is untracked scratch and was never executed — so **the widened collector is built
as part of BLOCK 8 rather than relied on from `.ai/tmp/`.**

**The step:** run each widened collector against the current tree and report **exactly which files
fail and why**. Do not assume the outcome; the near-certain failure is the bot collector.

| Once the step reports, | Consequence |
|---|---|
| The bot collector fails on the command-menu literals **only** | Record them as the **first named exemption** in BLOCK 8's single exemption set, with the reason recorded next to it. **BLOCK 8 and BLOCK 9 proceed** |
| The bot collector fails on **anything beyond** the command-menu literals | **Stop and report before writing the exemption.** New scope is a decision, not a discovery — that is how a plan like this one grows a fourteenth block nobody chartered |
| The template collector discovers **no root at all** | That is a defect in the collector, not a pass. BLOCK 8 adds the positive "at least one root discovered" assertion so this case fails loudly |
| The gate would be **red with no exemption recorded** | 🚫 **The commit must not be made.** Re-plan. **The gate is never committed red** |

### 5.5 `Q11` — may BLOCK 12 re-point the three dead links? · ✅ **RULED 2026-10-05 — option (b), see §5.0** · **BLOCK 12**

**Type: mix — predominantly TECHNICAL, and the recommendation is the Planner's.** **Who decides: the
Planner.** No option may be chosen by the Implementor.

**The premise reproduced exactly at `7f43e535`:** all three targets are still dead, still referenced
**5×**, and the whole `docs/96-researches/` directory does not exist.

🟡 **The price of option (b) has changed and the decider must be told so.** `docs/99-agent/` has grown
from **5 files to 9** since the anchor. The *option set* is unchanged, but option (b)'s "nearest live
document" set is different from the one the options were priced against. **None of the new files is a
semantic match** — so option (b) did not get safer, it got differently wrong.

| Option | Change | Consequence if chosen |
|---|---|---|
| **(a)** *(the Planner's recommendation)* | **Delete the three references** and fold their content into `i18n-spec.md` | **The honest, cheapest option.** The sources were research notes that were never committed; a link to a document that never existed is a broken promise, and folding the content in is the only way to keep the information. **Cost:** the document grows |
| **(b)** | **Re-point them at the nearest live documents** — `docs/99-agent/architecture.md`, `docs/01-spec/technical-specification.md` | **Cheapest diff, highest dishonesty.** It **asserts those documents contain content they may not contain**, and it now points at a different, larger file set than when the option was written. A reader who follows the link and finds nothing has been misled by a document that was supposed to be authoritative |
| **(c)** | **Replace the link text with a "see the repository" pointer and no link** | Honest and minimal. **Cost:** loses the pointer's usefulness — a reader is told the material exists somewhere without being told where |

**BLOCK 12's Option A limb for `14-I18N-013` is UNCONDITIONAL and separate from this gate.** `Q2` is
closed; the model-metadata exemption is written regardless of how `Q11` is answered.

### 5.6 `Q1` — who signs off the three real `bs` strings? · ✅ **RULED 2026-10-05 — option (b): no reviewer, finding ACCEPTED, see §5.0** · **BLOCK 9**

**RULED 2026-10-05 (§5.0): no native reviewer is available. The finding is ACCEPTED, the detection rule ships, and the three strings ship as-is under a named exemption.**

**The underlying translation debt is `ACCEPTED`, not settled — and the 2026-10-03 ruling that made it
`OPEN-PENDING-REVIEWER` is unchanged.** That ruling answered **who**: a native reviewer signs off;
**machine output and translation APIs are NOT acceptable**. It did **not** produce a sign-off, and
the 2026-10-05 ruling does not pretend otherwise — it decides only that the programme proceeds
without one. **The gate's history stays `OPEN-PENDING-REVIEWER`; re-opening requires only the
reviewer's sign-off — no re-decision.**

**This plan writes none of the three strings, and the Implementor is forbidden from writing, guessing,
machine-translating or "approximating" any of them.** Phase 09's outbound Google-Translate client is
explicitly **not** a catalogue tool, and project rule 1 makes every `msgid` English — the replacement
is a `bs` value only a speaker can produce. **"There is no reviewer yet" is the *only* reason the
strings ship as-is; it is not a licence to produce them another way.**

| State | Consequence |
|---|---|
| 🚧 **Current — no sign-off** | **BLOCK 9 ships its reduced deliverable:** the detection rule plus a named, commented exemption for all three, with the commit body recording `OPEN-PENDING-REVIEWER`. **When the sign-off arrives, a follow-up commit supplies the three values and removes the exemptions; the gate closes then** |
| A linguist supplies all three | The detection rule **and** the three corrected `msgstr` values, in one commit, with the failure demonstrated in the same session |
| A linguist supplies some | The rule, the corrected ones, and a **named, commented exemption** for each string knowingly shipped as-is — with the commit body stating the finding is **not closed** for those |
| 🚫 Gate red on arrival with no exemption recorded | **The commit must not be made.** Re-apply the previous `bs` content and re-plan |

**`Q2` does not gate this block, and its answer does not change that.** `14-I18N-013` is about **model
metadata** — a different surface from a template that is **already** in the gate's `exclude_subpaths`
tuple. **`Q1` and `Q2` are independent**, and the fact that `Q2` resolved while `Q1` stayed open is
the proof.

### 5.7 Closed and unchanged — recorded so nobody re-opens them

| Gate | Status | Consequence |
|---|---|---|
| **`Q2`** — `14-I18N-013` option | ✅ **RESOLVED 2026-10-03 (Product Owner): Option A.** Option B **declined** | BLOCK 12 delivers the documentation change and is the **sole home** of `14-I18N-013`. **BLOCK 13 is CANCELLED.** No catalogue growth. The admin tests asserting English field text **stay unchanged**. **The Implementor may not re-open the option** |
| **`Q4`** — `TIME_ZONE` | ✅ **RESOLVED 2026-10-03 (Product Owner):** `TIME_ZONE = "Europe/Podgorica"`, **hard-coded and NOT env-overridable** | **No `ALLOWED_ENV_VARS` entry and no `.env*.example` lines** — the allowlist collision disappears entirely and **no other phase's allowlist work is triggered**. `Europe/Belgrade` and `Europe/Sarajevo` are **declined**. **BLOCK 5 starts unblocked** |
| **`Q8`** — obsolete asymmetry as its own gate? | ✅ **RESOLVED (Planner): part of `14-I18N-014`** | One assertion, in BLOCK 11, alongside the reverse stale-entry gate — they read the same files and fail for the same root cause. Not a separate `VAL`-level item |
| `Q1` / `Q2` independence | ✅ confirmed | The code context's claim that `Q2`'s Option A removes two of the three `bs` strings from scope is **not supported by the tree**. Neither gate releases the other |
| `C-1` (`VAL-001`), `C-2` (template count), `C-3` (model-metadata scale), `C-5`/`C-6` (the `bs` copy-through split) | ✅ corrections carried forward | `VAL-001` is **not actioned** — no block touches it. The template count is **never hard-coded**. The model-metadata scale is `20 verbose_name` + `172 help_text`. The `bs` copy-through split is **9 total = 6 legitimate + 3 real**, with `Start` a fourth, pruned by BLOCK 10 |

---

## 6. Required tests, per block

### 6.1 Standing rules — these bind every block

1. **Assert on accessors and rendered values, never on private internals.** A test that reads
   `_parse_po_entries`'s accumulator, the middleware's local variable, or any module-level private
   state will break on the next refactor without the behaviour changing. Assert on what a user gets
   or what a public accessor returns.
2. **🚫 NEVER assert on gettext chrome text for an unsupported locale.** This is `VAL-003`, and it is
   the **one rule in this plan that produces false greens rather than false reds.** Production
   `LANGUAGE_CODE` is `"ru"`; test `LANGUAGE_CODE` is `"en"`; Django's `_add_fallback` makes the
   chrome for an unsupported locale Russian in production and English under test, while the DB
   accessors behave identically in both. **Such an assertion passes in CI and production is still
   wrong.** Where chrome genuinely must be asserted, **pin `LANGUAGE_CODE` with `override_settings`
   first**, so the test and production share a premise.
3. **Multi-language tests iterate `LanguageLocale.values()`**, never bare `"ru"` / `"bs"` / `"en"`
   literals. A bare literal silently stops covering a locale the day a fourth is added — which is
   exactly how `en`'s plural defect survived.
4. **Never hard-code a file count, a template count, a msgid count or a catalogue count.** Every guard
   derives its expectation from the collector, the parser or the filesystem. The numbers in §2.1 are a
   **measurement**, not an assertion input — and three of the source plan's were wrong.
5. **New tests go in the existing per-finding module. `src/backend/conftest.py` is never edited.** Per
   D-2, all four proposed new test modules are folded in — the parser case into
   `test_i18n_pipeline.py`; the collector, script-rule and synthetic-orphan cases into
   `test_i18n_completeness.py`. **No new test module is created in this phase.**
6. **Every new guard must be demonstrated failing before the commit.** A guard that has never been
   seen red is an unverified claim that the guard was necessary. Where a guard's *purpose* is to fire
   on a condition that does not exist in the current tree, the demonstration uses a **synthetic**
   fixture — never a mutation of a real catalogue.
7. **Production code is king.** If a test conflicts with the architecture or the business logic, fix
   or remove the test — never bend the production code to satisfy it. BLOCK 3's existing price test is
   the named case.
8. **Docker-only.** `.\Makefile.ps1 test`. `PYTEST_OPTS` is unquoted in the entrypoint: **bare paths and
   single-token flags only**, and setting it replaces the defaults.

### 6.2 Per-block test requirements

| Block | Module(s) | What is asserted | Demonstrated failing | Must **not** assert |
|---|---|---|---|---|
| **1** | `apps/core/tests/test_language_middleware.py` | For every cookie value in the priority table — including `en-US`, `EN`, `en_US`, `de-DE`, `ru-RU` and a nonsense tag — **`request.LANGUAGE_CODE` is a member of `settings.LANGUAGES`**, **and** `Category.get_name` / `City.get_name` / `Ad.get_title` return that locale's value rather than the `ru` fallback. `Accept-Language: de-DE,ru;q=0.8,bs;q=0.6` resolves to `ru`, not `bs`. A `q=0` member is never selected. The submenu cache key's locale segment is one of `ru`/`bs`/`en` | The non-canonical cookie cases are new, so each fails against the pre-fix resolver | 🚫 **Chrome text for an unsupported cookie locale** — the false-green trap |
| **2** | `apps/ads/tests/test_i18n_category_city.py` (existing) | Each accessor returns the requested locale's value for **every `LanguageLocale.values()` member**, and a value the enum cannot represent **degrades to the `ru` rung without raising** | The unmapped-locale degradation case is asserted as a **fallback**, not an exception — the assertion fails if a type tightening makes it raise | 🚫 Rendered chrome. 🚫 A bare locale string as the parametrising value |
| **3** | `apps/ads/tests/test_price_format.py` | **Exact per-locale output** for a fractional amount, a round integer amount, and a **≥7-digit** amount, under every `LanguageLocale.values()` member, asserting the **real separator code points** (read from `django.conf.locale`, not hard-coded strings) | The fractional case is the defect and fails pre-fix | 🚫 "A separator is present". 🚫 A 5-digit-only case — it cannot prove grouping works |
| **4** | `apps/ads/tests/test_price_format.py` (same module) | The chip's rendered output carries the **same separator and grouping as the card price in the same response**, for every `LanguageLocale.values()` member; the listings and search routes render **byte-identical** chips for the same bounds; a `None` bound renders **exactly as it does today** | The separator assertion fails pre-fix against the `blocktrans` interpolation | 🚫 "A separator is present". 🚫 A changed unbounded rendering silently accepted |
| **5** | `config/settings/tests/test_settings_defaults.py` | `settings.TIME_ZONE == "Europe/Podgorica"`; **one known UTC instant renders to the expected local wall time** under every `LanguageLocale.values()` member; the two `<time datetime>` ISO attributes are **byte-identical** to their pre-block values | The instant-rendering assertion fails pre-fix under the `America/Chicago` default | 🚫 A per-locale pattern string as an expected value — read the locale format, assert the rendering |
| **6** | `apps/core/tests/test_language_middleware.py` | The emitted `lang_pref` cookie carries `secure` and `samesite` **read from settings**; `httponly` is `True` under `Q5` (a), or **absent with a comment** under (b)/(c); the `Vary` header is **byte-identical** to its pre-block state; **under (a)**, `?lang=bs` sets the cookie **with no consent context present** | The attribute assertions fail pre-fix — the cookie carries none of the three | 🚫 Asserting on a `Vary` header the block did not add. 🚫 Assuming `secure=True` regardless of settings |
| **7** | `apps/ads/tests/test_i18n_pipeline.py` + `…/test_i18n_completeness.py` | A **synthetic** plural entry with a blank `msgstr[0]` is reported as a violation by **both** `test_no_empty_msgstr` copies; the `en` skip is byte-identical; the plural form counts for `ru`/`bs` (3) and `en` (2) are unchanged | 🚫 **Mandatory** — the blank-`msgstr[0]` case must be observed red pre-fix and green post-fix | 🚫 A catalogue-derived fixture — the catalogues' plural entries are **correct**. 🚫 Asserting `en`'s blank plural entries as a violation |
| **8** | `apps/ads/tests/test_i18n_completeness.py` | The widened bot collector reaches previously invisible modules (the middleware package, `retry.py`, `states.py`, the nine-module `handlers/ad_create` package); the template collector discovers app-level roots **and fails when it discovers none**; the `hreflang` assertion covers every page template, excludes `components/locale_head.html` itself, and does **not** fire on the two templates that are both excluded and inclusive | **Every** new assertion demonstrated failing — a widened collector never seen red is an unverified claim | 🚫 A hard-coded template count. 🚫 An assertion that fires on the two reconciled templates |
| **9** | `apps/ads/tests/test_i18n_completeness.py` | A Cyrillic code point in a **`bs`** `msgstr` **fails**; a Cyrillic code point in a **`ru`** `msgstr` **passes**. Both directions demonstrated. The existing `msgid`-only rule is byte-identical | The `bs` failure must be observed on the **current catalogue** before the exemption is recorded — that is the proof the rule has teeth | 🚫 A blanket "no Cyrillic in any `msgstr`" rule — it would fail on `ru` and be disabled within a day. 🚫 Any assertion that a `bs` string's *language quality* is wrong |
| **10** | No new guard in this block; the **commit body carries the evidence** | The disappearing entry set is enumerated **programmatically** with the BLOCK 7 parser, each item classified as reworded or orphan, and the starting counts match the corrected `7 / 7 / 1` baseline | The enumeration is a **pre-flight** demonstration in its own right — a different count means **stop and report**, not adjust | 🚫 Judging any entry's `msgstr` — the `en` obsolete entry legitimately has an empty one. 🚫 Accepting a removal-set mismatch silently |
| **11** | `apps/ads/tests/test_i18n_completeness.py` + `…/test_i18n_pipeline.py` | A **synthetic orphan** `msgid` fails the stale-entry gate; a **synthetic wrapped multi-line** orphan **also** fails and is explicitly covered; a **synthetic `#~` block fails in each of `ru`, `bs` and `en`** | **All of them, before the commit.** The wrapped case is the one a regex misses, so proving it is the whole point. The per-locale obsolete demonstration is mandatory — proving it only on `ru`/`bs` demonstrates the half that was already true | 🚫 A regex-based `msgid` match. 🚫 An assertion that an obsolete entry's `msgstr` is non-empty |
| **12** | No automated test; **the Validator checks every claim against the tree** | Every corrected claim is verified against the tree at commit time; no link points at a non-existent file; no line number appears as a citation; the links that were live are still live | N/A — this is documentation. **The Validator's tree-check is the verification** | 🚫 Asserting the catalogue numbers in §2.1 into prose — they are a measurement, and three source-plan equivalents were wrong |

### 6.3 Gate that must pass on every block, before the commit

```
.\Makefile.ps1 test          # fast gate: skips the nightly seed suite
```

Plus, for the blocks that touch the catalogue or the shared gate, the i18n modules specifically —
`test_i18n_completeness.py`, `test_i18n_pipeline.py`, and `test_i18n_category_city.py`. **The
DB-backed module must be included in the pre-block baseline run for BLOCK 1**: those five tests were
never run during the audit and they are the only DB-backed i18n evidence in the phase.

---

## 7. Risks and rollback

### 7.1 Sequenced risk list — highest first, with the block that owns each

| # | Risk | Why it is ranked here | Owned by | Mitigation | Rollback |
|---|---|---|---|---|---|
| 1 | **The `VAL-003` false green ships BLOCK 1 wrong.** A chrome assertion for an unsupported cookie locale passes in CI while production renders a Russian page | It is the phase's headline fix and nothing else in the repository would catch it | BLOCK 1 | Assert on the accessors, or pin `LANGUAGE_CODE` with `override_settings`. Record the strategy in the commit body | `git revert` the block commit. **Reverting restores a known-wrong state, so it is a stopgap, not a landing** — record the revert and re-plan |
| 2 | **The wrong prune deletes a string.** `--no-obsolete` deletes by design; six phases append to the same three files; a wrong deletion is **indistinguishable from a concurrent-phase conflict** until somebody notices a missing string | Highest-consequence and lowest-signal failure in the phase | BLOCK 10 | Enumerate the disappearing set **programmatically** before the run; classify each entry; **stop and report** on a third class. A Validator witnesses the before/after sets | Re-apply the pre-block `.po` content from the working tree and re-run the enumeration. **Do not attempt a manual reconstruction** |
| 3 | **`Q5` removes a consent gate from a cookie write** — a privacy-posture change belonging to another phase | It crosses a phase boundary and `httponly` is a one-way door in practice | BLOCK 6 | The gate is not closed, and phase 06 must acknowledge. Under (b)/(c) `httponly` is withheld with a comment saying why | Revert the commit. The two writers disagreeing again is the pre-block state — acceptable, because that is where it started |
| 4 | **`Q3` ships a half-fix that reads as complete.** The argument fix alone leaves `bs` grouping structurally impossible, so a reviewer signs off on a fix that fixed half the finding | The obvious fix is demonstrably incomplete and looks finished | BLOCK 3 | The grouping decision ships **in the same change** as the argument fix. Under option (c) the commit body states the finding is only half closed | `git revert`. Prices revert to the pre-block rendering, which is wrong in the same way they were |
| 5 | **BLOCK 2's boundary ends up stricter in templates and looser in services.** Tightening ten of eighteen leaves the two `str`-defaulting sites untouched | It is the phase's only `structural` item and the surface was under-counted | BLOCK 2 | **BC-1** names all eighteen and the two `str`-defaulting sites. The commit body must either cover them or report the omission | Revert. The typing is opt-in per signature, so a partial revert is safe |
| 6 | **A widened collector turns the green gate red on arrival.** A scanner that was never run may surface findings no phase chartered | The widened run is a **prediction that has never been executed** | BLOCK 8 | **`Q9` is a pre-block step**, not an assumption. Build the collector in the block; **if failures appear beyond the command-menu literals, stop and report** | Revert the block commit and re-plan against the reported failures. **Do not suppress a finding** |
| 7 | **BLOCK 7's parser fix is landed without BLOCK 11's gate**, leaving the plural blind spot still ungated | The ordering edge is easy to miss because BLOCK 7 closes on its own | BLOCK 7 → 11 | **The strict edge is stated in both blocks and in §4.** BLOCK 11 is not started without BLOCK 7 | n/a — the ordering is a plan constraint, not a runtime state |
| 8 | **Concurrent-agent drift on a contended file.** `config/settings/base.py` is six-way contended; `language.py`, the three `.po` files and the 1099-line gate module are all contested | This repository shows concurrent drift is routine | ALL | Re-read immediately before editing every contended file. **Stop and report a concurrent change** rather than clobbering | Nothing to roll back — the stop *is* the mitigation |
| 9 | **`.po` race.** Six phases append; a stale read silently reverts another phase's msgid | `.po` is the most contested artefact in the repository | BLOCKS 4 (conditional), 9, 10 | §2.2 in full: re-read **twice** — before extraction and before `git add`. Stage **by path**, never by directory | Re-read the file, re-apply the other phase's entry, re-run |
| 10 | **A `.mo` file lands in a commit.** It is gitignored, so it is invisible in most diffs until it is not | It would be compiled into an image from a working tree rather than from source | BLOCKS 9, 10 | §2.2 rule 3 — **never `git add` a `.mo`.** Verify the diff before committing | Un-stage the `.mo`; it never belonged in the tree |
| 11 | **BLOCK 5's `base.py` edit collides with a phase-02 allowlist change.** The risk the `Q4` ruling eliminated — but only for `ALLOWED_ENV_VARS`; the file itself is still contended | The ruling closed the allowlist branch, not the file contention | BLOCK 5 | `Q4` closed the allowlist work, so the edit is **one additive literal line**. Re-read `base.py` immediately before editing; stage by path | Unstage the file; re-read and re-apply as a one-line change |
| 12 | **BLOCK 12 institutionalises a claim the code does not make.** The document would then describe the source plan rather than the tree | This block runs **last** precisely so the code exists first | BLOCK 12 | Depends on BLOCKS 1, 5, 6, 9. **The Validator's job is to check every claim against the tree, not to read for prose quality** | `git revert` — documentation has no runtime blast radius |
| 13 | **A machine invents a `bs` translation.** The single worst outcome in this phase is a plausible-looking wrong string nobody can later spot | This is the one place where an Implementor is tempted to "just finish it" | BLOCK 9 | **No machine translation, no invented `bs`, no approximation.** The `Q1` reviewer supplies them or the strings are exempted. Phase 09's client is explicitly not a catalogue tool | `git revert` the `bs` edit and restore the previous content |
| 14 | **A `Q11` link is re-pointed at a document that does not contain the promised content.** The spec then points at live files that say nothing about the subject | Option (b) asserts content it cannot verify, and its price changed when `docs/99-agent/` grew 5 → 9 | BLOCK 12 | `Q11` is gated. **The decider is told the price changed.** No missing research document may be invented | `git revert` |
| 15 | **BLOCK 10's stale `en`-has-0 constraint is followed literally** — a false pre-existing violation is reported, or the deletion is skipped | The constraint is **already false at block entry** | BLOCK 10 | **`BC-2` replaces it verbatim**, in §1.2, in the block's constraints and in its task YAML | n/a — the correction ships with the plan |

### 7.2 Per-block rollback, compact

| Block | Blast radius if it must be reverted | Reverting is safe? | Note |
|---|---|---|---|
| **1** | Locale resolution site-wide; every DB-backed string | **Yes, mechanically** — but it restores a known-wrong state | Record the revert; do not leave it as the landed state |
| **2** | 18 signatures; type-checker surface | **Yes** — the typing is opt-in per signature, so a partial revert is coherent | Re-verify `basedpyright` after the revert |
| **3** | Every rendered price in `ru` and `bs` | **Yes** | Prices revert to the pre-block rendering, wrong in the same way |
| **4** | One template block, two routes | **Yes** | If a `.po` was written, the revert takes the `.po` edit with it |
| **5** | Every rendered timestamp | **Yes** | One settings line and four format-name swaps |
| **6** | The `lang_pref` cookie and the switcher | **Yes**, with one caveat | **Under option (a), reverting restores a consent-guarded client writer that no longer exists post-revert — check the pair together, not separately** |
| **7** | A shared parser plus two call sites | **Yes** — but revert the three files **together** | A half-reverted return type is a type error |
| **8** | The whole i18n gate | **Yes** | If the gate was red on arrival, the block should never have been committed |
| **9** | One `.po` plus one gate | **Yes** | Restore the previous `bs` content verbatim; **never hand-rewrite a `bs` string** |
| **10** | All three catalogues | ⚠️ **The hardest rollback in the phase** | Re-apply the pre-block content from the working tree and **re-run the enumeration**. A partial restore reintroduces the very asymmetry the block removed |
| **11** | The i18n gate | **Yes** | If its own gate is red, BLOCK 10 did not finish — fix the cause, not the assertion |
| **12** | Documentation only | **Yes** | No runtime blast radius |

---

## 8. Out of scope

Every item below was considered and refused. **Each has a named destination** — a block that owns it,
a phase that holds it, or a stated rationale. **Nothing here is deferred indefinitely without an
owner.**

| Refused item | Why | Named destination / rationale |
|---|---|---|
| **BLOCK 13 — `14-I18N-013` Option B** (`gettext_lazy` wrapping of ≈192 model-metadata entries) | **CANCELLED 2026-10-03.** Option B was **declined** on the merits by the Product Owner: it grows the catalogue by ≈192 entries and forces re-review of admin tests asserting English field text | **BLOCK 12, Option A** — model metadata is documented as a named exemption. `Q2` is closed and **the Implementor may not re-open it** |
| **Filling the `en` catalogue's empty `msgstr`s** (445 singular entries) | `msgid` **is** the English source string; an empty `en` `msgstr` is the documented convention, not a defect. Filling it is a 445-entry diff that changes nothing at runtime | **`Q7`, closed.** No block reads or writes `en` `msgstr`s. BLOCKS 9, 10 and 11 leave `en` alone except for the obsolete prune |
| **`14-I18N-001` — `VAL-001` (`RUN_TRANSLATION_BACKFILL` / `CFG-008`)** | **Stale / already fixed.** The setting is in `ALLOWED_ENV_VARS` and a reverse allowlist test exists | **No block touches it.** The report's *narrative* correction remains a documentation note; the actionable instruction does not apply |
| **The `&lang={{ LANGUAGE_CODE }}` URL renders (20+) and the 27 filter-argument call sites** | Under `Q6` option (a) these become type-dependent. They are **re-read**, not edited, unless the chosen option makes an edit necessary — and then it is **reported as new surface**, not absorbed silently | **`Q6`** — the decider's option determines this. BLOCK 2's constraint 6 forbids a template workaround for the typing |
| **`src/telegram_bot/middlewares/language.py` — the bot's per-user locale** | A **third distinct locale authority** (`User.telegram_language`). Conflating it with the web locale is the most common way to write a wrong fix in this finding | **`User.telegram_language`** belongs to the bot. BLOCK 2 constraint 8 forbids touching it |
| **`SavedSearch.language`** — which FTS vector a saved search matches | A **third authority** that does **not** affect message text. Neither BLOCK 1 nor BLOCK 2 alters it, and neither may | Stays where it is. Named in §2.3 so it is not mistaken for one of the two fixes |
| **Adding a `Vary: Cookie` header** | `14-I18N-012` was reclassified to `DOC-UPDATE` **because the code is already correct**: `CsrfViewMiddleware` adds `Vary: Cookie` on every full page. The original probe drove the middleware in isolation through `RequestFactory` and **measured the wrong stack** | **BLOCK 6** corrects the **docstring**. Adding a header is the specific wrong fix this finding warns about, and it is forbidden everywhere |
| **Adding `{% csrf_token %}` to the two HTMX fragments** | It would make the incidental-`Vary` property deliberate — but by **changing fragment cache semantics for a reason outside this finding** | **BLOCK 6** documents the fragility. The finding exists to be recorded, not silently fixed |
| **Adding `LocaleMiddleware`, a `set_language` view, or `i18n_patterns`** | `LocaleMiddleware` would re-derive the language from the never-set `django_language` cookie plus `Accept-Language`, clobbering the resolved value and ignoring both `?lang=` and `lang_pref` | Stays absent, by the module docstring's own reasoning. Forbidden everywhere |
| **Editing Django's bundled `bs` locale data** (`django/conf/locale/bs/formats.py`) | It is a **third-party package in `.venv`**. An edit there is not a repository change and vanishes on the next image build | **`Q3` option (a)** puts the `NUMBER_GROUPING` override in **project settings**, which is versioned and reviewable |
| **A bespoke number formatter** | Creates a **second formatting path that can drift from `number_format`**, against the project rule *avoid overengineering, follow existing patterns* | **`Q3` option (b)** exists only if the decider accepts that cost in writing. BLOCK 3 constraint 8 forbids a second entry point regardless |
| **Changing the price round-trip** — `Decimal("0.01")` / `ROUND_HALF_UP` quantisation and the trailing-zero trim | It is the **storage contract**, not part of `14-I18N-003` | BLOCK 3 constraint 6 forbids it. Out of the finding's scope entirely |
| **Editing the two `<time datetime="…">` ISO attributes** | They are **correct ISO 8601 machine-readable values**, the contract a screen reader, a crawler or a future JS enhancement reads | **BLOCK 5 constraint 8** forbids it. They are documented as locale-independent by design, not converted |
| **The six legitimate `bs` copy-throughs** — `ID`, `Telegram ID:`, `Pro`, `Telegram`, `Google Translate`, `Plausible Analytics` | Brand and product names that are **correctly identical** in Bosnian. "Correcting" them would be damage | BLOCK 9 constraint 6 forbids it |
| **The two `bs` plural entries sharing `msgstr[1]` / `msgstr[2]`** | **Correct** for `bs` CLDR. A uniformity edit would be a regression | BLOCK 7 constraint 3 and BLOCK 9 constraint 7 forbid it |
| **The `Start` copy-through correction** | It is one of the `14-I18N-014` orphans — **BLOCK 10 prunes it.** Fixing a string that is about to be deleted is wasted work | **BLOCK 10**, the prune |
| **A general translation-quality gate** | It would be a **machine-translation judgement** dressed as an engineering rule. It cannot tell a fluent wrong-language translation from a right one, and it does not pretend to | BLOCK 9's rule is about **script**, not quality. `Q1`'s linguist owns quality. BLOCK 11 constraint 9 forbids extending a hygiene assertion into quality |
| **A machine translation of the three `bs` strings** | **Explicitly not acceptable** per the 2026-10-03 ruling, and impossible under project rule 1 | **`Q1`'s named native reviewer.** The Implementor is forbidden from writing, guessing or approximating them |
| **Restoring, recreating or reconstructing the three missing research documents** | They **were never committed**. Inventing them would be fabrication — a fabricated source document is worse than a dead link | **`Q11`** resolves the links. Constraint 6 of BLOCK 12 forbids reconstruction |
| **`docs/01-spec/technical-specification.md`** | **Phase 06's file.** Naming `lang_pref` in its cookie list is a phase-06 clearance | **BLOCK 6's deferred limb**, routed to phase 06. BLOCK 12 constraint 5 forbids touching it |
| **`docs/01-spec/spec-index.md`** | **Phase 06's sole file** | Untouched. BLOCK 12 constraint 5 |
| **`src/backend/conftest.py`** | Shared fixture infrastructure. The fixtures there (`seller`, `user`, `category`, `city`, `create_test_ad`) are the source of truth for every other test, and `src/telegram_bot/tests/conftest.py` independently redefines the async versions — editing either collides with a surface this plan does not own | **New tests go in the existing per-finding modules** (§6.1 rule 5). Forbidden everywhere |
| **`\src/templates` / app-level template directories** | `src/templates` is empty and no `apps/*/templates` directory exists, so the `APP_DIRS` gap is **latent** | **BLOCK 8** widens the collector so the gap is covered *the moment* a directory appears, and adds the positive "at least one root discovered" assertion so the collector cannot silently reduce to nothing |
| **Hard-coding the `ru`/`bs`/`en` catalogue counts anywhere** | Three of the source plan's equivalents were already wrong (`6/6/0` → `7/7/1`; `408` → `445`). A repeated measurement becomes the next reader's rot | §2.1 is a **measurement**. Every guard derives its expectation from the parser, the collector or the filesystem (§6.1 rule 4) |
| **Any `.mo` file change** | `.mo` is gitignored and is compiled at image build, at container start and in the CI `i18n` job | §2.2 rule 3 — **never `git add` a `.mo`.** Forbidden everywhere |
| **Writing any `14-I18N-0NN` finding number without the `14-` prefix** | The bare form is ambiguous across phases once cycles repeat | Cycle-scoped `14-I18N-0NN` is the convention, in comments, docstrings, test names, tracker entries and commit messages |
| **Any new block** arising because a measurement drifted | Re-measuring is not a mandate to build. All twelve live blocks are already chartered; a thirteenth would be a scope invention | §5.4's stop-and-report rule: new scope is a **decision**, not a discovery |

---

## 9. One-page summary

**Twelve blocks, one Implementor, one commit each, `"{type}({scope}): {description}"`, cycle-scoped
`14-I18N-0NN`. No migration. Three blocks write `.po`. Zero blocks shipped. BLOCK 13 cancelled.**

**Load-bearing order edges:** BLOCK 7 → BLOCK 11 (the parser fix is what makes the plural assertion
meaningful), BLOCK 10 → BLOCK 11 (the tree must be clean before the gate arrives), BLOCK 3 → BLOCK 4
(the chip reuses the corrected helper), BLOCK 1 → BLOCK 2 (normalise, then type), BLOCK 8 → BLOCK 9
(the widened collector defines the exemption set).

**The three corrected binding constraints:**

1. **`BC-1` — BLOCK 2's surface is 18 signatures across 11 files, not 10 across 6**, and
   `immediate_alerts.py` + `send_alerts.py` default to `LanguageLocale.RUSSIAN.value` — a second
   anti-pattern the source plan never names. Plus 27 filter-arg and 20-plus URL template renders the
   plan never lists.
2. **`BC-2` — BLOCK 10: `en` has 1 obsolete entry, not 0**, and `--no-obsolete` is **preventive, not a
   deleter**. The corrected start is `ru` 7 / `bs` 7 / `en` 1; the end state is still zero in all three.
3. **`BC-3` — BLOCK 11's invariant is `7/7/1`, not `6/6/0`, and its shape changed**: the `ru`/`bs` pair
   is now itself symmetric, `en`'s entry is a **member** of that set with an **empty `msgstr`**, and the
   assertion targets **all-three agreement at zero** — never non-emptiness of an obsolete `msgstr`.

**The five open gates, and who decides:** `Q3` `bs` grouping — **technical, Planner** (Product Owner if
option (c)). `Q5` `lang_pref` writer vs consent gate — **product/owner, Product Owner + phase 06
acknowledgement**. `Q6` accessor typing propagation — **technical, Planner**; enumeration complete,
option not chosen. `Q9` widened collector run — **Auditor runs the step, Planner decides the
consequence**. `Q11` three dead links — **technical, Planner**; option (b)'s price changed when
`docs/99-agent/` grew 5 → 9. **`Q1` stays `OPEN-PENDING-REVIEWER`** — ruled on *who*, no sign-off exists;
Product Owner must produce a named native Bosnian reviewer, preferably Montenegrin. **No option is
chosen in this plan, and no Implementor may choose one.**