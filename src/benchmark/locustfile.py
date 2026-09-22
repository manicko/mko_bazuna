"""Locust load-test suite for Mko Bazuna buyer-critical journeys.

Each ``@task`` weight reflects the relative frequency of the journey on the
live site.  The ``_assert_p95`` event hook raises ``RuntimeError`` when the
p95 response time exceeds ``PerformanceSLO.P95_SLO_MS`` (500 ms), surfacing
regressions as a CI step failure rather than a silent threshold warning.

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
    Raises ``RuntimeError`` if the p95 exceeds ``PerformanceSLO.P95_SLO_MS``.
    """
    stats = environment.runner.stats
    p95 = stats.get("Total", "NONE").percentile(0.95)
    if p95 > P95_SLO_MS:
        msg = f"p95 response time {p95:.0f}ms exceeds SLO of {P95_SLO_MS}ms"
        logger.error(msg)
        environment.process_exit_code = 1
        raise RuntimeError(msg)
    logger.info("p95 response time %.0fms is within SLO of %dms", p95, P95_SLO_MS)


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
        """Buyer browses a category page."""
        self.client.get("/c/electronics", timeout=10, name="category-browse")

    @task(1)
    def browse_subcategory(self) -> None:
        """Buyer browses a subcategory."""
        self.client.get("/c/electronics/phones", timeout=10, name="subcategory")

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
