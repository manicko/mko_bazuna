"""
Tests for auto-moderation service validation functions.

Unit tests for validation rules without database dependencies.
"""

from apps.moderation.services.auto_moderation import (
    _contains_banned_words,
    _validate_description_length,
    _validate_image_count,
    _validate_title_length,
)


class TestValidateTitleLength:
    """Tests for _validate_title_length function."""

    def test_title_too_short_returns_false(self):
        """Title below minimum length returns False."""
        result = _validate_title_length("abc", min_len=5, max_len=100)
        assert result is False

    def test_title_too_long_returns_false(self):
        """Title above maximum length returns False."""
        title = "x" * 150
        result = _validate_title_length(title, min_len=5, max_len=100)
        assert result is False

    def test_title_min_boundary_returns_true(self):
        """Title at minimum length returns True."""
        result = _validate_title_length("abcde", min_len=5, max_len=100)
        assert result is True

    def test_title_max_boundary_returns_true(self):
        """Title at maximum length returns True."""
        title = "x" * 100
        result = _validate_title_length(title, min_len=5, max_len=100)
        assert result is True

    def test_title_within_range_returns_true(self):
        """Title within valid range returns True."""
        result = _validate_title_length("Valid Title", min_len=5, max_len=100)
        assert result is True


class TestValidateDescriptionLength:
    """Tests for _validate_description_length function."""

    def test_description_too_short_returns_false(self):
        """Description below minimum length returns False."""
        result = _validate_description_length("short", min_len=10, max_len=2000)
        assert result is False

    def test_description_too_long_returns_false(self):
        """Description above maximum length returns False."""
        desc = "x" * 2500
        result = _validate_description_length(desc, min_len=10, max_len=2000)
        assert result is False

    def test_description_min_boundary_returns_true(self):
        """Description at minimum length returns True."""
        result = _validate_description_length("x" * 10, min_len=10, max_len=2000)
        assert result is True

    def test_description_max_boundary_returns_true(self):
        """Description at maximum length returns True."""
        desc = "x" * 2000
        result = _validate_description_length(desc, min_len=10, max_len=2000)
        assert result is True


class TestValidateImageCount:
    """Tests for _validate_image_count function."""

    def test_no_images_returns_false(self):
        """No images returns False when min_images=1."""

        class MockImagesQuerySet:
            def count(self):
                return 0

        class MockAd:
            @property
            def images(self):
                return MockImagesQuerySet()

        result = _validate_image_count(MockAd(), min_count=1, max_count=5)
        assert result is False

    def test_too_many_images_returns_false(self):
        """Too many images returns False."""

        class MockImagesQuerySet:
            def count(self):
                return 7

        class MockAd:
            @property
            def images(self):
                return MockImagesQuerySet()

        result = _validate_image_count(MockAd(), min_count=1, max_count=5)
        assert result is False

    def test_valid_image_count_returns_true(self):
        """Valid image count returns True."""

        class MockImagesQuerySet:
            def count(self):
                return 3

        class MockAd:
            @property
            def images(self):
                return MockImagesQuerySet()

        result = _validate_image_count(MockAd(), min_count=1, max_count=5)
        assert result is True


class TestContainsBannedWords:
    """Tests for _contains_banned_words function."""

    def test_banned_word_in_title_returns_true(self):
        """Banned word in title returns True."""
        result = _contains_banned_words("Spammy Title", "Description here", ("spam", "scam"))
        assert result is True

    def test_banned_word_in_description_returns_true(self):
        """Banned word in description returns True."""
        result = _contains_banned_words("Title here", "This is a scam", ("spam", "scam"))
        assert result is True

    def test_banned_word_case_insensitive_returns_true(self):
        """Banned word matching is case-insensitive."""
        result = _contains_banned_words("SPAM Title", "Description", ("spam", "scam"))
        assert result is True

    def test_no_banned_words_returns_false(self):
        """No banned words returns False."""
        result = _contains_banned_words("Normal Title", "Normal description", ("spam", "scam"))
        assert result is False

    def test_empty_banned_words_returns_false(self):
        """Empty banned words tuple returns False."""
        result = _contains_banned_words("Any Title", "Any description", ())
        assert result is False