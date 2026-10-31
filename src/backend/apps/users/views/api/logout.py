"""
JSON logout endpoint — ``POST /api/v1/auth/logout/`` (S3.3).

Gap 22 (plan §2.4 row 22). The JSON sibling of the HTML logout view
(:func:`apps.users.views.logout.logout_view`): it flushes the session with
``django.contrib.auth.logout`` exactly as the HTML view does, but answers
``204 No Content`` with an empty body (the API lifecycle-completing shape from
the plan row) instead of the HTML redirect.

Auth is session-only (``login_required_api``): an anonymous caller gets a 401
``unauthenticated`` problem (no ``WWW-Authenticate``) **before** the method gate,
so an anonymous ``POST`` is 401, not 405. An authenticated non-POST gets a 405
``method_not_allowed`` problem with ``Allow: POST``. The shared write rate limit
is checked first (``api_write`` / ``RateLimitBudget.API_WRITE``), answering a 429
``rate_limited`` problem with ``Retry-After`` when exhausted.

No CSRF exemption is applied — the middleware chain is used as-is; writes are
POST-only.
"""

import logging
from http import HTTPStatus
from typing import Final

from django.contrib.auth import logout
from django.http import HttpRequest, HttpResponse
from django.utils.functional import Promise
from django.utils.translation import gettext_lazy as _

from apps.core.utils.api_auth import TYPE_METHOD_NOT_ALLOWED, login_required_api
from apps.core.utils.problem import problem, rate_limited_problem
from apps.search.services.rate_limit import RateLimitBudget, rate_limit_check

logger = logging.getLogger(__name__)

# English msgid (cataloged in ``ru``/``bs``/``en`` in the stage i18n batch).
_DETAIL_METHOD_NOT_ALLOWED: Final[str | Promise] = _("Method not allowed.")

# The rate-limit namespace for every authenticated ``/api/v1/`` write.
_RATE_LIMIT_NAMESPACE: Final[str] = "api_write"

# The only allowed method for this write endpoint.
_ALLOWED_METHODS: Final[tuple[str, ...]] = ("POST",)


@login_required_api
def logout_api_view(request: HttpRequest) -> HttpResponse:
    """``POST /api/v1/auth/logout/`` — flush the session and answer 204.

    ``login_required_api`` refuses an anonymous caller with a 401 problem first;
    the view then applies the POST gate and the shared write rate limit before
    flushing the session, matching the HTML logout view's ``logout(request)``
    call. The response carries no body.
    """
    if request.method not in _ALLOWED_METHODS:
        response = problem(
            HTTPStatus.METHOD_NOT_ALLOWED,
            TYPE_METHOD_NOT_ALLOWED,
            _DETAIL_METHOD_NOT_ALLOWED,
        )
        response["Allow"] = ", ".join(_ALLOWED_METHODS)
        return response

    if not rate_limit_check(
        request,
        namespace=_RATE_LIMIT_NAMESPACE,
        budget=RateLimitBudget.API_WRITE,
    ):
        return rate_limited_problem(RateLimitBudget.API_WRITE)

    # Flush the session exactly as the HTML logout view does.
    logout(request)
    logger.info("User logged out via API")
    return HttpResponse(status=HTTPStatus.NO_CONTENT)


__all__ = ["logout_api_view"]
