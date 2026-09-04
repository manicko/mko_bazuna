# Recommendations: Catalog Filter UI Fixes (T1–T4)

**Date:** 2026-09-03 · **Scope:** T1 (chips-block price condition), T2 (clear-all guard),
T3 (price chip), T4 (search-page clear-all `q` preservation) · **Status:** Recommendation for implementor
**Decision:** Proceed with the spec's proposed approach (extend the existing inline `{% if %}`);
do **not** introduce a `has_active_filters` context variable; do **not** DRY the URL
reconstruction as part of T1–T4 (out of scope per `filter-ui.md` / `05_filter-regression_spec.md`
L270). Flag the `querystring`-tag DRY opportunity as a separate future task.

---

## TL;DR

| Task | Recommendation | Why |
|---|---|---|
| T1 — chips-block price condition | **Extend** `{% if current_listing_purpose or current_features or current_condition or active_price_min or active_price_max %}` | PO-Q1=C (confirmed); AGENTS rule #7 (follow existing pattern); condition is used exactly once (wraps chips+clear-all after T2); a `has_active_filters` bool would duplicate computation across two views (DRY violation) |
| T2 — clear-all guard | **Move** L77–83 *inside* the (extended) L39 `{% if %}` block | PO-Q1=C; single shared condition for chips + clear-all; clear-all disappears automatically when no chips active |
| T3 — price chip | **Convert** L32–37 `<div class="filter-summary">` → `<span class="inline-flex … rounded-full">` chip with `×` removal link, placed inside the chips container | CR-6/CR-7; reuse the existing `{% blocktrans with min=active_price_min max=active_price_max %}` label (already extracted/compiled) |
| T4 — search clear-all `q` | **Branch** clear-all `hx-get` on `{% if query %}` to append `&q={{ query|urlencode }}`; **add `"query": None`** to listings.py context | CR-4; the `query` var is the existing page discriminator; explicit `None` makes the partial's contract symmetric (spec T4 L135 endorses) |

---

## 1. T1: Chips-block condition — extend inline vs. `has_active_filters` bool

### Two candidate approaches

**Option A — extend the inline `{% if %}`** (spec proposal / PO-Q1=C):
```django
{% if current_listing_purpose or current_features or current_condition or active_price_min or active_price_max %}
    <div class="flex flex-wrap gap-2 mb-4">
        {# purpose / condition / features / price chips #}
        {# Clear all filters link (after T2 moves it here) #}
    </div>
{% endif %}
```

**Option B — add a `has_active_filters` context variable** computed in both views:
```python
# In both listings.py and search.py
"has_active_filters": bool(
    listing_purpose_slug or condition_slug or feature_slugs
    or active_price_min or active_price_max
),
```
…then `{% if has_active_filters %}` in the template.

### Recommendation: **Option A (extend the inline `{% if %}`)**

**Rationale (evidence-based):**

1. **The PO explicitly chose C over A/B.** `.ai/problems/05_filter-regression_spec.md` PO-Q1 (L187): *"No separate `has_active_filters` variable needed; extend the existing chips condition to include `active_price_min` and `active_price_max`."* The "A" and "B" options in that table were *not* "has_active_filters" — they were different definitions of *when* the button shows. The PO rejected introducing a new variable.

2. **AGENTS.md rule #7 — follow existing patterns.** The chips block already uses an inline `{% if %}` (ad_list.html L39). The most local, lowest-surprise change is to extend that same expression. No new pattern is introduced.

3. **DRY at the *view* layer.** Option B requires computing the *identical* boolean in **two** separate view modules (`ads/views/listings.py` L447 and `search/views/search.py` L274). That's duplication. The spec author noted this cost ("No new context variable needed" — T1 L106 / T4 L135). Extracting a shared helper for one 5-term `or` is overengineering (rule #5).

4. **Single use-site.** After T2 moves the clear-all link *inside* the L39 block, the chips-block condition is referenced **exactly once** in the template. An inline `{% if %}` is the right tool for a single use. A named variable adds indirection without re-use benefit.

5. **No behavioral ambiguity.** The six source variables (`current_listing_purpose`, `current_features`, `current_condition`, `active_price_min`, `active_price_max`) are already all in context and already truthy/falsy-tested by surrounding logic. Extending the `or` chain by two terms is a safe, local edit.

**When Option B *would* be better:** if the same "are any filters active?" predicate were needed in **three or more** template locations, or if views beyond these two rendered the partial. Currently it's one location in one partial. So Option A wins on simplicity (rule #5).

---

## 2. T2+T3: Price chip shape and placement

### Current state (confirmed)
- Price summary: `ad_list.html` L32–37 — `<div class="filter-summary">` with `{% blocktrans with min=active_price_min max=active_price_max %}Price: {{ min }}–{{ max }}{% endblocktrans %}`; **no removal link**, **not a chip**, **outside** the L39 chips container.
- Peer chips (L41–74): `<span class="inline-flex items-center px-3 py-1 … rounded-full">` containing a label (`{% trans "Purpose:" %} {{ p|get_lookup_name:LANGUAGE_CODE }}`) + `&times;` `<a>` removal link.

### Recommended change for T3

Convert the price summary into a chip **inside** the chips container, mirroring the peer-chip structure:

```django
{% if active_price_min or active_price_max %}
    <span class="inline-flex items-center px-3 py-1 bg-yellow-100 text-yellow-800 rounded-full text-sm">
        {% blocktrans with min=active_price_min max=active_price_max %}Price: {{ min }}–{{ max }}{% endblocktrans %}
        <a href="?page=1{% if query %}&q={{ query|urlencode }}{% endif %}
            ...{% if current_listing_purpose %}&listing_purpose={{ current_listing_purpose }}{% endif %}
            {% if current_condition %}&condition={{ current_condition }}{% endif %}
            {% for fslug in current_features %}&features={{ fslug }}{% endfor %}
            {% if LANGUAGE_CODE %}&lang={{ LANGUAGE_CODE }}{% endif %}"
           hx-get="?page=1{% if query %}&q={{ query|urlencode }}{% endif %}
            ...{% if current_listing_purpose %}&listing_purpose={{ current_listing_purpose }}{% endif %}
            {% if current_condition %}&condition={{ current_condition }}{% endif %}
            {% for fslug in current_features %}&features={{ fslug }}{% endfor %}
            {% if LANGUAGE_CODE %}&lang={{ LANGUAGE_CODE }}{% endif %}"
           hx-push-url="true" hx-target="#ad-list" hx-swap="innerHTML"
           class="ml-2 text-yellow-600 hover:text-yellow-800">&times;</a>
    </span>
{% endif %}
```

#### i18n verification (item 3 of the brief)

- **Label pattern:** The price chip reuses the *existing* `{% blocktrans with min=active_price_min max=active_price_max %}Price: {{ min }}–{{ max }}{% endblocktrans %}` (ad_list.html L35). This msgid ("Price: %(min)s–%(max)s") is **already extracted and compiled** — `makemessages` already saw it (the price summary currently renders it as plain text). Converting to a chip changes **no** translatable string, so `test_i18n_completeness.py` / `test_no_hardcoded_visible_text` (docs/01-spec/i18n-spec.md L265–274) remain satisfied. ✔
- **Peer comparison:** The purpose/condition/features chips use `{% trans "Purpose:" %}` / `{% trans "Condition:" %}` / `{% trans "Feature:" %}` (static msgids) + `get_lookup_name` (DB-based, exempt). The price chip uses `blocktrans with` (variable interpolation), which is the *correct* choice when the string has positional variables — `{% trans %}` alone cannot interpolate `{{ min }}` / `{{ max }}`. This matches the 11 existing `{% blocktrans with %}` usages project-wide (grep: login_issue.html L16, moderation_dashboard.html L23/80, review.html L64/70/132/178, edit.html L72, privacy.html L22/29, **ad_list.html L35**). ✔
- **Removal link text:** `&times;` is a Unicode character, not a translatable ASCII string, so it needs no `{% trans %}`. The spec's CR-6 ("clickable chip with × removal link") is satisfied. ✔

#### Decimal vs. string consistency (item 3 of the brief)

- **Display** uses `active_price_min` / `active_price_max` — parsed `Decimal|None` (listings.py L347–359; search.py L110–122), exposed at listings.py L457–458 / search.py L283–284. ✔
- **URL reconstruction** uses `min_price` / `max_price` — raw `str|None` (listings.py L329–331 / L455–456; search.py L97–98 / L281–282). The price-chip *removal* URL simply **omits** these two params (does not emit `&min_price=`/`&max_price=`), exactly mirroring how the purpose chip omits `listing_purpose` and the condition chip omits `condition`. ✔
- This duality is **consistent** with how every other param works: raw GET strings go into URLs; parsed/typed views exist only where human formatting needs them. No change required. ✔

---

## 3. T4: Search-page clear-all `q` preservation

### Mechanism (existing)

`{% if query %}` already discriminates the two pages:
- `search()` sets `"query": query` (search.py L276), where `query = (request.GET.get("q") or "").strip()` (L57). On the search page, `query` is the (possibly empty) search term.
- `listings()` does **not** set `query` in its context (listings.py L447–467; grep confirms `query` appears only in two docstring comments at L207/L233, zero `"query"`-quoted context keys).

In the template, every chip/pagination link already uses `{% if query %}&q={{ query|urlencode }}{% endif %}` (ad_list.html L45, L58, L71, L144–177). So `query` is the established page discriminator and is already template-idiomatic.

### Recommendation

Make the clear-all URL branch on the same discriminator (spec T4, L133–134):

```django
{# Clear-all: preserve q ONLY on the search page #}
{% if query %}
    <a href="?page=1&q={{ query|urlencode }}{% if LANGUAGE_CODE %}&lang={{ LANGUAGE_CODE }}{% endif %}"
       hx-get="?page=1&q={{ query|urlencode }}{% if LANGUAGE_CODE %}&lang={{ LANGUAGE_CODE }}{% endif %}"
       hx-push-url="true" hx-target="#ad-list" hx-swap="innerHTML"
       class="text-sm text-blue-600 hover:underline">{% trans "Clear all filters" %}</a>
{% else %}
    <a href="?page=1{% if LANGUAGE_CODE %}&lang={{ LANGUAGE_CODE }}{% endif %}"
       hx-get="?page=1{% if LANGUAGE_CODE %}&lang={{ LANGUAGE_CODE }}{% endif %}"
       hx-push-url="true" hx-target="#ad-list" hx-swap="innerHTML"
       class="text-sm text-blue-600 hover:underline">{% trans "Clear all filters" %}</a>
{% endif %}
```

**Should `"query": None` be added to listings.py context?** **Yes — recommended (1-line, no behavioral change).** Rationale:
- It makes the two views' context shapes **identical** and the partial's contract **explicit** — any template author can rely on `query` being present (even if falsy) on both render paths. This is the single-reason-to-change that the spec T4 (L135) endorses: *"Affected files: … `listings.py` (export `query=None` for context consistency)."*
- Django treats `None` and an undefined variable identically in `{% if query %}` (both falsy), so this is **behavior-preserving**. No test should break solely from this line.
- Cost: one line (`"query": None,` in listings.py L447–467). Risk: negligible.

**Test impact (T7):** `test_clear_all_filters_has_push_url` (test_catalog_filters.py L665–687) currently asserts `q` is absent from the clear-all reset URL (L684–685: `assert "&q=" not in reset_url`). After T4, this assertion is **wrong for the search page** — on `/search/?q=…`, clear-all *must* retain `q`. The test must be split/parameterized: one assertion for listings (q absent) and one for search (q present). This is explicitly called out in the spec (T4 L136 / T7 L169).

---

## 4. DRY analysis: Can a template tag reduce the 9× URL duplication?

### Finding: Django 5.2 ships a built-in `{% querystring %}` tag

Verified against the Django 5.2.5 source (`django/template/defaulttags.py`):

```python
@register.simple_tag(name="querystring", takes_context=True)
def querystring(context, query_dict=None, **kwargs):
    if query_dict is None:
        query_dict = context.request.GET
    params = query_dict.copy()
    for key, value in kwargs.items():
        if value is None:
            if key in params:
                del params[key]            # removes the ENTIRE key
        elif isinstance(value, Iterable) and not isinstance(value, str):
            params.setlist(key, value)     # replaces the whole list
        else:
            params[key] = value
    ...
    return f"?{query_dict.urlencode()}"
```

Capabilities:
- `{% querystring page=3 %}` → set/replace `page`, keep everything else. ✔
- `{% querystring listing_purpose=None %}` → **delete** the `listing_purpose` key entirely. ✔
- `{% querystring features=[a,b,c] %}` → `setlist` (replace the whole list). ✔

### Why it's a *partial* DRY, not a full one

| Link type | Could `{% querystring %}` replace the inline URL? | Gap |
|---|---|---|
| **Pagination** (5 links: «« « N » »») | ✅ `{% querystring page=N %}` | none |
| **Purpose chip ×** | ✅ `{% querystring listing_purpose=None page=1 %}` | none |
| **Condition chip ×** | ✅ `{% querystring condition=None page=1 %}` | none |
| **Feature chip ×** | ❌ | Need to remove ONE value from a multi-valued `features` list. `{% querystring features=None %}` deletes *all* features; `{% querystring features=[list] %}` *replaces* the list — both require pre-computing the filtered list in the template (no loop/filter support). The built-in cannot drop a single `QueryDict` value cleanly. |
| **Clear-all** | ⚠ partial | `{% querystring q=None sort=None min_price=None max_price=None listing_purpose=None condition=None features=None page=1 %}` works but is verbose; `lang` is preserved from `request.GET` automatically, but the existing code *always* appends `&lang={{ LANGUAGE_CODE }}` even when `lang` isn't in the URL yet — a behavioral subtlety. |
| **Price-chip ×** (new, T3) | ❌ | Same multi-value problem does not apply, but price needs to drop `min_price`+`max_price`; `{% querystring min_price=None max_price=None page=1 %}` would work **here**. |

### Bottom line

- The built-in `{% querystring %}` could cleanly replace the **5 pagination** links and the **purpose** + **condition** chip removals (7 of 9).
- It **cannot** cleanly handle the **feature-chip** removal (single-value-from-list deletion) or the **clear-all** (drop-everything, with the `lang`-always-append subtlety) — those need either a custom tag or the existing hand-written approach.
- The project already has a **custom** `query_replace` tag (dict_tags.py L46–70) that **only sets params** (no `None`-removal) and has exactly **one** consumer (`language_switcher.html` L35). It predates/duplicates the built-in and is strictly inferior. This is a latent DRY smell.

**Recommendation:** Do **not** attempt the DRY refactor as part of T1–T4. The spec explicitly rules out "full filter architecture refactor (e.g., … consolidating the 18 inline URL constructions)" (filter-regression_spec.md L270). Bundling a `querystring` migration into T1–T4 would (a) exceed scope, (b) require re-validating the `lang`-always-append behavior and the feature-chip single-value case (which needs a *new* custom tag, e.g. `filter_query_drop key=value`), and (c) force updating `test_all_htmx_links_have_push_url` (hard-count 9) and `test_lang_param_in_all_htmx_urls` (≥18) anyway.

**Recommended follow-up task (out of scope here):** Introduce a single custom tag — e.g. extend `query_replace` (or replace it with the built-in `querystring`) plus a `query_drop` helper for single-value-from-list removal — and consolidate all 9 (+1 price-chip) inline expressions into `{% querystring page=N %}` / `{% query_drop features=f.slug page=1 %}` / clear-all forms. This would (i) eliminate the 9× duplication, (ii) subsume the single-use `query_replace` tag, and (iii) turn the hard-count tests into structural assertions. Defer per spec "No structural change."

---

## 5. Test impact summary (for T7)

| Test (test_catalog_filters.py) | Current assertion | Required change after T1–T4 |
|---|---|---|
| `test_all_htmx_links_have_push_url` (L647) | `hx-get=` == 9; `hx-push-url="true"` == 9 | → **10** (price chip adds 1 of each) |
| `test_lang_param_in_all_htmx_urls` (L656) | `LANGUAGE_CODE` occurrences ≥ 18 (9×2) | → **≥ 20** (10×2) |
| `test_clear_all_filters_has_push_url` (L665) | Asserts `q`/`sort` **absent** from clear-all reset URL; asserts presence of `hx-push-url`; does **not** check visibility guard | **Must be split/parameterized**: (a) assert clear-all is **inside** the chips `{% if %}` (hidden when no chips); (b) on search path, assert `q` **present** in reset URL; (c) on listings path, assert `q` **absent**. The current L684–685 (`&q=` not in reset_url) directly encodes the *spec-deviant* behavior and must be relaxed for the search case. |
| New (add) | — | Assert: price-only active → chips container + clear-all render; no filters active → neither renders; price-chip removal URL omits `min_price`/`max_price` only. |

---

## 6. Decisions requiring no second verification pass

- **Extend the inline `{% if %}` (not a bool var):** unambiguous — PO chosen, rule #7, single use-site. ✔
- **Reuse `{% blocktrans with min=… max=… %}` for the price label:** unambiguous — msgids already extracted; `{% trans %}` can't interpolate variables; matches 11 existing usages. ✔
- **Branch clear-all on `{% if query %}` + add `"query": None` to listings.py:** unambiguous — `query` is already the page discriminator; `None` is behavior-preserving in `{% if %}`; spec T4 endorses. ✔
- **Decimal (display) vs. str (URL) duality:** not a defect — consistent with every other param. No change. ✔

The **only** genuinely ambiguous design choice is T6 (language-switcher staleness — move header inside the swap target vs. JS `htmx:afterSwap` rewrite), which is **explicitly deferred** in `.ai/problems/05_filter-regression_spec.md` (L258, Q1 in §10) pending a PO decision. That is outside the T1–T4 scope of this brief and is not revisited here.

No second verification pass is required for T1–T4. The `querystring`-tag DRY refactor is the one item with real trade-offs (partial coverage, `lang` subtlety, test-count breakage) and is recommended as a **separate, deferred** task per the spec's "no structural change" constraint.
