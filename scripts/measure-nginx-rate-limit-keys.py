#!/usr/bin/env python3
"""Aggregate a captured nginx log stream into deployed-stack ``/media/`` rate-limit metrics.

Stdlib only, host-side. Reads the capture on **stdin** and writes a deterministic
text + JSON report on **stdout**. It **emits no verdict** (no PASS / FAIL / VOID):
the criterion is human-ruled and lives in
``docs/99-agent/nginx-rate-limit-attribution-record.md``.

Two independent channels arrive in one capture. Access and error logs are separate
Docker streams symlinked to ``/dev/stdout`` and ``/dev/stderr``, so error blocks
arrive **detached** from their access lines. The two channels are counted
**independently and summed** — never zipped, never paired by adjacency.

Origin attribution is one-sided and free: a rejected ``/media/`` ``GET`` whose
``$body_bytes_sent == 0`` is Django-origin; non-zero is an nginx-origin candidate.
Writing any literal byte count is prohibited — the nginx 429 body length is a
property of the pinned build's error page and drifts on upgrade, ``server_tokens
off`` and ``msie_padding on``; ``0`` alone is contractual.

GDPR discipline: everything is aggregated in memory and only counts are emitted —
no key, IP, referer, user-agent or forwarded-for value ever reaches stdout, and
nothing is written to disk.
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, TextIO

# ─── Config-derived constants ────────────────────────────────────────────
# MEDIA_WINDOW_SECONDS / MEDIA_BUDGET mirror RateLimitBudget.MEDIA_GATE in
# ``src/backend/apps/core/enums.py`` (60 requests / 60 s). They are a **derived**
# input, not a new magic number: the exposure precondition is `R > 60` per key
# per fixed 60 s window because at exactly 60 neither limiter rejects.
MEDIA_WINDOW_SECONDS: Final[int] = 60
MEDIA_BUDGET: Final[int] = 60
MEDIA_REQUEST_METHOD: Final[str] = "GET"
MEDIA_PATH_PREFIX: Final[str] = "/media/"
MEDIA_ZONE: Final[str] = "browse_limit"
MEDIA_STATUS_OK: Final[int] = 200
MEDIA_STATUS_FORBIDDEN: Final[int] = 403
MEDIA_STATUS_NOT_FOUND: Final[int] = 404
MEDIA_STATUS_TOO_MANY: Final[int] = 429
HTTP_STATUS_WIDTH: Final[int] = 3
# The single-second sub-bucket used by the burst-regime diagnostic: nginx's
# `rate=20r/s` is defined per second, so the peak-second count is comparable.
BURST_SUB_BUCKET_SECONDS: Final[int] = 1

# ─── Parsing patterns (anchored and quote-aware) ─────────────────────────
# `log_format main` renders, in order:
#   $remote_addr - $remote_user [$time_local] "$request" $status $body_bytes_sent
#   "$http_referer" "$http_user_agent" "$http_x_forwarded_for"
# `$time_local` is bracketed AND space-separated, `$remote_user` may be empty
# (two adjacent spaces) and `$request` is quoted with spaces inside — so
# positional/whitespace splitting is unsafe and would mis-assign
# `$body_bytes_sent`, the field the whole criterion rests on.
ACCESS_LINE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(?P<remote_addr>\S+) - (?P<remote_user>.*?) "
    r"\[(?P<time_local>[^\]]+)\] "
    r'"(?P<request>[^"]*)" '
    r"(?P<status>\d{3}) (?P<body_bytes_sent>\d+) "
    r'"(?P<referer>[^"]*)" '
    r'"(?P<user_agent>[^"]*)" '
    r'"(?P<forwarded_for>[^"]*)"\s*$'
)

# The nginx error line has NO `burst:` token and is logged at `error` level:
#   limiting requests, excess: <n> by zone "<zone>", client: <ip>, server: <s>,
#   request: "<METHOD> <URI> <PROTO>", host: "<h>"
ERROR_LINE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"limiting requests, excess: (?P<excess>\S+) "
    r'by zone "(?P<zone>[^"]*)", '
    r"client: (?P<client>\S+), "
    r"server: (?P<server>\S+), "
    r'request: "(?P<method>\S+) (?P<uri>\S+) (?P<proto>\S+)", '
    r'host: "(?P<host>[^"]*)"'
)

# The error log prefixes each line with ``2026/10/05 13:35:11`` — a different
# shape from the access log's bracketed ``$time_local``.
ERROR_TIME_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(?P<time_local>\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}) "
)

WEEKDAY_INDEX: Final[dict[str, int]] = {
    "Mon": 0,
    "Tue": 1,
    "Wed": 2,
    "Thu": 3,
    "Fri": 4,
    "Sat": 5,
    "Sun": 6,
}


@dataclass(frozen=True)
class AccessEvent:
    """One parsed ``log_format main`` access line, with raw-sensitive fields dropped."""

    key: str
    timestamp: datetime
    request_uri: str
    method: str
    status: int
    body_bytes_sent: int
    user_agent: str


@dataclass(frozen=True)
class LimitEvent:
    """One parsed nginx ``limiting requests`` error line (nginx-origin only)."""

    key: str
    timestamp: datetime
    uri: str
    method: str
    zone: str


def _parse_time_local(raw: str) -> datetime | None:
    """Parse nginx ``$time_local`` (``05/Oct/2026:13:35:07 +0000``).

    ``%d`` accepts both zero-padded and space-padded days without a platform
    ``%e`` extension."""
    try:
        return datetime.strptime(raw, "%d/%b/%Y:%H:%M:%S %z")
    except ValueError:
        return None


def _parse_error_time(raw: str) -> datetime | None:
    """Parse the nginx error-log timestamp (``2026/10/05 13:35:11``), naive UTC.

    ``error_log`` timestamps carry no offset, so they are interpreted as UTC to
    stay commensurable with the access log's ``$time_local``."""
    try:
        return datetime.strptime(raw, "%Y/%m/%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return None


def parse_access_line(line: str) -> AccessEvent | None:
    """Parse one access line, or return ``None`` when it matches neither shape."""
    match = ACCESS_LINE_PATTERN.match(line)
    if match is None:
        return None
    request = match.group("request")
    parts = request.split(" ")
    if len(parts) != 3:
        return None
    method, uri, _proto = parts
    timestamp = _parse_time_local(match.group("time_local"))
    if timestamp is None:
        return None
    return AccessEvent(
        key=match.group("remote_addr"),
        timestamp=timestamp,
        request_uri=uri,
        method=method,
        status=int(match.group("status")),
        body_bytes_sent=int(match.group("body_bytes_sent")),
        user_agent=match.group("user_agent"),
    )


def parse_error_line(line: str) -> LimitEvent | None:
    """Parse one ``limiting requests`` error line, or ``None`` for any other line."""
    match = ERROR_LINE_PATTERN.search(line)
    if match is None:
        return None
    timestamp_match = ERROR_TIME_PATTERN.match(line)
    if timestamp_match is None:
        return None
    timestamp = _parse_error_time(timestamp_match.group("time_local"))
    if timestamp is None:
        return None
    return LimitEvent(
        key=match.group("client"),
        timestamp=timestamp,
        uri=match.group("uri"),
        method=match.group("method"),
        zone=match.group("zone"),
    )


def _iter_lines(stream: TextIO) -> Iterator[str]:
    """Yield lines from the capture with ``\\r`` stripped and trailing newline removed."""
    for raw_line in stream:
        yield raw_line.replace("\r", "").rstrip("\n")


# `AccessEvent` names its path ``request_uri`` while ``LimitEvent`` names it ``uri``;
# a tiny accessor keeps the shared predicate honest without widening either shape.
def _access_path(event: AccessEvent) -> str:
    """Return the request path of an access event."""
    return event.request_uri


def _limit_path(event: LimitEvent) -> str:
    """Return the request path of an error event."""
    return event.uri


def _is_media_get(event: AccessEvent | LimitEvent) -> bool:
    """True when the event is a ``GET`` whose request path is under ``/media/``."""
    path = event.request_uri if isinstance(event, AccessEvent) else event.uri
    return event.method == MEDIA_REQUEST_METHOD and path.startswith(MEDIA_PATH_PREFIX)


def bucket_by_key(events: Iterable[AccessEvent]) -> dict[str, list[AccessEvent]]:
    """Group access events by key. Keys live only in this in-memory dict."""
    grouped: dict[str, list[AccessEvent]] = defaultdict(list)
    for event in events:
        grouped[event.key].append(event)
    return dict(grouped)


def histogram(counts: Iterable[int], edges: tuple[int, ...]) -> dict[str, int]:
    """Bucket counts by the given inclusive upper edges, with a final open bucket."""
    buckets: dict[str, int] = {}
    for upper in edges:
        buckets[f"<={upper}"] = 0
    buckets[f">{edges[-1]}"] = 0
    for count in counts:
        placed = False
        for upper in edges:
            if count <= upper:
                buckets[f"<={upper}"] += 1
                placed = True
                break
        if not placed:
            buckets[f">{edges[-1]}"] += 1
    return buckets


def peak_seconds(key: str, events: Iterable[AccessEvent], width_seconds: int) -> dict[str, int]:
    """Count events per fixed ``width_seconds`` sub-bucket for one key.

    The top-level 60 s window is a fixed, disjoint bucket; within it the peak is
    measured in 1-second sub-buckets because ``rate=20r/s`` is per second."""
    buckets: dict[str, int] = defaultdict(int)
    for event in events:
        if event.key != key:
            continue
        index = int(event.timestamp.timestamp()) // width_seconds
        buckets[str(index)] += 1
    return dict(buckets)


def attribute_media_429(
    events: Iterable[AccessEvent],
) -> tuple[int, int]:
    """Split ``/media/`` ``GET`` 429s into Django-origin (empty body) and nginx-candidate.

    The test is **one-sided**: a body length of ``0`` is Django-origin; any other
    value is an nginx-origin candidate. No literal byte count appears here."""
    empty_body = 0
    nonempty_body = 0
    for event in events:
        if event.status != MEDIA_STATUS_TOO_MANY:
            continue
        if not _is_media_get(event):
            continue
        if event.body_bytes_sent == 0:
            empty_body += 1
        else:
            nonempty_body += 1
    return empty_body, nonempty_body


def keys_over_media_budget(
    events: Iterable[AccessEvent],
    window_seconds: int = MEDIA_WINDOW_SECONDS,
    budget: int = MEDIA_BUDGET,
) -> int:
    """Count distinct keys with **more than** ``budget`` ``/media/`` requests in one fixed window.

    The window is **fixed and disjoint**, never sliding: a sliding window inflates
    every key's count and manufactures a vacuous result. At exactly ``budget``
    neither limiter rejects, so the comparison is strict ``>``."""
    per_key_window: dict[tuple[str, int], int] = defaultdict(int)
    for event in events:
        if event.method != MEDIA_REQUEST_METHOD:
            continue
        if not _access_path(event).startswith(MEDIA_PATH_PREFIX):
            continue
        index = int(event.timestamp.timestamp()) // window_seconds
        per_key_window[(event.key, index)] += 1
    over_budget: set[str] = set()
    for (key, _index), count in per_key_window.items():
        if count > budget:
            over_budget.add(key)
    return len(over_budget)


def _burst_width_seconds(events: list[AccessEvent]) -> int:
    """Return the widest integer-second span between the first and last event."""
    if len(events) < 2:
        return 0
    first = min(event.timestamp.timestamp() for event in events)
    last = max(event.timestamp.timestamp() for event in events)
    return int(last - first)


def burst_regime(rejected_by_key: dict[str, list[AccessEvent]]) -> dict[str, int]:
    """Per rejecting key, count rejections inside bursts of ``W <= 1 s`` versus ``W > 1 s``.

    Diagnostic only: the split is a function of burst duration, not a stable ratio,
    so it never participates in a soundness check. Emits aggregate counts only."""
    short_bursts = 0
    long_bursts = 0
    for events in rejected_by_key.values():
        if _burst_width_seconds(events) <= BURST_SUB_BUCKET_SECONDS:
            short_bursts += 1
        else:
            long_bursts += 1
    return {
        "burst_keys_w_le_1s": short_bursts,
        "burst_keys_w_gt_1s": long_bursts,
    }


def compute_metrics(
    access_events: list[AccessEvent],
    limit_events: list[LimitEvent],
    lines_unparsed: int,
) -> dict[str, object]:
    """Compute the full metric set. Counts only; ``attribution_delta`` is the only soundness input."""
    # The whole criterion is `GET`-only: nginx returns headers only for a rejected
    # HEAD, so its body length of 0 would be misclassified as Django-origin.
    media_access = [
        event
        for event in access_events
        if _is_media_get(event)
    ]
    media_429 = [
        event for event in media_access if event.status == MEDIA_STATUS_TOO_MANY
    ]
    empty_body, nonempty_body = attribute_media_429(media_429)

    other_status = sum(
        1
        for event in media_access
        if event.status
        not in (
            MEDIA_STATUS_OK,
            MEDIA_STATUS_FORBIDDEN,
            MEDIA_STATUS_NOT_FOUND,
            MEDIA_STATUS_TOO_MANY,
        )
    )

    # nginx-only rejection channel: zone browse_limit, /media/ path, GET.
    error_media = sum(
        1
        for event in limit_events
        if event.zone == MEDIA_ZONE
        and event.method == MEDIA_REQUEST_METHOD
        and _limit_path(event).startswith(MEDIA_PATH_PREFIX)
    )

    # The ONLY soundness input: nginx-candidate 429s must match the error channel.
    attribution_delta = nonempty_body - error_media

    rejected_by_key: dict[str, list[AccessEvent]] = defaultdict(list)
    for event in media_429:
        rejected_by_key[event.key].append(event)

    key_counts = bucket_by_key(media_access)
    key_size_histogram = histogram(
        (len(events) for events in key_counts.values()), (5, 24, 48)
    )

    # Advisory only: an upper bound on distinct (key, user-agent) pairs, emitted as
    # a count so no user-agent string ever reaches stdout.
    pair_count = len({(event.key, event.user_agent) for event in media_access})

    return {
        "keys_total": len(key_counts),
        "requests_total": len(access_events),
        "requests_media": len(media_access),
        "requests_media_429": len(media_429),
        "requests_media_429_empty_body": empty_body,
        "requests_media_429_nonempty_body": nonempty_body,
        "error_media_limit_rejected": error_media,
        "attribution_delta": attribution_delta,
        "requests_media_other_status": other_status,
        "keys_over_media_budget": keys_over_media_budget(media_access),
        "key_size_histogram": key_size_histogram,
        "distinct_key_user_agent_pairs": pair_count,
        "keys_rejected": len(rejected_by_key),
        "burst_regime": burst_regime(rejected_by_key),
        "lines_unparsed": lines_unparsed,
    }


def summarize(stream: TextIO) -> tuple[list[AccessEvent], list[LimitEvent], int]:
    """Read the whole capture, parsing each line against both channel patterns."""
    access_events: list[AccessEvent] = []
    limit_events: list[LimitEvent] = []
    lines_unparsed = 0
    for line in _iter_lines(stream):
        if not line.strip():
            continue
        access = parse_access_line(line)
        if access is not None:
            access_events.append(access)
            continue
        limit = parse_error_line(line)
        if limit is not None:
            limit_events.append(limit)
            continue
        lines_unparsed += 1
    return access_events, limit_events, lines_unparsed


def render(metrics: dict[str, object], stream: TextIO) -> None:
    """Render the deterministic text + JSON report. No verdict token is emitted."""
    stream.write("nginx /media/ rate-limit measurement\n")
    stream.write("====================================\n")
    stream.write("Counts only. Apply C1-C6 per the runbook; this report rules nothing.\n\n")
    for name, value in metrics.items():
        stream.write(f"{name}: {value}\n")
    stream.write("\nJSON\n----\n")
    stream.write(json.dumps(metrics, indent=2, sort_keys=True))
    stream.write("\n")


def main(argv: list[str] | None = None) -> int:
    """Read stdin, compute metrics and render them to stdout. Always exits 0."""
    del argv  # Input is stdin only; the script takes no arguments.
    access_events, limit_events, lines_unparsed = summarize(sys.stdin)
    metrics = compute_metrics(access_events, limit_events, lines_unparsed)
    render(metrics, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
