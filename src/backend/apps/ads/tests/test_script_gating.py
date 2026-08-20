"""
Script gating tests (T-06b / D7, TR-08).

Verifies that non-essential scripts (Plausible + GLightbox) are NOT present in
the rendered ad-detail response before consent, and ARE present after the user
accepts analytics consent.
"""

from __future__ import annotations

import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.ads.models import Ad, AdImage
from apps.categories.models import Category
from apps.core.enums import AdStatus
from apps.locations.models import City
from apps.users.models import User

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


@pytest.fixture
def seller() -> User:
    """An ad owner."""
    return User.objects.create(
        telegram_id=930000020,
        chat_id=930000020,
        password="x",
    )


@pytest.fixture
def category() -> Category:
    """A leaf category."""
    return Category.objects.create(name="Script Cat", slug="script-cat")


@pytest.fixture
def city() -> City:
    """A city."""
    return City.objects.create(
        country_code="ME", name="Script City", region="X", slug="script-city"
    )


@pytest.fixture
def ad(seller: User, category: Category, city: City) -> Ad:
    """A PUBLISHED ad with one image."""
    ad = Ad.objects.create(
        user=seller,
        title="Script Ad",
        description="Description",
        category=category,
        city=city,
        category_name=category.name,
        status=AdStatus.PUBLISHED,
        published_at=timezone.now(),
    )
    AdImage.objects.create(ad=ad, image="key-0.jpg", position=0)
    return ad


def _get_detail(client: Client, ad: Ad):
    return client.get(reverse("ads:detail", args=[ad.id]))


class TestConsentCookieFormat:
    """consent_given uses the new structured format (D-COOKIES)."""

    def test_consent_given_uses_accepted(self) -> None:
        """Accepting consent writes consent_given=accepted, not ``true``."""
        client = Client()
        response = client.post("/consent/accept/")
        assert response.cookies["consent_given"].value == "accepted"


class TestScriptGating:
    """Before consent scripts are absent; after consent they are present."""

    def test_scripts_absent_before_consent(self, ad: Ad) -> None:
        """Anonymous no-consent visitor sees no Plausible or GLightbox JS."""
        response = _get_detail(Client(), ad)
        content = response.content.decode()
        assert "plausible.io" not in content
        assert "glightbox.min.js" not in content
        assert "GLightbox({" not in content

    def test_scripts_present_after_consent(self, ad: Ad) -> None:
        """A consenting visitor sees Plausible and GLightbox JS."""
        client = Client()
        client.cookies["consent_given"] = "accepted"
        client.cookies["consent_analytics"] = "true"
        client.cookies["consent_preferences"] = "true"
        content = _get_detail(client, ad).content.decode()
        if settings.PLAUSIBLE_HOST:
            assert "plausible.io" in content
        assert "glightbox.min.js" in content
        assert "GLightbox({" in content
