"""
Seller ad edit views for Mko Bazuna.

Implements US-S5/S7 edit flow with zone C2 hide-on-text-edit behavior:
    - Text edits (title/description): PUBLISHED -> ON_MODERATION, immediately hidden
    - Price edits: save immediately, status stays PUBLISHED
    - Mixed edits follow text rule (re-moderation)
    - Reactivate (ARCHIVED -> PUBLISHED): text re-checked, hidden until pass

The status-to-branch table and the payload stages live in the shared
edit-flow service (``apps.ads.services.edit_flow``, S4.2) so the HTML view and
the future ``/api/v1/ads/{id}/edit/`` endpoint cannot drift. This module keeps
what is view-shaped: the transaction + row lock, the rendered form, the
redirects, the log lines and the 03-DB-004 lock-timeout re-render.

Photos are not seller-editable in phase 1: this view never changes an ad's
photos, and the bot affordance for seller-side photo editing was deliberately
deferred (owner decision Q07-6=(b)). The only post-publish photo change is a
moderator removing a single photo (apps.ads.services.ad_image_removal).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import DatabaseError, OperationalError, transaction
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

if TYPE_CHECKING:
    from apps.users.models import User

from apps.ads.models import Ad
from apps.ads.services.edit_flow import (
    EDIT_FORM_AVAILABLE_STATUSES,
    EDITABLE_DIRECT_SAVE_STATUSES,
    EditOutcome,
    apply_edit_payload,
)
from apps.ads.services.lifecycle import archive_ad, reactivate_ad
from apps.ads.services.submission import AdEditInput, SubmitAdOutcome
from apps.core.utils.db_lock_timeout import is_lock_timeout

logger = logging.getLogger(__name__)

__all__ = [
    "EDITABLE_DIRECT_SAVE_STATUSES",
    "EDIT_FORM_AVAILABLE_STATUSES",
    "ad_archive",
    "ad_edit",
    "ad_reactivate",
]


def _seller_may_create_ad(user: User) -> bool:
    """Whether the authenticated seller may create/edit an ad (06-PII-109).

    Thin view-layer seam over the composed ``can_create_ad`` predicate so every
    seller write surface consults the same rule. This is deliberately separate
    from, and checked alongside, the ownership check: an account that owns the
    ad is still refused when it has not granted (or has withdrawn) storage
    consent, so the gate is consulted rather than the ownership check firing.
    """
    from apps.users.services.account_state import can_create_ad

    return can_create_ad(user)


def _consent_required_forbidden(user: User, ad_id: int) -> HttpResponseForbidden:
    """Log and build the storage-consent 403 for a seller write surface.

    Uses ``HttpResponseForbidden`` with a distinct message — the same shape
    these views already use for the ownership refusal. There is no GET consent
    page (``users/urls.py` exposes POST-only consent endpoints), so a 403 with
    a clear message is the honest response.
    """
    logger.warning(
        "User %s refused ad %s write: personal-data storage consent required",
        user.id,
        ad_id,
    )
    return HttpResponseForbidden(
        _(
            "To manage ads, please accept the personal data storage consent first."
        )
    )


def _ownership_refused_forbidden(
    permission_message: str, action: str, ad_id: int, user_id: int
) -> HttpResponse:
    """Log and build the ownership 403 of a seller lifecycle action.

    ``permission_message`` is the translated text each action already returned
    (``"You do not have permission to <action> this ad."``), passed as a whole
    so the rendered 403 body stays byte-identical.
    """
    logger.warning(
        "User %s attempted to %s ad %s without owning it", user_id, action, ad_id
    )
    return HttpResponseForbidden(permission_message)


@login_required
def ad_edit(request: HttpRequest, ad_id: int) -> HttpResponse:
    """
    Edit view for seller's own ads.

    Behavior by status and field type:
        - PUBLISHED + text edit: -> ON_MODERATION, immediately hidden
        - PUBLISHED + price-only edit: stays PUBLISHED, public within 5s
        - PUBLISHED + mixed edit: follows text rule
        - ARCHIVED + reactivate: text re-checked, hidden until pass
        - DRAFT or ON_MODERATION: direct save, status unchanged
        - Any other status: refused, the ad is left completely unchanged

    Photos are not edited here (phase 1 defers seller-side photo editing,
    Q07-6=(b)); a price-only change is the only field edit on a live ad that
    stays PUBLISHED.

    Args:
        request: HTTP request (authenticated user required)
        ad_id: The ad ID to edit

    Returns:
        Rendered edit form or redirect after save
    """
    ad = get_object_or_404(Ad, id=ad_id)

    # Authorization check: must own the ad (returns 403 Forbidden)
    if ad.user_id != request.user.id:
        logger.warning(
            "User %s attempted to edit ad %s owned by %s",
            request.user.id,
            ad_id,
            ad.user_id,
        )
        return HttpResponseForbidden(_("You do not have permission to edit this ad."))

    if not _seller_may_create_ad(request.user):
        return _consent_required_forbidden(request.user, ad_id)

    if request.method == "GET":
        # Prefetch images for the edit template
        ad = Ad.objects.prefetch_related("images").get(id=ad_id)
        context = {
            "ad": ad,
        }
        return render(request, "ads/edit.html", context)

    # POST: process edit
    # re-fetch the Ad under a row lock inside a transaction so the
    # status-driven branch (now in the shared edit-flow service) and the
    # subsequent transition_to() operate on a locked, consistent row. The GET
    # path returns before this block, so the lock is scoped to POST mutations
    # only (mirrors review.py reject_ad).
    #
    # 03-DB-004: a lock timeout aborts the transaction. Catch it OUTSIDE the
    # atomic block (any query after the failure inside the block is dead),
    # re-fetch the ad on a fresh transaction and re-render the edit form with
    # the busy message so the seller's typed content is preserved. Re-raise
    # anything that is not a lock timeout.
    try:
        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]  # django-stubs not installed; Atomic lacks CM stubs
            ad = get_object_or_404(Ad.objects.select_for_update(), id=ad_id)

            # Validate POST data via DTO before any ad.save() call (QLT-004).
            # AdEditInput models the web-edit path's currency-fallback-on-invalid
            # and price-fallback-to-Free semantics via field validators.
            # Filter to declared fields so that CSRF/reactivate keys (not part of
            # the DTO) are rejected by extra="forbid" rather than raising on every
            # ad-edit POST.
            dto = AdEditInput.model_validate(
                {k: v for k, v in request.POST.items() if k in AdEditInput.model_fields}
            )

            # Status-to-branch table and payload application live in the shared
            # edit-flow service (S4.2). This view keeps only the response shapes.
            # The raw ``reactivate`` flag is passed through: the ARCHIVED
            # conjunct that makes it a reactivation lives in the service.
            result = apply_edit_payload(ad, dto, bool(request.POST.get("reactivate")))

            if result.outcome in (
                EditOutcome.REACTIVATED,
                EditOutcome.RESUBMITTED,
            ):
                # Only a PUBLISHED submission is a success (baseline rule): a
                # moderation failure parks the ad, and every submit-time refusal
                # (consent, draft gone, photo gone, invalid transition) leaves it
                # untouched — all of them re-render the form with the error.
                if result.submission_outcome is SubmitAdOutcome.PUBLISHED:
                    if result.outcome is EditOutcome.RESUBMITTED:
                        logger.info(
                            "Ad %s text edited, moved to ON_MODERATION", ad_id
                        )
                    return redirect("ads:dashboard")

                ad = Ad.objects.prefetch_related("images").get(id=ad_id)
                return render(
                    request,
                    "ads/edit.html",
                    {
                        "ad": ad,
                        "error": result.errors[0]
                        if result.errors
                        else _("Ad failed moderation checks"),
                    },
                )

            if result.outcome is EditOutcome.PRICE_UPDATED:
                logger.info("Ad %s price edited, stays PUBLISHED", ad_id)
                return redirect("ads:dashboard")

            if result.outcome is EditOutcome.DIRECT_SAVED:
                logger.info("Ad %s edited in status %s", ad_id, ad.status)
                return redirect("ads:dashboard")

            # Defined refusal: no field is written. Rendering the edit form
            # with the actionable message (HTTP 200) matches the moderation
            # failure paths above and makes the dead end explicit rather
            # than silently rewriting content. The product rule for what a
            # seller may do to a failed ad is Q5 and remains open (BLOCK 8B).
            logger.info("Ad %s edit refused in status %s", ad_id, ad.status)
            ad = Ad.objects.prefetch_related("images").get(id=ad_id)
            return render(
                request,
                "ads/edit.html",
                {
                    "ad": ad,
                    "error": _("This ad cannot be edited in its current status."),
                },
            )
    except OperationalError as exc:
        if not is_lock_timeout(exc):
            raise
        logger.warning(
            "Lock timeout editing ad %s (SQLSTATE 55P03); re-rendering form", ad_id
        )
        ad = Ad.objects.prefetch_related("images").get(id=ad_id)
        return render(
            request,
            "ads/edit.html",
            {
                "ad": ad,
                "error": _("The system is busy. Please try again in a moment."),
            },
        )


@require_POST
@login_required
def ad_archive(request: HttpRequest, ad_id: int) -> HttpResponse:
    """
    Archive an ad (PUBLISHED -> ARCHIVED).

    Manual archive action for sellers. Does not require moderation.

    This view owns the transaction, the row lock and the authorization: it
    fetches the ad under ``select_for_update()``, refuses a non-owner, then
    asserts the consent gate at the caller boundary, and the shared lifecycle
    service (S4.1) applies the ``PUBLISHED -> ARCHIVED`` transition to that
    locked instance. The service call is the last statement inside the block,
    so the fetch, the ownership check, the consent gate and the transition
    share one unit of work and one row-lock lifetime (the service's own
    ``atomic()`` nests as a PostgreSQL savepoint under this block).

    Args:
        request: HTTP request (authenticated user required)
        ad_id: The ad ID to archive

    Returns:
        Redirect to dashboard or 403 Forbidden if unauthorized
    """
    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]  # django-stubs not installed; Atomic lacks CM stubs
        ad = get_object_or_404(Ad.objects.select_for_update(), id=ad_id)

        if ad.user_id != request.user.id:
            return _ownership_refused_forbidden(
                _("You do not have permission to archive this ad."),
                "archive",
                ad_id,
                request.user.id,
            )

        if not _seller_may_create_ad(request.user):
            return _consent_required_forbidden(request.user, ad_id)

        archive_ad(ad)

    return redirect("ads:dashboard")


@require_POST
@login_required
def ad_reactivate(request: HttpRequest, ad_id: int) -> HttpResponse:
    """
    Reactivate an archived ad (ARCHIVED -> PUBLISHED or ON_MODERATION).

    Text is re-checked via auto-moderation. Ad is immediately hidden
    until moderation passes.

    The auto-moderation outcome is surfaced to the seller: a failed check
    commits the ad as ON_MODERATION_FAILED (hidden pending human review) and
    shows a dashboard message instead of a silent redirect; an unexpected
    non-database error raised by the check rolls the reactivation back (the ad
    stays ARCHIVED) and reports the failure instead of returning HTTP 500.
    Database errors keep the 03-DB-004 boundary (lock timeout -> 503 via
    DbLockTimeoutMiddleware, anything else re-raised untouched).

    This view owns the transaction, the row lock and the authorization: it
    fetches the ad under ``select_for_update()``, refuses a non-owner, then
    asserts the consent gate at the caller boundary, and the shared lifecycle
    service (S4.1) applies the ``ARCHIVED -> ON_MODERATION`` transition and
    the moderation decision to that locked instance. The service call is the
    last statement inside the block, so the fetch, the ownership check, the
    consent gate, the transition and the auto-moderation decision share one
    transaction and one row-lock lifetime (the service's ``atomic()`` nests as
    a savepoint).

    Args:
        request: HTTP request (authenticated user required)
        ad_id: The ad ID to reactivate

    Returns:
        Redirect to dashboard or 403 Forbidden if unauthorized
    """
    passed: bool | None = None
    try:
        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]  # django-stubs not installed; Atomic lacks CM stubs
            ad = get_object_or_404(Ad.objects.select_for_update(), id=ad_id)

            if ad.user_id != request.user.id:
                return _ownership_refused_forbidden(
                    _("You do not have permission to reactivate this ad."),
                    "reactivate",
                    ad_id,
                    request.user.id,
                )

            if not _seller_may_create_ad(request.user):
                return _consent_required_forbidden(request.user, ad_id)

            passed = reactivate_ad(ad).passed
    except (Http404, DatabaseError):
        # A missing ad keeps its 404; a database error keeps the 03-DB-004
        # boundary (a lock timeout becomes a 503 via DbLockTimeoutMiddleware,
        # anything else is re-raised untouched). Only a non-database failure of
        # the moderation pipeline is converted into a dashboard message below.
        raise
    except Exception:
        # auto_moderate raising a non-database error (e.g. a cache failure)
        # used to escape as HTTP 500 after the transaction rolled back. Report
        # it and leave the ad ARCHIVED (the rollback is the safe state).
        logger.exception("Ad %s reactivation failed during auto-moderation", ad_id)
        messages.error(
            request,
            _(
                "Reactivating ad #%(ad_id)s failed. The ad stays archived; "
                "please try again later."
            )
            % {"ad_id": ad_id},
        )
        return redirect("ads:dashboard")

    if passed is False:
        # The ad committed as ON_MODERATION_FAILED and stays hidden until human
        # review; without this branch the seller saw a silent redirect.
        logger.info("Ad %s failed re-moderation on reactivation", ad_id)
        messages.warning(
            request,
            _(
                "Ad #%(ad_id)s did not pass moderation and is hidden pending review."
            )
            % {"ad_id": ad_id},
        )
    elif passed:
        logger.info("Ad %s reactivated by user %s", ad_id, request.user.id)

    return redirect("ads:dashboard")
