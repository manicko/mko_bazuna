"""
JSON cities endpoint — ``GET /api/v1/cities/``.

The machine-readable mirror of the header city selector
(``apps.core.context_processors.header_context`` ``cities``): it exposes the same
city set the header dropdown surfaces, in the same ``order_by("name")`` order
the context processor uses, so an agent can resolve city slugs without scraping
the rendered header.

The declared mirror is ``apps.core.context_processors`` (plan §2.3 pairing-table
note): the context processor's city query is the HTML consumer of the
``locations`` models, and this module imports the ``locations`` models **only**
(plus the shared ``/api/v1/`` helpers), exactly the import surface the mirror
publishes.

Rate limiting uses the shared single enforcement point ``rate_limit_check`` with
the dedicated ``API_PUBLIC_READ`` budget and the per-route ``api_cities``
namespace (R1/Q4); exhaustion is rendered as an RFC 9457 ``rate_limited`` problem
with a ``Retry-After`` header, never a legacy bare/JSON 429.
"""

import logging
from typing import Any, Final

from django.http import HttpRequest, JsonResponse

from apps.core.enums import LanguageLocale, RateLimitBudget
from apps.core.utils.problem import rate_limited_problem
from apps.locations.models import City
from apps.search.services.rate_limit import rate_limit_check

logger = logging.getLogger(__name__)

# The rate-limit namespace for this route. Distinct per ``/api/v1/`` read route
# so exhausting this counter never throttles another endpoint (plan Q4).
_RATE_LIMIT_NAMESPACE: Final[str] = "api_cities"


def cities_view(request: HttpRequest) -> JsonResponse:
    """Return the city list as a JSON payload.

    The response is ``{"cities": [ <city>, ... ]}`` where each city is
    ``{"slug": ..., "name": ..., "region": ..., "country_code": ...}``. ``name``
    is the localized name for the request locale with the model's
    ``locale → ru → name`` fallback chain, exactly as the header renders it via
    ``get_city_name``.
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
    cities = City.objects.order_by("name")

    return JsonResponse(
        {"cities": [_serialize_city(city, locale) for city in cities]}
    )


def _serialize_city(city: City, locale: LanguageLocale) -> dict[str, Any]:
    """Serialize one city into the stable JSON shape (D4).

    Keys are stable. ``region`` and ``country_code`` come from the same row the
    header query already loads and give agents the administrative context they
    need to disambiguate identically named cities; the header itself renders only
    the localized ``name``.
    """
    return {
        "slug": city.slug,
        "name": city.get_name(locale),
        "region": city.region,
        "country_code": city.country_code,
    }


__all__ = ["cities_view"]
