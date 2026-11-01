"""
Edit-flow predicate and payload application — the five-branch edit stack (S4.2).

Extracted verbatim from the seller HTML edit view so that the HTML surface and
the future ``POST /api/v1/ads/{id}/edit/`` endpoint share **one** status-to-
branch table and **one** payload writer instead of two hand-written copies.

Scope split (plan S4.2):

- **This module carries the edit predicate and the payload stages** — the
  ownership / consent / status predicate (``can_edit_ad``) and the staged
  application of an :class:`AdEditInput` (``apply_edit_payload``).
- **The caller owns the transaction, the row lock and every rendered artifact.**
  ``apps/ads/views/edit.py`` opens ``transaction.atomic()`` and takes
  ``select_for_update()`` on the row, then hands the **locked** instance to
  ``apply_edit_payload``; it keeps the form rendering, the redirect, the
  messages and the 03-DB-004 lock-timeout re-render. The bot keeps its own
  dialog and its own FSM transitions.

Contract: request-free — an ``Ad`` instance (already fetched and locked by the
caller) plus the acting ``user_id`` / a validated :class:`AdEditInput`.

The five outcome families (auditor A5) — every one of them is a member of
:class:`EditOutcome`:

1. ``REACTIVATED`` — an ``ARCHIVED`` ad posted with a truthy ``reactivate``
   flag: routed through the shared submission orchestrator (``submit_ad``),
   which transitions ``ARCHIVED -> ON_MODERATION`` and runs ``auto_moderate``.
2. ``RESUBMITTED`` — a ``PUBLISHED`` ad whose title/description changed:
   routed through ``submit_ad`` as well (text edits re-enter moderation,
   hidden immediately — zone C2).
3. ``PRICE_UPDATED`` — a ``PUBLISHED`` ad with a price-only change: saved
   directly, status stays ``PUBLISHED``, publish clock reset. **Never**
   funnelled through ``submit_ad`` (frozen rule).
4. ``DIRECT_SAVED`` — a ``DRAFT``/``ON_MODERATION`` ad
   (``EDITABLE_DIRECT_SAVE_STATUSES``): saved directly, status unchanged.
   **Never** funnelled through ``submit_ad`` (frozen rule).
5. ``REFUSED`` — every other status: no field is written at all. The HTML
   caller re-renders the form with HTTP 200 (a deliberate mapping); the API
   caller maps this to ``409 not_editable``.

A moderation failure on families 1/2 is reported through the same
``REFUSED``-adjacent shape the view already had — see
:class:`EditResult.moderation_failed` and ``errors``.

A lock timeout is **not** an outcome: ``OperationalError`` propagates to the
caller's boundary (03-DB-004), exactly as before.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, NamedTuple

from apps.ads.models import Ad
from apps.ads.services.submission import (
    AdEditInput,
    SubmitAdInput,
    SubmitAdOutcome,
    submit_ad,
)
from apps.core.enums import AdStatus
from apps.currencies.enums import CurrencyCode
from apps.currencies.services.price_normalizer import normalize_price_to_eur

if TYPE_CHECKING:
    from apps.users.models import User

logger = logging.getLogger(__name__)


#: Statuses whose ad may be edited by a direct save (no status transition).
#:
#: This is the **branch** set: the single source of truth for which statuses
#: take the direct-save branch (``DRAFT`` and ``ON_MODERATION``). It is
#: deliberately explicit: previously the catch-all ``else:`` admitted DRAFT,
#: ON_MODERATION, ON_MODERATION_FAILED, REJECTED, DELETED, and (conditionally)
#: ARCHIVED, so every status silently took the same write path. Naming the two
#: coherent statuses — an unsubmitted DRAFT and a pending ON_MODERATION ad —
#: makes every other status a defined refusal and turns any future
#: re-broadening into a one-line, auditable diff (finding AD-002, BLOCK 8A).
#:
#: This set answers only "which statuses may take the direct save?" It is NOT
#: the set of statuses whose edit form is reachable — see the UI affordance set
#: ``EDIT_FORM_AVAILABLE_STATUSES`` below, which is derived from this one.
EDITABLE_DIRECT_SAVE_STATUSES: frozenset[AdStatus] = frozenset(
    {AdStatus.DRAFT, AdStatus.ON_MODERATION}
)

#: UI affordance set: the statuses for which the edit flow can succeed, i.e.
#: the statuses whose dashboard Edit link must be shown.
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


class EditOutcome(StrEnum):
    """The five outcome families of the edit flow (auditor A5)."""

    REACTIVATED = "reactivated"
    RESUBMITTED = "resubmitted"
    PRICE_UPDATED = "price_updated"
    DIRECT_SAVED = "direct_saved"
    REFUSED = "refused"


class EditResult(NamedTuple):
    """Outcome of :func:`apply_edit_payload`.

    ``moderation_failed`` distinguishes the two failure shapes of families 1/2
    (``REACTIVATED`` / ``RESUBMITTED``): the payload was committed by
    ``submit_ad`` but the content check did not pass (``True``), versus any
    other ``submit_ad`` refusal (``False``). Both re-render the HTML edit form
    with an error; the flag exists so a caller can tell them apart without
    string-matching ``errors``.

    ``errors`` carries the user-facing strings ``submit_ad`` produced (already
    translated, ``str()``-able); it is empty for every non-moderation outcome.
    """

    outcome: EditOutcome
    moderation_failed: bool = False
    errors: tuple[str, ...] = ()


def can_edit_ad(ad: Ad, user_id: int | None) -> bool:
    """Whether *user_id* may edit *ad* (ownership + status predicate).

    Reproduces the HTML edit view's two pre-write refusals, in the same order:

    - the ad must be owned by the actor (a non-owner is refused before
      anything else is considered);
    - the ad's status must admit an edit at all — the affordance set
      ``EDIT_FORM_AVAILABLE_STATUSES`` (``DRAFT``, ``ON_MODERATION``,
      ``PUBLISHED``, ``ARCHIVED``).

    The wrong-status check is a **pure** short-circuit here; the view keeps its
    own refusal branch (which renders the actionable message) so the rendered
    response is unchanged. An ad that cannot be edited because of its status is
    also refused here, which is what the future API maps to ``409
    not_editable``.

    The storage-consent gate is deliberately **not** part of this predicate:
    it is a property of the account, not of the ad, and stays caller-side
    (``can_create_ad`` — see :func:`can_edit_ad_by_service`, which composes it).
    """
    if user_id is None or ad.user_id != user_id:
        return False
    return ad.status in EDIT_FORM_AVAILABLE_STATUSES


def can_edit_ad_by_service(ad: Ad, user: User) -> bool:
    """Whether *user* may edit *ad*: ownership + status + storage consent.

    The composed predicate every seller write surface consults: it layers the
    create-time storage-consent gate (06-PII-109) on top of
    :func:`can_edit_ad`. ``can_create_ad`` is imported lazily so the service
    module carries no import-time dependency on ``apps.users`` beyond typing.
    """
    from apps.users.services.account_state import can_create_ad

    if not can_create_ad(user):
        return False
    return can_edit_ad(ad, user.id)


def text_fields_changed(dto: AdEditInput, ad: Ad) -> bool:
    """Whether the edit changes the ad's title or description.

    Args:
        dto: Validated edit input.
        ad: The ad being edited.

    Returns:
        True if title or description differs from the ad's current values.
    """
    return dto.title != ad.title or dto.description != ad.description


def apply_price_change(
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


def resolve_edit_currency(dto: AdEditInput, ad: Ad) -> CurrencyCode | None:
    """Resolve the currency an edit writes, preserving the ad's current one.

    Web-specific currency-fallback-on-invalid: an absent/blank POST currency
    yields ``None`` in :class:`AdEditInput`; the edit flow then keeps the ad's
    stored currency (which diverges from the bot flow, that always passes a
    valid ``CurrencyCode``). A stored value that is not a ``CurrencyCode``
    falls through to ``None`` exactly as the inline view expression did.
    """
    if dto.price_currency is not None:
        return dto.price_currency
    return CurrencyCode(ad.price_currency) if ad.price_currency else None


def _submit_like(
    ad: Ad, dto: AdEditInput, price_currency: CurrencyCode | None
) -> EditResult:
    """Route the payload through the shared submission orchestrator."""
    result = submit_ad(
        SubmitAdInput(
            ad_id=ad.id,
            title_ru=dto.title,
            desc_ru=dto.description,
            category_id=ad.category_id,
            city_id=ad.city_id,
            price_amount=dto.price_amount,
            price_currency=price_currency,
            photos=[],
            user_id=ad.user_id,
            listing_condition_id=ad.listing_condition_id,
        )
    )

    if result.outcome is SubmitAdOutcome.PUBLISHED:
        return EditResult(EditOutcome.REACTIVATED)
    return EditResult(
        EditOutcome.REACTIVATED,
        # ``submit_ad`` reports MODERATION_FAILED when the content check ran and
        # rejected the ad; every other outcome (DRAFT_GONE, PHOTO_UNAVAILABLE,
        # INVALID_TRANSITION, CONSENT_REQUIRED) is a refusal, which the HTML
        # caller has always rendered through the same form.
        moderation_failed=result.outcome is SubmitAdOutcome.MODERATION_FAILED,
        errors=tuple(str(error) for error in result.errors),
    )


def apply_edit_payload(
    ad: Ad,
    dto: AdEditInput,
    reactivate: bool,
    *,
    outcome_prefix: EditOutcome = EditOutcome.REACTIVATED,
) -> EditResult:
    """Apply a validated edit payload to a **locked** ad (five outcome families).

    The caller must hold the row lock (``select_for_update``) inside an open
    ``transaction.atomic()``: families 1/2 delegate to ``submit_ad`` (which
    re-fetches the row; the caller's lock guarantees a stable read) and
    families 3/4 write the instance in place.

    Args:
        ad: The ad, already fetched under a row lock by the caller.
        dto: Validated edit input (``AdEditInput``).
        reactivate: Whether the POST carried a truthy ``reactivate`` flag; only
            meaningful for an ``ARCHIVED`` ad, exactly as before.
        outcome_prefix: The outcome reported for the ``submit_ad`` families;
            the HTML caller passes ``REACTIVATED`` for the ARCHIVED branch and
            ``RESUBMITTED`` for the PUBLISHED text branch. Ignored otherwise.

    Returns:
        :class:`EditResult` naming the branch that ran.

    Raises:
        OperationalError: Propagated untouched (lock timeout — 03-DB-004).
    """
    is_reactivation = ad.status == AdStatus.ARCHIVED and reactivate

    if is_reactivation or (
        ad.status == AdStatus.PUBLISHED and text_fields_changed(dto, ad)
    ):
        price_currency = resolve_edit_currency(dto, ad)
        result = _submit_like(ad, dto, price_currency)
        if result.moderation_failed:
            return EditResult(
                outcome_prefix,
                moderation_failed=True,
                errors=result.errors,
            )
        return EditResult(outcome_prefix)

    if ad.status == AdStatus.PUBLISHED:
        # Price-only edit: stays published; recompute normalized price and
        # restart the auto-archive clock. The clock reset shares the existing
        # single save() deliberately: a second save() would fire a second
        # post_save and register a second
        # transaction.on_commit(deliver_immediate_alerts), which can send a
        # duplicate immediate alert.
        price_currency = resolve_edit_currency(dto, ad)
        ad = apply_price_change(ad, dto.price_amount, price_currency)
        update_fields = [
            "price_amount",
            "price_currency",
            "price_normalized_eur",
            "updated_at",
        ]
        ad.reset_publish_clock(update_fields)
        ad.save(update_fields=update_fields)
        return EditResult(EditOutcome.PRICE_UPDATED)

    if ad.status in EDITABLE_DIRECT_SAVE_STATUSES:
        price_currency = resolve_edit_currency(dto, ad)
        ad.title = dto.title
        ad.description = dto.description
        ad = apply_price_change(ad, dto.price_amount, price_currency)
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
        return EditResult(EditOutcome.DIRECT_SAVED)

    # Defined refusal: no field is written.
    return EditResult(EditOutcome.REFUSED)
