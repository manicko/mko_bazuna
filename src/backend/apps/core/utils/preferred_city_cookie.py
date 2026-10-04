"""
``preferred_city`` cookie ownership: name, max-age, and the mirrored write/expire pair.

The cookie stores a buyer's preferred city slug for anonymous sessions (hybrid
persistence per Decision 018: authenticated buyers use the DB column). This module
owns the cookie's identity and attributes so every writer and eraser emits the
same shape; it deliberately imports only the standard library and ``django.http``
(no app imports) so both ``apps.search.views`` and ``apps.core.middleware`` can
depend on it without an inverted cross-app dependency.

Why the expiry is hand-rolled with ``set_cookie`` rather than ``delete_cookie``:
``HttpResponseBase.delete_cookie()`` exposes no ``secure`` parameter in Django 5.2,
so it cannot mirror the write's ``Secure`` flag. The only one-flag route back
through ``delete_cookie`` is ``samesite="none"``, which would make this
buyer-scoped preference cookie cross-site capable — a genuine security regression.
Emitting an already-expired ``Set-Cookie`` via ``set_cookie`` is therefore the only
correct mechanism, not a stylistic choice. ``SameSite=None`` is never emitted.
"""

from __future__ import annotations

from typing import Final

from django.http import HttpResponse

PREFERRED_CITY_COOKIE_NAME: Final[str] = "preferred_city"
PREFERRED_CITY_COOKIE_MAX_AGE: Final[int] = 365 * 24 * 60 * 60  # 1 year

# Epoch expiry used to schedule deletion; ``max_age=0`` is the operative signal,
# the past ``expires`` is the belt-and-braces for legacy user agents.
_EXPIRED_EXPIRES: Final[str] = "Thu, 01 Jan 1970 00:00:00 GMT"


def set_preferred_city_cookie(
    response: HttpResponse,
    value: str,
    *,
    secure: bool,
    max_age: int = PREFERRED_CITY_COOKIE_MAX_AGE,
) -> None:
    """Write the ``preferred_city`` cookie with the canonical attributes.

    Args:
        response: The response to attach the ``Set-Cookie`` to.
        value: The city slug to store.
        secure: Whether to mark the cookie ``Secure``. Callers pass
            ``request.is_secure()`` so the flag tracks the origin scheme.
        max_age: Cookie lifetime in seconds; defaults to one year.
    """
    response.set_cookie(
        PREFERRED_CITY_COOKIE_NAME,
        value,
        max_age=max_age,
        httponly=True,
        samesite="Lax",
        secure=secure,
        path="/",
    )


def expire_preferred_city_cookie(response: HttpResponse, *, secure: bool) -> None:
    """Delete the ``preferred_city`` cookie by emitting an expired ``Set-Cookie``.

    Mirrors :func:`set_preferred_city_cookie`'s attributes — ``path="/"``,
    ``httponly=True``, ``samesite="Lax"`` and ``secure`` — because
    ``delete_cookie()`` has no ``secure`` parameter in Django 5.2 and the only
    ``delete_cookie`` route that would set ``Secure`` (``samesite="none"``) would
    make the cookie cross-site capable. ``secure`` must be the same
    ``request.is_secure()`` value used on the write; a ``Set-Cookie`` carrying
    ``Secure`` is rejected outright on a non-secure origin, so hard-coding it
    would make the deletion inert on plain-HTTP origins (``dev``, ``test``).

    Args:
        response: The response to attach the expiry ``Set-Cookie`` to.
        secure: Whether the origin scheme is HTTPS; pass ``request.is_secure()``.
    """
    response.set_cookie(
        PREFERRED_CITY_COOKIE_NAME,
        value="",
        max_age=0,
        expires=_EXPIRED_EXPIRES,
        path="/",
        httponly=True,
        samesite="Lax",
        secure=secure,
    )
