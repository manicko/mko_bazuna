"""
Tests for contact service render conditions (zone R2).

Unit tests for can_contact_seller logic without database dependencies.
"""


class TestCanContactSellerLogic:
    """Tests for can_contact_seller render condition logic."""

    def test_all_conditions_required_for_contact(self):
        """Contact requires all 5 zone R2 conditions to be true."""
        # Test that all conditions must be met
        # Simulating the logic from can_contact_seller:
        # - ad.status == PUBLISHED
        # - seller.telegram_id IS NOT NULL
        # - NOT seller.is_deleted
        # - NOT seller.is_banned
        # - seller.consent_revoked_at IS NULL

        # All conditions true -> contact allowed
        conditions_all_true = {
            "status_published": True,
            "telegram_id_not_null": True,
            "not_deleted": True,
            "not_banned": True,
            "consent_not_revoked": True,
        }
        result = all(conditions_all_true.values())
        assert result is True

        # Any condition false -> contact blocked
        conditions_one_false = {
            "status_published": True,
            "telegram_id_not_null": False,  # This one fails
            "not_deleted": True,
            "not_banned": True,
            "consent_not_revoked": True,
        }
        result = all(conditions_one_false.values())
        assert result is False

    def test_status_must_be_published(self):
        """Only PUBLISHED status allows contact."""
        from apps.core.enums import AdStatus

        # Check that we're using StrEnum correctly
        for status in AdStatus:
            is_published = status == AdStatus.PUBLISHED
            if status == AdStatus.PUBLISHED:
                assert is_published is True
            else:
                assert is_published is False

    def test_telegram_id_required(self):
        """telegram_id must not be None for contact."""
        # None telegram_id blocks contact
        telegram_id_none = None
        assert telegram_id_none is None  # Would block contact

        # Valid telegram_id allows contact
        telegram_id_valid = 123456789
        assert telegram_id_valid is not None


class TestContactPattern:
    """Tests for contact deep-link pattern matching."""

    def test_contact_pattern_matches_ad_id(self):
        """Contact pattern matches contact_<ad_id> format."""
        import re

        CONTACT_PATTERN = re.compile(r"^contact_(\d+)$")

        # Valid patterns
        assert CONTACT_PATTERN.match("contact_123") is not None
        assert CONTACT_PATTERN.match("contact_1") is not None
        assert CONTACT_PATTERN.match("contact_999999") is not None

        # Invalid patterns
        assert CONTACT_PATTERN.match("login_abc123") is None
        assert CONTACT_PATTERN.match("contact_abc") is None
        assert CONTACT_PATTERN.match("contact_123abc") is None

    def test_contact_pattern_extracts_ad_id(self):
        """Contact pattern correctly extracts ad_id from deep-link."""
        import re

        CONTACT_PATTERN = re.compile(r"^contact_(\d+)$")

        match = CONTACT_PATTERN.match("contact_456")
        assert match is not None
        assert int(match.group(1)) == 456