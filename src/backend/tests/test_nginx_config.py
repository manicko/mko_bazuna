"""
Structural tests for docker/nginx/nginx.conf.

Asserts that every ``location`` block which should proxy to the Django web
service contains a ``proxy_pass`` directive — the /metrics endpoint was
previously missing ``proxy_pass``, so Prometheus format output was never served.

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


def _location_block(text: str, location_match: str) -> str:
    """Extract a nginx ``location`` block by its match string (e.g. ``= /metrics``).

    Nginx blocks are delimited by braces; this function counts brace depth to
    find the closing ``}`` of the target ``location`` block, handling nested
    blocks (e.g. ``types { ... }`` inside a location).
    """
    lines = text.split("\n")
    start = None
    for i, line in enumerate(lines):
        if re.search(re.escape(location_match), line):
            start = i
            break
    if start is None:
        return ""
    block: list[str] = [lines[start]]
    # Initialize depth from the opening line's braces so nested blocks are found.
    depth = lines[start].count("{") - lines[start].count("}")
    for line in lines[start + 1 :]:
        depth += line.count("{")
        depth -= line.count("}")
        block.append(line)
        if depth <= 0:
            break
    return "\n".join(block)


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
