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


@overload
def rate_limited_response(*, json: Literal[True] = True) -> JsonResponse: ...


@overload
def rate_limited_response(*, json: Literal[False]) -> HttpResponse: ...


def rate_limited_response(*, json: bool = True) -> HttpResponse:
    """Return the shared HTTP 429 refusal response.

    Args:
        json: When ``True`` (default) emit ``{"error": "rate_limit"}`` as a
            ``JsonResponse``. When ``False`` emit a bare ``HttpResponse`` with
            status 429 and an empty body (HTML routes that render a status page
            rather than a JSON payload).

    Returns:
        An HTTP 429 response in the requested shape.
    """
    if json:
        return JsonResponse({"error": RATE_LIMIT_ERROR}, status=429)
    return HttpResponse(status=429)
