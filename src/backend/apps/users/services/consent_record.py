"""
Consent audit-log recording service for Mko Bazuna.

Creates ``ConsentRecord`` rows on every consent action (accept / decline /
withdraw) for GDPR Article 7(1) accountability. HTTP-layer context (anonymized
IP, truncated user agent) lives here; domain state mutation stays in the
service layer (``deletion.py``).

``record_consent_action`` takes an ``HttpRequest`` and is the view-layer entry
point; ``record_consent_action_with_context`` takes already-resolved scalars and
is the entry point for every caller without a request (the domain layer, the
bot, management commands). The former delegates to the latter, so there is one
insertion path and one place where the IP and user agent are sanitized.
"""

from __future__ import annotations

import ipaddress

from django.http import HttpRequest

from apps.core.enums import ConsentChoice, ConsentVersion, CookieCategory
from apps.core.utils.client_ip import get_client_ip
from apps.users.models import ConsentRecord, User

# Categories recorded when consent is withdrawn. Only the two non-essential
# categories the withdrawal response clears are listed: ``ESSENTIAL`` is never
# consent-gated, so it has no place in a withdrawal record (rule 10).
WITHDRAWN_CATEGORIES: dict[CookieCategory, bool] = {
    CookieCategory.ANALYTICS: False,
    CookieCategory.PREFERENCES: False,
}


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


def anonymized_client_ip(request: HttpRequest) -> str | None:
    """Resolve a request's client IP and anonymize it, mapping absence to ``None``.

    The single owner of ``get_client_ip``'s ``"unknown"`` sentinel. That literal
    is not a parseable address (``IPv6Address("unknown")`` raises
    ``ValueError``), so it is mapped to ``None`` here rather than duplicated into
    every caller — ``_anonymize_ip`` then canonicalizes the real address or
    returns ``None`` for an absent peer.
    """
    resolved_ip = get_client_ip(request)
    return _anonymize_ip(None if resolved_ip == "unknown" else resolved_ip)


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
    if request is None:
        return record_consent_action_with_context(user, choice, categories)

    # An anonymous consent must be attributable. A ``session_key`` is the
    # sole identifier of an anonymous record (the ``search_fields`` entry on
    # ``ConsentRecordAdmin``), so a row written with a NULL key is not
    # evidence. Nothing on the anonymous consent path otherwise creates a
    # session — ``SESSION_ENGINE`` is the DB-backed default,
    # ``CSRF_USE_SESSIONS`` is unset (CSRF lives in a cookie), and the only
    # ``request.session`` write in ``src/backend`` is the authenticated
    # ``?lang=`` branch — so force the session into existence before the read.
    # ``request.session.create()`` mints and saves the key here; setting
    # ``session.modified`` instead would defer key creation to
    # ``SessionMiddleware.process_response``, which has already run by the
    # time the caller assigns ``response`` (06-PII-105).
    if user is None and request.session.session_key is None:
        request.session.create()

    return record_consent_action_with_context(
        user,
        choice,
        categories,
        ip_address=anonymized_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT") or "",
        session_key=request.session.session_key,
        consent_version=consent_version,
    )


def record_consent_action_with_context(
    user: User | None,
    choice: ConsentChoice,
    categories: dict[CookieCategory, bool],
    *,
    ip_address: str | None = None,
    user_agent: str | None = None,
    session_key: str | None = None,
    consent_version: str = ConsentVersion.V1_0.value,
) -> ConsentRecord:
    """Create a ``ConsentRecord`` from already-resolved request scalars.

    The public writer for every entry point that does not (and must not) hold an
    ``HttpRequest``: ``withdraw_consent`` in the domain layer, the Telegram bot,
    management commands, ``consent_hard_delete`` and the admin. Taking resolved
    values keeps ``django.http`` and the session/middleware graph out of every
    importer and makes the audit write testable without a request (rule 3).

    The IP and user agent are sanitized here, not by the caller: a future caller
    cannot persist a raw client IP, and both transforms are idempotent, so a
    pre-processed and an unprocessed caller store the same row. ``user`` is
    nullable for anonymous cookie-based consent, identified by ``session_key``.

    Args:
        user: The acting user, or ``None`` for anonymous visitors.
        choice: The ``ConsentChoice`` made (ACCEPTED / DECLINED / WITHDRAWN).
        categories: Map of ``CookieCategory`` to whether it was accepted.
        ip_address: Resolved client IP, or ``None``; anonymized before storage.
        user_agent: Raw User-Agent header, or ``None``; truncated to 500 chars.
        session_key: Session key identifying an anonymous consent action.
        consent_version: Banner version the user was shown.

    Returns:
        The newly created ``ConsentRecord``.
    """
    return ConsentRecord.objects.create(
        user=user if user is not None and user.is_authenticated else None,
        session_key=session_key,
        consent_version=consent_version,
        choice=choice,
        categories=categories,
        ip_address=_anonymize_ip(ip_address),
        user_agent=(user_agent or "")[:500],
    )
