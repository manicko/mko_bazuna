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
from django.db import transaction
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _

from apps.ads.models import Ad
from apps.ads.services.submission import AdEditInput, SubmitAdInput, submit_ad
from apps.core.enums import AdStatus
from apps.currencies.enums import CurrencyCode
from apps.currencies.services.price_normalizer import normalize_price_to_eur

logger = logging.getLogger(__name__)


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


@login_required
def ad_edit(request: HttpRequest, ad_id: int) -> HttpResponse:
    """
    Edit view for seller's own ads.

    Behavior by status and field type:
        - PUBLISHED + text edit: -> ON_MODERATION, immediately hidden
        - PUBLISHED + price/photo edit: stays PUBLISHED, public within 5s
        - PUBLISHED + mixed edit: follows text rule
        - ARCHIVED + reactivate: text re-checked, hidden until pass
        - Other statuses: direct save (ON_MODERATION, ON_MODERATION_FAILED)

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

    if request.method == "GET":
        # Prefetch images for the edit template
        ad = Ad.objects.prefetch_related("images").get(id=ad_id)
        context = {
            "ad": ad,
        }
        return render(request, "ads/edit.html", context)

    # POST: process edit
    # DB-003: re-fetch the Ad under a row lock inside a transaction so the
    # status-driven branch below and the subsequent transition_to() operate
    # on a locked, consistent row. The GET path returns before this block, so
    # the lock is scoped to POST mutations only (mirrors review.py reject_ad).
    with transaction.atomic():  # pyright: ignore[reportGeneralTypeIssues]  # django-stubs not installed; Atomic lacks CM stubs
        ad = get_object_or_404(Ad.objects.select_for_update(), id=ad_id)

        # Determine if this is a reactivation request
        is_reactivation = ad.status == AdStatus.ARCHIVED and request.POST.get(
            "reactivate"
        )

        # Validate POST data via DTO before any ad.save() call (QLT-004).
        # AdEditInput models the web-edit path's currency-fallback-on-invalid
        # and price-fallback-to-Free semantics via field validators.
        dto = AdEditInput.model_validate(request.POST)

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
            passed, errors = submit_ad(
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

            if passed:
                return redirect("ads:dashboard")
            else:
                ad = Ad.objects.prefetch_related("images").get(id=ad_id)
                return render(
                    request,
                    "ads/edit.html",
                    {
                        "ad": ad,
                        "error": errors[0]
                        if errors
                        else _("Ad failed moderation checks"),
                    },
                )

        elif ad.status == AdStatus.PUBLISHED:
            # Zone C2: Text edit -> ON_MODERATION, hidden immediately
            # Price/photo edit -> stays PUBLISHED
            # Mixed edit -> follows text rule
            if has_text_change:
                # Text edit: go to moderation
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

                # Use transition_to for status change to ON_MODERATION
                ad.transition_to(AdStatus.ON_MODERATION)
                logger.info("Ad %s text edited, moved to ON_MODERATION", ad_id)

                # Run auto-moderation on the edited text content (mirrors
                # ad_reactivate which calls auto_moderate directly).
                # auto_moderate runs its own atomic() (a SAVEPOINT inside this
                # view's outer atomic); on pass it promotes to PUBLISHED, on fail
                # to ON_MODERATION_FAILED. Branch on the bool return and reuse
                # the seller-safe error message from the reactivation branch.
                from apps.moderation.services.auto_moderation import auto_moderate

                am_result = auto_moderate(ad)
                if am_result:
                    return redirect("ads:dashboard")

                ad = Ad.objects.prefetch_related("images").get(id=ad_id)
                return render(
                    request,
                    "ads/edit.html",
                    {
                        "ad": ad,
                        "error": _("Ad failed moderation checks"),
                    },
                )
            else:
                # Price/photo only edit: stay published; recompute normalized price.
                ad = _apply_price_change(ad, dto.price_amount, price_currency_value)
                ad.save(
                    update_fields=[
                        "price_amount",
                        "price_currency",
                        "price_normalized_eur",
                        "updated_at",
                    ]
                )
                logger.info("Ad %s price/photo edited, stays PUBLISHED", ad_id)

            return redirect("ads:dashboard")

        else:
            # Other statuses (ON_MODERATION, ON_MODERATION_FAILED): direct save
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

        if ad.status == AdStatus.PUBLISHED:
            ad.transition_to(AdStatus.ARCHIVED)
            logger.info("Ad %s archived by user %s", ad_id, request.user.id)

    return redirect("ads:dashboard")


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

        if ad.status == AdStatus.ARCHIVED:
            # Update status to ON_MODERATION for re-check (transition_to clears archived_at)
            ad.transition_to(AdStatus.ON_MODERATION)

            # Run auto-moderation check
            from apps.moderation.services.auto_moderation import auto_moderate

            auto_moderate(ad)

            logger.info("Ad %s reactivation initiated by user %s", ad_id, request.user.id)

    return redirect("ads:dashboard")
