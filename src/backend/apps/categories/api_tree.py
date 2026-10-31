"""
JSON category-tree endpoint — ``GET /api/v1/categories/``.

The machine-readable mirror of the header's "All Categories" dropdown
(``apps.core.context_processors.header_context`` ``root_categories`` + the HTMX
submenu partial rendered by :func:`apps.categories.views.category_submenu`). It
answers the full **active** category tree — parents with nested ``children`` —
so an agent can discover every navigable category in one request instead of
walking the lazy-loaded fragment endpoint level by level.

**SWR verdict honoured (plan S1.6 / auditor Check-5).** The JSON tree reads the
``Category`` models **directly**; it deliberately does **not** route through the
submenu fragment cache in ``apps.categories.views`` / ``apps.categories.cache``
(which stores *rendered* HTML fragments keyed by tree version + slug + locale).
The HTML fragment cache is an internal render-cache optimization, not the data
contract; the JSON surface queries the ORM itself so the payload can never serve
stale rendered fragments. For the same reason this endpoint does not import or
expose the fragment-cache tree version: that counter versions rendered fragments,
not the tree data, so publishing it here would falsely couple the JSON contract
to a render-cache seam.

Tree parity with the HTML menu is by construction: the same active-only filter
(``is_active=True`` at every level) and the same ``order_by("name")`` ordering the
header uses, so ``categories[].slug`` / nesting / order match what the menu
renders (pinned by ``test_categories_api.py``).

Rate limiting uses the shared single enforcement point ``rate_limit_check`` with
the dedicated ``API_PUBLIC_READ`` budget and the per-route ``api_categories``
namespace (R1/Q4); exhaustion is rendered as an RFC 9457 ``rate_limited``
problem with a ``Retry-After`` header, never a legacy bare/JSON 429.
"""

import logging
from typing import Any, Final

from django.http import HttpRequest, JsonResponse

from apps.categories.models import Category
from apps.core.enums import LanguageLocale, RateLimitBudget
from apps.core.utils.problem import rate_limited_problem
from apps.search.services.rate_limit import rate_limit_check

logger = logging.getLogger(__name__)

# The rate-limit namespace for this route. Distinct per ``/api/v1/`` read route
# so exhausting this counter never throttles another endpoint (plan Q4).
_RATE_LIMIT_NAMESPACE: Final[str] = "api_categories"


def categories_view(request: HttpRequest) -> JsonResponse:
    """Return the full active category tree as a JSON payload.

    The response is ``{"categories": [ <node>, ... ]}`` where each node is
    ``{"slug": ..., "name": ..., "children": [ <node>, ... ]}``. ``name`` is the
    localized name for the request locale (``?lang`` > cookie > ``Accept-Language``
    through the shared middleware chain) with the model's ``locale → ru → name``
    fallback chain, exactly as the HTML menu renders it via
    ``get_category_name``.
    """
    if not rate_limit_check(
        request,
        namespace=_RATE_LIMIT_NAMESPACE,
        budget=RateLimitBudget.API_PUBLIC_READ,
    ):
        return rate_limited_problem(RateLimitBudget.API_PUBLIC_READ)

    locale = LanguageLocale.from_code(
        request.LANGUAGE_CODE, fallback=LanguageLocale.RUSSIAN
    )
    # One query for every active category — the whole tree is assembled in
    # Python below, so there is no per-level N+1 (the HTML surface lazy-loads
    # one level per fragment request instead).
    active = list(Category.objects.filter(is_active=True).order_by("name"))

    return JsonResponse({"categories": _build_tree(active, locale)})


def _build_tree(
    active: list[Category], locale: LanguageLocale
) -> list[dict[str, Any]]:
    """Assemble the nested tree from a flat list of active categories.

    *active* arrives already ordered by ``name`` (the HTML menu's ordering), so
    every ``children`` array preserves that order without re-sorting.

    A category is reachable only through an **active** chain from a root: an
    active category whose parent is inactive (or itself absent from *active*) is
    dropped together with its subtree, mirroring the HTML menu, which never
    renders a child under an inactive/absent parent.
    """
    children_by_parent: dict[int | None, list[Category]] = {}
    for category in active:
        children_by_parent.setdefault(category.parent_id, []).append(category)

    def node(category: Category) -> dict[str, Any]:
        return {
            "slug": category.slug,
            "name": category.get_name(locale),
            "children": [
                node(child) for child in children_by_parent.get(category.id, [])
            ],
        }

    # Roots are the active categories with no parent. An active node under an
    # inactive/absent parent is unreachable and therefore omitted (its
    # ``parent_id`` never appears as a key of an included node).
    return [node(root) for root in children_by_parent.get(None, [])]


__all__ = ["categories_view"]
