"""Shared moderation test fixtures for permissive/banning criteria.

Registered as a pytest plugin via ``pytest_plugins`` in ``pyproject.toml`` so
that both the backend test tree (``src/backend``) and the bot test tree
(``src/telegram_bot``) can resolve these fixtures without relying on conftest
discovery (the two trees have separate conftest discovery boundaries).
"""
from unittest.mock import MagicMock

import pytest

from apps.moderation.models import ModerationCriteria

# Tuple layout of the criteria returned by _get_cached_criteria() in
# auto_moderation.py.  Positional order must match the unpacking site.
#   0: title_min_length
#   1: title_max_length
#   2: description_min_length
#   3: description_max_length
#   4: price_required
#   5: min_images
#   6: max_images
#   7: banned_words
#   8: max_ads_per_user
#   9: duplicate_title_threshold
_PERMISSIVE = (1, 200, 1, 2000, False, 0, 10, (), 100, 0)
_BANNING = (1, 200, 1, 2000, False, 0, 10, ("spam",), 100, 0)


@pytest.fixture
def permissive_criteria(monkeypatch) -> None:
    """Monkeypatch moderation criteria so auto_moderate passes trivially.

    Patches BOTH the cached read path (_get_cached_criteria in auto_moderation.py)
    AND the DB read path (ModerationCriteria.get_singleton in moderation_log.py)
    to ensure set_published's max_ads_per_user check is also permissive.
    """
    monkeypatch.setattr(
        "apps.moderation.services.auto_moderation._get_cached_criteria",
        lambda: _PERMISSIVE,
    )
    monkeypatch.setattr(
        "apps.moderation.services.auto_moderation._validate_max_ads_per_user",
        lambda user_id, max_ads: True,
    )
    monkeypatch.setattr(
        "apps.moderation.services.auto_moderation._is_duplicate_title",
        lambda title, user_id, ad_id, threshold: False,
    )
    _mock_criteria = MagicMock(spec=ModerationCriteria)
    _mock_criteria.max_ads_per_user = 100
    monkeypatch.setattr(
        "apps.moderation.services.moderation_log.ModerationCriteria.get_singleton",
        lambda: _mock_criteria,
    )


@pytest.fixture
def banning_criteria(monkeypatch) -> None:
    """Monkeypatch moderation criteria to fail on banned word 'spam'."""
    monkeypatch.setattr(
        "apps.moderation.services.auto_moderation._get_cached_criteria",
        lambda: _BANNING,
    )
    monkeypatch.setattr(
        "apps.moderation.services.auto_moderation._validate_max_ads_per_user",
        lambda user_id, max_ads: True,
    )
    monkeypatch.setattr(
        "apps.moderation.services.auto_moderation._is_duplicate_title",
        lambda title, user_id, ad_id, threshold: False,
    )
    _mock_criteria = MagicMock(spec=ModerationCriteria)
    _mock_criteria.max_ads_per_user = 100
    monkeypatch.setattr(
        "apps.moderation.services.moderation_log.ModerationCriteria.get_singleton",
        lambda: _mock_criteria,
    )
