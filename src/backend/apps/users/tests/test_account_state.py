"""
Tests for account-state gating logic (TST-010).

Covers the full flag matrix for:
- can_publish_ad (banned, deleted, ads_auto_publish=False, combinations)
- can_login (banned, declined, combinations)
- get_account_state
- get_state_badge
- account_state_q (queryset-level predicate, 06-PII-104)

The queryset-level tests live in this module (not a sibling) because the
instance-level ``get_account_state`` matrix above is exactly what
``account_state_q`` must agree with; keeping them together makes the drift
tripwire reviewable in one file.
"""

import os
import subprocess
import sys

import pytest
from django.db.models import Q

from apps.ads.models import Ad
from apps.search.models import SavedSearch
from apps.users.models import User
from apps.users.services import (
    AccountState,
    can_login,
    can_publish_ad,
    get_account_state,
    get_state_badge,
)
from apps.users.services.account_state import account_state_q
from conftest import create_test_ad, make_user

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Tests: get_account_state
# ---------------------------------------------------------------------------


class TestGetAccountState:
    """get_account_state returns correct flag snapshot."""

    def test_default_state(self, user: User) -> None:
        """Default user has all flags at false/true defaults."""
        state = get_account_state(user)
        assert state == AccountState(
            is_banned=False,
            is_deleted=False,
            is_declined=False,
            ads_auto_publish=True,
            consent_revoked=False,
        )

    def test_banned_user(self) -> None:
        """Banned user has is_banned=True."""
        u = make_user(900001001, is_banned=True)
        state = get_account_state(u)
        assert state.is_banned is True

    def test_deleted_user(self) -> None:
        """Deleted user has is_deleted=True."""
        u = make_user(900001002, is_deleted=True)
        state = get_account_state(u)
        assert state.is_deleted is True

    def test_declined_user(self) -> None:
        """Declined user has is_declined=True."""
        u = make_user(900001003, is_declined=True)
        state = get_account_state(u)
        assert state.is_declined is True

    def test_restricted_user(self) -> None:
        """Restricted user has ads_auto_publish=False."""
        u = make_user(900001004, ads_auto_publish=False)
        state = get_account_state(u)
        assert state.ads_auto_publish is False

    def test_consent_revoked(self, user: User) -> None:
        """User with consent_revoked_at set has consent_revoked=True."""
        from django.utils import timezone

        user.consent_revoked_at = timezone.now()
        user.save(update_fields=["consent_revoked_at"])
        state = get_account_state(user)
        assert state.consent_revoked is True


# ---------------------------------------------------------------------------
# Tests: can_publish_ad  — flag matrix
# ---------------------------------------------------------------------------


class TestCanPublishAd:
    """Flag matrix for can_publish_ad: banned, deleted, ads_auto_publish."""

    def test_normal_user_can_publish(self, user: User) -> None:
        """Default user (no flags set) can publish."""
        assert can_publish_ad(user) is True

    def test_banned_user_cannot_publish(self) -> None:
        """Banned user cannot publish regardless of other flags."""
        u = make_user(900001010, is_banned=True)
        assert can_publish_ad(u) is False

    def test_banned_and_restricted_cannot_publish(self) -> None:
        """Banned + restricted still cannot publish (banned takes priority in check order)."""
        u = make_user(900001011, is_banned=True, ads_auto_publish=False)
        assert can_publish_ad(u) is False

    def test_banned_and_deleted_cannot_publish(self) -> None:
        """Banned + deleted cannot publish."""
        u = make_user(900001012, is_banned=True, is_deleted=True)
        assert can_publish_ad(u) is False

    def test_deleted_user_cannot_publish(self) -> None:
        """Deleted user cannot publish."""
        u = make_user(900001013, is_deleted=True)
        assert can_publish_ad(u) is False

    def test_deleted_and_restricted_cannot_publish(self) -> None:
        """Deleted + restricted cannot publish."""
        u = make_user(900001014, is_deleted=True, ads_auto_publish=False)
        assert can_publish_ad(u) is False

    def test_restricted_user_cannot_publish(self) -> None:
        """User with ads_auto_publish=False cannot publish."""
        u = make_user(900001015, ads_auto_publish=False)
        assert can_publish_ad(u) is False

    def test_declined_user_can_publish(self) -> None:
        """Declined user CAN publish (decline only blocks login, not publishing)."""
        u = make_user(900001016, is_declined=True)
        assert can_publish_ad(u) is True

    def test_all_flags_cannot_publish(self) -> None:
        """All restriction flags together still cannot publish."""
        u = make_user(
            900001017,
            is_banned=True,
            is_deleted=True,
            is_declined=True,
            ads_auto_publish=False,
        )
        assert can_publish_ad(u) is False


# ---------------------------------------------------------------------------
# Tests: can_login  — flag matrix
# ---------------------------------------------------------------------------


class TestCanLogin:
    """Flag matrix for can_login: banned, declined."""

    def test_normal_user_can_login(self, user: User) -> None:
        """Default user can login."""
        assert can_login(user) is True

    def test_banned_user_cannot_login(self) -> None:
        """Banned user cannot login."""
        u = make_user(900001020, is_banned=True)
        assert can_login(u) is False

    def test_declined_user_cannot_login(self) -> None:
        """User who declined consent cannot login."""
        u = make_user(900001021, is_declined=True)
        assert can_login(u) is False

    def test_banned_and_declined_cannot_login(self) -> None:
        """Banned + declined cannot login."""
        u = make_user(900001022, is_banned=True, is_declined=True)
        assert can_login(u) is False

    def test_deleted_user_can_login_by_flag(self) -> None:
        """Deleted user CAN login by flag (telegram_id is nulled in practice).

        Note: can_login does not check is_deleted. Deleted users cannot actually
        authenticate because their telegram_id is nulled, but the gating function
        treats them as eligible. This is intentional per the docstring.
        """
        u = make_user(900001023, is_deleted=True)
        assert can_login(u) is True

    def test_restricted_user_can_login(self) -> None:
        """User with ads_auto_publish=False can still login."""
        u = make_user(900001024, ads_auto_publish=False)
        assert can_login(u) is True


# ---------------------------------------------------------------------------
# Tests: get_state_badge
# ---------------------------------------------------------------------------


class TestGetStateBadge:
    """get_state_badge returns correct badge text."""

    def test_normal_user_empty_badge(self, user: User) -> None:
        """Default user has empty badge."""
        assert get_state_badge(user) == ""

    def test_banned_badge(self) -> None:
        """Banned user shows 'banned'."""
        u = make_user(900001030, is_banned=True)
        assert get_state_badge(u) == "banned"

    def test_deleted_badge(self) -> None:
        """Deleted user shows 'deleted'."""
        u = make_user(900001031, is_deleted=True)
        assert get_state_badge(u) == "deleted"

    def test_declined_badge(self) -> None:
        """Declined user shows 'declined'."""
        u = make_user(900001032, is_declined=True)
        assert get_state_badge(u) == "declined"

    def test_restricted_badge(self) -> None:
        """Restricted user shows 'restricted'."""
        u = make_user(900001033, ads_auto_publish=False)
        assert get_state_badge(u) == "restricted"

    def test_all_flags_combined_badge(self) -> None:
        """All flags together show comma-separated badges."""
        u = make_user(
            900001034,
            is_banned=True,
            is_deleted=True,
            is_declined=True,
            ads_auto_publish=False,
        )
        badge = get_state_badge(u)
        assert "banned" in badge
        assert "deleted" in badge
        assert "declined" in badge
        assert "restricted" in badge

    def test_no_badge_for_default_user(self) -> None:
        """User with default flags returns empty string."""
        u = make_user(900001035)
        assert get_state_badge(u) == ""


# ---------------------------------------------------------------------------
# Tests: account_state_q — queryset-level predicate (06-PII-104)
#
# Every per-state test creates its OWN user via ``make_user`` with a unique
# telegram_id. The shared ``seller`` / ``user`` / ``buyer`` fixtures use
# ``get_or_create`` on a fixed id and survive ``--reuse-db``, so mutating them
# would leak state across xdist workers (see BLOCK 6 test-isolation note).
# ---------------------------------------------------------------------------

# Unique telegram_ids for this section — the existing matrix uses 9000010xx.
_QS_BASE = 900001100


def _state_user(offset: int, **flags: object) -> User:
    """Create a fresh user for a queryset-level case."""
    return make_user(_QS_BASE + offset, **flags)


def _is_eligible(user: User) -> bool:
    """The predicate's verdict for a single ``User`` row, as a bool."""
    return User.objects.filter(pk=user.pk).filter(account_state_q()).exists()


class TestPredicateConjunctIsLoadBearing:
    """Each of the five conjuncts excludes a row that fails only that flag.

    A row failing only one flag must be excluded, and an unconstrained row
    must be included — so the conjunct, not an unrelated default, is what
    does the filtering. States that ``get_account_state`` can express are
    also cross-checked against the instance-level helper (anti-drift).
    """

    def test_default_user_is_included(self) -> None:
        """A user with every flag at its default passes the predicate."""
        u = _state_user(0)
        assert _is_eligible(u) is True
        # Anti-drift: the instance helper agrees this is a clean account.
        state = get_account_state(u)
        assert not state.is_banned
        assert not state.is_deleted
        assert not state.is_declined
        assert not state.consent_revoked

    def test_is_deleted_excludes(self) -> None:
        """``is_deleted=True`` alone excludes the row."""
        u = _state_user(1, is_deleted=True)
        assert _is_eligible(u) is False
        assert get_account_state(u).is_deleted is True

    def test_is_declined_excludes(self) -> None:
        """``is_declined=True`` alone excludes the row."""
        u = _state_user(2, is_declined=True)
        assert _is_eligible(u) is False
        assert get_account_state(u).is_declined is True

    def test_is_banned_excludes(self) -> None:
        """``is_banned=True`` alone excludes the row."""
        u = _state_user(3, is_banned=True)
        assert _is_eligible(u) is False
        assert get_account_state(u).is_banned is True

    def test_consent_revoked_excludes(self) -> None:
        """``consent_revoked_at`` set alone excludes the row."""
        u = _state_user(4, consent_revoked=True)
        assert _is_eligible(u) is False
        assert get_account_state(u).consent_revoked is True

    def test_is_active_false_excludes(self) -> None:
        """``is_active=False`` alone excludes the row.

        This is the predicate-only conjunct: ``get_account_state`` has no
        ``is_active`` term, so the instance helper is NOT cross-checked here.
        """
        u = _state_user(5, is_active=False)
        assert _is_eligible(u) is False

    def test_ads_auto_publish_false_still_included(self) -> None:
        """A publishing restriction is orthogonal to messaging (rule 5)."""
        u = _state_user(6, ads_auto_publish=False)
        assert _is_eligible(u) is True
        assert get_account_state(u).ads_auto_publish is False

    def test_all_restrictions_exclude(self) -> None:
        """A row failing every conjunct is excluded."""
        u = _state_user(
            7,
            is_deleted=True,
            is_declined=True,
            is_banned=True,
            consent_revoked=True,
            is_active=False,
        )
        assert _is_eligible(u) is False


class TestPredicatePrefixRewritesTheList:
    """One declaration resolves from a ``User`` qs and from ``user__`` relations.

    This is the requirement the ``Q`` shape exists for: the same flag list
    must drive (a) a ``User`` queryset, (b) a ``SavedSearch`` queryset through
    its ``user`` FK, and (c) an ``Ad`` queryset through the owner's ``user`` FK.
    """

    def test_prefix_empty_filters_user_queryset(self) -> None:
        """``account_state_q()`` selects eligible ``User`` rows."""
        eligible = _state_user(10)
        excluded = _state_user(11, is_declined=True)
        ids = set(User.objects.filter(account_state_q()).values_list("pk", flat=True))
        assert eligible.pk in ids
        assert excluded.pk not in ids

    def test_user_prefix_filters_saved_search_queryset(self) -> None:
        """``account_state_q("user__")`` filters ``SavedSearch`` by its owner."""
        eligible_owner = _state_user(12)
        excluded_owner = _state_user(13, is_deleted=True)
        eligible_search = SavedSearch.objects.create(user=eligible_owner)
        excluded_search = SavedSearch.objects.create(user=excluded_owner)

        matching = set(
            SavedSearch.objects.filter(account_state_q("user__")).values_list(
                "pk", flat=True
            )
        )
        assert eligible_search.pk in matching
        assert excluded_search.pk not in matching

    def test_user_prefix_filters_ad_queryset_by_owner(
        self, category, city
    ) -> None:
        """``account_state_q("user__")`` filters ``Ad`` by the OWNER's state.

        The declined-seller half of the rule depends on this direction:
        filtering ``Ad`` reaches the owner's ``User`` FK, not the recipient.
        """
        eligible_owner = _state_user(14)
        excluded_owner = _state_user(15, is_declined=True)
        eligible_ad = create_test_ad(eligible_owner, category, city)
        excluded_ad = create_test_ad(excluded_owner, category, city)

        matching = set(
            Ad.objects.filter(account_state_q("user__")).values_list("pk", flat=True)
        )
        assert eligible_ad.pk in matching
        assert excluded_ad.pk not in matching


class TestPredicateComposition:
    """``Q`` is immutable and composes — the property phase 15 relies on."""

    def test_composes_with_extra_conjunct(self) -> None:
        """``account_state_q() & Q(...)`` narrows further."""
        u = _state_user(20)
        assert User.objects.filter(
            account_state_q() & Q(pk=u.pk)
        ).exists()
        assert not User.objects.filter(
            account_state_q() & Q(pk=-1)
        ).exists()

    def test_returned_value_is_not_mutated_by_composition(self) -> None:
        """A second call is unaffected by composing a previous result."""
        u = _state_user(21)
        first = account_state_q()
        # Composing must return a new object, leaving ``first`` untouched.
        _ = first & Q(is_deleted=True)
        second = account_state_q()
        assert User.objects.filter(first, pk=u.pk).exists()
        assert User.objects.filter(second, pk=u.pk).exists()

    def test_composes_into_saved_search_chain(self) -> None:
        """The prefix form composes into an existing ``SavedSearch`` chain."""
        owner = _state_user(22)
        s = SavedSearch.objects.create(user=owner)
        qs = SavedSearch.objects.filter(is_active=True).filter(
            account_state_q("user__")
        )
        assert qs.filter(pk=s.pk).exists()


class TestNoDefaultManagerFilter:
    """The shape must NOT degrade into a default-manager filter (06-PII-104).

    A default filter on ``User.objects`` would make
    ``AccountStateMiddleware._resolve_user`` (``User.objects.get(chat_id=...)``)
    miss for withdrawn / declined / banned / deactivated identities; that
    method returns ``None`` on ``DoesNotExist`` and ``_evaluate_user_state``
    fails open on ``None`` — silently INVERTING the deny gates to allow. This
    test is the anti-inversion tripwire: a withdrawn user's row must remain
    reachable by ``chat_id`` through plain ``User.objects``.
    """

    def test_plain_user_objects_is_unfiltered(self) -> None:
        """``User.objects.all()`` reaches restricted rows — no default filter."""
        withdrawn = _state_user(30, is_deleted=True, consent_revoked=True)
        banned = _state_user(31, is_banned=True)
        declined = _state_user(32, is_declined=True)
        inactive = _state_user(33, is_active=False)

        all_ids = set(User.objects.all().values_list("pk", flat=True))
        for u in (withdrawn, banned, declined, inactive):
            assert u.pk in all_ids

    def test_resolve_by_chat_id_still_finds_restricted_users(self) -> None:
        """The middleware's lookup path is unchanged by the declaration."""
        withdrawn = _state_user(34, is_deleted=True, consent_revoked=True)
        resolved = User.objects.get(chat_id=withdrawn.chat_id)
        assert resolved.pk == withdrawn.pk


# ---------------------------------------------------------------------------
# Fresh-interpreter import probe for the search -> users edge (06-PII-104)
#
# The transitive closure of apps.users.services.account_state already reaches
# apps.search.services.cache (via users.services.__init__ -> deletion ->
# bump_search_cache_version). The alert path consuming the declaration adds a
# module-level apps.search -> apps.users.services.account_state edge. That loop
# is open today ONLY because apps/search/services/__init__.py is import-free;
# a submodule import added there would close it and break the whole alert
# path. A cycle only reproduces in a COLD interpreter, so this probe runs in a
# new process. Neither __init__.py is edited by this block.
# ---------------------------------------------------------------------------

def _run_in_subprocess(
    env: dict[str, str], import_code: str
) -> subprocess.CompletedProcess[str]:
    """Run Python code in a subprocess with the given environment.

    Same idiom as config/settings/tests/test_prod_logging.py and
    test_csrf_trusted_origins.py.
    """
    env_with_path = {
        **env,
        "PYTHONPATH": os.pathsep.join(sys.path),
    }
    return subprocess.run(
        [sys.executable, "-c", import_code],
        env=env_with_path,
        capture_output=True,
        text=True,
    )


@pytest.mark.unit
def test_alert_query_imports_in_fresh_interpreter() -> None:
    """A cold interpreter can import the alert path with the new edge."""
    env = {k: v for k, v in os.environ.items()}
    env["DJANGO_SETTINGS_MODULE"] = "config.settings.test"
    env["DJANGO_SECRET_KEY"] = "test-secret-key-for-testing-only-extra-entropy-9f2a7c"
    code = (
        "import django; django.setup(); "
        "import apps.search.services.alert_query; "
        "from apps.users.services.account_state import account_state_q; "
        "print('IMPORT_OK')"
    )
    result = _run_in_subprocess(env, code)
    assert result.returncode == 0, result.stderr
    assert "IMPORT_OK" in result.stdout
