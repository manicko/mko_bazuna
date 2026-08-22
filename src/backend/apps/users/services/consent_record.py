"""
Consent audit-log recording service for Mko Bazuna.

Creates ``ConsentRecord`` rows on every consent action (accept / decline /
withdraw) for GDPR Article 7(1) accountability. HTTP-layer context (anonymized
IP, truncated user agent) lives here; domain state mutation stays in the
service layer (``deletion.py``).
"""

from __future__ import annotations

from django.http import HttpRequest

from apps.core.enums import ConsentChoice, CookieCategory
from apps.users.models import ConsentRecord, User


def _anonymize_ip(ip: str | None) -> str | None:
    """Zero out the last IPv4 octet to avoid storing a full client address.

    IPv6 addresses are returned unchanged (no reliable in-band masking).
    """
    if not ip:
        return None
    if "." in ip:
        parts = ip.split(".")
        return ".".join(parts[:-1] + ["0"])
    return ip


def record_consent_action(
    user: User | None,
    choice: ConsentChoice,
    categories: dict[CookieCategory, bool],
    request: HttpRequest,
    consent_version: str = "1.0",
) -> ConsentRecord:
    """Create a ``ConsentRecord`` for a consent action.

    ``user`` may be ``None`` for anonymous cookie-based consent; an anonymous
    record is identified by the request's ``session_key`` instead.

    Args:
        user: The acting user, or ``None`` for anonymous visitors.
        choice: The ``ConsentChoice`` made (ACCEPTED / DECLINED / WITHDRAWN).
        categories: Map of ``CookieCategory`` to whether it was accepted.
        request: The HTTP request carrying the session, IP, and user agent.
        consent_version: Banner version the user was shown.

    Returns:
        The newly created ``ConsentRecord``.
    """
    return ConsentRecord.objects.create(
        user=user if user is not None and user.is_authenticated else None,
        session_key=request.session.session_key,
        consent_version=consent_version,
        choice=choice,
        categories=categories,
        ip_address=_anonymize_ip(request.META.get("REMOTE_ADDR") or None),
        user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:500],
    )
