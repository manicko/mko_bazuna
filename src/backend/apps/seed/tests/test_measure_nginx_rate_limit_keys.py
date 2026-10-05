"""Unit tests for ``scripts/measure-nginx-rate-limit-keys.py``.

The script is a **host-side, stdlib-only** aggregator that reads an nginx capture
on stdin and writes metric counts on stdout. It emits no verdict; the criterion
(C1-C6) is human-ruled and recorded in
``docs/99-agent/nginx-rate-limit-attribution-record.md``.

These tests pin the **attribution rule** and the **parsing hazards**, not the
shape of a dict: the one-sided ``$body_bytes_sent == 0`` test, the
never-zip-the-two-channels rule, the ``GET``-only filter, the fixed-bucket
exposure boundary, and the GDPR "counts only" guarantee.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

# Load the standalone script as a module (``scripts/`` is not on the package
# path). Its ``if __name__ == "__main__"`` guard keeps import side-effect free.
# The module is registered in ``sys.modules`` before execution because it defines
# module-level ``dataclass`` types, which need the module resolvable by name.
_SCRIPT_PATH = (
    Path(__file__).resolve().parents[5] / "scripts" / "measure-nginx-rate-limit-keys.py"
)
_spec = importlib.util.spec_from_file_location(
    "measure_nginx_rate_limit_keys", _SCRIPT_PATH
)
assert _spec is not None
assert _spec.loader is not None
mrl = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = mrl
_spec.loader.exec_module(mrl)

FIXTURE_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "nginx_media_capture.txt"
)

pytestmark = [pytest.mark.unit]


# ─── Capture builders ─────────────────────────────────────────────────────

_TIME = datetime(2026, 10, 5, 13, 35, 7, tzinfo=UTC)


def _stamp(moment: datetime) -> str:
    """Render a datetime the way nginx ``$time_local`` does."""
    return moment.strftime("%d/%b/%Y:%H:%M:%S %z")


def access_line(
    key: str,
    moment: datetime,
    method: str,
    uri: str,
    status: int,
    *,
    body_empty: bool,
    user_agent: str = "Mozilla/5.0 (Test)",
    referer: str = "https://example.test/",
) -> str:
    """Build one ``log_format main`` access line.

    ``body_empty`` selects the origin the line encodes: ``True`` emits an empty
    body (Django-origin), ``False`` emits a body derived from the request so no
    literal byte count ever appears. The exemption for ``0`` is the one the
    attribution rule itself uses."""
    body = 0 if body_empty else len(f"{method} {uri} HTTP/1.1")
    return (
        f'{key} - - [{_stamp(moment)}] "{method} {uri} HTTP/1.1" '
        f'{status} {body} "{referer}" "{user_agent}" "-"'
    )


def error_line(
    moment: datetime,
    *,
    zone: str,
    client: str,
    method: str,
    uri: str,
    host: str = "example.test",
    excess: str = "1.000",
) -> str:
    """Build one nginx ``limiting requests`` error line (no ``burst:`` token)."""
    logged = moment.strftime("%Y/%m/%d %H:%M:%S")
    return (
        f"{logged} [error] 42#42: *9000 limiting requests, excess: {excess} "
        f'by zone "{zone}", client: {client}, server: _, '
        f'request: "{method} {uri} HTTP/1.1", host: "{host}"'
    )


def run_aggregate(capture: str) -> dict[str, object]:
    """Run the aggregator over a capture string and return its parsed JSON block."""
    output = io.StringIO()
    access_events, limit_events, lines_unparsed = mrl.summarize(io.StringIO(capture))
    metrics = mrl.compute_metrics(access_events, limit_events, lines_unparsed)
    mrl.render(metrics, output)
    text = output.getvalue()
    json_block = text.split("JSON\n----\n", 1)[1]
    parsed = json.loads(json_block)
    assert isinstance(parsed, dict)
    return parsed


# ─── 1. Healthy window ────────────────────────────────────────────────────


def test_healthy_media_200s_yield_zero_429_and_zero_delta() -> None:
    """A capture with only ``/media/`` 200s has no rejections and delta 0."""
    capture = "\n".join(
        access_line("203.0.113.10", _TIME + timedelta(seconds=i), "GET", f"/media/x{i}.jpg", 200, body_empty=False)
        for i in range(5)
    )
    metrics = run_aggregate(capture)
    assert metrics["requests_media_429"] == 0
    assert metrics["requests_media_429_empty_body"] == 0
    assert metrics["requests_media_429_nonempty_body"] == 0
    assert metrics["error_media_limit_rejected"] == 0
    assert metrics["attribution_delta"] == 0


# ─── 2. nginx-only rejections reconcile ───────────────────────────────────


def test_nginx_only_rejections_reconcile_to_zero_delta() -> None:
    """Matched non-empty-body 429s and error lines attribute cleanly (delta 0)."""
    capture = "\n".join(
        [
            access_line("198.51.100.22", _TIME, "GET", "/media/a.jpg", 429, body_empty=False),
            error_line(_TIME, zone="browse_limit", client="198.51.100.22", method="GET", uri="/media/a.jpg"),
            access_line("198.51.100.22", _TIME + timedelta(seconds=1), "GET", "/media/b.jpg", 429, body_empty=False),
            error_line(_TIME + timedelta(seconds=1), zone="browse_limit", client="198.51.100.22", method="GET", uri="/media/b.jpg"),
        ]
    )
    metrics = run_aggregate(capture)
    assert metrics["requests_media_429"] == 2
    assert metrics["requests_media_429_empty_body"] == 0
    assert metrics["requests_media_429_nonempty_body"] == 2
    assert metrics["error_media_limit_rejected"] == 2
    assert metrics["attribution_delta"] == 0


# ─── 3. Django-origin rejections (the decisive case) ──────────────────────


def test_django_origin_rejections_stay_delta_zero() -> None:
    """Empty-body 429s with no error line are Django-origin and reconcile to delta 0.

    The withdrawn access-vs-error equality returned VOID here on a healthy stack;
    the attribution rule returns a delta of 0 instead."""
    capture = "\n".join(
        access_line("203.0.113.40", _TIME + timedelta(seconds=i), "GET", f"/media/z{i}.jpg", 429, body_empty=True)
        for i in range(3)
    )
    metrics = run_aggregate(capture)
    assert metrics["requests_media_429_empty_body"] > 0
    assert metrics["requests_media_429_nonempty_body"] == 0
    assert metrics["error_media_limit_rejected"] == 0
    assert metrics["attribution_delta"] == 0


# ─── 4. Channel-integrity failure ─────────────────────────────────────────


def test_unaccounted_nonempty_body_429_raises_delta() -> None:
    """A non-empty-body 429 the error channel does not corroborate is a non-zero delta."""
    capture = "\n".join(
        [
            access_line("198.51.100.24", _TIME, "GET", "/media/eta.jpg", 429, body_empty=False),
        ]
    )
    metrics = run_aggregate(capture)
    assert metrics["requests_media_429_nonempty_body"] == 1
    assert metrics["error_media_limit_rejected"] == 0
    assert metrics["attribution_delta"] != 0


# ─── 5. CRLF capture ──────────────────────────────────────────────────────


def test_crlf_capture_parses_identically() -> None:
    """A Windows-authored capture with ``\\r\\n`` parses the same as ``\\n``."""
    lines = [
        access_line("203.0.113.10", _TIME, "GET", "/media/a.jpg", 200, body_empty=False),
        access_line("198.51.100.22", _TIME + timedelta(seconds=1), "GET", "/media/b.jpg", 429, body_empty=False),
        error_line(_TIME + timedelta(seconds=1), zone="browse_limit", client="198.51.100.22", method="GET", uri="/media/b.jpg"),
    ]
    lf = "\n".join(lines)
    crlf = "\r\n".join(lines)
    assert run_aggregate(crlf) == run_aggregate(lf)


# ─── 6. The $time_local hazard ────────────────────────────────────────────


def test_space_separated_timestamp_reads_correct_body_field() -> None:
    """A space inside ``$time_local`` must not shift ``$body_bytes_sent``.

    Positional whitespace splitting mis-reads the body field and would attribute
    this nginx-origin rejection as Django-origin. Parse by field, never by position.
    The body value is never compared to a literal: correctness is proven by the
    classification the discriminant produces from the parsed field."""
    capture = access_line("198.51.100.50", _TIME, "GET", "/media/hazard.jpg", 429, body_empty=False)
    event = mrl.parse_access_line(capture)
    assert event is not None
    assert event.key == "198.51.100.50"
    assert event.status == 429
    assert event.request_uri == "/media/hazard.jpg"
    assert event.method == "GET"
    assert event.timestamp == _TIME
    empty_body, nonempty_body = mrl.attribute_media_429([event])
    assert empty_body == 0
    assert nonempty_body == 1


# ─── 7. GET-only on both channels ─────────────────────────────────────────


def test_rejected_head_is_excluded_from_both_channels() -> None:
    """A rejected ``HEAD`` is excluded from the access and the error census."""
    capture = "\n".join(
        [
            access_line("198.51.100.25", _TIME, "HEAD", "/media/theta.jpg", 429, body_empty=True),
            error_line(_TIME, zone="browse_limit", client="198.51.100.25", method="HEAD", uri="/media/theta.jpg"),
        ]
    )
    metrics = run_aggregate(capture)
    assert metrics["requests_media_429"] == 0
    assert metrics["requests_media_429_empty_body"] == 0
    assert metrics["requests_media_429_nonempty_body"] == 0
    assert metrics["error_media_limit_rejected"] == 0
    assert metrics["attribution_delta"] == 0


# ─── 8. keys_over_media_budget boundary ───────────────────────────────────


def test_budget_boundary_is_strict_and_bucket_is_fixed() -> None:
    """A key at exactly the budget is not counted; one over is. Fixed beats sliding.

    A sliding 60 s window would count the second key below because all its requests
    fall inside a 60 s sliding span around the boundary; disjoint fixed buckets do not.
    """
    base = datetime(2026, 10, 5, 13, 0, 0, tzinfo=UTC)
    exactly_budget = "\n".join(
        access_line("203.0.113.60", base + timedelta(seconds=i), "GET", f"/media/e{i}.jpg", 200, body_empty=False)
        for i in range(mrl.MEDIA_BUDGET)
    )
    assert run_aggregate(exactly_budget)["keys_over_media_budget"] == 0

    # 61 requests that all land inside one fixed 60 s bucket (requests share
    # seconds, so the count is what exceeds the budget, not the span).
    over_budget = "\n".join(
        access_line("203.0.113.61", base + timedelta(seconds=i % 30), "GET", f"/media/o{i}.jpg", 200, body_empty=False)
        for i in range(mrl.MEDIA_BUDGET + 1)
    )
    assert run_aggregate(over_budget)["keys_over_media_budget"] == 1

    # 40 requests in each of two adjacent fixed 60 s buckets, clustered near the
    # shared boundary. A sliding 60 s window spanning the boundary would observe
    # all 80 and flag the key; disjoint fixed buckets observe 40 and 40, so neither
    # exceeds the budget.
    straddling = "\n".join(
        access_line("203.0.113.62", base + timedelta(seconds=30 + (i % 30)), "GET", f"/media/s{i}.jpg", 200, body_empty=False)
        for i in range(40)
    ) + "\n" + "\n".join(
        access_line("203.0.113.62", base + timedelta(seconds=60 + (i % 30)), "GET", f"/media/t{i}.jpg", 200, body_empty=False)
        for i in range(40)
    )
    assert run_aggregate(straddling)["keys_over_media_budget"] == 0


# ─── 9. Unparsed lines are counted ────────────────────────────────────────


def test_malformed_line_is_counted_and_does_not_crash() -> None:
    """A line matching neither shape increments ``lines_unparsed``."""
    capture = "this is not an nginx record"
    metrics = run_aggregate(capture)
    assert metrics["lines_unparsed"] == 1
    assert metrics["requests_media_429"] == 0


# ─── 10. GDPR — counts only ───────────────────────────────────────────────


def test_serialized_output_contains_no_personal_data() -> None:
    """The rendered output must contain no IP, referer or user-agent fixture value."""
    capture = FIXTURE_PATH.read_text(encoding="utf-8")
    output = io.StringIO()
    access_events, limit_events, lines_unparsed = mrl.summarize(io.StringIO(capture))
    mrl.render(mrl.compute_metrics(access_events, limit_events, lines_unparsed), output)
    rendered = output.getvalue()

    sensitive = [
        "203.0.113.10",
        "198.51.100.22",
        "198.51.100.20",
        "Mozilla/5.0 (X11; Linux x86_64)",
        "Mozilla/5.0 (Android 14)",
        "https://example.test/listing/1",
    ]
    for value in sensitive:
        assert value not in rendered


# ─── 11. Independent counting, never zipped ───────────────────────────────


def test_error_lines_detached_from_access_lines_are_counted() -> None:
    """Error lines in a block far from their access lines still reconcile.

    The two Docker streams are independent; zipping or pairing by adjacency would
    mis-count a detached error block."""
    access_block = "\n".join(
        access_line("198.51.100.70", _TIME + timedelta(seconds=i), "GET", f"/media/d{i}.jpg", 429, body_empty=False)
        for i in range(4)
    )
    error_block = "\n".join(
        error_line(_TIME + timedelta(seconds=i, minutes=5), zone="browse_limit", client="198.51.100.70", method="GET", uri=f"/media/d{i}.jpg")
        for i in range(4)
    )
    metrics = run_aggregate(access_block + "\n" + error_block)
    assert metrics["requests_media_429_nonempty_body"] == 4
    assert metrics["error_media_limit_rejected"] == 4
    assert metrics["attribution_delta"] == 0


# ─── Committed fixture: end-to-end mixed capture ──────────────────────────


def test_committed_fixture_end_to_end_metrics() -> None:
    """The committed synthetic capture exercises the mixed-channel contract.

    The fixture (``fixtures/nginx_media_capture.txt``, RFC 5737 addresses only)
    contains, in one interleaved capture:

    * ``/media/`` 200s and one non-media ``/`` 200;
    * a corroborated nginx-origin rejection (epsilon: non-empty body + error line);
    * a Django-origin rejection (zeta: empty body, no error line);
    * a channel-integrity failure (eta: non-empty body with no error line);
    * a rejected ``HEAD`` on both channels (theta), which both must exclude;
    * an error line for a non-media zone and one for a non-media path;
    * a malformed line; and a ``/media/`` 500 outside the known status set.
    """
    capture = FIXTURE_PATH.read_text(encoding="utf-8")
    metrics = run_aggregate(capture)
    assert metrics["requests_media_429"] == 3
    assert metrics["requests_media_429_empty_body"] == 1
    assert metrics["requests_media_429_nonempty_body"] == 2
    assert metrics["error_media_limit_rejected"] == 1
    assert metrics["attribution_delta"] == 1
    assert metrics["requests_media_other_status"] == 1
    assert metrics["lines_unparsed"] == 1
