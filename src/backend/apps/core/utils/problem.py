"""
RFC 9457 problem-document helper for the ``/api/v1/`` surface.

Every ``/api/v1/`` error is an RFC 9457 problem document served with the
``application/problem+json`` media type. This module is the single builder for
those documents so the shape cannot drift per view: endpoints call
:func:`problem`, :func:`validation_problem` or :func:`rate_limited_problem`
instead of hand-constructing a ``JsonResponse``.

Two fields carry a deliberate contract:

* ``type`` is a **stable ASCII token** (for example ``consent_required`` or
  ``rate_limited``). It is part of the machine contract and is **never
  translated**.
* ``detail`` is an **English** human-readable string. Its English text is the
  msgid cataloged in the ``ru`` / ``bs`` / ``en`` message catalogs in a later
  i18n batch; this module holds the plain English source text only.

The legacy 429 renderer (``apps/core/utils/rate_limit_response.py``) is NOT
touched by this module: legacy surfaces keep emitting their frozen shapes and
carry no ``Retry-After``. The ``Retry-After`` header for ``/api/v1/`` 429s is
derived here, from ``RateLimitBudget.period``.
"""

import logging
from http import HTTPStatus
from typing import TYPE_CHECKING, Final

from django.http import JsonResponse
from django.utils.functional import Promise
from django.utils.translation import gettext as _, gettext_lazy

from apps.core.utils.sanitize import pydantic_errors_json

if TYPE_CHECKING:
    from pydantic import ValidationError

    from apps.core.enums import RateLimitBudget

logger = logging.getLogger(__name__)

# RFC 9457 problem-document media type.
PROBLEM_CONTENT_TYPE: Final[str] = "application/problem+json"

# Header name used to signal how long the client should wait before retrying.
RETRY_AFTER_HEADER: Final[str] = "Retry-After"

# ``type`` values for the taxonomy members this helper mints directly. Other
# callers pass their own stable token to :func:`problem`.
TYPE_VALIDATION_FAILED: Final[str] = "validation_failed"
TYPE_RATE_LIMITED: Final[str] = "rate_limited"

# Short English titles keyed on the standard HTTP status. Each value is a
# ``gettext_lazy`` proxy so the msgid is cataloged from this module AND the
# title is resolved for the active request locale when the document renders.
# The title is a fallback presentation string; callers usually supply ``detail``
# as well.
_STATUS_TITLES: Final[dict[int, str | Promise]] = {
    HTTPStatus.BAD_REQUEST: gettext_lazy("Bad Request"),
    HTTPStatus.UNAUTHORIZED: gettext_lazy("Unauthorized"),
    HTTPStatus.FORBIDDEN: gettext_lazy("Forbidden"),
    HTTPStatus.NOT_FOUND: gettext_lazy("Not Found"),
    HTTPStatus.METHOD_NOT_ALLOWED: gettext_lazy("Method Not Allowed"),
    HTTPStatus.CONFLICT: gettext_lazy("Conflict"),
    HTTPStatus.UNPROCESSABLE_ENTITY: gettext_lazy("Unprocessable Entity"),
    HTTPStatus.TOO_MANY_REQUESTS: gettext_lazy("Too Many Requests"),
    HTTPStatus.SERVICE_UNAVAILABLE: gettext_lazy("Service Unavailable"),
    HTTPStatus.INTERNAL_SERVER_ERROR: gettext_lazy("Internal Server Error"),
}


def _title_for(status: int) -> str:
    """Return the short English title for an HTTP status.

    Falls back to the phrase for the status when the standard library knows it,
    otherwise to ``"Error"`` so an unusual status still yields a well-formed
    document.
    """
    known = _STATUS_TITLES.get(status)
    if known is not None:
        return str(known)
    try:
        return HTTPStatus(status).phrase
    except ValueError:
        return _("Error")


def _problem_response(
    status: int, body: dict[str, object]
) -> JsonResponse:
    """Build a ``JsonResponse`` carrying a problem-document body.

    The body dict is passed through ``JsonResponse``'s own serializer with
    ``safe=False`` disabled (the document is always a mapping), so the encoding
    matches every other JSON view in the project.
    """
    return JsonResponse(body, status=status, content_type=PROBLEM_CONTENT_TYPE)


def problem(status: int, type: str, detail: str) -> JsonResponse:
    """Build an RFC 9457 problem document as a JSON response.

    Args:
        status: The HTTP status code for the response.
        type: A stable ASCII token identifying the problem class (never
            translated).
        detail: An English human-readable explanation of this occurrence.

    Returns:
        A ``JsonResponse`` with HTTP status ``status``, content-type
        ``application/problem+json`` and a body containing ``type``, ``title``,
        ``status`` and ``detail``.
    """
    return _problem_response(
        status,
        {
            "type": type,
            "title": _title_for(status),
            "status": status,
            "detail": detail,
        },
    )


def validation_problem(exc: ValidationError) -> JsonResponse:
    """Build a 422 validation-failed problem from a Pydantic validation error.

    Wraps the existing ``pydantic_errors_json`` deposit rather than
    reimplementing the error formatting, so the ``errors`` payload matches the
    shipped ``api_bulk`` 422 shape exactly.

    Args:
        exc: The ``pydantic.ValidationError`` raised while validating a DTO.

    Returns:
        A 422 problem document whose ``errors`` key is
        ``pydantic_errors_json(exc)``.
    """
    status = HTTPStatus.UNPROCESSABLE_ENTITY
    return _problem_response(
        status,
        {
            "type": TYPE_VALIDATION_FAILED,
            "title": _title_for(status),
            "status": status,
            "detail": _("Request body failed validation."),
            "errors": pydantic_errors_json(exc),
        },
    )


def rate_limited_problem(budget: RateLimitBudget) -> JsonResponse:
    """Build a 429 rate-limited problem with a ``Retry-After`` header.

    The ``Retry-After`` value is the budget's whole window in seconds
    (``RateLimitBudget.period``), computed HERE and only here: the legacy
    renderer stays a pure formatter and legacy 429s keep emitting no
    ``Retry-After``.

    Args:
        budget: The ``RateLimitBudget`` member whose window drove the refusal.

    Returns:
        A 429 problem document carrying ``Retry-After: <budget.period>``.
    """
    status = HTTPStatus.TOO_MANY_REQUESTS
    response = _problem_response(
        status,
        {
            "type": TYPE_RATE_LIMITED,
            "title": _title_for(status),
            "status": status,
            "detail": _("Too many requests; retry after the indicated delay."),
        },
    )
    response[RETRY_AFTER_HEADER] = str(budget.period)
    return response


__all__ = [
    "PROBLEM_CONTENT_TYPE",
    "RETRY_AFTER_HEADER",
    "TYPE_RATE_LIMITED",
    "TYPE_VALIDATION_FAILED",
    "problem",
    "rate_limited_problem",
    "validation_problem",
]
