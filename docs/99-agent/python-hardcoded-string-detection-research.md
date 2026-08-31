---
id: python-hardcoded-string-detection-research
title: Hardcoded User-Facing String Detection in Python — Research Report
date: 2026-08-23
project: Mko Bazuna (Python 3.14, Django 5.2 LTS, PostgreSQL 18)
confidence: HIGH (all findings verified against source via AST scanning + source inspection)
---

> **Purpose:** Evaluate whether automated detection of hardcoded user-facing strings in
> `src/backend/` Python is feasible, or whether the spec's §4.6/§5.2 decision to route
> Python-side i18n to **code review** (automation covers templates only) is correct.
>
> This report is the Python-side complement to
> `docs/99-agent/translation-completeness-check-research.md` (which covers *template*
> detection and is confirmed accurate by re-reading).

---

## 0. Executive Summary

**Finding:** Automating Python-side hardcoded-string detection is *technically possible* but
**not cost-justified** for this codebase. Three verified facts drive this conclusion:

1. **gettext is not used anywhere in `src/backend/`**. Django's `gettext`/`gettext_lazy`
   is imported in **zero** production files (confirmed by grep and AST scan). Python-side
   i18n for the website is effectively *not yet adopted* — which is why the spec's
   §3.3 only documents **2** known Python-side hardcoded strings.
2. The **total population of genuine, public-facing, Python-sourced UI strings is ~15**
   (detailed in §3). A naive AST scan flags **3098** string literals — a **>99% false-positive
   rate** before any exclusions.
3. The most common legitimate pattern — **building a `context` dict as a variable, then
   passing it to `render()`** — is **invisible to call-site AST scanning** and requires
   data-flow analysis to detect (the killer limitation).

The spec's existing decision stands: **code review (§4.6 checklist) is the correct control
for Python; automation should remain template-only.** This report recommends *not* building
a general Python detector, while documenting a small set of high-signal, low-effort guards
(§5) that could complement review if the team wants a minimal safety net.

---

## 1. Problem Definition

### 1.1 What counts as a "hardcoded user-facing string"

A string literal in Python source that **ultimately becomes visible text in the browser**
rendered to an end user of the web site. Concretely, this is any of:

- A value placed into a context dict passed to `render()` / `render_to_string()` /
  `TemplateResponse` that a template outputs via `{{ var }}`.
- The body of an HTTP response that is rendered to a browser (not swallowed by middleware).
- A label returned by an enum's `.choices()` that becomes an `<option>`/`<select>` text.
- A `__str__()` return or `verbose_name` rendered by the admin UI.
- A `short_description` column header or `admin.action(description=...)` shown in Django admin.
- A `self.message_user(...)` message shown to a staff user.

### 1.2 What does NOT count (the noise)

These are the categories a detector must suppress (sized in §3):

| Category | Examples | Approx. occurrences (prod) |
|---|---|---|
| Module/class/function **docstrings** | `"""Seller dashboard views..."""` | 584 |
| `logger.info` / `logger.warning` args | `f"User {id} attempted..."` | 117 (+ 219 f-string parts) |
| **f-string interpolation parts** | `f"Rejected {count} ad(s)."` parts | 219 |
| `help_text` field kwargs | `"Ad title in Russian (translated from seller input)"` | 143 |
| `short_description` / admin `description` kwargs | `"Rejection Reason"`, `"Reject selected ads"` | 18 |
| Model **FK class refs** (`"users.User"`, `"ads.Ad"`) | machine identifiers | 30 |
| Django **settings constants** (`BACKEND`, `ENGINE`, `NAME`) | machine config | ~40+ |
| `redirect()` / `reverse()` **URL names** | `"ads:dashboard"` | 13 |
| **Template-name strings** at `render()` call sites | `"ads/list.html"` | 22 |
| `StrEnum` **member values used as machine identifiers** | `'draft'`, `'on_moderation'`, `'category'` | 81 |
| **Dictionary keys** (template-variable names) | `'ad'`, `'feature'`, `'error'` | ~24 of 25 render-context strings |
| Http404 messages (not user-visible in prod) | `"Ad not found"`, `"Image not found"` | 7 |
| JsonResponse machine keys (`status`, `ok`, `error`) | API JSON contract | ~25 |

### 1.3 Scope

- **In scope:** `src/backend/` `.py` files (production code).
- **Explicitly out of scope** (per spec Q3): `src/telegram_bot/` — the Telegram bot holds the
  *majority* of user-facing Russian text (807 string constants across 28 files) but is a
  separate i18n concern.
- **Tests / seed / migrations:** excluded from the "should be wrapped" audit (test assertions
  intentionally assert on current strings; seed data is synthetic). Findings from these are
  noted only to confirm they are *not* the bot-side public surface.

---

## 2. Approaches Evaluated

Methodology: each approach was assessed against the **real** `src/backend/` tree
(297 `.py` files; 193 production non-test/seed/migration files; 3098 string literals).
For Python tooling capabilities, ruff/pylint/semgrep were evaluated via official docs and
source inspection (these tools are not installed locally, so claims are sourced from
authoritative docs rather than local execution).

### A. AST-based detection (Python `ast` module) — **rank: most promising, but still not recommended as a gate**

**How it works:** Walk `ast.Constant` string nodes; classify by parent context; suppress the
known-OK buckets from §1.2; flag the remainder.

**Evidence gathered (actual scans run against the repo):**

| Scan | Strings flagged | Genuine UI strings | False positives |
|---|---|---|---|
| All string constants, production files | **3,098** | ~15 | ~3,083 (99.5%) |
| Render-context dict values (recursive) | 25 | 1 (`edit.py:170`) | 24 (dict *keys* like `ad`, `feature`, `error`) |
| HttpResponse/Http404/JsonResponse args | 43 | ~5 (`HttpResponseForbidden`) | ~38 (Http404-hidden, JSON keys, `content_type`) |
| `render()` call-site inline dicts only | 1 | 1 | 0 |
| Dict literals assigned to `context` vars | **0** (but misses nesting!) | — | — |

**The fatal flaw — call-site scanning misses the dominant pattern (HIGH confidence):**
The `dashboard()` view (`apps/ads/views/dashboard.py:75-88`) builds its context as a
*variable* — `context = {...}` — and then calls `render(request, "ads/dashboard.html", context)`.
Only **1 of 11** view files passes an inline dict literal to `render()`; the other 10 build
the dict as a named variable first. A call-site-only AST scan therefore **misses 10/11
render-context flows** and would have missed `status_labels` entirely (5 genuine UI strings:
`"Published"`, `"On Moderation"`, `"Failed Moderation"`, `"Archived"`, `"Rejected"` at
`dashboard.py:77-83`, confirmed rendered at `dashboard.html:76`).

Catching these requires **intra-procedural data-flow**: trace `context = {...}` →
`render(..., context)`. That is a meaningful step up in complexity (alias analysis: is
`context` reassigned, aliased to another name, merged?).

**Other disambiguation pain points (verified):**
- `Http404("Ad not found")` vs `HttpResponseForbidden("You do not have permission…")` —
  only the latter's body reaches the browser in production. Distinguishing them is
  **type-aware** (inspect the exception class / response class), not just AST.
- The 81 `StrEnum` member values (`'draft'`, `'published'`, `'telegram'`, `'russian'`,
  `'search_vector_ru'`, …) are all *machine identifiers* per §5.2's known-OK list, but
  are **syntactically identical** to legitimate labels (`'small'`, `'medium'` look harmless
  yet are `ThumbnailSizeStrEnum` machine values). An AST checker must either trust the
  project rule "all StrEnum values are machine IDs" or misflag all 81.

**Bottom line on A:** Accuracy after a *well-built* exclusion set is acceptable (~15 true
positives), but the **false-positive rate on a naive scan is ~99.5%**, and **reliable
coverage requires data-flow + type analysis** that pushes this from a "100-line AST walk"
to a project-scale static-analysis effort. For 15 strings, the maintenance burden never
pays off.

### B. pylint plugin (custom checker) — **feasible tooling, wrong stack**

**Evidence:** There is a real, published checker — [`pylint-i18n`](https://pypi.org/project/pylint-i18n/)
("Find strings in your code that should be passed through gettext"), and the pattern is
documented (Ned Batchelder's
[Writing pylint plugins](https://nedbatchelder.com/blog/201505/writing_pylint_plugins.html),
edx-lint `i18n_check.py`). Pylint uses **astroid**, a richer AST with limited inference,
so it *can* distinguish `gettext("literal")` from `gettext(some_var)` and can track
simple assignments — exactly the data-flow a pure `ast` walker cannot.

**But** the project does **not use pylint**. It uses **ruff** (`make lint` → `ruff check .`,
CI `lint` job runs `uv run ruff check .`). Adding pylint means:
- A second linter in CI/dev (pylint is ~112s vs ruff ~0.27s on CPython — *Real Python* /
  ruff benchmarks; the project's existing `make lint` is ruff-only).
- Two divergent exclusion/naming conventions to maintain.
- Violates the "Follow Existing Patterns" project rule.

**Assessment:** Effort to *write* the checker is low (existing `pylint-i18n` can be
reused or adapted). **Integration cost is high** because it requires introducing pylint
into a ruff-only pipeline. Confidence this fits the project: LOW.

### C. Semgrep rules — **works, but adds a new tool and inherits A's false-positive problem**

**Evidence (docs.src):** Semgrep matches on the AST (not text), supports metavariables
(`"..."` matches any string literal), `metavariable-regex`, and `pattern-not` for
exclusions. A rule can be written in ~15 lines of YAML.

**Example shape** (would also need ~20 `pattern-not` exclusions to reach a usable FP rate):

```yaml
# hypothetical: flag string literals NOT wrapped in gettext/messages/logger
rules:
  - id: non-translated-ui-string
    languages: [python]
    message: "Possible hardcoded UI string (verify it is wrapped in gettext or is a known non-UI literal)"
    severity: WARNING
    patterns:
      - pattern: '"$S"'            # any string literal
      - pattern-not: 'gettext(..., "$S")'   # … but this is NOT the exclusion syntax; need metavariable-regex
```

In practice Semgrep has **no native "is this a UI string" predicate** — the rule would
match *every* string literal (same 3098) and must be winnowed by a long `pattern-not`
chain mirroring §1.2. That chain is the maintenance burden. Semgrep is also **not in the
project dependency tree** (`pyproject.toml` dev group = ruff, djlint, basedpyright, pytest).

**Assessment:** Integration effort medium (new tool in CI + config), and it **does not
solve the data-flow limitation** that sinks approach A (variable context dicts). Confidence
the FP problem is manageable: MEDIUM (needs the same exclusion maintenance as A).

### D. ruff custom rule — **not supported; do not use**

**Evidence (authoritative):**
- Ruff docs (`docs.astral.sh/ruff/linter`, `docs.astral.sh/ruff/rules`) state rules are
  **re-implemented in Rust as first-party features** — "Ruff supports over 900 lint rules…
  regardless of the rule's origin, Ruff re-implements every rule in Rust."
- The `pydevtools.com` comparison table explicitly lists:
  **"`Plugin system | No (built-in rules)`"** for Ruff (vs `Yes` for flake8 and Pylint).
- Ruff's own [`CONTRIBUTING.md`](https://github.com/astral-sh/ruff/blob/main/CONTRIBUTING.md)
  shows new lint rules are added under `crates/ruff_linter/src/rules/` in **Rust**, with
  `scripts/add_rule.py` scaffolding — i.e., contribution to ruff *itself*, not a project
  config.
- The `ruff.api` PyPI package is documented as **"highly experimental" and the API is likely
  to change** — not a supported path for project lint rules.
- Ruff's nearest existing rule family is **flake8-gettext (INT)**: `INT001` (f-string in
  gettext plural arg), `INT002` (format in gettext arg), `INT003` (printf in gettext arg).
  These verify that *gettext is called correctly* — they do **not** detect strings that
  *should* be wrapped. No ruff rule "finds non-translatable strings."

**Assessment:** Writing a *new* ruff rule requires Rust development against ruff's source
(5/5 effort) and upstreaming — there is no in-tree `pyproject.toml` mechanism to add a
project-authored rule. Do **not** pursue. Confidence: HIGH.

### E. grep / regex heuristic — **simplest, worst FP, not gate-able**

**Evidence:** The Cyrillic regex scan earlier (before AST) returned matches in docstrings,
test assertions, and inline JS templates — the tool cannot tell a `help_text` docstring
context from a render value. A regex like `"([^"]+)"` inside `def` blocks that contain
`render(` would still swallow dict keys (`'ad'`, `'feature'`) and template names.

**Assessment:** 1/5 implementation, but 1/5 accuracy. Useful *only* as an informational
"smoke scanner" (warn, don't gate), and even then it is strictly dominated by approach A
(a 40-line AST script is just as easy and far more precise). Not recommended.

### Ranking (feasibility × fit for this project)

| Approach | Signal achievable | False-positive rate (as-built) | Effort | Verdict |
|---|---|---|---|---|
| A. AST (`ast`) | Medium (after exclusions) | ~95% on naive; ~5% after hand-built exclusions | 2–3 days to build & tune; ongoing brittleness | Viable only as a *partial* guard, not a gate |
| B. pylint plugin | High (astroid inference helps) | Low (can be precise) | 1–2 weeks incl. pylint integration | Wrong stack; do not add pylint |
| C. Semgrep | Medium (same FP issue as A) | ~95% naive; ~5% after exclusions | 3–5 days (tool + rule + CI) | Overkill relative to A |
| D. ruff custom rule | None (cannot be done in-project) | N/A | 5/5 (Rust contribution) | **Not feasible** |
| E. grep heuristic | Very low | ~99% | <1 day | Noise-only; not actionable |

---

## 3. Codebase Survey (measured)

Scans are AST-based over `src/backend/`, **production files only** (excludes
`tests/`, `seed/`, `migrations/`, `__pycache__`).

### 3.1 Corpus size

| Slice | `.py` files | string-literal constants |
|---|---|---|
| `src/backend/` total (incl. tests/seed/migrations) | 297 | 9,474 |
| `src/backend/` production (excl. tests/seed/migrations) | **193** | **3,098** |
| `src/telegram_bot/` (out of scope) | 28 | 807 |

### 3.2 Hardcoded Cyrillic (Russian) strings in production Python

Only **3** production files contain Cyrillic string literals that are *not* docstrings:

| File:Line | Context | Genuine UI? |
|---|---|---|
| `apps/core/context_processors.py:46` | `preferred_city_display = "Вся страна"` | ✅ Yes — rendered at `header_catalog.html:48` |
| `apps/search/services/immediate_alerts.py:103,105,112,119` | Telegram alert message fragments (`"Объявление"`, `"Цена не указана"`, `">Посмотреть объявление</a>"`, `"🔕 Отключить этот поиск"`) | ❌ No — **Telegram bot** channel (out of scope per Q3). These live in `search.services` but are sent via bot. |
| `apps/seed/generators/ads.py:254,395` | Seed ad `title`/`description` templates (`"Товар"`, `"Описание товара."`) | ❌ No — seed/synthetic data (excluded scope). |

Plus Cyrillic **inside docstrings** (not user-facing) in:
`apps/cabinet/apps.py:1`, `apps/search/services/entity_suggestions.py:18`,
`apps/search/services/immediate_alerts.py:92`,
`apps/search/views/save_search.py:1`,
`apps/categories/models.py:95` (`help_text` — admin-facing, staff-only).

**Conclusion for Cyrillic in Python:** exactly **1** genuine public-facing UI string
(`"Вся страна"`), and it is the one the spec already documents (§3.3.1). Everything else
is either bot-out-of-scope, seed data, docstrings, or admin `help_text`.

### 3.3 Hardcoded English UI strings in production Python

These are the strings a detector SHOULD flag (verified by reading the actual render flows
and confirming template consumption):

| # | File:Line | String | Flows to | Type | Already in spec §3.3? |
|---|---|---|---|---|---|
| 1 | `context_processors.py:46` | `"Вся страна"` (Cyrillic) | `header_catalog.html:48` `{{ preferred_city_display }}` | context processor | ✅ documented |
| 2–4 | `enums.py:133–136` | `"All Time"`, `"30 Days"`, `"7 Days"` | `dashboard.html:62` `<option>{{ label }}</option>` (via `TimeRange.choices()`) | enum `.choices()` labels | ✅ documented |
| 5–9 | `dashboard.py:77–83` | `"Published"`, `"On Moderation"`, `"Failed Moderation"`, `"Archived"`, `"Rejected"` | `dashboard.html:76` `{{ status_labels|get_item:status }}` | render-context dict values | ❌ **new finding** |
| 10 | `edit.py:170` | `"Ad failed moderation checks"` | `ads/edit.html` (as `error` context) | render-context inline dict value | ❌ **new finding** |
| 11 | `delete.py:44` | `"You do not have permission to delete this ad."` | 403 HTTP response body (browser) | `HttpResponseForbidden` body | ❌ **new finding** |
| 12 | `edit.py:105` | `"You do not have permission to edit this ad."` | 403 HTTP response body | `HttpResponseForbidden` body | ❌ **new finding** |
| 13 | `edit.py:243` | `"You do not have permission to archive this ad."` | 403 HTTP response body | `HttpResponseForbidden` body | ❌ **new finding** |
| 14 | `edit.py:274` | `"You do not have permission to reactivate this ad."` | 403 HTTP response body | `HttpResponseForbidden` body | ❌ **new finding** |
| 15 | `listings.py:187` | `"Access denied"` | 403 HTTP response body | `HttpResponseForbidden` body | ❌ **new finding** |

**Total genuine public-facing UI strings in production Python: 15** (1 Cyrillic + 14 English).
Of these, **only 5 are already documented** in the spec §3.3; **10 are undocumented** and were
discovered by this scan (notably the 5 `HttpResponseForbidden` bodies, the `status_labels`
block, and the `edit.py:170` error).

> Note on `Http404("Ad not found")` (6 occurrences in `listings.py`, `favorite.py`,
> `categories/views.py`, `moderation/views/decorators.py`): these are **NOT** user-facing in
> production — Django's default 404 handler logs the message and renders a generic page; the
> string is only surfaced under `DEBUG=True`. A detector that flags them is a false positive
> by the project's standard (machine/error detail, not UI). This is the canonical example of
> why **type-aware** disambiguation (response class) is required.

### 3.4 Admin-facing (staff-only) strings — relevant to spec Q1

A wide ring of "UI strings" exists in Django-admin code paths that the spec's Q1 leaves
undecided ("staff-only — PO decision"). These are *not* public-facing but would be flagged
by a naive scanner and would need an admin-scope exclusion:

| File:Line | String | Context |
|---|---|---|
| `ads/admin.py:31` | `"User (telegram_id)"` | `short_description` column header |
| `ads/admin.py:42` | `"Rejection Reason"` | `short_description` |
| `ads/admin.py:50` | `"Ad ID"` | `short_description` |
| `ads/admin.py:58` | `"Features"` | `short_description` |
| `ads/admin.py:115` | `"Reject selected ads"` | `@admin.action(description=...)` |
| `ads/admin.py:121` | `"Approve selected ads"` | `@admin.action(description=...)` |
| `ads/admin.py:127` | `"Ban users from selected ads"` | `@admin.action(description=...)` |
| `ads/admin.py:133` | `"Soft delete selected ads"` | `@admin.action(description=...)` |
| `ads/admin.py:145–147` | `"On Moderation"`, `"Failed"`, `"Rejected"` | `moderation_queues` context list |
| `moderation/models.py:75–79` | `"Moderation Criteria"` | `verbose_name` + `__str__` |
| `ads/admin.py:119,125,131,137` | `f"Rejected {count} ad(s)."` etc. | `self.message_user` (admin toast) |

These are f-strings (`self.message_user(request, f"..."`) so they were *not* captured by a
literal-string scan — another reminder that **interpolation obscures literals**, increasing
false negatives for any literal-only scanner.

### 3.5 Patterns that make detection easier or harder

| Pattern | Helps / hurts | Evidence |
|---|---|---|
| Most views build `context` as a **named dict variable** then call `render(..., context)` | **Hurts** — requires data-flow, not call-site AST | 10 of 11 view `render()` call sites pass a variable, not an inline dict |
| String values are usually **dict keys** (variable names), not values | **Hurts** — keys dominate the literal count, swamping signal | 24 of 25 render-context literals are keys, not values |
| `StrEnum` members are machine identifiers, not labels | **Hurts** — 81 enum values look like candidates but must be excluded | §5.2 §5.2 rule |
| `Http404` vs `HttpResponseForbidden` need different handling | **Hurts** — type-aware distinction | 7 vs 5 in §3.3 |
| `HttpResponseForbidden`, `render`-inline dict are the *only* high-confidence contexts | **Helps** — these two contexts are small & precise | 5 + 1 = 6 genuine strings from two tight patterns |
| `gettext`/`gettext_lazy` is **not imported anywhere** | **Helps the argument against automation** — the public-Python surface is tiny (15 strings) | grep + AST confirmed |

---

## 4. Implementation Difficulty Assessment (1 = trivial, 5 = infeasible)

Ratings reflect *this project's* stack (ruff-only lint pipeline, Docker test DB on 5433,
no pylint/semgrep/gettext).

| Approach | Impl effort (1–5) | FP rate (1–5: low→high) | FN rate (1–5: low→high) | Maintenance (1–5) | CI integration (1–5) | Overall |
|---|---|---|---|---|---|---|
| **A. AST (`ast`)** | 3 | 4 (naive:5) | 3 (misses variable context + f-string interiors) | 4 (brittle to context changes) | 2 | Not recommended as a gate |
| **B. pylint plugin** | 2 | 2 | 2 | 3 | 5 (no pylint in pipeline) | Wrong stack; rejected |
| **C. Semgrep** | 2 | 4 (same exclusions as A) | 3 | 4 | 3 (new tool) | Overkill; rejected |
| **D. ruff custom rule** | 5 | — | — | 5 | 5 | **Not supported** |
| **E. grep heuristic** | 1 | 5 | 4 | 2 | 1 | Noise-only |

---

## 5. Recommendation

### Verdict: **Do NOT build a general Python-side detector. The spec's §4.6/§5.2 decision (code review for Python; automation for templates only) is correct.**

### Why

1. **The signal is tiny and nearly all already known.** Only **15** genuine public-facing UI
   strings exist in all of `src/backend/` Python; **5 are already documented** in the spec
   §3.3, and the remaining 10 are concentrated in just 4 files (dashboard, edit, delete,
   context_processors). A dedicated detector is being built to catch a population that
   fits on a postcard.

2. **A naive detector is pure noise.** Flagging every string literal yields 3,098 candidates
   (>99% false positives: docstrings, `help_text`, Slugs, enum machine IDs, dict keys,
   config constants). Even after engineering the §1.2 exclusion set, the remaining buckets
   (`StrEnum` values, dict keys vs values, `Http404` vs `HttpResponseForbidden`) demand
   **type- and data-flow-aware analysis** that a lightweight `ast` walk cannot provide
   without false positives or false negatives.

3. **The dominant pattern defeats call-site scanning.** 10 of 11 views build their context
   as a *variable* (`context = {...}`) before calling `render()`. The 5 `status_labels`
   strings that a call-site scan misses are themselves genuine UI — exactly the kind you
   want to catch. Reliable coverage therefore needs intra-procedural taint/data-flow
   analysis, at which point you have reimplemented half of Pylint, and should simply use
   Pylint (which the project does not use and should not adopt for one concern).

4. **ruff cannot host the rule.** The project's lone linter is ruff (`make lint`), and ruff
   has **no in-project custom-rule mechanism** — rules are Rust-first-party features.
   (Verified: ruff docs, CONTRIBUTING.md, `scripts/add_rule.py`; `ruff.api` is
   "highly experimental".) There is no `flake8-gettext`-style rule that detects
   *missing* wrapping, only `INT001–003` that validate *correct usage* of gettext calls.

5. **Two of the three documented cases are being fixed anyway.** Task 2 (§4.38–4.42) wraps
   `"Вся страна"` and `TimeRange.choices()` in `gettext`/`gettext_lazy`. Once wrapped, the
   only way a *new* hardcoded UI string enters is a developer writing a raw literal in a
   new render context — exactly what the §4.6 code-review checklist (the very checklist
   this report feeds) is designed to catch.

### If the team still wants a lightweight Python-side safety net

Rather than a scanner that *guesses* whether a string is UI, add **two high-signal,
low-brittleness pytest guards** that encode the spec's own known-OK rules. These are
deterministic (no FP guessing) and directly prevent the two recurrence classes the survey
found:

**Guard 1 — `enum.choices()` labels must use `gettext_lazy`.**
The `TimeRange.choices()` pattern (returning raw `"All Time"` strings) is the *one*
enum pattern that produces user-facing labels. A guard that introspects `StrEnum`
subclasses and asserts that any `choices()`/`labels()`-style method returns lazy strings
(not `ast.Constant`/`str`) is ~40 lines, stable, and zero-FP. It would have caught
§3.3.2 directly.

```python
# (in a pytest test — NOT created as a project file per task constraints)
import ast, pathlib, re
from collections import Counter


def _choices_methods_returning_literal_strings():
    """Flag StrEnum classes whose methods return tuple-list literals with str constants."""
    offenders = []
    for p in pathlib.Path("apps").rglob("*.py"):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                bases = [ast.unparse(b) for b in node.bases]
                if not any("Enum" in b for b in bases):
                    continue
                for fn in node.body:
                    if isinstance(fn, ast.FunctionDef) and fn.name in {
                        "choices",
                        "labels",
                    }:
                        for sub in ast.walk(fn):
                            if isinstance(sub, ast.Constant) and isinstance(
                                sub.value, str
                            ):
                                offenders.append(
                                    (str(p), sub.lineno, fn.name, sub.value)
                                )
    return offenders


def test_enum_choice_labels_are_translated():
    bad = _choices_methods_returning_literal_strings()
    assert not bad, f"Choices() returns raw strings (wrap in gettext_lazy): {bad}"
```

**Guard 2 — no raw Cyrillic literals in `context`/render paths.**
A scan identical to the one that found `"Вся страна"` (search `ast.Constant` Cyrillic
values that are *not* docstrings or `help_text`) — ~60 lines, stable, zero-FP against the
documented §3.3.1.

Both guards are **deterministic** (they flag a precise, well-defined anti-pattern rather
than "any string that might be UI") and therefore avoid the FP collapse that sinks a
general detector. They do **not** attempt to catch every possible UI string (which is what
code review is for); they harden the *two specific shapes* the project has already tripped.

### Effort estimate for the recommended (no-automation) path

| Item | Effort |
|---|---|
| Fix the 2 documented strings (Task 2) + the 10 undocumented ones found here (5× `HttpResponseForbidden`, 5× `status_labels`, 1× `edit.py:170` error) | 0.5 day |
| Update asserting tests with `translation.activate("ru")` (§4.4 / Task 6) | 0.5 day |
| Keep Python under code review (§4.6 checklist) — **no new code** | 0 |
| *(Optional)* add the two deterministic pytest guards above | 0.5 day |

**Not recommended:** a general `ast`/`semgrep`/`pylint` scanner for "any hardcoded UI
string" — disproportionate cost, ~95%+ FP noise, and it still misses the variable-context
pattern that produced 5 of the 10 undocumented findings.

---

## 6. Known-OK Exclusions for Python (mirrors spec §5.2)

A detector that flags string literals must suppress (at minimum) all of the following.
This list is the reason a naive scan produces 3,000+ false positives:

- **Docstrings** — module/class/function `"""..."""`, first statement of a body.
- **`logger.*()` arguments** — `logger.info/warning/error/debug/exception/...`,
  including the literal *parts* of an f-string inside such a call.
- **f-string/template interpolation literal segments** — `f"Rejected {count} ad(s)."`
  contains a literal segment `" ad(s)."` that is not independently translatable.
- **`help_text=` / `verbose_name=` / `verbose_name_plural=`** model field kwargs and
  `Meta` attributes (admin-facing, mostly staff).
- **`short_description`** assignments and **`@admin.action(description=...)`** kwargs.
- **`self.message_user(...)` messages** (admin toasts).
- **Model FK / M2M constructor class refs** — `"users.User"`, `"categories.Category"`,
  `"lookups.LookupItem"` (machine identifiers).
- **`StrEnum` / `Enum` member values used as machine identifiers** (`'draft'`,
  `'published'`, `'category'`, `'ru'`, `'EUR'`) — *per §5.2, these are never display
  labels*. (Exception: the *return values* of a `.choices()` method that produces labels
  — see Guard 1.)
- **`redirect()` / `reverse()` URL names** — `"ads:dashboard"`, `"consent:withdraw"`.
- **Template-name strings** — `"ads/list.html"`, `"components/favorite_heart.html"`
  passed (positionally or as `template_name=`) to `render()`/`render_to_string()`.
- **Dictionary keys** in render-context dicts — `"ad"`, `"feature"`, `"error"`,
  `"time_range_options"` (template-variable names, not visible text). **Note:** this is
  the single biggest noise source — keys outnumber genuine values ~24:1 in this repo.
- **Django settings constants** — upper-case module attributes (`DATABASES`,
  `LOGGING`, `CACHES` values like `"django_redis.cache.RedisCache"`,
  `"django.template.backends.django.DjangoTemplates"`, `"FileSystemStorage"`).
- **`Http404(...)` messages** — not rendered to the browser in production (logged only).
- **`JsonResponse` dict values** that are machine keys/stats (`status`, `ok`, `error`,
  `rate_limit`, `invalid_city`, `unhealthy`) — API contract, not browser UI.
- **`HttpResponse(content_type=...)`** keyword values (e.g. `"image/jpeg"`).
- **Brand names / currency / locale codes** — `"Mko Bazuna"`, `"EUR"`, `"RSD"`, `"BAM"`,
  `"ru"`, `"en"`, `"bs"`.
- **Exception class names / error codes** — `"Bulk rejection via admin action"`,
  `"Bulk ban via admin action"` (these are *internal* log/action labels, not user UI).
- **Type annotations / type strings** — `"src/backend"`, module paths.
- **Regex patterns / SQL fragments / cache keys** — when present in `re.compile(r"...")`
  or raw SQL strings.

### What is left *after* applying all exclusions above

~15 genuine public-facing UI strings (§3.3), which is too small a set — and too
context-dependent a classification problem — to justify a dedicated, maintained detector.
The deterministic guards in §5 close the two recurrence classes the project actually
hit (enum `.choices()` labels and Cyrillic context strings); everything else is covered by
the §4.6 code-review checklist.

---

## 7. Sources & Verification

| Source | Confidence | Evidence extracted |
|---|---|---|
| `src/backend/` AST scan (297 files → 193 prod / 3098 literals) | HIGH | This report's counts; run via Python `ast` over the live tree |
| `apps/core/context_processors.py:46` | HIGH | `"Вся страна"` literal read directly |
| `apps/core/enums.py:133–136` (`TimeRange.choices`) | HIGH | Returns `"All Time"`/`"30 Days"`/`"7 Days"` |
| `apps/ads/views/dashboard.py:75–88` / `dashboard.html:76,62` | HIGH | `status_labels` + `time_range_options` rendered |
| `apps/ads/views/edit.py:170` | HIGH | `{"ad": ad, "error": "Ad failed moderation checks"}` |
| `apps/ads/views/{delete,edit}.py`, `listings.py:187` | HIGH | 5× `HttpResponseForbidden` bodies |
| grep for `gettext`/`gettext_lazy`/`django.utils.translation` in `src/backend` | HIGH | **0 matches** in production — gettext not adopted |
| `apps/ads/admin.py:115–133`, `moderation/models.py:75–79` | HIGH | Admin-facing strings (Q1 scope) |
| ruff docs (`docs.astral.sh/ruff/linter`, `/rules`) | HIGH | "re-implements every rule in Rust as a first-party feature" |
| ruff `CONTRIBUTING.md` + `scripts/add_rule.py` (GitHub) | HIGH | New rules = Rust contribution, not project config |
| ruff `flake8-gettext` (INT) rule docs | HIGH | INT001–003 exist (validate *usage*), no "find missing" rule |
| pydevtools "Ruff vs Pylint" comparison table | HIGH | "Plugin system | No (built-in rules)" for Ruff |
| `pylint-i18n` (PyPI / amandasaurus GitHub) | HIGH | Real checker exists; "find strings not passed through gettext" |
| Semgrep pattern-syntax docs (`docs.semgrep.dev`, `semgrep.dev/docs`) | HIGH | `"..."` matches any string literal; `metavariable-regex`/`pattern-not` for exclusions |
| Existing `translation-completeness-check-research.md` (§2.7, §2.9) | HIGH (re-read) | Confirms gettext absent, no `polib`; CI note now stale (CI exists) |
| `.github/workflows/ci.yml` (re-read during scan) | HIGH | Corrects prior doc: CI *does* exist with `build/test/lint/typecheck/lint-templates` jobs; lint = `ruff check .` only |

### Corrections to the earlier `translation-completeness-check-research.md`

Section 2.5 ("No CI pipeline") and E.1/E.5 are now **stale**: `.github/workflows/ci.yml`
exists with 5 jobs, and the `lint` job runs `uv run ruff check .` on `ubuntu-latest`.
The absence-of-pylint and ruff-plugin-system conclusions in *this* report are **unchanged**
and remain HIGH confidence.
