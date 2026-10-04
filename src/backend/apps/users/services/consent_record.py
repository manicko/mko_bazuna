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

from apps.core.enums import (
    ConsentActionSource,
    ConsentChoice,
    ConsentVersion,
    CookieCategory,
)
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
    *,
    action_source: ConsentActionSource | None = None,
) -> ConsentRecord:
    """Create a ``ConsentRecord`` for a consent action.

    ``user`` may be ``None`` for anonymous cookie-based consent; an anonymous
    record is identified by the request's ``session_key`` instead. When the
    caller is anonymous and the request has no session yet, the session is
    created (the stored key is what makes the row attributable) — see the
    comment in the body.

    When ``request`` is ``None`` the action is recorded without HTTP-layer
    context (e.g. a management command or a future bot caller). ``session_key``,
    ``ip_address`` and ``user_agent`` are left blank in that case.

    ``action_source`` derivation (``06-NEW-02``): when not supplied it resolves
    to ``ANONYMOUS_WEB`` if ``user is None`` and ``SELF_SERVICE`` otherwise. Every
    caller of this function today is one of the two self-service web views, so
    the derivation is exact; a caller that is neither MUST pass ``action_source``
    explicitly. The parameter is optional and keyword-only on purpose: the
    four-argument positional shape and every existing call site are unchanged
    (BLOCK 8 and BLOCK 10 relied on that freeze).

    Args:
        user: The subject of the action, or ``None`` for anonymous visitors.
        choice: The ``ConsentChoice`` made (ACCEPTED / DECLINED / WITHDRAWN).
        categories: Map of ``CookieCategory`` to whether it was accepted.
        request: The HTTP request carrying the session, IP, and user agent.
            When ``None``, HTTP-layer fields are blanked.
        consent_version: Banner version the user was shown.
        action_source: Mechanism override; derived from ``user`` when omitted.

    Returns:
        The newly created ``ConsentRecord``.
    """
    resolved_source = action_source or (
        ConsentActionSource.ANONYMOUS_WEB
        if user is None
        else ConsentActionSource.SELF_SERVICE
    )

    if request is None:
        # Pre-existing defect, out of scope but recorded: this branch drops
        # ``consent_version`` when delegating. It is edited here only to forward
        # ``action_source``; the version drop is not fixed (06-NEW-02 residual).
        return record_consent_action_with_context(
            user, choice, categories, action_source=resolved_source
        )

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
        action_source=resolved_source,
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
    action_source: ConsentActionSource,
    initiated_by: User | None = None,
) -> ConsentRecord:
    """Create a ``ConsentRecord`` from already-resolved request scalars.

    The single insertion path for every entry point that does not (and must not)
    hold an ``HttpRequest``: ``withdraw_consent`` in the domain layer, the
    Telegram bot, management commands, ``consent_hard_delete`` and the admin.
    Taking resolved values keeps ``django.http`` and the session/middleware graph
    out of every importer and makes the audit write testable without a request
    (rule 3).

    The IP and user agent are sanitized here, not by the caller: a future caller
    cannot persist a raw client IP, and both transforms are idempotent, so a
    pre-processed and an unprocessed caller store the same row. ``user`` is
    nullable for anonymous cookie-based consent, identified by ``session_key``.

    Actor normalisation (``06-NEW-02``) lives here, beside the IP sanitisation, so
    no future writer can bypass it. The actor is recorded **only when it is not
    the subject**: storing the subject twice would duplicate the very ``user``
    link BLOCK 15 clears at 90 days, and that surviving copy would be the only
    remaining link from an anonymous decision to a live account — re-opening the
    sweep's own re-identification path. Invariant: ``initiated_by`` is not null
    only when it is a different row from ``user``. ``action_source`` is required
    keyword-only (no default) so a new caller cannot forget to classify itself.

    Args:
        user: The subject of the action, or ``None`` for anonymous visitors.
        choice: The ``ConsentChoice`` made (ACCEPTED / DECLINED / WITHDRAWN).
        categories: Map of ``CookieCategory`` to whether it was accepted.
        ip_address: Resolved client IP, or ``None``; anonymized before storage.
        user_agent: Raw User-Agent header, or ``None``; truncated to 500 chars.
        session_key: Session key identifying an anonymous consent action.
        consent_version: Banner version the user was shown.
        action_source: The mechanism that initiated the action (required).
        initiated_by: The acting account, or ``None``; recorded only when it is
            a different row from ``user``.

    Returns:
        The newly created ``ConsentRecord``.
    """
    # Actor normalisation (06-NEW-02): the actor is recorded only when it is NOT
    # the subject. Storing the subject twice would duplicate the very link
    # BLOCK 15 clears at 90 days, and that surviving copy would be the only
    # remaining link from an anonymous decision to a live account. Invariant:
    # initiated_by is not null only when it is a different row from user.
    actor = (
        initiated_by
        if initiated_by is not None
        and (user is None or initiated_by.pk != user.pk)
        else None
    )
    return ConsentRecord.objects.create(
        user=user if user is not None and user.is_authenticated else None,
        session_key=session_key,
        consent_version=consent_version,
        choice=choice,
        categories=categories,
        ip_address=_anonymize_ip(ip_address),
        user_agent=(user_agent or "")[:500],
        action_source=action_source,
        initiated_by=actor,
    )
