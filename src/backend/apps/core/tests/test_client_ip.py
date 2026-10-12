"""Behavioural tests for the shared trusted client-IP resolver.

These verify the *trust decision* and key agreement, which is all a unit test
can observe: Django's test client is not proxy-aware (it hard-codes
``REMOTE_ADDR="127.0.0.1"`` and emits no forwarded headers), so nothing here
asserts anything about nginx.
"""

from __future__ import annotations

import ipaddress

import pytest
from django.http import HttpRequest
from django.test import override_settings

from apps.core.utils.client_ip import _is_trusted_peer, get_client_ip

# `override_settings(TRUSTED_PROXY_NETWORKS=...)` below is why most of these are
# django_db-free: they touch only request metadata and cache. The one exception
# is `TestConsumerAgreement`, which additionally exercises `record_consent_action`
# and therefore carries `django_db`.
# Genuinely public addresses: `203.0.113.0/24`, `198.51.100.0/24` and
# `192.0.2.0/24` are reserved TEST-NET ranges and report ``is_private is True``
# in Python 3.13+, which would make them look like trusted peers.
_UNTRUSTED_PEER = "1.2.3.4"
_SPOOF_A = "8.8.8.8"
_SPOOF_B = "9.9.9.9"
_TRUSTED_NETWORK = ("10.0.0.0/8",)

pytestmark = [pytest.mark.unit]


class _SessionStub:
    """Minimal session exposing only what ``record_consent_action`` reads."""

    def __init__(self, values: dict[str, str]) -> None:
        self._values = values

    def __getattr__(self, name: str) -> str | None:
        return self._values.get(name)


def _request(meta: dict[str, str]) -> HttpRequest:
    request = HttpRequest()
    request.META = dict(meta)
    return request


class TestPublicPeerCannotSpoof:
    """A public peer outside every listed network cannot have its headers read.

    The guarantee is *no public peer is trusted unless an operator explicitly
    lists a network containing it* — not that public peers are always untrusted.
    These tests run under the default ``TRUSTED_PROXY_NETWORKS = ()``, so the
    peer stays untrusted; an operator listing a network containing the peer
    would honour its headers by design.
    """

    def test_public_peer_ignores_x_forwarded_for(self) -> None:
        """X-Forwarded-For on an untrusted peer yields the same key as no header."""
        bare = get_client_ip(_request({"REMOTE_ADDR": _UNTRUSTED_PEER}))
        spoofed = get_client_ip(
            _request(
                {
                    "REMOTE_ADDR": _UNTRUSTED_PEER,
                    "HTTP_X_FORWARDED_FOR": _SPOOF_A,
                }
            )
        )
        assert spoofed == bare == _UNTRUSTED_PEER

    def test_public_peer_ignores_x_real_ip(self) -> None:
        """X-Real-IP on an untrusted peer yields the same key as no header."""
        bare = get_client_ip(_request({"REMOTE_ADDR": _UNTRUSTED_PEER}))
        spoofed = get_client_ip(
            _request(
                {
                    "REMOTE_ADDR": _UNTRUSTED_PEER,
                    "HTTP_X_REAL_IP": _SPOOF_A,
                }
            )
        )
        assert spoofed == bare == _UNTRUSTED_PEER


class TestTrustedPeerHeaderHandling:
    """When the gate is open, headers are honoured with a fixed precedence."""

    def test_trusted_peer_honours_x_real_ip(self) -> None:
        """A trusted (private) peer's X-Real-IP is returned canonically."""
        result = get_client_ip(
            _request(
                {
                    "REMOTE_ADDR": "10.0.0.4",
                    "HTTP_X_REAL_IP": "203.0.113.20",
                }
            )
        )
        assert result == "203.0.113.20"

    def test_x_real_ip_outranks_x_forwarded_for(self) -> None:
        """X-Real-IP wins over X-Forwarded-For when both are present."""
        result = get_client_ip(
            _request(
                {
                    "REMOTE_ADDR": "10.0.0.4",
                    "HTTP_X_REAL_IP": "203.0.113.20",
                    "HTTP_X_FORWARDED_FOR": _SPOOF_A,
                }
            )
        )
        assert result == "203.0.113.20"

    def test_forwarded_for_walk_returns_real_client(self) -> None:
        """Right-to-left walk skips the attacker prefix and the private proxy hop."""
        # `$proxy_add_x_forwarded_for` appends: client-added prefix is leftmost.
        result = get_client_ip(
            _request(
                {
                    "REMOTE_ADDR": "10.0.0.4",
                    "HTTP_X_FORWARDED_FOR": f"{_SPOOF_A}, {_SPOOF_B}, 10.0.0.4",
                }
            )
        )
        assert result == _SPOOF_B


class TestDegradedInput:
    """Malformed and absent metadata never raise."""

    def test_malformed_header_falls_back_to_peer(self) -> None:
        """An unparseable X-Real-IP falls back to the socket peer."""
        result = get_client_ip(
            _request(
                {
                    "REMOTE_ADDR": "10.0.0.4",
                    "HTTP_X_REAL_IP": "not-an-ip",
                }
            )
        )
        assert result == "10.0.0.4"

    def test_empty_meta_returns_unknown(self) -> None:
        """A bare HttpRequest has no REMOTE_ADDR and must not raise KeyError."""
        assert get_client_ip(HttpRequest()) == "unknown"


class TestKeyStability:
    """Canonicalisation keeps equivalent spellings in one bucket."""

    def test_ipv6_spellings_share_one_key(self) -> None:
        """Two spellings of one IPv6 address produce one rate-limit key."""
        expanded = get_client_ip(_request({"REMOTE_ADDR": "2001:0db8:0000:0000:0000:0000:0000:0001"}))
        compressed = get_client_ip(_request({"REMOTE_ADDR": "2001:db8::1"}))
        assert expanded == compressed


class TestIsTrustedPeer:
    """Direct unit tests for the peer-trust gate (``_is_trusted_peer``).

    These exercise the private decision function in isolation — no request
    metadata, no forwarded-header parsing — so the trust boundary itself is
    pinned independently of ``get_client_ip``'s precedence rules.
    """

    def test_ipv6_loopback_is_trusted(self) -> None:
        """IPv6 loopback (``::1``) is always trusted via ``is_loopback``."""
        assert _is_trusted_peer(ipaddress.ip_address("::1")) is True

    def test_ipv4_mapped_ipv6_loopback_is_trusted(self) -> None:
        """IPv4-mapped IPv6 of a loopback address (``::ffff:127.0.0.1``) is trusted."""
        peer = ipaddress.ip_address("::ffff:127.0.0.1")
        assert peer.is_loopback is True
        assert _is_trusted_peer(peer) is True

    def test_public_address_without_listed_network_is_untrusted(self) -> None:
        """A public address outside every listed network is untrusted."""
        assert _is_trusted_peer(ipaddress.ip_address(_UNTRUSTED_PEER)) is False

    @override_settings(TRUSTED_PROXY_NETWORKS=(_TRUSTED_NETWORK,))
    def test_network_boundary_inclusive(self) -> None:
        """The exact last address of a listed network is still contained."""
        # 10.255.255.255 is the broadcast edge of 10.0.0.0/8 — within strict=False.
        assert (
            _is_trusted_peer(ipaddress.ip_address("10.255.255.255")) is True
        )

    @override_settings(TRUSTED_PROXY_NETWORKS=(_TRUSTED_NETWORK,))
    def test_just_outside_network_is_untrusted(self) -> None:
        """The first address outside a listed network is not contained."""
        # 11.0.0.0 is the first address outside 10.0.0.0/8.
        assert (
            _is_trusted_peer(ipaddress.ip_address("11.0.0.0")) is False
        )

    @override_settings(TRUSTED_PROXY_NETWORKS=(_TRUSTED_NETWORK,))
    def test_malformed_network_entry_is_skipped(self) -> None:
        """A non-network string in TRUSTED_PROXY_NETWORKS is skipped, not fatal.

        A typo in the operator setting must not raise and must not broaden trust
        beyond the valid networks alongside it.
        """
        with override_settings(
            TRUSTED_PROXY_NETWORKS=("not-a-network", *_TRUSTED_NETWORK)
        ):
            # Inside the valid network — still trusted.
            assert (
                _is_trusted_peer(ipaddress.ip_address("10.1.2.3")) is True
            )
            # Public and not in any valid network — untrusted.
            assert (
                _is_trusted_peer(ipaddress.ip_address(_UNTRUSTED_PEER))
                is False
            )


class TestIPv6PeerTrust:
    """IPv6 peers are handled correctly by the trust gate and header resolution.

    Covers the ``is_loopback`` / ``is_private`` fast-path for IPv6 and the
    ``TRUSTED_PROXY_NETWORKS`` listing path for a public IPv6 address that is
    not privately routed (Gap 4: no prior test exercised a real IPv6 peer).
    """

    def test_ipv6_loopback_peer_honours_x_real_ip(self) -> None:
        """IPv6 loopback (``::1``) opens the gate; ``X-Real-IP`` is honoured."""
        result = get_client_ip(
            _request(
                {
                    "REMOTE_ADDR": "::1",
                    "HTTP_X_REAL_IP": "2001:db8::42",
                }
            )
        )
        assert result == "2001:db8::42"

    @override_settings(TRUSTED_PROXY_NETWORKS=("fd00::/8",))
    def test_ipv6_ula_peer_from_listed_network(self) -> None:
        """A ULA address from a listed IPv6 network opens the gate.

        ``fd00::/8`` is a unique-local address; listing it explicitly exercises
        the ``TRUSTED_PROXY_NETWORKS`` read loop with an IPv6 network object.
        """
        result = get_client_ip(
            _request(
                {
                    "REMOTE_ADDR": "fd00::1",
                    "HTTP_X_REAL_IP": "2001:db8::42",
                }
            )
        )
        assert result == "2001:db8::42"

    @override_settings(TRUSTED_PROXY_NETWORKS=("2606:4700::/32",))
    def test_public_ipv6_peer_from_listed_network(self) -> None:
        """A public (non-private) IPv6 peer in a listed network is trusted.

        ``2606:4700:4700::1111`` is a real, publicly-routed address — it is
        neither loopback nor private, so it can only open the gate through the
        ``TRUSTED_PROXY_NETWORKS`` listing. This pins the IPv6 branch of the
        network-containment loop, which the IPv4 coverage cannot.
        """
        peer = "2606:4700:4700::1111"
        # Sanity: confirm this address is genuinely public (not private/loopback).
        addr = ipaddress.ip_address(peer)
        assert addr.is_private is False
        assert addr.is_loopback is False

        result = get_client_ip(
            _request(
                {
                    "REMOTE_ADDR": peer,
                    "HTTP_X_REAL_IP": "2001:db8::42",
                }
            )
        )
        assert result == "2001:db8::42"


class TestConsumerAgreement:
    """Every IP-keyed limiter buckets one request under the same key."""

    @pytest.mark.django_db
    def test_all_four_consumers_agree_on_one_key(self) -> None:
        """login, deep-link, search/autocomplete and consent recording share the IP."""
        from apps.core.enums import ConsentChoice
        from apps.core.services.contact_rate_limit import (
            check_deep_link_render_rate_limit,
        )
        from apps.search.services.rate_limit import rate_limit_check
        from apps.users.services.consent_record import record_consent_action
        from apps.users.services.login_rate_limit import login_rate_limit_check

        request = _request(
            {
                "REMOTE_ADDR": "10.0.0.4",
                "HTTP_X_REAL_IP": _SPOOF_A,
            }
        )
        request.session = _SessionStub({"session_key": "agreement-session"})
        from django.core.cache import cache

        cache.clear()
        assert login_rate_limit_check(request) is True
        assert check_deep_link_render_rate_limit(request) is True
        assert rate_limit_check(request, namespace="autocomplete") is True
        assert rate_limit_check(request, namespace="search") is True

        expected = get_client_ip(request)
        assert expected == _SPOOF_A
        assert cache.get(f"login_rl:{expected}") == 1
        assert cache.get(f"telegram_dl_rl:{expected}") == 1
        assert cache.get(f"autocomplete_rl:{expected}") == 1
        assert cache.get(f"search_rl:{expected}") == 1

        # The consent recorder's fourth client-IP read must resolve the same
        # value; it stores the anonymized form, so the last octet is zeroed.
        record = record_consent_action(
            None, ConsentChoice.ACCEPTED, {}, request=request
        )
        assert record.ip_address == "8.8.8.0"


class TestPublicPeerUntrustedUnlessOperatorListed:
    """A public peer is untrusted unless an operator lists a network containing it.

    The code guarantees *no public peer is trusted unless an operator explicitly
    lists a network that contains it* — not that public peers are always
    untrusted. ``TRUSTED_PROXY_NETWORKS = ("0.0.0.0/0",)`` would honour a public
    peer's headers, which is correct operator-configured behaviour.
    """

    @override_settings(TRUSTED_PROXY_NETWORKS=_TRUSTED_NETWORK)
    def test_public_peer_stays_untrusted_with_trusted_networks_set(self) -> None:
        """A public peer outside the listed networks is still refused a header read."""
        result = get_client_ip(
            _request(
                {
                    "REMOTE_ADDR": _UNTRUSTED_PEER,
                    "HTTP_X_REAL_IP": _SPOOF_A,
                    "HTTP_X_FORWARDED_FOR": _SPOOF_A,
                }
            )
        )
        assert result == _UNTRUSTED_PEER

    @override_settings(TRUSTED_PROXY_NETWORKS=_TRUSTED_NETWORK)
    def test_listed_private_network_is_trusted(self) -> None:
        """A private peer inside TRUSTED_PROXY_NETWORKS opens the gate.

        A private peer is already trusted via ``is_private``; this exercises the
        listed-network branch only for the mixed trust decision.
        """
        result = get_client_ip(
            _request(
                {
                    "REMOTE_ADDR": "10.1.2.3",
                    "HTTP_X_REAL_IP": _SPOOF_B,
                }
            )
        )
        assert result == _SPOOF_B

    @override_settings(TRUSTED_PROXY_NETWORKS=("1.2.3.0/24",))
    def test_listed_network_with_public_peer_opens_gate(self) -> None:
        """A non-private peer inside a listed network is trusted.

        ``1.2.3.4`` is genuinely public, so this can only open the gate through
        the ``TRUSTED_PROXY_NETWORKS`` read loop — a private peer would pass on
        ``is_private`` alone and give the setting zero coverage.
        """
        result = get_client_ip(
            _request(
                {
                    "REMOTE_ADDR": "1.2.3.4",
                    "HTTP_X_REAL_IP": _SPOOF_B,
                }
            )
        )
        assert result == _SPOOF_B


class TestTrustedNetworksCannotNarrowPeerTrust:
    """``TRUSTED_PROXY_NETWORKS`` is purely additive: it can never remove trust.

    ``_is_trusted_peer`` returns on ``is_loopback or is_private`` **before** it
    consults the setting, so a private peer outside every listed network stays
    trusted. This ordering is the only thing standing between a mis-set tuple
    and a site-wide login lockout: an operator who lists a network that does not
    contain nginx's peer must not thereby stop trusting the real reverse proxy,
    which would collapse every production client onto nginx's address.
    """

    @override_settings(TRUSTED_PROXY_NETWORKS=("192.168.1.0/24",))
    def test_trusted_networks_cannot_narrow_the_private_peer_trust(self) -> None:
        """A private peer OUTSIDE every listed network is still trusted."""
        result = get_client_ip(
            _request({"REMOTE_ADDR": "172.18.0.5", "HTTP_X_REAL_IP": _SPOOF_B})
        )
        assert result == _SPOOF_B
