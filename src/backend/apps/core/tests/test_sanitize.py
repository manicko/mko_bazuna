"""
Unit tests for the mask_telegram_id sanitization utility.

Verifies that Telegram user IDs are pseudonymised with a keyed HMAC-SHA-256
truncated to 12 hex before reaching log output (06-PII-112). The value is a
correlation identifier, never an authenticator.
"""

import pytest
from django.conf import settings

from apps.core.utils.sanitize import mask_telegram_id


class TestMaskTelegramId:
    """Tests for mask_telegram_id."""

    def test_mask_telegram_id_masks_int(self) -> None:
        """mask_telegram_id hashes the ID: prefix present, raw value absent."""
        raw = 1098765432
        result = mask_telegram_id(raw)
        assert result.startswith("tg_")
        assert str(raw) not in result
        # Same input always produces the same output (log correlation).
        assert result == mask_telegram_id(raw)
        # Distinct inputs produce distinct outputs.
        assert result != mask_telegram_id(raw + 1)

    def test_mask_telegram_id_none(self) -> None:
        """mask_telegram_id(None) returns 'None'."""
        assert mask_telegram_id(None) == "None"

    def test_mask_telegram_id_is_stable(self) -> None:
        """Same input always produces the same output (for log correlation)."""
        assert mask_telegram_id(111) == mask_telegram_id(111)
        assert mask_telegram_id(1098765432) == mask_telegram_id(1098765432)

    def test_mask_telegram_id_different_inputs(self) -> None:
        """Different inputs produce different outputs."""
        assert mask_telegram_id(111) != mask_telegram_id(222)

    def test_mask_telegram_id_no_raw_id(self) -> None:
        """Raw telegram_id string is not present in masked output."""
        raw = 1098765432
        masked = mask_telegram_id(raw)
        assert str(raw) not in masked


class TestMaskTelegramIdKeyedSecurityProperty:
    """The enumeration-defeat property the keyed HMAC exists to provide.

    An attacker who holds a mask and a small candidate list must not be able to
    confirm which candidate produced it without the key. This test fails on the
    old unsalted ``sha256(str(tid))[:8]`` construction by design.
    """

    _REAL_KEY = "unit-test-log-mask-key-at-least-32-bytes-long"
    _WRONG_KEY = "unit-test-wrong-log-mask-key-at-least-32-bytes!!"
    _TRUE_ID = 1098765432

    def test_candidate_cannot_be_confirmed_without_the_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A party without the key cannot match any candidate to a real mask."""
        candidates = [self._TRUE_ID - 1, self._TRUE_ID, self._TRUE_ID + 1]

        monkeypatch.setattr(settings, "LOG_MASK_KEY", self._REAL_KEY)
        real_mask = mask_telegram_id(self._TRUE_ID)

        # Without the key the candidates are unverifiable: swapping in a
        # different key changes every candidate's mask, so none matches.
        monkeypatch.setattr(settings, "LOG_MASK_KEY", self._WRONG_KEY)
        forged = {candidate: mask_telegram_id(candidate) for candidate in candidates}
        assert real_mask not in forged.values()

        # With the real key restored, the true candidate matches and the others
        # do not, so the mask is correlatable by whoever holds the key.
        monkeypatch.setattr(settings, "LOG_MASK_KEY", self._REAL_KEY)
        trusted = {candidate: mask_telegram_id(candidate) for candidate in candidates}
        assert trusted[self._TRUE_ID] == real_mask
        assert trusted[self._TRUE_ID - 1] != real_mask
        assert trusted[self._TRUE_ID + 1] != real_mask

    def test_empty_key_never_leaks_raw_value(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With no LOG_MASK_KEY the mask still hides the raw ID and warns once."""
        monkeypatch.setattr(settings, "LOG_MASK_KEY", "")
        masked = mask_telegram_id(self._TRUE_ID)
        assert masked.startswith("tg_")
        assert str(self._TRUE_ID) not in masked
