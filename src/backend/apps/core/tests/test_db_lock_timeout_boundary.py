"""Lock-timeout error boundary in the web tier (03-DB-004, timeout half B).

Six redirect-only views have no error surface, so they are served by one
predicate-gated ``process_exception`` middleware (503 + ``Retry-After``).
``ad_edit`` is the one seller-facing view with a template to return to, so it
handles the timeout in-view and re-renders ``ads/edit.html``. The three bulk
admin actions fail loudly (nothing committed) rather than hanging.

The predicate is narrow: an ``OperationalError`` that is not a lock timeout must
keep its existing behaviour everywhere.
"""

from __future__ import annotations

from unittest.mock import patch

import psycopg
import pytest
from django.db import OperationalError
from django.test import Client, RequestFactory
from django.urls import reverse

from apps.core.enums import AdStatus
from apps.moderation.admin_actions import bulk_approve, bulk_delete, bulk_reject
from conftest import create_test_ad

pytestmark = [pytest.mark.integration]


def _lock_timeout_error() -> OperationalError:
    exc = OperationalError("canceling statement due to lock timeout")
    exc.__cause__ = psycopg.errors.LockNotAvailable(
        "canceling statement due to lock timeout"
    )
    return exc


def _unrelated_error() -> OperationalError:
    return OperationalError("connection refused")


class TestMiddleware:
    """The predicate-gated middleware turns a lock timeout into a 503."""

    def _middleware(self):
        from apps.core.middleware.db_lock_timeout import DbLockTimeoutMiddleware

        return DbLockTimeoutMiddleware(lambda request: None)

    def test_lock_timeout_returns_503(self) -> None:
        request = RequestFactory().post("/ads/1/archive/")
        response = self._middleware().process_exception(request, _lock_timeout_error())
        assert response is not None
        assert response.status_code == 503
        assert response["Retry-After"] == "30"

    def test_non_lock_error_is_not_intercepted(self) -> None:
        request = RequestFactory().post("/ads/1/archive/")
        assert self._middleware().process_exception(request, _unrelated_error()) is None

    def test_arbitrary_exception_is_not_intercepted(self) -> None:
        request = RequestFactory().post("/ads/1/archive/")
        assert self._middleware().process_exception(request, ValueError("boom")) is None


class TestAdEditLockTimeout:
    """``ad_edit`` re-renders the form with the busy message on a timeout."""

    @pytest.mark.django_db
    def test_lock_timeout_renders_edit_template_with_error(
        self, seller, category, city
    ) -> None:
        from apps.ads.views import edit

        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        client = Client()
        client.force_login(seller)

        with patch.object(
            edit.Ad.objects,
            "select_for_update",
            side_effect=_lock_timeout_error(),
        ):
            response = client.post(
                reverse("ads:edit", args=[ad.id]),
                {"title": "New title", "description": "New description"},
            )

        assert response.status_code == 200
        content = response.content.decode()
        assert "busy" in content.lower()

    @pytest.mark.django_db
    def test_unrelated_operational_error_propagates(
        self, seller, category, city
    ) -> None:
        from apps.ads.views import edit

        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        request = RequestFactory().post(
            reverse("ads:edit", args=[ad.id]),
            {"title": "New title", "description": "New description"},
        )
        request.user = seller

        with (
            patch.object(
                edit.Ad.objects,
                "select_for_update",
                side_effect=_unrelated_error(),
            ),
            pytest.raises(OperationalError),
        ):
            edit.ad_edit(request, ad.id)


class TestBulkLockTimeout:
    """The three bulk actions fail loudly with nothing committed."""

    @pytest.mark.django_db
    def test_bulk_approve_reraises_and_commits_nothing(
        self, seller, category, city
    ) -> None:
        from django.db.models.query import QuerySet

        from apps.ads.models import Ad

        create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)
        create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)

        with (
            patch.object(
                QuerySet,
                "select_for_update",
                side_effect=_lock_timeout_error(),
            ),
            pytest.raises(OperationalError),
        ):
            bulk_approve(Ad.objects.all(), seller.id)

        # Nothing was committed.
        assert not Ad.objects.filter(status=AdStatus.PUBLISHED).exists()

    @pytest.mark.django_db
    def test_bulk_reject_reraises(self, seller, category, city) -> None:
        from django.db.models.query import QuerySet

        from apps.ads.models import Ad

        create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)

        with (
            patch.object(
                QuerySet,
                "select_for_update",
                side_effect=_lock_timeout_error(),
            ),
            pytest.raises(OperationalError),
        ):
            bulk_reject(Ad.objects.all(), seller.id, "reason")

        assert not Ad.objects.filter(status=AdStatus.REJECTED).exists()

    @pytest.mark.django_db
    def test_bulk_delete_reraises(self, seller, category, city) -> None:
        from django.db.models.query import QuerySet

        from apps.ads.models import Ad

        create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)

        with (
            patch.object(
                QuerySet,
                "select_for_update",
                side_effect=_lock_timeout_error(),
            ),
            pytest.raises(OperationalError),
        ):
            bulk_delete(Ad.objects.all(), seller.id, "reason")

        assert not Ad.objects.filter(status=AdStatus.DELETED).exists()


class TestMiddlewareWiring:
    """The middleware is registered in MIDDLEWARE."""

    def test_middleware_registered(self) -> None:
        from django.conf import settings

        assert (
            "apps.core.middleware.db_lock_timeout.DbLockTimeoutMiddleware"
            in settings.MIDDLEWARE
        )
