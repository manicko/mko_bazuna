"""
GLightbox gallery markup tests (TST-GAL-001 / spec 13).

Verifies the ad-detail gallery wiring for PUBLISHED ads with images:
- The GLightbox CSS link, JS script, and inline init are present on the page
- The gallery uses a slider layout: main image (glightbox anchor), prev/next
  arrow buttons, hidden glightbox anchors for remaining images, and a
  horizontal thumbnail strip with data-index/data-full-url/data-thumb-url attrs
- Thumbnail buttons render in AdImage.position order
- Single-image and no-image branches are preserved
- No-JS progressive enhancement: the main <img> keeps a valid src
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


def _gallery_html(ad: Ad) -> str:
    """Render the detail page (no consent) in English and return decoded content.

    English is used so `{% trans %}` strings (e.g. "Previous image") render as
    their literal msgid, making the assertions independent of the default
    ``LANGUAGE_CODE`` (``ru``). The language is selected via ``?lang=en``, which
    the LanguagePreMiddleware resolves.
    """
    client = Client()
    response = client.get(
        reverse("ads:detail", args=[ad.id]) + "?lang=en"
    )
    assert response.status_code == 200
    return response.content.decode()


class TestGalleryMarkup:
    """Ad detail page renders the GLightbox gallery for published ads."""

    def test_detail_contains_glightbox_assets(
        self, seller: User, category: Category, city: City
    ) -> None:
        """The GLightbox CSS link, JS script, and inline init are present."""
        ad = _create_published_ad(seller, category, city, image_positions=[0, 1])
        client = _consent_client()
        response = client.get(reverse("ads:detail", args=[ad.id]))
        assert response.status_code == 200
        content = response.content.decode()
        assert "glightbox.min.css" in content
        assert "glightbox.min.js" in content
        assert "GLightbox({" in content

    def test_detail_gallery_has_slider_structure(
        self, seller: User, category: Category, city: City
    ) -> None:
        """The detail gallery has the slider structure: main image, arrows, thumbnails."""
        ad = _create_published_ad(seller, category, city, image_positions=[0, 1])
        content = _gallery_html(ad)
        # Main image img with primary thumbnail_large_url
        assert 'id="detail-main-image"' in content
        assert 'src="/media/key-0-large.jpg"' in content
        assert 'object-contain' in content
        # Main image GLightbox anchor
        assert 'id="detail-main-link"' in content
        assert 'class="glightbox"' in content
        assert 'data-gallery="ad-gallery"' in content
        assert 'href="/media/key-0.jpg"' in content
        # Prev/next arrow buttons
        assert 'id="detail-prev"' in content
        assert 'id="detail-next"' in content
        assert 'Previous image' in content
        assert 'Next image' in content
        # Thumbnail strip
        assert 'id="detail-thumbs"' in content
        assert 'data-detail-thumbs' in content
        # AC1: the main-image container has an aspect-ratio utility to prevent
        # cumulative-layout-shift before the image finishes loading
        assert 'aspect-' in content, "Gallery container must have an aspect-ratio class"
        # Thumbnail buttons with data attributes for all images
        assert 'data-index="0"' in content
        assert 'data-index="1"' in content
        assert 'data-full-url="/media/key-0.jpg"' in content
        assert 'data-full-url="/media/key-1.jpg"' in content
        assert 'data-thumb-url="/media/key-0-large.jpg"' in content
        assert 'data-thumb-url="/media/key-1-large.jpg"' in content

    def test_detail_main_image_uses_object_contain(
        self, seller: User, category: Category, city: City
    ) -> None:
        """The main detail image uses object-contain (not object-cover)."""
        ad = _create_published_ad(seller, category, city, image_positions=[0, 1])
        content = _gallery_html(ad)
        # Main image must use object-contain for aspect-ratio preservation
        assert 'object-contain' in content
        # The main image ID element must not use object-cover
        main_img_match = re.search(
            r'id="detail-main-image"[^>]*class="([^"]*)"', content
        )
        assert main_img_match is not None
        main_img_class = main_img_match.group(1)
        assert "object-contain" in main_img_class
        assert "object-cover" not in main_img_class

    def test_detail_thumbnails_use_object_cover(
        self, seller: User, category: Category, city: City
    ) -> None:
        """Thumbnail strip <img> elements use object-cover for uniform cropping."""
        ad = _create_published_ad(seller, category, city, image_positions=[0, 1])
        content = _gallery_html(ad)
        # Each thumbnail <img> inside the strip uses object-cover
        thumb_imgs = re.findall(r'<img[^>]*class="[^"]*object-cover[^"]*"[^>]*>', content)
        assert len(thumb_imgs) >= 2, "Expected at least 2 thumbnail imgs with object-cover"

    def test_detail_glightbox_href_sync(
        self, seller: User, category: Category, city: City
    ) -> None:
        """The GLightbox anchor #detail-main-link has href matching the first image."""
        ad = _create_published_ad(seller, category, city, image_positions=[0, 1])
        content = _gallery_html(ad)
        match = re.search(
            r'id="detail-main-link"[^>]*\bhref="([^"]+)"', content
        )
        assert match is not None, "detail-main-link anchor not found"
        href = match.group(1)
        assert href == "/media/key-0.jpg", f"Expected href '/media/key-0.jpg', got '{href}'"

    def test_detail_prev_next_buttons_present(
        self, seller: User, category: Category, city: City
    ) -> None:
        """Prev/next buttons exist with aria-labels for single+ image ads."""
        ad = _create_published_ad(seller, category, city, image_positions=[0, 1])
        content = _gallery_html(ad)
        assert 'id="detail-prev"' in content
        assert 'id="detail-next"' in content
        assert "Previous image" in content
        assert "Next image" in content

    def test_glightbox_init_options_present(
        self, seller: User, category: Category, city: City
    ) -> None:
        """The GLightbox init exposes the expected interaction options."""
        ad = _create_published_ad(seller, category, city, image_positions=[0])
        client = _consent_client()
        response = client.get(reverse("ads:detail", args=[ad.id]))
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
        """Thumbnail buttons render in AdImage.position order."""
        ad = _create_published_ad(seller, category, city, image_positions=[2, 0, 1])
        content = _gallery_html(ad)
        indices = re.findall(r'data-index="(\d+)"', content)
        assert indices == ["0", "1", "2"]
        full_urls = re.findall(r'data-full-url="(/media/key-\d+\.jpg)"', content)
        assert full_urls == [
            "/media/key-0.jpg",
            "/media/key-1.jpg",
            "/media/key-2.jpg",
        ]

    def test_single_image_single_anchor(
        self, seller: User, category: Category, city: City
    ) -> None:
        """An ad with one image renders exactly one GLightbox anchor."""
        ad = _create_published_ad(seller, category, city, image_positions=[0])
        content = _gallery_html(ad)
        assert content.count('class="glightbox"') == 1

    def test_no_images_no_gallery_block(
        self, seller: User, category: Category, city: City
    ) -> None:
        """An ad with no images renders no gallery anchors."""
        ad = _create_published_ad(seller, category, city, image_positions=[])
        content = _gallery_html(ad)
        assert 'class="glightbox"' not in content
        assert "data-gallery=" not in content

    def test_detail_no_template_comment_leakage(
        self, seller: User, category: Category, city: City
    ) -> None:
        """Multi-line template comments are stripped — no comment syntax or text
        leaks into the rendered HTML.

        Regression test: Django's ``tag_re`` does not use ``re.DOTALL``, so
        ``{# ... #}`` comments must be single-line. Multi-line comments must use
        ``{% comment %}...{% endcomment %}``. Using ``{# ... #}`` across
        multiple lines causes the raw comment text to appear as visible content.
        """
        ad = _create_published_ad(seller, category, city, image_positions=[0, 1])
        content = _gallery_html(ad)
        assert "Hidden GLightbox anchors" not in content
        assert "Minimal inline JS" not in content
        assert "GLightbox groups by" not in content
        assert "atomically so fullscreen" not in content
        assert "{#" not in content
        assert "#}" not in content

    def test_static_grid_renders_without_js(
        self, seller: User, category: Category, city: City
    ) -> None:
        """No-JS fallback: the main image <img> keeps a valid src from primary thumbnail_large_url."""
        ad = _create_published_ad(seller, category, city, image_positions=[0, 1])
        content = _gallery_html(ad)
        assert 'src="/media/key-0-large.jpg"' in content
