"""
Consent audit-log recording service for Mko Bazuna.

Creates ``ConsentRecord`` rows on every consent action (accept / decline /
withdraw) for GDPR Article 7(1) accountability. HTTP-layer context (anonymized
IP, truncated user agent) lives here; domain state mutation stays in the
service layer (``deletion.py``).
"""

from __future__ import annotations

import ipaddress

from django.http import HttpRequest

from apps.core.enums import ConsentChoice, ConsentVersion, CookieCategory
from apps.core.utils.client_ip import get_client_ip
from apps.users.models import ConsentRecord, User


def _anonymize_ip(ip: str | None) -> str | None:
    """Zero out the last octet (IPv4) or mask to /64 prefix (IPv6).

    IPv4: the last octet is zeroed to avoid storing a full client address.
    IPv6: the address is truncated to its /64 network prefix
    (the lower 64 bits are zeroed, retaining only the routing prefix).
    """
    if not ip:
        return None
    if "." in ip:
        parts = ip.split(".")
        return ".".join(parts[:-1] + ["0"])
    packed = int(ipaddress.IPv6Address(ip))
    network_prefix = packed & (0xFFFFFFFFFFFFFFFF << 64)
    return str(ipaddress.IPv6Address(network_prefix))


def record_consent_action(
    user: User | None,
    choice: ConsentChoice,
    categories: dict[CookieCategory, bool],
    request: HttpRequest | None = None,
    consent_version: str = ConsentVersion.V1_0.value,
) -> ConsentRecord:
    """Create a ``ConsentRecord`` for a consent action.

    ``user`` may be ``None`` for anonymous cookie-based consent; an anonymous
    record is identified by the request's ``session_key`` instead. When the
    caller is anonymous and the request has no session yet, the session is
    created (the stored key is what makes the row attributable) — see the
    comment in the body.

    When ``request`` is ``None`` the action is recorded without HTTP-layer
    context (e.g. from the Telegram bot /start entry point). ``session_key``,
    ``ip_address`` and ``user_agent`` are left blank in that case.

    Args:
        user: The acting user, or ``None`` for anonymous visitors.
        choice: The ``ConsentChoice`` made (ACCEPTED / DECLINED / WITHDRAWN).
        categories: Map of ``CookieCategory`` to whether it was accepted.
        request: The HTTP request carrying the session, IP, and user agent.
            When ``None`` (bot entry point), HTTP-layer fields are blanked.
        consent_version: Banner version the user was shown.

    Returns:
        The newly created ``ConsentRecord``.
    """
    if request is not None:
        # An anonymous consent must be attributable. A ``session_key`` is the
        # sole identifier of an anonymous record (the ``search_fields`` entry on
        # ``ConsentRecordAdmin``), so a row written with a NULL key is not
        # evidence. Nothing on the anonymous consent path otherwise creates a
        # session — ``SESSION_ENGINE`` is the DB-backed default,
        # ``CSRF_USE_SESSIONS`` is unset (CSRF lives in a cookie), and the only
        # ``request.session`` write in ``src/backend`` is the authenticated
        # ``?lang=`` branch — so force the session into existence before the
        # read. ``request.session.create()`` mints and saves the key here;
        # setting ``session.modified`` instead would defer key creation to
        # ``SessionMiddleware.process_response``, which has already run by the
        # time the caller assigns ``response`` (06-PII-105).
        if user is None and request.session.session_key is None:
            request.session.create()
        session_key = request.session.session_key
        # `get_client_ip` returns the literal "unknown" when no usable peer
        # exists; `_anonymize_ip` cannot parse that and would raise. Map the
        # sentinel back to None so an absent peer stores a null IP instead of
        # 500-ing, matching the pre-04-AUT-003 `or None` semantics.
        resolved_ip = get_client_ip(request)
        ip_address = _anonymize_ip(None if resolved_ip == "unknown" else resolved_ip)
        user_agent = (request.META.get("HTTP_USER_AGENT") or "")[:500]
    else:
        session_key = None
        ip_address = None
        user_agent = ""

    return ConsentRecord.objects.create(
        user=user if user is not None and user.is_authenticated else None,
        session_key=session_key,
        consent_version=consent_version,
        choice=choice,
        categories=categories,
        ip_address=ip_address,
        user_agent=user_agent,
    )
