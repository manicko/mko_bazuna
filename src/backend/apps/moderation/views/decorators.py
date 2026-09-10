"""
Shared decorators for moderation views.

Consolidates staff-required checks to avoid duplication across
template-based views and JSON API endpoints.
"""

import logging
from collections.abc import Callable
from functools import wraps

from django.http import Http404, HttpRequest, JsonResponse

logger = logging.getLogger(__name__)


def staff_required(
    view_func: Callable[..., object],
) -> Callable[..., object]:
    """Require staff or superuser access for template-based views.

    Raises Http404 for non-staff users to avoid leaking admin URLs.
    """

    @wraps(view_func)
    def wrapper(request: HttpRequest, *args: object, **kwargs: object) -> object:
        if not (request.user.is_staff or request.user.is_superuser):
            raise Http404("Not found")
        return view_func(request, *args, **kwargs)

    return wrapper


def staff_required_api(
    view_func: Callable[..., JsonResponse],
) -> Callable[..., JsonResponse]:
    """Require staff or superuser access for JSON API endpoints.

    Returns 401 (with WWW-Authenticate challenge) for unauthenticated requests,
    403 for authenticated-but-non-staff users, and 405 for wrong HTTP method.
    """

    @wraps(view_func)
    def wrapper(request: HttpRequest, *args: object, **kwargs: object) -> JsonResponse:
        if not request.user.is_authenticated:
            return JsonResponse(
                {"error": "Authentication required"},
                status=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not (request.user.is_staff or request.user.is_superuser):
            return JsonResponse({"error": "Staff access required"}, status=403)
        if request.method != "POST":
            return JsonResponse({"error": "POST required"}, status=405)
        return view_func(request, *args, **kwargs)

    return wrapper
