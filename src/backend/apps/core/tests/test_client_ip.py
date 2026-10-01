"""Behavioural tests for the shared trusted client-IP resolver.

These verify the *trust decision* and key agreement, which is all a unit test
can observe: Django's test client is not proxy-aware (it hard-codes
``REMOTE_ADDR="127.0.0.1"`` and emits no forwarded headers), so nothing here
asserts anything about nginx.
"""

from __future__ import annotations

from django.http import HttpRequest
from django.test import override_settings

from apps.core.utils.client_ip import get_client_ip

# `override_settings(TRUSTED_PROXY_NETWORKS=...)` below is why these are
# django_db-free: no test touches the database, only request metadata and cache.
# Genuinely public addresses: `203.0.113.0/24`, `198.51.100.0/24` and
# `192.0.2.0/24` are reserved TEST-NET ranges and report ``is_private is True``
# in Python 3.13+, which would make them look like trusted peers.
_UNTRUSTED_PEER = "1.2.3.4"
_SPOOF_A = "8.8.8.8"
_SPOOF_B = "9.9.9.9"
_TRUSTED_NETWORK = ("10.0.0.0/8",)


def _request(meta: dict[str, str]) -> HttpRequest:
    request = HttpRequest()
    request.META = dict(meta)
    return request


class TestPublicPeerCannotSpoof:
    """A public peer's forwarding headers must never be read."""

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


class TestConsumerAgreement:
    """Every IP-keyed limiter buckets one request under the same key."""

    def test_all_four_consumers_agree_on_one_key(self) -> None:
        """login, deep-link, search and autocomplete share the resolved IP."""
        from apps.core.services.contact_rate_limit import (
            check_deep_link_render_rate_limit,
        )
        from apps.search.services.rate_limit import rate_limit_check
        from apps.users.services.login_rate_limit import login_rate_limit_check

        request = _request(
            {
                "REMOTE_ADDR": "10.0.0.4",
                "HTTP_X_REAL_IP": _SPOOF_A,
            }
        )
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
