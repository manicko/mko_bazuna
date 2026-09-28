---
phase: "14"
phase_name: "i18n"
date: "2026-09-28"
auditor: "Executor (subagent)"
validator: "Validator (subagent), Phase 99"
mode: "problems-only"
id_prefix: "I18N"
report_status: "validated"
severity_taxonomy: ".kilo/commands/audit/phases/14-audit-i18n.md#severity-taxonomy"
---

# Audit Findings — i18n (VALIDATED)

> Phase 99 validation. Every finding below carries an explicit verdict.
> **CONFIRMED** = technically correct and currently applicable, kept as filed.
> **ADJUSTED** = the defect is real but severity, type, scope or evidence needed
> correction (the correction is stated in the Validation Note).
> **REJECTED** = the claim does not hold against the tree.
> **MERGED** = folded into another finding.
> **OWNER DECISION** = a real gap that is a product choice, not a code defect.
>
> This file is self-contained: the reader never needs the raw phase report or any
> source file to act on it. No source file, `.po` or `.mo` file was modified
> during validation; `git status --porcelain` reports no modified tracked file.

## Validated Executive Summary

The phase-14 thesis is **sound and independently reproduced**. Fifteen findings
were re-derived from the tree with fresh runtime probes: **12 CONFIRMED, 2
ADJUSTED (one severity change, one type change), 1 re-scoped as an owner
decision, 0 REJECTED**, plus **4 new `VAL-` entries** (one cross-phase conflict,
one coverage gap, two advisories).

The two "money" defects are real and both halves of each were reproduced
independently:

- **`lang_pref` is genuinely unvalidated** (I18N-001, HIGH). Every possible
  mitigation was checked and **none exists**: Django's `LocaleMiddleware` is not
  in `MIDDLEWARE` (`base.py:196-211`), there is no `set_language` view, and
  `translation.activate()` does not consult `settings.LANGUAGES` or normalise.
  Any cookie whose `to_language()` form is not exactly `ru`/`bs`/`en` — i.e. the
  overwhelming majority of real BCP-47 tags — makes every DB-backed string
  (category names, city names, feature tags, ad titles, ad descriptions) silently
  fall through the `locale → ru → name` chain to **Russian**, site-wide, for that
  visitor. The severity stands. Two of the auditor's evidence rows are wrong and
  are corrected below.
- **Fractional prices are not localised; integer prices are** (I18N-003, HIGH).
  Both halves reproduced. The root cause is narrow and the fix is one argument
  change — but the fix as proposed is **incomplete for `bs`** (new evidence below).

One severity is reduced. **I18N-004 (timezone + hardcoded en-US date patterns)
is re-rated HIGH → MEDIUM**: the facts are all reproduced exactly, `USE_TZ` is
`True` (so there is no naive/aware data-integrity class, which is the more
serious thing that could have been true), and no HIGH line in the phase-14
severity taxonomy covers a format/display defect. One severity is reduced for
subsumption (**I18N-002 MEDIUM → LOW**, fully closed by I18N-001), and one impact
claim is refuted (**I18N-012** — the documented cache-bleed cannot occur on full
page responses, for a reason the auditor's isolated probe could not see).

**No finding requires an architectural or structural change.** The auditor's
claim on this point is **CONFIRMED**. Every remedy is a bounded edit inside an
existing seam — one middleware branch, one library call signature, one missing
setting, one parser return type, two collector function bodies, one template
interpolation, one cookie call, one docstring. See "Architectural Assessment".

## Severity Distribution — Before and After Validation

| | CRITICAL | HIGH | MEDIUM | LOW | Total |
|---|---|---|---|---|---|
| **Auditor (as filed)** | 0 | 3 | 7 | 5 | 15 |
| **After validation** | 0 | **2** | **6** | **7** | 15 |

Movements: I18N-004 HIGH→MEDIUM, I18N-002 MEDIUM→LOW. I18N-012 keeps LOW but is
reclassified to `DOC-UPDATE`. No finding is added, removed or merged. Four `VAL-`
entries are added separately (see Cross-Phase Reconciliation and Validation
Summary) and are not counted in the 15.

## Verdict Summary

| ID | Title | Filed | Validated | Verdict | One-line justification |
|---|---|---|---|---|---|
| I18N-001 | `lang_pref` cookie locale unvalidated → catalogue degrades to Russian | HIGH | **HIGH** | **CONFIRMED** (evidence corrected) | No `LocaleMiddleware`, no `set_language` view, no `LANGUAGES` clamp at `translation.activate()` — the cookie branch is the only unvalidated priority source and the fall-through is site-wide. |
| I18N-002 | Unvalidated cookie locale becomes the submenu cache-key segment | MEDIUM | **LOW** | **ADJUSTED** (MEDIUM→LOW) | Entirely subsumed by I18N-001 — once normalised there are exactly three possible segments; what remains is defence-in-depth, not an independent defect. |
| I18N-003 | Prices render with the en-US decimal separator in `ru` and `bs` | HIGH | **HIGH** | **CONFIRMED** (recommendation extended) | Both halves independently reproduced; root cause is exactly as filed. **New evidence:** Django's bundled `bs` locale omits `NUMBER_GROUPING`, so the proposed one-argument fix restores the decimal mark but *not* grouping for `bs`. |
| I18N-004 | `TIME_ZONE` never set (`America/Chicago`) and date patterns hardcoded to en-US | HIGH | **MEDIUM** | **ADJUSTED** (HIGH→MEDIUM) | All facts reproduced exactly and `USE_TZ is True` (no naive/aware class), but the defect is a wrong-by-default display value in one render dimension, and no HIGH rubric line covers it. |
| I18N-005 | `test_no_empty_msgstr` only inspects the last plural form | MEDIUM | **MEDIUM** | **CONFIRMED** | Blind spot reproduced on a synthetic entry; also verified latent — the real `ru`/`bs` catalogues have 0 plural entries with any empty form. |
| I18N-006 | Bot i18n gate scans only `handlers/` (+`services/`) | MEDIUM | **MEDIUM** | **CONFIRMED** (scope extended) | Both collectors confirmed verbatim; the unscanned set is larger than filed — it also contains `retry.py` and `states.py`. |
| I18N-007 | Template i18n gate scans only `TEMPLATES["DIRS"]`, ignoring `APP_DIRS` | MEDIUM | **MEDIUM** | **CONFIRMED** | `DIRS`-only walk confirmed; latent today (no app-level `templates/` directory exists). |
| I18N-008 | `test_hreflang_present` never asserts page templates include the partial | MEDIUM | **MEDIUM** | **CONFIRMED** | Only `components/locale_head.html` is rendered; no page-template include assertion exists. |
| I18N-009 | Switcher gates its cookie write on consent; the server writes unconditionally | MEDIUM | **MEDIUM** | **CONFIRMED** | Both sites confirmed; added evidence — the client helper sets `SameSite=Lax` while the server `set_cookie` does not, so the two writers disagree on more than the gate. |
| I18N-010 | Active-price filter chip interpolates raw `Decimal` values | MEDIUM | **MEDIUM** | **CONFIRMED** | Raw `Decimal` into `{% blocktrans %}` confirmed; `ad_list.html:58` already uses the exact pattern the recommendation proposes. |
| I18N-011 | `lang_pref` cookie emitted without `Secure`/`HttpOnly`/`SameSite` | LOW | **LOW** | **CONFIRMED** | `set_cookie(..., max_age=…)` only; `base.py:139-144` and `prod.py:216-217` harden session+CSRF only. |
| I18N-012 | `Vary: Accept-Language` only; documented cache contract does not hold | LOW | **LOW** | **ADJUSTED** (→`DOC-UPDATE`, impact refuted) | `CsrfViewMiddleware` adds `Vary: Cookie` on every rendered page (every page calls `get_token()`), so a `Vary`-honouring cache already keys on the cookie. Only the docstring claim is wrong. |
| I18N-013 | `verbose_name`/`help_text` untranslated; admin renders English | LOW | **LOW** | **CONFIRMED as OWNER DECISION** | 18 `verbose_name` + 169 `help_text`, zero `gettext_lazy`, zero gettext import in any `models.py` — a real documentation gap, but translating vs. formally exempting is a product call, not a defect. |
| I18N-014 | Six orphaned msgids in all three catalogues; no gate detects stale entries | LOW | **LOW** | **CONFIRMED** | All six verified present in every working-tree `.po` and absent from extraction; `--no-obsolete` omission confirmed in `Makefile:189` and `.kilo/rules/commands.md:89`. |
| I18N-015 | `Accept-Language` q-values ignored; supported lower-ranked tag skipped | LOW | **LOW** | **CONFIRMED** | `de-DE,ru;q=0.8,bs;q=0.6` → `bs` reproduced; only the first tag is examined. |

---

## Cross-Phase Reconciliation

### 1. `RUN_TRANSLATION_BACKFILL` — the open contradiction is resolved; **phase 14 is wrong, phase 02 is right**

**`VAL-001` — CRITICAL (cross-phase conflict). CFG-008 stands; phase-14 Appendix D is incorrect.**

The question put to this validation was whether `RUN_TRANSLATION_BACKFILL` is
actually consumed, given that phase 14 states no `RunTranslationBackfill`
command exists.

**The variable is consumed.** It is read at
`src/backend/apps/core/utils/migrate_locked.py:57`:

```python
    if os.getenv("RUN_TRANSLATION_BACKFILL") == "true":
        steps_list.append(("backfill_translations",))
        logger.info("Translation backfill enabled (RUN_TRANSLATION_BACKFILL=true)")
```

`_build_steps()` is called by `migrate_locked.main()` (line 87) inside the
`AdvisoryLockId.MIGRATE` session-scoped lock, and `migrate_locked.main()` is the
body of the `migrate` Compose one-shot service, reached through
`apps/core/management/commands/bootstrap_reference_data.py`. The flag therefore
has a live, production-reachable effect: it appends a fourth bootstrap step that
invokes `backfill_translations`. It is also documented as operator-facing in
**seven** places: `docs/ops/migration-workflow.md:83,95,107,343,412`,
`docs/ops/docker-deployment.md:145,330`, `docs/ops/VERIFY_TESTS_INSTRUCTIONS.md:80,125,192`,
`docs/99-agent/architecture.md:57`, `docs/01-spec/architecture-structure.md:207,315`.

**Phase 14's Appendix D answered a question that was never asked.** The contested
claim is about an **environment variable**, not about a management-command class
name. Appendix D searched for a command called `RunTranslationBackfill` /
`run_translation_backfill`, correctly found none, and reported that absence as if
it settled whether the variable is consumed. It did not. There is no requirement
that a consumed env var correspond to a same-named command — the two names here
(`RUN_TRANSLATION_BACKFILL` → `backfill_translations`) were never the same, which
is exactly why the search found nothing. An exhaustive repo-wide search for the
three spellings returns 61 hits, all of which either consume the variable,
document it, test it, or are the Appendix D claim itself; there is **no** hit
anywhere in the tree for a `run_translation_backfill` command.

**Consequence.** CFG-008 (LOW, CONFIRMED) is unaffected: `RUN_TRANSLATION_BACKFILL`
is a genuinely consumed name absent from `ALLOWED_ENV_VARS`
(`base.py:19-38`) and from every `.env*.example`. The phase-14
"not audited" list is **not honest on this item** — it asserts an absence that
reads as exonerating ("only translation-backfill entry point is
`backfill_translations.py`") while leaving the actual consumption site
(`migrate_locked.py:57`) unexamined. Anyone reconciling these two reports from
phase 14's text alone would wrongly close CFG-008.

**Required action:** delete or rewrite the Appendix D bullet. The correct
statement is: *"the flag is consumed by `apps/core/utils/migrate_locked.py:57`,
which conditionally appends the `backfill_translations` step; the flag's absence
from `ALLOWED_ENV_VARS` is filed as CFG-008 in phase 02."*

### 2. Deferred phase-08 item — **missed**, and its premise is now stale

**`VAL-002` — MEDIUM (coverage gap). Assigned to phase 14, not addressed.**

Phase 08's validated report explicitly deferred this item to phase 14, in a
table row and in an in-body advisory:

> "Classification belongs to phase 14; recorded here so it is not lost."
> — `99-validation/08-search-fts-validated-findings.md:291-296`, deferred per
> `:1095` ("SRCH-002 (sub-note) … **classification deferred to 14**")

The claim was that `sanitize_query_for_log` "iterates `char.isalpha()` and drops
every non-alphabetic character, so Cyrillic and Montenegrin input collapses to
its letters while Serbian Latin characters (`č`, `ć`, `š`, `đ`, `ž`) and digits
are lost entirely", degrading incident triage for two of the three locales.

**Phase 14's report contains zero occurrences of `sanitize_query_for_log`.** The
item was not addressed, not mentioned, and not listed in Appendix D. This is a
genuine coverage gap against an explicit hand-off.

**Resolving it now.** The current implementation has **no `isalpha()` at all**:

```python
def sanitize_query_for_log(query: str | None) -> str:
    if not query:
        return ""
    cleaned = _CONTROL_CHAR_PATTERN.sub("", query)
    return cleaned[:_MAX_QUERY_LENGTH]
```
— `src/backend/apps/core/utils/sanitize.py:108-124`

A repo-wide search for `isalpha|isalnum|isdigit` across `sanitize.py`, its tests
and the search app returns **no hits**. The function strips only control
characters (`[\x00-\x1f\x7f-\x9f]`) and truncates to 100 chars, so Cyrillic,
Serbian Latin diacritics and digits all pass through intact.

**Verdict on the deferred item: STALE — the premise is no longer true in the
current tree, and the underlying triage concern is already satisfied.** No new
finding is raised. The residual action is procedural: close the phase-08
deferral explicitly rather than leaving it dangling, and correct the phase-08
advisory text, which still asserts behaviour the code no longer has.

### 3. Phase 09 / Phase 10 overlap — checked, no gap, no duplication

- **Phase 09 (API-007, MEDIUM, narrowed to `backfill_translations`) owns the
  Google-Translate client.** Phase 14's Appendix D correctly declines to re-audit
  the client's resilience and PII posture and defers to API-007. That is the
  right boundary and matches the phase-14 handbook §6 exclusion. No duplication.
- **Phase 10 (CQ-015, HIGH) owns the duplicated 11-field `ListingsQueryParams`
  build and the ~15-key template context in `listings.py` / `search.py`.** The
  concern raised was that duplicated template context is where untranslated keys
  typically hide. **Checked and clear:** both views feed the *same* partial,
  `ads/partials/ad_list.html` (`listings.py:263-263` and `search.py:196`), so any
  untranslated text in a duplicated context key would surface in a template the
  gate already scans. The gate run below (55 tests, all green) covers
  `test_no_hardcoded_visible_text` and `test_template_extraction_coverage` over
  that partial. There is no place for an untranslated key to hide. Both context
  dicts were diffed key-by-key and found consistent — `listings.py:268` does
  supply `active_price_max`, so the chip has both bounds on both routes. No
  coverage gap, and nothing for phase 14 to claim.

---

## Architectural Assessment

**The auditor's claim — "no finding requires an architectural change; all fixes
are localized" — is CONFIRMED.** Independently checked finding by finding:

| Change surface | Findings | Nature of the edit |
|---|---|---|
| `LanguagePreMiddleware` | I18N-001, I18N-011, I18N-012, I18N-015 | Route three inputs through one existing resolver; add cookie flags; docstring. No new module, no new abstraction. |
| Submenu cache key | I18N-002 | One f-string argument. |
| `price_tags._format_amount` | I18N-003 | One function; the helper already exists and already receives a `Decimal`. |
| `config/settings/base.py` | I18N-004 | One added setting, env-overridable by the file's existing `env()` idiom. |
| `testing/i18n_helpers.py` + 3 call sites | I18N-005 | One return type. |
| Two collector functions in the gate | I18N-006, I18N-007 | Replace two hard-coded directory tuples with `rglob` / app-config roots. |
| One assertion added to an existing test | I18N-008 | Additive. |
| `language_switcher.html` + middleware comment | I18N-009 | Delete a JS branch, or move a gate — plus a spec line. |
| `ad_list.html` chip + view context | I18N-010 | Follow the pattern already used 14 lines below the defect. |
| `makemessages` invocation + one new assertion | I18N-014 | Flags plus a test. |
| `docs/01-spec/i18n-spec.md`, `docs/99-agent/rules.md` | I18N-013 | Documentation. |

Two points where the *recommended* fix, taken alone, is architecturally
incomplete — both are called out in their findings rather than silently accepted:

- **I18N-003** — a one-argument change in `_format_amount` is necessary but does
  not restore grouping for `bs` (see the finding). The complete remedy needs a
  project-owned number-format decision, not a library call tweak.
- **I18N-001** — normalising only in the middleware leaves the model accessors
  (`Category.get_name`, `City.get_name`, `LookupItem.get_name`, `Ad.get_title`,
  `Ad.get_description`) still doing an exact-key dict test against an arbitrary
  string. The auditor's own recommendation calls this out; it is the right call
  and it is a **type-boundary** change (accept `LanguageLocale`, not `str`), not
  a patch. It is the only item here with any structural dimension, and even that
  is a signature tightening inside five small accessors — not a redesign.

**No new module, no new abstraction, no new cross-cutting pattern is warranted
by any finding in this phase.** The high-value structural item is
**I18N-001's accessor typing**, and it should be sequenced *after* the middleware
fix so the normalisation is in place first.

---

## Findings by Severity — Validated

### HIGH

#### I18N-001: [HIGH] — `lang_pref` cookie locale is neither normalized nor validated → whole catalogue silently degrades to Russian

> **Validation Note:**
> - **Action:** CONFIRMED (HIGH retained; evidence corrected; type broadened to
>   `SPEC-DEVIATION`)
> - **Detail:** The mechanism, the absent mitigation and the site-wide blast
>   radius are all independently reproduced. The phase-14 severity taxonomy
>   assigns HIGH to "Locale priority chain broken (… no normalization)", which
>   this matches exactly. **Corrections:** (a) the auditor's second evidence
>   table is wrong for `EN` and `en_US` — it fed raw cookie strings straight to
>   the accessors, but the real request path passes
>   `translation.get_language()` (Django's `to_language()`, which lower-cases and
>   hyphen-normalises), so `cookie=EN` resolves to `en` and the DB content comes
>   out **English**, not Russian; (b) the claim that "the page chrome is in the
>   selected language" is wrong for unsupported values — Django's
>   `DjangoTranslation._add_fallback` (`trans_real.py:235-250`) falls back to
>   `settings.LANGUAGE_CODE`, so under production settings (`LANGUAGE_CODE="ru"`)
>   an `xx` cookie makes the chrome **Russian too**; the auditor's probes ran
>   under `config.settings.test` where `LANGUAGE_CODE="en"`, so the observed
>   chrome was English. (c) `SPEC-DEVIATION` additionally: `docs/01-spec/i18n-spec.md:63`
>   states unconditionally that "the resolved code is normalized by
>   `LanguageLocale.from_code()`" — that is false for the cookie branch.
> - **See also:** I18N-002 (subsumed), I18N-011 (the enabler for a cross-site
>   overwrite), `VAL-003`.

| Field | Value |
|---|---|
| **ID** | I18N-001 |
| **Type** | `SPEC-DEVIATION` — code contradicts the documented normalisation contract (`docs/01-spec/i18n-spec.md:63`) and silently violates the `locale → ru → name` chain |
| **Category** | Correctness — runtime locale resolution |
| **File(s)** | `src/backend/apps/core/middleware/language.py:66-69` (raw cookie branch), `:111-130` (`_apply_lang_param`, the only normalising path), `src/backend/apps/categories/models.py:54-63`, `src/backend/apps/locations/models.py` (`City.get_name`), `src/backend/apps/lookups/models.py` (`LookupItem.get_name`), `src/backend/apps/ads/models.py` (`Ad.get_title` / `Ad.get_description`) |
| **Status** | Open |
| **Problem** | `process_request` validates and normalises only the `?lang=` query parameter. The cookie branch passes the raw cookie string to `_set_language_code`, which forwards it to `translation.activate()` and then assigns `request.LANGUAGE_CODE = translation.get_language()`. Templates pass `request.LANGUAGE_CODE` to `\|get_category_name`, `\|get_city_name`, `\|get_lookup_name`, `\|get_title`, `\|get_description`; each accessor is an exact dict-key test whose next branch is `name_i18n["ru"]`. |
| **Impact** | For any cookie whose `to_language()` form is not exactly `ru`, `bs` or `en`, every DB-backed string on the page renders in **Russian** while the page claims another language — and under production settings the gettext chrome falls back to Russian as well, so `?`/`xx`-style values produce a wholly Russian page. Real BCP-47 tags (`en-US`, `en_US`, `ru-RU`, `de-DE`, `sr-Latn`) are exactly the values that fail. The site never writes such a value itself (`_apply_lang_param` persists only the resolved canonical code, `language.py:120-122`), so the realistic trigger is an externally-written cookie — a cross-site overwrite enabled by I18N-011's missing `SameSite`, a subdomain, or manual editing. Harm is content-legibility, not data exposure or privilege escalation. |
| **Root Cause** | Normalisation lives only in `_apply_lang_param`. The cookie branch was never given the same treatment although the module docstring (`language.py:4-7`) and the i18n spec both claim the resolved code is normalised. |
| **Recommendation** | Route all three sources through one resolver: `LanguageLocale.from_code(raw, fallback=LanguageLocale.BOSNIAN).value` before `translation.activate()`. Tighten the five model accessors to accept `LanguageLocale` rather than `str` (the only structural item in this phase) so a bad locale degrades to `ru` *deliberately*. Add the non-canonical-cookie regression case that is missing from `test_language_middleware.py:284-301` (its table only exercises `{"lang_pref": "bs"}` — canonical only). |
| **Effort** | S (middleware) + S (accessor typing) |
| **Priority** | P0 |
| **Related Findings** | I18N-002, I18N-011, `VAL-003` |

**Evidence — mitigation check (all negative; the finding survives)**

```text
# base.py:196-211  MIDDLEWARE — no django.middleware.locale.LocaleMiddleware
"django.contrib.auth.middleware.AuthenticationMiddleware",
"apps.core.middleware.language.LanguagePreMiddleware",   <-- the only locale authority
"apps.core.middleware.city_resolution.CityResolutionMiddleware",
```
```python
# trans_real.py:296-303  activate() does not consult settings.LANGUAGES and does not normalise
def activate(language):
    if not language:
        return
    _active.value = translation(language)
```
`grep` over `src/backend`: no `set_language` view, no `i18n_patterns`, no second
`translation.activate` call site. There is **no** constraint between the cookie
and `translation.activate`.

**Evidence — validator runtime probe, the real request path** (validator-authored;
`RequestFactory` + `LanguagePreMiddleware`; the second column is
`Category.get_name(<that value>)` on an unsaved instance carrying
`{"ru","bs","en"}`; settings forced to `LANGUAGE_CODE="ru"` to match production):

```text
cookie='bs'     -> req.LANGUAGE_CODE='bs'      cat='Transport'     chrome='Sve kategorije'
cookie='en'     -> req.LANGUAGE_CODE='en'      cat='Transport'     chrome='All categories'
cookie='en-US'  -> req.LANGUAGE_CODE='en-us'   cat='Транспорт'      chrome='All categories'      <-- auditor's claim HOLDS
cookie='EN'     -> req.LANGUAGE_CODE='en'      cat='Transport'     chrome='Все категории'         <-- auditor's row WRONG (names are English)
cookie='en_US'  -> req.LANGUAGE_CODE='en-us'   cat='Транспорт'      chrome='All categories'       <-- auditor's row WRONG
cookie='xx'     -> req.LANGUAGE_CODE='xx'      cat='Транспорт'      chrome='Все категории'         <-- whole page Russian in prod
cookie='de-DE'  -> req.LANGUAGE_CODE='de-de'   cat='Транспорт'      chrome='Все категории'
cookie='ru-RU'  -> req.LANGUAGE_CODE='ru-ru'   cat='Транспорт'      chrome='Все категории'
```

**Evidence — why the chrome column differs (the correction the auditor could not see)**

```text
DjangoTranslation('en-us') _fallback=no  to_language='en-us'   # startswith("en") -> _add_fallback returns early
DjangoTranslation('EN'   ) _fallback=yes to_language='en'      # case-sensitive startswith("en") is False
DjangoTranslation('xx'   ) _fallback=yes to_language='xx'
```
`trans_real.py:235-250`. Consequence: **the symptom differs between production
and the test settings**, which is the whole of `VAL-003`.

**Evidence — the test gap that lets it ship** (`test_language_middleware.py:284-301`)

```python
(None, {"lang_pref": "bs"}, None, "bs"),         # cookie  (canonical only)
```

**Evidence — spec deviation** (`docs/01-spec/i18n-spec.md:63`)

> "The resolved code is normalized by `LanguageLocale.from_code()` (accepts
> `en-US` → `en`, falls back to `bs` when unsupported)."

Stated for the resolved code generally; true only of the query parameter.

---

#### I18N-003: [HIGH] — Prices render with the en-US decimal separator in `ru` and `bs`

> **Validation Note:**
> - **Action:** CONFIRMED (HIGH retained; **recommendation extended** with new
>   evidence)
> - **Detail:** Both halves of the asymmetry independently reproduced, the
>   `ru`/bs` separators confirmed from Django's own locale data, and the
>   non-localisation confirmed to originate in the `str`-typed argument exactly as
>   filed. **Addition the auditor missed:** Django's bundled `bs` locale data
>   leaves `NUMBER_GROUPING` undefined, and `numberformat.format` line 34
>   (`use_grouping = use_grouping and grouping != 0`) hard-disables grouping on
>   that value *even under `force_grouping=True`*. So the recommended
>   one-argument fix restores the **decimal mark** for `bs` but **not** the
>   **thousands grouping**. The fix as filed is necessary, not sufficient.
> - **See also:** I18N-010, `VAL-004`.

| Field | Value |
|---|---|
| **ID** | I18N-003 |
| **Type** | `SPEC-DEVIATION` — the project's own `test_price_format.py:24-28` docstring asserts locale-aware grouping; the code does not deliver it |
| **Category** | Correctness — format localization (numbers) |
| **File(s)** | `src/backend/apps/ads/templatetags/price_tags.py:43-58`, `src/backend/apps/ads/tests/test_price_format.py:22-32` |
| **Status** | Open |
| **Problem** | `_format_amount` converts the `Decimal` to a string and passes the **string** to `intcomma`. `intcomma` localises only `float`/`Decimal`; for a `str` it does `int(value)`, which raises `ValueError` on any fractional amount, and the `except` branch recurses with `use_l10n=False` — a path that hard-codes `,` as the grouping separator and leaves the `.` decimal mark untouched. Integer amounts survive the `int()` and take the localising path, which is why the defect is invisible for round prices. |
| **Impact** | Every ad card, ad detail page, search-result chip and Telegram alert that carries a fractional price renders `1,234.56` for all three locales. Russian (`1 234,56`) and Bosnian (`1.234,56`) readers get an en-US decimal point on a money value. Because `LANGUAGE_CODE = "ru"` and the `locale → ru → name` chain makes Russian the source language, this affects the **primary** market, not only the secondary ones. The same screen also shows a correctly grouped integer chip, so the page contradicts itself. |
| **Root Cause** | `intcomma` used as if it were locale-agnostic string formatting; its documented non-localised `str` fallback is silently taken for exactly the values that need localising. The existing test asserts only that *grouping happened*, never which separator, so the belief in the docstring was never tested. |
| **Recommendation** | Pass the `Decimal` to `intcomma` (or call `number_format` directly) after trimming the exponent on the `Decimal` rather than on the rendered string. **Additionally**, decide `bs` grouping explicitly — a project-level `FORMATS` override supplying `NUMBER_GROUPING = 3` for `bs`, or a shared number-format helper that does not rely on `number_format`'s grouping gate. Update `test_format_price_value_uses_intcomma` to assert the exact per-locale output for a fractional amount and add a ≥7-digit case so grouping is actually exercised. Per project rule "production code is king", the test follows the corrected behaviour. |
| **Effort** | S |
| **Priority** | P0 |
| **Related Findings** | I18N-010 |

**Evidence — the call site** (`price_tags.py:52-58`)

```python
    rounded = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP).normalize()
    formatted = format(rounded, "f")
    if "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")
    return intcomma(formatted)          # <-- str, not Decimal
```

**Evidence — the library contract** (`django/contrib/humanize/templatetags/humanize.py:67-88`) — quoted source matches the auditor's reproduction byte-for-byte.

**Evidence — validator runtime probe: the asymmetry, both halves** (`format_price_value(Decimal(a), "EUR")`)

```text
[en] THOUSAND_SEPARATOR=',' (U+002C)  DECIMAL_SEPARATOR='.' (U+002E)
          1250 -> '1,250 EUR'         1234.56 -> '1,234.56 EUR'   1000000 -> '1,000,000 EUR'
[ru] THOUSAND_SEPARATOR='\xa0' (U+00A0 non-breaking space)  DECIMAL_SEPARATOR=',' (U+002C)
          1250 -> '1\xa0250 EUR'  OK   1234.56 -> '1,234.56 EUR'  WRONG   1000000 -> '1\xa0000\xa0000 EUR'  OK
[bs] THOUSAND_SEPARATOR='.' (U+002E)  DECIMAL_SEPARATOR=',' (U+002C)
          1250 -> '1250 EUR'          1234.56 -> '1,234.56 EUR'   WRONG   1000000 -> '1000000 EUR'
```
Integer amounts localise; fractional amounts do not. **Confirmed as filed.**

**Evidence — the two candidate fixes side by side** (validates the `ru`/`bs` expectations exactly)

```text
[en] intcomma('1234.56')='1,234.56'    intcomma(Decimal('1234.56'))='1,234.56'    -> already correct
[ru] intcomma('1234.56')='1,234.56'    intcomma(Decimal('1234.56'))='1\xa0234,56'
[bs] intcomma('1234.56')='1,234.56'    intcomma(Decimal('1234.56'))='1234,56'
```

**Evidence — NEW: the `bs` grouping gap the recommendation as filed does not close**

```text
[en] NUMBER_GROUPING=3   number_format(1e6, force_grouping=True)='1,000,000'
[ru] NUMBER_GROUPING=3   number_format(1e6, force_grouping=True)='1\xa0000\xa0000'
[bs] NUMBER_GROUPING=0   number_format(1e6, force_grouping=True)='1000000'   <-- force_grouping ignored
```
`django/utils/numberformat.py:34` — `use_grouping = use_grouping and grouping != 0`.
`django/conf/locale/bs/formats.py` has `# NUMBER_GROUPING =` (commented out) and
sets only `DECIMAL_SEPARATOR = ","` / `THOUSAND_SEPARATOR = "."`; `ru/formats.py`
sets all three including `NUMBER_GROUPING = 3`. So for `bs` the thousands
separator is configured but structurally unreachable.

---

### MEDIUM

#### I18N-004: [MEDIUM — was HIGH] — `TIME_ZONE` is never set (`America/Chicago`) and date patterns are hardcoded to en-US

> **Validation Note:**
> - **Action:** ADJUSTED — **HIGH → MEDIUM**. Type, mechanism and evidence stand
>   entirely; only the severity and the framing are corrected.
> - **Detail:** Every factual claim reproduced exactly, including the probe value
>   `timezone.localtime(2026-09-05T23:30Z) = 2026-09-05T18:30:00-05:00` and the
>   per-locale `'M d, Y'` renderings. Three reasons for the downgrade:
>   (1) **the `USE_TZ` question is settled in the project's favour** —
>   `USE_TZ` is not set explicitly, but the Django 5 global default is `True`
>   (confirmed against `django.conf.global_settings`), so every stored and
>   rendered datetime is aware and the more serious naive/aware mismatch class
>   does **not** exist here; the auditor's report did not check this, and the
>   downgrade depends on it. (2) The defect is a wrong-by-default **display**
>   value in one render dimension (timestamps), not a broken mechanism, and not
>   site-wide content corruption as in I18N-001. (3) The phase-14 severity
>   taxonomy's HIGH line is "Locale priority chain broken (cookie overrides
>   `lang` param; no normalization)" — a timezone default matches no HIGH line.
>   It stays well above LOW because every ad's freshness timestamp — the signal a
>   buyer uses to judge a listing — is wrong by 5-7 hours and can mis-state the
>   calendar day. **Also added:** the `<time datetime="{{ …|date:'Y-m-d' }}">`
>   attributes at `ads/detail.html:159` and `ads/partials/ad_list.html:143` are
>   correct machine-readable ISO values and must **not** be swept into the
>   locale-format change.
> - **See also:** I18N-003, I18N-010.

| Field | Value |
|---|---|
| **ID** | I18N-004 |
| **Type** | `SPEC-DEVIATION` — the site's operating region is Montenegro/Bosnia, so `America/Chicago` and en-US date order are not neutral defaults |
| **Category** | Correctness — format localization (dates) |
| **File(s)** | `src/backend/config/settings/base.py:128-136` (i18n block; no `TIME_ZONE`), `src/backend/templates/ads/detail.html:160`, `src/backend/templates/ads/partials/ad_list.html:144`, `src/backend/templates/cabinet/search_history.html:43`, `src/backend/templates/analytics/seller_dashboard.html:87` |
| **Status** | Open |
| **Problem** | No settings module sets `TIME_ZONE`, so Django's default `America/Chicago` (UTC−5/−6) applies. Separately, all four user-visible date renderings hardcode the en-US pattern `'M d, Y'` / `'M d'` / `'M d, H:i'` instead of the locale format. `USE_TZ` is `True` (Django 5 default), so this is presentation-only — no data-integrity exposure. |
| **Impact** | Publish times, ad-card dates, search-history timestamps and seller-dashboard metric dates are all computed in US Central for a Balkan marketplace. For an ad published between 00:00 and 07:00 local the **calendar day itself** is wrong, and a day-old ad can read as published today. Month-first order is wrong in both `ru` and `bs`. |
| **Root Cause** | `TIME_ZONE` was never added alongside `LANGUAGE_CODE` in the i18n block, and the templates reach for an en-US pattern string instead of the locale format name. The i18n gate inspects translation *wrapping*, not format tokens, so neither is covered. |
| **Recommendation** | Set `TIME_ZONE` env-overridable next to `LANGUAGE_CODE` using the file's existing `env()` idiom. Replace only the four **display** patterns with locale format names (`'DATE_FORMAT'` for detail/dashboard, `'SHORT_DATE_FORMAT'` for the card, `'DATETIME_FORMAT'` for search history) — leave the two `datetime="…"` ISO attributes alone. Add a `unit` test asserting `settings.TIME_ZONE` and that a known UTC instant renders to the expected local time. |
| **Effort** | S |
| **Priority** | P1 |
| **Related Findings** | I18N-003, I18N-010 |

**Evidence — validator probe**

```text
settings.TIME_ZONE='America/Chicago'
settings.USE_TZ=True
django.conf.global_settings.USE_TZ default=True       <-- no naive/aware class
UTC instant 2026-09-05T23:30Z -> localtime 2026-09-05T18:30:00-05:00   (06:30 on 6 Sep in Belgrade)

[en] 'M d, Y'='Sep 05, 2026'    'M d'='Sep 05'    'M d, H:i'='Sep 05, 18:30'    DATE_FORMAT='Sept. 5, 2026'
[ru] 'M d, Y'='Сен 05, 2026'    'M d'='Сен 05'    'M d, H:i'='Сен 05, 18:30'    DATE_FORMAT='5 сентября 2026 г.'
[bs] 'M d, Y'='Sep. 05, 2026'   'M d'='Sep. 05'   'M d, H:i'='Sep. 05, 18:30'   DATE_FORMAT='5. septembar 2026.'
```

**Evidence — the four hardcoded patterns (exhaustive `|date:` sweep of `src/backend/templates`)**

```text
ads/detail.html:159                <time datetime="{{ ad.published_at|date:'Y-m-d' }}">   <- ISO, leave alone
ads/detail.html:160                {% trans "Published:" %} {{ ad.published_at|date:'M d, Y' }}
ads/partials/ad_list.html:143      <time datetime="{{ ad.published_at|date:'Y-m-d' }}">   <- ISO, leave alone
ads/partials/ad_list.html:144      {{ ad.published_at|date:'M d' }}
cabinet/search_history.html:43     {{ entry.created_at|date:"M d, H:i" }}
analytics/seller_dashboard.html:87 {{ metric.date|date:"M d, Y" }}
```
No other `|date:` filter exists in any template — the finding's inventory is
complete and correct.

---

#### I18N-002: [LOW — was MEDIUM] — Unvalidated cookie locale becomes the submenu cache-key segment

> **Validation Note:**
> - **Action:** ADJUSTED — **MEDIUM → LOW**.
> - **Detail:** The mechanism is confirmed (`categories/views.py:51` embeds
>   `request.LANGUAGE_CODE`; TTLs `SUBMENU_CACHE_TTL=300`, stale `60`, lock `30`
>   as filed; the endpoint is an unauthenticated GET with no rate-limit
>   middleware configured). But the finding is **entirely subsumed by I18N-001**:
>   once the cookie is normalised there are exactly three possible key segments,
>   so the "unbounded cardinality" is not an independent defect — it is an
>   artefact of I18N-001, with the same root cause. What survives as a standalone
>   item is defence-in-depth (the key-building site trusts a request attribute
>   that has not itself passed through the enum), which is LOW, not MEDIUM. Its
>   remediation already sits inside I18N-001's scope. The auditor's own
>   recommendation concedes this ("Fixing I18N-001 closes this automatically"),
>   which contradicts its own MEDIUM rating and P1 priority — re-rated accordingly.
> - **See also:** I18N-001.

| Field | Value |
|---|---|
| **ID** | I18N-002 |
| **Type** | `BEST-PRACTICE` (defence-in-depth) |
| **Category** | Operability — cache keying |
| **File(s)** | `src/backend/apps/categories/views.py:51`, `src/backend/apps/core/middleware/language.py:66-69` |
| **Status** | Open — **closed by I18N-001**; retained as defence-in-depth |
| **Problem** | The submenu fragment cache key is `category:submenu:<tree_version>:<slug>:<request.LANGUAGE_CODE or 'ru'>`. The locale segment does its documented job (no cross-language bleed) but is built from the unvalidated cookie string of I18N-001, so each distinct cookie value yields a distinct entry per category slug, each held for ~6 minutes. |
| **Impact** | A client walking the cookie through N values forces N × |categories| fragment renders and cache entries. The ceiling is Redis memory, not correctness. Eliminated by fixing I18N-001. |
| **Root Cause** | The key is built from a raw request attribute rather than from a value that has passed through `LanguageLocale`. |
| **Recommendation** | Fix I18N-001. As defence in depth, build the segment from `LanguageLocale.from_code(request.LANGUAGE_CODE, fallback=LanguageLocale.RUSSIAN).value`. |
| **Effort** | S |
| **Priority** | P2 |

**Evidence — `categories/views.py:51`**
```python
    cache_key = f"category:submenu:{get_tree_version()}:{category.slug}:{request.LANGUAGE_CODE or 'ru'}"
```
**Evidence — `apps/categories/cache.py`** — `SUBMENU_CACHE_TTL = 300`,
`SUBMENU_CACHE_STALE_TTL = 60`, `SUBMENU_CACHE_LOCK_TTL = 30` (SWR invariant
lock < stale, as documented). No rate-limit setting exists in any
`config/settings/*.py`.

---

#### I18N-005: [MEDIUM] — `test_no_empty_msgstr` only inspects the last plural form

> **Validation Note:**
> - **Action:** CONFIRMED (unchanged)
> - **Detail:** Reproduced on a synthetic plural entry, and independently
>   confirmed **latent** against the real catalogues: 0 plural entries in `ru` or
>   `bs` have any empty form today (`en` has 2, which is the documented
>   exemption). The DoD contract is genuinely unenforced for plural entries — a
>   latent hole, exactly as filed, not an inflated one.
> - **See also:** I18N-014.

| Field | Value |
|---|---|
| **ID** | I18N-005 |
| **Type** | `BEST-PRACTICE` — the DoD gate cannot see a class of violation it is specified to catch |
| **Category** | Test-gate completeness |
| **File(s)** | `src/backend/testing/i18n_helpers.py:45-52`, `src/backend/apps/ads/tests/test_i18n_completeness.py:428-437`, `src/backend/apps/ads/tests/test_i18n_pipeline.py:48-61` |
| **Status** | Open |
| **Problem** | `_parse_po_entries` reassigns `cur_msgstr` on every `msgstr`-prefixed line, including `msgstr[N]`, discarding all but the last plural form. Both copies of `test_no_empty_msgstr` then ask "is any msgstr blank?", which for a plural entry is only ever a question about the last form. The docstring claims the parser shares "the first `msgstr` value encountered"; the implementation keeps the **last**. |
| **Impact** | A translator or bulk edit can blank the Russian singular form and the gate stays green. At runtime the seller dashboard then renders `1 просмотров` instead of `1 просмотр`. The current catalogues are correct, so this is a latent hole. |
| **Root Cause** | The shared parser returns one `(msgid, msgstr)` pair per entry and has no representation for multiple plural forms. Neither of its two callers noticed. |
| **Recommendation** | Return `list[tuple[str, list[str]]]` and flatten with "any blank form is a violation". Add a regression test feeding the parser a plural entry with a blank `msgstr[0]`. Sequence with I18N-014 — a credible "no orphan entries" gate depends on a plural-aware parser. |
| **Effort** | S |
| **Priority** | P1 |

**Evidence — `i18n_helpers.py:47-52`**
```python
        elif stripped.startswith("msgstr"):
            in_msgstr = True
            rest = stripped[len("msgstr") :]
            if rest.startswith("["):
                rest = rest[rest.index("]") + 1 :]   # index discarded
            cur_msgstr = [_unescape(rest)]           # previous forms dropped
```

**Evidence — validator probe (identical result to the auditor's, independently obtained)**
```text
  msgid='%(counter)s view'  msgstr='%(counter)s просмотров'    <-- msgstr[0] was ""
  reported EMPTY: []      EXPECTED: ['%(counter)s view']      GATE BLIND SPOT CONFIRMED
```

**Evidence — NEW: the real catalogues are clean, so this is latent**
```text
  ru: plural entries=2  with any empty form=0
  bs: plural entries=2  with any empty form=0
  en: plural entries=2  with any empty form=2     (documented exemption)
```

---

#### I18N-006: [MEDIUM] — Bot i18n gate scans only `handlers/` (+`services/`)

> **Validation Note:**
> - **Action:** CONFIRMED (scope extended)
> - **Detail:** Both collectors confirmed verbatim. The finding understates the
>   unscanned set: the module root also contains **`retry.py`** and
>   **`states.py`**, which the auditor's title omits. Root cause and remedy are
>   unchanged. The finding's own honesty is noted — it correctly states
>   `lifecycle.py` is *not* currently defective, and the delivered gate run
>   confirms that.
> - **See also:** I18N-014 (the four orphaned command-menu msgids).

| Field | Value |
|---|---|
| **ID** | I18N-006 |
| **Type** | `BEST-PRACTICE` — gate scope narrower than the surface it is specified to protect |
| **Category** | Test-gate completeness |
| **File(s)** | `src/backend/apps/ads/tests/test_i18n_completeness.py:796-799`, `:959-966`, `src/telegram_bot/lifecycle.py:31-55` |
| **Status** | Open |
| **Problem** | `test_bot_no_hardcoded_messages` collects from `telegram_bot/handlers/` only; `test_bot_no_raw_model_field_access` from `handlers/` + `services/`. Unscanned and user-visible-capable: `lifecycle.py`, `main.py`, `retry.py`, `states.py`, `middlewares/*.py` (5 modules), `schemas/*.py` (4 modules). |
| **Impact** | Latent. `lifecycle.py` proves the surface is reachable — it holds four user-visible `BotCommand(description=…)` literals per language. The gate cannot distinguish "deliberately localised literal" from "a `_()` wrapper was dropped" outside `handlers/`. |
| **Root Cause** | The collectors hard-code two subdirectories instead of walking `telegram_bot/` and excluding only `tests/`. `main.py` and `lifecycle.py` postdate the gate. |
| **Recommendation** | `rglob("*.py")` over `telegram_bot` minus `tests/`; add `BotCommand` `description=` to the user-facing keyword set; record the four now-dead command-menu msgids as a documented, commented exemption. |
| **Effort** | S |
| **Priority** | P1 |

**Evidence — collectors confirmed verbatim** (`test_i18n_completeness.py:796-799` and `:959-966`), both matching the quoted source.

**Evidence — the actual unscanned set** (validator enumeration of `src/telegram_bot`, tests excluded)
```text
__init__.py  lifecycle.py  main.py  retry.py  states.py
middlewares/{__init__,connection,language,permissions,update_id_dedup}.py
schemas/{__init__,callbacks,message_payloads,saved_search}.py
```

**Evidence — the reachable surface** (`lifecycle.py:31-55`) — the quoted `_COMMANDS`
block and its comment are present verbatim, including the explanation that the
`en` entries are intentionally not gettext msgids.

---

#### I18N-007: [MEDIUM] — Template i18n gate scans only `TEMPLATES["DIRS"]`, ignoring `APP_DIRS`

> **Validation Note:**
> - **Action:** CONFIRMED (unchanged)
> - **Detail:** Confirmed — `_collect_template_files` iterates
>   `tmpl_cfg.get("DIRS", [])` and never consults `APP_DIRS`, while
>   `base.py:215-236` sets `APP_DIRS: True`. Latent today: the only template
>   roots on disk are `src/backend/templates` (43 files) and an empty
>   `src/templates`, so nothing is currently out of scope. The auditor correctly
>   frames this as a coverage-loss risk on refactor rather than a live gap, and
>   the gate's own docstring ("public/seller-facing templates") does overstate
>   coverage. No adjustment.
> - **See also:** I18N-008, I18N-005, I18N-006.

| Field | Value |
|---|---|
| **ID** | I18N-007 |
| **Type** | `BEST-PRACTICE` |
| **Category** | Test-gate completeness |
| **File(s)** | `src/backend/apps/ads/tests/test_i18n_completeness.py:80-100`, `src/backend/config/settings/base.py:215-236` |
| **Status** | Open |
| **Problem** | Only `DIRS` is walked. With `APP_DIRS: True`, Django also resolves `<app>/templates/**` for every `INSTALLED_APPS` entry, and none of those files would reach `test_no_hardcoded_visible_text`, `test_no_raw_get_name_in_templates`, `test_template_extraction_coverage`, `test_no_hardcoded_js_strings` or `test_title_tags_translated`. |
| **Impact** | The natural modular-Django refactor (moving a template next to its app) silently removes it from the i18n gate. Nothing detects the loss of coverage. |
| **Root Cause** | The collector predates `APP_DIRS` and was never widened. |
| **Recommendation** | Derive roots from app configs (`Path(app.path)/"templates"` for each installed app) unioned with `DIRS`, keeping `exclude_subpaths` relative to each root; add an assertion that at least one root is discovered. |
| **Effort** | S |
| **Priority** | P2 |

**Evidence — `test_i18n_completeness.py:91-100`** — the quoted collector is present verbatim.
**Evidence — `base.py:218-219`** — `"DIRS": [BASE_DIR / "backend" / "templates"]`, `"APP_DIRS": True`.
**Evidence — inventory (validator)** — no `apps/*/templates/` directory exists; the finding's inventory is accurate.

---

#### I18N-008: [MEDIUM] — `test_hreflang_present` never asserts that page templates include the partial

> **Validation Note:**
> - **Action:** CONFIRMED (unchanged)
> - **Detail:** The test renders `components/locale_head.html` in isolation and
>   asserts one `hreflang` per configured language plus the absence of
>   `x-default`. No page-template source is inspected. The docstring's claim
>   ("included by every page template") is asserted but not tested — a
>   docstring/behaviour mismatch, correctly filed. All 15 page templates do
>   include the partial today, so this is a coverage gap, not a live defect.
> - **See also:** I18N-007, I18N-005, I18N-006.

| Field | Value |
|---|---|
| **ID** | I18N-008 |
| **Type** | `BEST-PRACTICE` |
| **Category** | Test-gate completeness |
| **File(s)** | `src/backend/apps/ads/tests/test_i18n_completeness.py:568-591` |
| **Status** | Open |
| **Problem** | The test proves the partial renders correctly; it never proves any page includes it. `hreflang` is a per-page concern, so the property the test name implies is not enforced. |
| **Impact** | A new page template, or a refactor that moves the include into a base some pages do not extend, ships with no `hreflang` and no failing test. The gate reads as if the property is enforced. |
| **Root Cause** | The test was scoped to prove the partial (documented "Option B") and its name/docstring were then read as proving the site-wide property. |
| **Recommendation** | Add a source-level assertion over non-partial templates that each contains `{% include "components/locale_head.html" %}`. `unit` speed, no rendering. |
| **Effort** | S |
| **Priority** | P2 |

**Evidence — `test_i18n_completeness.py:577-591`** — the quoted test is present verbatim.
**Evidence — inventory** — 15 page templates reference `locale_head`; the
auditor's grep output (16 matches, 15 templates + the partial's own header
comment) is accurate.

---

#### I18N-009: [MEDIUM] — Language switcher gates its cookie write on consent while the server writes it unconditionally

> **Validation Note:**
> - **Action:** CONFIRMED (evidence extended)
> - **Detail:** Both writers confirmed. The auditor says the client branch is
>   "dead in practice" — more precisely it is **redundant, not dead**: it still
>   executes for consenting users, it simply duplicates a server write the
>   navigation triggers anyway. Added evidence: the client helper
>   (`language_switcher.html:60-68`) sets `SameSite=Lax`, while the server
>   `set_cookie` (`language.py:89-93`) sets no `samesite` at all — so the two
>   writers disagree on more than the consent gate, and the server's attribute-less
>   `Set-Cookie` is the one that lands last. Severity unchanged.
> - **See also:** I18N-011, I18N-012, phase 06 (consent semantics).

| Field | Value |
|---|---|
| **ID** | I18N-009 |
| **Type** | `SPEC-DEVIATION` — the consent contract is stated one way in the template and implemented another way in the middleware |
| **Category** | Consistency / coupling |
| **File(s)** | `src/backend/templates/components/language_switcher.html:99-110` (and `:60-68`), `src/backend/apps/core/middleware/language.py:87-93` |
| **Status** | Open |
| **Problem** | The switcher's JS writes `lang_pref` only inside `{% if consent_preferences %}`. The middleware writes the same cookie unconditionally in `process_response` whenever `?lang=` was supplied. Neither site references the other. |
| **Impact** | Operationally, locale persistence *appears* to depend on a consent decision that it does not; a cached pre-consent page or a future middleware change would break the switcher for non-consenting visitors with no test to catch it. For privacy, the template implies a consent-gated cookie while the server sets it for everyone. Phase 06 owns consent state; this phase flags the contradiction because the switcher is i18n behaviour. |
| **Root Cause** | One preference, two independent write paths, different gating, no shared comment. |
| **Recommendation** | Decide the contract once and write it down. Recommended: the server write is authoritative (it is the only one that runs on a plain `?lang=` link) — delete the consent-guarded JS branch and state in the middleware docstring that it sets `lang_pref`. If the consent gate is meant to be real, move it into `process_response` and coordinate with phase 06. Name `lang_pref` explicitly in the technical spec's cookie list either way. |
| **Effort** | S |
| **Priority** | P2 |

**Evidence — `language_switcher.html:99-110`** — the quoted consent-guarded block
is present verbatim; `:60-68` shows `setCookie` building
`'max-age=…','path=…','SameSite=Lax'`.
**Evidence — `language.py:87-93`** — the quoted unconditional `set_cookie` is
present verbatim, with only `max_age` supplied.

---

#### I18N-010: [MEDIUM] — Active-price filter chip interpolates raw, unformatted `Decimal` values

> **Validation Note:**
> - **Action:** CONFIRMED (unchanged; recommendation strengthened)
> - **Detail:** `ListingsQuery.active_price_range` returns
> `tuple[Decimal | None, Decimal | None]` and the chip interpolates them through
> `{% blocktrans %}`, which applies no formatting; the ad cards in the same
> response go through `|format_price`. Confirmed. The finding's recommended
> remedy — a `{% trans %}` label plus a pre-formatted value — is **already used
> fourteen lines below the defect** in the same file
> (`ad_list.html:58`: `{% trans "Purpose:" %} {{ p|get_lookup_name:LANGUAGE_CODE }}`),
> so the fix follows an existing in-file pattern rather than introducing one.
> That in-file precedent strengthens the "follow existing patterns" case and is
> added here. Note the fix must use the same helper as the cards, so it inherits
> I18N-003's `bs` grouping caveat.
> - **See also:** I18N-003.

| Field | Value |
|---|---|
| **ID** | I18N-010 |
| **Type** | `SPEC-DEVIATION` — the same document renders one price localised and one not |
| **Category** | Correctness — format localization |
| **File(s)** | `src/backend/templates/ads/partials/ad_list.html:44-53` (and the in-file precedent at `:58`), `src/backend/apps/ads/services/listings_query.py:208-220` |
| **Status** | Open |
| **Problem** | The chip renders `{% blocktrans with min=active_price_min max=active_price_max %}Price: {{ min }}–{{ max }}{% endblocktrans %}` from raw `Decimal`s. Django stringifies a `Decimal` in `{{ … }}` without `number_format`; `blocktrans` cannot apply a filter chain to a placeholder. The card price in the same response goes through `|format_price`. |
| **Impact** | The filter summary shows `1000.50` with an ASCII point and no grouping and no currency code, next to a grouped, code-suffixed card price — visibly inconsistent, and in the wrong notation for `ru` and `bs`. The gate cannot catch it: the text *is* wrapped; only the interpolation is unformatted. |
| **Root Cause** | The view exposes `Decimal`s where the template needs a formatted string, and `blocktrans` interpolation is the wrong composition tool for a formatted value. |
| **Recommendation** | Format in the view with the same helper the cards use and keep the label as `{% trans "Price:" %}` — the pattern already present at `ad_list.html:58`. Add a `unit` test rendering the chip under `override("ru")` and asserting the decimal separator. |
| **Effort** | S |
| **Priority** | P1 |

**Evidence — `ad_list.html:44-46`** — the quoted `blocktrans` chip is present verbatim.
**Evidence — `listings_query.py:208-220`** — the quoted `active_price_range` is
present verbatim.
**Evidence — NEW, the in-file precedent** (`ad_list.html:58`)
```html
{% trans "Purpose:" %} {{ p|get_lookup_name:LANGUAGE_CODE }}
```
**Evidence — both routes supply both bounds** (validator check, for completeness):
`listings.py:268` `"active_price_max": active_price_hi` and `search.py` both —
so the chip is not missing a key on either route.

---

### LOW

#### I18N-011: [LOW] — `lang_pref` cookie is emitted without `Secure`/`HttpOnly`/`SameSite`

> **Validation Note:**
> - **Action:** CONFIRMED (unchanged; cross-linked)
> - **Detail:** `response.set_cookie(LANGUAGE_COOKIE_NAME, cookie_value, max_age=…)`
>   supplies only `max_age`, so Django's defaults apply (`secure=False`,
>   `httponly=False`, `samesite=None`). `base.py:139-144` hardens session and CSRF
>   cookies, and `prod.py:216-217` re-asserts the two `SECURE` flags. The
>   language cookie is the only cookie the project issues that opts out. One
>   refinement worth carrying into the fix: the client-side writer already
>   supplies `SameSite=Lax` (I18N-009), so the two writers currently disagree and
>   the weaker one wins. The finding is also the practical enabler of I18N-001's
>   cross-site-overwrite path — that dependency is stated here so the sequencing is
>   explicit.
> - **See also:** I18N-001, I18N-009, phase 02 (general cookie policy).

| Field | Value |
|---|---|
| **ID** | I18N-011 |
| **Type** | `BEST-PRACTICE` — consistency with the project's own stated cookie policy |
| **Category** | Hardening |
| **File(s)** | `src/backend/apps/core/middleware/language.py:87-93`, `src/backend/config/settings/base.py:139-144`, `src/backend/config/settings/prod.py:216-217` |
| **Status** | Open |
| **Problem** | Only `max_age` is passed; the `secure`/`samesite`/`httponly` policy applied to every other cookie is not applied here. |
| **Impact** | Confidentiality impact is nil (a three-value language code). The consistency and integrity impact is not: on a deployment with a reachable plain-HTTP path this cookie travels in clear while the session cookie does not, and the absent `SameSite` makes it a candidate for cross-site overwrite — which, per I18N-001, is sufficient to change a visitor's rendered language. |
| **Root Cause** | The cookie policy lives in `base.py` for session/CSRF and is applied implicitly; a cookie set directly in middleware inherits nothing. |
| **Recommendation** | Pass `secure=settings.SESSION_COOKIE_SECURE`, `samesite=settings.SESSION_COOKIE_SAMESITE`, `httponly=True`. `httponly` is free once I18N-009 removes the client-side writer. Ship with or after I18N-001. |
| **Effort** | S |
| **Priority** | P2 |

**Evidence — `language.py:89-93`** — the quoted `set_cookie` is present verbatim.
**Evidence — `base.py:139-144`** — the six `SESSION_COOKIE_*` / `CSRF_COOKIE_*`
lines are present verbatim; `prod.py:216-217` sets only `SESSION_COOKIE_SECURE`
and `CSRF_COOKIE_SECURE`.

---

#### I18N-012: [LOW] — `Vary: Accept-Language` only; the documented proxy/page-cache contract does not hold

> **Validation Note:**
> - **Action:** ADJUSTED — type **`DOC-UPDATE`**, impact claim **REFUTED**,
>   severity stays LOW.
> - **Detail:** The *stated contract* is wrong and the recommendation is right,
>   but the *impact* is not reachable on full page responses. Django's
>   `CsrfViewMiddleware` adds `Vary: Cookie` on any response whose template calls
>   `get_token()`, and **every page in this project does** — `components/header.html:19`,
>   `components/consent_banner.html:41,59`, `ads/list.html:23`,
>   `components/header_catalog.html:365,606`, and others. `get_token()` sets
>   `CSRF_COOKIE_NEEDS_UPDATE`, so `process_response` calls
>   `patch_vary_headers(response, ("Cookie",))`. A shared cache that honours
>   `Vary` therefore **already** keys on the cookie, and the "may serve a Russian
>   body to a visitor whose cookie selects Bosnian" scenario cannot occur. The
>   auditor's probe observed no `Cookie` in `Vary` because it drove
>   `LanguagePreMiddleware` in isolation via `RequestFactory`, bypassing
>   `SessionMiddleware` and `CsrfViewMiddleware` — the probe measures the wrong
>   stack. The `?lang=` parameter needs no `Vary` at all: it is part of the cache
>   key as a query string. What genuinely remains: (1) the module docstring's
>   claim is factually inaccurate; (2) the property is **incidental** — it depends
>   on a CSRF side effect, so a page or HTMX fragment that renders no
>   `{% csrf_token %}` silently loses it. `ads/partials/ad_list.html` and
>   `categories/partials/mega_submenu.html` are exactly such fragments today.
>   That fragility is worth recording but is LOW, and the fix is documentation
>   plus an explicit decision, not a header change forced by a live incident.
> - **See also:** I18N-011.

| Field | Value |
|---|---|
| **ID** | I18N-012 |
| **Type** | `DOC-UPDATE` — the docstring's stated contract does not match the emitted one; the code needs no change for correctness |
| **Category** | Operability / documentation |
| **File(s)** | `src/backend/apps/core/middleware/language.py:16-19`, `:94-95` |
| **Status** | Open (re-scoped) |
| **Problem** | `process_response` calls `patch_vary_headers(response, ("Accept-Language",))` while the module docstring presents that as the complete response contract "forward-compatible with any future reverse proxy / page cache". In the real middleware stack the emitted `Vary` is in fact `Cookie, Accept-Language`, courtesy of `CsrfViewMiddleware`. |
| **Impact** | **Correctness impact: none on full page responses** — `Vary: Cookie` is present (see Validation Note), so a `Vary`-honouring cache already keys on the cookie. Residual: the docstring misdescribes the contract, and the property is an incidental side effect of CSRF rather than a declared invariant, so a future template that renders no CSRF token loses it without notice. No page cache or CDN is configured today (zero `proxy_cache`/`fastcgi_cache` in `docker/nginx/*.conf`), so nothing depends on it yet either. |
| **Root Cause** | The docstring was written describing only what the middleware itself emits, not what the stack emits. |
| **Recommendation** | Correct the docstring to state that cookie-driven locale is covered by `Vary: Cookie` via `CsrfViewMiddleware`, and note explicitly that this is incidental. When a shared cache is introduced, make the contract deliberate — `Cache-Control: private` or an explicit `Vary: Cookie` at the point a cache is added — rather than relying on the CSRF side effect. |
| **Effort** | S |
| **Priority** | P2 |

**Evidence — the middleware's own claim** (`language.py:16-19`, `:94-95`) — the
quoted text is present verbatim.
**Evidence — the mitigation the isolated probe could not see**
```python
# django/middleware/csrf.py:96-108  get_token()
    if "CSRF_COOKIE" in request.META:
        csrf_secret = request.META["CSRF_COOKIE"]
        request.META["CSRF_COOKIE_NEEDS_UPDATE"] = True
...
# django/middleware/csrf.py:268-269  _set_csrf_cookie()
    # Set the Vary header since content varies with the CSRF cookie.
    patch_vary_headers(response, ("Cookie",))
```
**Evidence — every page renders a CSRF token** (validator sweep of
`src/backend/templates`): 24 `csrf_token` occurrences across
`components/header.html:19`, `components/consent_banner.html:41,59`,
`components/header_auth_entry.html:55`, `components/favorite_heart.html:7`,
`components/header_catalog.html:365,606`, `ads/list.html:23`,
`ads/detail.html:29`, `ads/dashboard.html:28,108,118`, `ads/edit.html:28`,
`cabinet/*`, `users/login_issue.html:38`, `admin/moderation/review.html:*`.
`ads/partials/ad_list.html` and `categories/partials/mega_submenu.html` do not —
the fragility case above.

---

#### I18N-013: [LOW] — Django `verbose_name`/`help_text` are untranslated English; admin renders English in every locale

> **Validation Note:**
> - **Action:** CONFIRMED as a factual gap, **re-scoped as an OWNER DECISION** —
>   explicitly **not** a code defect. No severity change.
> - **Detail:** The underlying fact is fully reproduced and the auditor's
>   framing is the correct one: translating admin metadata versus formally
>   exempting it is a product choice, and this validation does **not** pre-decide
>   it. What the validation adds: (a) the scale is materially larger than filed —
>   the tree has **18** `verbose_name`/`verbose_name_plural` assignments and
>   **169** `help_text` assignments, and **zero** `gettext_lazy` on any of them;
>   there is not a single `gettext` import in any `models.py` in the project. The
>   auditor's "roughly 60 entries" estimate is low by ~3×. (b) Part of the scope
>   is *already* documented — `docs/99-agent/rules.md:212-213` records the
>   `admin/` **template** subtree as out of scan scope alongside
>   `feature_tag.html` and the moderation dashboard. What is genuinely unstated
>   is whether **model metadata** inherits that exclusion, which is exactly the
>   decision to be made. (c) The impact statement is correct and correctly scoped
>   as staff-only: no buyer or seller sees it.
> - **See also:** I18N-014.

**The decision that is required (not pre-empted here):**
*Option A* — declare the admin English-only by design, and extend the documented
exemption list in `docs/01-spec/i18n-spec.md` (or
`docs/99-agent/rules.md:212-213`) to name **model metadata** explicitly, so the
i18n coverage claim is accurate. Effort S.
*Option B* — wrap `verbose_name`/`help_text` in `gettext_lazy` across all models
and re-extract. Effort M; catalogue grows by ~187 entries; existing admin tests
that assert on English field text must be reviewed. Because production code is
king, such tests would be updated to the localised output, not the reverse.
*Until an owner chooses, the current state is a documentation gap, not a
violation of any written rule.*

| Field | Value |
|---|---|
| **ID** | I18N-013 |
| **Type** | Owner decision — real documentation gap, not a code defect |
| **Category** | Localization coverage |
| **File(s)** | every `src/backend/apps/*/models.py` (18 `verbose_name`, 169 `help_text`); `docs/99-agent/rules.md:212-213` |
| **Status** | Open — **awaiting owner decision** |
| **Problem** | All model `verbose_name` / `verbose_name_plural` / `help_text` values are plain English literals. `ModelAdmin` renders `verbose_name` through `capfirst()` and `help_text` verbatim, without translation. No gate inspects model metadata, and no rule states that admin-only metadata is exempt from the i18n DoD. |
| **Impact** | Staff-only: moderators and admins see English column labels and field help in every locale, while Django's own admin chrome *is* localised by Django's bundled catalogues. Inconsistent staff surface; no buyer or seller impact. |
| **Root Cause** | Model metadata was written as developer documentation, and the i18n DoD never stated whether it is in scope. |
| **Recommendation** | Owner decision — Option A or Option B above. Whichever is chosen, record it in the documented exemption list so the coverage claim is accurate. |
| **Effort** | S (Option A) / M (Option B) |
| **Priority** | P2 |

**Evidence — validator sweep** (validator counts, source of truth)
```text
  verbose_name / verbose_name_plural assignments: 18      of which gettext_lazy: 0
  help_text assignments:                           169      of which gettext_lazy: 0
  'gettext' occurrences in any src/backend/apps/*/models.py: 0
```
**Evidence — samples present verbatim** — `apps/ads/models.py:52`
(`help_text="Ad title in Russian (translated from seller input)"`),
`apps/categories/models.py:44` (`help_text="Parent category for tree structure"`),
`apps/core/models.py` `verbose_name = "Site Config"`.
**Evidence — the partial existing exemption** (`docs/99-agent/rules.md:212-213`)
```text
- DB-based i18n (`components/feature_tag.html` via `get_lookup_name`) is exempt from the completeness gate
- Scan scope excludes `admin/` staff templates, `analytics/moderation_dashboard.html`, and `components/feature_tag.html`
```

---

#### I18N-014: [LOW] — Six orphaned msgids left in all three catalogues; no gate detects stale entries

> **Validation Note:**
> - **Action:** CONFIRMED, with a verification note on method
> - **Detail:** All six msgids independently confirmed present in every
>   working-tree catalogue (`ru`/`bs`/`en`) and confirmed absent from the
>   extracted source set; the `--no-obsolete` omission is confirmed in two
>   places. One methodological note for whoever re-checks this: **the sixth
>   msgid is wrapped across multiple lines** in all three `.po` files, so a
>   `^msgid "<text>"$` regex silently misses it. A validator's first pass
>   reported "0 occurrences"; only a loose search found it. A stale-entry gate
>   built on a line-anchored regex would therefore inherit the same blind spot
>   and must parse, not regex. The auditor's `--no-obsolete` recommendation is
>   correct but incomplete on its own — pruning once is a one-shot cleanup; the
>   durable fix is the gate, and it should reuse a plural-aware parser, so
>   sequence it after I18N-005.
> - **See also:** I18N-005, I18N-006.

| Field | Value |
|---|---|
| **ID** | I18N-014 |
| **Type** | `BEST-PRACTICE` — catalogue hygiene |
| **Category** | Catalog hygiene |
| **File(s)** | `src/backend/locale/{ru,bs,en}/LC_MESSAGES/django.po`, `src/telegram_bot/lifecycle.py:36-55`, `Makefile:189`, `.kilo/rules/commands.md:89` |
| **Status** | Open |
| **Problem** | Six msgids remain in all three catalogues but are no longer extracted: `Start`, `Language`, `Post ad`, `Alerts` (superseded by the per-language `_COMMANDS` literals in `lifecycle.py`) and `Please login first.` + `Cannot approve: the ad owner has reached the maximum number of active ads.` (reworded). `makemessages` without `--no-obsolete` marks entries `#~` rather than removing them, and no gate compares the catalogue against the source in the "removed" direction. |
| **Impact** | Runtime impact nil. Dead entries accumulate silently: translators spend time on strings that will never render, and a reviewer grepping a `.po` for a string can be misled into believing a code path is translated. |
| **Root Cause** | The documented extraction omits `--no-obsolete`, and `test_extraction_completeness` only checks the "added" direction. |
| **Recommendation** | Add `--no-obsolete` to the documented invocation (`Makefile:189`, `.kilo/rules/commands.md:89`) and run once. Then add a gate asserting the catalogue has no entry absent from the source, using a **parsed** (not regex) msgid set and the documented exemptions for the four command-menu strings. Sequence after I18N-005. |
| **Effort** | S |
| **Priority** | P2 |

**Evidence — validator verification of all six** (working-tree `.po`; source set
from `grep` over `src/**/*.{py,html}`)
```text
  'Start'    present in 3/3 catalogues; source: only BotCommand/other non-msgid uses -> orphan
  'Language' present in 3/3 catalogues -> orphan
  'Post ad'  present in 3/3 catalogues; source: lifecycle.py:52 (BotCommand literal, not a gettext msgid) -> orphan
  'Alerts'   present in 3/3 catalogues -> orphan
  'Please login first.'                                            present in 3/3; 0 source hits -> orphan
  'Cannot approve: the ad owner has reached the maximum number of active ads.'
        ru/django.po:530, bs/django.po:520, en/django.po:449 — present in 3/3, as a WRAPPED multi-line msgid;
        0 source hits -> orphan
```
**Evidence — `--no-obsolete` omission** — `Makefile:189` and
`.kilo/rules/commands.md:89` both invoke
`makemessages -l ru -l bs -l en --no-location`, with no `--no-obsolete`.
**Evidence — the "added" direction is the only one gated** —
`test_i18n_completeness.py:406-425` computes `all_msgids - msgids` (missing from
this locale); there is no reverse assertion.
**Evidence — catalogues untouched by this validation** —
`git status --porcelain -- src/backend/locale` is empty.

---

#### I18N-015: [LOW] — `Accept-Language` q-values are ignored, so a supported lower-ranked tag is skipped

> **Validation Note:**
> - **Action:** CONFIRMED (unchanged)
> - **Detail:** Reproduced exactly. `_parse_accept_language` takes
>   `accept_language.split(",")[0]` and returns the `bs` fallback immediately when
>   that one tag is unsupported, without scanning the rest of the list. The
>   filed evidence value `de-DE,ru;q=0.8,bs;q=0.6 → 'bs'` is reproduced. The
>   finding correctly self-identifies as a spec-level trade-off rather than a
>   bug, and correctly notes the spec is silent on q-values
>   (`docs/01-spec/i18n-spec.md:63-64`). The LOW rating and the "specify the rule
>   either way" framing are both right; no adjustment.
> - **See also:** I18N-001 (same module, same `LanguageLocale.from_code` seam).

| Field | Value |
|---|---|
| **ID** | I18N-015 |
| **Type** | `BEST-PRACTICE` / spec gap |
| **Category** | Correctness — runtime locale resolution |
| **File(s)** | `src/backend/apps/core/middleware/language.py:144-160` |
| **Status** | Open |
| **Problem** | Only the first tag is examined. `Accept-Language: de-DE,ru;q=0.8,bs;q=0.6` — the shape Chrome sends for a German UI with Russian and Bosnian secondary preferences — resolves to `bs`, even though `ru` is a configured locale the user ranked above Bosnian. |
| **Impact** | Users with an unsupported primary UI language and a supported secondary one land on the wrong default. The behaviour is documented as intentional for the fallback; only the q-value rule is unspecified. |
| **Root Cause** | The RFC 9110 preference list is parsed positionally rather than by descending `q` with a supported-code scan. |
| **Recommendation** | Parse `(tag, q)` pairs, drop `q=0`, sort descending, return the first tag that maps to a configured locale, and only then fall back. Update `docs/01-spec/i18n-spec.md:63-64` to state the rule either way. Implement alongside I18N-001 — same function, one shared resolver. |
| **Effort** | S |
| **Priority** | P2 |

**Evidence — `language.py:153-160`** — the quoted block is present verbatim.
**Evidence — validator probe**
```text
AL='en-US,en;q=0.9'            -> 'en'  chrome='All categories'      (normalises correctly)
AL='de-DE,ru;q=0.8,bs;q=0.6'   -> 'bs'  chrome='Sve kategorije'      (ranked-above 'ru' skipped)
AL='fr'                        -> 'bs'  chrome='Sve kategorije'
AL='bs,ru;q=0.9'               -> 'bs'  chrome='Sve kategorije'
```

---

## Validation-Level Findings (Phase 99)

### VAL-001: [CRITICAL] — Cross-phase conflict: phase 02 CFG-008 is correct, phase-14 Appendix D is not

> **Validation Note:** Recorded per §6/§10. Full evidence in
> "Cross-Phase Reconciliation §1" above. Summary:
> `RUN_TRANSLATION_BACKFILL` **is** consumed, at
> `src/backend/apps/core/utils/migrate_locked.py:57`, where it conditionally
> appends the `backfill_translations` step to the bootstrap sequence. Phase 14's
> Appendix D established only that no management command *named*
> `RunTranslationBackfill` exists — a different question from whether the
> variable is read, and an answer that reads as exonerating. **CFG-008 stands.**
> Required action: rewrite the Appendix D bullet; do not close CFG-008.

### VAL-002: [MEDIUM] — Coverage gap: the phase-08 deferred `sanitize_query_for_log` classification was never performed by phase 14

> **Validation Note:** Recorded per §6. Full evidence in "Cross-Phase
> Reconciliation §2". Phase 08 deferred this explicitly
> (`99-validation/08-search-fts-validated-findings.md:291-296, :1095`); phase 14
> contains no reference to the function. **Resolved here as STALE:** the current
> `sanitize_query_for_log` (`apps/core/utils/sanitize.py:108-124`) contains no
> `isalpha()` logic — it strips only control characters and truncates, so
> Cyrillic, Serbian Latin diacritics and digits all survive. No new source
> finding is raised. Residual actions: close the phase-08 deferral explicitly, and
> correct the phase-08 advisory text, which still describes removed behaviour.

### VAL-003: [LOW — advisory] — The wrong-language symptom differs between production and test settings, and the auditor's evidence was gathered only under test settings

> **Validation Note:** Methodology correction that affects how I18N-001 should be
> tested and fixed. Django's `DjangoTranslation._add_fallback`
> (`trans_real.py:235-250`) adds `settings.LANGUAGE_CODE` as a catalogue fallback
> for any activated language that is not `en*`. `config.settings.base` sets
> `LANGUAGE_CODE = "ru"`; `config.settings.test` overrides it to `"en"`. So the
> *gettext chrome* for an unsupported locale is **Russian in production** and
> **English under test** for the identical request. Any regression test for
> I18N-001 written only under the test settings would therefore assert English
> chrome while production renders Russian — the test would pass and production
> would still be wrong. Such a test must assert on the **DB-accessor** result
> (which is default-independent) and must not assert on chrome text for an
> unsupported locale, or must pin `LANGUAGE_CODE` explicitly.

### VAL-004: [LOW — advisory] — Number-format grouping is structurally unavailable for `bs`; a `Decimal`-only fix is insufficient

> **Validation Note:** Discovered while validating I18N-003; folded into that
> finding's recommendation rather than raised as a separate code defect, because
> the root cause and the fix site are the same. Django's bundled
> `conf/locale/bs/formats.py` leaves `NUMBER_GROUPING` undefined (commented out),
> and `django/utils/numberformat.py:34` applies
> `use_grouping = use_grouping and grouping != 0` — which hard-disables grouping
> for `bs` **even under `force_grouping=True`**. Measured:
> `number_format(Decimal("1000000"), use_l10n=True, force_grouping=True)` →
> `'1000000'` for `bs`, `'1\xa0000\xa0000'` for `ru`, `'1,000,000'` for `en`.
> Any remediation of I18N-003 must include an explicit `bs` grouping decision, or
> `bs` users will keep reading `1000000 EUR` while `ru` users read `1 000 000`.

---

## Rollout Safety

| ID | Risk | Backward-compatible? | Ordering constraint | Test gap (must cover) |
|---|---|---|---|---|
| I18N-001 | Low | Yes — canonical values behave identically | **First.** I18N-011 and I18N-002 are weaker without it. | New: `lang_pref` = `en-US`/`EN`/`en_US`/`xx`/`de-DE` must resolve to a configured locale **and** render that locale's names, not `ru`. Assert on accessors, not chrome (see `VAL-003`). |
| I18N-003 | Low | Yes for `en`; changes rendered price strings for `ru`/`bs` | Independent of I18N-001. Include the `bs` grouping decision (`VAL-004`) in the same change. | Update `test_format_price_value_uses_intcomma` to assert exact `ru`/`bs` output; add a fractional case **and** a ≥7-digit case. |
| I18N-004 | **Med** | No — every rendered timestamp shifts | Independent. | New: assert `settings.TIME_ZONE`; assert a known UTC instant renders to the expected local time; assert the two `datetime="…"` ISO attributes are unchanged. |
| I18N-002 | Low | Yes | **After I18N-001** — otherwise there is nothing to fix. | Covered by I18N-001's fix; optionally assert the cache-key locale ∈ {`ru`,`bs`,`en`}. |
| I18N-010 | Low | Yes | After I18N-003, so the chip uses the corrected helper. | New: render the chip under `override("ru")` and assert the decimal separator. |
| I18N-005 | Low | Yes | **Before I18N-014** — a credible stale-entry gate needs a plural-aware parser. | New: parser unit test with a blank `msgstr[0]` must be reported. |
| I18N-006 | Med | Yes, if the four `lifecycle.py` literals are exempted as documented | With I18N-005/007/008 in one pass (shared collector work). | New: the widened gate must pass on the current tree; add a `retry.py`/`states.py` case. |
| I18N-007 | Low | Yes | Same pass as I18N-006. | New: assert the collector finds at least one app-level root once one exists. |
| I18N-008 | Low | Yes | Same pass. | New: the include assertion must hold for all 15 page templates. |
| I18N-009 | Med | Yes (the server write is already authoritative) | Coordinate the consent half with phase 06. | New: `?lang=bs` still sets `lang_pref` with no consent context; the JS no longer contains the gate. |
| I18N-011 | Low | Yes | With or after I18N-009 (so `httponly=True` is safe). | New: assert `secure`/`samesite`/`httponly` on the emitted cookie. |
| I18N-012 | Low | Yes | Documentation only. | Header assertion documenting that `Vary` includes `Cookie` in the full stack. |
| I18N-013 | Med (Option B) | No — admin labels change | **Owner decision first.** | Option A: assert the exemption is documented. Option B: existing admin tests must tolerate localised labels. |
| I18N-014 | Low | Yes | **After I18N-005.** | New: stale-entry assertion using a **parsed** msgid set (see the method note — the sixth orphan is a wrapped multi-line msgid). |
| I18N-015 | Med | Yes for single-tag headers | Same change as I18N-001 — one shared resolver. | Add a q-valued-header case to the middleware table. |

**No circular dependencies.** The only ordering chains are linear and
non-blocking: I18N-001 → {I18N-002, I18N-011, I18N-015}; I18N-003 → I18N-010;
I18N-005 → I18N-014; I18N-006/007/008 in one pass. No hidden dependency chain was
found beyond these. No rollout-safety blocker was detected that requires a new
finding.

---

## Validation Summary

| Action | Count | Details |
|---|---|---|
| Validated (unchanged) | 12 | I18N-003, I18N-005, I18N-006, I18N-007, I18N-008, I18N-009, I18N-010, I18N-011, I18N-013, I18N-014, I18N-015, and I18N-001 (HIGH retained, evidence corrected) |
| Reclassified (type) | 1 | I18N-012 → `DOC-UPDATE` |
| Re-scoped (owner decision) | 1 | I18N-013 |
| Severity-adjusted | 2 | I18N-004 HIGH→MEDIUM, I18N-002 MEDIUM→LOW |
| Merged | 0 | — |
| Rejected | 0 | — |
| VAL- (cross-phase / coverage / advisory) | 4 | VAL-001 (CRITICAL), VAL-002 (MEDIUM), VAL-003 (LOW), VAL-004 (LOW) |

### Rejected Findings

None. No finding failed independent reproduction. The two findings whose *impact*
claims did not survive (I18N-001's "chrome stays in the selected language" and
its `EN` row; I18N-012's cache-bleed scenario) were **adjusted**, not rejected,
because the underlying defect is real in both cases.

### Merged Findings

None. `VAL-004` is folded into I18N-003's recommendation rather than raised
separately (same root cause, same fix site). I18N-002 is *subsumed* by I18N-001
but retained rather than merged, because its remediation site differs
(defence-in-depth at the key-building site) and the handbook §7 "complement" case
applies.

### Reclassified Findings

| ID | Original type | New type | Rationale |
|---|---|---|---|
| I18N-001 | Correctness / i18n runtime | `SPEC-DEVIATION` | `docs/01-spec/i18n-spec.md:63` states unconditionally that the resolved code is normalised by `LanguageLocale.from_code()`; the cookie branch does not normalise. The code violates a documented contract, not just an internal expectation. |
| I18N-002 | Operability / i18n runtime | `BEST-PRACTICE` | What survives after I18N-001 subsumes the mechanism is defence-in-depth, not an independent operability defect. |
| I18N-003 | Correctness / format localization | `SPEC-DEVIATION` | The project's own test docstring (`test_price_format.py:24-28`) asserts locale-aware grouping that the code does not deliver. |
| I18N-004 | Correctness / format localization | `SPEC-DEVIATION` | Operating region is Montenegro/Bosnia; `America/Chicago` and en-US date order are not neutral defaults. |
| I18N-012 | Operability | `DOC-UPDATE` | The emitted contract is already correct on full page responses via `CsrfViewMiddleware`; only the docstring's description of it is wrong. |
| I18N-013 | Localization coverage | Owner decision | Real documentation gap; the remedy is a product choice, not a code change. |

---

## Validator Evidence Index

All probes were validator-authored, read-only, run against the local venv
(`RequestFactory` + `translation` + unsaved model instances, **no database
access**, no `.po`/`.mo` write). Probe scripts under `.ai/tmp/` were deleted after
the run; `git status --porcelain` reports **no modified tracked file**, and
`git status --porcelain -- src/backend/locale` is empty.

| # | Check | Result |
|---|---|---|
| V-01 | Mitigation sweep for I18N-001: `LocaleMiddleware` in `MIDDLEWARE`, `set_language` view, `i18n_patterns`, any second `translation.activate` call site | All **absent** — no mitigation exists |
| V-02 | `trans_real.py:296-303` `activate()` — consults `settings.LANGUAGES`? normalises? | **Neither** |
| V-03 | Middleware × 10 cookie values, prod-like `LANGUAGE_CODE="ru"`, `request.LANGUAGE_CODE` + chrome + `Category.get_name` | I18N-001 mechanism confirmed; 2 auditor rows corrected |
| V-04 | `DjangoTranslation._fallback` per locale | Confirms the prod-vs-test chrome divergence (`VAL-003`) |
| V-05 | `format_price_value` × 6 amounts × 3 locales; `intcomma` str-vs-`Decimal`; `DECIMAL_SEPARATOR`/`THOUSAND_SEPARATOR`/`NUMBER_GROUPING` | I18N-003 both halves confirmed; separators confirmed (`ru` U+00A0 + `,`; `bs` `.` + `,`) |
| V-06 | `number_format(1e6, force_grouping=True)` × 3 locales + `numberformat.py:34` | `bs` grouping structurally unavailable (`VAL-004`) |
| V-07 | `settings.TIME_ZONE`, `settings.USE_TZ`, `global_settings.USE_TZ`, `localtime`, 4 date patterns × 3 locales | I18N-004 facts confirmed; `USE_TZ=True`; ISO `datetime` attrs identified as must-not-touch |
| V-08 | Exhaustive `\|date:` sweep of `src/backend/templates` | 6 hits: 4 defective + 2 correct ISO attributes — the finding's inventory is complete |
| V-09 | `_parse_po_entries` on a synthetic plural entry with blank `msgstr[0]` | I18N-005 blind spot confirmed |
| V-10 | Real-catalogue plural scan, all 3 locales | 0 empty forms in `ru`/`bs` → I18N-005 is latent, as filed |
| V-11 | Gate run: `test_i18n_completeness.py` + `test_i18n_pipeline.py` + `test_i18n_category_city.py` + `test_price_format.py` + `test_language_middleware.py` | **55 tests, all passing** — the DoD gate is green today, so every gate finding is a coverage gap, not a live failure |
| V-12 | `RUN_TRANSLATION_BACKFILL` / `RunTranslationBackfill` / `run_translation_backfill` — 3-spelling repo-wide search (61 hits) + full `management/commands` inventory (33 commands) | Consumed at `migrate_locked.py:57`; no such command exists → **CFG-008 correct, Appendix D wrong** (`VAL-001`) |
| V-13 | `sanitize_query_for_log` current source + `isalpha\|isalnum\|isdigit` sweep | No `isalpha()` anywhere → the phase-08 deferral is **stale** (`VAL-002`) |
| V-14 | `verbose_name` / `help_text` / `gettext` counts across all `models.py` | 18 + 169, zero `gettext_lazy`, zero gettext imports (`VAL`-scope for I18N-013) |
| V-15 | Orphan-msgid verification: loose + line-anchored search in all 3 catalogues and across `src/**` | All 6 confirmed; the 6th is a **wrapped multi-line** msgid — a method note for the future gate |
| V-16 | `csrf_token` sweep of all templates + `csrf.py:96-108, 268-269` | `Vary: Cookie` is emitted on every full page → I18N-012's impact refuted |
| V-17 | `\|date:`-adjacent: `proxy_cache`/`fastcgi_cache` in `docker/nginx/*.conf`; rate-limit settings in `config/settings/*.py` | Zero cache directives (confirms I18N-012's "no impact today"); zero rate-limit middleware (I18N-002 context) |
| V-18 | Template-context key diff: `listings.py` vs `search.py`; `active_price_max` presence in both | Overlap confirmed (phase 10's CQ-015); both bounds supplied on both routes; no untranslated-key hiding place — phase-14 gate covers the shared partial |
