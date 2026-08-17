"""
Unit tests for mask_telegram_id sanitization utility.

Verifies that Telegram user IDs are masked with a non-reversible
SHA-256 hash before reaching log output (PII-002).
"""

from apps.core.utils.sanitize import mask_telegram_id


class TestMaskTelegramId:
    """Tests for mask_telegram_id."""

    def test_mask_telegram_id_masks_int(self) -> None:
        """mask_telegram_id(1098765432) returns 'tg_<8-hex>', raw NOT in result, length == 13."""
        result = mask_telegram_id(1098765432)
        assert result.startswith("tg_")
        assert len(result) == 11  # "tg_" (3 chars) + 8 hex chars
        assert str(1098765432) not in result

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
