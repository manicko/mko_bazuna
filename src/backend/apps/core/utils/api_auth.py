"""
Session-auth decorators for the ``/api/v1/`` surface.

``login_required_api`` is the session-credential mirror of
``staff_required_api`` (``apps/moderation/views/decorators.py``): an anonymous
request is refused with an RFC 9457 problem document instead of a login
redirect, and the refusal carries **no** ``WWW-Authenticate`` header. The
Django session cookie is the only non-staff credential this project accepts, so
a ``Bearer`` challenge would name a scheme the server cannot satisfy and send a
generic client into a retry loop for a token that does not exist (09-API-010).

``staff_required_api_problem`` is the RFC 9457 **problem-document** staff gate
for the ``/api/v1/`` reads (and, later, writes): the legacy
``staff_required_api`` is POST-only and emits a plain ``{"error": ...}`` body, so
it cannot serve a GET read that must answer 401/403/405 as problem documents.
The legacy decorator is intentionally left untouched; this module adds the
``/api/v1/`` variant alongside ``login_required_api``.

Both decorators keep the branch ordering of the frozen decorator: identity
before method — an anonymous ``POST`` gets 401, not 405. Phase 15 owns any
reorder of that branch ordering — this module deliberately does not change it.
"""

import logging
from collections.abc import Callable, Iterable
from functools import wraps
from http import HTTPStatus
from typing import overload

from django.http import HttpRequest, JsonResponse
from django.utils.translation import gettext as _

from apps.core.enums import UserRole
from apps.core.utils.problem import problem

logger = logging.getLogger(__name__)

# Stable ASCII token for the 401 refusal (never translated).
TYPE_UNAUTHENTICATED: str = "unauthenticated"

# Stable ASCII token for the 403 staff refusal (never translated).
TYPE_FORBIDDEN: str = "forbidden"

# Stable ASCII token for the 405 wrong-method refusal (never translated).
TYPE_METHOD_NOT_ALLOWED: str = "method_not_allowed"


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
                _("Authentication required."),
            )
        return view_func(request, *args, **kwargs)

    return wrapper


@overload
def staff_required_api_problem(
    view_func: Callable[..., JsonResponse],
) -> Callable[..., JsonResponse]: ...


@overload
def staff_required_api_problem(
    view_func: None = None,
    *,
    methods: Iterable[str] = ("GET",),
) -> Callable[[Callable[..., JsonResponse]], Callable[..., JsonResponse]]: ...


def staff_required_api_problem(
    view_func: Callable[..., JsonResponse] | None = None,
    *,
    methods: Iterable[str] = ("GET",),
) -> (
    Callable[..., JsonResponse]
    | Callable[[Callable[..., JsonResponse]], Callable[..., JsonResponse]]
):
    """Require a staff session **and** an allowed method, as problem documents.

    The RFC 9457 problem-document variant of the frozen ``staff_required_api``
    (``apps/moderation/views/decorators.py``) for the ``/api/v1/`` surface. The
    legacy decorator is POST-only and emits a plain ``{"error": ...}`` body, so
    it cannot serve the GET reads that must answer with ``application/problem+json``;
    this helper supplies the same identity discipline with problem documents.

    Semantics (branch order is identity **before** method, mirroring the frozen
    decorator, incl. the phase-15 reorder note):

    - anonymous → 401 problem (``type="unauthenticated"``), **no**
      ``WWW-Authenticate`` (09-API-010: the session cookie is the only
      credential, so a ``Bearer`` challenge would name an unsatisfiable scheme);
    - authenticated non-staff (``request.user.role != UserRole.ADMIN``) → 403
      problem (``type="forbidden"``), **no** ``WWW-Authenticate``;
    - wrong method (not in *methods*) → 405 problem
      (``type="method_not_allowed"``) with an ``Allow`` header naming the
      allowed methods.

    The credential is the **same** session cookie — this adds no new scheme.

    Usable bare (``@staff_required_api_problem``, defaulting to GET) or with
    parameters (``@staff_required_api_problem(methods=("POST",))``).

    Args:
        view_func: The wrapped view (supplied automatically in bare usage).
        methods: The HTTP methods the endpoint accepts; anything else is a 405.

    Returns:
        The decorated view (bare usage) or a decorator (parameterised usage).
    """
    allowed = tuple(methods)

    def decorator(
        inner: Callable[..., JsonResponse],
    ) -> Callable[..., JsonResponse]:
        @wraps(inner)
        def wrapper(
            request: HttpRequest, *args: object, **kwargs: object
        ) -> JsonResponse:
            # Identity before method: anonymous POST must be 401, not 405.
            # Deliberately no ``WWW-Authenticate`` (09-API-010); phase 15 owns
            # any reorder of the identity/method branches.
            if not request.user.is_authenticated:
                return problem(
                    HTTPStatus.UNAUTHORIZED,
                    TYPE_UNAUTHENTICATED,
                    _("Authentication required."),
                )
            if request.user.role != UserRole.ADMIN:
                return problem(
                    HTTPStatus.FORBIDDEN,
                    TYPE_FORBIDDEN,
                    _("Staff access required."),
                )
            if request.method not in allowed:
                response = problem(
                    HTTPStatus.METHOD_NOT_ALLOWED,
                    TYPE_METHOD_NOT_ALLOWED,
                    _("Method not allowed."),
                )
                response["Allow"] = ", ".join(allowed)
                return response
            return inner(request, *args, **kwargs)

        return wrapper

    if view_func is not None:
        return decorator(view_func)
    return decorator


__all__ = [
    "TYPE_FORBIDDEN",
    "TYPE_METHOD_NOT_ALLOWED",
    "TYPE_UNAUTHENTICATED",
    "login_required_api",
    "staff_required_api_problem",
]
