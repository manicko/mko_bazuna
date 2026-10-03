"""
Seller ad edit views for Mko Bazuna.

Implements US-S5/S7 edit flow with zone C2 hide-on-text-edit behavior:
    - Text edits (title/description): PUBLISHED -> ON_MODERATION, immediately hidden
    - Price/photo edits: save immediately, status stays PUBLISHED
    - Mixed edits follow text rule (re-moderation)
    - Reactivate (ARCHIVED -> PUBLISHED): text re-checked, hidden until pass
"""

import logging
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db import OperationalError, transaction
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.ads.models import Ad
from apps.ads.services.submission import (
    AdEditInput,
    SubmitAdInput,
    SubmitAdOutcome,
    submit_ad,
)
from apps.core.enums import AdStatus
from apps.core.utils.db_lock_timeout import is_lock_timeout
from apps.currencies.enums import CurrencyCode
from apps.currencies.services.price_normalizer import normalize_price_to_eur

logger = logging.getLogger(__name__)


#: Statuses whose ad may be edited by a direct save (no status transition).
#:
#: This is the **branch** set: the single source of truth for which statuses
#: take the ``ad_edit`` catch-all direct-save branch (``DRAFT`` and
#: ``ON_MODERATION``). It is deliberately explicit: previously the catch-all
#: ``else:`` admitted DRAFT, ON_MODERATION, ON_MODERATION_FAILED, REJECTED,
#: DELETED, and (conditionally) ARCHIVED, so every status silently took the same
#: write path. Naming the two coherent statuses — an unsubmitted DRAFT and a
#: pending ON_MODERATION ad — makes every other status a defined refusal and
#: turns any future re-broadening into a one-line, auditable diff
#: (finding AD-002, BLOCK 8A).
#:
#: This set answers only "which statuses may take the direct save?" It is NOT
#: the set of statuses whose edit form is reachable — see the UI affordance set
#: ``EDIT_FORM_AVAILABLE_STATUSES`` below, which is derived from this one.
EDITABLE_DIRECT_SAVE_STATUSES: frozenset[AdStatus] = frozenset(
    {AdStatus.DRAFT, AdStatus.ON_MODERATION}
)

#: UI affordance set: the statuses for which ``ad_edit`` can succeed, i.e. the
#: statuses whose dashboard Edit link must be shown.
#:
#: This is the **affordance** set and it is NOT the branch set. ``PUBLISHED``
#: has its own working branch (text edit -> ``ON_MODERATION``; price-only edit
#: stays ``PUBLISHED`` with a publish-clock reset) and ``ARCHIVED`` has a
#: working reactivation path (``is_reactivation`` routes through ``submit_ad``),
#: yet neither takes the direct save, so neither is in
#: ``EDITABLE_DIRECT_SAVE_STATUSES`` above. It is derived from that branch set
#: with ``|`` so the two can never drift: every direct-save status is also an
#: edit-form status, and the two extra statuses are appended explicitly.
EDIT_FORM_AVAILABLE_STATUSES: frozenset[AdStatus] = (
    EDITABLE_DIRECT_SAVE_STATUSES | frozenset({AdStatus.PUBLISHED, AdStatus.ARCHIVED})
)


def _apply_price_change(
    ad: Ad,
    price_amount: Decimal,
    price_currency: CurrencyCode | None,
) -> Ad:
    """Apply a price change and recompute ``price_normalized_eur``.

    Sets the source-of-truth fields (``price_amount``/``price_currency``) and
    recomputes the derived EUR-normalized value via ``normalize_price_to_eur``
    (the shared BR-03 seam). When the currency is missing the normalized value
    is cleared.
    Returns the ad so the caller can persist it.

    Args:
        ad: The ad to update.
        price_amount: The new price amount (Decimal("0") for Free).
        price_currency: The new price currency (None preserves current).

    Returns:
        The updated ``ad`` instance.
    """
    ad.price_amount = price_amount
    if price_currency is not None:
        ad.price_currency = price_currency.value
    normalize_price_to_eur(ad, price_amount, price_currency)
    return ad


def _text_fields_changed(dto: AdEditInput, ad: Ad) -> bool:
    """
    Check if text fields (title/description) were changed in the edit.

    Args:
        dto: Validated edit input from the POST form.
        ad: The ad being edited.

    Returns:
        True if title or description differs from the ad's current values.
    """
    return dto.title != ad.title or dto.description != ad.description


def _seller_may_create_ad(user) -> bool:
    """Whether the authenticated seller may create/edit an ad (06-PII-109).

    Thin view-layer seam over the composed ``can_create_ad`` predicate so every
    seller write surface consults the same rule. This is deliberately separate
    from, and checked alongside, the ownership check: an account that owns the
    ad is still refused when it has not granted (or has withdrawn) storage
    consent, so the gate is consulted rather than the ownership check firing.
    """
    from apps.users.services.account_state import can_create_ad

    return can_create_ad(user)


def _consent_required_forbidden(user, ad_id: int) -> HttpResponseForbidden:
    """Log and build the storage-consent 403 for a seller write surface.

    Uses ``HttpResponseForbidden`` with a distinct message — the same shape
    these views already use for the ownership refusal. There is no GET consent
    page (``users/urls.py`` exposes POST-only consent endpoints), so a 403 with
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


@login_required
def ad_edit(request: HttpRequest, ad_id: int) -> HttpResponse:
    """
    Edit view for seller's own ads.

    Behavior by status and field type:
        - PUBLISHED + text edit: -> ON_MODERATION, immediately hidden
        - PUBLISHED + price/photo edit: stays PUBLISHED, public within 5s
        - PUBLISHED + mixed edit: follows text rule
        - ARCHIVED + reactivate: text re-checked, hidden until pass
        - DRAFT or ON_MODERATION: direct save, status unchanged
        - Any other status: refused, the ad is left completely unchanged

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
    # status-driven branch below and the subsequent transition_to() operate
    # on a locked, consistent row. The GET path returns before this block, so
    # the lock is scoped to POST mutations only (mirrors review.py reject_ad).
    #
    # 03-DB-004: a lock timeout aborts the transaction. Catch it OUTSIDE the
    # atomic block (any query after the failure inside the block is dead),
    # re-fetch the ad on a fresh transaction and re-render the edit form with
    # the busy message so the seller's typed content is preserved. Re-raise
    # anything that is not a lock timeout.
    try:
        with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]  # django-stubs not installed; Atomic lacks CM stubs
            ad = get_object_or_404(Ad.objects.select_for_update(), id=ad_id)

            # Determine if this is a reactivation request
            is_reactivation = ad.status == AdStatus.ARCHIVED and request.POST.get(
                "reactivate"
            )

            # Validate POST data via DTO before any ad.save() call (QLT-004).
            # AdEditInput models the web-edit path's currency-fallback-on-invalid
            # and price-fallback-to-Free semantics via field validators.
            # Filter to declared fields so that CSRF/reactivate keys (not part of
            # the DTO) are rejected by extra="forbid" rather than raising on every
            # ad-edit POST.
            dto = AdEditInput.model_validate(
                {k: v for k, v in request.POST.items() if k in AdEditInput.model_fields}
            )

            # Currency-fallback-on-invalid: None means preserve the ad's current
            # currency (web-specific behavior that diverges from the bot flow).
            if dto.price_currency is not None:
                price_currency_value = dto.price_currency
            else:
                price_currency_value = (
                    CurrencyCode(ad.price_currency) if ad.price_currency else None
                )

            # Determine edit type
            has_text_change = _text_fields_changed(dto, ad)

            if is_reactivation:
                # Route through the shared submission orchestrator.
                #
                # The currency pre-coercion above (lines for price_currency_value)
                # ensures it is a valid CurrencyCode | None — submit_ad's
                # defensive coercion is a no-op here. This is an intentional
                # divergence: the web edit path preserves the user's existing
                # currency on invalid input, while the bot flow (always passes
                # a valid CurrencyCode) has no such need. See submit_ad docstring.
                #
                # submit_ad fetches a fresh Ad row; the outer transaction's row
                # lock guarantees no concurrent mutation, sets fields, saves,
                # transitions ARCHIVED -> ON_MODERATION, then calls auto_moderate
                # outside its own atomic.
                result = submit_ad(
                    SubmitAdInput(
                        ad_id=ad_id,
                        title_ru=dto.title,
                        desc_ru=dto.description,
                        category_id=ad.category_id,
                        city_id=ad.city_id,
                        price_amount=dto.price_amount,
                        price_currency=price_currency_value,
                        photos=[],
                        user_id=ad.user_id,
                        listing_condition_id=ad.listing_condition_id,
                    )
                )

                if result.outcome is SubmitAdOutcome.PUBLISHED:
                    return redirect("ads:dashboard")
                else:
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

            elif ad.status == AdStatus.PUBLISHED:
                # Zone C2: Text edit -> ON_MODERATION, hidden immediately
                # Price/photo edit -> stays PUBLISHED
                # Mixed edit -> follows text rule
                if has_text_change:
                    # Delegate to the shared submission orchestrator, mirroring the
                    # reactivation branch above. submit_ad sets the fields, saves,
                    # transitions to ON_MODERATION, then runs auto_moderate.
                    #
                    # The currency pre-coercion above (price_currency_value)
                    # ensures it is a valid CurrencyCode | None — submit_ad
                    # preserves the ad's current currency when None (web
                    # "keep-current" semantic, Path A).
                    result = submit_ad(
                        SubmitAdInput(
                            ad_id=ad_id,
                            title_ru=dto.title,
                            desc_ru=dto.description,
                            category_id=ad.category_id,
                            city_id=ad.city_id,
                            price_amount=dto.price_amount,
                            price_currency=price_currency_value,
                            photos=[],
                            user_id=ad.user_id,
                            listing_condition_id=ad.listing_condition_id,
                        )
                    )

                    if result.outcome is SubmitAdOutcome.PUBLISHED:
                        logger.info("Ad %s text edited, moved to ON_MODERATION", ad_id)
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
                else:
                    # Price/photo only edit: stay published; recompute normalized
                    # price and restart the auto-archive clock. The clock reset
                    # shares the existing single save() deliberately: a second
                    # save() would fire a second post_save and register a second
                    # transaction.on_commit(deliver_immediate_alerts), which can
                    # send a duplicate immediate alert.
                    ad = _apply_price_change(ad, dto.price_amount, price_currency_value)
                    update_fields = [
                        "price_amount",
                        "price_currency",
                        "price_normalized_eur",
                        "updated_at",
                    ]
                    ad.reset_publish_clock(update_fields)
                    ad.save(update_fields=update_fields)
                    logger.info("Ad %s price/photo edited, stays PUBLISHED", ad_id)

                return redirect("ads:dashboard")

            else:
                # Explicit allow-list. The former ``else:`` catch-all admitted
                # DRAFT, ON_MODERATION, ON_MODERATION_FAILED, REJECTED, DELETED,
                # and (without a ``reactivate`` key) ARCHIVED, silently writing
                # content for every one of them (finding AD-002). Only DRAFT and
                # ON_MODERATION have a coherent direct save; every other status
                # is refused below and the row is left untouched.
                if ad.status in EDITABLE_DIRECT_SAVE_STATUSES:
                    ad.title = dto.title
                    ad.description = dto.description
                    ad = _apply_price_change(ad, dto.price_amount, price_currency_value)
                    ad.save(
                        update_fields=[
                            "title",
                            "description",
                            "price_amount",
                            "price_currency",
                            "price_normalized_eur",
                            "updated_at",
                        ]
                    )
                    logger.info("Ad %s edited in status %s", ad_id, ad.status)
                    return redirect("ads:dashboard")

                # Defined refusal: no field is written. Rendering the edit form
                # with the actionable message (HTTP 200) matches the moderation
                # failure paths above and makes the dead end explicit rather
                # than silently rewriting content. The product rule for what a
                # seller may do to a failed ad is Q5 and remains open (BLOCK 8B).
                logger.info(
                    "Ad %s edit refused in status %s", ad_id, ad.status
                )
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

    Args:
        request: HTTP request (authenticated user required)
        ad_id: The ad ID to archive

    Returns:
        Redirect to dashboard or 403 Forbidden if unauthorized
    """
    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]  # django-stubs not installed; Atomic lacks CM stubs
        ad = get_object_or_404(Ad.objects.select_for_update(), id=ad_id)

        # Authorization check
        if ad.user_id != request.user.id:
            logger.warning(
                "User %s attempted to archive ad %s owned by %s",
                request.user.id,
                ad_id,
                ad.user_id,
            )
            return HttpResponseForbidden(
                _("You do not have permission to archive this ad.")
            )

        if not _seller_may_create_ad(request.user):
            return _consent_required_forbidden(request.user, ad_id)

        if ad.status == AdStatus.PUBLISHED:
            ad.transition_to(AdStatus.ARCHIVED)
            logger.info("Ad %s archived by user %s", ad_id, request.user.id)

    return redirect("ads:dashboard")


@require_POST
@login_required
def ad_reactivate(request: HttpRequest, ad_id: int) -> HttpResponse:
    """
    Reactivate an archived ad (ARCHIVED -> PUBLISHED or ON_MODERATION).

    Text is re-checked via auto-moderation. Ad is immediately hidden
    until moderation passes.

    Args:
        request: HTTP request (authenticated user required)
        ad_id: The ad ID to reactivate

    Returns:
        Redirect to dashboard or 403 Forbidden if unauthorized
    """
    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]  # django-stubs not installed; Atomic lacks CM stubs
        ad = get_object_or_404(Ad.objects.select_for_update(), id=ad_id)

        # Authorization check
        if ad.user_id != request.user.id:
            logger.warning(
                "User %s attempted to reactivate ad %s owned by %s",
                request.user.id,
                ad_id,
                ad.user_id,
            )
            return HttpResponseForbidden(
                _("You do not have permission to reactivate this ad.")
            )

        if not _seller_may_create_ad(request.user):
            return _consent_required_forbidden(request.user, ad_id)

        if ad.status == AdStatus.ARCHIVED:
            # Update status to ON_MODERATION for re-check (transition_to clears archived_at)
            ad.transition_to(AdStatus.ON_MODERATION)

            # Run auto-moderation check
            from apps.moderation.services.auto_moderation import auto_moderate

            auto_moderate(ad)

            logger.info("Ad %s reactivation initiated by user %s", ad_id, request.user.id)

    return redirect("ads:dashboard")
