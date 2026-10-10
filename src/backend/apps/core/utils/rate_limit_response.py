"""
One 429 response shape for every application rate-limit refusal (08-SRCH-013).

JSON bodies are the literal ``{"error": "rate_limit"}``; HTML routes use the
bare-status form. Before this module the two shapes diverged on adjacent
anonymous routes (``/search/`` returned JSON while ``/`` returned an empty
body), so a caller could not treat the refusals uniformly.
"""

from typing import Final, Literal, overload

from django.http import HttpResponse, JsonResponse

# The literal body shared by every JSON 429 refusal. Not a user-visible string:
# it is a machine-readable field value, so it is not translated.
RATE_LIMIT_ERROR: Final[str] = "rate_limit"

# Header name used to signal how long the client should wait before retrying.
RETRY_AFTER_HEADER: Final[str] = "Retry-After"


@overload
def rate_limited_response(
    *, json: Literal[True] = True, retry_after: int | None = None, body: str | None = None
) -> JsonResponse: ...


@overload
def rate_limited_response(
    *, json: Literal[False], retry_after: int | None = None, body: str | None = None
) -> HttpResponse: ...


def rate_limited_response(
    *, json: bool = True, retry_after: int | None = None, body: str | None = None
) -> HttpResponse:
    """Return the shared HTTP 429 refusal response.

    Args:
        json: When ``True`` (default) emit ``{"error": "rate_limit"}`` as a
            ``JsonResponse``. When ``False`` emit a bare ``HttpResponse`` with
            status 429 and an empty body (HTML routes that render a status page
            rather than a JSON payload).
        retry_after: When given, sets the ``Retry-After`` header to the number
            of seconds (as a string) the client should wait before retrying.
        body: When given, overrides the response content with the provided
            string. Callers passing ``body`` should use ``json=False`` so the
            Content-Type remains ``text/html``; passing ``body`` with the
            default ``json=True`` shapes would replace the JSON payload while
            the Content-Type stays ``application/json``.

    Returns:
        An HTTP 429 response in the requested shape, with
        ``Cache-Control: no-store`` on every response.
    """
    if json:
        response: HttpResponse = JsonResponse({"error": RATE_LIMIT_ERROR}, status=429)
    else:
        response = HttpResponse(status=429)

    response["Cache-Control"] = "no-store"
    if retry_after is not None:
        response[RETRY_AFTER_HEADER] = str(retry_after)
    if body is not None:
        response.content = body
    return response
