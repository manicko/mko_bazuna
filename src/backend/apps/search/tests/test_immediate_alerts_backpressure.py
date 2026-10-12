"""
Integration tests for the immediate-alert backpressure gate (09-API-013).

Moved from ``test_immediate_alerts.py`` (which is marked ``unit``) so that the
backpressure test — which writes DB rows and exercises the real dispatch path
at the threshold — is marked ``integration`` without stacking a ``unit`` marker
from a module-level ``pytestmark``.
"""

from __future__ import annotations

import logging

import pytest

from apps.core.enums import AdStatus
from apps.search.models import SavedSearch
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestBackpressureSheds:
    """Above the in-flight threshold the dispatch is skipped with a WARNING."""

    def test_backlog_above_threshold_skips_and_warns(
        self,
        seller,
        buyer,
        category,
        city,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A saturated backlog issues no outbound send and logs a WARNING."""
        from apps.search.services import immediate_alerts

        submitted: list[list] = []
        monkeypatch.setattr(
            immediate_alerts,
            "_executor",
            type(
                "_Recorder",
                (),
                {"submit": lambda self, fn, *a: submitted.append(a)},
            )(),
        )
        # Pretend the backlog is already at the threshold.
        monkeypatch.setattr(
            immediate_alerts,
            "_in_flight_batches",
            immediate_alerts._MAX_IN_FLIGHT_BATCHES,
        )

        ad = create_test_ad(
            seller, category, city, title="Красный велосипед",
            status=AdStatus.PUBLISHED,
        )
        SavedSearch.objects.create(user=buyer, is_active=True)

        with caplog.at_level(logging.WARNING):
            immediate_alerts.deliver_immediate_alerts(ad.id)

        assert submitted == [], "a shed dispatch must not reach the executor"
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any(f"ad {ad.id}" in r.getMessage() for r in warnings), (
            "the WARNING must name the ad"
        )
        assert any(
            str(immediate_alerts._MAX_IN_FLIGHT_BATCHES) in r.getMessage()
            for r in warnings
        ), "the WARNING must name the in-flight count/threshold"
        # The counter is untouched by a shed dispatch.
        assert (
            immediate_alerts._in_flight_batches
            == immediate_alerts._MAX_IN_FLIGHT_BATCHES
        )
