# Specification: Fix 3-Language Ad-Text Switching (ru / bs / en)

**File:** `08_seed-language-switching_spec.md`
**Status:** Final (ready for implementation planning)
**Date:** 2026-08-08
**Source Decision:** `.ai/problems/Decision_09.md` (ru/bs/en ad-text switching broken; skip translation API; use seed examples)
**Research:** `ses_01fa38721ffemMe0of6rRTdly9` (root-cause + cookie-name mismatch + middleware clobber confirmed; Approaches A–D evaluated)
**Related:** Decision_09, `docs/01-spec/technical-specification.md` §G, `docs/spec-index.md`, `03_seed-content-fixtures_spec.md` (§5.5), `AGENTS.md` (StrEnum rule, no `print`, migrations for schema)

---

## 1. Problem Statement

Per Decision_09, switching the site language (Russian / Bosnian-Latin / English) must change **ad text** (title + description); it currently does not. The seed fixtures and generator already produce per-language content, so this is framed as **ad-content display only** — no translation API is introduced (Decision_09: "функционал сохраняем, но шаг пропускаем").

**Reframed problem (research-verified):** The translated content already exists and is correct. The break is purely **in the request pipeline that resolves `request.LANGUAGE_CODE`** — the value that flows from the context processor into `{{ ad|get_title:LANGUAGE_CODE }}` / `{{ ad|get_description:LANGUAGE_CODE }}` and selects the DB column (`title_en` / `title_bs` / `title`).

### Root cause (confirmed end-to-end)

`MIDDLEWARE` order in `src/backend/config/settings/base.py:107-118`:
```
114  apps.core.middleware.language.LanguagePreMiddleware   (custom authority)
115  django.middleware.locale.LocaleMiddleware              (built-in OVERRIDER)
```
`process_request` runs top-to-bottom, so `LocaleMiddleware` runs **after** the custom middleware.

1. `LanguagePreMiddleware.process_request` (`apps/core/middleware/language.py:39-56`) computes the intended locale with priority `?lang=X` > `lang_pref` cookie > `Accept-Language` > `ru`, and sets `request.LANGUAGE_CODE = lang` (line 99). At this point the value is **correct** (e.g. `"en"`).

2. `LocaleMiddleware.process_request` (`.venv/Lib/site-packages/django/middleware/locale.py:19-36`) runs immediately after and **overwrites** it:
   ```python
   25  language = translation.get_language_from_request(request, check_path=i18n_patterns_used)
   35  translation.activate(language)
   36  request.LANGUAGE_CODE = translation.get_language()      # ← CLOBBER
   ```

3. `get_language_from_request` (`trans_real.py:559-603`) resolves language from:
   - **path** — `check_path=False` (no `i18n_patterns` in `config/urls.py:8`; verified no `i18n_patterns`/`set_language` repo-wide);
   - **cookie** `request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME)` (line 574) — defaults to `"django_language"` (Django `global_settings.py:164`); the project **never** sets `settings.LANGUAGE_COOKIE_NAME`, and the custom middleware writes/reads its OWN constant `"lang_pref"` (`language.py:20`) — a **cookie-name mismatch**; the `django_language` cookie is never set anywhere (no `set_language` view);
   - **Accept-Language header** (line 587) — browser default, e.g. `ru`;
   - `settings.LANGUAGE_CODE` = `"ru"` (line 55) as ultimate fallback (line 600).

   It does **not** read the `?lang=X` query parameter, and does **not** read the session. So `LocaleMiddleware` always re-derives from `django_language`(absent) → `Accept-Language` → `ru`, **ignoring** the `lang_pref` cookie and the `?lang=` parameter.

**Net effect:** `request.LANGUAGE_CODE` is always reset to `ru` (or the browser `Accept-Language` default), **regardless** of the user's choice. The context processor (`apps/core/context_processors.py:18-20`) exposes this clobbered value; `{{ ad|get_title:LANGUAGE_CODE }}` → `Ad.get_title("ru")` → `title` (Russian column). Ad text therefore never switches. The `lang_pref` cookie is persisted correctly in `process_response` (`language.py:58-71`), but it is never read back by `LocaleMiddleware`.

**Why tests miss it:** `test_language_middleware.py` instantiates `LanguagePreMiddleware` directly and calls `process_request`/`process_response` **without** `LocaleMiddleware` in the chain (isolation gap). `test_context_processors.py` hand-injects `request.LANGUAGE_CODE`. The clobber is a *composition* fault, invisible to both.

**Important non-cause (seed content is fine):** 351 seed templates (`apps/seed/fixtures/ads_templates.json`) carry ru/en/bs `patterns`. `AdGenerator` (`apps/seed/generators/ads.py:436-455`) populates all six columns (`title`, `title_en`, `title_bs`, `description`, `description_en`, `description_bs`) — verified by `test_seed.py:705-850`. The `Ad` model (`ads/models.py:42-70`) has **no** `title_ru`/`description_ru` column; `title`/`description` ARE the Russian base (docstrings lines 44, 59). So the "missing translated examples" premise in the task is **incorrect** — the data layer is complete; only the resolver is broken.

**Important non-cause (i18n gettext is dormant):** No `.mo` files exist under any `locale/` dir (only `.po` with empty `msgstr`); the project never imports `gettext`/`translation.activate` (`grep` = 0). So `{% trans %}` is a literal no-op and `LocaleMiddleware`'s `translation.activate()` has **zero** UI effect today — ad-content is the *only* language-driven rendering path, and that is exactly what gets clobbered.

---

## 2. Confirmed Requirements, Facts, Assumptions, Open Questions

### Facts (verified)
- F1. Three locales: `ru`, `bs` (Bosnian-Latin), `en` — `apps/core/enums.py:159-164` (`LanguageLocale.StrEnum`).
- F2. Ad content lives in DB columns: `title`, `title_en`, `title_bs`, `description`, `description_en`, `description_bs`; `title`/`description` = Russian base. (`ads/models.py:42-70`)
- F3. Seed ads already carry ru/en/bs content; `AdGenerator` writes all 6 columns. (`ads/generators/ads.py:436-455`; `test_seed.py:705-850`)
- F4. `request.LANGUAGE_CODE` is the sole signal driving ad content: context processor (`context_processors.py:18-20`) → `get_title`/`get_description` filter (`localized_content.py:18-49`) → `Ad.get_title`/`Ad.get_description` (`ads/models.py:366-381`).
- F5. Listings (`templates/ads/partials/ad_list.html:32,44,51`) and detail (`templates/ads/detail.html:13,37,47,55`) both read `LANGUAGE_CODE`; the fix is therefore **global**, not page-specific.
- F6. `LocaleMiddleware` is dormant/detrimental: no `i18n_patterns`, no `set_language` view, no `LANGUAGE_COOKIE_NAME` override, no `.mo`. Removing it loses nothing that exists.
- F7. The language switcher (`templates/components/language_switcher.html:40,56-116`) navigates via `?lang=X` and sets `lang_pref` via JS synchronously before navigation; uses `{% get_current_language %}` (needs thread-local `translation.get_language()`) and `{% get_available_languages %}` (reads `settings.LANGUAGES`, middleware-independent).

### Confirmed requirements
- **CR1 — Resolve correctly.** `request.LANGUAGE_CODE` must equal the user's chosen locale at the point the view renders, per priority `?lang=X` > `lang_pref` cookie > `Accept-Language` (first supported tag) > `ru`. Must honor `?lang=` even on the **first** click before any cookie is set.
- **CR2 — Ad content switches.** On `?lang=en` (or `lang_pref=en` cookie) a seed ad renders `title_en` / `description_en`; `?lang=bs` renders `title_bs` / `description_bs`; default renders Russian `title` / `description`. Applies to both ad detail and listing card snippets (F5).
- **CR3 — Persistence.** Language preference persists across revisits/anonymous sessions via the `lang_pref` cookie (1 year). Existing cookie name/semantics preserved (no client-side migration possible; server overwrites).
- **CR4 — Switcher reflects current.** The language-switcher button shows the active language (`{{ LANGUAGE_CODE|upper }}` and `{% get_current_language %}` highlight); requires `translation.activate()` to be called with the chosen locale.
- **CR5 — No translation API.** Out of scope: per Decision_09, no translation service, no `.mo` compilation, no static-UI string translation. Static UI strings (`{% trans "Photo" %}` etc.) may remain English; that is acceptable and unchanged.
- **CR6 — Safe fallback for partial translations.** When a locale column is NULL/empty, `get_title`/`get_description` fall back to the Russian base (`title`/`description`), then to the first non-empty (current behavior via `getattr` default).
- **CR7 — Testable.** The fix must be covered by an integration test exercising the **real middleware chain** + view + template + a published seed Ad (the composition-level test that isolation tests cannot provide).

### Assumptions
- **A1.** "Montenegrin/Bosnian" = the single `bs` locale (Bosnian-Latin script) already in `LanguageLocale`; no separate `cnr`/Cyrillic locale is introduced. *(Unlikely to change; flagged in Q2.)*
- **A2.** Authenticated-seller language preference does **not** require a DB-backed `user.profile.language`; cookie + session (`django_language` key, line 95) is sufficient because the buyer-facing ad-browsing surface (the thing that renders ad content) is anonymous.
- **A3.** `Content-Language` and `Vary: Accept-Language` response headers are **cosmetic/SEO hygiene**, not functional — no shared HTTP cache/CDN is configured in dev; production caching, if any, is PgBouncer/Postgres (per zone C5 `prepare_threshold`), not reverse-proxy page caching. Still set them (CR4/CR8) for correctness.

### Open questions for the Product Owner
- **Q1 (scope surface):** Confirm the requirement is **ad content only** (title/description) and that static UI strings staying in English is acceptable. *(Decision_09 implies yes; recorded for explicit sign-off.)*
- **Q2 (locale identity):** Confirm `bs` = Bosnian-Latin and that no Montenegrin (`cnr`) locale is desired. *(Default: yes.)*
- **Q3 (authed persistence):** Confirm a `user.profile.language` column is **not** required (cookie-only is acceptable for sellers). *(Default: not required; sellers authenticate into the bot, buyers are anonymous.)*
- **Q4 (Task 3 inclusion):** Decide whether to include the `title_ru`/`description_ru` dead-column cleanup (§5) in this change or as a follow-up. *(Default: include — it is safe and removes latent confusion.)*

---

## 3. Conceptual Development Tasks

Independent tasks; Tasks 1 and 2 are coupled (fix + regression guard) and must ship together; Task 3 is independent cleanup.

### Task 1 — Make `LanguagePreMiddleware` the single language authority (fixes root cause)
**Purpose:** Eliminate the `LocaleMiddleware` clobber so the chosen locale reaches `request.LANGUAGE_CODE` → context processor → `get_title`/`get_description`.

**Changes:**
- **`src/backend/config/settings/base.py` MIDDLEWARE (lines 107-118):** remove line 115 `"django.middleware.locale.LocaleMiddleware"`. Rationale: it is dormant (F6) and actively harmful (the clobber). The custom middleware already implements the team's chosen priority and persistence; it must simply own the thread-local too.
- **`src/backend/apps/core/middleware/language.py`:**
  - In `process_request`, after `lang` is determined (and before/instead of only `_set_language_code`), call `django.utils.translation.activate(lang)` **and** set `request.LANGUAGE_CODE = translation.get_language()` (so the thread-local and the request attr agree). This is required for `{% get_current_language %}` (`language_switcher.html:34`) and `{{ LANGUAGE_CODE }}` (`language_switcher.html:23`) to reflect the active locale.
  - In `process_response`, replicate `LocaleMiddleware`'s header contract (`.venv/.../locale.py:77-79`): `patch_vary_headers(response, ("Accept-Language",))` and `response.headers.setdefault("Content-Language", lang)`. This preserves `Vary` for any future reverse proxy and the `Content-Language` hygiene header.
  - Keep existing `lang_pref` cookie persistence (lines 58-71) and session write for authenticated users (lines 90-95) — unchanged.
- **Out of scope:** no `LANGUAGE_COOKIE_NAME` change (cookie stays `lang_pref`); no `i18n_patterns`; no `.mo`.

**Why not Approach A (align cookie name)?** Approach A (`settings.LANGUAGE_COOKIE_NAME = "lang_pref"`) fixes the steady-state return-visitor case but **not** the first `?lang=` click: `LocaleMiddleware` still ignores the query param and the `lang_pref` cookie is only set in `process_response` (after all `process_request`), so the navigating request still falls to `Accept-Language`. Approach B honors `?lang=` on every request by the team's chosen priority. Recommendation (see §4): **B**.

### Task 2 — Add an integration ("end-to-end") regression test for the full middleware chain
**Purpose:** The bug is a **composition** fault; isolation unit tests cannot catch it. A single test asserting `?lang=en` renders the English DB column through the real stack would have prevented this regression.

**New file:** `src/backend/apps/core/tests/test_language_end_to_end.py` (uses `django.test.TestCase` — needs a DB row).

**Setup:** create and `publish` a minimal `Ad` with: `title="Русско заголовок"`, `title_en="English title"`, `title_bs="Bosnian naslov"`, `description="Русское описание"`, `description_en="English desc"`, `description_bs="Bosnian opis"`, plus required FKs (`user`, `category`, `city`) and `category_name`.

**Assertions (real `Client`, real `MIDDLEWARE`):**
| Scenario | Request | Expected rendered content |
|---|---|---|
| First-click en vs ru-Acc-Lang | `GET /ad/<id>?lang=en`, `HTTP_ACCEPT_LANGUAGE="ru"` | `title_en` ("English title") |
| Cookie, no param | `GET /ad/<id>`, cookie `lang_pref=en` | `title_en` |
| bs param | `GET /ad/<id>?lang=bs` | `title_bs` ("Bosnian naslov") |
| Default (no signal) | `GET /ad/<id>` (Acc-Lang absent or non-matching) | Russian `title` |
| Invalid lang | `GET /ad/<id>?lang=fr` | Russian `title`; response does not persist `fr` |
| Listing snippet | `GET /` (list view) with `?lang=en` + `lang_pref=en` | card shows `title_en` (F5) |
| Headers | after `?lang=en` | `Vary` contains `Accept-Language`; `Content-Language: en` |
| Thread-local ↔ request-attr consistency | any `?lang=X` request | `translation.get_language()` (thread-local active language) == `request.LANGUAGE_CODE` == chosen `X` |

> Exact URL paths for ad detail and home depend on `apps/ads/urls.py` + `apps/core/urls.py`; the test author binds the concrete path. The seed Ad can be built via the existing `AdFactory`/`SeedAd` helpers or a direct ORM fixture; reuse whichever the project uses for `test_seed.py` DB tests.

**Validator note (thread-local contract):** Two resolution paths drive language-sensitive rendering — `{{ LANGUAGE_CODE }}` (built-in `i18n` context processor reads `translation.get_language()` thread-local, then the custom `language` context processor overrides it with `request.LANGUAGE_CODE`) and `{% get_current_language %}` (reads the thread-local directly). Removing `LocaleMiddleware` therefore requires `LanguagePreMiddleware` to set **both** `translation.activate(lang)` and `request.LANGUAGE_CODE` to the same value; diverging one without the other desyncs the switcher highlight from the rendered content. The new integration test asserts `translation.get_language()` == `request.LANGUAGE_CODE` per scenario, and an equivalent unit assertion should be added to `test_language_middleware.py` so the divergence is caught at unit level too.

### Task 3 — Clean up the `title_ru`/`description_ru` dead-column reference (latent, not the root cause)
**Purpose:** Remove misleading fallback references that cannot match any DB column, so the fallback is explicit and the model/test agree with the schema.

**Analysis:** `Ad.get_title` (`ads/models.py:366-373`) iterates `[f"title_{locale}", "title_ru", "title"]`; `get_description` (`:375-381`) iterates `[f"description_{locale}", "description_ru", "description"]`. There is **no** `title_ru`/`description_ru` column (F2) — the Russian base is `title`/`description`. `getattr(self, "title_ru", None)` silently returns `None`, so Russian falls through to `title` **by accident**. `test_ad_localization.py:50-96` sets phantom `title_ru`/`description_ru` attributes on an in-memory `Ad.__new__` object (`_make_ad`), asserting they're read — behavior the DB can never produce. This is the latent inconsistency called "Assumption A8" in `03_seed-content-fixtures_spec.md` §5.5 and is **incorrect** (there is no `title_ru` column).

**Changes (optional, PO Q4):**
- `ads/models.py` `get_title`/`get_description`: change the fallback lists to `[f"title_{locale}", "title"]` and `[f"description_{locale}", "description"]` (drop the dead `"title_ru"`/`"description_ru"` middle element). Functionally identical on real rows (Russian is `title`); makes intent explicit.
- `apps/ads/tests/test_ad_localization.py`: replace phantom `title_ru=`/`description_ru=` kwargs with real `title=`/`description=` kwargs (Russian base), e.g. `test_returns_ru_with_default_locale` sets `title="Russian title"` and asserts `get_title() == "Russian title"`.
- If PO declines Task 3, leave behavior as-is (it works via `getattr` default); it is flagged only as latent tech debt.

### Task 4 — Smoke-test seed examples manually (validation step, not a deliverable code change)
**Purpose:** Per Decision_09 the PO wants to *see* seed ads in different languages. After Tasks 1-2, boot the dev stack, open a published seed ad detail, and confirm: `?lang=en` → English; `?lang=bs` → Bosnian; no param → Russian; switcher persists via `lang_pref` cookie on reload. This is the user-facing acceptance check that the seed examples "are on different languages and you can see the text in the desired language" (Decision_09).

---

## 4. Product Owner Decisions

| # | Question (see §2 open questions) | Decision |
|---|---|---|
| D1 | Q1 — Scope surface = ad content only; static UI stays English? | **(A) Ad content only.** Static `{% trans %}` strings remain as-is (no `.mo`, no translation API per Decision_09). Confirmed by Decision_09. |
| D2 | Q2 — `bs` = Bosnian-Latin, no `cnr`? | **(A) Yes.** Single `bs` locale (Bosnian-Latin) per `LanguageLocale`. |
| D3 | Q3 — Need `user.profile.language` for sellers? | **(B) No.** Cookie + session (`django_language` key) is sufficient; buyers (ad consumers) are anonymous. |
| D4 | Q4 — Include Task 3 dead-column cleanup? | **(A) Yes, include** — safe, removes latent confusion, aligns test with schema. |
| D5 | Root-cause fix approach? | **(A) Approach B** — remove `LocaleMiddleware`, make `LanguagePreMiddleware` the single authority via `translation.activate()` + `Vary`/`Content-Language` in its own `process_response`. Chosen over Approach A (cookie align — does not fix first `?lang=` click) and Approach C (`set_language`+`i18n_patterns` — disproportionate, would re-Prefix URLs/renounce `?lang=` policy). **Task 1.** |

---

## 5. Research Summary

### Researcher session `ses_01fa38721ffemMe0of6rRTdly9` — key findings
- **Root cause confirmed (HIGH):** `LocaleMiddleware` (`locale.py:35-36`) runs after `LanguagePreMiddleware` and re-derives language from `settings.LANGUAGE_COOKIE_NAME` (default `"django_language"`, never set in this project) + `Accept-Language`, ignoring `?lang=` and `lang_pref` → overwrites `request.LANGUAGE_CODE` to `ru`. (§3 full chain.)
- **Cookie-name mismatch (HIGH):** custom middleware uses local constant `"lang_pref"` (`language.py:20`); Django reads `settings.LANGUAGE_COOKIE_NAME` (`"django_language"`); `settings.LANGUAGE_COOKIE_NAME` is **not** overridden anywhere (`global_settings.py:164`).
- **No `i18n_patterns` / `set_language` / `.mo` / `gettext` imports in project (HIGH):** grep-verified. `LocaleMiddleware` is fully dormant except for the destructive clobber; `{% trans %}` is a no-op (all `django.po` `msgstr` empty, no `.mo`).
- **Seed content already complete (F3):** 351 templates with ru/en/bs `patterns`; `AdGenerator` writes all 6 columns; `test_seed.py:705-850` verify multi-language fields. The "missing translated examples" premise is false — data layer is fine.
- **Fix evaluation (ranked):** **B (recommended)** complete + low-risk given dormant i18n; **A** minimal-risk stopgap but leaves first-click defect; **C** disproportionate (URL prefix + cookie rename + drop `?lang=` policy); **D** not viable standalone.
- **Test gap:** existing tests exercise `LanguagePreMiddleware` in isolation only; no test mounts both middlewares. Recommended integration test (real `Client`, published seed `Ad`, `?lang=en` renders English column + headers) would have caught the clobber (§3 Task 2).
- **Latent inconsistency (not root cause):** `get_title`/`get_description` reference `title_ru`/`description_ru` columns that do not exist; Russian is `title`/`description`; `test_ad_localization.py` asserts phantom-column behavior on an in-memory object. Addressed by Task 3.

### Risks / edge cases carried forward
- R1. `Vary: Accept-Language` **must** be re-added in the custom `process_response` after removing `LocaleMiddleware` (Task 1), else any reverse proxy could cache a page in one language and serve it to another-locale users.
- R2. `translation.activate()` in the custom middleware is required so `{% get_current_language %}`/thread-local is consistent with `request.LANGUAGE_CODE` (switcher highlight). Without it the switcher shows a stale language.
- R3. First `?lang=` request has no prior cookie — Approach B fixes this (reads the param directly); Approach A does not.
- R4. Whitespace-only translated columns are truthy and returned without fallback (`test_ad_localization.py:89-92`); preserve this behavior.
- R5. Bot process is unaffected (shares ORM, writes ad content, does not render the site).

---

## 6. Validation (independent re-check)

Validator agent session `ses_01f8eecb8ffertGa35TXOgVryc` re-verified every claim against the actual codebase (`src/backend/...` + `.venv` Django source). Verdict: **all 11 claims CONFIRMED** with exact `file:line` citations; architecture analysis is sound.

- Claims 1–11 (middleware order, clobber line numbers, cookie mismatch, dormancy of `LocaleMiddleware`, seed-content completeness, test gap, phantom `title_ru` column) — all **CONFIRMED**.
- **Architecture verdict on Approach B: sound-with-caveats.** Verified that `{% get_current_language %}` and `{% get_available_languages %}` still work without `LocaleMiddleware` (they read the thread-local `translation.get_language()` / `settings.LANGUAGES` respectively, not the middleware), and that no Django subsystem actually requires `LocaleMiddleware` here (admin, form widgets, formatting all fall back to `settings.LANGUAGE_CODE` or format files without project `.mo`). The only requirement is keeping the thread-local (`translation.activate`) and `request.LANGUAGE_CODE` **in sync** — hence the added consistency assertion (see §3 Task 2 / R2).
- `Vary: Accept-Language` confirmed **not** functionally required for the current deployment (only `LocMemCache`, no reverse-proxy page cache per spec A3), but re-added in `process_response` for forward-correctness.
- **Overall confidence: HIGH** — accept the spec as-is; only the augmentative thread-local consistency assertion was folded in.

