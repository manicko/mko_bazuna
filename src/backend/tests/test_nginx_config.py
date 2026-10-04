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


_LOCATION_RE = re.compile(r"\s*location\s+(?P<modifier>[~*^=]*)?\s*(?P<uri>\S+)")


def _deny_block(text: str) -> str:
    """Return the script-execution deny block, located order-independently.

    ``_location_block`` matches the **first** line containing a string, which is
    shadowed by the earlier comment, and matches on substring, which the ``~*``
    header does not contain. Iterating every block and matching on its whole
    body avoids both hazards.
    """
    for block in _iter_location_blocks(text):
        if "deny all" in block and "return 403" in block and "proxy_pass" not in block:
            return block
    return ""


def _location_modifier(block: str) -> str:
    """Return the location header modifier (``~*``, ``=``, ``''`` for prefix)."""
    match = _LOCATION_RE.match(block.split("\n", 1)[0])
    return match.group("modifier") or "" if match else ""


def _location_uri(block: str) -> str:
    """Return the location header's URI for the first line of ``block``."""
    match = _LOCATION_RE.match(block.split("\n", 1)[0])
    return match.group("uri") if match else ""


def _extract_deny_regex(block: str) -> str:
    """Return the raw PCRE source from the deny ``location`` header."""
    return _location_uri(block)


def _limit_req_zones(text: str) -> list[str]:
    """Return every ``limit_req_zone`` zone name declared in ``text``."""
    return re.findall(r"limit_req_zone\s+\S+\s+zone=([A-Za-z0-9_]+):", text)


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


@pytest.mark.parametrize("conf_path", _PROXIED_CONFS)
def test_media_denies_script_execution(conf_path: Path) -> None:
    """MEDIA_ROOT must refuse requests for executable script extensions.

    The nginx-served media directory must carry exactly one deny block for
    ``.php``/``.py``/``.cgi``/``.pl``/``.sh``. That block must be a ``~*``
    regex match — a plain prefix ``location /media/`` would collide with the
    proxying block (nginx refuses the duplicate, or, if it replaced it, 403s
    every genuine photo).

    The executable check is the extracted regex itself: it is compiled caseless
    and exercised against hostile URIs and against real storage-key shapes, with
    the query string stripped to model nginx. This is the anti-outage control —
    it fails on the unescaped-dot typo (which inverts the match) and on the
    ``$``-anchored counterfeit (which lets ``/media/x.php/a.jpg`` through).
    """
    text = conf_path.read_text()
    block = _deny_block(text)
    assert block, (
        f"{conf_path.name}: must define a script-execution deny block carrying "
        "`deny all` and `return 403` with no `proxy_pass`"
    )

    modifier = _location_modifier(block)
    assert modifier == "~*", (
        f"{conf_path.name}: the script-execution deny location must be a ~* "
        f"regex match, got {modifier!r}"
    )

    pattern = _extract_deny_regex(block)
    compiled = re.compile(pattern, re.IGNORECASE)

    # 10 hostile URIs: extension at the tail, with a trailing slash, in path
    # segments, uppercased, and double-extension shapes.
    hostile = [
        "/media/x.php",
        "/media/x.PHP",
        "/media/x.php/a.jpg",
        "/media/x.jpg.php",
        "/media/nested/dir/shell.sh",
        "/media/x.py?download=1",
        "/media/x.cgi/anything.png",
        "/media/x.pl",
        "/media/a.b.php/a.jpg",
        "/media/seed/x.php",
    ]
    # nginx strips the query string before matching a location, so strip it here
    # too (``?download=1`` must not smuggle an executable past the deny).
    missed = [uri for uri in hostile if not compiled.search(uri.split("?", 1)[0])]
    assert not missed, f"{conf_path.name}: deny regex does not deny: {missed}"

    # Real key shapes that must NEVER be denied: any false positive here is a
    # silent outage of the photo surface.
    genuine = [
        "/media/7f3c1a9e-8b2d-4c6f-9a01-2b3c4d5e6f70.jpg",
        "/media/7f3c1a9e-8b2d-4c6f-9a01-2b3c4d5e6f70-small.jpg",
        "/media/7f3c1a9e-8b2d-4c6f-9a01-2b3c4d5e6f70-medium.jpg",
        "/media/7f3c1a9e-8b2d-4c6f-9a01-2b3c4d5e6f70-large.jpg",
        "/media/seed/kvartiry_01.jpg",
        "/media/seed/kvartiry_01-small.jpg",
        "/media/staging/7f3c1a9e-8b2d-4c6f-9a01-2b3c4d5e6f70.jpg",
        "/media/seed/kvartiry_01-large.jpg",
        "/media/a.b.c.jpg",
        # Extension-less look-alikes that a wildcard dot would over-block: the
        # regex must key on a literal ``.`` before the extension, never on the
        # extension letters inside an arbitrary word. These are the shapes that
        # expose the unescaped-dot typo (``\.`` -> ``.``).
        "/media/spy",
        "/media/happy",
        "/media/seed/plash",
    ]
    broken = [uri for uri in genuine if compiled.search(uri.split("?", 1)[0])]
    assert not broken, (
        f"{conf_path.name}: OUTAGE: deny regex would 403 genuine photos: {broken}"
    )


@pytest.mark.parametrize("conf_path", _PROXIED_CONFS)
def test_media_location_is_rate_limited(conf_path: Path) -> None:
    """The proxying ``/media/`` location must use ``browse_limit`` with nodelay.

    ``browse_limit`` is already declared; ``/media/`` must reference it. The
    zone census is a positive equality so it fails if a zone is deleted, if a
    fourth is added, or if ``browse_limit`` is renamed.
    """
    text = conf_path.read_text()

    zones = _limit_req_zones(text)
    assert len(zones) == 3, (
        f"{conf_path.name}: expected exactly 3 limit_req zones, found {zones}"
    )
    assert zones.count("browse_limit") == 1, (
        f"{conf_path.name}: `browse_limit` must be defined exactly once; found "
        f"{zones.count('browse_limit')}"
    )

    media_blocks = [
        block
        for block in _iter_location_blocks(text)
        if _location_uri(block).startswith("/media/")
    ]
    assert len(media_blocks) == 1, (
        f"{conf_path.name}: expected exactly one `/media/` prefix location, "
        f"found {len(media_blocks)}"
    )
    block = media_blocks[0]
    assert "limit_req zone=browse_limit" in block, (
        f"{conf_path.name}: `location /media/` must carry "
        "`limit_req zone=browse_limit`"
    )
    assert "nodelay" in block, (
        f"{conf_path.name}: `location /media/` limit_req must use `nodelay`, "
        "otherwise accepted thumbnails are delayed"
    )
    assert "proxy_pass" in block, (
        f"{conf_path.name}: `location /media/` must still proxy to Django"
    )


@pytest.mark.parametrize("conf_path", _PROXIED_CONFS)
def test_media_location_carries_browse_limit_burst_40(conf_path: Path) -> None:
    """``/media/`` must keep the exact phase-07 proxy rating in both sites.

    This pins the coordinator ruling on ``09-API-005``: the proxy half was
    already shipped by phase 07 (``77c1653``) and is deliberately **not**
    re-rated. ``.ai/plans/21-nginx-dev-media-gate.md`` and
    ``.ai/plans/22-nginx-rate-limit-deployed-gate.md`` are open, human-gated
    verification plans that hold this exact directive as a deployed-stack
    measurement basis; adding a ``media_limit`` zone or changing these numbers
    would invalidate their readings. The application-level limiter lives in
    ``apps/ads/views/listings.py::media_gate`` instead.

    Asserts the directive byte-for-byte: a re-rate (zone rename or a changed
    ``burst``) fails here, by design.
    """
    text = conf_path.read_text()
    media_blocks = [
        block
        for block in _iter_location_blocks(text)
        if _location_uri(block).startswith("/media/")
    ]
    assert len(media_blocks) == 1, (
        f"{conf_path.name}: expected exactly one `/media/` prefix location, "
        f"found {len(media_blocks)}"
    )
    assert "limit_req zone=browse_limit burst=40 nodelay;" in media_blocks[0], (
        f"{conf_path.name}: `location /media/` must keep the phase-07 rating "
        "`limit_req zone=browse_limit burst=40 nodelay;` unchanged (09-API-005 "
        "coordinator ruling; plans 21/22 depend on this exact line)"
    )


def test_media_deny_adds_no_collateral_change() -> None:
    """The media hardening must leave the pre-existing controls untouched.

    Re-asserts the three ``/metrics`` facts and ``/protected-media/`` on
    nginx.conf, and confirms neither new comment mentions ``= /metrics`` (which
    would shadow ``_location_block(_NGINX_CONF, "= /metrics")``).
    """
    text = _NGINX_CONF.read_text()
    metrics = _location_block(text, "= /metrics")
    assert metrics, "nginx.conf must define a `location = /metrics` block"
    assert "proxy_pass" in metrics
    assert "allow 127.0.0.1" in metrics
    assert "deny all" in metrics

    protected = _location_block(text, "/protected-media/")
    assert protected, "nginx.conf must define a `location /protected-media/` block"
    assert "internal;" in protected
    assert "alias /media_volume/;" in protected

    deny = _deny_block(text)
    deny_comment = deny.split("location", 1)[0]
    assert "= /metrics" not in deny_comment, (
        "the new media comment must not contain `= /metrics`"
    )


# ---------------------------------------------------------------------------
# 09-API-010 / 09-API-014 — the nginx contract bundle
# ---------------------------------------------------------------------------


def _server_blocks(text: str) -> list[str]:
    """Return every ``server`` block in ``text`` as a brace-delimited string."""
    lines = text.split("\n")
    blocks: list[str] = []
    for i, line in enumerate(lines):
        if re.match(r"\s*server\s*\{", line):
            blocks.append(_brace_block(lines, i))
    return blocks


def _http80_block(text: str) -> str:
    """Return the ``server`` block whose ``listen`` is plain port 80."""
    for block in _server_blocks(text):
        for line in block.split("\n"):
            if re.match(r"\s*listen\s+80\s*;", line):
                return block
    return ""


@pytest.mark.parametrize("conf_path", _PROXIED_CONFS)
def test_http_listener_declares_an_explicit_catch_all(conf_path: Path) -> None:
    """The ``:80`` listener must declare ``server_name _;`` (Q14).

    A ``listen 80`` block with no ``server_name`` is already nginx's default
    server for the port, so this line changes no routing. It closes the
    asymmetry with the ``:443`` block, which declares its own catch-all: both
    listeners now state the same thing rather than one relying on the implicit
    default. The domain mechanism is deliberately routed, not invented.
    """
    text = conf_path.read_text()
    block = _http80_block(text)
    assert block, f"{conf_path.name}: must define a `listen 80` server block"
    assert "server_name _;" in block, (
        f"{conf_path.name}: the `listen 80` block must declare `server_name _;` "
        "(Q14 — close the asymmetry with the :443 catch-all)"
    )


@pytest.mark.parametrize("conf_path", _PROXIED_CONFS)
def test_every_proxied_location_sets_x_forwarded_host(conf_path: Path) -> None:
    """Every proxying location must set ``X-Forwarded-Host`` (09-API-010).

    ``USE_X_FORWARDED_HOST`` is trusted in Django, so a location that omits
    this header leaves the trust model depending on a header nobody sets or
    clears. Includes ``location /static/``, which re-declares the whole
    security-header set and is easy to miss.
    """
    text = conf_path.read_text()
    proxied = _proxied_locations(text)
    assert proxied, f"{conf_path.name} must define at least one proxying location"
    for block in proxied:
        assert "proxy_set_header X-Forwarded-Host $host;" in block, (
            f"{conf_path.name}: every proxying location must set "
            "`proxy_set_header X-Forwarded-Host $host;`"
        )


@pytest.mark.parametrize("conf_path", _PROXIED_CONFS)
def test_tls_posture_is_pinned_without_a_cipher_string(conf_path: Path) -> None:
    """``ssl_protocols`` and the session cache are pinned; no ``ssl_ciphers``.

    Pinning the protocols and the session cache is reviewable; an explicit
    cipher string is a maintenance burden that silently rots. TLS 1.2 is kept —
    this is about reviewability, not deprecating TLS 1.2.
    """
    text = conf_path.read_text()
    assert "ssl_protocols TLSv1.2 TLSv1.3;" in text, (
        f"{conf_path.name}: the TLS block must pin "
        "`ssl_protocols TLSv1.2 TLSv1.3;`"
    )
    assert "ssl_session_cache shared:SSL:" in text, (
        f"{conf_path.name}: the TLS block must pin an `ssl_session_cache`"
    )
    cipher_directives = [
        line.strip()
        for line in text.split("\n")
        if line.strip().startswith("ssl_ciphers")
    ]
    assert not cipher_directives, (
        f"{conf_path.name}: no explicit `ssl_ciphers` string may be pinned; "
        f"found: {cipher_directives}"
    )

