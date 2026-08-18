---
id: anonymous-history-research
domain: agent
tags:
  - research
  - search
  - sessions
related:
  - architecture
---

# Research: Anonymous Session-Scoped Search History

RESEARCH-ONLY report — no code changed. Consensus: anonymous (logged-out) users
get search history scoped to their browser session (Decision_017, Q6=A,
US-B12), surfaced in the search autocomplete.

## Verified Facts

1. `record_search_history` is currently a **no-op for anonymous users**
   (`apps/search/services/search_history.py:31-32` `if user_id is None: return`),
   and `search.py:128-129` gates history recording behind
   `request.user.is_authenticated`.
2. `autocomplete.py:62-64` calls `get_user_search_history(None)` which returns
   `[]` for anonymous users.
3. Django sessions are fully active (`base.py` INSTALLED_APPS + SessionMiddleware)
   with the default **`db` backend** (server-side `django_session`, 2-week expiry),
   already used in production for `django_language` (`language.py:118`).
4. Consent does not block anonymous session storage: `is_consent_given` returns
   true for anonymous users; search-query text is not PII; Decision_K allows
   anonymous browsing.

## Recommended Approach

**Option (a) — Django session store.** Store a deduplicated, capped-at-50 list
in `request.session["search_history"]`. No migration, no new table, no cleanup
sweep; the 2-week session expiry is the privacy retention policy.

- Extend `record_search_history(user_id, query, session=None)` and
  `get_user_search_history(user_id, limit, session=None)` to branch on
  `user_id is None` → session path; authenticated → DB path. Only one path runs
  per request.
- `views/search.py`: remove the `is_authenticated` guard; pass `request.session`.
- `views/autocomplete.py`: pass `request.session` for anonymous users.
- Update 4 tests asserting the old no-op (`test_autocomplete.py:220,338,365,521`),
  add session-path tests.

## Authenticated Cabinet Section (Q7=A)

New `views/cabinet_history.py` (authenticated view, `@login_required`) listing
`SearchHistory` for the user + POST "clear history" action; template reusing the
`header.html` pattern; URLs `/cabinet/search-history/` and `/clear/`. Anonymous
history is session-only and not shown in the cabinet.

## Risks

- **Session bloat:** ~5 KB (50 × 100-char queries) is negligible in `django_session`.
- **Merge ordering:** authenticated users get DB history, anonymous get session
  history; mutually exclusive by branch — no double-appearance.
- **Tests:** update, don't constrain production (project rule #2).
