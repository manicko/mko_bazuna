"""
Shared auth-aware header rendering tests (TST-SCB-001 / spec 12).

Verifies the extracted ``components/header.html`` across representative pages:
- Anonymous visitors see a header "Login" link pointing to ``consent:login_issue``
- Authenticated sellers see Dashboard + a POST Logout form; no Admin link (non-staff)
- Staff sellers additionally see an Admin link
- The logout control is a POST form carrying a CSRF token
- ``login_issue.html`` renders 200 with the header present
- ``@login_required`` pages redirect anonymous users to ``/login/issue/``
- The Withdraw Data form is preserved on the dashboard (relocated into <main>)
- The consent banner still renders behind its per-page guard (CR9)
"""

import pytest
from collections.abc import Generator
from django.core.cache import cache
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.ads.models import Ad
from apps.categories.models import Category
from apps.core.enums import AdStatus
from apps.locations.models import City
from apps.users.models import User

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


@pytest.fixture(autouse=True)
def _clear_cache() -> Generator[None]:
    """Clear the Django cache between tests (login rate limiter state bleed)."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def user() -> User:
    """Create a non-staff authenticated user."""
    return User.objects.create(
        telegram_id=920000001,
        chat_id=920000001,
        password="x",
    )


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
def category() -> Category:
    """Create a leaf category for ad fixtures."""
    return Category.objects.create(
        name="Test Category",
        slug="test-category",
    )


@pytest.fixture
def city() -> City:
    """Create a city for ad fixtures."""
    return City.objects.create(
        country_code="ME",
        name="Test City",
        region="Test Region",
        slug="test-city",
    )


@pytest.fixture
def published_ad(user: User, category: Category, city: City) -> Ad:
    """Create a PUBLISHED ad for the authenticated seller."""
    return Ad.objects.create(
        user=user,
        title="Header Nav Ad",
        description="Header nav description",
        category=category,
        city=city,
        category_name=category.name,
        status=AdStatus.PUBLISHED,
        published_at=timezone.now(),
    )


class TestAnonymousHeader:
    """Public catalog pages render the Avito-style shared header.

    Per the catalog-ui spec (PO Q9 / R-05c), the public catalog and ad-detail
    pages use the shared ``header_catalog.html`` component, which carries the
    search bar and place-an-ad CTA rather than a login link (login lives on the
    seller pages). These assert that shared header renders on anonymous pages.
    """

    def test_home_renders_catalog_header(self) -> None:
        client = Client()
        response = client.get("/")
        assert response.status_code == 200
        content = response.content.decode()
        # Place-an-ad CTA + search input from header_catalog.html.
        assert "Подать объявление" in content
        assert 'id="search-input"' in content

    def test_detail_renders_catalog_header(self, published_ad: Ad) -> None:
        client = Client()
        response = client.get(reverse("ads:detail", args=[published_ad.id]))
        assert response.status_code == 200
        content = response.content.decode()
        assert "Подать объявление" in content
        assert 'id="search-input"' in content

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
