"""
Structural tests for the shipped nginx sites (``nginx.conf`` and ``nginx.dev.conf``).

Asserts that every ``location`` block which should proxy to the Django web
service contains a ``proxy_pass`` directive — the /metrics endpoint was
previously missing ``proxy_pass``, so Prometheus format output was never served.

It also pins the client-IP trust-model invariant that ``apps/core/utils/client_ip.py``
relies on: every proxying location overwrites ``X-Real-IP`` with the socket peer,
no ``proxy_set_header`` forwards a client-controlled ``$http_*`` value, and any
``set_real_ip_from`` names a specific peer. ``B-09`` ships these tests only — it
changes no nginx configuration.

Follows the same pattern as test_deploy_workflow.py and test_compose_hardening.py:
string-level checks via Path.read_text(), no external Nginx parsing dependency,
repo-root resolution by searching upward for pyproject.toml.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

# Resolve repository root by searching upward for pyproject.toml.
# Robust to varying CWD in Docker (WORKDIR=/app or /app/src/backend) and
# local development (from repo root).
_ROOT = Path(__file__).resolve().parent
while not (_ROOT / "pyproject.toml").exists():
    _ROOT = _ROOT.parent

_NGINX_CONF = _ROOT / "docker" / "nginx" / "nginx.conf"

# Both shipped nginx sites must satisfy the client-IP trust invariant. The dev
# site has fewer locations (no /health/, /csp-report/ or = /metrics block), so
# every new assertion is written to be location-agnostic.
_PROXIED_CONFS = [
    pytest.param(_ROOT / "docker" / "nginx" / "nginx.conf", id="nginx.conf"),
    pytest.param(_ROOT / "docker" / "nginx" / "nginx.dev.conf", id="nginx.dev.conf"),
]


def _brace_block(lines: list[str], start: int) -> str:
    """Return the nginx block starting at ``lines[start]``, using brace depth.

    Counts ``{`` and ``}`` so nested blocks (e.g. ``types { ... }`` inside a
    ``location``) are handled. The opening line's braces seed the depth.
    """
    block: list[str] = [lines[start]]
    depth = lines[start].count("{") - lines[start].count("}")
    for line in lines[start + 1 :]:
        depth += line.count("{")
        depth -= line.count("}")
        block.append(line)
        if depth <= 0:
            break
    return "\n".join(block)


def _location_block(text: str, location_match: str) -> str:
    """Extract a nginx ``location`` block by its match string (e.g. ``= /metrics``).

    Matches the **first** line containing ``location_match``; callers must not
    introduce an earlier line containing that string elsewhere in the file.
    """
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if re.search(re.escape(location_match), line):
            return _brace_block(lines, i)
    return ""


def _iter_location_blocks(text: str) -> list[str]:
    """Return every ``location`` block in ``text`` as a brace-delimited string."""
    lines = text.split("\n")
    blocks: list[str] = []
    for i, line in enumerate(lines):
        if re.match(r"\s*location\b", line):
            blocks.append(_brace_block(lines, i))
    return blocks


def _proxied_locations(text: str) -> list[str]:
    """Return every ``location`` block that proxies to an upstream."""
    return [block for block in _iter_location_blocks(text) if "proxy_pass" in block]


def test_nginx_config_exists() -> None:
    """nginx.conf must exist at docker/nginx/nginx.conf."""
    assert _NGINX_CONF.exists(), (
        "docker/nginx/nginx.conf must exist"
    )


def test_nginx_metrics_has_proxy_pass() -> None:
    """The /metrics location block must have a proxy_pass directive.

    Every location block that proxies to the Django web service must include
    ``proxy_pass http://web:8000`` so the request is forwarded rather than
    served or dropped. The /metrics endpoint exposes Prometheus format output
    from django-prometheus and must be proxied inside the container, while the
    ``allow 127.0.0.1`` / ``deny all`` directives restrict external access.
    """
    text = _NGINX_CONF.read_text()
    block = _location_block(text, "= /metrics")
    assert block, "nginx.conf must define a `location = /metrics` block"
    assert "proxy_pass" in block, (
        "`location = /metrics` must have a `proxy_pass` directive so Prometheus "
        "format output from django-prometheus is served (was missing — /metrics "
        "returned only 403 from allow/deny without proxying)"
    )


def test_nginx_metrics_has_proxy_headers() -> None:
    """The /metrics location block must set standard proxy headers.

    Mirrors the /health/ location block pattern: Host, X-Real-IP,
    X-Forwarded-For, X-Forwarded-Proto.
    """
    text = _NGINX_CONF.read_text()
    block = _location_block(text, "= /metrics")
    assert block, "nginx.conf must define a `location = /metrics` block"
    for header in (
        "proxy_set_header Host",
        "proxy_set_header X-Real-IP",
        "proxy_set_header X-Forwarded-For",
        "proxy_set_header X-Forwarded-Proto",
    ):
        assert header in block, (
            f"`location = /metrics` must set `{header}` (matching /health/ pattern)"
        )


def test_nginx_metrics_restricted_to_localhost() -> None:
    """The /metrics location must still restrict access to localhost.

    The ``allow 127.0.0.1`` / ``deny all`` directives must be retained so that
    Prometheus (running on the host) is the only allowed client.
    """
    text = _NGINX_CONF.read_text()
    block = _location_block(text, "= /metrics")
    assert block, "nginx.conf must define a `location = /metrics` block"
    assert "allow 127.0.0.1" in block, "`location = /metrics` must allow 127.0.0.1"
    assert "deny all" in block, "`location = /metrics` must deny all other addresses"


@pytest.mark.parametrize("conf_path", _PROXIED_CONFS)
def test_proxied_locations_overwrite_x_real_ip(conf_path: Path) -> None:
    """Every proxying location must overwrite ``X-Real-IP`` with the socket peer.

    ``get_client_ip`` returns on ``HTTP_X_REAL_IP`` before it ever walks
    ``X-Forwarded-For``, so this directive is the production resolution path.
    Deleting it or repointing it at a client-controlled value silently reroutes
    every request to the weaker right-to-left walk. Asserts the invariant — the
    exact directive/value — not any surrounding directive set.
    """
    text = conf_path.read_text()
    proxied = _proxied_locations(text)
    assert proxied, f"{conf_path.name} must define at least one proxying location"
    for block in proxied:
        assert "proxy_set_header X-Real-IP $remote_addr;" in block, (
            f"{conf_path.name}: every proxying location must overwrite X-Real-IP "
            "with the socket peer (`proxy_set_header X-Real-IP $remote_addr;`), "
            "because get_client_ip returns on X-Real-IP before walking "
            "X-Forwarded-For"
        )


@pytest.mark.parametrize("conf_path", _PROXIED_CONFS)
def test_no_proxied_location_forwards_a_client_echo_variable(conf_path: Path) -> None:
    """No ``proxy_set_header`` may take its value from a client-supplied header.

    ``X-Real-IP $http_x_real_ip`` swaps a client-controlled *prefix* (the safe
    appending form) for a client-controlled *whole value*. Only
    ``proxy_set_header`` lines are scanned: ``log_format`` legitimately uses
    ``$http_x_forwarded_for`` and ``$http_user_agent``.
    """
    text = conf_path.read_text()
    offenders = [
        line.strip()
        for line in text.split("\n")
        if line.strip().startswith("proxy_set_header") and "$http_" in line
    ]
    assert not offenders, (
        f"{conf_path.name}: no proxy_set_header may forward a client-echo "
        f"variable ($http_*); found: {offenders}"
    )


@pytest.mark.parametrize("conf_path", _PROXIED_CONFS)
def test_real_ip_trust_is_never_wildcard(conf_path: Path) -> None:
    """Any ``set_real_ip_from`` must name a specific peer and pair with a header.

    nginx is the first hop, so there is no upstream proxy to trust:
    ``set_real_ip_from 0.0.0.0/0`` would make every client a trusted proxy,
    letting a client choose ``$remote_addr`` and — because ``limit_req_zone``
    keys on ``$binary_remote_addr`` — destroying the nginx rate limiting. The
    test asserts the invariant only: it does not require the directive to exist.
    """
    text = conf_path.read_text()
    set_from = [
        line.strip()
        for line in text.split("\n")
        if line.strip().startswith("set_real_ip_from")
    ]
    has_wildcard = any("/0" in line for line in set_from)
    assert not has_wildcard, (
        f"{conf_path.name}: `set_real_ip_from` must never use a wildcard "
        f"argument (e.g. 0.0.0.0/0); found: {set_from}"
    )
    has_real_ip_header = any(
        line.strip().startswith("real_ip_header") for line in text.split("\n")
    )
    assert not set_from or has_real_ip_header, (
        f"{conf_path.name}: a `set_real_ip_from` directive must be accompanied "
        "by an explicit `real_ip_header`"
    )
