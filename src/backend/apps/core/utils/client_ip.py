"""Trusted client-IP resolution shared by every IP-keyed rate limiter.

The socket peer (``REMOTE_ADDR``) is the only value a client cannot forge. Any
forwarding header is trustworthy only when the direct peer is a reverse proxy we
control, so this module resolves in two stages:

1. Peer gate — read ``REMOTE_ADDR``. When it is loopback, private, or inside
   ``settings.TRUSTED_PROXY_NETWORKS`` the gate is open and forwarded headers may
   be consulted; otherwise the peer is returned as-is and no header is read.
2. Header precedence (gate open only) — ``X-Real-IP`` first, then
   ``X-Forwarded-For`` walked right-to-left to the first non-private entry, then
   the socket peer.

Walking ``X-Forwarded-For`` right-to-left is what makes it safe against the
``$proxy_add_x_forwarded_for`` appending form, where an attacker-supplied prefix
appears left of the real client. ``X-Forwarded-For`` left of the real client is
never read.

The chosen value is validated with :mod:`ipaddress` for well-formedness only and
returned canonically, so two spellings of one IPv6 address share one rate-limit
bucket. Private and reserved addresses are deliberately accepted: refusing them
is the gate's job, and rejecting them here would change every dev/test key.
"""

from __future__ import annotations

import ipaddress
from typing import TYPE_CHECKING, Final

from django.conf import settings

if TYPE_CHECKING:
    from django.http import HttpRequest

_UNKNOWN: Final[str] = "unknown"


def _parse(value: str | None) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Parse a bare address string, returning ``None`` when it is not valid."""
    if not value:
        return None
    try:
        return ipaddress.ip_address(value.strip())
    except ValueError:
        return None


def _is_trusted_peer(peer: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True if the direct peer is a proxy we are allowed to trust."""
    if peer.is_loopback or peer.is_private:
        return True
    for network in settings.TRUSTED_PROXY_NETWORKS:
        try:
            if peer in ipaddress.ip_network(network, strict=False):
                return True
        except ValueError:
            continue
    return False


def get_client_ip(request: HttpRequest) -> str:
    """Resolve the client IP for rate-limit bucketing.

    Reads ``REMOTE_ADDR`` first and only consults forwarding headers when that
    peer is trusted (loopback, private, or listed in
    ``settings.TRUSTED_PROXY_NETWORKS``). When trusted, ``X-Real-IP`` wins;
    otherwise ``X-Forwarded-For`` is walked right-to-left to the first non-private
    entry, falling back to the socket peer. The result is returned in canonical
    form so equivalent spellings of one address share a bucket.

    Args:
        request: The incoming HTTP request.

    Returns:
        A canonical IP address string, or ``"unknown"`` when the peer is absent
        or unparseable.
    """
    peer = _parse(request.META.get("REMOTE_ADDR"))
    if peer is None:
        return _UNKNOWN

    if not _is_trusted_peer(peer):
        return str(peer)

    real_ip = _parse(request.META.get("HTTP_X_REAL_IP"))
    if real_ip is not None:
        return str(real_ip)

    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    for hop in reversed(forwarded.split(",")):
        candidate = _parse(hop)
        if candidate is not None and not candidate.is_private:
            return str(candidate)

    return str(peer)
