"""
Shared auth-aware header rendering tests (TST-SCB-001 / spec 12).

Verifies the extracted ``components/header.html`` across representative pages:
- Anonymous visitors on catalog/detail pages see an icon-only Login button in the header (header_catalog.html)
- Anonymous visitors on login/dashboard/cabinet pages see a Login link in the auth header (header.html)
- Authenticated sellers see Dashboard + a POST Logout form; no Admin link (non-staff)
- Staff sellers additionally see an Admin link
- The logout control is a POST form carrying a CSRF token
- ``login_issue.html`` renders 200 with the header present
- ``@login_required`` pages redirect anonymous users to ``/login/issue/``
- The Withdraw Data form is preserved on the dashboard (relocated into <main>)
- The consent banner still renders behind its per-page guard (CR9)
- Authenticated users see an avatar icon with a dropdown menu + heart-with-count badge in the catalog header
"""

import pytest
from collections.abc import Generator
from django.core.cache import cache
from django.test import Client
from django.urls import reverse

from apps.ads.models import Ad
from apps.categories.models import Category
from apps.core.enums import AdStatus
from apps.locations.models import City
from apps.users.models import User

from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


@pytest.fixture(autouse=True)
def _clear_cache() -> Generator[None]:
    """Clear the Django cache between tests (login rate limiter state bleed)."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def staff_user() -> User:
    """Create a staff user (admin-eligible)."""
    return User.objects.create(
        telegram_id=920000002,
        chat_id=920000002,
        password="x",
        is_staff=True,
    )


@pytest.fixture
def published_ad(user: User, category: Category, city: City) -> Ad:
    """Create a PUBLISHED ad for the authenticated seller."""
    return create_test_ad(
        user, category, city,
        title="Header Nav Ad",
        description="Header nav description",
        status=AdStatus.PUBLISHED,
    )


class TestAnonymousHeader:
    """Public catalog pages render the Avito-style shared header.

    Per the catalog-ui spec (R-06, §6 / 24_catalog-header-auth-entry_spec),
    the catalog header now includes an auth/cabinet entry in the top-right
    corner: an icon-only Login button (outline user icon) for anonymous
    visitors, and an avatar/filled-icon button with a dropdown menu plus a
    heart-with-count badge for authenticated users. See
    ``24_catalog-header-auth-entry_spec.md``.
    """

    def test_home_renders_catalog_header(self) -> None:
        client = Client()
        response = client.get("/")
        assert response.status_code == 200
        content = response.content.decode()
        # Place-an-ad CTA + search input from header_catalog.html.
        assert "Подать объявление" in content
        assert 'id="search-input"' in content
        # Auth entry: anonymous visitors see the Login button in the catalog header.
        assert "/login/issue/" in content
        assert "auth-entry" in content

    def test_detail_renders_catalog_header(self, published_ad: Ad) -> None:
        client = Client()
        response = client.get(reverse("ads:detail", args=[published_ad.id]))
        assert response.status_code == 200
        content = response.content.decode()
        assert "Подать объявление" in content
        assert 'id="search-input"' in content
        # Auth entry: anonymous visitors see the Login button in the catalog header.
        assert "/login/issue/" in content
        assert "auth-entry" in content

    def test_login_issue_renders_header(self) -> None:
        client = Client()
        response = client.get("/login/issue/")
        assert response.status_code == 200
        content = response.content.decode()
        assert ">Login<" in content

    def test_login_required_redirects_to_login_issue(self) -> None:
        client = Client()
        response = client.get("/dashboard/")
        assert response.status_code == 302
        assert response.url.startswith("/login/issue/")


class TestAuthenticatedHeader:
    """Authenticated sellers see Dashboard + POST Logout; staff see Admin."""

    def test_seller_sees_dashboard_and_post_logout(self, user: User) -> None:
        client = Client()
        client.force_login(user)
        response = client.get(reverse("ads:dashboard"))
        assert response.status_code == 200
        content = response.content.decode()
        # Header Dashboard link
        assert 'href="/dashboard/"' in content
        assert "Logout" in content
        # Logout is a POST form with a CSRF token posting to /logout/
        assert 'action="/logout/"' in content
        assert "csrfmiddlewaretoken" in content
        # Non-staff seller sees no Admin link
        assert 'href="/admin/"' not in content

    def test_staff_sees_admin_link(self, staff_user: User) -> None:
        client = Client()
        client.force_login(staff_user)
        response = client.get(reverse("ads:dashboard"))
        assert response.status_code == 200
        content = response.content.decode()
        assert 'href="/admin/"' in content

    def test_withdraw_form_preserved_on_dashboard(self, user: User) -> None:
        """The Withdraw Data form is preserved (relocated into <main>)."""
        client = Client()
        client.force_login(user)
        response = client.get(reverse("ads:dashboard"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "Withdraw Data" in content
        assert 'action="/consent/withdraw/"' in content

    def test_consent_banner_shown_for_active_user(self, user: User) -> None:
        """Unacted authenticated users still see the consent banner (CR9)."""
        client = Client()
        client.force_login(user)
        response = client.get(reverse("ads:dashboard"))
        assert response.status_code == 200
        assert b"consent-banner" in response.content

    def test_authenticated_catalog_header_shows_dropdown_and_badge(self, user: User) -> None:
        """Authenticated users on the homepage see the avatar button + dropdown
        and the favorites heart badge in the catalog header (CR2, CR4, CR6)."""
        client = Client()
        client.force_login(user)
        response = client.get("/")
        assert response.status_code == 200
        content = response.content.decode()
        # Dropdown toggle button + menu present.
        assert "data-header-auth-toggle" in content
        assert "data-header-auth-menu" in content
        # Menu entries.
        assert 'href="/cabinet/"' in content
        assert 'href="/dashboard/"' in content
        assert 'action="/logout/"' in content
        # Non-staff sees no admin link.
        assert 'href="/admin/"' not in content
        # Favorites heart badge links to the cabinet favorites page.
        assert 'aria-label="My favorites"' in content
