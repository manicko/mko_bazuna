"""Service-tier coverage for ``apps.ads.services.edit_flow``.

Covers the extracted predicate (``can_edit_ad``) and the five-branch payload
application (``apply_edit_payload`` + ``EditOutcome``) directly, without going
through the HTML form or the bot dialog. The core guard is
:class:`TestApplyEditPayloadSubmitOutcomeMatrix`: every ``SubmitAdOutcome``
member is carried through both submit branches, so no refusal can be reported
as a successful edit again. Rendered-artifact coverage stays with the untouched
pre-existing suites (``test_edit.py``, ``test_edit_views_locking.py``,
``test_submission.py``).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from apps.ads.models import Ad
from apps.ads.services.edit_flow import (
    EDIT_FORM_AVAILABLE_STATUSES,
    EDITABLE_DIRECT_SAVE_STATUSES,
    EditOutcome,
    apply_edit_payload,
    can_edit_ad,
)
from apps.ads.services.submission import (
    AdEditInput,
    SubmitAdOutcome,
    SubmitAdResult,
)
from apps.core.enums import AdStatus
from apps.currencies.enums import CurrencyCode
from conftest import create_test_ad, make_user

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Predicate matrix
# ---------------------------------------------------------------------------


class TestCanEditAd:
    """Ownership + status predicate (no consent term, no request)."""

    def test_owner_with_editable_status_can_edit(self, seller, category, city) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        assert can_edit_ad(ad, seller.id) is True

    def test_non_owner_cannot_edit(self, seller, user, category, city) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        assert can_edit_ad(ad, user.id) is False

    def test_anonymous_cannot_edit(self, seller, category, city) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
        assert can_edit_ad(ad, None) is False

    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            (AdStatus.DRAFT, True),
            (AdStatus.ON_MODERATION, True),
            (AdStatus.PUBLISHED, True),
            (AdStatus.ARCHIVED, True),
            (AdStatus.ON_MODERATION_FAILED, False),
            (AdStatus.REJECTED, False),
            (AdStatus.DELETED, False),
        ],
    )
    def test_status_matrix(self, seller, category, city, status, expected) -> None:
        """The predicate's status term is exactly the affordance set."""
        ad = create_test_ad(seller, category, city, status=status)
        assert can_edit_ad(ad, seller.id) is expected
        assert (status in EDIT_FORM_AVAILABLE_STATUSES) is expected

    def test_strict_superset_invariant_preserved(self) -> None:
        """The affordance set still derives from the branch set."""
        assert EDIT_FORM_AVAILABLE_STATUSES > EDITABLE_DIRECT_SAVE_STATUSES
        assert frozenset({AdStatus.PUBLISHED, AdStatus.ARCHIVED}) == (
            EDIT_FORM_AVAILABLE_STATUSES - EDITABLE_DIRECT_SAVE_STATUSES
        )

    def test_predicate_ignores_consent(self, category, city) -> None:
        """Consent is not part of ``can_edit_ad`` (caller-side gate)."""
        owner = make_user(900000901)
        assert owner.consent_given_at is None
        ad = create_test_ad(owner, category, city, status=AdStatus.PUBLISHED)
        assert can_edit_ad(ad, owner.id) is True



# ---------------------------------------------------------------------------
# Payload application — one case per EditOutcome branch
# ---------------------------------------------------------------------------


def _dto(**overrides: object) -> AdEditInput:
    payload: dict[str, object] = {
        "title": "Edited Title",
        "description": "Edited description body.",
        "price_amount": "150",
        "price_currency": CurrencyCode.EUR.value,
    }
    payload.update(overrides)
    return AdEditInput.model_validate(payload)


class TestApplyEditPayloadDirectSave:
    """Family 4: DRAFT / ON_MODERATION direct save (no transition)."""

    @pytest.mark.parametrize(
        "status", [AdStatus.DRAFT, AdStatus.ON_MODERATION]
    )
    def test_direct_save_writes_fields_and_keeps_status(
        self, seller, category, city, status
    ) -> None:
        ad = create_test_ad(seller, category, city, status=status, price=100)
        dto = _dto(title="Direct Save Title", price_amount="150")

        result = apply_edit_payload(ad, dto, False)

        assert result.outcome is EditOutcome.DIRECT_SAVED
        assert result.submission_outcome is None
        assert result.errors == ()
        refreshed = Ad.objects.get(pk=ad.pk)
        assert refreshed.title == "Direct Save Title"
        assert refreshed.description == "Edited description body."
        assert refreshed.price_amount == Decimal("150")
        assert refreshed.status == status
        assert refreshed.moderation_failed_at is None

    def test_direct_save_preserves_currency_when_absent(
        self, seller, category, city
    ) -> None:
        ad = create_test_ad(
            seller,
            category,
            city,
            status=AdStatus.DRAFT,
            price_currency=CurrencyCode.BAM,
        )
        dto = _dto(price_currency="")

        result = apply_edit_payload(ad, dto, False)

        assert result.outcome is EditOutcome.DIRECT_SAVED
        assert Ad.objects.get(pk=ad.pk).price_currency == CurrencyCode.BAM.value


class TestApplyEditPayloadPriceOnly:
    """Family 3: PUBLISHED price-only — direct save, stays PUBLISHED."""

    def test_price_only_keeps_published_and_resets_clock(
        self, seller, category, city
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED, price=100)
        published_at_before = ad.published_at
        dto = _dto(title=ad.title, description=ad.description, price_amount="250")

        result = apply_edit_payload(ad, dto, False)

        assert result.outcome is EditOutcome.PRICE_UPDATED
        assert result.submission_outcome is None
        refreshed = Ad.objects.get(pk=ad.pk)
        assert refreshed.status == AdStatus.PUBLISHED
        assert refreshed.price_amount == Decimal("250")
        # The price-only branch restarts the auto-archive clock on the same
        # single save (``Ad.reset_publish_clock``) and leaves the row PUBLISHED.
        assert refreshed.published_at is not None
        assert refreshed.published_at >= published_at_before
        assert refreshed.updated_at >= published_at_before

    def test_price_only_applies_new_currency(self, seller, category, city) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED, price=100)
        dto = _dto(
            title=ad.title,
            description=ad.description,
            price_amount="100",
            price_currency=CurrencyCode.BAM.value,
        )

        result = apply_edit_payload(ad, dto, False)

        assert result.outcome is EditOutcome.PRICE_UPDATED
        assert (
            Ad.objects.get(pk=ad.pk).price_currency == CurrencyCode.BAM.value
        )


class TestApplyEditPayloadResubmit:
    """Family 2: PUBLISHED text change re-enters moderation via ``submit_ad``."""

    def test_text_change_reports_resubmitted(
        self, seller, category, city, permissive_criteria
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED, price=100)
        dto = _dto(title="Brand New Title", description=ad.description)

        result = apply_edit_payload(ad, dto, False)

        assert result.outcome is EditOutcome.RESUBMITTED
        assert result.submission_outcome is SubmitAdOutcome.PUBLISHED
        assert result.errors == ()
        refreshed = Ad.objects.get(pk=ad.pk)
        assert refreshed.title == "Brand New Title"
        assert refreshed.status == AdStatus.PUBLISHED

    def test_text_change_moderation_failure_is_flagged(
        self, seller, category, city
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED, price=100)
        dto = _dto(title="spam offer", description=ad.description)

        result = apply_edit_payload(ad, dto, False)

        assert result.outcome is EditOutcome.RESUBMITTED
        assert result.submission_outcome is SubmitAdOutcome.MODERATION_FAILED
        assert result.errors
        refreshed = Ad.objects.get(pk=ad.pk)
        assert refreshed.status == AdStatus.ON_MODERATION_FAILED

    def test_description_change_alone_counts_as_text_change(
        self, seller, category, city, permissive_criteria
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED, price=100)
        dto = _dto(title=ad.title, description="A brand new description.")

        result = apply_edit_payload(ad, dto, False)

        assert result.outcome is EditOutcome.RESUBMITTED
        assert result.submission_outcome is SubmitAdOutcome.PUBLISHED


class TestApplyEditPayloadReactivation:
    """Family 1: ARCHIVED + reactivate flag re-enters moderation."""

    def test_reactivation_reports_reactivated(
        self, seller, category, city, permissive_criteria
    ) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED, price=100)
        ad.transition_to(AdStatus.ARCHIVED)
        ad.refresh_from_db()
        dto = _dto(title=ad.title, description=ad.description, price_amount="100")

        result = apply_edit_payload(ad, dto, True)

        assert result.outcome is EditOutcome.REACTIVATED
        assert result.submission_outcome is SubmitAdOutcome.PUBLISHED
        assert result.errors == ()
        refreshed = Ad.objects.get(pk=ad.pk)
        assert refreshed.status == AdStatus.PUBLISHED
        assert refreshed.archived_at is None

    def test_archived_without_flag_is_refused(self, seller, category, city) -> None:
        ad = create_test_ad(seller, category, city, status=AdStatus.ARCHIVED, price=100)
        dto = _dto(title="Unchanged Title", description=ad.description)

        result = apply_edit_payload(ad, dto, False)

        assert result.outcome is EditOutcome.REFUSED
        refreshed = Ad.objects.get(pk=ad.pk)
        assert refreshed.title == ad.title
        assert refreshed.status == AdStatus.ARCHIVED


class TestApplyEditPayloadRefusal:
    """Family 5: every other status writes nothing."""

    @pytest.mark.parametrize(
        "status",
        [AdStatus.ON_MODERATION_FAILED, AdStatus.REJECTED, AdStatus.DELETED],
    )
    def test_refused_status_is_untouched(
        self, seller, category, city, status
    ) -> None:
        ad = create_test_ad(seller, category, city, status=status, price=100)
        Ad.objects.filter(pk=ad.pk).update(title="Untouched Title")
        before = Ad.objects.get(pk=ad.pk)
        snapshot = (
            before.title,
            before.description,
            before.price_amount,
            before.price_currency,
            before.price_normalized_eur,
            before.updated_at,
        )
        dto = _dto(title="Changed Title", price_amount="999")

        result = apply_edit_payload(ad, dto, False)

        assert result.outcome is EditOutcome.REFUSED
        assert result.submission_outcome is None
        assert result.errors == ()
        after = Ad.objects.get(pk=ad.pk)
        assert (
            after.title,
            after.description,
            after.price_amount,
            after.price_currency,
            after.price_normalized_eur,
            after.updated_at,
        ) == snapshot
        assert after.status == status

    def test_every_status_has_one_outcome(self, seller, category, city) -> None:
        """Status-to-branch table: no status takes two branches, none is missed."""
        expected = {
            AdStatus.DRAFT: EditOutcome.DIRECT_SAVED,
            AdStatus.ON_MODERATION: EditOutcome.DIRECT_SAVED,
            AdStatus.PUBLISHED: EditOutcome.PRICE_UPDATED,
            AdStatus.ARCHIVED: EditOutcome.REFUSED,
            AdStatus.ON_MODERATION_FAILED: EditOutcome.REFUSED,
            AdStatus.REJECTED: EditOutcome.REFUSED,
            AdStatus.DELETED: EditOutcome.REFUSED,
        }
        for status, outcome in expected.items():
            ad = create_test_ad(seller, category, city, status=status, price=100)
            dto = _dto(title=ad.title, description=ad.description)
            assert apply_edit_payload(ad, dto, False).outcome is outcome, status



# ---------------------------------------------------------------------------
# Submission-outcome matrix — every SubmitAdOutcome survives both submit branches
# ---------------------------------------------------------------------------

#: The two submit families and how each fixture reaches its branch.
_SUBMIT_BRANCHES: dict[EditOutcome, dict[str, Any]] = {
    EditOutcome.REACTIVATED: {"status": AdStatus.ARCHIVED, "reactivate": True},
    EditOutcome.RESUBMITTED: {"status": AdStatus.PUBLISHED, "reactivate": False},
}

#: The four refusal outcomes, unreachable through the real ``submit_ad`` seam.
_INJECTED_REFUSALS: tuple[SubmitAdOutcome, ...] = (
    SubmitAdOutcome.CONSENT_REQUIRED,
    SubmitAdOutcome.DRAFT_GONE,
    SubmitAdOutcome.PHOTO_UNAVAILABLE,
    SubmitAdOutcome.INVALID_TRANSITION,
)


def _prepare_branch(
    seller, category, city, outcome: EditOutcome
) -> tuple[Ad, AdEditInput, bool]:
    """Build the fixture + DTO + ``reactivate`` flag for a submit branch."""
    spec = _SUBMIT_BRANCHES[outcome]
    ad = create_test_ad(
        seller, category, city, status=AdStatus.PUBLISHED, price=100, title="Old title"
    )
    if spec["status"] is AdStatus.ARCHIVED:
        ad.transition_to(AdStatus.ARCHIVED)
        ad.refresh_from_db()
        dto = _dto(title=ad.title, description=ad.description, price_amount="100")
    else:
        dto = _dto(title="Brand New Title", description=ad.description)
    return ad, dto, spec["reactivate"]


class TestApplyEditPayloadSubmitOutcomeMatrix:
    """Every ``SubmitAdOutcome`` reaches the caller through both submit branches.

    This is the regression guard for the P0 defect: the extracted service used
    to discard four of the six outcomes and report them as a successful branch,
    so an HTML redirect (and an API 200) claimed an edit that never happened.

    ``PUBLISHED`` and ``MODERATION_FAILED`` run **for real** through
    ``submit_ad`` (``permissive_criteria`` / ``banning_criteria``; the failing
    row's "spam" title is overwritten by the service, which is expected and
    harmless). The other four are **injected** at
    ``apps.ads.services.edit_flow.submit_ad`` because they are unreachable
    through this seam:

    - ``PHOTO_UNAVAILABLE`` — the edit always submits ``photos=[]``;
    - ``DRAFT_GONE`` — the caller's row lock plus ``submit_ad``'s locked
      re-fetch make a vanished draft a race, not a reachable state;
    - ``INVALID_TRANSITION`` — the caller derives the branch from the locked
      status, so a refused transition is a race too;
    - ``CONSENT_REQUIRED`` — needs consent withdrawn mid-request (covered
      end-to-end by the HTML/API consent-race tests).
    """

    @pytest.mark.parametrize("branch", list(_SUBMIT_BRANCHES))
    @pytest.mark.parametrize(
        ("outcome", "criteria"),
        [
            (SubmitAdOutcome.PUBLISHED, "permissive_criteria"),
            (SubmitAdOutcome.MODERATION_FAILED, "banning_criteria"),
        ],
        ids=["published", "moderation_failed"],
    )
    def test_real_submission_outcome_is_carried(
        self, request, seller, category, city, branch, outcome, criteria
    ) -> None:
        request.getfixturevalue(criteria)
        ad, dto, reactivate = _prepare_branch(seller, category, city, branch)
        if outcome is SubmitAdOutcome.MODERATION_FAILED:
            # ``submit_ad`` overwrites the title from the DTO, so the banned
            # word must ride in the description (which it preserves) for the
            # failure to be a real content-check rejection.
            dto = _dto(title=dto.title, description="A spam description body.")

        result = apply_edit_payload(ad, dto, reactivate)

        assert result.outcome is branch
        assert result.submission_outcome is outcome
        refreshed = Ad.objects.get(pk=ad.pk)
        if outcome is SubmitAdOutcome.MODERATION_FAILED:
            assert refreshed.status == AdStatus.ON_MODERATION_FAILED
            assert result.errors
            assert refreshed.moderation_failed_at is not None
        else:
            assert refreshed.status == AdStatus.PUBLISHED
            assert result.errors == ()
            assert refreshed.moderation_failed_at is None
            assert refreshed.title == dto.title

    @pytest.mark.parametrize("branch", list(_SUBMIT_BRANCHES))
    @pytest.mark.parametrize("outcome", _INJECTED_REFUSALS)
    def test_refusal_outcome_is_carried_verbatim(
        self, monkeypatch, seller, category, city, branch, outcome
    ) -> None:
        ad, dto, reactivate = _prepare_branch(seller, category, city, branch)
        before = Ad.objects.get(pk=ad.pk)
        snapshot = (
            before.title,
            before.description,
            before.price_amount,
            before.price_currency,
            before.price_normalized_eur,
            before.updated_at,
        )

        def _refuse(*args: Any, **kwargs: Any) -> SubmitAdResult:
            return SubmitAdResult(outcome=outcome, errors=["reason"])

        monkeypatch.setattr("apps.ads.services.edit_flow.submit_ad", _refuse)

        result = apply_edit_payload(ad, dto, reactivate)

        assert result.outcome is branch
        assert result.submission_outcome is outcome
        assert result.errors == ("reason",)
        after = Ad.objects.get(pk=ad.pk)
        assert (
            after.title,
            after.description,
            after.price_amount,
            after.price_currency,
            after.price_normalized_eur,
            after.updated_at,
        ) == snapshot
        assert after.status == before.status
