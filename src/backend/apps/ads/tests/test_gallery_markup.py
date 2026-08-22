"""
GLightbox gallery markup tests (TST-GAL-001 / spec 13).

Verifies the ad-detail gallery wiring for PUBLISHED ads with images:
- The GLightbox CSS link, JS script, and inline init are present on the page
- Each image is wrapped in an `<a class="glightbox" data-gallery="ad-gallery">`
  anchor whose `href` is the full image URL and whose thumbnail is used as src
- Images render in `AdImage.position` order
- Single-image and no-image branches are preserved
- No-JS progressive enhancement: the static grid `<img>` still renders valid src
"""

import re

import pytest
from django.test import Client
from django.urls import reverse

from apps.ads.models import Ad, AdImage
from apps.categories.models import Category
from apps.core.enums import AdStatus
from apps.locations.models import City
from apps.users.models import User

from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


def _create_published_ad(
    seller: User,
    category: Category,
    city: City,
    *,
    image_positions: list[int],
) -> Ad:
    """Create a PUBLISHED ad with AdImage rows at the given positions."""
    ad = create_test_ad(
        seller,
        category,
        city,
        title="Gallery Ad",
        description="Gallery description",
        status=AdStatus.PUBLISHED,
    )
    for pos in image_positions:
        AdImage.objects.create(
            ad=ad,
            image=f"key-{pos}.jpg",
            position=pos,
            thumbnail_large=f"key-{pos}-large.jpg",
        )
    return ad


def _consent_client() -> Client:
    """A client that has accepted analytics consent (enables script rendering).

    GLightbox JS is gated behind ``consent_analytics`` (D7 / T-06b), so tests
    that assert the JS presence must act as a consenting visitor.
    """
    client = Client()
    client.cookies["consent_given"] = "accepted"
    client.cookies["consent_analytics"] = "true"
    client.cookies["consent_preferences"] = "true"
    return client


class TestGalleryMarkup:
    """Ad detail page renders the GLightbox gallery for published ads."""

    def test_detail_contains_glightbox_assets(
        self, seller: User, category: Category, city: City
    ) -> None:
        """The GLightbox CSS link, JS script, and inline init are present."""
        ad = _create_published_ad(seller, category, city, image_positions=[0, 1])
        client = _consent_client()
        response =         client.get(reverse("ads:detail", args=[ad.id]))
        assert response.status_code == 200
        content = response.content.decode()
        assert "glightbox.min.css" in content
        assert "glightbox.min.js" in content
        assert "GLightbox({" in content

    def test_each_image_is_glightbox_anchor(
        self, seller: User, category: Category, city: City
    ) -> None:
        """Each image is wrapped in a GLightbox anchor with a thumbnail img."""
        ad = _create_published_ad(seller, category, city, image_positions=[0, 1])
        client = Client()
        response =         client.get(reverse("ads:detail", args=[ad.id]))
        content = response.content.decode()
        for pos in [0, 1]:
            assert f'href="/media/key-{pos}.jpg"' in content
            assert 'class="glightbox"' in content
            assert 'data-gallery="ad-gallery"' in content
            assert f'src="/media/key-{pos}-large.jpg"' in content

    def test_glightbox_init_options_present(
        self, seller: User, category: Category, city: City
    ) -> None:
        """The GLightbox init exposes the expected interaction options."""
        ad = _create_published_ad(seller, category, city, image_positions=[0])
        client = _consent_client()
        response =         client.get(reverse("ads:detail", args=[ad.id]))
        content = response.content.decode()
        for option in [
            "touchNavigation",
            "loop",
            "zoomable",
            "closeOnOutsideClick",
            "navigation",
        ]:
            assert option in content

    def test_images_render_in_position_order(
        self, seller: User, category: Category, city: City
    ) -> None:
        """Anchors appear in AdImage.position order within the gallery block."""
        ad = _create_published_ad(seller, category, city, image_positions=[2, 0, 1])
        client = Client()
        response = client.get(reverse("ads:detail", args=[ad.id]))
        content = response.content.decode()
        # Collect the ordered full-image hrefs as rendered in the gallery.
        hrefs = re.findall(r'href="(/media/key-\d+\.jpg)"', content)
        assert hrefs == [
            "/media/key-0.jpg",
            "/media/key-1.jpg",
            "/media/key-2.jpg",
        ]

    def test_single_image_single_anchor(
        self, seller: User, category: Category, city: City
    ) -> None:
        """An ad with one image renders exactly one GLightbox anchor."""
        ad = _create_published_ad(seller, category, city, image_positions=[0])
        client = Client()
        response =         client.get(reverse("ads:detail", args=[ad.id]))
        content = response.content.decode()
        assert content.count('class="glightbox"') == 1

    def test_no_images_no_gallery_block(
        self, seller: User, category: Category, city: City
    ) -> None:
        """An ad with no images renders no gallery anchors."""
        ad = _create_published_ad(seller, category, city, image_positions=[])
        client = Client()
        response =         client.get(reverse("ads:detail", args=[ad.id]))
        assert response.status_code == 200
        content = response.content.decode()
        assert 'class="glightbox"' not in content
        assert "data-gallery=" not in content

    def test_static_grid_renders_without_js(
        self, seller: User, category: Category, city: City
    ) -> None:
        """No-JS fallback: the static grid <img> elements keep valid src."""
        ad = _create_published_ad(seller, category, city, image_positions=[0, 1])
        client = Client()
        response =         client.get(reverse("ads:detail", args=[ad.id]))
        content = response.content.decode()
        assert 'src="/media/key-0-large.jpg"' in content
        assert 'src="/media/key-1-large.jpg"' in content
