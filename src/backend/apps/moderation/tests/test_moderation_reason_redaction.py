"""Moderator free text is redacted at write time (06-PII-114).

``ModeratorActionLog.reason`` is unbounded staff-authored free text on a row
that deliberately survives user erasure with ``user_id = NULL``. No erasure
sweep can reach it, so the only defence is redacting the value before the
INSERT, at the four writers that accept caller free text
(``log_manual_reject``, ``log_ban_account``, ``log_soft_delete``,
``log_photo_removed``).

These tests assert on the value read back from the database, never on a
helper's return value alone and never on an expected masked string. Pinning
the placeholder format would turn a future mask tuning into a false red.

The e-mail local part is deliberately realistic: ``_mask_email`` preserves a
local part of two or fewer characters, so ``a@b.co`` is untouched by design
and a test using it would pass for the wrong reason.
"""

from __future__ import annotations

import pytest

from apps.ads.admin import rejected_reason
from apps.core.enums import AdStatus, ModeratorActionType
from apps.core.utils.sanitize import redact_free_text
from apps.moderation.models import ModerationCriteria, ModeratorActionLog
from apps.moderation.services.moderation_log import (
    log_auto_fail,
    log_auto_publish,
    log_ban_account,
    log_manual_publish,
    log_manual_reject,
    log_photo_removed,
    log_soft_delete,
)
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

# A reason that carries both a phone number and an e-mail address with a local
# part longer than two characters, so the e-mail mask actually fires.
_PHONE = "+382 69 123 456"
_EMAIL = "ana.markovic@example.com"

# A reason with no phone, no e-mail and no two-or-more consecutive capitalised
# words, so the name mask cannot fire. "Photos" opens the sentence (title
# case) but the next word is lowercase, so it is not a multi-word name.
_CLEAN_REASON = "suspected spam; photos are blurry and the price looks wrong"

# The three fixed literals written by log_auto_fail, log_auto_publish and
# log_manual_publish — none of which is edited by this block.
_FIXED_LITERALS = (
    "Auto-moderation failed",
    "Auto-published",
    "Manually published by moderator",
)


@pytest.fixture
def moderation_criteria() -> ModerationCriteria:
    """Ensure the ModerationCriteria singleton exists with a safe cap."""
    criteria = ModerationCriteria.get_singleton()
    criteria.max_ads_per_user = 10
    criteria.save()
    return criteria


def _stored_reason(log: ModeratorActionLog) -> str:
    """Read ``reason`` back from the database, bypassing any in-memory value."""
    return ModeratorActionLog.objects.values_list("reason", flat=True).get(pk=log.pk)


# ---------------------------------------------------------------------------
# 1. Every free-text writer is redacted
# ---------------------------------------------------------------------------


def _write_via_manual_reject(seller, category, city, reason: str) -> ModeratorActionLog:
    ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
    return log_manual_reject(
        ad_id=ad.id,
        user_id=seller.id,
        moderator_id=seller.id,
        reason=reason,
    )


def _write_via_ban_account(seller, category, city, reason: str) -> ModeratorActionLog:
    return log_ban_account(user_id=seller.id, moderator_id=seller.id, reason=reason)


def _write_via_soft_delete(seller, category, city, reason: str) -> ModeratorActionLog:
    ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
    return log_soft_delete(
        ad_id=ad.id,
        user_id=seller.id,
        moderator_id=seller.id,
        reason=reason,
    )


def _write_via_photo_removed(seller, category, city, reason: str) -> ModeratorActionLog:
    ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
    return log_photo_removed(
        ad_id=ad.id,
        moderator_id=seller.id,
        reason=reason,
    )


_WRITERS = (
    _write_via_manual_reject,
    _write_via_ban_account,
    _write_via_soft_delete,
    _write_via_photo_removed,
)


@pytest.mark.parametrize("writer", _WRITERS, ids=lambda w: w.__name__)
def test_free_text_writer_stores_neither_phone_nor_email(
    writer, seller, category, city
) -> None:
    """Each free-text writer stores a reason with the phone and e-mail removed.

    A test that covers one writer proves nothing about the chokepoint; this
    one proves the rule holds for all four that accept caller free text.
    """
    reason = f"seller shared contact: call {_PHONE} or write to {_EMAIL}"
    log = writer(seller, category, city, reason)

    stored = _stored_reason(log)
    assert _PHONE not in stored
    assert _EMAIL not in stored
    # The rest of the moderator's words survive: only PII is masked.
    assert "seller shared contact" in stored


def test_title_case_prose_is_masked_by_the_name_rule(seller, category, city) -> None:
    """The name mask also masks title-case prose, and this is the honest trade-off.

    ``_NAME_PATTERN`` matches two or more consecutive capitalised words, so a
    moderator who writes "Photos Are Blurry" loses two words. The over-match is
    accepted rather than fixed: narrowing it would change masking behaviour for
    every caller of the shared pattern, beyond this block's scope. The
    ``help_text`` warns moderators that personal names are masked so the
    behaviour is stated, not discovered, and the rest of the sentence survives.
    """
    reason = "Photos Are Blurry and the price is wrong"
    log = _write_via_manual_reject(seller, category, city, reason)

    stored = _stored_reason(log)
    assert stored != reason
    assert "Photos Are Blurry" not in stored
    # Only the title-case run is masked; the lowercase prose is intact.
    assert "and the price is wrong" in stored


# ---------------------------------------------------------------------------
# 2. Clean text and the fixed literals are byte-identical
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("writer", _WRITERS, ids=lambda w: w.__name__)
def test_clean_reason_is_stored_byte_identical(
    writer, seller, category, city
) -> None:
    """A reason with no PII is stored exactly as supplied."""
    log = writer(seller, category, city, _CLEAN_REASON)
    assert _stored_reason(log) == _CLEAN_REASON


@pytest.mark.parametrize(
    "literal",
    _FIXED_LITERALS,
    ids=["auto_fail", "auto_publish", "manual_publish"],
)
def test_fixed_literal_is_stored_byte_identical(
    literal, moderation_criteria, seller, category, city
) -> None:
    """The three fixed-literal writers store their reason byte-identically.

    They are not edited by this block, so this pins that redaction is not an
    unconditional rewrite that would reformat legitimate audit content.
    """
    ad = create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)
    writer = {
        "Auto-moderation failed": lambda: log_auto_fail(
            ad_id=ad.id, user_id=seller.id
        ),
        "Auto-published": lambda: log_auto_publish(ad_id=ad.id, user_id=seller.id),
        "Manually published by moderator": lambda: log_manual_publish(
            ad_id=ad.id, moderator_id=seller.id
        ),
    }[literal]

    log = writer()
    assert _stored_reason(log) == literal


# ---------------------------------------------------------------------------
# 3. Idempotence as a property
# ---------------------------------------------------------------------------


def test_redaction_is_idempotent() -> None:
    """A second pass is a no-op: placeholders never accumulate asterisks.

    Assert the PROPERTY, never an expected masked string — pinning the
    placeholder format would turn a mask tuning into a false red.
    """
    once = redact_free_text(f"[{_PHONE}] {_EMAIL} and Ana Markovic wrote")
    assert redact_free_text(once) == once


def test_already_redacted_reason_is_not_corrupted(seller, category, city) -> None:
    """A reason already containing placeholders stores unchanged on re-write.

    Drives the property through a real writer and the database, not only a
    helper return value.
    """
    redacted = redact_free_text(f"call {_PHONE} or {_EMAIL}")
    log = _write_via_manual_reject(seller, category, city, redacted)
    assert _stored_reason(log) == redacted


# ---------------------------------------------------------------------------
# 4. No backfill, no read-time rewriting
# ---------------------------------------------------------------------------


def test_direct_insert_row_keeps_original_text(seller, category, city) -> None:
    """A row written straight through the manager keeps its un-redacted text.

    Redaction is a write-time rule applied by the four free-text service functions, not
    a read-time filter: a direct insert is not touched.
    """
    ad = create_test_ad(seller, category, city, status=AdStatus.REJECTED)
    original = f"legacy row with {_EMAIL}"

    log = ModeratorActionLog.objects.create(
        ad=ad,
        user=ad.user,
        action_type=ModeratorActionType.REJECT,
        reason=original,
    )

    assert _stored_reason(log) == original


def test_rejected_reason_helper_does_not_rewrite(seller, category, city) -> None:
    """``apps.ads.admin.rejected_reason`` returns the stored text unchanged.

    That helper is a render-time display over ``ModeratorActionLog.reason``
    and must not gain a filter; this pins that no read-time rewriting exists.
    """
    ad = create_test_ad(seller, category, city, status=AdStatus.REJECTED)
    original = f"legacy row with {_EMAIL}"

    ModeratorActionLog.objects.create(
        ad=ad,
        user=ad.user,
        action_type=ModeratorActionType.REJECT,
        reason=original,
    )

    assert rejected_reason(ad) == original


# ---------------------------------------------------------------------------
# 5. Not truncated
# ---------------------------------------------------------------------------


def test_clean_reason_longer_than_max_query_length_is_stored_in_full(
    seller, category, city
) -> None:
    """A clean reason longer than 100 characters is stored whole.

    This is the regression that would follow if ``redact_search_query``
    (which truncates to ``_MAX_QUERY_LENGTH = 100``) were used here instead
    of the non-truncating sibling.
    """
    long_reason = (_CLEAN_REASON + " ") * 5
    assert len(long_reason) > 100

    log = _write_via_manual_reject(seller, category, city, long_reason)
    assert _stored_reason(log) == long_reason
