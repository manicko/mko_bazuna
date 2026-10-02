"""
Tests for the account-state audience gate on both alert paths (06-PII-104).

Both the daily digest (``send_alerts``) and the publish-time path
(``alert_query``) select their audience by ``SavedSearch.is_active`` alone, so a
user who withdrew consent keeps receiving digests for the full 30-day window and
a declined seller's hidden ad fans out its title and price. This module pins the
fix: each of the four selection sites excludes an owner in a blocked account
state, and all four are driven by the one ``account_state_q`` declaration.

Each per-flag case creates its OWN user (unique ``telegram_id``) rather than
mutating the shared ``seller`` / ``buyer`` fixtures, which use ``get_or_create``
on a fixed id and survive ``--reuse-db``.
"""

from __future__ import annotations

import re
from collections.abc import Callable

import pytest
from django.db.models import Q

from apps.categories.models import Category
from apps.core.enums import AdStatus
from apps.locations.models import City
from apps.search.management.commands.send_alerts import Command
from apps.search.models import SavedSearch
from apps.search.services.alert_query import (
    find_matching_ads,
    find_matching_saved_searches,
)
from apps.users.models import User
from conftest import create_test_ad, make_user

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

# Unique telegram_ids for this module; other alert modules use 9000011xx.
_GATE_BASE = 900001500
_DRY_RUN_USERS_RE = re.compile(r"Would process (\d+) users")


def _owner(offset: int, **flags: object) -> User:
    """Create a fresh eligible/blocked owner with a unique telegram_id."""
    return make_user(_GATE_BASE + offset, **flags)


def _active_search(user: User, **kwargs: object) -> SavedSearch:
    """Create an active saved search owned by ``user``."""
    return SavedSearch.objects.create(user=user, is_active=True, **kwargs)


# One case per conjunct that can block a user. ``is_active`` is the predicate's
# only conjunct with no other writer; ``consent_revoked`` accompanies the
# withdrawn pair because ``withdraw_consent`` sets both in one ``save()``.
_BLOCKED_CASES = [
    ("withdrawn", {"is_deleted": True, "consent_revoked": True}),
    ("declined", {"is_declined": True}),
    ("banned", {"is_banned": True}),
    ("deactivated", {"is_active": False}),
]

_SITE_NAMES = [
    "collect_alerts",
    "dry_run_check",
    "find_matching_saved_searches",
    "find_matching_ads",
]


def _collect_alerts_users(search: SavedSearch, ad: object) -> set[int]:
    """Site 1: user ids collected by the daily command."""
    return set(Command()._collect_alerts()[0].keys())


def _ad_side_users(search: SavedSearch, ad: object) -> set[int]:
    """Site 3: recipient user ids selected for an ad."""
    return {ss.user_id for ss in find_matching_saved_searches(ad)}


def _search_side_users(search: SavedSearch, ad: object) -> set[int]:
    """Site 4: ad-owner user ids selected for a saved search."""
    return {ad.user_id for ad in find_matching_ads(search)}


# Sites 1, 3 and 4 return a set of owner pks. The dry-run site is a count, not
# a pk set, so it is driven and asserted separately below.
_SITE_FUNCS: dict[str, Callable[[SavedSearch, object], set[int]]] = {
    "collect_alerts": _collect_alerts_users,
    "find_matching_saved_searches": _ad_side_users,
    "find_matching_ads": _search_side_users,
}


class TestEachSelectionSiteExcludesBlockedOwner:
    """Every conjunct blocks the owner at every site, and eligible owners survive.

    The four alert selection sites must agree: a search/ad owned by a withdrawn,
    declined, banned or deactivated user appears at none of them. The eligible
    owner's row IS returned, so the fix is not simply returning nothing.

    The dry-run site is asserted on its operator-visible count: with one
    eligible and one blocked owner it must report one user, not two.
    """

    @pytest.mark.parametrize("flag_name,flags", _BLOCKED_CASES)
    @pytest.mark.parametrize(
        "site_name",
        [name for name in _SITE_NAMES if name != "dry_run_check"],
    )
    def test_blocked_owner_is_excluded_and_eligible_is_returned(
        self,
        flag_name: str,
        flags: dict,
        site_name: str,
        category: Category,
        city: City,
    ) -> None:
        eligible = _owner(0)
        blocked = _owner(1, **flags)
        eligible_search = _active_search(eligible)
        blocked_search = _active_search(blocked)
        # No-query searches match these ads structurally (no city/category set).
        eligible_ad = create_test_ad(
            eligible, category, city, status=AdStatus.PUBLISHED
        )
        blocked_ad = create_test_ad(blocked, category, city, status=AdStatus.PUBLISHED)

        site = _SITE_FUNCS[site_name]
        assert blocked.pk not in site(blocked_search, blocked_ad), (
            f"{site_name} returned the {flag_name} owner"
        )
        assert eligible.pk in site(eligible_search, eligible_ad), (
            f"{site_name} dropped the eligible owner"
        )

    @pytest.mark.parametrize("flag_name,flags", _BLOCKED_CASES)
    def test_dry_run_check_counts_only_the_eligible_owner(
        self,
        flag_name: str,
        flags: dict,
        category: Category,
        city: City,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """``Command._dry_run_check`` reports one user, not two."""
        eligible = _owner(2)
        blocked = _owner(3, **flags)
        _active_search(eligible)
        _active_search(blocked)
        # Matches do not need to exist: the user count is independent of them.
        create_test_ad(eligible, category, city, status=AdStatus.PUBLISHED)
        create_test_ad(blocked, category, city, status=AdStatus.PUBLISHED)

        with caplog.at_level("INFO"):
            Command()._dry_run_check()

        match = _DRY_RUN_USERS_RE.search(caplog.text)
        assert match is not None, caplog.text
        counted_users = int(match.group(1))
        assert counted_users == 1, (
            f"dry run counted the {flag_name} owner (reported {counted_users})"
        )


class TestDeclinedSellerAdDoesNotFanOut:
    """An ad whose OWNER is declined matches no subscriber on either path.

    This is the ad-owner direction of the predicate — distinct from the
    recipient's eligibility, which is a different filter and must still work.
    """

    def test_find_matching_ads_excludes_declined_owner_ad(
        self, category: Category, city: City
    ) -> None:
        declined_seller = _owner(10, is_declined=True)
        eligible_seller = _owner(11)
        declined_ad = create_test_ad(
            declined_seller, category, city, status=AdStatus.PUBLISHED
        )
        eligible_ad = create_test_ad(
            eligible_seller, category, city, status=AdStatus.PUBLISHED
        )

        subscriber = _owner(12)
        search = _active_search(subscriber)

        matches = {ad.pk for ad in find_matching_ads(search)}
        assert declined_ad.pk not in matches
        assert eligible_ad.pk in matches

    def test_find_matching_saved_searches_keeps_recipient_rule_intact(
        self, category: Category, city: City
    ) -> None:
        declined_recipient = _owner(20, is_declined=True)
        eligible_recipient = _owner(21)
        declined_search = _active_search(declined_recipient)
        eligible_search = _active_search(eligible_recipient)

        ad = create_test_ad(_owner(22), category, city, status=AdStatus.PUBLISHED)
        matched_pks = {ss.pk for ss in find_matching_saved_searches(ad)}

        # Recipient eligibility still applies on this path: the declined
        # recipient is excluded while the eligible recipient is retained.
        assert declined_search.pk not in matched_pks
        assert eligible_search.pk in matched_pks


class TestOneDeclarationDrivesAllFourSites:
    """A single mutation of the declaration moves all four sites together.

    Proven, not asserted: the test replaces ``account_state_q`` in the two
    importing modules with one mutation that drops the ``is_declined`` conjunct,
    then observes all four sites change together. The real declaration is
    exercised first in the same test, through the same helper, to show each site
    excludes the declined owner before the mutation — so a site that would pass
    either way cannot make the test green.
    """

    def test_mutating_declaration_changes_all_sites(
        self,
        monkeypatch: pytest.MonkeyPatch,
        category: Category,
        city: City,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        declined = _owner(30, is_declined=True)
        declined_search = _active_search(declined)
        declined_ad = create_test_ad(
            declined, category, city, status=AdStatus.PUBLISHED
        )

        def _declined_is_selected() -> dict[str, bool]:
            """Whether each of the four sites selects the declined owner."""
            caplog.clear()
            with caplog.at_level("INFO"):
                Command()._dry_run_check()
            match = _DRY_RUN_USERS_RE.search(caplog.text)
            counted_users = int(match.group(1)) if match else 0
            return {
                "collect_alerts": declined.pk
                in _collect_alerts_users(declined_search, declined_ad),
                "dry_run_check": counted_users > 0,
                "find_matching_saved_searches": declined.pk
                in _ad_side_users(declined_search, declined_ad),
                "find_matching_ads": declined.pk
                in _search_side_users(declined_search, declined_ad),
            }

        # Baseline: the real declaration excludes the declined owner everywhere.
        before = _declined_is_selected()
        assert before == dict.fromkeys(before, False), before

        def mutated(prefix: str = "") -> Q:
            return Q(
                **{
                    f"{prefix}is_deleted": False,
                    f"{prefix}is_banned": False,
                    f"{prefix}consent_revoked_at__isnull": True,
                    f"{prefix}is_active": True,
                }
            )

        monkeypatch.setattr(
            "apps.search.services.alert_query.account_state_q", mutated
        )
        monkeypatch.setattr(
            "apps.search.management.commands.send_alerts.account_state_q", mutated
        )

        # After the single mutation every site changes together.
        after = _declined_is_selected()
        assert after == dict.fromkeys(after, True), after
