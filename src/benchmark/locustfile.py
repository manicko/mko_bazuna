"""Locust load-test suite for Mko Bazuna buyer-critical journeys.

Each ``@task`` weight reflects the relative frequency of the journey on the
live site.  The ``_assert_p95`` event hook raises ``RuntimeError`` when the
run recorded no requests, or when the p95 response time exceeds
``PerformanceSLO.P95_SLO_MS`` (500 ms), surfacing regressions as a CI step
failure rather than a silent threshold warning (PERF-001 validated 2026-09).

The ``_assert_no_failures`` hook closes the complementary hole: a request to a
route that does not exist returns **404**, which measures fast and would pass
the p95 gate while discovering nothing.  It raises when the run recorded any
failure, so a target URL that stops resolving fails the job instead of
silently measuring an error page (PERF-012a validated 2026-09).

Every target URL must resolve against a real named route.  The browse
journeys therefore request ``/category/<slug>/`` — ``apps/ads/urls.py`` declares
``category/<slug:category_slug>/`` and there is no ``/c/`` route.

Run locally::

    make load

Run headless in CI (see ``.github/workflows/ci.yml`` ``load-test`` job)::

    uv run locust -f src/benchmark/locustfile.py --headless --host http://localhost:8000 \
        --users 50 --spawn-rate 10 --run-time 60s -L info --csv=/tmp/locust-results
"""

import logging

from locust import HttpUser, between, events, task

from benchmark.locust_test_config import (
    P95_SLO_MS,
)

logger = logging.getLogger(__name__)


@events.test_stop.add_listener
def _assert_p95(environment, **kwargs) -> None:
    """Assert the p95 response time stayed within the SLO threshold.

    Fires when locust finishes (including ``--headless`` runs in CI).
    Raises ``RuntimeError`` if the run carried no responses, or if the p95
    exceeds ``PerformanceSLO.P95_SLO_MS``.

    The aggregate is read from ``RequestStats.total`` (a ``StatsEntry`` that is
    always present).  ``RequestStats.get(name, method)`` must **not** be used:
    a missing key resolves through ``EntriesDict.__missing__``, which fabricates
    an empty entry, so the p95 would read as ``0`` and the gate would pass
    forever (PERF-001 validated 2026-09).  The non-empty precondition below
    turns "no data" into a loud failure rather than a silently green one.
    """
    stats = environment.runner.stats
    total = stats.total
    if total.num_requests == 0:
        msg = (
            "p95 gate cannot evaluate: the run recorded no requests "
            "(RequestStats.total.num_requests == 0)"
        )
        logger.error(msg)
        environment.process_exit_code = 1
        raise RuntimeError(msg)
    p95 = total.get_response_time_percentile(0.95)
    if p95 > P95_SLO_MS:
        msg = f"p95 response time {p95:.0f}ms exceeds SLO of {P95_SLO_MS}ms"
        logger.error(msg)
        environment.process_exit_code = 1
        raise RuntimeError(msg)
    logger.info(
        "p95 response time %.0fms is within SLO of %dms (%d requests)",
        p95,
        P95_SLO_MS,
        total.num_requests,
    )


@events.test_stop.add_listener
def _assert_no_failures(environment, **kwargs) -> None:
    """Assert the run recorded zero failed requests.

    A request to a route that does not exist returns **404**, which locust
    records as a failure.  A 404 is *fast*, so it passes the p95 gate while
    measuring nothing about the site's latency — the gate would be green
    against a URL that does not resolve.  This hook turns any recorded failure
    (a 404, a 500, a connection error) into a loud job failure, so the load
    test only ever measures routes that exist (PERF-012a validated 2026-09).

    The count is read from ``RequestStats.total`` (always present).  The
    ``num_requests == 0`` case is owned by the p95 hook, which fires first and
    reports the empty run; this hook is only meaningful once requests exist.
    """
    stats = environment.runner.stats
    total = stats.total
    if total.num_requests == 0:
        return
    if total.num_failures:
        msg = (
            f"load test recorded {total.num_failures} failed request(s) of "
            f"{total.num_requests} (fail ratio {total.fail_ratio:.1%}) — a "
            f"non-2xx response means a target URL did not resolve or the "
            f"server errored, so the latency measurement is void"
        )
        logger.error(msg)
        environment.process_exit_code = 1
        raise RuntimeError(msg)
    logger.info(
        "load test recorded no failed requests (%d requests)", total.num_requests
    )


class BuyerJourneyUser(HttpUser):
    """Buyer-critical user journeys: search, browse, filter, list."""

    wait_time = between(1, 5)

    # --- Search (most frequent buyer action) ---
    @task(3)
    def search_ads(self) -> None:
        """Buyer searches for a product."""
        self.client.get("/?q=laptop", timeout=10, name="search")

    @task(1)
    def search_empty_results(self) -> None:
        """Buyer searches with a rare query (cache-miss stress)."""
        self.client.get(
            "/?q=nonexistent+product+xyz123",
            timeout=10,
            name="search-empty",
        )

    # --- Browse by category ---
    @task(2)
    def browse_category(self) -> None:
        """Buyer browses a category page (real named route)."""
        self.client.get(
            "/category/electronics/", timeout=10, name="category-browse"
        )

    @task(1)
    def browse_subcategory(self) -> None:
        """Buyer browses a subcategory (real named route).

        ``apps/ads/urls.py`` declares a single-segment
        ``category/<slug:category_slug>/``; the category *subtree* is resolved
        by the view from that one slug, so a nested
        ``/category/electronics/phones/`` has no route.  ``phones`` is a real
        catalogue slug and is served by the same named route.
        """
        self.client.get(
            "/category/phones/", timeout=10, name="subcategory"
        )

    # --- Filter listings ---
    @task(1)
    def filter_price_range(self) -> None:
        """Buyer filters listings by price range."""
        self.client.get(
            "/?min_price=100&max_price=500",
            timeout=10,
            name="filter-price",
        )

    @task(1)
    def filter_with_query(self) -> None:
        """Buyer combines search + price filter."""
        self.client.get(
            "/?q=phone&min_price=100&max_price=500",
            timeout=10,
            name="filter-with-query",
        )

    # --- Listings index ---
    @task(1)
    def view_listings(self) -> None:
        """Buyer loads the homepage listings."""
        self.client.get("/", timeout=10, name="listings")
