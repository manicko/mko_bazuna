#!/usr/bin/env python3
"""cProfile harness for the Mko Bazuna search endpoint.

Runs the search view under ``cProfile`` for a configurable number of
iterations and prints the top-N functions by the chosen sort key.

Usage (inside the dev web container, via ``make profile``)::

    uv run python scripts/profile_search.py
        [--iterations N] [--top N] [--sort KEY] [--query STR]

Requires the dev environment to be running (``make up``) so the database
contains seed data and the search vectors are populated.

The harness uses the Django test ``Client`` so the full view stack —
middleware, ORM, native PostgreSQL FTS, SWR search cache, and template
rendering — is profiled without needing the HTTP server to be separately
reachable.
"""

import argparse
import cProfile
import logging
import os
import pstats
import sys
from enum import StrEnum
from typing import Final

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

import django  # noqa: E402
from django.test import Client  # noqa: E402
from django.urls import reverse  # noqa: E402

django.setup()

logger = logging.getLogger(__name__)


class ProfileSortKey(StrEnum):
    """Valid pstats sort specifiers for the profile report."""

    CUMULATIVE = "cumulative"
    TOTTIME = "tottime"
    TIME = "time"
    NCALLS = "ncalls"
    CALLS = "calls"
    FILENAME = "filename"
    LINENO = "lineno"
    PERCALL = "percall"


DEFAULT_QUERY: Final[str] = "laptop"
DEFAULT_ITERATIONS: Final[int] = 50
DEFAULT_TOP: Final[int] = 30
SEARCH_URL_NAME: Final[str] = "search:search"


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the profiling harness."""
    parser = argparse.ArgumentParser(
        description="Profile the Mko Bazuna search endpoint with cProfile.",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=DEFAULT_ITERATIONS,
        help="Number of search requests to execute under the profiler "
        "(default: %(default)s)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=DEFAULT_TOP,
        help="Number of top functions to print from the profile "
        "(default: %(default)s)",
    )
    parser.add_argument(
        "--sort",
        type=ProfileSortKey,
        default=ProfileSortKey.CUMULATIVE,
        help=(
            "pstats sort key (default: %(default)s). "
            f"Valid: {', '.join(k.value for k in ProfileSortKey)}"
        ),
    )
    parser.add_argument(
        "--query",
        type=str,
        default=DEFAULT_QUERY,
        help="Search query string sent to the search endpoint "
        "(default: %(default)s)",
    )
    return parser.parse_args()


def run_profile(
    iterations: int,
    search_query: str,
    sort_key: ProfileSortKey,
    top: int,
) -> None:
    """Execute *iterations* search requests under cProfile and print stats.

    Each iteration issues a GET to the ``search:search`` URL with ``?q=``
    set to *search_query*, exercising the language-aware PostgreSQL FTS
    path, the SWR search cache, and full template rendering.
    """
    url = reverse(SEARCH_URL_NAME)
    client = Client()

    profiler = cProfile.Profile()
    logger.info(
        "Starting cProfile: %d iterations of GET %s?q=%s",
        iterations,
        url,
        search_query,
    )
    profiler.enable()
    for i in range(iterations):
        response = client.get(url, {"q": search_query})
        _ = response.content
        logger.debug("Iteration %d: HTTP %s", i + 1, response.status_code)
    profiler.disable()
    logger.info("Profiling complete. Generating report...")

    stats = pstats.Stats(profiler, stream=sys.stdout)
    stats.sort_stats(sort_key.value)
    stats.print_stats(top)


def main() -> None:
    """Parse arguments, validate, and run the profiling harness."""
    args = _parse_args()
    if args.iterations <= 0:
        logger.error("--iterations must be a positive integer")
        sys.exit(2)
    if args.top <= 0:
        logger.error("--top must be a positive integer")
        sys.exit(2)

    run_profile(
        iterations=args.iterations,
        search_query=args.query,
        sort_key=args.sort,
        top=args.top,
    )


if __name__ == "__main__":
    main()
