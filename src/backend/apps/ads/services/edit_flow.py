"""
Edit-flow predicate and payload application — the five-branch edit stack.

Extracted verbatim from the seller HTML edit view so that the status-to-branch
table and the payload writer live in **one** place instead of being hand-written
inside the view.

Scope split:

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
5. ``REFUSED`` — every other status: no field is written at all. The caller
   re-renders the form with HTTP 200.

Families 1/2 always route through ``submit_ad`` and their result is reported
honestly: :class:`EditResult.submission_outcome` carries the orchestrator's own
:class:`~apps.ads.services.submission.SubmitAdOutcome` (``PUBLISHED``,
``MODERATION_FAILED``, or one of the four refusals) and ``errors`` carries its
``str()``-ified messages. Families 3/4 and the status-set ``REFUSED`` never call
``submit_ad``, so their ``submission_outcome`` is ``None``. Success is a
property of the submission outcome, never of a caller-supplied label.

A lock timeout is **not** an outcome: ``OperationalError`` propagates to the
caller's boundary (03-DB-004), exactly as before.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from enum import StrEnum
from typing import NamedTuple

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

    Two orthogonal typed facts, mirroring the
    :class:`~apps.ads.services.submission.SubmitAdResult` convention:

    - ``outcome`` names the **branch** that ran (``EditOutcome``);
    - ``submission_outcome`` — for the two ``submit_ad`` families
      (``REACTIVATED`` / ``RESUBMITTED``) — is the orchestrator's own
      :class:`~apps.ads.services.submission.SubmitAdOutcome`. It is ``None``
      for the two non-submission branches (``PRICE_UPDATED``, ``DIRECT_SAVED``)
      and for the status-set ``REFUSED``.

    A moderation failure is therefore **derived**, never stored:
    ``submission_outcome is SubmitAdOutcome.MODERATION_FAILED``. Nothing in
    this result can claim success for a submission that was refused.

    ``errors`` carries the submission's user-facing strings (already
    translated, ``str()``-ified); it is empty for ``PUBLISHED``,
    ``PRICE_UPDATED``, ``DIRECT_SAVED`` and the status-set ``REFUSED``.
    """

    outcome: EditOutcome
    submission_outcome: SubmitAdOutcome | None = None
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
    also refused here, so the predicate answers the same question the view's
    refusal branch does.

    The storage-consent gate is deliberately **not** part of this predicate:
    it is a property of the account, not of the ad, and stays caller-side —
    the HTML view composes it itself (``_seller_may_create_ad``), so this
    predicate stays a pure "ownership + status" term.
    """
    if user_id is None or ad.user_id != user_id:
        return False
    return ad.status in EDIT_FORM_AVAILABLE_STATUSES


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
    """Route the payload through the shared submission orchestrator.

    The orchestrator's outcome is carried verbatim — every one of its six
    members survives, so the caller can decide what counts as success (only
    ``PUBLISHED`` commits and publishes) and the API can map each refusal.
    The branch label is supplied by the caller, which is the only code that
    knows which of the two submit families it took.
    """
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
    return EditResult(
        EditOutcome.REACTIVATED,
        submission_outcome=result.outcome,
        errors=tuple(str(error) for error in result.errors),
    )


def apply_edit_payload(ad: Ad, dto: AdEditInput, reactivate: bool) -> EditResult:
    """Apply a validated edit payload to a **locked** ad (five outcome families).

    The caller must hold the row lock (``select_for_update``) inside an open
    ``transaction.atomic()``: families 1/2 delegate to ``submit_ad`` (which
    re-fetches the row; the caller's lock guarantees a stable read) and
    families 3/4 write the instance in place.

    The branch label is derived here from the same inputs the caller passes —
    ``ad.status``, ``reactivate`` and :func:`text_fields_changed` — so no
    caller-supplied label can misreport which branch ran.

    Args:
        ad: The ad, already fetched under a row lock by the caller.
        dto: Validated edit input (``AdEditInput``).
        reactivate: Whether the POST carried a truthy ``reactivate`` flag; only
            meaningful for an ``ARCHIVED`` ad. Callers pass the raw request
            flag — the ``ARCHIVED`` conjunct lives here.

    Returns:
        :class:`EditResult` naming the branch that ran and, for the two submit
        families, the orchestrator's outcome and errors.

    Raises:
        OperationalError: Propagated untouched (lock timeout — 03-DB-004).
    """
    is_reactivation = ad.status == AdStatus.ARCHIVED and reactivate
    is_text_resubmit = ad.status == AdStatus.PUBLISHED and text_fields_changed(dto, ad)

    if is_reactivation or is_text_resubmit:
        branch = EditOutcome.REACTIVATED if is_reactivation else EditOutcome.RESUBMITTED
        price_currency = resolve_edit_currency(dto, ad)
        submitted = _submit_like(ad, dto, price_currency)
        return EditResult(
            branch,
            submission_outcome=submitted.submission_outcome,
            errors=submitted.errors,
        )

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
