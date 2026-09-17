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

from apps.core.enums import ConsentChoice, CookieCategory
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
    consent_version: str = "1.0",
) -> ConsentRecord:
    """Create a ``ConsentRecord`` for a consent action.

    ``user`` may be ``None`` for anonymous cookie-based consent; an anonymous
    record is identified by the request's ``session_key`` instead.

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
        session_key = request.session.session_key
        ip_address = _anonymize_ip(request.META.get("REMOTE_ADDR") or None)
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
