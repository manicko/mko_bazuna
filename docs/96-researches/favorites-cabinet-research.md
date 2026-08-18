---
id: favorites-cabinet-research
domain: agent
tags:
  - research
  - favorites
  - cabinet
  - htmx
related:
  - architecture
---

# Research: Favorites + Lightweight User Cabinet Hub

RESEARCH-ONLY report — no code changed. Consensus: unified User Cabinet
(Decision_017), moving from "seller cabinet" to "user cabinet".

## Verified Facts

1. No favorite entity exists; autocomplete/history confirm `enums.py:59-78` has
   no `AD_FAVORITED` either (a `DASHBOARD_VIEWED` enum exists but is unused —
   enums are defined speculatively; do not add new analytics event until a
   dashboard consumes it).
2. Ad-card markup lives in `templates/ads/partials/ad_list.html` (card footer,
   line ~53) and `templates/ads/detail.html` (near title, line ~45).
3. The project has **zero existing htmx-POST-with-CSRF precedent** — a global
   `<body hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'` is recommended.
4. `@login_required` issues a 302 that htmx blindly follows — so the favorite-
   toggle endpoint must **not** use `@login_required`; it should manually check
   auth and return either a login-prompt fragment (anonymous) or the swapped
   heart (authenticated).
5. The save-search modal `templates/search/partials/save_search_modal.html`
   references `{% url 'search:save-search' %}` and `search:list` which **do not
   exist** in `apps/search/urls.py` — it is dead/unwired.
6. Header/auth-aware nav already built (spec 12): `templates/components/header.html`.

## Recommendations

- **`AdFavorite` model** in `apps/ads/models.py` (follow SavedSearch conventions):
  `user` FK → User (`related_name="favorites"`), `ad` FK → Ad
  (`related_name="favorites"`), `created_at`; `UniqueConstraint(user, ad)`;
  `db_table="ad_favorites"`; index `(user_id, -created_at)`. Migration.
- **Heart component:** shared `components/favorite_heart.html` `{% include %}`
  branching on `user.is_authenticated`, `hx-post`, `hx-swap="outerHTML"`,
  `hx-target="this"`; placed in `ad_list.html` footer + `detail.html`.
- **Toggle view** (no `@login_required`): manual auth check → anonymous returns
  `components/login_prompt.html` fragment ("Войдите, чтобы сохранить" → redirects
  to `consent:login_issue` at `/login/issue/`); authenticated toggles via
  `get_or_create` / delete and returns the new heart button. POST-only + CSRF.
- **Favorites list:** `/cabinet/favorites/` queries `Ad.objects.filter(favorites__user=user)`
  (Ad instances so the `ad_list` partial renders) + empty state + remove.
- **New `apps/cabinet` app** (FBV + `views/` package + `urls.py`, mounted in
  `config/urls.py`): `/cabinet/` hub, `/cabinet/favorites/`,
  `/cabinet/saved-searches/`, `/cabinet/search-history/`, `/cabinet/settings/`
  (stub, Q9=A). Shared `components/cabinet_nav.html` `{% include %}`; reuse
  `components/header.html`. "Мои объявления" links to existing `/dashboard/`
  (no refactor, Q10=A).
- Saved-search web UI wiring: create view + `search:save-search` URL to make the
  modal live; list/manage/enable-disable/delete views behind the saved-searches
  cabinet section.
