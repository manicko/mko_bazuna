"""
View-layer tests for consent views (TST-004).

Covers:
- consent_accept: sets consent_given_at + cookie, redirects
- consent_decline: sets ads_auto_publish=False + cookie, redirects
- consent_withdraw: soft-deletes user + ads, nulls PII, sets cookie, redirects
- Authentication required for all consent views
"""

import hashlib
from datetime import timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from pydantic import ValidationError

from apps.categories.models import Category
from apps.core.enums import AdStatus, ConsentChoice
from apps.core.utils.preferred_city_cookie import PREFERRED_CITY_COOKIE_NAME
from apps.locations.models import City
from apps.users.models import ConsentRecord, LoginToken, User
from apps.users.schemas import ConsentSubmission
from apps.users.services.login_token import LOGIN_BROWSER_ID_COOKIE
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Tests: consent_accept
# ---------------------------------------------------------------------------


class TestConsentAcceptView:
    """consent_accept view sets consent_given_at and redirects."""

    def test_accept_anonymous_redirects_home_and_sets_cookie(self) -> None:
        """Anonymous POST accept redirects home and sets consent cookies."""
        client = Client()
        response = client.post("/consent/accept/")

        assert response.status_code == 302
        assert response.url == "/"

        # No DB write for anonymous consent (security gate D-3).
        assert (
            ConsentRecord.objects.filter(
                user__isnull=False, choice=ConsentChoice.ACCEPTED
            ).count()
            == 0
        )

    def test_accept_requires_post(self) -> None:
        """GET /consent/accept/ is rejected (405 Method Not Allowed)."""
        client = Client()
        response = client.get("/consent/accept/")
        assert response.status_code == 405

    def test_accept_sets_consent_given_at(self, user: User) -> None:
        """consent_accept sets consent_given_at on the user."""
        client = Client()
        client.force_login(user)
        response = client.post("/consent/accept/")

        assert response.status_code == 302
        # Check redirect target
        assert response.url == "/dashboard/"  # noqa: S105

        # Verify user state
        user.refresh_from_db()
        assert user.consent_given_at is not None
        assert user.consent_revoked_at is None
        assert user.is_deleted is False

    def test_accept_sets_consent_cookie(self, user: User) -> None:
        """consent_accept sets the structured consent_given cookie."""
        client = Client()
        client.force_login(user)
        response = client.post("/consent/accept/")

        assert response.cookies.get("consent_given") is not None
        assert response.cookies["consent_given"].value == "accepted"

    def test_accept_sets_category_cookies(self, user: User) -> None:
        """consent_accept sets analytics and preferences cookies to 'true'."""
        client = Client()
        client.force_login(user)
        response = client.post("/consent/accept/")

        assert response.cookies["consent_analytics"].value == "true"
        assert response.cookies["consent_preferences"].value == "true"

    def test_accept_cookie_has_secure_flag(self, user: User) -> None:
        """consent cookies are marked Secure (T-05 / D-COOKIES)."""
        client = Client()
        client.force_login(user)
        response = client.post("/consent/accept/")

        for name in ("consent_given", "consent_analytics", "consent_preferences"):
            assert response.cookies[name]["secure"] is True, name

    def test_anonymous_accept_sets_cookie_no_db_write(self) -> None:
        """Anonymous accept sets cookies without creating a DB record."""
        client = Client()
        before = ConsentRecord.objects.count()
        response = client.post("/consent/accept/")

        assert response.status_code == 302
        assert response.url == "/"
        assert response.cookies["consent_given"].value == "accepted"
        assert response.cookies["consent_analytics"].value == "true"
        assert response.cookies["consent_preferences"].value == "true"
        # Exactly one consent record, with a null user (anonymous identity).
        assert ConsentRecord.objects.count() == before + 1
        record = ConsentRecord.objects.order_by("-id").first()
        assert record.user_id is None

    def test_accept_after_decline_restores_publishing(self, user: User) -> None:
        """Accept after decline clears is_declined and restores ads_auto_publish (D6)."""
        client = Client()
        client.force_login(user)

        client.post("/consent/decline/")
        user.refresh_from_db()
        assert user.is_declined is True
        assert user.ads_auto_publish is False

        client.post("/consent/accept/")
        user.refresh_from_db()
        assert user.is_declined is False
        assert user.ads_auto_publish is True
        assert user.consent_given_at is not None

    def test_accept_rejected_on_deleted_user(self, deleted_user: User) -> None:
        """POST /consent/accept/ by a soft-deleted user returns 403."""
        deleted_user.consent_revoked_at = timezone.now()
        deleted_user.save(update_fields=["consent_revoked_at"])

        client = Client()
        client.force_login(deleted_user)
        response = client.post("/consent/accept/")

        assert response.status_code == 403
        # No ConsentRecord(choice=ACCEPTED) created for the deleted identity
        assert ConsentRecord.objects.filter(choice=ConsentChoice.ACCEPTED).count() == 0
        # User state unchanged -- consent_revoked_at NOT cleared
        deleted_user.refresh_from_db()
        assert deleted_user.is_deleted is True
        assert deleted_user.consent_revoked_at is not None

    def test_accept_no_consent_record_on_deleted_user(self, deleted_user: User) -> None:
        """No ConsentRecord at all is created when a soft-deleted user accepts."""
        deleted_user.consent_revoked_at = timezone.now()
        deleted_user.save(update_fields=["consent_revoked_at"])

        client = Client()
        client.force_login(deleted_user)
        response = client.post("/consent/accept/")

        assert response.status_code == 403
        assert ConsentRecord.objects.count() == 0


# ---------------------------------------------------------------------------
# Tests: consent_decline
# ---------------------------------------------------------------------------


class TestConsentDeclineView:
    """consent_decline view sets ads_auto_publish=False and redirects."""

    def test_decline_requires_post(self) -> None:
        """GET /consent/decline/ is rejected (405 Method Not Allowed)."""
        client = Client()
        response = client.get("/consent/decline/")
        assert response.status_code == 405

    def test_anonymous_decline_sets_cookie_no_db_write(self) -> None:
        """Anonymous decline redirects home, sets declined cookie, no DB write."""
        client = Client()
        response = client.post("/consent/decline/")

        assert response.status_code == 302
        assert response.url == "/"
        assert response.cookies["consent_given"].value == "declined"
        assert response.cookies["consent_analytics"].value == "false"
        assert response.cookies["consent_preferences"].value == "true"
        # Anonymous consent never persists a DB record for a user account.
        assert (
            ConsentRecord.objects.filter(
                user__isnull=False, choice=ConsentChoice.DECLINED
            ).count()
            == 0
        )

    def test_decline_sets_ads_auto_publish_false(self, user: User) -> None:
        """consent_decline sets ads_auto_publish=False and is_declined=True."""
        client = Client()
        client.force_login(user)
        response = client.post("/consent/decline/")

        assert response.status_code == 302
        assert response.url == "/dashboard/"

        # Verify user state
        user.refresh_from_db()
        assert user.ads_auto_publish is False
        assert user.is_declined is True
        assert user.consent_given_at is None
        assert user.consent_revoked_at is None
        assert user.is_deleted is False
        assert user.telegram_id is not None  # PII preserved

    def test_decline_sets_declined_cookie(self, user: User) -> None:
        """consent_decline sets the consent_given cookie to 'declined'."""
        client = Client()
        client.force_login(user)
        response = client.post("/consent/decline/")

        assert response.cookies.get("consent_given") is not None
        assert response.cookies["consent_given"].value == "declined"
        assert response.cookies["consent_analytics"].value == "false"
        # Preferences remain available even on decline (PO-02).
        assert response.cookies["consent_preferences"].value == "true"

    def test_decline_clears_preferred_city_and_expires_cookie_on_https(
        self, user: User, city: City
    ) -> None:
        """A decline clears the column and expires the cookie over HTTPS (06-PII-110).

        Over HTTPS the deletion mirrors the write's ``Secure`` flag. ``set_cookie``
        is used rather than ``delete_cookie`` because Django 5.2's
        ``delete_cookie()`` has no ``secure`` parameter; the only one-flag route
        back through it (``samesite="none"``) would make the cookie cross-site
        capable. ``secure=True`` on the test client makes ``request.is_secure()``
        true, mirroring production nginx TLS. Modelled on
        ``apps/search/tests/test_preferred_city.py::TestReset::
        test_clear_deletion_cookie_mirrors_attributes_on_https``.
        """
        user.preferred_city = city
        user.save(update_fields=["preferred_city"])

        client = Client()
        client.force_login(user)
        response = client.post("/consent/decline/", secure=True)

        assert response.status_code == 302
        # The DB column is cleared.
        user.refresh_from_db()
        assert user.preferred_city_id is None
        # The cookie is expired with the write's secure attributes.
        cookie = response.cookies[PREFERRED_CITY_COOKIE_NAME]
        assert cookie.value == ""
        assert int(cookie["max-age"]) == 0
        assert cookie["secure"] is True
        assert cookie["samesite"] == "Lax"
        assert cookie["httponly"] is True
        assert cookie["path"] == "/"
        # The decline still records preferences as true (PO-02 unchanged).
        assert response.cookies["consent_preferences"].value == "true"
        # An already-expired Set-Cookie, not delete_cookie().
        assert cookie.key == PREFERRED_CITY_COOKIE_NAME

    def test_decline_clears_preferred_city_without_secure_flag_on_http(
        self, user: User, city: City
    ) -> None:
        """On a plain-HTTP origin the decline's expiry is emitted **without** ``Secure``.

        The ``preferred_city`` cookie is written with
        ``secure=request.is_secure()``, so on plain HTTP it is stored without
        ``Secure``. A ``Set-Cookie`` carrying ``Secure`` is rejected outright on
        a non-secure origin, so the deletion must likewise omit ``Secure`` or it
        could not take effect at all on ``dev``/``test`` (where
        ``SECURE_SSL_REDIRECT = False``). This is the regression the previous
        hard-coded ``secure=True`` helper introduced.
        """
        user.preferred_city = city
        user.save(update_fields=["preferred_city"])

        client = Client()
        client.force_login(user)
        response = client.post("/consent/decline/")  # not secure

        assert response.status_code == 302
        user.refresh_from_db()
        assert user.preferred_city_id is None
        cookie = response.cookies[PREFERRED_CITY_COOKIE_NAME]
        assert cookie.value == ""
        assert int(cookie["max-age"]) == 0
        assert cookie["secure"] == ""
        assert cookie["samesite"] == "Lax"
        assert cookie["httponly"] is True
        assert cookie["path"] == "/"

    def test_decline_rejected_on_deleted_user(self, deleted_user: User) -> None:
        """POST /consent/decline/ by a soft-deleted user returns 403."""
        deleted_user.consent_revoked_at = timezone.now()
        deleted_user.save(update_fields=["consent_revoked_at"])

        client = Client()
        client.force_login(deleted_user)
        response = client.post("/consent/decline/")

        assert response.status_code == 403
        # No ConsentRecord(choice=DECLINED) created for the deleted identity
        assert ConsentRecord.objects.filter(choice=ConsentChoice.DECLINED).count() == 0
        # User state unchanged
        deleted_user.refresh_from_db()
        assert deleted_user.is_deleted is True


# ---------------------------------------------------------------------------
# Tests: Known gap — consent_decline does not revoke the session (04-AUT-002)
# ---------------------------------------------------------------------------


class TestConsentDeclineSessionKnownGap:
    """Pin that ``consent_decline`` does not revoke the session, and stays usable.

    Known gap: ``consent_decline`` performs no ``logout()``. The session survives,
    but the decline path is a deliberately retained one-way door — this block
    (``B-07``, gate ``G-7b``) decided NOT to ship a decline logout. The original
    rationale cited ``can_login(is_declined=True) is False`` to call the session
    "harmless"; that premise is now **void**: since 06-PII-105 a decline is
    reversible, ``can_login`` allows a declined user, and the session a decline
    left behind is the **route back**, not harmless — it is what makes the
    authenticated ``consent_accept`` (the only clearer of ``is_declined``)
    reachable. Adding a logout would remove the only working session the user
    has while the decline remains unclearable on the web.

    This is a red-to-green specification for phase 15's ``15-AUTHZ-001``: it
    turns red if a decline logout is ever shipped. Owner of the eventual fix:
    phase 15, ``15-AUTHZ-001`` (phase 06's ``PII-105`` owns decline
    reversibility). Produced by B-07 gate ``G-7b``.
    """

    def test_consent_decline_keeps_the_session_and_is_reversible(
        self, user: User
    ) -> None:
        """Pin G-7b: decline keeps the session live and the account re-acceptable.

        Vacuity guard: the session is asserted live before the decline and after
        it, so the test cannot pass on a client that was never logged in.
        """
        client = Client()
        client.force_login(user)
        assert "_auth_user_id" in client.session

        decline_response = client.post("/consent/decline/")
        assert decline_response.status_code == 302
        assert decline_response.url == "/dashboard/"  # noqa: S105

        user.refresh_from_db()
        assert user.is_declined is True
        assert user.ads_auto_publish is False

        # Known gap (G-7b): the session was NOT flushed.
        assert "_auth_user_id" in client.session

        # Decline is reversible through the authenticated accept path.
        accept_response = client.post("/consent/accept/")
        assert accept_response.status_code == 302

        user.refresh_from_db()
        assert user.is_declined is False
        assert user.ads_auto_publish is True


# ---------------------------------------------------------------------------
# Decline reversibility end to end (06-PII-105)
# ---------------------------------------------------------------------------


class TestDeclineThenAcceptEndToEnd:
    """Decline then accept through the real views restores the seller fully."""

    def test_decline_then_accept_restores_the_seller(self, user: User) -> None:
        """Decline → accept restores state, login eligibility, record and publish.

        Drives the real HTTP flow (``/consent/decline/`` then
        ``/consent/accept/``) rather than hand-constructing a row, so the
        assertion covers the actual ``decline_consent`` / ``give_consent``
        transitions.
        """
        from apps.users.services.account_state import can_login, can_publish_ad

        client = Client()
        client.force_login(user)

        decline_response = client.post("/consent/decline/")
        assert decline_response.status_code == 302

        user.refresh_from_db()
        assert user.is_declined is True
        assert user.ads_auto_publish is False
        assert can_publish_ad(user) is False

        accept_response = client.post("/consent/accept/")
        assert accept_response.status_code == 302

        user.refresh_from_db()
        assert user.is_declined is False
        assert user.ads_auto_publish is True
        assert can_login(user) is True
        assert can_publish_ad(user) is True
        assert user.consent_given_at is not None

        # The accept is recorded as an ACCEPTED ConsentRecord for the user.
        assert ConsentRecord.objects.filter(
            user=user, choice=ConsentChoice.ACCEPTED
        ).exists()


# ---------------------------------------------------------------------------
# Tests: consent_withdraw
# ---------------------------------------------------------------------------


class TestConsentWithdrawView:
    """consent_withdraw view soft-deletes user and ads, redirects."""

    def test_withdraw_requires_authentication(self) -> None:
        """Anonymous users are redirected to login."""
        client = Client()
        response = client.post("/consent/withdraw/")
        assert response.status_code == 302

    def test_withdraw_triggers_user_soft_delete(
        self,
        user: User,
        category: Category,
        city: City,
    ) -> None:
        """consent_withdraw soft-deletes the user, nulls PII, and marks consent revoked."""
        # Create some ads
        create_test_ad(user, category, city, title="Ad 1", status=AdStatus.PUBLISHED)
        create_test_ad(
            user, category, city, title="Ad 2", status=AdStatus.ON_MODERATION
        )

        client = Client()
        client.force_login(user)
        response = client.post("/consent/withdraw/")

        assert response.status_code == 302
        assert response.url == "/dashboard/"

        # Verify user state
        user.refresh_from_db()
        assert user.consent_revoked_at is not None
        assert user.is_deleted is True
        assert user.deleted_at is not None
        assert user.telegram_id is None  # PII nulled
        assert user.username is None

    def test_withdraw_soft_deletes_ads(
        self,
        user: User,
        category: Category,
        city: City,
    ) -> None:
        """consent_withdraw soft-deletes all user ads."""
        ad1 = create_test_ad(
            user, category, city, title="Published Ad", status=AdStatus.PUBLISHED
        )
        ad2 = create_test_ad(
            user, category, city, title="Draft Ad", status=AdStatus.DRAFT
        )

        client = Client()
        client.force_login(user)
        client.post("/consent/withdraw/")

        # Verify ads are soft-deleted
        ad1.refresh_from_db()
        ad2.refresh_from_db()
        assert ad1.status == AdStatus.DELETED
        assert ad1.deleted_at is not None
        assert ad2.status == AdStatus.DELETED
        assert ad2.deleted_at is not None

    def test_withdraw_sets_withdrawn_cookie(self, user: User) -> None:
        """consent_withdraw sets the consent_given cookie to 'withdrawn'."""
        client = Client()
        client.force_login(user)
        response = client.post("/consent/withdraw/")

        assert response.cookies.get("consent_given") is not None
        assert response.cookies["consent_given"].value == "withdrawn"

    def test_withdraw_button_renders_on_dashboard(self, user: User) -> None:
        """Authenticated users see the Withdraw Data button on the dashboard."""
        client = Client()
        client.force_login(user)
        response = client.get("/dashboard/?lang=ru")

        assert response.status_code == 200
        # The Withdraw Data button is present in the response
        assert "Удалить данные".encode() in response.content
        # The form posts to the consent withdrawal endpoint
        assert b'action="/consent/withdraw/"' in response.content

    def test_withdraw_flushes_session_and_redirects(self, user: User) -> None:
        """consent_withdraw flushes the session and redirects to the dashboard."""
        client = Client()
        client.force_login(user)
        assert "_auth_user_id" in client.session

        response = client.post("/consent/withdraw/")
        assert response.status_code == 302
        assert response.url == "/dashboard/"
        # Session flushed by django.contrib.auth.logout (04-AUT-002)
        assert "_auth_user_id" not in client.session

    def test_withdraw_workflow_returns_anonymous(self, user: User) -> None:
        """Login -> dashboard -> POST withdraw -> redirected -> anonymous again."""
        client = Client()
        client.force_login(user)

        # dashboard reachable while authenticated
        dashboard = client.get("/dashboard/")
        assert dashboard.status_code == 200

        # withdraw via POST redirects to the dashboard
        response = client.post("/consent/withdraw/")
        assert response.status_code == 302
        assert response.url == "/dashboard/"

        # subsequent dashboard request redirects to login (anonymous)
        response = client.get("/dashboard/")
        assert response.status_code == 302
        assert response.url.startswith("/login/issue/")


# ---------------------------------------------------------------------------
# Tests: login_status PII masking
# ---------------------------------------------------------------------------


class TestLoginStatusNoPii:
    """Tests that login_status does not leak raw telegram_id in logs (PII-002)."""

    def test_login_consume_no_raw_telegram_id(self, caplog) -> None:
        """login_status must not log raw telegram_id after token consumption."""
        telegram_id = 999888777

        User.objects.create(
            telegram_id=telegram_id,
            chat_id=telegram_id,
            password="x",
        )

        # Issue through the real path so the row is bound to the client's
        # login-binding cookie (plain ``login_browser_id`` under test settings)
        # and the expected status stays 200.
        client = Client()
        issued = client.get("/login/issue/")
        raw_token = issued.context["raw_token"]
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        from apps.users.services.login_token import claim_token

        assert claim_token(token_hash, telegram_id, timezone.now()) is not None

        with caplog.at_level("INFO"):
            response = client.post("/login/status/", {"token": raw_token})

        assert response.status_code == 200
        # Raw telegram_id must not appear in any log output
        assert str(telegram_id) not in caplog.text
        # Masked value should be present for log correlation
        assert "tg_" in caplog.text

    def test_login_unbound_refusal_logs_no_pii(self, caplog) -> None:
        """The UNBOUND refusal log line must not leak the browser binding (D-4).

        ``TestLoginStatusNoPii`` previously exercised only the 200/CONSUMED
        path, so nothing would catch a future edit adding the browser id or the
        raw binding digest to the mismatch warning. This drives the *mismatch*
        path and asserts the warning carries none of: the presented browser id,
        its stored SHA-256 digest, or the raw telegram id.
        """
        telegram_id = 999888778
        # A well-formed 22-char URL-safe id (matches _BROWSER_ID_PATTERN), so the
        # presented value passes the shape check and drives the *digest-mismatch*
        # branch — the branch that must never log the digest — not the
        # malformed-presented-id sub-branch. A 21-char id would fullmatch-fail
        # and exercise the wrong path while the PII assertion still passed.
        browser_id = "attackerbrowserid00xyz"
        User.objects.create(
            telegram_id=telegram_id,
            chat_id=telegram_id,
            password="x",
        )

        issuer = Client()
        issued = issuer.get("/login/issue/")
        raw_token = issued.context["raw_token"]
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        from apps.users.services.login_token import claim_token

        assert claim_token(token_hash, telegram_id, timezone.now()) is not None

        # A different browser presents a different well-formed id -> mismatch.
        attacker = Client()
        attacker.cookies[LOGIN_BROWSER_ID_COOKIE] = browser_id

        with caplog.at_level("WARNING"):
            response = attacker.post("/login/status/", {"token": raw_token})

        assert response.status_code == 410
        # Neither the presented browser id, nor its digest, nor the raw
        # telegram id may appear in the refusal warning.
        assert browser_id not in caplog.text
        assert hashlib.sha256(browser_id.encode()).hexdigest() not in caplog.text
        assert str(telegram_id) not in caplog.text
        # The correlation prefix-only line is still emitted.
        assert token_hash[:8] in caplog.text


# ---------------------------------------------------------------------------
# Tests: consent banner guard for deleted users (PII-009)
# ---------------------------------------------------------------------------


@pytest.fixture
def deleted_user() -> User:
    """Create a soft-deleted user for banner visibility tests."""
    return User.objects.create(
        telegram_id=900000031,
        chat_id=900000031,
        password="x",
        is_deleted=True,
    )


class TestConsentBannerGuard:
    """Consent banner is suppressed for deleted users (PII-009).

    The banner include in every template is guarded by:
    ``{% if not request.user.is_authenticated or not request.user.is_deleted %}``
    so that soft-deleted users never see the consent banner.

    These assertions use the **public listings page**, not the dashboard: under
    the create-time storage-consent gate (06-PII-109) a never-consented user is
    refused the dashboard with a 403, so the dashboard can no longer be the
    surface where an un-consented banner is observed. The public page carries
    the same banner include and the same guard.
    """

    def test_banner_hidden_for_deleted_user(self, deleted_user: User) -> None:
        """Deleted users do *not* see the consent banner on the public page."""
        client = Client()
        client.force_login(deleted_user)
        response = client.get(reverse("ads:listings"))

        assert response.status_code == 200
        assert b"consent-banner" not in response.content

    def test_banner_shown_for_active_user(self) -> None:
        """Active, non-consenting users see the consent banner on the public page."""
        un_consented = User.objects.create(
            telegram_id=900000032,
            chat_id=900000032,
            password="x",
        )
        assert un_consented.consent_given_at is None
        client = Client()
        client.force_login(un_consented)
        response = client.get(reverse("ads:listings"))

        assert response.status_code == 200
        assert b"consent-banner" in response.content


# ---------------------------------------------------------------------------
# consent_withdraw idempotency on already-deleted user (decision F)
# ---------------------------------------------------------------------------


class TestConsentWithdrawIdempotency:
    """withdraw_consent is a no-op for already soft-deleted users.

    When ``user.is_deleted`` is already True the service returns ``[]``
    immediately: no LoginToken deletion, no PII nulling, no ad soft-delete,
    and no filesystem removal (the row was already withdrawn).
    """

    def test_consent_withdraw_idempotent_on_deleted_user(
        self, deleted_user: User
    ) -> None:
        """withdraw_consent on a deleted user returns [] and leaves PII/tokens."""
        from apps.users.services.deletion import withdraw_consent

        # A pre-existing login token must survive the idempotent no-op.
        LoginToken.objects.create(
            token_hash="0" * 64,
            telegram_id=deleted_user.telegram_id,
            expires_at=timezone.now() + timedelta(hours=1),
        )

        result = withdraw_consent(deleted_user)

        # No-op contract: empty result, no side effects.
        assert result == []

        # PII preserved (telegram_id not re-nulled).
        deleted_user.refresh_from_db()
        assert deleted_user.telegram_id == 900000031

        # Login token survives the idempotent no-op.
        assert LoginToken.objects.filter(
            telegram_id=deleted_user.telegram_id
        ).exists()


# ---------------------------------------------------------------------------
# ConsentSubmission DTO extra-field rejection (CC-2)
# ---------------------------------------------------------------------------


class TestConsentSubmissionExtraForbid:
    """``ConsentSubmission`` rejects unknown/extra fields (extra="forbid").

    The consent producer strips the always-present ``csrfmiddlewaretoken``
    before validation (see ``apps.users.views.consent._parse_submission``),
    so an unknown key on the DTO indicates a genuinely malformed submission.
    """

    def test_consent_submission_rejects_unknown_key(self) -> None:
        """An unknown key on ``ConsentSubmission`` raises ``ValidationError``."""
        with pytest.raises(ValidationError):
            ConsentSubmission(choice=ConsentChoice.ACCEPTED, rogue="x")

    def test_consent_submission_accepts_declared_fields(self) -> None:
        """``ConsentSubmission`` validates cleanly with declared fields only."""
        submission = ConsentSubmission(
            choice=ConsentChoice.ACCEPTED,
            analytics="true",
            preferences="false",
        )
        assert submission.analytics is True
        assert submission.preferences is False
