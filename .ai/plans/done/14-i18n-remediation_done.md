---
plan_id: "14-i18n-remediation"
phase: "14"
phase_name: "i18n / Internationalization"
source_report: ".ai/audit/99-validation/14-i18n-validated-findings.md"
source_findings: ".ai/audit/14-i18n/findings.md (deleted in the working tree — not an input)"
code_context: ".ai/tmp/code-context-phase14.md"
date: "2026-09-29"
planner: "Planner (subagent)"
anchor_commit: "d42f778"
report_anchor_commit: "e57f8f8"
status: "planned"
findings_in_scope: 19
findings_still_exist: 15
findings_partial: 0
findings_already_fixed: 0
findings_rejected: 0
val_findings_open: 2
val_findings_stale: 2
new_findings: 4
blocks: 13
---

# Execution Plan — Phase 14 Remediation (i18n / Internationalization)

## 0. Header, provenance and scope statement

### 0.1 Provenance

| Item | Value |
|---|---|
| Source report | `.ai/audit/99-validation/14-i18n-validated-findings.md` (validated, 1210 lines) — the **only** surviving phase-14 input, and self-contained |
| Source findings file | `.ai/audit/14-i18n/findings.md` — **does not exist in the working tree.** Recorded for traceability only; not an input, and not a problem to fix. **No block may restore it** |
| Code-context document | `.ai/tmp/code-context-phase14.md` (780 lines, Auditor), written against anchor `e57f8f8` |
| **Working anchor commit for this plan** | **`d42f778`** (`git rev-parse --short HEAD`, taken before writing). The code context was written at `e57f8f8`; **the anchor drifted while the plan was being written.** Every load-bearing claim in §0.2.1 was re-verified against `d42f778`, and where the two disagree the tree wins |
| Date | 2026-09-29 |
| Findings in scope | **19 units**: 15 `I18N-` (`I18N-001` … `I18N-015`) + 4 `VAL-` (`VAL-001` … `VAL-004`) |
| State at the anchor | **15 of 15 `I18N-` findings still exist unchanged** · 0 partially fixed · 0 already fixed · 0 rejected · 0 pre-empted by another phase. Of the four `VAL-` entries: **1 stale/already fixed** (`VAL-001`) · **1 still stale** (`VAL-002`) · **2 still valid** (`VAL-003`, `VAL-004`) |
| New findings folded in by this Planner | **4** (§0.2.1, rows N-1 … N-4) — none of them appears in the validated report |
| Validated severity split | **0 CRITICAL · 2 HIGH · 6 MEDIUM · 7 LOW** |
| Execution blocks | **13** — 3 `mechanical`, 5 `behavioural`, 2 `structural`, 3 `conditional` (§2 carries the classification per finding) |
| Implementor concurrency | **1**, strictly sequential (project rule: only one implementor at a time) |
| Migration | **none.** No block ships a schema change and no block allocates an `AdvisoryLockId` |
| i18n | **Four blocks touch `.po` files** (BLOCKS 9, 10, 11, 13). Every one of them carries §1.6's re-read-immediately-before rule and the `--no-obsolete` deletion hazard. **Real `bs` translation work is 3 strings, not hundreds** (§0.3) |

**Naming convention.** Every citation of this phase's own findings is cycle-scoped
**`14-I18N-0NN`**, never a bare `I18N-0NN`, wherever it must survive into a comment, a
docstring, a test name, a tracker entry or a commit message.

**The headline correction.** The phase task framing implied a bulk-translation project.
**It is not one.** The three catalogues are 409 active entries each with an identical msgid
set, **0 fuzzy**, **0 empty `msgstr` in `ru` or `bs`** (408 in `en`, which is the *documented*
exemption — `msgid` is English), **0 `msgctxt`**, and **2 plural entries each with 0 blank
forms**. The real, measurable `bs` debt is **3 strings**. Everything else in this phase is
engineering: one middleware branch, five accessor signatures, one formatting helper, one
settings line, one parser return type, three collectors, one template interpolation, one
cookie call, one docstring. **§0.3 sizes this explicitly; the plan is scoped to the
engineering, and the linguistic slice is gated, not written.**

**The real hazards are process, not code.** A `VAL-003` false-green regression test; a
half-fixed `bs` number format that a "complete-looking" fix introduces; a `.po` append race
across six other phases; and a six-way collision on `config/settings/base.py`. §0.2.2 states
all four; §7 assigns them per block.

---

### 0.2 Evidence basis — read this before executing any block

The validated report is the narrative source; the Auditor's code context re-measured it
against the tree at `e57f8f8`; this Planner re-verified the load-bearing claims against
`d42f778` using read-only inspection (no `makemessages`, no `compilemessages`, no test run,
no git mutation). **The tree is the authority.** Where the report, the code context and the
tree disagree, the correction is here and the plan is built on the tree's answer.

#### 0.2.1 Corrections — the tree wins

| # | Claim | Report / context says | **Tree at `d42f778` says** (✔ = re-verified by this Planner) | Consequence |
|---|---|---|---|---|
| **C-1** | `VAL-001`: `RUN_TRANSLATION_BACKFILL` is consumed and `CFG-008` stands | "do not close CFG-008" | ✔ **STALE / ALREADY FIXED.** `src/backend/config/settings/base.py` → `ALLOWED_ENV_VARS` contains `"RUN_TRANSLATION_BACKFILL"`, and `config/settings/tests/test_env_allowlist_reverse.py` exists. The consumption site (`apps/core/utils/migrate_locked.py` → `_build_steps`) is unchanged | **`VAL-001` is not actioned. No block touches it.** The report's *narrative* correction (phase-14 Appendix D answered the wrong question) remains true as a documentation note; the actionable instruction does not |
| **C-2** | `src/backend/templates` has 43 files | 43 | ✔ **38** `.html` files, and **38** files total — there is nothing else in the tree | No new gate may hard-code a file count. BLOCK 11's guard derives its expectation from the collector, not from a literal |
| **C-3** | `I18N-013`: 18 `verbose_name` + 169 `help_text` | 18 + 169 (context) / 18 + 169 (report) | ✔ **20** `verbose_name`/`verbose_name_plural` and **172** `help_text` assignments across `src/backend/apps/*/models.py`; **0** gettext occurrences in any `models.py` | Option B grows the catalogue by **~192** entries, not ~187. Both the report *and* the code context are stale here |
| **C-4** | `I18N-014`: `--no-obsolete` is omitted, "so entries are marked `#~` rather than removed" — implying no `#~` blocks exist | implied none | ✔ **Obsolete entries are 6 (`ru`) / 6 (`bs`) / 0 (`en`)** — not obsolete-symmetric, and **nothing gates that dimension**. Fuzzy **0 / 0 / 0**, `msgctxt` **0 / 0 / 0**, plural entries **2 / 2 / 2** | A new finding (N-2). BLOCK 10's prune is what resolves it once; BLOCK 11's assertion is what prevents recurrence. **The report's "prune once" framing understates a real live inconsistency** |
| **C-5** | The `bs` copy-through set is `ID`, `Telegram ID:`, `Pro`, `Telegram`, `Google Translate`, `Plausible Analytics`, `Admin`, `Moderator #%(mid)s`, `Start` | 9, of which 6 legitimate | ✔ **Exactly 9**, byte-for-byte the same list. ✔ **`Moderator #%(mid)s` lives in `templates/analytics/moderation_dashboard.html`** — which is in the gate's own `exclude_subpaths` tuple (`admin/`, `analytics/moderation_dashboard.html`, `components/feature_tag.html`) and is therefore **already out of scan scope** | **Corrects the code context's Q1 reasoning.** It claims "if the owner exempts admin metadata, two of the three [real `bs` strings] disappear from scope entirely". That is **not supported by the tree**: `I18N-013` is about *model metadata* (`verbose_name`/`help_text`), a different surface from a *template* that is already exempt. **Q1 and Q2 are independent; neither gates the other** |
| **C-6** | `Admin` is a real `bs` gap | 1 of the 3 | ✔ **In scan scope.** `{% trans "Admin" %` appears in `templates/components/header.html` and `templates/components/header_auth_entry.html` — neither is excluded | `Admin` is a genuine `bs` copy-through in a scanned template. Staff-facing, public-path. **A linguist decision, not an engineering one** (BLOCK 9, Q1) |
| **N-1** | *(not in the report)* | — | ✔ **One Cyrillic-contaminated `bs` translation.** The `bs` `msgstr` for the multi-line support-greeting msgid ends `"Za kreiranje oglasа користи /post."` — a Croatian/Bosnian frame carrying the **Russian verb** `користи` and a **Cyrillic "а"** inside `oglasa`. It is the **only** Cyrillic-bearing line in the whole `bs` catalogue. **No gate catches it**, and the reason is explicit: `test_no_cyrillic_msgids`'s own docstring says *"`msgstr` values for ru/bs are naturally Cyrillic and exempt"* — it inspects `msgid` only | BLOCK 9. The **detection half is engineering** (a `bs`-scoped `msgstr` script rule); the **string half is a human deliverable** (Q1). The Implementor is forbidden from writing the replacement text |
| **N-2** | *(not in the report)* | — | ✔ Obsolete **6 / 6 / 0** — see C-4. `test_pot_creation_date_sync` compares only the `POT-Creation-Date` header, so the asymmetry is ungated | BLOCK 10 (prune) + BLOCK 11 (assertion) |
| **N-3** | *(not in the report)* | — | ✔ **`docs/01-spec/i18n-spec.md` — phase 14's own authoritative document — has 3 dead relative link targets**, referenced 5 times in total: `../99-agent/i18n-translation-pipeline-gap-analysis.md` (×3), `../99-agent/i18n-definition-of-done-research.md` (×1), `../96-researches/i18n-translation-egress.md` (×1). **The whole `docs/96-researches/` directory does not exist**; the two `docs/99-agent/` files are absent from a directory that holds only `architecture.md`, `dependency-risk-register.md`, `references.md`, `rules.md` and three test-audit files | BLOCK 12. The "Development & CI Integration", "Translation Egress" and Definition-of-Done sections all point at documents that have never existed |
| **N-4** | *(not in the report)* | — | ✔ **`i18n-spec.md` carries stale line citations** (the settings block is cited as `L55`-`L62`; `Ad.get_title`/`get_description` are cited as one span `L464-487`, but they are two distinct methods). All **line anchors throughout the validated report have drifted** — e.g. the report cites `base.py:139-144` for the cookie block, which is at `:151-157`, and `TEMPLATES` at `:215-236`, which is at `:231-232` | BLOCK 12. **Every task target in this plan is semantic** — file path plus module / class / function / template name. **No line number is ever a target** |

**Symbol-level re-verification at `d42f778` (✔ every load-bearing claim reproduced).**

| Claim | Verified at the tree |
|---|---|
| `I18N-001` | `apps/core/middleware/language.py` → `process_request` reads `request.COOKIES.get(LANGUAGE_COOKIE_NAME)` and passes the **raw** string onward; `_apply_lang_param` is the only normalising path; `_set_language_code` calls `translation.activate(lang)` |
| `VAL-003` | `config/settings/base.py` → `LANGUAGE_CODE = "ru"`; `config/settings/test.py` → `LANGUAGE_CODE = "en"`. `TIME_ZONE` and `USE_TZ` are **absent from every module in the package** |
| `I18N-003` | `apps/ads/templatetags/price_tags.py` → `_format_amount` builds `format(rounded, "f")` and returns `intcomma(formatted)` — a **`str`**, not the `Decimal` |
| `VAL-004` | `django/conf/locale/bs/formats.py` sets `DECIMAL_SEPARATOR = ","` and `THOUSAND_SEPARATOR = "."` and leaves **`# NUMBER_GROUPING =` commented out**. `ru/formats.py` sets all three. Grouping is structurally unreachable for `bs` |
| `I18N-005` | `testing/i18n_helpers.py` → `_parse_po_entries(text: str) -> list[tuple[str, str]]`; on every `msgstr`-prefixed line **including `msgstr[N]`** it executes `cur_msgstr = [_unescape(rest)]`, keeping only the **last** form, while the docstring claims the **first** |
| `I18N-002` | `apps/categories/views.py` → `cache_key = f"category:submenu:{get_tree_version()}:{category.slug}:{request.LANGUAGE_CODE or 'ru'}"` |
| `I18N-011` | `language.py` → `process_response` calls `response.set_cookie(LANGUAGE_COOKIE_NAME, cookie_value, max_age=LANGUAGE_COOKIE_MAX_AGE)` and supplies **no** `secure`, `samesite` or `httponly` |
| `I18N-012` | `language.py` → `patch_vary_headers(response, ("Accept-Language",))` plus a docstring presenting that as the complete cache contract |
| `I18N-015` | `language.py` → `_parse_accept_language` does `first_tag = accept_language.split(",")[0]` and returns immediately |
| `I18N-001` limb 2 | All five accessors typed `locale: str = LanguageLocale.RUSSIAN` — `Category.get_name`, `City.get_name`, `LookupItem.get_name`, `Ad.get_title`, `Ad.get_description` — and all five `localized_content` filters identically typed. `context_processors.language` returns `{"LANGUAGE_CODE": getattr(request, "LANGUAGE_CODE", settings.LANGUAGE_CODE)}` — a **`str`** |
| `I18N-014` | `Makefile` → `makemessages` invokes `makemessages -l ru -l bs -l en --no-location`; **`--no-obsolete` is absent** |
| `I18N-006` / `-007` | The `bs` catalogue holds the twelve non-gettext `BotCommand` literals' residue: `Start`, `Language`, `Post ad`, `Alerts` are all present as **active** entries |
| Unverified | `test_i18n_category_city.py` exists (5 tests, `django_db` + `integration`) and was **not** run during the audit — see §0.2.3 |

#### 0.2.2 The four hazards that constrain how any block may be implemented

1. **`VAL-003` — a false-green `I18N-001` regression test is the single most likely way this
   phase ships wrong.** `config/settings/base.py` sets `LANGUAGE_CODE = "ru"`;
   `config/settings/test.py` sets `LANGUAGE_CODE = "en"`. Django's
   `DjangoTranslation._add_fallback` adds `settings.LANGUAGE_CODE` as a catalogue fallback
   for any activated language that is not `en*`, so **the gettext chrome for an unsupported
   locale is Russian in production and English under test for the identical request**, while
   the **DB accessors behave identically in both**. A test that asserts on rendered chrome
   for an unsupported cookie locale will pass in CI and production will still render a
   wholly Russian page. **The binding rule: assert on the accessor result, which is
   default-independent, or pin `LANGUAGE_CODE` explicitly with `override_settings`. Never
   assert on chrome text for an unsupported locale.** This is repeated verbatim in BLOCK 1's
   constraints, in its task YAML, and in §7.

2. **`I18N-003`'s one-argument fix is necessary and insufficient, and it will *look*
   complete.** Passing the `Decimal` to `intcomma` restores the decimal mark for `ru` and
   `bs` — but `bs` **thousands grouping remains structurally impossible**, because Django's
   bundled `bs` locale leaves `NUMBER_GROUPING` commented out and
   `django/utils/numberformat.py` gates on `use_grouping and grouping != 0`, which
   hard-disables grouping even under `force_grouping=True`. A plan that ships only the
   argument change leaves `bs` readers seeing `1234,56` beside `ru` readers seeing
   `1 234,56` — **a new visible inconsistency, introduced by a fix.** The grouping decision
   (`Q3`) **must be made and shipped inside the same change as the argument change.**

3. **The three `.po` files are the most contended i18n artefact in the repository, and six
   other phases are appending to them.** Phases 03, 05, 06, 07, 08 and 10 all add `ru`/`bs`
   strings, and `makemessages` rewrites all three catalogues in place. **Any wholesale
   regeneration in that window silently deletes a concurrent phase's work** — and the i18n
   gate would then be *red*, sending whoever lands next to the wrong conclusion. On top of
   that, **`--no-obsolete` deletes entries by design**, which makes BLOCK 10 the single most
   dangerous operation in the phase. **Every `.po` block carries §1.6's rule: re-read all
   three `.po` files immediately before the `makemessages` invocation and again immediately
   before `git add`, and stage them explicitly by path — never by directory.**

4. **`config/settings/base.py` is six-way contended, and `I18N-004` needs it.** Phases 02,
   04, 06, 07, 08 and 12 all claim it. A `TIME_ZONE` line plus an `ALLOWED_ENV_VARS` entry
   plus up to four `.env*.example` lines, in the most contended settings file in the
   repository, and the allowlist is gated **in both directions** by
   `config/settings/tests/test_env_allowlist.py`. Two settings files were being edited by a
   concurrent agent during the audit itself. **Re-read immediately before editing; stop and
   report a concurrent change; never stage by directory.**

#### 0.2.3 Runtime re-verification required before a block relies on a claim

No test suite was run for the audit, for the code context, or for this plan. Nothing was
executed against a running stack; no container or compose project was started, stopped or
altered; **no page was rendered and no `makemessages` / `compilemessages` was invoked.** The
validated report's probe values are plausible and statically supported, but they were
**never executed**. The items below are stated as **binding pre-conditions of the named
block**, not as background reading.

| # | Claim that is statically supported but **not executed** | Block | Required pre-step |
|---|---|---|---|
| 1 | `I18N-001`'s per-locale symptom table — that `en-US` / `en_US` / `EN` / `xx` / `de-DE` / `ru-RU` cookies drive every DB-backed string to the `ru` branch, and that `xx` renders a wholly Russian page under production settings | **1** | **Run the full i18n gate including `test_i18n_category_city.py` first** (§1.1) and record the observed per-locale table in the commit body. A red result from a concurrent agent is a teardown race, not a defect — re-run serially before reporting |
| 2 | `I18N-003`'s asymmetry — integer amounts localise, fractional amounts do not, and the specific `ru` / `bs` / `en` separator outputs | **3** | Drive `format_price_value` for a fractional amount, a round amount and a ≥7-digit amount under `translation.override` for all three locales **before** the edit, and record it |
| 3 | `VAL-004`'s runtime value — `number_format(1000000, force_grouping=True)` returning `1000000` for `bs` | **3** | Same probe as (2). ✔ Statically confirmed by reading Django's `bs/formats.py`; the runtime value is still unobserved |
| 4 | `I18N-004`'s probe values — `settings.TIME_ZONE == "America/Chicago"`, `USE_TZ is True`, and the per-locale renderings of the four display patterns | **5** | ✔ `TIME_ZONE`/`USE_TZ` absence re-verified statically. The renderings are unobserved; BLOCK 5's own tests establish them before and after |
| 5 | `I18N-006` / `I18N-007`'s "latent today" claims — that the widened bot collector and the app-template collector find nothing new | **8** | **Almost certainly false for the bot collector**, because `src/telegram_bot/lifecycle.py` → `_COMMANDS` holds twelve non-gettext `BotCommand` literals and four of their msgids are the `I18N-014` orphans. The widened run itself was never performed. This is **Q9**, a pre-block step, not an assumption |
| 6 | `I18N-012`'s `Vary: Cookie` claim — that `CsrfViewMiddleware` puts `Cookie` in `Vary` on every full page response | **6** | ✔ Statically supported (24 `csrf_token` occurrences across 16 templates; Django's own source behaviour). **BLOCK 6 changes the docstring, not the header** — the header claim is not load-bearing for the fix |
| 7 | `I18N-010`'s rendered output — that `{% blocktrans %}` stringifies a `Decimal` without `number_format` | **4** | BLOCK 4's own test renders the chip under `override("ru")` and asserts the separator; that *is* the verification |
| 8 | `.mo` runtime content | — | The audit read `.po` only. The container entrypoint reported all three `.mo` "already compiled and up to date", but their compiled content was not inspected. `.mo` is gitignored and is compiled at image build, at container start and in the CI `i18n` job |
| 9 | **`test_i18n_category_city.py`** (5 tests, `django_db` + `integration`) — the 5 DB-backed i18n tests | **1, 2, 4** | **NOT RUN during the audit** (they require the shared `test_mko_bazuna` database and another agent could have been using it). The 50 tests that did pass cover the four static modules only. These five are **the only DB-backed i18n evidence in the phase** and are the natural home for BLOCK 2's and BLOCK 4's rendering assertions. **Listed as unverified** |

---

### 0.3 Explicit scope statement

**In scope — the 15 live `I18N-` findings, plus 2 live `VAL-` advisories and 4 findings this
Planner added.** Every one is assigned to a block in §2 and none is dropped.

**Out of scope, by name, with a destination:**

| Not done here | Why | Where it goes |
|---|---|---|
| `VAL-001` — `RUN_TRANSLATION_BACKFILL` / `CFG-008` | ✔ **Stale — already fixed at the anchor** (C-1). Actioning it would produce a false reopening | Nowhere. Recorded |
| `VAL-002` — phase-08's deferred `sanitize_query_for_log` classification | ✔ **Still stale.** The function contains no `isalpha()`; it strips only control characters and truncates, so Cyrillic, Serbian Latin diacritics and digits all pass through. **No code change exists to make.** The residual work is procedural — close the phase-08 deferral explicitly and correct the phase-08 advisory text that still describes removed behaviour | §6.2 — recorded for phase 08. Phase 14 does **not** edit `apps/core/utils/sanitize.py`; it is claimed by phase 08 and phase 09 |
| The `RUN_TRANSLATION_BACKFILL` **target-language matrix** — which languages `backfill_translations` produces, and whether a wrong target silently degrades `bs` ad content to Russian through the same `locale → ru` chain, with no gate coverage | It is unowned, it is a **product/ops** decision, and `backfill_translations` is **phase 09's** | §6.2 — recorded, routed to phase 09 / the coordinator. Phase 14 records the interaction; it does not audit the backfill |
| The `en` catalogue's 408 empty `msgstr`s | **Documented convention** (the `msgid` is English) and asserted by `test_no_empty_msgstr`'s `en` skip in **two independent test modules**. Filling them is a 408-entry diff that changes nothing at runtime and breaks the stated contract | **Nowhere. Never.** §6.3 item 4 forbids it |
| The six legitimate `bs` copy-through entries (`ID`, `Telegram ID:`, `Pro`, `Telegram`, `Google Translate`, `Plausible Analytics`) | Brand and product names that are **correctly identical** in Bosnian | **Nowhere.** §6.3 item 5 forbids "fixing" them |
| The two `bs` plural entries that share `msgstr[1]` and `msgstr[2]` | **Correct** for `bs` CLDR (`nplurals=3; plural=n%10==1 && n%100!=11 ? 0 : 1`). Indistinguishable from a copy-paste error to a reader, and exactly the class `I18N-005`'s plural-aware parser must handle without flagging | **Nowhere.** §6.3 item 5 forbids "correcting" them |
| `I18N-012`'s **header** | The finding was reclassified to `DOC-UPDATE` **because the code is already correct**. The correctness impact was refuted: `CsrfViewMiddleware` adds `Vary: Cookie` on every full page response, so a `Vary`-honouring cache already keys on the cookie | **Nowhere.** §6.3 item 3 forbids adding a `Vary: Cookie` header. BLOCK 6 corrects the **docstring** |
| The two `<time datetime="{{ …\|date:'Y-m-d' }}">` ISO attributes in `ads/detail.html` and `ads/partials/ad_list.html` | They are **correct ISO 8601 machine-readable values**, not display strings | **Nowhere.** §6.3 item 6 forbids touching them in BLOCK 5 |
| The three `locale_head.html`-inclusion facts and the 38-file template census | Both are **verified** (16 files reference the partial; 38 templates exist). BLOCK 8 turns them into a guard that derives its own expectation | Carried into BLOCK 8 |
| Adding `LocaleMiddleware`, a `set_language` view, or `i18n_patterns` | The `language.py` module docstring explains why `LocaleMiddleware` is **intentionally absent**: it would re-derive the language from the never-set `django_language` cookie plus `Accept-Language`, clobbering the resolved value and ignoring both `?lang=` and `lang_pref` | **Nowhere.** §6.3 item 7 |
| The third locale authority, `SavedSearch.language` (which FTS vector a saved search matches) and `User.telegram_language` (the bot's per-user locale) | Three **distinct** authorities that are frequently conflated. Neither this plan's change alters either | Documented in BLOCK 1's constraints so a wrong fix is not written |

**The `bs` debt, sized exactly.** Three strings need a human; everything else is engineering.

| # | String | Where | Gate status | Block |
|---|---|---|---|---|
| 1 | the contaminated support-greeting sentence (`"Za kreiranje oglasа користи /post."` — Russian verb, Cyrillic `а`) | `bs` catalogue, support-contact flow | **No gate catches it.** `test_no_cyrillic_msgids` inspects `msgid` only, and its docstring declares `msgstr` exempt | **9** (N-1) |
| 2 | `Moderator #%(mid)s` — copy-through | `templates/analytics/moderation_dashboard.html` | In `exclude_subpaths`; the gate cannot see it | **9** (Q1) |
| 3 | `Admin` — copy-through | `templates/components/header.html`, `templates/components/header_auth_entry.html` | In scan scope, but a copy-through is not a violation the gate encodes | **9** (Q1) |

`Start` is a fourth copy-through and is **also** one of the six `I18N-014` orphans — it is
**pruned, not translated** (BLOCK 10). The other two orphans (`Language`, `Post ad`,
`Alerts`, plus two reworded strings) are pruned in the same pass. **Two of the three real
strings sit in staff surfaces, which is a reason to be careful, not a reason to drop them.**

---

### 0.4 Severity corrections

The validated report's own reclassifications are upheld in full, and two further corrections
are made by this Planner on tree evidence.

| ID | Filed | Report | **This plan** | Basis |
|---|---|---|---|---|
| `I18N-001` | HIGH | HIGH | **HIGH — P0, first block in the plan** | Unchanged. Every mitigation is still absent and the blast radius is still site-wide |
| `I18N-003` | HIGH | HIGH | **HIGH — P0, with `VAL-004` folded in** | Unchanged. The `bs` grouping gap is not a separate defect; it is an incompleteness in this finding's remedy |
| `I18N-004` | HIGH | MEDIUM | **MEDIUM — P1** | Upheld. `USE_TZ` is `True` (Django 5 global default), so no naive/aware integrity class exists; the defect is a wrong-by-default display value in one render dimension |
| `I18N-002` | MEDIUM | LOW | **LOW — folded into BLOCK 1 as defence-in-depth** | Upheld. Fully subsumed by `I18N-001`; what survives is a key-building site trusting an unvalidated request attribute |
| `I18N-005` | MEDIUM | MEDIUM | **MEDIUM — P1** | Unchanged. Reproduced on a synthetic entry; also confirmed **latent** (0 plural entries in `ru`/`bs` have any empty form) |
| `I18N-006` | MEDIUM | MEDIUM (scope extended) | **MEDIUM — P1** | Unchanged, and the unscanned set is confirmed to also include `retry.py` and `states.py` |
| `I18N-007` | MEDIUM | MEDIUM | **MEDIUM — P2** | Unchanged. `APP_DIRS: True` confirmed; latent today (no `apps/*/templates/` exists) |
| `I18N-008` | MEDIUM | MEDIUM | **MEDIUM — P2** | Unchanged. All 15 page templates include the partial today — a coverage gap, not a live defect |
| `I18N-009` | MEDIUM | MEDIUM | **MEDIUM — P1, gated on Q5** | Unchanged, and extended: the client helper sets `SameSite=Lax` while the server `set_cookie` sets none, so the two writers disagree on more than the consent gate |
| `I18N-010` | MEDIUM | MEDIUM | **MEDIUM — P1** | Unchanged. The in-file precedent the validator added is confirmed: `ads/partials/ad_list.html` already uses the exact pattern the remedy proposes |
| `I18N-011` | LOW | LOW | **LOW — P2, sequenced after `I18N-009`** | Unchanged. `httponly=True` is only safe once the client-side writer is removed |
| `I18N-012` | LOW | LOW, reclassified `DOC-UPDATE` | **LOW — documentation only, folded into BLOCK 6** | Upheld, with the impact refuted. **The code needs no change.** BLOCK 6 fixes the docstring |
| `I18N-013` | LOW | LOW, re-scoped as an **OWNER DECISION** | **NOT a severity. A gate.** Option A is `mechanical`; Option B is `M` and touches admin tests. BLOCK 12 carries Option A's doc change; BLOCK 13 carries Option B | Upheld. ✔ Scale corrected to **20 + 172** (C-3) |
| `I18N-014` | LOW | LOW | **LOW — P2, split into BLOCK 10 (prune) and BLOCK 11 (gate)** | Upheld, **strengthened** by C-4/N-2: six `#~` entries already exist in two of three catalogues, and the asymmetry is ungated |
| `I18N-015` | LOW | LOW | **LOW — P2, folded into BLOCK 1** | Upheld. Same module, one shared resolver |
| `VAL-003` | LOW | LOW advisory | **Advisory — but a binding constraint on BLOCK 1's test shape** | ✔ Still valid. Upheld and promoted from "advisory" to "constraint", because it decides whether the phase's headline fix can be tested honestly |
| `VAL-004` | LOW | LOW advisory | **Advisory — folded into `I18N-003`/BLOCK 3 as a shipped decision, not a note** | ✔ Confirmed statically. Promoted to a decision gate (**Q3**) because the one-argument fix is incomplete without it |
| **N-1** | — | *not filed* | **MEDIUM — new.** One Cyrillic-contaminated `bs` translation with **zero gate coverage** | A `mechanical` detection rule (BLOCK 9) plus a `conditional` human deliverable. The detection half is the finding; the string half is Q1 |
| **N-2** | — | *not filed* | **LOW — new.** `ru`/`bs` carry 6 obsolete entries, `en` carries 0, and nothing gates it | Folded into BLOCK 10 (one-shot resolution) and BLOCK 11 (durable assertion) |
| **N-3** | — | *not filed* | **LOW — new.** 3 dead link targets in `i18n-spec.md`, referenced 5× | BLOCK 12. Documentation, `mechanical` |
| **N-4** | — | *not filed* | **LOW — new.** Stale line citations in `i18n-spec.md` and throughout the validated report | BLOCK 12; and it is why no task in this plan uses a line number as a target |

**Nothing was rejected and nothing was merged away.** `I18N-002` is folded into BLOCK 1 by
shared root cause, not merged as a finding: its remediation site differs (the key-building
site, not the resolver) and it is retained as defence-in-depth. `VAL-004` is folded into
`I18N-003` because the root cause and the fix site are identical.

---

### 0.5 Open technical questions — resolved here, or explicitly gated in their block

**No question below is answered by this plan.** Each one either has an explicit pre-block
step, or is a labelled **decision required before implementation** gate carrying its
options and their consequences. **The Implementor is forbidden from choosing an option**
(§1.5, §8.1). **Q3, Q5, Q6, Q9 and Q11 are the ones that block a block from starting.**

**Updated 2026-10-03 (Product Owner decision round).** `Q1`, `Q2` and `Q4` are now recorded
below with their rulings. **`Q1`'s ruling settles *who signs off* and does NOT close the gate —
the gate is `OPEN-PENDING-REVIEWER`**, which is a recorded state distinct from both "gated" and
"closed". `Q2` and `Q4` are closed outright. `Q3`, `Q5`, `Q6`, `Q8` and `Q11` are untouched.

| # | Question | Kind | Owner | Block | Status |
|---|---|---|---|---|---|
| **Q1** | **Who signs off the 3 real `bs` translations?** A native Bosnian reviewer (preferably Montenegrin, per the operating region) is required for all three. **No engineer and no translation API may produce them** — the contaminated string needs a linguist, and phase 09's outbound Google-Translate client is explicitly **not** a catalogue tool. *Is a reviewer available, or does `bs` ship with these three as-is and the finding is recorded as accepted?* | **GATE — owner / coordinator** | **Product Owner** | **9** | **✅ RULED 2026-10-03 (Product Owner) — a native, preferably Montenegrin reviewer signs off the three `bs` strings; machine output and translation APIs are NOT acceptable. 🚧 GATE REMAINS `OPEN-PENDING-REVIEWER` — this is NOT closed.** Until a sign-off exists, **BLOCK 9 ships its reduced deliverable** (detection rule + a named commented exemption) exactly as specified below. The gate is recorded as **OPEN-PENDING-REVIEWER**, not closed, so nobody reads it as settled. Re-opening it requires only the reviewer's sign-off; no re-decision |
| **Q2** | **`I18N-013`: Option A (document model metadata as exempt) or Option B (wrap ~192 entries in `gettext_lazy` and re-extract)?** | **GATE — owner** | **Product Owner** | **12** (Option A doc), **13** (Option B code) | **✅ RESOLVED 2026-10-03 — Product Owner chose Option A: model `verbose_name` / `help_text` is documented as an explicit, named exemption in the i18n coverage rule**, following the existing documented exemption for the `admin/` template subtree. **Option B (wrapping ~192 entries in `gettext_lazy`) is DECLINED.** Consequences: **BLOCK 12 delivers the documentation change and is now the SOLE home of `I18N-013`** · **BLOCK 13 is CANCELLED** · **no catalogue growth** · the admin tests asserting English field text **stay unchanged**. The Implementor may not re-open the option |
| **Q3** | **The `bs` number-grouping decision.** Three options: **(a)** a project-level `FORMATS` override supplying `NUMBER_GROUPING = 3` for `bs` in settings; **(b)** a project-owned formatting helper that bypasses `numberformat.py`'s grouping gate; **(c)** accept ungrouped `bs` prices as a documented limitation. Django's bundled `bs` data cannot be edited — it is a third-party package | **GATE — Planner + Researcher** | Planner | **3** | **BLOCKING.** Option (a) touches the six-way-contended `base.py` and must ship its own settings test; option (b) adds a new project-owned module, which risks a *second* formatting path that can drift from `number_format`; option (c) leaves a visible `ru`/`bs` inconsistency, which **is** the defect the fix was meant to close. **This decision must be made and shipped inside the same change as the argument fix.** **Untouched by the 2026-10-03 round** |
| **Q4** | **The `TIME_ZONE` value, and whether it is env-overridable.** The operating region is Montenegro/Bosnia, so the intended value is almost certainly `Europe/Podgorica` — **but the exact zone is a product decision** (does the site track one country or several?). If it becomes env-overridable it needs an `ALLOWED_ENV_VARS` entry **and** up to four `.env*.example` lines **in the same commit**, in the most contended settings file in the repository, and the allowlist is gated in both directions | **GATE — owner + Planner** | **Owner decides the value; Planner decides the env-overridability** | **5** | **✅ RESOLVED 2026-10-03 — Product Owner chose the hard-coded outcome: `TIME_ZONE = "Europe/Podgorica"`, hard-coded and NOT env-overridable.** Consequences: **no `ALLOWED_ENV_VARS` entry and no `.env*.example` lines** — the allowlist collision **disappears entirely**, and **no other phase's allowlist work is triggered**. **The env-overridability branch is CLOSED**: the env-dependent file surface in BLOCK 5 below is marked not-applicable and must not be created. BLOCK 5 starts unblocked |
| **Q5** | **Is the server write authoritative for `lang_pref`, or is the consent gate real?** The report recommends "server write is authoritative; delete the consent-guarded JS branch". If the consent gate is meant to be real, it must move into `process_response` and **coordinate with phase 06**, which owns consent state. This is a **phase-06 boundary question, not a phase-14 unilateral decision** | **GATE — owner + coordinator, phase 06** | Owner + phase 06 | **6** | **BLOCKING.** Also gates `I18N-011`'s `httponly=True`: that is only safe once the client-side writer is gone. `docs/01-spec/technical-specification.md` is **phase 06's reservation** — the "name `lang_pref` in a cookie list" limb needs their clearance or is deferred |
| **Q6** | **Does `I18N-001`'s accessor typing propagate to the context processor?** The five accessors and the five `localized_content` filters are all typed `locale: str`; templates call them as `\|get_city_name:LANGUAGE_CODE` where `LANGUAGE_CODE` is a `str` from `apps/core/context_processors.py` → `language(request)`. Tightening the accessors to `LanguageLocale` propagates to the filters, and then to the context processor — which is read by several other phases' templates | **GATE — Planner + Auditor** | Planner | **2** | **NOT blocking, but sized as the phase's only structural item.** Options: (a) the context processor emits `LanguageLocale` and the filters take `LanguageLocale` (widest surface, strongest typing); (b) the accessors keep a `str`-accepting boundary and normalise internally (narrowest surface, weakest guarantee — and arguably a partial re-fix of `I18N-001` at a second site). The Auditor must enumerate every consumer of `context_processors.language` **before** the block starts |
| **Q7** | **Should the `en` catalogue's 408 empty `msgstr`s stay empty forever?** | **RESOLVED — no change** | Planner | — | Answered: the convention is already correct and is enforced by two tests. **Recorded so a remediation does not "helpfully" fill them.** §6.3 item 4 forbids it |
| **Q8** | **Should the obsolete asymmetry (N-2) become its own gate, or is it part of `I18N-014`?** | **GATE — Planner** | Planner | **11** | Resolved as **part of `I18N-014`**: one assertion, in BLOCK 11, alongside the reverse stale-entry gate — they read the same files and fail for the same root cause (a missing reverse assertion). Not a separate `VAL`-level item |
| **Q9** | **Does the widened bot collector (`I18N-006`) pass on the current tree?** | **PRE-BLOCK STEP — Auditor** | Auditor | **8** | **Explicit pre-block step, not a guess.** `src/telegram_bot/lifecycle.py` → `_COMMANDS` holds twelve non-gettext `BotCommand` literals, four of which are the `I18N-014` orphans, so the answer is almost certainly **"no, not without the documented exemption."** The Auditor must run the widened collector before the block starts and report exactly which files fail and why |
| **Q10** | **What is the `RUN_TRANSLATION_BACKFILL` target-language matrix, and who verifies it?** | **ROUTED** | Coordinator / phase 09 | — | **Unowned, and out of phase 14's scope.** `backfill_translations` produces the `Ad.title_bs` / `Ad.title_en` values that `Ad.get_title` reads; a wrong target degrades `bs` ad content to Russian through the same `locale → ru` chain, with no gate coverage. §6.2 records the interaction. Phase 14 does **not** audit the backfill and does **not** edit `apps/core/services/translation.py` |
| **Q11** | **May BLOCK 12 re-point `i18n-spec.md`'s three dead links (N-3) at documents that do not exist?** | **GATE — Planner** | Planner | **12** | Three options with different costs: (a) **delete the three references** and fold their content into `i18n-spec.md` (the honest, cheapest option — the sources they point at were research notes that were never committed); (b) re-point them at the nearest live documents (`docs/99-agent/architecture.md`, `docs/01-spec/technical-specification.md`) — **but that asserts those documents contain content they may not contain**; (c) replace the link text with a "see the repository" pointer and no link. The Implementor may not choose. **Option (a) is the Planner's recommendation** |

---

## 1. Environment and command contract for the implementor

### 1.1 Tests are Docker-only — `uv run pytest` on the host always fails

There is no PostgreSQL on `localhost:5432`. **Every test run goes through the `test` service
of the `mko-bazuna-test` Compose project** (PostgreSQL on host port `5433`).

```powershell
# Alias, copied once per session
$dc = 'docker compose --project-name mko-bazuna-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml'

# Start the DB if it is not already up
docker ps --filter "name=mko-bazuna-test-db-"
$dc up -d db

# Fast gate (skips the nightly `seed` suite) - the default iteration command
.\Makefile.ps1 test

# The same fast gate, spelled out (this exact form is the contract):
$dc run --rm --env PYTEST_SKIP_MARKERS=seed test

# Full suite (only when a change touches seeding or images)
.\Makefile.ps1 test-all

# Targeted run - the i18n gate, including the DB-backed module
$dc run --rm --env PYTEST_SKIP_MARKERS=seed -e PYTEST_OPTS="src/backend/apps/ads/tests/test_i18n_completeness.py src/backend/apps/ads/tests/test_i18n_pipeline.py src/backend/apps/ads/tests/test_price_format.py src/backend/apps/ads/tests/test_i18n_category_city.py src/backend/apps/core/tests/test_language_middleware.py -q" test
```

Three facts about this path that cost a day if they are not known:

1. **`PYTEST_OPTS` is unquoted in `docker/entrypoint-test.sh`**, so each token word-splits
   on spaces. Bare file paths and single-token flags work; **quoted multi-token values do
   not** (`-k "a b"` is impossible). Setting `PYTEST_OPTS` also **replaces** the defaults
   (`--reuse-db --tb=short --durations=10 -n auto --maxprocesses=4 --dist loadgroup`), so a
   targeted run loses xdist parallelism and DB reuse.
2. **Never use `--override-ini=addopts=`.** It strips `--import-mode=importlib`, which is
   set in `pyproject.toml`.
3. **The `test` container performs no database setup at all.** `test_mko_bazuna` is
   provisioned by pytest-django, and its reference data is restored by the session-autouse
   `_restore_test_schema_post_db_setup` fixture in `src/backend/conftest.py` under advisory
   lock 111. A red result caused by a concurrent agent's teardown is a **race, not a
   defect** — re-run serially before reporting it.

**No phase-14 block ships a migration.** If one appears that phase 14 did not write, it is
another phase's and is reported, not absorbed.

### 1.2 `makemessages` / `compilemessages` — `make` does not work on this environment

**This is the single most expensive thing to get wrong. Read it before BLOCK 9, 10, 11 or 13.**

`make makemessages` / `make compilemessages` **do not work on Windows 11 + Docker Desktop**,
for two independent verified reasons:

1. The dev `web` service `depends_on` `load_catalog`, `redis` and `seed` — i.e. the whole
   `db → redis → migrate → load_cities → load_catalog → seed → web` chain is booted in order
   to serve a static string-extraction scan.
2. `uv run` inside a one-shot `run` container triggers a venv sync that fails with
   `Read-only file system` on `/opt/venv`.

Use the `mko-bazuna-dev` one-shot instead. `--no-deps` skips the dependency chain,
`--entrypoint ""` skips the DB-wait and the entrypoint's own `compilemessages`, and the venv
`python` is called directly.

```powershell
# Alias, copied once per session
$dev = 'docker compose --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.override.yml --project-name mko-bazuna-dev'

# Extract - the SAME flags as the Makefile target, plus --no-obsolete where BLOCK 10 adds it
$dev run --rm --no-deps --entrypoint "" web python src/backend/manage.py makemessages -l ru -l bs -l en --no-location

# Compile - .mo is gitignored; only needed manually after editing a .po
$dev run --rm --no-deps --entrypoint "" web python src/backend/manage.py compilemessages --ignore=.venv --ignore=.git --ignore=__pycache__ --ignore=*.pyc --ignore=node_modules --locale ru --locale bs --locale en
```

Requires `.env.dev` (copy `.env.dev.example`).

**Catalogue facts the implementor must hold:**

- Locales are **`ru`, `bs`, `en`** and nothing else. `LANGUAGES` is exactly those three.
- **`msgstr` must be non-empty for `ru` and `bs`.** `en` **may** stay empty — the `msgid` is
  English. This is the documented convention and two independent tests assert it.
- **`.mo` files are gitignored** (`*.mo`) and are compiled automatically at image build, at
  container start (`docker/entrypoint.sh` → `compilemessages`, non-fatal), and in the CI
  `i18n` job. **Never `git add` a `.mo`.**
- **`--no-location` is the documented convention** in both `Makefile` and
  `.kilo/rules/commands.md`, and it is what keeps the three catalogues diffable. Dropping it
  re-introduces `src/…:NNN` churn across ~408 entries and destroys reviewability.
- The i18n document of record is **`docs/01-spec/i18n-spec.md`** — **not**
  `docs/08-features/i18n.md`, which does not exist. Phase 08 already recorded that
  mis-citation.
- The gate is **`src/backend/apps/ads/tests/test_i18n_completeness.py`**, with the
  documented DB-based exemption for `components/feature_tag.html` → `get_lookup_name`.

### 1.3 Lint, typecheck, template lint

```powershell
uv run ruff check <path>              # lint one path
uv run ruff check --fix <path>        # auto-fix, INCLUDING import sorting (I001)
uv run basedpyright <path>            # typecheck
uv run djlint src/backend/templates/  # template lint
```

`ruff check --fix` handles import sorting. **Scope every command to the block's own file
list** — a blanket `ruff check --fix src/` reorders imports that another phase's
uncommitted work depends on, and `[tool.ruff] fix = false` is set deliberately.

### 1.4 Project rules the implementor must not negotiate

- **English only.** Every comment, log, docstring, error message, `msgid` and source string
  is English. **Bosnian and Russian exist only in `.po` `msgstr` values and in DB
  `name_i18n` columns — never in source.**
- **Production code is king.** If a test conflicts with architecture or business logic, fix
  or remove the test. `test_format_price_value_uses_intcomma` is the phase's live example:
  its docstring claims locale-aware grouping that the code does not deliver, so **the test
  follows the corrected behaviour**, not the reverse.
- **i18n is part of the Definition of Done** (project rule 16). A block that changes a
  user-visible string without a non-empty `ru` and `bs` `msgstr` is incomplete.
- **No `print()`.** Use `logger = logging.getLogger(__name__)`.
- **Django ORM is the persistence layer**; Pydantic v2 is a DTO/validation layer at system
  boundaries only (bot input, settings schemas, future API). Neither is relevant to this
  phase — **no block writes a model field, a serializer or a Pydantic model.**
- **Django 5.2 LTS** (`>=5.2.16,<6.0`), **Python 3.14**, **PostgreSQL 18**, **aiogram 3.x**.
- **Two processes, one DB.** Web (gunicorn sync WSGI, HTMX MPA) + bot (aiogram), sharing the
  ORM and the catalogue. `LOCALE_PATHS` serves both.
- **All schema changes via Django migrations.** This plan ships none.
- **Fixed values via `StrEnum`, never plain strings or dicts.** `LanguageLocale` is the model
  to follow; the phase's typing work is an *instance* of this rule, not an exception to it.
- **Small focused modules and functions; composition over inheritance; follow existing
  patterns; no speculative abstraction; no scope creep.**
- **Docs in `docs/` must stay in sync** with the code they describe.
- **Do not edit `src/backend/conftest.py`.** It is off-limits to *every* phase. There is an
  autouse `_reset_translation_state` fixture; do **not** add per-file `deactivate()` calls —
  they are redundant.
- **Never use a line number as a task target.** Use file path plus module / class / method /
  function / template / msgid. Every line anchor in the validated report has drifted (N-4).

### 1.5 One Implementor, strictly sequential, one commit per block

- **One Implementor at a time.** The block numbering in §3 **is** the serial order.
- **One commit per block.** Stage explicitly — `git add <specific files>`, never a
  directory — then `git commit -m "{type}({scope}): {description}"` in the repository's
  style.
- **Never `git reset`, `git checkout`, `git restore` or `git stash`. Never rewrite history.**
- **Other agents are working in parallel. Changes you did not make are normal.** Do not
  revert, "clean up" or comment on another phase's uncommitted work.
- **No commit without an explicit user request** beyond the per-block instruction.
- **A gated block does not start until its answer is written down.** The Implementor is
  **forbidden from choosing an option** (§0.5). Silence is not an acceptable outcome: a
  declined gate is recorded with its reason.

### 1.6 The `.po` write contract — binding on BLOCKS 9, 10, 11 and 13

1. **Re-read all three `.po` files immediately before the `makemessages` invocation.** Six
   other phases are appending to them. A read taken at the start of the block is stale.
2. **Re-read them again immediately before `git add`.** Another phase may have landed
   between the extraction and the commit.
3. **Never regenerate wholesale.** `makemessages` rewrites all three in place. If another
   phase's strings are missing from the result, **restore and report — do not commit a
   catalogue that silently deleted a concurrent phase's work.**
4. **`--no-obsolete` deletes entries by design.** BLOCK 10 is the single most dangerous
   operation in the phase. Before invoking it, **record the exact set of entries that will
   disappear** (parse, do not eyeball) and confirm each one is either a reworded string
   whose replacement is present, or a genuine orphan. **Six obsolete entries already exist
   in `ru` and `bs` and zero in `en` (N-2) — the catalogues are not obsolete-symmetric, and
   the asymmetry is what BLOCK 10 resolves and BLOCK 11 asserts.**
5. **Never add a `.mo` file.** They are gitignored.
6. **Any new msgid is English.** Never a Russian or Bosnian source string.
7. **`ru` and `bs` `msgstr` must be non-empty** for every new entry, in the same commit.
8. **A gate that goes red because a concurrent phase's strings are missing is a race, not a
   defect.** Re-read the catalogues, re-run, and only then report.

### 1.7 Test authoring standard for every block

Tests verify **logic and component interaction**, not trivial implementation details.

| Rule | Why |
|---|---|
| **Assert on accessors and rendered values, never on a function's private internals** | A test that asserts a private helper's shape breaks on every refactor and detects nothing |
| **Never assert on gettext chrome text for an unsupported locale** | ✔ `VAL-003` (§0.2.2 item 1). This is the phase's headline test-shape constraint |
| **Parametrised multi-language tests use `LanguageLocale.values()`**, never bare string literals | Project rule 10 |
| **Unit tests use the `translation.override(lang)` context manager** | Automatic rollback even on exception |
| **Integration tests set the language through the middleware's documented priority order** — `?lang=X` or the `Accept-Language` header. **Never** call `translation.activate()` before `client.get()`; the middleware overrides it. Where the URL carries meaningful query params, prefer the header | `docs/99-agent/rules.md`, "i18n / Language Testing" |
| **New tests live in the existing per-finding test modules**, never in `conftest.py` | `conftest.py` is off-limits to every phase |
| **Every new guard must be demonstrated failing** | A guard that has never been observed red is an unverified assertion |
| **Never hard-code a file count, a msgid count or a template count** | C-2: the report's "43 templates" is 38. Derive the expectation from the collector |

### 1.8 Task shape

Every block's Implementor task follows `.ai\tasks\templates\task_template.yaml`: semantic
`targets` with `type`/`name`, `semantic_anchors`, `changes`, `acceptance_criteria`,
`source_reference` / `source_section` / `source_blocks`, and an `extra_context` block
carrying the binding constraints **verbatim**.

- **Never a line number as a target.**
- `extra_context` carries the full constraint list, the verified symbol map, and the
  hazards from §0.2.2 — copied, not summarised.
- `acceptance_criteria` is an acceptance contract: each item is checkable by running
  something.

---

## 2. Scope decisions table (acceptance contract for execution)

`mechanical` = no observable behaviour change, no outcome-changing gate, safe to batch or run
without a Validator. `behavioural` = changes an observable response, touches a shared
contract, breaks a shipped test, or is gated. `structural` = introduces a contract or a
source of truth. `conditional` = ships a reduced deliverable if its gate is declined.

| ID | Class | Disposition | Block | Severity | One-line reason |
|---|---|---|---|---|---|
| `I18N-001` | **structural** | **implement in two commits — BLOCK 1 (the resolver) then BLOCK 2 (the type boundary).** Route all three locale sources through one normalising resolver; then tighten the five accessors and five filters to `LanguageLocale` | **1**, **2** | **HIGH (P0)** | A cookie whose `to_language()` form is not exactly `ru`/`bs`/`en` — i.e. the overwhelming majority of real BCP-47 tags — makes every DB-backed string fall through `locale → ru → name` to Russian, site-wide. **No mitigation exists**: no `LocaleMiddleware`, no `set_language` view, no `LANGUAGES` clamp in `translation.activate()`. The site never writes such a value itself, so the trigger is an externally-written cookie — which `I18N-011`'s missing `SameSite` enables. Harm is content-legibility, not data exposure |
| `I18N-002` | **mechanical** | **implement as defence-in-depth inside BLOCK 1** | **1** | LOW | Fully subsumed by `I18N-001`: once normalised there are exactly three possible key segments, so the unbounded cardinality is an artefact of `I18N-001`, not an independent defect. What survives is that the key is built from a raw request attribute that never passed through the enum. The report's own recommendation concedes it |
| `I18N-003` | **behavioural** | **implement — gated on Q3, and the grouping decision ships in the same change** | **3** | **HIGH (P0)** | `_format_amount` stringifies the `Decimal` and passes a **`str`** to `intcomma`, whose `str` path does `int(value)` → `ValueError` on any fractional amount → a `use_l10n=False` recursion that hard-codes `,` and leaves the `.` decimal mark. Integer amounts survive, which is why round prices hide it. **✔ But the one-argument fix restores the decimal mark for `bs` and not the grouping** (`VAL-004`), so a plan that ships only the argument change introduces a *new* visible `ru`/`bs` inconsistency |
| `I18N-004` | **behavioural** | **implement — `Q4` RESOLVED 2026-10-03. `.po`-free. Hard-coded `TIME_ZONE = "Europe/Podgorica"`, NOT env-overridable** | **5** | MEDIUM (↓HIGH) | `TIME_ZONE` is absent from **every** settings module, so Django's `America/Chicago` applies to a Balkan marketplace, and all four user-visible date renderings hardcode `'M d, Y'` / `'M d'` / `'M d, H:i'`. `USE_TZ` is `True` (Django 5 default), so this is **presentation-only — no naive/aware integrity class**. For an ad published between 00:00 and 07:00 local the **calendar day itself** is wrong. **No `ALLOWED_ENV_VARS` entry and no `.env*.example` lines — the allowlist collision disappears entirely**, and **no other phase's allowlist work is triggered** |
| `I18N-005` | **structural** | **implement — BLOCK 7, before BLOCK 11** | **7** | MEDIUM | `_parse_po_entries` overwrites its accumulator on every `msgstr`-prefixed line **including `msgstr[N]`**, keeping only the last form, while its docstring claims the first. Both copies of `test_no_empty_msgstr` then ask a question that is only ever about the last form. **Latent**: `ru`/`bs` have 0 plural entries with any empty form today. **BLOCK 11's credible stale-entry gate needs this parser** — hence the strict ordering edge |
| `I18N-006` | **behavioural** | **implement — gated on Q9 (a pre-block Auditor step)** | **8** | MEDIUM | Both collectors hard-code subdirectories instead of walking `src/telegram_bot` and excluding `tests/`. The unscanned set is `__init__.py`, `lifecycle.py`, `main.py`, `retry.py`, `states.py`, `middlewares/*` (5), `schemas/*` (4) — and `middlewares/language.py`, where the locale is actually activated for every update, is in it. `lifecycle.py` proves the surface is reachable: twelve `BotCommand` literals |
| `I18N-007` | **mechanical** | **implement with `I18N-006` in one collector pass** | **8** | MEDIUM | `_collect_template_files` iterates `TEMPLATES["DIRS"]` and never consults `APP_DIRS`, which is `True`. **Latent today** — the only roots on disk are `src/backend/templates` (38 files) and an empty `src/templates`. The natural modular-Django refactor silently removes a template from the i18n gate and **nothing detects the loss** |
| `I18N-008` | **mehavioural** → **mechanical** | **implement with the same pass** | **8** | MEDIUM | `test_hreflang_present` renders `components/locale_head.html` **in isolation** and never inspects a page template, while its docstring claims the partial is "included by every page template". All 15 page templates do include it today — **a coverage gap, not a live defect**. The gate reads as if the site-wide property were enforced |
| `I18N-009` | **behavioural** | **implement — gated on Q5, a phase-06 boundary** | **6** | MEDIUM | The switcher's JS writes `lang_pref` only inside `{% if consent_preferences %}`; the middleware writes the same cookie unconditionally whenever `?lang=` was supplied. Neither site references the other. **Extended:** the client helper sets `SameSite=Lax` and the server sets none, so the two writers disagree on more than the gate — and the weaker one lands last. The template implies a consent-gated cookie while the server sets it for everyone |
| `I18N-010` | **behavioural** | **implement — after BLOCK 3** | **4** | MEDIUM | The chip renders raw `Decimal`s through `{% blocktrans %}`, which applies no filter chain, so `1000.50` appears with an ASCII point, no grouping and no currency code — directly above a correctly formatted card price **in the same response**. The gate cannot catch it: the text *is* wrapped. The remedy is the pattern already used fourteen lines below the defect |
| `I18N-011` | **mechanical** | **implement inside BLOCK 6 — after `I18N-009`** | **6** | LOW | `lang_pref` is the only cookie the project issues that opts out of all six `SESSION_COOKIE_*` / `CSRF_COOKIE_*` attributes the project sets elsewhere. Confidentiality impact is nil (a three-value code); the integrity impact is that the absent `SameSite` makes it a candidate for cross-site overwrite — which, per `I18N-001`, is sufficient to change a visitor's rendered language. `httponly=True` is only safe once the client writer is gone |
| `I18N-012` | **mechanical (doc only)** | **implement the docstring correction inside BLOCK 6. Do NOT touch the header** | **6** | LOW | The finding was reclassified to `DOC-UPDATE` **because the code is already correct**: `CsrfViewMiddleware` adds `Vary: Cookie` on any response whose template calls `get_token()`, and every page does, so a `Vary`-honouring cache already keys on the cookie. The auditor's probe measured the wrong stack. What remains is that the **docstring is factually wrong** and the property is **incidental** — `ads/partials/ad_list.html` and `categories/partials/mega_submenu.html` render no CSRF token |
| `I18N-013` | **mechanical (documentation only)** | **✅ RESOLVED 2026-10-03 — Option A. Model `verbose_name` / `help_text` is documented as an explicit, named exemption in the i18n coverage rule.** **BLOCK 12 is now the SOLE home of `I18N-013`** · **BLOCK 13 is CANCELLED** · **no catalogue growth** · the admin tests asserting English field text **stay unchanged** | **12** only (**13 CANCELLED**) | LOW | ✔ 20 `verbose_name` + **172** `help_text` (C-3), 0 `gettext_lazy`, 0 gettext imports in any `models.py`. **Staff-only** — no buyer or seller sees it. Option A is S and makes the coverage claim accurate; Option B (wrapping ~192 entries) is M, would grow the catalogue by ~192, and would require reviewing admin tests that assert English field text. **The Product Owner chose Option A and DECLINED Option B on 2026-10-03** |
| `I18N-014` | **mechanical + behavioural** | **implement in two commits — BLOCK 10 (the `--no-obsolete` flags and the one-shot prune) then BLOCK 11 (the durable reverse gate). BLOCK 10 must land after BLOCK 7** | **10**, **11** | LOW | Six msgids are present as **active** entries in all three catalogues and absent from extraction. Runtime impact is nil; the cost is that translators spend time on strings that never render and a reviewer grepping a `.po` can be misled into believing a code path is translated. **Method constraint: the sixth is a wrapped multi-line `msgid` — a line-anchored regex misses it, and a literal-substring source scan over-reports (47 false positives in the Auditor's cross-check). The gate must parse both sides.** ✔ **Strengthened by N-2**: six `#~` entries already exist in `ru`/`bs` and zero in `en`, and nothing gates it |
| `I18N-015` | **behavioural** | **implement inside BLOCK 1 — one shared resolver** | **1** | LOW | `_parse_accept_language` takes `split(",")[0]` and returns the fallback immediately, so `de-DE,ru;q=0.8,bs;q=0.6` resolves to `bs`, skipping the `ru` the user ranked above Bosnian. The spec is **silent on q-values**, so this is a spec gap as much as a code gap — BLOCK 12 states the rule either way |
| `VAL-001` | — | **NOT ACTIONED — stale, already fixed at the anchor** | — | CRITICAL (as filed) | ✔ C-1. `RUN_TRANSLATION_BACKFILL` is in `ALLOWED_ENV_VARS` and a reverse-direction whole-tree gate exists. Actioning it would produce a false reopening of `CFG-008` |
| `VAL-002` | — | **NOT ACTIONED — still stale; procedural closure only** | §6.2 | MEDIUM | ✔ The function contains no `isalpha()`; it strips only control characters and truncates to 100 chars, so Cyrillic, Serbian Latin diacritics and digits all pass through. The phase-08 premise no longer holds. The residual is closing the phase-08 deferral and correcting the phase-08 advisory — **phase 08's surface, not a code change here** |
| `VAL-003` | **advisory → constraint** | **implement as a binding constraint on BLOCK 1's and BLOCK 2's test shape** | **1**, **2** | LOW | ✔ `base.py` is `ru`, `test.py` is `en`. Django's `_add_fallback` makes the gettext chrome for an unsupported locale **Russian in production and English under test for the identical request**, while the DB accessors behave identically in both. **A chrome assertion passes in CI and production is still wrong** |
| `VAL-004` | **advisory → gate** | **folded into `I18N-003` as `Q3`, shipped in the same change** | **3** | LOW | ✔ Django's `bs/formats.py` leaves `NUMBER_GROUPING` commented out and `numberformat.py` gates on `grouping != 0`, so grouping is **structurally unreachable for `bs` even under `force_grouping=True`**. No project-level `FORMATS` override exists. Django's bundled locale data is a third-party package and cannot be edited |
| **N-1** (new) | **mechanical + conditional** | **implement the detection rule unconditionally; the string correction stays gated on Q1, which is `OPEN-PENDING-REVIEWER`** | **9** | MEDIUM | ✔ One `bs` `msgstr` ends `"Za kreiranje oglasа користи /post."` — a Croatian/Bosnian frame with the **Russian verb** `користи` and a **Cyrillic "а"** inside `oglasa`. It is the only Cyrillic-bearing line in the `bs` catalogue and it renders to every Bosnian user. **No gate catches it**, and the reason is written into the gate itself: `test_no_cyrillic_msgids`'s docstring says *"`msgstr` values for ru/bs are naturally Cyrillic and exempt"* |
| **N-2** (new) | **mechanical** | **implement the prune in BLOCK 10 and the assertion in BLOCK 11** | **10**, **11** | LOW | ✔ Obsolete entries are **6 (`ru`) / 6 (`bs`) / 0 (`en`)**. `test_pot_creation_date_sync` compares only the `POT-Creation-Date` header, so the asymmetry is ungated and the three catalogues disagree about their own history |
| **N-3** (new) | **mechanical** | **implement in BLOCK 12 — gated on Q11** | **12** | LOW | ✔ `i18n-spec.md` has **3 dead link targets referenced 5 times**: `../99-agent/i18n-translation-pipeline-gap-analysis.md` (×3), `../99-agent/i18n-definition-of-done-research.md` (×1), `../96-researches/i18n-translation-egress.md` (×1). **The whole `docs/96-researches/` directory does not exist** |
| **N-4** (new) | **mechanical** | **implement in BLOCK 12, and as a standing rule in §1.4** | **12** | LOW | ✔ `i18n-spec.md` carries stale line citations, and **every line anchor in the validated report has drifted**. No task in this plan uses a line number as a target |
| **Q1** / **Q2** | — | **`Q1` RULED 2026-10-03, gate `OPEN-PENDING-REVIEWER` · `Q2` RESOLVED 2026-10-03 (Option A)** | **9**, **12** | — | **Q1 is the outstanding human deliverable**: the Product Owner ruled on 2026-10-03 that a native (preferably Montenegrin) reviewer signs off the three `bs` strings and that machine output and translation APIs are not acceptable — but **no sign-off exists yet, so the gate is `OPEN-PENDING-REVIEWER`, not closed**, and BLOCK 9 ships its reduced deliverable. **Q2 is closed**: Option A, BLOCK 12 sole home, **BLOCK 13 CANCELLED**. **✔ Q1 and Q2 remain independent** — the code context's claim that Q2's Option A removes two of the three strings is not supported by the tree (C-5): `Moderator #%(mid)s` is in an **already-exempt template** and `I18N-013` is about a different surface. Q1's ruling does not release it |
| **Q3** / **Q4** / **Q5** | — | **`Q3` GATED · `Q4` RESOLVED 2026-10-03 · `Q5` GATED (phase-06 boundary)** | **3**, **5**, **6** | — | **Q4 is closed**: hard-coded `Europe/Podgorica`, not env-overridable, no allowlist work. **Q3 and Q5 are untouched by the 2026-10-03 round and remain open.** **Q5 is a phase-06 boundary** and also gates `I18N-011`'s `httponly=True` |
| **Q6** / **Q8** / **Q9** / **Q11** | — | **PRE-BLOCK STEP** (Q6, Q9) / **PLANNER RULING** (Q8) / **GATED** (Q11) | **2**, **8**, **12** | — | Q6: the Auditor enumerates every consumer of `context_processors.language` before BLOCK 2. Q9: the Auditor runs the widened collector before BLOCK 8. Q8: resolved — the obsolete assertion belongs in `I18N-014`, not as a separate item |
| **Q7** / **Q10** | — | **RESOLVED (no change)** / **ROUTED** | — | — | Q7: the `en` empty-`msgstr` convention is already correct and is recorded so nothing "helpfully" fills it. Q10: the backfill target-language matrix is unowned and belongs to phase 09 |

**Block classification summary:** `mechanical` = **8, 10, 12, 13** · `behavioural` = **3, 4, 5, 6, 8**
· `structural` = **1, 7** · `conditional` = **9** (reduced deliverable, pending `Q1`'s reviewer
sign-off). **BLOCK 13 is CANCELLED as of 2026-10-03** (`Q2` → Option A) and its rows appear below
only so the cancellation is on the record — **no implementor runs it and no commit exists for it.**

---

## 3. Execution blocks

Thirteen blocks. **One Implementor, strictly sequential, one commit per block** (§1.5). The
numbering *is* the serial order, chosen so that the contended files are written as few times
as possible and so that no block depends on a decision that has not been made:

```
apps/core/middleware/language.py   1 → 6                  (the file BLOCK 5 must not touch)
apps/ads/templatetags/price_tags.py 3 → 4                 (the chip reuses the corrected helper)
testing/i18n_helpers.py            7 → 11                (the parser BLOCK 11's gate depends on)
test_i18n_completeness.py          8 → 9 → 11            (collectors, then the msgstr gate, then the reverse gate)
locale/{ru,bs,en}/…/django.po      10 → 9 → 11 → 13     (prune, then gate+strings, then assertions, then Option B)
config/settings/base.py            3(opt a) → 5           (both six-way contended; both re-read)
docs/01-spec/i18n-spec.md          12 only                (the spec is written once, after the behaviour)
```

**Six blocks carry a labelled *decision required before implementation* gate (BLOCKS 3, 5, 6,
9, 12, 13).** A gated block does not start until the answer is written down; the Implementor
is **forbidden from choosing an option** (§1.5, §8.1). Two carry an explicit **pre-block
Auditor step** (BLOCKS 2 and 8) instead of a gate, because the answer is a measurement, not
a preference.

---

### BLOCK 1 — One locale resolver for all three sources (`14-I18N-001` limb 1, `14-I18N-015`, `14-I18N-002`)

| | |
|---|---|
| **Findings owned** | `I18N-001` (HIGH, first limb), `I18N-015` (LOW), `I18N-002` (LOW, defence-in-depth) |
| **Class** | **structural** — introduces a single source of truth for the resolved locale |
| **Depends on** | nothing in-plan |
| **Blocks** | BLOCK 2, BLOCK 6, BLOCK 12 |
| **Priority** | **P0.** First because every other locale finding is either weaker without it or depends on it |
| **Risk level** | **HIGH** — the phase's headline fix, and the one whose test can silently be wrong |
| **Blast radius** | `LanguagePreMiddleware` is the **sole locale authority** in the stack. Every DB-backed string on every page flows through it |
| **Required agents** | **Auditor · Researcher · Planner · Validator — all four**, because a false-green regression test here ships the phase's most important fix wrong and nothing else in the repository would catch it |

**Why this is one block and not three.** The three findings share a root cause and a single
seam: one resolver, one call site, one enum. Splitting them would produce three commits each
leaving the resolver half-built, and a Validator could not tell which state the tree was in.

**Scope correction.** The report's `I18N-001` evidence table is wrong for two rows, and the
correction changes what the fix must do. It fed raw cookie strings straight to the accessors,
but **the real request path passes `translation.get_language()`** (Django's `to_language()`,
which lower-cases and hyphen-normalises), so `cookie=EN` resolves to `en` and the DB content
comes out **English, not Russian**. The mechanism is real; the two rows were wrong.

**File surface (semantic units)**

| File | Symbol | What changes |
|---|---|---|
| `src/backend/apps/core/middleware/language.py` | `LanguagePreMiddleware.process_request` | The raw cookie branch stops calling `_set_language_code` with the raw string |
| | `LanguagePreMiddleware._set_language_code` | Becomes the single sink every source routes through, and normalises there |
| | `LanguagePreMiddleware._parse_accept_language` | `split(",")[0]` → a `(tag, q)` scan that drops `q=0`, sorts descending, and returns the first tag that maps to a configured locale before falling back (`I18N-015`) |
| | the module docstring | Records the priority chain and the normalisation guarantee, which it currently claims but the cookie branch does not honour |
| `src/backend/apps/categories/views.py` | `category_submenu` — the `category:submenu:<tree_version>:<slug>:<locale>` f-string | Build the locale segment through `LanguageLocale.from_code(...)` rather than from the raw request attribute (`I18N-002`, defence-in-depth) |
| `src/backend/apps/core/tests/test_language_middleware.py` | `test_cookie_valid_values` and the priority table | Grows from canonical-only to the non-canonical cookie cases that are currently absent |

**The single mechanism the fix must establish:** all three sources — `?lang=`, the
`lang_pref` cookie, and `Accept-Language` — pass through **one** resolver that yields a
`LanguageLocale` member, and that member is what reaches `translation.activate()` and
`request.LANGUAGE_CODE`. There is no fourth path.

**Binding constraints**

1. **✔ `VAL-003` — assert on accessors, never on chrome.** `config/settings/base.py` sets
   `LANGUAGE_CODE = "ru"`; `config/settings/test.py` sets `"en"`. Django's `_add_fallback`
   adds `settings.LANGUAGE_CODE` as a catalogue fallback for any activated language that is
   not `en*`, so **the same request renders Russian chrome in production and English chrome
   under test**, while the DB accessors behave identically in both. **A regression test that
   asserts on rendered chrome for an unsupported cookie locale will pass in CI and
   production will still be wrong.** The new cookie cases must assert on
   `Category.get_name` / `City.get_name` / `Ad.get_title` — the default-independent surface —
   **or** pin `LANGUAGE_CODE` explicitly with `override_settings`. Never chrome.
2. **Do not add `LocaleMiddleware`, a `set_language` view, or `i18n_patterns`.** The module
   docstring explains why `LocaleMiddleware` is intentionally absent: it would re-derive the
   language from the never-set `django_language` cookie plus `Accept-Language`, clobbering
   the resolved value and ignoring both `?lang=` and `lang_pref`. Any "just use
   `LocaleMiddleware`" shortcut re-opens that.
3. **There are three distinct locale authorities and this block touches only the first.**
   Per-request web locale is `request.LANGUAGE_CODE` (this block). Per-user Telegram locale
   is `User.telegram_language`, defaulting to `ru` (the bot's own `LanguageMiddleware` — **not
   in scope**). A third, `SavedSearch.language`, selects **which FTS vector** a saved search
   matches and does **not** affect message text. Conflating them is the easiest way to write
   a wrong fix.
4. **`request.LANGUAGE_CODE` must be a member of `settings.LANGUAGES` after this block** —
   assertable in the priority table for every input, including the hostile ones.
5. **The cookie's write path is BLOCK 6's, not this block's.** `_apply_lang_param` continues
   to persist only the resolved canonical code. Do not add, remove or change `set_cookie`
   here.
6. **Do not touch the five model accessors or the five template filters.** That is BLOCK 2,
   and BLOCK 2's gate (Q6) may widen the surface.
7. **The `<time datetime="…">` ISO attributes and every `Vary` header are untouched.** Those
   are BLOCK 5 and BLOCK 6's territory, and BLOCK 6 in particular is forbidden from adding a
   `Vary` header.
8. **Re-read `language.py` immediately before editing.** No other phase claims it, but
   `.ai/audit/**` and `.ai/plans/**` in this repository show concurrent-agent drift is
   routine, and the file is the phase's most important one.
9. **Run the full i18n gate including `test_i18n_category_city.py` before starting** (§0.2.3
   item 9 — the five DB-backed tests were never run during the audit). Record the observed
   per-locale symptom table in the commit body, before and after.

**Implementor task**

```yaml
id: task_14_b01_locale_resolver
title: "Route all three locale sources through one normalising resolver (14-I18N-001, 14-I18N-015, 14-I18N-002)"
priority: high
depends_on: []
source_reference: ".ai/plans/14-i18n-remediation.md"
source_section: "BLOCK 1 - One locale resolver for all three sources"
source_blocks: ["BLOCK 1"]
description: >
  LanguagePreMiddleware is the only locale authority in the stack. It normalises the ?lang=
  query parameter and the Accept-Language header, but the lang_pref cookie branch passes the
  raw cookie string straight to _set_language_code and on to translation.activate(), which
  neither consults settings.LANGUAGES nor normalises. Any cookie whose to_language() form is
  not exactly ru/bs/en - which is the overwhelming majority of real BCP-47 tags - drives every
  DB-backed string through the locale -> ru -> name chain to Russian, site-wide. Separately,
  _parse_accept_language inspects only the first tag of Accept-Language, so a supported
  lower-ranked tag is skipped, and the submenu cache key is built from the raw request
  attribute rather than from a value that has passed through the LanguageLocale enum.
goals:
  - "one resolver yields a LanguageLocale member from all three sources; request.LANGUAGE_CODE is always a member of settings.LANGUAGES"
  - "Accept-Language honours descending q-values, drops q=0, and picks the first supported tag before falling back"
  - "the submenu cache-key locale segment is built through LanguageLocale.from_code"
  - "add the non-canonical cookie regression cases that are currently absent from the priority table"
extra_context: |
  BINDING CONSTRAINTS (verbatim, from section 3 BLOCK 1)
  1. VAL-003 - ASSERT ON ACCESSORS, NEVER ON CHROME. base.py sets LANGUAGE_CODE="ru";
     test.py sets "en". Django's DjangoTranslation._add_fallback adds
     settings.LANGUAGE_CODE as a catalogue fallback for any activated language that is not
     en*, so the same request renders Russian chrome in production and English chrome under
     test, while the DB accessors behave identically in both. A chrome assertion for an
     unsupported cookie locale passes in CI and production is still wrong. Assert on
     Category.get_name / City.get_name / Ad.get_title, or pin LANGUAGE_CODE explicitly with
     override_settings.
  2. Do not add LocaleMiddleware, a set_language view, or i18n_patterns. LocaleMiddleware is
     intentionally absent: it would re-derive the language from the never-set
     django_language cookie plus Accept-Language, clobbering the resolved value and ignoring
     both ?lang= and lang_pref.
  3. Three distinct locale authorities. This block touches ONLY the per-request web locale
     (request.LANGUAGE_CODE). The per-user Telegram locale (User.telegram_language, default
     ru, activated by src/telegram_bot/middlewares/language.py) is OUT OF SCOPE. A third,
     SavedSearch.language, selects which FTS vector a saved search matches and does not
     affect message text.
  4. request.LANGUAGE_CODE must be a member of settings.LANGUAGES after this block,
     assertable in the priority table for every input including the hostile ones.
  5. The cookie WRITE path is BLOCK 6's. _apply_lang_param continues to persist only the
     resolved canonical code. Do not add, remove or change set_cookie here.
  6. Do not touch the five model accessors (Category.get_name, City.get_name,
     LookupItem.get_name, Ad.get_title, Ad.get_description) or the five localized_content
     template filters. That is BLOCK 2, and its Q6 gate may widen the surface.
  7. The two <time datetime="...|date:'Y-m-d'"> ISO attributes and every Vary header are
     untouched (BLOCKS 5 and 6).
  8. Re-read language.py immediately before editing.
  9. Run the full i18n gate INCLUDING test_i18n_category_city.py before starting. Those five
     DB-backed tests were never run during the audit and are the only DB-backed i18n
     evidence in the phase. Record the observed per-locale symptom table in the commit body,
     before and after.
  VERIFIED SYMBOL MAP (re-derived at d42f778; use symbols, never line numbers)
  - src/backend/apps/core/middleware/language.py -> class LanguagePreMiddleware, methods
    process_request, process_response, _apply_lang_param, _set_language_code,
    _parse_accept_language; module constants LANGUAGE_COOKIE_NAME, LANGUAGE_COOKIE_MAX_AGE
  - the raw cookie branch is inside process_request and reads request.COOKIES
  - _parse_accept_language currently does accept_language.split(",")[0] and returns
    LanguageLocale.from_code(first_tag, fallback=LanguageLocale.BOSNIAN).value immediately
  - src/backend/apps/categories/views.py -> view category_submenu; the key is
    f"category:submenu:{get_tree_version()}:{category.slug}:{request.LANGUAGE_CODE or 'ru'}"
  - src/backend/apps/core/enums.py -> LanguageLocale (StrEnum: RUSSIAN="ru", BOSNIAN="bs",
    ENGLISH="en"), with .from_code, .values, .fts_config, .fts_vector_field
  - src/backend/apps/core/tests/test_language_middleware.py -> test_cookie_valid_values and
    the priority table; today it exercises only ("ru", "bs", "en") for the cookie
  FORBIDDEN: editing src/backend/conftest.py; editing any .po file; adding LocaleMiddleware;
  changing set_cookie; touching the model accessors; adding a Vary header.
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
    changes: []  # extend the table; do not weaken any existing assertion
  - path: docs/01-spec/i18n-spec.md
    targets: []   # READ ONLY in this block. BLOCK 12 writes it.
    changes: []
changes:
  - action: add_code
    description: >
      Add one resolver on LanguagePreMiddleware that every locale source routes through:
      the ?lang= query parameter, the lang_pref cookie and the Accept-Language header all
      yield a LanguageLocale member, and that member is what reaches translation.activate()
      and request.LANGUAGE_CODE. The cookie branch currently passes the raw cookie string.
  - action: add_code
    description: >
      Replace the split(",")[0] in _parse_accept_language with a (tag, q) scan: parse each
      comma-separated member with its q parameter, drop q=0, sort by descending q, and return
      the first tag that maps to a configured locale, only then falling back.
  - action: add_code
    description: >
      Build the submenu cache-key locale segment through
      LanguageLocale.from_code(request.LANGUAGE_CODE, fallback=LanguageLocale.RUSSIAN).value
      instead of the raw request attribute.
  - action: add_test
    description: >
      Add non-canonical cookie cases to test_language_middleware.py - at minimum en-US, EN,
      en_US, de-DE, ru-RU and xx - each asserting that the resolved locale is a member of
      settings.LANGUAGES AND that the model accessor returns that locale's value, not the ru
      fallback. Add q-valued Accept-Language cases including
      "de-DE,ru;q=0.8,bs;q=0.6" and a q=0 exclusion case. The existing canonical cases must
      keep passing unchanged.
acceptance_criteria:
  - "for every cookie value in the table, including the non-canonical ones, request.LANGUAGE_CODE is a member of settings.LANGUAGES"
  - "the non-canonical cookie cases assert on Category.get_name / City.get_name / Ad.get_title, never on rendered chrome (VAL-003)"
  - "Accept-Language: de-DE,ru;q=0.8,bs;q=0.6 resolves to ru, not bs"
  - "an Accept-Language member with q=0 is not selected"
  - "the submenu cache key's locale segment is in {ru, bs, en} for every request in the table"
  - "every pre-existing test in test_language_middleware.py still passes unchanged"
  - "no LocaleMiddleware, set_language view or i18n_patterns was added"
  - "no .po file was touched by this block"
  - "the commit body records the before-and-after per-locale symptom table, and names the
     specific assertion strategy used to avoid the VAL-003 false green"
```

**Why the split from BLOCK 2 is deliberate.** BLOCK 1 normalises the value; BLOCK 2 makes the
type enforce it. Doing the typing first leaves a window where both are half-done — a
signature that promises `LanguageLocale` while the cookie still delivers a raw `str`. The
report is explicit that the accessor typing is the only structural item in the phase and
**should be sequenced after the middleware fix so the normalisation is in place first**.

---

### BLOCK 2 — The type boundary: `LanguageLocale` at the five accessors and five filters (`14-I18N-001` limb 2)

| | |
|---|---|
| **Findings owned** | `I18N-001` (HIGH, second limb) |
| **Class** | **structural** — the phase's only type-boundary change |
| **Depends on** | **BLOCK 1** (strict — normalisation must exist first) |
| **Blocks** | BLOCK 12 |
| **Priority** | **P0**, immediately after BLOCK 1 |
| **Risk level** | **HIGH** — the widest call-graph change in the phase, and Q6 may widen it further |
| **Blast radius** | Five model accessors, five template filters, and possibly `apps/core/context_processors.py` — which several other phases' templates read |
| **Required agents** | **Auditor · Researcher · Planner · Validator — all four**, because the surface is graph-shaped and the typing choice is reversible in one direction only |

**Pre-block step (Q6), not a preference gate.** The Auditor must enumerate **every** consumer
of `apps.core.context_processors.language` and of the five `localized_content` filters before
this block starts, and report them. The options are:

| Option | Change | Maintainability / future evolution | Project convention |
|---|---|---|---|
| **(a)** | The context processor emits a `LanguageLocale`; the filters take `LanguageLocale` | Strongest: a bad locale is impossible at the boundary, and `basedpyright` catches every call site. Widest surface — every template passing `|get_city_name:LANGUAGE_CODE` now depends on the context value's type | Aligns with project rule 10 (`StrEnum` for fixed values) and rule 9 (type safety) |
| **(b)** | The accessors accept `str \| LanguageLocale` and normalise internally | Narrowest surface, no template churn, no `context_processors` edit. **Weaker**: it re-implements normalisation at a second site, which is exactly the `I18N-001` root cause in miniature, and it keeps the "any `str` may reach the catalogue" shape alive | Weaker against rules 9 and 10; more consistent with "follow existing patterns" |

**This plan does not choose.** BLOCK 2 is written so that either option can be implemented;
the gate's answer, with its reason, goes in the commit body.

**File surface (semantic units)**

| File | Symbol |
|---|---|
| `src/backend/apps/categories/models.py` | `Category.get_name` |
| `src/backend/apps/locations/models.py` | `City.get_name` |
| `src/backend/apps/lookups/models.py` | `LookupItem.get_name` |
| `src/backend/apps/ads/models.py` | `Ad.get_title`, `Ad.get_description` |
| `src/backend/apps/core/templatetags/localized_content.py` | `get_title`, `get_description`, `get_lookup_name`, `get_category_name`, `get_city_name` |
| `src/backend/apps/core/context_processors.py` | `language` — **in scope only under Q6 option (a)** |

All ten are currently typed `locale: str = LanguageLocale.RUSSIAN`. **The default is already
a `LanguageLocale` member, so tightening the annotation is consistent with what the code
already does at runtime** — which is the strongest argument for (a).

**Binding constraints**

1. **Preserve the fallback chain exactly**: `locale → ru → name` for `Category`, `City` and
   `Ad`; `locale → ru → slug` for `LookupItem` (it ends at `slug`, not `name`). Tightening the
   type must not reorder or remove a rung.
2. **Do not change the accessors' behaviour.** A bad locale must still degrade to Russian —
   deliberately, and now by a route the type system documents rather than by accident. The
   difference is that the *source* of the value changes, not the fallback.
3. **`LookupItem.get_name` ends at `slug`, not `name`.** It is the one accessor with a
   different terminal rung; a "uniformity" edit that makes it fall back to `name` is a
   regression.
4. **The default parameter must remain `LanguageLocale.RUSSIAN`.** Do not "improve" the
   default to `None` or to a locale guessed from the thread.
5. **No template may be edited to work around the typing.** Templates call
   `|get_city_name:LANGUAGE_CODE`; if the type changes, the **context processor** changes,
   not the template. Thirty-eight templates are in scope for a change here and that is the
   wrong surface.
6. **Do not touch `src/telegram_bot/middlewares/language.py`.** The bot's per-user locale is
   a different authority (BLOCK 1 constraint 3).
7. **`basedpyright` must reach 0 errors on the changed paths.** A type change that leaves the
   typechecker reporting errors is not finished.
8. **The `VAL-003` constraint still applies to the tests** added here: assert on the
   accessor's returned value, never on chrome.
9. **The DB-backed assertions belong in `test_i18n_category_city.py`** (5 tests,
   `django_db` + `integration`) — the module that was never run during the audit and that
   already exists for exactly this surface. Do not create a new test module and do not touch
   `conftest.py`.

**Implementor task**

```yaml
id: task_14_b02_accessor_typing
title: "Tighten the five model accessors and five template filters to LanguageLocale (14-I18N-001 limb 2)"
priority: high
depends_on: [task_14_b01_locale_resolver]
source_reference: ".ai/plans/14-i18n-remediation.md"
source_section: "BLOCK 2 - The type boundary"
source_blocks: ["BLOCK 2"]
description: >
  Normalising the locale in the middleware (BLOCK 1) stops the bad value at the source, but
  the five model accessors and five template filters still accept an arbitrary str and do an
  exact dict-key test against it, with name_i18n["ru"] as the next rung. Tightening them to
  LanguageLocale makes a bad locale degrade to Russian deliberately and makes the typechecker
  flag every call site that can still deliver a raw string. This is the only structural item
  in the phase and it is gated on Q6, which may add apps/core/context_processors.py to the
  surface.
goals:
  - "all five accessors and all five filters accept LanguageLocale rather than str"
  - "the locale -> ru -> name (and LookupItem's locale -> ru -> slug) fallback chain is preserved exactly"
  - "every call site typechecks, and basedpyright reports 0 errors on the changed paths"
extra_context: |
  Q6 GATE - the answer must be written down before the block starts. The Implementor may not
  choose. Option (a): context_processors.language emits LanguageLocale and the filters take
  LanguageLocale. Option (b): the accessors accept str | LanguageLocale and normalise
  internally. Record the chosen option and the reason in the commit body.
  BINDING CONSTRAINTS (verbatim, from section 3 BLOCK 2)
  1. Preserve the fallback chain exactly: locale -> ru -> name for Category, City and Ad;
     locale -> ru -> slug for LookupItem, which ends at slug and NOT at name.
  2. Do not change the accessors' behaviour. A bad locale must still degrade to Russian -
     deliberately, via a route the type system documents rather than by accident.
  3. LookupItem.get_name ends at slug. A uniformity edit that makes it fall back to name is
     a regression.
  4. The default parameter remains LanguageLocale.RUSSIAN. Do not change it to None or to a
     thread-derived guess.
  5. No template may be edited to work around the typing. Templates call
     |get_city_name:LANGUAGE_CODE; if the type changes the CONTEXT PROCESSOR changes, not
     the 38 templates.
  6. Do not touch src/telegram_bot/middlewares/language.py - the bot's per-user locale is a
     different authority.
  7. basedpyright must reach 0 errors on the changed paths.
  8. VAL-003 still applies to the new tests: assert on the accessor's returned value, never
     on rendered chrome.
  9. The DB-backed assertions belong in test_i18n_category_city.py, which already exists for
     this surface. Do not create a new test module; do not touch conftest.py.
  VERIFIED SYMBOL MAP (re-derived at d42f778; use symbols, never line numbers)
  - all ten are currently typed locale: str = LanguageLocale.RUSSIAN - the default is ALREADY
    a LanguageLocale member, which is the strongest argument for option (a)
  - apps/core/context_processors.py -> function language, returning
    {"LANGUAGE_CODE": getattr(request, "LANGUAGE_CODE", settings.LANGUAGE_CODE)} - a str
  - docs/01-spec/i18n-spec.md, "Stored catalogue data" section, documents the four-layer
    surface and the fallback chain. BLOCK 12 updates the prose; this block does not.
  FORBIDDEN: editing src/backend/conftest.py; editing any template; editing any .po file;
  editing LanguagePreMiddleware; adding a fallback rung.
files:
  - path: src/backend/apps/categories/models.py
    targets: [{ type: method, name: get_name }]
  - path: src/backend/apps/locations/models.py
    targets: [{ type: method, name: get_name }]
  - path: src/backend/apps/lookups/models.py
    targets: [{ type: method, name: get_name }]
  - path: src/backend/apps/ads/models.py
    targets:
      - type: method
        name: get_title
      - type: method
        name: get_description
  - path: src/backend/apps/core/templatetags/localized_content.py
    targets:
      - type: function
        name: get_title
      - type: function
        name: get_description
      - type: function
        name: get_lookup_name
      - type: function
        name: get_category_name
      - type: function
        name: get_city_name
  - path: src/backend/apps/core/context_processors.py
    targets: [{ type: function, name: language }]
    changes: []  # in scope ONLY under Q6 option (a); a report otherwise, not a silent edit
  - path: src/backend/apps/ads/tests/test_i18n_category_city.py
    targets: []
    changes: []  # add cases to the existing module; do not weaken existing assertions
changes:
  - action: change_signature
    description: >
      Change the locale parameter of the five model accessors and the five template filters
      from str to the Q6-chosen type, keeping the default LanguageLocale.RUSSIAN and keeping
      every fallback rung in its current order.
  - action: add_test
    description: >
      Add DB-backed cases to test_i18n_category_city.py asserting that each accessor returns
      the requested locale's value for ru, bs and en (via LanguageLocale.values(), never bare
      string literals) and that a value the enum cannot represent degrades to the ru rung
      without raising.
acceptance_criteria:
  - "all five accessors and all five filters carry the Q6-chosen locale type"
  - "the default remains LanguageLocale.RUSSIAN"
  - "LookupItem still terminates at slug"
  - "the locale -> ru fallback still fires for an unmapped locale, and the test asserts that rather than an exception"
  - "uv run basedpyright reports 0 errors on every changed path"
  - "the existing assertions in test_i18n_category_city.py still pass unchanged"
  - "no template and no .po file was modified by this block"
  - "the commit body names the Q6 option chosen and the reason"
```

---

### BLOCK 3 — Price formatting: the `Decimal` argument and the `bs` grouping decision (`14-I18N-003`, `VAL-004`)

| | |
|---|---|
| **Findings owned** | `I18N-003` (HIGH), `VAL-004` (LOW advisory, folded in) |
| **Class** | **behavioural** — changes every rendered price in `ru` and `bs` |
| **Depends on** | nothing in-plan (independent of BLOCK 1) |
| **Blocks** | **BLOCK 4** (the chip must use the corrected helper) |
| **Priority** | **P0** |
| **Risk level** | **HIGH** — because the obvious fix is *demonstrably incomplete* and will read as finished |
| **Blast radius** | Every ad card, ad detail page, search-result row, and the Telegram alert messages that reuse `format_price_value` |
| **Required agents** | **Auditor · Researcher · Planner · Validator — all four**, because the incompleteness is invisible without a runtime probe and the gate below is a genuine technical choice |

**`Q3` — DECISION REQUIRED BEFORE IMPLEMENTATION. The block does not start until the answer
is written down.**

The root cause is narrow: `_format_amount` builds a plain string and passes a **`str`** to
`intcomma`. Django's `humanize.intcomma` localises only `float`/`Decimal`; for a `str` it
attempts `int(value)`, which raises `ValueError` on any fractional amount, and the `except`
branch recurses with `use_l10n=False` — a path that hard-codes `,` as the grouping separator
and leaves the `.` decimal mark untouched. Integer amounts survive the `int()` and take the
localising path, which is **why round prices look correct and hide the bug**.

| Option | Change | Maintainability / future evolution | Cost & risk |
|---|---|---|---|
| **(a)** | A project-level `FORMATS` override supplying `NUMBER_GROUPING = 3` for `bs` in settings | One declaration; every `number_format` and `intcomma` call in the project gets correct `bs` grouping, including the bot's alert messages, without any of them knowing | **Touches the six-way-contended `config/settings/base.py`** and needs its own settings test. Re-verified at the anchor: `bs/formats.py` sets `DECIMAL_SEPARATOR` and `THOUSAND_SEPARATOR` but leaves `NUMBER_GROUPING` commented out, and `numberformat.py` gates on `grouping != 0`, so grouping is structurally unreachable for `bs` **even under `force_grouping=True`** |
| **(b)** | A project-owned formatting helper that bypasses `numberformat.py`'s grouping gate | Total control; no dependence on a third-party locale file that could change | **Creates a second formatting path that can drift from `number_format`.** The project rule is *avoid overengineering, follow existing patterns* — a bespoke number formatter is the opposite, and it must then be used by the card, the chip, the detail page and the bot, or the inconsistency returns |
| **(c)** | Accept ungrouped `bs` prices and document the limitation | Zero cost; honest documentation | **Leaves the `ru`/`bs` inconsistency the fix was meant to close** — `1234,56` beside `1 234,56`. That *is* `I18N-003`'s impact, half-fixed and now described as a decision |

**Whatever is chosen, the grouping decision ships in the same change as the argument fix.**
A commit that changes only the argument is a half-fix that a reviewer will sign off on.

**File surface (semantic units)**

| File | Symbol | Change |
|---|---|---|
| `src/backend/apps/ads/templatetags/price_tags.py` | `_format_amount` | Pass the `Decimal` to `intcomma` (or call `number_format` directly) after trimming the exponent **on the `Decimal`**, not on the rendered string |
| | `format_price_value`, `format_price` | Unchanged in shape; BLOCK 4 reuses `format_price_value` |
| `src/backend/apps/ads/tests/test_price_format.py` | `test_format_price_value_uses_intcomma` | The docstring asserts locale-aware grouping; the body asserts only `"12345" not in result` and a 5-digit integer that never exercises the fractional branch. **Production code is king: the test follows the corrected behaviour** |
| `src/backend/config/settings/base.py` | `FORMATS` | **Only under `Q3` option (a)** — re-read immediately before editing; six-way contended |
| `src/backend/config/settings/tests/` | a new settings assertion | **Only under `Q3` option (a)** — the natural home is `test_settings_defaults.py`, which a concurrent phase-02 edit was landing in; re-read first |

**Binding constraints**

1. **`test_format_price_value_uses_intcomma` is a docstring/behaviour mismatch, not a
   regression to preserve.** Update the assertions to the corrected behaviour. Do **not**
   weaken them to accommodate the old output, and do not bend `_format_amount` back to
   satisfy them.
2. **Assert exact per-locale output**, not "a separator appeared". At minimum, for each of
   `ru`/`bs`/`en`: a fractional amount (exercises the defect), a round integer amount (proves
   no regression), and a **≥7-digit** amount (actually exercises grouping — a 5-digit number
   has at most one group and cannot prove grouping works).
3. **The separators are verified facts, not assumptions.** `ru`: `THOUSAND_SEPARATOR` is
   U+00A0 (non-breaking space) and `DECIMAL_SEPARATOR` is `,`. `bs`: `THOUSAND_SEPARATOR` is
   `.` and `DECIMAL_SEPARATOR` is `,`. Assert on the real code points.
4. **Under `Q3` option (a), the settings change and its test ship in the same commit**, and
   `base.py` is re-read immediately before editing. If the file has changed underneath, stop
   and report.
5. **Django's bundled `bs` locale data must not be edited.** It is a third-party package in
   `.venv`; an edit there is not a repository change and vanishes on the next image build.
6. **Do not change the price round-trip** — the `Decimal("0.01")` / `ROUND_HALF_UP`
   quantisation and the trailing-zero trim are the storage contract and are not part of this
   finding.
7. **Parametrise with `LanguageLocale.values()`**, never bare locale strings.
8. **BLOCK 4 reuses whatever helper this block lands.** Do not add a second formatting entry
   point for the chip's benefit.

**Implementor task**

```yaml
id: task_14_b03_price_format
title: "Pass the Decimal to the price formatter and ship the bs grouping decision (14-I18N-003, VAL-004)"
priority: high
depends_on: []
source_reference: ".ai/plans/14-i18n-remediation.md"
source_section: "BLOCK 3 - Price formatting"
source_blocks: ["BLOCK 3"]
description: >
  _format_amount in price_tags.py stringifies the Decimal and passes a str to intcomma.
  intcomma localises only float/Decimal; for a str it attempts int(value), which raises
  ValueError on any fractional amount, and the except branch recurses with use_l10n=False -
  hard-coding a comma as the grouping separator and leaving the ASCII decimal point. Integer
  amounts survive, so round prices hide the defect. The one-argument fix restores the decimal
  mark for ru and bs but NOT bs thousands grouping, because Django's bundled bs locale leaves
  NUMBER_GROUPING commented out and numberformat.py gates on grouping != 0. The grouping
  decision must ship in the same change.
goals:
  - "fractional prices localise correctly in all three locales"
  - "the bs grouping decision (Q3) is implemented and covered by a test, in the same commit"
  - "the existing test that documented the wrong behaviour is corrected, not weakened"
extra_context: |
  Q3 GATE - the block does not start until the option is written down. Option (a): a
  project-level FORMATS override supplying NUMBER_GROUPING = 3 for bs in
  config/settings/base.py, with its own settings test, in the same commit. Option (b): a
  project-owned formatting helper bypassing numberformat.py's grouping gate - accepted only
  with a written justification for accepting a second formatting path. Option (c): accept
  ungrouped bs prices as a documented limitation, and say plainly in the commit body that
  I18N-003 is only half closed.
  BINDING CONSTRAINTS (verbatim, from section 3 BLOCK 3)
  1. test_format_price_value_uses_intcomma is a docstring/behaviour mismatch, not a
     regression to preserve. Update the assertions to the corrected behaviour; do not weaken
     them and do not bend _format_amount back to satisfy them.
  2. Assert exact per-locale output. For each of ru/bs/en: a fractional amount, a round
     integer amount, and a >=7-digit amount. A 5-digit number has at most one group and
     cannot prove grouping works.
  3. Verified separator facts: ru THOUSAND_SEPARATOR is U+00A0 and DECIMAL_SEPARATOR is ",";
     bs THOUSAND_SEPARATOR is "." and DECIMAL_SEPARATOR is ",". Assert on real code points.
  4. Under Q3 option (a) the settings change and its test ship in the same commit, and
     base.py is re-read immediately before editing. Stop and report on a concurrent change.
  5. Django's bundled bs locale data must NOT be edited - it is a third-party package in
     .venv and the edit vanishes on the next image build.
  6. Do not change the price round-trip: the Decimal("0.01") / ROUND_HALF_UP quantisation and
     the trailing-zero trim are the storage contract.
  7. Parametrise with LanguageLocale.values(), never bare locale strings.
  8. BLOCK 4 reuses whatever helper this block lands. Do not add a second formatting entry
     point for the chip's benefit.
  VERIFIED SYMBOL MAP (re-derived at d42f778; use symbols, never line numbers)
  - src/backend/apps/ads/templatetags/price_tags.py -> function _format_amount, which builds
    format(rounded, "f"), trims trailing zeros, and returns intcomma(formatted)
  - the same module -> format_price_value and format_price, the latter the |format_price
    template filter
  - src/backend/apps/ads/tests/test_price_format.py -> test_format_price_value_uses_intcomma
  - django/conf/locale/bs/formats.py sets DECIMAL_SEPARATOR and THOUSAND_SEPARATOR and leaves
    "# NUMBER_GROUPING =" commented out; ru/formats.py sets all three
  FORBIDDEN: editing any .po file; editing price formatting in the bot; editing the
  quantisation; editing Django's bundled locale data.
files:
  - path: src/backend/apps/ads/templatetags/price_tags.py
    targets: [{ type: function, name: _format_amount }]
  - path: src/backend/apps/ads/tests/test_price_format.py
    targets: [{ type: function, name: test_format_price_value_uses_intcomma }]
    changes: []  # correct the assertions; do not weaken any
  - path: src/backend/config/settings/base.py
    targets: []
    changes: []  # ONLY under Q3 option (a); re-read immediately before editing
  - path: src/backend/config/settings/tests/test_settings_defaults.py
    targets: []
    changes: []  # ONLY under Q3 option (a); a concurrent phase-02 edit was landing here
changes:
  - action: change_code
    description: >
      Pass the Decimal to intcomma (or call number_format directly) after trimming the
      exponent on the Decimal rather than on the rendered string, so the localising path is
      taken for fractional amounts as well as integer ones.
  - action: add_code
    description: >
      Implement the Q3 decision. Under option (a) add the bs NUMBER_GROUPING form ofats
      override in config/settings/base.py next to the other locale configuration.
  - action: change_test
    description: >
      Rewrite test_format_price_value_uses_intcomma to assert exact per-locale output for a
      fractional amount, a round integer amount and a >=7-digit amount, and to assert the
      real separator code points.
acceptance_criteria:
  - "a fractional amount renders with the locale's decimal separator in ru, bs and en"
  - "a >=7-digit amount renders grouped in every locale the chosen Q3 option covers, and the test says explicitly which locales it does NOT cover under option (c)"
  - "a round integer amount renders identically to before this block"
  - "no test asserts only that a separator is present; every price assertion is exact-output"
  - "Django's bundled locale data under .venv is byte-identical to its shipped state"
  - "uv run basedpyright reports 0 errors on the changed paths"
  - "the commit body names the Q3 option chosen, the reason, and - under option (c) - that I18N-003 is only half closed"
```

---

### BLOCK 4 — The active-price filter chip uses the corrected helper (`14-I18N-010`)

| | |
|---|---|
| **Findings owned** | `I18N-010` (MEDIUM) |
| **Class** | **behavioural** |
| **Depends on** | **BLOCK 3** (strict — the chip must use the corrected formatting) |
| **Blocks** | nothing |
| **Priority** | **P1** |
| **Risk level** | **MEDIUM** — small edit, but it inherits `I18N-003`'s `bs` caveat |
| **Blast radius** | One partial, rendered by two routes (`listings.py` and `search.py`, both of which supply both bounds) |
| **Required agents** | **Auditor · Planner · Validator** — the surface is one template block plus two context keys; no Researcher is needed |

**The defect.** The chip renders
`{% blocktrans with min=active_price_min max=active_price_max %}Price: {{ min }}–{{ max }}{% endblocktrans %}`
from raw `Decimal`s. `blocktrans` placeholders apply **no filter chain**, so Django
stringifies a `Decimal` with an ASCII decimal point, no grouping and no currency code. The
ad cards in the **same response** go through `|format_price` — so the page contradicts itself
in the wrong notation for `ru` and `bs`. The gate cannot catch this: the text *is* wrapped;
only the interpolation is unformatted.

**The remedy already exists in the same file, fourteen lines below the defect:**
`{% trans "Purpose:" %} {{ p|get_lookup_name:LANGUAGE_CODE }}` — a `{% trans %}` label plus a
pre-computed value passed through a filter. **This block applies an existing in-file pattern
and introduces no new one.** That is the whole reason this is a `behavioural` block and not
a `structural` one.

**File surface (semantic units)**

| File | Symbol / element | Change |
|---|---|---|
| `src/backend/templates/ads/partials/ad_list.html` | the active-price `{% blocktrans %}` chip | Replaced with a `{% trans "Price:" %}` label plus the pre-formatted bounds |
| `src/backend/apps/ads/views/listings.py` | the template context that supplies `active_price_min` / `active_price_max` | Supplies **formatted** bounds via the BLOCK 3 helper. **Verified:** both routes already supply both keys, so this is a value-shape change, not a missing key |
| `src/backend/apps/search/views/search.py` | the same two context keys | Same change, so the two routes stay consistent |
| `src/backend/apps/ads/services/listings_query.py` | `ListingsQuery.active_price_range` — returns `tuple[Decimal \| None, Decimal \| None]` | **Unchanged.** The query layer returns `Decimal`s; the formatting belongs at the view boundary, not in the query object |

**Binding constraints**

1. **Format in the view, not in the template and not in the query.** The query service returns
   `Decimal`s and must keep doing so — a `Decimal` in a price range is the correct type at
   that layer.
2. **Use the BLOCK 3 helper exactly.** A second formatting call in the view is a second
   formatting path. Under `Q3` option (c) the chip will inherit the ungrouped `bs` output —
   **that inheritance must be stated in the commit body, not discovered later.**
3. **Both routes must be updated in the same commit.** `listings.py` and `search.py` feed the
   same partial; updating one leaves a locale-dependent inconsistency between the listings
   and search views of the same page.
4. **A `None` bound must render as before** — the current chip interpolates `None` when one
   side is open. Preserve whatever the current unbounded rendering is; do not invent a new
   placeholder and do not introduce a new translatable string.
5. **The `Price:` label already exists in all three catalogues.** ✔ Verified — the active
   msgid is the `#, python-format` entry `Price: %(min)s–%(max)s`, and the
   `Price: %(min)s–%(max)s` form is present. **Whether the `blocktrans` → `trans` change
   alters the extracted msgid is a BLOCK 10/12 concern: if it does, the new msgid must be
   present in `ru` and `bs` in the same commit, or the i18n gate goes red.** Report the
   msgid delta explicitly.
6. **Do not touch the `<time datetime="…">` display in the same partial** — the ISO
   attribute is BLOCK 5's must-not-touch item and the `'M d'` display beside it is BLOCK 5's
   change. Keeping them in separate commits keeps a date regression attributable.
7. **No new msgid may be introduced in English-only violation** — every new string is English
   in source and localised in `ru` and `bs`.

**Implementor task**

```yaml
id: task_14_b04_price_chip
title: "Render the active-price filter chip through the corrected formatter (14-I18N-010)"
priority: medium
depends_on: [task_14_b03_price_format]
source_reference: ".ai/plans/14-i18n-remediation.md"
source_section: "BLOCK 4 - The active-price filter chip"
source_blocks: ["BLOCK 4"]
description: >
  The active-price filter chip in the shared ad_list partial interpolates raw Decimal bounds
  through blocktrans, which applies no filter chain, so the summary shows 1000.50 with an
  ASCII point, no grouping and no currency code - directly above correctly formatted card
  prices in the same response. The remedy is the pattern already present fourteen lines below
  the defect: a trans label plus a pre-computed value passed through a filter.
goals:
  - "the chip renders the same grouped, localised, currency-suffixed price the cards do"
  - "both routes (listings and search) render identically, since they feed the same partial"
  - "introduce no new pattern and no new formatting entry point"
extra_context: |
  BINDING CONSTRAINTS (verbatim, from section 3 BLOCK 4)
  1. Format in the VIEW, not in the template and not in the query. ListingsQuery.active_price_range
     returns tuple[Decimal | None, Decimal | None] and must keep doing so - a Decimal in a
     price range is the correct type at that layer.
  2. Use the BLOCK 3 helper exactly. A second formatting call in the view is a second
     formatting path. Under Q3 option (c) the chip inherits the ungrouped bs output - state
     that inheritance in the commit body rather than discovering it later.
  3. Both routes must be updated in the same commit. listings.py and search.py feed the same
     partial; updating one leaves a locale-dependent inconsistency between two views of the
     same page. Both were verified to supply both bounds, so this is a value-shape change,
     not a missing key.
  4. A None bound must render as it does today. Preserve the current unbounded rendering; do
     not invent a placeholder and do not introduce a new translatable string.
  5. The Price: label already exists in all three catalogues. If the blocktrans -> trans
     change ALTERS the extracted msgid, the new msgid must be present with a non-empty ru and
     bs msgstr in the same commit or the i18n gate goes red. Report the msgid delta
     explicitly, and re-read all three .po files immediately before git add.
  6. Do not touch the <time datetime="...|date:'Y-m-d'"> attribute in the same partial. The
     ISO attribute is a must-not-touch item and the adjacent 'M d' display is BLOCK 5's
     change; separate commits keep a date regression attributable.
  7. Every new string is English in source, with non-empty ru and bs msgstr.
  VERIFIED SYMBOL MAP (re-derived at d42f778; use symbols, never line numbers)
  - src/backend/templates/ads/partials/ad_list.html -> the active-price blocktrans chip, and
    the in-file precedent {% trans "Purpose:" %} {{ p|get_lookup_name:LANGUAGE_CODE }}
  - src/backend/apps/ads/views/listings.py -> supplies active_price_min and active_price_max
  - src/backend/apps/search/views/search.py -> supplies the same two keys
  - src/backend/apps/ads/services/listings_query.py -> ListingsQuery.active_price_range
  - the active catalogue entry is the python-format msgid "Price: %(min)s-%(max)s"
  FORBIDDEN: editing ListingsQuery; adding a second formatter; touching the date filters;
  regenerating the catalogues wholesale.
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
  - path: src/backend/locale/ru/LC_MESSAGES/django.po
    targets: []
    changes: []  # ONLY if the msgid delta requires it; re-read immediately before git add
  - path: src/backend/locale/bs/LC_MESSAGES/django.po
    targets: []
    changes: []  # ONLY if the msgid delta requires it; non-empty msgstr required
changes:
  - action: change_code
    description: >
      Replace the blocktrans chip with a trans "Price:" label plus the pre-formatted bounds,
      applying the same pattern already used for the purpose chip in the same file.
  - action: change_code
    description: >
      Format both bounds in the view with the BLOCK 3 helper before they reach the template
      context, on both the listings and the search route.
  - action: add_test
    description: >
      Add a unit test that renders the chip under translation.override for each of ru/bs/en
      and asserts the decimal separator matches the locale's - not merely that a separator is
      present.
acceptance_criteria:
  - "the chip's rendered output uses the same separator and grouping as the card price in the same response, for all three locales"
  - "the listings and search routes render byte-identical chips for the same bounds"
  - "a None bound renders exactly as it did before this block"
  - "the test asserts an exact separator, not the presence of a separator"
  - "if the extracted msgid changed, ru and bs carry a non-empty msgstr for it in this same commit"
  - "no .po file was regenerated wholesale; any .po edit is a targeted entry edit with a re-read immediately before git add"
  - "the commit body reports the msgid delta and, under Q3 option (c), the inherited bs grouping limitation"
```

---

### BLOCK 5 — `TIME_ZONE` and the four display date patterns (`14-I18N-004`)

| | |
|---|---|
| **Findings owned** | `I18N-004` (MEDIUM, was HIGH) |
| **Class** | **behavioural** — **every rendered timestamp in the product shifts** |
| **Depends on** | nothing in-plan |
| **Blocks** | BLOCK 12 |
| **Priority** | **P1** |
| **Risk level** | **MEDIUM** (lowered from HIGH on 2026-10-03). The change is still the only one in the phase that is not backward-compatible and it still writes the six-way-contended settings file — **but the allowlist half of that risk is gone, because the value is hard-coded** |
| **Blast radius** | Ad-card freshness timestamps, the ad detail page, search history, and the seller dashboard's metric dates |
| **Required agents** | **Auditor · Researcher · Planner · Validator — all four**, because every rendered timestamp moves and the settings file is contended |

**`Q4` — ✅ RESOLVED 2026-10-03 (Product Owner). Both sub-answers are given; the block is
unblocked and the Implementor chooses nothing.**

> **1. The value: `TIME_ZONE = "Europe/Podgorica"`, hard-coded.**
> **2. Env-overridability: NO. The value is hard-coded and NOT env-overridable.**
>
> **Consequences, stated so no implementor re-opens them:**
> - **There is NO `ALLOWED_ENV_VARS` entry and NO `.env*.example` lines.** The allowlist collision
>   **disappears entirely** — the two rows in the file-surface table below are marked
>   *not applicable — do not create*.
> - **No other phase's allowlist work is triggered.** The reverse AST scanner and
>   `test_example_keys_in_allowlist` in both directions have nothing new to check.
> - **The env-overridability branch is CLOSED.** The earlier framing — "a hard-coded value is a
>   legitimate outcome and avoids the allowlist collision entirely; that is a real option" — has
>   been *chosen*, not merely listed. Do not create the env surface "for operator convenience".
> - `Europe/Belgrade` and `Europe/Sarajevo` are **declined**: they share today's offset and would
>   diverge if a jurisdiction changes, and the operating region is Montenegro.
> - The commit body records the ruling's date and that the zone was **ruled, not defaulted**.

**The defect.** `TIME_ZONE` is **absent from every module in the settings package**, so
Django's `America/Chicago` default (UTC−5/−6) applies. Separately, all four user-visible date
renderings hardcode en-US patterns. `USE_TZ` is `True` (Django 5's global default), so this
is **presentation-only — the naive/aware mismatch class does not exist here**, which is why
the severity was reduced. For an ad published between 00:00 and 07:00 local, **the calendar
day itself is wrong**, and a day-old ad can read as published today.

**File surface (semantic units)**

| File | Element | Change |
|---|---|---|
| `src/backend/config/settings/base.py` | the i18n / locale block, beside `LANGUAGE_CODE` | Add `TIME_ZONE = "Europe/Podgorica"` as a **hard-coded literal** — **NOT read through `env()`**, per the 2026-10-03 ruling. **Re-read immediately before editing; stop and report a concurrent change** |
| `src/backend/config/settings/base.py` | `ALLOWED_ENV_VARS` | 🚫 **NOT APPLICABLE — do not create.** `Q4` ruled the value non-env-overridable, so there is no entry. The allowlist collision disappears entirely |
| `.env.dev.example`, `.env.test.example`, `.env.prod.example`, and the fourth template | `TIME_ZONE=` | 🚫 **NOT APPLICABLE — do not create.** No env line is added, so `test_example_keys_in_allowlist` has nothing new to check in either direction. **No other phase's allowlist work is triggered** |
| `src/backend/templates/ads/detail.html` | the `{% trans "Published:" %}` display pattern | `'M d, Y'` → the locale `DATE_FORMAT`. **✔ The adjacent `<time datetime="{{ …\|date:'Y-m-d' }}">` attribute is correct ISO 8601 and must not change** |
| `src/backend/templates/ads/partials/ad_list.html` | the ad-card date display | `'M d'` → the locale `SHORT_DATE_FORMAT`. **Same file as BLOCK 4 — the two ISO attributes must not change** |
| `src/backend/templates/cabinet/search_history.html` | the search-history timestamp | `'M d, H:i'` → the locale `DATETIME_FORMAT` |
| `src/backend/templates/analytics/seller_dashboard.html` | the metric date | `'M d, Y'` → the locale `DATE_FORMAT` |
| `src/backend/config/settings/tests/` | a new `settings.TIME_ZONE` assertion | The natural home is `test_settings_defaults.py`, which had **no** `TIME_ZONE` or `LANGUAGE_*` assertion at all and which a concurrent phase-02 edit was landing in. **Re-read before adding one** |

**Binding constraints**

1. **The `|date:` inventory is complete and was re-verified: six occurrences in the whole
   template tree.** Two are the correct ISO `datetime=` attributes on `<time>` elements in
   `ads/detail.html` and `ads/partials/ad_list.html` — **must not be swept into this change.**
   The other four are the defective display patterns. There is nothing else to find, and
   nothing to "improve" while you are in there.
2. **This block adds no msgid.** ✔ Verified — the `Published:`, `Date:`, `Time:` labels already
   exist in all three catalogues. **This is a `.po`-free block**, and if a `makemessages` run
   is required to prove it, the `git diff` on `src/backend/locale` must come back empty.
3. **Use the locale format *names*, not new pattern strings.** `'DATE_FORMAT'`,
   `'SHORT_DATE_FORMAT'` and `'DATETIME_FORMAT'` are Django format names; the current
   `'M d, Y'` literals are the defect. Do not invent a new pattern per locale — that
   reimplements the locale data in templates.
4. **The change is not backward-compatible and is not claimed to be.** Every rendered
   timestamp moves. That is the fix. Record the before/after for one known instant in the
   commit body.
5. **`base.py` is six-way contended.** Re-read immediately before editing. Stage the specific
   files, never a directory. **The contention is now only additive**: one literal line.
6. **The setting is a literal — do not use the file's `env()` idiom here.** That was the shape
   under the env-overridable branch, which `Q4` **closed** on 2026-10-03. The file's `env()`
   idiom is correct everywhere else in `base.py` and is unchanged; it is simply **not** the idiom
   for this one setting.
7. **Do not touch `apps/core/utils/sanitize.py`, the bot's time handling, or any analytics
   query.** The change is display-timezone only; stored values are already aware and stay
   unchanged.
8. **The `<time datetime>` attributes are the machine-readable contract.** A screen reader, a
   crawler or a future JS enhancement reads them. Changing them to a locale format would
   break a consumer to make a human-facing string prettier.

**Implementor task**

```yaml
id: task_14_b05_timezone_and_dates
title: "Set TIME_ZONE and replace the four hardcoded en-US display date patterns (14-I18N-004)"
priority: medium
depends_on: []
source_reference: ".ai/plans/14-i18n-remediation.md"
source_section: "BLOCK 5 - TIME_ZONE and the display date patterns"
source_blocks: ["BLOCK 5"]
description: >
  TIME_ZONE is absent from every module in the settings package, so Django's America/Chicago
  default applies to a Balkan marketplace, and all four user-visible date renderings hardcode
  en-US patterns ('M d, Y', 'M d', 'M d, H:i'). USE_TZ is True - Django 5's global default -
  so this is presentation only and no naive/aware integrity class exists, but for an ad
  published between 00:00 and 07:00 local the calendar day itself is wrong. Six |date: uses
  exist in the whole template tree; two are correct ISO 8601 datetime attributes that must not
  change, and four are the defective display patterns.
goals:
  - "settings.TIME_ZONE is the ruled value Europe/Podgorica, hard-coded, and every rendered timestamp reflects it"
  - "the four display patterns use Django locale format names and the two ISO attributes are byte-identical"
  - "no msgid changes, so the catalogue diff is empty"
extra_context: |
  Q4 IS RESOLVED - 2026-10-03, Product Owner. BOTH sub-answers are given. (1) The value is
  Europe/Podgorica. (2) It is HARDCODED and NOT ENV-OVERRIDABLE.
  THEREFORE: NO ALLOWED_ENV_VARS entry and NO .env*.example lines. The allowlist collision
  disappears entirely and NO OTHER PHASE'S ALLOWLIST WORK IS TRIGGERED. The env-overridability
  branch is CLOSED - do not create the env surface for operator convenience.
  BINDING CONSTRAINTS (verbatim, from section 3 BLOCK 5)
  1. The |date: inventory is complete and re-verified: six occurrences in the whole template
     tree. The two <time datetime="{{ ...|date:'Y-m-d' }}"> attributes in ads/detail.html and
     ads/partials/ad_list.html are correct ISO 8601 machine-readable values and MUST NOT
     change. The other four are the defective display patterns. There is nothing else to
     find and nothing to improve while you are in there.
  2. This block adds no msgid - the Published:, Date: and Time: labels already exist in all
     three catalogues. It is a .po-FREE block. If a makemessages run is used to prove it,
     "git diff -- src/backend/locale" must come back empty.
  3. Use the locale format NAMES ('DATE_FORMAT', 'SHORT_DATE_FORMAT', 'DATETIME_FORMAT'),
     not new pattern strings. A new per-locale pattern reimplements the locale data in
     templates.
  4. This change is not backward-compatible and is not claimed to be: every rendered timestamp
     moves. Record the before/after for one known UTC instant in the commit body.
  5. config/settings/base.py is six-way contended (phases 02, 04, 06, 07, 08, 12). Re-read
     immediately before editing; stop and report a concurrent change; stage specific files, not
     a directory.
  6. TIME_ZONE IS A HARDCODED LITERAL - do NOT use the file's env() idiom for this one setting.
     That idiom is correct everywhere else in base.py and is unchanged; the env-overridable
     branch of Q4 was CLOSED on 2026-10-03, so this setting simply is not read from the
     environment.
  7. Do not touch apps/core/utils/sanitize.py, the bot's time handling, or any analytics
     query. Stored values are already aware and do not change.
  8. The two datetime attributes are the machine-readable contract - a screen reader, a
     crawler or a future JS enhancement reads them.
  VERIFIED SYMBOL MAP (re-derived at d42f778; use symbols, never line numbers)
  - config/settings/base.py -> LANGUAGE_CODE = "ru", the LANGUAGES tuple, the env() helper,
    ALLOWED_ENV_VARS. TIME_ZONE and USE_TZ are absent from EVERY module in the settings
    package.
  - templates/ads/detail.html -> the "Published:" display next to a <time datetime="Y-m-d">
  - templates/ads/partials/ad_list.html -> the ad-card date display next to a
    <time datetime="Y-m-d">. This file is also BLOCK 4's; re-read before editing.
  - templates/cabinet/search_history.html -> the search-history timestamp
  - templates/analytics/seller_dashboard.html -> the metric date
  - config/settings/tests/test_settings_defaults.py -> currently has NO TIME_ZONE or LANGUAGE_*
    assertion; a concurrent phase-02 edit was landing in it. Re-read before adding one.
  FORBIDDEN: editing the two ISO datetime attributes; editing a .po file; editing
  LanguagePreMiddleware; editing any stored-value or query-time conversion.
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
    changes: []  # add a TIME_ZONE assertion; re-read first, a concurrent edit was landing
changes:
  - action: add_code
    description: >
      Add TIME_ZONE = "Europe/Podgorica" next to LANGUAGE_CODE as a hard-coded literal, NOT read
      through env(). No ALLOWED_ENV_VARS entry and no .env*.example lines - Q4 ruled the value
      non-env-overridable on 2026-10-03.
  - action: change_code
    description: >
      Replace the four defective display date patterns with the corresponding Django locale
      format names, leaving the two <time datetime="...|date:'Y-m-d'"> attributes untouched.
  - action: add_test
    description: >
      Assert settings.TIME_ZONE equals "Europe/Podgorica", that a known UTC instant renders to
      the expected local time under each of ru/bs/en, and that the two ISO datetime
      attributes are byte-identical to their current values.
acceptance_criteria:
  - "settings.TIME_ZONE is the literal Europe/Podgorica, is NOT read from the environment, and a known UTC instant renders to the expected local wall time"
  - "ALLOWED_ENV_VARS is byte-unchanged and no .env*.example file gained a TIME_ZONE line; test_env_allowlist.py is green in both directions with nothing new to check"
  - "the four display patterns use locale format names; no per-locale pattern string is written in a template"
  - "the two <time datetime=\"...|date:'Y-m-d'\"> attributes are byte-identical to their pre-block state"
  - "git diff -- src/backend/locale is empty; this block adds no msgid"
  - "uv run djlint src/backend/templates/ reports no new finding"
  - "the commit body names the Q4 ruling (Product Owner, 2026-10-03), the chosen zone, that it was ruled and not defaulted, and a before/after rendering of one known instant"
```

---

### BLOCK 6 — `lang_pref`: one writer, hardened flags, honest cache contract (`14-I18N-009`, `14-I18N-011`, `14-I18N-012`)

| | |
|---|---|
| **Findings owned** | `I18N-009` (MEDIUM), `I18N-011` (LOW), `I18N-012` (LOW, documentation only) |
| **Class** | **behavioural** |
| **Depends on** | **BLOCK 1** (the resolver must exist before the cookie's write path is touched) |
| **Blocks** | BLOCK 12 |
| **Priority** | **P1** |
| **Risk level** | **HIGH** — Q5 is a **phase-06 boundary**, and the change removes a client-side code path |
| **Blast radius** | Every language switch on the site; `httponly` is a one-way door (a JS writer that cannot read or write the cookie breaks the switcher) |
| **Required agents** | **Auditor · Researcher · Planner · Validator — all four**, because this crosses a phase boundary and because `httponly` is irreversible in practice |

**`Q5` — DECISION REQUIRED BEFORE IMPLEMENTATION, and it is a phase-06 decision, not a
phase-14 one.** Phase 06 owns consent state (`06-PII-*`, `ConsentRecord`, the
`consent_preferences` context processor). The contradiction this block resolves is:

| Option | Change | Consequence |
|---|---|---|
| **(a)** *(the report's recommendation)* | **The server write is authoritative.** Delete the consent-guarded JS branch; state in the middleware docstring that it sets `lang_pref` | Correct and honest: the server write is the only one that runs on a plain `?lang=` link, so it already happens for everyone. It also makes `httponly=True` safe. **It removes a consent gate from a cookie write, which is a privacy-posture statement** — that is phase 06's call, not phase 14's |
| **(b)** | **The consent gate is real.** Move it into `process_response` and coordinate with phase 06 | The gate becomes a real server-side condition. It changes what the switcher does for a visitor who has not consented, and it may make `httponly=True` unnecessary (a cookie only written after consent) — but the middleware would then need access to consent state, which is phase 06's model |
| **(c)** | **Defer.** Record the contradiction, ship only the parts that are unambiguous | The two writers keep disagreeing, and the two `SameSite` values keep disagreeing. `I18N-011` can still ship `secure` and `samesite`; **`httponly` must be withheld** because a client-side writer may still need the cookie |

**Under every option, the two findings that are not in question ship:**
- `I18N-011` — pass `secure=settings.SESSION_COOKIE_SECURE`,
  `samesite=settings.SESSION_COOKIE_SAMESITE` and `httponly=True` to `set_cookie`. ✔ Both
  settings exist and are correct today; the fix is a **call-site** change, not a settings
  change. **`httponly=True` is only safe under option (a).**
- `I18N-012` — **correct the docstring, and nothing else.**

**✔ `I18N-012` — the header is not the defect, and this block is forbidden from changing it.**
The finding was reclassified to `DOC-UPDATE` **because the code is already correct**:
`CsrfViewMiddleware` calls `patch_vary_headers(response, ("Cookie",))` whenever a template
called `get_token()`, and every page does — so the emitted `Vary` in the real stack is
`Cookie, Accept-Language`, and a `Vary`-honouring cache **already** keys on the cookie. The
auditor's probe drove `LanguagePreMiddleware` in isolation through `RequestFactory`, bypassing
`SessionMiddleware` and `CsrfViewMiddleware` — **it measured the wrong stack.** What genuinely
remains is that the docstring misdescribes the contract and that the property is
**incidental**: `ads/partials/ad_list.html` and `categories/partials/mega_submenu.html` render
no `{% csrf_token %}`, so a fragment can lose `Vary: Cookie` without notice. The remedy is to
make the docstring say so, and to record what must happen when a shared cache is introduced.
**Do not add a `Vary: Cookie` header. That is the specific wrong fix this finding warns about.**

**File surface (semantic units)**

| File | Symbol / element | Change |
|---|---|---|
| `src/backend/apps/core/middleware/language.py` | `LanguagePreMiddleware.process_response` — the `response.set_cookie(...)` call | Add the `secure` / `samesite` / `httponly` arguments. **No other cookie behaviour changes** |
| `src/backend/apps/core/middleware/language.py` | the module docstring's cache-contract paragraph | State that cookie-driven locale is covered by `Vary: Cookie` **via `CsrfViewMiddleware`**, that this is **incidental**, and what must be made deliberate when a shared cache is added |
| `src/backend/apps/core/middleware/language.py` | the docstring's cookie-write paragraph | Record which writer is authoritative, per Q5 |
| `src/backend/templates/components/language_switcher.html` | the local `setCookie` helper and the `{% if consent_preferences %}`-gated click handler | **Only under Q5 option (a)** — the gated branch is deleted. **The helper itself is only removed if nothing else uses it** |
| `docs/01-spec/technical-specification.md` | the `lang_pref` cookie entry | **Deferred — phase 06 holds the reservation.** §5.3 |
| `src/backend/apps/core/tests/test_language_middleware.py` | the cookie-persistence tests | Assert the emitted cookie's `secure`, `samesite` and `httponly` attributes |

**Binding constraints**

1. **✔ Do not add a `Vary` header.** Fix the docstring. `I18N-012` exists because the code
   is already correct; adding a header would be a redundant, undeclared change to a
   contract that already holds.
2. **`httponly=True` only under Q5 option (a).** Under options (b) and (c), ship
   `secure` and `samesite` and withhold `httponly` with a comment saying why.
3. **Do not change the cookie's `max_age`**, its name, or the value written. `_apply_lang_param`
   persists the **resolved canonical code**, and BLOCK 1 did not change that.
4. **The `SESSION_COOKIE_*` settings are the source of truth, not literals.** Read
   `secure` and `samesite` from settings so `prod.py`'s `SESSION_COOKIE_SECURE = True` and
   `dev.py`/`test.py`'s relaxation to `False` keep working. **Do not edit `prod.py` or
   `dev.py`** — `prod.py` is phase 02's file and had a concurrent agent's unstaged work
   during the audit.
5. **Under Q5 option (a), verify the switcher still works end-to-end with `httponly`.** The
   JS writer is removed, so the server write is the only one. Assert that `?lang=bs` still
   sets `lang_pref` with **no** consent context present — that is the case the current tests
   do not cover.
6. **Deleting the JS branch must not delete a shared helper.** Read the whole
   `<script>` block first; if the local `setCookie` helper is used by another handler, keep it
   and only remove the gated call.
7. **Any new JS-visible string follows the `catalog_js_labels` pattern** —
   `apps/core/context_processors.py` → `header_context` → `catalog_js_labels`, consumed via
   `{{ catalog_js_labels|escapejs }}`. A raw literal in a `<script>` block bypasses both
   `makemessages` and the gate.
8. **Do not edit `docs/01-spec/technical-specification.md` in this block.** Phase 06 holds the
   reservation (BLOCKS 4, 11, 14). Record the desired edit and route it (§5.3).

**Implementor task**

```yaml
id: task_14_b06_lang_pref_cookie
title: "One writer for lang_pref, hardened cookie attributes, and a truthful cache contract (14-I18N-009, 14-I18N-011, 14-I18N-012)"
priority: medium
depends_on: [task_14_b01_locale_resolver]
source_reference: ".ai/plans/14-i18n-remediation.md"
source_section: "BLOCK 6 - lang_pref: one writer, hardened flags, honest cache contract"
source_blocks: ["BLOCK 6"]
description: >
  The language switcher's inline JS writes lang_pref only inside a consent gate while the
  middleware writes the same cookie unconditionally whenever ?lang= was supplied; neither site
  references the other, and the client helper sets SameSite=Lax while the server sets none, so
  the two writers disagree on more than the gate and the weaker one lands last. Separately,
  lang_pref is the only cookie the project issues that opts out of all six
  SESSION_COOKIE_*/CSRF_COOKIE_* attributes the project sets elsewhere. And the middleware
  docstring presents patch_vary_headers(Accept-Language) as the complete cache contract when
  CsrfViewMiddleware is already adding Vary: Cookie on every full page - an incidental CSRF
  side effect, not a declared invariant.
goals:
  - "exactly one writer persists lang_pref, and the middleware docstring says which"
  - "the cookie carries the project's own secure / samesite / httponly policy, read from settings"
  - "the cache-contract docstring is true, and the Vary header itself is unchanged"
extra_context: |
  Q5 GATE - phase-06 boundary. The block does not start until the answer is written down and
  phase 06 has acknowledged it. Option (a): the server write is authoritative; delete the
  consent-guarded JS branch and say so in the middleware docstring. Option (b): the consent
  gate is real; move it into process_response and coordinate with phase 06, which owns
  ConsentRecord and the consent_preferences context processor. Option (c): defer; record the
  contradiction and ship only the unambiguous parts. httponly=True is safe ONLY under (a).
  ALSO GATED: naming lang_pref in the technical specification's cookie list requires phase
  06's clearance on docs/01-spec/technical-specification.md. That limb is DEFERRED, not
  skipped, unless phase 06 clears it.
  BINDING CONSTRAINTS (verbatim, from section 3 BLOCK 6)
  1. DO NOT ADD A Vary HEADER. Fix the docstring. I18N-012 was reclassified to DOC-UPDATE
     because the code is ALREADY correct: CsrfViewMiddleware adds Vary: Cookie on any
     response whose template called get_token(), and every page does, so a Vary-honouring
     cache already keys on the cookie. The original probe drove LanguagePreMiddleware in
     isolation through RequestFactory and measured the wrong stack. What remains is that the
     property is INCIDENTAL - ads/partials/ad_list.html and
     categories/partials/mega_submenu.html render no csrf_token - so make the docstring say
     so, and record what must be made deliberate when a shared cache is introduced.
  2. httponly=True only under Q5 option (a). Under (b) and (c), ship secure and samesite and
     withhold httponly with a comment saying why.
  3. Do not change the cookie's max_age, its name, or the value written. _apply_lang_param
     persists the RESOLVED CANONICAL code, unchanged by BLOCK 1.
  4. Read secure and samesite from SESSION_COOKIE_SECURE and SESSION_COOKIE_SAMESITE - do not
     write literals. Do NOT edit prod.py or dev.py: prod.py is phase 02's file and had a
     concurrent agent's unstaged work during the audit.
  5. Under Q5 option (a), verify the switcher end-to-end with httponly and add the case the
     current tests do not cover: ?lang=bs sets lang_pref with NO consent context present.
  6. Deleting the JS branch must not delete a shared helper. Read the whole script block
     first; if the local setCookie helper is used elsewhere, keep it and remove only the
     gated call.
  7. Any new JS-visible string follows the catalog_js_labels pattern -
     apps/core/context_processors.py -> header_context -> catalog_js_labels, consumed via
     {{ catalog_js_labels|escapejs }}. A raw literal in a <script> block bypasses both
     makemessages and the gate.
  8. Do not edit docs/01-spec/technical-specification.md - phase 06 holds the reservation.
  VERIFIED SYMBOL MAP (re-derived at d42f778; use symbols, never line numbers)
  - src/backend/apps/core/middleware/language.py -> LanguagePreMiddleware.process_response
    calls response.set_cookie(LANGUAGE_COOKIE_NAME, cookie_value,
    max_age=LANGUAGE_COOKIE_MAX_AGE) with no secure, samesite or httponly, then
    patch_vary_headers(response, ("Accept-Language",)), then
    response.headers.setdefault("Content-Language", translation.get_language())
  - config/settings/base.py -> SESSION_COOKIE_SECURE / HTTPONLY / SAMESITE and the
    CSRF_COOKIE_* equivalents; config/settings/prod.py re-asserts the two _SECURE flags;
    dev.py and test.py relax them for local HTTP
  - src/backend/templates/components/language_switcher.html -> the local setCookie helper
    building ['max-age=...', 'path=...', 'SameSite=Lax'] and the {% if consent_preferences %}
    gated click handler
  FORBIDDEN: adding a Vary header; editing prod.py or dev.py; changing the cookie's name,
  max_age or value; editing docs/01-spec/technical-specification.md; editing a .po file.
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
    changes: []  # ONLY under Q5 option (a); otherwise read-only in this block
  - path: src/backend/apps/core/tests/test_language_middleware.py
    targets: [{ type: function, name: test_cookie_persists_canonical_code }]
    changes: []  # add attribute assertions; do not weaken existing ones
changes:
  - action: change_code
    description: >
      Pass secure=settings.SESSION_COOKIE_SECURE, samesite=settings.SESSION_COOKIE_SAMESITE
      and - only under Q5 option (a) - httponly=True to the lang_pref set_cookie call.
  - action: change_docstring
    description: >
      Correct the middleware's cache-contract docstring to state that cookie-driven locale is
      covered by Vary: Cookie via CsrfViewMiddleware, that this is incidental rather than
      declared, and what must be made deliberate when a shared cache is introduced.
  - action: change_docstring
    description: >
      Record in the cookie-write docstring which writer is authoritative, per the Q5 answer.
  - action: change_code
    description: >
      Under Q5 option (a) only: remove the consent-gated JS write from
     language_switcher.html, keeping the shared setCookie helper if anything else uses it.
  - action: add_test
    description: >
      Assert the emitted lang_pref cookie's secure, samesite and httponly attributes, and -
      under option (a) - that ?lang=bs sets the cookie with no consent context present.
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

### BLOCK 7 — A plural-aware `.po` parser (`14-I18N-005`)

| | |
|---|---|
| **Findings owned** | `I18N-005` (MEDIUM) |
| **Class** | **structural** — introduces a source of truth for `.po` entry structure |
| **Depends on** | nothing in-plan |
| **Blocks** | **BLOCK 11** (strict — a credible stale-entry gate needs this parser) |
| **Priority** | **P1** — do it before any block that parses a catalogue |
| **Risk level** | **MEDIUM** — a shared helper with two call sites, but a small one |
| **Blast radius** | Every `.po`-reading test in the phase; BLOCKS 9, 10, 11 all sit on top of it |
| **Required agents** | **Auditor · Planner · Validator** — the change is one return type and one function body, and the ordering it enables is the real risk |

**The defect.** `_parse_po_entries` reassigns `cur_msgstr` on **every** `msgstr`-prefixed
line, including `msgstr[N]`, discarding all but the last plural form. Both copies of
`test_no_empty_msgstr` then ask "is any `msgstr` blank?", which for a plural entry is only
ever a question about the **last** form. The docstring claims the parser shares "the first
`msgstr` value encountered"; the implementation keeps the **last**. ✔ Both re-verified at
`d42f778`.

**It is latent, not live.** ✔ Measured: `ru` 2 plural entries, **0** with any empty form;
`bs` 2, **0**; `en` 2, 2 empty (the documented `en` exemption). The DoD contract is genuinely
unenforced for plural entries; it just has not been violated. At runtime the seller dashboard
would render `1 просмотров` instead of `1 просмотр`.

**Why it must precede BLOCK 11.** A credible stale-entry gate must **parse** the catalogue,
not regex it — the sixth `I18N-014` orphan is a **wrapped multi-line `msgid`**, which a
line-anchored regex silently misses, and a literal-substring source comparison over-reports
(47 false positives in the Auditor's cross-check). Both problems need a parser that
represents a plural entry as a plural entry.

**File surface (semantic units)**

| File | Symbol | Change |
|---|---|---|
| `src/backend/testing/i18n_helpers.py` | `_parse_po_entries` | Return `list[tuple[str, list[str]]]` — the msgid and **all** its `msgstr` forms — instead of `list[tuple[str, str]]`. Accumulate `msgstr[N]` forms rather than overwriting |
| `src/backend/apps/ads/tests/test_i18n_completeness.py` | `test_no_empty_msgstr` | Flatten: "**any** blank form is a violation" |
| `src/backend/apps/ads/tests/test_i18n_pipeline.py` | `test_no_empty_msgstr` (the second copy) | The same change. ✔ The two copies are functionally equivalent and both have the blind spot |
| a parser unit test | new | Feed the parser a synthetic plural entry with a blank `msgstr[0]` and assert the blank form is reported |

**Binding constraints**

1. **Correct the docstring.** It currently describes behaviour the implementation does not
   have. A docstring that lies is the class of defect this block exists to remove.
2. **The `en` skip stays exactly as it is**, in both call sites. `en` may have empty
   `msgstr`s — that is the documented convention, and filling them is a 408-entry diff that
   changes nothing at runtime.
3. **Do not reorder or renumber plural forms.** `msgstr[0..2]` for `ru`/`bs` and
   `msgstr[0..1]` for `en` are CLDR-correct. The two `bs` plural entries that share
   `msgstr[1]` and `msgstr[2]` are **correct** for `bs` — do not "fix" them.
4. **A parser test that is never observed failing is unverified.** Demonstrate the blank
   `msgstr[0]` case failing before the fix and passing after.
5. **Both call sites change in the same commit.** A half-migrated return type is a type
   error, and the two `test_no_empty_msgstr` copies are the reason the phase has two of them.
6. **No catalogue file is edited.** The parser changes; the `.po` files do not.

**Implementor task**

```yaml
id: task_14_b07_plural_parser
title: "Make the shared .po parser plural-aware so any blank msgstr form is reported (14-I18N-005)"
priority: medium
depends_on: []
source_reference: ".ai/plans/14-i18n-remediation.md"
source_section: "BLOCK 7 - A plural-aware .po parser"
source_blocks: ["BLOCK 7"]
description: >
  _parse_po_entries reassigns its accumulator on every msgstr-prefixed line including
  msgstr[N], keeping only the last plural form, and its docstring claims it keeps the first.
  Both copies of test_no_empty_msgstr then ask a question that is only ever about the last
  form, so a translator can blank the Russian singular form and the gate stays green. The
  current catalogues are correct - ru and bs have 0 plural entries with any empty form - so
  this is a latent hole. BLOCK 11's stale-entry gate needs this parser, because one of the six
  orphans is a wrapped multi-line msgid that a line-anchored regex misses.
goals:
  - "the parser returns every msgstr form, so a blank non-final form is detectable"
  - "both copies of test_no_empty_msgstr fail on any blank form"
  - "the parser docstring describes what the code does"
extra_context: |
  BINDING CONSTRAINTS (verbatim, from section 3 BLOCK 7)
  1. Correct the docstring. It currently describes behaviour the implementation does not
     have; a lying docstring is the class of defect this block removes.
  2. The `en` skip stays EXACTLY as it is, in BOTH call sites. en may have empty msgstrs -
     that is the documented convention, and filling them is a 408-entry diff that changes
     nothing at runtime.
  3. Do not reorder or renumber plural forms. msgstr[0..2] for ru/bs and msgstr[0..1] for en
     are CLDR-correct. The two bs plural entries that share msgstr[1] and msgstr[2] are
     CORRECT for bs - do not "fix" them.
  4. Demonstrate the blank-msgstr[0] case failing before the fix and passing after. A parser
     test never observed failing is unverified.
  5. Both call sites change in the same commit.
  6. No catalogue file is edited by this block.
  VERIFIED SYMBOL MAP (re-derived at d42f778; use symbols, never line numbers)
  - src/backend/testing/i18n_helpers.py -> _parse_po_entries(text: str) -> list[tuple[str, str]],
    whose docstring claims it shares the FIRST msgstr value encountered while the body keeps
    the LAST
  - src/backend/apps/ads/tests/test_i18n_completeness.py -> test_no_empty_msgstr, which skips
    `en` by continue
  - src/backend/apps/ads/tests/test_i18n_pipeline.py -> test_no_empty_msgstr, the second copy,
    which skips `en` by continue AFTER computing the list - functionally equivalent, same
    blind spot
  - both use the identical expression
    empty = [msgid for msgid, msgstr in entries if msgid and not msgstr.strip()]
  - callers of _parse_po_entries elsewhere (including test_no_cyrillic_msgids and
    test_extraction_completeness) must keep compiling after the return type changes - enumerate
    them, do not discover them from a red run
  FORBIDDEN: editing any .po file; filling en msgstrs; "fixing" the shared bs plural forms;
  splitting the change across two commits.
files:
  - path: src/backend/testing/i18n_helpers.py
    targets: [{ type: function, name: _parse_po_entries }]
  - path: src/backend/apps/ads/tests/test_i18n_completeness.py
    targets: [{ type: function, name: test_no_empty_msgstr }]
  - path: src/backend/apps/ads/tests/test_i18n_pipeline.py
    targets: [{ type: function, name: test_no_empty_msgstr }]
  - path: src/backend/apps/ads/tests/test_i18n_helpers_unit.py
    targets: []
    changes: []  # new parser unit test; or an existing unit module in the same package
changes:
  - action: change_signature
    description: >
      Return list[tuple[str, list[str]]] from _parse_po_entries so each entry carries every
      msgstr form, accumulating msgstr[N] lines rather than overwriting the accumulator, and
      rewrite the docstring to match.
  - action: change_code
    description: >
      Flatten in both test_no_empty_msgstr copies: any blank form is a violation, not only a
      blank final form.
  - action: add_test
    description: >
      Add a parser unit test that feeds a synthetic plural entry with a blank msgstr[0] and
      asserts the blank form is reported as a violation.
acceptance_criteria:
  - "a synthetic plural entry with a blank msgstr[0] is reported as a violation by both test_no_empty_msgstr copies"
  - "the failure was demonstrated before the fix and the pass after it"
  - "the `en` skip is byte-identical in both call sites"
  - "every existing caller of _parse_po_entries still compiles and passes"
  - "no .po file was modified by this block"
  - "the parser docstring describes the actual behaviour"
```

---

### BLOCK 8 — Collector widening and the `hreflang` include assertion (`14-I18N-006`, `14-I18N-007`, `14-I18N-008`)

| | |
|---|---|
| **Findings owned** | `I18N-006` (MEDIUM), `I18N-007` (MEDIUM), `I18N-008` (MEDIUM) |
| **Class** | **behavioural** — every assertion here can turn the currently-green gate red |
| **Depends on** | nothing in-plan |
| **Blocks** | BLOCK 9 (the widened bot collector defines the exemption set BLOCK 9 needs) |
| **Priority** | **P1** |
| **Risk level** | **MEDIUM-HIGH** — a widened scanner is exactly the change that turns a green gate red on arrival |
| **Blast radius** | The whole i18n completeness gate, which every phase depends on |
| **Required agents** | **Auditor · Researcher · Planner · Validator** — all four, because the widened collector's first run is a **prediction that has never been executed** |

**Q9 is a pre-block Auditor step, not a preference gate.** Before the block starts, the
Auditor must run each widened collector against the current tree and report **exactly which
files fail and why**. The near-certain outcome for the bot collector is failure:
`src/telegram_bot/lifecycle.py` → `_COMMANDS` is a `dict[str, list[BotCommand]]` holding
**twelve** `BotCommand(command=…, description=…)` literals — four per language across
`ru`/`bs`/`en` — with an explicit module comment explaining that they are **not** gettext
msgids (an eager `_()` would freeze the string at import time). **Four of their strings are
the `I18N-014` orphans.**

**Binding constraints**

1. **Collect by walking, not by listing.** `rglob("*.py")` over `src/telegram_bot` minus
   `tests/`; app-template roots derived from each installed app's `path` unioned with
   `TEMPLATES["DIRS"]`. **Never a hard-coded module list** — `handlers/ad_create.py` is now a
   **nine-module package**, and a hard-coded list would silently lose all nine.
2. **The exclusion list is a named, documented set, not an inline tuple of paths that grows.**
   The `lifecycle.py` command-menu literals become the **first** named exemption, and BLOCK 9
   and BLOCK 11 both reuse that set. One definition, three consumers.
3. **The existing exclusion tuple is preserved as-is** — `admin/`,
   `analytics/moderation_dashboard.html`, `components/feature_tag.html` — and remains in sync
   with the exemption list in `docs/99-agent/rules.md`.
4. **The `hreflang` include assertion must exclude the partial itself** and must reconcile
   with the exclusion list: `admin/moderation/review.html` and
   `analytics/moderation_dashboard.html` are both excluded from `_collect_template_files`
   **and** both include the partial. Reconciling that is part of the work, not an edge case.
5. **Never hard-code a file count.** ✔ The report's "43 templates" is **38** at this anchor
   (C-2). Any guard derives its expectation from the collector.
6. **Add a positive assertion that at least one app-level template root is discovered** once
   one exists — otherwise a refactor that moves every template into apps silently reduces the
   gate to nothing and the guard stays green.
7. **The two HTMX fragments `ads/partials/ad_list.html` and `categories/partials/mega_submenu.html`
   render no `csrf_token`.** Do **not** "fix" this here by adding one. It is the incidental-`Vary`
   fragility `I18N-012` records, and BLOCK 6 documents it. Adding a CSRF token to a fragment
   changes cache semantics for a reason outside this finding.
8. **Every new assertion must be demonstrated failing.** A widened collector that has never
   been seen red is an unverified claim that the widening was necessary.
9. **No catalogue file is edited.**

**File surface (semantic units)**

| File | Symbol | Change |
|---|---|---|
| `src/backend/apps/ads/tests/test_i18n_completeness.py` | `_collect_bot_handler_files` | Widen to `src/telegram_bot` minus `tests/` |
| | `_collect_bot_source_files` | Same root, same exclusion |
| | `_collect_template_files` | Widen to `DIRS` ∪ per-app `path/templates`, keeping `exclude_subpaths` relative to each root |
| | `test_hreflang_present` | Add a source-level assertion over non-partial templates that each contains the `locale_head.html` include, excluding the partial itself and reconciling with the exclusion list |
| | the new named exemption set | A single module-level definition the collectors, the `hreflang` assertion, BLOCK 9 and BLOCK 11 all read |
| `src/backend/apps/ads/tests/` | a `retry.py` / `states.py` case | Prove the widened set reaches modules that were previously invisible |
| `docs/99-agent/rules.md` | the scan-scope bullet | **Read before writing** — phase 12 holds a conditional claim on this file (§5.3). Records the new exemption |

**Implementor task**

```yaml
id: task_14_b08_gate_collectors
title: "Widen the bot and template collectors and assert every page template includes the locale partial (14-I18N-006, 14-I18N-007, 14-I18N-008)"
priority: medium
depends_on: []
source_reference: ".ai/plans/14-i18n-remediation.md"
source_section: "BLOCK 8 - Collector widening and the hreflang include assertion"
source_blocks: ["BLOCK 8"]
description: >
  The i18n gate's bot collectors hard-code handlers/ and services/ instead of walking
  src/telegram_bot and excluding only tests/, and its template collector iterates
  TEMPLATES["DIRS"] while APP_DIRS is True. The unscanned bot set is __init__.py,
  lifecycle.py, main.py, retry.py, states.py, middlewares/* (5 modules, including the one that
  activates the locale for every update) and schemas/* (4). test_hreflang_present renders
  components/locale_head.html in isolation and never inspects a page template, while its
  docstring claims the partial is included by every page template. All 15 page templates do
  include it today - this is a coverage gap, not a live defect - and the gate reads as if the
  site-wide property were enforced.
goals:
  - "every bot module except tests/ is scanned, with a named and documented exemption set"
  - "app-level template directories are scanned, and the gate fails if it discovers no root"
  - "the site-wide hreflang include property is asserted, not just the partial's own rendering"
extra_context: |
  Q9 PRE-BLOCK STEP - the Auditor runs each widened collector against the current tree BEFORE
  the block starts and reports exactly which files fail and why. The near-certain outcome for
  the bot collector is failure: src/telegram_bot/lifecycle.py -> _COMMANDS holds twelve
  non-gettext BotCommand literals, four per language, with a module comment explaining they are
  deliberately not msgids. FOUR OF THEIR STRINGS ARE THE 14-I18N-014 ORPHANS (Start, Language,
  Post ad, Alerts). This block does not assume the outcome.
  BINDING CONSTRAINTS (verbatim, from section 3 BLOCK 8)
  1. Collect by WALKING, not by listing. rglob("*.py") over src/telegram_bot minus tests/;
     app-template roots from each installed app's path unioned with TEMPLATES["DIRS"]. Never a
     hard-coded module list - handlers/ad_create.py is now a NINE-MODULE PACKAGE and a
     hard-coded list would silently lose all nine.
  2. The exclusion list is a named, documented set with ONE definition, read by the collectors,
     the hreflang assertion, BLOCK 9 and BLOCK 11. The lifecycle.py command-menu literals are
     the first named exemption.
  3. The existing exclusion tuple is preserved as-is - admin/,
     analytics/moderation_dashboard.html, components/feature_tag.html - and stays in sync with
     the exemption list in docs/99-agent/rules.md.
  4. The hreflang include assertion must EXCLUDE the partial itself and must reconcile with
     the exclusion list: admin/moderation/review.html and
     analytics/moderation_dashboard.html are BOTH excluded from _collect_template_files AND
     both include the partial.
  5. NEVER HARD-CODE A FILE COUNT. The report's "43 templates" is 38 at this anchor. Any guard
     derives its expectation from the collector.
  6. Add a positive assertion that at least one app-level template root is discovered once one
     exists - otherwise a refactor that moves every template into apps silently reduces the
     gate to nothing and the guard stays green.
  7. ads/partials/ad_list.html and categories/partials/mega_submenu.html render no
     csrf_token. Do NOT "fix" this here by adding one - it is the incidental-Vary fragility
     I18N-012 records, and BLOCK 6 documents it. Adding a CSRF token to a fragment changes
     cache semantics for a reason outside this finding.
  8. Demonstrate every new assertion failing at least once.
  9. No catalogue file is edited by this block.
  10. Read docs/99-agent/rules.md before writing to it. Phase 12 holds a CONDITIONAL claim on
      that file; re-read and report a concurrent change rather than clobbering it.
  VERIFIED SYMBOL MAP (re-derived at d42f778; use symbols, never line numbers)
  - src/backend/apps/ads/tests/test_i18n_completeness.py -> _collect_bot_handler_files,
    _collect_bot_source_files, _collect_template_files, test_hreflang_present,
    _template_source, and the exclude_subpaths tuple
  - _collect_template_files walks tmpl_cfg.get("DIRS", []) and never reads APP_DIRS
  - config/settings/base.py -> TEMPLATES sets DIRS to [BASE_DIR / "backend" / "templates"]
    and APP_DIRS to True
  - src/backend/templates holds 38 .html files and NOTHING else; src/templates is empty; no
    apps/*/templates directory exists, so the APP_DIRS gap is latent today
  - 16 files reference components/locale_head.html: 15 page templates plus the partial's own
    header comment
  - _template_source already exists in the same module and has the same DIRS-only limitation
  FORBIDDEN: editing a .po file; editing any .mo file; adding a csrf_token to a fragment;
  hard-coding a template count; editing src/backend/conftest.py.
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
        name: test_hreflang_present
  - path: src/backend/apps/ads/tests/test_i18n_bot_scope_unit.py
    targets: []
    changes: []  # new unit module for the collectors; add retry.py / states.py cases
  - path: docs/99-agent/rules.md
    targets: []
    changes: []  # read-before-write; phase 12 holds a conditional claim
changes:
  - action: change_code
    description: >
      Widen both bot collectors to rglob over src/telegram_bot excluding tests/, and widen the
      template collector to TEMPLATES["DIRS"] unioned with each installed app's path/templates
      with exclude_subpaths applied relative to each root.
  - action: add_code
    description: >
      Introduce ONE named, documented exemption set - starting with the lifecycle.py
      command-menu literals - and have every consumer read it.
  - action: add_test
    description: >
      Add a source-level assertion that every non-partial page template contains the
      components/locale_head.html include, excluding the partial itself and reconciling with
      the documented exclusion list.
  - action: add_test
    description: >
      Add a positive assertion that at least one root was discovered, so a collector that
      silently matches nothing fails.
acceptance_criteria:
  - "the widened bot collector reaches retry.py, states.py, middlewares/language.py and the nine-module handlers/ad_create package"
  - "the widened template collector discovers app-level template directories when they exist, and fails if it discovers no root at all"
  - "the lifecycle.py exemption is named once and read by every consumer, with the reason recorded next to it"
  - "the hreflang assertion covers all 15 page templates, excludes components/locale_head.html itself, and does not fail on admin/moderation/review.html or analytics/moderation_dashboard.html"
  - "no assertion anywhere hard-codes a template or module count"
  - "every new assertion was demonstrated failing at least once"
  - "the two csrf_token-free fragments are unchanged"
  - "the gate is green on arrival with the documented exemptions in place; if it is not, that is the Q9 answer and it is reported, not suppressed"
```

---

### BLOCK 9 — A `msgstr` script gate, and the three real `bs` strings (new `N-1`, `I18N-013` interaction)

| | |
|---|---|
| **Findings owned** | **N-1** (new, MEDIUM) — the detection rule and, conditionally, the three `bs` strings |
| **Class** | **conditional** — ships the **reduced deliverable** (detection rule + named commented exemption) while `Q1` is `OPEN-PENDING-REVIEWER` |
| **Status** | 🚧 **`Q1` gate = `OPEN-PENDING-REVIEWER` as of 2026-10-03 — NOT closed.** The *who* is ruled (a native, preferably Montenegrin reviewer; machine output and translation APIs are not acceptable); the *sign-off* does not yet exist. **BLOCK 9 is runnable now and ships its reduced deliverable.** It is not blocked and it is not settled |
| **Depends on** | **BLOCK 7** (the parser) and **BLOCK 8** (the exemption set this block's gate reuses) |
| **Blocks** | BLOCK 11, BLOCK 12 |
| **Priority** | **P1** |
| **Risk level** | **MEDIUM** — small catalogue edits, but it is the block where a machine could be tempted to invent a translation |
| **Blast radius** | One `.po` file (`bs`) and one gate |
| **Required agents** | **Auditor · Planner · Validator** — all three of the engineering agents. **No translation is written by anyone; `Q1` is an owner/linguist decision** |

**`Q1` — RULED 2026-10-03 (Product Owner): a native, preferably Montenegrin reviewer signs off the
three `bs` strings; machine output and translation APIs are NOT acceptable. The gate is therefore
recorded as `OPEN-PENDING-REVIEWER`, not closed.** Three strings need that reviewer:

| # | String | Where | Verdict required |
|---|---|---|---|
| 1 | the contaminated support-greeting sentence — currently `"Za kreiranje oglasа користи /post."` (a Croatian/Bosnian frame with the **Russian verb** `користи` and a **Cyrillic "а"** inside `oglasa`) | `bs` catalogue, support-contact flow | **A linguist rewrite.** A machine translation of a corrupted string is worse than the corruption |
| 2 | `Moderator #%(mid)s` — copy-through | `templates/analytics/moderation_dashboard.html`, an **already-exempt** template | Is the copy-through correct Bosnian, or does it need a rewrite? |
| 3 | `Admin` — copy-through | `templates/components/header.html`, `components/header_auth_entry.html` | Same. **In scan scope** (C-6) |

**✔ This plan does not write any of them, and the Implementor is forbidden from writing,
guessing, machine-translating or "approximating" any of them.** Phase 09's outbound
Google-Translate client is explicitly **not** a catalogue tool, and project rule 1 makes every
`msgid` English — the replacement `msgstr` is a `bs` value that only a speaker can produce. **The
2026-10-03 ruling reinforces this: machine output and translation APIs are not acceptable, so
"there is no reviewer yet" is the *only* reason the strings ship as-is — it is not a licence to
produce them another way.**

**`Q2` does not gate this block, and its 2026-10-03 answer does not change that.** ✔ The code
context claims Option A for `I18N-013` would remove two of the three strings from scope. **The
tree does not support that**: `I18N-013` is about *model metadata* (`verbose_name` /
`help_text`), a different surface from a *template* that is already in the gate's
`exclude_subpaths` tuple (C-5). **Q1 and Q2 are independent**, and the fact that `Q2` resolved to
Option A on 2026-10-03 — while `Q1` remains `OPEN-PENDING-REVIEWER` — is the proof.

**The detection rule is engineering and ships unconditionally.** The gate's own docstring
declares the blind spot in writing: `test_no_cyrillic_msgids` says *"`msgstr` values for ru/bs
are naturally Cyrillic and exempt"* and inspects `msgid` only. That reasoning is right for
`ru` and **wrong for `bs`**, where Cyrillic is contamination by construction.

**Block outcomes — the `Q1` gate is `OPEN-PENDING-REVIEWER`, so the second row is the current one**

| `Q1` outcome | What ships |
|---|---|
| 🚧 **Current state — no reviewer sign-off yet (2026-10-03)** | **The detection rule plus a named, commented exemption for all three**, and the commit body says the gate is **`OPEN-PENDING-REVIEWER`**, not closed. `I18N-014`'s prune is unaffected. **When the sign-off arrives, a follow-up commit supplies the three values and removes the exemptions; the gate closes then** |
| **A linguist supplies all three** | The detection rule **and** the three corrected `msgstr` values, in one commit. The gate goes green having been red in the tree, and its failure is demonstrated in the same session |
| **A linguist supplies some** | The detection rule, the corrected ones, and a **named, commented exemption** for each string knowingly shipped as-is — with the commit body stating plainly that the finding is **not closed** for those |
| **Gate red on arrival with no exemption recorded** | **This commit must not be made.** Re-apply the previous `bs` content and re-plan. The gate is never committed red |

**File surface (semantic units)**

| File | Symbol / element | Change |
|---|---|---|
| `src/backend/apps/ads/tests/test_i18n_completeness.py` | `test_no_cyrillic_msgids` | **Add a sibling assertion, do not weaken the existing one.** A Cyrillic code point in a **`bs` `msgstr`** is a violation; a Cyrillic code point in a **`ru` `msgstr`** is correct and stays exempt. The rule is locale-scoped, which is why the existing blanket `msgstr` exemption can be narrowed without breaking `ru` |
| `src/backend/apps/ads/tests/` | a test for the `ru`-exempt / `bs`-contaminated distinction | Proves the rule is not "no Cyrillic anywhere", which would be wrong for `ru` |
| `src/backend/locale/bs/LC_MESSAGES/django.po` | the three `msgstr` values, addressed **by msgid** | Targeted entry edits only. Never regenerated. **Re-read all three `.po` files immediately before `git add`** (§1.6) |
| `src/backend/locale/{ru,en}/LC_MESSAGES/django.po` | — | **Untouched.** `ru`'s Cyrillic `msgstr`s are correct; `en` is empty by convention |

**Binding constraints**

1. **The `msgid` never changes.** These are `msgstr`-only corrections. Changing a `msgid`
   re-extracts the key and orphans the entry.
2. **No machine translation. No invented `bs`.** The three values are supplied by the `Q1`
   reviewer or they are exempted. This is the block's single hardest rule.
3. **The new assertion is locale-scoped.** `ru` legitimately contains 400+ Cyrillic `msgstr`s;
   a blanket "no Cyrillic in `msgstr`" rule would fail immediately and be disabled. The rule
   is: **Cyrillic in a `bs` `msgstr` is a violation; Cyrillic in a `ru` `msgstr` is correct.**
4. **The rule is about script, not about language quality.** It catches the *Cyrillic `а`
   inside `oglasa`* and the Russian verb. It cannot tell a fluent wrong-language translation
   from a right one, and it does not pretend to. A general quality gate is out of scope and
   would be a machine-translation judgement.
5. **The `Start` copy-through is NOT corrected here.** It is one of the six `I18N-014` orphans
   and BLOCK 10 **prunes** it. Fixing a string that is about to be deleted is wasted work.
6. **The six legitimate copy-through entries are not corrected**: `ID`, `Telegram ID:`,
   `Pro`, `Telegram`, `Google Translate`, `Plausible Analytics`. They are brand and product
   names that are correctly identical in Bosnian.
7. **The two `bs` plural entries that share `msgstr[1]`/`msgstr[2]` are CORRECT** for `bs`
   CLDR. Do not "correct" them.
8. **Any exemption is a named, commented entry with a reason and an owner** — not a
   `pytest.skip`. An exemption without a reason is how the next string opts out silently.
9. **§1.6 in full**: re-read before `makemessages`, re-read before `git add`, stage by path,
   never regenerate, never add a `.mo`.

**Implementor task**

```yaml
id: task_14_b09_bs_script_gate
title: "Add a bs-scoped msgstr script gate and apply the linguist-supplied corrections (N-1)"
priority: medium
depends_on: [task_14_b07_plural_parser, task_14_b08_gate_collectors]
source_reference: ".ai/plans/14-i18n-remediation.md"
source_section: "BLOCK 9 - A msgstr script gate, and the three real bs strings"
source_blocks: ["BLOCK 9"]
description: >
  One bs msgstr ends "Za kreiranje oglasa<cyrillic a> kooristi<cyrillic> /post." - a
  Croatian/Bosnian frame carrying the Russian verb and a Cyrillic character inside a Latin word.
  It is the only Cyrillic-bearing line in the bs catalogue and it renders to every Bosnian
  user. No gate catches it, and the reason is written into the gate itself: test_no_cyrillic_msgids
  declares msgstr values exempt because "msgstr values for ru/bs are naturally Cyrillic" - which
  is right for ru and wrong for bs, where Cyrillic is contamination by construction. The
  detection rule is engineering. The three corrected values are a human deliverable.
goals:
  - "a bs-scoped msgstr script rule exists and is demonstrated failing on the contaminated string"
  - "the three bs values are either corrected by a native reviewer or recorded as named, reasoned exemptions"
  - "ru's legitimate Cyrillic msgstrs stay correct and the gate stays green for them"
extra_context: |
  Q1 IS RULED but the GATE IS OPEN-PENDING-REVIEWER - 2026-10-03, Product Owner. Who signs off is
  decided: a native Bosnian reviewer, preferably Montenegrin. Machine output and translation APIs
  are NOT acceptable. NO SIGN-OFF EXISTS YET, so THIS BLOCK SHIPS ITS REDUCED DELIVERABLE NOW:
  the detection rule plus a named, commented exemption for all three strings, with the commit body
  recording the gate as OPEN-PENDING-REVIEWER rather than closed. THIS PLAN DOES NOT WRITE THEM
  AND THE IMPLEMENTOR IS FORBIDDEN FROM WRITING, GUESSING, MACHINE-TRANSLATING OR APPROXIMATING
  THEM. Phase 09's outbound Google-Translate client is explicitly NOT a catalogue tool. Project
  rule 1 makes every msgid English; the replacement is a bs value only a speaker can produce.
  Q2 DOES NOT GATE THIS BLOCK, and its 2026-10-03 answer (Option A) does not change that. The code
  context claims Option A for 14-I18N-013 would remove two of the three strings from scope; the
  tree does not support it. I18N-013 is about MODEL METADATA, a different surface from a template
  that is already in the gate's exclude_subpaths tuple. Q1 and Q2 are independent - and Q2
  resolving while Q1 stayed open is the proof.
  BINDING CONSTRAINTS (verbatim, from section 3 BLOCK 9)
  1. The msgid NEVER changes. These are msgstr-only corrections; changing a msgid re-extracts
     the key and orphans the entry.
  2. No machine translation, no invented bs.
  3. The new assertion is LOCALE-SCOPED. ru legitimately contains 400+ Cyrillic msgstrs; a
     blanket "no Cyrillic in msgstr" rule would fail immediately and be disabled. The rule is:
     Cyrillic in a bs msgstr is a violation; Cyrillic in a ru msgstr is correct.
  4. The rule is about SCRIPT, not language quality. It catches the Cyrillic character and the
     Russian verb. It cannot judge fluency and does not pretend to. A general quality gate is
     out of scope.
  5. The `Start` copy-through is NOT corrected here - it is one of the six 14-I18N-014 orphans
     and BLOCK 10 PRUNES it.
  6. The six legitimate copy-throughs are not corrected: ID, Telegram ID:, Pro, Telegram,
     Google Translate, Plausible Analytics.
  7. The two bs plural entries sharing msgstr[1] and msgstr[2] are CORRECT for bs CLDR.
  8. Any exemption is a named, commented entry with a reason and an owner - never a
     pytest.skip.
  9. Section 1.6 in full: re-read all three .po files immediately before any makemessages
     invocation and again immediately before git add; stage by path; never regenerate
     wholesale; never add a .mo file.
  10. If the gate would be red on arrival with no exemption recorded, THIS COMMIT MUST NOT BE
      MADE. Re-apply the previous bs content and re-plan.
  VERIFIED SYMBOL MAP (re-derived at d42f778; use symbols, never line numbers)
  - src/backend/apps/ads/tests/test_i18n_completeness.py -> test_no_cyrillic_msgids, whose
    docstring states msgstr values for ru/bs are naturally Cyrillic and exempt, and which
    iterates _parse_po_entries inspecting the msgid only
  - the three bs entries, addressed BY MSGID: the multi-line support-greeting msgid ending
    "To create an ad, use /post."; "Moderator #%(mid)s"; "Admin"
  - "Admin" is in scan scope - components/header.html and components/header_auth_entry.html
  - "Moderator #%(mid)s" is in analytics/moderation_dashboard.html, which IS in
    exclude_subpaths
  - bs has exactly 9 copy-through entries; 6 are legitimate, 3 are real, and "Start" is the
    4th and is an orphan pruned by BLOCK 10
  FORBIDDEN: editing a msgid; editing ru or en; filling en msgstrs; writing any bs text
  without the Q1 reviewer; correcting the shared bs plural forms; regenerating the catalogues.
files:
  - path: src/backend/apps/ads/tests/test_i18n_completeness.py
    targets:
      - type: function
        name: test_no_cyrillic_msgids
    changes: []  # ADD a sibling assertion; do not weaken the existing msgid-only rule
  - path: src/backend/apps/ads/tests/test_i18n_msgstr_script_unit.py
    targets: []
    changes: []  # new unit module proving the ru-exempt / bs-contaminated distinction
  - path: src/backend/locale/bs/LC_MESSAGES/django.po
    targets: []
    changes: []  # targeted msgstr-only edits by msgid; re-read immediately before git add
changes:
  - action: add_test
    description: >
      Add a locale-scoped assertion that a Cyrillic code point in a bs msgstr fails, while a
      Cyrillic code point in a ru msgstr is correct and stays exempt. Keep the existing
      msgid-only rule unchanged.
  - action: add_test
    description: >
      Add a unit test proving the rule distinguishes ru from bs, so a blanket no-Cyrillic rule
      cannot be substituted for it.
  - action: change_code
    description: >
      Apply the Q1 reviewer-supplied msgstr values by msgid, or record a named, commented
      exemption with a reason and an owner for each string knowingly shipped as-is.
acceptance_criteria:
  - "a Cyrillic code point in a bs msgstr fails the gate, and the failure was demonstrated on the current catalogue before the fix"
  - "a Cyrillic code point in a ru msgstr passes, and that pass was demonstrated too"
  - "the existing msgid-only Cyrillic rule is byte-identical to its pre-block state"
  - "every changed value came from the Q1 reviewer, or is a named exemption with a reason and an owner - no value was invented, guessed or machine-translated"
  - "the commit body records the Q1 gate as OPEN-PENDING-REVIEWER dated 2026-10-03, NOT as closed, and names the required reviewer (native Bosnian, preferably Montenegrin)"
  - "no msgid changed, and Start was left alone for BLOCK 10 to prune"
  - "the six legitimate copy-through entries and the two shared-form plural entries are untouched"
  - "ru and en catalogues are byte-identical to their pre-block state"
  - "the commit body states the Q1 outcome, and for every exempted string that the finding is NOT closed for it"
```

---

### BLOCK 10 — `--no-obsolete` and the one-shot prune (`14-I18N-014` limb 1, new `N-2`)

| | |
|---|---|
| **Findings owned** | `I18N-014` (LOW, first limb), **N-2** (new, LOW) |
| **Class** | **mechanical** — but the **single most dangerous operation in the phase** |
| **Depends on** | **BLOCK 7** (the plural-aware parser must exist before a catalogue is rewritten) |
| **Blocks** | BLOCK 11 |
| **Priority** | **P2** — placed after the gate work deliberately; the prune is the destructive half and the gate is the durable half |
| **Risk level** | **HIGH** — `--no-obsolete` **deletes entries by design**, six other phases are appending to the same three files, and a wrong prune is indistinguishable from a concurrent-phase conflict until someone notices a missing string |
| **Blast radius** | `src/backend/locale/{ru,bs,en}/LC_MESSAGES/django.po` — the most contended i18n artefact in the repository |
| **Required agents** | **Auditor · Planner · Validator** — all three. **A Validator must witness the before/after entry sets**; this is the one block where a silent deletion is the default failure mode |

**The defect.** Six msgids are present as **active** entries in all three catalogues and
absent from extraction: `Start`, `Language`, `Post ad`, `Alerts` (superseded by the
per-language `_COMMANDS` literals in `lifecycle.py`) plus two reworded strings
(`Please login first.`, and the wrapped `Cannot approve: …` message). `makemessages` without
`--no-obsolete` marks entries `#~` rather than removing them, and no gate compares the
catalogue against the source in the **removed** direction.

**✔ Strengthened by N-2 (C-4).** `ru` and `bs` already carry **6 `#~` obsolete entries
each**; `en` carries **0**. The report's "prune once" framing implies no `#~` blocks exist —
they do, in two of three catalogues, and the third disagrees. **This block is what makes them
agree.**

**The method constraint that makes this hard.** ✔ The sixth orphan is a **wrapped multi-line
`msgid ""` + continuation lines** in all three files, so a line-anchored regex silently misses
it. A literal-substring scan of the source over-reports **47** false positives (multi-line
`{% blocktrans %}` bodies and implicitly-concatenated Python literals whose rendered form
differs from the source literal). **This block must parse, not regex, and must enumerate the
entry set programmatically** — which is why it depends on BLOCK 7's parser.

**File surface (semantic units)**

| File | Element | Change |
|---|---|---|
| `Makefile` | the `makemessages` target's invocation | Add `--no-obsolete` alongside the existing `--no-location`. **The `Makefile` form does not run on Windows + Docker Desktop — the *flag contract* is what is being cited, not a runnable command** |
| `.kilo/rules/commands.md` | the "Extract" section's invocation | The same flag. **Both documented surfaces change in the same commit, or they disagree** |
| `src/backend/locale/{ru,bs,en}/LC_MESSAGES/django.po` | the obsolete + orphan entries | The one-shot prune |

**Binding constraints**

1. **Before the extraction: enumerate, with the parser, the exact set of entries that will
   disappear.** Do not eyeball a `git diff`. For each, record which of the two classes it is:
   (a) a reworded string whose replacement is already present, or (b) a genuine orphan. **A
   third class — a string another phase added in the last hour — must not appear.** If it
   does, **stop and report.**
2. **Re-read all three `.po` files immediately before the `makemessages` invocation** and
   **again immediately before `git add`** (§1.6). Six phases append to these files.
3. **The `POT-Creation-Date` header must stay identical across the three catalogues** —
   `test_pot_creation_date_sync` asserts it, and a mismatch sends the next person to the
   wrong conclusion about a race.
4. **`en` has 0 obsolete entries today and must still have 0 after.** The end state is
   obsolete-free in all three; the asymmetry is what this block resolves.
5. **The `lifecycle.py` command-menu strings are removed, not translated.** ✔ `Start`,
   `Language`, `Post ad` and `Alerts` are the residue of the twelve deliberate
   non-gettext `BotCommand` literals. Deleting them is correct. Translating them (BLOCK 9
   explicitly does not) would be wasted work on strings that never render.
6. **The six legitimate `#~` entries are the phase-04/06 consent-and-login strings** that
   were reworded in source. Their replacements are present; the `#~` blocks are simply
   history. Removing them changes nothing at runtime.
7. **Never regenerate wholesale and never add a `.mo`.** `.mo` is gitignored and is compiled at
   image build, at container start and in the CI `i18n` job.
8. **This block adds no msgid and no gate.** BLOCK 11 is the durable half. **The report is
   explicit that pruning once is a one-shot cleanup and the gate is the fix** — do not
   describe this block as closing `I18N-014`.
9. **Do not edit the bot's `lifecycle.py`.** The `BotCommand` literals are deliberate and are
   documented as such in the module. The orphans are the residue, not the cause.

**Implementor task**

```yaml
id: task_14_b10_po_prune
title: "Add --no-obsolete to both documented extractions and run the one-shot prune (14-I18N-014, N-2)"
priority: low
depends_on: [task_14_b07_plural_parser]
source_reference: ".ai/plans/14-i18n-remediation.md"
source_section: "BLOCK 10 - --no-obsolete and the one-shot prune"
source_blocks: ["BLOCK 10"]
description: >
  Six msgids are present as active entries in all three catalogues and absent from extraction,
  and ru and bs additionally carry six #~ obsolete entries each while en carries none. The
  documented extraction omits --no-obsolete in both places it is written down, so obsolete
  entries are marked rather than removed and the three catalogues disagree about their own
  history. Runtime impact is nil; the cost is that translators spend time on strings that
  never render and a reviewer grepping a .po can be misled into believing a code path is
  translated. This is the one-shot half only - BLOCK 11 adds the durable gate.
goals:
  - "both documented extraction invocations carry --no-obsolete"
  - "all three catalogues are obsolete-free and orphan-free after the prune"
  - "no string another phase added is deleted, and the entry-set change is enumerated before it is committed"
extra_context: |
  BINDING CONSTRAINTS (verbatim, from section 3 BLOCK 10)
  1. BEFORE the extraction, enumerate with the BLOCK 7 parser the EXACT set of entries that
     will disappear. Do not eyeball a git diff. For each, record whether it is (a) a reworded
     string whose replacement is present, or (b) a genuine orphan. A THIRD class - a string
     another phase added in the last hour - must not appear. If it does, STOP AND REPORT.
  2. Re-read all three .po files immediately before the makemessages invocation and again
     immediately before git add. Phases 03, 05, 06, 07, 08 and 10 all append to these files.
  3. POT-Creation-Date must stay IDENTICAL across the three catalogues -
     test_pot_creation_date_sync asserts it, and a mismatch sends the next person to the
     wrong conclusion about a race.
  4. en has 0 obsolete entries today and must have 0 after. The end state is obsolete-free in
     all three.
  5. The lifecycle.py command-menu strings are REMOVED, not translated. Start, Language, Post
     ad and Alerts are the residue of twelve deliberate non-gettext BotCommand literals.
  6. The six existing #~ entries are the phase-04/06 consent-and-login strings that were
     reworded in source; their replacements are present.
  7. Never regenerate wholesale; never add a .mo file.
  8. This block adds no msgid and no gate. BLOCK 11 is the durable half. Do NOT describe this
     block as closing 14-I18N-014.
  9. Do not edit src/telegram_bot/lifecycle.py - the BotCommand literals are deliberate and
     documented; the orphans are the residue, not the cause.
  METHOD CONSTRAINT - the sixth orphan is a WRAPPED MULTI-LINE msgid "" + continuation lines
  in all three files, so a line-anchored regex silently misses it, and a literal-substring scan
  of the source over-reports 47 false positives from multi-line blocktrans bodies and
  implicitly-concatenated Python literals. PARSE, do not regex.
  VERIFIED SYMBOL MAP (re-derived at d42f778; use symbols, never line numbers)
  - Makefile -> the `makemessages` target, currently
    `... makemessages -l ru -l bs -l en --no-location`
  - .kilo/rules/commands.md -> the "Extract" section, the same flags via the mko-bazuna-dev
    one-shot. BOTH surfaces change in the same commit or they disagree.
  - obsolete entries: ru 6, bs 6, en 0. The six are the same msgids in ru and bs.
  - the six active orphans are present 3/3: Start, Language, Post ad, Alerts, and two
    reworded strings, one of which is the wrapped Cannot-approve msgid
  FORBIDDEN: editing src/telegram_bot/lifecycle.py; editing the Makefile's compilemessages
  target; adding a .mo; describing this block as closing the finding.
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
    changes: []  # targeted prune only; re-read immediately before git add
  - path: src/backend/locale/bs/LC_MESSAGES/django.po
    targets: []
    changes: []  # targeted prune only; re-read immediately before git add
  - path: src/backend/locale/en/LC_MESSAGES/django.po
    targets: []
    changes: []  # targeted prune only; re-read immediately before git add
changes:
  - action: change_code
    description: >
      Add --no-obsolete to the makemessages invocation in the Makefile and in
      .kilo/rules/commands.md, in the same commit, keeping --no-location.
  - action: change_code
    description: >
      Run the prune once using the working Windows form from section 1.2 (make makemessages
      does not run on this environment), after enumerating the disappearing entry set with the
      BLOCK 7 parser and recording it in the commit body.
acceptance_criteria:
  - "the disappearing entry set is enumerated programmatically and recorded in the commit body, each item classified as reworded or orphan"
  - "no string added by another phase appears in the removal set; had one appeared, the block would have stopped and reported"
  - "all three catalogues have zero #~ obsolete entries and zero orphan msgids after the prune"
  - "POT-Creation-Date is byte-identical across the three catalogues"
  - "the msgid sets of the three catalogues remain identical to each other"
  - "ru and bs still have 0 fuzzy entries, 0 empty single-form msgstrs and 0 blank plural forms"
  - "en still has its documented empty msgstrs and was not filled"
  - "no .mo file appears in the diff"
  - "the commit body states that the durable gate is BLOCK 11 and that I18N-014 is not closed by this commit"
```

---

### BLOCK 11 — The reverse stale-entry gate and the obsolete-symmetry assertion (`14-I18N-014` limb 2, `N-2`)

| | |
|---|---|
| **Findings owned** | `I18N-014` (LOW, second limb), **N-2** (new, LOW, durable half) |
| **Class** | **behavioural** — a new assertion on a shared gate |
| **Depends on** | **BLOCK 7** (strict — needs the plural-aware parser), **BLOCK 8** (the named exemption set), **BLOCK 10** (strict — the tree must be clean before the gate is added, or it is red on arrival) |
| **Blocks** | BLOCK 12 |
| **Priority** | **P2** |
| **Risk level** | **MEDIUM** |
| **Blast radius** | The i18n completeness gate every phase depends on |
| **Required agents** | **Auditor · Planner · Validator** — three. No Researcher needed: the parsing approach is settled by BLOCK 7 |

**This is the durable half, and the report says so explicitly.** "Pruning once is a one-shot
cleanup; the durable fix is the gate." Only the **"added"** direction is currently gated
(`test_extraction_completeness` computes `all_msgids - msgids`; `test_template_extraction_coverage`
checks template msgids exist in every catalogue). **There is no reverse assertion**, so a
msgid that leaves the source stays in all three catalogues forever.

**The two assertions, in one block.** They read the same files and fail for the same root
cause — a missing reverse assertion — so splitting them would create two commits that both
touch the same module for one idea. **Q8 is resolved by this plan: the obsolete-asymmetry
assertion belongs to `I18N-014`, not to a separate item.**

**File surface (semantic units)**

| File | Symbol | Change |
|---|---|---|
| `src/backend/apps/ads/tests/test_i18n_completeness.py` | a new stale-entry assertion | Parse the catalogue msgid set with the BLOCK 7 parser and assert every entry is present in a real extraction of the source. **The documented exemption set from BLOCK 8 is read here** — the four `lifecycle.py` command-menu strings are its first member |
| `src/backend/apps/ads/tests/test_i18n_pipeline.py` | a new obsolete-symmetry assertion | Assert **no** `#~` obsolete block exists in **any** of the three catalogues. This is the durable form of BLOCK 10's prune |
| `src/backend/apps/ads/tests/` | a fixture-driven unit test | Feed the gate a synthetic orphan — **including a wrapped multi-line msgid** — and assert it fails. **A line-anchored regex misses the wrapped case; the test must prove the parse does not** |

**Binding constraints**

1. **Parse, never regex.** ✔ The sixth orphan is a wrapped multi-line `msgid ""`; a
   `^msgid "…"$` regex silently misses it. A literal-substring source comparison over-reports
   (47 false positives). The gate parses the catalogue with BLOCK 7's parser and compares
   against a **real extraction**, not a substring search.
2. **The exemption set is read from BLOCK 8's single definition**, with its reason attached.
   No second, divergent list.
3. **The obsolete assertion covers all three catalogues, not just `ru` and `bs`.** The
   asymmetry is the finding; an assertion that only checks two locales would let `en` drift
   the other way.
4. **Every new guard is demonstrated failing** — once with a synthetic orphan and once with a
   synthetic obsolete block — before the commit.
5. **Never hard-code a msgid count, a catalogue count or a template count.** ✔ The report's
   counts are stale (38 templates, 20 + 172 model metadata). Derive everything.
6. **`--no-location` stays on.** Without it the extraction references churn across ~408
   entries per catalogue and the diff becomes unreadable.
7. **This block adds no msgid and edits no catalogue.** If it needs a catalogue change to
   pass, BLOCK 10 did not finish — fix the cause, not the assertion.
8. **Do not extend the assertion into a translation-quality gate.** A stale-entry gate is a
   catalogue-hygiene guard. Quality is BLOCK 9's script rule and `Q1`'s linguist, nothing
   more.

**Implementor task**

```yaml
id: task_14_b11_stale_entry_gate
title: "Add the reverse stale-entry assertion and the obsolete-symmetry assertion (14-I18N-014, N-2)"
priority: low
depends_on: [task_14_b07_plural_parser, task_14_b08_gate_collectors, task_14_b10_po_prune]
source_reference: ".ai/plans/14-i18n-remediation.md"
source_section: "BLOCK 11 - The reverse stale-entry gate and the obsolete-symmetry assertion"
source_blocks: ["BLOCK 11"]
description: >
  Only the "added" direction of the catalogue is gated today: test_extraction_completeness
  computes all_msgids minus msgids, and test_template_extraction_coverage checks that template
  msgids exist in every catalogue. Nothing compares the catalogue against the source in the
  removed direction, so a msgid that leaves the source stays in all three catalogues forever.
  Separately, ru and bs carried six #~ obsolete entries each while en carried none, and no gate
  checks that dimension. BLOCK 10 resolved both once; this block makes them permanent.
goals:
  - "a msgid present in a catalogue but absent from a real extraction fails the gate"
  - "a #~ obsolete block in ANY of the three catalogues fails the gate"
  - "the wrapped multi-line msgid case is proven, not assumed"
extra_context: |
  BINDING CONSTRAINTS (verbatim, from section 3 BLOCK 11)
  1. PARSE, NEVER REGEX. The sixth orphan is a wrapped multi-line msgid "" + continuation
     lines; a ^msgid "..."$ regex silently misses it, and a literal-substring source comparison
     over-reports 47 false positives. The gate parses the catalogue with the BLOCK 7 parser and
     compares against a REAL EXTRACTION, not a substring search.
  2. The exemption set is read from BLOCK 8's single named definition, with its reason
     attached. No second, divergent list.
  3. The obsolete assertion covers ALL THREE catalogues, not just ru and bs. The asymmetry IS
     the finding; an assertion checking two locales lets en drift the other way.
  4. Demonstrate every new guard failing before the commit - once with a synthetic orphan and
     once with a synthetic obsolete block.
  5. NEVER hard-code a msgid count, a catalogue count or a template count.
  6. --no-location stays on.
  7. This block adds no msgid and edits no catalogue. If it needs a catalogue change to pass,
     BLOCK 10 did not finish - fix the cause, not the assertion.
  8. Do not extend the assertion into a translation-quality gate.
  VERIFIED SYMBOL MAP (re-derived at d42f778; use symbols, never line numbers)
      - src/backend/apps/ads/tests/test_i18n_completeness.py -> test_extraction_completeness,    test_template_extraction_coverage, the exclusion set introduced by BLOCK 8
  - src/backend/apps/ads/tests/test_i18n_pipeline.py -> test_pot_creation_date_sync, and the
    natural home for the obsolete-symmetry assertion
  - src/backend/testing/i18n_helpers.py -> _parse_po_entries as changed by BLOCK 7
  - the BLOCK 8 exemption set's first member is the four lifecycle.py command-menu msgids
  FORBIDDEN: editing a .po file; regex-based matching; hard-coding counts; adding a quality
  judgement to a hygiene assertion.
files:
  - path: src/backend/apps/ads/tests/test_i18n_completeness.py
    targets: []
    changes: []  # new stale-entry assertion; do not weaken existing assertions
  - path: src/backend/apps/ads/tests/test_i18n_pipeline.py
    targets: []
    changes: []  # new obsolete-symmetry assertion
  - path: src/backend/apps/ads/tests/test_i18n_stale_entry_unit.py
    targets: []
    changes: []  # new unit module: synthetic orphan incl. a wrapped multi-line msgid
changes:
  - action: add_test
    description: >
      Add an assertion that every msgid in every catalogue is present in a real extraction of
      the source, reading BLOCK 8's named exemption set. Parse the catalogue; never regex it.
  - action: add_test
    description: >
      Add an assertion that no #~ obsolete block exists in ANY of the three catalogues, the
      durable form of BLOCK 10's one-shot prune.
  - action: add_test
    description: >
      Add a fixture-driven unit test that feeds the gate a synthetic orphan, including a
      wrapped multi-line msgid, and asserts it fails - proving the parse catches the case a
      regex misses.
acceptance_criteria:
  - "a synthetic orphan msgid fails the gate, demonstrated before the commit"
  - "a synthetic wrapped multi-line orphan msgid ALSO fails, and that case is explicitly covered by a test"
  - "a synthetic #~ block in each of ru, bs and en fails the obsolete-symmetry assertion, demonstrated before the commit"
  - "the exemption set is read from BLOCK 8's single definition, with its reason attached"
  - "no regex-based msgid matching anywhere in the new assertions"
  - "no msgid count, catalogue count or template count is hard-coded"
  - "the full i18n gate is green on arrival, including test_i18n_category_city.py"
  - "no .po file was modified by this block"
  - "the commit body states that this, with BLOCK 10, is what closes 14-I18N-014"
```

---

### BLOCK 12 — `i18n-spec.md` brought back in line (doc claims, new `N-3` and `N-4`, `I18N-013` Option A)

| | |
|---|---|
| **Findings owned** | `I18N-001`, `I18N-002`, `I18N-004`, `I18N-012`, `I18N-015` (documentation limbs), **N-3** (new), **N-4** (new), `I18N-013` — **now the SOLE home of `I18N-013`** (Option A, ruled 2026-10-03) |
| **Class** | **mechanical** — no behaviour change at all |
| **Depends on** | **BLOCKS 1, 5, 6, 9** (the document describes the behaviour those blocks establish, and writing it earlier would institutionalise a claim the code does not yet make) |
| **Blocks** | **nothing** — was "BLOCK 13", which is **CANCELLED** as of 2026-10-03 |
| **Priority** | **P2**, and deliberately **last among the code blocks** |
| **Risk level** | **LOW** for behaviour, **MEDIUM** for contention — phase 12 holds a conditional claim on `docs/99-agent/rules.md` |
| **Blast radius** | The phase's authoritative document, plus the agent-rules file four other phases read |
| **Required agents** | **Auditor · Planner · Validator** — the Validator's job here is to check every claim against the tree, not to read for prose quality |

**Gated on `Q11` (the dead links). The Option A limb is UNCONDITIONAL: `Q2` was resolved on
2026-10-03 (Option A), so the model-metadata exemption is written here as a matter of course and
this block is the only place `I18N-013` is delivered.**

**The doc claims this block must correct or make true**

| Claim in `docs/01-spec/i18n-spec.md` | What the code actually does (after BLOCK 1) | Block |
|---|---|---|
| "The resolved code is normalized by `LanguageLocale.from_code()`" — stated **unconditionally** | True for `?lang=` and, after BLOCK 1, for all three sources. **Today it is false for the cookie branch** — that is `I18N-001`'s `SPEC-DEVIATION` classification | 1 |
| The submenu cache-key locale is `request.LANGUAGE_CODE or "ru"` | ✔ True, and after BLOCK 1 the value is always a `LanguageLocale` member. The document currently **describes the unvalidated value — so the doc and the code agree and both are the defect** | 1, 2 |
| Silent on `Accept-Language` q-values | After BLOCK 1 the rule is: parse `(tag, q)`, drop `q=0`, sort descending, first supported tag, then fall back. **State the rule either way** | 1 |
| Silent on `TIME_ZONE` and on the date patterns | After BLOCK 5 both are explicit | 5 |
| The middleware docstring's cache contract | Already corrected in BLOCK 6; the spec should point at it rather than restate it | 6 |
| **3 dead link targets, referenced 5×** | `../99-agent/i18n-translation-pipeline-gap-analysis.md` (×3), `../99-agent/i18n-definition-of-done-research.md` (×1), `../96-researches/i18n-translation-egress.md` (×1). **The whole `docs/96-researches/` directory does not exist** | **N-3** |
| **Stale line citations** | The settings block is cited as `L55`-`L62`; `Ad.get_title`/`get_description` are cited as one span `L464-487` but are two distinct methods. **Every line anchor in the validated report has drifted too** | **N-4** |
| Whether model metadata is exempt from the i18n DoD | **Unstated** — that is `I18N-013`. **Option A named the exemption, and the Product Owner chose Option A on 2026-10-03** — this block writes it, and it is the only place it is written | **12** (BLOCK 13 is CANCELLED) |

**`Q11` — the three dead links.** Options: (a) **delete the three references** and fold their
content into `i18n-spec.md` (the honest, cheapest option — the sources were research notes
that were never committed); (b) re-point them at the nearest live documents — **but that
asserts those documents contain content they may not contain**; (c) replace the link with a
non-link pointer. **The Implementor may not choose. Option (a) is the Planner's
recommendation.**

**File surface (semantic units)**

| File | Element | Change |
|---|---|---|
| `docs/01-spec/i18n-spec.md` | "Runtime Language Resolution (Web UI)" | The normalisation claim, the `Accept-Language` q-value rule, the priority table |
| | "Submenu Cache Localization" | The `<locale>` segment's contract |
| | the timezone / date-format section (add if absent) | `TIME_ZONE` and the four display formats; the two ISO attributes are documented as **machine-readable and locale-independent** |
| | the cache / `Vary` section | Point at the middleware docstring BLOCK 6 corrected; do **not** restate a contract the middleware no longer claims |
| | the i18n coverage / exemptions section | **Option A only:** name **model metadata** as an explicit exemption alongside the three existing template exclusions, so the coverage claim is accurate |
| | the whole document | **N-3** dead links and **N-4** stale line citations |
| `docs/99-agent/rules.md` | the scan-scope bullet and the i18n DoD section | **Read before writing — phase 12 holds a conditional claim** (§5.3). Records the BLOCK 8 exemption set and, under Option A, the model-metadata exemption |

**Binding constraints**

1. **The spec describes what the code does — never what the code should do.** Every claim is
   checked against the tree at commit time, not against the report. A documentation edit that
   outruns the code is the same defect class as `I18N-001`.
2. **No line numbers as citations.** ✔ N-4. Cite a file path plus a symbol, or a section
   heading. This is a standing project rule, not only a plan rule.
3. **The `Makefile` and `.kilo/rules/commands.md` extraction forms are already correct**
   (BLOCK 10 changed them) — do not "correct" them again, and do not restate them in the spec
   as runnable commands on a platform where they do not run.
4. **The model-metadata exemption MUST be written in this block.** ✔ `Q2` was resolved on
   2026-10-03 — Option A — so the exemption names model metadata explicitly and sits
   alongside the three existing exclusions (`admin/`, `analytics/moderation_dashboard.html`,
   `components/feature_tag.html`). **Option B was declined and BLOCK 13 is CANCELLED**, so there
   is no Option-B limb to skip and no second place `I18N-013` may be documented. **No catalogue
   entry is added here** — Option A costs nothing at runtime, and the admin tests asserting
   English field text **stay unchanged** because no `gettext_lazy` wrapping happened.
5. **`docs/01-spec/technical-specification.md` is phase 06's.** Do not touch it. If the
   `lang_pref` cookie needs naming there, that is BLOCK 6's deferred limb (§5.3).
6. **`docs/01-spec/spec-index.md` is phase 06's sole file.** Do not touch it.
7. **Do not restore, recreate or reconstruct the three missing research documents.** They were
   never committed; inventing them would be fabrication.
8. **A correction states what is true now, not what was wrong before.** A reader needs the
   contract, not the changelog.

**Implementor task**

```yaml
id: task_14_b12_i18n_spec
title: "Bring i18n-spec.md and the agent rules back in line with the code (I18N-001/-002/-004/-012/-015 doc limbs, N-3, N-4, I18N-013 Option A)"
priority: low
depends_on: [task_14_b01_locale_resolver, task_14_b05_timezone_and_dates, task_14_b06_lang_pref_cookie, task_14_b09_bs_script_gate]
source_reference: ".ai/plans/14-i18n-remediation.md"
source_section: "BLOCK 12 - i18n-spec.md brought back in line"
source_blocks: ["BLOCK 12"]
description: >
  docs/01-spec/i18n-spec.md is phase 14's authoritative document and it currently (a) states
  unconditionally that the resolved code is normalized by LanguageLocale.from_code(), which was
  false for the cookie branch; (b) is silent on Accept-Language q-values; (c) is silent on
  TIME_ZONE and the date patterns; (d) points at three documents that do not exist, five times
  in total, including the entire docs/96-researches/ directory; and (e) carries stale line
  citations. Under I18N-013 Option A it must also name model metadata as an explicit exemption
  so the coverage claim is accurate.
goals:
  - "every claim in the spec matches the code at commit time, verified against the tree"
  - "the three dead link targets are resolved per the Q11 answer, without inventing documents"
  - "no line number is used as a citation anywhere in the corrected sections"
extra_context: |
  GATES. Q11 (the three dead links) must be answered first: option (a) delete the references
  and fold the content into i18n-spec.md; option (b) re-point at the nearest live documents,
  which asserts those documents contain content they may not contain; option (c) a non-link
  pointer. Q2 decides the I18N-013 Option A limb - under Option B this limb is not written here
  and BLOCK 13 does the code instead.
  BINDING CONSTRAINTS (verbatim, from section 3 BLOCK 12)
  1. The spec describes what the code DOES, never what it should do. Every claim is checked
     against the tree at commit time, not against the report. Documentation that outruns the
     code is the same defect class as 14-I18N-001.
  2. NO LINE NUMBERS as citations. Cite a file path plus a symbol, or a section heading.
  3. Do not "correct" the Makefile or .kilo/rules/commands.md extraction forms again - BLOCK
     10 already owns them - and do not restate them in the spec as runnable commands on a
     platform where they do not run.
  4. Under Q2 Option A, name MODEL METADATA as an explicit exemption alongside the three
     existing template exclusions. Under Option B, do not write that limb here.
  5. Do NOT touch docs/01-spec/technical-specification.md (phase 06 holds it) or
     docs/01-spec/spec-index.md (phase 06's sole file).
  6. Read docs/99-agent/rules.md before writing to it - phase 12 holds a CONDITIONAL claim on
     that file.
  7. Do NOT restore, recreate or reconstruct the three missing research documents. They were
     never committed; inventing them would be fabrication.
  8. A correction states what is TRUE NOW, not what was wrong before.
  VERIFIED DEAD TARGETS (re-verified at d42f778)
  - ../99-agent/i18n-translation-pipeline-gap-analysis.md - referenced 3x, file absent
  - ../99-agent/i18n-definition-of-done-research.md - referenced 1x, file absent
  - ../96-researches/i18n-translation-egress.md - referenced 1x, and the whole docs/96-researches
    directory does not exist
  - docs/99-agent/ contains architecture.md, dependency-risk-register.md, references.md,
    rules.md and three test-audit files
  - the surviving relative links in i18n-spec.md that ARE live must stay live: the
    ../02-database/ and ../99-agent/architecture.md targets
  FORBIDDEN: editing any code file; editing a .po file; creating a missing research document;
  citing a line number; touching technical-specification.md or spec-index.md.
files:
  - path: docs/01-spec/i18n-spec.md
    targets:
      - type: markdown_section
        name: Runtime Language Resolution (Web UI)
      - type: markdown_section
        name: Submenu Cache Localization
  - path: docs/99-agent/rules.md
    targets: []
    changes: []  # read-before-write; phase 12 holds a conditional claim
changes:
  - action: change_doc
    description: >
      Correct the unconditional normalisation claim to describe the actual three-source
      priority chain and its normalisation guarantee, and state the Accept-Language q-value
      rule either way.
  - action: change_doc
    description: >
      Document TIME_ZONE and the four display formats, and state explicitly that the two
      <time datetime="...|date:'Y-m-d'"> attributes are machine-readable ISO values that are
      locale-independent by design.
  - action: change_doc
    description: >
      Resolve the three dead link targets per the Q11 answer and remove every stale line
      citation, replacing them with symbol or section references.
  - action: change_doc
    description: >
      Under Q2 Option A only: name model metadata as an explicit exemption in the i18n
      coverage section, alongside the three existing template exclusions.
acceptance_criteria:
  - "every claim in the corrected sections was verified against the tree, not against the report"
  - "no line number appears as a citation in any corrected section"
  - "no link in the document points at a non-existent file, and no missing research document was invented"
  - "the links that were already live are still live"
  - "the Accept-Language q-value rule and the TIME_ZONE value are stated explicitly"
  - "the two ISO datetime attributes are documented as locale-independent machine-readable values"
  - "under Option A, model metadata is named as an explicit exemption; under Option B, that text is absent"
  - "docs/01-spec/technical-specification.md and docs/01-spec/spec-index.md are untouched"
  - "docs/99-agent/rules.md was re-read before editing and no concurrent change was clobbered"
```

---

### BLOCK 13 — `I18N-013` Option B: translate the model metadata (`14-I18N-013`) — ❌ **CANCELLED 2026-10-03**

> ## 🚫 THIS BLOCK IS CANCELLED. IT DOES NOT RUN. THERE IS NO COMMIT, NO TASK AND NO FILE.
>
> **`Q2` was resolved on 2026-10-03 by the Product Owner: Option A.** Model `verbose_name` /
> `help_text` is documented as an **explicit, named exemption** in the i18n coverage rule,
> following the existing documented exemption for the `admin/` template subtree. **Option B —
> wrapping ~192 entries in `gettext_lazy` — is DECLINED.**
>
> **Consequences, recorded so nothing is silently dropped:**
> 1. **`I18N-013` is delivered by BLOCK 12's documentation and nowhere else.** BLOCK 12 is now
>    the **sole home** of this finding.
> 2. **This block is cancelled — not deferred, not de-scoped, not "later".**
> 3. **No catalogue growth.** The ~192 `ru`/`bs` entries below are **not** added; the three
>    `django.po` files gain nothing from this block.
> 4. **The admin tests asserting English field text stay UNCHANGED.** Project rule 2 is not
>    invoked anywhere here, because no production behaviour changed.
> 5. **No `models.py` file is edited.** No `gettext_lazy` import is added anywhere.
>
> Everything below is retained **as the record of what was declined and why** — the costed
> option table is what makes the cancellation reviewable. **An Implementor must not re-open
> Option B, must not "finish it later", and must not create the `task_14_b13_model_metadata_i18n`
> task.** The only legitimate follow-up is a **new Product Owner decision**, recorded as such.

| | |
|---|---|
| **Status** | ❌ **CANCELLED 2026-10-03** — `Q2` → Option A. Not deferred. |
| **Findings owned** | `I18N-013` — **delivered by BLOCK 12**, not here |
| **Class** | **cancelled** (was `conditional` — "ships nothing at all if `Q2` resolves to Option A") |
| **Depends on** | BLOCK 12 (its Option A limb) — the dependency that **cancelled** this block |
| **Blocks** | nothing |
| **Required agents** | **none** — no agent is dispatched |

**The outcome this block always described, now realised.** Under Option A the block is
cancelled, BLOCK 12's documentation limb closes the finding, and the phase is complete without it.
**That is no longer "the recommended outcome the Implementor may not assume" — it is the
decision.**

**What Option B would have cost, measured — retained as the record of the declined option. None of
it is paid.**

| Metric | Count (✔ re-verified at `d42f778`, C-3) |
|---|---|
| `verbose_name` / `verbose_name_plural` assignments | **20** |
| `help_text` assignments | **172** |
| Of those, already wrapped in `gettext_lazy` | **0** |
| `gettext` occurrences in any `apps/*/models.py` | **0** |
| `models.py` files carrying any metadata | **11** (`ads`, `analytics`, `categories`, `core`, `currencies`, `locations`, `lookups`, `media`, `moderation`, `search`, `users`) |
| **Catalogue growth** | **~192 entries**, not the report's ~187 and not the context's ~187 |
| `help_text` distribution | `users` 29, `ads` 42, `core` 19, `moderation` 17, `search` 16, `analytics` 12, `categories` 10, `lookups` 9, `currencies` 7, `locations` 5, `media` 5 |
| `verbose_name` distribution | `core` 8, `categories` 5, `lookups` 2, `moderation` 2, `users` 2, `locations` 1 |
| `admin.py` modules affected | **8** |

**Constraints that applied to Option B only, retained as the record of the declined option. None
of them binds anyone now that the block is cancelled — in particular constraint 4 (project rule 2,
admin tests follow corrected behaviour) is NOT invoked, because no production behaviour changed.**

1. **Option B had to be chosen in writing.** It was not; it was declined. **This block is
   cancelled, not deferred-and-partially-done.**
2. **Every new msgid is English.** Project rule 1. `verbose_name` and `help_text` are
   developer documentation today; making them msgids means every one becomes a translator
   obligation. **That is the cost of Option B and it should be restated in the commit body.**
3. **`gettext_lazy`, never `gettext`.** A module-level `gettext` call freezes the string at
   import time — the same trap the `lifecycle.py` comment documents. This is not a stylistic
   preference.
4. **Production code is king.** Admin tests that assert English field text **follow the
   corrected behaviour**. They are not a constraint on the change and must not be weakened to
   accommodate the old output.
5. **✔ The `bs` `msgstr` values for ~192 entries are a `Q1` linguist deliverable — this block
   does not write them.** A bulk machine translation of admin metadata is exactly the naive
   move §6.3 forbids. **If no reviewer is available, Option B cannot complete, and the correct
   outcome is to return to the owner and re-ask `Q2`, not to ship English `bs` values.**
6. **§1.6 in full.** ~192 entries means a large, conflict-prone `.po` diff against six other
   appending phases. Re-read before the extraction and again before `git add`; stage by path.
7. **The counts in this block are the tree's, not the report's.** ✔ The report says 18 + 169
   and the code context repeats it; the tree says **20 + 172**. Do not "helpfully" make the
   catalogue match the report's estimate.
8. **No `ModelAdmin` layout, list_display, or searchfield change.** This block changes the
   *text*, not the admin's structure.

**Implementor task — ❌ NOT ISSUED. Retained only to show what was declined; do not create this task.**

```yaml
cancelled: true
cancelled_on: "2026-10-03"
cancelled_by: "Product Owner"
cancellation_basis: "Q2 resolved to Option A; Option B declined. I18N-013 is delivered by BLOCK 12."
id: task_14_b13_model_metadata_i18n   # NOT CREATED - recorded so the ID is visibly retired
title: "CANCELLED - Wrap model verbose_name and help_text in gettext_lazy (~192 entries) (14-I18N-013, Option B)"
priority: none
depends_on: []
source_reference: ".ai/plans/14-i18n-remediation.md"
source_section: "BLOCK 13 - I18N-013 Option B (CANCELLED)"
source_blocks: ["BLOCK 13"]
description: >
  CANCELLED 2026-10-03 by the Product Owner. Q2 resolved to Option A: model verbose_name and
  help_text are documented as an explicit, named exemption in the i18n coverage rule, following
  the existing documented exemption for the admin/ template subtree. Option B - wrapping ~192
  entries in gettext_lazy - is DECLINED. This task is NOT created, NOT dispatched, and NOT
  partially executed. No models.py file is edited, no catalogue entry is added, and the admin
  tests asserting English field text stay unchanged.
goals:
  - "none - the block is cancelled"
  - "every verbose_name, verbose_name_plural and help_text is a gettext_lazy msgid"
  - "the catalogue grows by ~192 entries with non-empty ru and bs msgstr"
  - "existing admin tests that assert English field text are updated to the localised output"
extra_context: |
  GATE: Q2 must be answered OPTION B in writing. Otherwise this block is CANCELLED, not
  partially done. The Planner's recommendation is Option A, but the Implementor may not act on
  it.
  BINDING CONSTRAINTS (verbatim, from section 3 BLOCK 13)
  1. Q2 must be answered Option B in writing; otherwise the block is cancelled.
  2. Every new msgid is ENGLISH (project rule 1). Making these msgids creates ~192 translator
     obligations - restate that cost in the commit body.
  3. gettext_lazy, NEVER gettext. A module-level gettext call freezes the string at import
     time - the same trap the src/telegram_bot/lifecycle.py comment documents.
  4. PRODUCTION CODE IS KING. Admin tests asserting English field text follow the corrected
     behaviour. They are not a constraint and must not be weakened to accommodate the old
     output.
  5. The bs msgstr values for ~192 entries are a Q1 LINGUIST deliverable. This block does not
     write them. A bulk machine translation of admin metadata is explicitly forbidden. If no
     reviewer is available, Option B CANNOT COMPLETE - the correct outcome is to return to the
     owner and re-ask Q2, not to ship English bs values.
  6. Section 1.6 in full. ~192 entries means a large, conflict-prone .po diff against six other
     appending phases.
  7. The counts here are the TREE's, not the report's: 20 verbose_name + 172 help_text. The
     report and the code context both say 18 + 169; do not make the catalogue match the
     report's estimate.
  8. No ModelAdmin list_display, searchfield or layout change. This block changes the TEXT,
     not the admin's structure.
  VERIFIED SYMBOL MAP (re-derived at d42f778; use symbols, never line numbers)
  - 11 models.py files carry metadata: ads, analytics, categories, core, currencies,
    locations, lookups, media, moderation, search, users
  - 8 admin.py modules: ads, analytics, categories, core, locations, lookups, moderation, users
  - help_text distribution: users 29, ads 42, core 19, moderation 17, search 16, analytics 12,
    categories 10, lookups 9, currencies 7, locations 5, media 5
  - verbose_name distribution: core 8, categories 5, lookups 2, moderation 2, users 2,
    locations 1
  FORBIDDEN: using gettext instead of gettext_lazy; writing bs values without the Q1 reviewer;
  editing a ModelAdmin's structure; regenerating the catalogues wholesale; changing any
  msgid that is not one of the ~192 new model-metadata strings.
files:
  - path: src/backend/apps/ads/models.py
    targets: [{ type: class, name: "Ad" }]
  - path: src/backend/apps/users/models.py
    targets: [{ type: class, name: "User" }]
  - path: src/backend/apps/core/models.py
    targets: []
  - path: src/backend/apps/moderation/models.py
    targets: []
  - path: src/backend/apps/search/models.py
    targets: []
  - path: src/backend/apps/analytics/models.py
    targets: []
  - path: src/backend/apps/categories/models.py
    targets: [{ type: class, name: "Category" }]
  - path: src/backend/apps/lookups/models.py
    targets: []
  - path: src/backend/apps/currencies/models.py
    targets: []
  - path: src/backend/apps/locations/models.py
    targets: []
  - path: src/backend/apps/media/models.py
    targets: []
  - path: src/backend/locale/ru/LC_MESSAGES/django.po
    targets: []
    changes: []  # ~96 new entries; linguist-supplied; re-read immediately before git add
  - path: src/backend/locale/bs/LC_MESSAGES/django.po
    targets: []
    changes: []  # ~96 new entries; linguist-supplied; re-read immediately before git add
changes:
  - action: add_code
    description: >
      Wrap every verbose_name, verbose_name_plural and help_text literal in gettext_lazy and
      add the gettext_lazy import to each of the 11 models.py modules that needs one.
  - action: change_code
    description: >
      Run the extraction per section 1.2 and populate non-empty ru and bs msgstr for the ~192
      new entries with linguist-supplied values.
  - action: change_test
    description: >
      Review the existing admin tests that assert English field text and update them to the
      localised output. Weakening or skipping them is not acceptable.
acceptance_criteria:
  - "N/A - the block is CANCELLED. The verifiable consequence is that: no models.py changed, no catalogue entry added, no admin test changed, and BLOCK 12's documentation limb names the model-metadata exemption"
```

---

## 4. Dependency graph

### 4.1 The safe serial order

The block numbering **is** the order. It is chosen so that the phase's four process hazards —
the `VAL-003` false-green test, the `I18N-003` half-fix, the `.po` race, and the `base.py`
collision — are each concentrated into the smallest number of writes, and so that no block
depends on a decision that has not been made.

| # | Block | Why here |
|---|---|---|
| 1 | One locale resolver | The P0. Nothing about locale resolution can be reasoned about until it is correct, and `I18N-011`, `I18N-002` and `I18N-012` are all weaker without it |
| 2 | Accessor and filter typing | Immediately after 1 — the report is explicit that the typing is sequenced **after** the normalisation so the value has already passed through the enum |
| 3 | Price formatting + the `bs` grouping decision | Independent of 1 and 2, so it ships early. **Its own gate (`Q3`) is the first technical decision in the phase** |
| 4 | The price chip | Strictly after 3 — the chip must use the corrected helper, or BLOCK 3's fix leaves a second unformatted price on the same page |
| 5 | `TIME_ZONE` and the date patterns | Independent. Placed before 6 so the six-way-contended `base.py` write happens while the queue of other blocks is still short. **`Q4` resolved 2026-10-03 — hard-coded `Europe/Podgorica`, not env-overridable** |
| 6 | `lang_pref` writer, flags, cache contract | After 1 (the write path depends on the resolver). Gated on `Q5`, a **phase-06 boundary** |
| 7 | Plural-aware `.po` parser | Before every block that parses a catalogue |
| 8 | Collector widening + `hreflang` | Before 9, which reads the exemption set 8 defines. Gated on the `Q9` pre-block step |
| 9 | `msgstr` script gate + the three `bs` strings | After 7 (the parser) and 8 (the exemption set). **Reduced deliverable while `Q1` is `OPEN-PENDING-REVIEWER`** (ruled 2026-10-03, sign-off not yet in) |
| 10 | `--no-obsolete` + the one-shot prune | After 7 (it must parse before it deletes). **Placed after 9 so the three real `bs` strings are judged before the prune removes the fourth** |
| 11 | Reverse stale-entry gate + obsolete-symmetry | **Strictly after 10** — the tree must be clean before the gate that asserts it is clean is added |
| 12 | `i18n-spec.md` | After 1, 5, 6 and 9. The spec describes behaviour; writing it earlier institutionalises a claim the code does not make. **Sole home of `I18N-013` (Option A, ruled 2026-10-03)** |
| 13 | `I18N-013` Option B | ❌ **CANCELLED 2026-10-03** — `Q2` resolved to Option A. No task, no commit, no file |

### 4.2 The DAG and why each edge exists

```
                    ┌──────────────────────────────────────────────┐
                    │                                              │
                    ▼                                              │
              ┌───────────┐                                       │
              │  BLOCK 1  │  resolver (I18N-001 limb1, -015, -002)│
              └─────┬─────┘                                       │
                    │  1→2  normalisation must exist before the    │
                    │       type is tightened (report's explicit   │
                    │       sequencing: doing it in the other     │
                    │       order leaves a window where both are   │
                    │       half-done)                            │
                    ▼                                             │
              ┌───────────┐                                       │
              │  BLOCK 2  │  accessor/filter typing (Q6)           │
              └─────┬─────┘                                       │
                    │                                             │
                    ├──► BLOCK 6 ──► BLOCK 12                     │
                    │      │                                       │
                    │      │  1→6  the cookie WRITE path is        │
                    │      │       reached through _apply_lang_    │
                    │      │       param, which BLOCK 1 changed.   │
                    │      │       Touching the write path before  │
                    │      │       the resolver exists re-opens    │
                    │      │       I18N-001 through the door the   │
                    │      │       fix came in.                     │
                    │      │                                       │
                    │      │  6→12  the cache-contract text in the  │
                    │      │       spec must describe the docstring │
                    │      │       BLOCK 6 corrected                │
                    │      │                                       │
                    └──────┼──────────────────────────────────────┘
                           │
  ┌───────────┐            │            ┌───────────┐
  │  BLOCK 3  │ price + Q3 │            │  BLOCK 5  │ TZ + Q4
  └─────┬─────┘            │            └─────┬─────┘
        │  3→4             │                  │  5→12
        ▼                  │                  │
  ┌───────────┐            │                  │
  │  BLOCK 4  │ chip       │                  │
  └───────────┘            │                  │
                           │                  │
              ┌────────────┴──────────────────┴──────┐
              │            BLOCK 7  (parser)         │
              └──────┬─────────────────────┬─────────┘
                     │ 7→9  7→10          │  7→11
                     │     the parser must  │  strict: a credible
                     │     parse a plural    │  stale-entry gate
                     │     entry before a   │  needs the plural-aware
                     │     catalogue is     │  parser, because one of
                     │     rewritten        │  the six orphans is a
                     ▼     ▼                 │  WRAPPED multi-line msgid
              ┌───────────┐  ┌───────────┐  │
              │  BLOCK 8  │  │  BLOCK 10 │  │  ──► BLOCK 11
              └─────┬─────┘  └─────┬─────┘  │      reverse gate +
                    │  8→9           │       │      obsolete symmetry
                    │  BLOCK 9 reads  │  10→11│
                    │  BLOCK 8's      │  STRICT│
                    │  named exemption│  the  │
                    │  set            │  tree │◄─┘
                    │  (the four     │  must │
                    │  lifecycle.py   │  be   │
                    ▼  command msgids)│ clean │
              ┌───────────┐           │ first │
              │  BLOCK 9  │ Q1 OPEN-  │       │
              └─────┬─────┘           │       │
                    │  9→10            │       │
                    │  the three real  │       │
                    │  bs strings are  │       │
                    │  judged BEFORE   │       │
                    │  the prune       │       │
                    │  removes the 4th  │       │
                    │  (Start)         │       │
                    │  9→12            │       │
                    ▼                  ▼       │
              ┌───────────────────────────┐   │
              │  BLOCK 12  i18n-spec.md   │◄──┘
              └─────────────┬─────────────┘
                            │ 12→13
                            ▼
┌───────────────────────────┐
               │  BLOCK 13  I18N-013 Opt B │  CANCELLED 2026-10-03 (Q2 = A)
               └───────────────────────────┘
```

**Every edge, and what it would cost to remove**

| Edge | Why it exists | What breaks if removed |
|---|---|---|
| **1 → 2** | BLOCK 1 makes the resolved value a `LanguageLocale`; BLOCK 2 makes the type enforce it. The reverse order tightens signatures while the cookie still delivers an arbitrary `str` | A window where the annotations promise a guarantee nothing enforces — and `basedpyright` goes quiet about the one call site that actually needs the warning |
| **1 → 6** | BLOCK 6 edits `process_response`'s cookie write; the value it writes is the resolved canonical code produced by BLOCK 1 | `httponly=True` lands on a write path that still persists a raw cookie value, and `I18N-001` is re-opened through the persistence path |
| **3 → 4** | The chip must use BLOCK 3's corrected helper | Two price formats on one response again, and the chip inherits the **old** behaviour permanently while looking fixed |
| **5 → 12** | The spec must describe the timezone and formats BLOCK 5 established | The spec documents a value the code does not use — the same `SPEC-DEVIATION` class as `I18N-001` |
| **6 → 12** | BLOCK 12 points at BLOCK 6's corrected docstring rather than restating the cache contract | Two competing descriptions of one contract, and the one that outlives a later middleware change is the wrong one |
| **7 → 9** | BLOCK 9's gate reads catalogues through the parser | The gate parses plurals wrongly and misses a class of violation |
| **7 → 10** | BLOCK 10 must **enumerate before it deletes**, and enumeration is a parse | A destructive prune with a regex-derived list — the exact method the report warns fails on wrapped msgids |
| **7 → 11** | A credible stale-entry gate needs a plural-aware parser | The gate inherits the `I18N-005` blind spot, and the multi-line orphan is missed |
| **8 → 9** | BLOCK 9's exemption set is BLOCK 8's single named definition | Two divergent exemption lists — the mechanism by which the next string opts out silently |
| **9 → 10** | The three real `bs` strings must be judged before the prune removes the fourth (`Start`) | A linguist is asked to review a string that BLOCK 10 then deletes, wasting the review |
| **10 → 11** | **The strictest edge in the plan.** The tree must be clean before the assertion that it is clean is added | BLOCK 11 is red on arrival, and the implementor's response is to widen the assertion — which is how a gate becomes theatre |
| **9 → 12** | The spec's exemptions must reflect the script gate's final scope | The spec claims a coverage the gate does not have |
| **12 → 13** | ~~BLOCK 12 carries Option A's documentation; BLOCK 13 carries Option B's code~~ — **both owner options partially implemented, and the reader cannot tell which was chosen** | **EDGE REMOVED 2026-10-03: `Q2` resolved to Option A and BLOCK 13 is CANCELLED.** There is no second option left to half-implement, so the hazard the edge existed to prevent can no longer occur. BLOCK 12 is now the sole home of `I18N-013` |

### 4.3 Where there is deliberately **no** edge, and why

| Pair | Why there is no edge |
|---|---|
| **1 and 3** | Locale resolution and number formatting are unrelated mechanisms in unrelated modules. Nothing in BLOCK 1 changes what `intcomma` does, and nothing in BLOCK 3 changes how a locale is resolved. They could be two agents' work — except that the one-Implementor rule serialises them |
| **1 and 5** | `TIME_ZONE` and `LANGUAGE_CODE` sit in adjacent lines of the same file and are conceptually neighbours, but BLOCK 1 does not edit `config/settings/base.py` at all. The only coupling is the six-way contention, and the ordering there is a *contention* decision, not a *correctness* one |
| **3 and 5** | Both may edit `config/settings/base.py` (option (a) and Q4 part 2). That is contention, handled by re-read-before-edit — not a dependency |
| **5 and 6** | Unrelated mechanisms, unrelated files |
| **8 and 10** | Both read catalogues. Neither reads the other's output. **This is the pair most likely to be assumed ordered**, and it is not: BLOCK 8's collector questions and BLOCK 10's prune questions are independent |
| **10 and 12** | BLOCK 12 does not restate the extraction flags — BLOCK 10 owns them, and BLOCK 12 is forbidden from re-correcting them. That is a constraint, not an edge |
| **Any block and `VAL-001`** | `VAL-001` is stale. **No edge exists because there is nothing to do.** Do not let a Validator read the CRITICAL severity as a priority signal |

### 4.4 The orders that are unsafe

| Unsafe order | What goes wrong |
|---|---|
| **2 before 1** | The annotations are tightened while the cookie still delivers an arbitrary `str`. `basedpyright` passes, the gate passes, and `I18N-001` is still live. **This is the one that looks free** |
| **11 before 10** | The gate is red on arrival. The instinct is to widen the assertion or add an exemption "just for now", and the gate stops guarding |
| **10 before 7** | The prune is driven by a regex-derived entry list. **The wrapped multi-line orphan survives**, the diff looks clean, and `I18N-014` is reported closed |
| **4 before 3** | The chip formats through the old path. The same page shows two price notations and the phase looks finished |
| **12 before 1, 5, 6 or 9** | The document describes behaviour the code does not have. **This reproduces `I18N-001`'s defect class in a new file**, and a doc-only commit is exactly where a reviewer stops reading |
| **13 before 12** | Both `I18N-013` options are half-implemented and the record does not say which was chosen |
| **Any two `.po` blocks without a re-read** | Silent deletion of a concurrent phase's strings. **This is the plan's most likely catastrophic outcome** and it is why §1.6 exists |
| **BLOCK 3's argument fix without its `Q3` decision** | The `bs` readers get `1234,56` beside the `ru` readers' `1 234,56` — **a new visible inconsistency introduced by a fix that looks complete** |

### 4.5 What the DAG does *not* decide

- **It does not decide any `Q`.** `Q1`–`Q6` and `Q9`–`Q11` are answered by their named owners.
  Q7 is answered (no change) and Q8 is answered (the obsolete assertion belongs to
  `I18N-014`). Q10 is routed to phase 09.
- **It does not decide the content of any translation.** Three `bs` strings are a `Q1`
  linguist deliverable and the `I18N-013` Option B `bs` values are the same. **No block in
  this plan writes a `bs` sentence.**
- **It does not sequence the other phases.** Phases 03, 05, 06, 07, 08, 10, 11, 12 and 15
  run in parallel. §5 states the non-interference rules; it does not order anyone else.
- **It does not allocate an `AdvisoryLockId`.** Phase 14 ships no migration and takes no lock.
  `apps/core/enums.py` is read, not written.

---

## 5. Cross-phase coordination

Plans `.ai/plans/01-…` through `.ai/plans/13-performance-remediation.md` exist and phase 15
is being planned in parallel. **This plan does not contact the other agents.** Where another
phase is in the way, the rule is written down here and repeated in the block's constraints.

### 5.1 What phase 14 already owns and must not re-ship

| Artefact / decision | Owner | Phase 14's obligation |
|---|---|---|
| `VAL-001` / `CFG-008` | **Phase 02, closed at the anchor commit itself** | **Do not action. Do not re-open.** ✔ `RUN_TRANSLATION_BACKFILL` is in `ALLOWED_ENV_VARS` and a reverse-direction whole-tree gate exists. The report's "do not close CFG-008" instruction is obsolete and re-running it produces a false reopening (C-1) |
| The `en` empty-`msgstr` convention | **Two existing tests** (`test_no_empty_msgstr` in `test_i18n_completeness.py` and in `test_i18n_pipeline.py`) | **Do not fill them. Do not change either test's `en` skip.** 408 entries, no runtime effect, and it breaks the stated contract (Q7, §6.3 item 4) |
| The three documented template exemptions (`admin/`, `analytics/moderation_dashboard.html`, `components/feature_tag.html`) | **`docs/99-agent/rules.md` + `docs/01-spec/i18n-spec.md`** | **Preserve them exactly.** BLOCK 8 extends the set with a **named** entry; BLOCK 12 restates the list. Neither rewrites the tuple inline |
| `--no-location` as the extraction convention | **`Makefile` + `.kilo/rules/commands.md`** | **Keep it.** Dropping it re-introduces `src/…:NNN` churn across ~408 entries per catalogue and destroys reviewability — which is the property that makes phase 14's own `.po` edits reviewable |
| The `catalog_js_labels` inline-JS i18n pattern (`context_processors.header_context` → `{{ catalog_js_labels\|escapejs }}`) | **`docs/99-agent/rules.md`, "Inline-JS i18n"** | **Any new JS-visible string in BLOCK 6 follows it.** A raw literal in a `<script>` block bypasses both `makemessages` and the gate |
| The deliberately non-gettext `BotCommand` literals in `src/telegram_bot/lifecycle.py` | **The module's own comment** | **Do not edit `lifecycle.py`.** The four orphaned msgids are the *residue*, not the cause. BLOCK 8 names them as the first exemption; BLOCK 10 prunes the residue |
| The deliberate absence of `LocaleMiddleware` | **The `language.py` module docstring** | **Do not add it, a `set_language` view, or `i18n_patterns`.** Any such shortcut re-opens the resolved-value clobbering the docstring explains (BLOCK 1 constraint 2) |

### 5.2 What phase 14 must **not** do, for other phases' sake

| Phase | Phase 14 must not | Why |
|---|---|---|
| **02** | Touch `config/settings/prod.py`; add a settings key to `ALLOWED_ENV_VARS` without the matching `.env*.example` lines in the same commit; "helpfully" close or re-open `CFG-008` | `prod.py` is phase 02's file and had a concurrent agent's unstaged work during the audit. The allowlist is gated **in both directions** by `test_env_allowlist.py` — a half-added key goes red immediately. `test_settings_defaults.py` is the same story |
| **03** | Regenerate the catalogues while phase 03 appends BLOCK 6/BLOCK 10 strings | A wholesale `makemessages` silently deletes them, and the i18n gate then goes red — sending the next agent to the wrong conclusion |
| **05** | Same, for phase 05's BLOCK 8/11/12 strings | Same |
| **06** | Decide the consent question unilaterally; edit `docs/01-spec/technical-specification.md`; edit `docs/01-spec/spec-index.md`; edit the PII/consent strings | **Phase 06 owns consent state** (`ConsentRecord`, the `consent_preferences` context processor) and both spec files. `Q5` is a **phase-06 boundary question** — BLOCK 6 is gated on it and its `technical-specification.md` limb is deferred, not forced |
| **07** | Same, for phase 07's BLOCK 7/11/12 strings | Same |
| **08** | Edit `apps/core/utils/sanitize.py`; edit the FTS vector mapping or `LanguageLocale.fts_config` / `fts_vector_field`; act on the phase-08 deferral as if it were open | `sanitize.py` is phase 08's (BLOCKS 3/4) and phase 09's (compose only). `VAL-002` is **stale** — the function has no `isalpha()` — so the correct phase-14 action is a **procedural closure note**, not a code change (§6.2). The `category_name_i18n` **reindex path** is phase 08's: if BLOCK 2 or BLOCK 5 changes what a category or city name resolves to, the FTS vectors are **not** re-indexed by this plan, and that interaction is recorded rather than acted on |
| **09** | Edit `apps/core/services/translation.py`; edit `backfill_translations`; machine-translate anything | **Phase 09 owns the Google-Translate client (`API-007`)** and its resilience and PII posture. ✔ **Correcting the framing: phase 09 owns the translation-backfill *signal* (`RUN_TRANSLATION_BACKFILL` → `backfill_translations` via `migrate_locked.py`), and phase 06 — not phase 09 — owns `LOG_MASK_KEY`.** Phase 09's §5.2 explicitly refuses to implement the target-language matrix; it stays unowned and is routed (§6.2, Q10) |
| **10** | Regenerate the catalogues while phase 10 appends BLOCK 10/16 strings; edit the duplicated `ListingsQueryParams` or the listings/search template context | Both views feed the **same** `ads/partials/ad_list.html` partial, so the gate already covers that context. ✔ Verified: both supply both price bounds. BLOCK 4 changes both routes **in the same commit** precisely so the duplication cannot drift |
| **11** | Rewrite or relocate `test_i18n_completeness.py`'s test functions without reading phase 11's plan first | **Phase 11 owns the test-coverage gate.** This plan **edits** the i18n gate (BLOCKS 8, 9, 11) and does not relocate, rename or delete any of its test functions. If phase 11's plan restructures that module, the sequence is re-read-before-edit, not a conflict resolution |
| **12** | Edit `docs/99-agent/rules.md` or `docs/99-agent/architecture.md` without a re-read; edit `docs/ops/**`; add a job to `ci.yml` | **Phase 12 holds a conditional claim on `rules.md`** (its BLOCK 14, only if a topology statement changed). BLOCKS 8 and 12 both touch it → read-before-write, stop on a concurrent change. This plan adds **no** CI job and **no** operator-facing string |
| **15** | Assume anything about phase 15's scope | Phase 15 is being planned in parallel and its scope was not available to this Planner. **If phase 15 claims an artefact in §5.3, the coordinator resolves it — phase 14 does not preempt it** |

### 5.3 Shared-artefact reservations

| Artefact | Claimed by | Rule for phase 14 |
|---|---|---|
| **`src/backend/locale/{ru,bs,en}/LC_MESSAGES/django.po`** | **Six appending phases: 03, 05, 06, 07, 08, 10** | **The most contended i18n artefact in the repository.** Every `.po` block (9, 10, 11, 13) carries §1.6 in full: re-read immediately before the extraction, re-read immediately before `git add`, **append and prune — never regenerate**, stage by path, never add a `.mo`. **And the `--no-obsolete` hazard: BLOCK 10 deletes entries by design, which makes it the single most dangerous operation in the phase** |
| **`src/backend/config/settings/base.py`** | **Six-way: 02, 04, 06, 07, 08, 12** | BLOCK 3 (option (a)) and BLOCK 5 each add **one** line plus, conditionally, an `ALLOWED_ENV_VARS` entry. **Re-read immediately before editing; stop and report a concurrent change; stage by path.** Both settings blocks record in the commit body that the file is six-way contended |
| `src/backend/config/settings/prod.py` | **Phase 02**; **actively edited during the audit** | **Untouched.** BLOCK 6 *reads* `SESSION_COOKIE_SECURE` from settings, which is correct — it does not edit `prod.py` or `dev.py` |
| `src/backend/config/settings/tests/test_settings_defaults.py` | **In flight** (same concurrent agent) | BLOCK 3 (option (a)) and BLOCK 5 add assertions here. **Re-read before adding; the file currently has no `TIME_ZONE` or `LANGUAGE_*` assertion at all** |
| `config/settings/tests/test_env_allowlist.py` | Read in **both** directions by phase 02 and phase 12 | BLOCK 5's env-overridable option adds `TIME_ZONE` to `ALLOWED_ENV_VARS` **and** to every `.env*.example` **in one commit**, or the gate goes red |
| **`src/backend/conftest.py`** | **Nobody, in any plan — "the most contended file in the repository"** | **Untouched.** No new fixture. The autouse `_reset_translation_state` fixture already exists; do **not** add per-file `deactivate()` calls. All new tests go in the existing per-finding modules, including `test_i18n_category_city.py` |
| `docs/01-spec/technical-specification.md` | **Phase 06 holds it** (its BLOCKS 4, 11, 14) | **Untouched.** BLOCK 6's "name `lang_pref` in a cookie list" limb is **deferred to phase 06**, not forced |
| `docs/01-spec/spec-index.md` | **Phase 06, sole owner** | **Untouched** |
| `docs/99-agent/rules.md` | **Phase 12, conditionally** (its BLOCK 14) | BLOCKS 8 and 12 both edit it. **Read before write; stop on a concurrent change.** Record it in §5.3 so the coordinator can see the overlap |
| `docs/01-spec/i18n-spec.md` | **Phase 14 alone** | Phase 14 owns it. BLOCK 12 writes it once, after the behaviour it describes exists |
| `Makefile`, `.kilo/rules/commands.md` | Phase 14 for the two extraction targets; other phases may hold other targets | BLOCK 10 edits **only** the `makemessages` invocation, in **both** documented surfaces, in one commit. **`Makefile.ps1` has no `makemessages` target, so there is no parity obligation for that file** |
| `src/backend/apps/ads/tests/test_i18n_completeness.py` | **Phase 11 owns the coverage gate**; phase 14 owns the i18n assertions in it | Phase 14 **edits and adds**; it does not relocate, rename or delete a test function. Re-read before writing |
| `src/backend/apps/core/utils/sanitize.py` | Phase 08 (BLOCKS 3/4), phase 09 (BLOCK 16, compose only) | **Untouched.** `VAL-002` is stale |
| `src/backend/apps/core/services/translation.py` | Phase 09 (BLOCKS 8, 16) | **Untouched** |
| `apps/search/services/immediate_alerts.py` | **Three-way: 06, 03, 09** | **Read only.** The alert-message locale rendering documented in `i18n-spec.md` lives here. Phase 14 records the interaction and does not edit it |
| `src/telegram_bot/lifecycle.py` | The bot lifecycle; not claimed, but deliberate | **Untouched** — its literals are documented as deliberately not msgids |
| `src/backend/apps/core/context_processors.py` | Read by several phases' templates | BLOCK 2 touches it **only** under `Q6` option (a). A report, not a silent edit |
| `.github/workflows/ci.yml` | Phases 11, 09, 02, 12 | **Untouched.** Phase 14 adds no CI job and does not append after `deploy-check:` |
| `.ai/audit/**` | **Nobody. Unmodifiable by mandate** | The 18 tracked deletions are intentional. `git status --short .ai` must show no new modifications beyond this plan's own file |
| `.ai/plans/**` | Each Planner owns its own plan file | Phase 14 writes **only** `.ai/plans/14-i18n-remediation.md` |

### 5.4 One-way non-interference with the four i18n-gate owners

1. **Phase 11 (test coverage)** owns the *idea* of a test gate; phase 14 owns the *content* of
   the i18n one. Phase 14's BLOCKS 8, 9 and 11 add assertions and widen collectors **within**
   the existing module. **Phase 14 adds no new CI job and no new marker** — if phase 11's plan
   restructures that module, the sequence is re-read-before-edit.
2. **Phase 06 (PII/consent)** owns the consent strings and the `lang_pref` consent question.
   `Q5` is theirs. Phase 14 ships the parts that are unambiguous under every option
   (`secure`, `samesite`, the docstring) and **defers** the parts that are not.
3. **Phase 09 (external API)** owns the outbound translation client and the backfill signal.
   Phase 14 owns neither, and **uses neither as a translation tool**: the `bs` strings are a
   human deliverable precisely *because* the machine path exists and is wrong for this job.
4. **Phase 12 (production ops)** owns ops-facing strings. Phase 14 adds **no** user-visible
   string except through the `Q1` linguist deliverable and the `Q2` Option B catalogue growth.

### 5.5 What phase 14 needs from other phases

| From | What | If it does not arrive |
|---|---|---|
| **Phase 06** | A `Q5` answer on whether the server write or the consent gate is authoritative, and clearance (or not) for the `technical-specification.md` limb | **BLOCK 6 does not start.** The `secure`/`samesite` halves could ship independently, but the block as written is one commit and `httponly` is unsafe without the answer |
| **Owner** | `Q1` (a linguist for three `bs` strings), `Q2` (`I18N-013` A or B), `Q3` (the `bs` grouping), `Q4` (the `TIME_ZONE` value and its env-overridability) | **Updated 2026-10-03: `Q2` is RESOLVED (Option A — BLOCK 12 sole home, BLOCK 13 cancelled) and `Q4` is RESOLVED (hard-coded `Europe/Podgorica`, not env-overridable — BLOCK 5 unblocked). `Q1` is RULED but its gate is `OPEN-PENDING-REVIEWER`; `Q3` remains open. BLOCKS 3 and 6 stay gated** |
| **Phase 08** | The `sanitize_query_for_log` deferral closed and the advisory text corrected | §6.2. Phase 14's own conclusion is already recorded; this is phase 08's paperwork |
| **Phase 09 / the coordinator** | An owner for the `backfill_translations` target-language matrix | §6.2, Q10. **Phase 14 does not block on it** and does not audit it |

---

## 6. Out of scope for this plan

### 6.1 De-scoped by design (deliberately not done here, with the rationale)

| De-scoped | Why | Where it is routed |
|---|---|---|
| **Filling the `en` catalogue's 408 empty `msgstr`s** | The documented convention — the `msgid` is English — enforced by the `en` skip in **two independent test modules**. A 408-entry diff that changes nothing at runtime and breaks the stated contract | **Nowhere. Q7 answers it: no change.** §6.3 item 4 |
| **Correcting the six legitimate `bs` copy-throughs** (`ID`, `Telegram ID:`, `Pro`, `Telegram`, `Google Translate`, `Plausible Analytics`) | Brand and product names that are **correctly identical** in Bosnian | **Nowhere.** §6.3 item 5 |
| **"Correcting" the two `bs` plural entries that share `msgstr[1]` and `msgstr[2]`** | **Correct** for `bs` CLDR (`nplurals=3; plural=n%10==1 && n%100!=11 ? 0 : 1`). Indistinguishable from a copy-paste error to a reader — and exactly the class BLOCK 7's plural-aware parser must handle **without** flagging | **Nowhere.** §6.3 item 5 |
| **Adding a `Vary: Cookie` header** for `I18N-012` | The finding was reclassified to `DOC-UPDATE` **precisely because the code is already correct**. `CsrfViewMiddleware` adds it on every full page. The header would be a redundant, undeclared change to a contract that already holds | **Nowhere.** §6.3 item 3. BLOCK 6 fixes the docstring |
| **Adding `{% csrf_token %}` to the two `csrf_token`-free HTMX fragments** | It is the *incidental*-`Vary` fragility `I18N-012` records, and BLOCK 6 **documents** it. Adding a CSRF token to a fragment changes cache semantics for a reason outside any finding | **Nowhere.** BLOCK 8 constraint 7 |
| **Adding `LocaleMiddleware`, a `set_language` view, or `i18n_patterns`** | `LocaleMiddleware` is **intentionally absent** — the module docstring explains that it would re-derive the language from the never-set `django_language` cookie plus `Accept-Language`, clobbering the resolved value and ignoring both `?lang=` and `lang_pref` | **Nowhere.** §6.3 item 7 |
| **Moving the two `<time datetime="…\|date:'Y-m-d'">` ISO attributes to locale formats** | They are **correct ISO 8601 machine-readable values**, not display strings. A screen reader, a crawler and a future JS enhancement read them | **Nowhere.** §6.3 item 6 |
| **Restoring or reconstructing the three missing research documents** | `i18n-translation-pipeline-gap-analysis.md`, `i18n-definition-of-done-research.md` and the whole `docs/96-researches/` directory were never committed. Inventing them would be fabrication | BLOCK 12 resolves the **references** per `Q11`; the documents themselves stay absent |
| **Restoring `.ai/audit/14-i18n/findings.md`** | Deleted in the working tree, and `.ai/audit/**` is unmodifiable by mandate. The validated report is self-contained | **Nowhere.** §8.2 |
| **Auditing `backfill_translations`' resilience, PII posture or target-language matrix** | Phase 09's `API-007` owns the client; the matrix is unowned. Phase 14 records the interaction | §6.2, Q10 |
| **Auditing `sanitize_query_for_log`** | `VAL-002` is **stale** — the function has no `isalpha()`. There is no code change to make | §6.2 — phase 08's paperwork |
| **Re-opening `CFG-008`** | ✔ `VAL-001` is stale; `RUN_TRANSLATION_BACKFILL` is in `ALLOWED_ENV_VARS` at the anchor | **Nowhere.** C-1 |
| **Any migration, `AdvisoryLockId`, Pydantic model, serializer, ORM change or schema change** | None is needed by any finding, and the report confirms no finding requires an architectural or structural change beyond `I18N-001`'s accessor typing. `AdvisoryLockId` is read, never written | **Nowhere.** §6.3 item 9 |
| **Any new CI job or workflow edit** | `ci.yml` is claimed by four phases and appending after `deploy-check:` breaks shipped assertions | **Nowhere.** §6.3 item 10 |
| **Hard-coding any file, template, msgid or catalogue count in a new guard** | ✔ The report's counts are stale (43 → **38** templates; 18 + 169 → **20 + 172** model metadata) | **Nowhere.** §1.7. Every guard derives its expectation from the collector |

### 6.2 Rostered elsewhere, not dropped

| Item | Owner | Note |
|---|---|---|
| `VAL-002` — close phase-08's `sanitize_query_for_log` deferral and correct the phase-08 advisory text | **Phase 08** | The premise is stale; the residual is paperwork. Phase 14's conclusion is already recorded |
| The `backfill_translations` **target-language matrix** (Q10) | **Unowned — coordinator to assign; phase 09 owns the mechanism** | `backfill_translations` produces the `Ad.title_bs` / `Ad.title_en` values `Ad.get_title` reads. A wrong target degrades `bs` ad content to Russian through the **same `locale → ru` chain**, with no gate coverage. **Phase 14 does not block on it and does not audit it** |
| Naming `lang_pref` in a formal cookie inventory | **Phase 06** holds `technical-specification.md` | BLOCK 6's deferred limb (§5.3) |
| Translating ~192 model-metadata entries (`I18N-013` Option B) | ❌ **CANCELLED 2026-10-03** — `Q2` resolved to Option A | The finding closes in BLOCK 12's documentation. Option B is declined, **not deferred**; re-opening it requires a new Product Owner decision |
| The three real `bs` strings | **A human/linguist**, via `Q1` — gate `OPEN-PENDING-REVIEWER` | Never this plan. Never a machine, never a translation API (ruled 2026-10-03) |

### 6.3 Explicitly forbidden while implementing

1. **Never write a `bs` translation without the `Q1` reviewer.** No machine translation, no
   approximation, no "close enough". Phase 09's outbound Google-Translate client is explicitly
   **not** a catalogue tool, and project rule 1 makes every `msgid` English. This is the
   single hardest rule in the plan.
2. **Never fill the `en` catalogue's `msgstr`s**, and never change the `en` skip in either
   `test_no_empty_msgstr`. 408 entries, no runtime effect, and it breaks the stated contract.
3. **Never add a `Vary: Cookie` header.** `I18N-012` exists because the code is already
   correct.
4. **Never change a `msgid` to fix a `msgstr`.** That re-extracts the key and orphans the entry.
5. **Never "correct" a legitimate copy-through or a shared-form `bs` plural entry.**
6. **Never touch the two `<time datetime="…">` ISO attributes.**
7. **Never add `LocaleMiddleware`, a `set_language` view, or `i18n_patterns`.**
8. **Never regenerate a catalogue wholesale, and never `git add` a `.mo` file.** `.mo` is
   gitignored and is compiled at image build, at container start and in the CI `i18n` job.
9. **Never edit `src/backend/conftest.py`.** Off-limits to every phase. Use
   `translation.override` and the existing autouse `_reset_translation_state`.
10. **Never append a job to `ci.yml`, and never run a blanket `ruff check --fix src/`.**
    `[tool.ruff] fix = false` is set deliberately; scope `--fix` to the block's own files.
11. **Never use a line number as a task target or a doc citation.** ✔ N-4 — every line anchor
    in the report has drifted.
12. **Never `git reset`, `git checkout`, `git restore` or `git stash`,** and never revert
    another agent's work. **Changes you did not make are normal.**
13. **Never modify a file under `.ai/audit/**`.**
14. **Never choose an option on a gated question** (§0.5, §1.5). A declined gate is recorded
    with its reason; silence is not an acceptable outcome.

---

## 7. Per-block risk register

Severity here is **this Planner's assessment of execution risk for the change**, not the
finding's severity. "Blast" covers what else feels the change. "Contention" covers shared
files. "Behaviour" covers observable response changes. "Data" covers irreversible content
loss.

| Block | Risk | Kind | Likelihood | Impact | Mitigation / detection | Residual |
|---|---|---|---|---|---|---|
| **All** | An `I18N-001` regression test asserts on gettext chrome and passes in CI while production renders a wholly Russian page | **Correctness** | **High** | **High** | ✔ `VAL-003` (§0.2.2 item 1); BLOCK 1 constraint 1, the task YAML, and this row; the acceptance criteria forbid a chrome assertion for an unsupported locale | Low |
| **All** | A block runs with its gate unanswered, or the Implementor silently picks an option | Process | Med | **High** | Every gate is a labelled block in §3 and a row in §0.5, repeated verbatim in the task YAML's `extra_context`; §8.1 checks a written answer exists for each | Low |
| **All** | A `.po` block regenerates or commits a catalogue that silently deleted a concurrent phase's strings | **Data** | Med | **High** | ✔ §1.6 in full, repeated in every `.po` block; six phases append to those files; the disappearing-entry set is enumerated and recorded; a Validator witnesses the before/after | **Med — accepted** |
| **All** | A block edits a six-way-contended settings file on a stale read | Contention | **High** | Med | Re-read immediately before editing; stop and report; stage by path. Normal for `config/settings/base.py`, `prod.py`, `test_settings_defaults.py` | Med — accepted |
| **All** | A block's tests are **asserted** rather than **run**, or run on the host where there is no database | Process | Med | **High** | Every block names its Docker gate command; tests run only through the `test` service (§1.1) | Low |
| **All** | A red gate is captured while another phase agent runs and a teardown race is reported as a defect | Process | **High** | Med | Re-run serially before reporting. The symptom is `test_mko_bazuna does not exist` | Low |
| **All** | A new guard is added and never observed failing | Quality | Med | **High** | §1.7; **every** new guard's acceptance criteria include "and that failure is demonstrated before the commit" | Low |
| **All** | A block writes a `bs` string without the `Q1` reviewer | **Correctness / linguistics** | Med | **High** | §6.3 item 1; BLOCK 9's constraints; a reviewer reads the diff for any `bs` change | Low |
| **All** | A blanket `ruff check --fix src/` reorders imports another phase's uncommitted work depends on | Process | Med | Med | `[tool.ruff] fix = false` is set deliberately; §1.3 and §6.3 item 10 scope `--fix` to the block's own files | Low |
| **All** | The Implementor uses a line number from the report as a target and lands the edit in the wrong place | Process | Med | Med | ✔ N-4 — every report line anchor has drifted; §1.4 forbids line targets; every task YAML uses `type`/`name` | Low |
| **All** | `makemessages` is run via `make` and hangs or fails on the dependency chain, wasting the implementor's day | Process | **High** | Low | §1.2 states the two verified failure modes and gives the working one-shot form; it is repeated in every `.po` block's `extra_context` | Very low |
| **1** | The resolver normalises the cookie but `_parse_accept_language` still returns the fallback for a q-valued header, and the block is reported complete | Correctness | Med | Med | BLOCK 1 owns `I18N-015` in the same commit; the acceptance criteria name the exact header `de-DE,ru;q=0.8,bs;q=0.6` and the `q=0` case | Low |
| **1** | `translation.activate()` is bypassed or a fourth locale path is introduced | Correctness | Low | **High** | Constraint 2 and the three-authorities constraint; the acceptance criteria require `request.LANGUAGE_CODE ∈ settings.LANGUAGES` for every input | Very low |
| **1** | The fix is "simplified" by adding `LocaleMiddleware` | Architecture | Low | **High** | Constraint 2 names the docstring that explains why it is absent; §6.3 item 7 | Very low |
| **2** | `Q6` option (a) is taken and the context-processor change breaks a template another phase depends on | Contention | Med | Med | The `Q6` pre-block step requires the Auditor to enumerate every consumer **before** the block starts; a change is a report, not a silent edit | Low |
| **2** | `LookupItem.get_name` is "uniformed" and its terminal rung changes from `slug` to `name` | Correctness | Med | Med | Constraint 3 and an explicit acceptance criterion | Low |
| **2** | The typing change leaves `basedpyright` errors and is committed anyway | Quality | Med | Med | Constraint 7 and the acceptance criterion; `uv run basedpyright` is in §8.2 | Low |
| **3** | **The one-argument fix lands without the `Q3` grouping decision, and `bs` reads `1234,56` beside `ru`'s `1 234,56`** | **Correctness** | **High** | **High** | ✔ §0.2.2 item 2; `Q3` is a blocking gate; BLOCK 4 inherits the limitation and must restate it; §4.4 lists this as an unsafe order | Med — accepted, by decision |
| **3** | The test is corrected to assert only "a separator is present", reproducing the defect it documents | Quality | Med | **High** | Constraint 2; the acceptance criteria require exact output, a fractional case, a round case and a **≥7-digit** case | Low |
| **3** | Option (a) edits `base.py` without its `ALLOWED_ENV_VARS` / `.env` companion, and the allowlist gate goes red | Correctness | Med | Med | Constraint 4; §5.3 records the coupling. **Note: BLOCK 5's identical coupling is GONE — `Q4` ruled `TIME_ZONE` non-env-overridable on 2026-10-03, so BLOCK 5 creates no allowlist work** | Low |
| **3** | Django's bundled `bs` locale data is edited in `.venv` to fix grouping | Correctness | Med | **High** | Constraint 5; the acceptance criteria require `.venv` to be byte-identical to its shipped state | Very low |
| **4** | The chip is updated on one route only, and the listings and search views of the same page disagree | Correctness | Med | Med | Constraint 3; both files are in the file surface; the acceptance criteria require byte-identical chips | Low |
| **4** | The `blocktrans` → `trans` change alters the extracted msgid and the gate goes red in CI | Behaviour | **High** | Med | Constraint 5 names the `#, python-format` entry and requires a non-empty `ru`/`bs` `msgstr` in the same commit; the commit body must report the msgid delta | Low |
| **4** | The chip's date filter is changed "while you are in there", and an ISO attribute or a `TIME_ZONE` regression is introduced | Behaviour | Low | Med | Constraint 6 keeps BLOCK 5's change in a separate commit so a date regression stays attributable | Very low |
| **5** | ~~`TIME_ZONE` is set to the wrong zone~~ — **CLOSED 2026-10-03** | Correctness | **CLOSED** | — | `Q4` is RESOLVED: the zone is **`Europe/Podgorica`**, ruled by the Product Owner on 2026-10-03, and the Implementor does not pick. The commit body records that it was **ruled, not defaulted**, and the test asserts a known UTC instant | **Closed by decision** |
| **5** | ~~Env-overridable `TIME_ZONE` is added to the allowlist without all four `.env*.example` lines~~ — **CLOSED 2026-10-03** | Correctness | **CLOSED** | — | The env-overridability branch is **closed**: the value is hard-coded, there is **no `ALLOWED_ENV_VARS` entry and no `.env*.example` line**, and the allowlist collision disappears entirely. **The residual risk is inverted and much smaller: an implementor "helpfully" adding the env surface.** BLOCK 5's acceptance criteria name `ALLOWED_ENV_VARS` as byte-unchanged and the file-surface rows are marked *not applicable — do not create* | **Closed by decision** |
| **5** | The two ISO `datetime` attributes are swept into the locale-format change | **Compatibility** | Med | **High** | Constraint 1, restated as an acceptance criterion requiring byte-identity; the report flags this in the finding itself | Low |
| **5** | `base.py` has changed underneath and the block clobbers a concurrent phase | Contention | **High** | Med | Constraint 5; re-read; stop and report | Med — accepted |
| **6** | `httponly=True` lands while a client-side writer still needs the cookie, and the language switcher breaks in production | **Correctness** | Med | **High** | Constraint 2 restricts `httponly` to `Q5` option (a); the acceptance criteria require an end-to-end switcher check under option (a) | Low |
| **6** | **An implementor "fixes" `I18N-012` by adding a `Vary: Cookie` header** | **Design** | Med | Med | ✔ §0.2.2 and §6.3 item 3; constraint 1; the acceptance criteria require the `Vary` header to be **byte-identical** to its pre-block state | Very low |
| **6** | `Q5` is decided unilaterally without phase 06 | Process | Med | **High** | `Q5` is labelled a phase-06 boundary; §5.2 and §5.4 restate it; the commit body must name the answer and whether phase 06 cleared the doc limb | Low |
| **6** | The `lang_pref` cookie's `SameSite` is corrected on the client side only, and the weaker writer still lands last | Correctness | Low | Med | Constraint 3 forbids client-side cookie changes; the server `set_cookie` is the one edited | Very low |
| **7** | The return-type change leaves one of the two `test_no_empty_msgstr` copies unmigrated | Correctness | Med | Med | Constraint 5 — both call sites in one commit; the acceptance criteria require both to reject a blank `msgstr[0]` | Low |
| **7** | The parser is "fixed" to flag the `bs` plural entries that legitimately share `msgstr[1]`/`msgstr[2]` | Correctness | Med | Med | Constraint 3; those forms are CLDR-correct; the acceptance criteria require the tree to stay green on them | Low |
| **8** | The widened bot collector is red on arrival and the implementor adds blanket `skip`s | Quality | **High** | **High** | `Q9` is a **pre-block Auditor step** whose answer is reported, not suppressed; constraint 2 makes the exemption a named set with a reason; constraint 8 requires every new assertion to be seen red **and** green | Low |
| **8** | The collector rewrite uses a hard-coded module list and silently loses the nine-module `handlers/ad_create` package | **Correctness** | Med | Med | Constraint 1; the acceptance criteria require that package to be reached | Low |
| **8** | A hard-coded template count is baked into the new guard, encoding the report's stale "43" | Quality | **High** | Med | ✔ C-2; constraint 5; the acceptance criteria forbid any hard-coded count | Very low |
| **9** | **A machine translation fills the three `bs` strings, or the implementator "approximates" the corrupted sentence** | **Linguistics** | Med | **High** | §6.3 item 1; `Q1`'s consequences, reinforced by the 2026-10-03 ruling that machine output and translation APIs are not acceptable; the acceptance criteria require the value to come from the reviewer or be a named exemption with a reason and an owner; a reviewer reads any `bs` diff. **The gate is `OPEN-PENDING-REVIEWER`, so today's correct state is three named exemptions — not three invented strings** | Low |
| **9** | The new Cyrillic rule is written as a blanket "no Cyrillic in `msgstr`" and immediately fails on `ru` | Correctness | **High** | Med | Constraint 3; a dedicated unit test proves the `ru`-exempt / `bs`-contaminated distinction, and the acceptance criteria require that pass to be demonstrated | Low |
| **9** | `Start` is translated as well as pruned, and BLOCK 10 then deletes the translation | Process | Med | Low | Constraint 5 names it and points at BLOCK 10 | Very low |
| **9** | The gate is committed red | Process | Med | Med | Constraint 10 — the commit must not be made; the reduced deliverable (a named exemption) exists precisely so this never ships | Low |
| **10** | **The prune deletes a string another phase added in the last hour** | **Data** | Med | **High** | Constraint 1 — the disappearing set is enumerated programmatically and classified before the extraction, and a third class means *stop and report*; a Validator witnesses the before/after | **Med — accepted** |
| **10** | The prune is driven by a regex and the wrapped multi-line orphan survives, so the diff looks clean | **Correctness** | Med | Med | The method constraint is in `extra_context` verbatim; BLOCK 11's unit test proves the parse catches the wrapped case | Low |
| **10** | `POT-Creation-Date` diverges across the three catalogues and the next agent is sent to the wrong conclusion | Correctness | Med | Med | Constraint 3; the acceptance criteria require byte-identity | Low |
| **10** | The commit claims `I18N-014` is closed | Review | Med | Med | Constraint 8 and the acceptance criteria; the commit body must state that BLOCK 11 is the durable half | Low |
| **11** | The gate is added before the tree is clean, and the implementor widens the assertion to make it pass | **Design** | Med | **High** | ✔ The strict 10 → 11 edge (§4.2); the acceptance criteria state that if the gate needs a catalogue change, BLOCK 10 did not finish | Low |
| **11** | The stale-entry check uses a line-anchored regex and misses the wrapped msgid, reproducing the defect it prevents | Correctness | Med | **High** | Constraint 1; a dedicated fixture-driven test covers the wrapped case explicitly and the acceptance criteria name it | Low |
| **11** | A second, divergent exemption list is created | Quality | Med | Med | Constraint 2 — BLOCK 8's single named definition is read | Low |
| **12` | `i18n-spec.md` documents behaviour the code does not have, reproducing `I18N-001`'s defect class in a new file | **Documentation** | Med | Med | Constraint 1 — every claim is checked against the tree at commit time, not against the report; the 12-after-1/5/6/9 edges | Low |
| **12** | The three dead links are re-pointed at live documents that do not contain the referenced content | Documentation | Med | Med | `Q11`'s consequences; the acceptance criteria require no link to point at a non-existent file **and** that no missing document was invented | Low |
| **12** | `docs/99-agent/rules.md` is edited on a stale read and clobbers phase 12's conditional change | Contention | Med | Med | Constraint 6; §5.3 records the overlap; stop and report | Low |
| **12** | Stale line citations are re-introduced while rewriting the sections | Quality | Med | Med | Constraint 2; the acceptance criteria forbid a line-number citation in any corrected section | Low |
| **13** | ~~Option B is implemented without a `Q1` reviewer and ~192 `bs` values are machine-translated or left in English~~ — **NOT APPLICABLE: the block is CANCELLED 2026-10-03** | ~~Linguistics~~ | **CLOSED by cancellation** | — | `Q2` resolved to Option A; the block does not run. Retained so a reader who reaches this row sees the cancellation rather than an open hazard. **The only live version of this risk is BLOCK 9's three strings, row 9** | **Closed** |
| **13** | The catalogue grows by ~192 entries against six appending phases and a concurrent phase's strings are lost | **Data** | Med | **High** | Constraint 6 (§1.6 in full); the acceptance criteria require the diff to show only the new entries plus re-extraction churn | Med — accepted |
| **13** | Admin tests asserting English field text are weakened or skipped rather than updated | Quality | Med | Med | Constraint 4 — production code is king; the acceptance criteria explicitly reject skipping and weakening | Low |
| **13** | The implementor "corrects" the catalogue to the report's stale 18 + 169 count | Process | Med | Low | Constraint 7 names the tree's 20 + 172 and says why | Very low |
| **13** | `gettext` is used instead of `gettext_lazy`, freezing strings at import time | Correctness | Med | Med | Constraint 3; the acceptance criteria forbid any `gettext()` in a `models.py` | Low |

---

## 8. Definition of done for the whole plan

Phase 14 is complete when **all** of the following hold.

### 8.1 Scope

- [ ] All **19 in-scope units** have a recorded disposition: **15 `I18N-` findings implemented**
      (with `I18N-002` and `I18N-012` folded into other blocks by shared root cause and
      retained as defence-in-depth and documentation respectively), **2 live `VAL-` items
      honoured** (`VAL-003` as a binding test-shape constraint, `VAL-004` as a shipped
      decision in BLOCK 3), **2 `VAL-` items not actioned with a stated reason** (`VAL-001`
      stale/already fixed, `VAL-002` still stale), **4 new findings implemented** (`N-1`,
      `N-2`, `N-3`, `N-4`), **0 rejected**, **0 dropped without a destination**.
- [ ] Every gated block (**3, 6, 9, 12**) has a **written** answer for each of its open
      questions, naming the option chosen and the consequences accepted. **Silence is not an
      acceptable outcome for any of them.** **BLOCK 5 is no longer gated — `Q4` was resolved on
      2026-10-03 — and BLOCK 13 is CANCELLED.**
- [ ] Each of **Q1 … Q11** is either answered with a record, or explicitly re-routed with a
      named destination. **`Q2` and `Q4` are RESOLVED (Product Owner, 2026-10-03)**; **`Q1` is
      ruled but its gate is `OPEN-PENDING-REVIEWER` and is recorded as such**;
      **Q3, Q5, Q11** are owner or cross-phase decisions still open;
      **Q3, Q6, Q8, Q11** are Planner/Researcher rulings; **Q9** is an Auditor pre-block step;
      **Q7** is answered (no change); **Q10** is routed to phase 09 / the coordinator.
- [ ] **`VAL-001` was not actioned and `CFG-008` was not re-opened.**
- [ ] **The three `bs` strings were either supplied by the named reviewer or recorded as
      named, commented exemptions** — and for every exempted string, the commit body states
      the finding is **not closed** for it. **While `Q1` is `OPEN-PENDING-REVIEWER`, the
      exemptions are the expected state; a follow-up commit supplies the values and removes them
      when the sign-off arrives.**
- [ ] **`I18N-013` closed on exactly one option — Option A, in BLOCK 12's documentation (2026-10-03).**
      **BLOCK 13 was CANCELLED: no `models.py` changed, no catalogue entry was added, and the
      admin tests asserting English field text are unchanged. Not both options, and not half of
      each.**
- [ ] The `I18N-013` Option A/B decision was recorded as **independent of `Q1`** (C-5), not as
      a gate on it — and the fact that `Q2` resolved while `Q1` stayed open is the proof.
- [ ] **`settings.TIME_ZONE` is the hard-coded literal `Europe/Podgorica`; `ALLOWED_ENV_VARS` is
      byte-unchanged and no `.env*.example` gained a `TIME_ZONE` line.**
- [ ] Every de-scoping in §6 has a named destination or a stated rationale.
- [ ] **No `bs` sentence was written by an engineer, guessed, or machine-translated.**

### 8.2 Gates — all green

- [ ] `uv run ruff check src/` → exit 0.
- [ ] `uv run basedpyright src/` → **0 errors**.
- [ ] `uv run djlint src/backend/templates/` → no new finding.
- [ ] `.\Makefile.ps1 test` → fast gate green (`seed` marker skipped), run **after every
      block**.
- [ ] The targeted i18n gate from §1.1, **including `test_i18n_category_city.py`**, → green.
      **The five DB-backed tests were never run during the audit (§0.2.3 item 9) and are the
      only DB-backed i18n evidence in the phase; they must have been run at least once.**
- [ ] `makemigrations --check` → **no changes**. **This plan ships no migration.**
- [ ] `git diff -- src/backend/locale` is reviewed entry by entry, not skimmed, for every
      `.po` block — and the disappearing-entry set for BLOCK 10 was enumerated before the
      extraction and recorded in the commit body.
- [ ] **No `.mo` file appears in any commit.**
- [ ] Every red-gate observation was **re-run serially** before being reported as a defect
      (§1.1).
- [ ] **Every guard this plan adds was demonstrated failing** at least once (§1.7) — including
      BLOCK 11's wrapped-multi-line orphan case and BLOCK 9's `bs`-`msgstr` Cyrillic case.
- [ ] `git status --short .ai` shows **no new modifications** beyond the pre-existing
      `.ai/audit/**` deletions and `.ai/plans/14-i18n-remediation.md`.
- [ ] No commit was made without an explicit user request; no `git reset`, `git checkout`,
      `git restore` or `git stash` was run at any point; no container or compose stack was
      started, stopped or modified outside the commands in §1.1 and §1.2.

### 8.3 Per-finding behavioural confirmation

- [ ] **`I18N-001`** — for every cookie value in the priority table, including `en-US`, `EN`,
      `en_US`, `de-DE`, `ru-RU` and `xx`, `request.LANGUAGE_CODE` is a member of
      `settings.LANGUAGES` **and** the model accessors return that locale's value, not the
      `ru` rung. The assertions are on **accessors**, never on chrome. ✔
- [ ] **`I18N-002`** — the submenu cache key's locale segment is in `{ru, bs, en}` for every
      request in the table.
- [ ] **`I18N-003`** — a fractional amount renders with the locale's decimal separator in all
      three locales; a **≥7-digit** amount renders grouped in every locale the `Q3` option
      covers; a round integer amount renders identically to before. The test asserts exact
      output, not the presence of a separator. ✔
- [ ] **`I18N-004`** — `settings.TIME_ZONE` is the hard-coded literal `"Europe/Podgorica"`
      (not env-overridable); a known UTC instant renders to the expected local wall time under
      each of `ru`/`bs`/`en`; **`ALLOWED_ENV_VARS` is byte-unchanged and no `.env*.example` gained
      a `TIME_ZONE` line**; **the two
      `<time datetime="…|date:'Y-m-d'">` attributes are byte-identical to their pre-block
      state.** ✔
- [ ] **`I18N-005`** — a synthetic plural entry with a blank `msgstr[0]` is reported as a
      violation by **both** `test_no_empty_msgstr` copies; the failure was demonstrated before
      the fix. ✔
- [ ] **`I18N-006`** — the widened bot collector reaches `retry.py`, `states.py`,
      `middlewares/language.py` and the nine-module `handlers/ad_create` package, and the
      `lifecycle.py` exemption is named once with its reason. ✔
- [ ] **`I18N-007`** — the widened template collector discovers app-level template directories
      when they exist, and **fails if it discovers no root at all**. No file count is
      hard-coded. ✔
- [ ] **`I18N-008`** — the `hreflang` include assertion covers all 15 page templates, excludes
      `components/locale_head.html` itself, and does not fail on
      `admin/moderation/review.html` or `analytics/moderation_dashboard.html`. ✔
- [ ] **`I18N-009`** — exactly one writer persists `lang_pref`, and the middleware docstring
      names it. The `Q5` answer is in the commit body. ✔
- [ ] **`I18N-010`** — the chip renders the same separator and grouping as the card price in
      the same response, for all three locales, on **both** the listings and the search route.
      A `None` bound renders as before. ✔
- [ ] **`I18N-011`** — the cookie carries the project's own `secure` and `samesite` values,
      read from settings; `httponly` is `True` under `Q5` option (a) and withheld with a comment
      otherwise. `prod.py` and `dev.py` are untouched. ✔
- [ ] **`I18N-012`** — **the `Vary` header is byte-identical to its pre-block state**, and the
      docstring names `Vary: Cookie` via `CsrfViewMiddleware` and states that the coverage is
      **incidental**. ✔
- [ ] **`I18N-013`** — closed on **Option A**, ruled by the Product Owner on 2026-10-03. Model
      metadata is named as an explicit exemption beside the three template exclusions, in
      **`docs/01-spec/i18n-spec.md` and `docs/99-agent/rules.md`**. **BLOCK 13 did not run:** no
      `models.py` changed, no `gettext_lazy` was added, no catalogue entry was added, and the
      admin tests that assert English field text are **unchanged**. ✔
- [ ] **`I18N-014`** — BLOCK 10's prune is done and BLOCK 11's gate is in place; a synthetic
      orphan **including a wrapped multi-line msgid** fails the gate, and a synthetic `#~`
      block in **each** of `ru`, `bs` and `en` fails the obsolete-symmetry assertion. ✔
- [ ] **`I18N-015`** — `Accept-Language: de-DE,ru;q=0.8,bs;q=0.6` resolves to `ru`; a `q=0`
      member is not selected. ✔
- [ ] **`VAL-003`** — no test added by this plan asserts on rendered chrome for an
      unsupported locale. ✔
- [ ] **`VAL-004`** — the `bs` grouping decision is implemented and covered, or the commit
      body states that `I18N-003` is only half closed. ✔
- [ ] **`N-1`** — a Cyrillic code point in a `bs` `msgstr` fails the gate (demonstrated on the
      pre-fix catalogue) and a Cyrillic code point in a `ru` `msgstr` passes (demonstrated
      too). ✔
- [ ] **`N-2`** — no catalogue contains a `#~` obsolete block. ✔
- [ ] **`N-3`** — no link in `i18n-spec.md` points at a non-existent file, and no missing
      research document was invented. ✔
- [ ] **`N-4`** — no line number is used as a citation in any section this plan corrected, and
      no task used one as a target. ✔

### 8.4 The three claims that must be true of the phase as a whole

1. **Phase 14 was scoped as an engineering project, not a bulk-translation project** — and
   the record says so. The catalogues were 409 active entries each with 0 fuzzy, 0 empty
   `ru`/`bs` `msgstr`s, 0 `msgctxt` and 2 plural entries with 0 blank forms. The real `bs`
   debt was **three strings**, and two of them sit on staff surfaces. The volume in this
   phase is locale resolution, formatting, gate coverage and documentation honesty.
2. **No technical uncertainty was resolved by the Planner.** Six blocks carried a labelled gate,
   two carry an Auditor pre-block step, and one question was answered as "no change". Real `bs`
   translations were gated as a human deliverable and **not written**. The `bs` grouping
   decision, the consent question and the dead links were all **surfaced with their options and
   consequences**, not chosen. **On 2026-10-03 the Product Owner — not the Planner — resolved two
   of them: the `TIME_ZONE` value (hard-coded `Europe/Podgorica`, not env-overridable) and the
   `I18N-013` option (A; BLOCK 13 cancelled). The `bs`-reviewer gate was ruled in its `who`, and
   is recorded as `OPEN-PENDING-REVIEWER` because no sign-off exists.**
3. **The four process hazards were handled as first-class work, not as caveats**: the
   `VAL-003` false-green test, the `I18N-003` half-fix, the six-phase `.po` append race with
   the `--no-obsolete` deletion hazard, and the six-way `base.py` contention each have a
   binding constraint in the block that owns them, a row in §7, and a checkbox above.

**End of plan.** Thirteen blocks, of which **BLOCK 13 is CANCELLED** (2026-10-03) — so twelve
run; four labelled decision gates remain open, `Q1` is `OPEN-PENDING-REVIEWER`, and three real
`bs` strings are routed to a human reviewer rather than written by this plan.


