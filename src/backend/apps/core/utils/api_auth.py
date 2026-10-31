"""
Session-auth decorator for the ``/api/v1/`` surface.

``login_required_api`` is the session-credential mirror of
``staff_required_api`` (``apps/moderation/views/decorators.py``): an anonymous
request is refused with an RFC 9457 problem document instead of a login
redirect, and the refusal carries **no** ``WWW-Authenticate`` header. The
Django session cookie is the only non-staff credential this project accepts, so
a ``Bearer`` challenge would name a scheme the server cannot satisfy and send a
generic client into a retry loop for a token that does not exist (09-API-010).

The branch ordering is identity before method, exactly as ``staff_required_api``
does it: an anonymous ``POST`` gets 401, not 405. Phase 15 owns any reorder of
that branch ordering — this module deliberately does not change it.
"""

import logging
from collections.abc import Callable
from functools import wraps
from http import HTTPStatus

from django.http import HttpRequest, JsonResponse

from apps.core.utils.problem import problem

logger = logging.getLogger(__name__)

# Stable ASCII token for the 401 refusal (never translated).
TYPE_UNAUTHENTICATED: str = "unauthenticated"


def login_required_api(
    view_func: Callable[..., JsonResponse],
) -> Callable[..., JsonResponse]:
    """Require an authenticated session for a JSON API endpoint.

    An unauthenticated request is refused with a 401 RFC 9457 problem document
    (``type="unauthenticated"``) and **no** ``WWW-Authenticate`` header.

    The identity check runs before any method check, so an anonymous ``POST`` is
    a 401 rather than a 405 — mirroring ``staff_required_api`` exactly. Phase 15
    owns any reorder of this branch sequence.

    Applied as a decorator on the view function; ``functools.wraps`` preserves
    the wrapped view's signature and metadata.
    """

    @wraps(view_func)
    def wrapper(request: HttpRequest, *args: object, **kwargs: object) -> JsonResponse:
        if not request.user.is_authenticated:
            # Identity before method: anonymous POST must be 401, not 405.
            # Deliberately no ``WWW-Authenticate`` (09-API-010); phase 15 owns
            # any reorder of the identity/method branches.
            return problem(
                HTTPStatus.UNAUTHORIZED,
                TYPE_UNAUTHENTICATED,
                "Authentication required.",
            )
        return view_func(request, *args, **kwargs)

    return wrapper


__all__ = ["TYPE_UNAUTHENTICATED", "login_required_api"]
